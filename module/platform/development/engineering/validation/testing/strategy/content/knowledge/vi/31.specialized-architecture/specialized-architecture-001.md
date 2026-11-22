# Kiến trúc đặc thù: Thiết kế chiến lược cho thư viện Java có nhiều bên sử dụng

## 1. Vì sao thư viện Java cần chiến lược kiểm thử riêng?

Một thư viện Java được nhiều ứng dụng sử dụng có ranh giới chất lượng rộng hơn một ứng dụng đơn lẻ. Khi thư viện thay đổi, lỗi có thể xuất hiện trong chính thư viện, trong cách consumer biên dịch hoặc liên kết với thư viện, trong hành vi lúc chạy, hoặc trong tương tác với dependency và môi trường của consumer.

Nhóm phát triển thư viện thường kiểm soát được mã nguồn và pipeline của mình, nhưng không kiểm soát hoàn toàn:

- Phiên bản JDK mà từng consumer đang dùng.
- Maven, Gradle hoặc hệ thống build riêng của consumer.
- Classpath, module path và cách đóng gói ứng dụng.
- Phiên bản các dependency đã có trong ứng dụng.
- Cách consumer gọi API, xử lý exception và quản lý tài nguyên.
- Dữ liệu, tải, cấu hình và yêu cầu tương thích của từng hệ thống.

Một bộ unit test nội bộ pass không chứng minh rằng JAR mới có thể thay thế JAR cũ trong mọi ứng dụng. Thư viện có thể biên dịch thành công nhưng làm hỏng binary đã biên dịch trước đó, thay đổi hành vi của một API, kéo theo phiên bản dependency xung đột hoặc làm tăng đáng kể thời gian xử lý.

Trong **VALIDATION_TESTING_STRATEGY**, chiến lược cho thư viện Java đa consumer cần bảo vệ hợp đồng công khai, kiểm tra tương thích theo phạm vi hỗ trợ, xác minh cách dùng thực tế và tạo bằng chứng đủ rõ để consumer quyết định nâng cấp.

## 2. Xác định ai đang sử dụng thư viện và họ phụ thuộc vào điều gì

### 2.1. Lập hồ sơ nhóm consumer

Không nên xem mọi consumer là một nhóm đồng nhất. Hãy phân loại theo đặc điểm có thể ảnh hưởng đến cách kiểm thử:

| Nhóm consumer | Đặc điểm cần biết | Rủi ro thường gặp |
| --- | --- | --- |
| Ứng dụng nội bộ | Có thể phối hợp nâng cấp và chia sẻ pipeline | Thay đổi thư viện làm hỏng nhiều dịch vụ cùng lúc |
| Ứng dụng bên ngoài | Không kiểm soát lịch nâng cấp hoặc cấu hình | Consumer giữ phiên bản cũ lâu, gặp lỗi khi chuyển đổi |
| Consumer dùng JDK cũ | Bị giới hạn bởi API nền tảng | Thư viện vô tình yêu cầu JDK mới hơn |
| Consumer dùng JPMS | Dùng module path và module descriptor | Thay đổi exports, requires hoặc opens gây lỗi |
| Consumer dùng classpath | Dùng cơ chế class loading truyền thống | Xung đột class, service loader hoặc dependency |
| Framework/plugin host | Thư viện chạy trong container hoặc classloader riêng | Rò rỉ classloader, lifecycle và xung đột phiên bản |
| Consumer có tải lớn | Gọi API với concurrency hoặc dữ liệu lớn | Lock contention, allocation hoặc latency tăng |

Thông tin consumer nên được lấy từ dependency inventory, build metadata, khảo sát có cấu trúc, issue hỗ trợ và dữ liệu sử dụng đã được phép thu thập. Không suy luận rằng một consumer đại diện cho tất cả.

### 2.2. Xác định mức độ quan trọng của từng consumer

Đánh giá:

- Mức độ quan trọng của nghiệp vụ consumer.
- Số lượng ứng dụng hoặc người dùng bị ảnh hưởng.
- Khả năng nâng cấp và rollback.
- Tần suất sử dụng các API công khai.
- Mức độ tùy biến hoặc phụ thuộc vào hành vi chưa được tài liệu hóa.
- Yêu cầu về JDK, framework, module system và dependency.
- Thời gian consumer cần để xác minh bản phát hành mới.

Một consumer có số lượng nhỏ nhưng phục vụ nghiệp vụ quan trọng có thể cần được ưu tiên kiểm tra hơn một consumer có lưu lượng lớn nhưng dễ thay thế.

### 2.3. Lập ma trận consumer

Ma trận là đầu vào cho lựa chọn tổ hợp kiểm thử, không phải danh sách để chạy mọi khả năng một cách máy móc.

| Consumer đại diện | JDK | Build/đóng gói | Kiểu sử dụng | Rủi ro cần chú ý |
| --- | --- | --- | --- | --- |
| Service nội bộ A | Phiên bản tối thiểu được hỗ trợ | Maven, classpath | API đồng bộ | Source và binary compatibility |
| Service nội bộ B | JDK LTS hiện hành | Gradle, JPMS | API và ServiceLoader | Module descriptor và provider discovery |
| Ứng dụng plugin C | JDK được host hỗ trợ | Plugin classloader | Lifecycle và reflection | Classloader, resource cleanup |
| Ứng dụng xử lý dữ liệu D | JDK mới trong phạm vi hỗ trợ | Gradle, container | Batch và concurrency | Memory, throughput, thread safety |
| Consumer bên ngoài E | Phiên bản JDK được hỗ trợ | Maven, shaded dependencies | API công khai | Dependency conflict và migration |

