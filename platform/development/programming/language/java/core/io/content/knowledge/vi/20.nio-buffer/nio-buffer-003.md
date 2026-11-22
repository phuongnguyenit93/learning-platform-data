# Chu trình ghi vào buffer, `flip()` và đọc khỏi buffer trong Java NIO

## 1. Buffer không tự biết lúc nào bạn muốn ghi hay đọc

Trong Java NIO (`java.nio`), **buffer** là vùng lưu dữ liệu kèm các con trỏ mô tả phần nào đang được phép truy cập. Khi đọc dữ liệu từ channel, dữ liệu thường được **ghi vào buffer** trước, rồi chương trình **đọc ra khỏi buffer** để xử lý hoặc ghi sang channel khác.

Một `ByteBuffer` có ba đại lượng cần quan sát liên tục:

- **`capacity`**: tổng số phần tử mà buffer có thể chứa, cố định trong suốt vòng đời buffer.
- **`position`**: vị trí của phần tử sẽ được đọc/ghi tiếp theo khi dùng các thao tác *tương đối* như `get()`, `put(byte)`.
- **`limit`**: chỉ số đầu tiên **nằm ngoài vùng thao tác được phép** trong trạng thái hiện tại.

Bất biến:

~~~text
0 <= position <= limit <= capacity
remaining() = limit - position
hasRemaining() tương đương position < limit
~~~

**“Chế độ ghi” và “chế độ đọc” là cách chương trình sử dụng buffer**, không phải một cờ `READ/WRITE` được tự động chuyển đổi. Các lời gọi `flip()`, `clear()`, `rewind()` và `compact()` thay đổi `position`/`limit` để chuẩn bị cho bước kế tiếp.

Ví dụ buffer có `capacity = 8`, đang ghi 3 byte:

~~~text
index:      0   1   2   3   4   5   6   7
dữ liệu:    A   B   C   ?   ?   ?   ?   ?
           └─ đã ghi ─┘└──── còn chỗ ghi ────┘
position = 3
limit    = 8
capacity = 8
~~~

Ký hiệu `?` biểu diễn dữ liệu chưa có ý nghĩa cho lần ghi này; không được đọc các ô đó như nội dung hợp lệ.

## 2. Giai đoạn 1: ghi *vào* buffer

Sau khi tạo:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
~~~

Trạng thái ban đầu:

~~~text
position = 0
limit    = 8
capacity = 8
remaining = 8
~~~

Lệnh ghi tương đối:

~~~java
buffer.put((byte) 'A');
buffer.put((byte) 'B');
buffer.put((byte) 'C');
~~~

Mỗi `put(byte)` đặt một byte tại `position` hiện tại, sau đó tăng `position` lên 1. Sau ba lệnh:

~~~text
position = 3
limit    = 8
capacity = 8
remaining = 5
~~~

Đó là trạng thái **đang ghi/fill**. `limit` vẫn là 8 vì chưa gọi `flip()`. Nếu gọi `get()` ngay lúc này, `get()` sẽ đọc từ index 3 (nếu còn trong limit), nơi có thể chứa byte cũ hoặc byte không thuộc đợt ghi hiện tại. Không có cơ chế tự động hiểu “3 byte vừa ghi là toàn bộ dữ liệu hợp lệ”.

Lệnh `channel.read(buffer)` cũng thuộc pha **ghi vào buffer**: channel lấy dữ liệu từ nguồn rồi đưa vào các vị trí từ `position` đến trước `limit`. Nếu đọc được `n > 0` byte, `position` tăng `n`. Giá trị `0` có thể xuất hiện khi chưa có dữ liệu hoặc thao tác không tạo tiến triển; `-1` báo kết thúc đầu vào với `ReadableByteChannel`.

Lưu ý về giới hạn: nếu `position == limit` thì `remaining() == 0`, một lệnh `put(byte)` tương đối nữa sẽ ném `BufferOverflowException`. `ByteBuffer` không tự nới dung lượng.

## 3. Giai đoạn 2: `flip()` chuyển từ ghi sang đọc

