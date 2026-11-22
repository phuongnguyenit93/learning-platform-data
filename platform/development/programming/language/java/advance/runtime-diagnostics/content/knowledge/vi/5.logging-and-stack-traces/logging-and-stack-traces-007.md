# 5.7 Cú pháp -Xlog với tag, level, decorator, file và xoay vòng nhật ký

Khi cần điều tra pause GC, class loading, safepoint, lỗi bộ nhớ hoặc hành vi JVM trong Java 17+, chỉ nhìn log ứng dụng thường không đủ. HotSpot JVM cung cấp **Unified JVM Logging**: cơ chế ghi nhật ký nội bộ được cấu hình bằng tham số khởi động `-Xlog`. Cú pháp này cho phép chọn **nhóm sự kiện (tag)**, **mức độ chi tiết (level)**, **thông tin đi kèm dòng log (decorator)**, **đích xuất (stdout/stderr/file)** và **xoay vòng file (rotation)**.

Ví dụ:

```bash
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Cấu hình trên yêu cầu JVM ghi log có tag set chứa `gc` ở mức `info` trở lên vào file, dùng tên có PID/thời điểm khởi động, thêm thời gian/mức/tag vào dòng và cho phép rotation theo kích thước. Đây là **cú pháp minh họa**: `app.jar` và thư mục `logs` phải thực sự tồn tại, có quyền ghi; GC events phát sinh lúc nào phụ thuộc workload và runtime.

Mục tiêu bài học là **đọc và tự viết được lệnh `-Xlog` đúng ngữ pháp**, hiểu chính xác tag set matching, level, decorator, file và rotation; đồng thời biết cách kiểm chứng khi không thấy log hoặc file tăng không như mong đợi. Bài tập trung vào cấu hình **HotSpot Unified Logging (JDK 17/21)**, không nhầm với logging của ứng dụng qua SLF4J/Logback/Log4j.

## 1. Unified JVM Logging giải quyết việc gì?

Unified Logging là khung logging của JVM, được giới thiệu trong HotSpot từ Java 9 (JEP 158); log về GC và nhiều thành phần runtime sử dụng cùng kiểu chọn tag/level/output. Nó đặc biệt hữu ích để:

- Theo dõi GC start/end, cause, pause, heap occupancy và các thành phần collector tùy tag.
- Đối chiếu class loading/unloading khi nghi ngờ leak class loader hoặc khởi động chậm.
- Quan sát safepoint, container/OS, code cache hay compilation trong phạm vi các tag mà JVM hỗ trợ.
- Tạo các dòng log có timestamp/uptime/PID để tương quan với metrics, ứng dụng và hệ điều hành.
- Ghi dữ liệu chẩn đoán thành file có rotation, tránh một file tăng vô hạn trong nhiều trường hợp.

**Không phải mọi sự kiện Java đều đi qua `-Xlog`.** Lệnh `System.out.println`, stack trace do ứng dụng in ra, log từ SLF4J/Logback/Log4j, web access log và tracing đều có cơ chế cấu hình riêng. `-Xlog:gc` không tự bật DEBUG log của Spring hoặc thay đổi log4j configuration.

Nên coi `-Xlog` là một **nguồn bằng chứng runtime**, đặt cạnh application logs, metrics, JFR và thông tin OS/container. Nó không tự kết luận nguyên nhân sự cố nếu thiếu điều kiện tải/thời gian/JVM flags.

### 1.1 Cách xem JVM hiện tại thực sự hỗ trợ gì

Trước khi áp dụng một cấu hình:

```bash
java -version
java -Xlog:help
```

`java -Xlog:help` in hướng dẫn cú pháp, tag/level/decorator có sẵn và ví dụ theo **JVM được lệnh `java` này khởi chạy**. Kiểm tra phiên bản thực của service: terminal có thể dùng JDK khác. Danh sách tag và những tổ hợp tag có thể khác giữa JDK release, collector và implementation. Một tag có tên hợp lệ **không đảm bảo** mọi tổ hợp với tag đó sẽ phát ra sự kiện thực tế.

Một quy tắc an toàn khi học: **lấy `-Xlog:help` từ đúng JDK release và kiểm tra bằng workload nhỏ**, thay vì sao chép mù một option của JDK mới lên một JVM cũ.

## 2. Cấu trúc tổng quát của -Xlog

Theo tài liệu Java launcher, dạng chung là:

```text
-Xlog[:[what][:[output][:[decorators][:output-options]]]]
-Xlog:help
-Xlog:disable
-Xlog:async
```

Trong đó:

| Vị trí | Tên | Nội dung | Ví dụ |
| --- | --- | --- | --- |
| Sau `-Xlog:` | `what` | Tag/tag set, wildcard, level; nhiều selector cách nhau bằng dấu phẩy | `gc*=debug,safepoint=info` |
| Sau dấu `:` thứ hai | `output` | `stdout`, `stderr` hoặc `file=...` | `file=logs/gc.log` |
| Sau dấu `:` thứ ba | `decorators` | Những nhãn gắn trước message | `time,uptime,level,tags,pid` |
| Sau dấu `:` thứ tư | `output-options` | Các thiết lập output, nhất là file rotation | `filecount=5,filesize=10M` |
| Trực tiếp sau `-Xlog:` | directive | Lệnh/điều chỉnh toàn cục như `help`, `disable`, `async` | `-Xlog:help` |

**Dấu hai chấm phân tách *vị trí*, dấu phẩy phân tách *danh sách trong một vị trí*.** Dấu `+` nối nhiều tag thuộc **cùng tag set**. Dấu `*` ở cuối tag selector là wildcard matching. Dấu `=` chọn level. Các ký hiệu có vai trò khác nhau, không thể hoán đổi.

Phân tích mẫu:

```text
-Xlog:gc*=debug:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=10M
      |         |                       |                      |
      what      output                  decorators             output-options
