Câu 1: JDK 18 chuẩn hóa charset mặc định theo JEP 400 thành gì?
A. US-ASCII cho tất cả các tiến trình JVM.
B. Code page hiện tại của hệ điều hành.
C. UTF-8 mặc định trên mọi hệ điều hành.
D. ISO-8859-1 cho mọi Java API văn bản.
Đáp án đúng: C

Câu 2: FileReader không truyền charset trên JDK 18 chuẩn thường đọc bằng gì?
A. UTF-8 theo charset mặc định của Java runtime hiện tại.
B. ISO-8859-1 theo chuẩn của Properties.
C. Bảng mã được lưu trong metadata của file.
D. UTF-16 theo dạng biểu diễn của String.
Đáp án đúng: A

Câu 3: InputStreamReader(InputStream) không chỉ định charset dùng gì?
A. Charset từ tên file của InputStream đầu vào.
B. Charset.defaultCharset do Java runtime sử dụng.
C. Charset của HTTP header trong mọi trường hợp.
D. Charset được InputStream gắn vào byte.
Đáp án đúng: B

Câu 4: Khi đã truyền UTF_16LE vào InputStreamReader, codec được dùng là gì?
A. Charset được tự dò từ tên file dữ liệu.
B. UTF-16LE theo đối số tạo reader.
C. UTF-8 luôn được JDK 18 ghi đè lên lựa chọn.
D. Code page hiện hành của máy triển khai JVM.
Đáp án đúng: B

Câu 5: Tệp CSV dùng Windows-1258 được nhập trên JDK 18; cách đọc phù hợp là gì?
A. Giả định file cũ đã được JVM chuyển sang UTF-8.
B. Đọc mặc định để JVM nhận dạng mã của file.
C. Đổi phần mở rộng file để kích hoạt bộ giải mã.
D. Chỉ rõ Windows-1258 khi giải mã file CSV gốc.
Đáp án đúng: D

Câu 6: String.getBytes() không có đối số trên JDK 18 chuẩn mã hóa thế nào?
A. Dùng UTF-8 theo charset mặc định của JDK 18.
B. Dùng code page Windows ngay cả khi là UTF-8.
C. Dùng UTF-16 theo biểu diễn trong Java String.
D. Dùng ISO-8859-1 do kết quả là byte array.
Đáp án đúng: A

Câu 7: new String(bytes) không truyền charset trên JDK 18 giải mã bằng gì?
A. Theo charset cố định UTF-16 của JVM.
B. Theo UTF-8 mặc định của Java runtime.
C. Theo charset được lưu ngay trong mảng byte.
D. Theo bảng mã ISO-8859-1 cho mọi đầu vào.
Đáp án đúng: B

Câu 8: Files.readString(path) không truyền charset mặc định dùng gì?
A. Charset tự nhận diện từ tên mở rộng file.
B. Code page của hệ điều hành bất kể JDK.
C. UTF-16 theo dạng nội bộ của Java String.
D. UTF-8 theo hợp đồng riêng của API Files.
Đáp án đúng: D

Câu 9: Properties.load(InputStream) dùng nguyên tắc giải mã byte nào?
A. ISO-8859-1 và quy tắc escape properties.
B. UTF-16 mặc định của các đối tượng String.
C. UTF-8 mới của các API văn bản Java 18.
D. Code page do hệ điều hành gán cho console.
Đáp án đúng: A

Câu 10: Properties.load(Reader) dựa vào thành phần nào để giải mã byte?
A. JVM bỏ qua Reader và luôn chọn UTF-8.
B. Theo charset của Reader dùng đọc nguồn.
C. Tên file properties xác định dạng mã hóa.
D. Properties tự lựa chọn mã hóa của từng khóa.
Đáp án đúng: B

Câu 11: Ký tự é khi mã hóa theo UTF-8 có độ dài bao nhiêu?
A. 1 byte như ký tự ASCII thông thường.
B. 3 byte vì Unicode phải rộng ba byte.
C. 2 byte theo biểu diễn UTF-8 của ký tự này.
D. 4 byte vì UTF-8 luôn rộng bốn byte.
Đáp án đúng: C

