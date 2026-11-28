# Review frequency

## Mục tiêu bài học

Trong chương **Inventory và ownership** của quản lý truy cập đặc quyền (**Privileged Access Management — PAM**), **review frequency** là cách xác định khi nào phải rà soát lại tính đúng đắn của inventory, ownership và nhu cầu truy cập đặc quyền.

Một bản ghi từng đúng có thể trở nên lỗi thời khi người dùng chuyển đội, workload đổi chức năng, tài nguyên được thay thế hoặc role được mở rộng. Vì vậy, lịch review cần bám vào mức rủi ro và các sự kiện thay đổi, đồng thời tạo bằng chứng về những gì thực sự đã được xác nhận.

Bài học áp dụng cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Sau bài học, bạn có thể:

- Phân biệt chu kỳ review với chu kỳ discovery, luân chuyển credential và thời hạn quyền.
- Chọn nhịp rà soát phù hợp với tác động, mức thay đổi và chất lượng dữ liệu.
- Kết hợp review định kỳ, review theo sự kiện và đối soát liên tục.
- Quản lý ngày đến hạn, lần review thất bại, phần chưa bao phủ và trường hợp quá hạn.
- Lưu bằng chứng phục vụ least privilege, JIT/JEA, quản lý credential, kiểm toán và ứng phó sự cố.

## 1. Review frequency thực sự kiểm soát điều gì?

Mục tiêu của lịch review là giới hạn khoảng thời gian một sai lệch có thể tồn tại mà chưa được xem xét bằng quy trình phù hợp. Lịch không tự sửa dữ liệu hoặc thu hồi quyền; nó tạo điểm kiểm tra và trách nhiệm xử lý.

Trong inventory PAM, cần trả lời lại những câu hỏi như:

- Danh tính và tài nguyên này còn tồn tại trong đúng hệ thống không?
- Owner còn chịu trách nhiệm và có khả năng xác nhận nhu cầu không?
- Business purpose còn đúng với công việc hiện tại không?
- Phạm vi hệ thống và workload sử dụng đã thay đổi chưa?
- Quyền hiệu lực còn phù hợp với nhiệm vụ không?
- Credential, đường cấp quyền và phiên có được quản lý theo yêu cầu hiện tại không?
- Bằng chứng quan sát có đủ mới và đủ bao phủ không?

Review frequency không chỉ là một trường ghi “hàng quý”. Cần biết chu kỳ áp dụng cho đối tượng nào, loại review nào, ai thực hiện và điều gì được tính là hoàn tất.

### Bốn yếu tố cần xác định riêng

| Yếu tố | Ý nghĩa |
| --- | --- |
| Chu kỳ | Khoảng lặp lại của review định kỳ |
| Sự kiện kích hoạt | Thay đổi khiến phải xem lại trước kỳ tiếp theo |
| Hạn hoàn tất | Mốc mà review phải được thực hiện theo quy tắc đã định |
| Tiêu chí hoàn tất | Bằng chứng và quyết định cần có để đóng review |

Nếu chỉ có chu kỳ mà không có tiêu chí hoàn tất, một thao tác bấm xác nhận có thể bị hiểu nhầm thành review đầy đủ.

## 2. Những lịch khác nhau không thay thế nhau

| Hoạt động | Câu hỏi chính | Không tự chứng minh điều gì? |
| --- | --- | --- |
| Discovery hoặc đồng bộ inventory | Hiện quan sát được danh tính, tài nguyên và quan hệ nào? | Owner đã xác nhận nhu cầu và quyền đã phù hợp |
| Review ownership | Ai chịu trách nhiệm và trách nhiệm còn hiệu lực không? | Mọi quyền kỹ thuật của tài khoản đã được phân tích |
| Review business purpose | Công việc nào còn cần danh tính hoặc đường truy cập? | Tập quyền hiện tại là tập quyền tối thiểu |
| Review quyền | Khả năng hiệu lực có phù hợp với nhiệm vụ không? | Credential cũ và phiên hiện tại đều đã được xử lý |
| Luân chuyển credential | Credential được thay và bên phụ thuộc được cập nhật thế nào? | Quyền của tài khoản tại đích đã giảm |
| Hết hạn grant JIT | Grant tạm thời có kết thúc theo thiết kế không? | Quyền đủ điều kiện kích hoạt và ownership còn phù hợp |
| Đánh giá giám sát phiên | Hành động nhạy cảm có thể truy vết thế nào? | Mọi đường truy cập trực tiếp đã đi qua cơ chế ghi phiên |

