# Java 11+ — GC độ trễ thấp: ZGC và mục tiêu thu gom với thời gian dừng ngắn

## 1. ZGC giải quyết vấn đề gì?

**ZGC** (*Z Garbage Collector*) là bộ thu gom rác của HotSpot được thiết kế để giảm **thời gian tạm dừng các luồng ứng dụng do Garbage Collection (GC)**, đặc biệt khi heap lớn hoặc dịch vụ rất nhạy cảm với **tail latency**. ZGC được đưa vào JDK 11 theo **JEP 333** dưới dạng **thử nghiệm** và hiện đã phát triển thành bộ thu gom được hỗ trợ chính thức; các JDK hiện đại chỉ còn **Generational ZGC**.

Đặt vấn đề bằng một dịch vụ Java:

- Khi một request cần 10 ms xử lý nghiệp vụ nhưng JVM gặp **Stop-The-World (STW) GC pause** dài 100 ms, request có thể chậm đáng kể dù bản thân code ứng dụng không đổi.
- Nếu tối ưu chỉ nhìn **throughput trung bình** mà bỏ qua p99/p99.9, một số ít request bị chậm vẫn có thể vi phạm SLA.
- Nếu heap tăng lên hàng chục hoặc hàng trăm GB, một GC cần dừng tất cả application threads để duyệt/di chuyển toàn bộ tập object sống có thể tạo ra pause khó chấp nhận.

ZGC giải quyết bằng cách chuyển **phần lớn công việc nặng** — đánh dấu (*marking*), xử lý tính khả dụng, chuẩn bị di dời (*relocation*) và di dời object — sang các **pha concurrent**, tức **chạy đồng thời với application threads**. GC vẫn có một số **điểm đồng bộ STW rất ngắn**, nhưng khối lượng cần xử lý ở những điểm đó được thiết kế hạn chế hơn và không tăng trực tiếp theo toàn bộ heap/live set như các pha STW lớn của nhiều thiết kế khác.

**Mục tiêu thiết kế ban đầu của ZGC trong JDK 11:**

1. **GC pause không vượt quá khoảng 10 ms** (mục tiêu trong JEP 333, **không phải bảo đảm thời gian cứng**).
2. Thời gian pause không tăng theo kích thước heap hoặc tập object còn sống (*live set*) trong điều kiện thiết kế dự kiến.
3. Hỗ trợ heap từ kích thước tương đối nhỏ đến nhiều TB trên các hệ thống phù hợp.

Trong hướng dẫn ZGC hiện đại của Oracle, các GC pause thường được mô tả ở mức **vài mili giây hoặc thấp hơn**. Điều này **không có nghĩa** request latency, toàn bộ GC cycle, allocation stall hoặc tổng thời gian chạy ứng dụng đều phải dưới 10 ms.

### Điểm cốt lõi

> **“Low-pause GC” không đồng nghĩa “no pause”, “no overhead”, “no OutOfMemoryError” hoặc “mọi request đều phản hồi dưới 10 ms”.** ZGC ưu tiên giảm các khoảng STW của GC, trong khi throughput, CPU, memory headroom và tác động tới application tail latency vẫn phải được đo bằng workload thực tế.

## 2. Java 11 và ZGC hiện hành: phân biệt theo phiên bản

Đây là phần quan trọng nhất để tránh làm theo chỉ dẫn đã lỗi thời.

| Phiên bản JDK | Trạng thái ZGC | Cách chọn/điểm cần nhớ |
| --- | --- | --- |
| **JDK 11** | **Experimental** theo **JEP 333**; triển khai ban đầu **non-generational**. Bản đầu hỗ trợ Linux/x64. | Cần đặt `-XX:+UnlockExperimentalVMOptions` **trước** `-XX:+UseZGC`; phải kiểm tra nền tảng và bản JDK thực tế. |
| **JDK 15** | **Production feature** theo **JEP 377**. | Chọn bằng `-XX:+UseZGC`, **không cần** cờ mở tính năng thử nghiệm chỉ để bật ZGC. |
| **JDK 21** | **Generational ZGC** được thêm theo **JEP 439** như một chế độ opt-in; non-generational vẫn tồn tại. | `-XX:+ZGenerational` là cờ **lịch sử dành cho giai đoạn chuyển đổi**, không phải lệnh nên copy sang JDK mới nhất. |
| **JDK 23** | **Generational ZGC trở thành mặc định** khi đã chọn ZGC, theo **JEP 474**; non-generational bị deprecated. | Không cần yêu cầu generational riêng để có chế độ mặc định. |
| **JDK 24 trở lên** | **Non-generational ZGC bị loại bỏ** theo **JEP 490**; ZGC chỉ còn generational. | Dùng `-XX:+UseZGC`. **Không hướng dẫn bật/tắt `-XX:ZGenerational` như một cấu hình hợp lệ hiện hành.** |

**Trọng tâm của bài là ZGC vẫn đang được sử dụng**, còn các chi tiết JDK 11 thử nghiệm được nêu để đọc hiểu và vận hành đúng hệ thống Java 11. Không khuyến nghị áp dụng các giới hạn cũ của bản thử nghiệm (ví dụ “ZGC mãi mãi chỉ chạy Linux” hoặc “ZGC không có generations”) cho JDK hiện đại.

Lưu ý rằng **`-XX:+UseZGC` không phải default collector của mọi JVM**. Khi không chỉ định, HotSpot có thể chọn collector khác như G1 tùy phiên bản, môi trường và cấu hình. Đừng nhìn JDK version rồi tự suy ra ZGC đã bật; cần xác minh bằng logs, MXBeans hoặc JVM flags.

### 2.1. Lệnh dùng cho JDK 11 — chỉ trên bản/nền tảng thực sự hỗ trợ

```bash
# JDK 11 ZGC bản đầu: Linux/x64, experimental.
java -XX:+UnlockExperimentalVMOptions -XX:+UseZGC \
  -Xms128m -Xmx256m \
  -Xlog:gc*:file=zgc11.log:uptime,level,tags \
  ZgcGcProbe ZGC
```

Đây là lệnh dành cho lớp `ZgcGcProbe` trong mục 8 sau khi biên dịch, **nếu** bản JDK 11/Linux/x64 được cài hỗ trợ ZGC và giới hạn heap phù hợp. **Không** chạy nó trên JDK 11/Windows rồi coi lỗi không bật được là lỗi của ứng dụng Java. Đối với Java 11, `-XX:+UnlockExperimentalVMOptions` phải xuất hiện **trước** `-XX:+UseZGC`.

