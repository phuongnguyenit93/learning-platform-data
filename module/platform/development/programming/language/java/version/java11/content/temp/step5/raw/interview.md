Bạn sẽ xác định một API xuất hiện từ Java 11 còn được hỗ trợ trong JDK hiện đại bằng cách nào?
Bạn phân biệt việc một API được giới thiệu ở Java 11 với việc nó vẫn nên được sử dụng trong code mới theo tiêu chí nào?
Bạn sẽ tổ chức bài ôn Java 11 theo các khả năng còn hữu ích thay vì học thuộc mọi thay đổi lịch sử như thế nào?
Bạn mô tả sự khác nhau giữa source compatibility, binary compatibility và behavioral compatibility khi nâng JDK như thế nào?
Bạn sẽ kiểm tra class file version của một thư viện biên dịch cho Java 11 theo cách nào?
Bạn phân biệt cấu hình javac --release 11 với chỉ dùng -source 11 và -target 11 về bảo đảm tương thích như thế nào?
Bạn phân tích vì sao biên dịch bằng JDK mới với --release 11 hạn chế việc gọi nhầm API được thêm sau Java 11 ra sao?
Bạn sẽ kiểm tra một API mà chương trình đang gọi thực sự có trong public Java 11 platform API bằng cách nào?
Bạn mô tả quy trình thử nghiệm chương trình Java 11 trên JDK mới mà không phụ thuộc một JVM cũ để chạy production như thế nào?
Bạn sẽ chọn toolchain cho CI khi phải hỗ trợ cả Java 11 và một phiên bản Java mới hơn theo tiêu chí nào?
Bạn phân biệt LTS release với bảo đảm mã Java cũ hoạt động hoàn toàn không thay đổi về hành vi runtime ra sao?
Bạn sẽ xác định khi nào cần test một thư viện trên nhiều JDK vendors dù Java specification version giống nhau như thế nào?
Bạn phân tích vì sao phụ thuộc một JVM internal API không phải lựa chọn ổn định khi nâng từ Java 11 lên JDK mới ra sao?
Bạn sẽ đánh giá một cách sử dụng API còn biên dịch nhưng không còn được khuyến khích trong ứng dụng mới như thế nào?
Bạn mô tả phương pháp đối chiếu Java API documentation của phiên bản đích trước khi sử dụng overload mới như thế nào?
Bạn sẽ xác định tính tương thích của dependencies thông qua module path, classpath và JAR metadata như thế nào?
Bạn phân biệt mã Java 11 không dùng preview feature với mã dựa vào preview feature theo khả năng duy trì lâu dài ra sao?
Bạn sẽ thiết kế test hồi quy cho xử lý chuỗi và tệp khi chuyển runtime từ Java 11 lên phiên bản mới ra sao?
Bạn phân tích vì sao thay đổi Unicode version giữa các JDK có thể ảnh hưởng cách phân loại khoảng trắng hoặc ký tự như thế nào?
Bạn sẽ kiểm tra sự khác biệt của TLS defaults khi nâng runtime dù HTTP Client application code không đổi ra sao?
Bạn sẽ lựa chọn giữa API Java chuẩn và thư viện bên ngoài theo yêu cầu bảo trì, hiệu năng và hỗ trợ JDK ra sao?
Bạn mô tả cách giới hạn phạm vi ôn tập vào các API còn phổ biến và bảo đảm từ specification thay vì implementation detail như thế nào?
Bạn sẽ thiết lập một bộ smoke tests chung cho Java 11 source compatibility và runtime hiện đại theo cách nào?
Bạn giải thích String.isBlank được giới thiệu trong Java 11 kiểm tra chuỗi theo quy tắc nào?
Bạn phân biệt String.isBlank với String.isEmpty khi chuỗi chỉ chứa các ký tự khoảng trắng như thế nào?
Bạn sẽ dùng isBlank để kiểm tra một trường văn bản trước khi lưu nhưng vẫn phân biệt input null ra sao?
Bạn mô tả String.strip loại bỏ khoảng trắng Unicode theo Character.isWhitespace khác trim ở đặc điểm nào?
Bạn phân biệt strip, stripLeading và stripTrailing khi cần giữ một phía khoảng trắng theo nghiệp vụ như thế nào?
Bạn sẽ giải thích tại sao strip không mặc nhiên loại bỏ mọi ký tự hiển thị giống khoảng trắng trong Unicode như thế nào?
Bạn sẽ chọn strip hay trim theo chính sách chuẩn hóa dữ liệu và yêu cầu hỗ trợ ký tự quốc tế ra sao?
Bạn phân tích vì sao không nên dùng strip bừa bãi với mật khẩu, chữ ký hoặc văn bản cần giữ nguyên khoảng trắng như thế nào?
Bạn sẽ thiết kế test cho strip với tab, newline và các Unicode whitespace code points theo phương pháp nào?
Bạn mô tả String.lines tạo Stream<String> từ các dòng trong một chuỗi như thế nào?
Bạn phân biệt String.lines với split theo regex khi xử lý ký tự kết thúc dòng CR, LF và CRLF ra sao?
Bạn sẽ xử lý String.lines trên chuỗi rỗng hoặc có line terminator ở cuối theo contract nào?
Bạn phân tích vì sao String.lines là pipeline lazy khác với việc tách tất cả dòng thành mảng trước khi xử lý ra sao?
Bạn sẽ dùng String.lines kết hợp filter và map để loại dòng trống rồi phân tích file config như thế nào?
Bạn mô tả String.repeat nhận số lần lặp và tạo chuỗi mới theo quy tắc nào?
Bạn sẽ sử dụng String.repeat để xây output test hoặc định dạng văn bản mà không lặp vòng for như thế nào?
Bạn phân tích rủi ro dùng repeat với số lần quá lớn khiến bộ nhớ tăng mạnh ra sao?
Bạn sẽ xác định cách repeat xử lý số lần âm, bằng không và bằng một thông qua hợp đồng API như thế nào?
Bạn sẽ kết hợp isBlank, strip và lines để làm sạch dữ liệu nhập dạng nhiều dòng mà không mất thông tin quan trọng ra sao?
Bạn phân biệt xử lý chuỗi UTF-16 code units với Unicode code points khi cần đếm ký tự sau strip như thế nào?
Bạn sẽ dùng codePoints khi xử lý ký tự ngoài BMP thay vì giả định mỗi Java char là một ký tự ra sao?
Bạn phân tích vì sao normalize Unicode có thể cần thiết ngoài isBlank và strip trong so sánh định danh như thế nào?
Bạn sẽ thiết kế API chuẩn hóa chuỗi vẫn giữ original value để phục vụ audit hoặc thông báo lỗi ra sao?
Bạn mô tả cách String.lines kết hợp takeWhile hoặc limit cho các xử lý dừng sớm trên JDK phù hợp ra sao?
Bạn sẽ kiểm tra kết quả khác biệt khi một chuỗi chứa non-breaking space hoặc ký tự zero-width trong input validation như thế nào?
Bạn sẽ dùng unit tests và property-based tests để bảo đảm hàm chuẩn hóa văn bản không thay đổi nội dung ngoài quy định ra sao?
Bạn phân tích khi nào String.repeat không phù hợp để tạo payload benchmark hoặc dữ liệu thử nghiệm quá lớn như thế nào?
Bạn giải thích Files.readString được bổ sung ở Java 11 giúp đọc văn bản từ Path theo cách nào?
Bạn phân biệt Files.readString với Files.lines về lượng dữ liệu giữ trong bộ nhớ và quản lý resource như thế nào?
Bạn sẽ sử dụng Files.readString mặc định UTF-8 khi file được tạo ở môi trường đa hệ điều hành ra sao?
Bạn mô tả overload Files.readString nhận Charset hỗ trợ file có encoding khác UTF-8 như thế nào?
Bạn sẽ xử lý lỗi malformed input khi file chứa byte sequence không hợp lệ với Charset đã chọn ra sao?
Bạn phân tích vì sao không nên đọc file log hàng gigabyte bằng Files.readString trong một service có heap nhỏ ra sao?
Bạn sẽ dùng Files.writeString để tạo file văn bản nhỏ với nội dung UTF-8 theo yêu cầu nào?
Bạn phân biệt Files.writeString với Files.write khi nội dung nguồn là String thay vì byte array ra sao?
Bạn sẽ chọn StandardOpenOption.CREATE_NEW khi không được phép ghi đè file đầu ra theo quy tắc nào?
Bạn phân biệt TRUNCATE_EXISTING với APPEND khi dùng Files.writeString để cập nhật nội dung ra sao?
Bạn sẽ xác định hành vi mặc định của Files.writeString khi file đã tồn tại và khi file chưa tồn tại như thế nào?
Bạn phân tích vì sao ghi trực tiếp bằng Files.writeString không tự đảm bảo atomic replacement nếu ứng dụng dừng giữa chừng ra sao?
Bạn sẽ thiết kế quy trình ghi tệp tạm và Files.move với ATOMIC_MOVE nếu filesystem hỗ trợ theo chiến lược nào?
Bạn mô tả cách Path.of(String, String...) tạo đường dẫn theo filesystem mặc định như thế nào?
Bạn phân biệt Path.of(URI) với Path.of(String) khi nguồn đường dẫn đến từ URI có scheme cụ thể ra sao?
Bạn sẽ kết hợp Path.resolve và Path.normalize để dựng đường dẫn dưới một thư mục gốc theo cách nào?
Bạn phân tích vì sao Path.normalize không thay thế kiểm tra quyền truy cập hoặc chống symlink traversal ra sao?
Bạn sẽ dùng Files.exists, Files.isRegularFile và kiểm tra permission trước khi đọc một file theo chính sách nào?
Bạn mô tả sự khác nhau giữa Files.readString và Files.readAllLines về kiểu kết quả cũng như mức dùng bộ nhớ ra sao?
Bạn sẽ dùng try-with-resources cho Files.lines nhưng không cần đóng một String đã nhận từ Files.readString như thế nào?
Bạn sẽ chọn readString, lines hay buffered reader khi file lớn và cần xử lý tuần tự theo tiêu chí nào?
Bạn phân tích vì sao chèn nội dung từ người dùng vào đường dẫn mà không xác thực có thể gây path traversal ra sao?
Bạn sẽ kiểm tra line endings và charset khi chuyển file văn bản giữa Windows và Linux như thế nào?
Bạn sẽ bảo đảm việc ghi config hoặc report giữ nguyên lỗi IOException thay vì nuốt lỗi rồi trả chuỗi rỗng ra sao?
Bạn mô tả cách unit test dùng temporary directory kiểm chứng readString và writeString mà không phụ thuộc đường dẫn cố định ra sao?
Bạn sẽ kiểm thử round-trip các ký tự tiếng Việt và Unicode ngoài BMP qua Files.writeString rồi Files.readString như thế nào?
Bạn phân tích khi nào cần explicit fsync hoặc atomic save policy thay vì chỉ gọi writeString rồi coi dữ liệu đã bền ra sao?
Bạn giải thích java.net.http.HttpClient được chuẩn hóa trong Java 11 đóng vai trò gì đối với HTTP requests như thế nào?
Bạn phân biệt HttpClient, HttpRequest và HttpResponse theo trách nhiệm tạo client, khai báo request và đọc kết quả ra sao?
Bạn sẽ tạo HttpClient bằng HttpClient.newHttpClient hoặc HttpClient.newBuilder theo nhu cầu cấu hình nào?
Bạn mô tả lợi ích của việc tái sử dụng HttpClient cho nhiều requests thay vì tạo mới cho mỗi lời gọi như thế nào?
Bạn sẽ cấu hình HttpClient.Builder.connectTimeout để giới hạn giai đoạn thiết lập kết nối ra sao?
Bạn phân biệt connectTimeout của client với timeout trên HttpRequest theo phạm vi áp dụng nào?
Bạn sẽ thiết kế HttpRequest bằng URI.create và HttpRequest.newBuilder mà kiểm tra URI hợp lệ như thế nào?
Bạn mô tả HttpRequest.Builder.GET và POST khác nhau về khai báo method và request body như thế nào?
Bạn sẽ sử dụng HttpRequest.BodyPublishers.ofString để gửi JSON và đặt Content-Type phù hợp ra sao?
Bạn phân biệt BodyPublishers.ofByteArray với ofFile khi payload ở trong bộ nhớ hoặc trên đĩa như thế nào?
Bạn sẽ dùng BodyPublishers.noBody cho request không có body theo mục đích nào?
Bạn phân tích vì sao request body của một POST không mặc nhiên là idempotent và cần thận trọng với retry ra sao?
Bạn sẽ chọn BodyPublishers.ofInputStream khi dữ liệu lớn nhưng kiểm tra khả năng cung cấp lại stream như thế nào?
Bạn mô tả sự liên quan giữa BodyPublisher và reactive Flow Publisher trong truyền dữ liệu request ra sao?
Bạn sẽ cấu hình header Authorization an toàn mà không vô tình ghi giá trị đó vào application log như thế nào?
Bạn phân biệt Accept và Content-Type trên HttpRequest khi client gửi hoặc mong đợi JSON như thế nào?
Bạn sẽ sử dụng HttpRequest.Builder.header và setHeader theo quy tắc thêm hoặc thay giá trị header ra sao?
Bạn phân tích vì sao không được tin vào mọi header do user input cung cấp khi xây một HTTP gateway như thế nào?
Bạn sẽ xử lý query parameters trong URI theo quy tắc encoding thay vì nối chuỗi tùy ý như thế nào?
Bạn mô tả cách thiết lập HttpClient.Version.HTTP_2 để yêu cầu ưu tiên HTTP/2 mà vẫn kiểm tra version thực tế ra sao?
Bạn sẽ phân biệt HTTP/2 preference và cam kết server thực sự chấp nhận kết nối HTTP/2 như thế nào?
Bạn phân tích vì sao cấu hình followRedirects có thể ảnh hưởng việc gửi lại thông tin xác thực khi đổi host ra sao?
Bạn sẽ chọn Redirect.NORMAL, ALWAYS hoặc NEVER theo chính sách endpoint và bảo mật nào?
Bạn sẽ thiết kế request-level timeout theo SLA của một API mà không dùng một giá trị timeout toàn hệ thống ra sao?
Bạn mô tả cách chọn reusable HttpClient instance trong service có lượng request cao nhưng giới hạn tài nguyên hợp lý như thế nào?
Bạn sẽ kiểm tra HTTPS URI và hostname trước khi tạo request chứa thông tin nhạy cảm theo quy tắc nào?
Bạn phân tích vì sao HttpClient không phải giải pháp thay thế cho việc giới hạn số request đồng thời ở application layer ra sao?
Bạn giải thích HttpClient.send thực hiện request đồng bộ và trả HttpResponse theo cách nào?
Bạn phân biệt HttpClient.send với sendAsync về blocking caller và khả năng tiếp tục xử lý bất đồng bộ ra sao?
Bạn sẽ dùng HttpResponse.BodyHandlers.ofString để nhận nội dung text và kiểm tra status code như thế nào?
Bạn phân biệt BodyHandlers.ofString với ofByteArray khi phản hồi có nội dung nhị phân ra sao?
Bạn sẽ dùng BodyHandlers.ofFile để tải payload lớn xuống file mà không giữ toàn bộ dữ liệu trong heap như thế nào?
Bạn mô tả trách nhiệm quản lý InputStream khi nhận response qua BodyHandlers.ofInputStream như thế nào?
Bạn sẽ xử lý đóng InputStream khi đọc response lỗi hoặc hủy xử lý giữa chừng ra sao?
Bạn phân tích vì sao HttpResponse.statusCode có thể là 4xx hoặc 5xx mà send không ném exception ứng dụng tự động ra sao?
Bạn sẽ thiết kế status handling phân biệt thành công, lỗi client, lỗi server và retryable failure như thế nào?
Bạn phân biệt HttpResponse.headers với request headers theo nguồn dữ liệu nào?
Bạn sẽ sử dụng HttpHeaders.firstValue để đọc header tùy chọn mà không gây lỗi khi header thiếu ra sao?
Bạn mô tả HttpResponse.uri giúp kiểm tra URI phản hồi cuối cùng sau redirect như thế nào?
Bạn sẽ kiểm tra HttpResponse.version để ghi nhận phiên bản HTTP được thương lượng trên kết nối ra sao?
Bạn phân tích vì sao không nên đọc toàn bộ HTML hoặc JSON phản hồi không giới hạn bằng ofString khi server không tin cậy ra sao?
Bạn sẽ thiết kế giới hạn response size và timeout khi tải nội dung từ dịch vụ bên ngoài như thế nào?
Bạn mô tả CompletionStage/CompletableFuture nhận từ sendAsync phối hợp các bước tiếp theo ra sao?
Bạn sẽ dùng thenApply hoặc thenCompose sau sendAsync theo quan hệ đồng bộ/bất đồng bộ của phép xử lý như thế nào?
Bạn phân biệt CompletableFuture.exceptionally với handle khi xử lý thất bại và kết quả thành công ra sao?
Bạn sẽ quan sát CompletionException và nguyên nhân gốc khi một request bất đồng bộ thất bại như thế nào?
Bạn phân tích vì sao gọi join ngay sau sendAsync có thể làm mất lợi thế non-blocking tại call site ra sao?
Bạn sẽ triển khai nhiều requests độc lập bằng CompletableFuture.allOf nhưng vẫn giới hạn concurrency theo cách nào?
Bạn phân biệt hủy CompletableFuture với bảo đảm hủy hoàn toàn network I/O trong mọi phiên bản JDK như thế nào?
Bạn sẽ thiết kế retry có backoff và idempotency policy quanh sendAsync thay vì retry vô hạn như thế nào?
Bạn mô tả cách đo latency và gắn correlation ID vào HTTP request mà không log credentials ra sao?
Bạn sẽ kiểm tra response content type trước khi parse JSON để giảm lỗi dữ liệu đầu vào như thế nào?
Bạn phân tích rủi ro dùng default executor không kiểm soát khi callbacks thực hiện blocking business work lớn ra sao?
Bạn sẽ lựa chọn custom Executor qua HttpClient.Builder.executor hoặc tách callback computation sang executor riêng theo tiêu chí nào?
Bạn sẽ kiểm thử timeout, exception và non-2xx response bằng mock HTTP server thay vì phụ thuộc external network như thế nào?
Bạn giải thích HTTP/2 multiplexing thay đổi việc sử dụng một kết nối TCP so với HTTP/1.1 như thế nào?
Bạn sẽ xác minh HttpResponse.version để biết một request thật sự đi qua HTTP/2 hay HTTP/1.1 ra sao?
Bạn mô tả HTTP/2 server negotiation phụ thuộc server, proxy và TLS setup theo điều kiện nào?
Bạn sẽ đánh giá vấn đề head-of-line blocking còn tồn tại ở tầng nào khi dùng HTTP/2 trên TCP như thế nào?
Bạn phân tích vì sao không nên kết luận request nhanh hơn chỉ vì chọn HttpClient.Version.HTTP_2 ra sao?
Bạn sẽ đặt SSLContext vào HttpClient.Builder khi ứng dụng cần trust material riêng theo cách nào?
Bạn phân biệt SSLContext dùng truststore với key material khi client cần TLS xác thực máy chủ hoặc mTLS ra sao?
Bạn sẽ cấu hình ProxySelector cho HttpClient khi môi trường doanh nghiệp yêu cầu đi qua outbound proxy như thế nào?
Bạn mô tả Authenticator hỗ trợ một số cơ chế xác thực ở client và giới hạn bảo mật của thông tin xác thực như thế nào?
Bạn sẽ bảo đảm hostname verification không bị vô hiệu hóa khi xử lý lỗi chứng chỉ HTTPS theo nguyên tắc nào?
Bạn phân tích vì sao trust tất cả certificates để sửa nhanh lỗi TLS là phương án không an toàn ra sao?
Bạn sẽ kiểm thử handshake TLS 1.3 trên JDK hỗ trợ cùng server thực tế và xử lý fallback theo chính sách nào?
Bạn phân biệt TLS 1.3 support trong Java 11 với việc mọi máy chủ đều thương lượng TLS 1.3 ra sao?
Bạn sẽ kiểm tra chứng chỉ hết hạn, chuỗi tin cậy và tên miền khi HTTPS request thất bại như thế nào?
Bạn mô tả ALPN có vai trò gì khi chọn HTTP/2 qua một kết nối TLS như thế nào?
Bạn sẽ kiểm tra proxy và TLS interception ảnh hưởng certificate validation của HttpClient ra sao?
Bạn phân tích vì sao client certificate rotation phải được kiểm tra cùng lifecycle của HttpClient và SSLContext ra sao?
Bạn sẽ sử dụng java.net.http.WebSocket.Builder để tạo một WebSocket client từ Java HTTP Client API như thế nào?
Bạn phân biệt WebSocket.Listener với HttpResponse.BodyHandler trong cách nhận dữ liệu ra sao?
Bạn sẽ xử lý fragmented WebSocket text messages trong listener mà không giả định mỗi callback là trọn một message như thế nào?
Bạn mô tả WebSocket.request(n) điều khiển số callbacks nhận tiếp theo theo cơ chế demand như thế nào?
Bạn sẽ quản lý backpressure khi WebSocket producer nhanh hơn consumer xử lý messages ra sao?
Bạn phân tích vì sao WebSocket client không đồng nghĩa JDK cung cấp một WebSocket server API tương ứng như thế nào?
Bạn sẽ xử lý WebSocket.sendClose và lỗi kết nối để giải phóng resources theo contract nào?
Bạn sẽ kiểm thử reconnect có giới hạn và tránh duplicate business operations khi WebSocket mất kết nối như thế nào?
Bạn sẽ xác định khi nào dùng HTTP request/response thông thường thay vì WebSocket streaming theo use case nào?
Bạn phân tích vì sao việc ghép authentication tokens vào WebSocket URL có nguy cơ lộ thông tin trong logs ra sao?
Bạn giải thích cơ chế single-file source-code execution được giới thiệu từ Java 11 khi gọi java với một file .java như thế nào?
Bạn phân biệt chạy java Hello.java với biên dịch javac rồi chạy java Hello về mục đích và artifacts như thế nào?
Bạn sẽ lựa chọn source-file mode cho script thử nghiệm nhỏ thay vì chương trình triển khai lâu dài theo tiêu chí nào?
Bạn mô tả cơ chế chọn entry point khi file nguồn chứa nhiều khai báo top-level classes theo Java 11 như thế nào?
Bạn sẽ dùng java --source 11 khi cần chỉ định mức ngôn ngữ trong source-file execution theo cách nào?
Bạn phân biệt extension .java và source-file mode với chạy một tên class đã biên dịch trên classpath ra sao?
Bạn sẽ thiết kế script dùng source-file execution mà vẫn chỉ định external dependencies qua classpath khi cần như thế nào?
Bạn phân tích vì sao chạy trực tiếp file nguồn không làm mọi thư viện Maven/Gradle tự động có trên classpath ra sao?
Bạn sẽ xác định những hạn chế khi một single-file program cần nhiều source files hoặc tổ chức thành modules như thế nào?
Bạn mô tả khả năng chạy file script có shebang trên hệ Unix theo điều kiện launcher và quyền thực thi nào?
Bạn sẽ phân biệt shebang xử lý bởi OS shell với logic source launcher trong JDK như thế nào?
Bạn sẽ kiểm tra script source-file mode được chạy bằng đúng JDK đã chọn thay vì Java nằm trước trong PATH ra sao?
Bạn phân tích vì sao source-file mode vẫn thực hiện compilation trước khi chạy và có thể phát sinh compiler diagnostics ra sao?
Bạn sẽ xử lý compiler error trong source-file mode và phân biệt nó với runtime exception như thế nào?
Bạn sẽ kiểm tra exit code của một script Java chạy trực tiếp khi tích hợp trong CI ra sao?
Bạn mô tả cách truyền command-line arguments vào main của chương trình source-file mode như thế nào?
Bạn sẽ bảo đảm script không dựa vào working directory bất định khi đọc file qua Path.of như thế nào?
Bạn phân tích vì sao source-file execution phù hợp smoke test nhanh nhưng không thay thế artifact versioning như thế nào?
Bạn sẽ quyết định thời điểm chuyển một script Java sang project có build tool, tests và dependency lock theo dấu hiệu nào?
Bạn sẽ tránh nhúng secrets trong source-file script được lưu chung với repository theo cách nào?
Bạn mô tả cách kiểm tra source-file mode tiếp tục hoạt động sau khi nâng JDK bằng regression tests như thế nào?
Bạn sẽ so sánh khả năng debug script chạy trực tiếp với chương trình biên dịch theo đường build chính thức như thế nào?
Bạn sẽ phân biệt khả năng chạy source-file mode trên Java 11 với các tiện ích thêm ở JDK mới hơn khi đọc tài liệu như thế nào?
Bạn giải thích vì sao Java 11 cho phép dùng var trong khai báo tham số lambda mà vẫn giữ target typing như thế nào?
Bạn phân biệt tham số lambda viết var với tham số được compiler suy luận kiểu hoàn toàn theo cú pháp nào?
Bạn sẽ sử dụng var cho các tham số lambda khi muốn đặt annotation lên tham số theo tình huống nào?
Bạn mô tả ràng buộc tất cả tham số của cùng lambda phải dùng kiểu khai báo nhất quán khi chọn var như thế nào?
Bạn sẽ xác định vì sao không được trộn var với kiểu tường minh hoặc tham số không khai báo kiểu trong một lambda ra sao?
Bạn phân tích tại sao var trong lambda không thay đổi functional interface type mà lambda được gán vào như thế nào?
Bạn sẽ kiểm tra lỗi compiler khi dùng var cho lambda nhưng thiếu target functional interface như thế nào?
Bạn sẽ lựa chọn var hay explicit parameter types cho lambda để cân bằng readability và annotation needs ra sao?
Bạn mô tả giới hạn sử dụng var trong Java 11 và vì sao nó không thay thế kiểu trả về của method như thế nào?
Bạn sẽ phân biệt Java 10 local-variable type inference với khả năng dùng var cho tham số lambda được bổ sung ở Java 11 ra sao?
Bạn phân tích vì sao đặt annotation lên var lambda parameter không có nghĩa mọi annotation đều hợp lệ với target đó như thế nào?
Bạn sẽ kiểm tra annotation retention và target khi cần framework xử lý annotation từ lambda parameters như thế nào?
Bạn sẽ dùng Predicate.not trong Java 11 để viết filter với method reference bị phủ định như thế nào?
Bạn phân biệt Predicate.not(methodReference) với viết lambda phủ định trực tiếp theo readability và null handling ra sao?
Bạn sẽ thiết kế filter dùng Predicate.not(String::isBlank) nhưng xử lý null input trước như thế nào?
Bạn mô tả Optional.isEmpty được bổ sung trong Java 11 giúp thể hiện logic vắng giá trị như thế nào?
Bạn sẽ phân biệt Optional.isEmpty với isPresent ở hai nhánh điều kiện và cách tránh lạm dụng Optional.get ra sao?
Bạn sẽ sử dụng Collection.toArray(String[]::new) trong Java 11 để tạo mảng đúng kiểu từ danh sách như thế nào?
Bạn mô tả overload Collection.toArray(IntFunction<T[]>) phối hợp array constructor reference theo type inference ra sao?
Bạn phân tích vì sao các API nhỏ như Predicate.not hoặc Optional.isEmpty nên được chọn theo ý nghĩa chứ không chỉ vì cú pháp ngắn ra sao?
Bạn sẽ dùng Pattern.asMatchPredicate được hỗ trợ từ Java 11 khi cần kiểm tra toàn bộ chuỗi khớp regex như thế nào?
Bạn phân biệt Pattern.asMatchPredicate với Pattern.asPredicate về việc kiểm tra toàn chuỗi hay tìm đoạn khớp ra sao?
Bạn sẽ kiểm thử regex predicate trên input rỗng và ký tự Unicode để bảo đảm đúng business rule như thế nào?
Bạn sẽ quyết định khi nào dùng Collection.toArray(IntFunction) và khi nào giữ List thay vì tạo array trung gian ra sao?
Bạn mô tả cách kiểm tra một lambda có side effects khi được dùng trong Stream song song trên Java 11 hoặc mới hơn ra sao?
Bạn sẽ đánh giá code dùng var và các functional APIs theo mức hỗ trợ của --release 11 trong build như thế nào?
Bạn giải thích Java Flight Recorder (JFR) trong hệ sinh thái JDK 11 và hiện đại giúp thu thập JVM events như thế nào?
Bạn sẽ khởi động một JFR recording bằng -XX:StartFlightRecording theo thời gian và kích thước cần quan sát ra sao?
Bạn mô tả jcmd JFR.start có thể bật recording cho một JVM đang chạy theo điều kiện quyền truy cập nào?
Bạn sẽ sử dụng jcmd JFR.check để kiểm tra recordings còn hoạt động như thế nào?
Bạn phân biệt jcmd JFR.dump với JFR.stop trong việc xuất dữ liệu hoặc kết thúc recording như thế nào?
Bạn sẽ dùng công cụ jfr summary để xem những event types chiếm ưu thế trong file recording ra sao?
Bạn sẽ lọc dữ liệu bằng jfr print theo event name để tìm nguyên nhân một lần spike latency như thế nào?
Bạn mô tả CPU sampling events và allocation events trong JFR phù hợp với những loại performance investigation nào?
Bạn sẽ phân tích vì sao thời gian chờ lock hoặc thread park có thể tăng latency mà CPU usage vẫn thấp như thế nào?
Bạn sẽ dùng JFR để phân biệt GC pause với ứng dụng bị blocked trên monitor theo timeline như thế nào?
Bạn phân tích vì sao JFR sampling không thể thay thế một benchmark được thiết kế chuẩn như thế nào?
Bạn sẽ giới hạn duration, maxage và maxsize khi thu JFR trên production theo chính sách nào?
Bạn sẽ bảo vệ recording có thể chứa method arguments hoặc thông tin nhạy cảm trước khi chia sẻ với bên ngoài ra sao?
Bạn mô tả sự khác nhau giữa JFR default và profile settings về mức thu thập và chi phí tài nguyên như thế nào?
Bạn sẽ kiểm tra khả năng hỗ trợ và cú pháp của JFR event settings trên bản JDK đang chạy như thế nào?
Bạn sẽ kết hợp jfr print và JDK Mission Control để điều tra allocation hot paths như thế nào?
Bạn phân tích vì sao so sánh JFR trước và sau tối ưu cần giữ workload và JVM warmup tương đương ra sao?
Bạn sẽ tạo custom JFR event ở phiên bản JDK hỗ trợ để đánh dấu một operation quan trọng như thế nào?
Bạn sẽ xác định khi nào nên dùng structured logging cùng JFR thay vì cố đưa mọi thông tin vào recording ra sao?
Bạn mô tả cách đánh giá ảnh hưởng của HTTP Client network waits qua JFR cùng application timers như thế nào?
Bạn sẽ ghi lại metadata JDK version và recording configuration để một kết quả JFR có thể tái phân tích ra sao?
Bạn phân tích vì sao một recording thiếu event kỳ vọng có thể do event bị tắt hoặc điều kiện kích hoạt chưa xuất hiện ra sao?
Bạn sẽ thiết kế runbook kích hoạt JFR ngắn hạn khi production gặp độ trễ bất thường như thế nào?
Bạn sẽ bảo đảm việc thu JFR không vượt storage quota của host hoặc container theo cách nào?
Bạn sẽ dùng jcmd VM.version để xác định chính xác JVM đang chạy trong một incident như thế nào?
Bạn mô tả jcmd VM.command_line giúp so sánh startup options với cấu hình deployment dự kiến ra sao?
Bạn sẽ dùng jcmd VM.flags để xác minh những JVM flags thực tế được áp dụng theo cách nào?
Bạn phân biệt jcmd Thread.print với JFR thread sampling khi cần điều tra deadlock hoặc contention ra sao?
Bạn sẽ lấy nhiều thread dumps để tìm dấu hiệu các threads bị chặn kéo dài như thế nào?
Bạn mô tả jstack hỗ trợ điều tra trạng thái RUNNABLE, BLOCKED và WAITING như thế nào?
Bạn sẽ dùng jcmd GC.heap_info để xem tổng quan heap trước khi quyết định có cần heap dump ra sao?
Bạn phân biệt class histogram và heap dump về độ chi tiết cùng tác động lên tiến trình theo mục tiêu nào?
Bạn sẽ dùng jstat -gc để quan sát GC counters theo thời gian và tránh suy diễn một memory leak ngay lập tức như thế nào?
Bạn mô tả vì sao kết quả jcmd có thể không truy cập được JVM trong container khác PID namespace như thế nào?
Bạn sẽ kiểm tra quyền OS user và attach policy trước khi chạy diagnostic command trên production ra sao?
Bạn phân tích vì sao một heap dump có thể chứa tokens và dữ liệu cá nhân cần quyền truy cập nghiêm ngặt ra sao?
Bạn sẽ sử dụng jdeps --jdk-internals để phát hiện dependency dựa vào JDK internal API khi nâng bản Java ra sao?
Bạn mô tả jdeps --print-module-deps giúp xác định modules cho custom runtime image còn hữu ích như thế nào?
Bạn sẽ đối chiếu module graph tĩnh của jdeps với dynamic dependencies qua reflection khi chạy tests như thế nào?
Bạn phân biệt javap -verbose kiểm tra class file version với jdeps kiểm tra dependency graph như thế nào?
Bạn sẽ dùng javac --release 11 trên JDK hỗ trợ để chứng minh một API được dùng thuộc Java 11 platform như thế nào?
Bạn phân tích vì sao một chương trình dùng HTTP Client Java 11 có thể chạy khác trên JDK mới nếu TLS defaults thay đổi ra sao?
Bạn sẽ tổ chức diagnostic artifacts gồm thread dumps, JFR và GC logs để tái dựng timeline sự cố như thế nào?
Bạn sẽ chọn jcmd, jstack hoặc JFR tùy sự cố là treo thread, allocation tăng hay latency spike như thế nào?
Bạn mô tả cách kiểm tra JFR event format bằng công cụ đang đi kèm JDK thay vì dựa vào lệnh của phiên bản khác như thế nào?
Bạn sẽ đánh giá công cụ jlink khi đóng runtime tối thiểu có chứa module java.net.http theo nhu cầu nào?
Bạn phân tích vì sao một runtime image thiếu java.net.http làm HTTP Client code thất bại dù compile thành công ra sao?
Bạn sẽ thiết kế smoke tests xác nhận runtime image hỗ trợ những modules và TLS protocols ứng dụng cần như thế nào?
Bạn sẽ dùng HTTP Client mock server để kiểm thử request headers, body và status handling mà không gọi Internet như thế nào?
Bạn phân biệt unit test logic tạo HttpRequest với integration test HTTP server trả redirect hoặc timeout ra sao?
Bạn sẽ thiết kế test cho HttpClient.sendAsync có lỗi kết nối mà không làm test treo vô hạn như thế nào?
Bạn mô tả cách xác minh timeout và retry policies bằng server cố ý làm chậm response ra sao?
Bạn sẽ kiểm tra một HTTP Client không gửi Authorization header sang host ngoài allowlist sau redirect như thế nào?
Bạn phân tích vì sao test TLS tự ký chỉ nên dùng truststore thử nghiệm thay vì vô hiệu hóa certificate validation ra sao?
Bạn sẽ tạo test HTTP/2 có kiểm tra HttpResponse.version thay vì giả định builder preference luôn thành công như thế nào?
Bạn sẽ đánh giá resource leaks khi BodyHandlers.ofInputStream response không được đóng qua load test ra sao?
Bạn mô tả cách benchmark HttpClient reuse so với tạo client mới mà không nhầm network variability với CPU time như thế nào?
Bạn sẽ dùng JMH để benchmark String.strip hoặc String.lines trên dữ liệu đại diện và tránh tối ưu hóa bỏ kết quả ra sao?
Bạn phân tích vì sao đo String.repeat với số lần cực lớn có thể đo chủ yếu allocation/GC chứ không đại diện sản phẩm ra sao?
Bạn sẽ kiểm thử Files.readString với file UTF-8 hợp lệ và bytes không hợp lệ theo các trường hợp nào?
Bạn mô tả cách test Files.writeString với CREATE_NEW, APPEND và TRUNCATE_EXISTING trong thư mục tạm ra sao?
Bạn sẽ đánh giá tính tương thích của logic path khi code được chạy trên Windows và Linux như thế nào?
Bạn phân tích vì sao test chỉ dùng chuỗi ASCII không đủ xác nhận isBlank hoặc strip hoạt động đúng trên Unicode ra sao?
Bạn sẽ dùng test fixtures để phân biệt các dạng newline khi xử lý String.lines như thế nào?
Bạn sẽ xác minh Optional.isEmpty và Predicate.not không bị dùng trên target Java thấp hơn khả năng hỗ trợ ra sao?
Bạn phân tích vì sao chuyển runtime không cần sửa mã nguồn vẫn phải kiểm tra behavior của HTTP/TLS và Unicode như thế nào?
Bạn sẽ thiết kế regression tests kết hợp Java 11 API, Charset UTF-8 và single-file source execution trong CI như thế nào?
Bạn mô tả cách thêm automated security scan cho dependencies và JDK runtime image mà không phụ thuộc API legacy ra sao?
Bạn sẽ xác định khi nào thay một thư viện HTTP bên ngoài bằng java.net.http.HttpClient có lợi dựa trên tính năng và bảo trì như thế nào?
Bạn phân tích vì sao giữ abstraction cho HTTP calls giúp thay backend hoặc thay policy mà không phải sửa toàn bộ application ra sao?
Bạn sẽ viết checklist nâng JDK kiểm tra API availability, encoding, certificates, async behavior và diagnostic flags như thế nào?
Bạn sẽ xây quy trình theo dõi JDK release notes để cập nhật cấu hình nhưng tránh nhầm một optimization thành hợp đồng API ra sao?
Nếu String.isBlank trả kết quả khác kiểm tra length bằng không, bạn sẽ giải thích khác biệt dữ liệu đầu vào như thế nào?
Nếu String.strip không loại bỏ một ký tự nhìn giống khoảng trắng, bạn sẽ kiểm tra Unicode code point và Character.isWhitespace ra sao?
Nếu String.lines cho số dòng khác split theo regex, bạn sẽ phân tích newline semantics và trailing delimiter như thế nào?
Nếu String.repeat khiến ứng dụng thiếu bộ nhớ, bạn sẽ xác định giới hạn input và cách xây output theo luồng ra sao?
Nếu Files.readString thất bại trên file không phải UTF-8, bạn sẽ chẩn đoán Charset và chính sách đọc dữ liệu ra sao?
Nếu Files.writeString ghi dở rồi process chết, bạn sẽ thiết kế temporary file và atomic move để tránh file hỏng như thế nào?
Nếu một Path.of nhận đường dẫn do người dùng cung cấp, bạn sẽ bảo đảm nó nằm trong thư mục hợp lệ và không theo symlink nguy hiểm ra sao?
Nếu Java 11 HTTP Client nhận 404 nhưng code không ném exception, bạn sẽ thiết kế status validation đúng như thế nào?
Nếu HttpClient.sendAsync trả CompletionException, bạn sẽ truy nguyên IOException hoặc timeout thực sự ra sao?
Nếu HttpClient xử lý hàng nghìn requests nhưng latency tăng, bạn sẽ kiểm tra reuse, executor, concurrency và connection limits như thế nào?
Nếu HTTP/2 được yêu cầu nhưng HttpResponse.version là HTTP_1_1, bạn sẽ kiểm tra server negotiation, TLS và proxy ra sao?
Nếu request bị chuyển hướng tới host khác, bạn sẽ kiểm tra redirect policy và tránh rò thông tin xác thực ra sao?
Nếu HTTPS handshake lỗi certificate, bạn sẽ kiểm tra truststore, SAN và TLS configuration thay vì tắt validation như thế nào?
Nếu WebSocket.Listener nhận message dưới nhiều fragments, bạn sẽ tổ chức buffer và request(n) theo nhu cầu như thế nào?
Nếu BodyHandlers.ofInputStream bị bỏ quên close gây rò tài nguyên, bạn sẽ thiết kế ownership và finally block ra sao?
Nếu source-file script chạy ở máy dev nhưng lỗi trong CI, bạn sẽ kiểm tra JDK version, working directory và classpath như thế nào?
Nếu một lambda dùng var cho một tham số nhưng kiểu tường minh cho tham số khác, bạn sẽ giải thích compiler error và sửa ra sao?
Nếu Predicate.not(String::isBlank) gặp null, bạn sẽ kiểm tra input contract trước khi áp dụng predicate như thế nào?
Nếu thư viện dùng Optional.isEmpty nhưng cấu hình biên dịch nhắm tới bản Java chưa có API này, bạn sẽ kiểm tra release compatibility và điều chỉnh ra sao?
Nếu Collection.toArray(String[]::new) cho kết quả không như kỳ vọng, bạn sẽ kiểm tra generic element type và array covariance như thế nào?
Nếu JFR không ghi event cần tìm, bạn sẽ kiểm tra recording settings và thời điểm workload xảy ra như thế nào?
Nếu jcmd không attach được JVM đang chạy trong container, bạn sẽ kiểm tra permissions và PID namespace ra sao?
Nếu javac --release 11 báo không tìm thấy một method có ở JDK mới, bạn sẽ xác nhận API được thêm ở release nào như thế nào?
Nếu runtime image có module java.base nhưng thiếu java.net.http, bạn sẽ bổ sung modules và smoke test như thế nào?
Nếu nâng runtime khiến code xử lý Unicode đổi kết quả, bạn sẽ so sánh Character rules và test fixtures giữa hai JDK ra sao?
Nếu cần chọn các tính năng Java 11 vẫn đáng học hôm nay, bạn sẽ ưu tiên String/Files, HttpClient, source-file mode, lambda và JFR theo những tiêu chí nào?
