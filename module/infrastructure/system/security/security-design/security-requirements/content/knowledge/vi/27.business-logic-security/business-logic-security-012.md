# Four-eyes principle

## 1. Nguyên tắc bốn mắt bảo vệ quyết định nghiệp vụ như thế nào?

Trong chương **Business logic security**, four-eyes principle, hay **nguyên tắc bốn mắt**, yêu cầu một hành động nhạy cảm phải có sự tham gia kiểm soát của ít nhất hai người độc lập theo chính sách trước khi được thực hiện. Cách triển khai phổ biến là một người lập đề nghị và một người khác kiểm tra, phê duyệt.

Mục tiêu là giảm khả năng một cá nhân tự tạo và hoàn tất thay đổi có tác động lớn, dù do sai sót, lạm quyền hoặc tài khoản bị chiếm. Ví dụ gồm cấp quyền quản trị, xuất dữ liệu nhạy cảm, thay đổi cấu hình bảo vệ hoặc thực hiện một nghiệp vụ không thể dễ dàng đảo ngược.

Đối với đặc tả yêu cầu bảo mật, một màn hình có nút “Phê duyệt” chưa đủ. Cần xác định:

- Ai được đề nghị, ai được kiểm tra và thế nào là hai người khác nhau.
- Nội dung nào được phê duyệt và thay đổi nào làm phê duyệt mất hiệu lực.
- Khi nào quyết định hết hạn hoặc phải kiểm tra lại quyền.
- Cơ chế nào ngăn thực thi trực tiếp, thực thi lặp hoặc dùng phê duyệt cho đối tượng khác.
- Bằng chứng nào chứng minh quy trình được tuân thủ.

Bài học chuyển nguyên tắc tổ chức thành chuỗi yêu cầu:

**Rủi ro → vai trò và xung đột lợi ích → nội dung quyết định → điều kiện thực thi → kiểm thử và audit.**

Các luồng, thời hạn và ngưỡng trong bài là ví dụ thiết kế, cần điều chỉnh theo mô hình đe dọa và tác động nghiệp vụ của hệ thống thực tế.

## 2. Phân biệt các khái niệm dễ bị nhầm

| Khái niệm | Vai trò | Điều không được suy ra |
|---|---|---|
| Four-eyes principle | Có ít nhất hai người độc lập kiểm soát hành động theo chính sách | Hai tài khoản luôn đồng nghĩa với hai người |
| Separation of duties | Phân chia các nhiệm vụ hoặc quyền có thể tạo xung đột | Chỉ chia tên role là đã ngăn được một người giữ cả hai quyền |
| Maker-checker | Người lập đề nghị và người kiểm tra, quyết định | Checker được sửa nội dung rồi tự phê duyệt phiên bản mới mà không có kiểm soát |
| Xác thực nhiều yếu tố | Tăng độ tin cậy rằng một chủ thể đang sử dụng danh tính của mình | Hai yếu tố xác thực tạo thành hai người phê duyệt |
| Phê duyệt theo quorum | Đòi đủ số người hoặc nhóm đủ điều kiện | Mọi người có quyền xem request đều đủ điều kiện ký quyết định |
| Audit | Lưu bằng chứng về hành động và quyết định | Ghi log sau khi đã làm thay thế được kiểm soát trước khi thực thi |

### 2.1. Hai người hay hai người phê duyệt?

Một chính sách maker-checker có thể yêu cầu:

```text
1 người lập đề nghị + 1 người phê duyệt độc lập
= ít nhất 2 người tham gia kiểm soát
```

Nếu yêu cầu là “hai người phê duyệt độc lập ngoài người lập”, tối thiểu sẽ có ba người. Cần ghi rõ ai được tính vào điều kiện, không dùng cụm “cần hai chữ ký” mà thiếu định nghĩa.

Nếu đề nghị do máy tự động tạo và không có người lập chịu trách nhiệm xác nhận nội dung, không được tự tính service account thành một người. Chính sách có thể yêu cầu một người tiếp nhận, xác nhận đề nghị rồi một người khác kiểm tra, hoặc yêu cầu đủ số reviewer là người theo quy tắc riêng.

### 2.2. Phạm vi bảo vệ và giới hạn

Nguyên tắc này làm giảm rủi ro một người hành động đơn lẻ nhưng không tự loại trừ:

- Hai người thông đồng.
- Hai tài khoản cùng bị chiếm quyền.
- Người kiểm tra phê duyệt mà không đọc hoặc không hiểu tác động.
- Nội dung được thực thi khác với nội dung đã kiểm tra.
- Đường quản trị, job hoặc API nội bộ bỏ qua cổng phê duyệt.
- Một quản trị viên có thể tự sửa cả policy, dữ liệu và dấu vết audit.

Cần phối hợp phân quyền tối thiểu, xác thực phù hợp, bảo vệ nội dung quyết định, kiểm soát đường thực thi và khả năng điều tra. Không tuyên bố rằng thêm một bước approval sẽ giải quyết mọi rủi ro của nghiệp vụ.

## 3. Xuất phát từ mô hình đe dọa và hành động nhạy cảm