JDK 11 ban đầu còn có các giới hạn thử nghiệm như không hỗ trợ class unloading và compressed oops/class pointers trong cấu hình đó. Đó là **hạn chế theo phiên bản lịch sử**, không phải đặc trưng của ZGC trên mọi JDK hiện hành. Nếu vẫn phải vận hành JDK 11, kiểm tra **đúng vendor/build/update release** và tài liệu của bản triển khai thay vì suy đoán từ tài liệu JDK mới.

### 2.2. Lệnh hiện đại — chọn Generational ZGC bằng một cờ

```bash
# Ví dụ JDK 24+ / HotSpot hiện đại.
java -XX:+UseZGC -Xms128m -Xmx256m \
  -Xlog:gc*:file=zgc.log:uptime,level,tags \
  ZgcGcProbe ZGC
```

Không thêm `-XX:+ZGenerational` vì chế độ non-generational đã bị loại bỏ từ JDK 24. Cũng không cần thêm `-XX:+UnlockExperimentalVMOptions` chỉ để chạy ZGC hiện đại.

**Đừng copy toàn bộ cấu hình của bản JDK 11 sang JDK 24+**: collector đã thay đổi đáng kể, đặc biệt là **young/old generations, barriers, ergonomics, log events và tuning flags**.

## 3. STW pause, concurrent cycle và độ trễ request là ba phép đo khác nhau

Một ứng dụng có thể trông giống thế này trên trục thời gian:

```text
Thời gian ---------------------------------------------------->

Application threads:
RUN -------- |STW| -------- RUN ---------------- |STW| ----- RUN

ZGC worker threads:
              [ Concurrent Mark / Relocate / Reclaim ........ ]

Request A:
    start ------- work / waiting / lock / I/O ----------- end

GC pause duration:  chỉ phần |STW| mà GC báo
GC cycle duration:  toàn khoảng xử lý GC, gồm concurrent phases
Request latency:    từ lúc request đến lúc trả lời, gồm nhiều thành phần
```

| Đại lượng | Đang đo gì? | Không nên kết luận |
| --- | --- | --- |
| **GC STW pause** | Thời gian JVM ngừng các application threads vì một pha GC pause. | Không phải tổng thời gian GC cycle. |
| **Concurrent GC cycle** | GC xử lý phần lớn việc trong lúc application threads tiếp tục chạy. | Không phải toàn thời gian đó ứng dụng bị treo. |
| **Allocation stall** | Thread cấp phát phải chờ khi GC/allocator chưa cung cấp được bộ nhớ phù hợp. | Không đồng nhất với “GC STW pause” dù cũng làm request chậm. |
| **Request end-to-end latency** | Thời gian xử lý HTTP/RPC/task từ đầu đến cuối. | Không chỉ do GC quyết định. |
| **p99/p99.9 latency** | Phân vị 99%/99.9% của các request đã quan sát. | Không suy ra chỉ từ pause lớn nhất trong một log GC. |
| **Throughput** | Request/s, job/s, MB/s hoặc công việc hoàn thành trên đơn vị thời gian. | GC có pause thấp nhất luôn đạt throughput cao nhất. |
| **GC CPU** | CPU core-time dành cho GC threads, nhất là concurrent workers. | Không thể chỉ nhìn STW pause để biết chi phí CPU. |
| **Heap occupancy / RSS** | Heap sử dụng và memory resident của process/container. | Không phải cùng đại lượng; native memory nằm ngoài Java heap. |

Ví dụ, ZGC ghi `Pause Mark Start 0.02ms` không chứng minh request chỉ chậm `0.02ms`: trong cùng lúc request có thể chờ database 200 ms, nghẽn thread pool, bị CPU throttling hoặc gặp allocation stall. Ngược lại, một lần p99 tăng không nên mặc định quy cho ZGC nếu không có **tương quan timestamp, log GC và tracing**.

**Mục tiêu dừng ngắn là mục tiêu thiết kế, không phải hard real-time guarantee.** OS scheduling, safepoint synchronization, native code, contention, page faults và các yếu tố khác vẫn có thể ảnh hưởng latency. Cần xây một SLO riêng cho ứng dụng và kiểm thử với tải thật.

## 4. Cơ chế chính: phần lớn công việc được làm concurrently

Một chu trình ZGC có thể được hiểu ở mức khái niệm:

```text
       GC cần khởi động một chu kỳ
                     |
             +-------v--------+
             | STW sync point |
             | Pause Mark ... |
             +-------+--------+
                     |
               Concurrent Mark
        duyệt/đánh dấu objects còn sống
        trong khi Java threads tiếp tục chạy
                     |
            +--------v--------+
            | STW sync point  |
            | kết thúc mark   |
            +--------+--------+
                     |
         Concurrent Prepare Relocation
         xác định vùng/đối tượng cần di chuyển
                     |
             +-------v--------+
             | STW sync point |
             | relocation     |
             +-------+--------+
                     |
             Concurrent Relocation
          di chuyển/cập nhật references
          trong khi Java threads tiếp tục chạy
```

Đây là sơ đồ **khái niệm về ZGC**, đặc biệt hữu ích khi đọc log **non-generational ZGC**. Trên **Generational ZGC** hiện đại, hệ thống còn phân chia young/old, các hoạt động GC có cấu trúc minor/major và tên pha/log có thể khác. Không dùng sơ đồ để khẳng định mọi JVM version có cùng số pha, thứ tự log hay phương thức quản lý references.

### 4.1. Concurrent marking

Khi app đang chạy, Java threads có thể **tạo object mới** và **thay đổi tham chiếu**; trong lúc đó GC cần tìm các object còn reachable. Việc giữ đúng tính nhất quán của đồ thị đối tượng là thách thức cốt lõi của concurrent marking.

ZGC kết hợp thuật toán đánh dấu/di dời đồng thời với **barriers** ở những truy cập reference thích hợp. Các barrier phối hợp với trạng thái GC để đảm bảo reference vẫn hợp lệ khi objects di chuyển và quan hệ tham chiếu thay đổi.

### 4.2. Colored pointers và load/store barriers

Một trong các ý tưởng kiến trúc quan trọng của ZGC là **colored pointers/metadata bits trong references** và **barriers** giúp nhận biết hoặc xử lý references theo trạng thái GC. Có thể hình dung:

- Reference mang thông tin trạng thái phục vụ GC, không phải chỉ là địa chỉ object thuần.
- **Load barrier** có thể kiểm tra/sửa một reference theo yêu cầu thuật toán.
- Với **Generational ZGC**, việc ghi references giữa các generations cũng được theo dõi bằng **store barriers** và các cơ chế liên quan.
- Khi GC di chuyển object concurrent với Java threads, các barriers giúp ứng dụng tiếp tục truy cập object đúng.

