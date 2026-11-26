Câu 1. Với `InputStream.read()` không tham số, giá trị nào báo đã hết dữ liệu?
A. Giá trị `0` khi luồng đã tới cuối dữ liệu
B. Giá trị `-1` khi luồng đã tới cuối dữ liệu
C. Giá trị `null` khi luồng đã tới cuối dữ liệu
D. Giá trị `255` khi luồng đã tới cuối dữ liệu
Đáp án đúng: B

Câu 2. Khi gọi `InputStream.read(byte[])` với mảng không rỗng, giá trị trả về thông thường thể hiện gì?
A. Số byte còn lại trong luồng nguồn
B. Vị trí byte cuối cùng của luồng nguồn
C. Số byte thực tế đã đọc vào mảng đích
D. Độ dài tối đa của mảng đích được cấp
Đáp án đúng: C

Câu 3. `OutputStream.write(int value)` thực sự ghi phần nào của `value`?
A. Chuỗi chữ số thập phân của đối số
B. Mười sáu bit thấp nhất của đối số
C. Ghi tám bit thấp của đối số `int`
D. Toàn bộ ba mươi hai bit của đối số
Đáp án đúng: C

Câu 4. Phân biệt đúng nhất `Reader` với `InputStream` trong Java là gì?
A. `Reader` đọc ký tự, `InputStream` đọc byte
B. `Reader` đọc tệp, `InputStream` đọc mạng
C. `Reader` đọc mạng, `InputStream` đọc tệp
D. `Reader` đọc byte, `InputStream` đọc ký tự
Đáp án đúng: A

Câu 5. Chức năng cốt lõi của `InputStreamReader` khi biết charset là gì?
A. Giải mã chuỗi byte thành các ký tự Java
B. Chuyển đường dẫn tệp thành các ký tự
C. Mã hóa ký tự Java thành các byte đầu ra
D. Chuyển luồng byte thành các gói mạng TCP
Đáp án đúng: A

Câu 6. Đặt `StandardCharsets.UTF_8` vào `OutputStreamWriter` có tác dụng gì?
A. Giải mã byte thành ký tự theo chuẩn UTF-8
B. Chuyển tệp sang UTF-8 bằng đổi tên tệp
C. Kiểm tra mọi byte đầu vào là ký tự ASCII
D. Mã hóa ký tự thành byte theo chuẩn UTF-8
Đáp án đúng: D

Câu 7. Khi dùng `BufferedReader.readLine()`, kết quả nào đúng ở cuối tệp?
A. Trả `null` ở EOF, bỏ dấu xuống dòng
B. Trả `-1` khi hết dòng, bỏ dấu xuống dòng
C. Trả `""` khi hết dòng, giữ dấu xuống dòng
D. Trả `null` ở dòng rỗng, giữ dấu xuống dòng
Đáp án đúng: A

Câu 8. `BufferedOutputStream.flush()` chủ yếu bảo đảm thao tác nào?
A. Đồng bộ byte xuống thiết bị lưu trữ vật lý
B. Đẩy byte còn đệm sang luồng đầu ra bọc dưới
C. Giải phóng bộ đệm và đóng cả luồng bên dưới
D. Xóa toàn bộ dữ liệu đã ghi vào luồng bên dưới
Đáp án đúng: B

Câu 9. `PrintWriter` kiểm tra lỗi I/O trong lúc in bằng cách nào?
A. Gọi `close()` để nhận ngoại lệ I/O đã ghi
B. Gọi `checkError()` để xem cờ lỗi I/O
C. Gọi `printf()` để nhận ngoại lệ I/O đã ghi
D. Gọi `flush()` để nhận ngoại lệ I/O đã ghi
Đáp án đúng: B

Câu 10. `DataOutputStream.writeInt(0x01020304)` ghi theo cách nào?
A. Ghi bốn byte với byte giá trị thấp đứng trước
B. Ghi tám byte với byte giá trị cao đứng trước
C. Ghi chuỗi `01020304` theo định dạng UTF-8
D. Ghi bốn byte với byte giá trị cao đứng trước
Đáp án đúng: D

