# Code cache lưu mã máy do JVM tạo ra

**Code cache** trong HotSpot JVM là vùng bộ nhớ dùng để giữ **mã máy native đã được JVM tạo ra**, nổi bật là các phương thức Java được **JIT (Just-In-Time) compiler** biên dịch, cùng một số đoạn mã phục vụ bản thân VM như runtime stubs và adapters. Khi một method trở nên đủ “hot”, JVM có thể biên dịch bytecode của nó thành instruction cho CPU đang chạy rồi lưu phần mã máy đó ở code cache để dùng lại.

Đây là thành phần rất quan trọng trong chủ đề **các vùng bộ nhớ JVM**, nhưng cần phân biệt: **Java heap giữ objects; metaspace giữ class metadata; thread stack giữ frames; code cache giữ mã có thể được CPU thực thi**. Code cache không phải tên một vùng bộ nhớ bắt buộc với cùng cách hiện thực trên mọi JVM theo JVM Specification. Những cấu trúc như **nmethod**, **CodeHeap**, **C1/C2 tiered compilation** và các option `-XX:...` trong bài chủ yếu là **chi tiết HotSpot/OpenJDK**, không phải cam kết phổ quát cho mọi JVM.

## 1. Từ `.java` tới mã máy nằm trong code cache

Khi biên dịch và chạy một class Java thông thường, hai thời điểm khác nhau xuất hiện:

```text
        Compile time                                Runtime
  ┌─────────────────────┐                 ┌──────────────────────────┐
  │ Hello.java          │                 │ JVM / ClassLoader        │
  │ javac               │                 │ đọc Hello.class          │
  └─────────┬───────────┘                 └────────────┬─────────────┘
            │                                          │
            ▼                                          ▼
       Hello.class                         JVM bytecode + metadata
      JVM bytecode                                   │
                                          ┌──────────┴──────────────┐
                                          │                         │
                                          ▼                         ▼
                                    Interpreter                 JIT compiler
                                    thực thi bytecode          biên dịch method
                                                                     │
                                                                     ▼
                                                              Native machine code
                                                                     │
                                                                     ▼
                                                                 CODE CACHE
                                                                     │
                                                                     ▼
                                                             CPU thực thi mã JIT
```

Sơ đồ chỉ mô tả các đường thực thi có thể có. **Không phải một method luôn luôn được JIT compile**: code ít được dùng có thể tiếp tục chạy bằng interpreter; một method có thể được biên dịch nhiều lần ở mức tối ưu khác nhau; và JVM có thể bỏ mã máy đã biên dịch để trở lại interpreter hoặc biên dịch lại.

**Ba lớp mã cần phân biệt:**

1. **Java source**: ký tự trong `.java`, biên dịch bởi `javac`.
2. **JVM bytecode**: các opcode như `iload`, `iadd`, `invokevirtual` trong `.class`, về nguyên tắc độc lập với CPU đích.
3. **Native machine code**: instruction x86-64, AArch64... do JIT của JVM tạo cho nền tảng hiện tại. Những đoạn này được đặt trong code cache.

`javap -c` hiển thị **JVM bytecode trong class file**, **không phải native instructions trong code cache**. JIT có thể tạo mã khác hẳn cấu trúc bytecode vì inlining, loop optimization, vectorization và những phép tối ưu khác.

### Ví dụ ngắn về cùng một lời gọi

```java
static int square(int x) {
    return x * x;
}
```

Đây là một method minh họa trong một class. Bytecode thường có dạng:

```text
iload_0
iload_0
imul
ireturn
```

Các instruction này là **bytecode**. Nếu method được JIT compile, CPU có thể thực thi native code tương ứng, hoặc mã đã được **inline** vào caller mà không còn một lời gọi method độc lập. Vì vậy không thể chỉ đếm số Java methods để kết luận code cache nhất thiết có đúng ngần ấy đoạn mã máy.

## 2. Code cache nằm ở đâu so với những vùng bộ nhớ khác?

| Vùng | Nội dung điển hình | Cơ chế / ghi chú |
| --- | --- | --- |
| **Java heap** | Object instances, arrays, phần lớn dữ liệu ứng dụng | Chịu GC; thường chịu ảnh hưởng `-Xmx` |
| **Metaspace** (HotSpot) | Class metadata, thông tin runtime của class/interface | Dùng native memory; chịu các giới hạn metaspace riêng |
| **Java thread stack** | Stack frames, local variables và operand stacks | Mỗi thread có stack riêng; ảnh hưởng bởi `-Xss` |
| **Code cache** (HotSpot) | JIT-compiled machine code và một số VM-generated code | Native/executable memory, quản lý code blobs/nmethods |
| **Direct/native buffers** | Buffer off-heap, JNI/native allocations và tài nguyên khác | Không đồng nhất với code cache |
| **ClassFile trên đĩa/JAR** | JVM bytecode và constant pool đã biên dịch | Không phải vùng code cache trong tiến trình |

Code cache có thể được mô tả dưới **non-heap memory** khi xem management API, nhưng “non-heap” **không có nghĩa một vùng duy nhất**. Metaspace và code cache đều nằm ngoài Java heap theo các cấu trúc quản lý khác nhau.

**Quan trọng về bộ nhớ tổng của tiến trình:**

```text
Bộ nhớ tiến trình JVM
  = heap thực dùng / committed
  + metaspace, class metadata
  + thread stacks
  + code cache và các vùng native khác
  + GC/JIT/compiler buffers, thư viện native, ...
```

Đây là công thức phân loại, **không phải phép cộng chính xác dự báo RSS**, vì reserved virtual address space, committed pages, shared mappings và hệ điều hành có những cách hạch toán khác nhau. Nếu container có giới hạn bộ nhớ, chỉ điều chỉnh `-Xmx` mà bỏ qua native allocations có thể vẫn khiến tiến trình vượt giới hạn.

### Code cache không phải heap objects

