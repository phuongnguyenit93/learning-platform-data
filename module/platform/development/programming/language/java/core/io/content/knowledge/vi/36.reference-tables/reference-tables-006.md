# Bảng lỗi I/O thường gặp và thông tin cần kiểm tra trong Java

## Mục đích và cách sử dụng

Tài liệu này là bảng **tra cứu nhanh nhưng có giải thích** cho lỗi Java Core I/O: đọc/ghi tệp bằng java.io và java.nio.file, xử lý byte/character stream, charset, channel, socket, nén ZIP và Java object serialization. Khi thấy lỗi, hãy xác định thao tác vừa thực hiện, tìm tên exception hoặc thông điệp gần nhất trong bảng, kiểm tra bằng chứng tối thiểu và chọn cách sửa theo nguyên nhân đã xác nhận.

**Nguyên tắc quan trọng:** tên exception cho biết nhóm vấn đề, chưa chứng minh nguyên nhân. Cùng một thao tác đọc tệp có thể phát sinh IOException, một lớp con cụ thể hơn hoặc RuntimeException tùy API, hệ điều hành, file-system provider, quyền truy cập và thời điểm lỗi xuất hiện. Thông điệp như "Permission denied", "The process cannot access the file" và "Too many open files" thường do môi trường cung cấp; không được giả định chúng luôn ứng với cùng một lớp exception trên mọi hệ thống.

### Cần thu thập thông tin gì trước tiên?

Với một sự cố, ghi lại có kiểm soát:

1. **Thao tác và API:** Files.readString, Files.newInputStream, Files.move, FileInputStream, BufferedReader, Socket.connect, ZipInputStream, ObjectInputStream.readObject…; đọc hay ghi; chạy đồng bộ hay bất đồng bộ.
2. **Exception đầy đủ:** loại ngoại lệ cụ thể, message, nguyên nhân lồng nhau (cause), các suppressed exceptions nếu có, và stack trace tại điểm ném lỗi đầu tiên liên quan ứng dụng.
3. **Đối tượng đích:** đường dẫn tuyệt đối đã chuẩn hóa về mặt cú pháp, loại path (file/thư mục/link), endpoint host:port hoặc định dạng dữ liệu. Che các thông tin nhạy cảm trong log; không ghi token, mật khẩu, nội dung tệp riêng tư.
4. **Môi trường:** OS, JDK, working directory, container/mount, encoding/charset, trạng thái ổ đĩa, quota, file descriptor/handle, quyền của **tài khoản đang chạy**.
5. **Thời điểm và phạm vi:** xảy ra ở bước mở, đọc, ghi, flush hay close; một lần hay lặp lại; một file hay mọi file; trước/sau khi deploy; có tiến trình đồng thời sửa/xóa/đổi tên dữ liệu không.
6. **Kết quả cần làm rõ:** lỗi có khả năng khắc phục bằng thay đường dẫn/quyền/schema không, có cần retry không, retry có an toàn hoặc khiến ghi trùng không, và dữ liệu đã được ghi một phần hay chưa.

Không ép toàn bộ lỗi vào một khối catch(IOException) chỉ để in "I/O failed": điều đó làm mất ngữ cảnh. Giữ nguyên exception gốc, thêm tên thao tác và đường dẫn/endpoint đã che thông tin nhạy cảm.

## 1. Bảng tra cứu lỗi hệ thống tệp: java.nio.file và java.io

Đây là nhóm gặp thường xuyên khi dùng Files, Path, InputStream, OutputStream, FileChannel và thao tác với thư mục. Những lớp lỗi cụ thể của NIO phần lớn kế thừa IOException (đặc biệt FileSystemException), nhưng không phải mọi lỗi đều là checked exception.

