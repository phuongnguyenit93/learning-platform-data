Câu 1: Trước đợt kiểm thử phát hành, thông tin nào cần được chốt để có thể tái lập?
A. Commit/build, cấu hình và dữ liệu test tương ứng
B. Tên người chạy test và thời điểm bắt đầu chạy
C. Số bài test và định dạng báo cáo test cuối kỳ
D. Nhánh release và phiên bản IDE đang sử dụng
Đáp án đúng: A

Câu 2: Vì sao dữ liệu đầu vào cho test tích hợp cần có cách khởi tạo xác định?
A. Các lần chạy nên tái sử dụng dữ liệu từ production
B. Bỏ hoàn toàn bước dọn dữ liệu khi test kết thúc
C. Mọi test cần dùng chung một tài khoản đăng nhập
D. Giữ trạng thái ban đầu ổn định giữa các lượt chạy
Đáp án đúng: D

Câu 3: Bộ test chạy song song trên cùng database dễ lỗi do đâu?
A. Test luôn có thời gian thực thi bằng nhau nên dễ lỗi
B. Mỗi test đều được database tự tạo transaction riêng
C. Coverage report tự khóa mọi bảng trong lúc chạy test
D. Các test cùng ghi đè dữ liệu và trạng thái chia sẻ
Đáp án đúng: D

Câu 4: Cách giảm phụ thuộc vào thời gian thực trong kiểm thử Java là gì?
A. Tiêm Clock giả để cố định thời điểm được kiểm tra
B. Thêm Thread.sleep để ổn định thứ tự callback
C. Đổi timezone JVM theo từng dữ liệu đầu vào
D. Chạy test ở khung giờ được CI chỉ định sẵn
Đáp án đúng: A

Câu 5: Khi test tích hợp gọi dịch vụ ngoài không ổn định, cần xác định gì?
A. Ranh giới nào dùng stub và ranh giới nào chạy thật
B. Luôn thay mọi dịch vụ bằng mock dù kiểm thử contract
C. Luôn gọi production API trong mọi unit test
D. Bỏ qua lỗi kết nối vì không thuộc code đang được test
Đáp án đúng: A

Câu 6: Với test tạo tài nguyên trong CI song song, thiết kế nào phù hợp?
A. Mọi job tạo bản ghi có cùng khóa để dễ đối chiếu
B. Mỗi job dùng tài khoản admin production và không dọn
C. Tạo ID/namespace riêng rồi dọn sạch sau khi chạy
D. Mọi test giữ trạng thái để lượt sau chạy nhanh hơn
Đáp án đúng: C

Câu 7: Khi lưu kết quả test run, metadata nào giúp truy vết tốt nhất?
A. Chỉ tổng số bài test đã vượt qua trong ngày
B. Chỉ tên tester và định dạng file báo cáo
C. Chỉ độ dài log và số lần mở dashboard
D. Commit, build, môi trường và thời điểm kiểm thử
Đáp án đúng: D

Câu 8: Một test thất bại xen kẽ dù code không đổi, nhận định nào hợp lý?
A. Chắc chắn sản phẩm đã có một regression ổn định
B. Chắc chắn người chạy đã bỏ qua bước build Java
C. Có dấu hiệu flaky do điều kiện chạy dao động
D. Chắc chắn nên xóa test khỏi toàn bộ CI ngay lập tức
Đáp án đúng: C

Câu 9: Khi quarantine flaky test, chính sách nào giảm rủi ro che lỗi?
A. Ẩn kết quả vô thời hạn rồi coi toàn bộ suite xanh
B. Có owner, ticket, hạn xử lý và theo dõi riêng
C. Tắt toàn bộ test cùng module cho tới release kế tiếp
D. Cho test tự chạy lại không giới hạn và bỏ log lỗi
Đáp án đúng: B

Câu 10: Vì sao retry một test thất bại không đủ để kết luận lỗi đã được sửa?
A. Retry luôn xóa được race condition trong mã nguồn
B. Retry làm toàn bộ test tự cập nhật assertion mới
C. Lần chạy qua có thể che tình trạng flaky vẫn còn
D. Retry chứng minh lỗi cũ không thể tái xuất hiện
Đáp án đúng: C

Câu 11: Để chẩn đoán thất bại trong CI, bằng chứng nào hữu ích?
A. Chỉ ảnh dashboard hiển thị phần trăm thành công
B. Log, stack trace, input và artifact đúng lượt chạy
C. Chỉ thông báo tổng số test trong repository
D. Chỉ một đoạn README mô tả cách chạy thủ công
Đáp án đúng: B

Câu 12: Khi test không chạy vì container DB không khởi động, phân loại nào đúng?
A. Defect nghiệp vụ đã được xác nhận ở API response
B. Sai lệch assertion khi nhận dữ liệu hợp lệ
C. Độ trễ vượt ngưỡng trong benchmark ứng dụng
D. Lỗi môi trường hoặc hạ tầng thực thi kiểm thử
Đáp án đúng: D

Câu 13: Một defect report có khả năng tái hiện tốt thường gồm gì?
A. Chỉ mức nghiêm trọng và tên người phát hiện lỗi
B. Chỉ đường dẫn commit gần nhất và một ảnh giao diện
C. Bước tái hiện, expected/actual và môi trường
D. Chỉ tên case rồi yêu cầu developer tự tìm đầu vào
Đáp án đúng: C

Câu 14: Severity trong quản lý defect chủ yếu diễn tả điều gì?
A. Mức tác động của lỗi lên hệ thống hoặc người dùng
B. Thời điểm team dự kiến bắt đầu sửa một lỗi
C. Thứ tự ticket cần xử lý theo cam kết release
D. Số lần lỗi được reporter cập nhật mô tả
Đáp án đúng: A

