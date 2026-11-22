# Đọc unified GC logging — chẩn đoán GC độ trễ thấp trong Java 11+

## 1. Mục tiêu bài học

**Unified JVM Logging** là cơ chế ghi log thống nhất của HotSpot JVM. Từ Java 9 và tiếp tục có trên **Java 11, 17, 21, 25 và các JDK hiện đại**, cú pháp `-Xlog` cho phép chọn **thành phần JVM**, **mức chi tiết**, **đầu ra**, **dấu thời gian** và **xoay vòng file**. Với Garbage Collection (GC), các tag phổ biến gồm `gc`, `gc+heap`, `gc+phases`, `gc+cpu`, `gc+ergo` và `safepoint`.

Bài học nằm trong nhóm **GC độ trễ thấp** nên tập trung vào ba câu hỏi:

1. **GC có làm các application threads tạm dừng (stop-the-world — STW) không, và dừng trong bao lâu?**
2. **Trước và sau GC, lượng heap được JVM báo thay đổi thế nào; có dấu hiệu GC lặp dày hoặc phải Full GC không?**
3. **Trong một lần GC chậm, giai đoạn nào tốn thời gian và cần đối chiếu thêm log/metrics nào?**

Để trả lời đúng, cần phân biệt **tổng thời gian một concurrent GC cycle** với **thời gian STW pause**, hiểu cú pháp `GC(n)` và cảnh giác với việc đo độ trễ của ứng dụng chỉ bằng GC log.

**Điểm quan trọng nhất:** *Low-pause GC* không có nghĩa là mọi công việc GC chạy đồng thời; G1 có nhiều **pause STW**, còn các collector concurrent vẫn có thể phải tạm dừng thread ở một số giai đoạn. Chỉ các dòng log phù hợp mới được dùng tính pause statistics. `-XX:MaxGCPauseMillis` của G1 là **mục tiêu điều chỉnh**, không phải cam kết hard deadline cho từng lần GC.

### Kiến thức sẽ thực hành

- Bật log bằng `-Xlog:gc`, `-Xlog:gc*` và chọn thêm `safepoint` hoặc `gc+phases=debug`.
- Đọc decorators `time`, `uptime`, `level`, `tags` và GC identifiers.
- Diễn giải dòng G1 thực tế như `GC(0) Pause Young ... 18M->2M(32M) 1.269ms`.
- Phân biệt **Start / Summary / Phase / Concurrent** của cùng một GC ID; tránh đếm trùng.
- Nhận diện chu kỳ Young, Mixed, Remark, Full GC và dấu hiệu áp lực heap.
- Ghi file, giới hạn dung lượng và thay mức log qua `jcmd ... VM.log`.
- Biên dịch và chạy ví dụ **tương thích Java 11**, tạo GC log thật rồi đọc log bằng Java.
- Diễn giải sai số của con số pause, cách điều tra tail latency và những giới hạn theo collector/JDK.

## 2. Cú pháp unified logging

Oracle Java 11 mô tả dạng tổng quát:

```text
-Xlog[:[what][:[output][:[decorators][:output-options]]]]
```

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `what` | Tag selection, level, wildcard | `gc*=info,safepoint=info` |
| `output` | Nơi ghi | `stdout`, `stderr`, `file=gc.log` |
| `decorators` | Thông tin đi trước mỗi dòng | `time,uptime,level,tags` |
| `output-options` | File rotation và các tùy chọn khác | `filecount=5,filesize=20M` |

Có thể kiểm tra chính xác bộ tag/level mà **JDK đang chạy** hỗ trợ bằng:

```bash
java -Xlog:help
```

`-Xlog:help` không chạy ứng dụng; nó in cú pháp, tag names, levels và decorators có sẵn. Đừng copy tên một tag hiếm từ log của JDK khác mà mặc định JDK 11/vận hành thực tế cũng hỗ trợ.

### 2.1. Tag selection và dấu sao

Những lệnh sau **không tương đương**:

```bash
java -Xlog:gc -version
java '-Xlog:gc*' -version
java '-Xlog:gc+heap=debug' -version
```

- `gc` **không có wildcard**: chọn log messages có **tag set khớp chính xác `gc`**, ở mức `info` trở lên. Đây là tóm tắt ngắn; không gồm mọi dòng `gc,heap` hay `gc,phases`.
- `gc*` **có wildcard**: chọn những tag sets **chứa `gc`**, kể cả các tổ hợp như `gc,heap`, ở mức `info` trở lên.
- `gc+heap=debug`: chọn **tổ hợp tag chính xác `gc,heap`**, level `debug` trở lên, không phải mọi tag set khác cũng chứa `gc`.
- `gc+phases=debug`: xem các giai đoạn GC ở `debug` trên collector có xuất log phù hợp.
- `gc+ergo*=trace`: khớp các tag sets chứa đồng thời `gc` và `ergo`; `trace` có lượng output lớn, dùng để điều tra có kiểm soát.

Dấu `+` kết hợp tags trong **cùng một tag set**. Dấu phẩy giữa các lựa chọn `what` là phép **OR** các nhóm log độc lập. Ví dụ `gc*,safepoint=info` chọn log có tag `gc` ở level mặc định `info` và log tag `safepoint` ở level `info`.

**Không hiểu dấu sao thành “mọi mức chi tiết”.** `gc*` mở rộng tag match, nhưng mặc định vẫn là **`info`**; muốn debug/trace phải ghi rõ `=debug` hoặc `=trace`.

### 2.2. Các mức log hiện hành

Từ ít tới nhiều thông tin cho cùng tag:

| Level | Công dụng thường gặp |
| --- | --- |
| `error` | Lỗi nghiêm trọng |
| `warning` | Cảnh báo |
| `info` | Tóm tắt hoạt động, thời lượng pause, collector state |
| `debug` | Chi tiết GC phases, heap/regions, ergonomics tùy tag |
| `trace` | Chi tiết sâu, có thể tạo log rất lớn |
| `off` | Tắt log cho lựa chọn tương ứng |

`error` và `warning` không đồng nghĩa một ứng dụng đã chết; phải đọc **thông điệp cụ thể** và hành vi JVM. Ngược lại, không có warning cũng **không chứng minh** service có tail latency tốt.

Mặc định khi dùng `-Xlog:gc` thường đủ để tìm pause summary. Chỉ bật `debug`/`trace` khi cần phân tích nguyên nhân của các pause đã nhận diện.

### 2.3. Decorators: thông tin trước nội dung dòng

Ví dụ đã quan sát thực tế:

```text
[2026-11-07T15:32:41.664+0700][0.047s][info][gc          ] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->2M(32M) 1.269ms
```

Trong đó:

- `[2026-11-07T15:32:41.664+0700]` — `time`: thời gian thực theo đồng hồ, có timezone offset.
- `[0.047s]` — `uptime`: thời gian từ khi JVM bắt đầu, tính bằng giây.
- `[info]` — level.
- `[gc          ]` — tag set; JVM **có thể căn lề tags bằng khoảng trắng**, vì vậy parser đừng chỉ chấp nhận chính xác `[gc]`.
- `GC(0)` — ID của GC operation/cycle theo cách collector ghi.
- Phần còn lại là nội dung sự kiện.

Nếu **không** chỉ định decorators, unified logging mặc định dùng `uptime,level,tags`. Vì vậy không thể giả định dòng GC nào cũng có **wall-clock timestamp**; nếu cần đối chiếu metrics, request log hoặc log ứng dụng, hãy cấu hình rõ `time`.

`time` và `uptime` là **hai trục khác nhau**: uptime hữu ích để tính khoảng thời gian từ khi process chạy; wall-clock giúp ghép cùng log của services khác, nhưng cần lưu ý NTP, timezone, clock changes và độ lệch giữa máy.

## 3. Cấu hình để thu được GC log hữu ích

### 3.1. Xem nhanh qua terminal

```bash
java -XX:+UseG1GC '-Xlog:gc*' -version
```

Ví dụ chỉ in khởi tạo/thông tin GC liên quan vì `-version` không tạo workload đáng kể. Khi chạy ứng dụng thật, thay `-version` bằng tên main class hoặc `-jar app.jar` tương ứng.

Muốn có GC summary và thông tin safepoint:

```bash
java -XX:+UseG1GC '-Xlog:gc*,safepoint=info' -jar app.jar
```

**`app.jar` là placeholder** cho một JAR thực; dòng trên chỉ là cấu hình vận hành, không phải demo chạy nếu chưa có file ứng dụng.

### 3.2. Ghi file và giới hạn log rotation

Ví dụ cho production có giới hạn dung lượng:

```bash
java '-Xlog:gc*,safepoint=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar app.jar
```

Giải thích:

- `gc*,safepoint=info` — log GC ở info và safepoint ở info.
- `file=logs/gc-%p-%t.log` — ghi file; `%p` là PID, `%t` là dấu thời gian startup theo quy tắc JVM.
- `time,uptime,level,tags` — in đủ decorators để điều tra.
- `filecount=5,filesize=20M` — cấu hình số file rotation và kích thước mục tiêu. **Không phải hard quota chính xác từng byte**; log files phải được quản lý tiếp bằng policy hệ thống.
- Nếu dùng thư mục `logs/`, **hãy tạo thư mục đó trước khi khởi động JVM** và bảo đảm process user có quyền ghi.

Dấu nháy đơn quanh toàn bộ argument là ví dụ cho shell hỗ trợ single quotes và giúp tránh wildcard expansion. Trong PowerShell, single quotes cũng phù hợp. Trên Windows `cmd.exe`, cách trích dẫn khác: có thể dùng double quotes, xác nhận tham số JVM nhận đúng.

Khi cần chỉ tóm tắt ít dữ liệu:

```bash
java '-Xlog:gc:file=gc-summary.log:time,uptime,level,tags:filecount=3,filesize=5M' -jar app.jar
```

Khi cần điều tra G1 pause dài trong cửa sổ ngắn:

```bash
java '-Xlog:gc*=debug:file=gc-debug.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar app.jar
```

**`gc*=debug` có thể tăng log volume đáng kể.** Thử trên staging, đo overhead và tránh bật không giới hạn trên service allocation-intensive.

### 3.3. Nhóm tag thường dùng cho GC độ trễ thấp

| Cú pháp | Dữ liệu nổi bật | Dùng khi |
| --- | --- | --- |
| `-Xlog:gc` | Dòng tóm tắt `Pause Young/Full/Remark` (tùy collector) | Xác định pause count và duration |
| `-Xlog:gc*` | Mọi tag set chứa `gc` ở info | Tổng quan và bối cảnh |
| `-Xlog:gc+phases=debug` | Thời gian từng phase/worker | Có pause dài bất thường |
| `-Xlog:gc+heap=debug` | Heap/region details trước, sau và quanh GC | Cần xem heap pressure, young/old regions |
| `-Xlog:gc+cpu=info` | `User`, `Sys`, `Real` | Cần phân biệt CPU time và wall time |
| `-Xlog:gc+ergo*=debug` | Quyết định ergonomics/heuristics | Điều tra sizing và lựa chọn collection set |
| `-Xlog:gc+age=trace` | Phân bố tuổi object sống ở survivor | Điều tra promotion/tenuring sâu |
| `-Xlog:safepoint` | Tình trạng safepoint | Nghi application stalls ngoài GC pause |
| `-Xlog:gc+ref=debug` | Reference processing details | Nghi reference processing gây pause |

Không phải mọi collector và mọi bản JDK phát cùng số dòng hay cùng phase names. **Xem `java -Xlog:help` và log thực**, không phân tích tag bằng một danh sách cứng từ JDK khác.

**Nhận diện tầm mức:** `-Xlog:gc+phases=debug` chọn đúng tổ hợp tag đó; khi muốn giữ cả dòng tóm tắt GC trong một log file, có thể dùng `gc*,gc+phases=debug` với bộ chọn phù hợp, sau đó kiểm tra kết quả qua log.

## 4. Đọc một dòng G1 pause summary từ trái sang phải

Dòng được quan sát khi chạy một workload thử với G1:

```text
[2026-11-07T15:32:41.664+0700][0.047s][info][gc          ] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->2M(32M) 1.269ms
```

| Thành phần | Cách hiểu |
| --- | --- |
| `GC(0)` | GC identifier của hoạt động được log |
| `Pause` | Tín hiệu đây là **giai đoạn dừng ứng dụng** đối với dòng summary của G1 |
| `Young` | Thu gom tập vùng young theo G1 |
| `(Normal)` | Young GC bình thường, không phải Mixed hay Full |
| `(G1 Evacuation Pause)` | G1 đang di chuyển/copy objects còn sống khỏi collection set |
| `18M` | Heap **used trước GC** theo dòng summary |
| `2M` | Heap **used sau GC** |
| `(32M)` | Tổng **heap capacity** được dùng trong báo cáo GC |
| `1.269ms` | Thời lượng của **pause này**, tính bằng milliseconds |

**`18M->2M(32M)` không nói process RSS còn 2 MB.** Đây là một dạng **Java heap usage** trong ngữ cảnh GC, không bao gồm native memory, metaspace, thread stacks, direct buffers, code cache hoặc phần memory quản lý khác.

Và **18M − 2M = 16M không phải “đúng 16 MB objects đã bị leak rồi được chữa”**. Nó chỉ là chênh lệch used-heap trong lần GC; cần xem promotion, các đối tượng sống, concurrent work và workload để suy ra nguyên nhân.

### 4.1. Đơn vị thời gian và dung lượng

Unified logging có thể dùng:

- `B` = byte.
- `K` = 1024 bytes.
- `M` = 1024² bytes.
- `G` = 1024³ bytes.

