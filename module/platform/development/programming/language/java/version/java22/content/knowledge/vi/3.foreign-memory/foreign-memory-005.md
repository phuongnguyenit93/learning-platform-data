# Đọc ghi dữ liệu bằng ValueLayout với kiểu dữ liệu, byte order và căn chỉnh

Foreign Function & Memory API (FFM) chính thức từ Java 22 cung cấp cách đọc và ghi dữ liệu trong một vùng nhớ thông qua `MemorySegment` và `ValueLayout`. `MemorySegment` đại diện cho vùng nhớ; `ValueLayout` mô tả cách diễn giải một phần vùng nhớ thành giá trị Java như `int`, `long`, `float` hoặc địa chỉ.

Khi đọc hoặc ghi dữ liệu nhị phân, cần xác định đúng kiểu dữ liệu, thứ tự byte (*byte order*) và yêu cầu căn chỉnh (*alignment*) của từng trường. Các thông tin này phải khớp với định dạng dữ liệu thực tế, chẳng hạn cấu trúc C, file nhị phân hoặc giao thức mạng. Bài viết sử dụng API `java.lang.foreign` đã được chuẩn hóa trong Java 22 và còn áp dụng ở các JDK hiện đại.

## 1. Vai trò của MemorySegment và ValueLayout

`MemorySegment` cung cấp một vùng nhớ liên tục có kích thước xác định. Vùng nhớ đó có thể nằm trong heap Java, ngoài heap (native memory) hoặc được ánh xạ từ file. Các thao tác đọc ghi trên segment đều được giới hạn trong phạm vi vùng nhớ mà segment đại diện.

`ValueLayout` mô tả cách diễn giải các byte trong vùng nhớ thành một giá trị. Mỗi value layout chứa bốn đặc điểm chính:

- **Kiểu Java nhận/trả về (carrier):** ví dụ `int`, `long`, `float`, `double` hoặc `MemorySegment` đối với địa chỉ.
- **Kích thước (`byteSize`):** số byte cần đọc hoặc ghi.
- **Căn chỉnh (`byteAlignment`):** yêu cầu căn chỉnh địa chỉ khi truy cập.
- **Thứ tự byte (`order`):** cách sắp xếp byte của giá trị nhiều byte.

Ví dụ, `ValueLayout.JAVA_INT` mô tả một giá trị Java `int` có kích thước 4 byte, căn chỉnh 4 byte và sử dụng thứ tự byte native của máy đang chạy.

## 2. Các ValueLayout có sẵn

FFM cung cấp layout cho các kiểu nguyên thủy Java và địa chỉ:

| ValueLayout | Kiểu Java (carrier) | Kích thước |
| --- | --- | ---: |
| `JAVA_BOOLEAN` | `boolean` | 1 byte |
| `JAVA_BYTE` | `byte` | 1 byte |
| `JAVA_CHAR` | `char` | 2 byte |
| `JAVA_SHORT` | `short` | 2 byte |
| `JAVA_INT` | `int` | 4 byte |
| `JAVA_LONG` | `long` | 8 byte |
| `JAVA_FLOAT` | `float` | 4 byte |
| `JAVA_DOUBLE` | `double` | 8 byte |
| `ADDRESS` | `MemorySegment` | Phụ thuộc kích thước địa chỉ máy |

Các layout trên có thể được kiểm tra bằng `byteSize()`, `byteAlignment()`, `order()` và `carrier()`:

```java
import java.lang.foreign.ValueLayout;

System.out.println(ValueLayout.JAVA_INT.byteSize());      // 4
System.out.println(ValueLayout.JAVA_INT.byteAlignment()); // 4
System.out.println(ValueLayout.JAVA_INT.carrier());       // int
System.out.println(ValueLayout.JAVA_INT.order());         // Byte order native
```

Kích thước của các layout Java phản ánh kiểu Java tương ứng. Riêng căn chỉnh của `JAVA_LONG` và `JAVA_DOUBLE` có thể phụ thuộc nền tảng; trên hệ thống 64 bit thường là 8 byte, còn trên một số hệ thống 32 bit là 4 byte.

## 3. Đọc và ghi một giá trị tại offset

