# Java NIO Buffer: `rewind()`, `compact()` và `reset()`

## 1. Vì sao cần phân biệt ba thao tác này?

Khi dùng `java.nio.ByteBuffer` để đọc dữ liệu từ tệp/socket hoặc để ghép các mảnh thông điệp, ta thường luân phiên giữa **ghi dữ liệu vào buffer** và **đọc dữ liệu đã có trong buffer**. Vấn đề xuất hiện khi muốn:

- **Đọc lại từ đầu vùng đang được phép đọc:** dùng `rewind()`.
- **Giữ phần dữ liệu chưa xử lý, dồn nó về đầu để có chỗ nhận thêm dữ liệu:** dùng `compact()`.
- **Quay lại đúng vị trí đã đánh dấu trước đó:** dùng `mark()` kết hợp `reset()`.

Ba thao tác đều liên quan đến con trỏ, nhưng **không có cùng ý nghĩa**. Chọn sai có thể làm chương trình đọc lại dữ liệu cũ, bỏ sót phần dữ liệu còn dang dở hoặc cố đọc các byte chưa hợp lệ.

Bài viết dùng `ByteBuffer` trên Java 17+ để diễn giải; các nguyên tắc chung về `position`, `limit`, `mark` cũng áp dụng cho họ `java.nio.Buffer`. `compact()` là phương thức của các kiểu buffer cụ thể hỗ trợ nó (chẳng hạn `ByteBuffer`, `CharBuffer`), không phải phương thức trừu tượng của lớp nền `Buffer`.

## 2. Bốn trạng thái cần nắm: capacity, limit, position, mark

| Thuộc tính | Ý nghĩa |
|---|---|
| `capacity` | Số phần tử tối đa buffer có thể chứa; cố định trong vòng đời một buffer. Với `ByteBuffer`, đơn vị là **byte**. |
| `limit` | Ranh giới đầu tiên **không được** truy cập bằng thao tác tương đối; index hợp lệ nằm trước `limit`. |
| `position` | Vị trí của thao tác `get()` / `put()` tương đối tiếp theo; một lần `get()` hoặc `put()` thành công thường tăng `position` thêm một phần tử. |
| `mark` | Mốc tùy chọn do `mark()` ghi nhớ; `reset()` dùng để quay lại mốc này. Mark ban đầu **không được định nghĩa**. |

Với buffer có mark hợp lệ, bất biến là:

~~~text
0 <= mark <= position <= limit <= capacity
~~~

Nếu mark chưa được đặt, vẫn có `0 <= position <= limit <= capacity`.

Các API hữu ích:

- `buffer.position()`, `buffer.limit()`, `buffer.capacity()`: xem các giá trị.
- `buffer.remaining()` = `limit - position`; `buffer.hasRemaining()` cho biết còn vùng có thể truy cập tương đối hay không.
- `buffer.get()` / `buffer.put(value)`: truy cập tương đối và **dịch position**.
- `buffer.get(index)` / `buffer.put(index, value)`: truy cập theo index tuyệt đối và **không dịch position**.
- `buffer.mark()`: đặt mark = position hiện tại.
- `buffer.reset()`: đưa position trở lại mark.

**Các thao tác điều khiển vị trí không có nghĩa tự xóa dữ liệu.** Chúng thay đổi vùng đang được xem là hợp lệ cho lần đọc/ghi kế tiếp. Đối với `compact()`, còn có hành động **di chuyển dữ liệu còn lại** trong bộ nhớ.

### Ví dụ trạng thái khi nạp dữ liệu

Giả sử:

~~~java
ByteBuffer buf = ByteBuffer.allocate(8); // position=0, limit=8, capacity=8
buf.put(new byte[] {10, 20, 30, 40, 50}); // position=5, limit=8
buf.flip(); // position=0, limit=5: chuẩn bị đọc 5 byte hợp lệ
~~~

Sơ đồ sau `flip()`:

