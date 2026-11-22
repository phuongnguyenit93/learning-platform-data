# Phân biệt cấp độ kiểm thử, loại kiểm thử và kỹ thuật thiết kế

Khi xây dựng chiến lược kiểm thử, nhóm cần trả lời ba câu hỏi khác nhau: kiểm tra ở phạm vi nào, kiểm tra thuộc tính hoặc mục tiêu chất lượng nào, và dùng cách nào để thiết kế trường hợp kiểm thử. Ba câu hỏi này tương ứng với **cấp độ kiểm thử (test level)**, **loại kiểm thử (test type)** và **kỹ thuật thiết kế kiểm thử (test technique)**.

Ba khái niệm thường bị trộn lẫn vì một trường hợp kiểm thử có thể đồng thời thuộc một cấp độ, phục vụ một hoặc nhiều loại kiểm thử và được thiết kế bằng một kỹ thuật cụ thể. Phân biệt đúng giúp nhóm phân bổ trách nhiệm, chọn môi trường, tránh lặp lại không cần thiết và bảo đảm rủi ro quan trọng có bằng chứng ở vị trí phù hợp.

Ví dụ, kiểm tra quy tắc áp dụng mã giảm giá có thể được thực hiện ở cấp độ thành phần, thuộc loại kiểm thử chức năng và được thiết kế bằng bảng quyết định. Kiểm tra toàn bộ hành trình thanh toán trên môi trường gần production có thể thuộc cấp độ hệ thống, đồng thời bao gồm kiểm thử chức năng và hiệu năng; các trường hợp có thể được thiết kế từ luồng sử dụng và phân tích giá trị biên.

## 1. Ba câu hỏi cần tách biệt

| Khái niệm | Câu hỏi chính | Điều nó xác định | Ví dụ |
| --- | --- | --- | --- |
| Cấp độ kiểm thử | Kiểm tra ở đâu và phạm vi nào? | Phạm vi đối tượng, mức tích hợp và mục tiêu của giai đoạn kiểm thử | Kiểm thử thành phần tính giá; kiểm thử tích hợp giữa đặt hàng và thanh toán; kiểm thử toàn hệ thống |
| Loại kiểm thử | Đang đánh giá thuộc tính hoặc mục tiêu nào? | Khía cạnh chất lượng hoặc mục đích thay đổi cần xác minh | Kiểm thử chức năng, hiệu năng, bảo mật, khả năng sử dụng, hồi quy |
| Kỹ thuật thiết kế kiểm thử | Chọn dữ liệu và trường hợp nào để kiểm tra? | Cách phân tích cơ sở kiểm thử nhằm tạo điều kiện, dữ liệu và trường hợp kiểm thử | Phân vùng tương đương, giá trị biên, bảng quyết định, chuyển trạng thái, bao phủ nhánh |

Không có quan hệ một-một giữa ba khái niệm. Một cấp độ có thể chứa nhiều loại kiểm thử; một loại kiểm thử có thể được thực hiện ở nhiều cấp độ; một kỹ thuật có thể được dùng để thiết kế trường hợp cho nhiều loại kiểm thử khác nhau.

Ví dụ, kiểm thử bảo mật có thể được thực hiện ở cấp độ thành phần để kiểm tra hàm phân quyền, ở cấp độ tích hợp để xác minh token và quyền giữa các dịch vụ, hoặc ở cấp độ hệ thống để kiểm tra luồng truy cập từ giao diện. Bảng quyết định có thể dùng để thiết kế kiểm thử chức năng cho quy tắc giảm giá hoặc kiểm thử quyền truy cập theo vai trò.

## 2. Cấp độ kiểm thử: xác định phạm vi và ranh giới

Cấp độ kiểm thử mô tả phạm vi đối tượng được kiểm tra và mức độ kết hợp giữa các thành phần. Mỗi cấp độ trả lời một nhóm câu hỏi khác nhau, thường có cơ sở kiểm thử, môi trường, người tham gia và loại lỗi quan tâm riêng.

### Kiểm thử thành phần (component testing)

Kiểm thử thành phần tập trung vào một đơn vị hoặc thành phần riêng lẻ, chẳng hạn hàm, lớp, mô-đun hoặc dịch vụ nhỏ. Thành phần được kiểm tra trong điều kiện có thể kiểm soát, các cộng tác viên có thể được thay thế bằng mock, stub hoặc fake nếu mục tiêu là cô lập hành vi.

Mục tiêu thường gồm:

- Xác minh logic và quy tắc nghiệp vụ bên trong thành phần.
- Kiểm tra đầu vào hợp lệ, không hợp lệ, biên và trạng thái lỗi.
- Xác minh bất biến, kết quả trả về và các tác dụng phụ được mong đợi.
- Phát hiện lỗi sớm với phản hồi nhanh, dễ xác định vị trí.

