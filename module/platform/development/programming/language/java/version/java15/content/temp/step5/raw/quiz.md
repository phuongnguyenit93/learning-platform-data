Text block hoàn thiện ở Java 15 được biểu diễn bằng kiểu dữ liệu nào?
A. String, dùng được với các API xử lý chuỗi Java.
B. StringBuilder, hỗ trợ thay đổi trực tiếp nội dung chuỗi.
C. CharBuffer, lưu ký tự trong vùng nhớ có thể chỉnh sửa.
D. StringBuffer, đồng bộ hóa thao tác chỉnh sửa ký tự.
Đáp án đúng: A

Sau dấu phân cách mở của text block, cú pháp Java yêu cầu điều gì?
A. Phải xuống dòng trước khi bắt đầu phần nội dung.
B. Có thể viết ngay văn bản trên cùng dòng với dấu mở.
C. Phải ghi dấu phân cách đóng trên cùng dòng với dấu mở.
D. Có thể dùng dấu nháy kép đơn thay cho ba dấu mở.
Đáp án đúng: A

Quy tắc xử lý thụt lề của text block Java hoạt động như thế nào?
A. Giữ nguyên mọi khoảng trắng đầu dòng trong mã nguồn.
B. Xóa toàn bộ thụt lề đầu dòng, kể cả phần chủ ý.
C. Thay mọi thụt lề bằng ký tự tab trước khi dùng.
D. Loại phần thụt lề ngẫu nhiên theo quy tắc text block.
Đáp án đúng: D

Khi mã nguồn text block dùng kết thúc dòng CRLF, giá trị String xử lý xuống dòng thế nào?
A. Giữ nguyên CRLF để chuỗi giống từng byte trong tệp nguồn.
B. Chuẩn hóa dấu xuống dòng trong nội dung về dạng LF.
C. Xóa dấu xuống dòng để nối các dòng thành một chuỗi.
D. Thay dấu xuống dòng bằng phân cách hiện hành của hệ điều hành.
Đáp án đúng: B

Khi dấu phân cách đóng của text block nằm trên dòng riêng sau nội dung, điều gì đúng?
A. Trình biên dịch tự bỏ ký tự xuống dòng cuối cùng.
B. Nội dung chỉ có xuống dòng khi thêm dấu escape thủ công.
C. Chuỗi luôn được tự động thêm hai ký tự xuống dòng cuối.
D. Ký tự xuống dòng trước dấu đóng vẫn thuộc nội dung.
Đáp án đúng: D

Escape \s trong text block hữu ích ở trường hợp nào?
A. Giữ dấu cách cuối dòng có nguy cơ bị loại bỏ.
B. Thay dấu cách cuối dòng bằng một ký tự tab để căn đều.
C. Bỏ dấu xuống dòng trước dấu phân cách kết thúc text block.
D. Xóa toàn bộ khoảng trắng ở giữa các từ trên một dòng.
Đáp án đúng: A

Khi đặt dấu backslash ở cuối dòng text block, hiệu ứng đặc biệt là gì?
A. Giữ cả dấu backslash lẫn dấu xuống dòng trong giá trị.
B. Tự động xóa toàn bộ phần thụt lề của dòng kế tiếp.
C. Đổi dấu xuống dòng thành hai dấu cách trong giá trị.
D. Nối dòng kế tiếp mà không đưa xuống dòng vào chuỗi.
Đáp án đúng: D

String.stripIndent() giải quyết loại nhu cầu nào?
A. Thay mọi ký tự xuống dòng bằng dấu cách giữa từ.
B. Chuyển escape kiểu Java thành ký tự điều khiển.
C. Áp dụng tham số định dạng kiểu printf cho chuỗi.
D. Loại thụt lề ngẫu nhiên khỏi chuỗi nhiều dòng.
Đáp án đúng: D

String.translateEscapes() có chức năng chính nào?
A. Diễn giải các escape Java trong chuỗi văn bản.
B. Loại thụt lề ngẫu nhiên cho từng dòng văn bản.
C. Chuyển Unicode sang dãy byte UTF-8 trong JVM.
D. Áp dụng các giá trị lên placeholder định dạng.
Đáp án đúng: A

