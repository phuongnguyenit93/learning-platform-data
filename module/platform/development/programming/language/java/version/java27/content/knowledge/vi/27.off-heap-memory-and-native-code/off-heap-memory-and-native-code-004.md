# Đọc ghi dữ liệu native và kiểm tra biên truy cập

Trong Java 27, ứng dụng có thể cần đọc và ghi những vùng nhớ **nằm ngoài Java heap** để trao đổi dữ liệu với mã native, xử lý cấu trúc nhị phân hoặc giảm một số chi phí sao chép. Khác với đối tượng Java thông thường, native memory có vòng đời, căn chỉnh và quy ước biểu diễn dữ liệu cần được quản lý rõ ràng. Đọc sai offset hoặc dùng bộ nhớ sau khi đã giải phóng có thể dẫn tới lỗi nghiêm trọng nếu làm việc trực tiếp với con trỏ thô.

API **Foreign Function & Memory (FFM)** ổn định trong Java hiện đại cung cấp các kiểu thuộc package **java.lang.foreign**, đặc biệt:

- **MemorySegment**: mô tả một vùng bộ nhớ có giới hạn kích thước và vòng đời.
- **Arena**: cấp phát native memory và quản lý thời điểm các segment được vô hiệu hóa/giải phóng.
- **ValueLayout**: mô tả loại giá trị, kích thước, thứ tự byte và yêu cầu căn chỉnh của thao tác đọc/ghi.
- **MemoryLayout**: mô tả bố cục của dãy phần tử, cấu trúc hoặc tổ hợp nhiều trường.

Bài thuộc chương **Bộ nhớ ngoài heap và mã native** của học phần **Java 27 và các kiến thức liên quan**. Trọng tâm là **đọc ghi dữ liệu native và kiểm tra biên truy cập**, với ví dụ Java 27 tự chứa, không dựa vào API incubator/preview đã được thay thế. Việc gọi hàm C bằng linker và downcall được nêu ở mức ranh giới cần thận trọng, không phải mục tiêu chính.

## 1. Native memory là gì, khác Java heap thế nào?

Java heap chứa những đối tượng do JVM quản lý như **String**, **List**, **record** hay mảng Java. Garbage collector quản lý khả năng thu hồi vùng heap khi đối tượng không còn được tham chiếu.

Native memory, trong ngữ cảnh bài học, là bộ nhớ nằm ngoài Java heap mà ứng dụng có thể cấp phát hoặc nhận từ một thư viện native. Việc sử dụng native memory thường đòi hỏi làm rõ ai sở hữu nó và khi nào vùng nhớ hết hiệu lực.

~~~text
          Ứng dụng Java 27
                   |
        +----------+----------+
        |                     |
        v                     v
  Heap Java              Native memory
  byte[], int[]          Vùng byte off-heap
  Đối tượng JVM          Được quản lý bằng Arena
        |                     |
        v                     v
  MemorySegment.ofArray  arena.allocate(...)
        |                     |
        +----------+----------+
                   |
          MemorySegment API
          get/set/copy/slice
~~~

**MemorySegment có thể đại diện cho cả bộ nhớ heap và native**. Vì vậy, thấy một biến có kiểu MemorySegment chưa đủ để kết luận dữ liệu nằm ngoài heap; phải xem cách tạo segment.

| Đặc điểm | Heap segment | Native segment |
|---|---|---|
| Nguồn điển hình | **MemorySegment.ofArray(...)** | **Arena.allocate(...)** |
| Dữ liệu nằm ở đâu | Bên trong Java heap | Ngoài Java heap |
| Vòng đời | Gắn với vùng heap và đối tượng backing | Theo scope của Arena hoặc chủ sở hữu native |
| Truy cập qua FFM | Có | Có |
| Có kiểm tra bounds | Có | Có |
| Có thể bị giới hạn thread | Heap segment thông thường truy cập được từ nhiều thread | Tùy loại Arena/scope |
| Tự động bảo đảm giao dịch/atomic giữa thread | Không | Không |

Không chọn off-heap chỉ vì nghĩ rằng nó “luôn nhanh hơn”. Nó có thể làm tăng chi phí quản lý vòng đời, sao chép, căn chỉnh và tích hợp với mã native. Hãy sử dụng khi có nhu cầu rõ và đo hiệu năng trong workload thật.

## 2. FFM API hiện hành thay cho cách truy cập bộ nhớ không được hỗ trợ

Trong Java 27, lớp chính cho thao tác vùng nhớ là **java.lang.foreign.MemorySegment**. Có thể nhập:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

Ví dụ cấp phát và ghi một số nguyên:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);

    segment.set(ValueLayout.JAVA_INT, 0, 27);

    int value = segment.get(ValueLayout.JAVA_INT, 0);
    System.out.println(value); // 27
}
~~~

Các bước:

1. **Arena.ofConfined()** tạo một vùng quản lý bộ nhớ gắn với thread đang tạo Arena.
2. **arena.allocate(ValueLayout.JAVA_INT)** cấp phát native segment đủ chỗ và căn chỉnh thích hợp cho một int theo layout.
3. **set(...)** ghi int tại byte offset 0.
4. **get(...)** đọc int tại byte offset 0.
5. Kết thúc **try-with-resources** gọi **arena.close()**, làm các segment thuộc Arena hết hiệu lực.

Mẫu này không cần tính địa chỉ thô hay thao tác con trỏ qua API không công khai của JVM.

### Tránh mẫu mã lỗi thời

Không dùng namespace **jdk.incubator.foreign** như một hướng dẫn cho Java 27. FFM hiện hành nằm trong **java.lang.foreign**. Cũng không khuyến nghị phụ thuộc vào **sun.misc.Unsafe** hoặc những đoạn thao tác địa chỉ native không được bảo đảm bởi API Java SE chỉ để đọc/ghi một số nguyên.

FFM đã trở thành API chính thức từ Java 22; trong Java 27, các kiểu ở trên không cần bật preview chỉ để cấp phát và đọc/ghi segment. Một số thao tác native-access hạn chế ở phần liên kết/địa chỉ vẫn có quy tắc truy cập riêng và không nên đánh đồng với những lời gọi get/set thông thường.

## 3. Ba lớp bảo vệ: không gian, thời gian và thread

Một MemorySegment có ba nhóm điều kiện an toàn quan trọng:

1. **Spatial bounds — biên không gian:** byte đọc/ghi phải nằm hoàn toàn trong vùng segment.
2. **Temporal bounds — biên thời gian:** scope của segment phải còn sống khi truy cập.
3. **Thread confinement — hạn chế thread:** nếu segment thuộc Arena confined, chỉ thread được phép mới có thể truy cập.