**Không hiểu nhầm:** việc sử dụng colored pointers là **chi tiết triển khai HotSpot**, không phải một cú pháp Java hay API cho phép lập trình viên thao tác bit pointer trực tiếp. Các chi tiết bit layout, số lần barrier, cách tracking references thay đổi theo JDK và kiến trúc CPU.

### 4.3. Tại sao “heap lớn” không bắt buộc “pause lớn”?

Trong một collector mà phần lớn marking/compacting diễn ra **trong STW**, lượng work dừng ứng dụng có thể tăng mạnh theo live set/heap. ZGC nỗ lực **không làm phần lớn công việc đó trong STW**, nên việc tăng heap không trực tiếp làm các pha STW dài tương ứng.

Dù vậy, **concurrent work vẫn phải hoàn tất**. Heap lớn hoặc allocation rate cao có thể làm GC cần thêm CPU/memory/time, và nếu thiếu headroom có thể xảy ra **allocation stalls** hoặc out-of-memory. “Pause không phụ thuộc trực tiếp heap size” **không** có nghĩa “không cần tính heap” hoặc “ZGC luôn phù hợp trên mọi máy”.

## 5. Generational ZGC hiện hành: young và old

Nhiều workload Java có tính chất phổ biến: **phần lớn object được tạo ra và chết sớm**. Một collector **generational** có thể khai thác điều này bằng cách xử lý các object mới và sống lâu theo chiến lược khác nhau.

Với Generational ZGC hiện đại:

- **Young generation** chứa nhiều object mới cấp phát và thường được thu gom thường xuyên.
- **Old generation** chứa object tồn tại lâu hơn, cần được quản lý với tần suất/cách xử lý phù hợp.
- JVM có thể thích nghi kích thước/thu gom generations và phân bổ GC threads theo tải.
- GC vẫn hướng tới **concurrent work + pause ngắn**, không biến young collection thành một “full-heap stop” bắt buộc.
- Barriers và bookkeeping giúp theo dõi references, đặc biệt khi có liên hệ giữa các thế hệ.

Cơ chế này xuất hiện như lựa chọn ở JDK 21, mặc định khi chọn ZGC từ JDK 23, và **duy nhất** từ JDK 24.

### Không dùng tư duy non-generational làm kiến thức hiện hành

Một bài viết từ Java 11 có thể mô tả “ZGC không phân thế hệ” — điều đó **đúng với bản thử nghiệm ban đầu**, nhưng **sai nếu mô tả ZGC hiện tại**. Khi phân tích một log có các ký hiệu young/old hoặc minor/major trên JDK mới, không gọi đó là lỗi hoặc loại GC khác.

Đồng thời, **đừng tự gán ý nghĩa các cụm log** chỉ theo chữ “Major/Minor”; hãy xem tài liệu đúng JDK, sự kiện JFR và nhãn GC logs. G1 và ZGC dùng cách gọi pha và cách tính toán có thể khác nhau.

## 6. Chọn ZGC hay G1: dựa vào mục tiêu thật

| Tiêu chí | **ZGC** | **G1** |
| --- | --- | --- |
| Ưu tiên thiết kế | **Pause rất ngắn**, khả năng mở rộng với heap lớn. | Cân bằng throughput và pause predictability cho nhiều ứng dụng server. |
| Khối lượng công việc | Phần lớn GC work concurrent; cần CPU và headroom. | Concurrent marking kết hợp những pha STW evacuation/collection. |
| Độ trễ tail | Có thể giúp nếu **GC STW pause** thực sự là nguồn latency quan trọng. | Có thể đã đủ cho SLA nếu pauses hiện tại ngắn và ổn định. |
| Throughput | Concurrent barriers/GC workers tạo chi phí; không mặc định nhanh hơn. | Có thể đạt throughput tốt trong nhiều workload; phải benchmark. |
| Heap | Hoạt động trên heap rộng, thường quan trọng khi live set lớn và latency nghiêm. | Hiệu quả với nhiều kích thước heap, tùy cấu hình và pressure. |
| Tuning | Ưu tiên **`-Xmx`, headroom, CPU**; tránh tinh chỉnh cờ nội bộ quá sớm. | Có bộ heuristics/flags riêng; không copy flags giữa hai collector. |
| Dấu hiệu cần chuyển | GC pause là tác nhân đáng kể của p99/p99.9, với tài nguyên đủ để concurrent GC chạy. | Khi throughput/resource cost quan trọng hơn khoảng dừng rất nhỏ, hoặc đã đáp ứng SLA. |

Không cần bật ZGC cho mọi ứng dụng chỉ vì tên “low latency”. Với một batch job ưu tiên throughput hoặc container rất giới hạn CPU/memory, một collector khác có thể phù hợp hơn. Trước khi quyết định, đo **SLO thực tế** và đối chiếu p99, QPS, GC log, CPU, heap và RSS, không chỉ một dòng “Pause Mark ...”.

## 7. Heap headroom: điều kiện để GC concurrent theo kịp cấp phát

Điều quan trọng nhất khi tuning ZGC thường là chọn **heap tối đa `-Xmx`**.

ZGC cần đồng thời:

1. Giữ **live set** (object ứng dụng còn reachable).
2. Đáp ứng các allocation mới của application threads khi GC đang xử lý concurrent.
3. Có bộ nhớ/thời gian để di chuyển, thu hồi và quản lý objects mà không làm các threads chờ lâu.

Nếu live set đã gần `-Xmx` hoặc allocation rate quá cao so với tốc độ GC concurrent, bạn có thể gặp **allocation stalls** hoặc thậm chí `OutOfMemoryError`. ZGC không “biến RAM ít thành GC không dừng”.

### 7.1. Những knobs quan trọng

