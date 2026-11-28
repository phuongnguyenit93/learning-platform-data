# Phân biệt class loader leak với bộ nhớ chưa được hệ điều hành thu hồi ngay

**Module:** JAVA_VERSION_JAVA16  
**Chương:** Elastic Metaspace  
**Áp dụng:** Java 16 trở lên; dùng các khái niệm class unloading, Metaspace và công cụ chẩn đoán còn phù hợp trong JDK hiện đại.

Khi một ứng dụng Java nạp rồi dỡ plugin, redeploy ứng dụng hoặc tạo nhiều class động, bộ nhớ Metaspace có thể tăng. Sau khi dỡ plugin, số liệu bộ nhớ của process không nhất thiết giảm ngay. Điều này chưa đủ để kết luận có class loader leak.

Cần tách ba câu hỏi:

1. **Class còn được giữ sống không?** Nếu class loader vẫn reachable từ GC roots, các class do loader định nghĩa chưa thể unload.
2. **Metadata đã được giải phóng chưa?** Sau class unloading, phần Metaspace đã dùng có thể giảm và vùng trống được tái sử dụng.
3. **Bộ nhớ đã được trả cho hệ điều hành chưa?** JVM có thể giữ một phần vùng đã commit để tái sử dụng; RSS của process cũng bao gồm nhiều loại bộ nhớ khác ngoài Metaspace.

Hai tình huống có thể trông giống nhau ở Task Manager hoặc `ps`, nhưng cách xử lý khác nhau. Class loader leak cần tìm và loại bỏ tham chiếu giữ loader sống. Bộ nhớ đã có thể tái sử dụng nhưng chưa uncommit không nhất thiết là lỗi.

## 1. Ba trạng thái bộ nhớ cần phân biệt

Trên HotSpot, class metadata được quản lý trong native memory của Metaspace. Elastic Metaspace từ Java 16 (JEP 387) cải thiện việc quản lý chunk và khả năng trả vùng nhớ không còn cần thiết. Để đọc số liệu, phân biệt:

| Chỉ số | Ý nghĩa | Có thể giảm ngay sau class unloading không? |
| --- | --- | --- |
| Metaspace used | Phần vùng Metaspace đang được metadata sử dụng | Thường giảm khi metadata của class đã unload; mức giảm phụ thuộc workload |
| Metaspace committed | Vùng native memory JVM đã commit để allocator sử dụng | Có thể giữ nguyên để tái sử dụng rồi mới uncommit |
| Metaspace reserved | Không gian địa chỉ JVM đã reserve cho Metaspace | Không đồng nghĩa với RAM vật lý đang dùng |
| Process RSS | Các trang bộ nhớ của process hiện đang resident trong RAM | Không nhất thiết giảm cùng lúc với Metaspace used |

Các chỉ số này mô tả các lớp khác nhau. `Reserved` không phải lượng RAM đã tiêu thụ. `Committed` cũng không đồng nghĩa toàn bộ committed pages đang resident. RSS lại tính cả heap, thread stacks, code cache, direct buffers và các vùng native khác.

## 2. Class loader leak là gì?

Class loader leak xảy ra khi class loader lẽ ra đã kết thúc vòng đời vẫn còn reachable từ một đường tham chiếu sống. Vì defining class loader là một phần của danh tính class, JVM không thể unload các class do loader đó định nghĩa khi loader vẫn còn được giữ sống.

Các nguyên nhân phổ biến:

- Static registry hoặc cache ở application/server class loader giữ instance, `Class<?>`, `Method` hoặc `MethodHandle` của plugin.
- Thread do plugin tạo ra vẫn chạy sau khi plugin dừng.
- Thread pool dùng chung giữ `ThreadLocal` hoặc thread context class loader (TCCL) trỏ tới plugin loader.
- Event listener, scheduler, callback hoặc shutdown hook chưa được gỡ.
- Native code giữ JNI global reference tới object được định nghĩa bởi plugin loader.
- Một method của plugin vẫn đang chạy và stack frame còn giữ class/object liên quan.

Ví dụ đường tham chiếu:

```text
GC Root
  |
  v
Static registry trong application loader
  |
  v
Plugin instance / Class<?> / Method
  |
  v
Plugin defining class loader
  |
  v
Class metadata trong Metaspace
```

Chỉ đóng JAR hoặc gọi `URLClassLoader.close()` không phá được các đường tham chiếu này. Cần dừng thành phần của plugin và gỡ các tham chiếu khỏi những đối tượng có vòng đời dài hơn plugin.

## 3. Bộ nhớ chưa được trả về hệ điều hành là gì?

