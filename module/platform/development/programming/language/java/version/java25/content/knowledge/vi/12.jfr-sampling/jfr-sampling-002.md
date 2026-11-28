# Tạo, dừng và thu thập bản ghi bằng tùy chọn JVM hoặc công cụ chẩn đoán JDK

> **Chương:** Lấy mẫu JFR
>
> **Phạm vi:** Java 25 / JDK 25. Bài thực hành hướng dẫn tạo recording khi khởi động, gắn vào JVM đang chạy bằng `jcmd`, dump hoặc stop recording, thu thập file `.jfr` và đọc dữ liệu bằng công cụ JDK. Nội dung ưu tiên các lệnh hiện hành, cấu hình có giới hạn và các cải tiến JFR đã có trong Java 25.

## 1. JFR dùng để làm gì?

**Java Flight Recorder (JFR)** là hệ thống ghi sự kiện và dữ liệu chẩn đoán được tích hợp trong JVM. Một recording có thể lưu dấu thời gian, thread, stack trace và các sự kiện liên quan đến:

- CPU và method execution samples.
- Garbage collection, allocation và heap.
- Thread scheduling, monitor contention, park và sleep.
- File I/O, socket I/O và các sự kiện JVM khác.
- Sự kiện do ứng dụng tự định nghĩa bằng API `jdk.jfr`.

JFR phù hợp cho việc ghi dữ liệu khi ứng dụng chạy và phân tích lại sau sự cố. Thay vì phải dự đoán chính xác thời điểm xảy ra vấn đề để mở profiler, một dịch vụ có thể duy trì recording liên tục với cấu hình ít overhead, sau đó dump khoảng thời gian gần lúc có cảnh báo.

### Kết quả sau bài học

Bạn sẽ có thể:

1. Khởi động recording bằng `-XX:StartFlightRecording`.
2. Bắt đầu, kiểm tra, dump và dừng recording của JVM đang chạy bằng `jcmd`.
3. Chọn `default.jfc` hoặc `profile.jfc` đúng mục tiêu.
4. Giới hạn dữ liệu bằng `maxage` và `maxsize`.
5. Đọc file bằng `jfr summary`, `jfr view`, `jfr print` và JDK Mission Control.
6. Bảo vệ recording và thu thập đủ dữ liệu mà không tạo file không giới hạn.

## 2. Chọn đúng cấu hình recording

JDK 25 có hai cấu hình dựng sẵn trong thư mục `JAVA_HOME/lib/jfr`:

| Cấu hình | Mục tiêu | Cách sử dụng |
| --- | --- | --- |
| `default.jfc` | Thu thập liên tục với mức dữ liệu và overhead thấp | Dùng làm nền cho recording dài hạn hoặc production always-on. |
| `profile.jfc` | Thu thập nhiều sự kiện hơn để tìm bottleneck chi tiết | Dùng trong khoảng ngắn khi cần phân tích chuyên sâu. |

`default.jfc` là lựa chọn phù hợp cho recording liên tục. `profile.jfc` ghi nhiều dữ liệu hơn và có thể ảnh hưởng hiệu năng, nên chỉ bật trong khoảng thời gian cần điều tra. Overhead thực tế phụ thuộc workload, event settings, tần suất sự kiện và phần cứng; hãy đo trên môi trường đại diện.

Không bắt đầu bằng một cấu hình tự bật mọi event. Một recording quá chi tiết có thể tạo file lớn, tăng chi phí ghi và làm khó việc tìm thông tin cần thiết. Nếu event mặc định chưa đủ, tạo một file `.jfc` riêng từ cấu hình dựng sẵn rồi chỉnh đúng event cần phân tích; không sửa file `default.jfc` hoặc `profile.jfc` của JDK.

## 3. Xác định JVM và quyền thu thập

`jcmd` nằm trong thư mục `bin` của JDK. Để liệt kê các JVM có thể nhìn thấy trên cùng máy:

~~~bash
jcmd -l
~~~

Ví dụ kết quả:

~~~text
4812 com.example.orders.OrderApplication
9270 org.apache.catalina.startup.Bootstrap
~~~

Trong các ví dụ sau, `4812` là PID minh họa. Thay bằng PID thật của tiến trình cần điều tra.

### Điều kiện attach

