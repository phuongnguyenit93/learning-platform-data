# Java 11 — position, limit và phần dữ liệu còn lại

**Chủ đề:** Java 11 → Buffer và nén. Bài học giải thích cách Java NIO quản lý vùng dữ liệu đã ghi, đã đọc và chưa xử lý bằng ba thuộc tính `position`, `limit`, `capacity`; vì sao `remaining()` là số phần tử **có thể đọc/ghi trong cửa sổ hiện tại**; và cách tránh mất, lặp hoặc ghi dữ liệu thừa khi truyền file, kênh I/O hoặc xử lý luồng GZIP. Các API được trình bày có sẵn trên JDK 11 và tiếp tục là kiến thức nền tảng hữu ích trong ứng dụng Java hiện nay.

**Kết quả mong đợi:** Người học có thể giải thích chính xác các trạng thái của `ByteBuffer`, tính `remaining()` sau từng thao tác, chọn `flip`/`clear`/`rewind`/`compact` đúng mục đích, quản lý đọc/ghi từng phần, và xử lý đúng **số byte thực sự nhận được** khi giải nén hoặc truyền dữ liệu.

## 1. Buffer là vùng chứa dữ liệu có con trỏ trạng thái

Trong `java.nio`, một `Buffer` lưu một dãy hữu hạn phần tử cùng kiểu. `ByteBuffer` biểu diễn **byte**; các lớp như `CharBuffer`, `IntBuffer` hay `LongBuffer` dùng phần tử tương ứng. Buffer có **nội dung** và các thuộc tính **điều khiển cửa sổ truy cập**. Nội dung có thể còn trong bộ nhớ dù trạng thái không cho phép đọc đến nó.

| Thuộc tính | Ý nghĩa chính xác | Có thay đổi không? |
| --- | --- | --- |
| `capacity()` | Số phần tử tối đa mà **instance** buffer có thể chứa, tính bằng byte với `ByteBuffer`. | Cố định trong đời sống instance. |
| `limit()` | Chỉ số **đầu tiên không được truy cập** bởi thao tác tương đối; vùng hợp lệ kết thúc ngay trước `limit`. | Có thể thay đổi, từ 0 đến capacity. |
| `position()` | Chỉ số phần tử **tiếp theo** mà thao tác `get` hoặc `put` tương đối sẽ dùng. | Tự tăng theo số phần tử đã chuyển; cũng có thể đặt tường minh. |
| `remaining()` | Số phần tử từ position đến limit, **không gồm limit**. | Tính lại từ trạng thái hiện tại. |
| `hasRemaining()` | Có ít nhất một phần tử còn trong vùng position..limit không? | Tương đương `remaining() > 0`. |
| `mark()/reset()` | Đánh dấu một position để có thể quay lại khi cần parse/thử đọc. | Mark có thể mất khi thay đổi trạng thái. |

Bất biến luôn được giữ bởi API:

~~~text
0 <= position <= limit <= capacity
remaining = limit - position
hasRemaining = (remaining > 0)
~~~

Khi mark có hiệu lực, `0 <= mark <= position`. Mark **có thể chưa được thiết lập**; gọi `reset()` khi chưa có mark sẽ ném `InvalidMarkException`.

Hình dung cửa sổ truy cập của một `ByteBuffer` capacity 8, position 2, limit 6:

~~~text
Index:        0   1  |2   3   4   5|  6   7
                     ^position       ^limit  ^capacity=8
Đã đi qua:   [0,2)
Còn lại:     [2,6) = 4 byte
Ngoài limit: [6,8) không được get/put tương đối lúc này
~~~

**Điểm quan trọng:** `remaining()` **không phải tổng byte hữu ích đang nằm trong vùng nhớ**, cũng không luôn là số byte “chưa ghi”. Ý nghĩa nghiệp vụ phụ thuộc buffer đang được dùng để **ghi vào** hay **đọc ra**.

## 2. Ghi và đọc sử dụng cùng trạng thái nhưng hiểu khác nhau

### 2.1. Buffer mới: cửa sổ dùng để ghi

~~~java
ByteBuffer buf = ByteBuffer.allocate(8);
~~~

Ngay sau `allocate(8)`:

~~~text
position=0, limit=8, capacity=8, remaining=8
~~~

Buffer đang sẵn sàng cho thao tác `put`. Lúc này `remaining() == 8` nghĩa là **còn 8 ô có thể ghi**, không chứng minh 8 byte dữ liệu hợp lệ đã được cung cấp. Nội dung vùng nhớ được khởi tạo bằng byte 0, nhưng chúng **không tự động thành payload mà ứng dụng muốn gửi**.

Sau `buf.put(new byte[]{65,66,67,68,69})` (tương ứng ASCII `ABCDE`), position bằng 5, limit vẫn 8, remaining bằng 3. Ba ô còn lại là **chỗ trống để ghi thêm**. Nếu lập tức gọi `get()` mà chưa thay đổi trạng thái, bạn bắt đầu đọc ở index 5, tức là ngoài dữ liệu vừa ghi.

### 2.2. `flip()` chuyển cửa sổ sang đọc

~~~java
buf.flip();
~~~

`flip()` đặt:

~~~text
limit = position cũ = 5
position = 0
remaining = 5
~~~

