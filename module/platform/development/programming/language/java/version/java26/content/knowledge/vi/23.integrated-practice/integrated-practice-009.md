# Đo G1 và khởi động với AOT cache trên Java 26

## Mục tiêu

Sau bài thực hành này, bạn có thể:

- Giải thích JEP 522 thay đổi cách G1 đồng bộ card table và vì sao điều đó có thể tăng throughput.
- Đo GC pause, GC CPU time, heap, throughput và latency trong một workload có thể lặp lại.
- Phân biệt ảnh hưởng của G1 với ảnh hưởng của AOT cache.
- Tạo AOT cache bằng quy trình một bước hoặc tách training và assembly.
- Thiết kế training workload đủ đại diện cho production mà không tạo side effect nguy hiểm.
- Xác nhận JVM thực sự nạp cache và biết cách xử lý khi cache không tương thích.
- So sánh startup-to-ready và thời gian warmup bằng các lần chạy có cùng điều kiện.
- Đưa ra quyết định triển khai dựa trên số liệu thay vì chỉ dựa vào một kết quả benchmark.

## 1. Bài toán thực hành

Giả sử bạn vận hành một Java service có các chức năng:

- Khởi động HTTP server, nạp cấu hình và đăng ký dependency.
- Đọc danh mục, tìm kiếm và trả về dữ liệu JSON.
- Xử lý request có nhiều object liên kết như đơn hàng, khách hàng và dòng chi tiết.
- Tạo object, cập nhật các trường tham chiếu và sử dụng cache trong bộ nhớ.
- Chạy một số tác vụ nền sau khi service sẵn sàng.

Mục tiêu là kiểm tra hai thay đổi của HotSpot trong Java 26:

1. **JEP 522 – G1 GC: Improve Throughput by Reducing Synchronization:** giảm chi phí đồng bộ giữa application threads và các G1 refinement threads bằng cách thay đổi cách quản lý card table.
2. **JEP 516 – Ahead-of-Time Object Caching with Any GC:** mở rộng AOT cache để object caching hoạt động với mọi garbage collector HotSpot, bao gồm G1 và ZGC.

AOT cache còn kế thừa các cải tiến từ những release trước:

- JEP 483 trong JDK 24: AOT class loading và linking.
- JEP 515 trong JDK 25: lưu method execution profiles trong AOT cache để JIT có thể bắt đầu tối ưu sớm hơn.
- JEP 516 trong JDK 26: object caching hỗ trợ mọi GC.

Hai tính năng này giải quyết hai vấn đề khác nhau. JEP 522 cải thiện đường chạy của G1 khi ứng dụng đang hoạt động; AOT cache chuyển một phần công việc khởi động và warmup sang giai đoạn chuẩn bị trước. Phải đo riêng từng tác động.

## 2. G1 trong Java 26: thay đổi card table

G1 chia heap thành các region và duy trì remembered set để biết những vị trí bên ngoài collection set có thể tham chiếu vào region đang được thu gom. Heap được chia logic thành các card nhỏ. Khi ứng dụng ghi một tham chiếu, write barrier đánh dấu card tương ứng là dirty để G1 xử lý.

Trước JEP 522, application threads và các refinement threads cùng phối hợp trên card table. Refinement threads xử lý card dirty ở nền để cập nhật thông tin tham chiếu liên vùng. Việc phối hợp trên cùng cấu trúc cần đồng bộ và làm write barrier tốn chi phí hơn, nhất là khi workload cập nhật nhiều trường tham chiếu.

JDK 26 đưa vào card table thứ hai:

1. Application threads cập nhật active card table.
2. Refinement threads làm việc độc lập trên card table còn lại.
3. Khi G1 dự đoán quét active table có thể vượt pause-time target, G1 hoán đổi hai bảng một cách nguyên tử.
4. Refinement threads tiếp tục xử lý bảng đã được tách khỏi application threads, còn application threads ghi lên bảng đang hoạt động mới.

Sơ đồ khái quát:

~~~text
                 Application threads
                         |
                         | write barrier
                         v
                +-------------------+
                | Active card table |
                +-------------------+
                         |
                  atomic table swap
                         |
                         v
                +-------------------+
                | Card table for    |
                | refinement        |
                +-------------------+
                         ^
                         |
                 Refinement threads
~~~

