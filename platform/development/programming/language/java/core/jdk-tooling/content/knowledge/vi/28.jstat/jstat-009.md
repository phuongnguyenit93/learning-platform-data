# Giới hạn của jstat

**jstat** là công cụ dòng lệnh của JDK dùng để đọc các performance counters do Java HotSpot VM cung cấp. Công cụ thường được dùng để quan sát thống kê garbage collection, mức sử dụng các vùng heap, class loading và hoạt động của JIT compiler.

jstat hữu ích khi cần một cái nhìn nhanh theo từng mẫu thời gian. Tuy nhiên, nó không phải hệ thống monitoring đầy đủ, không ghi lại toàn bộ sự kiện runtime và không giải thích nguyên nhân sâu xa của một vấn đề. Trong Oracle JDK 24, jstat được phân loại là **experimental và unsupported**; các tùy chọn và chức năng có thể thay đổi hoặc bị loại bỏ trong những bản phát hành sau.

Bài này tập trung vào giới hạn dữ liệu, độ chính xác theo thời gian, phạm vi JVM được hỗ trợ, cách diễn giải các counter, remote monitoring và những trường hợp nên chuyển sang JFR, JMX, jcmd hoặc công cụ hệ điều hành.

## 1. jstat đo điều gì?

jstat đọc dữ liệu từ built-in instrumentation/performance counters của Java HotSpot VM. Các counter này cung cấp thông tin tổng hợp về một số hoạt động của JVM, ví dụ:

- Dung lượng và mức sử dụng các vùng heap.
- Số lần young GC và full GC đã xảy ra.
- Tổng thời gian GC đã tích lũy.
- Dung lượng và mức sử dụng metaspace.
- Số class đã load/unload.
- Thống kê tổng hợp của JIT compiler.
- Nguyên nhân của lần GC gần nhất và GC hiện tại nếu có.

jstat không thu thập mọi sự kiện bên trong JVM. Nó đọc các counter được VM công bố, rồi hiển thị snapshot theo chu kỳ lấy mẫu.

### jstat không phải profiler

Một profiler hoặc event recorder có thể ghi lại allocation, stack trace, lock contention, method execution, GC event và mốc thời gian cụ thể. jstat chủ yếu đưa ra số liệu tổng hợp như số lần GC và tổng thời gian đã tiêu tốn.

Ví dụ, jstat có thể cho thấy số lần young GC tăng từ 20 lên 25 giữa hai mẫu. Nó không cho biết chính xác từng GC bắt đầu lúc nào, object nào gây áp lực allocation hay method nào tạo ra nhiều object.

## 2. jstat chỉ hỗ trợ phạm vi JVM nhất định

jstat được thiết kế cho **instrumented Java HotSpot VM**. Không nên giả định nó có thể giám sát mọi implementation của JVM hoặc mọi process có tên java.

Các giới hạn thực tế:

- JVM không phải HotSpot có thể không cung cấp các counter mà jstat cần.
- JVM không được instrument hoặc không công bố performance data có thể không truy cập được.
- Người chạy jstat cần quyền quan sát/attach phù hợp với process đích.
- JVM chạy trong container hoặc PID namespace khác có thể khó tìm từ host.
- LVMID thường là PID hệ điều hành nhưng không được bảo đảm luôn trùng.
- Trên hệ thống dùng FAT32, Oracle Troubleshooting Guide ghi rõ instrumentation không truy cập được.

Theo Oracle JDK 24 Troubleshooting Guide, instrumentation HotSpot được bật mặc định và jstat thường không yêu cầu JVM khởi chạy với option đặc biệt. Điều này không có nghĩa mọi runtime, filesystem, tài khoản hoặc môi trường triển khai đều có thể truy cập được dữ liệu.

### Xác định đúng VMID

Cú pháp đơn giản cho JVM local:

~~~bash
jstat -gcutil 12345 1000ms 5
~~~

12345 là LVMID minh họa. Hãy tìm process bằng jps hoặc công cụ OS rồi xác minh lại trước khi chạy.

Linux/macOS:

~~~bash
ps -p 12345 -o pid,ppid,user,etime,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 12345" |
    Select-Object ProcessId, ParentProcessId, Name
~~~

