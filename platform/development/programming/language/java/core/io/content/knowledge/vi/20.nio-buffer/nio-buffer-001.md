# Buffer, ByteBuffer, CharBuffer và các kiểu buffer khác trong Java NIO

## 1. Buffer giải quyết vấn đề gì?

Trong Java NIO (New I/O), **buffer** là một vùng chứa có dung lượng xác định, dùng để ghi dữ liệu vào rồi đọc dữ liệu ra. Buffer đồng thời lưu trạng thái cho biết **đã sử dụng đến đâu** và **còn bao nhiêu phần tử có thể đọc hoặc ghi**. Đây là cầu nối quan trọng giữa chương trình và những API như `FileChannel`, `SocketChannel` hoặc bộ mã hóa ký tự.

Ví dụ: một channel đọc được 5 byte từ tệp và đưa vào `ByteBuffer` dung lượng 8 byte. Chương trình cần phân biệt 5 byte hợp lệ vừa nhận với 3 vị trí chưa được điền bằng lần đọc đó. Buffer làm được điều này qua `position` và `limit`; chỉ dựa vào kích thước mảng byte sẽ không đủ.

Các lớp liên quan thuộc gói `java.nio`:

- `Buffer` là lớp cơ sở trừu tượng: định nghĩa trạng thái và các thao tác điều khiển con trỏ.
- `ByteBuffer` chứa đơn vị `byte`; loại thường được sử dụng khi giao tiếp với channel và mã hóa nhị phân.
- `CharBuffer` chứa đơn vị `char` (mỗi `char` là một *UTF-16 code unit*).
- `ShortBuffer`, `IntBuffer`, `LongBuffer`, `FloatBuffer`, `DoubleBuffer` chứa từng kiểu nguyên thủy tương ứng.
- `MappedByteBuffer` là một dạng `ByteBuffer` đại diện vùng tệp được ánh xạ vào bộ nhớ.

Không có lớp `BooleanBuffer` chuẩn trong Java NIO. Các buffer này có cách quản lý `position`, `limit`, `capacity` tương tự nhưng mỗi lớp cung cấp `get`/`put` theo kiểu phần tử riêng.

## 2. Mô hình trạng thái: capacity, limit, position và mark

Bốn giá trị cần nắm vững:

| Thuộc tính | Ý nghĩa | Bất biến |
| --- | --- | --- |
| `capacity()` | Sức chứa tối đa, **đếm theo phần tử của buffer**. | Dung lượng cố định trong suốt vòng đời buffer đó. |
| `limit()` | Ranh giới *exclusive*: thao tác tương đối không đi tới hoặc vượt quá vị trí này. | `0 <= limit <= capacity`. |
| `position()` | Chỉ số phần tử kế tiếp để `get()` hoặc `put(...)` tương đối sử dụng. | `0 <= position <= limit`. |
| `mark()` / `reset()` | Ghi nhớ vị trí để quay lại sau; có thể chưa được thiết lập. | Nếu có mark, `0 <= mark <= position`. |

Hình minh họa một buffer có `capacity=8`, `limit=5`, `position=2`:

~~~text
index:     0   1   2   3   4   5   6   7
         +---+---+---+---+---+---+---+---+
buffer:  | A | B | C | D | E | ? | ? | ? |
         +---+---+---+---+---+---+---+---+
                 ^           ^           ^
             position=2    limit=5    capacity=8

remaining() = limit - position = 3
hasRemaining() = true
~~~

Các dấu hỏi chỉ phần tử nằm ngoài **vùng đang được xem là hợp lệ để đọc**, không nhất thiết là byte đã bị xóa hoặc chưa từng được ghi.

Một buffer tạo bằng `ByteBuffer.allocate(8)` bắt đầu với `position=0`, `limit=8`, `capacity=8`. Nếu gọi `put` 5 lần, `position=5` trong khi `limit` vẫn bằng 8. Sau `flip()`, `position=0` và `limit=5`: ta sẵn sàng đọc đúng 5 phần tử vừa ghi.

Công thức quan trọng:

~~~text
0 <= position <= limit <= capacity
remaining = limit - position
~~~

`remaining()` đếm **số phần tử**, không phải số byte trong mọi trường hợp. Với `IntBuffer`, `remaining() == 3` có nghĩa còn 3 giá trị `int`; thông thường tương đương 12 byte dữ liệu lưu trữ.

## 3. Quy trình ghi rồi đọc: put → flip → get → clear/compact

### 3.1. Các thao tác điều khiển trạng thái

