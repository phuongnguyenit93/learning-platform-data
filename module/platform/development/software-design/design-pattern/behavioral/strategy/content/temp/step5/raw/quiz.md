Câu 1. Khi cùng bài toán tính phí có nhiều thuật toán thay thế, Strategy tổ chức chúng ra sao?
A. Đặt mọi biến thể vào một chuỗi if trong Context
B. Chuyển thuật toán thành các hàm static rời rạc
C. Đóng gói từng thuật toán sau một hợp đồng chung
D. Kế thừa Context riêng cho mỗi kết quả tính phí
Đáp án đúng: C

Câu 2. Trong mẫu Strategy, trách nhiệm chủ yếu của Context là gì?
A. Ủy quyền phần thuật toán cho strategy được chọn
B. Lưu tất cả nhánh thuật toán trong lớp nghiệp vụ
C. Tự sinh thêm implementation khi dữ liệu thay đổi
D. Thay đổi hợp đồng chung theo từng request nhận
Đáp án đúng: A

Câu 3. Một interface Java làm Strategy nên khai báo điều gì?
A. Chi tiết constructor của tất cả Context đang dùng
B. Cách truy cập trực tiếp database của từng thuật toán
C. Thao tác chung để các biến thể có thể thay thế
D. Toàn bộ điều kiện chọn biến thể trong UI controller
Đáp án đúng: C

Câu 4. Hệ thống cần đổi thuật toán tính giá ngay khi chạy mà không sửa Context. Cách nào phù hợp?
A. Đổi superclass của Context bằng reflection mỗi lần
B. Dùng switch trong mọi nơi cần tính toán lại
C. Copy thuật toán được chọn vào method của Context
D. Truyền instance Strategy vào Context lúc chạy
Đáp án đúng: D

Câu 5. Vì sao Strategy thường giúp đáp ứng Open/Closed Principle?
A. Các biến thể bắt buộc thay đổi interface liên tục
B. Có thể thêm biến thể mà ít sửa logic dùng chung
C. Context tự động phát hiện mọi class không cấu hình
D. Mọi quy tắc đều chỉ cần một implementation duy nhất
Đáp án đúng: B

Câu 6. Khi thuật toán chỉ là một hàm nhỏ, cách triển khai Strategy Java nào gọn mà vẫn thay thế được?
A. Đưa biến thể vào một method private của Context
B. Bắt buộc tạo một abstract class nhiều lifecycle hook
C. Dùng một enum chỉ có trường dữ liệu cấu hình
D. Dùng lambda nếu hợp đồng là functional interface
Đáp án đúng: D

Câu 7. Strategy muốn biểu diễn bằng lambda Java cần điều kiện nào ở interface?
A. Có đúng một phương thức trừu tượng cần thực hiện
B. Có nhiều phương thức abstract để chọn lúc chạy
C. Là một lớp final, không có hàm trừu tượng
D. Chỉ có các phương thức static không có đầu vào
Đáp án đúng: A

Câu 8. Dùng enum để hiện thực nhiều Strategy cố định có điểm hạn chế nào?
A. Mỗi enum constant tự tạo vô hạn instance mỗi request
B. Bộ biến thể cố định, khó cấp state theo request
C. Mỗi enum constant có thể đổi tên class sau compile
D. Enum không thể hiện thực interface và override method
Đáp án đúng: B

Câu 9. Một Strategy giữ bộ đếm mutable nhưng được chia sẻ cho nhiều request. Rủi ro nào cần lưu ý?
A. Trạng thái dùng chung có thể gây race giữa các luồng
B. Context tự động copy strategy trước mỗi lần gọi
C. Đối tượng Strategy tự chuyển sang immutable bởi Java
D. Việc chọn Strategy sẽ luôn xảy ra lúc biên dịch
Đáp án đúng: A

Câu 10. Khi mỗi thuật toán trả một loại dữ liệu đầu ra rất khác nhau, thiết kế interface Strategy nên xem lại điều gì?
A. Chỉ cần ép mọi kết quả về Object và cast ở Context
B. Chỉ cần sinh interface riêng trong mọi request
C. Có còn một hợp đồng hành vi chung rõ ràng không
D. Có thể viết toàn bộ biến thể vào hàm khởi tạo không
Đáp án đúng: C

Câu 11. Chọn Strategy dựa trên mã thị trường từ cấu hình. Phần nào nên quyết định ánh xạ mã sang implementation?
A. Chính thuật toán phải tự gọi lại tất cả strategy còn lại
B. Context buộc dùng if trên từng dòng trong thuật toán
C. Mọi subclass Context tự đổi interface của Strategy
D. Một resolver hoặc factory chọn Strategy phù hợp
Đáp án đúng: D

Câu 12. Để test thuật toán khuyến mãi A mà không cần khởi động cả hệ thống, cách nào hợp lý?
A. Gọi toàn bộ Context với mọi biến thể một lúc
B. Chỉ kiểm tra tên class Strategy có hậu tố A
C. Test Strategy A bằng input và expected output
D. Chỉ đo thời gian chạy mà không xem kết quả tính
Đáp án đúng: C