JEP 522 không thay đổi semantics của Java, API GC hoặc cách ứng dụng cấp phát object. Đây là tối ưu implementation của G1 trong HotSpot. Không có cờ preview hoặc API ứng dụng mới cần bật để nhận cải tiến này.

Các phép đo được công bố cho thấy workload cập nhật tham chiếu nhiều có thể tăng throughput khoảng 5–15%; một số workload cập nhật tham chiếu ít hơn cũng có thể được lợi ở mức nhỏ. Trên x64, số instruction của write barrier trong một số trường hợp giảm từ khoảng 50 xuống khoảng 12. Pause time có thể giảm nhẹ. Đây là kết quả benchmark, không phải cam kết cho mọi ứng dụng. Card table bổ sung có thể tiêu thụ khoảng 2 MB native memory trên mỗi 1 GB heap.

JEP 522 chỉ áp dụng khi dùng G1. Nếu ứng dụng chạy ZGC, Parallel GC hoặc collector khác, không thể quy kết quả cho thay đổi card table của G1.

## 3. AOT cache trong Java 26 lưu điều gì?

AOT cache là một cơ chế của HotSpot để lưu những kết quả chuẩn bị trước cho một ứng dụng. Cache được tạo sau một lần chạy training và được sử dụng ở các lần chạy sau để giảm công việc JVM phải lặp lại.

| JDK | JEP | Đóng góp cho AOT cache |
|---|---|---|
| JDK 24 | JEP 483 | Class loading và linking được thực hiện trước và lưu vào cache |
| JDK 25 | JEP 515 | Method profiles từ training được lưu để hỗ trợ JIT tối ưu sớm hơn |
| JDK 26 | JEP 516 | Object caching có thể dùng với mọi GC, bao gồm ZGC |

Có thể hiểu ba nhóm thông tin như sau:

- **Class loading/linking:** lớp nào được nạp, phân tích và liên kết trong training.
- **Method profiles:** method nào được thực thi thường xuyên và trở thành hot method trong workload huấn luyện.
- **Cached heap objects:** một số object của runtime, ví dụ metadata Class và các object mà chúng tham chiếu như String hoặc byte array, có thể được chuẩn bị trong cache.

AOT cache không phải snapshot trạng thái nghiệp vụ. Không dùng nó để khôi phục session, transaction, dữ liệu request hoặc trạng thái database từ lần training trước. Ứng dụng vẫn khởi tạo trạng thái nghiệp vụ theo quy trình thông thường.

JEP 516 bổ sung định dạng object cache GC-agnostic để object có thể được dựng vào heap theo quy tắc của collector đang chạy. JDK có thể lựa chọn định dạng phù hợp theo heuristic; không cần đổi collector chỉ để dùng AOT cache. Khi đo một workload G1, vẫn giữ G1 ở cả training và production để so sánh công bằng.

## 4. Xác định các đại lượng cần đo

Không dùng một con số duy nhất để đánh giá cả G1 và AOT.

| Đại lượng | Cách hiểu | Mục tiêu |
|---|---|---|
| Startup-to-ready | Thời gian từ khi khởi chạy process đến khi readiness probe thành công | Đánh giá AOT class loading/linking và object caching |
| Warmup time | Thời gian từ readiness đến khi throughput/latency đạt trạng thái ổn định | Đánh giá lợi ích của method profiles và JIT |
| Throughput | Số request hoặc operation hoàn thành mỗi giây | Đánh giá năng lực xử lý tổng thể và tác động của G1 |
| Latency p50/p95/p99 | Phân vị thời gian xử lý request | Đánh giá trải nghiệm người dùng |
| GC pause | Thời gian ứng dụng bị dừng cho các pha GC stop-the-world | Đánh giá độ trễ do GC |
| GC CPU time | CPU time tích lũy dành cho hoạt động GC | Đánh giá chi phí CPU của collector |
| Allocation rate | Lượng object được cấp phát trong một đơn vị thời gian | Hiểu áp lực lên GC |
| Heap used/committed | Heap đang dùng và heap đã được cấp phát cho JVM | Phân biệt live set với dung lượng heap |
| RSS/process memory | Bộ nhớ resident của process | Kiểm tra tổng tài nguyên, gồm cả native memory |

Startup-to-ready không giống thời gian từ lúc gọi main đến lúc server mở socket. Dùng cùng một readiness probe cho mọi lần chạy và ghi thời điểm bắt đầu process bằng đồng hồ monotonic của hệ thống điều phối hoặc benchmark harness.

