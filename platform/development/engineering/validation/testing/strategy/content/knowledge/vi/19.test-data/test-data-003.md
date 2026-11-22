# Thiết kế dữ liệu cho trường hợp biên, lỗi và khối lượng lớn

## 1. Vì sao thiết kế dữ liệu kiểm thử quyết định chất lượng xác nhận?

Dữ liệu kiểm thử quyết định hệ thống được đặt vào những trạng thái nào và nhóm có thể quan sát được những hành vi nào. Một bộ kiểm thử có nhiều bước nhưng chỉ dùng dữ liệu đơn giản, hợp lệ và có quy mô nhỏ thường chỉ xác nhận đường đi thuận lợi. Các lỗi quan trọng lại thường xuất hiện ở ranh giới: giá trị ngay dưới hoặc trên giới hạn, trường bị thiếu, dữ liệu không nhất quán, ký tự đặc biệt, trạng thái bất thường, nhiều yêu cầu đồng thời hoặc khối lượng dữ liệu lớn hơn nhiều so với lúc phát triển.

Thiết kế dữ liệu kiểm thử cần bắt đầu từ quy tắc nghiệp vụ, cấu trúc dữ liệu, rủi ro và điều kiện vận hành. Nhóm phải xác định dữ liệu nào đại diện cho hành vi bình thường, dữ liệu nào kiểm tra giới hạn, dữ liệu nào cố ý vi phạm quy tắc và dữ liệu nào giúp đánh giá hiệu năng, khả năng mở rộng hoặc độ bền. Dữ liệu cần có thể tạo lại, cô lập, làm sạch và truy vết đến lần chạy kiểm thử.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, dữ liệu cho trường hợp biên, lỗi và khối lượng lớn giúp phát hiện những vấn đề mà kiểm thử happy path khó tìm thấy: tràn số, làm tròn sai, mất dữ liệu, xử lý null không nhất quán, lỗi phân quyền, giao dịch trùng, deadlock, suy giảm hiệu năng hoặc cạn tài nguyên. Thiết kế dữ liệu tốt cũng làm kết quả kiểm thử đáng tin hơn vì nhóm hiểu rõ điều kiện đã tạo ra kết quả.

Một tập dữ liệu có giá trị không nhất thiết phải lớn. Một số giá trị được chọn đúng tại ranh giới có thể phát hiện lỗi mà hàng nghìn bản ghi thông thường không phát hiện được. Ngược lại, kiểm thử khối lượng lớn cần dữ liệu đủ đa dạng và có phân bố phù hợp; nhân bản một bản ghi đơn giản hàng triệu lần có thể không đại diện cho tải và hành vi thật.

## 2. Phân loại dữ liệu kiểm thử theo mục đích

Trước khi tạo dữ liệu, cần xác định mục đích của từng nhóm dữ liệu. Một tập dữ liệu có thể phục vụ nhiều mục tiêu, nhưng cần ghi rõ những điều kiện mà nó hỗ trợ.

| Loại dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Dữ liệu hợp lệ thông thường | Xác nhận luồng nghiệp vụ chính | Người dùng có hồ sơ đầy đủ và đặt hàng với sản phẩm còn tồn |
| Dữ liệu đại diện | Mô phỏng dữ liệu gần với phân bố sử dụng thực tế | Khách hàng theo khu vực, nhóm tuổi, loại đơn và kênh giao dịch |
| Dữ liệu biên | Kiểm tra giới hạn và điểm chuyển trạng thái | Chuỗi dài đúng giới hạn, số tiền bằng 0, ngày cuối tháng |
| Dữ liệu không hợp lệ | Xác nhận hệ thống từ chối hoặc xử lý an toàn đầu vào sai | Email sai định dạng, số âm ở trường không cho phép âm |
| Dữ liệu bất thường | Kiểm tra tình huống hiếm hoặc không nhất quán | Bản ghi thiếu quan hệ, timestamp tương lai, trạng thái không mong đợi |
| Dữ liệu lỗi phụ thuộc | Kiểm tra timeout, retry và phản hồi lỗi từ hệ thống khác | Mã đối tác không tồn tại, webhook trùng, dịch vụ phụ thuộc trả 503 |
| Dữ liệu đồng thời | Kiểm tra tranh chấp và cập nhật song song | Hai yêu cầu cùng mua đơn vị hàng cuối cùng |
| Dữ liệu khối lượng lớn | Đánh giá hiệu năng, thông lượng và tài nguyên | Hàng triệu giao dịch với nhiều khách hàng, sản phẩm và trạng thái |
| Dữ liệu dài hạn/tích lũy | Kiểm tra tăng trưởng, lưu trữ và truy vấn theo thời gian | Lịch sử giao dịch nhiều năm, log hoặc sự kiện tích lũy |
| Dữ liệu phục hồi | Xác nhận backup, restore, migration và đối soát | Snapshot có quan hệ dữ liệu, bản ghi cập nhật dở dang và dữ liệu lịch sử |

Không nên dùng một tập dữ liệu duy nhất cho mọi loại kiểm thử. Dữ liệu phục vụ kiểm thử chức năng có thể nhỏ và dễ đọc; dữ liệu hiệu năng cần quy mô, phân bố và trạng thái đủ đại diện; dữ liệu bảo mật cần bao gồm các trường hợp nhạy cảm nhưng phải được tạo hoặc xử lý an toàn.

## 3. Phân tích yêu cầu dữ liệu trước khi tạo

### 3.1. Đọc quy tắc và ràng buộc của miền nghiệp vụ

Xác định kiểu dữ liệu, giới hạn, tính bắt buộc, quan hệ, trạng thái và quy tắc chuyển đổi. Với mỗi trường, cần trả lời:

- Trường có bắt buộc không? Giá trị null, chuỗi rỗng hoặc không có trường được hiểu khác nhau thế nào?
- Kiểu và định dạng hợp lệ là gì?
- Giá trị tối thiểu, tối đa, độ dài hoặc số chữ số cho phép là bao nhiêu?
- Có quy tắc phụ thuộc vào trường khác không?
- Có quy tắc về duy nhất, thứ tự, thời gian hoặc trạng thái không?
- Giá trị được chuẩn hóa, làm tròn, cắt bớt hoặc chuyển đổi như thế nào?
- Có yêu cầu bảo mật, riêng tư hoặc thời hạn lưu trữ không?

