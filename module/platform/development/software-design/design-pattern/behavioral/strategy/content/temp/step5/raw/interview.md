Bạn sẽ nhận biết tình huống nào nên áp dụng Strategy thay vì duy trì nhiều nhánh if/else trong cùng một phương thức như thế nào?
Bạn sẽ phân biệt phần hành vi thay đổi với phần quy trình ổn định trước khi trích xuất một họ thuật toán ra sao?
Bạn sẽ mô tả trách nhiệm của Context, Strategy và các Concrete Strategy trong một thiết kế Java như thế nào?
Bạn sẽ xác định hợp đồng đầu vào, đầu ra và lỗi chung cho các Strategy dựa trên nhu cầu của Context ra sao?
Khi các thuật toán có tiền điều kiện khác nhau, bạn sẽ giữ một interface thống nhất mà không che giấu ràng buộc như thế nào?
Bạn sẽ thiết kế Context phụ thuộc vào interface thay vì trực tiếp khởi tạo từng thuật toán cụ thể ra sao?
Trong bài toán tính phí vận chuyển theo phương thức giao hàng, bạn sẽ nhận diện các Strategy và dữ liệu chung như thế nào?
Bạn sẽ xử lý một chiến lược chưa được hỗ trợ mà không để Context rơi vào hành vi mặc định sai như thế nào?
Bạn sẽ quyết định chọn Strategy tại thời điểm tạo Context hay tại thời điểm mỗi lần gọi dựa trên điều kiện nào?
Bạn sẽ thiết kế cơ chế thay đổi Strategy khi ứng dụng đang chạy mà không làm hỏng trạng thái đang xử lý ra sao?
Khi lựa chọn Strategy dựa trên cấu hình người dùng, bạn sẽ tách quy tắc chọn khỏi phần thực thi thuật toán như thế nào?
Bạn sẽ phân biệt bộ chọn Strategy với bản thân Strategy để tránh đưa một chuỗi if/else lớn sang lớp khác ra sao?
Bạn sẽ xây dựng một registry ánh xạ mã nghiệp vụ sang Strategy mà vẫn dễ kiểm soát cấu hình thiếu hoặc trùng như thế nào?
Khi các thuật toán dùng chung dữ liệu nhưng không dùng chung cách tính, bạn sẽ tổ chức đối tượng tham số thế nào để tránh quá nhiều đối số?
Bạn sẽ cân nhắc interface Java có một phương thức trừu tượng so với một lớp trừu tượng cho họ Strategy theo tiêu chí nào?
Bạn sẽ sử dụng lambda Java thay cho Concrete Strategy có tên khi hành vi đơn giản và ít trạng thái như thế nào?
Bạn sẽ nhận biết lúc nào lambda làm mất ý nghĩa nghiệp vụ hoặc gây khó khăn khi cần kiểm thử và chẩn đoán ra sao?
Bạn sẽ triển khai các Strategy bằng enum Java trong trường hợp tập lựa chọn cố định và xác định giới hạn của cách đó như thế nào?
Bạn sẽ so sánh enum, lambda và các lớp triển khai interface về khả năng mở rộng và quản lý phụ thuộc ra sao?
Khi một Strategy cần truy cập repository hoặc dịch vụ bên ngoài, bạn sẽ cung cấp các phụ thuộc ấy bằng cách nào?
Bạn sẽ quyết định Strategy nào là đối tượng bất biến có thể tái sử dụng và Strategy nào cần tạo riêng cho từng yêu cầu như thế nào?
Khi nhiều luồng cùng dùng một Strategy, bạn sẽ kiểm tra nguy cơ dữ liệu có thể thay đổi bị chia sẻ ra sao?
Bạn sẽ xử lý cấu hình thuật toán thay đổi theo tenant mà không khiến Strategy của tenant này ảnh hưởng tenant khác như thế nào?
Bạn sẽ thiết kế thông báo lỗi và hành vi fallback khi Strategy được chọn không thể hoàn thành nhiệm vụ ra sao?
Bạn sẽ phân biệt fallback sang thuật toán khác với việc làm sai quy tắc nghiệp vụ trong tình huống nào?
Bạn sẽ xác định các bất biến đầu ra mà mọi Strategy phải bảo đảm để Context có thể xử lý thống nhất như thế nào?
Khi một chiến lược có độ chính xác khác chiến lược khác, bạn sẽ định nghĩa cách so sánh kết quả hợp lệ trong hợp đồng ra sao?
Bạn sẽ kiểm thử từng Concrete Strategy độc lập để đánh giá đúng thuật toán thay vì kiểm tra chi tiết cách Context gọi nó như thế nào?
Bạn sẽ thiết kế bộ test chung cho mọi Strategy để phát hiện triển khai nào vi phạm hợp đồng như thế nào?
Bạn sẽ chọn dữ liệu biên nào cho các Strategy tính chiết khấu để phát hiện lỗi về ngưỡng và làm tròn ra sao?
Bạn sẽ xác minh Context chuyển đúng input và nhận đúng output từ Strategy được tiêm vào như thế nào?
Khi thêm một Strategy mới, bạn sẽ kiểm thử hệ thống chọn đúng biến thể mà không làm thay đổi các biến thể cũ ra sao?
Bạn sẽ phân biệt lỗi trong thuật toán của Strategy với lỗi trong logic lựa chọn Strategy bằng loại kiểm thử nào?
Bạn sẽ thiết kế test để xác nhận thuật toán được thay thế lúc chạy thực sự có hiệu lực cho lời gọi tiếp theo như thế nào?
Khi các Strategy có thời gian thực thi khác nhau, bạn sẽ đo đạc hiệu năng mà không trộn kết quả với độ đúng nghiệp vụ ra sao?
Bạn sẽ đánh giá rủi ro khi mỗi Strategy trả về một kiểu dữ liệu khác nhau và đề xuất điều chỉnh hợp đồng như thế nào?
Bạn sẽ phân tích mối quan hệ giữa Strategy và nguyên tắc Open/Closed khi bổ sung thuật toán mới ra sao?
Vì sao Strategy không tự động loại bỏ mọi câu lệnh điều kiện trong hệ thống và bạn sẽ xác định điểm điều kiện hợp lý ở đâu?
Bạn sẽ phân biệt Strategy với State khi lựa chọn hành vi phụ thuộc vào trạng thái vòng đời thay vì một thuật toán thay thế như thế nào?
Bạn sẽ so sánh Strategy với Template Method theo cơ chế composition và inheritance trong một bài toán cụ thể ra sao?
Khi nhiều Strategy lặp lại một phần logic, bạn sẽ cân nhắc trích xuất thành phần dùng chung mà không tạo phụ thuộc giữa các thuật toán như thế nào?
Bạn sẽ nhận diện trường hợp dùng Strategy tạo quá nhiều lớp nhỏ không có khác biệt thực chất và quyết định đơn giản hóa ra sao?
Bạn sẽ xây dựng quy ước đặt tên để các Strategy phản ánh chính sách nghiệp vụ thay vì tên công nghệ triển khai như thế nào?
Khi code cũ có nhánh điều kiện tính giá, bạn sẽ chuyển dần sang Strategy mà vẫn giữ hành vi hiện tại như thế nào?
Bạn sẽ phân biệt Strategy do ứng dụng tự chọn với Strategy do caller cung cấp và đánh giá rủi ro của từng cách ra sao?
Bạn sẽ kiểm soát phiên bản cấu hình chọn Strategy để có thể tái hiện một kết quả tính toán trong quá khứ như thế nào?
Khi một yêu cầu áp dụng đồng thời nhiều thuật toán, bạn sẽ đánh giá nên phối hợp nhiều Strategy hay xây dựng một pipeline riêng ra sao?
Bạn sẽ xác định khi nào cần ghi log tên Strategy đã chọn mà vẫn tránh để chi tiết triển khai lộ ra ngoài API như thế nào?
Bạn sẽ đánh giá khả năng bảo trì sau khi áp dụng Strategy bằng những tín hiệu nào về độ phức tạp, test và thay đổi nghiệp vụ?
Khi một chiến lược mới làm xuất hiện yêu cầu đầu vào đặc biệt, bạn sẽ điều chỉnh hợp đồng hay chia lại họ Strategy dựa trên nguyên tắc nào?