Không lưu PID lâu dài để dùng lại sau. PID có thể được hệ điều hành tái sử dụng khi process cũ kết thúc.

## 3. jstat là công cụ experimental và unsupported

Oracle JDK 24 ghi rõ jstat là **experimental và unsupported**. Tài liệu cũng nêu tất cả option và chức năng có thể thay đổi hoặc bị loại bỏ trong các release tương lai.

Điều này ảnh hưởng trực tiếp đến cách sử dụng:

- Không coi output là giao diện dữ liệu ổn định.
- Không giả định mọi JDK vendor/version có cùng danh sách option.
- Không xây dựng automation quan trọng dựa trên một cột output cố định.
- Không giả định tên cột, thứ tự cột hoặc semantics luôn giống nhau.
- Kiểm tra help và tài liệu của đúng JDK đang chạy ứng dụng.

Xem version và danh sách option:

~~~bash
java --version
jstat --help
jstat -options
~~~

Trên OpenJDK 24.0.2 đã kiểm tra, danh sách option gồm:

~~~text
-class
-compiler
-gc
-gccapacity
-gccause
-gcmetacapacity
-gcnew
-gcnewcapacity
-gcold
-gcoldcapacity
-gcutil
-printcompilation
~~~

Danh sách này là kết quả của toolchain cụ thể, không phải cam kết rằng mọi JDK trong tương lai sẽ giữ nguyên các option đó.

## 4. Output không phải định dạng ổn định để parse

jstat hiển thị dữ liệu dạng bảng với các cột phân tách bằng khoảng trắng. Header mô tả tên cột; option được chọn quyết định cột nào xuất hiện.

Oracle cảnh báo không nên viết script parse output của jstat vì format có thể thay đổi trong các bản phát hành sau.

Ví dụ:

~~~text
Timestamp         S0     S1      E      O      M     CCS    YGC    YGCT
        120.1      -  82.40  54.21  70.10  91.00  88.10     18   0.420
        121.1      -  82.40  66.32  70.10  91.00  88.10     18   0.420
~~~

Đây là output minh họa. Không dùng các số trong ví dụ làm baseline hiệu năng.

Một script tách chuỗi theo dấu cách có thể hỏng khi:

- Tên cột hoặc số cột thay đổi.
- Giá trị không áp dụng được hiển thị bằng dấu gạch ngang.
- Collector hoặc JDK thêm/bớt counter.
- Output chứa warning hoặc diagnostic message.
- Một phiên bản mới thay đổi cách định dạng số.

Nếu cần machine-readable metrics, hãy dùng JMX MXBeans, JFR, monitoring agent hoặc API có hợp đồng ổn định hơn. Nếu vẫn phải dùng jstat trong script nội bộ, hãy khóa JDK version, kiểm tra output format, xử lý lỗi và chuẩn bị sửa script khi nâng cấp.

## 5. Lấy mẫu không phải ghi lại mọi sự kiện

Cú pháp tổng quát:

~~~bash
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Trong đó:

- option chọn nhóm thống kê.
- vmid xác định JVM mục tiêu.
- interval là khoảng cách giữa các lần lấy mẫu.
- count là số mẫu cần in.
- -t thêm cột thời gian đã trôi qua kể từ khi JVM khởi chạy.
- -h n lặp lại header sau mỗi n dòng dữ liệu.

Ví dụ lấy 5 mẫu, mỗi giây một lần:

~~~bash
jstat -gcutil 12345 1000ms 5
~~~

Có thể dùng đơn vị giây:

~~~bash
jstat -gcutil 12345 1s 5
~~~

Nếu bỏ count, jstat tiếp tục in mẫu cho đến khi JVM kết thúc hoặc người dùng dừng lệnh. Trong kiểm tra một lần, nên chỉ định count để tránh tiến trình theo dõi chạy vô hạn.

### Mẫu có thể bỏ lỡ sự kiện ngắn

Giả sử một GC xảy ra và hoàn tất giữa hai lần lấy mẫu. jstat có thể không hiển thị trạng thái đang chạy của sự kiện đó; counter tích lũy như YGC hoặc YGCT có thể tăng ở mẫu tiếp theo.

Do đó:

- Khoảng lấy mẫu 5 giây có thể bỏ lỡ nhiều thay đổi ngắn.
- Khoảng lấy mẫu 100 ms có độ phân giải cao hơn nhưng vẫn không phải event trace.
- Một giá trị không đổi giữa hai mẫu không chứng minh hệ thống không có hoạt động.
- Thời điểm thay đổi chỉ được giới hạn trong khoảng giữa hai mẫu, không phải thời điểm sự kiện chính xác.

Chọn interval theo câu hỏi cần trả lời. Không nên dùng một interval duy nhất cho mọi tình huống.

### Lấy mẫu quá dày cũng có giới hạn

jstat phải đọc counter, kết nối tới JVM và ghi output. Polling rất thường xuyên trên nhiều JVM làm tăng số lần truy vấn, lượng output và tải quản trị. Dù công cụ thường nhẹ hơn profiler, không nên coi việc polling liên tục ở interval cực ngắn là miễn phí.

Với giám sát dài hạn, dùng JFR, JMX hoặc monitoring platform có cơ chế lấy mẫu, lưu trữ và cảnh báo phù hợp.

## 6. Timestamp của jstat không phải đồng hồ thời gian thực

Tùy chọn -t thêm cột Timestamp:

~~~bash
jstat -gcutil -t 12345 1000ms 5
~~~

Timestamp là số giây đã trôi qua kể từ thời điểm JVM mục tiêu khởi chạy. Nó không phải ngày giờ UTC hoặc local time.

Độ phân giải timestamp phụ thuộc nhiều yếu tố và có thể thay đổi khi thread bị trì hoãn lập lịch trên hệ thống tải cao. Vì vậy, không dùng riêng cột này để đối chiếu chính xác với timestamp trong log ứng dụng, load balancer hoặc hệ thống monitoring khác.

Nếu cần tương quan thời gian:

1. Ghi lại thời điểm wall-clock bắt đầu lấy mẫu.
2. Lưu JDK version, host, process identity và timezone.
3. Dùng GC log hoặc JFR có timestamp cho timeline chi tiết.
4. Xem xét độ trễ do scheduling và clock synchronization giữa các máy.

### Lặp lại header với -h

~~~bash
jstat -gcutil -h5 12345 1000ms 20
~~~

Header được in lại sau mỗi 5 mẫu. Tùy chọn này giúp đọc log dài dễ hơn; nó không tăng độ chính xác hoặc bổ sung dữ liệu mới.

## 7. Phần trăm heap không phải số byte

Option -gcutil hiển thị mức sử dụng theo phần trăm dung lượng hiện tại của các vùng memory pool.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| S0, S1 | Phần trăm sử dụng survivor spaces |
| E | Phần trăm sử dụng eden |
| O | Phần trăm sử dụng old space |
| M | Phần trăm sử dụng metaspace |
| CCS | Phần trăm sử dụng compressed class space |
| YGC | Số young GC tích lũy |
| YGCT | Tổng thời gian young GC tích lũy |
| FGC | Số full GC tích lũy |
| FGCT | Tổng thời gian full GC tích lũy |
| GCT | Tổng thời gian GC tích lũy |

Ví dụ:

~~~bash
jstat -gcutil 12345 1000ms 5
~~~

Nếu O tăng từ 70% lên 85%, điều đó chỉ cho biết old space đang sử dụng tỷ lệ lớn hơn so với capacity hiện tại. Không thể kết luận heap đã tăng đúng 15% hoặc ứng dụng bị memory leak.

Capacity của vùng có thể thay đổi khi heap mở rộng hoặc thu hẹp. Để xem số liệu dung lượng theo KB, dùng:

~~~bash
jstat -gc 12345 1000ms 5
jstat -gccapacity 12345 1000ms 5
~~~

Đọc đồng thời capacity và utilization để hiểu phần trăm đang dựa trên mẫu số nào.

### Phần trăm cao không tự động là lỗi

Old space hoặc metaspace sử dụng cao có thể là trạng thái bình thường của ứng dụng. Garbage collector có thể giữ lại object sống, cache hoặc class đã nạp theo thiết kế.

Cần đánh giá thêm:

- Mức sử dụng sau GC.
- Xu hướng qua nhiều chu kỳ tải.
- Tần suất và thời gian GC.
- Heap capacity và giới hạn cấu hình.
- Request latency, throughput và memory pressure.
- Object graph hoặc class loader nếu nghi ngờ leak.

Không dùng một mẫu duy nhất để kết luận memory leak.

## 8. Counter tích lũy không phải thống kê từng GC event

Các cột như YGC, YGCT, FGC, FGCT và GCT là counter tích lũy từ khi JVM khởi chạy.

Ví dụ:

| Mẫu | YGC | YGCT (giây) | FGC | FGCT (giây) |
|---|---:|---:|---:|---:|
| 1 | 20 | 0,800 | 2 | 0,450 |
| 2 | 24 | 0,940 | 2 | 0,450 |

Trong khoảng giữa hai mẫu:

- Có 4 young GC mới.
- Tổng thời gian young GC tăng 0,140 giây.
- Không có full GC mới theo counter này.

Các con số trên chỉ minh họa phép đọc counter. Chúng không cho biết từng GC pause dài bao nhiêu hoặc xảy ra chính xác ở thời điểm nào.

### Không thể suy ra phân bố pause từ tổng thời gian

Nếu YGCT tăng 140 ms qua 4 lần GC, không thể kết luận mỗi lần kéo dài 35 ms. Có thể một sự kiện kéo dài 100 ms và ba sự kiện còn lại ngắn hơn nhiều.

Muốn biết từng pause, dùng unified GC logging:

~~~bash
-Xlog:gc*
~~~

Hoặc dùng JFR để thu thập GC events và phân tích trong JDK Mission Control.

### Counter có thể reset khi JVM khởi động lại

Counter bắt đầu lại theo vòng đời JVM. Khi process restart, YGC/FGC/YGCT có thể trở về giá trị nhỏ. Nếu monitoring lưu dữ liệu qua nhiều lần restart mà không gắn process identity, phép tính delta có thể sai.

Hãy lưu PID/LVMID, start time hoặc application instance identity cùng chuỗi số liệu.

### Collector có thể có counter riêng

Một số collector hoặc phiên bản JDK công bố thêm counter riêng. Ví dụ output G1 trên OpenJDK 24.0.2 có thể hiển thị CGC và CGCT cho concurrent cycles/time. Không giả định mọi collector đều có cùng cột.

## 9. jstat không cung cấp chi tiết nguyên nhân của memory growth

jstat có thể cho biết heap utilization tăng hoặc số GC tăng. Nó không cho biết object nào đang giữ heap hoặc class nào tạo ra lượng allocation lớn.

jstat không cung cấp trực tiếp:

- Danh sách object đang sống.
- Reference path đến GC roots.
- Retained heap theo object.
- Allocation stack trace theo từng allocation.
- Dominator tree.
- Object nào giữ cache hoặc collection không được giải phóng.
- Nội dung field hoặc quan hệ tham chiếu của object.

### Khi nghi ngờ memory leak

Dùng jstat để nhận biết xu hướng, sau đó thu thập dữ liệu sâu hơn:

~~~bash
jcmd 12345 GC.class_histogram
jcmd 12345 GC.heap_dump heap.hprof
~~~

GC.class_histogram cho biết class nào có nhiều instance và shallow bytes. Heap dump cho phép dùng MAT hoặc công cụ tương thích HPROF để xem dominator tree và paths to GC roots.

Heap dump có thể gây pause và chứa dữ liệu nhạy cảm. Chỉ thu thập khi đã đánh giá tác động, dung lượng đĩa và quyền truy cập.

## 10. jstat không đo đầy đủ native memory hoặc process memory

jstat tập trung vào một số HotSpot performance counters. Các cột heap và metaspace không phải toàn bộ memory của process.

Những vùng hoặc nguồn tiêu thụ có thể cần công cụ khác:

- Native thread stacks.
- JNI/native libraries.
- Direct ByteBuffer và native allocations.
- Code cache.
- GC native structures.
- Memory mapping.
- Process RSS/working set.
- Container/cgroup memory limit và usage.
- Bộ nhớ của process con hoặc sidecar.

Metaspace và compressed class space có thể xuất hiện trong một số jstat options, nhưng điều đó không có nghĩa jstat đo toàn bộ native memory.

