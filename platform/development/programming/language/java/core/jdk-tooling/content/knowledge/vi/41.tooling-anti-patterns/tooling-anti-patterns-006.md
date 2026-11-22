# Tránh dump production không kiểm soát trong Java

Dump là dữ liệu chẩn đoán được lấy từ một tiến trình hoặc JVM tại một thời điểm hay trong một khoảng thời gian. Thread dump, heap dump, core dump, Java Flight Recorder (JFR) và GC log phục vụ các câu hỏi khác nhau. Chúng cũng khác nhau về thời gian pause, CPU, dung lượng file, dữ liệu nhạy cảm và cách lưu trữ.

Trong production, tạo dump mà không xác định đúng process, mục tiêu, giới hạn tài nguyên và nơi lưu có thể làm sự cố nặng hơn. Heap dump có thể kích hoạt full GC và tạo pause dài; recording không giới hạn có thể lấp đầy disk; core dump có thể chứa phần lớn bộ nhớ của process; một lệnh nhắm sai PID có thể tác động đến nhiều JVM. Vì vậy, dump phải là một bước có mục đích trong quy trình incident, với phạm vi và thời hạn rõ ràng.

## 1. Dump là gì và khi nào cần?

Dump là bản ghi trạng thái phục vụ phân tích sau khi thu thập. Nó không tự sửa lỗi và cũng không chứng minh nguyên nhân nếu thiếu bối cảnh.

| Loại dữ liệu | Câu hỏi phù hợp | Mức tác động điển hình | Dữ liệu có thể chứa |
|---|---|---|---|
| Thread dump | Thread đang chạy, chờ lock hay deadlock? | Trung bình, phụ thuộc số thread | Thread name, stack, lock, tên class, một số thông tin môi trường |
| Heap dump (HPROF) | Object nào đang được giữ trong heap? | Cao, phụ thuộc heap và nội dung | Object graph, chuỗi, request, token, dữ liệu nghiệp vụ |
| Class histogram | Heap đang chứa bao nhiêu object theo class? | Cao, phụ thuộc heap | Tên class và số lượng/ước lượng bộ nhớ |
| JFR recording | CPU, allocation, GC, lock hoặc I/O biến động thế nào theo thời gian? | Từ thấp đến cao, tùy settings | Event, thread, stack trace, class, exception và metadata |
| GC log | GC xảy ra khi nào, pause và heap thay đổi ra sao? | Thường thấp nếu đã cấu hình hợp lý | Heap metrics, timestamp, GC cause và runtime metadata |
| Core dump | JVM/process gặp lỗi native hoặc crash ở trạng thái nào? | Rất cao; có thể làm process dừng và tạo file lớn | Bộ nhớ process, native state, thread, vùng heap và dữ liệu nhạy cảm |
| JVM fatal error log | JVM crash ở native/JVM layer vì sao? | Thường được tạo khi crash | JVM flags, thread/native stack, libraries, OS và thông tin process |

Các mức tác động của diagnostic command là đánh giá của JDK cho command đó; tác động thực tế còn tùy heap size, thread count, CPU, I/O, filesystem và tải hiện tại. Không hiểu “low impact” là không có overhead hoặc có thể chạy tùy ý.

### 1.1. Chọn dữ liệu theo triệu chứng

- Ứng dụng treo hoặc request chờ lâu: bắt đầu bằng một số thread dump cách nhau vài giây để so sánh tiến triển và lock.
- CPU cao hoặc latency tăng: dùng metrics/log hiện có, sau đó cân nhắc JFR ngắn với cấu hình mặc định.
- Heap tăng liên tục hoặc OOM: kiểm tra heap metrics và GC trước; chỉ lấy heap dump khi cần phân tích object retention và có đủ dung lượng/quyền lưu.
- GC pause kéo dài: bắt đầu bằng GC log và JFR; heap dump không phải công cụ đầu tiên để đo pause.
- JVM crash ở native layer: giữ lại fatal error log; core dump chỉ khi điều tra cần native memory/debugger và đã được phê duyệt.
- Lỗi xảy ra thoáng qua: recording có giới hạn hoặc log liên tục đã cấu hình thường hữu ích hơn việc tạo dump thủ công sau khi sự cố kết thúc.

