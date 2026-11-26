Câu 1. Một phương thức gọi `Files.readString(path)` nhưng không bắt ngoại lệ. Khai báo nào giúp xử lý yêu cầu checked exception của lời gọi này?
A. Khai báo `throws FileNotFoundException` ở phương thức
B. Khai báo `throws IOException` ở phương thức
C. Khai báo `throws UncheckedIOException` ở phương thức
D. Khai báo `throws RuntimeException` ở phương thức
Đáp án đúng: B

Câu 2. Hai lớp con trực tiếp của `Throwable` là cặp nào?
A. `Exception` cùng với `Error`
B. `RuntimeException` và `Error`
C. `Exception` và `IOException`
D. `RuntimeException` và `IOException`
Đáp án đúng: A

Câu 3. Cặp nào đều thuộc nhóm unchecked trong cơ chế kiểm tra ngoại lệ của trình biên dịch Java?
A. `IOException` và `Error`
B. `Exception` và `RuntimeException`
C. `InterruptedException` và `Error`
D. `RuntimeException` và `Error`
Đáp án đúng: D

Câu 4. Kiểu cha chung bao quát mọi đối tượng có thể đặt sau lệnh `throw` là gì?
A. `Exception`, gồm cả các checked exception
B. `Throwable`, cha của `Exception` và `Error`
C. `RuntimeException`, gồm ngoại lệ unchecked
D. `Error`, gồm cả lỗi của máy ảo Java
Đáp án đúng: B

Câu 5. Trong Java, phát biểu nào phân biệt đúng `throw` với `throws`?
A. `throw` khai báo lỗi; `throws` bắt ngoại lệ
B. `throw` ném đối tượng; `throws` khai báo lỗi
C. `throw` chỉ dùng trong `catch`; `throws` trong `try`
D. `throw` chỉ dùng với checked; `throws` với unchecked
Đáp án đúng: B

Câu 6. Một khối `try` có cả `catch (IOException e)` và `catch (Exception e)`. Cách sắp xếp nào hợp lệ?
A. Đặt `Exception` trước, rồi đến `IOException`
B. Đặt tùy ý nếu có thêm khối `finally`
C. Đặt `IOException` trước, rồi đến `Exception`
D. Chỉ có thể giữ lại một trong hai nhánh `catch`
Đáp án đúng: C

Câu 7. Đối với `catch (IOException | SQLException e)`, phát biểu nào đúng?
A. Hợp lệ vì hai kiểu không có quan hệ cha con
B. Không hợp lệ vì cả hai đều là checked exception
C. Chỉ hợp lệ khi cả hai đều là unchecked exception
D. Không hợp lệ vì Java cấm bắt nhiều kiểu ngoại lệ
Đáp án đúng: A

Câu 8. Khi phương thức thực hiện `return` trong `try`, `finally` thông thường chạy vào thời điểm nào?
A. Sau khi phương thức đã trả giá trị cho caller
B. Chỉ khi `return` nằm trong nhánh `catch`
C. Chỉ khi có ngoại lệ xảy ra trong thân `try`
D. Trước khi phương thức thực sự trả về caller
Đáp án đúng: D

Câu 9. Khối `try` ném `IOException`, còn khối `finally` ném `IllegalStateException`. Ngoại lệ nào thoát ra ngoài?
A. `IOException` phát sinh từ thân `try`
B. Cả hai dưới dạng lỗi chính và lỗi suppressed
C. `IllegalStateException` phát sinh từ `finally`
D. Java tự gộp chúng thành một đối tượng `Exception`
Đáp án đúng: C

Câu 10. Một tài nguyên được khai báo trong `try (...)` cần đáp ứng điều kiện kiểu nào để tự động đóng?
A. Kiểu tài nguyên triển khai `AutoCloseable`
B. Kiểu tài nguyên triển khai giao diện `Serializable`
C. Kiểu tài nguyên có phương thức tên `dispose()`
D. Kiểu tài nguyên có phương thức tên `finalize()`
Đáp án đúng: A