Ví dụ, trường số tiền có thể là số thập phân với hai chữ số sau dấu phẩy, không được âm và có giới hạn theo loại giao dịch. Chỉ kiểm tra một giá trị như 100,00 sẽ không phát hiện lỗi khi số tiền bằng 0, sát giới hạn tối đa, có nhiều chữ số thập phân hoặc được chuyển đổi giữa đơn vị đồng và xu.

### 3.2. Xác định quan hệ và bất biến dữ liệu

Nhiều lỗi chỉ xuất hiện khi dữ liệu liên quan với nhau. Ví dụ:

- Đơn hàng phải tham chiếu đến khách hàng tồn tại.
- Chi tiết đơn hàng phải thuộc đúng đơn hàng.
- Số lượng tồn không được âm sau khi xác nhận giao dịch.
- Tổng tiền đơn hàng phải bằng tổng các dòng hàng, thuế và phí theo quy tắc.
- Mỗi giao dịch có mã idempotency duy nhất trong phạm vi quy định.
- Một sự kiện đã xử lý không được tạo tác dụng phụ lần thứ hai.
- Trạng thái cuối không thể quay lại trạng thái trước nếu nghiệp vụ không cho phép.

Ghi các bất biến này thành điều kiện kiểm thử và assertion dữ liệu. Dữ liệu tạo ra phải tuân thủ quan hệ khi dùng cho kịch bản hợp lệ; khi cố ý phá vỡ quan hệ để kiểm tra lỗi, phải ghi rõ điểm không hợp lệ và kết quả mong đợi.

### 3.3. Xác định phân bố và hành vi thực tế

Với kiểm thử tải hoặc khối lượng lớn, cần hiểu dữ liệu thực tế có phân bố như thế nào. Hãy xem xét:

- Số lượng bản ghi theo khách hàng, tài khoản, khu vực hoặc loại giao dịch.
- Mức độ lệch phân bố, ví dụ một số khách hàng có rất nhiều giao dịch.
- Tỷ lệ trạng thái hoạt động, hoàn tất, hủy, lỗi và chờ xử lý.
- Tỷ lệ dữ liệu mới so với dữ liệu lịch sử.
- Tần suất trùng, giá trị thiếu, trường tùy chọn và dữ liệu hiếm.
- Phân bố thời gian, mùa vụ, giờ cao điểm và thời gian tích lũy.
- Kích thước payload, độ dài văn bản và số lượng phần tử trong mảng.

Không cần sao chép dữ liệu sản xuất để có tính đại diện. Có thể dùng thống kê tổng hợp, dữ liệu tổng hợp hoặc dữ liệu đã được xử lý theo chính sách. Điều quan trọng là giữ các đặc điểm phân bố có ảnh hưởng đến truy vấn, xử lý và hiệu năng.

## 4. Thiết kế dữ liệu cho trường hợp biên

### 4.1. Phân vùng tương đương

Phân vùng tương đương (equivalence partitioning) chia miền đầu vào thành các nhóm mà hệ thống dự kiến xử lý theo cùng một quy tắc. Thay vì kiểm tra mọi giá trị, chọn đại diện từ mỗi nhóm hợp lệ và không hợp lệ.

Ví dụ, một API chấp nhận tuổi từ 18 đến 65:

| Phân vùng | Ví dụ dữ liệu | Kết quả mong đợi |
|---|---:|---|
| Hợp lệ, gần đầu dưới | 18 | Chấp nhận |
| Hợp lệ, bên trong khoảng | 35 | Chấp nhận |
| Hợp lệ, gần đầu trên | 65 | Chấp nhận |
| Không hợp lệ, dưới giới hạn | 17 | Từ chối theo hợp đồng |
| Không hợp lệ, trên giới hạn | 66 | Từ chối theo hợp đồng |
| Không hợp lệ, kiểu sai | "eighteen" | Trả lỗi dữ liệu |
| Không hợp lệ, thiếu/null | null hoặc không gửi trường | Xử lý theo quy tắc bắt buộc/tùy chọn |

Phân vùng cần dựa trên cách hệ thống xử lý, không chỉ dựa trên kiểu dữ liệu. Nếu người dùng dưới 18 tuổi và người dùng trên 65 tuổi nhận hai thông báo hoặc quy trình khác nhau, cần tách thành hai phân vùng.

### 4.2. Phân tích giá trị biên

Phân tích giá trị biên (boundary value analysis) tập trung vào các điểm sát giới hạn vì lỗi thường xảy ra ở phép so sánh, làm tròn, chuyển kiểu và điều kiện một bên inclusive, bên kia exclusive.

Với giới hạn từ 18 đến 65, nên xem xét ít nhất 17, 18, 19, 64, 65 và 66. Với giới hạn kích thước 1 đến 100 phần tử, kiểm tra 0, 1, 2, 99, 100 và 101. Với trường chuỗi tối đa 255 ký tự, kiểm tra 254, 255 và 256 ký tự; đồng thời xét ký tự Unicode vì một ký tự hiển thị có thể chiếm nhiều byte hoặc nhiều code point.

Các loại biên thường gặp:

- Giá trị số nhỏ nhất/lớn nhất, số âm, số 0 và giá trị sát ngưỡng.
- Độ dài chuỗi, kích thước file, kích thước payload và số phần tử mảng.
- Ngày đầu/cuối tháng, năm nhuận, giao thời gian và múi giờ.
- Số trang đầu/cuối, cursor rỗng và giới hạn page size.
- Số lần retry, số kết nối đồng thời và thời hạn timeout.
- Trạng thái trước/sau một chuyển đổi hoặc thời điểm hết hạn.

Với khoảng giá trị có nhiều ranh giới, cần chọn điểm đại diện cho từng ranh giới. Không chỉ kiểm tra min và max nếu có các ngưỡng nghiệp vụ ở giữa.

### 4.3. Kiểm thử null, thiếu trường và giá trị rỗng

Ba trường hợp này thường bị nhầm lẫn:

- **Thiếu trường:** request không chứa thuộc tính.
- **Null:** thuộc tính có mặt nhưng giá trị là null.
- **Rỗng:** thuộc tính có mặt với chuỗi rỗng, mảng rỗng hoặc đối tượng rỗng.

Hệ thống có thể xử lý chúng khác nhau. Ví dụ, thiếu trường địa chỉ có thể giữ nguyên giá trị cũ trong PATCH, null có thể xóa địa chỉ và chuỗi rỗng có thể bị từ chối. Cần thiết kế dữ liệu riêng cho từng trường hợp và xác nhận hợp đồng.

### 4.4. Số học, độ chính xác và tràn số