Câu 11. `InputStream.transferTo(out)` được dùng phù hợp cho việc nào?
A. Đọc đúng một byte rồi tự động đóng hai luồng
B. Đọc ngược các byte từ cuối nguồn đến đầu nguồn
C. Chép các byte còn lại sang `OutputStream` đích
D. Chép một chuỗi ký tự sang đối tượng `Writer`
Đáp án đúng: C

Câu 12. Vì sao tránh `InputStream.readAllBytes()` trên nguồn có kích thước không kiểm soát?
A. Vì kết quả chỉ chứa nội dung đã giải mã UTF-8
B. Vì phương thức luôn chỉ đọc tối đa 8 KB đầu
C. Vì mảng chứa toàn bộ nội dung có thể tốn heap
D. Vì phương thức tự tạo một memory-mapped file
Đáp án đúng: C

Câu 13. `Files.readString(path, StandardCharsets.UTF_8)` thực hiện điều gì?
A. Trả về toàn bộ dữ liệu dưới dạng `byte[]`
B. Trả về đường dẫn tuyệt đối của tệp đã chọn
C. Đọc từng dòng dưới dạng một `Stream<String>`
D. Đọc tệp và giải mã dữ liệu theo UTF-8
Đáp án đúng: D

Câu 14. Mặc định `Files.writeString(path, text)` xử lý tệp đích thế nào?
A. Tạo tệp mới với tên khác nếu tên đã tồn tại
B. Chỉ ghi nối cuối nếu đường dẫn đã tồn tại
C. Luôn thất bại nếu đường dẫn đã tồn tại
D. Tạo nếu thiếu và ghi đè nội dung nếu đã tồn tại
Đáp án đúng: D

Câu 15. Dùng `Files.writeString(path, text, UTF_8, CREATE, APPEND)` nhằm mục đích gì?
A. Tạo tệp nếu thiếu, thay hết nếu tệp tồn tại
B. Tạo tệp nếu thiếu, ghi nối nếu đã có
C. Chỉ ghi khi tệp đã tồn tại, không tạo tệp
D. Chỉ ghi khi tệp chưa tồn tại, không nối tiếp
Đáp án đúng: B

Câu 16. Mặc định `Files.copy(source, target)` gặp tệp đích đã tồn tại sẽ ra sao?
A. Chỉ bổ sung byte còn thiếu vào tệp đích
B. Tự động ghi đè không cần tùy chọn bổ sung
C. Thường ném `FileAlreadyExistsException`
D. Đổi tên tệp đích trước khi sao chép nội dung
Đáp án đúng: C

Câu 17. Khi `Files.copy(sourceDir, targetDir)` sao chép một thư mục, nhận định nào đúng?
A. Không tự sao chép đệ quy các thư mục con
B. Tự sao chép mọi tệp và thư mục con đệ quy
C. Chỉ sao chép các tệp, bỏ qua mọi thư mục con
D. Chỉ sao chép các thư mục con, bỏ qua tệp
Đáp án đúng: A

Câu 18. Với `Files.move(source, target, ATOMIC_MOVE)`, khi nhà cung cấp không hỗ trợ thì sao?
A. Luôn sử dụng đường dẫn tạm và đổi tên hai lần
B. Có thể ném `AtomicMoveNotSupportedException`
C. Luôn hoàn thành di chuyển mà không báo lỗi
D. Luôn đổi sang sao chép và xóa một cách im lặng
Đáp án đúng: B

Câu 19. `Files.createDirectories(path)` khác `createDirectory(path)` ở điểm nào?
A. Có thể tạo các thư mục cha còn thiếu
B. Chỉ tạo thư mục cuối nếu tất cả thư mục cha đã có
C. Có thể tự dọn toàn bộ thư mục cũ trước khi tạo
D. Chỉ hoạt động nếu đường dẫn đã có đủ thư mục cha
Đáp án đúng: A