Ví dụ: kiểm tra hàm tính tổng đơn hàng có xử lý đúng giá sản phẩm, phí vận chuyển, mã giảm giá và quy tắc làm tròn hay không. Các trường hợp kiểm thử có thể chạy nhanh mà không cần gọi cổng thanh toán thật.

Kiểm thử đơn vị (unit testing) thường được xem là phần nhỏ nhất của kiểm thử thành phần. Trong thực tế, ranh giới của “đơn vị” có thể khác nhau theo ngôn ngữ và kiến trúc; điều quan trọng là mô tả rõ đối tượng và cộng tác viên nằm trong phạm vi.

### Kiểm thử tích hợp thành phần (component integration testing)

Kiểm thử tích hợp thành phần tập trung vào tương tác giữa các thành phần hoặc mô-đun. Mục tiêu là phát hiện lỗi ở giao diện và cách cộng tác: truyền dữ liệu, thứ tự gọi, xử lý lỗi, giao dịch, sự kiện và các giả định giữa hai bên.

Ví dụ: kiểm tra `CheckoutService` làm việc với `OrderRepository` và `PaymentAdapter` như thế nào; xác minh dữ liệu đơn hàng được lưu đúng và trạng thái thanh toán được cập nhật theo phản hồi.

Có thể tích hợp từng phần hoặc theo nhóm thành phần. Nếu dùng mock cho một số phụ thuộc, cần ghi rõ tương tác nào đã được kiểm tra bằng thành phần thật và tương tác nào chỉ được mô phỏng.

### Kiểm thử hệ thống (system testing)

Kiểm thử hệ thống đánh giá hành vi của một hệ thống hoàn chỉnh trong phạm vi xác định. Các thành phần cần thiết thường được triển khai cùng nhau trên một môi trường tích hợp. Mục tiêu là xác minh hệ thống đáp ứng các yêu cầu chức năng và phi chức năng ở góc nhìn tổng thể.

Ví dụ: thực hiện hành trình người dùng chọn sản phẩm, áp dụng mã giảm giá, thanh toán, nhận xác nhận đơn hàng và xem trạng thái đơn. Ngoài luồng đúng, cần xem xét các tình huống như thanh toán bị từ chối, dịch vụ phụ thuộc chậm hoặc người dùng tải lại trang.

Kiểm thử hệ thống có thể bao gồm nhiều loại kiểm thử: chức năng, hiệu năng, bảo mật, khả năng sử dụng, khả năng tương thích và độ tin cậy. Không nên hiểu kiểm thử hệ thống chỉ là chạy một số kịch bản đầu cuối.

### Kiểm thử tích hợp hệ thống (system integration testing)

Kiểm thử tích hợp hệ thống tập trung vào giao tiếp giữa hệ thống đang kiểm thử với các hệ thống bên ngoài hoặc hệ thống khác trong môi trường vận hành. Mục tiêu là xác minh các ranh giới liên hệ thống như API, thông điệp, xác thực, định dạng dữ liệu, xử lý lỗi và các quy tắc tương tác.

Ví dụ: cửa hàng trực tuyến trao đổi với cổng thanh toán, dịch vụ vận chuyển, nhà cung cấp định danh và hệ thống gửi thông báo. Mỗi API có thể đúng riêng lẻ nhưng luồng kết hợp vẫn thất bại do sai cấu hình, khác phiên bản, timeout hoặc ngữ nghĩa dữ liệu không thống nhất.

Kiểm thử hợp đồng có thể cung cấp bằng chứng về sự tương thích của giao diện; kiểm thử tích hợp trên sandbox hoặc môi trường thử nghiệm giúp xác minh một phần hành vi thực tế. Phạm vi và giới hạn của từng cách cần được ghi rõ.

### Kiểm thử chấp nhận (acceptance testing)

Kiểm thử chấp nhận đánh giá hệ thống có đáp ứng nhu cầu, tiêu chí chấp nhận và điều kiện sử dụng mà bên liên quan đặt ra hay không. Trọng tâm là khả năng phù hợp với mục đích sử dụng và mức sẵn sàng để đưa vào sử dụng hoặc bàn giao.

Ví dụ: đại diện nghiệp vụ xác minh rằng đơn hàng có thể được tạo, thanh toán, hủy theo chính sách và đối soát đúng quy trình. Kiểm thử chấp nhận có thể bao gồm kiểm thử chấp nhận người dùng (UAT), kiểm thử chấp nhận vận hành hoặc kiểm thử chấp nhận theo hợp đồng, tùy bối cảnh.

Người dùng hoặc đại diện nghiệp vụ thường tham gia xác định tiêu chí và đánh giá kết quả. Nhóm kiểm thử có thể hỗ trợ thiết kế, dữ liệu và môi trường, nhưng tiêu chí chấp nhận phải phản ánh nhu cầu và thẩm quyền của bên chịu trách nhiệm.

