Trong Java, tên lớp biểu diễn một khoản tiền nên dùng dạng nào?
A. Danh từ viết lowerCamelCase như tên biến
B. Danh từ viết UpperCamelCase như tên lớp
C. Danh từ viết UPPER_SNAKE_CASE như hằng
D. Danh từ viết kebab-case như tên đường dẫn
Đáp án đúng: B

Với hằng static final trong Java, kiểu định dạng tên nào phù hợp nhất?
A. RetryLimit thuộc dạng tên lớp UpperCamelCase
B. retryLimit thuộc dạng biến lowerCamelCase
C. retry-limit thuộc dạng segment kebab-case
D. RETRY_LIMIT thuộc dạng hằng UPPER_SNAKE_CASE
Đáp án đúng: D

Phương thức boolean cho biết tài khoản còn hoạt động nên đặt tên nào?
A. isActive()
B. activeStatus()
C. getActive()
D. accountActive()
Đáp án đúng: A

Ở dự án chia theo miền nghiệp vụ, package nên được tổ chức thế nào?
A. Theo framework được gọi thường xuyên nhất
B. Theo tính năng với ranh giới phụ thuộc rõ ràng
C. Theo hậu tố kỹ thuật của từng lớp Java
D. Theo cấu hình build của từng endpoint HTTP
Đáp án đúng: B

API chỉ cần các thao tác của danh sách nên nhận tham số kiểu nào?
A. ArrayList để ràng buộc cách lưu trữ phần tử
B. LinkedList để ràng buộc chi phí truy cập
C. List để chỉ công bố hợp đồng danh sách
D. Collection dù cần truy cập theo chỉ số
Đáp án đúng: C

Khi tầng service bổ sung ngữ cảnh cho lỗi dependency, cách nào phù hợp?
A. Ném exception phù hợp và giữ nguyên nhân gốc
B. Trả null để mọi tầng đều tự phát hiện lỗi
C. Bắt lỗi rồi bỏ qua cho luồng tiếp tục chạy
D. Chỉ ghi log và coi lỗi đã được khắc phục
Đáp án đúng: A

Trong API đọc Java, Optional nên được dùng trong trường hợp nào?
A. Làm thuộc tính bắt buộc trên mọi entity lưu trữ
B. Làm tham số đầu vào của mọi public method
C. Thay thế mọi collection khi không có phần tử
D. Làm kiểu trả về khi kết quả có thể vắng mặt
Đáp án đúng: D

Class giữ danh sách có thể thay đổi nên bảo vệ trạng thái nội bộ ra sao?
A. Trả tham chiếu gốc rồi yêu cầu caller không sửa
B. Để setter private nhưng trả nguyên mutable list
C. Sao chép phòng vệ khi nhận và trả danh sách
D. Đặt field final là đủ dù list vẫn thay đổi
Đáp án đúng: C

Theo hợp đồng equals/hashCode của Java, hai đối tượng bằng nhau cần gì?
A. Luôn phải sinh ra cùng một giá trị hashCode
B. Luôn phải cùng số field đã được khai báo
C. Luôn phải tạo hai hash khác để tránh va chạm
D. Luôn phải là đúng một instance trong bộ nhớ
Đáp án đúng: A

Một method vừa validate, map dữ liệu vừa lưu DB nên cải thiện thế nào?
A. Thêm comment cho từng khối và giữ nguyên
B. Chuyển cả ba bước sang constructor của lớp
C. Tách thành hàm theo trách nhiệm có tên rõ
D. Dồn ba bước vào helper dùng chung toàn app
Đáp án đúng: C

Khi nào nên bắt một exception thay vì truyền tiếp nó?
A. Khi cần ẩn mọi lỗi bằng một giá trị mặc định
B. Khi có thể phục hồi hoặc bổ sung ngữ cảnh
C. Khi muốn mọi lỗi thành một mã boolean chung
D. Khi cần đổi mọi lỗi sang IllegalArgumentException
Đáp án đúng: B

JavaDoc của public API nên ưu tiên mô tả điều gì?
A. Hợp đồng sử dụng, điều kiện đầu vào và lỗi
B. Toàn bộ lệnh theo đúng thứ tự trong method
C. Mỗi biến cục bộ được tạo trong implementation
D. Các bước chạy thay cho các bài kiểm thử
Đáp án đúng: A

Khi viết unit test cho quy tắc giảm giá, tiêu chí nào có ích nhất?
A. Kiểm chứng số lượng lệnh trong thân phương thức
B. Kiểm chứng tên test khớp quy chuẩn chữ hoa
C. Kiểm chứng chỉ mock chính lớp đang cần test
D. Kiểm chứng kết quả ở ca thường và ca biên
Đáp án đúng: D

PR vừa sửa bug vừa định dạng lại hàng trăm tệp nên tổ chức thay đổi ra sao?
A. Tắt hoàn toàn formatter cho nhánh sửa bug
B. Áp lại formatter cho toàn repo ở mỗi commit
C. Trộn hết thay đổi để giảm số commit cần đọc
D. Tách thay đổi định dạng khỏi thay đổi hành vi
Đáp án đúng: D

Muốn quy chuẩn mã Java được kiểm tra lặp lại trên CI, nên làm gì?
A. Chạy formatter thủ công vào cuối mỗi đợt release
B. Chỉ thêm checklist đặt tên vào mô tả pull request
C. Chạy rule bằng cấu hình được lưu cùng repository
D. Chặn mọi cảnh báo dù chưa có cách phân loại lỗi
Đáp án đúng: C

Khi áp quy chuẩn mới lên mã cũ có nhiều ngoại lệ, cách quản trị nào phù hợp?
A. Buộc định dạng toàn bộ repo trước mọi bản vá
B. Ghi rõ lý do, người phụ trách và kỳ rà soát
C. Hoãn tất cả quy tắc đến lần viết lại hệ thống
D. Cho phép bỏ qua rule tùy ý mà không ghi nhận
Đáp án đúng: B
