# Xác định tín hiệu dừng, quay lui hoặc khôi phục theo kế hoạch

Trong module **VALIDATION_TESTING_STRATEGY**, phát hành phần mềm không kết thúc ở thời điểm triển khai hoàn tất. Sau khi bản mới nhận lưu lượng hoặc bắt đầu xử lý dữ liệu thật, nhóm cần quan sát các tín hiệu cho biết hệ thống đang hoạt động đúng, có rủi ro cần ngăn chặn hay đã xảy ra sự cố cần phục hồi. Nếu không xác định trước điều kiện dừng, quay lui và khôi phục, quyết định thường bị đưa ra muộn, thiếu nhất quán hoặc dựa vào cảm tính khi áp lực sự cố tăng cao.

**Tín hiệu dừng (stop signal)** là điều kiện đã định nghĩa cho biết cần dừng tiến trình phát hành, ngăn tăng thêm lưu lượng hoặc tạm ngừng một hoạt động để đánh giá. **Quay lui (rollback)** là đưa phiên bản, cấu hình hoặc trạng thái triển khai về một trạng thái trước đó đã biết là an toàn, khi việc quay lại còn tương thích và có thể thực hiện. **Khôi phục (recovery)** là tập hành động đưa dịch vụ, dữ liệu và hoạt động nghiệp vụ về trạng thái có thể vận hành chấp nhận được; việc khôi phục có thể cần rollback, forward fix, restore dữ liệu hoặc giao dịch bù trừ.

Ba hành động có liên quan nhưng không đồng nghĩa. Dừng rollout có thể đủ để ngăn tác động lan rộng trong khi điều tra. Rollback có thể khôi phục ứng dụng nhưng không tự hoàn tác giao dịch hoặc dữ liệu đã thay đổi. Khôi phục có thể cần giữ phiên bản mới và sửa tiến về phía trước nếu schema hoặc dữ liệu không thể quay lại an toàn.

Bài học này hướng dẫn cách xác định tín hiệu dừng theo kỹ thuật và nghiệp vụ, thiết lập ngưỡng và cửa sổ quan sát, lựa chọn rollback hoặc recovery, phân định quyền quyết định, chuẩn bị runbook, kiểm tra tính sẵn sàng của phương án và ghi nhận bằng chứng sau sự cố. Mục tiêu là giúp nhóm phản ứng nhanh nhưng có kiểm soát, hạn chế tác động đến người dùng và bảo toàn dữ liệu.

## 1. Phân biệt dừng, quay lui và khôi phục

### 1.1. Dừng (stop / halt)

Dừng là hành động ngăn một bước tiếp theo hoặc hạn chế hoạt động đang diễn ra để tránh rủi ro tăng thêm. Tùy tình huống, dừng có thể là:

- Dừng promotion sang môi trường tiếp theo.
- Dừng tăng tỷ lệ traffic trong canary.
- Tạm ngừng rollout các instance còn lại.
- Tắt feature flag hoặc kill switch đã được thiết kế.
- Tạm dừng một job, consumer hoặc scheduler gây tác dụng phụ.
- Ngừng nhận một loại request hoặc giao dịch mới.
- Dừng migration trước bước không thể đảo ngược.
- Tạm ngừng một quy trình phát hành để xác minh bằng chứng.

Dừng không nhất thiết đưa hệ thống về trạng thái trước đó. Nó chủ yếu ngăn tình trạng xấu đi và tạo thời gian để đánh giá. Ví dụ, nếu canary có tỷ lệ lỗi tăng vượt ngưỡng, dừng tăng traffic giúp giới hạn số người dùng tiếp xúc trong khi nhóm xác minh nguyên nhân.

Cần xác định rõ phạm vi dừng. Dừng toàn bộ hệ thống có thể gây tác động lớn hơn việc dừng một tính năng, consumer hoặc một vùng triển khai.

### 1.2. Quay lui (rollback)

Rollback đưa một thành phần về phiên bản hoặc cấu hình trước đó. Ví dụ:

- Triển khai lại image digest trước đó.
- Chuyển traffic về blue environment.
- Khôi phục cấu hình đã biết là ổn định.
- Tắt feature flag của chức năng mới.
- Hủy một rollout đang dở và giữ các instance cũ phục vụ.

Rollback phù hợp khi phiên bản trước còn tương thích với dữ liệu, giao thức và các thành phần đang chạy. Nó có thể không phù hợp nếu phiên bản mới đã thay đổi schema theo cách không tương thích, đã ghi dữ liệu mới mà phiên bản cũ không đọc được, hoặc đã tạo tác dụng phụ ở hệ thống ngoài.

Rollback ứng dụng không tự động rollback database, message, giao dịch tài chính, email đã gửi hoặc hành động bên ngoài. Những tác dụng phụ này cần phương án xử lý riêng.

### 1.3. Khôi phục (recovery)

Recovery là mục tiêu đưa dịch vụ và nghiệp vụ về trạng thái chấp nhận được sau lỗi. Tùy sự cố, recovery có thể bao gồm:

- Rollback ứng dụng hoặc cấu hình.
- Forward fix bằng bản sửa mới.
- Restore database hoặc file từ backup/snapshot.
- Replay event hoặc xử lý lại hàng đợi.
- Giao dịch bù trừ để sửa tác dụng phụ.
- Đối soát và sửa các bản ghi sai.
- Chuyển traffic sang vùng hoặc cụm dự phòng.
- Khôi phục secret, certificate hoặc quyền truy cập.
- Bật lại dịch vụ sau khi xác minh điều kiện an toàn.

Recovery tập trung vào kết quả cuối: dịch vụ hoạt động, dữ liệu nhất quán và quy trình nghiệp vụ được kiểm soát. Nó có thể cần nhiều bước hơn rollback và không nhất thiết quay về đúng phiên bản cũ.

### 1.4. So sánh nhanh

