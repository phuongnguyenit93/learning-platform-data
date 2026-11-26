Câu 1: Trong JUnit 5, assertEquals(expected, actual) chủ yếu kiểm chứng điều gì?
A. Hai giá trị bằng nhau theo cách so sánh phù hợp của kiểu
B. Hai biến luôn trỏ cùng một instance trong bộ nhớ
C. Hai đối tượng luôn có cùng mã định danh JVM
D. Hai biến luôn được khởi tạo ở cùng một thời điểm
Đáp án đúng: A

Câu 2: Khi cần xác nhận hai biến tham chiếu đúng một object Java, nên dùng gì?
A. assertEquals(expected, actual) để so sánh identity
B. assertArrayEquals(expected, actual) để so sánh identity
C. assertSame(expected, actual) để so sánh identity
D. assertIterableEquals(expected, actual) để so sánh identity
Đáp án đúng: C

Câu 3: assertNotNull(result) trong JUnit xác nhận điều gì?
A. Mọi trường của result đã được khởi tạo hợp lệ
B. Tham chiếu result khác null, chưa nói dữ liệu đúng
C. result bằng đối tượng mong đợi theo equals
D. result không thể bị thay đổi sau thời điểm kiểm tra
Đáp án đúng: B

Câu 4: Khi cần chạy nhiều assertion và tổng hợp tất cả thất bại, JUnit 5 hỗ trợ gì?
A. assertTimeout với nhóm Executable độc lập để kiểm tra
B. assertThrows với nhóm Executable độc lập để kiểm tra
C. assertAll với nhóm Executable độc lập để kiểm tra
D. assertDoesNotThrow với nhóm Executable độc lập để kiểm tra
Đáp án đúng: C

Câu 5: Trong JUnit 5, assertThrows(IllegalArgumentException.class, ...) cho phép gì?
A. Chỉ ngoại lệ có class đúng hoàn toàn mới thành công
B. Chỉ ngoại lệ phát sinh từ constructor mới thành công
C. Ngoại lệ đúng kiểu đã nêu hoặc kiểu kế thừa
D. Ngoại lệ bất kỳ nếu message đúng với kỳ vọng
Đáp án đúng: C

Câu 6: Muốn khẳng định exception phải đúng class, không nhận subclass, dùng gì?
A. assertThrows với kiểu ngoại lệ được yêu cầu
B. assertThrowsExactly với kiểu ngoại lệ được yêu cầu
C. assertDoesNotThrow với kiểu ngoại lệ được yêu cầu
D. assertAll với kiểu ngoại lệ được yêu cầu
Đáp án đúng: B

Câu 7: Trong kiểm thử hàm parse hợp lệ, assertDoesNotThrow có ý nghĩa gì?
A. Khẳng định lời gọi luôn trả về object khác null
B. Khẳng định lời gọi không ném ngoại lệ trong đoạn thử
C. Khẳng định lời gọi không ghi bất cứ dòng log nào
D. Khẳng định lời gọi chạy dưới một giây trong CI
Đáp án đúng: B

Câu 8: Khi dùng JUnit assertTimeout, thời lượng vượt ngưỡng thường được xử lý thế nào?
A. Báo assertion fail sau khi tác vụ kết thúc quá hạn
B. Luôn ngắt thread thực thi tại đúng thời điểm hết hạn
C. Luôn hủy tất cả future của tác vụ khi hết hạn
D. Luôn rollback transaction đang chạy tại thời điểm đó
Đáp án đúng: A

Câu 9: Vì sao assertTimeoutPreemptively cần cân nhắc với test dùng ThreadLocal transaction?
A. Executable chạy ở thread khác nên context có thể không truyền
B. Executable luôn thực thi cùng thread như gọi assertTimeout
C. Executable tự sao chép mọi ThreadLocal sang thread mới
D. Executable luôn chạy tuần tự sau khi transaction commit
Đáp án đúng: A

