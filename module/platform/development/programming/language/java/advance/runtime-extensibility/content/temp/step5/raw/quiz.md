Câu 01. Mục đích chính của một Service Provider Interface (SPI) trong kiến trúc Java là gì?
A. Đảm bảo mỗi plugin chạy trong một tiến trình riêng
B. Định nghĩa hợp đồng chung cho các implementations khác nhau
C. Gắn implementation cố định tại thời điểm biên dịch
D. Đặt thuật toán của từng provider vào interface chung
Đáp án đúng: B

Câu 02. Để host gọi plugin mà không phụ thuộc class triển khai, kiểu nào nên nằm trong API chung?
A. Factory private của plugin được host import khi build
B. Service interface dùng chung giữa host và các providers
C. Class nội bộ của một provider được host gọi trực tiếp
D. Class loader cụ thể của plugin được nhúng vào SPI
Đáp án đúng: B

Câu 03. Trên classpath, file nào khai báo các provider cho SPI `com.acme.spi.Encoder`?
A. `META-INF/services/com.acme.spi.Encoder` trong JAR provider
B. `META-INF/spring/com.acme.spi.Encoder` trong JAR host
C. `META-INF/modules/com.acme.spi.Encoder` trong runtime image
D. `META-INF/providers/com.acme.spi.Encoder` trong JAR app
Đáp án đúng: A

Câu 04. Trong file `META-INF/services` truyền thống, một dòng provider hợp lệ chứa gì?
A. Đường dẫn tương đối tới file class trong thư mục resources
B. Tên bean đăng ký trong Spring context của ứng dụng host
C. Tên class triển khai fully qualified của service provider
D. Tên package của SPI để JVM tìm các class bằng reflection
Đáp án đúng: C

Câu 05. Provider class nằm trên classpath để ServiceLoader khởi tạo theo quy ước cơ bản cần gì?
A. Là interface kế thừa SPI với method factory private
B. Class implements SPI với public no-argument constructor
C. Là abstract class implements SPI, có constructor protected
D. Là final class chỉ có static method `provider()` ở classpath
Đáp án đúng: B

Câu 06. `ServiceLoader.load(Codec.class)` dùng class loader nào theo overload một tham số?
A. Bootstrap class loader dù SPI ở classpath ứng dụng
B. Class loader của `Codec` làm lựa chọn trực tiếp
C. System class loader bất kể context loader hiện tại
D. Thread context ClassLoader hiện tại khi gọi hàm `load`
Đáp án đúng: D

Câu 07. Khi SPI được nạp bởi host nhưng provider nằm trong plugin ClassLoader riêng, API nào giúp chọn loader?
A. `ServiceLoader.load(Codec.class, pluginLoader)` chỉ định loader
B. `ServiceLoader.reload(pluginLoader)` thay loader của instance
C. `Codec.class.getModule().addReads(pluginLoader)` chọn loader
D. `ServiceLoader.load(Codec.class)` chọn pluginLoader từ tham số
Đáp án đúng: A

Câu 08. Vì sao chỉ gọi `ServiceLoader.load(Service.class)` chưa có nghĩa tất cả provider đã tạo instance?
A. ServiceLoader chỉ trả metadata và không tạo provider instance
B. Phương thức load trả về danh sách provider đã gọi constructor
C. Phương thức load khởi tạo trước provider ở thư mục META-INF
D. Provider được tìm và khởi tạo lười khi bắt đầu duyệt
Đáp án đúng: D

Câu 09. Khi metadata dịch vụ chứa tên provider không tải được, lỗi nào ServiceLoader có thể ném khi duyệt?
A. `NoSuchFieldError` khi service descriptor bị sai tên
B. `ServiceConfigurationError` khi load hoặc tạo provider lỗi
C. `IllegalMonitorStateException` khi provider thiếu lock
D. `UnsupportedClassVersionError` với các metadata sai format
Đáp án đúng: B

Câu 10. Mục đích của `ServiceLoader.reload()` trên loader hiện có là gì?
A. Thay service interface của loader bằng API mới tương thích
B. Đóng các connection của các provider đang được sử dụng
C. Gỡ các class đã tải khỏi JVM và đóng plugin ClassLoader
D. Xóa cache provider để lần duyệt mới tra cứu lại
Đáp án đúng: D

