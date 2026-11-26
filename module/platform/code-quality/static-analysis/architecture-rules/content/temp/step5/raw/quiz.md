Câu 1. Với kiến trúc web/application/domain, hướng phụ thuộc nào thường hợp lệ?
A. Domain service import trực tiếp controller web
B. Entity nghiệp vụ phụ thuộc DTO tầng REST
C. Repository domain gọi view template của web
D. Controller gọi application service để xử lý
Đáp án đúng: D

Câu 2. Lợi ích chính khi dùng ArchUnit cho ràng buộc kiến trúc là gì?
A. Tự sinh toàn bộ module từ sơ đồ kiến trúc
B. Đưa luật phụ thuộc vào kiểm thử tự động
C. Thay compiler để chạy bytecode nhanh hơn
D. Tự cập nhật thư viện theo mỗi bản release
Đáp án đúng: B

Câu 3. ArchUnit chủ yếu tìm quan hệ phụ thuộc Java từ dữ liệu nào?
A. Bytecode các lớp được importer nạp vào
B. Nhật ký HTTP của ứng dụng đang chạy
C. Sơ đồ sequence do nhóm thiết kế vẽ
D. Báo cáo coverage do unit test xuất ra
Đáp án đúng: A

Câu 4. Quy tắc cấm domain phụ thuộc web nhằm bảo vệ điều gì?
A. Domain chỉ có thể chứa các lớp immutable
B. Logic nghiệp vụ không phụ thuộc giao diện
C. Controller không được gọi service nghiệp vụ
D. Mọi lớp web phải chuyển thành interface
Đáp án đúng: B

Câu 5. Muốn bắt buộc tên lớp controller kết thúc bằng Controller, dùng kiểu rule nào?
A. Rule đo thời gian thực thi của controller
B. Rule đếm số request đã qua controller
C. Rule kiểm tra quy ước tên của các lớp
D. Rule phát hiện chu trình giữa các module
Đáp án đúng: C

Câu 6. Vì sao có sơ đồ kiến trúc vẫn cần kiểm tra tự động trong CI?
A. Sơ đồ luôn khớp mã vì có source control
B. Sơ đồ thay thế được mọi bài kiểm thử API
C. Sơ đồ đảm bảo Java compiler chặn mọi import
D. Sơ đồ không tự bắt phụ thuộc mới trong mã
Đáp án đúng: D

Câu 7. Các package A, B, C phụ thuộc theo vòng A đến B đến C đến A. Rule nào phù hợp?
A. Kiểm tra thứ tự alphabet của tên package
B. Kiểm tra số dòng Java trong mỗi package
C. Kiểm tra chu trình phụ thuộc giữa các slice
D. Kiểm tra quyền đọc tệp cấu hình runtime
Đáp án đúng: C

Câu 8. Để luật ArchUnit kiểm tra đủ các lớp mục tiêu, điều gì quan trọng?
A. Nạp đúng phạm vi package vào importer
B. Chỉ chạy thử với lớp được đổi gần đây
C. Bỏ các lớp đã biên dịch khỏi classpath
D. Chỉ import các interface của tầng domain
Đáp án đúng: A

Câu 9. Khi rule phân tầng dựa vào đường dẫn package, rủi ro nào cần nhớ?
A. Package quyết định ngôn ngữ bytecode Java
B. Đặt sai package có thể làm sai phân loại lớp
C. Package luôn thay đổi theo tên file JAR
D. Package tự điều chỉnh sau mỗi lần chạy test
Đáp án đúng: B

Câu 10. Vì sao lớp Java public chưa chắc là API công khai của module?
A. Public chỉ có ý nghĩa ở bên trong unit test
B. Mọi public class đều bắt buộc triển khai SPI
C. Từ khóa public chỉ hợp lệ trong package web
D. Quyền truy cập Java khác ranh giới API module
Đáp án đúng: D

Câu 11. Cách nào kiểm soát client không dùng implementation nội bộ của module?
A. Giới hạn phụ thuộc ngoài vào package API
B. Cho client import mọi lớp có chữ public
C. Sao chép lớp implementation sang client
D. Chuyển mọi interface thành lớp private
Đáp án đúng: A

Câu 12. Architecture test nên được gắn vào build Maven hoặc Gradle như thế nào?
A. Chỉ chạy khi hệ thống đã vào production
B. Chạy sau deploy, bỏ qua kết quả trong CI
C. Chỉ chạy thủ công khi kiến trúc thay đổi
D. Chạy cùng test và làm build lỗi nếu vi phạm
Đáp án đúng: D

