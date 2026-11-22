# Đọc nhật ký G1 khi giới hạn tài nguyên thay đổi — bài thực hành Java 10 và HotSpot hiện đại

**Chủ đề cha:** Thực hành tổng hợp.  
**Trọng tâm:** Đọc **Unified GC Logging** của **Garbage-First Garbage Collector (G1)**, liên hệ các dòng log với số CPU/GC workers, heap được sử dụng/committed/max heap và giới hạn bộ nhớ/CPU khi Java chạy trong container. Học cách so sánh hai lần khởi động JVM dưới các cấu hình tài nguyên khác nhau, cũng như cách quan sát một JVM đang chạy trong lúc container thay đổi giới hạn mà **không suy diễn sai rằng mọi tham số G1 đều tự động điều chỉnh**.

**Bối cảnh Java 10:** G1 đã là collector mặc định trong cấu hình HotSpot phổ biến từ **JDK 9**, không phải được giới thiệu ở Java 10. **JDK 10** tăng cường việc HotSpot nhận diện **CPU/memory limits của Linux container**; cơ chế **`-Xlog`** của Unified JVM Logging đã có từ JDK 9. Những kiến thức này **vẫn áp dụng ở các JDK hiện đại**, nhưng định dạng chi tiết log, thuật toán G1 và container detection tiếp tục phát triển. Bài dùng lệnh/option còn được tài liệu **Oracle JDK 25** hỗ trợ, tránh các cờ GC logging cũ đã được thay thế bởi `-Xlog`.

**Phạm vi bằng chứng và kiểm thử:** Bốn chương trình Java dùng trong bài được biên dịch bằng **`javac --release 10`** và chạy trên **Zulu/OpenJDK HotSpot 24.0.2**. Các phép thử CPU count bằng `-XX:ActiveProcessorCount=1`/`4`, giới hạn Java heap bằng `-Xmx96m`, quan sát G1 GC logs và xử lý một fixture log **đều đã chạy**. Các lệnh Docker/cgroups/Kubernetes hướng dẫn phần **giới hạn tài nguyên Linux thật** và việc cập nhật limits của một container đang chạy; những tình huống đó **không được thử nghiệm trực tiếp trên môi trường Windows của lượt kiểm chứng**. Không biến mô phỏng JVM flags thành tuyên bố đã chứng minh CPU quota throttling hoặc cgroup OOM kill.

**Đầu ra học tập:** Sau bài này, bạn có thể đọc đúng `GC(n)`, `Pause Young`/`Mixed`/`Full`, `before->after(committed)`, `User/Sys/Real`, `Parallel Workers`, biết vì sao **một GC pause lớn không đủ kết luận có leak**, và xây một phép thử thay đổi giới hạn tài nguyên có đối chứng.

---

## 1. Phải phân biệt bốn loại “giới hạn”

Một log G1 được tạo trong một **JVM process**, còn CPU/memory limits thường được thực thi bởi **kernel/OS** hoặc **container runtime**. Trước khi phân tích dòng GC, phân biệt:

| Khái niệm | Ai quyết định/thực thi? | Ảnh hưởng trực tiếp nào? |
| --- | --- | --- |
| **Java heap tối đa `-Xmx`** | HotSpot/JVM | Giới hạn Java heap; không giới hạn toàn bộ native memory |
| **Số CPU JVM nhìn thấy** | OS/affinity/cgroup, HotSpot container support hoặc `ActiveProcessorCount` | Các quyết định ergonomics, bao gồm cấu hình số worker G1 |
| **CPU quota/period của cgroup** | Linux kernel và container runtime | CPU time được cấp; có thể **throttling** dù JVM muốn dùng nhiều workers |
| **Memory hard limit của cgroup** | Linux kernel và container runtime | Tổng memory tính theo cgroup; có thể **OOM-kill** process mà không phát sinh Java `OutOfMemoryError` |

**Không đồng nhất:** `-XX:ActiveProcessorCount=1` **không** làm kernel thực sự cấp cgroup CPU quota đúng 1 CPU; nó chỉ yêu cầu JVM sử dụng con số đó để tự cấu hình. Tương tự, `-Xmx96m` **không** tạo container memory limit 96 MiB. G1 log cho biết trạng thái **Java heap**, không trực tiếp đo toàn bộ RSS, direct memory hay file cache được tính vào cgroup.

### Khi operator nói “đổi giới hạn”

Cần hỏi họ đã thay đổi cái nào:

- **Đổi CPU limit Kubernetes/Docker:** kernel quota thay đổi; giá trị `availableProcessors()` có thể được JVM/OS phản ánh theo môi trường, nhưng **các pool đã khởi tạo không được bảo đảm resize ngay**.
- **Đổi memory limit của container:** thay **hard cap của cgroup**; không tự làm `-Xmx` explicit nhỏ lại hay nới ra.
- **Đổi `-Xmx` hoặc `-XX:ActiveProcessorCount` trong deployment:** thông thường là **khởi động một JVM mới** với JVM flags khác; không phải chỉnh JVM option cũ bằng một lần thay YAML.
- **Đổi allocation rate/live set trong ứng dụng:** workload thay đổi, G1 có thể tạo các kiểu GC/pauses khác, dù kernel resource limits không đổi.

**Phép thử hợp lệ phải ghi cả bốn thông số**, nếu không rất dễ gán một thay đổi GC do workload cho việc thay CPU/memory limit.

## 2. G1 hiện đại thu gom bộ nhớ như thế nào?

**G1** chia Java heap thành nhiều **regions** có kích thước tương đương nhau, được JVM chọn theo ergonomics. Một số regions được sử dụng làm **Eden**, **Survivor**, **Old** và **Humongous**; vai trò của chúng có thể thay đổi theo các chu kỳ GC.

Các khái niệm cần đọc trong log:

1. **Young collection:** thu gom vùng Eden/Survivor, chuyển/move các object còn sống sang survivor/old regions khi thích hợp. Thường là một **stop-the-world pause**, dù G1 có nhiều công việc chạy concurrent ngoài pause.
2. **Concurrent marking:** xác định liveness trong heap khi Java application vẫn có thể tiếp tục. Có các pause ngắn như Concurrent Start/Remark/Cleanup theo chu kỳ và phần việc concurrent.
3. **Mixed collection:** sau marking, thu gom **young regions và một số old regions đã được chọn**. Không đồng nghĩa với “thu gom toàn bộ old generation”.
4. **Full GC:** đường xử lý **stop-the-world full heap compaction** trong các tình huống cần thiết, thường tốn kém; thấy Full GC liên tục là tín hiệu quan trọng để điều tra, **không phải luôn do thiếu `-Xmx`**.
5. **Evacuation failure:** G1 không chuyển được một số object khỏi region vì không đủ vùng đích hoặc object bị pinned; tài liệu JDK hiện hành có ví dụ `Evacuation Failure: Allocation/Pinned`.
6. **Humongous object:** object có kích thước **từ một nửa G1 region trở lên**; thường chiếm những regions trong old generation và có cách xử lý khác object bình thường.

~~~text
                          G1 heap
      +---------------------------------------------+
      | Eden | Survivor | Old | Old | Humongous ...  |
      +---------------------------------------------+
             |           |
       Young pause       +--- Concurrent mark
             |                  |
       Promote/move             +-- Remark / Cleanup
             |                  |
             +------ Mixed young+old regions
                                |
                            nếu thiếu vùng/
                            điều kiện khác
                                |
                              Full GC
                         (không phải mỗi cycle)
~~~

**Không gán cứng** một tỉ lệ Eden/Survivor/Old cho G1. G1 tự điều chỉnh young generation và tập regions thu gom để cố đạt **mục tiêu pause**, cân bằng với throughput và footprint.

### `-XX:MaxGCPauseMillis` là mục tiêu mềm

Ví dụ:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar app.jar
~~~

Cờ đặt **soft target** cho độ dài pause, **không phải cam kết mọi GC dưới 200ms**. Với heap nhỏ, quá nhiều object sống hoặc CPU time bị cgroup throttled, G1 vẫn có thể vượt mục tiêu. Đặt mục tiêu quá nhỏ cũng có thể tăng số lần GC và chi phí runtime. Oracle JDK 25 khuyến nghị **bắt đầu với defaults**, chỉ sửa heap/pause goal khi có số liệu.

## 3. Bật Unified GC Logging bằng tùy chọn còn được hỗ trợ

Để đọc loại pause cơ bản:

~~~bash
java -XX:+UseG1GC -Xlog:gc -jar app.jar
~~~

Để đọc chi tiết thêm phases, heap regions, workers và CPU time:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info -jar app.jar
~~~

Để xem mức chi tiết cao hơn **chỉ khi cần chẩn đoán**:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=debug -jar app.jar
~~~

Một lệnh thực tế ghi file có **giới hạn xoay vòng**:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=3,filesize=2M -jar app.jar
~~~

Giải thích:

- **`gc*`**: chọn các tag sets chứa tag `gc`, như `gc`, `gc,heap`, `gc,cpu`, `gc,init`. Không có dấu `*` sẽ ít chi tiết hơn.
- **`=info`/`=debug`**: mức log; `debug` in nhiều dòng hơn và có overhead đáng kể.
- **`file=gc.log`**: ghi vào file.
- **`time,uptime,level,tags`**: in wall-clock timestamp, thời gian từ JVM startup, mức log và tags.
- **`filecount=3,filesize=2M`**: rotation của Java Unified Logging; file thực tế có thể mang hậu tố, cần đọc đúng tập rotated logs nếu phân tích khoảng thời gian dài.
- Đường ghi log phải có quyền ghi và đủ dung lượng. Trong container, nếu file ở ephemeral storage, cần chính sách log retention/volume.
- Mỗi `GC(n)` có thể có **nhiều dòng**, gồm `gc,start`, `gc,phases`, `gc,heap`, `gc,cpu` và **một dòng tóm tắt cuối**. Đừng đếm mọi dòng chứa `GC(n)` thành nhiều lần GC.