~~~text
MemorySegment: kích thước 16 byte
+------------------------------------------------+
| byte 0 ... byte 15                             |
+------------------------------------------------+
  ^                  ^                         ^
  |                  |                         |
  hợp lệ nếu          truy cập nhiều byte        sau byte 15
  layout phù hợp      phải nằm trọn trong       là ngoài biên
                     phạm vi

Arena còn mở? ---- không ---> IllegalStateException
Thread phù hợp? -- không ---> WrongThreadException
Offset hợp lệ? --- không ---> IndexOutOfBoundsException
Alignment đúng? -- không ---> IllegalArgumentException
~~~

Những kiểm tra này áp dụng cho **đường truy cập qua MemorySegment API**. Chúng không có nghĩa việc chuyển con trỏ sang thư viện C tùy ý sẽ làm C tự động kiểm tra mọi truy cập hoặc miễn nhiễm với use-after-free. Mã native bên ngoài có thể có lỗi riêng.

## 4. Cấp phát đúng kích thước và alignment

Một số kiểu cấp phát thường dùng:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment bytes = arena.allocate(16);
    MemorySegment aligned = arena.allocate(16, 8);
    MemorySegment oneInt = arena.allocate(ValueLayout.JAVA_INT);
    MemorySegment fourInts =
            arena.allocate(ValueLayout.JAVA_INT, 4);
}
~~~

Ý nghĩa:

- **allocate(16)**: cấp phát 16 byte, không mô tả riêng một cấu trúc dữ liệu.
- **allocate(16, 8)**: cấp phát 16 byte với yêu cầu căn chỉnh 8 byte.
- **allocate(JAVA_INT)**: lấy kích thước và alignment từ layout của int.
- **allocate(JAVA_INT, 4)**: cấp phát vùng đủ cho bốn phần tử có layout int.

Kích thước được đo bằng **byte**, không phải “số đối tượng”. Khi thao tác với nhiều giá trị int, dùng overload nhận **ValueLayout** và **elementCount** tránh nhầm số phần tử với số byte.

### Byte size và alignment

~~~java
System.out.println(ValueLayout.JAVA_INT.byteSize());      // 4
System.out.println(ValueLayout.JAVA_INT.byteAlignment()); // 4
~~~

**ValueLayout.JAVA_INT** có kích thước 4 byte và yêu cầu căn chỉnh theo layout chuẩn của Java. Khi làm việc với C ABI thật, bố cục và kích thước kiểu native cần tuân theo thông tin ABI của môi trường, không được mặc định mọi kiểu C đều tương ứng đơn giản với một kiểu Java.

### Cấp phát theo số phần tử do người dùng cung cấp

Khi kích thước đến từ đầu vào bên ngoài, phải giới hạn mức sử dụng bộ nhớ:

~~~java
static MemorySegment allocateInts(Arena arena, long count) {
    if (count < 0 || count > 1_000_000) {
        throw new IllegalArgumentException("Invalid element count");
    }

    return arena.allocate(ValueLayout.JAVA_INT, count);
}
~~~

**Arena không phải bộ giới hạn quota của ứng dụng**. Dù Java kiểm tra một số điều kiện kích thước, ứng dụng vẫn phải hạn chế yêu cầu cấp phát quá lớn, kiểm soát concurrency và xử lý lỗi tài nguyên theo chính sách.

## 5. get() và set(): byte offset chứ không phải index phần tử

Cặp method cơ bản:

~~~java
int value = segment.get(ValueLayout.JAVA_INT, byteOffset);
segment.set(ValueLayout.JAVA_INT, byteOffset, value);
~~~

Tham số thứ hai là **byte offset** tương đối với đầu segment.

Ví dụ:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment =
            arena.allocate(ValueLayout.JAVA_INT, 3);

    segment.set(ValueLayout.JAVA_INT, 0, 100);
    segment.set(ValueLayout.JAVA_INT, 4, 200);
    segment.set(ValueLayout.JAVA_INT, 8, 300);

    System.out.println(segment.get(ValueLayout.JAVA_INT, 4));
    // 200
}
~~~

Với int dài 4 byte:

| Phần tử | Byte offset | Vùng byte được sử dụng |
|---|---|---|
| 0 | 0 | 0..3 |
| 1 | 4 | 4..7 |
| 2 | 8 | 8..11 |

**segment.get(JAVA_INT, 1)** không có nghĩa “đọc phần tử thứ nhất”; đó là yêu cầu đọc một int bắt đầu tại **byte offset 1**, thường vi phạm alignment của JAVA_INT.

### Đọc các kiểu giá trị khác

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, 8);

    segment.set(ValueLayout.JAVA_LONG, 0, 42L);
    segment.set(ValueLayout.JAVA_DOUBLE, 8, 3.5);

    long id = segment.get(ValueLayout.JAVA_LONG, 0);
    double rate = segment.get(ValueLayout.JAVA_DOUBLE, 8);

    System.out.println(id);   // 42
    System.out.println(rate); // 3.5
}
~~~

Chọn đúng layout làm rõ kích thước, kiểu carrier, thứ tự byte và yêu cầu căn chỉnh. Việc ghi một kiểu rồi đọc bằng một kiểu khác cần có định dạng nhị phân được xác định, không phải phép chuyển kiểu số thông thường.

## 6. getAtIndex() và setAtIndex(): làm việc với dãy giá trị

Khi vùng nhớ chứa một dãy phần tử có layout đồng nhất, các method **getAtIndex()** và **setAtIndex()** tự tính byte offset từ chỉ số phần tử.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment numbers =
            arena.allocate(ValueLayout.JAVA_INT, 4);

    for (int i = 0; i < 4; i++) {
        numbers.setAtIndex(ValueLayout.JAVA_INT, i, (i + 1) * 10);
    }

    for (int i = 0; i < 4; i++) {
        System.out.println(
                numbers.getAtIndex(ValueLayout.JAVA_INT, i));
    }
}
~~~

Kết quả:

~~~text
10
20
30
40
~~~

Ở đây, **getAtIndex(JAVA_INT, 2)** tương ứng với byte offset **2 × 4 = 8**.

Nếu dùng index âm, index vượt số phần tử hoặc phép tính offset vượt phạm vi segment, Java sẽ báo lỗi qua cơ chế bounds checking của API. Không cần tự lấy địa chỉ native rồi cộng **index * 4** để bỏ qua kiểm tra.

### Phân biệt count, byteSize và vị trí cuối cùng

Nếu cấp phát bốn int, vùng nhớ có **16 byte**. Index hợp lệ là **0..3**. Index **4** là ngoài phạm vi, dù 4 nhìn có vẻ nhỏ hơn **byteSize() = 16**.

Đừng so sánh **index < segment.byteSize()** để kiểm tra index phần tử; phải quy đổi theo kích thước layout hoặc trực tiếp dùng **getAtIndex/setAtIndex** và xử lý đúng ngoại lệ.