Câu 15: Priority khác severity ở khía cạnh nào?
A. Phản ánh độ khó tái hiện của một lỗi trên CI
B. Phản ánh số dòng code tham gia gây ra lỗi
C. Phản ánh phần trăm test case đang bị bỏ qua
D. Mức cần xử lý sớm theo bối cảnh phát hành
Đáp án đúng: D

Câu 16: Trước khi đóng ticket defect đã sửa, bước xác nhận nào hợp lý?
A. Chỉ xác nhận commit đã merge mà không chạy kiểm thử
B. Retest lỗi cũ và chạy hồi quy vùng chịu ảnh hưởng
C. Chỉ xác nhận developer đổi trạng thái ticket sang Done
D. Chỉ cập nhật số lượng test suite mà bỏ kết quả thực tế
Đáp án đúng: B

Câu 17: Khi sửa hàm dùng chung, cách chọn regression test nào có cơ sở?
A. Chọn ngẫu nhiên các case vì không cần phân tích ảnh hưởng
B. Chỉ chạy test của file có cùng tên với commit hiện tại
C. Ưu tiên luồng bị tác động và quan hệ phụ thuộc liên quan
D. Bỏ test tích hợp vì unit test luôn bao phủ toàn bộ
Đáp án đúng: C

Câu 18: Mục tiêu của smoke test trước khi chạy suite dài trong CI là gì?
A. Bắt lỗi build hoặc môi trường ở luồng chính
B. Đo độ phức tạp của mọi thuật toán trong source
C. Thay toàn bộ acceptance test của từng chức năng
D. Chạy mọi dữ liệu production để kiểm thử tính bảo mật
Đáp án đúng: A

Câu 19: Nếu suite có 100% line coverage nhưng vẫn lọt defect, kết luận nào đúng?
A. Coverage cao chứng minh mọi hành vi của sản phẩm đều đúng
B. Coverage chỉ nói mã đã chạy, chưa chứng minh test đủ
C. Coverage cao chứng minh không thể còn bug concurrency
D. Coverage cao đồng nghĩa mọi test đều không flaky
Đáp án đúng: B

Câu 20: Chỉ số nào có thể dùng theo dõi sức khỏe test suite qua thời gian?
A. Số lượng comment trong source và số biến đặt tên ngắn
B. Số tab IDE đang mở và độ dài nhánh release
C. Số lần tải dependency nhưng bỏ số liệu test
D. Thời gian chạy, tỷ lệ flaky và phân bố lỗi theo nhóm
Đáp án đúng: D

Câu 21: Race condition thường gây flaky test trong tình huống nào?
A. Test luôn dùng một tập dữ liệu được cố định
B. Test kiểm tra kết quả của hàm thuần không có state
C. Test phụ thuộc lịch chạy thread và thiếu đồng bộ
D. Test dùng đồng hồ giả để cố định thời điểm xử lý
Đáp án đúng: C

Câu 22: Vì sao tăng timeout tùy tiện thường không sửa được flaky test?
A. Nó tự tạo khóa đồng bộ cho mọi biến chia sẻ
B. Nó tự loại bỏ độ trễ network khỏi môi trường CI
C. Nó có thể che nguyên nhân chờ đợi hoặc tranh chấp
D. Nó tự bảo đảm trình tự callback luôn cố định
Đáp án đúng: C

Câu 23: Đối với test data có PII, cách dùng nào thích hợp trong CI?
A. Dùng dữ liệu giả/ẩn danh và hạn chế quyền truy cập
B. Sao chép đầy đủ dữ liệu khách hàng từ production mỗi đêm
C. Ghi toàn bộ thông tin cá nhân vào log để dễ debug
D. Đưa secret test chung trực tiếp vào source repository
Đáp án đúng: A

Câu 24: Khi môi trường local pass nhưng CI fail, nên đối chiếu những gì?
A. Cấu trúc test suite mà không xét các biến môi trường
B. Số lượng test bị skip nhưng không xét dữ liệu đầu vào
C. Thời điểm commit nhưng bỏ phiên bản dependency
D. JDK, dependency, cấu hình, timezone và tài nguyên
Đáp án đúng: D

Câu 25: Để mỗi test độc lập với thứ tự chạy, fixture cần đặc tính nào?
A. Giả định các test trước đã chuẩn bị dữ liệu hợp lệ
B. Mỗi test tự thiết lập và dọn dữ liệu của mình
C. Chia sẻ state static để các test sau tái dùng
D. Giữ nguyên kết quả lần chạy trước để tăng tốc
Đáp án đúng: B

Câu 26: Khi lỗi xảy ra ở bước setup trước assertion, báo cáo nên phản ánh gì?
A. Coi tất cả là defect nghiệp vụ tại endpoint
B. Phân biệt lỗi setup và lỗi assertion
C. Coi setup thất bại là kết quả test pass
D. Bỏ toàn bộ stack trace để tránh gây nhiễu
Đáp án đúng: B

Câu 27: Khi CI gate chặn PR vì flaky test, điều hành phù hợp là gì?
A. Triage có bằng chứng và sửa nguyên nhân gốc
B. Cho retry vô hạn rồi xem lần pass là kết quả cuối
C. Xóa toàn bộ stage test để PR được merge nhanh
D. Tự đổi assertion thành điều kiện luôn đúng
Đáp án đúng: A

Câu 28: Khi hợp đồng API đã đổi có chủ đích, bảo trì test suite nên làm gì?
A. Giữ mọi assertion cũ dù không còn đúng với hợp đồng
B. Cập nhật test, fixture theo yêu cầu mới có review
C. Chỉ xóa mọi test failure và giữ nguyên test pass
D. Đổi tên file test mà không xem tác động nghiệp vụ
Đáp án đúng: B
