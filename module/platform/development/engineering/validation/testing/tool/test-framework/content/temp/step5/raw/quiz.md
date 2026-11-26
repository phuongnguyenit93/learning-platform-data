Câu 1. Trong JUnit Jupiter, annotation nào trực tiếp đánh dấu một phương thức là test?
A. @Test đánh dấu phương thức cần kiểm thử
B. @BeforeEach đánh dấu phương thức test
C. @AfterEach tự sinh test từ phương thức
D. @TestFactory đánh dấu mọi phương thức test
Đáp án đúng: A

Câu 2. Nếu cần tạo fixture mới trước mỗi test JUnit Jupiter, nên dùng hook nào?
A. @BeforeAll trước mỗi phương thức kiểm thử
B. @BeforeEach trước từng phương thức test
C. @AfterEach trước từng phương thức test
D. @AfterAll trước khi test đầu tiên chạy
Đáp án đúng: B

Câu 3. Muốn giải phóng tài nguyên sau từng test, lifecycle callback nào phù hợp?
A. @BeforeAll, chạy một lần trước mọi test
B. @AfterAll, chạy sau mỗi invocation của test
C. @BeforeEach, chạy ngay sau mỗi test
D. @AfterEach, chạy sau từng phương thức test
Đáp án đúng: D

Câu 4. Mặc định @BeforeAll phải static trong JUnit Jupiter; khi nào có thể khai báo non-static?
A. Khi dùng @TestInstance(PER_CLASS) cho lớp test
B. Khi đặt @DisplayName trên phương thức liên quan
C. Khi dùng @Tag để đánh dấu nhóm test riêng
D. Khi mọi phương thức test được khai báo final
Đáp án đúng: A

Câu 5. Cần kiểm tra loại exception và thông điệp; cách viết nào phù hợp?
A. Chỉ gọi hàm cần test mà không dùng assertion
B. Dùng assertDoesNotThrow rồi so message lỗi
C. Dùng assertThrows và kiểm tra exception trả về
D. Dùng assertEquals cho tên lớp khi chưa gọi hàm
Đáp án đúng: C

Câu 6. Một test cần báo nhiều lỗi assertion độc lập trong cùng lần chạy; API nào hỗ trợ?
A. assertTimeout để nhóm mọi phép so sánh
B. assertAll để chạy và báo nhiều assertion
C. assertSame để nhóm nhiều đối tượng khác nhau
D. assertNotNull để thực hiện toàn bộ phép so
Đáp án đúng: B

Câu 7. Trong JUnit Jupiter, assertTimeout khác assertTimeoutPreemptively về điểm nào?
A. Cả hai luôn chạy test trong cùng thread mới
B. Cả hai bắt buộc hủy đoạn mã ở thời điểm timeout
C. Bản preemptive có thể chạy mã ở thread riêng
D. Bản preemptive chỉ đo thời gian sau khi đã chạy
Đáp án đúng: C

Câu 8. Muốn chạy cùng test với nhiều hàng gồm userId và status trong JUnit, cách nào phù hợp?
A. Tạo nhiều @Test trùng tên và cùng nội dung
B. Dùng @ValueSource cho hai tham số mỗi hàng
C. Chỉ dùng @BeforeEach để thay dữ liệu thủ công
D. Dùng @ParameterizedTest kết hợp @CsvSource
Đáp án đúng: D

Câu 9. Khi dữ liệu tham số là đối tượng phức tạp, JUnit @MethodSource giúp gì?
A. Bắt buộc mọi tham số chỉ được là String
B. Cung cấp argument từ phương thức nguồn dữ liệu
C. Sinh input từ tên biến local trong test
D. Chạy cả nguồn dữ liệu mà không cần test method
Đáp án đúng: B

Câu 10. Một phương thức cần được test khi đầu vào null; annotation nguồn nào hỗ trợ?
A. @NullSource cung cấp một lượt dữ liệu null
B. @EmptySource luôn cung cấp giá trị null
C. @CsvSource tạo giá trị null cho mọi cột
D. @ValueSource chỉ tạo một giá trị null
Đáp án đúng: A

Câu 11. Trong TestNG, cách phổ biến cấp nhiều bộ tham số cho một @Test là gì?
A. Dùng @Factory thay cho tất cả argument
B. Dùng dependsOnMethods để tạo các argument
C. Dùng @BeforeSuite để trả về mảng dữ liệu
D. Dùng @DataProvider gắn với phương thức test
Đáp án đúng: D

Câu 12. Nếu mỗi phương thức TestNG cần setup riêng, lifecycle hook nào thường được dùng?
A. @BeforeMethod chạy trước từng test method
B. @BeforeTest chỉ chạy trước từng test method
C. @BeforeSuite chạy trước mỗi invocation
D. @AfterMethod chạy trước mỗi test method
Đáp án đúng: A