Câu 12: Với emoji 😀, String.length() và byte UTF-8 lần lượt là gì?
A. 2 đơn vị UTF-16 và 4 byte UTF-8 cho emoji.
B. 4 đơn vị UTF-16 và 4 byte UTF-8.
C. 2 đơn vị UTF-16 và 2 byte UTF-8.
D. 1 đơn vị UTF-16 và 4 byte UTF-8 theo code point.
Đáp án đúng: A

Câu 13: Muốn javac đọc nguồn không phải UTF-8, dùng tùy chọn nào?
A. --module-path và tên charset nguồn tương ứng.
B. --release và tên charset nguồn tương ứng.
C. -encoding chỉ rõ charset tệp nguồn cần đọc.
D. -classpath và tên charset nguồn tương ứng.
Đáp án đúng: C

Câu 14: Files.readString(path, UTF_16LE) trên JDK mới sẽ giải mã theo gì?
A. UTF-16BE vì Java bắt buộc đảo byte đầu.
B. UTF-16LE đã chỉ định trong tham số charset.
C. UTF-8 mặc định sẽ luôn thay thế tham số.
D. Charset do container thiết lập cho chương trình.
Đáp án đúng: B

Câu 15: native.encoding khác file.encoding trong JDK 18 có thể do điều gì?
A. file.encoding luôn theo tên file được mở đầu.
B. Encoding của hệ điều hành có thể khác UTF-8 mặc định của JVM.
C. Hai thuộc tính buộc phải giống nhau mọi lúc.
D. native.encoding luôn cố định bằng US-ASCII.
Đáp án đúng: B

Câu 16: Để phát hiện lỗi mã hóa sau nâng JDK, bằng chứng nào giá trị nhất?
A. So thời gian khởi động của hai phiên bản JVM.
B. So độ dài String trước khi bắt đầu xuất file.
C. Đối chiếu byte và charset của phía nhận.
D. So đuôi tên file được tạo bởi ứng dụng.
Đáp án đúng: C

Câu 17: jwebserver trong Java 18 thích hợp nhất với mục đích gì?
A. Phục vụ ứng dụng production với xác thực sẵn.
B. Tạo máy chủ HTTPS với chứng chỉ có sẵn.
C. Thực thi API nghiệp vụ có transaction SQL.
D. Chia sẻ file tĩnh cho thử nghiệm và gỡ lỗi.
Đáp án đúng: D

Câu 18: jwebserver chạy không tùy chọn sẽ lắng nghe cổng mặc định nào?
A. Cổng 8080 như máy chủ ứng dụng web.
B. Cổng 8000 theo cấu hình của công cụ.
C. Cổng 80 theo tiêu chuẩn giao thức HTTP.
D. Cổng 8443 theo chuẩn HTTPS thử nghiệm.
Đáp án đúng: B

Câu 19: Không chỉ định bind address, jwebserver thường lắng nghe ở đâu?
A. Địa chỉ IP công khai theo DNS hostname.
B. Địa chỉ multicast trong mạng nội bộ.
C. Địa chỉ loopback của chính máy chủ.
D. Tất cả giao diện mạng của máy chủ.
Đáp án đúng: C

Câu 20: Tùy chọn nào của jwebserver chỉ định thư mục được phục vụ?
A. -d hay --directory cho thư mục gốc.
B. -o hoặc --output kèm đường dẫn thư mục.
C. -b hoặc --bind-address kèm thư mục.
D. -p hoặc --port kèm đường dẫn thư mục.
Đáp án đúng: A

Câu 21: Lệnh jwebserver -b 0.0.0.0 có tác động chính nào?
A. Chỉ lắng nghe giao diện IPv4 loopback.
B. Chỉ nhận HTTP request từ cùng tiến trình.
C. Nghe trên mọi giao diện IPv4 của máy.
D. Tự kích hoạt TLS trên tất cả giao diện.
Đáp án đúng: C