Không lấy tất cả loại dump cùng lúc để “phòng trường hợp cần”. Mỗi file bổ sung làm tăng chi phí, dữ liệu nhạy cảm và khả năng ảnh hưởng service.

## 2. Vì sao dump production không kiểm soát nguy hiểm?

### 2.1. Tạo pause hoặc làm tăng tải

Heap dump và class histogram có thể cần duyệt lượng lớn object. Với JDK 17, `jcmd <pid> GC.heap_dump` được xếp mức tác động cao và mặc định yêu cầu full GC, trừ khi dùng tùy chọn `-all`. Full GC có thể làm ứng dụng pause, tăng tail latency và khiến health check hoặc request timeout.

Thread dump thường nhẹ hơn heap dump nhưng tác động được đánh giá trung bình và phụ thuộc số thread. Một process có hàng chục nghìn thread có thể tạo output lớn và cần thời gian thu thập.

JFR có thể chạy liên tục với cấu hình `default` có overhead thấp. Cấu hình `profile` ghi nhiều sự kiện hơn và có overhead cao hơn; phù hợp cho khoảng thời gian ngắn khi cần dữ liệu chi tiết. Bật nhiều event, stack trace hoặc tần suất lấy mẫu quá cao có thể làm tăng CPU và dung lượng.

### 2.2. Lấp đầy disk hoặc làm cạn quota

Heap dump có thể lớn gần với lượng dữ liệu heap được ghi ra; core dump có thể rất lớn tùy memory mapping và cấu hình hệ điều hành. Nếu ghi vào filesystem chứa application log, container writable layer hoặc volume dùng chung, việc hết dung lượng có thể làm ứng dụng không ghi được log, không tạo file tạm hoặc không khởi động được.

JFR recording cũng cần giới hạn thời gian và dung lượng. Một recording chạy vô hạn, không đặt maxage/maxsize hoặc không có chính sách cleanup có thể tích lũy dữ liệu ngoài dự kiến.

Trước khi tạo file, cần biết:

- Thư mục đích và filesystem thực tế.
- Dung lượng trống, quota và giới hạn ephemeral storage.
- File có được ghi trên volume riêng hay container layer.
- Dự kiến dung lượng và thời gian tạo.
- Hành vi khi hết disk: command thất bại, file dở dang hay process chịu ảnh hưởng.

Không ghi dump vào thư mục tạm chung hoặc volume production quan trọng nếu chưa xác định được quota và cleanup.

### 2.3. Rò rỉ dữ liệu nhạy cảm

Heap dump có thể chứa object đang sống: access token, session, request/response body, thông tin người dùng, dữ liệu thanh toán, mật khẩu trong chuỗi hoặc cấu hình đã giải mã. Core dump có thể chứa cả vùng nhớ native và JVM, nên phạm vi dữ liệu có thể rộng hơn heap dump.

Thread dump và JFR thường không chứa toàn bộ object heap nhưng vẫn có thể lộ URL, tên host, đường dẫn file, thread name, stack trace, exception message, tên tenant hoặc dữ liệu được đưa vào event. GC log thường ít nhạy cảm hơn nhưng có thể tiết lộ cấu trúc runtime và thông tin vận hành.

Hãy phân loại dump như dữ liệu production nhạy cảm. Đừng đính kèm file thô vào ticket công khai, email không mã hóa hoặc kênh chat không được phê duyệt.

### 2.4. Nhắm nhầm process

`jcmd` gửi diagnostic command đến PID hoặc tên main class được chỉ định. Theo tài liệu JDK, PID `0` gửi lệnh đến tất cả JVM mà công cụ có thể truy cập. Dùng `jcmd 0 ...` trong production có thể tác động nhiều service/process cùng lúc.

Tương tự, chọn main class không duy nhất có thể khớp nhiều process. Luôn xác định đúng PID, service instance, container và namespace trước khi gửi lệnh. Không copy PID từ máy khác hoặc dùng lại PID cũ sau khi process restart vì hệ điều hành có thể tái sử dụng PID.

### 2.5. Phân tích file sai bối cảnh

Một heap dump đơn lẻ không cho biết object nào đang tăng theo thời gian. Một thread dump đơn lẻ có thể không phân biệt thread đang chờ hợp lệ hay deadlock. Một JFR recording sau khi sự cố đã hết có thể không chứa event cần tìm.