| Cờ/thiết lập | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `-XX:+UseZGC` | Chọn ZGC trên HotSpot hỗ trợ. | Không phải default ở mọi JVM. |
| `-Xmx<size>` | **Giới hạn heap cứng** do JVM dùng. | Cần headroom cho allocation rate + live set; không đặt quá sát RAM limit process/container. |
| `-Xms<size>` | Kích thước heap ban đầu/tối thiểu. | Đặt bằng `-Xmx` có thể giảm các thay đổi commit/uncommit, đổi lại footprint/startup. |
| `-Xlog:gc*` | Unified Logging cho GC và các tags liên quan. | Thêm logs có overhead/dung lượng; dùng file rotation và bảo vệ dữ liệu. |
| `-XX:SoftMaxHeapSize=<size>` | Soft target ZGC cố không vượt quá nếu có thể. | **Không phải hard cap**; được phép vượt đến `-Xmx` để tránh stall. **Cờ có từ JDK 13**, không phải cờ bắt buộc của JDK 11. |
| `-XX:-ZUncommit` | Tắt khả năng trả unused heap pages về OS. | **Uncommit feature thêm ở JDK 13**; có thể tăng footprint. |
| `-XX:ZUncommitDelay=<seconds>` | Delay trước khi unused pages đủ điều kiện uncommit. | Chỉ dùng nếu runtime hỗ trợ; không copy sang Java 11 ban đầu. |
| `-XX:ConcGCThreads=<n>` | Giới hạn/điều chỉnh số concurrent GC workers khi thực sự cần. | JVM thường có heuristics tốt; đặt quá thấp có thể dẫn đến GC không theo kịp, quá cao có thể tranh CPU. |
| `-XX:+AlwaysPreTouch` | Chủ động chạm vào heap pages khi startup. | Có thể ảnh hưởng lớn startup, RAM/commit; cần kiểm thử, không mặc định bật. |

**Đặc biệt theo Special Note:**

- Trên **JDK 11**, tập cờ được hỗ trợ khác các JDK hiện đại. Không trình bày `SoftMaxHeapSize`, `ZUncommitDelay` hay `ZGenerational` như tùy chọn chắc chắn có ở Java 11.
- Trên **JDK 24+**, `ZGenerational` không còn là một flag có ý nghĩa để chọn mode; không giữ các cấu hình đã obsolete.
- Không dùng các lời khuyên cũ về CMS hoặc các flag GC đã deprecated/removed làm hướng dẫn thiết lập ZGC hiện nay.

### 7.2. Native memory và memory limit của container

`-Xmx` giới hạn **Java heap**, không giới hạn tổng resident memory của process JVM. Ngoài heap còn có metaspace, thread stacks, code cache, direct buffers, native allocations, page tables, GC bookkeeping và thư viện native.

Nếu chạy trong container với memory limit, phải để dư dung lượng cho **non-heap/native memory**. Đặt `-Xmx` bằng đúng container memory limit dễ gây kill bởi hệ điều hành dù Java heap chưa vượt giới hạn.

**Virtual memory reserved ≠ committed memory ≠ RSS**. Một số kỹ thuật ZGC sử dụng virtual address mapping và metadata, nên đừng đọc một con số reserved address space rồi suy ra toàn bộ là RAM thực đang dùng. Dùng metrics hệ điều hành/container, `jcmd VM.native_memory` khi đã bật Native Memory Tracking và các công cụ phù hợp.

### 7.3. Có nên đặt `-Xms = -Xmx`?

Khi mục tiêu cực kỳ nhạy cảm latency và máy có đủ RAM, dùng heap cố định và có thể pre-touch giúp tránh một số chi phí commit/uncommit trong giờ cao điểm. Tuy nhiên:

- Tăng resident/committed footprint, ảnh hưởng startup.
- Không phải cấu hình mặc định tốt nhất cho mọi container.
- Với JDK hiện đại, đặt `-Xms = -Xmx` ngăn ZGC uncommit xuống dưới mức minimum heap đã đặt.
- Nên thử A/B, quan sát p99/p99.9, RSS, startup, OS memory pressure và chi phí hạ tầng.

Khi mục tiêu là tiết kiệm RAM lúc idle, cơ chế uncommit có giá trị, nhưng commit lại pages cũng có thể ảnh hưởng latency. Phải chọn theo workload/SLO, không có một bộ flag “tối ưu tuyệt đối”.

## 8. Chương trình Java 11 hoàn chỉnh: so sánh xác thực ZGC và G1

Để không “đoán” collector đang chạy, ví dụ dùng **ManagementFactory.getGarbageCollectorMXBeans()**. Chương trình tạo cùng một workload cấp phát dưới **ZGC** và **G1**, xác minh tên collector của JVM có chứa chuỗi được yêu cầu. Thời gian GC và allocation stalls được lấy từ **GC logs**, không in một con số cố định giả.

Tính chất bài thực hành:

- Có **2 luồng** cấp phát độc lập.
- Mỗi luồng chạy **60.000 vòng** và tạo mảng `byte[4096]`.
- Tổng số vòng `120.000`, tổng kích thước **payload được yêu cầu** `491.520.000 byte`.
- Mỗi luồng giữ lại **128 mảng** cuối trong một ring; tổng `256` mảng và payload giữ lại `1.048.576 byte`.
- Từng mảng được ghi một byte, lưu vào ring rồi vòng lặp tiếp tục; nhiều mảng trước đó trở nên có thể thu gom.
- Giá trị payload là **kích thước mảng do code yêu cầu**, **không** gồm headers, alignment, thread allocations và các object của runtime.
- Code không tự gọi `System.gc()`; GC được kích hoạt bởi allocation pressure và ergonomics của JVM.
- Mỗi lần chạy trong một JVM/process riêng, bảo đảm flags được áp dụng ở startup thay vì đổi collector ở runtime.

Ví dụ không được thiết kế như một **benchmark kết luận collector nào nhanh hơn**. Nó là **bài kiểm thử cấu hình collector + tạo tải + đọc log**; muốn so sánh hiệu năng cần JMH/benchmark phù hợp và đo lặp với workload thực.