| Lệnh | Thay đổi trạng thái | Dùng khi |
| --- | --- | --- |
| `flip()` | `limit = position`; `position = 0`; xóa mark. | Chuyển từ **ghi vào buffer** sang **đọc dữ liệu đã ghi**. |
| `clear()` | `position = 0`; `limit = capacity`; xóa mark. | Sẵn sàng ghi lượt mới, không cần giữ dữ liệu cũ. |
| `rewind()` | `position = 0`; giữ nguyên limit; xóa mark. | Muốn đọc lại vùng dữ liệu hiện tại. |
| `compact()` | Dời những phần tử từ `position` đến `limit-1` về đầu vùng chứa; `position = số phần tử giữ lại`, `limit = capacity`; xóa mark. | Đã đọc một phần và muốn **giữ dữ liệu chưa đọc** rồi tiếp tục ghi. |
| `mark()` | Lưu position hiện tại vào mark. | Muốn đánh dấu vị trí có thể quay lại. |
| `reset()` | Đặt position về mark, nếu mark hợp lệ. | Đọc/ghi lại từ điểm đã đánh dấu. |
| `position(n)` / `limit(n)` | Thiết lập ranh giới trực tiếp, có thể vô hiệu hóa mark. | Cần điều khiển vùng dữ liệu chính xác. |

**`clear()` không xóa hay đặt tất cả byte thành 0.** Nó chỉ đặt lại `position` và `limit` để vùng nhớ có thể được ghi đè. Cũng không nên đọc phần còn sót lại sau `clear` và coi đó là dữ liệu mới.

### 3.2. Ví dụ từng bước

~~~java
ByteBuffer b = ByteBuffer.allocate(6);
b.put((byte) 'A');
b.put((byte) 'B');
b.put((byte) 'C');
// position=3, limit=6, capacity=6

b.flip();
// position=0, limit=3; chỉ A, B, C là vùng đang đọc

byte first = b.get(); // A; position=1
byte next = b.get();  // B; position=2

b.compact();
// Phần chưa đọc là C -> dời C tới index 0.
// position=1, limit=6: có thể ghi tiếp sau C.

b.put((byte) 'D');
b.flip();
// position=0, limit=2: vùng đọc là C, D.
~~~

Đây là **đoạn minh họa** giả sử đã import `java.nio.ByteBuffer` và đặt trong phương thức. `compact()` đặc biệt hữu ích với luồng dữ liệu đến theo nhiều đợt, chẳng hạn thông điệp mạng chưa nhận đủ.

### 3.3. Vì sao `flip()` thường không thể bỏ qua?

Một `Channel.read(buffer)` hoặc loạt lệnh `put` thường **tăng position** khi ghi dữ liệu vào buffer. Nếu lập tức gọi `get()` mà không `flip()`, chương trình sẽ đọc ở vị trí sau cùng đã ghi, thay vì từ đầu vùng dữ liệu vừa nhận. Kết quả có thể sai hoặc gặp `BufferUnderflowException` tùy trạng thái.

Ngược lại, sau khi đọc hết mà muốn ghi đè từ đầu, cần `clear()`. Nếu còn phần tử chưa xử lý thì dùng `compact()`. Chọn sai hai lệnh này thường khiến ứng dụng làm mất một phần thông điệp.

## 4. ByteBuffer: làm việc với byte và dữ liệu nhị phân

`ByteBuffer` là buffer trung tâm trong nhiều ứng dụng NIO vì channel đọc và ghi những chuỗi byte.

### 4.1. Tạo ByteBuffer

~~~java
ByteBuffer heap = ByteBuffer.allocate(1024);
ByteBuffer direct = ByteBuffer.allocateDirect(1024);

byte[] source = {10, 20, 30};
ByteBuffer wrapped = ByteBuffer.wrap(source);
~~~

Phân biệt:

- `allocate(1024)` cấp một **heap byte buffer**; các phần tử thường nằm trong một mảng byte trên heap. `isDirect()` là `false`.
- `allocateDirect(1024)` tạo một **direct byte buffer**; JVM cố gắng dành vùng nhớ thích hợp cho các hoạt động native I/O. `isDirect()` là `true`. Chi phí cấp phát và quản lý có thể cao hơn; không mặc định luôn nhanh hơn.
- `wrap(source)` tạo buffer dựa trên **mảng hiện có** và chia sẻ nội dung với mảng đó. Sửa phần tử qua buffer có thể làm thay đổi mảng gốc và ngược lại.

`ByteBuffer.wrap(array, offset, length)` tạo buffer có `capacity=array.length`, `position=offset`, `limit=offset+length`. Nó **không** tự cắt mảng thành một buffer có position bằng 0. Muốn một vùng nhìn mới bắt đầu tại 0, dùng `slice()` sau khi thiết lập `position`/`limit` phù hợp.

