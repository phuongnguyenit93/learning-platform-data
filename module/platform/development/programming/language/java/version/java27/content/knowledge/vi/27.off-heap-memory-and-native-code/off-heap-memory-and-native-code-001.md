# Foreign Function and Memory API và trường hợp sử dụng trong Java 27

**Foreign Function and Memory API (FFM API)** cho phép chương trình Java truy cập những vùng nhớ bên trong hoặc bên ngoài Java heap và tương tác với các hàm trong thư viện native, chẳng hạn thư viện C. Trong Java 27, các thành phần chính nằm ở package **`java.lang.foreign`** của module `java.base`.

FFM API được chuẩn hóa từ Java 22 (JEP 454); đây là một API hiện hành, không phải API incubator hoặc preview cần bật `--enable-preview`. Tuy nhiên, **một số thao tác liên kết/gọi mã native bị giới hạn quyền** vì có thể làm hỏng bộ nhớ hoặc khiến JVM gặp sự cố. Phải phân biệt các thao tác vùng nhớ thông thường với các thao tác native access bị hạn chế.

Bài thuộc chương **Bộ nhớ ngoài heap và mã native** trong lộ trình **Java 27 và các kiến thức liên quan**, tập trung vào điều kiện sử dụng, các khái niệm cốt lõi, ví dụ Java có thể chạy và những rủi ro phải kiểm soát. Chỉ sử dụng những cơ chế vẫn phù hợp với Java hiện đại.

## 1. FFM API giải quyết bài toán gì?

Trong một ứng dụng Java thông thường, đối tượng và mảng Java nằm trên heap do garbage collector (GC) quản lý. Nhưng có những tình huống cần làm việc trực tiếp với bộ nhớ native hoặc thư viện được viết bằng C/C++:

- Thư viện số học, đồ họa, nén, cơ sở dữ liệu, codec hoặc thư viện phần cứng cung cấp API dạng C.
- Hệ thống lưu trữ dữ liệu nhị phân có layout cố định gồm các trường, offset và alignment.
- Đọc những vùng dữ liệu lớn được ánh xạ trực tiếp từ tệp (*memory-mapped file*).
- Chia sẻ các vùng nhớ native với mã ở bên ngoài JVM, theo một giao thức rõ ràng.
- Tối ưu đường đi dữ liệu giữa mã Java và API native khi chi phí chuyển đổi đối tượng là đáng kể.

FFM API kết hợp **hai khả năng độc lập nhưng bổ trợ nhau**:

| Nhánh | Mục đích | Thành phần tiêu biểu |
|---|---|---|
| Foreign memory | Cấp phát, đọc, ghi, mô tả và quản lý vòng đời vùng nhớ | `MemorySegment`, `Arena`, `MemoryLayout`, `ValueLayout` |
| Foreign function | Tìm hàm native, mô tả chữ ký ABI, gọi từ Java hoặc cho native gọi lại Java | `Linker`, `SymbolLookup`, `FunctionDescriptor`, `MethodHandle` |

Một chương trình chỉ cần buffer off-heap có thể dùng **nhánh memory** mà không cần gọi một hàm C nào. Ngược lại, khi gọi hàm C nhận con trỏ, thường phải dùng cả hai nhánh để tạo và quản lý đối số trong native memory.

### 1.1. FFM không đồng nghĩa với “tắt GC”

Vùng nhớ native được cấp phát bởi `Arena` nằm ngoài Java heap, nhưng các **đối tượng Java mô tả vùng nhớ** vẫn tồn tại trên heap và GC vẫn hoạt động. FFM không làm mất nhu cầu quản lý tài nguyên; chỉ chuyển phần việc quản lý vòng đời vùng nhớ sang một cơ chế tường minh hơn.

Giảm áp lực heap trong một số workload không có nghĩa tổng bộ nhớ tiến trình giảm. Bộ nhớ off-heap vẫn chiếm RAM/virtual memory và có thể gây **out-of-memory ở mức hệ điều hành** nếu ứng dụng cấp phát quá mức.

### 1.2. Sơ đồ tổng quan

~~~text
          Ứng dụng Java 27
                  |
             java.lang.foreign
                  |
        +---------+----------+
        |                    |
   Foreign memory      Foreign function
        |                    |
     Arena                Linker
        |                    |
   MemorySegment       SymbolLookup
        |                    |
   MemoryLayout        FunctionDescriptor
        |                    |
   đọc / ghi bytes      MethodHandle downcall
        |                    |
        +----------+---------+
                   |
             Native memory
              / thư viện C
~~~

## 2. On-heap, off-heap và memory-mapped memory

Trước khi sử dụng FFM, cần phân biệt nơi lưu dữ liệu.

| Loại | Ví dụ | Ai quản lý vòng đời? | Trường hợp phù hợp |
|---|---|---|---|
| On-heap | `byte[]`, `int[]`, object thông thường | JVM/GC | Phần lớn dữ liệu nghiệp vụ |
| Heap-backed MemorySegment | `MemorySegment.ofArray(array)` | Mảng Java được giữ sống theo scope | Truy cập dữ liệu Java qua API segment |
| Off-heap MemorySegment | `Arena.ofConfined().allocate(...)` | Arena và lifecycle do ứng dụng xác định | Buffer native, tương tác với API C |
| Memory-mapped segment | `FileChannel.map(..., arena)` | File mapping gắn với scope của arena | Tệp nhị phân lớn, truy cập ngẫu nhiên |
| Direct ByteBuffer | `ByteBuffer.allocateDirect(...)` | Cơ chế quản lý buffer trực tiếp | NIO/I/O và API hiện có dùng ByteBuffer |

**MemorySegment là mô hình truy cập**, không đồng nghĩa lúc nào cũng off-heap. Một `MemorySegment` có thể trỏ tới mảng nằm trên heap hoặc một vùng native bên ngoài heap. Đặc tính truy cập và tương tác native phụ thuộc nguồn tạo segment.

### 2.1. Tại sao không chỉ dùng byte[] hoặc ByteBuffer?

Mảng Java đơn giản, an toàn và thường là lựa chọn tốt nhất nếu dữ liệu chỉ phục vụ mã Java.

`ByteBuffer` vẫn là API hiện hành và phù hợp với nhiều thư viện NIO. FFM hữu ích hơn khi cần:

- Mô tả một cấu trúc dữ liệu phức tạp theo `MemoryLayout`.
- Kiểm soát thời gian thu hồi vùng nhớ native bằng `Arena`.
- Tương tác với con trỏ và hàm C bằng `Linker`.
- Truy cập cùng loại dữ liệu thông qua heap/native segments với API tương đồng.
- Sử dụng con trỏ hoặc hàm callback native có hợp đồng rõ ràng.

Không nên đổi mọi `byte[]` sang off-heap chỉ vì cho rằng mã native luôn nhanh hơn. Trước tiên cần đo lường và xem xét chi phí cấp phát, copy, bounds checking, cleanup và complexity.

## 3. Các kiểu dữ liệu chính trong java.lang.foreign

| API | Chức năng |
|---|---|
| `Arena` | Cấp phát native memory, kiểm soát phạm vi sống và thread ownership |
| `MemorySegment` | Đại diện vùng byte liên tục, hỗ trợ đọc/ghi, slicing, copy, so sánh |
| `MemorySegment.Scope` | Mô tả lifetime/khả năng truy cập theo scope |
| `MemoryLayout` | Mô tả kích thước, alignment và cấu trúc vùng nhớ |
| `ValueLayout` | Mô tả giá trị đơn như int, long, float, địa chỉ |
| `SequenceLayout` | Nhiều phần tử cùng layout |
| `StructLayout`, `UnionLayout` | Mô tả tổng hợp kiểu struct và union |
| `PaddingLayout` | Mô tả khoảng đệm, thường dùng để đảm bảo alignment |
| `AddressLayout` | Mô tả giá trị địa chỉ/con trỏ native |
| `Linker` | Chuyển chữ ký hàm native thành method handle (downcall) hoặc upcall stub |
| `SymbolLookup` | Tìm địa chỉ hàm hoặc biến được export bởi thư viện |
| `FunctionDescriptor` | Mô tả tham số và kiểu trả về của hàm theo ABI |
| `MethodHandle` | Đại diện một lời gọi hàm; thuộc `java.lang.invoke` |

FFM không cần một dependency bên ngoài để dùng các API lõi. Với module Java tự khai báo, `java.lang.foreign` nằm trong `java.base` nên không cần thêm `requires` riêng cho FFM.

## 4. Ví dụ đầu tiên: cấp phát và truy cập mảng int off-heap

