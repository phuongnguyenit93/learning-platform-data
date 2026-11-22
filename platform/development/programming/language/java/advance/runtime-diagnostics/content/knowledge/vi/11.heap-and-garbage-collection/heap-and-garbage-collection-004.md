# 11.4 Đọc GC log theo collector đang dùng thay vì áp một mô hình vùng nhớ cố định

## 1. Vấn đề cần giải quyết

GC log là nhật ký các hoạt động thu gom rác của JVM: thời điểm, nguyên nhân, pha xử lý, thời gian tạm dừng ứng dụng và một số thống kê bộ nhớ. **Cùng một dòng “GC” không mang cùng ý nghĩa trên mọi garbage collector.** Cách đọc đúng bắt đầu bằng việc xác nhận JVM/JDK và collector đang chạy, sau đó mới dùng thuật ngữ, trạng thái và giới hạn của collector đó để giải thích log.

Không nên mặc định heap của mọi JVM đều là ba vùng vật lý cố định “Eden → Survivor → Old”, rồi suy ra rằng mọi lần GC đều là “minor GC” hoặc “full GC”. Mô hình này hữu ích để nhập môn collector phân thế hệ truyền thống, nhưng:

- **Serial/Parallel** quản lý young/old theo cách phù hợp với thuật toán của chúng và thường thực hiện thu gom trong các khoảng *stop-the-world* (STW).
- **G1** vẫn có khái niệm young/old, nhưng heap được chia thành nhiều **region**; vai trò eden, survivor, old có thể được gán cho các region khác nhau theo thời gian. Nó dùng young collection, mixed collection và concurrent marking.
- **ZGC** dành phần lớn công việc cho các pha concurrent. Với **JDK 21**, cần phân biệt ZGC một thế hệ (khi chỉ bật `-XX:+UseZGC`) và **Generational ZGC** (khi bật thêm `-XX:+ZGenerational`).
- **Shenandoah trong JDK 21** là collector concurrent, không phân thế hệ theo kiểu young/old truyền thống; khả năng sử dụng phụ thuộc bản phân phối JDK và nền tảng.

> Phạm vi: chủ yếu là HotSpot/JDK 17–21, lấy JDK 21 làm mốc cho các lựa chọn ZGC. Tên pha, tag, cấu trúc dòng và cờ hỗ trợ có thể đổi giữa bản JDK, nhà phân phối và chế độ collector. Luôn đối chiếu phiên bản thực tế, không suy diễn từ ví dụ minh họa.

### Sau bài này, người đọc có thể

1. Xác nhận collector và cấu hình JVM đã tạo ra một GC log.
2. Phân biệt **GC pause**, **concurrent phase**, **GC cycle** và **heap occupancy**.
3. Đọc các sự kiện đặc trưng của Serial/Parallel, G1, ZGC và Shenandoah mà không ép tất cả về một sơ đồ vùng nhớ.
4. Đánh giá dấu hiệu áp lực cấp phát, lượng đối tượng còn sống, Full/degenerated GC, allocation stall và tương quan với độ trễ ứng dụng.
5. Đưa ra giả thuyết có thể kiểm chứng bằng log cùng số liệu JVM/OS, thay vì kết luận rò rỉ bộ nhớ chỉ từ một dòng GC.

## 2. Xác định bối cảnh **trước khi** phân tích một dòng

### 2.1. Phiên bản Java, collector và thông số heap

Khi có quyền truy cập JVM đang chạy, dùng các lệnh sau (thay `12345` bằng PID thật):

```bash
java -version
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 VM.log list
```