| Lỗi/triệu chứng | Ý nghĩa và nguyên nhân thường gặp | Thông tin cần kiểm tra | Hướng xử lý |
| --- | --- | --- | --- |
| NoSuchFileException | Tệp hoặc thành phần trong đường dẫn không tồn tại tại lúc thao tác; có thể đã bị xóa/di chuyển sau kiểm tra trước đó | Path hiệu lực, working directory, tên/ký tự hoa-thường, đường dẫn cha, mount, thao tác của tiến trình khác | Xác nhận đúng file và lifecycle; tạo file nếu hợp đồng cho phép; xử lý vắng mặt như trạng thái nghiệp vụ khi phù hợp |
| FileNotFoundException | API java.io cũ không mở được tệp; có thể do tệp thiếu, quyền bị từ chối hoặc đường dẫn chỉ tới thư mục | API gọi, getMessage(), sự tồn tại và loại file, quyền mở, đường dẫn tương đối/tuyệt đối | Kiểm tra nguyên nhân hệ điều hành; đừng suy luận chắc chắn là file không tồn tại từ tên exception |
| AccessDeniedException | Quyền truy cập tệp/thư mục bị từ chối; thường từ NIO provider | Tài khoản thực thi, ACL/quyền file và thư mục cha, mount read-only, trạng thái chính sách bảo mật | Cấp quyền cần thiết hoặc đổi vị trí lưu; không chạy ứng dụng bằng quyền quản trị chỉ để che lỗi |
| SecurityException | Chính sách quyền của runtime hoặc môi trường từ chối hành động; là unchecked exception | Stack trace, security policy/runtime, sandbox, ứng dụng có quyền gọi API không | Điều chỉnh cấu hình/phạm vi cho phép theo chính sách; phân biệt với AccessDeniedException |
| FileAlreadyExistsException | Cố tạo đối tượng đã tồn tại, thường với CREATE_NEW hoặc Files.createFile/createDirectory | Đường dẫn và loại mục hiện tại, tên có bị tiến trình khác chiếm không, cần tính duy nhất không | Đặt tên duy nhất hoặc xử lý conflict rõ ràng; CREATE_NEW cung cấp kiểm tra/tạo mang tính nguyên tử tại provider hỗ trợ |
| DirectoryNotEmptyException | Thao tác xóa/di chuyển thư mục khi nội dung bên trong khiến operation không thể hoàn tất | Các mục bên trong (kể cả hidden), chương trình nào đang sử dụng, policy recursive-delete | Chỉ xóa đệ quy khi đó là yêu cầu nghiệp vụ đã xác nhận; tránh xóa nhầm dữ liệu |
| NotDirectoryException | Một thành phần được kỳ vọng là thư mục nhưng thực tế không phải thư mục | Từng phần của path, thuộc tính đường dẫn cha, symbolic link | Sửa đường dẫn hoặc cấu trúc thư mục; không tiếp tục bằng cách nối path tùy tiện |
| FileSystemLoopException | Duyệt link gây vòng khi follow symbolic links, ví dụ qua Files.walkFileTree | Cấu trúc liên kết tượng trưng, chế độ FOLLOW_LINKS, đường dẫn tạo vòng | Không follow link nếu không cần; phát hiện và bỏ qua vòng hoặc báo lỗi rõ ràng |
| FileSystemException | Lỗi file-system không có lớp con chuyên biệt, ví dụ không thể rename/move, file đang bị giữ, thiết bị lỗi | getFile(), getOtherFile(), getReason(), OS/provider và quyền, trạng thái ổ đĩa/lock | Dùng reason/cause để chẩn đoán; không coi FileSystemException là một nguyên nhân cụ thể |
| IOException: "No space left on device" / "Disk full" | Vùng lưu trữ không còn dung lượng hoặc vượt quota; lớp exception có thể thay đổi | Dung lượng, inode/quota (nếu có), vị trí file thực tế, temp directory, log/backup | Giải phóng/nâng quota, dự phòng dung lượng, kiểm tra ghi dở và giao dịch tương ứng |
| IOException: "Too many open files" | Cạn file descriptors/handles hoặc giới hạn OS; hay do không đóng stream/channel/socket | Số file mở của tiến trình, giới hạn hệ thống, xu hướng tăng, nhánh không close | Dùng try-with-resources, sửa leak, cân nhắc giới hạn concurrent I/O; chỉ tăng OS limit khi có lý do |
| IOException: "Read-only file system" | Môi trường không cho ghi trên mount hoặc file system hiện tại | Mount flags, volume container, vị trí output, môi trường deploy | Chuyển sang volume writable được cấu hình hoặc điều chỉnh mount hợp lệ |
| IOException: "Broken pipe" / "Connection reset" | Kết nối truyền dữ liệu đã bị đóng/reset khi chương trình ghi/đọc; là thông điệp từ network/pipe | Đầu nhận đã đóng? timeout? proxy/load balancer? số byte đã truyền? | Không tự retry việc ghi không idempotent; điều tra lifecycle kết nối và cơ chế xác nhận |
| InvalidPathException | Chuỗi path không hợp lệ theo hệ thống/provider hiện tại, ví dụ ký tự bị cấm; đây là unchecked exception | Dữ liệu đầu vào, OS, cú pháp path, Path.of(...) | Validate cấu trúc đầu vào, chuyển đổi format đúng theo hệ điều hành; không thay ký tự tùy ý làm sai định danh |
| ClosedFileSystemException | Truy cập FileSystem đã đóng, ví dụ hệ tệp ZIP được mount qua FileSystems; unchecked | Thời gian close, code giữ Path, lifecycle FileSystem provider | Đảm bảo các thao tác cần thiết diễn ra trước khi đóng và không dùng lại Path sau khi provider đã close |

**Lưu ý về checked/unchecked:** NoSuchFileException, AccessDeniedException, FileAlreadyExistsException và FileSystemException kế thừa IOException; InvalidPathException, ClosedFileSystemException và SecurityException kế thừa RuntimeException. Vì vậy catch(IOException) không bắt được mọi loại thất bại được liệt kê.

**Lưu ý về tồn tại và quyền:** Files.exists(path) trả false cả khi không thể xác định tình trạng tồn tại trong một số trường hợp; Files.notExists(path) cũng có thể trả false khi trạng thái không rõ. Đừng biến false thành bằng chứng chắc chắn file không tồn tại. Thao tác thực tế vẫn có thể thất bại do thay đổi đồng thời, dù ngay trước đó kiểm tra thành công.

## 2. Bảng lỗi khi đọc/ghi stream, buffer và channel

