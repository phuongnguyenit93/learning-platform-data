# Absolute bulk put và việc giữ nguyên position của buffer nguồn, đích

Java 16 bổ sung overload của ByteBuffer cho phép sao chép một vùng dữ liệu từ buffer nguồn sang buffer đích bằng các chỉ số tuyệt đối. Lệnh put(index, src, offset, length) ghi length byte vào buffer đích tại index, đọc từ buffer nguồn tại offset và **không thay đổi position của cả hai buffer**. API này hữu ích khi lắp ráp packet, cập nhật một vùng trong buffer hoặc sao chép dữ liệu mà nhiều phần khác của chương trình đang dựa vào vị trí hiện tại.

Điểm cần nhớ là index và offset được tính từ đầu buffer tương ứng, còn phạm vi hợp lệ được kiểm tra theo limit, không phải capacity hay remaining. Đây là khác biệt quan trọng với relative bulk put, vốn bắt đầu tại position và tăng position sau khi sao chép.

## 1. Overload mới trong Java 16

Chữ ký API:

~~~java
ByteBuffer put(int index, ByteBuffer src, int offset, int length)
~~~

Phương thức sao chép length byte:

- Đọc từ src bắt đầu tại offset.
- Ghi vào buffer đích bắt đầu tại index.
- Không thay đổi position của src.
- Không thay đổi position của buffer đích.
- Không thay đổi limit của hai buffer.

Phương thức trả về chính buffer đích để có thể nối lời gọi. Đây là một absolute bulk put operation và được bổ sung từ Java 16.

Ví dụ:

~~~java
ByteBuffer source = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50});
ByteBuffer target = ByteBuffer.allocate(8);

target.put(2, source, 1, 3);
~~~

Lệnh trên sao chép các byte tại source index 1, 2, 3 sang target index 2, 3, 4. Nội dung đích trở thành:

~~~text
index:  0   1   2   3   4   5   6   7
value:  0   0  20  30  40   0   0   0
~~~

Position của source và target đều vẫn bằng 0.

## 2. So sánh absolute bulk put và relative bulk put

ByteBuffer có hai cách sao chép buffer-to-buffer thường cần phân biệt:

| Đặc điểm | Relative put: put(src) | Absolute bulk put: put(index, src, offset, length) |
|---|---|---|
| Vị trí đọc nguồn | Bắt đầu tại src.position() | Bắt đầu tại offset |
| Vị trí ghi đích | Bắt đầu tại dst.position() | Bắt đầu tại index |
| Số byte | Toàn bộ src.remaining() | length do caller chỉ định |
| Position nguồn | Tăng thêm số byte đã sao chép | Giữ nguyên |
| Position đích | Tăng thêm số byte đã sao chép | Giữ nguyên |
| Điều kiện dung lượng | Dựa trên remaining() của hai buffer | Dựa trên limit() và các chỉ số tuyệt đối |
| Khi đích không đủ chỗ | BufferOverflowException | IndexOutOfBoundsException |
| Tự sao chép cùng buffer | IllegalArgumentException | Xử lý theo quy tắc vùng nhớ chồng lấn của absolute method |

Relative put phù hợp khi muốn tiêu thụ dữ liệu tuần tự và tiến con trỏ đọc/ghi. Absolute bulk put phù hợp khi cần cập nhật một vùng đã biết mà không làm thay đổi trạng thái position mà caller đang quản lý.

### Relative put

~~~java
ByteBuffer source = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50});
source.position(1);
source.limit(4);

ByteBuffer target = ByteBuffer.allocate(8);
target.position(2);

target.put(source);
~~~

Source còn 3 byte từ position 1 đến trước limit 4. Lệnh put(source) sao chép các byte 20, 30, 40 vào target từ position 2. Sau đó:

- source.position() bằng 4.
- target.position() bằng 5.
- Các limit giữ nguyên.

### Absolute bulk put

~~~java
ByteBuffer source = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50});
source.position(1);
source.limit(4);

ByteBuffer target = ByteBuffer.allocate(8);
target.position(6);

target.put(2, source, 1, 3);
~~~

Lệnh vẫn sao chép 20, 30, 40 vào target index 2, 3, 4, nhưng source.position() vẫn là 1 và target.position() vẫn là 6. Position không quyết định vùng sao chép của overload tuyệt đối.

