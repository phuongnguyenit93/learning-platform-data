# Sao chép vùng buffer chồng lấn và kiểm chứng dữ liệu

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Chỉ số và buffer. Java 16 bổ sung absolute bulk copy giữa hai vùng `ByteBuffer` bằng `put(int index, ByteBuffer src, int offset, int length)`. API này hữu ích khi source và destination là hai view cùng chia sẻ một vùng nhớ và các vùng copy chồng lấn. Hợp đồng bảo đảm kết quả như thể byte nguồn được chụp vào vùng trung gian trước khi ghi. Bài học trình bày cách xác định vùng, sao chép theo cả hai hướng, hiểu `duplicate` và `slice`, dùng `compact` trong luồng I/O và kiểm chứng dữ liệu sau sao chép.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích position, limit, capacity và chỉ số tuyệt đối của `ByteBuffer`.
- Nhận biết hai view có thể chia sẻ cùng backing memory dù là hai object khác nhau.
- Dùng absolute bulk put được bổ sung từ Java 16 để sao chép vùng buffer chồng lấn.
- Phân biệt absolute copy với relative `put(ByteBuffer src)`.
- Dùng `duplicate()` và `slice()` mà không nhầm hệ chỉ số của từng view.
- Giải thích `compact()` và cách giữ lại dữ liệu chưa được xử lý.
- Kiểm chứng vùng đích, vùng lân cận, position và limit sau sao chép.
- Kiểm tra lỗi range, read-only buffer và trường hợp source/destination thiếu dung lượng.

## 1. Vùng dữ liệu trong ByteBuffer

`ByteBuffer` quản lý một vùng byte cùng các giới hạn quan trọng:

- **capacity:** số byte tối đa mà buffer có thể chứa; không thay đổi sau khi tạo.
- **limit:** ranh giới mà thao tác đọc/ghi không được vượt qua.
- **position:** chỉ số của byte tiếp theo trong thao tác tương đối.
- **remaining:** số byte còn lại, bằng `limit - position`.

Một thao tác tuyệt đối như `get(index)` hoặc `put(index, value)` dùng chỉ số được truyền trực tiếp và không thay đổi position. Các thao tác tương đối như `get()` và `put(value)` sử dụng position hiện tại rồi tăng position.

Ví dụ:

```java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocate(8);

buffer.put(new byte[] { 10, 20, 30, 40 });
System.out.println(buffer.position()); // 4
System.out.println(buffer.limit());    // 8

buffer.flip();
System.out.println(buffer.position()); // 0
System.out.println(buffer.limit());    // 4

byte first = buffer.get(0); // Đọc tuyệt đối, position vẫn là 0
byte next = buffer.get();  // Đọc tương đối, position thành 1
```

`flip()` chuyển buffer từ chế độ ghi sang chế độ đọc: limit được đặt bằng position hiện tại, position trở về 0. Sau khi đọc xong dữ liệu cần giữ lại, `compact()` hoặc `clear()` có thể chuẩn bị buffer cho lần ghi tiếp theo, tùy mục đích.

### 1.1. Chỉ số tuyệt đối được kiểm tra theo limit

Với các thao tác tuyệt đối của `ByteBuffer`, chỉ số hợp lệ phải nằm trong vùng trước limit, không chỉ trước capacity. Ví dụ buffer có capacity 16 nhưng limit 8 thì `get(9)` không hợp lệ.

Với thao tác sao chép vùng:

```java
destination.put(index, source, offset, length);
```

- `index` là chỉ số bắt đầu ghi trong hệ chỉ số của destination.
- `offset` là chỉ số bắt đầu đọc trong hệ chỉ số của source.
- `length` là số byte cần sao chép.
- Vùng đích phải nằm trong limit của destination.
- Vùng nguồn phải nằm trong limit của source.

Không nhầm `offset` với position của source. Đây là chỉ số tuyệt đối trong source view, dù position của source đang ở vị trí khác.

## 2. Vì sao vùng buffer có thể chồng lấn?

Hai buffer không nhất thiết sở hữu hai vùng nhớ riêng. Các phương thức `duplicate()` và `slice()` tạo view mới chia sẻ nội dung với buffer gốc. Ghi vào một view sẽ nhìn thấy được từ view còn lại.

Ví dụ:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

byte[] bytes = "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