| Lỗi/triệu chứng | Thường xuất hiện khi nào | Thông tin cần kiểm tra | Hướng xử lý |
| --- | --- | --- | --- |
| EOFException | API yêu cầu đọc đủ một cấu trúc nhưng hết dữ liệu trước khi hoàn thành, ví dụ DataInputStream.readInt | Độ dài dữ liệu thực, format/thứ tự read-write, có header/version/checksum không, nguồn đã ghi xong chưa | Kiểm tra framing và dữ liệu cắt dở; phân biệt EOF hợp lệ ở vòng đọc byte và EOF bất thường khi đọc record |
| IOException: "Stream closed" | Đọc/ghi sau khi stream đã đóng; đôi khi wrapper khác đóng stream gốc | try-with-resources nào sở hữu resource, ai đóng trước, luồng sử dụng | Xác định ownership, không chia sẻ stream đã đóng; tránh đóng resource ở tầng không sở hữu |
| ClosedChannelException | Thao tác channel khi channel đã bị đóng | Thứ tự close, xử lý đa luồng, shutdown/cancel, channel lifecycle | Điều phối lifecycle, không tái sử dụng channel đã đóng |
| AsynchronousCloseException | Luồng khác đóng channel đang bị block trong một thao tác I/O | Thread nào close, có stop/cancel/shutdown không, stack trace tác vụ | Coi là hủy thao tác khi shutdown có chủ ý; sửa cạnh tranh đóng sớm nếu bất thường |
| ClosedByInterruptException | Thread bị interrupt khi đang block trên interruptible channel; channel cũng bị đóng | Thread interruption, executor shutdownNow, cancellation, trạng thái channel | Phân biệt hủy tác vụ với lỗi mạng/đĩa; tuân thủ chính sách interrupt và không retry mù |
| NonReadableChannelException / NonWritableChannelException | Dùng channel ở mode không cho đọc hoặc ghi; unchecked | Mode mở channel, OpenOption.READ/WRITE/APPEND, buffer và nhánh logic | Mở channel đúng mode và chỉ thực hiện thao tác được hỗ trợ |
| OverlappingFileLockException | Một lock trên cùng vùng file chồng lấn lock đã giữ trong cùng JVM, hoặc đang chờ lock chồng lấn; unchecked | Các lock đã được JVM giữ, vùng start/size, quản lý vòng đời FileLock | Điều phối lock trong cùng tiến trình, tránh khóa trùng; luôn release lock thích hợp |
| FileLockInterruptionException | Thread bị interrupt khi đang chờ lock của FileChannel | Chính sách interrupt, lịch sử lock, trạng thái worker/task | Điều tra tranh chấp khóa hoặc yêu cầu hủy; xử lý cancel đúng cách |
| InterruptedIOException | Một thao tác I/O bị ngắt và có thể đã chuyển một phần dữ liệu; có trường bytesTransferred | bytesTransferred, loại stream, thao tác hiện tại, trạng thái thread | Không tự suy luận toàn bộ thao tác chưa làm gì; quyết định resume/retry theo giao thức |
| IOException khi flush/close | Dữ liệu đệm chưa đẩy hết hoặc lỗi đóng resource, có thể xảy ra sau các lần write thành công | flush/close thực sự có chạy không, exception gốc và suppressed, FS/đường truyền còn sống? | Không công bố giao dịch thành công chỉ vì write trả về; kiểm tra lỗi close và đồng bộ/commit khi cần |
| BufferOverflowException / BufferUnderflowException | Ứng dụng ghi/đọc quá giới hạn còn lại của ByteBuffer; unchecked | position/limit/capacity, flip/clear/compact, kích thước record | Kiểm tra remaining() và giao thức byte; sửa vòng đời buffer, không tăng buffer tùy tiện |
| ReadOnlyBufferException | Ghi vào ByteBuffer chỉ đọc; unchecked | Buffer được tạo bởi asReadOnlyBuffer, map READ_ONLY hay cơ chế chia sẻ | Dùng buffer writable khi cần ghi hoặc tách vùng nhớ đúng mục đích |

### Ba điểm gây nhầm lẫn

- InputStream.read() trả **-1** khi đạt EOF thông thường. Đây là kết quả hợp lệ; không nhất thiết có EOFException. Ngược lại, DataInputStream.readFully/readInt có thể báo EOFException nếu không đủ byte cho cấu trúc được yêu cầu.
- Đối với InputStream.read(byte[]), số byte trả về có thể ít hơn độ dài buffer ngay cả khi **chưa** tới EOF. Cần lặp cho tới khi đủ dữ liệu theo framing/record, hoặc dùng readNBytes/readFully thích hợp.
- OutputStream.close() có thể flush phần đệm, nhưng không nên mặc định đó là cam kết dữ liệu đã được lưu bền vững trên đĩa. Nếu ứng dụng cần durability, phải xác định cơ chế sync/transaction cụ thể, ví dụ FileChannel.force(...) và giới hạn bảo đảm của môi trường.

