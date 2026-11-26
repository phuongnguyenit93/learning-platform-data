Câu 1: Một đối tượng được quản lý tự động bởi try-with-resources cần đáp ứng hợp đồng nào?
A. Triển khai Serializable để JVM đóng resource sau khi ghi.
B. Triển khai Runnable để close được chạy bằng worker riêng.
C. Triển khai Cloneable để tự sao lưu resource khi thoát khối.
D. Triển khai AutoCloseable để close được gọi khi thoát khối.
Đáp án đúng: D

Câu 2: Khi khai báo hai tài nguyên trong một try-with-resources, thứ tự đóng là gì?
A. Đóng tài nguyên khai báo đầu trước, tài nguyên sau sau.
B. Đóng tài nguyên có thời gian mở lâu hơn ở bước cuối.
C. Đóng tài nguyên được tham chiếu trong catch ở bước cuối.
D. Đóng tài nguyên khai báo sau trước, tài nguyên đầu sau.
Đáp án đúng: D

Câu 3: Thân try và close cùng ném exception trong try-with-resources; exception nào là chính?
A. Lỗi của close chính; lỗi trong try trở thành suppressed.
B. Lỗi của thân try chính; lỗi close được lưu suppressed.
C. Lỗi xảy ra đầu tiên luôn được đổi thành IOException.
D. Cả hai lỗi được hợp nhất thành một RuntimeException mới.
Đáp án đúng: B

Câu 4: Nếu thân try hoàn tất bình thường nhưng resource.close ném exception, điều gì xảy ra?
A. Lỗi từ close bị bỏ qua vì thân try đã chạy thành công.
B. Lỗi từ close thành suppressed của một exception rỗng.
C. Lỗi từ close có thể lan ra và cần được xử lý theo hợp đồng.
D. JVM sẽ tự thử gọi close lại cho đến lúc thành công.
Đáp án đúng: C

Câu 5: Muốn kiểm tra lỗi khi đóng tài nguyên sau lỗi chính, API nào thích hợp?
A. Đọc getSuppressed() trên exception chính vừa bắt.
B. Đọc getCause() vì mọi lỗi close thành cause trực tiếp.
C. Đọc getStackTrace() vì mọi lỗi close có stack riêng.
D. Đọc getLocalizedMessage() để lấy tất cả lỗi close.
Đáp án đúng: A

Câu 6: Trong try-with-resources có khối finally, trình tự thông thường nào đúng?
A. Resource đóng trước, sau đó mới chạy khối finally.
B. Khối finally chạy xong thì resource mới được đóng.
C. Khối finally chỉ chạy khi AutoCloseable.close thất bại.
D. Resource không được đóng khi finally có lệnh return.
Đáp án đúng: A

Câu 7: Một AutoCloseable.close khai báo checked exception; tác động khi dùng try-with-resources?
A. Javac bỏ qua mọi checked exception do compiler tự gọi.
B. Phải xử lý hoặc khai báo checked exception từ close.
C. Lỗi checked của close luôn chuyển thành IllegalStateException.
D. AutoCloseable.close chỉ được phép ném unchecked exception.
Đáp án đúng: B

Câu 8: Trong multi-catch, cú pháp nào gom các exception không có quan hệ cha-con?
A. Dùng dấu | để nối các kiểu exception cần bắt chung.
B. Dùng dấu phẩy , để liệt kê nhiều exception trong catch.
C. Viết nhiều catch cùng một thân nhưng dùng chung một nhãn.
D. Dùng dấu & để tạo kiểu giao của các exception cần bắt.
Đáp án đúng: A

Câu 9: Vì sao multi-catch không cho phép gán giá trị mới cho biến exception?
A. Biến exception tự động trở thành field static của Logger.
B. Mọi biến trong mọi khối catch đều bị cấm gán giá trị.
C. Biến multi-catch được coi là implicitly final trong catch.
D. Throwable không có constructor nên không được gán mới.
Đáp án đúng: C

