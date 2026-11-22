# Code cache, luồng biên dịch và chi phí tài nguyên của JIT

## 1. Tổng quan

**Just-in-time (JIT) compilation** cho phép HotSpot JVM biên dịch các phương thức Java bytecode thường được sử dụng thành **native machine code** trong khi chương trình đang chạy. Interpreter có thể bắt đầu thực thi method nhanh mà chưa phải biên dịch tối ưu; sau khi thu thập thông tin về những đoạn code thực sự nóng, JIT tạo native code để cải thiện hiệu năng.

JIT không miễn phí: nó tiêu tốn **CPU trên những compiler threads**, dùng **native memory** cho quá trình biên dịch, cần **code cache** để lưu machine code, có thời gian **warm-up**, và có thể phải **deoptimize/recompile** khi các giả định tối ưu không còn chính xác. Ở ứng dụng lớn, JIT có thể gây áp lực tài nguyên ngay cả khi Java heap chưa đầy hoặc GC hoạt động bình thường.

**Code cache** là vùng bộ nhớ nội bộ của HotSpot để lưu generated machine code và những VM code blobs phù hợp; **khác Java heap, Metaspace, class-file bytecode và run-time constant pool**. Đây là chi tiết implementation của HotSpot, không phải một vùng tên Code Cache được yêu cầu giống nhau trên mọi JVM trong Java Virtual Machine Specification (JVMS).

Học xong bài, bạn có thể:

- Mô tả pipeline **bytecode → interpreter/profiling → compilation queue → C1/C2 compiler threads → compiled nmethod → code cache**.
- Giải thích **tiered compilation levels**, sự khác biệt C1/C2, OSR, inlining, speculative optimization và deoptimization.
- Phân biệt các phân vùng của **segmented code cache**: non-method, profiled methods, non-profiled methods.
- Nêu được nguồn CPU/native memory của compiler threads và tác động lên startup, throughput, latency.
- Hiểu **code cache full**, fragmentation, flushing, sweeping, code unloading và vì sao có thể bị giảm hiệu năng dù Java heap vẫn còn chỗ.
- Hiểu các cờ HotSpot **ReservedCodeCacheSize**, **InitialCodeCacheSize**, **CICompilerCount**, **TieredCompilation**, **TieredStopAtLevel** và những công cụ kiểm tra cấu hình.
- Sử dụng **jcmd Compiler.codecache/queue/codelist**, **PrintCompilation**, **JFR**, **Native Memory Tracking** và benchmark với đúng phạm vi thông tin của từng công cụ.
- Không nhầm **reserved/committed/used**, CPU JIT với CPU application, compiler queue với request queue.

Ví dụ định hướng **HotSpot 64-bit Java 17**, dùng Java 17+ cho các chương trình chạy được. Flags, code-cache layout, thread policy và log formats có thể đổi theo vendor/JDK/platform; đọc JVM cụ thể trước khi kết luận.

## 2. Sơ đồ bytecode đến native code

~~~text
                     javac
  MyCode.java --------------------> MyCode.class
                                       |
                                       | Java bytecode / method metadata
                                       v
                               Class loading/linking
                                       |
                                       v
                                JVM Interpreter
                                       |
                           Invocation/backedge counts
                           Type/branch profiling
                                       |
                                       v
                               Compile Task Queues
                                /             \
                               v               v
                         C1 Compiler       C2 Compiler
                         (faster, tiers)  (optimizing)
                               \               /
                                v             v
                                 Native code
                                 nmethod blobs
                                      |
                                      v
                                   Code Cache
                                      |
                                      v
                          CPU executes compiled code
                                      |
                    assumption invalid / uncommon trap?
                                      v
                              Deoptimization
                              Fallback / Recompile
~~~

Sơ đồ là **mô hình hành vi**, không cam kết method nào cũng đi qua tất cả các bước. Một method có thể chỉ interpreted; một loop có thể được compile bằng **on-stack replacement (OSR)**; một callee có thể được inline thay vì có entry native code độc lập. Những VM stubs phục vụ runtime cũng có thể được lưu trong code cache.

### 2.1. Java class file và code cache khác nhau

| Thành phần | Ý nghĩa | Nơi lưu/quan sát |
| --- | --- | --- |
| **Java source** | Code do người viết chương trình cung cấp | .java |
| **Bytecode** | Instructions portable do javac/compiler ghi | Code attribute trong .class; đọc bằng javap -c |
| **Class metadata** | Tên, fields, methods, constant pool, descriptors và runtime structures | Metaspace/VM structures trong HotSpot |
| **JIT native code** | CPU-specific instructions đã compile từ bytecode | **Code cache** |
| **VM/interpreter stubs** | Generated code phục vụ thực thi/chuyển trạng thái | Code cache theo loại code blob |
| **Java objects/arrays** | Business data/instance state | Java heap |

**javap -c** hiển thị **bytecode**, không phải C2 machine instructions sinh ra sau runtime. Một nmethod trong code cache không phải file .class mới và không có Java source API cho phép dump nó như một Java object.

### 2.2. Code cache khác method area

JVMS §2.5.4 mô tả **method area** ở mức trừu tượng chứa per-class structures và code cho methods/constructors. HotSpot triển khai class metadata và JIT native-code memory bằng nhiều cơ chế riêng. Không suy rằng JVMS bắt buộc mọi JVM có **Metaspace** và **Code Cache** giống HotSpot.

## 3. Tại sao cần compiler threads?

Optimizing compilation có thể rất tốn CPU do:

- Parsing bytecode và xây dựng intermediate representation (IR).
- Control-flow/data-flow analysis và speculative type profiling.
- Inlining, devirtualization, constant propagation.
- Escape analysis, scalar replacement trong các trường hợp phù hợp.
- Loop transformations, range-check elimination và dead-code elimination.
- Instruction selection, scheduling, register allocation.
- Sinh machine code và metadata phục vụ deoptimization/GC/debugging.

Nếu application thread luôn bị buộc chờ compile đầy đủ, response latency sẽ phụ thuộc trực tiếp complexity của method mới. **Background compilation** giúp HotSpot tiếp tục chạy interpreter/compiled version cũ trong khi compiler threads xử lý các requests trong queue.

~~~text
Application Thread A       Application Thread B
  calls hot()                runs requests
       |                          |
       +-- counters/profile       |
               |                  |
               v                  |
          Compile Queue           |
             |                    |
      C1 / C2 CompilerThread      |
             |                    |
       compiled code installed    |
             |                    |
             +-- next hot() calls execute compiled version