Các phương thức `MemorySegment.get(...)` và `MemorySegment.set(...)` đọc hoặc ghi một giá trị theo layout được cung cấp. Offset được tính bằng byte và bắt đầu từ 0 tại đầu segment.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ReadWriteValue {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(8, 4);

            // Ghi hai giá trị int, mỗi giá trị chiếm 4 byte.
            segment.set(ValueLayout.JAVA_INT, 0, 120);
            segment.set(ValueLayout.JAVA_INT, 4, 350);

            // Đọc lại từ đúng các offset đã ghi.
            int first = segment.get(ValueLayout.JAVA_INT, 0);
            int second = segment.get(ValueLayout.JAVA_INT, 4);

            System.out.println(first);  // 120
            System.out.println(second); // 350
        }
    }
}
```

Trong ví dụ, segment có 8 byte và được cấp phát với căn chỉnh 4 byte. Trường `int` đầu tiên bắt đầu tại offset 0, trường thứ hai bắt đầu tại offset 4. Cần dùng cùng quy ước kiểu, thứ tự byte và offset khi đọc lại dữ liệu.

Các thao tác đọc ghi có kiểm tra phạm vi. Nếu offset âm hoặc vùng cần truy cập vượt quá `segment.byteSize()`, thao tác sẽ thất bại với `IndexOutOfBoundsException`. Nếu segment đã hết vòng đời hoặc luồng hiện tại không được phép truy cập segment, FFM cũng phát hiện và báo lỗi.

## 4. Phân biệt offset byte và index phần tử

`get` và `set` nhận offset theo byte. Nếu làm việc với một dãy phần tử cùng kiểu, `getAtIndex` và `setAtIndex` thuận tiện hơn vì nhận index logic; FFM tự nhân index với kích thước của layout.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class IntArraySegment {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            long count = 3;
            long size = count * ValueLayout.JAVA_INT.byteSize();
            MemorySegment numbers = arena.allocate(
                    size,
                    ValueLayout.JAVA_INT.byteAlignment()
            );

            numbers.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            numbers.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            numbers.setAtIndex(ValueLayout.JAVA_INT, 2, 30);

            for (long i = 0; i < count; i++) {
                System.out.println(numbers.getAtIndex(ValueLayout.JAVA_INT, i));
            }
        }
    }
}
```

Với `JAVA_INT`, index 0 tương ứng offset 0, index 1 tương ứng offset 4 và index 2 tương ứng offset 8. `getAtIndex` không nhận offset byte. Nếu cần truy cập trường ở vị trí byte cụ thể trong một cấu trúc, hãy dùng `get` hoặc `set` với offset rõ ràng.

## 5. Byte order: Big-endian và Little-endian

Byte order quyết định thứ tự các byte của một giá trị có nhiều hơn một byte:

- **Big-endian:** byte có trọng số cao nhất được lưu ở địa chỉ thấp nhất.
- **Little-endian:** byte có trọng số thấp nhất được lưu ở địa chỉ thấp nhất.

Với giá trị hệ thập lục phân `0x01020304`, cách lưu 4 byte là:

| Offset | Big-endian | Little-endian |
| ---: | ---: | ---: |
| 0 | `01` | `04` |
| 1 | `02` | `03` |
| 2 | `03` | `02` |
| 3 | `04` | `01` |

Các layout `JAVA_*` mặc định dùng `ByteOrder.nativeOrder()`, tức thứ tự byte của máy đang chạy. Nếu dữ liệu đến từ file hoặc giao thức có quy định byte order cụ thể, hãy tạo layout mới bằng `withOrder(...)` thay vì dựa vào mặc định.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