Một hệ thống có thể discovery hàng ngày, review ownership theo chu kỳ khác và review quyền nhạy cảm theo chu kỳ ngắn hơn. Các lịch có thể được phối hợp trong một chiến dịch nhưng vẫn phải lưu phạm vi và kết quả của từng phần.

Ví dụ, vault luân chuyển mật khẩu thành công không phải lý do để cập nhật ngày “quyền đã review”. Một collector đọc được tài khoản hôm nay cũng chưa chứng minh owner được ghi từ năm trước vẫn hợp lệ.

## 3. Xác định đơn vị review trước khi đặt chu kỳ

Một ngày đến hạn chỉ có ý nghĩa khi gắn với đối tượng và nội dung rõ ràng. Có thể có review ở các mức:

- Một danh tính hoặc tài khoản đặc quyền.
- Một quan hệ gán quyền hoặc quyền đủ điều kiện kích hoạt.
- Một workload và các danh tính nó sử dụng.
- Một system scope với tài nguyên, ownership và phụ thuộc.
- Một tập credential và consumer liên quan.
- Một ngoại lệ có thời hạn.

Không nên dùng kết quả review của một tài khoản để tự động đánh dấu toàn bộ hệ thống đã review. Tương tự, owner của hệ thống được xác nhận không đồng nghĩa mọi tài khoản dịch vụ bên trong đều có owner hợp lệ.

### Phạm vi cần bao gồm quyền gián tiếp

Nếu review quyền chỉ kiểm tra role trực tiếp, lịch ngắn hơn cũng không khắc phục được điểm mù. Cần xem những đường liên quan như nhóm lồng nhau, kế thừa, trust, quyền lấy credential và khả năng sửa workload chạy dưới danh tính mạnh hơn.

Mỗi nền tảng có quy tắc đánh giá quyền riêng. Trong hồ sơ review, nêu rõ những nguồn và điều kiện đã kiểm tra, cùng phần chưa đủ dữ liệu.

## 4. Chọn chu kỳ theo rủi ro và mức thay đổi

Không có một chu kỳ duy nhất phù hợp cho mọi tài khoản và hệ thống. Cần dựa trên chính sách áp dụng, mức tác động và khả năng sai lệch xuất hiện giữa hai lần review.

| Chiều đánh giá | Câu hỏi lựa chọn chu kỳ |
| --- | --- |
| Tác động của quyền | Tài khoản có thể sửa IAM, credential, audit, dữ liệu nhạy cảm hoặc cơ chế phục hồi không? |
| Phạm vi ảnh hưởng | Quyền chỉ áp dụng cho một tài nguyên hay nhiều hệ thống và môi trường? |
| Tính biến động | Nhân sự, workload, role, nhóm và tài nguyên thay đổi nhanh đến mức nào? |
| Cách nhận quyền | Quyền thường trực, có điều kiện, JIT, JEA hay qua danh tính trung gian? |
| Mức phơi lộ credential | Có nhiều bên nhận, bản sao ngoài quản lý hoặc credential dùng chung không? |
| Chất lượng ownership | Owner đã xác nhận, có đầu mối thay thế và cơ chế bàn giao chưa? |
| Độ bao phủ quan sát | Có biết nguồn nào lỗi, dữ liệu nào cũ và đường nào chưa được kiểm tra không? |
| Lịch sử phát hiện | Có lặp lại quyền dư, ngoại lệ quá hạn hoặc thay đổi ngoài quy trình không? |
| Phụ thuộc vận hành | Có nhiệm vụ hiếm gặp, phục hồi hoặc dịch vụ trọng yếu cần ngữ cảnh riêng không? |

Tài khoản có credential ngắn hạn vẫn có thể cần review thường xuyên nếu được nhận role rất rộng. Tài khoản khẩn cấp ít sử dụng vẫn cần được xem xét về ownership, điều kiện sử dụng và khả năng hoạt động khi cần.

### Tần suất cao không bù được nội dung review yếu

Một đội có thể xác nhận danh sách mỗi tuần nhưng chỉ dựa vào tên role. Đội khác review ít hơn nhưng phân tích quyền hiệu lực, xác nhận owner và đóng phần chênh lệch. Không thể đánh giá chất lượng chỉ từ số lần review.

Nếu lịch quá dày khiến người phụ trách duyệt hàng loạt mà không xem bằng chứng, cần điều chỉnh cách tổ chức, dữ liệu hỗ trợ và ưu tiên. Không tự kéo dài chu kỳ chỉ vì thiếu nhân lực mà không có quyết định và xử lý rủi ro phù hợp.