## 3. Index và offset được tính theo limit, không theo remaining

Đây là quy tắc quan trọng nhất khi gọi overload mới:

- index phải không âm và nhỏ hơn dst.limit().
- offset phải không âm và nhỏ hơn src.limit().
- length phải không âm.
- length không được lớn hơn dst.limit() - index.
- length không được lớn hơn src.limit() - offset.

Có thể viết điều kiện phạm vi tương đương:

~~~java
length <= dst.limit() - index
length <= src.limit() - offset
~~~

Phương thức kiểm tra các điều kiện này trước khi sao chép. Không dùng capacity để quyết định phạm vi hợp lệ nếu limit đã được đặt thấp hơn capacity.

Ví dụ:

~~~java
ByteBuffer source = ByteBuffer.allocate(16);
source.position(2);
source.limit(8);

ByteBuffer target = ByteBuffer.allocate(20);
target.position(0);
target.limit(10);

target.put(4, source, 3, 5);
~~~

Phạm vi nguồn là [3, 8), nằm trong source.limit() bằng 8. Phạm vi đích là [4, 9), nằm trong target.limit() bằng 10. Lệnh hợp lệ dù position của source đang là 2.

Nếu đổi length thành 6, phạm vi nguồn sẽ kết thúc tại 9, vượt source.limit() bằng 8 và phương thức ném IndexOutOfBoundsException. Tăng capacity mà không tăng limit cũng không làm lời gọi trở nên hợp lệ.

Không nên kiểm tra bằng phép cộng index + length nếu có nguy cơ tràn số nguyên. Dạng kiểm tra length <= limit - index an toàn hơn sau khi đã xác nhận index nằm trong phạm vi.

## 4. Ví dụ sao chép và xác minh position, limit

Ví dụ sau minh họa source có position khác 0, target cũng có position khác 0, nhưng vùng sao chép vẫn được xác định hoàn toàn bằng index và offset:

~~~java
import java.nio.ByteBuffer;

public class AbsoluteBulkPutExample {
    public static void main(String[] args) {
        ByteBuffer source = ByteBuffer.wrap(
                new byte[] {10, 20, 30, 40, 50});
        source.position(2);
        source.limit(4);

        ByteBuffer target = ByteBuffer.allocate(8);
        target.position(6);

        target.put(1, source, 1, 3);

        System.out.println(source.position()); // 2
        System.out.println(source.limit());    // 4
        System.out.println(target.position()); // 6
        System.out.println(target.limit());    // 8

        System.out.println(target.get(1));     // 20
        System.out.println(target.get(2));     // 30
        System.out.println(target.get(3));     // 40
    }
}
~~~

Các lời gọi get(index) cuối cùng cũng là absolute get, nên chúng không làm thay đổi target.position(). Nếu thay bằng get() không có index, thao tác sẽ đọc tại position hiện tại là 6, không đọc vùng vừa được ghi ở index 1.

## 5. Position, mark và limit được giữ nguyên

Trong Buffer, position là con trỏ cho các thao tác relative; limit xác định biên truy cập; mark là một vị trí đã lưu để reset. Absolute bulk put không di chuyển position của source hoặc destination, nên mark hợp lệ của mỗi buffer cũng không bị mất do thao tác này.

Ví dụ với mark:

~~~java
ByteBuffer source = ByteBuffer.wrap(
        new byte[] {1, 2, 3, 4, 5});
source.position(2);
source.mark();

ByteBuffer target = ByteBuffer.allocate(8);
target.position(5);
target.mark();

target.put(1, source, 0, 3);

source.reset();
target.reset();

System.out.println(source.position()); // 2
System.out.println(target.position()); // 5
~~~

Reset thành công vì mark không bị invalidated. Limit của hai buffer cũng giữ nguyên.

Điều này khác với relative put, vì relative put tăng position và có thể làm mark bị bỏ nếu position mới vượt mark. Nếu code phía sau phụ thuộc vào mark/position đã thiết lập, absolute bulk put giúp tránh thay đổi trạng thái đó.

## 6. Vùng sao chép và các buffer view

