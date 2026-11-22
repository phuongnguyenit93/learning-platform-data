# ZGC: thu gom đồng thời hướng đến thời gian dừng thấp

## 1. ZGC giải quyết vấn đề gì?

**ZGC (Z Garbage Collector)** là bộ thu gom rác của HotSpot JVM được thiết kế để giảm tối đa **stop-the-world GC pauses**, nhất là với dịch vụ Java nhạy cảm với tail latency hoặc sử dụng heap lớn. Thay vì dừng mọi Java application threads để thực hiện phần lớn marking và di chuyển đối tượng, ZGC làm gần như toàn bộ những công việc nặng **concurrently** trong khi ứng dụng vẫn chạy.

Tuy nhiên cần phân biệt:

- **Pause time thấp** không có nghĩa hoàn toàn không có pause.
- **GC cycle elapsed time** không giống **tổng thời gian ứng dụng bị dừng**.
- **End-to-end response latency** còn phụ thuộc CPU scheduling, lock contention, I/O, JIT, database, network và allocation stalls.
- **Concurrent GC** tiêu thụ CPU, cache/memory bandwidth và heap headroom; không phải miễn phí.
- **ZGC** không tự giải phóng những objects vẫn còn reachable qua cache/listener/ThreadLocal dù nghiệp vụ không còn cần.
- ZGC của **Java 17** và **Generational ZGC trong Java 21+** có khác biệt quan trọng về thuật toán và tham số.

Bài này trình bày kiến trúc **HotSpot ZGC trên Java 17** trước, rồi so sánh những thay đổi ở Java 21–25. Đây là **implementation detail** của HotSpot, không phải một thuật toán GC bắt buộc trong Java Language Specification hay JVMS.

### Mục tiêu

Sau bài học bạn có thể:

1. Phân biệt **GC pause**, **concurrent GC cycle**, **allocation stall**, **live set**, **allocation rate**, **heap headroom** và **throughput**.
2. Vẽ các pha cơ bản của ZGC non-generational Java 17: Pause Mark Start, Concurrent Mark, Pause Mark End, Concurrent Prepare for Relocation, Pause Relocate Start, Concurrent Relocate.
3. Mô tả **colored pointers**, **load barriers**, forwarding/remapping và tại sao Java object identity vẫn đúng khi GC di chuyển đối tượng concurrently.
4. Giải thích tại sao ZGC phải có **free memory headroom** để tiếp tục đáp ứng allocations trong khi GC chưa hoàn tất.
5. Phân biệt non-generational ZGC Java 17 với Generational ZGC Java 21, mặc định từ Java 23 và chỉ còn generational từ Java 24.
6. Bật collector, dùng GC logs, hiểu các cờ **UseZGC**, **Xmx**, **Xms**, **SoftMaxHeapSize**, **ConcGCThreads**, các tùy chọn trả unused heap về OS.
7. Đánh giá ZGC với G1/Parallel trên workload thật bằng pause distribution, p99 latency, throughput, CPU/RSS và allocation stalls.

## 2. Latency và throughput không phải một

Giả sử dịch vụ API có ngân sách **p99 request dưới 30 ms**. Một số nguyên nhân request chậm:

~~~text
Request #1:
  Business execution     12 ms
  GC STW overlap          1 ms
  Scheduler/network       2 ms
  Total                  15 ms

Request #2:
  Business execution     12 ms
  GC STW overlap         40 ms
  Scheduler/network       2 ms
  Total                  54 ms

Request #3:
  Business execution     12 ms
  Database lock         300 ms
  GC STW overlap          0 ms
  Total                 312 ms
~~~

ZGC có thể cải thiện trường hợp pause GC lớn như Request #2, nhưng không thể tự sửa database lock ở Request #3.

| Chỉ số | Nó đo gì? | Vì sao quan trọng? |
| --- | --- | --- |
| **GC pause time** | Khoảng dừng ứng dụng do GC | Mục tiêu trực tiếp của ZGC |
| **Concurrent cycle elapsed time** | Thời gian một vòng GC bao gồm concurrent phases | Không bằng STW duration |
| **p50/p95/p99/p99.9 request latency** | Phân phối độ trễ end-to-end | Chỉ số người dùng/SLA |
| **Throughput** | Transactions/requests hoàn thành theo thời gian | CPU dành cho GC có thể ảnh hưởng |
| **Allocation rate** | Byte objects được ứng dụng tạo ra mỗi giây | GC có theo kịp không? |
| **Live set** | Dung lượng objects còn reachable | Nhu cầu bộ nhớ tối thiểu về mặt đồ thị |
| **Heap headroom** | Dung lượng đủ cho allocations khi GC concurrent | Tránh allocation stalls |
| **GC CPU usage** | CPU sử dụng bởi các threads GC | Đánh đổi với application throughput |
| **RSS/committed/reserved** | Các dạng đo footprint khác nhau | Không được đồng nhất với Xmx |

Một bộ thu gom có **pause ngắn nhất** không nhất thiết có **throughput cao nhất** hoặc footprint thấp nhất. Tùy SLA, G1 hoặc Parallel có thể là lựa chọn hợp lý hơn.

## 3. ZGC đã thay đổi qua các phiên bản Java

| Java | Trạng thái ZGC | Cách hiểu |
| --- | --- | --- |
| **JDK 11** | JEP 333: experimental ZGC | Phiên bản ban đầu cần flag experimental |
| **JDK 15** | JEP 377: production ZGC | Bật bằng -XX:+UseZGC |
| **JDK 16** | Cải tiến concurrent thread-stack processing và relocation | Giảm một số nguồn STW |
| **JDK 17** | ZGC production, **non-generational** | Dùng làm baseline kiến trúc trong bài |
| **JDK 21** | JEP 439: **Generational ZGC** là tùy chọn | -XX:+UseZGC -XX:+ZGenerational |
| **JDK 23** | JEP 474: chọn generational mode làm mặc định cho ZGC | Non-generational bị deprecated |
| **JDK 24** | JEP 490: loại bỏ non-generational mode | Không dùng ZGenerational làm selector nữa |
| **JDK 25 LTS** | ZGC generational-only | Theo dõi tài liệu tuning đúng JDK 25 |