Khi class loader đã được thu hồi và class unloading diễn ra, metadata không còn cần thiết sẽ trở thành vùng trống trong bộ quản lý Metaspace. JVM có thể:

1. Tái sử dụng vùng trống cho class metadata được nạp sau đó.
2. Giữ một phần vùng đã commit để tránh phải xin lại native memory khi workload tiếp tục.
3. Uncommit các vùng/chunk phù hợp khi chính sách quản lý Metaspace xác định chúng không còn cần giữ.

Vì thế, có thể thấy Metaspace used giảm trong khi committed hoặc RSS thay đổi ít. Đây là tình huống có thể bình thường: dữ liệu class đã được giải phóng, nhưng JVM vẫn giữ một phần bộ nhớ để tái sử dụng.

Elastic Metaspace cải thiện khả năng thu hồi ở mức allocator; nó không cam kết RSS của process phải giảm ngay sau mỗi lần unload. Việc uncommit phụ thuộc kích thước vùng có thể trả, trạng thái allocator, thời điểm GC và chính sách runtime.

## 4. Bảng so sánh dấu hiệu

| Quan sát | Class loader leak có khả năng | Bộ nhớ được giữ để tái sử dụng có khả năng |
| --- | --- | --- |
| Số class loader sau mỗi lần redeploy | Tăng dần, loader cũ vẫn tồn tại | Ổn định hoặc quay về mức nền sau khi unload |
| Số class đã load | Tăng liên tục qua các chu kỳ có cùng workload | Tăng khi tải, sau đó giảm hoặc ổn định |
| Log class unloading | Không thấy unload của nhóm class cần dỡ; cần kiểm tra collector và reachability | Có log unload tương ứng với class loader đã dỡ |
| Metaspace used | Tiếp tục tăng qua các chu kỳ tương đương | Giảm hoặc ổn định sau unload |
| Metaspace committed | Có thể tăng cùng used | Có thể vẫn cao dù used đã giảm |
| Process RSS | Có thể tăng nếu leak tiếp tục tích lũy | Có thể giữ cao vì JVM/native allocator còn giữ trang để tái sử dụng |
| Heap dump | Có đường tham chiếu mạnh từ GC root tới loader cũ | Không thấy root giữ loader cũ; vùng native committed có thể vẫn còn |

Không dùng riêng một hàng trong bảng để kết luận. Cần kết hợp class loader stats, log unload, Metaspace metrics và reference path trong heap dump.

## 5. Quy trình đo có kiểm soát

Để phân biệt hai tình huống, hãy so sánh các lần load/unload có workload gần tương đương:

1. Ghi số liệu nền trước khi nạp plugin.
2. Nạp plugin và thực hiện workload đại diện; ghi số class loader, class count và Metaspace.
3. Dừng plugin theo đúng lifecycle: dừng task, thread, listener, scheduler; xóa cache/registry; khôi phục TCCL; đóng tài nguyên loader.
4. Chờ chu kỳ GC phù hợp với collector để class unloading có cơ hội xảy ra.
5. Ghi lại class loader stats, log unload, Metaspace used/committed và RSS.
6. Lặp lại nhiều chu kỳ để xem số liệu có tích lũy hay trở về một vùng ổn định.

Không so sánh một lần startup với một lần shutdown nếu tải class, số request hoặc số plugin đang hoạt động khác nhau. Hãy giữ workload, số plugin và thời gian quan sát tương đương.

## 6. Bật log class loading và unloading

Unified logging là cách hiện hành để quan sát class load/unload của HotSpot:

```sh
java -Xlog:class+load=info,class+unload=info -jar application.jar
```

Nếu cần xem thêm thông tin GC liên quan đến Metaspace:

```sh
java -Xlog:gc+metaspace=info,class+unload=info -jar application.jar
```

Đọc log theo hướng:

- Xác định thời điểm plugin được nạp và nhóm class do loader đó định nghĩa.
- Xác định thời điểm plugin được dừng.
- Kiểm tra có sự kiện class unloading sau khi loader không còn reachable hay không.
- Đối chiếu thời điểm unload với biến động Metaspace used/committed.

Không thấy log unload ngay sau khi gọi `close()` chưa chứng minh có leak. `close()` không yêu cầu GC; class unloading chỉ diễn ra khi loader đủ điều kiện thu hồi và collector thực hiện xử lý tương ứng. Một số collector/configuration có lịch và cơ chế class unloading khác nhau.

## 7. Xem thống kê class loader bằng jcmd

Trên HotSpot, có thể xem thống kê class loader của process:

```sh
jcmd <pid> VM.classloader_stats
```

Lệnh này giúp quan sát các class loader, số class được định nghĩa và thống kê vùng metadata liên quan. Chụp số liệu ở các mốc:

- Sau startup ổn định.
- Sau khi nạp plugin.
- Sau khi dừng plugin và có cơ hội class unloading.
- Sau mỗi chu kỳ redeploy tiếp theo.

Nếu số loader của plugin cũ tăng sau từng chu kỳ và không biến mất, cần tìm reference path giữ chúng. Nếu loader cũ không còn nhưng committed vẫn cao, hãy xem thêm Metaspace metrics và native memory trước khi kết luận.

Một lệnh khác trên các HotSpot JDK hiện đại là:

```sh
jcmd <pid> VM.metaspace
```

Lệnh này hiển thị thống kê chi tiết hơn về Metaspace theo khả năng của JDK đang dùng. Đầu ra và các trường chi tiết có thể thay đổi giữa phiên bản; dùng `jcmd <pid> help VM.metaspace` để xác nhận lệnh và tùy chọn được runtime hỗ trợ.

Trên JDK có hỗ trợ các tùy chọn này, có thể xem mức dùng theo class loader:

```sh
jcmd <pid> VM.metaspace show-loaders=true scale=MB
```

Lệnh chi tiết hơn có thể mất thời gian khi process có rất nhiều class. Chỉ bật liệt kê class khi cần truy vết một loader cụ thể:

```sh
jcmd <pid> VM.metaspace show-loaders=true show-classes=true scale=MB
```

## 8. Dùng Native Memory Tracking để đối chiếu

Native Memory Tracking (NMT) phải được bật khi JVM khởi động:

```sh
java -XX:NativeMemoryTracking=summary -jar application.jar
```

Chụp baseline sau khi ứng dụng ổn định:

```sh
jcmd <pid> VM.native_memory baseline
```

Sau một hoặc nhiều chu kỳ load/unload:

```sh
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Hoặc xem snapshot hiện tại:

```sh
jcmd <pid> VM.native_memory summary scale=MB
```

NMT giúp xem biến động native memory theo nhóm, trong đó có nhóm Class/Metaspace. Nó có overhead, không theo dõi đầy đủ mọi allocation native của thư viện bên thứ ba và không thay thế số đo RSS của hệ điều hành. Hãy dùng NMT cùng `VM.classloader_stats` và log class unloading.

## 9. RSS không phải Metaspace

RSS là lượng trang bộ nhớ của process hiện đang nằm trong RAM. Ngoài Metaspace, RSS có thể bao gồm:

- Java heap pages.
- Thread stacks của các thread Java và native.
- JIT code cache.
- Direct byte buffers và các native buffers.
- GC structures, compiler/runtime structures.
- Native allocations từ JNI hoặc thư viện bên thứ ba.

Vì vậy, RSS không giảm sau khi Metaspace used giảm không phải bằng chứng class loader leak. Ngược lại, RSS đứng yên cũng không chứng minh không có leak; Metaspace used và số class loader vẫn có thể tăng bên trong process.

Một số nguồn có thể giúp xem RSS và mapping theo hệ điều hành:

| Hệ điều hành | Công cụ/thông tin |
| --- | --- |
| Linux | `ps`, `/proc/<pid>/status`, `/proc/<pid>/smaps_rollup` |
| Windows | Task Manager, Process Explorer hoặc VMMap |
| macOS | Activity Monitor hoặc `vmmap <pid>` |

Các công cụ OS cho biết góc nhìn resident/virtual memory; chúng không tự xác định class loader nào đang giữ metadata. Dùng profiler hoặc heap dump để tìm tham chiếu Java.

## 10. Tìm đường tham chiếu giữ loader trong heap dump

Khi class loader cũ vẫn xuất hiện trong `VM.classloader_stats`, lấy heap dump trong môi trường có thể chấp nhận chi phí và dung lượng lưu trữ:

```sh
jcmd <pid> GC.heap_dump /path/to/application-heap.hprof
```

Heap dump có thể kích hoạt Full GC và tạo pause; thao tác cũng cần dung lượng đĩa đáng kể. Ưu tiên môi trường staging hoặc cửa sổ bảo trì nếu workload không cho phép pause. Mở dump bằng công cụ phân tích heap như Eclipse MAT hoặc profiler tương đương. Tìm instance của custom class loader hoặc object plugin rồi xem:

1. **Path to GC Roots:** đường tham chiếu mạnh từ root tới loader.
2. **Dominator tree:** object/cache nào giữ một vùng object lớn.
3. **Thread và ThreadLocal:** worker nào còn giữ context loader hoặc object plugin.
4. **Static fields và registry:** cache ở parent/application loader còn entry của plugin không.
5. **Listener và executor:** callback/task có còn được đăng ký không.

Heap dump có thể chứa dữ liệu nhạy cảm của ứng dụng. Lưu và phân tích nó theo chính sách bảo mật của hệ thống; không đưa dump production lên dịch vụ công cộng.

## 11. Ví dụ: hai kết quả khác nhau sau khi dỡ plugin

Giả sử mỗi plugin định nghĩa khoảng 300 class. Ứng dụng chạy cùng một workload và dỡ plugin sau mỗi chu kỳ.

**Trường hợp A — có khả năng class loader leak**

| Mốc đo | Số loader plugin cũ | Metaspace used |
| --- | ---: | ---: |
| Sau startup | 0 | 48 MiB |
| Sau lần nạp/dỡ thứ nhất | 1 | 61 MiB |
| Sau lần nạp/dỡ thứ hai | 2 | 75 MiB |
| Sau lần nạp/dỡ thứ ba | 3 | 89 MiB |

Nếu các loader cũ vẫn xuất hiện, log không có class unloading tương ứng và heap dump chỉ ra static registry giữ plugin instance, đây là bằng chứng mạnh của leak. Cần gỡ entry và hoàn tất shutdown lifecycle.

**Trường hợp B — vùng native được giữ để tái sử dụng**

| Mốc đo | Loader plugin cũ | Metaspace used | Metaspace committed |
| --- | ---: | ---: | ---: |
| Sau startup | 0 | 48 MiB | 64 MiB |
| Khi plugin hoạt động | 1 | 61 MiB | 72 MiB |
| Sau unload | 0 | 49 MiB | 72 MiB |
| Sau unload và thời gian ổn định | 0 | 49 MiB | 64 MiB |

Trong ví dụ này, loader đã biến mất và used trở về gần mức nền; committed chưa giảm ngay nhưng có thể được tái sử dụng. Nếu RSS vẫn cao, cần xem các nhóm native memory khác và cách OS báo resident pages.

Các số liệu trên chỉ minh họa cách đọc xu hướng, không phải ngưỡng chuẩn cho mọi ứng dụng.

## 12. Không dùng System.gc() làm phép kiểm tra duy nhất

Gọi `System.gc()` không phải cách xác nhận class loader leak:

- Đây chỉ là yêu cầu GC best-effort; JVM có thể bỏ qua hoặc xử lý theo chính sách runtime.
- Nó không xóa static reference, ThreadLocal, TCCL, listener hoặc JNI global reference.
- Nó không buộc JVM unload class nếu defining loader vẫn reachable.
- Nó có thể gây pause hoặc làm thay đổi hành vi hiệu năng trong môi trường đang phục vụ request.

Trong một thử nghiệm cô lập, có thể quan sát hành vi sau một GC cycle được kiểm soát, nhưng kết luận phải dựa trên reachability, log unloading và số liệu loader/Metaspace. Không đưa lời gọi `System.gc()` vào quy trình shutdown production để “giải phóng Metaspace”.

## 13. Khi nào nên điều chỉnh giới hạn Metaspace?

`-XX:MaxMetaspaceSize` giới hạn dung lượng Metaspace trên HotSpot. Điều chỉnh giới hạn chỉ hợp lý sau khi đã đo nhu cầu class metadata của workload và xác định headroom phù hợp.

Không tăng giới hạn để che một loader leak. Nếu số loader và Metaspace used tăng sau từng lần redeploy, tăng giới hạn chỉ trì hoãn `OutOfMemoryError: Metaspace`.

Nếu loader đã unload, used trở về ổn định nhưng committed hoặc RSS vẫn cao, tăng `MaxMetaspaceSize` không giải quyết vấn đề vì không có bằng chứng giới hạn Metaspace đang gây lỗi. Trước hết xác định vùng nhớ nào đang tăng và liệu nó có thể tái sử dụng hay được uncommit.

## 14. Cây quyết định chẩn đoán

```text
RSS hoặc native memory không giảm sau khi dỡ plugin
                  |
                  v
        Kiểm tra VM.classloader_stats
                  |
       +----------+-----------+
       |                      |
       v                      v
Loader cũ vẫn còn       Loader cũ đã biến mất
       |                      |
       v                      v
Kiểm tra class unload   So sánh Metaspace used
và heap reference path  và committed
       |                      |
       v                +-----+------+