## 5. Kết hợp ba lớp kiểm tra

```text
Review định kỳ
    -> Kiểm tra lại tập đối tượng theo lịch đã chốt

Review theo sự kiện
    -> Xem lại phần bị ảnh hưởng khi có thay đổi quan trọng

Đối soát hoặc giám sát liên tục
    -> Phát hiện sai lệch và đưa vào luồng xác minh

              Cùng cung cấp đầu vào cho
                        |
                        v
     Quyết định + thay đổi + xác minh + bằng chứng
```

### 5.1. Review định kỳ

Review định kỳ giúp tìm những thay đổi không tạo sự kiện, sự kiện bị bỏ lỡ hoặc dữ liệu không được cập nhật. Nó cũng tạo điểm xác nhận lại trách nhiệm và nhu cầu.

Cần có lịch cho phần đã biết và cơ chế đưa đối tượng mới vào lịch. Một tài khoản chưa được phân loại không nên bị bỏ quên chỉ vì chưa được gán chu kỳ.

### 5.2. Review theo sự kiện

| Sự kiện | Nội dung cần xem lại |
| --- | --- |
| Người dùng chuyển đội hoặc kết thúc nhiệm vụ | Mục đích, nhóm, role và phạm vi tài nguyên còn cần |
| Owner chuyển vai trò hoặc không còn liên hệ được | Trách nhiệm, người kế nhiệm và cơ chế phê duyệt |
| Workload đổi chức năng hoặc môi trường | Business purpose, danh tính, credential và scope |
| Role hoặc nhóm được mở rộng | Các chủ thể và hệ thống nhận khả năng mới |
| Trust hoặc cơ chế nhận danh tính thay đổi | Chủ thể nguồn, điều kiện và phạm vi quyền có thể nhận |
| Dự án hoặc migration kết thúc | Quyền tạm thời, tài khoản, credential và job còn tồn tại |
| Thêm consumer dùng chung credential | Ownership, phạm vi sử dụng và phụ thuộc luân chuyển |
| Có dấu hiệu lạm dụng | Điều tra, bảo toàn bằng chứng và hạn chế tác động theo quy trình sự cố |

Không chờ kỳ định kỳ tiếp theo để xem lại quyền của người đã kết thúc nhiệm vụ. Với sự cố đang diễn ra, review định kỳ không thay thế ứng phó.

### 5.3. Đối soát liên tục

Công cụ có thể phát hiện owner không còn hợp lệ, quyền tăng, tài nguyên mới hoặc credential ngoài danh mục. Tín hiệu đó nên tạo đầu việc xác minh với bên chịu trách nhiệm.

Không biến mọi cảnh báo thành thu hồi tự động nếu quy tắc chưa đủ rõ và chưa xét tác động. Ngược lại, cũng không đánh dấu review thành công chỉ vì một lần đối soát không có cảnh báo.

## 6. Ví dụ xây dựng lịch theo nhóm rủi ro

Bảng dưới đây là **giả định cho một tổ chức minh họa**, không phải chuẩn bắt buộc hoặc khuyến nghị dùng nguyên xi:

| Nhóm trong ví dụ | Chu kỳ review định kỳ giả định | Kiểm tra theo sự kiện |
| --- | --- | --- |
| Quyền sửa IAM, credential hoặc quản trị rộng production | Mỗi 30 ngày | Khi role, trust, owner hoặc bên sử dụng thay đổi |
| Quyền vận hành production có scope đã giới hạn | Mỗi 90 ngày | Khi nhiệm vụ, tài nguyên hoặc danh tính thay đổi |
| Quyền nhạy cảm có scope hẹp trong môi trường ít biến động | Mỗi 180 ngày | Khi môi trường, mức nhạy cảm hoặc phạm vi quyền thay đổi |

Các con số chỉ giúp minh họa cách gắn chu kỳ với phân loại. Khi áp dụng thực tế, tổ chức phải xác định tiêu chí, nguồn yêu cầu và người có thẩm quyền quyết định.

### Áp dụng nhiều yêu cầu cho cùng đối tượng

Một tài khoản có thể đồng thời thuộc review quyền định kỳ, review ownership và ngoại lệ sắp hết hạn. Không chọn chu kỳ dài nhất để thay mọi nghĩa vụ.

Nên lưu lịch riêng theo loại review hoặc dùng một chiến dịch chung có thể chứng minh đã đáp ứng từng phần. Nếu một sự kiện chỉ yêu cầu review trust, kết quả của nó không tự đặt lại ngày review toàn bộ quyền.

### Thiếu thông tin cần được xử lý, không bỏ qua