### Công cụ thay thế

Nếu cần phân tích native memory, có thể bật Native Memory Tracking khi khởi chạy JVM:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

Sau đó dùng:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

NMT phải được bật từ lúc JVM khởi chạy; không thể bật đầy đủ hồi tố sau khi process đã chạy. NMT cũng có overhead và có các mức chi tiết khác nhau.

Để xem process memory thực tế, dùng OS tools như ps, top, task manager hoặc container metrics. Không cộng các vùng jstat rồi coi đó là RSS của process.

## 11. jstat không cho biết đầy đủ trạng thái ứng dụng

jstat không phải health check. Nó không biết service có đang xử lý request thành công, database có kết nối được hay queue có bị backlog hay không.

jstat không trực tiếp cung cấp:

- Request rate và error rate.
- Latency percentile như p95/p99.
- Thread pool queue length.
- Deadlock và stack trace đầy đủ.
- Database connection pool health.
- HTTP dependency latency.
- Business transaction success rate.
- CPU usage của process theo từng core.

Một JVM có thể có heap ổn định nhưng ứng dụng vẫn bị nghẽn do lock contention, I/O, network, thread starvation hoặc database. Ngược lại, heap utilization cao có thể hoàn toàn bình thường nếu GC hoạt động tốt.

Kết hợp jstat với application metrics, logs, distributed tracing, JFR và OS monitoring để đánh giá hệ thống.

## 12. Các nhóm option có phạm vi hẹp

jstat có nhiều output option, nhưng mỗi option chỉ trình bày một nhóm counter cụ thể.

| Option | Dữ liệu chính | Điều không thể kết luận chỉ từ option |
|---|---|---|
| -class | Số class loaded/unloaded và thời gian | Không cho biết đầy đủ class loader nào giữ class hoặc nguyên nhân leak |
| -compiler | Thống kê JIT compilation và lần compile gần nhất | Không phải profile CPU hoặc toàn bộ lịch sử compile |
| -gc | Dung lượng và mức sử dụng một số heap spaces, GC counters | Không phải toàn bộ process memory hoặc từng GC event |
| -gccapacity | Capacity của generations/spaces | Không cho biết object nào chiếm dung lượng |
| -gccause | GC summary và cause gần nhất/hiện tại | Không phải lịch sử đầy đủ từng GC event |
| -gcnew | Thống kê new generation | Không giải thích allocation stack hoặc object promotion cụ thể |
| -gcnewcapacity | Capacity của new generation | Không cho biết heap pressure từ toàn bộ process |
| -gcold | Old generation và metaspace counters | Không cho biết reference path giữ object |
| -gcoldcapacity | Capacity của old generation | Không phải retained heap theo object |
| -gcmetacapacity | Capacity của metaspace | Không cho biết class loader cụ thể gây tăng metaspace |
| -gcutil | Phần trăm sử dụng và GC counters | Phần trăm không phải số byte tuyệt đối |
| -printcompilation | Thống kê compilation method | Không thay thế JFR hoặc profiler |

Dùng:

~~~bash
jstat -options
~~~

để xem option có sẵn trong JDK đang chạy. Không giả định option có cùng semantics trên mọi collector hoặc release.

## 13. -gccause chỉ cung cấp nguyên nhân GC gần nhất

Option:

~~~bash
jstat -gccause 12345 1000ms 5
~~~

hiển thị summary tương tự -gcutil và bổ sung:

- LGCC: nguyên nhân của lần GC gần nhất.
- GCC: nguyên nhân của GC hiện tại nếu có.

Đây không phải nhật ký toàn bộ các lần GC. Nếu cần biết thời điểm, duration, loại GC, phase, concurrent work và chi tiết pause, dùng GC log hoặc JFR.

## 14. Remote monitoring phụ thuộc jstatd và RMI

jstat có thể giám sát JVM từ xa bằng VMID có hostname:

~~~bash
jstat -gcutil 40496@remote.domain 1000ms 10
~~~

Cách này sử dụng RMI và yêu cầu jstatd trên host đích. RMI registry mặc định dùng port 1099 nếu không chỉ định port khác.

### jstatd có rủi ro và đang bị deprecate

