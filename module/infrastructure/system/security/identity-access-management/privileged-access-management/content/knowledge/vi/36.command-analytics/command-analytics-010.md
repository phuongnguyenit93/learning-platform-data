# Phát hiện command bất thường

## 1. Mục tiêu và phạm vi

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), phát hiện command bất thường là nhận ra thao tác hoặc chuỗi thao tác lệch khỏi mục đích đã được cấp quyền, cách làm việc thường thấy và mức rủi ro chấp nhận được của tài sản. Đối tượng có thể là người quản trị, nhà thầu hoặc tài khoản dịch vụ đang thao tác trên hệ điều hành, cơ sở dữ liệu hay thiết bị hạ tầng.

Một câu lệnh hợp lệ về cú pháp vẫn có thể nằm ngoài phạm vi công việc. Ngược lại, một command chưa từng xuất hiện có thể là thao tác bảo trì hợp lệ. Vì vậy, kết quả phân tích cần trả lời đồng thời:

- Ai khởi tạo thao tác, dùng tài khoản nào và thực thi với quyền hiệu lực nào?
- Thao tác tác động đến tài sản, dữ liệu hoặc chính sách nào?
- Phiên được phê duyệt làm gì, trong khoảng thời gian nào?
- Hành vi lệch khỏi lịch sử và nhóm công việc tương đồng đến mức nào?
- Có đủ bằng chứng để điều tra hoặc can thiệp hay chưa?

Sau bài này, người học có thể thiết kế dữ liệu đầu vào, kết hợp quy tắc với đường cơ sở hành vi, xây dựng cảnh báo giải thích được và kiểm thử cơ chế phát hiện bằng dữ liệu mô phỏng.

Trọng tâm là kiểm soát hành vi trong phiên đặc quyền. Vault, JIT/JEA, luân chuyển credential và giám sát phiên cung cấp ngữ cảnh hoặc biện pháp phản ứng; chúng không tự chứng minh rằng mọi thao tác trong phiên đều phù hợp.

## 2. Phân biệt bất thường, vi phạm và dấu hiệu xâm nhập

Ba khái niệm này có quan hệ nhưng không đồng nghĩa.

| Khái niệm | Câu hỏi chính | Ví dụ trong PAM | Cách sử dụng kết quả |
| --- | --- | --- | --- |
| Bất thường hành vi | Thao tác có khác cách làm việc thường thấy không? | Tài khoản dịch vụ lần đầu mở phiên tương tác | Bổ sung ngữ cảnh và điều tra |
| Vi phạm chính sách | Thao tác có trái quy định hoặc ngoài phạm vi đã cấp không? | Phiên chỉ được xem cấu hình nhưng lại sửa quyền | Áp dụng quy trình xử lý vi phạm đã định nghĩa |
| Dấu hiệu xâm nhập | Có bằng chứng hỗ trợ giả thuyết tài khoản hoặc máy bị chiếm dụng không? | Thay đổi quyền, truy cập dữ liệu nhạy cảm rồi kết nối đến đích chưa được phép | Liên kết nhiều nguồn để điều tra sự cố |

Một hành vi có thể thuộc nhiều nhóm. Ví dụ, tài khoản chỉ đọc sửa cấu hình là vi phạm dù thao tác đó đã xuất hiện nhiều lần trong lịch sử. Nếu dùng lịch sử làm chuẩn duy nhất, hệ thống có thể học cả hành vi sai thành “bình thường”.

Ngược lại, thao tác nâng cấp lần đầu có thể có độ hiếm cao nhưng phù hợp change ticket, đúng máy đích và được thực hiện trong cửa sổ bảo trì. Độ hiếm vẫn hữu ích cho quan sát, nhưng riêng nó không đủ để kết luận có tấn công.

Nên phân biệt ba trạng thái khi đối chiếu phạm vi: `MATCH`, `MISMATCH` và `UNKNOWN`. Thiếu ticket, chưa đồng bộ danh mục tài sản hoặc không xác định được command không được coi mặc nhiên là đã được phê duyệt.

## 3. Tình huống xuyên suốt

Một doanh nghiệp cấp phiên JIT cho kỹ sư vận hành trên `db-prod-02`. Yêu cầu `CHG-2048` cho phép:

- Xem trạng thái dịch vụ cơ sở dữ liệu.
- Đọc log vận hành đã được phân quyền.
- Không thay đổi cấu hình, quyền truy cập hoặc xuất dữ liệu khách hàng.
- Sử dụng quyền từ 02:00 đến trước 02:30 UTC.

Trong phiên, hệ thống quan sát các sự kiện:

| Thời điểm UTC | Hành vi đã chuẩn hóa | Ngữ cảnh | Đánh giá ban đầu |
| --- | --- | --- | --- |
| 02:05 | `service.status.read` | Đúng máy, đúng phạm vi | Phù hợp yêu cầu |
| 02:07 | `service.log.read` | Đúng nhóm log vận hành | Phù hợp yêu cầu |
| 02:11 | `identity.permission.change` | Tác động đến quyền truy cập | Ngoài phạm vi chỉ đọc |
| 02:12 | `sensitive_data.export` | Có truy cập dữ liệu khách hàng | Ngoài phạm vi và tác động cao |
| 02:13 | `network.destination.connect` | Đích chưa có trong danh sách được phép | Cần liên kết tiến trình và lưu lượng |

Bảng mô tả sự kiện phân tích, không phải một chuỗi lệnh để chạy. Tên hành vi là taxonomy minh họa do tổ chức xây dựng, không phải tên trường chuẩn của mọi sản phẩm PAM.

Một lần chạy công cụ quản trị không đủ để suy ra toàn bộ chuỗi trên. Cần chứng cứ về đối tượng bị tác động, kết quả thực thi, tiến trình và kết nối tương ứng. Nếu mới có bản ghi nhập command, chỉ có thể khẳng định ý định hoặc thao tác được yêu cầu ở mức nguồn đó quan sát được.

## 4. Thu thập đúng lớp bằng chứng

