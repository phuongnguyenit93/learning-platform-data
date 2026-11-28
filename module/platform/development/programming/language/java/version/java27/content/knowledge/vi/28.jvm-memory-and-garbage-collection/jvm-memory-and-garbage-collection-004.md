# Heap, stack, metaspace và bộ nhớ native trong JVM của Java 27

Một ứng dụng có thể báo `OutOfMemoryError: Java heap space` dù máy vẫn còn RAM. Một tiến trình Java có thể bị hệ điều hành kết thúc vì vượt giới hạn bộ nhớ container trong khi heap chưa chạm `-Xmx`. Một hệ thống tạo nhiều class động có thể hết **metaspace**, còn một ứng dụng mở quá nhiều luồng platform hoặc cấp phát nhiều direct buffer có thể thiếu **native memory** dù đồ thị heap trông bình thường.

Những hiện tượng này không mâu thuẫn: **bộ nhớ của tiến trình JVM không chỉ có Java heap**. Để thiết kế và vận hành Java 27 đúng, phải biết dữ liệu và trạng thái thực thi nằm ở đâu, phần nào được GC quản lý, phần nào phụ thuộc hệ điều hành, và mỗi công cụ quan sát thực sự đo điều gì.

Bài học thuộc chương **JVM, bộ nhớ và thu gom rác**, trong phạm vi **Java 27 và kiến thức vẫn áp dụng hiện nay**. Các ví dụ và công cụ dựa trên Java SE 27 và HotSpot JVM; khi mô tả chi tiết HotSpot cụ thể, bài sẽ phân biệt với hợp đồng chung của ngôn ngữ Java hoặc đặc tả JVM. Không dùng những mô hình bộ nhớ đã lỗi thời như coi **PermGen** vẫn là nơi chứa metadata class trong HotSpot hiện đại.

## 1. Bức tranh tổng thể: Java heap không phải toàn bộ RAM của JVM

Một tiến trình Java tiêu thụ nhiều loại bộ nhớ. Sơ đồ bên dưới thể hiện **các nhóm khái niệm**, không phải sơ đồ địa chỉ vật lý cố định:

~~~~text
Hệ điều hành / container
┌───────────────────────────────────────────────────────────────────┐
│ Tiến trình JVM (RAM và virtual address space)                     │
│                                                                   │
│  ┌───────────────────────────┐    ┌───────────────────────────┐   │
│  │ Java heap                 │    │ Native / non-heap          │   │
│  │                           │    │                           │   │
│  │ Object instances, arrays │    │ Metaspace: class metadata │   │
│  │ Strings, collections     │    │ Code cache: JIT code      │   │
│  │ Objects mà app còn giữ   │    │ GC/runtime internal data  │   │
│  │ Stack chunks của một số  │    │ Direct/mapped buffers     │   │
│  │ virtual threads          │    │ JNI/foreign/native malloc │   │
│  └───────────────────────────┘    └───────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────┐    ┌───────────────────────────┐   │
│  │ Platform thread stacks    │    │ Thành phần khác           │   │
│  │ Java call frames và dữ   │    │ JVM structures, shared    │   │
│  │ liệu frame đang chạy     │    │ libraries, page mappings  │   │
│  └───────────────────────────┘    └───────────────────────────┘   │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
~~~~

**Không cộng máy móc tất cả hình chữ nhật thành một con số RAM chính xác.** Một số vùng có thể được *reserve* trong không gian địa chỉ ảo nhưng chưa *commit*; một số có thể là trang ánh xạ tệp, trang dùng chung hoặc do hệ điều hành quản lý. Công cụ đo trên Java, HotSpot NMT và hệ điều hành có **phạm vi khác nhau**.

### 1.1. Bảng phân loại nhanh

| Vùng/nhóm | Thường chứa gì? | Quản lý vòng đời chủ yếu | Quan sát/điều chỉnh |
| --- | --- | --- | --- |
| **Java heap** | Đối tượng, mảng Java, một số cấu trúc stack chunk của virtual thread | Garbage collector dựa trên reachability | `-Xms`, `-Xmx`, `MemoryMXBean`, GC logs/heap dump |
| **Stack của platform thread** | Các frame lời gọi, trạng thái thực thi, biến local theo frame | Runtime và OS thread; thu hồi khi thread kết thúc | `-Xss`, thread dump, NMT nhóm Thread |
| **Metaspace** | Metadata của class/interface và cấu trúc class loader ở HotSpot | JVM class loading/unloading, native allocation | `-XX:MaxMetaspaceSize`, `jcmd VM.metaspace`, NMT |
| **Code cache** | Machine code được JIT biên dịch và một số stub của JVM | JVM/JIT | JFR, MemoryPoolMXBean, VM code commands |
| **Direct buffer** | Dữ liệu I/O phía ngoài Java heap, có object wrapper trên heap | JVM/JDK quản lý buffer và bộ nhớ native; thời điểm thu hồi phụ thuộc cơ chế | `BufferPoolMXBean`, `-XX:MaxDirectMemorySize` (HotSpot) |
| **Foreign memory** | Native `MemorySegment` và vùng cấp phát qua `Arena` | Scope/arena đã lựa chọn; có thể đóng tường minh | API `java.lang.foreign`, native tools |
| **JNI/native libraries** | malloc/mmap riêng của mã native, thư viện hệ thống | Chính thư viện và OS | Native profiler, OS metrics, không mặc định thấy đủ ở NMT |
| **GC/runtime internals** | Metadata GC, remembered sets, compiler, runtime bookkeeping | HotSpot | NMT, GC/JFR diagnostics |

**Cần phân biệt:** “non-heap” trong `MemoryMXBean.getNonHeapMemoryUsage()` là khái niệm theo các **memory pool được JVM công bố**, **không có nghĩa mọi bộ nhớ ngoài heap hoặc toàn bộ RSS**. Direct buffer, thread stack, native library và memory-mapped pages không mặc nhiên nằm trong con số non-heap MXBean ấy.

## 2. Java heap: nơi dữ liệu đối tượng tồn tại

### 2.1. Đối tượng và mảng Java

Với chương trình:

~~~~java
import java.util.ArrayList;
import java.util.List;

record Customer(long id, String name) {
}

Customer customer = new Customer(101L, "Lan");
List<Customer> customers = new ArrayList<>();
customers.add(customer);
~~~~

Mô hình tư duy thông thường:

- Instance `Customer`, `ArrayList`, cấu trúc mảng backing của list và `String` là **đối tượng Java**, thường được cấp phát trên heap.
- Biến `customer` và `customers` là **các tham chiếu** đến object; bản thân biến nằm ở đâu tùy bối cảnh (local frame, field hoặc một cấu trúc khác).
- Một biến local mang tham chiếu không có nghĩa **toàn bộ object** được chứa trong call stack.
- Hai biến có thể cùng tham chiếu một object; đặt một biến bằng `null` không nhất thiết làm object không còn reachable nếu còn tham chiếu khác.

Trong tối ưu hóa của HotSpot, compiler có thể **loại bỏ cấp phát (scalar replacement), inline hoặc tối ưu vòng đời object** khi chứng minh được điều đó không thay đổi hành vi quan sát được. Vì vậy, “mỗi câu `new` chắc chắn tạo một khối vật lý trên heap” chỉ là **mô hình sư phạm đơn giản**, không phải cam kết tối ưu hóa ở runtime.

### 2.2. Mảng lớn và mảng đối tượng khác nhau

~~~~java
int[] numbers = new int[1_000_000];
String[] names = new String[1_000_000];
~~~~

`numbers` biểu diễn một mảng các giá trị `int`, còn `names` biểu diễn một mảng **tham chiếu đến String**. Việc tạo mảng `names` chỉ tạo cấu trúc mảng, không tự tạo một triệu đối tượng String mới.

Object có thêm overhead như header, alignment và padding, thay đổi theo JVM, kiến trúc, cấu hình và các tối ưu hóa hiện hành. Không tính cứng “mỗi object luôn có 12 byte header” hoặc “mọi reference luôn 8 byte”. Java 27 có các tối ưu và tùy chọn HotSpot làm các giá trị này **không cố định cho mọi process**.

### 2.3. GC quan tâm đến khả năng tới được đối tượng (*reachability*)

Ví dụ:

~~~~java
import java.util.ArrayList;
import java.util.List;

List<byte[]> retained = new ArrayList<>();
retained.add(new byte[1024 * 1024]);

// Mảng còn reachable thông qua retained.
retained.clear();

// Nếu không còn tham chiếu khác, mảng có thể trở thành
// đối tượng đủ điều kiện được GC thu hồi.
~~~~

**GC không bắt buộc thu hồi ngay** sau `clear()`, sau khi method return hay sau khi một biến được gán null. “Đủ điều kiện thu hồi” khác với “bộ nhớ đã giảm trên biểu đồ tại giây tiếp theo”. Ngoài ra, JVM có thể giữ các vùng heap đã commit để **tái sử dụng** thay vì trả ngay cho OS.

Vì vậy:

- **Heap used** có thể giảm sau GC.
- **Heap committed** có thể không giảm ngay.
- **RSS của tiến trình** có thể duy trì cao dù nhiều object đã được thu hồi.

Không kết luận “memory leak” chỉ vì RSS không giảm sau một lần `System.gc()`.

### 2.4. Những gì giữ object sống lâu bất ngờ?