**Cạm bẫy lớn:** Nếu đọc kiến trúc ZGC Java 17, không tự thêm young/old generations vào collector ấy. Nếu chạy Java 25, không tiếp tục dạy ZGC là một collector non-generational duy nhất. Việc chọn collector và quan sát logs phải theo **JDK vendor, major version, build**.

### Lệnh chọn ZGC trên HotSpot Java 17

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

**app.jar** là tên giả định của một executable JAR. Bật ZGC trên JDK 17 **không cần** -XX:+UnlockExperimentalVMOptions chỉ vì ZGC; tùy chọn này đã production từ JDK 15.

Java 21 khi muốn **Generational ZGC**:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar
~~~

JDK 24+:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

Cờ **ZGenerational** bị loại bỏ từ JDK 24; không sao chép nguyên command Java 21 sang JDK 25 mà bỏ qua warning về option obsolete.

## 4. Concurrent GC và Stop-The-World (STW)

**STW** là giai đoạn JVM tạm dừng các threads ứng dụng để phối hợp collector/runtime. Các bộ GC truyền thống có thể thực hiện nhiều tracing/evacuation trong STW.

**Concurrent** nghĩa là GC threads làm một phần lớn công việc cùng lúc Java application threads tiếp tục thực thi. ZGC đưa marking, phần lớn reference processing và relocation ra khỏi những pause dài.

~~~text
Thời gian ------------------------------------------------------------->

Application:
  RUN ---- [P1] ----- RUN ------------ [P2] ------ RUN ---- [P3] --- RUN

ZGC:
           MarkStart  Concurrent Mark/Remap  MarkEnd
                     Concurrent Prepare Relocation
                                                    RelocateStart
                                                      Concurrent Relocate
~~~

Hình là **sơ đồ khái niệm**, không phải thời gian thực được đo. Tên/pha thay đổi theo JDK, nhất là Generational ZGC.

### 4.1. Vì sao vẫn có những pause ngắn?

ZGC cần các điểm đồng bộ để bắt đầu/kết thúc một số giai đoạn và thiết lập global phase state. Điểm quan trọng là tránh đem công việc có độ phức tạp tỉ lệ lớn với live heap vào các synchronization pauses.

Vì thế ZGC thường có các pause **rất ngắn so với một số STW collectors**, nhưng **không thể hứa 0 ms tuyệt đối** hoặc một con số cố định cho mọi OS/cpu/workload.

### 4.2. “Pause không tăng theo heap size” là mục tiêu thiết kế

ZGC được thiết kế để pause time không phụ thuộc trực tiếp vào việc heap có 1 GiB hay hàng trăm GiB như một stop-the-world full-heap traversal. Nhưng môi trường thực tế vẫn có:

- CPU contention, CPU quotas/cgroup throttling.
- Scheduler/safepoint coordination.
- JNI/native activities.
- Concurrent GC starvation hoặc memory pressure.
- OS page faults, container memory limits.
- JDK/architecture-specific bugs/overheads.
- Data races, locks và downstream I/O của ứng dụng.

Đọc “pause size-independent” như một **đặc tính kiến trúc chủ đích**, không phải lời cam kết p99 latency của mọi request.

## 5. Vòng đời một ZGC cycle trên Java 17

ZGC non-generational classic có thể diễn đạt qua các bước:

~~~text
1. Pause Mark Start                     (STW nhỏ)
            |
2. Concurrent Mark / Remap              (mutators chạy)
            |
3. Pause Mark End                       (STW nhỏ)
            |
4. Concurrent Prepare for Relocation    (mutators chạy)
            |
5. Pause Relocate Start                 (STW nhỏ)
            |
6. Concurrent Relocate                  (mutators chạy)
            |
7. Completion, reuse/free pages, work theo cycle protocol
~~~

### 5.1. Pause Mark Start

ZGC đồng bộ ngắn để mở đầu một vòng marking và thiết lập trạng thái phù hợp. Không phải lúc JVM quét mọi object của cả heap trong pause này.

### 5.2. Concurrent Mark / Remap

GC xác định objects cần được giữ sống theo reachability từ GC roots trong khi mutators có thể tạo và sửa references. Colored pointers/barriers duy trì điều kiện an toàn cho bộ đánh dấu. Với các ZGC versions, một số remapping work được kết hợp với concurrent marking.

**Không hiểu “đang mark” là mọi Java threads đã bị dừng.**

### 5.3. Pause Mark End

Đồng bộ ngắn để hoàn tất marking theo protocol của collector. Những chi tiết termination, weak roots và fixpoint phụ thuộc triển khai/phiên bản.

### 5.4. Concurrent Prepare for Relocation

Collector xác định các ZPages/regions thích hợp để di chuyển live objects, chuẩn bị forwarding metadata, lựa chọn tập relocation và phần bookkeeping liên quan. Không cần di chuyển tất cả objects trong mọi cycle.

### 5.5. Pause Relocate Start

Điểm đồng bộ ngắn báo chuyển pha bắt đầu relocation. Mutators sau pause vẫn cần nhìn thấy Java objects hợp lệ, kể cả nếu objects bị collector di chuyển.

### 5.6. Concurrent Relocate

Collector di chuyển các live objects được chọn trong khi ứng dụng tiếp tục chạy. Barriers/forwarding giúp objects được tìm đúng vị trí và references được cập nhật hoặc sửa dần.

**GC cycle dài không có nghĩa STW pause dài.** Nếu log cho thấy một concurrent phase chạy 60 ms, điều đó không đồng nghĩa application threads đã bị dừng suốt 60 ms.

## 6. Thách thức: chuyển đối tượng trong khi ứng dụng đang đọc

Giả sử **Node X** ở địa chỉ giả định A. Mutator đang giữ reference r:

~~~text
t0:
  Mutator: r ------------> Node X @ A

t1:
  Collector concurrently moves X from A to B

t2:
  Mutator attempts to dereference r
~~~

Nếu VM đơn giản thay đổi địa chỉ của X trong khi mutator vẫn theo reference cũ mà không có protocol, việc đọc có thể không an toàn. ZGC dùng kết hợp:

- **Colored pointers** chứa thông tin trạng thái trong reference encoding.
- **Load barriers** kiểm tra reference khi đọc.
- **Forwarding/relocation metadata** nhận diện vị trí mới.
- **Healing/remapping** cập nhật reference hoặc trả referent đúng cho mutator.

### 6.1. Colored pointers là gì?

“Color” là **metadata nội bộ** được biểu diễn trong một số bit của reference encoding. Nó giúp collector nhận biết reference có trạng thái phù hợp với phase hiện hành không.

~~~text
ZGC encoded reference (khái niệm, không phải bit layout cố định):

+-------------------------+------------------------+
| metadata/color bits     | address information    |
+-------------------------+------------------------+
           |
           v
     Load barrier kiểm tra reference
           |
           +-- trạng thái good -> fast path
           |
           +-- trạng thái bad -> slow path, remap/mark/heal
~~~

**Đừng học thuộc rằng bit N luôn là marked trên mọi JDK**. Pointer coloring và số bit/địa chỉ ảo thay đổi theo các phiên bản. Một mô tả JDK 19 hoặc Generational ZGC không được coi là cấu trúc bất biến của JDK 17.

Màu không phải một field Java mà ứng dụng có thể đọc từ **Object**. **System.identityHashCode(x)** và **x.toString()** không cho memory address hoặc GC color.

### 6.2. Colored pointers khác compressed oops

**Compressed oops** trong HotSpot thông thường mã hóa nhiều object references trong slots hẹp. Colored pointers của ZGC phục vụ GC state/relocation, có các ràng buộc khác về pointer encoding. Không mặc định ZGC Java 17 dùng narrowOop 4 byte chỉ vì một JVM 64-bit khác với G1 có UseCompressedOops=true.

Kiểm tra actual **UseCompressedOops**, **UseCompressedClassPointers** và other final flags trên bản HotSpot đang chạy. Object reference compression và class pointer compression là hai cơ chế riêng.

## 7. Load barriers và fast/slow path

Load barrier là đoạn code do compiler/VM thêm vào đường đọc reference khi cần để kiểm tra/tái tạo reference hợp lệ.

Pseudo-code:

~~~text
function loadObjectReference(slot):
    ref = load(slot)

    if gcStateOf(ref) is good:
        return validObject(ref)

    return slowPathFix(slot, ref)
~~~

**Pseudo-code** chỉ mô tả trách nhiệm; không có public Java API tên slowPathFix hoặc gcStateOf, và HotSpot có thể tối ưu/inlining các thao tác khác nhau.

### 7.1. Vì sao fast path rất quan trọng?

Java code đọc tham chiếu vô cùng thường xuyên. Nếu mọi load đều phải đi qua slow path với lock/metadata lookup đắt đỏ, throughput sẽ giảm mạnh. ZGC tối ưu trạng thái **good** để common-case rẻ nhất có thể.

Khi bad state, slow path có thể:

- Mark referent nếu cần.
- Tìm vị trí object sau relocation.
- Cập nhật/heal slot chứa reference.
- Đồng bộ với runtime relocation protocol.
- Trả reference đúng cho Java code.

### 7.2. Lazy healing

Một reference cũ không nhất thiết được cập nhật trong mọi vị trí ngay lập tức khi collector di chuyển object. Việc cập nhật có thể diễn ra khi mutator load reference hoặc khi các GC phases xử lý phù hợp.

Vì thế **“đã relocate xong object” không đồng nghĩa “mọi slot trỏ tới object đã bị thay bằng địa chỉ mới ở cùng một millisecond”**.

### 7.3. Load barrier của GC không phải volatile memory fence

GC barrier phục vụ memory safety và liveness/relocation invariants. **Java Memory Model (JMM)** và happens-before giữa application threads là chuyện khác.

Hai threads cùng ghi một reference field không synchronized vẫn có thể có data race. Chuyển từ G1 sang ZGC không biến field đó thành volatile hoặc lock.

## 8. ZPages và concurrent compaction

ZGC quản lý heap bằng các **ZPages** với cơ chế cấp phát/di chuyển thích hợp. Trong các ZGC designs, pages có thể thuộc những size classes khác nhau để xử lý objects nhỏ/vừa/lớn.

Sơ đồ khái niệm:

~~~text
Before:
  Page P1: [Live A][Dead ][Live B][Dead ][Live C]
  Page P2: [Live D][Dead ][Dead  ][Live E]

Chosen relocation set:
  P1, P2 hoặc subset tùy heuristics

Concurrent relocate:
  Chuyển những live objects khi cần

After (mô hình):
  Page Q: [Live A][Live B][Live C][Live D][Live E][free...]

Các references được remap/heal theo GC protocol.
~~~

Không khẳng định mọi cycle move tất cả objects, mọi pages có cùng kích thước hoặc object order sau GC giống hình. Collector chọn pages/regions dựa trên live bytes, fragmentation, khả năng có free space và cost-benefit.

### 8.1. Relocation cần memory headroom

Trong lúc copy object từ vùng cũ sang vùng mới, VM có thể cần đủ space để giữ object mới trước khi có thể giải phóng hoàn toàn vùng cũ. Cộng với mutator vẫn cấp phát, một heap **đầy sát live set** dễ dẫn tới allocation stalls.

Tức là một low-pause collector có thể **tốn thêm memory** để đạt độ trễ thấp. Không thể chỉ đặt -Xmx bằng số live heap vừa đủ trên giấy rồi mong ZGC vận hành tốt ở mọi workload.

## 9. Heap headroom và allocation rate

Khái niệm capacity planning:

~~~text
Heap cần thiết ≈
   Live object graph
 + bytes cấp phát khi concurrent GC đang chạy
 + relocation / fragmentation overhead
 + burst capacity / safety margin
~~~

Công thức trên chỉ là **mô hình lập ngân sách**, không phải thuật toán ZGC tính Xmx.

Ví dụ giả định:

~~~text
Live set                 5 GiB
Allocation rate          600 MiB/s
Concurrent cycle length  3 seconds

New allocations phát sinh trong 3 s:
  600 * 3 = 1800 MiB ≈ 1.76 GiB
~~~

Không phải mọi object vừa cấp phát đều sống đến cuối GC, nên không thể cộng máy móc 5 GiB + 1.76 GiB để bảo đảm đủ. Nhưng ví dụ giúp thấy **vì sao có allocation headroom**: trong lúc collector làm việc, mutator vẫn tạo objects mới.