### 4.1. Nguồn dữ liệu và giới hạn quan sát

| Nguồn | Giá trị đối với phân tích | Giới hạn cần ghi rõ |
| --- | --- | --- |
| PAM gateway hoặc proxy | Phiên, yêu cầu truy cập, tài khoản đích, dữ liệu tương tác | Chỉ quan sát đường truy cập đi qua thành phần đó |
| Ghi hình hoặc terminal recording | Diễn biến phiên và nội dung hiển thị | Không thay thế đầy đủ sự kiện tiến trình hay kết quả thay đổi |
| Audit hệ điều hành hoặc endpoint | Tiến trình, người dùng thực thi, quan hệ cha con, sự kiện tài nguyên tùy cấu hình | Mức chi tiết phụ thuộc nền tảng và chính sách thu thập |
| Audit cơ sở dữ liệu hoặc thiết bị | Thao tác theo ngữ nghĩa tài nguyên | Có thể không có biểu diễn shell command |
| Ticket, JIT, JEA và danh mục tài sản | Mục đích, quyền được cấp, thời hạn, độ nhạy cảm | Dữ liệu có thể thiếu hoặc đồng bộ chậm |
| Telemetry mạng | Đích kết nối, hướng lưu lượng, khối lượng và thời gian | Cần liên kết với tiến trình hoặc phiên trước khi quy kết |

Không dùng shell history làm nguồn duy nhất. Nó không bao phủ toàn bộ thao tác, có thể không được ghi kịp thời và không chứng minh kết quả thực thi.

Không phải mọi thao tác đều tạo một tiến trình mới. Shell built-in, script, công cụ chạy dài, thủ tục trong cơ sở dữ liệu hoặc thao tác qua API có thể cần nguồn audit khác. Một lần khởi chạy interpreter cũng không cho biết toàn bộ nội dung đã được thực thi bên trong.

Với PowerShell, shell trên Linux, công cụ SQL hoặc CLI của thiết bị mạng, nên có bộ chuẩn hóa phù hợp từng ngôn ngữ và nguồn. Không áp dụng một parser hoặc một biểu thức chính quy cho mọi dạng command.

### 4.2. Danh tính người yêu cầu và danh tính thực thi

Cần giữ riêng:

- Người hoặc workload yêu cầu phiên.
- Tài khoản đặc quyền được checkout hoặc được ánh xạ.
- Danh tính hiệu lực tại thời điểm thực thi.
- Danh tính workload, pipeline hoặc dịch vụ khởi tạo thao tác tự động.

Nếu chỉ lưu `root` hoặc một tài khoản quản trị dùng chung, đội điều tra khó biết ai thực sự hành động. Ngược lại, chỉ lưu người yêu cầu mà bỏ qua thay đổi quyền hiệu lực sẽ che mất các bước chuyển quyền trong phiên.

Liên kết các lớp danh tính bằng bằng chứng từ PAM và nền tảng đích. Khi không ánh xạ chắc chắn, ghi rõ mức tin cậy; không ghép chỉ vì hai sự kiện có tên người dùng giống nhau.

## 5. Thiết kế sự kiện chuẩn hóa

Một schema phân tích nên giữ cả dữ liệu nguồn và dữ liệu đã diễn giải. Ví dụ dưới đây đã rút gọn và dùng giá trị giả lập:

```json
{
  "event_id": "evt-0104",
  "event_time": "2026-01-15T02:11:00Z",
  "ingest_time": "2026-01-15T02:11:03Z",
  "source": "endpoint-audit",
  "source_event_id": "host02-7781",
  "session_id": "pam-session-023",
  "request_id": "CHG-2048",
  "actor_id": "engineer-17",
  "privileged_account": "ops-admin",
  "effective_identity": "uid:0",
  "asset_id": "db-prod-02",
  "asset_tier": "critical",
  "process_instance_id": "host02-boot07-proc7781",
  "parent_process_instance_id": "host02-boot07-proc7700",
  "operation": "identity.permission.change",
  "target_class": "identity_policy",
  "command_redacted": "permission-tool <redacted-arguments>",
  "parser_status": "SUPPORTED",
  "approval_match": "MISMATCH",
  "result": "SUCCESS",
  "telemetry_confidence": "HIGH"
}
```

`process_instance_id` phải đủ phân biệt các lần tái sử dụng PID trên máy đích; PID đơn lẻ thường không đủ cho liên kết dài hạn. Cách tạo khóa cụ thể phụ thuộc nguồn telemetry, chẳng hạn kết hợp máy, lần khởi động và thời điểm bắt đầu tiến trình.

Các nguyên tắc cần giữ:

1. `event_time` phản ánh thời điểm hành vi tại nguồn; `ingest_time` phản ánh khi hệ thống nhận sự kiện.
2. Lưu múi giờ nhất quán, độ lệch đồng hồ đã biết và chất lượng đồng bộ thời gian.
3. Mỗi sự kiện phải truy nguyên được đến bản ghi nguồn bằng khóa ổn định.
4. `UNKNOWN`, `NOT_APPLICABLE`, `FAILED` và `SUCCESS` có nghĩa riêng; không thay giá trị thiếu bằng một giá trị thành công.
5. Chỉ gán `SUCCESS` khi nguồn cung cấp bằng chứng phù hợp. Một lần nhập command không chứng minh thao tác đã hoàn tất.
6. Dữ liệu nguồn cần được bảo toàn theo chính sách bằng chứng; dữ liệu chuẩn hóa có thể được tái tạo và gắn phiên bản parser.
7. Phát hiện trùng phải dựa vào khóa nguồn hoặc định danh phù hợp. Không loại mọi command giống nhau vì người dùng có thể thực thi lặp thật.

Trường `operation` trong ví dụ là kết quả phân loại ngữ nghĩa, không phải chuỗi lấy trực tiếp từ command rồi tin tuyệt đối. Nếu parser không hỗ trợ cú pháp hoặc thiếu ngữ cảnh, cần để trạng thái chưa xác định và giảm mức chắc chắn của suy luận liên quan.

