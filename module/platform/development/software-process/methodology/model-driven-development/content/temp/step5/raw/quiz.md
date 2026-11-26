1. Trong Model-Driven Development, vai trò chính của mô hình là gì?
A. Làm tài liệu tham khảo khi nhóm tự viết toàn bộ mã
B. Làm bản vẽ phản ánh kiến trúc sau khi mã hoàn thành
C. Dùng làm đặc tả để kiểm chứng và sinh hiện vật
D. Làm tập dữ liệu chạy thử thay cho các ca nghiệp vụ
Đáp án đúng: C

2. Metamodel trong phát triển hướng mô hình xác định điều gì?
A. Dữ liệu instance được nạp ở mỗi lần chạy ứng dụng
B. Trình tự thao tác sinh mã của một phiên bản công cụ
C. Lịch sử sửa source code sau mỗi bản phát hành
D. Định nghĩa kiểu phần tử, quan hệ và các ràng buộc
Đáp án đúng: D

3. Khi nào một mô hình được xem là tuân theo metamodel?
A. Khi các phần tử đã có đủ tệp source được biên dịch
B. Khi cấu trúc mô hình phù hợp định nghĩa metamodel
C. Khi tên phần tử trùng với bảng trong database đích
D. Khi mô hình có thể hiển thị bằng trình chỉnh sửa UML
Đáp án đúng: B

4. Mục đích của Domain-Specific Language (DSL) trong MDD là gì?
A. Biểu diễn mọi lĩnh vực bằng cùng một cú pháp lập trình tổng quát
B. Buộc chuyên gia miền mô tả trực tiếp các lệnh triển khai SQL
C. Lưu mọi mô hình thành source code của một framework cố định
D. Diễn đạt quy tắc bằng những khái niệm quen thuộc của miền
Đáp án đúng: D

5. Abstract syntax và concrete syntax của DSL khác nhau ra sao?
A. Một bên xác định trình tự build, bên kia thiết lập môi trường
B. Một bên chỉ dùng khi kiểm thử, bên kia chỉ dùng khi triển khai
C. Một bên mô tả dữ liệu runtime, bên kia là dữ liệu kiểm thử
D. Một bên là cấu trúc khái niệm, bên kia là cách biểu diễn
Đáp án đúng: D

6. Khi thử nghiệm DSL cho chính sách giá, nhóm nên hỏi chuyên gia điều gì?
A. Cú pháp DSL đã giống hệt cấu trúc bảng SQL chưa?
B. Tên gọi và ví dụ có đúng cách hiểu nghiệp vụ không?
C. Có thể thay mọi invariant bằng phép kiểm tra UI không?
D. Mỗi quy tắc đã tạo số dòng Java gần bằng nhau chưa?
Đáp án đúng: B

7. Model-to-model transformation thường có đầu ra nào?
A. Các file mã nguồn được sinh trực tiếp từ cấu trúc mô hình
B. Một mô hình đích được tạo từ mô hình nguồn theo ánh xạ
C. Các bản ghi kiểm thử chạy tải theo thiết kế kiến trúc
D. Một báo cáo về thay đổi thủ công giữa hai lần deploy
Đáp án đúng: B

8. Model-to-text transformation thường dùng để làm gì?
A. Chuyển đổi mô hình miền thành mô hình nền tảng khác
B. So sánh hai phiên bản metamodel theo quy tắc ánh xạ
C. Kiểm tra invariant trên một phiên bản mô hình trừu tượng
D. Sinh mã nguồn hay file cấu hình từ phần tử mô hình
Đáp án đúng: D

9. Khác biệt chính giữa PIM và PSM trong Model-Driven Architecture là gì?
A. PIM mô tả runtime, PSM chỉ mô tả lịch sử commit mã
B. PIM chỉ mô tả database, PSM chỉ mô tả giao diện web
C. PIM ít gắn nền tảng, PSM thêm quyết định công nghệ
D. PIM chứa lớp đã build, PSM chứa các bộ kiểm thử UI
Đáp án đúng: C

10. Khi chuyển mô hình miền sang mô hình lưu trữ, điều gì phải được định nghĩa?
A. Quy tắc ánh xạ identity, thuộc tính và các quan hệ
B. Thời gian chạy tối đa của mỗi bước tạo file nguồn
C. Cách sắp đặt biểu tượng mô hình trên màn hình thiết kế
D. Số lượt biên dịch thử cho từng lớp được ánh xạ
Đáp án đúng: A

11. Vì sao cần trace giữa phần tử mô hình và artifact được sinh?
A. Để tất cả artifact buộc nằm trong một thư mục
B. Để mã đã sinh luôn có cùng số dòng với mô hình
C. Để xác định tác động khi phần tử mô hình thay đổi
D. Để thay thế việc review thiết kế trước khi sinh mã
Đáp án đúng: C

12. Cách nào giúp chạy sinh mã từ mô hình có kết quả tái lập?
A. Chỉ giữ các file output cuối mà bỏ thông tin generator
B. Chọn ngẫu nhiên template khả dụng ở từng lần build
C. Cố định mô hình, generator, template và cấu hình đầu vào
D. Cho phép người chạy sửa input trực tiếp trước mỗi lần sinh
Đáp án đúng: C