Câu 11. Với `try (A a = openA(); B b = openB())`, tài nguyên được đóng theo thứ tự nào?
A. Đóng `a` trước, sau đó mới đóng `b`
B. Đóng đồng thời cả `a` và `b` khi kết thúc
C. Đóng `b` trước, sau đó mới đóng `a`
D. Chỉ đóng `b` vì đó là tài nguyên cuối
Đáp án đúng: C

Câu 12. Nếu thân `try` và `close()` cùng ném ngoại lệ trong try-with-resources, kết quả thông thường là gì?
A. Lỗi `close()` thoát ra; lỗi thân `try` bị mất
B. Hai ngoại lệ được ném riêng qua cùng một `try`
C. Lỗi `close()` là chính; lỗi thân `try` là suppressed
D. Lỗi thân `try` là chính; lỗi `close()` là suppressed
Đáp án đúng: D

Câu 13. Muốn lấy các ngoại lệ đã bị suppressed trên một `Throwable`, gọi phương thức nào?
A. Gọi `getMessage()` trên đối tượng ngoại lệ
B. Gọi `getCause()` trên đối tượng ngoại lệ
C. Gọi `getStackTrace()` trên đối tượng ngoại lệ
D. Gọi `getSuppressed()` trên đối tượng ngoại lệ
Đáp án đúng: D

Câu 14. Khi bọc lỗi tầng thấp vào ngoại lệ tầng nghiệp vụ, cách nào giữ được nguyên nhân gốc?
A. Chỉ chép thông điệp lỗi vào ngoại lệ mới
B. Dùng constructor nhận nguyên nhân `cause` gốc
C. Chỉ lưu tên lớp ngoại lệ vào thông điệp
D. Chuyển ngoại lệ gốc thành chuỗi rồi bỏ đi
Đáp án đúng: B

Câu 15. Giả sử `cause` khác chính đối tượng ngoại lệ, khi nào `initCause(cause)` có thể thành công?
A. Khi ngoại lệ hiện tại thuộc nhóm checked exception
B. Khi đối tượng `cause` thuộc nhóm unchecked exception
C. Khi stack trace được tạo lại bằng `fillInStackTrace()`
D. Khi nguyên nhân của đối tượng chưa được khởi tạo
Đáp án đúng: D

Câu 16. Giả sử chữ ký còn lại tương thích, override của phương thức khai báo `throws IOException` có thể khai báo checked exception nào?
A. `throws Exception` trong phương thức override
B. `throws SQLException` trong phương thức override
C. `throws FileNotFoundException` trong override
D. `throws Throwable` trong phương thức override
Đáp án đúng: C

Câu 17. Khi override một phương thức không khai báo `throws`, lớp con có thể thêm ngoại lệ nào vào `throws`?
A. Thêm ngoại lệ `IOException` vào `throws`
B. Thêm ngoại lệ `SQLException` vào `throws`
C. Thêm ngoại lệ `InterruptedException` vào `throws`
D. Thêm `IllegalStateException` vào `throws`
Đáp án đúng: D

Câu 18. Vì sao đặt `catch (FileNotFoundException e)` sau `catch (IOException e)` gây lỗi biên dịch?
A. Nhánh sau đã bị nhánh trước bao phủ hoàn toàn
B. Java chỉ cho phép tối đa một nhánh `catch`
C. `FileNotFoundException` là kiểu unchecked
D. `IOException` chỉ được bắt trong `finally`
Đáp án đúng: A

Câu 19. `try (var in = Files.newInputStream(path)) { ... }` có bắt buộc kèm `catch` hoặc `finally` không?
A. Có, luôn phải có ít nhất một khối `catch`
B. Có, phải có `finally` để thực hiện `close()`
C. Không, khai báo tài nguyên đã đủ cho cú pháp
D. Không, nhưng chỉ khi tài nguyên không ném lỗi
Đáp án đúng: C

Câu 20. Cặp nào đều có thể được bắt bởi `catch (Exception e)`?
A. `IOException` và `OutOfMemoryError`
B. `IOException` và `NullPointerException`
C. `OutOfMemoryError` và `StackOverflowError`
D. `StackOverflowError` và `NullPointerException`
Đáp án đúng: B

