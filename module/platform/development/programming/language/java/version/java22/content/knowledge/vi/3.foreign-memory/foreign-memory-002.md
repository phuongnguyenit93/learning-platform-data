# MemorySegment: vùng nhớ trên heap, ngoài heap, kích thước và địa chỉ

**MemorySegment** là API trung tâm của Foreign Function & Memory (FFM) API, được hoàn thiện trong Java 22 qua JEP 454. API này vẫn được dùng trong các JDK hiện đại, bao gồm JDK 27. Bài viết sử dụng API final trong package **java.lang.foreign**, không dùng các phiên bản incubator cũ.

Một **MemorySegment** mô tả một vùng nhớ liên tục và cung cấp cách đọc, ghi vùng nhớ đó. Segment không nhất thiết tự cấp phát bộ nhớ: nó có thể là một góc nhìn trên mảng Java có sẵn, một vùng nhớ native do Arena cấp phát, hoặc vùng nhớ ánh xạ từ file. Mọi segment đều có kích thước, địa chỉ, phạm vi truy cập và vòng đời xác định.

## 1. Hai loại vùng nhớ: heap và native

FFM API phân biệt hai loại segment chính:

- **Heap segment (on-heap):** vùng nhớ nằm trong Java heap và được một đối tượng Java, thường là mảng primitive, backing.
- **Native segment (off-heap):** vùng nhớ nằm ngoài Java heap. Segment thường được tạo bởi Arena hoặc đại diện cho vùng nhớ ánh xạ từ file.

Cả hai loại đều dùng chung các thao tác như **get**, **set**, **getAtIndex**, **setAtIndex** và **asSlice**. Nhờ vậy, mã xử lý dữ liệu không phải thay đổi hoàn toàn chỉ vì dữ liệu chuyển từ heap sang native memory.

| Đặc điểm | Heap segment | Native segment |
|---|---|---|
| Vị trí vùng nhớ | Bên trong Java heap | Ngoài Java heap |
| Cách tạo thường gặp | **MemorySegment.ofArray(array)** | **arena.allocate(byteSize, byteAlignment)** |
| Vùng nhớ backing | Mảng Java hiện có; không sao chép mảng khi tạo segment | Vùng nhớ native do Arena cấp phát, hoặc vùng nhớ ánh xạ từ file |
| Quản lý bộ nhớ | Garbage Collector quản lý đối tượng backing; segment giữ đối tượng đó còn reachable | Arena quản lý vòng đời vùng nhớ native |
| Địa chỉ | Địa chỉ logic/offset trong vùng backing, không phải con trỏ vật lý | Địa chỉ native của vùng nhớ |
| Truy cập đa luồng | Có thể truy cập từ mọi thread | Phụ thuộc loại Arena, ví dụ confined hoặc shared |
| Khi hết vòng đời | Mảng được thu hồi khi không còn reachable | Vùng nhớ được giải phóng khi Arena tương ứng đóng hoặc theo cơ chế Arena được chọn |

Một heap segment không phải bản sao của mảng. Nếu ghi dữ liệu qua segment thì mảng backing cũng thay đổi; nếu ghi trực tiếp vào mảng thì đọc qua segment sẽ thấy giá trị mới.

Một native segment không nằm trong Java heap nên không được thu hồi theo cách thông thường của đối tượng Java. Cần xác định rõ khi nào vùng nhớ được giải phóng và bảo đảm không truy cập segment sau thời điểm đó.

## 2. Tạo heap segment từ mảng Java

Dùng các factory method **MemorySegment.ofArray(...)** để tạo segment từ mảng primitive. Ví dụ sau tạo segment trên một mảng int:

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

class HeapSegmentExample {
    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40};

        MemorySegment numbers = MemorySegment.ofArray(values);

        System.out.println(numbers.isNative()); // false
        System.out.println(numbers.byteSize()); // 16
        System.out.println(numbers.address());  // 0

        System.out.println(
                numbers.getAtIndex(ValueLayout.JAVA_INT, 2)
        ); // 30

        numbers.setAtIndex(ValueLayout.JAVA_INT, 1, 99);

        System.out.println(values[1]); // 99
    }
}
~~~