~~~

Các compiler threads vẫn thuộc **cùng process JVM**; chúng cần CPU và native stacks, có thể cạnh tranh cache, memory bandwidth và cgroup CPU quota với mutators và GC threads. Background không đồng nghĩa không ảnh hưởng ứng dụng.

### 3.1. Compiler thread không phải javac

**javac** chạy trong build toolchain, tạo bytecode .class. **C1/C2 compiler threads** chạy lúc JVM thực thi ứng dụng để tạo code native cho CPU cụ thể. Biên dịch javac thành công không chứng minh khi runtime JIT đã compile tất cả methods.

### 3.2. Compile task lifecycle

Một hot method muốn chạy bằng JIT code thường phải:

1. Có invocation/backedge counts hoặc profiling information phù hợp.
2. Được compilation policy cho phép và chọn để compile.
3. Vào compilation queue, có mức tier/mode tương ứng.
4. Được một compiler thread chọn để xử lý.
5. Hoàn thành biên dịch không lỗi/không bị bỏ tác vụ.
6. Có code-cache capacity để cài đặt nmethod mới.
7. Được VM dùng như entry point cho lần gọi tương ứng.

**Hot method chưa chắc lập tức compiled**. Nếu CPU quota thấp, queue backlog hoặc code cache full, interpreter/C1 version có thể tiếp tục được dùng lâu hơn.

## 4. Tiered compilation: Level 0 đến Level 4

HotSpot Java 17 thường sử dụng **tiered compilation**, kết hợp interpreter, **C1 (client/compiler1)** và **C2 (server/compiler2)** để cân bằng tốc độ compile và độ tối ưu.

| Level điển hình | Công cụ/thao tác | Vai trò |
| --- | --- | --- |
| **0** | Interpreter | Thực thi bytecode, thu thập counters |
| **1** | C1 code không đầy đủ profiling | Biên dịch nhanh, overhead profile thấp |
| **2** | C1 với limited profiling | Một phần dữ liệu profile |
| **3** | C1 với full profiling | Mã C1 đồng thời tích lũy dữ liệu cho C2 |
| **4** | C2 optimizing compiler | Code tối ưu chuyên sâu cho hot paths |

Đây là mapping của **HotSpot tiered compiler** trong điều kiện phù hợp, **không phải thứ tự bắt buộc 0→1→2→3→4 cho mọi method**. JVM có thể bỏ qua levels, chuyển thẳng một tier theo heuristics hoặc dùng OSR compilation cho loops.

### 4.1. Vì sao không compile C2 mọi thứ ngay từ đầu?

C2 có thể tạo machine code nhanh khi thực thi nhưng tốn đáng kể compile CPU/thời gian/native memory. Một method chỉ chạy hai lần không đáng biên dịch tối ưu tốn 30 ms nếu interpreted execution chỉ cần microseconds.

C1 sinh code sớm với chi phí thấp, tăng warm-up throughput; C2 tập trung vào những methods mà lợi ích lâu dài lớn hơn compile cost.

### 4.2. C1 vs C2 không phải hoàn toàn tách biệt

C1 có thể tạo profiled code, phục vụ loại thông tin mà C2 dựa vào. C2 dùng profiling và assumptions để inline/devirtualize/tối ưu mạnh hơn. Một cùng method có thể được compile ở nhiều tiers trong vòng đời runtime.

### 4.3. TieredStopAtLevel

Ví dụ thử nghiệm:

~~~bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 MyMain
~~~

**MyMain** là main class phải có thật. Giới hạn tier thấp có thể rút ngắn CPU warm-up nhưng làm steady-state throughput kém hơn trên hot methods. Không coi cờ này là khuyến nghị mặc định.

Tắt tiered bằng **-XX:-TieredCompilation** không đồng nghĩa tắt JIT. Trong HotSpot Server VM, non-tiered compiler vẫn có thể chạy. **-Xint** dùng để quan sát interpreter-only execution trong môi trường hỗ trợ; **-Xcomp** ưu tiên compile rất mạnh, có thể tăng startup/resource costs.

## 5. Profile-guided speculative optimization

Giả sử method xử lý interface:

~~~java
// Đoạn minh họa, không phải file chạy độc lập:
long total = 0;
for (Shape shape : shapes) {
    total += shape.area();
}
~~~

Nếu một call site phần lớn thấy implementation Circle, C2 có thể sử dụng profile để tối ưu đường gọi, thậm chí inline các thao tác của Circle với runtime guards. Về sau xuất hiện một shape implementation mới làm giả định type profile không còn phù hợp, JVM phải bảo toàn semantics, có thể **deoptimize và recompile**.

### 5.1. Inlining: lợi và hại

Inlining giúp bỏ call overhead và tạo cơ hội optimization xuyên method boundary. Nhưng nhúng code của nhiều callees vào caller có thể làm compiled code lớn, tăng:

- Thời gian biên dịch.
- Native code-cache occupation.
- Instruction cache/iTLB pressure.
- Chi phí deoptimization metadata.
- Register pressure ở một số paths.

Vì vậy inlining được HotSpot kiểm soát bằng heuristics/cost models; “inline tất cả methods” không phải luôn tốt.

### 5.2. Deoptimization không nhất thiết là lỗi

Compiled code dựa trên những assumptions có thể bị invalidated do class loading, uncommon control flow hoặc thông tin runtime khác. VM chuyển về trạng thái ít tối ưu/interpret rồi compile lại nếu cần.

~~~text
Optimized nmethod
      |
      +-- assumption invalidated / uncommon trap
                 |
                 v
              Deopt
                 |
           fallback execution
                 |
          more profile data
                 |
             Recompile
~~~

Điều này giữ đúng Java semantics. Một vài deopts sau warm-up là bình thường; nếu xảy ra liên tục cùng workload có thể làm code cache churn/CPU compiler tăng.

### 5.3. Vì sao một method có nhiều compiled versions?

Cùng method có thể có C1 profiled nmethod, C2 optimized nmethod, một hoặc nhiều OSR versions và bản cũ marked not entrant. Mã callee còn có thể được inline trong caller, nên **số nmethods không bằng số methods trong source**.

## 6. On-Stack Replacement (OSR)

