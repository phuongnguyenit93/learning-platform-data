# Cấp phát vùng nhớ rồi đọc, ghi theo ValueLayout và vị trí byte

> **Chủ đề:** Java Advance → Native Interoperability → MemorySegment. Bài này hướng dẫn cách tạo một vùng nhớ bằng Foreign Function & Memory API (FFM), ghi/đọc giá trị Java thông qua `ValueLayout` tại **byte offset** cụ thể, giải thích endianness, alignment, giới hạn vùng nhớ và vòng đời `Arena`. Ví dụ dùng **JDK 22+**, vì FFM API trở thành tính năng chính thức ở Java 22 (JEP 454). Java 17 không có API ổn định `java.lang.foreign` được sử dụng ở đây.

## 1. Hiểu đúng ba thành phần: vùng nhớ, layout, vị trí byte

Trong Java thông thường, `int[]` quản lý các phần tử `int`. Khi tương tác với C/C++, thư viện native, một vùng memory-mapped file hoặc protocol nhị phân, ta thường phải làm việc với **các byte nằm liền nhau** và biết chính xác mỗi trường bắt đầu tại đâu.

FFM chia trách nhiệm thành ba khái niệm:

1. **`MemorySegment`**: một *view* an toàn có kiểm tra giới hạn tới một vùng nhớ liên tiếp. Nó biết vùng dài bao nhiêu byte (`byteSize()`), có còn hợp lệ không và thread nào được phép truy cập. Vùng nhớ có thể nằm ngoài heap hoặc được backing bởi Java array.
2. **`ValueLayout`**: mô tả một giá trị đơn chiếm bao nhiêu byte, yêu cầu căn chỉnh (alignment), thứ tự byte (endianness) và kiểu dữ liệu Java khi đọc/ghi; ví dụ `JAVA_INT` là giá trị `int` bốn byte.
3. **`long offset`** trong `segment.get(layout, offset)` và `segment.set(layout, offset, value)`: **số byte tính từ đầu segment**, bắt đầu ở 0; đây không phải chỉ số phần tử `int[]`.

Sơ đồ tổng quát:

```text
Arena (quản lý lifetime, allocation)
  |
  +-- allocate(24, 8) --> MemorySegment 24 byte
                           offset byte:
                           0   1   2   3   4   5   6   7
                           +---+---+---+---+---+---+---+---+ ...
                           |       int #1  |       int #2  |
                           +---+---+---+---+---+---+---+---+ ...
                           |               |
                     get(JAVA_INT, 0)  get(JAVA_INT, 4)

ValueLayout.JAVA_INT: size=4 byte, alignment thường=4 byte
                  ^
                  | dùng để diễn giải 4 byte từ offset đã chọn
```

**Điểm then chốt:** `ValueLayout` **không chứa dữ liệu**, chỉ là mô tả cách truy cập. `MemorySegment` **không tự hiểu** byte ở offset 8 là `long`, `int` hay UTF-8; caller quyết định bằng layout. Cùng bốn byte có thể cho kết quả khác nếu đổi kiểu, byte order hoặc offset.

## 2. Bắt đầu nhanh: tạo segment và đọc/ghi hai số nguyên

Chương trình Java 22+:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class FirstSegment {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(8, 4);

            // 8 byte, mỗi int dài 4 byte.
            segment.set(ValueLayout.JAVA_INT, 0, 100);
            segment.set(ValueLayout.JAVA_INT, 4, 200);

            System.out.println("size = " + segment.byteSize());
            System.out.println("first = " +
                    segment.get(ValueLayout.JAVA_INT, 0));
            System.out.println("second = " +
                    segment.get(ValueLayout.JAVA_INT, 4));
        } // Arena đóng, vùng native memory được giải phóng.
    }
}
```

Lưu thành **`FirstSegment.java`** và chạy:

```bash
javac FirstSegment.java
java FirstSegment
```

**stdout:**

```text
size = 8
first = 100
second = 200
```

Đây là một chương trình đầy đủ, dùng `java.lang.foreign` của JDK 22+; **không cần C compiler, JNI library hoặc `--enable-preview`**. Ví dụ chỉ thực hiện native memory allocation và Java memory access, không thực hiện *restricted downcall*. Với những thao tác FFM khác (đặc biệt native linker/restricted API), quyền native access có thể được yêu cầu tùy phiên bản JDK.

Vì sao offset là 0 và 4? Một `int` Java có **32 bit = 4 byte**. `set(JAVA_INT, 0, 100)` ghi bốn byte tại `[0,4)`; `set(JAVA_INT, 4, 200)` ghi bốn byte tại `[4,8)`. Nếu dùng offset 1 hoặc 5 với layout `JAVA_INT` thông thường, truy cập còn có khả năng vi phạm yêu cầu alignment.

## 3. Arena cấp phát native memory: kích thước, alignment và lifetime

### `Arena.ofConfined()` và `allocate`

`Arena` là object quản lý vòng đời và việc cấp phát **off-heap/native memory**. Cách dùng cơ bản:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment bytes = arena.allocate(24, 8);
    // byteSize = 24; địa chỉ bắt đầu có alignment 8 byte.
}
```

Đây là **trích đoạn minh họa**, giả định có `import java.lang.foreign.*;`. Hai tham số của `allocate(24, 8)` đều có **đơn vị byte**:

