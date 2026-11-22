# Chuyển GC log cũ sang Unified Logging

Khi nâng Java từ JDK 8 lên JDK 11, 17, 21 hoặc các phiên bản mới hơn, một số cấu hình ghi nhật ký Garbage Collection (GC) cũ có thể không còn hoạt động theo cách quen thuộc. Những tùy chọn như -XX:+PrintGCDetails, -XX:+PrintGCTimeStamps, -XX:+PrintGCDateStamps, -Xloggc, -XX:+UseGCLogFileRotation hoặc các cờ ghi chi tiết từng collector đã từng xuất hiện trong startup script, Maven/Gradle task, application server và cấu hình container. Từ JDK 9, Java đưa ra **Unified JVM Logging**, với cú pháp chung bắt đầu bằng -Xlog.

Việc chuyển đổi không chỉ là thay tên cờ. Unified Logging thay đổi cách chọn sự kiện, mức chi tiết, định dạng timestamp, tag, output destination và cơ chế quay vòng file. Một cấu hình có thể vẫn khởi động nhưng ghi ít dữ liệu hơn, ghi quá nhiều dữ liệu, phát sinh chi phí I/O, hoặc khiến parser/GC dashboard cũ không còn nhận diện được các trường quan trọng.

Bài học thuộc **Java Advance Compatibility Migration**, chương **JVM và hiệu năng**, tập trung vào cách chuyển GC log truyền thống sang Unified Logging, đọc đúng cấu trúc -Xlog, lập bảng ánh xạ có điều kiện, thiết kế retention/rotation, kiểm thử trên JDK đích và giữ khả năng quan sát GC trong giai đoạn nâng cấp.

**Mục tiêu cuối cùng:** JVM khởi động với cấu hình hợp lệ, tạo GC log đủ thông tin vận hành, không làm lộ dữ liệu hoặc lấp đầy ổ đĩa, và hệ thống phân tích log đọc đúng sự kiện của collector/JDK đang chạy.

## 1. Vì sao GC logging quan trọng trong migration?

Garbage Collection ảnh hưởng đến mức sử dụng heap, thời gian dừng (pause), độ trễ phản hồi, throughput và việc thu hồi bộ nhớ. GC log cung cấp bằng chứng khi cần trả lời:

- Ứng dụng dừng do GC hay do safepoint/điều kiện khác?
- Có nhiều young collections bất thường không?
- Full GC có xuất hiện không; nguyên nhân là gì?
- Sau GC, heap còn bao nhiêu dữ liệu sống?
- GC pause có vượt latency SLO không?
- Áp lực allocation có thay đổi sau khi nâng JDK không?
- Collector hiện tại có đúng với cấu hình mong muốn không?
- Việc tăng heap hay thay GC flags có cải thiện thực tế không?
- Khi xảy ra OutOfMemoryError, GC đã hành xử như thế nào trước đó?

Một file GC log có thể giúp phân biệt lỗi memory leak, allocation spike, promotion pressure, heap sizing và tác động của việc đổi collector. Nhưng **GC log không phải toàn bộ hệ thống giám sát hiệu năng**. Cần kết hợp metric, thread dump, JFR, heap dump khi phù hợp và quan sát từ ứng dụng.

### 1.1. Mô hình quan sát

~~~text
JVM process
   |
   +--> Unified Logging (-Xlog:gc*)
   |         |
   |         +--> GC events, heap, phases, age, ergonomics
   |         +--> Timestamps, levels, tags, GC IDs
   |
   +--> JFR / JMX / metrics
   |         |
   |         +--> CPU, allocation, pause latency
   |
   +--> Application metrics
             |
             +--> Throughput, request latency, errors
             |
             v
   Phân tích đồng thời trước và sau migration
~~~

Giữ khả năng quan sát cần xét cả **nhật ký được JVM phát ra** và **hệ thống thu thập, đọc, hiển thị nó**.

## 2. Mốc chuyển đổi giữa GC logging cũ và Unified Logging

Java 8 và các thế hệ cũ thường dùng nhiều cờ PrintGC... và -Xloggc để cấu hình log. JDK 9 giới thiệu Unified JVM Logging theo JEP 158 và đưa thông tin GC vào mô hình mới theo JEP 271.

| Giai đoạn | Cấu hình phổ biến | Điểm cần chú ý |
|---|---|---|
| JDK 8 | -XX:+PrintGC, -XX:+PrintGCDetails, -Xloggc:... | Format phụ thuộc collector và cờ |
| JDK 9 trở đi | -Xlog với tag, level và output | Nhiều nguồn log JVM dùng cơ chế thống nhất |
| JDK 11/17/21 và các JDK hiện đại | -Xlog là giao diện chủ đạo | Cờ cũ có thể cảnh báo, không còn hỗ trợ hoặc có hành vi chuyển tiếp tùy bản |
| Các bản JDK tương lai | -Xlog và chính sách từng release | Xác nhận cú pháp, tags, collector và output policy ở JDK thực tế |

Không nên mặc định mọi cờ cũ sẽ luôn được JVM mới chuyển đổi một cách âm thầm. Một flag có thể vẫn được nhận bởi một bản JDK, bị xem là obsolete ở bản khác hoặc làm JVM từ chối khởi động.

### 2.1. Nâng JDK và đổi collector là hai biến độc lập

Một ứng dụng nâng từ Java 8 lên Java 17 có thể đồng thời đổi từ Parallel GC sang G1 GC do defaults hoặc configuration. Khi đó thay đổi GC log không chỉ do Unified Logging, mà còn do **collector và event types khác nhau**.

Ví dụ:

~~~text
Trước:
  JDK 8 + Parallel GC + GC flags cũ

Sau:
  JDK 17 + G1 GC + Unified Logging
~~~

Nếu biểu đồ GC pause thay đổi, phải tách tác động của runtime, collector, heap sizing, workload và log format. Không nên so sánh trực tiếp số “GC events” giữa hai collector rồi kết luận collector nào tốt hơn.

## 3. Các cờ GC logging truyền thống

Ví dụ cấu hình startup cũ:

~~~bash
java \
  -XX:+PrintGC \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -Xloggc:/var/log/myapp/gc.log \
  -XX:+UseGCLogFileRotation \
  -XX:NumberOfGCLogFiles=10 \
  -XX:GCLogFileSize=20M \
  -jar app.jar
~~~

Đây là ví dụ của cấu hình lịch sử, không phải câu lệnh khuyến nghị cho JDK mới.

Các thành phần hướng tới:

- Ghi sự kiện GC cơ bản.
- Ghi thông tin heap/collector chi tiết hơn.
- Thêm thời gian tính từ khi JVM khởi động hoặc timestamp ngày/giờ.
- Ghi ra file thay vì chỉ console.
- Quay vòng file theo kích thước và số lượng.

Một vài ứng dụng còn dùng -XX:+PrintTenuringDistribution, -XX:+PrintAdaptiveSizePolicy, -XX:+PrintReferenceGC, -XX:+PrintHeapAtGC hoặc các cờ khác phụ thuộc JDK/collector.

Vấn đề khi migration: không có ánh xạ một-một hoàn hảo giữa mọi Print... flag cũ và một -Xlog selector duy nhất. Mức dữ liệu, tên event, thẻ tag và định dạng có thể khác. Cần chuyển theo **mục đích quan sát**.

## 4. Unified Logging là gì?

Unified Logging là hệ thống ghi log cho nhiều thành phần nội bộ của JVM, không chỉ GC. Nó có thể cung cấp thông tin về class loading, safepoints, modules, threads, compilation và các chủ đề khác tùy JDK.

