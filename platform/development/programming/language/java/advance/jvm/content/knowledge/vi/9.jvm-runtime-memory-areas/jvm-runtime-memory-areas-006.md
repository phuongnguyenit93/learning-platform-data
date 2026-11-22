# HotSpot Metaspace, compressed class space và sự khác biệt với PermGen lịch sử

## 1. Mục tiêu và ranh giới của bài

Trong một ứng dụng Java chạy trên **HotSpot JVM**, bộ nhớ không chỉ có **Java heap** để chứa các đối tượng ứng dụng. JVM còn dùng những vùng nhớ khác cho stack của thread, JIT code cache, cấu trúc native và đặc biệt là **metadata của những class/interface đã nạp**.

Từ **JDK 8**, HotSpot loại bỏ **Permanent Generation (PermGen)** vốn là cách triển khai cũ của vùng chứa class metadata và thay bằng **Metaspace**, sử dụng bộ nhớ native thay vì PermGen được GC quản lý theo cách lịch sử. Trên các HotSpot 64-bit có **compressed class pointers**, một phần metadata liên quan cấu trúc class được đặt trong **compressed class space**, tách về mặt logic với vùng metadata còn lại.

Ba khái niệm phải phân biệt:

1. **PermGen:** thế hệ cũ, thuộc triển khai HotSpot trước JDK 8, không phải thành phần bắt buộc trong Java Virtual Machine Specification (JVMS).
2. **Metaspace:** cơ chế cấp phát và quản lý bộ nhớ cho class metadata trong HotSpot từ JDK 8, sử dụng **native memory**.
3. **Compressed class space:** khu vực địa chỉ dành cho phần metadata class có thể truy cập bằng **compressed class pointers**, chỉ có ý nghĩa ở các cấu hình HotSpot hỗ trợ và bật tính năng này.

Học xong, bạn cần trả lời được:

- Metaspace chứa gì, khác Java heap và method area khái niệm ở đâu?
- Vì sao `-Xmx` không trực tiếp giới hạn Metaspace?
- Compressed class pointers liên quan đến `CompressedClassSpaceSize` như thế nào?
- Số **reserved** và **committed** khác nhau ra sao?
- Khi nào class metadata được giải phóng và vì sao class loader leak có thể gây `OutOfMemoryError: Metaspace`?
- Làm thế nào kiểm tra bằng `jcmd`, Native Memory Tracking, logs và các cờ của HotSpot?
- Cần điều chỉnh flag hay sửa vòng đời class loader khi sử dụng Metaspace tăng liên tục?

**Phạm vi:** đây là bài về **HotSpot implementation** và lịch sử triển khai, không phải lời khẳng định mọi JVM của mọi nhà cung cấp bắt buộc có vùng tên Metaspace hoặc compressed class space.

## 2. Method area là khái niệm của JVM; Metaspace là triển khai HotSpot

### 2.1. JVMS nói gì về method area?

**Method area** là vùng dữ liệu runtime mà **các JVM threads chia sẻ**, lưu cấu trúc theo lớp như thông tin class, runtime constant pool, mã phương thức và trường, cũng như những dữ liệu phục vụ JVM theo mô hình đặc tả. JVMS mô tả *trách nhiệm/ngữ nghĩa* của method area, nhưng **không yêu cầu một cách quản lý bộ nhớ vật lý duy nhất**.

Cách triển khai có thể thay đổi theo bản JVM, phiên bản, kiến trúc, GC và các tối ưu. Vì vậy:

> **Không nên viết “method area = Metaspace” như một đẳng thức áp dụng cho mọi JVM.**

Cách diễn đạt chính xác hơn: **HotSpot dùng cơ chế Metaspace để cấp phát nhiều cấu trúc native class metadata phục vụ các chức năng của method area trong JVM**.

### 2.2. Bản đồ khái niệm

```text
                      Tiến trình HotSpot JVM
┌─────────────────────────────────────────────────────┐
│ Java heap (quản lý bởi Java GC)                    │
│  - instance Java, array object                     │
│  - java.lang.Class mirror (đối tượng Java)         │
│  - String, collection và object ứng dụng           │
├─────────────────────────────────────────────────────┤
│ Native / non-heap memory của VM                     │
│  - Metaspace: class metadata, non-class metadata   │
│  - Compressed class space (khi bật)                 │
│  - Code cache, thread/native stacks                │
│  - Cấu trúc VM/native khác                           │
└─────────────────────────────────────────────────────┘
```

Sơ đồ **không mô tả chính xác layout các địa chỉ bộ nhớ**. Nó chỉ phân biệt trách nhiệm các loại bộ nhớ.

Điều rất dễ nhầm:

- `java.lang.Class` là một **Java object mirror**, không phải bản thân toàn bộ dữ liệu native mô tả class.
- Những **instance** được tạo bằng `new MyClass()` thuộc **Java heap**, không di chuyển vào Metaspace chỉ vì đó là instance của một class đã load.
- Những **metadata structures** của HotSpot, như cấu trúc đại diện thông tin class, có thể nằm trong Metaspace.
- Không thể kết luận **mọi static field value** đều nằm trong Metaspace. Đặc biệt, object mà static reference trỏ tới vẫn là Java object trong heap; chi tiết bố trí static fields và mirrors thuộc triển khai runtime.

### 2.3. “Non-heap” trong MXBean không đồng nghĩa một vùng nhớ duy nhất

Java Management API có `MemoryType.NON_HEAP` và `MemoryPoolMXBean`. Các công cụ có thể báo những pool như **Metaspace**, **Compressed Class Space** và **CodeHeap/code cache**, tùy HotSpot/JDK/cấu hình.

Nhưng **tổng native memory của tiến trình** không bằng đúng “Metaspace + code cache” hoặc chỉ bằng `MemoryMXBean.getNonHeapMemoryUsage()`. Thread stacks, GC native structures, symbol tables, allocator overhead, thư viện native và vùng khác có thể làm bộ nhớ resident của process tăng.

Do đó, khi hệ điều hành báo RSS tăng, **không quy ngay toàn bộ phần tăng cho Metaspace**.

## 3. PermGen trước JDK 8 là gì?

### 3.1. Permanent Generation là một cấu trúc HotSpot cũ

Trong các HotSpot phiên bản trước JDK 8, metadata của class được quản lý trong một vùng tên **Permanent Generation**, thường gọi là **PermGen**. Nó là một thế hệ/vùng bộ nhớ trong cách tổ chức GC và VM thời kỳ đó, khác với thế hệ chứa những Java application objects thông thường.

Một số cờ lịch sử:

```text
-XX:PermSize=...
-XX:MaxPermSize=...
```

Những cờ này dùng để điều chỉnh PermGen ở các bản HotSpot cũ phù hợp. Khi giới hạn bị vượt trong bối cảnh không giải phóng đủ, có thể thấy lỗi:

```text
java.lang.OutOfMemoryError: PermGen space
```

**Không dùng `PermSize`/`MaxPermSize` để cấu hình HotSpot JDK 17+.** PermGen không còn là cơ chế lưu class metadata của HotSpot từ JDK 8.

