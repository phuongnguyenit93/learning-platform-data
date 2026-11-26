Nhóm xây bộ lọc log chỉ chấp nhận chuỗi trạng thái OPEN, RETRY, CLOSE theo một thứ tự quy định; danh sách ví dụ đúng chưa làm rõ toàn bộ ngôn ngữ các chuỗi được phép.
Trong hệ thống xác thực thiết bị, một máy trạng thái phải nhận đúng mẫu bắt đầu bằng mã đăng nhập và kết thúc bằng mã xác nhận; nhóm chưa xác định trạng thái nào tương ứng với tiền tố hợp lệ của thông điệp.
Một bộ đọc biểu thức chính quy được chuyển thành NFA; cùng một chuỗi có thể đi theo nhiều nhánh và người viết engine nhầm việc có một nhánh thất bại với việc toàn bộ chuỗi bị từ chối.
Nhóm triển khai DFA cho mã đặt hàng và vô tình bỏ qua chuyển trạng thái khi gặp ký tự bất thường; hai phiên bản chương trình xử lý trường hợp không có cạnh chuyển khác nhau.
Một ứng dụng cần kiểm tra mã hàng thỏa đồng thời hai quy tắc định dạng độc lập; hai automaton đã có nhưng đội thiết kế chưa biết cách mô hình hóa kết quả giao của hai ngôn ngữ.
Đội cần từ chối toàn bộ mã thẻ không hợp lệ bằng phép lấy phần bù ngôn ngữ hợp lệ; DFA đang dùng chưa định nghĩa chuyển trạng thái cho mọi ký tự đầu vào.
Trong bộ kiểm tra protocol, hai DFA có số trạng thái khác nhau nhưng chấp nhận cùng tập chuỗi thử nghiệm; nhóm muốn xác định chúng có tương đương trên mọi chuỗi hay không.
Thiết bị IoT chỉ có bộ nhớ nhỏ phải kiểm tra chuỗi sự kiện hợp lệ; automaton được tạo từ biểu thức mô tả có hàng trăm trạng thái và nhóm nghi ngờ nhiều trạng thái có thể gộp.
Một DSL cho phép lặp không hoặc nhiều lần một lệnh cấu hình; parser hiện yêu cầu xuất hiện lệnh ít nhất một lần, làm nhóm phải phân biệt toán tử lặp không giới hạn với lặp tối thiểu một lần.
Một thành viên đề xuất dùng biểu thức chính quy theo định nghĩa ngôn ngữ chính quy để kiểm tra ngoặc lồng nhau ở độ sâu bất kỳ; dữ liệu chạy thử chỉ có tối đa ba tầng khiến giới hạn chưa lộ ra.
Nhóm nghiên cứu bộ nhận dạng ngôn ngữ có số ký tự a bằng số ký tự b theo một thứ tự xác định; một lập luận dựa trên bơm chuỗi được đưa ra nhưng chưa xét đầy đủ mọi cách phân tách hợp lệ.
Trong ứng dụng kiểm tra chuỗi, đội đã có hai ngôn ngữ chính quy cho hai lớp token và cần chứng minh ngôn ngữ hợp, giao và nối vẫn nhận dạng được bằng cơ chế hữu hạn phù hợp.
Nhóm viết parser cho biểu thức số học có ngoặc lồng nhau tùy ý; bộ dò token hữu hạn xử lý đúng các ví dụ nông nhưng không lưu đủ thông tin để khớp mọi cặp ngoặc.
Một văn phạm cho phép biểu thức chứa phép cộng và nhân nhưng không mã hóa rõ ưu tiên; cùng chuỗi đầu vào có hai cây phân tích cú pháp dẫn đến hai kết quả tính khác nhau.
Công cụ phân tích cú pháp kiểu đệ quy xuống rơi vào đệ quy vô hạn với một quy tắc văn phạm có đệ quy trái trực tiếp, dù chuỗi đầu vào có thể hợp lệ.
Nhóm xây parser dự đoán một token nhưng hai production có tập token bắt đầu giao nhau; parser không biết chọn nhánh nào nếu không có thêm ngữ cảnh.
Trong ngôn ngữ cấu hình, một thành phần ngữ pháp có thể sinh chuỗi rỗng; việc tính sai trường hợp nullable làm parser từ chối cấu hình chỉ chứa các trường tùy chọn.
Một engine phân tích cú pháp thao tác trên ngăn xếp để theo dõi lời gọi hàm lồng nhau; nhóm cần liên hệ số lượng mức lồng với những gì automaton hữu hạn có thể ghi nhớ.
Nhóm muốn nhận đúng các chuỗi dạng n ký tự a, tiếp theo n ký tự b, rồi n ký tự c với n bất kỳ; thiết kế dùng một ngăn xếp đang vướng khó khăn khi phải đối chiếu đồng thời ba nhóm.
Bộ nhận dạng palindrome không có dấu ngăn giữa hai nửa phải chọn vị trí giữa khi đọc trái sang phải; nhóm tranh luận việc chọn không tất định có tác dụng gì đối với automaton ngăn xếp.
Một dịch vụ soạn thảo cấu hình muốn báo vị trí đóng ngoặc sai; văn phạm phi ngữ cảnh mô tả chuỗi hợp lệ nhưng việc ánh xạ lỗi parser sang vị trí cụ thể vẫn gây khó khăn.
Khi chuyển văn phạm về dạng chuẩn để phục vụ thuật toán phân tích, một phép biến đổi bỏ production sinh chuỗi rỗng khiến cấu hình rỗng vốn hợp lệ không còn được chấp nhận.
Đội thiết kế máy Turing mô phỏng phép tăng bộ đếm trên băng ký hiệu; sơ đồ trạng thái bỏ qua cách xử lý trường hợp đầu đọc gặp ô trống ở ranh giới dữ liệu.
Nhóm xây chương trình liệt kê các chuỗi được một ngôn ngữ chấp nhận; người dùng nhập chuỗi không thuộc ngôn ngữ và chương trình chạy mãi nên họ nhầm bộ nhận dạng với bộ quyết định.
Trong công cụ chứng minh, thuật toán trả lời đúng khi tìm thấy một phản ví dụ nhưng có thể không dừng nếu không tồn tại phản ví dụ; tài liệu lại mô tả nó như một thủ tục quyết định toàn phần.
Một nhóm cam kết xây công cụ nhận bất kỳ chương trình cùng đầu vào rồi xác định chắc chắn chương trình có dừng hay không; bản mẫu chỉ kiểm thử những chương trình kết thúc nhanh.
Đội kiểm thử giới hạn mô phỏng một chương trình trong 10 triệu bước rồi kết luận mọi chương trình chưa dừng đều sẽ chạy vô hạn; người thiết kế chưa phân biệt bài toán dừng có giới hạn với bài toán dừng tổng quát.
Người phát triển bộ phân tích mã muốn quyết định tự động liệu một chương trình bất kỳ có bao giờ in ra thông điệp lỗi hay không; nhóm đang đánh đồng thuộc tính hành vi tổng quát với kiểm tra cú pháp hữu hạn.
Hai thuật toán tối ưu cho kết quả giống nhau trên hàng nghìn bộ dữ liệu; đội muốn tạo công cụ khẳng định chúng tương đương trên mọi đầu vào và mọi đường thực thi.
Trong bài giảng về bất khả quyết, một học viên dựng phép quy dẫn từ bài toán dừng sang bài toán xác định chương trình có truy cập file hay không nhưng chưa chỉ rõ cách biến đổi từng instance.
Nhóm xây bộ kiểm tra trạng thái cho một protocol chỉ có số trạng thái hữu hạn và ngạc nhiên khi phương pháp liệt kê có thể kết luận tính an toàn, còn cùng câu hỏi với chương trình tùy ý lại không có bảo đảm tổng quát.
Trong bài toán mã hóa chuỗi và máy Turing thành đầu vào của một thuật toán khác, nhóm quên quy định cách phân biệt phần mô tả máy với phần dữ liệu, làm lập luận quy dẫn thiếu ánh xạ xác định.
Hệ thống kiểm tra số nguyên tố nhận số n ở dạng nhị phân, nhưng báo cáo độ phức tạp lấy n làm kích thước đầu vào thay vì số bit biểu diễn, dẫn đến so sánh thuật toán thiếu cơ sở.
Nhóm phát triển bộ tìm kiếm tất cả tập con của 45 phần tử; thuật toán hoạt động tốt với 15 phần tử nhưng thời gian tăng vọt theo cấp số mũ khi chạy bộ dữ liệu thật.
Một thuật toán quy hoạch động giải bài toán tổng tập con với chi phí phụ thuộc tổng giá trị các phần tử; đội mô tả đây là thời gian đa thức theo độ dài mã hóa nhị phân của dữ liệu.
Trong bài toán lập thời khóa biểu, nhóm có thể kiểm tra nhanh một lịch gán sẵn thỏa mọi ràng buộc nhưng việc tìm được lịch hợp lệ từ đầu vẫn tốn rất nhiều lần thử.
Đội xây bộ giải 3-SAT và cho rằng nếu chưa tìm được nghiệm sau nhiều giờ thì công thức chắc chắn vô nghiệm; quy trình chưa phân biệt tìm nhân chứng với chứng minh không tồn tại nhân chứng.
Nhóm quản lý tuyến giao hàng muốn dùng bộ giải đường đi Hamilton để hỗ trợ vấn đề phân ca; bản đề xuất quy dẫn chỉ nói hai bài toán giống nhau mà chưa chứng minh cách biến đổi bảo toàn đáp án có hoặc không.
Trong tài liệu phân loại NP-đầy đủ, người viết đã biết bài toán A là NP-đầy đủ nhưng chuyển một instance của bài toán B sang A rồi tuyên bố chứng minh B khó ít nhất bằng A.
Đội tối ưu lập lịch cần lời giải tốt trong vài giây cho dữ liệu lớn; nhóm tranh luận giữa thuật toán xấp xỉ có bảo đảm chất lượng và thuật toán tìm chính xác có thời gian tăng nhanh khi bài toán khó.
