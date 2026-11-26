Câu 1: Hệ thống Java nhận số điện thoại ở nhiều quốc gia với cách nhập khác nhau; biểu diễn đích gửi phù hợp nhất là gì?
A. Chuỗi số giữ nguyên ký tự nhập trên giao diện người dùng
B. Số được chuẩn hóa theo dạng quốc tế E.164
C. Số nội địa ghép với mã vùng server đang chạy
D. Mã người dùng thay cho số thuê bao của nhà mạng
Đáp án đúng: B

Câu 2: Khách nhập số nội địa có số 0 đầu và mã quốc gia được chọn riêng; backend cần chú ý điều gì khi chuẩn hóa?
A. Luôn nối trực tiếp số 0 với mã quốc gia đã chọn
B. Xóa mọi chữ số 0 ở bất kỳ vị trí nào của số
C. Dùng mã vùng của IP máy chủ thay cho quốc gia
D. Quy tắc quốc gia trước khi tạo số chuẩn E.164
Đáp án đúng: D

Câu 3: Backend phải gửi SMS qua một nhà cung cấp có REST API; kiểu tích hợp nào phù hợp nhất?
A. HTTP API với xác thực và xử lý phản hồi gửi
B. SMPP bind trực tiếp qua giao diện người nhận SMS
C. Webhook chỉ dùng để đẩy nhận dạng người dùng
D. Gửi email rồi xem như SMS đã đến nhà mạng
Đáp án đúng: A

Câu 4: Hệ thống gửi số lượng SMS lớn qua kết nối dài tới SMSC; giao thức nào phù hợp hơn HTTP đơn lẻ?
A. SMPP với phiên kết nối và quản lý trao đổi PDU
B. HTTP polling tới website công khai của nhà mạng
C. WebSocket mở từ điện thoại từng người nhận SMS
D. IMAP đọc hộp thư xác nhận của mỗi khách hàng
Đáp án đúng: A

Câu 5: Một SMS gateway trả về mã đã tiếp nhận yêu cầu gửi, nhưng người dùng chưa nhận được tin; điều nào đúng?
A. Đã chắc chắn thiết bị nhận được nội dung đầy đủ
B. Đã xác nhận người nhận đọc nội dung trên điện thoại
C. Đã chứng minh mọi nhà mạng đều định tuyến thành công
D. Tiếp nhận yêu cầu không chứng minh SMS đã phát tới máy
Đáp án đúng: D

Câu 6: Ứng dụng cần biết SMS đã tới thiết bị hay chưa sau khi gửi; loại thông tin nào quan trọng?
A. Delivery receipt từ nhà cung cấp hoặc nhà mạng
B. Mã HTTP của request tạo đơn hàng ban đầu
C. Tên class Java dùng chuyển mẫu SMS thành chuỗi
D. Phiên bản giao diện web của người quản trị hệ thống
Đáp án đúng: A

Câu 7: Gateway phát delivery receipt bất đồng bộ sau vài phút; backend nên liên kết nó với gì?
A. Tên mẫu nội dung của tin được tạo gần nhất
B. Địa chỉ IP của worker gửi tin vào hàng đợi
C. Màu cảnh báo được dùng trên dashboard giám sát
D. Message ID và trạng thái gửi đã lưu trước đó
Đáp án đúng: D

Câu 8: Một SMS bị báo DELIVERED sau khi callback FAILED tới trước do nguồn khác nhau; nguyên tắc nào cần xét?
A. Luôn lấy callback cuối cùng không xét thời điểm sự kiện
B. Ngữ nghĩa trạng thái và thứ tự receipt bất đồng bộ
C. Xem mọi receipt thất bại là bằng chứng máy đã nhận
D. Tự xóa lịch sử trạng thái khi có phản hồi mới bất kỳ
Đáp án đúng: B