### 3.2. Sự chuyển đổi không phải “toàn bộ PermGen chuyển y nguyên vào Metaspace”

Diễn giải “JDK 8 chỉ đổi tên PermGen thành Metaspace” là sai.

Về thực chất:

- HotSpot **loại bỏ Permanent Generation**.
- Class metadata được chuyển sang **vùng quản lý metadata trong native memory**.
- Cơ chế allocator, điều chỉnh ngưỡng, accounting và giải phóng bộ nhớ thay đổi.
- Các thành phần từng được gộp chung theo cách mô tả cũ **không tất cả nằm nguyên xi trong Metaspace**.

Ví dụ quan trọng: **interned strings** đã được chuyển khỏi PermGen vào Java heap từ một số bản HotSpot trước JDK 8, đặc biệt từ JDK 7. Không đúng nếu nói “JDK 8 chuyển toàn bộ string pool từ PermGen sang Metaspace”. Các đối tượng `String` Java thuộc heap; String table và các cấu trúc tra cứu lại có chi tiết native riêng.

### 3.3. Mốc lịch sử

| Giai đoạn | Cơ chế quản lý metadata trong HotSpot | Lưu ý |
| --- | --- | --- |
| JDK 6/7 và trước JDK 8 | **PermGen**, với giới hạn/flag phù hợp bản JVM | Class metadata liên quan Permanent Generation |
| **JDK 8** | **PermGen bị loại bỏ; dùng Metaspace native** | Nội dung chính của OpenJDK **JEP 122** |
| JDK 9–15 | Metaspace tiếp tục phát triển | Hành vi chi tiết tùy phiên bản và nền tảng |
| **JDK 16 trở lên** | **Elastic Metaspace** từ **JEP 387** | Cải thiện tái sử dụng và trả memory đã commit về OS khi unloading |
| JDK 17/21/25+ | Metaspace/Compressed class space theo HotSpot hiện đại | Cờ, ergonomics và cách accounting có thể khác giữa JDK |

**“Elastic Metaspace” không có nghĩa Metaspace không bao giờ OOME**; nó cải thiện khả năng quản lý/reclaim nhưng không loại bỏ giới hạn metadata hay lỗi giữ class loader.

## 4. Metaspace lưu gì và được cấp phát theo cơ chế nào?

### 4.1. Class metadata gồm những loại thông tin nào?

HotSpot cần dữ liệu native để hiểu và thực thi class đã load, chẳng hạn:

- Thông tin mô tả một lớp/giao diện, class hierarchy và các method/field descriptors.
- Metadata phục vụ runtime method/constant-pool access, liên kết và dispatch.
- Những cấu trúc liên quan method và class mà HotSpot duy trì bên ngoài Java object heap.
- Thông tin liên quan class-loader data và các allocator dành cho metadata.

Không nên mô tả đơn giản “Metaspace chứa toàn bộ bytecode, mọi object `Class`, static object và JIT compiled code”. **JIT compiled machine code** chủ yếu được quản lý trong **code cache** chứ không phải Metaspace; các Java object mirrors tồn tại trên heap.

### 4.2. Gắn với class loader và các chunks

Ở mức khái niệm, HotSpot cấp phát metadata theo những cấu trúc gắn với **class loaders/class-loader data**, sử dụng các **chunks/arenas** được quản lý bởi metaspace allocator:

```text
ClassLoader A
   |
   +--> metadata allocations / arena A
             ├── class metadata A1
             ├── method metadata A1
             └── class metadata A2

ClassLoader B
   |
   +--> metadata allocations / arena B
             ├── class metadata B1
             └── ...
```

Sơ đồ là **mô hình quản lý**, không phải một heap dump chính xác. Mục đích là nhấn mạnh class metadata có vòng đời liên quan tới **class loader/data**. Khi class loader và các class của nó có thể unload, HotSpot có cơ hội tái sử dụng hoặc trả lại chunks/phần bộ nhớ.

### 4.3. Một class name không quyết định duy nhất metadata

Trong JVM, một nonarray runtime class được định danh bởi **binary name và defining class loader**. Hai loader khác nhau có thể định nghĩa hai class mang cùng tên, dẫn đến hai runtime classes và **hai tập metadata riêng**.

Nếu một ứng dụng liên tục tạo custom loaders và định nghĩa cùng một class trong mỗi loader nhưng giữ tất cả loaders sống, Metaspace có thể tiếp tục tăng dù file `.class` trên đĩa không đổi.

Đây là một nguồn phổ biến của **class-loader retention** và Metaspace pressure trong plugin systems, application servers, test runners hoặc bytecode generation.

### 4.4. Metadata không giải phóng ngay chỉ vì một biến bằng null

```java
Object instance = new SomeType();
instance = null;
```

Đây là **đoạn mã minh họa**, giả định `SomeType` tồn tại. Xóa một reference tới instance **không đồng nghĩa unload class SomeType**. Class có thể còn được sử dụng bởi nhiều object, threads, static references, loaders, reflection caches, methods đang chạy và các cấu trúc VM.

Để class metadata được thu hồi, các điều kiện về **class unloading** phải thỏa; quá trình này gắn với GC và reachability thực tế. Không có API Java chuẩn “free this class metadata immediately”.

## 5. Compressed class pointers và compressed class space

### 5.1. “Compressed class pointers” là gì?

Trên một số cấu hình **HotSpot 64-bit**, VM có thể dùng biểu diễn con trỏ tham chiếu tới **class metadata** dưới dạng compressed encoding. Cờ thường gặp là:

```text
-XX:+UseCompressedClassPointers
```

Điều này **khác** với **compressed ordinary object pointers (compressed oops)**, thường điều chỉnh bằng:

```text
-XX:+UseCompressedOops
```

Hai loại pointer cần phân biệt:

| Cơ chế | Mục đích | Ví dụ tham chiếu |
| --- | --- | --- |
| **Compressed oops** | Nén biểu diễn reference từ Java object này tới Java object khác | Một field chứa reference tới `String` |
| **Compressed class pointers** | Nén cách object header/runtime cấu trúc tham chiếu tới metadata class | Con trỏ class metadata tương ứng kiểu runtime của object |

Dù có mối liên hệ trong cấu hình HotSpot, đây **không phải cùng một loại dữ liệu**. Không nên nói “bật compressed oops là mọi cấu trúc metadata tự động thu nhỏ theo một tỷ lệ cố định”.

### 5.2. Compressed class space nằm ở đâu?

Khi HotSpot bật compressed class pointers, VM sử dụng vùng riêng, gọi là **compressed class space**, để giữ những cấu trúc metadata class cần nằm trong vùng có thể được biểu diễn bởi cơ chế compressed class pointers.

```text
Native memory dành cho class metadata (mô hình)
┌───────────────────────────────────────────┐
│ Non-class metadata / Metaspace allocator   │
│  - nhiều metadata không thuộc class-space  │
├───────────────────────────────────────────┤
│ Compressed class space (khi bật)           │
│  - metadata cần compressed class pointers │
│  - reserved address range                 │
│  - committed dần theo nhu cầu             │
└───────────────────────────────────────────┘
```