Một method có vòng lặp dài có thể nóng **trước khi method return lần đầu**. **OSR** cho phép HotSpot chuyển việc thực thi giữa interpreted/C1 và một compiled version tại một điểm thích hợp trong loop.

~~~java
long value = 0;
for (int i = 0; i < 10_000_000; i++) {
    value += i % 7;
}
~~~

Backedge counters có thể vượt threshold khi method còn đang ở trong loop. VM có thể yêu cầu OSR compilation, nhưng không bảo đảm mọi lần chạy source trên đều có OSR: JIT heuristics, method size, CPU, compile queue, flags và optimizations có thể thay đổi.

**-XX:+PrintCompilation** đôi khi hiển thị OSR markers; không dựa vào một compilation ID/hàng log cố định. Phân biệt **OSR compiled version** với **regular method-entry compiled version**.

## 7. Code cache lưu cái gì?

**Code cache** là vùng HotSpot quản lý để lưu các **code blobs**, ví dụ:

- Nmethods chứa machine instructions do C1/C2 sinh.
- Runtime stubs/adapters.
- Một số generated code cho interpreter/transition paths.
- Metadata đi kèm compiled code phục vụ execution, GC và deoptimization.

Code cache thường là native memory với những yêu cầu bảo vệ trang thực thi (executable mappings), không phải Java byte[] hay String trong managed heap.

~~~text
HotSpot process
  Java Heap       -> objects, arrays
  Metaspace       -> class/method metadata
  Code Cache      -> executable compiled code / VM stubs
  Compiler Memory -> IR graphs, temporary buffers, arenas
  Thread Stacks   -> compiler/application/VM thread execution
  GC Native Mem   -> collector data structures
  Other Native    -> libraries, direct buffers, VM internals
~~~

### 7.1. Reserved, committed, used, free

Đây là các kích thước cần tách:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Reserved** | Virtual address space dành cho code cache |
| **Committed** | Các pages đã được commit theo cơ chế VM/OS |
| **Used** | Space do active code blobs và metadata liên quan chiếm |
| **Free** | Capacity còn dùng được theo allocator/code heap |
| **Fragmented free** | Space trống chia thành nhiều blocks, có thể khó cấp cho một code blob lớn |

Nếu Code Cache có **reserved=240 MiB** và **committed=40 MiB**, không được nói cache đã dùng 240 MiB RAM vật lý. Virtual reservation, committed memory và process RSS là các metrics khác nhau.

### 7.2. Code cache khác instruction cache CPU

**Code cache** do JVM quản lý trong virtual memory. **CPU instruction cache (I-cache)** là phần cứng lưu cache lines instructions khi CPU fetch; **iTLB** lưu translations cho virtual instruction addresses.

JEP 197 nói segmentation có thể cải thiện instruction cache/iTLB locality; không có nghĩa JVM code cache và CPU L1 I-cache là cùng một vùng bộ nhớ.

## 8. Segmented Code Cache: ba nhóm trong JDK 17

**OpenJDK JEP 197 — Segmented Code Cache** tách cache thành ba code heaps với lifetime/usage khác nhau:

| Code heap | Loại code | Ý nghĩa |
| --- | --- | --- |
| **Non-method** | VM-generated stubs, interpreter/adapter code và loại non-nmethod | Thường giữ lâu, khó reclaim bằng nmethod sweeper thông thường |
| **Profiled method** | Methods compiled có profiling, thường là một số C1 tiers | Nhiều mã có thể bị thay bởi tier cao sau warm-up |
| **Non-profiled method** | Methods không dùng profiling ở code version hiện tại, thường C2 optimized và C1 non-profiled tùy mode | Tập trung code hữu ích lâu, locality quan trọng |

~~~text
                 Reserved Code Cache
+-------------------------------------------------------+
|                                                       |
|  +--------------+ +---------------+ +--------------+ |
|  | Non-method   | | Profiled      | | Non-profiled | |
|  | stubs/runtime| | C1 profiled   | | optimized    | |
|  +--------------+ +---------------+ +--------------+ |
|                                                       |
+-------------------------------------------------------+
~~~

**Không** đồng nhất profiled heap với mọi C1 nmethod: C1 level 1 có thể là non-profiled code. Không hứa mọi code blob có lifetime cố định theo màu ô trên sơ đồ.

### 8.1. Tại sao phân vùng?

- Giảm fragmentation khi compiled methods ngắn hạn được thay/loại bỏ.
- Tách loại non-method không thể tùy tiện quét bỏ.
- Giảm một số chi phí scanning/code sweeper.
- Cải thiện locality của compiled hot code đối với CPU instruction cache.
- Giúp quản lý budget code heap theo types.

Theo tài liệu Java 17, **SegmentedCodeCache** được bật mặc định khi **TieredCompilation** bật và **ReservedCodeCacheSize từ 240 MB trở lên**, trong cấu hình hỗ trợ. Nếu thay flags, cần kiểm tra trạng thái thực.

### 8.2. Các code heap không nhất thiết được chia đều

Các flags HotSpot liên quan gồm:

- **NonNMethodCodeHeapSize**.
- **ProfiledCodeHeapSize**.
- **NonProfiledCodeHeapSize**.
- **ReservedCodeCacheSize**.

Kích thước có giới hạn và alignment; cấu hình cho từng segment tùy version/ergonomics. **Không giả định 240 MB chia thành ba phần bằng nhau**; phải quan sát final flags/jcmd.

### 8.3. Segmentation không loại bỏ cạn chỗ

Một heap cụ thể có thể thiếu space hoặc bị fragmentation ngay cả khi những heaps khác còn capacity. Có những VM stubs bắt buộc cần được cấp phát, nên cache exhaustion ở non-method segment có thể gây hậu quả nghiêm trọng hơn một nmethod optimized không được cài đặt.

## 9. Nmethod: vòng đời native code

Nmethod đại diện cho compiled Java method code/OSR code trong HotSpot, kèm metadata để GC/deoptimization/runtime có thể quản lý an toàn.

~~~text
Compile request
     |
     v
Compiled nmethod installed
     |
     v
Entrant (new invocations may execute)
     |
     +-- hot tier recompilation / OSR version
     |
     +-- invalid assumption / deoptimization
     |
     v
Not-entrant / obsolete
     |
     | runtime ensures no unsafe active use
     v
Reclaimed by sweeper/unloading when safe
~~~