Khi tự xây parser, **chuyển về bytes trước khi so sánh**; đừng so trực tiếp chuỗi `"900K"` với `"2M"`.

`1.269ms` là khoảng **milliseconds**, không phải seconds. Một số phase hoặc collector khác có thể in `us`, `ns`, `s` hoặc một format khác. Không áp regex cố định chỉ hợp G1 sang mọi collector mà không kiểm tra schema.

### 4.2. Một GC ID có nhiều dòng, không được đếm trùng

Chính lần chạy ví dụ phát ra hai dòng:

```text
[2026-11-07T15:32:41.662+0700][0.045s][info][gc,start    ] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[2026-11-07T15:32:41.664+0700][0.047s][info][gc          ] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->2M(32M) 1.269ms
```

Dòng `[gc,start]` thông báo **bắt đầu**; dòng `[gc]` có `before->after(capacity) duration` là **summary sau khi kết thúc**. **Đếm cả hai thành hai lần pause sẽ sai**.

Ngoài ra cùng `GC(0)` có thể xuất hiện trong nhiều dòng:

```text
GC(0) Eden regions: ...
GC(0) Survivor regions: ...
GC(0) User=... Sys=... Real=...
GC(0) [phase / worker stats / heap details]
```

Những dòng này mô tả **cùng một hoạt động** theo các tag khác nhau, không phải bốn hoạt động GC.

**Cách phân tích:** nhóm theo **GC ID** rồi phân biệt event start, phase, heap/cpu details và completion summary. Khi đo pause times cho G1, dùng các **dòng summary pause hoàn chỉnh**, không đơn giản đếm mọi dòng chứa `GC(n)`.

### 4.3. Không phải lúc nào GC ID cũng đồng nghĩa một STW pause

Một số collector có GC cycle gồm **nhiều giai đoạn** hoặc có nhiều pause thuộc cùng một cycle. Vì vậy GC identifier hữu ích để tương quan các dòng log, nhưng **không được phép giả định “một GC ID = một pause = một chu kỳ” cho mọi collector/JDK**.

Ngay với G1, một concurrent marking cycle có các giai đoạn concurrent và những pause như Remark/Cleanup. Để đo **STW**, phải nhận diện từng loại pause thật trong collector đang sử dụng.

## 5. Phân biệt STW pause và concurrent work

### 5.1. Pause Young, Mixed, Remark và Full của G1

Các mô tả thường gặp:

| Cụm log G1 | Cách hiểu | Tác động độ trễ |
| --- | --- | --- |
| `Pause Young (Normal)` | Thu gom young collections bình thường | **STW** trong thời gian pause summary |
| `Pause Young (Mixed)` | Thu gom young và một số old regions sau marking | **STW**; có thể có thêm old-region evacuation |
| `Pause Young (Concurrent Start)` | Young collection khởi động quá trình marking concurrent | **STW** cho phần Pause Young |
| `Pause Remark` | Hoàn tất marking, xử lý references và các tác vụ liên quan | **STW** |
| `Pause Cleanup` | Hoàn tất/đánh giá marking và collection candidates theo phiên bản | **STW** |
| `Pause Full (G1 Compaction Pause)` | Thu gom/compaction toàn heap dự phòng khi cần | **STW**, đáng điều tra nếu xảy ra thường xuyên |

Tên exact wording có thể khác giữa Java 11 và JDK mới. Đây là **ý nghĩa**, không phải danh sách regex chính thức cho mọi phiên bản.

**Full GC không tự có nghĩa Java heap chắc chắn đã hết**. Nó có thể do allocation pressure, fragmentation, evacuation failure, explicit `System.gc()` (tùy flags) hoặc những tình huống khác. Đọc **cause** và các dòng ngay trước đó.

### 5.2. Concurrent không có nghĩa ứng dụng bị pause toàn bộ chu kỳ

Các dòng ví dụ về công việc concurrent:

```text
GC(12) Concurrent Mark Cycle
GC(12) Concurrent Scan Root Regions
GC(12) Concurrent Mark From Roots
GC(12) Concurrent Mark Cycle 120.000ms
```

**Đây là minh họa định dạng**, không phải output của chương trình test. Tên phase/định dạng thay đổi theo JDK.

Một chu kỳ concurrent có thể chạy **120 ms** trong khi application threads vẫn được lên lịch. **Không cộng toàn bộ 120 ms vào “GC STW pause time”**. Concurrent GC vẫn dùng CPU/memory bandwidth và có thể ảnh hưởng latency qua contention, nhưng cơ chế tác động khác với việc tất cả application threads bị dừng.

Trong cùng cycle, những giai đoạn có `Pause Remark` hoặc `Pause Cleanup` phải được xem **riêng**. Muốn đánh giá đúng tail latency, ghép timestamps của GC pause, safepoint và request traces.

### 5.3. Safepoint không đồng nghĩa GC pause

`-Xlog:safepoint` giúp xem những khoảng JVM đồng bộ hoặc dừng threads cho các tác vụ có thể không phải GC, ví dụ một số hoạt động class metadata hoặc quản lý runtime.

Một safepoint event có thể chứa:

- Thời gian để các threads **đi đến trạng thái safepoint**.
- Thời gian JVM thực hiện **tác vụ tại safepoint**.
- Thời gian liên quan tới pause/resume theo thông điệp của runtime.

Khi có latency spike, tổng application-visible stall có thể khác con số trong dòng GC summary. **Không cộng bừa mọi safepoint line với từng GC pause** vì có thể trùng thời gian; phải nhóm và liên kết theo timestamp/operation.

Nếu GC log cho thấy 2 ms nhưng request dừng 100 ms, hãy kiểm tra thêm thread scheduling, CPU starvation, lock contention, safepoints, I/O và tracing; đừng kết luận mọi 98 ms đều do GC.

## 6. Dấu hiệu GC pressure và các trường hợp cần điều tra

### 6.1. Young GC xảy ra liên tục

Một chuỗi `Pause Young` dày đặc thường là dấu hiệu heap young bị lấp nhanh hoặc allocation rate cao. Đây **không tự là lỗi**; nhiều workload throughput cao sẽ GC thường xuyên mà mỗi pause vẫn ngắn.

Cần kiểm tra:

1. Pause frequency theo thời gian — có nhiều pause sát nhau không?
2. **Max/p95/p99 pause duration**, không chỉ mean.
3. Tổng pause wall-time trong cửa sổ.
4. Allocation rate và throughput của ứng dụng.
5. Heap trước/sau; survivor và old occupancy có tăng đều không?
6. Có Full GC, evacuation failure hay out-of-memory warning không?

Nếu mỗi GC chỉ 1 ms nhưng xảy ra mỗi 5 ms, tổng tác động vẫn có thể lớn. Ngược lại, một pause 30 ms duy nhất trong 1 giờ cần đánh giá theo SLA/traffic chứ không tự động quyết định đổi collector.