```

- `what = gc*=debug`: nhận các tag set **chứa** `gc`, từ debug tới các mức quan trọng hơn (info, warning, error).
- `output = file=...`: ghi tới file, tên có hai placeholder của JVM.
- `decorators = time,uptime,level,tags`: hiển thị thời gian lịch, thời gian JVM chạy, mức, tag set.
- `output-options = filecount=5,filesize=10M`: xoay vòng file khoảng mức kích thước 10 MB, dùng số file theo cấu hình.

**Cảnh báo:** nếu bỏ qua `output` nhưng vẫn muốn chỉ định decorator, phải giữ vị trí trống bằng hai dấu `:` liên tiếp. Ví dụ `-Xlog:gc::uptime,tid`: output vẫn là stdout, decorator là `uptime,tid`. Đừng biến `-Xlog:gc:uptime,tid` thành lệnh “tương đương”: lúc đó JVM sẽ diễn giải `uptime,tid` ở vị trí **output**.

### 2.1 Các cách viết ngắn hợp lệ

```bash
java -Xlog -version
java -Xlog:gc -version
java "-Xlog:gc=debug:stdout:uptime,level,tags" -version
java "-Xlog:gc=debug:file=gc.log:none" -version
java "-Xlog:gc::uptime,tid" -version
```

Các lệnh ở đây dùng `-version` để **kiểm tra parser/cấu hình** chứ không phải benchmark; do JVM có thể không thực hiện GC đáng quan sát trong tiến trình ngắn, **không có dòng GC log không chứng minh cấu hình sai**. Tùy JVM, log startup hoặc lời cảnh báo vẫn có thể xuất hiện.

## 3. Chọn tag: gc, gc*, gc+heap và các tổ hợp

### 3.1 Tag là phân loại của một bản tin runtime

Mỗi bản tin Unified Logging có một **tag set** (một hoặc nhiều tag) và một level. Các tag thường gặp khi làm runtime diagnostics gồm `gc`, `safepoint`, `class`, `load`, `unload`, `os`, `container`, `compiler`, `codecache`; danh sách thực được in bởi `-Xlog:help`.

Điều quan trọng: **selector không wildcard khớp chính xác tag set**, không phải “có chứa chuỗi” hay “chứa tag nào cũng được”.

| Selector | Ý nghĩa | Không tương đương với |
| --- | --- | --- |
| `gc` | Chọn bản tin có tag set **chính xác** là `gc` | Mọi log liên quan GC |
| `gc*` | Chọn mọi tag set **có chứa `gc`**, kể cả `gc+heap` | Chỉ mỗi tag set `gc` |
| `gc+heap` | Chọn chính xác tập tag gồm `gc` và `heap` | Mọi tag set có chứa hai tag đó |
| `gc+heap*` | Chọn tag set **ít nhất chứa** `gc` và `heap` | Mọi tag set chỉ chứa một trong hai |
| `gc,safepoint` | Hai selector độc lập: khớp chính xác `gc` **hoặc** chính xác `safepoint` | Tập tag `gc+safepoint` |
| `gc+safepoint` | Một selector cho tập tag gồm **cả** `gc` và `safepoint` | Hai dòng selector ngăn bằng dấu phẩy |
| `all` | Meta-tag chọn mọi tag set | Chỉ `gc` hoặc các tag bạn nêu |

Ví dụ:

```bash
java "-Xlog:gc=info" -jar app.jar
java "-Xlog:gc*=info" -jar app.jar
java "-Xlog:gc+heap=debug" -jar app.jar
java "-Xlog:gc+heap*=debug" -jar app.jar
java "-Xlog:gc=info,safepoint=debug" -jar app.jar
```

Tất cả ví dụ đều đòi hỏi `app.jar` hợp lệ. Nếu mục tiêu là **GC details**, `gc*` thường phù hợp hơn `gc` vì phần log chi tiết có thể mang nhiều tag. Tuy nhiên phạm vi rộng hơn cũng làm tăng số dòng và overhead; nên bắt đầu ở `info` và nâng độ chi tiết khi có giả thuyết cụ thể.

### 3.2 Cách đọc dấu +, dấu phẩy và wildcard

Giả sử JVM có các log event minh họa mang tag sets:

```text
[gc]
[gc,heap]
[gc,ergo]
[safepoint]
[gc,heap,region]
```

- `gc` chỉ khớp sự kiện đầu (tag set chính xác).
- `gc*` khớp các sự kiện có `gc`: đầu, hai, ba và năm.
- `gc+heap` chỉ khớp sự kiện hai.
- `gc+heap*` khớp sự kiện hai và năm.
- `gc,safepoint` chỉ khớp event đầu và event bốn.
- `gc*,safepoint` khớp mọi event ở danh sách này nếu event năm có tag gc.

Các tag set trên chỉ là **mô hình giải thích matching**, không phải khẳng định JVM nào chắc chắn phát đủ năm loại sự kiện. Tag thực được mô tả trong output `-Xlog:help` và phụ thuộc implementation.

### 3.3 Cách chọn từ hẹp đến rộng

Khi mới điều tra:

1. Bắt đầu với `-Xlog:gc=info` nếu cần GC summary cơ bản.
2. Dùng `-Xlog:gc*=info` nếu muốn cả các nhóm tag phối hợp chứa GC.
3. Nâng `gc+heap=debug` hoặc `gc+ergo*=debug` cho giả thuyết heap/ergonomics, **sau khi kiểm tra tag có hỗ trợ**.
4. Đặt time window đủ ngắn và rotation phù hợp nếu bật DEBUG/TRACE.
5. Không dùng `all=trace` kéo dài trên production khi chưa đánh giá lưu lượng log và overhead.

## 4. Chọn level: độ chi tiết và ngưỡng

JDK HotSpot Unified Logging hỗ trợ các level:

| Level | Ý nghĩa sử dụng | Độ chi tiết tương đối |
| --- | --- | --- |
| `off` | Tắt logging cho selection cụ thể | Không xuất bản tin được chọn |
| `error` | Những bản tin lỗi | Ít nhất |
| `warning` | Warning và error | Ít |
| `info` | Thông tin phổ biến và hai mức nghiêm trọng hơn | Trung bình |
| `debug` | Chi tiết hơn info | Nhiều hơn |
| `trace` | Rất chi tiết, thường dùng điều tra sâu | Nhiều nhất |

**Level được hiểu như ngưỡng**, không phải “chỉ đúng một level”. Chẳng hạn `gc=debug` cho phép debug cùng info/warning/error của tag set được chọn; `gc=warning` không phát các dòng info/debug/trace của tag set đó. `off` là mức đặc biệt để tắt, không phải một mức “ít hơn error nhưng vẫn in ra”.

Ví dụ:

```bash
java "-Xlog:gc=info" -jar app.jar
java "-Xlog:gc*=debug" -jar app.jar
java "-Xlog:gc+heap=trace" -jar app.jar
java "-Xlog:gc*=info,safepoint*=off" -jar app.jar
```

Ở cấu hình cuối, selector `safepoint*=off` chặn những log thuộc nhóm tag safepoint (kể cả tổ hợp có tag này) trong phạm vi áp dụng, dù selector `gc*` có thể khớp một số tag set chồng lấn. Oracle dùng ví dụ tương tự để minh họa khả năng tắt một nhóm tag. Khi có selector chồng lấn, tránh đoán thứ tự ưu tiên chung từ biểu thức; kiểm tra output và cách JVM áp dụng selection thực tế.

### 4.1 Không có dòng không tự chứng minh option sai

Một tag/level có thể không có event nào trong khoảng thời gian quan sát. Ví dụ:

- `gc=debug`: app chạy vài mili giây, không có GC event.
- `class+load=info`: ứng dụng đã load class từ trước khi bật logging động, nên không có log cho những lần load đã qua.
- `safepoint=info`: không có sự kiện cần báo ở khoảng bạn xem.
- `gc+heap=trace`: workload/collector không phát thông điệp ở tag set exact này trong lần chạy.

Cần kiểm tra **cú pháp, tag selection, level, output path và thời gian** trước khi suy từ sự vắng mặt của event đến kết luận JVM “không có GC”.

## 5. Chọn output: stdout, stderr và file

`-Xlog` cho phép:

```text
stdout
stderr
file=<filename>
```

Khi không ghi output, mặc định là **stdout**. Ví dụ:

```bash
java "-Xlog:gc=info:stdout" -jar app.jar
java "-Xlog:gc=info:stderr" -jar app.jar
java "-Xlog:gc*=info:file=logs/gc.log" -jar app.jar
```

### 5.1 Khi nào dùng stdout/stderr?

Trong hệ thống container, stdout/stderr thường được thu bởi container runtime và log collector. Cách này hợp lý nếu nền tảng đã có rotation/retention riêng. Tuy nhiên cần kiểm tra thật:

- Collector có phân biệt stderr và stdout không?
- Có giới hạn tốc độ hoặc số dòng bị drop không?
- Timestamp do collector thêm có trùng hoặc lệch với decorator của JVM không?
- Log ứng dụng và JVM trộn cùng stream thì có cách nhận diện bằng `[gc]`, `[info]`, PID/instance không?
- Collector/driver có thực hiện rotation hay phải cấu hình riêng?

**Không đặt filecount/filesize cho stdout rồi kỳ vọng JVM tự rotate stream**. Rotation trong `-Xlog` áp dụng cho **file outputs**, không thay thế cơ chế quản lý log của container.

### 5.2 Khi nào dùng file?

File riêng có lợi khi cần giữ log GC để đối chiếu với JFR/metrics hoặc tránh trộn với application stdout:

```bash
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:time,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Các điểm phải kiểm tra trước khi chạy production:

- Thư mục `logs/` đã tồn tại và user chạy JVM có quyền tạo/ghi file.
- Đường dẫn tương đối được giải từ **working directory** của process, không nhất thiết là thư mục chứa JAR.
- File nằm trên filesystem/container volume nào; pod restart có làm mất log không; log collector có đọc đường dẫn này không?
- Disk quota, inode, retention và cấu hình backup có phù hợp không?
- Một launcher/service manager có đặt khác `user.dir` hay startup environment?
- File có chứa thông tin nhạy cảm và được bảo vệ đúng quyền không?

Nếu JVM không mở được file output lúc startup, bản thân cấu hình logging có thể gây lỗi khởi động; kiểm tra stderr, exit code và quyền ghi trong **môi trường thử nghiệm trước**.

### 5.3 Placeholder %p và %t trong tên file

Theo tài liệu `java`, tên file dùng `file=...` có thể có:

| Placeholder | Ý nghĩa | Công dụng |
| --- | --- | --- |
| `%p` | PID của JVM | Giúp phân biệt các JVM được cấu hình cùng pattern |
| `%t` | Timestamp khi JVM khởi động | Giúp phân biệt nhiều lần restart |
| `gc-%p-%t.log` | Ví dụ kết hợp | Giảm nguy cơ file cũ và mới dùng chung tên |

Ví dụ file được tạo có thể như `gc-4242-2026-10-29_08-00-00.log`, nhưng **định dạng timestamp và giá trị PID thực phụ thuộc JVM/môi trường**; đây không phải cam kết tên file chuẩn từng ký tự. Không tạo script quan trọng bằng cách tự đoán cấu trúc đầy đủ của `%t` nếu chưa kiểm tra file thực.

**Lưu ý:** PID có thể trùng lại theo thời gian và một container mới có thể có PID 1, nên `%p` **một mình** không đảm bảo tên file duy nhất qua mọi lần khởi động. `%t` giúp giảm trùng, nhưng vẫn cần kiểm tra chính sách lưu trữ và việc JVM xử lý tên file đã tồn tại.

## 6. Decorator: gắn bối cảnh cho từng dòng

**Decorator** là metadata JVM đặt trước phần message, có thể gồm mốc thời gian, độ dài uptime, level, tag set, PID, thread ID và host. Nếu không chỉ định, mặc định là `uptime,level,tags`.

Một log **giả định**:

```text
[2.345s][info][gc] GC(1) Pause Young (Normal) ... 4.120ms
```

Dấu `...` trong dòng minh họa là phần message giả định được lược bớt, **không phải output từ một lần chạy đã xác minh**. Khi dùng default, cấu trúc đầu dòng giúp biết event xảy ra khi JVM chạy được bao lâu, severity và tag set.