## 6. Chuẩn hóa command mà không làm mất ý nghĩa

### 6.1. Giữ hai biểu diễn phục vụ hai mục đích

Biểu diễn nguồn hỗ trợ điều tra và đối chiếu. Biểu diễn chuẩn hóa hỗ trợ tìm kiếm, so sánh và tạo đặc trưng. Không ghi đè biểu diễn nguồn bằng fingerprint đã rút gọn.

Ví dụ, có thể tạo fingerprint từ:

```text
executable_identity
+ subcommand
+ meaningful_option_names
+ target_resource_class
+ execution_context
```

Không nên đưa timestamp, mã yêu cầu ngẫu nhiên hoặc tên tệp tạm vào mọi fingerprint vì chúng làm các thao tác cùng loại trở nên “mới” một cách giả tạo. Tuy nhiên, bỏ toàn bộ tham số cũng sai: tham số thường quyết định đọc hay ghi, môi trường thử nghiệm hay production, tài nguyên thông thường hay nhạy cảm.

### 6.2. Không đánh đồng tên công cụ với hành vi

Các công cụ như shell, trình quản trị dịch vụ hoặc trình khách cơ sở dữ liệu phục vụ nhiều mục đích hợp lệ. Phát hiện chỉ dựa vào tên executable dễ tạo nhiều cảnh báo thiếu ngữ cảnh.

Nên phân tích theo các lớp:

- Danh tính executable: đường dẫn đã quan sát và thông tin tin cậy mà nguồn thực sự cung cấp.
- Cấu trúc lệnh: subcommand, toán tử shell, tham số và dữ liệu đầu vào khi có thể hiểu đúng.
- Đối tượng: máy đích, tài nguyên, loại dữ liệu và môi trường.
- Quyền: danh tính hiệu lực và các bước chuyển quyền.
- Hệ quả: audit thay đổi, tiến trình con, truy cập tài nguyên hoặc kết nối liên quan.

Không tự khẳng định executable đáng tin chỉ vì tên giống một tiện ích hệ thống.

### 6.3. Giới hạn parser và giải mã

Chuỗi nhập vào terminal có thể chứa dấu nháy, pipeline, chuyển hướng, biến hoặc nhiều lớp interpreter. Tách token bằng khoảng trắng không mô phỏng đúng cú pháp shell.

Nếu dữ liệu có biểu diễn mã hóa hoặc nén, việc chuyển đổi để phân tích phải có giới hạn kích thước, độ sâu và tài nguyên. Giữ nguyên dấu vết chuyển đổi. Không chạy command, script hay nội dung giải mã chỉ để biết nó có “độc hại” hay không.

Một command dùng mã hóa chỉ là tín hiệu ngữ cảnh. Công cụ quản trị và tự động hóa hợp lệ cũng có thể dùng cách biểu diễn này. Khi không giải thích được ngữ nghĩa, báo khoảng trống phân tích; không tự gán hành vi xuất dữ liệu hoặc sửa quyền.

## 7. Xây dựng đường cơ sở hành vi

Đường cơ sở (baseline) mô tả hành vi thường gặp trong một ngữ cảnh đã định nghĩa. Chọn phạm vi đủ tương đồng trước khi thống kê.

| Chiều phân nhóm | Cách sử dụng | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| Người quản trị hoặc workload | So sánh với lịch sử của cùng chủ thể | Lẫn tự động hóa với thao tác tương tác |
| Vai trò công việc | So sánh với nhóm có nhiệm vụ tương đồng | Kỹ sư cơ sở dữ liệu bị so với quản trị mạng |
| Loại và độ nhạy tài sản | Phân biệt production, lab, máy quản lý danh tính | Hành vi ở lab làm loãng tín hiệu trên tài sản quan trọng |
| Kiểu phiên | Tách tương tác, batch, pipeline, break-glass | Tần suất command không còn cùng ý nghĩa |
| Cửa sổ vận hành | Nhận diện bảo trì hoặc lịch chạy định kỳ | Báo động giả với tác vụ hợp lệ ngoài giờ hành chính |

Phân nhóm quá nhỏ tạo mẫu ít và baseline không ổn định. Phân nhóm quá rộng che khuất bất thường. Có thể dùng baseline theo thứ bậc: lịch sử riêng của chủ thể nếu đủ mẫu, sau đó nhóm vai trò trên cùng lớp tài sản, rồi mức tổng quát hơn; luôn ghi nhận mức dữ liệu đã dùng.

### 7.1. Các đặc trưng hữu ích

- Command hoặc loại thao tác xuất hiện lần đầu đối với chủ thể.
- Tài sản, lớp tài nguyên hoặc đích kết nối chưa từng được sử dụng.
- Tỷ lệ thao tác thay đổi quyền so với tổng thao tác có ngữ nghĩa xác định.
- Số tài sản khác nhau được tiếp cận trong một phiên hoặc cửa sổ thời gian.
- Chuỗi chuyển từ đọc trạng thái sang thay đổi quyền, rồi đến dữ liệu nhạy cảm.
- Tài khoản dịch vụ chuyển sang tương tác khi chính sách chỉ cho chạy workload.
- Tần suất hoặc tốc độ thao tác lệch đáng kể khỏi các phiên tương đồng.
- Hành vi tiếp diễn ngoài thời hạn được cấp hoặc sau khi quyền bị thu hồi, nếu có chứng cứ thời gian và thực thi.

“Mới đối với người dùng” và “hiếm trong nhóm” là hai tín hiệu khác nhau. Một kỹ sư mới vào nhóm thường có nhiều hành vi mới đối với cá nhân, nhưng các thao tác đó có thể phổ biến trong nhóm được phân công.

### 7.2. Công thức đơn giản và cách đọc

Với một nhóm ngữ cảnh có `N` phiên đủ chất lượng, gọi `n(c)` là số phiên có xuất hiện fingerprint `c`. Một tỷ lệ có làm trơn minh họa là:

```text
p(c) = (n(c) + 1) / (N + 2)
rarity(c) = -ln(p(c))
```

