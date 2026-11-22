# Theo dõi JVM: heap, non-heap, GC, luồng và lớp đã nạp

## 1. Bắt đầu từ câu hỏi: JVM đang dùng tài nguyên để làm gì?

Một ứng dụng Java có thể chậm vì nhiều nguyên nhân khác nhau: tạo quá nhiều đối tượng tạm, giữ đối tượng sống quá lâu, cạnh tranh khóa, tạo quá nhiều luồng hoặc liên tục sinh lớp mới. Chỉ nhìn một đường “RAM sử dụng” không phân biệt được các tình huống đó.

Khi theo dõi JVM, cần nối năm nhóm thông tin:

- **Heap:** vùng chứa các đối tượng và mảng Java.
- **Non-heap:** các vùng JVM quản lý ngoài heap, chẳng hạn metadata lớp và mã máy do JIT tạo.
- **GC:** hoạt động thu hồi bộ nhớ, thời gian tạm dừng và dữ liệu liên quan.
- **Luồng:** số luồng đang sống, mức đỉnh và phân bố trạng thái.
- **Lớp đã nạp:** số lớp hiện đang được nạp và lượng lớp đã được dỡ.

Mỗi nhóm trả lời một câu hỏi riêng. Chúng cần được đọc theo thời gian, cùng tải ứng dụng và phiên bản JVM, thay vì dùng một điểm số để kết luận ngay “bị leak” hoặc “cần tăng heap”.

Trong Spring Boot 3.3, Actuator tự cấu hình các binder Micrometer để cung cấp nhiều chỉ số JVM dưới tên bắt đầu bằng `jvm.`. Xem [Spring Boot: JVM Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.jvm).

## 2. Nguồn dữ liệu và bản đồ các nhóm chỉ số

Nhiều phép đo lấy dữ liệu từ các giao diện quản lý JVM, thường gọi là MXBean, cùng các thông báo do JVM phát ra. Micrometer đóng gói chúng thành meter; Actuator cung cấp đường chẩn đoán và tích hợp với hệ thống giám sát.

```text
JVM: vùng nhớ, GC, luồng, class loading
    -> MXBean và thông báo JVM
    -> binder Micrometer
    -> MeterRegistry
    -> Actuator hoặc exporter
    -> hệ thống giám sát và phân tích theo thời gian
```

Một số tên thường gặp với Micrometer 1.13.x:

| Nhóm | Tên meter | Cách đọc chính |
| --- | --- | --- |
| Bộ nhớ | `jvm.memory.used` | Số byte đang dùng của pool |
| Bộ nhớ | `jvm.memory.committed` | Số byte JVM đã được bảo đảm có thể dùng cho pool |
| Bộ nhớ | `jvm.memory.max` | Giới hạn tối đa của pool nếu xác định được |
| Buffer | `jvm.buffer.memory.used`, `jvm.buffer.count` | Bộ nhớ và số buffer theo nhóm JVM cung cấp |
| GC | `jvm.gc.pause` | Số lần và thời gian các sự kiện pause được binder ghi |
| GC | `jvm.gc.live.data.size` | Kích thước dữ liệu sống theo thông tin GC mà binder có |
| GC | `jvm.gc.memory.allocated` | Lượng cấp phát được binder theo dõi/ước lượng |
| Luồng | `jvm.threads.live`, `jvm.threads.daemon` | Số luồng sống và số daemon thread |
| Luồng | `jvm.threads.peak`, `jvm.threads.states` | Đỉnh số luồng và số luồng theo trạng thái |
| Lớp | `jvm.classes.loaded`, `jvm.classes.unloaded` | Số lớp đang nạp và lượng lớp đã dỡ |

Không coi bảng là cam kết mọi JVM/collector đều có đầy đủ mọi meter ngay từ đầu. Tên pool, thông báo GC, khả năng hỗ trợ và một số chi tiết thay đổi theo JVM, JDK, collector và phiên bản Micrometer.

