Câu 1. Trong đánh giá chất lượng mã, ví dụ nào thể hiện tính đúng đắn?
A. Tên biến mô tả đúng các khái niệm nghiệp vụ
B. Độ trễ API giảm sau khi thêm bộ nhớ đệm
C. Hàm trả đúng kết quả ở các trường hợp biên
D. Số tệp mã giảm sau khi chia lại các module
Đáp án đúng: C

Câu 2. Đổi biến x thành totalPrice với cùng giá trị, cải thiện trực tiếp điều gì?
A. Tên mới bộc lộ ý nghĩa của giá trị đang giữ
B. Ràng buộc nhập liệu được kiểm tra sớm hơn
C. Bộ nhớ của đối tượng được giải phóng sớm
D. Thời gian tính giá trị được rút ngắn đáng kể
Đáp án đúng: A

Câu 3. Thay một quy tắc nghiệp vụ mà phải sửa nhiều lớp không liên quan báo hiệu điều gì?
A. Hệ thống đang sử dụng ít lớp trừu tượng
B. Ứng dụng đã được kiểm thử đầy đủ hơn
C. Bộ nhớ được chia sẻ giữa các thread tốt
D. Mã khó bảo trì do phụ thuộc lan rộng
Đáp án đúng: D

Câu 4. Một phương thức chứa nhiều nhánh và dài hàng trăm dòng thường có code smell nào?
A. Long Method: phương thức gánh quá nhiều bước
B. Data Clumps: nhiều nhóm tham số đi cùng
C. Lazy Class: lớp có rất ít trách nhiệm
D. Primitive Obsession: lạm dụng kiểu cơ bản
Đáp án đúng: A

Câu 5. Hai chức năng lặp đoạn xử lý tính chiết khấu, cách refactor hợp lý nhất là gì?
A. Nhân bản thêm đoạn mã để sửa từng nơi
B. Trích phần chung và kiểm thử hồi quy
C. Gộp tất cả lớp vào một lớp tiện ích
D. Đổi tên phương thức mà giữ nguyên lặp
Đáp án đúng: B

Câu 6. Một lớp vừa xử lý thanh toán vừa dựng giao diện thường vi phạm nguyên tắc nào?
A. Quy tắc chỉ nên dùng kiểu dữ liệu bất biến
B. Quy tắc luôn giảm tối đa số phương thức
C. Nguyên tắc một trách nhiệm chính cho lớp
D. Quy tắc tránh mọi constructor có tham số
Đáp án đúng: C

Câu 7. Phương thức chủ yếu đọc trường và gọi logic của lớp khác gợi ý smell nào?
A. Data Clumps: nhóm tham số lặp ở nhiều nơi
B. Feature Envy: thao tác nhiều với lớp khác
C. Shotgun Surgery: sửa một việc ở nhiều tệp
D. Long Parameter List: nhận quá nhiều tham số
Đáp án đúng: B

Câu 8. Tầng domain import lớp UI, còn UI lại import domain có nguy cơ gì?
A. Thêm ràng buộc kiểu dữ liệu lúc biên dịch
B. Tăng khả năng tái sử dụng dịch vụ nghiệp vụ
C. Tăng tính cô lập giữa tầng giao diện và lõi
D. Tạo chu trình phụ thuộc giữa các tầng
Đáp án đúng: D

Câu 9. Trong dự án phần mềm, nợ kỹ thuật thường chỉ điều gì?
A. Chi phí sửa đổi tương lai do giải pháp tạm
B. Số chi phí hạ tầng đã trả cho nhà cung cấp
C. Các lỗi runtime đã được ghi nhận trong log
D. Số nhiệm vụ còn mở trên bảng công việc
Đáp án đúng: A

Câu 10. Khi cần ưu tiên xử lý cảnh báo chất lượng, tiêu chí nào hữu ích nhất?
A. Chọn cảnh báo theo thứ tự tên quy tắc
B. Xếp theo tác động và khả năng gây lỗi
C. Xử lý theo thứ tự xuất hiện ở editor
D. Chọn tệp có số dòng ngắn nhất trước
Đáp án đúng: B

Câu 11. Trước khi refactor một nhánh tính thuế đang chạy tốt, nhóm nên làm gì?
A. Đổi toàn bộ tên hàm rồi mới chạy build
B. Xóa test cũ vì cấu trúc lớp đã thay đổi
C. Tạo kiểm thử hành vi làm mốc so sánh
D. Chỉ so số dòng mã trước và sau sửa đổi
Đáp án đúng: C

Câu 12. Một nhận xét code review nào giúp tác giả sửa vấn đề rõ ràng nhất?
A. Yêu cầu viết lại vì bản cũ trông không đẹp
B. Nêu trường hợp hỏng, gợi ý cách kiểm chứng
C. Chỉ ghi chung là cần làm sạch toàn bộ hàm
D. Chặn merge vì không giống sở thích cá nhân
Đáp án đúng: B