### 9.1. Allocation stall

Khi GC không theo kịp allocation, heap không có space để phục vụ một số allocations và threads có thể chờ GC tiến triển hoặc VM cần xử lý pressure.

Hệ quả:

- **GC pause histogram vẫn đẹp**, nhưng request latency có spike.
- CPU GC có thể cạnh tranh với mutators.
- GC cycles quá thường xuyên có thể làm throughput giảm.
- Có thể cần tăng Xmx, giảm allocation rate, tăng CPU headroom hoặc xem lại GC tuning.

**Allocation stall không đồng nghĩa STW GC pause.** Khi chẩn đoán p99, phải đo cả hai.

### 9.2. Gần 100% heap utilization không phải mục tiêu của ZGC

Một heap luôn sát Xmx có thể khiến ZGC phải làm việc liên tục hoặc thiếu space relocation. Tăng heap có thể giúp giảm stalls nhưng gây chi phí RAM. Ngược lại cấp quá nhiều heap để đạt p99 không tốt nếu container đang thiếu native memory. Cần cân bằng:

- Tail-latency SLO.
- Live set + burst allocation.
- CPU cores/quotas.
- RSS/container limits.
- GC cycle frequency và bandwidth.
- Chi phí hạ tầng.

## 10. Các tùy chọn JVM quan trọng

| Option | Vai trò | Ghi chú |
| --- | --- | --- |
| **-XX:+UseZGC** | Chọn ZGC | Chỉ trên HotSpot/JDK build hỗ trợ |
| **-Xmx<size>** | Hard max Java heap | Cờ quan trọng nhất để bảo đảm headroom |
| **-Xms<size>** | Initial/minimum heap capacity được cấu hình | Có thể ảnh hưởng uncommit behavior |
| **-XX:SoftMaxHeapSize=<size>** | Mục tiêu mềm để ZGC cố hoạt động dưới mức đó | Có thể vượt để tránh allocation problems |
| **-XX:ConcGCThreads=<n>** | Concurrent GC thread parallelism | GC CPU contention với mutator |
| **-XX:ParallelGCThreads=<n>** | Parallelism trong các phần công việc được VM chọn | Không đồng nghĩa number of application threads |
| **-XX:+PrintFlagsFinal** | In final JVM flag values | Đọc cùng startup arguments |
| **-Xlog:gc=info** | GC summary logging | Dùng -Xlog:help xem tags |
| **-Xlog:gc*=debug** | Diagnostics chi tiết hơn | Có thể log rất nhiều, tăng overhead |
| **-XX:+/-ZUncommit** | Cho phép/ngăn uncommit unused heap ở builds hỗ trợ | Implementation-specific |
| **-XX:ZUncommitDelay=<seconds>** | Điều khiển delay uncommit ở builds hỗ trợ | Không quyết định GC reclaim objects đúng deadline |

### 10.1. Xmx quan trọng nhất

Tài liệu tuning của ZGC nhấn mạnh đặt max heap đủ lớn để vừa chứa **live set**, vừa có space cho allocations khi GC đang concurrent. Không suy từ “pause vài ms” rằng heap có thể nhỏ tới sát live data.

### 10.2. SoftMaxHeapSize không phải hard cap

Lệnh minh họa:

~~~bash
java -XX:+UseZGC -Xms256m -Xmx2g -XX:SoftMaxHeapSize=1g MyService
~~~

MyService phải là class có main và đã được biên dịch. SoftMaxHeapSize là mục tiêu mềm; collector có thể dùng nhiều hơn để tránh allocation problems. **Xmx** vẫn là giới hạn tối đa chính.

### 10.3. ConcGCThreads: quá nhiều không phải lúc nào tốt

Nếu server có quota CPU hạn chế, tăng concurrent GC threads có thể khiến GC tiến nhanh hơn nhưng lấy CPU của request threads; latency/thoroughput có thể xấu đi.

Ngược lại, giảm threads quá mức có thể khiến GC không kịp hoàn thành, gây stalls. Hãy:

1. Đo GC CPU + mutator CPU.
2. Quan sát concurrent cycle length/stalls.
3. Chọn số threads theo workloads, CPU quotas.
4. Benchmark với nhiều lần chạy.
5. Tránh tune từ một biểu đồ pause duy nhất.

### 10.4. Uncommit unused heap

ZGC có thể trả một số committed pages không dùng tới cho OS trong điều kiện phù hợp. Điều này giảm footprint với workload biến động, nhưng:

- Uncommit không xảy ra tức thời khi object unreachable.
- Heap **reserved** vẫn có thể lớn.
- Xms=Xmx thường giảm khả năng hạ committed heap dưới minimum.
- Heap committed khác RSS/native memory.
- Flags và heuristics thay đổi theo JDK.

Không lấy một con số RSS của ZGC rồi suy rằng nó đã tạo nhiều bản sao dữ liệu nếu một triển khai có multiple virtual address views.

## 11. Generational ZGC từ Java 21

Nền tảng của generational GC là quan sát: **nhiều objects chết trẻ**. Một hệ chia young/old có thể thu gom young thường xuyên, tránh liên tục scan toàn bộ live old graph.

**ZGC non-generational JDK 17:** whole-heap marking theo cycle, không có Young/Old ZGC generations của JEP 439.

**Generational ZGC JDK 21+:** young/old generations, concurrent mechanisms và barriers thích hợp để duy trì liveness/cross-generation references.

~~~text
ZGC Java 17:
  Heap -> một generation logic
  Concurrent whole-heap marking/relocation cycles

Generational ZGC:
  Heap
    +-- Young generation: objects mới, nhiều objects chết sớm
    +-- Old generation: objects sống lâu
  Collect generations theo policies riêng
~~~

Đây là **mô hình học**, không mô tả layout địa chỉ chính xác.

### 11.1. Tại sao Generational ZGC có lợi?

Với workload tạo rất nhiều objects trẻ nhưng giữ một old live set lớn, quét lại toàn heap thường xuyên có thể gây chi phí CPU. Generational collection có thể tập trung vào young graph trong nhiều đợt, giảm:

- Work trên những objects sống lâu.
- GC CPU overhead.
- Allocation-stall risk.
- Heap headroom cần để duy trì tiến độ trong những trường hợp phù hợp.

Không bảo đảm mọi workload đều được lợi như nhau; nếu objects được promote/lifetime khác nhau, hiệu quả phụ thuộc pattern.

### 11.2. Write/store barriers bổ sung

Generational ZGC cần biết những tham chiếu **old → young** và các cập nhật graph để thu gom từng generation an toàn. Vì thế các thiết kế hiện đại có **store/write barrier** bên cạnh load barrier/colored-pointer scheme.

Đừng áp câu “ZGC chỉ có load barrier, không có write barrier” cho mọi JDK. Cũng không được coi ZGC là bản sao chính xác **G1 card table/remembered set**; các cấu trúc tracking khác nhau theo collector.

### 11.3. Versioned commands

~~~bash
# JDK 17: non-generational
java -XX:+UseZGC -jar app.jar

# JDK 21: chọn generational
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar

# JDK 24/25: generational-only
java -XX:+UseZGC -jar app.jar
~~~

Dùng startup script rõ phiên bản; cờ không còn hỗ trợ có thể được cảnh báo/bỏ qua, tạo cảm giác sai rằng đang chạy mode mình chọn.

## 12. So sánh ZGC, G1, Parallel và Serial

| Mục tiêu | ZGC | G1 | Parallel | Serial |
| --- | --- | --- | --- | --- |
| Ưu tiên chính | GC pauses rất thấp | Cân bằng throughput/latency | Throughput trên nhiều CPU | Đơn giản cho heap nhỏ |
| Concurrent marking | Có | Có trong old-cycle work | Nhiều công việc STW | Chủ yếu STW |
| Concurrent relocation | Có, là trọng tâm | Evacuation CSet thường trong pauses | Không tương đương | Không tương đương |
| Heap headroom | Cực kỳ quan trọng | Cũng cần evacuation space | Cần adequate free space | Cần adequate free space |
| CPU overhead | Concurrent GC/barrier work | Concurrent/parallel GC work, RSet | Nhiều CPU khi pause | Ít cấu trúc nhưng pause lớn hơn có thể |
| Chọn khi | p99/tail-latency rất quan trọng | Server workloads phổ biến | Throughput-centric batch | Nhỏ/ít threads |

Bảng chỉ là **định hướng**, không phải bằng chứng rằng ZGC luôn “thắng G1”. Collector mặc định còn phụ thuộc version và resource constraints. Với workload thiếu CPU, GC đồng thời có thể ảnh hưởng throughput hơn dự kiến.

### 12.1. Quy trình chọn

- Nếu p99 bị chi phối bởi GC pauses, cân nhắc ZGC.
- Nếu CPU đã quá tải, đánh giá concurrent GC cost.
- Nếu heap nhỏ, G1/Serial có thể đủ tốt và đơn giản.
- Nếu chạy batch có thể chấp nhận pauses dài, Parallel throughput có thể phù hợp.
- Nếu services thay đổi tải mạnh, đánh giá memory elasticity/uncommit.
- Nếu JVM nằm trong cgroup/container, đo actual CPU quota và native memory overhead.

## 13. Demo Java 17+: tính đúng của reference graph không phụ thuộc GC

Tạo **ZgcReachabilityDemo.java**:

~~~java
public class ZgcReachabilityDemo {
    static final class Node {
        final int id;
        Node next;
        Node(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Node first = new Node(1);
        Node second = new Node(2);
        Node third = new Node(3);

        first.next = second;
        second.next = third;
        third.next = first; // cycle

        System.out.println("first=" + first.id);
        System.out.println("second=" + first.next.id);
        System.out.println("third=" + first.next.next.id);
        System.out.println("cycle=" +
                (first.next.next.next == first));
    }
}
~~~

Biên dịch, chạy trên HotSpot JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ZgcReachabilityDemo.java
java -XX:+UseZGC ZgcReachabilityDemo
~~~

**Stdout chỉ từ Java code (khi không bật thêm logging):**

~~~text
first=1
second=2
third=3
cycle=true
~~~

Giải thích: Cycle first→second→third→first vẫn reachable khi main dùng first. Một khi không còn root path tới nhóm, cả cycle có thể được GC reclaim. ZGC không được làm thay đổi Java reference identity, bất kể objects có được di chuyển.

Chạy cùng bytecode với:

~~~bash
java -XX:+UseG1GC ZgcReachabilityDemo
~~~

Java-level output giống nhau; khác biệt collector là cách/quãng thời gian GC xử lý heap. Một chương trình nhỏ thế này có thể không kích hoạt GC cycle nào.

## 14. Demo Java 17+: allocation workload để quan sát GC

Tạo **ZgcAllocationLab.java**:

~~~java
public class ZgcAllocationLab {
    private static final int BLOCK = 256 * 1024;
    private static final int KEEP = 16;
    private static final int ROUNDS = 120;
    private static final int TEMP_PER_ROUND = 32;

