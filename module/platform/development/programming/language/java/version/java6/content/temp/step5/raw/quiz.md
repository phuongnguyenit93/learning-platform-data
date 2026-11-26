Đặc trưng nào của `Deque` bổ sung khả năng quan trọng so với `Queue` thông thường?
A. Thao tác ở cả hai đầu deque.
B. Chỉ lấy phần tử theo thứ tự FIFO.
C. Chỉ cho phép lấy phần tử ở đầu.
D. Tự sắp xếp các phần tử theo khóa.
Đáp án đúng: A

Điều gì xảy ra khi truyền `null` vào `ArrayDeque.addFirst`?
A. Trả `false` và giữ deque nguyên trạng.
B. Bỏ qua `null` mà không trả thông báo.
C. Phát sinh `NullPointerException`.
D. Chấp nhận `null` như phần tử thường.
Đáp án đúng: C

Khi một `Deque` đang rỗng, `peekFirst()` khác `removeFirst()` như thế nào?
A. Cả hai ném lỗi khi không có phần tử.
B. `peekFirst` trả null, `removeFirst` ném lỗi.
C. `peekFirst` ném lỗi, `removeFirst` trả null.
D. Cả hai trả null khi không có phần tử.
Đáp án đúng: B

Cặp phương thức nào thể hiện thao tác stack LIFO trên `Deque`?
A. `push` để thêm, `pop` để lấy.
B. `addLast` để thêm, `pollFirst` để lấy.
C. `offerLast` để thêm, `removeFirst` để lấy.
D. `pollFirst` để thêm, `peekLast` để lấy.
Đáp án đúng: A

Khi `LinkedBlockingDeque` bị đầy, `putFirst` hoạt động thế nào?
A. Ném lỗi lập tức nếu không thể thêm.
B. Loại phần tử cuối để thêm phần tử mới.
C. Trả false ngay nếu không thể thêm.
D. Chờ đến khi có chỗ hoặc bị ngắt.
Đáp án đúng: D

Nhận định nào đúng về `ArrayDeque` dùng chung giữa nhiều thread?
A. Các lời gọi `push` đều bảo đảm atomicity.
B. Cần đồng bộ ngoài nếu cập nhật đồng thời.
C. Mọi thao tác cập nhật đều được khóa sẵn.
D. Các iterator luôn là snapshot nhất quán.
Đáp án đúng: B

Muốn duyệt `Deque` từ cuối về đầu mà không đảo dữ liệu, nên dùng gì?
A. Dùng phương thức `descendingIterator()`.
B. Dùng phương thức `iterator().reverse()`.
C. Dùng phương thức `spliterator().reverse()`.
D. Dùng phương thức `descendingStream()`.
Đáp án đúng: A

Với deque có giới hạn sức chứa và đang đầy, `offerLast` thường xử lý ra sao?
A. Trả false khi deque đã đầy.
B. Ném lỗi bắt buộc khi không thêm được.
C. Đẩy phần tử đầu ra rồi thêm vào cuối.
D. Chờ đến khi có chỗ để thêm phần tử.
Đáp án đúng: A

Muốn giới hạn số phần tử của `LinkedBlockingDeque` ngay khi tạo, nên làm gì?
A. Truyền sức chứa vào `putFirst` đầu tiên.
B. Gọi `setCapacity` sau khi tạo deque.
C. Gọi `ensureCapacity` sau khi tạo deque.
D. Đặt sức chứa trong constructor deque.
Đáp án đúng: D

`NavigableMap.floorKey(k)` trả kết quả nào theo thứ tự khóa?
A. Khóa lớn nhất không hơn `k`.
B. Khóa nhỏ nhất không nhỏ hơn `k`.
C. Khóa lớn nhất nhưng nhỏ hơn `k`.
D. Khóa nhỏ nhất nhưng lớn hơn `k`.
Đáp án đúng: A

