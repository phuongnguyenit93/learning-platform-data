# Unified Logging với tag, mức ghi và tệp luân phiên trong Java 17

## 1. Unified Logging là gì?

**Unified Logging** là hệ thống ghi log thống nhất của HotSpot JVM, được đưa vào từ Java 9. Thay vì mỗi thành phần JVM có một nhóm cờ ghi log riêng, Unified Logging cung cấp một cú pháp chung để chọn:

- **Tag:** nhóm thông tin cần quan sát, ví dụ GC, heap, class loading hoặc safepoint.
- **Level:** mức độ chi tiết của thông điệp, từ lỗi đến trace.
- **Output:** nơi ghi log, như standard output, standard error hoặc file.
- **Decorator:** metadata được thêm vào mỗi dòng, như thời gian, PID, thread ID, level và tag.
- **Output options:** tùy chọn cho đích ghi, đặc biệt là kích thước và số lượng file luân phiên.

Trong Java 17, Unified Logging là cơ chế hiện hành để quan sát hoạt động của JVM. Ví dụ, thay vì dựa vào các cờ GC logging đời cũ, bạn có thể dùng `-Xlog:gc*` để thu thập log GC và các tag liên quan.

Unified Logging không phải logger của ứng dụng như SLF4J hoặc `java.util.logging`. Nó ghi các sự kiện nội bộ của JVM và một số thành phần runtime. Log ứng dụng vẫn nên được quản lý bằng logging framework phù hợp với ứng dụng.

## 2. Cú pháp tổng quát của `-Xlog`

Cú pháp:

~~~text
-Xlog[:what][:output][:decorators][:output-options]
~~~

Các phần đều có thể được rút gọn hoặc bỏ qua tùy mục đích.

| Phần | Nội dung |
|---|---|
| `what` | Tag selector và level muốn bật. |
| `output` | Đích ghi: `stdout`, `stderr` hoặc `file=...`. |
| `decorators` | Metadata thêm vào từng dòng log. |
| `output-options` | Tùy chọn của output, chẳng hạn `filecount` và `filesize`. |

Ví dụ tối thiểu:

~~~text
-Xlog:gc
~~~

Lệnh này bật log theo tag `gc` ở level mặc định `info` và ghi ra output mặc định của Unified Logging.

Ví dụ đầy đủ hơn:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Nghĩa là:

- Chọn các tag set khớp `gc*` ở level `info`.
- Ghi ra file `gc.log`.
- Thêm thời gian thực, thời gian từ lúc JVM khởi động, level và tag vào mỗi dòng.
- Luân phiên file khi file hiện tại đạt 20 MB và giữ tối đa năm file log đã luân phiên theo cấu hình.

Khi cấu hình logging, hãy tách rõ `what`, `output`, `decorators` và `output-options`. Nhiều lỗi cấu hình đến từ việc đặt nhầm dấu hai chấm hoặc dấu phẩy giữa các phần.

## 3. Tag và tag set

Tag là nhãn do JVM gắn vào một thông điệp log. Mỗi thông điệp có thể mang một hoặc nhiều tag. Ví dụ, thông điệp liên quan đến heap trong GC có thể mang tag set gồm `gc` và `heap`.

### 3.1. Chọn một tag

~~~text
-Xlog:gc=info
~~~

Chọn thông điệp thuộc tag set `gc` ở level `info`.

Một số tag thường gặp:

| Tag | Nhóm thông tin |
|---|---|
| `gc` | Hoạt động garbage collection. |
| `heap` | Trạng thái và cấu trúc heap. |
| `phases` | Các pha bên trong hoạt động GC. |
| `safepoint` | Safepoint và các thông tin liên quan đến việc đưa thread tới trạng thái an toàn. |
| `class` | Hoạt động nạp và gỡ class. |
| `load` | Thông tin nạp class khi kết hợp với tag `class`. |
| `unload` | Thông tin gỡ class khi kết hợp với tag `class`. |
| `os` | Thông tin liên quan đến hệ điều hành. |
| `container` | Thông tin nhận diện giới hạn tài nguyên container trên các runtime hỗ trợ. |
| `compiler` | Hoạt động biên dịch JIT. |
| `jit` | Một số thông tin liên quan tới JIT và runtime compiler. |