### 4.2. Ghi và đọc: thao tác tương đối và tuyệt đối

~~~java
ByteBuffer b = ByteBuffer.allocate(4);

b.put((byte) 10);             // Ghi tại position rồi tăng position.
b.put((byte) 20);
byte second = b.get(1);       // Đọc tuyệt đối index 1; position KHÔNG đổi.
int p = b.position();         // p == 2

b.flip();
byte first = b.get();         // Đọc tương đối index 0, sau đó tăng position.
~~~

Các overload phổ biến:

| API | Ý nghĩa |
| --- | --- |
| `get()` / `put(byte)` | Đọc/ghi một byte tại position và dịch position. |
| `get(index)` / `put(index, value)` | Đọc/ghi tại chỉ số tuyệt đối; không đổi position. |
| `get(byte[])` / `put(byte[])` | Chuyển nhiều byte, cập nhật position theo số phần tử chuyển. |
| `getInt()` / `putInt(int)` | Đọc/ghi 4 byte thành một `int`, theo `ByteOrder` của buffer. |
| `getLong()` / `putLong(long)` | Đọc/ghi 8 byte thành một `long`, theo `ByteOrder`. |
| `getChar()` / `putChar(char)` | Đọc/ghi một `char` như hai byte theo byte order; **không phải** chuyển mã UTF-8. |

Với absolute `get(index)`/`put(index, ...)`, chỉ số được kiểm tra theo `limit`, không thể tùy ý truy cập phía sau limit dù capacity còn lớn. Khi muốn kiểm tra số phần tử sẵn có, dùng `remaining()` và `hasRemaining()`.

### 4.3. Byte order (endianness)

Dữ liệu đa byte cần quy ước byte đứng trước:

- **Big-endian**: byte có trọng số cao được ghi trước.
- **Little-endian**: byte có trọng số thấp được ghi trước.

~~~java
ByteBuffer b = ByteBuffer.allocate(4);
b.order(ByteOrder.LITTLE_ENDIAN);
b.putInt(0x01020304);
// Bốn byte trong buffer: 04 03 02 01
~~~

Mặc định `ByteBuffer` dùng `ByteOrder.BIG_ENDIAN`; khi đọc/ghi giao thức nhị phân, phải chọn đúng quy ước của giao thức. Sai byte order có thể khiến số nguyên đọc ra sai dù các byte đã nhận đủ.

`order(ByteOrder)` **không** chuyển đổi lại dữ liệu đã có; nó quyết định cách các thao tác đọc/ghi đa byte tiếp theo diễn giải byte. Những buffer view kiểu số được tạo từ `ByteBuffer` ghi nhận byte order thích hợp tại thời điểm tạo; thay đổi byte order về sau cần được thiết kế có chủ đích.

## 5. CharBuffer: vùng chứa ký tự, khác ByteBuffer

`CharBuffer` chứa các phần tử kiểu Java `char`, mỗi phần tử là một đơn vị mã UTF-16. Nó phù hợp khi đã có dữ liệu ký tự hoặc khi decoder biến byte thành ký tự.

~~~java
CharBuffer a = CharBuffer.allocate(10);
a.put('J').put('a').put('v').put('a');
a.flip();
System.out.println(a.toString()); // Java

CharBuffer b = CharBuffer.wrap("Hello");
System.out.println(b.get());      // H
~~~

Đây là các **mảnh minh họa** khi đã import `java.nio.CharBuffer`. Phân biệt hai dạng `wrap`:

- `CharBuffer.wrap(char[])` chia sẻ mảng `char[]` và thường có thể ghi qua buffer nếu mảng/buffer đó không bị biến thành read-only.
- `CharBuffer.wrap(CharSequence)`, như `wrap("Hello")`, tạo buffer **read-only** dựa trên chuỗi ký tự; `put` vào buffer này sẽ ném `ReadOnlyBufferException`.

`CharBuffer` triển khai `CharSequence` và các phương thức hữu ích như `length()`, `charAt(...)`, `subSequence(...)`, `toString()`. `toString()` phản ánh **các ký tự còn lại từ position đến limit**, không mặc nhiên là toàn bộ capacity.

Không đồng nhất một `char` với một ký tự Unicode hoàn chỉnh: ký tự nằm ngoài Basic Multilingual Plane (ví dụ một số emoji) cần **cặp surrogate**, tức hai phần tử `char`. Muốn đếm *code point*, phải xử lý theo quy tắc Unicode, ví dụ thông qua API `String.codePointCount(...)` trên chuỗi đã thu được.

