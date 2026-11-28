# Ngày tạo và ngày hết hạn trong inventory PAM

## 1. Vì sao hai mốc thời gian này quan trọng?

Trong inventory của hệ thống quản lý truy cập đặc quyền (PAM), **ngày tạo** giúp xác định nguồn gốc và tuổi của một đối tượng; **ngày hết hạn** giúp xác định thời điểm đối tượng hoặc một khả năng truy cập không còn được phép tiếp tục theo quy định.

Hai trường này hỗ trợ kiểm kê tài khoản quản trị, tài khoản dịch vụ, credential, grant JIT và phiên truy cập vào hạ tầng nhạy cảm. Chúng cũng giúp nhóm owner lập kế hoạch rà soát, gia hạn, rotation, thu hồi và lưu bằng chứng.

Tuy nhiên, một dòng inventory có ngày hết hạn không tự bảo đảm quyền ở tài nguyên đã bị chặn đúng thời điểm. Muốn quản lý được vòng đời, cần biết mốc thời gian thuộc đối tượng nào, đến từ nguồn nào và cơ chế thực thi tương ứng là gì.

Ví dụ:

~~~text
Tài khoản svc-pay-deploy:
  tạo tại nguồn danh tính: 2025-05-08
  được discovery lần đầu: 2026-11-26
  credential hiện tại phát hành: 2026-11-25
  grant của job hiện tại hết hạn: 2026-11-26 lúc 10:15 +07:00
~~~

Đây là bốn mốc khác nhau. Nếu thay ngày tạo tài khoản bằng ngày discovery, ta làm mất tuổi thật của tài khoản. Nếu lấy ngày hết hạn grant làm ngày hết hạn credential, ta có thể hiểu sai khả năng tiếp tục sử dụng credential ở những ngữ cảnh khác.

Mục tiêu học tập:

1. Ghi đúng ý nghĩa của từng trường thời gian trong inventory.
2. Phân biệt vòng đời tài khoản, credential, quyền và phiên.
3. Chuẩn hóa múi giờ, biên hết hạn và dữ liệu chưa xác định.
4. Tổ chức cảnh báo, gia hạn và xử lý hết hạn có chủ thể chịu trách nhiệm.
5. Chứng minh việc thu hồi bằng trạng thái thực thi và bằng chứng tại các hệ thống liên quan.

## 2. Ngày tạo của đối tượng nào?

### 2.1. Ngày tạo tài khoản

account_created_at là thời điểm tài khoản được tạo trong nguồn quản lý danh tính hoặc tài nguyên có thẩm quyền, nếu nguồn cung cấp thông tin đó.

Đổi tên tài khoản không nhất thiết tạo ra một tài khoản mới. Ngược lại, xóa rồi tạo lại tài khoản cùng tên có thể tạo một đối tượng khác với định danh và ngày tạo khác.

Vì vậy, luôn liên kết thời gian với định danh ổn định và nguồn:

~~~text
account_reference = authority_namespace + immutable_account_id
~~~

Nếu nguồn không có định danh bất biến, cần có cơ chế nhận diện thay thế và ghi giới hạn. Không gộp hai tài khoản chỉ dựa trên tên và cùng một giá trị ngày tạo.

### 2.2. Ngày tạo credential hoặc phiên bản credential

credential_issued_at hoặc credential_version_created_at mô tả một credential hoặc phiên bản cụ thể. Mốc này có thể thay đổi qua mỗi lần phát hành hoặc rotation, trong khi ngày tạo tài khoản vẫn giữ nguyên.

Ví dụ, tài khoản dịch vụ tồn tại hai năm có thể đang dùng credential phát hành hôm qua. Tuổi tài khoản không phản ánh tuổi credential hiện tại.

Cũng cần phân biệt thời điểm credential được phát hành với thời điểm một bản ghi secret được tạo trong vault. Import một credential cũ vào vault không làm credential đó trở thành mới.

### 2.3. Ngày phát hiện và ngày nhập inventory

| Trường | Ý nghĩa |
|---|---|
| first_discovered_at | Lần đầu hệ thống discovery quan sát đối tượng |
| inventory_record_created_at | Thời điểm bản ghi được tạo trong kho inventory |
| imported_at | Thời điểm dữ liệu được nhập từ một nguồn khác |
| last_observed_at | Lần gần nhất quan sát đối tượng trong một lần thu thập xác định |
| last_confirmed_at | Lần gần nhất thông tin được xác minh theo quy trình áp dụng |

Các mốc trên hữu ích cho chất lượng dữ liệu, nhưng không thay thế account_created_at.

Một lần quét thành công cũng chưa chắc xác nhận mọi thuộc tính. Nếu chỉ đọc được tên và trạng thái tài khoản, không nên cập nhật last_confirmed_at cho ngày hết hạn chưa được đọc hoặc xác minh.

### 2.4. Ngày bắt đầu trách nhiệm của owner

ownership_valid_from mô tả thời điểm một nhóm hoặc vai trò tiếp nhận trách nhiệm. Nó không phải ngày tạo tài khoản.

Khi bàn giao dịch vụ, tài khoản có thể giữ nguyên định danh và lịch sử, nhưng owner mới bắt đầu chịu trách nhiệm từ một thời điểm khác. Cần giữ lịch sử để biết ai chịu trách nhiệm khi một sự kiện xảy ra.

## 3. Ngày hết hạn của đối tượng nào?

### 3.1. Hết hạn tài khoản

account_expires_at là mốc kết thúc vòng đời sử dụng tài khoản theo nguồn hoặc chính sách được xác định.