| Hành động | Câu hỏi chính | Mục đích | Ví dụ |
|---|---|---|---|
| Stop | Có cần ngăn bước tiếp theo hoặc tác động lan rộng không? | Giới hạn rủi ro | Dừng canary ở 10% traffic |
| Rollback | Có thể trở về phiên bản/cấu hình trước an toàn không? | Loại bỏ thay đổi gây lỗi | Deploy lại image digest trước |
| Recovery | Cần làm gì để dịch vụ và dữ liệu trở lại trạng thái chấp nhận được? | Khôi phục hoạt động | Restore, replay hoặc giao dịch bù trừ |

Thông thường trình tự có thể là phát hiện tín hiệu, dừng mở rộng, đánh giá, rồi rollback hoặc recovery. Tuy nhiên, với sự cố đang gây nguy hiểm hoặc mất dữ liệu, cần kích hoạt quy trình ứng phó khẩn cấp theo quyền đã quy định.

## 2. Xác định các tín hiệu cần dừng

### 2.1. Tín hiệu kỹ thuật

Các tín hiệu kỹ thuật có thể cho thấy bản triển khai làm suy giảm khả năng vận hành:

- Tỷ lệ lỗi request tăng bất thường.
- Latency p95 hoặc p99 vượt ngưỡng đã duyệt.
- Tỷ lệ timeout hoặc retry tăng.
- Crash, restart hoặc container không sẵn sàng.
- CPU, RAM, connection pool hoặc disk gần cạn.
- Queue backlog tăng nhanh hoặc consumer không theo kịp.
- Database replication lag hoặc lỗi transaction tăng.
- Liveness/readiness liên tục thất bại.
- Tỷ lệ deploy failure hoặc instance unhealthy vượt ngưỡng.
- Network error, DNS hoặc TLS handshake bất thường.
- Số lượng thread, file handle hoặc connection tăng không kiểm soát.

Không phải mọi metric bất thường đều cần rollback. Cần liên hệ tín hiệu với tác động, baseline và ngưỡng đã thống nhất. Một spike ngắn trong quá trình warm-up có thể khác với xu hướng kéo dài gây ảnh hưởng người dùng.

### 2.2. Tín hiệu nghiệp vụ

Một bản phát hành có thể có metrics kỹ thuật bình thường nhưng làm sai kết quả nghiệp vụ. Các tín hiệu cần quan sát gồm:

- Tỷ lệ thanh toán thành công giảm.
- Giao dịch trùng hoặc sai số tiền tăng.
- Đơn hàng không chuyển trạng thái như mong đợi.
- Tồn kho bị âm hoặc không khớp.
- Tỷ lệ hoàn tiền, hủy hoặc từ chối bất thường.
- Dữ liệu bị mất, sai lệch hoặc không nhất quán.
- Quy trình phê duyệt hoặc đối soát bị gián đoạn.
- Số lượng yêu cầu hỗ trợ tăng mạnh.
- Hành trình cốt lõi không thể hoàn tất.

Các chỉ số nghiệp vụ cần có định nghĩa và nguồn dữ liệu đáng tin cậy. Ví dụ, tỷ lệ thanh toán thành công phải xác định mẫu số, loại giao dịch và cách xử lý retry.

### 2.3. Tín hiệu bảo mật, quyền riêng tư và tuân thủ

Một số tín hiệu cần kích hoạt dừng hoặc escalation ngay theo chính sách, kể cả khi số người dùng bị ảnh hưởng chưa rõ:

- Người dùng truy cập được dữ liệu ngoài quyền.
- Secret, token hoặc dữ liệu nhạy cảm bị lộ.
- Xác thực hoặc phân quyền bị bỏ qua.
- Audit log không ghi nhận hoạt động bắt buộc.
- Mã hóa hoặc xác minh chứng thư không hoạt động đúng.
- Có dấu hiệu khai thác lỗ hổng hoặc truy cập trái phép.
- Dữ liệu được lưu hoặc truyền sai phạm vi được phép.
- Một quy trình vi phạm yêu cầu pháp lý hoặc chính sách bắt buộc.

Các tín hiệu này cần được chuyển đến nhóm security, privacy hoặc compliance theo quy trình. Không chờ đến khi có thống kê đầy đủ mới giới hạn tác động nếu chính sách yêu cầu hành động ngay.

### 2.4. Tín hiệu từ người dùng và vận hành

Nguồn tín hiệu khác gồm:

- Ticket hỗ trợ tăng đột biến.
- Báo cáo từ khách hàng hoặc nhân viên vận hành.
- Synthetic monitoring thất bại.
- Alert từ hệ thống quan sát.
- Nhân viên trực phát hiện hành vi bất thường.
- Đối tác thông báo lỗi tích hợp.
- Dashboard nghiệp vụ cho thấy xu hướng bất thường.
- Sự cố tương tự xuất hiện trên nhiều khu vực hoặc nhóm người dùng.

Một báo cáo đơn lẻ không phải lúc nào cũng đủ để xác định nguyên nhân, nhưng có thể là tín hiệu cần điều tra hoặc kích hoạt ngưỡng bảo vệ. Cần có kênh tiếp nhận và quy tắc xác minh.

### 2.5. Tín hiệu về chất lượng của chính bằng chứng

Đôi khi cần dừng promotion vì không còn khả năng xác minh an toàn:

- Monitoring hoặc alerting quan trọng không hoạt động.
- Không xác định được version đang phục vụ.
- Artifact digest không khớp với bản đã kiểm thử.
- Thiếu log hoặc trace cho hành trình trọng yếu.
- Test bắt buộc bị blocked hoặc không hợp lệ.
- Nguồn dữ liệu đo mất hoặc sai lệch.
- Không thể xác định phạm vi tác động của thay đổi.

