# Availability requirement — Đặc tả yêu cầu tính sẵn sàng

## 1. Mục tiêu và vị trí trong yêu cầu bảo mật

**Availability requirement** là yêu cầu mô tả một năng lực của hệ thống phải tiếp tục phục vụ ai, trong điều kiện nào, với chất lượng tối thiểu ra sao và trong bao lâu khi có lỗi hoặc hành vi gây gián đoạn. Yêu cầu tốt phải có cách đo và tiêu chí chấp nhận, thay vì chỉ viết “hệ thống luôn sẵn sàng” hoặc “có tính sẵn sàng cao”.

Trong môn đặc tả yêu cầu bảo mật, tính sẵn sàng bảo vệ khả năng sử dụng dịch vụ của chủ thể hợp lệ. Mối đe dọa có thể là lưu lượng gây cạn tài nguyên, thao tác tốn chi phí của một tài khoản đã xác thực, phá hoại dữ liệu, vô hiệu hóa dịch vụ định danh hoặc làm mất khả năng vận hành. Lỗi phần mềm, lỗi hạ tầng và thay đổi cấu hình cũng cần được đưa vào điều kiện kiểm chứng khi chúng gây cùng một hậu quả nghiệp vụ.

Bài học này tập trung vào cách chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành yêu cầu về tính sẵn sàng có thể đo, truy vết và kiểm thử. Sau khi học, người đọc có thể:

- Xác định hành trình nghiệp vụ, người dùng và tài nguyên cần được bảo vệ.
- Viết chỉ số đo, mục tiêu dịch vụ, phạm vi lỗi và ngân sách lỗi rõ ràng.
- Đặc tả hành vi khi quá tải, khi phụ thuộc hỏng và khi phải phục hồi.
- Liên kết yêu cầu với rủi ro, quyết định kiến trúc và bằng chứng nghiệm thu.

Các ngưỡng trong bài là **số liệu minh họa cho một hệ thống giả định**. Chúng cần được hiệu chỉnh theo tác động nghiệp vụ, khả năng vận hành, kinh phí và kết quả kiểm thử của hệ thống thực tế.

## 2. Phân biệt các khái niệm trước khi đặt con số

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Availability — tính sẵn sàng | Người dùng hợp lệ có sử dụng được năng lực cần thiết tại thời điểm cần không? | Người mua có tạo được đơn trong thời hạn cho phép không? |
| Reliability — độ tin cậy | Hệ thống có thực hiện đúng chức năng một cách ổn định trong điều kiện và khoảng thời gian xác định không? | Đơn đã được xác nhận không bị mất hoặc xử lý sai khi chạy lâu dài. |
| Resilience — khả năng chống chịu và phục hồi | Hệ thống duy trì hoặc khôi phục chức năng thế nào khi gặp gián đoạn? | Khi một tiến trình chết, phần còn lại tiếp tục phục vụ và năng lực được khôi phục. |
| SLI — chỉ số mức dịch vụ | Đo trải nghiệm dịch vụ bằng đại lượng nào? | Tỷ lệ yêu cầu tạo đơn hợp lệ được xác nhận đúng trong hai giây. |
| SLO — mục tiêu mức dịch vụ | Chỉ số phải đạt ngưỡng nào trong cửa sổ nào? | SLI đạt ít nhất 99,9% trong mỗi cửa sổ trượt 30 ngày. |
| SLA — thỏa thuận mức dịch vụ | Các bên cam kết gì và xử lý thế nào khi vi phạm? | Thỏa thuận với khách hàng quy định cách đo, ngoại lệ và cơ chế bồi hoàn. |
| RTO — mục tiêu thời gian phục hồi | Cho phép mất bao lâu để khôi phục năng lực sau gián đoạn được xác định? | Khôi phục tạo đơn trong 60 phút kể từ lúc chức năng mất khả dụng. |
| RPO — mục tiêu điểm phục hồi | Chấp nhận mất dữ liệu mới nhất tới mức nào? | Sau sự cố thuộc phạm vi đã thỏa thuận, điểm dữ liệu phục hồi không cũ hơn năm phút trước sự cố. |

Một dịch vụ có tiến trình đang chạy vẫn có thể không khả dụng nếu mọi thao tác đều timeout, kiểm tra quyền bị treo hoặc phản hồi trả về dữ liệu sai. Ngược lại, việc từ chối một yêu cầu không có quyền có thể là hành vi đúng; yêu cầu ấy không đương nhiên thuộc mẫu số trải nghiệm của người dùng hợp lệ.

Tỷ lệ sẵn sàng cao cũng không bảo đảm không có gián đoạn kéo dài. Cùng một lượng lỗi có thể tập trung vào một sự cố nghiêm trọng hoặc rải đều trong tháng. Vì vậy, cần bổ sung ràng buộc về thời gian gián đoạn liên tục, thời gian phát hiện hoặc phục hồi khi tác động nghiệp vụ đòi hỏi.

## 3. Bắt đầu từ tác động nghiệp vụ và mô hình đe dọa

