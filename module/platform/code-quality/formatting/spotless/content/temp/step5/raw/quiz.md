Câu 1. Khi CI chỉ cần phát hiện mã Java sai định dạng, thao tác nào phù hợp nhất?
A. Chạy spotlessApply rồi commit thay đổi
B. Chạy spotlessCheck để phát hiện lệch
C. Chạy test và bỏ qua kiểm tra định dạng
D. Chạy compileJava để tự sửa định dạng
Đáp án đúng: B

Câu 2. Muốn Spotless ghi lại các tệp Java theo cấu hình Gradle, cần chạy tác vụ nào?
A. spotlessCheck để báo các tệp không đạt
B. test để áp dụng lại các quy tắc kiểu
C. compileJava để ghi mã đã chuẩn hóa
D. spotlessApply để lưu định dạng mới
Đáp án đúng: D

Câu 3. Lệnh Maven nào kiểm tra định dạng bằng Spotless mà không tự sửa tệp?
A. mvn spotless:apply để ghi sửa đổi
B. mvn spotless:check để kiểm tra
C. mvn test để cập nhật định dạng mã
D. mvn package để thay thế mã nguồn
Đáp án đúng: B

Câu 4. Trong Gradle, nơi nào thường chứa cấu hình formatter dành riêng cho Java?
A. Khối sourceSets của tác vụ biên dịch
B. Khối dependencies của cấu hình build
C. Khối java bên trong cấu hình spotless
D. Khối repositories của dự án Java
Đáp án đúng: C

Câu 5. Vì sao nhóm nên chốt phiên bản formatter trong cấu hình Spotless?
A. Để tự động chọn JDK mới nhất ở CI
B. Để tránh phải khai báo đích định dạng
C. Để mọi máy bỏ qua khác biệt mã nguồn
D. Để cùng đầu vào cho cùng kết quả format
Đáp án đúng: D

Câu 6. Hai máy định dạng cùng dự án khác nhau dù cùng dùng Spotless. Cách xử lý ưu tiên là gì?
A. Đồng bộ phiên bản và cấu hình formatter
B. Tắt kiểm tra ở máy không giống CI
C. Chạy formatter thủ công theo từng IDE
D. Chỉ format những tệp bị thay đổi gần đây
Đáp án đúng: A

Câu 7. Phân biệt đúng hai bước importOrder và removeUnusedImports là gì?
A. Cả hai bước đều chỉ sắp xếp import
B. Cả hai bước đều chỉ xóa import dư
C. Một bước sắp thứ tự, một bước xóa dư
D. Một bước đổi package, một bước tạo import
Đáp án đúng: C

Câu 8. Khi cấu hình nhiều bước biến đổi Java, điều gì giúp kết quả lặp lại ổn định?
A. Giữ cố định thứ tự các bước xử lý
B. Đảo thứ tự các bước giữa các lần chạy
C. Dùng bước khác nhau trên máy và CI
D. Bỏ bước quản lý import khi chạy CI
Đáp án đúng: A

Câu 9. Muốn Spotless chỉ xử lý tệp Java trong một cây thư mục, nên cấu hình gì?
A. Chỉ đổi phiên bản của Java formatter
B. Thêm tùy chọn cho tác vụ kiểm thử
C. Đặt target bằng mẫu đường dẫn phù hợp
D. Đặt cấu hình trong khối dependencies
Đáp án đúng: C

Câu 10. Mã Java do công cụ sinh ra liên tục thay đổi; cách quản lý Spotless hợp lý là gì?
A. Đưa toàn bộ mã sinh ra vào formatter
B. Loại trừ tệp sinh tự động khỏi target
C. Đổi formatter mỗi lần chạy sinh mã
D. Chỉ áp dụng quy tắc import cho mã sinh
Đáp án đúng: B

Câu 11. Trong Gradle đa module, cách nào giúp các module Java tuân cùng quy tắc?
A. Áp dụng cấu hình Spotless chung cho module cần
B. Chỉ khai báo formatter ở module khởi chạy
C. Để từng module tự chọn formatter riêng lẻ
D. Chạy tác vụ định dạng ở duy nhất root project
Đáp án đúng: A

Câu 12. Với Maven, khai báo trong pluginManagement có đủ để tự chạy goal ở mọi module không?
A. Có, goal chạy khi khai báo phiên bản plugin
B. Không, cần kích hoạt plugin ở module cần chạy
C. Có, dependencyManagement gọi goal thay plugin
D. Có, mọi pluginManagement tự tạo execution
Đáp án đúng: B