Đây là cách làm trơn tỷ lệ hiện diện/không hiện diện của một fingerprint theo phiên, không phải một phân phối xác suất cộng lại bằng 1 cho mọi command. Chọn đơn vị phiên giúp giảm việc một script lặp command hàng nghìn lần chi phối thống kê. Nếu chọn đơn vị sự kiện thay vì phiên, cần định nghĩa lại tử số và mẫu số.

Ví dụ `N = 98`, `n(c) = 0` cho `p(c) = 0,01` và `rarity(c) ≈ 4,61`. Đây là thước đo độ hiếm trong mẫu đã chọn, không phải xác suất command độc hại.

Baseline ít mẫu phải mang nhãn `LOW_SUPPORT`. Không xử lý tài khoản mới bằng cách coi mọi thao tác đầu tiên là sự cố nghiêm trọng. Hãy dựa thêm vào nhóm tương đồng, quyền đã cấp và các quy tắc có ngữ nghĩa rõ.

### 7.3. Chống học nhầm hành vi xấu

Không đưa mọi dữ liệu mới vào baseline ngay lập tức. Cần có khoảng trễ cập nhật, phiên bản baseline và quy tắc xử lý dữ liệu đang điều tra. Một tài khoản bị chiếm dụng có thể tạo hành vi lặp đủ nhiều để làm hành vi đó trở nên phổ biến trong lịch sử.

Dữ liệu vi phạm chính sách đã xác nhận không nên trở thành mẫu “hợp lệ” chỉ vì xuất hiện nhiều. Đồng thời, phải theo dõi thay đổi thật như triển khai công cụ mới hoặc chuyển lịch vận hành để baseline không lỗi thời kéo dài.

## 8. Kết hợp các lớp phát hiện

### 8.1. Quy tắc dựa trên chính sách

Các điều kiện có thể giải thích rõ thường phù hợp làm lớp đầu:

- Thao tác thay đổi quyền nhưng phê duyệt chỉ cho phép đọc.
- Tài nguyên đích nằm ngoài phạm vi được cấp.
- Tài khoản dịch vụ dùng kiểu truy cập tương tác trái chính sách.
- Thao tác đặc quyền xảy ra ngoài thời hạn đã cấp, với dấu thời gian đáng tin.
- Thay đổi hoặc yêu cầu thay đổi cơ chế ghi log trong phiên không được phê duyệt cho nhiệm vụ đó.

Lần thử thay đổi cũng có thể đáng cảnh báo dù thao tác thất bại. Tuy nhiên, cảnh báo phải phân biệt “đã thử” và “đã thay đổi thành công” để không phóng đại tác động.

Đối chiếu phê duyệt nên dùng tập phạm vi có cấu trúc: hành vi, tài nguyên, danh tính, kiểu phiên, thời hạn và điều kiện bổ sung. Ticket có chữ “bảo trì” không đồng nghĩa được phép làm mọi việc.

### 8.2. Phát hiện độ lệch

Độ lệch bổ sung khả năng nhận ra hành vi chưa được viết thành quy tắc:

- Fingerprint mới trong nhóm đã có đủ mẫu.
- Tăng bất thường số tài sản tiếp cận trong một cửa sổ.
- Tỷ lệ thao tác nhạy cảm tăng so với các phiên cùng loại.
- Trình tự thao tác khác với quy trình vận hành đã quan sát.

Không nên gọi mô hình độ lệch là bộ phân loại đúng/sai tuyệt đối. Cần cho người điều tra biết cửa sổ lịch sử, số mẫu và yếu tố nào làm điểm tăng.

### 8.3. Tương quan chuỗi hành vi

Một chuỗi đáng chú ý có thể gồm:

```text
thay đổi quyền
    → truy cập dữ liệu nhạy cảm
    → kết nối đến đích chưa được phép
```

Chuỗi này chỉ hỗ trợ giả thuyết cần điều tra. Các sự kiện gần nhau về thời gian có thể thuộc các công việc khác nhau.

Khi tương quan, ưu tiên khóa phiên, tài sản, danh tính và quan hệ tiến trình. Nêu rõ loại liên kết: chắc chắn từ cùng tiến trình, cùng phiên có nhiều tiến trình, hay suy đoán từ cửa sổ thời gian.

Cửa sổ 5 hoặc 10 phút là tham số vận hành minh họa, không phải chuẩn cố định. Với tác vụ chạy lâu, cần mô hình khác và cơ chế giới hạn trạng thái để tránh ghép các phiên không liên quan.

## 9. Chấm điểm rủi ro và chất lượng bằng chứng

Nên giữ riêng điểm rủi ro và độ tin cậy telemetry. Một tài sản rất nhạy cảm làm tăng hậu quả tiềm tàng nhưng không làm parser chính xác hơn.

Ví dụ mô hình cộng điểm minh họa:

| Tín hiệu | Điểm ví dụ | Điều kiện áp dụng |
| --- | --- | --- |
| Ngoài phạm vi phê duyệt | 40 | Có đủ dữ liệu để kết luận `MISMATCH` |
| Thao tác nhạy cảm đã xác định | 25 | Nhận diện được hành vi và đối tượng |
| Hành vi hiếm | 15 | Baseline đủ mẫu và đặc trưng phù hợp |
| Tài sản quan trọng | 10 | Danh mục tài sản được quản lý |
| Chuỗi hành vi có nhiều nguồn hỗ trợ | 20 | Có liên kết ngữ cảnh đủ tin cậy |

Có thể chặn tổng ở 100, nhưng thang điểm phải được hiệu chỉnh theo dữ liệu và khả năng xử lý của tổ chức. Điểm 80 không có nghĩa xác suất xâm nhập là 80%.

Nếu một tín hiệu kéo theo tín hiệu khác từ cùng bằng chứng, cộng cả hai có thể đếm trùng. Ví dụ “thao tác sửa quyền” và “command thuộc nhóm sửa quyền” có thể chỉ là một đặc trưng. Cần đánh giá sự phụ thuộc, giới hạn đóng góp theo nhóm hoặc dùng quy tắc ưu tiên.