Giải thích:

1. **MemorySegment.ofArray(values)** tạo một heap segment backing bởi chính mảng **values**; không tạo một bản sao dữ liệu.
2. Mảng có bốn phần tử int, mỗi phần tử chiếm bốn byte, nên **byteSize()** trả về 16.
3. **isNative()** trả về false vì segment nằm trên heap.
4. **getAtIndex(ValueLayout.JAVA_INT, 2)** đọc phần tử int ở chỉ số logic 2.
5. **setAtIndex(...)** ghi trực tiếp vào vùng nhớ backing, vì vậy **values[1]** nhận giá trị 99.

Heap segment giữ mảng backing reachable trong thời gian segment còn được sử dụng. Mảng vẫn do Garbage Collector quản lý; không cần gọi hàm giải phóng thủ công.

Các factory method có thể nhận những mảng primitive khác như **byte[]**, **short[]**, **char[]**, **long[]**, **float[]** và **double[]**. Kích thước segment được tính theo số byte của mảng backing. API không có overload **MemorySegment.ofArray(boolean[])**; nếu cần biểu diễn dãy boolean trong segment, hãy chọn một cách mã hóa byte rõ ràng hoặc dùng native segment với **ValueLayout.JAVA_BOOLEAN**.

## 3. Tạo native segment bằng Arena

Dùng **Arena** để cấp phát vùng nhớ ngoài heap. Arena vừa cấp phát bộ nhớ, vừa xác định vòng đời và quy tắc truy cập thread của các segment được tạo từ nó.

Ví dụ sau cấp phát 32 byte, căn chỉnh theo biên 8 byte và lưu một giá trị long:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

class NativeSegmentExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(32, Long.BYTES);

            data.set(ValueLayout.JAVA_LONG, 0, 2026L);

            System.out.println(data.isNative()); // true
            System.out.println(data.byteSize()); // 32
            System.out.printf("0x%x%n", data.address());
            System.out.println(data.get(ValueLayout.JAVA_LONG, 0)); // 2026
        }
    }
}
~~~

Trong ví dụ:

- **Arena.ofConfined()** tạo Arena chỉ cho phép thread sở hữu nó truy cập các segment đã cấp phát.
- **allocate(32, Long.BYTES)** cấp phát vùng nhớ native có kích thước 32 byte và alignment 8 byte.
- **isNative()** xác nhận đây là native segment.
- **address()** trả về địa chỉ bắt đầu của vùng nhớ native.
- Khi thoát khỏi khối **try**, Arena tự đóng và vùng nhớ native được giải phóng.

Tham số **byteAlignment** được tính bằng byte và phải là số dương dạng lũy thừa của hai. Chọn alignment phù hợp với kiểu dữ liệu hoặc cấu trúc native sẽ truy cập. Ví dụ, vùng nhớ chứa các giá trị long thường cần alignment 8 byte.

### Chọn Arena theo vòng đời và thread

| Loại Arena | Thread có thể truy cập | Cách kết thúc vòng đời | Trường hợp sử dụng |
|---|---|---|---|
| **ofConfined()** | Chỉ thread tạo Arena | Gọi close; thường dùng try-with-resources | Công việc native memory trong một thread, cần giải phóng xác định |
| **ofShared()** | Nhiều thread | Gọi close khi mọi thao tác đã kết thúc | Khi nhiều thread cần cùng truy cập segment |
| **ofAuto()** | Nhiều thread | Garbage Collector quản lý; thời điểm giải phóng không xác định | Khi cần vòng đời tự động và chấp nhận không giải phóng đúng một thời điểm cụ thể |
| **global()** | Nhiều thread | Không thể đóng; vùng nhớ không được giải phóng | Vùng nhớ cần tồn tại suốt vòng đời JVM, dùng có chủ đích |

Với cấp phát cục bộ, ưu tiên **Arena.ofConfined()** và try-with-resources để vòng đời native memory rõ ràng. Dùng **ofShared()** khi cần chia sẻ segment giữa nhiều thread; việc cùng truy cập được không tự động bảo đảm dữ liệu không có race condition.

