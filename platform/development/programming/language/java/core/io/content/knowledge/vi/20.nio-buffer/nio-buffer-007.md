# `remaining()`, `hasRemaining()` và lỗi tràn hoặc thiếu NIO Buffer

## 1. Mục tiêu bài học

Trong Java NIO, một `Buffer` không chỉ là vùng nhớ chứa dữ liệu. Nó còn có một **trạng thái đọc/ghi** gồm `capacity`, `limit` và `position`. Hai phương thức `remaining()` và `hasRemaining()` trả lời câu hỏi về khoảng còn lại **giữa position và limit**, chứ không tự biết khoảng ấy chứa dữ liệu có ý nghĩa hay có đủ chỗ trống trong file.

Sau bài này, bạn có thể:

- Tính `remaining()` và giải thích `hasRemaining()` từ trạng thái buffer.
- Dùng đúng `flip()`, `clear()`, `rewind()` và `compact()` để chuyển qua lại giữa ghi dữ liệu vào buffer và đọc dữ liệu từ buffer.
- Phân biệt `BufferUnderflowException` (đọc tương đối thiếu dữ liệu) với `BufferOverflowException` (ghi tương đối không đủ khoảng trống).
- Nhận biết các ngoại lệ khác: `IndexOutOfBoundsException`, `ReadOnlyBufferException`; không nhầm EOF của channel với buffer underflow.
- Viết vòng lặp đọc/ghi `ByteBuffer` qua `FileChannel`, bao gồm xử lý trường hợp một lần ghi chưa tiêu thụ hết buffer.

Các ví dụ dùng Java 17+ và các lớp `java.nio.Buffer`, `java.nio.ByteBuffer`, `java.nio.BufferUnderflowException`, `java.nio.BufferOverflowException`. Nguyên tắc cơ bản cũng áp dụng cho các buffer có kiểu phần tử khác như `CharBuffer`, `IntBuffer` hoặc `DoubleBuffer`; chú ý đơn vị đếm của chúng là **phần tử**, không nhất thiết là byte.

## 2. Bộ ba `position`, `limit`, `capacity`

Một buffer duy trì các giá trị:

| Thuộc tính | Ý nghĩa | Ràng buộc |
| --- | --- | --- |
| `capacity()` | Số phần tử tối đa mà buffer có thể chứa | `capacity >= 0`, không đổi trong vòng đời buffer |
| `limit()` | Ranh giới độc quyền của vùng có thể truy cập theo trạng thái hiện tại | `0 <= limit <= capacity` |
| `position()` | Vị trí của lần đọc/ghi **tương đối** tiếp theo | `0 <= position <= limit` |
| `mark` | Vị trí đánh dấu tùy chọn bằng `mark()` để `reset()` quay lại | Nếu đã đặt, `mark <= position` |

**Công thức cốt lõi:**

```text
remaining() = limit() - position()
hasRemaining() = (position() < limit())
               = (remaining() > 0)
```

Vì API duy trì `0 <= position <= limit`, `remaining()` không âm. Một buffer có thể còn sức chứa vật lý (`capacity > limit`) mà `remaining() == 0`, vì chỉ khoảng từ `position` tới **limit hiện tại** mới là khoảng có thể dùng cho thao tác tương đối.

Minh họa buffer byte có `capacity = 8`:

```text
index:       0 1 2 3 4 5 6 7 |8 (capacity)
             . . . . . . . .
                       ^     ^
                  position=5 limit=8
remaining=8-5=3; hasRemaining=true
```

Nếu `position = limit = 8` thì `remaining = 0` và `hasRemaining = false`. Nếu chỉnh `limit` xuống 6 và `position` là 6, kết quả cũng bằng 0 **dù capacity vẫn là 8**.

`remaining()` không đo kích thước dữ liệu đã ghi trong quá khứ; ý nghĩa khoảng `[position, limit)` do bạn xác lập theo pha vận hành:

- Trong **write mode** (ví dụ buffer mới tạo hoặc sau `clear()/compact()`), `remaining()` thường là số phần tử có thể ghi thêm.
- Trong **read mode** (sau `flip()`), `remaining()` thường là số phần tử sẵn sàng được tiêu thụ, **nếu** dữ liệu trước đó đã được chuẩn bị đúng.