Hành vi tại mốc đó phụ thuộc nền tảng và cơ chế thực thi: có thể ngăn xác thực mới, yêu cầu thay đổi trạng thái hoặc cần một tác vụ quản lý riêng. Không tự suy ra rằng mọi phiên đang mở đều kết thúc.

Một tài khoản cộng tác viên có thể có mốc kết thúc theo hợp đồng. Tài khoản dịch vụ lâu dài có thể không có ngày hết hạn tài khoản nhưng vẫn cần owner, rà soát và credential có vòng đời phù hợp.

### 3.2. Hết hạn credential

credential_expires_at là mốc một credential hoặc phiên bản không còn được chấp nhận theo cơ chế tương ứng.

Ví dụ có thể gồm token có thời hạn, chứng thư hoặc mật khẩu chịu quy tắc hiệu lực của nền tảng. Không phải mọi loại credential đều có cơ chế hết hạn tự động.

Nếu một khóa tĩnh không có thời hạn ở nguồn, ghi rõ thực tế đó. Có thể đặt ngày phải thay hoặc ngừng sử dụng theo chính sách, nhưng phải phân biệt đó là hạn quản trị với mốc nguồn tự thực thi.

### 3.3. Hết hạn quyền, điều kiện kích hoạt và phiên

| Mốc | Trả lời câu hỏi |
|---|---|
| eligibility_expires_at | Đến khi nào chủ thể còn đủ điều kiện kích hoạt quyền? |
| activation_window_ends_at | Đến khi nào một quyết định cho phép còn có thể được dùng để bắt đầu? |
| grant_expires_at | Phần quyền đã cấp còn có hiệu lực đến khi nào? |
| session_expires_at | Phiên phải kết thúc hoặc mất khả năng truy cập vào thời điểm nào theo thiết kế? |
| idle_timeout | Bao lâu không có hoạt động theo định nghĩa thì phiên bị xử lý? |

Một approval dùng được đến 11:00 không nhất thiết có nghĩa phiên được mở lúc 10:59 có thể chạy vô hạn. Chính sách phải xác định thời lượng phiên và cách kết hợp với cửa sổ kích hoạt.

Idle timeout không thay thế thời hạn tuyệt đối. Nếu chỉ dựa vào hoạt động, một phiên có lưu lượng liên tục có thể tồn tại quá nhu cầu đã được chấp thuận.

### 3.4. Ngày rà soát, ngày rotation và thời hạn lưu bằng chứng

Các mốc sau cũng cần quản lý nhưng không phải ngày hết hạn quyền:

- next_access_review_at: thời điểm phải rà soát lại nhu cầu quyền.
- rotation_due_at: hạn thực hiện rotation theo chính sách.
- ownership_review_due_at: hạn xác nhận lại trách nhiệm.
- evidence_retention_until: mốc lưu bằng chứng theo yêu cầu áp dụng.

Quá hạn rà soát không tự chứng minh tài khoản đã bị vô hiệu hóa. Đến hạn rotation không tự chứng minh credential cũ không còn dùng được. Hết hạn quyền cũng không đồng nghĩa phải xóa ngay log liên quan.

## 4. Một đối tượng có nhiều đồng hồ vòng đời

Có thể hình dung:

~~~mermaid
flowchart LR
    A["Tài khoản: ngày tạo và vòng đời"] --> C["Credential: phát hành, rotation, hết hạn"]
    A --> E["Điều kiện và quyết định cấp quyền"]
    E --> G["Grant: bắt đầu và hết hạn"]
    G --> S["Phiên hoặc job: bắt đầu và kết thúc"]
    A --> O["Ownership: thời điểm trách nhiệm"]
    C --> I["Inventory và bằng chứng"]
    G --> I
    S --> I
    O --> I
~~~

Các vòng đời liên quan nhưng không đồng nhất. Gia hạn tài khoản không tự gia hạn token. Rotation mật khẩu không nhất thiết làm mất hiệu lực một token đã phát hành. Đóng phiên không tự hoàn tác thay đổi đã được thực hiện.

Đối với một thao tác mới, hệ thống cần kiểm tra các giới hạn liên quan cùng lúc. Nếu một giới hạn bắt buộc đã hết, việc giới hạn khác còn hiệu lực không tự làm thao tác được phép.

Có thể mô tả ở mức khái niệm:

~~~text
Được thực hiện thao tác mới khi:
  danh tính phù hợp
  AND cơ chế xác thực được chấp nhận
  AND quyền và điều kiện áp dụng còn hiệu lực
  AND ngữ cảnh phiên hoặc job hợp lệ
  AND không có chính sách liên quan ngăn thao tác.
~~~

Đây không phải bộ đánh giá dùng chung cho mọi nền tảng. Cần ánh xạ các kiểm tra vào nơi thực thi thực tế và xác định những trạng thái được lưu lại trong phiên hoặc token.

## 5. Biểu diễn thời gian rõ ràng

### 5.1. Giữ múi giờ hoặc chuẩn hóa về UTC

Dữ liệu có thời điểm cụ thể nên kèm offset hoặc biểu diễn UTC. Ví dụ hai giá trị sau chỉ cùng một thời điểm:

~~~text
2026-11-26T17:00:00+07:00
2026-11-26T10:00:00Z
~~~

Có thể chuẩn hóa về UTC để so sánh, đồng thời giữ giá trị gốc và cách diễn giải để kiểm toán. Trên giao diện, hiển thị múi giờ rõ ràng để owner không nhầm giờ hết hạn.

Không so sánh chuỗi thời gian có offset khác nhau bằng thứ tự từ điển. Cần parse theo định dạng đã thống nhất rồi so sánh thời điểm.

### 5.2. Ngày không có giờ cần một quy tắc