## 3. Bảng lỗi charset, văn bản và dữ liệu nhị phân

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Kiểm tra gì? | Hướng xử lý |
| --- | --- | --- | --- |
| MalformedInputException | Dãy byte không hợp lệ theo charset đã chọn, như UTF-8 có byte tiếp nối sai | Nguồn byte, BOM, charset ghi/đọc, vị trí lỗi, file có bị cắt? | Chọn đúng charset theo hợp đồng dữ liệu; chỉ thay thế ký tự lỗi nếu nghiệp vụ chấp nhận mất thông tin |
| UnmappableCharacterException | Ký tự Unicode không thể biểu diễn trong charset đích hoặc chuỗi chuyển mã không ánh xạ được | Encoder/decoder, charset đích, dữ liệu gốc, coding-error action | Dùng UTF-8/Unicode phù hợp, hoặc xử lý lỗi chuyển mã minh bạch |
| CharacterCodingException | Nhóm checked exception cho lỗi mã hóa/giải mã ký tự | IOException cause, decoder/encoder, byte mẫu đã ẩn dữ liệu nhạy cảm | Giữ dữ liệu gốc để chẩn đoán; xác định charset trước khi decode |
| UTFDataFormatException | Đọc/ghi định dạng modified UTF-8 của DataInput/DataOutput (ví dụ readUTF/writeUTF) không hợp lệ hoặc giới hạn format bị vi phạm | Có đúng cặp writeUTF/readUTF không, format/số byte đã ghi, dữ liệu bị cắt không | Không dùng readUTF để đọc UTF-8 text bất kỳ; theo đúng giao thức DataInput/DataOutput |
| Ký tự thành "�" (replacement character) nhưng không throw | Decoder dùng hành vi thay thế lỗi hoặc dữ liệu đã bị mã hóa sai trước đó | Từng bước encode/decode, CharsetDecoder.onMalformedInput, lưu dữ liệu nguồn | Chọn chính sách REPORT để phát hiện sớm khi cần giữ nguyên dữ liệu |
| Ký tự "mojibake" (ví dụ "Ã©") | Byte dùng một charset nhưng giải mã bằng charset khác | Charset gốc/đích, BOM, default charset và thông tin truyền tải | Chỉ định charset tường minh ở cả hai đầu; không encode lại chuỗi đã decode sai để vá bằng mẹo |
| File trông như rỗng hoặc thiếu dòng | Buffer chưa flush, Reader/Writer chưa close, logic đọc bỏ mất phần tử cuối | flush/close, vòng while, line separators, length trên đĩa và trong RAM | Đóng stream đúng, kiểm tra code đọc đến EOF và xử lý phần dữ liệu cuối |

**Phân biệt:** UTF-8 thường dùng với Files.readString(path, StandardCharsets.UTF_8), InputStreamReader(..., UTF_8), OutputStreamWriter(..., UTF_8). DataInputStream.readUTF và DataOutputStream.writeUTF sử dụng **modified UTF-8 có tiền tố độ dài**, không tương đương việc đọc/ghi văn bản UTF-8 thông thường.

## 4. Bảng lỗi mạng: Socket, timeout và TLS

Nhóm này thuộc java.net và javax.net.ssl; một số lỗi là lớp con của IOException. Khi chẩn đoán, phải biết lỗi xảy ra ở **DNS, TCP connect, TLS handshake, đọc, ghi hay đóng**.

| Lỗi | Dấu hiệu/ý nghĩa thường gặp | Kiểm tra thực tế | Cách tiếp cận |
| --- | --- | --- | --- |
| UnknownHostException | Không phân giải được hostname hoặc hostname không có địa chỉ phù hợp | Hostname, DNS từ môi trường chạy, search domain, cấu hình container/proxy, độ ổn định DNS | Sửa DNS/host; chỉ retry giới hạn khi lỗi thực sự tạm thời |
| ConnectException | Kết nối TCP bị từ chối hoặc thất bại ở bước connect, như "Connection refused" | Host:port, service đang lắng nghe, firewall, routing, IPv4/IPv6, proxy | Xác nhận endpoint và trạng thái dịch vụ; không nhầm với read timeout |
| SocketTimeoutException | Vượt timeout khi socket connect hoặc read (theo thao tác cấu hình) | Connect timeout hay SO_TIMEOUT? Mạng có kết nối chưa? server phản hồi chậm? | Đặt timeout có chủ đích, đo latency, retry theo idempotency/backoff |
| SocketException | Lỗi socket chung, như reset, broken pipe, socket closed | Peer đã đóng chưa, local close, idle timeout, HTTP proxy, keepalive | Xác định lifecycle và phần dữ liệu có thể đã chuyển; không coi mọi reset là lỗi mạng có thể retry an toàn |
| BindException | Không thể bind địa chỉ/cổng, thường cổng đã được dùng hoặc địa chỉ không phù hợp | Socket local address/port, tiến trình đang giữ, cấu hình bind, quyền OS | Chọn port/địa chỉ hợp lệ, dừng tiến trình xung đột nếu được phép |
| SSLHandshakeException | Bắt tay TLS không hoàn thành (chứng chỉ, protocol, cipher, hostname, trust) | Cause chain, certificate chain/truststore, hostname, expiry, TLS version, đồng hồ hệ thống | Sửa trust/identity/protocol; không tắt xác thực chứng chỉ để bỏ qua lỗi |
| SSLException | Lỗi TLS tổng quát khi handshake hoặc truyền dữ liệu | Stack/cause, vị trí handshake hay application data, đóng kết nối | Tìm nguyên nhân gốc, kiểm tra giao thức và cấu hình hai đầu |