Các khái niệm read/write mode ở đây là **quy ước sử dụng** do lập trình viên thiết lập bằng vị trí và giới hạn. `ByteBuffer` không có thuộc tính boolean `isReadMode()` và sẽ không tự chặn mọi thao tác sai pha.

## 3. Trạng thái điển hình của buffer

Giả sử `ByteBuffer buffer = ByteBuffer.allocate(6)`. Buffer mới có `position = 0`, `limit = capacity = 6`.

### Bước 1: ghi 4 byte vào buffer

```text
Sau put([10,20,30,40]):
index:       0   1   2   3   4   5
value:      10  20  30  40   ?   ?
                           ^
                         position=4; limit=6
remaining = 2  (chỗ có thể ghi tiếp theo write mode)
```

### Bước 2: `flip()` để chuẩn bị đọc

`flip()` đặt `limit = position` cũ rồi `position = 0`; mark bị loại bỏ.

```text
Sau flip():
index:       0   1   2   3   4   5
value:      10  20  30  40   ?   ?
             ^               ^
         position=0        limit=4
remaining = 4  (số byte đã ghi mà pha đọc chuẩn bị tiêu thụ)
```

Lúc này `get()` đọc byte tại position rồi tăng position. Sau khi đọc 3 byte, `position = 3`, `limit = 4` và `remaining = 1`.

### Bước 3: `compact()` giữ phần chưa đọc

`compact()` sao chép phần `[position, limit)` chưa đọc về đầu buffer, sau đó đặt `position` bằng số phần tử vừa giữ lại, `limit = capacity` và loại bỏ mark. Nếu còn byte 40 chưa đọc:

```text
Trước compact:  position=3, limit=4, remaining=1
Sau compact:   byte 40 được chuyển về index 0
                position=1, limit=6, remaining=5
```

Buffer trở về trạng thái phù hợp để **ghi nối tiếp** từ position 1. Nếu ghi thêm byte 50 rồi `flip()`, buffer đọc được lần lượt 40 và 50. Đừng gọi `clear()` thay cho `compact()` khi dữ liệu chưa đọc cần được giữ lại: `clear()` chỉ đặt lại chỉ số, không bảo tồn ranh giới của phần đang chờ xử lý.

## 4. Ví dụ Java 17+ hoàn chỉnh: theo dõi `remaining()` và `hasRemaining()`

Tạo tệp **`BufferLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.Arrays;

public class BufferLifecycleDemo {
    private static void state(String label, ByteBuffer buffer) {
        System.out.printf(
                "%s: position=%d, limit=%d, capacity=%d, remaining=%d, has=%s%n",
                label,
                buffer.position(),
                buffer.limit(),
                buffer.capacity(),
                buffer.remaining(),
                buffer.hasRemaining()
        );
    }

    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(6);
        state("new", buffer);

        buffer.put(new byte[] {10, 20, 30, 40});
        state("after put", buffer);

        buffer.flip();
        state("after flip", buffer);

        System.out.println("first=" + buffer.get());
        state("after get", buffer);

        byte[] pair = new byte[2];
        buffer.get(pair);
        System.out.println("pair=" + Arrays.toString(pair));
        state("after pair", buffer);

        buffer.compact();
        state("after compact", buffer);

        buffer.put((byte) 50);
        buffer.flip();

        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        System.out.println("result=" + Arrays.toString(result));
        state("at end", buffer);
    }
}
```

```bash
javac BufferLifecycleDemo.java
java BufferLifecycleDemo
```

Stdout khi chạy thành công:

```text
new: position=0, limit=6, capacity=6, remaining=6, has=true
after put: position=4, limit=6, capacity=6, remaining=2, has=true
after flip: position=0, limit=4, capacity=6, remaining=4, has=true
first=10
after get: position=1, limit=4, capacity=6, remaining=3, has=true
pair=[20, 30]
after pair: position=3, limit=4, capacity=6, remaining=1, has=true
after compact: position=1, limit=6, capacity=6, remaining=5, has=true
result=[40, 50]
at end: position=2, limit=2, capacity=6, remaining=0, has=false
```

Điểm quan trọng: ở dòng `after put`, `remaining = 2` nghĩa là **hai ô còn trống cho thao tác put trong pha ghi**. Sau `flip`, `remaining = 4` nghĩa là **bốn byte đang chờ đọc**. Hai phép đo dùng cùng công thức nhưng được diễn giải theo pha khác nhau.