## 7. Kiểm tra ngoài biên: IndexOutOfBoundsException

Một thao tác đọc/ghi phải đáp ứng:

- **offset >= 0**.
- **số byte cần truy cập** phải đủ để nằm trọn trong segment.
- Không được xảy ra overflow khi tính offset hoặc kích thước.

Ví dụ:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment =
            arena.allocate(ValueLayout.JAVA_INT, 2); // 8 byte.

    segment.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
    segment.setAtIndex(ValueLayout.JAVA_INT, 1, 20);

    try {
        segment.getAtIndex(ValueLayout.JAVA_INT, 2);
    } catch (IndexOutOfBoundsException exception) {
        System.out.println("Index out of bounds");
    }
}
~~~

Kết quả:

~~~text
Index out of bounds
~~~

**Không có vùng byte dành cho int thứ ba**. API ném ngoại lệ ở đường truy cập thay vì cố đọc sang vùng địa chỉ lân cận.

### Kiểm tra biên thủ công đúng cách

Khi cần thông báo lỗi rõ trước khi gọi FFM, có thể kiểm tra byte range:

~~~java
static void requireRange(
        MemorySegment segment, long offset, long bytes) {

    if (offset < 0
            || bytes < 0
            || bytes > segment.byteSize()
            || offset > segment.byteSize() - bytes) {
        throw new IndexOutOfBoundsException(
                "Invalid memory range");
    }
}
~~~

Điểm quan trọng của biểu thức **offset > size - bytes** là tránh tự cộng **offset + bytes** rồi vô tình overflow số long.

Dù có kiểm tra thủ công, **không nên bỏ kiểm tra của MemorySegment API**. Giữa thời điểm validate và thời điểm truy cập, scope có thể đóng hoặc thread có thể không phù hợp; các điều kiện khác như alignment/read-only cũng cần được xử lý.

## 8. Căn chỉnh: vì sao offset hợp lệ vẫn có thể bị từ chối?

Đọc một int cần bốn byte liên tiếp, nhưng layout chuẩn của int còn có ràng buộc **alignment**.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment =
            arena.allocate(8, ValueLayout.JAVA_INT.byteAlignment());

    // Byte offset 1 + 4 vẫn nằm trong 8 byte,
    // nhưng offset 1 không thỏa alignment 4 của JAVA_INT.
    try {
        segment.get(ValueLayout.JAVA_INT, 1);
    } catch (IllegalArgumentException exception) {
        System.out.println("Unaligned access rejected");
    }
}
~~~

Kết quả:

~~~text
Unaligned access rejected
~~~

Đây là tình huống khác với **IndexOutOfBoundsException**: dữ liệu có thể nằm trong phạm vi byte nhưng cách truy cập không tương thích với yêu cầu căn chỉnh.

### Khi định dạng nhị phân thật sự không căn chỉnh

Java có những **unaligned value layouts**, chẳng hạn **ValueLayout.JAVA_INT_UNALIGNED**, có alignment bằng 1.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(5);

    data.set(ValueLayout.JAVA_INT_UNALIGNED, 1, 1234);

    int value = data.get(ValueLayout.JAVA_INT_UNALIGNED, 1);
    System.out.println(value); // 1234
}
~~~

**Chỉ dùng unaligned layout khi cấu trúc dữ liệu thực sự đòi hỏi.** Việc truy cập lệch căn chỉnh có thể ảnh hưởng hiệu năng hoặc tính di động, và không nên xem đó là cách chữa mọi lỗi offset.

Khi thiết kế cấu trúc native mới, ưu tiên bố trí trường có alignment hợp lý thay vì chọn unaligned layout cho tất cả.

## 9. Byte order: little-endian và big-endian

Trong định dạng nhị phân, thứ tự các byte của một giá trị nhiều byte phải được xác định rõ.

- **Little-endian** đặt byte có trọng số thấp ở địa chỉ thấp trước.
- **Big-endian** đặt byte có trọng số cao ở địa chỉ thấp trước.

Các layout chuẩn như **ValueLayout.JAVA_INT** mặc định dùng **ByteOrder.nativeOrder()**, có thể phụ thuộc nền tảng. Vì vậy, khi đọc một định dạng tệp, gói mạng hoặc C struct đã xác định byte order, không nên dựa ngầm vào native order.

~~~java
import java.nio.ByteOrder;
import java.lang.foreign.ValueLayout;

ValueLayout.OfInt littleEndianInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);

ValueLayout.OfInt bigEndianInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
~~~

### Ví dụ độc lập với endianness của máy

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data =
            arena.allocate(ValueLayout.JAVA_INT);

    ValueLayout.OfInt little =
            ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);

    data.set(little, 0, 0x01020304);

    System.out.printf("%08X%n", data.get(little, 0));
    // 01020304

    for (long i = 0; i < 4; i++) {
        System.out.printf(
                "%02X ",
                Byte.toUnsignedInt(data.get(ValueLayout.JAVA_BYTE, i)));
    }
    System.out.println();
    // 04 03 02 01
}
~~~

Mọi byte offset trong ví dụ đều hợp lệ. Mã không giả định CPU chạy little-endian: layout chỉ định rõ cách diễn giải và ghi byte.

### Lưu ý khi trao đổi với hệ thống ngoài

Byte order là một phần của **hợp đồng định dạng dữ liệu**, không phải chi tiết có thể bỏ qua. Khi đọc/ghi tệp hoặc gọi thư viện C, cần xác định kích thước trường, byte order, signedness và padding theo tài liệu của giao thức hoặc ABI.

## 10. Slice: thu nhỏ biên truy cập của một vùng nhớ

**MemorySegment.asSlice(offset, size)** tạo một segment mới trỏ đến **cùng vùng nhớ**, nhưng chỉ nhìn thấy một phần được giới hạn rõ.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment all =
            arena.allocate(ValueLayout.JAVA_INT, 4);

    all.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
    all.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
    all.setAtIndex(ValueLayout.JAVA_INT, 2, 30);
    all.setAtIndex(ValueLayout.JAVA_INT, 3, 40);

    MemorySegment secondHalf = all.asSlice(8, 8);

    System.out.println(
            secondHalf.getAtIndex(ValueLayout.JAVA_INT, 0)); // 30

    System.out.println(
            secondHalf.getAtIndex(ValueLayout.JAVA_INT, 1)); // 40
}
~~~

**secondHalf** có đúng 8 byte; offset 0 của nó tương ứng byte offset 8 của **all**.

### Slice không phải bản sao

~~~java
secondHalf.setAtIndex(ValueLayout.JAVA_INT, 0, 99);