Câu 10: Khi bắt IOException và FileNotFoundException trong cùng multi-catch, javac xử lý ra sao?
A. Javac chấp nhận và ưu tiên kiểu con ở nhánh đầu.
B. Javac chấp nhận nếu kiểu con được ghi trước kiểu cha.
C. Javac tự loại IOException mà không đưa cảnh báo nào.
D. Javac từ chối vì hai kiểu có quan hệ kế thừa.
Đáp án đúng: D

Câu 11: Diamond operator trong lệnh tạo collection giúp ích điều gì?
A. Tự xác định kiểu phần tử bằng reflection ở runtime.
B. Bỏ kiểm tra generic và cho phép tạo raw collection.
C. Cho phép truyền collection sang mọi kiểu không cần cast.
D. Suy luận tham số generic từ ngữ cảnh khởi tạo.
Đáp án đúng: D

Câu 12: Khi dùng diamond operator với biến có kiểu List<String>, nhận định nào đúng?
A. Diamond tạo raw List để thêm Integer tùy ý vào list.
B. Generic vẫn được compiler kiểm tra khi biên dịch.
C. Kiểu phần tử chỉ xác định sau lần add đầu tiên vào list.
D. Compiler tạo một class riêng cho mỗi kiểu String.
Đáp án đúng: B

Câu 13: Lệnh switch dùng String được giới thiệu từ Java 7 so sánh nhánh bằng gì?
A. So tham chiếu String với case theo toán tử ==.
B. Sắp các case theo hashCode không theo nội dung.
C. So nội dung String với các nhãn case tương ứng.
D. Xem case là biểu thức regex thay cho literal.
Đáp án đúng: C

Câu 14: Switch trên biến String nhận giá trị null sẽ có hành vi nào?
A. Tự đi vào default bất kể đã có các case khác.
B. Xem null như chuỗi rỗng để khớp nhãn case đầu.
C. Ném NullPointerException khi đọc selector của switch.
D. Bỏ qua switch và chạy tiếp sau dấu đóng khối.
Đáp án đúng: C

Câu 15: Cách dùng dấu gạch dưới trong numeric literal nào hợp lệ?
A. Đặt giữa chữ số, không đặt sát dấu chấm thập phân.
B. Đặt ngay sau tiền tố 0x trước ký tự hex đầu tiên.
C. Đặt ngay cuối literal số nguyên trước dấu chấm phẩy.
D. Đặt trực tiếp trước hậu tố L trong literal long.
Đáp án đúng: A

Câu 16: Khi cần dùng UTF-8 mà không phụ thuộc tên charset do người dùng nhập, nên chọn gì?
A. Đưa tên charset rỗng để JVM tự suy luận UTF-8.
B. Dùng StandardCharsets.UTF_8 được cung cấp trong JDK.
C. Dùng Charset.defaultCharset vì luôn là UTF-8 mọi máy.
D. Dùng số thứ tự mã UTF-8 trong bảng charset của JVM.
Đáp án đúng: B

Câu 17: Đối tượng Path của NIO.2 biểu diễn điều gì khi vừa được tạo?
A. Một file đã được mở và giữ file descriptor đến khi close.
B. Nội dung tệp đã được JVM tải hoàn chỉnh vào bộ nhớ.
C. Một tên file đã được chuẩn hóa qua filesystem thực tế.
D. Đường dẫn tới tài nguyên, chưa khẳng định file tồn tại.
Đáp án đúng: D

Câu 18: Trong Java 7, API nào tạo Path từ một chuỗi đường dẫn thông dụng?
A. Dùng Path.of, một factory đã có sẵn ngay từ Java 7.
B. Dùng Files.createFile để lấy Path dù chưa muốn tạo file.
C. Dùng Paths.get với chuỗi đường dẫn và thành phần cần thiết.
D. Dùng FileChannel.open để lấy Path trực tiếp từ channel.
Đáp án đúng: C

Câu 19: Path.resolve nhận đối số là đường dẫn tuyệt đối; kết quả thông thường?
A. Luôn ghép nguyên hai đường dẫn thành một path mới.
B. Trả đường dẫn đối số thay vì nối sau đường dẫn gốc.
C. Ném IOException trước khi kiểm tra file có tồn tại.
D. Bỏ phần root của đối số rồi nối vào path ban đầu.
Đáp án đúng: B