### Bảng so sánh các cấp độ

| Cấp độ | Đối tượng chính | Câu hỏi thường gặp | Ví dụ lỗi dễ phát hiện |
| --- | --- | --- | --- |
| Thành phần | Một hàm, lớp, mô-đun hoặc dịch vụ nhỏ | Logic riêng lẻ có đúng không? | Tính sai mức giảm giá ở biên |
| Tích hợp thành phần | Tương tác giữa các mô-đun trong phạm vi ứng dụng | Các thành phần có phối hợp đúng không? | Ánh xạ sai trạng thái hoặc lưu dữ liệu không đúng |
| Hệ thống | Hệ thống hoàn chỉnh | Hệ thống có đáp ứng yêu cầu tổng thể không? | Luồng đặt hàng không hoàn thành do trạng thái giữa các phần không nhất quán |
| Tích hợp hệ thống | Giao tiếp với hệ thống khác | Các hệ thống có trao đổi đúng và xử lý tình huống lỗi phù hợp không? | API nhà cung cấp đổi schema hoặc timeout không được xử lý |
| Chấp nhận | Nhu cầu và tiêu chí của người dùng/nghiệp vụ | Sản phẩm có phù hợp để sử dụng hoặc bàn giao không? | Quy trình hoàn tiền không đáp ứng chính sách nghiệp vụ |

Không phải dự án nào cũng cần một giai đoạn riêng cho từng cấp độ hoặc dùng đúng tên gọi trên. Một nhóm nhỏ có thể gộp hoạt động, nhưng vẫn cần chỉ rõ phạm vi, mục tiêu và bằng chứng của từng hoạt động.

## 3. Loại kiểm thử: xác định thuộc tính hoặc mục tiêu cần đánh giá

Loại kiểm thử mô tả khía cạnh chất lượng hoặc mục đích mà nhóm muốn đánh giá. Cùng một cấp độ có thể thực hiện nhiều loại kiểm thử, tùy rủi ro và yêu cầu.

### Kiểm thử chức năng (functional testing)

Kiểm thử chức năng đánh giá hệ thống hoặc thành phần thực hiện những gì đã được quy định. Cơ sở kiểm thử có thể là yêu cầu, quy tắc nghiệp vụ, user story, tiêu chí chấp nhận, hợp đồng API hoặc mô hình hành vi.

Ví dụ:

- Giá đơn hàng được tính đúng khi có nhiều sản phẩm và ưu đãi.
- Người dùng không có quyền quản trị không thể truy cập chức năng quản trị.
- Đơn hàng chuyển từ `Pending` sang `Paid` khi nhận được xác nhận thanh toán hợp lệ.

Kiểm thử chức năng có thể xuất hiện ở mọi cấp độ: kiểm tra hàm tính giá ở cấp thành phần, trao đổi trạng thái ở cấp tích hợp, luồng mua hàng ở cấp hệ thống và quy trình nghiệp vụ ở cấp chấp nhận.

### Kiểm thử phi chức năng (non-functional testing)

Kiểm thử phi chức năng đánh giá cách hệ thống hoạt động và chất lượng của trải nghiệm hoặc vận hành. Các thuộc tính có thể gồm hiệu năng, bảo mật, khả năng sử dụng, khả năng tiếp cận, độ tin cậy, khả năng tương thích, khả năng cài đặt và khả năng phục hồi.

Một số ví dụ:

- **Hiệu năng:** thời gian phản hồi, thông lượng, mức sử dụng tài nguyên và hành vi dưới tải.
- **Bảo mật:** xác thực, phân quyền, bảo vệ dữ liệu, xử lý đầu vào và khả năng chống khai thác trong phạm vi đánh giá.
- **Khả năng sử dụng:** người dùng có hoàn thành tác vụ dễ dàng và hiểu phản hồi hay không.
- **Độ tin cậy và phục hồi:** hệ thống xử lý lỗi, khởi động lại, khôi phục hoặc tiếp tục hoạt động như thế nào.
- **Tương thích:** hành vi trên trình duyệt, thiết bị, hệ điều hành hoặc phiên bản được hỗ trợ.

Kiểm thử phi chức năng không chỉ được thực hiện ở cấp độ hệ thống. Ví dụ, kiểm tra độ trễ của một hàm hoặc mức sử dụng bộ nhớ của một thành phần có thể được thực hiện ở cấp thành phần; đánh giá tải toàn hệ thống thường cần môi trường và cấu hình gần với vận hành thật.

### Kiểm thử cấu trúc (structural testing)

Kiểm thử cấu trúc sử dụng cấu trúc bên trong của mã hoặc mô hình để thiết kế và đánh giá kiểm thử. Ví dụ, nhóm có thể đo độ bao phủ câu lệnh, nhánh, điều kiện hoặc đường đi trong mã.

