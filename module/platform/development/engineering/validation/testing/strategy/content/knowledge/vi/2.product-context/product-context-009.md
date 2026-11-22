# Xác định giả định, giới hạn và thông tin còn thiếu trước khi chọn phương án

Trong module `VALIDATION_TESTING_STRATEGY`, lựa chọn phương án kiểm thử cần dựa trên hiểu biết đủ tin cậy về sản phẩm, người dùng, quy trình và môi trường vận hành. Trên thực tế, nhóm thường phải ra quyết định khi tài liệu chưa đầy đủ, các bên hiểu khác nhau hoặc một số điều kiện chỉ được biết sau khi thử nghiệm. Nếu xem điều chưa được xác nhận như sự thật, nhóm có thể chọn sai phạm vi, kỹ thuật, dữ liệu hoặc tiêu chí chấp nhận.

Trước khi chọn phương án, hãy tách bạch ba loại thông tin:

- **Giả định (assumption):** điều đang tạm coi là đúng dù chưa có đủ bằng chứng xác nhận.
- **Giới hạn hoặc ràng buộc (constraint):** điều kiện thu hẹp những phương án có thể thực hiện, chẳng hạn quy định, thời gian, ngân sách, quyền truy cập hoặc đặc tính của hệ thống.
- **Thông tin còn thiếu (missing information):** dữ kiện cần cho quyết định nhưng chưa được thu thập, chưa rõ hoặc chưa được người có thẩm quyền xác nhận.

Ba loại này có quan hệ với nhau nhưng không thể thay thế cho nhau. Một giả định có thể che lấp thông tin còn thiếu; một ràng buộc có thể khiến một phương án không khả thi dù phương án đó đáp ứng yêu cầu kỹ thuật. Nhận diện chúng sớm giúp nhóm biết điều gì có thể quyết định ngay, điều gì cần kiểm chứng và điều gì phải được giải quyết trước khi tiếp tục.

## 1. Vì sao cần làm rõ trước khi chọn phương án?

Một chiến lược kiểm thử là tập hợp quyết định về mục tiêu, phạm vi, mức kiểm thử, cách tiếp cận, dữ liệu, môi trường, công cụ, bằng chứng và tiêu chí hoàn thành. Mỗi quyết định đều phụ thuộc vào một số thông tin đầu vào.

Ví dụ, nhóm có thể dự định kiểm thử tích hợp thanh toán bằng cách gửi yêu cầu vào môi trường thử nghiệm. Nhưng nếu chưa biết môi trường đó có mô phỏng được timeout hay thông báo thanh toán lặp hay không, nhóm chưa thể kết luận rằng cách tiếp cận đã bao phủ rủi ro chính. Nếu môi trường không hỗ trợ các tình huống này, cần bổ sung mô phỏng, kiểm thử hợp đồng hoặc một cách xác nhận khác.

Làm rõ giả định, ràng buộc và thông tin còn thiếu giúp:

- Tránh chọn giải pháp dựa trên hiểu nhầm về yêu cầu hoặc hành vi của hệ thống.
- Nhận ra những quyết định đang phụ thuộc vào dữ kiện chưa được xác minh.
- Ưu tiên việc tìm hiểu theo mức độ ảnh hưởng đến chất lượng và tiến độ.
- Xác định phương án nào khả thi trong giới hạn thực tế.
- Thống nhất ai có quyền xác nhận quy tắc, rủi ro và mức chấp nhận.
- Ghi lại lý do chọn phương án để có thể xem xét lại khi thông tin thay đổi.

Mục tiêu không phải thu thập mọi thông tin có thể có. Mục tiêu là tìm đủ bằng chứng cho những quyết định quan trọng, đồng thời công khai phần chưa chắc chắn có thể ảnh hưởng đến kết quả.

## 2. Phân biệt giả định, ràng buộc và thông tin còn thiếu

### 2.1. Giả định

Giả định là một nhận định đang được dùng làm cơ sở lập kế hoạch hoặc ra quyết định nhưng chưa được xác minh đầy đủ. Giả định có thể xuất phát từ kinh nghiệm, tài liệu cũ, lời trao đổi, hành vi quan sát được hoặc suy luận của nhóm.

Ví dụ:

- Nhóm cho rằng mỗi yêu cầu tạo đơn chỉ được xử lý một lần.
- Nhóm cho rằng người dùng luôn có kết nối mạng khi xác nhận giao dịch.
- Nhóm cho rằng dữ liệu kiểm thử có cấu trúc tương tự dữ liệu thật.
- Nhóm cho rằng một dịch vụ bên ngoài phản hồi trong một khoảng thời gian nhất định.
- Nhóm cho rằng nhân viên vận hành có thể xử lý thủ công khi tích hợp thất bại.

Một giả định cần được viết thành câu rõ ràng, có thể kiểm chứng. “Thanh toán ổn định” quá mơ hồ. “Khi cùng một mã yêu cầu được gửi lại, hệ thống thanh toán không tạo thêm giao dịch thu tiền” là một nhận định có thể thiết kế cách xác minh.