Ví dụ `new byte[10_000_000]` tạo **array object trên Java heap**; nó không yêu cầu 10 MB code cache. Ngược lại, method thực hiện vòng lặp nhiều lần có thể làm JIT tạo thêm mã máy dù dữ liệu mà method tính toán khá nhỏ.

Việc gọi `System.gc()` không phải lệnh “xóa code cache”. GC có thể phối hợp với các cơ chế làm sạch compiled code khi mã không còn hợp lệ hoặc có class unloading, nhưng chính sách quản lý code cache khác với quá trình thu gom các objects của Java heap.

## 3. Những loại mã được lưu trong HotSpot code cache

HotSpot dùng những cấu trúc nội bộ như **CodeBlob** để đại diện các đơn vị code/data liên quan trong code cache; **nmethod** là một dạng chứa compiled code của Java methods.

| Thành phần | Mục đích |
| --- | --- |
| **JIT-compiled nmethods** | Mã máy cho một phương thức/phiên bản tối ưu hóa cụ thể |
| **OSR nmethods** | Mã biên dịch cho phép chuyển vào vòng lặp đã biên dịch khi method đang chạy |
| **Runtime stubs** | Mã cầu nối/tiện ích JVM tạo cho các thao tác runtime đặc biệt |
| **Adapters** | Mã hỗ trợ chuyển tiếp giữa các calling conventions và đường gọi |
| **Interpreter-related generated code** | Một số đoạn code cần thiết cho engine interpreter trong HotSpot |
| **Compiler/VM buffers, auxiliary code** | Thành phần được HotSpot quản lý dưới code cache tùy cấu hình |

**Không nên hiểu toàn bộ code cache chỉ gồm “mỗi Java method đúng một nmethod”.** Một method có thể có phiên bản do C1 và phiên bản do C2 biên dịch, có OSR version riêng, hoặc được inline trong mã của method khác. JVM còn cần stubs và adapters không phải Java method biên dịch thông thường.

### Mã native ở code cache có cố định vĩnh viễn?

Không. JVM có thể:

- Thay mã C1 bằng một bản tối ưu hơn khi có profiling thích hợp.
- Đánh dấu nmethod **not entrant** để không nhận các lời gọi mới.
- Thực hiện **deoptimization** khi giả định tối ưu không còn đúng.
- Dọn mã cũ/không còn được dùng qua **code cache sweeper/code cache flushing** theo chính sách HotSpot.
- Giải phóng code liên quan tới class unloading hoặc dependency không còn hợp lệ khi đủ điều kiện.

Những hoạt động trên phụ thuộc thời gian chạy, trạng thái các thread và điều kiện an toàn. Không suy luận code cache **chỉ tăng không bao giờ giảm** hoặc **GC luôn xóa compiled code ngay khi một instance bị thu gom**.

## 4. Tiered compilation: vì sao HotSpot cần nhiều dạng mã?

HotSpot thường dùng **tiered compilation** để cân bằng **tốc độ khởi động**, **chi phí biên dịch**, **profiling** và **hiệu năng dài hạn**.

Mô hình khái quát:

```text
Chạy method lần đầu
          │
          ▼
 Interpreter + thu thập thông tin
          │
          ▼
 Method trở nên "hot"
          │
          ▼
   C1 biên dịch nhanh
   có thể bổ sung profiling
          │
          ▼
   C2 tối ưu chuyên sâu
   khi heuristics phù hợp
          │
          ▼
   Native code ở code cache
          │
          └── có thể deopt/recompile
```

Đây không phải pipeline bắt buộc “tất cả method đều đi đủ C1 rồi C2”. HotSpot có nhiều compilation levels, policy chuyển tầng, compilation thresholds và tình huống chỉ dùng một compiler hoặc không JIT. Các chi tiết thay đổi theo version và JVM flags.

### Interpreter không phải “bytecode nằm trong code cache”

- **Bytecode** vẫn là các instruction định nghĩa trong class file / runtime metadata.
- **Interpreter** đọc và thực thi ý nghĩa bytecode bằng cơ chế VM; một số interpreter stubs/mã phục vụ VM có thể ở code cache.
- **JIT** tạo mã máy chuyên biệt cho method/đường thực thi rồi quản lý nó ở code cache.

Vì interpreter có thể tự là mã native do VM cung cấp, đừng nói “mọi byte native trong code cache đều do C2 compile từ một Java method”. Ngược lại, code cache có thể chứa mã không phải bytecode Java source được JIT dịch trực tiếp.

## 5. Segmented code cache: nhiều CodeHeaps thay vì một khối duy nhất

HotSpot hỗ trợ **segmented code cache** theo JEP 197. Khi bật phân đoạn, code cache thường có ba **CodeHeaps** theo loại mã:

| Phân đoạn | Nội dung chính | Tên quan sát có thể gặp |
| --- | --- | --- |
| **Non-method** | VM-generated code không thuộc compiled Java method, ví dụ adapters/stubs/interpreter hỗ trợ | `CodeHeap 'non-nmethods'` |
| **Profiled methods** | Mã compiled có profiling, thường ngắn hạn và có thể được biên dịch lại | `CodeHeap 'profiled nmethods'` |
| **Non-profiled methods** | Mã compiled ít/không mang profiling, thường tối ưu dài hạn | `CodeHeap 'non-profiled nmethods'` |

Sơ đồ logic:

```text
HotSpot Code Cache (native executable code region)
┌───────────────────────────────────────┐
│ CodeHeap: non-nmethods                │
│  VM stubs / interpreter code / ...   │
├───────────────────────────────────────┤
│ CodeHeap: profiled nmethods           │
│  tiered compilation + profiling      │
├───────────────────────────────────────┤
│ CodeHeap: non-profiled nmethods       │
│  tối ưu cao, code dùng dài hạn        │
└───────────────────────────────────────┘
```