Với dữ liệu tiền tệ, tỷ lệ, số lượng và phép tính tích lũy, cần kiểm tra:

- Giá trị âm, 0, rất nhỏ và rất lớn.
- Số có nhiều chữ số thập phân.
- Quy tắc làm tròn ở nửa đơn vị và sai số tích lũy.
- Chuyển đổi giữa kiểu số nguyên, số thực và decimal.
- Giá trị vượt giới hạn kiểu dữ liệu hoặc cột database.
- Tổng của nhiều phần tử có thể vượt giới hạn dù từng phần tử hợp lệ.

Không dùng số thực nhị phân cho phép tính tiền nếu yêu cầu cần độ chính xác thập phân. Dữ liệu kiểm thử nên có trường hợp làm lộ sai số như 0,1 + 0,2, nhiều dòng có số lẻ và các giá trị sát ngưỡng làm tròn.

### 4.5. Ngày giờ và múi giờ

Ngày giờ có nhiều trường hợp biên dễ bị bỏ sót:

- Ngày 28/29 tháng 2 trong năm nhuận và năm thường.
- Ngày cuối tháng, cuối năm và thời điểm chuyển năm.
- Thời điểm đúng trước, đúng tại và sau thời hạn hết hạn.
- Timestamp có múi giờ, không có múi giờ hoặc offset khác nhau.
- Chuyển đổi giờ mùa hè ở các khu vực có áp dụng.
- Sự kiện đến trễ hoặc thứ tự timestamp khác thứ tự xử lý.
- Khoảng thời gian qua nửa đêm hoặc qua ranh giới ngày nghiệp vụ.

Nên dùng đồng hồ có thể kiểm soát hoặc dữ liệu thời gian cố định thay vì phụ thuộc thời gian thực của máy. Khi hệ thống dùng UTC để lưu và múi giờ địa phương để hiển thị, cần kiểm tra cả hai chiều.

### 4.6. Unicode, định dạng và ký tự đặc biệt

Với trường văn bản, kiểm tra:

- Dấu tiếng Việt, ký tự có dấu kết hợp và dạng Unicode chuẩn hóa khác nhau.
- Emoji hoặc ký tự ngoài Basic Multilingual Plane.
- Khoảng trắng đầu/cuối, tab, xuống dòng và ký tự điều khiển.
- Chuỗi dài, chuỗi chỉ có khoảng trắng và chuỗi rỗng.
- Ký tự phân cách, dấu nháy, dấu gạch chéo và ký tự escape.
- Nội dung có vẻ giống HTML, SQL hoặc script.

Mục đích là xác nhận xử lý và hiển thị an toàn, không phải thực thi payload nguy hiểm. Dùng dữ liệu vô hại để kiểm tra encoding, escaping, validation và chống injection; thực hiện kiểm thử bảo mật chuyên sâu theo quy trình riêng.

### 4.7. Tổ hợp và tương tác giữa trường

Hai trường riêng lẻ có thể hợp lệ nhưng tổ hợp của chúng không hợp lệ. Ví dụ, ngày kết thúc phải sau ngày bắt đầu; loại tài khoản doanh nghiệp mới được dùng hạn mức cao; quốc gia và mã bưu chính phải tương thích; trạng thái đã hủy không được có thời điểm giao hàng.

Có thể dùng bảng quyết định để liệt kê tổ hợp quan trọng. Với số lượng tổ hợp lớn, áp dụng pairwise hoặc combinatorial testing để giảm số trường hợp nhưng vẫn bao phủ các tương tác được chọn. Những tổ hợp có hậu quả nghiêm trọng cần được kiểm tra riêng, không loại bỏ chỉ vì kỹ thuật pairwise không chọn.

## 5. Thiết kế dữ liệu cho tình huống lỗi và đầu vào không hợp lệ

### 5.1. Đầu vào sai kiểu hoặc sai định dạng

Tạo dữ liệu có kiểu không đúng, định dạng sai hoặc giá trị không thể phân tích: số thay cho chuỗi, chuỗi thay cho số, JSON không hợp lệ, ngày không tồn tại, enum không hỗ trợ hoặc định danh sai định dạng. Xác nhận hệ thống từ chối rõ ràng, không lưu dữ liệu một phần và không để lộ stack trace hay thông tin nội bộ.

### 5.2. Vi phạm ràng buộc và quan hệ

Kiểm tra khóa ngoại không tồn tại, giá trị duy nhất bị trùng, quan hệ sai chủ sở hữu, bản ghi con không có bản ghi cha hoặc trạng thái không hợp lệ. Ví dụ, gửi yêu cầu cập nhật đơn hàng bằng customer ID của người dùng khác để xác nhận cả tính toàn vẹn và phân quyền.

### 5.3. Dữ liệu bị cắt cụt hoặc hỏng

Mô phỏng payload thiếu phần cuối, file hỏng, encoding không hợp lệ, message bị cắt hoặc bản ghi có trường bắt buộc không hoàn chỉnh. Xác nhận hệ thống phát hiện lỗi, không ghi trạng thái thành công giả và có thể tiếp tục xử lý các bản ghi hợp lệ khác nếu thiết kế hỗ trợ.

### 5.4. Trạng thái không nhất quán

Tạo dữ liệu phản ánh các tình huống:

- Đơn hàng đã hủy nhưng vẫn có sự kiện giao hàng.
- Thanh toán đã hoàn tất nhưng consumer chưa nhận webhook.
- Bản ghi đã bị xóa nhưng cache còn dữ liệu cũ.
- Hai bản cập nhật cùng sửa một phiên bản dữ liệu.
- Một message được gửi lặp hoặc đến sai thứ tự.
- Job bị dừng sau khi ghi một phần dữ liệu.

Các trường hợp này cần có expected behavior rõ: từ chối, bỏ qua, đối soát, retry, chuyển vào dead-letter queue hoặc yêu cầu can thiệp. Không tạo trạng thái sai chỉ để có dữ liệu “bẩn” mà không biết hệ thống phải xử lý thế nào.

### 5.5. Lỗi phụ thuộc và điều kiện mạng

Đối với dịch vụ bên ngoài, dữ liệu lỗi có thể là phản hồi 4xx/5xx, timeout, phản hồi chậm, payload không đầy đủ, chứng chỉ không hợp lệ, rate limit hoặc kết nối bị đóng. Dùng mock, simulator hoặc fault injection được kiểm soát để tái lập tình huống.