`compact()` giữ byte 40 còn chưa đọc; byte 50 được nối ngay sau nó. Dòng `result=[40, 50]` xác nhận xử lý chunk tiếp theo mà không làm mất phần dữ liệu đang chờ từ chunk trước.

## 5. `BufferUnderflowException`: yêu cầu đọc vượt `limit`

`BufferUnderflowException` là ngoại lệ runtime khi một thao tác **đọc tương đối** từ buffer đòi hỏi nhiều phần tử hơn `remaining()`. Ví dụ:

```java
ByteBuffer b = ByteBuffer.allocate(2);
b.get(); // BufferUnderflowException? KHÔNG:
         // allocate(2) tạo position=0, limit=2;
         // xét trạng thái NIO, thao tác get() vẫn có thể đọc một byte.
```

Điểm tinh tế: **buffer mới cấp phát không tự ở read mode**. Nó có `remaining = 2`, nên `get()` không ném underflow chỉ vì ứng dụng chưa chủ động `put()`. Dữ liệu đọc được từ một `ByteBuffer.allocate` mới được khởi tạo thành zero theo hợp đồng allocate, nhưng bạn chưa thiết kế dữ liệu có ý nghĩa trong giao thức ứng dụng.

Muốn ví dụ **đúng** về underflow, đặt `limit` về 0 bằng `flip()` khi chưa ghi byte nào:

```java
ByteBuffer emptyForRead = ByteBuffer.allocate(2);
emptyForRead.flip();       // position=0, limit=0
emptyForRead.get();        // BufferUnderflowException
```

Hoặc sau khi tiêu thụ toàn bộ dữ liệu hợp lệ trong read mode:

```java
ByteBuffer b = ByteBuffer.allocate(2);
b.put((byte) 7);
b.flip();                  // position=0, limit=1
b.get();                   // OK: 7; position=1
b.get();                   // BufferUnderflowException
```

Tương tự, nếu buffer chỉ còn `2` byte trong read mode nhưng yêu cầu `b.get(new byte[3])`, đây là underflow. Với các bulk `get`, API kiểm tra đủ phần tử trước khi truyền; khi thiếu, buffer position không bị dịch một phần vì lệnh thất bại.

**Quan trọng:** `BufferUnderflowException` nói rằng **buffer hiện tại** không có đủ phần tử theo limit, chứ không có nghĩa file/channel đã kết thúc. Đọc dữ liệu từ `FileChannel.read(buffer)` khi đến EOF trả `-1`; đọc từ `SocketChannel` theo chế độ nonblocking có thể trả `0` khi chưa có dữ liệu. Hai trạng thái đó khác với ngoại lệ do thao tác `ByteBuffer.get()` sai số lượng.

## 6. `BufferOverflowException`: ghi vượt `limit`

`BufferOverflowException` xuất hiện khi một thao tác **ghi tương đối** vào buffer cần nhiều phần tử hơn số lượng `remaining()` hiện tại.

```java
ByteBuffer b = ByteBuffer.allocate(2);
b.put((byte) 7);
b.put((byte) 8);
b.put((byte) 9);            // BufferOverflowException
```

Khi đã ghi 2 byte, `position = limit = capacity = 2`; `remaining = 0`. Muốn tiếp tục ghi vào buffer, cần tiêu thụ/di chuyển phần dữ liệu đang có theo đúng quy trình rồi `clear()` hoặc `compact()`. Không đơn giản gọi `flip()` sau khi buffer đầy rồi `put()` tiếp: `flip()` chuẩn bị **đọc** phần dữ liệu đã ghi, nên `position=0` và `limit=2`; một `put()` lúc này có thể ghi **đè** dữ liệu đang chờ đọc.

Điều quan trọng với bulk put:

```java
ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
ByteBuffer target = ByteBuffer.allocate(2);
target.put(source); // BufferOverflowException
```

Vì `source.remaining() = 3` nhưng `target.remaining() = 2`, thao tác `target.put(source)` ném `BufferOverflowException`; nó không được phép “chép được 2 byte rồi báo lỗi” theo hợp đồng bulk put của buffer. Hai position vẫn như trước thao tác. Cần tự chia chunk nhỏ phù hợp nếu muốn sao chép từng phần.

