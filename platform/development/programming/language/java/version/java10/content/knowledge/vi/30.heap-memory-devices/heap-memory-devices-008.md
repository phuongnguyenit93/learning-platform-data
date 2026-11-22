# Giới hạn phụ thuộc phần cứng, hệ điều hành và bản dựng JVM khi đặt Java heap trên thiết bị bộ nhớ (Java 10+)

## 1. Bài học này giải quyết điều gì?

Java 10 giới thiệu **JEP 316 — Heap Allocation on Alternative Memory Devices**: HotSpot JVM có thể được cấu hình để đặt **Java object heap** trên một thiết bị bộ nhớ thay thế, ví dụ **NV-DIMM / persistent memory (PMEM)**, thông qua một vùng được hệ điều hành ánh xạ vào không gian địa chỉ của process. Tùy chọn liên quan là:

~~~bash
-XX:AllocateHeapAt=/duong-dan/toi-filesystem
~~~

Ý tưởng rất hấp dẫn: ứng dụng vẫn tạo object bằng `new` và GC vẫn quản lý chúng; người phát triển không phải viết lại toàn bộ business code chỉ vì heap có backing khác DRAM. Nhưng điều đó **không có nghĩa bất kỳ máy tính, hệ điều hành hoặc bản JVM nào cũng đặt được heap lên thiết bị tùy ý**.

**Đề bài trọng tâm:** Giới hạn thực sự phụ thuộc vào **phần cứng**, **hệ điều hành/filesystem** và **bản dựng (build) JVM**. Muốn quyết định có triển khai được, phải kiểm tra **đồng thời cả ba**, thêm dung lượng, quyền truy cập, đặc tính hiệu năng và tính an toàn.

### Kết quả cần nắm

Sau bài học, bạn có thể:
1. Giải thích vai trò của `-XX:AllocateHeapAt` và giới hạn phạm vi **Java heap**.
2. Biết vì sao phải có **memory device với semantics phù hợp**, bao gồm byte-addressability và atomic operations theo yêu cầu nền tảng.
3. Phân biệt **DAX/file-backed mapping** với việc đơn giản lưu một tệp trên SSD, HDD hoặc network filesystem.
4. Hiểu sự phụ thuộc vào **kernel, filesystem, mount options, quyền truy cập, quota, page size và memory mappings**.
5. Kiểm tra **JDK distribution, version, OS/CPU architecture, HotSpot variant và GC** thay vì suy đoán từ chữ “Java 10+”.
6. Hiểu `-Xmx` và `-Xms` vẫn có vai trò; **Metaspace, code cache, thread stacks và native allocations** không tự chuyển sang thiết bị.
7. Thiết kế bước **preflight, staging, quan sát mapping, benchmark, fallback và rollback**.
8. Phân biệt **persistent hardware** với việc **lưu bền Java objects sau JVM restart** — hai chuyện hoàn toàn khác nhau.
9. Thực hành một chương trình **Java 17+ hoàn chỉnh** mô phỏng kiểm tra khả năng tương thích với stdout xác định; có chế độ đọc thông tin JVM hiện tại.
10. Tránh các cách làm lỗi thời, ví dụ giả định mọi hệ thống có PMEM hoặc khuyên dùng mặc định `AllocateHeapAt` mà chưa kiểm tra môi trường.

**Ghi chú tính hiện hành:** Oracle vẫn mô tả `-XX:AllocateHeapAt` trong tài liệu **JDK 25**. Việc flag còn được tài liệu hóa **không bảo đảm nó khả dụng hoặc có tác dụng trên tất cả các build/OS/GC combination**. Những phần mang tính lịch sử được nhận diện rõ; hướng dẫn thao tác luôn yêu cầu kiểm tra runtime thật.

## 2. Java heap trên bộ nhớ thay thế là gì?

Trong một cấu hình JVM thông thường, **Java object heap** được ánh xạ vào không gian địa chỉ ảo của process và backing bằng các trang bộ nhớ do OS quản lý. Với tính năng **AllocateHeapAt**, HotSpot có thể dùng **memory-mapped file** tại một filesystem do người vận hành chỉ định làm backing cho object heap.

~~~text
                 Java application
             new User(), new byte[]...
                         │
                         ▼
                 GC-managed heap
                         │
                    JVM mapping
                         │
           ┌─────────────┴───────────────┐
           │                             │
    Heap thường                  Heap theo AllocateHeapAt
    backing theo OS             backing qua file mapping
           │                             │
      RAM thông thường       Filesystem/device đặc biệt
                                         │
                             PMEM / byte-addressable
                             memory khi được hỗ trợ
~~~

Khả năng map thành công một file **không tự chứng minh** file ấy thật sự được đặt trên thiết bị memory-class thích hợp. Một filesystem thông thường trên SSD cũng có thể cho phép file mapping, nhưng cơ chế truy cập có thể qua **page cache và I/O storage**; nó không giống **direct mapping vào persistent memory qua DAX**.

### Phạm vi thay đổi

Theo tài liệu Oracle JDK hiện đại, `AllocateHeapAt` nhắm tới **Java object heap**. Những vùng khác, ví dụ:
- **Metaspace/class metadata**;
- **Code heap/JIT code cache**;
- **Thread stacks**;
- Các cấu trúc native khác của JVM;

**vẫn cần bộ nhớ theo cơ chế thông thường**, không được cam kết chuyển hết sang thiết bị mới.

**Đừng hiểu “heap trên PMEM” là “mọi byte mà JVM dùng đều trên PMEM”.** Khi lập capacity budget phải tính riêng phần còn ở DRAM và các giới hạn process/container.

## 3. Giới hạn lớp 1: phần cứng phải có semantics phù hợp

