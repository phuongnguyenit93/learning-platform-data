# Kiểm thử buffer read-only, sai chỉ số, vùng rỗng và dữ liệu nhị phân

Khi làm việc với ByteBuffer, một test tốt cần xác nhận cả dữ liệu lẫn trạng thái của buffer. Các trường hợp dễ bị bỏ sót gồm buffer chỉ đọc, index vượt limit dù chưa vượt capacity, vùng sao chép có length bằng 0, byte có giá trị lớn hơn 127 và dữ liệu nhiều byte phụ thuộc byte order. Nếu chỉ kiểm tra một kết quả đọc thành công, lỗi ở ranh giới có thể xuất hiện muộn trong lúc parse packet hoặc xử lý dữ liệu nhị phân.

ByteBuffer và các API absolute access hiện hành vẫn được dùng rộng rãi trên JDK hiện đại. Bài học này trình bày cách kiểm thử các trường hợp đó bằng JUnit Jupiter, phân biệt thao tác absolute với relative, và tạo dữ liệu nhị phân xác định mà không phụ thuộc vào backing array.

## 1. Những trạng thái cần kiểm tra của ByteBuffer

Một buffer có bốn thuộc tính trạng thái thường ảnh hưởng đến thao tác:

| Thuộc tính | Vai trò | Câu hỏi khi viết test |
|---|---|---|
| capacity | Số phần tử tối đa mà buffer được tạo để chứa | Buffer có bao nhiêu byte được cấp phát? |
| limit | Ranh giới hiện tại của vùng có thể đọc/ghi | Index có nằm trước limit không? |
| position | Vị trí của thao tác relative tiếp theo | Thao tác có làm position thay đổi không? |
| mark | Vị trí đã lưu để reset | Mark có còn hợp lệ sau thao tác không? |

Với absolute get/put, index được truyền trực tiếp và position không được dùng làm điểm bắt đầu. Với relative get/put, thao tác bắt đầu tại position và thường tăng position sau khi thành công.

Limit quan trọng hơn capacity khi xác minh chỉ số. Ví dụ buffer có capacity 16 nhưng limit bằng 5 thì index 5 không phải vị trí đọc hợp lệ, dù vùng nhớ vẫn được cấp phát.

## 2. Read-only buffer cho phép đọc nhưng cấm ghi qua view đó

Có thể tạo read-only view bằng asReadOnlyBuffer():

~~~java
ByteBuffer writable = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40});
ByteBuffer readOnly = writable.asReadOnlyBuffer();

System.out.println(readOnly.isReadOnly()); // true
System.out.println(readOnly.get(1));       // 20
readOnly.put(1, (byte) 99);                // ReadOnlyBufferException
~~~

Read-only buffer vẫn hỗ trợ các thao tác đọc như get(), get(index), bulk get và đọc kiểu dữ liệu như getInt(). Các thao tác làm thay đổi nội dung qua chính read-only view sẽ ném ReadOnlyBufferException.

Read-only là quyền truy cập của view, không phải bản sao bất biến của dữ liệu. Nếu buffer gốc vẫn có thể ghi và một phần khác của chương trình sửa nội dung qua buffer gốc, read-only view sẽ nhìn thấy thay đổi đó vì hai view chia sẻ vùng nhớ.

Ví dụ:

~~~java
ByteBuffer original = ByteBuffer.wrap(new byte[] {1, 2, 3});
ByteBuffer readOnly = original.asReadOnlyBuffer();

original.put(0, (byte) 9);

System.out.println(readOnly.get(0)); // 9
~~~

Do đó, read-only buffer ngăn caller ghi thông qua reference đó, nhưng không bảo đảm dữ liệu nền không bao giờ thay đổi. Nếu cần snapshot độc lập, hãy sao chép dữ liệu sang buffer hoặc array riêng và kiểm soát quyền sở hữu bản sao.

## 3. Kiểm thử đọc thành công và ghi bị từ chối

Test nên chứng minh read-only view vẫn đọc được dữ liệu và từ chối từng loại thao tác ghi quan trọng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import org.junit.jupiter.api.Test;

