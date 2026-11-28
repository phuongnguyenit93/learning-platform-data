# Load shedding

## 1. Load shedding là gì?

**Load shedding** là chủ động từ chối, loại bỏ hoặc ngừng tiếp nhận một phần công việc khi hệ thống không thể xử lý toàn bộ tải trong giới hạn an toàn. Mục tiêu là giữ năng lực phục vụ cho những công việc được ưu tiên, bảo vệ tài nguyên và tránh quá tải lan truyền.

Ví dụ, khi dịch vụ đang bão hòa, hệ thống có thể từ chối yêu cầu tạo báo cáo tùy chọn trước khi ảnh hưởng đến luồng xác nhận giao dịch. Yêu cầu bị từ chối nhận được kết quả theo hợp đồng thay vì tiếp tục chờ vô hạn và chiếm tài nguyên.

Trong chương **Availability và resilience** của module yêu cầu bảo mật, load shedding cần được đặc tả như một kiểm soát bảo vệ tính sẵn sàng. Từ mục tiêu an toàn thông tin và mô hình đe dọa, người thiết kế phải xác định được:

- Tài nguyên và luồng nghiệp vụ nào cần được bảo vệ.
- Dấu hiệu nào cho phép kết luận hệ thống cần giảm tải.
- Công việc nào được tiếp nhận, chờ, giảm chất lượng hoặc từ chối.
- Quyền ưu tiên được xác minh như thế nào.
- Client, hệ thống phụ thuộc và người vận hành phải phản ứng ra sao.
- Bằng chứng nào chứng minh chính sách hoạt động đúng trong điều kiện quá tải và lỗi.

Không nên dùng một yêu cầu chung như “hệ thống phải tự giảm tải khi cần”. Câu đó chưa định nghĩa được thời điểm kích hoạt, phạm vi tác động, hậu quả nghiệp vụ hoặc tiêu chí kiểm thử.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt load shedding với rate limiting, giới hạn đồng thời, giảm chất lượng và autoscaling.
2. Chuyển kịch bản cạn tài nguyên thành chính sách loại tải có thể kiểm chứng.
3. Đặc tả tín hiệu quá tải, mức ưu tiên, điểm thực thi và điều kiện phục hồi.
4. Bảo vệ tính đúng đắn của giao dịch, quyền truy cập và danh tính khi loại tải.
5. Xây dựng chỉ số và bài kiểm thử không che giấu tỷ lệ thất bại thực tế.

## 2. Liên kết với rủi ro bảo mật

Tải vượt năng lực có thể đến từ người dùng hợp lệ, client bị lỗi, tác vụ nội bộ hoặc hành vi cố ý làm cạn tài nguyên. Hệ thống không phải lúc nào cũng xác định được ý định của bên gửi trước khi cần tự bảo vệ.

| Kịch bản rủi ro | Tài nguyên hoặc mục tiêu bị ảnh hưởng | Quyết định giảm tải cần đặc tả |
|---|---|---|
| Nhiều yêu cầu tìm kiếm nặng | CPU, bộ nhớ, kết nối DB | Từ chối công việc mới trước khi bắt đầu truy vấn tốn kém |
| Một tenant tạo lượng việc lớn | Năng lực dùng chung của các tenant | Giới hạn phần tiêu thụ và phân bổ công bằng |
| Dịch vụ phụ thuộc chậm | Worker chờ, kết nối và hàng đợi | Hạn chế lời gọi mới, giảm tích tụ và trả kết quả rõ ràng |
| Client retry đồng loạt | Tải tiếp nhận và xử lý bị khuếch đại | Trả tín hiệu quá tải và áp dụng ngân sách retry |
| Tác vụ nền chiếm hết năng lực | Luồng nghiệp vụ tương tác bị chậm | Giảm hoặc dừng nhận tác vụ nền theo chính sách |
| Đối tượng giả mạo quyền ưu tiên | Phần năng lực dành cho công việc quan trọng | Xác minh mức ưu tiên phía máy chủ |
| Đường từ chối sinh log quá nhiều | CPU, I/O và nơi lưu log | Giữ xử lý từ chối nhẹ, có giới hạn và vẫn quan sát được |

Load shedding giúp hạn chế tác động khi tải đã tới điểm kiểm soát. Nó không tự bảo vệ băng thông mạng hoặc tài nguyên đã bị tiêu thụ ở các tầng trước đó. Nếu kịch bản đe dọa nằm ở lớp tiếp nhận kết nối, giới hạn payload hoặc giải mã đầu vào, cần kiểm soát tương ứng tại các lớp đó.

Yêu cầu cũng cần chỉ ra hậu quả chấp nhận được. Việc từ chối một thao tác xem gợi ý sản phẩm khác với việc bỏ một lệnh đã được ghi nhận là giao dịch thành công. Chính sách bảo vệ tính sẵn sàng không được âm thầm phá vỡ cam kết nghiệp vụ.

## 3. Phân biệt các cơ chế liên quan

| Cơ chế | Đại lượng hoặc hành vi được kiểm soát | Quan hệ với load shedding |
|---|---|---|
| Rate limiting | Số yêu cầu theo chủ thể và cửa sổ thời gian | Có thể thực thi quota kể cả khi hệ thống còn rảnh; cũng có thể hỗ trợ giảm tải |
| Concurrency limit | Số công việc đang đồng thời chiếm tài nguyên | Khi hết năng lực, việc từ chối nhận thêm là một cách loại tải |
| Hàng đợi có giới hạn | Số lượng, dung lượng và tuổi công việc chờ | Hấp thụ biến động ngắn; khi đầy hoặc quá hạn cần quyết định loại tải |
| Circuit breaker | Lời gọi đến dependency theo trạng thái lỗi | Ngăn tiếp tục gọi một dependency đang có vấn đề; không tự phân bổ mọi workload |
| Graceful degradation | Chất lượng hoặc tính năng của kết quả | Giảm chi phí phục vụ; cần hợp đồng riêng về kết quả suy giảm |
| Autoscaling | Năng lực triển khai | Bổ sung năng lực có độ trễ và có giới hạn; không thay thế cơ chế tự bảo vệ tức thời |
| Load shedding | Phần công việc được tiếp nhận khi năng lực thiếu | Chọn công việc phải từ chối để bảo vệ mục tiêu còn lại |