Không nên dùng **Arena.global()** cho cấp phát tạm thời vì vùng nhớ được cấp phát từ Arena này không được giải phóng trong vòng đời JVM. **Arena.ofAuto()** cũng không thay thế việc quản lý vòng đời xác định khi ứng dụng cần thu hồi native memory ngay sau một công việc.

## 4. Kích thước vùng nhớ với byteSize()

Mọi MemorySegment đều cung cấp phương thức **byteSize()**, trả về kích thước vùng nhớ theo byte dưới kiểu **long**. Đơn vị là byte, không phải số phần tử, số ký tự hay số giá trị Java.

Một số kích thước cơ bản:

| Kiểu dữ liệu | Kích thước thông thường | Ví dụ với mảng có 4 phần tử |
|---|---:|---:|
| byte | 1 byte | 4 byte |
| boolean | 1 byte trong ValueLayout | 4 byte nếu lưu 4 giá trị boolean trong segment |
| short, char | 2 byte | 8 byte |
| int, float | 4 byte | 16 byte |
| long, double | 8 byte | 32 byte |

Ví dụ:

~~~java
int[] numbers = {1, 2, 3, 4};
MemorySegment segment = MemorySegment.ofArray(numbers);

long sizeInBytes = segment.byteSize();
long expectedSize = (long) numbers.length * Integer.BYTES;

System.out.println(sizeInBytes);             // 16
System.out.println(sizeInBytes == expectedSize); // true
~~~

Ép **numbers.length** sang **long** trước phép nhân giúp biểu thức tính kích thước được thực hiện theo kiểu long. Bản thân **byteSize()** cũng trả về long để mô tả các vùng nhớ có kích thước lớn hơn giới hạn của chỉ số mảng Java.

### Offset và chỉ số phần tử

Các thao tác **get(layout, offset)** và **set(layout, offset, value)** nhận offset tính bằng byte, tương đối với địa chỉ bắt đầu của segment.

Ví dụ với một segment chứa các giá trị int:

~~~java
int[] values = {10, 20, 30, 40};
MemorySegment segment = MemorySegment.ofArray(values);

int second = segment.get(ValueLayout.JAVA_INT, Integer.BYTES);
~~~

Offset 4 trỏ đến byte bắt đầu của phần tử int thứ hai vì mỗi int chiếm 4 byte.

Nếu muốn làm việc theo chỉ số phần tử, dùng **getAtIndex(layout, index)** hoặc **setAtIndex(layout, index, value)**:

~~~java
int second = segment.getAtIndex(ValueLayout.JAVA_INT, 1);
segment.setAtIndex(ValueLayout.JAVA_INT, 1, 200);
~~~

Với kiểu dữ liệu có kích thước cố định, công thức quy đổi là:

\[
\text{byteOffset} = \text{index} \times \text{layout.byteSize()}
\]

Các access operation vẫn kiểm tra biên segment và alignment của layout. Không nên tự tính offset bằng số phần tử nếu chưa xác định kích thước và alignment của layout.

## 5. Địa chỉ vùng nhớ với address()

Phương thức **address()** trả về địa chỉ segment dưới kiểu **long**. Ý nghĩa của giá trị này phụ thuộc vào loại segment:

| Loại segment | Ý nghĩa của address() |
|---|---|
| Heap segment | Offset logic trong vùng backing của segment; không phải địa chỉ vật lý mà native code có thể dereference |
| Native segment | Địa chỉ bắt đầu của vùng nhớ native |
| Slice | Địa chỉ của segment cha cộng với offset bắt đầu slice |

Đối với segment gốc tạo từ **MemorySegment.ofArray(...)**, địa chỉ được đặt bằng 0. Nếu tạo slice từ offset 8 byte, địa chỉ logic của slice sẽ là địa chỉ segment gốc cộng 8.

Ví dụ:

~~~java
int[] values = {10, 20, 30, 40};
MemorySegment all = MemorySegment.ofArray(values);

MemorySegment lastTwo = all.asSlice(
        2L * Integer.BYTES,
        2L * Integer.BYTES
);

