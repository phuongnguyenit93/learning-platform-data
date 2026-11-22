# Đọc GC log, heap usage và thông tin cấp phát

Để hiểu garbage collection (GC) đang ảnh hưởng thế nào đến một ứng dụng Java, cần kết hợp ba nhóm dữ liệu: **GC log** cho biết collector đã làm gì và mất bao lâu, **heap usage** cho biết bộ nhớ heap đang được sử dụng ra sao, còn **allocation information** cho biết ứng dụng tạo object với tốc độ nào và ở những vị trí nào.

Không nên kết luận ứng dụng thiếu heap chỉ vì mức sử dụng heap tăng, hoặc đổi garbage collector chỉ vì thấy một pause dài. Hãy đối chiếu thời điểm GC với latency, throughput, CPU, allocation rate và trạng thái bộ nhớ sau GC. Trong Java 21, các công cụ chính để thực hiện việc này là unified logging qua `-Xlog`, `jcmd`, Java Flight Recorder (JFR), JDK Mission Control (JMC) và các MXBean trong Java Management API.

## 1. Ba nhóm dữ liệu cần quan sát

| Nhóm dữ liệu | Trả lời câu hỏi | Công cụ thường dùng |
|---|---|---|
| GC log và GC events | GC chạy khi nào, vì sao, pause bao lâu, thu hồi được bao nhiêu? | Unified logging, JFR |
| Heap usage | Heap đã dùng, đã commit và giới hạn tối đa là bao nhiêu? | `jcmd GC.heap_info`, MemoryMXBean, MemoryPoolMXBean |
| Allocation information | Object được tạo nhiều ở đâu, loại nào, tốc độ cấp phát ra sao? | JFR allocation events, JMC |

Ba nhóm dữ liệu bổ trợ cho nhau:

- GC log cho thấy thời điểm heap pressure hoặc collection tăng.
- Heap usage cho thấy mức dùng bộ nhớ trước và sau collection.
- Allocation profile giúp tìm code tạo ra lượng object lớn hoặc nhiều object sống lâu.

Cần quan sát cùng khoảng thời gian và cùng workload. Một allocation profile thu trong lúc khởi động không nhất thiết đại diện cho workload steady-state của production.

## 2. Bật GC log bằng unified logging

Java 21 sử dụng unified logging để cấu hình log của JVM. Có thể bật log GC và thông tin heap bằng tùy chọn `-Xlog`:

```bash
java \
  -Xms2g -Xmx2g \
  -Xlog:gc*=info,gc+heap=debug,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar application.jar
```

Ý nghĩa các phần chính:

- `gc*=info`: ghi các log có tag bắt đầu bằng `gc` ở mức info.
- `gc+heap=debug`: ghi chi tiết hơn về trạng thái heap ở các log có tag `gc` và `heap`.
- `safepoint=info`: ghi thông tin safepoint liên quan đến thời điểm JVM dừng các application thread.
- `file=gc.log`: ghi ra file thay vì chỉ xuất ra console.
- `time,uptime,level,tags`: thêm thời gian thực, thời gian JVM đã chạy, mức log và tag.
- `filecount` và `filesize`: giới hạn số file và kích thước mỗi file khi xoay vòng log.

Có thể dùng cùng cấu hình log khi thử G1 hoặc Generational ZGC. Tên tag và nội dung chi tiết phụ thuộc collector, nên cần đọc log theo collector đang chạy.

Ví dụ bật G1:

```bash
java -XX:+UseG1GC \
  -Xms2g -Xmx2g \
  -Xlog:gc*=info,gc+heap=debug,safepoint=info:file=g1.log:time,uptime,level,tags \
  -jar application.jar
```

Ví dụ bật Generational ZGC trên Java 21:

```bash
java -XX:+UseZGC -XX:+ZGenerational \
  -Xms2g -Xmx2g \
  -Xlog:gc*=info,gc+heap=debug,safepoint=info:file=zgc.log:time,uptime,level,tags \
  -jar application.jar
```

Trên Java 21, Generational ZGC cần được bật tường minh bằng `-XX:+UseZGC -XX:+ZGenerational`. Khi chạy trên JDK mới hơn, hãy kiểm tra mặc định của đúng phiên bản runtime; chế độ generational đã trở thành mặc định của ZGC từ JDK 23.