Các điều cần ghi nhớ:

- Timeout connect và timeout read là hai pha khác nhau. Connect thành công không chứng minh server sẽ trả dữ liệu đúng hạn.
- Retry thao tác đọc trạng thái thường khác retry lệnh ghi/thanh toán: nếu request đã đến server mà phản hồi mất, client có thể không biết thao tác đã hoàn thành hay chưa. Dùng request-id, idempotency key hay quy trình xác nhận theo ứng dụng.
- Không log payload, credential, private key, access token hoặc nội dung chứng chỉ nhạy cảm khi thu thập trace. Chỉ ghi thông tin kỹ thuật cần thiết cho việc chẩn đoán.

## 5. Bảng lỗi ZIP và object serialization

| Lỗi/triệu chứng | Vị trí và ý nghĩa | Thông tin cần kiểm tra | Hướng xử lý |
| --- | --- | --- | --- |
| ZipException | java.util.zip gặp dữ liệu ZIP/GZIP/DEFLATE không hợp lệ hoặc không thể xử lý | Định dạng thực tế, header/magic, file đã tải đủ chưa, CRC/entry, phương thức nén | Xác thực nguồn và tính toàn vẹn, đảm bảo giải nén đúng định dạng; hạn chế kích thước giải nén để chống zip bomb |
| EOFException khi giải nén | Stream nén bị cắt hoặc cấu trúc chưa đủ | Số byte tải/nhận so với mong đợi, checksum, close của nguồn | Truyền/tải lại có kiểm soát, xác nhận độ đầy đủ trước xử lý |
| StreamCorruptedException | ObjectInputStream thấy header, token hoặc cấu trúc Java serialized stream sai | Bên ghi có dùng ObjectOutputStream không, thứ tự đọc/ghi, byte bị chèn/cắt, protocol mismatch | Đồng nhất định dạng và thứ tự, tránh trộn dữ liệu văn bản/thô vào luồng object |
| InvalidClassException | Lớp không tương thích với luồng (serialVersionUID, kiểu/class descriptor), hoặc ObjectInputFilter từ chối | Full message/cause, serialVersionUID, thay đổi class, filter policy, tên lớp nhị phân | Sửa tương thích/schema hoặc allowlist đúng; không vô hiệu hóa filter chỉ để chạy qua lỗi |
| NotSerializableException | Ghi một lớp không Serializable trong đồ thị đối tượng | Kiểu được nêu trong message, trường có chứa resource/đối tượng khác không serializable | Dùng DTO serializable, tách state không được serialize bằng transient khi đúng ngữ nghĩa |
| OptionalDataException | ObjectInputStream đọc theo kiểu không khớp dữ liệu primitive/đối tượng trong luồng, hoặc tới cuối dữ liệu custom | Thứ tự writeObject/writeInt/readObject/readInt, custom readObject/writeObject | Khớp format và thứ tự, quản lý version rõ ràng |
| InvalidObjectException | Dữ liệu đối tượng không hợp lệ trong validation/readResolve hoặc logic khôi phục | Cause, invariants của class, dữ liệu gốc, mã kiểm tra trong custom deserialization | Kiểm tra và từ chối dữ liệu không hợp lệ, sửa nguồn hoặc migration được xác minh |
| ClassNotFoundException | Bên đọc không tìm được class mô tả trong stream; là checked exception, không kế thừa IOException | Classpath/module path, tên package/class, version triển khai, custom class loader | Bảo đảm class tương ứng hiện diện hoặc thay định dạng trao đổi dữ liệu rõ schema |

**Giới hạn bảo mật của serialization:** ObjectInputFilter có thể giới hạn lớp, độ sâu, số tham chiếu, bytes và kích thước mảng khi deserialization. Phải cài filter **trước readObject()**, ưu tiên allowlist theo nguồn tin cậy và vẫn giới hạn kích thước đầu vào bên ngoài. Filter không xác thực người gửi, không thay mã hóa/chữ ký, không ngăn mọi rủi ro trong custom readObject. Với đầu vào không tin cậy, cân nhắc định dạng trao đổi có schema và validation rõ ràng.

## 6. Ví dụ Java 17+ chạy độc lập: tạo và phân biệt ba lỗi I/O

Ví dụ này tạo một thư mục tạm, minh họa ba exception cụ thể theo trình tự rồi dọn tệp tạm. Mỗi lỗi được bắt bằng kiểu ngoại lệ phù hợp để người học nhìn thấy cách đọc nguyên nhân. Không dùng đường dẫn nhạy cảm hoặc tài nguyên bên ngoài.