| Nguồn giữ reference | Ví dụ | Rủi ro |
| --- | --- | --- |
| Collection sống lâu | `static Map`, cache không giới hạn | Object tiếp tục reachable |
| `ThreadLocal` | Cache lớn gắn với thread sống lâu | Dữ liệu không được giải phóng theo vòng đời request |
| Listener/callback | Đã đăng ký nhưng không unregister | Đối tượng được giữ bởi publisher |
| Queue | Message đến nhanh hơn tốc độ tiêu thụ | Payload tích lũy |
| Future/task | Callback hoặc lambda capture dữ liệu lớn | Dữ liệu sống đến khi task/continuation không còn reachable |
| Class loader | Class loader giữ class, resource hoặc object graph | Class metadata và object liên quan có thể tồn tại lâu |
| Reference chain | Một object nhỏ tham chiếu object graph rất lớn | Retained size lớn hơn shallow size |

Một **memory leak trong Java** thường không phải “địa chỉ bị mất và không giải phóng được” theo cách native, mà là **những object vẫn reachable dù không còn cần cho nghiệp vụ**.

## 3. Cách tổ chức heap và ranh giới của garbage collector

Heap là không gian object do JVM quản lý; chi tiết chia vùng phụ thuộc **garbage collector** và cấu hình. Không nên áp đặt sơ đồ **Young/Eden/Survivor/Old** cho mọi collector trong Java 27:

- Một số collector có thiết kế **generational**, phân biệt object mới và object sống lâu, với các chính sách thu gom tương ứng.
- Một số collector tổ chức heap theo **regions** hoặc những cấu trúc nội bộ khác; tên pool được JMX công bố có thể khác.
- Một số collector tối ưu **độ trễ pause**, số khác ưu tiên **throughput**, footprint hoặc chi phí CPU.

Các loại GC như G1, ZGC, Parallel GC hoặc Shenandoah có chi tiết hoạt động và tùy chọn khác nhau. Bài học này tập trung **mô hình bộ nhớ**; việc chọn collector cần dựa trên bản JDK/HotSpot cụ thể, workload, pause SLO và đo đạc thực tế, không dựa vào một sơ đồ heap cố định.

### 3.1. `-Xms` và `-Xmx`

~~~~text
java -Xms256m -Xmx1g -jar app.jar
~~~~

- `-Xms` xác định **kích thước heap ban đầu** theo cấu hình HotSpot.
- `-Xmx` đặt **giới hạn tối đa của Java heap**.
- `-Xmx1g` **không** đặt giới hạn cho toàn bộ RAM tiến trình JVM.
- Kích thước tối đa heap có thể còn bị ảnh hưởng bởi khả năng cấp phát thực tế của OS/container, kiến trúc và cấu hình khác.

Ví dụ `-Xmx1g` không có nghĩa tiến trình chỉ chiếm 1 GiB RAM. Ngoài heap còn stack, metaspace, code cache, buffer, native library, GC internals và những thành phần khác.

### 3.2. Dòng đời object và tần suất GC

Một ứng dụng tạo nhiều object ngắn hạn có thể chạy tốt nếu GC thu hồi chúng hiệu quả. Ngược lại, một ứng dụng tạo ít object nhưng giữ lại một graph lớn trong cache có thể làm **live set** cao và khó thu hồi.

Khi phân tích:

1. Kiểm tra **live data sau GC** chứ không chỉ đỉnh heap used trước GC.
2. Xem tốc độ cấp phát (**allocation rate**) và đối tượng nào tạo nhiều rác.
3. Xem tập object sống lâu và **retained references**.
4. Đối chiếu tần suất/pause GC với thời gian phản hồi và CPU của ứng dụng.

Tăng `-Xmx` có thể giúp tạm thời nếu workload thật cần nhiều live data, nhưng **không sửa được một collection tăng không giới hạn**. Cũng không giải quyết một rò rỉ ở native memory.

## 4. Stack và call frames: bộ nhớ cho lời gọi phương thức

### 4.1. Mỗi thread có ngữ cảnh thực thi riêng

Một **stack frame** đại diện cho việc thực thi một lần gọi method; nó chứa các cấu trúc như local variables, operand stack và thông tin cần thiết để method thực thi theo mô hình JVM.

~~~~java
static int doubleValue(int value) {
    int doubled = Math.multiplyExact(value, 2);
    return doubled;
}

static int calculate() {
    int input = 21;
    return doubleValue(input);
}
~~~~

Khi `calculate()` gọi `doubleValue()`, có một chuỗi frame cho lời gọi. Khi method return, frame của nó kết thúc. **Bộ nhớ chứa frame** và cách tối ưu hóa frame thuộc implementation; JVM không bắt buộc mọi local variable phải được đặt vật lý vào một khối native stack theo đúng sơ đồ.

Một local variable kiểu tham chiếu có thể giữ địa chỉ logic của object trên heap; nó **không chứa nguyên object** chỉ vì nằm trong frame.

### 4.2. Stack overflow

Đệ quy không có điều kiện dừng có thể khiến stack không còn chỗ cho frame mới:

~~~~java
public class RecursionDemo {
    static void recurse() {
        recurse();
    }

    public static void main(String[] args) {
        // Chỉ minh họa; không gọi trong ứng dụng thật.
        // recurse(); // Có thể ném StackOverflowError.
    }
}
~~~~

`StackOverflowError` thường gắn với độ sâu stack vượt khả năng dành cho thread. Không nhất thiết là Java heap đã hết. Nguyên nhân thường là đệ quy vô hạn, đệ quy quá sâu hoặc call chain bất thường.

Phương án xử lý ưu tiên **sửa thuật toán**, đặt điều kiện dừng hoặc chuyển sang duyệt bằng cấu trúc lặp thích hợp. Tăng stack size có thể thay đổi ngưỡng thất bại nhưng không chữa một vòng đệ quy vô hạn.

### 4.3. `-Xss` và giới hạn platform thread

~~~~text
java -Xss1m -jar app.jar
~~~~

Trên HotSpot, `-Xss` đặt **kích thước stack của thread Java theo cấu hình**; tác động cụ thể phụ thuộc OS/kiến trúc và cách JVM triển khai thread. Không hiểu nó là tổng bộ nhớ cấp cho một thread. Thread còn có cấu trúc JVM/OS, TLS, native library state và tài nguyên khác.

Với nhiều **platform threads**, chi phí stack và tài nguyên OS có thể trở thành đáng kể. Nếu quá nhiều thread được tạo hoặc OS từ chối cấp phát stack/thread, JVM có thể gặp `OutOfMemoryError: unable to create native thread` (thông điệp cụ thể có thể khác).

**Đừng nhân máy móc** số thread với `-Xss` rồi coi là RSS chính xác. Một thread stack có thể reserve không gian địa chỉ lớn nhưng chỉ commit một phần; OS có guard pages, chính sách overcommit và những phần memory khác.

### 4.4. Virtual threads trong Java 27

Virtual threads là tính năng **ổn định từ Java 21**, có trong Java 27. Chúng không có một **OS thread native riêng được giữ suốt vòng đời** như platform threads. Stack của virtual thread có thể được JVM biểu diễn bằng **stack chunks được quản lý trong Java heap**, đặc biệt khi virtual thread bị tạm dừng; khi chạy, nó được gắn với carrier platform thread.

~~~~java
public class VirtualThreadExample {
    public static void main(String[] args) throws InterruptedException {
        Thread task = Thread.ofVirtual().start(() ->
                System.out.println(Thread.currentThread().isVirtual()));

        task.join(); // true đã được in trước khi main kết thúc.
    }
}
~~~~

Điểm quan trọng:

- Không dành một **native OS stack độc lập cố định** cho mỗi virtual thread như một platform thread.
- Stack chunks của virtual thread vẫn **tiêu thụ bộ nhớ**, thường trên heap, và vẫn có giới hạn.
- Tạo hàng triệu virtual threads cùng giữ object graph lớn hoặc `ThreadLocal` lớn vẫn có thể cạn tài nguyên.
- Virtual threads giúp tăng khả năng xử lý nhiều tác vụ **chờ I/O**, không làm phép tính CPU nặng chạy nhanh hơn.

Đừng dùng `-Xss` như công cụ trực tiếp để ước lượng “mỗi virtual thread mất 1 MiB native stack”; mô hình stack của virtual threads khác platform threads. Cần quan sát workload và JVM thực tế.

## 5. Metaspace: metadata của class trong HotSpot

Khi JVM nạp và liên kết class, nó cần lưu những cấu trúc để biểu diễn **kiểu dữ liệu và thông tin runtime của class**: mô tả method, field, constant pool đã được xử lý và những metadata VM liên quan. Trong HotSpot hiện đại, phần lớn metadata class này được quản lý trong **metaspace**, dùng bộ nhớ native, **không phải Java heap**.

### 5.1. Metaspace khác với object `Class<?>`

~~~~java
Class<?> type = String.class;
System.out.println(type.getName()); // java.lang.String
~~~~

`String.class` là một đối tượng `java.lang.Class` nhìn thấy được từ Java, và **đối tượng Java** này có mô hình quản lý object tương ứng. Nhưng **metadata nội bộ của class** mà HotSpot cần để thực thi lại là chuyện khác, được lưu trong những vùng bộ nhớ VM như metaspace.

Không đồng nhất:

- “Mỗi `Class<?>` object trên heap chính là toàn bộ class metadata.”
- “Tất cả thông tin liên quan class đều nằm ngoài heap.”
- “Metaspace là nơi mọi object của một class được tạo ra.”

Những câu này đều sai hoặc gây hiểu nhầm. **Object instance** thông thường thuộc heap; **class metadata HotSpot** thuộc metaspace; nhiều cấu trúc khác của JVM có vị trí và vòng đời riêng.