Warmup cũng cần một tiêu chí thống nhất. Ví dụ, định nghĩa service đã ổn định khi throughput và latency nằm trong biên dao động đã thống nhất qua ba khoảng đo liên tiếp. Biên dao động phải dựa trên workload của hệ thống; không có một ngưỡng phần trăm đúng cho mọi ứng dụng.

## 5. Chuẩn bị workload huấn luyện

Training run cần chạy các đường xử lý mà production thực sự sử dụng. Nếu chỉ khởi động server và gọi health check, cache có thể thiếu class và method của nghiệp vụ chính.

Với HTTP service, chọn một workload có các nhóm request như:

| Nhóm request | Ví dụ | Mục đích |
|---|---|---|
| Health/readiness | GET /health, GET /ready | Xác nhận service đã sẵn sàng |
| Đọc danh mục | GET /products, GET /products/{id} | Nạp class truy cập dữ liệu và serialize |
| Tìm kiếm | GET /search?q=... | Chạy validation, query, mapping và response |
| Xem trước đơn hàng | POST /orders/preview | Chạy các đường xử lý object graph mà không ghi dữ liệu thật |
| Xác thực | POST /login/test | Nạp security filter và token parsing nếu thuộc phạm vi ứng dụng |
| Tác vụ nền | Refresh cache, load metadata | Bao phủ công việc thực sự chạy sau startup |

Tỷ lệ request nên lấy từ application metrics hoặc access log đã được tổng hợp. Ví dụ, nếu production có 60% đọc danh mục, 25% tìm kiếm và 15% xem trước đơn hàng, training nên mô phỏng tỷ lệ gần như vậy. Không lấy tỷ lệ minh họa làm cấu hình mặc định.

Mức đồng thời, kích thước payload, phân bố dữ liệu và số vòng request cũng cần gần với production. Để thu thập method profile, các method phổ biến phải được thực thi đủ thường xuyên; gọi mỗi endpoint đúng một lần có thể giúp class loading nhưng chưa chắc tạo profile hữu ích.

### Cô lập side effect

Training run thực thi ứng dụng thật. Một request ghi có thể tạo đơn hàng, gửi email, phát message hoặc gọi dịch vụ thanh toán. Vì vậy:

- Dùng staging hoặc sandbox có cấu hình gần production.
- Dùng dữ liệu tổng hợp hoặc dữ liệu đã ẩn danh.
- Dùng namespace, topic, bucket và tài khoản riêng.
- Chặn các tích hợp có side effect không thể đảo ngược.
- Ưu tiên endpoint preview/read-only nếu mục tiêu chỉ là chạy qua đường xử lý.
- Không replay message production hoặc tạo giao dịch thật chỉ để làm nóng method.

Không cần chạy toàn bộ test suite. Framework test và mock framework có thể nạp nhiều class không có trong production, làm cache lớn và kém tập trung. Chọn smoke/integration scenarios có mục tiêu rõ ràng.

## 6. Ghi baseline G1 không dùng AOT cache

Đầu tiên, đo ứng dụng trên JDK 26 với G1 và tắt AOT cache. Dùng cùng heap, JVM flags, artifact, dataset và workload cho tất cả lần chạy.

Ví dụ dùng G1 tường minh để loại bỏ khác biệt do lựa chọn collector:

~~~bash
java -XX:+UseG1GC -XX:AOTMode=off -Xms2g -Xmx2g -Xlog:gc*,safepoint:file=logs/g1-no-aot-%p.log:time,uptime,level,tags -jar app.jar
~~~

Thay dung lượng heap theo môi trường thật. Giá trị 2 GB chỉ là ví dụ; điều quan trọng là giữ nguyên Xms/Xmx giữa các cấu hình cần so sánh.

Tạo thư mục logs trước khi chạy. Mỗi lần chạy nên có file log riêng để tránh ghi đè dữ liệu.

Chạy workload đã chọn, ghi lại:

- Thời gian process start đến readiness.
- Thời gian warmup đến ngưỡng ổn định.
- Throughput và latency p50/p95/p99.
- GC pause count, duration và loại collection.
- GC CPU time nếu có.
- Heap used/committed, allocation rate và process memory.
- Error rate và kết quả nghiệp vụ.

Đây là baseline để so sánh với cùng ứng dụng khi có AOT cache.