Nếu chưa biết tài khoản thuộc nhóm rủi ro nào, gán trạng thái chờ phân loại và đầu mối xử lý theo quy trình. Không mặc định đưa nó vào nhóm chu kỳ dài nhất.

Với tài khoản không rõ owner hoặc có khả năng quản trị lớn chưa xác minh, cần ưu tiên làm rõ khoảng trống thay vì chờ hết một chu kỳ dài.

## 7. Tính ngày đến hạn bằng quy tắc rõ ràng

Cần chọn cách tính và dùng nhất quán. Hai cách thường gặp có ý nghĩa khác nhau:

| Cách lập lịch | Đặc điểm | Điều cần kiểm soát |
| --- | --- | --- |
| Theo mốc lịch cố định | Ví dụ review trong từng quý hoặc theo ngày đã chốt | Review làm muộn không được che mất kỳ đã quá hạn |
| Theo khoảng cách từ lần hoàn tất hợp lệ | Kỳ tiếp theo dựa trên một lần review đáp ứng tiêu chí | Lần thất bại, thử lại hoặc chỉ sửa metadata không được đặt lại đồng hồ |

Phải phân biệt **ngày** với **tháng theo lịch**. Ba tháng không luôn bằng 90 ngày. Nếu dùng mốc tháng, cần quy tắc cho ngày không tồn tại ở tháng đích. Nếu dùng thời điểm, lưu múi giờ hoặc thời gian chuẩn nhất quán.

### Ví dụ minh họa cách tính

Giả sử một loại review có quy tắc mỗi ba tháng theo lịch từ lần hoàn tất hợp lệ. Review hoàn tất ngày `2026-06-15` thì ngày đến hạn tiếp theo là `2026-09-15`, theo múi giờ đã quy định.

Nếu một thay đổi role ngày `2026-07-02` tạo review theo sự kiện, sự kiện có hạn riêng theo chính sách. Không chờ đến `2026-09-15` để xem xét thay đổi đó.

Nếu review theo sự kiện chỉ đánh giá phần role mới, ngày đến hạn review toàn bộ vẫn giữ nguyên. Chỉ được dùng nó làm lần hoàn tất cho review định kỳ khi phạm vi, bằng chứng và tiêu chí thực sự bao phủ nghĩa vụ tương ứng.

### Không để thời hạn trượt do thao tác hành chính

Các thao tác sau không tự tạo lần review hợp lệ:

- Đồng bộ dữ liệu từ nguồn.
- Đổi người được giao review.
- Thử lại một job thu thập bị lỗi.
- Sửa ngày đến hạn mà không có căn cứ.
- Bấm xác nhận khi thiếu dữ liệu bắt buộc.
- Gia hạn ngoại lệ mà chưa xem xét lại theo thẩm quyền.

Nếu đã quá hạn, giữ lịch sử quá hạn. Khi review muộn được hoàn tất, lưu thời điểm thực tế và cách lập kỳ tiếp theo; không sửa lịch sử để trông như đã hoàn tất đúng hạn.

## 8. Xác định thế nào là review đã hoàn tất

Một lần review cần có phạm vi, người thực hiện, nguồn bằng chứng, kết luận và phần chưa giải quyết. Không yêu cầu mọi review đều phải thay quyền; giữ nguyên có thể là kết luận hợp lệ nếu có căn cứ.

Có thể tách hai luồng trạng thái:

```text
Luồng review:
Đến hạn -> Đang thực hiện -> Đủ bằng chứng và có quyết định
                         -> Thiếu dữ liệu / chưa quyết định

Luồng xử lý phát hiện:
Phát hiện -> Có chủ trì -> Áp dụng thay đổi -> Xác minh kết quả
```

Theo quy trình của tổ chức, review có thể được đóng sau khi có quyết định đầy đủ và đã giao xử lý phát hiện. Khi đó, trạng thái phải cho biết còn công việc khắc phục mở. Không diễn giải “review hoàn tất” thành “mọi quyền đã giảm” hoặc “không còn rủi ro”.

Nếu tiêu chí yêu cầu dữ liệu bắt buộc mà chưa có, không đóng review đầy đủ chỉ bằng một ghi chú sẽ bổ sung sau. Có thể ghi kết quả một phần, ngoại lệ hoặc trạng thái chờ theo cơ chế được chấp nhận.

### Bằng chứng tối thiểu cần xác định trong thiết kế

