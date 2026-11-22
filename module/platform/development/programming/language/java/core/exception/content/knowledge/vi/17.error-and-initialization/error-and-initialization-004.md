# OutOfMemoryError và giới hạn phục hồi trong cùng tiến trình Java

## 1. Vì sao chủ đề này quan trọng?

`OutOfMemoryError`, thường gọi tắt **OOME**, báo rằng máy ảo Java không thể đáp ứng một nhu cầu cấp phát bộ nhớ hoặc tài nguyên tương ứng trong những điều kiện nhất định. Nó không chỉ xuất hiện khi `new byte[...]` làm đầy Java heap: ứng dụng còn có thể gặp thiếu native memory, metaspace, direct buffers, giới hạn tạo thread hoặc giới hạn kích thước mảng.

Sai lầm phổ biến nhất là xem OOME như một lỗi nghiệp vụ thông thường: viết `catch (OutOfMemoryError e)`, gọi `System.gc()`, xóa vài phần tử cache rồi cho toàn bộ dịch vụ tiếp tục như trước. **Bắt được OOME không chứng minh JVM đã đủ tài nguyên, dữ liệu còn nhất quán hoặc request tiếp theo an toàn.** Một số dạng lỗi không cho JVM cơ hội catch, chẳng hạn tiến trình bị hệ điều hành/container OOM killer chấm dứt.

Mục tiêu bài học:

- Xác định đúng cây kế thừa và hợp đồng **unchecked `Error`**.
- Phân biệt thiếu heap với metaspace, native thread, direct buffer và các giới hạn khác.
- Hiểu JVM có thể còn chạy sau OOME nhưng **không bảo đảm** khôi phục ứng dụng.
- Nhận biết giới hạn của `catch`, `finally`, `try-with-resources`, GC thủ công và bộ nhớ dự phòng.
- Giải thích OOME trong **static initialization** và tác động tới các lần sử dụng class sau.
- Thiết kế giới hạn memory input/cache/concurrency, streaming và backpressure để phòng tránh lỗi.
- Chẩn đoán qua heap dump, GC logs, JFR, process metrics, Native Memory Tracking và dữ liệu OOM kill.
- Xây dựng chính sách fail-fast, phát hiện sự cố và restart ngoài tiến trình, có kiểm tra trạng thái nghiệp vụ.
- Viết ví dụ Java 17+ an toàn **không cố làm cạn bộ nhớ thật**.

Tất cả ví dụ chạy được đều có tên file, lệnh `javac`/`java` và `stdout`. Những ví dụ ném `new OutOfMemoryError("simulated")` là **lỗi giả lập có chủ đích**, chỉ dùng để học ngữ nghĩa exception và class initialization, **không phải thử nghiệm khả năng phục hồi trong môi trường thực sự hết RAM**.

## 2. `OutOfMemoryError` nằm ở đâu trong cây `Throwable`?

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── java.lang.RuntimeException [unchecked]
│   └── các checked exceptions
└── java.lang.Error                  [unchecked]
    └── java.lang.VirtualMachineError
        ├── java.lang.OutOfMemoryError
        ├── java.lang.StackOverflowError
        └── java.lang.InternalError
