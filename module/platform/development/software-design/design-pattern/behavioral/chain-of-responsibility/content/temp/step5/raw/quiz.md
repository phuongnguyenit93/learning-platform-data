Câu 1: Mục đích chính của Chain of Responsibility là gì?
A. Để nhiều handler có cơ hội xử lý cùng yêu cầu
B. Để client chọn trực tiếp một handler cụ thể
C. Để request luôn chạy qua mọi handler không điều kiện
D. Để mỗi handler tự tạo bản sao yêu cầu trước khi chạy
Đáp án đúng: A

Câu 2: Trong Chain of Responsibility, client nên biết thành phần nào?
A. Toàn bộ lớp handler và thứ tự gọi nội bộ
B. Điểm đầu của chuỗi qua một hợp đồng xử lý
C. Handler cuối cùng và trạng thái từng bước
D. Mỗi nhánh điều kiện của các concrete handler
Đáp án đúng: B

Câu 3: Một Handler interface trong Java thường quy định nội dung gì?
A. Cấu trúc bảng dữ liệu lưu lịch sử request
B. Thuật toán cụ thể của từng bước xử lý riêng
C. Cách tiếp nhận request và chuyển tiếp khi cần
D. Định dạng hiển thị kết quả trong giao diện
Đáp án đúng: C

Câu 4: Handler hiện tại không đáp ứng điều kiện xử lý thì nên làm gì?
A. Dừng chuỗi với kết quả thành công giả định
B. Chuyển request cho successor theo hợp đồng
C. Gọi lại chính mình để thử điều kiện lần nữa
D. Chọn một concrete handler bằng tên lớp
Đáp án đúng: B

Câu 5: Nếu hết chuỗi mà không handler nào nhận yêu cầu, thiết kế cần gì?
A. Tự mặc định request đã được xử lý thành công
B. Kết quả chưa xử lý hoặc handler dự phòng rõ ràng
C. Thực thi lại chuỗi từ đầu mà không giới hạn
D. Giấu trạng thái và không trả kết quả cho client
Đáp án đúng: B

Câu 6: Trong chuỗi kiểu first-match, khi một handler xử lý xong thì sao?
A. Luôn gửi tiếp request sang successor còn lại
B. Luôn khởi động lại chuỗi từ handler đầu
C. Chuyển sang mọi handler trước đó để xác nhận
D. Ngừng chuyển tiếp để tránh xử lý request hai lần
Đáp án đúng: D

Câu 7: Một pipeline middleware khác first-match ở điểm nào?
A. Mỗi handler có thể thực hiện rồi vẫn chuyển tiếp
B. Mọi handler bắt buộc cùng loại điều kiện xử lý
C. Chỉ handler cuối cùng được phép đọc request
D. Client phải gọi riêng từng handler trong chuỗi
Đáp án đúng: A

Câu 8: Trong chuỗi kiểm tra quyền rồi mới thực hiện tác vụ, thứ tự nào hợp lý?
A. Ghi dữ liệu trước rồi mới kiểm tra quyền của user
B. Báo thành công trước khi chạy bước xác thực
C. Xác thực và phân quyền trước bước có tác dụng phụ
D. Bỏ bước kiểm tra quyền ở request lặp lại
Đáp án đúng: C

Câu 9: Vì sao thứ tự các handler có thể ảnh hưởng kết quả?
A. Các handler được JVM tự đảo thứ tự mỗi lần
B. Handler sớm có thể chặn hoặc biến đổi request
C. Mọi handler luôn độc lập với dữ liệu request
D. Thứ tự chỉ ảnh hưởng tốc độ biên dịch Java
Đáp án đúng: B

Câu 10: Cách nào giúp mở rộng chuỗi mà không sửa lớp client?
A. Lắp thêm handler thông qua cấu hình khởi tạo
B. Thêm if cho mỗi handler vào mọi client gọi
C. Cho client new từng concrete handler ở mỗi request
D. Chuyển toàn bộ logic handler vào một switch lớn
Đáp án đúng: A

Câu 11: Trong chuỗi phân cấp hỗ trợ, handler cấp thấp nên làm gì khi vượt thẩm quyền?
A. Trả thành công dù chưa xử lý hết yêu cầu
B. Thay đổi yêu cầu thành loại luôn được chấp thuận
C. Chuyển tiếp đến handler có khả năng giải quyết
D. Tạo thêm nhiều request không liên quan
Đáp án đúng: C

Câu 12: Khi xây chuỗi bằng successor reference, rủi ro cấu hình nào cần phát hiện?
A. Hai handler có cùng kiểu dữ liệu return
B. Một handler được khởi tạo bởi dependency injection
C. Liên kết vòng khiến request chuyển tiếp vô hạn
D. Client chỉ giữ tham chiếu handler đầu
Đáp án đúng: C

Câu 13: Điều gì giúp handler tái sử dụng tốt giữa nhiều chuỗi?
A. Truy cập trực tiếp mọi concrete handler trong dự án
B. Phụ thuộc hợp đồng request và successor trừu tượng
C. Đọc cấu hình từ biến global có thể bị đổi bất kỳ lúc
D. Dùng tên package của client để chọn xử lý
Đáp án đúng: B

Câu 14: Khi một handler ném ngoại lệ trong chuỗi, cần quy định gì?
A. Mọi lỗi đều được tự động xem là đã xử lý
B. Mọi lỗi đều buộc JVM gọi lại request từ đầu
C. Successor luôn chạy trước khi exception được kiểm tra
D. Cách dừng, chuyển tiếp hoặc chuyển lỗi nhất quán
Đáp án đúng: D