**Overflow của buffer không đồng nghĩa với hết dung lượng đĩa.** Nó cho biết giới hạn bộ nhớ logic trong `Buffer` hiện tại. Lỗi ghi xuống đĩa thường biểu hiện qua `IOException` hoặc ngoại lệ đặc thù hệ thống lưu trữ.

## 7. Phân biệt underflow, overflow, index và read-only

| Tình huống | Ngoại lệ hoặc kết quả điển hình | Cách xử lý |
| --- | --- | --- |
| `get()` khi `remaining() == 0` | `BufferUnderflowException` | Chỉ đọc khi còn phần tử, hoặc bổ sung dữ liệu rồi `flip()` |
| `get(byte[4])` khi remaining chỉ 3 | `BufferUnderflowException` | Giảm số byte yêu cầu hoặc thu thập thêm input |
| `put(byte)` khi remaining bằng 0 | `BufferOverflowException` | Đưa buffer qua pha tiêu thụ rồi `clear()/compact()` |
| `put(sourceBuffer)` khi source.remaining lớn hơn target.remaining | `BufferOverflowException` | Chia dữ liệu theo chunk hoặc dùng buffer đích lớn hơn |
| `get(index)` hoặc `put(index, value)` với index không hợp lệ so với limit | `IndexOutOfBoundsException` | Kiểm tra chỉ số truy cập **tuyệt đối** |
| `put(...)` vào read-only buffer | `ReadOnlyBufferException` | Dùng buffer có quyền ghi hoặc chỉ đọc từ view này |
| `FileChannel.read(buffer)` ở EOF | Trả `-1` | Hoàn tất xử lý dữ liệu cuối, không xem đây là BufferUnderflowException |
| `Channel.write(buffer)` ghi được một phần | Trả số byte thực đã ghi | Tiếp tục khi `buffer.hasRemaining()`, xử lý trường hợp không có tiến triển |

Không phải mọi truy cập sai đều ném `BufferUnderflowException` hoặc `BufferOverflowException`. Các phương thức absolute như `get(index)` thường kiểm tra index theo `limit` và ném `IndexOutOfBoundsException` khi sai; chúng **không tự thay đổi position**. Ví dụ `ByteBuffer.allocate(2).get(2)` vượt limit 2, dù không làm thay đổi trạng thái con trỏ.

`ReadOnlyBufferException` thuộc trường hợp quyền ghi của buffer, không phải số lượng còn lại. Các buffer view như `asReadOnlyBuffer()` có thể chia sẻ bộ nhớ nền nhưng ngăn ghi qua view read-only.

## 8. Ví dụ Java 17+ hoàn chỉnh: tái hiện từng lỗi

Tạo tệp **`BufferErrorsDemo.java`**:

```java
import java.nio.BufferOverflowException;
import java.nio.BufferUnderflowException;
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;

public class BufferErrorsDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(2);

        buffer.flip(); // không có byte đã put; limit=0
        try {
            buffer.get();
        } catch (BufferUnderflowException ex) {
            System.out.println("underflow: position=" + buffer.position());
        }

        buffer.clear();
        buffer.put((byte) 7).put((byte) 8);
        try {
            buffer.put((byte) 9);
        } catch (BufferOverflowException ex) {
            System.out.println("overflow: position=" + buffer.position());
        }

        buffer.flip(); // position=0, limit=2
        try {
            buffer.get(new byte[3]);
        } catch (BufferUnderflowException ex) {
            System.out.println("bulk underflow: position=" + buffer.position());
        }

        try {
            buffer.get(2); // index=2 == limit => ngoài phạm vi
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("absolute index out of bounds");
        }

        ByteBuffer readOnly = buffer.asReadOnlyBuffer();
        try {
            readOnly.put((byte) 1);
        } catch (ReadOnlyBufferException ex) {
            System.out.println("read-only write rejected");
        }

        ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
        ByteBuffer target = ByteBuffer.allocate(2);
        try {
            target.put(source);
        } catch (BufferOverflowException ex) {
            System.out.println("bulk overflow: source="
                    + source.position() + ", target=" + target.position());
        }

        System.out.println("first valid byte=" + buffer.get());
    }
}
```