~~~text
index:      0    1    2    3    4   | 5    6    7
data:      10   20   30   40   50   | ?    ?    ?
           ^ position=0             ^ limit=5      capacity=8
usable:    [----- 5 byte có thể đọc -----)
~~~

Dấu `?` biểu thị các vị trí **ngoài vùng đọc hiện tại**. Mặc dù `ByteBuffer.allocate` cấp vùng bộ nhớ được khởi tạo ban đầu bằng 0, ta vẫn không nên coi những phần tử bên ngoài `limit` là dữ liệu của thông điệp.

## 3. `rewind()`: đọc lại từ đầu vùng hiện tại

**Quy tắc chính thức:**

- `position = 0`.
- **Giữ nguyên `limit` và `capacity`**.
- **Bỏ mark**, nếu trước đó đã đặt.
- **Không sao chép/xóa nội dung** trong buffer.

Ví dụ (đoạn minh họa, cần `import java.nio.ByteBuffer;`):

~~~java
ByteBuffer buf = ByteBuffer.allocate(6);
buf.put(new byte[] {10, 20, 30, 40});
buf.flip();  // p=0, l=4, c=6
buf.get();   // 10; p=1
buf.get();   // 20; p=2

buf.rewind(); // p=0, l=4, c=6
byte firstAgain = buf.get(); // 10; p=1
~~~

Sau `rewind()`, bốn byte `10, 20, 30, 40` vẫn có thể được đọc theo giới hạn `limit=4`. Phương thức này **không biến buffer thành vùng ghi trống**.

**Khi nên dùng:**

- Cần phân tích lại cùng payload từ đầu.
- Cần xuất/gửi lại toàn bộ vùng dữ liệu đã chuẩn bị, với điều kiện `limit` vẫn mô tả đúng độ dài payload.
- Cần so sánh hoặc duyệt lại các byte mà không phải tạo/copy một buffer khác.

**Khi không nên dùng:** khi một phần thông điệp đã xử lý xong và phần **chưa xử lý** cần giữ lại để nhận thêm dữ liệu. `rewind()` sẽ quay về index 0 và khiến các byte đã xử lý cũng được đọc lại. Lúc đó cân nhắc `compact()`.

### `rewind()` và `flip()` không giống nhau

Nếu `position=3, limit=8, capacity=8`:

- `rewind()` → `position=0, limit=8`.
- `flip()` → `position=0, limit=3`.

`flip()` chuyển từ giai đoạn ghi sang đọc bằng cách **lấy position cũ làm limit mới**. `rewind()` giữ nguyên limit đã có để **đọc lại** vùng hiện tại.

Một lỗi điển hình là gọi `rewind()` ngay sau khi `put` mà chưa `flip()`: do `limit` vẫn bằng capacity, chương trình có thể đọc vượt ra ngoài số byte payload thực tế vừa ghi.

## 4. `reset()`: quay lại mark đã đặt

`reset()` không có nghĩa là đưa buffer về trạng thái mới tạo và cũng **không** có nghĩa tự động về vị trí 0.

Quy tắc:

1. Gọi `mark()` để lưu `mark = position`.
2. Đọc hoặc dịch `position` về phía trước.
3. Gọi `reset()` để đặt **`position = mark`**.
4. `limit` và `capacity` **không đổi**.
5. **Mark vẫn còn hợp lệ sau `reset()`**, vì thế có thể `reset()` nhiều lần, miễn chưa bị thao tác khác hủy.

Ví dụ:

~~~java
ByteBuffer buf = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
buf.get();     // 10; p=1
buf.mark();    // mark=1
buf.get();     // 20; p=2
buf.get();     // 30; p=3
buf.reset();   // p=1
byte again = buf.get(); // 20; p=2
buf.reset();   // p=1, vì mark chưa bị hủy
~~~

Phân biệt rõ:

- `mark()` **chỉ ghi nhớ vị trí**, không copy dữ liệu tại vị trí ấy.
- `reset()` **chỉ đặt lại vị trí**, không phục hồi byte đã bị ghi đè.
- Nếu gọi `reset()` khi chưa có mark hợp lệ, Java ném `java.nio.InvalidMarkException` (**unchecked exception**).