### 3.1. Xác định quyết định cần được kiểm soát

Không nên áp dụng approval như một bước hình thức cho mọi thao tác. Hãy xác định hành động có tác động lớn và lý do cần một người độc lập kiểm tra.

| Hành động | Sai sót hoặc lạm dụng cần phòng ngừa | Nội dung người kiểm tra cần thấy |
|---|---|---|
| Cấp quyền đặc biệt | Tự nâng quyền hoặc cấp sai phạm vi | Người nhận, quyền cụ thể, môi trường, tài nguyên, thời hạn |
| Xuất dữ liệu | Xuất vượt phạm vi hoặc gửi sai nơi nhận | Tập dữ liệu, bộ lọc, độ nhạy, đích xuất và quyền truy cập |
| Thay cấu hình bảo vệ | Tắt kiểm soát hoặc mở rộng ngoại lệ | Giá trị cũ/mới, tác động, thời hạn ngoại lệ và kế hoạch quay lại |
| Thay thông tin đích của một nghiệp vụ | Chuyển kết quả sang bên không được phép | Đối tượng nguồn, đích, căn cứ và thay đổi cụ thể |
| Xóa hoặc hủy dữ liệu quan trọng | Mất dữ liệu ngoài ý muốn | Phạm vi xóa, khả năng phục hồi, phụ thuộc và hệ quả |

### 3.2. Mô tả tác nhân và đường vượt kiểm soát

Các trường hợp cần đưa vào mô hình đe dọa:

1. Người lập dùng tài khoản phụ hoặc quyền được ủy quyền để tự phê duyệt.
2. Người kiểm tra thay nội dung sau khi đã đồng ý.
3. Caller tái sử dụng approval của request này cho request khác.
4. Request được phê duyệt khi người kiểm tra còn quyền nhưng thực thi sau khi quyền đã mất hiệu lực.
5. Hai request thực thi đồng thời làm dùng một approval nhiều lần.
6. Job hoặc API quản trị thực thi cùng loại thay đổi nhưng không cần approval.
7. Người có quyền cấu hình tự hạ số reviewer hoặc mở ngoại lệ cho chính mình.
8. Tác nhân chia nhỏ nghiệp vụ để né ngưỡng phê duyệt.

Nếu approval chỉ áp dụng khi vượt một ngưỡng, phải xét phạm vi cộng dồn, thời gian và những hành động liên quan. Kiểm soát từng request riêng lẻ có thể bỏ qua nhiều request nhỏ cùng tạo một tác động lớn.

## 4. Vai trò, danh tính và tính độc lập

### 4.1. Mô hình vai trò

Một mô hình tối thiểu có thể gồm:

- **Maker:** lập và chịu trách nhiệm về đề nghị.
- **Checker:** đánh giá nội dung, điều kiện và xung đột lợi ích, rồi chấp thuận hoặc từ chối.
- **Executor:** thực hiện nội dung đã đủ điều kiện, có thể là một dịch vụ.
- **Policy administrator:** quản lý điều kiện và danh sách vai trò đủ thẩm quyền.
- **Auditor:** xem xét bằng chứng theo quyền được cấp.

Executor là service account không làm mất yêu cầu có hai người ở bước quyết định. Ngược lại, việc một người vận hành bấm nút thực thi cũng không biến một approval không hợp lệ thành hợp lệ.

Một người có thể có nhiều vai trò trong tổ chức, nhưng chính sách động vẫn phải ngăn họ làm cả maker và checker cho cùng đề nghị nếu quy tắc yêu cầu độc lập.

### 4.2. Phải so sánh chủ thể người, không chỉ username

Hệ thống cần một định danh chủ thể người ổn định từ nguồn đủ tin cậy. Hai account, hai phiên đăng nhập hoặc hai credential của cùng người vẫn là một người trong điều kiện độc lập.

Ví dụ quy tắc:

```text
checker.person_id != maker.person_id
checker.person_id không nằm trong tập người có xung đột bị policy cấm
checker có quyền phê duyệt cho đúng loại hành động và phạm vi
```

Tùy nghiệp vụ, tập xung đột có thể gồm người thụ hưởng, người chỉnh sửa nội dung nhạy cảm hoặc các chủ thể khác được policy định nghĩa. Không mặc định quan hệ quản lý hay tên phòng ban tự chứng minh tính độc lập.

Ủy quyền cần có chủ thể thực sự thực hiện, người được đại diện, phạm vi và thời hạn. Không để một người đổi ngữ cảnh đại diện rồi được tính thành hai reviewer. Nếu không xác định được danh tính người hoặc quyền ủy quyền, không được tự cho qua điều kiện.

Thông tin danh tính và quan hệ cần được giới hạn quyền truy cập, không sao chép toàn bộ hồ sơ nhân sự vào log chỉ để chứng minh hai người khác nhau.

## 5. Phê duyệt phải gắn với đúng nội dung và phiên bản

### 5.1. Một approval không phải quyền thực thi tùy ý

Một quyết định chấp thuận cần ràng buộc tối thiểu với:

```text
request_id, request_version
tenant hoặc phạm vi tổ chức
action_type
target và người thụ hưởng nếu có
tham số có tác động bảo mật
phạm vi tài nguyên
thời hạn và điều kiện thực hiện
policy_id, policy_version
checker_person_id
decision, decision_time, approval_expiry
```

Nếu nội dung thay đổi từ “cấp quyền đọc ở môi trường thử” sang “cấp quyền quản trị ở production”, approval cũ phải mất hiệu lực. Không được chỉ giữ một cờ `approved=true` trên request rồi cho sửa các field còn lại.

Một yêu cầu an toàn hơn là đóng băng nội dung khi gửi xét duyệt. Sửa trường có ý nghĩa bảo mật tạo phiên bản mới và phải xét duyệt lại. Nội dung và lịch sử cũ vẫn được giữ theo chính sách để kiểm chứng.

### 5.2. Ràng buộc bằng snapshot và digest phía server

Có thể dùng snapshot bất biến cùng digest của biểu diễn chuẩn hóa:

```text
approval_binding =
    request_id
    + request_version
    + digest(canonical_security_relevant_payload)
    + policy_version
```

Server phải tạo hoặc xác minh biểu diễn này từ dữ liệu có thẩm quyền. Không tin digest hoặc phiên bản do client tự gửi như bằng chứng nội dung đã được duyệt.

Digest giúp phát hiện nội dung không khớp nhưng không tự chứng minh người nào đã phê duyệt hoặc dữ liệu chưa bị quản trị viên sửa. Cần bảo vệ record quyết định, quyền ghi, lịch sử và bằng chứng theo mô hình đe dọa. Nếu cần chữ ký số hay chứng thực độc lập, phải đặc tả cơ chế và quản lý khóa riêng; không gọi một hash thông thường là chữ ký của người phê duyệt.

Các trường tham chiếu cũng cần xem xét. Một `role_id` không đủ nếu định nghĩa role có thể mở rộng quyền sau approval. Có thể ràng buộc phiên bản định nghĩa quyền bất biến, snapshot quyền cụ thể hoặc điều kiện buộc xét duyệt lại khi định nghĩa thay đổi.

Tương tự, một bộ lọc xuất dữ liệu có thể chọn thêm đối tượng khi dữ liệu nguồn thay đổi. Cần quy định approval dành cho tập đối tượng đã cố định hay cho một quy tắc động có giới hạn rõ ràng. Không hiển thị một danh sách nhỏ rồi thực thi một tập lớn khác mà không có điều kiện được chấp thuận.

### 5.3. Người kiểm tra phải thấy tác động sẽ được thực thi

Giao diện cần thể hiện thông tin có ý nghĩa quyết định:

- Chủ thể đề nghị và đối tượng hưởng kết quả.
- Môi trường, tài nguyên, quyền hoặc dữ liệu chịu tác động.
- Giá trị cũ/mới và phần khác biệt quan trọng.
- Thời hạn, lý do và căn cứ cần thiết.
- Những điều kiện hoặc cảnh báo liên quan đến phạm vi và xung đột.

Nội dung hiển thị phải lấy từ cùng snapshot mà executor sẽ dùng. Các trường được thêm ở bước thực thi không được mở rộng tác động ngoài approval.

Bảo vệ giao diện, phiên đăng nhập và endpoint quyết định theo yêu cầu ứng dụng, chẳng hạn chống gửi quyết định trái ý người dùng và yêu cầu xác thực bổ sung cho hành động phù hợp. Các biện pháp này bảo vệ thao tác của checker, nhưng không thay thế kiểm tra tính độc lập và quyền phía server.

Checker không nên sửa nội dung nhạy cảm rồi tự chấp thuận ngay trên cùng phiên bản. Nếu có quy trình góp ý hoặc sửa đề nghị, cần ghi nhận người tham gia và áp dụng lại quy tắc độc lập cho nội dung cuối.

## 6. Vòng đời quyết định và cổng thực thi

### 6.1. Mô hình trạng thái minh họa

```text
DRAFT -> PENDING
PENDING -> APPROVED       khi đủ quyết định hợp lệ
PENDING -> REJECTED       theo quy tắc từ chối đã chốt

PENDING hoặc APPROVED -> CANCELLED
PENDING hoặc APPROVED -> EXPIRED
PENDING hoặc APPROVED -> INVALIDATED

APPROVED -> EXECUTING -> EXECUTED
EXECUTING -> RECONCILIATION_REQUIRED
    khi chưa xác định chắc kết quả thực thi
```

Đây là mô hình tham khảo. Cần xác định chuyển trạng thái nào hợp lệ, ai có quyền thực hiện và khi nào thay đổi có hiệu lực.

Ví dụ chính sách có thể quy định mọi quyết định từ chối hợp lệ trước khi thực thi sẽ kết thúc request, thay vì chỉ giảm số phiếu. Một policy khác có thể cho điều chỉnh và gửi lại phiên bản mới. Không được để hai cách xử lý tồn tại ngầm trong các endpoint khác nhau.

### 6.2. Điều kiện xét duyệt

Trước khi ghi một approval, server phải kiểm tra:

1. Request đang ở trạng thái cho phép quyết định.
2. Phiên bản và snapshot đúng nội dung checker đang xem.
3. Checker là người đủ thẩm quyền trong đúng phạm vi.
4. Checker độc lập theo policy và chưa được tính lặp.
5. Request, quyền và ngữ cảnh cần thiết còn hiệu lực.
6. Quyết định cùng bằng chứng được lưu bền vững.

Với quorum, cùng một người không được tăng số phiếu bằng nhiều account hoặc nhiều lần gửi. Ràng buộc duy nhất hoặc cơ chế tương đương cần áp dụng theo `request_version` và định danh người thực sự được tính.

### 6.3. Điều kiện thực thi

Executor phải kiểm tra lại các điều kiện mà policy yêu cầu tại thời điểm thực thi:

- Đủ maker và checker hợp lệ, độc lập và còn hiệu lực.
- Payload, target, request version và policy version khớp.
- Chưa hết hạn, chưa hủy, chưa bị vô hiệu.
- Điều kiện quyền, phạm vi và trạng thái tài nguyên còn đúng.
- Chưa có quyền thực thi khác đang tạo cùng kết quả.

Không chỉ kiểm tra lúc đưa request vào queue rồi vài giờ sau thực hiện mà không xét lại. Nếu policy cho phép một quyết định tiếp tục có hiệu lực sau khi reviewer đổi vai trò, điều đó phải được nêu rõ. Trong ví dụ ở phần sau, quyền reviewer phải còn hiệu lực tại cổng thực thi.

Kiểm tra và giành quyền thực thi phải phối hợp nguyên tử trong phạm vi cam kết. Nếu hai worker cùng đọc `APPROVED` rồi đều thực hiện, một approval có thể tạo hai tác dụng phụ.

### 6.4. Hủy, thu hồi và hết hạn khi có thao tác đồng thời

Nếu hủy và executor cùng tranh quyền, cần một thứ tự quyết định có thể kiểm chứng. Ví dụ:

- Nếu hủy chuyển trạng thái thành công trước khi claim thực thi, executor không được thực hiện.
- Nếu claim hợp lệ đã thắng, thao tác hủy không được trả lời như thể chắc chắn đã ngăn hành động.
- Khi hành động đã có hiệu lực, đảo ngược hoặc thu hồi là một nghiệp vụ khác, có yêu cầu quyền và audit riêng.

Không hứa rollback một tác dụng phụ bên ngoài chỉ bằng việc đổi trạng thái request về `CANCELLED`.

Thời gian phải được kiểm tra bằng nguồn có thẩm quyền và quy tắc biên rõ ràng. Tại `now >= expires_at`, ví dụ này xem request hết hạn. Không dùng timestamp client để kéo dài hiệu lực hoặc dùng mốc chụp trước khi chờ khóa như thể đó là thời điểm quyết định hiện tại.

## 7. Ví dụ đặc tả: cấp quyền quản trị tạm thời ở production

### 7.1. Bối cảnh và rủi ro

Một nền tảng cho phép kỹ sư đề nghị quyền quản trị tạm thời cho một tập tài nguyên production. Rủi ro `R-4E-01` là một cá nhân tự nâng quyền, xin quyền phạm vi nhỏ nhưng thực thi phạm vi lớn, hoặc dùng lại quyết định cũ để tạo thêm quyền.

Ví dụ chọn mô hình:

- Người lập là một người đã xác thực và được phép đề nghị.
- Có một checker là người khác, có quyền phê duyệt cho môi trường và loại quyền tương ứng.
- Checker không phải maker và không phải người nhận quyền.
- Service executor chỉ được cấp quyền theo request hợp lệ.
- Request phải được claim thực thi trước 15 phút kể từ lúc gửi.
- Quyền được cấp có thời hạn tối đa 30 phút tính từ lúc kích hoạt theo cơ chế phía server.

Maker có thể là người xin quyền cho chính mình, nhưng không được tự làm checker. Nếu maker đề nghị cho người khác, checker vẫn phải thỏa cả hai điều kiện độc lập nói trên.

Những mốc 15 và 30 phút có mục đích khác nhau: một mốc giới hạn hiệu lực xét duyệt, một mốc giới hạn quyền sau khi cấp. Chúng cần được hiển thị và kiểm chứng riêng.

### 7.2. Nội dung cần đóng băng

```text
request_id, request_version
maker_person_id
beneficiary_person_id
tenant, environment
resource_set
immutable_permission_definition_version
permission_digest
grant_duration
activation_deadline
reason_reference
policy_id, policy_version
```

Phạm vi tài nguyên và định nghĩa quyền phải có ý nghĩa ổn định. Nếu dùng một role động, cần cơ chế không để quyền thực tế mở rộng ngoài phiên bản đã duyệt, kể cả sau lúc cấp. Có thể cấp theo định nghĩa quyền bất biến hoặc đặt quy tắc thay đổi role tác động đến grant hiện hữu riêng biệt.

### 7.3. Tập yêu cầu minh họa