**Tránh hướng dẫn logging lỗi thời:** Không thiết lập các `PrintGCDetails`/`PrintGCTimeStamps` cũ làm giải pháp chính cho JDK hiện đại. Các tùy chọn `-Xlog` là API command-line được Oracle hiện hành tài liệu hóa; một số alias cũ được deprecated hoặc xử lý khác theo release.

### Kiểm tra tag trước khi chọn

~~~bash
java -Xlog:help
~~~

Khi chạy trên HotSpot JDK 24 dùng cho thí nghiệm, các tags `gc`, `heap`, `cpu` và `container` có mặt. Cú pháp chính xác vẫn phải theo `java -Xlog:help` và `java` man page của JDK thực tế.

## 4. Cách đọc một dòng G1 `Pause Young`

Ví dụ **dòng đã quan sát thực** trong phép thử JVM có `-Xmx96m`, `-Xms32m`, `ActiveProcessorCount=1`:

~~~text
[0.029s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 7M->2M(34M) 0.881ms
~~~

Một dòng có nhiều trường ý nghĩa:

| Thành phần | Cách đọc đúng |
| --- | --- |
| `[0.029s]` | Mốc **uptime** từ khi JVM khởi động (vì log chọn decorator `uptime`) |
| `[info][gc]` | Mức log và tag, không phải mức nghiêm trọng của sự cố |
| `GC(0)` | **ID sự kiện GC**, dùng ghép với các dòng chi tiết cùng `GC(0)` |
| `Pause Young` | Pause thu gom một tập regions young, có thể kèm đặc điểm khác theo giai đoạn |
| `(Normal)` | Kiểu young pause trong chu kỳ này; còn có `Concurrent Start`, `Prepare Mixed`, `Mixed` |
| `(G1 Evacuation Pause)` | Reason/type giải thích G1 đang evacuation collection set |
| `7M->2M` | **Java heap used** trước/sau collection theo bản log này |
| `(34M)` | Dung lượng **Java heap committed** được báo lúc sự kiện, **không nhất thiết là `-Xmx`** |
| `0.881ms` | Độ dài pause theo JVM logging cho sự kiện đó |

**Một bẫy rất quan trọng:** Dù JVM chạy với **`-Xmx96m`**, dòng log có **`(34M)`**, vì G1 khởi đầu với khoảng `-Xms32m` và có thể mở rộng Java heap trong quá trình chạy. **Không đọc `(34M)` rồi kết luận container memory limit hoặc `-Xmx` bằng 34 MiB**.

Tương tự, `7M->2M` là lượng **heap được sử dụng** ở hai thời điểm, không phải tổng bytes cấp phát trong toàn chương trình và không có nghĩa “5 MiB memory đã được trả về OS ngay lập tức”. Committed heap và cgroup RSS có cơ chế khác nhau.

### Đừng lấy GC ID làm số pause

Một sự kiện GC có thể in:

~~~text
[0.028s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.029s][info][gc]       GC(0) Pause Young (Normal) (G1 Evacuation Pause) 7M->2M(34M) 0.881ms
[0.029s][info][gc,cpu]   GC(0) User=0.00s Sys=0.00s Real=0.00s
~~~

Ba dòng cùng **`GC(0)`** liên quan một pause. Một số dòng có thêm phase detail. **Đếm các dòng `gc` tóm tắt đủ trường `before->after(capacity) duration`, hoặc dùng parser nhận dạng**, thay vì đếm số occurrence của chuỗi `GC(0)`.

Dòng `gc,cpu` có độ phân giải in thường chỉ đến phần trăm giây, nên pause một mili giây có thể cho `0.00s` ở User/Sys/Real. **Không kết luận pause bằng 0** khi thấy `Real=0.00s`; xem duration millisecond ở dòng summary.

## 5. Cách đọc `gc,init` và GC worker counts

Ngay lúc JVM khởi động, `-Xlog:gc*=info` có thể in:

~~~text
[0.006s][info][gc]      Using G1
[0.007s][info][gc,init] CPUs: 28 total, 1 available
[0.007s][info][gc,init] Heap Region Size: 1M
[0.007s][info][gc,init] Parallel Workers: 1
[0.007s][info][gc,init] Concurrent Workers: 1
~~~

Đây là **trích dòng đã quan sát trong lần chạy của thí nghiệm**. Ý nghĩa:

- **`28 total`**: con số logical CPU tổng mà HotSpot/OS nhận ở máy thử, **không phải CPU quota trong container**.
- **`1 available`**: HotSpot được yêu cầu xem **1 active processor** qua `-XX:ActiveProcessorCount=1` ở lần khởi động này.
- **`Parallel Workers: 1`**: G1 đã chọn cấu hình **tối đa/ergonomic parallel workers** tương ứng; không có nghĩa mọi GC luôn sử dụng đúng một worker trong mọi phase.
- **`Concurrent Workers: 1`**: số concurrent marking workers JVM chọn. **Không bắt buộc đổi theo tỷ lệ bằng Parallel Workers**.
- **`Heap Region Size: 1M`**: kích thước region trong cấu hình heap và JDK này. Với JDK/heap khác, G1 có thể chọn region size khác.

Khi thử `ActiveProcessorCount=4` trên **cùng máy/JDK và workload**, log cho biết:

~~~text
[0.007s][info][gc,init] CPUs: 28 total, 4 available
[0.007s][info][gc,init] Parallel Workers: 4
[0.007s][info][gc,init] Concurrent Workers: 1
~~~

**Quan sát trọng yếu:** CPU count 1→4 khiến G1 Parallel Workers cấu hình 1→4 trong phép thử, nhưng **Concurrent Workers vẫn là 1**. **Không áp công thức “tất cả số luồng GC = availableProcessors”**. Thậm chí khi max workers là 4, một collection cụ thể có thể chọn **Using N workers of 4**, phụ thuộc phase/ergonomics và tình trạng hệ thống.

**Quan hệ với tài nguyên container:** Trong Linux container được nhận diện đúng, HotSpot có thể xét CPU quota và cpuset khi quyết định active processors. Từ **JDK 19**, HotSpot **mặc định không còn dùng `cpu.shares` để tính active processor count** như một số bản JDK cũ. Đừng lấy CPU request/weight ở Kubernetes làm “CPU chắc chắn JVM nhìn thấy” nếu không có hard quota/affinity tương ứng.

## 6. `gc,heap` — đọc Eden, Survivor, Old và Humongous

Với `-Xlog:gc*=info`, trong một collection có thể thấy các dòng kiểu:

~~~text
[...][info][gc,heap] GC(7) Eden regions: 14->0(12)
[...][info][gc,heap] GC(7) Survivor regions: 2->3(3)
[...][info][gc,heap] GC(7) Old regions: 5->7
[...][info][gc,heap] GC(7) Humongous regions: 0->0
~~~

**Bốn dòng trên là ví dụ minh họa**, không phải exact output của phép thử; giá trị region thay đổi theo workload. Cách đọc:

- **Eden `14->0(12)`**: 14 Eden regions trước, 0 sau; giá trị trong ngoặc là **định cỡ/target tiếp theo** mà G1 dùng cho young regions (không phải `-Xmx`).
- **Survivor `2->3(3)`**: vùng survivor liên quan lần collection này tăng từ 2 lên 3, G1 điều chỉnh target.
- **Old `5->7`**: có thể phản ánh việc object sống được promoted vào old; một lần tăng old chưa chứng minh leak.
- **Humongous `0->0`**: không có humongous regions được báo ở ví dụ. Nếu tăng nhiều, xem kích thước object và region size.

**Lưu ý region size:** Với `Heap Region Size: 1M`, object **từ 512 KiB trở lên** có thể được xem là humongous theo G1. Điều đó giải thích tại sao bài lab cấp các array **128 KiB**, nhỏ hơn một nửa region thử nghiệm, để tập trung vào young allocation. Nếu bạn sửa chương trình thành array nhiều MiB, hành vi khác vì humongous allocation — đó là **thí nghiệm mới**, không được dùng so trực tiếp với baseline mà không ghi khác biệt.

### Old regions tăng có chắc là memory leak?

Không. Old tăng có thể do sống lâu hơn, promotions và chu kỳ marking chưa reclamation. Muốn kết luận leak cần xem **live-set growth sau các kỳ GC đầy đủ, heap dump, object retention paths và workload theo thời gian**. Dùng một đồ thị Old regions tăng trong vài giây là chưa đủ.

## 7. `gc,cpu` — phân biệt CPU time và wall-clock time

Ví dụ dạng log:

~~~text
[...][info][gc,cpu] GC(17) User=0.19s Sys=0.00s Real=0.04s
~~~

Đây là **ví dụ giải thích**, không phải số đo của thí nghiệm. Theo tài liệu G1 tuning:

- **User**: tổng CPU time các thread dành cho mã user-mode của JVM liên quan GC.
- **Sys**: CPU time dành trong kernel-mode.
- **Real**: **wall-clock elapsed time**, không phải phần trăm CPU usage.

Khi nhiều GC workers chạy song song, **User có thể lớn hơn Real** vì User cộng CPU time các threads. Khi **Real lớn đáng kể so với User+Sys**, cần xem thread có đang thiếu CPU/scheduling hay bị điều kiện ngoài làm chậm không, đặc biệt trên host quá tải hoặc cgroup bị throttling.

Nhưng **đừng kết luận “Real>User+Sys chắc chắn do CPU throttling”**: còn có lock waits, OS scheduling, page faults, system load, log I/O và yếu tố khác. Muốn chứng minh throttling, cần đối chiếu **cgroup CPU counters**/container metrics cùng khoảng thời gian.

### Vì sao log `Real=0.00s` dù pause >0?

JDK có thể hiển thị CPU times làm tròn đến độ phân giải hai chữ số thập phân của giây. Một pause `1.232ms` vẫn có thể in `Real=0.00s`. **Dùng duration có đơn vị ms của dòng `Pause ...` để đo pause**, không lấy giá trị Real được làm tròn rồi xem đó là 0ms.

## 8. Java lab số 1 — Tạo young allocation có kiểm soát

Tạo file độc lập **`G1ResourceLogLab.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class G1ResourceLogLab {
    static volatile long observed;

    public static void main(String[] args) {
        int rounds = args.length > 0
                ? Integer.parseInt(args[0]) : 240;
        int chunksPerRound = args.length > 1
                ? Integer.parseInt(args[1]) : 12;
        int chunkKiB = args.length > 2
                ? Integer.parseInt(args[2]) : 128;

        if (rounds < 1 || chunksPerRound < 1
                || chunkKiB < 1 || chunkKiB > 256) {
            throw new IllegalArgumentException(
                    "Positive rounds/chunks; chunkKiB 1..256");
        }

        byte[][] retained = new byte[48][];
        int next = 0;
        long sum = 0;
        int blocks = 0;

        for (int round = 0; round < rounds; round++) {
            for (int j = 0; j < chunksPerRound; j++) {
                byte[] data = new byte[chunkKiB * 1024];
                data[0] = 1;
                sum += data[0];
                blocks++;

                if ((round + j) % 6 == 0) {
                    retained[next++ % retained.length] = data;
                }
            }
        }

        observed = sum;
        boolean g1 = false;
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (gc.getName().startsWith("G1 ")) g1 = true;
        }

        System.out.println("g1-mxbean-visible=" + g1);
        System.out.println("available-processors=" +
                Runtime.getRuntime().availableProcessors());
        System.out.println("max-heap-mib=" +
                Runtime.getRuntime().maxMemory() / (1024 * 1024));
        System.out.println("allocated-chunks=" + blocks);
        System.out.println("allocated-mib=" +
                ((long) blocks * chunkKiB / 1024));
        System.out.println("checksum-correct=" +
                (observed == blocks));
    }
}
~~~

**Giải thích workload:**

- Mặc định có **240 rounds**, mỗi round cấp **12 arrays × 128 KiB**.
- Tổng số arrays **`240 × 12 = 2.880`** và tổng dung lượng mảng được yêu cầu khoảng **360 MiB** trong toàn vòng đời (không phải 360 MiB đang còn sống cùng lúc).
- `retained` chỉ giữ lại một phần trong ring 48 slots, nên các arrays cũ có thể được GC. Điều này tạo hoạt động cấp phát/lifetime đủ để thấy các young collections ở cấu hình thử.
- `volatile observed` và phép tính tổng buộc chương trình dùng kết quả của vòng lặp theo đường thực thi quan sát được; không dùng `System.gc()` để ép một Full GC rồi khẳng định là do thiếu memory.
- Dòng `g1-mxbean-visible` kiểm tên các collector management beans; nó **không** thay thế log startup `Using G1` để xác định cấu hình collector.

Biên dịch:

~~~bash
javac --release 10 G1ResourceLogLab.java
~~~

### Chạy A: 1 CPU theo góc nhìn JVM

~~~bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=1 -Xms32m -Xmx96m -Xlog:gc*=info:file=g1-cpu1.log:uptime,level,tags:filecount=2,filesize=2M G1ResourceLogLab 240 12 128
~~~

**Stdout chương trình đã kiểm chứng:**

~~~text
g1-mxbean-visible=true
available-processors=1
max-heap-mib=96
allocated-chunks=2880
allocated-mib=360
checksum-correct=true
~~~

### Chạy B: 4 CPUs theo góc nhìn JVM

~~~bash
java -XX:+UseG1GC -XX:ActiveProcessorCount=4 -Xms32m -Xmx96m -Xlog:gc*=info:file=g1-cpu4.log:uptime,level,tags:filecount=2,filesize=2M G1ResourceLogLab 240 12 128
~~~

**Stdout chương trình đã kiểm chứng:**

~~~text
g1-mxbean-visible=true
available-processors=4
max-heap-mib=96
allocated-chunks=2880
allocated-mib=360
checksum-correct=true
~~~

Hai lệnh giữ **cùng heap max, heap initial và workload**, chỉ đổi số CPU JVM nhìn thấy. Đúng mục đích so sánh **ergonomics/parallel workers**. **Không suy diễn chúng đang thực thi dưới hai CPU quotas khác nhau của Linux**; đây là thử nghiệm **JVM override**, không thay kernel scheduler.

### Log thực tế có gì?

Trên một lần thử riêng biệt của **OpenJDK 24.0.2**, bản A:

~~~text
[0.006s][info][gc]      Using G1
[0.007s][info][gc,init] CPUs: 28 total, 1 available
[0.007s][info][gc,init] Heap Region Size: 1M
[0.007s][info][gc,init] Parallel Workers: 1
[0.007s][info][gc,init] Concurrent Workers: 1
~~~

Bản B:

~~~text
[0.006s][info][gc]      Using G1
[0.007s][info][gc,init] CPUs: 28 total, 4 available
[0.007s][info][gc,init] Parallel Workers: 4
[0.007s][info][gc,init] Concurrent Workers: 1
~~~

**Số events và thời lượng pause không phải output bất biến.** Trong **một lần thử** với cùng source/flags, file A có **19** dòng tóm tắt Young, file B có **20**, cả hai không có Full GC; max Young pause lần lượt khoảng **1.232ms** và **1.376ms**. Các số đo này **chỉ là quan sát từ lần chạy ấy**, tuyệt đối không có kết luận rằng 4 CPUs làm GC chậm hơn hoặc nhanh hơn. Phân phối thời gian/GC frequency phụ thuộc startup, heap sizing, scheduling, JIT, allocations và lần chạy.

**Điều bất biến đáng xác minh hơn:** Cả hai runs phải hoàn thành workload, in đúng số chunks/allocated MiB/checksum, ghi được G1 log, và ở các conditions đã thử `Parallel Workers` thể hiện sự khác biệt 1/4.

## 9. Java lab số 2 — Parser đọc dòng summary G1

Để không chỉ nhìn log bằng mắt, một chương trình Java có thể đếm **dòng summary của Young/Full pauses** và tính maximum pause duration trong file nhỏ.

Tạo file **`G1LogInspector.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class G1LogInspector {
    static final Pattern PAUSE = Pattern.compile(
            "GC\\(\\d+\\) Pause (Young|Full) .*? " +
            "([0-9]+[KMG])->([0-9]+[KMG])" +
            "\\(([0-9]+[KMG])\\) " +
            "([0-9]+(?:\\.[0-9]+)?)ms");

    static final class Stats {
        int young;
        int full;
        double maxPauseMs;
        int matched;
    }

    static Stats summarize(List<String> lines) {
        Stats s = new Stats();
        for (String line : lines) {
            Matcher m = PAUSE.matcher(line);
            if (!m.find()) continue;

            s.matched++;
            if ("Young".equals(m.group(1))) s.young++;
            if ("Full".equals(m.group(1))) s.full++;
            s.maxPauseMs = Math.max(s.maxPauseMs,
                    Double.parseDouble(m.group(5)));
        }
        return s;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Pass one GC log file");
        }
        Stats s = summarize(Files.readAllLines(
                Paths.get(args[0]), StandardCharsets.UTF_8));

        System.out.println("parsed-pause-lines=" + s.matched);
        System.out.println("young-pause-lines=" + s.young);
        System.out.println("full-pause-lines=" + s.full);
        System.out.println("max-pause-ms=" + s.maxPauseMs);
    }
}
~~~