Câu 20: Path.normalize thực hiện dạng chuẩn hóa nào?
A. Rút gọn các thành phần . và .. theo cú pháp đường dẫn.
B. Truy cập file system để xác nhận mọi thành phần tồn tại.
C. Luôn giải quyết symlink về nơi tệp đích thực sự nằm.
D. Chuyển mọi path tương đối thành đường dẫn tuyệt đối.
Đáp án đúng: A

Câu 21: Để tìm đường dẫn thực sau khi xử lý symbolic link, cần cân nhắc API nào?
A. Path.normalize vì thao tác này luôn đọc symlink.
B. Path.getFileName vì chỉ tên cuối thể hiện đích thực.
C. Path.toRealPath với chính sách link phù hợp.
D. Path.resolveSibling vì luôn trả ra đường dẫn canonical.
Đáp án đúng: C

Câu 22: Files.exists kiểm tra symbolic link theo chế độ mặc định nào?
A. Chỉ kiểm tra sự tồn tại của file link, bỏ qua đích.
B. Luôn thử mở file nội dung trước khi có kết quả.
C. Theo liên kết tới đích nếu không chọn NOFOLLOW_LINKS.
D. Luôn từ chối mọi symbolic link bằng SecurityException.
Đáp án đúng: C

Câu 23: Files.copy gặp target đã tồn tại và không có tùy chọn thay thế; hành vi nào?
A. Âm thầm ghi đè nội dung của file target hiện tại.
B. Có thể ném FileAlreadyExistsException cho đường đích.
C. Luôn đổi tên đích để tránh xung đột dữ liệu cũ.
D. Luôn nối tiếp các byte nguồn vào cuối file target.
Đáp án đúng: B

Câu 24: Khi yêu cầu Files.move với ATOMIC_MOVE nhưng file system không hỗ trợ, điều gì có thể xảy ra?
A. Báo AtomicMoveNotSupportedException thay vì bảo đảm atomic.
B. Chuyển thành copy rồi xóa nhưng vẫn cam kết atomic hoàn toàn.
C. Thực hiện move trong một transaction JVM duy nhất.
D. Bỏ qua ATOMIC_MOVE và luôn ghi đè target khi thành công.
Đáp án đúng: A

Câu 25: Files.deleteIfExists khác Files.delete chủ yếu ở điểm nào khi file vắng mặt?
A. Cả hai đều trả về boolean nhưng giá trị mặc định khác nhau.
B. deleteIfExists chỉ dùng với folder, còn delete chỉ dùng file.
C. deleteIfExists luôn tạo file rỗng trước khi xóa để kiểm tra.
D. deleteIfExists trả false, còn delete có thể báo không tìm thấy.
Đáp án đúng: D

Câu 26: Ứng dụng đọc cả file log nhiều GB bằng Files.readAllBytes; rủi ro chính?
A. Cần cấp phát bộ nhớ cho toàn bộ nội dung file được đọc.
B. Dữ liệu sẽ được stream từng lô mà không giữ trong heap.
C. API chỉ trả metadata của file nên không tốn nhiều RAM.
D. JVM tự xoay file mỗi khi readAllBytes đạt ngưỡng lớn.
Đáp án đúng: A

Câu 27: Vì sao cần đóng DirectoryStream khi dùng Files.newDirectoryStream?
A. Để giải phóng tài nguyên liên quan việc duyệt thư mục.
B. Vì chỉ sau close mới bắt đầu xuất các tên file đã đọc.
C. Vì DirectoryStream bắt buộc ghi kết quả vào một file đệm.
D. Vì JVM cần xóa mọi file con đã duyệt trước khi thoát.
Đáp án đúng: A

Câu 28: Files.walkFileTree thường phù hợp nhất khi cần làm gì?
A. Chỉ đọc duy nhất một file rồi trả về String được mã hóa.
B. Duyệt cây thư mục với callback và xử lý lỗi ở từng nhánh.
C. Sắp tất cả file theo thời gian cập nhật từ mới đến cũ.
D. Sao chép cây tệp nguyên tử qua nhiều file system khác nhau.
Đáp án đúng: B