Danh sách tag thực tế phụ thuộc build JVM và thành phần được biên dịch vào runtime. Không nên đoán tag từ tên một tính năng; hãy kiểm tra danh sách của chính JDK đang chạy bằng `-Xlog:help`.

### 3.2. Chọn tag set kết hợp

Một selector có thể yêu cầu nhiều tag cùng xuất hiện:

~~~text
-Xlog:gc+heap=debug
~~~

Selector `gc+heap` chọn thông điệp mang cả hai tag `gc` và `heap`. Đây là cách hữu ích khi cần xem chi tiết heap gắn với GC mà không bật toàn bộ thông điệp GC.

Một ví dụ khác:

~~~text
-Xlog:class+load=info
~~~

Selector này ghi thông tin nạp class ở level `info`.

### 3.3. Wildcard `*`

Có thể dùng wildcard ở cuối tag selector để chọn tag set có chứa tag được chỉ định:

~~~text
-Xlog:gc*=info
~~~

`gc*` mở rộng phạm vi hơn `gc` đơn lẻ, bao gồm các tag set liên quan có chứa tag `gc`, chẳng hạn `gc+heap` hoặc `gc+phases`.

Không nên nhầm wildcard này với wildcard tên package trong Java. Đây là cú pháp chọn tag set của Unified Logging.

### 3.4. Nhiều selector trong cùng một cấu hình

Các selector được phân cách bằng dấu phẩy:

~~~text
-Xlog:gc=info,gc+heap=debug
~~~

Ví dụ trên lấy log GC tổng quát ở level `info` và thông tin heap chi tiết hơn ở level `debug`. Bạn có thể kết hợp các tag set theo nhu cầu điều tra, nhưng cần tránh bật quá nhiều nhóm log chi tiết trong production.

### 3.5. Xem tag nào được JVM hỗ trợ

Chạy:

~~~text
java -Xlog:help
~~~

Lệnh này in trợ giúp Unified Logging, bao gồm:

- Các tag set mà runtime hỗ trợ.
- Các level có thể dùng.
- Các decorator.
- Các output options và cú pháp liên quan.

Đây là nguồn kiểm tra đáng tin cậy nhất khi một tag hoặc tùy chọn không hoạt động trên build Java 17 cụ thể. Có thể lưu output này cùng thông tin phiên bản JVM khi chuẩn bị runbook vận hành.

## 4. Level: mức độ chi tiết của log

Unified Logging cung cấp các level sau:

| Level | Mục đích |
|---|---|
| `off` | Tắt thông điệp ở level được chọn. |
| `error` | Sự kiện lỗi. |
| `warning` | Cảnh báo. |
| `info` | Thông tin vận hành tổng quát. |
| `debug` | Thông tin chẩn đoán chi tiết hơn. |
| `trace` | Thông tin rất chi tiết, thường dùng khi điều tra sâu. |

Mức độ chi tiết tăng dần từ `error` tới `trace`. Nếu không ghi level trong selector, level mặc định là `info`.

Ví dụ:

~~~text
-Xlog:gc=warning
-Xlog:gc+heap=debug
-Xlog:class+load=info
-Xlog:safepoint=trace
~~~

`trace` có thể tạo lượng log rất lớn. Chỉ bật khi có mục tiêu điều tra rõ ràng, trong khoảng thời gian phù hợp và với dung lượng lưu trữ đủ.

### 4.1. Level là ngưỡng, không phải bộ lọc theo từ khóa

Khi chọn `debug`, JVM có thể ghi các thông điệp ở mức `debug` và những mức quan trọng hơn của selector đó. Khi chọn `info`, các thông điệp `info`, `warning` và `error` có thể được ghi; các thông điệp `debug` và `trace` không được ghi.