### 6.2. Mixed GC và tốc độ tăng old regions

G1 có thể thực hiện concurrent marking rồi tới **Mixed collections** để giải phóng một phần old regions. Một số old regions vẫn tồn tại nếu còn live objects; điều này bình thường.

Quan sát:

- Old-gen occupancy sau các chu kỳ.
- Mixed collections có đủ hiệu quả giảm old used không?
- G1 có thiếu thời gian concurrent marking trước khi heap đầy không?
- Có repeated Full GC/OOM khi old heap tăng không?

Đừng gọi mọi mức old occupancy cao là leak. Heap có cache/lifetime dài có thể ổn định ở mức cao; leak cần bằng chứng live set tăng bền vững dưới workload tương ứng.

### 6.3. Full GC hoặc evacuation failure

Các dấu hiệu đáng ưu tiên:

```text
Pause Full (...)
To-space exhausted
Evacuation Failure
Allocation Failure
OutOfMemoryError
```

Đây là **những cụm cần tìm**, không phải chúng luôn xuất hiện cùng nhau. Tùy collector/JDK, câu chữ có thể khác.

Hành động:

- Đọc những dòng **trước và sau** sự kiện, cùng GC ID và timestamp.
- Kiểm tra heap sizing, allocation rate, reference chains, humongous objects và GC ergonomics.
- Xem request latency/GC CPU trước khi đề xuất tăng heap hay đổi collector.
- Nếu nghi leak, dùng JFR OldObjectSample hoặc heap dump thích hợp, không chỉ nhìn `after GC heap`.
- Không thay nhiều JVM flags đồng thời khi chưa có baseline và kế hoạch đo lại.

### 6.4. Humongous allocation trong G1

G1 chia heap thành **regions**. Các object lớn hơn một phần đáng kể của region size được coi là **humongous**, có đường cấp phát và thu hồi riêng. Log có thể ghi `G1 Humongous Allocation` hoặc details về humongous regions.

Không đọc mọi `Pause Young (Concurrent Start) (G1 Humongous Allocation)` thành “Full GC”. Nó có thể là một **young pause khởi động concurrent marking** do áp lực humongous allocation.

Nếu log cho thấy GC xảy ra liên tục gần những object/array lớn, xem kích thước object, region sizing và cách thiết kế bộ đệm; không chỉ nhìn tổng heap.

## 7. Phân tích thời lượng: max, p95/p99 và tỷ lệ pause

### 7.1. Những metric có ích

Với các **pause summaries hoàn chỉnh** thuộc đúng một collector/JDK, có thể tính:

| Metric | Cách tính | Ý nghĩa |
| --- | --- | --- |
| `count` | Số dòng pause summary, bỏ các dòng start/detail | Số lần pause được quan sát |
| `max pause` | Lớn nhất của duration từng pause | Tail event nghiêm trọng nhất trong cửa sổ |
| `mean pause` | Tổng duration / count | Chi phí trung bình, dễ bị ảnh hưởng bởi sample mix |
| `p95/p99 pause` | Percentile của pause durations | Phân phối tail pause |
| `total pause time` | Tổng durations của những pause không chồng lấn | Tổng thời gian dừng theo tập pause đã đo |
| `pause fraction` | total pause time / wall-clock window | Ước lượng tỷ lệ thời gian GC dừng ứng dụng |

Nếu logs bị rotate/mất hoặc thiếu cửa sổ, các metrics sẽ **thiên lệch**. Nếu parser đếm cả start và completion line, count và p95 sai. Nếu cộng concurrent cycle duration, pause fraction bị đội lên không đúng.

### 7.2. p99 pause không phải p99 request latency

**GC p99 pause** là percentile của **các pause events**, còn **request p99** là percentile của **request durations**. Chúng có mẫu số và cơ chế tác động khác nhau.

Một GC pause 20 ms có thể ảnh hưởng nhiều request cùng lúc; một request chậm 500 ms có thể không trùng GC. Muốn quy trách nhiệm cần đồng bộ timestamp/trace và các metrics hệ thống.

### 7.3. Cửa sổ đủ lớn và xử lý lệch thống kê

Nếu chỉ có 5 pause trong test, `p99` không có nhiều ý nghĩa thống kê. Khi service chạy vài giờ, hãy xét:

- Các cửa sổ ổn định và cửa sổ incident riêng.
- Tần suất traffic, concurrency, allocation rate.
- Warm-up/JIT, heap sizing và GC ergonomics.
- Có thay collector settings, deployment hoặc machine load giữa chừng không?
- Dữ liệu bị rotate, dropped hoặc collector format thay đổi.

Đừng dùng một con số p95 từ log 2 giây để cam kết SLA dài hạn.

## 8. gc+cpu: phân biệt User, Sys và Real

Với `-Xlog:gc+cpu=info`, G1 có thể ghi:

```text
GC(4) User=0.19s Sys=0.00s Real=0.01s
```

Đây là **dòng minh họa từ kiểu log Oracle mô tả**, không phải output của demo. Ý nghĩa:

- **User**: tổng **CPU time của các threads** chạy code ở user mode trong hoạt động được đo. Vì GC có thể chạy song song, tổng CPU seconds có thể **lớn hơn wall-clock seconds**.
- **Sys**: CPU time dùng trong kernel/system mode.
- **Real**: **elapsed wall-clock time** của phần hoạt động liên quan.

Ví dụ `User=0.19s, Real=0.01s` không có nghĩa JVM “chạy nhanh hơn thời gian thực”; nhiều GC worker threads có thể sử dụng CPU đồng thời.

Nếu `Real` cao hơn bất thường so với `User+Sys`, xem CPU starvation, process scheduling, virtualization hoặc I/O stalls; nếu `Sys` cao, có thể nghi chi phí OS/memory operations. Không quy mọi chênh lệch cho duy nhất GC algorithm khi chưa đo hệ thống.

**Quan trọng:** `Real` của một dòng `gc+cpu` là metric trong ngữ cảnh GC event đó; muốn đánh giá request latency cần tracing/observability ở tầng ứng dụng.

## 9. gc+phases: lần theo giai đoạn tốn thời gian

Khi thấy một pause bất thường, bật mức phù hợp:

```bash
java '-Xlog:gc*=debug:file=gc-debug.log:time,uptime,level,tags:filecount=3,filesize=20M' -jar app.jar
```

Hoặc lựa chọn cụ thể:

```bash
java '-Xlog:gc,gc+phases=debug,gc+heap=debug:file=gc-phases.log:time,uptime,level,tags:filecount=3,filesize=20M' -jar app.jar
```

Lệnh thứ hai chứa bộ chọn `gc` cho pause summaries, `gc+phases` và `gc+heap` ở debug cho các tag set tương ứng. Với các chi tiết thuộc các tag khác, cần mở rộng selection có chủ đích.

Một số phase G1 thường gặp hoặc tương đương tùy JDK:

- **Pre Evacuate Collection Set**: chuẩn bị cho pause, TLAB, root và chọn collection set.
- **Merge Heap Roots / Scan Heap Roots**: xử lý các nguồn references vào collection set.
- **Evacuate Collection Set / Object Copy**: copy live objects sang regions mới.
- **Post Evacuate Collection Set**: kết thúc và xử lý hỗ trợ.
- **Reference Processing**: xử lý các loại references khi cần.
- **Other**: nhiều tác vụ quản lý khác.

**Không hardcode thứ tự/label của phase qua mọi JDK.** Oracle documentation và phiên bản HotSpot đã thay đổi tên/cách chia giai đoạn theo thời gian. Dùng log của JVM hiện tại để xác định các phase nổi bật.

### 9.1. Đọc bảng worker timings

Một dòng debug có thể cho `Min`, `Avg`, `Max`, `Sum` của GC worker tasks. Khi nhiều workers chạy song song:

- `Sum` là tổng thời gian công việc ở nhiều workers, **không phải duration STW của toàn pause**.
- `Max` của workers có thể liên quan tới slowest worker, nhưng còn synchronization/parallel phases khác.
- `Avg` là trung bình theo workers, không phải average response latency.
- Một phase có `Sum=40ms` với 8 workers có thể chỉ đóng góp khoảng vài ms elapsed nếu làm song song.

**Không cộng tất cả phase sums rồi tự gọi đó là GC pause wall time.** Dùng dòng summary `Pause ... N ms` làm chuẩn để đối chiếu tổng elapsed và điều tra chi tiết.

### 9.2. Khi GC phases ngắn nhưng pause summary dài

Xem thêm:

- Những phase không được bật ở level hiện tại.
- Runtime safepoint time hoặc OS scheduling.
- Serial portions, thread coordination, termination imbalance.
- CPU contention từ process khác.
- Heap page faults hoặc memory commitment.
- JVM/runtime version-specific details.

Chỉ sau khi xác định bottleneck mới cân nhắc tuning flags; những thay đổi young-gen cố định có thể làm **vô hiệu hóa khả năng G1 tự điều chỉnh để đạt pause goal**.

## 10. Đọc unified logs của các low-latency collectors khác

### 10.1. G1

G1 là collector mặc định trên nhiều cấu hình server HotSpot Java 11. Nó chia heap thành regions, thu young/mixed theo STW pause ngắn và có concurrent marking.

`-Xlog:gc*` giúp thấy pause summaries và concurrent phases, nhưng **phải tách từng loại** khi tính tổng thời gian dừng. Mục tiêu `-XX:MaxGCPauseMillis` là **soft goal** mà G1 cố gắng thỏa, không phải real-time guarantee.

### 10.2. ZGC

ZGC được giới thiệu ở JDK 11 dưới dạng tính năng còn ở giai đoạn đầu với yêu cầu/bản phân phối riêng; các JDK hiện đại đã thay đổi đáng kể ZGC, bao gồm mô hình generational. **Không dùng các flag thử nghiệm từ giai đoạn đầu như khuyến nghị chung cho JDK 25+**.

Khi dùng ZGC hiện hành:

- Chọn `-Xlog:gc*` trước để xem GC cycles, pause stages và heap statistics.
- Đọc **dòng pause** theo wording của ZGC đúng phiên bản; không dùng regex `Pause Young (G1 Evacuation Pause)`.
- Nhiều phase chạy concurrent, có thể kéo dài hơn pause time mà không STW toàn bộ chu kỳ.
- Đối chiếu allocation stalls, CPU sử dụng và request traces; “pause ngắn” không đồng nghĩa toàn bộ latency tốt nếu concurrent GC thiếu CPU hoặc heap margin.

### 10.3. Shenandoah

Shenandoah là collector concurrent/low-pause được cung cấp ở nhiều bản phân phối OpenJDK, nhưng khả năng hỗ trợ và syntax tùy phiên bản/vendor. Không giả định tất cả Java 11 builds đều có Shenandoah.

Cũng dùng unified `-Xlog` và xem những dòng **concurrent phases**, **stop-the-world pauses**, evacuation/update refs theo runtime cụ thể. Không copy bộ parser G1 cho Shenandoah và không dùng flags collector không còn hợp lệ chỉ vì thấy trong tài liệu cũ.

### 10.4. Không so sánh collector chỉ từ một log ngắn

Muốn so G1/ZGC/Shenandoah:

1. Chọn các bản JDK/collector thực sự **được hỗ trợ và phù hợp** workload hiện hành.
2. Cố định workload, heap/memory constraints, latency targets và concurrency.
3. Thu metrics request p95/p99, throughput, CPU, RSS, heap, GC pause distribution.
4. Đọc collector-specific log phases; không áp một parser hoặc một “Pause” regex chung.
5. Lặp lại nhiều lượt, ghi rõ số mẫu và runtime flags.

Low-latency collector có thể đánh đổi CPU, memory overhead hoặc throughput; không có collector tối ưu mọi workloads.

## 11. Thực hành: tạo log G1 thật và viết parser Java 11

Chương trình `GcLogReadingDemo` bên dưới là **một tệp Java độc lập**:

- Chế độ `workload` cấp phát nhiều mảng nhỏ trong heap 32 MiB để kích hoạt G1 young collections.
- Chạy JVM với `-XX:+UseG1GC -Xms32m -Xmx32m` và unified logging ra `gc.log`.
- Chế độ `read gc.log` đọc **các dòng G1 pause summary** chứa `GC(n) Pause ... before->after(capacity) duration`.
- Phân biệt log **start** với **completion** vì regex yêu cầu có cả before/after và duration.
- Chuyển `B/K/M/G/T` về bytes trước khi so sánh before/after.
- Kiểm tra có ít nhất một summary, heap giảm ở ít nhất một lần, max pause dương, GC ID và decorators.
- Không hardcode **số GC**, **max duration** hay **before/after heap** vì những giá trị này thay đổi theo runtime/máy/JIT/GC.

**Phạm vi parser:** đây là parser giáo dục cho **format G1 summary quan sát được**, **không phải thư viện GC log production** có thể hiểu mọi collector, mọi JDK, log rotation, định dạng khác hoặc dòng nhiều dòng. Đối với log lớn, dùng streaming và một parser/tool được bảo trì phù hợp runtime.

