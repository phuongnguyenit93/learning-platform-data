1. Trước khi chạy security test trên hệ thống thật, cần xác lập điều gì?
A. Chỉ danh sách hostname tìm được từ công cụ quét
B. Chỉ thời điểm ít người dùng truy cập hệ thống nhất
C. Phạm vi được duyệt, đầu mối và giới hạn thử
D. Chỉ danh sách lỗ hổng từ báo cáo công khai gần đây
Đáp án đúng: C

2. Trong threat modeling, bước xác định trust boundary nhằm mục tiêu gì?
A. Chỉ liệt kê version thư viện sử dụng khi biên dịch
B. Tìm luồng dữ liệu vượt qua các mức tin cậy
C. Chỉ tính dung lượng lưu trữ của hệ thống production
D. Chỉ phát hiện các class không còn được ứng dụng dùng
Đáp án đúng: B

3. Khi lập threat model cho API chuyển tiền, cần ưu tiên xác định gì?
A. Chỉ kích thước response trung bình của endpoint
B. Chỉ số lượng test case có trong bộ kiểm thử API
C. Chỉ ngôn ngữ lập trình của dịch vụ gọi endpoint
D. Tài sản, luồng dữ liệu, tác nhân và điểm tin cậy
Đáp án đúng: D

4. Sự khác biệt chính giữa authentication và authorization là gì?
A. Xác thực chỉ dùng TLS; phân quyền chỉ dùng mật khẩu
B. Xác thực kiểm tra schema; phân quyền kiểm tra kiểu dữ liệu
C. Xác thực kiểm tra tốc độ; phân quyền kiểm tra độ trễ
D. Xác thực danh tính; phân quyền quyết định truy cập
Đáp án đúng: D

5. Nếu người A đọc được đơn hàng B bằng cách đổi orderId, cần kiểm tra gì?
A. Quyền truy cập từng đối tượng ở phía server
B. Chỉ xem định dạng UUID có hợp lệ hay không
C. Chỉ so thứ tự field trong JSON response trả về
D. Chỉ xác minh token chưa hết hạn tại trình duyệt
Đáp án đúng: A

6. Với API đa tenant, ca kiểm thử nào đánh giá tốt việc cô lập dữ liệu?
A. Dùng token tenant A yêu cầu tài nguyên của tenant B
B. Dùng token tenant A đọc tài nguyên thuộc chính tenant A
C. Dùng token tenant B gọi endpoint sức khỏe chung
D. Dùng token tenant B đăng xuất sau phiên hợp lệ
Đáp án đúng: A

7. Đối với endpoint chỉ dành cho admin, negative test phù hợp nhất là gì?
A. Thử quyền admin và xác minh trả đúng kết quả
B. Thử endpoint không tham số với quyền admin
C. Thử cùng endpoint trên hai phiên bản trình duyệt
D. Thử quyền user thường và xác minh bị từ chối
Đáp án đúng: D

8. Khi token truy cập đã hết hạn, kết quả an toàn mong đợi là gì?
A. Tự gia hạn mọi token hết hạn từ bất kỳ trình duyệt
B. Cho tiếp tục thao tác ghi nếu request đến trước đó
C. Chuyển quyền phiên thành admin để phục hồi kết nối
D. Từ chối thao tác đòi token còn hiệu lực
Đáp án đúng: D

9. Để kiểm tra chống brute force đăng nhập, cần quan sát cơ chế nào?
A. Giới hạn lần thử và báo hành vi đăng nhập lạ
B. Tăng thời hạn phiên sau mỗi lần mật khẩu nhập sai
C. Chỉ ghi số lần đăng nhập thành công trong một ngày
D. Vô hiệu hóa xác minh mật khẩu khi có tải cao
Đáp án đúng: A

10. Cấu hình cookie phiên nào hỗ trợ giảm nguy cơ lộ phiên?
A. Bỏ `Secure` để mọi giao thức đều nhận cookie
B. Dùng `Secure`, `HttpOnly`, `SameSite` thích hợp
C. Bỏ `HttpOnly` để mọi JavaScript có thể đọc token
D. Đặt `SameSite=None` mà không xét luồng xác thực
Đáp án đúng: B

11. Với endpoint thay đổi trạng thái dùng cookie, biện pháp nào giảm CSRF?
A. Chỉ dùng HTTP GET cho mọi thao tác thay đổi dữ liệu
B. Chỉ kiểm tra regex của trường body trong request
C. Xác minh CSRF token hoặc nguồn gửi phù hợp
D. Chỉ giảm độ dài session ID do trình duyệt cấp
Đáp án đúng: C

12. Khi kiểm thử logging, dấu hiệu nào là rò rỉ dữ liệu nhạy cảm?
A. Request ID không mang danh tính xuất hiện trong log
B. Token hoặc mật khẩu bị ghi nguyên văn ra log
C. Tên route được ghi để hỗ trợ giám sát lỗi HTTP
D. Mã trạng thái HTTP xuất hiện trong bản ghi truy cập
Đáp án đúng: B