HotSpot có các trạng thái nội bộ như **in_use**, **not_entrant**, **zombie** và **unloaded** theo version. Đây **không phải Java object states** và không tương đương Young/Old GC generations.

### 9.1. Không xóa code cũ ngay lập tức

Một Java thread có thể đang thực thi compiled frame trong nmethod cũ khi VM quyết định không dùng version ấy cho calls mới. Nếu giải phóng machine code ngay sẽ phá memory safety. VM cần cơ chế an toàn để deopt/finish stack frames và reclaim khi không còn được sử dụng.

### 9.2. Nmethod sweeper/code cache flushing

HotSpot có **nmethod sweeper** và cơ chế **code cache flushing** để thu hồi cold/obsolete nmethods khi an toàn. Flag **UseCodeCacheFlushing** có liên quan trên JDK hỗ trợ. Không nên tắt nó chỉ để “giữ mã tối ưu mãi mãi”: như thế có thể tăng code cache pressure.

**Không được suy:** GC heap vừa chạy thì compiled nmethods cũ chắc chắn được xóa ngay. Class unloading, code unloading/sweeping và Java heap reclamation có liên quan nhưng không phải cùng sự kiện hay tài nguyên.

## 10. Khi code cache đầy

Một số HotSpot versions có thể ghi warning dạng:

~~~text
CodeCache is full. Compiler has been disabled.
Try increasing the code cache size using -XX:ReservedCodeCacheSize=
~~~

Đây chỉ là **dạng thông điệp minh họa**, không phải khẳng định mọi JDK báo y hệt hay compiler luôn disabled vĩnh viễn.

Những biểu hiện có thể xuất hiện:

- Compile task bị bỏ hoặc không cài đặt được nmethod mới.
- Java methods vẫn chạy bằng interpreter/C1 thay vì tier tối ưu.
- Application throughput giảm dù số requests không tăng.
- CPU có thể tăng vì code chạy ở tier thấp.
- p99 latency tăng sau một thời gian chạy, đặc biệt khi nhiều methods mới được gọi.
- Sweeper/code flushing có thể reclaim chỗ và JVM có thể phục hồi compilation theo chính sách thực tế.

**Code cache full không nhất thiết gây Java heap OutOfMemoryError.** Đôi khi ứng dụng tiếp tục phục vụ traffic nhưng chậm đi, khiến sự cố khó phát hiện nếu chỉ nhìn heap metrics.

### 10.1. Tại sao free bytes dương vẫn không đủ?

Một code blob cần đoạn space phù hợp về size/alignment và code heap type. Khi fragmentation hoặc một segment đã cạn, tổng free của cả cache không bảo đảm cấp được blob. Cần đọc **per-code-heap used/free/fragmentation** thay vì chỉ tổng cache.

### 10.2. Tại sao tăng Xmx không chữa?

- **-Xmx** giới hạn Java heap object memory.
- **ReservedCodeCacheSize** liên quan code cache.
- **Metaspace** liên quan nhiều loại class metadata.
- **CICompilerCount** ảnh hưởng compiler threads/native stacks.
- Container RSS là tổng kết quả từ các vùng và OS accounting.

Tăng -Xmx không tự cấp thêm chỗ cho nmethods. Thậm chí tăng heap quá nhiều trong container có thể làm ngân sách native nhỏ hơn.

## 11. ReservedCodeCacheSize và InitialCodeCacheSize

Hai tùy chọn JDK17:

- **-XX:ReservedCodeCacheSize=<size>**: định cấu hình maximum/reserved code cache budget.
- **-XX:InitialCodeCacheSize=<size>**: định cấu hình initial code cache size/commit theo implementation.

Theo Oracle Java 17 manual, code cache mặc định thông dụng có **ReservedCodeCacheSize=240 MB** với tiered compilation; khi **-XX:-TieredCompilation**, default tương ứng được tài liệu mô tả là **48 MB**. Manual JDK17 còn nêu giới hạn code cache reservation 2 GB. Các default/giới hạn này **là thông tin theo phiên bản**, không phải định luật xuyên JDK 11–26.

Ví dụ:

~~~bash
java -XX:ReservedCodeCacheSize=128m -XX:+PrintFlagsFinal -version
~~~

Cấu hình quá nhỏ hoặc mâu thuẫn kích thước segmented heaps có thể bị JVM từ chối. Nếu tăng cache để thử nghiệm, phải đo thực tế đã hết chỗ chưa, không đặt giá trị tùy ý chỉ vì ứng dụng có nhiều classes.

### 11.1. Reserved không phải committed

Giả sử code cache:

~~~text
Reserved:  240 MiB
Committed:  48 MiB
Used:       35 MiB
Free committed: 13 MiB (đơn giản hóa)
~~~

Các con số chỉ minh họa. Reserved thường là vùng virtual address space; committed là phần có OS backing/commit; used là space của code. RSS còn phụ thuộc mapping/physical pages touched. Không cộng reserved vào used Java heap rồi báo “process đang ăn từng ấy RAM”.

## 12. Chi phí CPU của compilation threads

C1/C2 compiler threads tiêu thụ cycles, CPU cache, memory bandwidth và có thể cạnh tranh với:

- HTTP worker threads.
- GC threads.
- Database client/event loop threads.
- JFR/profiling/monitoring threads.
- OS scheduler trên CPU quota nhỏ.

Ví dụ một container có **2 vCPU quota**, JVM có vài compiler threads cùng C1/C2 tasks: load cao khi warm-up có thể khiến request threads không được scheduler cấp CPU đúng lúc.

### 12.1. CICompilerCount

**-XX:CICompilerCount=<n>** điều chỉnh số compiler threads theo khả năng và các ràng buộc HotSpot. JVM có thể chọn số dựa trên CPU ergonomics/tiered policy.

Thử kiểm tra:

~~~bash
java -XX:CICompilerCount=2 -XX:+PrintFlagsFinal -version
~~~

Đừng suy compiler throughput tỷ lệ tuyến tính với threads: contention, queue mix, native memory, thread stacks và compiler IR allocations có thể giới hạn. Tăng threads có thể làm JIT nhanh hơn nhưng khiến service latency xấu do CPU bị tranh chấp. Giảm quá mạnh có thể kéo dài warm-up.

### 12.2. BackgroundCompilation

Thông thường HotSpot compile ở background. Các tùy chọn thay đổi foreground/background compilation nên được dùng cho nghiên cứu hơn là tối ưu mặc định; nếu buộc mutator chờ compiler, có thể thêm latency lớn vào request path.

