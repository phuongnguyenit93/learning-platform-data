# Lập ma trận rủi ro và tiêu chí chấp nhận chuyển đổi

Trong giai đoạn **Khảo sát hệ thống** của chủ đề **Java Advance Compatibility Migration**, việc lập ma trận rủi ro và tiêu chí chấp nhận giúp nhóm chuyển đổi xác định trước điều gì có thể hỏng, mức độ ảnh hưởng đến hệ thống và bằng chứng cần có để kết luận rằng một lần nâng cấp đã an toàn.

Một kế hoạch migration chỉ liệt kê các bước nâng phiên bản JDK, framework hoặc thư viện là chưa đủ. Cần hiểu các thành phần phụ thuộc vào nhau, những hợp đồng mà ứng dụng đang sử dụng, những client có thể đã được biên dịch từ trước và những điều kiện runtime phải được giữ nguyên. Ma trận rủi ro biến các giả định đó thành các mục có người phụ trách, mức ưu tiên và biện pháp xử lý. Tiêu chí chấp nhận biến mục tiêu chuyển đổi thành các điều kiện có thể kiểm chứng bằng kết quả build, kiểm thử và quan sát khi chạy.

## 1. Mục tiêu và phạm vi của đánh giá rủi ro

Rủi ro migration là khả năng một thay đổi trong quá trình chuyển đổi gây ra sự cố hoặc làm giảm chất lượng của hệ thống. Sự cố có thể xuất hiện ngay khi biên dịch, khi JVM nạp và liên kết class, trong quá trình xử lý nghiệp vụ, khi đọc dữ liệu cũ hoặc sau khi triển khai lên môi trường thật.

Đánh giá rủi ro cần trả lời được các câu hỏi:

- Thành phần nào sẽ thay đổi và thành phần nào đang phụ thuộc vào nó?
- Hợp đồng nào phải được giữ lại để các thành phần cũ tiếp tục hoạt động?
- Thay đổi nào có thể làm client cũ không liên kết được với thư viện mới?
- Dữ liệu, cấu hình, giao thức hoặc hành vi nào có thể thay đổi?
- Rủi ro nào có thể phát hiện trước khi phát hành, và rủi ro nào chỉ bộc lộ trong runtime?
- Bằng chứng nào chứng minh rủi ro đã được xử lý hoặc được chấp nhận?
- Nếu chuyển đổi thất bại, hệ thống có thể quay lại trạng thái hoạt động trước đó bằng cách nào?

Phạm vi đánh giá nên bao gồm cả thành phần trực tiếp được nâng cấp và các consumer chịu ảnh hưởng. Ví dụ, khi nâng một thư viện nội bộ, phạm vi không chỉ là repository của thư viện. Cần xem xét các ứng dụng, plugin, batch job, dịch vụ và module đã biên dịch với phiên bản cũ.

Một thay đổi có thể không gây lỗi trong ứng dụng được build lại toàn bộ nhưng vẫn làm hỏng một plugin được phát hành độc lập. Vì vậy, cần xác định rõ hai nhóm consumer:

| Nhóm consumer | Đặc điểm | Cách kiểm tra phù hợp |
|---|---|---|
| Consumer được build lại cùng migration | Có thể biên dịch lại mã nguồn với dependency mới | Build toàn bộ module và chạy test tích hợp |
| Consumer đã phát hành độc lập | Có thể tiếp tục dùng bytecode được biên dịch với API cũ | Chạy artifact cũ với dependency mới, kiểm tra liên kết và hành vi |
| Consumer bên ngoài không kiểm soát được | Không thể yêu cầu cập nhật đồng thời | Giữ API tương thích, kiểm thử contract và có kế hoạch hỗ trợ phiên bản |
| Consumer chỉ xuất hiện ở runtime | Plugin, reflection, service provider hoặc class loader động | Kiểm thử discovery, nạp class và đường thực thi thực tế |

Không nên đưa một thành phần vào phạm vi chỉ vì nó nằm trong cùng repository. Hãy dựa trên quan hệ phụ thuộc, đường triển khai và cách thành phần được nạp hoặc gọi khi chạy.

## 2. Thu thập dữ liệu trước khi chấm điểm rủi ro

Ma trận chỉ có giá trị khi đầu vào phản ánh đúng hệ thống. Trước khi chấm điểm, hãy lập một baseline mô tả trạng thái hiện tại.

### 2.1. Xác định phiên bản và artifact nền

Ghi nhận tối thiểu:

- Phiên bản Java dùng để biên dịch và phiên bản JVM dùng để chạy.
- Phiên bản Gradle, Maven hoặc build tool và các plugin liên quan.
- Phiên bản framework, thư viện nội bộ và dependency bên ngoài.
- Artifact đã phát hành: JAR, WAR, ZIP, image hoặc gói triển khai tương ứng.
- Cấu hình classpath hoặc module path và cách nạp plugin.
- Cấu hình runtime, biến môi trường, system properties và feature flags.
- Các profile triển khai và khác biệt giữa môi trường phát triển, kiểm thử, staging và production.

Phải phân biệt phiên bản khai báo trong build với artifact thực sự được nạp lúc chạy. Dependency resolution có thể chọn phiên bản khác với dự kiến do transitive dependency, dependency constraint, exclusion hoặc class loader.

### 2.2. Lập bản đồ quan hệ phụ thuộc

Với từng thành phần, xác định:

- Thành phần cung cấp API hoặc capability.
- Consumer gọi API đó trực tiếp hoặc thông qua abstraction.
- Quan hệ compile-time, runtime và test-time.
- Thành phần được triển khai cùng lúc hay có vòng đời phát hành riêng.
- Điểm tích hợp qua HTTP, messaging, database, file, serialization hoặc giao thức khác.
- Thành phần được nạp bằng classpath, module path, reflection, ServiceLoader hoặc plugin framework.