13. Trong CI, một secret bị commit vào repository cần xử lý thế nào?
A. Chỉ xóa dòng secret khỏi nhánh hiện tại là đủ
B. Đổi tên biến chứa secret mà giữ nguyên giá trị cũ
C. Chỉ đặt file ở thư mục không có tên `secrets`
D. Xoay vòng secret và chặn lộ lại trong CI
Đáp án đúng: D

14. Khi kiểm tra API dùng HTTPS, điều gì cần được xác minh?
A. Chỉ endpoint có phản hồi nhanh hơn qua kết nối HTTP
B. Chỉ server có ít nhất một cổng mạng đang mở
C. Chỉ tên miền được lưu ở file cấu hình ứng dụng
D. Chứng chỉ hợp lệ và cấu hình TLS an toàn
Đáp án đúng: D

15. SAST thường phù hợp để phát hiện vấn đề bảo mật ở đâu?
A. Phân tích source hoặc bytecode mà không chạy ứng dụng
B. Trong giao diện HTTP đang chạy từ bên ngoài
C. Trong cấu hình firewall của mọi máy khách ngoài mạng
D. Trong báo cáo tốc độ mạng của trình sinh tải
Đáp án đúng: A

16. DAST khác SAST chủ yếu ở cách quan sát đối tượng nào?
A. Chỉ phân tích text của source chưa được biên dịch
B. Chỉ kiểm tra thư viện có phiên bản mới nhất hay không
C. Kiểm tra ứng dụng đang chạy qua các điểm tương tác
D. Chỉ đối chiếu sơ đồ dependency của các module
Đáp án đúng: C

17. SCA hữu ích nhất khi đánh giá rủi ro nào của dự án?
A. Thiếu kiểm tra phân quyền trong logic API tùy biến
B. Dữ liệu khách hàng bị log tại endpoint tự viết
C. Các lỗ hổng đã biết ở dependency của dự án
D. Sai quy tắc xử lý chiết khấu trong luồng thanh toán
Đáp án đúng: C

18. SBOM hỗ trợ công tác kiểm thử và ứng phó bảo mật bằng cách nào?
A. Thay thế toàn bộ kiểm thử phân quyền của ứng dụng
B. Liệt kê thành phần phần mềm để đối chiếu ảnh hưởng
C. Tự chứng minh mọi dependency đều không có lỗ hổng
D. Loại bỏ hoàn toàn nhu cầu cập nhật phiên bản thư viện
Đáp án đúng: B

19. Trong fuzzing API có kiểm soát, công cụ chủ yếu làm gì?
A. Gửi một input hợp lệ lặp mãi để đo throughput
B. So sánh ảnh chụp giao diện giữa hai bản release
C. Tạo input đa dạng để tìm lỗi xử lý trường hợp lạ
D. Chỉ quét tên package để tìm thư viện trùng phiên bản
Đáp án đúng: C

20. Vì sao vẫn cần kiểm thử thủ công sau quét tự động?
A. Vì SAST luôn bỏ sót tất cả lỗi dùng API HTTP
B. Xác minh ngữ cảnh và lỗi logic nghiệp vụ khó suy ra
C. Vì DAST luôn chỉ sinh kết quả kiểm thử giao diện
D. Vì SCA tự động kiểm tra mọi luồng nghiệp vụ ứng dụng
Đáp án đúng: B

21. Khi công cụ SAST báo một đường đi nguy hiểm, bước triage đúng là gì?
A. Đánh dấu lỗ hổng nghiêm trọng mà không kiểm tra
B. Tự bỏ mọi cảnh báo trước khi phát hành production
C. Xác minh đường dữ liệu và khả năng khai thác lỗi
D. Chỉ so tên checker với danh sách phiên bản plugin
Đáp án đúng: C

22. Ưu tiên sửa hai phát hiện bảo mật nên xét những yếu tố nào?
A. Chỉ thứ tự công cụ phát hiện các lỗ hổng trong log
B. Tác động, khả năng khai thác và mức phơi lộ
C. Chỉ số dòng code của các phương thức bị gắn cờ
D. Chỉ độ dài mô tả của từng phát hiện trong ticket
Đáp án đúng: B

23. Sau khi nhóm phát triển sửa lỗ hổng, kiểm chứng nào đủ chặt chẽ?
A. Chạy lại ca lỗi và regression ở luồng liên quan
B. Chỉ đóng ticket khi có commit mang nhãn sửa lỗi
C. Chỉ xem CI đã chạy biên dịch mà không có test
D. Chỉ đổi mức độ nghiêm trọng trong báo cáo cũ
Đáp án đúng: A

24. Tích hợp security test vào CI/CD hợp lý nhất bằng cách nào?
A. Chạy scan và test phù hợp, đặt gate có quản lý ngoại lệ
B. Chỉ chạy một công cụ bất kể loại rủi ro của hệ thống
C. Chỉ kiểm tra bảo mật sau khi đưa bản build ra production
D. Chỉ giữ log của lần scan mà không theo dõi remediation
Đáp án đúng: A