- `java -version` mô tả JDK được gọi trong terminal hiện tại; **có thể khác** JDK của tiến trình đang điều tra.
- `VM.command_line` cho biết lệnh khởi chạy tiến trình, bao gồm các lựa chọn `-XX:+Use...GC` nếu được truyền.
- `VM.flags` cho biết trạng thái cờ JVM ở tiến trình đó, kể cả các lựa chọn đã được JVM quyết định tự động. Lệnh và output phụ thuộc JDK; đối chiếu thêm dòng khởi tạo GC trong log.
- `GC.heap_info` là ảnh chụp cấu trúc/thống kê heap mà JVM hỗ trợ tại thời điểm gọi, không phải lịch sử đầy đủ.
- `VM.log list` giúp kiểm tra cấu hình Unified Logging hiện hành. `jcmd` cần quyền attach phù hợp và JDK có công cụ này.

Ví dụ log khởi động thường có dòng đại loại `[info][gc] Using G1`, `Using Parallel`, `Using Serial`, `Using ZGC` hoặc `Using Shenandoah`. **Đừng xác định collector bằng việc thấy từ “young”, “old” hay “heap” xuất hiện ngẫu nhiên trong một dòng.**

Một số lựa chọn minh họa cho **JDK 21**:

| Collector/chế độ | Cờ chọn điển hình | Cách hiểu heap và nhịp GC |
| --- | --- | --- |
| Serial | `-XX:+UseSerialGC` | Young/old, công việc thu gom chủ yếu STW và tuần tự |
| Parallel | `-XX:+UseParallelGC` | Young/old, thu gom STW với nhiều GC worker; ưu tiên thông lượng |
| G1 | `-XX:+UseG1GC` | Young/old là vai trò của các region; young/mixed pauses và concurrent marking |
| ZGC một thế hệ (JDK 21) | `-XX:+UseZGC` | Không áp sơ đồ Eden/Survivor/Old truyền thống; nhiều pha concurrent |
| Generational ZGC (JDK 21) | `-XX:+UseZGC -XX:+ZGenerational` | Phân biệt thu gom thế hệ trẻ/già theo thuật toán ZGC; vẫn có concurrent work |
| Shenandoah (JDK 21) | `-XX:+UseShenandoahGC` | Concurrent marking/evacuation/update references; không mặc định young/old |

G1 là lựa chọn mặc định phổ biến của HotSpot JDK 21, nhưng quyết định thực tế có thể phụ thuộc môi trường, kích thước máy, bản JDK hoặc cờ khởi chạy. Đặc biệt, **không áp mặc định ZGC của JDK mới lên JDK 21**; xác nhận `ZGenerational` từ cấu hình khi phân tích log.

### 2.2. Bật Unified Logging đúng mục tiêu

Ví dụ chạy ứng dụng có ghi sự kiện GC và safepoint ra file; có thể dùng nguyên một dòng lệnh trên terminal:

```bash
java -Xms256m -Xmx256m -Xlog:gc*,safepoint=info:file=gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20m -jar app.jar
```

Ý nghĩa:

- `gc*` nhận các nhóm tag chứa `gc`; mức mặc định là `info`. `safepoint=info` thêm thông tin safepoint. Tag `gc,heap` hoặc `gc,phases` chỉ xuất hiện khi JVM có phát log cho tag/mức tương ứng.
- `time,uptime,level,tags` là các phần thông tin đi kèm (*decorators*); `uptime` thuận tiện để dựng lại thứ tự, `time` thuận tiện khi đối chiếu APM/request log.
- `%p` là PID và `%t` là thời điểm JVM khởi động trong tên file, giúp tránh trộn log nhiều tiến trình.
- `filecount=5,filesize=20m` cấu hình xoay vòng file; cần giữ đủ khoảng thời gian xảy ra sự cố. Các con số kích thước chỉ là mục tiêu gần đúng.
- `-Xms`/`-Xmx` trong ví dụ là tham số thí nghiệm; dùng giá trị phù hợp với ứng dụng thật. Heap tối đa không đồng nghĩa giới hạn bộ nhớ RSS/container.

Khi cần tìm lý do chọn kích thước vùng hay thời gian pha, có thể tăng có chọn lọc:

```bash
java -Xlog:gc*=info,gc+heap=debug,gc+ergo=debug:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=20m -jar app.jar
```