### 12.3. Compile queue

~~~text
Hot methods create compilation requests
               |
               v
        Pending Compile Tasks
               |
        C1/C2 CompilerThreads
               |
               v
      Compiled code installation
~~~

Nếu arrival rate của tasks > service rate, queue tăng, hot methods có thể chạy ở interpreted/C1 tier lâu hơn. Queue dài tạm thời trong startup không nhất thiết là lỗi; queue dài mãi ở steady state cùng compiler CPU saturation là tín hiệu cần điều tra.

Một **compiler queue** không phải **HTTP request queue**: request thường không được chuyển thành compile task trực tiếp rồi chờ. Ảnh hưởng performance có thể gián tiếp qua code chưa tối ưu và CPU contention.

## 13. Native memory: compiler, code và những vùng khác

| Native/resource group | Có gì? | Điều cần tránh |
| --- | --- | --- |
| **Code cache** | Machine instructions, nmethods, stubs | Đừng gọi là Java heap |
| **Compiler arenas** | IR graphs, temporary buffers, optimizer data | Không tính trực tiếp bằng used code-cache |
| **Thread stacks** | CompilerThread C1/C2 stacks | Không tính trong live Java object graph |
| **Profiling metadata** | Method profiles, counters, receiver data | Không đồng nghĩa mọi data ở code-cache memory |
| **Compilation queues** | Tasks và bookkeeping | Không phải Java request queues |
| **Metaspace** | Runtime class/method metadata | Không phải toàn bộ native compiler allocation |
| **Java heap** | Java objects/arrays | Không tự cấp thêm code cache qua Xmx |

Một service có -Xmx=2g vẫn có thể tiêu thụ nhiều hơn 2 GiB process memory vì code cache, class metadata, stacks, direct buffers và GC overhead. Khi chạy trong container, cần giữ native memory headroom bên cạnh heap max.

### 13.1. Chi phí biên dịch đổi lấy lợi ích lâu dài

Một compilation task tốn vài chục milliseconds CPU có thể đáng giá nếu method chạy hàng triệu lần và tiết kiệm nhiều cycles mỗi invocation. Nhưng nếu method chỉ chạy vài lần, code cache và compiler resources có thể lớn hơn lợi ích.

Đó là lý do compilation thresholds và tiered heuristics cần tồn tại. Không ép JVM “compile mọi thứ” để đảm bảo performance.

## 14. Warm-up và steady-state

~~~text
Startup:
  Class loading / init
  Interpreter + initial profiles
  Many C1 requests
  C2 requests for increasingly hot methods
  Code cache occupancy grows

Warm/steady state:
  Most hot paths compiled when beneficial
  Queue may mostly drain
  Deopt/recompile may continue after workload changes
~~~

Warm-up không phải lúc nào kết thúc tại một thời điểm cố định. Workload thay đổi, new class loaders, generated proxies, uncommon traps có thể sinh tasks mới sau hàng giờ.

**Benchmark startup khác steady-state**: chạy microbenchmark 500 ms có thể chủ yếu đo interpreter/C1, trong khi production hot paths sau 30 phút là C2.

### 14.1. JMH và lỗi đo JIT

Tự đo System.nanoTime quanh một loop rồi in kết quả không tự đảm bảo benchmark chính xác. JIT có thể constant-fold, dead-code-eliminate, inline hoặc scalar-replace code. Dùng **JMH** khi benchmark micro-level cần warm-up/forks/blackhole chuẩn, và dùng load test với realistic data để đánh giá service.

## 15. Demo Java 17+ số 1: hot loop, kết quả độc lập JIT

Tạo **JitWarmupDemo.java**:

~~~java
public class JitWarmupDemo {
    static long hotSum(int limit) {
        long total = 0;
        for (int i = 0; i < limit; i++) {
            total += i % 7;
        }
        return total;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int round = 0; round < 20; round++) {
            checksum += hotSum(100_000);
        }

        System.out.println("checksum=" + checksum);
        System.out.println("sameResult=true");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 JitWarmupDemo.java
java JitWarmupDemo
~~~

**Stdout của chương trình:**

~~~text
checksum=5999900
sameResult=true
~~~

Lý do: mỗi nhóm 7 số i%7 có tổng 21. Trong 100.000 iterations có 14.285 nhóm trọn vẹn và 5 phần dư 0+1+2+3+4. Tổng hotSum là **299.995**; gọi 20 lần thành **5.999.900**.

Nếu chạy interpreter:

~~~bash
java -Xint JitWarmupDemo
~~~

Kết quả Java-level phải giống. Nhưng running time có thể khác nhiều; chương trình quá ngắn để quyết định collector/JIT option production.

### 15.1. Bật PrintCompilation

~~~bash
java -XX:+PrintCompilation JitWarmupDemo
~~~

Diagnostic compiler log có thể xen với stdout application. Compile IDs, compiler levels, OSR markers và timings **không cố định** giữa các máy/lần chạy/JDK. Không được coi một log bất kỳ là expected stdout chuẩn.

### 15.2. Giới hạn C1 tier để thử nghiệm

~~~bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 JitWarmupDemo
~~~

Application checksum vẫn 5999900 khi hoàn thành; pipeline JIT có thể khác. **-XX:-TieredCompilation** không đồng nghĩa **-Xint**; muốn tránh JIT trong thí nghiệm so interpreter, dùng -Xint.

## 16. Demo Java 17+ số 2: giữ JVM sống để chạy jcmd

Tạo **CodeCacheTarget.java**:

~~~java
public class CodeCacheTarget {
    static volatile long sink;