Tên **“class space”** không có nghĩa vùng đó chứa các object Java `Class` trên heap. Nó chứa metadata native được HotSpot quản lý.

**Đừng đồng nhất compressed class space với toàn bộ Metaspace.** Đó là một **không gian metadata riêng về mặt logic** trong cấu hình có nén class pointers.

### 5.3. `-XX:CompressedClassSpaceSize`

Cờ:

```text
-XX:CompressedClassSpaceSize=128m
```

điều chỉnh **kích thước không gian địa chỉ class space** được dành cho biểu diễn compressed class pointers, tùy giới hạn và điều chỉnh của VM. Trên nhiều HotSpot 64-bit truyền thống, mặc định gần **1 GiB**, nhưng **không phải giá trị bất biến cho mọi JVM, kiến trúc hoặc JDK**. VM có thể điều chỉnh kích thước thực khi flag khác giới hạn hoặc cấu hình không hỗ trợ.

Quan trọng:

- **Reserved 1 GiB không có nghĩa process đã chiếm 1 GiB RAM vật lý** cho class metadata.
- Class space **commit** những trang cần sử dụng theo nhu cầu.
- Khi class space được commit đủ giới hạn khả dụng và không thể giải phóng/đáp ứng thêm, có thể xuất hiện `OutOfMemoryError: Compressed class space`.
- Cờ này không trực tiếp giới hạn số instance Java được tạo trên heap.

### 5.4. Quan hệ với `-XX:MaxMetaspaceSize`

Trong cấu hình HotSpot có class space, `MaxMetaspaceSize` được áp dụng cho **tổng mức committed metadata** cần quản lý, bao gồm metadata non-class và phần class space đã commit, theo cơ chế/giới hạn thực tế của runtime.

Không suy luận phép cộng đơn giản:

```text
MaxMetaspaceSize = ReservedCompressedClassSpaceSize + MaxNonClassMetaspace
```

Đây là **công thức sai nếu dùng như đẳng thức bắt buộc**. `CompressedClassSpaceSize` thiên về một **reserved address range/capacity** của class-space, còn `MaxMetaspaceSize` là **trần metadata committed** theo HotSpot, và VM có thể điều chỉnh giới hạn nội bộ để bảo đảm phù hợp.

Ví dụ, bạn có thể nhìn thấy:

```text
class space reserved:  ~1 GiB
class space committed: 20 MiB
non-class committed:   80 MiB
```

Đây chỉ là **con số minh họa**. Tổng metadata committed là khoảng 100 MiB, không phải khoảng 1.1 GiB. Muốn kết luận bộ nhớ thực tế, cần xem **committed và used**, không chỉ reserved.

## 6. Reserved, committed, used và capacity khác nhau ra sao?

Dữ liệu Metaspace rất dễ bị đọc sai, đặc biệt khi giám sát container memory.

| Khái niệm | Ý nghĩa khái quát | Điều không nên suy luận |
| --- | --- | --- |
| **Reserved** | Không gian địa chỉ ảo được đặt trước cho vùng dữ liệu | Không đồng nghĩa đã sử dụng lượng RAM vật lý tương ứng |
| **Committed** | Phần bộ nhớ VM/OS đã commit để có thể dùng theo cơ chế nền tảng | Không nhất thiết là số byte metadata thực sự đã sử dụng |
| **Used** | Bộ nhớ metadata đang được sử dụng để giữ dữ liệu theo cách accounting của VM | Không đồng nghĩa tổng native memory của process |
| **Capacity** | Năng lực cấp phát hiện có trong các chunks/arenas theo cách thống kê tương ứng | Không phải một ngưỡng cấu hình giống nhau cho mọi phiên bản JVM |

Ví dụ hư cấu:

```text
Metaspace:
  used       80 MiB
  capacity   90 MiB
  committed  96 MiB
  reserved   1200 MiB
```

Trong mô hình đó:

- Có 80 MiB metadata thực tế đang được dùng.
- VM đã commit 96 MiB cho các metadata areas tương ứng.
- Phần reserved 1200 MiB là virtual address reservation, **không nên cộng nguyên vào RAM thực đang dùng**.
- Sự khác biệt giữa used/capacity/committed có thể liên quan allocator chunks, internal fragmentation và dư địa cấp phát.

**Các field/định nghĩa cụ thể phụ thuộc output của phiên bản HotSpot.** Khi debug, đọc phần chú giải của công cụ và version, không tự lấy một định nghĩa báo cáo cũ áp sang output mới.

### 6.1. Tại sao “Metaspace reserved” lớn vẫn có thể bình thường?

Một compressed class space có thể **reserve** vùng địa chỉ ảo tương đối lớn để hỗ trợ compressed pointers nhưng chỉ **commit** một phần nhỏ. Công cụ memory map của OS có thể hiển thị một reservation lớn, trong khi memory resident thực tế nhỏ hơn nhiều.

Nếu thấy “1 GiB reserved class space” rồi kết luận “JVM đang ngốn 1 GiB heap”, bạn đã nhầm **địa chỉ ảo**, **native metadata** và **Java heap**.

### 6.2. Committed tăng nhưng used không tăng tương ứng?

Có thể liên quan metadata allocator giữ lại chunks phục vụ tái sử dụng, fragmentation hoặc chiến lược reclamation. Trên HotSpot hiện đại sau JEP 387, VM cải thiện khả năng trả committed memory về OS khi class unload, nhưng không có bảo đảm mọi chênh lệch phải về 0 ngay.

Hãy đo theo thời gian, đọc các số **used/committed/reserved** cùng với class-loading statistics, GC và các chỉ số native memory khác.

## 7. Các cờ cấu hình HotSpot thường gặp

| Cờ | Vai trò | Lỗi hiểu nhầm phổ biến |
| --- | --- | --- |
| `-Xmx512m` | Giới hạn tối đa **Java heap** | Không phải trần tổng memory process hoặc Metaspace |
| `-XX:MetaspaceSize=128m` | Ngưỡng khởi đầu liên quan metadata occupancy để thúc đẩy GC/class unloading; có thể thay đổi | **Không** phải “khởi tạo Metaspace đúng 128 MiB” hay hard limit |
| `-XX:MaxMetaspaceSize=256m` | Giới hạn trên đối với metadata memory theo HotSpot | Không phải tổng resident process cap |
| `-XX:CompressedClassSpaceSize=128m` | Điều chỉnh class-space reservation/khả năng sử dụng khi bật compressed class pointers | Không phải lượng committed ngay lúc khởi động |
| `-XX:+UseCompressedClassPointers` | Cho phép compressed class pointers khi môi trường hỗ trợ | Không phải nén Java object references một cách tổng quát |
| `-XX:-UseCompressedClassPointers` | Vô hiệu class-pointer compression khi VM hỗ trợ | Không có nghĩa mọi class metadata biến mất |
| `-XX:+UseCompressedOops` | Dùng compressed ordinary object references khi môi trường hỗ trợ | Không đồng nhất compressed oops với class-space |
| `-XX:MetaspaceReclaimPolicy=balanced` | Chính sách reclamation trên HotSpot từ JEP 387 | Không giải quyết class-loader leak đang còn reachable |
| `-XX:NativeMemoryTracking=summary` | Thu thập số liệu native memory phục vụ `jcmd VM.native_memory` | Tăng chi phí tracking; cần bật đúng thời điểm JVM khởi động |