Ghi lại timestamp, timezone, PID, instance/pod, build version, request impact và triệu chứng. Nếu lấy nhiều snapshot, giữ thứ tự và khoảng thời gian giữa chúng để so sánh.

## 3. Đánh giá tác động trước khi thu thập

Trước mỗi thao tác, trả lời các câu hỏi sau:

1. **Giả thuyết:** cần chứng minh điều gì? Deadlock, heap retention, GC pause, CPU hotspot hay native crash?
2. **Đúng process:** service, instance, PID, container và JVM version đã được xác nhận chưa?
3. **Tải hiện tại:** service đang ổn định, degraded hay đang mất khả năng phục vụ?
4. **Tác động:** command được JDK đánh giá Low, Medium hay High? Có thể gây full GC, pause hoặc I/O lớn không?
5. **Dung lượng:** file dự kiến ghi ở đâu, còn bao nhiêu dung lượng và có giới hạn không?
6. **Dữ liệu:** file có thể chứa thông tin khách hàng, token, secret hoặc dữ liệu cá nhân không?
7. **Quyền:** ai phê duyệt, ai được truy cập và ai chịu trách nhiệm phân tích?
8. **Giới hạn:** số lần chụp, thời lượng, maxage, maxsize và thời hạn lưu là bao nhiêu?
9. **Phương án dừng:** nếu latency, error rate hoặc disk usage tăng, ai dừng recording và bằng cách nào?

Nếu chưa có câu trả lời cho process, disk hoặc quyền xử lý dữ liệu, dừng ở metrics/log hiện có và xin người chịu trách nhiệm xác nhận. Không tạo dump chỉ vì một lệnh dễ chạy.

## 4. Chọn công cụ ít tác động trước

Một thứ tự thường phù hợp:

1. Metrics, application logs, GC logs đã bật và dashboard.
2. JVM identity/heap summary và một số thread dump có kiểm soát.
3. JFR recording ngắn với settings mặc định, giới hạn thời gian và dung lượng.
4. Heap dump khi có bằng chứng memory retention/OOM và đã đánh giá pause, disk, privacy.
5. Core dump khi cần điều tra native/process crash và có runbook riêng.

Đây là thứ tự gợi ý, không phải quy tắc cứng. Nếu service đã crash, không thể lấy thread dump từ process đã dừng; hãy dùng fatal error log và artifact crash đã được hệ điều hành lưu.

### 4.1. Xác định JVM đúng

Trên host:

~~~bash
jcmd -l
~~~

Trong container, PID namespace có thể khác host. Tài liệu Oracle lưu ý danh sách `jcmd -l` không hiển thị JVM chạy trong một Docker process riêng; dùng công cụ như `ps` trong đúng container để xác định PID nội bộ.

Sau khi xác nhận đúng PID, xem version:

~~~bash
jcmd 12345 VM.version
~~~

Thay `12345` bằng PID đã xác minh. `jcmd` phải chạy trên cùng máy với JVM và cùng effective user/group identity đã dùng để khởi chạy JVM. Quyền attach cũng có thể bị giới hạn bởi container, security policy hoặc cách JVM được khởi chạy.

Không dùng PID `0` để “tìm process”. Không dùng tên main class chung nếu nhiều instance có thể trùng tên.

## 5. Thread dump có kiểm soát

Thread dump là snapshot stack trace của các thread trong JVM. Nó hữu ích khi điều tra request bị treo, lock contention, thread pool cạn worker hoặc deadlock.

Lấy một dump:

~~~bash
jcmd 12345 Thread.print -l
~~~

Tùy chọn `-l` yêu cầu in thông tin lock của `java.util.concurrent`. JDK 17 đánh giá `Thread.print` ở mức tác động trung bình, tùy số lượng thread.

Khi cần so sánh trạng thái:

~~~bash
jcmd 12345 Thread.print -l > /secure/diagnostics/thread-01.txt
~~~

Sau đó chụp thêm một hoặc hai lần với khoảng cách ngắn, ví dụ 10–15 giây, theo runbook. Dùng tên file có timestamp UTC và instance/PID để không ghi đè snapshot trước. Khoảng cách và số lần chụp phải phù hợp với tốc độ thay đổi của sự cố; không tạo vòng lặp chụp liên tục.