- `24`: cấp phát **24 byte** có thể đọc/ghi trong segment.
- `8`: yêu cầu địa chỉ bắt đầu được căn chỉnh theo **bội số 8 byte**.
- Kích thước không phải số phần tử; `arena.allocate(6, 4)` **không** tự cấp phát sáu `int`.
- `byteAlignment` phải là **lũy thừa của hai dương**. Kích thước không được âm; yêu cầu sai gây `IllegalArgumentException`.
- Nội dung của các native segments mới cấp phát qua các built-in arena được **khởi tạo bằng byte 0**. Tuy vậy vẫn nên ghi giá trị từng trường mà contract yêu cầu, tránh phụ thuộc vào byte padding hoặc giả định tương lai trong các context khác.

Hai cách thường thấy:

```java
// Cấp phát theo kích thước và alignment tính bằng byte.
MemorySegment raw = arena.allocate(16, 8);

// Cấp phát theo một layout: size/alignment từ layout.
MemorySegment oneLong = arena.allocate(ValueLayout.JAVA_LONG);

// Cấp phát cho 10 phần tử, mỗi phần tử theo layout int.
MemorySegment tenInts = arena.allocate(ValueLayout.JAVA_INT, 10);
```

Đây là đoạn code minh họa **bên trong scope nơi `arena` đang tồn tại**. `arena.allocate(ValueLayout.JAVA_INT, 10)` bảo đảm đủ chỗ cho 10 giá trị `int` với alignment tương ứng, không nên tự viết `10 * 4` khi đã có layout và muốn sử dụng API theo đúng biểu diễn dữ liệu.

### Scope quản lý truy cập sau `close()`

`Arena.ofConfined()` cho phép truy cập các segment được cấp phát chỉ trên **thread tạo Arena**. Khi `try-with-resources` kết thúc, arena được đóng; mọi segment và slice dựa trên allocation đó **không còn hợp lệ**. Truy cập `get/set` sau đóng sẽ ném `IllegalStateException` thay vì trở thành một con trỏ C có thể sử dụng tùy tiện.

Các loại arena cần biết:

| Arena | Đóng thủ công? | Thread được truy cập? | Phù hợp |
|---|---|---|---|
| `Arena.ofConfined()` | Có; owner thread đóng | Chỉ owner thread | Mã tuyến tính, truy cập một thread, thử nghiệm nhỏ |
| `Arena.ofShared()` | Có | Nhiều thread, với đồng bộ thích hợp | Shared native buffer có lifecycle rõ |
| `Arena.ofAuto()` | Không | Nhiều thread; GC quản lý lifetime | Khi không cần giải phóng tại thời điểm xác định |
| `Arena.global()` | Không | Nhiều thread; tồn tại rất lâu | Dữ liệu thực sự cần lifecycle toàn tiến trình/JVM; tránh lạm dụng |

**Không đồng nghĩa:** shared arena cho phép nhiều thread **truy cập segment**, nhưng **không** tự biến các thao tác đọc-ghi thành atomic hay thread-safe theo thuật toán. Cần thêm đồng bộ khi có concurrent mutation. Arena global/auto không phải thay thế mặc định cho `try-with-resources` vì khó kiểm soát lúc thu hồi.

## 4. ValueLayout mô tả giá trị, kích thước, byte order, alignment

Một số layout có sẵn trong `java.lang.foreign.ValueLayout`:

| Layout Java | Kiểu kết quả của `get` / tham số `set` | Kích thước byte | Ghi chú |
|---|---|---:|---|
| `ValueLayout.JAVA_BYTE` | `byte` | 1 | Không có vấn đề byte order |
| `ValueLayout.JAVA_BOOLEAN` | `boolean` | 1 | Không tự giả định cùng C `bool` trong mọi ABI |
| `ValueLayout.JAVA_CHAR` | `char` | 2 | UTF-16 code unit; không phải UTF-8 byte |
| `ValueLayout.JAVA_SHORT` | `short` | 2 | Số nguyên có dấu 16-bit |
| `ValueLayout.JAVA_INT` | `int` | 4 | Số nguyên có dấu 32-bit |
| `ValueLayout.JAVA_LONG` | `long` | 8 | Số nguyên có dấu 64-bit |
| `ValueLayout.JAVA_FLOAT` | `float` | 4 | Floating-point |
| `ValueLayout.JAVA_DOUBLE` | `double` | 8 | Floating-point |
| `ValueLayout.ADDRESS` | `MemorySegment` (địa chỉ) | Phụ thuộc nền tảng | Dùng cho native pointer; không phải số nguyên byte thông thường |

Các layout có thể tùy chỉnh bất biến (trả về layout **mới**) bằng:

- `layout.withOrder(ByteOrder.LITTLE_ENDIAN)` hoặc `withOrder(ByteOrder.BIG_ENDIAN)`: cách sắp xếp byte của giá trị đa byte.
- `layout.withByteAlignment(1)`: hạ yêu cầu căn chỉnh byte của một layout (trường hợp unaligned, phải biết rõ memory format).
- `layout.withName("field")`: gắn tên cho layout, hữu ích với `structLayout` và `byteOffset(...)`.
- `layout.byteSize()`, `layout.byteAlignment()`, `layout.order()`: kiểm tra contract hiện hành.

