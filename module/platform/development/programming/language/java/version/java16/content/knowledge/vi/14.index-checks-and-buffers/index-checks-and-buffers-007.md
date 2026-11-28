# `ByteBuffer.put(index, src, offset, length)` bổ sung từ Java 16

Java 16 bổ sung overload `ByteBuffer.put(int index, ByteBuffer src, int offset, int length)` để sao chép một vùng byte từ buffer nguồn vào vị trí chỉ định của buffer đích. Đây là thao tác *absolute bulk put*: cả vị trí ghi ở buffer đích và vị trí đọc ở buffer nguồn đều được truyền tường minh, nên phương thức không thay đổi `position` của hai buffer.

API này hữu ích khi xử lý packet, header, frame hoặc vùng dữ liệu có cấu trúc, nơi cần sao chép một đoạn byte mà vẫn giữ nguyên trạng thái đọc/ghi hiện tại của các buffer. Cần nhớ rằng `index` và `offset` là chỉ số tuyệt đối tính từ đầu buffer và phạm vi hợp lệ được giới hạn bởi `limit()`, không phải `capacity()` hay `remaining()`.

## 1. Chữ ký và ý nghĩa các tham số

```java
public ByteBuffer put(int index, ByteBuffer src, int offset, int length)
```

| Tham số | Ý nghĩa |
| --- | --- |
| `index` | Chỉ số byte đầu tiên sẽ được ghi trong buffer đích (`this`). |
| `src` | Buffer nguồn cung cấp byte. Không được là chính buffer đích. |
| `offset` | Chỉ số byte đầu tiên được đọc trong buffer nguồn. |
| `length` | Số byte cần sao chép. |

Ví dụ, lời gọi:

```java
destination.put(2, source, 4, 3);
```

đọc ba byte tại các chỉ số `4`, `5`, `6` của `source`, rồi ghi vào các chỉ số `2`, `3`, `4` của `destination`.

Phương thức trả về chính buffer đích, nên có thể nối lời gọi nếu cần. Nó không tạo một `byte[]` trung gian trong mã ứng dụng và có thể được implementation tối ưu hiệu quả hơn vòng lặp sao chép từng byte. Tuy nhiên, API không cam kết đây là zero-copy; dữ liệu vẫn được sao chép từ vùng nguồn sang vùng đích.

## 2. Ví dụ cơ bản: sao chép một đoạn byte mà không đổi position

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

class AbsoluteBulkPutExample {
    public static void main(String[] args) {
        ByteBuffer source = ByteBuffer.wrap(
            "ABCDEF".getBytes(StandardCharsets.US_ASCII)
        );
        source.position(4);

        ByteBuffer destination = ByteBuffer.allocate(8);
        destination.position(6);

        destination.put(1, source, 1, 3);

        System.out.println((char) destination.get(1)); // B
        System.out.println((char) destination.get(2)); // C
        System.out.println((char) destination.get(3)); // D
        System.out.println(source.position());         // 4
        System.out.println(destination.position());    // 6
    }
}
```

Lời gọi sao chép các byte tại chỉ số `1` đến `3` của `source`, tương ứng `B`, `C`, `D`, vào chỉ số `1` đến `3` của `destination`. Dù `source.position()` đang là `4` và `destination.position()` đang là `6`, hai giá trị này không tham gia xác định vùng sao chép và không thay đổi sau lời gọi.

Điều này rất hữu ích khi một thành phần đang quản lý `position` để đọc hoặc ghi tuần tự, nhưng một thao tác phụ cần cập nhật một vùng cố định ở nơi khác trong buffer.

## 3. `offset` không phải `source.position()` và `index` không phải `destination.position()`

Đây là khác biệt quan trọng nhất của overload mới. Các tham số `index` và `offset` là chỉ số tuyệt đối:

- `offset` tính từ chỉ số `0` của buffer nguồn, không tính từ `source.position()`.
- `index` tính từ chỉ số `0` của buffer đích, không tính từ `destination.position()`.
- Việc sao chép không tự tăng position của nguồn hoặc đích.

Trong ví dụ phần trước, `source.position()` là `4`, nhưng `offset` truyền vào là `1`. Vì vậy byte đầu tiên được đọc là `source.get(1)`, tức `B`, không phải byte tại position hiện tại là `E`.

Nếu muốn sao chép dữ liệu bắt đầu từ position hiện tại của nguồn, hãy truyền position đó làm offset một cách tường minh:

```java
import java.nio.ByteBuffer;

