# Phân biệt heap với bộ nhớ native của lớp trong JVM

**Chủ đề:** Java 8 → JVM và công cụ → Phân biệt heap với bộ nhớ native của lớp.

Khi một class được nạp vào JVM, có nhiều loại dữ liệu cùng tồn tại nhưng **không nằm hết trong Java heap**. Một object được tạo từ class, object `java.lang.Class` đại diện cho class, class loader, metadata mô tả class, mã máy do JIT biên dịch và các vùng nhớ mà thư viện native sử dụng có vòng đời và cơ chế quản lý khác nhau.

Trong HotSpot hiện đại, cần phân biệt ít nhất ba khái niệm:

- **Java heap:** vùng cấp phát các object và array; GC quản lý vòng đời object.
- **Metaspace / Compressed Class Space:** vùng native memory HotSpot dùng để quản lý metadata của class.
- **Các vùng native khác:** thread stacks, code cache, cấu trúc GC, direct buffer, JNI/native allocations và các tài nguyên của hệ điều hành.

Một điểm dễ nhầm: **object `Class<?>` đại diện cho class nằm trên heap, còn metadata nội bộ mô tả class nằm trong Metaspace của HotSpot**. Hai thứ có liên hệ với nhau nhưng không phải cùng một khối nhớ.

Bài này phân biệt hợp đồng trừu tượng của JVM với cách HotSpot triển khai, sau đó hướng dẫn đo heap, Metaspace, direct memory và native memory bằng các công cụ JDK hiện hành. Các ví dụ chạy trên Java 17+; những công cụ HotSpot như NMT và `jcmd VM.metaspace` cần được kiểm tra trên đúng JDK/vendor đang vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Java heap dùng để lưu gì và GC quản lý vùng này như thế nào.
2. Phân biệt object instance, array, class mirror (`java.lang.Class`) và class metadata.
3. Giải thích Method Area trong JVM Specification khác Metaspace trong HotSpot ra sao.
4. Hiểu metadata class được cấp phát trong native memory từ HotSpot JDK 8 trở đi.
5. Phân biệt Metaspace với Compressed Class Space.
6. Biết static field, instance field và metadata mô tả field khác nhau ở đâu trong HotSpot.
7. Phân biệt non-heap memory trong JMX với toàn bộ native memory của process.
8. Nhận biết Code Cache, thread stack, direct buffer, GC structures và JNI allocations.
9. Hiểu `reserved`, `committed`, `used` và vì sao chúng khác RSS.
10. Đọc `MemoryMXBean`, `MemoryPoolMXBean`, `BufferPoolMXBean` và `ClassLoadingMXBean`.
11. Dùng Native Memory Tracking (NMT) và `jcmd` để tìm nguồn native memory tăng.
12. Phân biệt `OutOfMemoryError: Java heap space`, `Metaspace`, `Compressed class space` và lỗi cấp phát native.
13. Hiểu class unloading phụ thuộc khả năng thu hồi class loader.
14. Nhận diện class-loader leak do plugin, application redeploy, ThreadLocal, thread context class loader hoặc static cache.
15. Chọn đúng công cụ cho heap leak, Metaspace growth và native memory leak.
16. Tránh điều chỉnh `-Xmx` như một cách chữa mọi vấn đề bộ nhớ.

## 2. Mô hình tổng quan

Một process Java có thể sử dụng đồng thời các vùng sau:

~~~text
                 JAVA PROCESS
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  JAVA HEAP                                                │
│  ├── object instances                                    │
│  ├── arrays                                              │
│  ├── java.lang.Class objects (class mirrors)             │
│  ├── ClassLoader objects                                 │
│  ├── static field storage trong class mirror (HotSpot)   │
│  └── direct-buffer wrapper objects                       │
│                                                          │
│  HOTSPOT NATIVE MEMORY                                    │
│  ├── Metaspace: class metadata                           │
│  ├── Compressed Class Space: một loại Klass metadata     │
│  ├── Code Cache: mã máy do JIT biên dịch                 │
│  ├── Thread / native stacks                              │
│  ├── GC structures                                       │
│  ├── Compiler / Symbol / Internal                        │
│  └── các vùng native khác của JVM                        │
│                                                          │
│  OTHER NATIVE / OS MEMORY                                 │
│  ├── DirectByteBuffer data                               │
│  ├── JNI / FFM / thư viện native                         │
│  ├── memory-mapped files                                 │
│  ├── native libraries                                    │
│  └── OS thread, socket và process resources              │
│                                                          │
└──────────────────────────────────────────────────────────┘
~~~

Sơ đồ này là cách nhìn thực tế cho HotSpot. Các ranh giới và cách cấp phát chi tiết có thể khác giữa JVM implementation, GC, hệ điều hành và phiên bản JDK.

**Đừng cộng tất cả các dòng trong sơ đồ như thể chúng là những pool độc lập hoàn toàn.** Ví dụ, NMT có category `Java Heap` trong báo cáo tổng hợp dù heap không phải native metadata; một số vùng native được memory-map; direct memory có thể được đo qua buffer pool riêng.

## 3. Java heap là gì?

Theo JVM Specification, heap là vùng runtime dùng để cấp phát **tất cả class instances và arrays**. Heap được chia sẻ giữa các JVM threads. Bộ nhớ object được thu hồi bằng automatic storage management, thường là garbage collector.

Ví dụ:

~~~java
Customer customer = new Customer();
byte[] payload = new byte[1024];
List<String> names = new ArrayList<>();
~~~

Các object/array được tạo bởi những biểu thức này thuộc mô hình cấp phát heap của Java.

Heap có các đặc điểm:

- Là vùng runtime chính để chứa object và array.
- GC xác định object nào còn reachable từ GC roots.
- Object không còn reachable có thể được thu hồi.
- Heap có thể mở rộng/thu hẹp theo cấu hình và implementation.
- `-Xms` điều khiển heap ban đầu; `-Xmx` đặt giới hạn heap tối đa.
- `OutOfMemoryError: Java heap space` xảy ra khi không thể cấp phát object trong heap theo điều kiện hiện tại.

### 3.1. Heap chứa object, không chỉ object do `new` viết trực tiếp

Ngoài các object do code ứng dụng tạo, heap còn chứa nhiều object runtime:

- String và các object wrapper.
- Collection, map, queue và các node bên trong.
- Object reflection như `Method`, `Field` khi được tạo.
- Class mirror là object `java.lang.Class`.
- Object đại diện cho class loader.
- Direct buffer wrapper, dù phần data của direct buffer nằm ngoài heap.
- Stack chunks của virtual thread trong các implementation hiện đại như HotSpot.

### 3.2. GC quản lý object, không có nghĩa GC quản lý mọi byte của process

GC chủ yếu quản lý object/array trong Java heap. GC không trực tiếp thu hồi mọi native allocation do JNI hoặc thư viện bên ngoài tạo.

Một object Java có thể chỉ là wrapper cho một vùng native memory. Khi wrapper không còn reachable, cơ chế cleanup của thư viện/runtime có thể giải phóng vùng native sau đó; thời điểm giải phóng không nhất thiết tức thời. Vì vậy, **heap giảm không bảo đảm RSS của process giảm ngay**.