Đây là ví dụ **chạy hoàn chỉnh** chỉ dùng nhánh foreign memory, không cần load thư viện native hoặc gọi downcall.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class OffHeapIntegers {
    public static void main(String[] args) {
        int count = 10;
        long bytes = Math.multiplyExact(
                (long) count,
                ValueLayout.JAVA_INT.byteSize()
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocate(
                    bytes,
                    ValueLayout.JAVA_INT.byteAlignment()
            );

            for (int i = 0; i < count; i++) {
                numbers.setAtIndex(ValueLayout.JAVA_INT, i, i * 10);
            }

            long sum = 0;
            for (int i = 0; i < count; i++) {
                sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
            }

            System.out.println("Số byte = " + numbers.byteSize());
            System.out.println("Tổng = " + sum);
        } // Arena đóng và native memory được giải phóng.
    }
}
~~~

Kết quả:

~~~text
Số byte = 40
Tổng = 450
~~~

Giải thích:

1. `ValueLayout.JAVA_INT.byteSize()` là 4 byte; mười số nguyên dùng 40 byte.
2. `Math.multiplyExact` giúp phát hiện tràn số ở phép tính kích thước thay vì âm thầm cấp phát sai.
3. `Arena.ofConfined()` tạo scope được sở hữu bởi thread hiện tại.
4. `arena.allocate(bytes, alignment)` trả một segment native được căn chỉnh theo layout yêu cầu.
5. `setAtIndex` và `getAtIndex` dùng **chỉ số phần tử**, không phải offset byte.
6. Khi thoát try-with-resources, arena đóng, mọi segment do arena quản lý không còn được truy cập hợp lệ.

### 4.1. Lệnh biên dịch/chạy

~~~shell
javac --release 27 -encoding UTF-8 OffHeapIntegers.java
java OffHeapIntegers
~~~

Ví dụ này không gọi restricted native methods nên **không cần `--enable-native-access`** chỉ để cấp phát và truy cập off-heap segment qua `Arena`.

**Lưu ý:** Nếu đang sử dụng một JDK thấp hơn 27 để chạy thử độc lập, hãy chọn `--release` phù hợp với JDK thực tế. Các API FFM ổn định đã có từ Java 22.

## 5. Arena: chủ sở hữu vòng đời native memory

`Arena` kết hợp hai trách nhiệm: **cấp phát** và **giữ cho vùng nhớ hợp lệ trong một phạm vi sống nhất định**. Bốn loại arena quan trọng trong Java 27:

| Loại arena | Có thể đóng thủ công? | Nhiều thread cùng truy cập? | Vòng đời |
|---|---|---|---|
| `Arena.ofConfined()` | Có | Không, chỉ owner thread | Đến khi owner đóng |
| `Arena.ofShared()` | Có | Có | Đến khi đóng sau khi hoàn tất truy cập |
| `Arena.ofAuto()` | Không | Có | Do GC quản lý, thời điểm thu hồi không xác định |
| `Arena.global()` | Không | Có | Tồn tại đến hết vòng đời tiến trình |

### 5.1. Confined arena: ưu tiên cho công việc cục bộ

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(1024);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);
}
// Vùng nhớ đã được giải phóng, không dùng segment nữa.
~~~

Ưu điểm:

- Vòng đời rõ ràng.
- Được dùng cùng try-with-resources.
- Không có tranh chấp truy cập giữa nhiều thread.
- Kiểm soát thời điểm thu hồi dễ hiểu.

Đây thường là điểm khởi đầu phù hợp khi một tác vụ đơn luồng cần buffer native tạm.

### 5.2. Shared arena: dùng được giữa các thread, nhưng không tự đồng bộ dữ liệu

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SharedArenaExample {
    public static void main(String[] args)
            throws InterruptedException {

        try (Arena arena = Arena.ofShared()) {
            MemorySegment segment = arena.allocate(
                    ValueLayout.JAVA_LONG
            );

            Thread writer = Thread.ofPlatform().start(() ->
                    segment.set(ValueLayout.JAVA_LONG, 0, 123L)
            );

            // join tạo thứ tự hoàn thành/visibility cho ví dụ này.
            writer.join();

            System.out.println(
                    segment.get(ValueLayout.JAVA_LONG, 0)
            ); // 123
        }
    }
}
~~~

Shared arena cho phép các thread khác nhau truy cập segment và có thể đóng từ thread bất kỳ, nhưng **không tự tạo mutual exclusion hoặc làm các phép đọc/ghi cạnh tranh trở nên có thứ tự**.

Nếu hai thread cùng thực hiện read-modify-write trên một vị trí, cần thiết kế memory ordering/atomicity phù hợp, chẳng hạn dùng `VarHandle` với các access mode thích hợp, lock hoặc phân vùng dữ liệu. Với native memory, còn phải chú ý những yêu cầu memory ordering của thư viện native; thông thường Java Memory Model cho dữ liệu trên heap không tự bảo đảm mọi tương tác với mã C.

### 5.3. Automatic arena: GC quản lý, không có thời điểm giải phóng xác định

~~~java
MemorySegment segment = Arena.ofAuto().allocate(4096);
segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
~~~

Arena tự động có thể được thu hồi sau khi arena và những segment liên quan không còn reachable. **Không dựa vào thời điểm GC cụ thể** để quyết định khi nào bộ nhớ đã được giải phóng.

Vì không được đóng thủ công, automatic arena không phù hợp nếu cần bảo đảm giải phóng ngay cuối request hoặc transaction.

### 5.4. Global arena: không dùng cho cấp phát lặp lại không giới hạn

~~~java
MemorySegment segment = Arena.global().allocate(256);
~~~

Vùng nhớ được cấp phát qua global arena **không được giải phóng bằng việc đóng arena** và tồn tại cho đến hết vòng đời tiến trình. Chỉ phù hợp cho tài nguyên cần tồn tại toàn chương trình với kích thước đã kiểm soát.

**Không dùng global arena làm vùng cấp phát mặc định cho mỗi HTTP request**, vì sẽ tích lũy bộ nhớ native theo thời gian.

## 6. Ba bảo đảm truy cập: bounds, lifetime và confinement

FFM bảo vệ những thao tác Java trực tiếp qua `MemorySegment` bằng các kiểm tra:

1. **Spatial safety (bounds):** offset hoặc độ dài truy cập không được vượt khỏi phạm vi segment.
2. **Temporal safety (lifetime):** không được truy cập vùng nhớ sau khi scope đã đóng.
3. **Thread confinement:** segment thuộc confined arena chỉ cho phép owner thread truy cập.

### 6.1. Truy cập quá biên

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(4);

    segment.set(ValueLayout.JAVA_INT, 0, 42);

    // Thao tác sau vượt quá kích thước segment:
    // segment.get(ValueLayout.JAVA_INT, 4);
    // -> IndexOutOfBoundsException
}
~~~

Một `int` cần 4 byte. Với segment dài 4 byte, offset 0 là hợp lệ; offset 4 sẽ yêu cầu đọc các byte ở ngoài đoạn [0, 4).

### 6.2. Use-after-close bị ngăn ở lớp MemorySegment

~~~java
MemorySegment segment;

try (Arena arena = Arena.ofConfined()) {
    segment = arena.allocate(ValueLayout.JAVA_INT);
    segment.set(ValueLayout.JAVA_INT, 0, 42);
}

try {
    segment.get(ValueLayout.JAVA_INT, 0);
    throw new AssertionError("Không được truy cập sau close");
} catch (IllegalStateException expected) {
    System.out.println("Segment đã hết thời gian sống");
}
~~~

Kiểm tra này có giá trị cho các thao tác segment hợp lệ của Java. Nó **không đảm bảo một thư viện native sẽ tôn trọng** chiều dài hay lifetime của con trỏ được trao cho nó.

### 6.3. Truy cập sai thread

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(8);

    Thread other = Thread.ofPlatform().start(() -> {
        try {
            segment.get(ValueLayout.JAVA_LONG, 0);
        } catch (java.lang.WrongThreadException expected) {
            System.out.println("Sai owner thread");
        }
    });

    other.join();
}
~~~

Ví dụ này cần đặt trong phương thức có thể khai báo `throws InterruptedException`. Khi một thread khác truy cập segment thuộc confined arena, API kiểm tra và có thể ném `WrongThreadException`.

**Điểm giới hạn an toàn:** một khi vùng nhớ native đã được trao cho một hàm C, mã C có thể làm sai con trỏ, vượt biên, ghi vào vùng đã giải phóng hoặc crash JVM. Do đó, FFM cải thiện an toàn ở ranh giới Java nhưng **không làm mã native trở nên memory-safe**.

## 7. ValueLayout: đọc, ghi, alignment và byte order

`ValueLayout` mô tả kiểu giá trị, kích thước, alignment và thứ tự byte. Ví dụ:

| Layout | Carrier Java | Số byte |
|---|---|---|
| `JAVA_BYTE` | `byte` | 1 |
| `JAVA_SHORT` | `short` | 2 |
| `JAVA_INT` | `int` | 4 |
| `JAVA_LONG` | `long` | 8 |
| `JAVA_FLOAT` | `float` | 4 |
| `JAVA_DOUBLE` | `double` | 8 |
| `ADDRESS` | `MemorySegment` | Phụ thuộc kiến trúc, thường 8 trên 64-bit |