Không có bằng chứng không đồng nghĩa sản phẩm chắc chắn lỗi, nhưng có thể khiến quyết định phát hành không đủ căn cứ. Khi tiêu chí bắt buộc chưa được xác minh, cần dừng gate tương ứng hoặc yêu cầu quyết định ngoại lệ theo thẩm quyền.

## 3. Định nghĩa ngưỡng dừng có thể hành động

### 3.1. Đặt ngưỡng trước khi triển khai

Mỗi tín hiệu cần có:

- Metric hoặc sự kiện được theo dõi.
- Nguồn dữ liệu.
- Baseline hoặc mức bình thường.
- Ngưỡng cảnh báo và ngưỡng dừng.
- Cửa sổ thời gian.
- Số lượng mẫu tối thiểu nếu phù hợp.
- Phạm vi áp dụng: toàn hệ thống, một vùng, một tenant hoặc canary.
- Người hoặc hệ thống chịu trách nhiệm hành động.
- Hành động khi ngưỡng bị vượt.

Ví dụ, “latency cao” không đủ rõ. Có thể định nghĩa “p95 end-to-end latency của luồng checkout vượt ngưỡng đã duyệt trong 5 phút liên tục với số request tối thiểu, so với baseline cùng loại traffic”. Ngưỡng cụ thể cần dựa trên SLO và đặc điểm hệ thống, không sao chép một con số chung cho mọi dịch vụ.

### 3.2. Dùng cả ngưỡng tuyệt đối và ngưỡng tương đối

- **Ngưỡng tuyệt đối:** giá trị vượt giới hạn đã xác định, ví dụ error rate lớn hơn mức cho phép.
- **Ngưỡng tương đối:** thay đổi so với baseline, ví dụ tỷ lệ lỗi tăng gấp nhiều lần so với nhóm đối chứng.
- **Ngưỡng nghiệp vụ:** số giao dịch sai, số bản ghi không nhất quán hoặc tỷ lệ hoàn tất giảm.
- **Ngưỡng chính sách:** sự kiện bảo mật hoặc vi phạm bắt buộc phải escalation.

Ngưỡng tương đối hữu ích khi tải và traffic thay đổi theo giờ. Ngưỡng tuyệt đối cần thiết khi có giới hạn an toàn hoặc SLO. Có thể dùng kết hợp để giảm false alarm nhưng không bỏ qua sự cố nghiêm trọng.

### 3.3. Chọn cửa sổ quan sát và số mẫu

Một metric có thể dao động tự nhiên. Nếu dừng theo một mẫu đơn lẻ, nhóm có thể phản ứng quá mức; nếu đợi quá lâu, tác động có thể lan rộng.

Cần quy định:

- Cửa sổ đo ngắn và dài nếu có.
- Số mẫu tối thiểu.
- Thời gian liên tục vượt ngưỡng.
- Cách xử lý traffic thấp.
- Cách xử lý spike khi khởi động hoặc warm-up.
- Điều kiện dừng ngay không cần chờ cửa sổ.

Với sự cố dữ liệu hoặc bảo mật, một sự kiện được xác minh có thể đủ để dừng ngay. Không nên áp dụng cửa sổ trung bình dài làm chậm phản ứng đối với tín hiệu có hậu quả nghiêm trọng.

### 3.4. Phân biệt cảnh báo, điều tra và dừng

Có thể thiết lập ba mức:

| Mức | Ý nghĩa | Hành động |
|---|---|---|
| Warning | Có dấu hiệu lệch baseline nhưng chưa vượt điều kiện dừng | Theo dõi, xác minh và tăng tần suất quan sát |
| Investigate | Có khả năng ảnh hưởng hoặc bằng chứng chưa rõ | Dừng mở rộng, triage nhanh, kiểm tra chéo |
| Stop / Abort | Đã vượt điều kiện dừng hoặc có sự kiện bắt buộc | Dừng rollout/traffic/hoạt động liên quan và kích hoạt quy trình xử lý |

Tên mức có thể khác theo tổ chức. Quan trọng là mỗi mức có hành động, người nhận và thời gian phản hồi rõ ràng.

### 3.5. Tránh ngưỡng gây dao động liên tục

Nếu hệ thống tự động dừng và tiếp tục rollout mỗi khi metric dao động quanh một ngưỡng, quyết định có thể không ổn định. Có thể dùng:

- Hysteresis: ngưỡng dừng và ngưỡng cho phép tiếp tục khác nhau.
- Cooldown: khoảng chờ trước khi đánh giá lại.
- Số mẫu tối thiểu.
- Điều kiện phục hồi liên tục trong một cửa sổ.
- Quyết định thủ công với tín hiệu có rủi ro cao.

Ví dụ, dừng khi error rate vượt ngưỡng A; chỉ xem xét tiếp tục khi metric giảm dưới ngưỡng B thấp hơn A trong một khoảng ổn định. Các ngưỡng phải được thiết kế theo hành vi thực tế của hệ thống.

## 4. Xác định khi nào cần dừng rollout hoặc hoạt động

### 4.1. Dừng tăng traffic trong canary

Trong canary, phiên bản mới chỉ nhận một phần lưu lượng. Khi có tín hiệu bất thường:

1. Dừng tăng tỷ lệ traffic.
2. Giữ hoặc giảm traffic theo chính sách.
3. So sánh canary với nhóm baseline hoặc phiên bản cũ.
4. Kiểm tra metrics kỹ thuật và nghiệp vụ.
5. Quyết định tiếp tục quan sát, rollback hoặc recovery.

Không cần đợi toàn bộ rollout hoàn tất mới đánh giá. Canary chỉ có giá trị khi có khả năng giới hạn tác động và đủ dữ liệu so sánh.

### 4.2. Dừng rollout nhiều instance

Với rolling deployment, nếu một số instance mới lỗi:

- Dừng triển khai các instance còn lại.
- Xác định instance cũ còn khỏe hay không.
- Kiểm tra traffic đã được gửi đến instance mới chưa.
- Xác định trạng thái migration và dữ liệu dùng chung.
- Đánh giá khả năng rollback từng phần hoặc toàn bộ.
- Giữ bằng chứng của phiên bản và thời điểm xảy ra.