Ví dụ một đồ thị phụ thuộc đơn giản:

~~~text
                    +------------------+
                    |  shared-api v1   |
                    +------------------+
                       ^       ^     ^
                       |       |     |
             +---------+       |     +----------+
             |                 |                |
       +-----------+    +-------------+   +-------------+
       | service A |    | plugin B    |   | batch job C |
       +-----------+    +-------------+   +-------------+
          build cùng       phát hành         chạy độc lập
          migration        riêng
~~~

Service A có thể được build lại cùng thư viện mới. Plugin B và batch job C có thể vẫn giữ bytecode cũ. Ba consumer này có mức phơi nhiễm khác nhau dù cùng phụ thuộc vào một API.

### 2.3. Chụp lại hợp đồng hiện tại

Đối với thư viện Java, baseline nên ghi lại API công khai và các điểm mở rộng:

- Class, interface, enum, record và annotation công khai.
- Constructor, method và field mà consumer có thể truy cập.
- Tên, kiểu tham số, kiểu trả về, descriptor và access modifier.
- Quan hệ kế thừa, interface được triển khai và phương thức override.
- Generic signature, annotation và metadata mà framework hoặc reflection sử dụng.
- Hằng số compile-time có thể đã được nhúng vào bytecode consumer.
- Constructor hoặc factory method được framework gọi.
- Service provider, resource, tên class trong cấu hình và các điểm discovery.

Nếu có thể, lưu artifact cũ và kết quả phân tích API để so sánh với phiên bản mới. Không dùng source code hiện tại để suy đoán bytecode của một consumer đã phát hành từ lâu; hãy dùng đúng artifact consumer hoặc một fixture được biên dịch từ phiên bản nền.

## 3. Phân loại rủi ro trong Java migration

Một ma trận hữu ích không chỉ ghi “build có thể lỗi”. Nó phân loại các dạng hỏng khác nhau để chọn biện pháp kiểm tra tương ứng.

### 3.1. Rủi ro tương thích nhị phân

Đây là rủi ro khi bytecode đã biên dịch với API cũ không thể liên kết với class hoặc interface mới.

Các nguyên nhân thường gặp:

- Xóa hoặc đổi tên class, method, constructor hoặc field.
- Thay đổi descriptor của method do đổi tham số hoặc kiểu trả về.
- Đổi thành viên từ static sang instance hoặc ngược lại.
- Thu hẹp quyền truy cập.
- Thay class bằng interface hoặc thay đổi cấu trúc kế thừa không tương thích.
- Thêm abstract method khiến lớp triển khai cũ không có phần thực thi khi đường gọi được sử dụng.

Dấu hiệu runtime có thể gồm **NoSuchMethodError**, **NoSuchFieldError**, **NoClassDefFoundError**, **AbstractMethodError**, **IllegalAccessError** hoặc **IncompatibleClassChangeError**.

Biện pháp kiểm soát phù hợp là so sánh API nhị phân, chạy client đã biên dịch từ phiên bản cũ với artifact mới và kiểm thử các lớp triển khai hoặc plugin được phát hành độc lập.

### 3.2. Rủi ro tương thích mã nguồn

Mã nguồn cũ có thể không biên dịch được với API mới dù bytecode cũ vẫn chạy.

Ví dụ:

- Thêm overload làm một lời gọi trở nên mơ hồ.
- Thay đổi generic signature hoặc type inference.
- Thêm checked exception vào khai báo method.
- Thay đổi kiểu trả về làm ảnh hưởng đến mã nguồn gọi.
- Thay đổi quy tắc truy cập hoặc kiểu được kế thừa.
- Thay đổi annotation hoặc API mà annotation processor sử dụng.

Biện pháp kiểm soát là biên dịch các consumer từ source với dependency mới, đồng thời giữ riêng kiểm thử binary compatibility. Một kết quả build thành công không chứng minh rằng bytecode đã phát hành trước đó vẫn chạy được.

### 3.3. Rủi ro tương thích hành vi

API vẫn tồn tại nhưng cách hoạt động đã thay đổi.

Ví dụ:

- Method trả về kết quả khác hoặc thay đổi thứ tự phần tử.
- Ngoại lệ được ném ra thay đổi.
- Giá trị mặc định, timeout hoặc retry policy thay đổi.
- Thứ tự gọi callback hoặc tác dụng phụ thay đổi.
- Quy tắc transaction, đồng bộ hoặc concurrency thay đổi.
- Một API vốn chấp nhận null nay từ chối null.
- Một thao tác vốn idempotent nay tạo tác dụng phụ lặp lại.

Các thay đổi này thường không được phát hiện bằng so sánh descriptor. Cần kiểm thử contract, regression test và đối chiếu kết quả nghiệp vụ trên dữ liệu đại diện.

### 3.4. Rủi ro dữ liệu và serialization

Migration có thể thay đổi cách đọc, ghi hoặc diễn giải dữ liệu:

- Java serialization và serialVersionUID.
- JSON/XML field name, kiểu dữ liệu, nullability và default value.
- Database schema, index, constraint và kiểu cột.
- Message schema hoặc event version.
- Định dạng file, encoding, timezone và precision.
- Dữ liệu được cache hoặc lưu trong session.

Cần kiểm tra cả chiều đọc dữ liệu cũ và chiều ghi dữ liệu mới. Nếu hệ thống phải hỗ trợ rolling deployment, hãy xác định liệu phiên bản ứng dụng cũ và mới có thể cùng đọc/ghi dữ liệu trong giai đoạn chuyển tiếp hay không.