JEP 316 hướng tới thiết bị bộ nhớ thay thế có **semantics gần giống DRAM**, bao gồm ngữ nghĩa của **atomic operations** cần thiết cho JVM. Điều này quan trọng vì HotSpot/JIT/GC thực hiện nhiều thao tác trên Java heap với giả định về memory ordering, đồng bộ và truy cập trực tiếp.

| Thuộc tính phần cứng | Tại sao quan trọng? | Câu cần xác minh |
| --- | --- | --- |
| **Byte-addressability** | Heap có truy cập theo địa chỉ bộ nhớ, không chỉ qua block I/O | Thiết bị được OS expose như memory-addressable không? |
| **CPU/MMU mapping** | CPU phải truy cập vùng ánh xạ như memory | Kiến trúc và device mode có hỗ trợ không? |
| **Atomic operations semantics** | Các phép đồng bộ/volatile/CAS của JVM phải có hành vi đúng | Platform đáp ứng yêu cầu memory semantics không? |
| **Dung lượng khả dụng** | Heap có thể lớn; backing phải đủ chỗ theo phương thức cấp phát | Device/namespace/quota đủ cho heap budget không? |
| **Latency và bandwidth** | Memory khác DRAM có thể chậm hơn | Với workload heap-intensive, pause/throughput thay đổi thế nào? |
| **NUMA locality** | CPU và thiết bị có thể ở các NUMA nodes khác nhau | Có truy cập remote gây overhead không? |
| **Độ tin cậy thiết bị** | Lỗi media/I/O có thể ảnh hưởng mapping | Có giám sát health, error reporting và kế hoạch phục hồi không? |

### 3.1. NV-DIMM/PMEM không đồng nghĩa mọi SSD

Các ví dụ lịch sử của JEP 316 thường nói tới **NV-DIMM / persistent memory** được ánh xạ vào không gian địa chỉ để CPU đọc/ghi như bộ nhớ. **SSD NVMe thông thường** không tự biến thành byte-addressable main memory chỉ vì nó được gắn với filesystem hoặc `mmap`.

Phân biệt:
- **Memory-class device:** có thể có cơ chế truy cập trực tiếp qua address space, với OS/CPU hỗ trợ.
- **Block storage:** đọc/ghi theo cơ chế storage; file mapping có thể dựa vào page cache và page faults.
- **RAM-backed tmpfs:** tệp backing thường vẫn lấy từ RAM/swap của host, **không chứng minh đã dùng một thiết bị non-DRAM**.

**Cảnh báo diễn giải:** DAX là một cơ chế liên quan filesystem/kernel; **không thể suy ra toàn bộ hệ thống đủ điều kiện chỉ vì thiết bị quảng cáo “persistent” hoặc “NVMe”**.

### 3.2. Atomic semantics quan trọng hơn tên thương mại

Java programs dùng:
- `synchronized`;
- `volatile`;
- `AtomicInteger` và những atomic classes;
- Các cơ chế của JVM/GC/JIT dựa trên load/store và memory ordering.

Chúng không được mất tính đúng đắn chỉ vì backing heap thay đổi. Bởi vậy, không phải mọi loại thiết bị “đọc ghi nhanh” đều là ứng viên hợp lệ.

**Không thử chạy production trên phần cứng không có hợp đồng semantics phù hợp.** Một test `new Object()` chạy được không đủ chứng minh chương trình concurrent vẫn đúng trong mọi trường hợp.

### 3.3. Thời gian truy cập và hiệu năng

Ngay cả khi đúng semantics, thiết bị có thể có:
- Read latency cao hơn DRAM;
- Write latency/bandwidth khác nhau;
- NUMA penalties;
- Giá trị tối ưu khác nhau cho workload read-heavy, allocation-heavy và GC-intensive.

Vì vậy **không có lời hứa tăng tốc chung**. Đặt heap trên thiết bị khác có thể giúp tăng capacity hoặc phân tầng RAM, nhưng cũng có thể làm throughput, GC pause và p99 latency xấu đi.

## 4. Giới hạn lớp 2: hệ điều hành và filesystem phải thực sự hỗ trợ

HotSpot cần cơ chế OS để ánh xạ file-backed memory vào không gian địa chỉ JVM. Đối với loại PMEM mà JEP 316 nhắm tới, **filesystem DAX** là một hướng triển khai quan trọng trên Linux.

### 4.1. DAX là gì?

**Direct Access (DAX)** trên Linux cho phép những filesystem và thiết bị phù hợp cung cấp **file mappings trực tiếp tới storage/memory** thay vì đi qua page cache như cách dùng file thông thường. Điều này có ý nghĩa với thiết bị memory-like: tránh việc copy dư thừa qua page cache.

**Các lớp hỗ trợ phải khớp**:

~~~text
PMEM hardware / namespace
            │
    Kernel + memory drivers
            │
     Filesystem support
            │
    DAX configuration/policy
            │
       Mount point
            │
    File mapping của JVM
            │
        Java heap
~~~

Nếu một lớp không phù hợp, đường truy cập có thể:
- Không dùng DAX;
- Sử dụng cơ chế file mapping bình thường;
- Không đáp ứng yêu cầu latency/correctness đã đặt ra;
- Hoặc không cho JVM tạo/mở/map backing file.

Không nên **ép mount options theo bài viết cũ**. Tài liệu kernel Linux hiện đại mô tả chính sách DAX cho từng filesystem, có những cơ chế như `dax=inode`, `dax=always` hay `FS_XFLAG_DAX`. Cách bật đúng phụ thuộc kernel/filesystem, và tùy chọn `-o dax` trên một số hệ thống được coi là alias legacy. **Hãy làm theo kernel/filesystem docs đang dùng**, không copy lệnh mount không kiểm chứng.

### 4.2. File-backed mapping không phải database bền vững

