# Alert theo anomaly

## 1. Cảnh báo bất thường trong IAM là gì?

**Alert theo anomaly** là cảnh báo được phát khi một hoạt động hoặc chỉ số lệch đáng kể khỏi hành vi được kỳ vọng trong ngữ cảnh đã xác định. Trong IAM, ngữ cảnh có thể là loại luồng xác thực, nhóm ứng dụng, vai trò công việc, môi trường, thời điểm hoặc lịch sử của một workload.

Ví dụ, 500 lần xác thực thất bại trong 5 phút có thể rất khác thường với một ứng dụng nội bộ nhỏ nhưng bình thường với một cổng đăng nhập quy mô lớn. Ngược lại, một lần cấp quyền quản trị ngoài quy trình ở hệ thống ít sử dụng vẫn có thể cần điều tra ngay dù tổng số sự kiện rất thấp.

Anomaly trả lời câu hỏi **“điều gì khác với kỳ vọng?”**. Nó không tự trả lời được “đây có phải tấn công không?”, “ai gây ra?” hoặc “nên chặn tài khoản nào?”. Một đợt triển khai, lỗi liên kết danh tính, thay ca làm việc hoặc dữ liệu log đến muộn đều có thể tạo tín hiệu bất thường.

Mục tiêu của cảnh báo là đưa đúng bằng chứng và ngữ cảnh tới người có thể đánh giá, với mức khẩn cấp phù hợp. Muốn làm được điều đó, cần thiết kế cả nguồn dữ liệu, baseline, điều kiện phát cảnh báo, cách giảm nhiễu và quy trình phản ứng.

## 2. Phân biệt ngưỡng cố định, bất thường và vi phạm chính sách

| Cơ chế | So sánh với điều gì? | Ví dụ trong IAM | Giới hạn chính |
|---|---|---|---|
| Ngưỡng cố định | Một mốc đã đặt trước | Tỷ lệ lỗi kỹ thuật vượt mốc vận hành | Khó phù hợp với mọi mức tải và mọi nhóm |
| Anomaly theo chuỗi thời gian | Lịch sử của cùng một thực thể hoặc nhóm | Số lần refresh token tăng mạnh so với cùng khung giờ | Cần baseline và xử lý mùa vụ, thay đổi hành vi |
| Anomaly theo nhóm tương đồng | Hành vi của một nhóm có đặc điểm gần nhau | Một workload có mẫu truy cập lệch khỏi nhóm cùng chức năng | Nhóm so sánh sai sẽ tạo kết luận sai |
| Sự mới lạ | Những đặc điểm chưa được quan sát trong phạm vi lịch sử | Workload lần đầu yêu cầu một audience | Mới không đồng nghĩa nguy hiểm |
| Vi phạm chính sách | Một điều kiện được quy định rõ | Cấp đặc quyền không có phê duyệt bắt buộc | Phụ thuộc chính sách và khả năng ghi nhận bằng chứng |

Các cơ chế này có thể bổ sung cho nhau. Một hành vi bị cấm rõ ràng không nên được cho phép chỉ vì nó xuất hiện thường xuyên và đã trở thành “bình thường” trong dữ liệu.

Tương tự, cảnh báo bất thường không thay thế giám sát độ sẵn sàng. Nếu toàn bộ nguồn xác thực ngừng phản hồi, cần có kiểm tra lỗi, timeout và sức khỏe phụ thuộc rõ ràng, thay vì chỉ chờ mô hình thống kê phát hiện.

## 3. Bắt đầu từ câu hỏi điều tra cụ thể

Một yêu cầu như “bật AI phát hiện mọi bất thường IAM” quá rộng để có thể vận hành và kiểm chứng tốt. Nên chọn những câu hỏi có nguồn dữ liệu và hành động tiếp theo rõ ràng.