### 3.5. Rủi ro runtime và nền tảng

Một API có thể giữ nguyên nhưng runtime vẫn không tương thích:

- Bytecode được biên dịch bằng target Java mới hơn JVM triển khai hỗ trợ.
- Dependency yêu cầu class hoặc method của JDK không có ở runtime.
- Thay đổi classpath/module path hoặc module exports.
- Xung đột phiên bản thư viện do transitive dependency.
- Khác biệt class loader hoặc thứ tự nạp lớp.
- Thay đổi reflection, proxy, instrumentation hoặc annotation processing.
- Native library, TLS provider, charset hoặc hệ điều hành khác biệt.

Ví dụ, **UnsupportedClassVersionError** thường cho biết JVM đang chạy không hỗ trợ phiên bản class file. Đây là vấn đề tương thích nền tảng, không nhất thiết là thay đổi API nhị phân của thư viện.

### 3.6. Rủi ro vận hành và bảo mật

Đừng giới hạn khảo sát ở mã nguồn. Nâng phiên bản có thể làm thay đổi:

- Cách cấu hình, biến môi trường và secret được đọc.
- Health check, readiness, liveness và graceful shutdown.
- Logging, tracing, metrics và định dạng log.
- TLS, chứng thư, cipher suite và xác thực.
- Quyền file, user chạy tiến trình và network policy.
- Hiệu năng, mức dùng heap, thread, connection pool và latency.
- Khả năng rollback, tính tương thích của schema và artifact.

Các rủi ro này cần có bằng chứng ở môi trường triển khai gần production và có người chịu trách nhiệm vận hành xác nhận.

## 4. Xây dựng ma trận chấm điểm

Ma trận rủi ro nên đơn giản đủ để cả nhóm dùng nhất quán, nhưng phải thể hiện được xác suất, mức ảnh hưởng và độ khó phát hiện.

### 4.1. Chấm xác suất xảy ra

Có thể dùng thang 1 đến 5:

| Điểm | Mức | Mô tả tham khảo |
|---:|---|---|
| 1 | Hiếm | Chưa thấy đường phụ thuộc hoặc điều kiện gây lỗi; có bằng chứng kiểm soát tốt |
| 2 | Thấp | Có thể xảy ra nhưng phạm vi hẹp và đã có biện pháp kiểm soát đáng tin cậy |
| 3 | Trung bình | Có đường phụ thuộc thực tế; một số giả định chưa được xác minh |
| 4 | Cao | Đã có dấu hiệu không tương thích hoặc nhiều consumer chịu ảnh hưởng |
| 5 | Rất cao | Đã tái hiện lỗi, thay đổi phá vỡ hợp đồng hoặc điều kiện lỗi gần như chắc chắn xuất hiện |

Không chấm xác suất thấp chỉ vì chưa có báo cáo sự cố. Nếu chưa khảo sát plugin hoặc consumer bên ngoài, trạng thái đúng là chưa đủ bằng chứng để đánh giá.

### 4.2. Chấm mức ảnh hưởng

| Điểm | Mức | Mô tả tham khảo |
|---:|---|---|
| 1 | Không đáng kể | Ảnh hưởng nhỏ, dễ khôi phục, không tác động nghiệp vụ chính |
| 2 | Thấp | Một chức năng phụ bị ảnh hưởng, có workaround rõ ràng |
| 3 | Trung bình | Một nhóm consumer hoặc một luồng nghiệp vụ bị gián đoạn |
| 4 | Cao | Nhiều dịch vụ hoặc luồng nghiệp vụ quan trọng bị ảnh hưởng |
| 5 | Nghiêm trọng | Hệ thống ngừng hoạt động, mất/hỏng dữ liệu, vi phạm bảo mật hoặc không thể rollback an toàn |

Mức ảnh hưởng nên được xác định theo hậu quả thực tế đối với người dùng và vận hành, không theo số dòng code hoặc độ khó sửa.

### 4.3. Tính điểm và xếp mức

Công thức đơn giản:

~~~text
Risk Score = Likelihood x Impact
~~~

Với mỗi yếu tố từ 1 đến 5, điểm rủi ro nằm trong khoảng 1 đến 25.

Có thể bắt đầu với ngưỡng tham khảo sau:

| Điểm | Mức ưu tiên | Hướng xử lý |
|---:|---|---|
| 1–4 | Thấp | Theo dõi và ghi lại bằng chứng kiểm soát |
| 5–9 | Trung bình | Có biện pháp giảm thiểu và kiểm tra trước phát hành |
| 10–16 | Cao | Cần owner, kế hoạch xử lý và bằng chứng trước khi qua gate |
| 17–25 | Nghiêm trọng | Chặn chuyển đổi cho đến khi xử lý hoặc có quyết định chấp nhận chính thức ở cấp phù hợp |

Các ngưỡng này là ví dụ khởi đầu. Dự án có thể điều chỉnh theo mức độ quan trọng của hệ thống, nhưng phải dùng cùng một quy tắc trong toàn bộ đợt migration. Một rủi ro bảo mật hoặc mất dữ liệu có thể phải được coi là chặn phát hành dù điểm số tổng hợp thấp.

### 4.4. Ghi nhận độ khó phát hiện

Likelihood × Impact giúp ưu tiên, nhưng hai rủi ro có cùng điểm có thể cần cách xử lý khác nhau. Bổ sung trường **Detectability** để ghi mức độ dễ phát hiện:

| Mức | Ý nghĩa |
|---|---|
| Dễ | Có thể phát hiện bằng build, static analysis hoặc test tự động ổn định |
| Trung bình | Cần integration test, test môi trường hoặc dữ liệu đại diện |
| Khó | Chỉ xuất hiện ở consumer ít gặp, tải thực tế, thời điểm đặc biệt hoặc production |

Có thể dùng detectability như một thuộc tính bổ sung thay vì nhân vào điểm số. Cách này giúp tránh tạo ra một con số có vẻ chính xác nhưng che khuất lý do thực tế. Rủi ro khó phát hiện cần thêm quan sát runtime, canary, log hoặc kế hoạch kiểm tra riêng.

## 5. Mẫu ma trận rủi ro cho một đợt Java migration

Bảng dưới đây minh họa cách ghi nhận rủi ro. Điểm số chỉ là ví dụ để trình bày cách đánh giá; dự án phải thay bằng dữ liệu khảo sát thực tế.

| ID | Rủi ro / nguyên nhân | Ảnh hưởng | L | I | Điểm | Khả năng phát hiện | Biện pháp / bằng chứng cần có |
|---|---|---|---:|---:|---:|---|---|
| R-01 | Thư viện mới xóa method mà plugin cũ đang gọi | Plugin lỗi khi chạy với thư viện mới | 4 | 5 | 20 | Khó | Kiểm kê plugin, so sánh binary API, chạy plugin cũ với JAR mới |
| R-02 | Interface thêm abstract method | Consumer cũ có thể gặp AbstractMethodError | 3 | 4 | 12 | Trung bình | Kiểm kê implementation, dùng default method nếu phù hợp, test lớp triển khai cũ |
| R-03 | Consumer dùng hằng số compile-time đã được nhúng | Hành vi dùng giá trị cũ sau nâng cấp | 4 | 3 | 12 | Khó | Xác định constant public, thay bằng truy vấn runtime khi cần, kiểm thử client cũ |
| R-04 | JDK runtime thấp hơn class-file target | JVM không nạp được class mới | 2 | 5 | 10 | Dễ | Kiểm tra target release và JDK trên mọi môi trường triển khai |
| R-05 | Dependency transitive chọn phiên bản khác | Lỗi liên kết hoặc hành vi ngoài dự kiến | 3 | 4 | 12 | Trung bình | Lưu dependency graph, kiểm tra runtime classpath và integration test |
| R-06 | JSON field hoặc default value thay đổi | Consumer đọc dữ liệu sai hoặc mất trường | 3 | 5 | 15 | Khó | Contract test với payload cũ/mới, kiểm tra null/default và schema |
| R-07 | Cấu hình timeout hoặc connection pool thay đổi | Latency, timeout hoặc cạn tài nguyên | 2 | 4 | 8 | Trung bình | So sánh cấu hình hiệu lực, load test và quan sát metrics |
| R-08 | Thay đổi migration database không hỗ trợ rollback | Không thể quay về phiên bản trước an toàn | 2 | 5 | 10 | Khó | Thử restore, kiểm tra backward-compatible schema và runbook rollback |

Một rủi ro cần có ít nhất các trường:

- ID duy nhất.
- Mô tả nguyên nhân và điều kiện kích hoạt.
- Thành phần và consumer bị ảnh hưởng.
- Hậu quả đối với hệ thống hoặc nghiệp vụ.
- Likelihood, Impact, điểm và mức ưu tiên.
- Bằng chứng hiện có và phần chưa biết.
- Biện pháp phòng ngừa hoặc giảm thiểu.
- Kế hoạch kiểm tra và điều kiện hoàn tất.
- Owner chịu trách nhiệm.
- Trạng thái, hạn xử lý và rủi ro còn lại sau xử lý.

Không gộp nhiều nguyên nhân khác nhau vào một dòng chỉ để bảng ngắn hơn. Ví dụ, lỗi class-file version và lỗi NoSuchMethodError có nguyên nhân, cách phát hiện và biện pháp xử lý khác nhau; chúng nên là các rủi ro riêng.

## 6. Từ rủi ro đến biện pháp xử lý

Sau khi xếp mức, chọn cách xử lý có thể kiểm chứng. Bốn chiến lược thường dùng là:

| Chiến lược | Khi sử dụng | Ví dụ |
|---|---|---|
| Tránh rủi ro | Có thể thay đổi phạm vi hoặc thiết kế để loại bỏ điều kiện gây lỗi | Không xóa API cũ trong đợt phát hành cần hỗ trợ client cũ |
| Giảm thiểu | Có thể giảm xác suất hoặc hậu quả bằng kỹ thuật và kiểm thử | Giữ bridge method, thêm binary compatibility check |
| Chuyển giao / chia sẻ | Một phần rủi ro thuộc trách nhiệm nhà cung cấp hoặc nhóm khác | Yêu cầu nhà cung cấp dependency xác nhận phiên bản hỗ trợ |
| Chấp nhận có kiểm soát | Rủi ro còn lại nằm trong giới hạn cho phép và có người có thẩm quyền quyết định | Chấp nhận một thay đổi nhỏ có workaround và rollback đã thử |

“Chấp nhận” không có nghĩa là xóa dòng rủi ro khỏi bảng. Hãy lưu người phê duyệt, lý do, phạm vi, thời hạn hiệu lực, điều kiện theo dõi và phương án khi rủi ro xảy ra.

Rủi ro cao không tự động được giải quyết bằng cách tăng số lượng test. Chọn kiểm tra theo cơ chế lỗi:

- Thay đổi API nhị phân: so sánh API và chạy bytecode cũ.
- Thay đổi source compatibility: biên dịch consumer từ source.
- Thay đổi hành vi: contract và regression test.
- Thay đổi serialization hoặc schema: kiểm thử dữ liệu cũ và mới.
- Thay đổi runtime: kiểm tra trên đúng JDK, classpath, module path và cấu hình triển khai.
- Thay đổi hiệu năng: benchmark hoặc load test có baseline.
- Thay đổi vận hành: diễn tập triển khai, health check và rollback.

## 7. Xây dựng tiêu chí chấp nhận chuyển đổi

Tiêu chí chấp nhận (acceptance criteria) mô tả điều kiện cụ thể phải đạt trước khi chuyển đổi được coi là hoàn tất hoặc được phép đi qua một giai đoạn phát hành.

Một tiêu chí tốt cần:

1. **Cụ thể:** xác định thành phần, phiên bản và hành vi được kiểm tra.
2. **Đo được:** có kết quả hoặc ngưỡng để xác định đạt hay không đạt.
3. **Có thể tái hiện:** người khác có thể chạy lại và thu được bằng chứng tương đương.
4. **Có phạm vi:** nói rõ consumer, môi trường, dữ liệu và điều kiện áp dụng.
5. **Có owner:** biết ai xác nhận kết quả.
6. **Có xử lý khi thất bại:** quy định cách chặn, sửa, rollback hoặc xin chấp nhận ngoại lệ.

Tránh các câu chung chung như “ứng dụng chạy bình thường”, “không có lỗi nghiêm trọng” hoặc “đã test đầy đủ”. Chúng không cho biết phải chạy test nào, với artifact nào và cần bằng chứng gì.

### 7.1. Tiêu chí về build và source compatibility

Ví dụ:

- Tất cả module nằm trong phạm vi migration build thành công với JDK và build tool mục tiêu.
- Không có compilation error mới do API hoặc dependency thay đổi.
- Các consumer source được chỉ định biên dịch thành công với artifact mới.
- Không còn dependency phiên bản cũ ngoài danh sách ngoại lệ đã được phê duyệt.
- Build tái lập được từ commit và dependency lock hoặc cấu hình đã ghi nhận.

Cần ghi rõ build command, commit, JDK, profile và danh sách module. Một lệnh build thành công ở máy cá nhân không đủ nếu pipeline hoặc môi trường triển khai dùng cấu hình khác.

### 7.2. Tiêu chí về binary compatibility

Đây là nhóm quan trọng khi mục tiêu là tiếp tục chạy thành phần đã biên dịch mà không biên dịch lại.

Ví dụ:

- Các public và protected API thuộc hợp đồng hỗ trợ vẫn giữ descriptor và khả năng truy cập cần thiết, hoặc mọi thay đổi phá vỡ đã được liệt kê và phê duyệt.
- Công cụ so sánh API không báo thay đổi binary breaking ngoài danh sách ngoại lệ được chấp nhận.
- Tất cả consumer đại diện đã biên dịch với artifact nền đều chạy được với artifact mới trong môi trường mục tiêu.
- Không phát sinh lỗi liên kết như NoSuchMethodError, NoSuchFieldError, AbstractMethodError, IllegalAccessError hoặc IncompatibleClassChangeError trong các kịch bản kiểm thử đã xác định.
- Các plugin, implementation của interface và extension point cũ được nạp và thực thi thành công.

Cần định danh chính xác artifact cũ và mới bằng version hoặc checksum. Nếu test biên dịch client lại với dependency mới, test đó không chứng minh được binary compatibility.

### 7.3. Tiêu chí về hành vi nghiệp vụ

Ví dụ:

- Các contract test trọng yếu có cùng kết quả theo đặc tả đã thống nhất.
- Các mã trạng thái, exception contract, side effect và quy tắc retry quan trọng được giữ nguyên hoặc có thay đổi được phê duyệt.
- Các luồng nghiệp vụ quan trọng hoàn thành với dữ liệu đại diện.
- Không có regression vượt ngưỡng đã thống nhất về latency, throughput hoặc error rate.
- Các thay đổi hành vi chủ ý có migration note và test chứng minh hành vi mới.

Nếu một hành vi được phép thay đổi, tiêu chí phải mô tả rõ kết quả mới. Không nên ép mọi đầu ra phải giống hệt phiên bản cũ nếu migration có mục tiêu thay đổi nghiệp vụ đã được phê duyệt.

### 7.4. Tiêu chí về dữ liệu và tích hợp

Ví dụ:

- Payload hoặc bản ghi được tạo bởi phiên bản cũ vẫn đọc được trong giai đoạn tương thích đã cam kết.
- Consumer cũ và mới xử lý được schema/message theo chiến lược versioning.
- Không mất trường, sai kiểu, đổi timezone hoặc giảm precision ngoài chủ đích.
- Database migration hoàn tất và có phương án khôi phục đã được thử.
- Các API, message broker, file exchange và service contract vượt qua contract test.

Với rolling deployment, cần kiểm tra ít nhất các cặp tương tác liên quan: ứng dụng cũ với dữ liệu mới, ứng dụng mới với dữ liệu cũ và các producer/consumer chạy đồng thời.

### 7.5. Tiêu chí về runtime và vận hành

Ví dụ:

- Artifact khởi động được trên đúng JDK và cấu hình production target.
- Health check, readiness, liveness và graceful shutdown hoạt động đúng.
- Dependency được resolve đúng phiên bản; không có class trùng hoặc class loader conflict đã biết.
- Các secret, cấu hình và quyền truy cập được cung cấp đúng.
- Metrics, logging và tracing đủ để phát hiện lỗi sau triển khai.
- Các chỉ số hiệu năng và tài nguyên nằm trong ngưỡng được phê duyệt.
- Rollback đã được diễn tập hoặc có bằng chứng khôi phục tương đương.