Câu 11. Với `ServiceLoader.stream()`, thao tác nào lấy type provider mà chưa cần gọi `get()` tạo service?
A. Dùng `ServiceLoader.reload()` rồi truy cập field `type`
B. Dùng `Provider.get()` để chỉ đọc metadata kiểu class
C. Dùng `Class.forName()` lên service type để lấy provider
D. `Provider.type()` đọc type mà không tạo service instance
Đáp án đúng: D

Câu 12. Trong module tiêu thụ SPI qua JPMS, directive nào khai báo ứng dụng dùng service?
A. `uses com.acme.spi.Encoder;` trong module-info.java
B. `exports com.acme.spi.Encoder;` trong module-info.java
C. `provides com.acme.spi.Encoder;` trong module-info.java
D. `opens com.acme.spi.Encoder;` trong module-info.java
Đáp án đúng: A

Câu 13. Trong named module cung cấp `JsonEncoder`, directive JPMS nào đăng ký implementation?
A. `requires Encoder with JsonEncoder;` gắn service implementation
B. `exports Encoder with JsonEncoder;` công bố service implementation
C. `provides Encoder with JsonEncoder;` khai báo service provider
D. `uses Encoder with JsonEncoder;` đăng ký service provider
Đáp án đúng: C

Câu 14. Với provider trong named module, điều nào đúng về package chứa implementation?
A. Phải đặt implementation vào package trùng tên interface SPI
B. Không cần export package chỉ để khai báo service provider
C. Phải export package triển khai để ServiceLoader tạo provider
D. Phải opens package triển khai để class được module system đọc
Đáp án đúng: B

Câu 15. Muốn dò providers trong một `ModuleLayer` mới được tạo, overload nào phù hợp?
A. `ServiceLoader.load(layer.findLoader("p"))` nhận chỉ loader
B. `ServiceLoader.reload(layer, Encoder.class)` chọn module layer
C. `ServiceLoader.load(layer, Encoder.class)` tìm theo layer
D. `ServiceLoader.loadInstalled(layer)` nhận module layer runtime
Đáp án đúng: C

Câu 16. Lời gọi nào trả về boot layer chứa các modules hệ thống khi JVM khởi động?
A. `ModuleLayer.root()` lấy boot layer của JVM mặc định
B. `ModuleLayer.platform()` tạo boot layer từ classpath
C. `ModuleLayer.empty()` trả boot layer của ứng dụng đang chạy
D. `ModuleLayer.boot()` lấy boot module layer của JVM
Đáp án đúng: D

Câu 17. Khi plugin được phân phối thành modular JAR ở một thư mục, API nào có thể tìm module ở đó?
A. `ModuleFinder.of(path)` tìm modules ở vị trí được cho
B. `ClassLoader.getSystemModule(path)` phát hiện modular JAR
C. `ModuleLayer.boot(path)` tải module mới vào boot layer
D. `ServiceLoader.load(path)` tạo danh sách module descriptors
Đáp án đúng: A

Câu 18. Trước khi định nghĩa layer plugin bằng JPMS, đối tượng nào biểu diễn đồ thị module đã resolve?
A. `ModuleDescriptor` chứa class loader cho từng plugin module
B. `ModuleFinder` định nghĩa lớp cho nhóm resolved modules
C. `Configuration` mô tả các module và requires đã resolve
D. `ServiceLoader` chứa dependency graph của JPMS layer
Đáp án đúng: C

Câu 19. Khi muốn các modules plugin trong cùng layer dùng chung một class loader, API nào phù hợp?
A. `ModuleFinder.of` liên kết các modules vào bootstrap
B. `defineModulesWithOneLoader` gán loader chung cho layer
C. `ModuleLayer.boot` cấp loader tùy chỉnh cho layer mới
D. `defineModulesWithManyLoaders` dùng chung loader cho layer
Đáp án đúng: B

Câu 20. Điểm khác của `defineModulesWithManyLoaders` so với phiên bản OneLoader là gì?
A. Mỗi module trong layer mới có ClassLoader riêng
B. Đặt các packages thành exports để gọi chéo module
C. Gán một loader chung cho nhóm module trong layer mới
D. Bỏ kiểm tra dependencies giữa các named modules plugin
Đáp án đúng: A