`-Xlog:help` liệt kê mức và tag mà **JDK đang dùng** hỗ trợ. Mức `debug`/`trace` làm log lớn hơn và có thể tăng overhead; chỉ bật đủ để trả lời câu hỏi cụ thể. Thông thường `-Xlog:gc` là mức khảo sát ban đầu, `-Xlog:gc*` cho bối cảnh rộng hơn. Đối với ứng dụng đang chạy, có thể xem/điều chỉnh cấu hình log qua `jcmd ... VM.log` khi quyền và phiên bản cho phép.

## 3. Giải mã cú pháp, không vội kết luận

Ví dụ **giả lập về hình dạng** một dòng G1 (số liệu được đặt để giải thích cú pháp, không phải output bảo đảm của chương trình phía dưới):

```text
[2026-10-29T10:30:00.000+0700][12.345s][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 120M->48M(256M) 6.700ms
```

| Thành phần | Đọc như thế nào | Không được suy ra |
| --- | --- | --- |
| `2026-...` | Thời gian theo đồng hồ của JVM/máy | Mọi đồng hồ service đều đồng bộ tuyệt đối |
| `12.345s` | Uptime JVM tại sự kiện | Ứng dụng đã nhận request đúng từng ấy giây |
| `info`, `gc` | Mức log và tag set | Tất cả pha/cause đã được ghi ở mức này |
| `GC(12)` | ID để liên kết các bản ghi thuộc sự kiện/chu kỳ GC | Là request ID, thread ID hoặc “12 lần Full GC” |
| `Pause Young ...` | Tên sự kiện theo **G1**; có một khoảng STW | Cứ thấy `Young` thì trên mọi collector đều có một Eden vật lý cố định |
| `120M->48M(256M)` | Heap sử dụng trước → sau; dung lượng heap được trình bày trong ngữ cảnh dòng này | Bộ nhớ RSS giảm đúng 72 MB, hay `256M` nhất thiết là `-Xmx` |
| `6.700ms` | Thời lượng được báo cho sự kiện pause | Toàn bộ concurrent cycle, hoặc 100% thời gian gián đoạn request |

Các dòng `[gc,heap]`, `[gc,phases]` cùng `GC(12)` có thể bổ sung các giai đoạn và thay đổi vùng. Cần đọc **cả cụm sự kiện**, không kết luận từ một con số `before->after`.

Phân biệt bốn khái niệm:

- **STW pause:** ứng dụng phải dừng ở một pha GC; tác động trực tiếp đến latency, nhưng mức tác động lên từng request còn phụ thuộc thời điểm request.
- **Concurrent phase:** GC và ứng dụng có thể cùng chạy; thời lượng pha có thể dài hơn pause nhiều lần. Đây vẫn là chi phí CPU/băng thông bộ nhớ, nhưng **không có nghĩa ứng dụng dừng trong toàn bộ thời lượng đó**.
- **GC cycle:** chuỗi các pha/collection liên quan đến một lượt công việc. Trên collector concurrent, một cycle có thể gồm nhiều đoạn concurrent và pause; trên G1 cũng có nhiều young/mixed collection quanh concurrent marking.
- **Live set / post-GC occupancy:** lượng heap còn bị giữ sau thu gom. Chỉ là một tín hiệu về đối tượng đang sống, không tự chứng minh memory leak. Các bộ đệm, cache, class metadata, direct buffer và native memory có vòng đời riêng.

## 4. Đọc theo collector đang chạy

### 4.1. Serial và Parallel: phân thế hệ nhưng STW là trọng tâm

Với Serial/Parallel, thường cần quan sát:

- **Young GC:** cố gắng lấy lại bộ nhớ chứa nhiều đối tượng sống ngắn. Một cause như `Allocation Failure` có thể chỉ là lý do bình thường để kích hoạt young collection, **không tự đồng nghĩa lỗi cấp phát hay sắp `OutOfMemoryError`**.
- **Full GC / Old collection:** thường tốn kém hơn, có thể liên quan áp lực bộ nhớ cũ, ergonomics, explicit GC hoặc tình huống khác. Đọc **cause** và heap trước/sau để biết bối cảnh.
- **Promotion và survivor:** đối tượng sống qua lần young GC có thể được chuyển đến survivor/old; nếu mức sử dụng old sau GC liên tục tăng, cần điều tra retention và tốc độ cấp phát.
- **Parallel GC có nhiều worker** nhưng các pha thu gom thông thường vẫn là STW. “Parallel” không có nghĩa “concurrent với application”.