Câu 22: SimpleFileServer file handler hỗ trợ trực tiếp những HTTP method nào?
A. PUT và DELETE khi quản trị file tĩnh.
B. PATCH và OPTIONS khi xử lý request.
C. GET và POST khi ghi và đọc tài nguyên.
D. GET và HEAD cho các file tĩnh.
Đáp án đúng: D

Câu 23: Khi POST tới SimpleFileServer.createFileHandler, phản hồi chuẩn là gì?
A. 201 Created và tạo tài nguyên trên đĩa.
B. 200 OK và ghi body thành một file mới.
C. 405 Method Not Allowed khi client gửi POST.
D. 301 Moved Permanently tới file được yêu cầu.
Đáp án đúng: C

Câu 24: jwebserver cung cấp loại HTTP nào qua công cụ tiêu chuẩn?
A. HTTP/3 sử dụng QUIC làm giao thức chính.
B. HTTP/1.1, không có HTTPS trực tiếp.
C. HTTP/2 trên kết nối TLS mặc định sẵn.
D. HTTPS/1.1 với chứng chỉ tự ký tích hợp.
Đáp án đúng: B

Câu 25: Một nhóm muốn cấu hình HTTPS trực tiếp qua jwebserver; điều nào đúng?
A. Chuyển cổng từ 8000 sang 443 là đủ bật TLS.
B. Không hỗ trợ HTTPS trực tiếp bằng công cụ này.
C. Bind tới địa chỉ công khai sẽ tự bật TLS.
D. Đặt log verbose sẽ tự kích hoạt HTTPS.
Đáp án đúng: B

Câu 26: Khi thư mục có index.html, GET tới URL thư mục thường cho gì?
A. Danh sách file bất kể có file index ở đó.
B. 404 vì URL phải có tên file ở cuối cùng.
C. Nội dung file index.html thuộc thư mục đó.
D. Nội dung file index ở thư mục cha gần nhất.
Đáp án đúng: C

Câu 27: GET thư mục không có index qua jwebserver thường trả về gì?
A. Một file index do server tạo tại thời điểm GET.
B. Trang đăng nhập để kiểm soát quyền người dùng.
C. 404 vì server không hỗ trợ hiển thị thư mục.
D. Liệt kê các mục con có thể truy cập qua HTTP.
Đáp án đúng: D

Câu 28: Simple Web Server xử lý file ẩn và symbolic link mặc định thế nào?
A. Không liệt kê hoặc phục vụ các mục này.
B. Chỉ phục vụ file ẩn bằng HTTP POST request.
C. Chỉ theo liên kết nếu có quyền ghi thư mục.
D. Luôn liệt kê và phục vụ như các file khác.
Đáp án đúng: A

Câu 29: jwebserver nằm trong module nào của JDK 18?
A. jdk.httpserver cung cấp HTTP server của JDK.
B. java.net.http chứa các thành phần HTTP client.
C. java.desktop chứa các thư viện giao diện.
D. java.sql chứa các thành phần giao tiếp JDBC.
Đáp án đúng: A

Câu 30: SimpleFileServer.createFileServer trả gì sau khi gọi factory?
A. Một HttpClient đang sẵn sàng gửi request.
B. HttpServer chưa chạy, cần gọi start().
C. Một ServerSocket đã bắt đầu nhận dữ liệu.
D. Một HttpServer đã tự khởi chạy lúc tạo.
Đáp án đúng: B

Câu 31: SimpleFileServer.createFileHandler(path) tạo kiểu thành phần nào?
A. Executor chuyên xử lý đa luồng truy cập.
B. Filter chỉ dùng cho việc ghi log truy cập.
C. HttpClient chỉ dùng để tải các file tĩnh.
D. Một HttpHandler phục vụ file và liệt kê nội dung thư mục.
Đáp án đúng: D