System.out.println(all.getAtIndex(ValueLayout.JAVA_INT, 2));
// 99
~~~

Vì cả hai segment cùng tham chiếu vùng nhớ, thay đổi qua slice được quan sát qua segment gốc khi các điều kiện đồng bộ/vòng đời cho phép.

Slice có:

- Biên không gian riêng, nhỏ hơn hoặc bằng segment nguồn.
- Vòng đời gắn với scope tương ứng của vùng nhớ.
- Quy tắc thread/accessibility và khả năng read-only liên quan.

**Không trả slice ra ngoài phạm vi sống của Arena rồi giả định nó vẫn hợp lệ.** Slice không kéo dài vòng đời native memory một cách độc lập.

## 11. Cắt biên truy cập khi cấp một vùng dữ liệu cho thành phần khác

Giả sử một buffer gồm header 8 byte và payload 24 byte.

~~~text
Whole segment: 32 byte
+------------------+------------------------------+
| Header (8 byte)  | Payload (24 byte)            |
+------------------+------------------------------+
0                  8                              32
~~~

Có thể cấp cho parser chỉ phần payload:

~~~java
MemorySegment whole = arena.allocate(32, 8);
MemorySegment payload = whole.asSlice(8, 24);

parsePayload(payload);
~~~

Ví dụ giả định **arena** và **parsePayload(...)** được định nghĩa trong cùng phạm vi còn sống.

Lợi ích của việc truyền slice:

- Parser nhận đúng phạm vi byte nó được phép truy cập.
- Nếu parser cố đọc vượt quá 24 byte bằng MemorySegment API, Java báo lỗi.
- Không cần tiết lộ offset tuyệt đối của cả vùng nhớ cho mọi hàm xử lý.
- Hạn chế lỗi khi parser lẫn header với payload.

Tuy nhiên, việc **cấp slice không tương đương sandbox bảo mật hoàn chỉnh**. Nếu parser giữ thêm tham chiếu segment gốc hoặc gọi mã native không kiểm tra bounds, các bảo đảm khác vẫn cần thiết.

## 12. Copy dữ liệu: native-to-native và heap-to-native

Một vùng nhớ có thể được sao chép bằng **MemorySegment.copy(...)** theo số byte.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment source =
            arena.allocate(ValueLayout.JAVA_INT, 3);

    source.setAtIndex(ValueLayout.JAVA_INT, 0, 7);
    source.setAtIndex(ValueLayout.JAVA_INT, 1, 8);
    source.setAtIndex(ValueLayout.JAVA_INT, 2, 9);

    MemorySegment target =
            arena.allocate(ValueLayout.JAVA_INT, 3);

    MemorySegment.copy(
            source, 0,
            target, 0,
            source.byteSize());

    System.out.println(
            target.getAtIndex(ValueLayout.JAVA_INT, 1)); // 8
}
~~~

**MemorySegment.copy** kiểm tra cả biên nguồn và biên đích. Nếu yêu cầu sao chép vượt kích thước một trong hai, thao tác sẽ báo **IndexOutOfBoundsException** theo hợp đồng.

### Sao chép từ mảng Java

~~~java
int[] values = {10, 20, 30};

MemorySegment heap = MemorySegment.ofArray(values);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeCopy =
            arena.allocate(ValueLayout.JAVA_INT, values.length);

    MemorySegment.copy(
            heap, 0,
            nativeCopy, 0,
            heap.byteSize());

    System.out.println(
            nativeCopy.getAtIndex(ValueLayout.JAVA_INT, 2)); // 30
}
~~~

**MemorySegment.ofArray(values)** không cấp phát một bản sao native ngay; nó tạo heap segment hỗ trợ truy cập trên mảng có sẵn. **MemorySegment.copy** mới là bước chuyển nội dung sang nativeCopy.

### Bảo đảm gì khi copy?

Copy theo byte sao chép biểu diễn dữ liệu. Nó **không tự chuyển đổi byte order** của trường dữ liệu nhiều byte. Khi cần sao chép có chuyển đổi thứ tự byte từng phần tử, API còn có overload nhận source/destination value layout. Cần quyết định rõ đang sao chép **raw bytes** hay **giá trị có cấu trúc**.

## 13. Chuyển dữ liệu native trở lại mảng Java

Khi cần trả dữ liệu ra các API Java không dùng FFM, có thể sao chép về mảng:

~~~java
int[] result;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeValues =
            arena.allocate(ValueLayout.JAVA_INT, 3);

    nativeValues.setAtIndex(ValueLayout.JAVA_INT, 0, 3);
    nativeValues.setAtIndex(ValueLayout.JAVA_INT, 1, 6);
    nativeValues.setAtIndex(ValueLayout.JAVA_INT, 2, 9);

    result = nativeValues.toArray(ValueLayout.JAVA_INT);
}

System.out.println(java.util.Arrays.toString(result));
// [3, 6, 9]
~~~

Kết quả **int[]** là một mảng Java độc lập có thể sống sau khi Arena đã đóng. Đây là cách chuyển dữ liệu ra khỏi native memory khi caller cần tiếp tục dùng kết quả lâu hơn phạm vi Arena.

**Khác với slice**, thao tác **toArray(...)** tạo bản sao dữ liệu tương ứng; sửa mảng kết quả không tự thay đổi vùng native ban đầu.

Cần cẩn thận với lượng dữ liệu: một mảng Java có giới hạn kích thước và chi phí heap. Trước khi chuyển một segment rất lớn thành mảng, hãy xác định khả năng chứa và nhu cầu bộ nhớ.

## 14. Read-only view: chặn ghi qua một tham chiếu

**asReadOnly()** tạo view chỉ đọc của segment:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment writable =
            arena.allocate(ValueLayout.JAVA_INT);

    writable.set(ValueLayout.JAVA_INT, 0, 27);

    MemorySegment readOnly = writable.asReadOnly();

    System.out.println(
            readOnly.get(ValueLayout.JAVA_INT, 0)); // 27

    System.out.println(readOnly.isReadOnly()); // true

    try {
        readOnly.set(ValueLayout.JAVA_INT, 0, 99);
    } catch (IllegalArgumentException exception) {
        System.out.println("Write rejected");
    }
}
~~~

Read-only segment ngăn thao tác ghi qua **view đó** theo hợp đồng FFM.

**Không hiểu nhầm read-only view với snapshot bất biến.** Nếu còn một tham chiếu writable tới cùng vùng nhớ, việc ghi qua tham chiếu writable vẫn có thể làm nội dung readOnly view thay đổi. Nó cũng không ngăn mã native có quyền truy cập độc lập tới vùng nhớ sửa dữ liệu.

Dùng read-only view khi muốn biểu đạt quyền truy cập và giúp phát hiện thao tác ghi nhầm, không phải thay thế cơ chế phân quyền cấp hệ điều hành.

