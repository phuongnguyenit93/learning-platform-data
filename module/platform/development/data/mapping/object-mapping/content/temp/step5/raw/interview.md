Bạn sẽ xác định trách nhiệm của domain model, persistence entity và API DTO trong một ứng dụng Java như thế nào?
Bạn sẽ quyết định tại ranh giới kiến trúc nào cần chuyển đổi đối tượng để tránh làm lộ mô hình nội bộ ra sao?
Bạn sẽ thiết kế hợp đồng ánh xạ khi cùng một entity được dùng cho nhiều màn hình và mục đích API khác nhau như thế nào?
Bạn sẽ lựa chọn ánh xạ thủ công hay dùng thư viện dựa trên độ phức tạp, hiệu năng và khả năng bảo trì ra sao?
Bạn sẽ so sánh cách MapStruct sinh mã ở thời điểm biên dịch với cơ chế ánh xạ động của ModelMapper như thế nào?
Bạn sẽ đánh giá những rủi ro khi quy tắc ánh xạ dựa vào tên trường tự động trong một dự án lớn ra sao?
Bạn sẽ tổ chức các mapper theo tính năng hay theo cặp kiểu dữ liệu để tránh phụ thuộc vòng như thế nào?
Bạn sẽ lựa chọn cách chia sẻ quy tắc chuyển đổi dùng chung mà không khiến các mapper phụ thuộc quá chặt ra sao?
Bạn sẽ phát hiện các trường chưa được ánh xạ sau khi một DTO hoặc entity thay đổi như thế nào?
Bạn sẽ xây dựng quy ước đặt tên và ghi tài liệu cho những phép ánh xạ có ý nghĩa nghiệp vụ đặc biệt ra sao?
Bạn sẽ chuyển đổi giữa kiểu số nguyên, số thập phân và kiểu chuỗi mà không đánh mất độ chính xác như thế nào?
Bạn sẽ giải quyết khác biệt giữa kiểu ngày giờ có múi giờ và không có múi giờ khi ánh xạ như thế nào?
Bạn sẽ ánh xạ enum giữa hai lớp có tập giá trị khác nhau và xử lý giá trị chưa biết ra sao?
Bạn sẽ phân biệt giá trị null, giá trị mặc định và giá trị bị bỏ trống trong quá trình chuyển đổi như thế nào?
Bạn sẽ quyết định khi nào giữ nguyên null, khi nào dùng giá trị mặc định và khi nào báo lỗi trong một mapper ra sao?
Bạn sẽ xử lý các đối tượng lồng nhau mà một hoặc nhiều cấp trung gian có thể là null như thế nào?
Bạn sẽ chuyển đổi một cấu trúc entity lồng nhau thành DTO phẳng và kiểm soát việc mất thông tin ra sao?
Bạn sẽ ánh xạ collection có thứ tự, phần tử trùng và phần tử null theo hợp đồng dữ liệu như thế nào?
Bạn sẽ bảo đảm phép ánh xạ collection không vô tình sửa đổi danh sách nguồn hoặc làm lộ trạng thái có thể thay đổi ra sao?
Bạn sẽ xử lý mối quan hệ hai chiều giữa các entity khi chuyển sang DTO để tránh đệ quy vô hạn như thế nào?
Bạn sẽ lựa chọn ánh xạ tham chiếu bằng ID hay nhúng đối tượng con đầy đủ dựa trên nhu cầu API như thế nào?
Bạn sẽ đánh giá tác động của lazy loading và proxy JPA khi mapper truy cập các quan hệ của entity ra sao?
Bạn sẽ tránh tình trạng mapper kích hoạt hàng loạt truy vấn N+1 khi trả về danh sách DTO như thế nào?
Bạn sẽ thiết kế phép ánh xạ tạo mới entity mà không cho phép client tự đặt ID, phiên bản và trường kiểm toán ra sao?
Bạn sẽ tách DTO tạo mới, DTO cập nhật và DTO phản hồi để phản ánh các quyền thao tác khác nhau như thế nào?
Bạn sẽ bảo vệ trường nhạy cảm như mật khẩu, token và thông tin riêng tư khi ánh xạ sang phản hồi API ra sao?
Bạn sẽ ngăn lỗi mass assignment khi request chứa những trường trùng tên với thuộc tính nội bộ của entity như thế nào?
Bạn sẽ áp dụng quyền theo vai trò khi cùng một entity có nhiều tập trường được phép hiển thị như thế nào?
Bạn sẽ thiết kế phép ánh xạ theo ngữ cảnh tenant để không đưa dữ liệu của tenant khác vào response ra sao?
Bạn sẽ giải thích khác biệt giữa cập nhật toàn bộ đối tượng và cập nhật một phần theo ngữ nghĩa API như thế nào?
Bạn sẽ phân biệt trường không được gửi, trường gửi null và trường gửi giá trị mới trong một yêu cầu PATCH ra sao?
Bạn sẽ lựa chọn chiến lược cập nhật collection để tránh mất dữ liệu con khi chỉ có một phần danh sách thay đổi như thế nào?
Bạn sẽ bảo vệ các bất biến nghiệp vụ khi mapper cập nhật trạng thái của một aggregate đang tồn tại ra sao?
Bạn sẽ kết hợp ánh xạ cập nhật với cơ chế dirty checking của JPA để tránh tạo bản ghi mới ngoài ý muốn như thế nào?
Bạn sẽ xử lý trường hợp hai yêu cầu cùng cập nhật một entity và phiên bản dữ liệu đã thay đổi ra sao?
Bạn sẽ ánh xạ vào đối tượng bất biến hoặc Java record khi không thể dùng setter như thế nào?
Bạn sẽ áp dụng constructor hoặc builder để bảo đảm đối tượng đích luôn được khởi tạo hợp lệ ra sao?
Bạn sẽ ánh xạ đối tượng đa hình có nhiều subtype mà vẫn kiểm soát kiểu được chấp nhận như thế nào?
Bạn sẽ tổ chức các hàm chuyển đổi tùy biến cho kiểu giá trị chuyên biệt mà không lặp lại logic giữa nhiều mapper như thế nào?
Bạn sẽ đánh giá tác động của việc ánh xạ một đối tượng sâu thành nhiều DTO lên thời gian chạy và bộ nhớ ra sao?
Bạn sẽ xác định trường hợp nào cần projection trực tiếp từ truy vấn thay vì nạp entity rồi ánh xạ như thế nào?
Bạn sẽ tổ chức kiểm thử đơn vị để xác nhận từng trường, kiểu dữ liệu và giá trị null được chuyển đúng ra sao?
Bạn sẽ viết kiểm thử cho các đối tượng lồng nhau, collection rỗng và quan hệ vòng để phát hiện lỗi mapping như thế nào?
Bạn sẽ kiểm tra những trường hợp chuyển đổi làm tròn số, đổi múi giờ hoặc mất giá trị enum như thế nào?
Bạn sẽ xác định khi nào kiểm thử round-trip giữa hai mô hình là hợp lệ và khi nào phép ánh xạ có chủ ý làm mất thông tin ra sao?
Bạn sẽ xử lý lỗi ánh xạ kèm thông tin đường dẫn trường để hỗ trợ điều tra nhưng không làm lộ dữ liệu nhạy cảm như thế nào?
Bạn sẽ quản lý thay đổi tên hoặc ý nghĩa trường DTO khi API phải tương thích với client cũ ra sao?
Bạn sẽ đánh giá một thay đổi mapper gây ảnh hưởng đến dữ liệu được lưu, phản hồi API và các dịch vụ phụ thuộc như thế nào?
Bạn sẽ xây dựng tiêu chí code review để phát hiện mapper tạo phụ thuộc kiến trúc hoặc bỏ sót kiểm tra quyền ra sao?
Bạn sẽ xử lý sự cố một bản cập nhật thư viện mapping khiến trường nhạy cảm bất ngờ xuất hiện trong response như thế nào?