Sau khi ghi xong *một đợt*, gọi:

~~~java
buffer.flip();
~~~

`flip()` thực hiện về mặt trạng thái:

~~~text
limit = position cũ
position = 0
mark bị hủy (nếu có)
capacity không đổi
~~~

Trước và sau khi ghi A, B, C vào buffer 8 byte:

| Thời điểm | position | limit | capacity | remaining |
| --- | ---: | ---: | ---: | ---: |
| Mới tạo | 0 | 8 | 8 | 8 |
| Sau 3 lần `put` | 3 | 8 | 8 | 5 |
| Sau `flip()` | 0 | 3 | 8 | 3 |

~~~text
index:      0   1   2   3   4   5   6   7
dữ liệu:    A   B   C   ?   ?   ?   ?   ?
           └─ vùng đọc ─┘└── ngoài limit ─────┘
position = 0          limit = 3          capacity = 8
~~~

Lúc này `get()` có thể đọc đúng **3 byte vừa ghi**, và không đọc vào phần trống sau index 2.

`flip()` **không** đảo byte, không di chuyển dữ liệu, không cấp phát vùng nhớ mới và không chuyển ByteBuffer thành đối tượng read-only. Tên “flip” chỉ diễn tả đổi ranh giới truy cập: phần dữ liệu vừa được tạo trở thành vùng sẽ được tiêu thụ.

**Nhầm lẫn thường gặp:** gọi `flip()` hai lần liên tiếp mà không ghi/đọc có mục đích. Sau `flip` đầu, `position = 0`; `flip` thứ hai đặt `limit = 0`, khiến buffer trông như không còn byte nào để đọc. Chỉ `flip()` sau pha ghi thực sự.

## 4. Giai đoạn 3: đọc *khỏi* buffer

Sau `flip()`:

~~~java
while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Xử lý value.
}
~~~

Mỗi `get()` tương đối lấy phần tử tại `position` hiện tại rồi tăng `position`. Khi đã đọc A, B, C:

~~~text
position = 3
limit    = 3
remaining = 0
hasRemaining() = false
~~~

Nếu gọi thêm `get()` tương đối thì phát sinh `BufferUnderflowException` vì đã vượt giới hạn dữ liệu đang được phép đọc.

Vòng `while (buffer.hasRemaining())` diễn đạt rõ “đọc cho tới hết phần đang có”. Nếu cần biết số byte chưa đọc, dùng `remaining()` thay vì `capacity - position`: sau `flip`, phần từ `limit` tới `capacity` không thuộc dữ liệu của đợt hiện tại.

### Tương đối và tuyệt đối

- `get()` và `put(value)` là thao tác **tương đối**, làm thay đổi `position`.
- `get(index)` và `put(index, value)` là thao tác **tuyệt đối**, tác động tới chỉ số được chỉ định nhưng **không tự tăng `position`**. Các lệnh này vẫn kiểm tra giới hạn index và khả năng đọc/ghi.
- Nếu dùng cả hai kiểu lẫn nhau, phải xác định rõ `position` có còn biểu diễn đúng nơi sẽ tiếp tục đọc/ghi hay không.

Đối với bài toán xử lý dữ liệu tuần tự, `put` rồi `flip` rồi `get` tương đối thường dễ theo dõi nhất.

## 5. Sơ đồ vòng đời chuẩn

~~~text
        ┌──────────────────────────────┐
        │ FILL: ghi dữ liệu vào buffer │
        │ put(...) / channel.read(...)│
        │ position tăng, limit giữ    │
        └───────────────┬──────────────┘
                        │ flip()
                        ▼
        ┌──────────────────────────────┐
        │ DRAIN: đọc dữ liệu có sẵn    │
        │ get(...) / channel.write(...)│
        │ position tăng tới limit     │
        └───────────────┬──────────────┘
                        │
               Đã đọc hết dữ liệu?
                  /            \
                Có             Còn dư
                │                │
              clear()         compact()
                │                │
                └─────→ FILL ←───┘
