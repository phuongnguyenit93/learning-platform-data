# Failed approval pattern: nhận diện mẫu phê duyệt thất bại trong PAM

## 1. Mục tiêu và bối cảnh

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), một yêu cầu sử dụng tài khoản quản trị, mở phiên tới máy chủ nhạy cảm hoặc nhận quyền JIT thường phải đi qua chính sách và người phê duyệt. Một yêu cầu không được chấp thuận có thể là kết quả bình thường: người yêu cầu chọn sai tài nguyên, thiếu ticket thay đổi hoặc người duyệt xác định công việc chưa đủ điều kiện.

Tín hiệu cần giám sát xuất hiện khi các kết quả đó tạo thành một mẫu có ý nghĩa. Ví dụ: cùng một người liên tục xin quyền quản trị sau nhiều lần bị từ chối, chuyển sang nhiều tài khoản khác nhau, hoặc xin quyền có phạm vi rộng hơn rồi thực sự nhận được một grant. Ngược lại, hàng loạt yêu cầu hết hạn cùng lúc có thể phản ánh lỗi định tuyến phê duyệt và làm gián đoạn công việc hợp lệ.

**Failed approval pattern** trong bài này là mẫu bất thường liên quan đến những yêu cầu truy cập đặc quyền không hoàn tất phê duyệt như dự kiến. Đây là khái niệm phân tích vận hành; không giả định mọi sản phẩm PAM sử dụng cùng tên sự kiện hoặc cùng mô hình trạng thái.

Sau bài học, người học cần có khả năng:

- Phân loại đúng từ chối nghiệp vụ, chặn bởi chính sách, hết hạn, hủy và lỗi kỹ thuật.
- Xây dựng tín hiệu từ các yêu cầu khác nhau, tránh đếm trùng log hoặc lần đánh giá lại.
- Liên kết yêu cầu thất bại với yêu cầu kế tiếp, grant JIT, credential checkout và phiên truy cập.
- Chọn hành động xử lý phù hợp, giữ least privilege và lưu đủ bằng chứng điều tra.

Bài học nằm trong chương Monitoring của PAM. Đối tượng theo dõi gồm truy cập của quản trị viên và việc con người phê duyệt quyền cho tài khoản dịch vụ, ứng dụng hoặc hạ tầng nhạy cảm. Luồng cấp secret tự động không có bước phê duyệt con người chỉ được đưa vào khi có trạng thái chính sách tương đương và có cách giải thích rõ ràng.

## 2. Thất bại của phê duyệt không đồng nghĩa thất bại của bảo mật

Một lần từ chối có thể chứng minh cơ chế kiểm soát đang hoạt động. Lỗi bảo mật cần quan tâm là quyền vẫn được cấp trái điều kiện, việc từ chối bị vô hiệu hóa không đúng thẩm quyền, hoặc người yêu cầu tìm được đường cấp quyền khác mà không đáp ứng kiểm soát tương đương.

Ngược lại, nếu người dùng tuân thủ quy trình nhưng yêu cầu liên tục hết hạn do không có người duyệt, đây là vấn đề khả dụng của kiểm soát. Bỏ qua vấn đề đó có thể tạo áp lực sử dụng tài khoản chung hoặc break-glass cho công việc thường ngày.

Vì vậy, hoạt động giám sát cần trả lời hai nhóm câu hỏi:

1. Có người hoặc hệ thống đang tìm cách vượt quyết định từ chối hay mở rộng đặc quyền không?
2. Quy trình phê duyệt có đang làm thất bại những yêu cầu hợp lệ một cách bất thường không?

Không dùng một bộ đếm “approval failed” duy nhất để trả lời cả hai câu hỏi.

### 2.1. Phân loại kết quả trước khi xây rule

| Kết quả chuẩn hóa | Ý nghĩa cần xác minh | Hướng xử lý ban đầu |
| --- | --- | --- |
| `DENIED` | Người có thẩm quyền đưa ra quyết định từ chối | Xem lý do, phạm vi quyền và các lần xin lại |
| `POLICY_BLOCKED` | Chính sách chặn do thiếu điều kiện hoặc vi phạm ràng buộc | Kiểm tra policy, bằng chứng điều kiện và khả năng tìm đường khác |
| `EXPIRED` | Yêu cầu vượt hạn chờ mà không đạt quyết định cuối | Kiểm tra hàng đợi, người duyệt và thời hạn |
| `CANCELLED` | Yêu cầu được hủy bởi người dùng, hệ thống hoặc quy trình | Xác định tác nhân hủy; không mặc định là bị từ chối |
| `ERROR` | Xử lý phê duyệt gặp lỗi kỹ thuật | Điều tra tích hợp, quyền gọi API, định tuyến và dịch vụ phụ thuộc |
| `PENDING` | Chưa có kết quả cuối | Theo dõi tuổi yêu cầu; không đếm là một lần từ chối |
| `APPROVED` | Đạt điều kiện phê duyệt theo workflow | Tiếp tục kiểm tra việc cấp và sử dụng quyền |

Đây là bộ nhãn minh họa. Khi triển khai phải ánh xạ từ sự kiện thật của hệ thống và lưu nguyên kết quả gốc. Không ép một trạng thái chưa hiểu vào `DENIED`; sử dụng nhãn `UNKNOWN` và theo dõi chất lượng dữ liệu.

`APPROVED` không tự chứng minh một phiên đã được mở, cũng không chứng minh mọi điều kiện đã được thực thi đúng. Có hệ thống phê duyệt xong nhưng grant chưa được tạo; có hệ thống cấp quyền qua một kênh khác. Giám sát cần phân biệt quyết định phê duyệt, hiệu lực quyền và hành vi sử dụng.

### 2.2. Một quyết định thành phần chưa chắc là kết quả cuối

