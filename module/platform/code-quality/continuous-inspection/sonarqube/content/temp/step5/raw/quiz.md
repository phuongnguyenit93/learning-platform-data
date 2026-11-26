Để SonarQube phân tích chính xác mã Java, đầu ra build nào thường cần có?
A. Báo cáo Markdown mô tả kiến trúc package
B. Danh sách thư viện được viết trong README
C. Bytecode Java tương ứng với mã nguồn
D. Lịch sử commit và nhãn release từ Git
Đáp án đúng: C

Dự án Maven muốn phân tích SonarQube trong CI nên tích hợp theo cách nào?
A. Tải thủ công file JAR sau mỗi lần release
B. Chỉ gửi log Maven lên dashboard phân tích
C. Mở IDE trên CI runner rồi bấm phân tích
D. Chạy goal Sonar trong job Maven của CI
Đáp án đúng: D

Trong kiến trúc SonarQube, scanner và server đảm nhiệm việc nào?
A. Scanner phân tích; server tổng hợp và hiển thị
B. Scanner lưu dashboard; server chỉ tải source Git
C. Server biên dịch Java; scanner chỉ chạy unit test
D. Server cập nhật Git; scanner giữ toàn bộ metrics
Đáp án đúng: A

Khi đánh giá một PR trong SonarQube, cách nào tập trung vào chất lượng mã mới?
A. Dùng điều kiện Quality Gate gắn với New Code
B. Dùng tổng số issue cũ của toàn bộ repository
C. Dùng số commit đã có trong lịch sử nhánh chính
D. Dùng số file được scan kể từ đợt release
Đáp án đúng: A

Trong SonarQube, Quality Profile điều khiển thành phần nào?
A. Ngưỡng coverage quyết định trạng thái merge
B. Bộ rule Java được bật khi phân tích source
C. Quyền truy cập dashboard của người dùng
D. Thời gian chạy từng job trên pipeline CI
Đáp án đúng: B

Quality Gate trong SonarQube có mục đích chính nào?
A. Chọn compiler version cho module Java
B. Chọn SDK được cài trên các runner CI
C. So metric với ngưỡng để xét đạt hay trượt
D. Khóa phiên bản thư viện trong Maven POM
Đáp án đúng: C

Khi cấu hình New Code, phạm vi mã mới được xác định bằng điều gì?
A. Toàn bộ các dòng trong mọi version của repo
B. Chỉ những file vừa thêm vào cấu hình Gradle
C. Chỉ mã đã được formatter sửa ở nhánh PR
D. Mã mới theo mốc tham chiếu được cấu hình
Đáp án đúng: D

Để hiển thị coverage kiểm thử Java trong SonarQube, cần cung cấp dữ liệu nào?
A. Log các lệnh chạy unit test trong build
B. Báo cáo coverage do bộ test tạo ra
C. Số lượng assertion được viết trong test
D. Danh sách endpoint đã gọi lúc biên dịch
Đáp án đúng: B

Sau khi đổi Quality Profile, số issue tăng; cách diễn giải nào phù hợp?
A. Số issue tăng chứng tỏ code mới đã phát sinh lỗi
B. Scanner đổi kết quả vì các bài test chạy chậm
C. Bộ rule đã đổi nên cần đối chiếu các cảnh báo
D. Tất cả issue mới đều là false positive mặc định
Đáp án đúng: C

Một Security Hotspot trong SonarQube cần được xử lý theo hướng nào?
A. Rà ngữ cảnh để xác định rủi ro thực
B. Xử lý như lỗi runtime đã được tái hiện
C. Tăng coverage rồi đóng cảnh báo ngay lập tức
D. Mặc định coi là lỗ hổng đã được xác nhận
Đáp án đúng: A

Khi một issue được nghi là false positive, nên làm gì?
A. Tắt rule liên quan trên toàn bộ dự án
B. Loại luôn cả package khỏi lần phân tích
C. Bỏ trạng thái issue bằng cách xóa test
D. Xác minh mã rồi ghi rõ lý do đánh dấu
Đáp án đúng: D

Chỉ số duplication của SonarQube phản ánh điều nào?
A. Các file có danh sách import tương tự nhau
B. Các method dùng chung một kiểu trả về
C. Các bài test dùng cùng kiểu annotation
D. Các khối mã lặp được công cụ nhận diện
Đáp án đúng: D

Muốn CI từ chối thay đổi khi Quality Gate fail, pipeline cần làm gì?
A. Chờ Quality Gate rồi fail job khi trượt
B. Chỉ chờ scanner gửi xong báo cáo lên server
C. Chỉ so độ phủ kiểm thử trước khi cho merge
D. Coi scanner chạy xong là Quality Gate pass
Đáp án đúng: A

Token phân tích SonarQube được dùng trong CI nên được lưu thế nào?
A. Ghi token vào source để mọi reviewer nhìn thấy
B. Lưu trong CI secrets với quyền tối thiểu
C. Đưa token vào log build để dễ đối chiếu
D. Dùng token cá nhân chung cho nhiều repository
Đáp án đúng: B

Khi source sinh tự động gây cảnh báo nhiễu, cách cấu hình phù hợp là gì?
A. Bỏ hoàn toàn rule cho mọi nguồn Java trong repo
B. Đánh false positive cho mọi issue toàn dự án
C. Giới hạn exclusion đúng vùng code sinh tự động
D. Tắt Quality Gate trên tất cả các branch CI
Đáp án đúng: C

Trước khi nâng cấp máy chủ SonarQube, cần chuẩn bị điều gì?
A. Xóa lịch sử issue trước khi cập nhật schema
B. Sao lưu, kiểm tra tương thích và thử nâng cấp
C. Đổi project key để bắt đầu phân tích lại từ đầu
D. Tắt tất cả Quality Profile trước mỗi lần backup
Đáp án đúng: B
