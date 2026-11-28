# Bulk put trên CharBuffer, ShortBuffer và IntBuffer

Java 16 bổ sung một overload bulk put tuyệt đối để sao chép một đoạn dữ liệu trực tiếp từ buffer nguồn sang buffer đích. Overload này có trên `CharBuffer`, `ShortBuffer` và `IntBuffer`:

```java
destination.put(index, source, offset, length);
```

Phương thức ghi `length` phần tử từ `source`, bắt đầu tại `offset`, vào `destination` bắt đầu tại `index`. Điểm đáng chú ý là **position của cả hai buffer đều không thay đổi**. Điều này hữu ích khi cần ghi vào một vùng đã xác định mà vẫn giữ nguyên trạng thái đọc/ghi tuần tự của các buffer.

Đây là overload buffer-to-buffer tuyệt đối được bổ sung từ Java 16. Các overload bulk put từ array và các thao tác relative put đã tồn tại ở những phiên bản trước; không nên nhầm chúng với API mới này.

## 1. Bulk put là gì?

Bulk put là thao tác ghi nhiều phần tử trong một lần gọi. Thay vì lặp từng phần tử:

```java
for (int i = 0; i < length; i++) {
    destination.put(destinationIndex + i, source.get(sourceOffset + i));
}
```

có thể dùng một lời gọi:

```java
destination.put(destinationIndex, source, sourceOffset, length);
```

Hai cách có cùng mục tiêu sao chép một đoạn phần tử. Bulk put kiểm tra tính hợp lệ của các tham số và có thể được triển khai hiệu quả hơn vòng lặp thủ công.

Các buffer được đề cập là buffer kiểu nguyên thủy:

| Buffer | Kiểu phần tử | Kiểu mảng tương ứng |
|---|---|---|
| `CharBuffer` | `char` | `char[]` |
| `ShortBuffer` | `short` | `short[]` |
| `IntBuffer` | `int` | `int[]` |

Các phần tử được sao chép theo đơn vị phần tử của buffer. Ví dụ, `IntBuffer` sao chép các giá trị `int`; phương thức không thực hiện chuyển đổi byte order hay mã hóa văn bản.

## 2. Chữ ký mới từ Java 16

Ba phương thức có cùng hình dạng tham số:

```java
CharBuffer put(int index, CharBuffer src, int offset, int length)

ShortBuffer put(int index, ShortBuffer src, int offset, int length)

IntBuffer put(int index, IntBuffer src, int offset, int length)
```

Ý nghĩa tham số:

| Tham số | Ý nghĩa |
|---|---|
| `index` | Chỉ số trong buffer đích tại đó phần tử đầu tiên được ghi |
| `src` | Buffer nguồn chứa dữ liệu cần sao chép |
| `offset` | Chỉ số trong buffer nguồn của phần tử đầu tiên cần đọc |
| `length` | Số phần tử cần sao chép |

Ví dụ với `IntBuffer`:

```java
import java.nio.IntBuffer;

IntBuffer source = IntBuffer.wrap(new int[] {10, 20, 30, 40});
IntBuffer destination = IntBuffer.allocate(8);

destination.put(2, source, 1, 2);
```

Lời gọi sao chép hai phần tử từ chỉ số 1 của nguồn sang chỉ số 2 của đích:

- Đọc `source.get(1)` và `source.get(2)`.
- Ghi vào `destination.put(2, ...)` và `destination.put(3, ...)`.
- Nội dung đích tại chỉ số 2 và 3 trở thành 20 và 30.

Không cần thay đổi `position` của nguồn hoặc đích để xác định vùng sao chép.

## 3. Position của hai buffer được giữ nguyên

Đây là khác biệt quan trọng nhất giữa overload mới và relative bulk put.

```java
import java.nio.CharBuffer;

CharBuffer source = CharBuffer.wrap(new char[] {'A', 'B', 'C', 'D'});
source.position(1);

CharBuffer destination = CharBuffer.allocate(8);
destination.position(2);

destination.put(1, source, 0, 3);

System.out.println(source.position());      // 1
System.out.println(destination.position()); // 2

System.out.println(destination.get(1)); // A
System.out.println(destination.get(2)); // B
System.out.println(destination.get(3)); // C
```