Giá trị “hết hạn ngày 26/11/2026” chưa trả lời quyền hết lúc bắt đầu ngày đó hay sau khi ngày đó kết thúc, và theo múi giờ nào.

Nếu chính sách quy định “được dùng hết ngày 26 theo giờ +07:00”, có thể biểu diễn mốc kết thúc loại trừ:

~~~text
expires_at = 2026-11-27T00:00:00+07:00
           = 2026-11-26T17:00:00Z
~~~

Khi đó, quyền được dùng trước expires_at; tại đúng expires_at, thời hạn đã kết thúc.

Đây là một lựa chọn diễn giải phải được công bố và ánh xạ đúng nguồn. Không tự thêm giờ 23:59:59 hoặc đoán múi giờ cho một ngày nhập tay.

### 5.3. Dùng khoảng hiệu lực với biên rõ ràng

Một mô hình thường dễ xử lý là khoảng:

~~~text
[valid_from, expires_at)

Hợp lệ về thời gian khi:
  valid_from <= now AND now < expires_at
~~~

Biên đầu được bao gồm, biên cuối không được bao gồm. Quy tắc này giúp xác định chính xác hành vi ở mốc hết hạn, nhưng chỉ có tác dụng nếu được các điểm kiểm soát áp dụng nhất quán.

Không tự thêm khoảng gia hạn ngầm. Nếu cơ chế có dung sai thời gian, cần biết dung sai áp dụng cho kiểm tra nào, do thành phần nào quản lý và giới hạn ra sao.

### 5.4. Khoảng thời gian và ngày lịch khác nhau

“Mỗi 24 giờ” và “vào đầu ngày tiếp theo theo giờ địa phương” là hai quy tắc khác nhau. Với môi trường có thay đổi offset theo mùa, một ngày lịch cũng không phải lúc nào tương đương một khoảng thời lượng cố định.

Lưu rõ chính sách là khoảng thời lượng hay quy tắc lịch, múi giờ dùng để tính và thời điểm tính lại. Tránh trộn hai cách tính khi tạo hạn rotation hoặc gia hạn tài khoản.

### 5.5. Đồng hồ phải đáng tin cậy

Điểm quyết định quyền cần dùng nguồn thời gian được quản lý ở phía có thẩm quyền, không tin thời gian do client tùy ý gửi lên.

Đồng hồ lệch có thể làm quyền kết thúc sớm hoặc kéo dài hơn dự kiến. Cần theo dõi độ lệch, cách đồng bộ và hành vi khi không còn đủ tin cậy về thời gian.

Với đo thời lượng trong một tiến trình, cơ chế đo elapsed time phù hợp giúp tránh tác động của việc chỉnh đồng hồ hệ thống. Tuy nhiên, thời hạn tuyệt đối giữa nhiều hệ thống vẫn cần quy chiếu thời gian và đối soát; không thay toàn bộ timestamp kiểm toán bằng bộ đếm cục bộ.

## 6. Không có giá trị không đồng nghĩa với không hết hạn

### 6.1. Phân biệt các trạng thái

| Trạng thái | Ý nghĩa | Cách quản lý |
|---|---|---|
| finite | Có mốc hết hạn xác định | Lưu giá trị, nguồn và cơ chế thực thi |
| no_expiry_configured | Đã xác minh nguồn không cấu hình hết hạn cho đối tượng | Đánh giá có phù hợp chính sách và cần ngoại lệ hay không |
| unknown | Chưa biết vì thiếu hoặc lỗi dữ liệu | Theo dõi khoảng trống và xác minh lại |
| unsupported | Nguồn không cung cấp hoặc không hỗ trợ cơ chế cần thiết | Dùng kiểm soát bổ trợ và ghi giới hạn |
| not_applicable | Trường không có ý nghĩa với loại đối tượng đang xét | Ghi lý do thay vì để trống tùy tiện |

Đây là mô hình dữ liệu minh họa. Nếu hệ thống dùng giá trị khác, vẫn phải giữ được các ý nghĩa khác nhau.

Một tài khoản đã xác minh không có expiry ở nguồn có thể là thiết kế được chấp nhận, hoặc là vấn đề cần xử lý. Trạng thái kỹ thuật và quyết định chấp nhận rủi ro là hai thông tin riêng.

### 6.2. Không thay dữ liệu thiếu bằng một ngày giả

Không dùng các cách sau để làm trường dữ liệu “đủ”:

- Gán ngày tạo bằng ngày nhập inventory khi không đọc được nguồn.
- Gán ngày hết hạn rất xa để biểu diễn chưa biết.
- Gán ngày bắt đầu một epoch làm ngày tạo mặc định.
- Biến chuỗi rỗng thành “không bao giờ hết hạn”.
- Giữ ngày hết hạn cũ mà hiển thị như đã xác minh ở lần quét mới.

Nếu chưa biết ngày tạo, lưu giá trị chưa biết cùng lý do. Có thể vẫn dùng first_discovered_at cho hoạt động theo dõi, nhưng phải hiển thị đúng ý nghĩa.

### 6.3. Giá trị đặc biệt phải được giải mã theo nguồn

Một nguồn có thể dùng số, chuỗi hoặc giá trị đặc biệt để biểu diễn không hết hạn, chưa thiết lập hay trạng thái khác. Không áp dụng cách giải mã của nguồn này sang nguồn khác chỉ vì cùng kiểu dữ liệu.

Bộ chuyển đổi cần giữ giá trị gốc, quy tắc giải mã và kết quả chuẩn hóa. Nếu không nhận diện được giá trị, đánh dấu lỗi hoặc unknown thay vì chuyển thành một timestamp có vẻ hợp lệ.

