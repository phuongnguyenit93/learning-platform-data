# MemorySegment: sao chép, điền dữ liệu, đối chiếu và chuyển sang mảng Java

## 1. Mục tiêu và phiên bản Java

**`MemorySegment`** trong Foreign Function & Memory API (FFM) mô tả một vùng bộ nhớ liên tiếp có độ dài rõ ràng; vùng đó có thể thuộc **Java heap** (heap segment) hoặc là **bộ nhớ native/off-heap** (native segment). Khi cần xử lý dữ liệu nhị phân hoặc chuyển dữ liệu giữa Java và native, có bốn nhóm thao tác đặc biệt hữu ích:

1. **Sao chép**: `copyFrom`, các overload của `MemorySegment.copy`.
2. **Điền dữ liệu**: `fill(byte)`, điền toàn vùng hoặc trên một lát cắt (`asSlice`).
3. **Đối chiếu nội dung**: `mismatch` để tìm vị trí **byte** đầu tiên khác nhau.
4. **Chuyển dữ liệu về mảng Java**: `toArray(ValueLayout...)` hoặc copy trực tiếp vào mảng đã có.

Bài học thuộc nhóm **MemorySegment** của *Java Advance - native-interoperability*. Dù nằm cạnh các chủ đề JNI, các thao tác `MemorySegment` này thuộc **FFM API**, **không phải** các hàm `Get<Type>ArrayElements` của JNI. Có thể thực hành chỉ bằng Java, không cần viết C.

**Điều kiện phiên bản:** sử dụng **JDK 22 trở lên**, với API ổn định trong package `java.lang.foreign` theo JEP 454. Java 17 không có API chuẩn ổn định này; các bản Java trước JDK 22 từng sử dụng API incubator/preview với tên hoặc cú pháp khác. Code chạy mẫu dưới đây chủ đích dùng **Java 22+**, không tự khẳng định biên dịch được trên JDK 17. Các thao tác cấp phát, copy, fill, mismatch và toArray trong ví dụ **không yêu cầu `--enable-preview` hoặc nạp native library**.

### 1.1. Bảng thao tác nhanh

| Nhu cầu | API | Kết quả |
| --- | --- | --- |
| Tạo view trên một mảng Java có sẵn | `MemorySegment.ofArray(array)` | **Chia sẻ vùng lưu trữ** của mảng primitive |
| Cấp phát native memory | `arena.allocate(bytes)` | Segment off-heap, sống theo `Arena` |
| Copy toàn bộ source từ offset 0 vào destination | `dest.copyFrom(src)` | Trả `dest`; dest phải đủ lớn |
| Copy một dải byte | `MemorySegment.copy(src, srcOffset, dst, dstOffset, bytes)` | Copy đúng `bytes` byte |
| Copy các phần tử với layout | `MemorySegment.copy(src, srcLayout, srcOffset, dst, dstLayout, dstOffset, count)` | Copy `count` phần tử; có thể đổi byte order |
| Điền mọi byte trong segment | `segment.fill((byte) 0)` | Trả chính segment; dữ liệu thay đổi tại chỗ |
| So sánh dữ liệu | `left.mismatch(right)` | Offset byte đầu tiên khác, hoặc `-1` |
| Copy toàn segment ra mảng `byte[]` | `segment.toArray(ValueLayout.JAVA_BYTE)` | Mảng Java **mới**, độc lập |
| Copy toàn segment ra mảng `int[]` | `segment.toArray(ValueLayout.JAVA_INT)` | Mảng Java **mới**, kích thước phải hợp lệ |
| Copy một phần segment ra mảng có sẵn | `MemorySegment.copy(segment, layout, offset, array, index, count)` | Ghi vào chính mảng được truyền |
| Copy từ mảng vào segment | `MemorySegment.copy(array, index, segment, layout, offset, count)` | Ghi vào segment đích |

Trong bảng, **offset của segment đo bằng byte (`long`)**; **index của Java array đo bằng phần tử (`int`)**. Đây là nguồn gây lỗi rất phổ biến.

## 2. Hiểu đúng bộ nhớ, kích thước và vòng đời

### 2.1. Heap segment có thể chia sẻ mảng Java

```java
int[] numbers = {10, 20, 30};
MemorySegment heap = MemorySegment.ofArray(numbers);

heap.setAtIndex(ValueLayout.JAVA_INT, 1, 99);
System.out.println(java.util.Arrays.toString(numbers));
// [10, 99, 30]
```

**`MemorySegment.ofArray(numbers)` không sao chép dữ liệu.** Nó tạo một segment **backed by** mảng `numbers`. Thay đổi dữ liệu qua segment được phản ánh trong mảng và ngược lại. Segment này có scope tự động giữ backing array có thể truy cập và được phép sử dụng từ các thread khác nhau, nhưng việc truy cập đồng thời vẫn phải được đồng bộ hợp lý.

**Vì vậy:**

- `MemorySegment.ofArray(original)` tạo **view chia sẻ dữ liệu**.
- `segment.toArray(ValueLayout.JAVA_INT)` tạo **mảng độc lập bằng cách copy**.
- `dest.copyFrom(source)` thực hiện **copy**; source và destination vẫn là các vùng khác nhau nếu chúng không có backing chung.
- `segment.asSlice(...)` tạo **view/lát cắt** trên vùng có sẵn; **không copy**.

Nếu API của bạn yêu cầu “snapshot không thay đổi khi dữ liệu nguồn bị sửa”, cần **sao chép thật**, không chỉ tạo `ofArray` hoặc `asSlice`.