Câu 21. Trong JPMS, module A cần gọi public API trong module B, điều kiện cơ bản nào cần xét?
A. A chỉ cần cùng `ModuleLayer` với B, không khai báo reads
B. B chỉ cần `opens` package để Java call compile được
C. A đọc B và package API của B đã được export phù hợp
D. A tìm class B bằng ClassLoader mà không cần exports
Đáp án đúng: C

Câu 22. Theo implementation mặc định của `ClassLoader.loadClass`, thứ tự tra cứu class thường là gì?
A. Load class tại boot layer trước rồi bỏ qua parent loader chain
B. Khởi tạo class mới mỗi lần dù parent đã từng trả Class
C. Thử parent loader trước rồi mới tìm tại loader hiện tại
D. Tìm bản local trước, chỉ ủy quyền nếu class được đánh dấu final
Đáp án đúng: C

Câu 23. Hai loader khác nhau thực sự định nghĩa class cùng binary name; JVM phân biệt type bằng gì?
A. Thứ tự tải class của các thread trong JVM process
B. Chỉ tên package và checksum của bytecode class
C. Chỉ tên class vì JVM hợp nhất type có tên giống nhau
D. Binary name và defining ClassLoader tạo thành class identity
Đáp án đúng: D

Câu 24. Plugin object implements SPI nhưng host ép kiểu thất bại dù tên interface trùng nhau; nguyên nhân nào có thể là gì?
A. SPI có default method nên JDK không hỗ trợ ép kiểu runtime
B. SPI không nằm trong boot layer dù cùng ClassLoader
C. Hai loaders định nghĩa riêng SPI khiến type identity khác
D. Plugin class được nạp lười và chưa khởi chạy static init
Đáp án đúng: C

Câu 25. Để tránh xung đột type giữa host và plugin, nên đặt SPI classes trong loader nào?
A. Loader cha chung được cả host và plugin dùng để nạp SPI
B. Loader mới tạo cho từng request gọi plugin implementation
C. Loader chỉ tải dependency của plugin không thấy host API
D. Loader riêng của từng plugin để cô lập cả type SPI
Đáp án đúng: A

Câu 26. Nếu hai named modules cùng layer chứa cùng một package, nguy cơ gì cần xử lý?
A. Runtime chuyển cả hai modules về unnamed module để tiếp tục
B. ServiceLoader hợp nhất các classes cùng tên thành một package
C. JVM đổi package name của module thứ hai để tránh xung đột
D. Xung đột split package trong JPMS resolution/layer creation
Đáp án đúng: D

Câu 27. Một plugin phụ thuộc thư viện không nằm trong module graph được resolve, vấn đề gì có thể xuất hiện?
A. Resolution fail hoặc thiếu class khi chạy plugin
B. ServiceLoader tự tải các JAR từ Maven Central lúc startup
C. Java compiler tự nhúng thư viện còn thiếu vào modular JAR
D. Plugin dùng dependency của host mà không cần API đọc
Đáp án đúng: A

Câu 28. Nếu hai plugin cần hai phiên bản khác nhau của một library, cách thiết kế nào giúp giảm xung đột?
A. Bắt các plugin dùng singleton class loader của boot layer
B. Cô lập dependency bằng loader/layer riêng cho từng plugin
C. Đặt tên jar khác nhau để JVM phân biệt class binary names
D. Đưa cả hai version lên system classpath cùng một package
Đáp án đúng: B

Câu 29. Khi host nâng API plugin từ v1 lên v2, chiến lược nào giảm lỗi liên kết runtime?
A. Ép các plugin nạp bằng bootstrap loader để ổn định API
B. Chỉ đổi tên file plugin mà giữ mã nhị phân và interface
C. Bỏ kiểm thử provider vì SPI interface vẫn có cùng tên
D. Quản lý API version và kiểm tra binary compatibility trước deploy
Đáp án đúng: D

Câu 30. Khi thêm abstract method mới vào SPI interface, plugin cũ chưa triển khai và bị gọi method đó có thể gặp gì?
A. `ClassNotFoundException` vì interface tăng số method
B. `AbstractMethodError` khi implementation chưa có method mới
C. `UnsupportedClassVersionError` vì method abstract không có bytecode
D. `StackOverflowError` do ServiceLoader gọi plugin hai lần
Đáp án đúng: B

