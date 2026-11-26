Trong dự án có nhiều người, formatter đem lại lợi ích trực tiếp nào?
A. Giảm số ca unit test cần viết cho module
B. Xác định độ phức tạp của từng nhánh mã
C. Ngăn build dùng thư viện đã lỗi thời
D. Giữ quy tắc trình bày mã nhất quán
Đáp án đúng: D

Muốn mọi IDE dùng cùng quy tắc thụt lề, nên lấy cấu hình từ đâu?
A. Đọc profile formatter lưu trong repository
B. Tùy chọn mặc định trên từng máy developer
C. Mẫu code riêng của từng người review
D. Cấu hình được cập nhật khi deploy production
Đáp án đúng: A

Vị trí dấu ngoặc nhọn trong Java nên được thống nhất như thế nào?
A. Theo vị trí mà mỗi developer thấy dễ đọc
B. Theo một formatter profile dùng chung và có version
C. Theo chiều dài của tên method trong từng lớp
D. Theo cấu hình mặc định từ từng phiên bản IDE
Đáp án đúng: B

EditorConfig phù hợp để đồng nhất những yếu tố nào giữa các IDE?
A. Danh sách các class được nạp ở runtime
B. Thụt lề, charset và kiểu kết thúc dòng
C. Ngưỡng complexity cùng duplication của CI
D. Chiến lược xử lý exception của service
Đáp án đúng: B

Khác biệt chính giữa formatter và linter mã Java là gì?
A. Formatter tìm vi phạm rule; linter chỉ sửa layout
B. Formatter tự sửa lỗi logic; linter chủ yếu xem style
C. Formatter chuẩn hóa layout; linter kiểm tra quy tắc
D. Formatter chọn severity; linter chỉ sắp xếp import
Đáp án đúng: C

Repository dùng cả Windows và Linux nên quản lý line ending thế nào?
A. Chấp nhận LF và CRLF lẫn nhau trong cùng file
B. Dùng encoding riêng của IDE cho mỗi lần commit
C. Để CI sửa line ending sau khi đã merge code
D. Đặt quy tắc line ending dùng chung trong repo
Đáp án đúng: D

Muốn giảm diff do IDE tự sắp xếp import Java, nên làm gì?
A. Thống nhất cách nhóm và thứ tự sắp import
B. Để IDE tự chuyển import sau mỗi lần save
C. Chỉ chỉnh import khi reviewer yêu cầu
D. Luôn đổi toàn bộ import thành wildcard
Đáp án đúng: A

Khi dòng Java dài vượt ngưỡng, cách ngắt dòng nào dễ duy trì nhất?
A. Chia dòng theo thói quen trong từng PR
B. Giữ toàn biểu thức trên một dòng dài
C. Ngắt theo profile formatter đã thống nhất
D. Đổi tên API public để tránh xuống dòng
Đáp án đúng: C

CI nên kiểm tra định dạng mã nguồn theo cách nào?
A. Tự sửa mã rồi commit trực tiếp vào main
B. Fail job khi mã khác kết quả formatter
C. Chạy formatter chỉ trên máy của reviewer
D. Cho phép pass dù tệp đang sai quy chuẩn
Đáp án đúng: B

PR vừa sửa bug vừa định dạng lại nhiều tệp sẽ dễ review hơn khi nào?
A. Tách thay đổi format khỏi thay đổi logic
B. Đưa tất cả khác biệt vào cùng một commit
C. Chạy lại formatter toàn repo ở mọi bugfix
D. Tắt formatter cho đến lần phát hành sau
Đáp án đúng: A

Mã hiện hữu chưa đồng nhất, cách áp dụng formatter an toàn là gì?
A. Buộc mọi bugfix định dạng lại tất cả module
B. Chỉ áp formatter trên máy của maintainer
C. Tắt toàn bộ format check cho mã nguồn mới
D. Áp formatter theo đợt với phạm vi rõ ràng
Đáp án đúng: D

Formatter thay đổi whitespace trong Java text block; cần rà soát điều gì?
A. Mặc định whitespace không tác động đến giá trị
B. Bỏ test vì formatter không thể đổi hành vi
C. Thay nội dung literal để tránh dòng quá dài
D. Rà literal và test xem giá trị có thay đổi
Đáp án đúng: D

Khi IDE và CI format khác nhau, bước khắc phục phù hợp là gì?
A. Giữ nguyên tùy chọn riêng của từng người
B. Tắt kiểm tra trên CI cho các tệp bị lệch
C. Pin phiên bản và dùng cùng cấu hình
D. Để reviewer quyết định chọn kết quả bất kỳ
Đáp án đúng: C

Muốn PR chỉ đổi định dạng dễ kiểm tra, nên làm gì trước merge?
A. Đổi cả format lẫn API trong cùng commit
B. Chạy trên phạm vi rõ ràng rồi rà diff
C. Chỉ nhìn số file được IDE tự động sửa
D. Tự merge vì format không ảnh hưởng hành vi
Đáp án đúng: B

Đưa quy chuẩn định dạng vào CI để không tái diễn lệch style, nên làm gì?
A. Commit cấu hình và chạy check trước merge
B. Chỉ thêm hướng dẫn vào mẫu mô tả PR
C. Để từng reviewer kiểm tra lại bằng mắt
D. Cho phép CI bỏ qua mọi khác biệt style
Đáp án đúng: A

Sau khi rebase, một nhánh xuất hiện xung đột định dạng; nên xử lý thế nào?
A. Ghép output của hai formatter khác nhau
B. Giữ nguyên whitespace của cả hai nhánh
C. Chạy formatter chuẩn rồi rà diff cuối
D. Bỏ format check vì nhánh đã từng pass
Đáp án đúng: C