Không phải giả định nào cũng nguy hiểm. Một giả định có tác động thấp, dễ đảo ngược và có cách phát hiện nhanh có thể được chấp nhận tạm thời. Giả định liên quan đến tiền, quyền truy cập, dữ liệu nhạy cảm, an toàn hoặc kết quả cốt lõi cần được xác minh kỹ hơn.

### 2.2. Ràng buộc

Ràng buộc là điều kiện giới hạn phạm vi hoặc cách thực hiện. Ràng buộc có thể đến từ bên ngoài hoặc nội bộ; có thể bắt buộc tuyệt đối hoặc có khả năng thương lượng.

| Loại ràng buộc | Ví dụ | Ảnh hưởng đến phương án |
|---|---|---|
| Pháp lý, chính sách và hợp đồng | Quy định về dữ liệu, lưu trữ, thời hạn hoặc nghĩa vụ kiểm toán | Giới hạn dữ liệu được dùng, nơi xử lý và bằng chứng phải lưu |
| Kỹ thuật | Hệ thống cũ, giao diện tích hợp cố định, giới hạn tải hoặc phiên bản nền tảng | Giới hạn công cụ, môi trường và cách kiểm thử |
| Vận hành | Khung giờ triển khai, thời gian bảo trì, quy trình phê duyệt | Ảnh hưởng lịch chạy và khả năng tiếp cận hệ thống |
| Nguồn lực | Nhân sự, ngân sách, thiết bị hoặc thời gian có hạn | Buộc nhóm ưu tiên rủi ro và chọn phạm vi phù hợp |
| Dữ liệu | Không có dữ liệu đại diện hoặc không được sao chép dữ liệu thật | Ảnh hưởng độ chân thực và cách tạo dữ liệu kiểm thử |
| Quyền truy cập | Không có quyền vào hệ thống, log hoặc dịch vụ của đối tác | Giới hạn khả năng quan sát và xác minh |
| Chất lượng dịch vụ | Mức độ sẵn sàng, thời gian phản hồi hoặc năng lực tải được cam kết | Định hình tiêu chí và điều kiện kiểm thử phi chức năng |

Cần xác định nguồn và tính chất của từng ràng buộc. Một yêu cầu bắt buộc theo hợp đồng khác với một ưu tiên nội bộ có thể điều chỉnh. Nếu chưa rõ một điều kiện có bắt buộc hay không, hãy ghi nhận đó là thông tin cần xác minh thay vì tự phân loại.

Có thể chia ràng buộc thành:

- **Ràng buộc cứng:** không thể thay đổi trong phạm vi quyết định hiện tại. Phương án vi phạm ràng buộc này không khả thi.
- **Ràng buộc mềm:** mục tiêu hoặc giới hạn có thể thương lượng nếu có lý do, người phê duyệt và đánh đổi được chấp nhận.
- **Ràng buộc tạm thời:** chỉ áp dụng trong một giai đoạn, môi trường hoặc thời điểm nhất định; cần ghi ngày xem xét lại.

Không nên mặc định rằng một giới hạn là vĩnh viễn. Hãy hỏi ai đặt ra, áp dụng ở đâu, có ngoại lệ không và điều kiện nào cho phép thay đổi.

### 2.3. Thông tin còn thiếu

Thông tin còn thiếu là dữ kiện cần để ra quyết định nhưng hiện chưa có hoặc chưa đủ tin cậy. Khác với giả định, nó có thể được ghi nhận trực tiếp dưới dạng câu hỏi chưa có lời giải.

Ví dụ:

- Chưa biết ai là nguồn dữ liệu chuẩn khi hai dịch vụ trả về trạng thái khác nhau.
- Chưa rõ một thao tác có cần hoàn tất trong một thời hạn cụ thể hay không.
- Chưa có số liệu về số lượng giao dịch đồng thời vào giờ cao điểm.
- Chưa biết dữ liệu kiểm thử có thể được tạo tự động hay phải xin cấp thủ công.
- Chưa rõ tiêu chí nào xác định một giao dịch được xem là hoàn tất.

Thông tin còn thiếu chỉ đáng ưu tiên nếu nó có thể làm thay đổi quyết định, tiêu chí thành công, mức rủi ro hoặc khả năng thực hiện. Không cần trì hoãn mọi công việc chỉ vì một chi tiết chưa biết. Hãy phân biệt thông tin cần có ngay với thông tin có thể bổ sung sau.

### 2.4. Mối quan hệ giữa ba loại

Một tình huống có thể chứa cả ba loại:

- **Thông tin còn thiếu:** chưa biết dịch vụ thanh toán xử lý yêu cầu gửi lại như thế nào.
- **Giả định:** nhóm tạm cho rằng dịch vụ sẽ trả lại kết quả của giao dịch ban đầu.
- **Ràng buộc:** chỉ được kiểm thử với tài khoản và dữ liệu trong môi trường thử nghiệm do đối tác cấp.