Ví dụ:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

ValueLayout.OfInt intLE =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);

System.out.println(intLE.byteSize());       // 4
System.out.println(intLE.byteAlignment());  // Thường là 4
System.out.println(intLE.order());          // LITTLE_ENDIAN
```

Đây là **đoạn minh họa**, không phải file runnable độc lập. `ValueLayout.JAVA_INT` mặc định dùng byte order của nền tảng; **không giả định máy nào cũng little-endian**. Khi định nghĩa định dạng file/gói tin/binary protocol, nên chọn byte order rõ ràng để dữ liệu nhất quán trên mọi nền tảng.

**Cảnh báo ABI:** `JAVA_LONG` tương ứng Java `long` **8 byte**, không mặc nhiên đồng nghĩa với C `long` trên Windows/Linux. Nếu tương tác trực tiếp một C struct, phải kiểm tra kích thước/alignment/packing theo **ABI cụ thể**, không đoán từ tên kiểu Java.

## 5. `get/set` dùng byte offset; `getAtIndex/setAtIndex` dùng chỉ số phần tử

Hai cặp API sau trông giống nhau nhưng đơn vị **khác hẳn**:

```java
segment.set(ValueLayout.JAVA_INT, 8, 30);
int a = segment.get(ValueLayout.JAVA_INT, 8);

segment.setAtIndex(ValueLayout.JAVA_INT, 2, 30);
int b = segment.getAtIndex(ValueLayout.JAVA_INT, 2);
```

Đây là **trích đoạn minh họa** giả định segment có ít nhất 12 byte, đủ alignment và đang sống.

- `get(layout, offset)`: `offset = 8` nghĩa là byte thứ **8** tính từ đầu segment.
- `getAtIndex(layout, index)`: `index = 2` nghĩa là phần tử thứ **2** (đếm từ 0), offset byte thực = `2 * layout.byteSize()` = `2 * 4 = 8`.
- `getAtIndex` **không** tạo mảng Java và không tăng kích thước segment. Nó chỉ đổi đơn vị của tham số truy cập.
- Với layout 8 byte, `getAtIndex(JAVA_LONG, 2)` bắt đầu ở byte **16**, trong khi `get(JAVA_LONG, 2)` bắt đầu byte **2** (thường misaligned).

Bảng cho segment 16 byte chứa bốn `int`:

| Chỉ số `int` | Byte offset (`index × 4`) | Phạm vi byte truy cập |
|---:|---:|---|
| 0 | 0 | 0–3 |
| 1 | 4 | 4–7 |
| 2 | 8 | 8–11 |
| 3 | 12 | 12–15 |
| 4 | 16 | **Ngoài giới hạn**: cần byte 16–19 |

Đối với `long`/`double`, phần tử có kích thước 8 byte. Một segment 16 byte chứa **hai** phần tử 8 byte ở offset 0 và 8, **không** chứa 16 phần tử `long`.

### Công thức kiểm tra phạm vi

Cho segment có `N = segment.byteSize()`, layout có `S = layout.byteSize()`. Một truy cập bắt đầu ở byte offset `O` chỉ hợp lệ về giới hạn nếu:

```text
0 <= O  và  S <= N - O
```

Dùng dạng `S <= N - O` sau khi đã kiểm tra `O >= 0` giúp tránh tràn ở phép `O + S`. API đã kiểm tra bounds, nhưng nếu tính offset từ input không tin cậy, nên kiểm tra **trước khi nhân/cộng**:

```java
long offset = Math.multiplyExact(index, layout.byteSize());
// Math.multiplyExact phát hiện overflow thay vì wrap sang offset sai.
```

Đây là công thức Java minh họa, trong đó `index` và `layout` đã được khai báo, `layout.byteSize()` trả `long`. Với index dạng số lượng phần tử, phải kiểm tra `index >= 0`, số phần tử và alignment phù hợp.

## 6. Chương trình hoàn chỉnh: viết 24 byte, đọc lại và kiểm tra lỗi

Ví dụ dưới đây dùng **byte order tường minh** nên kết quả byte hex ổn định trên cả máy little-endian và big-endian. Một segment 24 byte được cấp phát với alignment 8.

**Tệp `SegmentOffsetsDemo.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