Nguồn có `position` bằng 1, nhưng `offset` bằng 0 nên thao tác đọc bắt đầu từ chỉ số tuyệt đối 0 của nguồn. Đích có `position` bằng 2, nhưng `index` bằng 1 nên dữ liệu được ghi bắt đầu tại chỉ số tuyệt đối 1 của đích.

Sau lời gọi, hai position vẫn lần lượt là 1 và 2. Các thao tác `get(index)` trong ví dụ cũng là absolute get nên không làm thay đổi position.

Điều này cho phép cập nhật một vùng đích độc lập với vị trí mà phần còn lại của chương trình đang đọc hoặc ghi tuần tự.

## 4. Index và offset là chỉ số tuyệt đối trong từng buffer

`index` và `offset` được tính theo hệ chỉ số của từng buffer, bắt đầu từ 0 và bị giới hạn bởi `limit` tương ứng.

Chúng không phải:

- `position` hiện tại của buffer.
- `arrayOffset()` của backing array.
- Chỉ số tuyệt đối của buffer cha nếu buffer hiện tại là một slice.
- Byte offset trong vùng nhớ.

Nếu buffer được tạo bằng `slice()`, chỉ số 0 của slice là phần tử đầu tiên trong vùng được slice. Lời gọi bulk put dùng chỉ số tương đối với slice đó.

Ví dụ:

```java
import java.nio.IntBuffer;

IntBuffer parent = IntBuffer.wrap(new int[] {10, 20, 30, 40, 50});
parent.position(1);
parent.limit(4);

IntBuffer sourceSlice = parent.slice();

IntBuffer destination = IntBuffer.allocate(6);
destination.put(1, sourceSlice, 0, 2);
```

`sourceSlice` nhìn thấy vùng gồm các giá trị 20, 30 và 40. Chỉ số 0 của slice tương ứng với giá trị 20 trong buffer cha. Vì vậy, lời gọi sao chép 20 và 30 vào destination tại chỉ số 1 và 2.

Không truyền chỉ số 1 của buffer cha làm offset cho slice nếu mục tiêu là phần tử đầu tiên của slice.

## 5. Điều kiện hợp lệ của index, offset và length

Theo hợp đồng API, các điều kiện cần thỏa mãn là:

```text
index >= 0
index < destination.limit()

offset >= 0
offset < source.limit()

length >= 0
length <= destination.limit() - index
length <= source.limit() - offset
```

Nói cách khác, vùng đích phải đủ chỗ từ `index` và vùng nguồn phải đủ phần tử từ `offset`. Các giới hạn được tính theo `limit`, không phải `capacity`.

Ví dụ:

```java
import java.nio.IntBuffer;

IntBuffer source = IntBuffer.wrap(new int[] {1, 2, 3, 4, 5});
source.limit(4);

IntBuffer destination = IntBuffer.allocate(8);
destination.limit(6);

destination.put(2, source, 1, 3);
```

Nguồn cho phép đọc các chỉ số 1, 2 và 3. Đích cho phép ghi các chỉ số 2, 3 và 4. Cả hai vùng đều nằm trong limit tương ứng.

Lưu ý rằng tài liệu API yêu cầu `index` nhỏ hơn limit của đích và `offset` nhỏ hơn limit của nguồn. Không nên tự suy ra rằng chỉ vì `length == 0` thì có thể đặt index hoặc offset bằng limit. Hãy tuân thủ đầy đủ precondition được mô tả cho overload này.

## 6. Phân biệt limit và capacity

`capacity` là số phần tử tối đa mà buffer có thể chứa. `limit` là ranh giới hiện tại mà thao tác đọc/ghi phải tôn trọng.

Ví dụ:

```java
import java.nio.IntBuffer;

IntBuffer destination = IntBuffer.allocate(10);
destination.position(2);
destination.limit(6);

System.out.println(destination.capacity()); // 10
System.out.println(destination.limit());    // 6

destination.put(4, IntBuffer.wrap(new int[] {7, 8}), 0, 2);
```

Lời gọi ghi vào chỉ số 4 và 5, hợp lệ vì vùng này nằm trước limit 6. Các vị trí 6 đến 9 vẫn nằm trong capacity nhưng không thể được ghi bằng thao tác này khi limit đang là 6.

Nếu vùng đích vượt limit, phương thức ném `IndexOutOfBoundsException` ngay cả khi capacity còn đủ chỗ.