| ID | Yêu cầu |
|---|---|
| SEC-4E-01 | Mọi đường cấp loại quyền production này phải đi qua cổng quyết định, gồm API, job, công cụ vận hành và đường nội bộ thuộc phạm vi hệ thống. |
| SEC-4E-02 | Trước thực thi phải có một maker là người và ít nhất một checker là người đủ thẩm quyền; checker khác maker và khác người nhận quyền theo định danh người có thẩm quyền. |
| SEC-4E-03 | Hai account hoặc hai quyết định của cùng một người không được thỏa điều kiện độc lập. Không xác định được liên kết danh tính thì không thực thi. |
| SEC-4E-04 | Checker chỉ được quyết định trên snapshot bất biến gắn request version và policy version. Thay nội dung có ý nghĩa bảo mật làm quyết định cũ mất hiệu lực và yêu cầu xét duyệt lại. |
| SEC-4E-05 | Giao diện quyết định phải thể hiện người nhận, môi trường, tập tài nguyên, quyền cụ thể, thời hạn và lý do từ đúng snapshot được dùng khi thực thi. |
| SEC-4E-06 | Tại thời điểm claim thực thi, checker vẫn phải có quyền hợp lệ; request chưa hết hạn và policy liên quan chưa đổi phiên bản. Không thỏa thì chuyển sang hết hạn hoặc vô hiệu theo nguyên nhân, không tự dùng quyết định cũ. |
| SEC-4E-07 | Request hết hạn khi thời điểm quyết định đạt hoặc vượt `activation_deadline`. Chờ trong queue không gia hạn deadline. |
| SEC-4E-08 | Claim thực thi và ràng buộc kết quả phải ngăn nhiều worker tạo nhiều grant cho cùng thao tác. Retry sau lỗi dùng cùng định danh thao tác và có cách đối soát. |
| SEC-4E-09 | Executor chỉ dùng trường đã đóng băng, không nhận quyền hoặc resource bổ sung từ lời gọi thực thi. Quyền được kích hoạt không vượt 30 phút và phải có cơ chế hết hiệu lực được kiểm chứng. |
| SEC-4E-10 | Hủy thắng trước claim thì không cấp quyền. Nếu claim đã thắng hoặc kết quả chưa rõ, API không được báo đã chắc chắn ngăn cấp; phải trả trạng thái và hướng dẫn theo hợp đồng. |
| SEC-4E-11 | Quyết định, claim và kết quả phải có record bền vững có thể liên kết. Không ghi được bằng chứng bắt buộc thì không tiếp tục tạo grant mới. |
| SEC-4E-12 | Thay đổi policy hoặc ngoại lệ có khả năng làm mất điều kiện độc lập phải có kiểm soát riêng, không cho maker tự hạ ngưỡng rồi thực thi request của mình. |

Mô hình này là một maker cộng một checker. Nếu tổ chức yêu cầu hai reviewer ngoài maker hoặc hai nhóm chuyên môn, phải đổi điều kiện và các ca kiểm thử; không chỉ đổi nhãn màn hình thành “two approvals”.

### 7.4. Mã giả tại cổng thực thi

```text
claim_and_execute(request_id, expected_version):
    load trusted request and frozen payload
    verify authenticated executor is allowed to use this workflow

    at the authoritative decision boundary:
        verify state is APPROVED
        verify request version and payload binding
        verify current policy version matches
        verify maker/checker identities and independence
        verify checker authority under the execution-time policy
        verify server time is before activation_deadline
        verify beneficiary and resource conditions
        claim execution for the stable operation identity

    perform only the frozen action through the controlled grant path
    persist or reconcile the result using that same operation identity
```

Mã giả mô tả yêu cầu ngữ nghĩa, không chứng minh các lời gọi riêng lẻ đã nguyên tử. Nhóm kiến trúc phải xác định cổng thẩm quyền nằm ở đâu và thành phần nào ngăn điều kiện thay đổi trong khoảng giữa kiểm tra và tạo grant.

Nếu dữ liệu workflow, policy và grant nằm cùng miền giao dịch, có thể thiết kế một quyết định nguyên tử tại đó. Nếu ở nhiều dịch vụ, cần giao thức cấp phép, ràng buộc phiên bản hoặc cơ chế tương đương được tài nguyên đích thực thi. Không suy tính nguyên tử xuyên hệ thống chỉ từ một transaction ở kho workflow.

## 8. Retry, sự cố, đường khẩn cấp và giới hạn tin cậy

### 8.1. Không biến kết quả chưa rõ thành một request mới

Có thể xảy ra việc grant đã được tạo nhưng executor chưa nhận kết quả. Đổi request ID hoặc xin approval mới rồi cấp lại ngay có thể tạo thêm grant hoặc kéo dài quyền ngoài ý định ban đầu.

Cần:

- Dùng định danh thao tác ổn định cho claim, lời gọi cấp quyền và đối soát.
- Phân biệt chưa thực thi với đã thực thi nhưng chưa nhận kết quả.
- Cho phép retry theo hợp đồng idempotency của thành phần cấp quyền.
- Không tự đưa request từ trạng thái không chắc chắn về “chưa làm” mà thiếu bằng chứng.
- Theo dõi các request cần đối soát và cận thời gian xử lý.