### 6.1 Những decorator có ích

| Decorator | Ý nghĩa | Điểm cần chú ý |
| --- | --- | --- |
| `time` / `t` | Thời điểm lịch, dạng ISO-8601 | Có ích khi ghép với log ứng dụng/OS; chú ý timezone |
| `utctime` / `utc` | Thời gian UTC | Ưu tiên để đối chiếu hệ thống ở nhiều timezone |
| `uptime` / `u` | Thời gian từ lúc JVM start | Không phải timestamp UTC; rất có ích phân biệt startup/steady state |
| `uptimemillis` / `um` | Uptime theo milliseconds | Dễ ghép sự kiện trong một JVM |
| `uptimenanos` / `un` | Uptime theo nanoseconds | Độ phân giải cao nhưng không phải mọi event có độ chính xác tương đương |
| `timemillis` / `tm` | Giá trị thời gian tương ứng `System.currentTimeMillis()` | Wall-clock có thể thay đổi do đồng bộ thời gian |
| `timenanos` / `tn` | Giá trị tương ứng `System.nanoTime()` | Không diễn giải như thời điểm lịch |
| `pid` / `p` | PID JVM | PID phải đặt trong ngữ cảnh host/namespace |
| `tid` / `ti` | Thread ID liên quan | Không tự chuyển sang Java Thread ID hay correlate nếu chưa biết ý nghĩa trên JVM |
| `level` / `l` | Level của message | Có thể lọc/đối chiếu với cấu hình |
| `tags` / `tg` | Danh sách tag của message | Hữu ích kiểm tra `gc` hay `gc+heap` thực sự khớp |
| `hostname` / `hn` | Hostname được JVM biết | Có thể là thông tin nội bộ nhạy cảm |
| `none` | Bỏ toàn bộ decorators | Khó phân tích thời gian/nguồn nếu hệ thống không thêm metadata ở nơi khác |

Ví dụ:

```bash
java "-Xlog:gc*=info:stdout:utctime,uptime,level,tags,pid" -jar app.jar
java "-Xlog:gc=debug:file=logs/gc.log:none:filecount=3,filesize=5M" -jar app.jar
java "-Xlog:gc::uptime,tid" -jar app.jar
```

**Decorator được chọn trong cùng một trường**, ngăn bằng dấu phẩy. Thứ tự hiển thị thực tế là thứ tự framework định nghĩa, không nhất thiết theo đúng chuỗi bạn gõ.

### 6.2 Chọn decorator theo nhu cầu điều tra

- Nếu chỉ đọc GC events của **một JVM**: `uptime,level,tags` có thể đủ.
- Nếu ghép events nhiều process/host: cân nhắc `utctime,uptime,pid,level,tags`; collector cần gắn thêm container/service identity vì PID có thể lặp giữa containers.
- Nếu nghi thread-specific events: thêm `tid` nhưng đừng gán nhầm với Java thread ID nếu công cụ khác có định danh khác.
- Nếu dùng parser/dashboard: thống nhất bộ decorator qua các instance và giữ cả timezone/units.
- Nếu lưu log ra môi trường ngoài: cân nhắc không in `hostname` hoặc thông tin hạ tầng riêng khi không cần.

Một số log collectors tự thêm timestamp; không vì thế mà luôn bỏ timestamp JVM. Hai timestamp phục vụ mục đích khác nhau: **thời điểm JVM phát event** và **thời điểm collector nhận được** có thể chênh lệch do buffering/delay.

## 7. Rotation: filecount và filesize

Không thể lưu `-Xlog:gc*=trace` vào một file tăng mãi trên dịch vụ chạy lâu mà không kiểm soát dung lượng. Unified Logging có cơ chế **xoay vòng log theo kích thước** cho file output.

Cấu hình:

```bash
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Ý nghĩa:

- `filesize=10M`: ngưỡng kích thước mục tiêu mỗi file là khoảng 10 MB. Đây là **ngưỡng gần đúng**, không bảo đảm mỗi file đúng từng byte vì kích thước từng log event và cơ chế ghi.
- `filecount=5`: cấu hình số file tham gia vòng xoay/giữ lại theo cơ chế HotSpot. Xoay vòng có thể ghi đè file cũ; không phải chính sách lưu giữ theo số ngày.
- Sau khi chạm ngưỡng, JVM xoay sang file tiếp theo trong bộ và có thể tái sử dụng file cũ. Cách đặt tên file xoay thực tế nên xem trên chính JDK để xây collector cho phù hợp.
- `M` là hậu tố độ lớn cho `filesize`; cú pháp cũng hỗ trợ `K`/`G`. Không tự thay thành “MB” hoặc dùng đơn vị không được parser hỗ trợ.

### 7.1 Trường hợp filecount=0

```bash
java "-Xlog:gc*=info:file=logs/gc.log:uptime,level,tags:filecount=0" -jar app.jar
```

Theo tài liệu JDK, **`filecount=0` nghĩa là không xoay vòng**. Đừng hiểu nó là giữ 0 file hoặc tắt ghi log. Nếu logging hoạt động liên tục, file có thể tăng dài và gây áp lực disk; chỉ dùng khi hệ thống có cơ chế khác kiểm soát dung lượng hoặc workload ngắn.

### 7.2 Giá trị mặc định không đồng nghĩa luôn phù hợp

Theo man page của JDK 21, file rotation mặc định có tới **5 file xoay** với target size **20 MB**, trừ khi ghi đè cấu hình. Mặc định là thông tin về release được tài liệu hóa, không phải quy tắc mãi mãi cho mọi JVM. Đối với production, nên **ghi tường minh `filecount` và `filesize`** trong startup configuration để dễ kiểm soát và audit.

Không nên tính disk budget bằng `5 × 10 MB` như một upper bound chặt chẽ: file active/rotated files, event size, overhead, nhiều JVM, các lần restart và các file cũ còn tồn tại đều có thể làm tổng dung lượng thực tế khác. Nếu quay vòng trên container ephemeral storage, cần kiểm tra node/pod quotas và chính sách ship log.

### 7.3 Rotation không thay thế log retention

Rotation theo size **không tự** giải quyết:

- Giữ log theo số ngày/tháng hoặc yêu cầu pháp lý.
- Xóa log khi file không còn thuộc bộ xoay của process đã kết thúc.
- Backup, mã hóa, RBAC hoặc hạn chế người đọc.
- Log từ nhiều containers/replicas hoặc metadata thu thập ngoài JVM.
- Kết nối với tập trung log và ngăn upload nhiều bản sao.
- Ổ đĩa đầy vì file khác/trace khác hoặc log collector mất kết nối.

Với service JVM chạy lâu, nên phối hợp `-Xlog` rotation, giám sát disk, collector và retention policy. Tránh dùng **hai cơ chế rotate độc lập** trên cùng file nếu không hiểu cách ứng dụng và collector giữ file descriptor: rename/copytruncate ngoài JVM có thể làm mất hoặc trùng log.

### 7.4 File trùng tên, restart và quyền ghi

Khi JVM khởi động lại với cùng `file=logs/gc.log`, file đã tồn tại **có khả năng bị ghi đè** theo tài liệu. Dùng `%p` và `%t` giúp giảm rủi ro, nhưng vẫn phải có retention/cleanup cho log cũ. Nếu chạy nhiều replica cùng mount dùng chung, cần tên và thư mục đủ phân biệt instance; không đòi filecount của mỗi JVM quản lý được file của mọi replica.

## 8. Bài thực hành Java 17+ độc lập

Để học cú pháp, nên có một chương trình chạy được, stdout rõ ràng và không hứa luôn phát cùng lượng GC log. Ví dụ dùng mảng nhỏ và một lệnh gợi ý GC; việc JVM có phát event hay không vẫn phụ thuộc collector và runtime.

Lưu file `UnifiedXlogDemo.java`:

```java
public class UnifiedXlogDemo {
    private static volatile Object lastAllocation;