## 7. Ví dụ với CharBuffer

`CharBuffer` phù hợp với thao tác trên chuỗi ký tự hoặc dữ liệu ký tự. Ví dụ, có thể sao chép một đoạn ký tự từ buffer nguồn vào một vị trí xác định trong buffer đích:

```java
import java.nio.CharBuffer;

CharBuffer source = CharBuffer.wrap("Java NIO buffer");

CharBuffer destination = CharBuffer.allocate(24);
destination.put("Header: ");

destination.put(8, source, 5, 3);

System.out.println(destination.get(8));  // N
System.out.println(destination.get(9));  // I
System.out.println(destination.get(10)); // O
System.out.println(destination.position()); // 8
```

`source` chứa chuỗi "Java NIO buffer". Offset 5 trỏ đến ký tự N; length 3 chọn N, I, O. Destination ghi tại index 8, ghi đè đúng ba vị trí bắt đầu từ đó.

Lời gọi `destination.put("Header: ")` là relative put nên position của đích tăng lên 8. Lời gọi bulk put tuyệt đối tiếp theo không thay đổi position, vì vậy position vẫn là 8.

Ví dụ này cho thấy có thể xây dựng phần đầu bằng relative put rồi điền một vùng khác bằng absolute bulk put mà không cần lưu và khôi phục position thủ công.

## 8. Ví dụ với ShortBuffer

`ShortBuffer` thường dùng để xử lý dữ liệu số nguyên 16-bit. Bulk put có thể chép một đoạn mẫu từ buffer nguồn sang vùng đích:

```java
import java.nio.ShortBuffer;

ShortBuffer source = ShortBuffer.wrap(
    new short[] {100, 200, 300, 400, 500}
);
source.position(2);
source.limit(5);

ShortBuffer destination = ShortBuffer.allocate(8);
destination.position(1);

destination.put(3, source, 1, 2);

System.out.println(destination.get(3)); // 200
System.out.println(destination.get(4)); // 300

System.out.println(source.position());      // 2
System.out.println(destination.position()); // 1
```

`offset` là 1, nên thao tác đọc phần tử tại source index 1 và 2, bất kể source position hiện tại là 2. Destination bắt đầu ghi tại index 3.

Nếu muốn sao chép từ vị trí hiện tại của nguồn, hãy truyền `source.position()` làm offset một cách tường minh. Overload tuyệt đối không tự lấy position thay cho offset.

## 9. Ví dụ với IntBuffer

`IntBuffer` phù hợp với dữ liệu số nguyên 32-bit, chẳng hạn các phần tử của một block dữ liệu hoặc kết quả tính toán:

```java
import java.nio.IntBuffer;

IntBuffer source = IntBuffer.wrap(
    new int[] {10, 20, 30, 40, 50, 60}
);
source.position(2);
source.limit(5);

IntBuffer destination = IntBuffer.allocate(10);
destination.position(4);

destination.put(1, source, 0, 3);

System.out.println(destination.get(1)); // 10
System.out.println(destination.get(2)); // 20
System.out.println(destination.get(3)); // 30

System.out.println(source.position());      // 2
System.out.println(destination.position()); // 4
```

Mặc dù nguồn có position 2, offset 0 yêu cầu sao chép từ phần tử đầu tiên trong vùng nguồn. Ba giá trị 10, 20 và 30 được ghi vào các chỉ số 1, 2 và 3 của đích.

Nếu cần ghi dữ liệu vào vị trí hiện tại của đích, relative put phù hợp hơn. Nếu cần ghi vào một index cụ thể và giữ position, dùng overload tuyệt đối.

## 10. So sánh absolute bulk put với relative bulk put

Hai overload buffer-to-buffer có mục đích khác nhau:

| Đặc điểm | Relative `put(src)` | Absolute `put(index, src, offset, length)` |
|---|---|---|
| Vùng nguồn | Từ `src.position()` đến `src.limit()` | Từ `offset` đến `offset + length` |
| Vùng đích | Từ `destination.position()` | Từ `index` |
| Destination position | Tăng theo số phần tử đã ghi | Không đổi |
| Source position | Tăng theo số phần tử đã đọc | Không đổi |
| Kiểm tra chỗ đích | `remaining()` | `limit() - index` |
| Thiếu chỗ đích | `BufferOverflowException` | `IndexOutOfBoundsException` |
| Kể từ | API buffer ban đầu | Java 16 |