## 15. Arena.ofConfined(): vòng đời gắn với thread tạo

Arena confined được thiết kế cho trường hợp một thread tạo, dùng rồi đóng các native segment:

~~~java
MemorySegment escaped;

try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(ValueLayout.JAVA_LONG);
    escaped.set(ValueLayout.JAVA_LONG, 0, 123L);
}

try {
    escaped.get(ValueLayout.JAVA_LONG, 0);
} catch (IllegalStateException exception) {
    System.out.println("Segment scope already closed");
}
~~~

Khi Arena đóng, bộ nhớ backing của các segment thuộc Arena được giải phóng theo hợp đồng, và việc truy cập segment qua FFM sẽ thất bại vì scope không còn sống.

### Tránh trả về segment thuộc Arena sắp đóng

~~~java
// Không nên dùng nếu caller cần đọc segment sau khi method trả về:
static MemorySegment broken() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    }
}
~~~

Caller nhận một segment có scope đã đóng. Thay vào đó:

- Để **caller sở hữu Arena** và truyền nó vào method tạo segment.
- Hoặc đọc dữ liệu trong phạm vi Arena rồi trả **int**, **record** hay **mảng Java** độc lập.
- Hoặc dùng một đối tượng quản lý đóng rõ ràng có vòng đời dài hơn method nếu thật sự cần.

### Không đóng Arena quá sớm khi có native call

Nếu bộ nhớ được truyền tới thư viện native, nó phải tiếp tục còn hiệu lực trong toàn bộ khoảng thời gian bên native được phép sử dụng. Đừng đóng Arena ngay sau khi gọi một native method trả về nếu thư viện vẫn giữ con trỏ để sử dụng bất đồng bộ về sau.

Quyền sở hữu và thời điểm thu hồi phải theo hợp đồng thư viện native, không chỉ theo vị trí kết thúc một block Java.

## 16. Arena.ofShared() và hạn chế thread

Nếu segment cần được truy cập từ nhiều thread, **Arena.ofShared()** cho phép nhiều thread phù hợp truy cập vùng nhớ.

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment values =
            arena.allocate(ValueLayout.JAVA_INT, 2);

    values.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
    values.setAtIndex(ValueLayout.JAVA_INT, 1, 20);

    Thread reader = Thread.ofVirtual().start(() ->
            System.out.println(
                    values.getAtIndex(ValueLayout.JAVA_INT, 1)));

    reader.join();
}
~~~

Đoạn trên nằm trong method khai báo hoặc xử lý **InterruptedException** cho **join()**. Luồng mới được phép truy cập segment trong khi shared arena còn mở; thread chính **join()** trước khi đóng Arena để tránh tranh chấp vòng đời.

### Shared không tự động đồng nghĩa atomic

**Arena.ofShared()** nới điều kiện thread accessibility, nhưng **không** biến một chuỗi đọc–sửa–ghi thành giao dịch nguyên tử. Nhiều thread cùng thay đổi một vị trí nhớ có thể gây data race nếu không dùng cơ chế đồng bộ/memory ordering phù hợp.

Khi chia dữ liệu giữa nhiều thread:

- Tránh ghi chồng lên cùng vùng nhớ nếu không có đồng bộ.
- Nếu có thể, chia segment thành các **slice không chồng lấn** và giao từng slice cho một worker.
- Nếu cần giá trị atomic, nghiên cứu **VarHandle** và các access mode được layout tương ứng hỗ trợ.
- Xác định rõ thời điểm các thread hoàn thành trước khi đóng Arena.
- Không tin rằng **volatile** trên một biến tham chiếu tới segment sẽ làm mọi byte bên trong segment trở thành atomic.

### WrongThreadException với confined arena

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment value =
            arena.allocate(ValueLayout.JAVA_INT);

    Thread other = Thread.ofVirtual().start(() -> {
        try {
            value.get(ValueLayout.JAVA_INT, 0);
        } catch (WrongThreadException exception) {
            System.out.println("Wrong thread");
        }
    });

    other.join();
}
~~~

**WrongThreadException** thuộc **java.lang**, nên không cần import riêng. Đoạn mã giả định method chứa nó có xử lý hoặc khai báo **InterruptedException** cho **join()**.

Thông điệp quan trọng: một segment có đủ byte và Arena còn sống vẫn có thể **không được phép truy cập từ thread khác**.

## 17. Các loại Arena và cách chọn

| Loại Arena | Thời gian sống | Đóng tường minh | Truy cập nhiều thread | Khi nào cân nhắc |
|---|---|---|---|---|
| **Arena.ofConfined()** | Có giới hạn | Có | Không | Xử lý một thread, vòng đời rõ |
| **Arena.ofShared()** | Có giới hạn | Có | Có | Nhiều thread cùng cần truy cập trong phạm vi quản lý |
| **Arena.ofAuto()** | Được runtime/GC quản lý | Không | Có | Khi chấp nhận thời điểm thu hồi không xác định |
| **Arena.global()** | Không giới hạn theo vòng đời ứng dụng | Không | Có | Chỉ khi vùng nhớ thật sự cần sống rất lâu |

**Ưu tiên Arena có thể đóng tường minh** khi ứng dụng sở hữu native memory và biết được điểm kết thúc công việc.

### Lưu ý về ofAuto() và global()

- **Arena.ofAuto()** không cho phép caller quyết định chính xác thời điểm giải phóng. Nó không thay thế try-with-resources khi cần thu hồi đúng lúc.
- **Arena.global()** có vòng đời không giới hạn; bộ nhớ cấp phát từ global arena không được tự động giải phóng theo cách của confined/shared arena trong suốt vòng đời thông thường.
- Gọi **close()** trên automatic/global arena không có tác dụng đóng bình thường và có thể ném **UnsupportedOperationException**.

Không sử dụng global arena như một cách bỏ qua xử lý vòng đời hoặc để che lỗi use-after-close. Nó có thể gây tăng mức sử dụng native memory không kiểm soát nếu bị lạm dụng.

## 18. MemoryLayout: diễn tả cấu trúc nhiều trường

Trong dữ liệu native, một record có thể có nhiều trường với kích thước và alignment khác nhau. **MemoryLayout** giúp biểu diễn bố cục rõ ràng hơn phép cộng offset rải rác.

Ví dụ cấu trúc có:

- Một trường **version** kiểu int (4 byte).
- Một khoảng padding 4 byte để trường sau căn theo 8 byte.
- Một trường **length** kiểu long (8 byte).

~~~text
Offset    Kích thước    Ý nghĩa
0         4 byte        version
4         4 byte        padding
8         8 byte        length
Tổng      16 byte
~~~

Khai báo layout:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.ValueLayout;