## 7. Mô hình dữ liệu có nguồn gốc

### 7.1. Một timestamp cần đi kèm bằng chứng

| Thuộc tính | Vai trò |
|---|---|
| object_reference | Định danh đối tượng mà mốc thời gian thuộc về |
| field_semantics | Ngày tạo tài khoản, ngày hết credential hay hạn quản trị |
| normalized_value | Giá trị đã chuẩn hóa để xử lý |
| raw_source_value | Giá trị gốc cần bảo vệ phù hợp để đối chiếu |
| source_system | Nguồn có thẩm quyền hoặc nguồn suy ra |
| source_observed_at | Thời điểm đọc được thuộc tính |
| derivation | Cách tính nếu giá trị không đến trực tiếp từ nguồn |
| policy_reference | Phiên bản chính sách liên quan |
| verification_status | Mức độ đã xác minh và vấn đề còn thiếu |

Không phải hệ thống nào cũng cần lưu mọi trường trong cùng bản ghi. Có thể lưu bằng chứng qua tham chiếu, miễn tái hiện được cách tạo kết luận.

### 7.2. Ví dụ bản ghi tài khoản

Mẫu sau chỉ minh họa thiết kế inventory, không phải cấu hình có thể nạp trực tiếp vào sản phẩm:

~~~json
{
  "account_reference": {
    "source": "identity-prod",
    "object_id": "account-temp-42"
  },
  "account_created_at": {
    "value": "2026-11-20T02:00:00Z",
    "source_field": "source_account_creation_time",
    "observed_at": "2026-11-26T02:00:00Z",
    "verification_status": "verified"
  },
  "first_discovered_at": "2026-11-21T02:00:00Z",
  "inventory_record_created_at": "2026-11-21T02:01:00Z",
  "account_expiry": {
    "kind": "finite",
    "value": "2026-11-30T10:00:00Z",
    "authority": "identity-prod",
    "enforcement_mode": "source_control",
    "observed_at": "2026-11-26T02:00:00Z"
  },
  "ownership_reference": "owner-team-infrastructure",
  "next_access_review_at": "2026-11-28T02:00:00Z",
  "policy_reference": "temporary-privileged-account/revision-4"
}
~~~

Các thuộc tính credential và grant nên được lưu theo định danh riêng, không nhét mọi mốc vào account_expiry. Một tài khoản có thể có nhiều credential và nhiều grant đồng thời, mỗi đối tượng có thời hạn khác nhau.

enforcement_mode mô tả cơ chế dự kiến hoặc đã xác minh theo dữ liệu nguồn. Nó chưa chứng minh tài khoản đã bị chặn ở mốc tương lai; cần bằng chứng thực thi khi mốc đó đến.

### 7.3. Hạn được suy ra từ chính sách

Nếu nguồn không cung cấp sẵn một ngày hết hạn mà inventory tính từ quy tắc, phải giữ nguồn gốc:

~~~text
Giá trị suy ra:
  rotation_due_at = credential_last_changed_at + policy_interval

Cần giữ:
  credential_id hoặc version_id,
  mốc gốc được dùng,
  khoảng thời gian hoặc quy tắc lịch,
  policy_version,
  computed_at,
  giới hạn của dữ liệu nguồn.
~~~

Không dùng account_created_at thay credential_last_changed_at nếu hai mốc khác ý nghĩa. Nếu không biết mốc gốc, kết quả tính hạn cũng chưa đủ tin cậy.

Khi chính sách thay đổi, có thể cần tính lại hạn. Việc tính lại phải phân biệt thay đổi quy tắc với một lần rotation thực tế; không tạo ra sự kiện “credential đã được thay” chỉ vì ngày đến hạn vừa thay đổi.

## 8. Tổ chức xử lý trước và tại mốc hết hạn

### 8.1. Trước hạn: phân công và chuẩn bị

Với một mốc quan trọng, cần xác định:

- Owner xác nhận nhu cầu tồn tại và phạm vi quyền.
- Nhóm kỹ thuật thực hiện thay đổi tại tài nguyên hoặc nguồn danh tính.
- Nhóm vận hành credential xử lý phát hành, rotation hoặc thu hồi theo nhiệm vụ.
- Bên chịu trách nhiệm theo dõi kết quả và ngoại lệ.
- Consumer, job hoặc dịch vụ có thể bị ảnh hưởng.

Có thể đặt nhiều ngưỡng nhắc việc trước hạn, chẳng hạn 14 ngày, 7 ngày và 1 ngày trong một chính sách minh họa. Các số này không phải khuyến nghị bắt buộc; cần chọn theo thời gian xử lý thực tế và mức độ nhạy cảm.

Cảnh báo phải nêu đúng đối tượng và hành động cần làm. “Tài khoản sắp hết hạn” khác với “credential cần rotation” hoặc “grant của phiên sắp kết thúc”.

### 8.2. Gia hạn là thay đổi vòng đời

Một lần gia hạn cần có lý do, phạm vi, thời hạn mới, chủ thể có thẩm quyền và bằng chứng quyết định theo quy trình áp dụng.

Không tự gia hạn vô hạn chỉ vì tài khoản còn hoạt động hoặc chưa có ai phản hồi. Hoạt động chứng minh đang có sử dụng, không tự chứng minh quyền vẫn phù hợp.

Khi gia hạn:

1. Xác nhận đúng đối tượng và mốc đang thay đổi.
2. Đánh giá nhu cầu, owner và phạm vi quyền.
3. Xác định các giới hạn liên quan có cần thay đổi riêng không.
4. Áp dụng tại nguồn có thẩm quyền.
5. Đọc lại để xác nhận hạn mới đã được lưu.
6. Giữ lịch sử hạn cũ, hạn mới, lý do và quyết định.