### 5.2. Metaspace có giới hạn không?

HotSpot sử dụng native memory để quản lý metaspace. Không có nghĩa “metaspace lớn vô hạn”: nó vẫn chịu giới hạn địa chỉ ảo, RAM, container, OS và có thể đặt trần rõ ràng:

~~~~text
java -XX:MaxMetaspaceSize=256m -jar app.jar
~~~~

`-XX:MaxMetaspaceSize` đặt mức tối đa metaspace theo HotSpot. Giá trị **256 MiB chỉ là ví dụ**, không phải khuyến nghị mặc định cho mọi ứng dụng. Nếu trần quá nhỏ cho framework có nhiều class, ứng dụng có thể gặp `OutOfMemoryError: Metaspace`.

Một số cấu hình HotSpot còn có vùng **Compressed Class Space** dùng cho metadata liên quan compressed class pointers khi chế độ đó được bật. Vùng này có flag tương ứng như `-XX:CompressedClassSpaceSize`. **Không cộng nhầm không gian địa chỉ đã reserve của Compressed Class Space thành lượng RAM đã dùng thực tế.**

### 5.3. Class loading và unloading

Một class có thể được nạp qua một `ClassLoader` và các class loader khác nhau có thể tạo ra những lớp phân biệt dù cùng tên nhị phân. JVM có thể **unload class** khi các điều kiện về reachability và hành vi runtime được thỏa mãn; trong nhiều trường hợp cần class loader và class graph tương ứng không còn được giữ sống.

Điều này không diễn ra ngay khi một object instance cuối cùng của class biến mất. Nếu application còn giữ tham chiếu đến `ClassLoader`, `Class<?>`, các instance, thread/callback hoặc những cấu trúc khác, class metadata có thể vẫn phải được giữ.

**Các nguồn tăng metaspace thường gặp:**

- Framework sinh class động, bytecode instrumentation hoặc proxy generation.
- Tạo **ClassLoader mới** liên tục theo request/tenant/task và không giải phóng.
- Redeploy plugin/module nhưng class loader cũ bị giữ bởi cache, thread, listener hoặc tài nguyên native.
- Classpath/module lớn và số lượng class thực sự tăng theo chức năng.

### 5.4. Ví dụ class loader được giữ ngoài ý muốn

~~~~java
import java.util.ArrayList;
import java.util.List;

final class LoaderRegistry {
    // Nếu không có chính sách loại bỏ, mọi loader được thêm
    // sẽ tiếp tục reachable qua collection tĩnh này.
    private static final List<ClassLoader> LOADERS = new ArrayList<>();

    static void register(ClassLoader loader) {
        LOADERS.add(loader);
    }
}
~~~~

Đây chỉ là ví dụ **mô hình giữ tham chiếu**; không tạo class loader thực hay tải class trong bài học. Nếu registry không xóa loader cũ, JVM không thể coi class loader ấy là unreachable. Nhưng một loader còn sống **chưa chắc đã chứng minh metaspace đang leak**: cần kiểm tra số class được nạp, class loader, footprint và trạng thái sử dụng qua thời gian.

### 5.5. `PermGen` là kiến thức lịch sử, không phải cấu hình hiện hành

Các tài liệu Java rất cũ có thể nói về `PermGen` hoặc `-XX:MaxPermSize`. Trong **HotSpot Java 27**, những hướng dẫn đó **không phải cách quản lý class metadata hiện đại**. Dùng metaspace, các công cụ chẩn đoán class loading và flag phù hợp thay vì cố “tăng PermGen”.

## 6. Native memory: phần ngoài Java heap

**Native memory** là một tên gọi rộng. Nó gồm nhiều vùng bộ nhớ được OS/HotSpot/thư viện cấp phát ở ngoài Java heap, nhưng **không phải mọi vùng đều có cùng API quản lý hoặc cùng thời điểm giải phóng**.

### 6.1. Các nhóm native thường gặp

| Nhóm | Ví dụ | Điều cần quan sát |
| --- | --- | --- |
| JVM runtime | GC bookkeeping, compiler data, symbols, module structures | NMT / JFR / công cụ JVM |
| Class metadata | Metaspace và phần class space | Class loaders, VM.metaspace, NMT |
| Thread-related | Native stacks và cấu trúc OS threads | Số platform threads, NMT Thread, OS |
| Code cache | Machine code do JIT tạo | Code cache pools, JIT diagnostics |
| NIO buffers | `ByteBuffer.allocateDirect` | `BufferPoolMXBean`, giới hạn direct memory |
| Memory mapped files | `FileChannel.map` / file mapping | OS mappings, BufferPoolMXBean nếu phù hợp |
| Foreign memory | `Arena.allocate` | Scope/arena lifecycle và kích thước |
| JNI/thư viện native | `malloc`, cấu trúc của C/C++ library | Native allocation profiler / OS |
| Shared libraries/mappings | Loaded library code và mapped pages | OS memory maps / RSS/PSS |

Không có một metric JDK duy nhất luôn cộng **đúng tất cả** những nhóm này. Một vùng có thể được tính trong nhiều cách báo cáo, hoặc không được NMT theo dõi nếu nó nằm ngoài cấp phát nội bộ HotSpot.

### 6.2. On-heap `ByteBuffer` và direct `ByteBuffer`

~~~~java
import java.nio.ByteBuffer;

ByteBuffer onHeap = ByteBuffer.allocate(1024);
ByteBuffer direct = ByteBuffer.allocateDirect(1024);

System.out.println(onHeap.isDirect()); // false
System.out.println(direct.isDirect()); // true

direct.putInt(0, 2026);
System.out.println(direct.getInt(0));  // 2026
~~~~

`ByteBuffer.allocate` dùng một vùng dữ liệu **trên Java heap**, còn `allocateDirect` tạo một direct buffer mà backing storage thường nằm trong **native memory** ngoài heap. Object wrapper `ByteBuffer` vẫn là object Java, được GC quản lý về reachability.

Một direct buffer có thể thuận lợi cho I/O native hoặc giảm một số thao tác copy tùy driver, channel và workload, nhưng **không mặc định nhanh hơn** trong mọi phép xử lý. Cấp phát direct buffer có thể tốn chi phí hơn, và việc thu hồi vùng backing memory có cơ chế/vòng đời riêng.

### 6.3. `-XX:MaxDirectMemorySize` không phải trần mọi native allocation

~~~~text
java -XX:MaxDirectMemorySize=256m -jar app.jar
~~~~

Đây là flag HotSpot dùng để **giới hạn trực tiếp một nhóm cấp phát direct buffer memory** của JDK. Không dùng nó như cơ chế giới hạn tổng bộ nhớ native của:

- Metaspace.
- Native thread stacks.
- Code cache hoặc bộ nhớ nội bộ GC.
- Mọi thư viện JNI/C/C++.
- Mọi vùng Foreign Memory API hoặc mapped memory theo mọi đường cấp phát.

Khi một ứng dụng báo lỗi về direct buffer memory, hãy kiểm tra **vòng đời buffer, số lượng buffer sống đồng thời, kích thước buffer, cache hoặc pooling**. Tăng trần mà không hiểu pattern giữ reference có thể chỉ trì hoãn sự cố.

### 6.4. Memory-mapped file

Các API mapping tệp đưa một vùng nội dung file vào **không gian địa chỉ của tiến trình**. Điều này không có nghĩa toàn bộ file đã được nạp thường trú trong RAM ngay lập tức; OS có thể xử lý trang theo nhu cầu.

`FileChannel.map` và các API mapping hiện hành có ngữ nghĩa riêng về lifecycle, thay đổi file, quyền truy cập, sync/flush và giới hạn OS. Không cộng toàn bộ kích thước file mapped vào “heap used”, cũng không giả định nó bằng RSS tại mọi thời điểm.

Khi chẩn đoán một process có **nhiều mappings**, cần kết hợp metric Java với sơ đồ vùng nhớ của OS.

## 7. Foreign Function & Memory API: cấp phát native có vòng đời rõ ràng

Java 27 có **Foreign Function & Memory API (FFM)** chính thức trong package `java.lang.foreign`. API này được hoàn thiện từ JDK 22 và cho phép biểu diễn vùng nhớ bằng `MemorySegment`, cấp phát/quản lý vòng đời bằng `Arena`. Ví dụ dưới đây chỉ dùng **memory access**, không gọi hàm native từ thư viện bên ngoài.

### 7.1. Một `Arena` có thể đóng

Chương trình tự chứa, lưu dưới tên `ForeignMemoryDemo.java`:

~~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(ValueLayout.JAVA_LONG);

            data.set(ValueLayout.JAVA_LONG, 0, 2026L);
            long value = data.get(ValueLayout.JAVA_LONG, 0);

            System.out.println(value); // 2026
            System.out.println(data.byteSize()); // 8
        }
        // Các vùng native được arena quản lý được giải phóng khi
        // arena.ofConfined đóng thành công.
    }
}
~~~~

**Lợi ích:** vùng native có vòng đời **gắn với scope/arena**, không chỉ phụ thuộc việc một object wrapper nào đó được GC thu hồi vào thời điểm không xác định. Trong `try-with-resources`, `Arena.close()` được gọi khi ra khỏi khối.

Các truy cập sau khi scope của segment bị đóng sẽ không hợp lệ (thường nhận `IllegalStateException` theo hợp đồng API). `MemorySegment` còn có kiểm tra giới hạn vùng nhớ và điều kiện truy cập giúp giảm nhiều lỗi native memory thường gặp.