Dạng log minh họa (tên và số tùy bản JDK):

```text
GC(7) Pause Young (Allocation Failure) 90M->28M(128M) 12.300ms
GC(8) Pause Full (Ergonomics) 118M->74M(128M) 95.600ms
```

Câu hỏi nên đặt ra: Full GC có lặp lại không? Sau Full GC heap còn bao nhiêu? Thời gian pause có vượt ngân sách độ trễ? Đối tượng sống dài hạn có gia tăng qua nhiều chu kỳ không? Đừng áp “mixed collection” của G1 vào Parallel chỉ vì cả hai đều có old generation.

### 4.2. G1: đọc **region và collection set**, không tưởng tượng ba khối liên tục

G1 phân heap thành các **region**. Một region có thể đóng vai trò eden, survivor, old hoặc humongous; các region cùng vai trò không bắt buộc liền nhau. Hai loại pause quen thuộc:

- **`Pause Young (Normal)`:** chọn một *collection set* gồm young regions; live objects được di chuyển sang survivor hoặc old regions. Eden bị làm trống sau collection **không đồng nghĩa tất cả đối tượng trong eden đã chết**.
- **`Pause Young (Mixed)`:** sau khi concurrent marking xác định region phù hợp, G1 có thể thu gom một số **old regions cùng young regions**. “Mixed” không phải Full GC.
- **`Concurrent Start`, `Concurrent Mark Cycle`, `Remark`, `Cleanup`:** mô tả các mốc phát hiện đối tượng còn sống, chuẩn bị chọn region old để thu gom. Một số pha là concurrent, còn initial-mark/remark và phần cleanup có các pause STW. Không cộng toàn bộ thời gian concurrent vào tổng GC pause.
- **`Humongous regions`:** đối tượng lớn (xấp xỉ từ nửa kích thước một region theo quy tắc G1) có xử lý riêng. Nhiều humongous allocations có thể gây áp lực fragmentation/khởi động marking sớm.
- **`Pause Full` hoặc `Evacuation Failure`:** cảnh báo cần xem kỹ việc thiếu chỗ di chuyển đối tượng, tốc độ cấp phát, thời điểm marking và số region trống; không phải phản ứng bắt buộc của mọi lần “old đầy”.

Ví dụ diễn giải nhiều dòng cùng sự kiện (**minh họa, không phải transcript thực đo**):

```text
GC(20) Pause Young (Normal) (G1 Evacuation Pause) 160M->72M(256M) 8.000ms
GC(20) Eden regions: 58->0(64)
GC(20) Survivor regions: 4->5(8)
GC(20) Old regions: 32->34
```

Diễn giải: G1 vừa có young evacuation pause 8 ms. Eden regions đã được giải phóng; một phần đối tượng có thể sống sót và được đặt trong survivor hoặc thăng lên old. Old region count tăng từ 32 lên 34 **không tự chứng minh leak**; cần xem chuỗi nhiều lần GC, lượng old còn sống và tải ứng dụng. Số region trong các dòng minh họa không phải số MB; kích thước region phải lấy từ log khởi tạo/cấu hình.

Nếu thấy:

```text
Pause Young (Concurrent Start) ...
Concurrent Mark Cycle ...
Pause Remark ...
Pause Cleanup ...
Pause Young (Mixed) ...
```

hãy đọc đây là diễn biến đặc trưng của G1: kích hoạt/conduct marking, hoàn thiện thông tin liveness, rồi chọn các old region để thu gom dần. Không đổi các dòng này thành “Minor → Major” theo khung Serial GC.