ByteBuffer có thể tạo view bằng duplicate(), slice() hoặc asReadOnlyBuffer(). Các view có position, limit và mark độc lập, nhưng có thể chia sẻ cùng vùng nội dung bộ nhớ với buffer gốc.

Absolute bulk put làm việc theo index của buffer được truyền vào, không phải index toàn cục của vùng nhớ nền:

- Với duplicate(), index 0 tương ứng index 0 của buffer gốc tại thời điểm duplicate.
- Với slice(), index 0 tương ứng vị trí bắt đầu của vùng remaining tại thời điểm tạo slice.
- Với view được tạo từ một buffer có position khác 0, không tự cộng position cũ vào index của view.

Ví dụ:

~~~java
ByteBuffer original = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50, 60});
original.position(2);
original.limit(5);

ByteBuffer slice = original.slice();
// slice index 0 tương ứng original index 2

ByteBuffer source = ByteBuffer.wrap(
        new byte[] {7, 8, 9});

slice.put(1, source, 1, 2);
~~~

Sau lời gọi, nội dung original là:

slice ghi index 1 và 2 của chính view, tương ứng original index 3 và 4. Vì vậy, kết quả của original là:

~~~text
[10, 20, 30, 8, 9, 60]
~~~

Các thay đổi nội dung được nhìn thấy qua view cùng chia sẻ vùng nhớ, trong khi position/limit của từng view độc lập.

## 7. Sao chép khi source và destination chia sẻ vùng nhớ

Hai buffer có thể chia sẻ backing array hoặc vùng nhớ native, ví dụ duplicate và slice của cùng một buffer. Absolute bulk put được quy định để cho kết quả như thể dữ liệu nguồn đã được sao chép vào một vùng trung gian trước khi ghi vào đích. Vì vậy, vùng nguồn và đích chồng lấn được xử lý theo semantics copy an toàn, không phụ thuộc thứ tự ghi từng byte kiểu vòng lặp đơn giản.

Ví dụ dùng cùng một buffer:

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {1, 2, 3, 4, 5});

buffer.put(1, buffer, 0, 4);
~~~

Kết quả tương đương:

~~~text
[1, 1, 2, 3, 4]
~~~

Các byte nguồn ban đầu ở index 0 đến 3 được xem như một vùng dữ liệu cần sao chép trước khi ghi vào index 1 đến 4. Kết quả không phải là chuỗi lặp 1 do việc ghi đè lần lượt làm thay đổi dữ liệu sẽ đọc tiếp.

Hợp đồng này cũng áp dụng khi hai buffer khác object nhưng chia sẻ backing array hoặc memory. Đây là điểm hữu ích khi thao tác với duplicate/slice, nhưng không có nghĩa thao tác an toàn khi nhiều thread đồng thời sửa cùng vùng nhớ. Cần đồng bộ hóa hoặc quy định ownership nếu có truy cập đồng thời.

## 8. Heap buffer, direct buffer và read-only buffer

Absolute bulk put làm việc với ByteBuffer, không yêu cầu buffer phải được tạo bằng allocate hay allocateDirect:

~~~java
ByteBuffer heapSource = ByteBuffer.allocate(16);
ByteBuffer directTarget = ByteBuffer.allocateDirect(32);

directTarget.put(4, heapSource, 0, 8);
~~~

Một số điểm cần kiểm tra:

- Heap buffer có thể truy cập backing array nếu hasArray() trả về true.
- Direct buffer không nhất thiết có backing array truy cập được.
- Phương thức put buffer-to-buffer không yêu cầu caller tự lấy array() hoặc address native.
- Source read-only vẫn có thể làm nguồn đọc.
- Destination read-only không thể ghi và sẽ ném ReadOnlyBufferException.

Ví dụ:

~~~java
ByteBuffer source = ByteBuffer.wrap(
        new byte[] {1, 2, 3, 4});
ByteBuffer readOnlyTarget = ByteBuffer.allocate(8)
        .asReadOnlyBuffer();

readOnlyTarget.put(0, source, 0, 4);
// ReadOnlyBufferException
~~~

Không nên suy luận rằng direct buffer luôn nhanh hơn heap buffer cho mọi lần sao chép. Hiệu năng phụ thuộc kích thước, implementation, cách sử dụng tiếp theo và chi phí cấp phát/quản lý bộ nhớ. Hãy benchmark trên workload thực tế.

