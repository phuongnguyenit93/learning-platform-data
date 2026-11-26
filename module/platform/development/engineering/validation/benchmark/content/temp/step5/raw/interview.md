Bạn sẽ xác định mục tiêu đo hiệu năng và tiêu chí chấp nhận trước khi thiết kế benchmark cho một thành phần Java như thế nào?
Bạn sẽ chọn workload đại diện cho hành vi người dùng thực tế dựa trên phân bố loại yêu cầu và kích thước dữ liệu ra sao?
Bạn sẽ phân biệt microbenchmark, benchmark thành phần và kiểm thử tải toàn hệ thống theo câu hỏi cần trả lời như thế nào?
Bạn sẽ quyết định đo độ trễ, thông lượng, mức dùng CPU hay bộ nhớ dựa trên đặc điểm hệ thống như thế nào?
Bạn sẽ giải thích ý nghĩa của p50, p95, p99 và độ trễ tối đa khi đánh giá trải nghiệm người dùng ra sao?
Bạn sẽ trình bày phân bố độ trễ bằng biểu đồ hoặc histogram để tránh kết luận sai từ giá trị trung bình như thế nào?
Bạn sẽ phân biệt thông lượng xử lý với tốc độ gửi yêu cầu và nhận diện hệ thống đang quá tải ra sao?
Bạn sẽ xác định ngưỡng chấp nhận hiệu năng dựa trên SLO và giới hạn tài nguyên như thế nào?
Bạn sẽ mô tả đầy đủ phiên bản mã, cấu hình JVM, phần cứng và dữ liệu thử nghiệm để người khác tái lập phép đo ra sao?
Bạn sẽ kiểm soát khác biệt về hệ điều hành, kiến trúc CPU và môi trường ảo hóa khi so sánh hai kết quả đo như thế nào?
Bạn sẽ giải thích vì sao một JVM mới khởi động có hành vi hiệu năng khác với JVM đã hoạt động ổn định ra sao?
Bạn sẽ quyết định thời lượng warmup và dấu hiệu hệ thống đã ổn định trước khi bắt đầu lấy mẫu như thế nào?
Bạn sẽ dùng JMH để tránh các sai lệch thường gặp khi tự đo thời gian bằng System.nanoTime như thế nào?
Bạn sẽ lựa chọn chế độ đo của JMH phù hợp khi cần so sánh thời gian mỗi thao tác và thông lượng như thế nào?
Bạn sẽ cấu hình fork, iteration và số luồng JMH để phân biệt ảnh hưởng của tiến trình JVM và độ biến thiên như thế nào?
Bạn sẽ tổ chức trạng thái dùng chung và trạng thái riêng của từng luồng trong JMH để mô phỏng đúng mức tranh chấp ra sao?
Bạn sẽ ngăn JIT loại bỏ phép tính không dùng tới trong một microbenchmark bằng cách nào?
Bạn sẽ kiểm tra nguy cơ constant folding và các tối ưu hóa của trình biên dịch khiến phép đo không còn đại diện ra sao?
Bạn sẽ thiết kế dữ liệu đầu vào thay đổi giữa các lượt đo mà không để chi phí chuẩn bị lẫn vào thao tác đang đo như thế nào?
Bạn sẽ phân biệt chi phí cấp phát đối tượng với chi phí của thuật toán chính trong kết quả benchmark ra sao?
Bạn sẽ nhận diện khi nào garbage collection hoặc JIT compilation làm xuất hiện các giá trị ngoại lệ trong phép đo như thế nào?
Bạn sẽ đo số lần thu gom rác và thời gian pause để giải thích biến động độ trễ của ứng dụng Java ra sao?
Bạn sẽ lựa chọn kích thước dữ liệu để phát hiện sự chuyển đổi từ xử lý trong cache sang truy cập bộ nhớ hoặc đĩa như thế nào?
Bạn sẽ kiểm soát CPU frequency scaling, thermal throttling và tiến trình nền khi đo trên máy dùng chung ra sao?
Bạn sẽ đánh giá khi nào cần cố định CPU affinity hoặc tài nguyên container để tăng tính lặp lại của phép đo như thế nào?
Bạn sẽ giải thích vì sao kết quả đo trên máy lập trình viên không thể suy rộng trực tiếp sang môi trường production ra sao?
Bạn sẽ thiết kế tập dữ liệu vừa đại diện tình huống phổ biến vừa chứa các trường hợp đầu vào xấu nhất như thế nào?
Bạn sẽ lựa chọn mức concurrency và mô hình tăng tải để tìm điểm bão hòa của một dịch vụ ra sao?
Bạn sẽ phân biệt mô hình phát tải theo số người dùng đồng thời và theo tốc độ yêu cầu đến như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của think time, kết nối lại và giữ kết nối đến kết quả kiểm thử tải ra sao?
Bạn sẽ nhận diện coordinated omission khi công cụ phát tải bỏ qua các yêu cầu đến trong lúc hệ thống chậm như thế nào?
Bạn sẽ xác định độ trễ phát sinh tại client, mạng, hàng đợi và server trong một bài kiểm thử phân tán ra sao?
Bạn sẽ phối hợp metric, trace và profiler để tìm nút thắt sau khi benchmark phát hiện suy giảm như thế nào?
Bạn sẽ kiểm tra độ trễ cold cache và warm cache để hiểu tác động của bộ nhớ đệm đến kết quả đo ra sao?
Bạn sẽ phân biệt tác động của giới hạn kết nối, connection pool và database query lên thông lượng như thế nào?
Bạn sẽ thiết lập phép đo đọc ghi file hoặc cơ sở dữ liệu để tránh sai lệch do OS page cache như thế nào?
Bạn sẽ cân đối độ dài từng lượt chạy và số lượt lặp để thu được kết quả ổn định mà không kéo dài thời gian đo quá mức ra sao?
Bạn sẽ đánh giá độ biến thiên giữa các lần chạy và quyết định khi nào cần thêm mẫu như thế nào?
Bạn sẽ diễn giải khoảng tin cậy và độ lớn hiệu ứng khi so sánh phiên bản mới với baseline ra sao?
Bạn sẽ phân biệt cải thiện có ý nghĩa thống kê với cải thiện đủ lớn để mang lại giá trị vận hành như thế nào?
Bạn sẽ tránh kết luận quá sớm khi đồng thời so sánh nhiều benchmark hoặc nhiều cấu hình như thế nào?
Bạn sẽ xây dựng baseline ổn định và quy tắc chấp nhận để phát hiện hồi quy hiệu năng trong CI ra sao?
Bạn sẽ phân biệt sự thay đổi do mã nguồn với sự thay đổi do môi trường đo khi CI báo hiệu năng giảm như thế nào?
Bạn sẽ lưu trữ metadata và kết quả thô của mỗi lần benchmark để phục vụ kiểm toán và so sánh lịch sử ra sao?
Bạn sẽ mô tả kết quả benchmark sao cho người đọc thấy rõ điều kiện đo, giới hạn và mức bất định như thế nào?
Bạn sẽ xác định những trường hợp cần kiểm tra hiệu năng theo thời gian dài để phát hiện rò rỉ bộ nhớ hoặc suy giảm dần ra sao?
Bạn sẽ dùng kiểm thử tải tăng đột ngột để đánh giá khả năng phục hồi và hàng đợi của dịch vụ như thế nào?
Bạn sẽ đánh giá đánh đổi giữa giảm thời gian phản hồi và tăng mức dùng CPU hoặc bộ nhớ trong một thay đổi tối ưu hóa ra sao?
Bạn sẽ điều tra vì sao microbenchmark của một hàm nhanh hơn nhưng độ trễ p99 toàn dịch vụ lại xấu đi như thế nào?
Bạn sẽ ra quyết định giữ hay hoàn nguyên một tối ưu hóa khi kết quả giữa các lần đo trái ngược nhau như thế nào?
