Câu 1. Khi gửi dữ liệu giữa hai tiến trình, serialization thực hiện bước nào?
A. Chuyển dữ liệu đầu vào thành khóa mã hóa bí mật
B. Chuyển giao địa chỉ heap của đối tượng qua mạng
C. Chuyển dữ liệu có cấu trúc thành lệnh SQL truy vấn
D. Chuyển dữ liệu có cấu trúc sang định dạng truyền
Đáp án đúng: D

Câu 2. Khác biệt đúng giữa Unicode code point và byte trong UTF-8 là gì?
A. Một code point luôn đúng một byte UTF-8
B. Một code point có thể cần nhiều byte
C. Byte luôn tương ứng với một ký tự nhìn thấy
D. UTF-8 chỉ mã hóa các code point ASCII
Đáp án đúng: B

Câu 3. Với UTF-8, nhận định nào chính xác về độ dài mã hóa một code point hợp lệ?
A. Một code point hợp lệ cần 1 đến 4 byte
B. Mỗi code point luôn được mã hóa bằng đúng 2 byte
C. Mỗi code point luôn được mã hóa bằng đúng 4 byte
D. Mỗi code point phải dùng một số byte cố định
Đáp án đúng: A

Câu 4. Khi trao đổi số nguyên 32 bit ở định dạng nhị phân, endianness quyết định gì?
A. Thứ tự các bit bên trong một byte đơn lẻ
B. Thứ tự byte của giá trị nhiều byte
C. Số bit biểu diễn dấu của số nguyên
D. Kiểu checksum đính kèm vào bản tin
Đáp án đúng: B

Câu 5. Trong JSON, hai giá trị 42 và "42" khác nhau cơ bản ở điểm nào?
A. Cả hai đều là string sau khi được parser đọc
B. Giá trị 42 luôn là một Boolean trong cấu trúc
C. Một giá trị là number, giá trị kia là string
D. Giá trị "42" luôn được parser tự chuyển thành số
Đáp án đúng: C

Câu 6. Một tài liệu JSON chuẩn có thể chứa chú thích dạng // trong văn bản không?
A. Có, nếu chú thích được đặt sau dấu phẩy
B. Có, nếu chú thích chỉ xuất hiện ở dòng cuối
C. Có, nếu chú thích nằm trong một mảng JSON
D. Không, JSON chuẩn không có cú pháp chú thích
Đáp án đúng: D

Câu 7. Vì sao cần phân biệt trường JSON bị thiếu và trường có giá trị null?
A. Vì trường thiếu luôn tự tạo giá trị số bằng không
B. Vì null luôn mang nghĩa chuỗi ký tự rỗng
C. Vì hai trạng thái có thể mang ngữ nghĩa khác nhau
D. Vì trường thiếu luôn khiến toàn bộ JSON không hợp lệ
Đáp án đúng: C

Câu 8. Trong XML, namespace giúp xử lý trường hợp nào?
A. Tránh xung đột tên phần tử giữa các bộ từ vựng
B. Biến mọi thuộc tính XML thành giá trị số nguyên
C. Bắt mọi phần tử XML dùng chung một tên cục bộ
D. Thay thế hoàn toàn việc kiểm tra schema tài liệu
Đáp án đúng: A

Câu 9. Với CSV có dấu phẩy làm delimiter, một ô chứa dấu phẩy thường được ghi thế nào?
A. Đổi dấu phẩy trong nội dung thành dấu chấm
B. Bao trường bằng dấu nháy theo quy tắc CSV
C. Chia trường thành hai cột không có dấu nháy
D. Đặt ký tự tab ở đầu mỗi dòng cần xử lý
Đáp án đúng: B

Câu 10. Khi đọc YAML không tin cậy bằng thư viện có khả năng dựng đối tượng, lựa chọn an toàn nào phù hợp?
A. Cho phép tự khởi tạo mọi lớp qua tag tùy ý
B. Bỏ mọi giới hạn độ sâu và kích thước tài liệu
C. Tự động chạy constructor của các tag không biết
D. Dùng safe loader và giới hạn kiểu dữ liệu
Đáp án đúng: D

Câu 11. Lợi thế thường gặp của định dạng serialization nhị phân có schema là gì?
A. Biểu diễn gọn và ánh xạ trường có quy tắc rõ
B. Luôn cho phép đọc bằng mắt mà không cần công cụ
C. Không bao giờ cần lưu mô tả schema qua phiên bản
D. Luôn tương thích mọi thay đổi kiểu dữ liệu tùy ý
Đáp án đúng: A

Câu 12. Một phiên bản mới thêm trường optional vào bản tin. Khi nào reader cũ dễ tiếp tục đọc được?
A. Khi schema mới đổi nghĩa mọi trường cũ
B. Khi reader cũ buộc phải hiểu mọi trường mới
C. Khi tất cả trường cũ bị đổi ID để tránh trùng
D. Khi reader cũ có thể bỏ qua trường lạ
Đáp án đúng: D