Trong JDK 24, jstatd được **deprecated for removal**. Đây là trạng thái của jstatd, không phải tuyên bố rằng local jstat đã bị deprecated for removal. jstat vẫn được mô tả là experimental và unsupported.

Oracle JDK 24 jstatd documentation cũng nêu:

- jstatd chạy với credential có quyền truy cập instrumentation của JVM mục tiêu.
- jstatd không cung cấp authentication cho remote clients.
- Instrumentation của các JVM mà jstatd có quyền truy cập có thể được expose cho người dùng trên mạng.
- Remote RMI interface là proprietary và được bảo đảm có thể thay đổi.

Không mở jstatd ra mạng công khai chỉ để tiện xem counter. Nếu không thể kiểm soát rủi ro remote access, không chạy daemon; dùng jstat local hoặc một hệ thống monitoring được bảo vệ.

Với hệ thống mới, ưu tiên JMX có authentication/TLS, JFR streaming hoặc monitoring agent đã được phê duyệt thay cho việc xây dựng hạ tầng mới phụ thuộc jstatd.

## 15. Filesystem, quyền và môi trường container

### Quyền truy cập process

jstat phải đọc được instrumentation của JVM mục tiêu. Nếu user chạy tool không có quyền phù hợp, lệnh có thể không tìm thấy VM hoặc không đọc được counter.

Không tự động chạy bằng root/Administrator để vượt qua mọi lỗi. Xác định owner, quyền attach và quy trình vận hành được phép.

### FAT32

Oracle JDK 24 Troubleshooting Guide ghi rõ instrumentation không truy cập được trên filesystem FAT32. Nếu JVM data directory hoặc cơ chế lưu instrumentation nằm trên FAT32, jstat có thể không hoạt động như mong đợi.

Kiểm tra filesystem của môi trường thay vì kết luận JVM không có performance counters.

### Container và PID namespace

Trong container, PID bên trong namespace có thể khác PID quan sát từ host. jstat cần VMID đúng với phạm vi mà tool đang chạy.

- Chạy jstat bên trong container nếu JDK và quyền cần thiết có sẵn.
- Hoặc xác định LVMID/PID theo đúng host và namespace.
- Không dùng PID trong container cho lệnh chạy ở host khác namespace.
- Kiểm tra giới hạn process visibility và security policy của container.

jstat không thay thế container metrics. Memory của JVM và memory usage của container là hai phạm vi khác nhau.

## 16. Ví dụ thực hành đọc một chuỗi mẫu

Giả sử chạy:

~~~bash
jstat -gcutil -t -h5 12345 1000ms 10
~~~

Lệnh lấy 10 mẫu, cách nhau khoảng một giây, thêm elapsed timestamp và lặp header sau mỗi 5 mẫu.

Giả sử hai mẫu liên tiếp:

~~~text
Timestamp         S0     S1      E      O      M     CCS    YGC    YGCT    FGC    FGCT    GCT
       100.0       -  80.00  65.00  72.00  91.00  88.00     20   0.800      2   0.450   1.250
       101.0       -  80.00  12.00  73.50  91.00  88.00     21   0.840      2   0.450   1.290
~~~

Đây là dữ liệu minh họa.

Có thể suy luận thận trọng:

- YGC tăng từ 20 lên 21, có thêm một young GC giữa hai mẫu.
- YGCT tăng 0,040 giây, tổng thời gian young GC tích lũy tăng 40 ms.
- FGC không đổi, không có full GC mới theo counter trong khoảng đó.
- E giảm mạnh vì eden utilization đã thay đổi sau chu kỳ GC.
- O tăng từ 72% lên 73,5%, nhưng cần xem capacity và nhiều mẫu tiếp theo trước khi kết luận old space tăng bất thường.

Không thể từ hai dòng này biết chính xác thời điểm GC, pause duration của sự kiện, class nào gây allocation hoặc object nào đang giữ old generation.

Nếu cần chi tiết hơn:

1. Dùng -gc hoặc -gccapacity để xem dung lượng theo KB.
2. Thu thập GC log hoặc JFR để có event timeline.
3. Dùng heap histogram/heap dump khi cần phân tích object.
4. Kiểm tra OS/container metrics nếu nghi ngờ native memory hoặc memory limit.