ByteBuffer original = ByteBuffer.wrap(bytes);
ByteBuffer view = original.duplicate();

view.put(0, (byte) 'Z');

System.out.println(new String(bytes, StandardCharsets.US_ASCII));
// ZBCDEFGH
```

`original` và `view` là hai object khác nhau nhưng cùng tham chiếu nội dung byte. Position, limit và mark của chúng độc lập; nội dung thì được chia sẻ.

Vì vậy, một thao tác copy có thể đọc và ghi vào những vùng địa chỉ giao nhau. Nếu copy từng byte theo chiều không phù hợp, byte vừa ghi có thể ghi đè byte chưa kịp đọc.

### 2.1. Ví dụ lỗi khi tự copy từng byte theo chiều tiến

Giả sử vùng ban đầu là:

```text
Chỉ số:  0 1 2 3 4 5 6 7
Dữ liệu: A B C D E F G H
```

Muốn chuyển 6 byte ở vùng nguồn [0, 6) sang vùng đích [2, 8), kết quả đúng phải là:

```text
Chỉ số:  0 1 2 3 4 5 6 7
Dữ liệu: A B A B C D E F
```

Nếu tự viết vòng lặp tăng chỉ số:

```java
for (int i = 0; i < 6; i++) {
    buffer.put(2 + i, buffer.get(i));
}
```

thì ở lần đầu, byte A được ghi vào chỉ số 2, làm byte C ban đầu biến mất trước khi vòng lặp đọc đến chỉ số 2. Kết quả sẽ bị sai.

Đây là vấn đề giống thao tác di chuyển vùng nhớ có chồng lấn: phải bảo đảm toàn bộ giá trị nguồn ban đầu được giữ lại cho đến khi được đọc.

### 2.2. Vì sao copy ngược đôi khi có vẻ đúng nhưng không phải hợp đồng tốt?

Với ví dụ đích bắt đầu sau nguồn, vòng lặp từ cuối về đầu có thể tránh ghi đè dữ liệu chưa đọc. Nhưng nếu đích nằm trước nguồn, hướng copy phù hợp lại khác. Code phải tự tính hướng, tự quản lý range và xử lý mọi loại view.

Một API copy có hợp đồng overlap-safe giúp loại bỏ logic hướng copy tự viết. Java 16 bổ sung overload tuyệt đối của `ByteBuffer.put` để xử lý trực tiếp tình huống này.

## 3. Absolute bulk put được bổ sung từ Java 16

Java 16 bổ sung phương thức:

```java
ByteBuffer put(int index, ByteBuffer src, int offset, int length)
```

Phương thức sao chép `length` byte từ `src`, bắt đầu ở `offset`, sang buffer đích tại `index`. Đây là absolute bulk put:

- Position của destination không đổi.
- Position của source không đổi.
- Các vùng được kiểm tra trước khi copy.
- Nếu source và destination chia sẻ backing array hoặc memory, kết quả giống như thể source được copy vào vùng trung gian trước khi ghi destination.
- Phương thức trả về destination để có thể nối lời gọi.

Hợp đồng này bao phủ cả trường hợp source và destination là hai view chồng lấn cùng một vùng nhớ.

### 3.1. Copy vùng chồng lấn bằng duplicate

Ví dụ hoàn chỉnh:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class OverlappingCopyDemo {
    public static void main(String[] args) {
        byte[] storage =
                "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

        ByteBuffer destination = ByteBuffer.wrap(storage);
        ByteBuffer source = destination.duplicate();

        destination.put(2, source, 0, 6);

        System.out.println(
                new String(storage, StandardCharsets.US_ASCII)
        ); // ABABCDEF

        System.out.println(destination.position()); // 0
        System.out.println(source.position());      // 0
    }
}
```

`source` và `destination` chia sẻ cùng mảng byte. Source chỉ vùng [0, 6), destination ghi vào [2, 8). Dù hai vùng chồng lấn, kết quả vẫn là `ABABCDEF` như thể sáu byte nguồn ban đầu đã được chụp lại trước khi ghi.

Không cần tự chọn copy từ cuối về đầu. Hợp đồng của phương thức xử lý trường hợp overlap cho cả hai hướng.

### 3.2. Copy theo hướng ngược lại

Nếu vùng đích bắt đầu trước vùng nguồn, phương thức vẫn giữ dữ liệu nguồn ban đầu:

