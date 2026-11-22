# Phần bộ nhớ dành cho Metaspace, Code Cache và Stack trong Java container

> **Java 10 — Bộ nhớ trong container.** Khi chạy HotSpot trong Docker hoặc Kubernetes, **heap không phải toàn bộ bộ nhớ JVM sử dụng**. Ngoài Java heap, tiến trình còn dùng **Metaspace** để lưu class metadata, **Code Cache** để giữ mã máy do JIT tạo ra, **stack của các platform threads**, cùng direct buffers, cấu trúc GC, vùng native của thư viện và nhiều thành phần hệ thống. **`-Xmx` chỉ giới hạn Java heap**, không tạo ra một phần “RAM miễn phí” được bảo đảm cho các phần ngoài heap. Từ Java 10, HotSpot có khả năng nhận biết giới hạn tài nguyên container; trên JDK hiện đại vẫn phải tự quản lý **toàn bộ memory footprint** dưới giới hạn cgroup. Bài học giải thích chức năng từng vùng, các chỉ số cần quan sát, cách tính ngân sách có headroom, dấu hiệu lỗi và quy trình chẩn đoán đang áp dụng trên JDK hiện đại.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **Java heap**, **non-heap memory theo MXBeans**, **Metaspace**, **Compressed Class Space**, **JIT Code Cache**, **native thread stacks** và những native allocations khác.
2. Hiểu tại sao **`Runtime.maxMemory()`/`-Xmx` không phải cgroup hard limit** và JVM có thể bị hệ điều hành dừng dù heap chưa đầy.
3. Giải thích vai trò của `-XX:MaxMetaspaceSize`, `-XX:MetaspaceSize`, `-XX:CompressedClassSpaceSize`, `-XX:ReservedCodeCacheSize` và `-Xss` mà không nhầm **reserved** với **committed** hay **resident**.
4. Hiểu class metadata có vòng đời gắn với class loaders, khả năng class unloading và các tình huống classloader retention/leak.
5. Hiểu Code Cache phục vụ JIT compiled methods; cảnh báo “CodeCache is full” không đồng nghĩa Java heap hết chỗ.
6. Hiểu stack mỗi **platform thread** có ngân sách riêng; tăng số lượng platform threads hoặc stack size có thể làm tăng áp lực memory/address space.
7. Phân biệt virtual-thread stack trong heap (Java 21+) với native stack của carrier platform threads, tránh nhân số virtual threads với `-Xss`.
8. Đọc đúng các nguồn quan sát: `MemoryMXBean`, `MemoryPoolMXBean`, `BufferPoolMXBean`, `jcmd VM.metaspace`, `jcmd Compiler.codecache`, `jcmd VM.native_memory` và Linux cgroup v2.
9. Hiểu NMT theo dõi các phân bổ **nội bộ HotSpot** nhưng không thể thay cho số cgroup `memory.current` hoặc thay thế hoàn toàn OS RSS/PSS.
10. Biết những lỗi `OutOfMemoryError: Metaspace`, `unable to create native thread`, `StackOverflowError`, JIT code cache pressure và Linux cgroup OOM kill có nguyên nhân/biện pháp khác nhau.
11. Thiết kế một **memory budget** có tính tới heap + Metaspace + Code Cache + thread stacks + direct buffers + GC/native/other và **headroom**.
12. Chạy một chương trình Java 17+ hoàn chỉnh với **25 dòng stdout xác định**, dùng dữ liệu giả lập để luyện lập ngân sách.
13. Dùng chương trình probe Java và công cụ OS để đo **ứng dụng thật** mà không nhầm dữ liệu giả lập với benchmark thực tế.
14. Áp dụng 16 bài tập và checklist để đánh giá cấu hình JVM trong container theo các JDK vẫn được hỗ trợ.

## 2. Bối cảnh Java 10: container awareness không có nghĩa tự tính hoàn hảo mọi vùng bộ nhớ

### 2.1. JVM đã nhận biết cgroup từ đâu?

**JDK 10**, qua các thay đổi như **JDK-8146115**, bổ sung hỗ trợ nhận biết giới hạn CPU/memory của Linux container; HotSpot có `-XX:+UseContainerSupport` và các cờ điều khiển kích thước heap theo tỷ lệ `MaxRAMPercentage`, `InitialRAMPercentage` và `MinRAMPercentage`. Những cờ hiện đại này tiếp tục được tài liệu hóa trên **Oracle JDK 25**.

Nhưng khả năng phát hiện container nghĩa là HotSpot **có thêm thông tin** để lựa chọn mặc định — **không đồng nghĩa tự bảo đảm**:

- mọi phân bổ ngoài heap đều nằm trong một tỷ lệ cố định;
- cộng lại tất cả vùng memory luôn nhỏ hơn giới hạn cgroup;
- một ứng dụng đặt `-Xmx` bằng 100% limit sẽ chạy được;
- native memory của thư viện bên thứ ba được JVM tự động giới hạn;
- một thay đổi về CPU/memory limit khi process đang chạy sẽ tự đổi mọi setting nội bộ;
- cgroup `memory.max` có thể vượt được nhờ một cờ JVM.

### 2.2. Hình dung đúng “RAM của JVM”

```text
Một container Linux (ví dụ memory.max = 1 GiB)
┌──────────────────────────────────────────────────────────────┐
│ RAM được cgroup hạch toán: mọi tác vụ thuộc cgroup           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ JVM process                                            │  │
│  │                                                        │  │
│  │ Java heap                 -Xmx / MaxRAMPercentage       │  │
│  │ Metaspace + class space   -XX:MaxMetaspaceSize          │  │
│  │ JIT Code Cache            -XX:ReservedCodeCacheSize    │  │
│  │ Platform thread stacks    -Xss                          │  │
│  │ Direct NIO buffers        -XX:MaxDirectMemorySize       │  │
│  │ GC/compiler/native libs   thêm các phân bổ khác        │  │
│  └────────────────────────────────────────────────────────┘  │
│  Các process khác, page cache/file-backed pages, kernel, ... │
└──────────────────────────────────────────────────────────────┘
```

Đây là **sơ đồ khái niệm**, không phải phép cộng chính xác các giá trị `reserved`. Trên Linux, các memory pages có thể là resident, shared, reclaimable hoặc file-backed; cgroup có quy tắc riêng về hạch toán. Một giới hạn của Java subsystem có thể là **địa chỉ ảo reserved**, không phải mức RAM thật đang dùng.

### 2.3. Nguồn giới hạn nào chi phối?

| Nguồn | Ý nghĩa | Không được nhầm |
| --- | --- | --- |
| `-Xmx512m` | Heap JVM có giới hạn tối đa xấp xỉ 512 MiB | Không đặt trần total native + heap |
| `-XX:MaxRAMPercentage=50` | Cơ sở **chọn kích thước heap tự động** theo RAM JVM xác định, khi không có override phù hợp | Không tự cho tất cả thành phần memory dùng 50% còn lại một cách an toàn |
| `-XX:MaxMetaspaceSize=...` | Giới hạn class metadata Metaspace | Không giới hạn GC, code cache, stacks, direct buffers |
| `-XX:ReservedCodeCacheSize=...` | Trần vùng code cache cho compiled code | Không phản ánh số RAM resident đã dùng |
| `-Xss1m` | Quy mô stack Java của **platform thread**, phụ thuộc platform | Không phải 1 MiB RAM resident nhân cứng theo thread |
| cgroup v2 `memory.max` | Giới hạn hard memory của cgroup tại mức đó | Không tương đương `Runtime.maxMemory()` |
| cgroup v2 `memory.current` | Memory đang được controller hạch toán, thường gồm cả các khoản ngoài process heap | Không đồng nghĩa NMT committed hay JVM nonheap used |
| Linux `VmRSS` / `smaps_rollup` | Chỉ số memory resident của process | Không tự bao trọn page cache hay toàn cgroup |

**Chỉ một trong các dòng này không đủ để kết luận cấu hình memory an toàn.** Hãy xem cả JVM flags, memory pool usage, cgroup counters và trạng thái các thành phần khác của container.

## 3. Bốn tầng số liệu: used, reserved, committed, resident

Một nguyên nhân lớn gây hiểu sai memory là dùng một từ **“đã dùng”** cho những đơn vị/semantics khác nhau.

### 3.1. Used — đang được subsystem sử dụng

Ví dụ `MemoryUsage.getUsed()` cho một memory pool mô tả mức memory **subsystem đang dùng** theo JMX, ví dụ số byte class metadata hoặc compiled code mà pool báo cáo.

Không suy ra một con số “used” bằng lượng resident physical RAM ngay lập tức. JVM có thể còn free space trong chunks được committed và OS có cơ chế resident riêng.

### 3.2. Reserved — vùng địa chỉ ảo đã giữ chỗ

HotSpot có thể **reserve** một vùng virtual address space rất lớn cho khả năng mở rộng sau này. Chẳng hạn **Compressed Class Space** trên 64-bit HotSpot thường được reserve trước với cỡ mặc định khoảng **1 GiB** theo tài liệu Oracle JDK 25.