**Một lưu ý về code:** Regex nhận các dòng `Pause Young`/`Pause Full` có kiểu **`123M->45M(256M) 4.500ms`** như định dạng HotSpot được kiểm thử. Nó **không phải parser GC log production tổng quát**, không hỗ trợ mọi tag set, mọi đơn vị/định dạng JDK, concurrent activities, rotated logs hoặc địa phương hóa. `Files.readAllLines` cũng tải toàn file vào memory; chỉ dùng với file lab nhỏ. Với logs production lớn, cần parser streaming và/hoặc hệ thống telemetry phù hợp.

Biên dịch:

~~~bash
javac --release 10 G1LogInspector.java
~~~

Đọc hai files đã tạo:

~~~bash
java G1LogInspector g1-cpu1.log
java G1LogInspector g1-cpu4.log
~~~

**Một lần chạy thực tế** đã thu được:

~~~text
parsed-pause-lines=19
young-pause-lines=19
full-pause-lines=0
max-pause-ms=1.232
~~~

và:

~~~text
parsed-pause-lines=20
young-pause-lines=20
full-pause-lines=0
max-pause-ms=1.376
~~~

**Không lấy hai bảng trên làm expected output tuyệt đối.** Những số đo thay đổi theo lần chạy và môi trường. Tiêu chí kiểm đúng là parser nhận đúng cấu trúc summary, không đếm nhầm dòng `gc,start`/`gc,cpu`, còn kết quả ứng dụng vẫn chính xác.