Câu 13. Khi IDE dùng formatter khác cấu hình Spotless, nhóm nên làm gì?
A. Tắt Spotless cho mọi thay đổi từ IDE
B. Chấp nhận hai kiểu định dạng trên nhánh
C. Chạy CI chỉ với tệp đã chỉnh trên IDE
D. Đồng bộ formatter của IDE với dự án
Đáp án đúng: D

Câu 14. Trong pipeline CI, vị trí phù hợp của Spotless là gì?
A. Chạy check, báo lỗi khi định dạng lệch
B. Chạy apply rồi commit trực tiếp lên nhánh
C. Chỉ chạy apply sau khi phát hành sản phẩm
D. Bỏ qua check nếu mã vẫn biên dịch được
Đáp án đúng: A

Câu 15. Khi lần đầu áp dụng Spotless vào mã cũ, cách giảm nhiễu trong code review là gì?
A. Đổi formatter trong mọi pull request mới
B. Gộp đổi định dạng cùng sửa lỗi nghiệp vụ
C. Chỉ format những tệp đang bị CI báo lỗi
D. Tách đổi format khỏi thay đổi logic
Đáp án đúng: D

Câu 16. Bước licenseHeader trong Spotless thường được dùng để làm gì?
A. Tự tải giấy phép thư viện phụ thuộc
B. Đổi phiên bản giấy phép của project
C. Thêm hoặc chuẩn hóa header theo mẫu
D. Kiểm tra quyền truy cập repository
Đáp án đúng: C

Câu 17. Cấu hình xuống dòng cuối tệp và kiểu line ending giúp ích gì cho nhóm?
A. Giảm diff do khác biệt quy tắc xuống dòng
B. Thay đổi mã hóa thành bytecode tối ưu hơn
C. Bảo đảm mọi cảnh báo compiler biến mất
D. Thay thế hoàn toàn cấu hình editorconfig
Đáp án đúng: A

Câu 18. Ngoài Java, muốn Spotless xử lý Markdown hoặc cấu hình, nên làm gì?
A. Chỉ mở rộng thuộc tính của compileJava
B. Đưa tệp tài liệu vào sourceSets Java
C. Thêm format target và bước xử lý tương ứng
D. Dùng lại tác vụ test để tự chỉnh văn bản
Đáp án đúng: C

Câu 19. CI báo Spotless không đạt còn máy cá nhân lại đạt. Điều gì nên kiểm tra trước?
A. Danh sách test unit có chạy đủ không
B. Phiên bản công cụ và tệp cấu hình có khớp
C. Có build lại toàn bộ artifact phụ thuộc không
D. Tốc độ tải plugin ở máy cá nhân có chậm
Đáp án đúng: B

Câu 20. SpotlessApply chạy thành công đảm bảo điều gì về mã Java?
A. Không còn lỗi logic tại tất cả đường chạy
B. Không còn cảnh báo an ninh từ dependency
C. Tệp tuân các bước định dạng đã cấu hình
D. Các bài kiểm thử đều đã chạy thành công
Đáp án đúng: C

Câu 21. Dùng git hook để chạy formatter trước commit, cách kiểm soát nào đáng tin cậy hơn?
A. Chỉ dựa vào hook vì mọi thành viên đều có
B. Tắt hoàn toàn CI khi đã cấu hình git hook
C. Cho IDE tự quyết định có chạy hook hay không
D. Giữ spotlessCheck trên CI dù có git hook
Đáp án đúng: D

Câu 22. Tính idempotent của một formatter được hiểu đúng là gì?
A. Chạy lại trên kết quả đã chuẩn không tạo diff
B. Formatter phải đổi tệp dù đầu vào đã chuẩn
C. Mỗi lần chạy lại sẽ đổi một phần khoảng trắng
D. Chỉ lần đầu chạy mới kiểm tra được import
Đáp án đúng: A

Câu 23. Khi build chậm do định dạng, cách tối ưu hợp lý trước tiên là gì?
A. Tắt luôn kiểm tra vì formatter tốn thời gian
B. Đổi kết quả check thành luôn thành công
C. Chạy formatter qua mọi tệp build sinh ra
D. Rà phạm vi target và khả năng dùng cache
Đáp án đúng: D

Câu 24. Muốn CI Maven chặn bản build khi nguồn Java sai định dạng, nên làm gì?
A. Gắn spotless:apply vào bước tạo artifact
B. Gắn spotless:check vào phase build
C. Chỉ chạy spotless:apply trên máy lập trình
D. Đưa plugin vào dependency của ứng dụng
Đáp án đúng: B