```java
byte[] storage =
        "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

ByteBuffer destination = ByteBuffer.wrap(storage);
ByteBuffer source = destination.duplicate();

destination.put(0, source, 2, 6);

System.out.println(new String(storage, StandardCharsets.US_ASCII));
// CDEFGHGH
```

Nguồn là `CDEFGH` tại [2, 8), đích là [0, 6). Các byte cuối không thuộc vùng đích được giữ nguyên. Phương thức không yêu cầu caller đảo chiều copy theo vị trí tương đối của hai vùng.

### 3.3. Không thay đổi position không có nghĩa nội dung không đổi

Absolute put không thay đổi position, limit hoặc mark của hai view. Nhưng nội dung ở vùng đích vẫn thay đổi và các view khác cùng chia sẻ vùng nhớ sẽ quan sát được nội dung mới.

| Thuộc tính | Sau absolute put |
|---|---|
| Nội dung vùng đích | Được ghi bằng byte nguồn |
| Nội dung vùng nguồn không chồng lấn | Không đổi |
| Nội dung vùng nguồn chồng lấn | Có thể thay đổi vì đó cũng là vùng đích |
| Position destination | Không đổi |
| Position source | Không đổi |
| Limit hai buffer | Không đổi |
| Mark | Không bị thay đổi bởi thao tác tuyệt đối này |

Không dùng position để suy ra vùng nào vừa được copy. Hãy dùng các chỉ số tuyệt đối đã truyền vào hoặc kiểm tra nội dung đích.

## 4. Phân biệt absolute put và relative put

`ByteBuffer` có hai cách copy giữa buffer.

### 4.1. Relative put(ByteBuffer)

`dst.put(src)` chuyển toàn bộ byte còn lại của source:

- Bắt đầu đọc tại `src.position()`.
- Bắt đầu ghi tại `dst.position()`.
- Số byte được copy bằng `src.remaining()`.
- Position của cả hai buffer tăng thêm số byte đã copy.
- Nếu destination không đủ remaining, ném `BufferOverflowException` và không copy byte nào.
- Source không được là chính destination object.

Nếu hai buffer chia sẻ cùng backing array hoặc memory, API cũng quy định kết quả như thể các phần tử nguồn được copy vào vùng trung gian trước khi ghi.

Ví dụ:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

ByteBuffer destination = ByteBuffer.allocate(8);
destination.position(2);

ByteBuffer source = ByteBuffer.wrap(
        "ABCD".getBytes(StandardCharsets.US_ASCII)
);
source.position(1);

destination.put(source);

System.out.println(destination.position()); // 5
System.out.println(source.position());      // 4
```

Destination ghi `BCD` từ position 2. Source đã được đọc hết nên position bằng limit 4.

### 4.2. Absolute put(index, src, offset, length)

Dùng overload Java 16 khi cần copy một vùng cụ thể mà không muốn thay đổi trạng thái đọc/ghi của hai buffer:

```java
destination.put(destinationIndex, source, sourceOffset, byteCount);
```

| Tiêu chí | Relative put(src) | Absolute put(index, src, offset, length) |
|---|---|---|
| Phạm vi nguồn | `src.position()` đến `src.limit()` | `offset` đến `offset + length` |
| Vị trí đích | `dst.position()` | `index` |
| Thay đổi position | Tăng position của cả hai | Không thay đổi position |
| Chọn số byte | Toàn bộ `src.remaining()` | Caller chỉ định `length` |
| Overlap cùng memory | Có semantics như source tạm | Có semantics như source tạm |
| Phiên bản | Có từ các phiên bản NIO đầu tiên | Có từ Java 16 |

Không phải lúc nào absolute copy cũng tốt hơn. Nếu đang chuyển dữ liệu tuần tự qua một pipeline, relative put thường tự nhiên hơn. Nếu đang thao tác trên các vùng byte có chỉ số rõ ràng, absolute put giúp code thể hiện chính xác vùng nguồn và đích.

## 5. duplicate và slice: cùng dữ liệu, hệ chỉ số khác nhau

`duplicate()` tạo view có position, limit, capacity ban đầu giống buffer gốc nhưng các trạng thái này độc lập. Chỉ số tuyệt đối trong duplicate tương ứng cùng chỉ số trong buffer gốc.

`slice()` tạo view bắt đầu tại position hiện tại của buffer gốc và có capacity bằng remaining của buffer gốc. Chỉ số 0 của slice tương ứng với position tại thời điểm tạo slice.

Ví dụ:

```java
byte[] storage =
        "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