Câu 13. Trong JUnit Jupiter, extension có thể tham gia lifecycle test qua cách đăng ký nào?
A. Chỉ kế thừa trực tiếp lớp java.lang.Thread
B. Chỉ dùng @Disabled trên toàn bộ lớp test
C. Dùng @ExtendWith với extension phù hợp
D. Dùng @DisplayName để tự đăng ký extension
Đáp án đúng: C

Câu 14. Test thao tác tệp cần thư mục tạm độc lập, JUnit Jupiter hỗ trợ gì?
A. @TempDir chỉ để so sánh nội dung chuỗi
B. @TempDir cấp thư mục tạm cho test
C. @Tag tự tạo thư mục tạm theo tên nhóm
D. @Timeout luôn tạo thư mục mới trên đĩa
Đáp án đúng: B

Câu 15. Một phép kiểm tra Boolean cần khẳng định biểu thức là true; assertion phù hợp?
A. assertSame so tham chiếu đến đối tượng boolean
B. assertNotNull kiểm tra biểu thức có giá trị
C. assertTrue kiểm tra biểu thức Boolean được tính
D. assertThrows kiểm tra biểu thức ném lỗi
Đáp án đúng: C

Câu 16. Vì sao các test tạo dữ liệu trên cơ sở dữ liệu cần teardown độc lập?
A. Để giữ lại dữ liệu cũ cho lượt chạy sau
B. Để tăng số test phụ thuộc thứ tự thực thi
C. Để biến bài kiểm thử thành integration test
D. Để tránh làm bẩn trạng thái của các test khác
Đáp án đúng: D

Câu 17. Một suite được bật thực thi song song, lỗi xuất hiện khi test ghi chung static list. Cách sửa đúng?
A. Thay mọi assertion bằng logging để tránh race
B. Buộc các test khác nhau dùng chung một list
C. Chỉ tăng số thread để lỗi xảy ra nhanh hơn
D. Cô lập dữ liệu hoặc đồng bộ truy cập hợp lý
Đáp án đúng: D

Câu 18. Khi không cấu hình thứ tự trong JUnit Jupiter, nên giả định gì giữa các test?
A. Thứ tự luôn theo tên phương thức trong source
B. Thứ tự luôn theo số dòng của annotation @Test
C. Không phụ thuộc thứ tự để bảo đảm độc lập
D. Thứ tự luôn ngẫu nhiên trong mọi lần chạy
Đáp án đúng: C

Câu 19. Dùng Gradle để thực thi JUnit Jupiter, cấu hình tác vụ test thường cần gì?
A. useTestNG() để chạy tất cả Jupiter test
B. useJUnitPlatform() để dùng JUnit Platform
C. Chỉ bật compileJava mà không gọi test
D. Đăng ký tác vụ test mới trong mọi class
Đáp án đúng: B

Câu 20. Trong Maven, thành phần nào thường thực thi test JUnit trên lifecycle test?
A. maven-compiler-plugin thay thế toàn bộ test
B. maven-jar-plugin xử lý assertion trong unit test
C. maven-surefire-plugin với hỗ trợ JUnit Platform
D. maven-deploy-plugin sinh kết quả unit test
Đáp án đúng: C

Câu 21. Muốn CI chạy riêng các test smoke đã gắn nhãn trong JUnit Jupiter, cách nào phù hợp?
A. Gắn @Tag và cấu hình bộ lọc tag khi chạy
B. Đặt mọi smoke test vào thư mục resources
C. Đổi annotation @Test thành @BeforeAll
D. Bỏ mọi assertion của các test không phải smoke
Đáp án đúng: A

Câu 22. Trong TestNG, nhóm các test regression để chạy có chọn lọc thường dùng gì?
A. @BeforeGroups chỉ để gán test vào nhóm
B. @Parameters dùng thay mọi cấu hình nhóm
C. @DataProvider tự đánh dấu nhóm regression
D. groups trong @Test và cấu hình suite phù hợp
Đáp án đúng: D

Câu 23. Vì sao cần xuất báo cáo kết quả test dạng XML tiêu chuẩn trên CI?
A. Để thay mọi assertion bằng thông báo console
B. Để CI tổng hợp ca pass, fail và thời gian chạy
C. Để tự sinh lại code cần test khi build thất bại
D. Để đảm bảo toàn bộ test dùng một database thật
Đáp án đúng: B

Câu 24. Một bộ test chỉ chạy ổn trên máy tác giả; bước cải thiện tính tái lập nào đáng ưu tiên?
A. Khóa phiên bản, seed dữ liệu và tránh phụ thuộc giờ
B. Tăng timeout mọi test mà không tìm nguồn lỗi
C. Chạy test theo thứ tự lớp ở máy tác giả
D. Giữ lại trạng thái test trước để tiết kiệm setup
Đáp án đúng: A