Các hằng layout Java dùng **native byte order** theo nền tảng. Không được suy rằng mọi file/network protocol dùng cùng byte order với máy.

### 7.1. Phân biệt byte offset và index

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment numbers =
            arena.allocate(ValueLayout.JAVA_INT, 3);

    numbers.setAtIndex(ValueLayout.JAVA_INT, 0, 100);
    numbers.setAtIndex(ValueLayout.JAVA_INT, 1, 200);
    numbers.setAtIndex(ValueLayout.JAVA_INT, 2, 300);

    int a = numbers.getAtIndex(ValueLayout.JAVA_INT, 1); // 200
    int b = numbers.get(ValueLayout.JAVA_INT, 4);        // 200

    System.out.println(a == b); // true
}
~~~

`getAtIndex(..., 1)` truy cập phần tử thứ hai; `get(..., 4)` truy cập offset 4 byte. Nhầm hai hệ tọa độ sẽ gây lỗi dữ liệu hoặc truy cập ngoài biên.

### 7.2. Chọn byte order tường minh cho định dạng nhị phân

~~~java
import java.nio.ByteOrder;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment packet = arena.allocate(4);

    ValueLayout.OfInt bigEndian =
            ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

    packet.set(bigEndian, 0, 0x01020304);

    for (int i = 0; i < 4; i++) {
        int value = Byte.toUnsignedInt(
                packet.get(ValueLayout.JAVA_BYTE, i)
        );
        System.out.printf("%02x ", value);
    }
    System.out.println();
    // 01 02 03 04
}
~~~

Với network protocol, metadata từ file hay thiết bị, **endianness phải theo đặc tả của dữ liệu**, không theo máy đang chạy.

### 7.3. Alignment không phải tùy chọn hình thức

`ValueLayout.JAVA_INT` có alignment 4 byte. Một truy cập kiểu int ở địa chỉ/offset không đáp ứng alignment có thể bị từ chối ngay từ API Java. Khi dữ liệu trên wire cố ý đóng gói không căn chỉnh, có thể sử dụng layout `JAVA_INT_UNALIGNED` hoặc layout được cấu hình thích hợp, nhưng cần hiểu hiệu quả và ràng buộc kiến trúc.

Không tự đặt alignment thấp cho một struct C chỉ để làm code chạy được; phải theo ABI chính xác của thư viện native.

## 8. MemoryLayout: mô tả array, struct và padding

Một `MemoryLayout` nói rõ cách các trường nằm trong vùng nhớ. Điều này đặc biệt hữu ích khi trao đổi cấu trúc nhị phân cố định hoặc ánh xạ C struct.

### 8.1. SequenceLayout cho mảng đồng nhất

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.ValueLayout;

public class SequenceLayoutDemo {
    public static void main(String[] args) {
        SequenceLayout layout = MemoryLayout.sequenceLayout(
                4, ValueLayout.JAVA_INT
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment values = arena.allocate(layout);

            for (int i = 0; i < 4; i++) {
                values.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
            }

            System.out.println(layout.byteSize()); // 16
            System.out.println(
                    values.getAtIndex(ValueLayout.JAVA_INT, 3)
            ); // 4
        }
    }
}
~~~

### 8.2. StructLayout và padding

Xét cấu trúc C trên **ABI có sizeof(int) = 4 và alignof(int) = 4**:

~~~c
struct Record {
    char kind;
    int value;
};
~~~

Một layout thông dụng của ABI này là:

~~~text
Offset  Size  Trường
0       1     kind
1       3     padding
4       4     value
Tổng    8 byte
~~~

Trong Java:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class StructLayoutDemo {
    public static void main(String[] args) {
        StructLayout recordLayout = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("kind"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("value")
        );

        long valueOffset = recordLayout.byteOffset(
                groupElement("value")
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(recordLayout);

            record.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
            record.set(ValueLayout.JAVA_INT, valueOffset, 1200);

            System.out.println(recordLayout.byteSize()); // 8
            System.out.println(valueOffset);             // 4
            System.out.println(
                    record.get(ValueLayout.JAVA_INT, valueOffset)
            ); // 1200
        }
    }
}
~~~

**Không phải mọi C ABI đều có cùng padding.** Trên nền tảng khác, cách căn chỉnh một struct có thể thay đổi. Khi làm việc với thư viện C thực tế, layout phải khớp chính xác compiler, ABI, kiến trúc, packing và kiểu dữ liệu của thư viện.

Không nên suy đoán dựa trên Java primitive size nếu C struct sử dụng kiểu như `long`, `size_t`, bitfield, packed struct hoặc union.

### 8.3. Layout path và VarHandle

`MemoryLayout` cho phép tìm offset và tạo `VarHandle` để thao tác một field theo tên:

~~~java
var valueHandle = recordLayout.varHandle(
        groupElement("value")
);

valueHandle.set(record, 0L, 500);
int result = (int) valueHandle.get(record, 0L);
System.out.println(result); // 500
~~~

Đoạn này dùng các biến `recordLayout` và `record` từ ví dụ trước, trong khi arena còn sống. `0L` là offset cơ sở của struct. Đối với layout lồng nhau hoặc sequence layout, tọa độ của VarHandle có thể có thêm index; cần đọc method type và layout path thay vì đoán thứ tự đối số.

## 9. Slice, copy và view của MemorySegment

Các thao tác trên segment cho phép làm việc với một phần của vùng nhớ mà không nhất thiết tạo thêm native allocation.

### 9.1. asSlice tạo view, không sở hữu bộ nhớ riêng

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16);

    MemorySegment firstHalf = segment.asSlice(0, 8);
    MemorySegment secondHalf = segment.asSlice(8, 8);

    firstHalf.set(ValueLayout.JAVA_LONG, 0, 10L);
    secondHalf.set(ValueLayout.JAVA_LONG, 0, 20L);

    System.out.println(
            segment.get(ValueLayout.JAVA_LONG, 8)
    ); // 20
}
~~~

Slice dùng chung backing region và scope với segment gốc. Nếu arena đóng, **slice cũng hết hiệu lực**. Đừng trả slice ra ngoài phương thức khi arena bị đóng ở cuối phương thức, rồi kỳ vọng caller vẫn có thể truy cập.

### 9.2. Copy dữ liệu giữa các segment

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment source = arena.allocate(8);
    MemorySegment target = arena.allocate(8);

    source.set(ValueLayout.JAVA_LONG, 0, 12345L);

    MemorySegment.copy(source, 0, target, 0, 8);

    System.out.println(
            target.get(ValueLayout.JAVA_LONG, 0)
    ); // 12345
}
~~~

`MemorySegment.copy` cần cả nguồn và đích hợp lệ, đủ phạm vi và không vi phạm thread-confinement. Việc copy byte không tự giải quyết chuyện **data race** nếu có thread khác đồng thời sửa dữ liệu.

### 9.3. Heap segment không nhất thiết copy mảng

~~~java
int[] values = {10, 20, 30};
MemorySegment heapSegment = MemorySegment.ofArray(values);

heapSegment.setAtIndex(ValueLayout.JAVA_INT, 1, 99);

System.out.println(values[1]); // 99
~~~

Segment này là **view trên mảng Java**, không phải buffer native mới được cấp phát. Thay đổi qua segment tác động lên mảng và ngược lại.

### 9.4. Tương tác với ByteBuffer

FFM có `MemorySegment.ofBuffer(buffer)` và `segment.asByteBuffer()` để tích hợp với mã sử dụng NIO. Tuy nhiên cần chú ý:

- Một segment xuất phát từ `ByteBuffer` có thể là heap hoặc native tùy backing buffer.
- Segment được tạo từ buffer tuân theo vị trí `position`/`limit` tại lúc tạo.
- Khi tạo ByteBuffer view từ segment, lifetime của segment vẫn quan trọng; đừng truy cập buffer sau khi arena đóng.
- Tránh giả định mọi segment có thể biểu diễn bằng một ByteBuffer nếu kích thước vượt giới hạn của API ByteBuffer.

## 10. Memory-mapped file: ánh xạ dữ liệu từ tệp vào một segment

Trong các ứng dụng phân tích tệp nhị phân, việc đọc bằng `Files.readAllBytes(...)` có thể không phù hợp nếu tệp rất lớn. Java 27 hỗ trợ ánh xạ một phần tệp thành `MemorySegment` thông qua `FileChannel.map(..., Arena)`.

Ví dụ **chạy độc lập** này ánh xạ một tệp nhỏ để minh họa cú pháp:

~~~java
import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("ffm-demo-", ".bin");

        try {
            Files.write(file, new byte[] {
                    1, 2, 3, 4, 5, 6, 7, 8
            });

            try (FileChannel channel = FileChannel.open(
                        file, StandardOpenOption.READ);
                 Arena arena = Arena.ofConfined()) {

                MemorySegment mapped = channel.map(
                        FileChannel.MapMode.READ_ONLY,
                        0,
                        channel.size(),
                        arena
                );

                int first = Byte.toUnsignedInt(
                        mapped.get(ValueLayout.JAVA_BYTE, 0)
                );

                int last = Byte.toUnsignedInt(
                        mapped.get(ValueLayout.JAVA_BYTE, 7)
                );

                System.out.println("First = " + first);
                System.out.println("Last  = " + last);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Kết quả:

~~~text
First = 1
Last  = 8
~~~

Ánh xạ file cho phép truy cập một vùng dữ liệu như bộ nhớ; hệ điều hành có thể nạp các trang vào RAM theo nhu cầu. **Không có nghĩa toàn bộ dữ liệu được nạp sẵn hoặc không còn I/O**.

### 10.1. Khi nào nên dùng file mapping?

Phù hợp để cân nhắc khi:

- Tệp rất lớn, cần truy cập ngẫu nhiên đến các record theo offset.
- Có nhiều lượt đọc trên cùng một vùng dữ liệu.
- Muốn đọc header/index/record nhị phân mà không tự xây dựng lớp đệm quá phức tạp.

Không nhất thiết phù hợp khi:

- Chỉ đọc tuần tự một lần trên tệp nhỏ.
- Dữ liệu đến từ một network stream, không phải file.
- Cần logic transaction/locking phức tạp mà file mapping không cung cấp.
- Tệp có thể bị sửa/truncate đồng thời bởi tiến trình khác.

Nếu mapping có quyền ghi, cần hiểu rõ `force()`, flush, độ bền dữ liệu, thời điểm đóng scope và tính nhất quán với thay đổi từ tiến trình khác. Memory mapping không tự biến thao tác cập nhật thành transaction.

### 10.2. Quy tắc vòng đời

Mapped segment gắn với arena truyền vào `FileChannel.map(...)`. Khi arena đóng, mapping liên quan không còn hợp lệ cho truy cập Java. Không giữ tham chiếu segment để sử dụng sau khi đóng.

Cần phối hợp vòng đời với file handle, tài nguyên hệ điều hành và những thread đang truy cập segment. Tệp có thể bị thu nhỏ hoặc thay đổi ngoài JVM; FFM bounds check không phải cơ chế khóa tệp thay cho ứng dụng.

## 11. Từ Java gọi hàm native: downcall

**Downcall** là lời gọi từ Java sang một hàm trong thư viện native.

Các bước:

1. Tạo `Linker` cho ABI của nền tảng.
2. Tìm symbol bằng `SymbolLookup`.
3. Xác định chính xác chữ ký hàm C qua `FunctionDescriptor`.
4. Tạo `MethodHandle` bằng `Linker.downcallHandle(...)`.
5. Chuẩn bị các tham số native, thường là `MemorySegment`.
6. Gọi `MethodHandle` với carrier Java tương ứng.
7. Giải phóng tài nguyên theo vòng đời arena và hợp đồng thư viện C.

~~~text
Java method
   |
   v
SymbolLookup.find("function_name")
   |
   v
FunctionDescriptor [return layout, arguments]
   |
   v
Linker.downcallHandle(...)
   |
   v
MethodHandle.invokeExact(...)
   |
   v
C ABI / native function
~~~

### 11.1. FunctionDescriptor mô tả kiểu native, không chỉ kiểu Java

Hàm C:

~~~c
size_t strlen(const char *s);
~~~

có một tham số con trỏ và trả về `size_t`. Để tạo downcall, cần mô tả **ABI type** của `size_t` và của con trỏ. Trên ABI 64-bit phổ biến, `size_t` tương ứng một giá trị 64-bit, còn con trỏ dùng `ValueLayout.ADDRESS`.

Điểm quan trọng: **C `long` không phải lúc nào cũng có kích thước như Java `long`**. Ví dụ trên Windows 64-bit, `long` trong mô hình dữ liệu thông dụng dài 32 bit, trong khi Java `long` là 64 bit. Đừng map tất cả C `long` sang `ValueLayout.JAVA_LONG` chỉ vì tên giống nhau.

`Linker.canonicalLayouts()` cung cấp những layout tương ứng với các kiểu C thông dụng của ABI hiện tại, chẳng hạn `size_t`, `long` và `int`. Hãy sử dụng metadata ABI thay vì đoán khi xây binding thư viện có tính di động.

## 12. Ví dụ hoàn chỉnh: gọi C strlen từ Java 27

Ví dụ sau phù hợp với các nền tảng **64-bit có hàm `strlen` xuất hiện trong default symbol lookup của native linker**. Đây là một minh họa downcall tương tự ví dụ trong tài liệu JDK; khả năng tìm được symbol và chi tiết ABI vẫn phụ thuộc OS/JDK.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class NativeStrlenDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        SymbolLookup symbols = linker.defaultLookup();
        MemorySegment function = symbols.findOrThrow("strlen");

        // Chữ ký minh họa cho ABI 64-bit:
        // size_t strlen(const char *text);
        FunctionDescriptor signature = FunctionDescriptor.of(
                ValueLayout.JAVA_LONG,
                ValueLayout.ADDRESS
        );

        MethodHandle strlen = linker.downcallHandle(
                function,
                signature
        );

        try (Arena arena = Arena.ofConfined()) {
            // UTF-8 và byte kết thúc NUL.
            MemorySegment text = arena.allocateFrom("Hello FFM");

            long length = (long) strlen.invokeExact(text);

            System.out.println("Số byte = " + length);
        }
    }
}
~~~

Kết quả mong đợi trên nền tảng phù hợp:

~~~text
Số byte = 9
~~~

Giải thích:

- `Linker.nativeLinker()` dùng ABI native của hệ thống.
- `defaultLookup()` tìm trong tập thư viện phổ biến mà linker công bố, không có cam kết mọi symbol đều xuất hiện trên mọi OS.
- `findOrThrow("strlen")` trả một **symbol address** ở dạng segment; nếu không tìm được, nó ném ngoại lệ.
- `FunctionDescriptor.of(JAVA_LONG, ADDRESS)` mô tả kiểu trả về 64-bit và tham số con trỏ trong ABI được minh họa.
- `downcallHandle` tạo một method handle gọi hàm native; đây là **restricted method**.
- `arena.allocateFrom("Hello FFM")` tạo chuỗi C null-terminated theo UTF-8.
- `invokeExact(text)` gọi native function với chữ ký chính xác, trả về Java `long`.

**Lưu ý Unicode:** `strlen` đếm **byte trước NUL**, không đếm code point hay ký tự Java. Nếu truyền một chuỗi tiếng Việt UTF-8, số byte có thể lớn hơn `String.length()`. Nếu chuỗi Java chứa ký tự NUL ở giữa, C `strlen` chỉ nhìn phần trước byte NUL đầu tiên.

### 12.1. Biên dịch và chạy với quyền native access

~~~shell
javac --release 27 -encoding UTF-8 NativeStrlenDemo.java

java --enable-native-access=ALL-UNNAMED NativeStrlenDemo
~~~

`ALL-UNNAMED` cho phép những class chạy trên **class path** gọi restricted native methods. Khi triển khai ứng dụng dưới dạng named module, nên cấp quyền hạn chế hơn theo tên module:

~~~shell
java --enable-native-access=com.example.ffi --module-path mods --module com.example.ffi/com.example.ffi.Main
~~~

Lệnh module là cú pháp minh họa cho một ứng dụng modular đã được đóng gói sẵn; nó không dùng trực tiếp class `NativeStrlenDemo` ở default package.

**Không cần `--enable-preview` để dùng FFM API ổn định.** Quyền native access và bật preview là hai cơ chế hoàn toàn khác nhau.

### 12.2. Khác biệt giữa byte count và character count

~~~java
String text = "Việt Nam";

int javaUnits = text.length();
int utf8Bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8
).length;

System.out.println(javaUnits);
System.out.println(utf8Bytes);
~~~

Số lượng UTF-16 code units và số byte UTF-8 có thể khác nhau. Việc ứng dụng truyền chuỗi cho C cần tuân thủ **encoding và kiểu chuỗi mà API native yêu cầu**: không phải thư viện C nào cũng nhận UTF-8 null-terminated.

## 13. Portability: ABI và symbol phải khớp nền tảng

Một binding native có thể chạy trên Linux x64 nhưng không chạy trên Windows x64 hoặc ARM64 nếu:

- Tên thư viện và quy tắc load khác nhau.
- Tên symbol thay đổi hoặc thư viện không export symbol.
- Kiểu C `long`, `size_t`, `wchar_t` có kích thước khác.
- Struct có padding, bitfield, alignment khác.
- Calling convention, variadic arguments hoặc C++ name mangling khác.
- Native library được biên dịch với compiler/runtime không tương thích.

### 13.1. Kiểm tra canonical layout theo linker

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.util.Map;

public class NativeLayoutInfo {
    public static void main(String[] args) {
        Linker linker = Linker.nativeLinker();

        Map<String, MemoryLayout> layouts =
                linker.canonicalLayouts();

        System.out.println("size_t = "
                + layouts.get("size_t"));
        System.out.println("long = "
                + layouts.get("long"));
        System.out.println("int = "
                + layouts.get("int"));
    }
}
~~~

