# Bộ nhớ riêng của luồng và bộ nhớ dùng chung trong đặc tả JVM

## 1. Bức tranh tổng thể

Java Virtual Machine Specification (JVMS) định nghĩa nhiều **run-time data areas**. Có vùng tồn tại cho toàn bộ JVM và được mọi luồng sử dụng, có vùng được tạo riêng cho từng Java thread. Phân biệt chính xác giúp giải thích vì sao hai luồng có local variables độc lập nhưng vẫn có thể cùng sửa một object; vì sao đệ quy sâu thường liên quan tới stack; và vì sao OutOfMemoryError không nhất thiết có nghĩa Java heap đã đầy.

**Theo JVMS §2.5:**

| Vùng | Phạm vi | Vai trò |
| --- | --- | --- |
| **`pc` register** | **Mỗi thread riêng** | Ghi địa chỉ instruction JVM hiện tại khi chạy Java method không phải native |
| **JVM stack** | **Mỗi thread riêng** | Chứa các frame tương ứng những lời gọi method đang hoạt động |
| **Native method stack** | **Thường theo thread nếu implementation có sử dụng** | Hỗ trợ native methods và thành phần VM cần conventional native stacks |
| **Heap** | **Chung cho mọi JVM threads** | Cấp phát class instances và arrays, được quản lý bằng GC |
| **Method area** | **Chung cho mọi JVM threads** | Per-class structures, field/method information, code, run-time constant pools |
| **Run-time constant pool** | **Mỗi class/interface một pool**, cấp phát trong method area dùng chung | Constants và symbolic references để liên kết |
| **Frame** | **Mỗi method invocation trong thread riêng** | Local-variable array, operand stack, tham chiếu tới run-time constant pool |

Cần phân biệt **phạm vi logic** của JVMS với **vị trí vật lý trong RAM**. JVM implementation, JIT compiler và garbage collector có quyền chọn layout/technique khác nhau miễn giữ đúng hành vi đã được đặc tả. Ví dụ, HotSpot Metaspace là kỹ thuật hiện thực class metadata, **không phải tên của vùng bắt buộc trong JVMS**.

### Sơ đồ liên hệ

~~~text
                         ONE JVM
+---------------------------------------------------------+
|                                                         |
| THREAD A                              THREAD B           |
| +--------------------+                +----------------+ |
| | pc A               |                | pc B           | |
| | JVM stack A        |                | JVM stack B    | |
| |   frame run()      |                |   frame run()  | |
| |   - locals         |                |   - locals     | |
| |   - operand stack  |                |   - operand    | |
| |   - pool reference |                |     stack      | |
| |   frame helper()   |                |   - pool ref   | |
| | native stack (*)   |                | native stack(*)| |
| +--------------------+                +----------------+ |
|                  |                        |             |
|                  v                        v             |
| +-----------------------------------------------------+ |
| | HEAP: objects, arrays                              | |
| |   shared Counter object, int[] results, ...        | |
| +-----------------------------------------------------+ |
| +-----------------------------------------------------+ |
| | METHOD AREA: per-class structures, method code     | |
| |   constant pool of Class X                         | |
| |   constant pool of Class Y                         | |
| +-----------------------------------------------------+ |
+---------------------------------------------------------+

(*) Chỉ nếu implementation dùng native method stacks.
~~~

Trong sơ đồ, hai frames khác nhau có thể cùng tham chiếu một pool vì chúng thực thi method thuộc cùng runtime class; điều đó **không khiến hai operand stacks hoặc local arrays thành một**.

## 2. pc register: trạng thái điều khiển riêng cho từng thread

Theo **JVMS §2.5.1**, mỗi JVM thread có một **pc register logic**. Khi thread chạy method Java không phải native, pc giữ địa chỉ instruction JVM đang thực thi; khi chạy native method, giá trị pc trong mô hình JVMS **không được xác định**. Hai threads chạy cùng method có thể ở hai bytecode offsets khác nhau. Pc **không** phải source line và không nhất thiết trùng CPU instruction pointer; `javap -c` và `LineNumberTable` cho thông tin liên quan ở **class file**, không phải API đọc pc chính xác của thread bất kỳ.