**Reserve 1 GiB không có nghĩa JVM vừa tiêu thụ 1 GiB physical RAM của container.** RAM chỉ được sử dụng theo những trang được commit/touch và OS accounting thực tế. Đừng lấy tổng reserved của NMT rồi so thẳng với `memory.max` để kết luận OOM chắc chắn.

### 3.3. Committed — phần memory VM/OS đã commit

“Committed” trong báo cáo HotSpot mô tả memory đã được cam kết cho hoạt động của subsystem theo semantics VM. Nó **không phải** phép đo hoàn hảo số physical pages resident theo kernel.

Ví dụ tài liệu NMT lưu ý stack có thể được đánh dấu committed trong HotSpot nhưng OS chưa nhất thiết commit/resident toàn bộ stack tương ứng. Cần đối chiếu với RSS/PSS/cgroup nếu mục đích là footprint thật.

### 3.4. Resident — những trang thật đang có trong RAM theo OS

**RSS** của process đo những trang resident được map vào process; **PSS** phân bổ tỉ lệ các trang shared cho từng process. **cgroup memory.current** theo dõi memory được quy về cgroup và descendants theo kernel rules, gồm những khoản như anonymous memory, file/page cache và một số kernel memory.

Vì vậy có thể có:

```text
Reserved virtual address space: rất lớn
Committed VM memory:          thấp hơn reserved
Resident process RSS:         khác committed
Cgroup memory.current:        có thêm page cache/kernel/other processes
```

**Không có phép bằng đơn giản** `RSS = NMT committed = heap used + metaspace used + code cache used`. Trình bày tổng bằng các con số khác semantics như vậy là một loại double counting và/hoặc bỏ sót.

## 4. Metaspace: chỗ lưu class metadata của HotSpot

### 4.1. Metaspace chứa gì?

**Metaspace** là không gian HotSpot dùng cho **metadata mô tả các lớp Java**, chẳng hạn các cấu trúc runtime biểu diễn class, method, constant pool theo triển khai VM. Từ các JDK hiện đại, class metadata được quản lý trong **native memory**, không phải đối tượng Java thông thường trong `-Xmx` heap.

**Không gộp tất cả thứ liên quan class vào Metaspace:** đối tượng `java.lang.Class`, arrays, các đối tượng reflection hoặc dữ liệu ứng dụng vẫn có thể nằm trên Java heap; còn metadata HotSpot native nằm trong khu vực quản lý tương ứng. Một thư viện có thể giữ ClassLoader object trên heap và vì vậy gián tiếp giữ metadata các lớp native được classloader tải.

### 4.2. Metaspace thay đổi theo số class và class loaders

Metaspace có xu hướng tăng khi:
- Ứng dụng tải nhiều lớp từ frameworks/libraries.
- Class loaders tạo lớp động, bytecode generation, proxies, instrumentation.
- Ứng dụng hot-reload nhiều lần, hoặc có nhiều tenants/plugins với class loaders riêng.
- Các loader không được garbage-collected/unloaded đúng vòng đời.

Class metadata có thể được thu hồi khi các class/classloader đủ điều kiện **class unloading**, tùy GC, reachability và môi trường. Metaspace không phải một “cache chỉ tăng không bao giờ giảm” được đặc tả cố định; nhưng tăng liên tục qua nhiều lần redeploy cũng là tín hiệu cần kiểm tra giữ tham chiếu ClassLoader.

**Không dùng `System.gc()` như bảo đảm class unloading xảy ra tức thì**, vì GC behavior thuộc JVM và có thể bị vô hiệu/điều chỉnh. Nếu tăng metadata theo số lần reload, điều tra object retention/classloader graph trước khi tăng memory limit.

### 4.3. Cờ `-XX:MaxMetaspaceSize`

```bash
java -XX:MaxMetaspaceSize=256m -jar app.jar
```

Đây là **lệnh mẫu**, chỉ chạy khi có `app.jar` hợp lệ. Cờ đặt **trần** lượng class metadata được phép dùng theo HotSpot, không đặt cứng một lượng RAM đã resident.

Một số vấn đề:
- Đặt quá nhỏ có thể gây **`java.lang.OutOfMemoryError: Metaspace`**.
- Đặt rất lớn không có nghĩa JVM sẽ dùng hết mức đó.
- Không đặt cờ thì kích thước metadata theo mặc định có thể được mở rộng theo nhu cầu/khả năng môi trường, không phải một ngân sách tự động bảo vệ toàn bộ cgroup.
- Tăng trần có thể giúp workload có nhiều lớp hợp lệ, nhưng nếu có classloader leak thì thường chỉ **trì hoãn lỗi**.
- `MaxMetaspaceSize` không bao trùm GC structures, Code Cache, thread stacks hay native buffers.

**Trên JDK hiện đại, muốn giới hạn phần class metadata, dùng `MaxMetaspaceSize`; không dùng các hướng dẫn PermGen legacy.** HotSpot đã không dùng Permanent Generation cho class metadata từ JDK 8.

### 4.4. `-XX:MetaspaceSize` không phải “Metaspace max”

Cờ `-XX:MetaspaceSize` liên quan **ngưỡng high-water-mark** khiến JVM cân nhắc một đợt GC để xử lý class metadata. Nó **không** đồng nghĩa hard maximum của Metaspace.

Ví dụ:

```text
-XX:MetaspaceSize=64m
-XX:MaxMetaspaceSize=256m
```

Đây là hai mục tiêu khác nhau:
- `MetaspaceSize` ảnh hưởng ngưỡng quản lý/GC, có thể được điều chỉnh theo runtime.
- `MaxMetaspaceSize` là trần được cấu hình cho class metadata.

Không coi số `64m` trong ví dụ là cam kết “Metaspace lúc nào cũng dùng 64 MiB”. Không ép chỉnh `MetaspaceSize` trước khi có bằng chứng GC/classloading bottleneck.

### 4.5. Compressed Class Space: 1 GiB reserved không có nghĩa 1 GiB physical

HotSpot x64 có một vùng **Compressed Class Space** để biểu diễn phần metadata lớp theo cơ chế class pointers nén. Theo Oracle JDK 25, vùng này thông thường được **reserve 1 GiB virtual address space** và commit theo lớp thực sự cần. `-XX:CompressedClassSpaceSize` điều chỉnh quy mô vùng trong giới hạn support/implementation.

Những điều quan trọng:
- **`reserved` 1 GiB không được cộng nguyên 1 GiB vào memory.current.**
- `-XX:MaxMetaspaceSize` áp dụng cho **tổng class metadata tương ứng**, bao gồm committed compressed class space cùng các thành phần khác theo Javadoc/GC tuning.
- Nếu cần thêm class metadata, hãy xem cả metrics class space/Metaspace và số lượng classes/classloaders trước khi sửa cờ.
- Java SE 25 **deprecated `UseCompressedClassPointers` flag** vì hướng tới chỉ còn compressed mode; không khuyên “tắt compressed pointers” như tuning mặc định để sửa memory.
- Các mặc định/giới hạn có thể thay đổi theo JDK/architecture, nên dùng tài liệu và diagnostics **đúng bản phát hành**.

### 4.6. Theo dõi Metaspace bằng công cụ thật

Để quan sát một JVM HotSpot đang chạy:

```bash
jcmd "$PID" VM.metaspace
jcmd "$PID" VM.classloader_stats
```

`VM.metaspace` có tùy chọn `basic` và những chế độ breakdown khác theo `jcmd "$PID" help VM.metaspace`; một số chế độ có tác động pause và nên dùng có chủ đích. `VM.classloader_stats` giúp xem class loaders và metadata thống kê, hữu ích trong chẩn đoán classloader leak.

Ngoài ra `MemoryPoolMXBean` có thể báo pool mang tên như “Metaspace” và “Compressed Class Space”, **nhưng tên pool là chi tiết implementation**, không nên hardcode tên cho logic bảo mật hoặc accounting cgroup.

## 5. Code Cache: vùng chứa mã máy JIT, không phải Java heap

### 5.1. Code Cache là gì?

**JIT (Just-In-Time) compiler** chuyển những method Java có lợi cho việc tối ưu thành **native machine code** để JVM có thể thực thi hiệu quả. Code Cache là vùng HotSpot dành cho mã máy được biên dịch và một số cấu trúc liên quan.

Đừng đồng nhất:
- Java `byte[]` hoặc object cache nằm trên heap.
- Application cache như Caffeine/Redis.
- File cache của hệ điều hành.
- **JIT Code Cache** chứa generated code.

Chúng khác mục đích, lifecycle, giới hạn và phép đo.

### 5.2. Flag `-XX:ReservedCodeCacheSize`

```bash
java -XX:ReservedCodeCacheSize=128m -jar app.jar
```