Thiếu telemetry cần có luồng xử lý riêng. Khi nguồn audit mất dữ liệu, hệ thống không được hiển thị “không có bất thường” như thể đã quan sát đầy đủ. Có thể vừa giữ mức rủi ro từ các chứng cứ còn lại, vừa phát cảnh báo sức khỏe dữ liệu và hạn chế phản ứng tự động có yêu cầu bằng chứng cao.

## 10. Ví dụ logic phát hiện có thể kiểm thử

Mã giả sau minh họa cách phát hiện thao tác nhạy cảm ngoài phạm vi hoặc có dấu hiệu mới. Đây không phải cấu hình của một sản phẩm cụ thể.

```text
function evaluate(event, approvalSnapshot, baseline):
    reasons = []
    dataIssues = []

    if event.parser_status != SUPPORTED:
        dataIssues.add("UNSUPPORTED_COMMAND_SYNTAX")

    if event.event_time_quality != TRUSTED:
        dataIssues.add("UNTRUSTED_EVENT_TIME")

    scope = compareApproval(
        actor = event.actor_id,
        account = event.privileged_account,
        asset = event.asset_id,
        operation = event.operation,
        target = event.target_resource,
        sessionType = event.session_type,
        eventTime = event.event_time,
        approval = approvalSnapshot
    )
    # compareApproval trả MATCH, MISMATCH hoặc UNKNOWN.
    # Khoảng hiệu lực dùng [valid_from, valid_to).
    # operation không xác định khiến đối chiếu hành vi trả UNKNOWN.

    sensitive = event.operation in {
        "identity.permission.change",
        "security_logging.configuration.change",
        "sensitive_data.export"
    }

    risk = 0

    if scope == MISMATCH:
        risk += 40
        reasons.add("APPROVAL_SCOPE_MISMATCH")
    else if scope == UNKNOWN:
        dataIssues.add("APPROVAL_CONTEXT_INCOMPLETE")

    if sensitive:
        risk += 25
        reasons.add("SENSITIVE_OPERATION")

    rarity = NOT_EVALUATED
    if baseline.support == SUFFICIENT and event.fingerprint is known:
        rarity = baseline.rarity(event.fingerprint)
        if rarity >= configuredRarityThreshold:
            risk += 15
            reasons.add("RARE_FOR_PEER_CONTEXT")

    if event.asset_tier == CRITICAL and risk > 0:
        risk += 10
        reasons.add("CRITICAL_ASSET")

    policyViolation = (scope == MISMATCH)
    behavioralCandidate = sensitive
        and (rarity is evaluated)
        and (rarity >= configuredRarityThreshold)

    return {
        alert: policyViolation or behavioralCandidate,
        risk: min(risk, 100),
        reasons: reasons,
        dataIssues: dataIssues,
        scope: scope,
        ruleVersion: "demo-1"
    }
```

Một số điểm cố ý tách rõ:

- Vi phạm phạm vi có thể tạo cảnh báo dù command không hiếm.
- Baseline thiếu mẫu làm bỏ qua phép tính độ hiếm, không tự biến độ hiếm thành 0.
- `UNKNOWN` không được chuyển thành `MATCH`.
- Nhãn tài sản quan trọng không tự tạo cảnh báo khi chưa có tín hiệu hành vi.
- Trường `risk` phục vụ ưu tiên trong mô hình minh họa; quyết định tạo cảnh báo là điều kiện riêng.
- Logic không tự chặn command. Hệ thống chặn trước thực thi cần một điểm cưỡng chế và chính sách riêng.

Trong triển khai thật, `compareApproval` phải dùng phiên bản phê duyệt có hiệu lực khi sự kiện xảy ra. Không dùng một ticket được sửa hoặc gia hạn sau đó để tự động hợp thức hóa hành vi trước thời điểm thay đổi.

### Bộ dữ liệu kiểm thử tối thiểu

Giả sử ngưỡng độ hiếm đã cấu hình và các đầu vào cần thiết đều có mặt trừ khi bảng nói khác.

| Ca | Dữ kiện chính | Kết quả mong đợi |
| --- | --- | --- |
| A | Đọc trạng thái, đúng phê duyệt, không hiếm, tài sản thường | Không cảnh báo hành vi |
| B | Sửa quyền, ngoài phạm vi, tài sản quan trọng, không hiếm | Cảnh báo; điểm 75; có lý do vi phạm và thao tác nhạy cảm |
| C | Xuất dữ liệu được phê duyệt đúng phạm vi, hiếm, tài sản quan trọng | Cảnh báo ứng viên hành vi; điểm 50; chưa kết luận vi phạm |
| D | Parser không hỗ trợ, thiếu đối tượng nên phạm vi chưa xác định | Có vấn đề dữ liệu; chưa đủ căn cứ kết luận phạm vi khớp |
| E | Sửa quyền ngoài phạm vi, baseline thiếu mẫu, tài sản thường | Cảnh báo; điểm 65; không cần điểm độ hiếm |
| F | Thao tác yêu cầu ngoài phạm vi nhưng thực thi thất bại | Có thể vẫn cảnh báo vi phạm; nội dung ghi rõ lần thử thất bại |

Bổ sung kiểm thử ngay sát thời điểm hết hạn. Với khoảng `[02:00, 02:30)`, sự kiện đáng tin ở 02:30 không còn nằm trong cửa sổ. Nếu đồng hồ nguồn có sai số đáng kể, kết quả cần phản ánh sự không chắc chắn thay vì đưa ra kết luận chính xác giả tạo.

## 11. Dữ liệu đến trễ, trùng và không đúng thứ tự

Phát hiện chuỗi dựa vào `event_time`, đồng thời theo dõi độ trễ qua `ingest_time`. Hai sự kiện đến sau không nhất thiết xảy ra sau.

Một cách vận hành:

1. Khử trùng theo định danh nguồn phù hợp.
2. Đưa sự kiện vào trạng thái tương quan theo khóa phiên và tài sản.
3. Chờ trong khoảng trễ cho phép theo đặc tính nguồn.
4. Khi có dữ liệu bổ sung, cập nhật cảnh báo hoặc phát một bản bổ sung có liên kết.
5. Hết thời gian giữ trạng thái thì kết thúc cửa sổ; sự kiện quá muộn được xử lý bằng quy trình bổ sung đã định nghĩa.

Watermark là mốc hệ thống dùng để ước lượng rằng phần lớn sự kiện trước một thời điểm đã đến, không phải bảo đảm tuyệt đối không còn dữ liệu muộn. Cần lựa chọn giữa độ trễ phát hiện và độ đầy đủ của chuỗi.

Không trì hoãn mọi cảnh báo chờ tương quan hoàn tất. Vi phạm chính sách rõ ràng có thể được báo sớm, sau đó bổ sung bằng chứng. Cũng không phát hàng chục cảnh báo độc lập cho cùng một chuỗi nếu có thể cập nhật một vụ việc bằng khóa ổn định.

Khi audit bị gián đoạn giữa phiên, cần đánh dấu đoạn thiếu. “Không có sự kiện xuất dữ liệu trong khoảng đó” khác với “đã chứng minh không xuất dữ liệu”.

## 12. Thiết kế cảnh báo để người vận hành hành động được

Một cảnh báo tốt cần nêu hành vi, bối cảnh, bằng chứng và điều chưa biết. Ví dụ:

```yaml
alert_id: pam-ca-0042
title: Thay đổi quyền ngoài phạm vi phiên chỉ đọc
rule_id: PAM-CMD-SCOPE-01
rule_version: demo-1
session_id: pam-session-023
request_id: CHG-2048
actor_id: engineer-17
privileged_account: ops-admin
asset_id: db-prod-02
event_time: "2026-01-15T02:11:00Z"
observed_operation: identity.permission.change
observed_result: SUCCESS
approval_match: MISMATCH
risk_score: 75
telemetry_confidence: HIGH
reasons:
  - Phạm vi được cấp chỉ cho phép đọc trạng thái và log vận hành
  - Sự kiện nguồn ghi nhận thao tác thay đổi quyền
  - Tài sản được phân loại quan trọng
evidence:
  - event_id: evt-0104
    source_ref: endpoint-audit/host02-7781
unknowns:
  - Chưa xác định phạm vi ảnh hưởng của thay đổi
recommended_next_step: Đối chiếu audit thay đổi và xác minh với người quản lý phiên
```

Không đưa credential, token hoặc toàn bộ nội dung dữ liệu khách hàng vào cảnh báo. Có thể cung cấp liên kết có kiểm soát đến bằng chứng gốc đã được bảo vệ.

Cảnh báo nên chứa phiên bản quy tắc, baseline và snapshot phạm vi được dùng để đánh giá. Nhờ đó đội điều tra có thể giải thích vì sao một sự kiện bị gắn cờ ở thời điểm đó, kể cả khi chính sách hoặc lịch sử đã thay đổi.

## 13. Điều tra và phản ứng theo mức chứng cứ

### 13.1. Trình tự phân tích

Bắt đầu từ chất lượng dữ liệu, sau đó mới kết luận hành vi:

1. Kiểm tra định danh nguồn, thời gian, phạm vi thu thập và khả năng trùng.
2. Xác minh người yêu cầu, tài khoản thực thi và cách liên kết với phiên.
3. Đọc phê duyệt có hiệu lực tại thời điểm hành vi, kể cả thay đổi phạm vi hợp lệ.
4. Đối chiếu thao tác được yêu cầu với bằng chứng về kết quả.
5. Kiểm tra các sự kiện trước và sau trong cùng ngữ cảnh.
6. Xác định ảnh hưởng, quyết định phản ứng và lưu lý do xử lý.

Một command thất bại do thiếu quyền có thể chứng minh biện pháp least privilege đã ngăn tác động, nhưng vẫn đặt ra câu hỏi vì sao thao tác ngoài nhiệm vụ được thử. Không đóng cảnh báo chỉ vì mã thoát khác 0.

### 13.2. Phân cấp phản ứng

| Điều kiện đã xác minh | Phản ứng phù hợp có thể được cấu hình |
| --- | --- |
| Chỉ có độ hiếm, chưa có vi phạm rõ | Ghi nhận, bổ sung ngữ cảnh, chuyển điều tra |
| Hành vi nhạy cảm cần xác minh người thực hiện | Yêu cầu xác thực bổ sung tại điểm hỗ trợ hoặc phê duyệt tiếp |
| Vi phạm chính sách có bằng chứng đủ và quy trình cho phép | Hạn chế thao tác hoặc kết thúc phiên tại điểm cưỡng chế phù hợp |
| Có dấu hiệu credential bị lộ hoặc tài khoản bị chiếm dụng | Thực hiện quy trình thu hồi, luân chuyển credential và xử lý phiên/token liên quan |
| Telemetry mất hoặc không tin cậy | Cảnh báo sức khỏe giám sát; áp dụng chính sách duy trì truy cập đã được tổ chức phê duyệt |

Không đồng nhất kết thúc phiên PAM với dừng mọi tiến trình hoặc thu hồi mọi token trên hệ thống đích. Cũng không đồng nhất đổi mật khẩu với vô hiệu hóa toàn bộ phiên đã xác thực. Phải xác minh hiệu lực thực tế của từng biện pháp trên các hệ thống liên quan.

Đối với tài khoản dịch vụ, luân chuyển credential cần phối hợp với cơ chế phân phối secret và workload phụ thuộc để tránh sự cố vận hành. Với break-glass, đường phản ứng cần giữ khả năng khôi phục hệ thống theo quy trình đã được thiết kế.

Phản ứng tự động phải có chủ sở hữu, phạm vi, điều kiện kích hoạt và cách phục hồi. Điểm bất thường đơn lẻ không nên trở thành lý do mặc định để ngắt một tác vụ production quan trọng.

## 14. Giảm cảnh báo sai mà vẫn giữ khả năng phát hiện