## 3. JVM stack: chuỗi frames riêng theo thread

Theo **JVMS §2.5.2**, mỗi JVM thread có một **JVM stack** chứa các frames của những method invocations đang hoạt động. Nếu thread A gọi `main → calculate → add`, ba frames logic nằm trên JVM stack A. Thread B có stack và frames riêng, dù có thể cùng gọi `add`.

~~~text
Thread A                      Thread B
pc A                          pc B
JVM stack A                   JVM stack B
  ├── frame add                  └── frame run
  ├── frame calculate
  └── frame main

Shared heap: references trong hai stacks có thể cùng trỏ tới một object.
~~~

**JVM stack không phải operand stack.** JVM stack chứa nhiều frames; mỗi frame lại chứa một operand stack riêng. JVMS không buộc tất cả frames có một layout native RAM cố định, và một implementation có thể áp dụng JIT/deoptimization hoặc các cách biểu diễn khác mà vẫn giữ đúng ngữ nghĩa. Đệ quy quá sâu có thể gây `StackOverflowError`; thiếu tài nguyên cấp/mở rộng stack có thể gây `OutOfMemoryError`. Cả hai không tự chứng minh Java heap đã đầy.

## 4. Frame: locals, operand stack và tham chiếu tới pool

Theo **JVMS §2.6**, một frame có **local variables array**, **operand stack** và tham chiếu tới **run-time constant pool** phục vụ dynamic linking. Mỗi invocation giữ locals của chính nó; một local chứa reference có thể trỏ tới object trên **shared heap**.

| Method | Local slot 0 | Các slots tiếp theo |
| --- | --- | --- |
| `static int add(int a,int b)` | `a` | `b`, rồi có thể local result |
| `int add(int a,int b)` | `this` | `a`, `b` |
| `static long sample(long x)` | phần đầu `x` | `x` chiếm tổng cộng hai slots |

`iload` nạp giá trị local lên operand stack; `iadd` lấy hai `int` trên đỉnh rồi đẩy kết quả; `ireturn` trả về caller. `long`/`double` chiếm hai local-variable slots hoặc hai units depth của operand stack. `max_locals` và `max_stack` trong `Code` attribute là thông số của **một method**, không phải giới hạn số frames trên stack. `LocalVariableTable` là metadata debug tùy chọn; `StackMapTable` hỗ trợ bytecode verification chứ không phải snapshot stack đang chạy.

Bài chuyên sâu về pc/JVM stack ngay sau đây sẽ đi vào **call/return, exception unwinding, recursion và StackWalker**; mục tiêu ở bài tổng quan này là nhận diện **ranh giới giữa bộ nhớ per-thread và bộ nhớ shared**.

## 5. Native method stacks: thường riêng thread, không nhất thiết có trên mọi JVM

**JVMS §2.5.6** cho phép implementation dùng conventional native stacks để hỗ trợ native methods (thường viết bằng C/C++) hoặc một số phần của VM/interpreter. Nếu có, chúng **thường được cấp phát theo thread**.

Nhưng đặc tả **không bắt buộc mọi JVM phải có native method stacks**. JVM implementation không hỗ trợ native methods và không dựa vào conventional native stacks có thể không cung cấp chúng.

Khi có native stacks:

- Nếu computation cần native stack lớn hơn mức cho phép, VM có thể ném **`StackOverflowError`** theo quy tắc.
- Nếu không cấp hoặc mở rộng được native stack theo các điều kiện đã mô tả, có thể ném **`OutOfMemoryError`**.
- Cách ánh xạ Java frames và native frames sang native memory là chi tiết implementation.

Đoạn minh họa cú pháp Java:

~~~java
public class NativeDeclaration {
    public native int transform(int input);
}
~~~

Đây **không phải chương trình có thể gọi thành công** nếu chưa có native implementation và library tương ứng. Không lấy lỗi `UnsatisfiedLinkError` do chưa triển khai native code làm bằng chứng stack JVM bị thiếu.