System.out.println(all.address());       // 0
System.out.println(lastTwo.address());   // 8
System.out.println(lastTwo.byteSize());  // 8
~~~

Địa chỉ 8 trong ví dụ là offset logic tính bằng byte trong vùng backing của mảng. Nó **không phải** con trỏ vật lý đến phần tử thứ ba. JVM có thể di chuyển đối tượng heap khi Garbage Collector hoạt động; MemorySegment trừu tượng hóa việc di chuyển đó để mã Java vẫn truy cập đúng vùng nhớ.

Với native segment, **address()** là địa chỉ native thực tế. Tuy nhiên, địa chỉ chỉ có ý nghĩa trong thời gian vùng nhớ còn hợp lệ. Nếu Arena đã đóng, địa chỉ cũ không thể được dùng để truy cập vùng nhớ đã giải phóng.

Trước khi diễn giải địa chỉ như một native pointer, có thể kiểm tra **isNative()**. Không lưu địa chỉ native rồi sử dụng sau khi Arena kết thúc; hãy giữ segment và Arena còn sống trong toàn bộ thời gian thao tác native.

### Không nhầm ofAddress() với cấp phát bộ nhớ

**MemorySegment.ofAddress(long)** tạo một native segment có kích thước bằng 0 để biểu diễn một địa chỉ đã có. Phương thức này không cấp phát vùng nhớ, không xác định kích thước vùng được trỏ tới và không chứng minh con trỏ còn hợp lệ.

Một segment có kích thước 0 không cho phép đọc hoặc ghi dữ liệu. Muốn dereference một địa chỉ native cần có thông tin kích thước, alignment và vòng đời đáng tin cậy. Những thao tác gán lại bounds cho địa chỉ native là restricted methods và có thể gây crash JVM hoặc hỏng bộ nhớ nếu dùng sai. Người mới học nên dùng segment được Arena cấp phát thay vì tự dựng segment từ một con trỏ không rõ nguồn gốc.

## 6. Chia vùng nhớ bằng asSlice()

**asSlice(offset, size)** tạo một segment mới đại diện cho một phần của segment ban đầu:

- **offset** là vị trí bắt đầu tính bằng byte.
- **size** là kích thước slice tính bằng byte.
- Slice dùng chung vùng nhớ backing với segment gốc, không sao chép dữ liệu.
- Địa chỉ slice bằng địa chỉ segment gốc cộng offset.
- Slice có giới hạn không gian riêng và kế thừa scope của segment gốc.
- Overload **asSlice(offset, size)** mặc định đặt alignment của slice là 1 byte; khi cần đọc/ghi kiểu có alignment lớn hơn, chọn overload có alignment hoặc overload nhận **MemoryLayout**.

Ví dụ chia một vùng nhớ native thành phần header và payload:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

class SliceExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment packet = arena.allocate(64, Long.BYTES);

            MemorySegment header = packet.asSlice(0, 16, Long.BYTES);
            MemorySegment payload = packet.asSlice(16, 48, Long.BYTES);

            header.set(ValueLayout.JAVA_INT, 0, 0x1234);
            payload.set(ValueLayout.JAVA_INT, 0, 100);

            System.out.println(header.byteSize());  // 16
            System.out.println(payload.byteSize()); // 48
            System.out.println(payload.get(ValueLayout.JAVA_INT, 0)); // 100
        }
    }
}
~~~

Hai slice không tạo hai vùng nhớ độc lập. Ghi qua slice sẽ thay đổi chính vùng nhớ tương ứng trong segment gốc.

Nếu **offset** hoặc **size** làm slice vượt ra ngoài phạm vi segment gốc, thao tác tạo slice ném **IndexOutOfBoundsException**. Nếu Arena của segment gốc bị đóng, các slice được tạo từ nó cũng không còn truy cập được.

Slice rất hữu ích để chia một buffer thành header, metadata và payload; giới hạn mỗi thành phần trong đúng vùng byte mà nó được phép sử dụng.

## 7. Alignment và ValueLayout

