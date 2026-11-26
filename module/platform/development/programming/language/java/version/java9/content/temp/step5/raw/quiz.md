Câu 1: Trong ứng dụng Java có module rõ ràng, file nào khai báo tên module và các chỉ thị phụ thuộc?
A. module-info.java khai báo tên module, requires và exports.
B. MANIFEST.MF mô tả mọi package export và module cần đọc khi compile.
C. package-info.java mô tả module path và các module được phép nạp.
D. settings.xml chỉ định module cần đọc cùng tất cả package mở.
Đáp án đúng: A

Câu 2: Trong module-info.java, chỉ thị requires module khác chủ yếu mang ý nghĩa nào?
A. Mở tất cả package riêng tư của module phụ thuộc cho reflection.
B. Gộp toàn bộ class của module phụ thuộc vào JAR đang được build.
C. Chỉ định module phụ thuộc phải chạy trong một JVM độc lập.
D. Khai báo module cần đọc để truy cập API được export thích hợp.
Đáp án đúng: D

Câu 3: Lệnh exports một package từ named module cho phép điều gì với module đọc nó?
A. Dùng reflection vào mọi private field của type trong package đó.
B. Tự động dùng mọi package không export của cùng module cung cấp.
C. Cho phép import các public type thuộc package được export.
D. Truy cập tất cả class của package dù chúng không public.
Đáp án đúng: C

Câu 4: Chỉ thị opens package trong module-info.java nhắm tới nhu cầu nào?
A. Cho phép mọi module biên dịch import private type trực tiếp.
B. Biến tất cả method trong package thành public ở runtime.
C. Yêu cầu các class trong package chỉ được tải từ classpath.
D. Cho phép deep reflection ở runtime vào package được mở.
Đáp án đúng: D

Câu 5: requires transitive được dùng khi module A muốn gì đối với module đọc A?
A. Cho module đọc A đọc thêm module dependency được A truyền tiếp.
B. Bắt mọi module phụ thuộc A phải export tất cả package nội bộ.
C. Tự đóng gói bytecode của dependency vào runtime image của A.
D. Bảo đảm dependency được nạp trên classpath thay vì module path.
Đáp án đúng: A

Câu 6: Chỉ thị exports api.pkg to partner.mod mang ý nghĩa gì?
A. Chỉ cho phép các class trong cùng package gọi public API.
B. Chỉ export package đó cho các named module được nêu rõ.
C. Chỉ cấp quyền reflection tới private field của package đó.
D. Chỉ định package phải được đóng trong một module JDK chuẩn.
Đáp án đúng: B

Câu 7: Khi consumer dùng ServiceLoader, chỉ thị uses trong module-info giúp làm gì?
A. Đăng ký implementation của dịch vụ vào classpath của consumer.
B. Export toàn bộ package chứa interface tới mọi module ngoài.
C. Bắt consumer tạo một implementation bằng constructor phản chiếu.
D. Khai báo module có nhu cầu sử dụng một giao diện dịch vụ.
Đáp án đúng: D

Câu 8: Một module cung cấp implementation cho ServiceLoader khai báo thế nào?
A. Dùng requires transitive tới implementation của tất cả dịch vụ.
B. Dùng opens module-info.java to ConsumerModule trong descriptor.
C. Dùng exports implementation.pkg to java.base trong descriptor.
D. Dùng provides ServiceType with ImplementationType trong descriptor.
Đáp án đúng: D

Câu 9: Với class nằm trên classpath truyền thống, mô tả JPMS nào phù hợp?
A. Mỗi JAR trên classpath tự trở thành một explicit named module.
B. Mọi package trên classpath mặc định được ẩn khỏi unnamed module.
C. Class được đưa vào unnamed module của class loader tương ứng.
D. module-info.java của JDK tự thêm requires cho mọi classpath JAR.
Đáp án đúng: C