Ví dụ relative put:

```java
import java.nio.IntBuffer;

IntBuffer source = IntBuffer.wrap(new int[] {1, 2, 3});
IntBuffer destination = IntBuffer.allocate(5);

destination.position(1);
destination.put(source);

System.out.println(source.position());      // 3
System.out.println(destination.position()); // 4
```

Relative put tiêu thụ phần còn lại của nguồn và tăng position cả hai buffer.

Với relative `put(src)`, hợp đồng yêu cầu nguồn không phải chính buffer đích; truyền cùng object sẽ gây `IllegalArgumentException`. Absolute bulk put có hợp đồng riêng về vùng chỉ số và vùng nhớ chồng lấp: khi hai buffer chia sẻ backing memory, kết quả được xác định như thể dữ liệu nguồn được sao chép tạm trước khi ghi.

Với absolute bulk put:

```java
IntBuffer source = IntBuffer.wrap(new int[] {1, 2, 3});
IntBuffer destination = IntBuffer.allocate(5);

destination.put(1, source, 0, 3);

System.out.println(source.position());      // 0
System.out.println(destination.position()); // 0
```

Lời gọi tuyệt đối sao chép vùng được chỉ định và giữ nguyên hai position.

## 11. Phân biệt bulk put từ array với overload mới từ buffer

Các typed buffer còn có bulk put từ array. Một số overload array tuyệt đối đã có từ Java 13, ví dụ:

```java
destination.put(index, sourceArray, offset, length);
```

Overload này sao chép từ array vào buffer và giữ nguyên position của buffer đích. Nó không phải overload mới được thêm trong Java 16.

Overload mới từ Java 16 nhận một buffer cùng kiểu:

```java
destination.put(index, sourceBuffer, offset, length);
```

Sự khác biệt quan trọng:

| Nguồn | Chữ ký | Phiên bản |
|---|---|---|
| Array | `put(int index, char[] src, int offset, int length)` | Java 13 |
| CharBuffer | `put(int index, CharBuffer src, int offset, int length)` | Java 16 |
| Array | `put(int index, short[] src, int offset, int length)` | Java 13 |
| ShortBuffer | `put(int index, ShortBuffer src, int offset, int length)` | Java 16 |
| Array | `put(int index, int[] src, int offset, int length)` | Java 13 |
| IntBuffer | `put(int index, IntBuffer src, int offset, int length)` | Java 16 |

Nếu nguồn vốn đã là typed buffer, overload mới giúp sao chép trực tiếp từ vùng của buffer nguồn mà không cần lấy backing array. Điều này cũng hữu ích với direct buffer hoặc read-only source buffer, nơi không thể truy cập array theo cách thông thường.

## 12. Sao chép giữa các buffer dùng chung vùng nhớ

Hai buffer có thể chia sẻ backing storage, ví dụ một buffer được tạo bằng `duplicate()` hoặc `slice()`. Khi vùng nguồn và vùng đích chồng lấp, hợp đồng của absolute bulk put quy định kết quả như thể các phần tử nguồn đã được sao chép vào một vùng trung gian trước khi ghi vào đích.

Ví dụ:

```java
import java.nio.IntBuffer;
import java.util.Arrays;

int[] values = {10, 20, 30, 40, 50};

IntBuffer source = IntBuffer.wrap(values);
IntBuffer destination = source.duplicate();

destination.put(1, source, 0, 3);

System.out.println(Arrays.toString(values));
// [10, 10, 20, 30, 50]
```

Nếu thực hiện sao chép theo kiểu đọc rồi ghi tuần tự mà không có vùng tạm, việc ghi đè phần tử có thể ảnh hưởng đến dữ liệu sẽ đọc ở bước sau. Bulk put định nghĩa kết quả như thể nguồn được chụp trước khi ghi, nên vùng chồng lấp có kết quả ổn định theo hợp đồng.

Không nên tự thay thế thao tác này bằng vòng lặp forward đơn giản khi nguồn và đích có thể dùng chung vùng nhớ. Nếu tự viết thuật toán sao chép, phải xử lý đúng trường hợp overlap.

## 13. Read-only destination và nguồn read-only