int sourceOffset = source.position();
int count = source.remaining();
int destinationIndex = 0;

destination.put(destinationIndex, source, sourceOffset, count);
```

Đoạn mã trên sao chép vùng `source` hiện còn lại vào đầu buffer đích, nhưng vẫn giữ nguyên position của cả hai buffer. Nếu cần tiêu thụ nguồn theo cách thông thường, hãy dùng overload tương đối `destination.put(source)` thay vì overload tuyệt đối.

Vì position của destination không tự tăng, đừng gọi `flip()` với giả định nó sẽ tự nhận biết vùng vừa được ghi bằng absolute put. Ví dụ, nếu buffer đang có position bằng `0` và ghi vào index `5`, gọi `flip()` ngay sau đó sẽ đặt limit về `0`; vùng byte ở index `5` không thể được đọc bằng thao tác tương đối. Hãy thiết lập vùng đọc một cách tường minh:

```java
import java.nio.ByteBuffer;

ByteBuffer view = destination.duplicate();
view.position(destinationIndex);
view.limit(destinationIndex + length);

while (view.hasRemaining()) {
    byte value = view.get();
    // Xử lý byte
}
```

`duplicate()` cho một position/limit độc lập nhưng vẫn chia sẻ nội dung với destination. Vì vậy, việc duyệt `view` không làm thay đổi position của buffer gốc.

## 4. Phạm vi được kiểm tra theo limit, không theo capacity

Một `ByteBuffer` có ba khái niệm trạng thái:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity` | Số byte tối đa mà buffer có thể chứa; không đổi sau khi tạo. |
| `limit` | Chỉ số giới hạn mà thao tác đọc/ghi không được vượt qua. |
| `position` | Chỉ số mà thao tác tương đối tiếp theo sẽ đọc hoặc ghi. |

Với `put(index, src, offset, length)`, hai vùng phải nằm trong giới hạn hiện hành:

```text
Buffer nguồn:    [0 ........ offset ........ offset + length ........ limit]
                                  |<--- length --->|

Buffer đích:     [0 ........ index .......... index + length ........ limit]
                                  |<--- length --->|
```

Điều kiện thực tế:

- `index` và `length` phải xác định một vùng nằm trong `[0, destination.limit())`.
- `offset` và `length` phải xác định một vùng nằm trong `[0, source.limit())`.
- `length` không được âm.
- Không dùng `capacity()` làm căn cứ duy nhất: buffer có thể đã được giới hạn bằng `limit()` nhỏ hơn capacity.

Ví dụ buffer có capacity 16 nhưng limit 8 chỉ cho phép vùng ghi kết thúc không vượt quá chỉ số 8. Ghi vào chỉ số 10 vẫn không hợp lệ dù bộ nhớ vật lý của buffer còn đủ capacity.

```java
import java.nio.ByteBuffer;

ByteBuffer destination = ByteBuffer.allocate(16);
destination.limit(8);

ByteBuffer source = ByteBuffer.wrap(new byte[] { 1, 2, 3, 4 });

destination.put(5, source, 0, 3); // Hợp lệ: vùng đích [5, 8)
// destination.put(6, source, 0, 3); // IndexOutOfBoundsException: [6, 9) vượt limit 8
```

## 5. Phương thức tuyệt đối khác với `put(ByteBuffer src)` tương đối

Hai overload phục vụ hai cách quản lý trạng thái khác nhau:

```java
destination.put(source);
```

`put(source)` tương đối sao chép các byte còn lại từ `source.position()` đến `source.limit()` vào vị trí hiện tại của destination. Sau khi thành công, position của cả hai buffer tăng theo số byte đã sao chép.

Ngược lại:

```java
destination.put(destinationIndex, source, sourceOffset, length);
```

Overload tuyệt đối sao chép đúng vùng được chỉ định, không phụ thuộc position hiện tại và không thay đổi position của hai buffer.

| Tiêu chí | `put(ByteBuffer src)` | `put(index, src, offset, length)` |
| --- | --- | --- |
| Cách xác định vùng nguồn | Từ `src.position()` đến `src.limit()` | Từ `offset` với độ dài `length` |
| Cách xác định vùng đích | Bắt đầu tại `this.position()` | Bắt đầu tại `index` |
| Thay đổi source position | Có, tăng theo số byte đọc | Không |
| Thay đổi destination position | Có, tăng theo số byte ghi | Không |
| Dùng khi | Muốn tiêu thụ dữ liệu tuần tự | Muốn sao chép một vùng cố định, giữ nguyên trạng thái buffer |