### 7.6. Tiêu chí về tài liệu và hỗ trợ

Ví dụ:

- Danh sách breaking changes và API deprecated được công bố.
- Hướng dẫn migration có ví dụ cho consumer cần thay đổi.
- Danh sách consumer được xác nhận đã cập nhật hoặc thuộc nhóm được hỗ trợ chạy bytecode cũ.
- Runbook triển khai, kiểm tra sau triển khai và rollback đã được cập nhật.
- Owner kỹ thuật và owner vận hành xác nhận phần thuộc trách nhiệm của họ.

## 8. Ví dụ bộ tiêu chí chấp nhận có thể dùng làm gate

Bộ tiêu chí sau minh họa cách chuyển mục tiêu migration thành các điều kiện có thể kiểm tra. Các ngưỡng cần được điều chỉnh theo SLA và mức độ quan trọng của hệ thống.

| Gate | Tiêu chí đạt | Bằng chứng |
|---|---|---|
| G1 — Phạm vi | 100% module, service, plugin và consumer đã biết được phân loại theo mức ảnh hưởng; mục chưa rõ có owner và hạn xác minh | Dependency inventory và consumer matrix |
| G2 — API | Không còn binary breaking change ngoài danh sách ngoại lệ đã được phê duyệt | Báo cáo Revapi/japicmp hoặc công cụ tương đương |
| G3 — Build | 100% module bắt buộc build thành công trên toolchain mục tiêu | CI run, commit, JDK và build log |
| G4 — Bytecode cũ | 100% bộ consumer cũ đại diện được chỉ định chạy qua kịch bản tương thích; không có lỗi liên kết ngoài ngoại lệ đã duyệt | Artifact checksum, test report và log runtime |
| G5 — Hành vi | Tất cả contract test trọng yếu đạt; regression nằm trong ngưỡng đã định | Test report, baseline và kết quả so sánh |
| G6 — Dữ liệu | Các fixture dữ liệu cũ/mới và migration schema đạt các kịch bản đọc/ghi đã xác định | Data compatibility report và migration test |
| G7 — Runtime | Ứng dụng khởi động, health check và các tích hợp bắt buộc hoạt động trên môi trường mục tiêu | Deployment test và observability snapshot |
| G8 — Vận hành | Rollback hoặc recovery đã được diễn tập; runbook và owner trực vận hành đã sẵn sàng | Biên bản rehearsal và runbook |
| G9 — Phê duyệt | Rủi ro cao/nghiêm trọng đã xử lý hoặc được chấp nhận bởi đúng người có thẩm quyền | Risk register và approval record |

Các tiêu chí có thể được chia thành ba trạng thái:

- **Pass:** có đủ bằng chứng và đạt ngưỡng.
- **Fail:** có bằng chứng không đạt; gate bị chặn cho đến khi xử lý.
- **Pending:** chưa có bằng chứng hoặc chưa chạy kiểm tra. Pending không được xem như Pass.

Một gate chỉ đạt khi toàn bộ tiêu chí bắt buộc của gate đó là Pass. Nếu có ngoại lệ, phải tham chiếu đến risk ID, người phê duyệt và điều kiện chấp nhận tương ứng.

## 9. Ví dụ chi tiết: chấp nhận thay thư viện dùng chung

Giả sử hệ thống có thư viện **shared-api** phiên bản 1 và nhiều consumer:

- Service A được build lại cùng đợt migration.
- Plugin B được biên dịch từ trước và triển khai độc lập.
- Batch C chỉ được chạy theo lịch, không thể cập nhật đồng thời.
- Một số consumer bên ngoài do nhóm khác quản lý.

Mục tiêu là phát hành **shared-api** phiên bản 2 nhưng tiếp tục hỗ trợ Plugin B và Batch C trong thời gian chuyển tiếp.

### 9.1. Rủi ro được ghi nhận

| ID | Rủi ro | Đánh giá ban đầu | Xử lý |
|---|---|---|---|
| R-01 | Phiên bản 2 xóa method mà Plugin B gọi | Cao | Giữ bridge method trong phiên bản 2 |
| R-02 | Phiên bản 2 thay đổi interface mà Batch C triển khai | Cao | Kiểm tra implementation cũ; ưu tiên default method nếu hợp đồng cho phép |
| R-03 | Phiên bản 2 thay đổi kết quả method dùng chung | Trung bình | Contract test và regression test trên dữ liệu đại diện |
| R-04 | Consumer bên ngoài chưa được kiểm kê | Chưa đánh giá được | Lập danh sách consumer và yêu cầu xác nhận artifact/version |

### 9.2. Tiêu chí chấp nhận cụ thể

| ID | Tiêu chí | Cách xác minh |
|---|---|---|
| AC-01 | Service A build thành công với shared-api v2 trên JDK mục tiêu | Chạy build trong CI từ commit đã chốt |
| AC-02 | Plugin B artifact cũ chạy được với shared-api v2 | Chạy nguyên JAR Plugin B đã lưu cùng JAR v2; không biên dịch lại Plugin B |
| AC-03 | Batch C artifact cũ nạp và thực thi thành công các đường gọi API đã sử dụng | Chạy fixture hoặc batch artifact cũ với runtime dependency mới |
| AC-04 | Không có lỗi liên kết trong các kịch bản đã xác định | Thu thập log test và kiểm tra lỗi JVM |
| AC-05 | Kết quả contract trọng yếu không đổi ngoài thay đổi đã duyệt | So sánh output, exception và side effect với baseline |
| AC-06 | Consumer bên ngoài đã có xác nhận hỗ trợ hoặc nằm trong danh sách ngoại lệ được phê duyệt | Lưu xác nhận và owner trong consumer inventory |
| AC-07 | Có thể quay lại artifact v1 trong điều kiện dữ liệu và cấu hình đã kiểm chứng | Diễn tập rollback trên môi trường tương đương |

