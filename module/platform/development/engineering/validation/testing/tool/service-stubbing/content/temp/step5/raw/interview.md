Bạn sẽ giải thích mục đích của service stubbing và giới hạn của việc thay thế một dịch vụ phụ thuộc thật trong kiểm thử như thế nào?
Bạn sẽ phân biệt stub, mock và fake khi xác định mục tiêu kiểm thử tương tác giữa các dịch vụ ra sao?
Trong trường hợp nào bạn sẽ chọn WireMock hoặc MockServer thay vì gọi trực tiếp API của đối tác?
Bạn sẽ xác định những hành vi quan sát được nào của dịch vụ bên ngoài phải được mô phỏng để phép thử có ý nghĩa?
Bạn sẽ tổ chức hợp đồng request và response của dịch vụ phụ thuộc để tạo stub không lệch khỏi hành vi thực tế như thế nào?
Bạn sẽ xây dựng quy tắc ghép request dựa trên phương thức HTTP và đường dẫn mà không bắt nhầm endpoint khác ra sao?
Khi request chứa query parameter ở nhiều thứ tự, bạn sẽ thiết kế matcher sao cho ổn định như thế nào?
Bạn sẽ so sánh ghép chính xác giá trị header với ghép theo mẫu khi kiểm thử header xác thực hoặc phiên bản như thế nào?
Bạn sẽ lựa chọn cách kiểm tra cấu trúc JSON body thay vì so sánh nguyên chuỗi nhằm tránh phụ thuộc vào thứ tự trường ra sao?
Khi chỉ một vài trường trong JSON quyết định hành vi, bạn sẽ thiết kế matcher để không ràng buộc các trường không cần thiết như thế nào?
Bạn sẽ mô phỏng nhiều response khác nhau cho cùng một endpoint tùy theo dữ liệu request bằng cách nào?
Bạn sẽ xác định mức ưu tiên khi nhiều stub cùng khớp một request để tránh kết quả không xác định như thế nào?
Khi không có stub khớp request, bạn muốn phép thử thất bại theo cách nào để lộ ra tương tác chưa được mô tả?
Bạn sẽ thiết kế response với status code, header và body như thế nào để mô phỏng đúng nhánh xử lý lỗi của client?
Bạn sẽ chọn dữ liệu response đại diện cho trường hợp thành công, dữ liệu rỗng và thông tin bị thiếu dựa trên tiêu chí nào?
Bạn sẽ mô phỏng dịch vụ trả lỗi xác thực hoặc phân quyền để kiểm tra logic ứng dụng phía client như thế nào?
Khi một dịch vụ bị giới hạn tần suất, bạn sẽ giả lập phản hồi quá tải và thông tin yêu cầu thử lại ra sao?
Bạn sẽ mô phỏng thời gian phản hồi chậm để xác minh timeout của ứng dụng mà không làm suite kiểm thử kéo dài không cần thiết như thế nào?
Bạn sẽ thiết kế kịch bản kết nối bị ngắt hoặc response chưa hoàn chỉnh để đánh giá hành vi phục hồi của client ra sao?
Khi cần mô phỏng lỗi xảy ra ở lần gọi đầu tiên rồi thành công ở lần tiếp theo, bạn sẽ quản lý trạng thái kịch bản như thế nào?
Bạn sẽ kiểm thử chính sách retry của ứng dụng bằng cách cấu hình chuỗi phản hồi và giới hạn số lần gọi ra sao?
Bạn sẽ xác minh ứng dụng không thử lại một yêu cầu không an toàn sau lỗi bằng những bằng chứng tương tác nào?
Khi ứng dụng gọi nhiều dịch vụ liên tiếp, bạn sẽ tổ chức stub theo thứ tự sự kiện nào mà không tạo phụ thuộc thời gian mong manh?
Bạn sẽ kiểm tra chính xác số lần một endpoint được gọi và phân biệt một lần gọi hợp lệ với các lần gọi thừa ra sao?
Bạn sẽ xác minh nội dung request phát ra có chứa đúng ID liên kết, tham số và dữ liệu nghiệp vụ như thế nào?
Bạn sẽ xác định trường hợp nào cần kiểm tra rằng một API bên ngoài hoàn toàn không bị gọi?
Bạn sẽ đối chiếu nhật ký request nhận bởi stub với mong đợi của test để chẩn đoán lỗi ghép request ra sao?
Bạn sẽ thiết kế thông báo khi một matcher thất bại để lập trình viên nhìn thấy khác biệt cần sửa như thế nào?
Bạn sẽ đặt tiêu chí nào để không biến test tương tác thành bài thử quá phụ thuộc vào chi tiết triển khai?
Bạn sẽ quản lý dữ liệu stub dạng tệp riêng so với định nghĩa bằng mã để cân bằng khả năng đọc và bảo trì như thế nào?
Khi có nhiều kịch bản dùng chung một response, bạn sẽ tái sử dụng fixture mà không che giấu ý nghĩa từng bài kiểm thử ra sao?
Bạn sẽ cách ly trạng thái kịch bản và lịch sử request giữa các test để tránh ảnh hưởng theo thứ tự chạy như thế nào?
Khi bộ test được chạy song song, bạn sẽ phân bổ cổng mạng hoặc phiên stub độc lập để tránh xung đột ra sao?
Bạn sẽ chọn vòng đời khởi tạo và dừng máy chủ WireMock trong JUnit dựa trên phạm vi sử dụng của bài kiểm thử như thế nào?
Bạn sẽ giải thích cách MockServer quản lý expectation và cách dọn expectation sau mỗi kịch bản ra sao?
Bạn sẽ đánh giá khi nào dùng response templating để tạo dữ liệu động từ request và rủi ro làm stub trở nên khó dự đoán như thế nào?
Khi request chứa giá trị động như timestamp hoặc token, bạn sẽ thiết kế matcher không phụ thuộc vào giá trị ngẫu nhiên như thế nào?
Bạn sẽ giả lập phân trang với nhiều trang dữ liệu và điều kiện kết thúc để kiểm tra client như thế nào?
Bạn sẽ mô phỏng cùng một tài nguyên trả kết quả thay đổi sau thao tác ghi để kiểm tra workflow nhiều bước ra sao?
Khi hệ thống gửi webhook tới một bên nhận, bạn sẽ dựng stub phía nhận và xác minh callback như thế nào?
Bạn sẽ xử lý trường hợp dịch vụ phụ thuộc dùng HTTPS hoặc yêu cầu chứng chỉ để môi trường kiểm thử phản ánh đúng giao tiếp ra sao?
Bạn sẽ phân biệt giả lập giao thức HTTP hợp lệ với giả lập lỗi tầng mạng để chọn cơ chế stubbing phù hợp như thế nào?
Bạn sẽ xác minh định dạng dữ liệu lỗi của provider không làm hỏng cơ chế phân tích response của ứng dụng ra sao?
Bạn sẽ kiểm tra tính tương thích giữa stub và API thật khi provider thay đổi schema hoặc hành vi trả lỗi như thế nào?
Bạn sẽ quyết định khi nào cần kết hợp kiểm thử contract với service stubbing để tránh cảm giác an toàn giả ra sao?
Bạn sẽ đưa máy chủ stub vào Docker hoặc môi trường CI và kiểm soát địa chỉ kết nối của ứng dụng cần kiểm thử như thế nào?
Khi stub khởi động chậm trong CI, bạn sẽ thiết kế kiểm tra sẵn sàng và cơ chế chờ có giới hạn ra sao?
Bạn sẽ thu thập log và lịch sử tương tác của stub như thế nào để chẩn đoán bài kiểm thử thất bại trên CI?
Khi bài thử thành công với stub nhưng thất bại khi tích hợp dịch vụ thật, bạn sẽ xác định giả định mô phỏng sai ở đâu?
Bạn sẽ đánh giá bộ service stubbing theo độ bao phủ kịch bản lỗi, tính tái lập và chi phí bảo trì như thế nào?
