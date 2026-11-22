# Heap, stack, metaspace và bộ nhớ ngoài heap trong Java 17

> **Chủ đề:** Java 17  
> **Chương:** JVM và bộ nhớ  
> **Phạm vi:** Các vùng dữ liệu runtime theo JVM Specification và cách HotSpot quản lý heap, stack, metaspace cùng những vùng native memory thường gặp trong Java 17.

## 1. JVM sử dụng nhiều vùng bộ nhớ

Một tiến trình Java không chỉ có một vùng nhớ duy nhất. Khi JVM chạy, nó quản lý nhiều loại dữ liệu với vòng đời và mục đích khác nhau:

- **Heap:** nơi lưu trữ object và array; được chia sẻ giữa các thread và được garbage collector quản lý.
- **Java stack:** mỗi thread có stack riêng để lưu các frame của lời gọi phương thức, biến cục bộ và operand stack.
- **Metaspace:** vùng native memory mà HotSpot dùng để lưu metadata của class và thông tin liên quan đến class loader.
- **Bộ nhớ ngoài heap (off-heap/native memory):** cách gọi chung các vùng bộ nhớ nằm ngoài Java heap, ví dụ direct buffer, memory-mapped file, thread stack, code cache, cấu trúc nội bộ của JVM và bộ nhớ do thư viện native cấp phát.

Sơ đồ khái quát:

```text
Tiến trình Java
|
+-- Java heap (chia sẻ giữa các thread)
|     +-- Objects
|     +-- Arrays
|     +-- TLAB của từng thread (vẫn nằm trong heap)
|
+-- Metaspace (native memory)
|     +-- Class metadata
|     +-- Class-loader-related metadata
|
+-- Các thread
|     +-- Java stack của thread A
|     +-- Java stack của thread B
|     +-- Native stack / vùng native liên quan
|
+-- Code cache (native memory)
|
+-- Direct buffers / mapped regions
|
+-- JVM, GC, JIT và thư viện native khác
```

Sơ đồ chỉ thể hiện các nhóm khái niệm. Cách bố trí vật lý cụ thể phụ thuộc JVM implementation, hệ điều hành, kiến trúc và cấu hình runtime.

## 2. Phân biệt mô hình JVM Specification và cách HotSpot triển khai

JVM Specification mô tả các **runtime data areas** mà một JVM cần cung cấp về mặt ngữ nghĩa. Nó không bắt buộc mọi implementation phải dùng đúng một cách bố trí bộ nhớ vật lý.

Các vùng dữ liệu runtime được mô tả gồm:

| Runtime data area | Phạm vi | Vai trò |
|---|---|---|
| PC register | Riêng mỗi thread | Theo dõi vị trí lệnh bytecode đang được thực thi |
| Java Virtual Machine stack | Riêng mỗi thread | Chứa frame của các lời gọi phương thức |
| Heap | Chia sẻ | Cấp phát object và array |
| Method area | Chia sẻ | Lưu cấu trúc theo class như metadata, runtime constant pool và mã phương thức theo mô hình đặc tả |
| Runtime constant pool | Theo class/interface, thuộc method area theo đặc tả | Chứa hằng số và tham chiếu symbolic được dùng khi liên kết |
| Native method stack | Liên quan từng thread | Hỗ trợ thực thi native method; cách triển khai phụ thuộc JVM |

Trong HotSpot Java 17:

- Heap là vùng managed memory được garbage collector quản lý.
- Class metadata được lưu trong **Metaspace**, nằm ngoài heap.
- Mã máy do JIT biên dịch được lưu trong **Code Cache**, nằm ngoài heap.
- Direct buffer có thể dùng native memory.
- Mỗi thread nền tảng có vùng stack riêng.

Không nên đồng nhất tên trong JVM Specification với một vùng cấp phát vật lý cụ thể của HotSpot. Ví dụ, **method area** là khái niệm trừu tượng của đặc tả; **Metaspace** là cách HotSpot triển khai phần lớn class metadata.

## 3. Heap: vùng lưu trữ object và array

### 3.1. Heap là gì?

Heap là vùng bộ nhớ được chia sẻ giữa các thread trong một tiến trình JVM. Khi chương trình tạo object hoặc array, bộ nhớ cho object thường được cấp phát trên heap:

```java
public class HeapDemo {
    public static void main(String[] args) {
        User user = new User("An");
        int[] scores = new int[1_000];
    }
}

class User {
    private final String name;

    User(String name) {
        this.name = name;
    }
}
```

Trong ví dụ:

- Biến cục bộ `user` giữ một tham chiếu đến object `User`.
- Object `User` thường được cấp phát trên heap.
- Biến cục bộ `scores` giữ tham chiếu đến array.
- Array `int[]` được cấp phát trên heap.

Biến tham chiếu có thể nằm trong stack frame, trong field của một object khác hoặc trong vùng dữ liệu khác. **Tham chiếu và object được tham chiếu là hai thứ khác nhau.**