Câu 10: Đặt JAR thường không có module-info lên module path tạo ra điều gì?
A. Nó bắt buộc trở thành unnamed module dù nằm trên module path.
B. JAR có thể được xem là automatic module khi nằm trên module path.
C. Nó tự chuyển bytecode thành explicit module descriptor khi build.
D. Nó bị Java launcher từ chối chỉ vì thiếu module-info.java.
Đáp án đúng: B

Câu 11: Hai named module chứa cùng một package trong đồ thị module gây rủi ro nào?
A. JVM tự trộn package và chọn class ở JAR có version cao hơn.
B. Split package có thể làm cấu hình JPMS không resolve hợp lệ.
C. Module nào khai báo trước sẽ tự động export cả hai tập class.
D. Package được JVM gắn thành unnamed module để tránh xung đột.
Đáp án đúng: B

Câu 12: Khi chạy ứng dụng dạng named module, tùy chọn nào chỉ định nơi tìm module?
A. --module-path khai báo các đường dẫn chứa module khi launch.
B. --class-path tự biến mọi JAR vào explicit module của ứng dụng.
C. --source-path bắt runtime đọc module dependency từ source Java.
D. --upgrade-path luôn thay thế module-info của tất cả thư viện.
Đáp án đúng: A

Câu 13: requires static trong JPMS thể hiện loại phụ thuộc nào?
A. Phụ thuộc chỉ cần ở runtime, compiler không cần nhìn thấy API.
B. Phụ thuộc được phép gọi private API mà không cần opens package.
C. Cần lúc biên dịch, nhưng module đó có thể vắng mặt lúc chạy.
D. Phụ thuộc luôn được đóng vào custom runtime khi chạy jlink.
Đáp án đúng: C

Câu 14: Một thư viện có public API cần được import bình thường và reflection vào private member; cấu hình nào đúng?
A. Chỉ requires trong consumer là đủ để truy cập mọi private member.
B. Chỉ opens package là đủ để compile import mọi public type.
C. Kết hợp exports cho import và opens cho deep reflection.
D. Chỉ thêm library vào classpath sẽ sửa descriptor named module.
Đáp án đúng: C

Câu 15: Vì sao một named module không thể mặc định import mọi type từ module khác?
A. Cần đọc được module và package tương ứng phải được export.
B. Một named module bắt buộc nạp mọi package qua ServiceLoader.
C. JPMS chỉ cho phép public type nằm trong java.base được import.
D. Mọi method của module khác đều phải gọi bằng reflection.
Đáp án đúng: A

Câu 16: Khi jdeps phân tích phụ thuộc bytecode, giới hạn nào cần ghi nhớ?
A. jdeps tự chạy toàn bộ test nên tìm được mọi dependency động.
B. Không tự tìm đủ các dependency chỉ được tải bằng reflection.
C. jdeps tự tải các ServiceLoader provider lúc phân tích mã.
D. jdeps thay thế được kiểm thử runtime của tất cả plugin.
Đáp án đúng: B

Câu 17: jlink dùng để tạo loại artifact nào từ các module đã chọn?
A. Uber JAR chứa tất cả class ứng dụng đã được làm phẳng.
B. Tệp bytecode duy nhất không cần thư viện native của JVM.
C. File cài đặt hệ điều hành có giao diện đồ họa tùy chọn.
D. Runtime image gồm các module Java cần chạy ứng dụng.
Đáp án đúng: D

Câu 18: Khi phân phối runtime image do jlink tạo ra, điểm tương thích nào quan trọng?
A. Image luôn chạy được trên mọi OS nếu bytecode hợp lệ.
B. Image bắt buộc có compiler javac để chạy ứng dụng.
C. Image chỉ chứa module của ứng dụng, không có module JDK.
D. Image thường gắn với hệ điều hành và kiến trúc đích.
Đáp án đúng: D

Câu 19: Điều gì cần lưu ý khi muốn đưa automatic module vào image của jlink?
A. jlink từ chối liên kết trực tiếp JAR thuộc loại automatic module.
B. jlink tự sinh module-info đầy đủ và liên kết không cần kiểm tra.
C. Automatic module được đưa vào image bất kể tùy chọn --add-modules.
D. Chỉ cần đổi đuôi JAR thành JMOD là module đã explicit.
Đáp án đúng: A