Kiểm thử cấu trúc giúp phát hiện phần logic chưa được thực thi và hướng dẫn bổ sung trường hợp kiểm thử. Tuy nhiên, thực thi một câu lệnh hoặc nhánh không đảm bảo kết quả nghiệp vụ được xác minh đúng. Chỉ số bao phủ phải được đọc cùng chất lượng khẳng định (assertion), dữ liệu và rủi ro.

### Kiểm thử liên quan đến thay đổi (change-related testing)

Loại kiểm thử này tập trung vào việc xác nhận một thay đổi đã được xử lý đúng và không gây tác động ngoài dự kiến.

- **Kiểm thử xác nhận (confirmation testing):** chạy lại các trường hợp liên quan đến lỗi đã sửa để xác minh lỗi cụ thể không còn xuất hiện trong điều kiện đã tái hiện.
- **Kiểm thử hồi quy (regression testing):** kiểm tra những vùng có thể bị ảnh hưởng bởi thay đổi nhằm phát hiện lỗi mới hoặc hành vi cũ bị phá vỡ.

Ví dụ, sau khi sửa quy tắc làm tròn giá, kiểm thử xác nhận chạy lại trường hợp từng sai; kiểm thử hồi quy kiểm tra thêm tổng đơn hàng, mã giảm giá, hóa đơn và báo cáo có sử dụng cùng quy tắc hay không.

### Kiểm thử tĩnh và kiểm thử động

Đây là một phân biệt khác theo việc có thực thi đối tượng kiểm thử hay không:

- **Kiểm thử tĩnh:** đánh giá tài liệu, yêu cầu, thiết kế hoặc mã mà không thực thi chương trình. Ví dụ: review yêu cầu, review mã, phân tích tĩnh.
- **Kiểm thử động:** thực thi phần mềm hoặc thành phần với dữ liệu và điều kiện xác định để quan sát hành vi.

Kiểm thử tĩnh có thể được áp dụng sớm ở nhiều cấp độ tài liệu và mã, giúp phát hiện mơ hồ hoặc lỗi trước khi chạy. Kiểm thử động cung cấp bằng chứng về hành vi khi thực thi. Hai cách bổ sung cho nhau.

## 4. Kỹ thuật thiết kế kiểm thử: chọn cách tạo trường hợp

Kỹ thuật thiết kế kiểm thử là phương pháp phân tích cơ sở kiểm thử để xác định điều kiện, dữ liệu và trường hợp cần kiểm tra. Việc chọn kỹ thuật phụ thuộc loại yêu cầu, cấu trúc hệ thống, rủi ro, dữ liệu sẵn có và bằng chứng mong muốn.

Ba nhóm kỹ thuật thường gặp là kỹ thuật hộp đen, kỹ thuật hộp trắng và kỹ thuật dựa trên kinh nghiệm.

### Kỹ thuật hộp đen (black-box techniques)

Kỹ thuật hộp đen thiết kế kiểm thử từ hành vi bên ngoài, yêu cầu hoặc mô hình nghiệp vụ mà không cần dựa vào cấu trúc mã bên trong.

**Phân vùng tương đương (equivalence partitioning)**

Chia miền dữ liệu thành các nhóm mà các giá trị trong cùng nhóm được kỳ vọng xử lý tương tự. Chọn một hoặc một số đại diện từ mỗi nhóm để giảm số trường hợp mà vẫn bao phủ các nhóm hành vi quan trọng.

Ví dụ, trường số lượng sản phẩm chỉ chấp nhận số nguyên từ 1 đến 99. Có thể chia thành các nhóm: nhỏ hơn 1, từ 1 đến 99, lớn hơn 99, và dữ liệu không phải số nguyên. Chọn đại diện như 0, 5, 100 và 2.5 để kiểm tra.

**Phân tích giá trị biên (boundary value analysis)**

Lỗi thường xuất hiện tại ranh giới của miền hợp lệ. Kỹ thuật này chọn giá trị ở biên, ngay dưới biên và ngay trên biên. Với miền 1 đến 99, các giá trị đáng chú ý là 0, 1, 2, 98, 99 và 100.

Phân vùng tương đương giúp xác định các nhóm dữ liệu; phân tích giá trị biên tập trung vào những điểm chuyển giữa nhóm hợp lệ và không hợp lệ. Hai kỹ thuật thường được kết hợp.

**Bảng quyết định (decision table testing)**

Dùng bảng để biểu diễn tổ hợp điều kiện và hành động hoặc kết quả tương ứng. Phù hợp với quy tắc nghiệp vụ có nhiều điều kiện kết hợp.

Ví dụ, mã giảm giá chỉ được áp dụng khi mã còn hiệu lực, đơn hàng đạt mức tối thiểu và người dùng thuộc nhóm được phép:

| Quy tắc | Mã còn hiệu lực | Đạt mức tối thiểu | Người dùng đủ điều kiện | Kết quả |
| --- | --- | --- | --- | --- |
| 1 | Có | Có | Có | Áp dụng giảm giá |
| 2 | Không | Có | Có | Từ chối mã |
| 3 | Có | Không | Có | Từ chối do chưa đủ mức đơn hàng |
| 4 | Có | Có | Không | Từ chối do không đủ điều kiện |

Trong hệ thống có nhiều điều kiện, nhóm có thể cần thêm tổ hợp để bao phủ đầy đủ hoặc dùng phân tích rủi ro để chọn các tổ hợp quan trọng. Không nên bỏ qua điều kiện chỉ vì bảng đã có vài dòng minh họa.

**Kiểm thử chuyển trạng thái (state transition testing)**

Dùng mô hình trạng thái và sự kiện để xác định các chuyển đổi hợp lệ, không hợp lệ và hành vi theo lịch sử.

Ví dụ, một đơn hàng có thể chuyển từ `Created` sang `PendingPayment`, rồi `Paid` hoặc `PaymentFailed`. Một đơn đã `Paid` không được chuyển ngược về `PendingPayment` chỉ vì người dùng gửi lại yêu cầu thanh toán. Kiểm thử nên bao gồm trạng thái ban đầu, sự kiện, trạng thái sau chuyển đổi và các chuyển đổi bị cấm.

**Kiểm thử dựa trên ca sử dụng (use-case testing)**

Thiết kế trường hợp từ luồng tương tác giữa tác nhân và hệ thống để hoàn thành mục tiêu. Cần xem xét luồng chính, luồng thay thế và luồng ngoại lệ.

Ví dụ, ca sử dụng “Đặt hàng” có luồng chính là chọn sản phẩm, nhập địa chỉ, chọn vận chuyển và thanh toán; luồng thay thế gồm dùng mã giảm giá; luồng ngoại lệ gồm hết hàng, thanh toán bị từ chối hoặc dịch vụ vận chuyển không phản hồi.

### Kỹ thuật hộp trắng (white-box techniques)

Kỹ thuật hộp trắng sử dụng cấu trúc bên trong của mã hoặc luồng điều khiển để thiết kế kiểm thử. Kỹ thuật này hữu ích khi cần đánh giá các câu lệnh, nhánh, điều kiện hoặc đường đi quan trọng.

**Bao phủ câu lệnh (statement coverage)**

Đo tỷ lệ câu lệnh có thể thực thi đã được chạy bởi bộ kiểm thử. Nếu có 100 câu lệnh có thể thực thi và 80 câu lệnh được chạy, độ bao phủ câu lệnh là 80%. Cần hiểu cách công cụ xác định câu lệnh có thể thực thi và mã bị loại trừ.

**Bao phủ nhánh (branch coverage)**

Đo tỷ lệ kết quả của các nhánh quyết định đã được thực hiện, ví dụ cả nhánh đúng và sai của điều kiện `if`. Bao phủ nhánh thường phát hiện trường hợp mà một câu lệnh đã được chạy nhưng một hướng quyết định chưa từng được kiểm tra.

Ví dụ:

```java
if (amount >= minimum && couponIsValid) {
    applyDiscount();
} else {
    rejectCoupon();
}
```

Nhóm cần tạo dữ liệu để kiểm tra nhánh áp dụng và nhánh từ chối. Với biểu thức có nhiều điều kiện, có thể cần kỹ thuật bao phủ điều kiện hoặc kết hợp điều kiện tùy mức đảm bảo cần đạt.

Bao phủ câu lệnh hoặc nhánh không chứng minh mọi đầu vào đều đúng, mọi tổ hợp điều kiện đã được kiểm tra hoặc yêu cầu nghiệp vụ đã được hiểu đúng. Đây là chỉ số về cấu trúc thực thi, cần được kết hợp với kỹ thuật hộp đen và xác minh kết quả.

### Kỹ thuật dựa trên kinh nghiệm (experience-based techniques)

Những kỹ thuật này tận dụng kiến thức miền nghiệp vụ, kinh nghiệm về lỗi và khả năng khám phá của người kiểm thử.

- **Dự đoán lỗi (error guessing):** dựa trên kinh nghiệm để dự đoán nơi dễ có lỗi, ví dụ nhập chuỗi rất dài, gửi biểu mẫu nhiều lần, dùng ký tự đặc biệt, thay đổi múi giờ hoặc mất kết nối giữa thao tác.
- **Kiểm thử thăm dò (exploratory testing):** vừa học hệ thống, thiết kế và thực hiện kiểm thử, vừa điều chỉnh hướng khám phá theo kết quả quan sát. Cần ghi lại mục tiêu phiên, dữ liệu, bước đi và phát hiện để có thể xem xét hoặc tái hiện.
- **Kiểm thử dựa trên checklist:** sử dụng danh sách câu hỏi hoặc điều kiện đã tích lũy từ kinh nghiệm và bài học trước đó. Checklist cần được cập nhật để không biến thành thao tác máy móc.