- Tập đối tượng và loại review được thực hiện.
- Mốc chụp dữ liệu, phiên bản scope và các nguồn đã dùng.
- Owner, mục đích và quyền đã được xem xét đến mức nào.
- Người ra quyết định và thời điểm thực tế.
- Kết luận giữ, thay đổi, thu hồi, chuyển cơ chế hoặc cần xác minh thêm.
- Phát hiện, chủ trì xử lý, hạn và tiêu chí xác minh.
- Phần thiếu dữ liệu, ngoại lệ và giới hạn của kết luận.

Nếu một review bao phủ nhiều tài khoản nhưng còn hai tài khoản chưa có bằng chứng, nên lưu kết quả theo từng đối tượng hoặc phần phạm vi. Không để trạng thái chung che mất phần chưa hoàn tất.

## 9. Lưu riêng các mốc thời gian

| Mốc | Ý nghĩa | Sai lầm cần tránh |
| --- | --- | --- |
| Lần quan sát dữ liệu gần nhất | Khi collector hoặc nguồn cung cấp dữ liệu | Coi đó là ngày owner đã xác nhận |
| Lần thử review gần nhất | Khi đã khởi động một lần thực hiện | Coi thử thất bại là hoàn tất |
| Lần review hợp lệ gần nhất | Khi phạm vi tương ứng đáp ứng tiêu chí | Dùng review phạm vi nhỏ cho toàn bộ hệ thống |
| Ngày đến hạn hiện tại | Nghĩa vụ cần hoàn tất theo quy tắc | Tự đẩy lùi khi chưa hoàn tất |
| Thời điểm phát sinh sự kiện | Khi thay đổi quan trọng xảy ra | Chỉ lưu ngày phát hiện rồi mất khoảng chậm trễ |
| Thời điểm ghi nhận sự kiện | Khi hệ thống hoặc đội vận hành biết sự kiện | Giả định luôn trùng thời điểm xảy ra |
| Hạn xử lý phát hiện | Khi cần áp dụng và xác minh thay đổi | Gộp với ngày đóng review |

Ví dụ sau là **hồ sơ lịch review minh họa**, không phải cấu hình của một sản phẩm:

```yaml
review_schedule:
  id: pam-review-schedule-example-009
  subject_ref: production/orders-service-account
  review_type: inventory-ownership-and-access
  scope_ref: orders-production-scope
  cadence:
    policy_ref: internal-example-policy
    mode: calendar-months-after-valid-completion
    interval: 3
    timezone: Asia/Ho_Chi_Minh
  responsibility:
    primary_team: orders-operations
    escalation_team: platform-governance
  timestamps:
    last_observed_at: '2026-08-30T08:00:00+07:00'
    last_review_attempt_at: '2026-08-30T10:00:00+07:00'
    last_valid_review_completed_at: '2026-06-15T15:00:00+07:00'
    periodic_due_at: '2026-09-15T15:00:00+07:00'
  current_attempt:
    state: blocked-by-missing-evidence
    missing_source: target-permission-snapshot
  evidence_ref: protected-records/review-attempt-example-009
```

Dữ liệu mới ngày 30/08 không làm thay đổi lần hoàn tất hợp lệ ngày 15/06. Lần thử ngày 30/08 thiếu bằng chứng cần thiết nên không tự tạo kỳ tiếp theo.

Nếu có gia hạn được chấp nhận, lưu cả hạn gốc, hạn mới, người quyết định và lý do. Không xóa hạn gốc hoặc sửa ngày hoàn tất quá khứ.

## 10. Tình huống: thay owner giữa hai kỳ review

Giả sử một hệ thống dùng lịch review đầy đủ mỗi ba tháng theo lịch, tính từ lần hoàn tất hợp lệ. Đây là quy tắc của tình huống minh họa.

| Thời điểm | Sự kiện | Cách ghi nhận |
| --- | --- | --- |
| 01/08 | Review đầy đủ hoàn tất | Lưu kết quả và hạn tiếp theo 01/11 |
| 10/09 | Owner chuyển sang đội khác | Tạo review theo sự kiện về ownership và các quyền bị ảnh hưởng |
| 12/09 | Owner mới nhận bàn giao | Ghi xác nhận trách nhiệm; không tự coi toàn bộ quyền đã review |
| 01/11 | Lượt thu thập quyền ở đích thất bại | Giữ hạn cũ và phần thiếu; không đánh dấu hoàn tất |
| 03/11 | Có dữ liệu cho 8 trong 10 đối tượng | Ghi phần đã review và hai đối tượng chưa đủ bằng chứng |
| 05/11 | Đủ dữ liệu, review đầy đủ có quyết định | Lưu hoàn tất muộn, phát hiện còn mở và kỳ tiếp theo theo quy tắc |