## 7. So sánh G1 giữa JDK 25 và JDK 26

Để quan sát tác động của JEP 522, chạy cùng artifact và workload trên JDK 25 và JDK 26, đều dùng G1 và đều tắt AOT cache:

~~~bash
java -XX:+UseG1GC -XX:AOTMode=off -Xms2g -Xmx2g -Xlog:gc*,safepoint:file=logs/jdk25-g1-%p.log:time,uptime,level,tags -jar app.jar
~~~

~~~bash
java -XX:+UseG1GC -XX:AOTMode=off -Xms2g -Xmx2g -Xlog:gc*,safepoint:file=logs/jdk26-g1-%p.log:time,uptime,level,tags -jar app.jar
~~~

Đảm bảo dependency, dữ liệu, heap, CPU quota, OS, container limit và tải nền tương đương. Chạy nhiều lần, luân phiên thứ tự JDK 25/JDK 26 nếu có thể để tránh ảnh hưởng do tải máy hoặc nhiệt độ CPU.

Để chạy đúng cùng một artifact trên cả JDK 25 và JDK 26, build phần ứng dụng dùng chung với baseline Java 25 (ví dụ javac --release 25) và không tham chiếu API chỉ có từ Java 26. Nếu cần đo MemoryMXBean.getTotalGcCpuTime(), chỉ lấy metric này ở lần chạy JDK 26 hoặc qua adapter/giám sát riêng; không đưa lời gọi method mới vào artifact dùng chung cho JDK 25. Nếu ứng dụng bắt buộc dùng API Java 26, hãy build hai artifact từ cùng commit và ghi rõ khác biệt đó trong báo cáo.

Nếu workload cập nhật nhiều trường tham chiếu, JDK 26 có thể cải thiện throughput nhờ JEP 522. Tuy nhiên, chênh lệch giữa hai JDK còn có thể đến từ các thay đổi runtime khác. Đây là phép so sánh trước/sau release, không phải bằng chứng duy nhất để quy toàn bộ mức tăng cho JEP 522.

JEP 522 không có cờ bật/tắt riêng. Không tìm cách tắt card table thứ hai hoặc chỉnh write barrier bằng cờ nội bộ để tạo baseline. Hãy so sánh các bản JDK và dùng workload reference-heavy để đánh giá tác động thực tế.

## 8. Tạo AOT cache bằng quy trình một bước

JDK 26 hỗ trợ tạo cache thuận tiện bằng tùy chọn AOTCacheOutput. Ở chế độ mặc định AOTMode=auto, khi chỉ định AOTCacheOutput, JVM tự chuyển sang training mode; khi ứng dụng kết thúc, JVM khởi chạy một JVM thứ hai để assembly và ghi cache.

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -XX:AOTCacheOutput=app.aot -Xlog:gc*,safepoint:file=logs/aot-training-%p.log:time,uptime,level,tags -jar app.jar
~~~

Quy trình:

1. Khởi động ứng dụng trong môi trường training.
2. Chờ readiness probe thành công.
3. Chạy workload đại diện theo tỷ lệ và mức đồng thời đã xác định.
4. Đợi các bước khởi tạo quan trọng hoàn tất.
5. Dừng ứng dụng theo graceful shutdown.
6. JVM thực hiện assembly và tạo file app.aot.

Với service chạy liên tục, cache chỉ được tạo sau khi tiến trình training kết thúc. Cần có cơ chế dừng service thử nghiệm có kiểm soát sau khi workload hoàn tất; không chờ cache xuất hiện khi process vẫn đang chạy.

### Lưu ý tài nguyên khi tạo cache một bước

JVM assembly là một process thứ hai. Theo hướng dẫn Inside Java, process assembly có heap riêng với kích thước tương đương heap của training JVM; do đó môi trường có thể cần bộ nhớ đỉnh gần gấp đôi Xmx đã cấu hình cho quy trình một bước.

Ví dụ, nếu training được cấu hình Xmx=2g, hãy dự trù thêm tài nguyên cho JVM assembly và các thành phần khác của hệ thống. Trong container nhỏ, quy trình một bước có thể thất bại vì thiếu RAM. Khi đó, tách training và assembly thành ba giai đoạn sẽ dễ kiểm soát hơn.

## 9. Tạo cache theo ba giai đoạn