### 3.3. `-Xmx` không phải giới hạn tổng bộ nhớ process

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

`-Xmx2g` giới hạn heap tối đa ở mức 2 GB. Process vẫn cần bộ nhớ cho Metaspace, code cache, thread stacks, GC, direct buffers, native libraries, memory-mapped regions và các cấu trúc khác.

Một container có giới hạn 3 GB không thể mặc định chạy an toàn chỉ vì `-Xmx` là 2 GB. Phải dành headroom cho native memory và OS/runtime overhead.

## 4. Class mirror và class metadata là hai thứ khác nhau

Khi class được JVM nạp, có hai khía cạnh cần phân biệt:

1. **Class mirror:** object Java kiểu `java.lang.Class<?>`, có thể truy cập bằng `MyType.class`.
2. **Class metadata:** cấu trúc nội bộ JVM mô tả class: tên, superclass, interfaces, field/method descriptors, runtime constant pool, metadata phục vụ linking, dispatch và reflection.

Ví dụ:

~~~java
Class<?> type = String.class;
System.out.println(type.getName());
System.out.println(type.getClass().getName());
~~~

- `type` tham chiếu đến một object `java.lang.Class` — class mirror.
- `type.getClass()` trả về class của object mirror, tức `java.lang.Class`.
- Metadata nội bộ mô tả `String` được JVM quản lý riêng.

Trong HotSpot, class mirror là một Java object trên heap. Metadata nội bộ của class được quản lý trong Metaspace native memory.

**Không nhầm `String.class` với toàn bộ metadata của `String`.** `String.class` là object đại diện; nó không phải bản sao toàn bộ class metadata.

## 5. Method Area trong JVM Specification và Metaspace trong HotSpot

Đây là điểm quan trọng nhất của bài.

### 5.1. Method Area là khái niệm trừu tượng của JVM

JVM Specification định nghĩa **Method Area** là runtime area được chia sẻ giữa các JVM threads. Nó lưu các cấu trúc theo class, ví dụ:

- Runtime constant pool.
- Field data và method data.
- Thông tin phục vụ khởi tạo class/interface.
- Cấu trúc liên quan đến method và constructor.

Specification mô tả Method Area là **logically part of the heap**, nhưng không bắt buộc implementation phải đặt nó tại một địa chỉ hay vùng vật lý cụ thể. Vị trí và chính sách quản lý do JVM implementation quyết định.

### 5.2. Metaspace là cách HotSpot triển khai class metadata

Trong HotSpot hiện đại, class metadata được cấp phát từ **native memory**, được quản lý bởi Metaspace. Đây là implementation detail của HotSpot, không phải một tên vùng nhớ bắt buộc trong mọi JVM.

Từ HotSpot JDK 8, metadata được chuyển sang native memory; vùng PermGen trước đây đã bị loại bỏ. Vì vậy:

- Với HotSpot hiện đại, `Metaspace` là vùng native quản lý class metadata.
- Không nên coi Metaspace là Java object heap.
- Không nên lấy mô tả trừu tượng Method Area trong JVMS rồi suy ra vị trí vật lý của metadata ở mọi JVM.
- Không dùng các hướng dẫn cấu hình PermGen cũ cho JDK hiện đại.

### 5.3. Quan hệ giữa ba khái niệm

| Khái niệm | Bản chất | Vị trí trong HotSpot hiện đại |
|---|---|---|
| Java heap | Vùng cấp phát object và array | Heap |
| Method Area | Runtime area trừu tượng theo JVMS | JVM implementation quyết định |
| Metaspace | Bộ quản lý class metadata của HotSpot | Native memory |
| Class mirror | Object `java.lang.Class` đại diện class | Java heap |
| Compressed Class Space | Vùng cho một loại class metadata khi dùng compressed class pointers | Native virtual memory |

**Method Area và Metaspace không phải hai tên đồng nghĩa ở cấp đặc tả.** Metaspace là cách HotSpot thực hiện phần class metadata tương ứng.

## 6. Class metadata trong Metaspace gồm những gì?

Metadata mô tả class và hỗ trợ JVM thực thi class. Tùy HotSpot/JDK, cấu trúc có thể gồm:

- Metadata mô tả class/interface.
- Tên class và cấu trúc liên kết.
- Field metadata: tên, kiểu, modifier và layout.
- Method metadata: tên, descriptor, modifier và cấu trúc phục vụ dispatch.
- Runtime constant pool và dữ liệu liên quan.
- Metadata về interfaces, superclass, annotations và generic signatures.
- Các cấu trúc phụ trợ phục vụ verification, linking, reflection và runtime.

Đây là metadata mô tả **cấu trúc và hành vi của class**. Nó không phải toàn bộ giá trị dữ liệu mà các instance đang giữ.

Ví dụ class:

~~~java
public class Account {
    private long id;
    private String owner;

    public String displayName() {
        return owner + "#" + id;
    }
}
~~~

Có thể phân biệt:

- Metadata lưu rằng `Account` có field `id` kiểu `long`, field `owner` kiểu `String`, method `displayName()` và method descriptor tương ứng.
- Mỗi object `Account` có giá trị `id` và reference `owner` của riêng instance.
- Object String mà `owner` tham chiếu đến là heap object.
- Metadata mô tả field/method được HotSpot quản lý trong Metaspace.

**Metaspace không phải nơi chứa mọi giá trị của mọi object thuộc class đó.**

## 7. Static field và instance field nằm ở đâu?

Cần tách **metadata mô tả field** khỏi **giá trị của field**.

| Thành phần | HotSpot hiện đại |
|---|---|
| Metadata mô tả field name/type/modifier | Metaspace |
| Giá trị instance field | Bên trong object instance trên heap |
| Object được instance field tham chiếu | Heap |
| Class mirror (`java.lang.Class`) | Heap |
| Giá trị static field của class Java | Lưu trong class mirror trên heap trong HotSpot |
| Object được static reference field tham chiếu | Heap |

Phần lưu giá trị static field trong class mirror là **chi tiết triển khai HotSpot**, không phải layout vật lý mà JVMS bắt buộc mọi JVM phải dùng.

Ví dụ:

~~~java
public class ClassMirrorDemo {
    static class SampleType {
        static final byte[] CACHE = new byte[1024];
        private final byte[] payload = new byte[2048];
    }