Giả sử một cổng đặt hàng B2B có các chức năng đăng nhập, xem danh mục, tạo đơn và xuất báo cáo. Tạo đơn là năng lực trọng yếu; xuất báo cáo có thể trì hoãn. Người dùng được phân theo tổ chức thuê dịch vụ, gọi là tenant.

Không nên gán một mục tiêu chung cho mọi endpoint chỉ vì chúng nằm trên cùng một máy chủ. Cần xác định riêng hành trình nào bị gián đoạn, ai bị ảnh hưởng và thiệt hại tăng theo thời gian ra sao.

| Tình huống rủi ro | Tác động cần hạn chế | Hướng chuyển thành yêu cầu |
|---|---|---|
| Một tài khoản xuất nhiều báo cáo nặng | Hết CPU hoặc kết nối cơ sở dữ liệu, người khác không tạo đơn được | Giới hạn công việc tốn chi phí và cô lập tài nguyên giữa báo cáo với giao dịch trọng yếu. |
| Một tenant gửi lưu lượng lớn | Tenant khác bị timeout dù vẫn dùng trong hạn mức | Đặt hạn mức có phạm vi và kiểm thử khả năng phục vụ tenant không gây quá tải. |
| Dịch vụ định danh không phản hồi | Không đăng nhập mới được hoặc toàn bộ giao dịch bị treo | Giới hạn thời gian chờ; quy định riêng đăng nhập mới và phiên đang hợp lệ. |
| Một tiến trình ứng dụng bị dừng đột ngột | Yêu cầu đang xử lý thất bại, có nguy cơ gửi lại và tạo đơn trùng | Giới hạn gián đoạn và đặc tả kết quả khi retry bằng cùng khóa idempotency. |
| Lưu lượng từ ngoài vượt khả năng hệ thống | Cạn tài nguyên tại biên hoặc bên trong dịch vụ | Xác định biên lưu lượng được cam kết, hành vi từ chối và năng lực cần duy trì. |
| Tài khoản quản trị bị chiếm dụng và xóa dữ liệu | Dịch vụ ngừng hoạt động, không còn trạng thái đáng tin cậy | Quy định bảo vệ bản phục hồi, phân quyền thao tác và diễn tập khôi phục an toàn. |

Chuỗi truy vết nên có dạng:

> Tài sản và tác động → kịch bản đe dọa → yêu cầu → quyết định kiến trúc → ca kiểm thử → bằng chứng.

Ví dụ: rủi ro một tenant chiếm hết tài nguyên dẫn tới yêu cầu duy trì tạo đơn cho tenant khác trong một kịch bản tải xác định. Quyết định kiến trúc có thể gồm hàng đợi, hạn ngạch hoặc phân vùng tài nguyên. Bằng chứng phải chứng minh kết quả phục vụ, không chỉ chứng minh đã bật một cấu hình giới hạn tốc độ.

## 4. Những thành phần bắt buộc phải làm rõ

Một câu yêu cầu có thể ngắn, nhưng đặc tả đi kèm phải trả lời đầy đủ các điểm sau.

| Thành phần | Nội dung cần xác định |
|---|---|
| Mã và chủ sở hữu | Mã ổn định, người chịu trách nhiệm nghiệp vụ, vận hành và chấp nhận rủi ro. |
| Năng lực được bảo vệ | Hành trình hoặc thao tác cụ thể; ranh giới đầu cuối của phép đo. |
| Người dùng và phạm vi | Tenant, nhóm người dùng, khu vực hoặc kênh truy cập nằm trong cam kết. |
| Điều kiện hợp lệ | Dữ liệu đầu vào, quyền truy cập, trạng thái phiên và hạn mức đã công bố. |
| Điều kiện tải | Tốc độ, mức đồng thời, tỷ lệ thao tác, kích thước dữ liệu và phân bố tenant. |
| Điều kiện gián đoạn | Lỗi đơn, lỗi phụ thuộc, kiểu quá tải hoặc kịch bản tấn công được xét. |
| Chỉ số và ngưỡng | Tử số, mẫu số, thời hạn phản hồi, mục tiêu và cửa sổ đo. |
| Hành vi suy giảm | Chức năng nào được trì hoãn hoặc từ chối; chức năng nào phải duy trì. |
| Ràng buộc bảo mật | Xác thực, phân quyền, tính toàn vẹn, logging và bí mật dữ liệu cần giữ. |
| Nguồn bằng chứng | Điểm đo, log, bộ đếm, truy vấn tính toán và cách phát hiện mất dữ liệu đo. |
| Tiêu chí chấp nhận | Kịch bản kiểm thử, ngưỡng đạt, môi trường và người xác nhận kết quả. |
| Phụ thuộc và ngoại lệ | Phụ thuộc quan trọng, giới hạn trách nhiệm và điều kiện loại trừ minh bạch. |

Mẫu câu có thể dùng:

> Đối với [năng lực] phục vụ [nhóm người dùng], trong [điều kiện tải và lỗi], hệ thống phải đạt [chỉ số, ngưỡng, cửa sổ]; khi không thể đáp ứng phải [hành vi suy giảm], đồng thời duy trì [ràng buộc bảo mật]. Kết quả được kiểm chứng bằng [phép đo và kịch bản].

