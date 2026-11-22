# 13.5 Thiết lập baseline rồi đọc `summary.diff` hoặc `detail.diff`

## Mục tiêu bài học

Khi bộ nhớ của tiến trình Java tăng, một ảnh chụp tức thời không đủ để biết **bộ nhớ tăng từ khi nào, ở nhóm nào và có tiếp tục tăng khi tải đã trở về bình thường không**. Native Memory Tracking (NMT) của HotSpot có cơ chế **baseline** để so sánh lượng bộ nhớ JVM đang quản lý ở những thời điểm khác nhau.

Sau bài này, bạn có thể:

1. Bật mức NMT phù hợp ngay khi khởi động JVM và kiểm tra nó đã hoạt động.
2. Chọn thời điểm baseline sau warm-up, thu thập `summary.diff` theo các pha tải và đọc dấu `+`/`-` đúng nghĩa.
3. Dùng `detail.diff` để đi sâu từ nhóm bộ nhớ đang tăng tới các điểm cấp phát/ánh xạ bộ nhớ mà HotSpot ghi nhận.
4. Phân biệt `reserved`, `committed`, số lượng allocation và bộ nhớ vật lý RSS; nhận diện giới hạn của NMT.
5. Viết kết luận chẩn đoán có bằng chứng, tránh gọi mọi delta dương là native memory leak.

> **Phạm vi:** Bài tập trung vào đo biến động bộ nhớ native của **HotSpot JVM** bằng NMT trong Java 17+/21. NMT cũng liệt kê vùng Java Heap mà VM đã reserve/commit, nhưng không thay thế heap profiler, GC log hay phép đo RSS của hệ điều hành.

## 1. Baseline là gì, và tại sao cần diff?

NMT ghi nhận lượng bộ nhớ mà **bản thân HotSpot JVM** sử dụng/đặt chỗ, tổng hợp theo nhóm như `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Other` và `Native Memory Tracking`. Tên, cấu trúc nhóm và mức chi tiết có thể khác giữa bản JDK.

Khi gọi:

- `VM.native_memory summary`: xem **ảnh chụp hiện tại** theo nhóm.
- `VM.native_memory baseline`: lưu một **mốc tham chiếu** trong tiến trình JVM đang chạy.
- `VM.native_memory summary.diff`: xem giá trị hiện tại **và chênh lệch so với baseline gần nhất**, theo nhóm.
- `VM.native_memory detail.diff`: xem chênh lệch chi tiết hơn theo call site/vùng virtual memory nếu JVM đã bật mức `detail`.

Phân biệt ba thời điểm:

| Thời điểm | Sự kiện | Cách hiểu |
| --- | --- | --- |
| T0 | Ứng dụng warm-up xong; tạo baseline | Mốc để tính delta |
| T1 | Vừa chạy một vòng tải | `summary.diff` tại T1 cho `T1 - T0` |
| T2 | Đã giảm tải, queue xử lý xong | `summary.diff` tại T2 vẫn là `T2 - T0`, **không phải `T2 - T1`** |

**Baseline là phép so chênh lệch trong cùng một JVM, không phải ảnh chụp hệ điều hành hay chứng cứ leak.** Lần gọi `summary.diff`/`detail.diff` không tự đặt baseline mới. Gọi lại `baseline` sẽ **thay mốc cũ**; từ đó mọi diff mới được tính theo mốc vừa tạo. Khi JVM khởi động lại, baseline của tiến trình cũ không còn hiệu lực.

Một delta tăng chứng minh **mức sử dụng được NMT theo dõi ở thời điểm đo cao hơn mốc**, chưa chứng minh dữ liệu vô dụng hoặc không thể giải phóng. Ngược lại, delta gần 0 cũng không loại trừ các đỉnh tăng bộ nhớ tạm thời giữa hai lần đo.

## 2. Trước khi đo: bật NMT đúng cấp độ

NMT mặc định tắt; phải bật bằng cờ JVM khi **khởi động tiến trình**. Không thể dùng `jcmd` bật hoặc bật lại NMT đã tắt trên tiến trình đang chạy.