Câu 29: Nếu không bật FOLLOW_LINKS, Files.walkFileTree xử lý symbolic link thế nào?
A. Luôn đi theo mọi symlink mà không thể thay đổi cấu hình.
B. Bỏ qua hoàn toàn symlink và không báo với visitor.
C. Luôn tự phát hiện chu kỳ link rồi thay bằng file rỗng.
D. Mặc định không đi theo symlink tới cây thư mục đích.
Đáp án đúng: D

Câu 30: Files.createDirectories khác Files.createDirectory ở hành vi nào?
A. Chỉ có createDirectories tạo file nội dung trong thư mục.
B. createDirectory luôn tạo các thư mục cha trước khi tạo đích.
C. createDirectories tự xóa thư mục cũ để tạo lại từ đầu.
D. Có thể tạo cả thư mục cha còn thiếu trên đường dẫn.
Đáp án đúng: D

Câu 31: NIO.2 hỗ trợ lấy metadata cơ bản của tệp bằng cơ chế nào?
A. Chỉ xem tên file qua Path.getFileName rồi suy ra size.
B. Dùng Files.readAllBytes để đọc size và thời gian tạo file.
C. Đọc BasicFileAttributes qua Files.readAttributes.
D. Suy ra BasicFileAttributes từ thông tin FileStore.
Đáp án đúng: C

Câu 32: Khi gọi Path.relativize cho hai Path, điều kiện nào cần xem xét?
A. Chỉ path ở đích mới cần tồn tại trước khi tương đối hóa.
B. Các path phải tương thích về root và kiểu tuyệt đối/tương đối.
C. Path nguồn phải là symbolic link trỏ tới path đích.
D. Hai path phải có phần tên cuối giống nhau để nhận kết quả.
Đáp án đúng: B

Câu 33: Khi đọc tệp văn bản rất lớn bằng Files.readAllLines, điểm nào cần lưu ý?
A. Phương thức luôn trả một Stream lazy không giữ nội dung.
B. Danh sách kết quả lưu các dòng đã đọc vào heap.
C. Dữ liệu được đọc qua mmap và tự hủy ngay sau từng dòng.
D. Kết quả chỉ có số lượng dòng chứ không có nội dung file.
Đáp án đúng: B

Câu 34: Trong Java 7, Files.newBufferedReader nhận thông tin nào để giải mã tệp đúng?
A. Một FileStore mô tả dung lượng còn trống của ổ đĩa.
B. Một PathMatcher xác định mẫu tên các tệp cần đọc.
C. Một Charset xác định cách giải mã byte thành ký tự.
D. Một WatchService theo dõi thay đổi khi file được mở.
Đáp án đúng: C

Câu 35: Files.newBufferedWriter với tùy chọn TRUNCATE_EXISTING mang ý nghĩa nào?
A. Nối byte mới vào cuối file mà không làm mất byte cũ.
B. Chỉ thay thế metadata nhưng giữ nguyên toàn bộ nội dung.
C. Tạo file mới bằng tên phụ rồi tự đổi tên khi đóng.
D. Xóa nội dung file đang có khi mở theo chế độ ghi.
Đáp án đúng: D

Câu 36: Nếu muốn tạo file mới và thất bại khi target đã tồn tại, nên xét OpenOption nào?
A. CREATE cho phép ghi đè ngay cả khi file đã hiện hữu.
B. CREATE_NEW kiểm tra và tạo mới theo hợp đồng filesystem.
C. APPEND chỉ tạo file nếu chưa từng xuất hiện trong thư mục.
D. TRUNCATE_EXISTING từ chối mở nếu file đang tồn tại.
Đáp án đúng: B

Câu 37: Khi Files.copy nhận InputStream làm nguồn, ai chịu trách nhiệm đóng stream?
A. Files.copy luôn đóng mọi InputStream nhận vào ngay khi trở về.
B. Bên sở hữu stream phải quản lý close, có thể dùng try-with-resources.
C. JVM chỉ đóng stream khi Path đích được garbage collect.
D. FileStore tự đóng input khi metadata file được cập nhật.
Đáp án đúng: B

