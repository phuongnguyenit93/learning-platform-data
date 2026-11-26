Bạn xác định ranh giới của một unit test đối với một hàm hoặc lớp Java có nhiều phụ thuộc như thế nào?
Bạn phân biệt kiểm thử một hành vi công khai với kiểm thử chi tiết cài đặt nội bộ và giải thích tác động đến khả năng refactor ra sao?
Bạn lựa chọn các tình huống kiểm thử từ hợp đồng đầu vào, đầu ra và bất biến của một method như thế nào?
Bạn đặt tên unit test để người đọc hiểu điều kiện, hành động và kết quả mong đợi mà không cần mở phần thân ra sao?
Bạn tổ chức cấu trúc Arrange, Act, Assert để một bài test chỉ có mục đích chính rõ ràng như thế nào?
Bạn quyết định khi nào nên tách các assertion của nhiều hành vi thành các test độc lập ra sao?
Bạn sử dụng JUnit Jupiter @Test, @BeforeEach và @AfterEach để xây dựng fixture có vòng đời phù hợp như thế nào?
Bạn phân biệt việc tạo fixture ở @BeforeAll với @BeforeEach khi dữ liệu hoặc đối tượng có thể bị thay đổi ra sao?
Bạn sử dụng @Nested trong JUnit Jupiter để mô tả các trạng thái và điều kiện nghiệp vụ có liên hệ như thế nào?
Bạn xác định bộ giá trị biên cho một hàm kiểm tra khoảng số nguyên và kiểm chứng các điểm ngay trong, ngay ngoài giới hạn ra sao?
Bạn thiết kế trường hợp dữ liệu rỗng, chỉ một phần tử, nhiều phần tử và giá trị null cho một thuật toán xử lý danh sách như thế nào?
Bạn áp dụng phân hoạch tương đương để giảm số lượng dữ liệu kiểm thử nhưng vẫn bảo vệ những nhánh hành vi khác nhau ra sao?
Bạn dùng JUnit parameterized test với @ValueSource, @CsvSource hoặc @MethodSource trong những tình huống nào?
Bạn xây dựng nguồn dữ liệu cho parameterized test để mỗi trường hợp thất bại chỉ ra nguyên nhân cụ thể như thế nào?
Bạn lựa chọn assertions của AssertJ để diễn đạt tập kết quả, thứ tự phần tử và thuộc tính đối tượng theo nghĩa nghiệp vụ ra sao?
Bạn kiểm chứng ngoại lệ bằng JUnit hoặc AssertJ như thế nào để phân biệt đúng loại lỗi và thông tin ngữ cảnh cần thiết?
Bạn thiết kế assertion kiểm tra số thực gần đúng để không phụ thuộc vào sai số biểu diễn dấu phẩy động ra sao?
Bạn kiểm thử một hàm phân tích thời gian với timezone và ngày chuyển đổi giờ mùa hè bằng cách lựa chọn dữ liệu như thế nào?
Bạn làm thế nào để loại bỏ phụ thuộc vào đồng hồ thực bằng Clock hoặc cơ chế truyền thời gian vào lớp cần kiểm thử?
Bạn thay thế các yếu tố ngẫu nhiên hoặc định danh sinh tự động bằng phụ thuộc có thể điều khiển để unit test tái lập ra sao?
Bạn xác định một phụ thuộc cần fake, stub hay mock dựa trên kết quả mà unit test phải quan sát như thế nào?
Bạn dùng Mockito để cấu hình phản hồi của một repository khi lớp service gặp dữ liệu có hoặc không tồn tại ra sao?
Bạn kiểm chứng tương tác với Mockito khi sự tương tác đó là một phần của hợp đồng hành vi thay vì chi tiết nội bộ như thế nào?
Bạn nhận diện dấu hiệu lạm dụng verify hoặc verifyNoMoreInteractions khiến unit test giòn và khó refactor ra sao?
Bạn dùng ArgumentCaptor khi nội dung yêu cầu gửi cho một cộng tác viên quan trọng hơn giá trị trả về như thế nào?
Bạn phân biệt mock và spy trong Mockito và đánh giá rủi ro khi spy gọi vào logic thực không mong muốn ra sao?
Bạn tổ chức kiểm thử các nhánh thành công, ngoại lệ và timeout của một service phụ thuộc HTTP client như thế nào?
Bạn kiểm tra rằng khi validation thất bại, service không thực hiện lệnh ghi hoặc phát sự kiện như thế nào?
Bạn thiết kế kiểm thử bất biến của một đối tượng khi nhiều method cập nhật trạng thái liên tiếp ra sao?
Bạn lựa chọn dùng test factory hoặc builder để tạo dữ liệu đầu vào rõ nghĩa và tránh fixture lớn khó đọc như thế nào?
Bạn làm thế nào để test không thay đổi trạng thái dùng chung và vẫn cho cùng kết quả khi chạy riêng lẻ hoặc chạy song song?
Bạn phát hiện một unit test phụ thuộc thứ tự thực thi hoặc vào trạng thái tĩnh và khắc phục nó như thế nào?
Bạn xây dựng unit test cho hàm đệ quy để kiểm tra điều kiện dừng và tình huống sâu bất thường ra sao?
Bạn kiểm thử một thuật toán sắp xếp để xác nhận đúng thứ tự, giữ nguyên tập phần tử và xử lý giá trị trùng như thế nào?
Bạn lựa chọn test theo ví dụ hay property-based testing để phát hiện lỗi thuật toán trên không gian đầu vào rộng ra sao?
Bạn xây dựng property như tính giao hoán, tính idempotent hoặc khả năng round-trip để kiểm chứng hàm chuyển đổi dữ liệu như thế nào?
Bạn dùng test doubles để kiểm thử một CompletableFuture thành công, thất bại hoặc bị hủy mà không chờ thời gian thực ra sao?
Bạn thiết kế kiểm thử tác vụ bất đồng bộ với timeout có kiểm soát để tránh treo cả suite như thế nào?
Bạn kiểm chứng sự kiện được phát sau khi điều kiện được thỏa mãn mà không làm test phụ thuộc vào lịch thực thi ngẫu nhiên ra sao?
Bạn thiết kế unit test cho code đa luồng để kiểm tra bất biến dữ liệu mà không tạo cảm giác an toàn giả từ vài lần chạy thành công như thế nào?
Bạn phân biệt các lỗi unit test flaky do thời gian, thứ tự, randomness và shared state bằng dấu hiệu nào?
Bạn sử dụng @Timeout của JUnit Jupiter phù hợp với mục tiêu phát hiện treo và tránh ngưỡng quá nhạy ra sao?
Bạn đánh giá nên mock lớp biên hạ tầng hay chạy một integration test thực khi cần xác minh SQL hoặc cấu hình HTTP như thế nào?
Bạn xác định mức độ chi tiết của test đối với logic thuần để mỗi thay đổi nghiệp vụ có bằng chứng hồi quy rõ ràng ra sao?
Bạn dùng line coverage và branch coverage để nhận diện vùng thiếu kiểm thử nhưng không đánh đồng coverage với chất lượng như thế nào?
Bạn phân tích trường hợp code coverage cao nhưng một điều kiện sai vẫn không bị test phát hiện ra sao?
Bạn sử dụng mutation testing để đánh giá khả năng bắt lỗi của assertions và phân loại mutant sống sót như thế nào?
Bạn xem xét equivalent mutant và chi phí chạy mutation test trước khi chọn ngưỡng mutation score như thế nào?
Bạn xác định khi nào một test chỉ lặp lại chính biểu thức của implementation và cần một oracle độc lập hơn ra sao?
Bạn tối ưu thời gian chạy unit test bằng cách loại bỏ I/O và khởi tạo framework không cần thiết như thế nào?
Bạn tổ chức unit test trong Maven hoặc Gradle để có thể chạy nhanh tại máy lập trình viên và trong CI ra sao?
Bạn đánh giá khi nào cần bổ sung test trước một đợt refactor nhằm bảo vệ hành vi hiện tại như thế nào?
Khi một test thất bại sau refactor nhưng hành vi công khai vẫn đúng, bạn xác định test đã phụ thuộc chi tiết cài đặt nào ra sao?
Bạn trình bày thông điệp assertion thất bại sao cho người sửa hiểu đầu vào, giá trị mong đợi và giá trị thực tế như thế nào?
Bạn dùng xu hướng lỗi hồi quy, độ ổn định và mutation score để chọn khu vực cần cải thiện bộ unit test như thế nào?