Lease của worker không đủ ngăn một worker cũ tiếp tục cấp quyền. Cần kiểm soát quyền thực thi tại nơi tạo grant hoặc một cơ chế ngăn writer cũ phù hợp.

### 8.2. Không có quyết định tin cậy thì không thực thi mới

Nếu không xác định được policy, danh tính, tính độc lập hoặc hiệu lực quyết định, ví dụ này chọn không tạo grant mới. Trạng thái lỗi cần rõ để vận hành xử lý, không âm thầm bỏ kiểm tra khi dịch vụ danh tính chậm.

Cần phân biệt không ghi được record quyết định bắt buộc với gián đoạn tạm thời ở hệ thống thu log tập trung. Có thể dùng outbox bền vững để chuyển audit sau, nếu đã có cận lưu trữ, giám sát và chính sách khi không còn lưu được. Không coi việc log collector trả lỗi là lý do tự bỏ mọi yêu cầu bằng chứng.

Nếu trạng thái quyền nằm ở một dịch vụ khác và có cache, yêu cầu “thu hồi có hiệu lực tức thì” cần cơ chế nhất quán riêng. Phải nêu cửa sổ hiệu lực nếu có; không hứa kiểm tra hiện tại trong khi chỉ đọc một bản cache không rõ tuổi.

### 8.3. Ngoại lệ khẩn cấp phải là một chính sách riêng

Nếu nghiệp vụ có break-glass, cần xác định điều kiện kích hoạt, chủ thể được dùng, phạm vi tối thiểu, thời hạn, xác thực và bằng chứng. Quyền khẩn cấp không được ẩn dưới một checkbox để maker tự bỏ checker.

Nếu ngoại lệ cho phép một người hành động đơn lẻ, phải ghi nhận đúng đó là ngoại lệ đối với kiểm soát trước thực thi. Việc một người khác xem lại sau không biến hành động trước đó thành đã tuân thủ four-eyes tại thời điểm thực hiện.

Yêu cầu có thể gồm cảnh báo tức thời theo quy trình, quyền tự hết hạn, rà soát sau sự kiện và kiểm tra lạm dụng. Các cơ chế này phải được đặc tả và diễn tập, không dùng nhãn “khẩn cấp” để bỏ ngỏ điều kiện.

### 8.4. Bảo vệ cả khả năng thay đổi kiểm soát

Nếu một người có thể sửa policy, tự cấp quyền checker, thay record approval và xóa audit, ranh giới bảo vệ của workflow đã bị vượt.

Cần phân tách quyền quản trị phù hợp, bảo vệ lịch sử quyết định và kiểm soát thay đổi cấu hình. Các quyền rất cao ở database, hạ tầng và hệ thống danh tính phải nằm trong mô hình đe dọa; không tuyên bố ứng dụng chặn được một quản trị viên ngoài phạm vi kiểm soát chỉ bằng một điều kiện trong API.

## 9. Tiêu chí kiểm thử và bằng chứng

### 9.1. Dữ liệu và điều kiện thử

Chuẩn bị các danh tính có quan hệ rõ ràng: maker, checker đủ quyền, checker thiếu phạm vi, người thụ hưởng, hai account cùng một người và service account. Nguồn ánh xạ người phải là nguồn dùng thực tế trong thiết kế, không chỉ các chuỗi username khác nhau trong fixture.

Kiểm thử cần đi qua API và cổng cấp quyền, bao gồm worker, thay vì chỉ kiểm tra nút trên giao diện có bị ẩn hay không. Với các ca thời hạn và đồng thời, dùng clock kiểm soát được và barrier để tái lập thứ tự quyết định.