Chọn overload theo ý nghĩa của thao tác. Không thay `put(source)` bằng overload tuyệt đối nếu code đang dựa vào việc position được cập nhật để đánh dấu dữ liệu đã tiêu thụ.

## 6. Ứng dụng: chèn payload vào vùng cố định của packet

Giả sử buffer đích dành tám byte đầu cho header và phần payload bắt đầu tại offset 8. Một buffer nguồn chứa nhiều trường, nhưng packet hiện tại chỉ cần sao chép một vùng con:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

class PacketBuilder {
    static ByteBuffer build(ByteBuffer payloadSource, int payloadOffset, int payloadLength) {
        int headerLength = 8;
        ByteBuffer packet = ByteBuffer.allocate(headerLength + payloadLength);

        packet.put(0, (byte) 0x50); // Magic byte
        packet.put(1, (byte) 0x01); // Version
        packet.put(2, (byte) (payloadLength >>> 8));
        packet.put(3, (byte) payloadLength);

        packet.put(headerLength, payloadSource, payloadOffset, payloadLength);

        return packet;
    }

    public static void main(String[] args) {
        ByteBuffer source = ByteBuffer.wrap(
            "prefix:HELLO:suffix".getBytes(StandardCharsets.US_ASCII)
        );

        ByteBuffer packet = build(source, 7, 5);

        System.out.println((char) packet.get(8));  // H
        System.out.println((char) packet.get(12)); // O
        System.out.println(source.position());     // 0
    }
}
```

`PacketBuilder` ghi header bằng các absolute put đơn byte và chèn payload bằng absolute bulk put. Position của `payloadSource` vẫn giữ nguyên để caller có thể tiếp tục đọc hoặc dùng buffer cho một thao tác khác. Ví dụ chỉ minh họa bố cục byte; một protocol thực tế cần định nghĩa đầy đủ kích thước header, byte order, kiểm tra độ dài và quy tắc xác thực dữ liệu.

## 7. Các ngoại lệ cần xử lý

Phương thức kiểm tra vùng nguồn và vùng đích trước khi sao chép. Các lỗi quan trọng:

| Ngoại lệ | Trường hợp |
| --- | --- |
| `IndexOutOfBoundsException` | `index`, `offset` hoặc `length` âm; hoặc vùng nguồn/đích vượt quá `limit()`. |
| `ReadOnlyBufferException` | Buffer đích là read-only. Buffer nguồn read-only vẫn có thể đọc bình thường. |
| `IllegalArgumentException` | `src` chính là object buffer đích (`src == this`). |

Ví dụ kiểm tra buffer đích chỉ đọc:

```java
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;

ByteBuffer source = ByteBuffer.wrap(new byte[] { 10, 20, 30 });
ByteBuffer destination = ByteBuffer.allocate(8).asReadOnlyBuffer();

try {
    destination.put(0, source, 0, 3);
} catch (ReadOnlyBufferException exception) {
    System.out.println("Buffer đích không cho phép ghi");
}
```

Không nên dùng exception làm cách kiểm soát luồng thông thường. Hãy xác thực kích thước và trạng thái buffer trước khi thực hiện copy nếu dữ liệu đến từ input không đáng tin cậy.

## 8. Kiểm tra độ dài trước khi sao chép

Với dữ liệu đến từ network hoặc file, độ dài payload có thể không hợp lệ. Hãy kiểm tra bằng phép tính tránh tràn số nguyên và dùng `limit()` làm ranh giới:

```java
import java.nio.ByteBuffer;

class BufferCopy {
    static void copyRange(
            ByteBuffer destination,
            int destinationIndex,
            ByteBuffer source,
            int sourceOffset,
            int length) {

        if (length < 0
                || destinationIndex < 0
                || sourceOffset < 0
                || destinationIndex > destination.limit() - length
                || sourceOffset > source.limit() - length) {
            throw new IllegalArgumentException("Vùng sao chép không hợp lệ");
        }

        destination.put(destinationIndex, source, sourceOffset, length);
    }
}
```

Trong ví dụ, kiểm tra `length < 0` trước khi trừ để tránh trường hợp số âm làm điều kiện biên trở nên sai lệch. Sau kiểm tra, API vẫn tự xác thực các điều kiện của nó, bao gồm read-only destination và trường hợp source trùng object với destination.

Nếu dữ liệu đầu vào có thể bị thay đổi đồng thời bởi thread khác, việc kiểm tra rồi sao chép không tự tạo ra một snapshot nhất quán. Cần đồng bộ hóa quyền sở hữu buffer hoặc sao chép từ vùng dữ liệu đã được bảo vệ.

## 9. Buffer heap, direct, slice và duplicate

Overload này làm việc với `ByteBuffer`, nên có thể dùng với buffer heap hoặc direct:

```java
import java.nio.ByteBuffer;