Một workflow có thể yêu cầu hai người duyệt, cho phép thay thế người duyệt, hoặc đánh giá chính sách nhiều lần. Một sự kiện `approver_declined` chưa chắc đồng nghĩa toàn bộ yêu cầu đã kết thúc nếu workflow vẫn cho phép người có thẩm quyền khác quyết định.

Ngược lại, việc “người khác đã duyệt” cũng không đủ để coi yêu cầu hợp lệ nếu workflow yêu cầu mọi bên cùng chấp thuận. Cần biết mô hình quyết định và phiên bản workflow tại thời điểm đó:

- Duyệt bởi bất kỳ một người đủ thẩm quyền.
- Duyệt tuần tự qua nhiều bước bắt buộc.
- Duyệt theo số người tối thiểu.
- Duyệt theo nhóm tài nguyên, điều kiện rủi ro hoặc phân tách nhiệm vụ.

Detector đếm thất bại ở cấp yêu cầu phải dựa vào kết quả cuối có thẩm quyền. Các quyết định thành phần được lưu riêng để phát hiện việc đổi tuyến, gây áp lực hoặc ghi đè quyết định.

## 3. Mô hình dữ liệu giúp giải thích được cảnh báo

Một cảnh báo hữu ích phải chỉ ra ai xin quyền gì, ở đâu, khi nào, bị xử lý ra sao và quyền có được sử dụng sau đó không. Chỉ có chuỗi thông báo “approval failed” không đủ để xác định mẫu.

### 3.1. Những định danh cần giữ riêng

| Trường | Mục đích |
| --- | --- |
| `tenant_id` | Ngăn trộn dữ liệu giữa các phạm vi tổ chức độc lập |
| `event_id` | Loại bản sao của cùng một sự kiện |
| `request_id` | Nhận diện một yêu cầu nghiệp vụ |
| `workflow_instance_id` | Phân biệt các lần chạy workflow khi nền tảng hỗ trợ |
| `request_revision` | Nhận diện thay đổi nội dung hoặc đánh giá lại yêu cầu |
| `requester_id` | Danh tính thực hiện thao tác gửi |
| `beneficiary_id` | Danh tính thực sự sẽ nhận quyền |
| `target_id` | Định danh tài nguyên đích ổn định |
| `target_account_id` | Tài khoản đặc quyền dự định sử dụng trên tài nguyên |
| `entitlement_id` | Quyền hoặc gói quyền được xin |
| `approver_id` | Người hoặc chủ thể ra quyết định |
| `policy_id`, `policy_version` | Chính sách có hiệu lực khi đánh giá |
| `ticket_id`, `change_id` | Liên hệ với công việc được phê chuẩn |
| `grant_id`, `session_id` | Liên hệ với hiệu lực và sử dụng quyền sau phê duyệt |

Đặc biệt cần tách người yêu cầu và người thụ hưởng. Một trưởng nhóm có thể xin quyền cho kỹ sư; một nền tảng triển khai có thể xin quyền cho service account. Nếu gom tất cả theo `requester_id`, một bot điều phối có thể trông như đang thử xin quyền hàng trăm lần dù phục vụ nhiều đối tượng độc lập.

Không dùng địa chỉ IP như danh tính duy nhất. Nhiều người có thể đi qua cùng VPN hoặc proxy; một người cũng có thể đổi IP. Tương tự, không suy ra hai tài khoản thuộc cùng người chỉ vì có tên hiển thị gần giống nhau. Liên kết danh tính phải đến từ nguồn danh bạ hoặc mapping đáng tin cậy, có hiệu lực theo thời gian.

### 3.2. Thời gian, lý do và ngữ cảnh

Mỗi sự kiện nên có `event_time` từ nguồn và `ingested_at` tại bộ thu thập. Cần ghi rõ múi giờ, chuẩn hóa thời gian khi phân tích, theo dõi sai lệch đồng hồ và độ trễ log.

Các trường ngữ cảnh thường hữu ích:

- Kết quả gốc, kết quả chuẩn hóa, mã lý do và trạng thái cuối hay thành phần.
- Quyền được xin, thời lượng, thời điểm bắt đầu và phạm vi tài nguyên.
- Mức quan trọng của tài nguyên, môi trường production hoặc non-production.
- Nguồn gửi yêu cầu, thiết bị đã xác minh, phương thức xác thực và trạng thái MFA nếu nguồn có.
- Tuyến duyệt, bước duyệt, thời hạn, người được phân công và người thực sự xử lý.
- Quyết định tự động hay thủ công; có override, escalation hoặc ngoại lệ được ghi nhận không.

Lý do tự do như “sửa lỗi gấp” hoặc “cùng ticket trước” là ngữ cảnh do người dùng khai báo, không phải bằng chứng thẩm quyền. Ưu tiên mã lý do có cấu trúc và đối chiếu ticket ở nguồn quản lý thay đổi khi điều tra.

Không đưa mật khẩu, token, private key, nội dung secret hoặc dữ liệu nghiệp vụ nhạy cảm vào log phê duyệt. Nếu cần lưu mô tả công việc, áp dụng giới hạn truy cập và che thông tin phù hợp.

### 3.3. Ví dụ bản ghi đã chuẩn hóa

Bản ghi sau dùng dữ liệu giả và schema minh họa:

```json
{
  "tenant_id": "org-training",
  "event_id": "evt-00041",
  "event_time": "2026-10-12T02:08:00Z",
  "ingested_at": "2026-10-12T02:08:04Z",
  "request_id": "req-0041",
  "workflow_instance_id": "wf-0041",
  "request_revision": 1,
  "requester_id": "user-017",
  "beneficiary_id": "user-017",
  "target_id": "db-prod-02",
  "target_account_id": "db-admin",
  "entitlement_id": "database-admin",
  "requested_duration_minutes": 60,
  "decision_scope": "REQUEST",
  "is_terminal": true,
  "source_outcome": "REJECTED",
  "normalized_outcome": "DENIED",
  "reason_code": "MISSING_APPROVED_CHANGE",
  "approver_id": "user-090",
  "policy_id": "prod-db-access",
  "policy_version": "v7",
  "ticket_id": "CHG-DEMO-104",
  "environment": "production"
}
```