Gia hạn tài khoản không được âm thầm thay thời hạn grant đang mở. Gia hạn grant cũng không tự phát hành credential mới, trừ khi cơ chế đã được thiết kế rõ ràng để thực hiện cả hai bước.

### 8.3. Tại mốc hết hạn: phân biệt thời gian và thực thi

Có thể theo dõi các lớp trạng thái:

~~~text
Time state:
  not_started / within_validity / expired / unknown

Enforcement state:
  not_required_yet / pending / requested / applied / failed / unknown

Verification state:
  not_verified / verified_for_declared_scope / incomplete
~~~

Ví dụ, time state là expired nhưng enforcement state là failed cho biết hạn đã qua mà cơ chế xử lý chưa thành công. Không gộp thành một nhãn “expired” rồi coi việc kiểm soát đã hoàn tất.

Nếu nền tảng tự thực thi hết hạn, vẫn cần biết cơ chế đó áp dụng tới đâu: đăng nhập mới, request mới, phiên đang mở hay các job đã chạy. Thu thập bằng chứng phù hợp với phạm vi đó.

### 8.4. Thu hồi quyền và dọn tác động

Khi thời hạn kết thúc, tùy đối tượng và thiết kế có thể cần:

- Chặn việc phát hành hoặc sử dụng grant mới.
- Ngăn xác thực hoặc request mới.
- Kết thúc hoặc giới hạn phiên liên quan.
- Thu hồi credential hoặc thay credential đã bị tiết lộ.
- Vô hiệu hóa tài khoản tạm theo cơ chế được hỗ trợ.
- Xử lý job, tiến trình con hoặc tài nguyên tạm.
- Xác nhận những đường quyền khác còn tồn tại.

Đóng phiên không tự xóa khóa mới được tạo trong phiên. Hết hạn tài khoản không tự hoàn tác cấu hình đã sửa. Việc dọn tác động bền vững cần được thiết kế và có chủ thể chịu trách nhiệm.

### 8.5. Khi thao tác đang chạy vượt qua deadline

Một truy vấn dài, bản sao lưu hoặc job triển khai có thể bắt đầu trước khi hết hạn và tiếp tục sau đó. Cần quy định rõ:

- Có chặn bắt đầu thao tác nếu thời gian còn lại không đủ không?
- Thao tác đang chạy sẽ bị hủy, hoàn tất có giới hạn hay chuyển sang cơ chế giám sát khác?
- Ai có quyền quyết định ngoại lệ?
- Bằng chứng nào xác nhận hành vi thực tế?

Không dùng việc ngắt kết nối như lời bảo đảm rằng tiến trình phía đích đã dừng. Với công việc cần hoàn tất an toàn, nên thiết kế quyền và vòng đời cho tác vụ đó từ đầu thay vì để phiên đặc quyền tồn tại không giới hạn.

## 9. Ví dụ xuyên suốt: tài khoản triển khai và grant theo job

### 9.1. Các mốc của tình huống

Giả sử tài khoản svc-pay-deploy có các dữ liệu:

| Đối tượng hoặc sự kiện | Thời điểm |
|---|---|
| Tài khoản được tạo tại nguồn | 2025-05-08T09:00:00+07:00 |
| Inventory phát hiện lần đầu | 2026-11-26T08:00:00+07:00 |
| Credential phiên bản cred-v17 phát hành | 2026-11-26T08:30:00+07:00 |
| cred-v17 hết hạn theo nguồn | 2026-11-26T11:00:00+07:00 |
| Grant gr-job-62 bắt đầu | 2026-11-26T10:00:00+07:00 |
| gr-job-62 hết hạn | 2026-11-26T10:15:00+07:00 |
| Job hoàn tất | 2026-11-26T10:08:00+07:00 |

Ngày tạo tài khoản là mốc năm 2025. Ngày discovery năm 2026 và lần phát hành cred-v17 không làm thay đổi mốc đó.

### 9.2. Mốc sớm hơn có ý nghĩa gì?

Trong thiết kế của ví dụ, mọi thao tác của job đều phải đi qua điểm kiểm soát grant. Grant kết thúc khi job hoàn tất hoặc đến deadline, tùy điều gì xảy ra trước.

Do đó, sau 10:08, job không được tiếp tục dùng gr-job-62, dù cred-v17 chưa đến mốc 11:00. Nếu điểm kiểm soát chỉ kiểm tra credential mà bỏ grant, quyền của job có thể tồn tại lâu hơn dự kiến.

Tuy nhiên, không vì vậy mà kết luận cred-v17 đã hết hạn hoặc đã bị thu hồi trên mọi đường khác. Phải xác định phạm vi sử dụng credential, các ràng buộc và việc nó có được tái sử dụng cho công việc khác hay không.

Nếu yêu cầu là credential chỉ phục vụ một job, có thể thiết kế credential riêng và vòng đời tương ứng. Nếu nền tảng không hỗ trợ ràng buộc đó, phải ghi rõ giới hạn và dùng kiểm soát bổ trợ phù hợp.

### 9.3. Dòng sự kiện mong đợi

~~~text
10:00  Xác thực workload, mở grant theo phạm vi công việc.
10:04  Thực hiện thao tác triển khai được phép.
10:08  Job hoàn tất; grant chuyển sang trạng thái không còn dùng được.
10:08+ Điểm thực thi chặn yêu cầu mới theo grant đã kết thúc.
10:09  Hệ thống xác nhận dọn quyền trong phạm vi đã thiết kế.
10:15  Thử dùng lại gr-job-62 vẫn bị từ chối.
11:00  cred-v17 đến mốc hết hạn riêng của credential.
~~~