Khi kiểm tra retry, cần phân biệt lỗi có thể retry và lỗi không nên retry. Ví dụ, timeout tạm thời có thể được retry với backoff; lỗi xác thực hoặc dữ liệu không hợp lệ thường cần sửa request. Với thao tác có tác dụng phụ, cần kiểm tra idempotency để tránh tạo giao dịch trùng.

### 5.6. Kiểm tra dữ liệu lỗi có an toàn không

Dữ liệu sai không nên khiến hệ thống:

- Lộ thông tin nhạy cảm hoặc chi tiết nội bộ.
- Ghi một phần dữ liệu mà không có trạng thái nhất quán.
- Bỏ qua kiểm tra phân quyền.
- Tạo giao dịch hoặc tác dụng phụ trùng.
- Làm cạn tài nguyên do payload quá lớn hoặc xử lý lặp vô hạn.
- Làm hỏng các bản ghi hợp lệ khác nếu yêu cầu xử lý theo từng bản ghi.

Kết quả mong đợi cần mô tả cả phản hồi bên ngoài và trạng thái dữ liệu bên trong có thể kiểm chứng.

## 6. Thiết kế dữ liệu cho khối lượng lớn

### 6.1. Phân biệt tải, khối lượng và thời gian tích lũy

Các bài kiểm thử quy mô lớn có thể tập trung vào những đặc tính khác nhau:

- **Load testing:** xác nhận hành vi ở tải dự kiến hoặc tải thông thường.
- **Stress testing:** tăng tải vượt điều kiện dự kiến để tìm điểm suy giảm hoặc giới hạn.
- **Spike testing:** tạo mức tăng tải đột ngột để kiểm tra khả năng phản ứng.
- **Soak/endurance testing:** duy trì tải trong thời gian dài để phát hiện rò rỉ bộ nhớ, suy giảm hiệu năng hoặc tích tụ tài nguyên.
- **Volume testing:** kiểm tra hệ thống với khối lượng dữ liệu lớn trong database, file, queue hoặc kho lưu trữ.
- **Scalability testing:** đánh giá khả năng tăng tài nguyên hoặc số instance khi tải tăng.

Một hệ thống có thể xử lý tốt 1.000 yêu cầu mỗi giây với database nhỏ nhưng suy giảm mạnh khi bảng có hàng trăm triệu bản ghi. Ngược lại, truy vấn có thể nhanh trên dữ liệu lớn nhưng dịch vụ không chịu được spike do giới hạn connection pool. Cần thiết kế dữ liệu và tải theo mục tiêu cụ thể.

### 6.2. Xác định quy mô và hồ sơ tải

Trước khi tạo dữ liệu, xác định:

- Tổng số bản ghi và dung lượng lưu trữ cần có.
- Số lượng người dùng, tài khoản, sản phẩm hoặc thực thể.
- Số quan hệ và phân bố bản ghi theo thực thể.
- Tỷ lệ đọc/ghi/cập nhật/xóa.
- Số request đồng thời và tốc độ gửi request.
- Kích thước payload trung bình, phân vị và tối đa.
- Thời lượng chạy và khoảng nghỉ.
- Tỷ lệ thành công, lỗi và retry dự kiến.
- Tình trạng cache nóng/lạnh và dữ liệu mới/cũ.

Nên xây dựng một workload profile có căn cứ từ metric, log đã tổng hợp, dự báo tăng trưởng hoặc giả định được chủ sở hữu xác nhận. Nếu dùng tải đồng đều trong khi sản xuất có một số tài khoản chiếm phần lớn giao dịch, kết quả có thể bỏ qua hot partition, lock contention hoặc truy vấn lệch phân bố.

### 6.3. Tạo phân bố dữ liệu đại diện

Một tập dữ liệu quy mô lớn nên có nhiều loại bản ghi và mức độ hoạt động khác nhau:

- Nhiều nhóm thực thể và quan hệ có kích thước khác nhau.
- Một số thực thể có lịch sử dài, một số chỉ có ít bản ghi.
- Trạng thái đang hoạt động, đã hoàn tất, hủy, lưu trữ và lỗi.
- Giá trị thường gặp cùng một tỷ lệ nhỏ giá trị hiếm.
- Phân bố thời gian theo giờ, ngày, tháng và mùa vụ.
- Kích thước payload nhỏ, trung bình và lớn.
- Trường tùy chọn có tỷ lệ thiếu phù hợp với dữ liệu thực tế.
- Một số khóa có tần suất truy cập cao để kiểm tra điểm nóng.

Không nên chỉ nhân bản cùng một dòng dữ liệu vì cache, index và tính duy nhất có thể khiến hành vi khác hẳn dữ liệu thực. Dữ liệu tổng hợp nên tạo được tính đa dạng và quan hệ nhất quán.

### 6.4. Tạo dữ liệu theo lô

Với hàng triệu bản ghi, tạo dữ liệu theo lô giúp kiểm soát bộ nhớ và thời gian. Có thể dùng script hoặc công cụ sinh dữ liệu để:

1. Tạo danh mục thực thể cha.
2. Tạo thực thể con tham chiếu đúng khóa cha.
3. Sinh các sự kiện hoặc giao dịch theo phân bố.
4. Tạo trạng thái và timestamp có ý nghĩa.
5. Nạp theo batch size đã xác định.
6. Kiểm tra số lượng, khóa duy nhất và bất biến sau nạp.
7. Lưu seed/config để tái tạo cùng tập dữ liệu.

Batch size cũng cần được kiểm tra. Batch quá nhỏ làm tăng overhead; batch quá lớn có thể gây áp lực bộ nhớ, transaction dài hoặc lock. Không có một kích thước batch tối ưu cho mọi hệ thống.

### 6.5. Dữ liệu nóng, lạnh và cache

Kiểm thử hiệu năng cần xác định trạng thái cache. Chạy nhiều lần trên cùng một dữ liệu có thể đo cache nóng, không phản ánh lần truy cập đầu hoặc dữ liệu ít dùng. Nên phân biệt:

- Cache nóng: các khóa thường xuyên được truy cập và dữ liệu đã nằm trong cache.
- Cache lạnh: dữ liệu chưa được nạp hoặc cache đã được làm sạch theo cách được phép.
- Cache hỗn hợp: tỷ lệ truy cập nóng/lạnh gần với hành vi dự kiến.

Không xóa cache của môi trường dùng chung hoặc sản xuất nếu chưa có phê duyệt. Ghi rõ trạng thái cache khi so sánh kết quả.