Cờ xác định giới hạn **code cache reserved capacity** theo HotSpot. Trong tài liệu Oracle Java SE 25, mặc định của Code Cache có thể là **240 MiB** khi tiered compilation bật và những điều kiện thông dụng, nhưng không coi 240 MiB là mức RAM resident bắt buộc hay một mặc định bất biến trên mọi JVM/JDK.

Quan trọng:
- **ReservedCodeCacheSize không phải “tổng native memory cap”.**
- Vùng code cache có thể reserve đủ virtual address range nhưng commit/touch một phần.
- Code cache có thể được **segmented** thành nhiều vùng như non-method, profiled, non-profiled code, tùy JVM flags và version.
- Một số code có thể bị dọn hoặc không còn được sử dụng theo hoạt động JIT và code cache management.
- Khi code cache đầy/fragmented, quá trình compilation/tối ưu có thể bị ảnh hưởng; JVM có thể phát cảnh báo/code compilation bị hạn chế.
- Đặt quá nhỏ có thể giảm peak throughput hoặc ảnh hưởng warmup; tăng vô điều kiện có thể làm tiêu thụ native memory tăng, cần đo.

### 5.3. Dấu hiệu code cache pressure

Các biểu hiện có thể có:
- Log cảnh báo `CodeCache is full. Compiler has been disabled.` hoặc thông báo tương tự tùy HotSpot build.
- Tốc độ JIT compilation không tiếp tục như kỳ vọng.
- Warmup hoặc steady-state throughput suy giảm sau một khoảng chạy dài.
- Metrics code heap sử dụng gần trần của một segment.
- `jcmd Compiler.codecache` cho thấy layout/capacity/usage của code heaps.

Không đồng nhất Code Cache full với `OutOfMemoryError: Java heap space`. Đây là hai subsystem khác nhau, có biện pháp chẩn đoán khác nhau.

### 5.4. Quan sát code cache

```bash
jcmd "$PID" Compiler.codecache
jcmd "$PID" help Compiler.codecache
```

Kết quả có thể liệt kê các code heaps, tổng used/free và metadata. Chi tiết của lệnh tùy JDK, hãy dùng `help` trên JVM mục tiêu.

JMX `MemoryPoolMXBean` thường có một hoặc vài pool Code Cache/CodeHeap, tùy phân đoạn; **đừng giả định chỉ có một pool tên `"Code Cache"` trên mọi JDK**. Thay vì hardcode, kiểm kê các `MemoryType.NON_HEAP` pools thực sự có mặt.

### 5.5. Sử dụng `Code Cache` và `Class Metaspace` là hai KPI khác

| Quan sát | Nghi vấn ưu tiên | Phép đo |
| --- | --- | --- |
| Lớp được tạo/tải không ngừng; metaspace tăng | ClassLoader/proxy/bytecode generation retention | `VM.metaspace`, `VM.classloader_stats`, JFR/heap analysis |
| Code Cache gần đầy; JIT warnings | Giới hạn hoặc fragment code cache, compilation profile | `Compiler.codecache`, JFR/compiler logs |
| Heap used tăng, GC không giải phóng | Object retention hoặc allocation rate | GC logs, heap dump/JFR (theo chính sách) |
| Cgroup memory.current tăng mà heap/nonheap gần ổn | Direct buffers, native libs, page cache, kernel memory hoặc process khác | NMT + OS metrics + process maps/cgroup |
| JVM báo nhiều threads rồi process mất ổn định | Stacks và native thread overhead, OS task limits | Thread count, NMT Thread, OS process/thread stats |

Không chỉ nhìn một biểu đồ “nonheap used” gộp rồi kết luận nguyên nhân là Metaspace.

## 6. Stack của Java thread: một chi phí theo platform threads

### 6.1. Stack chứa gì?

Mỗi **platform thread** của Java thường gắn với một OS thread và có **native stack** phục vụ call frames, lời gọi native và thực thi ngăn xếp theo môi trường JVM/OS. Stack không phải một object array có thể tính trực tiếp vào Java heap.

Kích thước stack còn chịu ảnh hưởng:
- Kiến trúc/OS, phiên bản JVM.
- Java/VM/native call frames thực tế.
- `-Xss` hoặc `-XX:ThreadStackSize` khi hỗ trợ.
- Cấu hình thread type, JDK internal threads và runtime.
- Kernel stack và các cấu trúc thread khác, không bị bao trọn bởi một phép nhân đơn giản.

### 6.2. `-Xss` và `-XX:ThreadStackSize`

```bash
java -Xss1m -jar app.jar
```

`-Xss1m` đặt kích thước stack của Java threads theo option được HotSpot hỗ trợ; `-XX:ThreadStackSize` có đơn vị/cú pháp riêng theo Oracle `java` launcher (kích thước tính theo KiB theo hướng dẫn flag).

**Không nói mỗi platform thread đang resident đúng 1 MiB ngay khi được tạo.** Stack có thể reserve một vùng address space nhưng chỉ phần trang thực sự dùng/touch mới trở thành resident theo OS. NMT stack reserved/committed, RSS và kernel accounting không phải một phép bằng đơn giản.

**Không có một con số “default stack = 1 MiB” bất biến** cho Linux AArch64, x64, macOS, Windows và các JDK distributions. Oracle JDK 25 `java` manpage có ví dụ mặc định theo từng nền tảng; hãy kiểm tra runtime/OS cụ thể.

### 6.3. Vì sao số platform threads ảnh hưởng native memory?

Giả sử 80 platform threads được hoạch định mỗi thread **1 MiB stack allowance**. Mô hình dự trù:

\[
80 \times 1 \mathrm{MiB}=80\ \mathrm{MiB}
\]

Nếu tăng lên 120 threads:

\[
120\times1 \mathrm{MiB}=120\ \mathrm{MiB}
\]

Ngân sách **tăng 40 MiB** cho stack allowance, chưa kể thread descriptors, TLS/native bookkeeping, GC thread overhead hoặc memory pressure do workload. **Đây là khoản dự trù, không phải phép đo RSS.**

Một thread stack có thể reserve nhiều địa chỉ ảo hơn lượng resident, nhưng tăng quá nhiều platform threads vẫn có thể dẫn tới:
- `OutOfMemoryError: unable to create native thread`;
- lỗi `pthread_create` do memory/OS task limits;
- CPU context switching cao;
- exhaustion của số PID/threads cho phép trong cgroup `pids.max`;
- áp lực lên container memory và scheduling.

**Không giải quyết bằng cách tăng `-Xmx`.** Với số platform threads quá lớn, tăng heap còn có thể làm thiếu headroom cho native memory.

### 6.4. `StackOverflowError` khác `OutOfMemoryError`

**`StackOverflowError`** thường xuất hiện khi một thread thực hiện call stack quá sâu, chẳng hạn đệ quy không có base case. Điều đó không đồng nghĩa “cgroup đã hết RAM”.

Ví dụ:

```java
// Đoạn minh họa NGUY HIỂM: không chạy trong production.
static int recurse(int n) {
    return recurse(n + 1);
}
```

Không dùng stack overflow cố ý làm benchmark memory container. Hãy sửa thuật toán/đệ quy trước, và chỉ cân nhắc `-Xss` khi có use case đo đạc rõ.

**`OutOfMemoryError: unable to create native thread`** lại liên quan không tạo được thread mới, có thể do native memory hoặc giới hạn OS/process; phải kiểm tra thread count, cgroup `pids.max`, ulimit, native memory và OS logs. Hai lỗi này không thể được gộp thành một nguyên nhân.

### 6.5. Virtual threads không nhân `-Xss` theo từng virtual thread

Từ **Java 21**, virtual threads là một loại Java `Thread` có stack frames được biểu diễn trong **heap-backed continuations** và có thể được mount/unmount trên **carrier platform threads**. Vì thế:
- Không nhân **1 triệu virtual threads × `-Xss1m` = 1 TiB native stacks** — đó là mô hình sai.
- Các virtual threads **vẫn dùng bộ nhớ**, chủ yếu qua object/continuation/stack chunks trong heap, cộng trạng thái nghiệp vụ.
- Carrier platform threads và một số runtime threads vẫn có native stacks.
- Virtual threads **không xóa cgroup memory.max** và không tự làm vô hạn số request dễ dàng.
- Khi virtual-thread task giữ nhiều object hoặc stack sâu, heap/memory pressure vẫn có thể tăng.

**Bài tập này không khuyên đổi toàn bộ platform threads thành virtual threads chỉ để tránh OOM.** Cần xem workload blocking I/O, pinned operations, library behavior, thread locals và CPU quota của ứng dụng thật.

## 7. Ngân sách 1 GiB: tại sao `-Xmx512m` chưa đủ để kết luận an toàn?

### 7.1. Dự trù minh họa, không phải phép đo HotSpot

Giả sử cgroup hard memory limit **1.024 MiB**. Một nhóm kỹ sư dự trù:

| Khoản dự trù | MiB | Bản chất |
| --- | ---: | --- |
| Heap allowance | 512 | Mức tối đa mong muốn cho Java heap |
| Metaspace allowance | 160 | Dự trù class metadata theo tải đã quan sát |
| Code Cache allowance | 96 | Dự trù mã JIT/segments, không phải số RSS hứa hẹn |
| Platform thread stack allowance | 80 | 80 threads × 1 MiB **planning** |
| Direct buffers | 64 | Một ngân sách NIO buffer minh họa |
| GC/native/other | 96 | Các vùng khác, thư viện và khoản OS/process dự trù |
| **Tổng dự trù** | **1.008** | 512+160+96+80+64+96 |
| **Phần dư headroom** | **16** | 1.024−1.008 |

**Phần dư 16 MiB/1 GiB là rất mỏng trong nhiều workload thật**, vì các con số dự trù không bao quát mọi biến động, có yếu tố shared pages/page cache/kernel/cgroup khác nhau và không phản ánh peak memory chính xác. **Đừng dùng bảng này như đề xuất cấu hình production.**

### 7.2. Giả sử tăng từ 80 lên 120 platform threads

Khi vẫn dự trù 1 MiB/thread:

| Chỉ tiêu | 80 threads | 120 threads |
| --- | ---: | ---: |
| Stack planning allowance | 80 MiB | 120 MiB |
| Các khoản khác cộng lại | 928 MiB | 928 MiB |
| Tổng planned | 1.008 MiB | 1.048 MiB |
| Cgroup budget | 1.024 MiB | 1.024 MiB |
| Headroom | +16 MiB | **−24 MiB** |

Trong mô hình, cấu hình thứ hai vượt ngân sách dự trù **24 MiB**. Điều đó không **tự chứng minh** JVM sẽ bị OOM kill, vì đây không phải số resident thực tế. Nhưng nó cho thấy **chỉ thay thread count đã làm rủi ro memory tăng đáng kể**, ngay cả khi `-Xmx` giữ nguyên.

### 7.3. “Heap tối đa + 3 giới hạn” không phải tổng OOM chính xác

Không được lấy:

```text
total = -Xmx + -XX:MaxMetaspaceSize
      + -XX:ReservedCodeCacheSize
      + platformThreads * -Xss
```

rồi gọi đó là **“RSS/JVM chính xác”**. Các thành phần trên có thể là **maximum** hoặc **reserved virtual capacity**, không phải committed/resident đồng thời. Ngược lại công thức còn **bỏ sót** direct buffers, GC native memory, symbol/string tables, JIT compiler working memory, runtime libraries, memory-mapped files, page cache, socket buffers và các process phụ.

Bảng budget có ích để xác định **headroom và rủi ro**, nhưng phải được **hiệu chỉnh bằng số liệu peak/steady thực tế**.

### 7.4. Ngưỡng headroom phải căn cứ workload

Không có một tỷ lệ “luôn giữ 20%” được Java SE bảo đảm cho mọi workload. Tùy:
- Tải cực đại và số requests concurrent.
- Số platform threads và native integrations.
- Số dynamic classes/classloaders.
- Warmup JIT và code cache growth.
- Giai đoạn GC, class loading và burst allocations.
- Số process/sidecars cùng cgroup.
- Chính sách page cache, kernel và swap.
- Memory.max, memory.high, memory.swap.max theo Linux runtime.

Một quy trình tốt là đo **p95/p99/peak memory** phù hợp, thiết lập cảnh báo trên cgroup stats và điều chỉnh `-Xmx`/native caps với **khoảng dự phòng được kiểm chứng**. Không hứa rằng áp một tỷ lệ cố định sẽ tránh được mọi loại OOM.

## 8. Java lab độc lập: tính ngân sách Metaspace, Code Cache và stack

### 8.1. Mục đích và giới hạn

Chương trình này **không thử cấp phát tới mức OOM**, không tạo hàng trăm threads và không cần container. Nó tính toán một **mô hình giả lập** với dữ liệu số nguyên MiB để người học thấy:

- Heap 512 MiB không có nghĩa tổng JVM chỉ cần 512 MiB.
- Metaspace, Code Cache, direct buffers và stacks phải có ngân sách.
- Tăng 40 threads có thể tăng stack allowance dự kiến.
- Có thể bị overbudget trong mô hình mà không kết luận RSS đã vượt.
- Input ngân sách âm/zero và arithmetic overflow được từ chối.

**Mã chạy trên JDK 17+**; không cần thư viện bên ngoài, không in số JVM thực tế nên có **25 dòng stdout xác định**.

### 8.2. Tệp `ContainerMemoryBudgetLab.java`

```java
public class ContainerMemoryBudgetLab {
    // Tất cả số trong record là giá trị DỰ TRÙ, đơn vị MiB.
    record Budget(
            long limitMiB,
            long heapMiB,
            long metaspaceMiB,
            long codeCacheMiB,
            long directMiB,
            long otherMiB,
            long platformThreads,
            long stackAllowanceMiB) {

        Budget {
            if (limitMiB <= 0 || heapMiB < 0 || metaspaceMiB < 0
                    || codeCacheMiB < 0 || directMiB < 0
                    || otherMiB < 0 || platformThreads < 0
                    || stackAllowanceMiB < 0) {
                throw new IllegalArgumentException(
                        "invalid planning inputs");
            }
        }

        long stacksMiB() {
            return Math.multiplyExact(
                    platformThreads, stackAllowanceMiB);
        }

        long plannedMiB() {
            long total = 0;
            for (long part : new long[]{
                    heapMiB, metaspaceMiB, codeCacheMiB,
                    directMiB, otherMiB, stacksMiB()}) {
                total = Math.addExact(total, part);
            }
            return total;
        }

        long remainingMiB() {
            return Math.subtractExact(limitMiB, plannedMiB());
        }
    }

    static void rejection(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": false");
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": true");
        }
    }

    public static void main(String[] args) {
        Budget base = new Budget(
                1024, 512, 160, 96, 64, 96, 80, 1);
        Budget crowded = new Budget(
                1024, 512, 160, 96, 64, 96, 120, 1);

        System.out.println(
                "container limit MiB: " + base.limitMiB());
        System.out.println(
                "heap planning MiB: " + base.heapMiB());
        System.out.println(
                "metaspace planning MiB: " + base.metaspaceMiB());
        System.out.println(
                "code cache planning MiB: " + base.codeCacheMiB());
        System.out.println(
                "direct buffers planning MiB: " + base.directMiB());
        System.out.println(
                "other planning MiB: " + base.otherMiB());
        System.out.println(
                "platform threads: " + base.platformThreads());
        System.out.println(
                "stack allowance per platform thread MiB: "
                        + base.stackAllowanceMiB());
        System.out.println(
                "aggregate planned stack MiB: " + base.stacksMiB());
        System.out.println(
                "total planned MiB: " + base.plannedMiB());
        System.out.println(
                "remaining planning MiB: " + base.remainingMiB());
        System.out.println(
                "plan fits within limit: "
                        + (base.remainingMiB() >= 0));

        System.out.println(
                "crowded platform threads: "
                        + crowded.platformThreads());
        System.out.println(
                "crowded planned stack MiB: "
                        + crowded.stacksMiB());
        System.out.println(
                "crowded total planned MiB: "
                        + crowded.plannedMiB());
        System.out.println(
                "crowded over limit MiB: "
                        + Math.max(0, -crowded.remainingMiB()));
        System.out.println(
                "crowded plan fits: "
                        + (crowded.remainingMiB() >= 0));
        System.out.println(
                "extra thread stack allowance MiB: "
                        + (crowded.stacksMiB() - base.stacksMiB()));

        // Các mệnh đề này là GIẢI THÍCH về hợp đồng,
        // không phải OS metrics của máy đang chạy.
        System.out.println("stack allowance equals RSS: false");
        System.out.println(
                "code cache reservation equals RSS: false");
        System.out.println(
                "metaspace cap covers all native memory: false");

        rejection("zero limit rejected",
                () -> new Budget(0, 0, 0, 0, 0, 0, 0, 0));
        rejection("negative threads rejected",
                () -> new Budget(1024, 0, 0, 0, 0, 0, -1, 1));

        try {
            new Budget(
                    Long.MAX_VALUE, 0, 0, 0, 0, 0,
                    Long.MAX_VALUE, 2).plannedMiB();
            System.out.println("arithmetic overflow detected: false");
        } catch (ArithmeticException ex) {
            System.out.println("arithmetic overflow detected: true");
        }

        System.out.println(
                "synthetic planning, not measured RSS: true");
    }
}
```

### 8.3. Biên dịch và chạy

```bash
javac ContainerMemoryBudgetLab.java
java ContainerMemoryBudgetLab
```

### 8.4. Stdout chính xác — 25 dòng