Tên consumer trong bảng có thể được ẩn danh. Chỉ lưu chi tiết cần thiết để xây dựng coverage và tái hiện lỗi.

## 3. Xác định hợp đồng công khai cần bảo vệ

### 3.1. Bề mặt API công khai

Lập danh mục các thành phần mà consumer được kỳ vọng sử dụng:

- Public class, interface, enum, record và annotation.
- Constructor, method, field và generic signature.
- Package được export hoặc công khai trong tài liệu.
- Exception có thể được ném ra.
- Callback, listener, SPI và Service Provider.
- Cấu hình, system property, environment variable và file format.
- Kiểu dữ liệu, schema hoặc protocol được trao đổi.
- Quy tắc quản lý tài nguyên và lifecycle.

Phân biệt API được hỗ trợ chính thức với chi tiết triển khai nội bộ. Tuy nhiên, nếu consumer đã phụ thuộc vào một hành vi chưa được tài liệu hóa, thay đổi đó vẫn có thể tạo ra tác động thực tế. Cần đánh giá dữ liệu sử dụng và phản hồi trước khi kết luận một thay đổi là vô hại.

### 3.2. Các chiều tương thích

| Chiều tương thích | Câu hỏi cần trả lời | Ví dụ thay đổi có thể gây lỗi |
| --- | --- | --- |
| Source compatibility | Mã nguồn consumer cũ có biên dịch với thư viện mới không? | Xóa method, đổi generic signature, thêm checked exception |
| Binary compatibility | Binary consumer đã biên dịch có chạy với thư viện mới không? | Xóa/đổi method descriptor, đổi class/interface hoặc constructor |
| Behavioral compatibility | Cùng lời gọi có còn tạo hành vi và kết quả được cam kết không? | Đổi thứ tự xử lý, giá trị mặc định, exception hoặc semantics |
| Serialization/protocol compatibility | Dữ liệu cũ và mới có thể đọc/trao đổi đúng không? | Đổi tên field, enum value hoặc schema |
| Configuration compatibility | Cấu hình cũ còn được nhận diện và diễn giải đúng không? | Đổi property, default hoặc precedence |
| Dependency compatibility | Consumer có giải quyết được dependency và tránh xung đột không? | Nâng major dependency hoặc đổi phạm vi transitive dependency |
| Performance compatibility | Tải và tài nguyên có nằm trong giới hạn chấp nhận không? | Allocation, lock contention hoặc latency tăng |
| Operational compatibility | Lifecycle, logging và resource usage có phù hợp môi trường host không? | Không đóng executor, giữ thread hoặc classloader |

Một thay đổi có thể tương thích ở một chiều nhưng không tương thích ở chiều khác. Ví dụ, mã nguồn consumer có thể biên dịch lại thành công nhưng binary đã biên dịch trước đó có thể không liên kết được.

### 3.3. Viết compatibility policy

Chính sách tương thích nên quy định:

- Các package và API được cam kết hỗ trợ.
- JDK tối thiểu và các phiên bản được kiểm thử.
- Quy tắc source và binary compatibility.
- Cách xử lý thay đổi hành vi.
- Chính sách deprecation và thời gian chuyển đổi.
- Hỗ trợ dữ liệu, cấu hình và serialization cũ.
- Phạm vi dependency được quản lý hoặc để consumer tự chọn.
- Quy trình thông báo breaking change và security fix.

Nếu một chiều tương thích không được cam kết, phải ghi rõ giới hạn. Không để consumer phải suy đoán từ số phiên bản hoặc việc build thành công.

## 4. Chọn chiến lược kiểm thử theo lớp

### 4.1. Unit test cho logic bên trong

Unit test kiểm tra quy tắc và nhánh logic có thể cô lập:

- Validation và chuyển đổi dữ liệu.
- Quy tắc tính toán.
- Xử lý null, giá trị biên và lỗi.
- Logic retry, timeout hoặc state transition.
- Các nhánh xử lý trong adapter.

Unit test nên kiểm tra hành vi có ý nghĩa, nhưng không thể thay thế kiểm thử qua public API hoặc môi trường consumer.

### 4.2. Public API test

Public API test sử dụng thư viện như một consumer độc lập:

- Chỉ import package và type được công khai.
- Tạo đối tượng qua constructor hoặc factory được hỗ trợ.
- Gọi API theo cách được tài liệu hướng dẫn.
- Xác minh kết quả, exception và lifecycle.
- Biên dịch trong một project riêng với dependency đã đóng gói.

Project kiểm thử nên tham chiếu artifact JAR được tạo ra từ pipeline, không chỉ tham chiếu source set nội bộ. Điều này giúp phát hiện vấn đề đóng gói, thiếu class hoặc resource.

### 4.3. Integration test với dependency

Kiểm tra cách thư viện tương tác với:

- Database driver và connection pool.
- HTTP client hoặc messaging client.
- Logging framework.
- JSON/XML serializer.
- Service provider và plugin API.
- File system, network hoặc clock.

Ưu tiên kiểm tra các phiên bản dependency được công bố hỗ trợ và các ranh giới có rủi ro cao. Với dependency ngoài, dùng container hoặc sandbox có thể tái lập; tránh phụ thuộc vào dịch vụ production thật trong pipeline thường xuyên.

### 4.4. Consumer contract test

Consumer contract test kiểm tra những giả định cụ thể mà consumer dựa vào:

- Tên và chữ ký API được sử dụng.
- Kiểu dữ liệu đầu vào/đầu ra.
- Hành vi khi lỗi hoặc dữ liệu không hợp lệ.
- Callback, event và thứ tự tương tác.
- Quy tắc cấu hình.
- Thread-safety hoặc lifecycle nếu được cam kết.

Contract test cần có owner và phiên bản. Không nên để một consumer duy nhất áp đặt hành vi riêng thành hợp đồng chung nếu đó không phải API được hỗ trợ.

### 4.5. Compatibility test với phiên bản trước

Có thể duy trì:

- Consumer source mẫu được biên dịch với thư viện mới.
- Consumer binary được biên dịch trước với phiên bản cũ rồi chạy cùng thư viện mới.
- Kiểm tra API diff giữa artifact cũ và mới.
- Kiểm tra cấu hình và dữ liệu đã lưu từ phiên bản trước.
- Kiểm tra deprecation và migration path.

API diff tool có thể hỗ trợ phát hiện thay đổi chữ ký và visibility, nhưng cần kết hợp với test hành vi và chính sách tương thích. Công cụ không tự xác định mọi thay đổi có phá vỡ hợp đồng nghiệp vụ hay không.

### 4.6. End-to-end test bằng ứng dụng mẫu

Ứng dụng mẫu mô phỏng cách consumer thực tế tích hợp thư viện:

- Khai báo dependency như một project bên ngoài.
- Dùng cấu hình và entry point công khai.
- Khởi tạo, sử dụng và đóng thư viện theo lifecycle.
- Chạy một luồng nghiệp vụ tiêu biểu.
- Kiểm tra kết quả và tài nguyên sau khi hoàn tất.

Không cần tạo một ứng dụng mẫu cho mọi consumer. Chọn một số đại diện theo mức độ sử dụng, kiến trúc và rủi ro.

## 5. Kiểm thử source và binary compatibility

### 5.1. Source compatibility

Source compatibility trả lời liệu mã nguồn consumer có thể biên dịch lại với phiên bản thư viện mới không.

Các thay đổi cần xem xét:

- Xóa hoặc đổi tên public class, method, field hoặc constructor.
- Giảm visibility.
- Đổi kiểu tham số hoặc kiểu trả về.
- Thay đổi generic bound hoặc type parameter.
- Thêm checked exception vào method.
- Thêm overload gây mơ hồ cho lời gọi cũ.
- Thay đổi interface mà consumer đang implement.
- Đổi annotation có ảnh hưởng tới code generation hoặc framework.

Một số thay đổi có thể vẫn biên dịch trong trường hợp đơn giản nhưng tạo lỗi với consumer dùng overload, lambda, method reference hoặc generic type cụ thể. Vì vậy, compile test nên dùng mã consumer đại diện thay vì chỉ kiểm tra một lời gọi tối giản.

### 5.2. Binary compatibility

Binary compatibility kiểm tra binary consumer đã biên dịch với thư viện cũ có tiếp tục liên kết và chạy với thư viện mới không.

Các rủi ro gồm:

- Method hoặc constructor bị xóa.
- Thay đổi descriptor của method.
- Class đổi thành interface hoặc ngược lại.
- Field hoặc method không còn truy cập được.
- Thay đổi hierarchy làm phát sinh lỗi liên kết.
- Thay đổi SPI khiến provider cũ không còn được phát hiện.

Một kiểm tra hữu ích là biên dịch consumer fixture một lần với phiên bản thư viện cũ, sau đó chạy binary đó trên classpath/module path có phiên bản thư viện mới. Không biên dịch lại fixture trong bước này, vì biên dịch lại chỉ kiểm tra source compatibility.

### 5.3. Ví dụ quy trình kiểm tra hai chiều

~~~text
Source compatibility:
1. Lấy consumer-source fixture đã dùng API công khai.
2. Đưa artifact thư viện mới vào dependency.
3. Biên dịch fixture bằng từng JDK/build mode được hỗ trợ.
4. Ghi compile error và xác định thay đổi API liên quan.

Binary compatibility:
1. Biên dịch consumer fixture với artifact thư viện cũ.
2. Lưu bytecode và dependency của fixture.
3. Thay đúng artifact thư viện bằng bản mới.
4. Chạy fixture mà không biên dịch lại.
5. Ghi linkage error, runtime error và hành vi quan sát được.
~~~

### 5.4. Không đánh đồng API diff với compatibility hoàn chỉnh

API diff có thể cảnh báo xóa method hoặc đổi visibility. Tuy nhiên, nó không đủ để xác nhận:

- Hành vi có giữ đúng semantics không.
- Default configuration có thay đổi không.
- Dependency có xung đột khi consumer giải quyết không.
- Serialization hoặc protocol có tương thích không.
- Performance và resource lifecycle có bị suy giảm không.

Kết quả diff là một nguồn bằng chứng trong compatibility review, không phải kết luận cuối cùng.

## 6. Ma trận JDK, build tool và module system

### 6.1. JDK support matrix

Chính sách hỗ trợ nên xác định:

- JDK tối thiểu để biên dịch thư viện.
- JDK tối thiểu để chạy thư viện.
- Các JDK được kiểm thử trong CI.
- Các JDK chỉ được hỗ trợ theo best effort nếu có.
- Thời điểm ngừng hỗ trợ một phiên bản.

Kiểm tra trên JDK tối thiểu giúp phát hiện việc vô tình sử dụng API mới hơn hoặc bytecode target không phù hợp. Kiểm tra trên JDK mới giúp phát hiện thay đổi runtime, reflection, security và cảnh báo deprecated.

Không chỉ thay JAVA_HOME rồi cho rằng ma trận đã được kiểm tra. Cần xác nhận compiler toolchain, runtime thực thi, target bytecode và dependency tương thích.

### 6.2. Ma trận build tool

Nếu consumer được hỗ trợ với Maven và Gradle, nên có fixture tối thiểu cho từng cách dùng:

- Dependency declaration.
- Repository resolution.
- Transitive dependency.
- Test/runtime classpath.
- Annotation processor hoặc generated source nếu có.
- Packaging và shading nếu thuộc phạm vi hỗ trợ.

Không nhất thiết kiểm thử mọi phiên bản build tool. Chọn các phiên bản trong chính sách hỗ trợ và một tổ hợp đại diện có rủi ro cao.

### 6.3. Classpath và JPMS

Nếu thư viện hỗ trợ cả classpath và Java Platform Module System (JPMS), cần kiểm tra hai cách chạy:

- Module descriptor có tên module đúng.
- exports chỉ công khai package dự kiến.
- requires phản ánh dependency thực tế.
- opens chỉ được dùng khi cần reflection có chủ đích.
- Service provider được khai báo và phát hiện đúng.
- Module path không tạo split package hoặc xung đột module name.
- Consumer có thể truy cập API được tài liệu cam kết.

Một thư viện chạy được trên classpath chưa chắc hoạt động đúng trên module path. Kiểm thử cần có consumer fixture modular và một fixture classpath nếu cả hai được hỗ trợ.

### 6.4. Tương thích framework và runtime host

Với thư viện được dùng trong framework hoặc plugin host, xem xét:

- Phiên bản framework được hỗ trợ.
- Lifecycle khởi tạo và hủy.
- Dependency injection và reflection.
- Context classloader.
- Thread pool và scheduler.
- Logging bridge.
- Cơ chế reload hoặc unload plugin.

Đặc biệt, kiểm tra thư viện có giữ thread, classloader hoặc resource sau khi consumer đóng context hay không.

## 7. Kiểm thử dependency và đóng gói

### 7.1. Dependency graph

Thư viện có thể kéo theo dependency transitive mà consumer đã dùng phiên bản khác. Kiểm tra:

- Dependency trực tiếp và transitive.
- Phạm vi compile/runtime/optional.
- Version conflict và dependency mediation.
- Dependency bị loại trừ hoặc được consumer override.
- CVE và chính sách cập nhật bảo mật.
- License và yêu cầu phân phối nếu thuộc quy trình.

Kiểm thử trên một consumer fixture có thêm dependency phổ biến giúp phát hiện xung đột không xuất hiện trong project thư viện đơn lẻ.

### 7.2. Kiểm tra artifact được phát hành

Xác minh nội dung JAR:

- Class và resource cần thiết có mặt.
- Không đóng gói nhầm test class hoặc file nội bộ.
- Metadata, manifest và module descriptor đúng.
- Service provider metadata được giữ lại khi đóng gói.
- License, notice và thông tin phiên bản có mặt theo chính sách.
- Shading/relocation không làm đổi API hoặc tên được consumer sử dụng.

Nếu phát hành nhiều artifact như main JAR, sources JAR, Javadoc JAR hoặc multi-release JAR, kiểm tra tính nhất quán giữa chúng.

### 7.3. Dependency convergence và xung đột

Consumer có thể dùng một phiên bản dependency khác với phiên bản mà thư viện đã kiểm thử. Tạo fixture có dependency graph đại diện và xác minh:

- Không có lỗi linkage hoặc class loading do xung đột class.
- Phiên bản được resolve đáp ứng yêu cầu tối thiểu.
- Optional dependency thực sự optional nếu đã công bố như vậy.
- Logging và service provider không bị đăng ký trùng hoặc mất.

Không nên ép consumer dùng dependency cụ thể nếu thư viện không cần kiểm soát nó. Nếu có giới hạn phiên bản, công bố rõ và kiểm thử ranh giới đó.

## 8. Kiểm thử hành vi, exception và lifecycle

### 8.1. Hợp đồng hành vi

Hợp đồng công khai cần xác định:

- Đầu vào hợp lệ và không hợp lệ.
- Giá trị mặc định.
- Kết quả và side effect.
- Thứ tự callback hoặc event nếu được cam kết.
- Quy tắc idempotency.
- Điều kiện retry và timeout.
- Exception có thể phát sinh và cách consumer xử lý.

Không để test phụ thuộc vào chi tiết nội bộ như tên private method nếu hợp đồng công khai không yêu cầu.

### 8.2. Exception compatibility

Kiểm tra:

- Loại exception trong các điều kiện được tài liệu hóa.
- Checked exception và unchecked exception.
- Cause chain và error code nếu là hợp đồng.
- Không làm lộ secret hoặc dữ liệu nhạy cảm trong message.
- Exception có được ném đồng bộ hay truyền qua callback/future.

Thay đổi từ một exception cụ thể sang một exception tổng quát có thể làm consumer mất khả năng xử lý theo nhánh. Ngược lại, thêm checked exception có thể làm source consumer cũ không biên dịch được.

### 8.3. Resource lifecycle

Với API mở file, socket, connection, executor hoặc stream, kiểm tra:

- Tài nguyên được tạo và giải phóng đúng lúc.
- close có thể gọi nhiều lần nếu hợp đồng cho phép.
- Exception trong lúc đóng được xử lý phù hợp.
- Không giữ thread hoặc connection sau khi consumer kết thúc.
- Không đóng tài nguyên do consumer sở hữu nếu thư viện không có quyền sở hữu.
- Hành vi shutdown được xác định khi tác vụ đang chạy.

Ví dụ, nếu thư viện tạo executor nội bộ, tài liệu cần quy định ai đóng executor và phương thức nào thực hiện shutdown. Integration test nên xác nhận thread không còn hoạt động sau lifecycle kết thúc.

### 8.4. Thread safety và concurrency

Nếu thư viện tuyên bố thread-safe hoặc được dùng trong môi trường nhiều luồng, kiểm tra:

- Nhiều thread gọi cùng instance.
- Nhiều instance chia sẻ dependency.
- Cập nhật state đồng thời.
- Callback đến theo thứ tự khác nhau.
- Cancellation, timeout và shutdown.
- Visibility và tính nhất quán của dữ liệu.

Chỉ ghi thread-safe khi phạm vi được xác định. Một class có thể thread-safe cho method đọc nhưng không hỗ trợ cấu hình đồng thời với method ghi.

## 9. Serialization, cấu hình và dữ liệu lưu trữ

### 9.1. Serialization compatibility

Nếu thư viện đọc/ghi dữ liệu, kiểm tra:

- JSON/XML field name và type.
- Giá trị enum.
- Null, missing field và default.
- Date/time, timezone và precision.
- Encoding và Unicode.
- Version schema.
- Unknown field và forward/backward compatibility.

Giữ fixture dữ liệu từ phiên bản cũ để xác minh phiên bản mới vẫn đọc được khi hợp đồng yêu cầu. Nếu format thay đổi, kiểm tra cả dữ liệu cũ và mới.

### 9.2. Java native serialization

Nếu public API hỗ trợ Java serialization, cần xem xét:

- serialVersionUID.
- Thay đổi field và class hierarchy.
- Custom readObject/writeObject.
- Invariant sau khi deserialize.
- Tương thích giữa object stream tạo bởi phiên bản cũ và mới.

Java native serialization có rủi ro bảo mật và vòng đời riêng. Không nên thêm nó vào API mới nếu không có lý do rõ ràng; nếu đã hỗ trợ, phải kiểm thử và áp dụng chính sách deserialization an toàn.

### 9.3. Cấu hình

Kiểm tra:

- Tên property và biến môi trường.
- Default value.
- Thứ tự ưu tiên giữa constructor, file, system property và environment.
- Cách xử lý property không biết hoặc sai kiểu.
- Hành vi khi thiếu cấu hình.
- Cảnh báo deprecation và migration.

Một thay đổi default có thể giữ binary compatibility nhưng thay đổi đáng kể hành vi consumer. Đây là lý do cần test cấu hình và behavioral compatibility.

## 10. Kiểm thử hiệu năng và tài nguyên trong bối cảnh đa consumer

### 10.1. Chọn workload đại diện

Benchmark nên đại diện cho cách consumer sử dụng:

- Kích thước và phân phối input.
- Tần suất gọi API.
- Concurrency và số instance.
- Tỷ lệ thao tác đọc/ghi.
- Warm-up và thời gian đo.
- Tài nguyên cấp phát.
- Các dependency và network call.

Không suy rộng từ microbenchmark một method sang hiệu năng toàn ứng dụng. Dùng benchmark nhỏ để tìm thay đổi cục bộ và integration/performance test để kiểm tra chi phí trong luồng sử dụng thực tế.

### 10.2. Metric cần theo dõi

- Latency p50, p95 và p99.
- Throughput.
- Allocation rate và garbage collection.
- Heap usage và retained object.
- Thread count, lock contention và context switching.
- Connection usage và queue depth.
- CPU và I/O.

So sánh trên cùng JDK, máy, workload và cấu hình hoặc ghi rõ các khác biệt. Chạy lặp và dùng baseline để tránh kết luận từ một lần đo nhiễu.

### 10.3. Tránh regression do hành vi chia sẻ