    public static void main(String[] args) {
        System.out.println("APPLICATION_START");

        for (int i = 0; i < 64; i++) {
            lastAllocation = new byte[64 * 1024];
        }

        // Chỉ là đề nghị JVM GC, không bảo đảm phát một GC event cụ thể.
        System.gc();

        System.out.println("APPLICATION_END");
    }
}
```

Biên dịch:

```bash
javac UnifiedXlogDemo.java
```

### 8.1 Bật GC log ra stdout

```bash
java "-Xlog:gc=info:stdout:uptime,level,tags" UnifiedXlogDemo
```

Hai dòng **do chương trình Java in ra** luôn theo thứ tự:

```text
APPLICATION_START
APPLICATION_END
```

JVM có thể in thêm Unified Logging messages trước, giữa hoặc sau hai dòng này, tùy collector, startup, tùy chọn `System.gc()` và môi trường. Vì vậy **không thể cam kết stdout tổng cộng chỉ gồm hai dòng trên**. Lệnh `System.gc()` có thể bị bỏ qua hoặc không dẫn đến cùng event trên mọi JVM; không dùng output GC giả làm kết quả chắc chắn.

### 8.2 Ghi vào file có PID, startup time và rotation

Trước tiên tạo thư mục `logs` có quyền ghi trong working directory. Ví dụ shell Unix/Linux:

```bash
mkdir -p logs
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=3,filesize=1M" UnifiedXlogDemo
```

Hoặc PowerShell:

```powershell
New-Item -ItemType Directory -Force logs
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=3,filesize=1M" UnifiedXlogDemo
```

Trong trường hợp công cụ chạy thành công, stdout của code ứng dụng gồm:

```text
APPLICATION_START
APPLICATION_END
```

Các dòng JVM khớp selector sẽ đi vào file cấu hình thay vì trộn vào stdout theo output này. JVM vẫn có thể in cảnh báo hoặc thông tin khác ra console theo cấu hình logging còn lại. Số file và lượng log là **không xác định cố định** từ đoạn code này: vài MiB allocated và `System.gc()` không bảo đảm vượt ngưỡng `filesize=1M`. **Không kỳ vọng file rotation xảy ra** trong lần chạy ngắn. Muốn kiểm thử xoay vòng thật, cần workload có lượng log đủ lớn trên môi trường thử nghiệm, đồng thời quan sát file disk và chi phí logging.

### 8.3 Giải thích đầy đủ lệnh ví dụ

```text
-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=3,filesize=1M
      └ what  ┘  └────── output ───────┘ └────── decorators ─────┘ └─ options ────┘
```

- `gc*=info`: mọi tag set có chứa `gc` ở mức info hoặc nghiêm trọng hơn.
- `file=...`: hướng các message được chọn vào file trong `logs`; `%p` và `%t` giúp nhận diện lần khởi động.
- `utctime,uptime,level,tags`: giúp ghép event với thời gian UTC và giai đoạn đời JVM.
- `filecount=3,filesize=1M`: giới hạn số file xoay và cỡ gần đúng theo cấu hình.
- `UnifiedXlogDemo`: main class đã được `javac` biên dịch; không phải tên JAR.
- Thay `UnifiedXlogDemo` bằng `-jar app.jar` chỉ khi `app.jar` thực sự có manifest main class và chạy được.

### 8.4 Kiểm chứng kết quả sau chạy

- Kiểm tra lệnh Java chạy thành công và có hai dòng của ứng dụng.
- Kiểm tra file có được tạo không, tên thực có PID/thời gian phù hợp không.
- Đọc một số dòng xem decorator đã chứa UTC/uptime/level/tags chưa.
- Nếu không có GC event, kiểm tra tag/level và thời lượng workload; không cho rằng logging sai ngay.
- Với thử nghiệm rotation, tăng tải phát event **có kiểm soát trong môi trường thử**, quan sát thay đổi file/dung lượng; không cố gây áp lực heap trên production chỉ để thấy rotation.
- Ghi Java vendor/version và command line **đã loại secret**, vì cú pháp/tags có thể khác giữa phiên bản.

## 9. Cấu hình thường dùng trong Java runtime diagnostics

### 9.1 GC summary nhẹ để theo dõi thường xuyên

```bash
java "-Xlog:gc=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Ưu tiên log summary nếu câu hỏi chỉ là GC frequency, pause thời gian hoặc collector behavior chung. Nếu muốn lấy nhiều GC subtag hơn, đổi `gc` thành `gc*` và đánh giá lượng phát sinh.