Việc phân đoạn nhằm cải thiện locality, giảm fragmentation và phân biệt vòng đời của những loại compiled code khác nhau. **Các CodeHeaps không tương đương ba Java heaps và không được GC Java như object collections.**

**Không phải JVM nào cũng có đúng ba phân đoạn trong mọi lúc.** Nếu segmentation tắt, có thể chỉ thấy `Code Cache` chung. Cấu hình tiered compilation, kích thước code cache, version HotSpot và các tùy chọn chuyên biệt có thể làm số phân đoạn khác. Một số phiên bản JVM tương lai có thể có thay đổi mới; cách chắc chắn nhất là **đọc thống kê từ JVM thực tế**.

### Những flags liên quan phân đoạn

```text
-XX:+SegmentedCodeCache
-XX:NonNMethodCodeHeapSize=<size>
-XX:ProfiledCodeHeapSize=<size>
-XX:NonProfiledCodeHeapSize=<size>
```

Các tham số trên là **HotSpot-specific**; không nên sao chép các giá trị tùy ý khi chưa đo tải và kiểm tra hỗ trợ trên phiên bản JDK. Với JDK 17 HotSpot, tên/khả năng của các flags có thể kiểm tra bằng `java -XX:+PrintFlagsFinal -version`, nhưng output rất dài và default có thể phụ thuộc môi trường.

**Cảnh báo cấu hình:** phân đoạn có các giới hạn bộ nhớ được phân chia theo loại; tăng tổng `ReservedCodeCacheSize` chưa chắc sửa được mất cân đối nếu đã tùy chỉnh riêng kích thước từng CodeHeap. Cần xem code heap nào đầy và VM có bật segmentation không trước khi chọn phương án chỉnh.

## 6. OSR (On-Stack Replacement) cũng dùng code cache

Một vòng lặp có thể chạy rất lâu **trong cùng một lần gọi method**. Nếu JVM chỉ JIT giữa các lần gọi, phương thức một lần chạy nhưng lặp hàng triệu vòng có thể mãi ở interpreter. **OSR** cho phép JVM biên dịch một đường vào vòng lặp và chuyển thực thi từ frame đang chạy sang mã compiled tại **OSR entry point** thích hợp.

```text
Method bắt đầu (interpreter)
          │
          ▼
     loop iteration...
          │ đủ nóng
          ▼
 JIT biên dịch OSR nmethod
          │
          ▼
    chuyển vào loop
       compiled code
          │
          ▼
  tiếp tục vòng lặp
```

Mã OSR có thể cùng tồn tại với phiên bản compiled thông thường của method. `-XX:+PrintCompilation` trong HotSpot có thể hiển thị ký hiệu **`%`** liên quan tới OSR compilation, nhưng không nên coi mọi vòng lặp trong chương trình demo chắc chắn tạo OSR ở mọi máy/chế độ.

**OSR không phải stack overflow**, cũng không có nghĩa JVM chép toàn bộ Java thread stack sang code cache. Nó là một cơ chế chuyển **đường thực thi** vào compiled code cho phần method đang hoạt động.

## 7. Nmethod có gì ngoài machine instructions?

Một compiled method cần tương tác với VM và runtime:

- **Entry points** để gọi compiled code theo calling convention thích hợp.
- **Machine instructions** thực hiện tính toán và các kiểm tra cần thiết.
- **Metadata** giúp xác định vị trí/quan hệ bytecode, inlining và trạng thái deoptimization.
- **Safepoints/polling** và những cơ chế giúp GC, stack walking, deoptimization phối hợp.
- **Oop maps**, relocation và những mô tả cần thiết để runtime biết nơi có object references và cập nhật chúng theo điều kiện áp dụng.
- **Exception handling/unwind information** phù hợp với code đã biên dịch.

Danh sách phản ánh ý tưởng thiết kế HotSpot; **không phải mô tả layout byte-for-byte của mọi `nmethod`**. Cách đặt những dữ liệu đi kèm có thể thay đổi giữa builds/architectures.

### Tại sao compiled code không thể xem như tệp EXE độc lập?

Một đoạn JIT-compiled code sử dụng runtime assumptions, class metadata, helper routines và địa chỉ trong **cùng JVM process**. Nó còn phải có khả năng deopt và phối hợp với GC/class loading. Vì vậy không thể lấy raw bytes từ code cache rồi dùng nó như `.exe` portable chạy trên máy khác mà không có VM context.

Code cache không phải một “ổ đĩa cache” để lần sau mở ứng dụng tự load lại tất cả native code giống hệt. HotSpot có các công nghệ khác như **Class Data Sharing (CDS)**, AppCDS và những cơ chế AOT tùy bản JDK, nhưng chúng **không đồng nhất** với code cache JIT thông thường.

## 8. Reserved, committed, used và free: bốn khái niệm dễ nhầm

HotSpot thường **reserve** một khoảng địa chỉ ảo tối đa cho code cache rồi **commit** bộ nhớ khi cần. Các thống kê có thể báo:

| Chỉ số | Ý nghĩa khái quát |
| --- | --- |
| **reserved** | Khoảng địa chỉ/khả năng bộ nhớ đã dành riêng cho code cache |
| **committed** | Phần vùng reserved đã được hệ thống/JVM cam kết sử dụng theo cơ chế quản lý |
| **used** | Dung lượng code blobs và cấu trúc đã chiếm chỗ theo thống kê của VM |
| **free** | Phần dung lượng còn trống theo cách đo của code heap |
| **max** | Giới hạn được báo qua management API, có thể tương ứng reservation/giới hạn VM |
| **largest free block / fragmentation** | Các yếu tố khả năng cấp phát code mới dù tổng free vẫn còn |

Các giá trị phụ thuộc thời điểm đọc và không nhất thiết trùng tổng memory RSS của tiến trình. **Reserved 240 MB không chứng minh JVM đang dùng 240 MB RAM vật lý**; cũng không thể lấy `used` từ các công cụ khác nhau rồi mặc định chúng cùng tính metadata/overhead một cách giống hệt.