### 14.1. Ngoại lệ có thời hạn và phạm vi cụ thể

Một ngoại lệ cho triển khai công cụ mới nên gắn với:

- Chủ thể hoặc workload cụ thể.
- Tài sản hoặc nhóm tài sản được phép.
- Loại hành vi và mục đích.
- Thời điểm bắt đầu, hết hạn.
- Người chịu trách nhiệm và yêu cầu thay đổi liên quan.

Tránh ngoại lệ kiểu “bỏ qua mọi command của tài khoản admin”. Một command hợp lệ trong một cửa sổ bảo trì không mặc nhiên hợp lệ trên mọi tài sản và trong tương lai.

Ngoại lệ có thể điều chỉnh cách tạo hoặc định tuyến cảnh báo nhưng không nên xóa bằng chứng nguồn. Các tín hiệu khác nằm ngoài phạm vi ngoại lệ vẫn cần được đánh giá.

### 14.2. Tách thay đổi môi trường với thay đổi hành vi nguy hiểm

Triển khai hệ điều hành, pipeline hoặc công cụ mới có thể làm fingerprint thay đổi hàng loạt. Cần đối chiếu với lịch phát hành và phân phối thay đổi theo nhóm tài sản.

Nếu chỉ một tài khoản xuất hiện hành vi mới trên máy quản lý danh tính ngoài thời gian triển khai, ngữ cảnh khác với hàng trăm máy nhận công cụ chuẩn qua pipeline đã phê duyệt.

### 14.3. Học từ kết quả điều tra

Gán nhãn đủ cụ thể, chẳng hạn:

- Vi phạm đã xác nhận.
- Hoạt động hợp lệ trong phạm vi được cấp.
- Phân loại command sai.
- Phê duyệt thiếu dữ liệu.
- Không đủ bằng chứng để kết luận.

Không gộp mọi cảnh báo được đóng thành “false positive”. Một cảnh báo có thể đúng về bất thường nhưng hoạt động cuối cùng được xác nhận hợp lệ; hoặc cảnh báo có cơ sở nhưng chưa đủ dữ liệu xác định tác động.

## 15. Bảo vệ dữ liệu command và bằng chứng

Command line có thể chứa mật khẩu, token, chuỗi kết nối, tên khách hàng hoặc dữ liệu nghiệp vụ. Chính hệ thống giám sát có thể trở thành nơi tập trung dữ liệu nhạy cảm nếu thu thập và hiển thị không có kiểm soát.

Nên thiết kế:

- Che dữ liệu nhạy cảm trước khi đưa vào chỉ mục tìm kiếm phổ thông hoặc thông báo.
- Phân quyền riêng cho bản ghi gốc, bản đã che và chức năng xuất bằng chứng.
- Ghi audit việc truy cập, giải mã hoặc tải bản ghi.
- Chính sách lưu giữ phù hợp từng lớp dữ liệu và mục đích điều tra.
- Mã hóa và kiểm soát toàn vẹn cho luồng thu thập và kho bằng chứng.
- Tách người vận hành tài sản với quyền sửa hoặc xóa bằng chứng của chính họ.

Không dùng hash đơn giản làm biện pháp ẩn danh tuyệt đối cho giá trị có không gian đoán nhỏ. Nếu cần liên kết ổn định mà hạn chế lộ dữ liệu, phải chọn cơ chế phù hợp và quản lý khóa, quyền truy cập cùng thời hạn lưu giữ.

Khi đưa command vào giao diện điều tra, coi nội dung là dữ liệu không tin cậy: mã hóa đầu ra phù hợp ngữ cảnh hiển thị, xử lý ký tự điều khiển và không để nút xem hoặc tìm kiếm vô tình thực thi command. Mẫu command trong cảnh báo cũng không nên biến thành một thao tác chạy trực tiếp.

## 16. Đánh giá hiệu quả phát hiện

Đo cả chất lượng phân tích lẫn sức khỏe thu thập.

| Nhóm chỉ số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Bao phủ | Tỷ lệ tài sản trọng yếu có nguồn audit hoạt động | Cho biết phạm vi thực sự quan sát được |
| Độ đầy đủ | Tỷ lệ sự kiện thiếu danh tính, phiên hoặc đối tượng | Cho biết khả năng giải thích hành vi |
| Độ trễ | Từ thời điểm sự kiện đến tạo cảnh báo, theo phân vị | Cho biết tốc độ phản ứng và ảnh hưởng của dữ liệu muộn |
| Chất lượng cảnh báo | Tỷ lệ cảnh báo đã điều tra có kết luận hữu ích | Cho biết mức tải điều tra có giá trị |
| Năng lực phát hiện | Tỷ lệ tình huống kiểm thử có tín hiệu mong đợi | Đánh giá trên tập có nhãn và phạm vi đã biết |
| Vận hành | Cảnh báo trên mỗi 100 phiên tương đồng, thời gian xử lý | Theo dõi tải và thay đổi theo quy mô sử dụng |

Nếu dùng precision, phải định nghĩa “dương tính thật” theo mục tiêu: vi phạm chính sách hay sự cố xâm nhập. Hai mục tiêu khác nhau có mẫu số và cách gán nhãn khác nhau.

Recall chỉ tính được khi có tập hành vi dương tính được biết trong phạm vi đánh giá. Không thể suy ra đầy đủ số sự cố bị bỏ sót chỉ từ danh sách cảnh báo sản xuất.

Khi đánh giá baseline, tách dữ liệu theo thời gian để tránh dùng thông tin tương lai dự đoán quá khứ. Chạy lại sự kiện phải dùng phiên bản chính sách, baseline và dữ liệu phê duyệt phù hợp; nếu dùng trạng thái hiện tại, kết quả không còn tái hiện đúng quyết định lịch sử.

Đánh giá riêng tài khoản con người, tài khoản dịch vụ, production và lab. Một con số tổng có thể che mất nhóm có nhiều cảnh báo sai hoặc nhiều khoảng trống.

## 17. Bài thực hành bằng dữ liệu mô phỏng

