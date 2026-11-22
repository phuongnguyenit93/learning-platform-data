# MemorySegment: giới hạn chỉ đọc, truy cập ngoài phạm vi và sai căn chỉnh

## Mục tiêu học tập

`MemorySegment` trong Foreign Function & Memory API (FFM) của Java biểu diễn **một vùng bộ nhớ liên tiếp có kích thước xác định**. Khi truy cập vùng này, JVM kiểm tra nhiều điều kiện mà con trỏ C thuần thường không tự kiểm tra: vùng nhớ có còn hợp lệ không, thread hiện tại có quyền truy cập không, thao tác có nằm trong giới hạn segment không, layout có đáp ứng yêu cầu căn chỉnh không và **thao tác ghi có bị cấm vì segment chỉ đọc không**.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của `byteSize()`, `isReadOnly()` và `asReadOnly()`.
- Tính đúng phạm vi hợp lệ cho `get`/`set` theo **byte offset** và kích thước `ValueLayout`.
- Phân biệt lỗi `IndexOutOfBoundsException`, `IllegalArgumentException` (trong đó có read-only và misalignment), `IllegalStateException` (scope đã hết) và `WrongThreadException` (sai thread).
- Hiểu tại sao một slice có offset bằng 0 vẫn có thể **misaligned**, và khi nào `JAVA_INT_UNALIGNED` có ích.
- Thiết kế parser/bridge native có kiểm tra giới hạn mà không giả định `asReadOnly()` tạo ra một bản sao dữ liệu hay đóng băng bộ nhớ vật lý.

**Phiên bản:** Nội dung và chương trình biên dịch dựa trên `java.lang.foreign` **API chuẩn từ JDK 22 trở lên** (JEP 454), đã được kiểm tra trên JDK 24. **JDK 17** có API FFM ở giai đoạn incubator với tên package và chữ ký khác, nên các ví dụ dưới đây **không** được quảng bá là chạy trực tiếp trên JDK 17. Các ví dụ chỉ dùng memory access; không yêu cầu liên kết native C hay gọi downcall.

## 1. Mental model: một segment là một "cửa sổ" có hợp đồng truy cập

Một vùng native memory được `Arena` cấp có thể gồm nhiều byte, nhưng một `MemorySegment` chỉ cho phép thao tác trên **khoảng byte mà chính segment mô tả**.

~~~text
Arena.allocate(16, 8) -> segment 16 byte, địa chỉ đầu được căn chỉnh 8 byte

byte offset       0  1  2  3 | 4  5  6  7 | 8  9 10 11 |12 13 14 15
                  <-------------- toàn bộ segment: byteSize() = 16 ------------>
JAVA_INT ở 0      [  4 byte  ]
JAVA_INT ở 12                                           [  4 byte  ]
JAVA_BYTE ở 16                                                       X quá biên
JAVA_INT ở 1         [  4 byte  ]   nằm trong vùng nhưng sai alignment 4
~~~

Một access hợp lệ phải **đồng thời** thỏa các điều kiện:

1. **Scope còn sống:** arena/scope gắn với segment vẫn còn hiệu lực.
2. **Thread được phép:** với confined arena, chỉ owner thread được truy cập.
3. **Vùng byte hợp lệ:** không đọc/ghi trước byte đầu hoặc vượt qua cuối segment.
4. **Căn chỉnh hợp lệ:** địa chỉ bắt đầu access đáp ứng `layout.byteAlignment()`.
5. **Quyền ghi hợp lệ:** với `set`, `fill`, copy-to và các thao tác sửa dữ liệu, destination không được là read-only segment.

`get` là đọc dữ liệu nên không yêu cầu segment writable, nhưng vẫn kiểm tra scope, thread, bounds và alignment. `set` phải thỏa thêm điều kiện writable. Không có bước kiểm tra nào mang ý nghĩa “segment được đọc thì mọi offset đều hợp lệ”.

## 2. Các thuộc tính và API cốt lõi

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(16, 8);
    System.out.println(data.byteSize());         // 16
    System.out.println(data.isReadOnly());       // false

    MemorySegment view = data.asReadOnly();
    System.out.println(view.byteSize());         // 16
    System.out.println(view.isReadOnly());       // true
}
~~~

Đây là **đoạn code ở trong phương thức Java**, không phải file Java độc lập: để chạy một tệp, đặt trong `main` hoặc tham khảo ví dụ đầy đủ ở mục 8.