Khi xây `FunctionDescriptor`, cần dùng layout đúng carrier Java theo ABI. `MethodHandle.invokeExact` kiểm tra **method type chính xác**; nếu carrier không trùng, có thể gặp `WrongMethodTypeException` hoặc lỗi tạo handle.

Với thư viện C phức tạp, đừng viết mọi binding bằng tay chỉ dựa trên header đọc lướt. Cần kiểm tra đúng header phiên bản, ABI, macro, struct layout và symbol thực tế.

### 13.2. Library lookup theo tên hoặc path

~~~java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lookup = SymbolLookup.libraryLookup(
            "example-native-library",
            arena
    );

    MemorySegment address =
            lookup.findOrThrow("example_function");

    // Cần FunctionDescriptor chính xác trước khi downcall.
}
~~~

Đây là đoạn minh họa API: tên thư viện và symbol chỉ là placeholder. `libraryLookup` là **restricted method**; cách phân giải tên thư viện do OS/JDK quyết định. Đừng cho input không tin cậy trực tiếp kiểm soát tên/path thư viện sẽ load.

Một overload khác nhận `Path` để trỏ đến một file thư viện cụ thể; nếu dùng, phải kiểm tra đường dẫn nguồn gốc thư viện, chữ ký/checksum, quyền file và kiến trúc tương thích.

### 13.3. defaultLookup, libraryLookup và loaderLookup khác nhau

| Lookup | Nguồn symbol |
|---|---|
| `linker.defaultLookup()` | Tập thư viện native phổ biến mà linker công bố |
| `SymbolLookup.libraryLookup(name/path, arena)` | Thư viện chỉ định, được load và gắn lifetime với arena |
| `SymbolLookup.loaderLookup()` | Những thư viện đã được load thông qua JNI và liên kết với class loader của caller |

Không giả định một thư viện được load bởi `libraryLookup` sẽ tự động xuất hiện trong `loaderLookup`. `libraryLookup` và `loaderLookup` có phạm vi và vòng đời khác nhau.

## 14. Restricted methods và --enable-native-access

Một số thao tác FFM có thể khiến JVM mất tính toàn vẹn nếu người gọi cung cấp thông tin sai. Vì vậy, Java 27 áp dụng cơ chế **restricted native access** cho những phương thức quan trọng.

Ví dụ:

- `Linker.downcallHandle(...)`: tạo entry point để gọi một hàm native.
- `Linker.upcallStub(...)`: tạo callback function pointer cho native gọi Java.
- `SymbolLookup.libraryLookup(...)`: load thư viện native.
- `MemorySegment.reinterpret(...)`: thay đổi cách hiểu phạm vi/vòng đời con trỏ.
- `AddressLayout.withTargetLayout(...)`: cho phép dereference con trỏ theo target layout.
- `System.load(...)` và `System.loadLibrary(...)` cũng liên quan đến cơ chế kiểm soát native access.

Ngược lại, các thao tác thông thường như `Arena.ofConfined()`, `arena.allocate(...)`, `MemorySegment.get(...)`, `set(...)`, `asSlice(...)` **không phải cứ dùng là cần bật native access**.

### 14.1. Bật quyền một cách có chủ đích

Chương trình trên class path:

~~~shell
java --enable-native-access=ALL-UNNAMED NativeStrlenDemo
~~~

Named module:

~~~shell
java --enable-native-access=com.example.ffi --module-path mods --module com.example.ffi
~~~

Ưu tiên cấp quyền cho **module cụ thể** thay vì `ALL-UNNAMED` nếu có thể. Đây là một hàng rào tin cậy: FFM restricted methods cho phép tương tác với mã native bên ngoài các bảo đảm an toàn thông thường của Java.

### 14.2. Hành vi khi không cấp quyền

Tài liệu Java SE 27 mô tả `--illegal-native-access` với các chế độ:

| Giá trị | Hành vi |
|---|---|
| `allow` | Cho phép thao tác không được cấp quyền, không cảnh báo |
| `warn` | Cho phép nhưng cảnh báo; là chế độ mặc định được tài liệu Java 27 công bố |
| `deny` | Không cho thao tác; có thể ném `IllegalCallerException` |

`deny` được dự kiến trở thành mặc định ở một bản JDK sau này. **Không viết ứng dụng dựa trên việc cảnh báo có nghĩa thao tác sẽ luôn được cho phép.** Trong build và triển khai, cấp native access rõ ràng cho code thực sự cần và có thể thử với:

~~~shell
java --illegal-native-access=deny --enable-native-access=ALL-UNNAMED NativeStrlenDemo
~~~

Đây là cách kiểm tra ứng dụng đã liệt kê đầy đủ những vùng code cần quyền native hay chưa, không phải lời khuyên bật `ALL-UNNAMED` cho mọi ứng dụng.

### 14.3. Bật quyền không khiến native code an toàn

`--enable-native-access` là **cho phép sử dụng khả năng rủi ro**, không phải chế độ bảo vệ bộ nhớ. Khi một thư viện C nhận con trỏ không hợp lệ, ghi vượt vùng nhớ hoặc dùng sai ABI, ứng dụng vẫn có thể:

- Crash toàn JVM.
- Ghi hỏng native heap hoặc dữ liệu trong tiến trình.
- Thực thi hành vi ngoài dự kiến.
- Rò rỉ địa chỉ/buffer có dữ liệu nhạy cảm.

Chỉ load thư viện từ nguồn được tin cậy và có quy trình phát hành/kiểm định phù hợp. Với code native không tin cậy, phân tách tiến trình (process isolation) có thể là biện pháp bảo vệ mạnh hơn so với chỉ kiểm tra trong một JVM.

## 15. Upcall: cho mã native gọi lại Java

**Upcall** là chiều ngược với downcall: mã native nhận một function pointer trỏ tới đoạn mã Java thông qua một **upcall stub** do `Linker` tạo.

~~~text
                   Downcall
Java --------------------------------> Native function
Java <-------------------------------- Native callback
                   Upcall
~~~

Tình huống:

- Thư viện C hỗ trợ callback xử lý từng record.
- Hàm native nhận comparator như `qsort`.
- API native báo tiến độ hoặc sự kiện cho Java.

### 15.1. Tạo stub cho hàm comparator

Ví dụ khái niệm, minh họa chữ ký:

~~~c
int compare(const int *left, const int *right);
~~~

Java có thể tạo callback với `MethodHandle` và `FunctionDescriptor` tương thích. Ví dụ này chỉ **tạo stub**, không giả định thư viện nào đã gọi nó:

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class NativeCallbackExample {
    public static int compare(
            MemorySegment left, MemorySegment right) {

        int a = left.get(ValueLayout.JAVA_INT, 0);
        int b = right.get(ValueLayout.JAVA_INT, 0);

        return Integer.compare(a, b);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        MethodHandle comparator =
                MethodHandles.lookup().findStatic(
                        NativeCallbackExample.class,
                        "compare",
                        MethodType.methodType(
                                int.class,
                                MemorySegment.class,
                                MemorySegment.class
                        )
                );

        AddressLayout intPointer =
                ValueLayout.ADDRESS.withTargetLayout(
                        ValueLayout.JAVA_INT
                );

        FunctionDescriptor callbackDescriptor =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        intPointer,
                        intPointer
                );

        try (Arena arena = Arena.ofShared()) {
            MemorySegment callbackPointer =
                    linker.upcallStub(
                            comparator, callbackDescriptor, arena
                    );

            System.out.println(
                    "Callback address: "
                    + callbackPointer.address()
            );

            // Thực tế sẽ truyền callbackPointer cho hàm C.
            // Không cho native giữ con trỏ sau khi arena đóng.
        }
    }
}
~~~

Chạy cần cấp native access do `upcallStub` và `withTargetLayout` bị hạn chế:

~~~shell
javac --release 27 -encoding UTF-8 NativeCallbackExample.java
java --enable-native-access=ALL-UNNAMED NativeCallbackExample
~~~

Những lưu ý nghiêm trọng:

- Cần dùng **đúng ABI** và descriptor cho callback.
- Upcall có thể được thực thi bởi một thread do thư viện native tạo; shared arena cho phép truy cập stub từ nhiều thread nhưng không làm trạng thái trong callback tự thread-safe.
- Nếu callback Java ném ngoại lệ không được xử lý, **JVM có thể chấm dứt đột ngột** theo hợp đồng của `Linker.upcallStub`.
- Callback cần bắt lỗi, biến lỗi thành giá trị kết quả hoặc trạng thái mà native API hiểu, không để exception thoát sang C.
- Không đóng arena trước khi chắc chắn native library không còn giữ hoặc gọi function pointer.

Ví dụ tạo stub **không phải** hướng dẫn dùng comparator này trực tiếp cho mọi C library; cần đối chiếu typedef callback và alignment/kiểu dữ liệu thực tế.

## 16. Con trỏ native và trách nhiệm quản lý ownership