ByteBuffer parent = ByteBuffer.wrap(storage);
ByteBuffer window = parent.duplicate();

window.position(2);
window.limit(6);

ByteBuffer slice = window.slice();

System.out.println(slice.position()); // 0
System.out.println(slice.limit());    // 4
System.out.println((char) slice.get(0)); // C
```

`slice.get(0)` đọc byte C vì slice bắt đầu tại chỉ số 2 của vùng nhớ gốc. Khi dùng slice làm source cho absolute put, `offset` được tính theo hệ chỉ số của slice, không phải hệ chỉ số của parent.

### 5.1. Copy từ slice sang parent

Ví dụ sao chép bốn byte từ slice về đầu parent:

```java
byte[] storage =
        "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

ByteBuffer parent = ByteBuffer.wrap(storage);
ByteBuffer sourceView = parent.duplicate();

sourceView.position(2);
sourceView.limit(6);

ByteBuffer slice = sourceView.slice();

// slice index 0..4 tương ứng parent index 2..6.
parent.put(0, slice, 0, 4);

System.out.println(new String(storage, StandardCharsets.US_ASCII));
// CDEFEFGH
```

Vùng nguồn trong slice là `CDEF`; vùng đích trong parent là [0, 4). Kết quả là `CDEFEFGH`. Position và limit của parent, sourceView và slice không thay đổi do absolute put.

Khi đọc code có nhiều view, luôn ghi rõ hệ chỉ số của từng buffer. Một chỉ số 0 có thể chỉ byte đầu của slice nhưng không phải byte đầu của mảng gốc.

## 6. Dùng compact để giữ byte chưa xử lý

`compact()` là thao tác buffer hữu ích trong xử lý I/O theo từng phần. Nó copy các byte còn lại từ `position` đến `limit - 1` về đầu buffer, rồi:

- Đặt position bằng số byte đã giữ lại.
- Đặt limit bằng capacity.
- Bỏ mark đã đặt trước đó.
- Giữ nguyên các byte còn lại theo thứ tự ban đầu.

Nếu vùng nguồn và vùng đích chồng lấn, `compact()` vẫn thực hiện việc dồn dữ liệu theo đúng hợp đồng của nó. Caller không cần tự copy từng byte.

### 6.1. Ví dụ sau một lần đọc/ghi chưa hoàn tất

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class CompactBufferDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(8);

        buffer.put("ABCDEF".getBytes(StandardCharsets.US_ASCII));
        buffer.flip();

        buffer.position(2); // A, B đã xử lý; C, D, E, F còn lại.
        buffer.compact();

        System.out.println(buffer.position()); // 4
        System.out.println(buffer.limit());    // 8

        buffer.put("GH".getBytes(StandardCharsets.US_ASCII));
        buffer.flip();

        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);

        System.out.println(new String(result, StandardCharsets.US_ASCII));
        // CDEFGH
    }
}
```

Sau `compact()`, bốn byte `CDEF` được dồn về đầu buffer. Position thành 4 để lần ghi tiếp theo tiếp tục ngay sau dữ liệu còn lại. Khi ghi `GH` rồi flip, buffer chứa chuỗi `CDEFGH` để xử lý tiếp.

Đây là mô hình thường gặp khi đọc từ channel nhưng lần ghi ra channel khác chỉ ghi được một phần. Sau khi ghi phần đã xử lý, compact giữ lại phần chưa ghi để lần I/O tiếp tục.

### 6.2. Chọn compact hay absolute put

Dùng `compact()` khi mục tiêu là giữ toàn bộ byte còn lại và chuẩn bị buffer cho lần ghi tiếp theo. Dùng absolute put khi cần di chuyển một vùng xác định mà không muốn thay đổi position/limit.

Không gọi `clear()` nếu cần giữ byte chưa xử lý: clear chỉ đặt lại position và limit, nó không xóa nội dung nhưng làm trạng thái buffer coi toàn capacity là vùng có thể ghi.

## 7. Kiểm chứng dữ liệu sau sao chép