## 6. Heap: object/array dùng chung nhưng reference có thể riêng

Theo **JVMS §2.5.3**, JVM tạo heap khi startup. Heap **dùng chung cho mọi JVM threads** và cấp phát **class instances cùng arrays**. Garbage collector tự động quản lý việc thu hồi storage khi phù hợp; Java source không có thao tác `free(object)` như C.

~~~text
Thread A frame                         Thread B frame
 local[1] = ref ------+       +------ local[0] = ref
                      v       v
                  HEAP OBJECT
                +----------------+
                | Counter        |
                | count=2        |
                +----------------+
~~~

Hai reference locals **nằm ở hai frames riêng** nhưng có thể cùng trỏ đến một Counter object. Nếu Counter có field mutable, cả hai threads có thể truy cập field ấy.

Xét:

~~~java
Counter c = new Counter();
int number = 7;
~~~

Nếu đoạn này nằm trong một method:

- Local `number` có một **primitive value** của invocation đó.
- Local `c` giữ một **reference value**, không chứa nguyên object.
- `new Counter()` tạo **Counter object trên heap** theo mô hình JVM.
- Khi frame kết thúc, việc mất local reference **không có nghĩa object lập tức bị GC thu hồi**; còn các references/roots khác hoặc runtime liveness.

**Không được suy** “bất cứ object nào tạo trong method đều nằm trên JVM stack” hoặc “object không còn dùng sẽ bị thu hồi ngay đúng lúc method return”.

### Heap chung không có nghĩa thread-safe

Ví dụ (đoạn minh họa trong class):

~~~java
class UnsafeCounter {
    int count;
    void increment() {
        count++; // read + add + write: không phải atomic increment
    }
}
~~~

Nếu nhiều threads gọi `increment` trên **cùng object** mà không có synchronization phù hợp, có thể có lost updates. Shared heap chỉ cho phép chia sẻ; quy tắc visibility/ordering/happens-before thuộc **Java Memory Model, JLS §17**, không tự sinh ra vì object nằm trên heap.

## 7. Method area: dữ liệu class dùng chung

Theo **JVMS §2.5.4**, method area:

- Là vùng **chia sẻ giữa mọi JVM threads**, được tạo khi VM startup.
- Chứa **per-class structures**: run-time constant pool, field/method data và code cho methods/constructors, kể cả special initialization methods.
- Có thể fixed size hoặc mở rộng/thu hẹp; không bắt buộc là một vùng memory liên tục.
- Có thể phát sinh **`OutOfMemoryError`** nếu không đủ memory cấp cho nhu cầu method area.

JVMS nói method area là **một phần của heap về mặt logic**, nhưng **không ấn định vị trí vật lý** hay chính sách quản lý compiled code. Đây không phải lời hứa rằng toàn bộ method-area structures luôn bị ràng buộc bởi giới hạn `-Xmx` của HotSpot.

### Method area khác Metaspace và PermGen

| Tên gọi | Tầng khái niệm |
| --- | --- |
| **Method area** | Vùng trừu tượng được JVMS quy định |
| **Metaspace** | Cách HotSpot hiện đại quản lý class metadata, thường sử dụng native memory |
| **PermGen** | Cơ chế lịch sử của HotSpot cũ, không phải thành phần bắt buộc của JVMS |
| **Java heap trong HotSpot** | Vùng quản lý các Java objects, thường cấu hình `-Xms`/`-Xmx` |

Không kết luận “JVMS định nghĩa Metaspace” hoặc “mọi JVM đều có PermGen”. Cũng không coi vị trí physical của mọi `static` field, `Class` object hay string literal là điều đã được JVMS `2.5` đóng đinh.

### Static fields chia sẻ theo runtime class identity

Một `static` field thuộc về **runtime class**, không thuộc một frame hay từng thread. Các threads đang dùng **cùng một runtime class identity** chia sẻ static state.

~~~java
class Registry {
    static int total;
}
~~~

Tuy nhiên:

- `Registry.total++` **không tự đồng bộ** trong multi-threaded code.
- Nếu hai defining class loaders khác nhau cùng định nghĩa class tên `Registry`, chúng tạo **hai runtime class identities** và mỗi class có static state riêng.
- “Method area shared” không có nghĩa static fields của mọi class trùng tên ở mọi plugin được hợp nhất.

## 8. Run-time constant pool: per-class, không phải per-thread

**JVMS §2.5.5** mô tả run-time constant pool là representation runtime của `constant_pool` trong file class. JVM tạo một pool **cho mỗi class/interface** trong method area khi loại đó được tạo. Pool chứa constants và symbolic references (classes, fields, methods, method handles…).

Ví dụ `javap -c -v` có thể hiển thị:

~~~text
  #N = Methodref ... // Example.add:(II)I
 ...
  invokestatic #N     // gọi Example.add(int,int)
~~~

`#N` là **constant-pool index**, không phải stack slot, BCI hay địa chỉ heap. Dynamic linking dùng symbolic reference này để resolution thành phần runtime phù hợp.

Các frames của những lời gọi `Example.calculate` ở hai threads có **local arrays/operand stacks khác nhau**, nhưng cùng giữ **reference tới run-time constant pool của runtime class Example**. Không cần sao chép toàn bộ constant pool cho mỗi invocation.

**Phạm vi chính xác:**
- JVM-wide: method area dùng chung.
- Per runtime class/interface: từng run-time constant pool.
- Per invocation/thread: frame reference tới pool, locals và operand stack.

## 9. Ví dụ Java 17+: hai threads có locals riêng và object chung

Tạo file **`MemoryScopeDemo.java`**:

~~~java
public class MemoryScopeDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter shared = new Counter();
        Counter alias = shared;
        int[] results = new int[2];

        Thread first = new Thread(() -> {
            int local = 10;
            results[0] = local + 1;
            shared.increment();
        }, "first");

        Thread second = new Thread(() -> {
            int local = 20;
            results[1] = local + 1;
            shared.increment();
        }, "second");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("first-local=" + results[0]);
        System.out.println("second-local=" + results[1]);
        System.out.println("shared-count=" + shared.get());
        System.out.println("same-reference=" + (shared == alias));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -g MemoryScopeDemo.java
java MemoryScopeDemo
~~~

**Stdout chính xác khi chạy bình thường, không bị interruption hoặc lỗi tài nguyên:**

~~~text
first-local=11
second-local=21
shared-count=2
same-reference=true
~~~

### Tại sao kết quả này có ý nghĩa?

1. Mỗi lambda body là một lần thực thi trên thread riêng; `int local` thuộc invocation tương ứng. Hai local values 10 và 20 **không phải một slot được chia sẻ**.
2. `results` trỏ tới **một int array object trên heap**. Worker thứ nhất ghi index 0; worker thứ hai ghi index 1.
3. `shared` và `alias` cùng trỏ tới **một Counter object**, bởi vậy `shared == alias` là true.
4. `increment` là `synchronized` để hai cập nhật vào `value` không bị lost update; sau hai calls `shared.get()` trả 2.
5. `join` đợi hai threads kết thúc và theo Java Memory Model giúp main nhìn thấy writes mà hai workers thực hiện. Chỉ **main in kết quả sau join**, nên **thứ tự các dòng output là xác định** dù lịch chạy threads khác nhau.

**Điều không được suy:** `local` bắt buộc được lưu ở một địa chỉ native stack riêng cố định. Compiler/JIT có thể giữ value trong register hoặc loại bỏ storage vật lý khi tối ưu; JVM vẫn phải bảo đảm semantics của mỗi invocation.

### Quan sát với `javap`

~~~bash
javap -c -v -p MemoryScopeDemo
javap -c -v -p 'MemoryScopeDemo$Counter'
~~~

Trong class `Counter`, method `increment` mang `ACC_SYNCHRONIZED`; trong class ngoài, lambdas có thể được triển khai bằng `invokedynamic`/synthetic methods. `javap` cho thấy **bytecode và class metadata** chứ không dump native memory của từng Java thread.