Đây là mô hình hữu ích để hiểu chương trình. JVM có thể tối ưu bằng escape analysis, scalar replacement hoặc loại bỏ allocation nếu không làm thay đổi hành vi quan sát được. Vì vậy, không nên giả định mọi biểu thức `new` nhất thiết dẫn đến một lần cấp phát vật lý trên heap trong mọi trường hợp.

### 3.2. Heap được chia sẻ giữa các thread

Các thread trong cùng JVM có thể giữ tham chiếu đến cùng một object:

```java
class Counter {
    int value;
}

Counter shared = new Counter();

Thread first = new Thread(() -> shared.value++);
Thread second = new Thread(() -> shared.value++);

first.start();
second.start();
```

Hai thread truy cập cùng object `shared`. Heap được chia sẻ, nên việc truy cập đồng thời cần tuân thủ Java Memory Model. Nếu nhiều thread cùng ghi một field mà không có đồng bộ phù hợp, chương trình có thể gặp race condition.

Các cơ chế như `synchronized`, `volatile`, lock hoặc các cấu trúc đồng bộ trong `java.util.concurrent` dùng để kiểm soát truy cập và khả năng nhìn thấy dữ liệu. Việc object nằm trên heap không tự đảm bảo thread-safe.

### 3.3. Garbage collector quản lý heap

Java có garbage collector (GC) để thu hồi vùng heap của object không còn reachable từ các GC roots. Những root thường gặp gồm:

- Tham chiếu từ stack của thread đang chạy.
- Tham chiếu từ static field đang được giữ bởi class sống.
- Tham chiếu JNI và một số root nội bộ của JVM.

Khi object không còn đường tham chiếu từ các root, nó có thể trở thành đối tượng đủ điều kiện thu gom. Thời điểm thu gom do JVM/GC quyết định; chương trình không thể yêu cầu chính xác object nào được giải phóng vào thời điểm nào.

Ví dụ:

```java
User user = new User("An");
user = null;
```

Sau phép gán `null`, biến `user` không còn tham chiếu đến object cũ. Nếu không còn tham chiếu nào khác, object có thể trở thành unreachable. Điều đó **không có nghĩa GC chạy ngay lập tức**.

### 3.4. Vòng đời object và memory leak trong Java

Java tự động thu gom object không còn reachable, nhưng ứng dụng vẫn có thể bị memory leak khi giữ tham chiếu đến object không còn cần thiết:

```java
static final List<byte[]> CACHE = new ArrayList<>();

static void addPayload() {
    CACHE.add(new byte[1024 * 1024]);
}
```

Mỗi lần gọi `addPayload()`, danh sách static giữ thêm một mảng 1 MiB. Các mảng vẫn reachable qua `CACHE`, nên GC không thể thu hồi chúng dù nghiệp vụ không còn dùng.

Những nguyên nhân thường gặp:

- Collection/cache không có giới hạn hoặc chính sách eviction.
- Listener/callback được đăng ký nhưng không hủy.
- Thread-local giữ object lớn quá lâu.
- Static field giữ object theo vòng đời toàn ứng dụng.
- Class loader không được giải phóng do còn tham chiếu từ nơi khác.

Memory leak trên heap là vấn đề về **vòng đời tham chiếu**, không nhất thiết là lỗi của garbage collector.

### 3.5. Điều chỉnh heap trong Java 17

Các tùy chọn JVM phổ biến:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-Xms<size>` | Kích thước heap ban đầu |
| `-Xmx<size>` | Kích thước heap tối đa |
| `-XX:MaxRAMPercentage=<n>` | Tỷ lệ RAM tối đa mà JVM dùng để suy ra giới hạn heap khi không đặt `-Xmx` trực tiếp |

Ví dụ:

```bash
java -Xms512m -Xmx2g -jar app.jar
```

Ví dụ này đặt heap ban đầu là 512 MiB và giới hạn tối đa là 2 GiB. Nó không có nghĩa toàn bộ tiến trình Java chỉ dùng tối đa 2 GiB; Metaspace, thread stack, direct buffer, code cache và các vùng native khác vẫn cần bộ nhớ riêng.

Khi chọn heap, cần xem số lượng và kích thước object sống đồng thời, tốc độ allocation, tỷ lệ object sống sót qua các chu kỳ GC, độ trễ GC chấp nhận được và giới hạn RAM thực tế của máy hoặc container.

Tăng `-Xmx` có thể giúp ứng dụng chứa nhiều object sống hơn, nhưng không tự sửa memory leak và có thể làm tiến trình vượt giới hạn RAM của container.

## 4. Stack: vùng dữ liệu riêng của từng thread

### 4.1. Java stack chứa những gì?

Mỗi thread có một Java Virtual Machine stack riêng. Stack chứa các **frame** tương ứng với những lời gọi phương thức đang hoạt động.

Một frame có các thành phần chính:

- Local variable array: tham số và biến cục bộ của phương thức.
- Operand stack: vùng trung gian để bytecode thực hiện phép toán và gọi phương thức.
- Thông tin hỗ trợ liên kết động và kết thúc lời gọi.

Ví dụ:

```java
static int calculate(int base) {
    int factor = 3;
    int result = base * factor;
    return result;
}