Biểu thức "%s-%d".formatted("A", 3) cho kết quả nào?
A. Chuỗi %s-%d, vì formatted không thực hiện thay thế.
B. Chuỗi A3, vì formatted tự loại ký tự phân cách.
C. Chuỗi A-3, do thay các tham số theo mẫu.
D. Chuỗi A-%d, vì formatted chỉ thay tham số đầu.
Đáp án đúng: C

Khi đưa dữ liệu người dùng vào JSON từ text block, cách làm phù hợp là gì?
A. Nối trực tiếp chuỗi vì text block tự escape JSON.
B. Dùng bộ tuần tự hóa JSON để mã hóa giá trị được chèn.
C. Chỉ gọi stripIndent rồi nối, không cần mã hóa JSON.
D. Đổi mọi dấu nháy kép sang dấu nháy đơn trước khi nối.
Đáp án đúng: B

Khi dùng text block viết SQL nhiều dòng có tham số động, cách nào an toàn?
A. Nối giá trị vào text block vì xuống dòng đã lọc ký tự.
B. Dùng String.formatted để tự loại nguy cơ SQL injection.
C. Gắn giá trị bằng tham số qua PreparedStatement.
D. Gọi translateEscapes trước khi đưa mọi tham số vào SQL.
Đáp án đúng: C

Khi cần chèn một dấu nháy kép đơn trong nội dung text block, nên làm thế nào?
A. Luôn phải escape mọi dấu nháy kép bằng backslash.
B. Đổi dấu nháy kép thành dấu nháy đơn tương đương.
C. Viết dấu nháy kép trực tiếp mà không cần escape.
D. Đóng text block trước mọi dấu nháy kép ở nội dung.
Đáp án đúng: C

API nào dùng để định nghĩa hidden class từ bytecode hợp lệ trên JDK hiện đại?
A. ClassLoader.loadClass(String) với tên chưa có trên classpath.
B. Class.forName(String) với tên lớp sinh tạm trong runtime.
C. Object.getClass() với một byte[] chứa dữ liệu class file.
D. MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ...).
Đáp án đúng: D

Kết quả trả về từ Lookup.defineHiddenClass khi định nghĩa thành công là gì?
A. Một ClassLoader mới chỉ chứa class vừa sinh.
B. Một Method biểu diễn phương thức của class.
C. Một Lookup liên kết với hidden class vừa tạo.
D. Một instance của class sau khi gọi constructor.
Đáp án đúng: C

API nào xác định một đối tượng Class có phải hidden class hay không?
A. Class.isAnonymousClass() cho mọi class được sinh động.
B. Class.isSynthetic() như cờ bắt buộc của hidden class.
C. Class.isHidden() trên đối tượng Class tương ứng.
D. Class.getName().isEmpty() để nhận biết class ẩn.
Đáp án đúng: C

Vì sao Class.forName không phù hợp để lấy lại hidden class từ tên?
A. Hidden class chỉ có thể tra cứu bằng tên package của nó.
B. Hidden class luôn dùng tên nhị phân của lookup class.
C. Hidden class luôn thuộc riêng bootstrap class loader.
D. Hidden class không tìm được qua tên nhị phân thông thường.
Đáp án đúng: D

Trường hợp nào phù hợp với hidden classes trong một framework?
A. Định nghĩa model public để các module khác import trực tiếp.
B. Thay mọi class nghiệp vụ thành class ẩn để tăng tốc tự động.
C. Sinh lớp trợ giúp runtime không cần tên công khai ổn định.
D. Đăng ký class API công khai lâu dài để tra bằng tên.
Đáp án đúng: C

Tham số boolean initialize của defineHiddenClass có ý nghĩa gì?
A. Yêu cầu tạo instance mặc định ngay lập tức nếu true.
B. Yêu cầu khởi tạo class ngay khi định nghĩa nếu là true.
C. Yêu cầu ghi bytecode ra tệp .class nếu đặt true.
D. Yêu cầu đăng ký tên nhị phân với loader nếu true.
Đáp án đúng: B