Kích thước không phải yếu tố duy nhất quyết định một thao tác đọc/ghi có hợp lệ hay không. Mỗi **ValueLayout** còn mô tả:

- Kiểu Java dùng để đọc hoặc ghi.
- Kích thước giá trị theo byte.
- Byte order, ví dụ native order hoặc big-endian.
- Alignment yêu cầu của địa chỉ truy cập.

Ví dụ, **ValueLayout.JAVA_INT** có kích thước 4 byte và alignment 4 byte. Khi đọc int từ native segment, offset cần phù hợp với alignment đó.

Một điểm dễ nhầm là heap segment được tạo từ **byte[]** có maximum alignment bằng 1 byte. Vì vậy, truy cập bằng layout yêu cầu alignment 4 byte như **ValueLayout.JAVA_INT** sẽ không hợp lệ, dù segment có đủ số byte. Nếu dữ liệu thực sự là mảng int, hãy tạo segment từ **int[]**. Nếu đang giải mã một định dạng byte có trường int không căn chỉnh, có thể dùng **ValueLayout.JAVA_INT_UNALIGNED** khi định dạng dữ liệu cho phép:

~~~java
byte[] raw = new byte[8];
MemorySegment bytes = MemorySegment.ofArray(raw);

// Dùng layout unaligned vì vùng backing là byte[].
bytes.set(ValueLayout.JAVA_INT_UNALIGNED, 0, 12345);

int value = bytes.get(ValueLayout.JAVA_INT_UNALIGNED, 0);
System.out.println(value); // 12345
~~~

Dùng layout unaligned có chủ đích cho dữ liệu byte được đóng gói. Với dữ liệu native, nên thiết kế alignment phù hợp ngay khi cấp phát để các access operation tương thích với layout và phần cứng.

## 8. Spatial bounds, temporal bounds và thread access

MemorySegment kết hợp ba nhóm kiểm tra giúp hạn chế lỗi truy cập bộ nhớ:

| Kiểm tra | Ý nghĩa | Lỗi thường gặp |
|---|---|---|
| Spatial bounds | Đảm bảo thao tác nằm trong vùng segment được cấp quyền | Đọc/ghi vượt byteSize hoặc vượt slice |
| Temporal bounds | Đảm bảo vùng nhớ backing vẫn còn tồn tại | Dùng native segment sau khi Arena đã đóng |
| Thread confinement | Đảm bảo thread hiện tại được phép truy cập segment | Dùng segment của confined Arena từ thread khác |

Các kiểm tra này không làm cho mọi thao tác native trở nên an toàn tuyệt đối. Khi gọi hàm native, cần bảo đảm thư viện native tuân thủ kích thước, kiểu dữ liệu, alignment và quy tắc vòng đời đã thống nhất với Java.

Đặc biệt, không trả một native segment ra ngoài phạm vi Arena rồi đóng Arena ngay lập tức. Nếu một API cần giữ vùng nhớ để sử dụng bất đồng bộ, vòng đời Arena phải bao trùm toàn bộ thời gian sử dụng đó. Khi cần truy cập từ nhiều thread, cân nhắc **Arena.ofShared()** và đồng bộ hóa dữ liệu ở cấp ứng dụng.

## 9. Những lỗi thường gặp khi làm việc với MemorySegment

| Cách hiểu hoặc cách làm sai | Cách xử lý đúng |
|---|---|
| Xem **byteSize()** là số phần tử | Đây là tổng kích thước theo byte; dùng layout để quy đổi sang chỉ số phần tử. |
| Coi **address()** của heap segment là con trỏ native | Heap address chỉ là offset logic; chỉ native segment mới có địa chỉ vùng nhớ native. |
| Nghĩ **ofArray(...)** tạo bản sao mảng | Segment dùng chung vùng nhớ với mảng backing. |
| Nghĩ **asSlice(...)** cấp phát hoặc sao chép vùng nhớ mới | Slice là view zero-copy, dùng chung backing và kế thừa scope. |
| Truy cập native segment sau khi đóng Arena | Chỉ truy cập khi scope còn sống; giữ Arena tồn tại trong toàn bộ thời gian sử dụng. |
| Dùng **JAVA_INT** trên segment từ **byte[]** mà bỏ qua alignment | Chọn mảng backing phù hợp hoặc layout unaligned khi định dạng dữ liệu yêu cầu. |
| Gọi **ofAddress(...)** rồi giả định có thể đọc dữ liệu | Segment được tạo có kích thước 0; phương thức không cấp phát hoặc tự xác định bounds. |
| Cho rằng off-heap luôn nhanh hơn heap | Đo hiệu năng theo workload thực tế; native memory có chi phí cấp phát, sao chép, quản lý vòng đời và tương tác native. |