### 2.2. Native segment và `Arena`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    System.out.println(block.byteSize()); // 32
}
// Sau khi arena đóng, không được truy cập block nữa.
```

`Arena.ofConfined()` tạo scope mà **thread sở hữu** được phép truy cập segment; `try-with-resources` tự đóng arena và giải phóng bộ nhớ native khi thoát block. Đừng trả một segment native ra ngoài rồi dùng sau khi arena bị đóng. `Arena.ofShared()` phù hợp với truy cập đa thread nhưng **không tự biến chương trình thành thread-safe**. Mỗi vòng đời segment cần có owner rõ ràng.

**`byteSize()` luôn trả số byte**, không phải số phần tử logic. Ví dụ:

- `MemorySegment.ofArray(new byte[6]).byteSize()` = `6`.
- `MemorySegment.ofArray(new int[6]).byteSize()` = `24` vì `int` chiếm 4 byte.
- Một native segment 24 byte có thể chứa 6 giá trị `int` hoặc 24 giá trị `byte` tùy `ValueLayout` dùng để diễn giải.

Các truy cập `get`, `set`, `copy` và `toArray` đều phải thỏa các giới hạn **bounds, scope còn sống và quyền truy cập thread**.

### 2.3. `ValueLayout` giúp hiểu nội dung

`MemorySegment` quản lý **vùng byte**. Để biết một nhóm byte biểu diễn `int`, `long` hay `double`, bạn cung cấp `ValueLayout`:

| Layout | Java carrier | Kích thước thường được quy định |
| --- | --- | --- |
| `ValueLayout.JAVA_BYTE` | `byte` | 1 byte |
| `ValueLayout.JAVA_SHORT` | `short` | 2 byte |
| `ValueLayout.JAVA_CHAR` | `char` | 2 byte |
| `ValueLayout.JAVA_INT` | `int` | 4 byte |
| `ValueLayout.JAVA_FLOAT` | `float` | 4 byte |
| `ValueLayout.JAVA_LONG` | `long` | 8 byte |
| `ValueLayout.JAVA_DOUBLE` | `double` | 8 byte |

Một `ValueLayout` còn mang thông tin **alignment** và **byte order**. `JAVA_INT` biểu diễn kiểu `int` với thứ tự byte mặc định của nền tảng. Nếu dữ liệu đến từ file/network/native API có byte order cố định, phải chỉ định `withOrder(ByteOrder.BIG_ENDIAN)` hoặc `LITTLE_ENDIAN` phù hợp.

## 3. Sao chép toàn vùng bằng `copyFrom`

Cách đơn giản khi destination đã đủ lớn:

```java
byte[] input = {1, 2, 3, 4};
MemorySegment heap = MemorySegment.ofArray(input);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeData = arena.allocate(4);
    nativeData.copyFrom(heap);

    System.out.println(
            java.util.Arrays.toString(
                    nativeData.toArray(ValueLayout.JAVA_BYTE)));
    // [1, 2, 3, 4]
}
```

Cú pháp: **`destination.copyFrom(source)`**. Hàm copy tất cả `source.byteSize()` byte, bắt đầu ở offset `0` vào destination từ offset `0`. Nó trả về chính destination để có thể viết `destination.copyFrom(source).asSlice(...)` nếu muốn.

**Điều kiện:** `destination.byteSize() >= source.byteSize()` và destination ghi được, hai segment còn sống và thread hiện tại có quyền truy cập. Nếu destination **lớn hơn**, `copyFrom` **chỉ copy số byte của source**, những byte dư ở destination không bị sửa theo hợp đồng của lệnh copy. Nếu destination quá nhỏ, sẽ phát sinh `IndexOutOfBoundsException`.

Không hiểu nhầm “copyFrom” là “gán lại biến reference”; dữ liệu được chép sang vùng đích. Việc thay mảng nguồn sau khi copy không tự thay đổi native buffer **nếu hai vùng không dùng chung backing storage**.

### 3.1. Nếu chỉ cần copy một đoạn

Thay vì copy toàn source, dùng `MemorySegment.copy` và tính offset rõ ràng:

```java
// Trích đoạn đặt trong phạm vi source/destination còn sống.
MemorySegment.copy(source, 2L, destination, 5L, 3L);
```

Ý nghĩa là **3 byte** bắt đầu ở byte offset 2 của `source` được copy vào byte offset 5 của `destination`. Lệnh không tự thay đổi độ lớn hai segment. Phải bảo đảm các khoảng `[2, 5)` và `[5, 8)` đều nằm trong phạm vi tương ứng.

Cũng có thể tạo slice:

```java
destination.asSlice(5L, 3L).copyFrom(source.asSlice(2L, 3L));
```

`asSlice(offset, length)` tạo view không copy. Khi dữ liệu đã chứa trong slice, `copyFrom` xử lý đúng vùng slice; không cần tự cộng offset thêm lần nữa.

## 4. `fill(byte)`: điền dữ liệu theo **byte**, không phải phần tử

```java
MemorySegment segment = MemorySegment.ofArray(
        new byte[]{10, 20, 30, 40, 50});

segment.asSlice(1, 3).fill((byte) 7);

System.out.println(java.util.Arrays.toString(
        segment.toArray(ValueLayout.JAVA_BYTE)));
// [10, 7, 7, 7, 50]
```

Ở đây `asSlice(1, 3)` đại diện ba byte offset 1, 2, 3 trong segment gốc. `fill((byte)7)` ghi giá trị 7 lên **mỗi byte** của slice đó. Hai byte ngoài slice giữ nguyên.

### 4.1. Điền zero thường gặp khi khởi tạo/reset buffer

```java
segment.fill((byte) 0);
```

Lệnh ghi `0` vào toàn bộ vùng của segment đang được tham chiếu, miễn là segment writable, scope còn sống và thread có quyền. Với native memory từ arena JDK 22, vùng mới cấp phát được **zero-initialized**, nhưng `fill((byte)0)` vẫn hữu ích khi **tái sử dụng** buffer hoặc muốn reset một slice sau khi dữ liệu đã thay đổi.

### 4.2. Cảnh báo khi điền trên segment chứa `int[]`

Nếu segment chứa 3 số `int`, không được hiểu:

```java
int[] values = {10, 20, 30};
MemorySegment.ofArray(values).fill((byte) 1);
```

thành “đặt mọi `int` bằng 1”. Lệnh ghi **byte `0x01` vào từng vị trí byte**; mỗi `int` gồm bốn byte 01, nên giá trị trở thành `0x01010101` = **16843009**.

Muốn đặt **từng phần tử `int` = 1**:

```java
MemorySegment ints = MemorySegment.ofArray(new int[3]);
for (long i = 0; i < 3; i++) {
    ints.setAtIndex(ValueLayout.JAVA_INT, i, 1);
}
```

Để điền hàng loạt giá trị có cấu trúc vào native memory, cân nhắc dùng `setAtIndex` theo layout hoặc copy từ một mảng đã điền sẵn. `fill` lý tưởng cho reset/fill **byte pattern**; nó không tự hiểu kiểu số học nằm trong dữ liệu.

### 4.3. Vì sao `fill` không phù hợp cho mọi tình huống?

- Không có bảo đảm các byte được ghi theo **thứ tự quan sát cụ thể** trong lúc đang fill; không dùng nó làm primitive đồng bộ đa thread.
- Dùng trên segment read-only sẽ ném `IllegalArgumentException`.
- Dùng trên segment thuộc arena đã đóng sẽ ném `IllegalStateException`.
- Dùng từ thread không sở hữu confined arena sẽ ném `WrongThreadException`.

Nếu cần write nguyên tử, ordering hay cấu trúc dữ liệu dùng chung giữa threads, phải thiết kế đồng bộ riêng; `fill` chỉ là thao tác nội dung bộ nhớ.

## 5. `mismatch`: tìm byte khác đầu tiên

`MemorySegment.mismatch` so sánh **nội dung**, không so sánh identity/reference hay địa chỉ. Bản thường dùng:

```java
long difference = left.mismatch(right);
```

Kết quả:

- `-1` nếu **toàn bộ byte và độ dài** hai segment giống nhau.
- Một số nguyên `>= 0` là **offset byte** của khác biệt đầu tiên.
- Nếu một segment là **prefix đúng** của segment kia, kết quả là **độ dài tính bằng byte của segment ngắn hơn**. Trường hợp này hai vùng có byte đầu giống nhưng không có cùng độ dài.
- Không trả về vị trí phần tử `int`/`double`; phải quy đổi nếu cần.

Ví dụ:

```java
MemorySegment a = MemorySegment.ofArray(new byte[]{1, 2, 3});
MemorySegment b = MemorySegment.ofArray(new byte[]{1, 2, 9});
MemorySegment c = MemorySegment.ofArray(new byte[]{1, 2});