Câu 21. Vì sao thường không nên dùng `catch (Throwable e)` để nuốt mọi lỗi rồi tiếp tục công việc?
A. Vì cú pháp `catch (Throwable e)` bị Java cấm
B. Vì `Throwable` chỉ bao gồm checked exception
C. Vì cách đó có thể che giấu các `Error` nghiêm trọng
D. Vì `Throwable` không hỗ trợ việc lấy stack trace
Đáp án đúng: C

Câu 22. Cần đảm bảo đóng `InputStream` kể cả khi đọc gặp lỗi. Cách làm nào phù hợp?
A. Đặt `InputStream` trong try-with-resources
B. Chỉ gọi `close()` sau khi đã đọc đến EOF
C. Chỉ gọi `close()` nếu đi vào nhánh `catch`
D. Chỉ gọi `close()` ở cuối phần thân `try`
Đáp án đúng: A

Câu 23. Với biến kiểu `AutoCloseable` đặt trong try-with-resources, vì sao compiler có thể yêu cầu xử lý `Exception`?
A. Vì mọi lời gọi `close()` đều ném unchecked exception
B. Vì `AutoCloseable.close()` khai báo `throws Exception`
C. Vì mọi khối `try` đều bắt buộc `throws Exception`
D. Vì tài nguyên phải có kiểu chính xác là `Closeable`
Đáp án đúng: B

Câu 24. Khai báo lớp nào tạo ra checked exception tự định nghĩa?
A. `class DataException extends Exception`
B. `class DataException extends RuntimeException`
C. `class DataException extends Error`
D. `class DataException extends AssertionError`
Đáp án đúng: A

Câu 25. Muốn định nghĩa một ngoại lệ nghiệp vụ thuộc nhóm unchecked, nên kế thừa lớp nào?
A. Cho lớp mới kế thừa `IOException`
B. Cho lớp mới kế thừa `Exception`
C. Cho lớp mới kế thừa `Throwable`
D. Cho lớp mới kế thừa `RuntimeException`
Đáp án đúng: D

Câu 26. Một API yêu cầu đối số là số dương nhưng caller truyền số âm. Ngoại lệ unchecked nào diễn đạt phù hợp nhất?
A. Ném một `IllegalStateException` cho tham số
B. Ném một `IndexOutOfBoundsException` cho tham số
C. Ném một `UnsupportedOperationException` cho tham số
D. Ném một `IllegalArgumentException` cho tham số
Đáp án đúng: D

Câu 27. Một phương thức được gọi khi đối tượng chưa `start()`. Ngoại lệ unchecked nào diễn đạt trạng thái không hợp lệ?
A. `IllegalStateException` cho trạng thái đối tượng
B. `IllegalArgumentException` cho trạng thái đối tượng
C. `UnsupportedOperationException` cho trạng thái đối tượng
D. `ClassCastException` cho trạng thái đối tượng
Đáp án đúng: A

Câu 28. Phát biểu nào đúng về `NullPointerException`?
A. Là checked exception nên buộc khai báo `throws`
B. Là unchecked exception nên không buộc khai báo `throws`
C. Là lớp con trực tiếp của `Error` trong Java
D. Chỉ xuất hiện khi lập trình viên gọi `throw`
Đáp án đúng: B

Câu 29. Lựa chọn nào là checked exception trong Java?
A. Đối tượng kiểu `IOException`
B. Đối tượng kiểu `IllegalArgumentException`
C. Đối tượng kiểu `NullPointerException`
D. Đối tượng kiểu `ArithmeticException`
Đáp án đúng: A

Câu 30. Sau khi lời gọi chặn ném `InterruptedException` và xóa cờ ngắt, nếu không thể ném tiếp thì nên làm gì?
A. Gọi `Thread.interrupted()` để khôi phục cờ ngắt
B. Bọc lỗi thành `NullPointerException` rồi ném tiếp
C. Bỏ qua lỗi vì cờ ngắt luôn tự giữ nguyên
D. Đặt lại cờ bằng `Thread.currentThread().interrupt()`
Đáp án đúng: D