Cú pháp khái quát:

~~~text
-Xlog[:[selections][:[output][:[decorators][:output-options]]]]
~~~

Các phần:

1. **selections:** chọn tag set và mức log, ví dụ gc*=info.
2. **output:** đưa log tới stdout, stderr hoặc file.
3. **decorators:** chọn metadata gắn với dòng log, như time, uptime, level, tags.
4. **output-options:** cấu hình liên quan output, ví dụ filecount và filesize cho file rotation.

Ví dụ:

~~~bash
java -Xlog:gc* -jar app.jar
~~~

Cách đọc: bật các log message có tag liên quan GC với mức mặc định phù hợp, xuất ra output mặc định với decorator mặc định do JVM chọn.

Một ví dụ tùy biến:

~~~bash
java \
  -Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M \
  -jar app.jar
~~~

Cách đọc:

- gc*=info: lấy log GC ở mức info và một số tag combination liên quan.
- file=logs/gc.log: ghi vào file.
- time,uptime,level,tags: thêm metadata vào dòng log.
- filecount=10,filesize=20M: cấu hình quay vòng file.

Đường dẫn relative phụ thuộc thư mục làm việc của tiến trình JVM. Trên Windows, shell quoting/path separators và quyền file có thể khác.

## 5. Tag, level và tag set

### 5.1. Tag là cách phân loại sự kiện

Trong Unified Logging, một message có thể được gắn một hoặc nhiều tag như:

~~~text
gc
gc,heap
gc,phases
gc,age
safepoint
os
class
~~~

Các tag có sẵn và vị trí event phụ thuộc implementation/version. Không nên tự đặt tên tag rồi giả định JVM có hỗ trợ.

### 5.2. Level xác định độ chi tiết

Các level thông dụng:

| Level | Tính chất | Sử dụng |
|---|---|---|
| off | Tắt log cho selection | Vô hiệu hóa cụ thể |
| error | Lỗi | Tín hiệu nghiêm trọng |
| warning | Cảnh báo | Sự kiện đáng chú ý |
| info | Thông tin vận hành | Baseline production phổ biến |
| debug | Chi tiết phục vụ phân tích | Bật có kiểm soát |
| trace | Rất chi tiết | Dùng ngắn hạn khi điều tra |

Trong một selector, ngưỡng level bao gồm những message ở mức đó và các mức nghiêm trọng hơn phù hợp với cơ chế logging. Dùng gc*=trace có thể tạo rất nhiều log và chi phí I/O. Không nên bật trace lâu dài chỉ để “có dữ liệu đầy đủ”.

### 5.3. gc khác gc*

Ví dụ:

~~~bash
-Xlog:gc
~~~

chọn những message có tag set gc theo quy tắc chọn tag set. Nó có thể không hiển thị những message có kết hợp tag như gc,heap hoặc gc,phases.

Còn:

~~~bash
-Xlog:gc*
~~~

dùng wildcard để chọn cả những tag set có liên quan đến gc, gồm các tổ hợp với tag bổ sung theo quy tắc Unified Logging.

Đây là khác biệt trọng tâm khi thay -XX:+PrintGCDetails: **-Xlog:gc không đồng nghĩa -Xlog:gc***.

### 5.4. Kết hợp nhiều tag bằng dấu cộng

~~~bash
-Xlog:gc+heap=debug
~~~

chọn thông tin GC có tag combination gc và heap ở level debug theo matching rules của logging system.

~~~bash
-Xlog:gc+phases=debug
~~~

chọn thông tin các pha GC khi collector/JDK có phát event với tag đó.

Để biết sự kiện nào thực sự được ghi, cần xem -Xlog:help và log trên JDK mục tiêu.

### 5.5. Nhiều selectors trong một -Xlog

Ví dụ:

~~~bash
-Xlog:gc*=info,safepoint=info
~~~

chọn cả GC và safepoint. Nếu cần thêm thông tin chi tiết cho một nhóm:

~~~bash
-Xlog:gc*=info,gc+heap=debug,safepoint=info
~~~

Cần xác minh mức log được bật cho những tag set chồng lấn. Khi cần cấu hình phức tạp, nên viết rõ selector và chạy thử trên bản JDK được triển khai.

## 6. Output: console hay file?

Unified Logging có thể xuất ra:

- stdout.
- stderr.
- File thông qua file=...
- Những output được JVM/provider hỗ trợ theo version.

Ví dụ console:

~~~bash
java -Xlog:gc*:stdout:uptime,level,tags -jar app.jar
~~~

Ví dụ file:

~~~bash
java -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M -jar app.jar
~~~

Ví dụ stderr:

~~~bash
java -Xlog:gc*:stderr:uptime,level,tags -jar app.jar
~~~

### 6.1. Lựa chọn trong container

Trong Docker/Kubernetes, ghi ra stdout/stderr có ưu điểm:

- Log được platform thu thập theo cơ chế chuẩn.
- Không cần tự quản lý thư mục log trong container.
- Có thể tích hợp với hệ thống log aggregation đang dùng.

Nhưng cũng có nhược điểm:

- GC log và application log trộn trên cùng stream.
- Collector logs có thể nhiều khi bật debug.
- Logging pipeline có thể xử lý multiline hoặc truncation khác mong muốn.
- Quota hoặc retention của nền tảng không giống file rotation JVM.

Ghi ra file có ưu điểm:

- Tách GC log khỏi application log.
- Dễ dùng một số công cụ phân tích file.
- Có thể cấu hình rotation theo cơ chế JVM.

Nhược điểm là phải quản lý storage, permissions, sidecar/file shipper, mount volume và cleanup.

**Chọn một chiến lược log transport phù hợp với hạ tầng**, không chỉ sao chép cấu hình máy ảo truyền thống sang container.

## 7. Decorators: xác định thời gian và ngữ cảnh

Một dòng Unified Logging thường có phần prefix trong dấu ngoặc vuông, chứa metadata theo decorators đã chọn.

Ví dụ minh họa:

~~~text
[2026-11-12T10:30:00.250+0700][3.624s][info][gc] GC(12) Pause Young ... 28M->12M(256M) 3.40ms
~~~

Giá trị và định dạng cụ thể phụ thuộc JDK, collector và decorators. Đừng coi dòng mẫu là format chuẩn bất biến.

Những decorator thường gặp:

| Decorator | Ý nghĩa |
|---|---|
| time | Thời gian theo đồng hồ hệ thống |
| utctime | Thời gian theo UTC |
| uptime | Thời gian từ lúc JVM chạy |
| timemillis | Epoch timestamp mili giây theo tùy chọn |
| uptimemillis | JVM uptime tính theo mili giây |
| timenanos / uptimenanos | Độ phân giải thời gian phù hợp, khi JDK hỗ trợ |
| level | Mức log |
| tags | Nhãn event |
| pid | Process identifier |
| tid | Thread identifier |

Tên, khả năng hỗ trợ và format decorator cần được xác nhận với -Xlog:help của JDK đang chạy.

### 7.1. Tại sao nên có cả time và uptime?

- time giúp đối chiếu GC pause với application log và dashboard theo thời gian thực.
- uptime giúp phân tích diễn biến theo vòng đời JVM, ví dụ startup và warm-up.

Nếu hệ thống chạy nhiều JVM instance, uptime riêng của mỗi JVM không thể so sánh như một timestamp toàn cục. Với log tập trung, nên giữ time và thêm định danh instance/pod qua metadata của log collector.