Câu 38: Muốn đọc metadata của symbolic link thay vì file đích qua Files.readAttributes, nên chọn gì?
A. Dùng StandardCopyOption.REPLACE_EXISTING trên path nguồn.
B. Dùng WatchEvent.Kind.ENTRY_MODIFY trong lời gọi đọc.
C. Chuyển mọi path thành absolute trước khi truy cập tệp.
D. Truyền LinkOption.NOFOLLOW_LINKS khi đọc attribute.
Đáp án đúng: D

Câu 39: Khi đặt quyền POSIX cho tệp qua Files.setPosixFilePermissions, điều gì quan trọng?
A. Filesystem provider phải hỗ trợ thuộc tính POSIX tương ứng.
B. Mọi hệ điều hành hỗ trợ cùng quy tắc owner/group mặc định.
C. API đổi owner theo tên tài khoản trong đường dẫn file.
D. Quyền được lưu trong nội dung file, không thuộc metadata.
Đáp án đúng: A

Câu 40: Ứng dụng muốn ước lượng dung lượng còn có thể sử dụng trên filesystem; nên đọc gì?
A. Path.getNameCount vì số thành phần tương ứng dung lượng.
B. Files.readAllBytes của đường dẫn root trên ổ đĩa.
C. FileStore.getUsableSpace của filesystem chứa dữ liệu.
D. FileTime.toMillis của lần thay đổi metadata cuối cùng.
Đáp án đúng: C

Câu 41: WatchService của NIO.2 được đăng ký theo đối tượng nào để theo dõi tệp?
A. Đăng ký một chuỗi nội dung được ghi vào file cần xem.
B. Đăng ký một FileChannel với vị trí byte bắt đầu theo dõi.
C. Đăng ký một thư mục với loại sự kiện quan tâm.
D. Đăng ký từng file riêng thay vì thư mục chứa file.
Đáp án đúng: C

Câu 42: Vì sao WatchService không mặc định thay thế trình quét toàn bộ cây thư mục?
A. WatchService không hỗ trợ bất cứ loại sự kiện xóa tệp nào.
B. WatchService bắt buộc đọc toàn bộ file sau mỗi lần sửa đổi.
C. Sự kiện tạo tệp luôn có đầy đủ các byte của tệp vừa tạo.
D. Đăng ký một thư mục không mặc nhiên theo dõi mọi thư mục con.
Đáp án đúng: D

Câu 43: WatchKey báo sự kiện OVERFLOW trong WatchService; việc này gợi ý điều gì?
A. ENTRY_DELETE sẽ tự biến thành ENTRY_CREATE cho file cũ.
B. Một số thay đổi có thể bị mất, cần đồng bộ lại trạng thái thư mục.
C. WatchService tự phát lại chính xác mọi sự kiện bị bỏ sót.
D. Tài nguyên cần mở lại bằng CREATE_NEW trước khi xử lý.
Đáp án đúng: B

Câu 44: Sau khi lấy danh sách event từ WatchKey, điều gì giúp tiếp tục nhận theo dõi?
A. Gọi cancel để đăng ký lại toàn bộ thư mục đã theo dõi.
B. Gọi close trên WatchKey nhưng giữ WatchService nguyên.
C. Gọi normalize trên Path của WatchKey để tái tạo event.
D. Gọi reset để WatchKey có thể nhận thông báo về sau.
Đáp án đúng: D

Câu 45: Khi nhận ENTRY_CREATE rồi đọc file ngay, ứng dụng cần chú ý rủi ro nào?
A. Producer có thể còn đang ghi dở tệp mới tạo.
B. ENTRY_CREATE bảo đảm file đã được đóng ở mọi tiến trình.
C. WatchService chuyển file thành read-only trước khi báo.
D. JVM tự chờ tới khi CRC của file hoàn tất rồi mới báo.
Đáp án đúng: A

Câu 46: FileVisitor trả SKIP_SUBTREE trong preVisitDirectory; hiệu ứng nào đúng?
A. Bỏ duyệt các mục con của thư mục hiện tại.
B. Kết thúc toàn bộ lượt walk kể cả các nhánh khác.
C. Đọc file trong thư mục nhưng bỏ mọi thư mục ngang cấp.
D. Khởi động lại walk từ thư mục gốc cho nhánh hiện tại.
Đáp án đúng: A