Kỹ thuật dựa trên kinh nghiệm đặc biệt hữu ích khi yêu cầu chưa đầy đủ hoặc cần tìm các hành vi bất ngờ. Chúng không thay thế việc phân tích yêu cầu và rủi ro; nên ghi lại cách kiểm thử và bằng chứng thu được.

## 5. Cách kết hợp cấp độ, loại kiểm thử và kỹ thuật

Để thiết kế chiến lược, nhóm có thể đi theo trình tự:

1. **Xác định rủi ro và yêu cầu:** điều gì có thể sai, hậu quả là gì và tiêu chí nào cần được xác minh?
2. **Chọn cấp độ:** lỗi có thể được phát hiện sớm nhất và rõ nhất ở ranh giới nào? Thành phần, tích hợp, hệ thống, tích hợp hệ thống hay chấp nhận?
3. **Chọn loại kiểm thử:** cần đánh giá tính đúng chức năng, hiệu năng, bảo mật, khả năng sử dụng, cấu trúc hay ảnh hưởng của thay đổi?
4. **Chọn kỹ thuật:** cơ sở kiểm thử phù hợp với phân vùng tương đương, giá trị biên, bảng quyết định, chuyển trạng thái, bao phủ cấu trúc hay khám phá?
5. **Xác định bằng chứng và điều kiện:** dữ liệu, môi trường, công cụ, cộng tác viên thật hoặc mô phỏng, tiêu chí đạt và cách lưu kết quả.
6. **Đánh giá phần chưa bao phủ:** rủi ro nào chưa có bằng chứng, kiểm thử nào trùng lặp và cần bổ sung ở đâu?

Ví dụ, với rủi ro “đơn hàng có thể bị thanh toán hai lần khi người dùng gửi lại yêu cầu”, nhóm có thể:

- Ở cấp thành phần, kiểm tra trực tiếp logic xử lý idempotency và chuyển trạng thái bằng kiểm thử chức năng, dùng bảng quyết định hoặc chuyển trạng thái để thiết kế trường hợp.
- Ở cấp tích hợp thành phần, kiểm tra cách `CheckoutService` và `PaymentAdapter` phối hợp khi nhận timeout hoặc phản hồi chậm; dùng mock để tạo điều kiện lỗi xác định.
- Ở cấp tích hợp hệ thống, xác minh hợp đồng và hành vi gửi lại với cổng thanh toán sandbox, bao gồm mã định danh yêu cầu và cách truy vấn trạng thái.
- Ở cấp hệ thống hoặc chấp nhận, kiểm tra hành trình người dùng và đối soát kết quả cuối cùng để xác nhận không có đơn hoặc giao dịch trùng trong phạm vi kịch bản.

Như vậy, cùng một rủi ro có thể cần nhiều cấp độ và kỹ thuật. Mỗi hoạt động cần bổ sung một loại bằng chứng cụ thể, tránh chạy lặp nhiều lần cùng một kịch bản mà không tăng mức tin cậy.

## 6. Ví dụ phân bổ kiểm thử cho chức năng đặt hàng

Giả sử hệ thống có quy tắc: người dùng chọn sản phẩm, nhập số lượng từ 1 đến 99, áp dụng mã giảm giá khi đơn hàng đủ điều kiện, sau đó thanh toán qua nhà cung cấp bên ngoài.

| Cấp độ | Loại kiểm thử | Kỹ thuật thiết kế phù hợp | Ví dụ trường hợp và bằng chứng |
| --- | --- | --- | --- |
| Thành phần | Chức năng | Phân vùng tương đương, giá trị biên | Kiểm tra số lượng 0, 1, 2, 98, 99, 100; xác minh kết quả xác thực và tính tổng |
| Thành phần | Chức năng | Bảng quyết định | Kết hợp mã hợp lệ, ngưỡng đơn hàng và nhóm người dùng; xác minh quyết định áp dụng ưu đãi |
| Thành phần | Cấu trúc | Bao phủ câu lệnh và nhánh | Kiểm tra các nhánh tính phí, áp dụng ưu đãi và từ chối dữ liệu không hợp lệ |
| Tích hợp thành phần | Chức năng và xử lý lỗi | Chuyển trạng thái, dự đoán lỗi | Kiểm tra trạng thái đơn khi kho hết hàng, thanh toán timeout hoặc phản hồi bị từ chối |
| Tích hợp hệ thống | Chức năng và tương thích | Hợp đồng API, phân vùng dữ liệu | Xác minh schema, mã phản hồi, đơn vị tiền, khóa idempotency và phiên bản API |
| Hệ thống | Chức năng và phi chức năng | Ca sử dụng, kiểm thử tải, khám phá | Thực hiện hành trình đặt hàng; đo thời gian phản hồi dưới tải; thử mất kết nối ở các bước quan trọng |
| Chấp nhận | Chức năng và khả năng sử dụng | Ca sử dụng, checklist nghiệp vụ | Đại diện nghiệp vụ xác minh quy trình đặt hàng, hủy, hoàn tiền và thông báo trạng thái |