## 10. Đệ quy: nhiều frames cho cùng một method

Nếu `sumDown(3)` gọi `sumDown(2)` rồi `sumDown(1)`, mỗi invocation có **frame và tham số `n` riêng**, dù cùng chạy bytecode của một method. Một loop trong cùng invocation không tạo thêm frame chỉ vì lặp. Không cần cố ý gây đệ quy vô hạn để quan sát `StackOverflowError`; bài tiếp theo trình bày code và trace chi tiết cho recursion.

## 11. `ThreadLocal` không phải local variable trong frame

`java.lang.ThreadLocal<T>` là **API** cho phép mỗi thread lưu một value riêng gắn với cùng ThreadLocal key, có thể tồn tại qua **nhiều method invocations** trên thread ấy.

| Khái niệm | Phạm vi |
| --- | --- |
| Method local | Một invocation/frame |
| `ThreadLocal` value | Một thread đối với key tương ứng, có thể qua nhiều calls |
| Instance field | Một object, có thể nhiều threads cùng truy cập |
| Static field | Một runtime class, có thể nhiều threads truy cập |
| Constant pool | Một runtime class/interface, dùng chung khi frames tham chiếu |

Ví dụ **`ThreadLocalSample.java`**:

~~~java
public class ThreadLocalSample {
    static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) {
        CONTEXT.set("request-1");
        System.out.println(CONTEXT.get());
        CONTEXT.remove();
    }
}
~~~

~~~bash
javac ThreadLocalSample.java
java ThreadLocalSample
~~~

**Stdout:**

~~~text
request-1
~~~

`ThreadLocal` **không được đồng nhất với địa chỉ local variable trên JVM stack**. Đặc biệt trong thread pools, `remove()` giúp không giữ lại context ngoài vòng đời mong muốn. Nếu dùng virtual threads hoặc các APIs khác, hãy kiểm tra hướng dẫn riêng của bản Java đang chạy.

## 12. Shared memory phải đi cùng Java Memory Model

Shared heap chỉ nói **những object có thể được nhiều threads truy cập**, không nói mọi thao tác trên object đều tự động atomic hoặc luôn visible ngay.

Các nguyên tắc cần nhớ:

- `synchronized` cung cấp mutual exclusion và memory-visibility ordering theo monitor.
- `volatile` có các guarantees về visibility/order của reads/writes, nhưng không biến `count++` thành atomic increment.
- `AtomicInteger.incrementAndGet()` là lựa chọn đơn giản cho atomic counting.
- `Thread.start()` và `Thread.join()` có các happens-before rules liên quan việc truyền dữ liệu giữa threads.
- Objects immutable hoặc dữ liệu confined có thể giảm chia sẻ mutable state và nguy cơ race.

Nguồn chuẩn: **JLS §17.4 Memory Model**. Đừng thay toàn bộ Java Memory Model bằng hình vẽ “stack riêng / heap chung”: hình đó mô tả **tổ chức lưu trữ trừu tượng**, không đầy đủ các quy tắc visibility/synchronization.

## 13. Vì sao OutOfMemoryError không phải lúc nào cũng là heap đầy?

| Vấn đề | Triệu chứng có thể gặp | Giải thích |
| --- | --- | --- |
| Call depth vượt JVM stack limit | `StackOverflowError` | Đệ quy sâu, chuỗi gọi không dừng |
| Không thể cấp/mở rộng JVM stack | `OutOfMemoryError` | Native/runtime memory cho stack không đủ theo điều kiện |
| Heap không đủ allocation cho object | `OutOfMemoryError` | Garbage collector và heap không cấp đủ storage |
| Method area không đủ memory | `OutOfMemoryError` | Metadata/code/constant-pool allocations thiếu |
| Native method stack vượt giới hạn | `StackOverflowError` | Nếu implementation sử dụng native method stack |
| Không tạo/mở rộng native stacks được | `OutOfMemoryError` | Native resource exhaustion |
| Quá nhiều platform threads/native resources | Có thể `OutOfMemoryError` hoặc lỗi tạo thread | Phụ thuộc OS, giới hạn và JVM |