ClassOption.NESTMATE liên quan đến khả năng nào của hidden class?
A. Tự kế thừa các interface mà lookup class đã cài đặt.
B. Công khai tên nhị phân cho tất cả các class loader.
C. Bỏ mọi kiểm tra truy cập thành viên Java lúc runtime.
D. Tham gia cùng nest với lookup class theo quy tắc nestmate.
Đáp án đúng: D

Vì sao quyền của Lookup quan trọng khi gọi defineHiddenClass?
A. Bytecode đầu vào luôn được cấp toàn quyền truy cập Java.
B. Tên class bất kỳ đủ để định nghĩa trong mọi package.
C. Quyền chỉ được xác minh lúc instance sang thread khác.
D. Ràng buộc package và ngữ cảnh truy cập khi định nghĩa.
Đáp án đúng: D

byte[] truyền cho defineHiddenClass phải chứa nội dung nào?
A. Các byte class file hợp lệ theo đặc tả JVM.
B. Văn bản mã nguồn Java được mã hóa thành UTF-8.
C. Dãy ký tự là tên class muốn tải bằng reflection.
D. Dữ liệu serialize của một đối tượng có sẵn.
Đáp án đúng: A

Giới hạn nào cần nhớ khi muốn tham chiếu hidden class ở mã nguồn khác?
A. Không thể dùng tên nhị phân thông thường để liên kết đến nó.
B. Có thể import trực tiếp như với bất kỳ lớp public nào.
C. Có thể gọi Class.forName để phục hồi tên của nó.
D. Có thể ghi tên class ẩn trong source và compile.
Đáp án đúng: A

ClassOption.STRONG tác động tới vòng đời hidden class như thế nào?
A. Giữ class tồn tại vĩnh viễn kể cả sau khi JVM dừng.
B. Gắn vòng đời class mạnh hơn với defining class loader.
C. Giữ mọi instance sống bằng một static field tự tạo.
D. Tự thêm final vào toàn bộ các trường của class.
Đáp án đúng: B

Về bảo mật, nhận định nào đúng khi dùng hidden class?
A. Class ẩn tự được cấp mọi quyền trong JVM khi tạo thành công.
B. Ẩn tên không thay thế các kiểm tra quyền truy cập dữ liệu.
C. Bytecode class ẩn không thể bị quan sát bởi công cụ JVM.
D. Reflection không thể truy cập bất kỳ thành viên nào của class.
Đáp án đúng: B

Để sử dụng chữ ký Ed25519 bằng JCA, nên gọi API nào?
A. Cipher.getInstance("Ed25519") để mã hóa và giải mã.
B. MessageDigest.getInstance("Ed25519") để tạo chữ ký.
C. Mac.getInstance("Ed25519") để tạo chữ ký đối xứng.
D. Signature.getInstance("Ed25519") để ký hoặc xác minh.
Đáp án đúng: D

Để sinh cặp khóa Ed25519 chuẩn trong JCA, lời gọi nào phù hợp?
A. KeyPairGenerator.getInstance("Ed25519").generateKeyPair().
B. KeyGenerator.getInstance("Ed25519").generateKey().
C. SecretKeyFactory.getInstance("Ed25519").generateSecret().
D. MessageDigest.getInstance("Ed25519").digest().
Đáp án đúng: A

Trong quy trình ký Ed25519, initSign phải nhận loại khóa nào?
A. Khóa riêng tương ứng với danh tính bên tạo chữ ký.
B. Khóa công khai tương ứng với danh tính bên tạo chữ ký.
C. Khóa bí mật dùng chung giữa hai bên tham gia xác minh.
D. Chứng thư X.509 thay thế hoàn toàn khóa riêng bên ký.
Đáp án đúng: A

Trong quy trình xác minh Ed25519, initVerify dùng loại khóa nào?
A. Khóa riêng tương ứng với khóa công khai bên gửi.
B. Chuỗi băm thông điệp thay thế toàn bộ khóa xác minh.
C. Khóa công khai tương ứng với khóa riêng đã ký.
D. Cặp khóa mới sinh cùng thuật toán ngay trước verify.
Đáp án đúng: C