| Câu hỏi | Tín hiệu có thể dùng | Ngữ cảnh cần thêm |
|---|---|---|
| Luồng đăng nhập có thay đổi bất thường không? | Số attempt, outcome, tỷ lệ thất bại, completion | Nhóm ứng dụng, phương thức, thời điểm, nguồn danh tính |
| Có nhiều chủ thể bị từ chối xác thực hơn bình thường không? | Số chủ thể khác nhau trong một nhóm có kiểm soát | Cách đếm, độ bao phủ dữ liệu, sự cố IdP |
| Workload có lấy token khác với nhu cầu thông thường không? | Tốc độ cấp token, grant, audience, scope yêu cầu | Lịch triển khai, số instance, mục đích workload |
| Quyền truy cập có biến động đáng chú ý không? | Số lần thêm role, cấp quyền, thay nhóm | Người thực hiện, đối tượng, phê duyệt và thay đổi tổ chức |
| Hoạt động đặc quyền có lệch ngữ cảnh không? | Thời gian truy cập, tài nguyên, loại hành động | Lịch trực, nhiệm vụ được duyệt, quy trình khẩn cấp |
| Hệ thống quan sát có bị suy giảm không? | Độ trễ log, mất nguồn, thay schema, số event | Lịch bảo trì, pipeline và khả năng đối chiếu nguồn |

Với mỗi câu hỏi, cần xác định trước ai nhận alert, họ cần xem gì và quyết định nào có thể đưa ra. Một detector không có người chịu trách nhiệm hoặc không có bước điều tra tiếp theo dễ tạo thêm hàng chờ mà ít giúp giảm rủi ro.

## 4. Chuẩn hóa sự kiện trước khi tìm bất thường

### 4.1. Chọn đơn vị quan sát

Một giao dịch đăng nhập có thể tạo nhiều request, nhiều challenge MFA và nhiều log ở gateway, IdP, ứng dụng. Nếu cộng tất cả log như những attempt độc lập, mức tăng có thể chỉ phản ánh thay đổi instrumentation.

Cần quy định rõ đang đếm giao dịch, request, bước xác thực, thay đổi quyền hay hoạt động quản trị. Dùng một nguồn kết quả chính hoặc cơ chế khử trùng phù hợp khi sự kiện được chuyển tiếp qua nhiều hệ thống.

Ví dụ, phân tích đăng nhập cần tách:

```text
Yêu cầu MFA                  -> giao dịch đang tiếp diễn
Một lần nhập mã bị từ chối   -> kết quả của một bước
Login hoàn tất thành công   -> kết quả cuối của giao dịch
Không đủ quyền đọc tài liệu  -> quyết định authorization
```

Không trộn các đơn vị này rồi tạo baseline cho một tỷ lệ được gọi chung là “failure”.

### 4.2. Ngữ cảnh và mức tin cậy của thuộc tính

Sự kiện có thể cần thời gian xảy ra, thời gian thu nhận, nguồn, môi trường, loại flow, outcome, nhóm lý do và thông tin liên kết được phép sử dụng.

Phải phân biệt thuộc tính đã được hệ thống tin cậy xác nhận với giá trị do client tự khai. IP có thể thuộc proxy dùng chung; thông tin vị trí có độ chính xác giới hạn; user agent có thể bị thay đổi. Những thuộc tính này bổ sung ngữ cảnh nhưng không tự chứng minh danh tính của người điều khiển request.

Khi theo dõi vị trí hoặc thiết bị mới, cần xét VPN, NAT, thiết bị dùng chung và các giới hạn của nguồn suy luận. Không trình bày vị trí suy đoán như một bằng chứng chính xác tuyệt đối.

### 4.3. Chất lượng dữ liệu là một đầu vào của quyết định

Log đến muộn có thể dồn nhiều sự kiện cũ vào một thời điểm thu nhận. Một connector ngừng gửi log có thể làm số lần thất bại giảm về 0 mà không phản ánh cải thiện an ninh.

Theo dõi tối thiểu:

- Nguồn nào đang gửi dữ liệu và độ bao phủ của nguồn đó.
- Độ trễ giữa thời điểm sự kiện và thời điểm thu nhận.
- Tỷ lệ sự kiện bị lỗi parse, thiếu field hoặc bị trùng.
- Thay đổi schema, bộ lọc, sampling và phiên bản bộ thu.
- Tình trạng đồng hồ và cách xử lý sự kiện đến muộn.

Khi chất lượng dữ liệu không đáp ứng điều kiện của detector, kết quả nên thể hiện `insufficient_data` hoặc trạng thái suy giảm phù hợp. Đồng thời phát tín hiệu về sức khỏe telemetry; không chuyển sự thiếu dữ liệu thành kết luận “không có bất thường”.

## 5. Xây dựng baseline phù hợp với ngữ cảnh

### 5.1. So sánh đúng đối tượng