Một thư viện được nhiều ứng dụng dùng có thể tạo tác động tổng thể qua:

- Thread pool chung.
- Static cache hoặc singleton.
- Global system property.
- Logging handler.
- Shutdown hook.
- Shared mutable state.

Kiểm tra việc khởi tạo nhiều instance, chạy nhiều consumer trong cùng JVM và đóng một consumer mà không ảnh hưởng consumer khác nếu thư viện cam kết hỗ trợ mô hình đó.

## 11. Quản lý thay đổi, deprecation và migration

### 11.1. Phân loại thay đổi

Mỗi thay đổi nên được đánh giá theo:

- API public có thay đổi không?
- Source/binary compatibility có bị ảnh hưởng không?
- Semantics hoặc default có đổi không?
- Dependency và JDK requirement có đổi không?
- Dữ liệu/cấu hình cũ có còn đọc được không?
- Performance hoặc resource usage có thay đổi không?
- Consumer nào cần hành động?

Kết quả review nên được gắn với release note và kế hoạch kiểm thử tương ứng.

### 11.2. Deprecation có lộ trình

Khi cần thay API:

1. Giới thiệu API thay thế.
2. Đánh dấu API cũ deprecated với thông tin chuyển đổi.
3. Giữ API cũ trong thời gian đã công bố nếu chính sách yêu cầu.
4. Cung cấp ví dụ migration.
5. Theo dõi việc sử dụng API cũ nếu có telemetry phù hợp.
6. Chỉ xóa theo chính sách major release hoặc thời điểm đã thông báo.

Không dùng deprecation annotation như một thông báo duy nhất nếu consumer cần biết cách thay thế. Release note cần mô tả ảnh hưởng và bước migration.

### 11.3. Migration test

Giữ một hoặc nhiều consumer fixture ở phiên bản cũ để kiểm tra:

- Nâng dependency có hoàn tất không.
- Cấu hình cũ có được nhận diện không.
- Dữ liệu cũ có đọc được không.
- API thay thế tạo kết quả tương đương theo yêu cầu không.
- Cảnh báo deprecation xuất hiện đúng.
- Không còn dependency hoặc class cũ sau migration nếu cần.

Migration test nên mô phỏng cách consumer nâng cấp thực tế, bao gồm cả việc cập nhật build file và cấu hình.

## 12. Kiểm soát độ rộng của ma trận kiểm thử

### 12.1. Không chạy mọi tổ hợp một cách máy móc

Số tổ hợp có thể tăng nhanh:

- Nhiều JDK.
- Nhiều build tool.
- Classpath và module path.
- Nhiều dependency version.
- Nhiều framework.
- Nhiều hệ điều hành.
- Nhiều kiểu consumer.

Không phải mọi tổ hợp đều có rủi ro hoặc nằm trong chính sách hỗ trợ. Chọn ma trận dựa trên mức hỗ trợ chính thức, dữ liệu consumer và tác động của thay đổi.

### 12.2. Chiến lược chọn tổ hợp

Có thể kết hợp:

- **Bắt buộc:** JDK tối thiểu, JDK hiện hành, build mode và module mode được công bố hỗ trợ.
- **Đại diện:** consumer có kiến trúc hoặc dependency khác biệt.
- **Theo thay đổi:** thêm tổ hợp liên quan tới package, SPI, serializer hoặc dependency bị sửa.
- **Theo rủi ro:** ưu tiên consumer quan trọng và vùng từng xảy ra incident.
- **Theo lịch:** chạy ma trận rộng hơn theo đêm hoặc trước release lớn.

Pairwise testing có thể giảm số tổ hợp khi các yếu tố độc lập tương đối, nhưng không thay thế kiểm thử các tổ hợp rủi ro đã biết hoặc dependency có tương tác phức tạp.

### 12.3. Ma trận kiểm thử mẫu

| Kiểm tra | JDK tối thiểu | JDK LTS hiện hành | Classpath | JPMS | Tần suất |
| --- | --- | --- | --- | --- | --- |
| Unit test | Có | Có | Không áp dụng | Không áp dụng | Mỗi thay đổi |
| Public API compile fixture | Có | Có | Có | Có nếu hỗ trợ | Mỗi pull request |
| Consumer binary fixture | Tổ hợp được hỗ trợ trọng yếu | Có | Có | Có nếu hỗ trợ | Mỗi release candidate |
| Integration dependency | Tổ hợp đại diện | Có | Theo consumer | Theo consumer | Pull request liên quan/định kỳ |
| Application sample | Tổ hợp đại diện | Có | Theo mẫu | Theo mẫu | Release candidate |
| Performance benchmark | Môi trường chuẩn | Môi trường chuẩn | Theo cách đóng gói | Theo cách đóng gói | Khi thay đổi ảnh hưởng hiệu năng |

Các ô “Có” cần được cụ thể hóa thành JDK, build tool và cấu hình thật trong pipeline của dự án.

## 13. Tổ chức pipeline cho thư viện

### 13.1. Pull request pipeline

Có thể bao gồm:

- Compile với JDK tối thiểu.
- Unit test và static checks.
- Public API compile fixture.
- API diff hoặc compatibility check.
- Kiểm tra dependency và đóng gói.
- Integration test nhanh cho các ranh giới thay đổi.