### Những thao tác làm mark mất hiệu lực

`clear()`, `flip()`, `rewind()` và `compact()` **luôn hủy mark**. Ngoài ra, `position(newPosition)` hủy mark nếu `newPosition < mark`; `limit(newLimit)` hủy mark nếu `newLimit < mark`. Đặt mark mới bằng `mark()` sẽ thay mốc cũ.

Ví dụ:

~~~java
ByteBuffer buf = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
buf.position(2).mark(); // mark=2
buf.position(1);        // Dịch về trước mark -> hủy mark
buf.reset();            // Ném InvalidMarkException
~~~

Trái lại, đọc theo index tuyệt đối như `buf.get(0)` **không thay position**, nên tự nó không làm mất mark.

**Tình huống điển hình:** parser đọc thử header, đặt mark trước một trường có độ dài biến đổi; nếu chưa đủ byte hoặc nhánh xử lý không phù hợp thì `reset()` để đọc lại đoạn đó. Với parser phức tạp có nhiều điểm rollback, một mark duy nhất có thể không đủ; có thể lưu vị trí vào biến `int saved = buffer.position()` và khôi phục có kiểm soát bằng `position(saved)`, lưu ý giới hạn hiện tại và quy tắc hủy mark.

## 5. `compact()`: giữ dữ liệu chưa đọc, tạo chỗ để ghi tiếp

Khác hai phương thức trên, `compact()` **di chuyển các phần tử còn lại** từ đoạn `[position, limit)` về đầu buffer.

Gọi:

- `p = position` trước khi compact.
- `l = limit` trước khi compact.
- `n = l - p = remaining()`.

Sau `compact()` trên buffer có thể ghi:

1. Sao chép `n` phần tử của đoạn `[p, l)` vào đoạn `[0, n)` theo đúng thứ tự.
2. Đặt `position = n`, **không phải 0**.
3. Đặt `limit = capacity`.
4. Hủy mark.
5. Trả buffer về **trạng thái sẵn sàng `put` thêm** sau phần dữ liệu còn dở.

### Ví dụ nhìn thấy phần byte được giữ lại

~~~text
Trước compact:
capacity = 8, position = 2, limit = 5
index:       0    1  | 2    3    4  | 5    6    7
data:       10   20  |30   40   50  | ?    ?    ?
              đã đọc   ^----- chưa đọc -----^
remaining = 5 - 2 = 3

Sau compact:
capacity = 8, position = 3, limit = 8
index:       0    1    2  | 3    4    5    6    7
data:       30   40   50  | ... vùng dành để ghi mới ...
                            ^ position=3
~~~

Các vị trí ngoài ba phần tử vừa được giữ lại có thể vẫn chứa byte cũ; **`compact()` không hứa xóa sạch phần còn lại**.

Thực hành:

~~~java
ByteBuffer buf = ByteBuffer.allocate(8);
buf.put(new byte[] {10, 20, 30, 40, 50});
buf.flip();                  // p=0, l=5
buf.get();                   // 10; p=1
buf.get();                   // 20; p=2

buf.compact();               // còn [30,40,50]; p=3, l=8
buf.put(new byte[] {60, 70}); // p=5, l=8
buf.flip();                  // p=0, l=5

// Năm byte có thể đọc: 30, 40, 50, 60, 70.
~~~

**Chu trình chuẩn:** `flip() → xử lý được một phần → compact() → nạp tiếp → flip()`.

### Vì sao không `rewind()` sau `compact()`?

Ngay sau `compact()`, buffer đang ở **chế độ ghi**: `position = số byte chưa xử lý`, `limit = capacity`. Gọi `rewind()` lúc này sẽ đặt `position=0` nhưng **giữ `limit=capacity`**, nên có thể đọc cả byte cũ hoặc byte chưa phải một phần của payload. Khi muốn đọc phần dữ liệu đã có sau khi ghi bổ sung, dùng **`flip()`** để giới hạn đúng số byte hợp lệ.