Phân bổ trên là ví dụ. Nếu rủi ro bảo mật cao, nhóm có thể bổ sung kiểm thử phân quyền ở cấp thành phần, kiểm thử tích hợp xác thực và kiểm thử hệ thống cho các luồng truy cập. Nếu sản phẩm hỗ trợ nhiều trình duyệt hoặc thiết bị, kiểm thử tương thích cần được phân bổ ở phạm vi phù hợp.

## 7. Chọn cấp độ và kỹ thuật dựa trên rủi ro

Không phải mọi chức năng đều cần số lượng kiểm thử như nhau ở mỗi cấp độ. Nên ưu tiên theo mức độ tác động, khả năng xảy ra, độ phức tạp và chi phí phát hiện lỗi.

- **Logic ổn định, thuần và có nhiều giá trị biên:** thường phù hợp với nhiều kiểm thử thành phần nhanh, dùng phân vùng tương đương, giá trị biên và bảng quyết định.
- **Nhiều thành phần phối hợp hoặc chia sẻ trạng thái:** cần kiểm thử tích hợp để phát hiện lỗi giao diện, transaction, thứ tự và xử lý lỗi.
- **Phụ thuộc bên ngoài hoặc thay đổi phiên bản:** cần kiểm chứng hợp đồng, adapter và các luồng tích hợp đại diện.
- **Rủi ro chỉ xuất hiện trong bối cảnh sử dụng hoàn chỉnh:** cần kiểm thử hệ thống hoặc đầu cuối có chọn lọc, ví dụ hành trình thanh toán và khôi phục.
- **Nhu cầu nghiệp vụ hoặc quy định chấp nhận:** cần sự tham gia của người dùng hoặc đại diện có thẩm quyền ở cấp chấp nhận.

Kiểm thử ở cấp thấp thường nhanh, ổn định và giúp định vị lỗi tốt. Kiểm thử ở cấp cao xác minh nhiều thành phần trong bối cảnh gần thực tế nhưng thường chậm hơn, dễ phụ thuộc môi trường và khó xác định nguyên nhân. Vì vậy, nên phát hiện lỗi sớm ở nơi có thể kiểm soát, đồng thời duy trì đủ kiểm thử tích hợp và hệ thống cho rủi ro xuyên ranh giới.

Không có tỷ lệ cố định giữa kiểm thử đơn vị, tích hợp và đầu cuối phù hợp với mọi sản phẩm. Phân bổ cần dựa trên kiến trúc, rủi ro, tốc độ phản hồi, độ ổn định môi trường và chi phí bảo trì.

## 8. Tránh nhầm lẫn và lặp lại không cần thiết

Những sai lầm thường gặp khi xây dựng kế hoạch kiểm thử:

- **Gọi mọi kiểm thử tự động là kiểm thử đơn vị:** tự động hóa mô tả cách thực thi, không cho biết cấp độ. Một kiểm thử API tự động có thể là kiểm thử tích hợp hoặc hệ thống.
- **Coi chức năng là cấp độ:** chức năng là loại kiểm thử; nó có thể được đánh giá ở cấp thành phần, tích hợp, hệ thống hoặc chấp nhận.
- **Coi giá trị biên là loại kiểm thử:** đây là kỹ thuật thiết kế dữ liệu và trường hợp, có thể dùng trong nhiều loại kiểm thử.
- **Cho rằng kiểm thử hệ thống chỉ kiểm tra luồng đúng:** cần xem cả lỗi, hiệu năng, bảo mật, khả năng tương thích và các thuộc tính liên quan.
- **Dùng mock để kết luận tích hợp thật đã đúng:** mock giúp kiểm soát cộng tác viên nhưng không cung cấp bằng chứng đầy đủ về hệ thống bên ngoài.
- **Theo đuổi độ bao phủ mà bỏ qua kết quả:** câu lệnh được chạy không có nghĩa hành vi được xác minh hoặc rủi ro được kiểm soát.
- **Lặp cùng một kịch bản ở mọi cấp độ:** làm tăng thời gian và chi phí mà không bổ sung bằng chứng đáng kể. Mỗi cấp độ nên có mục tiêu riêng.
- **Không ghi rõ điều kiện kiểm thử:** kết quả thiếu phiên bản, môi trường, dữ liệu và phụ thuộc sẽ khó tái hiện và khó so sánh.

