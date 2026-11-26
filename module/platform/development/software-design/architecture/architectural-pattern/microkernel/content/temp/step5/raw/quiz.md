Câu 1: Mục tiêu kiến trúc Microkernel trong một ứng dụng mở rộng là gì?
A. Đưa mọi tính năng vào lõi để tránh interface
B. Tách mỗi plugin thành database độc lập bắt buộc
C. Giữ lõi ổn định, bổ sung tính năng qua plugin
D. Thay toàn bộ logic core bằng script ở runtime
Đáp án đúng: C

Câu 2: Trong Microkernel, extension point nên được thể hiện như thế nào?
A. Một class cụ thể mà plugin sửa trực tiếp source
B. Một bảng database chứa toàn bộ implementation
C. Một tên file tùy ý không có ràng buộc kiểu
D. Hợp đồng rõ ràng để plugin cung cấp hành vi mới
Đáp án đúng: D

Câu 3: Một plugin xử lý định dạng xuất PDF thường nên làm gì?
A. Sửa trực tiếp mã nguồn core trước khi nạp
B. Cài đặt giao diện exporter do lõi công bố
C. Tự thay thế bộ định tuyến chính của hệ thống
D. Giữ độc quyền truy cập database của ứng dụng
Đáp án đúng: B

Câu 4: Vì sao API plugin cần ổn định qua nhiều phiên bản lõi?
A. Giảm khả năng plugin cũ hỏng khi host nâng cấp
B. Đảm bảo plugin luôn truy cập mọi lớp nội bộ của host
C. Buộc host tải lại mọi plugin ở từng request
D. Loại bỏ hoàn toàn nhu cầu kiểm thử tương thích
Đáp án đúng: A

Câu 5: Trong Java, cơ chế tiêu chuẩn nào hỗ trợ khám phá implementation của SPI?
A. ThreadLocal với biến môi trường mặc định
B. ObjectInputStream với bản sao class đã build
C. ServiceLoader với provider khai báo phù hợp
D. HttpSession với tên plugin làm khóa truy cập
Đáp án đúng: C

Câu 6: Khi plugin A và B cần phiên bản thư viện khác nhau, rủi ro điển hình là gì?
A. Bắt buộc xuất hiện deadlock trong mọi thread plugin
B. Xung đột lớp/phụ thuộc nếu dùng chung classpath
C. Tất cả plugin tự chuyển sang phiên bản mới nhất
D. Ứng dụng luôn mất toàn bộ cấu hình persistence
Đáp án đúng: B

Câu 7: Vì sao class loader tách biệt có thể hữu ích khi nạp plugin Java?
A. Bảo đảm plugin bất kỳ không thể đọc file hệ thống
B. Giúp cô lập một phần dependency của mỗi plugin
C. Tự đồng bộ dữ liệu giữa mọi phiên bản plugin
D. Tự tạo giao diện UI cho mọi plugin được nạp
Đáp án đúng: B

Câu 8: Interface API dùng chung giữa host và plugin nên được load thế nào?
A. Dùng class identity thống nhất ở ranh giới API
B. Mỗi bên định nghĩa một class trùng tên độc lập
C. Plugin tự sửa bytecode của interface host tại runtime
D. Mỗi request tạo class loader mới cho interface
Đáp án đúng: A

Câu 9: Khi plugin được nạp, thứ tự vòng đời nào thường hợp lý?
A. Khám phá, kiểm tra, khởi tạo, kích hoạt rồi dừng
B. Kích hoạt, hủy resource, rồi mới đọc manifest
C. Unload plugin trước khi xác minh compatibility
D. Dừng plugin trước khi cấp context khởi tạo
Đáp án đúng: A

Câu 10: Để tháo plugin an toàn, bước nào quan trọng?
A. Giữ thread nền và listener để tải plugin nhanh
B. Chỉ xóa file JAR trong lúc plugin đang chạy
C. Bỏ mọi trạng thái đang xử lý mà không thông báo
D. Hủy đăng ký callback và giải phóng tài nguyên
Đáp án đúng: D

Câu 11: Nguyên nhân nào khiến class loader plugin không được GC sau unload?
A. Thread hoặc listener còn giữ reference vào lớp plugin
B. Plugin đã tắt toàn bộ executor của chính mình
C. Plugin đã hủy đăng ký callback đúng thời điểm
D. Plugin không tạo bất kỳ object nào sau khi unload
Đáp án đúng: A

Câu 12: Nếu plugin phải gọi chức năng của host, cách liên kết nào phù hợp?
A. Đọc static field private của tất cả module lõi
B. Dùng reflection sửa mọi service singleton của host
C. Truy cập qua host context/interface được cấp
D. Truyền toàn bộ ApplicationContext cho mọi plugin
Đáp án đúng: C

Câu 13: Để phát hiện plugin không tương thích, manifest nên khai báo gì?
A. Chỉ tên máy của người biên dịch plugin
B. Chỉ kích thước file JAR đã upload lên server
C. Chỉ màu icon xuất hiện trên giao diện admin
D. Phiên bản API host và các capability bắt buộc
Đáp án đúng: D

Câu 14: Khi nâng cấp plugin mà hợp đồng API không còn tương thích, nên làm gì?
A. Ép gọi method cũ dù chữ ký đã thay đổi
B. Bỏ kiểm tra tương thích rồi hy vọng class load
C. Chặn tải hoặc dùng lớp adapter chuyển phiên bản
D. Tắt mọi plugin khác kể cả không liên quan
Đáp án đúng: C