class ReadOnlyBufferTest {
    @Test
    void allowsReadsAndRejectsWrites() {
        ByteBuffer source = ByteBuffer.wrap(
                new byte[] {10, 20, 30, 40});
        ByteBuffer readOnly = source.asReadOnlyBuffer();

        assertTrue(readOnly.isReadOnly());
        assertEquals(20, readOnly.get(1));

        assertThrows(ReadOnlyBufferException.class,
                () -> readOnly.put(1, (byte) 99));
        assertThrows(ReadOnlyBufferException.class,
                () -> readOnly.put((byte) 99));
    }
}
~~~

Trong test này, absolute put và relative put đều phải bị từ chối. Nên tách các assertion nếu muốn xác định rõ API ghi nào đã vô tình được gọi trong code production.

Một read-only buffer vẫn có thể làm nguồn cho một buffer đích có quyền ghi:

~~~java
ByteBuffer source = ByteBuffer.wrap(new byte[] {4, 5, 6})
        .asReadOnlyBuffer();
ByteBuffer target = ByteBuffer.allocate(3);

target.put(source);
~~~

Đây là thao tác hợp lệ vì chương trình chỉ đọc từ source và ghi vào target. Quyền read-only không ngăn buffer được dùng làm nguồn dữ liệu.

## 4. Index hợp lệ được xác định theo limit

Với absolute get(index), điều kiện cơ bản là:

- index không âm.
- index nhỏ hơn limit.

Nếu index âm hoặc index bằng/vượt limit, thao tác ném IndexOutOfBoundsException. Capacity không làm thay đổi quy tắc này.

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.limit(3);

buffer.get(2); // Hợp lệ
buffer.get(3); // IndexOutOfBoundsException
~~~

Có thể kiểm thử rõ trường hợp capacity còn lớn nhưng limit đã thu hẹp:

~~~java
@Test
void absoluteReadUsesLimitRatherThanCapacity() {
    ByteBuffer buffer = ByteBuffer.allocate(8);
    buffer.put(0, (byte) 11);
    buffer.put(1, (byte) 22);
    buffer.put(2, (byte) 33);
    buffer.limit(3);

    assertEquals(33, buffer.get(2));
    assertThrows(IndexOutOfBoundsException.class,
            () -> buffer.get(3));
}
~~~

Đặt limit trước khi đọc giúp test mô phỏng đúng vùng dữ liệu hợp lệ đã được parse hoặc nhận từ bên ngoài.

## 5. Phân biệt lỗi index và lỗi thiếu dữ liệu

Hai loại thao tác có điều kiện lỗi khác nhau:

| Thao tác | Trường hợp lỗi | Exception thường gặp |
|---|---|---|
| Absolute get(index) | index âm hoặc index >= limit | IndexOutOfBoundsException |
| Absolute bulk get(index, dst, offset, length) | vùng nguồn hoặc vùng đích không hợp lệ | IndexOutOfBoundsException |
| Relative get() | remaining bằng 0 | BufferUnderflowException |
| Relative bulk get(dst, offset, length) | length lớn hơn remaining | BufferUnderflowException |
| Relative put(byte) | remaining bằng 0 | BufferOverflowException |
| Ghi vào read-only buffer | buffer không cho phép ghi | ReadOnlyBufferException |

Ví dụ:

~~~java
@Test
void distinguishesAbsoluteIndexFailureFromRelativeUnderflow() {
    ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2});

    assertThrows(IndexOutOfBoundsException.class,
            () -> buffer.get(buffer.limit()));

    buffer.position(buffer.limit());
    assertThrows(java.nio.BufferUnderflowException.class,
            buffer::get);
}
~~~

Không nên bắt tất cả các exception này rồi chuyển thành một kết quả rỗng. Index sai thường là lỗi lập trình hoặc dữ liệu không hợp lệ; underflow có thể có nghĩa là chưa nhận đủ dữ liệu để parse một cấu trúc hoàn chỉnh.

## 6. Kiểm tra vùng absolute bulk get