    static long work(int value) {
        long x = value;
        for (int i = 0; i < 10_000; i++) {
            x = (x * 31 + i) & 0x7fff_ffffL;
        }
        return x;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("ready");
        for (int round = 0; round < 2_000; round++) {
            sink = work(round);
            Thread.sleep(10);
        }
        System.out.println("completed");
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 CodeCacheTarget.java
java -XX:+TieredCompilation CodeCacheTarget
~~~

**Stdout khi ứng dụng hoàn thành bình thường:**

~~~text
ready
completed
~~~

Trong lúc chương trình chạy, mở terminal khác:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.codelist
~~~

Thay **<PID>** bằng PID thực. jcmd chỉ attach được khi JVM vẫn còn chạy và quyền phù hợp. Các lệnh **Compiler.codecache**, **Compiler.queue**, **Compiler.codelist** có trong tài liệu jcmd Java 17 cho HotSpot; mức độ output và names phụ thuộc build.

### 16.1. Compiler.codecache

In code-cache layout/bounds và thông tin usage. Với segmented mode, dùng nó để phân biệt code heaps thay vì chỉ quan sát Java heap.

### 16.2. Compiler.queue

Cho biết compilation requests đang chờ xử lý tại thời điểm xem. Queue trống không có nghĩa chưa từng JIT compile; tasks có thể đã hoàn tất.

### 16.3. Compiler.codelist

Liệt kê compiled methods đang sống trong code cache theo tool. Một method có thể có nhiều compiled versions, nhiều Java methods chưa từng được JIT compile; không dùng count này như số source methods.

### 16.4. CodeHeap Analytics

Một số HotSpot builds có **Compiler.CodeHeap_Analytics**. Kiểm tra:

~~~bash
jcmd <PID> help
jcmd <PID> help Compiler.CodeHeap_Analytics
~~~

Khi command có mặt, có thể xem thống kê fragmentation, method space/code heap. Không giả định nó luôn khả dụng trên mọi JDK vendor hoặc có cùng subcommands.

## 17. Dùng compiler logs và PrintInlining

HotSpot hỗ trợ:

~~~bash
java -XX:+PrintCompilation JitWarmupDemo
~~~

Với diagnostic options:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining JitWarmupDemo
~~~

Thông tin hữu ích:

- Compilation IDs và tier.
- OSR vs regular compilation.
- Các phương thức được compile.
- Các quyết định inline thành công/không.
- Khi nmethod made not entrant.
- Compile task load trong warm-up.

Nhưng **-XX:+PrintInlining** có thể tạo output lớn và tăng overhead. Không bật tràn lan production nếu chưa quản lý log volume.

### 17.1. Unified JVM Logging

~~~bash
java -Xlog:help
~~~

Nếu tag codecache được JVM hỗ trợ:

~~~bash
java -Xlog:codecache=debug JitWarmupDemo
~~~

Bản JDK có thể khác về tag names và mức chi tiết, nên kiểm tra -Xlog:help trước. Đừng chế log format cố định cho codecache ở mọi HotSpot release.

## 18. Dùng CompilationMXBean

Java SE có **java.lang.management.CompilationMXBean**; bean có thể cho compiler name và aggregate compilation time khi JVM hỗ trợ.

Tạo **CompilerBeanDemo.java**:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;

public class CompilerBeanDemo {
    public static void main(String[] args) {
        CompilationMXBean bean =
                ManagementFactory.getCompilationMXBean();

        System.out.println("beanPresent=" + (bean != null));

        if (bean != null) {
            System.out.println("compiler=" + bean.getName());
            System.out.println("timeSupported="
                    + bean.isCompilationTimeMonitoringSupported());
            if (bean.isCompilationTimeMonitoringSupported()) {
                System.out.println("totalCompileMs="
                        + bean.getTotalCompilationTime());
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 CompilerBeanDemo.java
java CompilerBeanDemo
~~~

**Không có stdout đầy đủ cố định**: compiler name và totalCompileMs phụ thuộc JVM/time; bean có thể null khi compiler facility không có, time monitoring có thể không được hỗ trợ. Đây là ví dụ quan sát API, không nên bịa một expected result.

## 19. JFR và Native Memory Tracking

### 19.1. Java Flight Recorder

**JFR** có thể cung cấp compilation events, compiler statistics và CPU/thread observations khi recording settings bật các events tương ứng.

~~~bash
java -XX:StartFlightRecording=filename=jit-lab.jfr,duration=20s,settings=profile CodeCacheTarget
~~~

Khi có recording:

~~~bash
jfr summary jit-lab.jfr
jfr print --events jdk.Compilation jit-lab.jfr
~~~

Không có jdk.Compilation event **không đồng nghĩa JIT đã tắt**: sự kiện có thể chưa bật hoặc không xuất hiện trong khoảng recording. JFR và PrintCompilation trả lời những câu hỏi khác nhau; để xem code cache hiện tại dùng jcmd Compiler.codecache.

### 19.2. Native Memory Tracking (NMT)

Trên HotSpot Java 17:

~~~bash
java -XX:NativeMemoryTracking=summary CodeCacheTarget
~~~

Từ terminal khác:

~~~bash
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff
~~~

NMT thường phải bật từ JVM startup và có overhead. Các categories có thể gồm **Code**, **Compiler**, **Thread**, **Class**, **GC**. Không gộp category Code thành cả Java heap, và không suy mọi compiler IR memory nằm trong Code category.

Ví dụ minh họa:

~~~text
Code:
  reserved: 240 MiB
  committed: 35 MiB

Compiler:
  committed: 8 MiB
~~~

Các số chỉ là giả định, không phải log thật. Chúng nhấn mạnh cần nhìn **reserved vs committed** và native allocations ngoài Java heap.

## 20. Sự cố code cache full

Một tình huống có thể:

~~~text
Startup -> many methods get compiled
After warmup -> C2 code cache grows
After redeploy -> more generated proxies/classes
Code cache near capacity -> sweeper cannot keep up
Log warns: code cache full
Compiler stops installing optimized code
Application throughput declines
~~~

Lúc này:

1. Xác nhận **code cache full** qua log/jcmd.
2. Phân biệt **which code heap** đầy nếu segmented.
3. Đo **code cache committed/used/free** và fragmentation.
4. Kiểm tra **Compiler.queue** có backlog không.
5. Dùng JFR/PrintCompilation xem compilation churn/deopts/OSR.
6. Xem **generated classes**, dynamic proxies, lambdas và application redeploy.
7. Kiểm tra class-loader retention/unloading.
8. Kiểm tra ReservedCodeCacheSize và per-heap sizing thực.
9. Đo process RSS, NMT Code/Compiler, CPU quota.
10. Chỉ sau đó mới tăng cache budget hoặc thay compile policy.

### 20.1. Không chỉ tăng CodeCache vô hạn

- Cache quá nhỏ có thể đầy, nhưng cache quá lớn không tự làm compiler nhanh hơn.
- Native memory budget hữu hạn; tăng code-cache capacity có thể tăng memory usage của JVM.
- Nếu problem là high compiler CPU/queue, tăng cache không giải quyết task service rate.
- Nếu class generation liên tục, phải sửa root cause.
- Nếu code heap fragmentation/coarsening, cần xem phân vùng và sweeper activity.

### 20.2. Code cache đầy không đồng nghĩa OOME Java heap

JVM có thể tiếp tục interpreted execution/C1 code, tạo **performance degradation** thay vì ném Java heap space OOME. Native-code allocation failure trong một số điều kiện có thể nghiêm trọng hơn; luôn dựa vào thông báo và trạng thái tiến trình thực.

## 21. Compiler CPU cao và warm-up lâu

Một service mới startup có thể:

- CPU process tăng do C1/C2.
- Latency dao động trong warm-up.
- Code cache usage tăng nhanh rồi ổn định.
- Compiler.queue đông một thời gian.
- Sau khi hot methods compiled, throughput cải thiện.

Đây thường là hiệu ứng bình thường. Dấu hiệu đáng quan tâm là **compiler CPU tiếp tục cao trong steady state** do code churn, class generation, deoptimization/recompilation liên tục, hoặc tasks cực lớn.

Một số hướng:

- Warm-up representative traffic trong staging trước khi nhận full load.
- Đo CPU quotas trên container thực.
- So sánh compilation queue snapshots trước/sau warm-up.
- Không ép mọi method C2 ngay khi load.
- Cân nhắc TieredStopAtLevel cho short-lived workloads **sau benchmark**.
- Không giảm CICompilerCount ngay khi compiler threads xuất hiện trên CPU profiler.

## 22. Chi phí deoptimization và code churn

Một hệ framework tạo classes/proxies liên tục hoặc trải qua sự thay đổi runtime type profiles có thể gây:

~~~text
Profile -> Compile C2 -> Assumption changes
          |
          v
       Deopt
          |
          v
    Recompile new nmethod
          |
          v
    Old code becomes not entrant
          |
          v
     Sweeper later reclaims
~~~

Nhiều versions sống chồng nhau có thể tăng code cache occupancy và compiler CPU. Một vài deopts là bình thường; chuỗi lặp không dứt mới đáng phân tích.

**Không gán mọi code cache growth cho memory leak**. Cache thường tăng trong warm-up rồi đạt plateau. Muốn chẩn đoán leak/churn cần observe trend, live compiled code, cache pressure và class-loader lifetime.

## 23. Các hiểu lầm cần tránh

1. **“Code cache là Java heap.”** Sai: đây là HotSpot native/generated code memory.
2. **“JVMS bắt buộc mọi JVM có code cache giống HotSpot.”** Sai.
3. **“JIT compilation không tốn CPU vì chạy background.”** Sai: compiler threads dùng CPU thật.
4. **“Compiler threads chính là javac.”** Sai: javac compile trước runtime; C1/C2 compile trong runtime.
5. **“Mọi method đều được C2 compile.”** Sai: hotness/heuristics/resources quyết định.
6. **“Tiered là lúc nào cũng 0→1→2→3→4.”** Sai: policy có shortcuts.
7. **“Tắt TieredCompilation là tắt JIT.”** Sai: dùng -Xint để thử interpreted mode.
8. **“C1 code luôn ở profiled heap.”** Sai: còn non-profiled C1 tiers.
9. **“Code cache có ba phần kích thước bằng nhau.”** Sai: sizing theo flags/ergonomics.
10. **“Inlining luôn làm code nhỏ hơn.”** Sai: có thể tăng code cache footprint.
11. **“Một Java method bằng một nmethod.”** Sai: OSR/tiered/recompilation/inlining.
12. **“Deoptimization chứng minh có JVM bug.”** Sai: thường bảo toàn speculative assumptions.
13. **“nmethod bị not entrant thì bytes được xóa tức thì.”** Sai: an toàn compiled frames/sweeper.
14. **“GC heap xong thì code cache phải giảm.”** Sai: lifecycle khác nhau.
15. **“Code cache đầy luôn ném OutOfMemoryError ngay.”** Sai: có thể compiler disabled và interpreter fallback.
16. **“Tăng Xmx là tăng ReservedCodeCacheSize.”** Sai: hai budgets khác.
17. **“Reserved 240 MiB là 240 MiB RSS đang dùng.”** Sai: reserved, committed, used khác nhau.
18. **“Compiler.queue trống có nghĩa JIT chưa hoạt động.”** Sai: tasks có thể đã hoàn thành.
19. **“Compiler.codelist là toàn bộ Java source methods.”** Sai: chỉ compiled code entries còn sống.
20. **“PrintCompilation output luôn cố định.”** Sai: compilation timing/IDs/levels thay đổi.
21. **“NMT Code bao gồm toàn bộ Compiler memory.”** Sai: category khác nhau.
22. **“CICompilerCount tăng gấp đôi thì compile nhanh gấp đôi.”** Sai: CPU contention/queues/memory.
23. **“Warm-up benchmark 1 giây đại diện steady state.”** Sai: JIT tiering cần thời gian/profile.
24. **“Code cache đầy có thể chữa bằng System.gc().”** Không bảo đảm.
25. **“Một class-file Code attribute là một nmethod trong code cache.”** Sai: code bytecode khác machine code.
26. **“Cache free dương nghĩa chắc cấp được mọi blob.”** Sai: fragmentation/segment type có thể cản.
27. **“Compiled code không thể bị invalidated.”** Sai: deopt/unloading/recompile là cơ chế chuẩn HotSpot.
28. **“Tăng code cache không có memory overhead.”** Sai: allocation/native budget vẫn hữu hạn.
29. **“Một service thiếu CPU compiler có thể chữa bằng tăng heap.”** Không trực tiếp.
30. **“JIT logs không cần đúng JDK version.”** Sai: flags/log fields thay đổi.

## 24. Bài tập có đáp án

**Bài 1.** Code cache chứa gì và có phải Java heap không?

**Đáp án:** Chứa native code/code blobs của HotSpot, khác managed Java heap chứa objects/arrays.

**Bài 2.** Javac và C2 khác nhau ra sao?

**Đáp án:** Javac tạo Java bytecode; C2 tối ưu/biên dịch bytecode hot thành CPU-specific machine instructions khi runtime.

**Bài 3.** Vì sao HotSpot dùng background compiler threads?

**Đáp án:** Để mutator có thể tiếp tục thực thi while compilation diễn ra, giảm blocking trên đường nóng; vẫn có CPU/native costs.

**Bài 4.** Tại sao C1 và C2 cùng tồn tại?

**Đáp án:** C1 giúp compile sớm/warm-up/profile, C2 tốn CPU hơn nhưng có thể tăng steady-state performance.

**Bài 5.** Dùng -XX:-TieredCompilation có tắt JIT không?

**Đáp án:** Không nhất thiết; vẫn có non-tiered JIT, còn -Xint dùng để so interpreter.

**Bài 6.** OSR là gì?

**Đáp án:** Cho phép chuyển sang compiled code khi một method đang chạy một hot loop mà chưa return.

**Bài 7.** Segmented code cache gồm các phân vùng nào ở HotSpot JDK17?

**Đáp án:** Non-method, profiled method, non-profiled method heaps khi segmentation được bật.

**Bài 8.** Tại sao non-method heap không được sweep tùy tiện giống mọi C1 nmethod?

**Đáp án:** Chứa runtime/interpreter/compiler stubs có thể phải tồn tại lâu để JVM hoạt động đúng.

**Bài 9.** Compiler code bị deopt có thể còn trong cache không?

**Đáp án:** Có; reclaim phải đảm bảo code không còn unsafe active use.

**Bài 10.** Reserved 240 MiB, committed 40 MiB; code cache có chắc chiếm 240 MiB physical RAM không?

**Đáp án:** Không; reserved virtual address space khác committed/used.

**Bài 11.** Code cache full thì JVM nhất định OOME Java heap không?

**Đáp án:** Không; có thể compiler disabled, methods fallback interpreter và performance giảm.

**Bài 12.** Tại sao code cache capacity lớn hơn không luôn tăng throughput?

**Đáp án:** Nếu chưa cạn, bottleneck nằm ở compiler CPU, application processing hoặc memory bandwidth; tăng capacity không tự làm biên dịch nhanh.

**Bài 13.** Compilation queue dài nhưng cache còn free, nguyên nhân khả dĩ?

**Đáp án:** Compiler tasks nhiều/phức tạp, CICompilerCount thấp, CPU starvation hoặc quota hạn chế.

**Bài 14.** Dùng lệnh nào xem code cache thực của HotSpot?

**Đáp án:** jcmd <PID> Compiler.codecache.

**Bài 15.** Xem compiler tasks chờ xử lý bằng lệnh nào?

**Đáp án:** jcmd <PID> Compiler.queue.

**Bài 16.** Làm sao xem compiled methods đang sống?

**Đáp án:** jcmd <PID> Compiler.codelist.

**Bài 17.** Với hotSum(100_000) chạy 20 lần, checksum là bao nhiêu?

**Đáp án:** 5.999.900.

**Bài 18.** Nếu đổi -Xint mà Java stdout đổi khác (không do timing/concurrency), điều gì đáng nghi?

**Đáp án:** Chương trình có data race/nondeterministic behavior, native/undefined assumptions hoặc lỗi runtime; JIT không được đổi sequential Java semantics.

**Bài 19.** NMT dùng để đo gì?

**Đáp án:** Native allocations theo VM categories như Code, Compiler, Thread, Class; không thay CPU profiler hoặc heap dump.

**Bài 20.** Vì sao phải đo p99 cả trước/sau JIT tuning?

**Đáp án:** Giảm compilation CPU có thể kéo dài interpreted execution; tăng compiler threads có thể tranh CPU; chỉ đo throughput trung bình có thể bỏ qua tail latency.

## 25. Quy trình triển khai/tuning thực tế

1. **Xác nhận runtime:** HotSpot vendor, JDK17 build, architecture, container limits.
2. **Đo baseline:** p95/p99, throughput, CPU usage, startup time, heap/RSS.
3. **Kiểm tra final flags:** SegmentedCodeCache, ReservedCodeCacheSize, TieredCompilation, CICompilerCount.
4. **Quan sát code-cache segments:** Compiler.codecache và per-heap usage.
5. **Quan sát compilation backlog:** Compiler.queue theo nhiều mốc.
6. **Đọc compilation events:** PrintCompilation/JFR khi cần.
7. **Phân biệt warm-up bình thường với code churn bất thường.**
8. **Xem deoptimization/recompilation do runtime profiles/classes mới.**
9. **Đo native memory:** NMT Code/Compiler/Thread/Class và RSS thực.
10. **Nếu code cache full:** điều tra which heap/fragmentation; tăng budget chỉ khi có evidence.
11. **Nếu CPU compiler quá cao:** phân biệt load khởi động và sustained backlog; không tùy tiện hạ/tăng compiler threads.
12. **Benchmark bằng workload thật và JMH khi micro-level**, có warm-up, nhiều runs.
13. **Chỉ đổi một biến tuning mỗi lần**, ghi kết quả và rollback nếu regression.
14. **Không dùng -Xmx làm thay code-cache budget.**
15. **Kiểm tra lại khi nâng JDK**, vì compiler implementations/flags/defaults có thể thay đổi.

### Tài liệu chính thức

- **Oracle JDK 17 — java command, ReservedCodeCacheSize, SegmentedCodeCache, TieredCompilation:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle JDK 17 — jcmd Compiler.codecache/queue/codelist:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Oracle JDK 17 — Native Memory Tracking:** https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- **OpenJDK JEP 197 — Segmented Code Cache:** https://openjdk.org/jeps/197
- **Oracle HotSpot Performance Enhancements — Tiered Compilation/Code Cache:** https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **OpenJDK JDK 17 HotSpot Code Cache source:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/code
- **OpenJDK JDK 17 HotSpot Compiler source:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/compiler
- **Java SE 17 — CompilationMXBean:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html
- **Java SE 17 — jfr command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- **JVMS 17 — Method Area abstraction:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.4

**Kết luận:** JIT tăng tốc hot code nhưng tiêu tốn **compiler CPU, native temporary memory và code-cache capacity**. HotSpot JDK17 thường dùng tiered C1/C2 compilation và segmented code cache gồm non-method, profiled, non-profiled heaps. Native nmethods có thể được thay thế, deoptimize và reclaim an toàn. **Code cache đầy có thể khiến ứng dụng chạy chậm mà không gây Java heap OOME.** Muốn tuning phải quan sát **code cache, compilation queues, warm-up, GC/native memory và CPU contention**, không chỉ thay -Xmx hoặc đo một lần chạy nhỏ.