```

`OutOfMemoryError` là subclass của `VirtualMachineError` → `Error` → `Throwable`, **không** là subclass của `Exception`. Vì thế:

- `catch (Exception e)` và `catch (RuntimeException e)` không bắt OOME.
- `catch (OutOfMemoryError e)`, `catch (Error e)`, `catch (VirtualMachineError e)` và `catch (Throwable e)` có thể nhận OOME về mặt kiểu.
- Compiler **không buộc** method khai báo `throws OutOfMemoryError`.
- “Unchecked” chỉ là quy tắc compile-time, **không** đồng nghĩa ít nghiêm trọng hoặc có thể an toàn bỏ qua.

### Chương trình chạy được: kiểm tra quan hệ kiểu

Tạo file **`OomeHierarchyDemo.java`**:

```java
public class OomeHierarchyDemo {
    public static void main(String[] args) {
        Throwable sample = new OutOfMemoryError("simulated");

        System.out.println("type="
                + sample.getClass().getSimpleName());
        System.out.println("Throwable="
                + (sample instanceof Throwable));
        System.out.println("Error="
                + (sample instanceof Error));
        System.out.println("VirtualMachineError="
                + (sample instanceof VirtualMachineError));
        System.out.println("Exception="
                + (sample instanceof Exception));
    }
}
```

```bash
javac OomeHierarchyDemo.java
java OomeHierarchyDemo
```

`stdout`:

```text
type=OutOfMemoryError
Throwable=true
Error=true
VirtualMachineError=true
Exception=false
```

Chương trình chỉ tạo một đối tượng Throwable nhỏ, **không** cố cạn kiệt memory. Phép kiểm tra `instanceof` dùng biến có kiểu tĩnh `Throwable` để minh họa chính xác quan hệ kế thừa.

## 3. Những nguyên nhân OOME thường gặp

Thông điệp `OutOfMemoryError` gợi ý khu vực cần điều tra, nhưng không phải một bộ mã lỗi tiêu chuẩn bất biến giữa mọi JVM/JDK. Không thiết kế nghiệp vụ bằng cách so khớp duy nhất chuỗi `getMessage()`.

| Biểu hiện/thông điệp thường gặp | Hướng điều tra | Sai lầm cần tránh |
| --- | --- | --- |
| `Java heap space` | Giới hạn `-Xmx`, object còn sống, dữ liệu quá lớn, allocation spikes | Kết luận tất cả đều là leak |
| `GC overhead limit exceeded` | Thu gom rác rất tốn công mà giải phóng ít theo ngưỡng JVM | Gọi `System.gc()` vô hạn |
| `Metaspace` | Metadata class, class loading, class loader giữ lại, `MaxMetaspaceSize` | Chỉ tăng Java heap |
| `Requested array size exceeds VM limit` | Kích thước mảng bị giới hạn hoặc không biểu diễn được | Tin rằng cứ tăng RAM là tạo được |
| `unable to create native thread` | Native thread, stack, OS/process/container limits | Khẳng định heap chắc chắn đầy |
| Lỗi cấp direct-buffer memory | `ByteBuffer.allocateDirect`, budget native/direct buffers | Đọc `Runtime.freeMemory()` rồi kết luận đủ RAM |

### 3.1. Java heap

Các object Java được quản lý bởi GC thường nằm trên heap. Thiếu heap có thể do:

- **Leak logic**: cache không eviction, static collection, listeners, `ThreadLocal`, session hoặc queue vẫn giữ tham chiếu.
- **Live-set hợp lệ nhưng quá lớn**: yêu cầu nghiệp vụ giữ nhiều dữ liệu hơn cấu hình heap cho phép.
- **Allocation spike**: parse file lớn, decode ảnh, tạo nhiều bản sao chuỗi/array, batch processing và concurrent requests.
- **Một allocation riêng quá lớn**: buffer, mảng hoặc đối tượng trung gian không đáp ứng giới hạn.

GC không thể dọn object còn reachable chỉ vì ứng dụng cảm thấy chúng “không cần nữa”. Ngược lại, nhiều object còn sống là nghiệp vụ thực sự có thể không phải leak, mà cần thay đổi cấu trúc xử lý hoặc ngân sách memory.

### 3.2. Metaspace

Metaspace liên quan metadata class và thường sử dụng native memory. Framework tạo proxy/class động, nạp plugin qua nhiều class loader, hoặc giữ class loader cũ có thể gây áp lực. Điều tra class count, class loader lifetime, `-XX:MaxMetaspaceSize` và bộ nhớ native thay vì chỉ đọc `-Xmx`.

### 3.3. Native memory, direct buffers và threads

Direct buffers, thread stacks, JNI libraries, native allocator và một số thành phần JVM sử dụng tài nguyên không được đo đầy đủ chỉ bằng số liệu free heap. Trong container, **tổng RSS/process memory** cùng với cgroup limit quan trọng không kém `-Xmx`.

Tăng Java heap lên sát giới hạn RAM/container có thể làm **thiếu chỗ cho native memory**, khiến lỗi khác trầm trọng hơn. Thread pool không giới hạn hoặc quá nhiều platform threads có thể thất bại lúc tạo native thread dù heap vẫn còn.

### 3.4. OS OOM kill khác với Java OOME

Nếu hệ điều hành/container quyết định chấm dứt process vì vượt memory budget, Java **không nhất thiết nhận được một đối tượng `OutOfMemoryError` để catch**. Không có cơ hội bảo đảm chạy `finally`, shutdown hook hay ghi heap dump trước khi bị kill. Cần lấy dấu hiệu từ **supervisor, cgroup/container events và host logs**.

## 4. JVM có thể còn chạy nhưng trạng thái ứng dụng chưa chắc an toàn

Java không định nghĩa rằng mỗi `OutOfMemoryError` luôn lập tức tắt JVM. Một thread có thể ném OOME, unwind stack, chạy handler tương ứng và thread khác tiếp tục hoạt động. Đôi khi sau một request thất bại, một số object không còn reachable, GC có thể thu hồi memory.

Nhưng điều đó không cho phép kết luận:

- Bộ nhớ đã đủ cho request tiếp theo.
- Cache hoặc hàng đợi đã giảm tới ngưỡng an toàn.
- Transaction được rollback hoàn toàn.
- External API đã thực hiện hay chưa.
- Các bất biến của object đang được nhiều thread dùng còn nhất quán.
- Một class từng khởi tạo thất bại có thể init lại bình thường.
- Thao tác log, gửi metric hoặc tạo error response có thể chắc chắn thành công.

Ví dụ một request có thể cập nhật state trong heap, gửi yêu cầu ngoài hệ thống rồi OOME khi cần cấp phát buffer xử lý phản hồi. **Catch OOME không đảo ngược side effect**, cũng không cho biết request có an toàn để retry hay không.

Ba lớp kiểm tra cần phân biệt:

1. **Liveness của JVM**: process còn chạy?
2. **Readiness**: instance có đủ tài nguyên và trạng thái tốt để nhận workload mới?
3. **Consistency**: dữ liệu bền vững, giao dịch và trạng thái nghiệp vụ có khớp không?

Một lệnh `return true` từ health endpoint sau một `catch` không phải bằng chứng đáng tin cho cả ba lớp.

## 5. `catch (OutOfMemoryError)` đúng cú pháp, nhưng không phải recovery mặc định

Có thể viết:

```java
try {
    operation();
} catch (OutOfMemoryError failure) {
    // Chỉ thực hiện tín hiệu cực tối giản nếu thật sự cần.
    throw failure;
}
```

Đây là **mảnh minh họa**, cần định nghĩa `operation()`. Trong mã sản phẩm, **không nên** biến handler này thành một chuỗi công việc nặng: dựng JSON phản hồi, format stack trace đầy đủ, gửi HTTP, lấy snapshot lớn, cấp phát cache mới, tạo thread hoặc retry ngay cùng thao tác.

### Chương trình chạy được: bắt rồi ném tiếp lỗi được tạo có chủ đích

Tạo file **`ControlledOomePropagationDemo.java`**:

```java
public class ControlledOomePropagationDemo {
    static void run() {
        try {
            throw new OutOfMemoryError("simulated only");
        } catch (OutOfMemoryError failure) {
            System.out.println("boundary=observed");
            throw failure;
        } finally {
            System.out.println("finally=ran");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (OutOfMemoryError failure) {
            System.out.println("caller=" + failure.getMessage());
        }
    }
}
```

```bash
javac ControlledOomePropagationDemo.java
java ControlledOomePropagationDemo
```

`stdout`:

```text
boundary=observed
finally=ran
caller=simulated only
```

Đây là **đường thực thi bình thường của Throwable được ném**, không phải một JVM đang thật sự cạn bộ nhớ. Dòng `finally=ran` chứng minh `finally` chạy trong ví dụ này, **không** chứng minh nó luôn chạy khi process bị OS kill hoặc JVM không còn tài nguyên.

### Vì sao handler cũng có thể thất bại?

Trong hoàn cảnh thiếu bộ nhớ, các thao tác sau vẫn có thể cần cấp phát:

- Nối chuỗi, tạo stack trace text, serialize JSON hoặc format một logging event.
- Enqueue một message cho logger bất đồng bộ.
- Khởi tạo class được dùng lần đầu trong handler.
- Tạo object exception mới để bọc lỗi.
- Mở socket, tạo thread, thực hiện I/O phức tạp.
- Tạo response HTTP và state cho framework.

Một handler chứa các bước trên **không được bảo đảm hoàn thành**. Việc catch trả về bình thường sau OOME có thể khiến các request khác tiếp tục vào một JVM đang thiếu bộ nhớ hoặc có state dở dang.

### Có nên dành sẵn một buffer “cấp cứu”?

Một số ứng dụng chuẩn bị một buffer từ sớm rồi bỏ tham chiếu khi có lỗi với hy vọng GC tạo không gian ghi tín hiệu ngắn. Kỹ thuật này chỉ là **best-effort**: có thể không giúp được native/metaspace/thread exhaustion; GC không bảo đảm giải phóng đủ ngay; thread khác vẫn cấp phát; state nghiệp vụ cũng không được khôi phục. **Không coi reserve là bảo đảm recovery trong cùng process**.

## 6. `finally` và `try-with-resources`: bảo đảm ngữ nghĩa nhưng không phải phép màu

Khi một Throwable được ném theo cơ chế Java thông thường, `finally` được thực hiện theo quy tắc điều khiển luồng. `try-with-resources` cố đóng những resource đã tạo thành công, và nếu phần thân cùng `close()` đều ném, lỗi close có thể được ghi là **suppressed exception** của lỗi chính.

Nhưng:

- Nếu process bị OS giết, `Runtime.halt`, mất điện hoặc JVM crash, `finally` không có bảo đảm chạy.
- `close()` có thể cần memory, I/O hoặc ném lỗi khác.
- `finally` tự ném một Throwable khác có thể che mất lỗi gốc khi viết cleanup thủ công sai.
- Monitor của `synchronized` được giải phóng khi thoát vì exception theo luồng Java thông thường, **không** rollback state từng bị sửa.
- Ngay cả khi transaction rollback được thiết kế đúng, vẫn cần kiểm tra giao dịch đã commit hay chưa ở hệ thống khác.

### Chương trình chạy được: resource đóng khi ném OOME giả lập

Tạo file **`ControlledOomeCleanupDemo.java`**:

```java
public class ControlledOomeCleanupDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close=called");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new OutOfMemoryError("controlled failure");
        } catch (OutOfMemoryError failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ControlledOomeCleanupDemo.java
java ControlledOomeCleanupDemo
```

`stdout`:

```text
close=called
caught=controlled failure
```

Chương trình minh họa TWR **với error được tạo khi heap vẫn khỏe**. Nó không phải stress test, không chứng minh mọi resource vẫn đóng được khi native memory hoặc heap thật sự cạn.

**Thiết kế đúng:** đặt cleanup ở phạm vi sở hữu resource, dùng transaction và cơ chế phục hồi dữ liệu có thể hoạt động sau crash. Không để một JVM OOME chịu trách nhiệm duy nhất cho tính toàn vẹn của hệ thống.

## 7. OOME trong static initialization: trạng thái lỗi có thể tồn tại lâu

Một `OutOfMemoryError` xuất hiện trong quá trình khởi tạo static field/initializer của class có thể làm quá trình **class initialization thất bại**. JVM ghi nhận class đó ở trạng thái initialization error trong class loader tương ứng.

Khi Throwable thoát khỏi class initializer là một **Error** (như OOME), lỗi có thể được truyền ra **nguyên dạng** ở lần đầu. Khi truy cập lại class bị khởi tạo lỗi, JVM thường ném `NoClassDefFoundError` thay vì tự khởi chạy lại toàn bộ static initializer.

### Chương trình chạy được: class đã khởi tạo thất bại

Tạo file **`OomeClassInitializationDemo.java`**:

```java
public class OomeClassInitializationDemo {
    static class Broken {
        static final int VALUE = initialize();

        static int initialize() {
            throw new OutOfMemoryError("simulated during init");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(Broken.VALUE);
        } catch (OutOfMemoryError failure) {
            System.out.println("first="
                    + failure.getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.VALUE);
        } catch (NoClassDefFoundError failure) {
            System.out.println("second="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac OomeClassInitializationDemo.java
java OomeClassInitializationDemo
```

`stdout` trong Java 17:

```text
first=OutOfMemoryError
second=NoClassDefFoundError
```

Phân tích:

1. Truy cập `Broken.VALUE` lần đầu kích hoạt khởi tạo `Broken`.
2. `initialize()` ném OOME giả lập. Vì đó là `Error`, nó có thể truyền ra nguyên dạng, không cần bọc thành `ExceptionInInitializerError`.
3. `Broken` rơi vào trạng thái khởi tạo lỗi trong class loader.
4. Lần truy cập tiếp theo không phải một lần thử lại trong cùng class loader: JVM báo `NoClassDefFoundError`.
5. Không có bộ nhớ nào bị cố tình làm cạn trong bài test.

Trường hợp này cho thấy **khôi phục cục bộ bằng một catch không đủ**: có thể còn dấu vết lỗi kéo dài ngay trong trạng thái runtime. Khi static initializer ném Throwable **không phải Error**, quy tắc JLS có thể bọc thành `ExceptionInInitializerError`; đừng đồng nhất hai trường hợp.

## 8. `System.gc()` không phải nút sửa OOME

`System.gc()` là lời yêu cầu/hint với JVM về nỗ lực thu gom rác, không bảo đảm đúng thời điểm, loại GC hoặc lượng memory giải phóng; một số cấu hình có thể vô hiệu hóa explicit GC.

Ngay cả khi GC thực hiện:

- Object **còn reachable** từ static cache hoặc queue sẽ không tự mất.
- Yêu cầu array vượt giới hạn VM vẫn không hợp lệ.
- Native thread resource không tự hồi phục do full GC.
- Metaspace leak do class loader còn tham chiếu vẫn có thể tồn tại.
- OS OOM killer đã dừng process thì không có code Java nào để gọi GC.

Mẫu anti-pattern:

```java
try {
    doWork();
} catch (OutOfMemoryError failure) {
    System.gc();
    doWork(); // Retry ngay trong cùng tình trạng.
}
```

Đây là **mảnh code sai chính sách**, cần định nghĩa `doWork`. Nó có thể thất bại lặp lại và gây side effect trùng. Không dùng GC thủ công thay cho xác định nguyên nhân, giới hạn workload và quản lý vòng đời dữ liệu.

### `Runtime.freeMemory()` không phải “toàn bộ RAM còn lại”

`Runtime.getRuntime().freeMemory()` mô tả vùng trống trong heap **hiện tại** của JVM, không phải toàn bộ physical RAM, cgroup limit, direct memory hoặc số byte native thread còn có thể cấp phát. `Runtime.maxMemory()` chủ yếu là giới hạn heap; nó cũng không thay thế đo RSS và native memory.

Khi chẩn đoán, cần xem **used, committed, max heap**, non-heap, GC, direct/mapped buffers, số thread, class loaders, queue size, process RSS và giới hạn container cùng lúc.

## 9. Chặn yêu cầu cấp phát quá lớn trước khi chạm JVM limit

Đầu vào từ mạng, file, JSON, ảnh hoặc cấu hình có thể chứa các trường kích thước không tin cậy. Không nên viết:

```java
int count = Integer.parseInt(input);
byte[] buffer = new byte[count];
```

Đây là **mảnh minh họa anti-pattern**, vì `input` chưa có giới hạn, có thể âm hoặc quá lớn. Chương trình cần áp **max size theo nghiệp vụ**, kiểm tra toán học tránh integer overflow và ngân sách tổng cho các request đồng thời.

### Chương trình chạy được: từ chối trước khi cấp phát

Tạo file **`AllocationBudgetDemo.java`**:

```java
public class AllocationBudgetDemo {
    static byte[] allocateBounded(int count, int maxAllowed) {
        if (count < 0 || count > maxAllowed) {
            throw new IllegalArgumentException(
                    "allocation outside allowed budget");
        }
        return new byte[count];
    }

    public static void main(String[] args) {
        System.out.println("length="
                + allocateBounded(8, 16).length);

        try {
            allocateBounded(1000, 16);
        } catch (IllegalArgumentException failure) {
            System.out.println("rejected=" + failure.getMessage());
        }
    }
}
```

```bash
javac AllocationBudgetDemo.java
java AllocationBudgetDemo
```

`stdout`:

```text
length=8
rejected=allocation outside allowed budget
```

Cách này biến input không hợp lệ thành một lỗi **có kiểm soát** mà không cố gây OOME. Tuy vậy, một allocation dưới budget **không phải lời bảo đảm tuyệt đối** sẽ thành công trong mọi JVM: còn nhiều thread và object khác tranh memory.

Để tránh tràn số khi tính ngân sách cho `count * elementSize`, nên dùng kiểu `long` hoặc phép kiểm tra như `Math.multiplyExact` cùng giới hạn rõ ràng trước khi allocate.

## 10. Streaming có giới hạn thay cho đọc tất cả dữ liệu

`Files.readAllBytes(...)`, `Files.readAllLines(...)` hoặc gom tất cả entry vào `ArrayList` có thể phù hợp với input nhỏ. Khi kích thước không chắc chắn, chúng dễ tạo peak memory lớn; hơn nữa giải nén có thể làm dữ liệu **sau giải nén** phình ra nhiều lần.

Hướng xử lý:

- Đọc theo buffer/chunk vừa đủ.
- Giới hạn **tổng byte**, số record, độ dài mỗi token/line và độ sâu cấu trúc.
- Giải phóng resource bằng `try-with-resources` theo ownership.
- Không cache toàn bộ body request trong middleware rồi lại tạo bản sao ở parser.
- Khi concurrent, áp budget **tổng hợp**, không chỉ từng request.

### Chương trình chạy được: enforce giới hạn khi đọc luồng

Tạo file **`StreamingInputBudgetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class StreamingInputBudgetDemo {
    static long consume(InputStream input, long maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        long total = 0;
        byte[] chunk = new byte[3];
        int count;

        while ((count = input.read(chunk)) != -1) {
            if (count > maxBytes - total) {
                throw new IOException(
                        "input exceeds " + maxBytes + " bytes");
            }
            total += count;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        byte[] data = "abcde".getBytes(StandardCharsets.UTF_8);

        try (InputStream input = new ByteArrayInputStream(data)) {
            System.out.println("accepted=" + consume(input, 5));
        }

        try (InputStream input = new ByteArrayInputStream(data)) {
            consume(input, 4);
        } catch (IOException failure) {
            System.out.println("rejected=" + failure.getMessage());
        }
    }
}
```

```bash
javac StreamingInputBudgetDemo.java
java StreamingInputBudgetDemo
```

`stdout`:

```text
accepted=5
rejected=input exceeds 4 bytes
```

Ví dụ chỉ dùng buffer 3 byte, chặn dữ liệu khi vượt budget thay vì tạo mảng kích thước không hạn chế. Đây mới là **kiểm tra tổng byte**; một parser sản xuất còn phải giới hạn độ dài token và nesting. `BufferedReader.readLine()` vẫn có thể tạo một `String` khổng lồ nếu một dòng cực dài, dù tổng file được đọc theo từng dòng.

Đừng chỉ tin `Content-Length` do client cung cấp; phải thực sự **enforce số byte đã nhận**, đồng thời phân biệt kích thước dữ liệu nén và sau giải nén.

## 11. Bounded cache: GC không tự xóa object còn tham chiếu

Một bộ nhớ cache như:

```java
static final java.util.Map<String, byte[]> CACHE =
        new java.util.HashMap<>();

static void put(String key, byte[] value) {
    CACHE.put(key, value);
}
```

là **mảnh code nhận diện rủi ro**. Nếu key mới tăng mãi, static map vẫn tham chiếu payload; GC không tự thu hồi chúng theo ý định nghiệp vụ.

Chọn biện pháp như eviction, TTL, giới hạn **số entry**, tốt hơn nữa là giới hạn **trọng lượng byte** khi các object có kích thước rất khác nhau. Cần theo dõi cache hit ratio, tổng size, eviction count và vòng đời. `WeakHashMap` cũng **không phải bounded cache mặc định**: nó có điều kiện xóa theo tham chiếu yếu tới key và có nhiều hạn chế nếu value tham chiếu ngược.

### Chương trình chạy được: cache ba entry

Tạo file **`BoundedCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class BoundedCacheDemo {
    static class LimitedMap extends LinkedHashMap<Integer, String> {
        private final int capacity;

        LimitedMap(int capacity) {
            this.capacity = capacity;
        }

        @Override
        protected boolean removeEldestEntry(
                Map.Entry<Integer, String> eldest) {
            return size() > capacity;
        }
    }

    public static void main(String[] args) {
        LimitedMap cache = new LimitedMap(3);

        for (int i = 1; i <= 5; i++) {
            cache.put(i, "value-" + i);
        }

        System.out.println("size=" + cache.size());
        System.out.println("keys=" + cache.keySet());
    }
}
```

```bash
javac BoundedCacheDemo.java
java BoundedCacheDemo
```

`stdout`:

```text
size=3
keys=[3, 4, 5]
```

Do `LinkedHashMap` mặc định giữ insertion order, các entry cũ nhất bị loại khi vượt size 3. Đây là kỹ thuật học tập đơn giản, **chưa có synchronization** và **chưa giới hạn tổng byte payload**. Trong ứng dụng nhiều thread, cần cấu trúc cache thread-safe phù hợp và ngân sách toàn hệ thống.

## 12. Giới hạn thread pool **và** task queue

Giới hạn số worker chưa đủ nếu hàng đợi task không giới hạn. Một queue khổng lồ có thể giữ closure và các payload của hàng triệu request.

Ví dụ:

- `Executors.newFixedThreadPool(n)` có số worker cố định nhưng **queue mặc định không giới hạn**.
- `Executors.newCachedThreadPool()` có thể tạo thêm thread theo tải và cần chính sách giới hạn thực tế.
- `CompletableFuture` hoặc hàng đợi framework có thể giữ state chờ lâu.
- Retry vô hạn có thể tạo thêm task và dữ liệu khi hệ thống vốn đang quá tải.

Nên dùng bounded queue, admission control, semaphore, backpressure hoặc reject có kiểm soát; quyết định dựa trên yêu cầu độ trễ và idempotency.

### Chương trình chạy được: bounded executor

Tạo file **`BoundedExecutorDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedExecutorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.CallerRunsPolicy());

        AtomicInteger done = new AtomicInteger();

        for (int i = 0; i < 6; i++) {
            pool.execute(done::incrementAndGet);
        }

        pool.shutdown();
        boolean terminated =
                pool.awaitTermination(5, TimeUnit.SECONDS);

        System.out.println("terminated=" + terminated);
        System.out.println("completed=" + done.get());
    }
}
```

```bash
javac BoundedExecutorDemo.java
java BoundedExecutorDemo
```

`stdout` trong một môi trường lập lịch bình thường:

```text
terminated=true
completed=6
```

Queue tối đa 2 task; một worker; khi bão hòa, `CallerRunsPolicy` có thể làm thread submit chạy task nhằm tạo backpressure. Sau khi submit hết sáu task, chương trình shutdown và chờ chúng hoàn thành, nên counter là 6 trong điều kiện thời gian chờ đủ.

**Giới hạn:** `CallerRunsPolicy` không phải giải pháp cho mọi ứng dụng; nó có thể tăng latency ở caller hoặc gây tác động trong request thread. Khi executor đã shutdown, handler này có thể bỏ task theo contract. Queue dù bounded vẫn không giới hạn mọi memory dùng bên ngoài nó. Trong môi trường quá tải thật, nên có timeout/rejection/observability.

## 13. Khi nào có thể phục hồi cục bộ?

Không có quy tắc Java tổng quát rằng **mọi OOME đều bắt buộc giết JVM**, nhưng cũng không có bảo đảm có thể tiếp tục phục vụ. Một phương án phục hồi cục bộ chỉ đáng xem xét nếu ứng dụng có **bằng chứng cụ thể**:

- Lỗi bị giới hạn trong một **phân vùng/tác vụ** có ownership và state rõ ràng.
- Resource có thể được thu hồi an toàn.
- Các bất biến dữ liệu và transaction đã được khôi phục hoặc có thể kiểm chứng.
- Không làm rò rỉ lỗi sang thread/shared cache/singleton/class initialization.
- Memory pressure đã giảm theo số liệu đáng tin.
- Thao tác retry nếu có là idempotent, có giới hạn và backoff.
- Người vận hành chấp nhận residual risk và có thể ngắt instance từ xa.

Với phần lớn dịch vụ backend, các điều kiện này **khó chứng minh khi JVM thực sự cạn tài nguyên**. Một chính sách đáng tin hơn là coi instance **không còn sẵn sàng phục vụ**, phát tín hiệu best-effort và dùng **supervisor ngoài process** để thay thế nó.

### Restart không sửa root cause

Restart dọn trạng thái tiến trình bị lỗi và tạo cơ hội phục vụ lại, nhưng nếu heap leak, class-loader leak, queue tăng vô hạn hoặc input thiếu giới hạn vẫn còn, instance mới có thể OOME lần nữa. Phải sửa **nguyên nhân thiết kế, cấu hình và workload** rồi kiểm chứng dưới load test.

## 14. Biên process: phát hiện, fail-fast và restart

Một mô hình thực tế:

```text
Ứng dụng có memory budget và health checks
                   |
                   v
             OOME hoặc OOM kill
                   |
                   v
        Instance không còn đáng tin
                   |
                   +--> Tín hiệu lỗi best-effort (nếu còn thực thi)
                   +--> Dừng/thoát theo chính sách JVM, service
                   |
                   v
  Service manager / container orchestrator (ngoài JVM)
                   |
                   +--> Thấy process chết, health check hỏng, mất heartbeat
                   +--> Áp dụng restart policy / backoff
                   v
             Khởi động instance mới
                   |
                   +--> Kiểm tra readiness
                   +--> Reconcile dữ liệu, task dở dang
                   v
             Nhận workload trở lại
```

Nếu process bị kill trực tiếp, code Java có thể **không ghi được log nào**. Vì thế công cụ ngoài process rất quan trọng.

Khi quyết định dừng process:

- `System.exit(...)` yêu cầu shutdown theo JVM và có thể chạy shutdown hooks. Hooks có thể cần memory, I/O hoặc lock; **không bảo đảm xử lý hoàn hảo khi OOME thật**.
- `Runtime.halt(...)` kết thúc quyết liệt hơn, bỏ shutdown hooks và có thể mất dữ liệu chưa flush. Không dùng tùy tiện như một cách sửa memory.
- JVM flags của HotSpot có thể hỗ trợ process exit/crash trên OOME, được cấu hình theo chính sách vận hành và tính hỗ trợ JVM.

**Không rải lệnh `System.exit` vào những method nghiệp vụ** chỉ vì catch OOME. Đây là quyết định ở tầng vận hành để bảo vệ toàn hệ thống.

### Bảo đảm dữ liệu khi restart

Dịch vụ cần tính nhất quán thường dùng transaction, idempotency keys, durable queues, outbox/inbox pattern, checkpoint và reconciliation. Nếu process chết giữa ghi dữ liệu, restart **không tự hoàn tác** mọi side effect; hệ thống phải biết bước nào đã commit và bước nào cần replay/compensate an toàn.

## 15. JVM options phục vụ chẩn đoán (HotSpot Java 17)

Các tùy chọn sau là **minh họa cấu hình**, không phải lệnh tạo lỗi:

```bash
java -Xms128m -Xmx512m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./diagnostics -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

`app.jar` do ứng dụng cung cấp; đường dẫn dump phải được chuẩn bị và có quyền ghi. Cấu hình memory 128/512 MiB chỉ là ví dụ, **không phải mức khuyến nghị** cho mọi workload.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-Xms128m` | Thiết lập mức heap ban đầu theo HotSpot |
| `-Xmx512m` | Giới hạn tối đa của Java heap, không bao gồm toàn bộ native RSS |
| `-XX:+HeapDumpOnOutOfMemoryError` | Yêu cầu tạo heap dump khi JVM gặp OOME thích hợp, theo khả năng thực tế |
| `-XX:HeapDumpPath=...` | Chỉ định nơi lưu dump |
| `-Xlog:gc*...` | Ghi thông tin GC theo unified logging của JVM |

Heap dump có thể **rất lớn** và chứa secrets, token, PII, nội dung request và thông tin giao dịch. Bảo vệ quyền đọc, dung lượng đĩa và retention. Không bảo đảm dump luôn tạo được: thiếu disk, OOM kill ngoài JVM, native failure hoặc những điều kiện nghiêm trọng khác có thể ngăn thu thập.

### Fail-fast flags

Một số HotSpot JVM hỗ trợ:

```text
-XX:+ExitOnOutOfMemoryError
-XX:+CrashOnOutOfMemoryError
```

Đây là **cờ JVM theo implementation**, không phải cú pháp Java source hoặc bảo đảm của mọi JVM vendor. Chọn theo yêu cầu giữ bằng chứng, core dump, restart và supervisor. Cần kiểm thử trên JDK/JVM cụ thể trước khi dùng trong production.

### Nên thu thập gì?

- Heap usage: **used, committed, max**, tốc độ cấp phát và dữ liệu GC.
- Metaspace/class loaders, loaded class count.
- Direct/mapped buffer pools, native memory và thread count.
- Process RSS, cgroup/container memory, host OOM events.
- Queue lengths, active requests, cache entries, payload sizes.
- Thời điểm tăng memory so với deploy, workload và release mới.
- Heap dump và GC logs từ **môi trường kiểm soát**, tránh bật tracing nặng gây thêm áp lực.

NMT (`Native Memory Tracking`) trong HotSpot hữu ích để xem một số nhóm native allocations của JVM, nhưng cần cấu hình và overhead; không bảo đảm mô tả đầy đủ memory của mọi thư viện native/JNI.

## 16. Điều tra heap dump: giữ tham chiếu và retained size

Nếu đã xác nhận vấn đề thuộc Java heap và có heap dump phù hợp:

1. Mở dump bằng Eclipse Memory Analyzer, VisualVM hoặc công cụ JVM tương thích.
2. Xem histogram: class nào có nhiều instance, nhiều byte trực tiếp.
3. Xem **dominator tree** và retained size.
4. Theo **paths to GC roots** để biết object nào giữ dữ liệu còn sống.
5. Tập trung vào caches, static maps, `ThreadLocal`, listeners, request/session objects, queues, buffer arrays.
6. Phân biệt một **memory leak** với tập dữ liệu lớn còn cần thiết hoặc allocation spike hợp lệ.
7. So sánh snapshot theo thời gian nếu có cách thu thập an toàn.
8. Sửa vòng đời/giới hạn dữ liệu; load test để chứng minh memory trở lại ổn định.
9. Dọn và bảo vệ dump vì có thể chứa dữ liệu nhạy cảm.

**Shallow size** là memory trực tiếp của một object. **Retained size** là lượng heap được giải phóng gián tiếp nếu đối tượng không còn giữ phần đồ thị liên quan. Một `HashMap` nhỏ về shallow size vẫn có thể giữ hàng triệu payload phía sau.

Nếu OOME liên quan thread/native/metaspace, chỉ phân tích một heap dump **có thể không tìm được toàn bộ nguyên nhân**; hãy kiểm tra số liệu vùng memory tương ứng.

## 17. OOME khác `StackOverflowError` và lỗi nghiệp vụ thường gặp

| Loại | Nhánh | Ý nghĩa điển hình |
| --- | --- | --- |
| `OutOfMemoryError` | `VirtualMachineError` | Không thể đáp ứng cấp phát memory/resource |
| `StackOverflowError` | `VirtualMachineError` | Stack một thread vượt giới hạn, thường do recursion |
| `InternalError` | `VirtualMachineError` | Sự cố nội bộ runtime |
| `ArithmeticException` | `RuntimeException` | Ví dụ chia số nguyên cho 0 |
| `IOException` | Checked `Exception` | Lỗi input/output cần xử lý/khai báo |

Không đồng nhất `StackOverflowError` với OOME. Tăng `-Xmx` không sửa một recursion vô hạn theo cách trực tiếp. Một lỗi `IOException` hoặc `ArithmeticException` có thể có quy trình xử lý theo nghiệp vụ; OOME không nên được đẩy vào cùng handler rồi trả response bình thường.

## 18. Lỗi phổ biến cần tránh

**“OOME nào cũng là Java heap đầy.”** Sai. Phải xem metaspace, native buffers, thread resources, VM limits và OS/container.

**“Bắt được OOME thì service đã phục hồi.”** Sai. JVM còn chạy không chứng minh ứng dụng và dữ liệu nhất quán.

**“`catch (Exception)` luôn bắt mọi `Throwable`.”** Sai. Nó không bắt `Error`.

**“`catch (Throwable)` rồi trả response thành công là ổn.”** Nguy hiểm: có thể che những lỗi nghiêm trọng và làm lan truyền trạng thái không còn đáng tin.

**“`System.gc()` chắc chắn giải phóng đủ memory.”** Sai. Nó không dọn reachable objects, và GC theo yêu cầu không có bảo đảm như vậy.

**“`finally` nhất định chạy dù process bị kill.”** Sai.

**“TWR luôn đóng xong mọi resource dù JVM đã hết memory.”** Không có bảo đảm tuyệt đối trong sự cố thảm khốc.

**“Nếu OOME giả lập và catch chạy, recovery trong OOME thật cũng sẽ chạy.”** Sai. Ném một đối tượng Error nhỏ không làm cạn memory.

**“Có heap dump nghĩa là nó mô tả hết native memory.”** Sai. Heap dump chủ yếu cho trạng thái Java heap.

**“Không thấy heap dump tức là không có OOME.”** Sai. Process có thể bị kill trực tiếp hoặc không còn khả năng ghi dump.

**“`-Xmx` là giới hạn tổng RAM của process.”** Sai. Native, metaspace và thread stacks còn chiếm memory ngoài heap.

**“Tăng `-Xmx` luôn sửa OOME.”** Sai. Đôi khi làm container thiếu RAM native nặng hơn.

**“GC sẽ tự xóa static cache dù ứng dụng còn giữ references.”** Sai.

**“Fixed thread pool có queue giới hạn sẵn.”** Sai với cấu hình từ `Executors.newFixedThreadPool` thường gặp.

**“Streaming theo dòng chắc chắn không bao giờ có input lớn.”** Sai. Một dòng/token có thể dài bất thường.

**“Chỉ cần kiểm tra `Content-Length` là đã chặn mọi payload lớn.”** Sai. Input có thể khai báo thiếu/sai, và dữ liệu sau giải nén còn có thể lớn hơn.

**“Khởi tạo static class thất bại rồi truy cập lần nữa sẽ tự thử lại.”** Sai. Class có thể ở trạng thái erroneous.

**“Emergency buffer chắc chắn giúp ghi log và cứu JVM.”** Sai. Nó là best-effort, không xử lý nhiều nguồn OOME khác.

**“Restart là cách sửa memory leak.”** Sai. Restart là phục hồi instance; root cause vẫn phải sửa.

**“Heap dump có thể chia sẻ công khai để debug.”** Nguy hiểm. Dump có thể chứa dữ liệu nhạy cảm.

## 19. Bài tập tự kiểm tra

1. **OOME checked hay unchecked?** Unchecked, vì nằm dưới `Error`.
2. **`catch (Exception)` có bắt OOME?** Không.
3. **JVM có thể sống sau khi ném OOME?** Có thể, nhưng không bảo đảm phục vụ an toàn.
4. **OS OOM kill có cho Java catch OOME trước không?** Không nhất thiết; process có thể chết trực tiếp.
5. **Tăng `-Xmx` có chắc sửa direct/native OOME?** Không.
6. **`System.gc()` có dọn object còn tham chiếu từ static map không?** Không.
7. **Fixed thread pool thường có queue mặc định giới hạn không?** Không.
8. **Cache 3 entry có chắc dùng ít memory?** Không, payload mỗi entry có thể cực lớn.
9. **Làm sao tránh allocation từ một request tùy ý yêu cầu mảng 2 GB?** Validation kích thước, ngân sách trước cấp phát, streaming khi phù hợp.
10. **`try-with-resources` chạy trên OOME giả lập có bảo đảm chạy khi OS kill không?** Không.
11. **OOME trong static initialization có thể gây gì ở lần truy cập class tiếp theo?** `NoClassDefFoundError`.
12. **Tại sao OOME trong một request có thể ảnh hưởng request khác?** Heap/native resource và shared state là tài nguyên chung process.
13. **Bắt OOME rồi retry ngay có rủi ro gì?** Lặp memory pressure và lặp side effects chưa biết trạng thái.
14. **Tại sao không log toàn bộ JSON stack trace trong catch OOME?** Logging có thể cần cấp phát/resource không còn khả dụng.
15. **`Runtime.freeMemory()` có đại diện toàn bộ RAM vật lý trống không?** Không.
16. **Cần điều tra gì khi OOME thông báo Metaspace?** Class loaders, số class, metaspace limits và native usage.
17. **Có thể bảo đảm tạo được heap dump khi process bị OOM killer chấm dứt không?** Không.
18. **Retained size hữu ích cho điều tra leak ra sao?** Cho biết object nào giữ các object khác còn reachable.
19. **Nếu lỗi do array vượt VM limit, tăng GC có giúp chắc chắn?** Không.
20. **Tại sao cần supervisor ngoài JVM?** Để phát hiện và thay thế process khi code bên trong không còn chạy đáng tin.
21. **Restart có tự rollback giao dịch ngoài hệ thống không?** Không; cần transaction/idempotency/reconciliation.
22. **`OutOfMemoryError` và `StackOverflowError` có cùng class không?** Không, là hai subtype của `VirtualMachineError`.
23. **Nên ưu tiên giới hạn input/cache/queue hay chờ catch OOME?** Ưu tiên phòng tránh trước.
24. **Một `new OutOfMemoryError("simulated")` chứng minh điều gì?** Chỉ exception flow trong JVM bình thường, không phải recovery thật.

## 20. Tài liệu chính thức Java 17

- [Java SE 17 — OutOfMemoryError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html): ý nghĩa khi máy ảo không thể cấp phát bộ nhớ cần thiết.
- [Java SE 17 — VirtualMachineError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html): cây phân loại lỗi máy ảo.
- [Java SE 17 — Error](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html): các vấn đề nghiêm trọng mà ứng dụng thông thường không được kỳ vọng phục hồi.
- [Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `gc`, `maxMemory`, `freeMemory`.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue, giới hạn worker, rejection.
- [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): `removeEldestEntry`.
- [Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap và non-heap telemetry.
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): thông tin direct/mapped buffer pools.
- [Java Language Specification 17 — `11 Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked và lan truyền Throwable.
- [Java Language Specification 17 — `12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): class erroneous sau initialization failure.
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cleanup/suppressed exceptions.
- [Java SE 17 — java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xmx`, heap dumps, logging và HotSpot flags.
- [Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JVM diagnostics.

**Ghi nhớ:** `OutOfMemoryError` là **unchecked `VirtualMachineError`**, không chỉ là “heap đầy”. Việc JVM còn chạy hoặc handler bắt được nó **không bảo đảm** bộ nhớ, trạng thái khởi tạo class, các tài nguyên và dữ liệu nghiệp vụ đã phục hồi. Thiết kế đúng tập trung vào **budget, streaming, cache eviction, bounded concurrency, giám sát, chẩn đoán đúng vùng memory, fail-fast và cơ chế thay thế instance bên ngoài tiến trình**. Các ví dụ ném OOME giả lập chỉ là bài học về ngữ nghĩa Java, không phải chứng cứ rằng một JVM đã cạn memory sẽ phục vụ an toàn.