Trong schema này, `is_terminal` và `decision_scope` là kết quả của bước ánh xạ đã được xác minh. Không tự gắn chúng chỉ vì một chuỗi chứa từ “reject”.

## 4. Các mẫu cần theo dõi

### 4.1. Xin lại nhiều lần sau quyết định từ chối

Cùng người thụ hưởng gửi nhiều yêu cầu khác nhau tới cùng tài nguyên và quyền, trong thời gian ngắn, với cùng lý do bị từ chối.

Giả thuyết cần kiểm tra là người đó tiếp tục thử mà chưa đáp ứng điều kiện. Tuy nhiên cũng có thể giao diện lỗi khiến người dùng gửi lại, hoặc hướng dẫn sửa thiếu ticket không rõ ràng.

Tín hiệu trở nên đáng chú ý hơn khi yêu cầu mới vẫn thiếu điều kiện như cũ, thời lượng xin quyền tăng, hoặc người dùng bỏ thông tin từng khiến yêu cầu bị từ chối. Việc họ sửa ticket và được duyệt đúng quy trình có thể là kết quả hợp lệ.

### 4.2. Đổi người duyệt hoặc tuyến duyệt sau khi bị từ chối

Sau một quyết định từ chối, yêu cầu được chuyển tới tuyến khác hoặc được tạo lại để một người khác xử lý.

Đổi người duyệt có thể hợp lệ khi người được phân công không còn trực, có xung đột lợi ích hoặc workflow hỗ trợ escalation. Cần đối chiếu quyền đổi tuyến và phiên bản chính sách, thay vì coi mọi thay đổi là hành vi né kiểm soát.

Điểm cần điều tra là việc chuyển tuyến có loại bỏ một bước bắt buộc không, người duyệt mới có đủ thẩm quyền không và quyết định từ chối trước đó có được hiển thị cho họ không.

### 4.3. Đổi tài khoản nhưng giữ nguyên mục tiêu

Một người bị từ chối trên tài khoản cá nhân, sau đó gửi yêu cầu cho tài khoản quản trị phụ hoặc một tài khoản khác có thể liên kết chắc chắn với cùng người thụ hưởng.

Mẫu này có thể phản ánh thay đổi hợp lệ trong phân vai. Cũng có thể người dùng đang tìm một policy ít chặt hơn. Detector nên giữ định danh tài khoản riêng và chỉ thêm mối liên hệ “cùng người” khi có mapping có căn cứ.

Đối với tài khoản dùng chung, việc quy trách nhiệm cần dựa vào danh tính đã xác thực tại PAM, thời điểm checkout và phiên liên quan; tên tài khoản đích không đủ để xác định con người phía sau.

### 4.4. Xin phạm vi rộng hơn hoặc đi đường cấp quyền khác

Một yêu cầu xin quyền hẹp bị từ chối; sau đó người dùng xin quyền quản trị rộng hơn, nhóm quyền khác hoặc quyền trên một máy trung gian có thể dẫn tới cùng tài nguyên nhạy cảm.

Không thể suy ra quan hệ bao hàm quyền chỉ bằng tên role. Muốn phát hiện mở rộng phạm vi, cần một danh mục quyền đã được kiểm chứng: quyền nào bao gồm thao tác nào, trên tài nguyên nào và trong môi trường nào.

Nếu chưa có danh mục đó, cảnh báo chỉ nên nêu “thay đổi entitlement cần đối chiếu”, không khẳng định đã xác định vượt quyền.

### 4.5. Nhiều yêu cầu bị chặn bởi cùng một điều kiện

Ví dụ nhiều yêu cầu production đều bị chặn vì thiếu xác thực tăng cường, ngoài giờ được phép hoặc không có ticket hợp lệ.

Phải phân biệt hai tình huống:

- Cùng một người liên tục không đáp ứng điều kiện: xem ý định, thiết bị, quyền và công việc cụ thể.
- Nhiều người ở nhiều nhóm cùng thất bại sau một thay đổi policy: ưu tiên kiểm tra triển khai chính sách, cấu hình tích hợp và thông báo tới người dùng.

Chính sách hoạt động đúng nhưng tài liệu hướng dẫn sai vẫn có thể tạo một mẫu thất bại diện rộng. Không tự giảm điều kiện bảo mật để làm sạch dashboard.

### 4.6. Hết hạn, lỗi hoặc không có người duyệt trên diện rộng

Mẫu này thường cần cảnh báo vận hành. Ví dụ hàng đợi phê duyệt tăng tuổi liên tục, một nhóm duyệt không còn người trực hoặc dịch vụ tích hợp không gửi được thông báo.

Các dấu hiệu hữu ích gồm tỷ lệ hết hạn theo tuyến duyệt, thời gian chờ, số người bị ảnh hưởng và sự trùng khớp với thay đổi cấu hình. Cần theo dõi cả yêu cầu đang chờ quá lâu; chỉ nhìn kết quả cuối có thể bỏ lỡ sự cố đang phát triển.

### 4.7. Được cấp quyền hoặc mở phiên sau chuỗi thất bại

Đây là mối tương quan quan trọng giữa kiểm soát và hiệu lực thực tế. Sau chuỗi bị từ chối, cần xem có grant, checkout hoặc phiên nào cho cùng người thụ hưởng và phạm vi tương ứng hay không.

Không phải mọi thành công sau thất bại đều là sự cố. Các khả năng gồm:

- Người dùng bổ sung đủ điều kiện và được duyệt lại hợp lệ.
- Một grant đã được phê duyệt trước chuỗi thất bại vẫn còn hiệu lực.
- Người dùng dùng kênh break-glass có cơ chế kiểm soát riêng.
- Một quy trình khác cấp quyền tương đương mà không có bằng chứng phê duyệt phù hợp.

Detector phải thể hiện mối liên hệ chắc chắn đến đâu. Có `request_id → grant_id → session_id` là bằng chứng tốt hơn việc ghép theo IP và khoảng thời gian gần nhau.

## 5. Từ sự kiện rời rạc thành tín hiệu có thể hành động

### 5.1. Khử trùng lặp ở hai cấp

**Cấp sự kiện:** cùng `tenant_id` và `event_id` được chuyển qua nhiều bộ thu thập chỉ được xử lý một lần. Nếu nguồn không cung cấp ID, có thể tạo khóa từ các trường ổn định đã được phân tích; cần ghi rõ nguy cơ gộp nhầm khi hai sự kiện thực sự giống nhau.

**Cấp yêu cầu:** một yêu cầu có thể sinh nhiều sự kiện như tạo mới, phân công, nhắc hạn, quyết định từng bước và kết thúc. Bộ đếm “số yêu cầu bị từ chối” phải tính số yêu cầu riêng biệt có kết quả cuối tương ứng, không tính số dòng log.

Khi một quyết định được sửa hoặc nguồn cho phép mở lại yêu cầu, mô hình phải giữ lịch sử và trạng thái hiện hành. Không giữ đồng thời cùng một yêu cầu trong cả nhóm từ chối và nhóm phê duyệt của cùng phép đo trạng thái cuối.

Nếu nghiệp vụ cho phép nhiều lần phê duyệt độc lập trong cùng `request_id`, cần khóa bổ sung như `workflow_instance_id` hoặc chu kỳ quyết định có ngữ nghĩa rõ. Không tự tạo “lần thử mới” từ mỗi revision để làm tăng bộ đếm.

### 5.2. Chọn khóa gom nhóm theo giả thuyết

Một rule theo dõi việc xin lại cùng quyền có thể dùng:

```text
tenant_id
+ beneficiary_id
+ target_id
+ entitlement_id
+ environment
```

Một rule theo dõi đổi tuyến duyệt phải giữ đủ nhiều tuyến trong cùng tập phân tích. Nếu đưa `approver_id` vào khóa gom nhóm chính, hành vi đổi người duyệt sẽ bị chia nhỏ và có thể không đạt ngưỡng.

Ngược lại, cảnh báo lỗi phê duyệt diện rộng thường gom theo `policy_id`, tuyến duyệt hoặc dịch vụ tích hợp, sau đó đếm số người và tài nguyên bị ảnh hưởng.

Mỗi khóa phải phục vụ một câu hỏi. Không có một khóa gom nhóm chung tối ưu cho mọi mẫu.

### 5.3. Cửa sổ thời gian và thứ tự

Cửa sổ ngắn giúp phát hiện một đợt xin lại dồn dập. Cửa sổ dài hơn giúp nhìn thấy việc thử lại thưa hoặc các lần chuyển tài khoản. Các cửa sổ phải được chọn theo tần suất công việc thực tế, độ nhạy tài nguyên và khối lượng dữ liệu.

Ưu tiên sắp xếp theo thời gian sự kiện có độ tin cậy đã biết. Log tới muộn cần làm cập nhật lại kết quả cửa sổ liên quan hoặc gắn nhãn phân tích chưa đầy đủ. Không diễn giải thứ tự ingest như thứ tự nghiệp vụ.

Nếu chưa xác định được độ lệch đồng hồ giữa PAM và hệ thống đích, một phiên có vẻ bắt đầu trước phê duyệt chưa đủ để kết luận truy cập trái phép. Ghi nhận nghi vấn về thứ tự, đối chiếu định danh và kiểm tra mốc hiệu lực quyền.

### 5.4. Ngưỡng minh họa

Một rule thử nghiệm có thể tạo ứng viên cảnh báo khi trong 30 phút:

- Có ít nhất 5 yêu cầu kết thúc khác nhau cho cùng người thụ hưởng, tài nguyên và quyền.
- Có ít nhất 3 yêu cầu kết thúc bằng `DENIED`.
- Tỷ lệ `DENIED` trên toàn bộ yêu cầu đã kết thúc trong cửa sổ đạt ít nhất 60%.

Các con số này chỉ giúp minh họa cách định nghĩa. Chúng không phải ngưỡng chuẩn cho môi trường production.

Với định nghĩa trên:

```text
D = số yêu cầu kết thúc bằng DENIED
T = số yêu cầu có kết quả cuối đã biết
denial_ratio = D / T, khi T > 0
```

`POLICY_BLOCKED` không tự nhập vào D. Nếu cần phát hiện chặn bởi chính sách, định nghĩa rule riêng hoặc đổi tên tử số và tập trạng thái một cách công khai. `PENDING` và `UNKNOWN` không thuộc T; cần theo dõi riêng để tránh làm đẹp tỷ lệ khi dữ liệu bị thiếu.

T có thể gồm `APPROVED`, `DENIED`, `POLICY_BLOCKED`, `EXPIRED`, `CANCELLED` và `ERROR` nếu tất cả đã được xác nhận là kết quả cuối. Vì tập này trộn nhiều nguyên nhân, luôn hiển thị cơ cấu kết quả cạnh tỷ lệ. Muốn đo riêng quyết định của con người, hãy dùng mẫu số khác và đặt tên chỉ số tương ứng.

### 5.5. Pseudocode cho một detector có trạng thái