### 6.6. Dữ liệu và kiểm thử đồng thời

Để kiểm tra tranh chấp, cần tạo nhiều yêu cầu tác động đến cùng một tài nguyên và các tài nguyên khác nhau. Ví dụ:

- Nhiều người mua cùng đặt sản phẩm có một đơn vị tồn kho.
- Hai tiến trình cùng cập nhật một bản ghi.
- Nhiều worker cùng lấy message từ một queue.
- Nhiều giao dịch cùng cập nhật số dư hoặc hạn mức.
- Nhiều consumer xử lý cùng một event ID.

Thiết kế dữ liệu phải cho phép xác minh bất biến sau khi chạy: tồn kho không âm, số dư đúng, không có bản ghi trùng, mỗi message được xử lý theo ngữ nghĩa đã cam kết và không mất cập nhật. Cần ghi seed và cách tạo đồng thời để có thể lặp lại điều tra.

## 7. Kỹ thuật tạo dữ liệu kiểm thử

### 7.1. Dữ liệu cố định (static/fixture)

Dữ liệu cố định phù hợp cho kiểm thử đơn vị, thành phần hoặc các trường hợp cần kết quả dễ hiểu. Fixture nên nhỏ, có tên mô tả mục đích và được quản lý phiên bản. Không để fixture quá lớn hoặc phụ thuộc vào thứ tự chạy.

Ưu điểm là dễ tái lập và dễ điều tra. Hạn chế là có thể không bao phủ sự đa dạng hoặc phân bố thực tế. Nên bổ sung dữ liệu sinh tự động cho trường hợp biên và khối lượng lớn.

### 7.2. Dữ liệu sinh theo quy tắc (synthetic data)

Dữ liệu tổng hợp được tạo theo schema, quy tắc nghiệp vụ và phân bố đã xác định. Có thể dùng seed để tạo cùng một tập dữ liệu qua nhiều lần chạy. Ví dụ, tạo khách hàng, đơn hàng và giao dịch với số lượng, trạng thái và timestamp theo cấu hình.

Ưu điểm là kiểm soát được, không cần sao chép dữ liệu thật và dễ tạo giá trị hiếm. Hạn chế là dữ liệu có thể quá sạch hoặc không phản ánh tương quan thực tế nếu mô hình sinh đơn giản. Cần xác nhận chất lượng dữ liệu tổng hợp với người hiểu miền nghiệp vụ.

### 7.3. Dữ liệu đã ẩn danh hoặc giả danh

Khi cần đặc điểm gần với dữ liệu thật, tổ chức có thể dùng dữ liệu đã ẩn danh hoặc giả danh theo chính sách. Việc loại bỏ tên không tự động làm dữ liệu vô danh; tổ hợp thuộc tính vẫn có thể nhận diện một cá nhân. Cần đánh giá khả năng tái nhận diện, kiểm soát quyền truy cập, mục đích sử dụng và thời hạn lưu giữ.

Không sao chép dữ liệu sản xuất sang môi trường kiểm thử chỉ vì cần tính đại diện. Phải có phê duyệt và biện pháp bảo vệ phù hợp, ưu tiên dữ liệu tổng hợp hoặc phương pháp giảm thiểu rủi ro.

### 7.4. Property-based testing và dữ liệu ngẫu nhiên có kiểm soát

Property-based testing sinh nhiều đầu vào theo miền dữ liệu và kiểm tra các thuộc tính bất biến thay vì chỉ kiểm tra một vài ví dụ cố định. Ví dụ, với phép tính tổng đơn hàng, thuộc tính có thể là tổng không âm, tổng bằng tổng dòng hàng sau quy tắc làm tròn và thứ tự dòng không làm thay đổi kết quả.

Dữ liệu ngẫu nhiên cần có seed và khả năng thu nhỏ trường hợp thất bại (shrinking) nếu framework hỗ trợ. Khi tìm được lỗi, lưu đầu vào cụ thể và seed để tái hiện. Không dùng randomness không kiểm soát trong test cổng phát hành vì kết quả có thể khó lặp lại.

### 7.5. Mutation và biến đổi dữ liệu

Có thể tạo biến thể từ một bản ghi hợp lệ bằng cách thay đổi một hoặc nhiều thuộc tính: bỏ trường, đổi kiểu, tăng độ dài, làm lệch quan hệ, đổi trạng thái hoặc dịch timestamp. Kỹ thuật này hữu ích khi muốn tạo nhanh nhiều trường hợp lỗi có chủ đích.

Mỗi biến đổi cần có mục tiêu và expected result. Tránh biến đổi ngẫu nhiên đến mức không biết dữ liệu vi phạm quy tắc nào hoặc hệ thống cần phản ứng ra sao.

### 7.6. Data factory và builder

Data factory hoặc builder giúp tạo đối tượng hợp lệ với giá trị mặc định và cho phép ghi đè trường cần thử. Ví dụ, một builder tạo đơn hàng hợp lệ trước, sau đó test chỉ thay đổi số lượng hoặc trạng thái cần kiểm tra. Cách này giảm lặp dữ liệu nhưng cần tránh ẩn quá nhiều logic trong helper.

Các factory cần:

- Có giá trị mặc định hợp lệ và dễ hiểu.
- Cho phép tạo dữ liệu biên có chủ đích.
- Không tạo ID hoặc timestamp không xác định nếu test cần tái lập.
- Tạo quan hệ nhất quán giữa các thực thể.
- Có cách dọn dữ liệu hoặc namespace riêng.
- Không phụ thuộc vào trạng thái toàn cục hoặc thứ tự test.

## 8. Tính tái lập, cô lập và dọn dẹp dữ liệu

### 8.1. Seed và định danh lần chạy

Khi dùng dữ liệu sinh tự động, lưu seed hoặc cấu hình sinh. Mỗi test run nên có định danh riêng để tránh xung đột khi chạy song song. Có thể dùng namespace, tenant, schema hoặc tiền tố định danh được quản lý.

Nếu một test thất bại với seed cụ thể, cần lưu seed, phiên bản generator và cấu hình. Chỉ seed thôi có thể chưa đủ nếu thuật toán sinh hoặc schema thay đổi; cần ghi cả phiên bản mã tạo dữ liệu.

### 8.2. Cô lập trạng thái

Các test không nên phụ thuộc vào thứ tự chạy hoặc trạng thái do test khác tạo. Có thể dùng transaction rollback, database/schema riêng, container riêng, tenant riêng hoặc API reset có kiểm soát. Với hệ thống bất đồng bộ, cần chờ xử lý message hoàn tất và xác nhận trạng thái trước khi cleanup.