### 7.2. Bốn kiểu arena thường dùng

| Arena | Vòng đời | Đóng thủ công? | Truy cập qua nhiều thread? |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Đến khi đóng; gắn với thread sở hữu | Có | Không, chỉ thread sở hữu được truy cập |
| `Arena.ofShared()` | Đến khi đóng | Có | Có, theo hợp đồng shared scope |
| `Arena.ofAuto()` | Thu hồi tự động sau khi unreachable, thời điểm không cố định | Không | Có |
| `Arena.global()` | Không giới hạn; không được đóng thủ công | Không | Có |

Không dùng `Arena.global()` cho mỗi request lớn rồi kỳ vọng native region được thu hồi khi request kết thúc: theo tài liệu API, vùng cấp phát bằng global arena **không được giải phóng qua vòng đời ứng dụng**. Với vùng dữ liệu cần xử lý trong một phạm vi rõ, ưu tiên một arena closeable như confined hoặc shared tùy quyền truy cập.

### 7.3. `MemorySegment` không đồng nghĩa với native

`MemorySegment` có thể biểu diễn **heap segment** dựa trên mảng Java, hoặc **native segment** cấp phát qua arena. Ví dụ:

~~~~java
import java.lang.foreign.MemorySegment;

int[] values = {1, 2, 3};
MemorySegment heapSegment = MemorySegment.ofArray(values);

System.out.println(heapSegment.byteSize()); // 12
~~~~

`MemorySegment.ofArray(int[])` là **heap-backed**: không tự chuyển mảng `int[]` sang native memory. Để biết vùng dữ liệu ở đâu, xem nguồn tạo segment và những thuộc tính/vòng đời của nó, không chỉ kiểm tra class name.

### 7.4. Native allocation vẫn cần giới hạn

FFM cung cấp quyền kiểm soát vòng đời và bounds checks; nó **không biến native RAM thành vô hạn** và không tự giải quyết tải do ứng dụng cấp phát quá nhiều vùng cùng lúc. Hãy:

- Hạn chế số byte được cấp phát từ input không tin cậy.
- Gắn closeable arena vào vòng đời request/task đúng cách.
- Không chia sẻ confined arena sang thread khác.
- Với shared arena, đồng bộ việc đọc/ghi dữ liệu chung nếu có mutation.
- Kiểm soát các segment còn reachable và số vùng native còn mở.
- Khi cần gọi native function, đánh giá riêng quyền truy cập, ABI và vòng đời thư viện.

## 8. Code cache, class space và các cấu trúc JVM khác

Ngoài heap/stack/metaspace/direct memory, HotSpot cần các vùng phục vụ compiler, GC và runtime.

### 8.1. Code cache

HotSpot JIT có thể biên dịch các phương thức được sử dụng nhiều thành **machine code**. Machine code ấy và các cấu trúc thực thi liên quan được giữ trong **code cache**, không phải Java heap thông thường.

Một process có `heap used` ổn định nhưng code cache tăng khi ứng dụng warm up là hiện tượng có thể bình thường. Nếu code cache gặp giới hạn, hiệu năng biên dịch/tối ưu có thể bị ảnh hưởng; cần quan sát JIT và code cache thay vì tự quy nó là lỗi heap.

Một số tùy chọn HotSpot có thể kiểm soát code cache, nhưng việc đặt trần mặc định không nên dựa trên một con số chung cho mọi workload. JVM có chính sách ergonomics theo JDK/architecture và cấu hình; hãy đo trên môi trường thật.

### 8.2. Bộ nhớ phục vụ GC và compiler

Garbage collector cần những cấu trúc để quản lý heap, ví dụ card tables, remembered sets và metadata phục vụ tracing; JIT/compiler cũng cần bộ nhớ làm việc. Những vùng này thường góp vào **native memory footprint của JVM** nhưng không phải tất cả đều hiển thị thành “non-heap used” của JMX.

Khi tổng RSS vượt xa heap committed, cần xem **cả GC internals, compiler, thread stacks và các thư viện native**, không chỉ tăng/giảm `-Xmx`.

### 8.3. JNI và thư viện ngoài

Thư viện native có thể gọi `malloc`, ánh xạ tệp, tạo thread hoặc quản lý cache C/C++. Một phần cấp phát ấy nằm **ngoài phạm vi theo dõi của HotSpot Native Memory Tracking**. Vì vậy, một bản NMT “ổn định” không chứng minh rằng không có native memory leak nếu ứng dụng dùng JNI, FFM hoặc thư viện native khác.

Trong trường hợp đó cần xem thêm **OS memory metrics**, memory maps và native profiler thích hợp. Không thay thế phân tích native bằng một heap dump Java nếu triệu chứng rõ ràng nằm ngoài heap.

## 9. Used, committed, reserved, max và RSS: năm con số khác nhau

Đọc sai các con số này là nguồn gốc của nhiều kết luận nhầm lẫn trong vận hành JVM.

| Thuật ngữ | Ý nghĩa gần đúng | Điều **không** nên suy ra |
| --- | --- | --- |
| **Used** | Lượng bộ nhớ đang được đối tượng/cấu trúc sử dụng theo phép đo cụ thể | Không phải mọi byte đều là dữ liệu sống cần giữ |
| **Committed** | Dung lượng JVM/OS đã cam kết để sử dụng theo cơ chế của vùng nhớ | Không đồng nghĩa toàn bộ đã được đưa vào RAM vật lý |
| **Reserved** | Không gian địa chỉ ảo đã được giữ để có thể dùng sau | Không đồng nghĩa lượng RSS hoặc memory quota đã tiêu thụ |
| **Max** | Giới hạn tối đa theo một vùng/cấu hình, có thể không được xác định | Không phải trần toàn bộ process |
| **RSS** | *Resident Set Size*: trang của process đang cư trú trong RAM, theo OS | Không bằng heap used, cũng không nhất thiết bằng tổng NMT committed |

Một số công cụ còn dùng **PSS** (*Proportional Set Size*) để chia phần bộ nhớ dùng chung theo tỷ lệ. Với container, còn phải quan tâm bộ nhớ tính trong **cgroup**: một số metric tính cả page cache hoặc vùng shared, tùy định nghĩa và hệ điều hành.

### 9.1. Ví dụ diễn giải heap memory usage

Giả sử JMX báo:

~~~~text
Heap:
  used      = 420 MiB
  committed = 768 MiB
  max       = 1024 MiB

OS:
  RSS       = 1.3 GiB
~~~~

Diễn giải đúng:

- JVM đang tính khoảng **420 MiB heap used** tại thời điểm đo.
- Heap có khoảng **768 MiB committed** để sẵn sàng phục vụ cấp phát.
- Giới hạn heap tối đa khoảng **1 GiB**.
- Tiến trình đang có khoảng **1.3 GiB trang cư trú** theo định nghĩa RSS của OS.
- Phần chênh lệch **không thể** được kết luận trực tiếp là metaspace hoặc leak: còn nhiều vùng khác, shared mappings và những sai khác trong phép đo.

**Không làm phép tính “RSS - heap used = native leak”** rồi đóng sự cố. Hãy lấy NMT, metrics OS, buffer pools, class loader và thread statistics để phân rã thêm.

### 9.2. NMT `reserved` vs `committed`

Ví dụ HotSpot có thể **reserve** một khoảng địa chỉ ảo lớn cho Java heap nhưng chỉ **commit** phần nhỏ hơn để sử dụng ngay. Trong report NMT, các cột reserved/committed thể hiện hai trạng thái khác nhau. Một reserved mapping nhiều GiB **không có nghĩa đã dùng hết nhiều GiB RAM vật lý**.

Tương tự, một số vùng class space reserve lớn để tiện tổ chức địa chỉ, trong khi committed nhỏ hơn nhiều. Cần xem từng category và xu hướng thay đổi, không chỉ tổng reserved.

### 9.3. Lập ngân sách bộ nhớ cho container

Giả sử container có giới hạn **2 GiB**. Một cách suy nghĩ minh họa là:

~~~~text
Giới hạn process / container
    |
    +-- Heap tối đa, ví dụ 1 GiB
    +-- Metaspace/class metadata
    +-- Platform thread stacks
    +-- Code cache và JIT
    +-- GC internals
    +-- Direct buffers, mapped memory
    +-- Native libraries / Foreign Memory
    +-- Overhead hệ điều hành và headroom
~~~~

Không nên mặc định đặt `-Xmx2g` cho container có hạn mức 2 GiB rồi mong các vùng còn lại không tốn bộ nhớ. Cũng không có công thức cố định như “heap luôn bằng 70% container” cho mọi ứng dụng. Hãy đo tải đại diện, peak memory, số platform threads, class loading và direct memory để dự trù headroom.

Trên HotSpot hiện đại, các tùy chọn container-aware ergonomics có thể chọn kích thước heap dựa trên giới hạn môi trường; nhưng nếu đặt `-Xmx` tường minh, bạn đang đưa ra một quyết định cần kiểm chứng bằng metric thực.

## 10. Những lỗi bộ nhớ thường gặp và vùng cần điều tra

### 10.1. `OutOfMemoryError` không chỉ có một dạng

Thông báo lỗi khác nhau giúp định hướng vùng có vấn đề. Không nên dựa duy nhất vào một chuỗi thông báo vì nội dung có thể khác theo JDK, GC, OS và hoàn cảnh lỗi.