Khi gọi Signature.update để ký và xác minh, điều kiện dữ liệu quan trọng nhất là gì?
A. Hai bên chỉ cần cùng ký tự trước khi chọn mã hóa khác nhau.
B. Hai bên chỉ cần cùng độ dài byte, không cần nội dung.
C. Hai bên phải dùng đúng cùng chuỗi byte thông điệp.
D. Hai bên chỉ cần cùng tên file chứa thông điệp.
Đáp án đúng: C

EdDSA hỗ trợ mục tiêu bảo mật nào trong ứng dụng?
A. Mã hóa nội dung để chỉ bên giữ khóa riêng đọc được.
B. Thiết lập phiên TLS mà không phải kiểm tra chứng thư.
C. Dẫn xuất khóa đối xứng từ một chuỗi mật khẩu.
D. Xác minh tính toàn vẹn và nguồn ký qua chữ ký số.
Đáp án đúng: D

Ed25519 và Ed448 nên được phân biệt theo cách nào?
A. Hai phương thức nén văn bản trước khi ký thông điệp.
B. Hai chế độ AES dùng một khóa đối xứng có cùng độ dài.
C. Hai biến thể chữ ký EdDSA với đường cong khác nhau.
D. Hai định dạng JSON đóng gói kết quả chữ ký số.
Đáp án đúng: C

Cặp KeySpec chuẩn nào thường dùng khi đọc khóa Ed25519 đã mã hóa?
A. X509EncodedKeySpec cho khóa riêng và PKCS8EncodedKeySpec cho khóa công khai.
B. SecretKeySpec cho khóa riêng và IvParameterSpec cho khóa công khai.
C. PKCS8EncodedKeySpec cho khóa riêng, X509EncodedKeySpec cho khóa công khai.
D. PBEKeySpec cho khóa riêng và GCMParameterSpec cho khóa công khai.
Đáp án đúng: C

Khi nội dung byte đã ký Ed25519 bị thay đổi, xác minh bằng chữ ký cũ ra sao?
A. Không hợp lệ với thông điệp mới khi chữ ký không được tạo lại.
B. Vẫn đúng vì chữ ký chỉ phụ thuộc vào khóa công khai đã phát hành.
C. Vẫn đúng miễn hai thông điệp có cùng độ dài tính bằng byte.
D. Vẫn đúng miễn hai bên đều khai báo thuật toán là Ed25519.
Đáp án đúng: A

API nào vẫn phù hợp để ứng dụng Java gửi và nhận gói UDP?
A. Socket và InputStream để bảo toàn từng datagram riêng.
B. ServerSocket cùng OutputStream để tạo gói UDP.
C. SSLSocket cùng Reader để nhận các gói UDP mã hóa.
D. DatagramSocket cùng DatagramPacket để xử lý datagram.
Đáp án đúng: D

Giả định nào an toàn khi ứng dụng cần bảo đảm độ tin cậy qua UDP?
A. Ứng dụng tự xử lý khả năng mất gói và đảo thứ tự.
B. UDP tự giao đúng một lần theo thứ tự đã gửi.
C. UDP tự retry mọi gói không có xác nhận thành công.
D. UDP bảo đảm gói đến nếu DatagramSocket chưa đóng.
Đáp án đúng: A

Khi gửi qua DatagramSocket, DatagramPacket cần thêm thông tin nào?
A. Địa chỉ và cổng đích để định tuyến gói UDP.
B. IP nguồn bắt buộc được ứng dụng tạo chữ ký trước.
C. Tên DNS của từng router trên đường tới đích.
D. Chứng thư TLS gắn riêng theo mỗi datagram được gửi.
Đáp án đúng: A

setSoTimeout trên DatagramSocket tác động ra sao nếu receive chờ quá lâu?
A. receive trả null và socket tự đóng sau khi hết hạn chờ.
B. receive ném SocketTimeoutException, socket vẫn sử dụng được.
C. receive trả packet rỗng và tự tăng thời hạn chờ.
D. receive chuyển sang TCP để tiếp tục đợi dữ liệu.
Đáp án đúng: B

Khi cần đăng ký kênh UDP với Selector qua Java NIO, API nào phù hợp?
A. DatagramChannel ở chế độ nonblocking làm việc với Selector.
B. ServerSocketChannel dùng để đọc từng gói UDP trong selector.
C. AsynchronousSocketChannel dùng làm kênh UDP có packet.
D. FileChannel đăng ký sự kiện đọc datagram từ mạng.
Đáp án đúng: A