Khi đọc các dump, tìm:

- Thread nào đang BLOCKED và monitor/lock owner là ai?
- Thread nào WAITING/TIMED_WAITING trên queue, future, socket hoặc condition?
- Nhiều dump có cùng stack trace và lock owner không?
- Thread pool có hết worker hoặc tất cả worker chờ cùng một dependency không?
- Thread đang tiến triển giữa các snapshot hay bị kẹt ở cùng một điểm?

Một thread ở WAITING không mặc định là lỗi; thread pool và scheduler thường có thread chờ khi nhàn rỗi. Cần đối chiếu với request latency, thread state, lock owner và nhiều snapshot.

## 6. JFR: recording có giới hạn

JFR ghi event theo thời gian như CPU sampling, GC, allocation, lock contention, exception và một số hoạt động I/O. Đây thường là lựa chọn hữu ích cho CPU cao hoặc latency biến động vì nó giữ được trình tự sự kiện trong một cửa sổ thời gian.

Với JDK 17, cấu hình `default` được thiết kế overhead thấp và có thể dùng cho recording dài hạn; `profile` thu thập nhiều dữ liệu hơn, overhead cao hơn và nên dùng trong khoảng ngắn khi cần chi tiết.

Ví dụ recording 60 giây, giới hạn thời gian lưu và dung lượng:

~~~bash
jcmd 12345 JFR.start name=incident-2026-11-10 settings=default duration=60s maxage=10m maxsize=256M filename=/secure/diagnostics/incident-12345.jfr
~~~

Các giới hạn cần hiểu:

- `duration=60s` tự kết thúc recording sau một phút.
- `maxage=10m` giới hạn tuổi dữ liệu lưu trên disk trong recording.
- `maxsize=256M` giới hạn dung lượng recording trên disk.
- `filename` xác định vị trí file kết quả.
- `settings=default` dùng cấu hình mặc định ít overhead hơn profile.

Giá trị maxsize phải tương thích với max chunk size đang cấu hình. Kiểm tra option trên đúng JDK bằng:

~~~bash
jcmd 12345 help JFR.start
~~~

Theo dõi recording:

~~~bash
jcmd 12345 JFR.check name=incident-2026-11-10
~~~

Khi recording có duration hữu hạn, chờ hoàn tất rồi kiểm tra file. Nếu dùng recording không có duration, phải có người chịu trách nhiệm dừng nó và ghi rõ nơi lưu kết quả:

~~~bash
jcmd 12345 JFR.stop name=incident-2026-11-10 filename=/secure/diagnostics/incident-12345.jfr
~~~

Nếu dừng recording mà không chỉ định filename, dữ liệu recording có thể bị loại bỏ thay vì được lưu. Đừng khởi chạy recording không thời hạn rồi quên theo dõi.

Xem tóm tắt offline:

~~~bash
jfr summary /secure/diagnostics/incident-12345.jfr
~~~

JFR không phải “miễn phí”. Impact của `JFR.start` phụ thuộc settings và event configuration; tùy chọn profile và event tùy chỉnh có thể làm overhead tăng. Tài liệu JDK 17 nêu rằng cấu hình mặc định được sửa đổi có thể vượt quá 1% overhead. Đo ở môi trường đại diện trước khi áp dụng recording chuyên sâu trên production.

### 6.1. Tránh bật path-to-gc-roots tùy tiện

Path to GC roots hữu ích khi nghi ngờ memory leak vì giúp truy vết object đang được giữ bởi root nào. Tuy nhiên, thu thập đường dẫn này tốn thời gian và có thể làm ứng dụng pause trong một khoảng ngắn. Chỉ bật khi giả thuyết memory leak đã rõ và có phê duyệt cho phép thu thập thêm.

Không bật toàn bộ event, stack trace sâu hoặc sampling tần suất cao chỉ vì muốn “nhiều dữ liệu hơn”. Chọn event theo câu hỏi cần trả lời.

## 7. Heap dump: chỉ khi cần object graph