**Cách tiếp cận khi G1 có pause dài:** kiểm tra tần suất, phân vị pause; loại pause young/mixed/full; `gc+phases` để tìm phần mất thời gian (ví dụ scan remembered set, object copy); `gc+heap` xem eden/survivor/old/humongous; đầu vào như allocation rate, live set và số CPU sẵn có. Mục tiêu `-XX:MaxGCPauseMillis` là **soft goal**, không phải bảo đảm mọi pause nhỏ hơn ngưỡng.

### 4.3. ZGC: phân biệt phiên bản và **pause với concurrent work**

ZGC hướng tới pause ngắn bằng cách thực hiện phần lớn công việc đồng thời với ứng dụng. Trong **JDK 21**:

- `-XX:+UseZGC` chọn chế độ **non-generational**; không tìm “Eden/Survivor/Old” như bắt buộc phải có.
- `-XX:+UseZGC -XX:+ZGenerational` chọn **Generational ZGC**, có logic thu gom theo thế hệ; tên sự kiện có thể phản ánh các chu kỳ trẻ/già. Đừng giả định cách gắn nhãn giữa JDK 21 và JDK khác giống nhau.
- Các thông báo như **`Pause Mark Start`/`Pause Mark End`** (tùy chế độ), **`Concurrent ...`**, **`Garbage Collection (...)`** và thống kê heap cần đặt trong cùng cycle. Một cycle mất hàng chục hoặc hàng trăm mili giây **không có nghĩa** ứng dụng dừng liên tục trong chừng đó thời gian.
- **Allocation Stall** hoặc tín hiệu GC không theo kịp tốc độ cấp phát có thể quan trọng hơn một pause đơn lẻ. Xem mức heap được giữ lại, `-Xmx`, `-XX:SoftMaxHeapSize` nếu dùng, tốc độ allocation và ngân sách CPU cho GC workers.
- ZGC có thể thay đổi committed/uncommitted memory; hãy phân biệt **heap used**, **heap committed**, **heap reserved/max** và **RSS**. Một lần reclaim object không nhất thiết lập tức làm giảm RSS.

Câu hỏi chính khi đọc ZGC: collector có đang hoàn thành công việc concurrent đủ nhanh để cung cấp chỗ cho allocation mới? Có allocation stall hay áp lực CPU không? Pause STW thực tế dài bao nhiêu? Không cố “suy ra Eden bị đầy” từ một log không có Eden.

### 4.4. Shenandoah JDK 21: concurrent evacuation và đường thoát khi thiếu bộ nhớ

Shenandoah trên các bản JDK 21 có hỗ trợ là collector concurrent, **không phân thế hệ** như Serial/Parallel. Các pha có thể gồm:

- `Pause Init Mark` và `Pause Final Mark`: mốc STW tương ứng của marking.
- `Concurrent marking`, `Concurrent evacuation`, `Concurrent update references` hoặc các pha cleanup: công việc phần lớn chạy bên cạnh application.
- **Degenerated GC**: một phần công việc concurrent phải chuyển sang STW để hoàn tất khi không theo kịp; **Full GC** là đường xử lý nặng hơn. Đây là dấu hiệu nên điều tra áp lực cấp phát, heap headroom và khả năng cấp CPU.
- **Pacing/heuristics**: collector có thể làm chậm một số allocation để tránh hết chỗ. Độ trễ ứng dụng có thể thay đổi ngay cả khi các pause được ghi nhận còn ngắn.

Đọc theo **pha mark → evacuate → update references**, số lần fallback, áp lực cấp phát và các pause; không yêu cầu phải xuất hiện chỉ số “Old generation after GC”. Kiểm tra khả năng hỗ trợ của bản JDK đang dùng trước khi áp cờ `-XX:+UseShenandoahGC`.

## 5. Phân tích có hệ thống: từ log đến giả thuyết

### 5.1. Trình tự đọc một cửa sổ sự cố