Câu 20. Tính chất của `Files.createFile(path)` khi đường dẫn chưa tồn tại là gì?
A. Kiểm tra tồn tại rồi tạo một thư mục rỗng mới
B. Kiểm tra tồn tại rồi ghi đè tệp nếu đã có
C. Kiểm tra tồn tại rồi tự động tạo mọi thư mục cha
D. Kiểm tra tồn tại và tạo tệp trong một thao tác nguyên tử
Đáp án đúng: D

Câu 21. Khi `child` là đường dẫn tương đối, `base.resolve(child)` sẽ thế nào?
A. Thay thế tên cuối của `base` bằng `child`
B. Trả về thư mục cha của đường dẫn `base`
C. Chuyển `child` sang đường dẫn tuyệt đối
D. Ghép `child` vào cuối đường dẫn `base`
Đáp án đúng: D

Câu 22. `Path.normalize()` xử lý các thành phần `.` và `..` theo cách nào?
A. Kiểm tra tệp tồn tại rồi trả về đường dẫn thật
B. Di chuyển tệp đến đường dẫn rút gọn mới
C. Chuẩn hóa đường dẫn về mặt cú pháp, không đọc tệp
D. Truy cập hệ thống tệp để phân giải symbolic link
Đáp án đúng: C

Câu 23. `Path.toRealPath()` mặc định thực hiện việc gì với một đường dẫn hợp lệ?
A. Trả đường dẫn thực, kiểm tra tồn tại và theo liên kết
B. Ghi lại symbolic link bằng đường dẫn tương đối mới
C. Rút gọn chuỗi đường dẫn mà không truy cập hệ thống tệp
D. Tạo tệp nếu chưa tồn tại trước khi trả đường dẫn
Đáp án đúng: A

Câu 24. Hai đường dẫn khác tên nhưng chỉ tới cùng một tệp được kiểm tra bằng API nào?
A. `p1.toString().equals(p2.toString())` để so tệp
B. `Files.size(p1) == Files.size(p2)` để so tệp
C. `p1.getFileName().equals(p2.getFileName())` để so tệp
D. `Files.isSameFile(p1, p2)` để so đối tượng tệp
Đáp án đúng: D

Câu 25. Vì sao nên đặt `Files.walk(root)` trong try-with-resources?
A. Vì `Stream<Path>` có thể giữ tài nguyên mở
B. Vì `walk()` chỉ chạy khi luồng ghi đã được flush
C. Vì `walk()` tự ghi lại đường dẫn trong tệp tạm
D. Vì `walk()` chỉ duyệt nếu stream được mở lại
Đáp án đúng: A

Câu 26. Trong `Files.walkFileTree`, `preVisitDirectory` trả `SKIP_SUBTREE` có ý nghĩa gì?
A. Bỏ duyệt các thư mục cùng cấp với thư mục này
B. Bỏ duyệt toàn bộ cây kể cả các nhánh khác
C. Bỏ duyệt các mục con của thư mục hiện tại
D. Chỉ bỏ qua tệp thường nhưng vẫn duyệt thư mục con
Đáp án đúng: C

Câu 27. Với `BasicFileAttributes`, bộ phương thức nào dùng để đọc thuộc tính tệp?
A. `size()`, `owner()`, `isRegularFile()`
B. `size()`, `lastModifiedTime()`, `fileName()`
C. `size()`, `lastModifiedTime()`, `isRegularFile()`
D. `size()`, `lastModifiedTime()`, `isReadable()`
Đáp án đúng: C

Câu 28. Phát biểu nào đúng về `Files.probeContentType(path)`?
A. Có thể trả `null`; kết quả phụ thuộc triển khai
B. Luôn đọc chính xác magic bytes từ mọi định dạng
C. Luôn trả `application/octet-stream` nếu không biết
D. Luôn trả charset ký tự của nội dung tập tin
Đáp án đúng: A

Câu 29. Khi dùng `Files.isReadable(path)` trước khi mở tệp, cần lưu ý điều gì?
A. Kiểm tra trước khóa quyền tệp đến hết phương thức
B. Lần kiểm tra trước không bảo đảm mở thành công
C. Kiểm tra trước buộc mọi lần đọc sau đều hợp lệ
D. Kiểm tra trước giữ độc quyền tệp cho tới khi mở
Đáp án đúng: B