“Có hai máy chủ”, “dùng nhiều vùng” hoặc “có autoscaling” mô tả giải pháp. Chúng chỉ trở thành yêu cầu thiết kế bắt buộc khi có lý do riêng. Yêu cầu về kết quả phục vụ vẫn cần tồn tại để đánh giá giải pháp đó có hiệu quả hay không.

## 5. Định nghĩa SLI theo trải nghiệm thực tế

### 5.1. Chọn đơn vị đo và ranh giới

Với tạo đơn, có thể định nghĩa một sự kiện đủ điều kiện là một lần gửi yêu cầu qua cổng vào được quản lý, có quyền tạo đơn, dữ liệu đúng và nằm trong hạn mức sử dụng đã cam kết.

Một sự kiện tốt phải đáp ứng đồng thời:

1. Hệ thống trả kết quả xác nhận trong không quá hai giây, tính từ khi cổng vào nhận yêu cầu tới khi cổng vào phát xong phản hồi.
2. Đơn được ghi nhận bền vững theo cam kết của hệ thống trước khi xác nhận thành công.
3. Đơn gắn đúng tenant, đúng chủ thể và không bị nhân đôi khi người dùng gửi lại cùng khóa idempotency trong thời hạn hỗ trợ.
4. Các kiểm soát xác thực và phân quyền bắt buộc đã được thực thi.

Ranh giới trên chưa bao gồm toàn bộ đường truyền tới thiết bị người dùng. Nếu cam kết bao gồm trải nghiệm từ một khu vực truy cập, cần thêm phép đo bên ngoài từ khu vực đó và ghi rõ giới hạn của phép đo.

Trạng thái HTTP thành công chỉ là một tín hiệu. Phản hồi thành công nhưng đơn không tồn tại, thuộc sai tenant hoặc bị tạo trùng phải được coi là lỗi khi đánh giá tính đúng của hành trình. Việc đối soát tính đúng có thể đến muộn hơn phép đo độ trễ; quy tắc cập nhật kết quả SLI cần được xác định trước.

### 5.2. Công thức theo sự kiện

~~~text
SLI = số sự kiện tốt / tổng số sự kiện đủ điều kiện

Sự kiện tốt = đúng chức năng
              AND đúng kiểm soát bảo mật
              AND hoàn thành trong thời hạn
~~~

Ví dụ một cửa sổ có 2.000.000 sự kiện đủ điều kiện và 1.998.400 sự kiện tốt:

~~~text
SLI = 1.998.400 / 2.000.000 = 99,92%
~~~

Với mục tiêu 99,9%, cửa sổ này đạt yêu cầu về tỷ lệ. Tuy nhiên, vẫn phải kiểm tra các ràng buộc bổ sung như thời gian gián đoạn liên tục hoặc tác động riêng lên một tenant.

Một yêu cầu retry cần có quy tắc đếm nhất quán. Nếu đơn vị đo là từng lần thử thì mỗi lần thử hợp lệ đều được tính. Nếu đo theo giao dịch nghiệp vụ duy nhất thì phải có định danh và quy tắc gộp. Không được thay đổi cách gộp sau sự cố để làm chỉ số đẹp hơn.

### 5.3. Không để cách phân loại che mất lỗi

- Yêu cầu không có quyền hoặc dữ liệu sai theo hợp đồng API có thể được loại khỏi SLI nghiệp vụ, nhưng vẫn cần quan sát để phát hiện tấn công và lỗi tích hợp.
- Yêu cầu hợp lệ nằm trong hạn mức mà nhận mã từ chối do hệ thống cạn tài nguyên phải được tính là lỗi phục vụ.
- Không được loại yêu cầu chỉ vì chúng đã timeout trước khi tới ứng dụng. Bộ đếm cần quan sát được tại biên đã chọn.
- Khi dịch vụ xác thực lỗi, không thể kết luận mọi yêu cầu bị từ chối đều là “người dùng không hợp lệ”. Cần dữ liệu kiểm thử có danh tính biết trước và phương pháp đối soát lỗi xác thực.
- Lưu lượng tấn công nằm ngoài mẫu số trải nghiệm người dùng hợp lệ vẫn phải được ghi nhận trong chỉ số tấn công và tác động lên hạ tầng.
- Khoảng mất telemetry phải được thể hiện là thiếu bằng chứng, kèm cách xử lý đã thống nhất; không mặc nhiên tính là hoạt động tốt.

Đánh giá theo tenant hoặc khu vực khi tác động có thể không đồng đều. Chỉ số tổng hợp 99,9% có thể che việc một tenant nhỏ mất toàn bộ khả năng sử dụng dịch vụ.

### 5.4. Khi nào dùng chỉ số theo thời gian?

Với chức năng được kiểm tra định kỳ, có thể dùng:

~~~text
Availability theo thời gian
  = thời gian được xác nhận khả dụng / thời gian nằm trong phạm vi đo
~~~

Phải mô tả tần suất probe, nơi chạy probe, thao tác được kiểm tra, điều kiện xác nhận lỗi và quy tắc suy ra thời điểm bắt đầu, kết thúc gián đoạn. Probe chỉ kiểm tra trang chủ không chứng minh thao tác tạo đơn hoạt động.