Các cơ chế có thể kết hợp. Ví dụ, một API có quota tenant cố định, trần đồng thời theo dependency, hàng đợi ngắn và chính sách từ chối lớp ưu tiên thấp khi hệ thống suy giảm.

Đặc tả phải phân biệt lý do từ chối. Người dùng vượt quota không đồng nghĩa toàn hệ thống đang quá tải. Tương tự, một dependency lỗi không chứng minh CPU của ứng dụng đã bão hòa. Việc phân biệt giúp client và đội vận hành chọn phản ứng phù hợp.

## 4. Xác định đối tượng được loại tải

### 4.1. Đơn vị công việc

Cần chỉ rõ chính sách áp dụng cho request, tác vụ nền, message, stream hay một phần công việc bên trong request. Một request có thể tạo nhiều truy vấn hoặc nhiều job; chỉ đếm request ở gateway có thể không phản ánh chi phí thực.

Với API tạo job, phản hồi “đã tiếp nhận” thường tạo một cam kết khác với việc từ chối ngay. Nếu công việc đã được ghi bền vững và xác nhận tiếp nhận, không được âm thầm xóa nó rồi báo hệ thống đang giảm tải. Phải thực hiện đúng hợp đồng về trạng thái job, thất bại, hủy hoặc thử lại.

Với message, cần định nghĩa hành vi xác nhận nhận thành công, giữ lại, trả về hàng đợi hoặc đánh dấu thất bại. Xác nhận một message rồi bỏ công việc mà không có trạng thái nghiệp vụ tương ứng có thể gây mất dữ liệu.

### 4.2. Thời điểm ra quyết định

Ưu tiên đưa quyết định loại tải đến trước thao tác tốn tài nguyên hoặc tạo tác động phụ. Tuy nhiên, một số quyết định cần biết danh tính và quyền của người gọi. Có thể cần nhiều tầng:

```text
Tầng biên: giới hạn kết nối, kích thước và chi phí tiếp nhận
    ↓
Xác minh danh tính với ngân sách tài nguyên riêng
    ↓
Phân loại workload và kiểm tra quyền
    ↓
Admission theo tenant, ưu tiên và năng lực
    ↓
Thực thi công việc và gọi dependency
```

Sơ đồ mô tả các trách nhiệm logic, không bắt buộc mỗi tầng là một dịch vụ. Điểm quan trọng là không để công việc chưa được chấp nhận tiêu thụ phần lớn tài nguyên cần bảo vệ.

### 4.3. Không nhầm loại tải với hủy giao dịch tùy ý

Load shedding thường an toàn hơn khi từ chối công việc chưa bắt đầu. Nếu chính sách còn cho phép dừng công việc đang chạy, phải đặc tả điểm hủy an toàn, việc hoàn tác, khả năng chạy lại và trạng thái trả cho client.

Một request đã timeout có thể vẫn đang ghi dữ liệu. Trả lỗi không chứng minh tác động phụ chưa xảy ra. Cần cơ chế xác định kết quả, tra cứu trạng thái hoặc idempotency phù hợp để client không tạo giao dịch trùng khi thử lại.

## 5. Phân lớp ưu tiên bằng chính sách đáng tin cậy

### 5.1. Ưu tiên gắn với mục tiêu nghiệp vụ và rủi ro

Một hệ thống giả định có thể chia công việc như sau:

| Lớp | Ví dụ | Chính sách khi quá tải |
|---|---|---|
| A — quan trọng | Xác nhận nghiệp vụ thiết yếu, thao tác phục hồi đã được cấp quyền | Có phần năng lực được bảo vệ và trần riêng |
| B — thông thường | Truy vấn tương tác hợp lệ | Phục vụ theo phần năng lực còn lại và chính sách công bằng |
| C — có thể trì hoãn | Tạo báo cáo tùy chọn, đồng bộ nền không khẩn cấp | Giảm tiếp nhận trước, chờ có giới hạn hoặc từ chối |

Các nhãn này chỉ là ví dụ. Đội nghiệp vụ và bảo mật phải quyết định thao tác nào thật sự cần được bảo vệ. Không mặc nhiên coi mọi thao tác quản trị là quan trọng hơn mọi thao tác người dùng.

Mỗi lớp vẫn cần giới hạn. Nếu lớp A được phép sử dụng tài nguyên vô hạn, một tài khoản có đặc quyền bị chiếm đoạt có thể làm cạn toàn hệ thống bằng chính đường ưu tiên.

### 5.2. Không tin mức ưu tiên do client tự khai

Mức ưu tiên phải được suy ra từ loại thao tác, danh tính và quyền đã xác minh. Các trường như `priority`, `tenant_id` hoặc `internal_call` từ client không tự tạo ra quyền sử dụng năng lực dành riêng.

Nếu gateway truyền thông tin ưu tiên tới backend, ranh giới tin cậy và cơ chế xác minh phải được xác định. Backend không được nhận mọi header giống nhau từ cả gateway tin cậy và client bên ngoài mà không phân biệt nguồn.

Ngoại lệ cần có người phê duyệt, phạm vi, thời hạn, ngân sách và audit. Một cờ “bypass shedding” tồn tại lâu dài nhưng không có chủ sở hữu là đường vượt kiểm soát cần tránh.

### 5.3. Công bằng giữa tenant

