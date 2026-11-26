Một hàm Java tính phí vận chuyển đạt kết quả đúng với đơn thông thường, nhưng sau khi đổi ngưỡng miễn phí, đơn có tổng tiền đúng bằng ngưỡng bị thu phí sai; nhóm cần xây unit test phân biệt các trường hợp sát ranh giới.
Một bộ tính chiết khấu có các mức ưu đãi khác nhau theo loại khách hàng và giá trị đơn; bài kiểm thử hiện chỉ dùng một khách VIP nên không phát hiện nhánh kết hợp trạng thái khách hàng với mức tiền.
Một hàm chuẩn hóa số điện thoại bỏ ký tự khoảng trắng trong các ví dụ thông thường nhưng làm mất dấu cộng đầu số quốc tế; bộ test cần phản ánh hợp đồng dữ liệu hợp lệ thay vì chỉ kiểm tra một vài chuỗi quen thuộc.
Một phương thức kiểm tra mật khẩu nhận giá trị null, chuỗi rỗng và chuỗi Unicode có ký tự đặc biệt; nhóm đang phân vân cách thể hiện kết quả và ngoại lệ một cách nhất quán trong unit test.
Hàm tính lãi sử dụng số thực nhị phân để làm tròn đến hai chữ số thập phân; bài kiểm thử so sánh kết quả bằng độ lệch cho phép nên bỏ qua lỗi một xu trong hóa đơn.
Một tiện ích chuyển đổi ngày hết hạn phụ thuộc múi giờ mặc định của máy chạy; unit test đạt trên laptop nhưng thất bại ở CI khi ngày chuyển qua nửa đêm ở múi giờ khác.
Một dịch vụ phát mã khuyến mại dùng thời gian hệ thống và số ngẫu nhiên trực tiếp, khiến cùng bài test trả kết quả khác nhau mỗi lần chạy dù logic xét điều kiện cấp mã không đổi.
Một lớp Java mới có hơn mười nhánh xử lý trạng thái đơn hàng; đội tạo các ca kiểm thử trùng phần thiết lập và bỏ sót trạng thái hủy, nên muốn đánh giá cách dùng kiểm thử tham số hóa của JUnit Jupiter.
Hàm phân loại độ tuổi nhận giá trị từ người dùng; khi chạy các ví dụ hợp lệ, bộ test không phát hiện việc chấp nhận tuổi âm hoặc giá trị vượt miền nghiệp vụ, khiến nhóm cần xác định dữ liệu không hợp lệ và hành vi mong muốn.
Đội kiểm thử một bộ tính diện tích bằng nhiều ví dụ nhưng không nhận ra chương trình đã đổi nhầm chiều dài với chiều rộng trong một nhánh xử lý hình không vuông; họ cần kiểm tra mức độ đa dạng thực sự của dữ liệu test.
Một lớp chuyển số điểm sang mức đánh giá có kết quả đúng ở các mốc được chọn, nhưng một thay đổi toán tử so sánh ở mốc 80 vẫn được bộ test chấp nhận; nhóm phải xem lại chất lượng assertion và trường hợp biên.
Lớp xử lý thanh toán bắt ngoại lệ từ cổng bên ngoài rồi chuyển thành lỗi nghiệp vụ; unit test hiện chỉ xác nhận có ngoại lệ bất kỳ nên không phát hiện mã lỗi và nguyên nhân bị chuyển sai.
Một phương thức trả danh sách đơn đã lọc theo trạng thái; bài kiểm thử chỉ xác nhận danh sách không rỗng nên vẫn xanh khi hàm trả thừa đơn hàng không hợp lệ.
Trong bộ test dùng AssertJ, nhóm so sánh các tập kết quả bằng đúng thứ tự phần tử dù hợp đồng dịch vụ không yêu cầu thứ tự; sau lần refactor dùng tập hợp khác, nhiều ca thất bại dù kết quả nghiệp vụ vẫn đúng.
Một phương thức cập nhật số dư phải giữ nguyên dữ liệu đầu vào khi nghiệp vụ từ chối giao dịch; bộ test chỉ kiểm tra giá trị trả về và không phát hiện đối tượng được truyền vào đã bị sửa trước khi ném lỗi.
Một lớp Java xử lý danh sách đầu vào không được phép làm thay đổi collection của người gọi, nhưng test sử dụng danh sách mới và không so sánh trạng thái sau lời gọi; một refactor đã vô tình xóa phần tử gốc.
Một service tính giá phụ thuộc repository tra chính sách chiết khấu; nhóm dùng cơ sở dữ liệu thật trong unit test nên bài chạy chậm và thất bại khi dữ liệu môi trường thay đổi.
Một mock repository được cấu hình trả về cùng kết quả cho mọi mã sản phẩm; một bug khiến service dùng nhầm mã vẫn vượt qua unit test, do kết quả giả không phân biệt đầu vào của lời gọi.
Đội dùng Mockito xác nhận chính xác thứ tự và số lần gọi mọi phương thức repository, dù yêu cầu nghiệp vụ chỉ quan tâm tổng tiền; sau khi tối ưu bằng cache, test thất bại hàng loạt dù kết quả vẫn hợp lệ.
Một hàm xử lý đơn gọi dịch vụ thông báo chỉ khi giao dịch đã được chấp nhận; bài test hiện xác nhận giá trị trả về nhưng không nhận ra lời gọi thông báo vẫn xảy ra trong nhánh đơn bị từ chối.
Một nhóm dùng Mockito với cấu hình stub cho nhiều đường đi trong cùng fixture; các bài test lẻ đôi lúc báo stub không được sử dụng và lập trình viên muốn tắt kiểm tra nghiêm ngặt cho toàn bộ dự án.
Một lập trình viên dùng spy trên đối tượng chứa logic thật và vô tình kích hoạt truy vấn ngoài dự tính ngay trong bước thiết lập kiểm thử; bài unit test mất tính độc lập với môi trường.
Một bộ unit test đặt trạng thái dùng chung trong biến tĩnh và thay đổi nó trước mỗi phương thức; khi JUnit chạy song song, kết quả phụ thuộc vào test nào thiết lập giá trị cuối cùng.
Trong lớp kiểm thử JUnit Jupiter, một bài test sửa trực tiếp fixture chung được khởi tạo một lần; bài chạy sau nhận dữ liệu đã thay đổi và chỉ thất bại khi chạy cả lớp kiểm thử.
Một dịch vụ trả CompletableFuture xử lý đơn, nhưng unit test chỉ kiểm tra đối tượng future được tạo mà không quan sát kết quả khi tác vụ hoàn tất hoặc lỗi bên trong bị chuyển tiếp.
Một chức năng thử lại sau lỗi tạm thời sử dụng thời gian chờ thực và nhiều lần gọi mạng giả, khiến bài unit test mất vài phút và đôi lúc quá timeout trên runner CI.
Một bộ xử lý sự kiện bất đồng bộ có cơ chế hủy tác vụ, nhưng bài test kết thúc ngay sau khi phát tín hiệu hủy nên không phát hiện callback vẫn chạy và sửa trạng thái sau đó.
Một thuật toán phân phối lượt dùng chạy đúng với tập dữ liệu nhỏ nhưng sai khi cùng mã xuất hiện nhiều lần; nhóm cần xác định tính chất bất biến có thể kiểm tra qua nhiều đầu vào thay vì dựa vào một kết quả mẫu.
Dashboard báo line coverage gần 100% cho lớp tính thuế nhưng mutation testing cho thấy nhiều thay đổi phép so sánh và toán tử vẫn không làm bài nào thất bại; nhóm cần đánh giá hiệu lực bộ assertion.
Một đợt refactor chuyển hàm tính giá sang cấu trúc nhỏ hơn; nhiều unit test kiểm tra phương thức riêng qua phản chiếu bị hỏng dù kết quả công khai của lớp không đổi, khiến nhóm cần xem lại ranh giới kiểm thử hành vi.
Bộ unit test cho mã chuyển trạng thái đơn có một ca phụ thuộc thứ tự duyệt của HashMap; khi thay phiên bản JDK, kết quả kiểm tra bằng chuỗi cố định thất bại trên CI nhưng không phản ánh lỗi nghiệp vụ.
Một nhóm thêm nhiều unit test cho các getter, setter và constructor đơn giản để nâng coverage, trong khi logic hoàn tiền nhiều nhánh không có kiểm thử; trưởng nhóm cần đánh giá độ ưu tiên của ca test theo rủi ro và giá trị phát hiện lỗi.