Không nên bật mức log chi tiết nhất trong thời gian dài nếu chưa đánh giá dung lượng log và overhead. Hãy bắt đầu với mức info, tăng độ chi tiết trong một lần chẩn đoán ngắn khi cần tìm nguyên nhân.

## 3. Đọc cấu trúc một dòng GC log

Với G1, một dòng pause thường có dạng tương tự:

```text
[12.345s][info][gc] GC(18) Pause Young (Normal) (G1 Evacuation Pause) 512M->128M(2048M) 8.7ms
```

Có thể đọc các thành phần như sau:

- `12.345s`: thời gian kể từ khi JVM khởi động.
- `GC(18)`: định danh của chu kỳ hoặc sự kiện GC trong log.
- `Pause Young`: loại collection, ở đây là young collection.
- `512M->128M`: mức heap được báo cáo trước và sau collection trong dòng log.
- `(2048M)`: dung lượng heap được commit/hiển thị trong ngữ cảnh log đó.
- `8.7ms`: thời gian pause được ghi nhận cho sự kiện.

Định dạng cụ thể thay đổi theo collector và phiên bản JDK. Không nên áp đặt cách đọc `before -> after (capacity)` của một dòng G1 lên mọi dòng ZGC. Hãy xem tag, tên phase và tài liệu của collector tương ứng.

Các tên sự kiện thường gặp khi đọc log G1:

- **Pause Young:** thu gom các vùng young.
- **Pause Mixed:** thu gom young cùng một số region thuộc old generation.
- **Concurrent Mark Cycle:** chu kỳ đánh dấu concurrent phục vụ việc xác định object còn sống ở old generation.
- **Pause Full:** full garbage collection; nếu xuất hiện thường xuyên, cần tìm nguyên nhân và áp lực bộ nhớ liên quan.

Một dòng pause đơn lẻ chưa cho biết GC có phải nguyên nhân làm request chậm hay không. Cần so thời điểm pause với latency của ứng dụng và số lượng request đang xử lý.

## 4. Đọc log của Generational ZGC

Generational ZGC cũng ghi các sự kiện GC và thông tin heap, nhưng cách thể hiện phase khác G1. Log có thể mô tả chu kỳ collection, các pha pause ngắn, các pha concurrent và dung lượng heap theo cách riêng của ZGC.

Khi đọc log ZGC, tập trung vào:

- Thời điểm bắt đầu và kết thúc mỗi chu kỳ GC.
- Collection thuộc young generation hay old generation nếu log cung cấp thông tin đó.
- Thời gian các pha pause và tổng thời gian chu kỳ.
- Heap capacity, mức dùng bộ nhớ và dung lượng thu hồi.
- Allocation stall hoặc dấu hiệu ứng dụng phải chờ GC cung cấp thêm vùng cấp phát.
- Các dấu hiệu bộ nhớ tăng liên tục hoặc không đủ headroom.

ZGC thực hiện phần lớn công việc thu gom đồng thời với ứng dụng, nhưng không có nghĩa là không có pause. Cũng không nên so sánh tổng thời gian một chu kỳ concurrent của ZGC với thời gian pause stop-the-world của G1 như thể đó là cùng một chỉ số. Hãy so sánh pause time với pause time, đồng thời đánh giá CPU, throughput và latency đầu cuối.

## 5. Phân biệt heap used, committed và max

Heap usage thường được biểu diễn bằng ba giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `used` | Dung lượng heap hiện đang được sử dụng |
| `committed` | Dung lượng heap JVM đã commit và sẵn sàng sử dụng |
| `max` | Giới hạn heap tối đa mà JVM có thể sử dụng; có thể không xác định |

Ví dụ, nếu heap có:

- used = 900 MB
- committed = 1.5 GB
- max = 2 GB

thì JVM đang dùng khoảng 900 MB trong vùng heap đã commit 1.5 GB, và có thể mở rộng vùng commit tới giới hạn 2 GB nếu điều kiện runtime cho phép.