Các cờ trên là **HotSpot-specific**, không phải option bắt buộc của mọi JVM. Phiên bản, kiến trúc, GC và ergonomics có thể thay đổi giá trị mặc định, tương tác flag hoặc khả năng hỗ trợ.

### 7.1. Ví dụ đặt ngưỡng, không coi là cấu hình chuẩn cho production

```bash
java -Xmx512m -XX:MaxMetaspaceSize=256m -XX:CompressedClassSpaceSize=128m MyApp
```

Đây là **lệnh minh họa** khi `MyApp` đã được build thành công và nằm trên classpath. Nó không phải bài tập Java độc lập; không nên copy vào production mà không đo class-loading behavior, container memory limit và workload.

Tác dụng:

- `-Xmx512m` giới hạn Java heap khoảng mức cấu hình 512 MiB (chi tiết JVM).
- `-XX:MaxMetaspaceSize=256m` đặt trần metadata.
- `-XX:CompressedClassSpaceSize=128m` điều chỉnh vùng compressed class space khi khả dụng.

**Không suy luận tổng RAM tối đa của tiến trình là `512 + 256 + 128 = 896 MiB`**. Vì class space đã liên quan giới hạn metadata, còn thread stacks, code cache, GC native memory và vùng khác cũng chiếm tài nguyên ngoài heap. Tính tổng bằng cách cộng các flag như trên là sai.

### 7.2. MetaspaceSize khác MaxMetaspaceSize

Tên dễ làm người học lẫn:

- `MetaspaceSize` ảnh hưởng **ngưỡng liên quan GC** cho metadata, có thể được runtime điều chỉnh.
- `MaxMetaspaceSize` là **giới hạn trần** cho metadata allocation/commit mà VM thực thi theo chính sách của nó.

Tăng `MetaspaceSize` có thể giảm những lần GC sớm do vượt ngưỡng metadata trong một số workload, nhưng **không tự sửa việc giữ class loader**. Tăng `MaxMetaspaceSize` có thể kéo dài thời gian trước khi OOME nếu metadata không còn giải phóng được; **không tự giải quyết root cause**.

### 7.3. Nên xem cờ thực tế của JVM, đừng suy từ lệnh ghi trên wiki

Dùng:

```bash
java -XX:+PrintFlagsFinal -version
```

Sau đó tìm các flag `MetaspaceSize`, `MaxMetaspaceSize`, `CompressedClassSpaceSize`, `UseCompressedClassPointers`, `UseCompressedOops` khi được runtime hỗ trợ. Output rất dài và thay đổi theo JDK; không dùng một snapshot từ máy khác làm thông số mặc định cho mọi container.

Với JVM đang chạy, `jcmd <pid> VM.flags` cho phép xem một phần flag thực tế.

## 8. Vì sao class unloading quan trọng với Metaspace?

### 8.1. Class được nạp không tự biến mất khi method return

Một class được nạp có thể tồn tại trong JVM suốt thời gian ứng dụng nếu defining loader của nó và class metadata vẫn còn reachable theo các quy tắc JVM/GC.

Các tình huống phổ biến:

- Class của bootstrap/platform/system/application loader có vòng đời dài.
- Plugin được load qua một custom `ClassLoader`.
- Framework sinh nhiều class động (proxies, bytecode enhancement).
- Reload triển khai ứng dụng tạo những loaders mới.
- Thread, `ThreadLocal`, listener, cache hoặc static registry vô tình giữ reference tới loader cũ.

**Metaspace tăng không nhất thiết chứng minh leak.** Một ứng dụng có warm-up, lazily loaded classes hoặc thêm module mới có thể tăng metadata rồi ổn định. Cần xem mức tăng **qua nhiều chu kỳ hoạt động/GC/unloading**, không phán đoán chỉ từ một điểm đo.

### 8.2. Vòng đời metadata và unload

```text
Load class / define class
          |
          v
Metadata cấp phát cho class-loader data
          |
          v
Class còn được dùng / reachable? ---- có ----> tiếp tục giữ metadata
          |
         không
          v
GC có thể unload class / loader khi phù hợp
          |
          v
Metaspace chunks được tái sử dụng hoặc
committed memory được reclaim (tùy JVM)
```

Class unloading gắn với các điều kiện reachability, phiên bản, GC và cài đặt thực tế. **Không có cam kết cứ gọi `System.gc()` là unload toàn bộ class loader đang không còn dùng**; JVM có quyền xử lý lời gợi ý GC và chưa chắc unload xảy ra ngay.

### 8.3. Ví dụ một class-loader leak

Giả sử ứng dụng plugin có code dạng:

```java
// Sơ đồ minh họa, chưa phải ứng dụng độc lập:
static final java.util.List<ClassLoader> KEEP_FOREVER =
        new java.util.ArrayList<>();

void reloadPlugin() {
    ClassLoader loader = createPluginLoader();
    KEEP_FOREVER.add(loader);        // Cố tình giữ mọi loader đã tạo.
    // Nạp class của plugin bằng loader.
}
```

Nếu lần reload nào cũng thêm loader vào `KEEP_FOREVER`, những loaders cũ có thể tiếp tục reachable. Class metadata không được thu hồi như kỳ vọng.

Thêm bộ nhớ vào `-Xmx` không trực tiếp sửa vấn đề class metadata native được giữ. Tăng `MaxMetaspaceSize` cũng chỉ dời giới hạn nếu việc tạo loader không dừng.

### 8.4. Giải pháp về vòng đời

- Gỡ plugin khỏi registries/caches đúng cách.
- Đóng những loader có resource quản lý cần đóng, ví dụ `URLClassLoader.close()`, nhưng nhớ rằng **đóng URLClassLoader không tự ép unload mọi class**.
- Dừng threads của plugin, bỏ context class loader không còn cần.
- Xóa listeners, scheduled tasks, ThreadLocals và references xuyên từ host sang plugin.
- Giảm sinh class/proxy không giới hạn và dùng caching đúng scope.
- Đo lại unload/classloader counts sau mỗi chu kỳ reload.

Cần **quy trách nhiệm sở hữu object/loader** rõ ràng hơn là chỉ đặt một dung lượng Metaspace cực lớn.

## 9. Hai thông báo OutOfMemoryError dễ bị nhầm

### 9.1. `OutOfMemoryError: Metaspace`

Thông báo thường gặp:

```text
java.lang.OutOfMemoryError: Metaspace
```

Nó gợi ý **metadata allocation** không thể tiếp tục trong điều kiện runtime thực tế: có thể do `MaxMetaspaceSize`, native memory pressure, class-loader retention hoặc yếu tố khác. Thông báo và hành vi phụ thuộc phiên bản HotSpot.

Phân tích:

1. Kiểm tra cờ `MaxMetaspaceSize` có bị đặt quá thấp hay không.
2. Xem used/committed, số lượng classes/loaders và xu hướng theo thời gian.
3. Tìm các loaders tăng mãi hoặc tồn tại sau redeploy.
4. Kiểm tra native memory/container giới hạn; không chỉ heap.
5. Sửa nguồn tăng bất thường, sau đó mới điều chỉnh trần cho workload thật.

### 9.2. `OutOfMemoryError: Compressed class space`

Thông báo thường gặp khi dùng compressed class pointers:

```text
java.lang.OutOfMemoryError: Compressed class space
```

Nó gợi ý vùng **class metadata được quản lý trong compressed class space** đã không thể đáp ứng cấp phát, không đơn giản là “Java heap đầy”. Điều tra `CompressedClassSpaceSize`, cờ pointer compression, số lượng classes/loaders và metadata pressure.

Có thể tăng class-space limit khi VM và tài nguyên cho phép, hoặc xem xét cấu hình pointer compression theo tài liệu JVM cụ thể, **nhưng phải đánh giá tác động memory/performance và compatibility**. Không khuyến cáo tùy tiện tắt compressed class pointers để che giấu vòng đời loader sai.

### 9.3. So sánh với lỗi heap

| Dấu hiệu | Vùng nghi vấn trước tiên | Điều cần kiểm tra |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Java heap | Object retention, `-Xmx`, allocation profile |
| `OutOfMemoryError: Metaspace` | Class metadata native | Metadata limits, class loaders/classes, unloading |
| `OutOfMemoryError: Compressed class space` | Compressed class metadata region | Class space limit, compressed pointers, loader churn |
| OS/container kill do vượt RAM | **Toàn bộ resident process** | Heap + metaspace + stacks + code cache + GC/native allocations |

Lỗi thực tế có thể phức tạp; đây là **hướng điều tra ban đầu**, không phải phép chứng minh nguyên nhân duy nhất.

## 10. Quan sát Metaspace bằng các công cụ JDK

Các công cụ bên dưới phù hợp với **HotSpot/JDK hiện đại**. Cú pháp/khả năng hỗ trợ tùy runtime. Trước khi dùng trên sản xuất, cân nhắc quyền truy cập, tác động của lệnh diagnostic và lượng dữ liệu in ra.

### 10.1. Bước một: xác định Java process

```bash
jcmd -l
```

Lệnh có thể in danh sách process Java và PID. Nếu có nhiều JVM, chọn **đúng PID mục tiêu**; không gửi diagnostic tới nhầm ứng dụng.

### 10.2. Xem những diagnostic commands được hỗ trợ

```bash
jcmd <pid> help
```

`<pid>` là placeholder được thay bằng PID thực tế. Không gõ dấu `<` và `>` theo nghĩa cú pháp lệnh trong shell; trong tài liệu chúng chỉ biểu thị vị trí tham số. HotSpot 17+/21 thường hỗ trợ `VM.metaspace` nhưng luôn kiểm tra lệnh thực tế.

### 10.3. Xem metadata usage

```bash
jcmd <pid> VM.metaspace
jcmd <pid> VM.metaspace basic
```

`VM.metaspace` hiển thị thống kê metadata memory. Trong các phiên bản hỗ trợ, `basic` cho tóm tắt với ít yêu cầu dừng/đồng bộ hơn; các tùy chọn khác cho breakdown theo loader, class, chunk hoặc space.

```bash
jcmd <pid> VM.metaspace show-loaders
```

Lệnh này có thể nhiều output, nhất là khi ứng dụng nạp số class lớn. Không xem output là dữ liệu đầu ra cố định; chú ý sự khác nhau của **used/committed/reserved**, các số liên quan compressed class space và từng loader.

### 10.4. Xem class loader statistics

```bash
jcmd <pid> VM.classloader_stats
```

Dùng khi nghi ngờ plugin reload/framework sinh class không thu hồi được. Theo dõi:

- Số loaders.
- Số classes mỗi loader.
- Chunks/blocks metadata hoặc dữ liệu thống kê mà phiên bản HotSpot in ra.
- Những loader type giữ nhiều class hơn mong đợi.
- Những loader vẫn tồn tại sau khi plugin lẽ ra đã được unload.

**Không lấy “loaded class count tăng” làm bằng chứng leak duy nhất.** Khi warm-up, tăng là bình thường; quan trọng là **tốc độ tăng, mức ổn định, xu hướng unloading** và liên hệ với các bước nghiệp vụ.

### 10.5. Native Memory Tracking (NMT)

Khi muốn có breakdown native memory tổng thể, khởi động JVM với:

```bash
java -XX:NativeMemoryTracking=summary -cp . MetaspaceInspectDemo
```

**Lưu ý:** đây là cờ `-XX:NativeMemoryTracking=summary` của HotSpot, không phải `-XX:+NativeMemoryTracking`. Tracking có overhead và thường phải được bật khi JVM khởi động để có số liệu cần thiết.

Sau đó:

```bash
jcmd <pid> VM.native_memory summary
```

NMT có thể giúp phân biệt các nhóm như Class, Thread, Code, GC và những native subsystems khác. Số liệu NMT không nhất thiết bao gồm **mọi allocation từ thư viện native bên ngoài JVM**, và không trực tiếp bằng RSS của process.

Trong những trường hợp phân tích theo chu kỳ, có thể dùng các thao tác baseline và summary.diff khi phiên bản HotSpot hỗ trợ:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

Dùng baseline ngay trước một workload cụ thể, thực hiện workload rồi xem diff; điều này hữu ích hơn việc chỉ đọc số tổng một lần.

### 10.6. GC và class-loading logs

Có thể chạy HotSpot với:

```bash
java -Xlog:gc+metaspace=info -cp . MetaspaceInspectDemo
```

Tùy JVM/JDK, logs cung cấp thêm dữ liệu liên quan metaspace usage khi GC hoặc ở các thời điểm liên quan. Muốn kiểm tra tags và levels thực tế:

```bash
java -Xlog:help
```

Để quan sát class loading, một số cấu hình dùng:

```bash
java -Xlog:class+load=info -cp . MetaspaceInspectDemo
```

Class-load logs thường rất nhiều. Đừng cho rằng logging chi tiết miễn phí hoặc mọi dòng load đều chứng minh một classloader leak.

## 11. Ví dụ Java 17+ độc lập để kết hợp MXBean và `jcmd`

Tạo tệp duy nhất **`MetaspaceInspectDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class MetaspaceInspectDemo {
    static final class Marker {
        static final String NAME = "Marker";
    }

    public static void main(String[] args) throws Exception {
        Class<?> loaded = Class.forName(Marker.class.getName());
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("same runtime class: "
                + (loaded == Marker.class));
        System.out.println("class loading bean available: "
                + (classes != null));
        System.out.println("loaded class count positive: "
                + (classes.getLoadedClassCount() > 0));

        System.out.println("press Enter to finish");
        new BufferedReader(new InputStreamReader(System.in)).readLine();
        System.out.println("finished");
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 MetaspaceInspectDemo.java
java MetaspaceInspectDemo
```

**Stdout chính xác khi chạy trên HotSpot/JDK tiêu chuẩn và bấm Enter ở cuối:**