Câu 13. Dự án cũ có nhiều vi phạm kiến trúc; cách triển khai rule từng bước là gì?
A. Bỏ toàn bộ rule nếu một lớp đang vi phạm
B. Sửa package bằng đổi tên mà không chạy test
C. Ghi baseline hiện trạng, chặn vi phạm mới
D. Chấp nhận mọi vi phạm cho đến kỳ release
Đáp án đúng: C

Câu 14. Một ngoại lệ phụ thuộc kiến trúc nên được quản lý như thế nào?
A. Giấu ngoại lệ vào một rule bỏ qua mọi lớp
B. Ghi rõ phạm vi, lý do và điều kiện gỡ bỏ
C. Cho mọi module dùng chung ngoại lệ rộng
D. Bỏ qua ngoại lệ mà không để lại dấu vết
Đáp án đúng: B

Câu 15. Vì sao build đa module không tự thay thế mọi rule ArchUnit?
A. Compiler không thể phát hiện lỗi cú pháp Java
B. Module build luôn có chung classpath runtime
C. Ranh giới package có thể cần luật chặt hơn
D. Maven và Gradle không chạy được unit test
Đáp án đúng: C

Câu 16. Domain định nghĩa interface lưu trữ, adapter cơ sở dữ liệu triển khai interface. Ý nghĩa gì?
A. Phụ thuộc hướng vào abstraction của domain
B. Domain phải khởi tạo adapter khi ứng dụng mở
C. Database tự quyết định cấu trúc logic domain
D. Mỗi adapter phải import controller của web
Đáp án đúng: A

Câu 17. Một rule chỉ kiểm tra phụ thuộc trực tiếp có hạn chế nào?
A. Luôn phát hiện mọi lỗi dữ liệu ở runtime
B. Không phân biệt được class và interface Java
C. Tự động tính được độ trễ của toàn hệ thống
D. Chưa kết luận được mọi phụ thuộc gián tiếp
Đáp án đúng: D

Câu 18. Khi CI báo domain tham chiếu một lớp infrastructure trái luật, nên làm gì?
A. Xem chuỗi phụ thuộc và sửa hướng tham chiếu
B. Tắt rule để giữ build xanh cho mọi nhánh
C. Thêm phụ thuộc ngược từ infrastructure vào web
D. Đổi tên package mà không xem luồng gọi thật
Đáp án đúng: A

Câu 19. Kiểm tra chu trình phụ thuộc giúp nhóm nhận ra điều gì?
A. Module nào tiêu thụ nhiều CPU nhất khi chạy
B. Nhóm package khóa nhau khiến sửa đổi lan rộng
C. Package nào có ít phương thức public hơn
D. Tệp resource nào bị thiếu ở runtime build
Đáp án đúng: B

Câu 20. Ngoài phụ thuộc, ArchUnit có thể kiểm tra quy tắc nào về lớp?
A. Quy tắc đặt tên và phạm vi truy cập lớp
B. Mức sử dụng RAM trong mỗi request web
C. Thời gian query trả về ở môi trường thật
D. Số giao dịch bị rollback khi chạy load test
Đáp án đúng: A

Câu 21. Architecture test có thể thay thế hoàn toàn kiểm thử hành vi không?
A. Có, mọi logic đều suy được từ đồ thị package
B. Có, compiler đã bao phủ toàn bộ nghiệp vụ
C. Không, kiến trúc và hành vi là hai mục tiêu
D. Có, nếu các package đều đạt luật phụ thuộc
Đáp án đúng: C

Câu 22. Một rule báo không có lớp nào thuộc phạm vi kiểm tra. Phản ứng hợp lý là gì?
A. Xem đây là bằng chứng module đã đúng thiết kế
B. Đổi rule thành cho phép mọi lớp phụ thuộc nhau
C. Xóa rule vì chương trình đã compile thành công
D. Kiểm tra mẫu package và phạm vi import lớp
Đáp án đúng: D

Câu 23. Để module khác chỉ dùng các lớp thuộc gói API, rule nào hợp lý nhất?
A. Cấm mọi lớp trong module có phương thức public
B. Cấm client phụ thuộc package implementation
C. Buộc mọi class có hậu tố Service hoặc Controller
D. Buộc các module cùng dùng một package tên chung
Đáp án đúng: B

Câu 24. Khi kiến trúc phát triển qua nhiều phiên bản, làm sao tránh rule bị bỏ quên?
A. Xóa rule cũ sau khi hoàn thành lần đầu
B. Chỉ review luật khi phát sinh lỗi production
C. Review rule theo thiết kế và chạy trên mỗi PR
D. Chỉ kiểm tra luật trong máy một lập trình viên
Đáp án đúng: C