public static void main(String[] args) {
    int answer = calculate(10);
    System.out.println(answer);
}
```

Khi `main` gọi `calculate`, JVM tạo frame cho lời gọi `calculate`. Khi phương thức kết thúc, frame của nó được loại khỏi stack và quyền điều khiển trở về caller.

Sơ đồ khái niệm:

```text
Thread A - Java stack

Đỉnh stack
  +---------------------------+
  | Frame calculate()         |
  | local: base, factor,      |
  |        result             |
  | operand stack             |
  +---------------------------+
  | Frame main()              |
  | local: args, answer       |
  | operand stack             |
  +---------------------------+
Đáy stack
```

Frame chỉ tồn tại trong thời gian lời gọi phương thức tương ứng còn hoạt động. Đây là lý do stack thường phù hợp với dữ liệu có vòng đời gắn với call chain.

### 4.2. Biến cục bộ không đồng nghĩa object nằm trên stack

Ví dụ:

```java
void process() {
    int count = 10;
    User user = new User("An");
}
```

`count` là giá trị primitive cục bộ và `user` là biến tham chiếu cục bộ. Chúng thuộc vùng local variables của frame theo mô hình JVM. Object `User` thường ở heap.

Không nên kết luận rằng mọi biến cục bộ đều là “stack memory” theo nghĩa mọi giá trị luôn được lưu ở một vị trí vật lý trên stack. JIT có thể giữ giá trị trong register hoặc tối ưu frame; đặc tả quy định hành vi chứ không ép mọi chi tiết bố trí vật lý.

### 4.3. Stack overflow

Mỗi thread có giới hạn stack. Khi call chain quá sâu hoặc đệ quy không có điểm dừng, stack có thể cạn:

```java
public class StackOverflowDemo {
    static void recurse() {
        recurse();
    }

    public static void main(String[] args) {
        recurse();
    }
}
```

Chương trình có thể ném `StackOverflowError`. Lỗi này thường xuất hiện do đệ quy vô hạn/quá sâu hoặc chuỗi lời gọi lồng nhau quá lớn.

Cách xử lý đúng là sửa thuật toán, thêm điều kiện dừng, chuyển sang vòng lặp khi phù hợp hoặc giảm độ sâu lời gọi. Tăng stack chỉ giúp trong trường hợp nhu cầu stack hợp lệ nhưng lớn hơn mặc định; nó không sửa đệ quy vô hạn.

### 4.4. Điều chỉnh kích thước stack

Tùy chọn thường dùng:

```bash
java -Xss1m -jar app.jar
```

`-Xss` đặt kích thước stack cho mỗi thread nền tảng (platform thread), theo cách triển khai JVM và hệ điều hành. Giá trị mặc định phụ thuộc môi trường và không nên giả định giống nhau trên mọi máy.

Tổng bộ nhớ stack có thể trở nên đáng kể khi ứng dụng tạo nhiều thread. Ví dụ minh họa: nếu có 300 thread và mỗi stack được cấu hình 1 MiB, tổng không gian stack được dành/reserve có thể lên tới hàng trăm MiB, chưa tính các vùng native khác. Đây là phép ước lượng để lập ngân sách; RSS thực tế phụ thuộc mức stack thực sự được chạm và cách hệ điều hành cấp phát.

### 4.5. Stack và heap khác nhau

| Tiêu chí | Stack | Heap |
|---|---|---|
| Phạm vi | Riêng cho từng thread | Chia sẻ trong JVM |
| Nội dung điển hình | Frame, local variables, operand stack | Object và array |
| Vòng đời | Gắn với lời gọi phương thức/thread | Gắn với khả năng reachable và GC |
| Quản lý | Frame được push/pop khi gọi/trả phương thức | Garbage collector quản lý object |
| Lỗi thường gặp | `StackOverflowError` | `OutOfMemoryError: Java heap space` |
| Điều chỉnh HotSpot | `-Xss` | `-Xms`, `-Xmx` |

## 5. Metaspace: class metadata trong HotSpot

### 5.1. Metaspace là gì?

Metaspace là vùng native memory mà HotSpot sử dụng để lưu metadata của class được nạp. Metadata có thể bao gồm thông tin về:

- Cấu trúc class/interface và quan hệ kế thừa.
- Method, field và các thuộc tính liên quan.
- Runtime constant pool và dữ liệu hỗ trợ liên kết class theo cách HotSpot triển khai.
- Thông tin phục vụ reflection, verifier và runtime.

Metaspace **không phải nơi lưu các instance thông thường** của class. Ví dụ, object `User` được tạo bằng `new User(...)` thường nằm trên heap; metadata mô tả class `User` nằm trong vùng metadata do HotSpot quản lý.

### 5.2. Metaspace nằm ngoài Java heap

Trong HotSpot Java 17, Metaspace sử dụng native memory. Do đó:

- Tăng `-Xmx` không trực tiếp tăng giới hạn Metaspace.
- Heap có thể còn dung lượng nhưng JVM vẫn có thể hết Metaspace.
- Tiến trình có thể dùng nhiều RAM hơn `-Xmx` do Metaspace và các vùng native khác.

Từ Java 8, HotSpot sử dụng Metaspace thay cho vùng PermGen của các bản Java cũ. Khi cấu hình Java 17, hãy làm việc với Metaspace; các tùy chọn PermGen không còn là cách quản lý bộ nhớ phù hợp.

### 5.3. Class loader ảnh hưởng đến vòng đời metadata

Metadata gắn với class được nạp và class loader quản lý nó. Khi class loader đủ điều kiện được thu hồi, các class do loader đó định nghĩa có thể được unload, và metadata tương ứng có thể được thu hồi.

Ví dụ thường gặp là ứng dụng server triển khai lại ứng dụng nhiều lần. Mỗi lần deploy tạo class loader mới. Nếu một thành phần sống lâu (static registry, thread, ThreadLocal, listener, cache hoặc thư viện native) vẫn giữ tham chiếu đến class loader cũ, loader không thể được thu hồi. Metadata của các class cũ tiếp tục chiếm Metaspace.

Đây là một nguyên nhân của **class loader leak** và có thể dẫn tới:

```text
java.lang.OutOfMemoryError: Metaspace
```

Không nên mặc định tăng giới hạn Metaspace là giải pháp cuối cùng. Cần tìm lý do class loader không được unload hoặc vì sao ứng dụng nạp quá nhiều class.

### 5.4. Điều chỉnh Metaspace

Các tùy chọn HotSpot thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-XX:MetaspaceSize=<size>` | Ngưỡng ban đầu liên quan đến việc JVM kích hoạt GC để xử lý class metadata; không phải giới hạn tối đa |
| `-XX:MaxMetaspaceSize=<size>` | Giới hạn tối đa cho Metaspace |
| `-XX:CompressedClassSpaceSize=<size>` | Kích thước vùng address space cho compressed class space khi cơ chế compressed class pointers được dùng |