Nếu không phân biệt, nhóm có thể ghi “dịch vụ hỗ trợ gửi lại an toàn” như một sự thật dù đó mới chỉ là giả định. Việc ghi đúng loại giúp xác định hành động tiếp theo: tìm bằng chứng, thử nghiệm, xin xác nhận hoặc điều chỉnh phương án.

## 3. Tìm các điểm chưa chắc chắn trước khi lập phương án

Hãy bắt đầu từ quyết định mà nhóm sắp đưa ra. Sau đó lần ngược các điều kiện và thông tin có thể làm thay đổi quyết định đó.

### 3.1. Xác định quyết định cần đưa ra

Viết rõ quyết định dưới dạng câu hỏi cụ thể, chẳng hạn:

- Có cần kiểm thử đầu cuối toàn bộ quy trình hay có thể tập trung vào các điểm tích hợp rủi ro cao?
- Có thể dùng dữ liệu tổng hợp để xác nhận quy tắc hay cần dữ liệu gần với thực tế?
- Cần kiểm thử hiệu năng ở tải nào và trong thời gian bao lâu?
- Có thể dựa vào môi trường thử nghiệm của đối tác hay cần mô phỏng riêng?
- Điều kiện nào phải đạt trước khi phát hành?

Một quyết định rõ ràng giúp loại bỏ các câu hỏi không liên quan. Nếu nhóm chưa thống nhất mục tiêu cần đạt, hãy làm rõ mục tiêu trước khi tranh luận về công cụ.

### 3.2. Kiểm tra các nhóm thông tin

| Nhóm | Câu hỏi gợi ý | Ví dụ thông tin cần có |
|---|---|---|
| Người dùng và mục tiêu | Ai sử dụng? Công việc nào cần hoàn tất? Điều gì được xem là thành công? | Vai trò, hành trình, tiêu chí chấp nhận |
| Quy tắc nghiệp vụ | Điều kiện nào cho phép hoặc từ chối một hành động? | Quy tắc tính tiền, chuyển trạng thái, quyền hạn |
| Dữ liệu | Dữ liệu đến từ đâu, ai sở hữu, có đại diện không? | Nguồn chuẩn, chất lượng, kích thước và độ nhạy |
| Kiến trúc và tích hợp | Các thành phần trao đổi dữ liệu thế nào? | Giao diện, thứ tự sự kiện, timeout, cơ chế thử lại |
| Chất lượng | Mức độ nhanh, ổn định, an toàn hoặc sẵn sàng cần đạt là gì? | Ngưỡng hiệu năng, tải, khả năng phục hồi |
| Môi trường | Có môi trường nào, khác biệt với môi trường thật ra sao? | Cấu hình, phiên bản, dịch vụ phụ thuộc |
| Vận hành | Ai theo dõi, xử lý lỗi và khôi phục? | Quy trình trực, cảnh báo, đối soát |
| Tuân thủ và bảo mật | Có dữ liệu hoặc hành động nào bị giới hạn? | Quyền truy cập, lưu vết, thời hạn lưu trữ |
| Nguồn lực và lịch | Ai có thể tham gia và khi nào? | Nhân sự, thiết bị, cửa sổ kiểm thử |
| Bằng chứng | Dựa vào đâu để kết luận đạt hoặc không đạt? | Log, báo cáo, bản ghi, xác nhận nghiệp vụ |

Không cần trả lời mọi câu hỏi bằng một tài liệu dài. Hãy tập trung vào những câu hỏi liên quan trực tiếp đến quyết định và rủi ro của sản phẩm.

### 3.3. Tìm cả thông tin không được viết thành tài liệu

Tài liệu chính thức là một nguồn quan trọng, nhưng không phải lúc nào cũng phản ánh đầy đủ cách hệ thống vận hành. Hãy kết hợp:

- Trao đổi với Product Owner, chuyên gia nghiệp vụ và người chịu trách nhiệm quy trình.
- Phỏng vấn người dùng hoặc nhân viên vận hành về tình huống thực tế.
- Xem tiêu chí chấp nhận, chính sách, hợp đồng và quyết định đã được phê duyệt.
- Kiểm tra log, báo cáo, dữ liệu lỗi và lịch sử sự cố nếu được cấp quyền.
- Trao đổi với nhóm phát triển, vận hành, bảo mật và quản trị dữ liệu.
- Thử nghiệm có kiểm soát hoặc tạo nguyên mẫu để xác nhận hành vi chưa rõ.

Khi các nguồn khác nhau mâu thuẫn, hãy ghi rõ từng nguồn, thời điểm và người có thẩm quyền quyết định. Một trao đổi miệng có thể giúp phát hiện vấn đề, nhưng với quy tắc quan trọng cần lưu lại xác nhận có thể truy vết.

### 3.4. Đặt câu hỏi theo tình huống

Câu hỏi chung chung thường tạo ra câu trả lời chung chung. Hãy đưa ra tình huống cụ thể:

- Nếu người dùng gửi cùng yêu cầu hai lần do không nhận được phản hồi, hệ thống cần làm gì?
- Nếu dịch vụ ngoài đã xử lý giao dịch nhưng ứng dụng bị timeout, trạng thái nào là đúng?
- Nếu dữ liệu giữa hai hệ thống khác nhau, hệ thống nào có thẩm quyền quyết định?
- Nếu không thể dùng dữ liệu thật, dữ liệu tổng hợp cần giữ những đặc tính nào?
- Nếu không thể kiểm thử vào giờ cao điểm, bằng chứng nào có thể hỗ trợ đánh giá năng lực tải?
- Nếu một tiêu chí chất lượng không đạt, ai quyết định có thể chấp nhận rủi ro hay phải dừng phát hành?

Câu hỏi nên hướng tới quy tắc, kết quả mong đợi và người chịu trách nhiệm. Ghi cả câu trả lời lẫn điều kiện hoặc ngoại lệ đi kèm.

## 4. Đánh giá mức độ quan trọng của điều chưa chắc chắn

Không phải mọi giả định hoặc câu hỏi chưa giải đáp đều có cùng mức độ khẩn cấp. Hãy xem xét khả năng điều đó sai, hậu quả nếu sai và mức độ nó làm thay đổi quyết định.

### 4.1. Đánh giá giả định

Với mỗi giả định, ghi nhận:

1. **Độ tin cậy hiện tại:** có bằng chứng trực tiếp, bằng chứng gián tiếp hay chỉ là suy đoán?
2. **Khả năng sai:** điều gì khiến giả định có thể không đúng?
3. **Hậu quả nếu sai:** có ảnh hưởng đến tiền, dữ liệu, người dùng, tuân thủ hoặc quy trình cốt lõi không?
4. **Khả năng phát hiện:** nhóm có nhận ra sớm nếu giả định sai không?
5. **Khả năng đảo ngược:** có thể thay đổi phương án sau khi phát hiện mà không gây thiệt hại lớn không?
6. **Ảnh hưởng đến quyết định:** nếu giả định sai, phương án có phải thay đổi không?

Có thể dùng thang định tính thấp, trung bình, cao cho độ tin cậy và tác động. Nếu cần xếp hạng, nhóm có thể kết hợp khả năng sai với mức độ hậu quả. Đây là công cụ sàng lọc, không phải phép đo chính xác về xác suất.

| Độ tin cậy | Hậu quả nếu sai | Cách xử lý gợi ý |
|---|---|---|
| Cao | Thấp | Ghi nguồn bằng chứng và theo dõi khi có thay đổi |
| Cao | Cao | Xác nhận nguồn có thẩm quyền; duy trì kiểm soát và bằng chứng |
| Thấp | Thấp | Có thể tạm chấp nhận nếu dễ phát hiện và đảo ngược |
| Thấp | Cao | Ưu tiên xác minh trước khi chọn hoặc cam kết phương án |

Giả định có độ tin cậy cao vẫn có thể cần kiểm tra nếu hậu quả rất nghiêm trọng. Ngược lại, một giả định chưa chắc chắn nhưng ít ảnh hưởng có thể được ghi nhận và xử lý ở giai đoạn sau.

### 4.2. Đánh giá thông tin còn thiếu

Một câu hỏi chưa có lời giải cần được ưu tiên khi câu trả lời có thể:

- Làm thay đổi phạm vi hoặc cấp độ kiểm thử.
- Làm một phương án trở nên không khả thi.
- Thay đổi kết quả mong đợi hoặc tiêu chí chấp nhận.
- Làm tăng đáng kể rủi ro cho người dùng hoặc tổ chức.
- Ảnh hưởng đến khả năng thu thập bằng chứng.
- Gây trễ cho công việc phụ thuộc hoặc quyết định phát hành.

Có thể phân loại thông tin thành ba nhóm:

- **Cần có trước quyết định:** thiếu dữ kiện có thể khiến quyết định sai hoặc không thể thực hiện.
- **Cần có trước khi thực thi:** có thể chọn hướng đi nhưng chưa thể chạy kiểm thử an toàn hoặc có ý nghĩa.
- **Có thể bổ sung trong quá trình:** không làm thay đổi quyết định hiện tại và có thể xác minh ở mốc sau.

Ghi rõ thời điểm cần có thông tin. Cụm từ “sẽ tìm hiểu sau” không đủ nếu không có người phụ trách và mốc hoàn thành.

### 4.3. Xem xét sự phụ thuộc giữa các điểm chưa chắc chắn

Một giả định có thể phụ thuộc vào giả định khác. Ví dụ, kế hoạch dùng dữ liệu tổng hợp phụ thuộc vào việc nhóm hiểu các quy tắc tạo dữ liệu và có thể quan sát kết quả ở hệ thống đích. Nếu một điều kiện không đúng, toàn bộ phương án có thể mất giá trị.

Hãy vẽ hoặc ghi lại các phụ thuộc quan trọng:

```
Nguồn dữ liệu được phép sử dụng?
          |
          v
Có thể tạo dữ liệu đại diện?
          |
          v
Có thể quan sát kết quả ở hệ thống đích?
          |
          v
Có đủ bằng chứng để kết luận?
```

Giải quyết điểm phụ thuộc ở đầu chuỗi trước khi đầu tư nhiều công sức vào các bước sau.

## 5. Xác minh giả định và thu thập thông tin còn thiếu

Sau khi xếp hạng, chọn cách xác minh phù hợp với mức rủi ro, chi phí và thời gian. Không phải câu hỏi nào cũng cần một thử nghiệm lớn.

### 5.1. Các cách xác minh thường dùng

| Cách xác minh | Phù hợp khi | Bằng chứng có thể thu được |
|---|---|---|
| Xác nhận với chủ sở hữu nghiệp vụ | Cần làm rõ quy tắc, mục tiêu hoặc ngoại lệ | Quyết định, tiêu chí chấp nhận được xác nhận |
| Rà soát tài liệu và hợp đồng | Có chính sách hoặc cam kết chính thức | Điều khoản, giới hạn, phiên bản và nguồn tham chiếu |
| Phân tích dữ liệu vận hành | Cần hiểu tần suất, khối lượng hoặc mẫu lỗi | Số liệu, phân bố, xu hướng và ngoại lệ |
| Kiểm tra log và lịch sử sự kiện | Cần hiểu trình tự xử lý hoặc hành vi thực tế | Dấu thời gian, trạng thái, mã tương quan và dấu vết lỗi |
| Walkthrough quy trình | Cần xác nhận các bước và trách nhiệm | Luồng được các bên liên quan thống nhất |
| Thử nghiệm kỹ thuật nhỏ (spike) | Cần kiểm tra khả năng hoặc giới hạn kỹ thuật | Kết quả thử nghiệm, cấu hình và giới hạn đã quan sát |
| Prototype hoặc mô phỏng | Cần khám phá hành vi hoặc tương tác chưa rõ | Phản hồi người dùng, kết quả mô phỏng |
| Kiểm thử thăm dò có mục tiêu | Hành vi thực tế chưa được mô tả đầy đủ | Tình huống tái hiện, bằng chứng và câu hỏi mới |
| Thử nghiệm có kiểm soát | Cần so sánh hai cách xử lý hoặc kiểm chứng giả thuyết | Kết quả đo được trong điều kiện xác định |

Một thử nghiệm kỹ thuật nhỏ cần có câu hỏi cụ thể, điều kiện chạy, tiêu chí kết luận và giới hạn áp dụng. Kết quả từ một môi trường hoặc một lần chạy không tự động chứng minh hành vi ở mọi môi trường và mọi tải.

### 5.2. Viết giả định thành giả thuyết có thể kiểm chứng

Dùng cấu trúc:

- **Nhận định:** điều đang được cho là đúng.
- **Căn cứ hiện tại:** vì sao nhóm tin điều đó.
- **Cách kiểm chứng:** thao tác, dữ liệu hoặc nguồn xác nhận.
- **Kết quả chấp nhận:** quan sát nào xác nhận hoặc bác bỏ nhận định.
- **Phạm vi kết luận:** môi trường, phiên bản và điều kiện áp dụng.
- **Người xác nhận:** ai có thẩm quyền chấp nhận kết quả.

Ví dụ:

| Thành phần | Nội dung minh họa |
|---|---|
| Nhận định | Gửi lại cùng mã yêu cầu thanh toán không tạo thêm lần thu tiền |
| Căn cứ hiện tại | Tài liệu tích hợp đề cập cơ chế chống xử lý trùng nhưng chưa mô tả trường hợp timeout |
| Cách kiểm chứng | Gửi yêu cầu, mô phỏng mất phản hồi rồi gửi lại cùng mã trong môi trường thử nghiệm |
| Kết quả chấp nhận | Có thể truy vết một giao dịch thu tiền duy nhất và kết quả trả về nhất quán |
| Phạm vi kết luận | Phiên bản dịch vụ và cấu hình môi trường đã thử |
| Người xác nhận | Chủ sở hữu tích hợp và đại diện nghiệp vụ thanh toán |

Nếu kết quả không như dự kiến, cập nhật giả định thành sai hoặc cần giới hạn phạm vi. Không điều chỉnh tiêu chí sau khi thử chỉ để làm cho giả định có vẻ đúng.

### 5.3. Chọn cách xử lý sau xác minh

Một điểm chưa chắc chắn có thể dẫn đến một trong các quyết định:

- **Xác nhận:** bằng chứng đủ tin cậy trong phạm vi đã nêu; ghi nguồn và điều kiện áp dụng.
- **Bác bỏ:** giả định sai; sửa phương án, phạm vi hoặc tiêu chí.
- **Giới hạn:** nhận định chỉ đúng trong một môi trường, phiên bản hoặc điều kiện cụ thể; ghi rõ ranh giới.
- **Chấp nhận tạm thời:** chưa thể xác minh ngay nhưng tác động thấp, có biện pháp phát hiện và người chịu trách nhiệm chấp nhận.
- **Hoãn quyết định:** cần thêm dữ kiện trước khi chọn phương án.
- **Dừng hoặc chuyển cấp:** rủi ro vượt thẩm quyền hoặc không có cách kiểm soát phù hợp; chuyển người có trách nhiệm quyết định.

Việc chấp nhận một giả định cần có người chịu trách nhiệm, thời hạn xem xét và điều kiện khiến giả định phải được kiểm tra lại.

## 6. Xử lý ràng buộc khi so sánh phương án

Khi đã hiểu giới hạn, hãy đánh giá từng phương án theo cùng một bộ tiêu chí. Một phương án có thể tốt về mặt kỹ thuật nhưng không thể triển khai do quyền truy cập, dữ liệu, lịch hoặc nghĩa vụ tuân thủ.

### 6.1. Xác nhận nguồn và phạm vi của ràng buộc

Với mỗi ràng buộc, ghi lại:

- Nguồn đưa ra ràng buộc và người có thẩm quyền xác nhận.
- Phạm vi áp dụng: toàn hệ thống, một môi trường, một nhóm hoặc một giai đoạn.
- Mức bắt buộc: cứng, mềm hay tạm thời.
- Thời điểm bắt đầu và thời điểm cần xem xét lại.
- Hậu quả nếu vi phạm.
- Cách chứng minh phương án tuân thủ.

Nếu ràng buộc liên quan đến bảo mật, quyền riêng tư, an toàn hoặc nghĩa vụ pháp lý, cần xác nhận với vai trò chuyên trách phù hợp. Người kiểm thử không nên tự diễn giải một quy định chưa rõ thành quyết định chính thức.

### 6.2. Phân biệt điều kiện bắt buộc và tiêu chí đánh đổi

Điều kiện bắt buộc là tiêu chí loại trừ: phương án không đáp ứng thì không được chọn nếu chưa có thay đổi hoặc phê duyệt hợp lệ. Tiêu chí đánh đổi cho phép so sánh các phương án còn lại, ví dụ thời gian thực hiện, độ bao phủ, chi phí và khả năng bảo trì.

| Tiêu chí | Câu hỏi khi đánh giá |
|---|---|
| Tuân thủ | Phương án có đáp ứng chính sách và nghĩa vụ áp dụng không? |
| Bao phủ rủi ro | Có kiểm tra được những tình huống có hậu quả lớn không? |
| Bằng chứng | Có thể quan sát và xác nhận kết quả đáng tin cậy không? |
| Khả thi | Có đủ quyền truy cập, dữ liệu, môi trường và nhân lực không? |
| Thời gian | Có đáp ứng mốc quyết định cần thiết không? |
| Khả năng lặp lại | Kết quả có thể tái tạo và so sánh giữa các lần chạy không? |
| Bảo trì | Khi sản phẩm thay đổi, chi phí cập nhật phương án là bao nhiêu? |
| Phục hồi | Khi kiểm thử gây ra tác dụng phụ hoặc phát hiện lỗi, có cách xử lý an toàn không? |

Đừng cộng điểm cho một phương án nếu nó vi phạm một điều kiện bắt buộc. Trước tiên hãy loại các phương án không khả thi; sau đó mới so sánh lợi ích và chi phí của các phương án còn lại.

### 6.3. Ghi lại đánh đổi và rủi ro còn lại

Nếu giới hạn nguồn lực khiến nhóm không thể bao phủ toàn bộ phạm vi, cần ghi rõ:

- Rủi ro nào được kiểm tra trước và vì sao.
- Rủi ro nào chưa được kiểm tra.
- Bằng chứng hiện có và mức tin cậy của bằng chứng.
- Biện pháp giảm thiểu hoặc theo dõi sau phát hành.
- Người có thẩm quyền chấp nhận rủi ro còn lại.
- Điều kiện khiến quyết định phải được xem xét lại.

Việc ghi lại rủi ro còn lại giúp các bên hiểu chính xác mức độ bảo đảm mà hoạt động kiểm thử cung cấp.

## 7. Ví dụ tổng hợp: chọn cách kiểm thử cho tích hợp thanh toán

Giả sử nhóm cần chọn phương án xác nhận quy trình thanh toán. Thông tin ban đầu chưa đủ để biết dịch vụ ngoài xử lý yêu cầu gửi lại ra sao, thông báo có thể đến sai thứ tự hay không và môi trường thử nghiệm có hỗ trợ mô phỏng timeout không.

### 7.1. Lập danh sách ban đầu