Khác biệt giữa `higherKey(k)` và `ceilingKey(k)` là gì?
A. Cả hai đều loại khóa đúng bằng `k`.
B. Cả hai đều gồm khóa đúng bằng `k`.
C. `higherKey` loại `k`, `ceilingKey` gồm `k`.
D. `higherKey` gồm `k`, `ceilingKey` loại `k`.
Đáp án đúng: C

Khi dùng `subMap(from, true, to, false)`, khoảng khóa được chọn ra sao?
A. Loại trừ đồng thời `from` và `to`.
B. Loại trừ `from` nhưng bao gồm `to`.
C. Bao gồm đồng thời `from` và `to`.
D. Gồm `from`, không gồm `to`.
Đáp án đúng: D

Với `TreeMap`, kết quả `descendingMap()` có đặc điểm nào?
A. Là bản sao tách biệt hoàn toàn khỏi map gốc.
B. Là một view có liên kết với map gốc.
C. Là map chỉ đọc không thể xóa entry nào.
D. Là map mới được sắp theo hash của khóa.
Đáp án đúng: B

Lời gọi `pollFirstEntry()` trên `NavigableMap` có tác dụng gì?
A. Lấy và xóa entry có khóa lớn nhất.
B. Chỉ xem entry có khóa lớn nhất của map.
C. Lấy và xóa entry có khóa nhỏ nhất.
D. Chỉ xem entry có khóa nhỏ nhất của map.
Đáp án đúng: C

Rủi ro nào có thể xảy ra khi `Comparator` của `TreeMap` coi hai khóa khác nhau là bằng nhau?
A. Mỗi thao tác `put` với khóa trùng đều ném lỗi.
B. Map chuyển sang `equals` để phân biệt khóa.
C. Map tạo danh sách riêng cho các khóa trùng.
D. Hai khóa có thể bị xem là cùng một entry.
Đáp án đúng: D

Cấu trúc nào phù hợp khi cần map có thứ tự hỗ trợ truy cập đồng thời?
A. Sử dụng `TreeMap` không kèm đồng bộ.
B. Sử dụng `IdentityHashMap` trực tiếp.
C. Sử dụng `LinkedHashMap` trực tiếp.
D. Sử dụng `ConcurrentSkipListMap`.
Đáp án đúng: D

Để tìm phần tử nhỏ nhất lớn hơn hoặc bằng `x` trong `NavigableSet`, dùng gì?
A. Sử dụng `lower(x)` của tập hợp.
B. Sử dụng `higher(x)` của tập hợp.
C. Sử dụng `ceiling(x)` của tập hợp.
D. Sử dụng `floor(x)` của tập hợp.
Đáp án đúng: C

Điều gì cần lưu ý khi sửa view trả về bởi `TreeMap.subMap(...)`?
A. View tự cho chèn khóa vượt ngoài khoảng.
B. Cập nhật hợp lệ được phản ánh trên map gốc.
C. View tự sao chép dữ liệu trước khi thay đổi.
D. View bỏ qua cập nhật đến từ map gốc.
Đáp án đúng: B

Vì sao không nên sửa đối tượng khóa sau khi đưa vào `TreeMap`?
A. Map tự gắn khóa cứng và chặn mọi thay đổi.
B. Có thể làm sai quan hệ thứ tự tra cứu.
C. Map tự di chuyển entry ngay sau khi khóa đổi.
D. Mọi lần thay đổi khóa đều phát sinh exception.
Đáp án đúng: B

`ServiceLoader` giúp ứng dụng giải quyết vấn đề gì?
A. Khám phá provider theo hợp đồng SPI.
B. Quản lý transaction cho các provider.
C. Đồng bộ hóa các provider theo thứ tự.
D. Tạo đối tượng proxy cho mọi interface.
Đáp án đúng: A