Mục tiêu là phản hồi sớm với chi phí phù hợp.

### 13.2. Nightly hoặc scheduled pipeline

Có thể chạy:

- Ma trận JDK/build tool rộng hơn.
- JPMS và classpath fixtures.
- Dependency combinations đại diện.
- Consumer contract suite.
- Test concurrency và resource lifecycle.
- Benchmark theo baseline.

### 13.3. Release candidate pipeline

Trước khi phát hành:

- Kiểm tra artifact đúng như sẽ publish.
- Source và binary compatibility.
- Consumer sample end-to-end.
- Migration và serialization fixtures.
- Release note, deprecation và dependency metadata.
- Security scan và license review theo quy trình.
- Xác nhận mọi tiêu chí bắt buộc và ngoại lệ.

Không chỉ kiểm tra source tree rồi phát hành một artifact chưa được xác minh. Candidate cần được kiểm tra đúng file JAR hoặc package mà consumer sẽ tải.

### 13.4. Lưu bằng chứng

Mỗi lần chạy nên lưu:

- Version, commit và artifact digest.
- JDK, build tool, OS và module mode.
- Dependency graph đã resolve.
- Test suite/version và kết quả.
- API diff report.
- Log, trace và benchmark result.
- Các tổ hợp chưa chạy và lý do.
- Quyết định quality gate.

Nhờ vậy, khi consumer báo lỗi, nhóm có thể đối chiếu với tổ hợp đã kiểm tra.

## 14. Phản hồi từ consumer và xử lý sự cố tương thích

### 14.1. Thu thập báo cáo có đủ ngữ cảnh

Khi consumer báo lỗi sau nâng cấp, cần hỏi hoặc thu thập:

- Phiên bản thư viện cũ và mới.
- JDK và build tool.
- Dependency tree hoặc các dependency liên quan.
- Classpath/module path và cách đóng gói.
- Bước tái hiện tối thiểu.
- Expected/actual behavior.
- Exception, stack trace đã làm sạch.
- Cấu hình và dữ liệu cần thiết.
- Thời điểm nâng cấp và thay đổi khác đi kèm.

Không yêu cầu consumer gửi source hoặc dữ liệu nhạy cảm vượt quá phạm vi cần thiết. Có thể dùng một reproducer nhỏ đã làm sạch.

### 14.2. Phân loại lỗi

| Loại lỗi | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| Compile/source break | Consumer không biên dịch | API signature, generic, overload, checked exception |
| Linkage/binary break | Lỗi liên kết hoặc không tìm thấy class/method | Descriptor, hierarchy, class loading và dependency |
| Behavioral regression | Chạy được nhưng kết quả khác | Semantics, default, ordering, exception và state |
| Dependency conflict | Lỗi class/version khi resolve hoặc runtime | Dependency graph, mediation, shading |
| Environment incompatibility | Chỉ lỗi trên một JDK/OS/framework | Runtime API, reflection, module access |
| Resource/performance issue | Thread, memory, latency hoặc connection tăng | Lifecycle, allocation, lock và workload |

### 14.3. Chuyển incident thành lớp kiểm thử

Sau khi xác định nguyên nhân:

1. Tạo reproducer tối thiểu.
2. Xác định chiều tương thích bị vi phạm.
3. Chọn tầng kiểm thử phù hợp.
4. Xác nhận test thất bại trên artifact có lỗi nếu có thể.
5. Áp dụng bản sửa và xác nhận test pass.
6. Thêm tổ hợp consumer/JDK/dependency nếu nó đại diện cho một rủi ro riêng.
7. Cập nhật compatibility policy hoặc tài liệu nếu hợp đồng chưa rõ.

Không chỉ thêm một test cho consumer đầu tiên nếu nguyên nhân có thể ảnh hưởng mọi consumer cùng dùng API hoặc dependency đó.

## 15. Ví dụ tổng hợp: thay đổi một API được nhiều ứng dụng dùng

### 15.1. Bối cảnh

Thư viện cung cấp interface:

~~~java
public interface TokenProvider {
    Token createToken(UserContext context);
}
~~~

Nhiều ứng dụng triển khai TokenProvider để tạo token theo chính sách riêng. Nhóm thư viện muốn bổ sung thông tin audience.

### 15.2. Đánh giá thay đổi

Nếu thêm một abstract method mới vào interface, các consumer đang implement interface có thể không biên dịch hoặc có thể gặp lỗi tương thích khi chạy binary cũ. Nếu thêm một default method, khả năng tương thích có thể tốt hơn, nhưng cần kiểm tra xung đột method, semantics mặc định và cách consumer override.

Nhóm cần xác định:

- Có thể thêm overload hoặc API mới mà giữ nguyên interface không?
- Giá trị audience mặc định là gì?
- Consumer cũ có cần hành vi cũ không?
- Có cần deprecation cho API cũ không?
- Binary consumer đã biên dịch có tiếp tục chạy không?
- Javadoc và migration guide đã đủ rõ chưa?

### 15.3. Bộ kiểm thử cần có