public class ByteOrderDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(4, 4);

            ValueLayout.OfInt bigEndianInt =
                    ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

            segment.set(bigEndianInt, 0, 0x01020304);

            int value = segment.get(bigEndianInt, 0);
            byte firstByte = segment.get(ValueLayout.JAVA_BYTE, 0);

            System.out.printf("Giá trị: 0x%08X%n", value);
            System.out.printf("Byte đầu tiên: 0x%02X%n",
                    Byte.toUnsignedInt(firstByte));
        }
    }
}
```

Kết quả:

```text
Giá trị: 0x01020304
Byte đầu tiên: 0x01
```

`withOrder` trả về một layout mới có cùng kiểu, kích thước và căn chỉnh nhưng dùng byte order được chỉ định. Nó không chuyển đổi hay sửa dữ liệu đang nằm trong segment. Khi ghi bằng Big-endian, phải đọc bằng layout Big-endian tương ứng để nhận lại cùng giá trị.

`ByteOrder.BIG_ENDIAN` thường phù hợp với định dạng mạng hoặc file quy định Big-endian; `ByteOrder.LITTLE_ENDIAN` phù hợp với định dạng quy định Little-endian. Không có một thứ tự byte nào đúng cho mọi nguồn dữ liệu: hãy theo đặc tả của dữ liệu.

## 6. Căn chỉnh dữ liệu (alignment)

Căn chỉnh là yêu cầu về địa chỉ bắt đầu của một lần truy cập. Một layout có `byteAlignment()` bằng 4 yêu cầu địa chỉ đích chia hết cho 4. `ValueLayout.JAVA_INT` có căn chỉnh 4 byte, vì vậy các offset như 0, 4, 8 thường phù hợp khi segment có địa chỉ đầu được căn chỉnh đúng; offset 1 không phù hợp với layout này.

Khi cấp phát native memory, có thể yêu cầu căn chỉnh cho địa chỉ đầu của segment:

```java
MemorySegment segment = arena.allocate(16, ValueLayout.JAVA_INT.byteAlignment());
```

Hoặc cấp phát theo layout để allocator dùng kích thước và căn chỉnh của layout:

```java
MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
```

Khi bố trí nhiều trường trong một cấu trúc, cần tính đến padding giữa các trường để mỗi trường bắt đầu tại offset phù hợp. Ví dụ, một `int` 4 byte đặt ở offset 0 thường có thể theo sau bởi một `long` ở offset 8 trên ABI có căn chỉnh 8 byte, với 4 byte padding giữa chúng. Cấu trúc C thực tế phải được đối chiếu với ABI và layout của linker; không tự giả định mọi compiler đều dùng cùng padding.

### Dữ liệu không căn chỉnh

Một số định dạng nhị phân đóng gói trường liên tiếp mà không thêm padding. Khi đó, một số giá trị nhiều byte có thể bắt đầu tại offset không chia hết cho căn chỉnh tự nhiên. Có thể mô tả cách truy cập này bằng layout không căn chỉnh, ví dụ `JAVA_INT_UNALIGNED`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

public class UnalignedAccess {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment packet = arena.allocate(5, 1);

            ValueLayout.OfInt packedInt =
                    ValueLayout.JAVA_INT_UNALIGNED
                            .withOrder(ByteOrder.LITTLE_ENDIAN);

            packet.set(packedInt, 1, 0x12345678);
            int value = packet.get(packedInt, 1);

            System.out.printf("0x%08X%n", value);
        }
    }
}
```

Layout `JAVA_INT_UNALIGNED` có căn chỉnh 1 byte nên có thể dùng ở offset 1. Dữ liệu vẫn chiếm 4 byte; chỉ có yêu cầu căn chỉnh thay đổi. Truy cập không căn chỉnh có thể ảnh hưởng hiệu năng hoặc tính tương thích trên một số nền tảng, vì vậy chỉ dùng khi định dạng dữ liệu thực sự yêu cầu.

Ngoài các hằng số `*_UNALIGNED`, có thể tạo layout riêng bằng `withByteAlignment(1)`. Giá trị căn chỉnh phải là số dương và là lũy thừa của 2.

## 7. Dùng ValueLayout đúng với kiểu dữ liệu C

Không được đồng nhất mọi kiểu C với kiểu Java có tên gần giống. Kích thước và căn chỉnh của kiểu C phụ thuộc ABI, compiler, hệ điều hành và kiến trúc CPU. Ví dụ, `long` trong C thường là 8 byte trên Linux/x64 nhưng là 4 byte trên Windows/x64; `size_t` cũng thay đổi theo mô hình 32 bit hoặc 64 bit.

Khi làm việc với thư viện C qua native linker, hãy lấy layout chuẩn của ABI bằng `Linker.canonicalLayouts()`:

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