### 8.1. Mã nguồn `ZgcGcProbe.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public final class ZgcGcProbe {
    private static final int WORKERS = 2;
    private static final int ARRAYS_PER_WORKER = 60000;
    private static final int PAYLOAD_BYTES = 4096;
    private static final int RETAIN_PER_WORKER = 128;
    private static volatile byte[][][] retained;

    private static void allocate(byte[][][] result, int index) {
        byte[][] ring = new byte[RETAIN_PER_WORKER][];
        for (int i = 0; i < ARRAYS_PER_WORKER; i++) {
            byte[] data = new byte[PAYLOAD_BYTES];
            data[0] = (byte) (index + i);
            ring[i % RETAIN_PER_WORKER] = data;
        }
        result[index] = ring;
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length != 1
                || (!"ZGC".equals(args[0]) && !"G1".equals(args[0]))) {
            throw new IllegalArgumentException("Use: ZGC or G1");
        }

        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();
        boolean matched = beans.stream()
                .anyMatch(b -> b.getName().contains(args[0]));
        if (!matched) {
            throw new IllegalStateException(
                    "Requested collector not active: " + args[0]);
        }

        byte[][][] local = new byte[WORKERS][][];
        Thread[] threads = new Thread[WORKERS];
        for (int i = 0; i < WORKERS; i++) {
            final int index = i;
            threads[i] = new Thread(() -> allocate(local, index),
                    "allocator-" + i);
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }
        retained = local;

        int keptArrays = 0;
        long keptPayload = 0;
        for (byte[][] ring : retained) {
            for (byte[] array : ring) {
                if (array != null) {
                    keptArrays++;
                    keptPayload += array.length;
                }
            }
        }

        System.out.println("collector-verified=true");
        System.out.println("workers=" + WORKERS);
        System.out.println("allocation-loops=" + (WORKERS * ARRAYS_PER_WORKER));
        System.out.println("requested-payload-bytes=" +
                ((long) WORKERS * ARRAYS_PER_WORKER * PAYLOAD_BYTES));
        System.out.println("retained-arrays=" + keptArrays);
        System.out.println("retained-payload-bytes=" + keptPayload);
    }
}
```

**Về tên MXBeans:** chúng thay đổi theo collector và JDK; chương trình chỉ kiểm tra phần chuỗi `"ZGC"` hoặc `"G1"` có trong tên bean trên HotSpot. Nó không hard-code `ZGC Cycles`, `ZGC Young Generation` hay tên event của một JDK cụ thể. Nếu provider khác không phơi bày tên phù hợp, chương trình sẽ từ chối chứ không giả mạo kết quả.

### 8.2. Lệnh biên dịch và chạy với Generational ZGC hiện đại

Trên một HotSpot **JDK 24 trở lên có hỗ trợ ZGC**:

```bash
javac -encoding UTF-8 --release 11 ZgcGcProbe.java

java -XX:+UseZGC -Xms128m -Xmx256m \
  -Xlog:gc*:file=zgc.log:uptime,level,tags \
  ZgcGcProbe ZGC
```

Cờ `--release 11` xác minh **mã nguồn và public API Java tương thích Java 11**. Nó **không** biến JVM đang chạy thành JDK 11 và **không** kiểm chứng đặc tính GC của ZGC bản JDK 11. Kết quả thử thực tế ở đây dùng **Azul/OpenJDK 24** với **Generational ZGC**, không phải JDK 11 experimental ZGC.

**Stdout chính xác đã kiểm chứng cho lần chạy ZGC:**

```text
collector-verified=true
workers=2
allocation-loops=120000
requested-payload-bytes=491520000
retained-arrays=256
retained-payload-bytes=1048576
```

Nếu chạy trên **JDK 11/Linux/x64 có ZGC**, lệnh tương ứng cần cờ experimental từ mục 2.1. **Không áp dụng lệnh JDK 24+ nguyên xi như bằng chứng hỗ trợ ZGC trên mọi hệ điều hành của JDK 11.**

### 8.3. Chạy cùng workload bằng G1 để có dữ liệu đối chứng

Trên cùng JDK có G1:

```bash
java -XX:+UseG1GC -Xms128m -Xmx256m \
  -Xlog:gc*:file=g1.log:uptime,level,tags \
  ZgcGcProbe G1
```

**Stdout chính xác đã kiểm chứng cho lần chạy G1** cũng là:

```text
collector-verified=true
workers=2
allocation-loops=120000
requested-payload-bytes=491520000
retained-arrays=256
retained-payload-bytes=1048576
```

Hai stdout giống nhau vì đó là **khối lượng công việc và kiểm tra cấu hình collector**, không phải số đo hiệu năng. Các GC cycles, thời gian pause và throughput nằm trong **`zgc.log`/`g1.log`** và sẽ khác khi chạy lại.

### 8.4. Một đoạn GC log ZGC thực tế đã quan sát trên JDK 24

Các dòng sau là **trích đoạn của một lần chạy thật**; chúng **không phải** expected output bất biến:

```text
[0.012s][info][gc     ] Using The Z Garbage Collector
[0.098s][info][gc,phases   ] GC(0) Y: Pause Mark Start (Major) 0.013ms
[0.099s][info][gc,phases   ] GC(0) Y: Concurrent Mark 1.335ms
[0.099s][info][gc,phases   ] GC(0) Y: Pause Mark End 0.008ms
[0.103s][info][gc,phases   ] GC(0) Y: Pause Relocate Start 0.012ms
[0.103s][info][gc,alloc    ] GC(0) Y: Allocation Stalls:          0                0                0                0
[0.104s][info][gc,phases   ] GC(0) O: Concurrent Mark 0.344ms
[0.104s][info][gc,phases   ] GC(0) O: Pause Mark End 0.009ms
[0.147s][info][gc,phases   ] GC(0) O: Pause Relocate Start 0.173ms
```

Trong lần chạy đó, các pha ghi `Pause ...` là **GC synchronization pauses**, còn `Concurrent Mark` là **công việc concurrent**, **không phải** thời gian Java threads bị dừng toàn bộ. Tên `Y` và `O` là một dấu hiệu ở log của **Generational ZGC JDK 24**.

Không thể từ một lần chạy thấy pause 0.008–0.173 ms mà kết luận “ZGC đảm bảo 0.173 ms trên production”, “request p99 dưới 1ms” hoặc “không có performance cost”. Muốn kiểm thử thiết kế với heap lớn/CPU pressure phải chạy tải thực tế trong thời gian đủ dài.

### 8.5. Một đoạn GC log G1 cùng môi trường

```text
[0.009s][info][gc     ] Using G1
[0.057s][info][gc,start    ] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.058s][info][gc          ] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->2M(130M) 1.336ms
[0.062s][info][gc,start    ] GC(1) Pause Young (Normal) (G1 Evacuation Pause)
[0.062s][info][gc          ] GC(1) Pause Young (Normal) (G1 Evacuation Pause) 60M->2M(130M) 0.730ms
```

Ở đây, `Pause Young (G1 Evacuation Pause)` là **G1 STW pause**, còn ZGC sử dụng các pha và logger khác. Không nên cộng tất cả các dòng có chữ `GC(...)` vào một “tổng pause”; một dòng có thể là start marker, heap stats, concurrent step hoặc event khác.

**Đây không phải so sánh công bằng để chọn GC**: workload ngắn, startup/JIT chưa ổn định, heap nhỏ, CPU/memory không được kiểm soát và các thuật toán được đo trong những giai đoạn khác nhau. So sánh thực sự cần nhiều run, warmup, phân phối p99/p99.9 và cùng workload/throughput.

## 9. Đọc GC logs mà không nhầm pha và thời gian

Cấu hình `-Xlog:gc*` là **Unified Logging** trên HotSpot, có từ trước Java 11. Các log message thường gồm:

```text
[uptime][level][tags] GC(id) [generation/phase] nội dung duration
```

Các nhãn cần nhìn:

- **`Using The Z Garbage Collector` hoặc `Using ZGC`**: giúp xác minh GC đã chọn, tùy bản JVM.
- **`Pause ...`**: pha có điểm STW; lấy số duration sau khi hiểu đúng cấu trúc message.
- **`Concurrent ...`**: công việc GC concurrent với application threads, không cộng như pause.
- **`Allocation Stall(s)`**: dấu hiệu threads không được cấp phát ngay vì memory/collector pressure; cần điều tra riêng vì có thể ảnh hưởng tail latency.
- **Heap before/after**: kích thước đang sử dụng trong từng sự kiện/pha, không phải tổng physical RSS.
- **`GC(id)`**: tham chiếu để nhóm các pha thuộc cùng chu kỳ, nhưng không giả định một id luôn tương đương một lần “full STW GC”.

### 9.1. Dùng log file rotation trong dịch vụ chạy lâu

Với HotSpot hỗ trợ Unified Logging, một cách đặt dung lượng file có giới hạn:

```bash
java -XX:+UseZGC -Xmx2g \
  -Xlog:gc*:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M \
  MyService