Chính sách “loại 30% request ngẫu nhiên” có thể giảm tải tổng nhưng không tự bảo đảm công bằng. Một tenant gửi nhiều yêu cầu vẫn có thể chiếm phần lớn số được phục vụ. Cần kết hợp trần tenant hoặc scheduler phù hợp nếu mục tiêu là cách ly khách hàng.

Ngược lại, áp dụng một trần giống nhau cho mọi tenant có thể không phù hợp với các cam kết dịch vụ khác nhau. Yêu cầu phải công bố quy tắc phân bổ được phê duyệt, tránh để hành vi phụ thuộc ngẫu nhiên vào thứ tự request đến.

## 6. Chọn tín hiệu quá tải và điều kiện phục hồi

### 6.1. Tín hiệu phải gắn với điểm nghẽn

Không có một chỉ số duy nhất phù hợp cho mọi hệ thống. Cần xác định tín hiệu nào phản ánh sự thiếu năng lực của tài nguyên được bảo vệ.

| Tín hiệu | Giá trị sử dụng | Giới hạn cần lưu ý |
|---|---|---|
| Số công việc đang chạy | Nhận biết năng lực thực thi đã đầy | Cần định nghĩa vòng đời và phạm vi đếm |
| Độ dài hoặc dung lượng hàng đợi | Nhận biết công việc đang tích tụ | Một job lớn và nhiều job nhỏ có chi phí khác nhau |
| Tuổi công việc chờ | Nhận biết độ trễ và nguy cơ bỏ đói | Phân vị có thể che khuất một số công việc rất cũ; cần quan sát tuổi lớn nhất khi phù hợp |
| CPU theo ngân sách thực được cấp | Nhận biết bão hòa tính toán | CPU thấp vẫn có thể xảy ra khi nghẽn DB hoặc I/O |
| Bộ nhớ và dung lượng tạm | Nhận biết nguy cơ cạn tài nguyên | Số đo có độ trễ; cần khoảng dự phòng |
| Số lời gọi tới dependency và thời gian chờ | Nhận biết nghẽn ở tầng phụ thuộc | Phải tách thời gian chờ năng lực khỏi thời gian thực thi |
| Độ trễ và lỗi nghiệp vụ | Nhận biết tác động đến người dùng | Chỉ đo request hoàn tất có thể bỏ sót công việc đang treo |

Đơn vị và phạm vi cần rõ ràng. “CPU 80%” có thể nói đến một lõi, toàn máy hoặc quota của tiến trình. Chỉ số sai phạm vi có thể kích hoạt quá muộn hoặc loại tải không cần thiết.

### 6.2. Tránh dao động đóng mở

Nếu hệ thống bắt đầu loại tải ngay khi một số đo vượt ngưỡng và mở lại ngay khi số đo giảm chút ít, chính sách có thể liên tục bật tắt. Các yếu tố thường cần đặc tả gồm:

- Cửa sổ tổng hợp và chu kỳ đánh giá.
- Ngưỡng vào chế độ giảm tải và ngưỡng thoát thấp hơn.
- Số lần đo liên tiếp hoặc thời gian tối thiểu để chuyển trạng thái.
- Tốc độ tăng lại phần tải được chấp nhận.
- Điều kiện chuyển ngay sang bảo vệ khẩn cấp nếu gần chạm giới hạn cứng.

Ví dụ, trong một mô hình giả định, vào trạng thái giảm tải khi tuổi công việc chờ vượt 200 ms trong 3 lần đo liên tiếp cách nhau 1 giây; chỉ bắt đầu phục hồi khi tuổi công việc chờ dưới 80 ms và các điều kiện an toàn khác được thỏa trong 10 giây liên tục.

Các ngưỡng trên minh họa cách viết yêu cầu, không phải giá trị mặc định. Cần xác định chính xác tuổi đang dùng là lớn nhất hay một phân vị, cách xử lý khi hàng đợi rỗng và độ mới tối đa của số đo.

### 6.3. Mất telemetry không có nghĩa là khỏe

Nếu số đo đã cũ hoặc không lấy được, không tự gán giá trị 0 rồi tắt load shedding. Yêu cầu cần định nghĩa chính sách dự phòng, chẳng hạn sử dụng giới hạn tĩnh đã được kiểm chứng và ngừng tăng tải cho đến khi có tín hiệu hợp lệ.

Chính sách dự phòng phải có thời hạn, phạm vi và cách cảnh báo. Không mặc nhiên mở toàn bộ admission vì bộ điều khiển hoặc hệ thống giám sát không khả dụng.

## 7. Từ năng lực đo được đến chính sách loại tải

Giả sử một phép thử xác định hệ thống phục vụ bền vững khoảng 800 đơn vị công việc mỗi giây trong điều kiện tài nguyên, dependency và chi phí xử lý đã ghi nhận. Để minh họa, giả định các công việc có cùng chi phí chuẩn hóa và mức đầu vào tại điểm admission là:

| Lớp | Tải đến mỗi giây | Tải được tiếp nhận trong phương án minh họa | Tải bị loại |
|---|---|---|---|
| A | 150 | 150 | 0 |
| B | 750 | 650 | 100 |
| C | 300 | 0 | 300 |
| Tổng | 1.200 | 800 | 400 |

Phương án minh họa loại khoảng 33,3% công việc đến điểm admission và ưu tiên duy trì lớp A. Phép chia này giúp giải thích việc phân bổ; nó không tự tạo ra một bộ điều khiển an toàn.

Khi áp dụng thực tế cần kiểm chứng lại:

1. Chi phí xử lý từ chối, xác thực và đo lường đã được tính vào ngân sách chưa?
2. Các workload có thực sự cùng chi phí, hay phải dùng trọng số và giới hạn tài nguyên riêng?
3. Thời gian xử lý có tăng lên khi dependency suy giảm không?
4. Hệ thống có chịu được các burst ngắn mà không vượt trần bộ nhớ hoặc số công việc đồng thời không?
5. Nếu riêng lớp A vượt năng lực thì trần và hành vi từ chối của lớp A là gì?