Heap dump HPROF chứa trạng thái object trong Java heap. Công cụ phân tích có thể dùng dominator tree, retained size, reference path và histogram để tìm object đang giữ bộ nhớ.

Ví dụ lệnh:

~~~bash
jcmd 12345 GC.heap_dump /secure/diagnostics/heap-12345.hprof
~~~

JDK 17 đánh giá `GC.heap_dump` ở mức tác động cao, tùy heap size và nội dung. Lệnh yêu cầu full GC theo mặc định, trừ khi dùng tùy chọn `-all`. Full GC có thể tạo pause lớn. Heap dump còn cần disk đủ lớn và thời gian ghi file.

Tùy chọn `-all` làm dump bao gồm cả object unreachable; nó thay đổi tập object được ghi, không phải một chế độ “an toàn” hay “không pause”. Chỉ dùng khi câu hỏi phân tích yêu cầu và người vận hành hiểu hệ quả.

Trước khi lấy heap dump:

- Có bằng chứng heap retention hoặc OOM cần phân tích object graph không?
- Heap hiện tại bao nhiêu và filesystem đích còn đủ dung lượng không?
- Có thể chấp nhận pause/full GC trong trạng thái tải hiện tại không?
- File sẽ chứa dữ liệu gì và ai được phép đọc?
- Có thể lấy từ một replica ít tải hơn hoặc môi trường tái hiện không?
- Đã có cách truyền file an toàn và thời hạn xóa chưa?

Nếu cần heap dump khi OOM, JVM có tùy chọn:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure/diagnostics
~~~

Đây là cơ chế tự động tạo heap dump khi xảy ra OutOfMemoryError. Nó cần được cấu hình trước, có disk quota, permission và retention phù hợp. Dump tự động không đồng nghĩa không gây tác động; process đang OOM có thể không còn tài nguyên để hoàn tất thao tác, và file có thể chứa dữ liệu nhạy cảm. Không bật trên toàn bộ fleet mà chưa kiểm tra dung lượng và chính sách lưu.

## 8. Class histogram không phải heap dump nhẹ

`GC.class_histogram` cung cấp thống kê heap theo class. Nó hữu ích để xem class nào chiếm số lượng object lớn, nhưng JDK 17 xếp command này ở mức tác động cao vì chi phí phụ thuộc heap size và nội dung.

Không dùng histogram như phép đo rẻ mặc định trên production. Nếu cần, xác định PID, giới hạn số lần chụp, kiểm tra impact trên đúng JDK và lưu output như dữ liệu chẩn đoán. Histogram không cung cấp object graph và đường reference như heap dump, nên không thay thế được phân tích retained object.

Có thể bắt đầu bằng `GC.heap_info` để xem thông tin tổng quát về heap; JDK 17 đánh giá command này ở mức trung bình. Đối chiếu với metrics/GC log trước khi chọn thao tác nặng hơn.

## 9. GC log: thu thập liên tục có giới hạn

GC log thường hữu ích cho pause, heap occupancy và GC frequency. Trên Java 17, unified logging có thể được cấu hình lúc khởi động:

~~~text
-Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Ví dụ này tạo file log có rotation: tối đa năm file, mỗi file khoảng 20 MB. Hãy chọn đường dẫn, số file và kích thước theo volume, throughput và chính sách vận hành thực tế.

GC log khác heap dump:

- GC log ghi sự kiện GC và thống kê heap theo thời gian.
- Heap dump ghi object graph tại một thời điểm.
- GC log thường phù hợp để theo dõi xu hướng và pause.
- Heap dump phù hợp để phân tích object retention khi đã có giả thuyết memory leak.

Không bật GC logging với file path không giới hạn trên filesystem dùng chung. Kiểm tra rotation, quyền ghi, quota và cách thu thập log khi container restart.

## 10. Core dump và JVM fatal error log

Core dump là dữ liệu do hệ điều hành/debugger tạo từ process khi crash hoặc khi được yêu cầu. Nó có thể chứa native memory, Java heap, thread stack, loaded library và dữ liệu process khác. Dung lượng có thể lớn và việc tạo core dump có thể làm process dừng hoặc làm tăng I/O.