Không xóa dữ liệu dùng chung nếu không sở hữu hoặc chưa biết tác động. Cleanup phải giới hạn theo test run ID hoặc namespace cụ thể.

### 8.3. Idempotency của bước chuẩn bị

Script tạo dữ liệu nên có hành vi rõ khi chạy lại. Có thể tạo mới với ID riêng, cập nhật theo khóa xác định hoặc dừng nếu phát hiện dữ liệu đã tồn tại. Không để script chạy lại âm thầm nhân đôi dữ liệu hoặc thay đổi fixture đang được test khác sử dụng.

### 8.4. Cleanup và dữ liệu tồn dư

Sau kiểm thử, dọn dữ liệu, file, queue message, tài khoản và tài nguyên tạm theo chính sách. Nếu cần giữ dữ liệu để điều tra, đánh dấu trạng thái, giới hạn quyền và thời hạn lưu. Dữ liệu tồn dư có thể làm sai kết quả lần chạy sau hoặc tăng chi phí hạ tầng.

### 8.5. Đồng hồ và dữ liệu thời gian

Với test hết hạn, lịch chạy và sự kiện theo thời gian, ưu tiên clock có thể giả lập hoặc dữ liệu timestamp cố định. Tránh phụ thuộc vào giờ hiện tại khiến test chỉ chạy đúng trong một khoảng thời gian. Ghi múi giờ, định dạng và nguồn thời gian của môi trường.

## 9. Bảo vệ dữ liệu và tuân thủ

Thiết kế dữ liệu kiểm thử phải giảm nguy cơ lộ thông tin và tác động đến người thật:

- Ưu tiên dữ liệu tổng hợp hoặc dữ liệu đã được phê duyệt.
- Không đưa mật khẩu, token, khóa ký hoặc secret vào fixture và repository.
- Che hoặc loại bỏ dữ liệu cá nhân khỏi log, ảnh chụp, file HAR và báo cáo.
- Áp dụng quyền tối thiểu cho tài khoản kiểm thử.
- Phân tách môi trường kiểm thử với môi trường sản xuất.
- Hạn chế kết nối ra hệ thống thật và ngăn test tạo giao dịch thật ngoài phạm vi.
- Quy định thời hạn lưu và quy trình xóa dữ liệu.
- Ghi lại nguồn dữ liệu, mục đích, phê duyệt và biện pháp bảo vệ nếu dùng dữ liệu đã xử lý từ sản xuất.

Một tập dữ liệu giả vẫn có thể chứa thông tin nhạy cảm nếu được tạo từ dữ liệu thật mà chưa loại bỏ khả năng nhận diện. Cần đánh giá dữ liệu theo chính sách quyền riêng tư và bảo mật của tổ chức, không chỉ dựa vào nhãn “test data”.

## 10. Ví dụ thực tế

### Ví dụ A: Kiểm tra giới hạn số tiền và làm tròn

Một API nhận số tiền từ 0,01 đến 1.000.000,00 theo đơn vị tiền tệ đã công bố. Nhóm tạo dữ liệu:

| Trường hợp | Giá trị minh họa | Mục tiêu |
|---|---:|---|
| Dưới mức tối thiểu | 0,00 | Xác nhận từ chối |
| Tại mức tối thiểu | 0,01 | Xác nhận chấp nhận |
| Ngay trên tối thiểu | 0,02 | Kiểm tra biên |
| Giá trị thông thường | 125,50 | Xác nhận tính toán |
| Có nhiều chữ số thập phân | 10,005 | Xác nhận quy tắc làm tròn/validation |
| Tại mức tối đa | 1.000.000,00 | Xác nhận chấp nhận |
| Trên mức tối đa | 1.000.000,01 | Xác nhận từ chối |
| Giá trị âm | -1,00 | Xác nhận từ chối |
| Giá trị vượt kiểu lưu trữ | Một số có nhiều chữ số hơn cột cho phép | Xác nhận lỗi có kiểm soát, không ghi dữ liệu sai |

Ngoài response, nhóm đối chiếu số tiền lưu trong database, số tiền gửi sang provider và số tiền hiển thị. Nếu các hệ thống dùng đơn vị hoặc quy tắc làm tròn khác nhau, cần kiểm tra chuyển đổi tại từng ranh giới.

### Ví dụ B: Kiểm tra dữ liệu ngày giờ

Một chương trình khuyến mãi có hiệu lực từ 00:00 ngày bắt đầu đến trước 00:00 ngày kết thúc theo múi giờ Việt Nam. Nhóm tạo các thời điểm ngay trước, đúng tại và ngay sau hai mốc; ngày cuối tháng; ngày 29 tháng 2; timestamp UTC tương ứng và timestamp thiếu offset.

Expected result phải xác định rõ thời điểm được tính theo UTC hay giờ địa phương, và biên kết thúc là inclusive hay exclusive. Dùng clock cố định để kết quả không phụ thuộc thời gian chạy thực tế.

### Ví dụ C: Dữ liệu khối lượng lớn cho lịch sử giao dịch

Một dịch vụ truy vấn lịch sử giao dịch cần hỗ trợ khách hàng có từ vài giao dịch đến hàng triệu giao dịch. Nhóm tạo dữ liệu tổng hợp với:

- Nhiều khách hàng có số lượng giao dịch khác nhau.
- Một nhóm nhỏ khách hàng có lịch sử rất lớn để kiểm tra hot key.
- Trạng thái hoàn tất, chờ, hủy và hoàn tiền.
- Timestamp trải dài nhiều tháng/năm.
- Kích thước metadata và mô tả giao dịch đa dạng.
- Các giao dịch phân bố theo giờ cao điểm và ngày thường/cuối tuần.

Nhóm đo thời gian truy vấn theo phân vị, thông lượng, tài nguyên database, kích thước index và thời gian tạo trang cuối. Kết quả được so sánh với mục tiêu đã thống nhất. Dữ liệu không chỉ được nhân bản từ một khách hàng duy nhất vì cách đó không mô phỏng được phân bố truy vấn thực tế.

### Ví dụ D: Kiểm tra tồn kho khi nhiều người mua đồng thời

Kho còn một sản phẩm. Nhóm tạo nhiều yêu cầu đặt hàng đồng thời từ các tài khoản riêng, tất cả cùng mua đơn vị cuối cùng. Sau khi chạy, xác nhận chỉ số đơn hàng được chấp nhận phù hợp với quy tắc, tồn kho không âm và không có đơn thành công vượt số lượng khả dụng.