Trên classpath, tài nguyên nào thường đăng ký các provider cho `ServiceLoader`?
A. Tệp `META-INF/services/<tên service>`.
B. Tệp `META-INF/modules/<tên service>`.
C. Tệp `META-INF/providers/<tên service>`.
D. Tệp `META-INF/exports/<tên service>`.
Đáp án đúng: A

Khi duyệt `ServiceLoader`, điều gì đúng về việc tạo provider?
A. Mọi provider được tạo ngay khi JVM khởi chạy.
B. Provider chỉ được tạo khi đã gọi `reload`.
C. Mọi provider được tạo trước khi có iterator.
D. Provider có thể khởi tạo lúc duyệt.
Đáp án đúng: D

Khi cấu hình SPI chứa tên provider không hợp lệ, loại lỗi nào phù hợp?
A. Có thể nhận `IllegalMonitorStateException`.
B. Có thể nhận `NegativeArraySizeException`.
C. Có thể nhận `ConcurrentModificationException`.
D. Có thể nhận `ServiceConfigurationError`.
Đáp án đúng: D

Để dùng `ServiceLoader` với provider từ class loader plugin, nên chú ý gì?
A. Dùng loader thấy cả service lẫn provider.
B. Bỏ qua danh tính class loader của service.
C. Chỉ cho phép dùng bootstrap class loader.
D. Chỉ cho phép dùng system class loader.
Đáp án đúng: A

Trong JPMS, module khai báo sử dụng và cung cấp service bằng cặp nào?
A. `requires` và `exports ... to`.
B. `uses` và `provides ... with`.
C. `opens` và `exports ... to`.
D. `requires` và `opens ... to`.
Đáp án đúng: B

`ServiceLoader.reload()` có ý nghĩa cơ bản nào?
A. Tạo lại các object provider đang sử dụng.
B. Nạp lại mọi JAR trong classpath hiện tại.
C. Gỡ mọi lớp provider khỏi class loader.
D. Xóa bộ nhớ đệm provider để duyệt lại.
Đáp án đúng: D

Khi đóng gói shaded JAR chứa nhiều provider SPI, nguy cơ phổ biến là gì?
A. Các constructor provider bị xóa tự động.
B. Provider luôn bị chuyển thành module mới.
C. Tên service được sửa thành tên JAR.
D. Các tệp dịch vụ bị ghi đè khi hợp nhất.
Đáp án đúng: D

Muốn chọn provider theo capability thay vì thứ tự tìm thấy, nên làm gì?
A. Chọn provider đầu vì SPI tự sắp ưu tiên.
B. Chọn provider cuối vì SPI tự theo bản mới.
C. Duyệt provider rồi so sánh capability cần thiết.
D. Chọn provider bất kỳ vì các provider như nhau.
Đáp án đúng: C

API nào cung cấp Java compiler từ JDK phù hợp cho `javax.tools`?
A. `Compiler.getCurrentJavaCompiler()`.
B. `ToolProvider.getSystemJavaCompiler()`.
C. `ToolProvider.newCompilerTask()`.
D. `JavaCompiler.getDefaultCompiler()`.
Đáp án đúng: B

Vì sao `getSystemJavaCompiler()` có thể trả `null` khi chạy ứng dụng?
A. Compiler chưa từng chạy trong tiến trình.
B. Runtime không cung cấp compiler cần thiết.
C. Nguồn Java chưa khai báo `package`.
D. Classpath có nhiều thư viện khác nhau.
Đáp án đúng: B

Đối tượng nào nhận thông báo lỗi và vị trí lỗi từ `JavaCompiler`?
A. `StandardJavaFileManager` nhận stack trace.
B. `JavaFileObject` nhận các compiler warning.
C. `DiagnosticCollector` nhận các diagnostics.
D. `FileObject` nhận mọi thông báo ở console.
Đáp án đúng: C

Để biểu diễn mã nguồn nằm trong bộ nhớ cho Compiler API, nên dùng gì?
A. Một `JavaFileObject` biểu diễn source code.
B. Một `DiagnosticListener` lưu source code.
C. Một `JavaCompiler` chứa toàn bộ source code.
D. Một `ClassLoader` biểu diễn source code.
Đáp án đúng: A