| API | Tác dụng | Điểm cần nhớ |
| --- | --- | --- |
| `byteSize()` | Tổng số byte của vùng mà segment hiện tại mô tả | Đây là kích thước của **view**, không nhất thiết toàn bộ allocation gốc |
| `isReadOnly()` | Cho biết segment có chặn các thao tác ghi FFM không | Không chứng minh dữ liệu vật lý không thể thay đổi qua alias khác |
| `asReadOnly()` | Trả một **view chỉ đọc** của cùng vùng nhớ | Không copy dữ liệu; writable alias ban đầu vẫn có thể sửa |
| `asSlice(offset, size)` | Tạo segment con có bounds tương đối nhỏ hơn | Dùng byte offset, không tự cấp vùng nhớ mới |
| `get(layout, offset)` | Đọc giá trị kiểu layout tại byte offset | Kiểm bounds và căn chỉnh |
| `set(layout, offset, value)` | Ghi giá trị kiểu layout tại byte offset | Kiểm cả read-only, bounds và căn chỉnh |
| `ValueLayout.JAVA_INT` | Layout int 4 byte, alignment 4, byte order native | Không phù hợp địa chỉ bị lệch 1, 2, 3 byte |
| `ValueLayout.JAVA_INT_UNALIGNED` | Layout int 4 byte, alignment 1 | Vẫn phải có đủ 4 byte, và vẫn tôn trọng read-only |
| `Arena.ofConfined()` | Quản lý lifetime của native allocation trên một thread | Access sau `close()` hoặc từ thread không phù hợp sẽ lỗi |

Hai kiểu segment thường gặp: **heap segment** được tạo qua `MemorySegment.ofArray(...)` trỏ tới phần tử của mảng Java; **native segment** được cấp bởi `Arena` ngoài heap hoặc từ cơ chế khác như memory mapping. Các quy tắc về segment bounds/read-only vẫn áp dụng cho cả hai, nhưng nguồn memory và lifetime có đặc điểm khác nhau.

## 3. Read-only: `asReadOnly()` cấm những gì?

Gọi `asReadOnly()` tạo một view mà các thao tác ghi thông qua **view này** không được phép. `isReadOnly()` giúp kiểm tra thuộc tính đó trước khi chọn nhánh xử lý, nhưng JVM vẫn thực thi kiểm tra khi ghi.

~~~java
MemorySegment writable = MemorySegment.ofArray(new byte[] {10, 20, 30});
MemorySegment readOnly = writable.asReadOnly();

byte before = readOnly.get(ValueLayout.JAVA_BYTE, 0); // đọc được: 10
writable.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);
byte after = readOnly.get(ValueLayout.JAVA_BYTE, 0);  // đọc được: 99

// Dòng dưới gây IllegalArgumentException với API MemorySegment.set:
// readOnly.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);
~~~

Đây là đoạn minh họa rút gọn. **Read-only không đồng nghĩa immutable snapshot**: `readOnly` và `writable` cùng nhìn vào dữ liệu gốc. Việc thay đổi qua writable alias, qua mảng backing Java, hoặc qua một native pointer được cấp phép khác có thể hiển thị trong read-only view.

### Mức bảo vệ cần phân biệt

- `readOnly.get(layout, offset)`: **được phép** nếu các điều kiện truy cập khác hợp lệ.
- `readOnly.set(layout, offset, value)`: **không được phép**, theo `MemorySegment.set` sẽ ném **`IllegalArgumentException`** khi read-only.
- `readOnly.fill(value)`, `readOnly.copyFrom(source)` và các API ghi khác: read-only destination cũng bị từ chối; không dùng read-only view làm đích mutable.
- `readOnly.asSlice(...).isReadOnly()`: vẫn **true** vì slice được tạo từ view read-only.
- `writable.asReadOnly()` **không** chuyển `writable` ban đầu thành chỉ đọc; các view khác được tạo từ `writable` vẫn có thể writable.

Khi chia sẻ read-only view làm API contract, hãy chắc chắn rằng **không có writer khác** nếu yêu cầu thật sự là dữ liệu không thay đổi trong thời gian đọc. Read-only view không tự khóa đồng thời hoặc tạo transaction snapshot.

### Read-only `MemorySegment` khác read-only `ByteBuffer` về exception

Nếu gọi `readOnly.asByteBuffer()` rồi ghi qua `ByteBuffer.put(...)`, API `ByteBuffer` có thể báo **`java.nio.ReadOnlyBufferException`** theo hợp đồng NIO. Còn `MemorySegment.set(...)` trên chính read-only segment báo **`IllegalArgumentException`** theo hợp đồng FFM. Đừng bắt mọi lỗi read-only bằng một exception class cố định khi đang dùng hai loại API khác nhau.

## 4. Bounds: offset là byte, và toàn bộ giá trị phải nằm gọn trong segment

Giả sử `segment.byteSize() == 16` và bạn truy cập một `ValueLayout.JAVA_INT` có `byteSize() == 4`. Điều kiện bounds là:

~~~text
offset >= 0
offset + 4 <= 16
    tương đương, khi tránh overflow:
offset <= 16 - 4

offset 0: 4 byte ở [0,4)  -> OK, nếu alignment đúng
offset 12: 4 byte ở [12,16) -> OK, nếu alignment đúng
offset 13: 4 byte ở [13,17) -> quá giới hạn
offset 16: 1 byte ở [16,17) -> quá giới hạn
offset -1: bắt đầu trước vùng -> quá giới hạn
~~~

