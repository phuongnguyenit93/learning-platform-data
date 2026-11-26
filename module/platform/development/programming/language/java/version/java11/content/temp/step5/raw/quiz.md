Trong Java 11, String.isBlank() trả về true cho trường hợp nào?
A. Chỉ chuỗi có length bằng 0, không kiểm tra các ký tự bên trong.
B. Chuỗi chỉ gồm dấu cách ASCII, nhưng không gồm chuỗi rỗng.
C. Chuỗi rỗng hoặc chỉ chứa các ký tự Character.isWhitespace.
D. Chuỗi có ít nhất một ký tự whitespace, kể cả khi còn chữ.
Đáp án đúng: C

Điểm khác biệt chính giữa String.strip() và trim() trong Java 11 là gì?
A. strip dùng isWhitespace; trim xóa ký tự có mã đến U+0020.
B. strip chỉ xóa dấu cách ASCII; trim nhận diện toàn bộ Unicode whitespace.
C. strip xóa whitespace cả trong chuỗi; trim chỉ thao tác hai đầu chuỗi.
D. strip dùng locale hiện tại; trim luôn dùng locale mặc định của JVM.
Đáp án đúng: A

Kiểu kết quả của lời gọi "a\nb".lines() trong Java 11 là gì?
A. List<String> chứa các dòng, được tạo ngay lúc gọi phương thức.
B. String[] chứa những dòng được cắt ra từ chuỗi ban đầu.
C. Iterator<String> phải được duyệt trực tiếp bằng hasNext().
D. Stream<String> duyệt lần lượt nội dung các dòng của chuỗi.
Đáp án đúng: D

Giá trị của "ab".repeat(3) trong Java 11 là gì?
A. "ab3", vì số lần lặp được nối như chuỗi.
B. "ababab", vì nội dung gốc được nối ba lần.
C. "aaabbb", vì từng ký tự được lặp riêng ba lần.
D. "abababab", vì chuỗi gốc được giữ thêm một lần.
Đáp án đúng: B

Khi gọi text.stripLeading(), vùng whitespace nào bị loại bỏ?
A. Chỉ vùng whitespace nằm ở cuối chuỗi.
B. Cả vùng whitespace ở đầu và cuối chuỗi.
C. Mọi whitespace nằm giữa các ký tự trong chuỗi.
D. Xóa whitespace đầu chuỗi, giữ nguyên phần cuối.
Đáp án đúng: D

Đối với một chuỗi có whitespace ở cả hai đầu, stripTrailing() làm gì?
A. Xóa whitespace cuối chuỗi, giữ nguyên phần đầu.
B. Xóa whitespace ở đầu và giữ nguyên whitespace ở cuối.
C. Xóa đồng thời whitespace ở hai đầu của chuỗi.
D. Xóa toàn bộ whitespace, kể cả ở giữa nội dung.
Đáp án đúng: A

Với String s = "   ", cặp giá trị s.isEmpty() và s.isBlank() là gì?
A. true và true, vì cả hai đều kiểm tra khoảng trắng.
B. true và false, vì isEmpty bỏ qua dấu cách.
C. false và true, vì chuỗi có ký tự nhưng chỉ là whitespace.
D. false và false, vì isBlank chỉ nhận chuỗi rỗng.
Đáp án đúng: C

String.lines() xử lý dấu xuống dòng CRLF trong chuỗi như thế nào?
A. Xem CR và LF là hai dấu phân cách liên tiếp, tạo dòng trống ở giữa.
B. Chỉ nhận LF, còn CR luôn được giữ trong phần nội dung dòng.
C. Xem CRLF là một dấu kết thúc dòng duy nhất khi tách nội dung.
D. Chỉ nhận CR; ký tự LF trở thành ký tự thông thường của dòng.
Đáp án đúng: C

Đặc điểm nào đúng khi dùng String.lines() để xử lý nội dung nhiều dòng?
A. Mỗi phần tử dòng luôn kèm dấu xuống dòng gốc ở cuối.
B. Stream<String> chứa các dòng, không kèm ký tự xuống dòng.
C. Mọi dòng được chuyển thành chuỗi đã gọi strip() trước khi phát.
D. Luôn tạo trước một danh sách mutable chứa tất cả các dòng.
Đáp án đúng: B