```bash
javac BufferErrorsDemo.java
java BufferErrorsDemo
```

Stdout khi chạy thành công:

```text
underflow: position=0
overflow: position=2
bulk underflow: position=0
absolute index out of bounds
read-only write rejected
bulk overflow: source=0, target=0
first valid byte=7
```

Chú ý: `buffer.flip()` đầu tiên làm `limit=0` và bảo đảm underflow ở lệnh đọc sau đó; khác với ví dụ sai thường gặp là gọi `get()` ngay sau `allocate(2)` rồi mong bị underflow. Bulk read thất bại không dịch position, nên lệnh `get()` cuối đọc được byte 7 như mong đợi.

## 9. Tránh lỗi bằng cách kiểm tra khoảng còn lại

### Đọc một phần tử

Nếu yêu cầu “có thì đọc, hết buffer thì dừng”, `hasRemaining()` thích hợp:

```java
while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Xử lý value
}
```

Nhưng nếu giao thức yêu cầu **đúng 4 byte**, chỉ kiểm tra `hasRemaining()` là chưa đủ. Với `ByteBuffer`:

```java
if (buffer.remaining() >= Integer.BYTES) {
    int value = buffer.getInt();
    // Xử lý value
} else {
    // Chưa đủ 4 byte: yêu cầu thêm input, hoặc báo lỗi định dạng.
}
```

`getInt()` cần 4 byte liên tiếp; `remaining() == 1` khiến `hasRemaining()` trả true nhưng `getInt()` vẫn có thể ném `BufferUnderflowException`. `getLong()` tương tự cần 8 byte; với `CharBuffer.get()` một lần đọc cần một phần tử char.

### Ghi phần tử hoặc nhóm phần tử

```java
if (buffer.remaining() >= Long.BYTES) {
    buffer.putLong(123L);
} else {
    // Flush/consume dữ liệu hiện có, compact nếu phải giữ phần chưa dùng,
    // hoặc cấp phát buffer đủ lớn theo yêu cầu thiết kế.
}
```

Nếu cần ghi một mảng `data` với đoạn `offset` và `length`, kiểm tra số byte dự kiến cùng tính hợp lệ của offset/length. Đừng xem `hasRemaining()` là đủ cho một bulk operation lớn hơn 1 phần tử.

### Khi bắt buộc đủ toàn bộ record

Trong giao thức mạng có header cố định hoặc payload theo chiều dài, có thể phải đợi đủ dữ liệu của record. Mẫu xử lý thường là:

1. Đọc vào buffer đang ở write mode.
2. `flip()` để đọc những byte đã nhận.
3. Chỉ parse khi `remaining()` đủ cho trường dữ liệu hiện tại.
4. Nếu chưa đủ, **không tiêu thụ record dở một cách tùy tiện**; có thể dùng `mark()/reset()` khi đã kiểm soát trạng thái hoặc chỉ đọc sau khi kiểm tra đủ.
5. `compact()` để giữ những byte chưa đọc, đọc tiếp rồi lặp lại.

`mark()` lưu position, `reset()` quay lại mark. Thao tác `flip()`, `clear()`, `rewind()` và `compact()` làm mark không còn hợp lệ; gọi `reset()` khi không có mark hợp lệ ném `InvalidMarkException`. Phương thức `position(newPosition)` hoặc `limit(newLimit)` cũng có thể loại bỏ mark khi mark không còn tương thích với trạng thái mới.

## 10. `flip()`, `clear()`, `rewind()`, `compact()`: chọn đúng

| Phương thức | Position sau gọi | Limit sau gọi | Ý nghĩa |
| --- | --- | --- | --- |
| `flip()` | 0 | Position cũ | Chuyển từ ghi dữ liệu sang tiêu thụ dữ liệu |
| `clear()` | 0 | Capacity | Chuẩn bị dùng lại toàn bộ buffer; **không xóa byte vật lý** |
| `rewind()` | 0 | Giữ nguyên | Đọc/ghi lại từ đầu khoảng hiện hành; không nới limit |
| `compact()` | Số phần tử còn lại trước compact | Capacity | Giữ phần chưa tiêu thụ, chuyển sang chuẩn bị ghi thêm |