Câu 9: Nhiều dịch vụ cần gửi OTP nhưng một số lần xác thực không thành công vẫn giữ mã cũ dùng lại; thuộc tính nào thiết yếu?
A. OTP giữ hiệu lực vô thời hạn để hạn chế số SMS
B. OTP được đưa vào log đầy đủ để hỗ trợ tra cứu
C. OTP được dùng chung cho mọi người trong một phiên gửi
D. OTP có hạn dùng và chỉ chấp nhận một lần hợp lệ
Đáp án đúng: D

Câu 10: Hệ thống cho phép yêu cầu OTP liên tục không giới hạn nên SMS bị gửi dồn vào một số; cần kiểm soát điều gì?
A. Tăng tốc gateway để mỗi mã đến nhanh hơn
B. Đặt thời hạn OTP dài hơn để giảm độ trễ mạng
C. Dùng nhiều nhà cung cấp để tăng số tin trên mỗi số
D. Giới hạn tần suất cấp OTP theo ngữ cảnh xác thực
Đáp án đúng: D

Câu 11: Một nhóm hỗ trợ muốn tìm lỗi OTP nhưng log Java chứa cả mã xác thực và số đầy đủ; rủi ro nào cần xử lý?
A. Thiếu metadata định dạng nội dung trên điện thoại
B. Số lượng worker retry ít hơn các lần đăng nhập
C. Lộ dữ liệu nhạy cảm qua nhật ký ứng dụng
D. Giới hạn nhắn tin ở một nhà mạng cụ thể
Đáp án đúng: C

Câu 12: SMS nhắc lịch và OTP dùng cùng hàng đợi; khi có hàng nghìn tin nhắc, OTP đến trễ; thay đổi nào phù hợp?
A. Kéo dài thời gian sống OTP theo mọi tình huống
B. Gửi lại toàn bộ tin nhắc ngay khi OTP được tạo
C. Phân mức ưu tiên và điều phối các loại thông báo
D. Dùng một template chung cho mọi tin trong hàng đợi
Đáp án đúng: C

Câu 13: Một gateway báo timeout sau request gửi SMS, nhưng có thể đã tiếp nhận tin; retry ngay có rủi ro nào?
A. Gateway luôn tự từ chối mọi yêu cầu có nội dung trùng
B. Người nhận có thể nhận hai SMS cho cùng sự kiện
C. Mọi SMS gửi qua HTTP đều được đảm bảo exactly-once
D. Nhà mạng tự kết hợp mọi tin trùng thành một bản
Đáp án đúng: B

Câu 14: Backend Java bị restart sau khi xác nhận đơn hàng nhưng trước khi gọi gateway; cần cơ chế nào để không mất SMS?
A. Giữ thông báo chỉ trong một danh sách bộ nhớ tạm
B. Gửi SMS trực tiếp trong phần tạo giao diện đơn hàng
C. Lưu bền vững công việc gửi và tiến độ xử lý
D. Ghi mỗi số điện thoại vào log rồi xóa job gửi tin
Đáp án đúng: C

Câu 15: Một sự kiện thanh toán được queue nhận lại nhiều lần, khiến hệ thống gửi SMS trùng; khóa nào hữu ích để ngăn trùng?
A. Thời điểm hiện tại tại mỗi worker xử lý message
B. Định danh sự kiện nghiệp vụ ổn định qua lần retry
C. Mã ngẫu nhiên mới sinh cho mọi lần gọi gateway
D. Tên của template không kèm định danh giao dịch
Đáp án đúng: B

Câu 16: Một chiến dịch SMS sử dụng nội dung có dấu và emoji, chi phí đột ngột tăng; nguyên nhân nào cần đánh giá?
A. Mã quốc gia trong E.164 tự thêm phí cho mọi tin
B. Mã hóa ký tự ảnh hưởng số phân đoạn SMS
C. Số lượng object Java trong payload HTTP lớn hơn
D. Bản ghi delivery receipt được gửi quá nhiều lần
Đáp án đúng: B