Câu 13. Khi đặt tên phương thức nghiệp vụ, tiêu chí nào cải thiện khả năng đọc?
A. Đặt tên ngắn nhất để giảm số ký tự
B. Giữ tên trùng với tên kiểu trả về
C. Đưa hết tham số vào chuỗi tên hàm
D. Diễn đạt đúng mục đích trong miền nghiệp vụ
Đáp án đúng: D

Câu 14. Chỉ số cyclomatic complexity gần với điều gì nhất?
A. Số đường đi độc lập do các nhánh quyết định
B. Số package Java được tham chiếu trực tiếp
C. Số bytecode sinh ra từ trình biên dịch
D. Số lần gọi hàm đến các thư viện ngoài
Đáp án đúng: A

Câu 15. Vì sao coverage 95% chưa đủ chứng minh hệ thống không có lỗi?
A. Coverage không chạy được trên mã Java mới
B. Coverage chỉ dùng được khi hệ thống không có CI
C. Coverage tự bỏ qua các hàm mang giá trị trả về
D. Test có thể chạy qua mã nhưng assert chưa đủ
Đáp án đúng: D

Câu 16. Khi API bị chậm, hành động nào có căn cứ hơn phỏng đoán tối ưu?
A. Đổi mọi collection sang cấu trúc khác
B. Tăng số thread dù chưa đo chi phí khóa
C. Đo CPU, I/O và độ trễ trên tải đại diện
D. Xóa toàn bộ logging để giảm thời gian
Đáp án đúng: C

Câu 17. Khi nhận dữ liệu từ request, cách giảm lỗi và rủi ro bảo mật là gì?
A. Tin dữ liệu vì đã qua giao diện web
B. Kiểm tra kiểu, độ dài và phạm vi đầu vào
C. Chỉ kiểm tra đầu vào sau khi lưu xuống DB
D. Cho mọi tham số tự chuyển đổi không giới hạn
Đáp án đúng: B

Câu 18. Khác biệt hợp lý nhất giữa code smell và bug là gì?
A. Smell báo nguy cơ thiết kế, chưa chắc gây lỗi
B. Smell luôn khiến hệ thống dừng ngay khi chạy
C. Bug chỉ ảnh hưởng khả năng đọc của mã nguồn
D. Bug không cần kiểm chứng bằng trường hợp cụ thể
Đáp án đúng: A

Câu 19. Công cụ phân tích tĩnh thường phát hiện vấn đề bằng cách nào?
A. Gửi toàn bộ request thật đến môi trường chạy
B. Chạy kiểm thử hiệu năng trên hệ thống phát hành
C. Phân tích mã mà không thực thi nhánh đó
D. So sánh kết quả UI qua các lượt chạy trình duyệt
Đáp án đúng: C

Câu 20. Khi refactor một module có nhiều người sử dụng, cách làm nào giảm hồi quy?
A. Tách thay đổi nhỏ và chạy test sau mỗi bước
B. Viết lại toàn bộ module trong một lần merge
C. Chuyển hết lỗi phát hiện sang đợt sau
D. Tắt kiểm tra hợp đồng API trong giai đoạn sửa
Đáp án đúng: A

Câu 21. Review thay đổi hàm tính phí cần chú ý điều gì ngoài kiểu mã?
A. Đếm số dòng chỉnh sửa trên mỗi tệp Java
B. Kiểm tra độ dài tên biến theo quy ước
C. Kiểm tra thứ tự import của các package
D. Xét quy tắc làm tròn và trường hợp biên
Đáp án đúng: D

Câu 22. Thiết kế nào giúp kiểm thử lớp xử lý thanh toán độc lập hơn?
A. Khởi tạo kết nối DB thật ngay trong constructor
B. Tách phụ thuộc để thay bằng fake khi kiểm thử
C. Đưa mọi logic vào một phương thức static lớn
D. Gọi trực tiếp dịch vụ bên ngoài trong unit test
Đáp án đúng: B

Câu 23. Muốn ngăn lỗi chất lượng tái xuất hiện ở nhánh chính, nên làm gì?
A. Chỉ dựa vào trí nhớ của người code review
B. Đợi đến sát ngày release mới rà soát
C. Tự động chạy kiểm tra, test và gate trên CI
D. Chỉ ghi quy định chất lượng trong wiki dự án
Đáp án đúng: C

Câu 24. Khi dùng số lượng cảnh báo và coverage để đánh giá chất lượng, nên làm gì?
A. Chốt chất lượng theo một ngưỡng LOC cố định
B. Dùng coverage duy nhất để xếp hạng nhóm
C. Đếm mọi cảnh báo mà bỏ qua mức độ nặng
D. Xem xu hướng chỉ số cùng bối cảnh thay đổi
Đáp án đúng: D