### Tại sao code cache “còn free” mà cấp phát vẫn thất bại?

Một số trường hợp code cache bị **fragmentation** hoặc từng CodeHeap riêng bị đầy. Một code blob mới cần **vùng phù hợp**, nên dung lượng trống tổng cộng không đảm bảo mọi yêu cầu cấp phát mã đều thành công. Các chính sách sweeper/flushing, phân đoạn và compiler cũng ảnh hưởng khả năng cấp phát.

Không thể kết luận chỉ bằng một số `free=...`; cần xem thống kê theo heap, code cache state và compile activity.

## 9. Các JVM options cần biết

| Option HotSpot | Vai trò | Ghi chú |
| --- | --- | --- |
| `-XX:ReservedCodeCacheSize=<size>` | Đặt giới hạn vùng code cache được reserve | Ví dụ `64m` hoặc `256m`; hiệu quả phụ thuộc workload |
| `-XX:InitialCodeCacheSize=<size>` | Đặt kích thước ban đầu/commit khởi điểm | Phải nhất quán với giới hạn tổng |
| `-XX:+SegmentedCodeCache` | Cho phép phân đoạn code cache | Không phải JVM nào cũng mặc định như nhau |
| `-XX:+PrintCodeCache` | In thống kê code cache từ HotSpot | Thường xuất hiện khi JVM kết thúc |
| `-XX:+PrintCompilation` | In sự kiện method compilation | Logging thay đổi theo tải, phiên bản, compiler |
| `-XX:-TieredCompilation` | Tắt tiered compilation | Ảnh hưởng compiler strategy và code cache footprint |
| `-Xint` | Chạy ở chế độ thông dịch chủ yếu, không dùng JIT compilation của methods | Không có nghĩa code cache/VM native support code bằng 0 |
| `-Xcomp` | Ưu tiên biên dịch sớm các methods theo chính sách VM | Dùng thận trọng khi thử nghiệm; không phản ánh tải bình thường |

Ví dụ cách xem giá trị flag **thực tế**:

```bash
java -XX:+PrintFlagsFinal -version
```

Tìm các tên `ReservedCodeCacheSize`, `InitialCodeCacheSize`, `SegmentedCodeCache`, `TieredCompilation` trong output. Lệnh trả về rất nhiều flags; trên Linux/macOS có thể lọc:

```bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'ReservedCodeCacheSize|InitialCodeCacheSize|SegmentedCodeCache|TieredCompilation'
```

Trên PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String 'ReservedCodeCacheSize|InitialCodeCacheSize|SegmentedCodeCache|TieredCompilation'
```

Những lệnh này **không thay cấu hình hệ thống**. Giá trị mặc định của các flags có thể thay đổi theo release JDK, kiến trúc, bộ nhớ, chế độ JVM và ergonomics. Không hard-code “mọi Java đều có mặc định đúng 240 MB”; nếu đề cập con số đó, hãy kiểm tra phiên bản HotSpot đang dùng.

### Phân biệt sizing và tuning

Tăng `ReservedCodeCacheSize` có thể giúp khi **thực sự code cache thiếu** và workload cần giữ nhiều compiled code. Nhưng tăng giới hạn cũng dành thêm **virtual address space** và có thể tăng native memory commitment theo tải; nó không sửa memory leak ở Java heap, classloader leak ở metaspace, hay CPU bottleneck không liên quan JIT.

Giảm code cache quá mạnh có thể tăng **compilation failures**, code flushing hoặc gây giảm performance. Đừng áp một giá trị cố định cho mọi ứng dụng/production server chỉ vì thấy ví dụ trong bài.

## 10. Khi code cache đầy, JVM và ứng dụng bị ảnh hưởng như thế nào?

HotSpot có thể báo thông điệp tương tự:

```text
CodeCache is full. Compiler has been disabled.
Try increasing the code cache size using -XX:ReservedCodeCacheSize=
```

Đây là **mẫu thông báo thường gặp, không phải log chính xác bắt buộc ở mọi JDK**. Khi không thể cấp phát thêm code, JVM có thể ngừng hoặc hạn chế các tác vụ compilation phù hợp cho đến khi có điều kiện giải phóng/khôi phục theo chính sách. Ứng dụng **không nhất thiết dừng ngay** chỉ vì xuất hiện cảnh báo; nó có thể vẫn chạy bằng mã interpreter hoặc mã compiled còn hợp lệ nhưng throughput/latency giảm.

Những triệu chứng có thể quan sát:

- **Warm-up** không đạt tốc độ mong đợi dù method được gọi nhiều lần.
- Thời gian xử lý/CPU tăng hoặc latency p95/p99 xấu đi do compiler không tạo mã mới.
- Compiler queue tăng, các phương thức nóng chưa được tối ưu như bình thường.
- Thống kê code cache có used gần giới hạn hoặc một CodeHeap riêng cạn chỗ.
- Log cảnh báo liên quan code cache, code cache sweeper, compilation disabled hoặc code heap full.

**Không suy luận chỉ từ một triệu chứng:** CPU cao cũng có thể do GC, locking, dữ liệu lớn, I/O hoặc vòng lặp ứng dụng; latency cao có thể do network. Code cache metrics cần được kết hợp với **JIT compilation metrics, GC logs, thread profiles và tải thực tế**.

### Phân biệt `OutOfMemoryError` với code cache full

Code cache đầy **không bắt buộc** báo `OutOfMemoryError: Java heap space`. Đây là một vấn đề về vùng HotSpot dành cho generated code; VM có thể giảm/ngừng compilation trong khi Java heap còn trống. Tuy nhiên các lỗi native allocation hoặc cấu hình cực đoan có thể có biểu hiện nghiêm trọng riêng. Hãy đọc **log cụ thể** của JVM thay vì quy mọi lỗi cấp phát vào một exception giống nhau.

## 11. Code cache sweeper, deoptimization và class unloading

Mã đã biên dịch không bất biến mãi mãi:

```text
Method hot → JIT compile → nmethod trong CodeHeap
                             │
                   chạy và được profiling
                             │
          ┌──────────────────┼─────────────────┐
          │                  │                 │
          ▼                  ▼                 ▼
      vẫn dùng           deopt/recompile    không còn dùng
          │                  │                 │
          ▼                  ▼                 ▼
      giữ lại          nmethod cũ         sweeper/code cache
                       not entrant        cleanup khi an toàn