Các thời điểm phản ánh ví dụ vận hành, không phải cam kết về độ trễ của một sản phẩm. Trong thực tế, cần đo độ trễ truyền trạng thái tới các điểm thực thi và xử lý khi vượt mục tiêu.

### 9.4. Nếu job cần thêm thời gian

Job chưa xong lúc 10:14 không tự tạo quyền gia hạn. Cần một quyết định phù hợp với quy trình, có thời hạn mới và bằng chứng.

Nếu không kịp gia hạn, hành vi của job tại 10:15 phải theo thiết kế đã thống nhất: dừng thao tác mới, hủy hoặc xử lý tác vụ đang chạy theo loại công việc. Không lặng lẽ bỏ kiểm tra hết hạn để tránh lỗi triển khai.

Sau gia hạn, hệ thống phải xác định grant nào còn hiệu lực và credential nào có đủ thời hạn. Một grant kéo dài qua 11:00 có thể cần credential khác hoặc cách xác thực phù hợp; không chỉ sửa một trường trong inventory.

## 10. Thu thập và đối soát dữ liệu thời gian

### 10.1. Nguồn nào có thẩm quyền?

| Thuộc tính | Nguồn cần đối chiếu |
|---|---|
| Ngày tạo và expiry tài khoản | Nguồn danh tính hoặc tài nguyên quản lý tài khoản |
| Thời hạn credential | Nguồn phát hành hoặc cơ chế xác thực liên quan |
| Hạn rotation theo chính sách | Chính sách và mốc gốc đã xác minh |
| Thời hạn grant | Hệ thống cấp và quản lý grant |
| Trạng thái phiên | Cổng truy cập, tài nguyên đích hoặc hệ thống quản lý phiên |
| Thời điểm bàn giao owner | Quyết định và bản ghi ownership có thẩm quyền |

Một nguồn có thể đáng tin cậy cho một thuộc tính nhưng không phải mọi thuộc tính. Trường nhập tay trong inventory không tự vượt qua trạng thái nguồn danh tính nếu chưa có quyết định rõ ràng.

### 10.2. Đối soát mà không làm mất lịch sử

Nếu inventory ghi hết hạn 30/11 nhưng nguồn ghi 28/11:

1. Xác định hai giá trị có nói về cùng đối tượng và cùng loại thời hạn không.
2. Kiểm tra múi giờ, biên ngày và cách chuyển đổi.
3. Đối chiếu quyết định thay đổi gần nhất.
4. Giữ cả giá trị quan sát và nguồn trong khi xử lý mâu thuẫn.
5. Xác nhận giá trị hiện hành theo thẩm quyền và cập nhật có lịch sử.

Không dùng quy tắc “giá trị nào muộn hơn thì chọn” để tránh gián đoạn. Cũng không dùng “giá trị nào mới đọc nhất thì đúng” nếu nguồn đó không có thẩm quyền cho thuộc tính đang xét.

### 10.3. Pseudocode chuẩn hóa một thuộc tính

~~~text
normalize_expiry(source_record, adapter_rules):
    raw = source_record.expiry_value
    meaning = adapter_rules.interpret(raw)

    if meaning == UNKNOWN_OR_INVALID:
        return {
            kind: UNKNOWN,
            raw_reference,
            reason,
            observed_at
        }

    if meaning == NO_EXPIRY_CONFIGURED:
        return {
            kind: NO_EXPIRY_CONFIGURED,
            source_reference,
            observed_at
        }

    parsed = parse_using_declared_format_and_timezone(raw)

    if parsed is ambiguous or missing_required_timezone:
        return unresolved_time_value(raw, reason)

    return {
        kind: FINITE,
        value_utc: parsed.instant_utc,
        original_representation: raw,
        source_reference,
        observed_at,
        conversion_rule_version
    }
~~~

Đoạn này là mô hình xử lý, không phải chương trình để chạy. Quy tắc adapter phải được xác định cho từng nguồn; dữ liệu không hợp lệ cần được giữ để xử lý, không chuyển thành một thời hạn giả.

## 11. Rủi ro vận hành và cách xử lý

### 11.1. Hạn trong inventory khác hạn tại nguồn

Nếu chỉ sửa inventory mà không cập nhật nguồn thực thi, hệ thống có thể hiển thị quyền đã hết trong khi tài nguyên vẫn chấp nhận truy cập.

Cần có tham chiếu tới cơ chế áp dụng, trạng thái tác vụ và kết quả đọc lại. Nếu không thể cập nhật nguồn, giữ rõ trạng thái chưa hoàn tất và biện pháp hạn chế tạm thời theo thiết kế.

Không ghi applied chỉ vì một yêu cầu đã được đưa vào hàng đợi. Requested, applied và verified là những mức bằng chứng khác nhau.

### 11.2. Token hoặc phiên giữ trạng thái cũ

Một số cơ chế kiểm tra hiệu lực ở thời điểm xác thực hoặc phát hành token. Thay đổi hạn tài khoản hoặc chính sách sau đó không tự bảo đảm mọi token, kết nối và tiến trình đang hoạt động nhận thay đổi ngay.

Cần xác định:

- Điểm nào đánh giá lại ở mỗi thao tác.
- Điểm nào dùng thông tin tự chứa hoặc cache.
- Cách thu hồi hoặc kết thúc trong phạm vi được hỗ trợ.
- Thời hạn tối đa trước khi trạng thái cũ không còn được chấp nhận.
- Biện pháp xử lý khi không đạt mục tiêu.

Không mô tả việc thu hồi là tức thời nếu còn độ trễ hoặc đường sử dụng chưa được kiểm soát.