Không đồng nhất committed heap với RSS (resident set size) của process. RSS còn bao gồm các vùng bộ nhớ ngoài heap như metaspace, code cache, thread stack, direct buffer và native allocation. Ngược lại, committed heap cũng không nhất thiết đồng nghĩa toàn bộ vùng đó đang nằm trong RAM vật lý tại cùng thời điểm.

Giá trị `max` có thể là `-1` nếu runtime không xác định được giới hạn. Khi phân tích, hãy kiểm tra cả heap usage lẫn memory limit của container hoặc máy chủ.

## 6. Xem heap usage trực tiếp bằng jcmd

Lệnh `jcmd` có thể yêu cầu JVM đang chạy cung cấp thông tin heap:

```bash
jcmd <pid> GC.heap_info
```

Trong đó `<pid>` là process ID của JVM. Kết quả thường cho biết loại heap, dung lượng đã dùng/đã commit và một số thông tin riêng của collector. Với G1, output có thể có region size và số region theo trạng thái; với ZGC, output thể hiện thông tin heap theo cơ chế của ZGC.

Có thể xem các lệnh diagnostic mà JVM hỗ trợ:

```bash
jcmd <pid> help
```

Khi cần kiểm tra một snapshot, hãy ghi lại thời điểm lấy mẫu và tải đang chạy. Heap usage có thể thay đổi ngay sau khi lệnh trả kết quả vì ứng dụng vẫn tiếp tục cấp phát và GC vẫn tiếp tục hoạt động.

Không nên lấy một lần `GC.heap_info` làm kết luận về xu hướng. Hãy lấy nhiều mẫu theo chu kỳ hoặc dùng JFR/MXBean để quan sát theo thời gian.

## 7. Theo dõi heap bằng MemoryMXBean

Java Management API cung cấp `MemoryMXBean` để đọc thông tin bộ nhớ từ trong ứng dụng. Có thể dùng `getHeapMemoryUsage()` để lấy used, committed, init và max:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

class HeapMetrics {
    static void printHeapUsage() {
        MemoryUsage usage =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

        System.out.printf(
                "Heap used=%d MB, committed=%d MB, max=%d MB%n",
                toMb(usage.getUsed()),
                toMb(usage.getCommitted()),
                toMb(usage.getMax())
        );
    }

    private static long toMb(long bytes) {
        return bytes < 0 ? -1 : bytes / (1024 * 1024);
    }
}
```

`MemoryUsage` cũng có `getInit()`. Các giá trị có thể là `-1` nếu runtime không xác định được một mức cụ thể. Không nên giả định mọi trường đều luôn có giá trị dương.

Nếu cần theo dõi từng memory pool, dùng `MemoryPoolMXBean`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

class PoolMetrics {
    static void printPools() {
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {

            var usage = pool.getUsage();

            if (usage == null) {
                continue;
            }

            System.out.printf(
                    "%s: used=%d MB, committed=%d MB, max=%d MB%n",
                    pool.getName(),
                    toMb(usage.getUsed()),
                    toMb(usage.getCommitted()),
                    toMb(usage.getMax())
            );
        }
    }

    private static long toMb(long bytes) {
        return bytes < 0 ? -1 : bytes / (1024 * 1024);
    }
}
```

Tên và số lượng memory pool phụ thuộc collector và JDK. Không nên hard-code tên pool của G1 rồi giả định chúng tồn tại khi đổi sang ZGC. Hãy đọc danh sách pool tại runtime và sử dụng tên, loại pool cùng collector đang hoạt động để diễn giải.

## 8. Heap usage sau GC và live set

Mức heap used trước GC thường gồm cả object còn sống lẫn object đã không còn được tham chiếu nhưng chưa được thu hồi. Vì vậy, used cao trước GC không tự động có nghĩa ứng dụng bị memory leak.

Mức used sau một collection phù hợp có thể giúp ước lượng live set, tức lượng object còn cần giữ lại. Tuy nhiên, đây chỉ là một chỉ báo:

- Young collection chỉ xử lý phạm vi generation tương ứng, không đại diện toàn bộ live set.
- Với collector concurrent, heap usage có thể thay đổi trong lúc GC đang chạy.
- Object có thể tiếp tục được cấp phát trong khi GC xử lý.
- Kết quả phụ thuộc loại collection, collector và thời điểm lấy số liệu.