Việc dùng memory-mapped file **không biến Java object graph thành dữ liệu có thể khởi động lại**:
- Java heap vẫn thuộc về **một JVM process**;
- GC di chuyển object và thay đổi metadata/references;
- Object headers, class layouts, runtime pointers và thread state phụ thuộc process/runtime;
- Backing file của heap có thể là tệp tạm do JVM tạo và quản lý;
- Device có tính persistent cũng không đồng nghĩa dữ liệu Java object bền vững theo API của ứng dụng.

**Đừng thiết kế logic “restart JVM rồi mở lại Java objects từ vùng PMEM” chỉ dựa trên `AllocateHeapAt`.** Muốn persistence thực sự phải dùng database, storage engine hoặc cơ chế lưu trữ/memory-mapped data với giao thức phục hồi rõ ràng.

### 4.3. Quyền truy cập, đường dẫn và dung lượng

Để JVM sử dụng mount point, phải kiểm tra:
- Directory/path tồn tại và nằm trên filesystem đúng dự định;
- Process identity có quyền cần thiết để tạo/mở file backing;
- Filesystem còn đủ **usable capacity** và quota;
- Chính sách SELinux/AppArmor/container mounts cho phép thao tác;
- Mount point được đưa vào container nếu chạy Docker/Kubernetes;
- Device/namespace không bị dùng vượt hoặc bị unmount giữa chừng.

**Không coi một lệnh `df` thành công là bảo đảm đủ backing**. Cần đánh giá quota, reservation, page size, trạng thái device và cách JVM/OS sử dụng mapping.

### 4.4. Vì sao không dùng một thư mục bất kỳ để suy ra PMEM?

Ví dụ:
- `/tmp` có thể nằm trên ổ đĩa hoặc tmpfs tùy OS;
- `/dev/shm` thường là tmpfs, không phải bảo đảm non-DRAM PMEM;
- Một thư mục trong image container có thể là overlay filesystem;
- Mount NFS hoặc block storage thường có sematics/performance khác direct PMEM.

**Đường dẫn flag chỉ xác định vị trí filesystem**, không tự chuyển đổi loại phần cứng phía dưới nó.

## 5. Giới hạn lớp 3: bản dựng JVM, OS và CPU architecture

`-XX:AllocateHeapAt` là **HotSpot-specific option**. Nó **không phải một lời hứa của Java Language Specification hoặc mọi Java Virtual Machine implementation**.

Vì vậy phải xác định:
- **JDK distribution/vendor**: Oracle JDK, OpenJDK build, Temurin hoặc một biến thể khác;
- **Feature/update/build**: phiên bản chính và các bản vá có thể ảnh hưởng platform support;
- **JVM implementation**: HotSpot hay implementation khác;
- **OS**: Linux, Windows, macOS... không giả định cùng support;
- **CPU architecture**: x86-64, AArch64, các kiến trúc khác có thể có code paths khác;
- **GC đã chọn và VM flags**: khả năng backing heap, page allocation và collector có thể tương tác;
- **Bản đóng gói / container image**: build nhỏ gọn hoặc vendor-specific có thể khác.

### Cờ còn được tài liệu hóa trên JDK mới

Oracle JDK 25 `java` launcher tiếp tục mô tả **`-XX:AllocateHeapAt=path`**. Tài liệu cũng nêu:
- Mục tiêu là **Java object heap**;
- Có thể dùng thiết bị bộ nhớ thay thế có semantics thích hợp;
- Các vùng khác như code heap, metaspace và thread stacks vẫn dùng DRAM;
- `-Xmx`, `-Xms` và các tùy chọn GC có ý nghĩa như trước.

Nhưng **“được ghi trong manual JDK 25” không bằng “mọi VM hỗ trợ trên mọi OS”**. Trước khi sử dụng:
1. Đọc manual của **đúng JDK build** đang triển khai.
2. Xác nhận VM chấp nhận cờ tại startup.
3. Xác nhận **backing mapping thực sự** trỏ đến device/mount mong muốn.
4. Kiểm chứng tương thích với GC và flags đang dùng.
5. Chạy workload đại diện trước production.

### Java source code không thể tự quyết định backend của heap

Không có cú pháp Java chuẩn kiểu `newOnPMEM Foo()` để tự động điều khiển `AllocateHeapAt`. Đây là **VM-level launch option**.

**Cùng file .class** có thể chạy với heap bình thường hoặc heap trên thiết bị thay thế, khi nền tảng hỗ trợ. Nhưng source code không có quyền tự khẳng định “mình đang ở PMEM” chỉ vì `Runtime.maxMemory()` trả một dung lượng lớn.

## 6. Tổng hợp ma trận điều kiện trước khi thử

| Điều kiện | Ví dụ đạt | Ví dụ chưa đạt | Hành động |
| --- | --- | --- | --- |
| Phần cứng phù hợp | Thiết bị memory-addressable có semantics được hỗ trợ | SSD thông thường qua block I/O | Kiểm tra datasheet và OS exposure |
| CPU/atomic | Atomic operations và memory ordering tương thích | Semantics không được chứng minh | Không triển khai |
| OS mapping | OS có cơ chế file mapping thích hợp | Kernel/driver thiếu support | Cập nhật/cấu hình OS hoặc chọn backing khác |
| Filesystem | DAX thực sự khả dụng nếu mục tiêu là PMEM direct access | Chỉ có page cache trên filesystem thường | Kiểm tra FS/mount/driver |
| Đường dẫn | Mount point hợp lệ, process có quyền | Thiếu mount/permission denied | Sửa provisioning/ACL |
| Dung lượng | Capacity đáp ứng heap budget | Quota/space không đủ | Giảm heap hoặc cấp thêm dung lượng |
| JVM | HotSpot build và platform support được xác minh | `Unrecognized VM option` | Chọn JDK/build hỗ trợ |
| GC/flags | Workload chạy đúng, mapping được xác nhận | Tổ hợp JVM flags không tương thích | Test riêng, không áp đặt |
| Tính đúng đắn | Tests và stress tests PASS | Concurrent tests fail | Dừng triển khai |
| Hiệu năng | Latency/throughput đủ tốt | GC pause hoặc p99 xấu đi | Không mặc định tiếp tục |