| Mức NMT | Cờ JVM | Đọc được | Khi nên dùng |
| --- | --- | --- | --- |
| Tắt | `-XX:NativeMemoryTracking=off` (mặc định) | Không có báo cáo NMT hữu ích | Khi không cần thu thập |
| Summary | `-XX:NativeMemoryTracking=summary` | Tổng hợp theo nhóm và `summary.diff` | Điều tra ban đầu, overhead thấp hơn detail |
| Detail | `-XX:NativeMemoryTracking=detail` | Tổng hợp, call site/vùng ánh xạ, `summary.diff` và `detail.diff` | Đã khoanh vùng vấn đề và cần tìm nguồn sâu hơn |

Ví dụ **khởi động ứng dụng JAR có thật** với mức summary:

```bash
java -XX:NativeMemoryTracking=summary -Xms256m -Xmx1g -jar app.jar
```

`app.jar` chỉ là tên minh họa; dùng JAR ứng dụng thực tế và giữ nguyên các cấu hình JVM khác của môi trường khi thiết kế thí nghiệm. Khi cần `detail.diff`, khởi động JVM **mới** với:

```bash
java -XX:NativeMemoryTracking=detail -Xms256m -Xmx1g -jar app.jar
```

NMT có chi phí: tài liệu Oracle JDK mô tả overhead hiệu năng khoảng **5–10%** khi bật, và tracking có tiêu thụ bộ nhớ riêng. Vì vậy phép đo NMT hữu ích để phân tích **xu hướng và phân bổ theo nhóm**, nhưng phải tính đến overhead, đặc biệt khi so với một tiến trình không bật NMT hoặc khi chạy production.

### Kiểm tra PID, mức NMT và khả năng attach

Trong terminal khác, dùng đúng JDK `jcmd` tương thích và quyền người dùng được phép attach vào tiến trình:

```bash
jcmd -l
jcmd 12345 VM.native_memory summary scale=KB
jcmd 12345 help VM.native_memory
```

**Thay `12345` bằng PID Java thực**, không chạy nguyên số minh họa. `jcmd -l` liệt kê các tiến trình Java có thể nhìn thấy; trong container, namespace PID và quyền attach có thể khác host. Nếu lệnh báo NMT không được bật, cần khởi động lại ứng dụng với cờ thích hợp. Nếu `detail.diff` không khả dụng vì mức tracking là `summary`, không thể nâng mức đó bằng `jcmd` trên JVM hiện tại.

## 3. Chọn baseline cho một phép đo có ý nghĩa

Điểm bắt đầu không nhất thiết là lúc vừa khởi động JVM. Class loading, JIT compilation, connection pools, cache khởi tạo và GC subsystem có thể làm các nhóm tăng nhanh trong warm-up; nếu baseline quá sớm, diff sau đó chủ yếu đo **khởi động** chứ không đo tác động của workload đang điều tra.

Quy trình có đối chứng:

1. **Cố định môi trường:** ghi JDK/vendor/version, GC, `-Xms`/`-Xmx`, cờ liên quan memory, container limit, số thread và phiên bản ứng dụng.
2. **Warm-up đến trạng thái ổn định:** xử lý một lượng request đại diện, xác nhận pool/cache/class loading tương đối ổn định; đây là trạng thái T0.
3. **Lưu báo cáo tuyệt đối trước mốc:** `summary` hoặc `detail` giúp đối chiếu khi đọc các delta.
4. **Tạo baseline một lần ở T0.** Ghi timestamp bên ngoài hoặc vào nhật ký thí nghiệm.
5. **Áp tải có kiểm soát:** lưu RPS, request đồng thời, kích thước payload, queue depth, class/session/cache count và hệ số thay đổi.
6. **Đọc diff định kỳ tại T1, T2…** mà không gọi lại baseline, để cùng so với T0.
7. **Hạ tải và chờ hoàn tất công việc đang chạy**, đọc T3. Nếu nhóm nào vẫn tăng, kiểm tra owner/lifecycle trước khi kết luận.
8. Chỉ **rebaseline** khi chủ động bắt đầu cửa sổ điều tra mới (ví dụ muốn đo riêng từ T2 đến T3); ghi rõ mốc đã đổi.