### Tại sao parser không đếm `Concurrent Mark Cycle`?

Những dòng như `GC(8) Concurrent Mark Cycle` là sự kiện/phase **không cùng định dạng `Pause Young/Full` có heap before/after + ms**. Parser này cố tình **không phân loại** chúng. Muốn phân tích phần concurrent, viết parser/tag processing riêng hoặc dùng công cụ G1-aware đầy đủ; **không xem count=0 của parser là bằng chứng không có concurrent work**.

## 10. Java lab số 3 — Kiểm tra parser bằng fixture cố định

Với một parser đọc log đo hiệu năng, cần test bằng các mẫu có **expected output xác định**. Tạo file **`G1LogParserFixture.java`**:

~~~java
import java.util.Arrays;

public class G1LogParserFixture {
    public static void main(String[] args) {
        G1LogInspector.Stats s = G1LogInspector.summarize(
                Arrays.asList(
                "[0.123s][info][gc] GC(7) Pause Young (Normal) (G1 Evacuation Pause) 32M->8M(96M) 2.500ms",
                "[0.456s][info][gc] GC(8) Concurrent Mark Cycle",
                "[0.789s][info][gc] GC(9) Pause Young (Mixed) (G1 Evacuation Pause) 44M->19M(96M) 3.750ms",
                "[1.234s][info][gc] GC(10) Pause Full (G1 Compaction Pause) 92M->31M(96M) 12.000ms"));

        if (s.matched != 3 || s.young != 2
                || s.full != 1 || s.maxPauseMs != 12.0) {
            throw new AssertionError("wrong parser result");
        }

        System.out.println("fixtures-parsed=" + s.matched);
        System.out.println("fixture-young=" + s.young);
        System.out.println("fixture-full=" + s.full);
        System.out.println("fixture-max-pause-ms=" + s.maxPauseMs);
        System.out.println("parser-qa=PASS");
    }
}
~~~

Biên dịch hai class cùng lúc (nếu chưa biên dịch `G1LogInspector`):

~~~bash
javac --release 10 G1LogInspector.java G1LogParserFixture.java
java G1LogParserFixture
~~~

**Stdout đã kiểm chứng chính xác:**

~~~text
fixtures-parsed=3
fixture-young=2
fixture-full=1
fixture-max-pause-ms=12.0
parser-qa=PASS
~~~

**Đây là dữ liệu log giả lập có chủ đích để test parser**, không phải báo cáo rằng ứng dụng lab đã có một Full GC 12ms. Mẫu gồm **2 Young**, **1 Full** và một dòng **Concurrent Mark** bị bỏ qua theo thiết kế parser. Nếu parser đếm nhầm dòng concurrent, test sẽ fail.

### Phương pháp kiểm thử có giá trị

- **Fixture cố định** để kiểm regex/logic summary, expected output chính xác và có assert.
- **Log thực tế** để xác minh Java flags tạo đúng log và có sự kiện GC, số event/duration được xem là **biến số**.
- **Benchmark** để đánh giá hiệu năng, yêu cầu nhiều lần chạy/cùng workload/container runtime và metrics ngoài JVM.

Không sử dụng một dữ liệu giả lập làm bằng chứng rằng HotSpot đã xảy ra đủ các GC types ở thời điểm cụ thể.

## 11. Giới hạn heap và `MaxRAMPercentage`: đừng tính bằng phép nhân máy móc

Khi JVM **không đặt `-Xmx` explicit**, HotSpot có thể chọn heap max từ lượng RAM nhận diện được thông qua một số **ergonomics flags** như:

- `-XX:MaxRAMPercentage`: tỷ lệ memory dùng cho **maximum Java heap** trong các điều kiện được tài liệu hóa.
- `-XX:MinRAMPercentage`: dùng trong chính sách heap sizing với môi trường có **memory nhỏ**.
- `-XX:InitialRAMPercentage`: yếu tố định cỡ heap ban đầu.
- `-XX:MaxRAM`: đặt giới hạn RAM giả định cho heap ergonomics ở tình huống cấu hình/test.

**`MaxRAMPercentage` không phải hard limit cho toàn bộ process/container memory**, và không phải công thức `heap=X%×container_limit` áp dụng chính xác cho mọi cấu hình cực nhỏ.

Để **mô phỏng đầu vào về RAM cho JVM heap ergonomics mà không tạo container thật**, trên OpenJDK HotSpot có thể thử:

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:MaxRAMPercentage=25 -XshowSettings:vm -version
java -XX:+UseG1GC -XX:MaxRAM=1g -XX:MaxRAMPercentage=50 -XshowSettings:vm -version
~~~

**Quan sát đã xác minh trên JDK 24.0.2:**

~~~text
MaxRAM=1g, MaxRAMPercentage=25 => Max. Heap Size (Estimated): 256.00M
MaxRAM=1g, MaxRAMPercentage=50 => Max. Heap Size (Estimated): 512.00M
~~~

**Hai dòng trên là bản ghi tóm tắt phép thử, không phải nguyên văn stdout do một command tự in “MaxRAM=...”.** Kết quả cho thấy tỷ lệ phần trăm ở ví dụ môi trường này.

### Counterexample: RAM rất nhỏ

Cùng JDK, nhưng đặt **`-XX:MaxRAM=256m`**:

~~~bash
java -XX:+UseG1GC -XX:MaxRAM=256m -XX:MaxRAMPercentage=25 -XshowSettings:vm -version
java -XX:+UseG1GC -XX:MaxRAM=256m -XX:MaxRAMPercentage=50 -XshowSettings:vm -version
~~~

**Kết quả đã quan sát:**

~~~text
MaxRAM=256m, MaxRAMPercentage=25 => Max. Heap Size (Estimated): 126.00M
MaxRAM=256m, MaxRAMPercentage=50 => Max. Heap Size (Estimated): 128.00M
~~~

Dù `25% × 256MiB` = 64MiB theo số học, HotSpot trong ví dụ chọn khoảng **126MiB**, vì **chính sách heap nhỏ/MinRAMPercentage và ergonomics** tác động. Đây là lý do **phải đo JVM thật**, không dùng một phép nhân tỷ lệ làm giá trị expected tuyệt đối cho mọi container.

**Mấu chốt:** Với `-Xmx96m` explicit, JVM đã có heap max 96MiB theo flag; thay đổi `MaxRAMPercentage` không tự vượt qua `-Xmx`. Khi container memory limit giảm đột ngột xuống dưới mức dùng thực tế, kernel có thể **OOM-kill** dù Java heap chưa ném `OutOfMemoryError`.

## 12. Giới hạn CPU thay đổi ảnh hưởng log G1 thế nào?

Một phép thử A/B cần tách rõ ba con số:

1. **`Runtime.availableProcessors()`**: số CPU JVM nhìn thấy tại lúc gọi.
2. **`Parallel Workers`/`Concurrent Workers` của G1**: cấu hình JVM chọn; có thể phụ thuộc CPUs và những flag/cấu trúc khác.
3. **CPU quota thực của cgroup**: kernel thực thi thông qua CPU time và throttling.

Ví dụ trong thí nghiệm **cùng workload và heap**:

| Cấu hình khởi động | JVM active CPUs | G1 Parallel Workers | G1 Concurrent Workers |
| --- | ---: | ---: | ---: |
| `-XX:ActiveProcessorCount=1` | 1 | 1 | 1 |
| `-XX:ActiveProcessorCount=4` | 4 | 4 | 1 |

Đây là **kết quả quan sát trên một JDK/platform**, không phải quy tắc tính số GC threads bất biến. Số concurrent marking workers không tự tăng gấp bốn chỉ vì active processors tăng từ 1 lên 4.

### Khi CPU quota bị throttling

Nếu một container được giới hạn CPU time, các GC threads có thể phải chờ scheduler. Khi đó:

- G1 pause **Real time** có thể tăng, nhất là với workload sát quota.
- `User`/`Sys` không nhất thiết tăng cùng tỷ lệ, vì thời gian chờ scheduler không phải CPU time đang thực thi.
- `Parallel Workers` ở `gc,init` có thể vẫn ghi giá trị đã chọn khi khởi động.
- Số lần GC có thể đổi do throughput/allocation schedule của application thay đổi.
- **Không thể xác nhận throttling chỉ từ GC log**. Cần xem **`cpu.stat`** và metrics của runtime/container cùng mốc thời gian.

Với cgroups v2:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
~~~

`cpu.max` chứa quota và period (hoặc `max` nếu không hard quota). `cpu.stat` có các counters CPU usage/throttling, ví dụ `nr_throttled` và `throttled_usec` khi được kernel hỗ trợ. **Kiểm tra mount cgroup thực tế**, vì đường dẫn và các file có thể khác giữa cgroups v1/v2 hoặc container runtime.

**Cảnh báo khác biệt release:** HotSpot JDK 10 nâng cao container awareness trên Linux; hỗ trợ cgroups v2 được bổ sung ở các JDK sau và backport vào một số dòng. Cần sử dụng JDK còn được cập nhật và phù hợp Linux host. Từ JDK 19, việc suy đoán active CPUs từ shares/weight cũ **không còn là mặc định**. Không mang các hướng dẫn `UseContainerCpuShares` cũ vào bài vận hành hiện nay.

## 13. Memory limit thay đổi: đọc heap, native memory và kernel events riêng

Giả sử container có hard memory limit `512Mi`, JVM đặt `-Xmx384m`. **512−384=128 MiB chỉ là khoảng chênh lý thuyết** cho những thành phần ngoài heap:

- Metaspace/class metadata;
- JIT/code cache;
- Thread stacks và native JVM;
- Direct buffers, JNI/native libraries;
- Memory mappings và các bộ nhớ mà cgroup tính thêm;
- Page cache và các process khác nếu cùng memory cgroup.

**Không nói “heap trong GC log 300M thì container chắc đang dùng 300M”.** G1 log đo **Java heap**, còn memory controller tính nhiều phần khác.

Với Linux cgroups v2, có thể đối chiếu:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
~~~

**Lưu ý nền tảng:** một số file như `memory.peak` phụ thuộc kernel; đường mount có thể khác; cgroups v1 có file names khác. Không kết luận “không giới hạn memory” chỉ vì một path mẫu không tồn tại.

### Java `OutOfMemoryError` khác OOMKill

- **Java heap OOME** có thể có `java.lang.OutOfMemoryError: Java heap space` và GC logs cho thấy heap exhaustion hoặc nỗ lực Full GC; tùy policy JVM có thể sinh heap dump.
- **Kernel/cgroup OOMKill** gửi `SIGKILL` từ bên ngoài JVM. Có thể **không có Full GC hoặc Java OOME trong logs** trước khi process bị kill; shutdown hooks và dump-on-Java-OOME không thể được kích hoạt chỉ vì signal 9.
- Kubernetes `reason: OOMKilled` là dữ liệu runtime quan trọng; **exit 137 riêng lẻ chỉ tương thích với SIGKILL**, không chứng minh nguyên nhân là memory OOM.
- Khi giới hạn container bị thu nhỏ giữa runtime, không tự suy luận heap max/GC workers được điều chỉnh tương ứng. **Nếu `-Xmx` explicit vẫn lớn hơn memory thực có thể dùng, rủi ro kill tăng**.

Phần lab này **không cố ý gây kernel OOM**. Học đọc GC logs không cần cấp phát cho đến khi host/service bị kill; các thí nghiệm quá giới hạn có thể ảnh hưởng workload khác.

## 14. Java lab số 4 — Quan sát một JVM đang chạy

Để phân biệt việc “JVM nhìn thấy gì theo thời điểm” với “GC có bao nhiêu lần thu gom”, tạo **`G1LiveLimitObserver.java`**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class G1LiveLimitObserver {
    static volatile long touched;

    public static void main(String[] args) throws Exception {
        int samples = args.length > 0
                ? Integer.parseInt(args[0]) : 6;
        long delayMs = args.length > 1
                ? Long.parseLong(args[1]) : 50;

        if (samples < 1 || delayMs < 0) {
            throw new IllegalArgumentException(
                    "invalid samples/delay");
        }

        byte[][] keep = new byte[32][];
        for (int sample = 0; sample < samples; sample++) {
            for (int j = 0; j < 32; j++) {
                byte[] block = new byte[128 * 1024];
                block[0] = 1;
                touched += block[0];
                keep[j] = block;
            }

            long gcCount = 0;
            for (GarbageCollectorMXBean bean :
                    ManagementFactory.getGarbageCollectorMXBeans()) {
                long count = bean.getCollectionCount();
                if (count >= 0) gcCount += count;
            }

            System.out.println("sample=" + sample
                    + " cpus=" +
                    Runtime.getRuntime().availableProcessors()
                    + " heap-max-mib=" +
                    Runtime.getRuntime().maxMemory() / (1024 * 1024)
                    + " gc-count=" + gcCount);
            Thread.sleep(delayMs);
        }

        System.out.println("work-done=" +
                (touched == (long) samples * 32));
    }
}
~~~

Biên dịch/chạy trên môi trường Java 10+ để kiểm code:

~~~bash
javac --release 10 G1LiveLimitObserver.java
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -Xmx64m G1LiveLimitObserver 3 10
~~~

**Stdout đã quan sát trên OpenJDK 24.0.2 trong một lần thử:**

~~~text
sample=0 cpus=2 heap-max-mib=64 gc-count=0
sample=1 cpus=2 heap-max-mib=64 gc-count=0
sample=2 cpus=2 heap-max-mib=64 gc-count=1
work-done=true
~~~

**Không hard-code `gc-count=0,0,1` làm expected output cho mọi JVM.** GC là hoạt động phụ thuộc memory pressure/scheduler; có thể có collection count khác. Đầu ra ổn định đáng mong đợi dưới flags đã nêu là `cpus=2`, `heap-max-mib=64` trong runtime test tương tự và `work-done=true`.

### Những gì observer nói được

- Giá trị `availableProcessors()` **tại thời điểm sample**, không phải số CPU time đã thực thi.
- `Runtime.maxMemory()` là **maximum heap**, không phải memory limit của container.
- `GarbageCollectorMXBean.getCollectionCount()` là các số đếm collector cung cấp, có thể trả `-1` nếu không được hỗ trợ; code bỏ qua các giá trị âm.
- Tổng count có thể là số liệu quản lý tổng hợp, **không phải số dòng `GC(n)`** trong mỗi loại log. Không so 1:1 nếu các beans/kiểu collection khác nhau.
- Một lần tăng collection count không chỉ ra loại pause; cần log `-Xlog:gc*` để biết chi tiết.

Với một **tác vụ dài**, chạy `G1LiveLimitObserver 120 1000` trong container rồi đọc stdout và G1 logs trước/sau khi đổi limits. **Đừng giả định CPU count hoặc GC worker pools chắc chắn tự đổi ngay** sau một lần `docker update`. Đây là điều cần **quan sát/đo**, không phải kết quả được hứa trong hợp đồng API.

## 15. Thực hành Linux Docker: thay đổi giới hạn giữa các lần khởi động

**Phần này là bài thực hành đề xuất cho môi trường Linux containers riêng, chưa được chạy trong thử nghiệm Windows của bài viết.** Chỉ thực hiện trên máy/CI container cô lập, không trên node có dịch vụ production.

Bước 1 — biên dịch bằng JDK hỗ trợ `--release 10`:

~~~bash
javac --release 10 G1ResourceLogLab.java G1LiveLimitObserver.java
~~~

Bước 2 — tạo **`Dockerfile`** cùng thư mục:

~~~dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY G1ResourceLogLab.class /app/
COPY G1LiveLimitObserver.class /app/
~~~

Bước 3 — build image:

~~~bash
docker build -t g1-resource-lab .
~~~

Bước 4 — tạo **hai container tạm, hai JVM riêng** với cùng heap/workload nhưng khác CPU quota:

~~~bash
docker run --rm --cpus=1 --memory=512m g1-resource-lab java -XX:+UseG1GC -Xms32m -Xmx96m -Xlog:gc*=info:stdout:uptime,level,tags -cp /app G1ResourceLogLab 240 12 128

docker run --rm --cpus=2 --memory=512m g1-resource-lab java -XX:+UseG1GC -Xms32m -Xmx96m -Xlog:gc*=info:stdout:uptime,level,tags -cp /app G1ResourceLogLab 240 12 128
~~~

**Đọc stdout + log**, không kỳ vọng số `GC(n)`/duration cố định. So:

- `available-processors` do JVM trong container báo;
- `gc,init CPUs: ... available`;
- `Parallel Workers` và `Concurrent Workers`;
- `Pause Young` số lần/độ dài và `gc,cpu` User/Sys/Real;
- Kubernetes/Docker CPU metrics nếu có, để biết có **throttling** thật không.

Giữ `-Xmx96m` cố định để CPU-only comparison không bị lẫn ảnh hưởng heap sizing. `-XX:ActiveProcessorCount` **không được thêm** vào hai lệnh này để JVM tự phát hiện khả năng container của **HotSpot Linux JDK 25**, trong điều kiện môi trường hỗ trợ.

### Bước 5 — memory limit thay đổi, nhưng heap max giữ cố định

~~~bash
docker run --rm --cpus=2 --memory=384m g1-resource-lab java -XX:+UseG1GC -Xms32m -Xmx96m -Xlog:gc*=info:stdout:uptime,level,tags -cp /app G1ResourceLogLab 240 12 128

docker run --rm --cpus=2 --memory=768m g1-resource-lab java -XX:+UseG1GC -Xms32m -Xmx96m -Xlog:gc*=info:stdout:uptime,level,tags -cp /app G1ResourceLogLab 240 12 128
~~~

**Dự đoán hợp lý:** vì **`-Xmx96m` explicit ở cả hai**, `max-heap-mib` vẫn khoảng **96**, trong khi memory hard limit **384/768 MiB** là ràng buộc ở Linux. Dù memory limit thay đổi, Java heap max không tự lấy tỷ lệ mới. Nếu workload và native memory không chạm limit, GC logs có thể rất giống nhau. **Không thấy sự khác biệt là một kết quả có ý nghĩa**, không phải lỗi thí nghiệm.

### Bước 6 — quan sát heap ergonomics khi không đặt `-Xmx`

~~~bash
docker run --rm --memory=512m g1-resource-lab java -XX:+UseG1GC -XX:MaxRAMPercentage=50 -XshowSettings:vm -version

docker run --rm --memory=1g g1-resource-lab java -XX:+UseG1GC -XX:MaxRAMPercentage=50 -XshowSettings:vm -version
~~~

Lần này không đặt `-Xmx`, nên JVM dùng phần memory nhận diện/heap ergonomics để chọn heap max. **Đọc output thực tế** thay vì áp số học chung vì small-heap behavior, MinRAMPercentage, alignment và các yếu tố khác có thể làm khác kết quả 50% chính xác.