Câu 20: Trong jlink, tùy chọn --add-modules dùng để chỉ định điều gì?
A. Các package cần cho phép reflection từ mọi module ở runtime.
B. Các thư mục chứa file nguồn dùng để javac biên dịch lại.
C. Module gốc cần đưa vào image cùng dependency cần thiết.
D. Các ServiceLoader provider phải được chạy lúc tạo image.
Đáp án đúng: C

Câu 21: Tùy chọn --launcher của jlink đáp ứng mục đích nào?
A. Tạo module-info.java cho JAR vẫn nằm trên classpath.
B. Tạo bản sao portable của launcher cho mọi hệ điều hành.
C. Sinh lệnh chạy main class của module trong image.
D. Tạo bản ghi dependency động trong lần đầu ứng dụng chạy.
Đáp án đúng: C

Câu 22: jdeps với --print-module-deps hỗ trợ công việc nào?
A. Liệt kê dependency module để cân nhắc cấu hình jlink.
B. Chạy reflection test rồi xác nhận toàn bộ service binding.
C. Tự chuyển classpath JAR thành named module có descriptor.
D. Thay thế việc biên dịch lại mã nguồn khi nâng phiên bản.
Đáp án đúng: A

Câu 23: JShell hỗ trợ hoạt động phát triển nào thuận tiện nhất?
A. Đóng gói các module Java thành image runtime nhỏ theo yêu cầu.
B. Thử snippet Java qua phiên tương tác không cần class main.
C. Tự đổi runtime JDK để phù hợp bytecode của mọi project.
D. Kiểm thử tải tự động với cùng ngữ cảnh của production service.
Đáp án đúng: B

Câu 24: Trong JShell, lệnh /vars giúp người dùng quan sát điều gì?
A. Danh sách tất cả biến môi trường của tiến trình JVM chủ.
B. Xem biến được khai báo trong phiên JShell hiện tại.
C. Các field private của mọi class nằm trên module path.
D. Danh sách file thuộc tính mà chương trình tự động đọc.
Đáp án đúng: B

Câu 25: Trong JShell, lệnh /reset có tác dụng nào lên session?
A. Ghi toàn bộ snippet hiện tại thành JAR chạy độc lập.
B. Đổi mọi biến đã nhập về null nhưng giữ method và import.
C. Xóa trạng thái snippet để bắt đầu lại phiên JShell.
D. Xóa cache module của hệ điều hành rồi khởi động JVM.
Đáp án đúng: C

Câu 26: Lệnh /save trong JShell được dùng cho nhu cầu nào?
A. Lưu một runtime image tùy biến giống công cụ jlink.
B. Tạo file class đã ký số và cài vào module path.
C. Lưu heap dump của JVM khi đoạn snippet gặp exception.
D. Lưu các snippet của phiên vào file để tái sử dụng.
Đáp án đúng: D

Câu 27: Muốn JShell thử một API trong JAR bên ngoài, cách nào phù hợp?
A. Đặt JAR vào thư mục chứa file javac.exe là đủ.
B. Cung cấp dependency trên classpath cho phiên JShell.
C. Chỉ gọi /reset để JShell tự tìm dependency trên mạng.
D. Tạo một Package-private class để thay toàn bộ JAR.
Đáp án đúng: B

Câu 28: Vì sao không nên dùng JShell session thay thế bộ kiểm thử hồi quy?
A. JShell chỉ hỗ trợ cú pháp Java 9 mà không chạy được code mới.
B. Mọi snippet bắt buộc chạy dưới Java compiler của môi trường CI.
C. JShell luôn ghi lại đầy đủ input và assertion trong JAR test.
D. Snippet trong JShell không thay được kiểm thử hồi quy ứng dụng.
Đáp án đúng: D