**Đạt một điều kiện không bù được điều kiện khác.** Ví dụ có PMEM thật nhưng JVM build không có code path tương thích vẫn không đủ để cấu hình.

## 7. Lệnh kiểm tra platform mà không thay đổi heap

Các lệnh dưới đây phục vụ **quan sát**, không tự động bật `AllocateHeapAt`.

### 7.1. Xác nhận JVM

~~~bash
java --version
java -XshowSettings:vm -version
~~~

`java --version` cho biết tên/version/build của Java launcher đang dùng. `-XshowSettings:vm` có thể hiển thị những thông tin JVM liên quan, nhưng **không tự chứng minh backing heap**.

Trên một JVM đang chạy, nếu có `jcmd` tương thích và đủ quyền:

~~~text
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Thay `<pid>` bằng PID thật. **Không dùng kết quả từ một Java process khác** thay cho ứng dụng cần điều tra.

### 7.2. Kiểm tra cờ tại runtime

Một phép kiểm tra khả năng nhận diện tùy chọn:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Có thể lọc danh sách để tìm `AllocateHeapAt`, nhưng flag có thể bị ẩn/khác cách hiển thị giữa các build; **không chỉ dựa vào một kết quả grep**. Hãy đối chiếu manual và chạy một thử nghiệm staging có kiểm soát để xác thực.

### 7.3. Quan sát filesystem trên Linux

Nếu quản trị viên đã chuẩn bị mount point ví dụ `/mnt/pmem-dax`:

~~~bash
findmnt -T /mnt/pmem-dax
df -h /mnt/pmem-dax
ls -ld /mnt/pmem-dax
~~~

Ý nghĩa:
- `findmnt`: kiểm tra filesystem/mount backing ở path;
- `df`: dung lượng theo filesystem;
- `ls -ld`: quyền directory cơ bản.

Các lệnh trên chỉ cung cấp **một phần bằng chứng**. DAX còn phụ thuộc cả driver/kernel/fs config và policy của inode; chỉ nhìn tên mount hoặc output `df` không đủ kết luận mapping là direct PMEM.

Nếu có công cụ quản lý persistent memory như `ndctl`, `daxctl` hoặc `numactl`, người quản trị có thể dùng chúng để hiểu namespace/device/NUMA topology. **Các công cụ này không có sẵn trên mọi máy và cách dùng phụ thuộc thiết bị.** Không phát biểu rằng việc chạy chúng thành công đã chứng minh Java heap dùng đúng backing.

## 8. Quy trình bật `-XX:AllocateHeapAt` có kiểm soát

**Điều kiện tiên quyết:** Có một mount point được đội quản trị hệ thống xác nhận phù hợp với device/OS/JVM, ví dụ **`/mnt/pmem-dax`**. Đường dẫn này **chỉ là ví dụ**, không được tạo bằng cách trỏ bừa vào một SSD hoặc đường dẫn host.

### 8.1. Baseline bằng heap thông thường

Trên một ứng dụng thử nghiệm có file `app.jar` hợp lệ:

~~~bash
java -Xms1g -Xmx1g -Xlog:gc*,os=info -jar app.jar
~~~

Đây là baseline minh họa khi đã có Java application, không phải chương trình độc lập được cung cấp trong bài. Mức **1 GiB** phải được chọn theo tài nguyên test, không dùng như khuyến nghị production.

Ghi:
- Thời gian startup;
- Throughput và p95/p99 latency;
- GC pauses, allocation rate;
- RSS/PSS/NUMA locality nếu công cụ hỗ trợ;
- JVM, OS/kernel, CPU, device và workload.

### 8.2. Thử heap trên thiết bị thay thế

Chỉ sau khi platform team xác nhận tất cả điều kiện:

~~~bash
java -Xms1g -Xmx1g -XX:AllocateHeapAt=/mnt/pmem-dax -Xlog:gc*,os=info -jar app.jar
~~~

**Không chạy lệnh này trên laptop/production tùy ý.** Nếu path không hợp lệ, OS/device thiếu khả năng mapping, JVM không hỗ trợ option hoặc dung lượng không đủ, startup/heap allocation có thể thất bại; cách báo lỗi tùy build. **Không tự giả định luôn có silent fallback về DRAM.**

Đừng chạy hai cấu hình chỉ một lần rồi tuyên bố đã đo được tỷ lệ tăng tốc.

### 8.3. Xác minh mapping thực tế

Trên Linux, với process đã chạy và đủ quyền, có thể kiểm tra file-backed virtual memory mappings:

~~~text
/proc/<pid>/maps
/proc/<pid>/smaps
/proc/<pid>/numa_maps
~~~

Đường dẫn **`<pid>`** là process ID thật, không phải chuỗi nguyên văn. Một mapping có liên hệ với backing path là một dấu hiệu hữu ích, nhưng phải ghép với:
- Filesystem/mount và DAX configuration;
- JVM launch flags và log;
- Device capacity/mapping;
- OS/kernel memory placement metrics nếu có;
- Thông tin NUMA.

**Không chỉ nhìn `Runtime.maxMemory()` để biết heap nằm trên PMEM**. API đó báo max heap capacity, **không trả vị trí vật lý từng trang**.

### 8.4. Dùng đúng cờ sizing

Theo tài liệu Oracle, các cờ như `-Xmx` và `-Xms` vẫn giữ vai trò sizing heap khi dùng `AllocateHeapAt`. Chúng không phải cờ chọn thiết bị.

`-XX:AllocateHeapAt` xác định **nơi backing heap**, còn `-Xmx` xác định **giới hạn heap**. Một backing device 128 GiB không tự làm `-Xmx` thành 128 GiB; max heap vẫn chịu JVM settings và resource constraints.