Điểm kết thúc tính theo **end-exclusive**: đọc bốn byte tại offset 12 dùng các byte 12, 13, 14 và 15. Byte offset 16 là **vị trí sau cùng**, không phải byte có thể đọc.

Một pattern kiểm tra trước truy cập:

~~~java
static boolean fits(MemorySegment segment, long offset, long accessBytes) {
    return offset >= 0
            && accessBytes >= 0
            && accessBytes <= segment.byteSize()
            && offset <= segment.byteSize() - accessBytes;
}
~~~

Hàm helper này trả false nếu không đủ byte và tránh biểu thức `offset + accessBytes` có thể bị tràn số. Nhưng **`fits` chỉ kiểm tra bounds**: nó không tự đảm bảo layout alignment, scope/thread hay quyền ghi. Code sản xuất vẫn nên để API FFM thực hiện kiểm tra cuối cùng, vì điều kiện có thể thay đổi nếu scope đóng hoặc thao tác diễn ra qua thread khác.

Với `MemorySegment.get(ValueLayout.JAVA_INT, offset)`, truy cập vượt bounds ném **`IndexOutOfBoundsException`**. Với `getAtIndex`, tham số `index` là **chỉ số phần tử**, được nhân với layout byte size; khác hẳn byte offset:

~~~java
// Với segment có 16 byte, alignment phù hợp:
segment.get(ValueLayout.JAVA_INT, 12);        // byte offset 12
segment.getAtIndex(ValueLayout.JAVA_INT, 3);  // index 3 -> byte offset 12

// Index 4 -> byte offset 16 và cần 4 byte -> quá biên.
// segment.getAtIndex(ValueLayout.JAVA_INT, 4);
~~~

Đây là snippet, giả định `segment` tồn tại và có đủ alignment. Nếu index multiplication bị overflow hoặc phần tử nằm ngoài segment, `getAtIndex` cũng có thể ném `IndexOutOfBoundsException`.

### Một empty slice ở cuối vẫn có thể hợp lệ

`segment.asSlice(segment.byteSize(), 0)` biểu diễn vùng 0 byte ngay cuối segment và có thể được tạo hợp lệ. Nhưng **không có byte nào để đọc từ đó**. Ngược lại, `segment.asSlice(15, 2)` trên segment 16 byte phải bị từ chối vì slice đòi tới byte 16 (17 byte theo end-exclusive).

Đừng nhầm việc có thể tạo view kích thước 0 với quyền truy cập vào byte offset bằng chính `byteSize()`.

## 5. Alignment: vùng đủ rộng vẫn có thể không được đọc bằng layout mong muốn

**Căn chỉnh (alignment)** yêu cầu địa chỉ bắt đầu của một access phù hợp một ranh giới byte. `ValueLayout.JAVA_INT` có size 4 và alignment 4, `ValueLayout.JAVA_LONG` có size 8 và alignment 8. `ValueLayout.JAVA_BYTE` có size 1 và alignment 1.

Trên native segment được tạo bằng:

~~~java
MemorySegment segment = arena.allocate(16, 8);
~~~

`arena` là một `Arena` đang sống. Tham số thứ hai `8` yêu cầu byte alignment 8 cho địa chỉ **bắt đầu allocation**. Khi byte offset 0 đã aligned 8, offset 4 aligned 4, còn offset 1 không aligned 4.

~~~text
Địa chỉ gốc A: A % 8 == 0

A + 0: phù hợp JAVA_INT (4-byte alignment)
A + 4: phù hợp JAVA_INT
A + 8: phù hợp JAVA_INT
A + 1: KHÔNG phù hợp JAVA_INT
A + 1: phù hợp JAVA_BYTE
~~~

Nếu gọi:

~~~java
segment.get(ValueLayout.JAVA_INT, 1);
~~~

khi `segment` là native segment 16 byte nói trên, dữ liệu ở offset 1..4 **không vượt bounds** nhưng **vi phạm căn chỉnh**. FFM ném **`IllegalArgumentException`** vì access không tương thích `layout.byteAlignment()`.

### Layout UNALIGNED: thay đổi một ràng buộc, không bỏ mọi ràng buộc

~~~java
int value = segment.get(ValueLayout.JAVA_INT_UNALIGNED, 1);
~~~

`JAVA_INT_UNALIGNED` vẫn đọc **4 byte** nhưng alignment chỉ còn **1**. Vì vậy byte offset 1 có thể được đọc bằng layout này trong phạm vi segment hợp lệ. Tuy nhiên:

- `get(JAVA_INT_UNALIGNED, 13)` trên segment 16 byte vẫn bị bounds check chặn vì cần đến byte offset 16.
- `set(JAVA_INT_UNALIGNED, ..., ...)` trên **read-only** segment vẫn bị từ chối.
- Scope đã đóng hoặc thread không được phép vẫn gây lỗi dù layout cho phép unaligned.
- Unaligned access có thể có chi phí hiệu năng hoặc vấn đề portability; không nên chọn layout này mặc định để che lỗi cấu trúc dữ liệu.

