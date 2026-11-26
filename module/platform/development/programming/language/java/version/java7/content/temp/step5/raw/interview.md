Những cải tiến nào được giới thiệu từ Java 7 vẫn có giá trị trên JDK hiện đại, và bạn xác định phạm vi áp dụng của chúng trong một dự án đang bảo trì ra sao?
Khi nâng một dự án viết theo phong cách Java 7 lên JDK hiện đại, bạn kiểm tra những rủi ro tương thích nào trước khi thay đổi mã nguồn?
Try-with-resources quản lý vòng đời tài nguyên như thế nào, và nó giúp tránh kiểu lỗi nào khi xử lý I/O hoặc JDBC?
Bạn phân biệt hợp đồng AutoCloseable và Closeable như thế nào khi thiết kế lớp quản lý tài nguyên của riêng mình?
Trong try-with-resources có nhiều tài nguyên, bạn giải thích thứ tự khởi tạo và đóng tài nguyên cùng ảnh hưởng của thứ tự đó ra sao?
Nếu cả phần xử lý chính và phương thức close đều ném ngoại lệ, bạn sẽ xác định ngoại lệ chính và các ngoại lệ suppressed bằng cách nào?
Bạn xây dựng nhật ký và cách kiểm thử cho lỗi xảy ra trong lúc đóng tài nguyên để không đánh mất nguyên nhân ban đầu như thế nào?
Khi phương thức khởi tạo tài nguyên thứ hai thất bại, try-with-resources xử lý tài nguyên đã được khởi tạo trước đó ra sao?
Bạn tổ chức nhiều Connection, PreparedStatement và ResultSet trong try-with-resources để thể hiện rõ quyền sở hữu và thời điểm giải phóng như thế nào?
Bạn quyết định khi nào một hàm nên tự đóng tài nguyên và khi nào nên chuyển quyền sở hữu tài nguyên cho hàm gọi ra sao?
Bạn giải thích khác biệt giữa cú pháp khai báo tài nguyên của Java 7 và cú pháp dùng biến effectively final được bổ sung sau này như thế nào?
Với một Stream từ Files.lines hoặc Files.walk, bạn xác định nơi cần try-with-resources để tránh giữ tay nắm tệp quá lâu ra sao?
Bạn tổ chức cleanup cho tài nguyên phụ thuộc nhau như thế nào để các ngoại lệ close không che khuất lỗi nghiệp vụ?
Khi một tài nguyên chỉ hỗ trợ thao tác bất đồng bộ, bạn đánh giá giới hạn của try-with-resources và cách quản lý vòng đời phù hợp ra sao?
Multi-catch giải quyết vấn đề gì khi nhiều ngoại lệ cần chung cách xử lý, và trong trường hợp nào bạn vẫn nên dùng các nhánh catch riêng?
Bạn phân tích ràng buộc quan hệ kế thừa giữa các loại ngoại lệ trong một multi-catch như thế nào?
Vì sao tham số ngoại lệ của multi-catch không thể được gán lại, và điều đó ảnh hưởng thế nào đến cách viết mã xử lý lỗi?
Bạn quyết định mức thông tin cần ghi log và cách giữ nguyên nguyên nhân lỗi khi dùng multi-catch cho I/O và thao tác dữ liệu ra sao?
Cơ chế precise rethrow giúp trình biên dịch xác định ngoại lệ được ném lại như thế nào trong phương thức khai báo throws?
Bạn thiết kế kiểm thử cho đường đi thành công và thất bại của một phương thức dùng multi-catch cùng try-with-resources như thế nào?
Diamond operator suy luận tham số kiểu generic khi khởi tạo đối tượng như thế nào, và bạn kiểm tra kiểu suy luận bằng cách nào?
Bạn so sánh diamond operator với raw type về kiểm tra kiểu lúc biên dịch và nguy cơ lỗi khi chạy như thế nào?
Trong một lệnh khởi tạo generic lồng nhau, bạn lựa chọn giữa diamond operator và khai báo kiểu tường minh dựa trên tiêu chí gì?
Bạn giải thích ảnh hưởng của target typing và ngữ cảnh gán đối với kết quả suy luận kiểu của diamond operator ra sao?
Bạn nhận diện giới hạn sử dụng diamond operator trong mã nguồn Java 7 và những mở rộng hợp lệ trên JDK hiện đại như thế nào?
Bạn xử lý tình huống trình biên dịch không suy luận được kiểu generic mong muốn khi gọi constructor overload bằng cách nào?
Switch trên String so sánh các nhánh case theo cơ chế nào, và bạn kiểm tra hành vi với chữ hoa, chữ thường và Unicode ra sao?
Khi giá trị String đưa vào switch có thể là null, bạn thiết kế cách kiểm tra đầu vào và xử lý nhánh mặc định như thế nào?
Bạn chọn giữa switch trên String, enum và bảng tra cứu Map cho một bộ quy tắc phân loại dữ liệu dựa trên những tiêu chí gì?
Bạn đánh giá khi nào nên giữ switch statement theo cú pháp Java 7 và khi nào nên chuyển sang switch expression trên JDK hiện đại ra sao?
Binary literal và dấu gạch dưới trong numeric literal giúp mã xử lý bitmask dễ đọc hơn như thế nào, và bạn tránh các vị trí đặt dấu không hợp lệ bằng cách nào?
Bạn kiểm thử các thao tác bitmask dùng binary literal để tránh nhầm lẫn về độ rộng kiểu số và bit dấu như thế nào?
Path và java.io.File khác nhau như thế nào về biểu diễn đường dẫn và khả năng thao tác hệ thống tệp?
Bạn kết hợp Path.resolve, resolveSibling và relativize như thế nào khi tạo đường dẫn cho cấu trúc thư mục có thể di chuyển?
Bạn phân biệt Path.normalize với Path.toRealPath trong việc xử lý dấu chấm, liên kết tượng trưng và kiểm tra đường dẫn ra sao?
Bạn thiết kế cách xử lý đường dẫn tương đối, đường dẫn tuyệt đối và working directory để ứng dụng chạy nhất quán trên nhiều môi trường như thế nào?
Bạn sử dụng Files.newBufferedReader và Files.newBufferedWriter với charset xác định để xử lý văn bản đa ngôn ngữ như thế nào?
Bạn so sánh đọc toàn bộ nội dung tệp vào bộ nhớ với đọc theo luồng dựa trên kích thước dữ liệu và giới hạn tài nguyên ra sao?
Bạn lựa chọn giữa Files.copy, Files.move và Files.write khi cập nhật dữ liệu tệp để bảo toàn tính toàn vẹn của kết quả như thế nào?
Khi cần thay thế một tệp cấu hình một cách nguyên tử, bạn xử lý ATOMIC_MOVE và trường hợp filesystem không hỗ trợ tính năng đó ra sao?
Bạn phân biệt các OpenOption như CREATE_NEW, CREATE, APPEND và TRUNCATE_EXISTING để tránh ghi đè dữ liệu ngoài ý muốn như thế nào?
Bạn tổ chức tạo thư mục, tệp tạm và dọn dẹp tệp trong quy trình xử lý upload bằng Files API như thế nào?
Vì sao kiểm tra Files.exists trước khi mở tệp vẫn có thể dẫn đến lỗi tranh chấp, và bạn xử lý thao tác đọc hoặc tạo tệp an toàn ra sao?
Bạn kiểm soát việc đi theo symbolic link khi đọc, sao chép hoặc xóa dữ liệu bằng NIO.2 như thế nào?
Bạn xây dựng thuật toán duyệt cây thư mục bằng Files.walkFileTree để xử lý tệp lỗi, thư mục không truy cập được và quyết định bỏ qua nhánh ra sao?
Bạn giải thích vai trò của preVisitDirectory, visitFile, visitFileFailed và postVisitDirectory trong FileVisitor như thế nào?
Bạn phát hiện và ngăn việc duyệt lặp do symbolic link khi quét một cây thư mục lớn như thế nào?
Bạn so sánh DirectoryStream, Files.list và Files.walk trong việc duyệt thư mục về tính lười, tiêu thụ tài nguyên và cách đóng kết quả ra sao?
Bạn thiết kế xử lý lỗi cục bộ khi duyệt hàng triệu tệp mà vẫn có thể tiếp tục phần hợp lệ như thế nào?
Bạn dùng WatchService để theo dõi thay đổi thư mục như thế nào, và xử lý OVERFLOW hoặc sự kiện bị gộp để dữ liệu cuối vẫn nhất quán ra sao?
Bạn đánh giá những khác biệt giữa WatchService trên Windows, Linux và các filesystem mạng như thế nào trước khi dùng trong production?
Bạn phân biệt BasicFileAttributes, PosixFileAttributes và DosFileAttributes để viết chức năng đọc metadata tệp có thể chạy trên nhiều hệ điều hành ra sao?
Bạn thiết lập và kiểm thử quyền truy cập tệp nhạy cảm bằng PosixFilePermissions hoặc FileAttributeView trong giới hạn filesystem hỗ trợ như thế nào?
Bạn áp dụng SecureDirectoryStream khi provider hỗ trợ để giảm rủi ro đường dẫn bị thay đổi qua symbolic link ra sao?
Bạn truy xuất dung lượng và giới hạn filesystem qua FileStore để quyết định trước một thao tác ghi tệp lớn như thế nào?
Bạn sử dụng Zip FileSystem để đọc hoặc ghi nội dung một tệp ZIP dưới dạng đường dẫn Path, và xử lý vòng đời filesystem đó như thế nào?
Bạn phân biệt FileChannel, SeekableByteChannel và AsynchronousFileChannel theo nhu cầu truy cập ngẫu nhiên, throughput và đồng thời ra sao?
Bạn thiết kế thao tác đọc ghi tệp lớn bằng FileChannel và ByteBuffer để tránh lỗi do kết quả đọc ghi từng phần như thế nào?
Bạn đánh giá giới hạn của FileLock khi nhiều tiến trình hoặc filesystem khác nhau cùng thao tác lên một tệp như thế nào?
Bạn phân biệt trách nhiệm của Paths.get với Path.of trong mã cũ và mã mới, đồng thời lập kế hoạch cải tiến mà vẫn giữ hành vi ra sao?
Fork/Join framework tổ chức một tác vụ chia để trị bằng RecursiveTask hoặc RecursiveAction như thế nào?
Bạn chọn ngưỡng chia nhỏ tác vụ trong Fork/Join để cân bằng chi phí điều phối và khả năng tận dụng CPU ra sao?
Work-stealing trong ForkJoinPool giúp phân phối khối lượng xử lý không đồng đều giữa các worker như thế nào?
Bạn thiết kế tác vụ tính tổng một mảng lớn bằng Fork/Join sao cho không chia công việc quá nhỏ hoặc tạo quá nhiều đối tượng ra sao?
Bạn phân biệt fork, join và invoke trong việc lên lịch và chờ kết quả tác vụ như thế nào?
Bạn đánh giá các rủi ro khi thực hiện I/O blocking trong ForkJoinPool và lựa chọn cơ chế phù hợp cho tác vụ chờ mạng ra sao?
Bạn so sánh ForkJoinPool riêng với common pool về cách ly tài nguyên và ảnh hưởng khi nhiều thành phần cùng chạy song song như thế nào?
Bạn thiết kế xử lý ngoại lệ, cancellation và timeout của một phép tính Fork/Join để tránh bỏ lại tác vụ không còn cần thiết ra sao?
Bạn đánh giá nguy cơ deadlock hoặc starvation khi các tác vụ Fork/Join chờ nhau hoặc chờ khóa dùng chung như thế nào?
Bạn đo hiệu quả thực tế của Fork/Join so với vòng lặp tuần tự bằng benchmark có warm-up và bộ dữ liệu đại diện như thế nào?
Bạn phân biệt trường hợp nên dùng Fork/Join, parallel stream và virtual thread trên JDK hiện đại dựa trên đặc tính CPU hoặc I/O như thế nào?
Phaser hỗ trợ đồng bộ các giai đoạn xử lý có số lượng tác vụ thay đổi như thế nào, và khác gì với CountDownLatch hoặc CyclicBarrier?
Bạn tổ chức register, arrive, awaitAdvance và arriveAndDeregister trong Phaser để không khiến một giai đoạn chờ vô hạn như thế nào?
Bạn thiết kế chính sách dừng và xử lý lỗi cho một nhóm worker đang dùng Phaser khi một worker thất bại giữa chừng ra sao?
Bạn phân biệt ThreadLocalRandom với Random thông thường và SecureRandom khi chọn nguồn số ngẫu nhiên cho mô phỏng và nghiệp vụ bảo mật như thế nào?
Bạn kiểm tra khả năng tái lập kết quả kiểm thử của thuật toán dùng ThreadLocalRandom và xác định trường hợp cần bộ sinh có seed tường minh ra sao?
TransferQueue hỗ trợ chuyển giao công việc trực tiếp giữa producer và consumer như thế nào, và cách dùng transfer khác gì với put?
Bạn chọn LinkedTransferQueue so với BlockingQueue có dung lượng giới hạn như thế nào khi cần điều tiết áp lực của hệ thống?
Bạn đánh giá ConcurrentLinkedDeque khi nhiều luồng thêm hoặc lấy phần tử ở hai đầu, bao gồm giới hạn của phép đo size, như thế nào?
Bạn tận dụng Objects.requireNonNull để làm rõ hợp đồng tham số và vị trí phát sinh lỗi trong một API như thế nào?
Bạn sử dụng StandardCharsets.UTF_8 để loại bỏ phụ thuộc vào charset mặc định khi đọc ghi dữ liệu giữa các hệ thống như thế nào?
Bạn xây dựng bộ kiểm thử hồi quy cho các phần Java 7 còn được dùng trên JDK hiện đại, bao gồm thao tác tệp, lỗi đóng tài nguyên và xử lý đồng thời, ra sao?