Không dùng một con số throughput ở trạng thái khỏe làm cam kết cố định cho mọi điều kiện. Năng lực tiếp nhận cần phù hợp với tài nguyên thực tế và mức suy giảm đang có. Các giới hạn cứng về công việc đồng thời, hàng đợi hoặc bộ nhớ vẫn cần thiết nếu bộ điều khiển động phản ứng chậm.

## 8. Hợp đồng phản hồi và hành vi của client

### 8.1. Kết quả từ chối phải rõ ràng

Khi request chưa được nhận thực thi, phản hồi cần cho biết yêu cầu bị từ chối do chính sách năng lực, có thể thử lại hay không và mã liên kết để điều tra. Không trả thành công giả hoặc một kết quả rỗng khó phân biệt với kết quả nghiệp vụ hợp lệ.

Với API HTTP, một hợp đồng có thể dùng `503` cho việc dịch vụ tạm thời không đủ năng lực và `429` cho việc chủ thể vượt quota của mình. Cách ánh xạ cần thống nhất với API của dự án; không suy ra mọi lỗi `503` đều là load shedding.

Ví dụ cấu trúc phản hồi minh họa:

```json
{
  "code": "TEMPORARY_CAPACITY_REJECTION",
  "message": "Chưa thể tiếp nhận tác vụ tại thời điểm này.",
  "retryable": true,
  "requestId": "req-example-17"
}
```

`retryable: true` nghĩa là có thể thử lại theo chính sách, không phải yêu cầu thử lại ngay lập tức. Thông tin phản hồi không nên tiết lộ tenant nào đang chiếm tài nguyên, dung lượng bí mật hoặc cách vượt cơ chế ưu tiên.

### 8.2. Retry có ngân sách

Đặc tả cần quy định bên nào được retry, tối đa bao nhiêu lần, deadline tổng và cách tăng khoảng chờ. Nếu nhiều tầng cùng retry độc lập, số lần thực thi phía sau có thể tăng mạnh dù người dùng chỉ gửi một thao tác.

Các yêu cầu hữu ích gồm:

- Dùng khoảng lùi và độ ngẫu nhiên phù hợp để tránh client đồng loạt gửi lại.
- Không retry sau khi deadline nghiệp vụ đã hết.
- Không vượt quota hoặc ngân sách retry chỉ vì phản hồi có thể thử lại.
- Mọi lần thử tạo công việc thật đều đi qua admission tương ứng.
- Với thao tác có tác động phụ, áp dụng hợp đồng idempotency hoặc tra cứu kết quả trước khi gửi lại.

Nếu có hướng dẫn thời gian chờ như `Retry-After`, phải định nghĩa ý nghĩa và cách client xử lý. Hết thời gian gợi ý không tạo bảo đảm rằng năng lực đã có sẵn. Hệ thống cũng cần giữ trần an toàn khi client không tuân thủ hướng dẫn.

### 8.3. Deadline và công việc không còn giá trị

Công việc hết deadline trước khi được chạy nên được loại khỏi hàng đợi theo chính sách, thay vì tiếp tục chiếm năng lực để tạo kết quả không còn hữu ích. Deadline do client gửi phải được giới hạn và xác minh; client không được xin một thời hạn vô hạn để giữ tài nguyên.

Với công việc đã chạy, việc hủy phải tuân theo điểm an toàn. Nếu request kết thúc nhưng tác vụ nền hoặc lời gọi từ xa vẫn tồn tại, hệ thống phải tiếp tục hạch toán tài nguyên đó cho đến khi thực sự được giải phóng.

## 9. Giảm chất lượng và giữ nguyên các bảo đảm bảo mật

Thay vì từ chối toàn bộ một request, hệ thống đôi khi có thể trả kết quả giảm chất lượng. Ví dụ, tạm bỏ thành phần gợi ý tùy chọn hoặc trả dữ liệu cache trong một khoảng tuổi được phép. Đây là chính sách riêng cần được phê duyệt cho từng loại dữ liệu và thao tác.

| Hành vi suy giảm | Điều kiện cần đặc tả |
|---|---|
| Bỏ tính năng tùy chọn | Kết quả cốt lõi vẫn đúng và người dùng nhận biết phần bị thiếu khi cần |
| Trả dữ liệu cache | Tuổi tối đa, phạm vi quyền và điều kiện vô hiệu hóa cache |
| Giảm độ chi tiết báo cáo | Trường được phép bỏ và cách biểu thị mức đầy đủ |
| Hoãn xử lý nền | Thời hạn trì hoãn, nơi lưu chờ và trạng thái công việc |
| Chuyển sang chế độ chỉ đọc | Phạm vi thao tác bị chặn và hành vi với giao dịch đang chạy |

Không giảm chi phí bằng cách bỏ xác thực, bỏ phân quyền tenant, tắt xác minh tính toàn vẹn hoặc dùng quyền đã bị thu hồi. Tương tự, không coi việc trả dữ liệu nhạy cảm từ cache mà thiếu kiểm tra quyền là một phương án duy trì sẵn sàng hợp lệ.

Với thao tác bắt buộc có audit, cần quy định hành vi khi không thể ghi audit. Tùy yêu cầu nghiệp vụ, hệ thống có thể từ chối thao tác hoặc ghi qua kênh bền vững đã được thiết kế. Không để chế độ quá tải tự động bỏ dấu vết kiểm toán mà không có hợp đồng.

Việc loại tải có chủ đích phải bảo toàn ý nghĩa kết quả: thành công, suy giảm, từ chối trước thực thi, đã tiếp nhận, thất bại trong thực thi và kết quả chưa xác định cần được phân biệt khi có ý nghĩa nghiệp vụ.