Kết quả của "x".repeat(0) trong Java 11 là gì?
A. Chuỗi rỗng "", vì không có bản sao nào của "x" được tạo.
B. Chuỗi "x", vì số lần lặp bằng 0 giữ nguyên.
C. Giá trị null để biểu diễn không có phần tử.
D. IllegalArgumentException vì số lần lặp không dương.
Đáp án đúng: A

Files.readString(path) dùng charset nào khi không truyền tham số charset?
A. Charset.defaultCharset() được chọn theo cấu hình hệ điều hành.
B. ISO-8859-1 để mọi byte có thể chuyển thành một ký tự.
C. UTF-16 với byte order được suy ra theo nội dung tệp.
D. UTF-8 theo hợp đồng của overload mặc định không có charset.
Đáp án đúng: D

Files.writeString(path, text) có hành vi mặc định nào với tệp đích?
A. Chỉ ghi khi tệp đã tồn tại và luôn nối thêm vào cuối.
B. Tạo tệp nếu thiếu và ghi đè nội dung cũ nếu tệp tồn tại.
C. Chỉ tạo tệp mới và luôn báo lỗi nếu tên tệp đã tồn tại.
D. Ghi qua tệp tạm rồi bảo đảm atomic replace ở mọi file system.
Đáp án đúng: B

Lời gọi Files.writeString(path, text, CREATE, APPEND) thường có tác dụng gì?
A. Tạo tệp nếu chưa có và nối thêm văn bản vào tệp cũ nếu đã tồn tại.
B. Chỉ ghi khi tệp chưa tồn tại, nếu có thì báo FileAlreadyExistsException.
C. Xóa toàn bộ nội dung hiện tại trước khi ghi phần văn bản mới.
D. Đọc lại tệp và tạo bản sao trước khi nối dữ liệu vào bản gốc.
Đáp án đúng: A

Path.of("logs", "app.txt") trong Java 11 biểu diễn điều gì?
A. Một Path ghép các thành phần theo file system.
B. Một URI với scheme file, không phụ thuộc file system.
C. Một File luôn có đường dẫn tuyệt đối từ thư mục gốc.
D. Một chuỗi đường dẫn được chuẩn hóa và mở tệp ngay.
Đáp án đúng: A

Khi xử lý tệp văn bản rất lớn, khác biệt quan trọng giữa Files.readString và Files.lines là gì?
A. readString trả Stream; lines luôn nạp toàn bộ dữ liệu thành String.
B. readString đọc nội dung thành String; Stream từ lines cần được đóng.
C. Cả hai trả Stream và tự đóng ngay sau khi duyệt hết phần tử.
D. Cả hai luôn tạo List<String> và đóng file descriptor sau khi tạo List.
Đáp án đúng: B

Khi tệp yêu cầu UTF-16, lựa chọn nào xác định charset khi ghi văn bản?
A. Files.writeString(path, text) và thay đổi default locale của JVM.
B. Files.write(path, text.getBytes()) rồi mặc định mọi byte là UTF-16.
C. Files.lines(path, UTF_16) sau đó ghi lại bằng Files.writeString.
D. Files.writeString(path, text, StandardCharsets.UTF_16).
Đáp án đúng: D

HttpClient.send(request, BodyHandlers.ofString()) trả về kiểu kết quả gì?
A. CompletableFuture<String> chứa nội dung phản hồi.
B. HttpResponse<String> trả về sau lời gọi đồng bộ.
C. HttpRequest mới có gắn nội dung phản hồi của server.
D. Flow.Publisher<String> phát các dòng phản hồi.
Đáp án đúng: B

HttpClient.sendAsync(request, BodyHandlers.ofString()) trả về gì?
A. HttpResponse<String> ngay khi HTTP headers được nhận.
B. Future<HttpRequest> chứa request đã được chuẩn hóa.
C. Stream<HttpResponse<String>> phát các phản hồi của từng lần redirect HTTP.
D. CompletableFuture<HttpResponse<String>> cho tác vụ bất đồng bộ.
Đáp án đúng: D

Cách nào tạo HTTP POST gửi nội dung String bằng HTTP Client chuẩn?
A. HttpRequest.newBuilder(uri).GET(BodyPublishers.ofString(body)).build().
B. HttpClient.newBuilder(uri).POST(BodyHandlers.ofString()).build().
C. HttpRequest.newBuilder(uri).POST(BodyPublishers.ofString(body)).build().
D. HttpResponse.newBuilder(uri).POST(BodyPublishers.ofString(body)).build().
Đáp án đúng: C