Các lệnh này thao tác **trạng thái** của buffer; `clear()` không đổ số 0 vào bộ nhớ. Sau `clear()`, bộ nhớ có thể vẫn chứa byte cũ, nhưng chương trình phải hiểu rằng trạng thái logic mới là để chuẩn bị ghi. Nếu `clear()` rồi `flip()` ngay mà chưa ghi byte nào, `limit=0` và `hasRemaining()=false`.

`compact()` chỉ có ý nghĩa theo phần chưa tiêu thụ `[position, limit)`. Khi buffer đang ở write mode, gọi `compact()` một cách vô thức có thể sao chép cả vùng mà ứng dụng chưa xem là dữ liệu hợp lệ. Cần kiểm soát pha trước khi dùng.

## 11. Vòng lặp channel: buffer còn dữ liệu chưa chắc ghi xong trong một lần

`WritableByteChannel.write(buffer)` cố gắng ghi một số byte từ khoảng `[position, limit)` hiện tại, tăng position bằng số byte thực đã ghi và **có thể chỉ ghi một phần**. Do đó:

```java
buffer.flip();
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
buffer.clear();
```

Đây là ý tưởng nền, nhưng vòng lặp như trên **có thể bận chờ vô hạn** nếu channel không ghi tiến triển (`write` liên tục trả 0, thường gặp với nonblocking channel khi chưa sẵn sàng). Phải lựa chọn cơ chế chờ đúng: với `SocketChannel` không chặn, dùng `Selector` / OP_WRITE hoặc cơ chế backpressure; với channel chặn, hiểu các hành vi I/O phù hợp.

Một điểm khác: `hasRemaining()` chỉ biết buffer còn byte đang chờ, **không** đảm bảo tài nguyên đích đang sẵn sàng, có dung lượng hoặc ghi xong sẽ bền vững. Ghi thành công vẫn phải kiểm tra tiến triển và xử lý `IOException`.

### Ví dụ đầy đủ: sao chép tệp qua `FileChannel`

Tạo tệp **`ChannelCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class ChannelCopyDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("nio-source-", ".bin");
        Path destination = Files.createTempFile("nio-dest-", ".bin");

        try {
            byte[] input = "abcdefghi".getBytes(StandardCharsets.UTF_8);
            Files.write(source, input);

            try (FileChannel from = FileChannel.open(
                         source, StandardOpenOption.READ);
                 FileChannel to = FileChannel.open(
                         destination,
                         StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer buffer = ByteBuffer.allocate(4);

                while (true) {
                    int read = from.read(buffer);
                    if (read == -1) {
                        break; // EOF của file, không phải buffer underflow
                    }
                    if (read == 0) {
                        continue; // với FileChannel thường không xảy ra ở đây
                    }

                    buffer.flip();
                    while (buffer.hasRemaining()) {
                        int written = to.write(buffer);
                        if (written == 0) {
                            throw new IOException("FileChannel write made no progress");
                        }
                    }
                    buffer.clear();
                }
            }

            System.out.println("copied bytes=" + Files.size(destination));
            System.out.println("matches=" + Arrays.equals(
                    input, Files.readAllBytes(destination)));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(destination);
        }
    }
}
```

```bash
javac ChannelCopyDemo.java
java ChannelCopyDemo
```

Stdout khi chạy thành công:

```text
copied bytes=9
matches=true
```

Giải thích từng vòng: buffer có capacity 4; `from.read(buffer)` nạp byte và tăng position; `flip()` đặt limit đến số byte đã nạp; `to.write(buffer)` chuyển một phần hoặc toàn bộ số byte còn lại, có thể phải gọi nhiều lần; `clear()` chuẩn bị buffer cho lần đọc tiếp. File dài 9 byte được truyền theo các chunk tối đa 4 byte và không bị mất chunk cuối cùng (1 byte).

Ví dụ dùng **`FileChannel` thông thường** cho file cục bộ. Với nonblocking channel, việc xử lý `read == 0` hoặc `write == 0` cần chiến lược chờ có sự kiện; không dùng vòng `continue` liên tục để đốt CPU. Trong chương trình thực tế, tạo hai file tạm liên tiếp cũng nên có cleanup phù hợp ngay cả khi lần tạo thứ hai thất bại; ở đây mục đích chính là minh họa giao thức trạng thái buffer.