1. **Chốt cửa sổ thời gian:** request latency/p99 tăng lúc nào, node/pod nào, PID và JVM uptime tương ứng? Tránh nối log của các tiến trình hoặc container đã restart.
2. **Định danh JVM/collector:** version, cờ chọn GC, heap min/max, CPU quota, container memory limit, dòng `Using ...`.
3. **Phân loại sự kiện:** pause STW, concurrent phase/cycle, Full/degenerated GC, allocation stall, explicit GC. Giữ nguyên tên gốc của collector.
4. **Đo tác động:** số pause mỗi phút; thời lượng max/p95/p99 của **pause**; tổng thời gian STW trong cửa sổ; thời gian và tần suất các concurrent cycle **ghi riêng**. Phân vị GC pause không thay thế phân vị request latency.
5. **Đọc xu hướng heap:** used trước/sau GC theo thời gian, sức chứa heap, live set ước lượng, số old/humongous regions nếu là G1; với ZGC/Shenandoah đọc chỉ số tương ứng chúng thực sự ghi.
6. **Kiểm tra cơ chế:** G1 có kịp concurrent marking trước khi old pressure tăng? ZGC/Shenandoah có allocation stall/degenerated/full? Parallel/Serial có Full GC lặp dày? Thời gian safepoint có vượt riêng thời gian GC pause không?
7. **Đối chiếu dữ liệu ngoài GC:** allocation rate, heap histogram/JFR khi có điều kiện, CPU/GC threads, RSS/native memory, container OOMKilled, request trace, thread dumps. Chỉ kết luận khi các nguồn số liệu nhất quán.

Có thể ghi kết quả điều tra vào bảng nhỏ:

| Quan sát đã kiểm chứng | Giả thuyết hợp lý | Bằng chứng bổ sung cần tìm |
| --- | --- | --- |
| G1 young pauses dày nhưng post-GC heap ổn định | Tải tạo nhiều đối tượng sống ngắn | Allocation rate, JFR allocations, CPU và p99 |
| G1 mixed pauses tăng; sau Full GC mức sử dụng vẫn cao | Live set lớn, cache/retention hoặc bộ nhớ cấp phát sát giới hạn | Heap histogram/dump, kích thước heap, old/humongous regions |
| ZGC concurrent cycles dài, có allocation stall | Allocation lấn át khả năng reclaim hoặc CPU/heap headroom thiếu | Logs của stall, allocation rate, CPU quota, committed/used heap |
| Shenandoah chuyển sang degenerated/full | Concurrent cycle không theo kịp áp lực bộ nhớ | Thời điểm fallback, headroom, pacing và GC heuristics |
| Request chậm nhưng GC pauses rất ngắn | Nguyên nhân có thể ở CPU, safepoint khác, lock, I/O hoặc mạng | Request tracing, thread/CPU profiling, safepoint log |

Những cột “giả thuyết” **chưa phải kết luận**. Ví dụ `after-GC` tăng sau ba sự kiện có thể là cache đang warm up; cần nhìn cả khoảng vận hành ổn định và biết retention được thiết kế ra sao.

### 5.2. Ba tình huống hay bị đọc sai

**Tình huống A — “Old regions tăng, chắc chắn leak.”** G1 có thể chuyển đối tượng sống lâu từ young sang old; old tăng trong giai đoạn warm up là bình thường. Hãy so sánh mức sau những lần reclaim có khả năng thu hồi old (mixed/full), xu hướng qua nhiều chu kỳ, lưu lượng request/cache và dữ liệu heap object. Không dùng riêng số region old trong một young pause để kết luận leak.

**Tình huống B — “Concurrent Mark Cycle 850 ms nghĩa là request đứng 850 ms.”** Phần lớn concurrent marking chạy song song với application; chỉ các pha `Pause ...` cụ thể mới phản ánh STW của GC. Đồng thời, concurrent work vẫn cạnh tranh CPU/băng thông bộ nhớ, nên latency có thể xấu đi **gián tiếp**. Cần đặt cạnh pause/safepoint và trace request.