System.out.println(a.mismatch(a)); // -1
System.out.println(a.mismatch(b)); // 2
System.out.println(a.mismatch(c)); // 2: c là prefix của a
```

**Không nhầm `mismatch` với `equals`:** `equals` xét sự tương đương của các đối tượng segment theo quy tắc của `MemorySegment`, không phải API khuyến nghị để xác định hai vùng byte có nội dung giống nhau. Muốn so byte, dùng `mismatch`.

### 5.1. Đối chiếu một vùng con

Có hai cách:

**Cách A — so slice**:

```java
long mismatch = left.asSlice(10, 4)
                    .mismatch(right.asSlice(20, 4));
```

Kết quả là vị trí **tương đối từ đầu hai slice**, trong khoảng 0..3 hoặc `-1`. Nếu cần offset tuyệt đối của `left` khi có khác biệt, cộng `10` vào kết quả **chỉ khi `mismatch >= 0`**.

**Cách B — hàm static có ranges**:

```java
long mismatch = MemorySegment.mismatch(
        left, 10, 14,
        right, 20, 24);
```

Các khoảng có dạng **`[fromOffset, toOffset)`**, offset **cuối không bao gồm**. Trong ví dụ đều so 4 byte; kết quả cũng tính **tương đối từ đầu vùng được chọn**, không phải offset tuyệt đối của toàn segment.

### 5.2. Cẩn trọng khi kiểm tra dữ liệu kiểu số

Vì so **byte**, hai số học cùng giá trị có thể bị xem là khác nếu byte order hoặc cách mã hóa khác nhau. `mismatch` không tự endian-swap và không tự chuyển kiểu `int` hay chuẩn hóa `NaN`. Nếu muốn so **giá trị logic** thay vì bytes, phải đọc theo cùng layout/endianness rồi so các giá trị Java; còn nếu muốn kiểm chứng **wire-format/binary-format** thì so byte chính là mục tiêu.

Đối với mảng lớn, `mismatch` hữu ích để tìm offset đầu tiên khác khi validate copy/serialization; nó không tạo một bản sao dữ liệu và không trả về một danh sách đầy đủ các offset khác.

## 6. `toArray`: chuyển toàn bộ segment sang mảng Java mới

Khi cần trả dữ liệu native về code Java thông thường:

```java
byte[] bytes = segment.toArray(ValueLayout.JAVA_BYTE);
int[] ints   = segment.toArray(ValueLayout.JAVA_INT);
long[] longs = segment.toArray(ValueLayout.JAVA_LONG);
```

Đây là **ba ví dụ lựa chọn độc lập**, mỗi layout yêu cầu segment có nội dung phù hợp; không phải lúc nào cũng đọc cùng một buffer bằng mọi layout. `toArray` tạo **một mảng mới**, sao chép nội dung qua layout đưa vào.

### 6.1. Chọn layout để quyết định kiểu mảng

| Gọi `toArray` | Kiểu kết quả | Yêu cầu |
| --- | --- | --- |
| `toArray(ValueLayout.JAVA_BYTE)` | `byte[]` | Một phần tử/byte |
| `toArray(ValueLayout.JAVA_CHAR)` | `char[]` | Số byte chia hết cho 2 |
| `toArray(ValueLayout.JAVA_SHORT)` | `short[]` | Số byte chia hết cho 2 |
| `toArray(ValueLayout.JAVA_INT)` | `int[]` | Số byte chia hết cho 4 |
| `toArray(ValueLayout.JAVA_FLOAT)` | `float[]` | Số byte chia hết cho 4 |
| `toArray(ValueLayout.JAVA_LONG)` | `long[]` | Số byte chia hết cho 8 |
| `toArray(ValueLayout.JAVA_DOUBLE)` | `double[]` | Số byte chia hết cho 8 |

`byteSize() / layout.byteSize()` phải vừa với chiều dài mảng Java (`Integer.MAX_VALUE`) và việc truy cập phải hợp lệ. Với dữ liệu multi-byte, byte order của layout tham gia diễn giải dữ liệu; nếu thứ tự byte của layout khác thứ tự byte native, `toArray` thực hiện phép đổi byte order cho mỗi phần tử như tài liệu API mô tả.

**Không có `toArray(ValueLayout.JAVA_BOOLEAN)` trong các overload `toArray` của Java 22.** Các overload bulk-copy mảng cũng hỗ trợ `byte[]`, `char[]`, `short[]`, `int[]`, `float[]`, `long[]`, `double[]`, không hỗ trợ `Object[]` hay `String[]`. Với dữ liệu biểu diễn boolean hay struct, định nghĩa quy tắc mã hóa và tự chuyển đổi thành các đối tượng Java cần thiết.

### 6.2. `toArray` không chia sẻ cùng vùng dữ liệu

```java
MemorySegment nativeSegment = /* native segment còn sống */;
int[] snapshot = nativeSegment.toArray(ValueLayout.JAVA_INT);