### 9.2 GC detail tạm thời khi nghi heap/ergonomics

```bash
java "-Xlog:gc*=debug:file=logs/gc-debug-%p-%t.log:utctime,uptime,level,tags,pid:filecount=5,filesize=20M" -jar app.jar
```

Dùng debug trong cửa sổ đo có giới hạn, lưu cả workload/phiên bản JVM/heap flags. Debug nhiều hơn **không mặc nhiên tốt hơn**: file lớn, CPU/I/O overhead và dữ liệu nội bộ xuất hiện nhiều hơn. Không bật trace toàn bộ GC trên production chỉ vì p99 có spike chưa xác định.

### 9.3 Safepoint và GC trong cùng output

```bash
java "-Xlog:gc*=info,safepoint=info:file=logs/jvm-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Vì `gc*` là wildcard, nhóm GC được chọn rộng; `safepoint=info` chọn **chính xác** tag set `safepoint` ở mức info. Nếu cần các subtag safepoint, dùng `safepoint*` sau khi kiểm tra JDK hỗ trợ. Chỉ từ timestamp safepoint và GC **chưa đủ** để quy mọi độ trễ request cho GC; cần cùng cửa sổ và application metrics.

### 9.4 Class loading/unloading

```bash
java "-Xlog:class+load=info,class+unload=info:stdout:utctime,level,tags" -jar app.jar
```

Dùng khi muốn quan sát class loading hoặc unload, nhưng tần suất có thể cao, nhất là giai đoạn startup. Không dùng output này như danh sách đầy đủ “mọi class từng tồn tại” nếu logging mới bật sau đó hoặc nhiều event bị bỏ sót từ collector.

### 9.5 Container/cgroup diagnostic

```bash
java "-Xlog:os+container=debug:stdout:uptime,level,tags" -jar app.jar
```

Useful khi kiểm tra JVM nhìn giới hạn container như thế nào trên môi trường Linux có container support phù hợp. Một số môi trường không phát log hoặc không có cùng tag/level; `-Xlog:help` và version target là nguồn kiểm chứng. **Không nhầm mức CPU quota container với mức CPU của toàn host** khi đối chiếu log.

### 9.6 Tắt một nhóm log hoặc bỏ decorator

```bash
java "-Xlog:gc*=info,safepoint*=off:stdout:uptime,level,tags" -jar app.jar
java "-Xlog:gc=debug:file=logs/gc-simple.log:none:filecount=2,filesize=5M" -jar app.jar
```

Lệnh thứ nhất loại các sự kiện có tag set chứa safepoint khỏi selection mong muốn; lệnh thứ hai bỏ decorators, chỉ thích hợp khi bối cảnh time/level đã có nguồn khác đáng tin. Với log chẩn đoán cần ghép thời gian, `none` thường làm mất khả năng tương quan.

## 10. Tương tác với mặc định và nhiều -Xlog options

### 10.1 Mặc định của JVM

Không cấu hình thêm `-Xlog`, JDK 21 giữ logging mặc định cho message level `warning` và `error` trên stdout với `uptime,level,tags` (cách diễn đạt tương đương `-Xlog:all=warning:stdout:uptime,level,tags`). Vì vậy:

- `-Xlog:gc=info` bật thêm thông tin nhóm `gc` nhưng **không phải** “chỉ in GC và tuyệt đối bỏ mọi warning/error khác”.
- `-Xlog:help` chỉ in help rồi thoát, không chạy ứng dụng.
- `-Xlog:disable` xóa toàn bộ cấu hình logging hiện tại, **kể cả warning/error mặc định**. Đây là lựa chọn mạnh, chỉ dùng khi thật sự có yêu cầu chẩn đoán đặc biệt và hiểu hậu quả mất log.
- `-Xlog` không có phần selection bật logging mặc định theo semantics được tài liệu mô tả, không phải tương đương `-Xlog:gc`.

### 10.2 Nhiều -Xlog trên cùng dòng lệnh

Java launcher xử lý nhiều option `-Xlog` theo thứ tự; theo tài liệu, cấu hình có cùng output có thể **ghi đè nhau** theo thứ tự xuất hiện. Vì thế không viết:

```bash
java "-Xlog:gc=info:file=logs/jvm.log" "-Xlog:safepoint=debug:file=logs/jvm.log" -jar app.jar
```

rồi **mặc định** cả hai selection cùng được cộng dồn vào một output. Nếu muốn hai nhóm tag cùng đích, viết rõ trong **một selection**:

```bash
java "-Xlog:gc=info,safepoint=debug:file=logs/jvm-%p-%t.log:utctime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Nếu muốn hai file log riêng, dùng hai outputs khác tên, và kiểm tra configuration cuối; nhớ rằng warnings của JVM có thể còn gửi stdout theo mặc định. Cũng cân nhắc option được thêm bởi `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, script launcher hay container entrypoint làm thay đổi cấu hình thực tế.

### 10.3 Logging động bằng jcmd VM.log

Trong nhiều bản HotSpot hiện đại, `jcmd PID VM.log` cho phép **liệt kê hoặc thay đổi cấu hình Unified Logging của JVM đang chạy**, nếu có quyền attach và command được hỗ trợ.

Bắt đầu bằng thao tác đọc:

```bash
jcmd 4242 help VM.log
jcmd 4242 VM.log list
```

`4242` chỉ là PID minh họa. Hãy xác minh PID/instance và quyền; `jcmd -l` có giới hạn khi JVM nằm trong Docker process riêng. `VM.log` có thể cấu hình `what`, `output`, `decorators`, `output_options` hoặc yêu cầu rotate. Thay đổi qua diagnostic command tác động tới **JVM đang chạy**; không coi đó là sửa startup config bền vững qua restart.

