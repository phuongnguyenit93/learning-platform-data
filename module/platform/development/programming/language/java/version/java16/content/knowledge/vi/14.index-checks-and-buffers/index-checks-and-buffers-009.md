# Kiểm tra theo limit thay vì chỉ nhìn capacity

> **Chương:** Chỉ số và buffer  
> **Phạm vi:** Hiểu cách ByteBuffer quản lý position, limit và capacity; xác định đúng biên cho thao tác đọc/ghi tương đối và tuyệt đối. Nội dung tập trung vào vòng đời buffer, vùng dữ liệu con và I/O với channel bằng API NIO hiện hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt position, limit và capacity.
2. Áp dụng invariant 0 <= position <= limit <= capacity.
3. Giải thích vì sao truy cập tuyệt đối phải kiểm tra theo limit, không phải chỉ theo capacity.
4. Phân biệt exception của thao tác đọc/ghi tương đối và tuyệt đối.
5. Dùng đúng flip(), clear(), rewind() và compact().
6. Hiểu biên của slice(), duplicate() và buffer được tạo từ mảng.
7. Xử lý buffer đúng cách khi đọc/ghi qua Channel.

## 1. Ba chỉ số trạng thái của Buffer

ByteBuffer kế thừa mô hình trạng thái từ Buffer. Mỗi buffer có ba giá trị quan trọng:

- capacity: tổng số phần tử mà buffer có thể chứa; cố định sau khi tạo.
- limit: vị trí đầu tiên nằm ngoài vùng hiện có thể đọc hoặc ghi.
- position: vị trí của phần tử tiếp theo sẽ được đọc hoặc ghi bởi thao tác tương đối.

Luôn có invariant:

\[
0 \le position \le limit \le capacity
\]

Ví dụ, buffer có capacity = 8, limit = 5, position = 2:

| Vùng chỉ số | Ý nghĩa |
| --- | --- |
| 0 đến 1 | Đã nằm trước position |
| 2 đến 4 | Phần còn lại có thể đọc/ghi theo thao tác tương đối |
| 5 đến 7 | Nằm sau limit, chưa thuộc vùng truy cập hiện tại |

capacity mô tả dung lượng tối đa. limit mô tả biên đang có hiệu lực. position mô tả điểm thao tác tương đối tiếp theo.

## 2. Vì sao phải kiểm tra theo limit?

Một lỗi thường gặp là chỉ kiểm tra index nhỏ hơn capacity. Điều đó chưa đủ. Với các thao tác truy cập của Buffer, limit mới là cận trên hiện tại.

Ví dụ:

```java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {10, 20, 30, 40, 50});

System.out.println(buffer.position()); // 5
System.out.println(buffer.limit());    // 8
System.out.println(buffer.capacity()); // 8

buffer.flip();

System.out.println(buffer.position()); // 0
System.out.println(buffer.limit());    // 5
System.out.println(buffer.capacity()); // 8

System.out.println(buffer.get(4));     // 50
// buffer.get(5) ném IndexOutOfBoundsException
```

Sau flip(), buffer chuyển sang chế độ đọc dữ liệu vừa ghi. Dù capacity vẫn là 8, chỉ các chỉ số 0 đến 4 nằm trước limit và được truy cập. Chỉ số 5 nhỏ hơn capacity nhưng đã bằng limit, nên không hợp lệ.

Điều kiện cho một index tuyệt đối:

\[
0 \le index < limit
\]

Không dùng index < capacity để tự xác nhận một thao tác get(index) hoặc put(index, value) là hợp lệ.

## 3. Thao tác tương đối và tuyệt đối

ByteBuffer cung cấp hai nhóm thao tác đọc/ghi.

| Nhóm | Ví dụ | Dùng biên nào? | Thay đổi position? |
| --- | --- | --- | --- |
| Tương đối | get(), put(byte) | remaining() phải đủ | Có |
| Tuyệt đối | get(index), put(index, byte) | 0 <= index < limit | Không |