snapshot[0] = 500;
// Không có cam kết thay đổi này sẽ được ghi ngược vào nativeSegment.
```

Đoạn minh họa này **không độc lập** vì cần `nativeSegment` đã có và có kích thước hợp lệ. Mảng kết quả là **copy**; sửa `snapshot` sẽ không tự động viết vào vùng gốc. Muốn ghi lại, cần `MemorySegment.copy` từ mảng vào segment hoặc một vòng lặp `setAtIndex`.

### 6.3. Khi chỉ cần một phần, tránh tạo array quá lớn

`toArray` copy **toàn bộ** segment. Với dữ liệu rất lớn, lấy slice hoặc copy trực tiếp vào mảng nhỏ:

```java
byte[] header = segment.asSlice(0, 16)
                       .toArray(ValueLayout.JAVA_BYTE);
```

Trước khi dùng, bảo đảm `segment.byteSize() >= 16`. Nếu dữ liệu có hàng tỷ byte, tạo mảng Java khổng lồ có thể không thực tế hoặc vượt giới hạn; API không tự động phân trang/chunk cho bạn. Có thể lặp qua từng slice với giới hạn kích thước được xác nhận.

## 7. Ví dụ chạy được — phần 1: copy, fill, mismatch và `byte[]`

Tạo tệp **`SegmentBulkDemo.java`** (không khai báo package). Đây là chương trình Java **độc lập**, dùng JDK 22+; không cần C/JNI.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public final class SegmentBulkDemo {
    private SegmentBulkDemo() {}

    public static void main(String[] args) {
        byte[] source = {1, 2, 3, 4, 5, 6};
        MemorySegment heap = MemorySegment.ofArray(source);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeData = arena.allocate(source.length);

            // 1. Copy heap -> native. Hai vùng lưu trữ độc lập.
            nativeData.copyFrom(heap);
            System.out.println("copy = " +
                    Arrays.toString(nativeData.toArray(ValueLayout.JAVA_BYTE)));

            source[0] = 99;
            System.out.println("native[0] = " +
                    nativeData.get(ValueLayout.JAVA_BYTE, 0));

            // 2. Fill ba byte trong slice [1, 4).
            nativeData.asSlice(1, 3).fill((byte) 9);
            System.out.println("filled = " +
                    Arrays.toString(nativeData.toArray(ValueLayout.JAVA_BYTE)));

            // 3. Mismatch trả vị trí byte khác đầu tiên.
            MemorySegment clone = arena.allocate(nativeData.byteSize());
            clone.copyFrom(nativeData);
            System.out.println("equal mismatch = " + nativeData.mismatch(clone));

            clone.set(ValueLayout.JAVA_BYTE, 3, (byte) 8);
            System.out.println("changed mismatch = " + nativeData.mismatch(clone));

            // 4. toArray luôn tạo mảng Java mới.
            byte[] javaCopy = nativeData.toArray(ValueLayout.JAVA_BYTE);
            javaCopy[0] = 77;
            System.out.println("native after array edit = " +
                    nativeData.get(ValueLayout.JAVA_BYTE, 0));
            System.out.println("java copy = " + Arrays.toString(javaCopy));

            // 5. Copy một đoạn từ segment vào mảng Java có sẵn.
            byte[] picked = new byte[3];
            MemorySegment.copy(
                    nativeData, ValueLayout.JAVA_BYTE, 2,
                    picked, 0, picked.length);
            System.out.println("picked = " + Arrays.toString(picked));

            // 6. Copy ngược từ mảng Java vào một vị trí của segment.
            byte[] patch = {7, 8};
            MemorySegment.copy(
                    patch, 0,
                    nativeData, ValueLayout.JAVA_BYTE, 4, patch.length);
            System.out.println("patched = " +
                    Arrays.toString(nativeData.toArray(ValueLayout.JAVA_BYTE)));

            // 7. ofArray chia sẻ dữ liệu với mảng backing.
            heap.set(ValueLayout.JAVA_BYTE, 1, (byte) 42);
            System.out.println("source = " + Arrays.toString(source));
        }
    }
}
```

### 7.1. Biên dịch/chạy

Dùng JDK 22 trở lên và đứng trong thư mục chứa file:

```bash
javac SegmentBulkDemo.java
java SegmentBulkDemo
```

Không cần `--enable-preview` với JDK 22+; không cần `System.loadLibrary`. Ứng dụng chỉ thao tác `MemorySegment` thông qua FFM Java API.

### 7.2. Stdout chính xác

```text
copy = [1, 2, 3, 4, 5, 6]
native[0] = 1
filled = [1, 9, 9, 9, 5, 6]
equal mismatch = -1
changed mismatch = 3
native after array edit = 1
java copy = [77, 9, 9, 9, 5, 6]
picked = [9, 9, 5]
patched = [1, 9, 9, 9, 7, 8]
source = [99, 42, 3, 4, 5, 6]
```

**Giải thích lần lượt:**

1. `copyFrom` đưa dữ liệu từ mảng `source` vào native block. Sửa `source[0]=99` sau đó không sửa `nativeData` nên `native[0]=1`.
2. `asSlice(1,3).fill((byte)9)` chỉ sửa ba byte offset 1, 2, 3; hai byte cuối và byte đầu giữ nguyên.
3. `clone.copyFrom(nativeData)` tạo nội dung giống hệt nên `mismatch=-1`. Sửa byte số 3 của clone thành 8 khiến `mismatch=3`.
4. `toArray` tạo mảng mới: sửa `javaCopy[0]=77` không ảnh hưởng nativeData.
5. `MemorySegment.copy(..., offset=2, ..., length=3)` đưa byte 2, 3, 4 thành `[9,9,5]`.
6. Overload array→segment ghi `[7,8]` vào byte offset 4,5 của nativeData.
7. `heap` là view trên chính mảng source, nên sửa qua `heap.set` làm `source[1]=42`, bên cạnh `source[0]=99` được sửa trực tiếp.

Khi `try` kết thúc, arena đóng và native blocks không còn hợp lệ. Mảng `source` và `javaCopy` vẫn là Java heap arrays bình thường, không phụ thuộc vòng đời arena.

## 8. Ví dụ chạy được — phần 2: chuyển `int[]`, offset và layout

Một lỗi phổ biến là dùng `byteSize()` như số lượng `int`, hoặc viết `dstOffset=1` khi muốn bắt đầu từ phần tử `int` thứ hai. Đoạn sau thực hành copy **có layout** để tránh nhầm.