## 10. Phạm vi phân tán và khả năng phục hồi

### 10.1. Chính sách local không tự trở thành chính sách toàn cụm

Mỗi instance có thể biết tài nguyên cục bộ của mình và loại tải để tự bảo vệ. Tuy nhiên, giới hạn tenant hoặc năng lực của một dependency dùng chung cần phạm vi rộng hơn nếu muốn cam kết toàn cụm.

Nếu một tenant được phép tối đa 10 công việc trên mỗi instance, ba instance có thể tiếp nhận tổng cộng 30 công việc của tenant đó. Không được mô tả cấu hình này là “tối đa 10 toàn hệ thống”. Autoscaling và rolling deployment còn có thể làm tổng thay đổi.

Đặc tả cần chọn cách phân bổ ngân sách: điều phối dùng chung, các phần năng lực được cấp có kiểm soát hoặc giới hạn tại tài nguyên đích. Nếu cho phép sai số trong lúc lỗi, phải nêu rõ phạm vi và hậu quả; không tuyên bố một trần cứng mà cơ chế chưa bảo đảm được.

### 10.2. Bộ điều khiển hoặc nơi lưu chính sách bị lỗi

Phải xác định chính sách nào được dùng khi không tải được cấu hình mới, khi phiên bản không nhất quán hoặc khi mất liên lạc với bộ điều phối. Một phương án là giữ cấu hình hợp lệ gần nhất trong thời hạn cho phép, kết hợp trần cục bộ an toàn đã được phân bổ.

Không để từng instance tự cấp lại toàn bộ ngân sách chung khi mất điều phối. Phần năng lực đã được các worker khác sử dụng vẫn phải được tính. Nếu không chứng minh được phần năng lực còn an toàn, hệ thống cần hạn chế cấp mới theo hợp đồng dự phòng.

### 10.3. Health check và năng lực vận hành

Cần giữ đủ năng lực cho đo lường sức khỏe, điều khiển và phục hồi, đồng thời bảo vệ các đường này bằng quyền và giới hạn phù hợp. Một endpoint được gắn nhãn “health” không nên trở thành đường chạy công việc tốn kém không giới hạn.

Phân biệt tiến trình còn sống, có thể nhận thêm tải và đang giảm tải. Nếu tải cao bị diễn giải thành tiến trình hỏng rồi gây khởi động lại liên tục, hệ thống có thể mất thêm năng lực đúng lúc cần phục hồi.

Việc loại một instance khỏi tuyến nhận tải cần được phối hợp với phần còn lại. Nếu mọi instance đồng loạt rút khỏi tuyến chỉ vì cùng một dependency chậm, lớp định tuyến có thể hết nơi phục vụ. Yêu cầu phải xác định trạng thái và phản ứng của từng tầng thay vì để chúng khuếch đại lẫn nhau.

### 10.4. Phục hồi dần và nạp lại công việc

Khi tín hiệu trở lại an toàn, không nhất thiết mở ngay toàn bộ lưu lượng hoặc giải phóng mọi job chờ cùng lúc. Cần có tốc độ tăng lại, bước đánh giá và điều kiện quay lại giảm tải.

Các tác vụ được hoãn, message gửi lại và client retry đều tiêu thụ năng lực trong giai đoạn phục hồi. Chúng phải tiếp tục chịu giới hạn và ưu tiên. Tránh coi tải phục hồi là một nguồn đặc biệt được vượt qua mọi kiểm soát.

Nếu đã bỏ công việc theo chính sách, trạng thái và hậu quả phải có thể truy vết. Nếu cam kết giữ công việc để xử lý sau, cần kiểm chứng rằng nó vẫn tồn tại và không bị chạy trùng hoặc mất sau khi hệ thống khôi phục.

## 11. Quan sát hiệu quả mà không che giấu thất bại

### 11.1. Các chỉ số tối thiểu

| Nhóm | Chỉ số cần định nghĩa |
|---|---|
| Đầu vào | Số yêu cầu tới điểm đo, lớp công việc, phạm vi và trạng thái hợp lệ |
| Admission | Số được chạy, số vào hàng đợi, số bị loại theo lý do |
| Tài nguyên | Công việc đang chạy, độ dài và dung lượng queue, tuổi chờ, tài nguyên còn lại |
| Kết quả | Thành công, thất bại, timeout, hủy, chưa xác định kết quả và kết quả suy giảm |
| Chính sách | Chế độ hiện tại, phiên bản, lý do kích hoạt và thời gian ở mỗi trạng thái |
| Phục hồi | Tải tăng lại, công việc hoãn còn lại, số lần quay lại trạng thái quá tải |

Phải phân biệt quyết định admission với kết quả cuối. Một request được nhận chạy chưa phải là một request thành công; một job vào hàng đợi cũng chưa hoàn thành nghiệp vụ.

Ví dụ tỷ lệ loại tải tại một điểm admission:

```text
shedding_ratio = số quyết định từ chối do thiếu năng lực
                 / số yêu cầu đủ điều kiện được đánh giá tại điểm đó
```

Hợp đồng chỉ số phải định nghĩa “đủ điều kiện”, cửa sổ thời gian, cách đếm retry và các lý do từ chối khác. Nếu mỗi lần thử được đếm riêng, tỷ lệ này mô tả lần thử, không mô tả số người dùng hoặc số giao dịch duy nhất bị ảnh hưởng.

Khi mẫu số bằng 0, hiển thị không có mẫu hoặc không áp dụng theo ngữ cảnh, không diễn giải 0% như bằng chứng đang phục vụ tốt. Những yêu cầu bị mất trước điểm đo cần được quan sát ở tầng tương ứng; chỉ số của ứng dụng không tự bao phủ chúng.