```text
container limit MiB: 1024
heap planning MiB: 512
metaspace planning MiB: 160
code cache planning MiB: 96
direct buffers planning MiB: 64
other planning MiB: 96
platform threads: 80
stack allowance per platform thread MiB: 1
aggregate planned stack MiB: 80
total planned MiB: 1008
remaining planning MiB: 16
plan fits within limit: true
crowded platform threads: 120
crowded planned stack MiB: 120
crowded total planned MiB: 1048
crowded over limit MiB: 24
crowded plan fits: false
extra thread stack allowance MiB: 40
stack allowance equals RSS: false
code cache reservation equals RSS: false
metaspace cap covers all native memory: false
zero limit rejected: true
negative threads rejected: true
arithmetic overflow detected: true
synthetic planning, not measured RSS: true
```

**Đã kiểm tra 25 dòng** với Java hiện đại. Các phép tính từ fixtures cố định nên không phụ thuộc CPU, Docker, JDK vendor hay bộ nhớ của máy bạn.

### 8.5. Giải thích kết quả theo nhóm

**Dòng 1–8:** ngân sách giả định 1 GiB và các khoản dự trù riêng cho heap, Metaspace, Code Cache, direct buffers, “other” và 80 platform threads.

**Dòng 9–12:** 80 threads × 1 MiB = 80 MiB stack allowance; tổng planned 1.008 MiB; headroom 16 MiB; phép kiểm toán học nói tổng dự trù **chưa vượt** hard budget. Điều đó **không** chứng minh OS memory.current sẽ không chạm giới hạn.

**Dòng 13–18:** tăng platform threads từ 80 lên 120 làm stack allowance tăng từ 80 lên 120 MiB; tổng planned thành 1.048 MiB, lớn hơn 1.024 MiB **24 MiB**.

**Dòng 19–21:** nhấn mạnh stack allowance và code cache reservation **không phải số resident chính xác**, còn giới hạn Metaspace không bao trùm toàn bộ native memory.

**Dòng 22–24:** kiểm tra input: limit bằng 0, số threads âm và phép nhân overflow không được chấp nhận. Đây là chính sách của mô hình, không phải Java VM tự ném lỗi khi cấu hình những tình huống đó.

**Dòng 25:** tất cả dữ liệu là **synthetic planning**, không phải kết quả đo HotSpot/JFR/NMT hay Linux cgroup.

## 9. Probe Java thật: các memory pools, buffer pools và thread count

### 9.1. Khi nào cần probe?

`ContainerMemoryBudgetLab` dạy phép tính nhưng không quan sát container. Để lấy dữ liệu từ JVM **đang chạy**, có thể dùng các APIs Java SE:

- `ManagementFactory.getMemoryMXBean()`: heap/nonheap memory usage.
- `ManagementFactory.getMemoryPoolMXBeans()`: các heap/nonheap pools do implementation cung cấp.
- `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`: managed buffer pools, gồm direct buffers khi có.
- `ManagementFactory.getThreadMXBean()`: thống kê số platform threads theo cách MXBean cung cấp.

**Giới hạn:** `MemoryMXBean.getNonHeapMemoryUsage()` không đo **toàn bộ native memory**; thread stacks, native libraries, OS page cache và các phân bổ khác không nhất thiết nằm trong tổng này. Danh sách pool và tên cụ thể phụ thuộc HotSpot/JDK. Không tính tổng memory.current bằng cách cộng các JMX metrics đó.

### 9.2. Ví dụ `JvmMemoryProbe.java`

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.Comparator;
import java.util.Locale;

public class JvmMemoryProbe {
    static String mib(long bytes) {
        return bytes < 0 ? "undefined"
                : String.format(
                        Locale.ROOT, "%.1f",
                        bytes / (1024.0 * 1024.0));
    }

    public static void main(String[] args) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();
        MemoryUsage nonheap =
                ManagementFactory.getMemoryMXBean()
                        .getNonHeapMemoryUsage();

        System.out.println("heap used MiB: "
                + mib(heap.getUsed()));
        System.out.println("heap committed MiB: "
                + mib(heap.getCommitted()));
        System.out.println("heap max MiB: "
                + mib(heap.getMax()));
        System.out.println("nonheap used MiB: "
                + mib(nonheap.getUsed()));
        System.out.println("nonheap committed MiB: "
                + mib(nonheap.getCommitted()));

        ManagementFactory.getMemoryPoolMXBeans().stream()
                .filter(p -> p.getType() == MemoryType.NON_HEAP)
                .sorted(Comparator.comparing(
                        MemoryPoolMXBean::getName))
                .forEach(p -> {
                    MemoryUsage usage = p.getUsage();
                    if (usage != null) {
                        System.out.println("pool " + p.getName()
                                + " used MiB: "
                                + mib(usage.getUsed()));
                    }
                });

        ManagementFactory.getPlatformMXBeans(
                BufferPoolMXBean.class).stream()
                .sorted(Comparator.comparing(
                        BufferPoolMXBean::getName))
                .forEach(p ->
                        System.out.println(
                                "buffer pool " + p.getName()
                                + " memory used MiB: "
                                + mib(p.getMemoryUsed())));

        System.out.println("live platform thread count: "
                + ManagementFactory.getThreadMXBean()
                        .getThreadCount());
    }
}
```

Biên dịch/chạy:

```bash
javac JvmMemoryProbe.java
java JvmMemoryProbe
```

**Không có stdout cố định cho probe này:** pool names, số threads và mức memory tùy JDK/GC/OS/flags. Nó đo **tiến trình probe**, không thể tự đọc toàn bộ memory của một service khác nếu không tích hợp JMX/JFR/JVM diagnostics hoặc chạy code trong chính service đó.

### 9.3. Không dùng một chỉ số thay cho tất cả

Nếu `nonheap used=100 MiB`, không được kết luận:
- “mọi native memory còn lại là 100 MiB”;
- “container limit trừ heap used trừ 100 là headroom an toàn”;
- “80 platform thread stacks đã được tính đủ trong nonheap”;
- “direct-buffer cap của VM bao gồm native allocations của mọi thư viện”.

`MemoryMXBean` là nguồn thuận tiện cho **JVM managed pools**, không phải bộ đo tất cả memory sử dụng bởi kernel/cgroup.

## 10. Chẩn đoán bằng jcmd, Native Memory Tracking và Linux cgroup

### 10.1. Bật NMT ở lúc khởi động

Nếu cần điều tra native memory trên HotSpot:

```bash
java -XX:NativeMemoryTracking=summary \
     -Xmx512m \
     -jar app.jar
```

Trên Bash/sh, dấu `\` cuối dòng dùng nối dòng. Trên PowerShell, hãy đặt lệnh trên một dòng hoặc dùng cách nối riêng. Thay `app.jar` bằng artifact thật.

Theo Oracle JDK 25:
- `NativeMemoryTracking=off` là mặc định.
- `summary` thu thập các nhóm memory VM, như Class, Code, Thread, GC.
- `detail` thêm callsite/virtual memory region chi tiết hơn, overhead có thể cao hơn.
- **NMT phải bật khi JVM bắt đầu**; không thể bật lại hoàn toàn từ trạng thái off chỉ bằng `jcmd`.
- NMT làm tăng overhead; tài liệu Oracle nêu **khoảng 5–10%** trong một số trường hợp. Không bật NMT chỉ ở candidate của một benchmark throughput A/B rồi quy overhead cho app config.

### 10.2. Các lệnh jcmd hữu ích

Với một **PID thật** và quyền attach phù hợp:

```bash
jcmd "$PID" help
jcmd "$PID" VM.flags
jcmd "$PID" VM.metaspace
jcmd "$PID" VM.classloader_stats
jcmd "$PID" Compiler.codecache
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
jcmd "$PID" VM.native_memory summary.diff scale=MB
```

**Các điều kiện quan trọng:**
- `VM.native_memory` chỉ có dữ liệu khi NMT đã bật.
- `baseline` phải chạy trước `summary.diff`; kết quả diff là biến động **kể từ baseline**, không phải tổng hiện tại.
- `jcmd help` giúp xác nhận lệnh có trên JVM/version đó.
- Attach có thể yêu cầu cùng user/quyền, PID namespace hoặc cấu hình container cho phép.
- Một số lệnh có thể gây pause hoặc overhead; tránh chạy trong thời điểm benchmark nhạy cảm nếu chưa biết tác động.

**Không đồng nhất NMT `Thread reserved` với RSS stacks.** NMT có giới hạn coverage và quy tắc báo reserved/committed riêng, đặc biệt với stack/CDS.

### 10.3. NMT không nhìn thấy mọi thứ

Oracle JDK 25 tài liệu hóa rằng NMT theo dõi memory dùng bởi HotSpot JVM **không bao trùm hoàn toàn**:
- Các phân bổ native trong một số **JDK class libraries**.
- Native code của bên thứ ba.
- Toàn bộ dữ liệu memory của **CDS archive**.
- File/page cache và kernel memory do OS hạch toán ở cgroup.

Bởi vậy nếu NMT total khác `memory.current`, đó **không tự chứng minh NMT/JVM sai**. Hai công cụ đo hai phạm vi khác nhau.

### 10.4. cgroup v2: `memory.max`, `memory.current` và events

Trong một Linux container có cgroup v2 mount tại đường dẫn thông dụng:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.peak
```