### Đọc tương đối

get() đọc tại position, sau đó tăng position lên một:

```java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40}
);

byte first = buffer.get();
byte second = buffer.get();

System.out.println(first);             // 10
System.out.println(second);            // 20
System.out.println(buffer.position()); // 2
```

Thao tác tương đối không nhận index. Nó yêu cầu còn ít nhất một phần tử trong vùng [position, limit). Nếu không còn phần tử, get() ném BufferUnderflowException.

### Đọc tuyệt đối

get(index) đọc tại chỉ số được chỉ định và giữ nguyên position:

```java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40}
);

byte value = buffer.get(2);

System.out.println(value);             // 30
System.out.println(buffer.position()); // 0
```

Chỉ số phải nhỏ hơn limit, kể cả khi buffer có capacity lớn hơn limit. Index âm hoặc index bằng/đứng sau limit sẽ gây IndexOutOfBoundsException.

### Ghi tương đối và tuyệt đối

Quy tắc tương tự áp dụng cho put:

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.limit(4);

buffer.put((byte) 11);          // Ghi tại position 0, position thành 1
buffer.put(3, (byte) 44);       // Ghi tại index 3, position vẫn là 1

System.out.println(buffer.position()); // 1

// Index 4 nhỏ hơn capacity 8 nhưng bằng limit nên không hợp lệ:
// buffer.put(4, (byte) 55);
```

put() tương đối ném BufferOverflowException nếu không còn chỗ trước limit. put(index, value) tuyệt đối ném IndexOutOfBoundsException nếu index không nằm trong [0, limit). Nếu buffer chỉ đọc, thao tác ghi còn có thể ném ReadOnlyBufferException.

## 4. remaining và hasRemaining

Số phần tử còn lại trong vùng hiện hành là:

\[
remaining = limit - position
\]

hasRemaining() trả về true khi position < limit.

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {1, 2, 3});
buffer.flip();

while (buffer.hasRemaining()) {
    System.out.println(buffer.get());
}
```

Vòng lặp chỉ đọc vùng dữ liệu hiện có. Nó tự dừng khi position chạm limit, dù buffer còn dung lượng ở phía sau.

Với thao tác theo lô, kiểm tra số phần tử còn lại trước khi đọc/ghi:

```java
int bytesNeeded = 4;

if (buffer.remaining() >= bytesNeeded) {
    // Có đủ byte trước limit cho thao tác này.
}
```

Đừng dùng capacity - position để thay cho remaining(). Biểu thức đó tính cả vùng sau limit, vốn không thuộc vùng truy cập hiện tại.

## 5. Bốn thao tác chuyển trạng thái quan trọng

flip(), clear(), rewind() và compact() thường được dùng trong vòng đời đọc/ghi buffer.

| Phương thức | Position sau gọi | Limit sau gọi | Mục đích |
| --- | ---: | ---: | --- |
| flip() | 0 | position cũ | Chuyển từ ghi sang đọc phần vừa ghi |
| clear() | 0 | capacity | Chuẩn bị ghi lại toàn bộ vùng |
| rewind() | 0 | giữ nguyên | Đọc lại từ đầu vùng hiện tại |
| compact() | số byte còn lại | capacity | Giữ phần chưa đọc và mở chỗ ghi tiếp |

### flip(): dữ liệu đã ghi trở thành dữ liệu để đọc

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {10, 20, 30});