public class SegmentOffsetsDemo {
    public static void main(String[] args) {
        var intLE = ValueLayout.JAVA_INT.withOrder(
                ByteOrder.LITTLE_ENDIAN);
        var longBE = ValueLayout.JAVA_LONG.withOrder(
                ByteOrder.BIG_ENDIAN);

        MemorySegment savedView;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(24, 8);
            savedView = segment;

            // byte 0..3, 4..7: hai số int little-endian.
            segment.set(intLE, 0, 0x12345678);
            segment.set(intLE, 4, -7);

            // byte 8..15: một số long big-endian.
            segment.set(longBE, 8, 0x0102030405060708L);

            // byte 16: một giá trị byte, không có byte order.
            segment.set(ValueLayout.JAVA_BYTE, 16, (byte) 0x7F);

            // byte 20..23: một số int little-endian.
            segment.set(intLE, 20, 99);

            System.out.println("size=" + segment.byteSize());
            System.out.printf("int@0=0x%08X%n",
                    segment.get(intLE, 0));
            System.out.println("int@4=" + segment.get(intLE, 4));
            System.out.printf("long@8=0x%016X%n",
                    segment.get(longBE, 8));
            System.out.printf("byte@16=0x%02X%n",
                    Byte.toUnsignedInt(
                            segment.get(ValueLayout.JAVA_BYTE, 16)));

            // index = 1 => byte offset = 1 * 4 = 4.
            System.out.println("atIndex[1]=" +
                    segment.getAtIndex(intLE, 1));

            // Slice có gốc tại byte 8 của parent.
            MemorySegment slice = segment.asSlice(8, 8);
            System.out.printf("slice long@0=0x%016X%n",
                    slice.get(longBE, 0));

            StringBuilder hex = new StringBuilder();
            for (long offset = 0; offset < segment.byteSize();
                    offset++) {
                if (offset != 0) {
                    hex.append(' ');
                }
                int unsignedByte = Byte.toUnsignedInt(
                        segment.get(ValueLayout.JAVA_BYTE, offset));
                hex.append("%02X".formatted(unsignedByte));
            }
            System.out.println("raw=" + hex);

            try {
                segment.get(intLE, 2);
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "misaligned=IllegalArgumentException");
            }

            try {
                segment.get(intLE, 24);
            } catch (IndexOutOfBoundsException e) {
                System.out.println(
                        "oob=IndexOutOfBoundsException");
            }

            try {
                segment.asReadOnly().set(intLE, 0, 1);
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "readonly=IllegalArgumentException");
            }
        }

        // savedView tham chiếu tới cùng memory đã hết lifetime.
        try {
            savedView.get(intLE, 0);
        } catch (IllegalStateException e) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 22+:

```bash
javac -encoding UTF-8 SegmentOffsetsDemo.java
java SegmentOffsetsDemo
```

**stdout đầy đủ (đã đối chiếu trên JDK 24):**

```text
size=24
int@0=0x12345678
int@4=-7
long@8=0x0102030405060708
byte@16=0x7F
atIndex[1]=-7
slice long@0=0x0102030405060708
raw=78 56 34 12 F9 FF FF FF 01 02 03 04 05 06 07 08 7F 00 00 00 63 00 00 00
misaligned=IllegalArgumentException
oob=IndexOutOfBoundsException
readonly=IllegalArgumentException
afterClose=IllegalStateException
```

### Cách giải thích các dòng output

- `size=24`: `byteSize()` trả số **byte**, không phải số `int`.
- `0x12345678` được ghi little-endian thành các byte `78 56 34 12` tại offset 0–3.
- `-7` có biểu diễn bù hai 32-bit `0xFFFFFFF9`, nên bốn byte little-endian là `F9 FF FF FF` tại offset 4–7.
- `0x0102030405060708L` được ghi big-endian thành `01 02 03 04 05 06 07 08` tại offset 8–15.
- Byte `7F` nằm tại offset 16; ba byte 17–19 vẫn là `00` do allocation mới được khởi tạo zero.
- Giá trị `99 = 0x63` ghi ở offset 20 thành `63 00 00 00`.
- `getAtIndex(intLE, 1)` đọc đúng byte offset 4 và trả `-7`.
- `asSlice(8, 8)` tạo một **view** dài 8 byte của vùng gốc: byte offset 0 của slice tương ứng byte offset 8 của parent.
- Ba exception chứng minh alignment, bounds, read-only và arena lifetime được kiểm tra **trước** khi truy cập không hợp lệ.

Sơ đồ vùng nhớ sau các lệnh `set`:

```text
offset  [00][01][02][03]  [04][05][06][07]
bytes    78  56  34  12    F9  FF  FF  FF
         int little-endian   -7 little-endian

offset  [08][09][10][11][12][13][14][15]
bytes    01  02  03  04  05  06  07  08
         long big-endian

offset  [16][17][18][19]  [20][21][22][23]
bytes    7F  00  00  00    63  00  00  00
         byte + zero        int 99 little-endian
```

Đây là bộ nhớ **có kiểu do caller diễn giải tại thời điểm đọc/ghi**. Segment bản thân không ghi metadata “offset 8 là long” vào native bytes.

## 7. Byte order: đọc đúng giá trị và tránh phụ thuộc máy chạy

**Endianness** là thứ tự byte của các giá trị nhiều byte:

| Giá trị `int 0x12345678` | Byte ở offset 0, 1, 2, 3 |
|---|---|
| Big-endian | `12 34 56 78` |
| Little-endian | `78 56 34 12` |

Với `ValueLayout.JAVA_INT`, byte order gốc dùng thứ tự byte **native của nền tảng**. Nếu yêu cầu tương tác nhị phân cố định, hãy khai báo:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