Tạo tệp **`SegmentIntDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public final class SegmentIntDemo {
    private SegmentIntDemo() {}

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40};

        long intBytes = ValueLayout.JAVA_INT.byteSize();
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeInts = arena.allocate(
                    values.length * intBytes,
                    ValueLayout.JAVA_INT.byteAlignment());

            // Số phần tử = 4, không phải 16.
            MemorySegment.copy(
                    values, 0,
                    nativeInts, ValueLayout.JAVA_INT, 0, values.length);

            // Sửa phần tử index=1 trong native memory.
            nativeInts.setAtIndex(ValueLayout.JAVA_INT, 1, 99);

            int[] exported = nativeInts.toArray(ValueLayout.JAVA_INT);
            System.out.println("native ints = " + Arrays.toString(exported));
            System.out.println("original ints = " + Arrays.toString(values));

            // Bắt đầu từ offset byte = 1 * 4, lấy 2 phần tử.
            int[] middle = new int[2];
            MemorySegment.copy(
                    nativeInts, ValueLayout.JAVA_INT, intBytes,
                    middle, 0, middle.length);
            System.out.println("middle = " + Arrays.toString(middle));

            // ofArray là view: sửa heap segment làm thay đổi values.
            MemorySegment heapView = MemorySegment.ofArray(values);
            heapView.setAtIndex(ValueLayout.JAVA_INT, 0, -1);
            System.out.println("heap-backed ints = " +
                    Arrays.toString(values));
        }
    }
}
```

Lệnh chạy:

```bash
javac SegmentIntDemo.java
java SegmentIntDemo
```

Stdout chính xác:

```text
native ints = [10, 99, 30, 40]
original ints = [10, 20, 30, 40]
middle = [99, 30]
heap-backed ints = [-1, 20, 30, 40]
```

**Vì sao đúng:** `values.length=4` phần tử, mỗi `int` có size 4 byte, nên native segment cần 16 byte. `setAtIndex(JAVA_INT,1,99)` tương đương ghi `int` tại offset 4 byte, còn `MemorySegment.copy` với mảng dùng `elementCount` là số lượng phần tử và `dstOffset/srcOffset` của segment theo byte.

Khi `nativeInts.toArray(JAVA_INT)` tạo `exported`, đó là một bản sao độc lập, vì vậy `values` chưa thay đổi thành `99`. Chỉ lúc `heapView.setAtIndex(...)` được gọi, mảng `values` mới bị sửa trực tiếp qua heap-backed segment.

### 8.1. Không ép mọi byte buffer thành `int[]`

Với `byteSize() = 6`, gọi `toArray(ValueLayout.JAVA_INT)` không thể chia đều thành các phần tử 4 byte và sẽ thất bại (theo Javadoc, `IllegalStateException` nếu dữ liệu không thể chuyển thành mảng loại đó). Cách xử lý: xác thực `size % layout.byteSize() == 0` hoặc lấy slice có độ dài hợp lệ, rồi dùng đúng layout.

Nếu segment rất lớn mà `byteSize()/layout.byteSize() > Integer.MAX_VALUE`, một Java array thông thường không thể biểu diễn tất cả phần tử trong một lần. Cần chia batch/chunks.

### 8.2. `setAtIndex` và `getAtIndex` giúp giảm lỗi offset

So sánh:

```java
int second = nativeInts.get(ValueLayout.JAVA_INT, 4L);
int alsoSecond = nativeInts.getAtIndex(ValueLayout.JAVA_INT, 1L);
```

Đây là **trích đoạn minh họa** khi `nativeInts` đã có 8 byte trở lên và có căn chỉnh đúng. Hai câu đều trỏ phần tử `int` thứ hai nếu `JAVA_INT.byteSize()=4`. `getAtIndex` nhân chỉ số với kích thước layout; với xử lý mảng các phần tử cùng kích thước nó dễ đọc hơn tự tính offset.

## 9. Sao chép an toàn khi source và destination chồng lấp

`MemorySegment.copy` hỗ trợ các vùng chồng lấp theo semantics tương tự **memmove**: khi vùng nguồn và đích overlap mà API nhận biết, kết quả như thể đã copy qua một buffer tạm, không phải copy ngây thơ đè lên dữ liệu chưa đọc. Ví dụ Java 22+ độc lập:

```java
import java.lang.foreign.MemorySegment;
import java.util.Arrays;

public class SegmentOverlapDemo {
    public static void main(String[] args) {
        byte[] bytes = {1, 2, 3, 4, 5};
        MemorySegment view = MemorySegment.ofArray(bytes);

        MemorySegment.copy(view, 0, view, 1, 4);

        System.out.println(Arrays.toString(bytes));
    }
}
```

Biên dịch/chạy:

```bash
javac SegmentOverlapDemo.java
java SegmentOverlapDemo
```

Kết quả:

```text
[1, 1, 2, 3, 4]
```

Trong lệnh này vùng byte nguồn là `[0,4)` và vùng đích là `[1,5)` của **cùng backing array**. `copy` không làm mảng thành `[1,1,1,1,1]` như một vòng lặp copy tuần tự sai.

**Giới hạn quan trọng:** nếu hai segment **không được nhận diện là overlap** nhưng lại tham chiếu tới các vùng bộ nhớ vật lý trùng nhau qua **địa chỉ khác nhau** (ví dụ mapping cùng một file theo cách bất thường), Javadoc nêu kết quả bulk copy là **không xác định**. Đừng biến bảo đảm overlap thông thường thành lời hứa cho mọi aliasing từ native address.

## 10. Copy theo phần tử, byte order và dữ liệu dạng số

Với dữ liệu số nhiều byte, có hai kiểu copy quan trọng:

**A. Copy byte thô**:

```java
MemorySegment.copy(src, 0, dst, 0, 16);
```

Copy nguyên **16 byte**, không diễn giải nội dung. Byte thứ N sang byte thứ N. Phù hợp khi cần giữ đúng **binary representation**.

**B. Copy theo layout**:

```java
MemorySegment.copy(
        src, ValueLayout.JAVA_INT, 0,
        dst, ValueLayout.JAVA_INT, 0,
        4);
```

Copy **4 phần tử `int`**, mỗi phần tử 4 byte, tổng 16 byte. Có overload nhận layout nguồn và đích; nếu hai layout cùng kích thước nhưng **byte order khác nhau**, API có thể **byte-swap theo từng phần tử** khi copy. Layout nguồn/đích phải cùng `byteSize` và phải tuân thủ alignment của từng bên.

Ví dụ về ý tưởng khi nhập dữ liệu network big-endian sang buffer native-order:

```java
import java.nio.ByteOrder;

var networkInt = ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
var localInt = ValueLayout.JAVA_INT.withOrder(ByteOrder.nativeOrder());

MemorySegment.copy(
        networkBuffer, networkInt, 0,
        localBuffer, localInt, 0,
        count);
```

**Đây là trích đoạn minh họa, không phải file chạy độc lập**: `networkBuffer` và `localBuffer` phải là các MemorySegment sống/đúng kích thước/đúng căn chỉnh, `count` là số lượng phần tử. Cách copy theo layout giữ ý nghĩa số `int` giữa hai byte order, còn copy byte thô sẽ giữ nguyên chuỗi byte trên bộ nhớ.

**Endianness và alignment là hai thuộc tính riêng:**

- `withOrder` điều chỉnh cách diễn giải thứ tự byte; **không làm thay đổi kích thước** của một `int`.
- `byteAlignment` đặt ràng buộc căn chỉnh; heap segment backed by `byte[]` không mặc nhiên đủ alignment cho `JAVA_INT`.
- Khi cần truy cập `int` từ một `byte[]` ở vị trí không căn chỉnh, dùng `ValueLayout.JAVA_INT_UNALIGNED` hoặc layout được hạ alignment thích hợp, và vẫn tính offset đúng.
- `toArray(ValueLayout.JAVA_INT.withOrder(...))` dùng layout để diễn giải dữ liệu thành các giá trị `int` trước khi đưa vào mảng Java.

## 11. `MemorySegment.ofArray`, `MemorySegment.copy` và `toArray`: khác nhau về ownership

Hãy xét ba dòng này (sử dụng một `byte[] original` và segment `nativeBuffer` còn sống):

```java
MemorySegment heapView = MemorySegment.ofArray(original);
nativeBuffer.copyFrom(heapView);
byte[] independent = nativeBuffer.toArray(ValueLayout.JAVA_BYTE);
```

- **`heapView`** chia sẻ backing với `original`. Sửa dữ liệu qua view sửa `original`.
- **`nativeBuffer`** là vùng riêng nếu được cấp phát độc lập trong arena. Sau `copyFrom`, nội dung bằng original tại thời điểm copy, nhưng **không đồng bộ tự động** với original.
- **`independent`** là `byte[]` mới từ `toArray`. Sửa nó không làm `nativeBuffer` thay đổi.

Sơ đồ:

```text
Java byte[] original
          ^
          | CHIA SẺ (không copy)
          v
MemorySegment.ofArray(original)
          |
          | copyFrom (chép bytes thật)
          v
    nativeBuffer (off-heap)
          |
          | toArray(JAVA_BYTE) (chép bytes thật)
          v
 Java byte[] independent
```

**Lỗi phổ biến:** dùng `MemorySegment.ofArray(array)` rồi gọi đó là “mảng đã được copy ra native memory”. Không đúng: segment vẫn backed by Java array. Muốn native memory độc lập, allocate bằng arena rồi copy.

Ngược lại, đôi khi **không cần copy**: nếu chỉ cần điền/checksum dữ liệu trong một mảng Java hiện có, tạo heap view bằng `ofArray` có thể là lựa chọn tốt hơn; lưu ý phạm vi và thread safety.

## 12. Những API chuyển đổi thường gặp khác

### 12.1. Copy trực tiếp từ segment vào mảng Java có sẵn

```java
byte[] output = new byte[8];
MemorySegment.copy(segment, ValueLayout.JAVA_BYTE,
                   4L, output, 0, output.length);
```

Ví dụ này giả định `segment` còn sống và có ít nhất 12 byte. Nó **không tạo mảng mới** trong API copy; caller đã cấp phát `output`. Tham số `srcOffset=4L` là **byte offset**; `dstIndex=0` là **array element index**; `elementCount=8`.

**Tại sao hữu ích:** muốn tái sử dụng Java arrays trong hệ thống xử lý nhiều batch để giảm tạo object/rác heap. Tuy nhiên, copy vẫn có chi phí chuyển byte giữa hai vùng.

### 12.2. Copy từ mảng Java vào native segment

```java
int[] source = {10, 20, 30};
MemorySegment.copy(source, 0, nativeInts,
                   ValueLayout.JAVA_INT, 0L, source.length);
```

Đoạn này giả định `nativeInts` có ít nhất 12 byte, căn chỉnh phù hợp và writable. Array index (`0`) là đơn vị **phần tử int**, còn segment offset (`0L`) đo bằng byte. `MemorySegment.copy` có overload nhận `Object` cho array, nhưng kiểm tra carrier: không đưa `double[]` vào layout `JAVA_INT`.

### 12.3. Sao chép tới một slice/đọc một slice

```java
MemorySegment header = entireSegment.asSlice(0, 16);
byte[] bytes = header.toArray(ValueLayout.JAVA_BYTE);
```

`header` là **view**, `bytes` là **copy**. Sau khi lấy `bytes`, dữ liệu Java tồn tại độc lập với tuổi thọ của native `entireSegment`. Nhưng `header` vẫn bị ràng buộc bởi scope và thread confinement của vùng nguồn.

### 12.4. `asByteBuffer` khi cần NIO

`MemorySegment.asByteBuffer()` tạo view kiểu `ByteBuffer` của segment, phù hợp khi tích hợp thư viện chỉ nhận NIO buffer. Đây **không phải** `toArray`, và việc byte buffer chia sẻ/tiếp cận bộ nhớ phải tuân theo scope và giới hạn của segment. Nếu cần **mảng Java độc lập**, ưu tiên `toArray` hoặc copy trực tiếp.

Với segment quá lớn, `ByteBuffer` có giới hạn index theo `int`; không mặc nhiên cho rằng toàn bộ native segment với `byteSize > Integer.MAX_VALUE` đều có thể ánh xạ thành một `ByteBuffer` duy nhất.

## 13. Lỗi biên và exception thường gặp