MemoryLayout headerLayout = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("version"),
        MemoryLayout.paddingLayout(4),
        ValueLayout.JAVA_LONG.withName("length")
);

long versionOffset =
        headerLayout.byteOffset(PathElement.groupElement("version"));

long lengthOffset =
        headerLayout.byteOffset(PathElement.groupElement("length"));
~~~

Sử dụng:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment header = arena.allocate(headerLayout);

    header.set(ValueLayout.JAVA_INT, versionOffset, 27);
    header.set(ValueLayout.JAVA_LONG, lengthOffset, 1024L);

    System.out.println(
            header.get(ValueLayout.JAVA_INT, versionOffset)); // 27

    System.out.println(
            header.get(ValueLayout.JAVA_LONG, lengthOffset)); // 1024
}
~~~

Layout giúp ràng buộc ý nghĩa trường và offset. **Padding cần được thiết kế rõ**; không nên mặc định Java tự suy ra và thêm toàn bộ padding của C compiler trong mọi tình huống.

### Tương thích C struct phải dựa vào ABI

Một C struct có thể có kích thước, alignment hoặc padding khác theo platform/ABI/compiler. Đừng mặc định **JAVA_LONG** luôn đồng nghĩa với **C long** trên mọi nền tảng. Nếu đang xây binding native thật, phải dùng thông tin ABI và layout phù hợp từ FFM linker/canonical layouts hoặc đặc tả C tương ứng.

Cú pháp Java đúng chưa đủ để bảo đảm layout binary tương thích C trên nhiều hệ điều hành.

## 19. SequenceLayout và xử lý dữ liệu dạng mảng

**MemoryLayout.sequenceLayout(count, elementLayout)** mô tả một dãy phần tử đồng nhất.

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.ValueLayout;

SequenceLayout vectorLayout =
        MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_FLOAT);
~~~

Kết hợp với Arena:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment vector = arena.allocate(vectorLayout);

    vector.setAtIndex(ValueLayout.JAVA_FLOAT, 0, 1.0f);
    vector.setAtIndex(ValueLayout.JAVA_FLOAT, 1, 2.0f);
    vector.setAtIndex(ValueLayout.JAVA_FLOAT, 2, 3.0f);
    vector.setAtIndex(ValueLayout.JAVA_FLOAT, 3, 4.0f);

    float sum = 0;

    for (long i = 0; i < 4; i++) {
        sum += vector.getAtIndex(ValueLayout.JAVA_FLOAT, i);
    }

    System.out.println(sum); // 10.0
}
~~~

Các chỉ số được nhân với kích thước element layout. Sử dụng **arena.allocate(vectorLayout)** tránh tự tính byteSize từ số phần tử nếu layout phức tạp.

Khi dữ liệu chứa nhiều struct, có thể kết hợp SequenceLayout với GroupLayout và đường dẫn trường; nhưng nên giữ API đọc/ghi ở một tầng rõ ràng để hạn chế việc dùng offset sai.

## 20. Không được đoán kích thước vùng nhớ từ một con trỏ

Một lỗi nguy hiểm khi tương tác với native code là nhận một con trỏ rồi **tự đoán vùng nhớ nó trỏ tới có bao nhiêu byte**.

Trong FFM, một giá trị địa chỉ lấy qua layout **ValueLayout.ADDRESS** có thể được biểu diễn bằng native MemorySegment **có kích thước bằng 0**. Chỉ biết địa chỉ không đủ để truy cập hợp lệ tới phần dữ liệu phía sau.

~~~java
// Ví dụ ý tưởng, không tự suy ra kích thước từ pointer:
// MemorySegment address = segment.get(ValueLayout.ADDRESS, offset);
// address.byteSize() có thể bằng 0.
~~~

Các thao tác tái diễn giải kích thước/quyền truy cập native như **reinterpret(...)** có thể là **restricted methods** và làm suy yếu những bảo đảm của segment nếu dữ liệu kích thước/ownership không đáng tin. Không nên sử dụng chúng như cách “chữa lỗi” **IndexOutOfBoundsException**.

### Quy tắc an toàn khi nhận pointer từ C

- Biết chính xác thư viện nào sở hữu vùng nhớ.
- Nhận **kích thước được khai báo rõ** hoặc layout chính thức đi kèm pointer.
- Xác định ai chịu trách nhiệm giải phóng và bằng cách nào.
- Không đọc dữ liệu sau khi thư viện đã giải phóng pointer.
- Không tạo segment với kích thước tự suy đoán hoặc coi địa chỉ là chứng cứ vùng nhớ hợp lệ.
- Không đọc hoặc ghi bên ngoài hợp đồng API native, kể cả khi Java cho phép một bước reinterpret.
- Tránh giữ con trỏ vượt quá thời hạn cho phép của một callback hoặc một lần native call.

**MemorySegment kiểm tra bounds dựa trên kích thước segment đã khai báo; nó không thể tự xác minh lời khẳng định sai của mã native về kích thước và thời hạn của một con trỏ.**

## 21. MemorySegment và ByteBuffer

Java vẫn có **ByteBuffer**, trong đó **ByteBuffer.allocateDirect(...)** tạo direct buffer. Với các tác vụ I/O, ByteBuffer vẫn là API thích hợp và hiện hành.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer buffer = ByteBuffer.allocateDirect(16)
        .order(ByteOrder.LITTLE_ENDIAN);

buffer.putInt(0, 27);

System.out.println(buffer.getInt(0)); // 27
~~~

Đây không phải API legacy. Không cần chuyển toàn bộ code ByteBuffer sang FFM chỉ vì Java có MemorySegment.

### Khi nào dùng mỗi API?

| Nhu cầu | API phù hợp |
|---|---|
| Đọc/ghi dữ liệu I/O thông thường qua channel | ByteBuffer và API java.nio |
| Điều khiển vòng đời native memory rõ ràng | MemorySegment + Arena |
| Biểu diễn C struct/union/sequence có layout rõ | MemoryLayout |
| Dùng giới hạn thời gian và thread của native segment | FFM scope/Arena |
| Tích hợp lời gọi hàm C | FFM Linker/FunctionDescriptor theo hợp đồng native access |
| Chỉ cần mảng dữ liệu Java | byte[], int[] hoặc đối tượng Java thích hợp |

Một MemorySegment có thể cung cấp view ByteBuffer qua **asByteBuffer()** cho những API tương thích. View có thể chia sẻ vùng nhớ, nên **không tự xem việc tạo ByteBuffer là sao chép** hoặc kéo dài vòng đời Arena. Cần kiểm tra và đặt rõ ByteOrder của ByteBuffer nếu dùng để đọc nhiều byte thành giá trị.

## 22. Bộ nhớ ngoài heap không tự thread-safe hay bảo mật