### 5.1. Chuyển giữa ByteBuffer và CharBuffer bằng Charset

**Byte ≠ char.** Để chuyển văn bản sang byte, cần biết charset như UTF-8. Không dùng `getChar()`/`putChar()` của `ByteBuffer` để thay thế UTF-8 encoder/decoder.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.StandardCharsets;

ByteBuffer bytes = StandardCharsets.UTF_8.encode("Tiếng Việt");
CharBuffer chars = StandardCharsets.UTF_8.decode(bytes);
System.out.println(chars.toString()); // Tiếng Việt
~~~

Đây là mảnh minh họa đặt trong `main`. Các helper `Charset.encode`/`decode` trả buffer với position/limit ở trạng thái có thể đọc đầu ra. `decode(bytes)` **tiêu thụ vị trí đọc của bytes**; nếu cần đọc lại byte sau đó, hãy `rewind`/`duplicate` có chủ đích.

Trong ứng dụng xử lý nhiều đợt byte, một ký tự UTF-8 có thể bị chia giữa hai lượt đọc. Khi ấy dùng `CharsetDecoder` theo cơ chế streaming, xử lý kết quả `CoderResult` và giữ byte còn dang dở; không tùy tiện decode từng mảnh độc lập vì có thể sinh ký tự thay thế hoặc lỗi giải mã.

## 6. Các buffer kiểu nguyên thủy khác

| Buffer | Kiểu phần tử | Dung lượng `allocate(n)` | Tình huống sử dụng |
| --- | --- | --- | --- |
| `ByteBuffer` | `byte` (8 bit) | `n` byte | Tệp, socket, protocol, binary payload. |
| `CharBuffer` | `char` (16 bit) | `n` code unit UTF-16 | Ký tự sau khi decode, xử lý văn bản. |
| `ShortBuffer` | `short` (16 bit) | `n` giá trị `short` | Giá trị nhị phân 16 bit. |
| `IntBuffer` | `int` (32 bit) | `n` giá trị `int` | Dữ liệu số nguyên, binary view. |
| `LongBuffer` | `long` (64 bit) | `n` giá trị `long` | Số nguyên 64 bit. |
| `FloatBuffer` | `float` (32 bit) | `n` giá trị `float` | Dữ liệu số thực 32 bit. |
| `DoubleBuffer` | `double` (64 bit) | `n` giá trị `double` | Dữ liệu số thực 64 bit. |

Chẳng hạn:

~~~java
IntBuffer numbers = IntBuffer.allocate(3);
numbers.put(10).put(20).put(30);
numbers.flip();

while (numbers.hasRemaining()) {
    System.out.println(numbers.get());
}
~~~

Output:

~~~text
10
20
30
~~~

Đoạn mã cần `import java.nio.IntBuffer;` và đặt trong phương thức Java. Vòng lặp đọc **theo phần tử `int`**, không phải từng byte.

Nhiều typed buffer cũng hỗ trợ `wrap(array)`, `slice()`, `duplicate()`, `asReadOnlyBuffer()`, `get`/`put` và các thao tác tương ứng để xem dữ liệu; cách cấp phát vùng nhớ và khả năng hỗ trợ mảng phụ thuộc kiểu buffer và nguồn tạo ra nó.

## 7. View buffer, slice, duplicate và read-only

Đây là nhóm API dễ gây lỗi do nhiều buffer **chia sẻ cùng một vùng dữ liệu**, dù trạng thái `position` và `limit` độc lập.

| Cách tạo | Dữ liệu | Position/limit | Đặc điểm |
| --- | --- | --- | --- |
| `duplicate()` | Chia sẻ vùng nhớ với buffer gốc. | Sao chép trạng thái ban đầu, sau đó di chuyển độc lập. | Sửa byte qua một buffer nhìn thấy ở buffer kia. |
| `slice()` | Chia sẻ đoạn từ position đến limit của buffer gốc. | View mới bắt đầu position=0 và capacity=remaining tại lúc cắt. | Index 0 của slice tương ứng vị trí gốc tại thời điểm slice. |
| `asReadOnlyBuffer()` | Chia sẻ dữ liệu với gốc. | Trạng thái vị trí riêng. | Ghi qua view bị cấm, dù gốc có thể tiếp tục ghi. |
| `asIntBuffer()` và các primitive views | Chia sẻ byte làm dữ liệu kiểu nguyên thủy. | Position/limit tính theo **số phần tử của kiểu view**. | Diễn giải byte theo byte order của nguồn tại thời điểm tạo view. |

Ví dụ về `slice()`:

~~~java
ByteBuffer original = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
original.position(1);
original.limit(3);