Nếu instance cũ và mới cùng phục vụ, cần xem xét tương thích schema, cache, message và session trước khi chuyển traffic.

### 4.3. Tắt tính năng bằng feature flag hoặc kill switch

Feature flag có thể là cách giảm thiểu nhanh nếu:

- Flag được thiết kế để tắt an toàn.
- Hành vi khi tắt đã được kiểm thử.
- Việc tắt không làm dữ liệu ở trạng thái dở dang.
- Có thể áp dụng theo tenant, khu vực hoặc nhóm người dùng.
- Có log và người chịu trách nhiệm thay đổi.

Kill switch không phải giải pháp chung cho mọi lỗi. Nếu lỗi nằm trong luồng dữ liệu nền hoặc tác dụng phụ đã xảy ra, tắt giao diện có thể không ngăn được xử lý tiếp tục ở backend. Cần xác định đúng thành phần và đường đi của dữ liệu.

### 4.4. Dừng job, consumer hoặc migration

Với tác vụ nền:

- Dừng consumer nếu đang tạo dữ liệu sai hoặc tác dụng phụ trùng.
- Tạm dừng scheduler nếu job lặp gây tải hoặc thay đổi trạng thái sai.
- Dừng migration ở checkpoint an toàn nếu có thể.
- Giữ queue và offset để không mất dấu sự kiện.
- Xác định message đang xử lý và message chưa xử lý.
- Kiểm tra tính idempotent trước khi chạy lại.

Không xóa queue hoặc reset offset để “làm sạch” sự cố nếu chưa hiểu tác động. Việc đó có thể gây mất dữ liệu hoặc xử lý trùng.

### 4.5. Dừng toàn hệ thống khi cần thiết

Dừng toàn bộ dịch vụ có thể cần thiết khi tiếp tục hoạt động sẽ gây mất dữ liệu, vi phạm bảo mật hoặc hậu quả lớn hơn. Tuy nhiên, cần xem xét:

- Có thể cô lập một tính năng hoặc vùng không?
- Có cần giữ endpoint read-only?
- Các dịch vụ phụ thuộc có cần dừng theo thứ tự?
- Tác động đến giao dịch đang xử lý là gì?
- Người dùng sẽ nhận thông báo nào?
- Có thể bảo toàn dữ liệu và bằng chứng không?
- Điều kiện nào cho phép khởi động lại?

Quyết định dừng toàn hệ thống cần theo quyền và runbook đã được xác định.

## 5. Quyết định rollback hay forward fix

### 5.1. Khi rollback thường phù hợp

Rollback có thể phù hợp khi:

- Phiên bản trước đã được xác minh ổn định.
- Artifact trước còn sẵn và có thể triển khai chính xác.
- Schema và dữ liệu vẫn tương thích.
- Thay đổi mới là nguyên nhân có khả năng cao.
- Rollback giảm tác động nhanh hơn sửa nóng.
- Phụ thuộc và giao thức chưa bị thay đổi theo cách không tương thích.

Cần xác minh digest hoặc version của artifact cũ, không dựa vào tag có thể thay đổi.

### 5.2. Khi rollback có thể không an toàn

Không nên rollback máy móc nếu:

- Migration đã loại bỏ hoặc biến đổi dữ liệu theo cách phiên bản cũ không đọc được.
- Phiên bản mới đã tạo event hoặc message mà consumer cũ không hiểu.
- Đã phát sinh giao dịch thanh toán, hoàn tiền hoặc thông báo bên ngoài.
- Schema thay đổi không tương thích.
- Secret, certificate hoặc endpoint đã được luân chuyển.
- Rollback sẽ đưa lỗ hổng bảo mật đã biết trở lại.
- Phiên bản cũ không còn tương thích với dịch vụ phụ thuộc hiện tại.

Trong các trường hợp này, forward fix, compatibility mode hoặc recovery có thể an toàn hơn.

### 5.3. Forward fix

Forward fix là triển khai bản sửa tiến về phía trước thay vì quay lại phiên bản cũ. Có thể chọn khi:

- Dữ liệu hoặc schema đã chuyển sang trạng thái mới.
- Bản cũ không tương thích.
- Lỗi có thể được sửa nhanh và kiểm chứng đủ.
- Rollback có nguy cơ gây hỏng dữ liệu lớn hơn.
- Cần giữ một thay đổi nền tảng đã được triển khai.

Forward fix vẫn cần kiểm soát: dừng rollout nếu cần, xác minh artifact, kiểm tra phạm vi, có kế hoạch rollback/recovery cho chính bản sửa và theo dõi sau triển khai.

### 5.4. Quy tắc ra quyết định

| Điều kiện | Hướng xem xét |
|---|---|
| Artifact cũ tương thích, đã biết ổn định, rollback an toàn | Rollback có thể là lựa chọn ưu tiên |
| Schema/data đã thay đổi không tương thích | Đánh giá forward fix hoặc recovery dữ liệu |
| Tác dụng phụ bên ngoài đã xảy ra | Cần đối soát hoặc giao dịch bù trừ; rollback code không đủ |
| Lỗi chỉ nằm trong một tính năng có kill switch an toàn | Tắt tính năng để giới hạn tác động, sau đó điều tra |
| Nguyên nhân chưa rõ nhưng tác động đang tăng | Dừng mở rộng, cô lập và thu thập bằng chứng trước quyết định tiếp |
| Sự cố bảo mật hoặc dữ liệu đang diễn ra | Kích hoạt quy trình chuyên môn và containment ngay |

Bảng chỉ hỗ trợ thảo luận. Quyết định cuối cần dựa trên kiến trúc, dữ liệu, quyền và runbook của hệ thống cụ thể.

## 6. Lập kế hoạch khôi phục dữ liệu và nghiệp vụ