### 7.2. Không đánh đồng thời gian sự kiện với thời gian ingest

Một GC event xảy ra lúc 10:30:00 nhưng sidecar gửi lên log server lúc 10:30:03. Nếu dashboard dùng ingestion timestamp, có thể xếp sai tương quan với độ trễ request.

Nên parse timestamp event theo đúng decorator, timezone và độ chính xác được cấu hình; đồng thời có thể giữ ingest timestamp riêng để phân tích pipeline.

## 8. Bảng chuyển các cờ GC logging cũ

Bảng sau đưa ra **điểm khởi đầu** cho migration. Không coi đây là ánh xạ ngữ nghĩa 1:1 giữa mọi JDK và collector.

| Mục đích trong JDK cũ | Cờ cũ điển hình | Unified Logging tham khảo |
|---|---|---|
| Sự kiện GC cơ bản | -XX:+PrintGC | -Xlog:gc |
| Thông tin GC chi tiết hơn | -XX:+PrintGCDetails | -Xlog:gc* |
| Ghi GC ra file | -Xloggc:logs/gc.log | -Xlog:gc*:file=logs/gc.log |
| Gắn thời gian JVM uptime | -XX:+PrintGCTimeStamps | -Xlog:gc*:stdout:uptime,level,tags |
| Gắn thời gian lịch | -XX:+PrintGCDateStamps | -Xlog:gc*:stdout:time,level,tags |
| Thời gian ở safepoint | -XX:+PrintGCApplicationStoppedTime | -Xlog:safepoint hoặc selection liên quan theo JDK |
| Theo dõi tuổi đối tượng | -XX:+PrintTenuringDistribution | Kiểm tra gc+age và mức debug/trace |
| Heuristics/ergonomics của GC | -XX:+PrintAdaptiveSizePolicy | Kiểm tra gc+ergo* với mức phù hợp |
| Thông tin heap quanh GC | -XX:+PrintHeapAtGC | Kiểm tra gc+heap và mức debug/trace |
| Quay vòng GC log | -XX:+UseGCLogFileRotation, -XX:NumberOfGCLogFiles, -XX:GCLogFileSize | output-options filecount và filesize |

Lưu ý:

- Các cờ cũ có thể chỉ tồn tại trên một số JDK/collector.
- Một số thông tin trước đây được in cùng một dòng nay nằm ở nhiều tag/level khác nhau.
- Thuật ngữ “application stopped time” không đồng nhất hoàn toàn với pause do GC; xem safepoint logs.
- Để xem nhiều nội dung GC mặc định, -Xlog:gc* là điểm khởi đầu hữu ích nhưng không bảo đảm giống toàn bộ PrintGCDetails.
- Với từng mục đích cụ thể, nên tạo một sự kiện GC có kiểm soát và xác minh thực tế log trên JDK đích.

### 8.1. Từ PrintGCDetails sang -Xlog:gc*

Cũ:

~~~bash
java -XX:+PrintGCDetails -jar app.jar
~~~

Mới:

~~~bash
java -Xlog:gc* -jar app.jar
~~~

Ở JDK mới, log có thể hiển thị thông tin collector initialization, pause events, heap before/after và các phase theo tags khác nhau. Không nên mong dòng và đơn vị đo giống hệt Java 8.

### 8.2. Từ -Xloggc sang output file

Cũ:

~~~bash
java -Xloggc:/var/log/myapp/gc.log -jar app.jar
~~~

Mới:

~~~bash
java -Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags -jar app.jar
~~~

Với đường dẫn có khoảng trắng hoặc ký tự shell đặc biệt, cần quoting phù hợp theo OS và launcher.

### 8.3. Từ timestamp flags sang decorators

Cũ:

~~~bash
-XX:+PrintGCDateStamps
-XX:+PrintGCTimeStamps
~~~

Mới:

~~~bash
-Xlog:gc*:stdout:time,uptime,level,tags
~~~

Nên ghi rõ output và decorators thay vì phụ thuộc default nếu parser hoặc retention policy cần format ổn định.

## 9. Quay vòng file log trong Unified Logging

GC log dài có thể chiếm nhiều dung lượng. Unified Logging có tùy chọn rotation cho file output.

Ví dụ:

~~~bash
java \
  -Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=10,filesize=20M \
  -jar app.jar
~~~

Ý tưởng:

- filesize=20M giới hạn kích thước định hướng cho file trước khi quay vòng theo cơ chế JVM.
- filecount=10 điều khiển số file log được giữ theo rotation policy.
- Khi đủ điều kiện, file cũ được quay vòng và ghi file mới.

Cần xem semantics chính xác ở JDK đang chạy. Đừng cộng đơn giản 10 × 20M rồi khẳng định tổng dung lượng tối đa tuyệt đối trong mọi tình huống; còn metadata, file active, log manager và các điều kiện vận hành khác.

### 9.1. Khác cờ rotation cũ

Cấu hình cũ:

~~~bash
-XX:+UseGCLogFileRotation
-XX:NumberOfGCLogFiles=10
-XX:GCLogFileSize=20M
~~~

Không nên giữ nguyên những cờ này khi đã chuyển sang -Xlog. Hãy dùng output-options tương ứng của Unified Logging, kiểm tra startup và xác nhận rotation bằng file thực tế.

### 9.2. File path, quyền và cleanup

Trước khi deploy, cần bảo đảm:

- Thư mục đích tồn tại hoặc được tạo bởi deployment.
- User chạy JVM có quyền ghi.
- Disk quota phù hợp.
- Có chính sách retention.
- Không dùng cùng một file giữa nhiều JVM instances.
- Nếu ghi vào volume chung, mỗi instance có đường dẫn riêng.
- Khi file shipper đọc log quay vòng, không bỏ sót hoặc đọc trùng sự kiện.
- Khi rollback sang JDK cũ, startup flags và log path vẫn phù hợp với bản runtime đó.

### 9.3. Tránh nhiều JVM cùng ghi một file

Nếu hai tiến trình JVM cùng dùng:

~~~text
/var/log/myapp/gc.log
~~~

có thể xảy ra ghi đè, đan xen hoặc quay vòng xung đột tùy cơ chế output. Nên tách file theo instance/container hoặc dùng stdout/stderr với metadata process/pod.

Unified Logging hỗ trợ một số placeholder/khả năng output file naming tùy version như process ID hoặc startup timestamp. Trước khi dùng, xác nhận tên placeholder và escaping trên JDK target thay vì tự suy đoán.

## 10. Lựa chọn baseline cho production

Cấu hình cân bằng cho nhiều ứng dụng là bắt đầu với GC events ở mức info, rồi bổ sung chi tiết theo nhu cầu.

Ví dụ:

~~~bash
java \
  -Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=8,filesize=25M \
  -jar app.jar
~~~

Đây là một ví dụ, không phải một công thức dùng cho mọi workload. Cần cân nhắc kích thước heap, collector, lượng GC, log transport và retention.

### 10.1. Khi cần log ít

~~~bash
-Xlog:gc=info
~~~

Có thể phù hợp khi hệ thống dùng JFR/JMX metrics làm nguồn chính và chỉ cần log pause cơ bản. Nhưng với điều tra sâu, nó có thể thiếu tags/phase information.

### 10.2. Khi cần chẩn đoán ngắn hạn

~~~bash
-Xlog:gc*=debug
~~~

Hoặc chọn nhóm cụ thể:

~~~bash
-Xlog:gc*=info,gc+heap=debug,gc+phases=debug
~~~