ByteBuffer heap = ByteBuffer.allocate(1024);
ByteBuffer direct = ByteBuffer.allocateDirect(1024);

direct.put(0, heap, 0, 128);
```

`allocateDirect()` có thể hữu ích cho một số I/O native hoặc workload cần giảm chi phí trung gian, nhưng không mặc định nhanh hơn trong mọi trường hợp. Cần đo trên workload thật; API `put()` không cam kết zero-copy.

`slice()` và `duplicate()` tạo buffer mới về mặt object nhưng có thể chia sẻ vùng nhớ với buffer gốc. `slice()` có chỉ số 0 tương ứng với position của buffer gốc tại lúc tạo; `duplicate()` giữ cùng nội dung và trạng thái ban đầu nhưng có position/limit độc lập.

Vì các view có thể chia sẻ vùng nhớ, hãy cẩn thận nếu vùng nguồn và đích chồng lấn. Javadoc mô tả kết quả tương đương vòng lặp đọc từng byte tuyệt đối rồi ghi từng byte; do đó không giả định thao tác này có semantics như `memmove()` khi vùng nhớ chồng lấn. Nếu cần snapshot an toàn, hãy sao chép vùng nguồn sang một buffer tạm độc lập trước:

```java
import java.nio.ByteBuffer;

class OverlapSafeCopy {
    static void copyThroughTemporary(
            ByteBuffer destination,
            int destinationIndex,
            ByteBuffer source,
            int sourceOffset,
            int length) {

        if (length < 0
                || destinationIndex < 0
                || sourceOffset < 0
                || destinationIndex > destination.limit() - length
                || sourceOffset > source.limit() - length) {
            throw new IndexOutOfBoundsException("Vùng sao chép không hợp lệ");
        }

        ByteBuffer sourceView = source.duplicate();
        sourceView.position(sourceOffset);
        sourceView.limit(sourceOffset + length);

        ByteBuffer snapshot = ByteBuffer.allocate(length);
        snapshot.put(sourceView);
        snapshot.flip();

        destination.put(destinationIndex, snapshot, 0, length);
    }
}
```

Buffer tạm bảo đảm dữ liệu nguồn được chụp lại trước khi ghi vào vùng đích. Cần xác thực range trước khi thiết lập position/limit của `sourceView` và trước khi ghi vào destination.

## 10. Byte order không làm thay đổi byte được sao chép

`put(index, src, offset, length)` sao chép byte nguyên trạng. `ByteOrder.BIG_ENDIAN` hoặc `ByteOrder.LITTLE_ENDIAN` không làm đảo byte trong thao tác copy này. Byte order ảnh hưởng cách các thao tác đọc/ghi kiểu nhiều byte như `getInt()`, `putInt()`, `getLong()` diễn giải dữ liệu.

Ví dụ copy bốn byte từ buffer nguồn sang buffer đích không chuyển đổi thứ tự byte:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer source = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN);
source.putInt(0, 0x01020304);

ByteBuffer destination = ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN);
destination.put(0, source, 0, 4);

// Các byte được copy nguyên trạng: 04 03 02 01
```

Nếu protocol yêu cầu một byte order cụ thể, hãy đặt byte order phù hợp trước khi đọc hoặc ghi các giá trị số. Đừng mong đợi bulk byte copy tự chuyển đổi endianness.

## 11. Kiểm thử position, vùng byte và ngoại lệ

JUnit 5 có thể kiểm tra những bảo đảm quan trọng của overload này:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import org.junit.jupiter.api.Test;

class AbsoluteBulkPutTest {
    @Test
    void copiesSelectedRangeWithoutChangingPositions() {
        ByteBuffer source = ByteBuffer.wrap(new byte[] { 10, 20, 30, 40, 50 });
        source.position(4);

        ByteBuffer destination = ByteBuffer.allocate(8);
        destination.position(6);

        destination.put(2, source, 1, 3);

        assertEquals(4, source.position());
        assertEquals(6, destination.position());
        assertArrayEquals(new byte[] { 20, 30, 40 }, new byte[] {
            destination.get(2), destination.get(3), destination.get(4)
        });
    }

