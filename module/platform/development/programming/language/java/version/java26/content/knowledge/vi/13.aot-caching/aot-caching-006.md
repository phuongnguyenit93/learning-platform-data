# Chọn tải huấn luyện đại diện cho ứng dụng

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao AOT cache cần một lần chạy huấn luyện với workload đại diện.
- Phân biệt dữ liệu về class loading/linking, method profile và object caching.
- Chọn kịch bản, tỷ lệ request, dữ liệu và mức đồng thời gần với production.
- Thiết kế training run an toàn cho ứng dụng có side effect như ghi database, gửi email hoặc phát message.
- Chọn cách tạo cache một bước hoặc tách riêng training và assembly.
- Kiểm tra cache có tương thích và được JVM nạp trong production hay không.
- Đo startup, warmup và tài nguyên để xác định workload huấn luyện có đem lại lợi ích thực tế.

## 1. Training run có vai trò gì?

AOT cache của HotSpot giúp giảm một phần công việc JVM phải lặp lại khi khởi động ứng dụng. Cache được tạo từ những quan sát thu thập trong một lần chạy ứng dụng trước đó. Lần chạy này gọi là **training run**.

Trong training run, ứng dụng phải thực sự chạy các luồng xử lý cần được tối ưu. JVM quan sát những lớp được nạp/liên kết, những method được thực thi và các object đủ điều kiện để đưa vào AOT cache. Sau đó, bước assembly tạo cache để những lần chạy sau có thể sử dụng.

Training không phải thao tác phân tích source code tĩnh. Nếu một endpoint hoặc một nhánh nghiệp vụ chưa từng chạy trong training, JVM không thể dựa vào lần chạy đó để quan sát đầy đủ lớp và hành vi của nhánh ấy.

Ví dụ, nếu training chỉ khởi động một HTTP server rồi gửi một request health check, cache có thể thiếu các lớp và method chỉ được dùng khi người dùng đăng nhập, tìm kiếm, thanh toán hoặc tải báo cáo. Ứng dụng vẫn chạy đúng khi production gọi các chức năng đó, nhưng chúng có thể phải chịu chi phí nạp lớp và warmup như trước.

## 2. Training quan sát ba nhóm hành vi

Cần thiết kế workload dựa trên mục tiêu của từng nhóm dữ liệu.

| Nhóm | JVM quan sát điều gì? | Workload cần có |
|---|---|---|
| Class loading và linking | Lớp nào được nạp, khởi tạo và liên kết trong các luồng xử lý. | Khởi động ứng dụng và gọi các chức năng cần sẵn sàng nhanh. |
| Method execution profile | Method nào được gọi thường xuyên, nhánh và kiểu thực thi nào xuất hiện trong training. | Chạy đủ lâu các đường xử lý thường gặp với tỷ lệ gần production. |
| AOT object caching | Một số object heap đủ điều kiện để lưu và tái sử dụng khi khởi động. | Chạy các bước khởi tạo tạo ra object dùng chung, ổn định và có thể tái sử dụng. |

JEP 483 (JDK 24) đưa vào AOT class loading và linking. JEP 515 (JDK 25) bổ sung AOT method profiling để profile thu thập trong training có thể được sử dụng sớm hơn khi ứng dụng chạy lại. JEP 516 (JDK 26) mở rộng AOT object caching để hoạt động với mọi garbage collector HotSpot, bao gồm ZGC.

Method profile từ training là điểm khởi đầu cho JIT, không phải bản biên dịch native cố định cho mọi tình huống. Trong production, JVM vẫn tiếp tục quan sát hành vi thật, profiling và biên dịch lại khi cần. Nếu workload production khác đáng kể với training, JIT vẫn có thể thích nghi, nhưng lợi ích warmup ban đầu có thể giảm.

AOT cache không phải snapshot trạng thái nghiệp vụ. Không dùng nó để khôi phục session người dùng, giao dịch, nội dung request, dữ liệu database hoặc trạng thái runtime cần thay đổi giữa các lần chạy.