Không cần chạy command đặc quyền để thực hiện bài tập. Hãy tạo bảng sự kiện giả lập hoặc xử lý trong bộ nhớ.

### Bước 1 — Xác định bối cảnh

Chuẩn bị hai lớp tài sản, hai loại chủ thể và một yêu cầu chỉ đọc:

- `db-prod-02`: tài sản quan trọng.
- `app-lab-01`: tài sản thử nghiệm.
- `engineer-17`: tài khoản con người.
- `svc-backup`: workload chỉ được chạy tác vụ tự động.
- `CHG-2048`: chỉ đọc trạng thái và log trên `db-prod-02`, từ 02:00 đến trước 02:30 UTC.

### Bước 2 — Tạo tập sự kiện

Tập dữ liệu phải có ít nhất:

1. Một thao tác bình thường đúng phạm vi.
2. Một thao tác sửa quyền ngoài phạm vi.
3. Một thao tác mới nhưng được phê duyệt riêng đầy đủ.
4. Một lần thử thao tác nhạy cảm bị từ chối.
5. Một sự kiện parser chưa hỗ trợ.
6. Một bản ghi đến muộn.
7. Một bản gửi lại trùng định danh nguồn.
8. Một phiên tương tác của `svc-backup` trái chính sách kiểu phiên.

Mỗi sự kiện cần có dữ liệu đủ để biết kết luận nào được hỗ trợ và kết luận nào chưa thể đưa ra. Không điền giả `SUCCESS` cho sự kiện thiếu kết quả.

### Bước 3 — Thực hiện phát hiện

Đối chiếu phê duyệt theo từng chiều, tính độ hiếm chỉ khi baseline đủ mẫu và gom các sự kiện có liên kết thành cùng một vụ việc.

Cho bản ghi đến muộn bổ sung vào chuỗi đã tạo. Cho bản ghi trùng đi qua đường khử trùng mà không làm tăng số lần thực thi. Hai sự kiện có command giống nhau nhưng khác định danh thực thi vẫn phải được giữ là hai lần quan sát.

### Bước 4 — Kiểm tra kết quả

Đầu ra cần cho thấy:

- Sửa quyền ngoài phạm vi bị phát hiện dù thao tác không hiếm.
- Hành vi mới được cấp phép không bị tự động kết luận là vi phạm.
- Lần thử thất bại không bị mô tả thành thay đổi thành công.
- Parser không hỗ trợ làm xuất hiện vấn đề chất lượng dữ liệu.
- Thiếu phê duyệt không biến thành phê duyệt hợp lệ.
- Dữ liệu muộn có thể bổ sung vụ việc và vẫn truy nguyên được.
- Dữ liệu trùng không làm tăng giả tốc độ command hoặc điểm chuỗi.
- Vi phạm kiểu phiên của tài khoản dịch vụ có lý do riêng, không phụ thuộc tên command.

Sản phẩm bài tập gồm schema sự kiện, định nghĩa phạm vi, logic phát hiện, bảng kết quả mong đợi và một cảnh báo có bằng chứng tham chiếu. Không đưa secret thật hoặc bản ghi production vào dữ liệu học tập.

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa thiết kế |
| --- | --- | --- |
| Command hiếm luôn bị coi là độc hại | Cảnh báo dồn vào tác vụ mới hoặc nhân sự mới | Kết hợp phê duyệt, vai trò và nhóm tương đồng |
| Chỉ tìm tên công cụ đáng ngờ | Bỏ qua tham số và tài nguyên, nhiều cảnh báo sai | Phân tích ngữ nghĩa và hệ quả được quan sát |
| Tin mọi thao tác trong phiên đã phê duyệt | Bỏ qua việc vượt phạm vi sau khi vào phiên | Đối chiếu từng hành vi với quyền và mục đích |
| Dùng chuỗi con để xác định quyền được phép | Nhầm đối tượng, cú pháp hoặc mục đích | Dùng phạm vi có cấu trúc và parser phù hợp |
| Command xuất hiện trong recording nghĩa là đã thành công | Đánh giá sai tác động | Tách yêu cầu, thực thi và kết quả |
| Mất log được coi là không có bất thường | Tạo cảm giác an toàn giả | Theo dõi sức khỏe dữ liệu và đánh dấu khoảng trống |
| Học baseline từ mọi dữ liệu mới | Hành vi sai lặp lại trở thành bình thường | Quản lý cập nhật, nhãn điều tra và phiên bản baseline |
| Gộp chuỗi chỉ vì gần thời gian | Quy kết nhầm giữa nhiều công việc | Liên kết phiên, tiến trình, danh tính và tài sản |
| Điểm cao tự động ngắt mọi phiên | Có thể gây gián đoạn ngoài mong muốn | Định nghĩa phản ứng theo chứng cứ và điểm cưỡng chế |
| Đưa command nguyên bản vào thông báo rộng | Làm lộ secret hoặc dữ liệu nghiệp vụ | Che dữ liệu và kiểm soát truy cập bằng chứng |

## 19. Các điểm cần ghi nhớ

Phát hiện command bất thường trong PAM phải đặt thao tác vào bối cảnh danh tính, quyền hiệu lực, tài sản, mục đích và thời hạn được cấp. Độ hiếm giúp phát hiện điều đáng xem xét; chính sách xác định điều được phép; bằng chứng từ nền tảng đích giúp xác định điều thực sự xảy ra.

Một cơ chế hữu ích cần vừa phát hiện được vi phạm quen thuộc, vừa nhận ra hành vi mới, đồng thời thể hiện trung thực những gì telemetry chưa quan sát được. Cảnh báo phải giải thích được, truy nguyên được và hỗ trợ phản ứng phù hợp với mức chứng cứ.

Least privilege, JIT/JEA, vault và luân chuyển credential giúp giới hạn hoặc xử lý rủi ro. Command analytics bổ sung khả năng nhìn thấy cách quyền đặc biệt được sử dụng trong từng phiên, để tổ chức kiểm tra việc sử dụng đó và lưu bằng chứng phục vụ điều tra, kiểm toán.