ByteBuffer view = original.slice(); // View chứa 20, 30.
view.put(0, (byte) 99);             // Thay byte đầu của slice.

System.out.println(original.get(1)); // 99
System.out.println(original.position()); // 1
~~~

**Tại sao position của gốc vẫn là 1?** Vì `view.put(0, ...)` là truy cập tuyệt đối trong slice; hai buffer chia sẻ dữ liệu nhưng không chia sẻ con trỏ. Trường hợp `duplicate()` cũng không tự đồng bộ con trỏ.

### 7.1. Primitive view từ ByteBuffer

~~~java
ByteBuffer bytes = ByteBuffer.allocate(8);
bytes.order(ByteOrder.BIG_ENDIAN);
IntBuffer ints = bytes.asIntBuffer();

ints.put(0, 42);
ints.put(1, 7);

System.out.println(bytes.getInt(0)); // 42
System.out.println(bytes.getInt(4)); // 7
~~~

Đây là mảnh minh họa với import `java.nio.ByteBuffer`, `java.nio.ByteOrder` và `java.nio.IntBuffer`. `asIntBuffer()` tạo view trên các byte còn lại, dung lượng đo theo các nhóm 4 byte. Phép `ints.put(index, value)` làm thay đổi vùng nhớ chung; `bytes.getInt(...)` đọc lại cùng byte.

Nếu số byte còn lại không chia hết cho kích thước kiểu phần tử, view chỉ chứa số phần tử **nguyên vẹn** có thể biểu diễn. Byte order và alignment có thể ảnh hưởng đến tính đúng đắn hoặc hiệu năng trong những thao tác cấp thấp.

## 8. Heap buffer và direct buffer

`ByteBuffer.allocate(...)` và `ByteBuffer.allocateDirect(...)` đều cung cấp API đọc/ghi tương tự, nhưng khác về cách quản lý vùng nhớ.

| Tiêu chí | Heap ByteBuffer | Direct ByteBuffer |
| --- | --- | --- |
| Tạo | `ByteBuffer.allocate(n)` | `ByteBuffer.allocateDirect(n)` |
| `isDirect()` | `false` | `true` |
| Mảng backing | Thường có thể truy cập qua `array()` nếu writable và có mảng. | Không được giả định có mảng Java truy cập được. |
| Cấp phát/giải phóng | Chủ yếu theo cơ chế bộ nhớ Java heap. | Có chi phí quản lý native memory và phụ thuộc JVM/GC. |
| I/O native | Có thể cần thao tác sao chép trung gian. | Có thể giảm một số lần sao chép với channel I/O phù hợp. |
| Chọn dùng | Buffer nhỏ, sống ngắn, thao tác dữ liệu thường. | Buffer lớn/tái sử dụng, I/O có đo đạc chứng minh lợi ích. |

**Không gọi `array()` mà chưa kiểm tra khả năng.** `hasArray()` trả về `false` đối với direct buffer và read-only buffer; `array()` có thể ném `UnsupportedOperationException` hoặc `ReadOnlyBufferException` tùy loại buffer. Ngay cả khi có mảng, cần lưu ý `arrayOffset()` và vị trí của view/slice.

Khi cần đọc bất kỳ `ByteBuffer` nào thành mảng độc lập, có thể làm như sau:

~~~java
ByteBuffer copy = source.duplicate();
byte[] bytes = new byte[copy.remaining()];
copy.get(bytes);
~~~

Đây là mảnh minh họa với `source` là `ByteBuffer` có sẵn. Lệnh lấy **remaining bytes** của source tại thời điểm đó. Dùng duplicate giúp giữ nguyên position của source và làm việc với cả heap, direct lẫn read-only buffer.

Không cấp phát direct buffer cho mọi thao tác với niềm tin nó chắc chắn nhanh hơn. Độ lớn dữ liệu, số lần tái sử dụng, provider, thao tác mã hóa và đường đi thực tế của I/O mới quyết định hiệu quả; nếu quan trọng về hiệu năng, hãy benchmark đúng workload.

## 9. MappedByteBuffer: ánh xạ vùng tệp

`MappedByteBuffer` kế thừa `ByteBuffer`. Thông qua `FileChannel.map(...)`, ứng dụng có thể ánh xạ một vùng tệp vào bộ nhớ và đọc/ghi qua API buffer.

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, channel.size());

    if (mapped.hasRemaining()) {
        byte first = mapped.get(0);
        mapped.put(0, (byte) (first + 1));
        mapped.force();
    }
}
~~~