Câu 13. Backward compatibility trong trao đổi dữ liệu thường có ý nghĩa nào?
A. Reader cũ đọc được dữ liệu do writer mới tạo
B. Writer cũ bắt buộc hiểu schema của writer mới
C. Reader mới đọc được dữ liệu writer cũ đã tạo
D. Writer mới phải phát đúng byte như writer cũ
Đáp án đúng: C

Câu 14. Kiểm thử round-trip serialize rồi deserialize nên kiểm tra điều gì?
A. Chuỗi byte đầu ra luôn trùng từng byte với input
B. Giá trị đọc lại tương đương về ngữ nghĩa
C. Mọi định dạng đều giữ nguyên thứ tự khóa JSON
D. Bộ parser luôn sinh lại cùng địa chỉ đối tượng
Đáp án đúng: B

Câu 15. Khi serialize một mốc thời gian cần chia sẻ liên hệ múi giờ, cách làm nào hợp lý?
A. Chỉ ghi tên ngày trong tuần mà bỏ giờ phút giây
B. Ghi thời gian máy cục bộ nhưng bỏ mọi thông tin zone
C. Dùng định dạng thời gian rõ UTC hoặc offset
D. Chuyển mọi timestamp thành số giây trong một ngày
Đáp án đúng: C

Câu 16. Khi API cho phép partial update, việc phân biệt missing field với explicit null giúp gì?
A. Phân biệt không sửa với yêu cầu xóa một giá trị
B. Buộc mọi trường không xuất hiện phải mang số 0
C. Bảo đảm mọi trường nullable đều được ghi đè
D. Loại bỏ hoàn toàn nhu cầu định nghĩa hợp đồng API
Đáp án đúng: A

Câu 17. Vì sao streaming parser có lợi khi đọc tệp JSON rất lớn?
A. Parser sẽ luôn giữ toàn bộ cây tài liệu trong RAM
B. Parser chỉ có thể đọc các tệp định dạng nhị phân
C. Parser buộc các object JSON có cùng số trường
D. Parser xử lý từng phần mà không giữ cả cây
Đáp án đúng: D

Câu 18. Khi nhận dữ liệu serialization từ client, hạn chế độ sâu và kích thước giúp giảm nguy cơ gì?
A. Giảm tiêu thụ tài nguyên do payload độc hại
B. Tăng tốc mọi thuật toán xuống thời gian hằng
C. Bỏ hoàn toàn mọi lỗi do phiên bản schema khác
D. Thay thế nhu cầu phân quyền trên các endpoint
Đáp án đúng: A

Câu 19. Vì sao việc deserialize Java ObjectInputStream từ nguồn không tin cậy nguy hiểm?
A. Vì Java Serialization không hỗ trợ đối tượng có trường
B. Vì quá trình dựng đối tượng có thể gọi gadget
C. Vì ObjectInputStream chỉ có thể đọc JSON và XML
D. Vì Java Serialization tự xác thực mọi payload đầu vào
Đáp án đúng: B

Câu 20. Trong Java Serialization, serialVersionUID thường dùng nhằm mục đích nào?
A. Đối chiếu phiên bản khi đọc lớp đã serialize
B. Mã hóa dữ liệu thành bản tin bí mật theo một khóa
C. Tự sinh mã định danh duy nhất cho mọi instance
D. Định nghĩa thứ tự các trường trong toàn bộ JSON
Đáp án đúng: A

Câu 21. Với cơ chế Java default serialization, thuộc tính instance đánh dấu transient có hành vi nào?
A. Luôn được ghi ra cùng các thuộc tính bình thường
B. Được ghi ra nhưng dưới dạng trường bí mật
C. Bị bỏ qua khi serialize mặc định đối tượng
D. Tự được ghi trở lại bằng giá trị runtime mới
Đáp án đúng: C

Câu 22. Nếu buộc phải nhận Java serialized data từ nguồn hạn chế, biện pháp nào giảm rủi ro?
A. Chấp nhận mọi class vì đã có serialVersionUID
B. Đọc mà không giới hạn số lượng đối tượng lồng
C. Chuyển cảnh báo deserialization thành log thông thường
D. Áp dụng ObjectInputFilter với giới hạn cụ thể
Đáp án đúng: D

Câu 23. Trước khi đưa dữ liệu đã deserialize vào xử lý nghiệp vụ, kiểm tra nào cần thiết?
A. Chỉ kiểm tra chuỗi JSON có thụt đầu dòng chuẩn
B. Kiểm tra kiểu, trường bắt buộc và giới hạn giá trị
C. Chỉ đảm bảo tên file truyền tải có phần mở rộng đúng
D. Kiểm tra thứ tự khóa trong đối tượng sau khi parse
Đáp án đúng: B

Câu 24. Checksum gắn với payload được dùng phù hợp nhất để làm gì?
A. Xác thực chắc chắn tác giả trước đối thủ chủ động
B. Ngăn hoàn toàn thay đổi dữ liệu do người dùng gửi
C. Phát hiện lỗi dữ liệu khi truyền tải hoặc lưu trữ
D. Thay thế việc kiểm thử tương thích phiên bản schema
Đáp án đúng: C