Baseline là mô tả hành vi được kỳ vọng, có thể dựa trên lịch sử, nhóm tương đồng hoặc cấu hình được quản trị. Nó không phải danh sách những hành vi được phép.

Ví dụ, nên cân nhắc tách:

- Đăng nhập người dùng với cấp token của workload.
- Production với môi trường phát triển.
- Nhóm quản trị với nhóm người dùng thông thường.
- Những flow có loại grant hoặc nguồn danh tính khác nhau.
- Các vùng có lịch sử sử dụng và quy mô tải khác nhau.

Tách quá ít sẽ làm các quần thể khác nhau che lấp nhau. Tách quá nhiều có thể tạo nhóm chỉ có vài mẫu, baseline thiếu ổn định và chi phí xử lý cao. Cần chọn độ chi tiết phục vụ câu hỏi điều tra, có cách xử lý nhóm ít dữ liệu.

### 5.2. Mùa vụ, lịch làm việc và thay đổi hợp lệ

Lưu lượng sáng thứ Hai có thể khác cuối tuần; một tác vụ batch có thể chạy ban đêm; đội vận hành có thể làm việc theo ca. So sánh tất cả với cùng một giá trị trung bình dễ gây nhiều cảnh báo sai.

Có thể xây dựng baseline theo những khung giờ hoặc loại ngày tương đồng, đồng thời đối chiếu lịch triển khai, thay đổi tổ chức và vận hành đã được duyệt. Mức độ chi tiết phụ thuộc lượng lịch sử thực tế.

Không mặc định khoảng thời gian ban đêm là bất thường cho mọi tổ chức. Một đặc điểm chỉ có ý nghĩa khi gắn với lịch sử, vai trò và mục đích sử dụng.

### 5.3. Cold start và nhóm ít hoạt động

Client mới, ứng dụng mới hoặc một tài khoản khẩn cấp có thể chưa có đủ lịch sử để học baseline riêng. Khi đó có thể dùng cấu hình ban đầu được phê duyệt, nhóm so sánh phù hợp hoặc detector theo sự kiện và chính sách.

Trạng thái thiếu lịch sử cần được hiển thị rõ. Không gán một anomaly score có vẻ chính xác cho đối tượng mà hệ thống chưa đủ dữ liệu để đánh giá.

Một lần cấp quyền nhạy cảm ở nhóm ít lưu lượng vẫn có thể cần kiểm tra theo chính sách. Không dùng điều kiện “chưa đủ mẫu” của detector thống kê để tắt toàn bộ kiểm soát đối với nhóm đó.

## 6. Chọn tín hiệu và phương pháp phát hiện

Không có một phương pháp duy nhất phù hợp với mọi tín hiệu IAM.

| Tín hiệu hoặc phương pháp | Điểm hữu ích | Điều phải kiểm soát |
|---|---|---|
| Số lượng trong cửa sổ | Dễ hiểu khi tải hoặc số hành động tăng mạnh | Quy mô lưu lượng, cửa sổ, sự kiện trùng |
| Tỷ lệ outcome | Phân biệt thay đổi chất lượng với tăng tải đơn thuần | Mẫu số, lượng mẫu và outcome nhất quán |
| Dải kỳ vọng theo thời gian | Thể hiện mức lệch so với lịch sử tương đồng | Mùa vụ, khoảng thiếu dữ liệu và drift |
| Median và thước đo phân tán bền vững | Hạn chế ảnh hưởng của một số điểm cực đoan | Không tự giải quyết mùa vụ hoặc thay đổi quần thể |
| So sánh nhóm tương đồng | Hữu ích khi cá thể ít lịch sử riêng | Nhóm phải có mục đích và đặc điểm phù hợp |
| Sự mới lạ của tổ hợp thuộc tính | Tìm ngữ cảnh chưa từng quan sát | Lịch sử không đầy đủ và thay đổi hợp lệ |
| Kết hợp nhiều tín hiệu | Bổ sung bằng chứng từ nhiều khía cạnh | Tương quan giữa tín hiệu và khả năng giải thích |

Một z-score dựa trên trung bình và độ lệch chuẩn có thể diễn giải đơn giản, nhưng không nên tự coi mọi chuỗi đếm hoặc tỷ lệ IAM có phân bố phù hợp với giả định của phương pháp đó. Phân bố lệch, nhiều số 0, ít mẫu và tính mùa vụ đều ảnh hưởng ý nghĩa của score.