Khi dùng BodyHandlers.ofString(StandardCharsets.UTF_8), phần body được đọc thành gì?
A. ByteBuffer chứa các byte đã nhận nhưng chưa giải mã.
B. InputStream để caller tự đọc và đóng sau khi sử dụng.
C. String được giải mã bằng UTF-8 từ nội dung phản hồi.
D. Path trỏ tới tệp tạm mà HTTP Client đã tự tạo.
Đáp án đúng: C

Vai trò của HttpRequest.BodyPublishers.ofString(payload) là gì?
A. Cung cấp nội dung String để xuất bản làm request body.
B. Chỉ định bộ giải mã response body nhận từ phía server.
C. Tạo một HttpResponse<String> trước khi gửi HTTP request.
D. Biến HTTP headers thành nội dung body theo thứ tự khai báo.
Đáp án đúng: A

Kết quả body của BodyHandlers.ofFile(targetPath) khi send thành công là gì?
A. Một byte[] chứa toàn bộ nội dung đã được tải xuống.
B. Path đại diện cho tệp đích nơi nội dung phản hồi được ghi.
C. Một InputStream mở trên kết nối mạng tới máy chủ.
D. String biểu diễn từng dòng đã tải theo charset mặc định.
Đáp án đúng: B

HttpClient.Redirect.NORMAL có điểm khác biệt nào so với ALWAYS?
A. NORMAL không theo chuyển hướng nào, còn ALWAYS theo tất cả.
B. NORMAL chỉ theo redirect trong cùng hostname của request đầu.
C. NORMAL không theo chuyển hướng hạ cấp từ HTTPS sang HTTP.
D. NORMAL chỉ xử lý mã 301, trong khi ALWAYS xử lý cả 302.
Đáp án đúng: C

Khi cấu hình HttpClient.Version.HTTP_2 làm phiên bản ưu tiên, điều gì đúng?
A. Client bảo đảm mọi server phải trả HTTP/2 hoặc request sẽ lỗi.
B. Client tự buộc cả HTTP URL không mã hóa chuyển thành HTTPS.
C. Client dùng HTTP/2 và không bao giờ fallback sang HTTP/1.1.
D. Client ưu tiên HTTP/2 nhưng có thể dùng HTTP/1.1 khi máy chủ cần.
Đáp án đúng: D

HttpRequest.Builder.timeout(duration) tác động tới thành phần nào?
A. Thời gian tối đa để tạo bất kỳ TCP connection mới nào cho client.
B. Thời gian tối đa mà executor chờ một tác vụ được lên lịch.
C. Khoảng thời gian client giữ kết nối rảnh trong pool.
D. Giới hạn thời gian của request khi chờ phản hồi HTTP.
Đáp án đúng: D

HttpClient.Builder.connectTimeout(duration) cấu hình điều gì?
A. Giới hạn thời gian thiết lập kết nối khi cần kết nối mới.
B. Giới hạn tổng thời gian đọc mọi byte của response body.
C. Giới hạn thời gian chạy callback của CompletableFuture.
D. Giới hạn thời gian giữa hai lần retry được client tự thực hiện.
Đáp án đúng: A

Chính sách chuyển hướng mặc định của HttpClient mới tạo là gì?
A. ALWAYS, tự động theo mọi Location header hợp lệ.
B. NEVER, không tự theo redirect trừ khi cấu hình khác.
C. NORMAL, theo redirect trừ từ HTTPS xuống HTTP.
D. SAME_ORIGIN, chỉ tự theo redirect trong một origin.
Đáp án đúng: B

Khi lỗi kết nối xảy ra trong HttpClient.sendAsync, lỗi thường được phản ánh ra sao?
A. Phương thức luôn trả null thay vì một CompletableFuture.
B. HttpResponse luôn có statusCode bằng 0 để báo không kết nối.
C. Kết quả HTTP được chuyển thành chuỗi lỗi trong response body.
D. CompletableFuture hoàn thành exceptionally để caller xử lý.
Đáp án đúng: D

Với ứng dụng gửi nhiều HTTP request, cách quản lý HttpClient nào phù hợp?
A. Tái sử dụng HttpClient để tận dụng quản lý kết nối.
B. Tạo một HttpClient mới cho mọi request để tránh mọi dạng contention.
C. Tạo một HttpClient mới cho mỗi redirect do server yêu cầu.
D. Đóng và tạo lại HttpClient sau từng header để làm mới TLS state.
Đáp án đúng: A