## 10. API hiện hành và ví dụ FFM cũ

FFM API được hoàn thiện trong Java 22. Khi học hoặc nâng cấp ứng dụng, hãy dùng các thành phần hiện hành:

| Thành phần | Vai trò |
|---|---|
| **MemorySegment** | Mô tả vùng nhớ, kích thước, địa chỉ và phạm vi truy cập |
| **Arena** | Cấp phát và quản lý vòng đời native memory |
| **MemoryLayout** | Mô tả cấu trúc, kích thước và alignment của vùng nhớ |
| **ValueLayout** | Mô tả cách đọc/ghi một giá trị có kiểu |
| **SegmentAllocator** | Giao diện cấp phát segment từ Arena hoặc allocator khác |

Các ví dụ FFM từ những vòng incubator trước Java 22 có thể chứa **MemoryAddress**, **ResourceScope**, **MemorySegment.allocateNative(...)** hoặc các lớp truy cập bộ nhớ cũ. Không áp dụng nguyên trạng những ví dụ đó cho API final hiện nay. Hãy chuyển sang **Arena**, **MemorySegment**, **ValueLayout** và **MemoryLayout**.

FFM API final nằm trong module **java.base**, vì vậy các ví dụ MemorySegment thông thường không cần **--enable-preview** hoặc **--add-modules jdk.incubator.foreign**. Cờ native access chỉ liên quan đến các restricted methods nhất định khi làm việc với mã native; tạo segment, đọc/ghi segment được Arena quản lý không tự yêu cầu bật cờ này.

## 11. Gợi ý lựa chọn heap segment hay native segment

| Tình huống | Lựa chọn nên cân nhắc |
|---|---|
| Xử lý dữ liệu đang nằm trong mảng Java | Heap segment qua **MemorySegment.ofArray(...)** |
| Cần chia sẻ trực tiếp vùng nhớ với thư viện native | Native segment được cấp phát bằng Arena, cùng quy ước ABI với thư viện |
| Cần vòng đời native memory rõ ràng trong một thao tác | **Arena.ofConfined()** và try-with-resources |
| Nhiều thread cần truy cập cùng native memory | **Arena.ofShared()**, kèm đồng bộ hóa dữ liệu |
| Truy cập dữ liệu trong file lớn theo vùng | Memory-mapped segment, với vòng đời và quyền ghi phù hợp |
| Chưa có bằng chứng cần native memory | Ưu tiên cấu trúc heap đơn giản; benchmark trước khi chuyển sang off-heap |

Không nên chọn native memory chỉ vì muốn tránh Garbage Collector. Heap segment vẫn có thể được truy cập bằng cùng API và thường đơn giản hơn trong ứng dụng Java thuần. Native segment hữu ích khi cần tương tác với native code, chia sẻ dữ liệu theo ABI, ánh xạ file hoặc kiểm soát vùng nhớ ngoài heap theo một vòng đời cụ thể.

## Tài liệu tham khảo chính thức

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): mục tiêu và việc hoàn thiện FFM API trong JDK 22.
- [MemorySegment — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): loại segment, address, byteSize, slicing, alignment và bounds.
- [Arena — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát native memory, vòng đời và thread confinement.
- [MemorySegment — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): API tại phiên bản giới thiệu.
- [Memory Segments and Arenas — Java 25 Core Libraries Guide](https://docs.oracle.com/en/java/javase/25/core/memory-segments-and-arenas.html): hướng dẫn về heap, native memory và quản lý Arena.