### 11.1. Mã hoàn chỉnh — GcLogReadingDemo.java

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GcLogReadingDemo {
    private static final Object[] RETAIN = new Object[16];

    private static void allocate() {
        for (int i = 0; i < 6000; i++) {
            byte[] bytes = new byte[64 * 1024];
            bytes[0] = (byte) i;
            RETAIN[i % RETAIN.length] = bytes;
        }
    }

    private static void check(boolean yes, String message) {
        if (!yes) throw new AssertionError(message);
    }

    private static void readLog(Path file) throws Exception {
        List<String> lines = Files.readAllLines(file);

        Pattern pause = Pattern.compile(
            "GC\\((\\d+)\\) Pause .*? " +
            "(\\d+(?:\\.\\d+)?)([BKMGT])->" +
            "(\\d+(?:\\.\\d+)?)([BKMGT])\\(" +
            "(\\d+(?:\\.\\d+)?)([BKMGT])\\) " +
            "(\\d+(?:\\.\\d+)?)ms");

        int count = 0;
        boolean heapDecreased = false;
        boolean idPresent = false;
        boolean decorated = false;
        double maxPause = 0.0;

        for (String line : lines) {
            // Các GC tags có thể được căn lề bằng khoảng trắng.
            if (line.startsWith("[")
                    && line.contains("][info][gc")) {
                decorated = true;
            }

            Matcher m = pause.matcher(line);
            if (m.find()) {
                count++;
                idPresent = !m.group(1).isEmpty();

                double before = Double.parseDouble(m.group(2))
                        * unit(m.group(3));
                double after = Double.parseDouble(m.group(4))
                        * unit(m.group(5));

                heapDecreased |= after < before;
                maxPause = Math.max(maxPause,
                        Double.parseDouble(m.group(8)));
            }
        }

        check(count > 0, "No G1 pause summary found");
        check(heapDecreased, "No GC reduced used heap");
        check(maxPause > 0 && idPresent && decorated,
                "Unexpected GC log schema");

        System.out.println("pause summaries found = true");
        System.out.println("heap decreased in a pause = true");
        System.out.println("max pause positive = true");
        System.out.println("GC identifiers present = true");
        System.out.println("decorators present = true");
        System.out.println("ALL CHECKS PASSED");
    }

    private static double unit(String unit) {
        switch (unit) {
            case "B": return 1.0;
            case "K": return 1024.0;
            case "M": return 1024.0 * 1024.0;
            case "G": return Math.pow(1024.0, 3);
            case "T": return Math.pow(1024.0, 4);
            default: throw new IllegalArgumentException(unit);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("workload")) {
            allocate();
            System.out.println("WORKLOAD COMPLETED");
        } else if (args.length == 2 && args[0].equals("read")) {
            readLog(Path.of(args[1]));
        } else {
            throw new IllegalArgumentException(
                    "Use workload or read <gc.log>");
        }
    }
}
```

`Path.of`, `Files.readAllLines`, `Pattern`, `Matcher`, switch, arrays đều có từ Java 11. Không cần thư viện ngoài JDK.

**Lệnh chạy trong thư mục test có quyền ghi:**

```bash
javac --release 11 GcLogReadingDemo.java

java -XX:+UseG1GC -Xms32m -Xmx32m '-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=3,filesize=5M' GcLogReadingDemo workload

