Mutation testing bổ sung điều gì so với chỉ đo line coverage?
A. Kiểm tra test có phát hiện thay đổi nhỏ trong mã
B. Chỉ đếm dòng được thực thi bởi bộ kiểm thử
C. Chỉ đo thời gian nạp các class trong mỗi lần test
D. Chỉ báo số commit mới được tạo từ source code
Đáp án đúng: A

Một mutant được báo KILLED trong PIT có nghĩa là gì?
A. Mã gốc đã bị xóa khỏi repository sau phân tích
B. Mutation được compiler bỏ qua vì code không hợp lệ
C. Một bài test thất bại khi chạy phiên bản biến đổi
D. Các bài test vẫn pass dù mã đã bị thay đổi
Đáp án đúng: C

Một mutant ở trạng thái SURVIVED thường cho thấy điều gì?
A. Mọi bài test liên quan đều đã được skip có chủ ý
B. Mutant được xóa khỏi lần chạy trước khi test bắt đầu
C. Các bài test chạy nhưng không phát hiện biến đổi đó
D. Mutant chắc chắn tương đương với logic nghiệp vụ gốc
Đáp án đúng: C

PIT báo NO_COVERAGE cho một mutant; diễn giải nào phù hợp?
A. Test đã chạy và xác nhận mutant tương đương
B. Không bài test nào chạm tới vùng mã bị biến đổi
C. Một test đã fail và mutant bị diệt bởi assertion
D. Không có class Java nào trong dự án được build
Đáp án đúng: B

Một mutant đổi `amount >= limit` thành `amount > limit`; đầu vào nào phân biệt được?
A. `amount = limit - 1` ở phía dưới ranh giới
B. `amount = limit + 2` ở phía trên ranh giới
C. `amount = limit + 1` ở phía trên ranh giới
D. `amount = limit`: đúng bằng mốc so sánh
Đáp án đúng: D

Line coverage không đổi nhưng mutation score tăng; cải tiến nào có thể tạo ra điều đó?
A. Assertion mạnh hơn trên các đường chạy đã có
B. Chỉ tăng timeout cho toàn bộ lệnh build project
C. Chỉ thêm lời gọi method không có assertion nào
D. Chỉ đổi tên phương thức test trong source Java
Đáp án đúng: A

Mutant tương đương (equivalent mutant) có đặc tính gì?
A. Chỉ cần retry là mọi test đều diệt được nó
B. Không có input hợp lệ phân biệt hành vi của nó
C. Luôn nằm trong code chưa từng được test thực thi
D. Được tạo bằng thao tác xóa toàn bộ thân method
Đáp án đúng: B

Khi chạy PIT trên mã Java, thay đổi mutation được hiểu thế nào?
A. Sửa migration DB trước khi chạy mọi unit test
B. Cập nhật dependency để ứng dụng chạy phiên bản mới
C. Ghi đè source chính rồi commit kết quả biến thể
D. Dùng biến thể mã khi chạy test, giữ source gốc
Đáp án đúng: D

Mutant còn sống tại nhánh xử lý exception; bước đánh giá đầu tiên nên làm gì?
A. Bỏ qua mọi mutant liên quan đến xử lý exception
B. Xóa toàn bộ nhánh xử lý lỗi khỏi source chính
C. Rà ca lỗi và assertion có phân biệt hành vi
D. Tăng mutation threshold để loại cảnh báo trên CI
Đáp án đúng: C

Một mutation đổi phép cộng thành phép trừ nhưng test vẫn pass, điều gì đáng kiểm tra?
A. Số lượng import Java trong lớp được kiểm tra
B. Việc Gradle có dùng cùng phiên bản formatter
C. Độ dài tên method chứa phép tính vừa thay đổi
D. Kiểm tra assertion có phát hiện kết quả sai
Đáp án đúng: D

Test không ổn định khiến kết quả mutation dao động; hướng xử lý nào phù hợp?
A. Ổn định test trước khi đánh giá điểm mutation
B. Bỏ mọi assertion chậm để các test luôn pass
C. Dùng random seed mới mỗi lần chạy để phủ rộng
D. Chỉ tăng số mutant được tạo ở cùng một vị trí
Đáp án đúng: A

Đưa mutation score vào quality gate CI, tiêu chí nào giúp áp dụng thực tế?
A. Dùng ngưỡng theo baseline và tăng dần
B. Chỉ so score giữa các dự án với ngôn ngữ khác
C. Áp ngưỡng tuyệt đối 100% cho mọi module ngay
D. Bỏ toàn bộ unit test khi score vượt một mức
Đáp án đúng: A

PIT làm pipeline PR chậm; tối ưu phạm vi nào hợp lý?
A. Chỉ bỏ tất cả mutation test khỏi mọi pipeline
B. Ưu tiên mã thay đổi, chạy phạm vi rộng định kỳ
C. Vô hiệu hóa unit test để dành thời gian cho PIT
D. Chỉ chạy PIT trên class không có test nào
Đáp án đúng: B

Code sinh tự động gây nhiều mutation không hữu ích; nên quản trị ra sao?
A. Xóa mọi test liên quan đến phần code được sinh
B. Thay các file sinh thành biến toàn cục không đổi
C. Giới hạn vùng mã sinh và ghi rõ lý do loại trừ
D. Chấp nhận mọi mutant trong mã sinh là lỗi thực
Đáp án đúng: C

Vì sao chỉ assert kết quả không null có thể để nhiều mutant sống?
A. Mọi test assertion đều bị bỏ qua khi chạy PIT
B. Kết quả không null tự động xác nhận logic đúng
C. PIT chỉ thay đổi tên field, không đụng biểu thức
D. Assertion quá yếu để nhận ra giá trị sai cụ thể
Đáp án đúng: D

Để so sánh mutation score qua hai lần cải tiến, cần giữ nhất quán điều gì?
A. Chỉ số lượng developer đã tham gia review PR
B. Giữ cùng phạm vi mã, mutator và bộ test
C. Chỉ thời điểm chạy và tên máy CI được chọn
D. Danh sách commit được tạo cùng ngày phát hành
Đáp án đúng: B