Câu 15: Trong service xử lý nhiều request song song, handler dùng chung nên ưu tiên gì?
A. Lưu request gần nhất vào field shared có thể sửa
B. Tạo cache tạm từ request mà không đồng bộ
C. Tránh lưu trạng thái thay đổi theo từng request
D. Dùng biến static để giữ user hiện đang xác thực
Đáp án đúng: C

Câu 16: Nếu chuỗi hàng nghìn handler dùng đệ quy để forward, rủi ro nào tăng?
A. Ngăn xếp lời gọi sâu gây StackOverflowError
B. Tất cả handler sẽ tự động chạy trên thread khác
C. Dữ liệu request được JVM tự serialize thành JSON
D. Mỗi handler sẽ phải tạo một ClassLoader mới
Đáp án đúng: A

Câu 17: Cách nào giảm độ sâu ngăn xếp khi chuyển qua chuỗi rất dài?
A. Gọi đệ quy hai lần trên mỗi successor
B. Đổi tên method handle thành execute
C. Điều phối duyệt handler theo vòng lặp
D. Tăng số lớp kế thừa của concrete handler
Đáp án đúng: C

Câu 18: Trong Java Servlet Filter, thao tác nào đưa request tiếp theo trong chuỗi?
A. Gọi FilterChain.doFilter(request, response)
B. Gọi HttpServletResponse.sendRedirect tới chính URL
C. Gọi ServletContext.getAttribute bằng tên filter
D. Gọi HttpServletRequest.getSession để tiếp tục
Đáp án đúng: A

Câu 19: Trong bộ lọc HTTP, nếu handler đã từ chối truy cập, thường nên làm gì?
A. Gọi chain rồi mới gửi status bị từ chối
B. Đưa request vào queue và coi như đã xác thực
C. Chuyển request sang controller rồi ghi lỗi vào log
D. Trả lỗi thích hợp và không gọi tiếp filter chain
Đáp án đúng: D

Câu 20: Khi test handler quyết định xử lý và dừng, cần xác nhận gì?
A. Kết quả đúng và successor không được gọi
B. Kết quả đúng và successor luôn được gọi hai lần
C. Chỉ handler được tạo bằng constructor public
D. Chỉ không có lỗi compiler trong file handler
Đáp án đúng: A

Câu 21: Khi test handler bỏ qua request, cần xác nhận điều gì?
A. Handler tự ghi kết quả thành công trước chuyển
B. Client phải biết tên đầy đủ của successor
C. Request bị hủy trước khi handler kế tiếp nhận
D. Successor nhận cùng ngữ cảnh xử lý dự kiến
Đáp án đúng: D

Câu 22: Để kiểm tra toàn chuỗi thay vì một handler, test nên dùng gì?
A. Chỉ kiểm tra một constructor của handler đầu
B. Chỉ đếm tổng số lớp implements Handler
C. Chỉ kiểm tra danh sách phụ thuộc của Maven
D. Tình huống đi qua nhiều mắt xích và điểm dừng
Đáp án đúng: D

Câu 23: Trong chuỗi ghi log/tracing, cách bảo toàn quan hệ request là gì?
A. Sinh ID khác nhau mà không giữ liên kết ở mỗi bước
B. Dùng số dòng source Java làm mã giao dịch
C. Truyền correlation ID qua ngữ cảnh các handler
D. Chỉ ghi log từ handler cuối, bỏ các bước trước
Đáp án đúng: C

Câu 24: Chain of Responsibility khác Strategy chủ yếu ở đâu?
A. Client trực tiếp chọn một thuật toán cố định để chạy
B. Một đối tượng chỉ có một implementation tại runtime
C. Không có điều kiện xử lý trước khi thực thi thuật toán
D. Request được xét bởi chuỗi handler có thể chuyển tiếp
Đáp án đúng: D

Câu 25: So với Decorator, điểm nhấn của Chain of Responsibility là gì?
A. Mọi handler nhất thiết bọc thêm một hành vi cho object
B. Handler có thể nhận xử lý hoặc nhường cho mắt xích sau
C. Cấu trúc đối tượng chỉ cần kế thừa một abstract class
D. Mỗi handler luôn phải gọi successor sau khi đã xử lý
Đáp án đúng: B

Câu 26: Nếu nhiều handler cùng đủ điều kiện xử lý trong chuỗi first-match, yếu tố nào quyết định?
A. Handler có tên lớp dài nhất được ưu tiên
B. JVM tự chọn handler ngẫu nhiên theo thread
C. Handler cuối cùng luôn thắng mọi handler trước
D. Thứ tự chuỗi và quy tắc dừng sau khi nhận
Đáp án đúng: D

Câu 27: Với chuỗi validation cần thu thập mọi lỗi, thiết kế nào phù hợp?
A. Dừng ngay khi validator đầu tiên trả về thành công
B. Mỗi validator chuyển tiếp và bổ sung lỗi vào kết quả
C. Chỉ chạy validator cuối cùng để tránh trùng lỗi
D. Client tự gọi riêng mọi concrete validator
Đáp án đúng: B

Câu 28: Khi chain bắt đầu gây khó theo dõi, biện pháp nào hữu ích?
A. Ghi nhận thứ tự handler và nguyên nhân dừng
B. Ẩn toàn bộ đường chuyển tiếp sau một method static
C. Bỏ hết test vì thứ tự có thể đổi theo config
D. Cho mỗi handler tự đổi vị trí trong chain
Đáp án đúng: A