### Giới hạn của Docker demo

- Docker command ở trên cần **Docker Engine/Container runtime Linux** và quyền phù hợp.
- `eclipse-temurin:25-jre` là **JRE container image**, không có `javac`; vì thế class files được compile bên ngoài trước khi build.
- Containers có thể dùng **cgroups v1 hoặc v2**, hoặc là Linux VM nếu host dùng Docker Desktop. Cần quan sát runtime bên trong, không lấy CPU của máy development làm CPU container.
- `--cpus=2` là **CPU quota**, không nhất thiết pin process vào hai physical cores.
- Docker `--memory=...` hard limit được kernel thực thi, không phải `-Xmx`.
- Startup/GC logging cần được so theo cùng JDK image digest và host conditions nếu muốn benchmark.
- Lệnh không cố làm container bị OOM kill. Bài đọc G1 logs **không đòi hỏi gây cgroup OOMKill**.

## 16. Thực hành Docker đang chạy: thay đổi limits theo thời gian

Tùy Docker Engine, Linux kernel và quyền của môi trường, `docker update` có thể đổi CPU và memory settings cho một container đang chạy. **Đây là tình huống cần xem kết quả thực tế; không bảo đảm mọi môi trường hỗ trợ đổi hot-update hoặc JVM sẽ resize những thành phần đã khởi tạo.**

Khởi chạy workload dài:

~~~bash
docker run -d --name g1-live-demo --cpus=2 --memory=768m g1-resource-lab java -XX:+UseG1GC -Xms64m -Xmx160m -Xlog:gc*=info:stdout:time,uptime,level,tags -cp /app G1LiveLimitObserver 120 1000
~~~

Ở terminal khác, theo dõi log:

~~~bash
docker logs -f g1-live-demo
~~~

Trong khi container còn chạy, ở terminal quản lý (chỉ với container thử nghiệm), cập nhật:

~~~bash
docker update --cpus=1 --memory=640m g1-live-demo
~~~

Sau đó xác nhận cấu hình engine và cgroup (nếu mount v2 ở vị trí thông thường):

~~~bash
docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}' g1-live-demo

docker exec g1-live-demo sh -c 'cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/cpu.stat; cat /sys/fs/cgroup/memory.max'
~~~

Nếu không cần giữ container, xóa sau khi kết thúc:

~~~bash
docker rm -f g1-live-demo
~~~

**Quan trọng khi diễn giải:**

- `docker update` có thể từ chối thay đổi nếu giới hạn mới không hợp lệ hoặc thấp hơn mức process đang dùng. **Đừng ép memory limit xuống dưới memory current để gây OOM trên môi trường dùng chung**.
- `Runtime.availableProcessors()` **theo Java API có thể thay đổi trong một invocation**, nhưng việc thay đổi có được nhận ở các sampling points phụ thuộc JVM/version/cgroup/OS.
- **G1 `Parallel Workers` được log ở `gc,init` là cấu hình lúc khởi động**; không có cam kết các GC pools đã được khởi tạo sẽ tự thay đổi ngay khi CPU quota đổi.
- `-Xmx160m` là heap max explicit. **Dòng `heap-max-mib` không được kỳ vọng giảm theo Docker memory limit mới**, vì JVM không nhận lại `-Xmx` như một flags update.
- `gc-count` có thể tăng bình thường do workload, không chứng minh lỗi.
- `cpu.stat` thay đổi chỉ ra tình trạng CPU usage/throttling ở cgroup; không dùng mỗi dòng Real của G1 để kết luận.
- Cách thay đổi giới hạn **giữa các lần start JVM** và **trong khi một JVM đang chạy** là **hai thí nghiệm khác nhau**. Ghi rõ chúng trong báo cáo.

**Lưu ý về `docker rm -f`:** lệnh có thể chấm dứt container đang chạy; chỉ dùng với **tên container thử nghiệm do bạn vừa tạo**, không sao chép sang production containers.

## 17. Một kịch bản Kubernetes cần điều tra

Một đoạn YAML thuộc **spec của một container**, không phải file Deployment hoàn chỉnh:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1500m"
    memory: "768Mi"
~~~

Kubernetes có những ngữ nghĩa khác nhau:

- **CPU request** ảnh hưởng scheduling/resource allocation; không đồng nghĩa hard quota đúng 500m.
- **CPU limit 1500m** thường được Linux cgroup áp dưới dạng quota **1.5 CPU time**, có thể bị throttling.
- **Memory request 256Mi** không phải hard cap.
- **Memory limit 768Mi** là hard limit kernel quản lý; khi thiếu memory và reclaim không đủ có thể xảy ra **OOM kill**.
- Với HotSpot hiện đại, việc tính active processors từ quota phân số có thể cần **làm tròn sang số nguyên**. `availableProcessors()` trả `int`, không phải số thực 1.5.
- **CPU shares/weight không được JVM mặc định quy đổi thành active processor count từ JDK 19**. Đừng lấy request 500m rồi kết luận JVM chắc thấy 1 CPU.

### Khi pod bị chậm/đột ngột restart

Đọc trạng thái và log:

~~~bash
kubectl describe pod my-pod -n my-namespace
kubectl logs my-pod -n my-namespace -c app --previous
kubectl top pod my-pod -n my-namespace --containers
~~~

Các lệnh trên có **tên pod/namespace/container minh họa**, cần thay bằng tài nguyên được phép kiểm tra. Đừng tự làm một thao tác thay đổi resource limits trên workload production chỉ để xem khác biệt G1.

Khi `reason: OOMKilled`, đọc memory limit/current/peak/events, native memory, direct buffers, metaspace, thread stacks và file cache. **Không kết luận `-Xmx` hoặc G1 là nguyên nhân duy nhất**, và **không mặc nhiên có Java heap OOME hay Full GC trong log**.

Khi latency tăng nhưng pod còn sống, xem CPU throttling counters/metrics, G1 `gc,cpu`, ứng dụng allocation rate và số requests đồng thời. Một `MaxGCPauseMillis=200` không chứng minh tail latency service <=200ms vì còn I/O, scheduling và nhiều loại chờ khác.

## 18. Cách phân biệt Young, Mixed, Concurrent và Full trong log

| Dấu hiệu log G1 | Cách hiểu | Câu hỏi tiếp theo |
| --- | --- | --- |
| `Pause Young (Normal)` | Young-only evacuation pause | Allocation rate, survivors, promotion, pause duration |
| `Pause Young (Concurrent Start)` | Young pause khởi đầu một concurrent marking cycle | Vì sao cần marking lúc này? Occupancy/IHOP/humongous? |
| `Concurrent Mark Cycle` | Concurrent cycle có các bước và pauses liên quan | Có hoàn tất kịp trước áp lực old heap? |
| `Pause Remark` | Pause thuộc marking cycle | Độ dài và work của remark/refs/class unloading |
| `Pause Cleanup` | Hoàn tất/dọn dẹp liên quan marking | Có mixed candidates hiệu quả không? |
| `Pause Young (Prepare Mixed)` | Chuyển sang giai đoạn sẽ thu gom old candidates | Có bao nhiêu old candidates và cost ước lượng? |
| `Pause Young (Mixed)` | Thu gom young **và các old regions được chọn** | Mixed quá lâu hoặc không thu hồi đủ old? |
| `Pause Full (G1 Compaction Pause)` | Stop-the-world full heap collection | Heap occupancy, allocation failure, marking không kịp, explicit GC? |
| `Evacuation Failure: Allocation/Pinned` | Một số object không move được vì allocation/pinning | Có thiếu to-space hay JNI critical/pinned? |
| `Humongous regions: X->Y` | Số regions dùng cho large objects | Có arrays/strings/buffers quá lớn, region fragmentation? |

**Đừng nghĩ các loại này luôn xuất hiện theo một chuỗi cứng.** Workload lab cấp array 128KiB chủ yếu tạo Young pauses. Một run không có Mixed hoặc Full GC là hoàn toàn hợp lệ và không có nghĩa G1 đã bị vô hiệu.

### Humongous allocation không giống leak

Khi object lớn hơn hoặc bằng **một nửa G1 region**, nó có thể đi vào humongous regions và tạo áp lực vùng liên tục; việc có nhiều humongous objects làm tăng rủi ro fragmentation hoặc Full GC trong một số tình huống. Tối ưu trước tiên là **xác định và giảm allocations lớn không cần thiết**, cân nhắc region size/heap chỉ sau khi có bằng chứng. Không kết luận tăng `-XX:G1HeapRegionSize` luôn cải thiện throughput; nó làm thay đổi đánh đổi về overhead/fragmentation.

### Evacuation failure không phải mọi lúc một Java OOME

Evacuation failure là G1 không move được một số objects. G1 có đường xử lý dự phòng, và việc thấy một dòng failure **không có nghĩa process đã chết**. Nếu đi kèm Full GC liên tiếp và heap after-GC gần đầy, cần xem live set, mark progress, promotion pressure, humongous objects và loại nguyên nhân failure. Trên JDK mới, có thể có reason `Pinned` bên cạnh `Allocation`; không dựa vào danh sách old logs của JDK 8 để diễn giải hiện đại.

## 19. Mẫu bảng so sánh có thể điền sau khi chạy