Nếu cần level trace cho một tag:

~~~bash
-Xlog:gc*=info,gc+age*=trace
~~~

Không bật trace mặc định cho mọi production JVM nếu chưa đánh giá log volume. Trong nhiều tình huống, JFR là phương án bổ sung hiệu quả hơn để điều tra có thời hạn.

### 10.3. Đừng dùng cấu hình debug vì “collector mới chắc cần”

G1, Parallel, ZGC và các collector khác phát ra các loại message khác nhau. Chỉ bật những tag/level phục vụ câu hỏi vận hành hiện tại. Thừa log có thể làm giảm hiệu năng hoặc che khuất sự kiện quan trọng.

## 11. Unified Logging và safepoint logging

GC pause thường liên quan thời điểm các Java threads phải dừng hoặc phối hợp. Nhưng **không phải mọi safepoint đều là GC**, và **không phải mọi hoạt động của concurrent collector đều gây stop-the-world pause lớn**.

Các thông tin cần phân biệt:

- GC event: vòng hoặc pha thu gom bộ nhớ.
- Stop-the-world GC pause: khoảng dừng ứng dụng do collector thực hiện một pha cần dừng threads.
- Safepoint: trạng thái/điểm mà JVM phối hợp với Java threads để thực hiện những hoạt động nhất định.
- Application stopped time: có thể bao gồm những lý do khác ngoài GC tùy cơ chế đo và log.
- Concurrent GC work: hoạt động chạy song song với ứng dụng, không đồng nghĩa toàn bộ thời lượng là pause.

### 11.1. Bật safepoint

Ví dụ:

~~~bash
-Xlog:safepoint=info
~~~

Kết hợp:

~~~bash
-Xlog:gc*=info,safepoint=info:stdout:time,uptime,level,tags
~~~

Việc hiển thị các sự kiện safepoint giúp điều tra những khoảng dừng mà GC log một mình không giải thích đầy đủ.

### 11.2. Không cộng tổng thời gian GC một cách cơ học

Một collector có thể có các pha concurrent dài và các pause ngắn. Nếu parser cộng mọi duration từ GC log thành “application downtime”, kết quả sẽ sai.

Khi xây dashboard, phải phân loại đúng event là pause, concurrent cycle, evacuation, cleanup hay phase khác. Collector và JDK version quyết định cách đặt tên.

## 12. Cách đọc một dòng GC Unified Logging

Một log minh họa:

~~~text
[2026-11-12T10:30:00.250+0700][3.624s][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 128M->72M(512M) 5.4ms
~~~

Có thể diễn giải:

- Thời điểm theo wall-clock: 2026-11-12T10:30:00.250+0700.
- Uptime: 3.624 giây sau khi JVM khởi động.
- Level: info.
- Tags: gc.
- GC(12): một identifier dùng để liên kết những message thuộc một hoạt động GC theo cách của JDK.
- Pause Young...: tên event/collector.
- 128M->72M(512M): dung lượng heap trước/sau trong thông điệp mẫu, cùng capacity mà event báo.
- 5.4ms: duration của event trong log.

Lưu ý: format và ý nghĩa chính xác của các số liệu có thể khác theo collector và release. Với event concurrent, phần duration hoặc heap figures có thể có ngữ nghĩa khác.

### 12.1. GC ID không phải timestamp

GC(12) giúp nhóm những message liên quan, nhưng một JVM restart sẽ có chuỗi GC ID mới. Nếu log collector gộp nhiều instance, không thể chỉ dựa vào GC ID để định danh duy nhất một sự kiện trên toàn cluster.

Nên kết hợp process/container identifier, startup time và GC ID khi cần đối chiếu.

### 12.2. Heap before/after không trực tiếp bằng RSS

GC heap usage là thông tin managed heap theo event. RSS của JVM process còn gồm metaspace, thread stacks, code cache, direct buffers, native libraries và các vùng bộ nhớ khác.

Nếu RSS tăng nhưng heap after-GC ổn định, có thể cần điều tra off-heap/native memory chứ không chỉ GC log.

### 12.3. Pause time không bằng request latency

Một GC pause có thể góp phần làm request chậm, nhưng request latency còn chịu network, thread contention, I/O và application processing. Phải đối chiếu timestamp và metrics, không chỉ xem pause duration riêng lẻ.

## 13. GC log format thay đổi theo collector

Một hệ thống có thể dùng:

- Serial GC.
- Parallel GC.
- G1 GC.
- ZGC.
- Shenandoah GC ở những JDK/vendor hỗ trợ.
- Các collector hoặc mode khác tùy bản phân phối JDK.

GC log của các collector này không dùng cùng event model. Ngay cả cùng collector, thông điệp giữa các JDK releases có thể thay đổi.

### 13.1. G1

Có thể có:

- Pause Young.
- Mixed collections.
- Concurrent marking.
- Heap regions.
- Humongous allocations.
- Remembered sets và GC phases.

Các tag như gc+heap hoặc gc+phases có thể hữu ích khi điều tra sâu, nhưng không nên coi mọi log line là pause.

### 13.2. ZGC

ZGC nhấn mạnh hoạt động concurrent để giảm pause time. Có thể có các cycle và phase với thời lượng khác nhau. Parser GC log được thiết kế riêng cho Parallel/G1 có thể không phân loại đúng ZGC logs.

### 13.3. Shenandoah

Shenandoah cũng có những sự kiện concurrent và pause riêng theo collector/version. Cần xác nhận collector thực sự có trong distribution và cấu hình JVM mục tiêu trước khi bật tag/flag chuyên biệt.

### 13.4. Đừng nâng JDK và đổi collector mà không có baseline

Nếu chuyển collector cùng lúc, hãy giữ kết quả:

- p50/p95/p99 request latency.
- GC pause distribution.
- Heap allocation rate.
- CPU utilization.
- Throughput.
- RSS và container memory.
- Concurrent GC activity.
- Full GC frequency khi có ý nghĩa với collector.

Nhờ vậy có thể đánh giá runtime behavior, không chỉ đối chiếu text log.

## 14. Sử dụng -Xlog:help

Trước khi áp dụng cấu hình từ tài liệu cũ, chạy:

~~~bash
java -Xlog:help
~~~

Lệnh này cho biết khả năng logging của JDK đang dùng, bao gồm:

- Available log levels.
- Available tags.
- Output và decorators.
- Các option của output file và rotation.
- Cú pháp selector.

Trong môi trường có nhiều JDK installations, phải chạy **đúng java executable của runtime được deploy**, không chỉ Java trên máy phát triển.

### 14.1. Vì sao không copy một tag chưa xác minh?

Một tag được blog hoặc tài liệu phiên bản khác nhắc đến có thể không tồn tại hoặc mang thông tin khác trên JDK hiện tại. Với cấu hình không hợp lệ, JVM có thể từ chối khởi động ngay từ bước parse VM options.

Cách an toàn:

1. Chọn JDK target.
2. Chạy java -Xlog:help.
3. Thiết lập cấu hình tối thiểu.
4. Chạy startup smoke test.
5. Tạo GC activity có kiểm soát trong test.
6. Xác minh log file/output thực sự có thông tin mong muốn.

## 15. Phân biệt dòng lệnh, environment và application configuration

GC logging là cấu hình của **JVM process**, không phải log level của Log4j, Logback hoặc java.util.logging.

Ví dụ:

~~~bash
java -Xlog:gc* -jar app.jar
~~~

khác với:

~~~properties
logging.level.root=INFO
~~~

Thay Spring Boot property logging.level.root không tự bật GC logs. Ngược lại, -Xlog:gc*=debug không đồng nghĩa tăng Logback application logger lên DEBUG.

### 15.1. Nơi startup flags có thể xuất hiện

- Shell script hoặc Windows service.
- Dockerfile ENTRYPOINT/CMD.
- Kubernetes Deployment args và env.
- JAVA_TOOL_OPTIONS hoặc JDK_JAVA_OPTIONS theo cơ chế launcher.
- Application server domain configuration.
- Gradle test JVM arguments.
- Maven Surefire/Failsafe argLine.
- Systemd service.
- Cloud runtime startup options.
- CI performance test jobs.

Nếu một môi trường khai báo nhiều nguồn flags, cần xem lệnh JVM cuối cùng và cách options được ghép. Một cấu hình hợp lệ trong script nhưng không được launcher chuyển vào JVM sẽ không có tác dụng.

### 15.2. Maven test JVM

Ví dụ mang tính khái niệm trong Surefire plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <argLine>
            -Xlog:gc*:file=target/test-gc.log:uptime,level,tags
        </argLine>
    </configuration>
</plugin>
~~~

Version và cấu hình chỉ để minh họa. Cần kiểm tra JVM mà Surefire thực sự fork, các argLine do công cụ coverage/agent thêm và Maven plugin version. Không nên ghi đè argLine đã có rồi vô tình làm mất Java agent.

### 15.3. Gradle test JVM

Ví dụ:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        "-Xlog:gc*:stdout:uptime,level,tags"
    )
}
~~~