- Chạy `jcmd` trên cùng máy với JVM đích.
- Thông thường phải dùng cùng effective user/group đã khởi chạy JVM.
- Trong container, PID namespace có thể khác host; `jcmd -l` không nhất thiết liệt kê JVM chạy trong Docker process riêng. Hãy chạy công cụ trong đúng container hoặc dùng PID namespace phù hợp.
- Dùng `jcmd <pid> help` để kiểm tra các diagnostic command được JVM đích hỗ trợ.

~~~bash
jcmd 4812 help
jcmd 4812 help JFR.start
jcmd 4812 help JFR.dump
~~~

Không mở quyền attach hoặc quyền đọc file recording cho người dùng không được phép. JFR có thể chứa tên class/method, stack trace, đường dẫn file, thông tin request hoặc dữ liệu do ứng dụng ghi vào custom event.

## 4. Cách 1 — Tạo recording ngay khi JVM khởi động

Nếu có thể cấu hình lệnh khởi chạy ứng dụng, dùng `-XX:StartFlightRecording`. Cách này hữu ích khi muốn thu thập từ những giây đầu tiên hoặc cần ghi dữ liệu trước khi sự cố xảy ra.

### 4.1. Recording có thời lượng cố định

~~~bash
java -XX:StartFlightRecording:name=checkout-profile,settings=profile,duration=90s,filename=checkout-profile.jfr,dumponexit=true -jar checkout-service.jar
~~~

Tùy chọn minh họa:

| Tham số | Ý nghĩa |
| --- | --- |
| `name` | Tên recording để nhận diện. |
| `settings=profile` | Dùng cấu hình profiling có nhiều dữ liệu hơn. |
| `duration=90s` | Tự kết thúc sau 90 giây. Có thể dùng `s`, `m`, `h` hoặc `d`. |
| `filename` | Đường dẫn file `.jfr` khi recording được ghi ra. |
| `dumponexit=true` | Ghi recording đang chạy khi JVM shutdown. |

Khi recording đạt thời lượng, JFR hoàn tất file theo cấu hình. `dumponexit=true` là bảo vệ thêm cho trường hợp JVM shutdown trước khi hết thời lượng; không nên dựa vào nó để thay thế quy trình dump/stop có kiểm soát.

### 4.2. Bắt đầu với cấu hình ít overhead

~~~bash
java -XX:StartFlightRecording:name=checkout-continuous,settings=default,disk=true,maxage=6h,maxsize=1g -jar checkout-service.jar
~~~

Recording này được giữ liên tục và giới hạn dữ liệu trên disk theo tuổi tối đa 6 giờ hoặc kích thước tối đa 1 GB. Khi cần lấy dữ liệu, dùng `jcmd JFR.dump` như phần 6. Giá trị `maxage`/`maxsize` phải được chọn theo tốc độ phát sinh event, dung lượng đĩa và khoảng thời gian điều tra cần giữ.

### 4.3. Xem trợ giúp tham số JVM

~~~bash
java -XX:StartFlightRecording:help
~~~

Phần tham số của `-XX:StartFlightRecording` là danh sách `key=value` phân tách bằng dấu phẩy. Nếu shell hoặc cách gọi JVM yêu cầu, đặt cả danh sách trong dấu nháy kép:

~~~bash
java "-XX:StartFlightRecording:name=checkout-profile,settings=profile,duration=90s,filename=checkout-profile.jfr" -jar checkout-service.jar
~~~

## 5. Cách 2 — Bắt đầu recording trên JVM đang chạy

Không cần restart ứng dụng chỉ để bắt đầu thu thập. Dùng `JFR.start`:

~~~bash
jcmd 4812 JFR.start name=incident-profile settings=profile duration=2m filename=incident-profile.jfr
~~~

JVM bắt đầu recording `incident-profile` với `profile.jfc`, ghi tối đa 2 phút và lưu vào file đã chỉ định khi recording kết thúc.

Nếu muốn bắt đầu một recording có thời lượng không giới hạn, có thể bỏ `duration`; cần chủ động dump hoặc stop sau đó:

~~~bash
jcmd 4812 JFR.start name=incident-window settings=profile disk=true
~~~

JFR trả về thông tin recording, bao gồm tên hoặc ID được tạo. Hãy giữ lại tên đó để sử dụng cho `JFR.check`, `JFR.dump` và `JFR.stop`.