```

**`MyService` là tên lớp minh họa**, cần thay bằng entrypoint và classpath/module path thực tế. `%p` trong filename được HotSpot thay bằng PID. Cần kiểm tra path, quyền ghi và retention. Điều chỉnh tag/level theo mục tiêu: mở `trace` rộng trên production lâu dài có thể tạo file lớn và overhead, không phải cài đặt mặc định tốt.

Nếu cần điều tra thời gian JVM dừng do safepoint **không chỉ vì GC**, dùng thêm `-Xlog:safepoint` hoặc các tags/levels được JVM target hỗ trợ. **Đừng quy mọi safepoint pause cho ZGC**.

### 9.2. Đọc một file nhiều chu kỳ

Quy trình:

1. Xác nhận **JDK/vendor/version** và GC đang chạy.
2. Lấy **khoảng thời gian** và lưu time zone/correlation với request traces.
3. Lọc những dòng có `Pause` và kiểm tra **loại pha**, **duration**, **GC id**.
4. Tách **concurrent durations**, **allocation stalls**, **memory usage** và **GC CPU usage**.
5. Tính phân vị của **GC STW pauses** riêng biệt, không đánh tráo với request latency p99.
6. Dùng biểu đồ theo thời gian để kiểm tra liên hệ với **QPS, error rate, timeouts và queue depth**.
7. Kiểm tra có heap/CPU pressure hoặc container throttling cùng thời điểm hay không.
8. Không kết luận từ một vài dòng log hoặc một benchmark quá ngắn.

Có thể dùng **JDK Flight Recorder (JFR)**/JDK Mission Control để so sánh GC events với các sự kiện ứng dụng và thread states. Tên các event ZGC cụ thể có thể khác giữa JDK 11 và JDK 24+, nên xem **event metadata trong recording đang phân tích** thay vì hard-code một schema “dùng mọi phiên bản”.

## 10. Phân biệt GC pause thấp với allocation stall và OOM

Đây là nguyên nhân thường khiến chuyển từ G1 sang ZGC nhưng hệ thống **không** đạt latency kỳ vọng.

### Kịch bản A — Có đủ headroom

```text
Java threads cấp phát
       |
       |       ZGC concurrent GC chạy kịp
       |                 |
       v                 v
  [alloc] [alloc] [alloc] [alloc] ...
       |
       v
Không phải đợi GC thu hồi toàn heap trong một STW pause dài
```

Các chu kỳ GC có thể hoàn thành trong khi ứng dụng tiếp tục chạy; những điểm STW ngắn tạo ít gián đoạn. Tuy nhiên GC threads vẫn tiêu thụ CPU và cần RAM để hoàn thành.

### Kịch bản B — Không đủ headroom hoặc CPU

```text
Allocation rate tăng mạnh
            |
            v
Live set + new allocations gần Xmx
            |
            v
Concurrent GC không kịp reclaim/relocate
            |
            +--> application threads chờ allocation
            |
            +--> request latency tăng
            |
            +--> có thể OutOfMemoryError nếu không đủ memory