Thước đo bền vững cũng có trường hợp suy biến, chẳng hạn mức phân tán bằng 0 trong lịch sử. Detector phải có quy tắc xử lý được kiểm chứng; không chia cho 0 hoặc âm thầm thay bằng một hằng số rồi diễn giải như kết quả thống kê chuẩn.

### Ví dụ về lượng mẫu và mẫu số

Giả sử baseline minh họa của một flow thường có tỷ lệ từ chối khoảng 2%. Trong cửa sổ hiện tại:

```text
Trường hợp A: 120 lần từ chối / 1.000 attempt = 12%
Trường hợp B:   1 lần từ chối /     2 attempt = 50%
```

Trường hợp B có tỷ lệ lớn hơn nhưng ít dữ liệu hơn nhiều. Không thể chỉ so sánh 50% với 12% để kết luận trường hợp B nghiêm trọng hơn.

Trường hợp A cũng chưa chứng minh hành vi xấu. Cần xem phần từ chối do credential, chính sách, trạng thái tài khoản hay cấu hình nguồn danh tính. Dải baseline, lượng mẫu và ngưỡng phát alert đều phải được lựa chọn theo dữ liệu và mục tiêu thực tế; các số trong ví dụ không phải ngưỡng chung.

## 7. Từ phát hiện bất thường đến phát cảnh báo

Một điểm dữ liệu lệch baseline chưa nhất thiết phải đánh thức người trực. Có thể tách quá trình thành những quyết định rõ ràng:

```text
Sự kiện đã chuẩn hóa
    -> kiểm tra chất lượng và phạm vi dữ liệu
    -> tạo đặc trưng trong cửa sổ phù hợp
    -> so sánh với baseline có phiên bản
    -> xác định bất thường và bằng chứng
    -> xét điều kiện phát alert, mức độ và nhóm nhận
    -> điều tra, phản hồi và theo dõi kết quả
```

### 7.1. Điều kiện phát alert

Các điều kiện có thể xét mức lệch, số lượng tuyệt đối, tỷ lệ, thời gian kéo dài, độ quan trọng của đối tượng và tín hiệu hỗ trợ.

Ví dụ dưới đây là logic minh họa, không phải cấu hình chạy được của một sản phẩm:

```text
Nếu nguồn dữ liệu thiếu hoặc baseline chưa đủ:
    ghi trạng thái không đủ dữ liệu
    chuyển tín hiệu chất lượng dữ liệu tới kênh phù hợp
Ngược lại:
    so sánh flow với các cửa sổ lịch sử tương đồng
    tạo bằng chứng về mức lệch và lượng mẫu
    nếu đạt điều kiện cảnh báo của detector:
        nhóm các kết quả liên quan thành một alert
        gán mức độ theo tác động và ngữ cảnh
        gửi tới người sở hữu quy trình phản ứng
```

Một số detector cần bất thường kéo dài qua vài cửa sổ để giảm nhiễu. Các sự kiện đặc quyền quan trọng có thể cần điều tra ngay theo chính sách, không chờ điều kiện kéo dài dành cho số liệu lưu lượng.

### 7.2. Anomaly score không phải mức rủi ro hoàn chỉnh

Một hành vi cực hiếm trên tài khoản thử nghiệm có thể ít tác động hơn một mức lệch nhỏ nhưng liên quan tới quyền quản trị production.

Đánh giá mức độ cần xét riêng:

- Độ tin cậy và độ đầy đủ của bằng chứng.
- Mức quan trọng của tài nguyên và đặc quyền.
- Phạm vi chủ thể, ứng dụng và môi trường bị ảnh hưởng.
- Dấu hiệu hoạt động thành công đáng chú ý sau các lần bị từ chối.
- Khả năng đó là thay đổi hợp lệ hoặc sự cố kỹ thuật.

Nếu hệ thống tính một risk score tổng hợp, cần công bố ý nghĩa, giới hạn và các đầu vào chính. Không mặc định một score là xác suất tấn công đã được hiệu chuẩn.

## 8. Nội dung một alert có thể điều tra được

Alert nên cho biết điều gì lệch, lệch so với đâu và người nhận có thể kiểm tra bằng chứng nào.

Ví dụ minh họa:

```yaml
detector: iam-login-rejection-anomaly
detectorVersion: example-v1
scope:
  environment: production
  flowGroup: workforce-login
window:
  start: "2030-01-15T08:00:00Z"
  end: "2030-01-15T08:05:00Z"
observed:
  attempts: 1000
  rejected: 120
  rejectionRate: 0.12
baseline:
  comparison: comparable-historical-windows
  typicalRejectionRate: 0.02
dataQuality: sufficient_for_this_detector
severity: needs_triage
owner: identity-operations
```

Schema, thời gian và các giá trị trên chỉ phục vụ bài học. Trong hệ thống thực, alert cần thêm liên kết truy vấn được phân quyền, lý do kích hoạt, tình trạng detector, các thay đổi liên quan và runbook cụ thể.

Không nhúng token, password, OTP, cookie hoặc secret vào payload cảnh báo. Kênh chat và email nhận alert có thể có nhiều người hoặc thời gian lưu khác với kho log, nên cần giới hạn dữ liệu ngay khi tạo payload.

Các định danh chi tiết cần thiết cho điều tra có thể đặt trong hệ thống được phân quyền, với liên kết tham chiếu phù hợp. Việc giảm dữ liệu trong alert không nên khiến người điều tra không thể truy tìm nguồn bằng chứng.

## 9. Nhóm, giảm nhiễu và quản lý vòng đời alert

Một sự cố nguồn SSO có thể tạo hàng nghìn kết quả bất thường trên nhiều ứng dụng. Phát một alert cho từng event sẽ làm người trực khó nhận ra nguyên nhân chung.

Có thể nhóm theo detector, phạm vi bị ảnh hưởng, nguồn phụ thuộc và cửa sổ thời gian phù hợp. Mỗi nhóm cần giữ số lượng, thời gian bắt đầu, lần cập nhật gần nhất và khả năng mở rộng xuống bằng chứng chi tiết.

Các kỹ thuật vận hành thường gồm:

- Dedup để tránh tạo nhiều alert giống nhau từ cùng một tình trạng.
- Cooldown để hạn chế gửi lại liên tục khi tình trạng chưa đổi.
- Hysteresis để điều kiện mở và đóng không dao động quanh một mốc.
- Escalation khi tình trạng kéo dài hoặc tác động mở rộng.
- Maintenance annotation để giải thích những thay đổi đã lên lịch.

Suppression phải có phạm vi, lý do, người chịu trách nhiệm và thời điểm hết hiệu lực. Không suppress toàn bộ IAM chỉ vì đang bảo trì một connector.

Đóng alert cũng là một quyết định có bằng chứng. Tín hiệu trở về baseline không tự chứng minh nguyên nhân đã được xử lý; baseline có thể vừa dịch chuyển hoặc nguồn dữ liệu vừa mất. Cần xét sức khỏe telemetry và kết quả điều tra.

Với người dùng hoặc workload quan trọng ít hoạt động, cân nhắc kênh và detector riêng để tránh bị mất trong cơ chế nhóm dành cho lưu lượng lớn.

## 10. Runbook điều tra theo loại bằng chứng

Người nhận alert có thể đi theo trình tự:

1. Xác nhận detector, cửa sổ, phạm vi, phiên bản baseline và chất lượng dữ liệu.
2. Xem cả số lượng, tỷ lệ, mẫu số và các lát cắt liên quan.
3. Tách lỗi kỹ thuật, từ chối theo chính sách và những kết quả xác thực thành công.
4. Đối chiếu triển khai, bảo trì, thay đổi vai trò, onboarding hoặc tác vụ batch đã được duyệt.
5. Truy vấn log hoặc trace trong quyền được cấp để tìm bằng chứng hỗ trợ hay bác bỏ giả thuyết.
6. Xác định tác động và chuyển đúng bên chịu trách nhiệm.
7. Thực hiện biện pháp được cho phép, ghi lại kết quả và theo dõi sau phản ứng.

### Tình huống A: Từ chối đăng nhập tăng ở nhiều ứng dụng

Một nhóm ứng dụng cùng lệch baseline ngay sau thay đổi mapping tại nguồn danh tính. Lỗi tập trung vào cùng một nguồn, trong khi các nguồn khác ổn định.

Giả thuyết ưu tiên là cấu hình hoặc dịch vụ phụ thuộc có vấn đề. Cần kiểm tra nhóm lý do, thay đổi mapping và phạm vi tài khoản bị ảnh hưởng. Việc khóa hàng loạt người dùng theo anomaly score có thể làm sự cố rộng hơn.