Nếu cần bật debug tạm thời trên production, phải theo quy trình vận hành: ghi trạng thái ban đầu, đặt thời hạn quan sát, đánh giá overhead/log volume, biết cách **khôi phục** cấu hình và kiểm tra lại. Không tự chạy lệnh đổi logging của PID không được xác minh hoặc nhắm hàng loạt JVM.

## 11. Những lỗi cú pháp và vận hành hay gặp

| Vấn đề | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `-Xlog:gc` không có heap details | Exact tag set `gc` không khớp `gc+heap` | Dùng `gc*` hoặc chọn `gc+heap` đúng phạm vi |
| Viết `gc+heap` mà muốn hai nhóm riêng | `+` là AND trong một tag set, không phải OR | Dùng `gc,heap` chỉ khi muốn exact tag sets độc lập |
| Quên dấu `:` khi bỏ output | JVM hiểu decorators là output | Dùng `-Xlog:gc::uptime,tid` |
| Không thấy GC log trong app ngắn | Không có event/không cùng tag/level | Kiểm tra workload, `-Xlog:help`, output |
| Dùng `debug` nhưng rất ít log | Selector exact hoặc ít event | Kiểm tra tag set thật, thử wildcard có kiểm soát |
| Viết `filesize=10MB` | Suffix có thể không hợp lệ | Dùng `filesize=10M` theo `-Xlog:help` |
| Đặt `filecount` cho stdout | Rotation thuộc file output | Dùng `file=...` hoặc nền tảng quản lý stdout |
| `filecount=0` vẫn tăng file | Giá trị 0 nghĩa là không rotate | Dùng filecount dương/retention chính sách |
| JVM không tạo file | Thư mục chưa tồn tại, thiếu quyền, sai working dir hoặc startup lỗi | Kiểm tra stderr/exit status và filesystem |
| File bị ghi đè sau restart | Cùng tên output không duy nhất | Dùng `%p`, `%t` và chính sách lưu file |
| Đã đặt time nhưng không thấy đúng thứ tự trong dòng | Framework có thứ tự decorator định sẵn | Kiểm tra file thực và parser, không suy từ thứ tự cấu hình |
| Hai `-Xlog` cùng file không cộng dồn như nghĩ | Option sau có thể override output trước | Gộp selectors trong một option |
| Log bị trộn với app stdout | Cùng output stream | Dùng file riêng hoặc parser/metadata xác định nguồn |
| Disk đầy dù có rotation | Nhiều JVM/file cũ, các nguồn log khác hoặc quota nhỏ | Ước tính disk, giám sát, dọn theo chính sách |
| Log thiếu PID/instance | Decorators chưa đủ hoặc container trùng PID | Thêm pid và metadata từ collector |
| Nội dung chứa path/host/secret | Thông tin runtime/log được chia sẻ nguyên văn | Chọn dữ liệu tối thiểu, redact trước khi chia sẻ |
| Dùng option JDK 21 trên runtime khác | Tags/options khác release/VM | `java -Xlog:help` trên JDK thực của service |

### 11.1 Mẹo đọc thông báo lỗi parser

Nếu JVM không khởi động do cấu hình `-Xlog`, cần lấy **nguyên lỗi stderr và exit code** ở môi trường thử nghiệm, kiểm tra:

1. Có dùng dấu `:` ở đúng vị trí không?
2. Dấu `+`, `*`, `,` và `=` có đặt đúng cú pháp `what`?
3. Tag, level, decorator có xuất hiện trong `java -Xlog:help` của JDK đích?
4. Output có phải `stdout`, `stderr` hoặc `file=...` và path hợp lệ không?
5. File options có ở đúng vị trí sau decorators không?
6. Các tham số JVM có thực sự đứng **trước** main class hoặc `-jar` trên lệnh Java không?
7. Shell quoting có giữ nguyên toàn bộ argument nếu chứa dấu cách, wildcard hoặc ký tự đặc biệt không?

Ví dụ có thể gây khó hiểu:

```bash
java -jar app.jar "-Xlog:gc=info:file=gc.log"
```

Với cách đặt này, `-Xlog...` đứng **sau** `app.jar` nên thường trở thành **đối số của ứng dụng**, không phải JVM option. Cú pháp đúng:

```bash
java "-Xlog:gc=info:file=gc.log" -jar app.jar
```

Trên shell POSIX, ký tự `*` đôi khi chịu pathname expansion nếu không được quote theo ngữ cảnh. Đặt toàn bộ chuỗi `-Xlog:...` trong dấu nháy khi có wildcard/đường dẫn chứa khoảng trắng giúp tránh các diễn giải không mong muốn. Trên Windows, cú pháp quoting và path separators có khác biệt; kiểm tra lệnh đã truyền đúng cho JVM.

## 12. Tác động vận hành và độ tin cậy log

### 12.1 Logging quá nhiều có thể làm thay đổi hệ thống đang đo

`-Xlog:all=trace` hoặc wildcard rất rộng có thể tạo lượng message lớn, tăng CPU/I/O, lock/contention và disk usage tùy collector/level. Khi đo p99 latency hoặc GC overhead, bật logging nặng có thể **làm kết quả đo thay đổi**. Nên lưu chính xác cấu hình logging cho từng run, không so benchmark với log profile khác mà kết luận nguyên nhân chỉ do code.

Bắt đầu ở info và nhóm tag hẹp; chỉ nâng debug/trace có thời hạn. Với log GC, giữ timestamp, collector, JDK version và mẫu tải để phân tích. Nếu một event không xuất hiện trong log, cần xét liệu không phát sinh hay bị loại bởi selection/level/collector.

### 12.2 Đồng bộ thời gian và tương quan

- `uptime` đo thời gian kể từ lúc JVM start; không thay cho timestamp UTC.
- `utctime` hoặc `time` có ích để ghép với app log/OS/JFR; làm rõ timezone.
- `pid` có thể trùng giữa containers hoặc sau restart; cần container/instance ID từ hệ thống quản lý.
- `tags` và `level` giúp debug parser và phân biệt GC event với safepoint.
- Khi xoay vòng, event nằm ở nhiều file: parser cần đọc đúng thứ tự và tránh mất/tính trùng phần cắt file.
- Nếu sử dụng log collector, cần phân biệt **thời gian JVM tạo event** với **thời gian collector nhận message**.