Khi máy chủ trả HTTP 404 và việc trao đổi HTTP hoàn tất, send thường làm gì?
A. Luôn ném IOException vì mọi status 4xx đều là lỗi truyền tải.
B. Luôn gửi lại request theo HTTP/2 trước khi trả kết quả.
C. Tự chuyển response thành Optional.empty() nếu không có dữ liệu.
D. Trả về HttpResponse để caller kiểm tra statusCode và body.
Đáp án đúng: D

Khác biệt giữa HttpRequest.Builder.header và setHeader là gì?
A. header thay thế giá trị cũ, còn setHeader luôn nối thêm giá trị.
B. header chỉ thêm header cho HTTP/2, setHeader dành cho HTTP/1.1.
C. header thêm giá trị; setHeader thay giá trị cũ cùng tên.
D. header bỏ qua ký tự Unicode, setHeader tự mã hóa toàn bộ JSON.
Đáp án đúng: C

Khác biệt về cách chờ kết quả giữa HttpClient.send và sendAsync là gì?
A. send chỉ hợp lệ với HTTP/1.1, sendAsync chỉ hợp lệ với HTTP/2.
B. send chờ phản hồi đồng bộ; sendAsync trả về CompletableFuture.
C. send trả Stream<String>, sendAsync trả List<String> ngay lập tức.
D. sendAsync luôn chạy callback trên đúng thread gọi phương thức.
Đáp án đúng: B

Mục đích của BodyHandlers.discarding() là gì?
A. Giữ body trong bộ nhớ để caller có thể đọc lại nhiều lần.
B. Ghi body vào file mặc định và trả về File của file đó.
C. Bỏ nội dung body và dùng Void làm kiểu kết quả body.
D. Chỉ bỏ status code để trả trực tiếp header của response.
Đáp án đúng: C

Khi dùng BodyHandlers.ofInputStream(), caller cần chú ý điều gì?
A. Body luôn được tải hết vào heap trước khi trả InputStream.
B. Cần đọc rồi đóng InputStream để giải phóng tài nguyên.
C. InputStream tự đóng ngay khi HttpClient.send trả về.
D. InputStream chỉ có thể đọc khi server trả HTTP/2.
Đáp án đúng: B

BodyPublishers.ofFile(path) dùng để làm gì khi tạo request?
A. Chỉ định file để ghi lại phản hồi HTTP sau khi tải.
B. Tạo file rỗng rồi chuyển tên file thành chuỗi JSON.
C. Gửi nội dung file qua HTTP headers thay vì request body.
D. Cung cấp byte từ file làm request body để gửi đi.
Đáp án đúng: D

HttpClient.Builder.authenticator(authenticator) chủ yếu phục vụ cơ chế nào?
A. Cung cấp thông tin xác thực cho HTTP authentication challenge.
B. Thay SSLContext để xác minh chứng chỉ TLS của server.
C. Tự mã hóa toàn bộ request body bằng khóa đối xứng.
D. Chỉ định chính sách phân quyền của các method Java.
Đáp án đúng: A

Trong Java 11, lệnh nào chạy trực tiếp file nguồn chứa entry point hợp lệ?
A. javac Hello.java, không cần gọi launcher sau khi biên dịch.
B. java -jar Hello.java, launcher sẽ tự xây một JAR tạm.
C. java Hello.java, launcher xử lý nguồn trước khi thực thi.
D. java Hello, kể cả khi chưa có Hello.class hoặc module.
Đáp án đúng: C

Khi dùng chế độ chạy trực tiếp một source file trong Java 11, điều gì đúng?
A. Launcher luôn ghi .class vào cùng thư mục với source file.
B. Launcher chỉ dùng JVM interpreter, không gọi compiler nội bộ.
C. Mã nguồn được biên dịch trong bộ nhớ để khởi chạy.
D. Launcher tạo JAR vĩnh viễn để tái sử dụng cho lần chạy sau.
Đáp án đúng: C

Trong Java 11 source-file mode, khi file chứa nhiều top-level class, lớp nào được dùng làm entry point?
A. Lớp top-level đầu tiên trong file, với phương thức main hợp lệ.
B. Lớp có tên trùng tên file, bất kể thứ tự khai báo trong file.
C. Lớp đầu tiên chứa bất kỳ method static nào tên main.
D. Lớp public cuối cùng được compiler ghi vào class file.
Đáp án đúng: A