```text
on_event(raw_event):
    e = normalize_using_validated_source_mapping(raw_event)

    if duplicate_event(e.tenant_id, e.event_id):
        return

    remember_event(e)
    update_request_history(e)

    if e.decision_scope != "REQUEST":
        retain_component_decision_for_investigation(e)
        return

    if not e.has_authoritative_order_or_revision:
        mark_request_order_uncertain(e.request_id)
        return

    previous, current = apply_authoritative_request_update(e)

    # Nếu trạng thái cuối thay đổi, bỏ đóng góp cũ trước khi thêm mới.
    # Một yêu cầu chỉ có một đóng góp trong phép đo trạng thái cuối.
    retract_previous_window_contribution(previous)
    add_current_terminal_contribution_if_known(current)

    key = (
        current.tenant_id,
        current.beneficiary_id,
        current.target_id,
        current.entitlement_id,
        current.environment
    )

    terminal_requests = distinct_terminal_requests(
        key=key,
        window="30 minutes",
        time_basis="terminal_decision_event_time"
    )

    D = count_outcome(terminal_requests, "DENIED")
    T = count(terminal_requests)

    if T >= 5 and D >= 3 and D / T >= 0.60:
        upsert_detection_episode(
            rule_id="repeated-denial-demo-v1",
            key=key,
            request_ids=ids(terminal_requests),
            outcomes=outcome_breakdown(terminal_requests),
            data_quality=quality_for(key)
        )
```

Pseudocode mô tả ý tưởng, không phải API sẵn có của một sản phẩm. Các hàm cập nhật cửa sổ cần hỗ trợ dữ liệu tới muộn, sửa trạng thái và lưu dấu vết thay đổi.

Ngoài cửa sổ 30 phút, có thể lưu lịch sử dài hơn phục vụ điều tra. Không kéo mọi sự kiện cũ vào cửa sổ hiện tại chỉ vì log vừa được ingest.

### 5.6. Hợp nhất cảnh báo theo đợt

Một chuỗi 20 yêu cầu không nhất thiết cần 20 ticket. Hệ thống có thể cập nhật một episode đang mở, bổ sung yêu cầu mới, kết quả mới và mức độ nghiêm trọng mới.

Khóa hợp nhất nên có rule, phiên bản rule, tenant và khóa thực thể phù hợp. Cần quy định khoảng yên lặng để đóng một đợt và điều kiện mở lại. Việc hợp nhất không được loại bỏ bằng chứng của từng yêu cầu.

Nếu xuất hiện grant không giải thích được hoặc truy cập tới tài nguyên quan trọng hơn, episode phải được nâng cấp và thông báo lại theo cơ chế ứng phó. Thời gian tạm ngưng thông báo không nên che mất một diễn biến mới có ý nghĩa.

## 6. Tương quan với quyền được cấp và phiên sử dụng

Chuỗi nghiệp vụ cần đối chiếu có dạng:

```text
Yêu cầu truy cập
    → quyết định phê duyệt / chính sách
    → grant JIT hoặc quyền có hiệu lực
    → checkout credential hoặc mở phiên
    → kết thúc phiên, hết hạn hoặc thu hồi quyền
```

Không phải luồng nào cũng có đủ mọi bước. Có tài khoản được cấp quyền bằng thay đổi nhóm, có quyền được dùng qua proxy không lộ credential, và có hệ thống đích tự ghi phiên. Cần mô tả nguồn nào chứng minh mỗi bước.

### 6.1. Các câu hỏi khi thấy thành công sau thất bại

1. Grant được tạo từ yêu cầu nào, cho ai, trên tài nguyên nào?
2. Quyết định phê duyệt có trước thời điểm hiệu lực quyền không, sau khi xét sai lệch đồng hồ?
3. Phạm vi quyền và thời lượng có khớp nội dung được phê duyệt không?
4. Các điều kiện từng bị thiếu đã được đáp ứng hay chỉ bị bỏ qua?
5. Phiên thực tế có sử dụng đúng tài khoản và giới hạn đã được cấp không?
6. Quyền đã hết hạn hoặc được thu hồi đúng lúc chưa?

Nếu không có ID nối trực tiếp, có thể tương quan theo người thụ hưởng, tài nguyên, tài khoản, quyền và thời gian. Kết quả này cần ghi là quan hệ suy đoán, kèm độ tin cậy và các trường chưa khớp.

### 6.2. Quyền tồn tại trước đó

Một yêu cầu mới bị từ chối không nhất thiết thu hồi grant đã được cấp hợp lệ trước đó. Không suy ra “phiên sau từ chối” là bypass nếu phiên dùng grant cũ vẫn còn hiệu lực và đúng phạm vi.

Tuy nhiên, có chính sách quy định quyết định từ chối mới phải dẫn tới rà soát hoặc thu hồi quyền hiện hành. Khi đó cần kiểm tra cơ chế enforcement cụ thể, không suy đoán từ tên trạng thái.

### 6.3. Break-glass và thay đổi khẩn cấp

Một lần sử dụng break-glass sau chuỗi thất bại là mối liên hệ cần xem xét. Cần tìm bằng chứng về tình huống khẩn cấp, người kích hoạt, phạm vi, thời hạn, phiên giám sát, việc quay vòng credential và hậu kiểm theo quy trình tổ chức.

Không tự thêm break-glass vào danh sách bỏ qua mọi cảnh báo. Cũng không coi mọi lần dùng là hành vi sai. Mục tiêu là xác định kênh khẩn cấp có được dùng đúng điều kiện và có tạo quyền tồn dư hay không.

## 7. Ví dụ phân tích một chuỗi sự kiện

Giả sử các yêu cầu sau đều thuộc cùng người thụ hưởng `user-017`, tài nguyên `db-prod-02` và entitlement `database-admin`. Thời gian trong bảng là thời gian sự kiện đã chuẩn hóa, hiển thị theo cùng một múi giờ.

| Thời điểm | Yêu cầu | Kết quả cuối | Ngữ cảnh |
| --- | --- | --- | --- |
| 09:00 | R101 | DENIED | Thiếu thay đổi đã được duyệt |
| 09:04 | R102 | DENIED | Cùng điều kiện còn thiếu |
| 09:07 | R103 | DENIED | Cùng điều kiện còn thiếu |
| 09:09 | R104 | CANCELLED | Người dùng tự hủy |
| 09:12 | R105 | APPROVED | Đính kèm thay đổi đã được xác minh |

