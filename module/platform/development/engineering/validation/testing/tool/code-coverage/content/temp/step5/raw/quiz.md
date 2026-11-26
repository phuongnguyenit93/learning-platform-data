Câu 1: JaCoCo instruction coverage đo điều gì trong ứng dụng Java?
A. Instruction bytecode được thực thi trong lần đo
B. Dòng văn bản Java được đọc trong mỗi vòng test
C. Assertion thành công trong tổng số assertion chạy
D. Request HTTP thành công khi ứng dụng nhận tải
Đáp án đúng: A

Câu 2: Một dòng Java được JaCoCo coi là đã covered khi nào?
A. Có ít nhất một instruction của dòng đã thực thi
B. Mọi nhánh logic trên dòng được chọn khi chạy test
C. Có test method cùng tên với dòng nguồn đang xét
D. Trình biên dịch đã parse dòng mà không thấy lỗi
Đáp án đúng: A

Câu 3: Màu vàng trên dòng mã trong báo cáo HTML JaCoCo thường biểu thị gì?
A. Dòng chưa được trình biên dịch tạo bytecode
B. Dòng đã phủ hết mọi hướng rẽ của điều kiện
C. Dòng đã phủ một phần, vẫn còn phần chưa chạy
D. Dòng được loại khỏi báo cáo bằng excludes
Đáp án đúng: C

Câu 4: Branch coverage của JaCoCo chủ yếu đếm những nhánh nào?
A. Mỗi nhánh Git được tạo trong repository Java
B. Mọi khối catch như một nhánh riêng biệt
C. Mọi câu lệnh import trong class được biên dịch
D. Các hướng rẽ của if và switch ở mức bytecode
Đáp án đúng: D

Câu 5: Vì sao một dòng đã covered có thể vẫn chưa phủ hết branch?
A. Dòng đã covered thì mọi nhánh đều đã covered
B. Dòng có comment khiến các nhánh bị bỏ qua
C. Một hướng rẽ của điều kiện chưa được thực thi
D. Dòng chứa if nên không tạo bất kỳ bytecode nào
Đáp án đúng: C

Câu 6: Method coverage trong JaCoCo cho biết điều gì?
A. Một phương thức có được thực thi ít nhất một lần
B. Phương thức có assertion xác nhận đủ logic hay chưa
C. Phương thức xử lý đúng tất cả giá trị đầu vào
D. Phương thức có được JVM tối ưu bằng JIT chưa
Đáp án đúng: A

Câu 7: JaCoCo ghi nhận coverage Java thông dụng bằng cơ chế nào?
A. Chụp ảnh IDE để suy ra các lệnh đã được chạy
B. Đếm source dựa trên breakpoint trong debugger
C. Gắn probe vào bytecode rồi thu execution data
D. Phân tích commit để dự đoán nhánh đã thực thi
Đáp án đúng: C

Câu 8: Tệp jacoco.exec thường chứa dữ liệu gì?
A. Báo cáo HTML đã có phần trăm bao phủ theo dòng
B. Dữ liệu thực thi để kết hợp với class làm báo cáo
C. Danh sách toàn bộ assertion đúng trong mỗi lần test
D. Mã nguồn Java được sửa để bỏ những dòng chưa phủ
Đáp án đúng: B

Câu 9: Để JaCoCo dựng báo cáo phủ theo dòng nguồn, cần kết hợp dữ liệu nào?
A. Chỉ file pom.xml mà không cần bytecode đã biên dịch
B. Chỉ log stdout test mà không cần execution data
C. Execution data, class files và source đúng bản build
D. Chỉ kết quả git diff mà không cần thông tin class
Đáp án đúng: C

Câu 10: Trong Maven, goal jacoco:prepare-agent thường làm gì?
A. Sinh HTML report sau khi mọi test case hoàn thành
B. Kiểm tra rule coverage rồi từ chối build tức thì
C. Xóa các test chưa có assertion khỏi test suite
D. Thiết lập Java agent cho tiến trình thực thi test
Đáp án đúng: D

Câu 11: Goal jacoco:report của Maven dùng để thực hiện việc gì?
A. Bổ sung assertion vào test chưa được thực thi
B. Sinh báo cáo từ execution data và class/source
C. Khởi chạy integration test trong môi trường mới
D. Thay đổi nhánh if nhằm tăng tỷ lệ bao phủ
Đáp án đúng: B

Câu 12: Muốn build Maven thất bại khi tỷ lệ coverage dưới ngưỡng, dùng gì?
A. Chỉ gọi jacoco:prepare-agent mà không có rule
B. Cấu hình jacoco:check với rule/limit cần thiết
C. Chỉ gọi jacoco:report mà không giới hạn tối thiểu
D. Chỉ gọi mvn clean khi báo cáo có nhiều dòng đỏ
Đáp án đúng: B

Câu 13: Trong Maven, cấu hình Surefire tắt JVM fork có thể ảnh hưởng JaCoCo ra sao?
A. JaCoCo luôn chạy số lượng test tăng lên gấp đôi
B. JaCoCo biến toàn bộ unit test thành integration test
C. JaCoCo bỏ qua rule check dù cấu hình không đổi
D. Agent không được gắn vào JVM test như mong đợi
Đáp án đúng: D

Câu 14: Khi nhiều module Maven cần báo cáo tổng hợp, hướng nào phù hợp?
A. Mở HTML từng module rồi cộng tỷ lệ theo tay
B. Dùng report-aggregate với các module liên quan
C. Gộp toàn bộ test source thành một Java class
D. Đổi tên class trùng nhau để tăng tỷ lệ coverage
Đáp án đúng: B