Câu 17: Ứng dụng có mẫu SMS theo từng ngôn ngữ và tham số tên khách; khi gửi cần bảo đảm điều gì?
A. Gắn mã OTP thật vào mọi mẫu để dễ kiểm thử
B. Dùng một mẫu tiếng Anh cho tất cả số quốc tế
C. Biến mẫu được xử lý đúng và nội dung đã kiểm tra
D. Chèn toàn bộ thông tin cá nhân vào nội dung SMS
Đáp án đúng: C

Câu 18: Nhà cung cấp SMS thay đổi cách phân loại lỗi gửi; hệ thống retry mọi lỗi, kể cả số không hợp lệ; nên cải thiện gì?
A. Phân biệt lỗi tạm thời với lỗi không thể khắc phục
B. Tăng số lần thử lại cho mọi mã lỗi giống nhau
C. Gửi sang nhà cung cấp khác trước khi đọc mã lỗi
D. Đổi tên template cho tất cả request gặp lỗi
Đáp án đúng: A

Câu 19: Gateway giới hạn số SMS mỗi giây, nhưng worker Java đẩy đồng loạt nhiều request; chiến lược nào phù hợp?
A. Điều tiết thông lượng và giãn cách retry khi cần
B. Tạo nhiều thread hơn để cố vượt qua mọi giới hạn
C. Đổi số điện thoại nhận thành một topic chung
D. Bỏ kiểm tra kết quả để giảm chi phí xử lý gateway
Đáp án đúng: A

Câu 20: Một SMS gửi qua HTTP API trả lỗi tạm thời; cách retry nào giảm quá tải khi nhiều worker cùng lỗi?
A. Retry mọi tin ngay đúng cùng một thời điểm cố định
B. Tạo phiên HTTP mới và gửi vô hạn không giới hạn
C. Backoff có độ lệch thời gian và giới hạn thử lại
D. Giữ toàn bộ worker chờ đồng bộ trong transaction
Đáp án đúng: C

Câu 21: Một doanh nghiệp có hai nhà cung cấp SMS; khi tuyến chính gặp sự cố cần quyết định gì trước khi chuyển tuyến?
A. Luôn gửi qua cả hai gateway với mọi đơn hàng
B. Xác định trạng thái lần gửi đầu để tránh gửi trùng
C. Bỏ receipt trước đó vì tuyến dự phòng tách biệt
D. Thay số điện thoại người nhận để phù hợp tuyến mới
Đáp án đúng: B

Câu 22: Một provider trả kết quả đã nhận request nhưng chưa có delivery receipt; backend nên thể hiện trạng thái nào?
A. Đã phát thành công và người dùng đã đọc mã OTP
B. Đã bị thất bại vĩnh viễn và không cần theo dõi
C. Đã tiếp nhận hoặc đang chờ xác nhận giao nhận
D. Đã hoàn tiền SMS ngay khi HTTP response thành công
Đáp án đúng: C

Câu 23: Một callback delivery receipt tới backend từ nguồn Internet và có thể bị giả mạo; cần kiểm tra điều gì?
A. Chỉ kiểm tra tên template có chứa mã chiến dịch
B. Cho phép mọi địa chỉ IP tự cập nhật trạng thái tin
C. Nguồn gửi được xác thực và dữ liệu khớp message ID
D. Tin mọi request có trường delivered trong body
Đáp án đúng: C

Câu 24: SMPP gateway phản hồi chậm và liên tục ngắt phiên kết nối; hệ thống cần quan sát yếu tố nào?
A. Chỉ độ dài title của trang quản trị chiến dịch
B. Chỉ số lượng bảng trong cơ sở dữ liệu người dùng
C. Chỉ tên biến dùng để lưu số điện thoại E.164
D. Trạng thái bind, kết nối và kết quả gửi qua phiên
Đáp án đúng: D