Bộ thu thập nhận thêm hai bản sao của sự kiện R102. Hai bản sao không tạo yêu cầu mới và không làm thay đổi kết quả.

Trong cửa sổ này, D = 3, T = 5 và tỷ lệ từ chối = 60%. Rule minh họa tạo một ứng viên cảnh báo. R104 không được cộng vào D dù đã kết thúc không có phê duyệt.

Bước tiếp theo là xem R105 có thực sự bổ sung điều kiện hay không:

- Nếu người duyệt xác minh đúng thay đổi, grant và phiên khớp phạm vi, cảnh báo có thể được kết luận là xin lại sau khi hoàn thiện hồ sơ. Vẫn xem có cần cải thiện hướng dẫn để giảm lặp.
- Nếu R105 chỉ đổi tuyến duyệt và bỏ điều kiện bắt buộc, cần điều tra khả năng né kiểm soát.
- Nếu có phiên 09:13 nhưng không tìm thấy grant hoặc ID yêu cầu, chưa được tự gắn phiên đó vào R105. Phải kiểm tra kênh cấp quyền và mapping log.
- Nếu R105 được approve nhưng grant chỉ có hiệu lực từ 10:00, một phiên 09:13 có thể dùng quyền khác. Mốc approve không thay cho mốc hiệu lực.

Bây giờ giả sử nhiều người dùng ở nhiều nhóm đồng thời có kết quả `EXPIRED`, trong khi không xuất hiện `DENIED` bất thường. Không nên dùng rule từ chối lặp để mô tả sự cố này. Hướng kiểm tra phù hợp là tuổi hàng đợi, lịch trực, định tuyến và sức khỏe tích hợp.

## 8. Phân mức độ và xử lý cảnh báo

Mức độ phụ thuộc vào tác động tiềm năng, độ tin cậy của liên kết và bằng chứng quyền đã được cấp. Số lần thất bại chỉ là một thành phần.

| Tình huống quan sát | Đánh giá khởi đầu | Hành động phù hợp |
| --- | --- | --- |
| Một lần bị từ chối vì thiếu ticket | Thường là sự kiện nghiệp vụ | Ghi nhận; hướng dẫn sửa yêu cầu nếu cần |
| Nhiều yêu cầu bị từ chối, chưa thấy cấp quyền | Có dấu hiệu cần xác minh | Liên hệ người phụ trách, xem lý do và công việc |
| Đổi tuyến hoặc tài khoản sau từ chối | Cần đối chiếu thẩm quyền | Kiểm tra workflow, danh tính và lịch sử thay đổi |
| Được cấp quyền nhạy cảm sau chuỗi thất bại nhưng thiếu bằng chứng phù hợp | Ưu tiên điều tra an ninh | Xác minh grant, phiên và khả năng hạn chế đúng phạm vi |
| Hàng loạt hết hạn hoặc lỗi cùng tuyến | Ưu tiên vận hành theo tác động | Khôi phục định tuyến hoặc tích hợp, bảo toàn điều kiện kiểm soát |

Đây là gợi ý phân loại ban đầu, không thay thế mô hình mức độ sự cố của tổ chức.

### 8.1. Runbook điều tra

**Bước 1 — Xác nhận dữ liệu.** Kiểm tra tenant, mapping trạng thái, số yêu cầu riêng biệt, log trùng, log muộn và độ lệch thời gian. Xác nhận cảnh báo dùng kết quả cuối hay quyết định thành phần.

**Bước 2 — Xác nhận công việc.** Đối chiếu người thụ hưởng, tài nguyên, quyền, ticket và thời lượng. Xem có bảo trì, sự cố, đổi ca hoặc triển khai policy gần thời điểm đó không.

**Bước 3 — Dựng lại diễn biến.** Đặt yêu cầu, revision, lý do, người duyệt, chuyển tuyến, override và thay đổi policy trên cùng timeline. Phân biệt dữ liệu từ nguồn với suy luận của người điều tra.

**Bước 4 — Kiểm tra quyền thực tế.** Tìm grant đang hiệu lực, nhóm quyền được thêm, credential checkout, phiên đang mở và kết quả thu hồi. Kiểm tra tài khoản hoặc kênh khác chỉ trong phạm vi điều tra được phép.

**Bước 5 — Chọn hành động.** Nếu có bằng chứng cấp quyền sai, thực hiện hạn chế theo runbook và thẩm quyền: dừng một phiên cụ thể, thu hồi một grant hoặc yêu cầu xác minh bổ sung. Đánh giá tác động trước khi ảnh hưởng tài khoản dịch vụ hoặc hệ thống production.

**Bước 6 — Lưu kết luận và cải tiến.** Ghi nguyên nhân, bằng chứng, hành động, quyền tồn dư và người chịu trách nhiệm. Nếu là lỗi quy trình, mở việc sửa định tuyến hoặc hướng dẫn. Nếu là vấn đề an ninh, giữ chuỗi bằng chứng và liên kết hồ sơ sự cố.

Không tự động khóa toàn bộ tài khoản chỉ vì đạt ngưỡng số lần từ chối. Một detector có thể bị kích hoạt bởi retry hợp lệ, thay đổi policy lỗi hoặc hành vi cố tình tạo yêu cầu thay cho người khác.

### 8.2. Khi có thể tự động hóa

Tự động hóa ít tác động như gom sự kiện, truy vấn grant, bổ sung thông tin tài nguyên và mở ticket thường dễ triển khai trước. Việc dừng phiên hoặc thu hồi quyền cần ràng buộc mạnh hơn về độ tin cậy, phạm vi, thẩm quyền và khả năng phục hồi.