Lưu seed, số worker, thời điểm bắt đầu, mức đồng thời và kết quả từng request. Nếu hệ thống dùng hàng đợi hoặc khóa, thu thập trace và log để phân tích thứ tự xử lý. Chạy lại trong môi trường cô lập để tránh ảnh hưởng đến dữ liệu của nhóm khác.

### Ví dụ E: Dữ liệu lỗi trong quá trình nhập file

Một chức năng nhập CSV nhận danh sách khách hàng. Tạo file có header thiếu, dòng rỗng, mã định danh trùng, ngày sai định dạng, ký tự Unicode, trường quá dài và một số dòng hợp lệ xen kẽ dòng lỗi. Xác nhận hệ thống báo lỗi theo dòng, không nhập sai dữ liệu và tuân thủ chính sách xử lý một phần hay toàn bộ file.

Nếu hệ thống cho phép nhập một phần, cần xác định rõ quy tắc transaction: dòng hợp lệ được lưu hay toàn bộ file bị rollback. Kiểm tra báo cáo lỗi không làm lộ dữ liệu nhạy cảm và có thể liên kết với dòng nguồn.

## 11. Mẫu đặc tả tập dữ liệu kiểm thử

Có thể dùng mẫu sau để mô tả một tập dữ liệu trước khi tạo:

~~~yaml
dataset:
  id: DATA-ORDERS-BOUNDARY-01
  purpose: "Kiểm tra giới hạn số lượng và tổng tiền của đơn hàng"
  owner: "Order service test owner"
  version: 1

source:
  type: synthetic
  generator: "order-data-generator"
  generator_version: "1.2.0"
  seed: 41027

scope:
  entities:
    - customer
    - product
    - order
    - order_item
  record_profile:
    customers: 100
    products: 40
    orders: 5000
    order_items: 18000

partitions:
  - name: "valid-normal"
    description: "Đơn hàng hợp lệ thông thường"
  - name: "boundary-min-max"
    description: "Số lượng và tổng tiền tại các giới hạn"
  - name: "invalid-reference"
    description: "Mã sản phẩm hoặc khách hàng không tồn tại"
  - name: "duplicate-and-concurrent"
    description: "Yêu cầu lặp và cập nhật đồng thời"

constraints:
  - "Mọi order_item hợp lệ tham chiếu đến order và product tồn tại"
  - "Dữ liệu tiền tệ dùng decimal theo quy tắc nghiệp vụ"
  - "Không sử dụng dữ liệu cá nhân thật"

cleanup:
  namespace: "test-run-specific"
  policy: "Xóa sau khi hoàn tất; giữ artifact đã làm sạch"
~~~

Mẫu này minh họa cách mô tả nguồn, phiên bản generator, seed, quy mô, phân vùng và ràng buộc. Tập dữ liệu thực tế cần bổ sung định nghĩa trường, phân bố, quan hệ, expected result và cách xác minh sau khi nạp.

## 12. Mẫu kế hoạch dữ liệu cho kiểm thử khối lượng lớn

Một kế hoạch volume/load test nên xác định các thông số sau:

| Trường | Nội dung cần xác định |
|---|---|
| Mục tiêu | Đánh giá volume, load, stress, spike, soak hay scalability |
| Môi trường | Phiên bản, cấu hình, topology, tài nguyên và khác biệt với sản xuất |
| Quy mô dữ liệu | Số bản ghi, dung lượng, số quan hệ và thời gian tích lũy |
| Phân bố | Số lượng theo tenant, trạng thái, thời gian, kích thước và tần suất truy cập |
| Mô hình tải | Request/giây, đồng thời, tỷ lệ đọc/ghi, spike và thời lượng |
| Trạng thái cache | Nóng, lạnh hoặc hỗn hợp; cách chuẩn bị và xác minh |
| Tiêu chí đạt | p95/p99, thông lượng, tỷ lệ lỗi, tài nguyên, tính đúng đắn dữ liệu |
| Bằng chứng | Script, seed, log, metric, trace, kết quả đối soát và thời điểm chạy |
| An toàn | Giới hạn tải, tài khoản, mạng, dữ liệu và điều kiện dừng |
| Cleanup | Cách dừng tải, xóa dữ liệu, giải phóng tài nguyên và lưu artifact |

Tiêu chí đạt cần được thống nhất trước khi chạy. Ví dụ, yêu cầu p95 dưới một ngưỡng chỉ có ý nghĩa khi biết số mẫu, mô hình tải, thời gian đo, cấu hình và tỷ lệ lỗi. Không so sánh hai lần chạy nếu dữ liệu, cache hoặc tài nguyên khác nhau đáng kể mà không giải thích.

## 13. Kiểm tra tính đúng đắn của tập dữ liệu

Trước khi dùng dữ liệu để kết luận về sản phẩm, cần xác nhận chính dữ liệu đã được tạo đúng:

- Tổng số bản ghi và số lượng theo từng phân vùng đúng cấu hình.
- Khóa chính duy nhất và khóa ngoại hợp lệ ở các phân vùng được kỳ vọng hợp lệ.
- Tỷ lệ trạng thái, giá trị thiếu và kích thước trường đúng phân bố thiết kế.
- Timestamp, múi giờ và thứ tự sự kiện đúng quy tắc.
- Các trường hợp lỗi chỉ vi phạm đúng điều kiện dự kiến.
- Dữ liệu không chứa secret hoặc thông tin cá nhân ngoài phạm vi.
- Generator, seed, phiên bản và cấu hình được lưu để tái tạo.
- Dữ liệu sau nạp được đối chiếu với dữ liệu nguồn hoặc thống kê kỳ vọng.

Một generator sai có thể tạo ra kết quả kiểm thử sai lệch. Ví dụ, nếu generator vô tình tạo mọi đơn hàng với một khách hàng, truy vấn và index sẽ có phân bố khác thực tế; nếu khóa ngoại bị lỗi, test có thể thất bại do dữ liệu chuẩn bị chứ không phải do sản phẩm.

Nên có các kiểm tra sanity độc lập trước khi chạy workload chính. Với dữ liệu lớn, dùng thống kê, checksum, đếm bản ghi và kiểm tra mẫu có chọn lọc để xác nhận chất lượng mà không phải đọc thủ công toàn bộ tập.

## 14. Đọc kết quả và điều tra lỗi liên quan đến dữ liệu