Trong C API, một hàm có thể:

1. Nhận con trỏ nhưng **chỉ đọc** trong khi lời gọi chưa kết thúc.
2. Giữ con trỏ lại để xử lý **bất đồng bộ sau khi hàm trả về**.
3. Cấp phát một vùng nhớ và trả con trỏ cho caller.
4. Yêu cầu caller trả vùng nhớ bằng một hàm giải phóng riêng.
5. Trả con trỏ tới dữ liệu thuộc sở hữu của thư viện, **không được tự free**.

Đây là các hợp đồng **khác nhau**, không thể suy ra từ kiểu `MemorySegment` đơn thuần.

### 16.1. Ownership matrix

| C API | Ownership | Điều ứng dụng Java cần làm |
|---|---|---|
| Hàm chỉ dùng buffer trong lời gọi | Caller giữ buffer | Arena phải sống đến khi downcall trả về |
| Hàm giữ pointer để xử lý async | Caller hoặc thư viện theo hợp đồng | Giữ arena còn sống tới khi native xác nhận hoàn tất |
| Hàm trả pointer do malloc cấp phát | Có thể caller phải free | Gọi đúng hàm native giải phóng, không tự đoán |
| Hàm trả pointer tới bộ nhớ nội bộ | Thư viện sở hữu | Không free; không dùng sau khi thư viện hủy/đổi dữ liệu |
| Hàm giữ callback pointer | Stub do Java tạo | Giữ arena và callback state sống đến khi unregister thành công |

Một lỗi điển hình là trả địa chỉ của một segment trong confined arena cho native code và đóng arena ngay khi lời gọi Java kết thúc, trong khi native vẫn đang lưu pointer. **FFM không có phép màu đảm bảo an toàn cho con trỏ mà mã C giữ lại.**

### 16.2. Reinterpret không phải phép xác thực con trỏ

Symbol address, con trỏ từ native function hoặc callback pointer có thể là segment dài 0 byte. Một số API cho phép dùng `reinterpret` hoặc `AddressLayout.withTargetLayout` để tạo khả năng dereference theo kích thước được khai báo.

Đây là **restricted operation** vì Java không thể kiểm chứng pointer đó thực sự trỏ tới vùng nhớ hợp lệ hoặc có đủ kích thước. Không dùng `reinterpret(Long.MAX_VALUE)` hoặc mở rộng con trỏ theo metadata không tin cậy để “bỏ kiểm tra bounds”.

Trước khi dereference pointer, phải biết rõ:

- Nó có thể là NULL không?
- Vùng nhớ dài bao nhiêu byte?
- Alignment và byte order nào?
- Ai sở hữu vùng nhớ và khi nào giải phóng?
- Một thread khác có thể sửa/giải phóng cùng lúc không?

## 17. FFM so với JNI và các lựa chọn Java thuần

`Java Native Interface (JNI)` vẫn là công nghệ được hỗ trợ, không nên khẳng định JNI đã bị loại bỏ. FFM giải quyết nhiều khó khăn thường gặp khi xây binding mới, đặc biệt với thư viện cung cấp **C ABI**.

| Tiêu chí | FFM API | JNI |
|---|---|---|
| Định nghĩa lời gọi C từ Java | `Linker` và `FunctionDescriptor` | Hàm native và lớp cầu nối JNI |
| Mã “glue” C tự viết | Nhiều trường hợp không cần | Thường cần |
| Kiểm soát off-heap memory | `Arena` và `MemorySegment` | Có thể qua mã C/JNI, DirectByteBuffer |
| Cấu trúc binary phức tạp | `MemoryLayout` / `VarHandle` | Định nghĩa theo mã Java/C riêng |
| Truy cập Java object tùy ý từ C | Không tự thay thế mọi khả năng JNI | JNI thiết kế riêng cho trường hợp này |
| Rủi ro sai con trỏ/ABI | Vẫn có | Vẫn có |
| Phân phối native dependency | Vẫn cần | Vẫn cần |
| Quyền native access trong Java hiện đại | Một số thao tác restricted | Những thao tác JNI tương ứng cũng chịu native access policy |

Nếu ứng dụng chỉ làm việc trên `List`, `Map`, `byte[]` và I/O Java thông thường, **không cần FFM**. Chỉ chọn khi có yêu cầu native memory hoặc foreign function rõ ràng.

Nếu thư viện có API C++ với class, template, exception và name mangling, `Linker` không tự hiểu toàn bộ mô hình C++. Một **C-compatible facade** hoặc binding chuyên dụng có thể vẫn cần thiết.

## 18. Các trường hợp sử dụng phù hợp

### 18.1. Tận dụng thư viện C đã được kiểm chứng

Một tổ chức có thư viện C ổn định cho phép toán đặc thù, codec hoặc thiết bị phần cứng. FFM có thể tạo downcall trực tiếp thay vì viết lớp glue JNI riêng cho từng hàm.

**Điều kiện:** có C ABI ổn định, header chuẩn, phiên bản thư viện được quản lý và quy tắc ownership rõ ràng.

### 18.2. Đọc cấu trúc nhị phân hoặc giao tiếp phần cứng

Với file hoặc buffer chứa các record có offset và alignment cố định, `MemoryLayout` và `VarHandle` làm code dễ kiểm tra hơn so với liên tục tính offset thủ công.

**Điều kiện:** định dạng dữ liệu được mô tả rõ, kiểm soát endianness, padding, số lượng record và byte range.

### 18.3. Truy cập tệp dữ liệu lớn qua memory mapping

Ứng dụng phân tích dữ liệu có thể map một vùng file và đọc các record theo offset mà không phải đưa toàn bộ tệp lên `byte[]`.

**Điều kiện:** truy cập có lợi từ mapping, đủ tài nguyên hệ điều hành, không có sửa đổi file không đồng bộ và có chính sách cleanup rõ ràng.

### 18.4. Buffer tạm cho một native call

Một phương thức Java cần tạo C string hoặc cấu trúc tham số, gọi native function, đọc kết quả rồi giải phóng ngay.

**Mẫu ưu tiên:** `try (Arena arena = Arena.ofConfined())` cùng downcall trong scope. Cần xác nhận native không giữ pointer sau khi hàm trả về.

### 18.5. Callback từ thư viện native

Một thư viện C yêu cầu callback để báo sự kiện, thống kê tiến độ hoặc comparator.

**Điều kiện:** callback ABI đúng, lifetime stub đủ dài, xử lý exception ngay trong Java callback, đồng bộ state và unregister trước khi đóng arena.

## 19. Các trường hợp không nên vội dùng FFM

- **Dữ liệu nghiệp vụ thông thường**: `record`, collection, array và object Java thường đơn giản và an toàn hơn.
- **Chỉ gửi/nhận network**: `HttpClient`, `SocketChannel` hoặc Netty/framework phù hợp không nhất thiết cần off-heap tự quản.
- **Chỉ đọc file nhỏ**: `Files.readAllBytes` hoặc `InputStream` thường đủ.
- **Cần phân lập mã không tin cậy**: gọi thư viện native trong cùng JVM có thể crash toàn tiến trình; cân nhắc tách process.
- **Không có C ABI rõ**: đoán descriptor có thể gây corruption, không nên triển khai từ tên hàm.
- **Không có lợi ích hiệu năng đã đo**: chi phí FFM và native boundary có thể khiến giải pháp phức tạp hơn mà không nhanh hơn.
- **Thư viện thay đổi ABI thường xuyên**: phải cân nhắc công cụ sinh binding và quy trình kiểm tra thích hợp.

Không nên dùng FFM như một con đường “bỏ qua” giới hạn an toàn của Java. Những thao tác native đặc quyền cần đánh giá bảo mật và kiểm tra nguồn gốc thư viện trước khi triển khai.

## 20. Hiệu năng và chi phí vận hành

FFM có thể giảm nhu cầu viết mã JNI glue hoặc chi phí chuyển đổi dữ liệu ở một số đường đi, nhưng **không mặc định nhanh hơn mã Java thuần**.

Các chi phí cần đánh giá:

| Chi phí | Ví dụ |
|---|---|
| Cấp phát/giải phóng native | Tạo nhiều arena nhỏ hoặc allocate theo từng record |
| Kiểm tra segment | Bounds, lifetime, thread-confinement |
| Chuyển đổi dữ liệu | Java String sang UTF-8 C string; struct layout; copy heap → native |
| Native boundary | Chi phí chuyển điều khiển Java ↔ C |
| Quản lý cache/TLB | Truy cập bộ nhớ ngẫu nhiên lớn |
| File mapping và page fault | Trang dữ liệu chưa nằm trong bộ nhớ vật lý |
| Đồng bộ | Shared arena, nhiều thread đọc/ghi một vùng |
| Biến động thư viện | ABI, cách compiler tối ưu và phiên bản dependency |

### 20.1. Đừng đo chi phí gọi native bằng một vòng lặp vô nghĩa