## 3. Xác định workload production trước khi huấn luyện

Đừng bắt đầu bằng việc chọn một bộ test có sẵn. Trước tiên, hãy xác định ứng dụng thực sự làm gì trong môi trường triển khai.

Có thể lấy thông tin từ:

- Access log, API gateway metrics hoặc request metrics.
- Phân bố endpoint và tỷ lệ request theo chức năng.
- Số lượng người dùng đồng thời và thời điểm tải cao.
- Kích thước payload, kích thước batch và phân bố dữ liệu.
- Các bước khởi tạo sau startup như kết nối pool, nạp schema, dựng router hoặc nạp metadata.
- Các consumer, scheduler và background worker hoạt động ngay sau khi service sẵn sàng.
- Các luồng ít gặp nhưng bắt buộc phải sẵn sàng nhanh, ví dụ xác thực hoặc xử lý giao dịch quan trọng.

Nên lấy dữ liệu trong một khoảng thời gian đủ đại diện cho chu kỳ sử dụng. Nếu ứng dụng có giờ cao điểm, ngày chốt sổ hoặc batch theo lịch, cần xác định các luồng đó có nằm trong mục tiêu warmup hay không.

Không lấy riêng một ngày bất thường, một đợt stress test hoặc một kịch bản kiểm thử hiếm gặp làm đại diện cho toàn bộ production. Workload training cần phản ánh cách ứng dụng thường chạy sau khi khởi động.

## 4. Phân biệt độ phủ class với tỷ lệ method nóng

Hai mục tiêu này liên quan nhưng không giống nhau.

**Độ phủ class loading** cần các luồng xử lý quan trọng được thực thi ít nhất một lần để JVM quan sát các lớp cần dùng. Ví dụ, nếu ứng dụng có endpoint đăng nhập, tìm kiếm và xuất báo cáo, training nên gọi cả ba nếu chúng thuộc phạm vi cần tối ưu startup.

**Method profiling** cần các đường xử lý phổ biến được thực thi đủ thường xuyên để JVM nhận biết method nóng. Gọi mỗi endpoint đúng một lần có thể giúp nạp lớp, nhưng thường không đủ để thể hiện chính xác hành vi thường xuyên của ứng dụng.

Do đó, hãy kết hợp:

1. Một lượt khởi động với cấu hình production-like.
2. Các smoke request để đi qua những đường xử lý quan trọng.
3. Một workload có tỷ lệ request và mức đồng thời gần với production.
4. Các bước khởi tạo hoặc background task thật sự cần chạy sớm sau startup.

Không cần chạy mọi test case trong test suite. Những test hiếm, framework kiểm thử, mock framework và công cụ chẩn đoán có thể nạp thêm nhiều lớp không được dùng trong production. Việc đưa chúng vào training có thể làm cache lớn và kém tập trung.

## 5. Xây dựng ma trận workload

Một ma trận workload giúp nhóm thống nhất những gì cần được chạy trong training. Ví dụ dưới đây chỉ minh họa cách phân bổ; hãy thay tỷ lệ bằng số liệu của ứng dụng thật.

| Kịch bản | Tỷ lệ minh họa | Mục đích | Dữ liệu cần đại diện |
|---|---:|---|---|
| Đọc danh sách và chi tiết | 50% | Đường xử lý phổ biến, đọc dữ liệu và serialize response | Kích thước danh sách, số trường, phân trang |
| Tìm kiếm và lọc | 25% | Query, validation, mapping và xử lý kết quả | Bộ lọc phổ biến, truy vấn ngắn/dài |
| Ghi hoặc cập nhật | 15% | Validation, transaction và cập nhật object graph | Payload hợp lệ, các trạng thái nghiệp vụ thường gặp |
| Xác thực và phân quyền | 8% | Security filter, token parsing và authorization | Vai trò, quyền và loại token thường dùng |
| Báo cáo hoặc chức năng quản trị | 2% | Đường ít gặp nhưng cần nạp lớp đúng | Dữ liệu đại diện, kích thước báo cáo |