Thứ tự khuyến nghị là **baseline sau warm-up → đo tải ổn định → tăng tải → hạ tải → đo sau hồi phục**. Cùng một loại workload phải được lặp lại đủ lâu để phân biệt xu hướng tăng bền với allocation tạm thời.

### Chuỗi lệnh thực tế với mức `summary`

Giả sử JVM đã chạy với `-XX:NativeMemoryTracking=summary` và PID thật là `12345`. Các lệnh sau là ví dụ cho terminal Linux/macOS hoặc shell Bash:

```bash
PID=12345

# T0: ứng dụng đã warm-up, lưu ảnh chụp tuyệt đối.
jcmd "$PID" VM.native_memory summary scale=KB > nmt-t0-summary.txt

# Đặt mốc. Lệnh này làm mới baseline dùng cho các diff kế tiếp.
jcmd "$PID" VM.native_memory baseline

# T1: sau một pha tải ổn định.
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t1-summary.diff.txt

# T2: sau khi tăng tải nhưng không đổi baseline.
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t2-summary.diff.txt

# T3: hạ tải, đợi queue/task cần hoàn thành và đọc lại.
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t3-summary.diff.txt

# Xem giá trị tuyệt đối hiện tại khi cần giải thích delta.
jcmd "$PID" VM.native_memory summary scale=KB > nmt-t3-summary.txt
```

Phần ghi chú `T1/T2/T3` biểu diễn thao tác áp/hạ tải được thực hiện **giữa các lệnh**; bản thân những lệnh NMT không tạo workload, không chờ queue drain và không đo RSS. Trên PowerShell, thay cú pháp biến Bash bằng PID trực tiếp (ví dụ `jcmd 12345 ...`) hoặc biến PowerShell `$pidOfJava`, tránh dùng biến đặc biệt `$PID` của PowerShell.

**Vì sao chọn `scale=KB`?** Khi chênh lệch nhỏ, dùng MB/GB có thể làm số liệu bị làm tròn thành 0 ở một số mục. Lưu báo cáo dạng KB để so và chỉ đổi sang MB/GB khi trình bày. `scale` đổi đơn vị hiển thị, không đổi lượng bộ nhớ.

## 4. Đọc đúng `summary.diff`

NMT thường trình bày hai khái niệm độc lập:

| Trường | Ý nghĩa | Hiểu sai cần tránh |
| --- | --- | --- |
| `reserved` | Dung lượng **không gian địa chỉ ảo được dành trước** | Không đồng nghĩa RAM vật lý đã được sử dụng |
| `committed` | Dung lượng vùng nhớ VM đã **commit** theo cơ chế quản lý bộ nhớ | Không đồng nghĩa RSS, không phải lượng Java object còn sống |
| `malloc` | Bộ nhớ cấp phát qua cơ chế malloc mà HotSpot theo dõi | Không bao quát mọi thư viện native ngoài HotSpot |
| `mmap` | Vùng ánh xạ/đặt chỗ và commit có liên quan | Cần đọc reserved và committed riêng; không cộng chồng tùy tiện với tổng nhóm |
| `#` sau mục như `thread`, `classes`, `malloc` | Số luồng, lớp hoặc lần cấp phát được báo cáo theo ngữ cảnh | Không luôn là số Java object hay số request |

Ví dụ đầu ra **giả lập để luyện cách đọc**; đã rút gọn nhiều nhóm, không phải ảnh chụp của một ứng dụng cụ thể:

```text
Native Memory Tracking:

Total: reserved=4000000KB +65536KB, committed=500000KB +28672KB

-                 Java Heap (reserved=2097152KB, committed=262144KB)

-                    Thread (reserved=256000KB +32768KB,
                            committed=22000KB +4096KB)
                            (thread #250 +32)

-                     Class (reserved=1060000KB +8192KB,
                            committed=40000KB +6144KB)
                            (classes #6000 +900)

-                     Other (reserved=30000KB +16384KB,
                            committed=30000KB +16384KB)

... (các nhóm còn lại được lược bỏ)
```

Diễn giải **trên từng dòng**:

- `Total committed=500000KB +28672KB`: ở thời điểm đo NMT báo tổng committed là 500.000 KB, **cao hơn baseline 28.672 KB**; không có nghĩa “vừa tăng 28.672 KB kể từ lần diff trước”.
- `Thread reserved +32768KB` cùng `thread #250 +32`: hiện có thêm 32 luồng so với baseline và nhiều không gian stack/thread được đặt chỗ hơn. Đây là hướng kiểm tra thread pool, thread dump và vòng đời luồng. **Reserved tăng không chứng minh có 32 MB RAM đang resident**.
- `Class committed +6144KB` và `classes +900`: có thêm class được giữ/tải so với baseline; có thể là warm-up, nạp plugin/class động hợp lệ, hoặc class loader chưa được giải phóng. Đếm số class loader, class unload và kiểm tra metaspace trước khi gọi leak.
- `Other committed +16384KB`: nhóm `Other` tăng 16 MB. Đây là dấu hiệu để kiểm tra allocation phù hợp trong JVM, **không thể quy ngay cho direct buffer hoặc một thư viện cụ thể** chỉ vì tên nhóm.
- `Java Heap reserved` bằng giá trị cố định: có thể đơn giản là `-Xmx`/heap reservation ổn định. NMT không nói đối tượng Java nào còn sống; cần thêm GC/heap used nếu nghi giữ tham chiếu ở Java heap.

### Đọc dấu `+` và `-`

- `committed=12000KB +4096KB`: hiện tại 12.000 KB, **tăng ròng 4.096 KB so với mốc**.
- `committed=12000KB -2048KB`: hiện tại 12.000 KB, **giảm ròng 2.048 KB so với mốc**.
- `committed=12000KB` không có hậu tố delta trong một dòng diff: thường không có thay đổi được hiển thị ở độ phân giải đó.
- `classes #6000 +900`: hiện có 6.000 class theo cách đếm của báo cáo, cao hơn baseline 900 class.

Dấu `+`/`-` trên từng nhóm thể hiện **thay đổi ròng tại thời điểm lấy mẫu**, có thể gồm allocation và deallocation đã xảy ra trong khoảng. Không thể cộng các dòng con và dòng tổng của chính nhóm đó thành một tổng mới; chúng thường trình bày **cùng lượng bộ nhớ ở các mức phân rã khác nhau**. Tổng toàn JVM còn gồm các nhóm không xuất hiện trong trích đoạn.

### So sánh ba lần diff cùng baseline

Một bảng nhật ký **minh họa** (các delta đều so với T0, đơn vị MB; workload giả định):

| Mốc | Active threads | Delta Thread committed | Delta Class committed | Delta Other committed | Ý nghĩa cần kiểm tra |
| --- | ---: | ---: | ---: | ---: | --- |
| T0: baseline | 80 | 0 | 0 | 0 | Mốc tham chiếu |
| T1: tải đều | 100 | +3 | +2 | +12 | Tăng cùng workload |
| T2: tăng tải | 150 | +8 | +3 | +30 | Concurrency và allocation tăng |
| T3: tải trở về nền | 82 | +1 | +3 | +1 | Thread/Other gần hồi phục; Class vẫn giữ thêm 3 MB |

Kết luận sơ bộ hợp lý: hai nhóm `Thread` và `Other` có tính **đảo ngược theo tải**, nên chưa thấy bằng chứng giữ tăng liên tục sau hồi phục; `Class` còn cao hơn baseline cần đối chiếu class loading hợp lệ với class loader còn sống. **Không** suy rằng “Class +3 MB = leak” nếu thiếu bằng chứng các class đáng ra đã unload.