Native memory có thể nằm ngoài phạm vi quản lý trực tiếp của garbage collector, nhưng nó không miễn trừ ứng dụng khỏi các quy tắc về đồng thời và bảo vệ dữ liệu.

### Chia sẻ giữa thread

Nếu hai worker cùng sửa một bộ đếm trong shared Arena bằng các lời gọi get/set thông thường:

~~~java
// Không nên xem chuỗi này là một phép tăng nguyên tử:
int oldValue = segment.get(ValueLayout.JAVA_INT, 0);
segment.set(ValueLayout.JAVA_INT, 0, oldValue + 1);
~~~

Hai thread có thể cùng đọc giá trị cũ và cùng ghi một kết quả, tạo **lost update**. Nếu cần atomic access, xem các thao tác VarHandle được hỗ trợ cho layout và alignment phù hợp, hoặc phối hợp bằng khóa/cấu trúc đồng thời cấp ứng dụng.

### Dữ liệu nhạy cảm

Đừng cho rằng đóng Arena đồng nghĩa dữ liệu bí mật chắc chắn bị xóa an toàn khỏi mọi bản sao trong bộ nhớ. Trình biên dịch, hệ điều hành và việc sao chép dữ liệu có thể làm việc bảo đảm xóa sạch hoàn toàn trở nên phức tạp.

Nếu xử lý khóa hoặc bí mật:

- Giảm thời gian tồn tại và số lần sao chép.
- Hạn chế log hoặc chuyển dữ liệu sang String bất biến không cần thiết.
- Có chính sách xóa dữ liệu ở nơi phù hợp và kiểm tra tính chất của API thực sự được dùng.
- Không mô tả một thao tác **fill(0)** đơn lẻ là cam kết xóa tuyệt đối mọi bản sao.

## 23. Một số lỗi và ngoại lệ cần nhận biết

| Lỗi | Tình huống thường gặp | Hướng xử lý |
|---|---|---|
| **IndexOutOfBoundsException** | Offset âm, vượt biên hoặc đọc nhiều byte hơn vùng còn lại | Dùng byteSize, layout size, index và range đúng |
| **IllegalArgumentException** | Truy cập không đáp ứng alignment hoặc ghi qua read-only segment | Dùng layout/alignment đúng, tôn trọng quyền ghi |
| **IllegalStateException** | Truy cập segment khi scope/Arena đã đóng | Điều chỉnh ownership và vòng đời |
| **WrongThreadException** | Thread không có quyền truy cập confined segment | Giữ xử lý trên owner thread hoặc dùng shared arena khi cần |
| **UnsupportedOperationException** | Gọi thao tác không được hỗ trợ bởi loại Arena/segment | Chọn API đúng khả năng, không giả định mọi Arena đều closeable |
| **OutOfMemoryError** hoặc lỗi tài nguyên | Cấp phát native quá lớn hay không đủ nguồn lực | Giới hạn input, tổng mức cấp phát và concurrency |
| Dữ liệu đọc sai dù không ném lỗi | Nhầm endianness, signedness, padding hoặc cấu trúc | Đối chiếu hợp đồng binary/ABI |
| Dữ liệu bị ghi đè đồng thời | Shared memory không có đồng bộ | Chia slice không chồng lấn hoặc dùng đồng bộ |
| Không giải mã được dữ liệu sau chuyển nền tảng | Dựa ngầm vào native byte order/kiểu C | Ghi rõ format và canonical layout |
| Parser chỉ nhận pointer mà không có length | Không thể chứng minh phạm vi truy cập hợp lệ | Yêu cầu pointer + length + ownership chính xác |

Khi có lỗi bounds hoặc alignment, **không sửa bằng cách tăng size tùy tiện hay reinterpret một địa chỉ không được chứng thực**. Hãy sửa nguyên nhân ở phép tính offset hoặc mô hình dữ liệu.

## 24. Ví dụ tổng hợp có thể chạy độc lập

Ví dụ dưới đây kết hợp:

- Cấp phát bốn int trong native memory.
- Ghi/đọc theo index.
- Dùng slice để giới hạn truy cập.
- Thử đọc vượt biên và thử đọc lệch alignment.
- Tạo read-only view rồi thử ghi.
- Sao chép dữ liệu từ mảng Java vào native memory.
- Ghi/đọc một struct có padding và offset tính từ MemoryLayout.
- Ghi byte little-endian với layout tường minh.
- Kiểm tra truy cập sau khi Arena đóng.

Lưu thành **NativeMemoryDemo.java**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

public final class NativeMemoryDemo {
    private NativeMemoryDemo() {}