Một benchmark nhỏ chạy một lần có thể bị nhiễu bởi warm-up, JIT, GC, page fault, tốc độ CPU và số lượng dữ liệu. Nếu cần đo FFM so với Java, dùng benchmark chuyên dụng như **JMH**, với workload thật và kết quả được tiêu thụ để tránh phép tối ưu loại bỏ công việc.

Nên so sánh theo **nhiệm vụ tương đương**:

- Java native arrays với FFM memory segment.
- Java parser với native parser cộng cả chi phí chuyển dữ liệu.
- `FileChannel`/`ByteBuffer` với mapped `MemorySegment` trên cùng tập dữ liệu.
- Thời gian thao tác và tổng mức sử dụng bộ nhớ, không chỉ latency của một lệnh.

### 20.2. Đo tổng bộ nhớ tiến trình, không chỉ -Xmx

`-Xmx` giới hạn Java heap, **không phải tổng RAM của JVM**. Process còn sử dụng metaspace, thread stacks, code cache, direct/native buffers và vùng nhớ cấp phát bằng FFM.

Khi dùng FFM với bộ nhớ lớn, theo dõi:

- Resident set size / working set của tiến trình.
- Mức cấp phát và thu hồi off-heap.
- Số arena đang sống.
- Mức sử dụng virtual memory/address space.
- Page fault, I/O và độ trễ file mapping.
- Số native callback/downcall lỗi và timeout.

Một chương trình có heap nhỏ vẫn có thể bị hệ điều hành chấm dứt nếu off-heap allocation quá lớn.

## 21. Giải phóng tài nguyên khi gọi native bị lỗi

Ví dụ dùng confined arena thường an toàn nhất ở tầng lifecycle Java:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment buffer = arena.allocate(1024);

    // Gọi native API với buffer.
    // Nếu phía Java ném ngoại lệ, arena vẫn được close.
}
~~~

Tuy nhiên, cần phân biệt:

- **Ngoại lệ Java thông thường**: try-with-resources bảo đảm `Arena.close()` được gọi khi rời khối.
- **Native code crash JVM**: `finally`/try-with-resources không thể được xem là cơ chế phục hồi một tiến trình đã crash.
- **Native API giữ pointer**: đóng arena khi native còn sử dụng pointer gây rủi ro, dù mã Java trông hợp lệ.
- **Native API yêu cầu một cleanup function riêng**: đóng arena cấp phát Java không tự gọi hàm giải phóng do thư viện C quy định cho vùng nhớ do thư viện cấp phát.
- **Upcall stub được native lưu lại**: không được đóng arena trước khi hủy đăng ký callback và bảo đảm mọi native call liên quan đã kết thúc.

Trong thiết kế production, định nghĩa rõ một **ownership protocol**: ai cấp phát, ai giải phóng, thời điểm hợp lệ, cơ chế đồng bộ và phản ứng khi thao tác thất bại.

## 22. Native error và errno

Không phải mọi hàm C đều báo lỗi qua exception. Một hàm có thể:

- Trả về giá trị đặc biệt, chẳng hạn `-1` hoặc `NULL`.
- Ghi chi tiết lỗi vào `errno` (trong nhiều C/POSIX API).
- Ghi mã lỗi vào tham số con trỏ.
- Sử dụng trạng thái riêng của thư viện.

FFM không tự biến mọi mã lỗi của C thành `IOException` hoặc Java exception. Caller phải **kiểm tra quy ước trả lỗi được tài liệu hóa của từng hàm**.

Đối với một số ABI, `Linker.Option.captureCallState(...)` cho phép thu trạng thái lỗi của native call, chẳng hạn `errno`, theo lựa chọn linker hỗ trợ. Đây là phần nâng cao: tên state và quy tắc thu phụ thuộc ABI/nền tảng.

Không giả định rằng đọc `errno` từ một lời gọi native khác sau đó sẽ còn phản ánh chính xác lỗi gốc; nhiều thao tác native khác có thể thay đổi trạng thái lỗi của thread.

## 23. Công cụ hỗ trợ và phát hành native dependency

### 23.1. jextract và sinh binding

Với thư viện C lớn, viết thủ công hàng trăm `FunctionDescriptor` và `MemoryLayout` dễ sai. **jextract** là công cụ thuộc hệ sinh thái OpenJDK để sinh mã Java binding từ C headers phù hợp với FFM.

Cần lưu ý:

- jextract không phải một class của `java.lang.foreign`.
- Không được mặc định rằng mọi bản JDK 27 đều đóng gói sẵn một file thực thi jextract.
- Phiên bản công cụ sinh binding phải tương thích JDK mục tiêu.
- Mã sinh ra vẫn phải được review, đặc biệt về ownership, callback lifetime, ABI và native library loading.
- Không dùng thư viện/binding sinh ra mà bỏ qua kiểm tra rủi ro đầu vào không tin cậy.

### 23.2. Đóng gói native library

Một ứng dụng có thể cần phân phối:

~~~text
app/
├── app.jar
└── native/
    ├── linux-x64/
    │   └── libexample.so
    ├── macos-arm64/
    │   └── libexample.dylib
    └── windows-x64/
        └── example.dll
~~~

Cấu trúc là minh họa, không phải quy ước được JDK tự áp dụng. Ứng dụng cần chọn đúng thư viện theo OS/architecture, kiểm tra nguồn gốc và truyền path phù hợp vào `SymbolLookup.libraryLookup(...)` hoặc dùng chính sách native loading đã thiết kế.

Không tự download rồi chạy bất kỳ native library nào chỉ dựa trên tên thư viện do client cung cấp. Native library có thể thực thi mã ngay khi được load (ví dụ qua initialization hook), trước khi ứng dụng thực hiện downcall cụ thể.

### 23.3. Module và quyền native

Trong ứng dụng JPMS:

- Nhánh FFM API nằm trong `java.base` nên không yêu cầu `requires java.lang.foreign`.
- Nếu module gọi **restricted FFM methods**, cấp `--enable-native-access=<module-name>`.
- Chỉ module chứa code thực sự gọi restricted methods cần quyền tương ứng; không cấp quyền rộng cho toàn bộ module graph một cách mặc định.
- Kiểm tra runtime image và native library được đóng gói đầy đủ cho nền tảng triển khai.

## 24. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `IndexOutOfBoundsException` khi `get/set` | Offset hoặc độ dài vượt segment | Dùng `byteSize`, tính toán offset an toàn |
| `IllegalStateException` sau khi close | Sử dụng segment đã hết scope | Không để segment thoát lifetime của arena |
| `WrongThreadException` | Truy cập confined segment từ thread khác | Giữ trong owner thread hoặc dùng shared arena có đồng bộ |
| `IllegalCallerException` ở downcall/linker | Restricted native access bị từ chối | Cấp `--enable-native-access` đúng module |
| Cảnh báo illegal native access | Chưa cấp quyền nhưng runtime đang ở chế độ warn | Cấu hình quyền tường minh; kiểm tra với deny |
| `NoSuchElementException` khi findOrThrow | Thư viện không export symbol yêu cầu | Kiểm tra thư viện/tên symbol và platform |
| `WrongMethodTypeException` từ invokeExact | Carrier Java không khớp method handle | Dựa vào `FunctionDescriptor` và method type |
| `IllegalArgumentException` tạo downcall | ABI/layout không được hỗ trợ hoặc option sai | Kiểm tra C signature, canonical layout |
| Kết quả số nguyên sai | Nhầm endianness, alignment, offset hoặc C type size | Đọc header/ABI, kiểm tra byte order |
| JVM crash khi gọi native | Pointer sai, native bug, ABI mismatch hoặc use-after-free | Kiểm tra native code, ownership, dụng cụ chẩn đoán |
| Native callback crash tiến trình | Callback Java ném ngoại lệ ra ngoài upcall | Catch toàn bộ exception, trả mã lỗi hợp lệ |
| Rò rỉ RAM ngoài heap | Không đóng arena hoặc lạm dụng global arena | Dùng confined/shared arena và try-with-resources |
| File mapping đọc dữ liệu bất thường | File bị thay đổi/truncate đồng thời | Quy định đồng bộ và vòng đời mapped region |
| `OutOfMemoryError` hoặc tiến trình bị kill | Native memory vượt ngân sách | Giới hạn allocation, theo dõi RSS/quota |
| Thư viện chạy máy này nhưng không chạy máy kia | Khác OS/CPU/ABI/dependency | Đóng gói đúng native build, kiểm tra portability |

### 24.1. Lộ trình gỡ lỗi downcall

~~~text
Không gọi được C function?
       |
       v
Có đúng native library cho OS/CPU?
       |
       v
Library được load thành công?
       |
       v
Symbol có được export đúng tên?
       |
       v
FunctionDescriptor khớp header và ABI?
       |
       v
Đã cấp quyền native access cho module?
       |
       v
Đối số pointer hợp lệ, đủ size, còn sống?
       |
       v
Native API có yêu cầu ownership/cleanup?
       |
       v
Kiểm tra mã trả lỗi và log chẩn đoán
~~~