Chọn level phù hợp giúp kiểm soát cả độ chi tiết và lượng log. Không nên mặc định rằng `debug` chỉ thêm một vài dòng; với một số tag, nó có thể tạo dữ liệu đáng kể.

### 4.2. Dùng `off` để tắt một nhóm

Có thể tắt một tag set cụ thể trong cấu hình:

~~~text
-Xlog:gc*=info,gc+heap=off
~~~

Ví dụ này bật log các tag set có chứa `gc`, nhưng tắt nhóm `gc+heap` theo selector riêng. Khi có nhiều selector khớp cùng thông điệp, hãy kiểm tra quy tắc lựa chọn selector bằng tài liệu và `-Xlog:help` của runtime đang dùng; cấu hình càng rõ ràng càng dễ vận hành.

## 5. Output: ghi log ra đâu?

Unified Logging hỗ trợ các đích ghi phổ biến:

| Output | Ý nghĩa |
|---|---|
| `stdout` | Standard output. |
| `stderr` | Standard error. |
| `file=filename` | Ghi vào file được chỉ định. |

Ví dụ ghi GC log ra standard output:

~~~text
-Xlog:gc*=info:stdout
~~~

Ghi ra standard error:

~~~text
-Xlog:gc*=info:stderr
~~~

Ghi ra file:

~~~text
-Xlog:gc*=info:file=gc.log
~~~

Trong môi trường container, việc ghi ra `stdout`/`stderr` thường phù hợp nếu nền tảng triển khai đã thu thập console log. Với máy chủ tự quản lý, ghi ra file riêng có thể thuận tiện cho việc giữ log và phân tích.

### 5.1. Đường dẫn file

Ví dụ trên Linux:

~~~text
-Xlog:gc*=info:file=/var/log/myapp/gc.log
~~~

Ví dụ trên Windows:

~~~text
-Xlog:gc*=info:file=C:/logs/myapp/gc.log
~~~

Hãy bảo đảm thư mục đích tồn tại và tiến trình Java có quyền ghi. Nếu đường dẫn chứa khoảng trắng, hãy đặt toàn bộ đối số JVM trong dấu nháy phù hợp với shell hoặc script khởi chạy.

### 5.2. Nhiều nhóm log và nhiều output

Có thể cấu hình các nhóm tag khác nhau với đích ghi khác nhau bằng nhiều cấu hình `-Xlog`. Ví dụ:

~~~text
java ^
  -Xlog:gc*=info:file=gc.log:uptime,level,tags:filecount=5,filesize=20M ^
  -Xlog:class+load=info:file=class-load.log:time,level,tags:filecount=3,filesize=10M ^
  -jar app.jar
~~~