**Các đường dẫn trên chỉ là ví dụ phổ biến.** Cgroup namespace, mount layout, cgroup membership và mức phân cấp có thể khác; hãy đối chiếu `/proc/self/cgroup`, `/proc/self/mountinfo` và ancestors để xác định đúng phạm vi.

Theo Linux kernel:
- `memory.max` là giới hạn cứng của **cgroup đó**, biểu diễn bằng bytes hoặc `max` nếu không đặt cap tại mức ấy.
- `memory.current` là lượng memory đang được cgroup/descendants sử dụng theo quy tắc controller (bytes).
- `memory.peak` là peak hạch toán; behavior reset có thể khác theo version/kernel và thao tác với file descriptor.
- `memory.high` là ngưỡng pressure/throttling/reclaim, **không phải hard kill limit**.
- `memory.events` gồm counter như `low`, `high`, `max`, `oom` và `oom_kill` (tùy kernel), cần quan sát delta.
- `memory.stat` phân loại anonymous, file cache, kernel/slab, socket buffers, page tables và những khoản liên quan theo kernel.

**Không nói `memory.current` chính xác bằng tổng `-Xmx + MaxMetaspaceSize + ReservedCodeCacheSize + N×Xss`.** Các khoản này khác loại và có shared/mapped/reclaimable pages.

### 10.5. cgroup v1 và Kubernetes

Một số môi trường vẫn dùng cgroup v1, có các file như:
- `memory.limit_in_bytes`.
- `memory.usage_in_bytes`.
- `memory.failcnt` hoặc các cơ chế OOM notification liên quan, tùy controller/kernel.
- Các mount paths controller-specific.

Đây là **compatibility knowledge** để chẩn đoán hệ thống vẫn chạy v1, không phải khuyến nghị triển khai mới theo cách legacy. Trên Kubernetes, cấu hình `resources.limits.memory` thường được đưa thành giới hạn memory của container qua cgroup, nhưng phải xác nhận **runtime thực tế và phạm vi Pod/container**, đặc biệt nếu có sidecars, process khác và cgroup ancestor.

Nếu container bị OOMKilled, hãy thu thập:
- Event/trạng thái Pod và lý do termination từ orchestration.
- `memory.events`/`oom_kill` delta.
- Memory peak, working set và `memory.stat`.
- JVM logs, NMT, JFR/heap metrics trước khi bị kill, nếu có.
- Số platform threads, metaspace/code cache/class count.
- Các native allocations và file-cache/sidecar impact.

Không chỉ nhìn `-Xmx` mà bỏ qua nguyên nhân ngoài heap.

### 10.6. RSS và PSS hỗ trợ gì?

Linux `/proc/<PID>/smaps_rollup` có thể báo:
- `Rss`: resident mappings của process, gồm shared pages có thể bị đếm nhiều lần giữa processes.
- `Pss`: tỷ lệ resident pages được phân bổ theo số mappers.
- `Private_Clean`/`Private_Dirty`: các trang private của process theo kernel.

Khi một node chạy nhiều JVM cùng dùng CDS/AOT archive, tổng RSS có thể **đếm trùng shared mappings**; PSS phù hợp hơn để đánh giá footprint nhiều JVM trong điều kiện có quyền đọc và đủ phạm vi. Nhưng cgroup memory.current còn có kernel/file cache/other process accounting, nên không tự đồng nhất với tổng PSS.

## 11. Phân biệt năm loại lỗi memory phổ biến

| Triệu chứng | Cơ chế thường liên quan | Việc kiểm tra đầu tiên |
| --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | Heap không đủ cho object allocation, hoặc object retention/GC behavior | `-Xmx`, heap used/GC logs/heap dump khi được phép |
| `java.lang.OutOfMemoryError: Metaspace` | Class metadata chạm limit/không cấp thêm được | `VM.metaspace`, `MaxMetaspaceSize`, classloader stats |
| `OutOfMemoryError: unable to create native thread` | Không tạo được OS/platform thread | Thread counts, `pids.max`, OS resource caps, native memory |
| `StackOverflowError` | Call stack của một thread quá sâu | Đệ quy, stack traces, `-Xss` và thuật toán |
| Code cache warning/compilation hạn chế | JIT Code Cache gần đầy/fragmented | `Compiler.codecache`, `ReservedCodeCacheSize`, JIT metrics |
| Container bị OOMKilled / SIGKILL | OS/cgroup không đủ memory theo quy tắc kernel | `memory.events`, `memory.current/peak`, orchestration events, RSS/PSS |

**Một tiến trình có thể bị kernel kill mà không kịp ném `OutOfMemoryError` hay ghi Java stack trace**; cgroup OOM kill diễn ra **bên ngoài logic bắt ngoại lệ của Java**. Exit code thường gặp là 137 trong một số môi trường Docker/Kubernetes sau SIGKILL, nhưng mã exit **không đủ** để kết luận chính xác nguyên nhân nếu không có OS/cgroup evidence.

### 11.1. Khi nào tăng `-Xmx` là phản tác dụng?

Giả sử container có limit 1 GiB, `-Xmx512m`, Metaspace/Code Cache/stacks/direct buffers đã dùng nhiều memory. Tăng `-Xmx` lên 800 MiB có thể làm Java heap ít GC hơn ở một số workload, **nhưng làm giảm headroom native** và tăng rủi ro OOMKilled.

Quy tắc:
1. Xác định lỗi/metric nào chạm giới hạn.
2. Nếu heap thực sự thiếu, cân nhắc điều chỉnh heap hoặc container limit, cùng hướng tối ưu object retention/GC.
3. Nếu Metaspace/Code Cache/threads là nguyên nhân, tăng heap **không sửa được phần đó**.
4. Nếu total cgroup pressure cao, điều chỉnh ngân sách hoặc kiến trúc triển khai sau khi đo.

### 11.2. Khi nào tăng MaxMetaspaceSize?

Có ích khi:
- Workload tạo/tải nhiều class hợp lệ và số class ổn định theo nhu cầu.
- Trần hiện tại thấp hơn nhu cầu thật.
- Container có đủ tổng memory headroom sau thay đổi.

Không tự giải quyết:
- Classloader leak.
- Native library memory leak.
- Heap OOME.
- Quá nhiều OS threads.
- CodeCache full.

Để điều tra classloader leak, so `VM.classloader_stats` qua các giai đoạn hoặc dùng heap/JFR analysis trong môi trường có quyền, quan sát class count và metadata cùng lifecycle.

### 11.3. Khi nào điều chỉnh ReservedCodeCacheSize?

Cân nhắc khi:
- `jcmd Compiler.codecache` cho thấy code heaps gần trần/có áp lực.
- Có cảnh báo code cache full.
- Tác động lên warmup/throughput đã được đo.
- Còn headroom trong container cho việc mở rộng.

Không giảm Code Cache quá thấp chỉ để “có thêm RAM” nếu code JIT cần không gian; dễ làm performance giảm. Ngược lại, tăng không điều kiện dù usage thấp không tạo lợi ích.

### 11.4. Khi nào điều chỉnh `-Xss` hoặc số platform threads?

Nếu có quá nhiều threads:
- Ưu tiên giảm thread pool size không cần thiết.
- Kiểm tra blocking behavior, queueing, concurrency architecture và giới hạn `pids.max`.
- Với I/O nhiều, cân nhắc virtual threads/async design nếu JDK/framework phù hợp.
- Chỉ giảm `-Xss` sau khi xem recursion depth và stack traces; giá trị quá thấp có thể gây `StackOverflowError` ở đường thực thi sâu.
- Đo thread stack reserved/committed và resident, không chọn một con số trên giấy làm “tiết kiệm chắc chắn” về physical RAM.

## 12. Quy trình tuning có đối chứng cho container thật

### 12.1. Bước 1 — Phân định phạm vi

Ghi:
- JDK distribution, feature/update/build và HotSpot flags.
- Container image/OS architecture, libc nếu liên quan, memory controller version.
- `memory.max` (và ancestor limits), `memory.high`, swap policy.
- Heap flags (đặc biệt `-Xmx`, `MaxRAMPercentage`).
- Metaspace/Class Space, Code Cache, stack flags.
- Số platform threads, virtual threads nếu dùng, worker pool sizing.
- Số processes/sidecars cùng cgroup.
- Peak load, traffic/requests, class loading profile.

Không khởi đầu bằng câu “cấu hình JVM nào tối ưu nhất” khi chưa biết metric cần tối ưu: **OOM rate, startup, p99 latency, throughput hay cost/replica**.

### 12.2. Bước 2 — Quan sát baseline

Ít nhất đo:
- Heap used/committed/max và GC pressure.
- Metaspace used/committed, loaded classes/class loaders.
- Code Cache used/committed/capacity.
- Thread count và native memory Thread category.
- Direct buffers nếu liên quan, GC/native subsystem overhead.
- cgroup memory.current/peak và memory.events.
- Process RSS/PSS nếu môi trường hỗ trợ.
- p95/p99 latency, throughput, error rate.