### Nếu không còn byte chưa đọc thì sao?

Nếu trước `compact()` có `position == limit` thì `remaining=0`:

- Không còn phần tử nào được chuyển về đầu.
- Kết quả là `position=0, limit=capacity`.
- Có thể tiếp tục nạp dữ liệu mới, giống trạng thái sẵn sàng ghi của `clear()` về mặt các con trỏ.

Nhưng ý nghĩa hai thao tác vẫn khác nhau: `compact()` được dùng theo chính sách **bảo toàn phần chưa xử lý**; `clear()` tuyên bố bỏ vùng đọc hiện tại và sẵn sàng ghi mới. Cả hai đều không đảm bảo xóa byte cũ khỏi bộ nhớ.

### Buffer chỉ đọc và tính khả chuyển

`compact()` là thao tác **ghi/copy các phần tử** bên trong buffer; với `ByteBuffer` chỉ đọc (ví dụ từ `asReadOnlyBuffer()`), nó ném `ReadOnlyBufferException`. Trong khi đó `rewind()`, `mark()` và `reset()` vẫn có thể điều chỉnh vị trí của một buffer chỉ đọc.

Các buffer kiểu `ByteBuffer`, `CharBuffer` và các buffer nguyên thủy khác có thể hỗ trợ `compact()` theo phần tử của chúng. Vị trí và số lượng trong `CharBuffer` tính theo **char code unit**, không phải byte; trong `IntBuffer` tính theo số nguyên 32-bit. Đừng lấy đơn vị byte của `ByteBuffer` áp đặt cho mọi buffer.

## 6. Bảng so sánh trực tiếp

Giả sử trước thao tác: `position=p`, `limit=l`, `capacity=c` và có thể đã đặt mark.

| Phương thức | position sau gọi | limit sau gọi | Dữ liệu | Mark sau gọi | Sử dụng |
|---|---:|---:|---|---|---|
| `rewind()` | `0` | `l` (không đổi) | Không di chuyển/xóa | Bị hủy | Đọc lại từ đầu vùng hiện tại |
| `reset()` | `mark` cũ | `l` (không đổi) | Không di chuyển/xóa | **Giữ nguyên** | Quay lại mốc đã đánh dấu |
| `compact()` | `l - p` | `c` | **Dời dữ liệu chưa đọc về đầu** | Bị hủy | Giữ phần còn dở để ghi thêm |
| `flip()` *(đối chiếu)* | `0` | `p` cũ | Không di chuyển/xóa | Bị hủy | Chuyển ghi → đọc |
| `clear()` *(đối chiếu)* | `0` | `c` | Không xóa vật lý | Bị hủy | Chuẩn bị ghi mới, bỏ qua dữ liệu còn dở |

Nếu chưa từng `mark()`, `reset()` ném `InvalidMarkException`. `compact()` có thể ném `ReadOnlyBufferException` nếu buffer là read-only.

**Mẹo nhớ:**

- **re-wind** → đưa con trỏ về **đầu** để đọc lại;
- **re-set** → đưa con trỏ về **mốc mark**;
- **com-pact** → **nén phần chưa đọc về đầu**, đặt con trỏ sau phần được giữ lại để ghi tiếp.

## 7. Chương trình Java 17+ chạy được và stdout chính xác

Lưu mã sau thành **`BufferNavigationDemo.java`**. Chương trình tách hai buffer để theo dõi hai luồng: đọc lại bằng mark/rewind và xử lý phần còn dở bằng compact.

~~~java
import java.nio.ByteBuffer;
import java.nio.InvalidMarkException;
import java.util.StringJoiner;

public class BufferNavigationDemo {

    private static void show(String name, ByteBuffer b) {
        System.out.printf(
                "%s: p=%d, l=%d, c=%d, remaining=%d%n",
                name, b.position(), b.limit(),
                b.capacity(), b.remaining());
    }