```text
same runtime class: true
class loading bean available: true
loaded class count positive: true
press Enter to finish
finished
```

Mẫu trên đã được biên dịch và chạy bằng JDK 21 với `--release 17`; kết quả khớp. Những giá trị **số lượng class thực tế** và **dung lượng Metaspace** không được hardcode trong stdout vì chúng tùy runtime, workload và class-loading activity.

### 11.1. Vì sao demo chờ Enter?

Chương trình giữ tiến trình sống để bạn có thể chạy `jcmd` từ **một terminal khác**:

```bash
jcmd -l
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.flags
```

Sau khi chụp thống kê, quay lại terminal chạy `MetaspaceInspectDemo` và nhấn Enter để chương trình in `finished` rồi thoát.

Nếu đang chạy dưới IDE/CI không cấp tương tác stdin, lời gọi `readLine()` có thể nhận EOF và chương trình kết thúc ngay. Trong tình huống đó, chạy trực tiếp từ terminal tương tác khi cần inspection.

### 11.2. MXBean hiển thị gì?

`ClassLoadingMXBean` là API chuẩn để truy xuất những số đếm class loading tổng thể, ví dụ:

```java
// Minh họa bên trong phương thức:
ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();
int current = bean.getLoadedClassCount();
long total = bean.getTotalLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
```

Các số này **có thể thay đổi trong lúc chạy**, nên không nên công bố một “stdout chính xác” cho chúng. Chúng hữu ích để theo dõi xu hướng cùng thời gian/GC/logs, nhưng không đủ để biết chi tiết từng loader hoặc mỗi metadata allocation.

### 11.3. MemoryPoolMXBean có thể hiện Metaspace và class space

Trên HotSpot có thể truy vấn:

```java
// Đoạn code minh họa trong phương thức:
for (java.lang.management.MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {
    System.out.println(pool.getName() + ": " + pool.getUsage());
}
```

Các pool names và values **không cố định theo mọi JVM**. Có thể thấy `Metaspace` và `Compressed Class Space` nếu cấu hình phù hợp; khi compressed class pointers không sử dụng, pool class-space có thể không xuất hiện theo cách bạn kỳ vọng.

Không dùng output một lần để quyết định đặt flag cho production. Cần so sánh theo thời gian và workload.

## 12. So sánh PermGen, Metaspace và compressed class space

| Tiêu chí | **PermGen (lịch sử)** | **Metaspace (HotSpot 8+)** | **Compressed class space (khi bật)** |
| --- | --- | --- | --- |
| Tồn tại trong HotSpot hiện đại? | **Không** từ JDK 8 | **Có** | **Có điều kiện** trên cấu hình hỗ trợ |
| Vai trò chính | Cấp phát class metadata theo mô hình cũ | Cơ chế metadata allocation ở native memory | Vùng metadata class cho compressed class pointers |
| Quan hệ với Java heap | Vùng/GC generation riêng trong HotSpot cũ; không phải Java heap ứng dụng thông thường | **Ngoài Java heap**, dùng native memory | **Ngoài Java heap**, là vùng riêng liên quan Metaspace |
| Cờ điển hình | `PermSize`, `MaxPermSize` | `MetaspaceSize`, `MaxMetaspaceSize` | `CompressedClassSpaceSize` |
| Lỗi OOME thường gặp | `PermGen space` | `Metaspace` | `Compressed class space` |
| Giải phóng metadata | Theo chính sách GC/class unloading cũ | Tái sử dụng/reclaim gắn với unloading và allocator | Cũng phụ thuộc metadata/class unloading và cơ chế class-space |
| Diễn giải kích thước | Giới hạn vùng theo thế hệ cũ | Used/committed/reserved cần phân biệt | Reservation thường lớn nhưng commit theo nhu cầu |
| Đặc tả JVMS bắt buộc tên này? | Không | Không | Không |

Điểm cần nhớ: **Compressed class space không phải hậu duệ riêng của PermGen**; nó là chi tiết triển khai **bên trong thiết kế HotSpot Metaspace có compressed class pointers**. Tên gọi dễ gây nhầm, nhưng mục đích và cách cấp phát khác nhau.

### 12.1. Vì sao JDK 8 không loại bỏ OutOfMemoryError metadata?

Việc loại bỏ một vùng giới hạn cứng kiểu PermGen không làm class metadata trở nên vô hạn. Native memory vẫn có giới hạn thực tế, JVM có cờ trần, container có giới hạn bộ nhớ, và class loader leak có thể tiếp tục giữ metadata.

Một ứng dụng chỉ tăng `-XX:MaxPermSize` ở JDK 7 rồi nâng lên JDK 17 mà không thay cách giám sát có thể gặp tình huống giám sát “PermGen” bị mất, trong khi **Metaspace** mới là nơi cần quan sát.

### 12.2. “Metaspace nằm trên native heap” có chính xác tuyệt đối không?

Nói **Metaspace sử dụng native memory** là phù hợp. Nhưng “mọi byte Metaspace cấp phát bằng `malloc` trên C heap” không chính xác đối với cách HotSpot thường quản lý metadata: nó có cơ chế reserve/commit các vùng địa chỉ ảo, thường sử dụng ánh xạ bộ nhớ và allocator/chunks riêng. Vì vậy thuật ngữ **native memory**, **reserved address space** và **committed pages** thường chính xác hơn câu “được malloc hết ngay”.

## 13. JEP 387 — Elastic Metaspace và ý nghĩa thực tế

**JEP 387: Elastic Metaspace** đi vào JDK 16. Mục tiêu là cải thiện quản lý native memory dành cho metadata để **tái sử dụng hiệu quả hơn** và **trả bộ nhớ đã commit về hệ điều hành kịp thời hơn**, nhất là những workload có nhiều class loaders nhỏ hoặc liên tục load/unload.

Trước đây, class metadata không còn dùng có thể dẫn đến việc allocator giữ lại không gian committed lớn hơn mong muốn. Elastic Metaspace thiết kế lại một số cấu trúc quản lý và reclamation để giảm footprint.

### 13.1. Các chính sách reclamation

Một cờ trên HotSpot hiện đại:

```text
-XX:MetaspaceReclaimPolicy=balanced
```

Tùy bản JDK, các lựa chọn có thể gồm:

- `balanced`: chính sách cân bằng (thường là mặc định).
- `aggressive`: reclamation tích cực hơn, có thể tăng chi phí quản lý.
- `none`: tắt một số cơ chế reclamation như chính sách tương ứng mô tả.

Các option là **chi tiết HotSpot**, cần xác nhận phiên bản và mục tiêu tuning.

### 13.2. Elastic không đồng nghĩa “chắc chắn trả hết RAM”

Nếu loader và class vẫn reachable thì metadata vẫn **cần tồn tại**. Elastic Metaspace không thay đổi các quy tắc reachability. Nếu một cache giữ hàng trăm loader cũ, policy aggressive cũng không thể biến các class đang sống thành class đã unload.

Ngay cả khi class được unload, tài nguyên runtime khác, fragmentation, allocator management và hoạt động GC khiến committed memory có thể không trở lại chính xác mức khởi động.