Từ Java 13, ByteBuffer có overload absolute bulk get cho phép đọc một vùng bắt đầu tại index vào một vùng trong byte array:

~~~java
buffer.get(index, destinationArray, offset, length);
~~~

Phương thức đọc length byte:

- Từ buffer bắt đầu tại index.
- Ghi vào array bắt đầu tại offset.
- Không thay đổi position của buffer.

Phạm vi cần thỏa mãn:

~~~java
length <= buffer.limit() - index
length <= destinationArray.length - offset
~~~

Sau khi đã xác nhận index và offset không âm, dạng kiểm tra dùng phép trừ giúp tránh tràn số khi cộng index + length.

Ví dụ:

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50});
buffer.position(2);
buffer.limit(4);

byte[] output = new byte[3];
buffer.get(1, output, 1, 2);
~~~

Hai byte tại buffer index 1 và 2 được ghi vào output index 1 và 2. Position của buffer vẫn bằng 2; phần tử output index 0 không bị thay đổi.

## 7. Kiểm thử sai index, offset và length

Test nên bao phủ cả hai phía của thao tác bulk: vùng đọc trong buffer và vùng ghi trong array.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.ByteBuffer;
import org.junit.jupiter.api.Test;

class BufferRangeTest {
    @Test
    void rejectsInvalidSourceIndexAndLength() {
        ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
        byte[] destination = new byte[4];

        assertThrows(IndexOutOfBoundsException.class,
                () -> source.get(-1, destination, 0, 1));
        assertThrows(IndexOutOfBoundsException.class,
                () -> source.get(4, destination, 0, 1));
        assertThrows(IndexOutOfBoundsException.class,
                () -> source.get(2, destination, 0, 3));
        assertThrows(IndexOutOfBoundsException.class,
                () -> source.get(0, destination, 0, -1));
    }

    @Test
    void rejectsInvalidDestinationArrayRange() {
        ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
        byte[] destination = new byte[3];

        assertThrows(IndexOutOfBoundsException.class,
                () -> source.get(0, destination, -1, 1));
        assertThrows(IndexOutOfBoundsException.class,
                () -> source.get(0, destination, 2, 2));
    }
}
~~~

Nếu buffer có limit thấp hơn capacity, hãy bổ sung test vùng nguồn vượt limit nhưng chưa vượt capacity. Đây là trường hợp thường xuất hiện khi buffer chứa một packet lớn hơn phần dữ liệu hợp lệ hiện tại.

## 8. Vùng rỗng: length bằng 0

Vùng rỗng là trường hợp hợp lệ trong nhiều API bulk. Nó có thể xuất hiện khi parser đọc một trường có độ dài 0, một payload tùy chọn không có dữ liệu hoặc một đoạn cần sao chép không chứa byte nào.

Với absolute bulk get, length bằng 0 không đọc byte nào và không thay đổi position. Các điểm bắt đầu vẫn phải nằm trong biên cho phép:

- index có thể bằng limit khi length bằng 0.
- offset có thể bằng destinationArray.length khi length bằng 0.
- index hoặc offset âm vẫn không hợp lệ.
- index lớn hơn limit hoặc offset lớn hơn độ dài array vẫn không hợp lệ.

Ví dụ:

~~~java
@Test
void acceptsEmptyAbsoluteReadAtEndBoundaries() {
    ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
    source.position(1);
    source.limit(3);
    source.mark();

    byte[] destination = new byte[2];
    destination[0] = 90;
    destination[1] = 91;

    source.get(source.limit(), destination, destination.length, 0);

    assertEquals(1, source.position());
    assertEquals(90, destination[0]);
    assertEquals(91, destination[1]);

    source.reset();
    assertEquals(1, source.position());
}
~~~

Không nhầm vùng rỗng với vùng không hợp lệ. Ví dụ length bằng 0 nhưng index âm vẫn phải bị từ chối. Một test vùng rỗng nên kiểm tra cả dữ liệu đích và position để chứng minh thao tác không gây tác dụng phụ.

### Vùng rỗng với relative bulk get