| Tình huống | Kiểu lỗi thường gặp | Giải thích |
| --- | --- | --- |
| `dest.copyFrom(src)` khi dest nhỏ hơn src | `IndexOutOfBoundsException` | Thiếu chỗ chứa toàn bộ byte nguồn |
| Copy với `srcOffset < 0` hoặc vượt giới hạn | `IndexOutOfBoundsException` | Vùng nguồn không hợp lệ |
| `fill` hoặc copy vào view read-only | `IllegalArgumentException` | Không được phép ghi vào destination |
| Thao tác segment sau khi arena đóng | `IllegalStateException` | Scope không còn sống |
| Worker khác đọc/ghi segment từ `Arena.ofConfined()` | `WrongThreadException` | Thread confinement bị vi phạm |
| `toArray(JAVA_INT)` với segment 6 byte | `IllegalStateException` | Kích thước không chia hết cho 4 |
| `toArray` tạo số phần tử quá lớn | `IllegalStateException` | Không thể biểu diễn bằng Java array hợp lệ |
| Typed `MemorySegment.copy` với layout khác kích thước | `IllegalArgumentException` | Cần hai layout có cùng kích thước phần tử |
| Copy `double[]` cùng `JAVA_INT` | `IllegalArgumentException` | Carrier/layout không khớp kiểu mảng |
| Ghi `JAVA_INT` vào heap segment backed by `byte[]` không đủ alignment | `IllegalArgumentException` | Layout/offset không tương thích alignment |
| `mismatch` dùng vùng [from,to) vượt byteSize | `IndexOutOfBoundsException` | Giới hạn của region bị vi phạm |

Có thể còn các lỗi liên quan `null`, overflow số byte, native allocation hoặc cấu hình môi trường. Hãy kiểm tra **kích thước, offset, layout, scope và read-only** trước khi gọi. Không bắt mọi `RuntimeException` rồi bỏ qua để chương trình tiếp tục với dữ liệu không đáng tin.

### 13.1. Kiểm tra trước khi copy từ một nguồn không tin cậy

Một helper điển hình:

```java
static void copyChecked(MemorySegment src,
                        long srcOffset,
                        MemorySegment dst,
                        long dstOffset,
                        long bytes) {
    if (bytes < 0 || srcOffset < 0 || dstOffset < 0
            || srcOffset > src.byteSize() - bytes
            || dstOffset > dst.byteSize() - bytes) {
        throw new IndexOutOfBoundsException("Invalid copy range");
    }
    MemorySegment.copy(src, srcOffset, dst, dstOffset, bytes);
}
```

Đây là **trích đoạn phương thức**, cần đặt trong một class có import `java.lang.foreign.MemorySegment`. Kiểm tra dạng `offset > size - length` giúp tránh phép cộng `offset + length` có thể overflow. Tuy nhiên helper này **không thay thế** checks của FFM: destination có thể read-only, segment có thể dead hoặc confined.

Với copy theo phần tử, dùng `Math.multiplyExact(elementCount, layout.byteSize())` hoặc so giới hạn bằng phép chia cẩn thận để tránh overflow khi tính kích thước byte.

### 13.2. Không quên đóng arena

```java
MemorySegment leaked;
try (Arena arena = Arena.ofConfined()) {
    leaked = arena.allocate(8);
}
// Đừng sử dụng leaked sau điểm này.
```

Đoạn này minh họa lỗi vòng đời: `leaked` chỉ còn là object đại diện cho segment, không bảo đảm backing memory còn hợp lệ. Cách đúng là thực hiện `toArray` **trong try**, rồi trả Java array độc lập cho bên gọi:

```java
static byte[] readResult() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment block = arena.allocate(8);
        block.fill((byte) 5);
        return block.toArray(ValueLayout.JAVA_BYTE);
    }
}
```

Đây là một **phương thức minh họa**, đặt trong class có imports `Arena`, `MemorySegment`, `ValueLayout`. Khi return, mảng `byte[]` đã được copy, không phụ thuộc `arena` đóng sau đó.

## 14. Hiệu năng và sự lựa chọn API

### 14.1. Copy hay view?

- `ofArray`/`asSlice`: **view**, thường không copy nội dung và phù hợp khi cần đọc/ghi ngay trên backing chung; phải kiểm soát aliasing và thread safety.
- `copyFrom`/`copy`: **copy**, có chi phí theo lượng dữ liệu nhưng tách backing nếu target là vùng được cấp phát độc lập.
- `toArray`: **copy + cấp phát Java array mới**, dễ sử dụng nhưng tăng áp lực GC nếu gọi liên tục với dữ liệu lớn.
- `MemorySegment.copy(..., array, ...)`: copy vào **Java array do caller quản lý**, hữu ích khi muốn tái sử dụng buffer.

**Không coi `copy` là zero-copy**, ngay cả khi FFM nội bộ tối ưu các lệnh bulk copy. Ngược lại, view không đồng nghĩa không có cost: việc quản lý scope, alignment, access và đồng bộ vẫn có thể quan trọng.

### 14.2. Ưu tiên bulk operation khi phù hợp

Thay vì gọi `get(JAVA_BYTE, i)` và `set(JAVA_BYTE, i)` trong vòng lặp dài hàng triệu lần chỉ để chuyển nguyên bytes, ưu tiên `copyFrom` hoặc `MemorySegment.copy` cho dải lớn. Dùng `fill` để điền một byte pattern, `mismatch` để tìm byte khác và `toArray` khi thật sự cần mảng Java độc lập.

Nhưng nếu cần diễn giải phần tử, xử lý số học hoặc đổi cấu trúc, bạn vẫn phải dùng `ValueLayout` đúng và có thể cần loop hoặc copy theo element layout.

### 14.3. Chia chunk với dữ liệu rất lớn

Một Java `byte[]` có kích thước do `int` giới hạn, còn `MemorySegment.byteSize()` là `long`. Với native segment rất lớn, không cố gọi `toArray` cho toàn bộ nếu vượt giới hạn. Có thể xử lý theo chunk:

```java
// Minh họa khi src là một MemorySegment còn sống.
long position = 0L;
final int chunkSize = 64 * 1024;

while (position < src.byteSize()) {
    int count = (int) Math.min(
            (long) chunkSize, src.byteSize() - position);
    byte[] chunk = src.asSlice(position, count)
                      .toArray(ValueLayout.JAVA_BYTE);
    // Gửi chunk sang code Java cần xử lý, rồi mới lặp tiếp.
    position += count;
}
```

Đây là **trích đoạn**, không có biến `src` độc lập. Cần thiết kế consumer rõ ràng, tránh tích trữ tất cả `chunk` trong RAM nếu mục tiêu là streaming. Cũng không dùng một segment đã đóng scope.

### 14.4. Thread safety

`Arena.ofShared()` cho phép nhiều thread **truy cập** segment, nhưng **không tự cung cấp giao thức tránh data race** khi hai thread ghi/chạy `fill` hoặc `copy` đồng thời trên các dải overlap. Dùng phân chia vùng dữ liệu không giao nhau, lock hoặc memory-ordering phù hợp. `mismatch` đọc bytes tại một thời điểm không được bảo đảm snapshot nguyên tử nếu thread khác đang thay đổi cùng vùng.