Nếu muốn chạy training trên môi trường gần production nhưng assembly trên máy có nhiều CPU/RAM hơn, tách riêng các bước.

### Giai đoạn 1: Training

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -Xlog:gc*,safepoint:file=logs/aot-record-%p.log:time,uptime,level,tags -jar app.jar
~~~

Chạy workload đại diện như phần trước, sau đó graceful shutdown. JVM ghi dữ liệu quan sát vào app.aotconfig.

### Giai đoạn 2: Assembly

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar
~~~

JVM đọc file cấu hình và tạo app.aot. Ứng dụng không được thực thi trong giai đoạn assembly. Có thể thực hiện bước này trên máy lớn hơn cùng OS và kiến trúc CPU với môi trường triển khai.

### Giai đoạn 3: Production

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -XX:AOTCache=app.aot -Xlog:aot,class+path=info -Xlog:gc*,safepoint:file=logs/g1-aot-%p.log:time,uptime,level,tags -jar app.jar
~~~

Ở chế độ mặc định auto, JVM thử nạp cache. Nếu cache tương thích, các tối ưu AOT được sử dụng; nếu không tương thích, JVM tiếp tục chạy ứng dụng mà không dùng cache.

Dùng AOTMode=on trong staging để kiểm tra fail-fast:

~~~bash
java -XX:+UseG1GC -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot,class+path=info -jar app.jar
~~~

Nếu cache không thể nạp, chế độ on báo lỗi và dừng. Đây là cách kiểm tra cấu hình trong CI/staging; production thường nên giữ auto để ứng dụng vẫn chạy khi cache bị thiếu hoặc không tương thích.

## 10. Kiểm tra AOT cache có thực sự được dùng

Không kết luận cache hoạt động chỉ vì file app.aot tồn tại. Cần kiểm tra log khi JVM khởi động:

~~~bash
java -XX:AOTCache=app.aot -Xlog:aot,class+path=info -jar app.jar
~~~

Log giúp nhận biết cache có được tìm thấy và sử dụng hay bị bỏ qua vì mismatch. Nếu cache không được nạp, kiểm tra:

- JDK release có đúng không.
- Artifact và classpath/module path có giống training không.
- OS và CPU architecture có khớp không.
- Các JAR có bị rebuild hoặc thay đổi timestamp không.
- JVM options hoặc agent có làm cache không tương thích không.
- Cache file có tồn tại và có quyền đọc không.

Trong JDK 26, AOT object caching có thể hoạt động với G1, Parallel, Serial và ZGC. JEP 516 giải quyết giới hạn trước đó khiến object caching không dùng được với ZGC. Tuy vậy, cache vẫn gắn với ứng dụng, JDK release và nền tảng cụ thể; hỗ trợ mọi GC không có nghĩa cache có thể chuyển tùy ý giữa JDK hoặc OS/CPU khác nhau.

## 11. Các điều kiện để tái sử dụng cache

Training, assembly và production cần có cấu hình nhất quán. Trước khi phát hành cache, kiểm tra:

- **JDK:** dùng cùng JDK release cho training và production; nên giữ cùng vendor/build trong quy trình tạo cache để dễ tái lập.
- **Ứng dụng:** tạo cache từ đúng artifact và dependency sẽ triển khai.
- **Classpath/module path:** dùng danh sách JAR rõ ràng, tránh thư mục, wildcard hoặc nested JAR trong classpath training.
- **Classpath production:** phải là superset của classpath training.
- **JAR timestamps:** giữ nguyên timestamp của các JAR qua training và production.
- **Nền tảng:** cùng hệ điều hành và kiến trúc CPU.
- **JVM options:** giữ các tùy chọn tương thích giữa training và production.
- **JVMTI agents:** tránh agent gọi AddToBootstrapClassLoaderSearch hoặc AddToSystemClassLoaderSearch.
- **Artifact update:** build mới, thêm hoặc nâng cấp dependency thì tạo lại cache.

Không dùng cache của JDK 25 cho JDK 26 hoặc ngược lại. Cache là artifact riêng cho release JDK và ứng dụng đã được huấn luyện.

## 12. Đọc G1 log để hiểu GC đang làm gì

Unified logging là cách hiện hành để thu thập log GC trên HotSpot.

Ví dụ:

~~~bash
java -XX:+UseG1GC -Xlog:gc*,safepoint -jar app.jar
~~~

Các thông tin cần quan sát:

- Số lượng young GC và mixed GC.
- Pause duration và phân bố thời gian pause.
- Heap occupancy trước/sau collection.
- Thời gian từng pha GC nếu cần điều tra sâu.
- Concurrent marking có hoàn tất trước khi heap cạn hay không.
- Có evacuation failure hoặc Full GC hay không.
- Safepoint time có khác biệt lớn so với GC pause hay không.

Khi cần xem chi tiết từng pha:

~~~bash
java -XX:+UseG1GC -Xlog:gc+phases=debug -jar app.jar
~~~

Đây là lần chạy chẩn đoán sâu. Log debug có thể tăng lượng dữ liệu và chi phí I/O; không nên dùng cùng cấu hình debug nặng cho phép đo latency cuối cùng nếu chưa đánh giá overhead.

### Nhận diện dấu hiệu cần điều tra

| Dấu hiệu | Hướng kiểm tra |
|---|---|
| Young GC xảy ra dày đặc | Allocation rate, kích thước heap, tốc độ tạo object và tuổi thọ object |
| Pause tăng dần | Live set, số object phải copy, region được chọn và pha GC chiếm thời gian |
| Full GC | Old-generation occupancy, humongous objects, allocation pressure, concurrent marking và nguyên nhân gọi System.gc() |
| Evacuation failure | Heap còn đủ vùng đích hay không, tốc độ promotion và object pinned |
| GC CPU cao nhưng pause ngắn | Concurrent GC/refinement có thể đang dùng nhiều CPU ngoài pause |
| Throughput giảm khi tải tăng | CPU contention giữa application threads và GC threads, allocation và lock ứng dụng |

Không tăng heap hoặc chỉnh hàng loạt cờ G1 chỉ vì thấy GC xảy ra. Trước tiên xác định vấn đề là pause, throughput, allocation hay thiếu bộ nhớ. G1 được thiết kế để tự điều chỉnh young generation theo pause-time goal; đặt cố định young generation bằng các cờ như Xmn có thể hạn chế khả năng điều khiển này.

## 13. Đo GC CPU time bằng MemoryMXBean

Java 26 bổ sung method getTotalGcCpuTime() vào java.lang.management.MemoryMXBean. Method trả về CPU time tích lũy xấp xỉ dành cho hoạt động GC, đơn vị nanosecond.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

long before = memory.getTotalGcCpuTime();

// Chạy workload cần đo trong cùng process.

long after = memory.getTotalGcCpuTime();

if (before >= 0 && after >= before) {
    long gcCpuNanos = after - before;
    double gcCpuMillis = gcCpuNanos / 1_000_000.0;

    System.out.printf("GC CPU delta: %.3f ms%n", gcCpuMillis);
} else {
    System.out.println("GC CPU time is unavailable");
}
~~~

Cần hiểu giới hạn của metric:

- Giá trị là tổng tích lũy từ khi JVM chạy, vì vậy nên lấy hai mẫu và tính delta cho khoảng đo.
- Trả về -1 nếu JVM không hỗ trợ hoặc thông tin không khả dụng.
- Đây là CPU time, không phải wall-clock time và không phải tổng GC pause duration.
- Tổng CPU time có thể cộng dồn trên nhiều GC threads chạy song song.
- HotSpot tính cả overhead và các hoạt động implementation-specific; giá trị có thể khác 0 ngay cả khi chưa có một collection cycle rõ ràng.

Dùng metric này cùng GC log và process CPU time để hiểu tỷ lệ tài nguyên. Không lấy nó làm SLA hoặc so sánh trực tiếp giữa các JVM vendor mà chưa xác định semantics của implementation.

## 14. Ma trận thí nghiệm để tách ảnh hưởng

Thực hiện tối thiểu ba cấu hình:

| Cấu hình | JDK | GC | AOT cache | Mục đích |
|---|---|---|---|---|
| A | 25 | G1 | Tắt | Baseline trước JEP 522 |
| B | 26 | G1 | Tắt | Đánh giá thay đổi runtime/G1 trong JDK 26 |
| C | 26 | G1 | Bật | Đo lợi ích startup và warmup từ AOT cache |

Giữ cùng artifact tương thích, dataset, request mix, concurrency, CPU quota, heap và OS. Vì JDK 25 và 26 có nhiều thay đổi runtime, chênh lệch A/B là phép so sánh release-level. Dùng kiến thức JEP 522 và workload reference-heavy để giải thích xu hướng, nhưng không khẳng định mọi chênh lệch đều do riêng JEP 522.