Câu 47: FileVisitor trả TERMINATE trong quá trình walkFileTree; ý nghĩa nào đúng?
A. Chỉ bỏ file hiện tại và tiếp tục các file kế tiếp.
B. Duyệt lại thư mục cha rồi mới dừng khi hết callback.
C. Dừng việc duyệt cây ngay, không đi tiếp các mục khác.
D. Chỉ ngừng theo symbolic link nhưng giữ walk bình thường.
Đáp án đúng: C

Câu 48: AsynchronousFileChannel.read cho phép theo dõi kết quả đọc theo cách nào?
A. Nhận Future hoặc cung cấp CompletionHandler theo API.
B. Nhận DirectoryStream và lấy event từ WatchService.
C. Nhận PathMatcher và gọi matches trên tên tệp sau đọc.
D. Nhận Formatter rồi chuyển byte thành LogRecord đầu ra.
Đáp án đúng: A

Câu 49: Khi cần viết tác vụ Fork/Join trả về giá trị, nên kế thừa lớp nào?
A. RecursiveAction vì compute có thể trả về kiểu generic.
B. RecursiveTask<V> vì compute trả về giá trị kiểu V.
C. ForkJoinWorkerThread vì lớp này cung cấp hàm compute.
D. ForkJoinPool vì pool trực tiếp định nghĩa hàm compute.
Đáp án đúng: B

Câu 50: Trong một RecursiveTask, gọi fork rồi join thường có ý nghĩa gì?
A. Lên lịch task con, sau đó chờ và nhận kết quả của nó.
B. Chạy task con trên thread mới bắt buộc, không có chờ đợi.
C. Hủy task con sau khi tính kết quả của task cha.
D. Chỉ đăng ký task con vào một barrier giữa các worker.
Đáp án đúng: A

Câu 51: Work stealing trong ForkJoinPool hỗ trợ điều gì?
A. Mọi task được giao cố định cho một worker đến lúc hoàn tất.
B. Mỗi task luôn có một platform thread riêng không được tái dùng.
C. Worker có thể lấy việc ở queue khác khi thiếu việc riêng.
D. Các phép tính tự khóa dữ liệu chung để tránh race condition.
Đáp án đúng: C

Câu 52: Ngưỡng chia nhỏ task quá thấp khi dùng Fork/Join dễ gây tác động nào?
A. Giảm chi phí điều phối vì không còn tác vụ nào được fork.
B. Tăng chi phí tạo và phối hợp rất nhiều task nhỏ.
C. Bảo đảm mọi nhánh chạy cùng lúc với số lượng CPU tùy ý.
D. Ngăn tất cả worker thực hiện work stealing khi rảnh.
Đáp án đúng: B

Câu 53: ForkJoinPool thực hiện nhiều tác vụ I/O chặn lâu; vấn đề nào cần đánh giá?
A. Worker có thể bị giữ khi chờ, làm giảm khả năng xử lý task.
B. Mọi I/O chặn luôn tự chuyển thành non-blocking dưới JVM.
C. Pool buộc tạo một worker mới cho mọi lời gọi đọc file.
D. ForkJoinTask tự dùng CompletableFuture cho toàn bộ I/O.
Đáp án đúng: A

Câu 54: Khi một ForkJoinTask bắt buộc dùng blocking operation, API nào có thể hỗ trợ pool điều phối?
A. ForkJoinPool.managedBlock phối hợp với ManagedBlocker.
B. ForkJoinPool.getStealCount tự tạo worker bù khi bị chặn.
C. ThreadLocalRandom.current tạo thêm worker khi bị chặn.
D. Phaser.forceTermination mở rộng queue chờ của pool.
Đáp án đúng: A

Câu 55: Hai RecursiveTask đồng thời cộng vào một biến số nguyên chung; rủi ro chính nào?
A. Các giá trị luôn được cộng nguyên tử vì task dùng Fork/Join.
B. Biến chung tự thành volatile khi được capture trong task.
C. Race condition có thể làm mất cập nhật giữa các nhánh.
D. Lệnh join tự hoàn tác các phép cộng bị trùng trước đó.
Đáp án đúng: C