**Đo đúng mốc:** after startup, after warmup, at steady load, at peak/burst, sau nhiều lần hot reload nếu có. Một snapshot đầu `main` không phản ánh warm-state Code Cache và Metaspace.

### 12.3. Bước 3 — Thay đúng một biến

Ví dụ:
- Đổi `-Xmx` từ 512m sang 448m trong cùng 1 GiB container để xem GC/heap pressure vs native headroom, không đồng thời đổi GC, CPU và framework version.
- Giữ `-Xmx` rồi điều chỉnh `MaxMetaspaceSize` nếu có bằng chứng class metadata chạm trần.
- Đổi `ReservedCodeCacheSize` nếu JIT code cache thật sự gần full.
- Giảm worker pool size nếu có quá nhiều platform threads trong workload I/O hay CPU-bound.
- Tăng **container memory limit** nếu tổng nhu cầu đã được xác minh, thay vì chỉ vặn JVM flag để “vượt” cgroup.

Các số chỉ là **ví dụ thí nghiệm**, không phải cấu hình production mặc định được khuyến nghị.

### 12.4. Bước 4 — Lặp và đánh giá

Chạy nhiều trial, kiểm soát:
- Cùng workload và input dataset.
- Cùng JDK/version, GC, số cores, CPU quota/memory limits.
- Cùng warmup, app container image, phụ thuộc bên ngoài.
- Cùng số process/threads và logging overhead.
- Cùng quy tắc lấy mẫu `memory.current`/JFR/NMT/OS.

Một thay đổi được coi là có ích khi:
- Giảm OOM kill hoặc headroom pressure theo mục tiêu.
- Không làm xấu SLO latency/throughput vượt tolerance.
- Không tạo thêm Metaspace/stack/code cache errors.
- Có lợi ích lặp lại vượt noise.

**Không chỉ đọc “RSS thấp hơn một lần” rồi kết luận JVM tối ưu hơn**; file cache, GC timing, CDS shared pages và warmup có thể làm snapshot dao động.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| “`-Xmx=memory.max` là cấu hình an toàn” | Không còn headroom cho native/OS memory | Chừa khoảng dự phòng theo số đo |
| “Metaspace nằm hoàn toàn trong heap” | Class metadata chủ yếu là native memory | Đo NMT Class/Metaspace riêng |
| “Java 10 còn dùng Permanent Generation để chứa metadata” | Không còn áp dụng trên JDK hiện đại | Dùng khái niệm Metaspace |
| “`MetaspaceSize` là hard max” | Là high-water-mark/GC trigger | Dùng `MaxMetaspaceSize` cho cap metadata |
| “Compressed Class Space reserved 1 GiB nghĩa thêm 1 GiB resident ngay” | Virtual reservation != physical usage | Đọc committed/used/OS metrics |
| “Tắt compressed class pointers để tiết kiệm memory” | Uncompressed có thể tốn hơn; flag deprecated JDK25 | Giữ mode hiện đại, đo nhu cầu |
| “`ReservedCodeCacheSize=128m` tức Code Cache resident 128 MiB” | Trần/reserved khác resident | Đọc `Compiler.codecache`/NMT/OS |
| “Code Cache full là Java heap OOME” | Là subsystem JIT code | Kiểm tra compiler/codecache |
| “`-Xss1m` nhân 80 threads là RSS chính xác 80 MiB” | Stack reservation ≠ resident | Dùng làm planning, đo NMT/OS |
| “Mỗi virtual thread có native stack 1 MiB” | Virtual thread stacks nằm trong heap-backed continuations | Phân biệt carriers/virtual |
| “StackOverflowError nghĩa container thiếu RAM” | Thường call stack quá sâu | Điều tra recursion/stack limit |
| “Unable to create native thread nghĩa heap hết” | Có thể native memory hoặc PID/task limit | Xem OS pids, thread count |
| “`MemoryMXBean.getNonHeapMemoryUsage` bằng tất cả native memory” | Không gồm mọi native/OS allocation | Dùng NMT và OS metrics |
| “`jcmd VM.native_memory` bằng memory.current” | Coverage/units khác, có file cache/kernel/native libs | Phối hợp công cụ theo phạm vi |
| “NMT có thể bật bất kỳ lúc nào trên JVM đang chạy” | Phải bật khi startup | Đặt `NativeMemoryTracking` ngay từ đầu |
| “Chỉ bật NMT ở candidate benchmark” | Tăng overhead không cân xứng | Chẩn đoán riêng hoặc bật đều |
| “Chỉ nhìn heap used nhỏ hơn limit là đủ” | Cgroup còn nhiều thành phần khác | Theo dõi `memory.current/peak/events` |
| “Không thấy Java OOME nghĩa không có OOMKill” | Kernel có thể kill từ ngoài JVM | Kiểm tra cgroup/orchestrator |
| “memory.max=max bảo đảm không có limit” | Ancestor/host có thể giới hạn | Kiểm tra hierarchy và quota |
| “Tăng MaxMetaspaceSize sửa mọi classloader leak” | Chỉ trì hoãn khi dữ liệu vẫn tăng | Sửa retention/lifecycle |
| “Đặt Code Cache cực nhỏ luôn giúp tăng available RAM” | Có thể làm JIT bị giới hạn và throughput giảm | Benchmark riêng |
| “Tất cả native memory chỉ là meta+code+stack” | Còn direct/GC/compiler/native libs/shared pages | Lập ngân sách đầy đủ |
| “Một số reserved trong NMT = OOM amount” | Reserved address space khác committed/resident | Chọn metric đúng |
| “Gắn một PSS process thay cho cgroup memory” | Scope khác nhau | Báo rõ process vs container group |

## 14. Bài tập và lời giải

### Bài 1 — Heap cap và hard container limit

**Đề:** Container có `memory.max=1 GiB`, JVM chạy `-Xmx512m`. Có thể khẳng định tổng process memory nhỏ hơn 512 MiB không?

**Đáp án:** Không. `-Xmx` chỉ giới hạn Java heap. Metaspace, JIT Code Cache, platform stacks, direct buffers, GC/native libs và kernel/file cache/other processes còn có thể được cgroup hạch toán.

### Bài 2 — Chức năng Metaspace

**Đề:** Một ứng dụng tạo nhiều class động; vì sao Metaspace tăng dù Java heap used không tăng tương ứng?

**Đáp án:** Metadata của classes dùng native memory trong HotSpot Metaspace. Java heap và class metadata là hai khoản khác nhau. Xem số class/classloaders và class unloading.

### Bài 3 — Cờ Metaspace

**Đề:** `-XX:MetaspaceSize=64m` có đặt trần 64 MiB class metadata không?

**Đáp án:** Không. `MetaspaceSize` là ngưỡng liên quan GC/high-water-mark; `-XX:MaxMetaspaceSize` mới là cờ giới hạn metadata mà HotSpot cung cấp.

### Bài 4 — Compressed Class Space reserved

**Đề:** JDK báo 1 GiB `compressed class space reserved` nhưng cgroup memory.current thấp. Có mâu thuẫn?

**Đáp án:** Không. Reserved là vùng địa chỉ ảo, chưa đồng nghĩa 1 GiB RAM đã committed hoặc resident. Đo used/committed và OS memory.

### Bài 5 — JIT Code Cache

**Đề:** Code Cache báo gần full, ứng dụng chậm hơn khi warmup nhưng heap vẫn còn trống. Có nên tăng `-Xmx` đầu tiên?

**Đáp án:** Không. Quan sát `jcmd Compiler.codecache` và JIT behavior, rồi đánh giá Code Cache size/cấu hình. Tăng heap không giải quyết trực tiếp giới hạn code heap.

### Bài 6 — Chi phí thread stacks

**Đề:** 80 platform threads dự trù 1 MiB/thread, stack allowance là bao nhiêu? Có bằng RSS?

**Đáp án:** 80 MiB theo mô hình hoạch định. **Không** là số RSS chính xác vì virtual reservation và actual touched/resident pages khác nhau.

### Bài 7 — Tăng thread count

**Đề:** Tăng từ 80 lên 120 platform threads, vẫn dự trù 1 MiB/thread. Ngân sách stack thay đổi?

**Đáp án:** Tăng thêm 40 MiB, từ 80 lên 120 MiB. Còn overhead thread structures và native libraries khác.

### Bài 8 — Ngân sách 1 GiB

**Đề:** Dự trù heap 512, metaspace 160, code cache 96, stack 80, direct 64, other 96 MiB. Tổng và headroom?

**Đáp án:** 1.008 MiB, headroom `1024−1008=16 MiB`. Rất mỏng; không dùng làm cam kết production memory an toàn.

### Bài 9 — Khi threads tăng

**Đề:** Các khoản bài 8 giữ nguyên nhưng stack tăng 120 MiB. Ngân sách vượt bao nhiêu?