Ví dụ:

```bash
java -XX:MetaspaceSize=128m -XX:MaxMetaspaceSize=512m -jar app.jar
```

Các giá trị trên chỉ minh họa cú pháp, không phải cấu hình khuyến nghị cho mọi ứng dụng. `MetaspaceSize` là ngưỡng GC có thể được JVM điều chỉnh, không nên diễn giải như “JVM chỉ cấp đúng 128 MiB metadata”. `MaxMetaspaceSize` mới là giới hạn trên.

## 6. Bộ nhớ ngoài heap (off-heap/native memory)

### 6.1. Off-heap là khái niệm rộng

“Off-heap” thường được dùng để chỉ bộ nhớ mà ứng dụng/JVM sử dụng ngoài Java heap. Nó không phải một vùng đơn nhất với một bộ quản lý duy nhất. Các nguồn tiêu thụ có thể gồm:

- Thread stack và native stack.
- Metaspace.
- JIT code cache.
- Direct byte buffers.
- Memory-mapped files.
- Cấu trúc dữ liệu của garbage collector và runtime.
- Thư viện native/JNI.
- Native allocator, TLS, socket buffer và các thành phần hệ điều hành liên quan.

Do đó, khi đo RAM tiến trình, không thể chỉ nhìn heap usage.

### 6.2. Direct ByteBuffer

`ByteBuffer.allocateDirect()` tạo một direct buffer có dữ liệu được lưu trong vùng nhớ phù hợp cho I/O native:

```java
import java.nio.ByteBuffer;

public class DirectBufferDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
        buffer.putInt(42);
        buffer.flip();

        System.out.println(buffer.getInt());
    }
}
```

Object wrapper `ByteBuffer` là object Java trên heap, nhưng vùng dữ liệu của direct buffer được cấp phát ngoài heap. Điều này có thể giảm một số bước copy trong các luồng I/O, tùy API và hệ điều hành.

Direct buffer không miễn phí:

- Vùng native memory vẫn tiêu thụ RAM/address space.
- Cấp phát và thu hồi có chi phí.
- Nếu tạo quá nhiều direct buffer hoặc giữ tham chiếu quá lâu, ứng dụng có thể hết native memory.
- Việc thu hồi bộ nhớ native gắn với vòng đời/cleaner của buffer; không nên dựa vào `System.gc()` để giải phóng đúng thời điểm.

Giới hạn tổng direct buffer có thể cấu hình bằng:

```bash
java -XX:MaxDirectMemorySize=512m -jar app.jar
```

Khi giới hạn bị vượt, ứng dụng có thể gặp:

```text
java.lang.OutOfMemoryError: Direct buffer memory
```

Chọn giới hạn dựa trên tổng số buffer đồng thời, kích thước mỗi buffer, vòng đời và ngân sách native memory của tiến trình.