// Trước flip: position=3, limit=8, capacity=8
buffer.flip();
// Sau flip: position=0, limit=3, capacity=8
```

flip() đặt limit bằng position cũ rồi đưa position về 0. Vì vậy vùng đọc đúng bằng số phần tử vừa ghi.

### clear(): mở lại toàn bộ capacity để ghi

```java
buffer.clear();
// position=0, limit=capacity
```

clear() không xóa byte cũ. Nó chỉ thay đổi trạng thái để toàn bộ vùng capacity có thể được ghi lại. Nội dung cũ vẫn còn trong bộ nhớ nhưng không nên coi là dữ liệu mới hợp lệ.

### rewind(): đọc lại từ đầu mà không mở rộng limit

```java
buffer.rewind();
// position=0, limit giữ nguyên
```

Dùng rewind() khi muốn đọc lại cùng vùng dữ liệu. Nếu limit là 3, rewind() vẫn giữ limit bằng 3; nó không làm cho các byte sau limit trở nên truy cập được.

### compact(): giữ dữ liệu còn lại để ghi tiếp

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {10, 20, 30, 40, 50});
buffer.flip();

buffer.get(); // Đọc 10
buffer.get(); // Đọc 20

buffer.compact();
// Ba byte còn lại được chuyển về đầu buffer.
// position=3, limit=8, capacity=8
```

Sau compact(), các byte chưa đọc được giữ ở đầu buffer; position đặt ngay sau chúng để ứng dụng ghi dữ liệu mới tiếp theo. Khi cần đọc toàn bộ vùng đã tích lũy, gọi flip() lại.

## 6. Trạng thái buffer khi đọc/ghi qua Channel

Channel đọc dữ liệu vào buffer từ position đến limit. Nó không ghi vượt qua limit chỉ vì capacity còn chỗ.

Ví dụ đọc từ ReadableByteChannel:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ReadableByteChannel;

static int readOnce(ReadableByteChannel channel, ByteBuffer buffer)
        throws IOException {
    buffer.clear();
    int bytesRead = channel.read(buffer);
    buffer.flip();
    return bytesRead;
}
```

Sau khi channel.read(buffer) ghi byte vào buffer, position được tăng theo số byte đã đọc. Gọi flip() để đặt limit tại vị trí đó và position về 0 trước khi ứng dụng đọc dữ liệu.

Với channel không chặn hoặc khi đọc theo vòng lặp, phải xử lý kết quả 0 và -1 theo hợp đồng của channel. -1 biểu thị EOF; không tiếp tục xử lý buffer như thể có dữ liệu mới.

### Ghi buffer vào WritableByteChannel

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.WritableByteChannel;

static void writeFully(WritableByteChannel channel, ByteBuffer buffer)
        throws IOException {
    while (buffer.hasRemaining()) {
        channel.write(buffer);
    }
}
```

Channel có thể ghi ít byte hơn số byte còn lại. Vòng lặp dựa trên hasRemaining() bảo đảm tiếp tục cho đến khi vùng [position, limit) đã được ghi hết khi thao tác ghi có thể tiếp tục tạo tiến triển, chẳng hạn với channel blocking. Với non-blocking channel, không dùng vòng lặp chờ bận này: chỉ ghi khi channel sẵn sàng, giữ buffer nếu vẫn còn remaining và đăng ký tiếp tục ghi khi có sự kiện ghi được.

## 7. Slice và duplicate có trạng thái riêng

slice() và duplicate() tạo buffer mới có trạng thái position/limit độc lập với buffer gốc, nhưng nội dung có thể dùng chung vùng nhớ.

| Phương thức | Capacity của buffer mới | Position ban đầu | Limit ban đầu | Nội dung |
| --- | --- | ---: | ---: | --- |
| slice() | Số phần tử còn lại của buffer gốc | 0 | Capacity mới | Chia sẻ vùng còn lại |
| duplicate() | Bằng capacity của buffer gốc | Bằng position gốc | Bằng limit gốc | Chia sẻ nội dung |

Ví dụ:

```java
ByteBuffer original = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50}
);
original.position(1);
original.limit(4);

ByteBuffer slice = original.slice();

System.out.println(slice.position()); // 0
System.out.println(slice.limit());    // 3
System.out.println(slice.capacity()); // 3
System.out.println(slice.get(0));     // 20
```

Slice có chỉ số 0 ánh xạ đến vị trí 1 của buffer gốc. Chỉ số tuyệt đối của slice phải nhỏ hơn limit của slice, không phải capacity hoặc limit của buffer gốc.