Câu 31. Một provider khởi tạo thất bại tại runtime; host mở rộng được nên xử lý thế nào?
A. Xóa các plugin còn lại và cập nhật SPI trong JVM
B. Bỏ qua exception nhưng tiếp tục dùng provider chưa tạo
C. Bắt lỗi provider, ghi log và chuyển sang fallback thích hợp
D. Bắt các request chờ vô hạn cho tới khi provider tạo được
Đáp án đúng: C

Câu 32. Để quản lý vòng đời plugin có tài nguyên, host nên quy định hợp đồng nào?
A. Dựa vào `finalize()` để gọi shutdown sau khi plugin unload
B. Có hook `start`/`stop` hoặc `close` với thứ tự rõ ràng
C. Chỉ một method `execute` và để JVM thu hồi resources
D. Bắt các providers dùng static initializer để mở sockets
Đáp án đúng: B

Câu 33. Khi thay plugin đang phục vụ request, cách cập nhật nào tránh cắt ngang công việc?
A. Đóng class loader cũ trước khi các task đang chạy kết thúc
B. Xóa JAR cũ ngay khi phát hiện version mới tại thư mục
C. Chuyển thread cũ sang bytecode mới giữa lúc đang gọi method
D. Ngừng nhận việc mới, drain in-flight rồi mới stop plugin
Đáp án đúng: D

Câu 34. Plugin tự tạo `ExecutorService` và thread; vì sao cần shutdown trước khi unload?
A. JVM hủy thread khi `ServiceLoader.reload()` được gọi
B. Thread plugin được chuyển sang host thread pool khi reload
C. ExecutorService gắn với GC và tự đóng khi xóa file JAR
D. Thread sống và context loader giữ references tới plugin cũ
Đáp án đúng: D

Câu 35. Khi nào các class và class loader của plugin cũ có cơ hội được unload?
A. Mỗi lần `ServiceLoader.reload()` kết thúc việc duyệt
B. Ngay sau khi `URLClassLoader.close()` trả về thành công
C. Khi loader và classes không còn strong references từ GC roots
D. Ngay sau khi file JAR được thay thế bằng một bản mới
Đáp án đúng: C

Câu 36. Host giữ instance plugin trong singleton static cache; hậu quả nào có thể xảy ra khi hot reload?
A. Cache giữ instance làm class loader cũ chưa được thu hồi
B. Cache ép JVM đổi class identity của provider mới
C. Cache làm service descriptor biến mất khỏi các JAR plugin
D. Cache cấm lời gọi method sau lần reload đầu tiên
Đáp án đúng: A

Câu 37. Tại sao custom ClassLoader không đủ làm ranh giới bảo mật cho plugin không tin cậy?
A. ClassLoader cấp security policy mạnh hơn cô lập process riêng
B. Cô lập tên class không tương đương sandbox quyền hệ thống
C. ClassLoader chỉ tải Java module được đánh dấu trusted
D. ClassLoader tự chặn I/O và network khi plugin không ký số
Đáp án đúng: B

Câu 38. Với plugin tải từ nguồn bên ngoài, bước kiểm soát supply chain nào hữu ích?
A. Kiểm provenance, chữ ký/checksum và phê duyệt quyền triển khai
B. Chỉ kiểm module descriptor có trường `requires` hợp lệ
C. Tin toàn bộ JAR vì JVM verifier kiểm chứng bytecode khi load
D. Chỉ kiểm tên file plugin trùng ID của provider đã đăng ký
Đáp án đúng: A

Câu 39. Một ServiceLoader instance được nhiều thread duyệt và reload đồng thời, biện pháp nào an toàn?
A. Đồng bộ hoặc dùng loader riêng vì ServiceLoader không thread-safe
B. Dùng chung không khóa vì iterator tự đồng bộ nội bộ
C. Chỉ thêm `volatile` cho biến ServiceLoader là đủ an toàn
D. Bật `parallelStream()` trên loader để giải quyết reload race
Đáp án đúng: A

Câu 40. Để kiểm thử hot reload plugin có khác phiên bản dependency, tình huống nào đáng ưu tiên?
A. Chỉ test interface bằng mock không tạo ClassLoader plugin
B. Chỉ đổi tên JAR rồi xác nhận file tồn tại trong thư mục
C. Nạp bằng loader riêng, chạy contract test rồi kiểm cleanup
D. Chỉ kiểm phiên bản JDK trên máy build, bỏ gọi API provider
Đáp án đúng: C