## 9. Lỗi startup: nên chẩn đoán theo lớp nào?

| Triệu chứng | Giả thuyết cần kiểm tra | Cách điều tra |
| --- | --- | --- |
| `Unrecognized VM option` | Build/VM không có flag | Xem vendor, version, manual, build type |
| JVM thoát sớm khi tạo heap | Path/backing không thể allocate/map | Xem stderr/exit code, OS logs, filesystem |
| Permission denied | Không có quyền tạo/mở backing file | Kiểm tra owner, ACL, SELinux/AppArmor, container mount |
| No space left on device | Dung lượng/quota không đủ | `df`, quota, device health, max heap |
| Mapping được nhưng vẫn dùng storage thường | Filesystem không DAX hoặc chọn sai path | Kiểm tra device, FS policy, actual mapping |
| Test Java nhanh/chậm bất thường | Device latency/NUMA/GC/OS cache khác | Benchmark nhiều lượt, phân tích bottleneck |
| JVM có flag nhưng mapping không như mong muốn | Build/platform/GC interaction | Xem log, process maps, docs đúng build |
| Container OOM kill | Native/heap cùng bị cgroup hạn chế | Đọc cgroup/OS memory events, tổng footprint |
| Crash hoặc I/O/media error | Backing device/kernel lỗi | Kiểm tra kernel logs và device health, rollback |

**Không sửa hàng loạt JVM flags khi chưa phân loại nguyên nhân**. Nếu `Unrecognized VM option`, tăng `-Xmx` không giúp. Nếu path không có quyền ghi, thay GC cũng không tự cấp quyền.

### Về hành vi khi không hỗ trợ

Không có một thông điệp lỗi nhất quán cho mọi JDK distribution. **Thông báo thực tế, exit code và nơi ghi log** mới là bằng chứng. Nếu VM từ chối cờ hoặc fail heap mapping, ghi nhận nguyên văn và quay về cấu hình heap đã kiểm chứng; không coi việc JVM in `-version` thành công là chứng minh chắc chắn workload sẽ dùng mapping được.

## 10. Độ tương thích giữa các Garbage Collectors

**JEP 316 không phải cam kết rằng mọi GC trên mọi build đều hỗ trợ chính xác cùng loại backing**. Các GC có thể sử dụng các chính sách:
- Reserve/commit/uncommit khác nhau;
- Page size và large pages khác nhau;
- Memory mappings/virtual address spaces;
- Chuyển object, pinning, alignment và barrier strategies.

Vì thế, cần xác minh **GC được chọn thực sự** và test workload với đúng collector. Có thể bắt đầu với G1 trên một bản HotSpot hỗ trợ, nhưng **không tuyên bố tất cả ZGC/Shenandoah/Serial/Parallel đều có hành vi như nhau ở mọi nền tảng**.

Điều cần kiểm tra:
1. VM flags và collector thực tế ở runtime.
2. Có lỗi lúc reserve/commit/uncommit hay không.
3. Large pages và NUMA settings có tương tác với device mapping không.
4. GC logs phản ánh pause/throughput/heap capacity ra sao.
5. Trong stress test, heap expansion/shrink và GC cycles có hoạt động ổn định không.
6. Tổ hợp flags có support rõ trên build mục tiêu không.

**Không rút gọn thành “Java 10+ nào cũng chạy được với mọi GC”.** Cần kiểm tra cụ thể từng bản JVM.

## 11. Vì sao OS và phần cứng có thể làm hiệu năng khác nhau?

### 11.1. Memory latency/bandwidth

GC và application đều truy cập heap thường xuyên. Heap trên thiết bị chậm hơn DRAM có thể làm:
- Object access latency cao hơn;
- GC scan/copy tốn thời gian hơn;
- Cache misses và memory stalls tăng;
- Throughput giảm dù heap capacity lớn hơn.

Ngược lại, workload hưởng lợi khi có **heap capacity lớn** giảm áp lực GC hoặc tránh dữ liệu tràn sang storage chậm hơn. Đây là trade-off cần đo, không có một kết luận chung.

### 11.2. NUMA topology

Một device/PMEM namespace có thể gần một CPU socket hơn socket khác. Nếu application threads chạy xa vùng bộ nhớ, remote memory access có thể tăng latency. `numactl`, OS NUMA maps và các counters theo platform có thể giúp điều tra.

**Đừng thay NUMA policy tùy tiện**; nó có thể ảnh hưởng scheduler, GC threads và memory allocation ở phần DRAM còn lại.

### 11.3. Page size và memory mapping

OS có thể sử dụng nhiều kích thước trang, huge pages, DAX mappings hoặc flags mmap đặc biệt. Không phải mọi combination đều được một JVM build hỗ trợ.

Một cảnh báo thực tế là **đặt large-page flags và AllocateHeapAt cùng lúc** rồi nghĩ mọi cấu hình đều tương thích. Nên bắt đầu từ một configuration tối giản đã được nhà cung cấp xác nhận, sau đó đánh giá từng tùy chọn.

### 11.4. Dung lượng memory devices và lỗi media

Device capacity không bằng dung lượng heap bảo đảm: còn quota, mappings, các allocations khác hoặc sự cố media/namespace. Việc backing không thể thực hiện yêu cầu có thể gây lỗi khởi tạo/thi hành.

Phải có:
- Giám sát capacity;
- Device health/error reporting;
- Alert khi mounting/namespace thay đổi;
- Recovery/rollback;
- Kiểm tra backup/persistence của **dữ liệu nghiệp vụ** bằng cơ chế riêng.

## 12. Lưu ý an toàn và bảo mật

### Dữ liệu heap có thể nhạy cảm

Java heap có thể chứa:
- Session tokens;
- User data;
- Secrets và key material;
- Nội dung request/response;
- Thông tin database credentials hoặc application state.