Nếu T3 vẫn giữ `Other +30 MB` dù queue đã trống, đó là **điểm nghi vấn**, chưa phải kết luận. Cần lặp thêm chu kỳ, xem `detail.diff` (nếu được bật) và kiểm chứng owner/allocator.

## 5. Khi nào dùng `detail.diff` và cách đọc

`summary.diff` giúp trả lời “**nhóm nào** tăng?”. Khi một nhóm liên tục tăng trong những lần đo có thể so sánh, `detail.diff` trả lời sâu hơn “**điểm cấp phát nào hoặc vùng địa chỉ ảo nào** thay đổi?”. Muốn dùng được báo cáo này, JVM phải khởi động với:

```bash
java -XX:NativeMemoryTracking=detail -Xms256m -Xmx1g -jar app.jar
```

Trong terminal khác, sau warm-up:

```bash
PID=12345
jcmd "$PID" VM.native_memory detail scale=KB > nmt-t0-detail.txt
jcmd "$PID" VM.native_memory baseline

# Sau khi chạy workload đã ghi nhận:
jcmd "$PID" VM.native_memory summary.diff scale=KB > nmt-t1-summary.diff.txt
jcmd "$PID" VM.native_memory detail.diff scale=KB > nmt-t1-detail.diff.txt
```

Với mức `detail`, bạn có thể đọc **cả** summary và detail. Nếu chỉ bật mức `summary`, không thể kỳ vọng `detail.diff` chỉ vì đã gọi `baseline`.

Một mảnh ví dụ **mô phỏng** nội dung call site (địa chỉ, tên hàm và lượng cấp phát chỉ mang tính minh họa):

```text
[0x00007fff01234567] ExampleHotSpotAllocator::allocate(...)
                 (malloc=20480KB type=Other +16384KB #480 +384)

[0x00007fff07654321] ExampleVMRegion::reserve(...)
                 (reserved=65536KB +32768KB, committed=8192KB +4096KB)
```

Cách tiếp cận:

1. Ở dòng `malloc`: 20.480 KB là tổng lượng hiện tại tại call site này; `+16384KB` là phần tăng so với baseline. `#480 +384` biểu thị số allocation đang được NMT báo cáo cho ngữ cảnh này, tăng 384, **không phải 384 Java object hoặc 384 request**.
2. Ở dòng vùng địa chỉ: phân biệt `reserved +32768KB` với `committed +4096KB`. Chỉ nhìn reserved rất dễ phóng đại tác động lên RAM thực.
3. Tìm **call site có delta committed/malloc tăng bền vững** qua những phép đo cùng workload; nhóm tổng chỉ là điểm xuất phát.
4. Liên hệ call site với subsystem Java/HotSpot tương ứng và số đo nghiệp vụ: số thread, class loader, direct/mapped buffer, queue, worker/cache.
5. Kiểm tra deallocation khi workload kết thúc và xem xu hướng nhiều chu kỳ. Một call site có delta dương trong lúc ứng dụng vẫn giữ dữ liệu hợp lệ không mặc nhiên leak.

Nội dung `detail` phụ thuộc bản JDK, biểu tượng debug/symbols, nền tảng và loại phân bổ. Một số dòng có thể là call stack nội bộ HotSpot, `mmap`/virtual memory map thay vì `malloc`. **Điểm cấp phát tăng là nơi cần điều tra, không tự động là lỗi ở đúng hàm đó.** Có thể owner ở lớp cao hơn đã yêu cầu giữ bộ nhớ hợp lệ; ngược lại, owner sống lâu vô ý khiến vùng cấp phát vẫn tồn tại.

Detail tracking tốn tài nguyên hơn summary và tạo báo cáo dài. Với môi trường quan trọng, lên kế hoạch thời gian đo, dung lượng lưu kết quả và tác động vận hành.

## 6. Từ `summary.diff` sang giả thuyết nguyên nhân