| Chỉ số | Run A | Run B | Nguồn bằng chứng |
| --- | --- | --- | --- |
| JDK vendor/build | ghi đúng | ghi đúng | `java -version`, container image digest |
| Tên workload/args | ghi đúng | ghi đúng | commandline, app stdout |
| Kernel CPU quota | ghi đúng | ghi đúng | `cpu.max`/Docker inspect |
| CPU active JVM | ghi đúng | ghi đúng | app stdout, `gc,init` |
| G1 Parallel Workers | ghi đúng | ghi đúng | `gc,init` |
| G1 Concurrent Workers | ghi đúng | ghi đúng | `gc,init` |
| CPU throttling time | ghi đúng | ghi đúng | `cpu.stat`/metrics |
| Memory hard limit | ghi đúng | ghi đúng | `memory.max`/Docker inspect |
| `-Xmx` hoặc RAM% | ghi đúng | ghi đúng | JVM args |
| Max heap JVM thấy | ghi đúng | ghi đúng | `Runtime.maxMemory()` |
| Committed heap trong log | ghi đúng | ghi đúng | `before->after(committed)` |
| Số Young/Mixed/Full pauses | ghi đúng | ghi đúng | Log parser/GC events |
| Pause p95/p99 | tính trên đủ mẫu | tính trên đủ mẫu | Log analysis |
| GC total time / throughput | ghi đúng | ghi đúng | GC metrics + workload |
| Service p95/p99 latency | ghi đúng | ghi đúng | Application monitoring |
| Cgroup OOM/kill events | ghi đúng | ghi đúng | `memory.events`/Kubernetes status |

Đây là **mẫu báo cáo**, không phải bảng kết quả sẵn của những thử nghiệm Docker chưa chạy. Khi so sánh:

- **Giữ workload, JDK, heap flags ổn định** nếu muốn cô lập tác động CPU.
- **Giữ CPU và workload ổn định** nếu muốn cô lập tác động heap.
- Nếu dùng `MaxRAMPercentage`, ghi chính xác RAM mà JVM detect thay vì tự giả định nó bằng `--memory`.
- Không so một run mới startup/cold JIT với run đã warmup như thể chúng hoàn toàn tương đương.
- Có ít GCs thì **p99 pause thiếu ý nghĩa thống kê**; không hứa percentile đáng tin từ 19–20 pauses.
- Cần nhiều lần đo trên runtime Linux thật trước khi đưa ra quyết định scaling/production.

## 20. Phương pháp đọc một sự cố GC thực tế

1. **Xác nhận collector.** Tìm `Using G1`. Nếu không dùng G1 thì đừng diễn giải theo region/young-mixed của G1.
2. **Xác nhận JVM flags/heap.** `-Xmx`, `-Xms`, `MaxRAMPercentage`, `ActiveProcessorCount`, `MaxGCPauseMillis` và GC version.
3. **Xác nhận container resource limits.** CPU quota/cpuset, memory.max, cgroups version; đọc dữ liệu từ đúng container JVM.
4. **Nối timestamps.** `uptime` trong log với application time, deployment/resizing event và Kubernetes events.
5. **Phân loại pauses.** Young Normal/Concurrent Start/Mixed/Full; không gộp mọi dòng vào một loại “GC”.
6. **Đọc before/after/committed.** `used before/after` vs heap committed ở ngoặc vs JVM max heap.
7. **Đọc các regions.** Eden/Survivor/Old/Humongous, xem promotions/region pressure.
8. **Đọc `Parallel Workers`/`Concurrent Workers` và event-level workers.** Không giả sử tất cả threads đang chạy đồng thời.
9. **Đọc `User/Sys/Real`.** Nếu wall time tăng nhưng CPU time không tăng, xem scheduling, throttling, OS/I/O.
10. **Kiểm tra cgroup metrics.** CPU `nr_throttled`/`throttled_usec`, memory current/peak/oom_kill, node pressure.
11. **Phân biệt Java heap OOME với OOMKilled.** Kernel kill có thể không tạo Java exception hay heap dump.
12. **Đọc timeline resource change.** Thay limits giữa hai JVM starts khác việc đổi live limits của cùng process.
13. **Kiểm tra old-live set/mark progress.** Full GC liên tục thường cần điều tra allocation/retention trước khi tăng flags.
14. **Kiểm tra humongous và evacuation failures.** Có thể gợi ý áp lực to-space/fragmentation hoặc pinned objects.
15. **Đánh giá workload thật.** G1 pauses ảnh hưởng độ trễ nhưng không thay toàn bộ HTTP/database/network latency.
16. **Chỉ thay một nhóm biến khi tuning.** Bắt đầu bằng app allocation, heap budget và pause goal; không bật nhiều cờ G1 cùng lúc.
17. **Lưu raw logs/metrics, version và test args.** Không lấy screenshot một dòng log làm toàn bộ kết luận.
18. **QA câu kết luận bằng bằng chứng:** Phân biệt “đã quan sát”, “có thể do” và “chưa xác minh”.

### Ví dụ một lập luận đúng

“Trong hai lần JVM **khởi động riêng biệt**, `ActiveProcessorCount` đổi 1→4; G1 `Parallel Workers` tại init đổi 1→4. Mỗi run xử lý đúng workload 360MiB đã cấp phát tổng và không gặp Full GC trong mẫu thử. Số Young pauses/độ dài khác nhau đôi chút nhưng chưa có đủ bằng chứng kết luận lợi ích hiệu năng. **Đây không phải phép thử thay đổi quota kernel trong một JVM đang chạy.**”

### Ví dụ kết luận sai

“Run với 4 GC workers có max pause cao hơn một chút nên G1 hoạt động tệ khi CPU tăng; chỉ cần đặt `ParallelGCThreads=1` trong production là tốt nhất.”

Kết luận sai vì chỉ có một mẫu chạy, không kiểm cgroup throttle/workload noise, chưa đo throughput/tail latency và tự ép G1 ergonomics. Cần thí nghiệm có đối chứng trước khi tuning.

## 21. Những sai lầm hay gặp khi đọc G1 logs

| Sai lầm | Vì sao sai? | Cách đọc đúng |
| --- | --- | --- |
| “G1 chỉ xuất hiện từ Java 10” | G1 đã có trước, là default từ JDK 9 trong HotSpot phổ biến | Java 10 liên quan container awareness |
| “`GC(7)` nghĩa bảy collections trong dòng này” | Đây là event ID | Ghép tất cả dòng cùng ID |
| “Một dòng `gc,start` và một dòng `gc` là hai GC khác nhau” | Cùng một event có nhiều dòng | Đếm summary lines hoặc GC events |
| “`7M->2M(34M)` nghĩa `-Xmx34m`” | 34M là committed heap trong log | `-Xmx` phải đọc riêng |
| “GC giải phóng 5M thì OS RSS chắc giảm 5M” | Heap used khác committed/cgroup RSS | Kiểm container memory metrics |
| “`Real=0.00s` nghĩa pause dài 0ms” | Dòng CPU thời gian bị làm tròn | Dùng duration ms của pause summary |
| “4 active CPUs nghĩa 4 workers thực chạy mỗi GC” | G1 chọn workers theo phase/ergonomics | Đọc `gc,task`/`gc,init` |
| “Concurrent Workers luôn bằng Parallel Workers” | Hai policies riêng | Quan sát từng giá trị |
| “`MaxGCPauseMillis=200` là SLA 200ms” | Chỉ soft goal | Đo pause distribution |
| “Không có Full GC = không có vấn đề memory” | Kernel OOMKill/native memory vẫn có thể xảy ra | Xem memory cgroup |
| “Exit 137 = Java OOME” | 137 thường tương thích SIGKILL | Xem Kubernetes reason/events |
| “`OOMKilled` chắc có heap dump” | Kernel kill không kích Java OOME hook | Chẩn đoán bằng cgroups/kernel logs |
| “Đổi memory limit thì `-Xmx` tự đổi” | Explicit heap max không được cập nhật theo YAML | Tách VM flags và kernel cap |
| “`ActiveProcessorCount` thay CPU quota thật” | Flag chỉ ảnh hưởng JVM count | Kiểm `cpu.max` |
| “Memory request = hard memory limit” | Request phục vụ scheduling | Đọc limits/cgroup |
| “CPU request 500m chắc JVM thấy 1 CPU” | Shares/weight không hard quota, JDK19 thay mặc định | Đo JVM và quota thật |
| “Tăng Old regions có nghĩa leak” | Có thể chỉ promotions/chu kỳ chưa reclaim | Xem live set sau GC & heap dump |
| “Humongous = mọi object lớn” | Threshold theo **region size/2** | Kiểm region size và object allocation |
| “Evacuation failure luôn chết JVM” | Có thể có fallback/retry | Xem sự kiện tiếp theo và heap pressure |
| “Log 20 events đủ tính p99 production” | Mẫu quá nhỏ | Thu nhiều mẫu workload thật |
| “Một parser regex là chuẩn tương thích mọi JDK” | Log format thay đổi | Dùng parser theo version và fixtures |
| “Dùng cờ logging cũ từ JDK 8 vẫn tốt nhất” | Unified logging `-Xlog` là hướng hiện hành | Dùng `java -Xlog:help` |
| “Cứ giảm young gen bằng `-Xmn` sẽ giảm pause” | G1 cần tự điều chỉnh young set | Ưu tiên defaults/heap/pause goal |
| “Full GC nào cũng do hết `-Xmx`” | Có thể do explicit GC, marking không kịp, humongous, policy | Xem cause và context |
| “Giới hạn đổi live thì G1 pool chắc resize ngay” | Không có bảo đảm tổng quát | Quan sát trên JDK/container thật |

## 22. Checklist QA và các phép thử nên thực hiện

