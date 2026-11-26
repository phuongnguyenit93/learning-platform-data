Bạn giải thích Java Platform Module System (JPMS) xuất hiện từ Java 9 nhằm giải quyết những hạn chế nào của classpath trong ứng dụng lớn?
Bạn mô tả vai trò của `module-info.java` và cách module descriptor khai báo ranh giới phụ thuộc của một thư viện Java như thế nào?
Bạn dùng `requires` để khai báo một module phụ thuộc vào module khác và kiểm tra khả năng đọc module tại thời điểm biên dịch ra sao?
Bạn phân biệt `requires transitive` với `requires` thông thường khi một public API trả về kiểu thuộc module phụ thuộc như thế nào?
Bạn xác định trường hợp phù hợp với `requires static` khi một dependency chỉ cần tại thời điểm biên dịch như thế nào?
Bạn giải thích ý nghĩa của `exports` và vì sao một public class trong package chưa được export vẫn có giới hạn truy cập từ module khác ra sao?
Bạn lựa chọn qualified export để công bố package cho một số module xác định thay vì mọi module như thế nào?
Bạn phân biệt `opens` với `exports` khi một thư viện cần truy cập thành viên không public bằng reflection ra sao?
Bạn phân tích ảnh hưởng của việc khai báo `open module` so với mở có chọn lọc từng package bằng `opens` như thế nào?
Bạn dùng `uses` và `provides ... with` để cấu hình cơ chế service loading giữa các named module ra sao?
Bạn phân biệt cấu hình SPI bằng module descriptor với tệp `META-INF/services` khi chuyển từ classpath sang module path như thế nào?
Bạn thiết kế kiểm thử để xác minh module consumer thực sự tìm được service provider sau khi đóng gói ứng dụng như thế nào?
Bạn giải thích khái niệm module readability và package accessibility, đồng thời phân biệt hai điều kiện khi gặp lỗi truy cập như thế nào?
Bạn xác định module chứa một class tại runtime thông qua `Class.getModule()` và sử dụng thông tin đó khi chẩn đoán lỗi ra sao?
Bạn truy xuất metadata từ `ModuleDescriptor` để kiểm tra tên module, requires, exports và services của một thư viện như thế nào?
Bạn phân biệt named module, automatic module và unnamed module khi một ứng dụng cần trộn thư viện có và không có descriptor ra sao?
Bạn lựa chọn tên module ổn định cho JAR và đánh giá vai trò của `Automatic-Module-Name` trong chiến lược chuyển đổi như thế nào?
Bạn xác định rủi ro khi dựa vào tên automatic module được suy ra từ tên file JAR trong các bản phát hành sau như thế nào?
Bạn giải thích nguyên nhân xung đột split package khi hai module cung cấp cùng một package và đề xuất cách tổ chức lại ra sao?
Bạn thiết kế quá trình chuyển đổi một ứng dụng lớn từ classpath sang module path theo từng bước mà không thay đổi toàn bộ thư viện cùng lúc như thế nào?
Bạn phân biệt cách chương trình trên classpath truy cập các public API của named module với cách named module khai báo dependency như thế nào?
Bạn kiểm tra vì sao một thư viện chạy trên classpath nhưng thất bại khi chuyển sang module path dù bytecode không thay đổi ra sao?
Bạn dùng `--module-path` cùng `--module` khi khởi chạy ứng dụng JPMS và so sánh với cách chạy classpath như thế nào?
Bạn xác định cách xây dựng module graph và phân tích lỗi module không được tìm thấy hoặc module không đọc được như thế nào?
Bạn thiết kế module test sao cho kiểm chứng được cả package export và package chỉ open cho công cụ kiểm thử như thế nào?
Bạn chẩn đoán `InaccessibleObjectException` khi framework cố phản chiếu sâu vào package của named module như thế nào?
Bạn đánh giá các tùy chọn `--add-opens` hoặc `--add-exports` như giải pháp chuyển tiếp và lập kế hoạch loại bỏ chúng ra sao?
Bạn phân biệt lỗi do thiếu dependency trên module path với lỗi do package không được export khi đọc stack trace như thế nào?
Bạn dùng `jdeps` để xác định phụ thuộc giữa các module và nhận diện API JDK nội bộ mà thư viện đang sử dụng ra sao?
Bạn xác định cách kiểm tra module JDK nào được ứng dụng thực sự sử dụng trước khi tạo runtime image như thế nào?
Bạn lựa chọn cách tách API module khỏi implementation module để tránh vòng phụ thuộc và giảm ràng buộc giữa các thành phần ra sao?
Bạn thiết kế `ModuleLayer` khi một ứng dụng cần nạp thêm nhóm module ở runtime và kiểm soát class loader của chúng như thế nào?
Bạn đánh giá giới hạn của JPMS trong việc cách ly mã không tin cậy và phân biệt module encapsulation với sandbox bảo mật như thế nào?
Bạn sử dụng `jlink` để tạo runtime image chứa các module bắt buộc của ứng dụng Java trên JDK được hỗ trợ như thế nào?
Bạn giải thích cách dependency graph ảnh hưởng đến các module được đưa vào runtime image do `jlink` tạo ra ra sao?
Bạn lựa chọn module gốc và các tùy chọn `jlink` phù hợp để cân bằng kích thước runtime image với các chức năng cần thiết như thế nào?
Bạn kiểm tra một runtime image do `jlink` tạo ra có đủ provider, charset và tài nguyên cần thiết trước khi phân phối như thế nào?
Bạn xử lý tình huống ứng dụng dùng reflection hoặc service loading khiến một số dependency không được phát hiện chỉ bằng phân tích tĩnh ra sao?
Bạn phân biệt mục đích của `jmod` với JAR thông thường khi đóng gói thành phần dành cho công cụ liên kết runtime như thế nào?
Bạn đánh giá cách build và phân phối runtime image riêng cho từng hệ điều hành mà không giả định image được tạo ra chạy được ở mọi nền tảng ra sao?
Bạn thiết kế kiểm thử khởi động ứng dụng trên runtime image tối giản để phát hiện module bị thiếu khi nâng cấp JDK như thế nào?
Bạn giải thích mục đích của JShell từ Java 9 trong việc thử nghiệm biểu thức, câu lệnh và API Java mà không tạo ứng dụng hoàn chỉnh như thế nào?
Bạn sử dụng JShell để kiểm tra nhanh hợp đồng của một API Collection hoặc Stream trước khi đưa vào mã production ra sao?
Bạn phân biệt snippet khai báo biến, method và class trong JShell với một file Java được biên dịch đầy đủ về vòng đời như thế nào?
Bạn quản lý việc thay thế hoặc xóa snippet trong một phiên JShell để kết quả thử nghiệm không phụ thuộc trạng thái cũ ra sao?
Bạn dùng lệnh JShell để xem kiểu được suy luận và giá trị của một biểu thức trong quá trình khám phá API như thế nào?
Bạn cấu hình classpath hoặc module path cho JShell khi muốn thử một thư viện ngoài JDK như thế nào?
Bạn xử lý kết quả thử nghiệm trong JShell khác môi trường ứng dụng do module access hoặc cấu hình runtime như thế nào?
Bạn lựa chọn API `jdk.jshell.JShell` khi cần nhúng khả năng đánh giá snippet vào một công cụ phát triển với kiểm soát lỗi như thế nào?
Bạn thu thập diagnostics hoặc sự kiện đánh giá từ JShell API để phản hồi lỗi cú pháp cho người dùng như thế nào?
Bạn đánh giá rủi ro thực thi mã Java không tin cậy trong môi trường JShell và vì sao không nên coi REPL là sandbox bảo mật ra sao?
Bạn giải thích các factory `List.of`, `Set.of` và `Map.of` được bổ sung từ Java 9 nhằm cung cấp loại collection nào như thế nào?
Bạn phân biệt collection không thể sửa đổi được tạo bằng `List.of` với danh sách mutable được tạo bằng `new ArrayList<>()` ra sao?
Bạn xác định hành vi của `List.of` khi một phần tử là `null` và thiết kế xác thực dữ liệu đầu vào như thế nào?
Bạn kiểm tra phản ứng của `Set.of` khi các phần tử đầu vào trùng nhau và phân biệt với cách tạo `HashSet` từ dữ liệu trùng ra sao?
Bạn phân biệt điều kiện khóa trùng và giá trị `null` khi xây dựng một `Map.of` chứa cấu hình như thế nào?
Bạn dùng `Map.ofEntries` và `Map.entry` khi danh sách cặp khóa-giá trị dài hơn số đối số tiện lợi của `Map.of` ra sao?
Bạn giải thích vì sao không nên phụ thuộc vào thứ tự duyệt của `Set.of` hoặc `Map.of` trong một giao thức có thứ tự ổn định như thế nào?
Bạn kiểm thử hành vi `UnsupportedOperationException` khi code cũ cố thêm, xóa hoặc thay phần tử trong collection được tạo bằng factory Java 9 ra sao?
Bạn phân biệt cấu trúc không thể chỉnh sửa với tính bất biến sâu khi một `List.of` chứa các đối tượng mutable như thế nào?
Bạn xác định vì sao một collection tạo bởi factory Java 9 không nên được so sánh bằng identity để suy ra giá trị nghiệp vụ ra sao?
Bạn lựa chọn tạo collection không thể sửa đổi hay một collection có thể chỉnh sửa theo hợp đồng của public API như thế nào?
Bạn so sánh `List.of` với `Collections.unmodifiableList` khi một nguồn danh sách mutable có thể thay đổi sau khi wrapper được tạo ra ra sao?
Bạn xác định khi nào nên dùng `List.copyOf` trên JDK hiện đại và phân biệt nó với các factory `of` đã có ở Java 9 như thế nào?
Bạn xây dựng kiểm thử kết quả collection factory với dữ liệu rỗng, một phần tử và nhiều phần tử theo yêu cầu nghiệp vụ ra sao?
Bạn đánh giá tác động của value-based collection tới việc sử dụng khóa Map hoặc cache và quyết định tránh những giả định identity nào?
Bạn giải thích `Stream.takeWhile` được bổ sung ở Java 9 xử lý phần đầu liên tiếp của một ordered stream như thế nào?
Bạn phân biệt `takeWhile` với `filter` khi điều kiện chuyển từ đúng sang sai giữa một dãy dữ liệu có thứ tự ra sao?
Bạn xác định tác động của `takeWhile` đối với unordered stream khi không thể giả định một prefix theo thứ tự gặp như thế nào?
Bạn sử dụng `Stream.dropWhile` để bỏ một đoạn đầu thỏa điều kiện mà vẫn giữ phần còn lại của stream như thế nào?
Bạn so sánh `dropWhile` với `skip` khi số lượng phần tử cần bỏ phụ thuộc vào predicate thay vì số cố định ra sao?
Bạn thiết kế kiểm thử biên cho `takeWhile` và `dropWhile` trên stream rỗng, tất cả phần tử đúng và tất cả phần tử sai ra sao?
Bạn giải thích mục đích của `Stream.ofNullable` khi một hàm có thể trả về đối tượng hoặc `null` như thế nào?
Bạn sử dụng `Stream.ofNullable` với `flatMap` để loại các kết quả không tồn tại mà không đưa `null` vào pipeline ra sao?
Bạn lựa chọn overload `Stream.iterate(seed, hasNext, next)` khi cần dãy hữu hạn và phân biệt với dạng iterate không có điều kiện kết thúc ra sao?
Bạn kiểm chứng điều kiện dừng của `Stream.iterate` để tránh vòng sinh phần tử vô hạn khi thay đổi bước chuyển trạng thái như thế nào?
Bạn phân biệt encounter order và xử lý song song khi áp dụng các thao tác phụ thuộc prefix lên Stream như thế nào?
Bạn đánh giá chi phí của `takeWhile` hoặc `dropWhile` trên parallel ordered stream lớn so với vòng lặp tuần tự ra sao?
Bạn dùng `Optional.stream` để tích hợp các giá trị Optional trong pipeline Stream mà không thao tác thủ công `isPresent` như thế nào?
Bạn phân biệt `Optional.ifPresentOrElse` với `ifPresent` khi cần hành vi rõ ràng cho cả giá trị có và không có ra sao?
Bạn sử dụng `Optional.or` để cung cấp Optional dự phòng được tạo lười và phân biệt với `orElse` như thế nào?
Bạn xác định khi nào nên dùng `Optional.orElseThrow()` không đối số trên JDK mới và kiểm tra phiên bản API so với Java 9 như thế nào?
Bạn thiết kế một pipeline kết hợp `Optional.stream`, `flatMap` và factory collection mà vẫn tránh null và side effect không mong đợi như thế nào?
Bạn phân biệt `Collectors.filtering` với gọi `filter` trước khi thu thập bằng `groupingBy` đối với nhóm có thể nhận kết quả rỗng như thế nào?
Bạn dùng `Collectors.flatMapping` để gom các tập phần tử con trong `groupingBy` mà không phải tạo collection trung gian như thế nào?
Bạn xây dựng kiểm thử cho `Collectors.flatMapping` khi các phần tử nguồn không có phần tử con hoặc stream con cần đóng ra sao?
Bạn giải thích vai trò của `Flow.Publisher`, `Flow.Subscriber`, `Flow.Subscription` và `Flow.Processor` trong mô hình Reactive Streams như thế nào?
Bạn thiết kế một Subscriber quản lý vòng đời `onSubscribe`, `onNext`, `onError` và `onComplete` theo đúng hợp đồng như thế nào?
Bạn sử dụng `Flow.Subscription.request(n)` để điều chỉnh demand và ngăn producer đẩy dữ liệu nhanh hơn consumer xử lý ra sao?
Bạn giải thích backpressure khác với việc đơn thuần tăng số lượng thread hoặc tăng kích thước queue trong một luồng sự kiện như thế nào?
Bạn phân tích điều gì xảy ra khi Subscriber yêu cầu số phần tử không hợp lệ hoặc gọi `cancel` trong lúc Publisher đang phát dữ liệu như thế nào?
Bạn lựa chọn `SubmissionPublisher` khi cần một Publisher đơn giản và kiểm soát khả năng chặn khi buffer đầy ra sao?
Bạn đánh giá rủi ro khi dùng `SubmissionPublisher.submit` từ thread nhạy độ trễ nếu Subscriber xử lý chậm như thế nào?
Bạn phân biệt các kết quả từ `SubmissionPublisher.offer` với việc chắc chắn một phần tử đã được xử lý thành công như thế nào?
Bạn kiểm tra việc đóng Publisher bình thường và đóng với exception ảnh hưởng tới callback của Subscriber ra sao?
Bạn thiết kế Processor nhận dữ liệu, biến đổi và phát cho Subscriber tiếp theo mà vẫn truyền tín hiệu lỗi và demand như thế nào?
Bạn kiểm thử mô hình Flow khi Subscriber hủy subscription, xử lý chậm hoặc ném lỗi trong callback như thế nào?
Bạn phân biệt Java `Flow` API với một thư viện reactive chuyên dụng về mức trừu tượng, scheduler và các toán tử có sẵn ra sao?
Bạn xác định cách kết nối nguồn dữ liệu bất đồng bộ dùng Flow với mã đồng bộ mà không làm mất khả năng giới hạn demand như thế nào?
Bạn sử dụng `CompletableFuture.orTimeout` để giới hạn thời gian chờ của một phép tính bất đồng bộ và xử lý kết quả lỗi ra sao?
Bạn phân biệt `CompletableFuture.completeOnTimeout` với `orTimeout` về giá trị hoàn tất và trạng thái exception như thế nào?
Bạn đánh giá vì sao một `CompletableFuture` đã hoàn tất do timeout không đồng nghĩa tác vụ đang chạy bên dưới được hủy ngay lập tức ra sao?
Bạn sử dụng `CompletableFuture.delayedExecutor` để lên lịch tiếp tục tác vụ và quản lý tài nguyên executor như thế nào?
Bạn lựa chọn cách kết hợp nhiều `CompletableFuture` và chính sách dừng khi một tác vụ lỗi để tránh bỏ qua kết quả lỗi ra sao?
Bạn giải thích ý nghĩa của `VarHandle` được chuẩn hóa từ Java 9 và các hình thức truy cập biến mà nó cung cấp như thế nào?
Bạn phân biệt plain, opaque, acquire/release và volatile access mode của `VarHandle` theo yêu cầu thứ tự bộ nhớ ra sao?
Bạn sử dụng `MethodHandles.lookup` hoặc `privateLookupIn` để lấy quyền truy cập hợp lệ tới một field và xây dựng `VarHandle` như thế nào?
Bạn đánh giá vì sao `VarHandle` là lựa chọn phù hợp hơn truy cập API bộ nhớ nội bộ không được hỗ trợ trong nhiều thuật toán đồng thời ra sao?
Bạn dùng `VarHandle.compareAndSet` để cập nhật trạng thái atomically và kiểm tra tính đúng đắn khi nhiều thread cạnh tranh như thế nào?
Bạn phân biệt thao tác `getAndAdd` của `VarHandle` với chuỗi đọc rồi ghi không nguyên tử khi cập nhật bộ đếm ra sao?
Bạn kiểm tra kiểu tọa độ và kiểu giá trị của một `VarHandle` trước khi gọi các access mode để tránh lỗi signature như thế nào?
Bạn thiết kế kiểm thử race condition khi thay một vùng mã đồng thời dựa vào `synchronized` bằng `VarHandle` như thế nào?
Bạn giải thích cú pháp try-with-resources được mở rộng ở Java 9 cho biến đã tồn tại và điều kiện biến phải final hoặc effectively final như thế nào?
Bạn sử dụng một resource đã được khởi tạo trước trong try-with-resources mà vẫn giữ đúng quy tắc sở hữu và đóng tài nguyên như thế nào?
Bạn phân biệt ngoại lệ phát sinh trong thân `try` với suppressed exception khi đóng resource ở cấu trúc try-with-resources như thế nào?
Bạn kiểm tra ảnh hưởng khi resource được mượn từ caller nhưng try-with-resources lại đóng resource đó trước khi caller sử dụng xong ra sao?
Bạn giải thích tác dụng của private method trong interface từ Java 9 khi cần chia sẻ logic giữa các default method như thế nào?
Bạn phân biệt private instance method và private static method trong interface về cách được gọi và khả năng truy cập như thế nào?
Bạn thiết kế kiểm thử bảo đảm refactor logic lặp sang private interface method không làm thay đổi contract của default method ra sao?
Bạn giải thích sự cải tiến toán tử diamond với anonymous class trong Java 9 và kiểm tra giới hạn của kiểu suy luận như thế nào?
Bạn đánh giá khi nào nên dùng anonymous class với diamond và khi nào lambda giúp mã nguồn rõ ràng hơn trong Java hiện đại ra sao?
Bạn sử dụng `ProcessHandle.current()` để lấy thông tin tiến trình Java hiện tại mà không phụ thuộc API hệ điều hành cụ thể như thế nào?
Bạn truy xuất PID, command, arguments hoặc start time từ `ProcessHandle.Info` và xử lý dữ liệu tùy chọn thiếu như thế nào?
Bạn phân biệt thông tin tiến trình JVM hiện tại với các tiến trình con được tạo bởi `ProcessBuilder` khi giám sát ứng dụng ra sao?
Bạn sử dụng `ProcessHandle.descendants()` để phát hiện các tiến trình con và đánh giá tính không nguyên tử của snapshot tiến trình như thế nào?
Bạn xác định điều kiện kiểm tra `ProcessHandle.isAlive()` khi một tiến trình có thể kết thúc giữa hai lần quan sát như thế nào?
Bạn dùng `Process.onExit()` hoặc `ProcessHandle.onExit()` để xử lý sự kiện kết thúc tiến trình mà không chặn một thread vô hạn như thế nào?
Bạn phân biệt `destroy` với `destroyForcibly` khi dừng tiến trình và tổ chức chính sách timeout hoặc cleanup ra sao?
Bạn giải thích vì sao khả năng kết thúc tiến trình hoặc đọc metadata tiến trình phụ thuộc quyền của hệ điều hành như thế nào?
Bạn xây dựng kiểm thử tạo và dừng tiến trình con bằng `ProcessBuilder` sao cho không để sót process sau khi test thất bại ra sao?
Bạn giải thích vì sao `StackWalker` từ Java 9 phù hợp để truy vấn call stack có kiểm soát thay vì luôn tạo stack trace đầy đủ như thế nào?
Bạn dùng `StackWalker.walk` để lọc frame thuộc một package ứng dụng khi xây dựng thông tin chẩn đoán như thế nào?
Bạn phân biệt việc chỉ lấy class name với tùy chọn `RETAIN_CLASS_REFERENCE` khi cần đối tượng `Class` của stack frame như thế nào?
Bạn giải thích vai trò của tùy chọn hiển thị các hidden frame khi phân tích call stack có lambda hoặc framework runtime như thế nào?
Bạn đánh giá chi phí của việc quan sát stack trong hot path và chọn cách giảm tần suất thu thập như thế nào?
Bạn xử lý khác biệt giữa tên method, tên class và số dòng trong stack trace khi chương trình được tối ưu hoặc thiếu debug information như thế nào?
Bạn dùng `Cleaner` được giới thiệu từ Java 9 làm cơ chế dọn dẹp dự phòng và giải thích vì sao không thay thế đóng tài nguyên tường minh như thế nào?
Bạn thiết kế clean-up action để tránh giữ tham chiếu mạnh tới đối tượng được đăng ký khiến tài nguyên không thể được thu hồi ra sao?
Bạn so sánh cơ chế đăng ký `Cleaner` với `AutoCloseable` và xác định khi nào cần kết hợp cả hai như thế nào?
Bạn giải thích mặc định G1 GC từ Java 9 và lý do không nên chọn collector chỉ dựa vào giá trị mặc định lịch sử như thế nào?
Bạn sử dụng Unified JVM Logging với `-Xlog` để thu thập dữ liệu GC, class loading hoặc safepoint theo mục tiêu chẩn đoán ra sao?
Bạn phân biệt cấu hình tag và level của Unified Logging khi muốn giới hạn log mà vẫn đủ thông tin kiểm tra sự cố như thế nào?
Bạn thiết kế chiến lược đánh giá tác động của cấu hình GC và logging sau khi nâng cấp JDK bằng latency, throughput và CPU như thế nào?
Bạn phân biệt Compact Strings của Java 9 với thay đổi biểu diễn Unicode của `String` ở cấp API công khai như thế nào?
Bạn đánh giá vì sao cải tiến String Concat dựa trên `invokedynamic` không đồng nghĩa mọi phép nối chuỗi có hiệu năng tốt trong mọi vòng lặp như thế nào?
Bạn giải thích cải tiến hỗ trợ UTF-8 cho resource bundle từ Java 9 và cách kiểm chứng đường xử lý ký tự trên các JDK mới như thế nào?
Bạn đánh giá lợi ích của multi-release JAR từ Java 9 khi một thư viện cần cung cấp implementation tối ưu theo phiên bản JDK như thế nào?
Bạn phân biệt phiên bản class cơ sở với class nằm dưới `META-INF/versions` của multi-release JAR khi runtime lựa chọn class như thế nào?
Bạn kiểm thử multi-release JAR trên các JDK được hỗ trợ để bảo đảm public API không thay đổi không tương thích như thế nào?
Bạn xác định nguy cơ build tool không xử lý đúng multi-release JAR khi đóng gói shaded JAR hoặc chạy công cụ phân tích tĩnh ra sao?
Bạn phân biệt `ObjectInputFilter` từ Java 9 với việc deserialize Java object không có giới hạn và tổ chức chính sách lọc an toàn như thế nào?
Bạn sử dụng cơ chế serialization filter hiện còn được hỗ trợ để hạn chế loại đối tượng, chiều sâu hoặc kích thước đồ thị khi nhận dữ liệu không tin cậy ra sao?
Bạn thiết kế kế hoạch chuyển định dạng truyền dữ liệu khỏi Java native serialization khi hệ thống cần hợp đồng schema rõ ràng như thế nào?
Bạn kiểm tra tính tương thích khi một library Java 9 chạy trên JDK mới có module encapsulation mạnh hơn và API nội bộ bị hạn chế ra sao?
Bạn dùng `javac --release` trên JDK hiện đại để xác minh cú pháp và API đúng với phiên bản Java tối thiểu của thư viện như thế nào?
Bạn phân biệt những tính năng chính thức của Java 9 với API HTTP Client từng ở incubator và chỉ trở thành chuẩn ở JDK sau như thế nào?
Bạn xây dựng ma trận hồi quy cho JPMS, `ServiceLoader`, JAR packaging, charset và reflection khi di chuyển ứng dụng từ Java 8 lên JDK hiện đại như thế nào?
Bạn thiết kế tiêu chí chọn dùng các đóng góp lâu dài của Java 9 dựa trên hợp đồng API, giới hạn tương thích, hiệu năng và chi phí bảo trì như thế nào?