Tỷ lệ trong bảng không phải cấu hình tối ưu mặc định. Nếu ứng dụng thực tế có 80% request tìm kiếm, training cũng phải phản ánh điều đó.

Mỗi kịch bản nên ghi:

- Endpoint hoặc entry point được gọi.
- Số lần gọi và tỷ lệ tương đối.
- Kích thước và phân bố dữ liệu đầu vào.
- Mức đồng thời.
- Các dependency được sử dụng.
- Những class hoặc module quan trọng cần được đi qua.
- Side effect có thể xảy ra và cách cô lập chúng.

Với ứng dụng không dùng HTTP, hãy thay endpoint bằng message type, command, scheduled job, batch partition hoặc luồng giao diện tương ứng.

## 6. Chọn mức đồng thời và thời lượng training

Training không nhất thiết phải mô phỏng tải cực đại. Mục tiêu là thu thập hành vi đại diện, đặc biệt các đường xử lý thường gặp và method nóng.

Khi chọn mức đồng thời, cân nhắc:

- Số request đồng thời bình thường.
- Số worker và thread pool thực tế.
- Các tác vụ nền khởi chạy cùng thời điểm.
- Tỷ lệ request đọc/ghi.
- Các luồng có dùng chung cache, pool hoặc lock.
- Hành vi khi dependency phản hồi chậm.

Nếu production thường chạy 20 request đồng thời nhưng training chỉ chạy tuần tự, profile có thể không phản ánh đầy đủ cách ứng dụng được thực thi. Ngược lại, nếu training chạy hàng nghìn request đồng thời trong khi production hiếm khi đạt mức đó, profile có thể bị chi phối bởi workload bất thường.

Thời lượng training cần đủ để các luồng quan trọng được thực thi và các method thường dùng có cơ hội trở thành hot method. Không có một số phút cố định phù hợp cho mọi ứng dụng. Hãy dựa trên:

- Thời gian startup và khởi tạo thành phần.
- Số vòng xử lý cần thiết để method profile có ý nghĩa.
- Mức ổn định của phân bố request.
- Thời gian và chi phí tạo cache.
- Khả năng tái hiện workload trong CI hoặc staging.

Tránh kéo dài training chỉ để tạo một file cache lớn hơn. Training dài có thể ghi nhận các luồng hiếm hoặc tác vụ một lần không đại diện cho hoạt động thường xuyên. Hãy ưu tiên workload đúng hơn workload dài.

## 7. Training cho ứng dụng có side effect

Training run thực thi ứng dụng thật. Vì vậy, nó có thể gửi email, ghi database, tạo đơn hàng, phát message, cập nhật cache hoặc gọi dịch vụ bên ngoài.

Không chạy training tùy tiện trên production data. Hãy chọn một trong các cách sau:

- Dùng staging có cấu hình, schema và dependency gần production.
- Dùng dữ liệu đã ẩn danh hoặc dữ liệu tổng hợp có hình dạng tương tự production.
- Dùng tài khoản và namespace riêng để mọi thay đổi có thể xóa hoặc reset.
- Cô lập email, SMS, payment, message broker và các API ghi dữ liệu ra ngoài.
- Nếu cần mock dependency, chỉ mock ở ranh giới bên ngoài và bảo đảm đường code ứng dụng quan trọng vẫn được thực thi.

Mock không phải lúc nào cũng tốt hơn dependency thật. Một mock framework có thể nạp thêm lớp và làm workload khác với production. Nếu có thể, dùng môi trường kiểm thử có database hoặc service tương thích để giữ đường xử lý gần với production nhưng không gây side effect lên dữ liệu thật.