Câu 15: Plugin từ bên thứ ba chạy cùng JVM có đặc điểm bảo mật nào?
A. Class loader tự tạo sandbox bảo mật tuyệt đối
B. SPI mặc định cấm plugin gọi file hoặc network
C. Cần xem là mã có quyền trong tiến trình host
D. Plugin tự bị giới hạn CPU và bộ nhớ hoàn toàn
Đáp án đúng: C

Câu 16: Nếu plugin cần đọc file, cách kiểm soát quyền nào phù hợp?
A. Cho phép đọc mọi thư mục chỉ vì đã cài JAR
B. Cấp quyền admin cho plugin để giảm lỗi tích hợp
C. Tắt audit khi plugin thao tác dữ liệu nhạy cảm
D. Cấp capability tối thiểu và xác nhận nguồn plugin
Đáp án đúng: D

Câu 17: Khi plugin lỗi trong callback, host nên xử lý ra sao?
A. Cho exception luôn làm hỏng mọi service lõi
B. Bỏ mọi log để plugin tự phục hồi ở lần sau
C. Tự xóa database để làm sạch trạng thái host
D. Ghi nhận lỗi và cô lập ảnh hưởng theo chính sách
Đáp án đúng: D

Câu 18: Vì sao callback plugin cần giới hạn tài nguyên hoặc timeout?
A. Để ép mọi callback luôn kết thúc trong 1 ns
B. Tránh plugin chậm làm nghẽn luồng xử lý của host
C. Để class loader bỏ qua kiểm tra chữ ký lớp
D. Để ứng dụng không cần log lỗi callback
Đáp án đúng: B

Câu 19: Khi hai plugin đăng ký xử lý cùng một event, host cần gì?
A. Chọn ngẫu nhiên plugin mỗi lần khởi động mà không log
B. Bỏ qua cả hai plugin để giảm phụ thuộc hệ thống
C. Để plugin tự sửa registry của nhau ở runtime
D. Quy tắc ưu tiên hoặc dispatch được xác định
Đáp án đúng: D

Câu 20: Một plugin có trạng thái lưu lâu dài qua nâng cấp cần quan tâm gì?
A. Phiên bản hóa dữ liệu và migration có kiểm soát
B. Luôn xóa trạng thái cũ khi có file JAR mới
C. Giữ serialVersionUID tùy ý rồi bỏ mọi thử nghiệm
D. Cho plugin mới truy cập trực tiếp mọi bảng hệ thống
Đáp án đúng: A

Câu 21: Vì sao cấu hình plugin nên được kiểm tra theo schema riêng?
A. Để plugin tự đọc mọi biến môi trường bí mật
B. Phát hiện sớm giá trị thiếu hoặc sai kiểu
C. Để bỏ bước validate khi host khởi động
D. Để cấm mọi plugin thay đổi cấu hình hợp lệ
Đáp án đúng: B

Câu 22: Plugin muốn bổ sung menu vào ứng dụng nên tương tác thế nào?
A. Ghi đè trực tiếp source code view controller
B. Đăng ký menu qua extension API của host
C. Thêm SQL trigger thay đổi template của host
D. Đổi tên package nội bộ của ứng dụng lõi
Đáp án đúng: B

Câu 23: Khi unit test plugin, cách nào giúp không phụ thuộc host thật?
A. Khởi động toàn bộ production trước mỗi assertion
B. Mock chính interface plugin rồi coi đã test plugin
C. Dùng fake host API và kiểm tra hành vi plugin
D. Chỉ kiểm tra file manifest mà bỏ mã thực thi
Đáp án đúng: C

Câu 24: Để xác minh plugin tuân thủ hợp đồng, suite test nên chứa gì?
A. Các ca tương thích, lỗi và vòng đời chuẩn
B. Chỉ số dòng source Java của từng plugin
C. Chỉ kết quả đo CPU máy đã phát triển plugin
D. Chỉ ảnh màn hình của trang tải plugin
Đáp án đúng: A

Câu 25: Với nhiều plugin có phụ thuộc nhau, host cần xử lý gì?
A. Xếp thứ tự tải dựa dependency và phát hiện chu trình
B. Tải tất cả ngẫu nhiên, không xét phụ thuộc plugin
C. Luôn khởi tạo plugin mới nhất trước mọi API host
D. Bỏ manifest và dùng tên file để suy ra tương thích
Đáp án đúng: A

Câu 26: Khi hot reload plugin, cách nào giảm rủi ro request gọi plugin đã unload?
A. Xóa ngay file JAR trong khi callback còn chạy
B. Ngừng dispatch, đợi tác vụ dở dang rồi thay registry
C. Thay class loader giữa chừng trong một invocation
D. Đổi tên plugin mà giữ listener và thread cũ
Đáp án đúng: B

Câu 27: Nếu một plugin gây lỗi khó tái hiện, host nên cung cấp thông tin nào?
A. Chỉ tổng số plugin được cài trong hệ thống
B. Chỉ tên host máy chạy mà bỏ thông tin plugin
C. Chỉ mã HTTP của mọi request không liên quan
D. Plugin ID, version, trace và lỗi vòng đời
Đáp án đúng: D

Câu 28: Đổi từ plugin nội bộ sang plugin do đối tác viết thường cần bổ sung điều gì?
A. Bỏ định nghĩa SPI vì đối tác được tự do sửa core
B. Cấp quyền đọc database cho mọi plugin đối tác
C. Review API, kiểm soát quyền và kiểm thử tương thích
D. Bắt mọi plugin dùng một singleton của toàn hệ thống
Đáp án đúng: C