Câu 32: Đường dẫn root tương đối được truyền vào createFileServer sẽ thế nào?
A. Tự đổi root thành URL theo HTTP request.
B. Ném NumberFormatException do định dạng.
C. Tự đổi root theo thư mục home của JVM.
D. IllegalArgumentException vì root không tuyệt đối.
Đáp án đúng: D

Câu 33: Thẻ mới nào của Javadoc Java 18 dành cho ví dụ code nhiều dòng?
A. Thẻ {@snippet ...} cho ví dụ code.
B. Thẻ {@example ...} để hiển thị đoạn mã mẫu.
C. Thẻ {@execute ...} để hiển thị đoạn mã mẫu.
D. Thẻ {@sample ...} để hiển thị đoạn mã mẫu.
Đáp án đúng: A

Câu 34: Cú pháp mở snippet inline hợp lệ trong Javadoc 18 là gì?
A. Dùng {@snippet file= rồi đến mã inline.
B. Dùng /// snippet như cú pháp trong Java 18.
C. Dùng @snippet như Java annotation của class.
D. Dùng {@snippet : rồi đến nội dung mã mẫu.
Đáp án đúng: D

Câu 35: Thẻ @snippet ở Java 18 nằm trong kiểu chú thích nào?
A. Chú thích khối Java thường bắt đầu /*.
B. Chú thích Javadoc có mở đầu /**.
C. Chú thích dòng Java thông thường bắt đầu //.
D. Chú thích Markdown Java bắt đầu bằng ///.
Đáp án đúng: B

Câu 36: Thuộc tính nào trong @snippet tham chiếu tệp ví dụ ngoài?
A. file="Example.java" cùng đường dẫn file hợp lệ.
B. import="Example.java" cùng đường dẫn file hợp lệ.
C. include="Example.java" cùng đường dẫn file hợp lệ.
D. source="Example.java" cùng đường dẫn file hợp lệ.
Đáp án đúng: A

Câu 37: Thư mục nào có thể chứa file snippet ngoài gần source của package?
A. generated-resources theo thư mục class output.
B. module-patches trong các dependency runtime.
C. runtime-snippets dưới thư mục cài JDK.
D. snippet-files theo cấu trúc package source.
Đáp án đúng: D

Câu 38: Tùy chọn Javadoc nào thêm nơi tìm external snippet?
A. --source-path kèm thư mục chứa snippet.
B. --snippet-path để định vị file snippet.
C. --class-path kèm thư mục chứa snippet.
D. --module-path kèm thư mục chứa snippet.
Đáp án đúng: B

Câu 39: Cặp marker nào xác định region trong snippet ngoài?
A. @open region=... và @close region=....
B. @begin region=... và @finish region=....
C. @select region=... và @reset region=....
D. @start region=... và @end region=....
Đáp án đúng: D

Câu 40: Một @snippet yêu cầu region không tồn tại trong file sẽ ra sao?
A. Javadoc báo lỗi vì thiếu vùng tham chiếu.
B. Javadoc tìm method có tên giống region đó.
C. Javadoc luôn lấy toàn bộ file và bỏ qua lỗi.
D. Javadoc tạo một region rỗng không thông báo.
Đáp án đúng: A

Câu 41: Markup nào tô nổi bật một chuỗi con của Javadoc snippet?
A. @boldtext substring="..." trong comment markup.
B. @highlight substring="..." tại comment markup.
C. @emphasize substring="..." trong comment markup.
D. @focusline substring="..." trong comment markup.
Đáp án đúng: B

Câu 42: Markup @replace trong Javadoc snippet có tác dụng chính nào?
A. Ghi đè nội dung file snippet được tham chiếu.
B. Tự đổi mọi API deprecated thành API hiện đại.
C. Đổi phần hiển thị, giữ nguyên mã gốc.
D. Biên dịch lại mã với phần văn bản được thay.
Đáp án đúng: C

Câu 43: Markup nào của Javadoc snippet hỗ trợ tạo liên kết API?
A. @link và thuộc tính chỉ đích liên kết cần tới.
B. @import và thuộc tính chỉ đích liên kết cần tới.
C. @export và thuộc tính chỉ đích liên kết cần tới.
D. @attach và thuộc tính chỉ đích liên kết cần tới.
Đáp án đúng: A

Câu 44: Javadoc có tự biên dịch và chạy tất cả đoạn @snippet không?
A. Không; cần biên dịch và thử các ví dụ riêng.
B. Có; Javadoc tự tạo unit test cho ví dụ.
C. Có; nếu đoạn code chỉ gọi API Java 18.
D. Có; mọi snippet được javac biên dịch và chạy.
Đáp án đúng: A

Câu 45: Vì sao snippet inline không thể chứa nguyên văn chuỗi */?
A. Chuỗi này mở một vùng region mới cho snippet.
B. Chuỗi này chỉ thuộc cú pháp tài liệu Markdown.
C. Chuỗi này bị cấm trong mọi file Java source.
D. Chuỗi này kết thúc chú thích Javadoc đang mở.
Đáp án đúng: D

Câu 46: Dấu ngoặc nhọn trong snippet inline cần điều kiện nào?
A. Phải có đúng một cặp ngoặc ở mỗi dòng.
B. Cần cân bằng các dấu { và } của thẻ.
C. Javadoc luôn bỏ qua toàn bộ dấu ngoặc nhọn.
D. Không được chứa một dấu ngoặc nhọn nào.
Đáp án đúng: B

Câu 47: Snippet hybrid có inline và file ngoài không khớp sẽ thế nào?
A. Javadoc luôn ưu tiên file ngoài và bỏ inline.
B. Javadoc luôn ưu tiên inline và bỏ file ngoài.
C. Javadoc báo lỗi do hai nội dung lệch nhau.
D. Javadoc nối cả hai đoạn vào HTML kết quả.
Đáp án đúng: C

Câu 48: Dùng @snippet Java 18 nhưng tạo tài liệu bằng javadoc JDK 17 có rủi ro gì?
A. Snippet chỉ được kiểm tra khi chạy ứng dụng.
B. JDK 17 tự kích hoạt snippet nếu thấy thẻ.
C. Javadoc 17 không hiểu thẻ snippet mới.
D. JDK 17 tự biến snippet thành annotation.
Đáp án đúng: C

Câu 49: SPI Java 18 nào giúp tùy biến resolver cho InetAddress?
A. java.nio.spi.NetworkFileResolverProvider.
B. java.net.http.HttpClient.ResolverProvider.
C. javax.naming.spi.JavaHostResolverProvider.
D. java.net.spi.InetAddressResolverProvider.
Đáp án đúng: D

Câu 50: InetAddressResolverProvider.get(configuration) tạo đối tượng nào?
A. Một HttpClient thực hiện kết nối tới mạng.
B. Một InetAddressResolver cho việc tra cứu.
C. Một SocketAddress đại diện cho IP của máy.
D. Một Stream<String> chứa các hostname đã biết.
Đáp án đúng: B

Câu 51: InetAddress nhận provider resolver tùy biến thông qua cơ chế nào?
A. Class.forName quét toàn bộ mọi Java class.
B. ResourceBundle tải provider theo locale.
C. ServiceLoader với system class loader.
D. java.util.logging tìm theo tên provider.
Đáp án đúng: C

Câu 52: Khi có nhiều resolver provider, Java 18 dùng provider nào?
A. Provider có tên dài nhất trong danh sách.
B. Tất cả provider được ghép thành một resolver.
C. Provider đầu tiên theo thứ tự do JVM chọn.
D. Báo lỗi khởi động JVM vì không thể có nhiều.
Đáp án đúng: C

Câu 53: Không có custom resolver provider, InetAddress dùng gì?
A. Bộ phân giải built-in của JDK đang chạy.
B. Bộ phân giải đọc từ cấu hình Javadoc.
C. Bộ phân giải do ServiceLoader tự sáng tạo.
D. Bộ nhớ cache nội bộ của Java HttpClient.
Đáp án đúng: A

Câu 54: Vòng đời resolver hệ thống của InetAddress được mô tả thế nào?
A. Một provider mới được tạo ở mỗi lần getByName.
B. Mỗi đối tượng InetAddress mang resolver riêng.
C. Mỗi thread khởi động riêng một resolver mới.
D. Một resolver dùng chung toàn JVM khi lookup.
Đáp án đúng: D

Câu 55: InetAddressResolver.lookupByName trả về dữ liệu dạng nào?
A. Optional<URI> theo host và lookup policy.
B. SocketChannel theo host và lookup policy.
C. Stream<InetAddress> theo LookupPolicy.
D. List<String> theo host và lookup policy.
Đáp án đúng: C

Câu 56: Phương thức nào phân giải ngược byte IP sang tên host?
A. lookupByAddress(byte[]) trả chuỗi hostname.
B. resolveByPort(int) trả về String tên host.
C. lookupByName(String) trả về String tên host.
D. reverseLookup(URI) trả về String tên host.
Đáp án đúng: A

Câu 57: JEP 416 của Java 18 thay đổi gì về core reflection?
A. Buộc mọi phương thức phản xạ dùng JShell.
B. Thay API reflection thành ngôn ngữ truy vấn.
C. Loại bỏ hoàn toàn các lớp Method và Field.
D. Reflection lõi được xây trên MethodHandle.
Đáp án đúng: D

Câu 58: Method.invoke gặp exception do method đích ném, thường báo gì?
A. ClassNotFoundException chứa lỗi của đích.
B. NumberFormatException chứa lỗi của đích.
C. InvocationTargetException bọc lỗi của đích.
D. WrongMethodTypeException chứa lỗi của đích.
Đáp án đúng: C

Câu 59: Reflection Java 18 có tự bỏ giới hạn private của JPMS không?
A. Có, mọi field private đều được truy cập.
B. Có, nếu method mang annotation bất kỳ.
C. Không, quy tắc mở package vẫn được áp dụng.
D. Có, MethodHandle bỏ qua mọi ranh giới module.
Đáp án đúng: C

Câu 60: MethodHandle.invokeExact yêu cầu kiểu tại lời gọi thế nào?
A. Tự ép mọi kiểu số giống như Method.invoke.
B. Luôn nhận null kể cả tham số nguyên thủy.
C. Không cần kiểm tra kiểu trả về tại call site.
D. Khớp chính xác với method type của handle.
Đáp án đúng: D

Câu 61: MethodHandle.asType phục vụ mục đích nào sau đây?
A. Tự biên dịch Java source chưa có class file.
B. Mở quyền private của tất cả module trong JVM.
C. Tự cấp thread riêng cho mọi lần gọi handle.
D. Thích nghi handle qua chuyển kiểu hợp lệ.
Đáp án đúng: D

Câu 62: Framework muốn deep reflection vào package của named module khác cần gì?
A. Package được opens thích hợp theo quy tắc JPMS.
B. Module chỉ cần exports package khác không liên quan.
C. Chỉ cần đổi kiểu trả về của Method.invoke.
D. Chỉ cần runtime mới hơn Java 17 một phiên bản.
Đáp án đúng: A

Câu 63: Vì sao cần benchmark reflection sau khi nâng lên JDK 18?
A. Phụ thuộc metadata và cách runtime JDK xử lý.
B. Mọi Method.invoke sẽ nhanh hơn đúng một tỷ lệ.
C. Mọi hợp đồng API của reflection đã thay đổi.
D. Mọi MethodHandle đều chậm hơn reflection cũ.
Đáp án đúng: A

Câu 64: Với --release 17 có thể dùng trực tiếp API Resolver SPI thêm ở Java 18 không?
A. Không, vì SPI này mãi là API preview.
B. Không, API chỉ có từ Java 18.
C. Có, chỉ cần thêm module java.net.http.
D. Có, javac JDK mới luôn mở toàn bộ API.
Đáp án đúng: B