## 14. Một quy trình thực tế khi Metaspace tăng liên tục

Giả sử JVM server có heap vẫn ổn định nhưng RSS và Metaspace committed tăng sau mỗi lần reload plugin.

### Bước 1 — Ghi nhận môi trường

Thu thập:

```bash
java -version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

Xác định JVM vendor/build, kiến trúc, GC, container limits và những flag memory được đặt.

### Bước 2 — Phân biệt các vùng bộ nhớ

Thu:

```bash
jcmd <pid> VM.metaspace
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.heap_info
```

Nếu NMT đã bật từ đầu:

```bash
jcmd <pid> VM.native_memory summary
```

Không gộp heap, Metaspace, compressed class space và resident process thành một con số không nguồn gốc.

### Bước 3 — So sánh trước/sau workload lặp lại

Lấy baseline trước khi reload plugin nhiều lần. Ghi nhận:

- Số class loader hiện tồn tại và loại loader.
- Số classes của các loaders.
- Metaspace used/committed (nếu phân tách class-space thì ghi riêng).
- Số unloaded classes theo thời gian nếu có.
- Heap/RSS cùng các hoạt động GC.

Nếu sau mỗi vòng, số loaders vẫn tăng, metadata used tăng và không có dấu hiệu unload tương ứng, điều tra **class loader retention**.

### Bước 4 — Tìm reference giữ loaders

Khảo sát:

- Static registries, callback listeners, JMX registrations.
- Executor threads và thread context class loaders.
- ThreadLocal values/keys, scheduled tasks.
- Caches của framework, reflection/proxy frameworks.
- Resources được giữ bởi plugin hoặc class loader.
- Đối tượng host giữ instance của class do plugin loader định nghĩa.

Không giả định “`loader.close()` đã gọi” là đủ; phải xem những reference nào còn khiến loader reachable.

### Bước 5 — Điều chỉnh cờ khi có bằng chứng

Nếu class loading là hợp lý, ổn định nhưng giới hạn metadata đặt quá nhỏ, xem xét tăng `MaxMetaspaceSize` hoặc class-space cap phù hợp. Nếu là leak, **sửa leak trước**; giới hạn lớn chỉ kéo dài thời gian trước OOME.

### Bước 6 — Xác minh sau sửa

Chạy lại cùng workload với cùng JDK/config:

- Số loaders ổn định hoặc giảm sau unload.
- Metaspace **used** không tăng không giới hạn.
- Committed memory có thể giảm hoặc tái sử dụng theo policy.
- Application heap, native memory và RSS phù hợp ngân sách container.
- Không xuất hiện lỗi runtime mới do thay đổi loader lifecycle.

## 15. Những sai lầm và phát biểu cần sửa

1. **“Metaspace là một phần của Java heap.”** Sai với HotSpot 8+: class metadata của Metaspace dùng native memory ngoài Java heap.
2. **“JVMS bắt buộc mọi JVM phải có Metaspace.”** Sai. JVMS mô tả method area; Metaspace là cách triển khai HotSpot.
3. **“Tăng `-Xmx` là tăng Metaspace.”** Sai. `-Xmx` áp dụng cho Java heap.
4. **“JDK 8 chỉ đổi tên PermGen.”** Sai. Cơ chế cấp phát/accounting và vị trí metadata thay đổi đáng kể.
5. **“String intern pool chuyển sang Metaspace từ JDK 8.”** Sai. Không phải mọi cấu trúc cũ của PermGen được chuyển nguyên vào Metaspace; interned Strings đã có thay đổi từ JDK 7.
6. **“`MaxMetaspaceSize` luôn bằng `CompressedClassSpaceSize` cộng phần còn lại.”** Sai. Hai cờ điều khiển loại giới hạn khác nhau, phụ thuộc ergonomics/committed và reserved.
7. **“Compressed class space 1 GiB reserved nghĩa là 1 GiB RAM đã sử dụng.”** Sai. Reserved khác committed/used.
8. **“Compressed oops và compressed class pointers là một.”** Sai. Loại tham chiếu và mục đích khác.
9. **“Static object instances được cất trong Metaspace.”** Sai. Java objects thuộc heap; metadata class là dữ liệu native.
10. **“Mỗi instance `new` tạo một bản metadata class mới.”** Sai. Các instances thông thường của cùng runtime class chia sẻ metadata của class đã được nạp.
11. **“Class loader leak luôn làm Java heap space OOME trước.”** Sai. Metadata native cũng có thể hết trước, tùy cấu hình/workload.
12. **“`System.gc()` bảo đảm unload mọi class cũ ngay.”** Sai. Không có bảo đảm như vậy.
13. **“Elastic Metaspace đã loại bỏ mọi native memory pressure.”** Sai. Nó tối ưu reclamation, không tạo bộ nhớ vô hạn.
14. **“`MetaspaceSize` là maximum heap của metadata.”** Sai. Nó chủ yếu liên quan GC high-water mark, không là hard cap.
15. **“NMT class memory là tất cả RSS JVM.”** Sai. NMT/VM accounting và RSS phục vụ phép đo khác nhau, có phạm vi khác nhau.
16. **“Không có `Compressed Class Space` trong MXBean là JVM lỗi.”** Không. Feature/pool có thể không xuất hiện ở cấu hình tắt compressed class pointers hoặc JVM khác.
17. **“Một snapshot class count tăng chứng minh leak.”** Sai. Cần quan sát xu hướng, unloading và workload.
18. **“Đặt `-XX:-UseCompressedClassPointers` là cách chữa mọi OOME.”** Sai. Việc tắt nén có trade-offs và không thay vòng đời class loader.

## 16. Bài tập tự kiểm tra có đáp án

**Câu 1.** HotSpot JDK 17 dùng PermGen để lưu metadata lớp không?

**Đáp án:** Không. HotSpot bỏ PermGen từ JDK 8; class metadata được cấp phát qua Metaspace/native memory.

**Câu 2.** Method area của JVMS có phải luôn chính là Metaspace?

**Đáp án:** Không. Method area là khái niệm trong JVM Specification; Metaspace là cách HotSpot triển khai và cấp phát nhiều loại class metadata.

**Câu 3.** `-Xmx1g` đặt trần Metaspace bằng 1 GiB không?

**Đáp án:** Không. `-Xmx` giới hạn Java heap, không trực tiếp giới hạn native Metaspace.

**Câu 4.** `CompressedClassSpaceSize=1g` có nghĩa JVM vừa khởi động đã sử dụng 1 GiB RAM cho metadata không?

**Đáp án:** Không. Flag liên quan virtual address space reservation/capacity; committed/used có thể thấp hơn nhiều.

**Câu 5.** Tại sao `MaxMetaspaceSize=256m` và class-space reservation gần 1 GiB không phải mâu thuẫn?

**Đáp án:** Vì MaxMetaspaceSize tác động lên metadata committed/allocated theo giới hạn runtime, còn class-space reservation là **địa chỉ ảo được dành trước**, không đồng nghĩa đã commit hết.

**Câu 6.** Hai custom class loaders định nghĩa hai bản của `example.Plugin`. Có thể cần hai tập metadata không?

**Đáp án:** Có. Runtime class identity phụ thuộc cả binary name và defining loader, nên hai định nghĩa độc lập có metadata riêng.

**Câu 7.** Sau khi `plugin = null`, metadata của plugin class chắc chắn được giải phóng chưa?

**Đáp án:** Chưa chắc. Class loader/classes có thể còn reachable bởi caches, threads, static registries, listeners hoặc những tham chiếu khác. Class unloading không tức thì.

**Câu 8.** Lệnh nào cho thống kê chi tiết Metaspace của một HotSpot JVM đang chạy?

**Đáp án:** `jcmd <pid> VM.metaspace` khi JVM hỗ trợ. Với loader breakdown có thể dùng `jcmd <pid> VM.classloader_stats`.

**Câu 9.** Muốn dùng `VM.native_memory summary` cần chuẩn bị gì?

**Đáp án:** Trong HotSpot thường phải bật NMT từ lúc khởi động, ví dụ `-XX:NativeMemoryTracking=summary`; công cụ có overhead và không bao gồm mọi memory do native libraries bên ngoài VM tự quản lý.

**Câu 10.** Vì sao `MemoryPoolMXBean` không thể luôn dùng để tính RSS của process?

**Đáp án:** Pool metrics thể hiện những memory pools do JVM báo cáo, không phải toàn bộ OS resident memory gồm mọi native allocations và thread stacks.

**Câu 11.** Tại sao JEP 387 không tự sửa class-loader leak?

**Đáp án:** Elastic Metaspace giúp reclaim **metadata của classes đã unload**. Nếu loader vẫn reachable, class chưa unload nên metadata vẫn cần tồn tại.

**Câu 12.** `OutOfMemoryError: Java heap space` và `OutOfMemoryError: Metaspace` có hướng điều tra khác nhau thế nào?

**Đáp án:** Lỗi heap ưu tiên xem object heap retention và `-Xmx`; lỗi Metaspace ưu tiên xem metadata limits, class counts/loaders, unloading và native memory pressure.

**Câu 13.** `java.lang.Class` object ở heap hay Metaspace?

**Đáp án:** `java.lang.Class` mirror là Java object trong heap trên HotSpot, còn VM có các native metadata structures riêng liên kết với nó.

**Câu 14.** Vì sao không dùng `MaxPermSize` để điều chỉnh HotSpot JDK 21?

**Đáp án:** Vì PermGen đã bị loại bỏ; phải xem các cờ Metaspace/Compressed Class Space được hỗ trợ bởi bản JVM đích.

**Câu 15.** Một lần redeploy khiến Metaspace committed tăng, sau vài lần GC committed không giảm. Có kết luận chắc chắn leak không?

**Đáp án:** Chưa. Cần xem **used, số loaders/classes vẫn tồn tại, khả năng unloading, allocator caching và chính sách reclamation**. Committed có thể ổn định/được giữ để tái sử dụng; cần trend và bằng chứng reachability.

## 17. Checklist khi triển khai HotSpot trong container

Metaspace là một phần của **native memory budget**. Khi một JVM nằm trong container có giới hạn RAM, cần dành chỗ cho:

```text
Tổng giới hạn bộ nhớ container
    ├── Java heap (-Xmx)
    ├── Metaspace + compressed class space (committed)
    ├── JIT code cache
    ├── Thread stacks
    ├── GC/native VM structures
    ├── Direct buffers và native I/O
    └── Những native allocations khác