```

**GC pause log rất đẹp nhưng request p99 vẫn tệ** có thể là dấu hiệu ứng dụng bị allocation stalls, CPU contention hoặc vấn đề I/O khác. Kiểm tra ZGC allocation stall messages, heap/free headroom, OS memory pressure và metrics ứng dụng.

### Kịch bản C — CPU cạn kiệt

Concurrent GC không “miễn phí”. Nếu container giới hạn CPU quá chặt, threads ứng dụng và threads GC cạnh tranh phần CPU ít ỏi. Có thể thấy throughput giảm, GC cycle kéo dài, allocation rate vượt khả năng thu gom hoặc queue/request timeout.

Giải pháp có thể là **tăng CPU headroom**, giảm allocation rate, tăng heap, giảm object churn, cân nhắc workload scheduling hoặc chọn collector khác sau khi benchmark. Không tự ý tăng `ConcGCThreads` thật lớn với giả định càng nhiều GC threads thì pause càng ngắn.

## 11. Thiết kế benchmark đúng cho mục tiêu latency

Muốn quyết định có nên dùng ZGC trong production, hãy đo cả **bốn nhóm**:

| Nhóm | Thước đo gợi ý | Vì sao quan trọng |
| --- | --- | --- |
| **End-to-end latency** | p50/p95/p99/p99.9, max, timeouts theo request type. | Đây mới là SLO mà người dùng cảm nhận. |
| **Throughput** | QPS, requests/s, jobs/s, CPU/core-time. | ZGC có thể đổi throughput lấy latency; không thể chỉ chọn pause thấp. |
| **GC và memory** | STW pause phân phối, concurrent cycles, allocation stalls, live set, allocation rate, RSS. | Chứng minh sự khác biệt đến từ collector hay memory pressure. |
| **Tài nguyên** | CPU throttling, free RAM, container limit, OS page faults, native/direct memory. | GC không giải quyết giới hạn CPU/RAM bên ngoài heap. |

### Quy trình A/B công bằng

1. Chọn **một JDK/vendor/build** được sản phẩm hỗ trợ, cố định OS, CPU limit, container settings.
2. Dùng **cùng ứng dụng và cùng dữ liệu**. Giữ request mix, arrival rate, concurrency, cache warmup và backpressure tương đương.
3. Khởi động **hai process tách biệt**, một G1 và một ZGC, cùng `-Xms/-Xmx` ban đầu (hoặc có thử nghiệm heap sizing riêng được ghi rõ).
4. Warm up JIT/caches, chạy đủ lâu qua nhiều GC cycles, không lấy một lần benchmark ngắn làm kết luận.
5. Ghi **latency distribution và error rate**, không chỉ average hoặc “max GC pause”.
6. Lấy GC logs/JFR và log ứng dụng với timestamp correlation, nhìn cả allocation stalls và GC CPU.
7. Lặp trên nhiều trial, xem variance, confidence interval hoặc phân phối; tránh công bố chính xác quá mức.
8. Kiểm tra **headroom và container memory budget**; nếu ZGC dùng thêm CPU/RAM cần đưa vào quyết định.
9. Thử cả tải bình thường, burst traffic, đỉnh data size, GC pressure, cold/warm cache và graceful shutdown.
10. Chọn theo SLA/SLO thực tế, chi phí tài nguyên, khả năng vận hành và giới hạn platform.

Ví dụ “JDK24 ZGC có một Pause Mark Start 0.013ms; JDK24 G1 có một Pause Young 1.336ms” **không đủ bằng chứng** để kết luận ZGC mang lại end-to-end p99 tốt hơn gấp 100 lần. So sánh ở mục 8 chỉ là test **đúng cờ + tạo GC + đọc log**.

## 12. Giám sát collector qua Java Management API

Ngoài GC logging, Java có `java.lang.management.GarbageCollectorMXBean` và `ManagementFactory`:

```java
for (GarbageCollectorMXBean bean :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    System.out.println(bean.getName());
}
```

Đây là snippet cần import `java.lang.management.*` và đặt trong method Java. Tên bean cụ thể thay đổi với collector/JDK, ví dụ G1 và ZGC có các bean khác nhau; **không hard-code tên bean generational từ JDK 24** để áp dụng cho JDK 11.

Các phương thức như `getCollectionCount()` và `getCollectionTime()` có semantics và mức hỗ trợ tùy collector/provider; có thể trả **-1** nếu không hỗ trợ. Không suy ra **max STW pause**, “mọi request latency” hay tổng concurrent GC CPU chính xác chỉ từ một số MXBean.

Trong mục 8, chương trình **chỉ** dùng tên beans để **xác minh collector**; số liệu performance cần đọc từ GC logs, JFR, OS và application metrics.

### Dùng `jcmd` khi được phép

Nếu cần kiểm tra một JVM đang chạy, có thể dùng:

```bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

`<PID>` là **ký hiệu chỗ cần thay bằng PID hợp lệ**, không phải đối số literal có dấu ngoặc. Chỉ điều tra JVM bạn được phép quản lý, vì các lệnh chẩn đoán có thể lộ metadata hoặc ảnh hưởng vận hành. Các lệnh/đầu ra tùy HotSpot build và trạng thái attach; đây là **hướng dẫn vận hành**, không phải một cách đảm bảo API Java chạy được trên mọi JVM/vendor.

## 13. Khi nào cần đổi cấu hình ZGC?

| Hiện tượng | Kiểm tra trước | Hành động có thể thử |
| --- | --- | --- |
| GC pauses dài bất thường | Đúng ZGC? JDK/version nào? Có STW hay safepoint khác? | Đọc tag/duration, JFR/safepoint; cập nhật runtime nếu cần và được hỗ trợ. |
| Allocation stalls tăng | Live set, free headroom, `-Xmx`, allocation rate. | Tăng headroom hoặc giảm allocation pressure; đo lại. |
| GC concurrent tốn CPU | Tổng CPU, CPU quota, GC threads và workload. | Kiểm soát workload/CPU, xem heuristics, không ép `ConcGCThreads` mù quáng. |
| Container bị OOMKill | RSS và non-heap/direct/native memory, cgroup limit. | Chừa memory budget ngoài `-Xmx`, điều tra native leaks. |
| Footprint lớn lúc idle | Committed heap, uncommit settings, `-Xms`. | Trên JDK hỗ trợ, cân nhắc ZUncommit/SoftMax; đánh giá cost latency. |
| Startup quá chậm | `AlwaysPreTouch`, heap initial, disk/container startup. | Thử giảm pre-touch/`-Xms` theo mục tiêu; đo lại. |
| p99 cao dù GC pauses rất thấp | Queue, lock, DB/network, CPU scheduling, allocation stalls. | Trace request, không chỉ chỉnh GC. |
| Throughput giảm sau đổi từ G1 | CPU overhead/concurrent work, barrier cost. | Benchmark A/B cùng dữ liệu; có thể chọn G1 nếu SLA đã đạt. |
| Tài liệu cũ yêu cầu `-XX:+ZGenerational` | JDK hiện tại? | Trên JDK 24+, bỏ cờ đã loại bỏ; chỉ dùng `-XX:+UseZGC`. |
| Tài liệu đòi `UnlockExperimentalVMOptions` | Có phải JDK 11–14? | Chỉ cần cho các bản ZGC còn experimental, không áp dụng chung với JDK 15+. |
| ZGC không khởi động trên Java 11/Windows | Giới hạn nền tảng của bản thử nghiệm ban đầu. | Không coi là lỗi code; dùng JDK/platform được hỗ trợ hoặc GC khác. |

**Nguyên tắc tuning:** thay **một biến tại một thời điểm**, ghi JDK version, flags, memory/CPU limits, QPS, p99/p99.9 và GC logs trước–sau. Tránh “mượn” hàng chục `-XX` flags từ một blog viết cho JDK 11 rồi áp lên ZGC JDK 25.