Trên HotSpot, messages như `Java heap space`, `Metaspace`, `unable to create native thread` là gợi ý nguyên nhân, nhưng không phải JVMS bắt buộc mọi triển khai phải trả đúng wording đó.

**Không thực hiện thí nghiệm cố ý dùng vô hạn memory/threads** trên máy làm việc hoặc production; quan sát thống kê và tái hiện có giới hạn trong môi trường test sẽ an toàn hơn.

## 14. Cách theo dõi vùng nhớ trên HotSpot

Một số công cụ/flags phổ biến:

~~~bash
java -version
java -XshowSettings:vm -version
java -Xlog:help
~~~

| Cấu hình/công cụ | Có thể xem hoặc tác động | Không được kết luận |
| --- | --- | --- |
| `-Xmx512m` | Giới hạn Java object heap trên HotSpot | Toàn bộ memory của process bị giới hạn đúng 512 MB |
| `-Xss1m` | Kích thước stack thread theo runtime/platform phù hợp | Mỗi frame Java chiếm đúng 1 MB |
| `-XX:MaxMetaspaceSize=...` | Quản lý giới hạn Metaspace trên HotSpot | Metaspace là vùng bắt buộc của mọi JVM |
| `jcmd <pid> GC.heap_info` | Thông tin heap/collector | Run-time constant pool chi tiết của từng class |
| `jcmd <pid> Thread.print` | Call stacks và threads | Nội dung mọi operand stack theo slot |
| `jcmd <pid> VM.native_memory summary` | Native Memory Tracking nếu bật | Mọi memory category đều là vùng trong JVMS `2.5` |

Native Memory Tracking (NMT) của HotSpot có thể được bật khi khởi chạy với:

~~~bash
java -XX:NativeMemoryTracking=summary MemoryScopeDemo
~~~

**Ví dụ `MemoryScopeDemo` kết thúc quá nhanh để attach** là điều bình thường. Trong server chạy lâu, xác định PID bằng `jcmd -l`, rồi dùng `jcmd <pid> VM.native_memory summary` khi có quyền và JVM bật tracking. Không mặc định lệnh NMT hoạt động trên mọi JVM.

**RSS/Process memory ≠ Java heap limit**: process còn metadata, native stacks, code cache, JVM internals… `-Xmx` không phải “giới hạn RAM tuyệt đối của process”.

## 15. Các ngộ nhận dễ gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Chỉ có một JVM stack cho cả process.” | Mỗi JVM thread có **stack riêng**. |
| “Operand stack và JVM stack là một.” | Operand stack thuộc **frame**; JVM stack chứa **frames**. |
| “Một local reference nghĩa object được tạo nằm trong stack.” | Local chứa **reference**, object cấp phát trên **heap** theo mô hình. |
| “Mất local reference thì GC thu object ngay.” | Object có thể còn reachable; GC không bị ràng buộc đúng thời điểm method return. |
| “`ThreadLocal` là frame local variable.” | ThreadLocal là **API per-thread value**, khác local array per-invocation. |
| “Hai threads cùng thấy object thì locals của chúng cũng dùng chung.” | Locals riêng, có thể chứa references tới cùng object. |
| “Static field có một bản cho tất cả classloaders.” | Static state thuộc runtime class identity; class cùng tên do defining loaders khác nhau vẫn riêng. |
| “Method area = Metaspace trong mọi JVM.” | Method area thuộc JVMS; Metaspace thuộc HotSpot. |
| “Method area luôn vật lý nằm trong `-Xmx` heap.” | Đặc tả chỉ nói *logically part of heap*, không ấn định implementation layout. |
| “Runtime constant pool là per-thread.” | **Per-class/interface**, nằm trong method area dùng chung. |
| “Native method stack chắc chắn có trên mọi JVM.” | Tùy implementation, không luôn bắt buộc. |
| “`pc` của native method luôn trỏ Java opcode.” | Theo JVMS, pc của JVM **undefined** khi current method native. |
| “Shared heap tự bảo đảm thread-safe.” | Cần Java Memory Model và synchronization phù hợp. |
| “`max_stack` là số method calls tối đa.” | Độ sâu operand stack của **một method**, không phải số frames. |
| “Mọi OutOfMemoryError là Java heap hết chỗ.” | Còn có metadata, stack/native resources và nguyên nhân khác. |