### Tình huống B: Workload xin token tăng đột biến

Một workload production có request cấp token cao hơn lịch sử. Cùng thời điểm, số instance tăng và retry cũng tăng.

Cần kiểm tra cách ứng dụng quản lý token, thời điểm khởi động và lỗi phụ thuộc. Nếu workload còn yêu cầu audience mới hoặc có thay đổi quyền ngoài quy trình, đó là bằng chứng khác cần điều tra thêm. Chỉ riêng request rate tăng chưa đủ kết luận credential bị lộ.

### Tình huống C: Hoạt động đặc quyền ít gặp

Một tài khoản quản trị lần đầu thêm role nhạy cảm cho workload trong một khoảng thời gian khác lịch sử. Tổng số sự kiện chỉ là một.

Cần kiểm tra quyền của người thực hiện, phê duyệt thay đổi, quy trình khẩn cấp, đối tượng nhận quyền và các hoạt động sau đó. Không đợi hàng trăm event để đạt điều kiện lượng mẫu của một detector lưu lượng; sự kiện này có thể thuộc kiểm soát chính sách riêng.

## 11. Phản ứng có giới hạn và bảo toàn bằng chứng

Không gắn một hành động gây tác động lớn trực tiếp với mọi điểm bất thường. Một alert có thể cần bổ sung ngữ cảnh, yêu cầu đánh giá, hoặc chuyển tới quy trình phản ứng đã được phê duyệt.

Tự động hóa có thể hỗ trợ thu thập tham chiếu log, mở hồ sơ điều tra, gắn mốc thay đổi và gửi thông báo. Các biện pháp như thu hồi phiên, xoay credential hoặc vô hiệu hóa tài khoản cần điều kiện, thẩm quyền và giới hạn tác động rõ ràng.

Nếu có cơ chế tự động phản ứng, cần quy định trước:

- Bằng chứng nào đủ để kích hoạt và trường hợp nào cần người đánh giá.
- Phạm vi tài khoản, workload hoặc tài nguyên được tác động.
- Cách tránh phản ứng lặp, phản ứng dây chuyền và tự gây từ chối dịch vụ.
- Cách khôi phục hoặc xử lý khi phát hiện đánh giá sai.
- Cách ghi audit cho quyết định và kết quả thực thi.

Giữ lại bằng chứng phù hợp trong quyền và thời gian lưu đã quy định. Không xóa log hoặc thay đổi dữ liệu nguồn để làm alert biến mất. Trong khi xử lý sự cố, vẫn phải giữ nguyên tắc ít quyền nhất và các điều kiện xác thực cần thiết.

## 12. Drift, phản hồi và chất lượng detector

### 12.1. Khi hành vi bình thường thay đổi

Concept drift xảy ra khi đặc điểm hoạt động thay đổi theo thời gian, chẳng hạn tổ chức chuyển sang MFA, thêm nguồn SSO hoặc di chuyển workload. Baseline cũ có thể không còn phù hợp.

Cần theo dõi thay đổi phân bố, lượng alert, nhóm thường xuyên bị gắn cờ và những detector thiếu dữ liệu. Baseline mới nên có phiên bản, khoảng dữ liệu học rõ ràng và khả năng so sánh với phiên bản trước.

Không tự động học mọi dữ liệu mới như hành vi hợp lệ. Một sự cố hoặc hành vi lạm dụng kéo dài có thể làm baseline thích nghi sai. Cần có cách nhận diện và quản lý các khoảng dữ liệu nghi ngờ, cùng quy trình phê duyệt thay đổi phù hợp với mức quan trọng của detector.

### 12.2. Phản hồi điều tra

Có thể phân loại alert đã điều tra thành hoạt động xấu được xác nhận, thay đổi hợp lệ, sự cố vận hành, lỗi dữ liệu hoặc chưa đủ bằng chứng. Không ép mọi alert chưa kết luận thành false positive.

Những chỉ số hữu ích gồm:

- Số alert theo detector và tỷ lệ được điều tra.
- Tỷ lệ alert có kết luận trong tập đã điều tra, với định nghĩa rõ ràng.
- Thời gian phát hiện, tiếp nhận và xử lý.
- Số alert lặp, số lần suppression và tình trạng quá tải của người nhận.
- Độ bao phủ nguồn dữ liệu và số đối tượng đang thiếu baseline.
- Các tình huống kiểm chứng mà detector phát hiện hoặc bỏ sót.