- [ ] Đã đọc đúng **`java -version`** và thấy **`Using G1`** trong log.
- [ ] Đã kiểm `-Xlog:help` khi cần về tags/levels/decorators.
- [ ] Đã chạy `G1ResourceLogLab` với **`javac --release 10`**.
- [ ] Cả 2 runs CPU1/CPU4 hoàn thành đúng 2880 chunks/360MiB tổng allocations/checksum.
- [ ] Hai lần chạy **tách biệt** giữ nguyên `-Xms32m` và `-Xmx96m`.
- [ ] Log init cho thấy `available CPUs` và `Parallel Workers`, không giả định tất cả GC threads tăng cùng tỷ lệ.
- [ ] Đã hiểu `7M->2M(34M)`: before/after used và committed heap, không phải maximum.
- [ ] Đã nhìn `gc,heap` cho Eden/Survivor/Old/Humongous.
- [ ] Đã phân biệt `Pause Young` với `Pause Full` và concurrent events.
- [ ] Đã hiểu `User/Sys/Real` và không gán ngay Real lớn cho CPU throttling.
- [ ] Đã biên dịch `G1LogInspector` và đọc được hai log files đã ghi.
- [ ] Đã chạy `G1LogParserFixture` với **2 Young/1 Full**, parser test PASS.
- [ ] Đã phân biệt fixture là log giả định với logs thực tế có số pauses biến thiên.
- [ ] Đã biên dịch `G1LiveLimitObserver`; không dùng gc-count cụ thể làm expected cứng.
- [ ] Đã xem `MaxRAMPercentage` và tình huống **small-heap ergonomics** trước khi tính tỉ lệ.
- [ ] Nếu có Linux container, đã đọc cgroup `cpu.max`/`cpu.stat`/`memory.max`/`memory.events`.
- [ ] Nếu thay resource limits live, đã ghi trước/sau `docker inspect` và bảo vệ container thử nghiệm.
- [ ] Không nhận nhầm `-XX:ActiveProcessorCount` là thay CPU quota kernel.
- [ ] Không nhận nhầm `-Xmx` là tổng memory limit container.
- [ ] Không cố ý gây OOMKill trên host/cluster dùng chung để phục vụ bài lab.
- [ ] Không dùng `PrintGCDetails`/`PrintGCTimeStamps` cũ thay cho `-Xlog` trên JDK hiện đại.
- [ ] Không tuyên bố đã kiểm Docker/Linux nếu chỉ có bằng chứng Java flags trên Windows.
- [ ] Tài liệu/flags ứng dụng phù hợp JDK hiện đang vận hành, không lấy defaults của Java 10 lịch sử làm mặc định vĩnh viễn.
- [ ] Kết luận hiệu năng chỉ sau khi có nhiều phép đo, metrics workload và cgroup cùng thời điểm.

## 23. Câu hỏi tự kiểm tra

1. G1 được đưa vào Java từ Java 10 hay đã có trước?
2. `-Xlog:gc*=info` khác `-Xlog:gc` như thế nào?
3. `GC(9)` trong log là event ID hay số thread GC?
4. `7M->2M(34M) 0.881ms` có bốn giá trị nào cần hiểu?
5. `(34M)` có chứng minh `-Xmx` bằng 34MiB không?
6. `Parallel Workers: 4` có nghĩa mỗi collection luôn dùng đúng 4 workers không?
7. `Concurrent Workers` có luôn bằng `Parallel Workers` không?
8. `User` lớn hơn `Real` có thể xảy ra khi nào?
9. `Real=0.00s` trong `gc,cpu` có chứng minh pause bằng 0ms không?
10. Khi memory hard limit giảm còn ít, JVM explicit `-Xmx` có tự giảm ngay không?
11. `-XX:ActiveProcessorCount=2` có đổi cgroup `cpu.max` không?
12. `CPU quota 1.5` có cho phép `Runtime.availableProcessors()` trả 1.5 không?
13. Thấy `Pause Young (Mixed)` nghĩa thu gom toàn bộ Old không?
14. Khi nào G1 có thể chạy Full GC?
15. Humongous object có threshold gì so với G1 region?
16. `-XX:MaxGCPauseMillis=200` có phải ngưỡng bảo đảm không?
17. `-XX:MaxRAMPercentage=25` với `MaxRAM256m` có bắt buộc cho heap 64MiB không?
18. Vì sao chỉ nhìn `Old regions` tăng chưa đủ chẩn đoán leak?
19. Vì sao `G1LogInspector` không đếm `Concurrent Mark Cycle`?
20. Vì sao `G1LogParserFixture` có Full GC trong khi lab thực tế không?
21. Exit code 137 có đủ chứng minh container `OOMKilled` không?
22. `docker update` thành công có nghĩa GC worker pool JVM tự resize không?
23. Tại sao hai JVM chạy cùng `-Xmx96m` dưới memory limit 384MiB và 768MiB có thể có G1 log rất giống?
24. Khi so sánh hiệu năng G1, tại sao cần cả cgroup throttling metrics và application latency?

**Đáp án:**

1. G1 đã có trước và là collector default trong HotSpot phổ biến từ **Java 9**; Java 10 cải thiện container awareness.
2. `gc*` chọn cả tag sets chứa `gc` như `gc,heap`/`gc,init`/`gc,cpu`, cho nhiều chi tiết.
3. **Event ID**.
4. Heap used trước, heap used sau, heap committed, pause duration.
5. Không; `-Xmx` là maximum riêng của JVM.
6. Không; event-level worker count có thể khác.
7. Không. Thí nghiệm CPU1/CPU4 có Concurrent Workers đều 1.
8. Nhiều GC threads tiêu CPU song song nên tổng user CPU time có thể lớn hơn elapsed time.
9. Không; log CPU time có rounding, xem summary pause ms.
10. Không có bảo đảm; nếu `-Xmx` explicit, kernel cap và JVM heap limit là hai điều kiện khác.
11. Không; nó override số CPU JVM dùng cho ergonomics.
12. Không; Java API trả **`int`**.
13. Không; Mixed chọn một số old candidate regions cùng young.
14. Khi G1 cần fallback, ví dụ allocation/evacuation pressure hoặc nguyên nhân explicit khác.
15. **Kích thước từ một nửa region trở lên**.
16. Không, chỉ soft target.
17. Không; small-heap ergonomics/`MinRAMPercentage` có thể làm khác kết quả.
18. Old có thể tăng do promotion/marking cycle, chưa chứng minh live set tăng vĩnh viễn.
19. Parser mục đích hẹp chỉ nhận Pause Young/Full summary.
20. Fixture là **dữ liệu tổng hợp để test parser**, không phải event log thực tế.
21. Không; 137 thường do SIGKILL, cần reason/events.
22. Không; đây là hành vi cần đo trên runtime/container version.
23. Explicit heap max bằng nhau; nếu container vẫn đủ memory, G1 có thể gần như không thay đổi.
24. GC log không trực tiếp đo kernel CPU throttle hay toàn bộ latency/end-to-end throughput.

## 24. Nguồn chính thức còn áp dụng

- **Oracle JDK 25 — Garbage-First (G1) Garbage Collector: internals, pauses, mixed, humongous, evacuation failures:** https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html
- **Oracle JDK 25 — Garbage-First Garbage Collector Tuning: general recommendations, Full GC và User/Sys/Real:** https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html
- **Oracle JDK 25 — Garbage Collector Implementation: các dòng G1 logs và phân biệt phases:** https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html
- **Oracle JDK 25 — `java` command, `-Xlog`, `ActiveProcessorCount`, `MaxRAMPercentage`, `MinRAMPercentage` và container support:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **OpenJDK JEP 248 — Make G1 the Default Garbage Collector (Java 9):** https://openjdk.org/jeps/248
- **OpenJDK — JDK-8146115, Linux container CPU/memory awareness trong Java 10:** https://bugs.openjdk.org/browse/JDK-8146115
- **OpenJDK — JDK-8230305, hỗ trợ cgroups v2 trong JDK mới:** https://bugs.openjdk.org/browse/JDK-8230305
- **Oracle JDK 19 Release Notes — CPU shares bị bỏ khỏi cách tính active CPUs theo mặc định (JDK-8281181):** https://www.oracle.com/java/technologies/javase/19-relnote-issues.html
- **Linux kernel — Control Group v2: `cpu.max`, `cpu.stat`, `memory.max`, `memory.events`:** https://docs.kernel.org/admin-guide/cgroup-v2.html
- **Kubernetes — Resource Management for Pods and Containers, CPU throttling và reactive memory OOM kills:** https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- **Oracle Java SE 25 — `Runtime` và `availableProcessors()`/`maxMemory()`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html
- **Oracle Java SE 25 — `GarbageCollectorMXBean` và `getCollectionCount()`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html

**Kết luận:** Khi tài nguyên thay đổi, đọc **G1 log đồng thời với JVM flags, cgroup CPU/memory metrics và application workload**. `GC(n)` liên kết các dòng thuộc cùng sự kiện; `Pause Young/Mixed/Full` cho biết loại hoạt động; `7M->2M(34M)` là **Java heap used trước/sau và committed hiện tại**, không phải memory limit hoặc `-Xmx`; `gc,init` cho biết cấu hình workers lúc startup; `User/Sys/Real` hỗ trợ nhận biết vấn đề CPU scheduling nhưng không tự chứng minh throttling. Thay đổi **JVM CPU/heap flags giữa hai lần khởi động** và **thay đổi giới hạn cgroup khi JVM đang chạy** phải được đánh giá riêng. Từ dữ liệu lab một lần không được kết luận hiệu năng G1 tốt/xấu hay khẳng định có leak; hãy dùng **lặp lại phép đo, ứng dụng metrics và nguồn chính thức của JDK hiện hành**.