### Kiểm tra recording đang chạy

~~~bash
jcmd 4812 JFR.check
jcmd 4812 JFR.check name=incident-window verbose=true
~~~

`JFR.check` cho biết recording nào đang hoạt động; `verbose=true` hiển thị thêm event settings. Nếu không nhớ tên recording, chạy lệnh không có `name`.

## 6. Dump dữ liệu mà không dừng recording

Đây là thao tác hữu ích nhất khi điều tra production. `JFR.dump` ghi dữ liệu hiện có ra file nhưng **recording vẫn tiếp tục chạy**:

~~~bash
jcmd 4812 JFR.dump name=incident-window filename=incident-snapshot.jfr
~~~

Có thể dump một khoảng thời gian thay vì toàn bộ dữ liệu đang giữ:

~~~bash
jcmd 4812 JFR.dump name=incident-window begin=-15m filename=incident-last-15m.jfr
~~~

`begin=-15m` yêu cầu lấy dữ liệu bắt đầu từ 15 phút trước thời điểm dump. JDK 25 hỗ trợ `begin`/`end` theo thời gian tuyệt đối hoặc thời gian tương đối (ví dụ `-15m`, `-30s`). Nếu cần giới hạn chính xác khoảng thời gian, kiểm tra định dạng timestamp trong tài liệu `jcmd` của đúng JDK.

Sau dump, kiểm tra recording vẫn còn:

~~~bash
jcmd 4812 JFR.check name=incident-window
~~~

Nếu cần tiếp tục thu thập sau snapshot, không dùng `JFR.stop` ở bước này. Dump nhiều lần có thể tạo nhiều file; đặt tên file có PID/thời điểm hoặc mã incident để tránh ghi đè và giúp đối chiếu.

## 7. Dừng recording và bảo toàn file

`JFR.stop` kết thúc recording. Nếu muốn giữ dữ liệu, **phải chỉ định `filename`**:

~~~bash
jcmd 4812 JFR.stop name=incident-window filename=incident-final.jfr
~~~

Nếu bỏ `filename`, dữ liệu của recording bị loại bỏ thay vì được lưu thành file. Vì vậy, hãy xác nhận đường dẫn đích và dung lượng trống trước khi stop.

Kiểm tra lại:

~~~bash
jcmd 4812 JFR.check
~~~

Nếu recording đã dừng, tên `incident-window` không còn xuất hiện trong danh sách đang chạy.

### Phân biệt ba lệnh lifecycle

| Lệnh | Tác dụng | Recording sau lệnh |
| --- | --- | --- |
| `JFR.start` | Tạo và bắt đầu recording | Đang chạy |
| `JFR.dump` | Ghi snapshot ra file | **Tiếp tục chạy** |
| `JFR.stop` | Kết thúc recording; có thể ghi file bằng `filename` | Đã dừng |

Đừng nhầm `JFR.dump` với `JFR.stop`: nếu mục tiêu là chụp nhanh dữ liệu rồi tiếp tục theo dõi, dùng `dump`; nếu mục tiêu là kết thúc phiên thu thập, dùng `stop filename=...`.

## 8. Duy trì recording liên tục có giới hạn

Với dịch vụ dài hạn, một recording dùng `default.jfc` và giới hạn tuổi/kích thước có thể lưu dữ liệu gần nhất để điều tra sau sự cố.

~~~bash
jcmd 4812 JFR.start name=always-on settings=default disk=true maxage=6h maxsize=1g
~~~

Khi có cảnh báo:

~~~bash
jcmd 4812 JFR.dump name=always-on filename=orders-before-incident.jfr
~~~

Sau khi điều tra xong hoặc khi cần giải phóng recording:

~~~bash
jcmd 4812 JFR.stop name=always-on filename=orders-recording-final.jfr
~~~

`maxage` và `maxsize` là giới hạn dữ liệu được giữ cho recording ghi ra disk. Khi chạm giới hạn, dữ liệu cũ được loại dần để giữ cửa sổ gần nhất; đây không phải giới hạn kích thước của file dump đã xuất. File dump là bản dữ liệu được lưu riêng và phải có chính sách retention riêng.

### Chọn cửa sổ lưu trữ