```

- **Deoptimization:** JIT có thể tối ưu dựa trên giả định về runtime types, class hierarchy, branch frequencies... Khi giả định cần thay đổi, VM có thể chuyển về trạng thái ít tối ưu hơn và tiếp tục thực thi đúng ngữ nghĩa.
- **Not entrant/zombie:** các trạng thái quản lý compiled methods của HotSpot biểu thị compiled code không còn dùng cho lời gọi mới hoặc đang chờ điều kiện dọn dẹp phù hợp.
- **Code cache sweeper:** có thể giải phóng compiled methods không còn cần thiết theo điều kiện an toàn; không được loại bỏ mã mà thread vẫn cần thực thi một cách phá vỡ correctness.
- **Class unloading:** có thể khiến compiled code liên quan mất tính hợp lệ hoặc được dọn, nhưng class unloading còn phụ thuộc khả năng sống của class loader, Class objects, instances và các reference liên quan.

**Code cache flushing** không giống với **evict entries của một Java `Map`**. Nó tác động vào **mã máy có thể đang được các threads gọi** và phải phối hợp với VM runtime state.

## 12. Thực hành Java 17+: tạo workload có thể được JIT tối ưu

Tạo file **`CodeCacheDemo.java`**:

```java
public class CodeCacheDemo {
    static long checksum(int rounds) {
        long total = 0;
        for (int i = 1; i <= rounds; i++) {
            total += i % 7;
        }
        return total;
    }

    public static void main(String[] args) {
        long result = 0;
        int repeats = 50;
        for (int j = 0; j < repeats; j++) {
            result = checksum(700_000);
        }

        System.out.println("checksum: " + result);
        System.out.println("repeats: " + repeats);
    }
}
```

Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 CodeCacheDemo.java
java CodeCacheDemo
```

**Standard output chính xác khi chạy không bật logging bổ sung:**

```text
checksum: 2100000
repeats: 50
```

Lý do `checksum` có kết quả **2.100.000**: dãy phần dư của `i % 7` qua 7 giá trị liên tiếp có tổng `0+1+2+3+4+5+6 = 21`. `700_000` chia hết cho 7 và chứa `100_000` chu kỳ, nên tổng là `21 × 100_000`. Biến `result` được gán từ kết quả mỗi lần gọi; không cộng 50 lần kết quả vào stdout.

**Lưu ý:** chương trình này tạo cơ hội cho JIT quan sát method/vòng lặp hot, nhưng **không cam kết JVM phải compile method** ở một cấp cụ thể, cũng không cam kết code cache tăng đúng số byte nào. Quyết định JIT là việc của VM.

### 12.1. Đọc JVM bytecode

```bash
javap -c -p CodeCacheDemo
```

Tìm `checksum(int)` với các opcode như `iload`, `irem`, `i2l`, `ladd`, `lstore`, nhánh điều khiển vòng lặp, `lreturn`. Đây là **bytecode trong class file**. Dù output `javap` xuất hiện, nó **không chứng minh** method đã có native compiled version trong code cache.

### 12.2. In hoạt động compilation

```bash
java -XX:+PrintCompilation CodeCacheDemo
```

Bên cạnh hai dòng chương trình, JVM có thể in nhiều dòng về compiled methods. Dạng của output HotSpot thường có các chỉ báo **compile id**, **tier/level**, **method name**, **kích thước** và ký hiệu biểu thị trạng thái. Thứ tự/giá trị **không cố định**, vì còn có JIT compiler threads và các classes thư viện được VM khởi tạo/compile.

Nếu thấy `CodeCacheDemo::checksum` trong logging, đó là bằng chứng JVM đã biên dịch một phiên bản nào đó của method, **không chứng minh mỗi lần gọi đều tiếp tục chạy đúng bản đó**: deopt/recompile có thể xảy ra.

### 12.3. Xem thống kê code cache ở lúc VM kết thúc

```bash
java -XX:+PrintCodeCache CodeCacheDemo
```

Trên HotSpot hỗ trợ flag này, ngoài output của chương trình, JVM in thống kê code cache khi kết thúc. Bạn có thể thấy các dòng tương tự:

```text
CodeHeap 'non-profiled nmethods': size=... used=... max_used=... free=...
CodeHeap 'profiled nmethods':     size=... used=... max_used=... free=...
CodeHeap 'non-nmethods':          size=... used=... max_used=... free=...
```

Đây là **hình dạng log minh họa**, không phải output stdout chính xác: dấu `...` có nghĩa giá trị thực cần lấy từ máy đang chạy; JVM không phân đoạn có thể chỉ in một nhóm thống kê khác. Dòng code cache là thông tin HotSpot, không phải lời in từ `System.out.println` trong source.

### 12.4. Thử thay đổi kích thước code cache

```bash
java -XX:ReservedCodeCacheSize=64m -XX:+PrintCodeCache CodeCacheDemo
```

Con số `64m` là **tham số thí nghiệm**, không phải khuyến nghị cấu hình production. Nếu một số CodeHeaps không đủ dung lượng hoặc flag không tương thích với chế độ JVM, cấu hình có thể lỗi hoặc thay đổi cách segmentation. So sánh **code cache size/used**, **compilation behavior** và hiệu năng giữa các lần chạy, không chỉ dùng một phép đo thời gian đơn lẻ.