## 15. Tình huống trước–sau

### A. Nhận payload native và đưa về Java

**Trước:** trả `MemorySegment` của arena sẽ đóng ngay sau lời gọi; phía Java dùng sau đó bị `IllegalStateException`.

**Sau:** trước khi arena đóng, tạo `byte[] result = segment.toArray(JAVA_BYTE)` rồi trả mảng Java. Chấp nhận một lần copy để có ownership đơn giản.

### B. Tái sử dụng buffer native

**Trước:** lặp từng byte và ghi zero để reset.

**Sau:** `buffer.fill((byte)0)`, hoặc `buffer.asSlice(headerBytes, payloadBytes).fill((byte)0)` nếu chỉ muốn reset payload. Nhớ đây là điền byte, không phải giá trị của từng struct field.

### C. Phát hiện hỏng nội dung khi copy

**Trước:** so địa chỉ hai segment hoặc dùng `==` rồi kết luận khác nội dung.

**Sau:** `long firstDiff = expected.mismatch(actual)`. Nếu `-1`, byte sequence và kích thước bằng nhau. Nếu `>= 0`, báo offset byte đầu khác, rồi có thể trích một slice để debug.

### D. Xử lý vùng giữa một bản ghi lớn

**Trước:** `toArray` toàn bộ 100 MB chỉ để lấy 32 byte header phụ.

**Sau:** `segment.asSlice(headerOffset, 32).toArray(JAVA_BYTE)` hoặc copy trực tiếp vào `byte[32]` có sẵn. Bảo đảm đã kiểm tra giới hạn.

### E. Ghi mảng `int[]` vào native buffer

**Trước:** lấy `values.length=100` và cấp phát 100 byte, rồi copy 100 số `int` → sai kích thước.

**Sau:** cấp phát `100 * JAVA_INT.byteSize() = 400` byte với alignment phù hợp, dùng typed `MemorySegment.copy(values, 0, native, JAVA_INT, 0, values.length)`; khi nhận lại, `native.toArray(JAVA_INT)` tạo mảng int mới.

## 16. Câu hỏi tự luyện

**1. `fill((byte)1)` trên segment chứa `int[]` có điền từng `int` bằng 1 không?** Không. Nó điền từng byte 01; một `int` gồm bốn byte 01 trở thành `0x01010101`.

**2. `MemorySegment.ofArray(byte[])` có sao chép dữ liệu không?** Không. Nó tạo heap segment backed by chính mảng ấy. Sửa qua segment có thể quan sát ngay trong mảng.

**3. `toArray(JAVA_BYTE)` có trả view cùng backing không?** Không. Nó tạo và trả một **Java byte array mới** bằng cách copy.

**4. `left.mismatch(right) == -1` có nghĩa là gì?** Hai byte sequences so sánh giống nhau và có cùng độ dài. Nếu một bên chỉ là prefix đúng của bên còn lại, kết quả là độ dài bên ngắn hơn, không phải `-1`.

**5. Offset trong `MemorySegment.copy` tính bằng gì?** Offset segment bằng **byte**; index Java array là **phần tử**; `elementCount` của typed copy là **số phần tử**.

**6. `copyFrom` cho destination nhỏ hơn source sẽ tự mở rộng destination không?** Không. Nó thất bại vì không đủ chỗ.

**7. `Arena.ofConfined()` có cho thread khác truy cập native segment không?** Không. Cần đúng owner thread; nếu thực sự chia sẻ, cân nhắc shared arena và đồng bộ dữ liệu đúng cách.

**8. Có thể gọi `toArray(JAVA_INT)` trên segment 6 byte không?** Không. Segment phải có độ dài chia hết cho 4 và số phần tử hợp lệ.

**9. `MemorySegment.copy` có hỗ trợ overlap giữa hai slice của cùng backing không?** Có, theo semantics tương tự copy qua buffer tạm với overlap được nhận diện. Không suy rộng cho aliasing vật lý bất thường qua các address khác nhau.

**10. Khi code chạy trên JDK 17, có thể copy ví dụ `java.lang.foreign.MemorySegment` JDK 22 y nguyên không?** Không. Cần JDK 22+ để dùng bản API FFM ổn định ở đây.

## 17. Checklist khi dùng MemorySegment trong dự án

1. Chọn đúng **JDK 22+** cho mã dùng `java.lang.foreign` ổn định; không trộn ví dụ incubator/preview cũ.
2. Kiểm tra **heap view (`ofArray`) vs native allocation (`Arena`)** và ownership của dữ liệu.
3. Đừng nhầm **`byteSize`/offset byte** với **số phần tử/index Java array**.
4. Với `fill`, nhớ **một giá trị byte được lặp lại**, không phải phép gán từng phần tử `int/long`.
5. Với `copyFrom`, đảm bảo destination đủ lớn; với `copy`, kiểm tra mọi offset/length và quyền ghi.
6. Với typed copy hoặc `toArray`, dùng `ValueLayout` đúng kiểu, kích thước, alignment và endian.
7. `mismatch` so **byte**, trả **offset byte** đầu khác hoặc `-1`; kiểm tra cả trường hợp một vùng là prefix.
8. Khi cần dữ liệu Java độc lập, dùng `toArray` hoặc copy sang mảng đã có; `asSlice`/`ofArray` không phải copy.
9. Đóng `Arena` đúng lúc, không để segment sống giả sau khi memory đã invalid; hạn chế mang confined segment qua thread.
10. Với dữ liệu lớn, thiết kế **chunking**; tránh cấp phát mảng khổng lồ và copy dư.
11. Với memory chia sẻ, có chiến lược đồng bộ riêng; copy/fill/mismatch không tự là atomic transaction.
12. Test kết quả, boundary cases, endian và lỗi scope/thread/read-only, thay vì chỉ benchmark happy path.

## Nguồn chính thức

- [Java SE 22 — `MemorySegment` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `copy`, `copyFrom`, `fill`, `mismatch`, `toArray`, `ofArray`, `asSlice` và các điều kiện lỗi.
- [Java SE 22 — `Arena` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát native memory, phạm vi sống và confined/shared arena.
- [Java SE 22 — `ValueLayout` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): primitive carriers, byteSize, byteOrder và alignment.
- [Oracle — Foreign Function & Memory API Guide (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): thực hành FFM, heap/native segments và memory arenas.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API FFM được chuẩn hóa trong JDK 22.