    public static void main(String[] args) {
        // Phần 1: mark/reset và rewind.
        ByteBuffer a = ByteBuffer.allocate(6);
        a.put(new byte[] {10, 20, 30, 40});
        a.flip();

        show("after flip", a);
        System.out.println("first=" + Byte.toUnsignedInt(a.get()));

        a.mark(); // mark = 1
        System.out.println("next=" + Byte.toUnsignedInt(a.get()));
        System.out.println("another=" + Byte.toUnsignedInt(a.get()));

        a.reset(); // Quay về mark = 1.
        show("after reset", a);
        System.out.println("again=" + Byte.toUnsignedInt(a.get()));

        a.rewind(); // Về position = 0, hủy mark.
        show("after rewind", a);
        System.out.println("replay=" + Byte.toUnsignedInt(a.get()));

        try {
            a.reset(); // Mark đã bị rewind() hủy.
        } catch (InvalidMarkException e) {
            System.out.println("reset after rewind: InvalidMarkException");
        }

        // Phần 2: giữ byte chưa xử lý rồi ghi tiếp.
        ByteBuffer b = ByteBuffer.allocate(8);
        b.put(new byte[] {10, 20, 30, 40, 50});
        b.flip();

        System.out.println("consumed="
                + Byte.toUnsignedInt(b.get()) + ","
                + Byte.toUnsignedInt(b.get()));
        show("before compact", b);

        b.compact(); // Giữ 30,40,50 ở đầu; p=3, l=8.
        show("after compact", b);
        b.put(new byte[] {60, 70});
        b.flip();
        show("after next flip", b);

        StringJoiner values = new StringJoiner(",");
        while (b.hasRemaining()) {
            values.add(Integer.toString(Byte.toUnsignedInt(b.get())));
        }
        System.out.println("recovered=" + values);
    }
}
~~~

Chạy từ thư mục chứa file nguồn:

~~~bash
javac BufferNavigationDemo.java
java BufferNavigationDemo
~~~

**Stdout:**

~~~text
after flip: p=0, l=4, c=6, remaining=4
first=10
next=20
another=30
after reset: p=1, l=4, c=6, remaining=3
again=20
after rewind: p=0, l=4, c=6, remaining=4
replay=10
reset after rewind: InvalidMarkException
consumed=10,20
before compact: p=2, l=5, c=8, remaining=3
after compact: p=3, l=8, c=8, remaining=5
after next flip: p=0, l=5, c=8, remaining=5
recovered=30,40,50,60,70
~~~

**Giải thích kết quả:**

1. Buffer `a` có 4 byte đã nạp nên sau `flip()`: `p=0, l=4, c=6`. `get()` trả 10 rồi dịch con trỏ đến 1.
2. `mark()` đặt mốc 1. Hai lần đọc tiếp nhận 20, 30. `reset()` phục hồi `p=1`, vì thế lần đọc tiếp lại nhận 20.
3. `rewind()` đặt `p=0`, vẫn giữ `l=4`; đọc lần nữa được 10. Vì mark đã bị xóa, `reset()` sau đó ném `InvalidMarkException`.
4. Buffer `b` đã xử lý 10 và 20, còn đúng ba byte `30,40,50`. `compact()` chuyển ba byte đó đến đầu và đặt `p=3, l=8`.
5. Thêm 60 và 70 tại hai vị trí kế tiếp làm `p=5`; `flip()` đặt `p=0, l=5`. Kết quả đọc là **30,40,50,60,70**, không có hai byte đã xử lý.

## 8. Ví dụ ứng dụng: đọc bản ghi không trọn vẹn từ FileChannel

Giả sử giao thức truyền dữ liệu gồm các bản ghi **mỗi bản ghi đúng 4 byte**, được giải mã bằng `getInt()`. Một lần `FileChannel.read(buffer)` có thể điền vào buffer một số byte không đủ bội số của 4. Khi đó phần dư phải được giữ cho lượt đọc tiếp theo.