Giờ `remaining() == 5` nghĩa là **có 5 byte có thể lấy ra**, từ index 0 đến 4. Sau `buf.get()` hai lần, position bằng 2, remaining bằng 3: ba byte chưa đọc ở index 2, 3, 4 là `CDE`.

### 2.3. Không dùng capacity thay cho limit

Sai:

~~~java
byte[] data = new byte[buf.capacity()];
buf.get(data);
~~~

Nếu buffer đang ở chế độ đọc với `position=2`, `limit=5`, `capacity=8`, `get(data)` yêu cầu 8 byte nhưng chỉ còn 3; `BufferUnderflowException` sẽ xảy ra. Ngay cả khi đủ chỗ trong backing array, **limit mới là ranh giới của cửa sổ thao tác**.

Đúng khi muốn lấy chính xác phần chưa đọc:

~~~java
byte[] data = new byte[buf.remaining()];
buf.get(data);
~~~

Đây là **đoạn minh họa**, giả sử `buf` đã ở trạng thái đọc. Sau `get(data)`, position tăng đúng bằng độ dài `data` và thường đến limit. Với dữ liệu lớn, tránh tạo mảng theo `remaining()` không giới hạn nếu bên gửi có thể kiểm soát kích thước; xử lý theo chunk và giới hạn dung lượng.

## 3. Những thao tác chuyển trạng thái dễ nhầm

| Thao tác | Position mới | Limit mới | Có di chuyển byte không? | Sử dụng khi |
| --- | --- | --- | --- | --- |
| `flip()` | 0 | Position trước thao tác | Không | Đã `put`/channel-read xong một đợt, cần `get`/channel-write. |
| `clear()` | 0 | Capacity | Không | Dữ liệu cũ đã xử lý xong hoặc có thể bỏ, muốn ghi lại từ đầu. |
| `rewind()` | 0 | Giữ nguyên limit | Không | Muốn đọc lại cùng cửa sổ đã xác định. |
| `compact()` của `ByteBuffer` | Số phần tử còn lại trước compact | Capacity | **Có**, chuyển phần chưa tiêu thụ về đầu | Cần giữ dữ liệu chưa đọc/chưa gửi để ghi bổ sung. |
| `position(n)` | n | Giữ limit | Không | Di chuyển con trỏ trong cửa sổ hợp lệ. |
| `limit(n)` | Không quá n; nếu position cũ > n thì hạ xuống n | n | Không | Thu hẹp/mở cửa sổ hợp lệ trong capacity. |

Cả `flip`, `clear`, `rewind` và `compact` đều làm mark đã đặt mất hiệu lực. **`clear()` không xóa byte khỏi bộ nhớ**, cũng không phải thao tác bảo mật để xóa dữ liệu nhạy cảm; nó chỉ đổi con trỏ và giới hạn.

Ví dụ sau khi viết `ABCDE` và đọc `AB`:

~~~text
Trước compact:
buffer:  A  B | C  D  E | ?  ?  ?
position=2, limit=5, capacity=8, remaining=3

Sau compact:
buffer:  C  D  E | (vùng có thể ghi tiếp)
position=3, limit=8, capacity=8, remaining=5

Sau put('F') rồi flip():
buffer đọc: C  D  E  F
position=0, limit=4, capacity=8, remaining=4
~~~

`compact()` giữ **đúng 3 byte chưa đọc** và tạo không gian để ghép thêm dữ liệu. Ngược lại, gọi `clear()` khi còn `CDE` sẽ cho phép ghi đè chúng và có thể làm mất bản tin chưa parse hết.

**Quy tắc nhớ:** `put → flip → get → compact/clear → put tiếp`. `compact` chỉ cần khi **còn dữ liệu phải bảo toàn**; nếu đã tiêu thụ hết, `clear` đơn giản hơn. Khi gọi `compact` trên buffer read-only, Java ném `ReadOnlyBufferException`.

## 4. Chương trình Java 11 hoàn chỉnh: mọi con số đều kiểm chứng được