**Không cố tình đặt code cache cực nhỏ để làm JVM thất bại** khi đang chạy ứng dụng quan trọng. Thử nghiệm code cache full nên tiến hành riêng trong môi trường test được phép restart, với logs/metrics và khả năng trở về cấu hình ổn định.

## 13. Quan sát code cache của tiến trình đang chạy bằng `jcmd`

`jcmd` là công cụ chẩn đoán JDK, có thể gửi yêu cầu tới **JVM process khác đang chạy** nếu quyền hạn/attach được phép.

Liệt kê tiến trình:

```bash
jcmd -l
```

Sau khi xác định PID thực sự của Java process cần kiểm tra:

```bash
jcmd <PID> help
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.codelist
jcmd <PID> Compiler.queue
```

Trong lệnh, **`<PID>` là placeholder cho mã tiến trình thật**, ví dụ PID hiển thị bởi `jcmd -l`. Phải thay nó bằng số thích hợp, không sao chép nguyên `<PID>` vì shell có thể hiểu dấu `<` và `>` là cú pháp điều hướng.

| Diagnostic command | Tác dụng |
| --- | --- |
| `Compiler.codecache` | In layout/ranh giới và trạng thái code cache |
| `Compiler.codelist` | Liệt kê compiled methods còn alive trong code cache (có thể dài) |
| `Compiler.queue` | Cho biết methods đang chờ compilation |
| `help` | Xác minh commands JVM đó hỗ trợ |

Có thể dùng thêm `Compiler.CodeHeap_Analytics` trên những HotSpot có hỗ trợ, nhưng hãy **kiểm tra `jcmd PID help` trước** và cân nhắc độ dài output/chi phí chẩn đoán của production process.

**Những giới hạn thực tế:**

- `jcmd` thường cần chạy trên **cùng máy** với Java process và dưới **quyền hệ điều hành thích hợp**.
- Container/PID namespaces hoặc attach settings có thể ảnh hưởng khả năng liệt kê/đính kèm.
- Một JVM ngoài HotSpot hoặc bản JDK khác có thể không cung cấp cùng các commands.
- `CodeCacheDemo` chạy quá nhanh để bạn nhập lệnh `jcmd` trong khi còn chạy; dùng ứng dụng/service đang hoạt động hoặc một tiến trình test tồn tại đủ lâu để quan sát.

`jcmd Compiler.codecache` cho số liệu live, hữu ích hơn việc cố suy ra code cache chỉ từ `javap` output.

## 14. Quan sát theo JMX `MemoryPoolMXBean`

HotSpot có thể công bố các **non-heap memory pools** cho code cache thông qua Java Management Extensions (JMX). Tên pool có thể là `Code Cache` hoặc bắt đầu bằng `CodeHeap`, tùy JVM/segmentation. API `MemoryPoolMXBean` cho phép lấy các số như `used`, `committed`, `max` khi JVM báo được.

Tạo file **`CodeCachePools.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;

public class CodeCachePools {
    public static void main(String[] args) {
        boolean found = false;
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            String name = pool.getName();
            boolean codePool = name.equals("Code Cache")
                    || name.startsWith("CodeHeap");

            if (!codePool || pool.getType() != MemoryType.NON_HEAP) {
                continue;
            }

            found = true;
            System.out.println("pool: " + name);
            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                System.out.println("usage: unavailable");
            } else {
                System.out.println("used(bytes): " + usage.getUsed());
                System.out.println("committed(bytes): "
                        + usage.getCommitted());
                System.out.println("max(bytes): " + usage.getMax());
            }
        }
        System.out.println("code pools found: " + found);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CodeCachePools.java
java CodeCachePools
```

**Output phụ thuộc JVM:** ví dụ trên HotSpot có phân đoạn, các tên pool có thể là `CodeHeap 'non-nmethods'`, `CodeHeap 'profiled nmethods'`, `CodeHeap 'non-profiled nmethods'`, kèm những số byte khác nhau. Không đưa một bộ số cụ thể vì **tải, cấu hình, JDK và thời điểm đo** sẽ làm chúng thay đổi.

Đọc kết quả:

- `used(bytes)`: dung lượng được pool báo hiện dùng, **không nhất thiết là số bytes mã máy thuần**.
- `committed(bytes)`: dung lượng đã committed theo API.
- `max(bytes)`: giới hạn pool báo, có thể mang giá trị `-1` nếu không xác định theo hợp đồng `MemoryUsage`.
- `code pools found: true`: thường gặp trên HotSpot JDK 17; `false` có thể xảy ra trên JVM không expose pool cùng tên, vì tên pool **không chuẩn hóa** cho mọi triển khai.

Nếu muốn monitoring lâu dài, lấy samples định kỳ qua JMX metrics/exporter hoặc dùng công cụ observability phù hợp; một lần đọc ngay lúc JVM vừa khởi động thường chưa phản ánh code cache của service sau warm-up.

## 15. Native Memory Tracking (NMT) và RSS: liên hệ nhưng không đồng nghĩa