Sau khi biết nhóm tăng, phải nối dữ liệu NMT với phép đo khác:

| Nhóm tăng trong NMT | Câu hỏi tiếp theo | Nguồn bằng chứng bổ sung |
| --- | --- | --- |
| `Thread`: reserved/committed và `thread #` tăng | Đây là thread pool đang scale theo tải hay luồng không kết thúc? | `jcmd <pid> Thread.print`, metric live thread, executor pool/queue, lifecycle |
| `Class`: class count, metaspace committed tăng | Có nạp class/lambda/proxy mới liên tục? Class loader nào đáng ra phải unload? | JFR class load/unload, `jcmd <pid> VM.classloader_stats`, class loader retention |
| `Code`/`Compiler` tăng | JIT còn trong warm-up, hay có compile activity bất thường? | Code cache, compilation metrics/JFR, thời gian ổn định |
| `GC` tăng | JVM/collector có mở rộng cấu trúc GC phù hợp heap/workload? | GC logs, heap committed, collector/config |
| `Other`/`Internal` tăng | Có buffer/off-heap hoặc allocation HotSpot nào liên quan? | `detail.diff`, direct/mapped BufferPoolMXBean, JFR, thành phần sử dụng native |
| `Java Heap` committed tăng | VM commit thêm heap hay live Java object tăng? | GC log, heap used sau các GC tương đương, heap dump/histogram |
| `Native Memory Tracking` tăng | Có phải overhead bản thân công cụ đo? | NMT tracking overhead, snapshot cùng cấu hình |

Trong Java, kiểm tra direct/mapped buffer bằng các số đo ở `java.nio:type=BufferPool` (JMX) hoặc `BufferPoolMXBean` có thể giúp đối chiếu. **Không mặc định** mọi byte NMT `Other` là direct buffer: cách gắn category phụ thuộc đường cấp phát và phiên bản JVM. Đồng thời `BufferPoolMXBean` chỉ phản ánh các pool mà JVM công bố, không bao quát mọi `malloc` của mã JNI.

### Ba kịch bản chẩn đoán

**Kịch bản A — Thread tăng khi traffic tăng.** T1 thấy `Thread reserved +64 MB`, thread count `+64`; khi traffic trở về bình thường và executor hạ số luồng, T3 còn `+2`. Đây có thể là scale theo tải. Xác minh bằng thread dump và pool config; nếu số luồng tiếp tục đi lên qua các vòng tải giống nhau dù công việc đã kết thúc, kiểm tra thread creation và cleanup.

**Kịch bản B — Class tăng qua nhiều lần nạp plugin.** Sau mỗi lần reload, `Class committed` và số class/class loader cùng tăng; T3 không giảm dù phiên cũ đáng lẽ không dùng nữa. Đây là nghi vấn class loader retention. NMT chỉ khoanh nhóm; cần xem classloader stats, các tham chiếu giữ loader cũ, thread, registry/listener và kiểm chứng sau sửa. Không mặc nhiên gắn tên `metaspace leak` cho giai đoạn warm-up.

**Kịch bản C — RSS tăng nhưng NMT ít đổi.** Process RSS tăng 300 MB trong khi tổng `committed` được NMT theo dõi gần như đứng yên. Điều này **không bác bỏ** vấn đề native memory: NMT không bao quát cấp phát ngoài HotSpot (ví dụ thư viện JNI tự gọi malloc), và committed cũng không đồng nhất RSS. Kiểm tra `/proc/<pid>/smaps`, `smaps_rollup`, `pmap`/native profiler tùy OS, memory mapping, thread stacks, container/cgroup và thư viện native liên quan.

## 7. Quy trình điều tra thực hành từng bước

**Bước 1 — Xác định triệu chứng chính xác.** Có phải RSS/cgroup tăng, Java heap used tăng, OOME ở native allocation, hay chỉ vùng `reserved` rất lớn? Vẽ đồ thị ít nhất một khoảng workload đại diện, không căn cứ vào một số duy nhất.