Bulk put là thao tác ghi vào buffer đích. Nếu đích là read-only, phương thức ném `ReadOnlyBufferException`.

```java
import java.nio.IntBuffer;

IntBuffer source = IntBuffer.wrap(new int[] {1, 2, 3});
IntBuffer writable = IntBuffer.allocate(5);
IntBuffer readOnlyDestination = writable.asReadOnlyBuffer();

readOnlyDestination.put(0, source, 0, 2);
// ReadOnlyBufferException
```

Nguồn read-only vẫn có thể được đọc để sao chép. Điều kiện read-only áp dụng cho buffer đích vì đó là nơi nội dung bị thay đổi.

```java
IntBuffer readOnlySource =
    IntBuffer.wrap(new int[] {7, 8, 9}).asReadOnlyBuffer();

IntBuffer destination = IntBuffer.allocate(5);

destination.put(1, readOnlySource, 0, 3);
```

Ví dụ này hợp lệ: nguồn chỉ được đọc, còn đích có thể ghi.

## 14. Các exception cần phân biệt

Overload tuyệt đối buffer-to-buffer có thể ném:

| Exception | Nguyên nhân |
|---|---|
| `IndexOutOfBoundsException` | `index`, `offset` hoặc `length` không thỏa điều kiện phạm vi |
| `ReadOnlyBufferException` | Buffer đích không cho phép ghi |
| `NullPointerException` | Tham chiếu nguồn là null |

Đặc biệt, nếu vùng đích không đủ chỗ từ index đã cho, overload tuyệt đối báo `IndexOutOfBoundsException` theo hợp đồng tham số. Không nhầm với `BufferOverflowException` của relative put khi `remaining()` không đủ.

Ví dụ:

```java
import java.nio.IntBuffer;

IntBuffer source = IntBuffer.wrap(new int[] {1, 2, 3});
IntBuffer destination = IntBuffer.allocate(4);
destination.limit(3);

destination.put(2, source, 0, 2);
// IndexOutOfBoundsException: limit - index chỉ còn 1, nhưng length là 2.
```

Nếu dùng relative put với destination position 2 và remaining bằng 1 trong khi nguồn còn 3 phần tử, lỗi tương ứng sẽ là `BufferOverflowException`.

## 15. Dùng Objects.checkFromIndexSize để xác thực vùng trước khi sao chép

Khi xây dựng API bao quanh buffer, có thể xác thực vùng đích và vùng nguồn trước khi gọi bulk put. Điều này hữu ích nếu cùng các vùng sẽ được dùng cho nhiều bước xử lý.

```java
import java.nio.IntBuffer;
import java.util.Objects;

static void copy(
    IntBuffer destination,
    int destinationIndex,
    IntBuffer source,
    int sourceOffset,
    int length
) {
    Objects.checkFromIndexSize(
        destinationIndex, length, destination.limit()
    );

    Objects.checkFromIndexSize(
        sourceOffset, length, source.limit()
    );

    destination.put(destinationIndex, source, sourceOffset, length);
}
```

Lưu ý: helper kiểm tra khoảng có thể chấp nhận một range rỗng bắt đầu tại đúng limit. Javadoc của overload absolute bulk put mô tả rõ index và offset phải nhỏ hơn limit. Vì vậy, nếu tự xác thực trước bằng helper, hãy bảo đảm hợp đồng của wrapper không nới lỏng precondition của thao tác cuối cùng, đặc biệt khi length bằng 0.

Nếu chỉ gọi bulk put một lần, thường không cần lặp lại toàn bộ kiểm tra bằng helper; chính phương thức đã xác thực tham số. Kiểm tra tường minh có ý nghĩa khi API riêng cần đưa ra thông báo hoặc xác thực nhiều vùng trước khi thay đổi dữ liệu.

## 16. Khi nào nên dùng bulk put tuyệt đối?

Dùng overload mới khi:

- Cần chép một đoạn cụ thể từ buffer nguồn sang vị trí cụ thể của buffer đích.
- Muốn giữ nguyên position của cả hai buffer.
- Đang xử lý nhiều vùng dữ liệu độc lập trong cùng buffer.
- Nguồn là typed buffer, kể cả direct buffer hoặc read-only buffer.
- Cần sao chép giữa các buffer chia sẻ vùng nhớ và muốn tuân theo semantics overlap của API.