Câu 31. Tác vụ do `ExecutorService.submit(...)` chạy thất bại. `Future.get()` thường ném gì?
A. `IOException` chứa ngoại lệ gốc từ tác vụ
B. `RuntimeException` nguyên gốc từ tác vụ
C. `ExecutionException` chứa ngoại lệ gốc từ tác vụ
D. `InterruptedException` chứa ngoại lệ gốc từ tác vụ
Đáp án đúng: C

Câu 32. Khi `Future.get()` ném `ExecutionException`, phương thức nào lấy được lỗi gốc?
A. Gọi `getSuppressed()` trên `ExecutionException`
B. Gọi `getCause()` trên `ExecutionException`
C. Gọi `fillInStackTrace()` trên `ExecutionException`
D. Gọi `getLocalizedMessage()` trên `ExecutionException`
Đáp án đúng: B

Câu 33. Nếu `try` chỉ có `catch (RuntimeException e)`, lời gọi có thể ném `IOException` phải được xử lý thế nào?
A. Nhánh `RuntimeException` đã xử lý luôn `IOException`
B. JVM tự chuyển `IOException` thành `RuntimeException`
C. Vẫn phải bắt hoặc khai báo checked `IOException`
D. Chỉ cần thêm `finally` là trình biên dịch chấp nhận
Đáp án đúng: C

Câu 34. Phương thức chỉ khai báo `throws IOException` mà không có `catch`. Phát biểu nào đúng?
A. IOException có thể lan đến caller khi thực sự phát sinh
B. JVM lập tức tạo IOException khi phương thức bắt đầu
C. Compiler tự ghi log IOException trước khi phương thức trả
D. Mọi IOException đều được xử lý ngay trong phương thức
Đáp án đúng: A

Câu 35. Khi ném một ngoại lệ trong `try` có nhiều nhánh `catch` hợp lệ, Java chọn nhánh nào?
A. Nhánh cuối cùng có kiểu có thể bắt ngoại lệ đó
B. Nhánh đầu tiên từ trên xuống có kiểu bắt phù hợp
C. Nhánh có kiểu hẹp nhất bất kể thứ tự khai báo
D. Tất cả nhánh có kiểu phù hợp đều được thực thi
Đáp án đúng: B

Câu 36. Tham số `e` trong `catch (IOException | SQLException e)` được Java xử lý như thế nào?
A. Cho phép gán lại `e` thành một `IOException` mới
B. Cho phép gán lại `e` thành một `SQLException` mới
C. Biến `e` ngầm là `final`, không thể gán lại
D. Cho phép gán lại `e` sau khi gọi `getCause()`
Đáp án đúng: C

Câu 37. Vì sao `System.out.println("x");` ngay sau `throw new IllegalArgumentException();` trong cùng khối gây lỗi biên dịch?
A. Vì câu lệnh `println` chắc chắn không thể chạy tới
B. Vì `IllegalArgumentException` buộc khai báo `throws`
C. Vì `println` chỉ được gọi trong khối `catch`
D. Vì câu lệnh `throw` chỉ được viết trong `catch`
Đáp án đúng: A

Câu 38. Trong `try (A a = openA(); B b = openB())`, nếu `openB()` ném lỗi sau khi `a` được tạo, Java làm gì?
A. Giữ `a` mở vì phần thân `try` chưa chạy
B. Đóng `a` rồi lan truyền lỗi từ `openB()`
C. Chỉ đóng `b` còn `a` tiếp tục mở
D. Tiếp tục vào thân `try` với `b` là `null`
Đáp án đúng: B

Câu 39. Biến tài nguyên khai báo trong `try (Resource r = ...)` có phạm vi sử dụng nào?
A. Từ khai báo đến hết khối `catch` sau đó
B. Chỉ trong phần khai báo và phần thân `try`
C. Từ khai báo đến hết khối `finally` sau đó
D. Từ khai báo đến hết phương thức đang gọi
Đáp án đúng: B