Nhiều sự cố chồng lấn trong cùng một khoảng thời gian không được cộng thành nhiều lần thời gian ngừng phục vụ của cùng một phạm vi. Đồng thời, probe thưa có thể bỏ sót gián đoạn ngắn; độ chính xác phép đo phải phù hợp với ngưỡng cần chứng minh.

Không quy đổi trực tiếp tỷ lệ lỗi theo sự kiện thành số phút downtime nếu chưa có giả định về phân bố lưu lượng. Hai cách đo trả lời những câu hỏi khác nhau.

## 6. Đặt mục tiêu và ngân sách lỗi

Với SLO tính theo thời gian, trong một cửa sổ cố định 30 ngày, nếu toàn bộ thời gian đều thuộc phạm vi cam kết:

| Mục tiêu | Tỷ lệ thời gian lỗi tối đa | Thời gian lỗi tối đa trong 30 ngày |
|---|---:|---:|
| 99,9% | 0,1% | 43 phút 12 giây |
| 99,95% | 0,05% | 21 phút 36 giây |
| 99,99% | 0,01% | 4 phút 19,2 giây |

Với SLO theo sự kiện, ngân sách lỗi được tính bằng số sự kiện:

~~~text
Ngân sách lỗi = (1 - SLO) × số sự kiện đủ điều kiện
~~~

Trong ví dụ 2.000.000 sự kiện, mục tiêu 99,9% cho phép tối đa 2.000 sự kiện không tốt. Có 1.600 sự kiện không tốt nghĩa là đã dùng 80% ngân sách của cửa sổ ấy. Với cửa sổ trượt, tổng sự kiện và các sự kiện lỗi thay đổi khi dữ liệu đi vào hoặc ra khỏi cửa sổ; đây không phải một hạn mức cố định tồn tại mãi.

Cần thống nhất thêm:

- Dùng tháng lịch hay cửa sổ trượt; mốc thời gian và múi giờ tính toán.
- Bảo trì có được tính là gián đoạn hay không. Nếu có loại trừ thì phải chỉ rõ khoảng, cách thông báo và tác động; vẫn nên quan sát trải nghiệm tổng thể.
- Mục tiêu riêng cho chức năng trọng yếu hoặc nhóm khách hàng có yêu cầu khác nhau.
- Ngưỡng cảnh báo khi ngân sách bị tiêu thụ nhanh và ai phải xử lý.
- Quyết định vận hành khi ngân sách gần hết, chẳng hạn ưu tiên sửa lỗi hoặc hoãn thay đổi làm tăng rủi ro.

Độ trễ nên được đưa vào định nghĩa sự kiện tốt hoặc một SLO riêng. Trung bình thấp có thể che nhiều người dùng chờ quá lâu. Nếu dùng percentile, phải ghi rõ tập mẫu và cửa sổ; không lấy trung bình các giá trị p99 của nhiều máy để coi là p99 chung.

## 7. Đặc tả điều kiện tải và lỗi

Một cam kết “chịu được 1.000 request/giây” còn thiếu nhiều thông tin. Một request đọc dữ liệu nhỏ khác xa một request xuất báo cáo lớn. Cùng tổng lưu lượng nhưng dồn vào một tenant hoặc một khóa dữ liệu nóng có thể gây hậu quả khác.

Đặc tả tải cần mô tả ít nhất:

- Tốc độ và mức đồng thời của từng nhóm thao tác, cùng thời gian duy trì.
- Kích thước yêu cầu, khối lượng dữ liệu và các trường hợp tốn chi phí.
- Phân bố tenant, kết nối và tài khoản; trạng thái cache đầu thử nghiệm.
- Cách phát tải: giữ tốc độ gửi hay chờ phản hồi rồi mới gửi tiếp.
- Vị trí phát tải, năng lực bộ phát tải và điểm bắt đầu đo.
- Lưu lượng hợp lệ cần bảo vệ, lưu lượng gây nhiễu và quy tắc nhận diện chúng.

Bộ phát tải chờ mỗi phản hồi rồi mới gửi tiếp có thể tự giảm tải khi hệ thống chậm. Kết quả vì thế có thể bỏ sót mức quá tải mà người dùng thực tế tạo ra. Cần chọn mô hình phù hợp và báo cáo cả số yêu cầu dự kiến gửi, thực sự gửi và bị rơi tại bộ phát tải.

Phạm vi lỗi cũng phải cụ thể:

| Tình huống | Điều cần ghi rõ |
|---|---|
| Mất một tiến trình | Dừng tiến trình nào, đột ngột hay có drain, số tiến trình còn lại và trạng thái giao dịch đang chạy. |
| Phụ thuộc bị chậm | Thêm độ trễ bao nhiêu, tỷ lệ yêu cầu bị ảnh hưởng, có timeout hay mất kết nối không. |
| Mất cơ sở dữ liệu ghi | Chế độ failover, ngữ nghĩa giao dịch đã xác nhận, khả năng đọc và ghi trong chuyển đổi. |
| Cạn kết nối hoặc hàng đợi | Giới hạn tài nguyên, hành vi khi đầy, thời gian tối đa một tác vụ được chờ. |
| Mất một vùng triển khai | Vùng nào, tài nguyên phụ thuộc có chung vùng không, các điều kiện ngoài phạm vi. |
| Gián đoạn dịch vụ định danh | Ảnh hưởng đến đăng nhập mới, phiên hiện hữu, kiểm tra thu hồi quyền và thao tác nhạy cảm. |