Đặc biệt chú ý các tác vụ không idempotent. Một lần training có thể thực hiện thao tác nhiều lần, vì workload cần lặp request để thu thập profile. Không dùng ID giao dịch thật, không gửi thanh toán thật và không phát message vào topic production nếu chưa có cơ chế cô lập.

## 8. Ví dụ training cho HTTP service

Giả sử ứng dụng được đóng gói trong app.jar và có các endpoint:

- GET /health
- POST /login
- GET /orders
- GET /orders/{id}
- POST /orders
- GET /reports/monthly

Một training run có thể được tổ chức như sau:

1. Khởi động ứng dụng bằng đúng JDK và cấu hình JVM dự kiến dùng ở production.
2. Chờ ứng dụng hoàn tất startup và readiness.
3. Gọi health check để xác nhận service sẵn sàng.
4. Gọi login với nhiều vai trò đại diện.
5. Gọi danh sách và chi tiết đơn hàng với nhiều kích thước dữ liệu.
6. Gọi tạo đơn hàng trong môi trường sandbox để đi qua validation, transaction và mapping.
7. Gọi báo cáo với dữ liệu đại diện nếu đây là chức năng cần tối ưu.
8. Phát một workload có tỷ lệ request tương tự production và mức đồng thời phù hợp.
9. Dừng ứng dụng theo quy trình graceful shutdown để hoàn tất training và tạo cache.

Không cần gọi health endpoint hàng nghìn lần nếu nó không đại diện cho workload thực tế. Cũng không nên chỉ gọi health endpoint rồi kết luận cache đã bao phủ các đường nghiệp vụ.

Nếu service có consumer, scheduler hoặc background worker, hãy xác định chúng có chạy ngay khi ứng dụng khởi động hay không. Chỉ đưa chúng vào training nếu hành vi đó tương ứng với production và các side effect đã được cô lập.

## 9. Ví dụ training cho batch và message consumer

### Batch application

Với batch application, workload đại diện có thể gồm:

- Đọc một tập dữ liệu có kích thước gần mức thông thường.
- Thực hiện parse, validate và transform.
- Ghi kết quả vào một đích kiểm thử.
- Xử lý một số bản ghi lỗi đại diện nếu đây là đường xử lý quan trọng.

Không nhất thiết chạy toàn bộ dataset production. Chọn mẫu dữ liệu có đủ các kiểu record và nhánh xử lý thường gặp. Nếu chỉ chạy một record đơn giản, những lớp và method chỉ dùng ở các record khác có thể không được quan sát.

### Message consumer

Với consumer, gửi các loại message phổ biến theo tỷ lệ thực tế:

- Message hợp lệ thường gặp.
- Message có payload lớn hoặc nhiều trường.
- Message cần gọi dependency.
- Message có lỗi định dạng nếu nhánh xử lý lỗi là một phần quan trọng của runtime.

Dùng topic, queue hoặc broker riêng. Không replay message production vào consumer training nếu việc xử lý có thể tạo side effect không thể đảo ngược.

## 10. Quan sát training bằng class log và JFR

Sau khi thiết kế workload, cần xác nhận ứng dụng đã đi qua những lớp và method mong muốn.

### Theo dõi class loading

Có thể dùng:

~~~bash
java -verbose:class -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -jar app.jar
~~~

Output giúp quan sát các class được nạp trong training. Log có thể rất lớn, nên lưu vào file và lọc theo package hoặc nhóm chức năng cần kiểm tra.

Một lựa chọn khác là JFR với event class loading. JFR có thể giúp xem thời điểm class được nạp và các method được sample trong quá trình training. Dùng JDK Mission Control hoặc công cụ JFR tương ứng để xem Hot Methods và Call Tree.

### Theo dõi method nóng

Method profile có ý nghĩa khi các đường xử lý thường gặp thực sự được thực thi. Dùng JFR để xác định method nào chiếm nhiều thời gian CPU hoặc được gọi thường xuyên. Nếu method quan trọng không xuất hiện, hãy kiểm tra:

- Workload có gọi đúng chức năng không?
- Dữ liệu có đi qua nhánh mong muốn không?
- Thời lượng training có đủ không?
- Có cấu hình feature flag làm tắt đường xử lý không?
- Dependency mock có bỏ qua phần code cần được quan sát không?

JFR và class log là công cụ chẩn đoán; bản thân việc ghi JFR không thay thế AOT training. Hãy tránh dùng cấu hình profiler nặng trong phép đo hiệu năng cuối cùng vì instrumentation có thể làm thay đổi hành vi và tài nguyên.

## 11. Tạo AOT cache sau khi chọn workload

### Cách một bước: training và assembly tự động

JDK 26 hỗ trợ cách tạo cache bằng một lệnh:

~~~bash
java -XX:AOTCacheOutput=app.aot -jar app.jar
~~~

Ở chế độ mặc định AOTMode=auto, khi chỉ định AOTCacheOutput, JVM chuyển sang training mode. Ứng dụng chạy với workload huấn luyện. Khi tiến trình kết thúc, JVM khởi chạy một JVM thứ hai để assembly và ghi file app.aot.

Vì vậy, với một service chạy liên tục, hãy có cách kết thúc training run có kiểm soát sau khi workload đã hoàn tất. Không để tiến trình training chạy mãi và chờ cache tự xuất hiện.

Cách một bước tiện lợi, nhưng JVM assembly sử dụng thêm tài nguyên. Theo hướng dẫn của Inside Java, tiến trình assembly có thể dùng heap cùng kích thước với heap training; môi trường cần tính đến mức bộ nhớ đỉnh gần gấp đôi heap đã cấu hình. Nếu máy/container bị giới hạn RAM, việc tạo cache có thể thất bại do thiếu tài nguyên.

### Cách ba giai đoạn: tách training và assembly

Nếu cần kiểm soát tài nguyên hoặc muốn assembly trên một máy mạnh hơn, tách riêng hai bước:

Training:

~~~bash
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -jar app.jar
~~~

Assembly:

~~~bash
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar
~~~

Trong bước training, chạy ứng dụng và workload đại diện rồi kết thúc tiến trình. JVM ghi dữ liệu quan sát vào app.aotconfig.

Trong bước assembly, JVM đọc file cấu hình và tạo app.aot. Bản thân ứng dụng không được thực thi ở giai đoạn assembly.

Có thể chạy training trên một instance có cùng hệ điều hành và kiến trúc CPU với production, sau đó assembly trên instance lớn hơn cùng nền tảng. Cách này hữu ích khi máy training có ít RAM nhưng workload cần phản ánh môi trường triển khai.

### Production run

Khi triển khai, trỏ JVM tới cache:

~~~bash
java -XX:AOTCache=app.aot -jar app.jar
~~~

Ở chế độ mặc định auto, JVM cố gắng nạp cache. Nếu cache không tương thích, JVM tiếp tục chạy ứng dụng mà không dùng cache. Đây là hành vi phù hợp cho production vì AOT cache là tối ưu hóa, không phải điều kiện để ứng dụng hoạt động đúng.

Khi cần kiểm tra fail-fast trong môi trường test, có thể dùng:

~~~bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot -jar app.jar
~~~

Chế độ on báo lỗi và dừng nếu cache không thể được nạp. Không nên bật chế độ này một cách vô thức trong production nếu môi trường có thể thêm JVM option hoặc agent ngoài dự kiến.

## 12. Điều kiện để training và production tương thích

AOT cache gắn với ứng dụng và môi trường cụ thể. Trước khi tạo cache, cần xác nhận:

- Cùng JDK release; nên giữ cùng bản phân phối và build trong quy trình tạo và sử dụng cache.
- Cùng hệ điều hành và kiến trúc CPU.
- Cùng artifact ứng dụng và dependency tương ứng.
- Classpath, JAR hoặc module path được khai báo nhất quán.
- Các JVM option có ảnh hưởng tới AOT cache tương thích giữa training, assembly và production.
- Các agent hoặc công cụ biến đổi class không làm thay đổi cấu trúc class theo cách cache không hỗ trợ.

AOT cache được tạo cho một ứng dụng cụ thể theo classpath, -jar hoặc module path. Khi đổi artifact, thêm hoặc nâng cấp thư viện, thay JDK release, chuyển OS/CPU architecture hoặc thay đổi cấu hình không tương thích, hãy tạo lại cache.

Với classpath, nên dùng danh sách JAR xác định rõ thay vì wildcard, thư mục hoặc nested JAR. Production classpath phải bao gồm các thành phần đã được training ghi nhận. Giữ nguyên timestamp của JAR trong quy trình training/assembly nếu build pipeline cần tái sử dụng cùng artifact.

Một số JVMTI agent hoặc class transformation có thể làm cache không sử dụng được. Nếu JVM bỏ qua cache, hãy kiểm tra AOT log thay vì giả định cache vẫn có tác dụng.

## 13. Liên hệ với GC trong JDK 26

JDK 26 có JEP 516 – Ahead-of-Time Object Caching with Any GC. Trước thay đổi này, cách biểu diễn object trong AOT cache bị ràng buộc với garbage collector và cấu hình heap nhất định. JDK 26 bổ sung định dạng object cache độc lập với GC, cho phép AOT object caching hoạt động với các collector HotSpot, bao gồm ZGC.

Điều này có ý nghĩa khi chọn workload:

- Nếu production dùng ZGC vì yêu cầu độ trễ thấp, vẫn có thể dùng AOT cache.
- Nếu production dùng G1 hoặc collector khác, vẫn cần đo startup và warmup trên collector mục tiêu.
- Không nên đổi GC chỉ để làm cache tương thích.
- Hãy dùng cấu hình GC gần production trong training để đánh giá sát hơn hành vi triển khai, dù JEP 516 đã mở rộng khả năng tương thích object cache.

AOT cache có thể dùng dạng object GC-specific để memory-map nhanh hoặc dạng GC-agnostic/streamable để dựng object theo GC đang chạy. Định dạng streamable có thể cần thêm CPU khi khởi động; hãy để JVM chọn mặc định trước, chỉ ép tùy chọn nâng cao sau khi benchmark chứng minh có lợi.

## 14. Đánh giá training có đại diện hay không

Không thể xác nhận workload tốt chỉ vì file .aot đã được tạo. Hãy đánh giá bằng hai nhóm bằng chứng.

**Bằng chứng về độ phủ:**

- Các lớp khởi động quan trọng xuất hiện trong class loading log hoặc JFR.
- Các endpoint, message type và background task thuộc phạm vi tối ưu đã được thực thi.
- Method quan trọng xuất hiện trong profile theo kỳ vọng.
- Không có nhiều lớp của test framework, mock hoặc công cụ chẩn đoán không cần thiết trong production.

**Bằng chứng về hiệu năng:**

- So sánh startup-to-ready giữa chạy không cache và chạy có cache.
- Đo warmup tới ngưỡng throughput/latency mục tiêu.
- Đo nhiều lần với cùng artifact, JDK, CPU, RAM và JVM options.
- Thử cả cold start và warm start nếu môi trường có khác biệt về filesystem page cache.
- Theo dõi CPU, heap, RSS và thời gian assembly.
- Kiểm tra cache thực sự được JVM nạp bằng AOT log.

Không chỉ đo thời gian tới hàm main. Với server, mốc quan trọng là khi readiness báo ứng dụng có thể nhận request. Nếu AOT làm startup nhanh hơn nhưng request đầu tiên vẫn chậm vì method chưa được profile, cần bổ sung workload cho đường xử lý đó.