## 14. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “ZGC không bao giờ dừng ứng dụng.” | ZGC vẫn có những **STW synchronization pauses**, được thiết kế rất ngắn. |
| “ZGC đảm bảo mọi pause dưới 10 ms.” | Đó là **mục tiêu thiết kế** của JEP 333, không phải hard real-time SLA. |
| “Request p99 = GC pause p99.” | End-to-end latency còn gồm code, CPU, lock, network, DB, queue, allocation stalls. |
| “GC cycle 20 ms nghĩa là ứng dụng bị dừng 20 ms.” | Concurrent GC cycle có thể kéo dài khi app vẫn chạy. |
| “Tăng heap thì ZGC pause sẽ tăng tuyến tính.” | ZGC được thiết kế để phần lớn pause không phụ thuộc trực tiếp heap/live set; vẫn chịu resource pressure. |
| “ZGC không cần heap headroom.” | Concurrent GC phải theo kịp allocation; thiếu headroom gây stall/OOM. |
| “ZGC luôn dùng ít RAM hơn.” | Không: cần headroom và native/GC memory; uncommit/committed/RSS còn tùy cấu hình. |
| “ZGC luôn có throughput cao hơn G1.” | Không thể mặc định; concurrent/barrier work tiêu thụ CPU, cần benchmark. |
| “Trên Java 11 chỉ cần `-XX:+UseZGC`.” | Bản JDK 11 experimental cần `-XX:+UnlockExperimentalVMOptions` **trước** flag ZGC và hỗ trợ platform. |
| “Java 11 ZGC chạy được mọi hệ điều hành.” | Bản thử nghiệm ban đầu giới hạn **Linux/x64**; hỗ trợ hiện đại rộng hơn. |
| “ZGC hiện nay không phân thế hệ.” | Sai từ JDK 24 trở đi: **chỉ còn Generational ZGC**. |
| “Dùng `-XX:+ZGenerational` là cấu hình chuẩn mọi JDK mới.” | Đó là tùy chọn giai đoạn JDK 21–23; **đã bị loại bỏ từ JDK 24**. |
| “`SoftMaxHeapSize` là giới hạn heap cứng.” | Không: soft target, có thể vượt tới `-Xmx`. |
| “`SoftMaxHeapSize` có sẵn trong Java 11.” | Không: được thêm từ **JDK 13**. |
| “`-Xmx` là tổng RAM JVM tiêu thụ.” | Không: còn metaspace, native, stacks, direct buffers, GC data structures. |
| “Có log GC nhanh thì không cần tracing.” | Cần request latency, stalls và các tài nguyên khác để xác định nguyên nhân. |
| “Có thể dựa vào một log mẫu để chứng minh SLA.” | Không: phải đo trên nhiều chu kỳ và workload thực tế, phân phối latency. |
| “G1 và ZGC log có cùng event names/semantics.” | Không: phải đọc đúng version/collector. |
| “Một dòng Concurrent Mark là STW pause.” | Không: concurrent work chạy khi application threads tiếp tục. |
| “GC pause thấp chứng minh app không có memory leak.” | Không: retained heap leak vẫn có thể xảy ra và cuối cùng gây OOM. |
| “Bật pre-touch và fixed heap luôn tiết kiệm RAM.” | Có thể tăng footprint/startup; chọn theo SLA và budget. |

## 15. Checklist áp dụng ZGC với mục tiêu dừng ngắn

1. Xác định **SLO end-to-end**: p99/p99.9, timeout/error rate, QPS; không dùng GC pause làm SLO duy nhất.
2. Biết rõ **JDK/vendor/build và OS**; JDK 11 ZGC experimental Linux/x64 khác ZGC hiện đại.
3. Nếu dùng JDK 11, kiểm tra đúng support matrix và bật `-XX:+UnlockExperimentalVMOptions -XX:+UseZGC`; đây là kiến thức theo phiên bản, không áp dụng mặc định cho JDK mới.
4. Nếu dùng JDK 24+, chọn `-XX:+UseZGC`; ZGC **chỉ generational**, không dùng `-XX:+ZGenerational` như một chế độ có thể bật thêm.
5. Xác minh collector bằng GC startup log và/hoặc `GarbageCollectorMXBeans`, không đoán theo Java version.
6. Chọn `-Xmx` đủ cho **live set + allocation headroom + concurrent GC**; tính cả memory ngoài heap và container limit.
7. Giữ CPU headroom cho GC concurrent workers; kiểm tra CPU throttling.
8. Ghi GC logs bằng `-Xlog:gc*` hoặc cấu hình cụ thể, có rotation/retention phù hợp.
9. **Tách số liệu**: STW pauses, concurrent cycles, allocation stalls, request latency, throughput, heap/RSS và GC CPU.
10. Dùng JFR/tracing/metrics ứng dụng để tương quan theo thời gian, không quy mọi spike cho ZGC.
11. So sánh với G1 trên **cùng app/workload/JDK/heap/resource limits** và chạy nhiều lượt; không suy ra benchmark từ demo ngắn.
12. Chỉ dùng `SoftMaxHeapSize`/`ZUncommit` trên phiên bản hỗ trợ và khi biết đánh đổi footprint–latency.
13. Đánh giá `-Xms = -Xmx`/pre-touch dựa trên RAM và startup budget, không bật mù quáng.
14. Nếu thấy allocation stalls/OOM, điều tra headroom và allocation pressure; GC pause thấp không loại trừ stall.
15. Giữ ứng dụng cập nhật trên bản JDK được hỗ trợ, nhưng không copy flags cũ/đã obsolete sang collector hiện hành.
16. Khi báo cáo, nêu **collector, version, flags, heap, CPU/memory limit, workload, time window, percentile latency và log evidence**.

### Tài liệu chính thức và hiện hành

- [OpenJDK JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector (Experimental, JDK 11)](https://openjdk.org/jeps/333)
- [Oracle JDK 11 Release Notes — JEP 333, mục tiêu dưới 10 ms và giới hạn Linux/x64 của bản experimental](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html)
- [Oracle Java SE 11 — Garbage Collection Tuning: The Z Garbage Collector](https://docs.oracle.com/en/java/javase/11/gctuning/z-garbage-collector4.html)
- [Oracle Java SE 11 — `java` command, `-XX:+UseZGC` và Unified Logging `-Xlog`](https://docs.oracle.com/en/java/javase/11/tools/java.html)
- [OpenJDK JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector (Production, JDK 15)](https://openjdk.org/jeps/377)
- [OpenJDK JEP 439 — Generational ZGC (JDK 21)](https://openjdk.org/jeps/439)
- [OpenJDK JEP 474 — ZGC: Generational Mode by Default (JDK 23)](https://openjdk.org/jeps/474)
- [OpenJDK JEP 490 — ZGC: Remove the Non-Generational Mode (JDK 24)](https://openjdk.org/jeps/490)
- [Oracle Java SE 24 — The Z Garbage Collector (Generational ZGC, heap sizing và uncommit)](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html)
- [Oracle JDK 13 Release Notes — ZGC uncommit và `SoftMaxHeapSize` từ JDK 13](https://www.oracle.com/java/technologies/javase/13all-relnotes.html)
- [Dev.java — Deep-dive of ZGC architecture, pauses và concurrent phases](https://dev.java/learn/jvm/tool/garbage-collection/zgc-deepdive/)