### Điều cần học từ tình huống

Review theo sự kiện ngày 12/09 giải quyết phần ownership nhưng không nhất thiết bao phủ toàn bộ nhiệm vụ của kỳ định kỳ. Lượt thu thập thất bại không đặt lại đồng hồ. Kết quả một phần phải được thể hiện rõ.

Khi hoàn tất ngày 05/11, có thể lập kỳ tiếp theo theo quy tắc đã chọn, nhưng vẫn giữ bằng chứng kỳ trước bị muộn. Nếu dùng lịch cố định thay cho khoảng cách từ lần hoàn tất, mốc kỳ tiếp theo phải theo lịch cố định tương ứng.

Việc có owner mới cũng không tự thu hồi quyền của owner cũ. Cần kiểm tra các quan hệ cấp quyền liên quan và trạng thái credential hoặc phiên nếu có thay đổi quyền.

## 11. Tổ chức thực hiện để lịch có khả năng vận hành

### Phân công rõ người quyết định

Owner dịch vụ xác nhận nhu cầu; chủ sở hữu tài nguyên hoặc nền tảng hỗ trợ đánh giá quyền; nhóm IAM/PAM hỗ trợ dữ liệu và cơ chế kiểm soát. Một đội có thể đảm nhiệm nhiều vai trò nhưng cần biết ai chịu trách nhiệm cho kết luận.

Không để reviewer chỉ nhận một danh sách role không có ngữ cảnh. Hồ sơ nên có mục đích, tài nguyên, thay đổi từ lần trước, nguồn quyền và phát hiện cần chú ý.

Nếu reviewer rời tổ chức hoặc không còn đủ ngữ cảnh, cần chuyển giao. Việc đổi người được giao không làm nghĩa vụ review cũ biến mất.

### Phân bổ lịch và ưu tiên

Có thể chia chiến dịch thành các nhóm để tránh mọi review cùng đến hạn một ngày. Cách phân bổ phải phù hợp với quy tắc chu kỳ và không âm thầm kéo dài khoảng tối đa được chấp nhận.

Khi có nhiều việc, ưu tiên theo khả năng tác động và mức khẩn cấp. Một thay đổi trust cho tài khoản quản trị rộng cần được xem xét khác với cập nhật mô tả của tài nguyên thử nghiệm.

### Gộp công việc có kiểm soát

Nhiều sự kiện có thể cùng ảnh hưởng một tài khoản. Có thể gộp vào một đầu việc nếu lưu các sự kiện nguồn, phạm vi cần kiểm tra và hạn áp dụng. Không để một sự kiện mới ít khẩn cấp ghi đè hạn sớm hơn của sự kiện cũ.

Một review toàn diện có thể đáp ứng nhiều nghĩa vụ nếu bằng chứng thực sự bao phủ từng nghĩa vụ. Khi đó, liên kết kết quả chung tới từng lịch tương ứng; không chỉ đổi mọi mốc thời gian về cùng một ngày.

### Chuẩn bị dữ liệu trước hạn

Trước khi đến hạn, có thể kiểm tra nguồn dữ liệu, định danh reviewer và phần scope chưa rõ. Chuẩn bị giúp giảm chậm trễ nhưng chưa được tính như review đã hoàn tất.

Quyền của công cụ thu thập cũng cần giới hạn phù hợp. Không cấp quyền quản trị toàn hệ thống cho collector chỉ để đơn giản hóa review.

## 12. Xử lý quá hạn và ngoại lệ

Quá hạn là trạng thái cần được quản lý, không phải lý do để tự thay ngày đến hạn.

Một luồng xử lý có thể gồm:

1. Xác định review nào quá hạn và phần nào chưa hoàn tất.
2. Phân biệt nguyên nhân: thiếu reviewer, thiếu dữ liệu, tranh chấp ownership hoặc chưa quyết định.
3. Đánh giá tác động của việc chưa có kết luận.
4. Giao trách nhiệm, chuyển cấp và áp dụng biện pháp phù hợp theo thẩm quyền.
5. Nếu cần ngoại lệ, lưu căn cứ, phạm vi, hạn và điều kiện kết thúc.
6. Hoàn tất review bằng bằng chứng thực tế, rồi tiếp tục xử lý các phát hiện.

Không có một phản ứng tự động phù hợp cho mọi tài khoản quá hạn. Vô hiệu hóa ngay một danh tính phục hồi hoặc tài khoản dịch vụ trọng yếu có thể gây tác động vận hành. Giữ quyền rộng vô thời hạn cũng không phải cách xử lý đầy đủ.

