Bạn phân biệt byte stream và character stream trong Java và chọn loại nào khi xử lý dữ liệu nhị phân hoặc văn bản như thế nào?
Bạn giải thích trách nhiệm của `InputStream`, `OutputStream`, `Reader` và `Writer` trong thiết kế API nhập xuất dữ liệu ra sao?
Bạn lựa chọn thao tác đọc từng byte, đọc vào mảng hoặc dùng bộ đệm dựa trên kích thước dữ liệu và chi phí lời gọi I/O như thế nào?
Bạn diễn giải giá trị trả về của `InputStream.read()` và phân biệt byte hợp lệ với dấu hiệu kết thúc luồng ra sao?
Bạn xử lý kết quả đọc ít byte hơn số lượng yêu cầu từ `InputStream.read(byte[], off, len)` như thế nào?
Bạn viết vòng lặp sao chép stream mà vẫn xử lý đúng EOF và không giả định một lần đọc sẽ lấy hết dữ liệu ra sao?
Bạn phân biệt ý nghĩa của `available()` với kích thước tổng dữ liệu còn lại trong một `InputStream` như thế nào?
Bạn đánh giá giới hạn của `skip()` khi muốn bỏ qua chính xác một lượng dữ liệu từ luồng như thế nào?
Bạn sử dụng `mark`, `reset` và `markSupported` để đọc thử dữ liệu rồi quay lại vị trí cũ ra sao?
Bạn thiết kế quy tắc sở hữu stream để quyết định phương thức nào phải đóng stream và phương thức nào chỉ mượn để sử dụng như thế nào?
Bạn lựa chọn `BufferedInputStream` hoặc `BufferedOutputStream` để giảm số lần truy cập nguồn I/O trong tình huống nào?
Bạn giải thích quan hệ giữa kích thước buffer, số lời gọi hệ thống và độ trễ khi đọc file lớn như thế nào?
Bạn phân biệt `flush` với `close` của output stream và xác định lúc nào dữ liệu thực sự được đẩy tới tầng bên dưới ra sao?
Bạn đánh giá vì sao gọi `flush` chưa đồng nghĩa với bảo đảm dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ như thế nào?
Bạn sử dụng `DataInputStream` và `DataOutputStream` để trao đổi giá trị nguyên thủy theo một định dạng nhị phân nhất quán ra sao?
Bạn xác định cách xử lý thứ tự byte và định dạng số khi đọc một file nhị phân do chương trình ngoài Java tạo ra như thế nào?
Bạn phân biệt `PrintStream` và `PrintWriter` về cách xử lý lỗi ghi, encoding và phương thức `checkError` như thế nào?
Bạn kiểm soát việc một `PrintWriter` không trực tiếp ném `IOException` trong quá trình ghi bằng cách nào?
Bạn thiết kế định dạng file nhị phân có header, phiên bản và độ dài payload để phát hiện dữ liệu hỏng hoặc bị cắt cụt ra sao?
Bạn phân biệt `EOFException` với lỗi I/O khác khi đọc dữ liệu theo khuôn dạng có độ dài cố định như thế nào?
Bạn xử lý một stream có thể bị chặn lâu khi nguồn dữ liệu chưa cung cấp đủ bytes bằng cơ chế nào?
Bạn chọn `try-with-resources` để quản lý stream và bảo toàn nguyên nhân khi cả thao tác đọc lẫn đóng tài nguyên đều thất bại như thế nào?
Bạn giải thích thứ tự đóng nhiều tài nguyên trong `try-with-resources` và cách truy xuất suppressed exceptions ra sao?
Bạn thiết kế đóng stream an toàn khi một lớp wrapper và stream nguồn có vòng đời do các thành phần khác nhau sở hữu như thế nào?
Bạn kiểm tra tác động của việc đóng một `BufferedReader` tới `InputStreamReader` và luồng byte bên dưới như thế nào?
Bạn dùng `InputStreamReader` hoặc `OutputStreamWriter` để nối giữa byte stream và character stream theo charset cụ thể ra sao?
Bạn giải thích vì sao chuyển một mảng byte thành chuỗi mà không chỉ rõ charset có thể gây sai dữ liệu như thế nào?
Bạn xác định sự khác nhau giữa UTF-8, UTF-16 và các charset một byte khi giải mã văn bản tiếng Việt bằng cách nào?
Bạn xử lý một ký tự Unicode được mã hóa thành nhiều byte nhưng bị chia qua hai lần đọc stream như thế nào?
Bạn chọn cách xử lý byte không hợp lệ hoặc ký tự không thể biểu diễn bằng `CharsetDecoder` và `CodingErrorAction` ra sao?
Bạn thiết kế quy trình chuyển đổi file văn bản giữa hai charset mà vẫn phát hiện lỗi thay thế ký tự âm thầm như thế nào?
Bạn kiểm tra và xử lý byte order mark của file văn bản khi công cụ bên ngoài có thể thêm BOM như thế nào?
Bạn phân biệt `Reader.read()` trả về đơn vị UTF-16 với Unicode code point khi xử lý ký tự ngoài BMP như thế nào?
Bạn tránh giả định một lần gọi `Reader.read(char[])` sẽ trả lại một dòng hoặc một ký tự hoàn chỉnh ra sao?
Bạn chọn `BufferedReader.readLine` để duyệt từng dòng và đánh giá hành vi với các kiểu xuống dòng khác nhau như thế nào?
Bạn giải thích vì sao `readLine` bỏ ký tự kết thúc dòng và cách giữ nguyên định dạng file khi cần xử lý như thế nào?
Bạn so sánh `Files.readString`, `Files.readAllLines` và đọc tuần tự bằng `BufferedReader` đối với file rất lớn ra sao?
Bạn lựa chọn `Files.lines` để xử lý file dạng dòng bằng stream và bảo đảm stream được đóng đúng thời điểm như thế nào?
Bạn thiết kế ghi log hoặc dữ liệu văn bản có charset và ký tự xuống dòng ổn định trên Windows, Linux và macOS như thế nào?
Bạn xác định cách kiểm tra một file văn bản chứa dòng cực dài có thể làm tăng đột biến bộ nhớ khi dùng `readLine` ra sao?
Bạn thiết kế xuất dữ liệu dạng CSV hoặc TSV sao cho escaping, charset và newline không làm mất cấu trúc dữ liệu như thế nào?
Bạn cân nhắc khi nào nên dùng `ObjectInputStream` và `ObjectOutputStream` thay cho một định dạng serialization có schema rõ ràng như thế nào?
Bạn kiểm soát rủi ro bảo mật khi đọc dữ liệu Java serialization từ nguồn không tin cậy bằng các cơ chế nào?
Bạn đánh giá vai trò của `serialVersionUID` và tính tương thích dữ liệu khi thay đổi class được serialize như thế nào?
Bạn xử lý trường `transient` và chu trình tham chiếu đối tượng khi lưu hoặc khôi phục object graph như thế nào?
Bạn phân biệt `java.io.File` và `java.nio.file.Path` theo khả năng biểu diễn đường dẫn và thao tác filesystem ra sao?
Bạn lựa chọn `Path.of`, `resolve` và `resolveSibling` để ghép đường dẫn mà không phụ thuộc dấu phân cách hệ điều hành như thế nào?
Bạn giải thích sự khác nhau giữa đường dẫn tương đối, đường dẫn tuyệt đối và thư mục làm việc hiện tại khi truy cập file ra sao?
Bạn phân biệt `Path.normalize()` với `toRealPath()` trong xử lý thành phần `..` và symbolic link như thế nào?
Bạn xác định khi nào `Path.relativize` hợp lệ và cách xử lý hai đường dẫn không tương thích với nhau ra sao?
Bạn kiểm tra vì sao hai đối tượng `Path` cùng trỏ tới một file nhưng không bằng nhau theo `equals` như thế nào?
Bạn dùng `Files.isSameFile` để so sánh mục tiêu thực tế của các đường dẫn có alias hoặc symbolic link ra sao?
Bạn bảo vệ thao tác ghi file trong thư mục giới hạn trước đầu vào chứa `..` hoặc symbolic link như thế nào?
Bạn giải thích giới hạn của kiểm tra đường dẫn trước khi mở file khi có tiến trình khác thay đổi filesystem cùng lúc như thế nào?
Bạn xác định khác biệt giữa `Files.exists`, `Files.notExists` và việc kiểm tra quyền truy cập thực tế như thế nào?
Bạn xử lý sự khác nhau giữa `NoSuchFileException`, `AccessDeniedException` và `FileAlreadyExistsException` khi thao tác `Files` ra sao?
Bạn dùng `Files.createFile` và `Files.createDirectories` để tạo dữ liệu mới và xử lý trường hợp mục tiêu đã tồn tại như thế nào?
Bạn thiết kế quyền truy cập ban đầu cho file tạm chứa dữ liệu nhạy cảm bằng API filesystem phù hợp như thế nào?
Bạn sử dụng `Files.createTempFile` hoặc `createTempDirectory` và lên kế hoạch dọn dẹp khi thao tác tiếp theo thất bại ra sao?
Bạn phân biệt các chế độ `CREATE`, `CREATE_NEW`, `TRUNCATE_EXISTING` và `APPEND` khi mở file để ghi như thế nào?
Bạn đánh giá nguy cơ ghi đè ngoài ý muốn khi dùng `Files.write` hoặc `newOutputStream` với các tùy chọn mặc định ra sao?
Bạn thiết kế cách cập nhật file cấu hình bằng file tạm và `Files.move` để hạn chế tình trạng file đích bị ghi dở dang như thế nào?
Bạn phân biệt `StandardCopyOption.REPLACE_EXISTING` và `ATOMIC_MOVE`, đồng thời xử lý môi trường không hỗ trợ move nguyên tử ra sao?
Bạn kiểm tra trường hợp chuyển file giữa hai filesystem khiến rename không thể bảo đảm tính nguyên tử như thế nào?
Bạn bảo đảm dữ liệu đã ghi được đồng bộ xuống thiết bị khi yêu cầu độ bền cao bằng các tùy chọn hoặc phương thức phù hợp ra sao?
Bạn phân biệt sao chép nội dung với sao chép metadata và thuộc tính file khi dùng `Files.copy` như thế nào?
Bạn lựa chọn chính sách xử lý symbolic link khi sao chép, xóa hoặc duyệt cây thư mục như thế nào?
Bạn xác định thứ tự thao tác cần thiết để xóa một thư mục có nhiều cấp con mà vẫn tránh theo nhầm symbolic link ra sao?
Bạn sử dụng `Files.walkFileTree` và `FileVisitor` để xử lý cây thư mục lớn mà không giữ mọi đường dẫn trong bộ nhớ như thế nào?
Bạn phân biệt kết quả từ `Files.list`, `Files.walk` và `Files.find` về phạm vi duyệt và quản lý resource stream ra sao?
Bạn xử lý lỗi I/O xuất hiện giữa lúc duyệt cây thư mục để tiếp tục phần còn lại hoặc dừng có kiểm soát như thế nào?
Bạn nhận diện vòng lặp symbolic link khi duyệt cây với `FOLLOW_LINKS` và quyết định cách phục hồi ra sao?
Bạn kiểm tra độ sâu duyệt và bộ lọc để tránh vô tình đọc toàn bộ cây thư mục lớn bằng cách nào?
Bạn dùng `BasicFileAttributes` để phân biệt file thường, thư mục, symbolic link và thuộc tính thời gian ra sao?
Bạn xử lý khác biệt của `PosixFileAttributes` và `DosFileAttributes` khi chạy trên nhiều hệ điều hành như thế nào?
Bạn đánh giá độ tin cậy của `FileTime` và timestamp filesystem khi dùng để phát hiện file đã thay đổi ra sao?
Bạn đọc, ghi và kiểm chứng quyền truy cập file trên filesystem hỗ trợ POSIX bằng những API nào?
Bạn sử dụng `FileStore` để kiểm tra khả năng hỗ trợ một dạng thuộc tính hoặc dung lượng lưu trữ trước khi thao tác ra sao?
Bạn phân biệt filesystem mặc định với filesystem do provider cung cấp, chẳng hạn ZIP filesystem, khi làm việc với `Path` như thế nào?
Bạn tổ chức đóng `FileSystem` được mở qua provider để tránh giữ file archive đang được sử dụng ra sao?
Bạn dùng `WatchService` để quan sát tạo, sửa và xóa file rồi xử lý vòng đời của `WatchKey` như thế nào?
Bạn phân tích vì sao sự kiện từ `WatchService` không đủ để bảo đảm nhận chính xác mọi thay đổi filesystem ra sao?
Bạn xử lý sự kiện `OVERFLOW`, sự kiện trùng lặp hoặc nhiều thay đổi xảy ra nhanh khi đồng bộ thư mục như thế nào?
Bạn xác định giới hạn của `WatchService` khi cần theo dõi cây thư mục có nhiều thư mục con ra sao?
Bạn giải thích vai trò của `Buffer`, `ByteBuffer` và `Channel` trong NIO so với mô hình stream truyền thống như thế nào?
Bạn phân biệt `capacity`, `position`, `limit` và `remaining` của `ByteBuffer` qua chu trình ghi rồi đọc như thế nào?
Bạn mô tả cách dùng `flip`, `clear`, `rewind` và `compact` khi một channel chỉ đọc hoặc ghi được một phần buffer ra sao?
Bạn thiết kế vòng lặp đọc từ `FileChannel` vào `ByteBuffer` mà không làm mất dữ liệu còn sót lại trong buffer như thế nào?
Bạn giải thích sự khác biệt giữa `ByteBuffer.slice`, `duplicate` và bản sao dữ liệu độc lập về bộ nhớ và trạng thái đọc ghi như thế nào?
Bạn kiểm tra cách `ByteBuffer.asReadOnlyBuffer` bảo vệ thao tác ghi nhưng vẫn chia sẻ bộ nhớ nền như thế nào?
Bạn so sánh `ByteBuffer.allocate` và `allocateDirect` về chi phí cấp phát, GC và hiệu năng trao đổi với native I/O ra sao?
Bạn xác định khi nào lợi ích của direct buffer bù được chi phí cấp phát và thu hồi cao hơn so với heap buffer như thế nào?
Bạn sử dụng `ByteBuffer.order` để đọc cấu trúc nhị phân có endian xác định và kiểm tra alignment thích hợp ra sao?
Bạn xử lý `BufferUnderflowException` hoặc `BufferOverflowException` bằng cách thiết kế đúng giao thức dữ liệu và trạng thái buffer như thế nào?
Bạn phân biệt `ReadableByteChannel`, `WritableByteChannel` và `SeekableByteChannel` theo khả năng di chuyển vị trí đọc ghi như thế nào?
Bạn dùng `FileChannel.position` và `size` để truy cập ngẫu nhiên mà không phải đọc tuần tự toàn bộ file ra sao?
Bạn phân biệt thao tác đọc có vị trí tường minh với thao tác dùng vị trí hiện tại của `FileChannel` khi nhiều luồng truy cập như thế nào?
Bạn thiết kế ghi một record vào vị trí xác định của file và kiểm soát trường hợp ghi chưa đủ bytes như thế nào?
Bạn sử dụng `FileChannel.truncate` hoặc `RandomAccessFile.setLength` để thay đổi kích thước file và đánh giá tác động đến dữ liệu ra sao?
Bạn lựa chọn `RandomAccessFile` hoặc `FileChannel` khi cần cập nhật các khối dữ liệu ở vị trí ngẫu nhiên theo tiêu chí nào?
Bạn đánh giá lợi ích và giới hạn của `FileChannel.transferTo` hoặc `transferFrom` khi sao chép file rất lớn như thế nào?
Bạn kiểm tra vì sao một lời gọi `transferTo` có thể chuyển ít dữ liệu hơn số lượng yêu cầu và thiết kế vòng lặp hoàn tất ra sao?
Bạn sử dụng scatter/gather I/O để đọc hoặc ghi nhiều buffer theo định dạng header và payload như thế nào?
Bạn phân biệt đồng bộ dữ liệu và metadata bằng `FileChannel.force` khi yêu cầu tính bền vững của bản ghi như thế nào?
Bạn giải thích sự khác nhau giữa khóa file dùng để phối hợp nhiều tiến trình và đồng bộ dữ liệu giữa các thread trong cùng JVM ra sao?
Bạn chọn `FileChannel.lock` hay `tryLock` và quản lý `FileLock` trong `try-with-resources` như thế nào?
Bạn xử lý `OverlappingFileLockException` và trường hợp filesystem chỉ hỗ trợ file lock theo cơ chế advisory ra sao?
Bạn đánh giá giới hạn của file locking khi triển khai ứng dụng trên filesystem mạng hoặc nhiều hệ điều hành như thế nào?
Bạn sử dụng `FileChannel.map` để ánh xạ file lớn vào bộ nhớ và lựa chọn `MapMode` phù hợp như thế nào?
Bạn phân biệt memory-mapped I/O với `FileChannel.read` theo số lần copy, chi phí page fault và mẫu truy cập như thế nào?
Bạn xác định rủi ro khi một tiến trình khác thay đổi kích thước file đang được ánh xạ và cách phòng ngừa ra sao?
Bạn dùng `MappedByteBuffer.force` trong tình huống nào và đánh giá giới hạn bảo đảm dữ liệu bền vững như thế nào?
Bạn quản lý vòng đời memory-mapped buffer khi cần thay thế hoặc xóa file trên các hệ điều hành khác nhau ra sao?
Bạn phân tích hiện tượng đọc một file lớn gây tăng page cache và bộ nhớ tiến trình dù Java heap không tăng tương ứng như thế nào?
Bạn giải thích khác biệt giữa blocking channel và non-blocking channel về thời điểm lời gọi đọc ghi trả về như thế nào?
Bạn tổ chức `Selector` và `SelectionKey` cho nhiều channel không chặn mà tránh busy polling ra sao?
Bạn xử lý trạng thái đọc được hoặc ghi được của channel không chặn mà vẫn kiểm tra số byte xử lý thực tế như thế nào?
Bạn lựa chọn `AsynchronousFileChannel` thay vì `FileChannel` khi cần thực hiện nhiều yêu cầu I/O độc lập theo tiêu chí nào?
Bạn sử dụng `Future` hoặc `CompletionHandler` để nhận kết quả và lỗi từ `AsynchronousFileChannel` như thế nào?
Bạn thiết kế xử lý partial read hoặc partial write trong callback của `AsynchronousFileChannel` ra sao?
Bạn quyết định vòng đời `ByteBuffer` khi I/O bất đồng bộ chưa hoàn thành để tránh sửa hoặc tái sử dụng dữ liệu quá sớm như thế nào?
Bạn xử lý tình huống đóng `AsynchronousFileChannel` khi vẫn còn yêu cầu I/O chưa hoàn tất ra sao?
Bạn thiết kế chính sách hủy, timeout và đóng tài nguyên khi một chuỗi thao tác I/O bất đồng bộ mất nhiều thời gian hơn mong đợi như thế nào?
Bạn so sánh giới hạn của async file I/O trên các nền tảng và tác động của thread pool hỗ trợ tới hiệu năng thực tế như thế nào?
Bạn chọn chiến lược batch, buffering và backpressure để ghi lượng lớn sự kiện xuống file mà không làm cạn bộ nhớ ra sao?
Bạn thiết kế pipeline đọc file rất lớn theo từng chunk để giới hạn sử dụng heap và vẫn kiểm chứng dữ liệu đầu vào như thế nào?
Bạn đánh giá tác động của kích thước block, hệ thống lưu trữ và truy cập tuần tự hoặc ngẫu nhiên tới throughput của chương trình như thế nào?
Bạn thiết kế benchmark cho `BufferedInputStream`, `FileChannel` và memory-mapped file sao cho kiểm soát được JIT, cache và ảnh hưởng hệ điều hành ra sao?
Bạn phân biệt độ trễ thao tác, thông lượng và mức sử dụng bộ nhớ khi lựa chọn giải pháp I/O cho hệ thống như thế nào?
Bạn chẩn đoán ứng dụng bị tăng số lượng file descriptor hoặc handle theo thời gian và xác định nơi chưa đóng tài nguyên ra sao?
Bạn thiết kế kiểm thử cho lỗi hết dung lượng đĩa, mất quyền ghi hoặc file bị xóa trong khi đang thao tác như thế nào?
Bạn tổ chức ghi file có checksum và xác minh checksum khi đọc để phát hiện dữ liệu bị cắt cụt hoặc hư hỏng ra sao?
Bạn bảo đảm thao tác ghi file là idempotent khi một tác vụ có thể bị chạy lại sau lỗi hoặc sau khi ứng dụng khởi động lại như thế nào?
Bạn thiết kế test với file tạm và thư mục tạm để kiểm chứng đường dẫn, charset, đóng tài nguyên và dọn dẹp khi gặp exception như thế nào?
Bạn xây dựng ma trận kiểm thử I/O trên Windows, Linux và macOS để phát hiện khác biệt đường dẫn, khóa file, quyền và encoding như thế nào?