Hãy xem danh sách meter/tag thực tế trước khi viết dashboard. Các binder tương ứng được mô tả tại [Micrometer 1.13: JVM Metrics](https://docs.micrometer.io/micrometer/reference/1.13/reference/jvm.html).

## 3. Heap: phân biệt used, committed và max

### 3.1. Ba số không thể thay thế cho nhau

Heap chứa các đối tượng và mảng được tạo khi chương trình chạy. Đối tượng không còn được truy cập có thể được GC thu hồi, nhưng không nhất thiết được thu ngay sau khi biến mất tham chiếu.

Ba giá trị cần phân biệt:

| Giá trị | Ý nghĩa | Không nên hiểu thành |
| --- | --- | --- |
| `used` | Dung lượng đang được dùng | Toàn bộ RAM vật lý của tiến trình |
| `committed` | Dung lượng đã được bảo đảm có thể dùng cho vùng nhớ | Chỉ phần đang chứa đối tượng sống |
| `max` | Giới hạn tối đa nếu JVM xác định được | Dung lượng chắc chắn còn có thể cấp phát từ hệ điều hành |

Với một ảnh chụp `MemoryUsage`, `used <= committed`. Nếu max xác định được thì committed không lớn hơn max. Giá trị max có thể bằng `-1` khi chưa xác định; đó không phải dung lượng âm. Xem [Java MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

Ví dụ khái niệm: used=300 MiB, committed=512 MiB, max=1024 MiB. Ứng dụng đang dùng 300 MiB trong vùng đã được bảo đảm 512 MiB; giới hạn 1024 MiB không có nghĩa hệ điều hành luôn còn sẵn thêm 512 MiB cho tiến trình.

`1 MiB = 1024 × 1024 byte`. Kiểm tra đơn vị khi so sánh các công cụ; không lẫn byte với MiB hoặc MB thập phân.

### 3.2. Tên pool phụ thuộc collector

Với HotSpot/G1 có thể thấy `G1 Eden Space`, `G1 Survivor Space` và `G1 Old Gen`. Collector khác có thể dùng tên khác hoặc có cách tổ chức vùng nhớ khác.

Các tag thường dùng là:

- `area=heap` hoặc `area=nonheap`.
- `id` là tên pool thực tế.

Không hard-code tên G1 vào dashboard dùng cho mọi JVM. Đổi collector có thể làm một chuỗi theo pool biến mất dù ứng dụng vẫn chạy bình thường.

### 3.3. Không cộng mọi max của các pool rồi chia một cách máy móc

Một số pool báo max=-1; một số giới hạn pool phụ thuộc cách collector tổ chức heap. Cộng các số max mà chưa hiểu pool có thể tạo ra một mẫu số vô nghĩa.

Muốn xem ảnh chụp heap tổng thể ở tầng Java, có thể lấy:

```java
MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
long used = heap.getUsed();
long max = heap.getMax();
```

Đây là đoạn đọc minh họa, cần import `java.lang.management.MemoryUsage` và `ManagementFactory`; không phải chương trình độc lập.

Chỉ tính `used / max` khi max hợp lệ và lớn hơn 0. Với max=-1, nên biểu diễn “chưa xác định”, không thay bằng 0 hoặc hiển thị một phần trăm âm.

### 3.4. Heap cao chưa đủ để kết luận rò rỉ

Heap tăng rồi giảm sau GC là hành vi thường gặp. Điều đáng xem xét là xu hướng dữ liệu còn sống qua nhiều chu kỳ GC dưới tải có thể so sánh được.

Các khả năng cần phân biệt:

- Tải tăng làm nhiều đối tượng cùng tồn tại hơn.
- Cache đang khởi tạo hoặc tăng tới giới hạn dự kiến.
- Đối tượng tạm được cấp phát nhanh nhưng sớm được thu hồi.
- Một cấu trúc giữ tham chiếu lâu hơn dự kiến, làm nền bộ nhớ sau GC tăng.
- Một tác vụ batch tạo đỉnh bộ nhớ tạm thời.

Metrics giúp nhận diện mẫu hình, chưa chỉ ra đối tượng nào bị giữ và chuỗi tham chiếu nào gây ra việc đó. Khi cần kết luận, phải có bằng chứng chi tiết hơn.

## 4. Non-heap và phần bộ nhớ mà heap không giải thích được

### 4.1. Non-heap không phải một vùng duy nhất

Trong HotSpot, có thể gặp:

- **Metaspace:** metadata phục vụ các lớp đã nạp.
- **Compressed Class Space:** dữ liệu lớp theo cơ chế nén con trỏ lớp khi cấu hình/JVM sử dụng.
- **CodeHeap/Code Cache:** mã máy và dữ liệu phục vụ việc biên dịch JIT.

Tên và số pool có thể khác giữa các môi trường. Không gọi mọi non-heap là Metaspace; Code Cache cũng có vai trò riêng.

Một đối tượng Java thông thường và metadata của lớp nó không phải cùng một thứ. Số instance tăng chủ yếu làm thay đổi heap; số lớp động tăng có thể liên quan tới Metaspace và class loading. Các vùng heap/non-heap được JVM mô tả tại [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).

### 4.2. used của heap cộng non-heap không bằng toàn bộ RAM tiến trình

Tiến trình còn có thể dùng bộ nhớ cho stack của platform thread, buffer trực tiếp, thư viện native, cấu trúc nội bộ JVM, ánh xạ tệp và các thành phần khác. Không phải mọi khoản đó đều nằm trong các pool được báo dưới `jvm.memory.*`.

`jvm.buffer.*` giúp quan sát các buffer pool mà JVM cung cấp, nhưng cũng không phải bảng kê toàn bộ bộ nhớ native.

Do đó:

```text
heap used                 != RSS của tiến trình
heap used + nonheap used  != bảng kê đầy đủ mọi byte của tiến trình
-Xmx                      != giới hạn RAM toàn tiến trình
```

RSS là chỉ số về các trang bộ nhớ cư trú mà hệ điều hành quan sát. Nó không cùng định nghĩa với used, committed hoặc không gian địa chỉ được reserve.

Một container có thể chạm giới hạn bộ nhớ trong khi heap chưa đầy. Cần đọc đồng thời dữ liệu JVM với bộ nhớ tiến trình/container và tải hệ thống, thay vì chỉ tăng `-Xmx`.

### 4.3. Đừng dùng một ngưỡng phần trăm chung cho mọi pool

Metaspace có thể báo max=-1 nếu không có giới hạn xác định theo thông tin JVM cung cấp. Khi đó không thể xây một phần trăm “đã dùng trên tối đa” bằng cách chia thông thường.

Với Code Cache, Metaspace và heap, hãy xét quy mô tuyệt đối, xu hướng, giới hạn thực tế, giai đoạn khởi động và đặc tính ứng dụng. Một ngưỡng tùy ý áp cho tất cả pool có thể báo động sai hoặc bỏ qua vấn đề thật.

## 5. GC: xem hoạt động thu hồi, không chỉ nhìn số lần

### 5.1. GC không có nhiệm vụ thu hồi mọi đối tượng còn tham chiếu

GC tìm phần bộ nhớ có thể thu hồi và tái sử dụng. Nếu ứng dụng vẫn giữ một đối tượng qua cache, danh sách hoặc tham chiếu khác, GC không thể tự quyết định rằng đối tượng đó “không còn cần về nghiệp vụ”.

Tốc độ tạo đối tượng, thời gian sống và kích thước dữ liệu còn giữ ảnh hưởng hoạt động GC. Collector có thể có cả pha tạm dừng và công việc chạy đồng thời; “thời gian GC” không phải một con số có cùng ý nghĩa trong mọi cách đo. Xem [Java 21: Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/introduction-garbage-collection-tuning.html).

### 5.2. Đọc pause cùng số lần và thời gian

`jvm.gc.pause` được biểu diễn bằng Timer. Cần xem ít nhất:

- Count: bao nhiêu sự kiện pause đã được ghi nhận.
- Tổng thời gian: tổng thời lượng các mẫu pause được ghi.
- Max/phân bố nếu được cấu hình: có pause dài bất thường hay không.
- Tag thực tế: phân biệt nhóm hành động/nguyên nhân mà collector và binder cung cấp.

Ví dụ khái niệm: 100 pause ngắn và 2 pause rất dài có thể tạo tác động độ trễ khác nhau dù chỉ nhìn một tổng số GC thì không rõ. Cần liên hệ pause với độ trễ yêu cầu, thông lượng và tải cùng thời điểm.

Không đánh đồng tổng pause với CPU mà GC tiêu thụ, hay với toàn bộ thời gian của mọi pha concurrent. Các loại thông tin đó có phạm vi khác nhau.

### 5.3. Không có meter pause ngay từ đầu chưa chắc là không hỗ trợ GC

Một số chuỗi được tạo khi binder nhận được sự kiện phù hợp. Ở JVM vừa khởi động, tên `jvm.gc.pause` có thể chưa xuất hiện hoặc chưa có mẫu.

Tương tự, dữ liệu sống từ GC có thể chưa được cập nhật từ một sự kiện thích hợp. Một giá trị ban đầu bằng 0 không tự chứng minh heap không có đối tượng sống.

Bài thực hành không gọi `System.gc()` để ép ra một kết quả. Khi chẩn đoán ứng dụng, phải xem collector, thời điểm gắn binder, tải đã chạy và khả năng phát thông báo trước khi kết luận.

### 5.4. Dữ liệu cấp phát và dữ liệu sống trả lời hai câu hỏi khác nhau

`jvm.gc.memory.allocated` phản ánh lượng cấp phát được binder theo dõi/ước lượng. `jvm.gc.live.data.size` phản ánh dữ liệu sống theo thông tin GC mà binder có, không phải một lần quét chính xác mọi object tại thời điểm người dùng mở dashboard.

Một ứng dụng có thể cấp phát rất nhanh nhưng giữ lại ít dữ liệu; nó có thể gây áp lực GC mà không có rò rỉ. Ngược lại, lượng dữ liệu giữ lại tăng đều có thể đáng điều tra dù tốc độ cấp phát không đột biến.

Ở tầng MXBean, số lần và thời gian collection có thể có giá trị `-1` nếu collector không cung cấp. Không chuyển giá trị “không xác định” thành một kết luận “không xảy ra GC”. Xem [GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).

### 5.5. Những kết luận cần tránh

- “GC nhiều” chưa đủ nói ứng dụng có leak.
- “Heap giảm sau GC” chưa đủ chứng minh không có đối tượng bị giữ quá lâu.
- “Pause max bằng 0” sau khoảng im lặng không phải bằng chứng lần GC gần nhất chỉ mất 0 giây; thống kê max có thể hết hạn.
- “Tăng heap” có thể thay đổi tần suất GC nhưng không tự sửa cấu trúc giữ dữ liệu sai.
- Tên pool hoặc nhãn GC đổi sau khi thay collector không có nghĩa mọi dữ liệu giám sát vẫn so sánh trực tiếp được.

## 6. Luồng: số lượng, trạng thái và giới hạn quan sát

### 6.1. Live, daemon và peak khác nhau

- `jvm.threads.live`: số platform thread hiện còn sống mà nguồn quản lý JVM quan sát.
- `jvm.threads.daemon`: phần daemon thread trong số đang sống.
- `jvm.threads.peak`: đỉnh số luồng sống kể từ khi JVM bắt đầu hoặc từ lần đỉnh được reset ở nguồn quản lý.
- `jvm.threads.states`: số luồng theo trạng thái tại lúc quan sát.

Peak không phải số luồng đang chạy hiện tại và không có cùng cơ chế hết hạn như max của một Timer. Peak cao có thể còn nguyên sau khi một đợt tải kết thúc.

Nhiều luồng không tự có nghĩa nhiều công việc đang dùng CPU. Cần đọc trạng thái và chức năng của luồng.

### 6.2. Đọc trạng thái đúng nghĩa Java

| Trạng thái | Ý nghĩa chính | Một điều không thể kết luận chỉ từ trạng thái |
| --- | --- | --- |
| `RUNNABLE` | Luồng ở trạng thái có thể thực thi trong JVM | Đang dùng CPU 100% hoặc chắc chắn không chờ tài nguyên hệ điều hành |
| `BLOCKED` | Chờ lấy monitor lock | Đã có deadlock |
| `WAITING` | Chờ một hành động khác mà không có thời hạn | Luồng bị lỗi hoặc bị rò rỉ |
| `TIMED_WAITING` | Chờ với thời hạn | Ứng dụng đang treo |
| `NEW` | Chưa được start | Đã là một live thread đang xử lý |
| `TERMINATED` | Đã kết thúc | Còn đóng góp như một luồng sống |

`BLOCKED` gắn với việc lấy monitor, thường liên quan `synchronized`. Không dùng từ đó như tên chung cho mọi kiểu chờ I/O hoặc chờ một khóa.

Một worker nằm chờ trên hàng đợi rỗng có thể ở WAITING; đó có thể là trạng thái nhàn rỗi bình thường. Muốn kết luận nghẽn, cần xem stack, đối tượng đang chờ, lưu lượng công việc và thời gian trạng thái kéo dài.

Các trạng thái này là trạng thái JVM, không trùng hoàn toàn với trạng thái luồng mà hệ điều hành báo. Xem [Java Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).

### 6.3. Java 21: không coi đây là tổng mọi virtual thread

`ThreadMXBean` trong Java 21 quản lý platform thread và không cung cấp việc theo dõi virtual thread qua các thống kê tương tự. Các binder dựa trên nguồn này không tự biến thành bộ đếm mọi virtual thread.

Vì vậy, khi ứng dụng dùng virtual threads, không diễn giải `jvm.threads.live` là số tác vụ ảo đang tồn tại. Cần phép đo/công cụ phù hợp với loại luồng và phiên bản thư viện đang dùng. Xem [ThreadMXBean Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

Đây cũng là lý do cần biết kiến trúc thực thi trước khi đặt cảnh báo chỉ dựa trên thread count.

### 6.4. Đếm trạng thái không thay thế thread dump

Một tổng số BLOCKED không cho biết ai giữ khóa. Một tổng số WAITING không cho biết tác vụ đang chờ hàng đợi, điều kiện, I/O hay một thao tác phối hợp nào khác.

Khi có dấu hiệu kéo dài, lấy bằng chứng stack/khóa phù hợp và so nhiều thời điểm. Deadlock cần bằng chứng về quan hệ chờ vòng hoặc công cụ phát hiện tương ứng, không phải chỉ có một luồng BLOCKED.

## 7. Lớp đã nạp: phân biệt hiện tại với tổng lịch sử

`ClassLoadingMXBean` phân biệt:

| Đại lượng | Ý nghĩa |
| --- | --- |
| Loaded class count | Số lớp hiện đang được nạp |
| Total loaded class count | Tổng số lớp từng được nạp từ lúc JVM chạy |
| Unloaded class count | Tổng số lớp đã được dỡ từ lúc JVM chạy |

`jvm.classes.loaded` của binder đang dùng là Gauge cho số lớp hiện đang nạp. `jvm.classes.unloaded` theo dõi lượng dỡ tích lũy; không phải “số lớp đang ở trạng thái unloaded”. Xem [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html).

Ứng dụng Spring có thể nạp thêm lớp khi khởi động, khi một tính năng được dùng lần đầu hoặc khi tạo proxy/mã động. Đường loaded tăng trong giai đoạn làm nóng chưa đủ chứng minh classloader leak.

Các điểm cần xem cùng nhau:

- Sau khi làm nóng và dưới tải ổn định, số lớp có tiếp tục tăng không?
- Metaspace tăng cùng tốc độ hay có giai đoạn ổn định?
- Ứng dụng có plugin, biên dịch động, tạo proxy hoặc cơ chế tải lại không?
- Các classloader lẽ ra hết vòng đời còn bị giữ tham chiếu không?
- Dữ liệu có đang so từ cùng một tiến trình hay JVM vừa restart?

Một tên lớp có thể được các classloader khác nhau nạp thành các định nghĩa lớp khác nhau. Chỉ số đếm lớp không đơn giản là số tên tệp `.class` khác nhau trong repository.

Việc dỡ lớp phụ thuộc khả năng thu hồi và cơ chế của JVM/collector. Không kỳ vọng mỗi object bị thu hồi thì lớp tương ứng cũng phải được unload.

## 8. Đọc qua Spring Boot Actuator

### 8.1. Mở đúng endpoint trong môi trường chẩn đoán

Trong một ứng dụng Spring Boot có web và Actuator, cấu hình minh họa:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Đây là cấu hình tích hợp cho ứng dụng có sẵn; chương trình console ở phần sau không khởi động HTTP. Với ứng dụng cần truy cập từ xa, cấu hình xác thực, phân quyền và mạng quản trị phù hợp trước khi expose dữ liệu.

Spring Boot đã tự cấu hình nhiều binder JVM. Không đăng ký lại toàn bộ binder thủ công vào registry của ứng dụng chỉ vì ví dụ console làm như vậy.

### 8.2. Khám phá tên và tag trước khi lọc

Các lệnh dưới dùng `curl.exe` trên Windows. Trên Linux/macOS, thay bằng `curl`. URL minh họa giả sử ứng dụng web đang chạy ở máy cục bộ cổng 8080:

```powershell
curl.exe --silent --show-error "http://127.0.0.1:8080/actuator/metrics"
curl.exe --silent --show-error "http://127.0.0.1:8080/actuator/metrics/jvm.memory.used"
```

Đọc `measurements`, `baseUnit` và `availableTags`. Nếu không lọc, một tên metric có thể đại diện cho nhiều meter/pool được tổng hợp; đó không phải tự động là một vùng nhớ duy nhất.

Lọc heap:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:8080/actuator/metrics/jvm.memory.used" --data-urlencode "tag=area:heap"
```

Nếu danh sách thực tế có `G1 Old Gen`, có thể xem riêng pool đó:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:8080/actuator/metrics/jvm.memory.used" --data-urlencode "tag=area:heap" --data-urlencode "tag=id:G1 Old Gen"
```

`--data-urlencode` giữ đúng tên pool có khoảng trắng. Không giả định tên G1 tồn tại khi chạy collector khác.

Tương tự, đọc:

```powershell
curl.exe --silent --show-error "http://127.0.0.1:8080/actuator/metrics/jvm.threads.live"
curl.exe --silent --show-error "http://127.0.0.1:8080/actuator/metrics/jvm.threads.states"
curl.exe --silent --show-error "http://127.0.0.1:8080/actuator/metrics/jvm.classes.loaded"
curl.exe --silent --show-error "http://127.0.0.1:8080/actuator/metrics/jvm.gc.pause"
```

Nếu metric GC chưa được tạo, kiểm tra điều kiện thu thập và sự kiện trước khi kết luận. Với metric trạng thái luồng, dùng giá trị tag thực tế do endpoint trả về; không tự suy ra cách viết hoa/thường từ enum Java.

Endpoint `metrics` phục vụ khám phá/chẩn đoán, không phải kho lịch sử hay endpoint nên dùng để scrape production. Theo dõi liên tục cần exporter và backend phù hợp. Xem [Spring Boot 3.3: Metrics endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

## 9. Thực hành Java: kiểm tra binder, giá trị chưa xác định và một luồng WAITING

Ví dụ dùng API Java 17+, biên dịch với đích Java 17 và chạy kiểm chứng trên HotSpot JDK 21/G1. Spring Boot parent 3.3.13 quản lý Micrometer 1.13.15.

Mục tiêu là quan sát thật mà không bịa số heap/GC cố định. Chế độ mặc định in các kiểm tra và vòng đời luồng có thể đối chiếu. Chế độ `--values` in các số đo thay đổi theo lần chạy.

Không tạo vòng cấp phát vô hạn, không ép GC và không cố tạo deadlock hoặc OutOfMemoryError.

### 9.1. Cấu trúc và pom.xml

Tạo thư mục riêng:

```text
jvm-signals-lab/
├── pom.xml
└── src/main/java/demo/JvmSignalsDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>jvm-signals-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-core</artifactId>
    </dependency>
  </dependencies>
</project>
```

Chỉ cần `micrometer-core` vì đây là chương trình console đọc meter trực tiếp. Không cần server web hay cơ sở dữ liệu.

### 9.2. Chương trình hoàn chỉnh

Tệp `src/main/java/demo/JvmSignalsDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.binder.jvm.ClassLoaderMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmGcMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.Comparator;
import java.util.Locale;
import java.util.OptionalDouble;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class JvmSignalsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 1
                || (args.length == 1 && !args[0].equals("--values"))) {
            throw new IllegalArgumentException("Use no argument or --values");
        }
        boolean values = args.length == 1;
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        JvmGcMetrics gc = new JvmGcMetrics();

        try {
            new JvmMemoryMetrics().bindTo(registry);
            new JvmThreadMetrics().bindTo(registry);
            new ClassLoaderMetrics().bindTo(registry);
            gc.bindTo(registry);

            System.out.println("heap.meters="
                    + !registry.find("jvm.memory.used").tag("area", "heap")
                    .gauges().isEmpty());
            System.out.println("nonheap.meters="
                    + !registry.find("jvm.memory.used").tag("area", "nonheap")
                    .gauges().isEmpty());
            System.out.println("threads.live.meter="
                    + (registry.find("jvm.threads.live").gauge() != null));
            System.out.println("classes.loaded.meter="
                    + (registry.find("jvm.classes.loaded").gauge() != null));
            System.out.println("classes.unloaded.meter="
                    + (registry.find("jvm.classes.unloaded").functionCounter() != null));
            System.out.println("gc.liveData.meter="
                    + (registry.find("jvm.gc.live.data.size").gauge() != null));

            System.out.println("ratio.demo.known=" + ratioText(512, 1024));
            System.out.println("ratio.demo.undefined=" + ratioText(512, -1));
            observeWorker(registry, values);
        } finally {
            gc.close();
            registry.close();
        }
    }

    private static void observeWorker(
            SimpleMeterRegistry registry, boolean values) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "jvm-lab-worker");

        worker.start();
        try {
            if (!entered.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
            while (worker.getState() != Thread.State.WAITING
                    && System.nanoTime() < deadline) {
                Thread.sleep(1);
            }
            if (worker.getState() != Thread.State.WAITING) {
                throw new IllegalStateException("Worker did not enter WAITING");
            }

            System.out.println("worker.state=" + worker.getState());
            Gauge waiting = registry.find("jvm.threads.states")
                    .tag("state", "waiting").gauge();
            System.out.println("threads.waiting.observed="
                    + (waiting != null && waiting.value() >= 1));
            if (values) {
                printValues(registry);
            }
        } finally {
            release.countDown();
            worker.join(2000);
        }
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not stop");
        }
        System.out.println("worker.state.after=" + worker.getState());
    }

    private static void printValues(SimpleMeterRegistry registry) {
        System.out.println("VALUES: numbers depend on this JVM and observation time");
        registry.find("jvm.memory.used").gauges().stream()
                .sorted(Comparator.comparing(g -> g.getId().toString()))
                .forEach(used -> {
                    String area = used.getId().getTag("area");
                    String id = used.getId().getTag("id");
                    Gauge committed = registry.find("jvm.memory.committed")
                            .tags("area", area, "id", id).gauge();
                    Gauge max = registry.find("jvm.memory.max")
                            .tags("area", area, "id", id).gauge();
                    double u = used.value();
                    double c = committed.value();
                    double m = max.value();
                    System.out.printf(Locale.ROOT,
                            "memory area=%s id=%s used=%.0f committed=%.0f max=%.0f ratio=%s%n",
                            area, id, u, c, m, ratioText(u, m));
                });

        System.out.printf(Locale.ROOT,
                "threads live=%.0f daemon=%.0f peak=%.0f%n",
                registry.get("jvm.threads.live").gauge().value(),
                registry.get("jvm.threads.daemon").gauge().value(),
                registry.get("jvm.threads.peak").gauge().value());
        System.out.printf(Locale.ROOT,
                "classes current=%.0f unloadedTotal=%.0f%n",
                registry.get("jvm.classes.loaded").gauge().value(),
                registry.get("jvm.classes.unloaded").functionCounter().count());

        System.out.println("gc.pause.series="
                + registry.find("jvm.gc.pause").timers().size());
        for (Timer pause : registry.find("jvm.gc.pause").timers()) {
            System.out.printf(Locale.ROOT,
                    "gc.pause tags=%s count=%d totalSeconds=%.6f maxSeconds=%.6f%n",
                    pause.getId().getTags(), pause.count(),
                    pause.totalTime(TimeUnit.SECONDS), pause.max(TimeUnit.SECONDS));
        }
    }

    private static String ratioText(double used, double max) {
        OptionalDouble ratio = usageRatio(used, max);
        return ratio.isPresent()
                ? String.format(Locale.ROOT, "%.1f%%", 100 * ratio.getAsDouble())
                : "unknown";
    }

    private static OptionalDouble usageRatio(double used, double max) {
        if (!Double.isFinite(used) || used < 0
                || !Double.isFinite(max) || max <= 0) {
            return OptionalDouble.empty();
        }
        return OptionalDouble.of(used / max);
    }
}
```

Những chi tiết quan trọng:

1. Các binder được gắn thủ công vì đây là chương trình độc lập, không có auto-configuration của Spring Boot.
2. `JvmGcMetrics` được đóng để gỡ các tài nguyên/listener của binder; registry cũng được đóng trong `finally`.
3. Worker dùng `new Thread` nên là platform thread. Nó chờ một latch để tạo trạng thái WAITING có chủ đích.
4. Latch được nhả và worker được join khi xong, kể cả khi đường quan sát có lỗi.
5. Kiểm tra “có ít nhất một luồng waiting” không giả định tổng số luồng JVM luôn bằng một hằng số.
6. Hai phép tính ratio demo dùng dữ liệu 512/1024 và 512/-1 để kiểm chứng cách xử lý; chúng không giả làm số heap đo được.
7. Các phép đọc pool riêng biệt không phải một giao dịch ảnh chụp nguyên tử toàn JVM. Số liệu có thể thay đổi trong lúc in.

Chương trình không có yêu cầu rằng JVM phải phát sinh một pause GC trong thời gian chạy rất ngắn.

### 9.3. Biên dịch và chạy chế độ kiểm chứng

Chọn JDK 21 và đứng trong thư mục `jvm-signals-lab`. Lần đầu Maven cần mạng để lấy plugin/phụ thuộc.

Trên PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -XX:+UseG1GC -Xms32m -Xmx128m -cp $cp demo.JvmSignalsDemo
```

Trên Linux/macOS, sau cùng lệnh Maven:

```bash
cp="target/classes:$(cat classpath.txt)"
java -XX:+UseG1GC -Xms32m -Xmx128m -cp "$cp" demo.JvmSignalsDemo
```

G1 và các giới hạn heap ở đây xác định bối cảnh phòng thực hành, không phải bộ tham số khuyến nghị cho mọi ứng dụng vận hành.

Stdout của chế độ mặc định trong bối cảnh kiểm chứng:

```text
heap.meters=true
nonheap.meters=true
threads.live.meter=true
classes.loaded.meter=true
classes.unloaded.meter=true
gc.liveData.meter=true
ratio.demo.known=50.0%
ratio.demo.undefined=unknown
worker.state=WAITING
threads.waiting.observed=true
worker.state.after=TERMINATED
```

Các dòng `meter=true` chỉ xác nhận meter đã được đăng ký và tìm thấy. Chúng không có nghĩa mọi subsystem “khỏe” hoặc đã phát sinh GC.

`worker.state=WAITING` cho thấy một luồng đang chờ có chủ đích. `worker.state.after=TERMINATED` cho thấy luồng đã được giải phóng và kết thúc; WAITING trước đó không phải deadlock.

### 9.4. Chạy chế độ in số đo

Trên PowerShell, tiếp tục dùng classpath vừa tạo:

```powershell
java -XX:+UseG1GC -Xms32m -Xmx128m -cp $cp demo.JvmSignalsDemo --values
```

Trên Linux/macOS, dùng `"$cp"` thay `$cp` trong lệnh trên.

Các con số sẽ thay đổi theo máy, JDK, tiến trình và thời điểm. Một phần đầu ra thực tế của một lần chạy JDK 21/G1 là:

```text
memory area=heap id=G1 Eden Space used=6291456 committed=16777216 max=-1 ratio=unknown
memory area=nonheap id=Metaspace used=2228064 committed=2424832 max=-1 ratio=unknown
gc.pause.series=0
```

Không coi những giá trị này là stdout cố định cần khớp ở mọi máy. Chúng minh họa ba điểm:

- Một heap pool như Eden có thể không có max riêng xác định.
- Metaspace có thể báo max=-1; ratio phải là unknown.
- `gc.pause.series=0` ở thời điểm đọc nghĩa là registry lúc đó chưa có chuỗi Timer pause để in; không phải chứng minh GC bị tắt hoặc JVM không có heap.

Các dòng `threads live=...` và `classes current=...` trong chế độ values là số quan sát thực tế. Không cố viết assertion rằng mọi JVM phải có cùng số luồng hoặc cùng số lớp.

## 10. Đọc phối hợp để hình thành giả thuyết đúng

| Mẫu hình quan sát | Giả thuyết cần kiểm tra | Bằng chứng nên bổ sung |
| --- | --- | --- |
| Heap tăng rồi giảm theo chu kỳ, độ trễ ổn định | Hành vi cấp phát/thu hồi bình thường | Tải, allocation rate, nền sau GC qua nhiều chu kỳ |
| Nền bộ nhớ sau GC tăng dưới tải tương đương | Dữ liệu giữ lại tăng, cache tăng hoặc rò rỉ tham chiếu | Loại đối tượng, đường giữ tham chiếu, giới hạn cache |
| Heap chưa đầy nhưng RAM tiến trình/container cao | Native memory, buffer, stack hoặc phần khác ngoài heap | Bộ nhớ tiến trình/container, buffer, số luồng, dữ liệu native phù hợp |
| Pause dài đi cùng tăng độ trễ | GC có thể góp phần làm chậm | Dòng thời gian GC, request latency và collector đang dùng |
| Nhiều BLOCKED kéo dài, thông lượng giảm | Cạnh tranh monitor hoặc một đường giữ khóa lâu | Thread dump và đối tượng/luồng giữ khóa |
| Nhiều WAITING nhưng hàng đợi rỗng, hệ thống đáp ứng tốt | Worker nhàn rỗi có thể bình thường | Stack của worker và cấu hình pool |
| Live thread tăng liên tục, không về nền sau tải | Tạo luồng quá mức hoặc thiếu đóng tài nguyên | Nguồn tạo luồng, tên luồng, executor và vòng đời |
| Lớp đang nạp và Metaspace cùng tăng sau làm nóng | Sinh lớp động nhiều hoặc classloader bị giữ | Thống kê classloader và cơ chế proxy/plugin/reload |
| Peak thread cao nhưng live hiện thấp | Đã có một đợt đỉnh trước đó | Thời điểm đợt tải và lịch sử live, không chỉ peak |

Các hàng là giả thuyết, không phải chẩn đoán tự động. Ví dụ “nền sau GC tăng” còn có thể do tải dữ liệu tăng hợp lệ; “nhiều waiting” còn có thể do thiếu tài nguyên ở nơi khác. Cần tìm chuỗi nguyên nhân bằng bằng chứng.

Không cộng dữ liệu của nhiều instance rồi kết luận một JVM cụ thể đã đầy heap. Giữ khả năng tách theo instance, phiên bản triển khai, collector và giai đoạn vòng đời.

Tương tự, không so một đỉnh ở phút này với mức trung bình tải của giờ khác rồi coi đó là quan hệ trực tiếp. Các chỉ số phải được đối chiếu trên dòng thời gian phù hợp.

## 11. Từ metrics sang công cụ chẩn đoán

Metrics giúp biết **khi nào** và **nhóm nào** đáng điều tra. Chúng không chứa stack chi tiết của mọi luồng hoặc đường tham chiếu tới từng object.

Với HotSpot/JDK có hỗ trợ, `jcmd` cung cấp các lệnh chẩn đoán. Ví dụ PowerShell sau để người vận hành tự chọn đúng PID đang cần kiểm tra:

```powershell
jcmd -l
$targetJvmPid = Read-Host "Nhap PID cua JVM can kiem tra"
jcmd $targetJvmPid help
jcmd $targetJvmPid GC.heap_info
jcmd $targetJvmPid Thread.print
jcmd $targetJvmPid VM.classloader_stats
```

Các lệnh này dành cho một JVM **vẫn đang chạy**, thường trên cùng máy và với quyền người dùng phù hợp. Chương trình console ở trên kết thúc nhanh nên không giả định PID của nó còn tồn tại sau khi đã chạy xong.

Lệnh được hỗ trợ và chi phí có thể khác theo JVM. `Thread.print` lấy thông tin stack, `VM.classloader_stats` lấy thống kê classloader; chúng không tự sửa nguyên nhân sự cố. Xem [The jcmd Command, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Khi cần quan sát chi tiết theo thời gian, có thể dùng JFR; khi cần xác định object bị giữ, có thể cần heap dump và phân tích tham chiếu. Những thao tác đó có chi phí và có thể chứa dữ liệu ứng dụng, nên chọn đúng thời điểm/phạm vi và cách lưu trữ. Không tự động tạo heap dump liên tục chỉ vì một điểm heap cao.

Bài này tập trung vào đọc chỉ số và chọn hướng điều tra, không hướng dẫn thay collector hoặc điều chỉnh một bộ cờ GC sản xuất khi chưa có bằng chứng.

## 12. Những lỗi diễn giải thường gặp

- Coi `jvm.memory.used` không lọc tag là “heap hiện tại”.
- Cộng mọi pool max, kể cả max=-1, rồi tính phần trăm.
- Coi committed là toàn bộ RAM vật lý đang dùng hoặc coi `-Xmx` là giới hạn cả tiến trình.
- Coi mọi non-heap là Metaspace.
- Coi số GC tăng là bằng chứng chắc chắn có rò rỉ.
- Coi không thấy `jvm.gc.pause` lúc vừa khởi động là bằng chứng GC không chạy.
- Coi RUNNABLE là đang dùng CPU tối đa.
- Coi WAITING là deadlock hoặc mọi BLOCKED là deadlock.
- Coi peak thread là live thread hiện tại.
- Coi bộ đếm platform thread là số lượng mọi virtual thread trên Java 21.
- Coi `jvm.classes.loaded` là tổng lớp từng nạp trong suốt vòng đời.
- Coi class count tăng khi khởi động là classloader leak.
- Mong các con số heap, class và thread cố định giữa mọi lần chạy.
- Đăng ký lại binder JVM trong ứng dụng Boot mà chưa kiểm tra auto-configuration đã làm việc đó.

Một thiết kế dashboard tốt phải làm rõ vùng nhớ, đơn vị, pool/instance, loại thống kê và thời gian, thay vì chỉ có những nhãn chung như “memory” hoặc “threads”.

## 13. Tự kiểm tra

**Bài tập 1:** Một pool có used=64 MiB và max=-1. Tính phần trăm dùng bộ nhớ như thế nào?

**Đáp án:** không có mẫu số tối đa hợp lệ để tính. Hiển thị dung lượng tuyệt đối và trạng thái chưa xác định cho ratio; không chia cho -1 hoặc thay max bằng 0.

**Bài tập 2:** Heap chỉ dùng một nửa giới hạn nhưng container gần hết bộ nhớ. Có thể loại trừ vấn đề bộ nhớ không?

**Đáp án:** không. Cần kiểm tra phần ngoài heap, buffer/native memory, stack, số luồng và dữ liệu bộ nhớ tiến trình/container. Heap chỉ là một phần.

**Bài tập 3:** Có 50 worker ở WAITING, hàng đợi rỗng và request vẫn đáp ứng tốt. Có thể kết luận deadlock không?

**Đáp án:** không. Worker có thể đang chờ công việc bình thường. Cần stack và quan hệ chờ khóa để kết luận nghẽn/deadlock.

**Bài tập 4:** `jvm.classes.loaded` tăng sau lần đầu gọi một tính năng. Điều cần kiểm tra tiếp là gì?

**Đáp án:** quan sát sau giai đoạn làm nóng và dưới tải có thể so sánh, liên hệ Metaspace và cơ chế nạp/sinh lớp. Một lần tăng không đủ chứng minh leak.

**Bài tập 5:** Live thread hiện tại là 20, peak là 200. Có phải đang có 200 luồng sống không?

**Đáp án:** không. Peak thể hiện đỉnh trước đó theo vòng đời/reset của nguồn quản lý; số sống hiện tại là đại lượng live.

**Bài tập 6:** JVM vừa chạy, meter dữ liệu GC đã được đăng ký nhưng chưa có Timer pause. Điều đó nói gì?

**Đáp án:** mới xác nhận binder/meter đã có ở phạm vi tương ứng. Cần xem thông báo GC và mẫu được ghi; không tự suy ra có/không có mọi hoạt động GC từ một tên metric chưa xuất hiện.

Theo dõi JVM hiệu quả là nối vùng nhớ, hoạt động GC, luồng và class loading với cùng bối cảnh tải. Metrics giúp đặt giả thuyết có cơ sở; kết luận về nguyên nhân cần những bằng chứng chi tiết đúng với giả thuyết đó.