### 11.2. Không làm đẹp SLO bằng cách bỏ request bị loại

Độ trễ của các request được tiếp nhận có thể giảm khi hệ thống loại nhiều tải. Đây là tín hiệu có ích nhưng chưa chứng minh trải nghiệm chung đã tốt lên. Cần đặt cạnh tỷ lệ tiếp nhận, tỷ lệ thành công và kết quả của từng lớp công việc.

Với mục tiêu sẵn sàng cho yêu cầu hợp lệ, không tự loại các request bị shedding khỏi mẫu đánh giá chỉ vì việc từ chối là có chủ đích. Những ngoại lệ phải được quy định trong hợp đồng SLO. Có thể đồng thời theo dõi:

- Mục tiêu độ trễ của công việc được tiếp nhận.
- Mục tiêu kết quả cho toàn bộ yêu cầu hợp lệ thuộc phạm vi cam kết.
- Mức bảo vệ riêng cho luồng nghiệp vụ quan trọng trong một tải đầu vào xác định.

Số đo chỉ dựa vào request đã hoàn tất cũng có thể bỏ sót công việc treo. Cần quan sát số đang chạy, tuổi công việc và deadline để không hiểu nhầm hệ thống khỏe vì chỉ những request nhanh mới có kết quả đo.

### 11.3. Logging và audit có ngân sách

Ghi một log chi tiết cho mỗi request bị từ chối trong một đợt tải lớn có thể tạo thêm quá tải. Có thể dùng bộ đếm đầy đủ kết hợp sự kiện lấy mẫu hoặc tổng hợp, nhưng phải công bố chính sách để người điều tra không coi mẫu log là toàn bộ số sự kiện.

Không ghi token, bí mật hoặc payload nhạy cảm vào log giảm tải. Các nhãn metric cần được giới hạn để tránh số lượng chuỗi đo tăng không kiểm soát theo đầu vào của đối tượng gây tải.

Thay đổi ngưỡng, lớp ưu tiên, ngoại lệ, chế độ cưỡng bức và thao tác vận hành phải có audit theo chính sách. Bản ghi nên có người thực hiện, phạm vi, phiên bản trước và sau, lý do, thời điểm và kết quả.

## 12. Bộ yêu cầu minh họa có thể kiểm chứng

Giả sử một dịch vụ có ba lớp A, B, C như phần trước. Bộ yêu cầu dưới đây minh họa cách nối rủi ro, kiến trúc và tiêu chí kiểm thử. Các con số cần được xác nhận bằng hồ sơ năng lực của dự án trước khi dùng làm cam kết thực tế.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| LS-01 | Chính sách phải xác định workload, tài nguyên, phạm vi instance hoặc toàn cụm, chủ sở hữu và phiên bản | Đối chiếu cấu hình với điểm admission và tài liệu rủi ro |
| LS-02 | Request bị từ chối trước thực thi không được bắt đầu truy vấn nặng, tạo job hoặc phát sinh tác động nghiệp vụ được bảo vệ | Dấu vết tại worker, DB hoặc bộ tạo job trong bài thử quá tải |
| LS-03 | Lớp ưu tiên phải do máy chủ suy ra từ thao tác và quyền đã xác minh; giả mạo metadata không được nâng lớp | Gửi request cùng thao tác với header ưu tiên và tenant khác nhau |
| LS-04 | Tại phạm vi thực thi được cam kết, hệ thống không vượt trần 80 công việc chạy và 200 mục chờ; mỗi mục chờ chỉ giữ metadata trong ngân sách đã định | Đối chiếu công việc thực, queue và dung lượng trong tải burst |
| LS-05 | Chế độ giảm tải động được kích hoạt khi tuổi lớn nhất của công việc chờ vượt 200 ms trong 3 mẫu hợp lệ liên tiếp cách nhau 1 giây; trần cứng vẫn áp dụng ngay cả khi chưa đủ 3 mẫu | Điều khiển đầu vào và mốc đo, đối chiếu chuyển trạng thái với trần cứng |
| LS-06 | Chỉ bắt đầu phục hồi khi tuổi chờ lớn nhất dưới 80 ms và các tín hiệu tài nguyên được chỉ định đều an toàn trong 10 giây liên tục; queue rỗng có tuổi chờ bằng 0 nếu dữ liệu còn hợp lệ | Bài thử dao động quanh ngưỡng và chuỗi mẫu phục hồi |
| LS-07 | Không dùng mẫu quá hạn để kết luận hệ thống khỏe; giới hạn độ mới và chính sách tĩnh dự phòng phải được cấu hình, có trạng thái hiển thị và cảnh báo | Ngừng cập nhật telemetry trong lúc có tải |
| LS-08 | Hợp đồng phản hồi phải phân biệt thiếu năng lực, vượt quota và kết quả nghiệp vụ chưa xác định; retry phải có ngân sách | Đối chiếu API, client và số lần thử tới backend |
| LS-09 | Không âm thầm bỏ job hoặc message đã được xác nhận tiếp nhận; mọi trạng thái hủy, thất bại và hoãn phải tuân theo hợp đồng nghiệp vụ | Đối chiếu dữ liệu bền vững trước, trong và sau quá tải |
| LS-10 | Chế độ giảm tải không được bỏ xác thực, phân quyền, cách ly tenant hoặc audit bắt buộc của thao tác nhạy cảm | Kiểm thử truy cập trái quyền và lỗi hệ thống audit khi giảm tải |
| LS-11 | Khi phục hồi, việc tăng tiếp nhận và nạp công việc hoãn phải theo tốc độ được phê duyệt; mọi công việc vẫn chịu trần tài nguyên | Bài thử mở lại lưu lượng cùng retry và backlog |
| LS-12 | Báo cáo phải thể hiện số bị loại, số được tiếp nhận, kết quả cuối và phiên bản chính sách theo cùng phạm vi thời gian | Đối chiếu bộ đếm, dấu vết và tập request có định danh |