## 16. Tự kiểm tra

**1.** Những vùng nào per-thread theo JVMS?  
**Đáp án:** `pc`, JVM stack; native method stacks thường per-thread **nếu implementation cung cấp**.

**2.** Những vùng nào JVM-wide?  
**Đáp án:** Heap và method area. Run-time constant pool là **per-runtime-class/interface** nhưng được cấp trong method area.

**3.** Hai threads cùng chạy `add(3,4)` có một operand stack chung không?  
**Đáp án:** Không. Mỗi invocation tạo frame riêng với operand stack riêng.

**4.** Một local `Person p` chứa cả Person object trên JVM stack?  
**Đáp án:** Không. Nó chứa reference value; Person object được cấp phát trên heap theo mô hình.

**5.** Vì sao `static int count` không mặc định an toàn khi hai threads dùng `count++`?  
**Đáp án:** `count++` là read–modify–write có thể tranh chấp; static field shared không có nghĩa atomic.

**6.** `ThreadLocal<String>` có tương đương một local biến Java không?  
**Đáp án:** Không. ThreadLocal value gắn với thread qua nhiều calls; method local gắn với frame/invocation.

**7.** Run-time constant pool có được tạo mới mỗi khi call method?  
**Đáp án:** Không. Pool thuộc class/interface; frame của lần gọi chỉ giữ reference tới pool.

**8.** Method area có luôn được triển khai bằng HotSpot Metaspace?  
**Đáp án:** Không. Đặc tả không bắt buộc một cách triển khai hoặc physical layout.

**9.** Một frame return khiến object được cấp phát trong method tự hủy ngay?  
**Đáp án:** Không. Object có thể còn reachable từ nơi khác và GC không nhất thiết xảy ra ngay.

**10.** Tại sao `MemoryScopeDemo` luôn in shared-count=2 trong execution bình thường?  
**Đáp án:** `increment()` đồng bộ để không mất update; `join()` bảo đảm main đợi hai worker xong mới đọc.

**11.** Lệnh `-Xmx` có giới hạn tuyệt đối RAM của JVM process?  
**Đáp án:** Không. Còn native memory, metadata, stack và các nguồn khác.

**12.** Khi chạy native method, JVMS định nghĩa pc là địa chỉ nào?  
**Đáp án:** Giá trị pc của JVM **không xác định** trong native method.

## 17. Nguồn chuẩn

- [JVMS Java SE 25 — §2.5 Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5): cấu trúc memory JVM.
- [JVMS §2.5.1 pc Register](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.1).
- [JVMS §2.5.2 JVM Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.2).
- [JVMS §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3).
- [JVMS §2.5.4 Method Area](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.4).
- [JVMS §2.5.5 Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.5).
- [JVMS §2.5.6 Native Method Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.6).
- [JVMS §2.6 Frames](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6).
- [JVMS §4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): `max_stack`/`max_locals`.
- [JLS Java SE 25 — Chapter 17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): memory model và happens-before.
- [JDK 25 — javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): quan sát bytecode.
- [JDK 25 — jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): quan sát runtime trên JVM phù hợp.

**Ghi nhớ cuối:** `pc`/JVM stack/native stacks (nếu có) theo thread; heap/method area chung toàn JVM; runtime constant pools gắn với từng runtime class; locals/operand stack gắn với từng frame. **Per-thread không đồng nghĩa đối tượng không thể được chia sẻ**, và **shared heap không tự tạo thread-safety**. Khi học JVM, luôn tách **mô hình đặc tả**, **Java Memory Model** và **chi tiết physical memory của implementation**.