Nếu áp dụng giảm tốc độ gửi yêu cầu hoặc yêu cầu xác minh tăng cường, phải thiết kế để không tạo đường từ chối dịch vụ cho người thụ hưởng khi người khác có quyền gửi thay. Cơ chế bảo vệ phải gắn đúng tác nhân và đúng luồng nghiệp vụ.

## 9. Giảm cảnh báo nhầm và tránh bỏ sót

### 9.1. Những nguồn nhiễu thường gặp

| Nguồn nhiễu | Cách kiểm tra hoặc giảm nhiễu |
| --- | --- |
| Gửi lại cùng sự kiện từ nhiều connector | Khử trùng theo định danh nguồn và sự kiện |
| Một yêu cầu có nhiều bước hoặc revision | Tách lịch sử khỏi bộ đếm kết quả cuối |
| Người dùng sửa hồ sơ nhiều lần | So sánh điều kiện bị thiếu và nội dung đã được bổ sung |
| Bot xin quyền thay cho nhiều người | Phân biệt requester, beneficiary và danh tính workload |
| Người duyệt đổi ca | Đối chiếu lịch trực và quyền chuyển tuyến |
| Policy mới gây chặn diện rộng | Phân tích theo phiên bản và thời điểm triển khai |
| Tài nguyên được đổi tên | Dùng định danh ổn định và mapping có thời hạn |
| Log tới muộn hoặc thiếu | Hiển thị độ trễ, độ phủ và mức tin cậy dữ liệu |

Không miễn trừ vĩnh viễn một tài khoản chỉ vì nó hoạt động nhiều. Nếu cần ngoại lệ, giới hạn theo danh tính, tài nguyên, quyền, lý do và thời gian; chỉ định chủ sở hữu và ngày rà soát.

Ngoại lệ có thể thay đổi kênh thông báo hoặc mức ưu tiên nhưng vẫn phải giữ bằng chứng. Các dấu hiệu mới như cấp quyền vượt phạm vi không nên bị che bởi ngoại lệ dành cho tần suất yêu cầu.

### 9.2. Những khoảng trống dễ gây bỏ sót

Một rule chỉ đếm từ chối trong 30 phút có thể không phát hiện yêu cầu thưa trong nhiều ngày. Một rule chỉ nhìn cùng entitlement có thể bỏ lỡ việc chuyển sang role khác. Một rule chỉ thu log PAM không thấy quyền được cấp trực tiếp ở hệ thống đích.

Biện pháp bổ sung gồm theo dõi nhiều cửa sổ thời gian, đối chiếu lịch sử danh tính có căn cứ, kiểm kê quan hệ quyền và thu nhận sự kiện cấp quyền ngoài PAM. Mỗi nguồn bổ sung cần xác định độ phủ và giới hạn thay vì coi như đã bao quát mọi đường truy cập.

Cũng cần phát hiện chính detector bị mất đầu vào. Không có cảnh báo trong một ngày mất log không phải bằng chứng quy trình phê duyệt hoạt động tốt.

## 10. Chỉ số vận hành và bằng chứng

### 10.1. Chỉ số nên quan sát cùng nhau

- Số yêu cầu riêng biệt theo kết quả cuối, tuyến duyệt, policy và mức quan trọng tài nguyên.
- Tỷ lệ từ chối theo định nghĩa mẫu số đã công bố.
- Tỷ lệ hết hạn và tỷ lệ lỗi kỹ thuật, tách khỏi từ chối nghiệp vụ.
- Số yêu cầu đang chờ quá mục tiêu thời gian xử lý và phân bố tuổi hàng đợi.
- Số episode có grant hoặc phiên tiếp theo, phân biệt liên kết trực tiếp và suy đoán.
- Thời gian xác minh cảnh báo, số cảnh báo nhầm và nguyên nhân gây nhiễu.
- Độ trễ log, số trạng thái chưa ánh xạ và tỷ lệ thiếu định danh cần tương quan.

Với chỉ số dùng một tập yêu cầu được tạo trong một giai đoạn, cần chờ đủ thời gian để biết kết quả hoặc hiển thị số yêu cầu chưa kết thúc. Không so sánh một nhóm đã quan sát đủ với một nhóm mới tạo còn nhiều yêu cầu pending rồi kết luận chất lượng phê duyệt khác nhau.

Tỷ lệ có mẫu số nhỏ nên hiển thị cả số tuyệt đối. Một yêu cầu bị từ chối trên tổng một yêu cầu cho tỷ lệ 100% nhưng ý nghĩa khác hẳn 200 yêu cầu bị từ chối trên tổng 200 yêu cầu.

### 10.2. Hồ sơ tối thiểu của một episode

Một hồ sơ nên giữ:

1. Rule, phiên bản, ngưỡng và cửa sổ đã tạo cảnh báo.
2. Danh tính, tenant, tài nguyên, entitlement và mức quan trọng tại thời điểm phát hiện.
3. Danh sách request ID và event ID tham chiếu; kết quả gốc lẫn chuẩn hóa.
4. Lịch sử người duyệt, tuyến duyệt, lý do và phiên bản policy liên quan.
5. Grant, checkout, phiên, thời điểm hiệu lực và kết quả thu hồi nếu có.
6. Độ trễ, dữ liệu thiếu, độ tin cậy của mapping và các liên kết suy đoán.
7. Người xử lý, kết luận, hành động và căn cứ của mọi ngoại lệ.

Tham chiếu tới log gốc phải có khả năng truy xuất trong thời hạn lưu giữ phù hợp. Giới hạn quyền đọc hồ sơ vì nó có thể tiết lộ danh sách tài khoản đặc quyền, tài nguyên quan trọng và lịch hoạt động quản trị. Không nhúng secret vào bằng chứng.

## 11. Bài thực hành bằng dữ liệu giả