Nếu backing nằm trên thiết bị **không mất dữ liệu khi tắt điện**, cần tính tới khả năng **dấu vết dữ liệu** tồn tại ở mức media, ngay cả khi JVM process đã thoát. Ngữ nghĩa xóa/truncate/unlink file tùy OS/filesystem/device; không tự suy ra rằng file tạm đã bị xóa là mọi byte vật lý đã bị khử an toàn.

Biện pháp:
- Giới hạn quyền mount directory;
- Không để nhiều người dùng/containers tùy ý truy cập cùng backing path;
- Áp dụng chính sách mã hóa, sanitization và media disposal phù hợp;
- Kiểm soát heap dump, core dump và những artifacts chẩn đoán;
- Có kế hoạch xử lý dữ liệu nhạy cảm khi thu hồi thiết bị.

**Không dùng AllocateHeapAt để giả lập cơ chế persistence nghiệp vụ**. Bảo vệ dữ liệu bền vững phải do storage system/application thiết kế riêng.

### Lỗi phần cứng và tính đúng đắn

Thiết bị phải đáp ứng memory semantics JVM yêu cầu. Nếu không, các lỗi concurrent có thể khó tái hiện và nguy hiểm hơn một lỗi startup rõ ràng. Hãy kiểm tra theo vendor guidance và làm stress/concurrency testing.

## 13. Chương trình Java 17+ hoàn chỉnh: mô phỏng ma trận giới hạn

Không phải ai học Java cũng có NV-DIMM hoặc DAX filesystem. Ví dụ dưới đây **chạy được trên mọi JDK 17+ thông thường** mà không thay đổi heap backing. Nó mô hình hóa năm điều kiện, đưa ra **quyết định ban đầu cho staging test**, và cung cấp chế độ `--runtime` để xem thông tin JVM hiện tại.

**Quan trọng:** Các giá trị boolean trong chương trình là **dữ liệu giả lập do người học cung cấp**. Chương trình **không tự chứng nhận** phần cứng, DAX, quyền ghi hay JVM build của máy đang chạy. Kết quả `READY_FOR_STAGING_TEST` **không phải giấy chứng nhận production-ready**.

Tạo file **HeapPlacementLimitsDemo.java**:

~~~java
import java.util.List;

public class HeapPlacementLimitsDemo {

    record Platform(
            String name,
            boolean memorySemantics,
            boolean directMapping,
            boolean writablePath,
            boolean enoughCapacity,
            boolean compatibleVmBuild) {
    }

    static String assessment(Platform p) {
        if (!p.memorySemantics()) {
            return "BLOCKED: hardware semantics";
        }
        if (!p.directMapping()) {
            return "BLOCKED: OS/filesystem mapping";
        }
        if (!p.writablePath()) {
            return "BLOCKED: path permissions";
        }
        if (!p.enoughCapacity()) {
            return "BLOCKED: backing capacity";
        }
        if (!p.compatibleVmBuild()) {
            return "BLOCKED: JVM build";
        }
        return "READY_FOR_STAGING_TEST";
    }