Không suy ra khả năng chịu lỗi toàn vùng từ một bài thử dừng một tiến trình. Không suy ra khả năng chống mọi cuộc tấn công từ một bài thử tăng request tại tầng ứng dụng. Nếu lưu lượng làm đầy đường truyền trước điểm kiểm soát, cơ chế giới hạn trong ứng dụng không thể tự bảo đảm khả năng truy cập.

## 8. Ví dụ một bộ yêu cầu có thể kiểm chứng

Giả định chủ nghiệp vụ xác định tạo đơn là năng lực trọng yếu. Các mã dưới đây minh họa cách tách yêu cầu để mỗi yêu cầu có bằng chứng riêng.

### SR-AVL-001 — Khả dụng của hành trình tạo đơn

Trong mỗi cửa sổ trượt 30 ngày, ít nhất 99,9% lần thử tạo đơn đủ điều kiện qua cổng vào được quản lý phải được xác nhận đúng trong hai giây. Tính đúng và ranh giới đo tuân theo mục 5. Thời gian bảo trì được tính trong chỉ số này.

Phạm vi phục vụ gồm các tenant đã kích hoạt, có quyền tạo đơn và đang dùng trong hạn mức được công bố. Những lần thử đủ điều kiện bị từ chối vì thiếu tài nguyên hoặc lỗi phụ thuộc được tính là lỗi.

Bằng chứng gồm bộ đếm tại cổng vào, log kết quả giao dịch, đối soát đơn theo tenant và truy vấn tính SLI có phiên bản. Mục tiêu vận hành 30 ngày được theo dõi sau triển khai; một bài thử ngắn chỉ cung cấp bằng chứng trong điều kiện thử, không tự chứng minh toàn bộ SLO vận hành.

### SR-AVL-002 — Cô lập lưu lượng gây cạn tài nguyên

Trong môi trường nghiệm thu đã mô tả cấu hình và dữ liệu, hệ thống phải phục vụ luồng tạo đơn hợp lệ 200 lần/giây trong 60 phút. Trong 15 phút giữa bài thử, bổ sung 1.000 lần/giây từ nhóm tài khoản gây nhiễu, gửi vượt hạn mức đã công bố của nhóm đó.

Ít nhất 99,9% lần thử hợp lệ của các tenant được bảo vệ phải thành công đúng trong hai giây, tính trên chính khoảng 15 phút có gây nhiễu. Lưu lượng trước và sau khoảng này được báo cáo riêng để không che tác động bằng thời gian hệ thống hoạt động bình thường.

Yêu cầu vượt hạn mức có thể bị từ chối bằng phản hồi đã đặc tả. Hàng đợi, bộ nhớ và kết nối phải có giới hạn đã cấu hình; không được bỏ kiểm tra quyền để tăng tỷ lệ thành công. Bộ phát tải phải chứng minh đã gửi đủ tải theo kế hoạch và không tự trở thành nút thắt.

Với 200 lần/giây được phát đủ trong 15 phút, có 180.000 lần thử hợp lệ; ngưỡng 99,9% tương ứng tối đa 180 lần không tốt. Bài thử này chứng minh một kịch bản cạn tài nguyên đã xác định, chưa phải cam kết chịu mọi dạng DDoS.

### SR-AVL-003 — Hành vi khi phụ thuộc định danh không phản hồi

Khi dịch vụ định danh không phản hồi trong bài thử kéo dài mười phút:

- Các lần đăng nhập mới phải kết thúc bằng phản hồi thành công hoặc lỗi tạm thời được đặc tả trong tối đa ba giây tại ranh giới đo; không chờ vô hạn.
- Đăng nhập thất bại do phụ thuộc được ghi nhận trong SLI đăng nhập, kể cả khi phản hồi lỗi được trả đúng hạn.
- Thao tác bắt buộc phải xác minh quyền trực tuyến phải bị từ chối an toàn nếu không thể xác minh; lỗi không được dẫn tới cấp quyền mặc định.
- Phiên hiện hữu chỉ tiếp tục dùng được trong phạm vi chính sách đã phê duyệt về hiệu lực, kiểm tra chữ ký và khả năng thu hồi. Yêu cầu này không tự tạo ngoại lệ cho xác thực hoặc phân quyền.
- Lỗi phải sinh sự kiện vận hành có mã tương quan; thông tin hiển thị cho người dùng không chứa token hoặc chi tiết nội bộ nhạy cảm.

Bằng chứng phải tách đăng nhập mới, phiên đang hợp lệ, phiên hết hạn và chủ thể đã bị thu hồi quyền. Một phản hồi từ chối nhanh bảo vệ tài nguyên nhưng không được ghi nhận thành công cho hành trình đăng nhập.