### 6.1. Phân biệt khôi phục dịch vụ với khôi phục dữ liệu

Dịch vụ có thể đã hoạt động trở lại nhưng dữ liệu vẫn sai. Ví dụ, API thanh toán trả response bình thường sau rollback, nhưng các giao dịch đã tạo trùng trong khoảng thời gian sự cố vẫn cần đối soát.

Kế hoạch cần xác định riêng:

- Khôi phục khả năng phục vụ.
- Khôi phục hoặc sửa dữ liệu.
- Xử lý giao dịch đang dở.
- Replay hoặc loại bỏ event theo quy tắc.
- Khôi phục quyền và cấu hình.
- Xác minh các tác dụng phụ với hệ thống ngoài.
- Thông báo và hỗ trợ người dùng bị ảnh hưởng.

### 6.2. Backup, snapshot và điểm phục hồi

Trước thay đổi có rủi ro dữ liệu, xác định:

- Backup gần nhất và trạng thái thành công.
- Snapshot hoặc checkpoint phù hợp.
- Thời gian tạo và phạm vi dữ liệu.
- Cách kiểm tra tính toàn vẹn.
- Quyền truy cập và vị trí lưu.
- Thời gian cần để restore.
- Khả năng khôi phục vào môi trường cô lập để kiểm tra trước.

Backup chưa được thử restore không phải bằng chứng chắc chắn rằng có thể khôi phục khi cần. Cần kiểm tra quy trình restore định kỳ.

### 6.3. RPO và RTO

Hai mục tiêu thường dùng trong kế hoạch phục hồi:

- **RPO (Recovery Point Objective):** lượng mất dữ liệu tối đa theo thời gian mà tổ chức có thể chấp nhận trong tình huống phục hồi.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ hoặc hoạt động ở mức đã định.

Ví dụ, RPO 15 phút có nghĩa tổ chức đặt mục tiêu giới hạn điểm mất dữ liệu ở mức tương đương tối đa 15 phút theo cách đo đã thống nhất. RTO 2 giờ là mục tiêu thời gian khôi phục dịch vụ. Đây là mục tiêu cần xác nhận với chủ sở hữu nghiệp vụ và vận hành; không phải cam kết tự động mà công cụ backup bảo đảm.

Cần xác định phạm vi RTO: toàn bộ hệ thống, một chức năng quan trọng hay mức dịch vụ tối thiểu.

### 6.4. Restore và kiểm tra tính nhất quán

Khi restore:

1. Xác định điểm phục hồi và phạm vi dữ liệu.
2. Cô lập nguồn ghi nếu cần để tránh ghi mới vào trạng thái đang phục hồi.
3. Thực hiện restore theo runbook.
4. Kiểm tra schema, ràng buộc và quan hệ.
5. Đối chiếu số lượng, tổng giá trị hoặc checksum phù hợp.
6. Xác định dữ liệu phát sinh sau điểm backup.
7. Replay hoặc xử lý bù theo quy tắc.
8. Xác nhận với chủ sở hữu dữ liệu trước khi mở lại ghi.

Không mở lại traffic ghi chỉ vì database khởi động thành công. Cần xác minh dữ liệu và các phụ thuộc liên quan.

### 6.5. Giao dịch bù trừ và đối soát

Với tác dụng phụ không thể xóa hoặc rollback trực tiếp, có thể cần hành động bù trừ:

- Hủy hoặc hoàn giao dịch theo quy trình tài chính.
- Phát event điều chỉnh.
- Sửa trạng thái đơn hoặc tồn kho.
- Gửi thông báo đính chính.
- Đối soát với provider hoặc đối tác.
- Đánh dấu bản ghi cần xử lý thủ công.

Giao dịch bù trừ cần idempotent hoặc có cơ chế ngăn thực hiện lặp. Phải lưu liên kết giữa hành động gốc, hành động bù và lý do.

## 7. Chuẩn bị runbook dừng, rollback và recovery

### 7.1. Nội dung tối thiểu của runbook

Một runbook nên có:

- Tên dịch vụ, thành phần và môi trường.
- Tín hiệu kích hoạt và ngưỡng.
- Phạm vi có thể dừng hoặc cô lập.
- Người phát hiện, người điều phối và người có quyền quyết định.
- Lệnh hoặc thao tác đã được kiểm chứng.
- Artifact hoặc cấu hình phiên bản trước.
- Phụ thuộc và thứ tự thao tác.
- Cách bảo toàn log, trace và dữ liệu.
- Phương án rollback hoặc forward fix.
- Phương án restore/reconcile nếu có.
- Điều kiện xác minh thành công.
- Điều kiện mở lại traffic hoặc job.
- Kênh thông báo và escalation.
- Hướng xử lý nếu runbook thất bại.

Runbook phải cụ thể cho hệ thống. Không dùng lệnh minh họa chưa được xác minh để thực hiện trên production.

### 7.2. Phân định vai trò và quyền quyết định

Có thể phân công:

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander / Release owner | Điều phối, quyết định theo quyền và giữ liên lạc |
| On-call / Operations | Thực hiện containment, rollout, rollback và recovery |
| Developer / Service owner | Phân tích lỗi, tương thích phiên bản và phương án sửa |
| DBA / Data owner | Đánh giá backup, restore, migration và tính nhất quán |
| QA / Test lead | Cung cấp bằng chứng, xác minh hành vi và kiểm thử sau phục hồi |
| Security / Privacy | Xử lý tín hiệu bảo mật, dữ liệu nhạy cảm và nghĩa vụ liên quan |
| Product / Business owner | Đánh giá tác động nghiệp vụ và chấp nhận rủi ro theo thẩm quyền |
| Communications / Support | Cập nhật thông tin cho người dùng và nhóm liên quan |