~~~

Khi đọc một file vào channel rồi đọc khỏi buffer, chu trình quen thuộc là:

1. Buffer còn chỗ trống: ghi từ nguồn vào buffer.
2. `flip()`: đặt ranh giới dữ liệu vừa nhận để có thể đọc.
3. Đọc/ghi ra khỏi buffer trong phạm vi `position..limit`.
4. Nếu không còn dữ liệu chưa xử lý, dùng `clear()`. Nếu còn dữ liệu chưa tiêu thụ, cân nhắc `compact()`.
5. Tiếp tục đợt ghi vào buffer mới.

**Không phải mọi lần đọc channel sẽ lấp đầy buffer**, và không phải mọi lần ghi channel sẽ tiêu thụ toàn bộ dữ liệu. Luôn dựa vào `position`, `remaining()` và kết quả I/O thực tế.

## 6. Chương trình Java 17+ chạy độc lập: ghi → flip → đọc

Lưu file `BufferCycleDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferCycleDemo {

    private static void state(String name, ByteBuffer b) {
        System.out.printf(
                "%s: position=%d, limit=%d, capacity=%d, remaining=%d%n",
                name, b.position(), b.limit(), b.capacity(), b.remaining());
    }

    private static String readAscii(ByteBuffer b) {
        StringBuilder result = new StringBuilder();
        while (b.hasRemaining()) {
            result.append((char) b.get());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        state("new", b);

        b.put((byte) 'A');
        b.put((byte) 'B');
        b.put((byte) 'C');
        state("written", b);

        b.flip();
        state("flipped", b);

        System.out.println("read = " + readAscii(b));
        state("drained", b);

        b.rewind();
        System.out.println("reread = " + readAscii(b));

        b.clear();
        state("cleared", b);
        b.put((byte) 'X');
        b.flip();
        System.out.println("next = " + readAscii(b));

        ByteBuffer partial = ByteBuffer.allocate(6);
        partial.put("ABCD".getBytes(StandardCharsets.US_ASCII));
        partial.flip();

        System.out.println(
                "consumed = " + (char) partial.get() + (char) partial.get());
        state("two read", partial);

        partial.compact();
        state("compacted", partial);
        partial.put((byte) 'E');
        partial.put((byte) 'F');
        partial.flip();

        System.out.println("remaining + new = " + readAscii(partial));
        state("second drained", partial);
    }
}
~~~

Chạy từ thư mục chứa file bằng JDK 17+:

~~~bash
javac BufferCycleDemo.java
java BufferCycleDemo
~~~

Stdout chính xác:

~~~text
new: position=0, limit=8, capacity=8, remaining=8
written: position=3, limit=8, capacity=8, remaining=5
flipped: position=0, limit=3, capacity=8, remaining=3
read = ABC
drained: position=3, limit=3, capacity=8, remaining=0
reread = ABC
cleared: position=0, limit=8, capacity=8, remaining=8
next = X
consumed = AB
two read: position=2, limit=4, capacity=6, remaining=2
compacted: position=2, limit=6, capacity=6, remaining=4
remaining + new = CDEF
second drained: position=4, limit=4, capacity=6, remaining=0
~~~

Vì ví dụ chỉ ghi các ký tự ASCII đơn byte, chuyển từ byte sang `char` trong `readAscii` là đủ cho việc minh họa con trỏ. **Không** dùng cách cast đó làm bộ giải mã UTF-8 tổng quát: ký tự tiếng Việt có thể chiếm nhiều byte. Với dữ liệu văn bản thực tế, dùng `CharsetDecoder` hoặc API giải mã qua `StandardCharsets.UTF_8` và bảo toàn các chuỗi byte chưa đủ tạo thành ký tự hoàn chỉnh.

Đọc các mốc quan trọng:

- `written`: ba byte vừa được ghi nhưng `limit` vẫn là 8.
- `flipped`: `position` về 0, `limit` thành 3, đúng số byte đã ghi.
- `drained`: vòng `readAscii` lấy hết ba byte, nên `remaining` về 0.
- `reread`: `rewind()` cho đọc lại A, B, C vì `limit` vẫn là 3.
- `cleared`: `clear()` đặt lại cửa sổ ghi; tiếp theo chỉ ghi X và `flip`, vì vậy lần đọc mới chỉ thấy X.
- `two read`/`compacted`: hai byte C, D chưa đọc được giữ lại để ghép thêm E, F ở đợt kế tiếp.

## 7. `clear()`, `rewind()` và `compact()` khác nhau thế nào?

Ba thao tác này **không tương đương**, dù đều thường xuất hiện gần cuối pha đọc.

### `clear()`: chuẩn bị ghi mới, bỏ qua phần chưa đọc

~~~java
buffer.clear();
~~~

Tác dụng:

~~~text
position = 0
limit = capacity
mark bị hủy
~~~

`clear()` **không xóa dữ liệu vật lý** trong backing array hoặc bộ nhớ trực tiếp; tên phương thức có nghĩa là “đặt lại trạng thái truy cập để sử dụng lại vùng chứa”. Nếu trước `clear` vẫn còn dữ liệu chưa đọc, chương trình đang chủ động bỏ qua chúng. Do đó chỉ dùng `clear()` khi đã tiêu thụ xong nội dung cũ hoặc quyết định không cần nó nữa.

### `rewind()`: đọc lại cùng vùng dữ liệu

~~~java
buffer.rewind();
~~~

Tác dụng:

~~~text
position = 0
limit giữ nguyên
mark bị hủy
~~~

Sau khi đọc hết A, B, C và có `limit=3`, `rewind()` cho phép đọc lại cả ba byte mà không gọi `flip()` lần nữa. `rewind()` phù hợp khi cần quét lại dữ liệu trong cửa sổ hiện tại, không nhằm chuẩn bị nhận đợt dữ liệu mới từ channel.

### `compact()`: giữ phần chưa đọc, mở chỗ để ghi tiếp

Giả sử buffer 6 byte chứa A, B, C, D đã `flip` rồi chỉ đọc A và B:

~~~text
index:        0   1   2   3   4   5
data:         A   B   C   D   ?   ?
                  ↑       ↑
             position=2  limit=4
unread: C D
~~~

Gọi:

~~~java
buffer.compact();
~~~

Khi đó `compact()` chuyển **hai byte còn chưa đọc (C, D)** lên đầu buffer, rồi đặt:

~~~text
index:        0   1   2   3   4   5
data:         C   D   ?   ?   ?   ?
position = 2
limit    = 6
capacity = 6
remaining = 4
~~~

Dấu `?` không tuyên bố bộ nhớ được dọn sạch: các byte bên ngoài phần dữ liệu hợp lệ có thể vẫn chứa giá trị cũ. Sau `compact`, buffer sẵn sàng **ghi nối tiếp từ position 2**. Ghi thêm E, F rồi `flip` sẽ cho vùng đọc C, D, E, F.

`compact()` là bước đặc biệt hữu ích khi một gói tin, bản ghi hoặc ký tự nhiều byte chưa được nhận đủ để xử lý. Nó giữ lại dữ liệu chưa tiêu thụ. Nếu buffer là read-only, `compact()` sẽ ném `ReadOnlyBufferException`.

| Phương thức | position sau gọi | limit sau gọi | Phần dữ liệu còn dùng |
| --- | --- | --- | --- |
| `flip()` | 0 | position cũ | Dữ liệu vừa ghi, từ 0 tới position cũ |
| `clear()` | 0 | capacity | Không cam kết giữ dữ liệu cũ để đọc tiếp |
| `rewind()` | 0 | limit cũ | Cùng vùng dữ liệu trong limit hiện tại |
| `compact()` | Số phần tử chưa đọc | capacity | Các phần tử từ position cũ tới limit cũ, đã dồn lên đầu |

`compact()` tiêu tốn công di chuyển phần tử chưa đọc; nếu đã tiêu thụ hết thì `clear()` dễ hiểu và thường không cần sao chép gì.

## 8. Gắn chu trình với `Channel`

Có hai chiều nhìn dễ gây nhầm:

- `channel.read(buffer)`: **đọc từ channel**, nghĩa là **ghi vào buffer**. Nó làm tăng `buffer.position()` theo số byte đọc được.
- `channel.write(buffer)`: **ghi vào channel**, nghĩa là **đọc ra khỏi buffer**. Nó làm tăng `buffer.position()` theo số byte thực sự được ghi.

Dòng chảy khi sao chép tệp:

~~~text
Source FileChannel
     │ read(buffer)   — fill
     ▼
ByteBuffer: position tiến về limit/capacity
     │ flip()
     ▼
ByteBuffer: position=0, limit=số byte đã nhận
     │ write(buffer)  — drain
     ▼
Destination FileChannel
     │ clear() hoặc compact()
     └────────────────────→ đợt tiếp theo
~~~

### Ví dụ minh họa sao chép tệp theo đợt

Đoạn này dành cho trường hợp có sẵn hai đối tượng `FileChannel input`, `FileChannel output` mở ở chế độ đọc/ghi phù hợp. **Đây là mảnh code minh họa nằm trong phương thức**, không phải chương trình Java độc lập:

~~~java
ByteBuffer buf = ByteBuffer.allocate(4096);
int count;
while ((count = input.read(buf)) != -1) {
    buf.flip();
    while (buf.hasRemaining()) {
        output.write(buf);
    }
    buf.clear();
}
~~~

Ý nghĩa:

1. `input.read(buf)` điền byte vào buffer; không giả định sẽ nhận đủ 4096 byte.
2. `flip()` đặt `limit` bằng số byte đã có.
3. Vòng `while (buf.hasRemaining())` bảo đảm output channel có cơ hội nhận hết những byte chưa ghi. Một lần `write` không nhất thiết tiêu thụ hết buffer.
4. `clear()` an toàn trong ví dụ này vì vòng trước chỉ hoàn thành khi đã chuyển hết byte trong buffer.
5. `read` trả `-1` báo EOF; không còn đợt byte mới để đưa vào buffer.

Đoạn code trên thể hiện chu trình cho kênh tệp thông thường; với **non-blocking channel**, `read/write` có thể trả `0` khi chưa tiến triển. Đặc biệt, không được bận chờ vô hạn bằng một vòng `while` gọi `write` liên tục nếu đầu ra chưa sẵn sàng. Trong môi trường NIO không chặn, hãy dùng `Selector`/khả năng sẵn sàng ghi hoặc cơ chế điều phối phù hợp, đồng thời giữ lại phần dữ liệu chưa gửi bằng `compact()` hoặc không chuyển trạng thái buffer sai lúc.

Với dữ liệu phân mảnh (chẳng hạn một bản ghi chưa đủ byte để phân tích), quy tắc là **sau `flip` chỉ tiêu thụ các bản ghi hoàn chỉnh; sau đó `compact` để giữ phần đuôi chưa xử lý**, trước khi đọc thêm từ nguồn. `clear` sẽ làm mất vùng dữ liệu cần ghép giữa hai đợt.

## 9. Những lỗi hay gặp khi quản lý `position` và `limit`

### Quên `flip()` trước khi đọc

~~~java
ByteBuffer b = ByteBuffer.allocate(8);
b.put((byte) 'A');
byte x = b.get(); // Sai mục đích: đọc từ position=1, không phải A ở index=0.
~~~

`get()` ở ví dụ có thể trả giá trị cũ ở index 1, không ném lỗi, khiến bug khó nhận ra. Cách sửa là gọi `b.flip()` trước khi bắt đầu đọc byte vừa ghi.

### Dùng `flip()` thay `clear()` trước lượt ghi mới

Sau khi đọc hết buffer, `position == limit`. Gọi `flip()` sẽ đặt `limit` thành số byte đã đọc và `position` về 0, chưa chắc mang ý nghĩa “chuẩn bị ghi mới với toàn bộ capacity”. Để tái sử dụng buffer cho đợt ghi mới, dùng `clear()` nếu không còn dữ liệu cần bảo toàn, hoặc `compact()` nếu còn dữ liệu chưa xử lý.

### Dùng `clear()` khi vẫn còn byte chưa xử lý

Giả sử đã nhận một phần bản tin, chỉ xử lý được header mà body chưa đủ. `clear()` đặt lại vùng ghi nhưng loại bỏ trạng thái chỉ ra phần body đang đợi. Kết quả là bản tin bị mất/không ghép được. Với dữ liệu chưa đọc nằm ở đoạn `position..limit`, dùng `compact()`.

### Đọc quá `limit` hoặc ghi khi hết chỗ

Các thao tác tương đối kiểm tra trạng thái:

- `get()` khi `position == limit` ⇒ `BufferUnderflowException`.
- `put(byte)` khi `position == limit` ⇒ `BufferOverflowException`.

Dùng `hasRemaining()` hoặc `remaining()`; khi ghi nhiều byte trong một lần, kiểm tra còn đủ chỗ trước khi gọi.

### Tưởng `capacity` là số byte hợp lệ

`capacity` phản ánh dung lượng vùng chứa, không phải lượng dữ liệu đã nhận. Sau `flip()`, **`limit`** là ranh giới dữ liệu có thể đọc; `remaining()` là số phần tử chưa đọc tính từ `position`.

### Tưởng `flip()` biến `ByteBuffer` thành dữ liệu văn bản

Buffer là dãy byte. Với UTF-8, một ký tự có thể trải qua nhiều lần `channel.read`. Đọc từng byte và cast sang `char` chỉ đáng tin với ASCII trong ví dụ học tập. Khi xây parser text, dùng charset decoder hỗ trợ chuỗi byte chưa hoàn chỉnh và xử lý trạng thái cuối luồng đúng cách.

### Hiểu sai `mark()` và `reset()`

`mark()` lưu position hiện tại; `reset()` quay về mark nếu còn hợp lệ. `flip()`, `clear()`, `rewind()` và `compact()` đều hủy mark, nên `reset()` sau các thao tác đó sẽ ném `InvalidMarkException`. Hãy đặt mark lại sau khi chuyển trạng thái nếu cần.

## 10. Tự kiểm tra

1. Một `ByteBuffer.allocate(10)` vừa được `put` 4 byte. Hãy xác định `position=4`, `limit=10`. Sau `flip()`, kết quả là `position=0`, `limit=4`, `remaining=4`.
2. Sau `flip` của câu 1, chương trình đọc 2 byte. Còn `remaining=2`. Nếu muốn giữ hai byte đó và ghi nối đợt sau, chọn **`compact()`**, khi đó `position=2`, `limit=10`.
3. Nếu đã đọc hết tất cả byte trong buffer và cần ghi đợt mới, chọn **`clear()`**. Vì sao không cần `compact()`? Không còn dữ liệu chưa đọc để dồn về đầu.
4. Nếu muốn đọc lại cùng 4 byte mà không thay đổi `limit`, chọn **`rewind()`**.
5. Một `channel.write(buffer)` ghi được ít byte hơn `buffer.remaining()`. Vì sao không `clear()` ngay? Vì phần còn lại trong buffer chưa được gửi, phải giữ để gửi tiếp.
6. Tại sao `flip()` là bước bắt buộc trong mô hình ghi rồi đọc tương đối? Vì nó đặt `limit` đúng bằng lượng dữ liệu vừa ghi, đồng thời đưa `position` về đầu vùng dữ liệu hợp lệ.

**Ghi nhớ thực hành:** Mẫu chuẩn là **`put`/`channel.read` → `flip` → `get`/`channel.write` → `clear` hoặc `compact`**. Luôn dùng `position`, `limit` và `remaining()` làm bằng chứng cho byte nào đang có, byte nào đã được tiêu thụ và chỗ nào còn có thể ghi.