Một thao tác copy thành công không tự chứng minh vùng đích chứa đúng byte mong muốn. Kiểm chứng nên so sánh kết quả với snapshot được chụp trước khi ghi.

Một quy trình đáng tin cậy:

1. Xác định chính xác source range và destination range.
2. Chụp byte nguồn vào mảng tạm trước khi copy.
3. Thực hiện copy.
4. Đọc lại vùng đích bằng chỉ số tuyệt đối hoặc view riêng.
5. So sánh byte thực tế với snapshot.
6. Kiểm tra vùng lân cận không bị ghi ngoài phạm vi.
7. Kiểm tra position và limit có giữ đúng hợp đồng hay không.

Ví dụ dùng mảng tạm:

```java
byte[] expected = new byte[length];

for (int i = 0; i < length; i++) {
    expected[i] = source.get(sourceOffset + i);
}

destination.put(destinationIndex, source, sourceOffset, length);

byte[] actual = new byte[length];

for (int i = 0; i < length; i++) {
    actual[i] = destination.get(destinationIndex + i);
}

if (!java.util.Arrays.equals(expected, actual)) {
    throw new IllegalStateException("Buffer copy verification failed");
}
```

Snapshot phải được tạo trước khi copy. Nếu tạo expected sau khi vùng nhớ đã bị ghi, test có thể chỉ so sánh dữ liệu với chính kết quả sai.

### 7.1. Kiểm tra vùng đích và byte lân cận

Ngoài vùng đích, có thể kiểm tra byte ngay trước và ngay sau vùng ghi để phát hiện ghi tràn:

```java
byte before = destination.get(destinationIndex - 1);
byte after = destination.get(destinationIndex + length);

destination.put(destinationIndex, source, sourceOffset, length);

if (destination.get(destinationIndex - 1) != before
        || destination.get(destinationIndex + length) != after) {
    throw new IllegalStateException("Copy modified bytes outside destination range");
}
```

Chỉ thực hiện phép kiểm tra này khi các chỉ số lân cận nằm trong limit và không thuộc một vùng khác được phép thay đổi. Trong một test có cả snapshot vùng đích, hãy gọi thao tác copy một lần rồi kiểm tra đồng thời expected bytes và hai byte lân cận.

### 7.2. Không phụ thuộc vào array()

Không phải buffer nào cũng có backing array truy cập được. Direct buffer và read-only buffer có thể không hỗ trợ `array()` hoặc `arrayOffset()`. Khi viết code dùng chung cho heap/direct buffer, hãy kiểm tra dữ liệu bằng `get(index)`, `duplicate()` hoặc chuyển vùng cần kiểm tra sang mảng riêng.

Không dùng `array()` như điều kiện bắt buộc của thuật toán copy. Absolute put hoạt động theo hợp đồng ByteBuffer mà không yêu cầu caller truy cập trực tiếp mảng nền.

## 8. Kiểm thử overlap bằng JUnit 5

Test nên kiểm tra đồng thời byte được copy và trạng thái buffer. Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class OverlappingBufferCopyTest {
    @Test
    void copiesForwardOverlappingRegionFromOriginalSourceBytes() {
        byte[] storage =
                "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

        ByteBuffer destination = ByteBuffer.wrap(storage);
        ByteBuffer source = destination.duplicate();

        byte[] expected = new byte[6];
        for (int i = 0; i < expected.length; i++) {
            expected[i] = source.get(i);
        }

        int destinationPosition = destination.position();
        int sourcePosition = source.position();
        int destinationLimit = destination.limit();
        int sourceLimit = source.limit();

        destination.put(2, source, 0, expected.length);

        assertArrayEquals(
                expected,
                Arrays.copyOfRange(storage, 2, 8)
        );
        assertArrayEquals(
                "ABABCDEF".getBytes(StandardCharsets.US_ASCII),
                storage
        );

        assertEquals(destinationPosition, destination.position());
        assertEquals(sourcePosition, source.position());
        assertEquals(destinationLimit, destination.limit());
        assertEquals(sourceLimit, source.limit());
    }
}
```

Test chụp sáu byte nguồn trước khi copy, rồi xác minh vùng đích có đúng sáu byte ban đầu hay không. Nó cũng xác minh position và limit của hai view không thay đổi.

### 8.1. Kiểm tra overlap theo hướng ngược

```java
@Test
void copiesBackwardOverlappingRegion() {
    byte[] storage =
            "ABCDEFGH".getBytes(StandardCharsets.US_ASCII);

    ByteBuffer destination = ByteBuffer.wrap(storage);
    ByteBuffer source = destination.duplicate();

    destination.put(0, source, 2, 6);

    assertArrayEquals(
            "CDEFGHGH".getBytes(StandardCharsets.US_ASCII),
            storage
    );
}
```

Method này là một test bổ sung trong cùng class `OverlappingBufferCopyTest`. Nó xác minh trường hợp đích nằm trước nguồn.

### 8.2. Kiểm tra range không hợp lệ

Vùng copy phải nằm hoàn toàn trong limit của cả hai buffer. Nếu đích không đủ chỗ hoặc source range vượt limit, absolute put ném `IndexOutOfBoundsException`.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.ByteBuffer;
import org.junit.jupiter.api.Test;

class BufferRangeValidationTest {
    @Test
    void rejectsDestinationRangeBeyondLimit() {
        ByteBuffer destination = ByteBuffer.allocate(8);
        ByteBuffer source = ByteBuffer.wrap(new byte[] { 1, 2, 3, 4, 5 });

        assertThrows(
                IndexOutOfBoundsException.class,
                () -> destination.put(5, source, 0, 4)
        );
    }
}
```