Các hằng `JAVA_SHORT_UNALIGNED`, `JAVA_CHAR_UNALIGNED`, `JAVA_LONG_UNALIGNED`, `JAVA_FLOAT_UNALIGNED` và `JAVA_DOUBLE_UNALIGNED` cũng có mặt khi định dạng thực sự yêu cầu đọc tại byte offsets không aligned.

### Endianness khác alignment

`layout.order()` quy định thứ tự byte (big-endian/little-endian) khi giải mã số nhiều byte. Nó **không** làm một địa chỉ lệch trở nên aligned. Ví dụ:

~~~java
import java.nio.ByteOrder;

var bigEndianInt = ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
// bigEndianInt vẫn có byteAlignment() == 4.
~~~

Muốn vừa yêu cầu unaligned vừa chỉ định byte order, có thể dùng `ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN)` khi hợp đồng binary format yêu cầu. Chọn byte order theo **giao thức dữ liệu**; không tự dùng native order nếu file/network format đã định nghĩa thứ tự byte khác.

## 6. Slice và offset 0: "đầu view" chưa chắc aligned

Một slice là **view trên cùng bộ nhớ** và có **bounds riêng**. Offset khi gọi `slice.get(layout, 0)` là offset 0 **tương đối với slice**, không phải offset 0 của allocation gốc.

~~~java
MemorySegment base = arena.allocate(16, 8);
MemorySegment shifted = base.asSlice(1, 4);

shifted.get(ValueLayout.JAVA_BYTE, 0); // OK, byte alignment 1

// Sai: địa chỉ của shifted là base-address + 1; JAVA_INT cần alignment 4.
// shifted.get(ValueLayout.JAVA_INT, 0);

// Đúng khi định dạng yêu cầu unaligned:
// shifted.get(ValueLayout.JAVA_INT_UNALIGNED, 0);
~~~

Đây là snippet cần một `Arena arena` hợp lệ; không thể chạy độc lập dưới dạng tệp. Bằng cách dùng `JAVA_INT_UNALIGNED`, bạn chấp nhận giải mã int từ bốn byte bắt đầu ở địa chỉ lệch. **Không sửa được lỗi alignment bằng cách đổi biến offset về 0 trên một view đã bị lệch**.

Một slice cũng làm **nhỏ phạm vi truy cập**: nếu `shifted.byteSize() == 4`, việc `shifted.get(JAVA_BYTE, 4)` vẫn là out of bounds dù `base` còn rất nhiều byte phía sau. JVM kiểm tra theo **đối tượng segment dùng trong lời gọi**, không tự nới ra tới allocation gốc.

### Read-only được lan truyền qua slice

~~~java
MemorySegment ro = base.asReadOnly();
MemorySegment child = ro.asSlice(4, 4);

System.out.println(ro.isReadOnly());    // true
System.out.println(child.isReadOnly()); // true
~~~

Nếu bạn muốn view read-only của một phần bộ nhớ, có thể tạo slice rồi `asReadOnly()`. Tính read-only được giữ qua việc tạo slice từ view đã read-only. Nhưng điều này vẫn là **quyền của view**, không phải thay đổi quyền ghi của mọi alias.

## 7. Bảng lỗi: cùng ngoại lệ không nhất thiết cùng nguyên nhân

| Điều kiện vi phạm | API điển hình | Exception thường được đặc tả | Cách kiểm tra và sửa |
| --- | --- | --- | --- |
| Ghi vào `asReadOnly()` view | `set(JAVA_INT, 0, ...)` | `IllegalArgumentException` | Xác định `isReadOnly()`; chọn writable destination đúng ownership |
| Access không thỏa layout alignment | `get(JAVA_INT, 1)` trên aligned base | `IllegalArgumentException` | Sửa offset/layout hoặc dùng `JAVA_INT_UNALIGNED` có chủ đích |
| Truy cập ngoài segment | `get(JAVA_BYTE, byteSize())` | `IndexOutOfBoundsException` | Kiểm bounds bằng byte offset và access size |
| Tạo slice vượt giới hạn | `asSlice(15, 2)` trên segment 16 byte | `IndexOutOfBoundsException` | Bảo đảm offset và newSize nằm trong parent |
| Arena đã đóng | `get` sau `arena.close()` | `IllegalStateException` | Không dùng segment sau khi scope hết hiệu lực |
| Confined segment từ thread khác | `get` từ worker thread | `WrongThreadException` | Dùng owner thread hoặc chính sách Arena thích hợp |
| Ghi qua NIO buffer read-only | `asByteBuffer().put(...)` | `ReadOnlyBufferException` | Phân biệt exception NIO với FFM; dùng writable view |
| `getAtIndex` có index overflow/vượt số phần tử | `getAtIndex(JAVA_INT, 4)` trên 16 byte | `IndexOutOfBoundsException` | Kiểm logical index và số phần tử theo layout |