Câu 30. Đối với `Files.lines(path, UTF_8)`, cách sử dụng nào đúng để tránh rò rỉ?
A. Đóng `Stream<String>` sau khi xử lý các dòng
B. Không cần đóng vì stream không giữ tài nguyên mở
C. Chỉ cần gọi `count()` là chắc chắn đóng stream
D. Chỉ cần gọi `forEach()` là chắc chắn đóng stream
Đáp án đúng: A

Câu 31. Khi mở tệp với `StandardOpenOption.CREATE_NEW`, điều gì xảy ra nếu tệp đã tồn tại?
A. Tệp hiện tại được mở để ghi nối vào cuối
B. Tệp hiện tại được mở để ghi đè từ đầu
C. Tệp hiện tại bị xóa rồi tạo lại nội dung trống
D. Thao tác tạo mới thất bại với lỗi đã tồn tại
Đáp án đúng: D

Câu 32. Gọi `channel.position(128)` trên `FileChannel` có tác dụng gì?
A. Đặt giới hạn của mọi `ByteBuffer` thành 128
B. Đặt vị trí hiện tại để đọc hoặc ghi tuần tự tiếp theo
C. Giới hạn dung lượng tệp xuống đúng 128 byte
D. Di chuyển con trỏ của mọi channel trong JVM
Đáp án đúng: B

Câu 33. Khi gọi `FileChannel.read(dst, offset)`, vị trí hiện tại của channel thay đổi thế nào?
A. Tăng bằng số byte đã đọc vào bộ đệm đích
B. Không đổi; `offset` chỉ định vị trí đọc
C. Được cập nhật thành `offset` trước khi đọc
D. Được cập nhật thành `offset + dst.capacity()`
Đáp án đúng: B

Câu 34. Sau khi ghi dữ liệu vào `ByteBuffer`, `flip()` chuẩn bị cho thao tác đọc bằng cách nào?
A. Đặt `limit` bằng `position` cũ, rồi `position` về 0
B. Xóa các byte đã ghi và đưa `limit` về `capacity`
C. Đặt `capacity` bằng `position` cũ, rồi `limit` về 0
D. Đưa `position` về 0 và giữ nguyên `limit` cũ
Đáp án đúng: A

Câu 35. `ByteBuffer.clear()` thực tế làm gì với nội dung của buffer?
A. Đặt lại `position` và `limit` mà không xóa byte
B. Ghi toàn bộ số 0 vào các byte của buffer
C. Giải phóng toàn bộ vùng nhớ ngoài heap
D. Đóng channel đang liên kết với buffer
Đáp án đúng: A

Câu 36. Khi đọc dở một buffer và cần ghi dữ liệu mới, `compact()` sẽ làm gì?
A. Xóa sạch mọi byte trước khi chuyển sang đọc
B. Khóa buffer ở chế độ chỉ đọc vĩnh viễn
C. Giữ byte đã đọc và bỏ phần byte chưa đọc
D. Chuyển byte chưa đọc về đầu để tiếp tục ghi
Đáp án đúng: D

Câu 37. Điều nào đúng về `ByteBuffer.allocateDirect(n)`?
A. Luôn cấp phát trên Java heap như `allocate(n)`
B. Luôn ánh xạ một tệp vào vùng nhớ của tiến trình
C. Tạo direct buffer có thể lưu ngoài heap
D. Luôn nhanh hơn heap buffer cho mọi thao tác
Đáp án đúng: C

Câu 38. Thứ tự byte mặc định của `ByteBuffer` mới tạo là gì?
A. Thứ tự byte của CPU đang chạy tiến trình
B. Thứ tự byte được quyết định từ charset UTF-8
C. `BIG_ENDIAN` cho các giá trị nhiều byte
D. `LITTLE_ENDIAN` cho các giá trị nhiều byte
Đáp án đúng: C

Câu 39. `ByteBuffer.slice()` tác động tới dữ liệu và vị trí ra sao?
A. Chuyển vùng byte nguồn thành buffer chỉ đọc
B. Chung vùng byte nền nhưng có `position` riêng
C. Sao chép byte sang vùng mới và có vị trí riêng
D. Dùng vùng byte riêng nhưng chung `position`
Đáp án đúng: B