Relative bulk get với length bằng 0 không tiêu thụ dữ liệu và không tăng position:

~~~java
@Test
void emptyRelativeReadDoesNotAdvancePosition() {
    ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
    source.position(1);
    byte[] destination = new byte[2];

    source.get(destination, 1, 0);

    assertEquals(1, source.position());
}
~~~

Relative operation vẫn sử dụng position và remaining theo hợp đồng của nó. Khi kiểm thử vùng rỗng, không nên suy ra rằng mọi index/offset đều được chấp nhận chỉ vì length bằng 0.

## 9. Byte trong Java là signed: kiểm tra dữ liệu nhị phân đúng cách

Kiểu byte trong Java có miền giá trị từ -128 đến 127. Một byte trong giao thức nhị phân thường được hiểu là giá trị unsigned từ 0 đến 255. Khi đọc byte có bit cao bằng 1, kết quả Java có thể là số âm.

Ví dụ:

~~~java
byte value = (byte) 0xFF;

System.out.println(value);                    // -1
System.out.println(Byte.toUnsignedInt(value)); // 255
~~~

Khi test protocol field unsigned, dùng Byte.toUnsignedInt thay vì so sánh trực tiếp byte với một số nguyên dương:

~~~java
ByteBuffer packet = ByteBuffer.wrap(
        new byte[] {(byte) 0x7F, (byte) 0x80, (byte) 0xFF});

assertEquals(127, Byte.toUnsignedInt(packet.get(0)));
assertEquals(128, Byte.toUnsignedInt(packet.get(1)));
assertEquals(255, Byte.toUnsignedInt(packet.get(2)));
~~~

Nếu chỉ so sánh raw byte, hãy viết expected dưới dạng byte literal hoặc cast rõ ràng:

~~~java
assertArrayEquals(
        new byte[] {(byte) 0x7F, (byte) 0x80, (byte) 0xFF},
        actual);
~~~

## 10. Kiểm thử byte order của dữ liệu nhiều byte

ByteBuffer mặc định dùng BIG_ENDIAN: byte có trọng số cao nằm trước. Có thể chọn LITTLE_ENDIAN khi giao thức hoặc định dạng file quy định thứ tự byte ngược lại.

Ví dụ cùng một dãy byte:

~~~java
byte[] bytes = {
        0x01, 0x02, 0x03, 0x04
};

ByteBuffer buffer = ByteBuffer.wrap(bytes);

int bigEndian = buffer.getInt(0);
int littleEndian = buffer.duplicate()
        .order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .getInt(0);

System.out.printf("%08X%n", bigEndian);    // 01020304
System.out.printf("%08X%n", littleEndian); // 04030201
~~~

getInt(index) là absolute read, nên không thay đổi position. Khi test dữ liệu nhị phân, cần đặt byte order tường minh nếu format có quy định; không phụ thuộc vào default chỉ vì nó đang khớp với máy phát triển.

Byte order chỉ ảnh hưởng cách diễn giải nhóm byte thành kiểu nhiều byte như short, int, long, float hoặc double. Các thao tác get(byte) và get(byte[]) vẫn trả về đúng dãy byte theo thứ tự đã lưu.

## 11. Test binary payload bằng array, không phụ thuộc array() của buffer

Không phải ByteBuffer nào cũng cho phép gọi array():

- Direct buffer không có backing array Java có thể truy cập.
- Read-only buffer không cho phép lấy array có thể ghi.
- Code dùng array() có thể chạy với heap buffer nhưng thất bại khi đổi sang direct hoặc read-only buffer.

Để kiểm tra dữ liệu, hãy đọc ra một byte array riêng bằng bulk get:

~~~java
@Test
void readsBinaryPayloadFromReadOnlyBuffer() {
    byte[] expected = {
            0x00, 0x7F, (byte) 0x80, (byte) 0xFF
    };

    ByteBuffer source = ByteBuffer.wrap(expected)
            .asReadOnlyBuffer();
    byte[] actual = new byte[expected.length];

    source.get(0, actual, 0, actual.length);

    assertArrayEquals(expected, actual);
    assertEquals(0, source.position());
}
~~~