**Không giả định một thứ tự ưu tiên exception khi cùng một thao tác vi phạm nhiều điều kiện.** Ví dụ đọc `JAVA_INT` tại offset 13 trên segment 16 byte có thể vừa sai bounds (cần 4 byte) vừa misaligned. Để kiểm thử rõ ràng, hãy tạo ca **chỉ sai một điều kiện tại một thời điểm**. Cũng không nên bắt mọi `IllegalArgumentException` rồi luôn kết luận “read-only”, bởi sai alignment có thể có cùng class.

## 8. Chương trình Java 22+ đầy đủ, có thể biên dịch và chạy

Ví dụ này làm rõ sáu hành vi: read-only; out-of-bounds; misalignment; layout unaligned; alias nhìn cùng dữ liệu; và scope hết hạn.

Tạo tệp `SegmentSafetyDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class SegmentSafetyDemo {
    private static void expect(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected.getSimpleName());
        } catch (RuntimeException actual) {
            if (!expected.isInstance(actual)) {
                throw new AssertionError("Unexpected exception", actual);
            }
            System.out.println(label + "=" + actual.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        MemorySegment[] afterClose = new MemorySegment[1];

        try (Arena arena = Arena.ofConfined()) {
            // Địa chỉ gốc được căn chỉnh 8, size = 16 byte.
            MemorySegment writable = arena.allocate(16, 8);
            afterClose[0] = writable;

            writable.set(ValueLayout.JAVA_INT, 0, 100);
            writable.set(ValueLayout.JAVA_INT, 12, 500);
            MemorySegment readOnly = writable.asReadOnly();

            System.out.println("size=" + writable.byteSize());
            System.out.println("readOnly=" + readOnly.isReadOnly());
            System.out.println("first=" + readOnly.get(ValueLayout.JAVA_INT, 0));

            expect("write", IllegalArgumentException.class,
                    () -> readOnly.set(ValueLayout.JAVA_INT, 0, 300));

            // Offset 16 không chứa byte hợp lệ nào.
            expect("bounds", IndexOutOfBoundsException.class,
                    () -> writable.get(ValueLayout.JAVA_BYTE, 16));

            // Offset 1 còn nằm trong 16 byte nhưng lệch alignment 4.
            expect("alignment", IllegalArgumentException.class,
                    () -> writable.get(ValueLayout.JAVA_INT, 1));

            // Layout UNALIGNED cho phép đọc bốn byte tại offset 1.
            writable.get(ValueLayout.JAVA_INT_UNALIGNED, 1);
            System.out.println("unalignedAllowed=true");

            MemorySegment slice = readOnly.asSlice(0, 4);
            System.out.println("sliceReadOnly=" + slice.isReadOnly());

            expect("sliceBounds", IndexOutOfBoundsException.class,
                    () -> writable.asSlice(15, 2));
            System.out.println("emptyEnd=" + writable.asSlice(16, 0).byteSize());

            // View read-only thấy thay đổi từ writable alias.
            writable.set(ValueLayout.JAVA_INT, 0, 200);
            System.out.println("updatedView="
                    + readOnly.get(ValueLayout.JAVA_INT, 0));
        }

        // Arena đã được đóng bởi try-with-resources.
        expect("closed", IllegalStateException.class,
                () -> afterClose[0].get(ValueLayout.JAVA_BYTE, 0));
    }
}
~~~

Biên dịch và chạy bằng **JDK 22+** (không dùng `--enable-preview` cho API chuẩn):

~~~bash
javac -encoding UTF-8 SegmentSafetyDemo.java
java SegmentSafetyDemo
~~~

Stdout kỳ vọng:

~~~text
size=16
readOnly=true
first=100
write=IllegalArgumentException
bounds=IndexOutOfBoundsException
alignment=IllegalArgumentException
unalignedAllowed=true
sliceReadOnly=true
sliceBounds=IndexOutOfBoundsException
emptyEnd=0
updatedView=200
closed=IllegalStateException
~~~

Giải thích từng trường hợp:

1. `arena.allocate(16, 8)` tạo segment đủ 16 byte với base alignment 8.
2. `readOnly.get(JAVA_INT, 0)` hợp lệ, trả 100.
3. Ghi qua `readOnly` tạo `IllegalArgumentException` do read-only.
4. Đọc một byte ở offset 16 bị `IndexOutOfBoundsException` vì byte cuối hợp lệ là 15.
5. Đọc int ở offset 1 sai căn chỉnh nhưng vẫn nằm trong bounds nên ném `IllegalArgumentException`.
6. `JAVA_INT_UNALIGNED` chấp nhận offset 1; kết quả integer không được in vì nó phụ thuộc nội dung byte và byte order, không cần dùng để chứng minh quyền truy cập.
7. Slice từ `readOnly` vẫn read-only; slice 15,2 vượt bounds; slice 16,0 là view rỗng hợp lệ.
8. Khi cập nhật giá trị qua writable segment, read-only view thấy 200 — chứng tỏ view chia sẻ backing memory.
9. Sau khi `Arena.ofConfined()` được đóng, access tiếp theo bị `IllegalStateException`. Không cố đọc lại vùng native đã được giải phóng bằng pointer C.

**Đây là output của chương trình khi chạy bình thường.** Nếu chạy với JDK 17 (không có API chuẩn tương ứng) sẽ lỗi biên dịch; cần dùng JDK 22+.

## 9. Sai thread: lỗi khác với read-only/bounds/alignment

`Arena.ofConfined()` giới hạn quyền truy cập các native segments do nó quản lý vào thread sở hữu arena. Một thread khác đọc byte offset 0 dù trong phạm vi và aligned vẫn không được phép.

Tạo `ConfinedThreadDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicReference;