### 11.3. Chứng thư hết hạn và kết nối đã mở

Hạn của chứng thư có thể được kiểm tra tại những thời điểm cụ thể của giao thức. Một kết nối đã xác thực trước đó không nhất thiết bị đóng chỉ vì chứng thư vừa đến mốc hết hạn.

Nếu yêu cầu nghiệp vụ là không còn thao tác sau deadline, phải có giới hạn phiên hoặc kiểm tra quyền phù hợp ngoài việc chỉ đặt thời hạn chứng thư. Hành vi cần được xác minh với các thành phần thực sự tham gia đường truy cập.

### 11.4. Nguồn hoặc hệ thống thực thi không sẵn sàng

Một tác vụ xử lý hết hạn có thể thất bại vì nguồn danh tính không sẵn sàng, lỗi mạng hoặc connector thiếu quyền. Hệ thống phải ghi thất bại, thử lại theo quy tắc và chuyển cấp khi cần.

Không tự kéo dài thời hạn để biến lỗi xử lý thành trạng thái hợp lệ. Nếu cần ngoại lệ có kiểm soát, ghi riêng quyết định, phạm vi và mốc kết thúc ngoại lệ.

Đối với quyền có rủi ro cao, cơ chế chặn tại chỗ với thời hạn đã biết có thể giúp giảm phụ thuộc vào tác vụ trung tâm. Tuy nhiên, mức bảo đảm còn tùy khả năng thực thi và mô hình vận hành thực tế.

### 11.5. Tài khoản lâu dài không có expiry tại nguồn

Không có expiry tài khoản không tự đồng nghĩa cấu hình sai trong mọi trường hợp. Một số danh tính dịch vụ có vòng đời gắn với dịch vụ lâu dài.

Cần kiểm soát bằng mục đích rõ ràng, owner, quyền tối thiểu, quản lý credential, rà soát và cơ chế kết thúc khi dịch vụ ngừng hoạt động. Nếu chính sách yêu cầu ngoại lệ, giữ tham chiếu quyết định và thời hạn rà soát ngoại lệ.

Một ngoại lệ về expiry tài khoản không tự miễn yêu cầu rotation, grant có hạn hoặc theo dõi phiên nếu các yêu cầu đó vẫn áp dụng.

### 11.6. Tài khoản cũ không chắc là tài khoản bỏ quên

Tuổi tài khoản lớn chỉ là tín hiệu cần xem xét. Một tài khoản lâu năm có thể phục vụ công việc ổn định; một tài khoản mới có thể đã có quyền quá rộng.

Kết hợp tuổi với owner, mục đích, quyền, trạng thái credential và bằng chứng sử dụng. Không có last_used_at hoặc không thấy hoạt động trong một nguồn log chưa đủ để kết luận tài khoản không còn sử dụng.

## 12. Bằng chứng phục vụ kiểm toán

Một chuỗi bằng chứng hữu ích có thể gồm:

~~~text
Định danh tài khoản và ngày tạo ở nguồn
  → quyết định về vòng đời hoặc thời hạn
  → credential/grant/phiên liên quan
  → cảnh báo và hành động trước hạn
  → quyết định gia hạn hoặc kết thúc
  → kết quả thực thi tại nguồn và tài nguyên
  → ngoại lệ hoặc phần chưa hoàn tất
~~~

Với mỗi thay đổi thời hạn, nên giữ:

| Nội dung | Mục đích |
|---|---|
| Giá trị cũ và mới | Biết deadline đã thay đổi thế nào |
| Đối tượng và loại thời hạn | Tránh lẫn tài khoản, credential và grant |
| Người hoặc workload thực hiện | Xác định chủ thể thao tác |
| Chủ thể quyết định theo thẩm quyền | Truy nguồn quyết định khi cần |
| Lý do và tham chiếu | Giải thích nhu cầu thay đổi |
| Thời điểm quyết định, áp dụng và quan sát | Phân biệt ý định và trạng thái thực tế |
| Kết quả đọc lại hoặc đánh giá | Chứng minh thay đổi đã tới đúng nơi |
| Phạm vi xác minh và giới hạn | Tránh khẳng định vượt bằng chứng |

Nếu dữ liệu được nhập muộn, giữ cả thời điểm sự kiện và thời điểm ghi nhận. Không sửa lịch sử để làm mất dấu khoảng thời gian quyền đã quá hạn.

Bằng chứng không cần chứa giá trị credential. Dùng định danh credential hoặc phiên bản, tham chiếu log và dấu vết được bảo vệ để liên kết.

Chính sách lưu bằng chứng cần được quản lý riêng. Tài khoản hoặc credential hết hạn không có nghĩa được xóa ngay những bản ghi cần cho điều tra và kiểm toán.

## 13. Chỉ số chất lượng và hiệu quả thực thi

| Chỉ số | Ý nghĩa |
|---|---|
| Tỷ lệ đối tượng có ngày tạo từ nguồn đã xác minh | Đo chất lượng nguồn gốc, không tính ngày import thay thế |
| Phân bố finite, no_expiry_configured, unknown và unsupported | Làm rõ tình trạng thời hạn thay vì gộp tất cả giá trị trống |
| Số đối tượng quá hạn nhưng thực thi chưa xác nhận | Theo dõi khoảng trống kiểm soát thực tế |
| Độ trễ từ deadline đến khi chặn trong phạm vi xác định | Đánh giá hiệu quả xử lý hết hạn |
| Số lần gia hạn và thời lượng gia hạn | Hỗ trợ phát hiện quyền tạm bị kéo dài thường xuyên |
| Số credential quá hạn rotation | Theo dõi công việc vòng đời credential riêng |
| Số lỗi múi giờ hoặc giá trị không parse được | Đánh giá chất lượng bộ chuyển đổi |
| Số quyết định đã áp dụng nhưng chưa đối soát | Phân biệt thao tác hoàn tất và bằng chứng hoàn tất |