Để giảm lặp, nhóm nên liên kết từng trường hợp với yêu cầu hoặc rủi ro, cấp độ, loại kiểm thử, kỹ thuật và mục tiêu bằng chứng. Khi một trường hợp xuất hiện ở nhiều cấp độ, hãy giải thích sự khác nhau: ví dụ kiểm tra logic bằng mock ở cấp thành phần và xác minh giao dịch thật ở cấp tích hợp.

## 9. Mẫu ma trận phân bổ kiểm thử

Có thể dùng ma trận sau khi lập kế hoạch. Các ô không cần được điền bằng số lượng trường hợp; hãy ghi mục tiêu hoặc tham chiếu bộ kiểm thử tương ứng.

| Rủi ro/yêu cầu | Cấp độ | Loại kiểm thử | Kỹ thuật | Bằng chứng cần có |
| --- | --- | --- | --- | --- |
| Tính tổng đơn hàng sai ở biên | Thành phần | Chức năng | Giá trị biên, phân vùng tương đương | Kết quả tính tổng cho các giá trị biên và nhóm dữ liệu |
| Áp dụng sai ưu đãi khi nhiều điều kiện kết hợp | Thành phần | Chức năng | Bảng quyết định | Kết quả cho từng tổ hợp điều kiện quan trọng |
| Đơn hàng chuyển trạng thái sai khi thanh toán thất bại | Tích hợp thành phần | Chức năng, xử lý lỗi | Chuyển trạng thái, dự đoán lỗi | Trạng thái và dữ liệu sau từng phản hồi |
| API thanh toán thay đổi schema | Tích hợp hệ thống | Chức năng, tương thích | Kiểm thử hợp đồng | Kết quả xác minh consumer/provider hoặc sandbox |
| Hành trình đặt hàng chậm dưới tải | Hệ thống | Hiệu năng | Ca sử dụng, kiểm thử tải | p95/p99, thông lượng, tỷ lệ lỗi ở mức tải quy định |
| Quy trình đặt hàng đáp ứng chính sách | Chấp nhận | Chức năng, khả năng sử dụng | Ca sử dụng, checklist | Xác nhận của đại diện nghiệp vụ theo tiêu chí chấp nhận |

Ma trận cần được cập nhật khi yêu cầu, kiến trúc hoặc mức rủi ro thay đổi. Không nên coi ô đã có tên kiểm thử là bằng chứng đã đạt; cần tham chiếu kết quả thực hiện và phiên bản cụ thể.

## 10. Những điểm cần ghi nhớ

- Cấp độ kiểm thử xác định phạm vi và ranh giới của đối tượng được kiểm tra.
- Loại kiểm thử xác định thuộc tính chất lượng hoặc mục tiêu cần đánh giá.
- Kỹ thuật thiết kế kiểm thử xác định cách chọn điều kiện, dữ liệu và trường hợp kiểm thử.
- Một cấp độ có thể chứa nhiều loại kiểm thử; một loại kiểm thử và một kỹ thuật có thể xuất hiện ở nhiều cấp độ.
- Phân bổ kiểm thử cần xuất phát từ yêu cầu và rủi ro, đồng thời ghi rõ môi trường, cộng tác viên và giới hạn bằng chứng.
- Kiểm thử ở cấp thấp giúp phản hồi nhanh; kiểm thử tích hợp, hệ thống và chấp nhận cung cấp bằng chứng về tương tác và bối cảnh sử dụng.
- Không dùng tự động hóa hoặc độ bao phủ làm đại diện duy nhất cho chất lượng; mỗi trường hợp cần có mục tiêu và kết quả được xác minh.

## Câu hỏi tự kiểm tra

1. Hãy giải thích sự khác nhau giữa cấp độ kiểm thử, loại kiểm thử và kỹ thuật thiết kế kiểm thử bằng một ví dụ.
2. Kiểm thử hiệu năng có thể được thực hiện ở những cấp độ nào? Hãy nêu ví dụ và giải thích phạm vi của từng trường hợp.
3. Với quy tắc số lượng từ 1 đến 99, hãy áp dụng phân vùng tương đương và phân tích giá trị biên để chọn dữ liệu kiểm thử.
4. Vì sao kiểm thử thành phần dùng mock không thể thay thế hoàn toàn kiểm thử tích hợp với dịch vụ thật?
5. Hãy chọn một rủi ro trong luồng nghiệp vụ của bạn và lập ma trận gồm cấp độ, loại kiểm thử, kỹ thuật và bằng chứng cần có.
6. Sau khi sửa lỗi tính giá, hãy phân biệt trường hợp kiểm thử xác nhận và các trường hợp kiểm thử hồi quy cần thực hiện.