### SR-AVL-004 — Phục hồi sau sự cố thuộc phạm vi đã chọn

Với kịch bản mất vùng triển khai chính và các nguồn phục hồi được giả định vẫn truy cập được, năng lực tạo đơn phải được khôi phục trong 60 phút. Điểm bắt đầu là thời điểm phép đo độc lập xác định năng lực mất khả dụng; điểm kết thúc là khi kiểm thử giao dịch đúng và kiểm tra bảo mật bắt buộc đều đạt trên hệ thống phục hồi.

Điểm dữ liệu phục hồi phải không cũ hơn năm phút trước thời điểm sự cố theo bộ giao dịch đối chứng. Yêu cầu này chấp nhận khả năng mất một phần dữ liệu gần sự cố; chủ nghiệp vụ phải chấp nhận mức mất đó và quy định cách đối soát các đơn đã được thông báo thành công.

Nếu nghiệp vụ không chấp nhận mất bất kỳ đơn đã xác nhận nào, phải đặt yêu cầu riêng về độ bền và RPO cho các đơn ấy, đồng thời chứng minh cơ chế ghi nhận đáp ứng được. Không được giữ RPO năm phút rồi diễn giải thành “không mất dữ liệu”.

Kịch bản mã độc làm hỏng dữ liệu trong thời gian dài cần một yêu cầu phục hồi riêng, vì bản sao mới nhất có thể đã bị nhiễm hoặc chứa trạng thái sai. Mục tiêu của sự cố hạ tầng không tự chứng minh có thể phục hồi an toàn sau xâm nhập.

## 9. Thiết kế chế độ suy giảm mà vẫn giữ bảo mật

Chế độ suy giảm phải được mô tả trước sự cố. Mục tiêu là dành tài nguyên cho năng lực cần thiết và cho người dùng biết trạng thái giao dịch rõ ràng.

| Chức năng | Hành vi suy giảm có thể đặc tả | Ràng buộc phải giữ |
|---|---|---|
| Xem danh mục công khai | Phục vụ bản cache không quá độ cũ đã chấp nhận | Không dùng cache công khai cho dữ liệu riêng của tenant. |
| Xem dữ liệu riêng | Chỉ dùng cache khi quyền và độ cũ đáp ứng chính sách | Không rò dữ liệu giữa tenant hoặc giữ quyền đã bị thu hồi vượt giới hạn cho phép. |
| Xuất báo cáo | Xếp hàng hữu hạn, trì hoãn hoặc từ chối khi đầy | Giới hạn tài nguyên, thời gian lưu và quyền truy cập tệp kết quả. |
| Tạo đơn | Ưu tiên tài nguyên; từ chối rõ ràng khi không thể xử lý đúng | Không báo thành công nếu chưa đạt cam kết ghi nhận; chống tạo trùng khi retry. |
| Thay đổi quyền hoặc thao tác nhạy cảm | Tạm dừng nếu không thể kiểm tra điều kiện bảo mật bắt buộc | Không cho phép bỏ qua kiểm tra chỉ vì phụ thuộc hỏng. |
| Ghi log bảo mật | Dùng bộ đệm hữu hạn hoặc cơ chế lưu dự phòng theo chính sách | Không âm thầm bỏ audit bắt buộc; không ghi bí mật để bù thiếu khả năng quan sát. |

Nếu một thao tác chỉ được phép hoàn tất khi audit được lưu bền vững, yêu cầu phải nói rõ thao tác sẽ thất bại hoặc bị tạm dừng khi không thể đáp ứng điều đó. Với loại log chẩn đoán có thể mất một phần, cần quy định mức mất chấp nhận được và cảnh báo tương ứng.

Cơ chế retry phải có giới hạn số lần, tổng thời gian và khoảng chờ phù hợp. Nhiều tầng cùng retry có thể nhân lưu lượng lên và kéo dài sự cố. Yêu cầu nên ràng buộc ngân sách retry toàn hành trình và kết quả giao dịch, thay vì chỉ yêu cầu “tự động retry”.

Các lựa chọn như timeout, circuit breaker, bulkhead, hạn ngạch hay backpressure là phương tiện thiết kế. Giá trị của chúng được đánh giá bằng việc giảm tác động, giữ đúng quyền và đáp ứng tiêu chí đã đặc tả.

## 10. Đặc tả phục hồi sâu hơn việc “có backup”

Backup chỉ có ích khi có thể khôi phục đúng dữ liệu, đúng khóa, đúng cấu hình và đúng quyền trong thời gian cho phép. Tần suất tạo backup không tự chứng minh RPO; thời gian chép dữ liệu cũng không phải toàn bộ RTO.

Một yêu cầu phục hồi đầy đủ cần làm rõ:

1. **Điểm bắt đầu và kết thúc:** thời gian phát hiện, ra quyết định và khôi phục có được tính vào RTO hay không. Trong ví dụ trên, thời gian được tính từ lúc mất khả dụng nên có bao gồm độ trễ phát hiện.
2. **Dữ liệu và phụ thuộc cần phục hồi:** dữ liệu nghiệp vụ, cấu hình, khóa cần thiết, danh tính dịch vụ và các thành phần hạ tầng liên quan.
3. **Độ tin cậy của nguồn phục hồi:** cách phát hiện bản sao hỏng, nguồn bị sửa trái phép và quyền xóa hoặc thay thế bản sao.
4. **Trình tự khôi phục:** phụ thuộc nào phải có trước, giới hạn tài nguyên và đường truy cập quản trị khi hệ thống chính đã hỏng.
5. **Kiểm tra trước mở phục vụ:** đối soát dữ liệu, phân quyền tenant, khóa và bí mật, phiên hoặc quyền đã bị thu hồi, audit và các giao dịch đang ở trạng thái không rõ.
6. **Đối soát sau phục hồi:** tìm giao dịch bị mất, bị gửi lại hoặc bị lặp; quy định người chịu trách nhiệm giải quyết.
7. **Tần suất diễn tập:** lịch phù hợp với mức rủi ro, các thay đổi buộc diễn tập lại và bằng chứng phải lưu.

Khôi phục một bản dữ liệu cũ có thể làm sống lại quyền truy cập đã bị thu hồi. Vì vậy, tiêu chí “ứng dụng khởi động được” chưa đủ để kết thúc phục hồi an toàn. Cần kiểm tra nguồn trạng thái quyền hiện hành hoặc cơ chế tái áp dụng các thay đổi an ninh trước khi mở giao dịch nhạy cảm.

## 11. Liên kết yêu cầu với kiến trúc và phép thử

Bảng truy vết giúp phát hiện yêu cầu không có bằng chứng hoặc một lựa chọn kiến trúc không phục vụ mục tiêu đã xác định.

| Rủi ro | Yêu cầu | Quyết định kiến trúc cần xem xét | Bằng chứng chấp nhận |
|---|---|---|---|
| Người dùng hợp lệ không hoàn tất tạo đơn | SR-AVL-001 | Điểm đo đầu vào, kiểm soát thời gian xử lý, đối soát kết quả | Báo cáo SLI, truy vấn có phiên bản và mẫu giao dịch đối chứng. |
| Một tenant chiếm tài nguyên dùng chung | SR-AVL-002 | Hạn ngạch, hàng đợi hữu hạn, cô lập tài nguyên | Kết quả tải đồng thời với số liệu riêng cho tenant được bảo vệ. |
| Lỗi định danh làm treo hoặc mở quyền | SR-AVL-003 | Timeout, xử lý phiên và chính sách khi không thể xác minh | Kịch bản gián đoạn phụ thuộc; bằng chứng từ chối và kiểm tra quyền. |
| Mất vùng chính làm ngừng nghiệp vụ | SR-AVL-004 | Nguồn phục hồi, quyền quản trị, phụ thuộc tại vùng phục hồi | Biên bản diễn tập có mốc thời gian và đối soát dữ liệu. |

Các lỗi cần được chèn trong môi trường kiểm thử hoặc môi trường diễn tập được kiểm soát, với phạm vi và điều kiện dừng xác định. Không cần dùng lưu lượng ngoài phạm vi được phép để chứng minh một yêu cầu thiết kế.

Ví dụ kịch bản nghiệm thu cho SR-AVL-002:

~~~gherkin
Feature: Duy trì tạo đơn khi một nhóm tài khoản gây quá tải

  Scenario: Tenant trong hạn mức tiếp tục tạo đơn
    Given cấu hình, dữ liệu và hạn mức đã được cố định trong hồ sơ thử
    And luồng tạo đơn hợp lệ chạy ở mức 200 lần mỗi giây trong 60 phút
    When nhóm gây nhiễu gửi 1000 lần mỗi giây trong 15 phút giữa bài thử
    Then ít nhất 99,9% lần thử hợp lệ trong 15 phút đó thành công trong 2 giây
    And số lần phát tải thực tế khớp kế hoạch trong sai số đã công bố
    And không có đơn được ghi nhận sai tenant hoặc bị tạo trùng
    And các lần từ chối vượt hạn mức có thể được đối soát
    And các giới hạn tài nguyên và lỗi quan sát được có báo cáo
~~~

Điều kiện về sai số phát tải phải được ấn định trước khi chạy. Nếu phát tải thiếu đáng kể, bài thử không đủ bằng chứng để kết luận đạt ở mức đã cam kết.

Hồ sơ kiểm thử nên lưu phiên bản ứng dụng và cấu hình, bố trí phụ thuộc, dữ liệu thử, lịch chèn lỗi, số liệu thô cần thiết, cách tính chỉ số và kết luận. Khi dùng tài khoản thử để kiểm tra phân quyền hoặc chống tạo trùng, phải có kết quả đối chiếu bên ngoài mã phản hồi HTTP.

## 12. Bằng chứng trong vòng đời phát triển

Yêu cầu cần được duy trì cùng những thay đổi ảnh hưởng tới khả năng phục vụ:

- Khi phân tích nghiệp vụ, xác nhận thời gian gián đoạn và mất dữ liệu có thể chấp nhận; xác định ai chấp nhận rủi ro còn lại.
- Khi mô hình hóa đe dọa, bổ sung kịch bản cạn tài nguyên, phụ thuộc bảo mật bị lỗi và lạm dụng chức năng hợp lệ.
- Khi thiết kế, liên kết mỗi yêu cầu với các thành phần thực thi và điểm đo; nhận diện phụ thuộc dùng chung có thể làm nhiều lớp cùng hỏng.
- Khi phát triển, triển khai giới hạn tài nguyên và hợp đồng lỗi; bảo đảm client biết khi nào được retry và cách xử lý kết quả không rõ.
- Khi nghiệm thu, kiểm chứng tải, gián đoạn, phục hồi và ràng buộc bảo mật bằng các kịch bản tương ứng.
- Khi vận hành, đo SLI theo định nghĩa đã thống nhất, theo dõi ngân sách lỗi và cập nhật yêu cầu khi phạm vi phục vụ thay đổi.

Ví dụ, chuyển kiểm tra quyền từ xử lý cục bộ sang một dịch vụ gọi qua mạng làm xuất hiện phụ thuộc mới trên đường tạo đơn. Thay đổi đó cần được xem lại trong SR-AVL-001 và SR-AVL-003; kết quả thử cũ có thể không còn đủ để chứng minh hành vi mới.

Cảnh báo vận hành cũng phải gắn với năng lực được bảo vệ. CPU cao là dấu hiệu điều tra, trong khi tỷ lệ giao dịch hợp lệ thất bại hoặc ngân sách lỗi bị tiêu thụ nhanh phản ánh trực tiếp hơn tác động cần xử lý. Hai loại tín hiệu có thể bổ sung cho nhau.

## 13. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Hệ thống luôn sẵn sàng.” | Không có phạm vi, ngưỡng hoặc phương pháp đo. | Chỉ rõ hành trình, nhóm người dùng, SLI, SLO và cửa sổ. |
| “API trả HTTP 200 là khả dụng.” | Có thể trả sai dữ liệu, sai quyền hoặc chưa ghi nhận giao dịch. | Đưa tính đúng, độ bền theo cam kết và kiểm soát bảo mật vào sự kiện tốt. |
| “Có nhiều replica nên đạt 99,99%.” | Chưa xét phụ thuộc chung, lưu lượng và thao tác thực tế. | Đo tại ranh giới đã chọn và thử các lỗi thuộc phạm vi cam kết. |
| “Không tính downtime của nhà cung cấp.” | Có thể làm chỉ số không còn phản ánh trải nghiệm người dùng. | Ghi rõ giới hạn trách nhiệm và duy trì số đo đầu cuối cho hành trình. |
| “Khi xác thực lỗi thì cho truy cập tạm.” | Có thể cấp quyền cho chủ thể không được phép. | Đặc tả theo loại thao tác, trạng thái phiên và giới hạn của chính sách quyền. |
| “Backup mỗi năm phút nên RPO năm phút.” | Chưa chứng minh bản sao dùng được và điểm khôi phục thực tế. | Khôi phục và đối chiếu giao dịch để đo khoảng mất dữ liệu. |
| “Bài load test đạt nên SLO cả tháng đạt.” | Thời gian và điều kiện thử không đại diện toàn bộ vận hành. | Tách kết quả nghiệm thu với bằng chứng SLO sau triển khai. |
| “Đạt chỉ số tổng nên mọi tenant đều tốt.” | Nhóm nhỏ có thể chịu phần lớn lỗi. | Bổ sung phép đo theo nhóm chịu rủi ro và tiêu chí bảo vệ phù hợp. |

## 14. Bài tập áp dụng

Một nền tảng học trực tuyến yêu cầu: “Hệ thống thi phải sẵn sàng cao, có backup và chống được tấn công.”

Hãy viết lại thành các yêu cầu có thể nghiệm thu cho ba hành trình: bắt đầu bài thi, lưu câu trả lời và nộp bài. Với mỗi hành trình:

1. Xác định người dùng hợp lệ, ranh giới đo và một sự kiện tốt.
2. Nêu điều kiện tải, thời gian cao điểm và tình huống lỗi hoặc lạm dụng cần xét.
3. Chọn SLO và giải thích tác động khi dùng hết ngân sách lỗi.
4. Quy định hành vi khi mất kết nối tới dịch vụ định danh hoặc hệ thống lưu trữ.
5. Xác định RTO, RPO và cách xử lý câu trả lời đã được báo lưu thành công.
6. Viết một ca kiểm thử cùng bằng chứng đủ để quyết định đạt hoặc không đạt.
7. Liên kết từng yêu cầu với một rủi ro và một quyết định kiến trúc cần đánh giá.

Một điểm cần phân tích là khác biệt giữa “nộp bài thất bại rõ ràng” và “hiển thị đã nộp nhưng làm mất bài”. Cả hai đều ảnh hưởng người học, nhưng tình huống thứ hai còn vi phạm tính toàn vẹn và độ tin cậy của xác nhận. Đặc tả tính sẵn sàng phải đi cùng tính đúng của kết quả và các kiểm soát bảo mật bắt buộc.