Câu 29: Để kích hoạt khả năng multi-release JAR, manifest cần metadata nào?
A. Khai báo Multi-Release: true trong manifest của JAR.
B. Khai báo Automatic-Module-Name: true cho mọi class versioned.
C. Khai báo Class-Path: 9 để runtime tự thay bytecode gốc.
D. Khai báo Sealed: false rồi JVM tự chọn mọi version class.
Đáp án đúng: A

Câu 30: Trong multi-release JAR, lớp dành riêng cho Java 9 thường đặt ở vị trí nào?
A. Bên dưới META-INF/versions/9 theo tên package tương ứng.
B. Bên dưới META-INF/services/9 và nạp qua ServiceLoader.
C. Bên dưới module-info.java/versions/9 rồi tự biên dịch.
D. Bên dưới root/9/classes và nạp bằng extension classloader.
Đáp án đúng: A

Câu 31: Private method trong Java interface từ Java 9 chủ yếu giúp gì?
A. Cho implementer gọi private method như public API mặc định.
B. Thay thế mọi method abstract bằng instance method của Object.
C. Tái dùng logic riêng của interface giữa default và static method.
D. Biến interface thành class chứa instance field mutable.
Đáp án đúng: C

Câu 32: API nào từ Java 9 giúp lấy handle của tiến trình Java hiện tại?
A. Runtime.getRuntime().handle() lấy ProcessHandle khi cần.
B. ProcessHandle.current() lấy handle tiến trình hiện tại.
C. ProcessBuilder.current() trả ProcessHandle của JVM đang chạy.
D. Thread.currentThread().toHandle() trả handle của tiến trình.
Đáp án đúng: B

Câu 33: Lời gọi List.of tạo collection có hợp đồng thay đổi phần tử thế nào?
A. Cho phép set nhưng từ chối add và remove với mọi kiểu phần tử.
B. Cho phép add nếu kích thước mới vẫn dưới giới hạn mặc định.
C. Cho phép sửa list sau khi chuyển sang Iterator từ nguồn.
D. Không hỗ trợ thao tác thêm, xóa hay thay phần tử qua List.
Đáp án đúng: D

Câu 34: Điều gì xảy ra khi truyền một phần tử null vào List.of?
A. Tạo list hợp lệ rồi bỏ phần tử null khi bắt đầu duyệt.
B. Ném NullPointerException khi tạo list với phần tử null.
C. Thay null bằng Optional.empty trước khi trả về danh sách.
D. Trả một list chỉ chứa phần tử null và không thể sửa.
Đáp án đúng: B

Câu 35: Set.of nhận các phần tử trùng nhau theo equals sẽ xử lý thế nào?
A. Giữ bản đầu và bỏ các phần tử trùng một cách im lặng.
B. Giữ bản cuối và ghi đè các phần tử có cùng hashCode.
C. Ném IllegalArgumentException trong lúc tạo tập hợp.
D. Chuyển thành List để bảo toàn tất cả phần tử lặp.
Đáp án đúng: C

Câu 36: Map.of nhận hai entry có cùng key theo equals; kết quả nào phù hợp?
A. Giữ value cuối với cùng key như thao tác Map.put.
B. Giữ value đầu và loại entry sau khi khởi tạo.
C. Tạo hai entry khác nhau nếu giá trị value không trùng.
D. Ném IllegalArgumentException vì key được đưa vào trùng.
Đáp án đúng: D

Câu 37: Khi dùng List.of với các phần tử khác nhau, đặc tính thứ tự nào đúng?
A. List tự sắp xếp phần tử theo thứ tự tự nhiên nếu có.
B. List phát lại thứ tự tùy theo hashCode của phần tử.
C. List bỏ thứ tự khi Iterator được dùng để duyệt.
D. List giữ thứ tự phần tử theo thứ tự đối số truyền vào.
Đáp án đúng: D

Câu 38: Tại sao không nên dựa vào thứ tự duyệt của Set.of?
A. Thứ tự lặp không được API bảo đảm ổn định.
B. Set.of cam kết thứ tự chèn giống LinkedHashSet.
C. Set.of luôn sắp xếp theo Comparable của phần tử.
D. Set.of cam kết thứ tự tăng dần của hashCode.
Đáp án đúng: A