**Bước 2 — Chọn chế độ NMT.** Bắt đầu với `summary` nếu chưa biết nhóm nào. Chọn `detail` khi đã có khả năng tái hiện và cần allocation sites; kế hoạch khởi động lại với cờ `detail` là một phần của phép thử.

**Bước 3 — Ghi một baseline có ý nghĩa.** Chỉ sau warm-up theo mục tiêu bài thử. Lưu giá trị tuyệt đối, timestamp, PID, phiên bản JDK và cấu hình, workload hiện tại.

**Bước 4 — Đo nhiều mốc cùng baseline.** Thu `summary.diff` tại tải ổn định, tăng tải, sau khi hạ tải và sau thời gian hồi phục hợp lý. Đặt các delta cạnh request concurrency, active threads, queue depth, class count, buffer usage.

**Bước 5 — Chọn nhóm có tăng bền.** Quan sát `committed` và `malloc`/`mmap` phù hợp, không đánh đồng `reserved` với RSS; kiểm tra liệu tăng phù hợp warm-up/working set có giới hạn hay không.

**Bước 6 — Đi sâu bằng detail và công cụ bổ sung.** Truy call site có delta tăng, xem allocation owner và lifecycle. Khi thiếu coverage NMT, chuyển sang số đo OS/native profiler hoặc công cụ chuyên cho JNI.

**Bước 7 — Đưa ra giả thuyết có thể bác bỏ.** Ví dụ “cứ 1.000 lần reload plugin, số class loader cũ tăng, Class committed tăng dù không còn request dùng plugin cũ”. Thiết kế phép thử hạ tải/cleanup cho giả thuyết.

**Bước 8 — Sửa rồi đo lại cùng điều kiện.** Đặt baseline mới sau warm-up của phiên bản đã sửa, so xu hướng delta theo *cùng thời lượng, cùng traffic, cùng trình tự*. Có thể so các bản snapshot tuyệt đối giữa hai JVM, nhưng **không lấy diff nội bộ của JVM A áp sang baseline JVM B**.

### Mẫu nhật ký đo cho một phiên

| Trường cần ghi | Ví dụ |
| --- | --- |
| JVM, PID, NMT | JDK 21, PID 12345, `detail` |
| Heap/config | `-Xms256m -Xmx1g`, collector và container limit ghi riêng |
| Baseline | T0 sau 5 phút warm-up đại diện |
| Workload | RPS, concurrency, payload size, key cardinality, queue length |
| Mốc | T1 sau tải đều, T2 sau stress, T3 sau hạ tải |
| Báo cáo lưu | `nmt-t0-detail.txt`; các file `summary.diff`/`detail.diff` |
| Nhóm thay đổi | Delta reserved và committed, số thread/class/allocation |
| Giả thuyết | Tăng theo pool, cache/buffer hợp lệ, hoặc owner không được cleanup |
| Phép kiểm chứng | So lifecycle/counter, hạ tải, lặp chu kỳ và snapshot bổ sung |

## 8. Lỗi thường gặp khi đọc diff

**1. “`reserved +1 GB` nghĩa là JVM ăn thêm 1 GB RAM.”** Sai. Reserved là không gian địa chỉ ảo; xem committed và RSS/cgroup. Java heap hoặc compressed class space có thể reserve diện tích lớn từ sớm mà chưa commit tương ứng.

**2. “`committed +100 MB` chắc chắn memory leak.”** Chưa đủ. Có thể có heap expansion, pool/cache warm-up, JIT, thread count tăng theo concurrency. Đặt câu hỏi liệu bộ nhớ có trở về nền/plateau sau khi workload kết thúc và có owner hợp lệ hay không.

**3. “Chạy `summary.diff` hai lần cho ra thay đổi giữa hai lần.”** Sai. Cả hai so với baseline gần nhất. Muốn so riêng T2 với T1 phải tạo baseline mới tại T1 và ghi rõ sự thay đổi mốc, hoặc tự trừ số đo tuyệt đối theo cùng đơn vị/quy tắc.