Câu 10: Với AssertJ, assertThat(user).isEqualTo(expected) dựa vào gì?
A. Phép so sánh mọi trường lồng nhau bất kể equals
B. Phép so sánh cùng reference ở heap thay cho equals
C. Phép so sánh JSON serialization của mọi thuộc tính
D. Cách so sánh bằng nhau của đối tượng, thường là equals
Đáp án đúng: D

Câu 11: Muốn so sánh sâu nội dung DTO lồng nhau bằng AssertJ, chọn gì?
A. isSameAs(expected) để so sánh mọi thuộc tính con
B. hasSameHashCodeAs(expected) để so sánh toàn bộ DTO
C. hasToString(expected) để so sánh toàn bộ DTO
D. usingRecursiveComparison().isEqualTo(expected)
Đáp án đúng: D

Câu 12: Khi thứ tự phần tử List là một phần hợp đồng, AssertJ nên kiểm tra gì?
A. containsExactly để kiểm tra cả nội dung và thứ tự
B. containsExactlyInAnyOrder để kiểm tra cả thứ tự
C. containsAnyOf để kiểm tra toàn bộ nội dung có thứ tự
D. containsOnlyOnce để kiểm tra toàn bộ danh sách có thứ tự
Đáp án đúng: A

Câu 13: Khi danh sách kết quả không yêu cầu thứ tự nhưng phải đủ các phần tử, dùng gì?
A. containsExactly với phần tử mong đợi
B. containsAnyOf với phần tử mong đợi
C. containsOnlyOnce với phần tử mong đợi
D. containsExactlyInAnyOrder với phần tử mong đợi
Đáp án đúng: D

Câu 14: Với List<OrderDto>, cách kiểm tra các mã order mà không lệ thuộc các field khác?
A. extracting(OrderDto::getId) rồi assert danh sách ID
B. isSameAs(orderDtos) rồi assert danh sách ID
C. hasSameHashCodeAs(orderDtos) rồi assert danh sách ID
D. isInstanceOf(List.class) rồi assert danh sách ID
Đáp án đúng: A

Câu 15: Khi xác nhận một Map có cặp khóa-giá trị cụ thể, AssertJ hỗ trợ gì?
A. containsExactly(key, value) trên assertion của map
B. containsEntry(key, value) trên assertion của map
C. hasFieldOrProperty(key, value) trên assertion map
D. containsOnlyKeys(key, value) trên assertion của map
Đáp án đúng: B

Câu 16: Nếu muốn kiểm tra quy tắc áp dụng cho từng phần tử collection, nên dùng gì?
A. anySatisfy với assertion trên từng phần tử
B. singleElement với assertion trên từng phần tử
C. allSatisfy với assertion trên từng phần tử
D. first với assertion trên từng phần tử
Đáp án đúng: C

Câu 17: Để chứng minh một collection có đúng ba phần tử, nên dùng gì?
A. isNotEmpty() thay vì kiểm tra kích thước
B. hasSameSizeAs(3) thay vì kiểm tra kích thước
C. isNotNull() thay vì kiểm tra kích thước
D. hasSize(3) thay vì chỉ kiểm tra không rỗng
Đáp án đúng: D

Câu 18: Với AssertJ, cách xác minh loại ngoại lệ và một đoạn message là gì?
A. assertThatCode(...).doesNotThrowAnyException().hasMessage(...)
B. assertThat(result).isNotNull().hasMessageContaining(...)
C. assertThatThrownBy(...).isEqualTo(...).hasSize(...)
D. assertThatThrownBy(...).isInstanceOf(...).hasMessageContaining(...)
Đáp án đúng: D

Câu 19: Khi ServiceException bọc IOException, làm sao xác nhận nguyên nhân gốc bằng AssertJ?
A. Kiểm tra cause bằng hasCauseInstanceOf(IOException.class)
B. Kiểm tra cause bằng hasMessage(IOException.class)
C. Kiểm tra cause bằng isSameAs(IOException.class)
D. Kiểm tra cause bằng contains(IOException.class)
Đáp án đúng: A