### 9.3. Bằng chứng bắt buộc

Một kết luận “đã tương thích” nên truy xuất được đến:

- Commit và build ID tạo shared-api v2.
- Version hoặc checksum của shared-api v1 và v2.
- Version hoặc checksum của Plugin B và Batch C dùng trong test.
- JDK, build tool, runtime flags và dependency graph của lần chạy.
- Test report, log khởi động và log các kịch bản đã thực thi.
- Danh sách ngoại lệ và quyết định phê duyệt.
- Risk register sau xử lý, bao gồm rủi ro còn lại.

Nếu Plugin B đã được biên dịch lại với v2 trước khi test, AC-02 chưa được chứng minh. Phải chạy đúng bytecode cũ để xác nhận mục tiêu không cần biên dịch lại.

## 10. Liên kết rủi ro với tiêu chí và bằng chứng

Rủi ro và tiêu chí chấp nhận cần liên kết hai chiều. Mỗi rủi ro quan trọng phải có ít nhất một biện pháp kiểm soát hoặc một quyết định chấp nhận. Mỗi tiêu chí quan trọng phải chỉ ra rủi ro hoặc mục tiêu mà nó đang kiểm soát.

Một cấu trúc quản lý có thể dùng:

~~~text
Risk ID
  -> nguyên nhân và hậu quả
  -> biện pháp giảm thiểu
  -> Acceptance Criteria ID
  -> test / kiểm tra cụ thể
  -> evidence location
  -> kết quả Pass / Fail / Pending
  -> owner xác nhận
~~~

Ví dụ:

| Risk ID | Acceptance Criteria | Kiểm tra | Evidence |
|---|---|---|---|
| R-01 | AC-02, AC-04 | Chạy plugin cũ với thư viện mới | Plugin compatibility test report |
| R-02 | AC-03, AC-04 | Chạy implementation cũ của interface | Legacy implementation test |
| R-03 | AC-05 | So sánh contract output | Regression report |
| R-04 | AC-06 | Đối chiếu danh sách consumer | Consumer confirmation record |

Nếu một test thất bại, cần cập nhật trạng thái rủi ro và đánh giá lại điểm sau khi có thêm dữ liệu. Không được đánh dấu rủi ro đã đóng chỉ vì một test liên quan đã chạy; phải kiểm tra test có bao phủ đúng điều kiện gây lỗi hay không.

## 11. Tổ chức các gate theo tiến trình migration

Không nên đợi đến cuối dự án mới kiểm tra toàn bộ tiêu chí. Chia chúng thành các gate theo thời điểm sẽ giúp phát hiện sớm những giả định sai.

### Gate A — Hoàn tất khảo sát

Điều kiện đi qua:

- Phạm vi module và consumer đã được xác định.
- Baseline artifact, toolchain và runtime đã được lưu.
- Dependency inventory và consumer matrix có owner.
- Các rủi ro chưa rõ được ghi nhận là Pending, có kế hoạch xác minh.
- Mục tiêu tương thích và nhóm consumer cần hỗ trợ được thống nhất.

### Gate B — Thiết kế chuyển đổi được chấp nhận

Điều kiện đi qua:

- Các API hoặc schema có thay đổi đã được phân loại.
- Các breaking change có phương án giữ tương thích, adapter hoặc lịch chuyển đổi.
- Rủi ro cao có biện pháp, owner và tiêu chí kiểm tra.
- Kế hoạch test có consumer cũ, dữ liệu cũ và runtime mục tiêu.
- Chiến lược rollback phù hợp với thay đổi code và dữ liệu.

### Gate C — Kiểm chứng kỹ thuật đạt

Điều kiện đi qua:

- Build và source compatibility đạt.
- Binary compatibility test với artifact cũ đạt.
- Contract, regression, data và integration test bắt buộc đạt.
- Các lỗi còn lại được liên kết đến risk ID và có quyết định rõ ràng.
- Báo cáo bằng chứng có thể truy xuất.

### Gate D — Sẵn sàng triển khai

Điều kiện đi qua:

- Artifact đúng commit và checksum đã được xác nhận.
- Cấu hình, secret, runtime và dependency đã được kiểm tra.
- Canary hoặc rollout strategy đã được chuẩn bị nếu cần.
- Dashboard, log, alert và người trực vận hành sẵn sàng.
- Rollback hoặc recovery đã được diễn tập.
- Rủi ro còn lại được chấp nhận bởi đúng owner.

### Gate E — Xác nhận sau triển khai

Điều kiện hoàn tất:

- Health check và luồng nghiệp vụ trọng yếu đạt.
- Không có lỗi liên kết hoặc lỗi tương thích mới trong khoảng quan sát đã định.
- Error rate, latency và resource usage nằm trong ngưỡng.
- Consumer độc lập đã được xác nhận hoạt động hoặc có kế hoạch chuyển đổi được theo dõi.
- Rủi ro phát sinh được cập nhật và có owner.

Thời gian quan sát phải phù hợp với chu kỳ sử dụng thực tế. Với batch chạy mỗi ngày hoặc mỗi tuần, kiểm tra ngay sau deployment không đủ để chứng minh batch đã tương thích.

## 12. Quyết định rollback và quản lý rủi ro còn lại

Rollback cần được thiết kế cùng migration, đặc biệt khi có thay đổi schema hoặc dữ liệu.