### Dùng slice để giới hạn một vùng dữ liệu

```java
ByteBuffer original = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50}
);
original.position(1);
original.limit(4);

ByteBuffer region = original.slice();
region.put(0, (byte) 99);

System.out.println(original.get(1)); // 99: nội dung được chia sẻ
System.out.println(region.position()); // 0: position của region độc lập
```

Ghi qua slice thay đổi nội dung vùng nhớ chung, nhưng không làm position của buffer gốc thay đổi.

### duplicate giữ cùng biên nhưng có trạng thái riêng

```java
ByteBuffer original = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40}
);
original.position(1);
original.limit(3);

ByteBuffer copyOfState = original.duplicate();
copyOfState.get();

System.out.println(original.position());    // 1
System.out.println(copyOfState.position()); // 2
```

Tên duplicate() không có nghĩa sao chép byte sang vùng nhớ mới. Hai buffer dùng chung nội dung, nhưng có position, limit và mark riêng.

## 8. ByteBuffer.wrap với offset và length

ByteBuffer.wrap(array, offset, length) tạo buffer có capacity bằng độ dài toàn mảng, position bằng offset và limit bằng offset + length.

```java
byte[] bytes = {10, 20, 30, 40, 50, 60};
ByteBuffer wrapped = ByteBuffer.wrap(bytes, 2, 3);

System.out.println(wrapped.position()); // 2
System.out.println(wrapped.limit());    // 5
System.out.println(wrapped.capacity()); // 6
```

Điểm cần chú ý: position ban đầu là 2, nhưng các thao tác tuyệt đối vẫn dùng index theo hệ chỉ số của buffer và chỉ kiểm tra index nhỏ hơn limit. Vì vậy get(1) vẫn có thể truy cập byte ở vị trí 1 của mảng, dù vị trí đó nằm trước position ban đầu.

Nếu muốn tạo một buffer con có index bắt đầu từ 0 và chỉ nhìn thấy đúng vùng [offset, offset + length), hãy thiết lập position/limit rồi gọi slice():

```java
byte[] bytes = {10, 20, 30, 40, 50, 60};

ByteBuffer region = ByteBuffer.wrap(bytes);
region.position(2);
region.limit(5);

ByteBuffer isolatedView = region.slice();

System.out.println(isolatedView.position()); // 0
System.out.println(isolatedView.limit());    // 3
System.out.println(isolatedView.capacity()); // 3
System.out.println(isolatedView.get(0));     // 30
```

isolatedView giới hạn truy cập theo vùng đã chọn, dù nội dung vẫn chia sẻ với mảng gốc.

## 9. Buffer chỉ đọc và giới hạn truy cập

asReadOnlyBuffer() tạo view chỉ đọc. Giới hạn index vẫn dựa trên limit, và mọi thao tác ghi đều bị từ chối:

```java
ByteBuffer writable = ByteBuffer.wrap(
        new byte[] {10, 20, 30}
);
ByteBuffer readOnly = writable.asReadOnlyBuffer();

System.out.println(readOnly.get(2)); // 30
// readOnly.put(1, (byte) 99);       // ReadOnlyBufferException
```

ReadOnlyBufferException là một kiểm tra riêng với kiểm tra biên. Một index nằm trong limit không làm cho thao tác ghi trở nên hợp lệ nếu buffer chỉ đọc.

## 10. Chọn đúng exception theo thao tác

| Thao tác | Điều kiện vi phạm | Exception thường gặp |
| --- | --- | --- |
| get() tương đối | remaining() == 0 | BufferUnderflowException |
| get(index) tuyệt đối | Index âm hoặc index >= limit | IndexOutOfBoundsException |
| put(byte) tương đối | remaining() == 0 | BufferOverflowException |
| put(index, byte) tuyệt đối | Index âm hoặc index >= limit | IndexOutOfBoundsException |
| Ghi vào read-only buffer | Buffer không cho phép ghi | ReadOnlyBufferException |
| Đặt position/limit sai invariant | Giá trị vượt miền hợp lệ | IllegalArgumentException |