| Nội dung | Phân loại | Tác động nếu chưa làm rõ |
|---|---|---|
| Cùng mã yêu cầu được gửi lại chỉ tạo một giao dịch | Giả định | Có thể bỏ sót thu tiền trùng |
| Không biết thông báo có thể đến lặp hoặc sai thứ tự không | Thông tin còn thiếu | Không xác định đủ tình huống tích hợp |
| Chỉ được dùng tài khoản và dữ liệu trong môi trường thử nghiệm | Ràng buộc | Không thể thực hiện giao dịch kiểm thử tùy ý trên hệ thống thật |
| Chưa biết có thể truy cập log phía đối tác không | Thông tin còn thiếu | Khó xác định nguồn gây sai lệch khi đối soát |
| Dịch vụ có giới hạn số yêu cầu trong một khoảng thời gian | Ràng buộc cần xác nhận | Có thể làm sai kết quả kiểm thử tải hoặc gây khóa tài khoản |

### 7.2. Xác định việc cần làm trước

Nhóm có thể ưu tiên xác nhận cơ chế chống xử lý trùng và cách xử lý thông báo đến trễ vì hai điểm này liên quan trực tiếp đến nguy cơ thu tiền sai và trạng thái đơn không nhất quán. Tiếp theo, nhóm xác nhận môi trường thử nghiệm hỗ trợ những tình huống nào và có nguồn bằng chứng nào để đối soát.

Một kế hoạch xác minh ngắn có thể gồm:

1. Xin tài liệu tích hợp và xác nhận quy tắc với chủ sở hữu dịch vụ.
2. Kiểm tra khả năng tạo giao dịch thử, gửi lại yêu cầu và mô phỏng timeout.
3. Kiểm tra khả năng quan sát mã giao dịch, trạng thái đơn và thông báo nhận được.
4. Ghi lại các tình huống môi trường không mô phỏng được.
5. Chọn cách bổ sung như mô phỏng phản hồi, kiểm thử hợp đồng hoặc xác nhận bằng log được cấp quyền.

### 7.3. So sánh phương án sau khi có bằng chứng

| Phương án | Ưu điểm | Giới hạn cần xem xét |
|---|---|---|
| Chỉ kiểm thử API với phản hồi thành công | Nhanh, dễ lặp lại | Không đủ bằng chứng về thông báo lặp, timeout và kết quả đầu cuối |
| Kiểm thử tích hợp trên môi trường thử nghiệm | Xác nhận tương tác thực giữa các dịch vụ trong phạm vi môi trường | Có thể không mô phỏng đủ mọi lỗi hoặc tải thực tế |
| Kết hợp kiểm thử tích hợp, mô phỏng lỗi và đối soát | Bao phủ được nhiều nhánh rủi ro và có bằng chứng từ nhiều điểm | Cần chuẩn bị dữ liệu, mô phỏng và quyền quan sát phù hợp |

Nếu môi trường thử nghiệm không hỗ trợ một tình huống, nhóm phải ghi rõ khoảng trống và bổ sung cách xác minh có kiểm soát. Kết luận cuối cùng cần nêu rõ điều gì đã được kiểm tra trực tiếp, điều gì được mô phỏng và điều gì vẫn là rủi ro còn lại.

## 8. Ghi nhận quyết định và duy trì dấu vết

Thông tin sẽ thay đổi theo phiên bản, chính sách và điều kiện vận hành. Vì vậy, kết quả xác minh cần được ghi lại ở nơi nhóm có thể tìm thấy và cập nhật.

### 8.1. Mẫu sổ đăng ký giả định, ràng buộc và thông tin còn thiếu

| Trường | Nội dung |
|---|---|
| ID | Mã tham chiếu duy nhất |
| Nội dung | Câu nhận định hoặc câu hỏi cụ thể |
| Loại | Giả định, ràng buộc hoặc thông tin còn thiếu |
| Phạm vi | Quy trình, hệ thống, môi trường hoặc phiên bản liên quan |
| Nguồn | Tài liệu, người trao đổi, dữ liệu hoặc quan sát |
| Độ tin cậy | Cao, trung bình, thấp hoặc chưa có bằng chứng |
| Tác động nếu sai/chưa rõ | Hậu quả đối với người dùng, nghiệp vụ và kiểm thử |
| Mức ưu tiên | Cần xử lý trước quyết định, trước thực thi hoặc có thể bổ sung sau |
| Cách xác minh | Câu hỏi, phân tích, thử nghiệm hoặc phê duyệt cần thực hiện |
| Người phụ trách | Người theo dõi và phối hợp giải quyết |
| Hạn xử lý | Mốc cần có kết quả |
| Trạng thái | Mới, đang xác minh, đã xác nhận, bị bác bỏ, chấp nhận tạm thời |
| Quyết định liên quan | Phương án hoặc tiêu chí bị ảnh hưởng |
| Ngày xem xét lại | Mốc kiểm tra khi bối cảnh thay đổi |

### 8.2. Mẫu ghi nhận quyết định

Một quyết định về phương án kiểm thử nên có:

- **Bối cảnh:** mục tiêu và vấn đề cần giải quyết.
- **Các phương án:** những lựa chọn đã cân nhắc.
- **Ràng buộc:** điều kiện bắt buộc và nguồn xác nhận.
- **Giả định:** những điều còn được chấp nhận tạm thời.
- **Bằng chứng:** tài liệu, dữ liệu và kết quả thử nghiệm.
- **Lý do chọn:** tiêu chí và đánh đổi chính.
- **Rủi ro còn lại:** điều chưa được kiểm tra hoặc chưa thể kết luận.
- **Người quyết định:** vai trò chịu trách nhiệm phê duyệt.
- **Điều kiện xem xét lại:** thay đổi nào sẽ làm quyết định mất hiệu lực.

Có thể liên kết sổ đăng ký với yêu cầu, rủi ro và kịch bản kiểm thử bằng ID. Nhờ đó, khi một giả định bị bác bỏ, nhóm xác định được những quyết định và kiểm thử nào cần xem xét lại.

### 8.3. Cập nhật khi bối cảnh thay đổi

Cần xem lại các mục đã ghi nhận khi:

- Yêu cầu hoặc chính sách nghiệp vụ thay đổi.
- Phiên bản dịch vụ tích hợp hoặc cấu hình môi trường thay đổi.
- Xuất hiện dữ liệu, sự cố hoặc hành vi mới trái với giả định.
- Quyền truy cập, nguồn lực hoặc lịch kiểm thử thay đổi.
- Một ràng buộc tạm thời hết hiệu lực.
- Có quyết định mới từ người chịu trách nhiệm.

Một mục đã xác nhận không nhất thiết đúng mãi mãi. Hãy lưu phạm vi, thời điểm và phiên bản để tránh áp dụng kết luận cũ cho bối cảnh mới.

## 9. Những sai lầm thường gặp

1. **Biến giả định thành sự thật:** dùng câu “hệ thống luôn…” mà không có bằng chứng hoặc phạm vi áp dụng.
2. **Ghi ràng buộc không rõ nguồn:** không biết ai đặt ra, có bắt buộc không hoặc có thể xin ngoại lệ không.
3. **Thu thập quá nhiều thông tin không liên quan:** làm chậm quyết định mà không giảm rủi ro đáng kể.
4. **Bỏ qua câu hỏi có hậu quả lớn:** ưu tiên chi tiết dễ trả lời trong khi quy tắc cốt lõi vẫn chưa rõ.
5. **Dùng một lần thử làm bằng chứng phổ quát:** kết luận cho mọi phiên bản và môi trường từ một lần chạy giới hạn.
6. **Không ghi người chịu trách nhiệm:** câu hỏi tồn tại lâu vì không có người theo dõi hoặc người có quyền quyết định.
7. **Chấp nhận rủi ro không có thời hạn:** giả định tạm thời trở thành mặc định và không được xem xét lại.
8. **So sánh phương án trước khi loại ràng buộc bắt buộc:** chọn phương án hấp dẫn nhưng không thể thực hiện hoặc không được phép.
9. **Không cập nhật quyết định khi bằng chứng thay đổi:** tiếp tục dùng phạm vi và tiêu chí dựa trên thông tin đã lỗi thời.
10. **Không công khai rủi ro còn lại:** khiến người phê duyệt hiểu nhầm rằng mọi tình huống quan trọng đã được xác nhận.

## 10. Checklist trước khi chọn phương án

- [ ] Đã viết rõ quyết định cần đưa ra và mục tiêu cần đạt.
- [ ] Đã phân loại điều chưa chắc chắn thành giả định, ràng buộc hoặc thông tin còn thiếu.
- [ ] Mỗi giả định quan trọng đều có căn cứ, mức tin cậy và cách kiểm chứng.
- [ ] Mỗi ràng buộc đều có nguồn, phạm vi, mức bắt buộc và người xác nhận.
- [ ] Các câu hỏi còn thiếu đã được ưu tiên theo ảnh hưởng đến quyết định và rủi ro.
- [ ] Đã kiểm tra các phụ thuộc giữa những thông tin chưa chắc chắn.
- [ ] Đã chọn cách xác minh phù hợp và xác định bằng chứng cần thu được.
- [ ] Đã loại các phương án vi phạm điều kiện bắt buộc.
- [ ] Đã so sánh các phương án còn lại theo cùng tiêu chí và ghi lại đánh đổi.
- [ ] Đã nêu rõ giả định được chấp nhận tạm thời và người chịu trách nhiệm.
- [ ] Đã ghi nhận rủi ro còn lại, mốc xử lý và điều kiện xem xét lại.
- [ ] Đã liên kết quyết định với phạm vi, mục tiêu và bằng chứng kiểm thử.

Chỉ nên chốt phương án khi nhóm hiểu những điều kiện có thể làm thay đổi quyết định, biết bằng chứng nào đang hỗ trợ lựa chọn và công khai phần rủi ro còn lại. Nếu một thông tin có thể làm phương án trở nên không an toàn, không hợp lệ hoặc không khả thi, hãy giải quyết thông tin đó trước khi cam kết thực hiện.