Có root giữ loader?     |            |
       |                v            v
   +---+---+        Used vẫn cao  Used giảm,
   |       |        hoặc tăng     committed cao
   v       v            |            |
  Có     Không          v            v
   |       |       Kiểm tra class   Có thể là
   v       v       còn được dùng,   vùng giữ để
Gỡ root  Kiểm tra  loader khác,    tái sử dụng;
và lặp   collector  workload        đối chiếu RSS
đo       và log     và leak          và NMT
```

Nếu loader cũ không còn nhưng Metaspace used vẫn cao, điều đó chưa tự chứng minh leak: có thể class của ứng dụng khác vẫn đang hoạt động hoặc workload đã nạp thêm class hợp lệ. Tiếp tục so sánh class count, loader identity và baseline cùng tải.

## 15. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| RSS không giảm nghĩa là class loader leak. | **Sai** | RSS bao gồm nhiều loại memory và không đồng bộ với Metaspace used. |
| `URLClassLoader.close()` làm class unload ngay. | **Sai** | Nó đóng tài nguyên I/O; loader phải unreachable và GC phải xử lý unloading. |
| Metaspace committed cao sau unload luôn là leak. | **Sai** | JVM có thể giữ vùng đã commit để tái sử dụng. |
| Metaspace used giảm là bằng chứng hữu ích cho việc metadata đã được thu hồi. | **Đúng** | Cần kết hợp với class loader stats và log unload để xác nhận nhóm class tương ứng. |
| Class loader cũ vẫn hiện diện sau nhiều chu kỳ là dấu hiệu cần điều tra. | **Đúng** | Tìm root path giữ loader trước khi thay đổi giới hạn bộ nhớ. |
| `System.gc()` có thể xóa mọi tham chiếu giữ loader. | **Sai** | GC không xóa các tham chiếu còn sống trong ứng dụng. |
| NMT thay thế được RSS và heap dump. | **Sai** | NMT theo dõi nhóm native memory của JVM; không cho biết mọi root path hay toàn bộ RSS. |
| Tăng `MaxMetaspaceSize` sửa được leak. | **Sai** | Nó chỉ trì hoãn lỗi khi metadata tiếp tục tích lũy. |

## 16. Checklist phân biệt leak và bộ nhớ được giữ lại

1. Đã đo số class loader trước và sau mỗi chu kỳ plugin/redeploy chưa?
2. Loader cũ có còn trong `VM.classloader_stats` không?
3. Log `class+unload` có ghi nhận các class thuộc loader đã dỡ không?
4. Metaspace used có giảm hoặc trở về vùng ổn định không?
5. Metaspace committed có cao hơn used vì vùng nhớ được giữ để tái sử dụng không?
6. RSS đang tăng hay chỉ giữ nguyên? Các nhóm heap, stack, code cache và direct buffer thay đổi ra sao?
7. Heap dump có đường tham chiếu từ GC roots tới loader cũ không?
8. Static cache, ThreadLocal, TCCL, listener, executor và JNI reference đã được dọn chưa?
9. NMT có được bật từ lúc JVM khởi động để so sánh native memory không?
10. Các lần đo có cùng workload, số plugin và thời gian quan sát không?
11. Có tránh dùng `System.gc()` hoặc tăng giới hạn như giải pháp mặc định không?
12. Kết luận có dựa trên nhiều nguồn số liệu thay vì chỉ RSS không?

**Ghi nhớ:** Class loader leak nghĩa là loader cũ vẫn reachable và ngăn class unloading; hãy tìm đường tham chiếu giữ nó sống. Nếu loader đã biến mất và Metaspace used giảm nhưng committed hoặc RSS vẫn cao, JVM có thể đang giữ vùng nhớ để tái sử dụng hoặc process còn các native allocation khác. Kết hợp `VM.classloader_stats`, log `class+unload`, `VM.metaspace`, NMT và heap dump để phân biệt. RSS không phải Metaspace, và `System.gc()` không phải cách sửa leak.

## Tài liệu chính thức

- [JEP 387 — Elastic Metaspace, delivered in Java 16](https://openjdk.org/jeps/387).
- [Java SE 26 `jcmd` Tool — `VM.classloader_stats`, `VM.metaspace` and `VM.native_memory`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html).
- [Java SE 26 `java` Launcher — Unified Logging](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [Java SE 26 Troubleshooting Guide — Class Loader Statistics and memory leak diagnostics](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html).
- [Java SE 26 API — `URLClassLoader.close()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLClassLoader.html#close()).
- [Java Language Specification — Section 12.7, Unloading of Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.7).