Câu 13. Kiểm thử Context có thực sự ủy quyền cho Strategy nên dùng kỹ thuật nào?
A. Sao chép logic hai Strategy vào test của Context
B. Tiêm fake Strategy và kiểm tra kết quả nhận
C. Tắt mọi assertion để xem quá trình chạy ổn định
D. Thay mã nguồn Context ngay trước mỗi lần chạy test
Đáp án đúng: B

Câu 14. Điểm phân biệt trọng tâm của Strategy với State là gì?
A. State chỉ dùng interface, Strategy chỉ dùng abstract class
B. Strategy không cho thay instance sau khi khởi tạo
C. State bắt buộc dùng enum, Strategy bắt buộc dùng lambda
D. Strategy chọn thuật toán; State gắn chuyển trạng thái
Đáp án đúng: D

Câu 15. So với Template Method, Strategy ưu tiên cơ chế tái sử dụng nào?
A. Composition để thay thuật toán qua một đối tượng
B. Kế thừa lớp cơ sở và override toàn bộ pipeline
C. Method static với nhánh điều kiện trong mọi lời gọi
D. Sửa trực tiếp mã Context khi bổ sung biến thể
Đáp án đúng: A

Câu 16. Khi số lượng Strategy quá lớn và nhiều lớp chỉ khác hằng số, cải tiến nào đáng xem xét?
A. Bỏ interface để gộp toàn bộ bằng switch dài
B. Chuyển mọi strategy thành subclass của controller
C. Tạo thêm một interface cho từng giá trị cấu hình
D. Tách cấu hình dữ liệu khỏi thuật toán dùng chung
Đáp án đúng: D

Câu 17. Khi thêm Strategy tính phí mới, test regression nào có giá trị?
A. Chỉ kiểm tra implementation mới trả về số khác 0
B. Chỉ biên dịch interface và bỏ kiểm thử Context
C. Kiểm tra contract chung và lựa chọn đúng biến thể
D. Chỉ xác nhận số file Java tăng đúng một file
Đáp án đúng: C

Câu 18. Nếu resolver không tìm được Strategy cho mã thuật toán, Context nên làm gì?
A. Mặc định chọn một thuật toán bất kỳ và im lặng
B. Báo lỗi rõ hoặc dùng fallback đã định nghĩa
C. Đổi dữ liệu đầu vào cho đến khi có biến thể hợp lệ
D. Bỏ qua toàn bộ phần tính toán và trả mã thành công
Đáp án đúng: B

Câu 19. Một Strategy gọi dịch vụ ngoài và có thể thất bại; hợp đồng nào cần được nêu rõ?
A. Quy tắc trả lỗi, retry hoặc fallback của lời gọi
B. Mọi lỗi đều phải bị nuốt và trả số 0
C. Context phải đổi implementation khi có mọi lỗi
D. Chỉ việc tên class có chứa hậu tố Strategy hay không
Đáp án đúng: A

Câu 20. Vì sao không nên đặt logic chọn từng Strategy bên trong từng implementation?
A. Strategy sẽ bị Java cấm tạo object qua constructor
B. Các biến thể dễ phụ thuộc và gọi vòng lẫn nhau
C. Mọi biến thể bắt buộc dùng cùng một giá trị trả về
D. Interface sẽ tự động trở thành lớp abstract
Đáp án đúng: B

Câu 21. Muốn thêm biến thể định tuyến đơn hàng, bước nào đúng tinh thần Strategy?
A. Đổi chữ ký method chung mỗi lần thêm biến thể
B. Tạo subclass của mọi Context đang sử dụng
C. Thêm một nhánh if mới vào từng client của Context
D. Tạo implementation mới theo contract định tuyến
Đáp án đúng: D

Câu 22. Khi Context nhận Strategy qua constructor, lợi thế quan trọng cho test là gì?
A. Không còn cần kiểm tra bất kỳ điều kiện nghiệp vụ nào
B. Context tự động nhận tất cả strategy đang có
C. Có thể dùng test double thay implementation thật
D. Framework tự sinh kết quả kỳ vọng cho từng test
Đáp án đúng: C

Câu 23. Một Strategy cache dữ liệu theo request nhưng instance lại là singleton; cần xem xét điều gì?
A. Singleton luôn bảo đảm mỗi request có cache riêng
B. Tách state theo request để tránh ảnh hưởng chéo
C. Dữ liệu cache không còn chiếm bộ nhớ ở runtime
D. Mỗi thread sẽ tự tạo lại singleton khi gọi method
Đáp án đúng: B

Câu 24. Hệ thống chọn cách tính thuế theo quốc gia; quyết định nào thể hiện Strategy đúng nhất?
A. Chọn Strategy theo quốc gia rồi gọi hợp đồng
B. Cho mỗi quốc gia tự sửa trực tiếp class Context
C. Đưa công thức mọi quốc gia vào một constructor
D. Dùng nhiều lớp Context chỉ để đổi tên quốc gia
Đáp án đúng: A