## 12. Buffer view, slice và bộ nhớ dùng chung

`duplicate()`, `slice()` và `asReadOnlyBuffer()` có thể tạo những buffer chia sẻ nội dung nền nhưng có **position/limit/mark riêng**. Điều này ảnh hưởng trực tiếp đến `remaining()` và `hasRemaining()`:

```java
ByteBuffer original = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
original.position(1);
original.limit(3);          // original remaining = 2

ByteBuffer slice = original.slice(); // capacity=2, position=0, limit=2
slice.get();                // slice position=1, remaining=1

System.out.println(original.remaining()); // 2
System.out.println(slice.remaining());    // 1
```

Mặc dù nội dung nền được chia sẻ, thao tác `get()` trên `slice` không dịch position của `original`. Những thay đổi **byte dữ liệu** thông qua một view có thể nhìn thấy qua view khác, nhưng chỉ số trạng thái của chúng vẫn độc lập.

Với code đa luồng, buffer không được bảo đảm thread-safe cho truy cập đồng thời tùy ý. Nếu các luồng dùng chung buffer hoặc vùng nhớ được chia sẻ, cần chiến lược phối hợp rõ ràng; không coi `remaining()` là kết quả bất biến trước một thao tác tiếp theo.

## 13. Một số ranh giới quan trọng của kiến thức

- `remaining()` của `ByteBuffer` là số **byte**, của `CharBuffer` là số **char**, của `IntBuffer` là số **int**. Khi thiết kế dung lượng của record, tính đúng đơn vị.
- `buffer.get(byte[])` có thể phát sinh underflow nếu yêu cầu quá nhiều byte; `buffer.get(index)` là absolute, dùng kiểm tra index và không tăng position.
- `ByteBuffer.putInt` và `getInt` tiêu thụ **bốn byte**; `hasRemaining() == true` chưa đủ. Kiểm tra `remaining() >= Integer.BYTES`.
- `BufferOverflowException` không có nghĩa file hết chỗ và `BufferUnderflowException` không đồng nghĩa network EOF.
- `clear()`, `flip()`, `rewind()`, `compact()` không tự ghi xuống đĩa hoặc đọc từ socket; chúng chỉ điều chỉnh con trỏ/giới hạn và trong trường hợp compact thì sao chép phần chưa đọc trong buffer.
- Những tên **UNDERFLOW/OVERFLOW** trong API giải mã ký tự `java.nio.charset.CoderResult` là **trạng thái kết quả của coder** (có phương thức `isUnderflow()/isOverflow()`), không phải cứ gặp tên ấy là `BufferUnderflowException` hoặc `BufferOverflowException`. Khi xử lý `CharsetDecoder` hoặc `CharsetEncoder`, phải tuân theo hợp đồng trạng thái của coder.
- `ByteBuffer.allocate(...)` tạo buffer heap được khởi tạo theo mặc định của Java, nhưng “byte có giá trị 0” không tự biến thành “frame dữ liệu hợp lệ”. Hợp đồng giao thức ứng dụng vẫn cần xác định bao nhiêu byte đã được ghi/nhận hợp lệ.
- `ByteBuffer.allocateDirect(...)` có đặc điểm cấp phát và thao tác khác buffer heap; logic position/limit/remaining vẫn dùng cùng hợp đồng `Buffer`, nên không thay đổi nguyên tắc kiểm tra giới hạn.

## 14. Lỗi phổ biến và cách phòng tránh