### 9.2. Ma trận kiểm chứng ví dụ

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Luồng hợp lệ | Maker và checker độc lập, đúng quyền, snapshot không đổi, còn hạn | Một grant đúng phạm vi và thời hạn được tạo; liên kết được với đề nghị và approval |
| T02 — Tự phê duyệt qua account phụ | Checker dùng account khác nhưng ánh xạ về maker hoặc người nhận quyền | Bị từ chối theo policy; không tạo grant |
| T03 — Sai phạm vi quyền | Checker có quyền ở môi trường thử nhưng duyệt production | Quyết định không được tính hợp lệ |
| T04 — Thay nội dung | Sau approval, đổi người nhận, resource, thời hạn hoặc phiên bản quyền | Không thực thi theo approval cũ; yêu cầu mới hoặc phiên bản mới phải được xét lại |
| T05 — Hết hạn | Cho claim xảy ra trước và tại đúng `activation_deadline` bằng clock thử | Trước hạn còn cần thỏa mọi điều kiện khác; tại hạn không tạo grant mới |
| T06 — Checker mất quyền | Thu hồi thẩm quyền checker trước cổng thực thi | Request không được thực thi theo chính sách kiểm tra quyền hiện tại của ví dụ |
| T07 — Policy thay đổi | Đổi phiên bản policy liên quan sau approval | Quyết định cũ bị vô hiệu cho thực thi; không tự bỏ điều kiện mới |
| T08 — Hai worker cạnh tranh | Hai worker cùng claim một request đủ điều kiện | Chỉ một quyền thực thi cho thao tác; không có hai grant độc lập |
| T09 — Mất response | Hệ thống cấp quyền đã nhận thao tác nhưng executor mất kết quả | Đối soát hoặc retry cùng operation identity; không cấp lại bằng ID mới |
| T10 — Hủy và thực thi | Dùng barrier để hủy thắng trước claim, rồi thử thứ tự ngược lại | Thứ tự thứ nhất không cấp; thứ tự thứ hai không báo hủy như thể chắc chắn đã ngăn cấp |
| T11 — Đường gọi trực tiếp | Gọi endpoint, job hoặc công cụ nội bộ cấp quyền khi thiếu quyết định hợp lệ | Không tạo grant qua đường thuộc phạm vi kiểm soát |
| T12 — Hết hạn quyền | Kích hoạt grant rồi đưa clock tới giới hạn hiệu lực | Quyền không còn được sử dụng theo hợp đồng, kể cả khi job dọn dữ liệu chạy chậm |
| T13 — Tính lặp reviewer | Với biến thể cần hai checker, một người gửi hai quyết định qua hai account | Chỉ tính một người; chưa đủ quorum |
| T14 — Đề nghị từ máy | Service account tạo request nhưng không có maker là người theo policy ví dụ | Không được tính service account thành maker để thỏa hai người |
| T15 — Thiếu bằng chứng bắt buộc | Làm lỗi bước lưu record quyết định hoặc claim bền vững | Không tiếp tục tạo grant mới mà thiếu bằng chứng |
| T16 — Ngoại lệ | Chủ thể không đủ quyền thử bỏ bước kiểm tra qua đường khẩn cấp | Bị từ chối; ngoại lệ hợp lệ nếu có được ghi theo policy riêng |

Ở T08 và T09, phải đối chiếu grant thực tế và định danh thao tác ở nơi cấp quyền. Đếm số response thành công chưa đủ vì response có thể là kết quả replay hợp lệ.

Ở T12, một job xóa grant không phải bằng chứng duy nhất. Cần kiểm chứng điểm ra quyết định cho phép sử dụng quyền có tôn trọng thời hạn và chính sách cache hay không.

T13 kiểm chứng biến thể quorum, không đổi ví dụ maker cộng một checker thành yêu cầu hai checker. Mỗi sản phẩm phải chọn rõ chính sách áp dụng.

### 9.3. Điều cần giữ trong báo cáo

Báo cáo cần có phiên bản policy, snapshot hoặc digest, quan hệ danh tính, trạng thái đầu, lịch sự kiện, kết quả claim, grant thực tế và các record liên quan.

Với hệ thống phân tán, ghi rõ giả định nhất quán của quyền, phiên bản và thời gian. Một lần chạy đúng ở một replica không chứng minh mọi đường thực thi đều giữ điều kiện.

Kiểm thử cần xác nhận cả hành vi cho phép và từ chối. Nếu mọi request đều bị chặn, hệ thống có thể giữ an toàn theo một nghĩa hẹp nhưng không đáp ứng nghiệp vụ cấp quyền hợp lệ.

## 10. Liên kết yêu cầu với rủi ro và kiến trúc

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc cần chứng minh | Bằng chứng |
|---|---|---|---|
| R-4E-01: Một người tự nâng quyền | SEC-4E-01, 02, 03 | Ánh xạ người có thẩm quyền và cổng kiểm tra độc lập | T02, T03, T11, T14 |
| Duyệt nội dung nhỏ nhưng thực thi rộng hơn | SEC-4E-04, 05, 09 | Snapshot bất biến và binding payload, quyền, resource | T04 và đối chiếu grant |
| Dùng quyết định cũ hoặc quyền đã mất hiệu lực | SEC-4E-06, 07 | Kiểm tra phiên bản, quyền và thời gian tại cổng thực thi | T05, T06, T07 |
| Dùng một approval tạo nhiều tác dụng phụ | SEC-4E-08 | Claim phối hợp, operation identity và đối soát | T08, T09 |
| Hủy không ngăn được nhưng báo đã hủy thành công | SEC-4E-10 | Thứ tự chuyển trạng thái có hiệu lực và hợp đồng kết quả | T10 |
| Không đủ bằng chứng hoặc tự sửa policy | SEC-4E-11, 12 | Record bền vững, phân quyền cấu hình và audit | T15, kiểm thử quyền thay đổi và ngoại lệ |

Khi thêm API, thay hệ thống danh tính, thay định nghĩa role hoặc chuyển nơi cấp quyền, cần đánh giá lại những cam kết chịu ảnh hưởng. Chuỗi truy vết giúp nhóm triển khai biết yêu cầu nào cần kiểm chứng lại.

Tên một công cụ workflow không thay thế đặc tả. Yêu cầu cần giữ được ý nghĩa dù chuyển sang engine khác: người nào, nội dung nào, quyết định nào và tác dụng phụ nào phải được ràng buộc.

## 11. Logging, audit và vận hành

Record quyết định nên có:

```text
request_id, request_version
policy_id, policy_version
payload_binding
maker_person_reference
checker_person_reference
acting_account_reference và ngữ cảnh ủy quyền nếu có
decision và reason_reference
decision_time, expiry
execution_operation_id
claim_time, execution_state, result_reference
```