Nếu mức used sau các chu kỳ collection đầy đủ liên tục tăng trong cùng workload, hãy điều tra object retention, cache không giới hạn, listener hoặc collection giữ tham chiếu ngoài dự kiến. Cần dùng heap dump hoặc phân tích object graph để xác nhận nguyên nhân; không kết luận memory leak chỉ từ một đường biểu diễn heap.

## 9. Xem class histogram và heap dump

Khi cần biết loại object nào chiếm nhiều heap, có thể dùng class histogram:

```bash
jcmd <pid> GC.class_histogram
```

Histogram cung cấp số lượng instance và tổng dung lượng ước tính theo class. Nó giúp tìm các class có số lượng lớn hoặc chiếm nhiều bộ nhớ, chẳng hạn byte array, String, DTO hoặc node của collection.

Đây là thao tác có thể gây ảnh hưởng đáng kể tới ứng dụng và có thể yêu cầu GC/safepoint tùy tùy chọn và runtime. Không nên chạy lặp lại thường xuyên trên production mà chưa đánh giá tác động.

Khi cần phân tích sâu object graph, có thể tạo heap dump:

```bash
jcmd <pid> GC.heap_dump /path/to/application.hprof
```

Heap dump có thể rất lớn, tiêu tốn I/O và gây pause hoặc kích hoạt collection tùy tùy chọn. Hãy bảo đảm đủ dung lượng lưu trữ, quyền truy cập file và chính sách bảo vệ dữ liệu trước khi thực hiện. Heap dump có thể chứa dữ liệu nhạy cảm đang nằm trong bộ nhớ của ứng dụng.

Histogram cho biết class nào chiếm dung lượng; heap dump cho phép phân tích đường tham chiếu và lý do object vẫn còn sống. Hai công cụ phục vụ mức độ điều tra khác nhau.

## 10. Đọc allocation information bằng JFR

JFR có thể ghi nhận các mẫu cấp phát object cùng stack trace. Trên Java 21, có thể bắt đầu recording ngắn bằng `jcmd`:

```bash
jcmd <pid> JFR.start name=AllocationProfile settings=profile duration=60s filename=allocation.jfr
```

Sau khi recording kết thúc, xem tổng quan:

```bash
jfr summary allocation.jfr
```

In các mẫu cấp phát:

```bash
jfr print --events jdk.ObjectAllocationSample allocation.jfr
```

Event `jdk.ObjectAllocationSample` cung cấp thông tin về class được cấp phát, thread, stack trace và trọng số mẫu (`weight`). Trọng số giúp ước lượng lượng bộ nhớ được cấp phát tương ứng với mẫu; đây là dữ liệu sampling, không phải danh sách chính xác mọi object được tạo ra.

Trong JMC, có thể xem allocation theo class, thread hoặc call stack để tìm vị trí tạo object đáng chú ý. Hãy chú ý những stack trace lặp lại và tổng trọng số lớn, sau đó xác minh bằng profiling hoặc benchmark có kiểm soát.

## 11. Phân biệt allocation sampling và allocation events chi tiết

JFR có một số event liên quan tới cấp phát:

| Event | Ý nghĩa |
|---|---|
| `jdk.ObjectAllocationSample` | Lấy mẫu cấp phát để ước lượng hoạt động allocation với overhead phù hợp cho profiling |
| `jdk.ObjectAllocationInNewTLAB` | Ghi nhận sự kiện cấp phát liên quan tới việc cấp một TLAB mới |
| `jdk.ObjectAllocationOutsideTLAB` | Ghi nhận cấp phát object nằm ngoài TLAB |

TLAB (Thread-Local Allocation Buffer) là vùng cấp phát riêng cho từng thread, giúp nhiều lần cấp phát object nhỏ diễn ra nhanh mà không cần tranh chấp một điểm cấp phát chung.

Các event TLAB không nên được hiểu là một bản ghi cho mọi object được cấp phát bên trong TLAB. `ObjectAllocationInNewTLAB` gắn với việc cấp TLAB mới; `ObjectAllocationOutsideTLAB` ghi nhận cấp phát ngoài TLAB. Bật các event chi tiết có thể làm tăng overhead và lượng dữ liệu ghi, vì vậy nên dùng khi cần điều tra sâu trong một khoảng thời gian ngắn.