Cách này hoạt động với heap buffer, direct buffer và read-only buffer miễn là vùng đọc hợp lệ. Nó cũng kiểm tra được rằng absolute bulk get giữ nguyên position.

## 12. Kiểm thử direct buffer và read-only view

Một số lỗi chỉ xuất hiện khi implementation không còn dựa vào backing array. Hãy có ít nhất một test sử dụng direct buffer nếu code production hỗ trợ direct memory:

~~~java
@Test
void readsDirectReadOnlyBufferWithoutAccessingBackingArray() {
    ByteBuffer direct = ByteBuffer.allocateDirect(4);
    direct.put(new byte[] {11, 22, 33, 44});
    direct.flip();

    ByteBuffer readOnly = direct.asReadOnlyBuffer();
    byte[] actual = new byte[4];
    readOnly.get(0, actual, 0, actual.length);

    assertArrayEquals(
            new byte[] {11, 22, 33, 44},
            actual);
    assertTrue(readOnly.isDirect());
    assertTrue(readOnly.isReadOnly());
}
~~~

Test này không gọi array() và không giả định buffer có backing array. Direct buffer có chi phí cấp phát/quản lý khác heap buffer, nên không nên tạo direct buffer nhỏ cho mọi test đơn vị nếu code không dùng loại buffer đó; chọn test đại diện cho các đường chạy thật.

## 13. ByteBuffer.equals không so sánh toàn bộ capacity

ByteBuffer.equals so sánh các phần tử còn lại trong vùng từ position đến trước limit của hai buffer. Nó không so sánh toàn bộ capacity hoặc mọi byte đã từng được ghi.

Ví dụ:

~~~java
ByteBuffer first = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
ByteBuffer second = ByteBuffer.wrap(new byte[] {9, 2, 3, 8});

first.position(1);
second.position(1);
first.limit(3);
second.limit(3);

System.out.println(first.equals(second)); // true
~~~

Hai buffer bằng nhau theo phần remaining là [2, 3], dù byte ở ngoài vùng đó khác nhau. Vì vậy:

- Dùng assertArrayEquals khi cần kiểm tra toàn bộ payload byte.
- Dùng equals khi mục tiêu thật sự là so sánh remaining sequence theo hợp đồng Buffer.
- Đặt position/limit rõ ràng nếu muốn so sánh một đoạn.
- Không dùng hashCode của buffer làm checksum cho toàn bộ backing memory nếu state buffer có thể thay đổi.

## 14. Kiểm thử trạng thái buffer sau absolute read

Absolute get và absolute bulk get không di chuyển position. Mark hợp lệ cũng vẫn có thể reset nếu thao tác không thay đổi position:

~~~java
@Test
void absoluteBulkReadPreservesPositionLimitAndMark() {
    ByteBuffer source = ByteBuffer.wrap(
            new byte[] {10, 20, 30, 40});
    source.position(1);
    source.limit(4);
    source.mark();

    byte[] output = new byte[2];
    source.get(0, output, 0, 2);

    assertArrayEquals(new byte[] {10, 20}, output);
    assertEquals(1, source.position());
    assertEquals(4, source.limit());

    source.reset();
    assertEquals(1, source.position());
}
~~~

Đây là kiểm tra quan trọng khi buffer được chia sẻ giữa nhiều bước xử lý. Nếu một parser đọc một field theo index tuyệt đối, caller có thể tiếp tục relative read từ position trước đó.

## 15. Ma trận test nên có cho buffer