Các định danh nội bộ cần đủ để đối chiếu nhưng chỉ người có quyền mới được xem. Không ghi token phiên, credential, secret hoặc toàn bộ dữ liệu nhạy cảm trong đề nghị chỉ để làm audit.

Bảo vệ bằng chứng khỏi sửa hoặc xóa trái phép, có chính sách lưu giữ và đồng bộ thời gian phù hợp. Nếu dùng audit ngoài miền quản trị chính, phải xác định quyền và khả năng đối soát khi luồng chuyển audit lỗi.

Các chỉ số hữu ích:

- Số đề nghị, quyết định chấp thuận, từ chối, hết hạn và vô hiệu.
- Số lần tự phê duyệt hoặc xung đột danh tính bị chặn.
- Số snapshot hoặc policy version không khớp.
- Số lần claim cạnh tranh, retry và request chưa xác định kết quả.
- Thời gian chờ xét duyệt, thời gian từ approval tới thực thi.
- Số grant còn hiệu lực, grant quá hạn bị phát hiện và ngoại lệ khẩn cấp.

Không dùng reviewer ID, request ID hoặc tenant ID có số lượng không kiểm soát làm nhãn cho mọi metric. Dữ liệu chi tiết nên nằm trong log hoặc hệ thống audit được phân quyền.

Tỷ lệ phê duyệt gần như tuyệt đối, quyết định quá nhanh hoặc một nhóm người luôn duyệt lẫn nhau có thể là tín hiệu cần xem xét. Chúng không tự chứng minh lạm dụng; phải đối chiếu bối cảnh và quy trình.

Cần có người chịu trách nhiệm cho request tồn đọng, quyền quá hạn và kết quả thực thi không chắc chắn. Không giải quyết hàng đợi chậm bằng cách tự bỏ tính độc lập hoặc gia hạn approval mà không có policy.

## 12. Các lỗi đặc tả thường gặp

| Phát biểu | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “Mọi thay đổi cần bốn mắt” | Chưa có hành động, vai trò và điều kiện | Liệt kê hành động nhạy cảm, maker/checker và quy tắc thực thi |
| “Hai tài khoản là đủ” | Một người có thể sở hữu nhiều account | So sánh định danh người và quan hệ ủy quyền có thẩm quyền |
| “Có MFA thì đã đủ hai người” | MFA vẫn xác thực một chủ thể | Giữ riêng yêu cầu xác thực và yêu cầu độc lập |
| “Cờ approved cho phép thực hiện” | Không ràng buộc phiên bản, target và payload | Gắn quyết định với snapshot và kiểm tra tại cổng thực thi |
| “Checker có role admin là được” | Chưa có phạm vi và xung đột | Kiểm tra đúng action, tenant, môi trường và điều kiện độc lập |
| “Duyệt một lần dùng mãi” | Quyền, nội dung và policy có thể thay đổi | Nêu hạn hiệu lực và điều kiện bắt buộc xét lại |
| “Ẩn nút cấp quyền là đủ” | API, worker hoặc công cụ nội bộ vẫn có thể gọi | Bảo vệ nơi thực hiện tác dụng phụ và mọi đường thuộc phạm vi |
| “Mất kết quả thì cấp lại” | Có thể đã tạo grant | Đối soát theo operation identity và hợp đồng idempotency |
| “Khẩn cấp thì được tự bỏ kiểm tra” | Ngoại lệ không có cận hoặc chủ thể | Đặc tả policy break-glass riêng, có bằng chứng và thời hạn |
| “Log sau là thay được approval trước” | Không ngăn tác động xảy ra | Tách kiểm soát trước thực thi với rà soát sau sự kiện |

## 13. Bài tập áp dụng

Bạn thiết kế chức năng xuất dữ liệu khách hàng cho một nhóm vận hành. Hãy viết một tập yêu cầu gồm:

1. Rủi ro cần kiểm soát và hành động nào phải qua maker-checker.
2. Chủ thể người, role, phạm vi và điều kiện xung đột.
3. Nội dung đóng băng: tập dữ liệu, bộ lọc hoặc danh sách đối tượng, đích nhận và thời hạn.
4. Quy tắc với thay đổi payload, thay đổi policy, checker mất quyền và request hết hạn.
5. Cách ngăn thực thi trực tiếp, dùng lại approval hoặc hai worker cùng xuất hai lần.
6. Quy trình khi tạo tệp thành công nhưng phản hồi bị mất, hoặc cần hủy trước khi giao tệp.
7. Ca kiểm thử tự phê duyệt qua account phụ, đổi đích nhận sau approval và retry sau lỗi.
8. Chuỗi truy vết từ rủi ro tới yêu cầu, kiến trúc và bằng chứng audit.

Tự kiểm tra: **Hai người có thật sự độc lập theo policy không, và điều họ đã xem xét có đúng là điều hệ thống thực thi không?** Nếu chỉ chứng minh có hai lần bấm nút mà không trả lời được hai câu hỏi này, yêu cầu còn thiếu.