### 6.3. Memory-mapped files

`FileChannel.map()` tạo vùng nhớ ánh xạ file:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedFileDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.bin");

        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, channel.size());

            mapped.put(0, (byte) 42);
        }
    }
}
```

Vùng ánh xạ gắn với file và hệ điều hành. Các trang dữ liệu có thể được đưa vào RAM theo nhu cầu truy cập; chúng không được tính như object heap thông thường. Một mapping lớn có thể làm tăng virtual address space và áp lực bộ nhớ hệ điều hành, dù không phải toàn bộ mapping luôn resident trong RAM cùng lúc.

Khi dùng mapping:

- Giới hạn kích thước file và vùng ánh xạ.
- Đóng `FileChannel` khi hoàn tất thao tác I/O thông thường.
- Hiểu rằng vòng đời mapping có quy tắc riêng; đóng channel không nhất thiết làm vùng mapping biến mất ngay.
- Theo dõi giới hạn address space, page cache và tài nguyên file của hệ điều hành.

### 6.4. Code Cache

HotSpot JIT biên dịch bytecode thành mã máy để tăng tốc các đoạn code thường chạy. Mã máy được lưu trong **Code Cache**, là vùng native memory.

Code Cache có thể tăng khi ứng dụng chạy và JIT biên dịch thêm phương thức. Nếu code cache quá nhỏ hoặc đầy, JVM có thể hạn chế/không tiếp tục biên dịch một số phương thức, làm hiệu năng giảm. Đây không phải Java heap và GC heap không thu hồi vùng code cache như object thông thường.

Một tùy chọn liên quan:

```bash
java -XX:ReservedCodeCacheSize=256m -jar app.jar
```

Chỉ điều chỉnh khi có dữ liệu chẩn đoán cho thấy Code Cache là nút thắt. Không nên tăng mọi giới hạn native chỉ vì RSS cao.

### 6.5. Thread và native memory

Mỗi thread nền tảng cần tài nguyên hệ điều hành và vùng stack. Tạo quá nhiều thread có thể làm:

- Tăng tổng vùng stack được reserve.
- Tăng cấu trúc quản lý thread của JVM và hệ điều hành.
- Tăng context switching và áp lực scheduler.
- Làm `Thread.start()` thất bại với lỗi tạo native thread.

Ví dụ lỗi có thể thấy:

```text
java.lang.OutOfMemoryError: unable to create native thread
```

Lỗi này không nhất thiết do heap đầy. Hãy kiểm tra số thread, giới hạn tiến trình của OS/container, kích thước stack, native memory và giới hạn tài nguyên của người dùng.

## 7. Heap, Metaspace và off-heap phối hợp như thế nào?

Một ứng dụng có thể có heap còn trống nhưng vẫn không tạo được object hoặc thread mới do một vùng khác cạn. Ngược lại, heap có thể đầy trong khi Metaspace còn dư.

| Khu vực | Nội dung chính | Bộ quản lý/thu hồi | Tùy chọn hoặc công cụ thường dùng |
|---|---|---|---|
| Heap | Object, array | GC | `-Xms`, `-Xmx`, GC logs, heap dump |
| Java stack | Frame của mỗi thread | Push/pop theo lời gọi | `-Xss`, thread dump |
| Metaspace | Class metadata | Class unloading/HotSpot | `-XX:MaxMetaspaceSize`, `jcmd VM.metaspace` |
| Direct memory | Direct ByteBuffer data | Cleaner/lifecycle của buffer và JVM | `-XX:MaxDirectMemorySize`, NMT |
| Code Cache | JIT compiled code | JVM code cache management | `-XX:ReservedCodeCacheSize`, compiler/code cache logs |
| Native libraries | Vùng cấp phát qua JNI/native allocator | Thư viện hoặc code native quản lý | NMT một phần, profiler/OS tools |
| Memory mapping | Trang ánh xạ file | OS và vòng đời mapping | OS memory maps, process tools |

Một cách lập ngân sách bộ nhớ:

```text
Tổng RAM tiến trình
  ≈ Java heap
  + Metaspace
  + thread stacks
  + direct/mapped memory đang resident
  + Code Cache
  + GC/JVM/native structures
  + native libraries
  + các vùng hệ điều hành tính vào tiến trình