Câu 40. Trong `try`–`catch`–`finally`, nếu `catch` xử lý xong bình thường, điều gì xảy ra tiếp?
A. Khối `finally` bị bỏ qua do lỗi đã được bắt
B. Java chạy lại khối `try` để kiểm tra lần nữa
C. Java tự ném lại ngoại lệ mà `catch` vừa xử lý
D. Khối `finally` chạy trước khi sang lệnh tiếp theo
Đáp án đúng: D

Câu 41. Phát biểu nào phân biệt đúng `getMessage()` và `getCause()` trên `Throwable`?
A. `getMessage()` lấy stack trace; `getCause()` lấy vị trí lỗi
B. `getMessage()` lấy mô tả; `getCause()` lấy ngoại lệ nguồn
C. `getMessage()` lấy suppressed; `getCause()` lấy stack trace
D. `getMessage()` lấy mã lỗi; `getCause()` lấy thời gian lỗi
Đáp án đúng: B

Câu 42. Tính năng precise rethrow cho phép gì khi `catch (Exception e)` ném lại `e` và không gán lại biến này?
A. Suy luận các checked exception từ khối `try`
B. Tự chuyển mọi checked exception thành unchecked
C. Tự xóa các checked exception khỏi chữ ký `throws`
D. Cấm `throw e` nếu khai báo kiểu biến là `Exception`
Đáp án đúng: A

Câu 43. Với Java từ phiên bản 9, biến tài nguyên khai báo trước có thể dùng trong `try (resource)` khi nào?
A. Biến là `volatile` và có kiểu `AutoCloseable`
B. Biến là `static` và có kiểu `AutoCloseable`
C. Biến được gán lại trong `try` và có kiểu `AutoCloseable`
D. Biến final/effectively final, có kiểu `AutoCloseable`
Đáp án đúng: D

Câu 44. Nếu thân try-with-resources thực hiện `return`, `close()` thường chạy vào thời điểm nào?
A. Sau khi caller đã nhận giá trị trả về
B. Chỉ khi thân `try` xuất hiện ngoại lệ
C. Trước khi giá trị trả về rời phương thức
D. Chỉ sau khi caller gọi lại phương thức
Đáp án đúng: C

Câu 45. Khi bắt `IOException e` rồi thực hiện `throw e;`, điều nào đúng về đối tượng ngoại lệ được ném?
A. Java tạo một `IOException` mới cùng thông điệp
B. Java bọc ngoại lệ này trong một `RuntimeException`
C. Java ném lại cùng đối tượng `IOException` đã bắt
D. Java loại bỏ stack trace trước khi ném đối tượng
Đáp án đúng: C

Câu 46. Với JUnit Jupiter, `assertThrows(IOException.class, executable)` đạt khi điều kiện nào đúng?
A. Lệnh không ném ngoại lệ nào trong lúc kiểm thử
B. Lệnh ném một đối tượng thuộc bất kỳ lớp `Throwable`
C. Lệnh ném chính xác `IOException`, không chấp nhận lớp con
D. Lệnh ném `IOException` hoặc một lớp con của nó
Đáp án đúng: D

Câu 47. Trong JUnit Jupiter, cách nào yêu cầu kiểu ngoại lệ khớp chính xác và không chấp nhận lớp con?
A. Dùng `assertThrowsExactly()` với kiểu mong đợi
B. Dùng `assertThrows()` với kiểu mong đợi
C. Dùng `assertDoesNotThrow()` với kiểu mong đợi
D. Dùng `assertTimeout()` với kiểu mong đợi
Đáp án đúng: A

Câu 48. Trong `catch (IOException e)`, muốn chuyển lỗi thành unchecked và giữ nguyên nhân, lệnh nào phù hợp?
A. `throw new IOException("Đọc thất bại", e);`
B. `throw new RuntimeException("Đọc thất bại");`
C. `throw new UncheckedIOException("Đọc thất bại", e);`
D. `throw new IllegalStateException("Đọc thất bại");`
Đáp án đúng: C