Đây là **mảnh minh họa**; cần các import `java.nio.MappedByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Path` và `java.nio.file.StandardOpenOption`, và phải có tệp `path` hợp lệ. `force()` yêu cầu chuyển thay đổi của mapping xuống thiết bị lưu trữ theo hợp đồng API; việc ánh xạ, độ bền dữ liệu và sự tương tác với sửa tệp ngoài chương trình còn tùy nền tảng và chế độ map.

Việc đóng `FileChannel` **không nhất thiết hủy ngay vùng nhớ đã ánh xạ**. Vòng đời mapping có thể kéo dài đến khi buffer được thu hồi. Không dùng mmap như phương án mặc định; nó có giới hạn về quản lý tài nguyên, khóa tệp hoặc phối hợp đọc/ghi đa tiến trình.

## 10. Buffer làm việc với Channel như thế nào?

Khi đọc từ một channel vào `ByteBuffer`:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(4096);
int n = channel.read(buffer);  // Channel ghi byte vào buffer.
buffer.flip();                 // Chuyển sang đọc phần vừa nhận.

while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Xử lý value...
}

buffer.clear();                // Sẵn sàng nhận lượt tiếp theo.
~~~

Đây là **mảnh minh họa** giả định `channel` hỗ trợ `read(ByteBuffer)` và đã được khởi tạo. Lệnh `read` có thể trả:

- Một số dương: số byte thực tế nhận được, có thể nhỏ hơn dung lượng còn trống.
- `0`: không có byte được chuyển trong lần gọi đó (chẳng hạn với non-blocking channel chưa sẵn sàng).
- `-1`: đã đến cuối luồng (EOF) đối với những channel hỗ trợ hợp đồng này.

Không giả định **một** lần `read` chắc chắn điền đủ buffer hoặc một lần `write` chắc chắn xuất hết `remaining()`; với channel cho phép partial I/O, cần vòng lặp và quy tắc chờ phù hợp.

### 10.1. Khi còn dữ liệu chưa xử lý: dùng compact()

Giả sử ứng dụng nhận gói dữ liệu mà một thông điệp bị chia giữa hai lần đọc. Sau khi xử lý phần thông điệp hoàn chỉnh trong buffer, hãy giữ các byte còn dang dở:

~~~java
buffer.flip();           // Đọc dữ liệu vừa nhận.
consumeCompleteFrames(buffer); // Chỉ tăng position qua các frame đầy đủ.
buffer.compact();        // Giữ phần byte chưa thuộc frame hoàn chỉnh.
~~~

Đây là **pseudocode minh họa**; `consumeCompleteFrames` là hàm ứng dụng cần tự định nghĩa, không phải API Java. Ví dụ giúp giải thích lý do `compact()` có giá trị: `clear()` sẽ đặt lại con trỏ và cho phép dữ liệu chưa xử lý bị ghi đè.

Khi viết buffer ra channel, buffer thường đã ở trạng thái đọc sau `flip()`:

~~~java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // Với channel non-blocking, đăng ký/chờ tín hiệu ghi sẵn sàng.
        break;
    }
}
~~~

Đây là đoạn minh họa điều khiển luồng; nếu dừng ở `written == 0`, ứng dụng phải **giữ nguyên phần còn lại** để tiếp tục khi channel sẵn sàng. Với channel blocking, giao thức chờ có thể khác. Không dùng vòng lặp busy-spin vô hạn trên channel non-blocking.

## 11. Chương trình chạy được trên Java 17+: nhiều kiểu buffer và compact()

