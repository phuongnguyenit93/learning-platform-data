Bạn giải thích mục đích của cơ chế exception trong Java so với cách trả về mã lỗi từ phương thức như thế nào?
Bạn mô tả cấu trúc phân cấp `Throwable`, `Error`, `Exception` và `RuntimeException` và ý nghĩa từng nhánh ra sao?
Bạn phân biệt checked exception và unchecked exception dựa trên quy tắc kiểm tra lúc biên dịch như thế nào?
Bạn chọn checked exception hay unchecked exception cho một lỗi nghiệp vụ có thể phục hồi dựa trên tiêu chí nào?
Bạn phân biệt lỗi lập trình, lỗi dữ liệu đầu vào và lỗi tài nguyên bên ngoài khi xác định loại exception như thế nào?
Bạn giải thích tác dụng của từ khóa `throw` so với khai báo `throws` trong chữ ký phương thức như thế nào?
Bạn phân tích điều gì xảy ra với luồng thực thi khi một phương thức ném exception mà không có catch phù hợp ở cấp hiện tại ra sao?
Bạn mô tả cách runtime tìm catch handler tương thích khi exception truyền qua nhiều lời gọi phương thức như thế nào?
Bạn kiểm tra thứ tự các khối `catch` cho exception cha và con để tránh nhánh xử lý không thể truy cập ra sao?
Bạn sử dụng multi-catch để xử lý nhiều exception khác loại có cùng chính sách phục hồi bằng cách nào?
Bạn giải thích vì sao multi-catch không cho phép các kiểu exception có quan hệ kế thừa trực tiếp cùng xuất hiện như thế nào?
Bạn xác định giới hạn khi gán lại biến exception trong một nhánh multi-catch và giải thích nguyên nhân ra sao?
Bạn phân biệt hành vi của `try`, `catch` và `finally` khi thực thi bình thường so với khi có exception như thế nào?
Bạn phân tích giá trị trả về của một phương thức khi cả khối `try` và `finally` đều có lệnh `return` như thế nào?
Bạn giải thích vì sao không nên ném exception mới hoặc trả về trực tiếp trong `finally` nếu đang có lỗi trước đó ra sao?
Bạn kiểm chứng `finally` có luôn thực thi trong mọi tình huống JVM kết thúc bất thường hay không bằng cách nào?
Bạn xác định phạm vi biến khai báo trong `try` và các nhánh `catch` khi tổ chức xử lý lỗi như thế nào?
Bạn chọn giữa bắt và xử lý ngay, chuyển đổi exception hoặc cho exception tiếp tục truyền lên dựa trên trách nhiệm từng tầng như thế nào?
Bạn thiết kế một phương thức có hợp đồng ném checked exception để người gọi nhận biết cách phục hồi ra sao?
Bạn xác định những checked exception nào bắt buộc phải bắt hoặc khai báo khi gọi chuỗi phương thức có `throws` như thế nào?
Bạn giải thích vì sao unchecked exception không bắt buộc xuất hiện trong `throws` nhưng vẫn có thể được tài liệu hóa như thế nào?
Bạn phân tích giới hạn thay đổi khai báo checked exception khi override một phương thức của lớp cha hoặc interface như thế nào?
Bạn kiểm tra tính tương thích của một lambda với functional interface khi thân lambda có thể ném checked exception ra sao?
Bạn giải thích vì sao chỉ thay đổi phần `throws` không tạo ra một overload mới của cùng một phương thức như thế nào?
Bạn chẩn đoán lỗi biên dịch unreachable catch khi nhánh catch không thể bắt exception được phép phát sinh trong try ra sao?
Bạn đánh giá điều gì xảy ra nếu ném `null` bằng câu lệnh `throw` và cách tránh thiết kế phụ thuộc vào hành vi này như thế nào?
Bạn phân biệt `ExceptionInInitializerError` và exception thông thường phát sinh trong phương thức khi khởi tạo class như thế nào?
Bạn xác định nguyên nhân một class có thể phát sinh `NoClassDefFoundError` ở lần sử dụng sau khi static initializer thất bại ra sao?
Bạn đánh giá trường hợp nào nên bắt `Error`, trường hợp nào cần để runtime hoặc tầng giám sát xử lý như thế nào?
Bạn xây dựng exception tùy chỉnh bằng cách kế thừa `Exception` hoặc `RuntimeException` và thiết kế constructor phù hợp ra sao?
Bạn lựa chọn tên, thông điệp và trường dữ liệu cho domain exception để người gọi hiểu tình huống thất bại như thế nào?
Bạn truyền nguyên nhân gốc bằng constructor có `cause` khi chuyển đổi exception qua nhiều tầng ứng dụng ra sao?
Bạn phân biệt `getMessage`, `getCause` và `getStackTrace` trong quá trình chẩn đoán exception như thế nào?
Bạn phân tích trường hợp `getCause` trả về `null` và tác động của việc bỏ mất nguyên nhân khi wrap exception ra sao?
Bạn quyết định khi nào giữ nguyên exception gốc và khi nào tạo exception mới để bảo vệ ranh giới API như thế nào?
Bạn thiết kế một hierarchy domain exception đủ rõ nghĩa mà không tạo quá nhiều lớp chỉ khác tên ra sao?
Bạn duy trì tương thích cho các client khi thay đổi tập checked exception được khai báo trong một public API như thế nào?
Bạn xác định thông tin nào nên xuất hiện trong thông điệp exception và thông tin nào phải tránh đưa vào vì nhạy cảm như thế nào?
Bạn thiết kế mã lỗi ổn định tách khỏi nội dung thông điệp để ứng dụng khách có thể xử lý mà không phải phân tích chuỗi ra sao?
Bạn phân biệt exception dùng để điều khiển luồng bình thường với exception dùng để biểu diễn tình huống thất bại như thế nào?
Bạn đánh giá chi phí tạo exception và thu thập stack trace khi ngoại lệ bị sử dụng liên tục trong một vòng lặp nóng ra sao?
Bạn giải thích ý nghĩa của `StackTraceElement` và cách dùng thông tin này khi điều tra đường đi gây lỗi như thế nào?
Bạn giữ ngữ cảnh nghiệp vụ khi bọc một lỗi I/O nhưng vẫn bảo toàn cause và tránh lặp thông điệp ra sao?
Bạn sử dụng `addSuppressed` và `getSuppressed` để theo dõi nhiều lỗi phát sinh trong cùng một quá trình dọn dẹp như thế nào?
Bạn phân biệt primary exception và suppressed exception khi một thao tác chính và bước đóng tài nguyên đều thất bại như thế nào?
Bạn thiết kế xử lý lỗi khi nhiều tài nguyên cần được đóng và từng thao tác đóng có thể ném exception ra sao?
Bạn giải thích cơ chế hoạt động của `try-with-resources` đối với đối tượng triển khai `AutoCloseable` như thế nào?
Bạn phân biệt hợp đồng của `AutoCloseable` và `Closeable` khi thiết kế một lớp quản lý tài nguyên như thế nào?
Bạn xác định thứ tự đóng nhiều tài nguyên được khai báo trong một câu lệnh `try-with-resources` ra sao?
Bạn phân tích loại exception nào trở thành exception chính nếu thân `try` và phương thức `close` cùng ném lỗi như thế nào?
Bạn sử dụng tài nguyên đã khai báo trước `try-with-resources` và đánh giá điều kiện effectively final áp dụng ra sao?
Bạn thiết kế đối tượng `AutoCloseable` có thao tác `close` idempotent và trạng thái tài nguyên rõ ràng như thế nào?
Bạn so sánh `try-with-resources` với `try-finally` thủ công về khả năng giữ lỗi gốc và khả năng đọc mã như thế nào?
Bạn xác định những đối tượng nào nên được đóng bởi phạm vi hiện tại thay vì đóng trong phương thức mượn tài nguyên như thế nào?
Bạn quản lý một kết nối hoặc stream được trả về từ API để tránh đóng sớm khi caller vẫn còn sử dụng ra sao?
Bạn kiểm thử tình huống một resource đóng thất bại nhưng các resource khác vẫn được yêu cầu đóng như thế nào?
Bạn chẩn đoán file handle hoặc kết nối bị rò rỉ khi một đường đi exception bỏ qua thao tác dọn dẹp như thế nào?
Bạn thiết kế ranh giới transaction để rollback khi có checked hoặc unchecked exception theo chính sách cụ thể ra sao?
Bạn xác định cách giữ trạng thái nhất quán khi một thao tác cập nhật nhiều bước thất bại giữa chừng như thế nào?
Bạn phân biệt lỗi có thể retry và lỗi không nên retry khi ánh xạ exception từ hệ thống bên ngoài ra sao?
Bạn xây dựng cơ chế retry có giới hạn dựa trên loại exception và tình trạng side effect của thao tác ra sao?
Bạn ngăn việc bắt exception quá rộng rồi bỏ qua lỗi khiến dữ liệu hoặc trạng thái hệ thống không nhất quán như thế nào?
Bạn lựa chọn điểm ghi log cho exception để tránh nhiều tầng cùng ghi trùng một stack trace ra sao?
Bạn thiết kế thông điệp log có correlation ID, operation và cause để chẩn đoán mà không lộ dữ liệu nhạy cảm như thế nào?
Bạn phân biệt việc log một exception với việc đã xử lý và phục hồi thành công từ exception đó ra sao?
Bạn xử lý exception ở lớp controller để trả mã trạng thái HTTP và thông điệp lỗi nhất quán như thế nào?
Bạn ánh xạ exception miền nghiệp vụ thành hợp đồng lỗi API mà không để lộ chi tiết implementation như thế nào?
Bạn xử lý ngoại lệ không dự kiến tại ranh giới ứng dụng sao cho vẫn ghi nhận nguyên nhân và tránh che giấu sự cố ra sao?
Bạn xác định thời điểm nên dùng giá trị trả về dạng `Optional` thay vì ném exception cho trường hợp không tìm thấy dữ liệu như thế nào?
Bạn thiết kế kết quả nghiệp vụ bằng kiểu `Result` hoặc đối tượng trạng thái thay cho exception khi thất bại là một nhánh bình thường ra sao?
Bạn phân biệt `IllegalArgumentException`, `IllegalStateException` và `NullPointerException` khi kiểm tra tiền điều kiện như thế nào?
Bạn lựa chọn cách dùng `Objects.requireNonNull` để phát hiện tham số không hợp lệ và mô tả lỗi rõ ràng ra sao?
Bạn xác định quy tắc kiểm tra đầu vào trước khi bắt đầu cập nhật trạng thái để giảm trường hợp lỗi dở dang như thế nào?
Bạn phân tích cách exception tác động đến biểu thức `finally` khi có `break`, `continue` hoặc `return` trong vòng lặp như thế nào?
Bạn xử lý exception phát sinh trong `Stream.map` hoặc `forEach` khi callback khai báo giao diện không cho ném checked exception ra sao?
Bạn đánh giá rủi ro khi bỏ qua exception của từng phần tử trong một batch mà không ghi nhận mục thất bại như thế nào?
Bạn thiết kế kết quả xử lý batch để báo lỗi từng bản ghi và vẫn quyết định được khi nào dừng toàn bộ thao tác ra sao?
Bạn xác định exception được truyền ra ngoài một luồng `Thread` khi phương thức `run` không xử lý nó như thế nào?
Bạn dùng `Thread.UncaughtExceptionHandler` để ghi nhận lỗi chưa xử lý trong worker thread bằng cách nào?
Bạn phân biệt cách exception xuất hiện khi thực thi tác vụ bằng `Executor.execute` và `ExecutorService.submit` như thế nào?
Bạn xử lý `ExecutionException` từ `Future.get` và khôi phục nguyên nhân gốc của tác vụ thất bại ra sao?
Bạn phân biệt `CompletionException`, `ExecutionException` và exception gốc khi sử dụng `CompletableFuture` như thế nào?
Bạn lựa chọn `exceptionally`, `handle` hoặc `whenComplete` để phục hồi hoặc quan sát lỗi trong chuỗi `CompletableFuture` ra sao?
Bạn bảo toàn nguyên nhân khi chuyển đổi lỗi từ một callback bất đồng bộ sang lời gọi đồng bộ như thế nào?
Bạn xử lý `InterruptedException` sao cho giữ đúng yêu cầu hủy hoặc tín hiệu interrupt của luồng như thế nào?
Bạn đánh giá điều gì xảy ra với cờ interrupt khi `InterruptedException` được ném và khi nào cần đặt lại cờ đó ra sao?
Bạn phân biệt `CancellationException` với lỗi thực thi trong các tác vụ bất đồng bộ và thiết kế xử lý từng trường hợp như thế nào?
Bạn thiết kế chính sách dừng tác vụ khi vừa nhận yêu cầu hủy vừa gặp lỗi I/O để không che giấu tín hiệu điều khiển ra sao?
Bạn xử lý exception của một request trong server đa luồng để không ảnh hưởng đến các request độc lập khác như thế nào?
Bạn thiết kế giới hạn retry, backoff và circuit breaker dựa trên phân loại exception mà vẫn ngăn gọi lại thao tác không idempotent ra sao?
Bạn sử dụng JUnit `assertThrows` để kiểm thử đúng kiểu exception và thông tin ngữ cảnh mong đợi như thế nào?
Bạn kiểm thử cause chain và suppressed exceptions để bảo đảm exception không làm mất nguyên nhân gốc ra sao?
Bạn viết kiểm thử chứng minh `finally` chạy khi có exception và nhận diện các trường hợp không thể dựa vào bảo đảm đó như thế nào?
Bạn kiểm thử một đối tượng `AutoCloseable` được đóng đúng một lần khi thân `try` ném exception bằng cách nào?
Bạn phân biệt kiểm thử ném đúng một lớp exception với kiểm thử cho phép lớp con trong JUnit như thế nào?
Bạn thiết kế kiểm thử cho phương thức có nhiều đường đi checked exception, unchecked exception và kết quả thành công ra sao?
Bạn kiểm thử API xử lý đúng khi có exception từ lớp repository nhưng không rò rỉ chi tiết tầng persistence ra sao?
Bạn xây dựng tình huống kiểm thử bảo đảm log và metric phát hiện được exception chưa xử lý mà không ghi trùng lặp như thế nào?
Bạn dùng exception breakpoint trong debugger để truy tìm nơi exception ban đầu được tạo trước khi bị wrap nhiều lớp ra sao?
Bạn chẩn đoán stack trace bị thiếu hoặc khó đọc do tác vụ bất đồng bộ và xác định ngữ cảnh nào cần bổ sung như thế nào?
Bạn đánh giá một catch block đang quá rộng bằng cách xem các kiểu exception, khả năng phục hồi và ảnh hưởng đến dữ liệu ra sao?
Bạn tổ chức review hợp đồng exception của thư viện công khai để người dùng API hiểu khả năng phục hồi và hành vi khi lỗi như thế nào?
Bạn xây dựng nguyên tắc nhất quán về ném, bắt, wrap, ghi log và kiểm thử exception cho một dự án Java như thế nào?