| Nhóm | Dữ liệu/điều kiện | Kết quả cần xác nhận |
|---|---|---|
| Read-only | Đọc byte hợp lệ | Đọc được nội dung |
| Read-only | Ghi absolute hoặc relative | ReadOnlyBufferException |
| Read-only source | Sao chép sang writable destination | Thành công |
| Index | index âm | IndexOutOfBoundsException |
| Index | index bằng limit | IndexOutOfBoundsException với thao tác đọc một byte |
| Limit | capacity lớn nhưng limit nhỏ | Không đọc vượt limit |
| Bulk range | source range vượt limit | IndexOutOfBoundsException |
| Bulk range | destination array range vượt length | IndexOutOfBoundsException |
| Empty range | length bằng 0, điểm bắt đầu ở biên hợp lệ | Không đọc byte, position không đổi |
| Empty range | length bằng 0 nhưng index/offset âm hoặc vượt biên | Bị từ chối |
| Binary | byte 0x80 và 0xFF | Kiểm tra unsigned bằng Byte.toUnsignedInt |
| Endianness | Dữ liệu nhiều byte | BIG_ENDIAN/LITTLE_ENDIAN đúng format |
| Direct | Direct read-only buffer | Đọc được mà không gọi array() |
| State | Absolute read sau khi đặt mark | Position, limit, mark giữ nguyên |
| Equality | Hai buffer có remaining giống nhưng byte ngoài remaining khác | equals có thể true; array comparison kiểm tra toàn payload |

## 16. Checklist review test

- [ ] Test phân biệt read-only view với buffer có quyền ghi.
- [ ] Test đọc thành công từ read-only buffer.
- [ ] Test ghi vào read-only buffer và xác nhận ReadOnlyBufferException.
- [ ] Test read-only source có thể được sao chép sang destination writable.
- [ ] Test index âm, index bằng limit và vùng vượt limit.
- [ ] Test riêng absolute index failure và relative underflow.
- [ ] Test source range và destination array range của bulk get.
- [ ] Test vùng rỗng với length bằng 0 ở biên hợp lệ.
- [ ] Test vùng rỗng nhưng index/offset sai.
- [ ] Test dữ liệu có byte unsigned lớn hơn 127.
- [ ] Test byte order của các field nhiều byte.
- [ ] Test direct buffer nếu ứng dụng dùng direct memory.
- [ ] Không phụ thuộc array() khi test buffer tổng quát.
- [ ] Test position, limit và mark sau absolute read.
- [ ] Chọn assertArrayEquals hoặc ByteBuffer.equals đúng với mục tiêu.

## 17. Ghi nhớ

- Read-only buffer vẫn đọc được; mọi thao tác ghi qua view đó bị từ chối.
- Read-only view có thể chia sẻ nội dung với buffer gốc mutable, nên không phải snapshot bất biến.
- Absolute index hợp lệ được xác định theo limit, không phải capacity.
- Absolute get lỗi index bằng IndexOutOfBoundsException; relative get thiếu dữ liệu lỗi BufferUnderflowException.
- Absolute bulk get có thể đọc vùng bắt đầu tại index vào array offset mà không đổi position.
- Vùng length bằng 0 không đọc byte nào, nhưng index/offset vẫn phải nằm trong biên cho phép.
- Byte là signed trong Java; dùng Byte.toUnsignedInt khi diễn giải byte của protocol là unsigned.
- Đặt ByteOrder tường minh khi parse dữ liệu nhiều byte.
- Direct và read-only buffer không nên bị ép dùng array(); bulk get ra array riêng là cách kiểm tra dễ dự đoán.
- ByteBuffer.equals chỉ so sánh remaining sequence, không phải toàn bộ capacity.

Kiểm thử buffer cần bao phủ quyền đọc/ghi, giới hạn chỉ số, vùng rỗng và nội dung nhị phân. Khi test cả dữ liệu lẫn position/limit/mark, đồng thời không phụ thuộc vào backing array, bộ kiểm thử sẽ đáng tin cậy hơn khi ứng dụng chuyển giữa heap, direct và read-only buffer trên các JDK hiện đại.

## Tài liệu tham khảo

- [Java SE 16 ByteBuffer API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html) — absolute get, bulk get, read-only buffer và byte order.
- [Java SE 26 ByteBuffer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html) — hợp đồng API hiện hành và các overload absolute.
- [Java SE 26 Buffer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/Buffer.html) — capacity, limit, position và mark.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — assertion và exception testing với JUnit Jupiter.