```

Các mục trên chỉ mang tính **kiểm kê nguồn tiêu thụ**; không giả định mọi field NMT là nhóm độc lập không chồng lấp hay có thể cộng các reservation thành RSS thực.

Gợi ý thực hành:

- Theo dõi RSS, heap used/committed và metadata used/committed riêng.
- Đánh giá warm-up class loading và peak loader count.
- Thử build/runtime đúng JDK đang triển khai.
- Dùng NMT ở môi trường kiểm thử hoặc production có cân nhắc overhead.
- Không đặt `-Xmx` sát toàn bộ RAM container rồi bỏ qua native memory.
- Không giảm quá thấp class-space cap nếu ứng dụng dùng nhiều dynamically generated classes.
- Tránh đặt trần quá lớn vô căn cứ, vì điều đó có thể che dấu tăng metadata bất thường.
- Xác minh bằng monitoring và workload thật, không dùng một default rule cho mọi service.

## 18. Tóm tắt

```text
HotSpot trước JDK 8:
    PermGen
      |
      +-- class metadata theo cơ chế cũ

HotSpot JDK 8+:
    Native class metadata management
      |
      +-- Metaspace (non-class metadata)
      |
      +-- Compressed class space (nếu bật compressed class pointers)
              reserved address space ≠ committed memory ≠ used bytes

Class unloading:
    class/loader không còn cần và đủ điều kiện unload
      |
      +-- metadata allocator có thể tái sử dụng/reclaim
      +-- JEP 387 (JDK 16+) cải thiện trả committed pages
```

**Kết luận trọng tâm:**

- **PermGen là lịch sử của HotSpot trước JDK 8; Metaspace là cơ chế native metadata của HotSpot từ JDK 8.**
- **Compressed class space chỉ là khu vực class metadata đặc thù khi bật compressed class pointers**, không phải toàn bộ Metaspace.
- **Reserved, committed và used phải được đọc khác nhau.** Reservation lớn chưa phải một lượng RAM đã dùng.
- **Metaspace không phải Java heap:** `-Xmx` không trực tiếp giới hạn Metaspace, và OOME Metaspace có hướng chẩn đoán khác OOME heap.
- **Class metadata có vòng đời liên quan class loading/unloading và defining class loaders.** Nếu giữ loader mãi, Metaspace có thể tăng mãi.
- **JEP 387 cải thiện độ đàn hồi nhưng không tự chữa memory leak.** Theo dõi `jcmd VM.metaspace`, `VM.classloader_stats`, NMT và workload có kiểm soát để đưa ra quyết định.

### Tài liệu chính thức và nguồn kiểm chứng

- [Oracle JDK 21 GC Tuning Guide — Class Metadata](https://docs.oracle.com/en/java/javase/21/gctuning/other-considerations.html): Metaspace native memory, compressed class pointers, class space, flags và các chỉ số memory.
- [OpenJDK JEP 122 — Remove the Permanent Generation](https://openjdk.org/jeps/122): loại bỏ PermGen khi chuyển sang JDK 8.
- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387): cải thiện allocator và reclamation từ JDK 16.
- [Oracle JDK 21 — java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): các tùy chọn `-XX:MaxMetaspaceSize`, `-XX:MetaspaceSize` và những JVM flags.
- [Oracle JDK 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.metaspace`, `VM.classloader_stats`, `VM.native_memory` và cách sử dụng diagnostic commands.
- [Oracle JDK 21 — JVM Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/): chẩn đoán native memory và các lỗi liên quan class metadata.
- [JVMS §2.5.4 — Method Area](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.4): vùng khái niệm trong đặc tả JVM, không bắt buộc chi tiết HotSpot.
- [ClassLoadingMXBean — JDK 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): số lượng classes được load/unload.