| Nhu cầu | Cấu hình khởi đầu để thử |
| --- | --- |
| Dịch vụ production cần lịch sử gần đây | `settings=default,maxage=6h,maxsize=1g` |
| Một phiên profiling ngắn | `settings=profile,duration=1m` đến `5m` |
| Điều tra memory leak nghi ngờ | Recording profile phù hợp, sau đó cân nhắc `path-to-gc-roots=true` trong một lần dump có chủ đích |

Đây là điểm xuất phát, không phải định mức chung. Dùng số liệu dung lượng thực tế để điều chỉnh; nếu event rate cao, một GB có thể chỉ giữ được một khoảng thời gian ngắn.

## 9. Phân tích file bằng công cụ JDK

File `.jfr` là định dạng nhị phân. JDK cung cấp lệnh `jfr` trong thư mục `JAVA_HOME/bin`.

### 9.1. Kiểm tra tổng quan

~~~bash
jfr summary incident-snapshot.jfr
~~~

`jfr summary` cho biết metadata tổng quan, khoảng thời gian và số lượng event. Bước này giúp xác nhận file có dữ liệu, nhận diện event nào chiếm dung lượng lớn và quyết định cần lọc gì tiếp.

### 9.2. Xem các nhóm dữ liệu tổng hợp

~~~bash
jfr view all-views incident-snapshot.jfr
jfr view all-events incident-snapshot.jfr
~~~

Có thể xem một view cụ thể nếu biết tên view:

~~~bash
jfr view <view-name> incident-snapshot.jfr
~~~

Danh sách view phụ thuộc JDK và nội dung recording. Dùng `jfr help view` hoặc `jfr view all-views` để biết các view có sẵn, sau đó thay `<view-name>` bằng tên một view trong danh sách; không giả định mọi bản JDK đều có cùng danh sách.

### 9.3. In event cần điều tra

~~~bash
jfr print --events jdk.ExecutionSample incident-snapshot.jfr
jfr print --events jdk.GarbageCollection incident-snapshot.jfr
jfr print --categories GC incident-snapshot.jfr
~~~

Có thể giới hạn stack depth hoặc xuất dữ liệu dạng máy đọc được:

~~~bash
jfr print --stack-depth 20 --events jdk.ExecutionSample incident-snapshot.jfr
jfr print --json --events jdk.GarbageCollection incident-snapshot.jfr
~~~

`jfr metadata incident-snapshot.jfr` liệt kê event và cấu trúc field có trong recording. Đây là cách kiểm tra event có được ghi hay không trước khi viết filter hoặc pipeline phân tích.

### 9.4. Lọc dữ liệu trước khi chia sẻ

Recording có thể chứa thông tin nhạy cảm. `jfr scrub` cho phép tạo bản đã lọc theo event, category hoặc thread:

~~~bash
jfr scrub --exclude-events jdk.SocketRead,jdk.SocketWrite incident-snapshot.jfr incident-scrubbed.jfr
~~~

Ví dụ chỉ mang tính minh họa; hãy chọn filter theo dữ liệu thật cần bảo vệ. Sau khi scrub, kiểm tra lại file bằng `jfr summary` và `jfr print` để xác nhận nội dung còn lại đủ cho mục tiêu điều tra. Không coi scrub là bảo đảm tự động xóa mọi bí mật; hãy kiểm tra custom event và trường dữ liệu do ứng dụng tự ghi.

## 10. Phân tích bằng JDK Mission Control

**JDK Mission Control (JMC)** cung cấp giao diện để xem recording dưới dạng bảng, biểu đồ, call tree và các nhóm sự kiện. JMC không nằm trong bộ cài JDK tiêu chuẩn; cài riêng nếu cần giao diện phân tích.

Quy trình cơ bản:

1. Mở file `.jfr` bằng JMC.
2. Kiểm tra khoảng thời gian, event count và thông tin JVM.
3. Xem CPU usage, Hot Methods, Thread, Lock Instances và Garbage Collections.
4. Chọn vùng thời gian có latency spike hoặc sự cố.
5. Đi từ event tổng quan tới stack trace và method liên quan.
6. Đối chiếu với metric ứng dụng, log và thời điểm incident.

Một recording có nhiều event không tự nói ra nguyên nhân. Hãy đặt câu hỏi cụ thể:

- CPU cao: thread nào có nhiều execution samples và method nào xuất hiện nhiều trong stack?
- Latency tăng: thread đang chạy code, chờ monitor, park, sleep hay đợi I/O?
- GC pause: loại GC, thời lượng, allocation pressure và heap occupancy thay đổi thế nào?
- Lock contention: thread nào giữ lock và thread nào phải chờ?
- Allocation tăng: class nào được tạo nhiều và stack trace nào dẫn đến allocation?

## 11. Những điểm JFR mới trong Java 25

JDK 25 có ba thay đổi đáng biết khi đọc recording:

| JEP | Trạng thái trong JDK 25 | Ý nghĩa |
| --- | --- | --- |
| **518 — JFR Cooperative Sampling** | Tính năng JDK 25 | Cải thiện độ ổn định của việc lấy mẫu stack bằng cách phối hợp việc stack walking tại safepoint và giảm safepoint bias. |
| **520 — JFR Method Timing & Tracing** | Tính năng JDK 25 | Bổ sung khả năng timing và tracing lời gọi method bằng bytecode instrumentation. |
| **509 — JFR CPU-Time Profiling** | **Experimental** trong JDK 25 | Thu thập CPU-time samples chính xác hơn trên Linux; không xem là baseline ổn định cho production. |

### Sampling khác method timing/tracing

- **Sampling** lấy mẫu stack theo thời điểm. Nó phù hợp để tìm nơi chương trình dành nhiều thời gian mà không cần ghi từng lần gọi method.
- **Method timing/tracing** dùng instrumentation để ghi thông tin lời gọi và thời lượng method được chọn. Dữ liệu chi tiết hơn nhưng phải lọc hẹp để kiểm soát overhead và kích thước recording.

JEP 518 cải thiện cơ chế sampling nền tảng. JEP 520 mở rộng khả năng đo/tracing method; trong JDK 25 có các event `jdk.MethodTiming` và `jdk.MethodTrace`. Khi cần các event này, cấu hình custom JFC với filter method/package cụ thể và xác nhận bằng `jfr metadata`. Không bật tracing mọi method của ứng dụng trong recording production dài hạn.

JEP 509 vẫn được đánh dấu experimental trong Java 25 và chỉ nhắm tới Linux. Bài thực hành này không dùng nó làm cấu hình mặc định; nếu một môi trường nghiên cứu cần thử, phải tách riêng khỏi baseline và xác minh lại trạng thái hỗ trợ ở đúng bản JDK.

## 12. Tạo custom JFC khi event mặc định chưa đủ

Khi cần bật event hoặc thay threshold/period, tạo cấu hình mới từ `default.jfc` hoặc `profile.jfc` bằng `jfr configure`:

~~~bash
jfr configure --input profile.jfc --output checkout-profile.jfc
~~~

Sau đó chỉnh các event settings theo mục tiêu, ví dụ bật một event duration hoặc cấu hình filter cho method tracing. Cú pháp tổng quát của event setting là:

~~~text
<event-name>#<setting-name>=<value>
~~~

Các setting phổ biến gồm:

| Setting | Ý nghĩa |
| --- | --- |
| `enabled` | Có ghi event hay không. |
| `threshold` | Chỉ ghi event có duration đạt ngưỡng. |
| `period` | Chu kỳ của event dạng periodic. |
| `stackTrace` | Có ghi stack trace cho event hay không. |
| `filter` | Chọn class/method cho các event hỗ trợ filter, gồm `jdk.MethodTiming` và `jdk.MethodTrace`. |

Kiểm tra cú pháp và setting thực tế trên đúng JDK bằng:

~~~bash
jfr help configure
jfr metadata
~~~

Sau khi tạo file JFC, dùng nó khi khởi động hoặc attach:

~~~bash
jcmd 4812 JFR.start name=checkout-methods settings=checkout-profile.jfc duration=60s filename=checkout-methods.jfr
~~~

Đặt đường dẫn đầy đủ nếu file JFC không nằm trong thư mục mặc định của JDK. Không sửa cấu hình dựng sẵn; giữ custom JFC cùng phiên bản source/configuration trong kho cấu hình của nhóm để có thể tái tạo kết quả.

## 13. Lưu ý khi recording memory leak

Nếu nghi ngờ memory leak, recording cần bắt đầu **trước khi** tiến trình hết bộ nhớ hoặc trước khi restart. Có thể dump dữ liệu kèm đường dẫn tới GC roots:

~~~bash
jcmd 4812 JFR.dump name=always-on filename=memory-investigation.jfr path-to-gc-roots=true
~~~

Thu thập path-to-GC-roots có thể mất thời gian và làm ứng dụng pause trong một khoảng ngắn. Chỉ bật khi thực sự nghi ngờ memory leak, không bật cho recording liên tục mặc định.

Recording có thể cho biết allocation stack và các dấu hiệu giữ object; nó không thay thế heap dump trong mọi tình huống. Khi cần xác định object graph đang giữ reference, hãy cân nhắc thêm heap dump và phân tích bằng công cụ phù hợp, đồng thời tính đến tác động pause/dung lượng.

## 14. Quyền truy cập, dung lượng và dữ liệu nhạy cảm

Một file JFR có thể tiết lộ:

- Tên package, class, method và stack trace nội bộ.
- Tên thread, đường dẫn file, tên host hoặc endpoint.
- Exception message, custom event field hoặc metadata nghiệp vụ.
- Thông tin request nếu ứng dụng tự ghi vào event.

Vì vậy:

- Lưu file ở thư mục có quyền truy cập hạn chế.
- Đặt retention cho file dump đã xuất; giới hạn `maxage`/`maxsize` của recording không tự quản lý các file dump đã lưu riêng.
- Không gửi file recording production lên nơi công khai hoặc ticket không kiểm soát quyền.
- Dùng `jfr scrub` hoặc quy trình lọc được phê duyệt trước khi chia sẻ.
- Không bật event/custom field có chứa password, token, secret hoặc payload nhạy cảm.
- Xóa file sau khi hết mục đích điều tra theo chính sách lưu trữ của tổ chức.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `jcmd -l` không thấy JVM | JVM nằm trong container namespace khác hoặc user không có quyền nhìn thấy | Chạy `jcmd` trong đúng container/namespace và đúng user. |
| Attach báo permission/access denied | Effective user/group khác hoặc cơ chế attach bị giới hạn | Dùng đúng tài khoản chạy JVM và kiểm tra policy runtime/container. |
| `JFR.start` không tìm thấy settings | Tên JFC sai hoặc file ngoài thư mục JDK | Dùng `default`/`profile` hoặc cung cấp path đầy đủ tới `.jfc`. |
| File `.jfr` không xuất hiện sau `JFR.start` | Recording vẫn đang chạy, chưa dump/stop hoặc filename không được đặt | Dùng `JFR.check`, rồi `JFR.dump` hoặc `JFR.stop filename=...`. |
| Dữ liệu bị mất sau `JFR.stop` | Stop mà không chỉ định `filename` | Chỉ stop sau khi xác định đường dẫn file cần lưu. |
| Dump xong recording không còn? | Có thể đã gọi `JFR.stop` thay vì `JFR.dump` | Kiểm tra lệnh và trạng thái bằng `JFR.check`; `JFR.dump` giữ recording chạy. |
| Recording quá lớn | Dùng `profile` quá lâu, bật nhiều event hoặc không giới hạn retention | Dùng `default` cho continuous; giới hạn `maxage`/`maxsize`; bật event chi tiết trong khoảng ngắn. |
| Không thấy event mong muốn | Event chưa bật hoặc threshold/period không phù hợp | Dùng `jfr metadata`, kiểm tra JFC và event setting. |
| File recording chứa thông tin nhạy cảm | Custom event hoặc event có field nhạy cảm | Giới hạn event, scrub trước khi chia sẻ và kiểm soát quyền file. |
| Phân tích CPU không thấy method nóng | Recording quá ngắn, workload không đại diện hoặc sample count thấp | Thu trong lúc workload thật xảy ra; dùng profile ngắn có kiểm soát và so sánh nhiều lần. |

## 16. Bài tập thực hành

### Bài A — Recording khi khởi động

Khởi chạy một ứng dụng test với `-XX:StartFlightRecording`, dùng `settings=profile`, `duration=60s` và một tên file xác định.

**Điều kiện đạt:** file `.jfr` được tạo, `jfr summary` đọc được và recording có khoảng thời gian mong đợi.

### Bài B — Attach vào JVM đang chạy

Khởi chạy ứng dụng trước, tìm PID bằng `jcmd -l`, sau đó:

1. `JFR.start` với tên `manual-profile`.
2. `JFR.check` xác nhận đang chạy.
3. `JFR.dump` tạo snapshot.
4. `JFR.check` xác nhận recording vẫn hoạt động.
5. `JFR.stop` với `filename` để kết thúc và lưu file.

**Điều kiện đạt:** có cả file snapshot và file cuối, recording dừng sau bước 5.

### Bài C — Continuous recording có giới hạn

Khởi động recording `default` với `maxage` và `maxsize`. Dump dữ liệu sau khi tạo workload, xác nhận recording tiếp tục chạy và file dump có thể phân tích.

**Điều kiện đạt:** giải thích được retention của repository khác retention của file dump.

### Bài D — Tìm bottleneck

Dùng `jfr view` hoặc JDK Mission Control để xác định một dấu hiệu: CPU sample tập trung ở method, lock wait, socket read/write hoặc GC pause.

**Điều kiện đạt:** nêu event/stack trace hỗ trợ nhận định, khoảng thời gian và giới hạn của kết luận.

### Bài E — Chia sẻ recording an toàn

Tạo một bản recording đã lọc bằng `jfr scrub`, kiểm tra lại bằng `jfr summary` và `jfr print`.

**Điều kiện đạt:** chỉ giữ event cần thiết cho người nhận và không để lộ field nhạy cảm trong custom event.

## 17. Checklist vận hành

- [ ] Xác định đúng PID, JDK và user của JVM cần attach.
- [ ] Chọn `default` cho continuous recording hoặc `profile` cho phiên profiling ngắn.
- [ ] Đặt tên recording có ý nghĩa và ghi nhận PID/timestamp/incident ID.
- [ ] Giới hạn recording liên tục bằng `maxage` và/hoặc `maxsize`.
- [ ] Phân biệt `JFR.dump` (tiếp tục chạy) với `JFR.stop` (dừng).
- [ ] Khi stop, luôn chỉ định `filename` nếu cần bảo toàn dữ liệu.
- [ ] Kiểm tra file bằng `jfr summary` trước khi chuyển sang phân tích sâu.
- [ ] Dùng `jfr metadata` để xác nhận event có trong file; lọc bằng `jfr print` hoặc `jfr view`.
- [ ] Chỉ bật `profile`, method tracing hoặc path-to-GC-roots trong phạm vi có chủ đích.
- [ ] Không dùng JEP 509 experimental làm baseline production cho Java 25.
- [ ] Hạn chế quyền đọc file JFR, scrub trước khi chia sẻ và đặt retention cho bản dump.
- [ ] Ghi lại JDK vendor/version, JFC settings, lệnh thu thập và thời điểm workload để tái lập kết quả.

## 18. Tài liệu tham khảo chính thức

1. [Oracle Java 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:StartFlightRecording`, `settings`, `duration`, `filename`, `maxage`, `maxsize`, `dumponexit`.
2. [Oracle Java 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` và các tùy chọn.
3. [Oracle Java 25 — The jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`, `view`, `print`, `metadata`, `scrub`, `assemble`, `disassemble`.
4. [Oracle Java 25 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/25/jfapi/flight-recorder-configurations.html): `default.jfc`, `profile.jfc` và cấu hình event.
5. [Oracle Java 25 — Configure Events and Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/configuration.html): event settings, threshold, period, stack trace và filter.
6. [Oracle Java 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): tạo recording, JDK Mission Control và quy trình chẩn đoán.
7. [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): thay đổi cơ chế lấy mẫu stack trong JDK 25.
8. [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): timing và tracing method bằng bytecode instrumentation.
9. [Oracle — Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): trạng thái JEP 518, JEP 520 và JEP 509 experimental.

**Ghi nhớ:** Quy trình JFR có ba thao tác riêng: **start để bắt đầu**, **dump để chụp dữ liệu mà vẫn tiếp tục ghi**, và **stop để kết thúc recording**. Dùng `default` cho lịch sử liên tục có giới hạn, `profile` cho điều tra ngắn, rồi xác nhận file bằng `jfr summary` trước khi phân tích hoặc chia sẻ. JFR chỉ hữu ích khi recording được tạo đúng thời điểm, đúng event, có giới hạn dung lượng và được bảo vệ như dữ liệu vận hành nhạy cảm.