Câu 40. Với `FileChannel.transferTo(pos, count, dest)`, khi chép tệp lớn cần lưu ý gì?
A. Luôn chuyển toàn bộ tệp bất kể `pos` và `count`
B. Tự động đóng channel đích khi hoàn tất lời gọi
C. Luôn chuyển chính xác `count` byte trong một lời gọi
D. Có thể chuyển ít byte hơn yêu cầu, cần kiểm tra số chuyển
Đáp án đúng: D

Câu 41. `RandomAccessFile.seek(100)` xác định vị trí như thế nào?
A. Đặt con trỏ tới dòng văn bản thứ 100 trong tệp
B. Đặt con trỏ tệp tới offset byte 100 tính từ đầu
C. Di chuyển con trỏ thêm 100 byte từ chỗ hiện tại
D. Giới hạn độ dài tệp tối đa còn đúng 100 byte
Đáp án đúng: B

Câu 42. `FileChannel.force(true)` yêu cầu đồng bộ những thành phần nào?
A. Chỉ đồng bộ metadata, không gồm nội dung tệp
B. Chỉ đồng bộ nội dung, bỏ qua mọi metadata
C. Đồng bộ nội dung tệp và cập nhật metadata
D. Chỉ đẩy byte từ `ByteBuffer` sang `FileChannel`
Đáp án đúng: C

Câu 43. Trong vùng nhớ ánh xạ đọc-ghi, `MappedByteBuffer.force()` dùng để làm gì?
A. Chuyển buffer từ chế độ đọc-ghi sang chỉ đọc
B. Yêu cầu ghi các thay đổi vùng ánh xạ ra thiết bị
C. Tạo lại ánh xạ mới ở offset của con trỏ tệp
D. Đóng `FileChannel` và giải phóng ánh xạ ngay
Đáp án đúng: B

Câu 44. Điều gì đúng về `FileChannel.lock()` khi vùng khóa bị tiến trình khác giữ?
A. Luôn trả `null` ngay thay vì đợi cấp khóa
B. Luôn bỏ qua khóa của tiến trình đang giữ
C. Luôn tự động xóa khóa của tiến trình đang giữ
D. Có thể chờ tới khi khóa vùng tệp được cấp
Đáp án đúng: D

Câu 45. Khi cùng JVM đã giữ khóa chồng lấn, `FileChannel.tryLock()` có thể làm gì?
A. Tự động thu hồi khóa cũ rồi lấy khóa mới
B. Chờ đến khi một luồng khác tự giải phóng
C. Ném `OverlappingFileLockException` cho vùng trùng
D. Trả `null` trong mọi trường hợp vùng trùng
Đáp án đúng: C

Câu 46. `AsynchronousFileChannel.read(dst, pos)` trả về đối tượng gì?
A. `Future<Integer>` báo số byte của thao tác đọc
B. `ByteBuffer` mới chứa kết quả đọc bất đồng bộ
C. `InputStream` đã đọc xong toàn bộ dữ liệu
D. `FileLock` bảo vệ vùng đọc bất đồng bộ
Đáp án đúng: A

Câu 47. Với cách đọc bất đồng bộ có `CompletionHandler`, kết quả được báo thế nào?
A. Chỉ gọi `completed` rồi ném lỗi vào caller
B. Chỉ gọi `failed` rồi caller tự đọc kết quả
C. Gọi `failed` khi thành công, `completed` khi lỗi
D. Gọi `completed` khi thành công, `failed` khi lỗi
Đáp án đúng: D

Câu 48. Khi dùng NIO `Selector` để đợi readiness, kiểu channel nào phù hợp?
A. `AsynchronousFileChannel` với `CompletionHandler`
B. `SocketChannel` cấu hình chế độ non-blocking
C. `FileChannel` mở để đọc từ đĩa bằng `READ`
D. `FileChannel` mở để ghi ra đĩa bằng `WRITE`
Đáp án đúng: B