### 12.3 Asynchronous logging và khả năng mất event

Một số JDK HotSpot hiện đại hỗ trợ `-Xlog:async`, cho phép log producer đẩy message vào buffer rồi writer thread ghi ra output. Đây là **cấu hình toàn cục**; trong JDK 21 buffer có giới hạn và **message có thể bị bỏ khi buffer đầy**. Vì vậy không bật async rồi mặc định số dòng log là dữ liệu lossless. Nếu cần đếm event hoặc làm forensic, phải đánh giá độ tin cậy, điều kiện tải và cách công cụ thông báo drop. Logging đồng bộ cũng không phải lời hứa về độ bền dữ liệu khi process bị kill hoặc storage mất.

### 12.4 Tính nhạy cảm của nhật ký JVM

Log có thể mang hostname, process IDs, class/package names, file paths, JVM flags, metadata runtime hoặc thông tin môi trường. Không paste toàn bộ log ra hệ thống công khai mà chưa phân loại người nhận; dùng đúng quyền lưu trữ và retention. GC log thường ít chứa payload ứng dụng hơn heap dump nhưng **không được suy ra luôn an toàn công khai**.

## 13. Checklist cấu hình -Xlog trước khi triển khai

- [ ] Đã xác minh service dùng HotSpot/JDK release nào và `-Xlog:help` hỗ trợ selector cần dùng.
- [ ] `what` dùng đúng tag/tag set, `+` cho AND, `,` cho OR selector, `*` cho wildcard, `=` cho ngưỡng level.
- [ ] Mức `info/debug/trace` phù hợp mục đích và tác động dự kiến.
- [ ] Output rõ `stdout`/`stderr`/`file=...`; các dấu `:` cho vị trí trống đúng.
- [ ] Decorators đủ để phân tích (ít nhất timestamp/uptime, level, tags khi cần).
- [ ] Nếu dùng file, thư mục tồn tại, JVM user có quyền ghi, path/quota/volume/collector được kiểm tra.
- [ ] Cấu hình `filecount`, `filesize` phù hợp và hiểu đó là rotation theo kích thước, không phải retention theo ngày.
- [ ] Tên file giảm xung đột qua restart/replica, chẳng hạn `%p` và `%t`.
- [ ] Có cách đối chiếu log với application metrics, GC/JFR và process identity.
- [ ] Không có option `-Xlog` khác vô tình ghi đè cùng output hoặc làm mất warning/error.
- [ ] Cấu hình đã được thử ở môi trường tương đương, không chỉ kiểm tra cú pháp bằng `-version`.
- [ ] Đã đánh giá overhead, dung lượng, bảo mật dữ liệu và cách rollback debug profile.
- [ ] Có cách đọc log sau rotation mà không bỏ sót hoặc lặp dữ liệu.

## 14. Bài tập tự kiểm tra

**Câu 1.** Vì sao `-Xlog:gc=debug` không bảo đảm có các dòng thuộc tag set `gc+heap`?

**Trả lời:** không có wildcard nên `gc` khớp **chính xác** tag set `gc`. Muốn mở rộng sang các tag set chứa GC, chọn `gc*=debug`; muốn đúng tag set gồm GC và heap, chọn `gc+heap=debug`.

**Câu 2.** Để gửi log GC ra stdout và chỉ dùng decorator `uptime,tid`, phải giữ cú pháp nào?

**Trả lời:** `-Xlog:gc::uptime,tid`. Dấu `::` cho biết vị trí output để trống (mặc định stdout), tiếp đến là decorator.

**Câu 3.** Cấu hình `-Xlog:gc*=info:file=gc.log:time,level,tags:filecount=0` có nghĩa xoay vòng không?

**Trả lời:** Không. `filecount=0` là **không xoay vòng**, file có thể tăng nếu JVM ghi nhiều log. Nếu muốn rotation theo kích thước, dùng `filecount` dương và `filesize` thích hợp.

**Câu 4.** Lệnh `-Xlog:gc,safepoint` có giống `-Xlog:gc+safepoint` không?

**Trả lời:** Không. Dấu phẩy là **hai selector độc lập**, còn dấu cộng xác định **một tag set chứa cả hai tag**. Không có wildcard, matching chính xác tag set.

**Câu 5.** Vì sao chương trình `UnifiedXlogDemo` không thể cam kết có đúng năm dòng GC log và một lần rotation?

**Trả lời:** lượng log phụ thuộc JVM/collector/event thực tế, và thời gian chạy ngắn chưa chắc phát đủ event/kích thước để rotate. `System.gc()` là yêu cầu mang tính gợi ý theo JVM, không phải bảo đảm cùng một event trên mọi môi trường.

**Câu 6.** Lệnh `java -jar app.jar -Xlog:gc` có bật logging của JVM không?

**Trả lời:** Không theo cách dự kiến, vì option sau `-jar app.jar` được truyền như **đối số ứng dụng**. Dùng `java -Xlog:gc -jar app.jar`.

## Tài liệu tham khảo

- [Oracle JDK 21 — The java Command, Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): cú pháp, tags/levels, decorators, output/rotation, examples và logging mặc định.
- [Oracle JDK 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): kiểm tra cú pháp trên baseline Java 17+.
- [Oracle JDK 21 — jcmd VM.log](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cấu hình logging động, kiểm tra options và những giới hạn quyền attach.
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158): thiết kế tag set, level, output/decorator và file rotation.

**Ghi nhớ:** đọc `-Xlog` theo thứ tự **`what : output : decorators : output-options`**. Dùng `+` để chọn tổ hợp tag, `,` để chọn nhiều selector, `*` để khớp tag set mở rộng và `=level` để đặt ngưỡng. Kiểm tra log file, đường dẫn, quyền và rotation bằng JVM thật; không lấy “không thấy log” làm bằng chứng không có sự kiện. Với production, cấu hình tối thiểu đủ dùng, theo dõi overhead và giữ thông tin thời gian/instance để việc chẩn đoán có thể kiểm chứng.