Ví dụ sau là **đoạn minh họa** nằm trong phương thức xử lý; `input` là `FileChannel` đang mở để đọc từ một nguồn tệp, và đoạn xử lý phải xử lý ngoại lệ I/O:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);

while (input.read(buffer) != -1) {
    buffer.flip(); // Chuyển phần vừa nạp + phần còn dư sang chế độ đọc.

    while (buffer.remaining() >= Integer.BYTES) {
        int value = buffer.getInt(); // Xử lý đúng một bản ghi 4 byte.
        consume(value);              // Hàm ứng dụng định nghĩa.
    }

    // Nếu còn 1..3 byte, giữ chúng và dành chỗ cho lần đọc tiếp.
    buffer.compact();
}

buffer.flip(); // Kiểm tra số byte còn dư sau EOF.
if (buffer.hasRemaining()) {
    throw new java.io.EOFException("Ban ghi 4 byte cuoi bi thieu");
}
~~~

Vì sao dùng `compact()` ở đây?

- Ví dụ một lượt đọc tạo ra 6 byte: parser xử lý 4 byte đầu, còn 2 byte trong vùng `[position, limit)`.
- `compact()` mang 2 byte này về index 0 và đặt `position=2`; lần đọc tiếp của channel bổ sung byte từ index 2.
- Khi có thêm ít nhất 2 byte, `flip()` cho parser đọc tiếp một bản ghi 4 byte hoàn chỉnh.
- Nếu thay bằng `clear()`, phần dư 2 byte bị coi là không còn cần thiết và dễ bị ghi đè; nếu thay bằng `rewind()`, parser có thể đọc lại 4 byte đã xử lý.
- Nếu gặp EOF mà vẫn còn 1..3 byte, dữ liệu cuối **không đủ một bản ghi**; ví dụ chủ động báo lỗi thay vì âm thầm bỏ dữ liệu.

**Lưu ý cho I/O phi chặn (non-blocking):** lượt đọc có thể trả `0` dù chưa EOF; cần tích hợp với cơ chế readiness/selector hoặc kế hoạch chờ phù hợp, tránh vòng lặp bận. Ví dụ trên minh họa cách dùng buffer với `FileChannel` đọc tuần tự; nó không phải bộ giải mã mạng đa luồng hoàn chỉnh. Nếu tệp có byte order khác big-endian mặc định của `ByteBuffer`, phải thiết lập `buffer.order(ByteOrder.LITTLE_ENDIAN)` hoặc theo giao thức tương ứng.

### Một trường hợp gần giống: ghi một phần ra channel

Khi `SocketChannel.write(buffer)` chỉ tiêu thụ **một phần byte còn lại**, buffer vẫn giữ `position` tại điểm chưa gửi. Nếu cần **nối thêm payload** vào cùng buffer trước lượt ghi tiếp, `compact()` đưa các byte chưa gửi về đầu, rồi chương trình có thể `put(...)` phần mới và `flip()` để chuẩn bị gửi lại.

Trường hợp chỉ cần tiếp tục gửi những byte hiện có mà **không thêm dữ liệu**, thường không cần compact: cứ tiếp tục gọi `write(buffer)` theo chính sách readiness đến khi `hasRemaining()==false`. Không dùng `rewind()` vì nó có thể khiến gửi lặp các byte đã được channel tiêu thụ.