Trong sự cố khẩn cấp, người điều phối cần có quyền kích hoạt hành động containment đã được phê duyệt mà không phải tìm nhiều người để xin từng thao tác. Quyền rollback, restore và thay đổi dữ liệu cần được xác định trước.

### 7.3. Chuẩn bị artifact và cấu hình trước phát hành

Lưu sẵn:

- Digest của artifact hiện tại và phiên bản trước.
- Manifest và release metadata.
- Cấu hình có version.
- Tham chiếu secret an toàn.
- Migration scripts và trạng thái tương thích.
- Runbook đã review.
- Backup/snapshot reference.
- Danh sách phụ thuộc và owner.
- Smoke test sau rollback.
- Các dashboard và alert cần theo dõi.

Không để đến lúc sự cố mới tìm artifact cũ hoặc phát hiện rằng phiên bản trước đã bị xóa khỏi registry.

### 7.4. Xác định điều kiện hoàn tất recovery

Recovery chỉ hoàn tất khi tiêu chí được xác nhận, ví dụ:

- Dịch vụ sẵn sàng và error rate trở về ngưỡng.
- Hành trình nghiệp vụ cốt lõi hoạt động.
- Dữ liệu và giao dịch đã được đối soát.
- Queue không còn backlog bất thường hoặc có kế hoạch xử lý.
- Không còn tác dụng phụ đang tiếp diễn.
- Monitoring và alert hoạt động.
- Chủ sở hữu dịch vụ và nghiệp vụ xác nhận mức vận hành.
- Rủi ro còn lại và hành động tiếp theo được ghi nhận.

Không chỉ dựa vào việc deployment thành công hoặc pod healthy để tuyên bố phục hồi hoàn tất.

## 8. Quy trình ứng phó từ phát hiện đến phục hồi

### 8.1. Các bước xử lý

Một quy trình khái quát:

1. **Phát hiện:** alert, test, monitoring hoặc báo cáo người dùng kích hoạt tín hiệu.
2. **Xác nhận nhanh:** kiểm tra nguồn dữ liệu, phạm vi và khả năng ảnh hưởng.
3. **Containment:** dừng rollout, giảm traffic, tắt tính năng hoặc dừng job theo runbook.
4. **Điều phối:** chỉ định incident commander, owner và kênh trao đổi.
5. **Đánh giá lựa chọn:** rollback, forward fix, restore hoặc giao dịch bù trừ.
6. **Thực hiện:** theo thứ tự, quyền và checkpoint đã xác định.
7. **Xác minh:** smoke, functional, data integrity và monitoring.
8. **Mở lại có kiểm soát:** tăng traffic hoặc bật job theo từng bước.
9. **Theo dõi:** quan sát đủ cửa sổ và chỉ số đã định.
10. **Kết thúc và học hỏi:** ghi timeline, bằng chứng, nguyên nhân và hành động phòng ngừa.

### 8.2. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Phát hiện tín hiệu bất thường] --> B{Tín hiệu có hợp lệ hoặc bắt buộc xử lý ngay?}
    B -- Không rõ --> C[Dừng mở rộng và xác minh dữ liệu]
    C --> D{Có nguy cơ tác động tiếp diễn?}
    B -- Có --> D
    D -- Có --> E[Containment: dừng traffic, flag, job hoặc rollout]
    D -- Không --> F[Theo dõi và điều tra trong giới hạn]
    E --> G{Rollback có an toàn và tương thích?}
    G -- Có --> H[Rollback theo runbook]
    G -- Không --> I[Forward fix / Restore / Compensation]
    H --> J[Kiểm tra dịch vụ và dữ liệu]
    I --> J
    J --> K{Tiêu chí recovery đạt?}
    K -- Không --> L[Tiếp tục recovery hoặc escalation]
    L --> J
    K -- Có --> M[Mở lại có kiểm soát và theo dõi]
    M --> N[Đóng incident và cải tiến]
~~~

Sơ đồ là hướng dẫn khái quát. Sự cố bảo mật, an toàn hoặc mất dữ liệu có thể yêu cầu quy trình chuyên biệt và quyết định dừng ngay theo chính sách.

### 8.3. Bảo toàn bằng chứng trong khi xử lý

Trong quá trình containment, không xóa log, reset queue hoặc ghi đè dữ liệu cần điều tra nếu chưa xác định cách bảo toàn. Thu thập:

- Release ID, build và artifact digest.
- Thời điểm phát hiện và timeline.
- Metric trước, trong và sau sự cố.
- Log, trace, event và correlation ID.
- Phạm vi người dùng, tenant hoặc giao dịch.
- Các thao tác đã thực hiện và người thực hiện.
- Kết quả rollback, restore hoặc compensation.
- Các giả định và thông tin chưa xác minh.

Bảo toàn bằng chứng phải tuân thủ chính sách bảo mật và quyền riêng tư. Không sao chép secret hoặc dữ liệu cá nhân vào kênh không được phép.

## 9. Kiểm thử và diễn tập kế hoạch

### 9.1. Kiểm thử rollback trước khi cần

Một kế hoạch chỉ tồn tại trên tài liệu chưa đủ. Cần xác minh:

- Có thể lấy đúng artifact trước không?
- Thời gian rollback thực tế là bao lâu?
- Traffic có chuyển về phiên bản cũ đúng không?
- Phiên bản cũ có tương thích schema và message không?
- Health, smoke và hành trình chính có đạt sau rollback không?
- Có tác dụng phụ nào vẫn còn?
- Ai có quyền và thao tác được trong thời gian yêu cầu không?

Thử trong môi trường phù hợp và ghi giới hạn. Không cần tạo sự cố production để chứng minh runbook hoạt động.

### 9.2. Diễn tập restore và phục hồi dữ liệu

Định kỳ thực hiện restore thử trong môi trường cô lập:

- Chọn backup hoặc snapshot.
- Thực hiện restore theo runbook.
- Đo thời gian thực tế.
- Kiểm tra tính toàn vẹn và đối soát.
- Xác minh RPO/RTO mục tiêu.
- Thử replay hoặc compensation khi phù hợp.
- Ghi lỗi và cập nhật tài liệu.

Backup thành công không bảo đảm restore thành công. Restore test là bằng chứng cần thiết về khả năng phục hồi.

### 9.3. Tabletop exercise

Tabletop là buổi diễn tập theo kịch bản, trong đó các vai trò cùng đi qua quyết định mà không nhất thiết thao tác trên hệ thống thật.

Kịch bản có thể gồm:

- Canary tăng error rate.
- Thanh toán bị ghi nhận trùng.
- Migration thất bại giữa chừng.
- Secret bị lộ.
- Database mất khả năng ghi.
- Queue backlog tăng nhanh.
- Monitoring mất dữ liệu trong lúc rollout.

Đánh giá người nhận alert, quyền quyết định, khả năng tìm runbook, thông tin liên lạc và cách ghi nhận quyết định.

### 9.4. Tiêu chí đánh giá diễn tập

- Tín hiệu được phát hiện đúng và đủ nhanh.
- Người chịu trách nhiệm được xác định.
- Quyết định stop/rollback/recovery phù hợp.
- Thao tác có thể thực hiện với quyền sẵn có.
- Dữ liệu và bằng chứng được bảo toàn.
- RTO/RPO mục tiêu được kiểm tra.
- Recovery được xác minh bằng tiêu chí rõ.
- Thông báo và cập nhật trạng thái được thực hiện.
- Bài học được chuyển thành action item có owner và hạn.

## 10. Ví dụ tổng hợp theo tình huống

### 10.1. Canary làm tăng lỗi checkout

**Tình huống:** phiên bản mới nhận 10% traffic. Error rate của checkout tăng vượt ngưỡng trong cửa sổ đã định; phiên bản cũ ổn định.

**Hành động:**

1. Dừng tăng traffic.
2. So sánh metrics và trace của canary với baseline.
3. Xác minh lỗi có liên quan đến bản mới.
4. Nếu artifact cũ tương thích và rollback an toàn, chuyển traffic về bản cũ.
5. Chạy smoke và hành trình checkout trên phiên bản cũ.
6. Theo dõi error rate và giao dịch tồn đọng.

**Bằng chứng hoàn tất:** đúng version cũ đang phục vụ, tỷ lệ lỗi trở về ngưỡng, hành trình nghiệp vụ đạt và không còn traffic đến bản lỗi ngoài phạm vi kiểm tra.

### 10.2. Giao dịch thanh toán bị tạo trùng

**Tình huống:** sau triển khai, retry của client tạo hai giao dịch cho cùng một đơn.

**Hành động:**

1. Dừng hoặc giới hạn luồng retry gây lỗi theo cơ chế an toàn.
2. Cân nhắc tắt phương thức thanh toán hoặc tính năng bị ảnh hưởng.
3. Giữ log, idempotency key, transaction ID và provider reference.
4. Đối soát số giao dịch với provider.
5. Rollback code nếu tương thích, hoặc triển khai forward fix nếu schema/data đã thay đổi.
6. Xử lý giao dịch trùng bằng quy trình hoàn/hủy được phê duyệt.
7. Kiểm tra idempotency và hồi quy trước khi mở lại.

**Bằng chứng hoàn tất:** số giao dịch được đối soát, giao dịch bù trừ có liên kết, không còn tạo trùng trong test và monitoring theo dõi được.

### 10.3. Migration thất bại giữa chừng

**Tình huống:** migration đã chuyển một phần dữ liệu rồi dừng do lỗi constraint.

**Hành động:**

1. Dừng các job hoặc deployment tiếp tục ghi vào trạng thái không nhất quán.
2. Xác định checkpoint và phạm vi bản ghi đã chuyển.
3. Không tự chạy lại migration nếu chưa xác nhận tính idempotent.
4. Kiểm tra backup, snapshot và khả năng restore.
5. Chọn resume, forward repair hoặc restore theo thiết kế migration.
6. Đối chiếu số lượng, quan hệ và giá trị dữ liệu.
7. Chỉ mở lại ghi khi data owner xác nhận.

**Bằng chứng hoàn tất:** migration state rõ, dữ liệu được đối chiếu, không còn bản ghi ở trạng thái trung gian ngoài dự kiến và ứng dụng tương thích với schema.

### 10.4. Phát hiện truy cập dữ liệu trái quyền

**Tình huống:** người dùng tenant A có thể đọc dữ liệu tenant B.

**Hành động:**

1. Kích hoạt kênh security/privacy và containment ngay.
2. Tắt hoặc giới hạn endpoint/tính năng bị ảnh hưởng nếu có thể làm an toàn.
3. Bảo toàn audit log, request và phạm vi tài khoản.
4. Xác định khoảng thời gian, dữ liệu và tenant có thể bị ảnh hưởng.
5. Triển khai biện pháp sửa và kiểm tra quyền theo ma trận tenant.
6. Đánh giá nghĩa vụ thông báo theo chính sách.
7. Chỉ mở lại khi security và service owner xác nhận điều kiện.

**Bằng chứng hoàn tất:** kiểm tra truy cập trái quyền thất bại đúng như mong đợi, quyền hợp lệ vẫn hoạt động, log/audit được xác minh và quy trình xử lý dữ liệu bị ảnh hưởng đã được thực hiện.

## 11. Theo dõi sau recovery và cải tiến

### 11.1. Xác minh ổn định sau khi mở lại

Sau khi dịch vụ phục hồi, không nên lập tức kết thúc theo dõi. Xác định cửa sổ quan sát dựa trên traffic và chu kỳ nghiệp vụ:

- Error rate và latency ổn định.
- Tỷ lệ giao dịch hoàn tất trở về baseline.
- Queue backlog giảm theo kế hoạch.
- Không phát sinh lỗi dữ liệu mới.
- Tài nguyên không tiếp tục tăng bất thường.
- Alert và dashboard hoạt động.
- Không có instance hoặc consumer chạy sai phiên bản.