    public static void main(String[] args) {
        byte[][] retained = new byte[KEEP][];
        for (int i = 0; i < KEEP; i++) {
            retained[i] = new byte[BLOCK];
            retained[i][0] = (byte) i;
        }

        long checksum = 0;
        for (int r = 0; r < ROUNDS; r++) {
            for (int j = 0; j < TEMP_PER_ROUND; j++) {
                byte[] temp = new byte[BLOCK];
                temp[0] = 1;
                checksum += temp[0];
            }
        }

        long retainedBytes = (long) KEEP * BLOCK;
        System.out.println("retainedBlocks=" + retained.length);
        System.out.println("retainedBytes=" + retainedBytes);
        System.out.println("checksum=" + checksum);
        java.lang.ref.Reference.reachabilityFence(retained);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 ZgcAllocationLab.java
java -XX:+UseZGC -Xms64m -Xmx128m ZgcAllocationLab
~~~

**Stdout của Java logic (nếu chương trình chạy xong, không có thêm logging):**

~~~text
retainedBlocks=16
retainedBytes=4194304
checksum=3840
~~~

Phân tích:

- Retained array payload = 16 × 256 KiB = **4 MiB**, chưa tính các array headers.
- Có 120 × 32 = **3840 vòng tạo temporary byte[]** ở Java source.
- Mỗi temporary[0] được gán 1 rồi cộng vào checksum, nên tổng là **3840**.
- Nhiều temporary arrays có thể chết sớm, tạo áp lực allocation theo thời gian.
- **Reference.reachabilityFence(retained)** giữ strong reachability cho retained graph tới điểm đó theo API; không ép GC hoặc pin địa chỉ.
- JIT có thể tối ưu khi bảo toàn ngữ nghĩa; **số byte allocation thực cần đo bằng profiler/JFR**, không suy chắc từ source.
- Số collections, pauses, heap regions và timing không phải stdout cố định.

### 14.1. Bật GC log khi chạy demo

~~~bash
java -XX:+UseZGC -Xms64m -Xmx128m -Xlog:gc* ZgcAllocationLab
~~~

Có thể xuất nhiều GC lines với format tùy JDK, workload và heuristics. Dòng application stdout vẫn cùng nội dung nếu chương trình hoàn thành, nhưng log có thể xuất hiện xen kẽ.

Lệnh Bash xuống dòng:

~~~bash
java -XX:+UseZGC -Xms64m -Xmx128m \
  -Xlog:gc*=debug ZgcAllocationLab
~~~

Trong Windows PowerShell/Command Prompt, nên đặt tất cả flags trên một dòng; Bash backslash continuation không dùng y nguyên.

### 14.2. So sánh G1

~~~bash
java -XX:+UseG1GC -Xms64m -Xmx128m -Xlog:gc* ZgcAllocationLab
~~~

Đo trên nhiều lần chạy, bỏ warm-up bias và không dùng demo nhỏ này để tuyên bố collector nào tốt nhất production.

### 14.3. Rủi ro của demo

- -Xmx128m quá nhỏ cho một số machine/workload có thể tăng GC frequency hoặc stalls.
- GC events có thể ít hoặc nhiều tùy VM/JIT/OS; không đoán chính xác.
- Logs debug/trace có thể tốn dung lượng.
- Không dùng System.gc() để biến một test thành một timing guarantee.
- Khi muốn benchmark chuyên nghiệp, dùng JMH/JFR và workload giống thực.

## 15. Demo Java 17+: theo dõi GC beans

Java ManagementFactory cung cấp **GarbageCollectorMXBean**. Tên beans/count/times phụ thuộc JVM/collector và có thể thay đổi giữa versions.

Tạo **GcBeansDemo.java**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class GcBeansDemo {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();

        System.out.println("hasBeans=" + !beans.isEmpty());

        for (GarbageCollectorMXBean bean : beans) {
            System.out.println("name=" + bean.getName());
            System.out.println("count=" + bean.getCollectionCount());
            System.out.println("timeMs=" + bean.getCollectionTime());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GcBeansDemo.java
java -XX:+UseZGC GcBeansDemo
~~~

**Không có một stdout chính xác chung** cho bean names/collection counts/timings trên mọi JDK và tiến trình, nên bài không bịa output. Bài thực hành là quan sát **hiện có những bean nào** và đối chiếu dữ liệu với GC logs.

Trong HotSpot Java 17, có thể thấy beans cho các ZGC pauses/cycles. Nhưng khi chuyển sang Generational ZGC JDK25, đừng hardcode tên Java17 beans làm điều kiện logic.

## 16. Phân tích GC logs của ZGC

Bắt đầu bằng logs nhẹ:

~~~bash
java -XX:+UseZGC -Xlog:gc=info ZgcAllocationLab
~~~

Chi tiết hơn cho thí nghiệm:

~~~bash
java -XX:+UseZGC -Xlog:gc*=debug ZgcAllocationLab
~~~

Các tên tag/cấu trúc có thể khác giữa JDK 17/21/25; để xem cấu hình logging mà **runtime hiện tại** hỗ trợ:

~~~bash
java -Xlog:help
~~~

### 16.1. Phân biệt pause, concurrent cycle và stall

| Dữ kiện | Đọc đúng |
| --- | --- |
| **Pause Mark Start** | Một synchronization pause |
| **Pause Mark End** | Một synchronization pause |
| **Pause Relocate Start** | Một synchronization pause |
| **Concurrent Mark** | GC làm việc trong khi application còn chạy |
| **Concurrent Relocate** | GC có thể di chuyển objects đồng thời với mutators |
| **Allocation Stall** | Mutator có thể phải chờ cấp phát; cần xử lý như nguồn latency riêng |
| **Used before/after GC** | Heap occupancy, không phải tổng process RSS |
| **Cycle duration** | Total elapsed phase processing, không đồng nghĩa STW |

### 16.2. Nếu GC pause thấp mà p99 vẫn cao

Hãy kiểm tra theo thứ tự:

1. Timestamps của request traces và GC logs có trùng không?
2. Có **allocation stalls** hoặc heap sát Xmx không?
3. CPU utilization và cgroup throttling thế nào?
4. Concurrent GC threads có tranh CPU với request threads không?
5. Application có locks/monitor contention/ThreadLocal leaks không?
6. Database/network calls có chiếm phần lớn latency không?
7. JIT compilation, class loading hay other safepoint operations có spike không?
8. Mức traffic và cache miss có đổi khi thử collector không?

**Một GC cycle dài 300 ms** chỉ có ý nghĩa rằng GC work trải trong 300 ms elapsed; application có thể được chạy phần lớn thời gian đó.

## 17. Virtual memory và memory footprint

Một số thiết kế ZGC dùng **virtual memory multi-mapping**/nhiều address views phục vụ colored pointer semantics. Khi đọc công cụ memory:

- **Virtual address space reserved** không bằng committed physical pages.
- Một physical page có thể xuất hiện qua nhiều virtual views trong một số triển khai.
- **Heap used**, **heap committed**, **heap reserved**, **process RSS** và **container working set** là các metrics khác nhau.
- Không kết luận memory leak chỉ từ một con số virtual address space lớn.
- Layout này có thể thay đổi giữa versions; không coi sơ đồ JDK17 là API được bảo đảm cho JDK25.

Ngoài Java heap còn có Metaspace, JIT code cache, thread stacks, native buffers, GC metadata và runtime libraries. Vì vậy **-Xmx không phải giới hạn tổng process RSS**.

### 17.1. Uncommit unused heap

Khi traffic giảm, ZGC có thể trả unused committed heap memory về OS trong những điều kiện thích hợp. Điều này hữu ích cho services có tải không đều.

Nhưng:

- Không có hợp đồng “mỗi khi GC reclaim 1 GiB là RSS giảm 1 GiB ngay”.
- Xms có thể thiết lập memory floor.
- OS accounting và native allocations vẫn ảnh hưởng RSS.
- Nếu cần kiểm chứng, đo **used/committed/reserved** qua logs/JMX và đo process memory riêng.

## 18. ZGC và memory leak

ZGC vẫn là tracing garbage collector: object graph **strongly reachable** từ GC roots không được xem là rác chỉ vì ứng dụng “không còn dùng về nghiệp vụ”.

Ví dụ:

~~~text
Static Cache ROOT
      |
      +--> Map
             |
             +--> Session đã hết hạn
                       |
                       +--> Data arrays lớn
~~~

Nếu application không remove/evict sessions, ZGC vẫn phải giữ graph đó. Thay Parallel/G1 bằng ZGC **không chữa memory leak logic**.

Những nguồn retention thường gặp:

- Static collections không giới hạn.
- ThreadLocal values trong pooled threads.
- Event listeners chưa unsubscribe.
- Scheduled tasks chứa captured objects.
- Long-lived class loaders hoặc JNI global references.
- Session caches/queues không có backpressure.

Để xử lý: heap dump, dominator tree, path-to-GC-root, sửa lifecycle; không chỉ tăng -Xmx hoặc đổi GC.

## 19. Những hiểu lầm phổ biến

1. **“ZGC không có STW.”** Sai: có các pause đồng bộ ngắn.
2. **“ZGC p99 response luôn dưới 1 ms.”** Sai: GC pause không phải end-to-end latency.
3. **“Concurrent GC không lấy CPU của ứng dụng.”** Sai: GC threads cạnh tranh tài nguyên.
4. **“ZGC luôn throughput hơn G1.”** Sai: tùy workload và CPU headroom.
5. **“Một ZGC cycle kéo dài 100 ms nghĩa là STW 100 ms.”** Sai: có concurrent phases.
6. **“Heap có đúng bằng live set là đủ.”** Sai: còn allocation/relocation headroom.
7. **“ZGC Java 17 là generational.”** Sai; Generational ZGC xuất hiện JDK21.
8. **“JDK25 cần -XX:+ZGenerational.”** Sai; mode non-generational đã bị bỏ từ JDK24.
9. **“Colored pointer là thuộc tính Java Object đọc được.”** Sai: VM-private encoding.
10. **“Load barrier là volatile memory fence.”** Sai: GC barrier khác JMM synchronization.
11. **“Mọi load reference đều phải chạy slow path.”** Sai: good-color fast path tối ưu.
12. **“ZGC không di chuyển objects.”** Sai: concurrent relocation/compaction là đặc trưng.
13. **“GC move làm a==b thay đổi.”** Sai: identity semantics không đổi.
14. **“ZGC tự reclaim vòng tham chiếu còn rooted.”** Sai: strong reachability vẫn giữ đối tượng.
15. **“Mọi ZGC versions dùng cùng bit layout màu.”** Sai: internals phát triển qua versions.
16. **“ZGC chỉ dùng load barriers mãi mãi.”** Sai khi nói Generational ZGC hiện đại.
17. **“GC log mặc định chỉ ra đúng source line gây allocation.”** Sai: cần profiling/tracing.
18. **“Tăng ConcGCThreads luôn giảm latency.”** Sai: có CPU contention trade-off.
19. **“SoftMaxHeapSize là giới hạn hard.”** Sai: mục tiêu mềm.
20. **“Xmx hạn chế mọi native memory JVM.”** Sai: heap khác native allocations.
21. **“System.gc() chắc chắn kích hoạt ZGC cycle và reclaim xong.”** Không có timing guarantee như vậy.
22. **“Kết quả một microbenchmark 1 giây đủ chọn collector.”** Sai: warm-up, realistic live set, long-tail cần đo.
23. **“Heap committed thấp nghĩa là GC pause cao.”** Không có quan hệ trực tiếp đủ để kết luận.
24. **“ZGC được hỗ trợ ở mọi JVM/OS dù vendor nào.”** Sai: kiểm tra implementation/build/platform.
25. **“Cứ bật ZGC là allocation stalls biến mất.”** Sai nếu thiếu headroom hoặc GC progress.
26. **“Đặt Xms=Xmx luôn tốt nhất.”** Sai: có thể ảnh hưởng memory elasticity/uncommit.
27. **“Với colored pointers, hashCode là địa chỉ vật lý.”** Sai.
28. **“Generational ZGC là bản sao G1 với tên khác.”** Sai: collector architecture/barriers khác.
29. **“Heap lớn hơn luôn tạo pause ZGC dài hơn theo tuyến tính.”** Không phải đặc điểm thiết kế; đo thực tế.
30. **“Lỗi OutOfMemoryError có thể bỏ qua vì ZGC concurrent.”** Sai: memory capacity vẫn hữu hạn.

## 20. Bài tập tự kiểm tra có đáp án

**Bài 1.** ZGC tối ưu điều gì?

**Đáp án:** Stop-the-world GC pause latency, bằng cách thực hiện gần như toàn bộ marking và relocation concurrently.

**Bài 2.** Một concurrent cycle dài 400 ms; ứng dụng bị dừng 400 ms chắc không?

**Đáp án:** Không. Cần xem các pause phases riêng; phần lớn cycle có thể chạy concurrent.

**Bài 3.** Object X di chuyển từ A sang B khi mutator giữ reference cũ. Công nghệ nào xử lý?

**Đáp án:** Colored pointers, load barriers và relocation/forwarding metadata.

**Bài 4.** Java 17 dùng -XX:+UseZGC thì đã có young/old generations theo JEP439 chưa?

**Đáp án:** Chưa. Đó là non-generational ZGC.

**Bài 5.** JDK21 bật generational bằng cách nào?

**Đáp án:** -XX:+UseZGC -XX:+ZGenerational.

**Bài 6.** Vì sao JDK24/25 không cần ZGenerational?

**Đáp án:** JDK24 loại bỏ non-generational mode; ZGC là generational-only.

**Bài 7.** Live set = 8 GiB, -Xmx=8g, allocation rate cao. Có rủi ro?

**Đáp án:** Có: thiếu headroom, allocation stalls/OOME. Cần cấp dung lượng theo workload.

**Bài 8.** GC pause ổn định <1 ms nhưng request p99 xấu. Cần xem gì?

**Đáp án:** Allocation stalls, CPU quota, I/O, locks, JIT và downstream operations, không chỉ STW.

**Bài 9.** Tăng ConcGCThreads vô hạn có tốt không?

**Đáp án:** Không; GC tiến triển nhanh hơn có thể giành CPU với mutators và giảm throughput.

**Bài 10.** SoftMaxHeapSize có được phép vượt không?

**Đáp án:** Có; đó là soft target, giới hạn max heap là Xmx.

**Bài 11.** Colored pointers có làm thay đổi Object.equals/== không?

**Đáp án:** Không. JVM phải giữ Java reference/object identity semantics.

**Bài 12.** Cả một chu trình A→B→A không còn root path có được ZGC reclaim không?

**Đáp án:** Có thể được, như tracing GC khác; cycle không tự tạo memory leak.

**Bài 13.** Vì sao Generational ZGC thường hiệu quả hơn non-generational với nhiều temporary objects?

**Đáp án:** Có thể xử lý young generation thường xuyên mà không phải duyệt toàn bộ old live set mỗi young cycle, đồng thời tracking cross-gen references đúng.

**Bài 14.** Heap reserved 1 TiB đồng nghĩa 1 TiB RAM vật lý đang dùng?

**Đáp án:** Không. Reserved virtual address space khác committed/used memory và RSS.

**Bài 15.** Một collection chưa xảy ra trong demo có phải -XX:+UseZGC thất bại?

**Đáp án:** Không. Chương trình nhỏ có thể hoàn thành trước khi GC cần chạy; kiểm tra final flags/log initialization.

**Bài 16.** Một ứng dụng memory leak do static HashMap sẽ hết leak khi đổi sang ZGC?

**Đáp án:** Không. Rooted object graph vẫn reachable; phải sửa cache eviction/lifecycle.

**Bài 17.** GC pause nhỏ, nhưng có allocation stalls lớn. ZGC tuning ưu tiên gì?

**Đáp án:** Đo allocation rate, live set, headroom/Xmx, concurrent GC CPU/progress và container budget.

**Bài 18.** Một JDK cũ chỉ hỗ trợ experimental ZGC: có thể dùng ngay flag Java17?

**Đáp án:** Không chắc. Kiểm tra JDK version, platform và flags; JDK11 ban đầu cần experimental unlock.

**Bài 19.** Load barrier của GC có làm một data race Java trở thành thread-safe không?

**Đáp án:** Không. Thread safety thuộc JMM locks/volatile/atomics riêng.

**Bài 20.** Khi chọn collector, chỉ so average request latency được không?

**Đáp án:** Không. Phải đo p95/p99/p99.9, throughput, CPU/memory costs, GC pauses và stalls dưới workload tương đương.

## 21. Checklist áp dụng trong môi trường thực

1. Ghi **JDK vendor/version/build, OS/architecture, CPU/container quotas** trước khi tune.
2. Phân biệt **non-generational JDK17** và **Generational ZGC JDK21+**.
3. Bật **-XX:+UseZGC** trên HotSpot hỗ trợ, xem final JVM flags.
4. Giữ **-Xmx** đủ live set + allocation/relocation headroom.
5. Theo dõi cả **STW pauses** lẫn **concurrent cycle durations**.
6. Đặc biệt theo dõi **allocation stalls** và GC CPU contention.
7. Nếu dùng **SoftMaxHeapSize**, hiểu nó là soft target và có thể bị vượt.
8. Không dùng cờ **ZGenerational** không còn hỗ trợ trên JDK24+.
9. Đọc **java -Xlog:help** trước khi xây parsing rule cho logs.
10. So sánh G1/ZGC trên cùng realistic workload, JIT warm-up và SLA.
11. Theo dõi application p99 và JVM metrics theo cùng timestamps.
12. Phân biệt Java heap với process RSS/native memory và vùng address-space reserved.
13. Không dựa vào System.gc() để tạo một benchmark có timing deterministic.
14. Dùng heap dump/path-to-GC-roots khi nghi memory leak; GC không thu hồi rooted graph.
15. Đọc tài liệu đúng major version vì coloring, barriers và pause logs có thể thay đổi.

### Tài liệu chính thức và chuyên sâu

- **Oracle Java SE 17 — The Z Garbage Collector:** https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector1.html
- **Oracle Java SE 17 — Available Collectors:** https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- **Oracle JVM Performance — Tuning ZGC:** https://ops.java/performance/jvm/articles/tuning-zgc/
- **OpenJDK JEP 333 — ZGC (experimental):** https://openjdk.org/jeps/333
- **OpenJDK JEP 377 — ZGC (production):** https://openjdk.org/jeps/377
- **OpenJDK JEP 439 — Generational ZGC:** https://openjdk.org/jeps/439
- **OpenJDK JEP 474 — Generational Mode by Default:** https://openjdk.org/jeps/474
- **OpenJDK JEP 490 — Remove Non-Generational Mode:** https://openjdk.org/jeps/490
- **Dev.java — Deep-dive of ZGC's Architecture:** https://dev.java/learn/jvm/tool/garbage-collection/zgc-deepdive/
- **Oracle Java SE 17 — java Command / Unified JVM Logging:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html

**Ghi nhớ cốt lõi:** ZGC đạt mục tiêu dừng rất ngắn bằng cách thực hiện phần lớn công việc đánh dấu và di chuyển objects **đồng thời với ứng dụng**, dùng **colored pointers/load barriers** để giữ references an toàn. Đây là đánh đổi giữa **tail latency, CPU và bộ nhớ dành cho concurrent GC**; muốn tối ưu phải đo cả **GC pauses, allocation stalls, throughput và p99**, và phải xác định đúng **phiên bản ZGC** thay vì đem cơ chế Java 17 áp cho Java 25.