ValueLayout.OfInt intBE =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
ValueLayout.OfInt intLE =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);
```

Đây là trích đoạn khai báo. Layout `withOrder` **không chuyển đổi toàn bộ segment**; nó chỉ làm thay đổi cách **một lần get/set cụ thể** diễn giải/ghi các byte tại offset. Nếu cùng bốn byte `78 56 34 12`, đọc bằng `intLE` trả `0x12345678` nhưng đọc bằng `intBE` trả `0x78563412`.

Cũng đừng hiểu endianness là "thứ tự của phần tử mảng". Các phần tử vẫn nằm ở offset 0, 4, 8, ...; byte order chỉ ảnh hưởng cách sắp xếp **bên trong một giá trị đa byte**.

**Đối với C struct hoặc file:** chọn byte order theo đặc tả C ABI hoặc wire format thực tế; không mặc định tất cả file đều little-endian hoặc tất cả C types đều dùng cùng kích thước. Một `char` Java 16-bit không phải C `char` 8-bit; nên dùng `JAVA_BYTE` cho raw bytes và bộ mã hóa/giải mã charset nếu cần text.

## 8. Alignment và truy cập unaligned

**Alignment** là ràng buộc địa chỉ truy cập, khác với bounds. Ví dụ:

- Segment cấp phát `arena.allocate(24, 8)` có base address căn chỉnh 8 byte.
- `ValueLayout.JAVA_INT` có alignment tự nhiên thường 4 byte.
- Truy cập int tại offset **0, 4, 8, ...** phù hợp; offset **2** có thể vi phạm alignment dù `2 + 4 <= 24` vẫn nằm trong vùng nhớ.
- `get(intLE, 2)` của demo gây `IllegalArgumentException` do offset không tương thích với alignment của layout.

**Nếu binary protocol được thiết kế *packed***, một giá trị nhiều byte có thể xuất hiện ở vị trí không căn chỉnh. Ta có thể khai báo layout alignment nhỏ hơn khi thật sự cần:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class UnalignedRead {
    public static void main(String[] args) {
        var intUnaligned =
                ValueLayout.JAVA_INT.withByteAlignment(1);
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(8, 4);
            segment.set(intUnaligned, 1, 0x01020304);
            System.out.printf("0x%08X%n",
                    segment.get(intUnaligned, 1));
        }
    }
}
```

Biên dịch/chạy `javac UnalignedRead.java` và `java UnalignedRead` cho:

```text
0x01020304
```

`withByteAlignment(1)` làm layout cho phép truy cập ở byte offset bất kỳ về mặt alignment; nó **không** mở rộng vùng nhớ và **không** thay đổi byte order. Các access unaligned có thể có chi phí/đặc điểm triển khai khác và không phải lựa chọn mặc định tốt cho native structs có alignment rõ ràng.

Khi làm việc với một slice, alignment được kiểm tra theo **địa chỉ hiệu dụng** của truy cập, không chỉ theo chỉ số tính từ slice. Một slice bắt đầu ở byte 1 có thể khiến truy cập `JAVA_INT` tại slice offset 0 bị misaligned. Hãy xem cả base address, slice offset và layout.

## 9. Slice: vùng con vẫn chia sẻ cùng backing memory

`asSlice(offset, length)` không tự cấp phát một vùng native memory mới. Nó tạo một **view** tới phần tương ứng của segment gốc:

```java
// Trong một Arena đang sống, cùng thread:
MemorySegment whole = arena.allocate(16, 4);
MemorySegment secondInt = whole.asSlice(4, 4);

secondInt.set(ValueLayout.JAVA_INT, 0, 55);
System.out.println(whole.get(ValueLayout.JAVA_INT, 4)); // 55
```

Đây là **trích đoạn minh họa**, biến `arena` đã được khởi tạo. Byte offset 0 của `secondInt` là byte offset 4 của `whole`. Cả hai có cùng backing allocation và cùng lifetime.

Hệ quả:

1. Ghi vào slice có thể quan sát được qua parent (và ngược lại).
2. Slice có bounds riêng: `secondInt.get(JAVA_INT, 4)` sẽ vượt quá slice 4 byte, dù parent còn dữ liệu tại offset 8.
3. Đóng Arena làm mất hiệu lực cả parent lẫn mọi slices; không có chuyện slice kéo dài lifetime sau `arena.close()`.
4. `asReadOnly()` tạo một read-only view, không sao chép và không làm backing memory read-only toàn cục: nếu còn writable view khác, nó vẫn có thể ghi.
5. Nếu bạn muốn **snapshot không bị thay đổi**, phải cấp phát/copy sang buffer riêng, không chỉ dùng `asReadOnly`.

Slice rất hữu ích khi có packet header, record hoặc fixed-size binary field: truyền segment con cho hàm xử lý để giảm rủi ro vô tình truy cập những byte khác. Tuy nhiên caller vẫn phải bảo đảm owner Arena chưa đóng trong lúc segment con được dùng.

## 10. Truy cập mảng giá trị theo chỉ số mà không nhầm đơn vị

Với dữ liệu `int` lặp lại, dùng `getAtIndex`/`setAtIndex` làm code dễ đọc và tránh tự tính offset cho từng lần:

**Tệp `IntArraySegment.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class IntArraySegment {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_INT, 3);

            segment.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            segment.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            segment.setAtIndex(ValueLayout.JAVA_INT, 2, 30);

            System.out.println("bytes=" + segment.byteSize());
            System.out.println("index2=" +
                    segment.getAtIndex(ValueLayout.JAVA_INT, 2));
            System.out.println("offset8=" +
                    segment.get(ValueLayout.JAVA_INT, 8));
        }
    }
}
```

Chạy `javac IntArraySegment.java` rồi `java IntArraySegment`:

```text
bytes=12
index2=30
offset8=30
```

Giải thích:

- `allocate(JAVA_INT, 3)` tạo đủ **12 byte** cho ba giá trị 4 byte.
- `getAtIndex(JAVA_INT, 2)` và `get(JAVA_INT, 8)` cùng chỉ tới byte offset `2 × 4 = 8`.
- `get(JAVA_INT, 2)` **không** truy cập phần tử thứ hai; đó là truy cập bắt đầu tại byte 2 và có thể lỗi alignment.
- `getAtIndex(JAVA_INT, 3)` là `IndexOutOfBoundsException`: index 3 đòi truy cập byte 12–15, trong khi segment chỉ có byte 0–11.

Trong loop với input không tin cậy, dùng `Math.multiplyExact` hoặc `getAtIndex` thay vì tự nhân số lớn không kiểm soát tràn. Chỉ số `long` và byte offsets `long` vẫn không mang nghĩa "memory vô hạn": mọi truy cập phải nằm trong `segment.byteSize()`.

## 11. Struct layout: tính offset từ bố cục thay vì hard-code

Khi tương tác với record gồm các trường khác kích thước, một offset cố định tự viết bằng tay rất dễ nhầm phần **padding** giữa các trường. FFM cung cấp `MemoryLayout.structLayout` để mô tả bố cục và `byteOffset(PathElement...)` để tìm offset từ tên trường.

Giả sử một định dạng record (do ứng dụng **chủ động định nghĩa**, không khẳng định trùng C ABI của mọi hệ điều hành):

```text
byte 0..3    : int id       (4 byte)
byte 4..5    : short flags  (2 byte)
byte 6..7    : padding      (2 byte)
byte 8..15   : long count   (8 byte)
Tổng         : 16 byte
```

**Tệp `StructOffsets.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class StructOffsets {
    public static void main(String[] args) {
        MemoryLayout record = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("id"),
                ValueLayout.JAVA_SHORT.withName("flags"),
                MemoryLayout.paddingLayout(2),
                ValueLayout.JAVA_LONG.withName("count")
        );

        long idOffset = record.byteOffset(groupElement("id"));
        long flagsOffset = record.byteOffset(groupElement("flags"));
        long countOffset = record.byteOffset(groupElement("count"));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(record);

            segment.set(ValueLayout.JAVA_INT, idOffset, 42);
            segment.set(ValueLayout.JAVA_SHORT, flagsOffset, (short) 7);
            segment.set(ValueLayout.JAVA_LONG, countOffset, 1_000L);

            System.out.println("size=" + record.byteSize()
                    + " offsets=" + idOffset + ","
                    + flagsOffset + "," + countOffset);

            System.out.println("id=" +
                    segment.get(ValueLayout.JAVA_INT, idOffset)
                    + " flags=" +
                    segment.get(ValueLayout.JAVA_SHORT, flagsOffset)
                    + " count=" +
                    segment.get(ValueLayout.JAVA_LONG, countOffset));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac StructOffsets.java
java StructOffsets
```

**stdout:**

```text
size=16 offsets=0,4,8
id=42 flags=7 count=1000
```

Những điểm cần nhớ:

- `structLayout` mô tả các trường và byte padding được khai báo; đừng mặc nhiên cho rằng nó luôn tự chèn padding giống compiler C. Trong ví dụ, ta **ghi rõ** `paddingLayout(2)`.
- `record.byteOffset(groupElement("count"))` trả **8 byte**, không phải trường thứ 8.
- `arena.allocate(record)` dùng size và alignment của record khi cấp phát; tốt hơn việc tự đếm rồi cấp phát sai.
- `ValueLayout.withName` giúp đặt tên field trong layout, nhưng tên không tự tồn tại trong native byte buffer.
- Khi cần chia sẻ chính xác với native C struct, phải xác minh `sizeof`, `offsetof`, ABI packing/alignment và kiểu C tương ứng ở toolchain mục tiêu. Ví dụ trên là một bố cục **đã định nghĩa rõ**, không phải lời hứa portability của mọi `struct` C.

Có thể dùng `MemoryLayout.sequenceLayout` và layout paths nếu cần mảng field phức tạp, hoặc var handles tạo từ layout để truy cập trường lặp nhiều lần. Tuy nhiên với bài cơ bản, `byteOffset` cộng `segment.get/set` đủ trực quan và dễ kiểm tra.

## 12. Các điều kiện lỗi: bounds, alignment, read-only, scope, thread

FFM bảo vệ một số lỗi thường gặp bằng kiểm tra ở runtime. Các exception quan trọng:

| Điều kiện | Ví dụ | Kết quả thường gặp |
|---|---|---|
| Byte offset âm hoặc truy cập vượt segment | `segment.get(JAVA_INT, -1)`; với segment 24 byte, `get(JAVA_INT, 24)` | `IndexOutOfBoundsException` |
| Offset không thỏa alignment của layout | `segment.get(JAVA_INT, 2)` với native base đủ aligned | `IllegalArgumentException` |
| Ghi qua read-only segment | `segment.asReadOnly().set(JAVA_INT, 0, 1)` | `IllegalArgumentException` |
| Truy cập segment sau `Arena.close()` | `savedView.get(JAVA_INT, 0)` | `IllegalStateException` |
| Confined arena/segment bị truy cập từ thread khác | Worker thread gọi `get` trên segment do confined arena của thread A quản lý | `WrongThreadException` |
| `Arena.allocate` với size âm hoặc alignment sai | `arena.allocate(-1, 4)`; `arena.allocate(8, 3)` | `IllegalArgumentException` |
| Cố đóng Arena đã đóng | Gọi `close()` hai lần trên manually closeable arena | `IllegalStateException` |
| Shared data race dù bounds đúng | Nhiều thread ghi cùng bytes thiếu đồng bộ | Không có exception đảm bảo; có thể là data race/logic bug |