Dùng relative `put(src)` khi:

- Muốn tiêu thụ toàn bộ phần còn lại của nguồn.
- Muốn position hai buffer tự tiến lên sau khi sao chép.
- Pipeline xử lý dữ liệu tuần tự theo position hiện tại.

Dùng bulk put từ array khi nguồn là mảng và không cần biểu diễn nó như một buffer.

Không chọn overload chỉ vì tên có chữ bulk. Hãy chọn theo nguồn dữ liệu, vị trí cần ghi và trạng thái position mà phần còn lại của chương trình mong đợi.

## 17. Những lỗi thường gặp

**Nghĩ offset là source.position.** Offset là chỉ số tuyệt đối được truyền rõ ràng. Muốn bắt đầu từ position hiện tại, hãy truyền `source.position()`.

**Nghĩ index là destination.position.** Index là vị trí tuyệt đối của phần tử đầu tiên được ghi. Destination position không tham gia xác định vùng ghi.

**Mong hai position tăng sau lời gọi.** Overload mới giữ nguyên position của cả nguồn và đích. Relative `put(src)` mới tiêu thụ phần còn lại và tăng position.

**Dùng capacity để xác định vùng hợp lệ.** Các chỉ số bị giới hạn bởi limit. Capacity lớn hơn limit không làm cho vùng vượt limit hợp lệ.

**Nhầm IndexOutOfBoundsException với BufferOverflowException.** Absolute bulk put báo lỗi phạm vi qua `IndexOutOfBoundsException`; relative put báo thiếu remaining qua `BufferOverflowException`.

**Nhầm overload từ array với overload mới từ buffer.** Absolute array bulk put đã có từ Java 13; buffer-to-buffer absolute bulk put được bổ sung trong Java 16.

**Tự viết vòng lặp khi hai buffer có thể overlap.** Cách sao chép forward có thể ghi đè dữ liệu nguồn chưa đọc. Bulk put định nghĩa kết quả như thể vùng nguồn được sao chép tạm trước.

**Ghi vào read-only destination.** Buffer nguồn read-only vẫn đọc được; buffer đích read-only sẽ ném `ReadOnlyBufferException`.

**Giả định bulk put luôn nhanh hơn trong mọi trường hợp.** API cho phép triển khai hiệu quả hơn vòng lặp, nhưng hiệu năng phụ thuộc implementation, loại buffer và workload. Đo khi hiệu năng là yêu cầu thực tế.

## 18. Ghi nhớ

- Java 16 bổ sung `put(int index, XxxBuffer src, int offset, int length)` cho `CharBuffer`, `ShortBuffer` và `IntBuffer`.
- Phương thức chép `length` phần tử từ source offset sang destination index.
- Position của cả hai buffer không thay đổi.
- Index và offset là chỉ số tuyệt đối theo từng buffer, được giới hạn bởi limit.
- Destination phải đủ chỗ từ index; source phải đủ phần tử từ offset.
- Vùng nguồn và đích có thể dùng chung backing memory; kết quả được xác định như thể nguồn được sao chép vào vùng tạm trước.
- Destination read-only gây `ReadOnlyBufferException`; vùng tham số sai gây `IndexOutOfBoundsException`.
- Relative `put(src)` có semantics khác: nó sao chép phần còn lại và tăng position hai buffer.
- Absolute bulk put từ array đã có từ Java 13; overload buffer-to-buffer là phần bổ sung Java 16.
- Không giả định thao tác luôn nhanh hơn vòng lặp hoặc không có chi phí nội bộ.
- Chọn overload theo vùng dữ liệu cần sao chép và trạng thái position mà ứng dụng cần giữ.

Bulk put tuyệt đối giúp sao chép một vùng typed buffer mà không làm thay đổi vị trí đọc/ghi hiện tại. Khi hiểu rõ `index`, `offset`, `length`, `limit` và các exception, có thể dùng cùng một cách nhất quán trên `CharBuffer`, `ShortBuffer` và `IntBuffer` trong mã Java hiện đại.

## Tài liệu tham khảo

- [Java SE 16 API – CharBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/CharBuffer.html)
- [Java SE 16 API – ShortBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ShortBuffer.html)
- [Java SE 16 API – IntBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/IntBuffer.html)
- [Java SE API – Buffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/Buffer.html)