JVM fatal error log (thường tên `hs_err_pid*.log`) là văn bản được HotSpot ghi khi gặp lỗi fatal. File này có thể chứa signal/exception, native stack, thread, JVM flags, loaded libraries và môi trường. Nó khác core dump: fatal error log là báo cáo text, core dump là snapshot bộ nhớ/process theo cơ chế OS.

Quy tắc vận hành:

- Giữ fatal error log gốc cùng timestamp và build/runtime identity.
- Core dump chỉ lấy khi cần phân tích native/JVM crash bằng debugger hoặc đội phụ trách.
- Không dùng lệnh ép process abort chỉ để “thử xem có core dump không”.
- Kiểm tra OS core pattern, quota, filesystem, quyền đọc và chính sách retention trước khi bật core dump.
- Phân tích offline trên máy có quyền truy cập hạn chế; không mở file production nhạy cảm trên máy cá nhân không được quản lý.

Core dump không phải cách thay thế heap dump cho mọi OOM. Chọn loại dữ liệu theo loại lỗi và công cụ phân tích dự kiến.

## 11. Kiểm soát nơi lưu, quyền truy cập và retention

Mỗi dump cần có lifecycle rõ ràng:

1. **Thư mục riêng:** dùng volume diagnostics riêng, không ghi vào thư mục ứng dụng hoặc container writable layer nếu không cần.
2. **Quyền tối thiểu:** chỉ tài khoản service/incident responder được tạo hoặc đọc file.
3. **Mã hóa:** mã hóa khi lưu và khi truyền; quản lý key theo quy trình tổ chức.
4. **Đặt tên:** service, instance, PID, timestamp UTC, loại dump và incident ID.
5. **Quota:** giới hạn số file, tổng dung lượng và dung lượng cho mỗi incident.
6. **Retention:** đặt thời hạn lưu phù hợp mục đích; tự động xóa khi hết hạn.
7. **Audit:** ghi ai tạo, tải, phân tích, chia sẻ và xóa file.
8. **Transfer:** dùng artifact store hoặc kênh bảo mật được phê duyệt; xác minh checksum sau truyền.
9. **Redaction:** nếu có thể, lọc hoặc trích xuất phần cần thiết trước khi chia sẻ rộng.
10. **Cleanup:** xác nhận file bản sao, cache phân tích và bản tạm đều được xử lý sau incident.

Không mặc định rằng file trong thư mục /tmp hoặc workspace cá nhân sẽ tự biến mất. Container volume, node disk, backup và artifact store có thể giữ bản sao lâu hơn dự kiến.

## 12. Runbook khi cần chẩn đoán production

Một quy trình có kiểm soát có thể gồm các bước sau:

### Bước 1: Ghi nhận sự cố

Ghi incident ID, service, môi trường, build/version, instance/pod, PID, thời điểm UTC, triệu chứng, metric liên quan và người chịu trách nhiệm. Không ghi token hoặc dữ liệu khách hàng vào tên file/log.

### Bước 2: Kiểm tra baseline

Dùng dashboard, application log, GC log và thông tin JVM đã được thu thập. Xác định lỗi ảnh hưởng toàn bộ fleet hay một replica. Không tạo dump trên tất cả replica cùng lúc.

### Bước 3: Chọn một process đại diện

Xác định đúng PID trong đúng host/container và kiểm tra JVM version. Đối chiếu service identity để tránh attach vào sidecar, agent hoặc JVM khác trên cùng node.

### Bước 4: Bắt đầu bằng phép đo có tác động thấp hơn

Nếu process treo, lấy số lượng thread dump nhỏ theo runbook. Nếu CPU/latency cao, cân nhắc JFR default ngắn có giới hạn duration/maxage/maxsize. Theo dõi latency, error rate, CPU, memory và disk trong khi thu thập.

### Bước 5: Chỉ nâng mức khi có lý do

Heap dump chỉ khi cần object graph để kiểm tra retention/leak và đã đánh giá full GC, pause, disk và privacy. Core dump chỉ khi điều tra native/JVM crash và có người phụ trách phê duyệt.

### Bước 6: Xác minh file

Kiểm tra file tồn tại, kích thước, timestamp, checksum và nội dung cơ bản. Không mở hoặc gửi file thô đến công cụ phân tích chưa được phê duyệt.

### Bước 7: Phân tích và đóng incident