Lệnh java --source 11 Hello.java có vai trò gì?
A. Chuyển đổi mã nguồn sang cú pháp Java 11 và ghi đè file.
B. Chạy source-file mode với mức ngôn ngữ Java 11 được chỉ định.
C. Tạo class file Java 11 trên đĩa nhưng không chạy chương trình.
D. Chạy JAR bất kỳ có manifest ghi Main-Class là Hello.
Đáp án đúng: B

Với lệnh java Hello.java alpha beta, main(String[] args) nhận gì?
A. Hai đối số alpha và beta, không kèm tên file.
B. Ba đối số Hello.java, alpha và beta theo thứ tự lệnh.
C. Một đối số duy nhất là chuỗi "alpha beta".
D. Mảng rỗng vì source-file mode không chuyển đối số.
Đáp án đúng: A

Giới hạn quan trọng của source-file mode trong Java 11 là gì?
A. Bắt buộc sử dụng module-info.java cho mọi chương trình.
B. Mọi source file cùng package được tự động biên dịch theo phụ thuộc.
C. Chỉ chạy với source chứa đúng một class và không có class phụ.
D. Không tự biên dịch toàn bộ các source file phụ trợ như build đa file.
Đáp án đúng: D

Với BiFunction<Integer,Integer,Integer>, lambda nào dùng var hợp lệ trong Java 11?
A. (var x, var y) -> x + y
B. (var x, Integer y) -> x + y
C. (var x, y) -> x + y
D. var x, var y -> x + y
Đáp án đúng: A

Java 11 cho phép dùng var trong tham số lambda để hỗ trợ mục đích nào?
A. Chuyển lambda thành hàm không kiểm tra kiểu trong runtime.
B. Cho phép lược bỏ hoàn toàn target type của functional interface.
C. Đặt annotation trên tham số lambda với cú pháp suy luận kiểu.
D. Cho phép mỗi tham số của lambda mang kiểu động khác nhau.
Đáp án đúng: C

Khi một tham số lambda được viết với var, các tham số còn lại phải thế nào?
A. Luôn khai báo kiểu tường minh như Integer hoặc String.
B. Cũng dùng var cho toàn bộ tham số của lambda đó.
C. Không cần tên biến và chỉ được viết dấu gạch dưới.
D. Tất cả phải bỏ var để compiler tự suy luận kiểu.
Đáp án đúng: B

var trong tham số lambda Java 11 có ý nghĩa gì đối với type safety?
A. Kiểu được chọn ở runtime sau khi lambda nhận đối số đầu tiên.
B. Mỗi lần gọi có thể làm thay đổi kiểu của tham số trong bytecode.
C. Compiler vẫn suy luận và kiểm tra kiểu tĩnh theo target type của lambda.
D. Tham số được chuyển về Object và bỏ qua mọi generic constraint.
Đáp án đúng: C

Với lambda một tham số, cú pháp nào hợp lệ khi muốn dùng var?
A. var value -> value.trim()
B. (var val -> val.trim())
C. var (x) -> x.trim()
D. (var x) -> x.trim()
Đáp án đúng: D

Optional.isEmpty() trong Java 11 trả về true khi nào?
A. Optional không chứa giá trị, đối lập với isPresent().
B. Optional có phần tử nhưng phần tử là chuỗi rỗng.
C. Optional chứa collection có size bằng 0.
D. Optional được tạo bằng ofNullable với giá trị khác null.
Đáp án đúng: A

Lệnh jcmd <pid> JFR.start chủ yếu dùng để làm gì?
A. Xuất heap dump theo định dạng HPROF để tìm object leak.
B. Liệt kê tất cả class có bytecode được JVM xác minh.
C. Bắt đầu một bản ghi Java Flight Recorder trên JVM đích.
D. Biên dịch class đang chạy thành native executable tại chỗ.
Đáp án đúng: C

Lệnh jcmd <pid> JFR.dump filename=recording.jfr dùng để làm gì?
A. Xóa tất cả bản ghi JFR khỏi JVM mà không tạo tệp đầu ra.
B. Khởi động một JVM mới có cùng classpath với JVM hiện tại.
C. In mọi thread stack của JVM vào standard output.
D. Ghi dữ liệu bản ghi JFR hiện có ra tệp được chỉ định.
Đáp án đúng: D