Cấu hình B và C chạy cùng JDK 26, vì vậy chênh lệch startup-to-ready và warmup chủ yếu phản ánh việc dùng AOT cache, nếu các điều kiện khác được giữ nguyên.

Với mỗi cấu hình:

1. Thực hiện warmup theo cùng một quy trình nếu mục tiêu là steady state.
2. Đo ít nhất 10 lần chạy độc lập; tăng số lần nếu biến động còn lớn.
3. Luân phiên thứ tự chạy hoặc dùng máy thử nghiệm riêng để giảm ảnh hưởng tải nền.
4. Tách cold start và warm start nếu filesystem page cache ảnh hưởng đáng kể.
5. Ghi startup-to-ready, warmup time, throughput, p50/p95/p99, GC pause, GC CPU, heap và RSS.
6. Kiểm tra error rate và tính đúng của kết quả.
7. Báo cáo median, min/max và độ phân tán; không chỉ chọn lần chạy nhanh nhất.

Không chạy load generator trên cùng process JVM với ứng dụng được đo. Nếu cùng host, bảo đảm load generator không chiếm hết CPU hoặc RAM của service.

## 15. Đọc kết quả và đưa ra quyết định

Một báo cáo tốt cần giải thích điều gì thay đổi và vì sao.

### Ví dụ cách diễn giải

- Nếu B tăng throughput so với A trong workload cập nhật nhiều tham chiếu, đồng thời GC CPU hoặc pause giảm nhẹ, kết quả phù hợp với mục tiêu của JEP 522. Vẫn cần ghi nhận các thay đổi khác giữa JDK 25 và 26.
- Nếu C giảm startup-to-ready so với B và AOT log xác nhận cache được nạp, AOT cache đang giúp chuyển công việc class loading/linking và chuẩn bị object sang giai đoạn trước.
- Nếu startup nhanh hơn nhưng warmup không cải thiện, hãy kiểm tra workload training đã thực thi các method nóng chưa và JDK có lưu method profile phù hợp không.
- Nếu cache không được nạp, kiểm tra JDK, classpath, artifact, timestamp, OS/CPU và JVM options trước khi đánh giá hiệu năng.
- Nếu GC pause không đổi nhưng throughput tăng, điều đó vẫn có thể phù hợp với JEP 522 vì mục tiêu chính là giảm chi phí đồng bộ trên đường chạy ứng dụng.
- Nếu AOT cache làm startup chậm hơn, xem xét cold/warm filesystem cache, định dạng object cache, CPU cho streaming/materialization và dung lượng cache.

AOT cache chủ yếu nhắm startup và warmup. Không giả định steady-state throughput sẽ tăng đáng kể chỉ vì cache được bật. G1 JEP 522 nhắm throughput của collector; không giả định nó làm startup nhanh hơn.

### Những kết quả không nên kết luận

- Một lần chạy nhanh hơn không đủ chứng minh cải thiện.
- Ít GC pause hơn không luôn đồng nghĩa GC CPU thấp hơn.
- GC CPU time thấp không luôn đồng nghĩa p99 latency thấp.
- File AOT tồn tại không chứng minh JVM đã sử dụng cache.
- Throughput tăng 5–15% không phải cam kết của JEP 522 cho mọi workload.
- AOT cache tương thích với mọi GC không có nghĩa cache tương thích với mọi JDK, OS hoặc CPU.

## 16. Các lỗi thực hành thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Training chỉ gọi health check | Cache thiếu lớp và method nghiệp vụ | Chạy workload đại diện |
| Training dùng test suite quá rộng | Cache chứa nhiều class không chạy trong production | Chọn smoke/integration scenario có mục tiêu |
| Dùng dữ liệu production có side effect | Tạo giao dịch hoặc message thật nhiều lần | Dùng staging/sandbox |
| Không graceful shutdown training app | Chưa có bước assembly nên cache chưa được tạo | Kết thúc process có kiểm soát |
| One-step assembly thiếu RAM | JVM thứ hai cần thêm heap và tài nguyên | Tách record/create hoặc tăng tài nguyên |
| Rebuild JAR sau training | Cache không còn khớp artifact | Tạo lại cache sau mỗi build |
| Chuyển cache giữa JDK hoặc OS/CPU khác | JVM từ chối cache hoặc bỏ qua | Tạo cache trên đúng nền tảng |
| Chỉ nhìn startup time | Bỏ qua warmup và GC behavior | Đo cả startup, warmup, steady state và GC |
| Bật GC debug cho mọi benchmark | Log I/O làm sai lệch phép đo | Dùng log info cho benchmark, debug trong lần chẩn đoán riêng |
| Tinh chỉnh nhiều cờ G1 ngay từ đầu | Không biết thay đổi nào có tác động | Bắt đầu từ mặc định, thay một biến mỗi lần |
| Dùng AOTMode=on trong production | JVM có thể dừng nếu cache không nạp được | Dùng auto trong production, on để fail-fast ở staging |