`StandardJavaFileManager` hỗ trợ công việc nào trong Compiler API?
A. Quản lý file đầu vào, đầu ra và vị trí.
B. Tạo đối tượng runtime từ class đã sinh.
C. Phân tích AST và tối ưu luồng điều khiển.
D. Thực hiện JIT cho phương thức mới nạp.
Đáp án đúng: A

Lời gọi `JavaCompiler.getTask` chủ yếu tạo ra đối tượng gì?
A. Class loader mới đã nạp bytecode.
B. Tiến trình chạy `javac` ở bên ngoài.
C. Đối tượng `Class` của source chưa biên dịch.
D. Tác vụ biên dịch có thể gọi `call()`.
Đáp án đúng: D

Trên JDK mới, dùng tùy chọn nào để kiểm tra API và cú pháp theo mức Java mục tiêu?
A. `jar --describe-module` theo phiên bản đích.
B. `jshell --startup` theo phiên bản đích.
C. `java --class-path` với phiên bản đích.
D. `javac --release` với phiên bản đích.
Đáp án đúng: D

Trong annotation processor, API nào dùng để tạo file nguồn mới?
A. `Elements` từ `ProcessingEnvironment`.
B. `Filer` từ `ProcessingEnvironment`.
C. `Messager` từ `ProcessingEnvironment`.
D. `RoundEnvironment` với `getElements`.
Đáp án đúng: B

Khi annotation không hợp lệ, processor nên báo diagnostic bằng gì?
A. Dùng `Filer` ghi một tệp class lỗi.
B. Dùng `Trees` đổi AST trước khi báo lỗi.
C. Dùng `Messager` gắn với phần tử nguồn.
D. Dùng `Types` trả về giá trị enum lỗi.
Đáp án đúng: C

Vì sao không được coi JavaCompiler API là sandbox cho mã nguồn không tin cậy?
A. Bytecode luôn chạy trong JVM cô lập.
B. Biên dịch hợp lệ không bảo đảm chạy an toàn.
C. Compiler tự từ chối mọi API mạng.
D. Compiler tự chặn mọi thao tác trên file.
Đáp án đúng: B

Đặc trưng nào của StAX phân biệt nó với SAX khi đọc XML?
A. Consumer chủ động kéo sự kiện từ parser.
B. Parser chỉ đọc nội dung qua DOM node.
C. Parser chủ động gọi handler theo sự kiện.
D. Parser dựng cây tài liệu toàn bộ trong heap.
Đáp án đúng: A

Muốn đọc XML bằng cursor API của StAX, nên tạo loại nào?
A. `XMLEventReader` từ `XMLOutputFactory`.
B. `XMLStreamWriter` từ `XMLInputFactory`.
C. `XMLEventWriter` từ `XMLOutputFactory`.
D. `XMLStreamReader` từ `XMLInputFactory`.
Đáp án đúng: D

Khi đọc text giữa hai thẻ XML bằng `XMLStreamReader`, điều gì cần lưu ý?
A. Text luôn nằm trong một event `CDATA`.
B. Text có thể được chia thành nhiều event.
C. Text được parser bỏ qua sau `nextTag`.
D. Text luôn là duy nhất một `CHARACTERS`.
Đáp án đúng: B

Khi phân tích XML có namespace, nhận diện phần tử nên dựa vào gì?
A. Tên file chứa XML và tên của phần tử.
B. Prefix nguyên văn trong XML đầu vào.
C. Namespace URI cùng local name của phần tử.
D. Thứ tự của các attribute trong phần tử.
Đáp án đúng: C

Để giảm nguy cơ XXE khi nhận XML không tin cậy qua StAX, nên làm gì?
A. Hạn chế DTD và external entities qua factory.
B. Chỉ gọi `nextTag` thay vì `next`.
C. Chỉ đọc nội dung bằng `getElementText`.
D. Tắt kiểm tra namespace của input factory.
Đáp án đúng: A