Đối với LS-04, cần hoàn thiện giới hạn dung lượng metadata trước nghiệm thu, không chỉ ghi “nhỏ”. Đối với LS-06 và LS-07, hồ sơ cấu hình phải liệt kê các tín hiệu an toàn, tuổi mẫu tối đa và chính sách dự phòng cụ thể. Đây là những tham số bắt buộc của bản đặc tả triển khai, không phải chỗ để hệ thống tự suy đoán.

Nếu yêu cầu một mức phục vụ tối thiểu cho lớp A, phải bổ sung tỷ lệ thành công hoặc độ trễ cùng hồ sơ tải và điều kiện dependency. Không thể cam kết mọi request lớp A đều thành công với tải lớp A không giới hạn.

## 13. Tiêu chí nghiệm thu và bài kiểm thử

### 13.1. Chứng minh từ chối trước công việc tốn kém

```gherkin
Given hệ thống đang ở chế độ giảm tải đã xác định
And chính sách từ chối công việc lớp C chưa bắt đầu
When một request lớp C hợp lệ tới admission
Then request nhận mã thiếu năng lực theo hợp đồng
And không có truy vấn nặng hoặc job mới được tạo cho request đó
And bộ đếm loại tải ghi đúng lớp và lý do
And phản hồi không tiết lộ hoạt động của tenant khác
```

Phải quan sát tại điểm thực thi hoặc tài nguyên được bảo vệ. Chỉ kiểm tra mã HTTP chưa đủ chứng minh request không tạo công việc phía sau.

### 13.2. Chống giả mạo mức ưu tiên

```gherkin
Given một danh tính chỉ có quyền thực hiện thao tác lớp C
When client thêm header priority=A hoặc internal_call=true
Then mức ưu tiên vẫn được xác định theo quyền thực tế
And request không dùng được phần năng lực dành riêng trái quyền
And các bộ lọc tenant không thay đổi theo metadata chưa xác minh
```

Lặp lại ở API nội bộ có liên quan, đường gọi qua gateway và đường truy cập trực tiếp được đưa vào phạm vi kiểm thử. Ngoại lệ vận hành cũng phải được kiểm tra quyền, thời hạn và audit.

### 13.3. Đánh giá ngưỡng và phục hồi

Với ví dụ LS-05, tạo ba mẫu hợp lệ liên tiếp có tuổi chờ lớn nhất 210 ms, 230 ms và 240 ms. Xác minh hệ thống chuyển sang giảm tải sau mẫu thứ ba theo chu kỳ đã cấu hình.

Sau đó, tạo chuỗi mẫu dưới 80 ms nhưng chèn một mẫu vi phạm trước khi đủ 10 giây. Bộ đếm điều kiện phục hồi phải được xử lý theo chính sách liên tục đã định; không mở tải chỉ vì trung bình cả khoảng thấp. Khi đủ chuỗi an toàn, kiểm tra tốc độ mở lại thay vì chỉ kiểm tra một cờ trạng thái.

Với tải tăng đột ngột trước khi có đủ mẫu kích hoạt, trần cứng vẫn phải giữ được. Cần kiểm tra riêng trường hợp queue rỗng với dữ liệu hợp lệ và trường hợp mất số đo, vì chúng không có cùng ý nghĩa.

### 13.4. Kiểm tra toàn vẹn công việc đã được tiếp nhận

Tạo một job và nhận xác nhận tiếp nhận trước khi bật chế độ giảm tải. Sau đó gây quá tải, timeout client và phục hồi dịch vụ. Đối chiếu trạng thái job, tác động nghiệp vụ và số lần thực thi theo hợp đồng idempotency.

Kết quả cần cho thấy job đã tiếp nhận không bị mất âm thầm, trạng thái không bị ghi sai thành công và một request gửi lại không tạo tác động trùng ngoài chính sách. Nếu hủy được cho phép, phải có trạng thái cùng bằng chứng hoàn tất hoặc hoàn tác phù hợp.

### 13.5. Kiểm tra retry và lỗi lan truyền

Cho dependency phản hồi chậm rồi kiểm tra số lời gọi đồng thời, số retry và tuổi công việc. Client không tuân thủ thời gian chờ cũng không được làm hệ thống vượt trần đã cam kết.

Theo dõi xem tầng gateway, ứng dụng và worker có cùng retry một thao tác hay không. Khi dependency hồi phục, chạy đồng thời backlog và retry để xác minh chính sách mở tải không tạo đỉnh quá tải mới.

### 13.6. Kiểm tra hiệu quả bảo vệ luồng quan trọng

Hồ sơ thử nghiệm phải chốt cấu hình triển khai, dữ liệu, tỷ lệ workload, đặc điểm thời gian xử lý, tình trạng dependency, thời gian tăng tải và thời lượng duy trì. Có thể dùng mô hình 1.200 đơn vị/giây ở phần trước làm điểm bắt đầu, nhưng cần đo chi phí thực trước khi chốt ngưỡng nghiệm thu.

Trong cùng bài thử, đối chiếu tỷ lệ thành công và độ trễ từng lớp với trần tài nguyên và tỷ lệ bị loại. Không chỉ chứng minh độ trễ của request được nhận chạy giảm xuống. Nếu không có mục tiêu định lượng cho lớp A và hồ sơ tải tương ứng, chưa thể kết luận chính sách đã đáp ứng cam kết bảo vệ lớp đó.

### 13.7. Kiểm tra lỗi điều khiển và telemetry

Các tình huống tối thiểu gồm mất số đo, mẫu đến muộn, cấu hình lỗi, lệch phiên bản giữa instance, mất bộ điều phối và instance mới tham gia trong khi đã quá tải.