**Tình huống C — “Chỉ có 2 ms pause nên GC không liên quan.”** Với ZGC/Shenandoah, allocation stall, pacing, CPU contention hoặc degenerated/full fallback vẫn có thể ảnh hưởng latency. Phải xem cả tín hiệu concurrent và tài nguyên máy, không chỉ max pause.

## 6. Thí nghiệm Java 17+/21 có thể tự chạy

Tạo file `GcLogDemo.java` với nội dung dưới đây. Chương trình liên tục cấp phát mảng 64 KiB, giữ lại tối đa 64 mảng gần nhất và đọc byte của mảng vừa loại ra để tránh biến toàn bộ thao tác thành cấp phát không quan sát được. Đây là workload minh họa, không đại diện benchmark production.

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class GcLogDemo {
    public static void main(String[] args) {
        Deque<byte[]> recent = new ArrayDeque<>();
        long checksum = 0;

        for (int i = 0; i < 8_000; i++) {
            byte[] block = new byte[64 * 1024];
            block[0] = (byte) i;
            recent.addLast(block);

            if (recent.size() > 64) {
                checksum += recent.removeFirst()[0] & 0xff;
            }
        }

        System.out.println("retained=" + recent.size()
                + ", checksum=" + checksum);
    }
}
```

Biên dịch và chạy với G1:

```bash
javac GcLogDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info:file=g1.log:time,uptime,level,tags:filecount=3,filesize=10m GcLogDemo
```

**Stdout của chương trình** (không tính log GC ghi riêng vào file):

```text
retained=64, checksum=1011840
```

Giải thích: trong 8.000 vòng lặp, chỉ 64 mảng cuối còn trong deque; 7.936 mảng được lấy ra để cộng byte đầu không dấu. Mẫu byte 0..255 lặp đúng 31 lần nên tổng là `31 × (0 + ... + 255) = 1.011.840`. Kích thước heap 64 MiB tạo điều kiện quan sát nhiều lần GC; tần suất, số ID, tên sự kiện và pause phụ thuộc JDK/máy, **không có stdout GC cố định**.

Lần lượt thử trên bản JDK hỗ trợ, cùng workload và cấu hình heap:

```bash
java -Xms64m -Xmx64m -XX:+UseParallelGC -Xlog:gc*=info:file=parallel.log:uptime,level,tags GcLogDemo
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info:file=g1-again.log:uptime,level,tags GcLogDemo
```

Với **JDK 21** và các collector được build hỗ trợ, có thể thử thêm ZGC/Shenandoah, nhưng cần kiểm tra cờ, heap tối thiểu và tài nguyên platform trước khi so sánh:

```bash
java -Xms64m -Xmx64m -XX:+UseZGC -Xlog:gc*=info:file=zgc21.log:uptime,level,tags GcLogDemo
java -Xms64m -Xmx64m -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*=info:file=zgc-gen21.log:uptime,level,tags GcLogDemo
java -Xms64m -Xmx64m -XX:+UseShenandoahGC -Xlog:gc*=info:file=shenandoah21.log:uptime,level,tags GcLogDemo
```

**Bài tập đọc log:** với mỗi file, tìm dòng nhận diện collector, liệt kê tên các sự kiện, tách pause STW ra khỏi concurrent work, ghi nhận thời gian pause lớn nhất và xu hướng heap sau collection. Sau đó nêu **hai điểm khác nhau trong cách diễn giải**, chẳng hạn G1 có young/mixed region phases còn ZGC một thế hệ của JDK 21 không có sơ đồ Eden/Old để áp trực tiếp. Không so sánh “collector nào tốt nhất” chỉ từ demo quá nhỏ này; một thí nghiệm tin cậy cần workload thật, warm-up, nhiều lần đo, cùng giới hạn CPU/RAM và tiêu chí latency/throughput.

## 7. Lỗi phổ biến và cách tự kiểm tra

| Nhận định sai | Cách sửa |
| --- | --- |
| “Mọi collector đều có Eden, Survivor, Old vật lý cố định.” | Dùng sơ đồ collector đang chạy: region roles của G1, non-generational hay generational ZGC, concurrent Shenandoah. |
| “`Allocation Failure` trong young GC là `OutOfMemoryError`.” | Đó có thể là trigger collection thông thường; phải tìm bằng chứng OOME, repeated failures hoặc không reclaim đủ chỗ. |
| “`Concurrent` = ứng dụng dừng.” | Chỉ các pha STW/pause cụ thể dừng application; concurrent work vẫn có thể gây tranh chấp tài nguyên. |
| “`Pause Young (Mixed)` là Full GC.” | Với G1, mixed chọn một phần old regions cộng young regions; Full GC có cơ chế/phạm vi khác. |
| “`before->after(capacity)` là RAM của process.” | Phần lớn là thống kê Java heap trong ngữ cảnh collector; RSS/native/direct/metaspace cần công cụ riêng. |
| “Một dòng `Old regions` tăng chứng minh leak.” | Cần xem nhiều chu kỳ, warm-up, live set và heap object retention. |
| “Tổng thời gian tất cả dòng `gc` là GC pause time.” | Có dòng start/end/phases lặp ý nghĩa và pha concurrent; chỉ cộng sự kiện pause theo đúng định nghĩa, tránh double count. |
| “Cờ collector mặc định giống nhau ở mọi JDK.” | Đối chiếu JDK cụ thể, startup log và VM flags; đặc biệt chế độ ZGC giữa các release. |
| “GC log giải thích toàn bộ latency.” | Ghép với safepoint, CPU, request traces, I/O, lock và số liệu OS/container. |

## 8. Checklist kết luận cho một GC incident

- [ ] Ghi rõ **JDK version, vendor/build, PID, collector, collector mode, `-Xms`/`-Xmx`, CPU và container limits**.
- [ ] Chỉ ra **đúng loại sự kiện** trong log (young/mixed/full, concurrent cycle, allocation stall, degenerated...) và phạm vi pause thực tế.
- [ ] Thống kê pause theo **cửa sổ thời gian của sự cố**, phân biệt concurrent duration và STW; dùng timestamp/uptime nhất quán.
- [ ] Đối chiếu **heap used trước/sau GC**, live-set trend và số liệu riêng collector (G1 region/humongous, ZGC stalls, Shenandoah fallback...).
- [ ] Phân biệt **quan sát**, **giả thuyết** và **bằng chứng bổ sung** trước khi đề xuất tăng heap, đổi collector hay sửa ứng dụng.
- [ ] Nếu cần thay đổi cấu hình, đo lại bằng **cùng workload/giới hạn tài nguyên**, so sánh cả throughput, p95/p99 latency, CPU và footprint.

**Nguyên tắc cốt lõi:** bắt đầu bằng “Collector nào, JDK nào, pha nào, pause hay concurrent, heap metric nào?” rồi mới trả lời “Điều gì đang làm ứng dụng chậm hoặc cạn bộ nhớ?”. Không dùng một mô hình vùng nhớ cố định để gán ý nghĩa cho mọi GC log.

## Tài liệu đối chiếu

- Oracle JDK 21 — [Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html): cơ chế và lựa chọn Serial, Parallel, G1, ZGC.
- Oracle JDK 21 — [Garbage-First Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html): region, young/mixed collection, concurrent marking.
- Oracle JDK 21 — [java command / Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): cú pháp `-Xlog`, tags, decorators, rotation và cờ GC.
- Oracle JDK 21 — [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.command_line`, `VM.flags`, `GC.heap_info`, `VM.log`.
- OpenJDK/Inside Java — [Introducing Generational ZGC](https://inside.java/2023/11/28/gen-zgc-explainer/): phân biệt chế độ ZGC trong JDK 21.
- Red Hat OpenJDK 21 — [Using Shenandoah GC](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/21/html-single/using_shenandoah_garbage_collector_with_red_hat_build_of_openjdk_21/index): phases, logging, heuristics và giới hạn môi trường.