## 15. Những lỗi chọn workload thường gặp

| Lỗi | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Chỉ chạy health check | Cache thiếu class và method của luồng nghiệp vụ | Gọi các endpoint và chức năng quan trọng |
| Chạy toàn bộ test suite | Nạp nhiều lớp test/mock không dùng trong production | Chọn smoke và integration scenario có mục tiêu |
| Dùng tỷ lệ request không giống production | Method profile lệch so với runtime thật | Dựa vào metrics/log thực tế để phân bổ workload |
| Training quá ngắn | Method nóng chưa được quan sát đủ | Tăng thời gian có kiểm soát, kiểm tra JFR |
| Training stress test cực đại | Profile có thể bị chi phối bởi tải bất thường | Dùng workload thường gặp và thêm kịch bản tải cao nếu thật sự quan trọng |
| Chạy trên dữ liệu production có side effect | Giao dịch, email hoặc message bị tạo lặp | Dùng staging/sandbox và dữ liệu an toàn |
| Thay artifact sau training | Cache không còn tương ứng với ứng dụng | Tạo lại cache từ đúng artifact release |
| Chỉ nhìn thấy file .aot | Có thể cache không tương thích hoặc bị JVM bỏ qua | Dùng AOT log và kiểm tra production run |
| Bắt buộc AOTMode=on trong mọi môi trường | Ứng dụng có thể dừng khi cache không dùng được | Dùng auto ở production, on cho kiểm tra fail-fast |

## 16. Checklist trước khi phát hành cache

- [ ] Workload được xây dựng từ dữ liệu sử dụng thực tế hoặc mô hình production đã được xác nhận.
- [ ] Các đường startup và chức năng quan trọng đã được thực thi.
- [ ] Tỷ lệ request, kích thước dữ liệu và mức đồng thời phù hợp.
- [ ] Side effect được cô lập; không dùng dữ liệu hoặc tài khoản production để tạo giao dịch thử.
- [ ] Không nạp thừa test framework, mock framework hoặc công cụ không chạy trong production.
- [ ] Đã kiểm tra class loading và method profile bằng log/JFR.
- [ ] Training và production dùng cùng JDK release, OS và CPU architecture.
- [ ] Artifact và classpath/module path được giữ nhất quán.
- [ ] Đã tính đủ bộ nhớ cho giai đoạn assembly.
- [ ] Đã xác nhận JVM thực sự nạp cache bằng AOT log.
- [ ] Đã benchmark startup-to-ready, warmup, CPU và memory với baseline không cache.
- [ ] Có quy trình tạo lại cache khi build hoặc dependency thay đổi.

## Kết luận

Training run quyết định những lớp, method profile và object nào có thể được chuẩn bị cho AOT cache. Một workload tốt phải phản ánh cả đường khởi động lẫn các chức năng thực tế, với tỷ lệ request, dữ liệu và mức đồng thời gần production. Chỉ chạy health check thường không đủ; chạy toàn bộ test suite hoặc stress test không đại diện cũng có thể làm cache kém tập trung. Hãy dùng ma trận workload dựa trên metrics, cô lập side effect, kiểm tra class loading và method nóng bằng JFR, sau đó xác nhận cache được nạp và cải thiện startup/warmup trên đúng môi trường triển khai. JDK 26 hỗ trợ AOT object caching với mọi GC theo JEP 516; AOT cache vẫn là tối ưu hóa phụ thuộc ứng dụng, JDK và nền tảng, nên cần được tạo lại khi các yếu tố đó thay đổi.

## Tài liệu tham khảo

- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [JEP 514: Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514)
- [JEP 515: Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515)
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [The java Command – JDK 26, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations – Inside Java](https://inside.java/2026/01/09/run-aot-cache/)
- [Performance Improvements in JDK 26 – Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
- [AOT Caching: Netflix's Practice vs OpenJDK's Theory – Inside Java Podcast](https://inside.java/podcast/70/)