Không bắt một exception chung rồi bỏ qua mọi lỗi. Hãy xử lý theo hợp đồng của thao tác và xác định buffer đang ở trạng thái đọc, ghi hay chỉ đọc.

## 11. Checklist trước khi truy cập buffer

| Câu hỏi | Cách xác nhận |
| --- | --- |
| Index có âm không? | Index phải từ 0 trở lên |
| Index có nhỏ hơn limit không? | Kiểm tra index < buffer.limit() |
| Thao tác tương đối còn phần tử không? | Dùng hasRemaining() hoặc remaining() |
| Đang đọc hay ghi? | Kiểm tra quy ước trạng thái và vị trí trước thao tác |
| Có vừa gọi flip() hoặc compact() không? | Xem lại position/limit sau chuyển trạng thái |
| Có đang dùng slice không? | Dùng limit của slice, không dùng limit gốc |
| Có phải read-only buffer không? | Kiểm tra nguồn tạo buffer trước khi ghi |
| Có làm việc với channel không? | Đọc/ghi trong vùng từ position đến limit |
| Có cần giữ dữ liệu cũ không? | Dùng compact() thay vì clear() |
| Có định dùng capacity làm cận truy cập? | Chỉ dùng capacity để hiểu dung lượng; dùng limit để xác thực index |

## 12. Bài tập thực hành

### Bài 1 — Capacity lớn hơn limit

Tạo buffer có capacity 10, ghi 4 byte rồi gọi flip(). Xác định position, limit và capacity. Thử get(3) và get(4), giải thích kết quả.

### Bài 2 — Relative và absolute

Đọc một byte bằng get(), sau đó đọc index 3 bằng get(3). Ghi lại position sau mỗi thao tác và giải thích vì sao chỉ thao tác tương đối làm position tăng.

### Bài 3 — Ghi theo limit

Tạo buffer capacity 8, đặt limit bằng 3. Thử put(2, value) và put(3, value). Vì sao index 3 không hợp lệ dù nhỏ hơn capacity?

### Bài 4 — Vòng đời buffer

Ghi dữ liệu, gọi flip(), đọc một phần, gọi compact(), ghi tiếp rồi flip() lại. Theo dõi position/limit/capacity sau mỗi bước.

### Bài 5 — Slice

Tạo buffer gốc, chọn một vùng bằng position/limit rồi gọi slice(). Chứng minh slice có index bắt đầu từ 0, limit riêng và nội dung chia sẻ.

### Bài 6 — Channel

Đọc dữ liệu từ một ReadableByteChannel vào buffer. Gọi flip() trước khi đọc byte; sau khi xử lý, chọn clear() hoặc compact() tùy việc có cần giữ byte chưa xử lý hay không.

## Tài liệu chính thức

- [Java SE 16 — Buffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/Buffer.html) — invariant, position, limit, capacity và các thao tác chuyển trạng thái.
- [Java SE 16 — ByteBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html) — đọc/ghi tương đối, tuyệt đối, slice, duplicate và read-only view.
- [Java SE 16 — ByteBuffer.wrap](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html#wrap(byte%5B%5D,int,int)) — trạng thái position/limit/capacity khi bọc một vùng mảng.
- [Java SE 25 — Buffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/Buffer.html) — xác nhận mô hình buffer tiếp tục được hỗ trợ trong JDK hiện đại.
- [Java SE 25 — ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html) — API NIO hiện hành.

**Nguyên tắc áp dụng:** capacity là dung lượng tối đa, limit là biên truy cập hiện tại và position là vị trí thao tác tương đối tiếp theo. Luôn kiểm tra index theo limit, dùng remaining() cho thao tác tương đối và chuyển trạng thái buffer đúng với chu trình đọc/ghi.