## 9. Xử lý exception và kiểm tra đầu vào

Absolute bulk put không sử dụng BufferOverflowException cho trường hợp index/offset/length vượt giới hạn. Các trường hợp chính:

| Tình huống | Exception |
|---|---|
| index âm hoặc index không nhỏ hơn destination limit | IndexOutOfBoundsException |
| offset âm hoặc offset không nhỏ hơn source limit | IndexOutOfBoundsException |
| length âm | IndexOutOfBoundsException |
| Vùng nguồn vượt source limit | IndexOutOfBoundsException |
| Vùng đích vượt destination limit | IndexOutOfBoundsException |
| Destination là read-only | ReadOnlyBufferException |
| Source là read-only | Không lỗi chỉ vì read-only; source chỉ được đọc |

Ví dụ kiểm tra phạm vi trước khi gọi:

~~~java
static void copyRange(
        ByteBuffer destination,
        int destinationIndex,
        ByteBuffer source,
        int sourceOffset,
        int length) {

    if (destinationIndex < 0
            || destinationIndex >= destination.limit()
            || sourceOffset < 0
            || sourceOffset >= source.limit()
            || length < 0
            || length > destination.limit() - destinationIndex
            || length > source.limit() - sourceOffset) {
        throw new IllegalArgumentException("Invalid buffer range");
    }

    destination.put(destinationIndex, source, sourceOffset, length);
}
~~~

Đây là ví dụ kiểm tra đầu vào cho API ở tầng ứng dụng. Nếu muốn khớp chính xác các điều kiện của method, cần lưu ý Javadoc yêu cầu index nhỏ hơn destination limit và offset nhỏ hơn source limit; với trường hợp length bằng 0, không nên tự suy diễn rằng mọi index bằng limit đều được chấp nhận. Cách đơn giản là để method chuẩn của JDK thực hiện kiểm tra cuối cùng hoặc áp dụng điều kiện nghiêm ngặt tương ứng trong wrapper.

Không cần kiểm tra capacity riêng vì phương thức dựa trên limit. Nếu muốn ghi đến hết vùng nhớ đã cấp phát, hãy điều chỉnh limit trước bằng clear() hoặc limit(capacity()) theo trạng thái buffer mong muốn.

## 10. Lắp ráp packet mà không thay đổi position của payload

Một trường hợp thực tế là tạo packet gồm header và payload. Payload có thể đang được một phần khác của chương trình quản lý position; absolute bulk put cho phép sao chép vùng cần thiết mà không tiêu thụ payload.

~~~java
import java.nio.ByteBuffer;

public class PacketAssembler {
    public static ByteBuffer assemble(
            byte[] header,
            ByteBuffer payload) {

        int payloadOffset = payload.position();
        int payloadLength = payload.remaining();
        int totalLength = header.length + payloadLength;

        ByteBuffer packet = ByteBuffer.allocate(totalLength);
        if (header.length > 0) {
            packet.put(0, header, 0, header.length);
        }
        if (payloadLength > 0) {
            packet.put(header.length, payload,
                    payloadOffset, payloadLength);
        }

        // packet.position() vẫn là 0 vì cả hai lần put đều absolute.
        // payload.position() vẫn là payloadOffset.
        ByteBuffer outbound = packet.duplicate();
        outbound.position(0);
        outbound.limit(totalLength);
        return outbound;
    }
}
~~~

Trong ví dụ:

- Overload put(index, byte[], offset, length) cho array đã có từ Java 13.
- Overload put(index, ByteBuffer, offset, length) là phần bổ sung từ Java 16.
- Payload được đọc từ position hiện tại đến trước limit.
- Position payload không thay đổi.
- Position packet không tự tăng theo số byte đã ghi.
- Buffer trả về là duplicate có position 0 và limit bằng tổng chiều dài packet.

Duplicate chia sẻ nội dung với packet nhưng có position/limit riêng. Caller có thể ghi outbound ra channel mà không làm thay đổi position của packet gốc.

## 11. Absolute put không tự chuẩn bị buffer để ghi ra channel