Câu 39: Cần tạo immutable-map factory với số entry nhiều hơn overload Map.of; nên dùng gì?
A. Map.ofEntries nhận các Map.entry để tạo map nhiều cặp.
B. Map.of cho phép truyền vô hạn key-value qua varargs.
C. Map.putAll tạo map không thể sửa từ mọi nguồn đầu vào.
D. Collections.singletonMap nhận danh sách entry tùy ý.
Đáp án đúng: A

Câu 40: Vì sao List.of chứa một object mutable không tạo bất biến sâu?
A. Factory tự chuyển object mutable thành bản sao immutable.
B. Tất cả field của object bị chuyển final khi đưa vào list.
C. Tham chiếu phần tử giữ nguyên nên trạng thái object vẫn có thể đổi.
D. JVM tạo deep copy cho từng phần tử và đóng băng trạng thái.
Đáp án đúng: C

Câu 41: Với Stream đã có encounter order, takeWhile(predicate) thực hiện điều gì?
A. Lọc tất cả phần tử thỏa điều kiện, kể cả sau phần tử không đạt.
B. Lấy hậu tố bắt đầu từ phần tử đầu tiên không thỏa điều kiện.
C. Lấy tối đa một phần tử thỏa predicate rồi kết thúc Stream.
D. Lấy prefix liên tục cho đến phần tử đầu không thỏa predicate.
Đáp án đúng: D

Câu 42: Với Stream có thứ tự, dropWhile(predicate) xử lý phần đầu thế nào?
A. Loại mọi phần tử thỏa điều kiện dù xuất hiện sau phần tử sai.
B. Chỉ giữ prefix thỏa điều kiện rồi loại những phần tử sau.
C. Bỏ prefix liên tục đang thỏa điều kiện rồi giữ phần còn lại.
D. Sắp phần tử không thỏa lên trước rồi mới tạo Stream kết quả.
Đáp án đúng: C

Câu 43: Stream.ofNullable(x) cho kết quả nào khi x là null?
A. Tạo Stream có đúng một phần tử mang giá trị null.
B. Tạo một Stream rỗng không chứa phần tử nào.
C. Ném IllegalArgumentException vì Stream cấm mọi null.
D. Chuyển null thành Optional.empty làm phần tử Stream.
Đáp án đúng: B

Câu 44: Phiên bản Stream.iterate(seed, hasNext, next) có ích trong trường hợp nào?
A. Tự chạy mọi bước trên thread riêng bằng ForkJoinPool.
B. Sinh Stream với điều kiện dừng được kiểm tra theo bước.
C. Tự dừng ngay khi tập dữ liệu đầu vào gặp giá trị null.
D. Chỉ cho phép tạo một phần tử từ seed rồi kết thúc.
Đáp án đúng: B

Câu 45: Optional.ifPresentOrElse nhận hai nhánh để xử lý trường hợp nào?
A. Có giá trị chạy Runnable, rỗng chạy Consumer.
B. Luôn chạy cả hai callback nhưng trả về kết quả khác.
C. Có giá trị chạy Consumer, rỗng chạy Runnable.
D. Có giá trị trả Optional mới, rỗng ném exception.
Đáp án đúng: C

Câu 46: Optional.or(supplier) hoạt động thế nào khi Optional hiện tại rỗng?
A. Gọi supplier để trả về một Optional khác khi rỗng.
B. Gọi supplier trả giá trị T rồi bọc thành Optional.
C. Luôn gọi supplier trước dù Optional đang có giá trị.
D. Gọi supplier để ném exception và kết thúc xử lý.
Đáp án đúng: A