Trước khi chọn rollback, hãy xác định:

- Artifact và cấu hình phiên bản trước còn sẵn sàng không?
- Database schema mới có còn tương thích với ứng dụng cũ không?
- Dữ liệu được ghi bởi phiên bản mới có thể được phiên bản cũ đọc không?
- Message hoặc event đã phát ra có thể được consumer cũ xử lý không?
- Có thao tác nào không thể đảo ngược, như gửi thanh toán, phát thông báo hoặc xóa dữ liệu không?
- Ai có quyền quyết định rollback và ngưỡng kích hoạt là gì?

Với database, chiến lược mở rộng rồi thu hẹp (expand and contract) thường giúp giảm rủi ro:

1. Mở rộng schema theo cách phiên bản cũ vẫn hoạt động.
2. Triển khai code mới có thể đọc/ghi theo quy tắc tương thích.
3. Di chuyển dữ liệu và consumer theo giai đoạn.
4. Xác nhận không còn consumer dùng cấu trúc cũ.
5. Chỉ sau đó mới loại bỏ cột, field hoặc đường xử lý cũ.

Không giả định rằng rollback code đồng nghĩa rollback dữ liệu. Nếu code mới đã ghi dữ liệu theo định dạng mà code cũ không đọc được, quay lại binary cũ có thể làm hệ thống hỏng thêm.

Rủi ro còn lại (residual risk) là phần rủi ro vẫn tồn tại sau khi đã thực hiện biện pháp kiểm soát. Hãy đánh giá lại likelihood và impact dựa trên bằng chứng mới, ghi rõ phần chưa thể kiểm thử và đặt điều kiện theo dõi. Nếu phạm vi consumer chưa đầy đủ, rủi ro không thể được coi là đã biến mất chỉ vì test hiện có đều Pass.

## 13. Mẫu ghi nhận để nhóm có thể áp dụng

### 13.1. Mẫu risk register

~~~text
Risk ID:
Tên rủi ro:
Thành phần / consumer:
Nguyên nhân:
Điều kiện kích hoạt:
Hậu quả:
Likelihood (1-5):
Impact (1-5):
Risk Score:
Detectability:
Bằng chứng hiện có:
Điểm chưa xác minh:
Biện pháp xử lý:
Acceptance Criteria liên quan:
Test / kiểm tra:
Owner:
Due date:
Trạng thái: Open / Mitigating / Pending / Accepted / Closed
Residual risk:
Người chấp nhận (nếu có):
Evidence location:
~~~

### 13.2. Mẫu acceptance criteria

~~~text
AC ID:
Tên tiêu chí:
Mục tiêu tương thích:
Phạm vi module / consumer:
Artifact hoặc phiên bản đầu vào:
Môi trường và điều kiện:
Hành động kiểm tra:
Kết quả mong đợi:
Ngưỡng Pass:
Điều kiện Fail:
Bằng chứng cần lưu:
Owner xác nhận:
Risk ID liên quan:
Gate áp dụng:
~~~

### 13.3. Mẫu quyết định ngoại lệ

~~~text
Exception ID:
Risk ID:
Tiêu chí không đạt hoặc chưa thể kiểm chứng:
Lý do:
Phạm vi consumer bị ảnh hưởng:
Tác động nếu xảy ra:
Biện pháp bù:
Điều kiện theo dõi:
Thời hạn chấp nhận:
Điều kiện hết hiệu lực:
Người có thẩm quyền chấp nhận:
Bằng chứng:
~~~

Mẫu ngoại lệ cần được dùng có kiểm soát. Một mục Pending do thiếu test không nên được chuyển thành Accepted chỉ để vượt gate. Phải có lý do, phạm vi, biện pháp bù, thời hạn và người chịu trách nhiệm.

## 14. Checklist hoàn tất khảo sát rủi ro và tiêu chí chấp nhận

- [ ] Xác định phiên bản nền, artifact, JDK, build tool và runtime thực tế.
- [ ] Lập danh sách module, service, plugin, batch và consumer bên ngoài.
- [ ] Ghi nhận quan hệ compile-time, runtime và triển khai độc lập.
- [ ] Chụp baseline API và các điểm mở rộng quan trọng.
- [ ] Phân loại rủi ro binary, source, behavior, data, runtime, security và operations.
- [ ] Chấm likelihood và impact theo cùng một thang điểm.
- [ ] Ghi độ khó phát hiện và bằng chứng còn thiếu.
- [ ] Gán owner, biện pháp xử lý và acceptance criteria cho rủi ro quan trọng.
- [ ] Có kiểm thử chạy bytecode consumer cũ với artifact mới.
- [ ] Có kiểm thử source compatibility, behavior, data và runtime phù hợp.
- [ ] Định nghĩa Pass, Fail, Pending và điều kiện ngoại lệ.
- [ ] Liên kết mỗi tiêu chí với test và evidence cụ thể.
- [ ] Xác định gate, người phê duyệt và điều kiện rollback.
- [ ] Đánh giá residual risk trước khi triển khai và sau thời gian quan sát.

Một ma trận rủi ro có ích khi nó giúp nhóm quyết định phải kiểm tra điều gì trước, ai chịu trách nhiệm và bằng chứng nào đủ để tiếp tục. Một bộ tiêu chí chấp nhận có ích khi bất kỳ thành viên nào cũng có thể tái hiện phép kiểm tra và kết luận Pass, Fail hoặc Pending từ cùng một artifact, môi trường và dữ liệu. Khi hai phần này được liên kết, migration có thể được quản lý bằng bằng chứng cụ thể thay vì dựa vào cảm giác rằng hệ thống đã chạy thử và có vẻ ổn.