```

Đây là mô hình ngân sách, không phải công thức cộng chính xác: vùng reserve, commit, shared pages và resident pages có cách đo khác nhau.

## 8. Vì sao RSS của tiến trình lớn hơn -Xmx?

`-Xmx` chỉ giới hạn dung lượng Java heap tối đa. Nó không đặt giới hạn tổng bộ nhớ cho tiến trình Java.

Ví dụ một ứng dụng có:

- Heap tối đa 2 GiB.
- Metaspace tối đa 300 MiB.
- Direct buffer tối đa 512 MiB.
- 200 thread với stack được cấu hình 1 MiB.
- Code cache và các cấu trúc JVM/native khác.

Tổng ngân sách có thể vượt xa 2 GiB. Vì vậy, container có memory limit 2 GiB không thể an toàn chỉ vì JVM đặt `-Xmx2g`; các vùng native sẽ cần thêm dung lượng.

Khi chạy trong container, hãy dành headroom cho native memory và hệ điều hành. Java 17 trên các nền tảng được hỗ trợ có thể nhận biết giới hạn container để tính ergonomics, nhưng cấu hình `-Xmx` trực tiếp vẫn cần nằm trong ngân sách tổng. Kiểm tra giới hạn container thực tế và số liệu process RSS, không suy luận từ heap usage đơn lẻ.

## 9. Các lỗi bộ nhớ thường gặp

| Thông báo/lỗi | Vùng thường liên quan | Hướng điều tra ban đầu |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap | Heap dump, dominator tree, retained size, allocation rate, cache và reference leak |
| `OutOfMemoryError: GC overhead limit exceeded` | Heap/GC pressure | Kiểm tra live set, allocation, GC logs và khả năng ứng dụng đang tiến gần cạn heap |
| `OutOfMemoryError: Metaspace` | Metaspace | Class count, class loader, redeploy leak, giới hạn Metaspace |
| `OutOfMemoryError: Direct buffer memory` | Direct memory | Số lượng/kích thước direct buffer, vòng đời buffer và giới hạn direct memory |
| `OutOfMemoryError: unable to create native thread` | Native/thread resources | Thread count, `-Xss`, OS/container limits, native memory |
| `StackOverflowError` | Stack của thread | Đệ quy, call chain sâu, callback lặp |
| `OutOfMemoryError: Requested array size exceeds VM limit` | Kích thước array/giới hạn VM | Kích thước đầu vào, phép tính length overflow và thiết kế chunking |

Thông báo lỗi chỉ là dấu hiệu ban đầu. Cần đối chiếu log, heap dump, thread dump và số liệu native memory để xác định nguyên nhân thực.

## 10. Công cụ quan sát bộ nhớ trên Java 17

### 10.1. Xem cấu hình VM

```bash
java -XshowSettings:vm -version
```

Lệnh này in một số thông tin cấu hình VM, hữu ích để xác nhận JVM đang dùng và các giới hạn tổng quát.

### 10.2. Dùng jcmd

`jcmd` là công cụ chẩn đoán đi kèm JDK. Ví dụ, với PID của tiến trình Java:

```bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.metaspace
jcmd <pid> Thread.print
```

Ý nghĩa:

- `GC.heap_info`: thông tin tổng quan heap và GC.
- `VM.metaspace`: thống kê Metaspace.
- `Thread.print`: dump stack trace của các thread.

Tên lệnh và mức chi tiết phụ thuộc JVM build; dùng `jcmd <pid> help` để xem lệnh có sẵn.

### 10.3. Native Memory Tracking

HotSpot có **Native Memory Tracking (NMT)** để theo dõi một số nhóm native memory do JVM quản lý. Cần bật khi JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc chọn `detail` để có thêm thông tin chi tiết, với chi phí theo dõi cao hơn:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Sau khi bật, có thể truy vấn:

```bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory detail
```

NMT hữu ích để so sánh các nhóm như Java Heap, Class/Metaspace, Thread, Code, GC và Internal. NMT không phải bộ đo toàn bộ mọi allocation native của mọi thư viện bên thứ ba; hãy đối chiếu thêm công cụ hệ điều hành hoặc profiler khi RSS không khớp.

### 10.4. Bật GC log trong Java 17

Java 17 dùng Unified Logging:

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

GC log giúp xem:

- Heap trước/sau các lần GC.
- Tần suất và thời gian pause.
- Các pha GC.
- Thay đổi occupancy theo thời gian.

Không dùng một con số heap usage đơn lẻ để kết luận có memory leak. Hãy quan sát xu hướng sau GC và đối chiếu workload.

### 10.5. Tạo heap dump khi OutOfMemoryError

Có thể yêu cầu JVM ghi heap dump khi gặp OOME:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps -jar app.jar
```

Heap dump giúp phân tích object nào đang giữ nhiều bộ nhớ. Nó không chứa đầy đủ mọi loại native memory; nếu lỗi liên quan Metaspace, direct memory hoặc native thread, cần thêm NMT, thread dump và công cụ phù hợp.

Heap dump có thể lớn và chứa dữ liệu nhạy cảm của ứng dụng. Lưu file ở vị trí có dung lượng đủ và quyền truy cập được kiểm soát.

## 11. Ví dụ phân tích một số tình huống

### Tình huống A — Heap tăng liên tục sau mỗi request

Triệu chứng:

- Heap occupancy tăng theo thời gian.
- Sau Full GC, dung lượng object sống vẫn tăng.
- Cuối cùng có thể gặp `Java heap space`.

Hướng điều tra:

1. Lấy heap dump ở các thời điểm phù hợp.
2. So sánh histogram/dominator tree giữa các dump.
3. Tìm collection/cache/static field đang giữ object.
4. Kiểm tra listener, ThreadLocal và reference chain.
5. Đặt giới hạn kích thước cache hoặc hủy đăng ký tài nguyên đúng lúc.

Tăng `-Xmx` có thể trì hoãn lỗi, nhưng nếu live set tiếp tục tăng không giới hạn thì nguyên nhân vẫn còn.

### Tình huống B — Heap ổn định nhưng container bị OOM kill

Triệu chứng:

- Heap usage thấp hơn `-Xmx`.
- RSS của process cao.
- Container vượt memory limit và bị hệ điều hành kết thúc.

Hướng điều tra:

1. Kiểm tra direct buffer và memory mapping.
2. Kiểm tra Metaspace, Code Cache và NMT.
3. Kiểm tra thread count và `-Xss`.
4. Kiểm tra thư viện JNI/native.
5. So sánh RSS với cgroup/container metrics.

Không tăng `-Xmx` trong tình huống này nếu chưa xác định được vùng tiêu thụ native.

### Tình huống C — Redeploy nhiều lần rồi gặp Metaspace OOME

Triệu chứng:

- Mỗi lần redeploy, class count hoặc Metaspace usage tăng.
- Class loader cũ không được thu hồi.

Hướng điều tra:

1. Dùng `jcmd <pid> VM.metaspace` và class histogram để quan sát.
2. Tìm thread hoặc ThreadLocal giữ class loader cũ.
3. Kiểm tra static registry, logging/plugin framework và listener.
4. Kiểm tra dependency tạo thread hoặc đăng ký callback nhưng không dọn dẹp.
5. Sửa vòng đời class loader; chỉ tăng `MaxMetaspaceSize` khi mức sử dụng hợp lệ thực sự cần cao hơn.

### Tình huống D — Không tạo thêm thread được

Triệu chứng:

```text
OutOfMemoryError: unable to create native thread
```

Hướng điều tra:

1. Đếm số thread bằng thread dump hoặc công cụ quản lý process.
2. Kiểm tra thread pool có giới hạn hay đang tạo thread không kiểm soát.
3. Kiểm tra giới hạn process/thread của OS và container.
4. Kiểm tra kích thước stack và tổng native memory.
5. Ưu tiên giới hạn concurrency và dùng executor có cấu hình phù hợp.

Tăng heap thường không giải quyết lỗi tạo native thread.

## 12. Nguyên tắc cấu hình bộ nhớ cho ứng dụng Java 17

### 12.1. Lập ngân sách tổng, không chỉ đặt Xmx

Trước khi triển khai, xác định:

- Giới hạn RAM của máy/container.
- Heap tối đa dự kiến.
- Metaspace dự kiến và giới hạn nếu cần.
- Số thread tối đa và stack mỗi thread.
- Direct buffer/mapped memory.
- Code Cache và cấu trúc native của JVM.
- Bộ nhớ native của thư viện bên thứ ba.
- Headroom cho hệ điều hành và biến động tải.

### 12.2. Đo trước khi điều chỉnh

Không tăng mọi giới hạn cùng lúc. Thu thập GC log, heap dump, NMT và thread dump để xác định vùng nào đang chịu áp lực.

### 12.3. Phân biệt capacity với leak

- **Capacity issue:** workload hợp lệ cần nhiều bộ nhớ hơn giới hạn hiện tại.
- **Leak:** bộ nhớ không được giải phóng vì vẫn có tham chiếu hoặc tài nguyên không được đóng.
- **Native pressure:** bộ nhớ ngoài heap tăng dù heap không tăng tương ứng.

Ba tình huống này cần cách xử lý khác nhau.

### 12.4. Giới hạn tài nguyên ở tầng ứng dụng

- Giới hạn cache, queue và batch size.
- Dùng thread pool có giới hạn.
- Đóng file, socket và resource đúng lúc.
- Quản lý direct buffer theo vòng đời hợp lý.
- Giới hạn request size và dữ liệu đầu vào.
- Tránh tạo object lớn không cần thiết trong vòng lặp nóng.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| `-Xmx` là giới hạn RAM của toàn tiến trình | `-Xmx` chỉ giới hạn Java heap |
| Object luôn nằm vật lý trên heap vì code có `new` | JVM có thể tối ưu allocation nếu hành vi quan sát được không đổi |
| Biến local là object nằm trên stack | Biến local có thể là primitive hoặc reference trong frame; object được tham chiếu thường ở heap |
| Stack được chia sẻ giữa các thread | Mỗi thread có JVM stack riêng |
| Tăng `-Xss` luôn giải quyết StackOverflowError | Nó chỉ tăng dung lượng stack; đệ quy vô hạn vẫn gây lỗi và mỗi thread sẽ cần nhiều tài nguyên hơn |
| GC thu hồi mọi loại bộ nhớ của process | GC quản lý object heap; native memory có vòng đời/quản lý riêng |
| Metaspace chứa mọi object của class | Metaspace chứa class metadata; instance thông thường ở heap |
| Metaspace là một phần của `-Xmx` | Trong HotSpot, Metaspace dùng native memory ngoài heap |
| DirectByteBuffer không dùng RAM | Vùng dữ liệu direct buffer vẫn tiêu thụ native memory |
| Heap còn trống thì không thể OOME | Có thể hết Metaspace, direct memory, native thread hoặc stack |
| RSS phải nhỏ hơn hoặc bằng `-Xmx` | RSS gồm heap resident và nhiều vùng native khác |
| NMT đo toàn bộ native memory của mọi thư viện | NMT theo dõi nhiều vùng do HotSpot quản lý nhưng không bao phủ mọi allocator bên ngoài |