- Unit test cho quy tắc tạo audience.
- Public API compile fixture gọi API mới.
- Consumer fixture implement interface cũ.
- Binary compatibility fixture đã biên dịch với artifact trước.
- Behavioral test cho default audience.
- Test khi consumer override method.
- Test trên JDK tối thiểu và JDK hiện hành.
- Application sample chạy theo classpath và JPMS nếu hỗ trợ.

### 15.4. Điều kiện phát hành

Chỉ phát hành khi:

- API change được review theo compatibility policy.
- Các fixture bắt buộc pass.
- Không có binary/source break chưa được chấp nhận.
- Default behavior được tài liệu hóa.
- Migration/deprecation được công bố.
- Release note mô tả consumer nào cần hành động.

Nếu một breaking change là cần thiết, phải phân loại version và cung cấp lộ trình migration theo chính sách của thư viện.

## 16. Mẫu kế hoạch kiểm thử cho một thư viện đa consumer

~~~text
Tên thư viện:
Phiên bản hiện tại / candidate:
Artifact coordinates:
Owner:
Compatibility policy version:

1. Consumer profile
- Consumer group:
- Business criticality:
- JDK:
- Build tool:
- Classpath / JPMS:
- Framework / runtime:
- Dependency đặc biệt:
- API/SPI đang dùng:

2. Public contract
- Public packages/types:
- API và semantics được cam kết:
- Exception:
- Configuration:
- Serialization/protocol:
- Lifecycle/thread-safety:

3. Compatibility scope
- Source compatibility:
- Binary compatibility:
- Behavioral compatibility:
- Dependency compatibility:
- JDK/build/module compatibility:
- Performance/operational compatibility:

4. Test matrix
- Unit/public API:
- Consumer compile fixture:
- Consumer binary fixture:
- Contract/integration:
- Application sample:
- Migration/serialization:
- Performance/concurrency:
- JDK/build/module combinations:

5. Release evidence
- Artifact digest:
- Test reports:
- API diff:
- Dependency report:
- Benchmark:
- Known limitations:
- Breaking changes/deprecations:
- Consumer action required:
- Approval / exception:
~~~

## 17. Chỉ số theo dõi chất lượng tương thích

Có thể theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Compatibility test pass rate | Mức độ đạt của các tổ hợp bắt buộc |
| Consumer upgrade success | Tỷ lệ consumer nâng cấp thành công trong phạm vi quan sát |
| Consumer-reported regression | Lỗi tương thích được báo sau phát hành |
| Binary/source break count | Số thay đổi phá vỡ được phát hiện trước release |
| Time to reproduce | Thời gian tạo được reproducer đáng tin cậy |
| Dependency conflict rate | Tần suất xung đột dependency trong consumer fixture |
| Migration completion | Mức độ hoàn tất chuyển đổi khỏi API deprecated |
| Performance delta | Thay đổi latency, throughput và resource usage trên workload chuẩn |

Không dùng một tỷ lệ tổng làm đại diện cho mọi consumer. Báo theo nhóm JDK, build mode, framework hoặc mức độ quan trọng khi dữ liệu cho phép. Consumer không phản hồi không đồng nghĩa nâng cấp thành công.

## 18. Checklist thiết kế chiến lược cho thư viện Java có nhiều bên sử dụng

- [ ] Đã xác định nhóm consumer và đặc điểm môi trường chính.
- [ ] Có inventory về JDK, build tool, module mode và dependency.
- [ ] Public API, SPI, configuration và protocol được nhận diện.
- [ ] Compatibility policy nêu rõ source, binary và behavioral compatibility.
- [ ] JDK tối thiểu và các phiên bản hỗ trợ được kiểm tra.
- [ ] Có public API compile fixture chạy như consumer độc lập.
- [ ] Có binary fixture được biên dịch từ phiên bản trước.
- [ ] Có contract/integration test cho các ranh giới quan trọng.
- [ ] Có consumer sample đại diện và test artifact thực tế.
- [ ] Classpath và JPMS được kiểm tra nếu cả hai được hỗ trợ.
- [ ] Dependency graph, transitive dependency và packaging được xác minh.
- [ ] Serialization, cấu hình cũ và migration được kiểm tra khi có áp dụng.
- [ ] Exception, lifecycle, resource cleanup và thread-safety được kiểm tra theo hợp đồng.
- [ ] Performance benchmark dùng workload và baseline có thể so sánh.
- [ ] Ma trận được chọn theo hỗ trợ và rủi ro, không chạy mọi tổ hợp vô điều kiện.
- [ ] Pipeline lưu artifact, phiên bản môi trường và bằng chứng.
- [ ] Breaking change và deprecation có migration guide và release note.
- [ ] Có quy trình tiếp nhận, tái hiện và chuyển consumer incident thành regression test.
- [ ] Quality gate nêu rõ tổ hợp bắt buộc, ngoại lệ và người phê duyệt.

Chiến lược kiểm thử cho thư viện Java đa consumer phải chứng minh nhiều hơn việc mã nguồn của thư viện biên dịch và unit test pass. Khi hợp đồng công khai, môi trường consumer, source/binary/behavioral compatibility, dependency, lifecycle và hiệu năng được kiểm tra theo ma trận có chủ đích, nhóm phát hành có bằng chứng đáng tin cậy hơn và consumer có thể nâng cấp với rủi ro được hiểu rõ.