Định nghĩa mẫu số, điểm bắt đầu và điểm kết thúc khi đo. Ví dụ, một API nhận yêu cầu thu hồi không đủ để tính rằng mọi tài nguyên đã ngừng chấp nhận quyền.

Không loại các nguồn không hỗ trợ expiry khỏi báo cáo mà không nêu rõ. Cũng không gộp “đã xác minh không cấu hình hạn” với “chưa biết” để tăng tỷ lệ hoàn tất.

Ưu tiên xử lý theo ảnh hưởng: tài khoản có quyền rộng, credential có thể xuất ra ngoài, hạ tầng nhạy cảm hoặc grant còn dùng được sau hạn thường cần được xem xét trước những vấn đề metadata ít tác động.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Ngày tạo bằng ngày discovery | Làm sai tuổi và nguồn gốc tài khoản | Tách mốc nguồn và mốc quan sát |
| Lấy tuổi tài khoản làm tuổi mật khẩu | Đánh giá sai vòng đời credential | Theo dõi credential hoặc phiên bản riêng |
| Không lưu múi giờ | Hết hạn sớm hoặc muộn ngoài dự kiến | Chuẩn hóa thời điểm và giữ cách diễn giải |
| Ngày cuối được hiểu khác nhau | Lỗi tại biên ngày | Công bố giờ cắt, múi giờ và biên loại trừ |
| Null được hiểu là không bao giờ hết hạn | Che giấu dữ liệu thiếu | Dùng trạng thái có kiểu và lý do |
| Gia hạn một lớp là coi mọi lớp đã gia hạn | Grant hoặc credential vẫn không phù hợp | Đối chiếu từng vòng đời liên quan |
| Hết hạn trong inventory là coi đã chặn | Quyền thực tế có thể còn dùng được | Theo dõi thực thi và xác minh tại điểm kiểm soát |
| Rotation là coi mọi token cũ mất hiệu lực | Bỏ sót đường truy cập còn tồn tại | Xác định cơ chế thu hồi theo loại credential |
| Lỗi truy cập là coi đã mất quyền | Kết luận sai do lỗi mạng hoặc dịch vụ | Dùng bằng chứng liên quan tới đánh giá quyền |
| Tự gia hạn để tránh lỗi vận hành | Quyền tạm trở thành thường trực | Giữ quyết định, lý do và mốc kết thúc rõ ràng |

## 15. Bài tập áp dụng

Một tài khoản hỗ trợ có dữ liệu:

~~~text
account_created_at:        2026-10-01T09:00:00+07:00
first_discovered_at:       2026-11-20T10:00:00+07:00
inventory_created_at:      2026-11-20T10:02:00+07:00

Nội dung yêu cầu:          dùng hết ngày 26/11/2026 theo giờ +07:00
Quy tắc đã thống nhất:     mốc kết thúc là đầu ngày kế tiếp, loại trừ

credential_expires_at:    2026-11-27T02:00:00+07:00
grant_expires_at:         2026-11-26T23:30:00+07:00
Phiên mở lúc:             2026-11-26T23:00:00+07:00
~~~

Hãy trả lời:

1. Ngày tạo tài khoản có phải ngày 20/11 không?
2. account_expires_at cần được chuẩn hóa thành thời điểm nào?
3. Tại 23:45 ngày 26/11, credential chưa hết hạn có đủ để tiếp tục dùng grant không?
4. Đến mốc hết hạn tài khoản, cần biết gì về phiên đang mở?
5. Nếu hệ thống không đọc được expiry của một credential khác, nên ghi trạng thái gì?
6. Nếu cần gia hạn tới sáng hôm sau, những lớp thời hạn nào phải được xem xét riêng?

Hướng phân tích:

- Ngày tạo tài khoản là mốc 01/10; 20/11 là mốc quan sát và tạo bản ghi.
- Theo quy tắc đã thống nhất, hạn tài khoản là 2026-11-27T00:00:00+07:00, tương đương 2026-11-26T17:00:00Z.
- Tại 23:45, grant đã hết hạn; credential còn hiệu lực không tự khôi phục grant.
- Cần xác định cơ chế xử lý phiên, request và thao tác đang chạy, cùng bằng chứng thực thi.
- Không đọc được dữ liệu nên biểu diễn unknown hoặc trạng thái lỗi cụ thể, không tự coi là không hết hạn.
- Gia hạn cần xét tài khoản, credential, grant, phiên và các điều kiện liên quan; thay đổi nào cũng cần đúng nguồn và phạm vi.

Có thể mở rộng bài tập bằng một tác vụ đang chạy qua mốc 23:30. Hãy mô tả cách xử lý an toàn, ai chịu trách nhiệm và bằng chứng nào xác nhận việc đó thay vì chỉ đóng cửa sổ truy cập.

## 16. Ghi nhớ

Ngày tạo cho biết nguồn gốc của một đối tượng; ngày hết hạn giới hạn một vòng đời cụ thể. Tài khoản, credential, grant, phiên và ownership có các mốc riêng, cần liên kết bằng định danh và bằng chứng.

Trong PAM, quản lý thời gian có ý nghĩa khi mốc được hiểu đúng, đến từ nguồn phù hợp và gắn với cơ chế thực thi. Một deadline đã qua chỉ là trạng thái thời gian; việc quyền đã bị chặn hoặc tác động đã được dọn cần được xác minh riêng.
