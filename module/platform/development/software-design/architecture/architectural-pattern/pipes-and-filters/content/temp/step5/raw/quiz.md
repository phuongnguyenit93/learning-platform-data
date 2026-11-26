Trong Pipes and Filters, trách nhiệm cốt lõi của một filter là gì?
A. Điều khiển toàn bộ trạng thái của hệ thống
B. Tự quyết định thứ tự chạy của mọi filter khác
C. Biến đổi input thành output theo một hợp đồng
D. Khởi tạo riêng một database cho mỗi bản ghi
Đáp án đúng: C

Pipe nối các filter liên tiếp chủ yếu để thực hiện điều gì?
A. Tự sửa schema khi hợp đồng hai bước khác nhau
B. Bảo đảm mọi thao tác đều thành transaction
C. Ghi đè quy tắc xử lý nghiệp vụ của các filter
D. Chuyển dữ liệu giữa hai bước nối tiếp
Đáp án đúng: D

Điểm lợi khi tách parse, validate và enrich thành các filter là gì?
A. Không còn chi phí chuyển dữ liệu giữa bước
B. Mọi lỗi đầu vào đều được sửa tự động
C. Dễ kiểm thử và thay thế từng bước độc lập
D. Mọi bước luôn chạy cùng một thread cố định
Đáp án đúng: C

Khi output của filter A không hợp input của filter B, nên làm gì?
A. Kiểm tra contract và chuyển đổi rõ ràng
B. Ép kiểu không kiểm tra tại phần đầu filter B
C. Bỏ validation để đường ống tiếp tục chạy
D. Dùng biến global để chia sẻ dữ liệu thô
Đáp án đúng: A

Filter không giữ trạng thái dùng chung hỗ trợ khả năng nào?
A. Tự động loại bỏ mọi chi phí serialization
B. Dễ nhân bản worker cho bản ghi độc lập
C. Luôn loại trừ nhu cầu xử lý lỗi đầu vào
D. Tự bảo đảm mọi bản ghi có thứ tự toàn cục
Đáp án đúng: B

Nhiều worker của filter cùng sửa một biến đếm dùng chung có thể gây gì?
A. Race condition nếu cập nhật thiếu đồng bộ
B. Thứ tự pipe tự động được đảo lại khi ghi
C. Lỗi parse vì kiểu đầu vào không còn là JSON
D. Deadlock chắc chắn xảy ra ngay khi có hai worker
Đáp án đúng: A

Khi producer nhanh hơn consumer lâu dài, cơ chế nào kiểm soát bộ nhớ tốt?
A. Tăng vô hạn vùng đệm để không làm chậm producer
B. Tắt kiểm tra số bản ghi đang đợi ở từng bước
C. Sao chép toàn bộ thông điệp sang bộ nhớ tạm
D. Giới hạn queue để tạo áp lực ngược
Đáp án đúng: D

Hàng đợi bounded giữa hai filter đã đầy; hành vi nào thể hiện backpressure?
A. Producer tăng kích thước queue vô hạn
B. Producer chờ hoặc nhận tín hiệu giảm tốc
C. Pipeline đổi thứ tự các bước để né chờ
D. Consumer buộc hủy mọi record đang xử lý
Đáp án đúng: B

Một bản ghi không qua validation; thiết kế xử lý lỗi nào dễ kiểm soát?
A. Cho record đi tiếp như thể đã qua validation
B. Xóa im lặng bản ghi, không cần báo trạng thái
C. Thử lại không giới hạn dù đầu vào không đổi
D. Đưa record lỗi sang nhánh có kiểm soát
Đáp án đúng: D

Một filter ghi dữ liệu bị retry sau timeout; đặc tính nào của sink hữu ích?
A. Mỗi lần retry đều tạo một khóa bản ghi mới
B. Cho phép consumer bỏ qua mọi kết quả ghi
C. Dùng idempotency key để ngăn ghi trùng
D. Cố giữ transaction mở vô hạn khi gặp lỗi
Đáp án đúng: C

Muốn test một filter mà không chạy toàn pipeline, nên kiểm tra gì?
A. Đầu ra và lỗi từ những input đã kiểm soát
B. Chỉ thứ tự khởi động của các thread trong JVM
C. Chỉ tổng thời gian chạy của tất cả filter
D. Đủ số lượng class được tải khi ứng dụng chạy
Đáp án đúng: A

Vì sao đổi thứ tự hai filter có thể làm kết quả cuối khác đi?
A. Kết quả phụ thuộc thứ tự phép biến đổi
B. Filter phía sau sẽ bỏ qua mọi phép biến đổi trước
C. Pipe luôn tự bảo đảm hai hàm có tính giao hoán
D. Mọi filter luôn xử lý được record ở thứ tự bất kỳ
Đáp án đúng: A

Khi mở rộng một filter thành nhiều worker, cần đặc biệt xét điều gì?
A. Mọi worker đều phải dùng chung một biến mutable
B. Thứ tự theo khóa nếu luồng dữ liệu đòi hỏi
C. Mọi pipe phải chuyển thành một table quan hệ
D. Filter mới bắt buộc chứa toàn bộ workflow
Đáp án đúng: B

Khi chẩn đoán một record chậm trong pipeline, nên thu thập gì?
A. Chỉ số lượng class có tên kết thúc bằng Filter
B. Chỉ thời gian khởi động của tiến trình chính
C. Chỉ tốc độ CPU của máy phát sinh dữ liệu
D. Trace ID và thời gian xử lý theo từng bước
Đáp án đúng: D

Muốn tìm nút thắt throughput của pipeline, nên quan sát gì?
A. Chỉ độ dài tên file chứa code của từng bước
B. Chỉ tổng kích thước source code của các filter
C. Tốc độ xử lý và queue backlog theo từng filter
D. Chỉ số lượng interface mà từng filter triển khai
Đáp án đúng: C

Đánh đổi hiệu năng nào có thể xuất hiện khi chia quá nhiều filter?
A. Toàn bộ bước luôn được tối ưu chung như một hàm
B. Chi phí truyền, đệm và tuần tự hóa tăng
C. Chi phí kết nối giữa các bước giảm về bằng không
D. Không còn cần giám sát lưu lượng giữa các bước
Đáp án đúng: B