Xác minh hệ thống không tự mở toàn bộ admission, không nhân ngân sách chung và không dùng dữ liệu cũ như bằng chứng phục hồi. Người vận hành phải nhìn thấy chế độ dự phòng, nguyên nhân và phiên bản đang dùng.

## 14. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Hệ quả | Cách làm rõ |
|---|---|---|
| “CPU cao thì trả lỗi” | Có thể kích hoạt sai phạm vi hoặc quá muộn | Gắn tín hiệu với tài nguyên, chu kỳ đo và điều kiện chuyển trạng thái |
| “Loại ngẫu nhiên 30% là đủ” | Không bảo đảm cách ly tenant hay mức phục vụ lớp quan trọng | Định nghĩa phân bổ, trần và chính sách công bằng |
| “Request đã trả 503 nên không có tác động” | Công việc có thể đã chạy hoặc ghi dữ liệu | Phân biệt từ chối trước thực thi với kết quả chưa xác định |
| “Lớp ưu tiên cao không bị giới hạn” | Đường ưu tiên có thể làm cạn hệ thống | Giới hạn cả năng lực dành riêng và tổng tài nguyên |
| “Queue sẽ giữ mọi request đến khi rảnh” | Bộ nhớ, dung lượng và thời gian chờ tăng không giới hạn | Giới hạn số lượng, dung lượng, tuổi chờ và hành vi hết hạn |
| “Autoscaling sẽ giải quyết quá tải” | Năng lực chưa tăng kịp hoặc dependency vẫn nghẽn | Có chính sách giảm tải độc lập trong thời gian chờ |
| “Không có số đo nghĩa là đã hết tải” | Chính sách mở lại khi đang mất khả năng quan sát | Dùng trạng thái chưa xác định và giới hạn dự phòng |
| “Request bị loại không tính vào độ sẵn sàng” | Báo cáo che giấu tác động người dùng | Quy định mẫu SLO và trình bày cả tiếp nhận lẫn kết quả cuối |
| “Ghi toàn bộ log để điều tra” | Đường từ chối trở thành điểm cạn I/O | Dùng bộ đếm, tổng hợp và lấy mẫu có chính sách |
| “Phục hồi là mở lại 100% ngay” | Backlog và retry tạo đợt quá tải tiếp theo | Tăng tải dần, giữ trần và đánh giá lại tín hiệu |

## 15. Đưa load shedding vào vòng đời phát triển

Ở giai đoạn phân tích, xác định luồng nghiệp vụ cần bảo vệ, tài nguyên có thể cạn và hậu quả của việc từ chối từng loại công việc. Liên kết chính sách với kịch bản đe dọa, tenant và cam kết dịch vụ.

Ở giai đoạn thiết kế, hoàn thiện phân lớp ưu tiên, điểm admission, hợp đồng phản hồi, giới hạn cứng, bộ điều khiển động và hành vi dự phòng. Quy định rõ trách nhiệm của gateway, ứng dụng, worker, client và hệ thống giám sát.

Ở giai đoạn triển khai và nghiệm thu, gắn yêu cầu với cấu hình có phiên bản và các bài kiểm thử tải, quyền truy cập, toàn vẹn dữ liệu, lỗi dependency và phục hồi. Đối chiếu bằng chứng từ nơi quyết định admission với nơi thực thi thật.

Ở giai đoạn vận hành, theo dõi tác động từng lớp, tỷ lệ bị loại, thời gian suy giảm và mức ổn định sau phục hồi. Mọi thay đổi về workload, retry, số instance, schema dữ liệu hoặc dependency có thể làm thay đổi năng lực; cần đánh giá lại ngưỡng thay vì giữ chúng vô thời hạn.

Các ngoại lệ khẩn cấp cần có người chịu trách nhiệm, thời hạn và cách quay về chính sách đã duyệt. Việc tắt shedding để xử lý một phản ánh người dùng cũng có thể làm ảnh hưởng toàn bộ hệ thống, nên phải có cơ sở năng lực và dấu vết quyết định.

## 16. Bài tập tự kiểm tra

Một dịch vụ có chính sách “nếu CPU vượt 85% thì trả 503 cho 40% request”. Mọi request được đọc đầy đủ vào bộ nhớ và truy vấn quyền từ DB trước khi kiểm tra CPU. Client tự đặt header ưu tiên; request có header này không bị loại. Mỗi lần nhận 503, ba tầng đều thử lại ngay. Khi mất telemetry, bộ điều khiển coi CPU là 0 và mở toàn bộ lưu lượng. Dashboard chỉ đo độ trễ của request thành công.

Hãy thực hiện các việc sau:

1. Chỉ ra những tài nguyên và đường ưu tiên vẫn có thể bị làm cạn.
2. Viết lại điểm kiểm soát trước xác thực và sau xác thực theo đúng ranh giới tin cậy.
3. Định nghĩa các lớp công việc, trần tài nguyên và hành vi khi riêng lớp quan trọng vượt năng lực.
4. Đặc tả điều kiện kích hoạt, điều kiện phục hồi và chính sách khi số đo không hợp lệ.
5. Viết hợp đồng từ chối và retry cho cả client lẫn các tầng nội bộ.
6. Xác định chỉ số cần bổ sung để đánh giá trải nghiệm của toàn bộ yêu cầu hợp lệ.
7. Viết hai bài kiểm thử: giả mạo ưu tiên và phục hồi đồng thời với backlog cùng retry.

Một lời giải đầy đủ phải nối được quyết định loại tải với tài nguyên thực, quyền được ưu tiên, trạng thái nghiệp vụ và bằng chứng đo lường. Load shedding đáp ứng yêu cầu bảo mật khi nó giữ được các bảo đảm đã cam kết trong phạm vi tải xác định, đồng thời biểu thị trung thực phần công việc không thể phục vụ.