**4. “Có thể bật `detail.diff` giữa chừng mà không restart.”** Không. NMT tracking level được thiết lập khi khởi động. Nếu mức hiện tại là `summary` thì cần một JVM khác khởi động với `detail`.

**5. “Class count tăng là class loader leak.”** Không nhất thiết. Khởi động/JIT, dynamic proxy/lambda và module hợp lệ đều có thể tăng class count. Cần xem class unloading, số loader không còn được dùng và đường giữ loader cũ.

**6. “NMT ổn định thì không có JNI/native leak.”** Sai. NMT không theo dõi toàn bộ allocation do thư viện native bên ngoài HotSpot thực hiện. RSS hoặc memory cgroup có thể tăng độc lập với báo cáo NMT.

**7. “`detail.diff` chỉ thẳng dòng Java gây leak.”** Không. Nó cho thấy **call site HotSpot** và vùng virtual memory được theo dõi, không phải lời giải trực tiếp cho đồ thị owner Java hoặc mọi thư viện native. Cần liên hệ stack, subsystem và vòng đời đối tượng.

**8. “Diff âm đã chứng minh toàn bộ bộ nhớ được giải phóng.”** Không. Đó là giảm **ròng so với baseline** ở nhóm/đơn vị đo; vẫn có thể còn allocation sống lâu, fragmentation hoặc phần memory ngoài phạm vi NMT.

**9. “Baseline ngay khi process start giúp đo mọi thứ tốt hơn.”** Không hẳn. Nếu mục tiêu là bộ nhớ tăng do workload sau warm-up, mốc quá sớm trộn cả class loading, code cache và pool initialization. Chọn baseline theo câu hỏi đang điều tra, và ghi rõ thời điểm.

**10. “Đổi `scale=MB` làm tiết kiệm bộ nhớ hơn.”** Không. Đây chỉ là đơn vị hiển thị; với delta nhỏ có thể làm tròn mất tín hiệu. Dùng KB khi cần theo dõi tăng nhỏ nhưng kéo dài.

## 9. Checklist chốt kết luận

Trước khi viết báo cáo “native memory leak”, hãy xác nhận:

- [ ] Đúng PID/JDK, JVM bật `-XX:NativeMemoryTracking=summary` hoặc `detail` **từ lúc khởi động**.
- [ ] T0 được đặt sau warm-up phù hợp; biết mọi lần `baseline` đã gọi và diff tham chiếu tới mốc nào.
- [ ] Có nhiều mốc ở tải tương đương và giai đoạn hạ tải; không suy xu hướng từ một ảnh chụp.
- [ ] Đọc `reserved` và `committed` tách biệt, không đánh đồng với RSS hoặc Java heap live objects.
- [ ] Nhóm tăng có delta lặp lại và được đối chiếu với thread/class/buffer/queue/workload metrics.
- [ ] Nếu cần, `detail.diff` xác định được HotSpot call site/vùng VM cần điều tra; đã cân nhắc phần ngoài coverage NMT.
- [ ] Có giả thuyết về owner, giới hạn và thời điểm giải phóng bộ nhớ, cùng phép thử để bác bỏ hoặc xác nhận.
- [ ] Sau thay đổi, cùng phép thử cho thấy bộ nhớ đạt plateau hoặc trở về nền mong đợi, và hiệu năng/chức năng vẫn đạt yêu cầu.

**Thông điệp cốt lõi:** `baseline` cố định thời điểm so sánh; `summary.diff` chỉ ra **nhóm bộ nhớ nào thay đổi**; `detail.diff` đưa bạn gần hơn đến **nơi HotSpot cấp phát/ánh xạ bộ nhớ**. Cả ba là công cụ thu thập bằng chứng, còn kết luận leak cần xu hướng qua thời gian và xác minh vòng đời owner.

### Tài liệu tham khảo chính thức

- Oracle JDK 21 — *Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle JDK 21 — *Diagnostic Tools / Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — *Troubleshoot Memory Leaks*: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