Chương trình sau kiểm tra trạng thái sau các bước ghi, đọc, compact và tạo view. Không cần Internet, thư viện ngoài hoặc filesystem. Lưu vào file **`BufferRemainingDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class BufferRemainingDemo {
    private BufferRemainingDemo() {
    }

    private static void state(String name, ByteBuffer b) {
        System.out.printf(
            "%s: position=%d limit=%d capacity=%d remaining=%d%n",
            name, b.position(), b.limit(), b.capacity(), b.remaining());
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        state("new", b);

        b.put("ABCDE".getBytes(StandardCharsets.US_ASCII));
        state("put5", b);

        b.flip();
        state("flip", b);

        byte[] first = new byte[2];
        b.get(first);
        System.out.println("first=" +
            new String(first, StandardCharsets.US_ASCII));
        state("read2", b);

        b.compact();
        state("compact", b);

        b.put((byte) 'F');
        state("putF", b);

        b.flip();
        byte[] rest = new byte[b.remaining()];
        b.get(rest);
        System.out.println("remaining-data=" +
            new String(rest, StandardCharsets.US_ASCII));
        state("finish", b);

        byte[] source = {10, 20, 30, 40, 50, 60};
        ByteBuffer wrapped = ByteBuffer.wrap(source, 2, 3);
        state("wrap-window", wrapped);

        ByteBuffer view = wrapped.slice();
        state("slice", view);

        byte[] copy = new byte[view.remaining()];
        view.get(copy);
        System.out.println("slice-bytes=" + Arrays.toString(copy));
        state("original-window", wrapped);
    }
}
~~~

Biên dịch và chạy bằng JDK 11 trở lên, với tệp mã nguồn được lưu UTF-8:

~~~bash
javac -encoding UTF-8 BufferRemainingDemo.java
java BufferRemainingDemo
~~~

**Stdout chính xác:**

~~~text
new: position=0 limit=8 capacity=8 remaining=8
put5: position=5 limit=8 capacity=8 remaining=3
flip: position=0 limit=5 capacity=8 remaining=5
first=AB
read2: position=2 limit=5 capacity=8 remaining=3
compact: position=3 limit=8 capacity=8 remaining=5
putF: position=4 limit=8 capacity=8 remaining=4
remaining-data=CDEF
finish: position=4 limit=4 capacity=8 remaining=0
wrap-window: position=2 limit=5 capacity=6 remaining=3
slice: position=0 limit=3 capacity=3 remaining=3
slice-bytes=[30, 40, 50]
original-window: position=2 limit=5 capacity=6 remaining=3
~~~

**Lý giải output:**

1. `new`: tất cả 8 ô còn nằm trong cửa sổ ghi, dù chưa ghi payload.
2. `put5`: năm byte `ABCDE` được ghi, position tăng lên 5, còn 3 vị trí ghi tiếp.
3. `flip`: giới hạn được hạ xuống 5; số byte có thể đọc trở thành 5.
4. `get(first)` lấy hai byte `AB`, position tăng lên 2; ba byte `CDE` chưa đọc.
5. `compact` dồn `CDE` về index 0..2, đặt position=3, limit=capacity=8.
6. `putF` ghi tiếp vào index 3; `flip` và `get(rest)` xuất `CDEF`, kết thúc tại position=limit=4.
7. `ByteBuffer.wrap(source, 2, 3)` **không tạo buffer capacity 3**: capacity vẫn bằng `source.length=6`, position=2, limit=5, remaining=3. `slice()` tạo view của vùng còn lại với position=0, limit=capacity=3, dùng chung byte nhưng con trỏ độc lập. Đọc hết `view` không đổi position của `wrapped`.

Không suy từ `Arrays.toString(source)` hay `ByteBuffer.toString()` rằng tất cả byte trong backing array đều là payload đã xác thực; chúng có thể chứa byte cũ ngoài giới hạn hiện tại.

## 5. get/put tương đối, tuyệt đối và lỗi ranh giới

`ByteBuffer` có hai loại truy cập:

- **Relative**: `get()`, `put(byte)`, `get(byte[])`, `put(byte[])` và các dạng với offset/length tác động từ **position hiện tại**, sau đó tăng position theo số phần tử chuyển.
- **Absolute**: `get(index)`, `put(index, byte)`, `getInt(index)`... truy cập theo index, **không thay đổi position**. Index phải nằm trong phạm vi hợp lệ so với limit, không chỉ capacity.

Ví dụ:

~~~java
ByteBuffer b = ByteBuffer.wrap(new byte[]{10, 20, 30});
System.out.println(b.get(1));        // 20, position vẫn 0.
System.out.println(b.get());         // 10, position thành 1.
System.out.println(b.remaining());   // 2.
~~~

Đây là **đoạn minh họa**, cần import `java.nio.ByteBuffer`.

Nếu muốn đọc một `int` 4 byte bằng `getInt()`, kiểm tra `remaining() >= Integer.BYTES`. `getInt()` di chuyển position lên 4 byte, và cách giải thích số phụ thuộc `ByteOrder` (mặc định của byte buffer là big-endian; có thể chọn little-endian qua `order(ByteOrder.LITTLE_ENDIAN)`). Ngay cả khi `capacity() >= 4`, nếu `remaining() < 4` thì không đủ dữ liệu cho lần đọc.

Những exception cần hiểu:

| Exception | Khi nào xuất hiện |
| --- | --- |
| `BufferUnderflowException` | `get` tương đối yêu cầu nhiều phần tử hơn `remaining`. |
| `BufferOverflowException` | `put` tương đối cần nhiều ô hơn `remaining`. |
| `IndexOutOfBoundsException` | Index, offset hoặc length không hợp lệ ở thao tác tuyệt đối/bulk. |
| `ReadOnlyBufferException` | Ghi/compact trên buffer chỉ đọc. |
| `InvalidMarkException` | `reset()` khi chưa có mark hiệu lực. |
| `IllegalArgumentException` | Đặt position/limit không hợp lệ. |

Một `put` số lượng lớn vào buffer không đủ chỗ thường thất bại thay vì tự tăng capacity. Khi cần dữ liệu lớn hơn, chọn buffer đủ kích thước, phân nhỏ chunk hoặc thiết kế pooling/streaming, thay vì mong ByteBuffer tự giãn.

### 5.1. Giới hạn của mảng đích

~~~java
byte[] destination = new byte[16];
int count = Math.min(buffer.remaining(), destination.length);
buffer.get(destination, 0, count);
~~~

Đây là đoạn minh họa với `buffer` đã ở chế độ đọc. `get(destination, 0, count)` chỉ đọc `count` byte và tăng position tương ứng. Nếu `count=0`, không có dữ liệu được lấy ra. Ở chiều ngược lại, `buffer.put(source, offset, count)` cũng phải bảo đảm đủ `remaining()` trong cửa sổ ghi.

**Không dùng `buffer.array()` để tiết kiệm một lời gọi `get` khi chưa rõ trạng thái**: mảng có thể lớn hơn cửa sổ hợp lệ; buffer direct hoặc read-only có thể không cho truy cập backing array. Với buffer slice, offset tới array không nhất thiết bằng index trong view. Dùng `get`/`put` hoặc kiểm tra `hasArray()` và `arrayOffset()` khi thật sự cần tối ưu.

### 5.2. mark/reset để thử parse một phần

~~~java
buffer.mark();
if (buffer.remaining() >= 4) {
    int length = buffer.getInt();
    // Dùng length sau khi kiểm tra giới hạn nghiệp vụ.
} else {
    buffer.reset();
    // Chờ dữ liệu bổ sung rồi parse tiếp.
}
~~~

Đây là **đoạn minh họa** với `buffer` ở chế độ đọc; giả sử khi thiếu 4 byte bạn muốn giữ position để thử lại. Trong ví dụ, vì không gọi `get` khi thiếu 4 byte nên `reset` không bắt buộc, nhưng vẫn minh họa khả năng phục hồi vị trí. Với parser thực sự đã đọc một phần header, mark/reset giúp đưa position về đầu phần chưa đủ, sau đó `compact` giữ phần đó lại. Đừng để nguồn cung cấp `length` chưa tin cậy quyết định phân bổ bộ nhớ vô hạn.

Khi gọi `clear`, `flip`, `rewind`, `compact` hoặc thay đổi position/limit làm mất mark, đừng dựa vào `reset` để “khôi phục” trạng thái trước đó; cần tự bảo quản các ranh giới nghiệp vụ nếu cần.

## 6. FileChannel và SocketChannel: đọc/ghi một lần không chắc là đủ

Một kênh Java NIO sử dụng buffer tại **position hiện tại**. `channel.read(buffer)` có thể đọc một phần rồi trả số byte thực tế `n` (hoặc -1 khi hết luồng theo ngữ cảnh); `channel.write(buffer)` có thể ghi ít hơn `remaining()` ban đầu. Phải dùng giá trị trả về, position và limit để điều khiển vòng lặp.

### 6.1. Đọc từ FileChannel vào ByteBuffer

~~~java
try (FileChannel channel =
         FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buf = ByteBuffer.allocate(4096);
    while (true) {
        int n = channel.read(buf);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            continue; // Với channel non-blocking cần chờ readiness thay vì spin.
        }

        buf.flip();
        while (buf.hasRemaining()) {
            byte value = buf.get();
            process(value);
        }
        buf.clear();
    }
}
~~~

Đây là **đoạn minh họa**, giả sử `path` là `Path`, `process(byte)` đã định nghĩa và nội dung là **byte stream** có thể xử lý từng byte độc lập; cần import `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.StandardOpenOption` và `java.io.IOException`. Ở đây mọi byte sau `flip` đều được tiêu thụ, nên `clear` là hợp lý. Với kênh non-blocking, đọc trả 0 có thể nghĩa là tạm chưa có dữ liệu: tích hợp `Selector`/cơ chế chờ phù hợp, không busy-spin.

**Nếu mỗi bản tin có độ dài hoặc header và chưa đủ byte để parse trọn:** không được tiêu thụ/bỏ dữ liệu còn dở. Sau khi xử lý các frame hoàn chỉnh, để position chỉ tới đầu phần chưa hoàn chỉnh, rồi `compact`. Phần chưa đọc chuyển về đầu buffer, lần `channel.read` tiếp theo nối dữ liệu vào sau nó. Dùng `clear` ở đây có thể phá header đang đọc dở.

### 6.2. Ghi ra FileChannel phải xét partial write

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE)) {
    ByteBuffer source = StandardCharsets.UTF_8.encode("Xin chào");
    while (source.hasRemaining()) {
        channel.write(source);
    }
}
~~~

Đây là **đoạn minh họa** với `path` kiểu `Path` và quyền ghi hợp lệ; cần import `FileChannel`, `ByteBuffer`, `StandardOpenOption`, `StandardCharsets` và xử lý `IOException`. `StandardCharsets.UTF_8.encode` tạo ByteBuffer ở trạng thái **sẵn sàng đọc**, nên **không gọi `flip()` thêm**. Vòng lặp chạy cho đến khi source.remaining() == 0; nếu chỉ gọi `write` một lần và giả định ghi hết, tệp có thể thiếu byte.

Với `SocketChannel` non-blocking, `write` có thể trả 0; không tạo vòng lặp nóng chiếm CPU. Đăng ký quan tâm `OP_WRITE`/readiness và quản lý buffer qua các lần gửi. Với ứng dụng HTTP thông thường, ưu tiên client/framework được duy trì để quản lý nhiều chi tiết I/O thấp tầng; học ByteBuffer vẫn hữu ích khi phân tích hiệu năng, framing và lỗi dữ liệu.

**Cảnh báo quan trọng:** các snippet trên làm việc với byte, không tự phân định ký tự UTF-8. Nếu một tiếng Việt/emoji bị chia giữa hai lần `read`, từng byte hoặc từng chunk có thể không phải một chuỗi hợp lệ độc lập; cần giữ byte còn dở hoặc dùng `CharsetDecoder` với trạng thái đúng.

## 7. Slice, duplicate, read-only và phần dữ liệu còn lại

`ByteBuffer.wrap(array)` bọc mảng có sẵn, không sao chép nội dung. `wrap(array, offset, length)` đặt **position=offset**, **limit=offset+length**, còn **capacity=array.length**. Nó **không** có nghĩa buffer mới bắt đầu ở position 0 với capacity bằng length; xem `wrap-window` trong ví dụ hoàn chỉnh.

`slice()` trên Java 11 tạo một view từ **position hiện tại đến limit**: position mới 0, limit=capacity mới bằng remaining của buffer gốc. Hai buffer **dùng chung byte**, nhưng position, limit và mark độc lập. Vì vậy:

- `slice.get()` tăng position của slice; **không tự tăng** position của buffer gốc.
- Sửa nội dung thông qua slice có thể đổi byte mà buffer gốc nhìn thấy; đây không phải deep copy.
- Nếu cần gửi view cho một consumer bất đồng bộ, phải quản lý vòng đời dữ liệu; producer không được tái sử dụng backing storage trước khi consumer xử lý xong.
- `duplicate()` cũng dùng chung nội dung, có cửa sổ trạng thái độc lập và ban đầu sao chép position/limit; không được hiểu là clone dữ liệu.
- `asReadOnlyBuffer()` chỉ cấm sửa **thông qua view chỉ đọc**, không bảo vệ khỏi thay đổi qua view khác cùng backing storage. Position/limit của view chỉ đọc vẫn đổi được.

Những view và buffer nói chung **không được bảo đảm thread-safe**. Không đưa cùng buffer đang biến đổi position vào hai thread đồng thời nếu thiếu cơ chế đồng bộ/ownership rõ ràng.

Một cách an toàn khi muốn gửi đúng vùng còn lại mà không làm dịch chuyển buffer gốc:

~~~java
ByteBuffer window = original.slice();
consumer.accept(window);
~~~

Đây là đoạn minh họa với `original` đã ở chế độ đọc và `consumer` nhận `ByteBuffer`; việc consumer có thể giữ view bao lâu phải được thỏa thuận. Nếu cần cô lập nội dung trước khi chuyển cho thread khác, tạo bản sao dữ liệu có giới hạn thay vì giả định `slice()` đã copy byte.

## 8. Kết nối với nén GZIP: số byte thực tế luôn quan trọng

Các lớp `java.util.zip.GZIPOutputStream` và `GZIPInputStream` vẫn là API tiêu chuẩn trên Java 11 để ghi và đọc định dạng GZIP. `GZIPInputStream.read(byte[])` trả số byte **đã giải nén** thực sự đưa vào mảng trong lượt đọc, hoặc -1 khi hết; không bảo đảm lấp đầy mảng. Đây là nơi khái niệm position/limit/remaining giúp xử lý đúng chỉ phần dữ liệu hợp lệ.

Giả sử một mảng tái sử dụng dài 4096 byte nhưng `read` chỉ trả `n=137`. Chỉ các byte trong `[0,137)` là phần hợp lệ mới nhận ở lượt đó; phần còn lại có thể chứa dữ liệu cũ. Nếu đóng gói vào `ByteBuffer.wrap(chunk, 0, n)` thì:

~~~text
position=0, limit=137, capacity=4096, remaining=137
~~~

Sau `get(new byte[remaining])`, chỉ 137 byte được chuyển tiếp. Nếu lấy `chunk.length` hoặc `capacity()` làm độ dài payload sẽ thêm byte rác, làm hỏng tệp/chuỗi sau giải nén.

**GZIP không tự biến ByteBuffer thành một “buffer nén”.** GZIP stream xử lý định dạng nén; ByteBuffer/byte array kiểm soát **cửa sổ byte** được trao giữa các bước. Số byte nén và số byte đã giải nén khác nhau và không có quan hệ một-một theo các chunk.

### 8.1. Chương trình Java 11 GZIP có xử lý partial chunk

Lưu file **`GzipRemainingDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public final class GzipRemainingDemo {
    private GzipRemainingDemo() {
    }

    public static void main(String[] args) throws IOException {
        String message = "Xin chào Java 11";
        byte[] original = message.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream compressed = new ByteArrayOutputStream();
        try (GZIPOutputStream out = new GZIPOutputStream(compressed)) {
            out.write(original);
        }

        ByteArrayOutputStream restored = new ByteArrayOutputStream();
        byte[] reusable = new byte[5];
        try (GZIPInputStream in = new GZIPInputStream(
                new ByteArrayInputStream(compressed.toByteArray()))) {
            int n;
            while ((n = in.read(reusable)) != -1) {
                ByteBuffer valid = ByteBuffer.wrap(reusable, 0, n);
                byte[] part = new byte[valid.remaining()];
                valid.get(part);
                restored.write(part);
            }
        }

        String result = new String(
            restored.toByteArray(), StandardCharsets.UTF_8);
        System.out.println("roundtrip=" + result);
        System.out.println("equal=" + message.equals(result));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GzipRemainingDemo.java
java GzipRemainingDemo
~~~

**Stdout chính xác** khi chương trình chạy thành công trong môi trường xuất Unicode chuẩn:

~~~text
roundtrip=Xin chào Java 11
equal=true
~~~

**Các điểm quan trọng:**

1. `GZIPOutputStream` phải được **đóng** trước khi lấy dữ liệu nén hoàn chỉnh; thao tác đóng hoàn tất phần cuối luồng GZIP. `ByteArrayOutputStream` giữ byte nén của ví dụ nhỏ.
2. Mỗi lần `GZIPInputStream.read(reusable)` trả `n`, chỉ dùng đúng `n` byte. `wrap(reusable, 0, n)` đặt cửa sổ [0,n), `remaining()==n`, và `get(part)` không sao chép phần cũ ngoài limit.
3. Một ký tự UTF-8 có thể bị chia giữa hai chunk 5 byte. Ví dụ **thu thập lại toàn bộ byte trước rồi mới tạo String** nên không cắt hỏng ký tự. Với dữ liệu lớn, dùng `InputStreamReader` hoặc `CharsetDecoder` dạng streaming để giữ trạng thái giải mã giữa các chunk.
4. Ví dụ dùng bộ nhớ để đơn giản hóa demo. **Trong production, giới hạn tổng byte giải nén** và thời gian/tài nguyên; tệp nén nhỏ có thể mở rộng thành lượng dữ liệu rất lớn (“decompression bomb”). Ghi kết quả ra sink có kiểm soát thay vì gom mọi byte trong RAM.
5. GZIP hỏng/truncated có thể gây `ZipException`/`IOException`. Đừng coi một lần `read` ít byte hơn kích thước mảng là lỗi: đó là hiện tượng bình thường. Đừng retry vô hạn khi dữ liệu nén sai định dạng.

### 8.2. Nhận diện lỗi ở ranh giới nén và buffer

| Dấu hiệu | Cần kiểm tra |
| --- | --- |
| File giải nén có byte rác cuối mỗi chunk | Có dùng `reusable.length`/capacity thay vì `n`/limit không? |
| Dữ liệu cuối stream bị thiếu | Có bỏ qua partial final chunk hoặc không đóng GZIPOutputStream? |
| Trùng một đoạn dữ liệu | Có `rewind` hoặc `compact` sai rồi gửi lại byte đã xử lý không? |
| Dữ liệu mất ở giữa hai lượt đọc | Có gọi `clear` khi buffer vẫn còn phần frame chưa parse không? |
| Tiếng Việt trở thành ký tự thay thế | Có decode UTF-8 độc lập từng chunk thay vì giữ decoder state? |
| Thiếu data nhưng vẫn cố đọc số nguyên/header | Có kiểm tra `remaining() >= số byte cần` không? |
| Hết bộ nhớ khi giải nén input lạ | Có giới hạn lượng byte giải nén và kích thước record không? |
| CPU cao khi gửi non-blocking | Có retry trong while khi `write()==0` thay vì chờ readiness không? |

## 9. ByteBuffer không đồng nghĩa với backing byte[]

Những cách tạo thường dùng:

| Factory | Đặc điểm | Lưu ý về vùng dữ liệu còn lại |
| --- | --- | --- |
| `ByteBuffer.allocate(n)` | Heap-backed buffer mới; position=0, limit=capacity=n. | remaining=n ở chế độ ghi. |
| `ByteBuffer.wrap(bytes)` | Dùng chung mảng có sẵn; position=0, limit=capacity=length. | Cần biết mảng đã chứa bao nhiêu byte hợp lệ. |
| `ByteBuffer.wrap(bytes, off, len)` | Dùng chung mảng, position=off, limit=off+len, capacity=bytes.length. | remaining=len; không coi offset là arrayOffset. |
| `ByteBuffer.allocateDirect(n)` | Direct buffer, hữu ích cho một số I/O cần giảm copy. | API position/limit/remaining giống heap buffer; không đương nhiên nhanh hơn. |
| `buffer.slice()` | View chung nội dung từ position đến limit. | View mới có remaining bằng remaining của buffer gốc tại thời điểm tạo. |
| `buffer.duplicate()` | View chung nội dung với con trỏ độc lập. | Ban đầu giữ cùng position/limit với buffer gốc. |

Direct buffer thường có chi phí tạo/thu hồi cao hơn và có thể sử dụng bộ nhớ ngoài Java heap. Chọn nó khi có **đo hiệu năng** cho tác vụ I/O phù hợp, thay vì chuyển toàn bộ buffer thành direct theo thói quen. Các khái niệm position/limit/remaining **không đổi** giữa direct và heap buffer.

`ByteBuffer` không tự “mở rộng” capacity. Với giao thức nhiều bản tin, phải thiết kế hạn mức, pool/lifetime hoặc luồng chuyển dữ liệu, đặc biệt khi phía gửi có thể cung cấp length không tin cậy. Tránh phân bổ `byte[remaining()]` theo input chưa kiểm tra; với kích thước lớn, truyền dữ liệu theo chunk.

## 10. Những sai lầm phổ biến

1. **Quên `flip()` sau `put`:** đọc từ phần chưa ghi hoặc gặp underflow; phải đưa limit về cuối payload đã ghi trước khi dùng `get`.
2. **Gọi `flip()` hai lần liên tiếp:** lần thứ hai lấy position=0 làm limit, tạo cửa sổ rỗng. Hãy kiểm tra trạng thái trước khi chuyển chế độ.
3. **Dùng `clear()` khi còn byte chưa xử lý:** dữ liệu còn lại có thể bị ghi đè; chọn `compact()` nếu cần giữ phần chưa đọc.
4. **Tưởng `clear()` xóa dữ liệu:** nội dung cũ vẫn có thể nằm trong backing storage; không dùng `clear` để xóa bí mật.
5. **Dùng `capacity()` làm số byte hiện có:** dễ gửi byte rác hoặc gặp underflow; dùng `remaining()` trong chế độ đọc.
6. **Dùng `remaining()` trong chế độ ghi để báo “payload size”:** đây là chỗ trống còn ghi được, không phải lượng đã ghi.
7. **Chỉ gọi `channel.write` một lần:** partial write có thể khiến payload bị cắt; phải dùng loop/quản lý readiness.
8. **Gửi cả mảng tái sử dụng sau `read`:** phần chưa được ghi mới có thể chứa byte của chunk trước; chỉ chuyển đúng `n` byte.
9. **Đọc một message/header khi `remaining()` chưa đủ:** phải chờ thêm dữ liệu hoặc thiết kế parser xử lý từng phần.
10. **Đọc byte như ký tự UTF-8 độc lập:** ký tự nhiều byte có thể bị cắt giữa hai chunk; dùng decoder streaming hoặc ghép byte đúng.
11. **Coi `slice/duplicate` là bản sao độc lập:** backing bytes vẫn được chia sẻ, dễ phát sinh race hoặc thay đổi dữ liệu ngoài dự kiến.
12. **Dùng `buffer.array()` trên direct/read-only:** có thể không hỗ trợ; nên dùng thao tác `get/put` hoặc kiểm tra `hasArray`.
13. **Dùng cùng một buffer đồng thời ở nhiều thread không phối hợp:** thay đổi position/limit bị tranh chấp; áp dụng ownership và đồng bộ.
14. **Giải nén không giới hạn:** compressed input nhỏ có thể tạo uncompressed output cực lớn; đặt budget tài nguyên.

## 11. Kiểm thử hành vi position, limit và remaining

Ngoài việc xem stdout, bạn có thể viết unit tests theo những bất biến và trường hợp biên:

| Case | Thiết lập | Điều cần khẳng định |
| --- | --- | --- |
| Buffer mới | `allocate(8)` | position=0, limit=8, capacity=8, remaining=8. |
| Ghi 5 byte | `put(new byte[5])` | position=5, limit=8, remaining=3. |
| Chuyển đọc | `flip()` | position=0, limit=5, remaining=5. |
| Đọc một phần | `get(new byte[2])` | position=2, remaining=3, dữ liệu chưa đọc là 3 byte. |
| Bảo toàn còn lại | `compact()` | position=3, limit=8, byte chưa đọc giữ nguyên thứ tự. |
| Đọc hết | `get(new byte[remaining])` | position=limit, hasRemaining=false. |
| Không đủ dữ liệu | `getInt()` khi remaining<4 | `BufferUnderflowException`. |
| Không đủ chỗ ghi | `put` vượt remaining | `BufferOverflowException`. |
| View | `slice()` sau đặt position/limit | remaining của view bằng remaining gốc, vị trí view độc lập. |
| Chunk cuối | GZIP read trả n<array.length | Chỉ n byte được chuyển tiếp, không có byte rác. |

Nếu đã dùng JUnit Jupiter bản tương thích JDK 11, ví dụ test sau có thể đặt trong `BufferRemainingTest.java` (phải cấu hình JUnit trong Maven/Gradle; nó không nằm sẵn trong JDK):

~~~java
import java.nio.ByteBuffer;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BufferRemainingTest {
    @Test
    void compactKeepsUnreadBytes() {
        ByteBuffer b = ByteBuffer.allocate(5);
        b.put(new byte[]{1, 2, 3});
        b.flip();
        assertEquals(1, b.get());
        assertEquals(2, b.remaining());
        b.compact();
        assertEquals(2, b.position());
        assertEquals(5, b.limit());
        b.flip();
        assertEquals(2, b.get());
        assertEquals(3, b.get());
        assertFalse(b.hasRemaining());
    }

    @Test
    void sliceKeepsIndependentPosition() {
        ByteBuffer b = ByteBuffer.wrap(new byte[]{10, 20, 30, 40});
        b.position(1);
        b.limit(3);
        ByteBuffer s = b.slice();
        assertEquals(2, s.remaining());
        assertEquals(20, s.get());
        assertEquals(1, b.position());
    }
}
~~~

Test đầu chứng minh byte 2 và 3 được giữ sau compact, test sau chứng minh slice có con trỏ độc lập. Chúng kiểm tra hành vi API quan sát được, không mô phỏng lại nội bộ ByteBuffer.

Đối với I/O thật, bổ sung integration test với file/channel và đầu vào cắt ở **mọi vị trí chia chunk**, nhất là giữa header và payload hoặc giữa các byte của một ký tự UTF-8. Dùng dữ liệu nhỏ để xác thực tính đúng đắn trước khi tối ưu bằng direct buffers hoặc buffer pooling.

## 12. Cách chẩn đoán lỗi trong ứng dụng

Khi nghi dữ liệu bị thiếu/trùng/nhòe ở một pipeline NIO hoặc giải nén:

1. Ghi nhận tại từng ranh giới **`position, limit, capacity, remaining`**, thao tác chuẩn bị chạy, kết quả `read/write` trả bao nhiêu byte và tổng byte đã xử lý.
2. Xác minh **chế độ** hiện tại: vừa `put` xong đã `flip` chưa? Sau `get` đã `compact` hay `clear`? Có khả năng `flip` hai lần không?
3. Đối chiếu **byte count**, không dựa vào kích thước array/buffer: tổng số byte đã gửi phải khớp tổng byte dữ liệu hợp lệ được tạo; sau giải nén so với số byte expected khi có thể.
4. Với parser, xem **ranh giới frame**: có giữ header không đủ hoặc payload chưa đọc hết cho lượt kế tiếp không?
5. Với UTF-8, giữ trạng thái decoder hoặc tái ghép byte rồi decode; không “sửa” lỗi bằng cách bỏ byte chưa đủ.
6. Với GZIP, xác nhận stream đã đóng/flush phù hợp, dữ liệu đầu vào không corrupt và giới hạn output; phân biệt lỗi định dạng nén với lỗi buffer.
7. Với concurrent I/O, xác định ai sở hữu buffer và bao lâu; view chung dữ liệu có bị producer tái sử dụng trước khi consumer hoàn tất không?
8. Viết test tái hiện với chunk kích thước 1, 2, 3, 5... để bộc lộ giả định sai về kích thước read/write.

Không log raw payload hoặc dữ liệu nhạy cảm chỉ để debug; giới hạn số lượng log, dùng request/operation ID khi cần nối chuỗi xử lý. Metrics có thể theo dõi byte input/output, số lỗi parse/giải nén và duration với nhãn cardinality hữu hạn.

## 13. Bài tập vận dụng

**Bài 1 — Tính trạng thái:** Buffer capacity 12 đang ở chế độ ghi, position 7, limit 12. Tính remaining. Sau `flip` rồi `get` 3 byte, tính position/limit/remaining mới. **Đáp án đối chiếu:** trước flip remaining=5 ô ghi; sau flip position=0, limit=7, remaining=7 byte đọc; sau 3 byte position=3, limit=7, remaining=4 byte chưa đọc.

**Bài 2 — Chọn thao tác:** Bạn đã nhận 10 byte, parse được 6 byte và còn 4 byte đầu của một frame chưa đủ. Nên dùng `clear()` hay `compact()` trước lượt read kế tiếp? Giải thích vị trí của 4 byte sau thao tác. **Đáp án:** `compact()` giữ 4 byte ở đầu, position=4, limit=capacity; lần ghi tiếp nối sau chúng.

**Bài 3 — Xác định bug:** Trình gửi file nén đọc 8192 byte vào mảng, lượt cuối chỉ nhận 41 byte rồi gửi cả mảng. Nêu nguyên nhân file hỏng và cách sửa bằng `n`/`remaining()`.

**Bài 4 — Debug view:** Với `ByteBuffer.wrap(new byte[]{1,2,3,4,5}, 1, 3)`, tìm capacity, position, limit, remaining; gọi `slice()` thì state của slice ra sao? **Đáp án:** gốc cap=5, pos=1, lim=4, rem=3; slice cap=lim=3, pos=0, rem=3.

**Bài 5 — Streaming:** Dùng `FileChannel` viết một tệp UTF-8; triển khai vòng lặp `while (buffer.hasRemaining())`. Nêu hành vi cần làm khác khi dùng non-blocking socket write trả 0. Đảm bảo không busy-spin.

**Bài 6 — UTF-8 và GZIP:** Dùng GZIP demo, giảm mảng chunk xuống 1 byte. Quan sát vẫn giải mã đúng **sau khi ghép lại toàn bộ byte**; giải thích vì sao không được `new String(chunk, 0, n, UTF_8)` riêng trên mỗi chunk.

## 14. Tài liệu chính thức

- [Java SE 11 — Buffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/Buffer.html): định nghĩa capacity, limit, position, mark, remaining và các thao tác chuyển trạng thái.
- [Java SE 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): get/put, wrap, slice, duplicate, compact, direct buffer, byte order.
- [Java SE 11 — FileChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/FileChannel.html): đọc/ghi qua ByteBuffer.
- [Java SE 11 — GZIPInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/GZIPInputStream.html): đọc dữ liệu giải nén và nhận số byte thực tế.
- [Java SE 11 — GZIPOutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/GZIPOutputStream.html): ghi luồng GZIP.

**Ghi nhớ:** `capacity` cho biết kích thước buffer; `limit` là ranh giới hợp lệ; `position` là vị trí tiếp theo; **`remaining = limit - position`** là lượng còn có thể thao tác trong cửa sổ hiện tại. Khi **đọc**, remaining là số byte chưa tiêu thụ; khi **ghi**, remaining là số ô còn trống. `flip` đổi sang đọc, `compact` giữ dữ liệu chưa xử lý, `clear` bắt đầu ghi mới mà không xóa byte. Trong nén và I/O theo khối, luôn truyền đúng số byte thực tế đã nhận hoặc chưa gửi hết.