Điều này tác động tới JVM được Gradle dùng để chạy test task phù hợp, không tự cấu hình JVM production. Nếu project chạy Gradle daemon bằng một JDK và test bằng toolchain khác, cần test đúng runtime target.

## 16. Cấu hình cho container và Kubernetes

Một container thường có nhiều nơi lưu log:

~~~text
JVM stdout/stderr
       |
       v
Container runtime log
       |
       v
Log collector / shipper
       |
       v
Centralized log store
~~~

Nếu GC logs ra stdout:

~~~bash
java -Xlog:gc*=info:stdout:time,uptime,level,tags -jar app.jar
~~~

chúng sẽ đi cùng luồng container logs theo cơ chế hạ tầng.

### 16.1. Ưu điểm

- Đỡ cần mount directory writable.
- Có thể tận dụng retention/rotation của platform.
- Dễ gắn pod, namespace, container và node metadata.
- Thu thập log qua cơ chế chuẩn của cluster.

### 16.2. Điều cần chú ý

- Nếu application log cũng dùng stdout, pipeline phải phân biệt GC logs bằng tags/prefix.
- Collector có thể parse timestamp trong dòng khác với timestamp container runtime.
- Log volume trong peak GC có thể làm tăng chi phí ingestion.
- Quá trình restart cần được nhận diện khi GC ID và uptime reset.
- Kubernetes log rotation và retention không phải filecount/filesize của JVM.
- Sidecar/agent phải hỗ trợ những version JDK/collector tương ứng.

### 16.3. File log trong container

Nếu chọn file:

~~~bash
-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

cần xác nhận /logs là mount writable, JVM user có quyền ghi và file shipper có thể đọc. Trong image read-only, /logs chưa được mount có thể khiến JVM không mở được output.

Không nên ghi nhiều GC logs lớn vào ephemeral filesystem mà không có quota/cleanup; container có thể bị evict hoặc hết disk.

## 17. Parser GC log cũ có thể hỏng ở đâu?

Một parser được viết cho JDK 8 có thể tìm mẫu:

~~~text
[GC ...
[Full GC ...
[Times: user=...
~~~

Unified Logging có prefixes và message names khác. Ví dụ:

~~~text
[3.624s][info][gc] GC(12) Pause Young ...
~~~

Tương thích parser có thể bị phá vì:

- Timestamp chuyển từ định dạng cũ sang decorator mới.
- Thêm [info][gc] prefix.
- GC ID xuất hiện trong nhiều message.
- Event name khác.
- Heap units/field placement thay đổi.
- Collector mới phát log phase khác.
- Các số liệu không còn nằm cùng một dòng.
- File rotation naming khác.
- Structured fields không được parser nhận diện.

### 17.1. Không sửa parser chỉ bằng regex đại khái

Một regex bắt mọi số có hậu tố ms có thể trộn:

- GC pause duration.
- Concurrent cycle duration.
- Time to reach safepoint.
- Time spent at safepoint.
- Subphase duration.
- Application event duration.

Kết quả dashboard có thể báo sai downtime hoặc throughput dù không có lỗi parse rõ ràng.

Nên dùng parser hỗ trợ **JDK version + collector + Unified Logging format** hoặc phát triển parser có fixture cho từng trường hợp.

### 17.2. Kiểm tra các dashboard quan trọng

Ví dụ:

- GC pause p95/p99.
- Số lần Full GC.
- Tỉ lệ thời gian JVM dành cho GC.
- Heap occupancy sau GC.
- Allocation rate.
- Metadata about collector.
- OutOfMemory incidents.
- Time to safepoint.

Với collector concurrent, định nghĩa “GC time percentage” cần rất thận trọng. Không nên lấy tổng tất cả cycle durations chia uptime rồi gọi đó là thời gian stop-the-world.

### 17.3. Sử dụng fixture log

Lưu một số file mẫu:

~~~text
fixtures/
  jdk8-parallel-gc.log
  jdk11-g1-unified.log
  jdk17-g1-unified.log
  jdk21-g1-unified.log
  jdk21-zgc-unified.log
~~~

Tên chỉ là ví dụ, không khẳng định mọi tổ hợp đều được dự án dùng. Fixture cần phản ánh startup, pause, concurrent events, rotation và shutdown để parser không chỉ hoạt động với một dòng đẹp.

## 18. Phân tích GC trước và sau nâng JDK

Để đánh giá tác động migration, cần so sánh trên điều kiện gần nhất có thể:

| Yếu tố | Trước | Sau |
|---|---|---|
| Runtime JDK | Build/vendor/update | Build/vendor/update |
| GC collector | Parallel/G1/... | Parallel/G1/... |
| Heap | -Xms/-Xmx | -Xms/-Xmx |
| Container memory | Limit và host | Limit và host |
| Workload | Throughput, payload | Tương đương |
| GC logging | Cũ | Unified |
| Log parser | Version | Version hỗ trợ format mới |
| Application version | Commit/release | Commit/release |
| JVM flags | Tập flags thực tế | Tập flags thực tế |

Nếu thay cả GC collector, heap sizing và application code, rất khó gán nguyên nhân một thay đổi pause chỉ cho Unified Logging.

### 18.1. Thước đo nên dùng

- Pause count và latency distribution.
- Longest pause trong cửa sổ quan sát.
- Time between collections.
- Heap occupancy after GC.
- Allocation rate và promotion pressure khi có số liệu.
- CPU cost.
- Application p95/p99 latency.
- Throughput.
- Full GC occurrence theo collector.
- RSS/container memory headroom.

### 18.2. Log không đủ cho mọi metric

Một số metrics được đo tốt hơn qua JFR, JMX, Micrometer hoặc cơ chế của JVM/collector. Đừng suy luận metric không được log với độ chính xác cần thiết. Nên dùng công cụ đo phù hợp cho từng câu hỏi.

## 19. Chạy song song JDK 8 và JDK mới trong cùng tổ chức

Một hệ thống lớn có thể còn dịch vụ Java 8 bên cạnh Java 17/21. Khi đó, một biến môi trường chung chứa -Xlog:gc* sẽ không hoạt động trên Java 8.

### 19.1. Chọn cấu hình theo JDK runtime

~~~text
JDK 8:
  -XX:+PrintGCDetails
  -XX:+PrintGCDateStamps
  -Xloggc:logs/gc.log

JDK 9+:
  -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags
~~~

Đây là cách phân nhánh theo **JDK thực tế đang khởi động**, không theo project sourceCompatibility hoặc Maven compiler release. Java bytecode có thể target 8 nhưng chạy trên JDK 17; lúc đó JVM logging options vẫn phải theo JDK 17.

### 19.2. Không đưa cả hai bộ flags vào cùng JVM theo thói quen

Kết hợp cờ cũ và mới có thể gây cảnh báo, startup failure hoặc kết quả log không mong muốn tùy JDK. Nên quản lý một bộ GC logging flags cho từng nhóm runtime, có tài liệu và cơ chế test startup.

### 19.3. Java version detection

Startup script có thể phát hiện JDK version và chọn flags phù hợp. Nhưng parser nhận diện Java version cần an toàn với version strings khác nhau giữa Java 8, 9+, vendor distributions và update levels.

Nếu deployment platform cho phép, tốt hơn là cấu hình profile/container image theo nhóm runtime rõ ràng, thay vì shell logic phức tạp.

## 20. GC log và bảo mật vận hành

GC log chủ yếu chứa metadata về heap, class loading/collector behavior và JVM lifecycle, không mặc định là application payload. Tuy vậy, nó vẫn có thể tiết lộ:

- Tên file/đường dẫn và vị trí triển khai.
- Tên JVM process, PID, instance.
- Thời điểm hoạt động, uptime, capacity và pattern workload.
- Một số class/tag/debug metadata theo mức log.
- Thông tin về hạ tầng và cấu hình memory.

Nếu bật tags khác ngoài GC hoặc mức trace, phạm vi dữ liệu có thể rộng hơn. Cần áp dụng:

- Quyền file đọc/ghi tối thiểu.
- Retention và xóa có kiểm soát.
- Không gắn GC log vào ticket công khai khi có metadata nhạy cảm.
- Không cấp quyền xem log tập trung quá rộng.
- Không để log chiếm hết volume làm gián đoạn service.
- Chính sách debug bật có thời hạn.

### 20.1. OOME dump khác GC log

Heap dump có thể chứa object và dữ liệu ứng dụng, bao gồm secrets. Không nhầm GC log với heap dump. Nếu bật -XX:+HeapDumpOnOutOfMemoryError, cần quản lý file dump với mức bảo mật và dung lượng nghiêm ngặt hơn.

## 21. Các lỗi cấu hình -Xlog thường gặp

### 21.1. JVM không khởi động vì sai cú pháp

Ví dụ cấu hình thiếu dấu hai chấm, sai tag hoặc sai output-options có thể khiến JVM báo invalid -Xlog option.

Cách xử lý:

1. Lấy command line JVM đầy đủ.
2. Chạy java -Xlog:help trên JDK đích.
3. Bắt đầu từ -Xlog:gc*.
4. Thêm output, decorators, rotation từng bước.
5. Smoke test startup trước deploy.

### 21.2. JVM khởi động nhưng không có GC log

Có thể vì:

- Không xảy ra event GC trong khoảng quan sát.
- Selector quá hẹp.
- Log ghi tới stdout/stderr khác nơi đang xem.
- File path relative không như kỳ vọng.
- Container không mount thư mục.
- Log bị rotation sang tên file khác.
- Startup flags không thực sự được truyền vào JVM.

Không kết luận “GC không chạy” chỉ vì một file trống.

### 21.3. Chỉ có một số dòng GC, thiếu heap/phases

Nguyên nhân có thể là dùng -Xlog:gc thay vì -Xlog:gc* hoặc selector level quá thấp cho tag mong muốn. Hãy bật gc* hoặc tag set cụ thể ở mức phù hợp trong môi trường thử nghiệm.

### 21.4. Quá nhiều log, disk usage tăng

gc*=debug hoặc gc*=trace có thể tạo nhiều event; kết hợp với traffic lớn và rotation không được quản lý sẽ làm log volume tăng mạnh.

Giải pháp: trở về info hoặc chọn tag hẹp, giới hạn output và retention, xem log collector quotas.

### 21.5. Log parser đếm sai GC pause

Nếu parser lấy duration của concurrent GC như stop-the-world pause, chỉ số latency sẽ sai. Cần phân loại event theo collector/JDK, đối chiếu app metrics và sửa parser.

### 21.6. GC log date/time lệch dashboard

Kiểm tra decorators, timezone, đồng hồ host/container, offset và thời điểm ingest. Không dùng JVM uptime như timestamp epoch.

### 21.7. Cờ cũ bị báo Unrecognized VM option

Một số cờ PrintGC... hoặc rotation cũ không còn được runtime nhận. Hãy chuyển sang -Xlog theo đúng mục đích và kiểm tra toàn bộ JVM args thay vì bật -XX:+IgnoreUnrecognizedVMOptions để che lỗi không kiểm soát.

### 21.8. JVM lỗi mở file GC log

Có thể do đường dẫn không tồn tại, permission denied, filesystem read-only hoặc chính sách bảo mật container. Đặt đường file hợp lệ và kiểm thử bằng đúng user chạy service.

### 21.9. Nhiều -Xlog flags không cho output như mong muốn

Khi cấu hình nhiều -Xlog với cùng output/selector, semantics có thể không trực quan. Nên định nghĩa rõ từng output destination và các selections liên quan, tránh copy-paste nhiều flags từ các nguồn khác nhau.

### 21.10. JDK mới hơn có collector/event tags khác

Cùng câu lệnh -Xlog:gc* có thể tạo nội dung khác khi đổi từ G1 sang ZGC hoặc khi JDK thay đổi log messages. Cần cập nhật parser, không cố ép output thành format Java 8 bằng regex cũ.

## 22. Quy trình chuyển cấu hình GC log cũ

### Bước 1 — Thu thập cấu hình thực tế

Ghi:

- JDK vendor, version, update/build.
- Collector được sử dụng.
- Heap sizing và container limits.
- Startup flags từ tất cả nguồn.
- Vị trí log, rotation và retention.
- Tool/parser/dashboard đang đọc GC log.
- Nhu cầu quan sát: pause, heap, safepoint, tuning.

Không chỉ tìm một file startup script rồi bỏ qua flags từ Docker, systemd, Maven/Gradle hoặc application server.

### Bước 2 — Phân loại mục tiêu của từng cờ cũ

Ví dụ:

| Cờ cũ | Mục đích |
|---|---|
| PrintGCDetails | Muốn nhiều chi tiết GC |
| PrintGCDateStamps | Tương quan với wall-clock |
| PrintGCTimeStamps | Tương quan với JVM uptime |
| Xloggc | Ghi ra file |
| UseGCLogFileRotation | Tránh file phình |
| PrintTenuringDistribution | Theo dõi tuổi và promotion |
| PrintGCApplicationStoppedTime | Điều tra safepoint/stop time |

Không nhất thiết phải tái tạo mọi dòng cũ. Chỉ cần đảm bảo **câu hỏi vận hành mà cờ cũ phục vụ vẫn có câu trả lời**.

### Bước 3 — Xây cấu hình -Xlog tối thiểu

Ví dụ:

~~~bash
-Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

Nếu cần safepoint:

~~~bash
-Xlog:gc*=info,safepoint=info:file=logs/jvm-gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

### Bước 4 — Xác minh với -Xlog:help

Chạy đúng JDK mục tiêu. Nếu cần tag đặc biệt cho collector, xác minh nó tồn tại và log phát ra nội dung cần quan sát.

### Bước 5 — Startup smoke test

Chạy JVM bằng cấu hình mới, kiểm tra:

- Exit status và startup errors.
- Có đúng collector.
- File/console output tồn tại.
- Định dạng decorator như mong muốn.
- Quyền ghi file và paths.
- JVM không còn cờ cũ gây warning/error.

### Bước 6 — Tạo workload và kiểm tra log

Chạy một kịch bản tạo allocation/GC event có kiểm soát. Không cần ép System.gc trong production chỉ để lấy log; lời gọi System.gc có thể không tạo sự kiện như mong đợi tùy cờ/collector. Test nên dùng workload thực tế hoặc controlled allocation trong môi trường riêng.

### Bước 7 — Xác nhận rotation và ingestion

Kiểm tra file naming, filecount/filesize, sidecar/agent thu thập đủ log, restart không ghi đè ngoài ý muốn và dashboard parse được.

### Bước 8 — So sánh các chỉ số và phát hành từng bước

Chạy canary, quan sát GC pause, heap after-GC, CPU, p99 latency và log volume. Nếu đổi collector cùng lúc, ghi rõ hai thay đổi để tránh quy nguyên nhân sai.

### Bước 9 — Thu gọn cờ legacy

Sau khi xác nhận, xóa những GC flags cũ không còn được sử dụng, cập nhật runbook và parser documentation. Không để một container production còn dùng startup flags Java 8 trong khi môi trường khác đã dùng Unified Logging.

## 23. Ví dụ migration hoàn chỉnh: Java 8 sang Java 17

### 23.1. Cấu hình Java 8 trước migration

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -Xloggc:/logs/gc.log \
  -XX:+UseGCLogFileRotation \
  -XX:NumberOfGCLogFiles=5 \
  -XX:GCLogFileSize=20M \
  -jar orders-service.jar
~~~

Đây là cấu hình lịch sử mang tính ví dụ. Nó chọn G1 và ghi GC log chi tiết, có timestamp, file output và rotation.

### 23.2. Cấu hình Java 17 sau migration

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -Xlog:gc*=info:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders-service.jar
~~~

Những điểm chính:

- Giữ heap và collector để giảm biến số trong giai đoạn đầu.
- Thay nhóm PrintGC... bằng -Xlog.
- Giữ thông tin wall-clock, uptime, level và tags.
- Giữ file output và rotation ở cấu hình tương tự về mục đích.
- Không giữ cờ rotation cũ.

### 23.3. Nếu cần safepoint analysis

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -Xlog:gc*=info,safepoint=info:file=/logs/jvm.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders-service.jar
~~~

Cấu hình này cho thêm thông tin safepoint ở output được chỉ định; parser cũ chỉ đọc GC events có thể cần lọc tags.

### 23.4. Đường kiểm tra

Sau khi đổi, cần chạy các bước độc lập:

1. JVM startup không báo invalid options.
2. Log file được tạo.
3. Một workload kiểm thử tạo GC events.
4. Log có timestamp và GC IDs.
5. File rotation được thực hiện theo kỳ vọng.
6. Dashboard có thể phân biệt pause và concurrent phases.
7. Application latency và throughput không xấu đi vì log volume.
8. Rollback sử dụng bộ flags phù hợp với JDK 8 nếu cần quay lại.

## 24. Mối quan hệ giữa GC log và JVM memory tuning

Trong migration, nhiều team có xu hướng dùng một số GC flags cũ để tối ưu heap rồi chuyển nguyên xi sang JDK mới. Cần tách:

- **Logging flags:** quyết định thông tin được ghi.
- **GC selection flags:** quyết định collector được dùng.
- **GC tuning flags:** điều chỉnh mục tiêu và heuristics.
- **Heap flags:** giới hạn và cấu hình vùng nhớ.
- **Diagnostic flags:** cung cấp thông tin bổ sung.

Ví dụ:

~~~text
-Xlog:gc*                  -> logging
-XX:+UseG1GC               -> collector selection
-Xmx4g                     -> heap maximum
-XX:MaxGCPauseMillis=200   -> tuning goal của collector phù hợp
~~~

Chuyển PrintGCDetails sang -Xlog không phải là lý do tự động đổi -Xmx, MaxGCPauseMillis hay collector. Nên giữ nguyên các biến không liên quan trong pha đầu để đánh giá ảnh hưởng thực tế.

### 24.1. GC log có thể chỉ ra vấn đề nhưng không tự sửa nó

Nếu GC log cho thấy liên tục thu gom với heap occupancy cao, giải pháp có thể là giảm allocation, sửa memory leak, tăng heap phù hợp hoặc điều chỉnh collector. Bật thêm debug/trace không làm hiệu năng tốt hơn; thậm chí có thể tốn thêm I/O/CPU.

## 25. Dynamic logging và chẩn đoán ngắn hạn

Một số JDK hiện đại hỗ trợ điều chỉnh Unified Logging ở JVM đang chạy qua công cụ quản trị như jcmd với VM.log. Khả năng và cú pháp cụ thể phụ thuộc JDK, quyền truy cập và môi trường.

Ví dụ hướng dẫn kiểm tra:

~~~bash
jcmd <pid> help VM.log
~~~

Ký hiệu <pid> ở đây là placeholder cho process ID, không phải cú pháp nhập nguyên văn.

Nếu cần bật debug trong production, có thể xem cơ chế điều chỉnh logging động mà JDK mục tiêu hỗ trợ, thay vì bắt buộc restart toàn bộ service. Nhưng phải lưu ý:

- Chỉ có quyền attach/management phù hợp mới thao tác được.
- Runtime có thể hạn chế attach hoặc jcmd trong container.
- Không được phép điều chỉnh tùy tiện với service nhạy cảm.
- Cần biết log output/rotation đang được dùng.
- Sau điều tra phải trả level về baseline.
- Cấu hình động có thể không còn sau JVM restart.

**Không giả định mọi JVM production đều cho phép dùng jcmd.** Cần tuân thủ chính sách vận hành và bảo mật.

## 26. Kiểm thử lưu lượng log và chi phí

Một cấu hình gc*=trace có thể làm tăng mạnh log rate, nhất là khi workload có nhiều allocation và collector phát nhiều phase events.

Nên đo:

- Bytes log mỗi phút.
- Số message mỗi giây.
- CPU overhead khi ghi log.
- Disk I/O và write latency.
- Bộ nhớ/buffer của log shipper.
- Ingestion cost.
- Rủi ro drop log khi pipeline quá tải.
- Tác động tới application tail latency.

### 26.1. Không kết luận overhead bằng một lần chạy

Nếu so sánh logging off và trace ở hai lần chạy có workload khác nhau, kết quả không có ý nghĩa. Cần giữ tải, heap, collector, JDK và môi trường gần như tương đương; chạy đủ lần để thấy độ biến thiên.

### 26.2. Production baseline và debug profile

Nên có hai cấu hình được tài liệu hóa:

**Baseline:** thông tin đủ để xác định GC pause và heap trend, log volume có kiểm soát.

**Diagnostic:** bật thêm tags/levels cần cho một vấn đề cụ thể, có thời hạn và chủ sở hữu.

Không nên để debug profile trở thành mặc định vĩnh viễn sau khi sự cố được khắc phục.

## 27. Checklist vận hành sau khi chuyển sang Unified Logging

- [ ] Xác định đúng JDK runtime, vendor và build.
- [ ] Đọc java -Xlog:help của JDK mục tiêu.
- [ ] Kiểm kê mọi GC logging flags cũ trong startup.
- [ ] Tách flags logging khỏi heap/collector tuning.
- [ ] Chọn gc hoặc gc* dựa trên nhu cầu dữ liệu.
- [ ] Chọn level production phù hợp; debug/trace dùng có thời hạn.
- [ ] Bổ sung safepoint selector nếu cần.
- [ ] Chọn output file hoặc stdout/stderr theo hạ tầng.
- [ ] Định nghĩa decorators time/uptime/level/tags rõ ràng.
- [ ] Kiểm tra đường file, permissions và volume.
- [ ] Cấu hình rotation/retention khi ghi file.
- [ ] Không để nhiều JVM ghi chung một file tùy tiện.
- [ ] Startup smoke test không có invalid option.
- [ ] Workload test tạo được event cần quan sát.
- [ ] Log parser hỗ trợ đúng JDK và collector.
- [ ] Dashboard phân biệt GC pauses với concurrent work.
- [ ] Timestamp không bị lệch timezone/ingestion time.
- [ ] Log shipper thu đủ dữ liệu sau rotation.
- [ ] Theo dõi log volume và overhead.
- [ ] Canary so sánh heap, pause, CPU và latency.
- [ ] Runbook/rollback có bộ flags phù hợp JDK cũ.
- [ ] Gỡ cờ GC logging legacy sau khi hoàn tất.

## 28. Mẫu tài liệu quyết định logging trong migration

~~~text
APPLICATION
  Service:
  Current JDK/vendor/build:
  Target JDK/vendor/build:
  Current collector:
  Target collector:
  Heap -Xms/-Xmx:
  Container memory limit:

LEGACY GC LOGGING
  Old JVM flags:
  Log path:
  Timestamp format:
  Rotation and retention:
  Parser/dashboard:
  Questions answered by legacy logs:

UNIFIED LOGGING
  Selected -Xlog:
  Selected tags:
  Levels:
  Output:
  Decorators:
  Filecount/filesize:
  Expected log volume:
  Safepoint logging?:

DEPLOYMENT
  Host/container:
  JVM user:
  Writable log paths:
  Log shipper:
  Rotation ownership:
  Multi-instance naming:
  Retention and access policy:

VALIDATION
  java -Xlog:help:
  Startup smoke test:
  GC workload test:
  Log readback:
  Rotation test:
  Parser compatibility:
  Dashboard metrics:
  Canary latency/CPU:
  Rollback flags:

DECISION
  Approved baseline:
  Diagnostic profile:
  Owner:
  Exceptions:
  Removal milestone for old flags:
~~~

Mẫu hồ sơ phải nêu chính xác **phiên bản JDK, collector và -Xlog selection**. Chỉ ghi “đã bật GC log” không đủ để người khác tái lập cách giám sát.

## 29. Những hiểu lầm thường gặp

### “-Xlog:gc và -Xlog:gc* giống nhau”

Không đúng. Wildcard ảnh hưởng việc chọn các tag combinations liên quan GC. gc* thường rộng hơn gc.

### “Chỉ cần thay -Xloggc bằng -Xlog, mọi log sẽ giữ nguyên format”

Không đúng. Prefix, tags, levels, message names và collector semantics đều có thể khác. Parser và dashboard phải được kiểm thử lại.

### “PrintGCDetails có ánh xạ tuyệt đối sang một selector”

Không có bảo đảm 1:1 cho mọi JDK. -Xlog:gc* là điểm khởi đầu; các tag chuyên sâu có thể cần mức debug/trace.

### “JDK mới không nhận GC flag cũ thì cứ bật IgnoreUnrecognizedVMOptions”

Không nên. Việc bỏ qua cờ có thể làm mất quan sát hoặc che sự cố cấu hình. Hãy chuyển cờ theo mục đích và kiểm thử startup.

### “Timestamp trong GC log luôn là thời điểm UTC”

Không đúng. Decorator time, utctime và timezone của runtime có thể khác. Cần đọc đúng định dạng.

### “Một concurrent GC cycle dài nghĩa là application bị pause từng đó”

Sai. Concurrent work và stop-the-world pause là hai đại lượng khác nhau.

### “GC heap usage bằng toàn bộ RSS của JVM”

Không đúng. Native memory, thread stacks, direct buffers và các vùng khác còn nằm ngoài Java heap.

### “Chuyển sang stdout thì không cần quản lý retention”

Không đúng. Container runtime và log aggregation vẫn có rotation, quota và retention. Chỉ chuyển nơi chịu trách nhiệm.

### “Filecount và filesize bảo đảm sẽ không bao giờ hết ổ đĩa”

Không nên kết luận tuyệt đối. Có thể có nhiều JVM instances, file shipper, output khác hoặc cấu hình storage không phù hợp.

### “Parser GC Java 8 sẽ tự đọc mọi log Java 21”

Không đúng. Format, events và collector có thể thay đổi; cần parser tương thích và fixture.

### “Tăng log level sẽ cải thiện GC performance”

Không đúng. Logging cung cấp dữ liệu chẩn đoán, thường có overhead và không thay đổi cơ chế GC theo hướng tối ưu.

### “Nâng JDK mà ứng dụng khởi động được là đã migration GC logging thành công”

Không đủ. File output, rotation, parser, dashboard và cảnh báo vận hành vẫn có thể hỏng.

## 30. Kết luận

Chuyển GC log cũ sang Unified Logging là một phần quan trọng của Java compatibility migration vì nó ảnh hưởng trực tiếp đến khả năng quan sát và phân tích hiệu năng của JVM sau nâng cấp.

Những nguyên tắc quan trọng:

1. **Từ JDK 9 trở đi, -Xlog là giao diện logging thống nhất chủ đạo.** Cấu hình GC cũ phải được chuyển theo mục đích, không thay chuỗi cơ học.
2. **Hiểu cú pháp selectors, tags, levels, output và decorators.** Phân biệt gc với gc* và mức info với debug/trace.
3. **Quản lý file rotation, retention và transport.** File trong VM/container và stdout trong Kubernetes có trách nhiệm vận hành khác nhau.
4. **Không coi GC log format là API ổn định bất biến.** Collector, JDK và tags có thể thay đổi; parser cần được cập nhật.
5. **Phân biệt GC pause, safepoint và concurrent activity.** Không báo cáo sai latency chỉ vì lấy mọi duration trong log.
6. **Giữ baseline có thể so sánh.** Khi nâng JDK, ưu tiên giữ collector/heap/workload ổn định trong giai đoạn xác minh ban đầu.
7. **Kiểm thử cả đường vận hành.** Startup, log generation, file rotation, ingestion, dashboard và rollback đều cần được xác nhận.

Một cấu hình Unified Logging được migration tốt không chỉ làm biến mất warning về cờ GC cũ. Nó giúp đội vận hành tiếp tục hiểu JVM đang thu gom bộ nhớ như thế nào, giải thích được sự thay đổi hiệu năng và phát hiện vấn đề thật sự trên JDK mới mà không trả giá bằng log volume hoặc rủi ro vận hành ngoài ý muốn.