Khác biệt về ranh giới dữ liệu giữa UDP và TCP là gì?
A. UDP là luồng byte, TCP giữ ranh giới thông điệp.
B. Cả UDP lẫn TCP tự giữ thông điệp ứng dụng nguyên vẹn.
C. UDP giữ ranh giới datagram, TCP cung cấp luồng byte.
D. Cả UDP lẫn TCP đều nhận packet có kích thước cố định.
Đáp án đúng: C

Lý do nào khiến cần hạn chế datagram UDP quá lớn trong thực tế?
A. DatagramSocket tự chia thông điệp thành nhiều gói có ack.
B. Phân mảnh IP có thể làm tăng xác suất mất cả datagram.
C. UDP tự sửa mọi mảnh gói bị mất trước khi giao ứng dụng.
D. Bên nhận luôn thu đủ datagram dù MTU đường truyền thấp.
Đáp án đúng: B

Khi cân nhắc ZGC trên JDK hiện đại, mục tiêu chính thường là gì?
A. Tăng thời gian dừng ứng dụng để tối ưu nén heap.
B. Giảm thời gian tạm dừng GC trong tải nhạy độ trễ.
C. Thay toàn bộ cấp phát heap bằng cấp phát trên stack.
D. Chỉ chạy GC sau khi ứng dụng gọi trực tiếp System.gc.
Đáp án đúng: B

Với Shenandoah GC trên bản JDK có hỗ trợ, đặc điểm nào đáng quan tâm?
A. Mọi chu kỳ đều dừng toàn bộ ứng dụng trong suốt GC.
B. Chỉ quản lý các đối tượng trong vùng bộ nhớ native.
C. Nhiều công việc GC chạy đồng thời nhằm giảm pause.
D. Chỉ quét vùng young generation mà không xử lý vùng old.
Đáp án đúng: C

Để quan sát hoạt động GC của JVM hiện đại, cách nào phù hợp?
A. Dùng javac -Xlog:gc* để xem pause trong runtime.
B. Dùng unified logging như -Xlog:gc* để lấy log GC.
C. Dùng javap -Xlog:gc* để đo thời gian chạy GC.
D. Dùng javadoc -Xlog:gc* để ghi các lần cấp phát.
Đáp án đúng: B

Khi so sánh ZGC hoặc Shenandoah với collector khác, bộ chỉ số nào hữu ích nhất?
A. Chỉ thời gian khởi động JVM, bỏ qua các pause.
B. Pause tail latency, throughput, CPU và mức dùng bộ nhớ.
C. Chỉ kích thước JAR, không đo allocation trên heap.
D. Chỉ số class đã load, không xét tốc độ xử lý.
Đáp án đúng: B

Ứng dụng Java tạo quá nhiều object tạm; nên khảo sát chỉ số nào trước khi chỉnh GC?
A. Kích thước text block lớn nhất trong mã nguồn.
B. Thời gian ký Ed25519 thay cho lượng phân bổ.
C. Số phương thức String.formatted được khai báo.
D. Allocation rate và các vị trí cấp phát nổi bật.
Đáp án đúng: D

Với bản JDK hỗ trợ ZGC, tùy chọn nào chọn bộ thu gom đó?
A. -XX:+UseG1GC là tùy chọn bật ZGC trong JVM.
B. -XX:+UseZGC là tùy chọn bật ZGC trong JVM.
C. -XX:+UseSerialGC là tùy chọn bật ZGC trong JVM.
D. -XX:+UseParallelGC là tùy chọn bật ZGC trong JVM.
Đáp án đúng: B

Nhận định nào đúng về lời gọi System.gc() trên JDK hiện đại?
A. Đây là lệnh bắt buộc mọi collector phải dọn toàn bộ heap.
B. Đây là gợi ý thu gom, không bảo đảm GC hoàn tất như mong muốn.
C. Đây là lệnh luôn đóng ngay tất cả tài nguyên native.
D. Đây là lệnh hủy mọi đối tượng không còn tham chiếu.
Đáp án đúng: B