## 17. Lựa chọn công cụ thay thế theo câu hỏi

| Câu hỏi | Công cụ phù hợp |
|---|---|
| Heap utilization và GC counters nhanh | jstat |
| GC event timeline và pause detail | Unified GC logging hoặc JFR |
| Allocation, lock và runtime events | JFR + JDK Mission Control |
| Metrics programmatic trong ứng dụng | JMX MXBeans |
| Một lần xem JVM flags hoặc diagnostic state | jcmd |
| Object count theo class | jcmd GC.class_histogram |
| Reference graph và retained heap | Heap dump + MAT |
| Native memory theo nhóm | Native Memory Tracking + jcmd |
| Process RSS, CPU, cgroup usage | OS/container monitoring |
| Health, latency, throughput | Application metrics và distributed tracing |
| Monitoring nhiều JVM dài hạn | JMX/agent/monitoring platform được bảo vệ |

### Ví dụ dùng JFR

JFR có thể ghi lại các runtime events trong một khoảng thời gian:

~~~bash
jcmd 12345 JFR.start name=runtime-audit duration=60s filename=runtime-audit.jfr
~~~

Sau đó mở file bằng JDK Mission Control hoặc dùng jfr tool để kiểm tra. Tên event và nội dung phụ thuộc cấu hình recording và JDK. JFR phù hợp hơn khi cần tìm mối liên hệ giữa GC, allocation, CPU, lock và application behavior.

### Ví dụ dùng JMX

Các MXBeans như MemoryMXBean, GarbageCollectorMXBean và MemoryPoolMXBean cung cấp API để đọc memory usage và GC counters. Chúng phù hợp cho monitoring có cấu trúc, nhưng vẫn cần bảo vệ JMX endpoint bằng authentication, TLS và network controls.

## 18. Lỗi thường gặp khi diễn giải jstat

### Heap percentage tăng nghĩa là memory leak

Không đủ bằng chứng. Capacity có thể thay đổi, cache có thể hợp lệ và object có thể được thu hồi ở chu kỳ sau. So sánh nhiều mẫu, xem sau GC và phân tích object graph nếu cần.

### GCT tăng nghĩa là ứng dụng pause đúng bằng giá trị đó

GCT là tổng thời gian GC tích lũy theo counter. Nó không cho biết phân bố pause hoặc latency từng request. Dùng GC log/JFR để xem từng event.

### Không thấy counter thay đổi nghĩa là JVM không hoạt động

Có thể JVM đang idle hoặc thay đổi xảy ra giữa hai mẫu. jstat chỉ lấy snapshot, không phải event stream.

### O hoặc M gần 100% luôn là lỗi

Không nhất thiết. Xem capacity, GC behavior, memory pool và giới hạn cấu hình. Metaspace usage cao không tự chứng minh class loader leak.

### jstat không kết nối được nghĩa là JVM bị treo

Nguyên nhân có thể là PID sai, quyền attach, VMID không đúng, namespace, filesystem hoặc instrumentation không truy cập được. Xác minh process bằng OS tool trước.

### Remote jstat không hoạt động dù JVM vẫn chạy

Kiểm tra jstatd, RMI registry, port, hostname, network và quyền. Nhớ jstatd bị deprecated for removal trong JDK 24 và không có authentication cho remote clients.

### Script parser hỏng sau khi nâng JDK

jstat output không phải format ổn định. Dừng việc phụ thuộc vào token position; chuyển sang JMX, JFR hoặc API monitoring có cấu trúc.

## 19. Quy trình dùng jstat có trách nhiệm

1. Xác định đúng JDK vendor/version và kiểm tra jstat -help, jstat -options.
2. Xác minh JVM mục tiêu, VMID, host, user và container namespace.
3. Chọn option đúng câu hỏi: gcutil, gc, gccause, class hoặc compiler.
4. Chọn interval/count hợp lý; tránh polling cực dày.
5. Thêm -t nếu cần elapsed time và ghi wall-clock start time riêng.
6. Ghi lại JDK, collector, heap flags, host và process identity.
7. Đọc phần trăm cùng capacity; không kết luận từ một cột.
8. So sánh counter tích lũy bằng delta giữa các mẫu.
9. Dùng GC logs/JFR nếu cần event timeline hoặc pause distribution.
10. Dùng heap dump/histogram nếu cần object-level diagnosis.
11. Dùng OS/NMT metrics nếu cần native memory và process RSS.
12. Không parse output trong automation quan trọng.
13. Không mở jstatd remote nếu chưa đánh giá security; ưu tiên giải pháp monitoring được bảo vệ.
14. Lưu kết quả theo release/runtime và đánh giá lại sau khi nâng JDK.