## 14. Bài tập thực hành

### Bài 1 — Phân loại vùng nhớ

Với mỗi mục dưới đây, xác định vùng bộ nhớ phù hợp nhất:

1. Một object `Customer` được tạo bằng `new`.
2. Biến `int count` trong một lời gọi phương thức.
3. Metadata mô tả class `Customer` trong HotSpot.
4. Dữ liệu của `ByteBuffer.allocateDirect(4096)`.
5. Frame của một phương thức đang thực thi trên thread.
6. Mã máy được JIT biên dịch.

**Gợi ý:** Heap; local variable/frame; Metaspace; direct/native memory; Java stack; Code Cache.

### Bài 2 — Phân tích lỗi

Một ứng dụng có `-Xmx4g`, heap usage chỉ khoảng 1.5 GiB nhưng vẫn gặp:

```text
java.lang.OutOfMemoryError: Metaspace
```

Giải thích vì sao tăng `-Xmx` không trực tiếp giải quyết lỗi. Nêu những số liệu cần thu thập và một số nguyên nhân class loader leak.

### Bài 3 — Tính ngân sách stack

Một dịch vụ có tối đa 250 platform threads và cấu hình `-Xss1m`.

- Ước lượng tổng vùng stack được reserve theo cấu hình.
- Vì sao RSS thực tế có thể thấp hơn hoặc khác phép nhân này?
- Nếu thread count tăng gấp đôi, điều gì thay đổi?

### Bài 4 — Đọc cấu hình JVM

Giải thích ý nghĩa của:

```bash
java -Xms512m -Xmx2g -Xss1m \
     -XX:MaxMetaspaceSize=512m \
     -XX:MaxDirectMemorySize=256m \
     -XX:NativeMemoryTracking=summary \
     -jar app.jar
```

Nêu ít nhất ba nhóm bộ nhớ vẫn có thể làm tổng RAM tiến trình vượt 2 GiB.

### Bài 5 — Chọn công cụ chẩn đoán

Chọn công cụ phù hợp cho từng mục tiêu:

- Xem heap và GC.
- Xem Metaspace.
- Xem stack trace các thread.
- Xem nhóm native memory do HotSpot quản lý.
- Tìm object đang giữ nhiều heap.

**Gợi ý:** `jcmd GC.heap_info`, `jcmd VM.metaspace`, `jcmd Thread.print`, `jcmd VM.native_memory summary`, heap dump và công cụ phân tích heap.

### Bài 6 — Thiết kế giới hạn

Một API tạo direct buffer theo kích thước do client gửi. Hãy nêu các giới hạn cần đặt ở tầng request và JVM để tránh cấp phát native memory không kiểm soát. Giải thích vì sao chỉ đặt `-Xmx` không đủ.

## 15. Tài liệu chính thức của Java 17

- [Java Virtual Machine Specification 17 — Chapter 2: The Structure of the Java Virtual Machine](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): runtime data areas, heap, stack, method area, PC register và native method stack.
- [Java SE 17 API — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): thông tin bộ nhớ heap mà runtime báo cáo.
- [Java SE 17 API — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): heap buffer và direct buffer.
- [Java SE 17 API — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): memory-mapped file qua `map`.
- [Java 17 HotSpot Virtual Machine Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): các tùy chọn JVM như heap, stack, Metaspace và direct memory.
- [Java 17 jcmd man page](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): công cụ chẩn đoán tiến trình JVM.
- [JEP 122 — Remove the Permanent Generation](https://openjdk.org/jeps/122): lịch sử chuyển class metadata sang native memory; khi cấu hình Java 17, dùng Metaspace thay cho các tùy chọn PermGen cũ.

**Ghi nhớ:** Heap chứa object và array, được GC quản lý; mỗi thread có Java stack riêng chứa frame của các lời gọi; Metaspace của HotSpot lưu class metadata trong native memory; còn off-heap là nhóm rộng gồm direct buffer, code cache, thread/native stack, memory mapping và các vùng JVM/native khác. `-Xmx` không giới hạn toàn bộ RAM tiến trình. Muốn điều tra chính xác, hãy kết hợp GC log, heap dump, thread dump, Metaspace statistics, Native Memory Tracking và số liệu hệ điều hành.