Câu 15: Trong Gradle Java project có plugin JaCoCo, tác vụ báo cáo thường là gì?
A. jacocoTestReport để sinh báo cáo coverage
B. jacocoTestCoverageVerification để sinh báo cáo HTML
C. testClasses để gộp execution data từ nhiều JVM
D. compileJava để xuất XML coverage vào thư mục build
Đáp án đúng: A

Câu 16: Gradle task nào phù hợp để kiểm tra violation của ngưỡng coverage?
A. jacocoTestReport với lệnh xóa các coverage rule
B. jacocoTestData với yêu cầu tạo source giả
C. jacocoCompileVerification với threshold tự động
D. jacocoTestCoverageVerification với violationRules
Đáp án đúng: D

Câu 17: Vì sao muốn xuất JaCoCo XML cho hệ thống CI thường phải cấu hình report?
A. Để CI đọc kết quả theo định dạng máy có cấu trúc
B. Vì trình duyệt không thể mở báo cáo dạng HTML
C. Vì JaCoCo luôn chạy test lại mỗi lần xuất XML
D. Vì XML chứng minh các assertion đã hợp lệ
Đáp án đúng: A

Câu 18: Trong báo cáo JaCoCo, chỉ số missed branches tăng nói lên điều gì?
A. Có nhiều phương thức cùng tên trong một package
B. Có test case bị trình biên dịch bỏ qua lúc chạy
C. Một số hướng rẽ điều kiện chưa được thực thi
D. Có log message không đúng format trong unit test
Đáp án đúng: C

Câu 19: Tình huống nào có thể đạt 100% line coverage nhưng vẫn bỏ sót lỗi?
A. Test có oracle độc lập kiểm tra mọi hành vi quan trọng
B. Test có đủ assertion cho mọi trường hợp biên và lỗi
C. Test đã đối chiếu đầy đủ các bất biến nghiệp vụ
D. Test chạy qua từng dòng nhưng không assert đầu ra
Đáp án đúng: D

Câu 20: Vì sao 100% branch coverage chưa bảo đảm hết lỗi logic?
A. Tất cả input đã hợp lệ khi mọi nhánh được covered
B. Chưa thử hết tổ hợp input và bất biến nghiệp vụ
C. JaCoCo tự kiểm chứng hành vi nghiệp vụ của if
D. Exception nào cũng được tính vào branch đã covered
Đáp án đúng: B

Câu 21: Vì sao nhánh ném exception có thể cần test riêng dù branch báo tốt?
A. Bộ đếm branch không coi exception edges là nhánh
B. JaCoCo luôn tính mỗi catch thành branch đã covered
C. JaCoCo suy ra exception message từ mọi class file
D. JaCoCo chỉ đếm branch trong các method private
Đáp án đúng: A

Câu 22: Để tránh coverage vô tình giảm vì test bị skip trong CI, nên kiểm tra gì?
A. Chỉ kích thước file README của module cần kiểm thử
B. Chỉ thời gian checkout repository trên CI runner
C. Số test thực chạy và dữ liệu coverage được sinh
D. Chỉ số lượng nhánh remote đang tồn tại trong Git
Đáp án đúng: C

Câu 23: Nếu báo cáo cho thấy class mới có 0% method coverage, bước phân tích nào hữu ích?
A. Giảm ngưỡng chung ngay mà không xem vùng thiếu phủ
B. Class có được load và đường gọi được test không
C. Bỏ qua class vì JaCoCo không đọc mã nguồn Java
D. Thay mọi test bằng phép đo tốc độ trong JMH
Đáp án đúng: B

Câu 24: Khi coverage giảm sau refactor, cần loại trừ nguyên nhân nào trước khi kết luận?
A. Màu theme IDE của người viết refactor khác
B. Bookmark trong dự án đã được sắp xếp lại
C. Tên branch trong Git log dài hơn phiên trước
D. Phạm vi report, class bytecode và tập test đổi
Đáp án đúng: D

Câu 25: Khi gộp execution data từ nhiều JVM, điều kiện nào giúp kết quả có ý nghĩa?
A. Mỗi JVM phải dùng source khác để không trùng class
B. Mỗi JVM chỉ được chạy một assertion cho dự án
C. Chỉ cộng phần trăm coverage mỗi JVM bằng tay
D. Các JVM dùng class files khớp phiên bản build
Đáp án đúng: D

Câu 26: Khi loại generated code khỏi báo cáo coverage, nguyên tắc nào phù hợp?
A. Loại mọi file có điều kiện if để tỷ lệ tăng nhanh
B. Exclude có lý do rõ, không che vùng code rủi ro
C. Loại tất cả class có tỷ lệ thấp khỏi báo cáo
D. Loại mọi method private vì không thể thực thi
Đáp án đúng: B

Câu 27: Để thiết kế ngưỡng CI hợp lý, ngoài tỷ lệ coverage cần xét gì?
A. Rủi ro, mã thay đổi và chất lượng assertions
B. Số lượng test method được tạo trong source
C. Số dòng trắng được lọc khỏi các file Java
D. Số nhánh Git đã được merge trong tuần hiện tại
Đáp án đúng: A

Câu 28: Nếu code đã được test chạy qua nhưng không bắt được mutation gây sai kết quả, nên làm gì?
A. Chỉ tăng line coverage mà bỏ qua đầu ra
B. Thêm sleep để test dài hơn rồi chạy lại
C. Thêm assertion kiểm chứng hành vi đích
D. Đổi báo cáo coverage từ XML sang HTML
Đáp án đúng: C