Phân tích trong môi trường hạn chế quyền. Ghi kết luận, bằng chứng, giới hạn và cách khắc phục. Sau đó xóa file theo retention, xác nhận bản sao/backup và thu hồi quyền tạm thời.

### Bước 8: Cải thiện observability

Nếu sự cố lặp lại, ưu tiên metrics, logs, bounded JFR, GC logging và alert phù hợp để lần sau không cần chụp dump khẩn cấp không kiểm soát.

## 13. Tự động hóa an toàn

Dump tự động có thể hữu ích nếu đã thiết kế giới hạn:

- Bật heap dump on OOM chỉ trên workload đã kiểm tra disk capacity, path, permissions và retention.
- Dùng JFR default continuous recording với giới hạn maxage/maxsize khi có nhu cầu vận hành rõ.
- Giới hạn số recording đồng thời trên một JVM.
- Đặt quota theo service/instance, không để một process lấp đầy node disk.
- Dùng tên file duy nhất theo PID/time/incident ID để tránh ghi đè.
- Cảnh báo khi recording tồn tại quá thời hạn hoặc disk usage vượt ngưỡng.
- Không tự động tạo heap/core dump trên mọi replica chỉ vì một alert ngắn hạn.
- Kiểm tra runbook khi nâng JDK vì command, option và impact có thể thay đổi.

Nếu dùng JFR continuous, người trực sự cố cần biết cách kiểm tra recording hiện có bằng `JFR.check` và cách dump cửa sổ thời gian cần thiết. Không tạo thêm recording mới khi một recording phù hợp đã chạy, trừ khi có lý do rõ ràng.

## 14. Các anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách làm phù hợp |
|---|---|---|
| Chạy `jcmd 0 GC.heap_dump ...` | Gửi lệnh đến mọi JVM có thể truy cập | Chỉ định PID đã xác minh |
| Lấy heap dump ngay khi thấy memory tăng | Full GC/pause, file lớn, lộ dữ liệu | Xem metrics/GC log, đánh giá retention và xin phê duyệt |
| Lặp heap dump liên tục | Tăng pause, CPU và disk I/O | Xác định số snapshot tối thiểu, so sánh histogram/metrics trước |
| Chạy class histogram theo chu kỳ ngắn | Command impact cao | Dùng metrics nhẹ hơn, chỉ lấy histogram khi cần |
| JFR profile vô thời hạn | Overhead và file tích lũy | Dùng default hoặc duration/maxage/maxsize rõ ràng |
| Bật path-to-gc-roots mọi lúc | Thu thập tốn thời gian, có thể pause | Chỉ bật khi điều tra memory leak có mục tiêu |
| Ghi dump vào /tmp hoặc root filesystem | Có thể lấp đầy disk/container layer | Dùng diagnostics volume có quota |
| Lưu dump trên máy cá nhân | Mất kiểm soát quyền và retention | Dùng nơi lưu bảo mật được phê duyệt |
| Gửi heap/core dump vào ticket/chat | Lộ toàn bộ hoặc phần lớn dữ liệu process | Chia sẻ kết quả phân tích đã lọc, hoặc transfer an toàn |
| Không ghi PID/instance/time | Không biết dump thuộc process nào | Gắn metadata và incident ID |
| Không dừng recording | File và overhead tiếp tục tăng | Đặt duration/maxage/maxsize, có owner theo dõi |
| Bỏ quên bản sao sau incident | Dữ liệu nhạy cảm tồn tại ngoài dự kiến | Cleanup và audit toàn bộ bản sao |

## 15. Ví dụ Java 17: tạo process lab để thực hành an toàn

Ví dụ dưới đây tạo một process nhỏ để hiểu cách xác định trạng thái JVM. Chạy trong thư mục lab trên máy phát triển, không dùng làm lệnh chạy production.