Biện pháp trong thời gian chờ có thể là hạn chế cấp quyền mới, tăng giám sát, thu hẹp đường sử dụng hoặc cơ chế khác phù hợp với hệ thống. Cần mô tả chính xác biện pháp nào đã áp dụng và rủi ro nào vẫn còn.

### Ngoại lệ không biến review thành đúng hạn

Một quyết định chấp nhận tiếp tục vận hành có thể cho phép xử lý theo kế hoạch, nhưng không nên xóa trạng thái lịch sử của kỳ bị trễ. Báo cáo cần phân biệt đã review, đang quá hạn và đang được xử lý theo ngoại lệ.

Nếu vấn đề lặp lại, xem lại nguồn dữ liệu, cách phân công và khả năng vận hành của lịch. Thay đổi chu kỳ phải có căn cứ; không chỉ làm cho chỉ số nhìn tốt hơn.

## 13. Kiểm chứng kết quả liên quan tới PAM

Review có thể dẫn tới giữ nguyên, giảm quyền, đổi ownership, tách danh tính hoặc thay cơ chế cấp credential. Mỗi quyết định cần bước xác nhận tương ứng.

| Quyết định | Điều cần kiểm tra tiếp |
| --- | --- |
| Giữ quyền | Nhu cầu, scope, điều kiện và bên xác nhận có căn cứ |
| Đổi owner | Bàn giao trách nhiệm và quyền của người/đội cũ được xem xét |
| Thu hẹp quyền | Khả năng dư đã mất và nhiệm vụ hợp lệ vẫn hoạt động |
| Chuyển sang JIT | Điều kiện kích hoạt, thời hạn, khả năng cấp quyền tiếp và phiên được xử lý |
| Chuyển sang JEA | Tác vụ, tham số, đích và khả năng sửa công cụ được giới hạn thực chất |
| Luân chuyển credential | Bên phụ thuộc đã chuyển và credential cũ được xử lý theo mục tiêu |
| Kết thúc nhu cầu | Các đường quyền, credential và phiên liên quan được xem xét |

Không gắn mọi bước xử lý vào chu kỳ review tiếp theo. Một phát hiện cần xử lý sớm phải có hạn riêng. Nếu thay đổi đã áp dụng nhưng chưa xác minh, giữ trạng thái đó thay vì coi đã khắc phục.

Credential và phiên có vòng đời khác nhau tùy nền tảng. Thu hồi một grant không tự bảo đảm mọi token hoặc phiên đã mất khả năng; cũng không nên khẳng định mọi token luôn giữ quyền tới khi hết hạn. Kế hoạch cần dựa trên cơ chế thực tế.

## 14. Đo lịch review bằng chỉ số có mẫu số rõ

Các chỉ số hữu ích gồm:

- Số nghĩa vụ review đến hạn trong kỳ.
- Tỷ lệ hoàn tất đúng hạn.
- Số đã hoàn tất muộn và số còn quá hạn.
- Số kết quả một phần hoặc bị chặn do thiếu dữ liệu.
- Tỷ lệ đối tượng đã có kết luận trong từng chiến dịch.
- Số phát hiện chưa áp dụng hoặc chưa xác minh.
- Số sự kiện thay đổi chưa được gắn với review cần thiết.

### Ví dụ tính chỉ số

Giả sử có **12 nghĩa vụ review đến hạn** trong kỳ, tất cả có cùng đơn vị đếm đã được định nghĩa:

| Kết quả | Số nghĩa vụ |
| --- | --- |
| Hoàn tất đúng hạn | 9 |
| Hoàn tất muộn | 2 |
| Chưa hoàn tất sau hạn | 1 |

Tỷ lệ hoàn tất đúng hạn là **9/12 = 75%**. Tổng tỷ lệ đã hoàn tất tại thời điểm báo cáo là **11/12**, khoảng **91,7%**. Hai chỉ số trả lời hai câu hỏi khác nhau.

Nếu một review tạo ra phát hiện chưa khắc phục, cần báo cáo riêng phần đó. Không cộng “đã giao người xử lý” vào số phát hiện đã xác minh hoàn tất.

### Tránh mẫu số bị thay đổi để che khoảng trống

Một tài khoản không truy vấn được vẫn cần được thể hiện trong phạm vi phù hợp. Không xóa đối tượng lỗi khỏi chiến dịch rồi báo đạt 100%. Nếu scope thực sự thay đổi, lưu quyết định, phiên bản và lý do.

