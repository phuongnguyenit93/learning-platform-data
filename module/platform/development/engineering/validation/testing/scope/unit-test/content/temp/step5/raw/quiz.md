Một unit test tốt cho lớp tính giá nên xác minh điều gì?
A. Kết nối cơ sở dữ liệu qua container thực
B. Luồng duyệt sản phẩm từ giao diện tới API
C. Cách framework khởi tạo từng bean service
D. Kết quả tính giá với đầu vào được kiểm soát
Đáp án đúng: D

Trong JUnit Jupiter, annotation nào đánh dấu một phương thức là bài test?
A. `@BeforeEach` dùng để chuẩn bị trạng thái
B. `@Test` dùng để khai báo phương thức test
C. `@AfterEach` dùng để dọn tài nguyên
D. `@Disabled` dùng để tạm bỏ qua test
Đáp án đúng: B

Muốn mỗi bài test có một giỏ hàng mới, nên khởi tạo ở đâu?
A. Trong `@BeforeEach` trước từng test
B. Trong `@BeforeAll` chỉ một lần cho cả lớp
C. Trong biến static được chia sẻ nhiều bài
D. Trong `@AfterEach` sau khi test đã kết thúc
Đáp án đúng: A

Khi dùng AssertJ để kiểm tra danh sách kết quả, assertion nào có giá trị hơn?
A. Chỉ kiểm tra tham chiếu danh sách không null
B. So nội dung phần tử với danh sách kỳ vọng
C. Chỉ kiểm tra constructor không ném exception
D. So số method được gọi trong lớp danh sách
Đáp án đúng: B

Service gọi cổng gửi email, unit test nên kiểm soát phụ thuộc ấy thế nào?
A. Gọi máy chủ SMTP thực ở mỗi lần chạy CI
B. Khởi tạo container mail mới cho mỗi assertion
C. Dùng mock cổng email và xác minh tương tác
D. Đọc lại email từ hộp thư cá nhân thật
Đáp án đúng: C

Khi Mockito mock repository trả dữ liệu cố định, thao tác nào thường dùng?
A. Dùng `when(...).thenReturn(...)` để stub giá trị
B. Dùng `verify(...)` để tự tạo dữ liệu trả về
C. Dùng `reset(...)` để thay cho mọi stub
D. Dùng `clearInvocations(...)` để thiết lập kết quả
Đáp án đúng: A

Khi service phải gọi publisher đúng một lần, Mockito hỗ trợ xác minh ra sao?
A. Dùng `@BeforeAll` để kiểm tra lời gọi thực tế
B. Chỉ stub publisher rồi suy ra số lần được gọi
C. Dùng `verify(publisher, times(1))` phù hợp
D. Dùng `assertNotNull` cho tham chiếu publisher
Đáp án đúng: C

Hàm phân loại điểm chấp nhận 0 đến 100, tập ca biên nào hợp lý?
A. Chỉ dùng giá trị 50 và 60 ở giữa miền
B. Chỉ dùng ba giá trị ngẫu nhiên bất kỳ
C. Chỉ dùng 0 rồi coi mọi giá trị khác tương đương
D. Thử -1, 0, 100, 101 cùng các ca thông thường
Đáp án đúng: D

Khi kiểm thử CompletableFuture bất đồng bộ, cách xác minh nào vững hơn?
A. Gọi sleep cố định và bỏ qua giá trị cuối
B. Chờ kết quả với timeout rồi so kỳ vọng
C. Gọi phương thức một lần và coi là đã chạy
D. Tắt executor trước khi tạo CompletableFuture
Đáp án đúng: B

Mutation score phản ánh khía cạnh nào của bộ unit test?
A. Tỷ lệ dòng code từng được chạy trong lúc test
B. Số class có tên test trùng tên class nguồn
C. Tỷ lệ biến thể mã bị kiểm thử phát hiện
D. Số test được thêm sau lần refactor gần nhất
Đáp án đúng: C

Một phương thức đạt 100% line coverage nhưng không có assertion, đánh giá nào đúng?
A. Bài test đã kiểm tra toàn bộ hành vi mong đợi
B. Mọi lỗi logic đã chắc chắn được phát hiện
C. Các case biên không còn cần kiểm thử thêm
D. Coverage cao chưa chứng minh test phát hiện lỗi
Đáp án đúng: D

Unit test dùng thời điểm hiện tại nên giảm phụ thuộc môi trường bằng cách nào?
A. Đọc trực tiếp đồng hồ hệ thống nhiều lần
B. Chờ đến đầu giây để tránh sai lệch thời gian
C. Dùng giá trị thời gian ngẫu nhiên trong từng lần
D. Tiêm `Clock` hoặc nguồn thời gian kiểm soát được
Đáp án đúng: D

Khi muốn kiểm tra input sai ném exception trong JUnit Jupiter, dùng gì?
A. `assertThrows` với loại lỗi và lời gọi cần test
B. `assertEquals` với `Exception.class` rồi kết thúc
C. `assertDoesNotThrow` cho lời gọi đầu vào sai
D. `assertTimeout` mà không kiểm tra loại exception
Đáp án đúng: A

Unit test phụ thuộc thứ tự chạy thường gây rủi ro nào?
A. Kiểm tra chính xác hơn vì tái dùng fixture đã lập
B. Giảm coupling do chia sẻ state giữa nhiều bài
C. Pass/fail khác nhau khi đổi thứ tự test
D. Luôn chạy nhanh hơn một bộ test độc lập
Đáp án đúng: C

Khi refactor nội bộ một hàm mà hợp đồng không đổi, bộ unit test tốt nên thế nào?
A. Fail mỗi khi tên biến cục bộ được đổi
B. Tiếp tục pass nếu hành vi quan sát vẫn đúng
C. Đòi gọi private method với đúng thứ tự cũ
D. Bắt buộc cập nhật assertion cho mọi refactor
Đáp án đúng: B

Khi test logic có nhiều tập dữ liệu đầu vào và kỳ vọng, cách tổ chức nào gọn?
A. Dùng `@ParameterizedTest` với nguồn dữ liệu rõ ràng
B. Tạo một test chứa mọi nhánh và bỏ thông báo lỗi
C. Lặp cùng một đoạn assertion trong nhiều method
D. Trộn ngẫu nhiên đầu vào mà không lưu seed
Đáp án đúng: A