**Đừng dùng exception làm phép đo offset**: kiểm tra kích thước/layout/offset theo contract trước; bắt exception trong demo giúp nhìn rõ phạm vi bảo vệ, không phải cách thiết kế parser nhị phân hiệu quả.

### Về thread confinement

`Arena.ofConfined()` chỉ cho thread tạo arena truy cập các segment liên quan. Nếu thật sự cần nhiều thread, cân nhắc `Arena.ofShared()` và quản lý các thao tác đồng thời:

```java
// Trích đoạn minh họa, không phải ứng dụng đa luồng đầy đủ.
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(8, 8);
    // Có thể chuyển view này cho thread khác.
    // Phải bảo đảm thread kia kết thúc dùng trước khi arena.close().
    // Phải đồng bộ nếu nhiều thread ghi/đọc cùng vị trí.
}
```

**Shared arena không làm `segment.set` và `segment.get` thành giao thức đồng bộ hóa.** Nếu cần atomic/volatile access giữa threads, dùng var handle thích hợp và các memory-ordering guarantees; hoặc lock rõ ràng. Không đóng shared arena khi background worker vẫn dự định dùng vùng nhớ. Khi truyền địa chỉ native cho C, càng phải thận trọng: C giữ pointer sau khi arena đóng có thể tạo use-after-free **ngoài** bảo vệ của Java API.

## 13. Gắn nội dung này vào bài toán native interoperability

Khi Java gọi hàm C với buffer/struct, Java và C phải thỏa thuận **một hợp đồng nhị phân**:

1. **Kích thước**: tổng số byte, kích thước mỗi field và số phần tử (khác nhau).
2. **Alignment**: vị trí bắt đầu field có đúng yêu cầu native ABI không; có padding hay packing không.
3. **Byte order**: native order hay protocol-defined order, tránh sửa sai dữ liệu trên máy khác.
4. **Mutability**: C được ghi hay chỉ đọc? Nếu dùng read-only view trong Java thì điều đó không tự ngăn native pointer bị ghi trái phép.
5. **Lifetime**: Arena/segment phải còn sống trong suốt thời gian native function hoặc callback dùng pointer. Không gửi segment đến native worker rồi đóng arena trước khi worker kết thúc.
6. **Thread-safety**: nếu Java và C cùng truy cập một vùng nhớ, hợp đồng đồng bộ là gì?
7. **Ownership**: ai cấp phát, ai chịu trách nhiệm đóng Arena hoặc gọi `free` nếu thư viện C sở hữu allocation?

Ví dụ với một SDK native có hàm nhận `int32_t*` để ghi 10 phần tử, Java có thể allocate segment theo `JAVA_INT` rồi cung cấp pointer qua FFM downcall; **nhưng chỉ khi** C ABI, lifetime và callback contract phù hợp. Không đưa ra giả định `JAVA_INT` khớp `C long` hoặc một packed struct chưa xác minh.

Với **file/wire format** yêu cầu little-endian, sử dụng `withOrder(LITTLE_ENDIAN)`. Với **C ABI** thường dùng native endianness nhưng vẫn phải xác minh layout của hệ thống đang chạy. `ValueLayout.JAVA_INT` và `ValueLayout.JAVA_LONG` là Java primitive layouts; chúng không tự xác định mọi native ABI type.

### Khi nào dùng `ByteBuffer`, khi nào dùng `MemorySegment`?

`ByteBuffer` cũng cho phép `getInt(index)`/`putInt(index)` với byte index; nhưng nó có vị trí/giới hạn và ByteOrder riêng. `MemorySegment` có `long byteSize`, lifecycle theo Arena, thread-access constraints và tích hợp layout cho FFM. Cả hai không được phép dùng sai byte offset/alignment. Nếu có sẵn `ByteBuffer` từ Java API, không cần đổi sang FFM chỉ vì muốn đọc vài byte; nếu cần native downcall, structs và ownership rõ, `MemorySegment` là sự trừu tượng phù hợp.

## 14. Checklist và bài tập củng cố

### Checklist trước mỗi `get/set`

- [ ] JDK ≥22; import đúng `java.lang.foreign.`, không dùng nhầm preview/incubator API cũ.
- [ ] Arena và segment còn sống; dùng `try-with-resources` khi cần lifetime xác định.
- [ ] Segment dài đủ byte; không nhầm số phần tử và số byte.
- [ ] Layout đúng kiểu Java, kích thước, alignment và byte order được hợp đồng định nghĩa.
- [ ] Offset của `get/set` là **byte offset**; index của `getAtIndex/setAtIndex` là **chỉ số phần tử**.
- [ ] Giá trị cần đọc/ghi nằm trọn trong `[0, segment.byteSize())`.
- [ ] Địa chỉ hiệu dụng thỏa `layout.byteAlignment()`, trừ khi dùng layout unaligned có chủ đích.
- [ ] Không ghi qua read-only view; không giữ slice sống lâu hơn owner Arena.
- [ ] Nếu nhiều thread truy cập, Arena phù hợp và đã có synchronization/lifecycle barrier.
- [ ] Nếu truyền xuống C, xác minh ABI, byte order, struct padding, quyền sở hữu và thời điểm giải phóng.