| Triệu chứng / thông báo thường gặp | Hướng điều tra ưu tiên |
| --- | --- |
| `OutOfMemoryError: Java heap space` | Heap used/live set, giữ object qua collection/cache, allocation rate, `-Xmx` |
| `OutOfMemoryError: GC overhead limit exceeded` | GC dành quá nhiều công sức, không thu hồi đủ heap; tùy collector và cơ chế bật |
| `OutOfMemoryError: Requested array size exceeds VM limit` | Kích thước mảng yêu cầu vượt giới hạn thực thi, không chỉ thiếu RAM |
| `OutOfMemoryError: Metaspace` | Class metadata, class loaders, dynamic class generation, metaspace cap |
| `OutOfMemoryError: Compressed class space` | Vùng class space cho compressed pointers nếu cơ chế tương ứng đang dùng |
| `OutOfMemoryError: Cannot reserve... / native allocation failed` | Virtual address space, RAM/container/OS constraints, native malloc/mmap |
| `OutOfMemoryError: unable to create native thread` | Platform threads/OS resource limits, stack memory, process/thread quotas |
| `OutOfMemoryError: Cannot reserve ... direct buffer memory` | Số lượng và kích thước direct buffers, direct memory cap, lifecycle |
| `StackOverflowError` | Độ sâu gọi method/đệ quy, stack size, không mặc định do heap |
| Process bị OS/container kill, không có Java OOME | Cgroup/RSS/OS OOM event, tổng footprint, kernel logs và native memory |

**Lưu ý:** `OutOfMemoryError` là một loại `Error` thường cho biết JVM không còn đủ tài nguyên để tiếp tục bình thường. Đừng viết một `catch (OutOfMemoryError)` rộng rồi “tạo thêm object để ghi log” hoặc tiếp tục giao dịch nghiệp vụ như chưa có gì xảy ra; khả năng phục hồi phụ thuộc trạng thái thực và hạ tầng.

### 10.2. Trường hợp 1: Heap used tăng không hồi

Gợi ý kiểm tra:

1. Quan sát heap used sau các kỳ GC, không chỉ cực đại giữa hai lần GC.
2. Ghi nhận allocation rate và đỉnh traffic.
3. Xem histogram/heap dump ở môi trường được phép.
4. Tìm **GC roots** và các đường giữ object sống.
5. Tập trung vào **retained size** của object graph, không chỉ shallow size của từng instance.

Ví dụ một `HashMap` vài KB có thể giữ hàng triệu object chứa dữ liệu lớn. Histogram cho thấy loại object chiếm nhiều chỗ, nhưng muốn biết **ai giữ chúng sống** phải xem đường tham chiếu trong heap dump.

### 10.3. Trường hợp 2: Heap ổn định, RSS tăng

Các hướng kiểm tra:

- Direct/mapped buffer pools và native allocations.
- Số platform threads và bộ nhớ stack.
- Class loading/metaspace và code cache.
- Native library/FFM allocations.
- File mapping, page cache, shared mappings và hành vi memory allocator của OS.
- NMT committed tăng hay ổn định.

Nếu NMT không cho thấy mức tăng tương xứng, vẫn phải điều tra **cấp phát ngoài phạm vi NMT** và metric của OS. `-Xmx` thấp hơn RSS không đủ để xác định nguyên nhân.

### 10.4. Trường hợp 3: Metaspace tăng sau mỗi lần redeploy

Cần kiểm tra:

- Số class loader mới và cũ.
- Class unloading có xảy ra không.
- Threads, listeners, executors hoặc cache tĩnh còn giữ class loader cũ.
- `ServiceLoader`, plugin registry, framework proxy hoặc bytecode generation có tạo class liên tục không.
- Tình trạng metaspace **sau khi các class loader không còn reachable**, không chỉ trong giai đoạn warm-up.

Không mặc định tăng `MaxMetaspaceSize` là sửa được một classloader leak: nó có thể chỉ làm tiến trình chạy lâu hơn trước khi gặp cùng vấn đề.

## 11. Quan sát bộ nhớ bằng các API Java Management

`java.lang.management` có các MXBean tiêu chuẩn giúp đọc số liệu trực tiếp từ **chính JVM đang chạy**. Những phép đo này phù hợp để tạo metric nền tảng, nhưng không phải một trình native profiler đầy đủ.

### 11.1. `MemoryMXBean`

~~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean bean = ManagementFactory.getMemoryMXBean();

MemoryUsage heap = bean.getHeapMemoryUsage();
MemoryUsage nonHeap = bean.getNonHeapMemoryUsage();

System.out.println("Heap used bytes: " + heap.getUsed());
System.out.println("Heap committed bytes: " + heap.getCommitted());
System.out.println("Heap max bytes: " + heap.getMax());
System.out.println("Non-heap used bytes: " + nonHeap.getUsed());
~~~~

`MemoryUsage` có các thuộc tính:

| Getter | Ý nghĩa |
| --- | --- |
| `getInit()` | Bộ nhớ ban đầu được yêu cầu, có thể không xác định |
| `getUsed()` | Lượng đang dùng theo nghĩa của memory pool |
| `getCommitted()` | Lượng cam kết sẵn cho JVM sử dụng |
| `getMax()` | Giới hạn tối đa, có thể trả **`-1`** nếu không xác định |

**Không vẽ biểu đồ max = -1 byte** rồi coi nó là số âm thực tế. `-1` thường là ký hiệu “không xác định” trong các API quản lý bộ nhớ.

### 11.2. `MemoryPoolMXBean`: các pool riêng của JVM

~~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
    MemoryUsage usage = pool.getUsage();
    if (usage != null) {
        System.out.printf(
                "%s (%s): used=%d, committed=%d%n",
                pool.getName(),
                pool.getType(),
                usage.getUsed(),
                usage.getCommitted());
    }
}
~~~~

Tên pool như “G1 Eden Space”, “Metaspace” hoặc “CodeHeap ...” **không phải hợp đồng portable** áp dụng cho tất cả JVM/collector. Muốn thu thập metric, hãy kiểm tra loại pool, tên do runtime công bố và cấu hình môi trường; đừng hardcode một tập tên pool cho mọi Java process.

### 11.3. `BufferPoolMXBean`: direct và mapped buffers

~~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {

    System.out.printf(
            "%s: count=%d capacity=%d bytes used=%d bytes%n",
            pool.getName(),
            pool.getCount(),
            pool.getTotalCapacity(),
            pool.getMemoryUsed());
}
~~~~

`BufferPoolMXBean` có thể công bố các pool `direct` hoặc `mapped`. `getMemoryUsed` là **ước lượng**, có thể khác `getTotalCapacity` do alignment, allocator hoặc đặc điểm implementation, và có thể trả `-1` nếu không có ước lượng.

**Không** hiểu tổng `getMemoryUsed` của các buffer pools là toàn bộ off-heap native usage. Nó không phải phép đo tổng mọi cấp phát từ FFM/JNI, metaspace, stack và code cache.

### 11.4. `ThreadMXBean` và số luồng

~~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean threads = ManagementFactory.getThreadMXBean();
System.out.println("Live monitored threads: " +
        threads.getThreadCount());
~~~~

Các metric `ThreadMXBean` truyền thống không bảo đảm thể hiện **toàn bộ virtual threads** theo cách bạn mong đợi. Với virtual-thread-heavy workload, dùng thêm các công cụ và event dành riêng cho virtual threads như `jcmd Thread.dump_to_file`, JFR hoặc các interface quản lý virtual-thread scheduler khi phù hợp.

## 12. Chương trình quan sát bộ nhớ tự chứa

Ví dụ sau chỉ đọc số liệu, không cưỡng bức GC hoặc cấp phát mảng khổng lồ. Lưu thành `JvmMemoryOverview.java`:

~~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public class JvmMemoryOverview {

    private static String mib(long bytes) {
        return bytes < 0
                ? "n/a"
                : String.format("%.1f MiB", bytes / 1_048_576.0);
    }

    private static void printUsage(String label, MemoryUsage usage) {
        System.out.printf(
                "%s: used=%s committed=%s max=%s%n",
                label,
                mib(usage.getUsed()),
                mib(usage.getCommitted()),
                mib(usage.getMax()));
    }

    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        System.out.println("=== JVM memory snapshot ===");
        printUsage("Heap", memory.getHeapMemoryUsage());
        printUsage("Non-heap", memory.getNonHeapMemoryUsage());

        System.out.println("=== JVM memory pools ===");
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {

            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                printUsage(pool.getName(), usage);
            }
        }

        System.out.println("=== Buffer pools ===");
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {

            System.out.printf(
                    "%s: count=%d used=%s capacity=%s%n",
                    pool.getName(),
                    pool.getCount(),
                    mib(pool.getMemoryUsed()),
                    mib(pool.getTotalCapacity()));
        }

        Runtime runtime = Runtime.getRuntime();
        System.out.println("=== Runtime ===");
        System.out.println("Heap max via Runtime: " +
                mib(runtime.maxMemory()));
    }
}
~~~~

Chạy ví dụ (cần JDK 27 được cài và nằm trên PATH):

~~~~text
javac JvmMemoryOverview.java
java -Xms128m -Xmx512m JvmMemoryOverview
~~~~

**Đừng ngạc nhiên** nếu các pool/giá trị dùng khác nhau giữa máy, lần chạy hoặc collector. Ngay cả `-Xmx512m` cũng không bảo đảm `getMax()` hoặc tổng các pool chính xác bằng một con số hiển thị duy nhất theo đơn vị MiB sau mọi ràng buộc và làm tròn.