    static void showRuntime() {
        System.out.println("=== Runtime-dependent ===");
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vm.name=" +
                System.getProperty("java.vm.name"));
        System.out.println("heap.max.bytes=" +
                Runtime.getRuntime().maxMemory());
    }

    public static void main(String[] args) {
        List<Platform> examples = List.of(
            new Platform("Verified PMEM stack",
                    true, true, true, true, true),
            new Platform("No suitable hardware",
                    false, true, true, true, true),
            new Platform("No DAX mapping",
                    true, false, true, true, true),
            new Platform("No write permission",
                    true, true, false, true, true),
            new Platform("Insufficient device space",
                    true, true, true, false, true),
            new Platform("Unsupported JVM build",
                    true, true, true, true, false)
        );

        for (Platform p : examples) {
            System.out.println(p.name() + " -> " + assessment(p));
        }

        if (args.length > 0 && "--runtime".equals(args[0])) {
            showRuntime();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 HeapPlacementLimitsDemo.java
java HeapPlacementLimitsDemo
~~~

**Stdout chính xác khi không có đối số:**

~~~text
Verified PMEM stack -> READY_FOR_STAGING_TEST
No suitable hardware -> BLOCKED: hardware semantics
No DAX mapping -> BLOCKED: OS/filesystem mapping
No write permission -> BLOCKED: path permissions
Insufficient device space -> BLOCKED: backing capacity
Unsupported JVM build -> BLOCKED: JVM build
~~~

Giải thích:
- Case 1 mô tả **tập giả định mọi điều kiện đã được kiểm chứng**, đủ để **bắt đầu thử nghiệm staging**, chưa phải production approval.
- Case 2 thiếu memory semantics thích hợp; filesystem hoặc JVM tốt không thể bù.
- Case 3 không có mapping đủ điều kiện theo kịch bản; một directory trên SSD thông thường không tự đạt yêu cầu.
- Case 4 fail do thiếu quyền, bất kể dung lượng đủ.
- Case 5 fail do dung lượng/quota.
- Case 6 fail do JVM build không tương thích; Java source vẫn có thể compile/run bình thường trên một VM khác.

### Chế độ xem runtime, không xác nhận PMEM

~~~bash
java HeapPlacementLimitsDemo --runtime
~~~

Sau sáu dòng cố định, chương trình in thêm **tên OS, kiến trúc CPU, Java version, VM name và max heap bytes**, những giá trị phụ thuộc môi trường.

**Không có dòng nào trong API `System.getProperty` hoặc `Runtime.maxMemory()` chứng minh Java heap được backed bởi PMEM.** Đó là lý do phải kết hợp JVM launch configuration, OS maps và thông tin device/filesystem.

## 14. Quy trình thử nghiệm ba giai đoạn

### Giai đoạn A — Preflight, chưa chạy app với alternative heap

1. Xác minh thiết bị **thực sự là memory-class hardware**, không suy từ tên filesystem.
2. Kiểm tra CPU/OS memory semantics và khả năng atomic.
3. Kiểm tra kernel driver và filesystem support.
4. Xác nhận DAX mode/policy ở đúng directory nếu cần direct mapping.
5. Kiểm tra quyền, quota, device capacity, mount namespace và container binds.
6. Xem JDK build, platform, GC và flags có được hỗ trợ không.
7. Lập ngân sách **DRAM cho các vùng ngoài Java heap**.
8. Chọn workload đo đúng nhu cầu capacity, latency và throughput.

### Giai đoạn B — Staging, có đối chứng

1. Chạy JVM heap thông thường với `-Xms`, `-Xmx`, GC và workload đã cố định.
2. Chạy cùng ứng dụng với `AllocateHeapAt` trên môi trường thật phù hợp.
3. Xác minh process start, GC behavior và heap backing.
4. Đo startup, GC pause p95/p99, throughput và RAM/native footprint.
5. Kiểm tra concurrent workload, exceptions và correctness.
6. Lặp nhiều lượt, không chọn một kết quả đẹp duy nhất.

### Giai đoạn C — Triển khai có kiểm soát

1. Giữ artifact/version của JDK và cấu hình device/OS đã kiểm chứng.
2. Dùng canary nếu hệ thống cho phép.
3. Giám sát device health, quota, remapping, kernel errors.
4. Theo dõi tail latency và GC pause, không chỉ heap capacity.
5. Có phương án **rollback về heap thường** và khởi động lại process an toàn.
6. Kiểm tra đường dẫn chứa dữ liệu nhạy cảm và media sanitization policy.
7. Sau nâng kernel/JDK/GC/image, **kiểm thử lại**, không mặc định tính tương thích còn nguyên.

## 15. Các hiểu nhầm thường gặp

**Hiểu nhầm 1 — “Có Java 10+ là mọi máy đều dùng AllocateHeapAt được.”**  
Sai: cần hardware, OS/filesystem và JVM build phù hợp.

**Hiểu nhầm 2 — “SSD NVMe là persistent memory có thể dùng như DRAM.”**  
Sai: một block device NVMe thông thường không tự cung cấp byte-addressability và atomic semantics như main memory.

**Hiểu nhầm 3 — “Chỉ cần thư mục tồn tại là heap ở PMEM.”**  
Sai: path có thể nằm trên tmpfs, overlayfs, SSD hoặc network storage.

**Hiểu nhầm 4 — “Tệp mmap nào cũng là DAX.”**  
Sai: file mapping có thể đi qua page cache; DAX cần thiết bị, filesystem và policy phù hợp.

**Hiểu nhầm 5 — “Persistent hardware sẽ giữ nguyên Java object sau khi JVM thoát.”**  
Sai: `AllocateHeapAt` không cung cấp Java object persistence/recovery API.

**Hiểu nhầm 6 — “Toàn bộ JVM memory chuyển sang thiết bị thay thế.”**  
Sai: code cache, Metaspace, thread stacks và nhiều native allocations vẫn dùng nguồn bộ nhớ thông thường.

**Hiểu nhầm 7 — “Dùng heap thay thế sẽ luôn nhanh hơn DRAM.”**  
Sai: latency, bandwidth, NUMA và GC workload có thể khiến hiệu năng giảm.

**Hiểu nhầm 8 — “`-Xmx` không còn tác dụng khi dùng AllocateHeapAt.”**  
Sai: heap-size flags vẫn có ngữ nghĩa riêng.

**Hiểu nhầm 9 — “Oracle JDK 25 ghi cờ, nên mọi vendor/JVM trên mọi OS đều hỗ trợ.”**  
Sai: phải kiểm tra build và platform thực.

**Hiểu nhầm 10 — “`Runtime.maxMemory()` cho biết heap nằm trên thiết bị nào.”**  
Sai: nó chỉ cho maximum Java heap.

**Hiểu nhầm 11 — “Tăng `-Xmx` tới dung lượng thiết bị là an toàn.”**  
Sai: còn space/quota, mapping, off-heap DRAM và OS limits.

**Hiểu nhầm 12 — “Một lệnh `java -version` có flag chạy thành công chứng minh workload sẽ ổn.”**  
Sai: phải kiểm thử actual backing và allocation/GC thật.

**Hiểu nhầm 13 — “Mọi GC implementation/flags đều tương thích trên tất cả build.”**  
Sai: support thực tế tùy version, collector, OS và memory mapping.

**Hiểu nhầm 14 — “Nếu JVM startup fail, cứ chỉnh GC threads.”**  
Sai: lỗi có thể do path, permission, quota, filesystem hoặc unsupported option.

**Hiểu nhầm 15 — “Xóa backing file là đảm bảo không còn dữ liệu nhạy cảm trên PMEM.”**  
Không được bảo đảm; phải tuân thủ chính sách sanitization và quyền truy cập.

## 16. Checklist chẩn đoán khi không thể đặt heap lên thiết bị

1. Ghi đúng **Java launcher/JVM vendor, version và build**.
2. Ghi **OS/kernel version** và CPU architecture.
3. Xác nhận option **`-XX:AllocateHeapAt`** có trong manual phù hợp.
4. Xác minh command line đã truyền flag **trước** main class hoặc `-jar`.
5. Kiểm tra **device thực**, không đoán từ tên directory.
6. Xác minh byte-addressability/atomic semantics.
7. Kiểm tra filesystem DAX/OS mapping policy khi dùng PMEM direct access.
8. Đọc **mount point** và các driver/namespace constraints.
9. Kiểm tra quyền ghi và ownership của JVM process.
10. Kiểm tra quota, device capacity và OS memory mapping limits.
11. Xác minh GC, large pages và các flags khác có tương thích không.
12. Ghi stderr/exit code khi startup failure.
13. Nếu process chạy được, xác minh **actual backing mapping**, không chỉ heap max.
14. Theo dõi Metaspace, code cache, stacks và DRAM còn lại.
15. Thử concurrency/GC stress tests trên staging.
16. So kết quả với baseline heap thường.
17. Theo dõi startup, GC pauses, p99 latency và throughput.
18. Kiểm tra bảo mật dữ liệu trên persistent device.
19. Chuẩn bị rollback và recovery nếu device/kernel gặp lỗi.
20. Kiểm thử lại sau khi nâng JDK, OS hoặc đổi phần cứng.

## 17. Câu hỏi tự kiểm tra

**Câu 1. Tính năng Java 10 nào liên quan đặt object heap trên alternative memory?**  
**JEP 316 — Heap Allocation on Alternative Memory Devices**, gắn với HotSpot flag `-XX:AllocateHeapAt`.

**Câu 2. Tại sao không phải mọi SSD đều phù hợp?**  
Vì SSD block storage thông thường không tự cung cấp memory access semantics/atomic operations mà JVM cần khi dùng heap như main memory.

**Câu 3. DAX giải quyết điều gì?**  
Trên filesystem/device phù hợp, DAX có thể cho file mapping trực tiếp, tránh bản sao trong page cache theo cơ chế file thông thường.

**Câu 4. Chỉ cần một thư mục trên filesystem là đủ?**  
Không. Phải biết filesystem backing, device, mapping mode, quyền, quota và build JVM.

**Câu 5. Cờ nào chọn vị trí backing, cờ nào chọn mức heap tối đa?**  
`-XX:AllocateHeapAt=path` chọn backing path; `-Xmx` chọn maximum heap.

**Câu 6. Metaspace và thread stacks có tự chuyển sang device khi dùng AllocateHeapAt?**  
Không. Oracle mô tả các vùng như code heap, Metaspace và stacks vẫn thuộc DRAM.

**Câu 7. Nếu dùng PMEM, Java objects có tự tồn tại qua JVM restart không?**  
Không. Đây là đổi backing heap, không phải persistence/recovery API.

**Câu 8. Vì sao cần kiểm tra OS và JVM build?**  
Vì flag/code paths, kernel/filesystem support, CPU architecture và GC có thể khác nhau theo môi trường.

**Câu 9. Có thể dùng Java API chuẩn để xác định từng trang heap đang ở PMEM không?**  
Không có API Java SE tiêu chuẩn cho việc này. Phải phối hợp OS mappings, JVM flags và device metrics.

**Câu 10. Nếu một process dùng flag thành công có bảo đảm nhanh hơn không?**  
Không. Phải đo workload với baseline DRAM, kể cả GC pause và tail latency.

**Câu 11. Vì sao NUMA quan trọng?**  
Vì CPU socket xa memory device có thể tăng latency/giảm bandwidth.

**Câu 12. Việc `-XX:AllocateHeapAt` còn trong manual JDK 25 có nghĩa mọi VM dùng được?**  
Không. Nó là HotSpot-specific và có giới hạn platform/build.

**Câu 13. Nếu startup báo permission denied, sửa gì trước?**  
Kiểm tra mount/path, UID/GID, ACL/SELinux/AppArmor và quyền trong container, không chỉnh GC tùy tiện.

**Câu 14. Tại sao phải xem security dù Java heap không phải database?**  
Vì heap có thể chứa secrets; persistent media có thể lưu lại dữ liệu ở mức thiết bị và cần sanitization thích hợp.

**Câu 15. Một chương trình Java 17+ in `READY_FOR_STAGING_TEST` đã chứng minh phần cứng thật phù hợp chưa?**  
Chưa. Trong ví dụ đó chỉ là kết quả **mô phỏng dữ liệu đầu vào**; phải xác minh thực tế.

## 18. Kết luận

- Java 10 đưa vào **JEP 316**, cho phép HotSpot cấu hình **Java object heap** trên thiết bị bộ nhớ thay thế với `-XX:AllocateHeapAt=path`.
- **Giới hạn phụ thuộc đồng thời vào ba lớp:** phần cứng có memory semantics đúng; hệ điều hành/filesystem hỗ trợ memory mapping; bản dựng JVM/GC/platform thực sự hỗ trợ.
- **NV-DIMM/PMEM, DAX, SSD và tmpfs không đồng nghĩa nhau**. Path filesystem không đủ xác nhận loại backing.
- `-Xmx`/`-Xms` vẫn tham gia sizing; **Metaspace, thread stacks, code cache** không tự chuyển sang device.
- **Thiết bị persistent không biến Java heap thành kho object bền vững**. Persistence nghiệp vụ cần cơ chế khác.
- Khả năng dùng option **không được suy từ nhãn “Java 10+”**; dù manual JDK 25 còn mô tả cờ, phải kiểm tra runtime, OS, architecture, collector và memory mappings.
- Luôn làm **preflight → staging → xác minh mapping → benchmark đối chứng → rollout có rollback**. Không đánh đổi tính đúng đắn, bảo mật và latency để lấy dung lượng lớn mà không có số đo.

**Tài liệu tham khảo chính thức, còn áp dụng:**
- [OpenJDK — JEP 316: Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316).
- [Oracle Java SE 10 — `java` launcher, `-XX:AllocateHeapAt`](https://docs.oracle.com/javase/10/tools/java.htm).
- [Oracle Java SE 17 — `java` launcher, advanced runtime options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java SE 25 — `java` launcher, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [Linux Kernel Documentation — Direct Access for files (DAX)](https://docs.kernel.org/filesystems/dax.html).
- [Oracle Java SE 25 — On-Heap and Off-Heap Memory](https://docs.oracle.com/en/java/javase/25/core/heap-and-heap-memory.html).