    @Test
    void rejectsDestinationRangeBeyondLimit() {
        ByteBuffer source = ByteBuffer.wrap(new byte[] { 1, 2, 3 });
        ByteBuffer destination = ByteBuffer.allocate(8);
        destination.limit(4);

        assertThrows(IndexOutOfBoundsException.class,
            () -> destination.put(2, source, 0, 3));
    }

    @Test
    void rejectsReadOnlyDestination() {
        ByteBuffer source = ByteBuffer.wrap(new byte[] { 1 });
        ByteBuffer destination = ByteBuffer.allocate(4).asReadOnlyBuffer();

        assertThrows(ReadOnlyBufferException.class,
            () -> destination.put(0, source, 0, 1));
    }

    @Test
    void rejectsTheSameBufferAsSourceAndDestination() {
        ByteBuffer buffer = ByteBuffer.allocate(4);

        assertThrows(IllegalArgumentException.class,
            () -> buffer.put(1, buffer, 0, 2));
    }
}
```

Các test trên xác minh hành vi công khai: vùng byte được copy, position không đổi, giới hạn được kiểm tra và các trường hợp không hợp lệ bị từ chối. Không kiểm tra lớp triển khai nội bộ của buffer.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Truyền `source.position()` nhưng lại nghĩ `offset` tự tính từ position | Có thể copy nhầm vùng dữ liệu. | Tính offset rõ ràng; tham số là chỉ số tuyệt đối. |
| Dùng `destination.position()` như thể API tự tăng position | Ghi nhầm vùng đích hoặc làm sai trạng thái buffer. | Truyền `index` rõ ràng và tự quản lý position nếu cần. |
| Kiểm tra theo `capacity()` thay vì `limit()` | Có thể ghi vượt giới hạn hiện hành. | Kiểm tra cả vùng nguồn và đích theo `limit()`. |
| Mong `put(index, src, offset, length)` tiêu thụ source | Các lần đọc tiếp theo vẫn thấy position cũ. | Dùng relative `put(src)` nếu cần tiêu thụ dữ liệu. |
| Cho buffer đích read-only | Ném `ReadOnlyBufferException`. | Dùng buffer có quyền ghi. |
| Truyền chính buffer đích làm nguồn | Ném `IllegalArgumentException`. | Dùng buffer nguồn riêng; cẩn thận với view chia sẻ bộ nhớ. |
| Mong byte order chuyển đổi dữ liệu khi copy | Byte vẫn được sao chép nguyên trạng. | Chuyển đổi giá trị bằng typed get/put nếu protocol yêu cầu. |
| Cho rằng API bảo đảm zero-copy | Hiểu sai chi phí và hiệu năng. | Xem đây là bulk copy có thể được tối ưu; đo trên workload thật. |

## 13. Những điểm cần nhớ

- Overload `put(int index, ByteBuffer src, int offset, int length)` được bổ sung từ Java 16.
- `index` và `offset` là chỉ số tuyệt đối, không tính từ position.
- Phạm vi copy phải nằm trong `limit()` của cả buffer nguồn và buffer đích.
- Phương thức không thay đổi position của hai buffer.
- `put(ByteBuffer src)` tương đối tiêu thụ phần remaining và tăng position của cả hai buffer.
- Buffer đích read-only gây `ReadOnlyBufferException`; source không được là chính destination.
- Byte được copy nguyên trạng, không chuyển đổi theo byte order.
- Cẩn thận với slice/duplicate chia sẻ vùng nhớ và vùng copy chồng lấn.
- API hỗ trợ bulk copy hiệu quả nhưng không cam kết zero-copy.

Hãy dùng absolute bulk put khi cần sao chép một vùng byte xác định mà không làm thay đổi trạng thái đọc/ghi tuần tự của buffer. Khi cần tiêu thụ dữ liệu theo position, dùng overload tương đối; khi cần xử lý vùng nhớ chồng lấn, tạo snapshot tạm và xác thực phạm vi trước khi copy.

## Tài liệu tham khảo

- [ByteBuffer.put(int, ByteBuffer, int, int) – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html#put(int,java.nio.ByteBuffer,int,int))
- [ByteBuffer – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html)
- [Buffer – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/Buffer.html)
- [ByteOrder – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteOrder.html)