Khác biệt nổi bật giữa `XMLEventReader` và `XMLStreamReader` là gì?
A. StreamReader luôn trả một `XMLEvent`.
B. StreamReader tự dựng toàn bộ DOM tree.
C. EventReader trả về các đối tượng sự kiện.
D. EventReader luôn trả một `Document`.
Đáp án đúng: C

API nào phù hợp khi cần tạo nội dung XML theo từng phần tử?
A. `XMLResolver` từ `XMLInputFactory`.
B. `XMLStreamReader` từ `XMLInputFactory`.
C. `XMLEventReader` từ `XMLInputFactory`.
D. `XMLStreamWriter` từ `XMLOutputFactory`.
Đáp án đúng: D

Vì sao khi ghi XML nên dùng phương thức ghi text của StAX thay vì nối chuỗi thẳng?
A. Để tự động kiểm tra tài liệu với XSD.
B. Để tự xóa mọi namespace không dùng.
C. Để escape ký tự đặc biệt đúng ngữ cảnh.
D. Để tự thêm chữ ký số cho toàn tài liệu.
Đáp án đúng: C

Nếu tài liệu XML sai cấu trúc khi đọc bằng StAX, cần xử lý lỗi nào?
A. `ParserConfigurationException` từ reader.
B. `TransformerException` từ XML writer.
C. `XMLStreamException` từ XML reader.
D. `SAXNotRecognizedException` từ reader.
Đáp án đúng: C

Khi xử lý XML rất lớn, lợi ích quan trọng của StAX là gì?
A. Tạo sẵn index XPath cho mọi XML element.
B. Chỉ giữ cây DOM nhưng bỏ các thuộc tính.
C. Dựng toàn bộ tree trước rồi duyệt tuần tự.
D. Đọc tuần tự, không giữ toàn bộ cây XML.
Đáp án đúng: D

Cơ chế JDBC 4.0 nào giúp tìm driver khi JAR được đóng gói đúng?
A. Driver được khám phá qua service provider.
B. Driver luôn được nạp từ `module-info.java`.
C. Driver được chọn theo tên class trong URL.
D. Driver bắt buộc phải gọi `Class.forName`.
Đáp án đúng: A

Dùng `Connection.isValid(timeout)` để làm gì?
A. Kiểm tra mọi bảng của database đang tồn tại.
B. Kiểm tra transaction đã được commit đầy đủ.
C. Kiểm tra kết nối còn hợp lệ trong thời hạn.
D. Kiểm tra truy vấn sẽ luôn có execution plan.
Đáp án đúng: C

Khi dùng `Connection.setClientInfo`, ngoại lệ nào phù hợp nếu thuộc tính bị từ chối?
A. `SQLIntegrityConstraintViolationException`.
B. `SQLClientInfoException` cho client info.
C. `SQLTimeoutException` cho client info.
D. `SQLNonTransientConnectionException`.
Đáp án đúng: B

Loại ngoại lệ JDBC nào gợi ý lỗi có thể tạm thời và cân nhắc retry?
A. `SQLNonTransientException` theo loại lỗi.
B. `SQLIntegrityConstraintViolationException`.
C. `SQLFeatureNotSupportedException`.
D. `SQLTransientException` theo loại lỗi.
Đáp án đúng: D

Khi driver không hỗ trợ một chức năng JDBC được yêu cầu, nên dự kiến gì?
A. Có thể gặp `SQLIntegrityConstraintViolationException`.
B. Có thể gặp `SQLTransactionRollbackException`.
C. Có thể gặp `SQLFeatureNotSupportedException`.
D. Có thể gặp `SQLTransientConnectionException`.
Đáp án đúng: C