public final class ConfinedThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(1);
            AtomicReference<String> error = new AtomicReference<>("none");

            Thread worker = new Thread(() -> {
                try {
                    segment.get(ValueLayout.JAVA_BYTE, 0);
                } catch (RuntimeException ex) {
                    error.set(ex.getClass().getSimpleName());
                }
            });

            worker.start();
            worker.join();
            System.out.println("otherThread=" + error.get());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ConfinedThreadDemo.java
java ConfinedThreadDemo
~~~

Stdout:

~~~text
otherThread=WrongThreadException
~~~

Đây là **lỗi quyền truy cập theo thread**, không phải lỗi read-only hay misalignment. Nếu muốn chia sẻ native segment giữa threads, cân nhắc `Arena.ofShared()` cùng cơ chế đồng bộ ứng dụng phù hợp; shared arena cho phép sử dụng nhiều thread nhưng **không tự làm mọi thao tác ghi đồng thời trở nên an toàn**.

Lưu ý thứ tự: `worker.join()` trước khi arena đóng giúp phân biệt rõ lỗi wrong thread; nếu vừa đóng scope vừa truy cập từ thread sai, có nhiều điều kiện vi phạm và không nên dựa vào class exception được ưu tiên.

## 10. Quy tắc kiểm tra trước khi xử lý dữ liệu không tin cậy

Giả sử bạn đọc một cấu trúc binary đến từ file hoặc native library:

~~~text
header: 4 byte int
payloadLength: 4 byte int
payload: payloadLength byte
~~~

Các điều cần kiểm tra **trước khi đọc**:

- Segment có ít nhất 8 byte để đọc hai số nguyên ở các offset 0 và 4 không?
- Offset và kích thước được tính theo **byte** hay số phần tử?
- Field nào cần aligned access? Nếu file có fields packed không aligned, layout có cần `*_UNALIGNED` không?
- Số nguyên độ dài có thể âm hoặc rất lớn không? Có bị tràn khi cộng với header không?
- Segment là read-only hay writable? Parser chỉ cần đọc, không được yêu cầu `set` vào view đã bị cấm ghi.
- Arena/scope và quyền thread còn hợp lệ trong toàn bộ quá trình xử lý không?

Một helper đơn giản kiểm tra bounds trước truy cập:

~~~java
static void requireRange(MemorySegment segment,
                         long offset,
                         long length) {
    long size = segment.byteSize();

    if (offset < 0 || length < 0
            || length > size
            || offset > size - length) {
        throw new IllegalArgumentException("Invalid byte range");
    }
}
~~~

**Lưu ý về exception:** helper tự viết này cố ý ném `IllegalArgumentException` để phản ánh dữ liệu đầu vào của ứng dụng không hợp lệ. Nếu gọi trực tiếp `MemorySegment.get/set` sai bounds, FFM ném **`IndexOutOfBoundsException`**. Không dùng loại exception từ helper để khẳng định FFM sẽ ném cùng loại.

Tránh:

~~~java
// Sai khi offset + length có thể tràn long:
// if (offset + length <= segment.byteSize()) ...

// Sai khi nhầm length theo số byte với số int:
// segment.getAtIndex(ValueLayout.JAVA_INT, byteOffset);

// Sai khi coi unaligned layout bỏ qua bounds:
// segment.get(ValueLayout.JAVA_INT_UNALIGNED, segment.byteSize());
~~~

Đối với binary format có byte order được quy định, chọn `ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` hoặc `JAVA_INT_UNALIGNED.withOrder(...)` tùy cả căn chỉnh và thứ tự byte. Byte order chỉ quyết định cách diễn giải bytes, không mở rộng bounds hoặc quyền ghi.

## 11. Read-only view có phải lớp bảo vệ tuyệt đối cho native memory?

**Không.** `MemorySegment.asReadOnly()` thực thi quy tắc read-only **khi truy cập thông qua view đó bằng API FFM**. Nó không biến backing allocation thành bất biến toàn cục.

Ví dụ với heap-backed segment:

~~~java
byte[] backing = {1, 2, 3};
MemorySegment ro = MemorySegment.ofArray(backing).asReadOnly();

System.out.println(ro.get(ValueLayout.JAVA_BYTE, 0)); // 1
backing[0] = 7;
System.out.println(ro.get(ValueLayout.JAVA_BYTE, 0)); // 7
~~~

Các đường cập nhật hợp lệ khác vào cùng dữ liệu có thể thay đổi giá trị mà view chỉ đọc quan sát được. Do đó:

- Nếu API yêu cầu **snapshot không đổi**, cần copy nội dung sang storage riêng do caller quản lý và kiểm soát mọi đường ghi; chỉ `asReadOnly()` không đủ.
- Nếu API yêu cầu **tránh sửa nhầm qua một handle**, read-only view là cơ chế tốt vì FFM sẽ từ chối thao tác ghi qua handle đó.
- Nếu native code đã có con trỏ C tới cùng allocation, read-only FFM wrapper không tự ràng buộc mọi truy cập C.
- Nếu dữ liệu được chia sẻ đa luồng, vẫn cần chính sách memory visibility và synchronization; `isReadOnly()` không thay cho synchronization.

Đặc biệt với native pointer và các phương thức nguy hiểm có thể reinterpret kích thước hoặc lifetime vùng nhớ, đừng vô hiệu hóa các ràng buộc FFM bằng cách tin tưởng con trỏ/length không được xác thực. Tính memory safety của access FFM dựa trên **segment mô tả đúng vùng nhớ được cấp và thời gian sống**.

## 12. Những bẫy thường gặp khi sửa lỗi

| Triệu chứng | Chẩn đoán khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `set` ném `IllegalArgumentException` tại offset 0 | View có thể là read-only, hoặc layout căn chỉnh không đúng | Kiểm `isReadOnly()`, `byteAlignment()`, base/slice offset |
| `get(JAVA_INT, 1)` lỗi trên segment 16 byte | Không phải thiếu bytes; layout yêu cầu alignment 4 | Dùng offset aligned hoặc layout unaligned **nếu format cho phép** |
| `get(JAVA_INT_UNALIGNED, 13)` vẫn lỗi | 13 + 4 vượt byteSize 16 | Kiểm vùng đủ lớn; unaligned không vô hiệu hóa bounds |
| `asSlice(1, 4).get(JAVA_INT, 0)` lỗi | Đầu slice ở địa chỉ base + 1, không aligned 4 | Cân nhắc slice aligned hoặc `JAVA_INT_UNALIGNED` |
| `readOnly.asSlice(...).set(...)` lỗi | Slice kế thừa read-only | Muốn ghi, cần writable alias/đích riêng hợp lệ |
| `asSlice(16, 0)` tạo được nhưng `get` thất bại | Zero-length view không có byte để đọc | Bỏ qua read khi kích thước 0 |
| `getAtIndex(JAVA_INT, 3)` hợp lệ nhưng 4 lỗi | Index 3 là byte offset 12, index 4 là 16 | Tính index theo số phần tử; giới hạn 0..3 |
| Đọc sau `arena.close()` lỗi | Scope đã hết hiệu lực | Không dùng segment/pointer sau close |
| Đọc từ thread khác lỗi dù byte offset 0 | Confined arena ràng buộc owner thread | Dùng thread sở hữu hoặc shared arena |
| Đọc qua view read-only thấy dữ liệu đổi | Một alias khác đã sửa backing memory | Copy để lấy snapshot nếu cần |
| `ByteBuffer.put` và `MemorySegment.set` ném exception khác nhau | API khác nhau quy định exceptions khác nhau | Phân biệt `ReadOnlyBufferException` (NIO) và `IllegalArgumentException` (FFM) |

**Không chữa mọi lỗi bằng `JAVA_INT_UNALIGNED`.** Làm thế chỉ giảm yêu cầu căn chỉnh; nếu lỗi gốc là out-of-bounds, read-only, expired scope hay sai thread, nó vẫn xảy ra. Ngoài ra, unaligned access có thể kém tối ưu và không phù hợp giả định của native struct/ABI.

## 13. Bài tự kiểm tra

**Câu 1.** Một segment dài 16 byte, `get(JAVA_INT, 12)` có hợp lệ không? Còn `get(JAVA_INT, 13)`?

Đáp án: offset 12 đọc byte 12..15, **nằm trong bounds**; chỉ thực hiện được nếu alignment cũng phù hợp. Offset 13 cần byte 13..16 nên **vượt bounds**. Nếu cùng lúc sai alignment, đừng xây code phụ thuộc thứ tự kiểm tra exception.

**Câu 2.** `asReadOnly()` có copy bộ nhớ gốc hoặc chặn mọi alias khác ghi không?

Đáp án: không; nó tạo một **read-only view** trên cùng backing memory. Những alias còn writable vẫn có thể thay đổi dữ liệu.