**Đáp án:** Tổng 1.048 MiB, lớn hơn 1 GiB **24 MiB**. Đó là overbudget theo planning, không tự kết luận OS RSS sẽ tăng đúng 40 MiB.

### Bài 10 — Vì sao `nonheap used` không đủ?

**Đề:** `MemoryMXBean.getNonHeapMemoryUsage` trả 130 MiB; có phải tổng tất cả native memory?

**Đáp án:** Không. Thread stacks, direct buffers/native libs và OS page cache không nhất thiết nằm trong pool được JMX tính. Dùng NMT + OS metrics phù hợp.

### Bài 11 — Native Memory Tracking

**Đề:** Lệnh nào cần thêm từ lúc startup để dùng `jcmd VM.native_memory summary`?

**Đáp án:** Thêm `-XX:NativeMemoryTracking=summary` (hoặc `detail` nếu thực sự cần) khi launch JVM. Theo tài liệu Oracle, không bật NMT mới hoàn toàn bằng `jcmd` trên process đã chạy.

### Bài 12 — NMT so với cgroup

**Đề:** NMT committed thấp hơn `memory.current`. Đây có phải bằng chứng HotSpot đã hạch toán sai?

**Đáp án:** Không đủ. NMT không bao phủ mọi JDK/native libraries/CDS archive; cgroup còn page cache/kernel/other processes. Đọc phạm vi/semantics của từng tool.

### Bài 13 — OutOfMemoryError Metaspace

**Đề:** Một service liên tục hot-reload, class loaders được giữ tham chiếu; có `OOME: Metaspace`. Chỉ tăng MaxMetaspaceSize có sửa gốc không?

**Đáp án:** Thường không. Nó có thể trì hoãn sự cố. Cần điều tra classloader retention, số classes được nạp/unloaded, dynamic proxy generation và vòng đời application/plugin.

### Bài 14 — StackOverflowError

**Đề:** Java gọi đệ quy vô hạn, ném `StackOverflowError`. Có phải Kubernetes đã OOMKill container?

**Đáp án:** Không nhất thiết; đây là lỗi stack của thread. Kiểm tra stack trace, thuật toán/đệ quy, sau đó mới xem OS memory events nếu có bằng chứng khác.

### Bài 15 — Virtual threads

**Đề:** 100.000 virtual threads với `-Xss1m` có dự trù thẳng 100.000 MiB native stacks không?

**Đáp án:** Không. Virtual-thread stacks được lưu trong heap-backed continuations, dùng carrier platform threads khi chạy. Vẫn có footprint trong heap và các overhead khác; không nhân naïve `-Xss` theo virtual-thread count.

### Bài 16 — Kết luận từ cgroup memory.events

**Đề:** JVM chưa log `OutOfMemoryError` nhưng Pod bị báo OOMKilled, `memory.events.oom_kill` tăng. Nên làm gì?

**Đáp án:** Xem OS/cgroup kill, `memory.current/peak/stat`, Pod events, heap/nonheap/NMT đã thu trước đó và native/sidecar usage. Kernel có thể kill trước khi Java ghi OOME; không gán mọi OOMKill là heap leak.

## 15. Checklist triển khai

- [ ] Dùng JDK được hỗ trợ; không mang hướng dẫn PermGen legacy vào Java 10+.
- [ ] Biết từ Java 10 HotSpot hỗ trợ container memory awareness; cgroup vẫn là source of enforcement.
- [ ] Phân biệt `-Xmx` heap limit với total cgroup `memory.max`.
- [ ] Kiểm kê Metaspace, Compressed Class Space, JIT Code Cache và native platform thread stacks.
- [ ] Không cộng `reserved` thành **physical RAM đã dùng**.
- [ ] Hiểu `committed` của VM cũng không luôn bằng process RSS/cgroup current.
- [ ] Dùng `-XX:MaxMetaspaceSize` cho cap metadata; `MetaspaceSize` là GC threshold.
- [ ] Hiểu Compressed Class Space có thể reserve khoảng 1 GiB virtual mà chưa resident 1 GiB.
- [ ] Không khuyên tắt compressed class pointers trong JDK 25 để tối ưu memory.
- [ ] Dùng `-XX:ReservedCodeCacheSize` có chủ đích, kiểm tra `Compiler.codecache`.
- [ ] Đọc Code Cache full như dấu hiệu JIT compilation pressure, không phải Java heap OOME.
- [ ] Dùng `-Xss` và thread count như input planning, **không coi tích là RSS chính xác**.
- [ ] Không nhân native thread stack allowance theo virtual-thread count.
- [ ] Nếu dùng JDK17+ monitor, biết `MemoryMXBean` nonheap không bằng total native memory.
- [ ] Quan sát `VM.metaspace`, `VM.classloader_stats`, `Compiler.codecache` trong phạm vi quyền.
- [ ] Nếu cần NMT, bật từ startup, hiểu overhead và coverage limitations.
- [ ] Không so trực tiếp NMT committed và cgroup memory.current như cùng đại lượng.
- [ ] Đọc đúng cgroup v2 `memory.max`, `memory.current`, `memory.peak`, `memory.stat` và `memory.events`.
- [ ] Xác định cgroup membership/ancestor limits và container sidecars khi cần.
- [ ] Chẩn đoán Java heap OOME, Metaspace OOME, unable native thread, StackOverflowError và cgroup OOMKilled bằng luồng riêng.
- [ ] Khi tính budget, dành headroom từ peak memory measurements chứ không dùng một tỷ lệ bảo đảm chung.
- [ ] Thử `ContainerMemoryBudgetLab.java`, đối chiếu **25 dòng stdout giả lập**.
- [ ] Chạy `JvmMemoryProbe.java` trên ứng dụng thích hợp và chấp nhận output thay đổi theo JDK/workload.
- [ ] Chạy thử nghiệm có đối chứng khi đổi flags, và bảo vệ SLO latency/throughput.

## 16. Kết luận

**Metaspace, JIT Code Cache và stack của platform threads đều là những khoản bộ nhớ cần tính khi một JVM chạy dưới giới hạn RAM của container.** Chúng không được giới hạn chỉ bằng `-Xmx`. Metaspace chứa class metadata và liên quan vòng đời classloaders; Code Cache giữ compiled native code của JIT; platform-thread stacks phụ thuộc số threads, cấu hình `-Xss` và các điều kiện OS. Chúng có các flags và cách giám sát riêng.

Để tránh OOM trong container:
1. Xem **`memory.max` và các ancestor limits** là giới hạn hard ở mức OS.
2. Lập ngân sách **heap + native/nonheap + other processes/kernel/page cache + headroom**, phân biệt con số hoạch định với số resident.
3. Quan sát **JMX/MemoryPoolMXBeans, jcmd/NMT và Linux cgroup metrics** theo đúng phạm vi từng công cụ.
4. Chẩn đoán theo **triệu chứng thực tế** trước khi tăng/giảm `-Xmx`, `MaxMetaspaceSize`, `ReservedCodeCacheSize` hay `-Xss`.
5. Kiểm thử lại ở các giai đoạn startup, warmup và peak load trên JDK còn được hỗ trợ.

Đây là các nguyên tắc **vẫn áp dụng trên Java hiện đại** từ nền tảng container awareness của JDK 10; không dựa vào mô hình Permanent Generation đã bị loại bỏ, không dùng reserved memory như RAM resident và không khuyến nghị các flag cũ không còn phù hợp.

## 17. Tài liệu tham khảo chính thức

- [Oracle JDK 10 Release Notes — Container-Aware JVM](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): JDK-8146115, `UseContainerSupport` và `MaxRAMPercentage` được giới thiệu trong thời kỳ Java 10.
- [Oracle Java SE 25 — Other Considerations: Class Metadata](https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html): Metaspace, class metadata, Compressed Class Space, reserved/committed/used và `MaxMetaspaceSize`.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xmx`, `MaxRAMPercentage`, `MetaspaceSize`, `MaxMetaspaceSize`, `ReservedCodeCacheSize`, `-Xss`, `MaxDirectMemorySize`, `NativeMemoryTracking` và container flags.
- [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): `jcmd VM.native_memory`, NMT off/summary/detail, overhead và giới hạn phạm vi.
- [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): NMT memory categories, phân loại các vấn đề native memory.
- [Oracle Java SE 25 — jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.metaspace`, `VM.classloader_stats`, `Compiler.codecache`, `VM.native_memory`.
- [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): flag `UseCompressedClassPointers` deprecated và compressed class space/reservation.
- [Linux Kernel — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.max`, `memory.current`, `memory.peak`, `memory.high`, `memory.stat` và `memory.events`.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): memory requests/limits, container resource enforcement.
- [Oracle Java SE 25 — MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/nonheap usage và giới hạn API.
- [Oracle Java SE 25 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): pool usage của JVM, type HEAP/NON_HEAP.
- [Oracle Java SE 25 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): managed direct/mapped buffer pools.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): Java 21 virtual threads, khác biệt với native stack theo platform threads.