public class CLayouts {
    public static void main(String[] args) {
        Linker linker = Linker.nativeLinker();
        MemoryLayout cLong = linker.canonicalLayouts().get("long");

        System.out.println("C long size: " + cLong.byteSize());
        System.out.println("C long alignment: " + cLong.byteAlignment());
    }
}
```

Native linker cung cấp canonical layout cho các kiểu C phổ biến như `bool`, `char`, `short`, `int`, `long`, `long long`, `float`, `double`, `size_t`, `wchar_t` và `void*`. Layout cụ thể có thể khác nhau giữa các ABI. Con trỏ C được mô tả bằng `ValueLayout.ADDRESS`; kiểu số nguyên không dấu thường dùng layout tương ứng với kiểu có dấu cùng kích thước và cần xử lý đúng miền giá trị khi chuyển đổi.

`ValueLayout.JAVA_LONG` luôn mô tả Java `long` 8 byte, không đồng nghĩa với C `long` trên mọi nền tảng. Nếu đọc một trường C `long`, hãy dùng layout ABI tương ứng thay vì chọn layout dựa trên tên.

## 8. Kết hợp nhiều layout cho một cấu trúc dữ liệu

Khi dữ liệu có nhiều trường, có thể mô tả cấu trúc bằng `MemoryLayout.structLayout(...)` và đặt tên từng trường. Ví dụ sau mô tả một cấu trúc đơn giản gồm hai số nguyên Java:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class StructAccess {
    private static final MemoryLayout POINT_LAYOUT = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("x"),
            ValueLayout.JAVA_INT.withName("y")
    );

    public static void main(String[] args) {
        var xHandle = POINT_LAYOUT.varHandle(groupElement("x"));
        var yHandle = POINT_LAYOUT.varHandle(groupElement("y"));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment point = arena.allocate(POINT_LAYOUT);

            xHandle.set(point, 15);
            yHandle.set(point, 25);

            System.out.println("x = " + (int) xHandle.get(point));
            System.out.println("y = " + (int) yHandle.get(point));
        }
    }
}
```

Ví dụ dùng `VarHandle` được tạo từ layout path để truy cập trường theo tên. Khi mô tả `struct` C thực tế, cần thêm padding layout và căn chỉnh đúng theo ABI nếu cấu trúc có khoảng đệm giữa các trường. `structLayout` không tự suy luận layout C từ header; lập trình viên phải mô tả chính xác cấu trúc native.

## 9. Lỗi thường gặp và cách tránh

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đọc ra số khác mong đợi | Dùng sai byte order hoặc sai kiểu layout. | Đối chiếu định dạng dữ liệu và chọn `withOrder(...)` phù hợp. |
| `IndexOutOfBoundsException` | Offset hoặc kích thước truy cập vượt phạm vi segment. | Kiểm tra `byteSize()` và tính toán offset trước khi đọc ghi. |
| `IllegalArgumentException` khi truy cập | Địa chỉ đích không đáp ứng căn chỉnh của layout. | Chọn offset đúng căn chỉnh hoặc layout không căn chỉnh nếu định dạng yêu cầu. |
| Giá trị C bị sai trên hệ điều hành khác | Dùng layout Java thay cho layout theo ABI, chẳng hạn mặc định cho rằng C `long` luôn là 8 byte. | Dùng `Linker.canonicalLayouts()` và tài liệu ABI. |
| Truy cập sau khi arena đóng | Vùng nhớ đã hết vòng đời. | Giữ segment trong phạm vi arena còn mở; dùng try-with-resources để đóng đúng lúc. |

Các thao tác trên `MemorySegment` có kiểm tra giới hạn không gian, vòng đời và quyền truy cập luồng. Những kiểm tra này giúp phát hiện nhiều lỗi truy cập, nhưng không thể xác nhận rằng byte đang đọc thực sự mang đúng ý nghĩa nghiệp vụ hoặc đúng cấu trúc mà thư viện native mong đợi.

## 10. Khi nào nên sử dụng ValueLayout?

`ValueLayout` phù hợp khi cần đọc ghi các trường có kiểu cơ bản trong native memory, file được ánh xạ hoặc vùng dữ liệu nhị phân. Nó đặc biệt hữu ích khi làm việc với thư viện C, định dạng file có cấu trúc, giao thức mạng hoặc dữ liệu cần chia sẻ giữa Java và native code.

Trước khi đọc hoặc ghi, hãy xác định bốn thông tin: kiểu dữ liệu, kích thước, byte order và căn chỉnh. Với dữ liệu do ABI C quyết định, lấy canonical layout từ native linker; với định dạng file hoặc giao thức, tuân thủ đặc tả của định dạng. Luôn kiểm tra offset, giới hạn segment và vòng đời arena để tránh đọc sai hoặc truy cập vùng nhớ không còn hợp lệ.

## 11. Tài liệu tham khảo

- [Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html) — kiểu dữ liệu, carrier, byte order và căn chỉnh.
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html) — các thao tác đọc ghi theo layout và offset.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html) — cấp phát native memory với kích thước và căn chỉnh.
- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html) — canonical layout cho các kiểu dữ liệu C theo ABI.
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — API chính thức từ Java 22.