Khi nghi ngờ memory corruption, chạy trong môi trường test riêng và sử dụng công cụ phân tích native phù hợp. **Đừng tự động retry một hàm native đang làm crash JVM trong cùng tiến trình**, vì bộ nhớ có thể đã hỏng.

## 25. Thiết kế an toàn: các nguyên tắc thực hành

1. **Ưu tiên API Java thuần** nếu nó đã đáp ứng yêu cầu rõ ràng.
2. **Giới hạn native access** chỉ cho module cần thiết.
3. **Chọn đúng arena**: confined cho công việc cục bộ, shared khi thật sự cần truy cập đa luồng.
4. **Đóng arena đúng thời điểm**, không để con trỏ native dùng sau khi đã đóng.
5. **Không lạm dụng global arena** để cấp phát hàng loạt.
6. **Tính toán kích thước bằng long và kiểm tra tràn số** trước khi allocate.
7. **Giới hạn dung lượng** nhận từ input, kể cả số record và độ sâu cấu trúc.
8. **Mô tả byte order và alignment tường minh** khi trao đổi với file/thiết bị.
9. **Định nghĩa ownership của C pointer** theo từng API.
10. **Kiểm tra chữ ký ABI**, không ánh xạ kiểu C theo tên một cách máy móc.
11. **Không để exception Java thoát từ upcall** sang mã native.
12. **Bảo vệ state đồng thời** khi dùng shared arena hoặc callback multi-thread.
13. **Xác minh native dependency**, quản lý phiên bản, checksum/chữ ký phù hợp.
14. **Theo dõi off-heap RSS và quota**, đừng chỉ xem heap.
15. **Benchmark với workload thật**, không cho rằng native luôn nhanh hơn.

## 26. Bảng quyết định: có nên chọn FFM API?

| Câu hỏi | Nếu câu trả lời là… | Hướng làm |
|---|---|---|
| Chỉ cần xử lý object/mảng Java? | Có | Tiếp tục dùng Java heap và API collection |
| Có cần gọi thư viện C với ABI ổn định? | Có | Cân nhắc FFM downcall |
| Có cần native callback? | Có | Upcall stub với lifetime và exception policy rõ |
| Có cần buffer off-heap quản lý theo scope? | Có | `Arena` + `MemorySegment` |
| Có cần đọc file nhị phân lớn theo offset? | Có | Cân nhắc memory-mapped segment |
| Có cần tích hợp NIO đang dùng ByteBuffer? | Có | Xem `MemorySegment.ofBuffer`/`asByteBuffer` |
| Có cần C++ class ABI trực tiếp? | Có | Xem C-compatible wrapper/binding phù hợp |
| Có yêu cầu chạy mã native không tin cậy? | Có | Phân lập process thay vì nạp vào JVM |
| Không có đội ngũ kiểm tra ABI, ownership và bảo mật? | Có | Ưu tiên phương án Java thuần hoặc binding đã được kiểm chứng |
| Chưa đo được lợi ích hiệu năng? | Có | Benchmark trước khi tăng độ phức tạp |

## 27. Bài tập thực hành

### Bài 1: Array off-heap

Tạo một confined arena, cấp phát đủ chỗ cho 100 số `long` và ghi giá trị `i * 3` vào phần tử thứ `i`. Tính tổng và kiểm tra kết quả.

**Câu hỏi:** Vì sao nên dùng `Math.multiplyExact` hoặc cơ chế kiểm tra kích thước khi số lượng phần tử được nhận từ input?

### Bài 2: Endianness

Tạo một segment 8 byte, ghi số `0x01020304` bằng `JAVA_INT.withOrder(BIG_ENDIAN)`, sau đó đọc từng byte và xác nhận thứ tự.

**Câu hỏi:** Vì sao dùng `JAVA_INT` mặc định có thể cho thứ tự byte khác giữa các kiến trúc?

### Bài 3: Struct và padding

Mô tả C struct gồm `char kind` và `int value` trên ABI thông dụng có `sizeof(int)=4` và `alignof(int)=4`. Sử dụng `MemoryLayout.structLayout`, `paddingLayout` và `byteOffset`.

**Câu hỏi:** Vì sao không được dùng layout giả định 8 byte này cho mọi compiler/ABI mà không kiểm tra?

### Bài 4: Native strlen

Chạy `NativeStrlenDemo` trên máy 64-bit có symbol `strlen` được công bố bởi default lookup. Thử hai chuỗi ASCII và Unicode, so sánh:

- `String.length()`.
- Số byte khi encode UTF-8.
- Kết quả downcall `strlen`.

**Câu hỏi:** Tại sao ba đại lượng có thể khác nhau?

### Bài 5: Arena lifetime

Tạo segment trong confined arena, truy cập trước khi close và thử truy cập sau close; quan sát `IllegalStateException`. Tiếp tục tạo shared arena và thử truy cập từ thread khác.

**Câu hỏi:** Shared arena cho phép đa luồng, nhưng tại sao vẫn cần đồng bộ khi nhiều thread cùng cập nhật một vùng nhớ?

### Bài 6: Native access policy

Biên dịch/downcall như ví dụ, so sánh cách chạy:

~~~shell
java --enable-native-access=ALL-UNNAMED NativeStrlenDemo
java --illegal-native-access=deny NativeStrlenDemo
~~~

Lệnh thứ hai minh họa việc thiếu quyền native khi chuyển sang chế độ deny; hành vi cụ thể còn tùy code đã được cấp quyền qua cấu hình khác hay chưa.

**Câu hỏi:** `--enable-preview` có thay thế `--enable-native-access` không?

## 28. Checklist trước khi đưa FFM vào sản phẩm

- [ ] Bài toán thật sự cần native memory hoặc native function?
- [ ] Java API thuần/ByteBuffer hiện có có thể đáp ứng đơn giản hơn không?
- [ ] Đã kiểm tra API FFM trên đúng JDK mục tiêu chưa?
- [ ] Đã dùng package `java.lang.foreign` ổn định, không dựa vào API incubator cũ?
- [ ] Đã xác định chính xác ABI và signature từ header thư viện?
- [ ] Đã kiểm tra kích thước, padding và byte order?
- [ ] Có giới hạn byte để tránh cấp phát vô hạn?
- [ ] Arena được quản lý qua scope và try-with-resources?
- [ ] Có kiểm tra thread ownership và không chia sẻ confined segment sai quy tắc?
- [ ] Có đồng bộ đúng với shared segment và callbacks?
- [ ] Native library có giữ pointer sau khi lời gọi trả về không?
- [ ] Có biết ai chịu trách nhiệm free từng con trỏ?
- [ ] Upcall có bắt toàn bộ exception và bảo toàn callback lifetime không?
- [ ] Đã cấp native access đúng module, không bật rộng vô cớ?
- [ ] Có chính sách nguồn gốc và phiên bản thư viện native?
- [ ] Có đo tổng RAM native/RSS và mức tiêu thụ CPU thực tế?
- [ ] Có test trên các OS/CPU/JDK được hỗ trợ?
- [ ] Có phương án xử lý crash native và bảo vệ dữ liệu nghiệp vụ?
- [ ] Có test lỗi, timeout, cancellation và cleanup khi cần?
- [ ] Đã ghi nhận trade-off về bảo trì và khả năng deploy?

## 29. Tóm tắt

- **FFM API** là cơ chế hiện hành của Java để làm việc với vùng nhớ và hàm ngoài JVM, đã ổn định từ Java 22 và tiếp tục phù hợp với Java 27.
- `MemorySegment` mô hình hóa vùng nhớ **on-heap hoặc off-heap**; không phải mọi segment đều là native.
- `Arena` quản lý native memory theo thời gian sống; confined/shared cho phép giải phóng có kiểm soát.
- `MemoryLayout` và `ValueLayout` mô tả kích thước, offset, alignment và byte order.
- `Linker`, `SymbolLookup` và `FunctionDescriptor` tạo **downcall** sang hàm C; `upcallStub` tạo callback cho native gọi Java.
- Đối chiếu **ABI, C types, padding, ownership và lifetime** là bắt buộc; FFM không tự làm mã native an toàn.
- Những phương thức restricted phải được cấp quyền với `--enable-native-access`. Việc thiếu quyền hiện có thể tạo cảnh báo, nhưng chính sách dự kiến sẽ nghiêm ngặt hơn ở những JDK tương lai.
- FFM hữu ích khi cần thư viện C, cấu trúc nhị phân, mapped file hoặc off-heap buffer, **không phải lựa chọn mặc định cho mọi dữ liệu Java**.
- Luôn quản lý vòng đời, giới hạn tài nguyên, kiểm tra lỗi, đánh giá bảo mật và benchmark trước khi đưa vào production.

## Tài liệu tham khảo chính thức

- [java.lang.foreign — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Arena — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html)
- [MemorySegment — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [MemoryLayout — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [ValueLayout — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [FunctionDescriptor — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Linker — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html)
- [SymbolLookup — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Restricted Methods — Java SE 27](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