Để bắt đầu phân tích allocation trong production, thường nên dùng cấu hình JFR profile và `ObjectAllocationSample`. Chỉ chuyển sang event chi tiết hơn khi sampling chưa đủ để xác định nguyên nhân.

## 12. Ước lượng allocation rate

Allocation rate biểu thị lượng bộ nhớ ứng dụng cấp phát trong một đơn vị thời gian, thường dùng MB/s hoặc GB/s. Có thể ước lượng từ tổng trọng số allocation sample trong một khoảng thời gian chia cho độ dài khoảng đó:

`Allocation rate ≈ estimated allocated bytes / elapsed seconds`

Đây là ước lượng dựa trên sampling, không phải phép đếm chính xác từng byte. Cần dùng cùng cấu hình recording và workload khi so sánh trước/sau thay đổi.

Ví dụ, nếu JFR ước lượng ứng dụng cấp phát khoảng 3 GB trong 60 giây, allocation rate trung bình xấp xỉ 51.2 MB/s theo đơn vị nhị phân. Một số công cụ hiển thị MB theo hệ thập phân; hãy kiểm tra đơn vị trước khi so sánh.

Allocation rate cao không tự động là vấn đề. Nếu phần lớn object chết nhanh và collector xử lý tốt, ứng dụng vẫn có thể hoạt động ổn định. Ngược lại, allocation rate vừa phải nhưng nhiều object được giữ lại lâu có thể làm live set tăng và gây áp lực heap.

## 13. Kết hợp GC log, heap usage và allocation profile

Các nguồn dữ liệu cần được ghép theo cùng timeline:

1. GC log cho biết thời điểm collection, loại collection, pause và mức heap được báo cáo.
2. Heap metrics cho biết used/committed/max theo chu kỳ.
3. Allocation profile cho biết class và call stack tạo nhiều object.
4. Application metrics cho biết latency, throughput và số request đang xử lý.

Ví dụ cách diễn giải:

| Quan sát | Giả thuyết cần kiểm tra |
|---|---|
| Heap used tăng nhanh giữa các lần GC, giảm mạnh sau GC | Allocation rate cao, nhiều object ngắn hạn |
| Heap used sau collection tăng dần qua nhiều chu kỳ | Object retention tăng, cache hoặc cấu trúc dữ liệu giữ tham chiếu |
| G1 có pause tăng đồng thời p99 tăng | GC pause có thể góp phần vào tail latency |
| ZGC pause thấp nhưng CPU tăng | Concurrent GC có thể đang tiêu thụ thêm CPU |
| Allocation sample tập trung vào một method tạo nhiều byte array | Buffer hoặc chuyển đổi dữ liệu có thể tạo allocation pressure |
| Heap ổn định nhưng RSS tăng | Kiểm tra native memory, direct buffer, thread stack và các vùng ngoài heap |
| Allocation rate cao nhưng live set ổn định | Nhiều object ngắn hạn; tối ưu allocation chỉ khi có lợi ích đo được |

Đây là các giả thuyết, không phải kết luận tự động. Hãy đối chiếu stack trace, thời điểm và workload trước khi thay đổi code hoặc collector.

## 14. Heap và native memory là hai phạm vi khác nhau

Heap chứa object Java được quản lý bởi garbage collector. Process memory còn có các vùng ngoài heap:

- Metaspace lưu metadata của class.
- Code cache lưu mã máy được JIT compiler tạo ra.
- Thread stack dùng cho các thread.
- Direct buffer và native allocation có thể nằm ngoài heap.
- Thư viện native và runtime có thể cấp phát bộ nhớ riêng.

Nếu heap used ổn định nhưng process RSS tiếp tục tăng, không nên mặc định đó là Java heap leak. Có thể cần quan sát native memory.

Native Memory Tracking (NMT) có thể được bật khi khởi động JVM:

```bash
java -XX:NativeMemoryTracking=summary -jar application.jar
```

Sau đó xem tổng quan:

```bash
jcmd <pid> VM.native_memory summary
```

Có thể lấy baseline và so sánh thay đổi:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT theo dõi nhiều nhóm native memory do JVM quản lý, nhưng không phải công cụ đo mọi byte RSS hoặc mọi allocation do thư viện native bên ngoài thực hiện. NMT cũng có overhead và cần bật từ lúc JVM khởi động; không thể bật hồi tố cho một process đang chạy mà chưa cấu hình.

## 15. Quy trình quan sát runtime thực tế

Một quy trình cơ bản có thể triển khai như sau:

1. Bật unified GC logging với mức info và file rotation phù hợp.
2. Ghi JFR trong khoảng thời gian đại diện cho workload.
3. Thu thập heap usage bằng `jcmd GC.heap_info` hoặc MemoryMXBean theo chu kỳ.
4. Dùng JFR `ObjectAllocationSample` để tìm class và stack trace có allocation lớn.
5. Đối chiếu GC pause, heap trend, allocation rate và p95/p99 latency.
6. Nếu nghi ngờ object retention, lấy class histogram hoặc heap dump trong cửa sổ điều tra có kiểm soát.
7. Nếu RSS tăng mà heap không tăng tương ứng, xem xét NMT và các vùng native.
8. Sau khi thay đổi, chạy lại cùng workload và so sánh cùng bộ chỉ số.

Đừng thay đổi heap size hoặc collector trước khi có baseline. Nếu thay nhiều biến cùng lúc, sẽ khó xác định yếu tố nào tạo ra khác biệt.

## 16. Các lỗi thường gặp khi đọc dữ liệu GC và memory

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Coi heap used cao là memory leak | Used có thể gồm object chưa được thu gom | So sánh mức sau collection và kiểm tra object retention |
| Coi committed là RSS | Hai số đo phạm vi bộ nhớ khác nhau | Theo dõi heap, process RSS và native memory riêng |
| So sánh pause G1 với tổng thời gian concurrent cycle của ZGC | Không cùng loại thời gian | So sánh pause với pause; đánh giá CPU và throughput riêng |
| Cho rằng JFR allocation sample đếm chính xác mọi object | Đây là dữ liệu sampling có trọng số | Dùng để tìm xu hướng và stack đáng chú ý, không coi là số đếm tuyệt đối |
| Chạy heap dump thường xuyên trên production | Có thể gây pause, I/O lớn và chứa dữ liệu nhạy cảm | Chỉ thực hiện khi có kế hoạch và kiểm soát tác động |
| Hard-code tên memory pool của một collector | Tên và số pool phụ thuộc runtime | Liệt kê pool qua MemoryPoolMXBean |
| Bật log/event chi tiết liên tục | Tăng overhead và dung lượng dữ liệu | Bắt đầu bằng cấu hình vừa phải, tăng chi tiết trong thời gian ngắn |
| Đổi collector chỉ vì một pause dài | Có thể latency đến từ I/O, lock hoặc CPU | Tương quan GC với application metrics và profile |

## 17. Nguyên tắc áp dụng trong Java 21

Khi quan sát runtime Java 21, hãy dùng unified logging để ghi GC và safepoint, JFR để thu thập GC/allocation events, `jcmd` để truy vấn trạng thái heap và MXBean nếu cần xuất metric từ trong ứng dụng.

Luôn phân biệt ba khái niệm:

- **Heap usage** cho biết lượng heap đang được sử dụng, đã commit và giới hạn.
- **Allocation rate** cho biết tốc độ tạo object, thường được ước lượng từ JFR sampling.
- **Live set/retained objects** cho biết lượng object thực sự còn được giữ lại và cần phân tích object graph để xác nhận.

Khi kết hợp các dữ liệu trên với latency và throughput của ứng dụng, có thể xác định GC đang là nguyên nhân chính, chỉ là một yếu tố phụ hay hoàn toàn không liên quan tới vấn đề hiệu năng. Đây là cơ sở để quyết định tối ưu allocation, điều chỉnh heap, thay đổi cấu trúc dữ liệu hoặc benchmark collector khác.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java SE 21 — Unified Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
- [Oracle Java SE 21 API — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 21 API — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Oracle Java SE 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