Tạo `DumpLab.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class DumpLab {
    public static void main(String[] args) throws InterruptedException {
        List<byte[]> retained = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            retained.add(new byte[128 * 1024]);
        }

        System.out.println("DUMP_LAB_READY");
        if (args.length > 0 && "--self-test".equals(args[0])) {
            return;
        }
        while (true) {
            Thread.sleep(1000);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d out DumpLab.java
java -Xms16m -Xmx32m -cp out DumpLab
~~~

Output:

~~~text
DUMP_LAB_READY
~~~

Mở terminal thứ hai, xác định PID của đúng process lab bằng `jcmd -l`, sau đó thay `<pid>` bằng PID thực tế:

~~~bash
jcmd <pid> VM.version
jcmd <pid> Thread.print -l
jcmd <pid> GC.heap_info
~~~

Nếu muốn thử JFR, dùng recording ngắn có giới hạn:

~~~bash
jcmd <pid> JFR.start name=lab settings=default duration=10s maxage=1m maxsize=64M filename=lab.jfr
jcmd <pid> JFR.check name=lab
jfr summary lab.jfr
~~~

Heap dump chỉ nên được thử trong lab khi đã hiểu rằng command yêu cầu full GC theo mặc định:

~~~bash
jcmd <pid> GC.heap_dump lab.hprof
~~~

Có thể kiểm tra code lab và stdout mà không giữ process chạy lâu bằng:

~~~bash
java -Xms16m -Xmx32m -cp out DumpLab --self-test
~~~

Output chính xác:

~~~text
DUMP_LAB_READY
~~~

Sau thực hành, dừng process lab bằng Ctrl+C và xóa file lab theo nhu cầu. Ví dụ này không phải một runbook production; production cần process identity, approval, secure storage, resource budget và retention đã được xác định.

## 16. Checklist trước, trong và sau khi tạo dump

### Trước khi tạo

- [ ] Đã xác định câu hỏi chẩn đoán và loại dump cần thiết.
- [ ] Đã xác nhận đúng service, instance, container, PID và JDK version.
- [ ] Đã kiểm tra impact của command trên đúng JDK.
- [ ] Đã đánh giá tải hiện tại và khả năng pause/latency.
- [ ] Đã kiểm tra dung lượng, quota, filesystem và vị trí lưu.
- [ ] Đã xác định dữ liệu nhạy cảm có thể xuất hiện.
- [ ] Đã có người phê duyệt, owner và người nhận file.
- [ ] Đã đặt giới hạn thời gian, số lần, kích thước và retention.
- [ ] Đã chuẩn bị điều kiện dừng khi service hoặc disk xấu đi.

### Trong khi tạo

- [ ] Chỉ nhắm đúng PID, không dùng PID 0.
- [ ] Không tạo nhiều loại dump cùng lúc nếu chưa cần.
- [ ] Theo dõi latency, error rate, CPU, memory và disk.
- [ ] Ghi timestamp UTC, incident ID, PID và instance.
- [ ] Dừng recording khi hết thời hạn hoặc đạt mục tiêu.

### Sau khi tạo

- [ ] Xác minh file, kích thước, timestamp và checksum.
- [ ] Lưu file ở nơi mã hóa và phân quyền phù hợp.
- [ ] Không gửi file thô qua kênh không được phê duyệt.
- [ ] Phân tích offline trong môi trường hạn chế quyền.
- [ ] Ghi kết luận và giới hạn của bằng chứng.
- [ ] Xóa file và mọi bản sao khi hết retention.
- [ ] Thu hồi quyền truy cập tạm thời.
- [ ] Cập nhật runbook/observability để tránh lặp lại thao tác khẩn cấp.

## 17. Ghi nhớ

Dump là bằng chứng có chi phí, không phải thao tác mặc định mỗi khi production có lỗi. Thread dump giúp xem thread/lock; heap dump giúp phân tích object retention nhưng có impact cao và mặc định yêu cầu full GC; JFR cho dữ liệu theo thời gian với overhead tùy settings; GC log hỗ trợ theo dõi pause/heap; core dump phục vụ điều tra native/process crash và có thể chứa bộ nhớ rất nhạy cảm.

Chọn loại dữ liệu theo giả thuyết, xác định đúng process, giới hạn thời gian/dung lượng, theo dõi tác động và quản lý file như dữ liệu production. Chỉ tạo dump khi có mục tiêu, owner, quyền truy cập, nơi lưu và thời hạn xóa rõ ràng.

Tài liệu tham khảo:

- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 17 — Prepare for Troubleshooting](https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html)
- [Oracle Java SE 17 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-guide.pdf)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [JDK Flight Recorder — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html)