Với nghiệp vụ theo chu kỳ ngày hoặc tuần, cần kiểm tra cả những job không xuất hiện ngay sau khi mở lại.

### 11.2. Post-incident review

Sau sự cố, ghi nhận:

- Timeline và tín hiệu đầu tiên.
- Tác động người dùng, dữ liệu và nghiệp vụ.
- Nguyên nhân trực tiếp và yếu tố góp phần.
- Vì sao tín hiệu có hoặc không phát hiện kịp.
- Quyết định stop, rollback và recovery.
- Thời gian containment và phục hồi.
- Bằng chứng và giới hạn.
- Điều gì đã hoạt động tốt hoặc chưa tốt.
- Action item, owner và thời hạn.

Tập trung vào cải thiện hệ thống, quy trình và khả năng phát hiện; tránh quy lỗi cá nhân khi không có phân tích đầy đủ.

### 11.3. Cập nhật kế hoạch

Sau review, cập nhật:

- Ngưỡng và cửa sổ alert.
- Canary analysis và quality gate.
- Runbook và quyền truy cập.
- Kế hoạch backup/restore.
- Tương thích schema và quy trình migration.
- Feature flag và kill switch.
- Smoke test sau rollback/recovery.
- Dashboard và bằng chứng bắt buộc.
- Kịch bản diễn tập tiếp theo.

Kế hoạch cần được versioning và review khi kiến trúc, nhà cung cấp, dữ liệu hoặc quy trình phát hành thay đổi.

## 12. Những sai lầm thường gặp

1. **Chỉ định nghĩa rollback mà không có stop signal:** nhóm phát hiện vấn đề nhưng không biết khi nào dừng mở rộng.
2. **Dùng một ngưỡng chung cho mọi dịch vụ:** bỏ qua baseline, SLO và đặc điểm nghiệp vụ.
3. **Chờ quá lâu để xác minh sự cố nghiêm trọng:** làm tác động lan rộng khi đã có tín hiệu bắt buộc.
4. **Rollback tự động không kiểm tra tương thích:** phiên bản cũ có thể không đọc được schema hoặc message mới.
5. **Cho rằng rollback code hoàn tác mọi thứ:** bỏ qua giao dịch, event và tác dụng phụ bên ngoài.
6. **Không có forward-fix path:** không biết xử lý thế nào khi rollback không an toàn.
7. **Backup chưa từng restore thử:** không có bằng chứng khả năng phục hồi.
8. **Không xác định RPO/RTO:** không biết mức mất dữ liệu và thời gian dừng có thể chấp nhận.
9. **Runbook thiếu owner hoặc quyền:** sự cố bị chậm vì không rõ ai được hành động.
10. **Tắt tính năng nhưng không dừng backend job:** tác dụng phụ vẫn tiếp tục.
11. **Xóa queue hoặc dữ liệu để xử lý nhanh:** có thể làm mất bằng chứng hoặc gây mất dữ liệu.
12. **Mở lại traffic ngay sau deploy rollback:** chưa kiểm tra dữ liệu, hành trình và metrics.
13. **Không bảo toàn timeline và evidence:** khó phân tích nguyên nhân và nghĩa vụ sau sự cố.
14. **Không diễn tập:** phát hiện runbook thiếu bước hoặc quyền chỉ khi sự cố thật xảy ra.
15. **Kết thúc incident khi service healthy:** bỏ qua dữ liệu chưa đối soát hoặc job chưa hoàn tất.

## 13. Checklist xác định tín hiệu dừng, quay lui hoặc khôi phục theo kế hoạch

- [ ] Tín hiệu kỹ thuật, nghiệp vụ, bảo mật và vận hành đã được xác định.
- [ ] Mỗi tín hiệu có nguồn dữ liệu, baseline, ngưỡng và cửa sổ quan sát.
- [ ] Có điều kiện dừng ngay cho sự kiện dữ liệu, bảo mật hoặc an toàn trọng yếu.
- [ ] Warning, investigate và stop có hành động và owner rõ ràng.
- [ ] Có cơ chế dừng rollout, giảm traffic, tắt flag hoặc dừng job phù hợp.
- [ ] Artifact và cấu hình phiên bản trước có thể truy xuất.
- [ ] Đã đánh giá tương thích schema, dữ liệu, message và phụ thuộc trước rollback.
- [ ] Có lựa chọn forward fix khi rollback không an toàn.
- [ ] Kế hoạch restore, replay, reconciliation hoặc compensation được xác định khi cần.
- [ ] Backup/snapshot có kiểm tra restore và tính toàn vẹn.
- [ ] RPO, RTO và phạm vi phục hồi được chủ sở hữu xác nhận.
- [ ] Runbook có trình tự, quyền, owner, liên lạc và điều kiện hoàn tất.
- [ ] Bằng chứng, log, trace và trạng thái dữ liệu được bảo toàn.
- [ ] Recovery được xác minh bằng smoke, nghiệp vụ, dữ liệu và monitoring.
- [ ] Mở lại traffic hoặc job theo từng bước và có cửa sổ theo dõi.
- [ ] Post-incident review có action item, owner và thời hạn.
- [ ] Rollback, restore và runbook được diễn tập định kỳ.

Xác định trước tín hiệu dừng, điều kiện rollback và kế hoạch recovery giúp nhóm kiểm soát rủi ro ngay khi bản phát hành có dấu hiệu bất thường. Khi ngưỡng, quyền quyết định, tính tương thích, phương án dữ liệu và tiêu chí xác minh được chuẩn bị rõ ràng, nhóm có thể giới hạn tác động, khôi phục dịch vụ an toàn và đưa ra quyết định dựa trên bằng chứng thay vì ứng biến trong lúc sự cố diễn ra.