Các thao tác channel như SocketChannel.write(ByteBuffer) sử dụng vùng remaining của buffer, tức từ position đến limit. Absolute bulk put không thay đổi position, vì vậy dữ liệu vừa ghi theo index có thể nằm ngoài remaining hiện tại.

Ví dụ:

~~~java
ByteBuffer packet = ByteBuffer.allocate(32);
packet.position(20);
packet.put(0, header, 0, header.length);
~~~

Sau lệnh put, packet.position() vẫn là 20. Nếu gọi channel.write(packet), channel bắt đầu đọc từ index 20, không tự quay về index 0 để gửi header.

Có hai cách chuẩn bị vùng cần ghi:

~~~java
ByteBuffer outbound = packet.duplicate();
outbound.position(0);
outbound.limit(header.length);

while (outbound.hasRemaining()) {
    channel.write(outbound);
}
~~~

Hoặc nếu không cần giữ position cũ của packet, đặt position và limit trực tiếp trên packet:

~~~java
packet.position(0);
packet.limit(header.length);
~~~

Duplicate thường hữu ích khi nhiều phần của chương trình cần giữ state buffer gốc riêng. Nhớ rằng duplicate chia sẻ nội dung, nên thay đổi byte vẫn nhìn thấy ở cả hai buffer.

Không gọi flip() một cách máy móc sau absolute put. flip() đặt limit bằng position hiện tại rồi đặt position về 0; vì absolute put không tăng position, flip không biết vùng nào vừa được ghi. Hãy đặt rõ position/limit cho vùng dữ liệu cần đọc hoặc ghi.

## 12. So sánh với thao tác từng byte

Có thể mô phỏng absolute bulk put bằng vòng lặp:

~~~java
for (int i = 0, j = destinationIndex;
        i < length;
        i++, j++) {
    destination.put(j, source.get(sourceOffset + i));
}
~~~

Vòng lặp này cho thấy ý nghĩa tuyệt đối của index và offset, nhưng tự viết loop có thể bỏ sót kiểm tra phạm vi, semantics khi vùng nhớ chồng lấn và cơ hội tối ưu của implementation. API bulk thực hiện kiểm tra tham số trước và có thể dùng đường sao chép hiệu quả hơn.

Không nên thay API bulk bằng vòng lặp chỉ vì muốn tránh một method call. Nếu cần đo hiệu năng, hãy benchmark với kích thước buffer, loại buffer và runtime tương ứng; không suy luận hiệu năng từ số dòng code.

## 13. Kiểm thử position, limit, mark và dữ liệu

Test nên xác nhận cả nội dung được sao chép và trạng thái hai buffer:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.ByteBuffer;
import org.junit.jupiter.api.Test;

class AbsoluteBulkPutTest {
    @Test
    void copiesBytesWithoutChangingBufferState() {
        ByteBuffer source = ByteBuffer.wrap(
                new byte[] {10, 20, 30, 40, 50});
        source.position(2);
        source.limit(4);
        source.mark();

        ByteBuffer target = ByteBuffer.allocate(8);
        target.position(6);
        target.mark();

        target.put(1, source, 1, 3);

        assertEquals(2, source.position());
        assertEquals(4, source.limit());
        assertEquals(6, target.position());
        assertEquals(8, target.limit());

        assertEquals(20, target.get(1));
        assertEquals(30, target.get(2));
        assertEquals(40, target.get(3));

        source.reset();
        target.reset();
        assertEquals(2, source.position());
        assertEquals(6, target.position());
    }
}
~~~

Test này kiểm tra:

- Byte được đọc theo source offset, không theo source position.
- Byte được ghi theo destination index, không theo destination position.
- Position và limit của hai buffer không đổi.
- Mark vẫn có thể reset.
- Absolute get để xác minh nội dung cũng không làm thay đổi position.

### Kiểm thử giới hạn

~~~java
@Test
void rejectsRangeBeyondSourceLimit() {
    ByteBuffer source = ByteBuffer.allocate(8);
    source.limit(4);
    ByteBuffer target = ByteBuffer.allocate(8);

    assertThrows(IndexOutOfBoundsException.class,
            () -> target.put(0, source, 2, 3));
}

@Test
void rejectsRangeBeyondDestinationLimit() {
    ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
    ByteBuffer target = ByteBuffer.allocate(8);
    target.limit(2);

    assertThrows(IndexOutOfBoundsException.class,
            () -> target.put(0, source, 0, 3));
}
~~~