Tỷ lệ cảnh báo đúng trong tập đã điều tra có thể bị lệch do cách ưu tiên xử lý. Recall còn cần biết những sự kiện mục tiêu đã bị bỏ sót, không thể tính đáng tin chỉ từ danh sách alert được tạo. Có thể dùng tình huống kiểm chứng có kiểm soát, dữ liệu gắn nhãn hoặc đánh giá sau sự cố để bổ sung bằng chứng.

Trước khi đưa một detector mới vào kênh trực, có thể chạy ở chế độ quan sát để đánh giá ngữ nghĩa tín hiệu và tải xử lý. Việc triển khai từng bước vẫn cần duy trì những kiểm soát hiện có.

## 13. Quyền riêng tư, cardinality và quyền truy cập

Phân tích IAM có thể cần nhìn theo chủ thể, nhưng không phải mọi định danh đều phù hợp làm metric label. Hàng triệu subject ID, IP hoặc request ID sẽ tạo số lượng chuỗi thời gian lớn và có thể làm tăng khả năng lộ dữ liệu.

Metric tổng hợp nên dùng nhóm có giới hạn. Khi cần phân tích theo chủ thể hoặc chuỗi sự kiện, có thể dùng kho sự kiện hoặc công cụ phân tích được thiết kế và phân quyền cho mục đích đó. Băm định danh không tự làm giảm cardinality và không bảo đảm không thể liên kết dữ liệu.

Cần giới hạn ai được xem, sửa detector, thay baseline, suppress alert và thực thi phản ứng. Các quyền này có thể ảnh hưởng trực tiếp đến khả năng phát hiện, nên thay đổi cần được audit và phân tách trách nhiệm phù hợp.

Chỉ thu dữ liệu cần cho mục tiêu đã xác định; kiểm soát thời gian lưu, xuất dữ liệu và phạm vi chia sẻ. Không dùng yêu cầu observability để ghi credential hoặc mở quyền truy vấn rộng hơn nhu cầu điều tra.

## 14. Kiểm chứng trước và trong quá trình vận hành

| Tình huống kiểm chứng | Điều cần xác nhận |
|---|---|
| Lưu lượng tăng hợp lệ nhưng tỷ lệ outcome ổn định | Detector không mặc định đánh đồng tăng tải với hành vi xấu |
| Tỷ lệ tăng ở nhóm chỉ có vài event | Kết quả thể hiện lượng mẫu và mức chắc chắn phù hợp |
| Một thay đổi đặc quyền nhạy cảm | Kiểm soát theo chính sách vẫn hoạt động dù ít mẫu |
| Sự kiện bị gửi lặp | Không khuếch đại số lượng ngoài hợp đồng đếm |
| Log đến trễ hoặc pipeline dồn lô | Cửa sổ và logic dữ liệu muộn giữ đúng ý nghĩa |
| Nguồn log ngừng gửi | Có tín hiệu chất lượng dữ liệu, không kết luận hệ thống an toàn |
| Client mới chưa có lịch sử | Có trạng thái cold start và cơ chế theo dõi phù hợp |
| Thay đổi hợp lệ đã được duyệt | Có ngữ cảnh giải thích; suppression nếu dùng có hạn và đúng phạm vi |
| Tình trạng kéo dài qua nhiều cửa sổ | Nhóm, cập nhật và escalation hoạt động như thiết kế |
| Baseline thay đổi hoặc học từ khoảng dữ liệu nghi ngờ | Có phiên bản, kiểm soát và khả năng đối chiếu |
| Người không có quyền mở liên kết bằng chứng | Dữ liệu được bảo vệ theo phân quyền |
| Alert bị đánh giá sai | Có thể ghi phản hồi và xử lý tác động của phản ứng trước đó |

Một cảnh báo anomaly có giá trị khi người nhận hiểu được dữ liệu nào tạo ra nó, baseline nào được dùng, điều gì còn chưa chắc chắn và bước điều tra tiếp theo là gì. Kết hợp tín hiệu bất thường với chính sách, ngữ cảnh vận hành và bằng chứng được bảo vệ giúp IAM phát hiện những thay đổi đáng chú ý mà vẫn giữ được khả năng phản ứng đúng mức.