java GcLogReadingDemo read gc.log
```

Dòng thứ hai sinh `gc.log` qua **JVM logging**. Dòng thứ ba là chương trình **đọc file đã ghi**; nó không bắt buộc bật GC logging của chính process parser.

**Đầu ra đã kiểm chứng** sau khi biên dịch bằng `javac --release 11` và chạy trên HotSpot JDK 24.0.2:

```text
WORKLOAD COMPLETED
pause summaries found = true
heap decreased in a pause = true
max pause positive = true
GC identifiers present = true
decorators present = true
ALL CHECKS PASSED
```

File `gc.log` thử nghiệm có kích thước **43.047 byte** và chứa những dòng `GC(0) Pause Young ...`; con số file size chỉ là quan sát của một lần chạy, không phải thuộc tính cố định của demo.

**Lưu ý giới hạn:** dù chương trình biên dịch theo API Java 11, các dòng log cụ thể có thể đổi theo JDK 11/17/21/24/25 và các flags. Với collector khác G1 hoặc format log không giống regex, cần sửa parser/kiểm chứng tương ứng — không coi `AssertionError` ở ví dụ là lỗi GC của ứng dụng.

### 11.2. Giải thích điều kiện trong parser

| Kiểm tra | Ý nghĩa |
| --- | --- |
| `pause summaries found = true` | Có ít nhất một dòng chứa đủ `GC(n) Pause ... before->after(capacity) duration` |
| `heap decreased in a pause = true` | Có ít nhất một G1 pause mà used heap sau GC thấp hơn trước |
| `max pause positive = true` | Ít nhất một pause summary có thời lượng dương |
| `GC identifiers present = true` | Parser bắt được GC identifier |
| `decorators present = true` | Có log dòng phù hợp với info/gc decorators |
| `ALL CHECKS PASSED` | Các assertion thành công; không chứng minh SLA latency |

Điểm nhỏ nhưng hữu ích: trong JVM hiện hành, field `tags` có thể được **padded**, ví dụ `[gc          ]`, nên code kiểm tra `line.contains("][info][gc")` thay vì chỉ tìm `[info][gc]` kết thúc bằng bracket ngay.

### 11.3. Giới hạn của ví dụ phải hiểu trước khi dùng production

- `Files.readAllLines` nạp toàn bộ file vào RAM; **không phù hợp** với GC log hàng GB. Dùng `Files.lines` kèm `try-with-resources`, hoặc đọc streaming `BufferedReader`.
- Nếu log bị **rotate**, chỉ đọc `gc.log` có thể bỏ các file cũ; cần ghép theo timestamp đúng thứ tự và xử lý duplicate/overlap.
- Regex chọn **G1 pause summaries** dạng có `before->after(capacity) duration ms`. Nó **không** phải parser chung của ZGC/Shenandoah/Parallel/Serial.
- Parser này chỉ kiểm tra có đủ trường, **chưa tính p95/p99**, chưa xử lý safepoint waits hay concurrent cycles.
- Nó kiểm tra một **điều kiện thử nghiệm**, không đo GC pause performance production.
- Không chạy workload tạo hàng trăm MB allocation trong JVM production để test; dùng môi trường riêng.

## 12. Điều chỉnh logging lúc ứng dụng đang chạy

Trên JDK có `jcmd` và quyền attach process, có thể xem cấu hình:

```bash
jcmd <PID> VM.log list
```

`<PID>` là placeholder, phải thay bằng **PID thực tế**. Cú pháp `VM.log` hỗ trợ tham số `output`, `what`, `decorators`, `output_options`, `list`, `disable` và `rotate` theo Java 11 tools guide.

Ví dụ yêu cầu tăng mức log trên một JVM đang chạy:

```bash
jcmd <PID> VM.log what=gc*=debug
```

Hoặc đặt lại đầu ra/tags bằng lựa chọn được JVM hỗ trợ. **Hãy đọc trợ giúp của process trước khi thay**:

```bash
jcmd <PID> help VM.log
jcmd <PID> VM.log list
```

Đừng áp dụng `disable` toàn cục khi chỉ muốn tắt debug GC, vì nó có thể vô hiệu hóa **những log của JVM khác**. Thay cấu hình qua `VM.log` còn phụ thuộc output và các lựa chọn đang tồn tại; xem thông báo jcmd sau khi chạy và đọc `VM.log list` để xác nhận.

Nếu process trong container, user khác, không hỗ trợ attach hoặc bị security policy chặn, `jcmd` có thể thất bại dù ứng dụng hoạt động bình thường. Không tự cấp đặc quyền quản trị chỉ để bật log nếu chưa được phép.

## 13. Checklist chẩn đoán độ trễ qua GC log

Khi nhận một incident “p99 tăng vào 14:00”, có thể đi theo thứ tự sau:

1. **Xác định JVM/JDK/collector:** ghi version/vendor, `-XX:+UseG1GC` hay collector khác, heap size và các flags GC có hiệu lực.
2. **Xác định khoảng thời gian:** log có wall-clock `time` không? timezone/time skew? Các file rotation có đủ cửa sổ không?
3. **Tách pause summaries:** loại dòng start, debug details và concurrent cycle khỏi tập STW pauses.
4. **Tính số lần/max/p95/p99** khi có đủ mẫu; không chỉ nhìn average.
5. **Nhóm theo GC IDs** để xem các details trước/sau một pause chậm.
6. **Đọc used heap trước/sau và capacity:** có GC lặp dày, old regions tăng hoặc Full GC không?
7. **Đối chiếu `gc+cpu` và `gc+phases`** khi cần biết tắc nghẽn CPU/OS/worker phase.
8. **So sánh safepoint và request traces:** spike có trùng GC pause không? Hay nằm ở CPU/I/O/lock?
9. **Xem allocation rate và liveness:** có object/array bất thường, humongous allocation, memory leak hay cache growth?
10. **Đưa ra giả thuyết cụ thể:** ví dụ “Mixed pause kéo dài do object copying” thay vì “GC chậm chung chung”.
11. **Thay đúng một biến/cấu hình** khi thử giải pháp, giữ workload tương đương.
12. **Đo lại**: request tail latency, GC pauses, CPU, RSS, throughput; không chỉ xem một log sau chỉnh flags.

### 13.1. Ví dụ phân tích từ một pause 1.269 ms

```text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->2M(32M) 1.269ms
```

Kết luận **có cơ sở**:

- Đây là **G1 Young STW pause** theo format log.
- Dòng log ghi **1.269 ms** cho pause này.
- Used heap của JVM từ **18 MiB xuống 2 MiB**, reported heap capacity **32 MiB**.
- Có thể dùng GC ID 0 để tìm lines start, heap và phase details tương ứng nếu đã bật.

Kết luận **không có cơ sở chỉ từ dòng này**:

- “Service p99 chắc chắn tăng 1.269 ms.”
- “JVM chỉ sử dụng tổng cộng 2 MiB RAM.”
- “Mọi request đều bị ảnh hưởng đúng 1.269 ms.”
- “Ứng dụng đã hết leak vì heap giảm 16 MiB.”
- “Tất cả GC sau này chắc chắn không vượt 2 ms.”

**Một dòng GC log không thay thế request tracing, heap profiler và đo workload.**

## 14. Những sai lầm thường gặp

| Nhầm lẫn / triệu chứng | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `-Xlog:gc` không có heap/phase details | Tag selection chính xác `gc`, level info | Dùng `gc*` hoặc bổ sung `gc+heap=debug`/`gc+phases=debug` |
| `-Xlog:gc*` quá nhiều dòng | Wildcard mở rộng các tag sets có `gc` | Chọn tag/level hẹp hơn, dùng file rotation |
| Thấy `gc,start` rồi tăng count | Một GC có start và completion | Đếm **summary** thích hợp, không đếm mọi `GC(n)` |
| Thấy `Concurrent Mark Cycle 120ms` và ghi STW=120ms | Concurrent work ≠ full stop | Tìm những `Pause` stage thực, giữ concurrent duration riêng |
| `GC(0)` xuất hiện nhiều lần | Nhiều messages cùng GC ID | Group theo ID và loại message |
| Heap giảm nhưng RSS chưa giảm | Heap used khác process memory/RSS | Đo RSS, native memory và OS metrics riêng |
| `before->after` được dùng làm exact allocation bytes | Đó là used heap quanh collection | Đo allocation rate bằng công cụ thích hợp |
| Parser bỏ qua `[gc          ]` | Tags được padding | Normalize/trim decorators hoặc match linh hoạt |
| `Real` nhỏ hơn `User` | Nhiều worker threads cộng CPU time | Phân biệt CPU seconds và elapsed wall seconds |
| `gc+phases` có Sum lớn hơn pause | Nhiều workers song song | Không cộng worker CPU times thành STW |
| Thấy Full GC là kết luận leak | Full GC có nhiều nguyên nhân | Xem GC cause, old occupancy, object liveness |
| Không có GC log trong file | Thiếu quyền ghi, sai path, log rotation hoặc JVM args không được truyền | Kiểm tra `-Xlog:help`, output path, actual process command |
| File GC bị ghi đè | Cấu hình output filename/rotation | Dùng `%p`/`%t` và retention riêng |
| Log file bị mất phần đầu | Rotation giới hạn filecount/filesize | Mở rộng retention, thu đầy đủ rotated files |
| `MaxGCPauseMillis=50` nhưng pause 80ms | G1 pause goal là soft, không hard guarantee | Điều tra phase, CPU/OS load, heap sizing |
| Không thấy safepoint details | Chỉ bật `gc` tag | Bổ sung `safepoint` phù hợp |
| ZGC logs không khớp regex G1 | Wording/phase/schema khác | Dùng collector-specific parser/version-aware analysis |
| Bật trace trên production gây overhead | Quá nhiều log I/O | Giới hạn cửa sổ và output, đo overhead, tắt sau điều tra |
| Đổi nhiều GC flags rồi không biết tác dụng | Thiếu baseline | Chỉ đổi một giả thuyết một lúc, ghi kết quả trước/sau |
| Một p99 GC pause từ 3 samples | Thống kê thiếu dữ liệu | Tăng cửa sổ và đối chiếu workload |

## 15. An toàn vận hành

- **Hạn chế quyền đọc/ghi log:** đường dẫn file, GC flags, heap layout và process metadata có thể tiết lộ thông tin nội bộ.
- **Không ghi log vô hạn:** dùng rotation và chính sách lưu trữ/thu gom ngoài JVM. `filecount/filesize` là các mức mục tiêu, không thay filesystem quota.
- **Quan sát overhead của logging:** debug/trace sinh nhiều dữ liệu, gây I/O và có thể làm chính latency bạn đo bị thay đổi.
- **Đặt wall-clock + uptime:** giúp tương quan cross-service và tính thời gian trong process; giữ timezone nhất quán.
- **Không bỏ cảnh báo toàn JVM:** tránh `-Xlog:disable` nếu không có nhu cầu và review rõ ràng.
- **Tránh hardcoded GC flags lỗi thời:** dùng `-Xlog` cho Java 11+, không làm hướng dẫn mới dựa trên cơ chế `PrintGCDetails` thời Java 8.
- **Cập nhật định dạng khi nâng JDK:** không coi regex cho một JDK là tiêu chuẩn classfile/API ổn định.
- **Kiểm chứng bộ thu thập:** ZGC, G1 và Shenandoah có các giai đoạn và log vocabulary khác nhau.
- **Không tự động đổi collector giữa incident** khi chưa đo memory/CPU/throughput; latency thấp thường là bài toán hệ thống.

## 16. Tự kiểm tra kiến thức

**Câu 1.** `-Xlog:gc` và `-Xlog:gc*` khác gì?  
**Đáp án:** `gc` match exact tag set, còn `gc*` match cả tag sets có chứa `gc`, như `gc,heap`; cùng level info nếu không ghi khác.

**Câu 2.** `gc+phases=debug` dùng để làm gì?  
**Đáp án:** Xem chi tiết các giai đoạn GC có tổ hợp tag phù hợp, giúp giải thích một pause dài; không phải tự bật mọi tag GC ở debug.

**Câu 3.** `[0.047s]` là wall-clock time không?  
**Đáp án:** Không, đây là JVM uptime; wall-clock được in nếu có decorator `time`.

**Câu 4.** Dòng `GC(0) Pause Young ...` tại `[gc,start]` có phải một pause khác so với `[gc]` cùng GC ID không?  
**Đáp án:** Không. Dòng start và dòng summary có thể mô tả cùng một hoạt động.

**Câu 5.** `18M->2M(32M)` nghĩa là process RSS giảm từ 18 MiB xuống 2 MiB?  
**Đáp án:** Không. Đây là used Java heap trước/sau GC và reported heap capacity.

**Câu 6.** `Concurrent Mark Cycle 120ms` có nghĩa ứng dụng STW 120 ms?  
**Đáp án:** Không. Concurrent work chạy đồng thời với ứng dụng, phải tách các giai đoạn Pause thật khi tính STW.

**Câu 7.** Có thể lấy `MaxGCPauseMillis` làm deadline cứng của mọi G1 pause không?  
**Đáp án:** Không. G1 là collector với pause-time goal mềm; nó không bảo đảm real-time deadline.

**Câu 8.** `gc+cpu` có `User=0.19s Real=0.01s` có phải log bị lỗi không?  
**Đáp án:** Không. User là tổng CPU time nhiều worker threads, Real là wall time; nhiều workers có thể làm tổng CPU time lớn hơn elapsed.

**Câu 9.** Vì sao parser chỉ tìm chuỗi `GC(` rồi đếm dòng là sai?  
**Đáp án:** Cùng GC ID có start, summary, heap, CPU và phase details; một ID có nhiều lines.

**Câu 10.** Muốn lưu GC log và xoay vòng thì làm thế nào?  
**Đáp án:** Dùng `-Xlog:gc*:file=...:time,uptime,level,tags:filecount=N,filesize=20M`, tạo thư mục trước và thiết lập policy retention.

**Câu 11.** Muốn xem logging configuration của JVM đang chạy dùng gì?  
**Đáp án:** `jcmd PID VM.log list`, và xem trợ giúp cụ thể với `jcmd PID help VM.log`.

**Câu 12.** Vì sao không dùng parser G1 y nguyên cho ZGC?  
**Đáp án:** Collector có log vocabulary, phase names và định dạng summary khác; phải kiểm tra đúng runtime/phiên bản.

**Câu 13.** Log GC có thể giải thích mọi request latency spikes không?  
**Đáp án:** Không. Cần đối chiếu safepoint, CPU, thread scheduling, I/O, lock contention và request tracing.

**Câu 14.** Nếu log có 100 Young GCs nhanh, điều đó chứng minh ứng dụng có leak?  
**Đáp án:** Không. Có thể chỉ là allocation rate cao với short-lived objects; leak cần liveness/retained heap evidence.

**Câu 15.** Tại sao phải ghi rõ JDK version khi báo cáo pause distribution?  
**Đáp án:** Collector behavior, log details, ergonomics và format có thể đổi qua JDK/vendor; kết quả chỉ có ý nghĩa với môi trường xác định.

## 17. Tổng kết

```text
JVM Unified Logging (Java 11+)
  -Xlog:<tags>[=level]:<output>:<decorators>:<output-options>
              |
              v
       [time][uptime][level][tags] GC(n) ...
              |
     +--------+----------+------------------+
     |                   |                  |
  Pause Young/Mixed    Concurrent ...    heap/cpu/phases/safepoint
     |                   |                  |
   STW summary       KHÔNG tự xem STW    Thông tin để giải thích
     |                   |                  |
     +-------------------+------------------+
                         |
                         v
        Group theo GC ID, lọc đúng pause summaries
                         |
                         v
           Count/max/p95/p99/total pause duration
                         |
                         v
      Đối chiếu request tracing, heap, GC & system CPU
```

**Nguyên tắc rút gọn:**

1. Bắt đầu bằng **`-Xlog:gc*`** và **`safepoint`** khi cần tìm nguyên nhân latency.
2. Đọc đúng **decorators → GC ID → pause/cycle type → before/after heap → duration**.
3. Đếm các **pause summaries** đã hoàn tất, không đếm mọi dòng chứa GC ID.
4. Không nhầm **concurrent cycle duration** với **STW pause time**.
5. Dùng `gc+phases=debug` và `gc+cpu=info` để giải thích các pause bất thường.
6. Không biến `MaxGCPauseMillis` hay một dòng heap reduction thành kết luận về SLA hoặc leak.
7. Bảo đảm logs có rotation, timestamps, đủ dữ liệu và không gây overhead quá lớn.
8. Luôn ghi rõ collector/JDK và kiểm chứng bằng metrics của ứng dụng.

Cơ chế **`-Xlog` và cách tư duy trên vẫn áp dụng hiện nay**. Các chi tiết riêng của G1 được trình bày đúng phạm vi Java 11+, còn collector khác phải dựa trên log và tài liệu của **runtime thực tế**.

### Tài liệu tham khảo chính thức còn áp dụng

- [Oracle Java SE 11 — java command: Enable Logging with JVM Unified Logging Framework](https://docs.oracle.com/en/java/javase/11/tools/java.html)
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158)
- [OpenJDK JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271)
- [Oracle Java SE 11 — G1 Garbage Collector: phases, STW và concurrent](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-g1-garbage-collector3.html)
- [Oracle Java SE 11 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-garbage-collector-tuning1.html)
- [Oracle Java SE 11 — jcmd: VM.log (list, what, output, decorators, rotate)](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html)
- [Oracle Java SE 25 — java unified logging command vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle Java SE 26 — G1 GC tuning và gc+cpu=info](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