Câu 25: Một doanh nghiệp muốn đo chi phí SMS theo từng bộ phận, tuyến và loại thông báo; dữ liệu nào quan trọng?
A. Nhà cung cấp, số phân đoạn và thông tin quy chiếu
B. Tên class thực thi HTTP và phiên bản thư viện JSON
C. Chỉ trạng thái xanh đỏ của dashboard cảnh báo
D. Địa chỉ IP của máy chủ tạo yêu cầu gửi đầu tiên
Đáp án đúng: A

Câu 26: Một ứng dụng Spring gửi SMS ngay trong transaction xác nhận đơn, làm đơn lỗi khi gateway gián đoạn; nên làm gì?
A. Chờ SMS được phát tới máy rồi mới commit đơn hàng
B. Tách yêu cầu gửi SMS khỏi transaction cốt lõi
C. Hủy đơn nếu nhà mạng chưa trả receipt trong vài giây
D. Đưa OTP vào bảng đơn để coi là đã gửi thông báo
Đáp án đúng: B

Câu 27: Một tin nhắc lịch phải đến trước giờ hẹn nhưng nằm trong queue quá lâu; cần áp dụng thuộc tính nào?
A. Mã số nhà mạng được lưu trong tên template SMS
B. Phiên bản hệ điều hành của người dùng nhận lịch
C. Số lần dựng lại object Java trước khi gọi gateway
D. Thời hạn hữu ích của tin trước khi thực hiện gửi
Đáp án đúng: D

Câu 28: Một số khách không nhận SMS dù gateway báo đã tiếp nhận; dữ liệu chẩn đoán nào nên được lưu?
A. Message ID, lỗi tuyến, receipt và thời điểm xử lý
B. Số dòng Java chứa đoạn gọi tới API của gateway
C. Mã phiên giao diện trình duyệt của quản trị viên
D. Tên nhánh Git của lần cuối sửa mẫu thông báo
Đáp án đúng: A

Câu 29: Nhiều số điện thoại được nhập sai định dạng dẫn đến SMS không đến; đâu là nơi kiểm soát cần ưu tiên?
A. Tự thêm mã quốc gia của máy chủ cho mọi số nhận
B. Gửi nguyên chuỗi nhập rồi đợi delivery receipt lỗi
C. Đổi route nhà mạng ngẫu nhiên khi thiếu số quốc gia
D. Chuẩn hóa và xác minh số trước khi xếp hàng gửi
Đáp án đúng: D

Câu 30: Một khách nhấn gửi lại OTP sau khi request đầu timeout; backend cần cân nhắc điều gì?
A. Tạo mã mới cho mọi lần nhấn mà không kiểm tra lịch sử
B. Giữ mọi OTP cũ còn hiệu lực để khách chọn tùy ý
C. Trạng thái lần gửi và giới hạn cấp mã theo yêu cầu
D. Gửi cùng lúc qua mọi gateway cho mỗi yêu cầu retry
Đáp án đúng: C

Câu 31: Một chiến dịch SMS quốc tế có tỷ lệ lỗi cao ở một mạng nhưng nhà cung cấp khác hoạt động tốt; cách phân tích nào phù hợp?
A. Chỉ so sánh tổng SMS theo ngày không phân tách mạng
B. Theo dõi lỗi theo quốc gia, nhà mạng và tuyến gửi
C. Chỉ xem số tin có nội dung dài hơn một phân đoạn
D. Thay toàn bộ mẫu tin trước khi kiểm tra trạng thái gửi
Đáp án đúng: B

Câu 32: Hệ thống thông báo SMS Java/Spring cần gửi OTP và tin dịch vụ đáng tin cậy với nhiều gateway; tiêu chí nào bao quát nhất?
A. E.164, quyền truy cập, hàng đợi, receipt và chi phí
B. Chọn gateway có tên ngắn và mẫu SMS đẹp nhất
C. Chỉ tối ưu tốc độ HTTP của request đầu tiên
D. Dựa vào phản hồi accepted như bằng chứng đã đọc
Đáp án đúng: A