Câu 20: Với BigDecimal("1.0") và BigDecimal("1.00"), so sánh số học nào phù hợp?
A. isSameAs để bỏ khác biệt scale của đối tượng
B. hasSameHashCodeAs để bỏ khác biệt scale
C. isEqualByComparingTo để bỏ khác biệt scale
D. isEqualTo để luôn bỏ khác biệt scale trong equals
Đáp án đúng: C

Câu 21: Khi kiểm tra kết quả double của phép tính có sai số làm tròn, nên dùng gì?
A. isEqualTo(expected) và bỏ mọi sai số làm tròn
B. isSameAs(expected) và dùng identity của double
C. isCloseTo(expected, within(delta)) với dung sai
D. isNotNaN() để xác nhận số đã đúng kỳ vọng
Đáp án đúng: C

Câu 22: Khi hàm được kỳ vọng trả Double.NaN, AssertJ có assertion nào rõ nghĩa?
A. isZero() để xác nhận giá trị không phải số
B. isNaN() để xác nhận giá trị không phải số
C. isNegative() để xác nhận giá trị không phải số
D. isFinite() để xác nhận giá trị không phải số
Đáp án đúng: B

Câu 23: Với logic phụ thuộc thời gian hiện tại, thiết kế nào giúp assertion lặp lại được?
A. Gọi Instant.now() ở hai phía rồi so sánh bằng nhau
B. Dùng Thread.sleep để đồng bộ hai thời điểm đang chạy
C. Dùng múi giờ mặc định của máy và bỏ qua offset
D. Tiêm Clock cố định và so sánh Instant được dự đoán
Đáp án đúng: D

Câu 24: Khi kiểm tra hai Instant biểu diễn cùng thời điểm nhưng khác cách hiển thị múi giờ, nên làm gì?
A. So sánh tên timezone và bỏ qua epoch timestamp
B. So sánh phần giờ-phút và bỏ qua ngày tháng
C. So sánh định dạng chữ mà không xét offset
D. So sánh giá trị Instant thay vì chuỗi giờ địa phương
Đáp án đúng: D

Câu 25: Với CompletableFuture kết thúc bất đồng bộ, cách lấy giá trị có hạn chờ để assert là gì?
A. Gọi future.get(timeout, unit) rồi so sánh kết quả
B. Gọi future.get() và bỏ qua mọi giới hạn chờ
C. Gọi future.join() rồi tin rằng luôn có giới hạn chờ
D. Gọi future.isDone() rồi coi đã biết giá trị trả về
Đáp án đúng: A

Câu 26: Khi CompletableFuture.join() thất bại do tác vụ ném lỗi, nên assert lớp bọc nào?
A. ExecutionException ngay tại mọi lần gọi join
B. TimeoutException ngay khi tác vụ ném lỗi runtime
C. CompletionException và kiểm tra cause nếu cần
D. InterruptedException ngay khi tác vụ ném lỗi runtime
Đáp án đúng: C

Câu 27: Vì sao assertion so sánh toàn bộ stack trace dạng chuỗi thường mong manh?
A. Stack trace luôn có nội dung ổn định trên mọi JDK
B. Nội dung phụ thuộc runtime, line number và thư viện
C. Stack trace không thể chứa các thông tin từ thư viện
D. Stack trace luôn giống nhau giữa lần chạy song song
Đáp án đúng: B

Câu 28: Vì sao chỉ assert HTTP status 200 thường không đủ khi kiểm thử nghiệp vụ?
A. Mã 200 tự chứng minh mọi dữ liệu response hợp lệ
B. Cần đối chiếu thêm body và invariant quan trọng
C. Mã 200 tự chứng minh database đã lưu đúng transaction
D. Mã 200 tự chứng minh không có dữ liệu nhạy cảm bị lộ
Đáp án đúng: B