Câu 47: Optional.stream() chuyển một Optional có giá trị thành gì?
A. Stream chứa một phần tử, còn Optional rỗng thành Stream rỗng.
B. Stream chỉ gồm Optional wrapper, không lấy giá trị bên trong.
C. Stream luôn tạo hai phần tử cho nhánh hiện tại và dự phòng.
D. Stream bỏ giá trị và chỉ giữ boolean thể hiện isPresent.
Đáp án đúng: A

Câu 48: Dùng takeWhile trên unordered Stream có rủi ro ngữ nghĩa nào?
A. Bắt buộc giữ đúng thứ tự phần tử trong dữ liệu nguồn ban đầu.
B. Không có prefix encounter order để dựa vào kết quả dừng.
C. Luôn hoạt động giống filter khi không có encounter order.
D. Tự gắn timestamp cho phần tử để khôi phục thứ tự xử lý.
Đáp án đúng: B

Câu 49: Trong Java 9 Flow API, Publisher đóng vai trò nào với Subscriber?
A. Chỉ lưu kết quả cuối cùng khi Subscriber đã hoàn tất mọi callback.
B. Chủ động gọi request(n) thay cho Subscriber ở mỗi vòng xử lý.
C. Đảm bảo lưu bền mọi sự kiện đã phát xuống ổ đĩa hệ thống.
D. Cung cấp luồng phần tử và các tín hiệu theo một subscription.
Đáp án đúng: D

Câu 50: Khi nhận onSubscribe từ Publisher, Subscriber nên làm gì để nhận dữ liệu?
A. Gọi onNext trên Publisher để lấy phần tử đầu tiên đang chờ.
B. Đóng Subscription ngay để kích hoạt mọi phần tử trong queue.
C. Gọi onComplete trước để Publisher bắt đầu gửi các dữ liệu.
D. Giữ Subscription và yêu cầu nhu cầu bằng request(n) hợp lệ.
Đáp án đúng: D

Câu 51: Flow.Subscription.request(n) biểu thị điều gì khi n dương?
A. Đặt số lượng worker thread mà Publisher bắt buộc tạo ra.
B. Thông báo số phần tử tối đa muốn nhận thêm qua subscription.
C. Giới hạn tổng phần tử từng xuất bản trong toàn bộ JVM.
D. Đặt timeout cho từng lần gọi phương thức onNext.
Đáp án đúng: B

Câu 52: Subscriber gọi request(0) cho Flow.Subscription; cách xử lý theo hợp đồng nào?
A. Đó là yêu cầu không hợp lệ, dẫn đến tín hiệu onError.
B. Được hiểu như yêu cầu vô hạn cho mọi phần tử tiếp theo.
C. Hệ thống chuyển giá trị 0 thành request(1) mặc định.
D. Được xem như cancel nhưng phát onComplete thay onError.
Đáp án đúng: A

Câu 53: Tại sao một Publisher cần tôn trọng demand của Subscriber?
A. Để đảm bảo mọi callback được chạy trên chính main thread.
B. Để buộc Subscriber nhận một lần toàn bộ phần tử đang chờ.
C. Không phát onNext vượt quá demand Subscriber đã yêu cầu.
D. Để JVM tự giảm kích thước object khi payload quá lớn.
Đáp án đúng: C

Câu 54: Ý nghĩa của Subscription.cancel trong Flow là gì?
A. Buộc thu hồi mọi event đã được xử lý bởi các Subscriber khác.
B. Phát onComplete cho mọi subscription đang hoạt động của Publisher.
C. Đề nghị ngừng subscription, không hoàn tác side effect đã xảy ra.
D. Xóa toàn bộ cache và hàng đợi JVM ở thời điểm hủy.
Đáp án đúng: C

Câu 55: Sau khi Subscriber nhận onError, hành vi nào không phù hợp hợp đồng?
A. Tiếp tục gửi onNext cho cùng subscription đã kết thúc.
B. Giải phóng các tài nguyên dành riêng cho subscription.
C. Ghi nhận lỗi để phục vụ việc kiểm tra và giám sát.
D. Dừng gửi các yêu cầu demand mới cho subscription lỗi.
Đáp án đúng: A