HotSpot **Native Memory Tracking** có thể giúp quan sát native memory theo nhóm khi được bật ngay từ lúc JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary CodeCacheDemo
```

Lệnh này **chỉ bật NMT cho tiến trình demo**, không tự in mọi thống kê NMT nếu chưa có yêu cầu. Với tiến trình đang chạy và có NMT, bạn có thể dùng:

```bash
jcmd <PID> VM.native_memory summary
```

Trong output có thể có nhóm **Code** với reserved/committed. Tuy nhiên NMT là công cụ hạch toán native memory **theo phân loại của HotSpot**, không phải chương trình phân tích chi tiết từng `nmethod`. Các nhóm, cách thống kê và chi phí NMT phụ thuộc chế độ `summary`/`detail` và phiên bản JVM.

**Khác biệt quan trọng:**

- **`-Xmx`** giới hạn Java heap, không kiểm soát trực tiếp toàn bộ native footprint.
- **NMT Code** giúp thấy vùng native liên quan đến code được JVM ghi nhận.
- **Code cache pool metrics** giúp thấy mức dùng của các CodeHeaps.
- **RSS của process** được OS đo theo physical memory resident và còn chứa nhiều phần khác.

Không so NMT `reserved` với container RSS rồi kết luận có “rò rỉ ảo” nếu chưa hiểu virtual reservation và committed pages.

## 16. Khi nào nên tăng `ReservedCodeCacheSize`?

Chỉ cân nhắc sau khi **đo** có dấu hiệu code cache thật sự là nút thắt.

Một quy trình điều tra:

1. **Ghi nhận JVM thực tế:** `java --version`, vendor, HotSpot build, flags, chế độ tiered compilation.
2. **Quan sát code cache theo thời gian:** dùng `jcmd Compiler.codecache`, JMX pools hoặc monitoring của hệ thống.
3. **Xem compiler activity:** `Compiler.queue`, compile logs, cảnh báo `CodeCache is full`, code sweeper/flushing.
4. **Phân loại memory:** Java heap, metaspace, direct/native buffers, thread stacks và code cache; tránh sửa nhầm vùng.
5. **Xác định CodeHeap bị áp lực:** profiled/non-profiled/non-method hoặc code cache không phân đoạn.
6. **Thử cấu hình trong staging:** tăng code cache một mức hợp lý, giữ cùng workload, warm-up, giới hạn container.
7. **Đo lại throughput, latency và memory footprint:** xác nhận có cải thiện thay vì chỉ nhìn một số used giảm.
8. **Theo dõi dài hạn:** code cache có thể đạt plateau, hoặc thay đổi do class loading động, warm-up và compilation lifecycle.

### Các tình huống thường cần chú ý

- Server chạy lâu và có **rất nhiều Java methods** được gọi/biên dịch.
- Framework tạo nhiều classes lúc runtime hoặc class loaders/plugin systems, khiến số compiled methods thay đổi đáng kể.
- Ứng dụng dùng dynamic proxies, generated bytecode, expression engines, ORM hoặc rule engines với nhiều đường code.
- Chế độ tiered compilation tạo các versions khác nhau của methods và nhiều compiled code theo thời gian.
- Kích thước code cache đã bị cấu hình quá nhỏ so với load thực tế.

**Không có một kích thước code cache tối ưu phổ quát.** App nhỏ chạy một tác vụ rồi thoát khác hẳn server nhiều giờ với hàng nghìn endpoints. Cấu hình phù hợp phải cân bằng CPU, compiler threads, native memory budget, startup warm-up và hiệu năng ổn định.

## 17. Các hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “`.class` đã chứa mã x86 nên được copy vào code cache.” | ClassFile chuẩn chứa **JVM bytecode**; JIT có thể tạo mã native cho CPU đang chạy |
| “Code cache là Java heap.” | Nó là vùng native executable code, thường được HotSpot báo trong non-heap pools |
| “`-Xmx` càng lớn thì code cache càng lớn.” | `-Xmx` điều khiển heap; code cache có flags/ergonomics riêng |
| “Mỗi Java object có một mã máy copy riêng.” | Nhiều instances cùng class/method dùng chung compiled code, không tạo code copy cho từng object |
| “Mọi Java method đều được JIT compile.” | Interpreter có thể xử lý cold code; JIT dùng heuristics |
| “Một method chỉ có duy nhất một bản compiled code.” | Có thể có C1/C2 versions, OSR nmethods hoặc recompile |
| “Code cache chỉ chứa nmethods.” | HotSpot có thể chứa stubs, adapters, interpreter-related code và CodeBlobs khác |
| “Mã đã biên dịch không thể bị xóa.” | Code sweeping, deopt, unloading có thể làm code không còn hợp lệ và được thu hồi |
| “ReservedCodeCacheSize 240m nghĩa là JVM đang dùng 240 MB RAM.” | Reserved virtual address space không đồng nghĩa committed hay RSS |
| “Code cache full chắc chắn làm JVM exit ngay.” | HotSpot có thể disable/giới hạn compilation và chương trình vẫn chạy nhưng chậm; hành vi cụ thể tùy tình huống |
| “`javap -c` hiển thị nội dung code cache.” | `javap` hiển thị JVM bytecode, không phải live JIT machine code |
| “Có đúng ba CodeHeaps trên mọi JVM.” | Phân đoạn/triển khai phụ thuộc HotSpot configuration, version và flags |
| “Chạy `System.gc()` là xóa hết code cache.” | GC quản lý heap objects; compiled-code lifecycle có cơ chế riêng và điểm phối hợp |
| “NMT Code reserved bằng RSS.” | Hai chỉ số có định nghĩa, phạm vi và cách hạch toán khác nhau |
| “Một benchmark chạy 1 lần là đủ để chọn code cache size.” | Cần warm-up, monitoring và so sánh theo tải/phiên bản có kiểm soát |

## 18. Bài tập có đáp án

### Bài 1 — Xác định vùng bộ nhớ

Một chương trình Java tạo một `new long[10_000]` và chạy method tính toán nhiều lần. **Giá trị mảng và mã máy JIT nằm đâu?**

**Đáp án:** Array object nằm trên **Java heap**; nếu method được JIT biên dịch, native code tương ứng có thể nằm trong **code cache**. Mảng không “di chuyển sang code cache” vì method của nó trở nên hot.

### Bài 2 — Phân biệt bytecode với machine code

`javap -c Example` hiển thị `imul`. Điều đó có chứng minh code cache có instruction x86 `imul` không?

**Đáp án:** **Không.** `imul` ở đây là opcode JVM. JIT có thể tạo native instruction theo CPU và optimization; có thể inline hoặc chọn cách tính tương đương khác.

### Bài 3 — Sizing

Ứng dụng có Java heap `-Xmx512m`, code cache reserved 128 MB. Có phải tổng RSS tối đa luôn bằng 640 MB?

**Đáp án:** **Không.** Ngoài heap và code cache còn metaspace, thread stacks, GC/native allocations và các vùng khác; reserved code cache còn khác committed/RSS.

### Bài 4 — Tiered code

Cùng một method có thể tạo C1 code và sau đó C2 code không?

**Đáp án:** **Có**, nếu policy/heuristics lựa chọn; không phải tất cả methods đều đi đủ các tiers.

### Bài 5 — OSR

Một method chỉ được gọi một lần nhưng chạy một vòng lặp cực dài có cơ hội chạy mã JIT không?

**Đáp án:** **Có thể.** JVM có thể dùng **OSR** để biên dịch/chuyển vào compiled loop khi vòng lặp trở nên hot.

### Bài 6 — Phân đoạn

Khi `CodeHeap 'profiled nmethods'` áp sát giới hạn nhưng `non-profiled nmethods` còn nhiều chỗ, có thể kết luận code cache không có vấn đề?

**Đáp án:** **Không.** Phải xét khả năng cấp phát theo từng CodeHeap, segmentation và flushing policy của phiên bản HotSpot.

### Bài 7 — Code cache full

Sau khi thấy log “CodeCache is full”, có nên tăng `-Xmx` trước không?

**Đáp án:** **Không mặc định.** Kiểm tra code cache metrics và compiler activity trước. Tăng Java heap không trực tiếp giải quyết code cache capacity.

### Bài 8 — Quan sát thực tế

Muốn biết code cache layout của một Java process đang chạy, công cụ nào phù hợp?

**Đáp án:** Với HotSpot JDK 17, dùng `jcmd PID Compiler.codecache` (kiểm tra `jcmd PID help` trước), kết hợp `Compiler.queue`, JMX hoặc logs phù hợp.

### Bài 9 — Độ tin cậy của số liệu

`CodeCachePools` in `max(bytes)=-1`. Có chứng minh code cache không giới hạn không?

**Đáp án:** **Không.** Trong hợp đồng `MemoryUsage`, `-1` có nghĩa **không xác định theo API**; nên xem JVM flags và công cụ chẩn đoán chuyên biệt.

### Bài 10 — Lifecycle

GC thu gom một object `User` thì nmethod `User.getName()` chắc chắn lập tức bị xóa?

**Đáp án:** **Không.** Compiled method gắn với runtime code/class dependencies, không phải mỗi instance. Điều kiện dọn code và class unloading phức tạp hơn việc một object bị GC.

### Bài 11 — Biểu hiện bottleneck

Nếu ứng dụng chậm hơn sau warm-up, nhưng code cache chỉ dùng 10% capacity, có nên đổ lỗi cho code cache full?

**Đáp án:** **Chưa có bằng chứng.** Cần đo JIT, GC, locks, I/O, CPU profiling, memory pressure; code cache 10% không tự giải thích slowdown.

### Bài 12 — Phân biệt VM-specific

Mọi JVM implementer có bắt buộc hỗ trợ `-XX:ReservedCodeCacheSize` không?

**Đáp án:** **Không.** Đây là option thuộc hệ sinh thái HotSpot. JVM Specification quy định ngữ nghĩa bytecode/runtime, không chuẩn hóa cấu trúc CodeHeap/flag HotSpot.

## 19. Checklist khi điều tra code cache

- Có xác nhận JVM vendor/version và `TieredCompilation`/segmentation chưa?
- Đã tách Java heap, metaspace, code cache và các native allocations khác chưa?
- Đã lấy thống kê `used`/`committed`/`reserved` từ đúng công cụ chưa?
- Đã xem từng CodeHeap khi segmentation bật chưa?
- Có bằng chứng compiler bị hạn chế, queue cao hoặc `CodeCache is full` không?
- Đã so sánh workload sau warm-up và trước/sau thay đổi cấu hình chưa?
- Đã xác nhận tổng native memory vẫn phù hợp container/OS limit chưa?
- Có kế hoạch quay về cấu hình cũ nếu performance regression không?
- Có hiểu số liệu đo được từ JMX/NMT/`jcmd` có phạm vi khác nhau không?

**Ghi nhớ cuối:** code cache là nơi **HotSpot lưu và quản lý native executable code do JVM tạo**, chứ không chứa Java objects hay bytecode nguồn theo cách hiểu thông thường. Hiệu năng liên quan code cache phụ thuộc việc JIT compile, tiered levels, OSR, deoptimization, code sweeping, phân đoạn và khả năng cấp phát. Quan sát bằng **`-XX:+PrintCodeCache`, `-XX:+PrintCompilation`, `jcmd Compiler.codecache`, JMX và NMT** trước khi chỉnh sizing. Một code cache đủ chỗ không bảo đảm ứng dụng nhanh; một code cache đầy có thể làm JIT mất cơ hội tối ưu dù Java heap vẫn còn.

## Tài liệu tham khảo

- **OpenJDK — JEP 197: Segmented Code Cache:** https://openjdk.org/jeps/197/
- **Oracle JDK 17 — The java Command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html (tùy chọn HotSpot như `ReservedCodeCacheSize`, `SegmentedCodeCache`, `PrintCompilation`).
- **Oracle JDK 17 — The jcmd Command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html (các commands `Compiler.codecache`, `Compiler.codelist`, `Compiler.queue`).
- **OpenJDK HotSpot source — CodeCache:** https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/codeCache.hpp và https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/codeCache.cpp (chi tiết implementation có thể thay đổi theo branch/release).
- **Java SE 17 — `MemoryPoolMXBean`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html (giao diện quản lý memory pools ở mức API).

Tài liệu OpenJDK/HotSpot nói về **một triển khai JVM cụ thể**; khi làm việc với OpenJ9, GraalVM hoặc một JVM khác, cần dùng tài liệu/options tương ứng thay vì mặc nhiên áp các flags và cấu trúc CodeHeap của HotSpot.