### 12.1. Vì sao không dùng `System.gc()` để “kiểm tra cho chính xác”?

`System.gc()` là **yêu cầu** JVM thực hiện GC, không phải cam kết rằng heap sẽ đạt trạng thái mong muốn ngay sau lời gọi. JVM/collector/flag có thể quyết định khác, và lệnh GC chủ động có thể tác động latency của production.

Khi lấy metric để điều tra, ưu tiên **chuỗi thời gian** và GC logs/JFR thay vì lặp đi lặp lại `System.gc()` rồi kết luận bộ nhớ có leak hay không.

## 13. Theo dõi HotSpot bằng `jcmd`, NMT, GC logs và JFR

Java 27 có nhiều công cụ chẩn đoán chính thức. Hãy chọn đúng công cụ theo câu hỏi:

| Câu hỏi | Công cụ phù hợp |
| --- | --- |
| Heap hiện đang có kích thước và mức dùng ra sao? | `jcmd <pid> GC.heap_info`, MXBeans |
| Loại object nào đang chiếm nhiều heap? | `GC.class_histogram` hoặc heap dump có kiểm soát |
| Tại sao object vẫn sống? | Heap dump + công cụ phân tích GC roots/retained paths |
| Metaspace tăng ở class loader nào? | `VM.metaspace`, `VM.classloader_stats` |
| Native memory nội bộ HotSpot tăng ở subsystem nào? | NMT `summary` / `summary.diff` |
| Có nhiều platform/virtual threads? | `Thread.dump_to_file`, JFR, OS metrics |
| GC pause và allocation rate ra sao? | Unified GC logging, JFR |
| RSS tăng nhưng NMT không giải thích? | OS/process memory maps, native profiler |

Các lệnh `jcmd` cần quyền phù hợp và thông thường phải chạy trên **cùng máy/container context** hoặc môi trường hỗ trợ attach vào JVM đích. Cú pháp thực tế có thể được kiểm tra bằng `jcmd <pid> help` và `jcmd <pid> help <command>`.

### 13.1. Xác định PID và xem heap

~~~~text
jcmd -l
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~~

`<pid>` trong tài liệu là placeholder, cần thay bằng **PID thật**. Không sao chép ký tự `<` và `>` nguyên văn vào terminal khi dùng lệnh. Trong container, PID hiển thị ngoài host và PID trong namespace container có thể khác nhau.

Một số lệnh chẩn đoán có mức impact **Medium hoặc High**, nên cân nhắc trên production và không chạy hàng loạt không có giới hạn.

### 13.2. Xem metaspace và class loaders

~~~~text
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.classloader_stats
~~~~

`VM.metaspace basic` báo thống kê metaspace ở mức cơ bản. Muốn xem sâu hơn, có tùy chọn như `show-loaders`; hãy đọc `jcmd <pid> help VM.metaspace` để chọn chính xác và đánh giá chi phí của lệnh.

~~~~text
jcmd <pid> VM.metaspace show-loaders
~~~~

Chú ý “có nhiều class loaders” không tự đủ để kết luận leak. Cần so sánh nhiều thời điểm và xem loader nào được dự kiến sống theo vòng đời ứng dụng. Class loaders của framework, module, proxy, application server có thể là hoàn toàn hợp lệ.

### 13.3. Native Memory Tracking (NMT)

**NMT** là tính năng của **HotSpot VM** để theo dõi các cấp phát nội bộ JVM. Phải bật khi khởi động JVM:

~~~~text
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~~

Hoặc thu thập mức chi tiết hơn:

~~~~text
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~~

NMT mặc định **tắt**. Sau khi JVM chạy, có thể xem:

~~~~text
jcmd <pid> VM.native_memory summary scale=MB
~~~~

Lấy baseline và so sánh sau một khoảng tải:

~~~~text
jcmd <pid> VM.native_memory baseline

# Thực hiện workload có kiểm soát trong môi trường được phép.

jcmd <pid> VM.native_memory summary.diff scale=MB
~~~~

**Giới hạn quan trọng của NMT:**

- Theo dõi nội bộ **HotSpot/JVM**, không bao phủ tất cả native allocation của mã bên ngoài JVM, ví dụ nhiều thư viện JNI và native allocations của JDK class libraries.
- Không thay thế metric RSS/PSS hoặc memory maps do OS cung cấp.
- Không báo chính xác từng byte của một Java object graph; heap dump và heap profiler phù hợp hơn cho câu hỏi đó.
- Có overhead. Tài liệu Oracle lưu ý NMT có thể tăng chi phí khoảng **5–10%** tùy môi trường; dùng thận trọng trên production.
- Có thể **tắt** NMT qua công cụ, nhưng không thể bật lại từ trạng thái tắt bằng `jcmd` cho một process đã khởi động mà không bật tính năng này từ đầu.

`summary` cho phép thấy các nhóm như Java Heap, Class, Thread, Code, GC, Compiler và nội bộ. `detail` thêm thông tin call sites/vùng nhớ nhưng tốn chi phí lớn hơn.

### 13.4. Đọc một báo cáo NMT đúng cách

Ví dụ **minh họa, không phải output chuẩn của mọi JVM**:

~~~~text
Total: reserved=5000MB, committed=1000MB
  Java Heap  (reserved=3072MB, committed=600MB)
  Class      (reserved=1000MB, committed=100MB)
  Thread     (reserved=350MB, committed=50MB)
  Code       (reserved=250MB, committed=80MB)
  GC         (reserved=..., committed=...)
  ...
~~~~

Ý nghĩa:

- “Java Heap reserved 3 GiB” **không có nghĩa heap dùng 3 GiB RAM**.
- “Class reserved 1 GiB” có thể bao gồm class space reserve; cần xem committed và phần chia theo loader.
- “Thread reserved 350 MiB” không có nghĩa đang dùng 350 MiB vật lý cho stack.
- “Total committed 1 GiB” **không phải** một phiên bản chính xác của RSS.

Hãy ưu tiên **mức tăng theo thời gian của từng category** và đối chiếu sự kiện workload. Nếu tăng nhanh ở Class, đi điều tra class loaders; nếu tăng ở Thread, kiểm tra thread lifecycle; nếu NMT không tăng nhưng RSS tăng, mở rộng điều tra đến cấp phát ngoài NMT/OS.

### 13.5. Java Flight Recorder (JFR)

**JFR** là công cụ profiling/diagnostics của JDK, giúp thu các event như GC, allocation pressure, class loading, thread activity và một số hoạt động runtime khác với overhead phụ thuộc cấu hình.

Ví dụ chạy ghi nhận có giới hạn (chỉ thực hiện trên JVM được phép):

~~~~text
jcmd <pid> JFR.start name=memory-check settings=profile duration=60s filename=memory-check.jfr
~~~~

Có thể mở file trong công cụ phân tích hỗ trợ JFR như **JDK Mission Control** hoặc ứng dụng có khả năng đọc JFR. Các event cụ thể phụ thuộc cấu hình recording, JVM và phiên bản JDK; không mặc định mọi loại event được ghi ở mức chi tiết giống nhau.

**File JFR có thể chứa dữ liệu nhạy cảm**: tên class, stack trace, đường dẫn và metadata ứng dụng. Áp dụng quy định lưu trữ, phân quyền và xóa file phù hợp.

### 13.6. Unified GC logging

HotSpot hỗ trợ logging theo tag/level. Một cấu hình minh họa để quan sát GC:

~~~~text
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~~

Đây là ví dụ cấu hình, không phải thiết lập tối ưu chung. Khối lượng log phụ thuộc tag và level; mức quá chi tiết có thể tạo lượng file/chi phí I/O lớn. Với process dài hạn, cần cấu hình rotation và retention theo yêu cầu vận hành.

GC log giúp trả lời:

- GC xảy ra thường xuyên không?
- Heap trước và sau GC có xu hướng thế nào?
- Có pause lớn hoặc allocation pressure không?
- Live data sau GC có tăng qua nhiều chu kỳ cùng tải không?

GC log **không tự chỉ ra đường tham chiếu** khiến một object sống lâu; cần heap dump/heap profiler khi điều tra retained objects.

### 13.7. Histogram và heap dump

~~~~text
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /secure-diagnostics/app-heap.hprof
~~~~

**Cảnh báo vận hành:**

- `GC.class_histogram` có mức impact cao, có thể cần phối hợp với GC tùy tùy chọn/implementation.
- `GC.heap_dump` có impact **High**; theo tài liệu Java 27, theo mặc định nó có thể yêu cầu full GC trước khi tạo dump nếu không dùng tùy chọn `-all`. Hãy cân nhắc latency và disk space.
- Heap dump có thể rất lớn và chứa **toàn bộ thông tin object**: dữ liệu cá nhân, token, mật khẩu, payload và những bí mật còn trong heap. Chỉ ghi vào nơi an toàn.
- Không dùng heap dump như một “backup ứng dụng” để khôi phục trạng thái nghiệp vụ.

Nếu JVM vừa bị OS kill mà không tạo kịp heap dump, cần kiểm tra thêm event OOM của container và metric OS. Việc bật các tùy chọn chẩn đoán khi lỗi phải phù hợp quyền vận hành, disk quota và chính sách dữ liệu.

### 13.8. Quan sát virtual threads

`jcmd` Java 27 có thể xuất thread dump gồm cả virtual threads:

~~~~text
jcmd <pid> Thread.dump_to_file -format=plain threads.txt
~~~~

Đối với JVM cần JSON:

~~~~text
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~~

`Thread.print` thiên về platform threads và các virtual threads đang mounted, còn `Thread.dump_to_file` cung cấp danh sách phù hợp hơn cho phân tích lượng lớn virtual threads. Với lượng thread rất lớn, file output cũng có thể lớn và chứa tên/stack trace nhạy cảm.

## 14. Ví dụ quan sát cách giữ dữ liệu làm heap tăng

Chương trình nhỏ dưới đây minh họa **retention** ở mức Java. Nó cố ý cấp phát một lượng dữ liệu có **giới hạn**, sau đó bỏ các tham chiếu:

~~~~java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

public class HeapRetentionDemo {
    private static final List<byte[]> CACHE = new ArrayList<>();

    private static long heapUsed() {
        return ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage()
                .getUsed();
    }

    public static void main(String[] args) {
        System.out.println("Before: " + heapUsed());

        for (int i = 0; i < 8; i++) {
            CACHE.add(new byte[1024 * 1024]);
        }

        System.out.println("Retained: " + heapUsed());
        System.out.println("Entries: " + CACHE.size()); // 8

        CACHE.clear();
        System.out.println("After clear: " + heapUsed());
    }
}
~~~~

Chạy trong môi trường test:

~~~~text
javac HeapRetentionDemo.java
java -Xmx128m HeapRetentionDemo
~~~~

**Không đòi hỏi** ba số heap used phải tăng/giảm chính xác 8 MiB. JVM còn các object khác, và thời điểm GC là không xác định. Điểm của bài tập:

- Khi `CACHE` giữ các mảng, chúng vẫn reachable.
- Sau `CACHE.clear()`, nếu không có alias khác, chúng có thể đủ điều kiện được GC thu hồi.
- Việc chưa thấy used/RSS giảm ngay không chứng minh chúng còn reachable.
- Nếu ứng dụng **tiếp tục thêm** vào một cache tĩnh không giới hạn, live set có thể tăng liên tục.

Không dùng `System.gc()` trong vòng lặp production để cưỡng bức giảm heap sau mỗi request. Hãy thiết kế cache có **giới hạn kích thước, thời gian tồn tại và chính sách eviction**, thay vì dùng GC để quản lý logic nghiệp vụ.

## 15. Một quy trình chẩn đoán thực tế, từng bước

Giả sử cảnh báo cho biết “container memory gần đạt 95%”, nhưng biểu đồ heap mới khoảng 60% `-Xmx`.

### Bước 1 — Phân loại tín hiệu

Ghi lại:

- JDK và JVM implementation/version thực tế.
- Giới hạn memory của container/VM, RSS, page cache, cgroup events.
- `-Xms`, `-Xmx`, `-Xss`, metaspace/direct-memory flags.
- Số platform threads, virtual threads (nếu quan sát được), class loaders.
- Heap used/committed sau GC và tình trạng GC.

**Không** tăng `-Xmx` ngay khi cảnh báo là tổng RSS/cgroup memory; tăng heap có thể khiến process bị kill sớm hơn.

### Bước 2 — Xem có đang chạm giới hạn heap không

Nếu heap sau GC gần trần và live set tăng, ưu tiên heap dump/histogram và object reachability. Nếu heap used/committed ổn định, đừng dừng ở phân tích heap.

### Bước 3 — Xem NMT và native metrics

Nếu NMT đã bật, lấy `summary` và `summary.diff`. So sánh Class/Thread/Code/GC cùng các thành phần khác, đối chiếu với `BufferPoolMXBean` và OS metrics. Nếu NMT tắt, ghi nhận giới hạn này; lập kế hoạch bật NMT trong lần restart có kiểm soát nếu cần.

### Bước 4 — Thu hẹp theo subsystem

- Tăng **Class** → class loaders, proxy/dynamic code, metaspace.
- Tăng **Thread** → platform thread creation, executor lifecycle và stack.
- Tăng **direct buffer** → I/O buffers, pooling, giữ reference và cap.
- Tăng **heap live set** → object graph và GC roots.
- NMT không giải thích hết RSS → JNI, FFM, native library, OS mappings/allocator.

### Bước 5 — Tạo giả thuyết kiểm chứng được

Ví dụ: “Trong khoảng 30 phút, số platform threads tăng từ 100 lên 2.000 cùng với NMT Thread committed tăng”. Đây là một giả thuyết có thể kiểm tra bằng thread dump, executor lifecycle và tải mô phỏng.

Tránh giả thuyết mơ hồ như “Java GC không hoạt động tốt” nếu chưa có metric chứng minh.

### Bước 6 — Thử thay đổi trong môi trường đại diện

Sửa nguồn retention, đóng native resources, giới hạn concurrency hoặc điều chỉnh đúng vùng bộ nhớ, rồi chạy test tải tương tự. So sánh:

- Memory footprint lúc ổn định và lúc peak.
- Latency/pause, CPU và throughput.
- Live set và NMT/RSS trend.
- Số resource còn mở sau khi tải dừng.

**Mục tiêu không phải ép mọi biểu đồ memory trở về 0**, mà là chứng minh bộ nhớ và tài nguyên **được giới hạn theo tải**, không tăng vô hạn và vận hành trong ngân sách/container.

## 16. Hiểu đúng các mối liên hệ giữa heap, stack và metaspace

### 16.1. Ví dụ object, local variable, static field

~~~~java
import java.util.List;

public class ReferenceModel {
    private static List<String> catalog = List.of("A", "B");

    static void process() {
        String value = new String("item");
        printValue(value);
    }

    static void printValue(String text) {
        System.out.println(text);
    }
}
~~~~

**Giải thích theo mô hình thông thường:**

- `ReferenceModel` được JVM nạp; HotSpot lưu **class metadata** trong những cấu trúc như metaspace.
- `catalog` là **static field** thuộc trạng thái của class; giá trị của nó tham chiếu một object `List`. Không kết luận “static field và toàn bộ List đều nằm trong metaspace”.
- `process()` tạo một local reference `value`. Object `String` thuộc mô hình object Java; runtime có thể tối ưu cấp phát nếu hợp lệ.
- `printValue(text)` nhận một tham chiếu; không tự động clone `String` trước khi in.
- Khi frame kết thúc, local reference của frame không còn sống qua frame ấy, nhưng object có thể còn được giữ bởi **tham chiếu khác**.

Trong mô hình JIT đã tối ưu, compiler có thể loại bỏ hoặc biến đổi những cấp phát/frame không quan sát được, nên đừng suy vị trí vật lý từng byte từ cú pháp Java.

### 16.2. Static field có thể gây heap leak **và** gián tiếp giữ metaspace

Nếu một `static List<ClassLoader>` lưu mọi loader từng nạp, nó có thể:

1. Chiếm **heap** cho collection và các object tham chiếu.
2. Giữ class loaders còn reachable.
3. Khiến class metadata tương ứng **không đủ điều kiện unload**, làm metaspace tiếp tục được giữ.

Vì vậy, lỗi tăng heap và tăng metaspace có thể có **cùng một nguyên nhân gốc**: vòng đời class loader không được quản lý. Phải điều tra root references thay vì coi hai vùng hoàn toàn không liên quan.

### 16.3. Stack không phải “nơi chứa mọi primitive”

Đôi khi tài liệu đơn giản nói “primitive ở stack, object ở heap”. Mệnh đề đó **không chính xác**:

~~~~java
record Sample(int count, long total) {
}

Sample value = new Sample(3, 10L);
int[] counts = new int[] {1, 2, 3};
~~~~

Các trường `int` và `long` nằm trong cấu trúc dữ liệu của object `Sample` theo mô hình object, còn các phần tử `int` của mảng nằm trong **mảng Java**. Chúng không phải tự di chuyển sang platform stack chỉ vì là primitive.

Stack frame giữ **giá trị local/operand** theo thực thi method, có thể gồm primitive hoặc reference. Nơi storage thực tế của một biến có thể được tối ưu vào register hoặc cấu trúc khác tùy JIT.

## 17. Kiểm thử và quan sát các trường hợp biên

### 17.1. Bảng kịch bản

| Kịch bản | Nên quan sát | Kết luận hợp lệ |
| --- | --- | --- |
| Tạo nhiều object ngắn hạn rồi bỏ | Heap allocation, GC logs | Allocation rate cao chưa chắc leak |
| `static List` giữ mảng ngày càng lớn | Heap after GC, retained size | Có nguy cơ leak do giữ tham chiếu |
| Tăng `-Xmx` nhưng RSS vẫn vượt quota | OS/cgroup, NMT, pools | Quota quá thấp hoặc native usage cần phân tích |
| Tạo nhiều platform threads | Thread count, NMT Thread, OS quota | Có thể thiếu OS threads/native stack |
| Tạo nhiều virtual threads chờ I/O | Heap, số virtual threads, ThreadLocal objects | Virtual threads rẻ hơn nhưng không miễn phí |
| Tạo nhiều ClassLoader rồi giữ reference | Metaspace, classloader stats | Metadata có thể không unload |
| Tạo nhiều direct buffers và giữ reference | BufferPoolMXBean, direct memory pressure | Heap dùng cho wrapper không phản ánh backing size |
| Cấp phát nhiều Arena.ofConfined rồi quên close | Native allocation trend | Cần quản lý lifecycle và close |
| Arena.global cấp phát liên tục | Native memory và process RSS | Không có cơ chế close tường minh để trả vùng đó |
| Heap used giảm sau GC nhưng RSS không giảm | Heap committed, OS metrics | Không chứng minh có leak |
| NMT ổn định nhưng RSS tăng | OS maps, third-party JNI, mapped memory | NMT không bao trùm mọi nguồn native |
| Java process bị container kill mà không có Java exception | cgroup OOM event, kernel logs | Có thể là OS-level kill, không phải Java heap OOME |