Câu 56: Trong Flow, onComplete được dùng để thông báo sự kiện nào?
A. Subscriber vừa yêu cầu thêm một phần tử bằng request(1).
B. Luồng kết thúc bình thường và không còn onNext tiếp theo.
C. Publisher phát hiện exception và cần thông báo nguyên nhân.
D. Một event đang chờ được Subscriber nhận thành công.
Đáp án đúng: B

Câu 57: Flow.Processor kết hợp hai vai trò nào trong một thành phần?
A. Vừa là Executor để chạy task vừa là Future chứa kết quả.
B. Nhận đầu vào như Subscriber và phát ra như Publisher.
C. Vừa là Subscription đầu vào vừa là Thread tạo sự kiện.
D. Vừa là Comparator của event vừa là Consumer của lỗi.
Đáp án đúng: B

Câu 58: SubmissionPublisher hỗ trợ mô hình giao sự kiện nào trong JDK?
A. Cung cấp cơ sở dữ liệu bền vững cho mọi event đã ghi.
B. Tự chuyển Flow.Publisher thành HTTP server không cấu hình.
C. Bảo đảm toàn bộ callback đồng bộ trên thread gọi submit.
D. Phát dữ liệu bất đồng bộ cho Subscriber qua Executor.
Đáp án đúng: D

Câu 59: Khi Subscriber xử lý chậm và buffer đầy, SubmissionPublisher.submit có thể làm gì?
A. Tự bỏ toàn bộ event mà không thể báo lại số lượng bị bỏ.
B. Tự mở rộng buffer không giới hạn khi subscriber bị chậm.
C. Chờ có dung lượng đệm trước khi tiếp tục việc submit.
D. Luôn trả về ngay vì kích thước queue mặc định vô hạn.
Đáp án đúng: C

Câu 60: Cách dùng SubmissionPublisher.offer với drop handler cần cân nhắc gì?
A. Chính sách mất event khi không thể nhận vào buffer đúng hạn.
B. Mọi offer đều tương đương submit và không bao giờ drop.
C. Handler chỉ được chạy khi subscriber gọi onComplete.
D. Mỗi event bị drop sẽ luôn được gửi lại nhờ Flow API.
Đáp án đúng: A

Câu 61: Khi gọi SubmissionPublisher.close, mục đích chính là gì?
A. Hủy ngay tất cả Subscription và hoàn tác event đã xử lý.
B. Báo hoàn tất xuất bản sau các phần tử còn chờ theo hợp đồng.
C. Đóng Executor được truyền vào dù còn các công việc khác.
D. Tự ghi nội dung buffer thành một file bền vững rồi thoát.
Đáp án đúng: B

Câu 62: Flow API có tự cung cấp một hệ thống message broker phân tán không?
A. Không, đây là các giao diện phối hợp luồng trong ứng dụng.
B. Có, mọi Publisher luôn ghi ra cluster broker sẵn trong JDK.
C. Có, mọi Subscription mặc định dùng một hàng đợi bền vững.
D. Không, vì Flow chỉ cho phép Subscriber thuộc cùng thread.
Đáp án đúng: A

Câu 63: Khi dùng ProcessHandle.info(), kỳ vọng nào phù hợp với metadata của process?
A. Mọi field đều phải tồn tại và được JVM điền đầy đủ.
B. Giá trị PID và command luôn giống nhau giữa mọi OS.
C. Một số thông tin như command hoặc start time có thể vắng mặt.
D. Thông tin trả về chỉ gồm stream dữ liệu stdout của process.
Đáp án đúng: C

Câu 64: Java 9 API nào hỗ trợ duyệt StackFrame bằng Stream trong callback?
A. Thread.getStackTrace luôn trả về Stream<StackFrame> trực tiếp.
B. Throwable.getStackTrace tự cung cấp Stream trong mọi JDK.
C. Thread.getAllStackTraces trả Stream<StackFrame> hiện hành.
D. StackWalker.walk cho phép duyệt stack frame theo callback.
Đáp án đúng: D