Khi kiểm thử thất bại, trước khi kết luận sản phẩm có lỗi, hãy kiểm tra:

1. Dữ liệu đầu vào có đúng cấu hình và seed không?
2. Trạng thái ban đầu có được tạo và xác minh đúng không?
3. Test run có dùng namespace riêng không?
4. Có test khác hoặc tiến trình nền thay đổi dữ liệu không?
5. Generator hoặc migration có thay đổi giữa các lần chạy không?
6. Có khác biệt kiểu dữ liệu, collation, timezone hoặc phiên bản database không?
7. Lỗi có tái hiện khi chạy trên cùng dữ liệu trong môi trường cô lập không?

Nếu lỗi chỉ xuất hiện với một seed, lưu seed và dữ liệu tối thiểu tái hiện. Nếu lỗi chỉ xuất hiện ở quy mô lớn, tìm ngưỡng kích hoạt, phân bố có liên quan, tài nguyên và thời gian tích lũy. Nếu lỗi liên quan đến đồng thời, lưu lịch thực thi hoặc trace đủ để phân tích thứ tự.

Không xóa dữ liệu thất bại trước khi thu thập bằng chứng cần thiết. Tuy nhiên, việc giữ lại phải theo chính sách bảo mật và thời hạn lưu trữ; có thể tạo bản sao tối thiểu đã làm sạch để điều tra.

## 15. Những sai lầm thường gặp

- **Chỉ dùng dữ liệu hợp lệ thông thường:** bỏ sót ranh giới, lỗi và trạng thái bất thường.
- **Chọn giá trị biên không có căn cứ:** không dựa trên giới hạn thực tế của yêu cầu hoặc kiểu lưu trữ.
- **Nhầm thiếu trường với null hoặc rỗng:** không kiểm tra đúng ngữ nghĩa request.
- **Chỉ kiểm tra từng trường riêng lẻ:** bỏ qua quy tắc và ràng buộc giữa nhiều trường.
- **Nhân bản một bản ghi để tạo dữ liệu lớn:** không mô phỏng phân bố, quan hệ và mức độ truy cập thực tế.
- **Không lưu seed hoặc phiên bản generator:** lỗi không thể tái lập sau khi generator thay đổi.
- **Dùng dữ liệu sản xuất tùy tiện:** tạo rủi ro quyền riêng tư, bảo mật và tuân thủ.
- **Không cô lập dữ liệu giữa test:** chạy song song gây xung đột hoặc kết quả phụ thuộc thứ tự.
- **Không kiểm tra dữ liệu sau khi nạp:** lỗi generator bị nhầm thành lỗi sản phẩm.
- **Chỉ đo thời gian trung bình:** bỏ qua độ trễ ở phần đuôi, tỷ lệ lỗi và tài nguyên.
- **Không xác định trạng thái cache:** kết quả hiệu năng giữa các lần chạy không thể so sánh.
- **Không dọn dữ liệu và tài nguyên:** gây rò rỉ, tăng chi phí và ảnh hưởng lần chạy sau.
- **Retry thao tác có tác dụng phụ mà không kiểm tra idempotency:** có thể tạo giao dịch hoặc dữ liệu trùng.
- **Không ghi expected result cho dữ liệu lỗi:** không biết hệ thống từ chối, bỏ qua hay xử lý một phần theo đúng yêu cầu.

## 16. Checklist thiết kế dữ liệu kiểm thử

### Trước khi tạo dữ liệu

- [ ] Mục tiêu kiểm thử và rủi ro cần xác nhận đã rõ.
- [ ] Quy tắc nghiệp vụ, kiểu dữ liệu, giới hạn và quan hệ đã được xác định.
- [ ] Các phân vùng hợp lệ, không hợp lệ và bất thường đã được liệt kê.
- [ ] Giá trị biên được chọn ở cả hai phía của giới hạn.
- [ ] Các trường hợp null, thiếu, rỗng và sai kiểu được phân biệt.
- [ ] Tổ hợp trường và trạng thái quan trọng được xem xét.
- [ ] Quy mô, phân bố và mô hình tải có căn cứ.
- [ ] Nguồn dữ liệu, quyền riêng tư và biện pháp bảo vệ được phê duyệt.

### Khi tạo và chuẩn bị dữ liệu

- [ ] Dữ liệu có seed, phiên bản generator hoặc fixture được quản lý.
- [ ] Quan hệ và bất biến dữ liệu hợp lệ được duy trì.
- [ ] Dữ liệu lỗi chỉ vi phạm điều kiện dự kiến.
- [ ] Dữ liệu lớn có phân bố và kích thước đại diện.
- [ ] Test run có namespace hoặc cơ chế cô lập.
- [ ] Script tạo dữ liệu có hành vi rõ khi chạy lại.
- [ ] Secret và dữ liệu cá nhân được bảo vệ.
- [ ] Dữ liệu sau nạp được kiểm tra số lượng, quan hệ và thống kê.

### Khi thực hiện và kết thúc

- [ ] Phiên bản, môi trường, cấu hình, seed và trạng thái cache được ghi lại.
- [ ] Expected result và tiêu chí đạt được xác định trước.
- [ ] Kết quả bao gồm tính đúng đắn, lỗi, độ trễ và tài nguyên khi phù hợp.
- [ ] Lỗi được liên kết với dữ liệu và lần chạy cụ thể.
- [ ] Bằng chứng được làm sạch và lưu đúng nơi.
- [ ] Dữ liệu, queue, file và tài nguyên tạm được cleanup theo chính sách.
- [ ] Tập dữ liệu cần giữ để điều tra có chủ sở hữu và thời hạn.

## Kết luận

Thiết kế dữ liệu cho trường hợp biên, lỗi và khối lượng lớn cần dựa trên quy tắc nghiệp vụ, rủi ro và đặc điểm vận hành. Phân vùng tương đương cùng phân tích giá trị biên giúp chọn đầu vào có khả năng phát hiện lỗi; dữ liệu lỗi và trạng thái bất thường kiểm tra khả năng từ chối, phục hồi và bảo vệ bất biến; dữ liệu khối lượng lớn cần phản ánh quy mô, phân bố, mức đồng thời và thời gian tích lũy. Khi dữ liệu có nguồn gốc, seed, phiên bản, cô lập, kiểm tra chất lượng và cleanup rõ ràng, kết quả kiểm thử dễ tái lập, dễ điều tra và có giá trị hơn cho quyết định chất lượng.