    public static void main(String[] args) {
        Class<?> mirror = SampleType.class;
        SampleType instance = new SampleType();

        System.out.println("mirror="
                + mirror.getName());

        System.out.println("staticPayload="
                + SampleType.CACHE.length);

        System.out.println("instancePayload="
                + instance.payload.length);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ClassMirrorDemo.java
java ClassMirrorDemo
~~~

Stdout:

~~~text
mirror=ClassMirrorDemo$SampleType
staticPayload=1024
instancePayload=2048
~~~

Giải thích:

- `mirror` là reference tới object `Class` trên heap.
- `SampleType.CACHE` là static reference field. Trong HotSpot, giá trị reference này nằm trong class mirror; mảng `byte[]` mà nó trỏ đến nằm trên heap.
- `instance.payload` là instance field của object `SampleType`; mảng `byte[]` mà field trỏ đến cũng nằm trên heap.
- Metadata mô tả `CACHE`, `payload`, tên và method của `SampleType` nằm trong Metaspace.

Chương trình chứng minh cách truy cập dữ liệu và class mirror. Java không cung cấp API chuẩn để in địa chỉ vật lý của từng field hoặc khẳng định layout byte cụ thể của object.

### 7.1. String literal và runtime constant pool

Không nhầm runtime constant pool với toàn bộ object String.

- Metadata/constant-pool structures của class được JVM quản lý cùng class metadata.
- Object `String` mà ứng dụng sử dụng vẫn là Java object trên heap.
- String intern table và cách quản lý string reference là chi tiết runtime riêng; không nên gọi mọi String literal là “nằm trong Metaspace”.

## 8. Compressed Class Space là gì?

Trên HotSpot 64-bit, JVM có thể sử dụng **compressed class pointers** để biểu diễn class metadata pointer bằng offset 32-bit trong một vùng địa chỉ được reserve.

Vùng địa chỉ dành cho cơ chế này được gọi là **Compressed Class Space**.

Điểm cần nhớ:

- Chỉ một loại class metadata (`Klass` metadata) nằm trong compressed class space.
- Các class metadata khác vẫn nằm trong Metaspace.
- Vùng compressed class space được reserve khi JVM khởi động và commit dần khi cần.
- `-XX:CompressedClassSpaceSize` điều chỉnh kích thước vùng này.
- `-XX:UseCompressedClassPointers` điều khiển cơ chế compressed class pointers trên HotSpot.
- `-XX:MaxMetaspaceSize` giới hạn tổng phần metadata committed theo quy tắc HotSpot, bao gồm compressed class space và các vùng metadata còn lại.

**Compressed Class Space không phải Java heap và không phải một bản copy của toàn bộ Metaspace.**

### 8.1. Phân biệt `OutOfMemoryError: Metaspace` và `Compressed class space`

Hai lỗi có liên quan nhưng chỉ ra pool khác nhau:

- `OutOfMemoryError: Metaspace`: không thể cấp phát thêm class metadata trong vùng Metaspace theo giới hạn/cấu hình hiện tại.
- `OutOfMemoryError: Compressed class space`: vùng dành cho compressed class metadata đã hết khả năng cấp phát.

Oracle HotSpot troubleshooting guide phân biệt `Klass` metadata với các metadata khác; chỉ `Klass` metadata thuộc vùng compressed class space.

Không tự động tăng cả hai flag khi chưa xác định pool nào tăng. Hãy kiểm tra báo cáo `VM.metaspace`, `VM.native_memory` và class-loader statistics trước.

## 9. Metaspace được cấp phát và thu hồi như thế nào?

HotSpot quản lý Metaspace bằng các vùng/chunk native memory:

1. JVM yêu cầu vùng nhớ từ hệ điều hành.
2. Metaspace quản lý vùng đã nhận thành các chunk.
3. Class loader cấp phát metadata từ chunk gắn với loader.
4. Khi class được unload, metadata tương ứng có thể được giải phóng.
5. Chunk được tái sử dụng hoặc trả lại cho hệ điều hành tùy tình trạng allocator và implementation.

Vòng đời metadata thường gắn với **class loader đã định nghĩa class**. Vì thế, ứng dụng tạo nhiều class loader động nhưng giữ chúng sống mãi có thể làm Metaspace tăng theo thời gian.

### 9.1. Reserved, committed, used

Ba số liệu này không giống nhau:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Reserved** | Vùng địa chỉ ảo JVM đã giữ chỗ |
| **Committed** | Vùng đã được JVM commit để dùng |
| **Used** | Phần thực tế đang được allocator sử dụng cho metadata/object tương ứng |

Ví dụ một vùng Metaspace có thể reserve dung lượng lớn nhưng chỉ commit một phần nhỏ. Không được nhìn số reserved rồi kết luận toàn bộ lượng đó đang chiếm RAM vật lý.

RSS/Working Set của process cũng không bằng chính xác `committed`: hệ điều hành có chính sách paging, memory mapping và chia sẻ trang riêng.

### 9.2. `-XX:MetaspaceSize` và `-XX:MaxMetaspaceSize`

- `-XX:MetaspaceSize` là ngưỡng ban đầu/high-water mark có liên quan đến thời điểm GC được kích hoạt để thu hồi class metadata.
- `-XX:MaxMetaspaceSize` là giới hạn trên cho dung lượng metadata native mà HotSpot được phép commit theo cấu hình.
- `-XX:CompressedClassSpaceSize` điều chỉnh vùng compressed class space.

**`MetaspaceSize` không phải giới hạn tối đa Metaspace.** Khi muốn giới hạn tổng dung lượng, cần hiểu `MaxMetaspaceSize` và compressed class space.

Không tăng flag theo cảm tính. Nếu class count tăng liên tục do class loader leak, tăng giới hạn chỉ trì hoãn lỗi.

## 10. Các vùng native khác ngoài Metaspace

Native memory của JVM rộng hơn bộ nhớ metadata class.

| Vùng | Nội dung điển hình | Cách theo dõi |
|---|---|---|
| Metaspace | Class metadata | MemoryPoolMXBean, `jcmd VM.metaspace`, NMT |
| Compressed Class Space | Compressed `Klass` metadata | MemoryPoolMXBean, NMT |
| Code Cache | Native machine code do JIT biên dịch | CodeHeap pools, `jcmd Compiler.codecache`, NMT |
| Thread | Thread structures, platform thread stacks và tài nguyên liên quan | NMT, thread dump, OS tools |
| GC | Card table, GC structures, vùng phụ trợ collector | NMT, GC logs |
| Compiler | Bộ nhớ dùng cho JIT/compiler | NMT |
| Direct buffer | Data của direct/mapped buffers | BufferPoolMXBean |
| JNI / native library | `malloc`, C/C++ allocations, native handles | OS tools hoặc profiler native |
| Memory-mapped file | Mapping file vào virtual address space | BufferPoolMXBean nếu qua mapped buffer, OS tools |
| Native library / OS | Shared libraries, socket buffers và tài nguyên process | OS monitoring |

### 10.1. Code Cache không phải Metaspace

JIT compiler có thể biên dịch method thành native machine code và lưu trong **Code Cache**.

- Metaspace lưu metadata mô tả class/method.
- Code Cache lưu mã máy đã biên dịch.
- Hai vùng đều không phải Java object heap.
- Code Cache có thể có các code heap/pool khác nhau tùy HotSpot.

Không chẩn đoán Metaspace leak chỉ vì Code Cache tăng.

### 10.2. Thread stack và native stack

Platform thread thường được triển khai gắn với một OS thread; OS thread có stack và tài nguyên native riêng. Số lượng platform threads lớn có thể làm native memory tăng đáng kể.

Từ Java 21, **virtual threads** là một loại `Thread` được runtime quản lý và không gắn cố định một-một với OS thread. Stack chunks của virtual threads được lưu trong heap; các carrier platform threads vẫn dùng tài nguyên OS/native tương ứng.

Do đó, không nhân số virtual threads với native stack size để tính tổng native stack. Hãy phân biệt số platform threads/carrier threads với số virtual threads.

### 10.3. DirectByteBuffer: wrapper trên heap, data ngoài heap

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(1024 * 1024);
~~~

- Object `ByteBuffer`/wrapper là Java object trên heap.
- Vùng data của direct buffer được cấp phát ngoài heap.
- `BufferPoolMXBean` có thể hiển thị pool `direct` và `mapped`.
- Dữ liệu native có thể còn được giữ cho tới khi cơ chế cleanup/GC phù hợp chạy; không dựa vào thời điểm GC để quản lý tài nguyên quan trọng.

Không nhầm `ByteBuffer.allocate(…)` với `ByteBuffer.allocateDirect(…)`: loại thứ nhất dùng heap buffer; loại thứ hai dùng direct memory.

## 11. Heap, non-heap và native memory không phải ba tên thay thế nhau

Trong Java Management API:

- `MemoryMXBean.getHeapMemoryUsage()` báo usage của Java heap.
- `MemoryMXBean.getNonHeapMemoryUsage()` báo usage của các memory pool được phân loại non-heap.
- `MemoryPoolMXBean` cho số liệu từng pool, ví dụ Metaspace, Compressed Class Space, CodeHeap.
- `BufferPoolMXBean` báo pool direct/mapped buffers.

**Non-heap trong JMX không đồng nghĩa với toàn bộ native memory của process.** Ví dụ, native allocations của JNI, nhiều thư viện native và các vùng OS-level không nhất thiết xuất hiện trong `getNonHeapMemoryUsage()`.

Tương tự, `Runtime.totalMemory()`, `freeMemory()` và `maxMemory()` là các số liệu liên quan Java heap; không phải phép đo toàn bộ RSS.

### 11.1. Bảng đối chiếu công cụ

| API/công cụ | Đo gì | Không dùng để kết luận gì |
|---|---|---|
| `MemoryMXBean` | Heap và non-heap usage | Tổng native memory process |
| `MemoryPoolMXBean` | Usage từng pool JVM công bố | Tất cả JNI/native allocations |
| `BufferPoolMXBean` | Direct/mapped buffer pools | Mọi native memory khác |
| `ClassLoadingMXBean` | Số class đang load, tổng load/unload | Số byte Metaspace chính xác |
| `jcmd VM.metaspace` | Thống kê Metaspace/class loaders | Toàn bộ RSS process |
| NMT | Native allocations nội bộ HotSpot theo category | Mọi allocation bên ngoài JVM |
| Heap dump | Object và reference graph trong Java heap | Native allocations không có Java object tương ứng |
| OS tools | RSS, virtual memory map, process-level memory | Ngữ nghĩa object/class trong Java nếu chỉ nhìn số tổng |

## 12. Demo Java: đo heap, non-heap, Metaspace, direct buffer và class loading

Chương trình dưới đây dùng API quản lý chuẩn để quan sát các pool mà JVM công bố.

Lưu thành **`MemoryAreaProbe.java`**:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.nio.ByteBuffer;
import java.util.List;

public class MemoryAreaProbe {
    private static void printUsage(
            String label, MemoryUsage usage) {

        if (usage == null) {
            System.out.println(label + "=unavailable");
            return;
        }

        System.out.println(label + ".used=" + usage.getUsed());
        System.out.println(label + ".committed="
                + usage.getCommitted());
        System.out.println(label + ".max=" + usage.getMax());
    }

    public static void main(String[] args) {
        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();

        printUsage("heap", memory.getHeapMemoryUsage());
        printUsage("nonHeap", memory.getNonHeapMemoryUsage());

        System.out.println("-- memory pools --");

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {

            MemoryUsage usage = pool.getUsage();

            if (usage != null) {
                System.out.println(
                        "pool=" + pool.getName()
                        + ",type=" + pool.getType()
                        + ",used=" + usage.getUsed()
                        + ",committed=" + usage.getCommitted());
            }
        }

        // Giữ reference sống trong lúc đọc buffer pool.
        ByteBuffer direct =
                ByteBuffer.allocateDirect(1024 * 1024);

        System.out.println("-- buffer pools --");

        List<BufferPoolMXBean> buffers =
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class);

        for (BufferPoolMXBean buffer : buffers) {
            System.out.println(
                    "buffer=" + buffer.getName()
                    + ",count=" + buffer.getCount()
                    + ",capacity=" + buffer.getTotalCapacity()
                    + ",used=" + buffer.getMemoryUsed());
        }

        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("classes.loaded="
                + classes.getLoadedClassCount());

        System.out.println("classes.totalLoaded="
                + classes.getTotalLoadedClassCount());

        System.out.println("classes.unloaded="
                + classes.getUnloadedClassCount());

        System.out.println("direct.capacity="
                + direct.capacity());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MemoryAreaProbe.java
java MemoryAreaProbe
~~~

**Ví dụ hình dạng output** (số byte, pool names và số class thay đổi theo JDK, GC, provider và thời điểm chạy):

~~~text
heap.used=<value>
heap.committed=<value>
heap.max=<value>
nonHeap.used=<value>
nonHeap.committed=<value>
nonHeap.max=<value>
-- memory pools --
pool=Metaspace,type=Non-heap memory,used=<value>,committed=<value>
pool=Compressed Class Space,type=Non-heap memory,used=<value>,committed=<value>
pool=CodeHeap ...,type=Non-heap memory,used=<value>,committed=<value>
...
-- buffer pools --
buffer=direct,count=1,capacity=1048576,used=<value>
buffer=mapped,count=0,capacity=0,used=0
...
classes.loaded=<value>
classes.totalLoaded=<value>
classes.unloaded=<value>
direct.capacity=1048576
~~~

Không so sánh các con số output giữa hai máy như một test cố định. Dùng chương trình để xác định pool nào đang hiện diện và quan sát xu hướng qua nhiều lần lấy mẫu.

### 12.1. Vì sao demo không in “Metaspace chính xác bằng bao nhiêu native memory”?

`MemoryPoolMXBean` báo usage của pool Metaspace mà HotSpot công bố. Đây là số liệu hữu ích cho class metadata, nhưng không đại diện cho mọi native allocation của process.

Nếu cần quan sát cả Thread, Code, GC, Compiler, Internal và các category khác, dùng NMT.

## 13. Native Memory Tracking (NMT)

**Native Memory Tracking** là công cụ của HotSpot dùng để theo dõi native memory allocation nội bộ JVM.

NMT có hai mức:

- `summary`: tổng hợp theo category.
- `detail`: chi tiết allocation/call site hơn.

NMT bị tắt mặc định. Phải bật khi khởi chạy JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Hoặc:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

Sau đó dùng `jcmd` với đúng PID và user chạy JVM:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Tạo baseline sau khi ứng dụng warm-up:

~~~bash
jcmd <pid> VM.native_memory baseline
~~~

Đọc mức tăng kể từ baseline:

~~~bash
jcmd <pid> VM.native_memory summary.diff
~~~

Nếu cần allocation site chi tiết hơn và JVM đã khởi động với `detail`:

~~~bash
jcmd <pid> VM.native_memory detail
jcmd <pid> VM.native_memory detail.diff
~~~

### 13.1. NMT phân loại những vùng nào?

Các category thường gặp trong báo cáo HotSpot:

| Category | Nội dung |
|---|---|
| Java Heap | Heap object/array |
| Class | Class metadata, Metaspace và class space |
| Thread | Thread structures, stack và tài nguyên liên quan |
| Code | Native code cache |
| GC | Cấu trúc hỗ trợ garbage collector |
| Compiler | Bộ nhớ cho compiler |
| Internal | Bộ nhớ nội bộ khác của JVM |
| Other | Category khác chưa phân loại riêng |
| Symbol | Symbol metadata |
| Native Memory Tracking | Bộ nhớ dùng cho chính NMT |
| Arena Chunk | Các arena chunks |
| Logging / Arguments / Module | Các cấu trúc phụ trợ tương ứng |

Các category có thể thay đổi theo phiên bản HotSpot. Đọc output thực tế của JDK đang chạy thay vì dựa vào một bảng cứng từ phiên bản cũ.

### 13.2. NMT có giới hạn

NMT:

- Chỉ theo dõi native memory nội bộ HotSpot theo phạm vi công cụ hỗ trợ.
- Không theo dõi đầy đủ allocations do JNI code/thư viện native bên ngoài JVM tạo.
- Không cung cấp toàn bộ thông tin memory của CDS archive.
- Có overhead: Oracle ghi nhận mức giảm hiệu năng khoảng 5–10% trong tài liệu chẩn đoán; cần cân nhắc khi bật trên production.
- Bản thân NMT cũng sử dụng một lượng memory để tracking.

Vì vậy **NMT không thay thế công cụ OS/native profiler** nếu nghi ngờ JNI library hoặc C/C++ code bị leak.

## 14. `jcmd` hiện hành để chẩn đoán class memory

Các lệnh hữu ích trên HotSpot JDK hiện đại:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
jcmd <pid> VM.metaspace show-loaders=true
jcmd <pid> VM.classes
jcmd <pid> GC.class_histogram
~~~

Ý nghĩa:

- `VM.native_memory`: xem native memory theo category.
- `VM.classloader_stats`: thống kê theo class loader.
- `VM.metaspace`: xem thống kê Metaspace.
- `VM.metaspace show-loaders=true`: xem usage theo loader.
- `VM.classes`: liệt kê các class đang được load.
- `GC.class_histogram`: thống kê object types trong Java heap.

Các lệnh là diagnostic commands của HotSpot, không phải API Java portable cho mọi JVM. Kiểm tra `jcmd <pid> help` trên đúng runtime để biết command/option được hỗ trợ.

### 14.1. Khi nghi ngờ class loader giữ Metaspace

Có thể bắt đầu bằng:

~~~bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace show-loaders=true
jcmd <pid> VM.native_memory summary
~~~

Theo dõi:

- Số class loaders.
- Số class đang được load.
- Số bytes metadata theo loader.
- Metaspace used/committed/reserved.
- Category `Class` trong NMT qua nhiều baseline.

Nếu một loader hoặc một nhóm loader liên tục tăng mà không unload, điều tra lifecycle của plugin/redeploy/framework tạo class động.

### 14.2. Khi nghi ngờ heap leak

Dùng các công cụ heap:

~~~bash
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump heap.hprof
~~~

Heap dump có thể lớn và ảnh hưởng hiệu năng/latency. Cần lưu ở nơi bảo mật vì dump có thể chứa token, dữ liệu cá nhân, password tạm, request payload hoặc thông tin nhạy cảm.

Heap dump không chứa toàn bộ native memory ngoài heap.

## 15. Class unloading và vòng đời Metaspace

Một class được định nghĩa bởi một class loader cụ thể. Trong HotSpot, metadata của các class do loader quản lý có vòng đời gắn với loader data.

JLS cho phép JVM unload class khi **defining class loader có thể được garbage collector thu hồi**. Điều này có nghĩa:

- Class loader còn reachable thì class của nó không thể unload.
- Loader không còn reachable là điều kiện cần; việc unload cụ thể do implementation/GC quyết định.
- Không có cam kết class được unload ngay khi một reference biến mất.
- Class được bootstrap loader định nghĩa không được unload.
- Sau khi class unload, Metaspace chunks có thể được tái sử dụng hoặc trả lại hệ điều hành tùy allocator.

### 15.1. ClassLoader object nằm ở đâu?

Object của một custom `ClassLoader` là Java object, nằm trên heap.

Nhưng metadata của các class mà loader định nghĩa được HotSpot quản lý trong Metaspace.

Đây là một cặp thường gặp khi debug:

~~~text
Heap:
  CustomClassLoader object
       |
       | quản lý / định nghĩa
       v
Native memory:
  Class metadata trong Metaspace
~~~

Nếu heap dump cho thấy nhiều classloader object đang sống, có thể có liên hệ với Metaspace tăng. Nhưng phải kiểm tra reference path và classloader statistics trước khi kết luận.

### 15.2. URLClassLoader.close() không đồng nghĩa unload class

`URLClassLoader.close()` đóng các resource/JAR mà loader đã mở. Nó không tự động làm class unload.

Để class có thể unload:

1. Dừng công việc đang chạy trong plugin.
2. Giải phóng references tới plugin classes và instances.
3. Dọn ThreadLocal/static cache/registrations.
4. Xử lý thread context class loader và thread do plugin tạo.
5. Đóng loader nếu dùng URLClassLoader.
6. Đảm bảo không còn GC root giữ loader.
7. Để GC có cơ hội thu hồi loader và class metadata.

**Không có method public `ClassLoader.unload()` để cưỡng bức unload class.** `System.gc()` chỉ là request/hint; không bảo đảm thời điểm class unload.

### 15.3. Các nguồn giữ class loader sống ngoài ý muốn

- Static map ở class loader cha giữ `Class<?>`, `Method`, `ClassLoader` hoặc instance của plugin.
- Thread pool dùng thread context class loader của plugin.
- ThreadLocal giữ object thuộc plugin.
- Executor/thread của plugin chưa dừng.
- JDBC driver, logging handler, MBean hoặc callback chưa deregister.
- JNI global reference giữ object/class.
- Cache của framework hoặc serialization/reflection giữ metadata reference.
- Shutdown hook hoặc listener còn đăng ký.

Khi class loader còn sống, metadata của các class thuộc loader vẫn có thể tiếp tục chiếm Metaspace.

## 16. Ví dụ: đo class loading count

`ClassLoadingMXBean` cho biết số class đang loaded, tổng số class đã từng load và số class đã unload.

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public class ClassLoadingProbe {
    public static void main(String[] args) {
        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("loaded="
                + bean.getLoadedClassCount());

        System.out.println("totalLoaded="
                + bean.getTotalLoadedClassCount());

        System.out.println("unloaded="
                + bean.getUnloadedClassCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ClassLoadingProbe.java
java ClassLoadingProbe
~~~

Stdout có dạng:

~~~text
loaded=<current-loaded-class-count>
totalLoaded=<total-ever-loaded-class-count>
unloaded=<total-unloaded-class-count>
~~~

Số liệu phụ thuộc ứng dụng và runtime. `loaded` là số hiện đang được load; `totalLoaded` là tổng tích lũy; `unloaded` là tổng class đã unload kể từ khi JVM chạy.

**Class count tăng không tự động chứng minh leak.** Framework có thể tạo proxy/generated classes hợp lệ. Cần quan sát xu hướng và classloader ownership.

## 17. Ví dụ: vòng đời plugin và class loader

Đoạn dưới minh họa ý tưởng kiểm tra loader bằng `WeakReference`. Đây là snippet cần thay tên plugin và JAR bằng fixture thực tế, không phải một chương trình standalone.

~~~java
static WeakReference<ClassLoader> loadPlugin(Path jar)
        throws Exception {

    URLClassLoader loader = new URLClassLoader(
            new URL[] { jar.toUri().toURL() },
            ClassLoader.getPlatformClassLoader());

    try {
        Class<?> entry = Class.forName(
                "example.plugin.Entry",
                true,
                loader);

        entry.getDeclaredConstructor().newInstance();

        return new WeakReference<>(loader);
    } finally {
        loader.close();
    }
}
~~~

Sau khi method kết thúc, nếu không còn strong reference nào khác tới loader hoặc class của plugin, loader có thể đủ điều kiện được GC thu hồi.

Để quan sát:

~~~java
WeakReference<ClassLoader> ref = loadPlugin(pluginJar);

// Kiểm tra sau một khoảng thời gian và các lần GC phù hợp.
System.out.println(ref.get() == null);
~~~

**Không viết test yêu cầu `System.gc()` phải làm `ref.get()` thành null ngay.** GC có thể bỏ qua request, JIT/runtime có thể còn giữ local reference trong stack frame, hoặc plugin còn được tham chiếu ở nơi khác. Dùng test này như công cụ quan sát lifecycle, không phải assertion thời điểm unload xác định.

## 18. Phân biệt các loại OutOfMemoryError

| Thông báo | Vùng có vấn đề thường gặp | Hướng điều tra |
|---|---|---|
| `Java heap space` | Java heap | Heap usage, GC, heap dump, retaining paths |
| `GC overhead limit exceeded` | Heap/GC pressure | Live set, allocation rate, GC logs |
| `Metaspace` | Class metadata trong Metaspace | Class count, class loaders, NMT, `VM.metaspace` |
| `Compressed class space` | Compressed `Klass` metadata | Compressed Class Space usage và class loading |
| `Direct buffer memory` | Direct buffer/native memory budget | BufferPoolMXBean, direct-buffer lifecycle |
| `unable to create native thread` | OS thread/resource/native memory | Thread count, stack reservation, OS limits |
| `Out of swap space?` / native allocation failure | Native allocation hoặc OS memory | NMT, OS memory maps, native profiler |

Một OOME không tự động có nghĩa memory leak. Có thể do cấu hình giới hạn quá thấp, workload tăng, thread count quá lớn hoặc native resource cạn.

### 18.1. Heap đầy và Metaspace đầy là hai vấn đề khác nhau

- Heap đầy: object sống nhiều, object allocation quá lớn hoặc heap max quá nhỏ.
- Metaspace đầy: class metadata cần nhiều hơn giới hạn/capacity hiện tại.
- Class loader leak: loader bị giữ sống, khiến class metadata không được unload.
- Native allocation failure: JNI/native library hoặc JVM subsystem không lấy được memory.

Tăng `-Xmx` không giải quyết trực tiếp `OutOfMemoryError: Metaspace`.

### 18.2. Native thread exhaustion

Một process có thể hết tài nguyên tạo OS threads trước khi heap đầy.

Điều tra:

- Số platform threads.
- Thread stack size.
- OS process/thread limits.
- Container PID limit.
- Thread pool có tăng không kiểm soát hay không.
- JNI/native code có tạo thread riêng không.

Với virtual threads, cần phân biệt số virtual threads và số carrier/platform threads. Hàng triệu virtual threads không có nghĩa process phải tạo hàng triệu OS threads.

## 19. Phân biệt heap leak, Metaspace leak và native memory leak

| Dấu hiệu | Có thể là | Kiểm tra tiếp |
|---|---|---|
| Heap used/live set tăng sau nhiều GC | Object retention | Heap dump, JFR, GC logs |
| Loaded classes tăng liên tục | Class loading không được kiểm soát | `ClassLoadingMXBean`, `VM.classes` |
| Metaspace used tăng cùng classloader count | Class loader giữ class metadata | `VM.classloader_stats`, `VM.metaspace` |
| Direct buffer capacity tăng | Direct buffer retention | BufferPoolMXBean, buffer lifecycle |
| RSS tăng nhưng heap/non-heap JMX ổn định | Native allocation, memory map, OS library | NMT, OS tools, native profiler |
| Thread count tăng | Thread leak hoặc pool không giới hạn | Thread dump, NMT Thread category |
| Code Cache tăng | JIT compilation activity | CodeHeap pools, `Compiler.codecache` |

### 19.1. Quy trình điều tra đề xuất

1. Xác định OOME message hoặc metric nào đang tăng.
2. Đo heap và từng memory pool bằng JMX.
3. Đo direct/mapped buffer bằng BufferPoolMXBean.
4. Nếu dùng HotSpot, bật NMT từ lần khởi động tiếp theo.
5. Lấy NMT baseline sau warm-up.
6. Chạy workload ổn định và thu `summary.diff`.
7. Nếu category `Class` tăng, xem `VM.classloader_stats` và `VM.metaspace show-loaders=true`.
8. Nếu heap tăng, lấy histogram/heap dump và tìm retaining paths.
9. Nếu RSS tăng nhưng NMT/JMX không giải thích được, dùng OS native tools hoặc profiler.
10. Chỉ điều chỉnh JVM flags sau khi biết đúng pool đang thiếu.

## 20. Tuning memory đúng vùng

| Mục tiêu | Flag/API liên quan | Lưu ý |
|---|---|---|
| Heap ban đầu | `-Xms` | Không phải native memory limit |
| Heap tối đa | `-Xmx` | Không phải giới hạn tổng process |
| Giới hạn Metaspace | `-XX:MaxMetaspaceSize` | Không chữa class-loader leak |
| Ngưỡng GC liên quan metadata | `-XX:MetaspaceSize` | Không phải maximum |
| Compressed class space | `-XX:CompressedClassSpaceSize` | Chỉ ảnh hưởng vùng compressed class metadata |
| Direct memory limit | `-XX:MaxDirectMemorySize` | Liên quan direct buffers |
| Theo dõi native allocations | `-XX:NativeMemoryTracking=summary/detail` | Phải bật khi startup |
| Theo dõi heap/class loading | JMX/JFR/jcmd | Chọn công cụ theo vấn đề |

### 20.1. Đừng tăng MaxMetaspaceSize trước khi kiểm tra class loading

Nếu class loader leak là nguyên nhân, tăng giới hạn chỉ giúp ứng dụng chạy lâu hơn trước khi gặp OOME.

Tìm loader nào đang giữ nhiều classes, tại sao loader còn reachable và references nào cần được giải phóng.

### 20.2. Đừng giảm heap chỉ để “nhường chỗ” cho Metaspace nếu heap đang thiếu

Heap và Metaspace cùng tiêu thụ tài nguyên process/address space, nhưng việc giảm heap chỉ hợp lý khi heap có dư thừa thực sự. Nếu live set gần `-Xmx`, giảm heap sẽ làm GC pressure nặng hơn.

### 20.3. Đừng xem RSS = Xmx

RSS/Working Set còn phụ thuộc:

- Heap pages đã commit và đang resident.
- Metaspace, Code Cache, thread stacks.
- Direct buffers và JNI allocations.
- Shared libraries, mapped files.
- GC/compiler/internal structures.
- OS bookkeeping và native allocations ngoài JVM.

Cấu hình container cần headroom cho những vùng này.

## 21. Lỗi thường gặp

1. **Nghĩ mọi thứ liên quan class đều ở Metaspace.** Class mirror và ClassLoader objects là heap objects.
2. **Nghĩ object `Class<?>` chính là metadata class.** Mirror là object đại diện; metadata nội bộ là cấu trúc khác.
3. **Nghĩ static field values đều ở Metaspace.** Trong HotSpot, static field values gắn với class mirror; object được reference vẫn là heap object.
4. **Đồng nhất Method Area và Metaspace.** Method Area là khái niệm JVMS; Metaspace là HotSpot implementation.
5. **Nghĩ Metaspace chứa toàn bộ bytecode và mọi giá trị object.** Nó chứa metadata mô tả class, không phải mọi instance data.
6. **Nghĩ Code Cache là Metaspace.** Code Cache lưu JIT-compiled native code.
7. **Nghĩ non-heap JMX là tổng native memory.** Các JNI/native allocations và direct buffers không được phản ánh đầy đủ ở đó.
8. **Nghĩ `-Xmx` giới hạn tổng process.** Nó chỉ đặt giới hạn heap.
9. **Nhìn reserved rồi kết luận RAM đã dùng.** Reserved chỉ là vùng địa chỉ ảo đã giữ chỗ.
10. **Nghĩ committed luôn bằng RSS.** OS residency và memory mapping còn ảnh hưởng.
11. **Tăng `MaxMetaspaceSize` khi chưa xem class loader.** Có thể che leak.
12. **Nghĩ class loader object nằm trong Metaspace.** Object loader là heap object; class metadata của classes do nó định nghĩa nằm trong Metaspace.
13. **Nghĩ gọi `URLClassLoader.close()` sẽ unload classes.** Close resource không đồng nghĩa class unload.
14. **Gọi `System.gc()` rồi kỳ vọng Metaspace giảm ngay.** GC request không bảo đảm class unloading tức thời.
15. **Nghĩ NMT theo dõi toàn bộ JNI memory.** NMT không theo dõi đầy đủ allocations bên ngoài JVM.
16. **Dùng heap dump để tìm mọi native leak.** Heap dump chỉ phản ánh Java heap objects và references.
17. **Nghĩ mọi native memory tăng là Metaspace leak.** Có thể là direct buffer, threads, code cache, JNI hoặc OS mappings.
18. **Không kiểm tra direct buffer pool.** Direct buffer có data ngoài heap.
19. **Nghĩ mỗi virtual thread có một native OS stack riêng.** Virtual threads được multiplex lên carrier platform threads; stack chunks được quản lý trên heap.
20. **Dùng lệnh `jcmd` không có trong JDK/runtime hiện tại.** Kiểm tra `jcmd <pid> help`.
21. **Bật NMT mà không tính overhead.** NMT có chi phí hiệu năng và memory riêng.
22. **Coi class count tăng là leak.** Framework có thể tạo proxy/classes hợp lệ; cần kiểm tra xu hướng và loader ownership.
23. **Không phân biệt heap leak và class-loader leak.** Một bên giữ object; bên kia giữ class loader và metadata.
24. **Dùng thông tin PermGen hoặc flag cũ cho JDK hiện đại.** HotSpot JDK 8+ dùng Metaspace.
25. **Tăng tất cả memory flags cùng lúc.** Làm khó xác định nguyên nhân và ảnh hưởng của từng thay đổi.

## 22. Checklist production

- [ ] Đã phân biệt object instance, class mirror và class metadata.
- [ ] Đã hiểu Method Area là khái niệm JVMS và Metaspace là HotSpot implementation.
- [ ] Đã xác định JVM vendor/version và GC đang dùng.
- [ ] Theo dõi heap used/committed/max.
- [ ] Theo dõi non-heap memory pools.
- [ ] Theo dõi Metaspace và Compressed Class Space riêng.
- [ ] Theo dõi Code Cache khi cần.
- [ ] Theo dõi direct/mapped buffer pools.
- [ ] Theo dõi số platform threads và virtual threads phù hợp.
- [ ] Có class-loading metrics và classloader statistics.
- [ ] Đã bật NMT từ startup khi cần điều tra native memory.
- [ ] Có baseline và so sánh NMT qua workload ổn định.
- [ ] Biết giới hạn NMT đối với JNI/native code và CDS.
- [ ] Có cách lấy heap histogram/heap dump khi heap tăng.
- [ ] Có cách lấy native/process memory map khi RSS tăng mà JMX không giải thích.
- [ ] Đã xác định thread context class loader, ThreadLocal và static cache có giữ plugin loader không.
- [ ] Đã đóng resource/plugin loader và giải phóng references đúng lifecycle.
- [ ] Không xem `-Xmx` là tổng memory limit.
- [ ] Đã dành headroom native memory trong container.
- [ ] Không tăng MaxMetaspaceSize trước khi xác định nguyên nhân class metadata tăng.
- [ ] Không dựa vào `System.gc()` để bảo đảm unload hoặc trả memory ngay.

## 23. Bài tập thực hành

### Bài 1 — Class mirror

Tạo một class `Order`, lấy `Order.class`, tạo hai object `new Order()`. Giải thích object nào là class mirror, object nào là instance, và metadata nằm ở đâu trong HotSpot.

### Bài 2 — Static và instance field

Tạo class có static `byte[] CACHE` và instance `byte[] payload`. Phân biệt metadata mô tả hai field, giá trị static reference, hai array và class mirror.

### Bài 3 — Heap và non-heap

Chạy `MemoryAreaProbe.java`. Xác định pool nào có tên Metaspace, Compressed Class Space, CodeHeap và phân biệt pool type Heap/Non-heap.

### Bài 4 — Direct memory

Tạo `ByteBuffer.allocate(1_000_000)` rồi `ByteBuffer.allocateDirect(1_000_000)`. Quan sát BufferPoolMXBean và giải thích khác nhau.

### Bài 5 — Class loading

In `ClassLoadingMXBean` trước và sau khi dùng reflection/proxy/framework tạo class. Vì sao `totalLoaded` có thể tăng trong khi `loaded` không tăng mãi?

### Bài 6 — Metaspace OOM

Giả sử ứng dụng ném `OutOfMemoryError: Metaspace`. Viết quy trình dùng `jcmd VM.metaspace`, `VM.classloader_stats` và NMT để tìm loader tăng metadata.

### Bài 7 — Class-loader leak

Thiết kế plugin loader. Sau khi stop plugin, kiểm tra static registry, thread context class loader, ThreadLocal, executor, MBean và callback nào có thể giữ loader sống.

### Bài 8 — Reserved và committed

Một vùng heap reserve 4 GB nhưng committed 512 MB. Vì sao không thể kết luận process đang dùng 4 GB RAM?

### Bài 9 — NMT baseline

Chạy JVM với `-XX:NativeMemoryTracking=summary`. Tạo baseline sau warm-up, chạy workload, lấy `summary.diff`. Category nào tăng khi tải nhiều class?

### Bài 10 — Heap leak hay native leak?

Process RSS tăng 500 MB nhưng heap used ổn định. Hãy liệt kê các vùng cần kiểm tra: Metaspace, direct buffers, thread, Code Cache, JNI, mapped files và OS native allocations.

### Bài 11 — Virtual threads

Tạo nhiều virtual threads chờ I/O. So sánh số virtual threads với số carrier platform threads và giải thích vì sao không tính native stack theo số virtual threads.

### Bài 12 — Tuning

Một service có `-Xmx2g`, Metaspace tăng đều và class loader count tăng sau mỗi lần redeploy. Đề xuất cách tìm leak trước khi đổi `MaxMetaspaceSize`.

## 24. Câu hỏi ôn tập và đáp án

**1. Heap chứa gì?** — Class instances và arrays.

**2. Heap được quản lý chủ yếu bởi gì?** — Garbage collector/automatic storage management.

**3. `String.class` là gì?** — Reference tới class mirror, một object `java.lang.Class`.

**4. Class metadata là gì?** — Cấu trúc nội bộ mô tả class, field, method, constant pool và dữ liệu runtime liên quan.

**5. Trong HotSpot hiện đại, class metadata nằm ở đâu?** — Metaspace trong native memory.

**6. Method Area và Metaspace có đồng nghĩa ở cấp JVM Specification không?** — Không. Method Area là runtime area trừu tượng; Metaspace là HotSpot implementation.

**7. Static field values có phải metadata không?** — Không. Metadata mô tả field; giá trị field là dữ liệu runtime. Trong HotSpot, static field storage gắn với class mirror trên heap.

**8. ClassLoader object nằm ở đâu?** — Heap.

**9. Metadata của class do ClassLoader định nghĩa nằm ở đâu trong HotSpot?** — Metaspace/Compressed Class Space theo loại metadata.

**10. Compressed Class Space lưu gì?** — Một loại `Klass` metadata khi compressed class pointers được sử dụng.

**11. Code Cache lưu gì?** — Native machine code do JIT compiler tạo.

**12. DirectByteBuffer data nằm ở đâu?** — Ngoài heap; wrapper Java vẫn là heap object.

**13. Non-heap JMX có phải tổng native memory không?** — Không.

**14. `-Xmx` giới hạn gì?** — Heap tối đa.

**15. `-XX:MaxMetaspaceSize` giới hạn gì?** — Native memory dành cho class metadata theo HotSpot configuration.

**16. `-XX:MetaspaceSize` có phải maximum không?** — Không, nó liên quan ngưỡng/high-water mark cho GC metadata.

**17. `reserved` nghĩa là gì?** — Địa chỉ ảo đã reserve.

**18. `committed` nghĩa là gì?** — Vùng JVM đã commit để sử dụng.

**19. NMT có bật mặc định không?** — Không, cần bật khi startup.

**20. NMT có theo dõi mọi JNI allocation không?** — Không.

**21. Lệnh xem Metaspace theo class loader?** — `jcmd <pid> VM.metaspace show-loaders=true`.

**22. Lệnh xem thống kê class loaders?** — `jcmd <pid> VM.classloader_stats`.

**23. Lệnh lấy NMT baseline?** — `jcmd <pid> VM.native_memory baseline`.

**24. Lệnh lấy native memory summary?** — `jcmd <pid> VM.native_memory summary`.

**25. Lệnh so sánh NMT sau baseline?** — `jcmd <pid> VM.native_memory summary.diff`.

**26. Class có unload ngay khi không còn object instance không?** — Không. Cần defining class loader có thể được thu hồi; thời điểm unload phụ thuộc JVM/GC.

**27. `URLClassLoader.close()` có unload class không?** — Không, nó đóng resource; class unloading là lifecycle khác.

**28. Vì sao static cache có thể gây Metaspace leak?** — Cache có thể giữ Class/instance/ClassLoader, làm defining loader còn reachable.

**29. Vì sao RSS tăng nhưng heap ổn định?** — Native memory, direct buffers, stacks, code cache, JNI hoặc mapped files có thể tăng.

**30. Virtual thread có một OS thread/native stack riêng cho toàn bộ lifetime không?** — Không; nó được runtime multiplex lên carrier platform threads, stack chunks được quản lý trên heap.

## 25. Tổng kết

**Java heap và Metaspace quản lý hai nhóm dữ liệu khác nhau.** Heap chứa object/array; Metaspace trong HotSpot chứa class metadata ở native memory. Class mirror (`java.lang.Class`) và ClassLoader object vẫn là object trên heap, nên không thể nói “mọi thứ của class đều nằm trong Metaspace”.

Các nguyên tắc cần nhớ:

1. JVM Specification định nghĩa Method Area trừu tượng; không bắt buộc một vị trí vật lý cụ thể.
2. HotSpot hiện đại quản lý class metadata trong native Metaspace.
3. Class mirror là object `java.lang.Class` trên heap.
4. Trong HotSpot, static field storage gắn với class mirror; object mà static reference trỏ tới vẫn ở heap.
5. Compressed Class Space chỉ chứa một loại `Klass` metadata.
6. Code Cache, thread stacks, GC structures và direct buffers là các vùng khác; không đồng nhất chúng với Metaspace.
7. Non-heap JMX không phải toàn bộ native memory của process.
8. NMT cần bật khi startup và không theo dõi đầy đủ allocations ngoài JVM.
9. Class unloading phụ thuộc defining class loader có thể được thu hồi; `close()` không tự unload class.
10. Dùng heap dump cho heap, NMT/`jcmd` cho HotSpot native memory và OS tools cho native allocations bên ngoài JVM.
11. `-Xmx` chỉ giới hạn heap; process cần headroom cho native memory.
12. Tìm đúng pool và đúng owner trước khi thay đổi các memory flags.

### Tài liệu chính thức hiện hành

- [Java Virtual Machine Specification SE 26 — Runtime Data Areas, Heap, Method Area, Runtime Constant Pool](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html)
- [Java Language Specification SE 26 — Class Loading, Initialization và Class Unloading (§12.7)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html)
- [Oracle Java SE 26 GC Tuning Guide — Class Metadata, Metaspace và Compressed Class Space](https://docs.oracle.com/en/java/javase/26/gctuning/other-considerations.html)
- [Oracle Java SE 26 Troubleshooting Guide — Heap, Metaspace, Compressed Class Space và memory leaks](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle Java SE 26 Diagnostic Tools — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 26 `jcmd` Command Reference — VM.metaspace, VM.classloader_stats, VM.native_memory](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle Java SE 26 `MemoryMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 26 `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Oracle Java SE 26 `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Oracle Java SE 26 Virtual Threads — Platform Threads và Carrier Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html)