Công cụ nào hiển thị thống kê tổng quan của tệp JFR recording.jfr?
A. javap -verbose recording.jfr
B. jfr summary recording.jfr
C. jdeps --summary recording.jfr
D. jlink --list-plugins recording.jfr
Đáp án đúng: B

Khi nâng ứng dụng lên Java 11, lệnh nào giúp tìm phụ thuộc vào JDK internal API?
A. jdeps --jdk-internals app.jar
B. jar --describe-module --release 11
C. javac --show-module-resolution app.jar
D. jcmd app.jar VM.class_hierarchy
Đáp án đúng: A

Khi biên dịch trên JDK mới nhưng đích là Java 11, cờ nào kiểm tra cả API được hỗ trợ?
A. -source 11, chỉ định ngôn ngữ nhưng mặc định giới hạn mọi API.
B. --release 11, giới hạn cả mức ngôn ngữ và API nền tảng.
C. -target 11, tự loại bỏ lời gọi API của mọi JDK mới hơn.
D. -Xlint:all, thay thế kiểm tra tương thích API và bytecode.
Đáp án đúng: B

Mục đích chính của công cụ jlink còn hữu ích trong Java hiện đại là gì?
A. Ký số mọi JAR và tải bản cập nhật runtime qua HTTPS.
B. Tạo runtime image tùy chỉnh từ tập module thực sự cần thiết.
C. Sinh mã nguồn Java cho các module thiếu trong ứng dụng.
D. Gộp các class file thành một source file chạy trực tiếp.
Đáp án đúng: B

Cải tiến TLS được chuẩn hóa trong JDK 11 hỗ trợ cơ chế nào?
A. Loại bỏ TLS 1.2 khỏi mọi kết nối HTTPS trong Java.
B. Bắt buộc mọi request HTTP Client dùng mutual TLS.
C. Có hỗ trợ giao thức TLS 1.3 trong bộ API bảo mật chuẩn.
D. Thay TLS bằng cơ chế xác thực riêng của HTTP/2.
Đáp án đúng: C

Khi chuyển ứng dụng cũ dùng javax.xml.bind sang Java 11, điều gì cần lưu ý?
A. JAXB đã được chuyển vào java.base nên không cần dependency.
B. JAXB chỉ hoạt động khi bật cờ --enable-preview trên runtime.
C. Mọi API XML đều bị loại khỏi nền tảng Java 11.
D. JAXB đã rời khỏi JDK; cần thêm dependency riêng.
Đáp án đúng: D

Java Flight Recorder trong OpenJDK 11 có đặc điểm nào đúng?
A. Chỉ tồn tại dưới dạng plugin của trình soạn thảo mã.
B. Chỉ thu thập dữ liệu bằng cách thay bytecode của mọi class.
C. Chỉ ghi sự kiện khi một ứng dụng JavaFX đang chạy.
D. Có thể ghi sự kiện JVM để phân tích hiệu năng và chẩn đoán.
Đáp án đúng: D

Nest-based access control được đưa vào Java 11 hỗ trợ trường hợp nào?
A. Mọi class trong cùng package tự được đọc private field của nhau.
B. Các class trong cùng một nest có thể truy cập private member của nhau.
C. Mọi class được cùng class loader nạp đều chia sẻ quyền private.
D. Các module có requires đều được quyền deep reflection qua nhau.
Đáp án đúng: B

Predicate.not(String::isBlank) trong Java 11 biểu diễn điều kiện nào?
A. Predicate nhận chuỗi không blank theo phép phủ định isBlank.
B. Predicate nhận chuỗi rỗng sau khi đã loại whitespace ở hai đầu bằng strip().
C. Predicate đảo ngược thứ tự ký tự của mỗi chuỗi đầu vào.
D. Predicate yêu cầu chuỗi chỉ gồm những ký tự whitespace.
Đáp án đúng: A

Collection<String> names có thể dùng names.toArray(String[]::new) để nhận gì?
A. Stream<String> trì hoãn việc đọc nội dung Collection.
B. Object[] không được kiểm tra kiểu khi được truyền cho caller.
C. String[] được tạo bằng hàm cấp phát mảng được cung cấp.
D. List<String> mới có thứ tự đảo ngược so với collection cũ.
Đáp án đúng: C