1. **Quên `flip()` trước khi đọc byte vừa `put`.** `position` vẫn ở cuối dữ liệu, `limit` chưa thu về số byte thực đã ghi. Hãy chuyển pha rõ ràng.
2. **Quên `clear()/compact()` trước khi nạp đợt kế tiếp.** Buffer có thể hết `remaining` ở pha đọc hoặc ghi sai vị trí.
3. **Gọi `clear()` khi còn dữ liệu chưa tiêu thụ.** Trạng thái coi buffer là trống để ghi mới; dùng `compact()` khi muốn giữ phần còn lại.
4. **Hiểu nhầm `hasRemaining()` là đủ cho mọi thao tác.** Nếu chuẩn bị `getLong()`, hãy kiểm tra ít nhất 8 byte.
5. **Bắt underflow/overflow để điều khiển từng vòng lặp thông thường.** Với dữ liệu có thể kiểm tra trước, `remaining()` giúp code rõ hơn và tránh ngoại lệ làm luồng xử lý chính.
6. **Nhầm overflow buffer với lỗi ổ đĩa.** Xem lại `position/limit` và luồng `flip/clear` trước.
7. **Sao chép buffer-to-buffer nhưng không kiểm tra kích thước đích.** `target.put(source)` yêu cầu đủ chỗ cho toàn bộ `source.remaining()`; hãy chia chunk hoặc dùng vùng đủ lớn.
8. **Gọi `get(index)` và mong position tăng.** Absolute access không dịch position; kiểm tra bằng `getFilePointer` không liên quan, phải dùng `position()` của buffer.
9. **Không xử lý partial write từ channel.** Một lần `write(buffer)` không được đảm bảo tiêu thụ hết byte; dùng vòng lặp có xử lý tiến triển.
10. **Vòng lặp nonblocking bận chờ khi kết quả I/O bằng 0.** Sử dụng selector/event và không quay vòng vô hạn.
11. **Dùng `limit=capacity` làm số byte đã nhận.** Khi channel read được ít byte, `flip()` giúp limit phản ánh position trước đó; `capacity` chỉ là kích thước tối đa.
12. **Chia sẻ view rồi tưởng position chung.** `slice` và `duplicate` có con trỏ riêng dù nội dung nền có thể chung.

## 15. Câu hỏi và bài tập tự kiểm tra

1. Buffer có `capacity=16`, `limit=11` và `position=7`. `remaining()` và `hasRemaining()` là gì? Nếu `position=11` thì sao?
2. Buffer mới `allocate(8)` có `remaining=8`. Điều này có chứng minh ứng dụng đã ghi 8 byte dữ liệu có nghĩa vào đó không?
3. Sau `put` 5 byte vào buffer capacity 8, vì sao phải `flip()` trước khi đọc 5 byte ấy? Sau flip, `position` và `limit` là bao nhiêu?
4. `remaining()=3` và `hasRemaining()=true`, gọi `getInt()` có hợp lệ không? Cần kiểm tra điều gì?
5. Buffer vừa chứa 10 byte dữ liệu, đã đọc 7 byte. Nên dùng `clear()` hay `compact()` nếu phải giữ 3 byte cuối để ghép với chunk mới?
6. Vì sao `ByteBuffer.get(10)` khi `limit=10` gây `IndexOutOfBoundsException`, trong khi `get()` lúc `position=limit` gây `BufferUnderflowException`?
7. Tại sao `FileChannel.read(buffer)==-1` có ý nghĩa khác với `BufferUnderflowException`?
8. Có được kết luận đã gửi thành công toàn bộ dữ liệu nếu một lần `SocketChannel.write(buffer)` trả về số byte nhỏ hơn `buffer.remaining()` trước lúc gọi không? Bạn sẽ thiết kế vòng lặp thế nào?
9. Hai buffer `original` và `original.slice()` chia sẻ memory; gọi `slice.get()` có tăng `original.position()` không?
10. Hãy dự đoán toàn bộ stdout của `BufferLifecycleDemo`, chạy rồi đối chiếu; sửa chương trình để `compact()` giữ 2 byte cuối thay vì 1.

## 16. Tóm lược kiến thức

Cốt lõi của NIO Buffer là **`0 <= position <= limit <= capacity`**, từ đó:

```text
remaining() = limit - position
hasRemaining() = remaining() > 0
```

Trong pha ghi, số còn lại thường là chỗ để ghi thêm; trong pha đọc, đó là số phần tử còn để tiêu thụ. `BufferUnderflowException` báo thao tác đọc tương đối vượt khoảng hiện có, `BufferOverflowException` báo thao tác ghi tương đối vượt khoảng còn trống. Dùng `flip()` để bắt đầu đọc dữ liệu vừa nạp, `clear()` để dùng lại khi đã tiêu thụ xong, `compact()` để giữ phần còn sót, và `remaining()` để kiểm tra đủ cho đúng **số phần tử** mà API sắp dùng. Khi tích hợp channel, việc buffer còn phần tử chỉ là một điều kiện trong vòng lặp; EOF, partial write và nonblocking readiness phải được xử lý riêng.