Không trộn số tài khoản, số grant và số hệ thống trong cùng một tỷ lệ nếu chưa định nghĩa đơn vị. Một tài khoản có nhiều loại review có thể tạo nhiều nghĩa vụ; cần giải thích rõ điều đó.

Với scope động, lưu tập đối tượng tại mốc chốt và cách xử lý đối tượng thêm hoặc xóa giữa kỳ. Kết quả tại một thời điểm không chứng minh toàn bộ tài nguyên phát sinh sau đó đã được review.

## 15. Bảo vệ và lưu bằng chứng

Hồ sơ lịch và kết quả review nên liên kết được:

1. Quy tắc chu kỳ và phiên bản chính sách được dùng.
2. Đối tượng, scope và loại review.
3. Hạn gốc, thay đổi hạn nếu có và lý do.
4. Những lần thử, dữ liệu thiếu và sự kiện nguồn.
5. Người xác nhận, quyết định và thời điểm thực tế.
6. Đầu việc khắc phục, ngoại lệ và kết quả xác minh.

Inventory và hồ sơ quyền có thể tiết lộ kiến trúc, đường quản trị và tài nguyên nhạy cảm. Cần giới hạn quyền xem/sửa, bảo vệ lịch sử và lưu theo chính sách áp dụng. Không đưa mật khẩu, token hoặc private key vào hồ sơ review.

Một người kiểm tra cần tái dựng được vì sao lịch được chọn, kỳ nào bị chậm và quyết định nào còn chưa được thực thi. Một ngày xác nhận đơn lẻ không đủ thay thế chuỗi bằng chứng đó.

## 16. Tình huống tự đánh giá

Một tổ chức quy định review toàn bộ quyền của tài khoản phát hành mỗi quý. Collector đồng bộ hàng ngày. Giữa quý, tài khoản được thêm quyền sửa IAM và owner cũ chuyển đội. Cuối quý, reviewer chỉ xác nhận owner mới rồi đánh dấu toàn bộ review hoàn tất.

### Những điểm cần phát hiện

- Đồng bộ hàng ngày không chứng minh quyền đã được đánh giá.
- Quyền sửa IAM là thay đổi cần xem xét theo sự kiện và có thể làm thay đổi phân loại rủi ro.
- Owner chuyển đội cần bàn giao trách nhiệm và xem xét quyền liên quan.
- Xác nhận owner mới chưa bao phủ nội dung review toàn bộ quyền.
- Trạng thái hoàn tất cần phản ánh phạm vi bằng chứng thực tế.

### Hướng xử lý

Tách phần ownership đã xác nhận khỏi phần quyền chưa review. Bổ sung đánh giá quyền hiệu lực, nhu cầu sửa IAM, điều kiện nhận quyền và các đường gián tiếp liên quan. Ghi các nghĩa vụ đã trễ, giao xử lý phát hiện và xem lại chu kỳ dựa trên mức rủi ro hiện tại.

Nếu quyền sửa IAM không thuộc nhiệm vụ phát hành, cần lập thay đổi giảm quyền với xác minh phù hợp. Nếu có nhu cầu riêng hợp lệ, mô tả nhiệm vụ và cơ chế kiểm soát tương ứng, thay vì giữ quyền rộng bằng một xác nhận chung.

## 17. Checklist thiết kế review frequency

- Xác định rõ đối tượng và loại nội dung cần review.
- Chọn chu kỳ dựa trên rủi ro, biến động và yêu cầu áp dụng.
- Có sự kiện kích hoạt trước kỳ định kỳ.
- Ghi quy tắc tính hạn, múi giờ và cách xử lý lịch cố định hoặc lịch từ lần hoàn tất.
- Phân biệt dữ liệu mới, lần thử và lần review hợp lệ.
- Có tiêu chí hoàn tất và cách thể hiện kết quả một phần.
- Có reviewer, bên chuyển cấp và trách nhiệm xử lý dữ liệu thiếu.
- Giữ hạn gốc và lịch sử quá hạn khi gia hạn hoặc hoàn tất muộn.
- Tách review hoàn tất khỏi khắc phục đã được xác minh.
- Đo bằng đơn vị, mẫu số và scope có thể đối chiếu.

Review frequency có giá trị khi giúp phát hiện sai lệch đúng lúc và buộc thông tin inventory, ownership cùng nhu cầu quyền được xem lại bằng bằng chứng. Lịch phù hợp kết hợp **chu kỳ theo rủi ro, sự kiện thay đổi và kết quả có thể truy vết**, thay vì chỉ tạo thêm ngày xác nhận trên danh mục.