13. Quy tắc `min <= max` trong mô hình cấu hình nên được xem là gì?
A. Một invariant về giá trị hợp lệ trong mô hình
B. Quy tắc đổi tên file của generator trước khi thực thi
C. Tùy chọn chuyển đổi mô hình sang một định dạng văn bản
D. Thuộc tính của bản vẽ biểu diễn thứ tự phần tử
Đáp án đúng: A

14. Khi mô hình có liên kết bắt buộc nhưng thiếu đối tượng đích, nên làm gì?
A. Báo lỗi validation trước khi thực hiện code generation
B. Tự thay liên kết bằng optional để quá trình sinh tiếp tục
C. Chỉ thêm cảnh báo ở mã đã sinh và vẫn bỏ qua mô hình
D. Đổi kiểu liên kết sang string mà không rà lại yêu cầu
Đáp án đúng: A

15. Model validation khác với kiểm thử code đã sinh chủ yếu ở đâu?
A. Xác minh tương tác runtime giữa các thành phần đã chạy
B. Đo response của ứng dụng đã build khi có tải thử nghiệm
C. Phát hiện vi phạm cấu trúc và quy tắc ngay trên mô hình
D. Kiểm tra kết quả triển khai chương trình trên môi trường đích
Đáp án đúng: C

16. Hai quy tắc DSL mâu thuẫn về cùng một điều kiện thì nên xử lý thế nào?
A. Phát hiện xung đột ngữ nghĩa khi kiểm tra mô hình
B. Để generator ưu tiên quy tắc xuất hiện ở cuối file
C. Giữ hai quy tắc rồi chọn rule theo thứ tự nhập liệu
D. Bỏ kiểm tra mâu thuẫn và giải quyết chỉ ở mã sinh
Đáp án đúng: A

17. Khi mã sinh cần chứa phần mở rộng thủ công, cách tổ chức nào bền vững?
A. Tách mã tự viết khỏi phần file do generator quản lý
B. Sửa luôn phần được sinh và để lần build sau ghi đè
C. Cho phép generator xóa extension không còn trùng template
D. Đưa mọi extension vào tên file để dễ sinh lại toàn bộ
Đáp án đúng: A

18. Vì sao chỉnh trực tiếp file generated có nguy cơ mất thay đổi?
A. Mọi phần mềm sinh mã đều tự làm file thành chỉ đọc
B. Compiler sẽ bỏ qua toàn bộ câu lệnh thêm bằng tay
C. Generator có thể ghi đè chỉnh sửa khi chạy lại
D. Mọi sửa đổi tự động được chuyển ngược vào metamodel
Đáp án đúng: C

19. Thách thức lớn của round-trip giữa model và source là gì?
A. Không thể biểu diễn mô hình và code trong cùng Git repo
B. Source luôn có cùng mức trừu tượng như mô hình nghiệp vụ
C. Generator luôn tự hợp nhất mọi sửa đổi theo đúng ý định
D. Đồng bộ hai chiều mà không mất ý nghĩa hoặc thay đổi
Đáp án đúng: D

20. Khi cả mô hình lẫn mã sinh đều được phép chỉnh, nhóm cần quyết định gì?
A. Số lần được chỉnh mã trong mỗi sprint triển khai
B. Tên nhánh dành riêng cho người tạo diagram cuối cùng
C. Định dạng ảnh ưu tiên để lưu sơ đồ vào tài liệu
D. Xác định nguồn sự thật và cách hợp nhất hai chiều
Đáp án đúng: D

21. Traceability giúp gì khi thêm thuộc tính mới vào mô hình nghiệp vụ?
A. Chứng minh mọi API vẫn tương thích mà không cần test
B. Tìm các quy tắc chuyển đổi và artifact bị tác động
C. Bảo đảm source được sinh lại mà không thay đổi dòng nào
D. Chỉ ghi lịch sử ai sửa vị trí ký hiệu trên sơ đồ
Đáp án đúng: B

22. Trong CI, phép kiểm nào giúp phát hiện model-code drift?
A. Chạy lại unit test cũ mà không dùng phiên bản mô hình mới
B. Sinh mã từ model cố định và kiểm tra diff kết quả
C. So thời gian sửa file UML với timestamp của Java source
D. Bỏ qua template đổi phiên bản nếu mã vẫn biên dịch
Đáp án đúng: B

23. Trường hợp nào thường đem lại giá trị cao khi áp dụng MDD?
A. Có cấu trúc ổn định lặp lại và nhiều output cần sinh
B. Có thay đổi ngữ nghĩa liên tục và không ai sở hữu DSL
C. Chỉ cần một cấu hình nhỏ được viết tay duy nhất
D. Không có quy tắc có thể kiểm tra hay chuyển đổi nhất quán
Đáp án đúng: A

24. Khi quyết định đầu tư MDD, đánh đổi nào quan trọng nhất?
A. Số lượng ký hiệu có thể đặt trên sơ đồ ở một màn hình
B. So lợi ích tự động hóa với công bảo trì generator
C. Thời gian học phím tắt của công cụ chỉnh sửa mô hình
D. Dạng tệp ảnh dùng để xuất mô hình cho tài liệu thiết kế
Đáp án đúng: B