Ví dụ dùng ký hiệu nối dòng của Command Prompt Windows (`^`). Trên Linux/macOS, thay bằng dấu `\` ở cuối dòng hoặc viết toàn bộ thành một dòng. Cấu hình đầu ghi GC; cấu hình thứ hai ghi class loading vào file riêng để tránh trộn hai loại sự kiện trong cùng một file.

Khi thêm nhiều cấu hình, hãy xác định rõ tag selector nào ghi vào output nào. Nếu cùng một tag set được cấu hình nhiều lần, kiểm tra cấu hình cuối cùng bằng log thực tế và `jcmd <pid> VM.log list`.

## 6. Decorator: metadata trên mỗi dòng log

Decorator là thông tin được thêm vào dòng log để hỗ trợ phân tích. Cú pháp:

~~~text
-Xlog:gc*:stdout:uptime,level,tags
~~~

Các decorator thường dùng:

| Decorator | Ý nghĩa |
|---|---|
| `time` | Thời gian lịch tại thời điểm ghi log. |
| `utctime` | Thời gian UTC. |
| `uptime` | Thời gian đã trôi qua kể từ lúc JVM khởi động. |
| `timemillis` | Thời gian lịch dưới dạng millisecond. |
| `uptimemillis` | Uptime dưới dạng millisecond. |
| `timenanos` | Thời gian lịch với độ phân giải nano theo định dạng logger. |
| `uptimenanos` | Uptime dưới dạng nanosecond. |
| `pid` | Process ID. |
| `tid` | Thread ID. |
| `level` | Level của thông điệp. |
| `tags` | Tag set gắn với thông điệp. |
| `none` | Không thêm decorator. |

Ví dụ một dòng log có thể có dạng:

~~~text
[2026-11-15T10:30:12.345+0000][12.345s][info][gc] GC(4) Pause Young ...
~~~

Trong ví dụ:

- Timestamp cho biết thời điểm theo đồng hồ hệ thống.
- Uptime giúp so sánh các sự kiện theo thời gian chạy của JVM.
- `info` là level.
- `gc` là tag.

`uptime` thường hữu ích khi đối chiếu nhiều log từ cùng một lần khởi động. `time` hữu ích khi ghép với log ứng dụng hoặc timeline bên ngoài. Có thể chọn nhiều decorator bằng dấu phẩy.

### 6.1. Decorator mặc định

Nếu không chỉ định decorator, Unified Logging dùng bộ decorator mặc định của runtime. Trong các ví dụ vận hành, nên chỉ định rõ `uptime,level,tags` hoặc `time,uptime,level,tags` để định dạng log nhất quán và dễ đọc.

### 6.2. Decorator không thay đổi nội dung sự kiện

Decorator chỉ bổ sung metadata về thông điệp log. Chúng không làm JVM ghi thêm các loại sự kiện khác. Muốn xem heap, class loading hay safepoint, bạn vẫn phải chọn tag tương ứng trong phần `what`.

## 7. Tệp luân phiên: `filecount` và `filesize`

Nếu ghi log liên tục vào một file duy nhất, file có thể tăng dung lượng không giới hạn và làm đầy ổ đĩa. Unified Logging hỗ trợ luân phiên file (*log rotation*) khi output là file.

Hai tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `filesize=<size>` | Ngưỡng kích thước file trước khi thực hiện rotation. |
| `filecount=<count>` | Số file đã luân phiên được giữ lại. |

Ví dụ:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Khi file log đạt ngưỡng 20 MB, JVM luân phiên file theo chính sách cấu hình và giữ số file rotation đã chỉ định. Điều này giúp giới hạn dung lượng log trên đĩa.

### 7.1. Chọn kích thước và số file

Giả sử cấu hình:

~~~text
filecount=5,filesize=20M
~~~

Dung lượng lưu trữ dành cho nhóm log này có thể xấp xỉ sáu file kích thước 20 MB khi tính cả file hiện tại và các file đã luân phiên, ngoài sai khác do thời điểm rotation và metadata filesystem. Hãy dự trù thêm dung lượng cho log khác, file đang được collector đọc và các file được copy ra ngoài.

Chọn giá trị dựa trên:

- Tốc độ phát sinh log mỗi giây.
- Khoảng thời gian cần giữ log để điều tra.
- Dung lượng đĩa có thể dành cho JVM.
- Tần suất thu thập log về hệ thống tập trung.
- Mức log đang bật (`info`, `debug` hay `trace`).

Nếu log được đẩy liên tục về hệ thống tập trung, có thể dùng ít file local hơn. Nếu cần giữ log tại máy chủ để điều tra sự cố sau khi xảy ra, cần đủ số file và kích thước để bao phủ khoảng thời gian mong muốn.

### 7.2. Ví dụ cấu hình log GC có rotation

~~~text
java \
  -Xms2g \
  -Xmx2g \
  -Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=8,filesize=32M \
  -jar app.jar
~~~

Đây là cấu hình phù hợp để bắt đầu thu thập GC log trong môi trường cần giữ nhiều file nhỏ thay vì một file lớn. Hãy tạo thư mục `logs` trước và bảo đảm user chạy JVM có quyền ghi.

### 7.3. Rotation không thay thế chính sách lưu trữ

Rotation giữ dung lượng local trong giới hạn tương đối ổn định, nhưng không phải hệ thống backup hoặc archive. Nếu cần giữ log nhiều ngày/tháng, hãy chuyển log sang hệ thống lưu trữ tập trung hoặc quy trình archive có retention policy riêng.

Không nên để log `trace` ghi vào một file không giới hạn. Khi bật level chi tiết, cần điều chỉnh `filesize`, `filecount` và thời gian thu thập cùng lúc.

## 8. Một số cấu hình thực tế theo mục tiêu chẩn đoán

### 8.1. Theo dõi GC ở mức thông tin

~~~text
-Xlog:gc*=info:stdout:uptime,level,tags
~~~

Dùng khi cần quan sát chu kỳ GC, pause và thông tin liên quan ở mức tổng quát.

### 8.2. Xem chi tiết heap và các phase GC

~~~text
-Xlog:gc+heap=debug,gc+phases=debug:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Dùng khi đang điều tra vì sao pause dài hoặc heap thay đổi bất thường. `debug` có thể tạo nhiều log hơn `info`; hãy bật có thời hạn.

### 8.3. Theo dõi class loading

~~~text
-Xlog:class+load=info,class+unload=info:file=class-lifecycle.log:time,level,tags:filecount=3,filesize=10M
~~~

Cấu hình này hữu ích khi điều tra thời điểm class được nạp/gỡ, class loader hoặc footprint metadata liên quan đến vòng đời class.

### 8.4. Theo dõi safepoint

~~~text
-Xlog:safepoint=info:file=safepoint.log:time,uptime,level,tags:filecount=5,filesize=10M
~~~

Safepoint log có thể giúp phân tích thời gian JVM đưa các thread tới trạng thái an toàn. Nó hữu ích khi thấy pause dài nhưng chưa rõ phần thời gian nằm ở GC work hay thời gian chờ thread tới safepoint.

### 8.5. Kết hợp GC và safepoint

~~~text
-Xlog:gc*=info,safepoint=info:file=jvm-diagnostics.log:time,uptime,level,tags:filecount=6,filesize=25M
~~~

Hai nhóm log cùng ghi vào một file để dễ đối chiếu timeline. Nếu cần tách quyền truy cập, retention hoặc lượng log theo từng nhóm, hãy dùng output riêng.

### 8.6. Điều tra JIT compiler

~~~text
-Xlog:compiler=debug:file=compiler.log:uptime,level,tags:filecount=3,filesize=20M
~~~

Compiler log có thể rất chi tiết. Chỉ bật khi điều tra hành vi JIT, biên dịch method hoặc vấn đề liên quan tới code cache; không cần bật thường trực trong mọi môi trường.

## 9. Khám phá và kiểm tra cấu hình bằng `-Xlog:help`

Khi một selector không tạo log như mong đợi, đừng vội kết luận thành phần JVM không phát sinh sự kiện. Trước hết, kiểm tra cú pháp và khả năng hỗ trợ của runtime:

~~~text
java -Xlog:help
~~~

Đối chiếu:

1. Tag có tồn tại trong runtime không?
2. Tag set có đúng cách ghép bằng dấu `+` không?
3. Selector wildcard có đặt đúng vị trí không?
4. Level có hợp lệ không?
5. Output path có hợp lệ và có quyền ghi không?
6. Decorator có nằm trong danh sách được hỗ trợ không?
7. Output option có được đặt sau phần decorator không?

Có thể kiểm tra phiên bản JVM:

~~~text
java -version
~~~

Điều này quan trọng vì các tag, nội dung log và một số chi tiết triển khai có thể khác nhau giữa vendor hoặc bản cập nhật JDK. Hãy ghi lại chính xác runtime khi tạo runbook chẩn đoán.

## 10. Thay đổi logging khi JVM đang chạy với `jcmd`

Không phải lúc nào cũng có thể khởi động lại ứng dụng chỉ để bật thêm log. HotSpot cung cấp diagnostic command `VM.log`, có thể gọi qua công cụ `jcmd` để liệt kê hoặc thay đổi cấu hình Unified Logging trong JVM đang chạy.

Trước tiên, tìm PID:

~~~text
jcmd -l
~~~

Liệt kê cấu hình logging:

~~~text
jcmd <pid> VM.log list
~~~

Thêm cấu hình log GC ra standard output:

~~~text
jcmd <pid> VM.log output=stdout what="gc*=debug" decorators="uptime,level,tags"
~~~

Thêm cấu hình ghi vào file:

~~~text
jcmd <pid> VM.log output="file=gc-live.log" what="gc*=info" decorators="time,uptime,level,tags" output_options="filecount=5,filesize=20M"
~~~

Cú pháp chi tiết của `VM.log` có thể kiểm tra trên runtime đang chạy:

~~~text
jcmd <pid> help VM.log
~~~

Việc thay đổi cấu hình qua `VM.log` áp dụng cho tiến trình hiện tại; nó không tự cập nhật script hoặc service definition dùng cho lần khởi động tiếp theo. Hãy lưu cấu hình cần duy trì vào cấu hình khởi chạy sau khi đã xác nhận hiệu quả.

### 10.1. Quyền truy cập và môi trường

`jcmd` cần có quyền attach tới tiến trình đích theo cơ chế của hệ điều hành và JVM. Trên một số môi trường container hoặc tài khoản hệ thống, lệnh có thể không nhìn thấy PID hoặc không attach được. Khi đó, kiểm tra user chạy JVM, namespace PID, quyền attach và chính sách vận hành.

Không nên mở rộng quyền hệ thống chỉ để bật log nếu chưa hiểu tác động. Nếu không thể attach, có thể cần cấu hình `-Xlog` ở lần khởi động kế tiếp theo quy trình triển khai.

## 11. Đọc log và liên hệ các sự kiện

Một dòng Unified Logging thường có dạng khái quát:

~~~text
[decorators] message
~~~

Ví dụ:

~~~text
[12.345s][info][gc] GC(7) Pause Young (Normal) (G1 Evacuation Pause) 512M->180M(2G) 18.4ms
~~~

Khi đọc, hãy xác định:

- Uptime hoặc timestamp để đặt sự kiện vào timeline.
- Level để biết mức độ chi tiết.
- Tag set để hiểu subsystem phát ra thông điệp.
- Nội dung message để lấy thông tin cụ thể.

Không nên chỉ grep một từ như `Pause` rồi kết luận nguyên nhân. Hãy ghép các dòng cùng GC ID hoặc cùng khoảng uptime, đặc biệt khi phân tích GC phases, safepoints, class loading và compiler events.

### 11.1. Đối chiếu GC pause với safepoint

GC pause thường yêu cầu stop-the-world. Safepoint log cung cấp thông tin về việc dừng thread và thời gian liên quan đến safepoint. Khi thấy pause dài, có thể đối chiếu:

- Thời gian chuẩn bị/đợi thread tới safepoint.
- Thời gian GC thực hiện công việc.
- Thời gian đưa thread trở lại hoạt động.

Điều này giúp phân biệt pause dài do GC xử lý nhiều dữ liệu với pause dài do thread chậm đi tới safepoint.

### 11.2. Đối chiếu class loading với bộ nhớ

Khi số lượng class tăng nhanh, hãy đối chiếu class loading/unloading với số lượng class loader, metaspace usage và vòng đời ứng dụng. Unified Logging cung cấp sự kiện; các công cụ như JFR, `jcmd` và metrics runtime có thể bổ sung dữ liệu để tìm nguyên nhân.

### 11.3. Tránh kết luận từ log thiếu ngữ cảnh

Log có thể bị cắt do rotation, process restart hoặc collector chưa lấy hết file. Khi phân tích:

- Kiểm tra thời gian và uptime của từng file.
- Xác định file nào là file hiện tại và file nào đã rotate.
- Ghi lại PID để tránh ghép log của hai tiến trình.
- Kiểm tra cấu hình level/tag trong thời gian xảy ra sự cố.
- Đối chiếu với application metrics và request logs.

## 12. Chi phí và lưu ý khi bật log

Unified Logging được thiết kế cho việc quan sát JVM, nhưng ghi log vẫn có chi phí:

- Tạo thêm CPU work để định dạng và ghi thông điệp.
- Tăng I/O và áp lực lên filesystem.
- Tốn dung lượng lưu trữ.
- Có thể ảnh hưởng latency nếu output chậm hoặc phát sinh log quá nhiều.
- Một số log chi tiết có thể làm lộ tên lớp, đường dẫn, cấu trúc runtime hoặc thông tin vận hành.

Khuyến nghị:

1. Bắt đầu từ level `info` và tag hẹp.
2. Chỉ tăng lên `debug`/`trace` khi có giả thuyết điều tra.
3. Dùng rotation cho file output.
4. Đặt quyền truy cập file log phù hợp.
5. Không ghi dữ liệu nhạy cảm vào log ứng dụng hoặc cấu hình chẩn đoán.
6. Tắt hoặc giảm log chi tiết sau khi hoàn thành điều tra.
7. Đo tác động trên môi trường gần với production trước khi giữ cấu hình dài hạn.

Không nên bật `all=trace` trong production như cấu hình mặc định. Nó có thể tạo lượng log rất lớn và làm thay đổi đặc tính hiệu năng mà bạn đang muốn đo.

## 13. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có log mong muốn | Tag set hoặc level không khớp. | Kiểm tra `-Xlog:help`, thử selector hẹp như `gc=info`. |
| Log quá nhiều | Dùng wildcard rộng hoặc level `debug`/`trace`. | Thu hẹp tag set và giảm level. |
| File log không được tạo | Sai đường dẫn, thư mục chưa tồn tại hoặc thiếu quyền ghi. | Kiểm tra path và quyền của user chạy JVM. |
| File log tăng không giới hạn | Chưa cấu hình rotation. | Đặt `filecount` và `filesize`. |
| Không hiểu dòng log thuộc thread nào | Thiếu decorator thread ID. | Thêm `tid` khi cần phân tích đa luồng. |
| Khó ghép log giữa nhiều lần restart | Chỉ dùng uptime mà không có timestamp/PID. | Thêm `time` hoặc `utctime`, `pid` và giữ thông tin phiên chạy. |
| `jcmd VM.log` không attach được | Sai PID, khác user, namespace hoặc attach bị hạn chế. | Kiểm tra quyền và môi trường tiến trình. |
| Selector kết hợp không cho kết quả dự kiến | Nhầm tag đơn với tag set, wildcard hoặc selector overlap. | Kiểm tra tag set và cấu hình hiện hành bằng `VM.log list`. |
| Log bị thiếu đoạn đầu | Rotation, restart hoặc collector chưa thu thập file cũ. | Đối chiếu file đã rotate, PID và uptime. |
| Log gây I/O cao | Bật quá nhiều tag hoặc level quá chi tiết. | Giảm phạm vi và thời gian thu thập, dùng rotation. |

## 14. Bài tập thực hành

### Bài tập 1 — Khám phá tag và level

Chạy `java -Xlog:help`. Ghi lại các tag liên quan tới GC, heap, safepoint và class loading mà runtime đang dùng hỗ trợ. Xác định những level hợp lệ và decorator có sẵn.

### Bài tập 2 — So sánh selector

Chạy cùng một chương trình với:

~~~text
-Xlog:gc=info
-Xlog:gc*=info
-Xlog:gc+heap=debug
~~~

So sánh số lượng và loại thông điệp nhận được. Giải thích khác biệt giữa một tag, wildcard tag set và tag set kết hợp.

### Bài tập 3 — Thay đổi decorator

Chạy với `uptime,level,tags`, sau đó với `time,pid,tid,level,tags`. So sánh khả năng đối chiếu log giữa nhiều tiến trình và giữa log JVM với log ứng dụng.

### Bài tập 4 — Ghi file có rotation

Bật GC logging với `filecount=3,filesize=1M` trong một workload tạo đủ log. Quan sát file hiện tại và các file đã rotate. Giải thích vì sao rotation giúp giới hạn dung lượng local.

### Bài tập 5 — Tách log theo subsystem

Ghi GC log vào `gc.log` và class loading log vào `class-load.log`. Dùng decorator có timestamp và level. Giải thích khi nào nên tách output và khi nào nên gom về một file.

### Bài tập 6 — Điều chỉnh runtime bằng jcmd

Khởi chạy một ứng dụng Java chạy đủ lâu. Dùng `jcmd -l` để tìm PID, `jcmd <pid> VM.log list` để xem cấu hình, sau đó thêm selector GC ở level `debug`. Xác nhận log xuất hiện và kiểm tra cách tắt/điều chỉnh cấu hình bằng `jcmd <pid> help VM.log`.

### Bài tập 7 — Điều tra pause dài

Bật `gc*=info` và `safepoint=info`, chạy workload có allocation cao. Ghép các dòng theo uptime và GC ID. Xác định phần thời gian nằm ở safepoint và phần thời gian GC work nếu log cung cấp đủ dữ liệu.

## 15. Quy trình cấu hình Unified Logging trong dự án

Một quy trình dễ vận hành:

1. **Xác định câu hỏi cần trả lời.** Ví dụ: pause GC dài, class loading bất thường hay safepoint kéo dài.
2. **Chọn tag hẹp.** Dùng `gc`, `gc+heap`, `gc+phases`, `class+load` hoặc `safepoint` theo vấn đề.
3. **Chọn level thấp nhất đủ dùng.** Bắt đầu từ `info`; tăng lên `debug` hoặc `trace` khi cần.
4. **Chọn output.** Console nếu nền tảng thu thập stdout/stderr; file nếu cần lưu tại host.
5. **Chọn decorator.** Thường dùng `time,uptime,level,tags`; thêm `pid`/`tid` khi cần.
6. **Cấu hình rotation.** Đặt `filesize` và `filecount` theo tốc độ log và retention mong muốn.
7. **Kiểm tra bằng runtime thực tế.** Dùng `-Xlog:help`, log thử và `jcmd <pid> VM.log list`.
8. **Theo dõi tác động.** Kiểm tra I/O, CPU, dung lượng và latency.
9. **Điều chỉnh sau điều tra.** Giảm level hoặc tắt tag chi tiết khi không còn cần.
10. **Lưu cấu hình vào runbook/deployment.** Ghi lại JDK version, JVM flags và thời điểm thay đổi để có thể tái hiện.

## 16. Các nguyên tắc cần ghi nhớ

- Unified Logging là cơ chế ghi log thống nhất của HotSpot JVM, dùng cú pháp `-Xlog` trong Java 17.
- `what` chọn tag/tag set và level; `output` chọn stdout, stderr hoặc file; `decorators` thêm metadata; `output-options` điều khiển đích ghi.
- Tag set kết hợp dùng dấu `+`; nhiều selector dùng dấu phẩy; wildcard `*` giúp chọn các tag set liên quan.
- Các level phổ biến là `off`, `error`, `warning`, `info`, `debug`, `trace`; nếu bỏ level, mặc định là `info`.
- `-Xlog:help` hiển thị tag, level, decorator và tùy chọn mà runtime hỗ trợ.
- Decorator như `time`, `uptime`, `pid`, `tid`, `level`, `tags` giúp đặt log vào đúng timeline và tiến trình.
- File output có thể luân phiên bằng `filesize` và `filecount` để giới hạn dung lượng local.
- `jcmd <pid> VM.log` cho phép xem và thay đổi cấu hình trong JVM đang chạy; thay đổi runtime không tự cập nhật cấu hình khởi động.
- Bắt đầu từ tag hẹp và level `info`; chỉ bật `debug`/`trace` khi có mục tiêu điều tra.
- Unified Logging bổ sung cho logging ứng dụng, JFR và metrics; nó không thay thế các công cụ đó.
- Dùng cấu hình hiện hành `-Xlog` trong Java 17; tránh hướng dẫn dựa trên các cờ logging JVM đời cũ.

### Tài liệu tham khảo

- [Oracle Java 17 — The `-Xlog` Option](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java 17 — Unified Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158).
- [JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271).
- [Oracle Java 17 — `jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