### 17.2. Không tạo OOME như một bài tập production

Để hiểu OOME, **không cần** chạy vòng lặp `while (true) { list.add(new byte[...]); }` trên hệ thống thật. Bài học nên ưu tiên **mô hình và công cụ chẩn đoán**. Nếu cần mô phỏng trong lớp học, hãy sử dụng sandbox riêng với quota nhỏ, đo đạc và cơ chế tự dừng rõ ràng, không chạy trên máy production hoặc máy có dữ liệu quan trọng.

### 17.3. Quan sát file dump có rủi ro bảo mật

Heap dump, core dump, JFR và một số thread dump có thể chứa thông tin hệ thống hoặc dữ liệu cá nhân. Trước khi tạo:

- Xác định đường dẫn có đủ dung lượng và quyền chỉ người vận hành được xem.
- Hạn chế các token, khóa bí mật hoặc nội dung user xuất hiện trong artifact nếu có thể.
- Không gửi dump thô vào kênh chat công khai, bug tracker không kiểm soát hoặc kho mã nguồn.
- Đặt retention, cleanup và cơ chế truyền file an toàn.

Nếu dump tác động lớn đến latency, phải cân nhắc cửa sổ vận hành và ngân sách hiệu năng. Không tự chạy lệnh có impact High lên production chỉ vì thấy chúng xuất hiện trong ví dụ.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `-Xmx` là tổng RAM JVM được phép dùng | JVM còn stack, metaspace, code cache, native memory | Cần ngân sách toàn process/container |
| Mọi primitive đều nằm trên stack | Primitive có thể là field/array element trên heap | Phân biệt giá trị local với data structure |
| Mọi `new` bắt buộc tạo object vật lý trên heap | JIT có thể tối ưu cấp phát | Dùng mô hình ngữ nghĩa, đo runtime |
| Local reference bị gán null là object được giải phóng tức thì | Còn alias khác hoặc GC chưa chạy | Xem reachability và vòng đời GC |
| Heap used giảm thì RSS cũng phải giảm | JVM/OS có thể giữ committed pages | Phân biệt used, committed, RSS |
| Compressed Class Space reserved 1 GiB nghĩa là dùng 1 GiB RAM | Reserved là không gian địa chỉ ảo | Xem committed/used |
| Non-heap MXBean bằng toàn bộ native memory | Không bao gồm mọi cấp phát ngoài JVM memory pools | Kết hợp NMT và OS metrics |
| NMT đo đủ JNI và mọi thư viện native | NMT chủ yếu theo dõi HotSpot internals | Dùng native profiler và memory maps nếu cần |
| Metaspace chính là nơi chứa mọi static object | Static field có thể tham chiếu object trên heap | Tách class metadata khỏi object graph |
| Java 27 vẫn cần `MaxPermSize` | PermGen là khái niệm HotSpot cũ | Dùng metaspace hiện hành |
| Có nhiều class là chắc chắn leak | Có thể là khởi tạo bình thường | Quan sát xu hướng và class loader lifecycle |
| Virtual thread không tốn stack | Stack được quản lý khác platform thread nhưng vẫn tốn memory | Theo dõi stack chunks và object giữ bởi task |
| `-Xss1m` nghĩa mỗi virtual thread tốn 1 MiB native RAM | Virtual thread không giữ OS stack riêng suốt vòng đời | Không ước lượng kiểu platform thread |
| DirectByteBuffer có wrapper trên heap nên toàn bộ data cũng trên heap | Backing có thể là native memory | Xem BufferPoolMXBean và native usage |
| `MaxDirectMemorySize` giới hạn tất cả native memory | Chỉ chi phối một số direct buffer allocations | Theo dõi riêng FFM/JNI/stacks/metaspace |
| `Arena.global()` tự động giải phóng khi method kết thúc | Global arena có vòng đời không giới hạn | Dùng arena có scope phù hợp |
| `System.gc()` là cách sửa memory leak | Không sửa nguyên nhân giữ object | Tìm GC roots/retained paths |
| Heap dump luôn rẻ và vô hại | Có thể pause, tạo file lớn và chứa dữ liệu nhạy cảm | Đánh giá impact và quyền truy cập |
| Tăng memory limit luôn chữa được OOME | Leak và giới hạn khác vẫn tồn tại | Chọn đúng vùng và sửa root cause |

## 19. Hướng dẫn lựa chọn bước chẩn đoán

| Triệu chứng chính | Bước ưu tiên |
| --- | --- |
| `Java heap space` | GC logs → histogram/heap dump → GC roots và cache lifecycle |
| `Metaspace` | `VM.metaspace` → `VM.classloader_stats` → phân tích classloader retention |
| Native thread creation failure | Thread count/dumps → executor lifecycle → OS/thread quota |
| Direct buffer pressure | `BufferPoolMXBean` → I/O buffer lifecycle → direct memory cap |
| RSS cao, heap ổn định | NMT + OS metrics → stacks, code, FFM/JNI, memory maps |
| GC pause cao | JFR/GC logs → allocation/live set → collector/workload tuning |
| Cgroup OOM kill | Container events + RSS + peak workload → process memory budget |
| Mapped memory nghi ngờ tăng | Buffer pool + OS maps → file channel/mapping lifecycle |
| Virtual threads nhiều | Thread dump/JFR → task lifecycle, ThreadLocal, request fan-out |

### Checklist vận hành bộ nhớ Java 27

- [ ] Biết chính xác JVM implementation và JDK version đang chạy.
- [ ] Đã phân biệt heap, native stack, metaspace, code cache, direct/foreign memory.
- [ ] `-Xms` và `-Xmx` được cấu hình theo ngân sách process/container, không phải theo cảm tính.
- [ ] Có giới hạn hợp lý cho platform threads, connection pools, queues và buffer caches.
- [ ] Biết dùng JMX `MemoryMXBean`, `MemoryPoolMXBean` và `BufferPoolMXBean`.
- [ ] Không xem `non-heap used` như tổng native RAM.
- [ ] Đã phân biệt used/committed/reserved/max/RSS và kiểm tra xu hướng qua thời gian.
- [ ] Có GC logging/JFR phù hợp cho môi trường vận hành.
- [ ] Nếu cần NMT, đã **bật khi khởi động** và chấp nhận overhead.
- [ ] Dùng `VM.metaspace` và classloader diagnostics khi class metadata tăng.
- [ ] Xem số platform threads và giới hạn OS khi gặp native thread failure.
- [ ] Với virtual threads, không giả định mỗi task có stack native cố định hoặc hoàn toàn miễn phí.
- [ ] Với direct buffers và FFM arenas, có chính sách lifecycle và giới hạn cấp phát.
- [ ] Với thư viện native, biết NMT có thể không theo dõi đầy đủ.
- [ ] Không dựa vào `System.gc()` để giải phóng resource nghiệp vụ.
- [ ] Chỉ tạo dump trên process được phép và giữ file theo chính sách bảo mật.
- [ ] Mọi kết luận leak dựa trên **dữ liệu theo thời gian và đường giữ tham chiếu**, không chỉ một snapshot.

## 20. Tài liệu tham khảo chính thức

- [Java SE 27 — Java Virtual Machine / Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/27/troubleshoot/troubleshooting-memory-leaks.html): các dạng lỗi bộ nhớ, heap/metaspace và hướng điều tra.
- [Java SE 27 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/27/vm/native-memory-tracking.html): phạm vi NMT, reserved/committed, `summary`, `detail`, `baseline` và giới hạn theo dõi.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-Xss`, metaspace/direct-memory flags và unified logging.
- [Java SE 27 — The jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): `GC.heap_info`, `GC.heap_dump`, `GC.class_histogram`, `VM.metaspace`, `VM.native_memory`, `Thread.dump_to_file` và JFR.
- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): platform vs virtual threads, carrier, diagnostics và lifecycle.
- [Java SE 27 — MemoryMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryMXBean.html) và [MemoryUsage](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryUsage.html): heap/non-heap management metrics.
- [Java SE 27 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): các memory pools do JVM công bố.
- [Java SE 27 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): thống kê direct/mapped buffer pools.
- [Java SE 27 — ByteBuffer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/ByteBuffer.html): `allocate`, `allocateDirect` và direct buffers.
- [Java SE 27 — Arena](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): quản lý scope/lifecycle của memory segments.
- [Java SE 27 — MemorySegment](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): heap/native segments, bounds/lifetime checks.

**Kết luận:** Khi phân tích JVM của **Java 27**, hãy bắt đầu bằng việc **phân loại vùng bộ nhớ** trước khi chỉnh flag. **Heap** lưu phần lớn dữ liệu đối tượng; **stack** gắn với thực thi method và có mô hình khác nhau giữa platform/virtual threads; **metaspace** lưu class metadata của HotSpot; còn **native memory** gồm buffer, code cache, GC/runtime structures, native stacks và nhiều cấp phát ngoài heap khác. Các con số **used, committed, reserved, RSS** không hoán đổi được. Muốn xử lý sự cố đúng, phải kết hợp GC/JMX/JFR, NMT, `jcmd` và metric của OS, rồi sửa **nguyên nhân giữ dữ liệu hoặc cấp phát quá mức**, thay vì chỉ tăng `-Xmx`.