Tạo tệp **IoErrorLookupDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoErrorLookupDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("io-error-lookup-");
        Path missing = dir.resolve("missing.txt");
        Path existing = dir.resolve("existing.txt");
        Path invalidUtf8 = dir.resolve("invalid-utf8.txt");

        try {
            // 1. Không thể đọc tệp chưa tồn tại.
            try {
                Files.readString(missing, StandardCharsets.UTF_8);
            } catch (NoSuchFileException ex) {
                System.out.println("NoSuchFileException: missing.txt");
            }

            // 2. CREATE_NEW chỉ tạo file khi đường dẫn chưa tồn tại.
            Files.writeString(existing, "Hello", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);
            try {
                Files.writeString(existing, "Again", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("FileAlreadyExistsException: existing.txt");
            }

            // 3. Hai byte dưới đây không tạo thành chuỗi UTF-8 hợp lệ.
            Files.write(invalidUtf8, new byte[] {(byte) 0xC3, (byte) 0x28});
            try {
                Files.readString(invalidUtf8, StandardCharsets.UTF_8);
            } catch (MalformedInputException ex) {
                System.out.println("MalformedInputException: invalid UTF-8");
            }
        } finally {
            Files.deleteIfExists(invalidUtf8);
            Files.deleteIfExists(existing);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac IoErrorLookupDemo.java
java IoErrorLookupDemo
~~~

Kết quả mong đợi trong môi trường có thể tạo/đọc/ghi/xóa thư mục tạm:

~~~text
NoSuchFileException: missing.txt
FileAlreadyExistsException: existing.txt
MalformedInputException: invalid UTF-8
~~~

**Vì sao ví dụ hoạt động?**

1. Files.readString(missing, UTF_8) gặp file chưa tồn tại nên trên default file-system provider phổ biến ném NoSuchFileException. Không có bước kiểm tra exists trước, vì thao tác đọc là nơi trạng thái thật được xác định.
2. Files.writeString(existing, ..., CREATE_NEW) tạo file lần đầu. Lần thứ hai, chính tùy chọn CREATE_NEW yêu cầu không ghi đè đường dẫn đang tồn tại, nên ném FileAlreadyExistsException. Đây là lựa chọn thường phù hợp khi tránh ghi đè vô ý.
3. Byte 0xC3 là ký tự mở đầu của một chuỗi hai byte UTF-8, nhưng byte tiếp theo 0x28 không phải continuation byte hợp lệ. Files.readString(..., UTF_8) báo MalformedInputException, cho thấy lỗi ở **giải mã byte thành ký tự**, không phải tệp thiếu hay quyền bị từ chối.
4. finally dọn các đường dẫn được tạo trong bài. Nếu bản thân việc cleanup thất bại, IOException có thể được ném từ finally; trong ứng dụng lớn, nên giữ lại exception gốc và bổ sung lỗi cleanup như suppressed/log riêng thay vì vô tình che mất nguyên nhân đầu tiên.

**Giới hạn của ví dụ:** Nếu thư mục tạm không ghi được, hết dung lượng hoặc một tiến trình khác can thiệp, chương trình có thể thất bại bằng ngoại lệ khác trước khi in đủ ba dòng. Điều đó là hành vi I/O thực tế cần chẩn đoán, không phải lý do bắt mọi exception rồi in kết quả giả.

## 7. Mẫu chẩn đoán lỗi và ghi log có ngữ cảnh

Không cần ghi toàn bộ dữ liệu khách hàng để debug I/O. Ghi thông tin đủ để tìm ra **thao tác nào**, **đích nào** và **lý do hệ điều hành/provider báo gì**.

Ví dụ minh họa một method trong ứng dụng đã có logger và path:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

static String loadConfig(Path path) throws IOException {
    try {
        return Files.readString(path, StandardCharsets.UTF_8);
    } catch (NoSuchFileException ex) {
        // File được yêu cầu không tồn tại; chính sách có thể là trả 404.
        throw new IOException("Config is missing: " + path.getFileName(), ex);
    } catch (AccessDeniedException ex) {
        // Kiểm tra service account, ACL và quyền trên thư mục cha.
        throw new IOException("Cannot read config: access denied", ex);
    } catch (FileSystemException ex) {
        // getReason() có thể null; nội dung có thể phụ thuộc OS/provider.
        throw new IOException("Cannot read config: " + ex.getReason(), ex);
    }
}
~~~

Đây là **đoạn method minh họa**, không phải một chương trình độc lập vì chưa có class và main. Trong môi trường thực:

- Ghi stack trace/cause vào kênh log nội bộ có quyền phù hợp; chỉ trả thông báo an toàn cho người dùng. Không tự động in absolute path chứa tên tài khoản, bí mật hoặc cấu trúc hạ tầng ra API công khai.
- Giữ nguyên cause khi bọc lỗi. Không chuyển một lỗi quyền sang "file not found" trong log vận hành; tầng HTTP có thể trả mã thông báo khác nhưng cần giữ bằng chứng gốc.
- Với FileSystemException, dùng getFile(), getOtherFile(), getReason() nếu hữu ích; một số giá trị có thể null và exception message có thể mang thông tin không nên lộ công khai.
- Đừng bắt SecurityException bằng IOException. Nếu cần xử lý lỗi chính sách runtime, bắt theo hợp đồng riêng và đừng làm mờ dấu hiệu vi phạm chính sách.
- Khi dùng try-with-resources, lỗi từ close của resource có thể nằm trong getSuppressed() của exception chính. Đọc cả suppressed khi chuỗi thao tác có nhiều resource.

### Mẫu ghi nhận sự cố I/O

~~~text
Operation      : READ_TEXT / WRITE_BYTES / MOVE / SOCKET_CONNECT / DESERIALIZE
API            : Files.readString(Path, UTF_8)
Resource       : <path alias hoặc endpoint đã ẩn thông tin nhạy cảm>
Environment    : JDK version, OS, container/mount, service account
Exception      : <fully-qualified exception class>
Message/Reason : <thông điệp rút gọn, đã loại thông tin nhạy cảm>
Cause          : <cause chain, stack trace nội bộ>
Suppressed     : <các lỗi cleanup/close nếu có>
Input format   : UTF-8 / binary protocol / serialized object / ZIP / ...
Timing         : Thời điểm xảy ra, pha open/read/write/flush/close
Observed state : Exists? Directory? Permissions? Free space? Host:port reachable?
Concurrency    : Có writer/deleter/closer đồng thời? Có retry trước đó?
Next action    : Fix path / permissions / schema / storage / connectivity / code
~~~

Thông tin exists/isDirectory/isReadable chỉ là ảnh chụp tại một thời điểm, có thể thay đổi ngay sau đó. Không sử dụng chúng làm bảo đảm có thể mở/đọc/ghi thành công; vẫn cần xử lý lỗi từ thao tác thật.

## 8. Quy trình điều tra theo thứ tự ít rủi ro

1. **Xác định điểm thất bại:** đọc 1–3 stack frame thuộc mã của bạn cùng exception class, cause, suppressed. Đừng bắt đầu bằng việc thay charset hay cấp thêm quyền khi chưa biết pha lỗi.
2. **Đối chiếu loại API:** FileInputStream có thể báo FileNotFoundException rộng; Files có thể cung cấp NoSuchFileException hoặc AccessDeniedException cụ thể hơn. Với mạng, xác định connect/read/write/TLS trước khi đặt timeout.
3. **Kiểm tra dữ kiện không thay đổi hệ thống:** version JDK/OS, đường dẫn thực tế, working directory, isRegularFile/isDirectory, thông tin permission/mount nếu được phép; không chạy lệnh xóa, chmod đệ quy hoặc kill tiến trình để thử.
4. **Kiểm tra tài nguyên:** còn dung lượng/quota không, có bị leak stream/channel/socket không, file handle/lock có bị giữ không, pool và số lượng tác vụ I/O song song có bất thường không.
5. **Kiểm tra hợp đồng dữ liệu:** bên ghi và bên đọc có chung charset, cách phân khung record, thứ tự field, version/schema, checksum/length không; với ZIP và serialized stream, có đúng định dạng không.
6. **Tái hiện có kiểm soát:** dùng tệp tạm và dữ liệu không nhạy cảm; kiểm tra thành công + đầu vào thiếu + quyền bị từ chối + dữ liệu cắt dở + file đang bị sửa đồng thời khi các tình huống đó thực sự liên quan.
7. **Sửa nguyên nhân, kiểm thử case âm:** sửa đường dẫn/permissions/resource lifecycle/charset/framing; xác nhận exception cụ thể được xử lý đúng. Với thao tác ghi, kiểm tra trạng thái trước retry để tránh trùng hoặc hỏng dữ liệu.
8. **Bổ sung quan sát:** nếu sự cố chưa tái hiện, log thêm thao tác, số byte kỳ vọng/đã đọc (không log nội dung), thời gian connect/read/write, path alias, exception cause và correlation id.

### Câu hỏi quyết định nhanh

| Câu hỏi | Nếu câu trả lời là "Có" | Kiểm tra kế tiếp |
| --- | --- | --- |
| Lỗi xảy ra ngay khi mở file? | Khả năng cao liên quan path, type, permission hoặc resource | Path resolve, working directory, quyền của service account |
| Mở được nhưng fail sau nhiều lần đọc? | Dữ liệu bị cắt, framing sai, lỗi kết nối hoặc nguồn thay đổi | Độ dài/record boundary, EOF, bytes đã đọc, writer/peer |
| Chỉ lỗi với tiếng Việt/ký tự đặc biệt? | Charset hoặc chuyển mã không đồng nhất | UTF-8, BOM, decoder policy, byte gốc |
| Chỉ lỗi khi tải nhiều/đồng thời? | Leak, lock, contention hoặc race condition | try-with-resources, file handles, channel close, pool size |
| Chỉ lỗi khi deploy/container? | Working directory, mount, account, DNS hoặc permission đổi | Environment diff, volume, path, service user, network route |
| Chỉ lỗi với dữ liệu lưu từ bản cũ? | Format/schema/serialVersionUID thay đổi | Version, migration, classpath, backward compatibility |
| Chỉ lỗi sau thời gian idle của socket? | Idle timeout, peer/proxy close hoặc connection reset | Timeout cấu hình, keepalive, lifecycle, request replay safety |

## 9. Ngăn lỗi ngay khi thiết kế chương trình

### Quản lý vòng đời tài nguyên

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void printNonEmptyLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {
        String line;
        while ((line = reader.readLine()) != null) {
            if (!line.isBlank()) {
                System.out.println(line);
            }
        }
    }
}
~~~

Đây là method minh họa. try-with-resources đóng BufferedReader kể cả khi đọc thất bại và giúp tránh leak. Không mở stream ngoài try rồi quên close ở một nhánh return hoặc catch.

### Chọn phương án mở/ghi theo hợp đồng

- **Chỉ đọc:** Files.newInputStream(path, READ) hoặc Files.newBufferedReader(path, UTF_8); xử lý file thiếu, quyền và lỗi dữ liệu theo mục đích.
- **Tạo file mới, tuyệt đối không ghi đè:** Files.write(..., CREATE_NEW) hoặc Files.createFile(path), bắt FileAlreadyExistsException để xử lý xung đột.
- **Ghi thay thế có kiểm soát:** Ghi dữ liệu đầy đủ vào file tạm cùng file system, kiểm tra flush/close, rồi move thay thế nếu hợp đồng cho phép. ATOMIC_MOVE không được mọi provider hỗ trợ; phải xử lý AtomicMoveNotSupportedException và quyết định fallback theo yêu cầu về atomicity, không âm thầm giả vờ atomic.
- **Đọc dữ liệu lớn:** Dùng stream/channel và bộ đệm với giới hạn; tránh Files.readAllBytes cho file không kiểm soát kích thước vì có thể gây áp lực bộ nhớ.
- **Đọc text:** Chỉ định UTF-8 hoặc charset theo tài liệu dữ liệu, không dựa vào default charset khi trao đổi với hệ thống khác.
- **I/O mạng:** Cấu hình timeout từng pha, giới hạn kích thước payload và sử dụng retry có điều kiện/idempotent; ghi nhận kết quả một phần khi giao thức có yêu cầu.
- **Serialization:** Đặt ObjectInputFilter phù hợp trước khi gọi ObjectInputStream.readObject; validate dữ liệu sau khi khôi phục; hạn chế input bytes từ đầu.

### Khi nào nên retry?

| Loại tình huống | Retry tự động? | Lý do |
| --- | --- | --- |
| File chưa tồn tại do path gõ sai | Thường không | Lặp lại không sửa path |
| AccessDeniedException do ACL cố định | Thường không | Cần sửa quyền hoặc chính sách |
| FileAlreadyExistsException với CREATE_NEW | Không với cùng tên và cùng yêu cầu | Việc lặp lại sẽ tiếp tục xung đột |
| SocketTimeoutException trên truy vấn idempotent | Có thể, có giới hạn và backoff | Đôi lúc lỗi mạng tạm thời, nhưng vẫn cần giới hạn |
| Lệnh ghi có tác dụng phụ đã gửi, phản hồi timeout | Chỉ nếu có giao thức đảm bảo/idempotency key | Có nguy cơ thực thi hai lần |
| Hết dung lượng hoặc hết file handles | Không retry gấp vô hạn | Cần phục hồi tài nguyên và xử lý phần dữ liệu đã ghi |
| MalformedInputException do file sai charset cố định | Không | Cần sửa format/charset, retry không thay đổi byte |
| EOF bất thường của dữ liệu tải dở | Có thể tải lại nếu nguồn/hợp đồng cho phép | Phải kiểm tra checksum/length và tránh ghép sai phiên |

## 10. Kiểm tra kiến thức

1. Vì sao FileNotFoundException không đủ để kết luận file không tồn tại?
2. Files.exists(path) vừa trả true, nhưng ngay sau đó Files.readString(path) vẫn ném NoSuchFileException. Điều này có thể xảy ra như thế nào?
3. Khi DataInputStream.readInt ném EOFException, tại sao cách xử lý khác với vòng while(InputStream.read() != -1)?
4. Làm thế nào để nhận biết lỗi charset khác với lỗi stream byte bị cắt?
5. Khi thao tác Files.move thất bại, thông tin nào của FileSystemException giúp tìm nguyên nhân?
6. Tại sao đặt CREATE_NEW thường an toàn hơn chuỗi "kiểm tra exists rồi mới tạo" khi có nhiều writer?
7. SocketTimeoutException trong lúc connect khác gì trong lúc read? Vì sao không retry mọi lệnh gửi một cách vô điều kiện?
8. Lỗi IOException từ close ảnh hưởng thế nào đến khẳng định "ghi thành công"?
9. Những ngoại lệ nào trong bảng là unchecked, và vì sao catch(IOException) không bao phủ chúng?
10. InvalidClassException có thể biểu thị hai tình huống rất khác nhau nào trong Java serialization?

**Tiêu chí đạt:** Bạn chỉ ra được thao tác đang lỗi, exception và nguyên nhân có thể kiểm chứng; chọn được API/check cụ thể để phân biệt giả thuyết; xử lý tài nguyên và lỗi đúng, tránh retry nguy hiểm; không tiết lộ thông tin nhạy cảm khi ghi log.

## Tài liệu tham khảo Java SE 17

- java.io.IOException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html
- java.io.EOFException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html
- java.io.FileNotFoundException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html
- java.nio.file.Files: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- java.nio.file.FileSystemException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html
- java.nio.charset.MalformedInputException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html
- java.nio.channels.ClosedChannelException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedChannelException.html
- java.net.SocketTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html
- java.io.ObjectInputFilter: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Java tutorials — Basic I/O: https://docs.oracle.com/javase/tutorial/essential/io/