Lưu nội dung sau vào tệp `BufferDemo.java`. Chương trình dùng các thao tác xác định, không phụ thuộc hệ điều hành hay file bên ngoài.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.CharBuffer;
import java.nio.IntBuffer;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class BufferDemo {
    public static void main(String[] args) {
        ByteBuffer bytes = ByteBuffer.allocate(8);
        bytes.order(ByteOrder.BIG_ENDIAN);
        bytes.putInt(0x01020304);
        bytes.put((byte) 'A');
        bytes.flip();

        System.out.println("capacity=" + bytes.capacity());
        System.out.println("limit=" + bytes.limit());
        System.out.println("hex=" + Integer.toHexString(bytes.getInt()));
        System.out.println("letter=" + (char) bytes.get());
        System.out.println("hasRemaining=" + bytes.hasRemaining());

        bytes.clear();
        bytes.put((byte) 'B');
        bytes.flip();
        System.out.println("reuse=" + (char) bytes.get());

        CharBuffer chars = CharBuffer.wrap("Java");
        System.out.println("charRemaining=" + chars.remaining());
        System.out.println("firstChar=" + chars.get());

        IntBuffer numbers = IntBuffer.allocate(3);
        numbers.put(10).put(20).put(30);
        numbers.flip();
        System.out.println("sum=" + (numbers.get() + numbers.get() + numbers.get()));

        ByteBuffer partial = ByteBuffer.allocate(8);
        partial.put("abcde".getBytes(StandardCharsets.US_ASCII));
        partial.flip();
        partial.get(); // Tiêu thụ a.
        partial.get(); // Tiêu thụ b.
        partial.compact(); // Giữ cde.
        partial.put("FG".getBytes(StandardCharsets.US_ASCII));
        partial.flip();

        byte[] remaining = new byte[partial.remaining()];
        partial.get(remaining);
        System.out.println("compact=" +
                new String(remaining, StandardCharsets.US_ASCII));

        ByteBuffer little = ByteBuffer.allocate(4);
        little.order(ByteOrder.LITTLE_ENDIAN);
        little.putInt(0x01020304);
        System.out.println("littleEndian=" +
                HexFormat.of().formatHex(little.array()));

        ByteBuffer encoded = StandardCharsets.UTF_8.encode("Tiếng Việt");
        CharBuffer decoded = StandardCharsets.UTF_8.decode(encoded);
        System.out.println("decoded=" + decoded);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BufferDemo.java
java BufferDemo
~~~

Stdout:

~~~text
capacity=8
limit=5
hex=1020304
letter=A
hasRemaining=false
reuse=B
charRemaining=4
firstChar=J
sum=60
compact=cdeFG
littleEndian=04030201
decoded=Tiếng Việt
~~~

Giải thích những dòng chính:

1. Sau `putInt` (4 byte) và `put('A')` (1 byte), `position=5`. `flip` đặt `limit=5` để đọc đúng 5 byte, trong khi `capacity` vẫn là 8.
2. `getInt()` đọc bốn byte big-endian và trả giá trị `0x01020304`; `Integer.toHexString` in `1020304` (không thêm số 0 đứng đầu). Lệnh `get()` tiếp theo đọc ký tự `A`, nên không còn phần tử nào giữa position và limit.
3. `clear` cho phép ghi lại vào bộ nhớ cũ, nhưng không phải xóa nội dung. `put('B')`/`flip` tạo lượt dữ liệu mới có đúng một byte.
4. `CharBuffer.wrap("Java")` có bốn `char` còn lại; đọc một phần tử đầu tiên cho kết quả `J`.
5. `IntBuffer` chứa ba số nguyên, nên tổng là 60.
6. Với `partial`, hai byte `a` và `b` đã đọc; `compact` giữ `cde`, sau đó thêm `FG` để vùng đọc cuối cùng là `cdeFG`.
7. Byte order little-endian biểu diễn `0x01020304` bằng chuỗi byte hex `04 03 02 01`.
8. UTF-8 encoding/decoding giữ nguyên chuỗi `Tiếng Việt`. Quá trình này chuyển **byte** thành **char**, không phụ thuộc byte order của `ByteBuffer`.

## 12. Lỗi thường gặp và cách chẩn đoán

| Vấn đề | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `BufferUnderflowException` | Gọi `get` khi `remaining()` không đủ số phần tử cần đọc. | Kiểm tra trạng thái và số byte cần thiết trước khi đọc. |
| `BufferOverflowException` | Gọi `put` vượt `limit` hoặc không còn chỗ. | Kiểm tra `remaining()`, phân bổ đủ dung lượng, `clear`/`compact` khi đúng quy trình. |
| `InvalidMarkException` | Gọi `reset()` khi mark chưa được thiết lập hoặc đã bị xóa. | Gọi `mark()` tại vị trí phù hợp và hiểu tác động của `flip/clear/rewind`. |
| `ReadOnlyBufferException` | Ghi vào read-only buffer/view. | Dùng writable buffer khác hoặc tạo bản sao dữ liệu. |
| `IndexOutOfBoundsException` | Truy cập absolute index không hợp lệ so với limit hoặc vùng chỉ định. | Dùng position/limit đúng, kiểm tra trước khi đọc/ghi. |
| `UnsupportedOperationException` khi `array()` | Buffer không có backing array truy cập được. | Dùng `hasArray()` hoặc `duplicate().get(byte[])`. |
| Dữ liệu đọc bị thiếu | Quên `flip()`, hoặc một lần channel read trả ít byte hơn kỳ vọng. | Quản lý trạng thái chuẩn và xử lý partial reads. |
| Mất phần dữ liệu chưa xử lý | Gọi `clear()` thay cho `compact()` sau khi chỉ tiêu thụ một phần. | Giữ `remaining` bằng compact khi cần. |
| Số nhị phân sai | Sai `ByteOrder` hoặc đọc nhầm kiểu (ví dụ `getShort` thay vì `getInt`). | Đối chiếu đặc tả dữ liệu/giao thức. |
| Ký tự lỗi | Dùng `getChar()` thay cho decoder hoặc cắt một ký tự UTF-8 giữa hai chunk. | Chọn đúng `Charset` và xử lý luồng nhiều đợt bằng decoder. |

### Các nguyên tắc sử dụng an toàn

- **Buffer không mặc định thread-safe.** Nếu nhiều luồng cùng đọc/ghi một buffer, phải có cơ chế đồng bộ hoặc thiết kế ownership rõ ràng. `duplicate()` tách con trỏ nhưng vẫn chia sẻ dữ liệu, không tự giải quyết race condition.
- **Không giữ trạng thái position/limit bằng phỏng đoán.** Ghi lại quy trình vào/ra, dùng `remaining()`, kiểm tra read/write count và vị trí sau mỗi bước khi chẩn đoán.
- **Đừng dùng `array()` trên mọi buffer.** Direct, read-only và view buffer có thể không lộ mảng; nếu lộ mảng, `arrayOffset()` mới cho biết phép ánh xạ chỉ số thích hợp.
- **Không dùng `clear()` để xóa bí mật khỏi bộ nhớ.** Nó thay đổi trạng thái logic; muốn xóa dữ liệu cần quy trình ghi đè riêng phù hợp và lưu ý các bản sao dữ liệu đã tồn tại.
- **Không coi số phần tử là số byte cho mọi buffer.** `IntBuffer.remaining()` đếm `int`; khi tính kích thước dữ liệu nhị phân cần nhân với số byte/phần tử một cách rõ ràng.
- **Các phương thức so sánh có thể dựa trên phần tử còn lại.** `equals` và `compareTo` của nhiều typed buffer so sánh vùng từ position đến limit; cùng vùng lưu trữ nhưng vị trí khác nhau có thể không bằng nhau.
- **Chọn kích thước buffer theo tải thực tế.** Buffer quá nhỏ có thể làm tăng số lần I/O; buffer quá lớn tăng chi phí bộ nhớ. Direct buffer cần thêm lưu ý vòng đời/tái sử dụng.

## 13. Câu hỏi tự kiểm tra

1. **`ByteBuffer.allocate(10)` có position, limit, capacity ban đầu là bao nhiêu?** Tương ứng `0, 10, 10`.
2. **Sau khi ghi 4 byte vào buffer dung lượng 10 và gọi `flip()`?** `position=0`, `limit=4`, `capacity=10`; có đúng 4 byte trong vùng sẵn sàng đọc.
3. **Đã đọc một phần và muốn giữ byte còn lại để nhận thêm dữ liệu, nên gọi gì?** `compact()`, rồi ghi tiếp và `flip()` trước lượt đọc tiếp.
4. **`clear()` có ghi số 0 vào toàn bộ byte cũ không?** Không. Nó chỉ đặt position về 0 và limit về capacity.
5. **`ByteBuffer.wrap(array)` có copy nội dung array không?** Không. Nội dung được chia sẻ với mảng gốc.
6. **`duplicate()` và `slice()` có độc lập dữ liệu với gốc không?** Không. Chúng chia sẻ vùng lưu trữ; chỉ trạng thái position/limit độc lập.
7. **`CharBuffer` có lưu sẵn UTF-8 bytes không?** Không. Nó lưu `char`, tức các UTF-16 code unit. Muốn chuyển dữ liệu byte và ký tự, dùng `Charset`/encoder/decoder.
8. **`ByteBuffer.putInt(0x01020304)` dưới little-endian tạo những byte nào?** `04 03 02 01`.
9. **`ByteBuffer.allocateDirect(100)` có bảo đảm `array()` sử dụng được?** Không. Truy xuất byte qua `get/put` hoặc sao chép `remaining` ra mảng.
10. **Vì sao một lần `FileChannel.read` chưa đủ để kết luận đã nhận đầy đủ thông điệp?** Vì một lần đọc có thể chuyển ít byte hơn lượng cần thiết; chương trình phải quản lý buffer và tiếp tục đọc theo giao thức.

**Ghi nhớ:** `Buffer` định nghĩa **trạng thái vùng dữ liệu**; `ByteBuffer` là công cụ làm việc với **byte và channel I/O**; `CharBuffer` và các typed buffer diễn giải **phần tử theo kiểu cụ thể**. Quy tắc thực hành quan trọng nhất là **ghi → flip → đọc → clear hoặc compact**, đồng thời kiểm soát `position`, `limit`, `capacity`, byte order và việc chia sẻ vùng nhớ.