## 17. Checklist hoàn thành bài thực hành

- [ ] Xác nhận ứng dụng thực sự dùng G1 trong các lần đo.
- [ ] Giữ nguyên artifact, dữ liệu, CPU quota, heap và workload.
- [ ] Tách baseline JDK 25/26 khỏi thí nghiệm AOT.
- [ ] Đo startup-to-ready bằng cùng readiness probe.
- [ ] Định nghĩa tiêu chí warmup ổn định.
- [ ] Training bao phủ class loading, method nóng và bước khởi tạo cần thiết.
- [ ] Side effect được cô lập bằng sandbox/staging.
- [ ] AOT cache được tạo bằng một bước hoặc ba giai đoạn.
- [ ] Đã dự trù RAM cho giai đoạn assembly.
- [ ] AOT log xác nhận cache thực sự được nạp.
- [ ] Cache được tạo từ đúng JDK, artifact, OS và CPU architecture.
- [ ] GC log có pause, heap và safepoint data cần thiết.
- [ ] GC CPU time được lấy delta và hiểu đúng đơn vị.
- [ ] Đã đo ít nhất 10 lần chạy hoặc đủ lần để phân bố ổn định.
- [ ] Báo cáo median và độ biến động, không chọn best run.
- [ ] Kết quả được xác nhận trên môi trường production-like.

## 18. Trạng thái tính năng trong Java 26

| Thành phần | Release đầu tiên | Trạng thái trong Java 26 |
|---|---:|---|
| AOT class loading/linking – JEP 483 | JDK 24 | Tính năng HotSpot ổn định |
| AOT method profiling – JEP 515 | JDK 25 | Có trong AOT cache |
| AOT object caching với mọi GC – JEP 516 | JDK 26 | Tính năng HotSpot ổn định, hỗ trợ G1 và ZGC |
| G1 giảm đồng bộ card table – JEP 522 | JDK 26 | Tối ưu implementation G1 |
| MemoryMXBean.getTotalGcCpuTime() | JDK 26 | API Java SE ổn định, không phải preview |

Không cần --enable-preview cho các tính năng trên. AOT cache và các cờ -XX là chức năng HotSpot/JDK; nếu dùng JVM vendor khác, phải kiểm tra tài liệu và khả năng hỗ trợ tương ứng.

## Kết luận

JEP 522 giảm đồng bộ card table của G1 bằng cách tách hoạt động ghi nhận của application threads khỏi refinement threads, giúp một số workload cập nhật tham chiếu có throughput tốt hơn. JEP 516 mở rộng AOT object caching cho mọi GC, còn JEP 483 và JEP 515 cung cấp nền tảng class loading/linking và method profiling từ các JDK trước. Muốn đánh giá đúng, hãy đo G1 không AOT trên JDK 25 và 26, sau đó so sánh JDK 26 không AOT với JDK 26 có AOT cache. Training phải đại diện cho production, cache phải khớp ứng dụng và nền tảng, còn kết quả cần có startup-to-ready, warmup, throughput, latency, GC pause và GC CPU time. Chỉ triển khai khi cache được nạp đúng và cải thiện có thể lặp lại trên môi trường production-like.

## Tài liệu tham khảo

- [JEP 522: G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522)
- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [JEP 515: Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515)
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [Oracle JDK 26 – The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Oracle JDK 26 – G1 Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html)
- [Oracle JDK 26 – G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
- [Java SE 26 API – MemoryMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Inside Java – Performance Improvements in JDK 26](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
- [Inside Java – Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/)
- [Inside Java – Java 26 for DevOps](https://inside.java/2026/03/02/jdk-26-rn-ops/)