## 20. Checklist giới hạn cần nhớ

- jstat là experimental/unsupported trong Oracle JDK 24.
- jstat chỉ đọc instrumentation của instrumented HotSpot VM.
- LVMID thường nhưng không nhất thiết là PID hệ điều hành.
- Instrumentation không truy cập được trên FAT32 theo Oracle Troubleshooting Guide.
- Counter là snapshot hoặc số tích lũy, không phải event trace.
- Sampling có thể bỏ lỡ thay đổi ngắn giữa hai lần đọc.
- Timestamp -t là elapsed time từ lúc JVM start, không phải wall-clock.
- Output format có thể thay đổi; không parse bằng script production.
- gcutil là phần trăm theo capacity hiện tại, không phải byte tuyệt đối.
- YGC/FGC và thời gian GC là counter tích lũy, không phải pause distribution.
- gccause chỉ nêu cause gần nhất/hiện tại, không phải lịch sử đầy đủ.
- jstat không cho object graph, retained heap hoặc allocation stack.
- jstat không đo toàn bộ native memory, RSS hoặc container usage.
- Remote monitoring phụ thuộc jstatd/RMI; jstatd bị deprecated for removal từ JDK 24.
- jstatd không xác thực remote clients trong tài liệu JDK 24.
- Dùng JFR, JMX, jcmd, GC logs và OS/container metrics cho câu hỏi chuyên sâu.

## 21. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| jstat | Công cụ đọc performance counters của HotSpot JVM |
| Instrumented VM | JVM công bố dữ liệu instrumentation cho công cụ quản trị |
| VMID | Định danh máy ảo mà jstat dùng để tìm JVM |
| LVMID | Local VM identifier, thường nhưng không nhất thiết là OS PID |
| Sampling interval | Khoảng thời gian giữa hai lần lấy mẫu |
| Count | Số mẫu jstat sẽ in |
| Snapshot | Trạng thái counter tại một thời điểm |
| Cumulative counter | Bộ đếm tích lũy từ lúc JVM khởi chạy |
| YGC / FGC | Số young GC / full GC |
| YGCT / FGCT / GCT | Thời gian GC tích lũy |
| Heap capacity | Dung lượng hiện tại hoặc giới hạn của memory pool |
| Utilization | Tỷ lệ sử dụng capacity |
| Metaspace | Vùng native memory lưu metadata class |
| JFR | Java Flight Recorder, công cụ ghi runtime events |
| JMX MXBean | API quản lý và giám sát JVM có cấu trúc |
| NMT | Native Memory Tracking |
| jstatd | RMI daemon cho phép remote jstat/jps truy cập JVM |
| JMX | Java Management Extensions |
| GC log | Nhật ký sự kiện garbage collection |
| Retained heap | Bộ nhớ được giữ bởi một object cùng các object chỉ nó giữ |

jstat phù hợp để xem nhanh các counter tổng hợp của HotSpot JVM. Những giới hạn về phạm vi instrumentation, sampling, counter tích lũy, output không ổn định, thiếu object-level detail và remote jstatd khiến nó không thể thay thế hệ thống observability. Hãy dùng jstat để định hướng điều tra, rồi chọn JFR, JMX, jcmd, GC logs hoặc OS metrics cho câu hỏi cần độ chi tiết cao hơn.

## Tài liệu tham khảo

- Oracle JDK 24 — [The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- Oracle JDK 24 — [The jstatd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstatd.html)
- Oracle JDK 24 — [Release Notes: jstatd Is Deprecated for Removal](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html)
- Oracle JDK 24 — [Troubleshooting Guide: The jstat Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- Oracle JDK 24 — [Java Flight Recorder and JDK Mission Control](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)