## 9. Lỗi hay gặp, nguyên nhân và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Đọc lại cả byte đã xử lý | Dùng `rewind()` thay vì `compact()` sau một lần parse dở | Chỉ compact phần còn lại rồi nạp tiếp, `flip()` trước khi parse lần sau |
| `InvalidMarkException` | Chưa gọi `mark()` hoặc mark bị `flip/clear/rewind/compact` hủy | Đặt mark ngay trước vùng cần thử đọc; theo dõi vòng đời mark |
| `reset()` không về đầu buffer | Mark đã được đặt ở vị trí khác 0 | Dùng `rewind()` nếu thật sự muốn về 0 |
| `rewind()` đọc ra giá trị thừa sau ghi | `limit` còn bằng capacity, chưa `flip()` | `flip()` sau giai đoạn `put` để giới hạn vùng đã ghi |
| `compact()` xong đọc ngay thấy dữ liệu thừa | Compact để buffer trong **trạng thái ghi** với `limit=capacity` | Nạp tiếp khi cần, rồi `flip()` trước khi đọc |
| `BufferUnderflowException` | Đọc nhiều hơn `remaining()` | Kiểm tra đủ số byte trước khi giải mã; compact phần thiếu để nạp tiếp |
| `BufferOverflowException` | Không còn chỗ cho các lệnh `put` | Kiểm tra `remaining()`, xử lý bớt dữ liệu hoặc cấp buffer phù hợp |
| `ReadOnlyBufferException` khi compact | Buffer không cho phép ghi | Dùng buffer writable hoặc copy dữ liệu vào buffer writable mới |
| Thay đổi nội dung sau `reset()` không khôi phục được | Mark chỉ lưu **vị trí** | Nếu cần rollback giá trị, phải quản lý bản sao dữ liệu/transaction riêng |
| Sau `compact()` còn byte cũ trong backing array | Compact không xóa vùng dư | Xem dữ liệu hợp lệ theo `position/limit`, không coi toàn bộ backing array là payload |

## 10. Cách chọn trong tình huống thực tế

- **Cần đọc lại toàn bộ vùng hiện hành:** `rewind()`. Điều kiện: `limit` đã biểu diễn đúng ranh giới đọc.
- **Cần đọc thử và quay lại một điểm cụ thể:** `mark()` rồi `reset()`. Điều kiện: mark còn hợp lệ; không mong mark tự lưu byte cũ.
- **Cần giữ phần chưa parse/chưa gửi để nạp thêm:** `compact()`, tiếp tục `put` hoặc `channel.read(buffer)`, rồi `flip()`.
- **Vừa ghi vào buffer xong và muốn đọc:** `flip()`.
- **Muốn bỏ toàn bộ vùng chưa xử lý để nạp từ đầu:** `clear()`.
- **Cần di chuyển ngẫu nhiên đến một offset bất kỳ:** kiểm tra phạm vi rồi cân nhắc `position(index)`, không dùng `reset()` nếu chưa có mark.

### Tự kiểm tra nhanh

1. `position=4, limit=7, capacity=10`. Sau `rewind()`? **`position=0, limit=7, capacity=10`**.
2. Cùng trạng thái trên, sau `compact()`? **Di chuyển 3 phần tử còn lại về đầu, `position=3, limit=10, capacity=10`**.
3. `mark()` tại 2, đọc đến 5, rồi `reset()`? **`position=2`**, limit không đổi.
4. Gọi `rewind()` rồi `reset()` mà không `mark()` lại? **`InvalidMarkException`**.
5. Sau `compact()` có `position=3, limit=8`; muốn đọc đúng ba byte còn giữ lại và chưa ghi thêm thì gọi gì? **`flip()`** để thành `position=0, limit=3`.
6. Parser đã xử lý 7 byte trong 10 byte hợp lệ, còn 3 byte chưa đủ một bản ghi. Nên dùng gì trước lần nạp tiếp? **`compact()`**, không phải `rewind()`.
7. `reset()` có xóa mark không? **Không.** Nhưng `clear()`, `flip()`, `rewind()`, `compact()` có.
8. `compact()` có đảm bảo ghi số 0 vào những ô nhớ trống không? **Không.** Nội dung ngoài vùng payload cần được coi là không có ý nghĩa.

## 11. Tài liệu chính thức

- [Java SE 17 — `Buffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `capacity`, `mark`, `reset`, `rewind`, `clear`, `flip` và bất biến của buffer.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `compact`, thao tác `get/put`, các view và các giới hạn read-only.
- [Java SE 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): đọc/ghi buffer qua channel.
- [Java SE 17 — `InvalidMarkException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/InvalidMarkException.html): lỗi khi `reset()` không có mark hợp lệ.