    private static final MemoryLayout HEADER =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("version"),
                    MemoryLayout.paddingLayout(4),
                    ValueLayout.JAVA_LONG.withName("length")
            );

    public static void main(String[] args) {
        MemorySegment escaped;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment values =
                    arena.allocate(ValueLayout.JAVA_INT, 4);

            for (int i = 0; i < 4; i++) {
                values.setAtIndex(
                        ValueLayout.JAVA_INT, i, (i + 1) * 10);
            }

            System.out.println(
                    "third=" +
                    values.getAtIndex(ValueLayout.JAVA_INT, 2));

            // Slice chỉ có hai int cuối.
            MemorySegment tail = values.asSlice(8, 8);

            System.out.println(
                    "tail-first=" +
                    tail.getAtIndex(ValueLayout.JAVA_INT, 0));

            try {
                tail.getAtIndex(ValueLayout.JAVA_INT, 2);
            } catch (IndexOutOfBoundsException exception) {
                System.out.println("bounds-check=PASS");
            }

            try {
                values.get(ValueLayout.JAVA_INT, 1);
            } catch (IllegalArgumentException exception) {
                System.out.println("alignment-check=PASS");
            }

            MemorySegment readOnly = values.asReadOnly();

            try {
                readOnly.set(ValueLayout.JAVA_INT, 0, 99);
            } catch (IllegalArgumentException exception) {
                System.out.println("read-only-check=PASS");
            }

            // Copy từ Java heap sang native.
            int[] source = {7, 8, 9};
            MemorySegment heap = MemorySegment.ofArray(source);
            MemorySegment nativeCopy =
                    arena.allocate(ValueLayout.JAVA_INT, source.length);

            MemorySegment.copy(
                    heap, 0, nativeCopy, 0, heap.byteSize());

            System.out.println(
                    "copy-third=" +
                    nativeCopy.getAtIndex(ValueLayout.JAVA_INT, 2));

            // Struct có padding xác định.
            long versionOffset =
                    HEADER.byteOffset(
                            PathElement.groupElement("version"));

            long lengthOffset =
                    HEADER.byteOffset(
                            PathElement.groupElement("length"));

            MemorySegment header = arena.allocate(HEADER);
            header.set(ValueLayout.JAVA_INT, versionOffset, 27);
            header.set(ValueLayout.JAVA_LONG, lengthOffset, 1024L);

            System.out.println(
                    "header-version=" +
                    header.get(ValueLayout.JAVA_INT, versionOffset));

            System.out.println(
                    "header-length=" +
                    header.get(ValueLayout.JAVA_LONG, lengthOffset));

            // Byte order không phụ thuộc vào CPU chạy chương trình.
            ValueLayout.OfInt little =
                    ValueLayout.JAVA_INT.withOrder(
                            ByteOrder.LITTLE_ENDIAN);

            MemorySegment encoded = arena.allocate(little);
            encoded.set(little, 0, 0x01020304);

            System.out.printf(
                    "encoded-int=%08X%n",
                    encoded.get(little, 0));

            escaped = values;
        }

        // Arena đã đóng, segment không còn được truy cập hợp lệ.
        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException exception) {
            System.out.println("scope-check=PASS");
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
third=30
tail-first=30
bounds-check=PASS
alignment-check=PASS
read-only-check=PASS
copy-third=9
header-version=27
header-length=1024
encoded-int=01020304
scope-check=PASS
~~~

### Giải thích từng bảo đảm

1. **arena.allocate(JAVA_INT, 4)** cấp phát đúng không gian và alignment cho bốn int.
2. **getAtIndex(...)** dùng chỉ số phần tử thay vì offset byte thủ công.
3. **tail.asSlice(...)** giới hạn không gian đọc xuống tám byte; index thứ ba của tail vượt biên.
4. **get(JAVA_INT, 1)** vẫn nằm trong kích thước segment gốc nhưng không đáp ứng alignment của int.
5. **asReadOnly()** không cho phép ghi qua view chỉ đọc.
6. **MemorySegment.copy(...)** sao chép ba int từ heap segment sang một native segment khác.
7. **HEADER.byteOffset(...)** tính offset theo tên trường và layout, có padding rõ ràng.
8. **withOrder(LITTLE_ENDIAN)** làm rõ định dạng byte khi ghi/đọc số nguyên.
9. **escaped** còn là một tham chiếu Java sau khi try kết thúc, nhưng native memory của nó đã hết vòng đời; API ném lỗi thay vì tiếp tục đọc.

Chương trình không gọi thư viện C hoặc dùng pointer không an toàn. Đây là ví dụ thực hành **FFM memory access ổn định** và các kiểm tra không gian/thời gian của Java 27.

## 25. Checklist khi đọc/ghi native memory

Trước khi triển khai một thao tác FFM đọc/ghi dữ liệu native, hãy xác nhận:

1. **Vùng nhớ ở heap hay off-heap?** MemorySegment được tạo bằng cách nào?
2. **Ai sở hữu native memory?** Arena và trách nhiệm close thuộc thành phần nào?
3. **Phạm vi sống đủ dài chưa?** Có return segment thuộc Arena sắp đóng không?
4. **Thread nào được truy cập?** Confined arena có bị dùng từ thread khác không?
5. **Byte size** có đúng và được giới hạn theo input không?
6. Offset dùng trong **get/set** là byte offset hay bị nhầm thành phần tử index?
7. Với mảng đồng nhất, có thể dùng **getAtIndex/setAtIndex** hoặc SequenceLayout không?
8. Mọi vùng đọc/ghi có nằm trọn trong **byteSize()** không, bao gồm khi tính số phần tử?
9. Alignment có đúng với layout và ABI không? Có đang dùng unaligned chỉ vì muốn bỏ qua một lỗi?
10. Byte order có được quy định tường minh cho dữ liệu ngoài JVM không?
11. Cấu trúc có padding đúng với định dạng nhị phân và C ABI mục tiêu không?
12. Slice đang được dùng như view hay caller hiểu nhầm thành bản sao?
13. Read-only view có bị hiểu nhầm là snapshot bất biến không?
14. Dữ liệu cần tồn tại sau khi Arena đóng đã được copy sang heap hoặc chuyển ownership hợp lệ chưa?
15. Nếu có nhiều thread, các vùng ghi có chồng lấn không và đã có đồng bộ chưa?
16. Nếu có con trỏ từ C, đã có kích thước, ownership và thời hạn hợp lệ được xác minh chưa?
17. Có đang dùng restricted reinterpret/địa chỉ thô chỉ để né lỗi bounds không?
18. Có giới hạn mức sử dụng native memory, kể cả khi nhiều request cùng cấp phát không?
19. Có kiểm thử **out of bounds, unaligned, read-only, use-after-close, wrong-thread** chưa?
20. Có tránh dùng API incubator hoặc Unsafe cho bài toán đã giải quyết bằng FFM chuẩn không?

## 26. Tài liệu API chính thức nên đối chiếu

Đối với Java 27, có thể tra cứu tài liệu chuẩn của các API được dùng trong bài:

- [MemorySegment — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): các thao tác get/set, slice, copy, bounds, temporal scope và thread accessibility.
- [Arena — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát, ownership, confined/shared/automatic/global arenas.
- [ValueLayout — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/ValueLayout.html): kích thước, alignment, byte order và các layout kiểu nguyên thủy.
- [MemoryLayout — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemoryLayout.html): sequence, group/struct, padding, layout paths và byte offset.

Hãy đối chiếu các ràng buộc của API với runtime và native library thật trước khi đưa mã vào sản phẩm. Các bảo đảm an toàn FFM có phạm vi rõ ràng; chúng không thay thế việc xem xét quyền sở hữu con trỏ hoặc hợp đồng bộ nhớ của C.

## Kết luận

Trong Java 27, **MemorySegment** và **Arena** là nền tảng chuẩn để đọc, ghi và quản lý dữ liệu native có kiểm tra biên. **ValueLayout** làm rõ kích thước, thứ tự byte, carrier type và yêu cầu alignment; **MemoryLayout** giúp mô tả cấu trúc nhiều trường mà không phải rải các phép cộng offset thủ công.

Khi dùng FFM đúng cách, Java kiểm tra **biên không gian**, **vòng đời scope** và **quyền truy cập theo thread** trên các đường thao tác MemorySegment. Tuy nhiên, native memory vẫn cần xác định **ownership, độ dài thực, layout/ABI, đồng bộ và thời điểm giải phóng**. Không tự tăng size, bỏ qua alignment hoặc reinterpret một pointer chưa được chứng thực chỉ để làm mã tiếp tục chạy.

Nguyên tắc bền vững là: **cấp phát theo layout, truy cập trong biên, giữ dữ liệu trong scope hợp lệ và chỉ chia sẻ native memory khi đã có hợp đồng đồng bộ rõ ràng**.