### Kiểm thử destination read-only

~~~java
@Test
void rejectsReadOnlyDestination() {
    ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2});
    ByteBuffer target = ByteBuffer.allocate(4).asReadOnlyBuffer();

    assertThrows(ReadOnlyBufferException.class,
            () -> target.put(0, source, 0, 2));
}
~~~

### Kiểm thử vùng nhớ chồng lấn

~~~java
@Test
void copiesOverlappingRegionAsIfUsingTemporaryStorage() {
    ByteBuffer buffer = ByteBuffer.wrap(
            new byte[] {1, 2, 3, 4, 5});

    buffer.put(1, buffer, 0, 4);

    assertEquals(1, buffer.get(0));
    assertEquals(1, buffer.get(1));
    assertEquals(2, buffer.get(2));
    assertEquals(3, buffer.get(3));
    assertEquals(4, buffer.get(4));
}
~~~

## 14. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Dùng position thay cho index | Absolute method không lấy position làm điểm bắt đầu | Truyền index và offset tường minh |
| Kiểm tra capacity thay vì limit | Vùng có thể vượt limit dù chưa vượt capacity | Kiểm tra theo limit |
| Nghĩ source.position() sẽ tăng | Absolute bulk put giữ nguyên position nguồn | Tự cập nhật position nếu logic sau cần tiêu thụ nguồn |
| Nghĩ destination.position() sẽ tăng | Absolute bulk put giữ nguyên position đích | Đặt position/limit trước thao tác relative tiếp theo |
| Gọi flip() ngay sau absolute put | Position vẫn là giá trị cũ, flip có thể tạo vùng remaining sai | Thiết lập position và limit cho vùng thực sự đã ghi |
| Gọi channel.write() mà không chỉnh view | Channel chỉ ghi từ position đến limit | Tạo duplicate và đặt vùng ghi |
| Dùng index vượt limit nhưng không vượt capacity | Absolute operation kiểm tra limit | Nâng limit hợp lệ hoặc dùng index trong limit |
| Dùng destination read-only | Không thể ghi vào read-only buffer | Dùng buffer có quyền ghi |
| Tự viết vòng lặp copy khi vùng chồng lấn | Có thể ghi đè dữ liệu sẽ đọc ở bước sau | Dùng bulk API có semantics overlap được xác định |

## 15. Ghi nhớ

- Overload ByteBuffer.put(index, src, offset, length) được thêm từ Java 16.
- Phương thức sao chép length byte từ source offset sang destination index.
- Position của cả source và destination không thay đổi; limit và mark cũng được giữ nguyên.
- index, offset và length được kiểm tra theo limit, không phải capacity hoặc remaining.
- Relative put(src) bắt đầu từ position và tăng position của cả hai buffer.
- Absolute bulk put có thể làm việc với heap/direct buffer; source read-only vẫn đọc được, destination read-only thì không ghi được.
- Khi source và destination chia sẻ backing memory, kết quả như thể dữ liệu nguồn được sao chép qua vùng trung gian trước khi ghi.
- Index trong slice/duplicate là index của view, không phải index toàn cục của buffer gốc.
- Sau absolute put, channel vẫn đọc theo position/limit hiện tại; dùng duplicate và đặt vùng ghi khi cần.
- Không gọi flip() nếu chưa xác định position hiện tại có đúng là điểm kết thúc dữ liệu cần đọc hay không.

Absolute bulk put giúp sao chép vùng dữ liệu chính xác mà không làm xáo trộn state của hai buffer. Khi nắm rõ index, offset, length và giới hạn theo limit, có thể dùng API này để lắp ráp packet, cập nhật buffer view và chuyển dữ liệu giữa các vùng nhớ một cách rõ ràng trên Java 16 trở lên.

## Tài liệu tham khảo

- [Java SE 16 ByteBuffer API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html) — overload put(int, ByteBuffer, int, int) và trạng thái position.
- [Java SE 26 ByteBuffer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html) — hợp đồng API hiện hành, kiểm tra giới hạn và xử lý vùng nhớ chia sẻ.
- [Java SE 26 Buffer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/Buffer.html) — ý nghĩa position, limit và mark.