Thực hành trên tập sự kiện mô phỏng hoặc môi trường lab; không tạo yêu cầu hàng loạt trên production để thử detector.

### 11.1. Tập tình huống

| Tình huống | Dữ liệu mô phỏng | Kết quả mong đợi |
| --- | --- | --- |
| A | 1 yêu cầu bị từ chối, cùng sự kiện được gửi 10 lần | 1 yêu cầu; không đạt ngưỡng lặp |
| B | 5 yêu cầu cuối gồm 3 DENIED, 1 CANCELLED, 1 APPROVED trong 30 phút | Tạo ứng viên của rule minh họa với D=3, T=5 |
| C | 1 yêu cầu có 3 quyết định thành phần, sau đó kết thúc APPROVED | Không đếm thành 3 yêu cầu bị từ chối |
| D | Nhiều người có yêu cầu EXPIRED sau thay đổi định tuyến | Cảnh báo vận hành; không cộng vào D |
| E | Chuỗi DENIED rồi grant từ yêu cầu đã sửa đủ điều kiện | Phát hiện tương quan và xác minh khả năng hợp lệ |
| F | Chuỗi DENIED rồi phiên qua kênh không có mapping grant | Cần điều tra; không tự khẳng định quan hệ trực tiếp |
| G | 5 DENIED đến muộn nhưng thời gian sự kiện nằm ngoài cửa sổ hiện tại | Cập nhật cửa sổ lịch sử theo thiết kế; không dồn vào hiện tại |
| H | Quyết định DENIED được sửa thành APPROVED trong cùng chu kỳ có phiên bản rõ | Rút đóng góp cũ, giữ một kết quả cuối và bảo toàn lịch sử |

Với tình huống H, detector có thể từng tạo một cảnh báo đúng theo dữ liệu biết lúc đó. Khi nhận bản sửa, cần cập nhật hoặc đánh dấu cảnh báo đã được điều chỉnh; không xóa âm thầm lịch sử điều tra.

### 11.2. Các bước thực hiện

1. Chuẩn hóa các trạng thái nguồn theo bảng mapping đã định nghĩa.
2. Tách sự kiện thành phần và kết quả cuối ở cấp yêu cầu.
3. Khử trùng sự kiện rồi dựng trạng thái yêu cầu có xét revision.
4. Tính D, T, cơ cấu kết quả và độ đầy đủ dữ liệu cho từng cửa sổ.
5. Tạo một episode thay vì thông báo lặp cho mỗi sự kiện bổ sung.
6. Bổ sung dữ liệu grant và phiên, ghi độ tin cậy của mối liên hệ.
7. Viết kết luận cho từng tình huống: vấn đề an ninh, vấn đề vận hành, hành vi hợp lệ hoặc chưa đủ bằng chứng.

Bản thực hành đạt yêu cầu khi kết quả không thay đổi chỉ vì log được gửi lại, một yêu cầu không bị đếm như nhiều yêu cầu, và mọi kết luận truy cập sau từ chối đều có căn cứ tương quan rõ ràng.

## 12. Câu hỏi tự kiểm tra

**Vì sao không cộng EXPIRED vào số lần bị từ chối?**

Hết hạn cho biết yêu cầu không đạt kết quả trước deadline. Nó không chứng minh người có thẩm quyền đã quyết định từ chối. Gộp hai loại sẽ làm lẫn lỗi khả dụng của workflow với quyết định kiểm soát.

**Ba người duyệt từ chối cùng một yêu cầu có phải ba lần xin quyền thất bại không?**

Không, nếu detector đang đo số yêu cầu. Đó có thể là ba quyết định thành phần của một yêu cầu; phải xem quy tắc kết thúc của workflow trước khi xác định trạng thái cuối.

**Một phiên xuất hiện sau chuỗi từ chối có đủ để kết luận bypass không?**

Chưa đủ. Cần xác định người thụ hưởng, tài nguyên, quyền, grant và thời điểm hiệu lực. Phiên có thể dùng quyền đã được cấp hợp lệ từ trước hoặc một yêu cầu mới đã đáp ứng điều kiện.

**Tại sao không dùng IP làm khóa chính?**

IP có thể được chia sẻ hoặc thay đổi, và không thể hiện chính xác người sẽ nhận quyền. Dùng danh tính đã xác minh, tenant và định danh tài nguyên; IP là ngữ cảnh bổ sung.

**Khi hàng loạt yêu cầu hợp lệ bị chặn, có nên bỏ approval để khôi phục công việc không?**

Cần khôi phục tuyến duyệt, tích hợp hoặc cấu hình đúng quy trình. Nếu có nhu cầu khẩn cấp, dùng cơ chế khẩn cấp đã được tổ chức phê chuẩn với phạm vi, thời hạn và bằng chứng phù hợp.

**Điều gì quan trọng hơn một ngưỡng đếm tốt?**

Khả năng giải thích detector đã đếm những yêu cầu nào, dùng trạng thái nào, thiếu dữ liệu gì và quyền thực tế có phát sinh hay không. Ngưỡng chỉ hữu ích khi dữ liệu và mối liên hệ đó đáng tin cậy.

## 13. Điểm ghi nhớ

Failed approval pattern là tín hiệu để đặt câu hỏi về cả hành vi xin quyền và sức khỏe quy trình phê duyệt. Muốn dùng tín hiệu đúng, cần phân loại kết quả, đếm yêu cầu riêng biệt, giữ lịch sử quyết định và tương quan với quyền được cấp cùng phiên sử dụng.

Trong PAM, kết quả mong muốn là quyền đặc biệt chỉ được cấp đúng người, đúng phạm vi, đúng thời hạn và có bằng chứng. Giám sát tốt giúp nhận ra khi điều kiện đó có nguy cơ bị phá vỡ, đồng thời phát hiện những trục trặc khiến công việc hợp lệ không thể đi qua kiểm soát.