### Bài tập 1 — byte offset

Có segment 24 byte, gọi `segment.set(ValueLayout.JAVA_LONG, 8, 123L)`. Những byte nào được truy cập?

**Đáp án:** bắt đầu tại byte offset **8**, ghi 8 byte là vùng byte **8–15** (hay khoảng `[8,16)`). Layout vẫn phải thỏa alignment và segment còn sống.

### Bài tập 2 — phần tử và byte

Có `arena.allocate(ValueLayout.JAVA_INT, 5)`. Hỏi `byteSize()`, byte offset của `getAtIndex(JAVA_INT, 3)` và index đầu tiên bị out-of-bounds?

**Đáp án:** `byteSize() = 20`, phần tử index 3 ở byte offset **12**; index **5** là index đầu tiên vượt quá segment (nếu index không âm).

### Bài tập 3 — Endianness

`set(JAVA_INT.withOrder(LITTLE_ENDIAN), 0, 0x01020304)` ghi bốn byte nào?

**Đáp án:** `04 03 02 01`. Đọc lại bằng BIG_ENDIAN tại offset 0 trả `0x04030201`, không phải `0x01020304`.

### Bài tập 4 — alignment

Segment được cấp phát với alignment 8, bạn cần ghi một `int` ở offset 2 của định dạng packed. Tại sao `set(JAVA_INT, 2, ...)` có thể lỗi? Phải làm gì?

**Đáp án:** Layout int thường đòi alignment 4, offset 2 không hợp lệ dù không vượt bounds. Dùng `JAVA_INT.withByteAlignment(1)` **nếu** định dạng thật sự cho phép unaligned field, hoặc đổi vị trí field sang offset đúng alignment.

### Bài tập 5 — slice và arena

Một method trả về `segment.asSlice(4, 4)` từ trong `try (Arena arena = Arena.ofConfined())`, rồi caller dùng slice sau khi method kết thúc. Có hợp lệ không?

**Đáp án:** Không. Slice dùng cùng backing memory và scope của Arena. Khi `try` kết thúc, arena đóng, slice cũng không còn hợp lệ; `get` sẽ ném `IllegalStateException`. Phải thiết kế owner lifetime kéo dài phù hợp hoặc copy dữ liệu sang vùng còn sống.

### Bài tập 6 — struct

Một record gồm `int id` (4 byte), `short status` (2 byte), padding 2 byte và `long version` (8 byte). Tổng số byte và offset của `version`?

**Đáp án:** Tổng **16 byte**, `version` bắt đầu byte offset **8**. Dùng `structLayout` với `paddingLayout(2)` và `byteOffset(groupElement("version"))` sẽ ít sai hơn hard-code.

### Bài tập 7 — lỗi trong code

Đánh giá:

```java
// Trích đoạn ví dụ sai về đơn vị.
MemorySegment segment = arena.allocate(4, 4);
segment.set(ValueLayout.JAVA_INT, 1, 42);
```

**Đáp án:** `allocate(4,4)` tạo 4 byte, đủ **một int tại offset 0**. Ghi tại offset **1** đòi các byte 1–4, vượt bounds (và thường sai alignment). Sửa thành `set(JAVA_INT, 0, 42)`. Nếu mục tiêu là phần tử thứ hai, phải cấp phát ít nhất 8 byte và ghi ở offset 4 hoặc `setAtIndex(JAVA_INT, 1, 42)`.

## 15. Tóm tắt và tài liệu chính thức

Khi cấp phát và truy cập native memory với FFM, hãy nhớ:

- **Arena cấp phát và quản lý lifetime**: `arena.allocate(bytes, alignment)`, `try-with-resources` đóng vùng nhớ đúng lúc.
- **MemorySegment là view có giới hạn**: `byteSize()`, `get/set`, `asSlice`, `asReadOnly`; không chứa thông tin kiểu field tự động.
- **ValueLayout quyết định cách đọc/ghi một giá trị**: `JAVA_INT`, `JAVA_LONG`, `withOrder`, `withByteAlignment`, `byteSize` và `byteAlignment`.
- **Byte offset khác element index**: `get(JAVA_INT, 8)` tương đương `getAtIndex(JAVA_INT, 2)` về vị trí.
- **Quy tắc an toàn tối thiểu**: bounds + alignment + scope còn sống + thread hợp lệ + byte order/ABI đúng.
- **Dành cho interop**: ghi chính xác từng byte, có hợp đồng về lifetime, ownership và packing, thay vì tin rằng Java primitive layout mặc nhiên khớp mọi cấu trúc C.

Tài liệu chuẩn để đối chiếu:

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 22 — `java.lang.foreign` package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Oracle Java SE 25 — `MemorySegment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle Java SE 25 — `Arena`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle Java SE 25 — `ValueLayout`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java SE 25 — `MemoryLayout` và `byteOffset`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 25 — `SegmentAllocator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