**Câu 3.** `MemorySegment.set` trên một read-only segment ném `ReadOnlyBufferException` hay `IllegalArgumentException`?

Đáp án: với API `MemorySegment.set` trong JDK 22+, **`IllegalArgumentException`**. `ReadOnlyBufferException` thuộc đường ghi qua read-only `java.nio.ByteBuffer`.

**Câu 4.** Sau `base.asSlice(1, 4)`, gọi `slice.get(JAVA_INT, 0)` có chắc aligned?

Đáp án: không; địa chỉ của slice bắt đầu tại `base.address + 1`. Nếu base aligned 8 byte, slice bắt đầu lệch 1 byte, không thỏa `JAVA_INT` alignment 4. Offset 0 chỉ tương đối với slice.

**Câu 5.** `JAVA_INT_UNALIGNED` có cho phép đọc bốn byte từ offset 15 trong segment 16 byte không?

Đáp án: không, vì chỉ còn một byte. Unaligned layout vẫn yêu cầu **đủ 4 byte** và mọi quyền truy cập khác.

**Câu 6.** `getAtIndex(JAVA_INT, 2)` trên segment 16 byte dùng những bytes nào?

Đáp án: index 2 ứng với byte offset `2 * 4 = 8`, đọc bytes 8, 9, 10, 11 khi aligned.

**Câu 7.** Khi `Arena.ofConfined()` đóng, `asReadOnly()` view có còn được đọc vì chỉ read không?

Đáp án: không. Scope của backing memory đã hết; truy cập qua view vẫn bị `IllegalStateException`. Read-only không kéo dài lifetime arena.

**Câu 8.** Nếu muốn nhiều thread đọc một native segment, chỉ cần gọi `asReadOnly()` trên confined segment có đủ không?

Đáp án: không. Read-only điều khiển quyền ghi, **không** xóa quy tắc thread confinement. Cần chọn lifetime/thread ownership đúng, ví dụ shared arena, và giải quyết đồng bộ nếu có writers.

**Câu 9.** Vì sao kiểm tra `offset >= 0 && offset + size <= byteSize` có thể chưa an toàn khi xử lý input không tin cậy?

Đáp án: `offset + size` có thể tràn `long`. Dùng kiểm tra các đại lượng không âm, `size <= byteSize` và `offset <= byteSize - size` để tránh overflow khi tính giới hạn.

## Checklist review code MemorySegment

- [ ] Dùng JDK 22+ cho API chuẩn `java.lang.foreign`, không dùng nhầm package incubator cũ.
- [ ] Đã biết `byteSize()` của **segment/view thực sự truy cập**, không tự lấy kích thước allocation gốc?
- [ ] Mọi `get/set` dùng byte offset; `getAtIndex/setAtIndex` dùng element index đúng layout?
- [ ] Đã kiểm bounds trên **toàn bộ giá trị cần đọc/ghi**, không chỉ offset bắt đầu?
- [ ] Đã xác nhận layout alignment và offset của **slice** theo địa chỉ thực của view?
- [ ] Nếu dùng `*_UNALIGNED`, có yêu cầu từ binary format và hiểu giới hạn portability/hiệu năng?
- [ ] Đã phân biệt byte order của dữ liệu với alignment và kích thước?
- [ ] Với API ghi, `segment.isReadOnly()` được xét, và không dùng read-only destination?
- [ ] Không hiểu `asReadOnly()` như snapshot/copy hoặc bảo vệ khỏi mọi writer khác?
- [ ] Arena scope còn sống và thread đang gọi được phép truy cập?
- [ ] Đã xử lý đúng `IllegalArgumentException`, `IndexOutOfBoundsException`, `IllegalStateException` và `WrongThreadException` mà không đoán từ một lỗi có thể nhiều nguyên nhân?
- [ ] Kiểm thử offset âm, vị trí cuối, slice zero-length, dữ liệu packed, misalignment, writable alias, closed scope và cross-thread?

## Tài liệu chính thức

1. [Java SE 22 — MemorySegment API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `asReadOnly`, `isReadOnly`, `byteSize`, `asSlice`, `get`/`set` và các điều kiện lỗi.
2. [Java SE 22 — ValueLayout API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): kích thước, byte alignment, byte order, các layout `JAVA_*_UNALIGNED`.
3. [Java SE 22 — Arena API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát native memory, scoped lifetime, confined/shared arenas.
4. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM trở thành API chuẩn trong JDK 22.
5. [Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): đối chiếu cách mô tả lỗi và quyền truy cập trên JDK chạy ví dụ.

**Ghi nhớ:** Một memory access hợp lệ đòi hỏi **đúng bounds, alignment, scope, thread và quyền ghi**. `asReadOnly()` chỉ ràng buộc thao tác ghi qua view; `JAVA_INT_UNALIGNED` chỉ nới ràng buộc alignment; còn `byteSize()` luôn là biên giới của chính segment bạn đang sử dụng.