`SQLXML` trong JDBC dùng chủ yếu để làm gì?
A. Thay thế transaction isolation level.
B. Đọc hoặc ghi dữ liệu cột SQL kiểu XML.
C. Định nghĩa cấu hình connection pool XML.
D. Chuyển toàn bộ câu SQL thành XPath.
Đáp án đúng: B

Điều gì nên được xem xét khi sử dụng `RowId` từ JDBC?
A. Giá trị luôn là UUID ổn định toàn cầu.
B. Giá trị luôn bằng khóa chính được khai báo.
C. Hiệu lực phụ thuộc vào hệ cơ sở dữ liệu.
D. Giá trị luôn tồn tại qua mọi lần export.
Đáp án đúng: C

Tác dụng của `Wrapper.unwrap` trong JDBC là gì?
A. Chuyển mọi câu SQL sang prepared statement.
B. Tự động thực thi lại truy vấn lỗi tạm thời.
C. Giải phóng tài nguyên của kết nối đang mở.
D. Lấy interface chuyên biệt do driver hỗ trợ.
Đáp án đúng: D

`NClob` trong JDBC liên quan tới loại dữ liệu nào?
A. Dữ liệu khóa chính kiểu số nguyên.
B. Dữ liệu ký tự lớn dạng national character.
C. Dữ liệu byte lớn dùng cho file nhị phân.
D. Dữ liệu JSON lớn không có cấu trúc.
Đáp án đúng: B

`Statement.setPoolable(true)` mang ý nghĩa nào theo hợp đồng JDBC?
A. Gợi ý driver có thể đưa statement vào pool.
B. Bắt buộc pool connection phải được tạo mới.
C. Bật auto-commit cho mọi statement hiện có.
D. Giữ statement sống khi connection đã đóng.
Đáp án đúng: A

Khi `Arrays.copyOf` sao chép mảng đối tượng, điều gì đúng về phần tử?
A. Các phần tử gốc tự chuyển sang `null`.
B. Bản sao vẫn tham chiếu đối tượng bên trong.
C. Mọi đối tượng gốc bị khóa không cho sửa.
D. Mỗi đối tượng phần tử được deep copy.
Đáp án đúng: B

`Arrays.copyOfRange(a, from, to)` dùng quy tắc ranh giới nào?
A. Loại trừ cả `from` lẫn `to`.
B. Loại trừ `from` và bao gồm `to`.
C. Bao gồm `from` và loại trừ `to`.
D. Bao gồm cả `from` lẫn `to`.
Đáp án đúng: C

Khi tạo set bằng `Collections.newSetFromMap(map)`, điều kiện nào quan trọng?
A. Backing map phải rỗng khi tạo set.
B. Backing map phải chứa sẵn một khóa.
C. Backing map phải là `TreeMap` có thứ tự.
D. Backing map phải chứa một giá trị `null`.
Đáp án đúng: A

Dùng `Normalizer.normalize(text, Form.NFC)` khi nào là phù hợp?
A. Khi muốn đổi mọi chữ thành chữ hoa.
B. Khi cần chuẩn hóa dạng Unicode chuẩn tắc.
C. Khi muốn sắp xếp từ theo locale.
D. Khi muốn bỏ toàn bộ dấu tiếng Việt.
Đáp án đúng: B

Trước khi gọi `Desktop.browse`, ứng dụng cần kiểm tra điều gì?
A. Desktop và thao tác `BROWSE` được hỗ trợ.
B. Ứng dụng có thể ghi vào thư mục tạm.
C. JVM có trình duyệt JavaScript tích hợp sẵn.
D. Desktop luôn có sẵn trên môi trường server.
Đáp án đúng: A

Đối với `ScriptEngineManager` trên JDK hiện đại, nhận định nào đúng?
A. JDK luôn tích hợp Nashorn làm mặc định.
B. Mọi engine phải được đóng gói trong JDK.
C. Engine JavaScript cần có provider tương ứng.
D. Mọi JavaScript engine đều dùng chung runtime.
Đáp án đúng: C