Destination limit là 8, bắt đầu ở index 5 nhưng copy 4 byte sẽ vượt qua limit. Phương thức từ chối range trước khi thực hiện copy.

### 8.3. Kiểm tra destination read-only

Absolute put là thao tác ghi. Nếu destination là read-only buffer, phương thức ném `ReadOnlyBufferException`:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import org.junit.jupiter.api.Test;

class ReadOnlyBufferCopyTest {
    @Test
    void rejectsReadOnlyDestination() {
        ByteBuffer source = ByteBuffer.wrap(new byte[] { 1, 2, 3 });
        ByteBuffer destination = ByteBuffer.allocate(3).asReadOnlyBuffer();

        assertThrows(
                ReadOnlyBufferException.class,
                () -> destination.put(0, source, 0, 3)
        );
    }
}
```

Source có thể là read-only vì thao tác chỉ đọc dữ liệu từ source. Điều kiện ghi được kiểm tra trên destination.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự copy từng byte theo chiều tiến trong vùng overlap | Byte nguồn bị ghi đè trước khi đọc | Dùng absolute bulk put Java 16 hoặc snapshot tạm |
| Nghĩ duplicate tạo bản sao nội dung độc lập | Ghi ở view này xuất hiện ở view kia | Nhớ duplicate chia sẻ backing memory |
| Dùng index của parent cho slice | Đọc/ghi sai vị trí vì slice có hệ chỉ số riêng | Tính index tương đối với view đang truyền |
| Nghĩ absolute put thay đổi position | Logic đọc tiếp bị lệch | Absolute put không đổi position |
| Dùng capacity để kiểm tra range | Có thể ghi vượt limit | Kiểm tra index/offset/length theo limit |
| Gọi array() trên direct/read-only buffer | Có thể nhận UnsupportedOperationException | Dùng get(index) hoặc view để kiểm chứng |
| Dùng clear() khi muốn giữ dữ liệu chưa xử lý | Trạng thái buffer mất ranh giới vùng remaining | Dùng compact() |
| Chỉ kiểm tra tổng số byte hoặc checksum | Có thể không phát hiện vị trí byte bị hoán đổi trong một số trường hợp | So sánh chính xác vùng đích với snapshot |
| Cho rằng overlap-safe đồng nghĩa thread-safe | Thread khác vẫn có thể đọc/ghi đồng thời | Đồng bộ hoặc chuyển quyền sở hữu buffer |

## 10. Lưu ý về tính đúng đắn và đồng thời

Overlap-safe là bảo đảm về kết quả của một thao tác copy khi source và destination chia sẻ memory. Nó không có nghĩa thao tác là atomic đối với thread khác, cũng không biến `ByteBuffer` thành cấu trúc thread-safe.

Nếu nhiều thread cùng truy cập vùng nhớ:

- Dùng cơ chế đồng bộ hoặc quy tắc ownership rõ ràng.
- Không để một thread sửa source trong khi thread khác đang copy.
- Không giả định việc kiểm tra checksum sau copy thay thế được đồng bộ bộ nhớ.
- Với dữ liệu chia sẻ qua direct buffer hoặc memory-mapped buffer, xác định rõ ai chịu trách nhiệm đọc, ghi và vòng đời vùng nhớ.

Byte copy cũng không diễn giải byte thành số. Nếu copy dữ liệu nhị phân có nhiều byte, thứ tự byte được giữ nguyên; `ByteOrder` chỉ ảnh hưởng cách các thao tác typed như `getInt()` hoặc `putLong()` diễn giải/ghi giá trị nhiều byte.

### 10.1. Checksum có vai trò gì?

Checksum hoặc hash có thể hữu ích khi kiểm tra một payload lớn qua ranh giới I/O hoặc lưu trữ. Tuy nhiên, với unit test vùng copy nhỏ, so sánh từng byte hoặc mảng byte thường trực tiếp và dễ chẩn đoán hơn.

Checksum chỉ kiểm tra dấu vết dữ liệu theo thuật toán đã chọn; checksum không chứng minh dữ liệu đến từ nguồn đáng tin cậy. Nếu cần tính toàn vẹn chống sửa đổi có chủ đích, cần cơ chế xác thực như MAC hoặc chữ ký số phù hợp.

## 11. Checklist sao chép buffer chồng lấn

Trước khi copy, hãy kiểm tra:

1. Source và destination có thể chia sẻ cùng backing memory không?
2. Đã xác định đúng index theo hệ chỉ số của từng view chưa?
3. Source range có nằm trong source limit không?
4. Destination range có nằm trong destination limit không?
5. Cần relative put hay absolute put?
6. Nếu cần copy vùng tuyệt đối, runtime có phải Java 16 trở lên không?
7. Có cần giữ nguyên position và limit không?
8. Destination có phải read-only không?
9. Có snapshot expected bytes trước thao tác để kiểm chứng không?
10. Đã kiểm tra cả overlap tiến, overlap lùi và byte lân cận chưa?
11. Có buffer nào được truy cập đồng thời bởi thread khác không?
12. Dữ liệu cần so sánh byte chính xác hay cần kiểm tra thêm semantics như encoding/byte order?

## 12. Bài tập vận dụng

**Bài 1 — Copy tiến:** Tạo buffer chứa `ABCDEFGH`. Dùng `duplicate()` rồi gọi `put(2, source, 0, 6)`. Dự đoán và xác minh nội dung cuối cùng.

**Bài 2 — Copy lùi:** Dùng cùng dữ liệu nhưng copy vùng [2, 8) về [0, 6). Viết assertion cho toàn bộ backing array.

**Bài 3 — Slice index:** Tạo duplicate, đặt position 2 và limit 6, sau đó tạo slice. Copy bốn byte từ slice về parent. Vẽ bảng ánh xạ chỉ số giữa parent và slice.

**Bài 4 — compact:** Tạo buffer có sáu byte, đọc hoặc đánh dấu hai byte đầu đã xử lý, gọi compact rồi ghi thêm hai byte. Xác minh thứ tự dữ liệu sau flip.

**Bài 5 — Kiểm chứng range:** Viết test cho source range vượt limit, destination range vượt limit và destination read-only. Kiểm tra nội dung không bị thay đổi khi range không hợp lệ.

---

## Tài liệu tham khảo

- [ByteBuffer — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html): absolute bulk `put(int, ByteBuffer, int, int)`, overlap semantics, `duplicate`, `slice` và `compact`.
- [Buffer — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/Buffer.html): position, limit, capacity, remaining và trạng thái buffer.
- [ByteBuffer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html): xác nhận absolute bulk put và overlap semantics tiếp tục có trong Java hiện đại.
- [Buffer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/Buffer.html): API buffer hiện hành và các quy tắc chỉ số.

---

**Ghi nhớ:** Java 16 bổ sung absolute bulk `ByteBuffer.put(index, src, offset, length)`. Khi source và destination chia sẻ memory, kết quả như thể source được chụp vào vùng tạm trước khi ghi, nên copy overlap an toàn mà không phải tự chọn hướng. Absolute put giữ nguyên position/limit; hãy xác minh vùng đích bằng snapshot byte và luôn tính chỉ số theo đúng view đang sử dụng.