Câu 56: Khi gọi ForkJoinPool.invoke với một ForkJoinTask phù hợp, tác động nào đúng?
A. Pool chỉ đưa task vào queue rồi trả về Future ngay.
B. Pool lập tức hủy task nếu không có worker đang rảnh.
C. Pool chỉ đăng ký task vào Phaser của các worker.
D. Pool thực thi task và trả kết quả sau khi hoàn thành.
Đáp án đúng: D

Câu 57: Khi cần đồng bộ nhiều vòng xử lý với số bên tham gia thay đổi, loại công cụ nào phù hợp?
A. Phaser hỗ trợ đăng ký và hủy đăng ký các party qua phase.
B. CountDownLatch tự tăng số party mới trong mỗi vòng.
C. CyclicBarrier cho phép đổi số bên tham gia bất kỳ lúc nào.
D. Semaphore mặc định chờ mọi bên đến cuối mỗi vòng.
Đáp án đúng: A

Câu 58: Trong Phaser, arriveAndAwaitAdvance thể hiện hành vi nào?
A. Bỏ một party vĩnh viễn và trả về ngay không cần chờ.
B. Tăng số party tham gia trước khi báo hoàn thành phase.
C. Hủy tất cả party còn lại mà không đổi phase hiện hành.
D. Báo đã đến phase hiện tại rồi chờ phase chuyển tiếp.
Đáp án đúng: D

Câu 59: Nếu một worker kết thúc vĩnh viễn và không tham gia các phase sau, nên dùng gì?
A. arriveAndAwaitAdvance rồi giữ party đang đăng ký mãi.
B. register để thêm một party thay cho worker vừa rời.
C. getPhase để tự động hủy đăng ký khỏi Phaser hiện tại.
D. arriveAndDeregister để giảm số party ở các phase sau.
Đáp án đúng: D

Câu 60: Với ThreadLocalRandom, cách lấy generator cho thread đang chạy là gì?
A. new ThreadLocalRandom() tạo generator mới công khai mỗi lần.
B. Random.getInstance() tải generator qua ServiceLoader.
C. ThreadLocalRandom.current() trả instance dành cho thread.
D. ForkJoinPool.commonPool() cung cấp generator theo worker.
Đáp án đúng: C

Câu 61: ThreadLocalRandom.current().nextInt(bound) chọn phạm vi giá trị nào?
A. Từ 0 đến bound bao gồm cả giá trị bound.
B. Từ 0 đến bound-1 nếu bound dương.
C. Từ 1 đến bound nếu bound dương.
D. Từ -bound đến bound-1 với mọi bound.
Đáp án đúng: B

Câu 62: LinkedTransferQueue.transfer khác thao tác thêm không chờ thông thường ở điểm nào?
A. Luôn chỉ đưa phần tử vào queue rồi trả về tức thì.
B. Có thể đợi tới khi consumer nhận phần tử được chuyển.
C. Luôn xóa phần tử cũ nhất trước khi thêm phần tử mới.
D. Tự phát bản sao dữ liệu đến tất cả consumer đăng ký.
Đáp án đúng: B

Câu 63: Ứng dụng cần deque nhiều thread cùng thêm và lấy ở hai đầu; lựa chọn nào phù hợp?
A. ArrayDeque bảo đảm thread safety cho mọi lời gọi không cần khóa.
B. LinkedList tự bảo vệ mọi phương thức bằng CAS mặc định.
C. ConcurrentLinkedDeque hỗ trợ thao tác đồng thời ở cả hai đầu.
D. PriorityQueue duy trì hai đầu FIFO mà không cần đồng bộ.
Đáp án đúng: C

Câu 64: Objects.requireNonNull giúp kiểm soát đầu vào theo cách nào?
A. Tự thay thế null bằng object mặc định của kiểu generic.
B. Chuyển mọi tham chiếu null thành Optional.empty khi gọi.
C. Chỉ ghi cảnh báo ra log và tiếp tục trả về một null.
D. Ném NullPointerException sớm khi đối số truyền vào null.
Đáp án đúng: D
