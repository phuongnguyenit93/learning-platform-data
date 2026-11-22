# Capacity, position, limit và mark trong Java NIO Buffer

## 1. Vì sao Buffer cần bốn thông số trạng thái?

Trong Java NIO, một **buffer** là vùng lưu trữ dữ liệu có kích thước xác định, đồng thời duy trì trạng thái để đọc và ghi tuần tự. Những trạng thái cơ bản được khai báo trong `java.nio.Buffer` và xuất hiện ở các lớp cụ thể như `ByteBuffer`, `CharBuffer`, `IntBuffer`:

- **capacity**: sức chứa tối đa của buffer, cố định trong suốt vòng đời buffer đó.
- **position**: chỉ số phần tử kế tiếp sẽ được thao tác khi **đọc/ghi tương đối** (*relative*).
- **limit**: ranh giới trên, độc quyền, của các phần tử hiện được phép thao tác.
- **mark**: vị trí được đánh dấu tùy chọn để có thể quay lại bằng `reset()`.

Điểm khó của Buffer là **cùng một vùng nhớ được sử dụng trong nhiều giai đoạn**. Trong giai đoạn ghi, `position` thường biểu thị nơi ghi phần tử kế tiếp. Trong giai đoạn đọc, `position` thường biểu thị nơi đọc phần tử kế tiếp. Vì vậy, muốn đọc dữ liệu vừa ghi, chương trình phải thiết lập lại `position` và `limit` thích hợp, thường bằng `flip()`.

Ví dụ với `ByteBuffer.allocate(8)`: có chỗ chứa 8 byte, chỉ số hợp lệ của vùng lưu trữ là 0–7. Tuy nhiên, `limit` có thể nhỏ hơn 8, và lúc đó không phải toàn bộ 8 vị trí đều thuộc vùng được phép đọc/ghi theo trạng thái hiện tại.

## 2. Bất biến cốt lõi của Buffer

Tại mọi thời điểm, một Buffer hợp lệ phải thỏa mãn:

\[
0 \leq position \leq limit \leq capacity
\]

Nếu `mark` đã được đặt, nó phải thỏa mãn:

\[
0 \leq mark \leq position
\]

`mark` **có thể không tồn tại**; lúc này không được coi nó là một số mặc định như 0. Trạng thái “không có mark” khiến `reset()` ném `InvalidMarkException`.

Hãy xét một buffer có `capacity = 8`, `position = 3`, `limit = 6`:

```text
Chỉ số:       0   1   2   3   4   5   6   7
Vùng nhớ:    [ ] [ ] [ ] [ ] [ ] [ ] [ ] [ ]
                          ^
                       position = 3
                                       ^
                                    limit = 6
                                               ^
                                            capacity = 8

Vùng có thể thao tác tương đối từ position: [3, 6)
Số phần tử còn lại: limit - position = 3
```

Trong hình, `limit = 6` là **ranh giới**, không phải chỉ số phần tử được phép thao tác. Khi `position == limit`, đã hết phần tử cho thao tác tương đối.

| Trạng thái | Lấy bằng | Ý nghĩa |
| --- | --- | --- |
| Capacity | `buffer.capacity()` | Tổng số phần tử buffer chứa được |
| Position | `buffer.position()` | Chỉ số cho lần thao tác tương đối tiếp theo |
| Limit | `buffer.limit()` | Ranh giới trên, không bao gồm vị trí này |
| Mark | `buffer.mark()` / `buffer.reset()` | Lưu rồi khôi phục position; không có getter `mark()` trả về một số |
| Remaining | `buffer.remaining()` | `limit() - position()` |
| Has remaining | `buffer.hasRemaining()` | `position() < limit()` |

**Đơn vị là phần tử của loại Buffer**, không nhất thiết là byte. `ByteBuffer` có các vị trí theo byte; `CharBuffer` theo `char`; `IntBuffer` theo `int`. Khi tạo view buffer, cần hiểu đơn vị vị trí và quan hệ với vùng lưu trữ nền.

## 3. Trạng thái khởi tạo: `allocate`, `wrap`

Ví dụ:

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
```

Ngay sau khi tạo:

```text
capacity = 8
position = 0
limit    = 8
mark     = undefined
remaining = 8
```

Đây là trạng thái **sẵn sàng ghi tối đa 8 byte** bằng các thao tác tương đối như `put(byte)`. Các byte mới ghi làm `position` tăng dần.

Với `ByteBuffer.wrap(byte[])`, buffer được tạo dựa trên một mảng có sẵn. Thông thường `position = 0`, `limit = capacity = array.length`. **Dữ liệu đã có trong mảng không có nghĩa phải gọi `flip()` trước khi đọc**: `wrap` đã thiết lập trạng thái cho phép bắt đầu đọc từ phần tử đầu tiên.

Ví dụ:

```java
ByteBuffer wrapped = ByteBuffer.wrap(new byte[] {10, 20, 30});
System.out.println(wrapped.get()); // 10
```

Lưu ý: phiên bản `wrap(array, offset, length)` có trạng thái khởi tạo khác: `position = offset`, `limit = offset + length`, `capacity = array.length`. `offset` không làm chỉ số buffer trở thành chỉ số bắt đầu từ 0 của một đoạn cắt mới.

## 4. `position`: vị trí kế tiếp và chuyển động khi đọc/ghi

Các thao tác **tương đối** (*relative*) dùng vị trí hiện tại:

```java
ByteBuffer b = ByteBuffer.allocate(5);
b.put((byte) 11);         // ghi tại index 0, position thành 1
b.put((byte) 22);         // ghi tại index 1, position thành 2
b.put((byte) 33);         // ghi tại index 2, position thành 3
```

Ngược lại, thao tác **tuyệt đối** (*absolute*) chỉ định index cụ thể, không di chuyển `position`:

```java
b.put(0, (byte) 99);      // thay byte index 0, position vẫn là 3
byte first = b.get(0);    // đọc byte index 0, position vẫn là 3
```

Hai đoạn mã trên minh họa chung một biến `b` và không phải chương trình đầy đủ. Khi áp dụng thao tác tuyệt đối, index phải hợp lệ theo `limit` hiện tại; không tự cho phép truy cập qua `limit` chỉ vì `capacity` lớn hơn.

**`position(int newPosition)`** có thể tự đặt lại con trỏ mà không đọc/ghi dữ liệu. `newPosition` phải từ 0 đến `limit`; nếu vượt phạm vi, ném `IllegalArgumentException`. Nếu thay position xuống dưới mark hiện tại, mark bị xóa.

Không nên dùng các lệnh thay đổi position để giả định byte trong vùng lưu trữ được thay đổi. Chúng **chỉ đổi trạng thái**.

## 5. `limit`: ranh giới thao tác

`limit()` trả về chỉ số ranh giới trên **không bao gồm**, tức các chỉ số hợp lệ để đọc/ghi tuyệt đối nằm trong `[0, limit)`. `limit(int newLimit)` có thể giảm hoặc tăng ranh giới, với điều kiện `0 <= newLimit <= capacity`.

Nếu đặt `newLimit` nhỏ hơn `position` hiện tại, position bị kéo xuống bằng limit mới để vẫn giữ bất biến. Nếu mark vượt quá limit mới, mark bị xóa.

Ví dụ:

```java
ByteBuffer b = ByteBuffer.allocate(8);
b.position(5);
b.limit(3);
System.out.println(b.position()); // 3
System.out.println(b.limit());    // 3
```

Sau hai lệnh, không còn phần tử cho thao tác tương đối: `remaining() == 0`.

**Khi `position == limit`:**

- `hasRemaining()` trả về `false`.
- `remaining()` trả về 0.
- `get()` tương đối sẽ ném `BufferUnderflowException`.
- `put(byte)` tương đối trên buffer có thể ghi sẽ ném `BufferOverflowException`.
- Một buffer chỉ đọc sẽ ném `ReadOnlyBufferException` khi gọi thao tác ghi.

Phân biệt `capacity` và `limit` giúp tránh lỗi xử lý cả vùng lưu trữ chưa chứa dữ liệu mới hoặc ghi vượt ranh giới của giai đoạn hiện tại.

## 6. `mark` và `reset`: ghi nhớ một vị trí, không sao lưu dữ liệu

`mark()` lưu **position hiện tại** làm mark. `reset()` đặt lại position bằng mark đã lưu; nó **không đổi nội dung**, không tự đặt lại limit và không xóa mark sau khi reset thành công.

Ví dụ tuần tự:

```java
ByteBuffer b = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});

System.out.println(b.get());   // 10; position = 1
b.mark();                       // mark = 1
System.out.println(b.get());   // 20; position = 2
System.out.println(b.get());   // 30; position = 3
b.reset();                      // position quay về 1
System.out.println(b.get());   // 20 lần nữa; position = 2
```

Ở đây dữ liệu `20` không được sao chép; chương trình chỉ đọc lại cùng vị trí.

`mark` sẽ không còn hợp lệ khi:

- Gọi `clear()`, `flip()` hoặc `rewind()`.
- Gọi `compact()` trên các buffer có hỗ trợ phương thức này.
- Đặt `position` xuống **thấp hơn mark**.
- Đặt `limit` xuống **thấp hơn mark**.

Gọi `reset()` khi chưa có mark hoặc mark đã bị hủy sẽ ném `java.nio.InvalidMarkException`. Đây là ngoại lệ unchecked, không phải `IOException`.

**Mark không phải lịch sử nhiều cấp**: buffer giữ nhiều nhất một mark. Gọi `mark()` lần nữa sẽ thay mark trước đó bằng vị trí hiện tại.

## 7. Bốn thao tác đổi pha: `flip`, `clear`, `rewind`, `compact`

Cần hiểu mục đích từng thao tác để chuyển giữa ghi và đọc trên **cùng một buffer**.

| Thao tác | Position sau thao tác | Limit sau thao tác | Mark | Nội dung dữ liệu |
| --- | --- | --- | --- | --- |
| `flip()` | 0 | position cũ | Bỏ | Không tự sửa byte |
| `clear()` | 0 | capacity | Bỏ | **Không xóa byte** |
| `rewind()` | 0 | Giữ nguyên limit | Bỏ | Không tự sửa byte |
| `compact()` | Số phần tử còn lại trước compact | capacity | Bỏ | **Sao chép** phần chưa đọc về đầu |

### 7.1. `flip()`: từ ghi sang đọc

Trong giai đoạn ghi, position đi sau dữ liệu đã ghi. `flip()` thực hiện chính xác:

```text
limit = oldPosition
position = 0
mark = undefined
```

Ví dụ `capacity = 8`, ghi 3 byte:

```text
Sau put(10), put(20), put(30):
[10][20][30][  ][  ][  ][  ][  ]
             ^
         position = 3
                             limit = 8

Sau flip():
[10][20][30][  ][  ][  ][  ][  ]
 ^
 position = 0
             ^
         limit = 3
```

Bây giờ chỉ ba byte đã ghi thuộc phần dữ liệu đọc qua thao tác tương đối. **`flip` không đảo thứ tự byte** và không “biến” byte thành dạng khác; nó chỉ thay đổi ranh giới.

Nếu gọi `flip()` một lần nữa ngay sau đó, limit trở thành 0 và buffer trông như không có dữ liệu để đọc. Không gọi `flip` lặp lại nếu chưa có bước ghi mới cần chuyển pha.

### 7.2. `clear()`: quay về trạng thái sẵn sàng ghi từ đầu

`clear()` thực hiện:

```text
position = 0
limit = capacity
mark = undefined
```

**`clear()` không xóa vùng lưu trữ.** Byte cũ vẫn có thể nằm trong backing array/direct memory cho đến khi bị ghi đè, nhưng theo logic buffer dữ liệu đó đã được bỏ qua để bắt đầu chu kỳ ghi mới. Đừng dùng `clear()` để xóa thông tin nhạy cảm.

Khi dữ liệu cũ **đã đọc hết và không cần giữ**, dùng `clear()` để tái sử dụng vùng ghi.

### 7.3. `rewind()`: đọc lại từ đầu trong limit hiện tại

`rewind()` đặt position về 0, **giữ limit như cũ**, đồng thời bỏ mark. Nó phù hợp khi cần đọc lại cùng đoạn dữ liệu đã được giới hạn.

Ví dụ sau `flip()` có `limit = 3`, đọc hết ba byte rồi `rewind()`: `position` trở về 0 và `limit` vẫn 3; có thể đọc lại ba byte. Nó khác `clear()` vì `clear` nâng limit lên toàn bộ capacity.

### 7.4. `compact()`: giữ phần chưa đọc khi còn cần ghi thêm

Giả sử buffer đang ở **read mode**:

```text
capacity = 8, position = 2, limit = 5

[10][20][30][40][50][ ?][ ?][ ?]
         ^
      position = 2
                     ^
                  limit = 5
```

Ba byte **chưa đọc** nằm tại các offset 2, 3, 4. `compact()` sao chép chúng về đầu:

```text
Sau compact():
[30][40][50][ ?][ ?][ ?][ ?][ ?]
             ^
          position = 3
                             ^
                          limit = 8
```

Sau đó tiếp tục `put` các byte mới, rồi `flip()` để đọc cả phần còn lại lẫn dữ liệu mới.

Công thức của `compact()`:

\[
newPosition = oldLimit - oldPosition
\]

`newLimit = capacity` và mark bị xóa. **Không được dựa vào giá trị các ô khác ngoài phần được chuyển về đầu**; những vị trí ấy sẽ được xem là vùng để ghi tiếp. `compact()` không có cùng tác dụng với `clear()` vì nó **bảo toàn các phần tử chưa đọc**.

## 8. Ví dụ Java 17+ chạy độc lập: quan sát toàn bộ trạng thái

Chương trình sau minh họa cả bốn trạng thái và kiểm tra `mark`, `remaining`, `flip`, `rewind`, `clear`.

**Tệp `BufferStateDemo.java`:**

```java
import java.nio.ByteBuffer;
import java.nio.InvalidMarkException;

public class BufferStateDemo {
    private static void show(String label, ByteBuffer b) {
        System.out.printf(
            "%s: cap=%d, pos=%d, lim=%d, remaining=%d%n",
            label, b.capacity(), b.position(), b.limit(), b.remaining());
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        show("Moi tao", b);

        b.put((byte) 10);
        b.put((byte) 20);
        b.put((byte) 30);
        b.put((byte) 40);
        show("Sau 4 put", b);

        b.flip();
        show("Sau flip", b);

        System.out.println("Doc dau: " + b.get());
        b.mark();
        System.out.println("Doc tiep: " + b.get());
        System.out.println("Doc nua: " + b.get());
        show("Truoc reset", b);

        b.reset();
        show("Sau reset", b);
        System.out.println("Doc lai: " + b.get());

        b.rewind();
        show("Sau rewind", b);

        try {
            b.reset();
            System.out.println("Mark van ton tai");
        } catch (InvalidMarkException ex) {
            System.out.println("Mark da bi huy");
        }

        b.clear();
        show("Sau clear", b);
        System.out.println("Byte cu tai 0: " + b.get(0));
        show("Sau get tuyet doi", b);
    }
}
```

Biên dịch, chạy:

```bash
javac BufferStateDemo.java
java BufferStateDemo
```

**Stdout chính xác:**

```text
Moi tao: cap=8, pos=0, lim=8, remaining=8
Sau 4 put: cap=8, pos=4, lim=8, remaining=4
Sau flip: cap=8, pos=0, lim=4, remaining=4
Doc dau: 10
Doc tiep: 20
Doc nua: 30
Truoc reset: cap=8, pos=3, lim=4, remaining=1
Sau reset: cap=8, pos=1, lim=4, remaining=3
Doc lai: 20
Sau rewind: cap=8, pos=0, lim=4, remaining=4
Mark da bi huy
Sau clear: cap=8, pos=0, lim=8, remaining=8
Byte cu tai 0: 10
Sau get tuyet doi: cap=8, pos=0, lim=8, remaining=8
```

**Phân tích quan trọng:**

1. Sau bốn `put`, position là 4 dù capacity là 8.
2. `flip` biến position cũ 4 thành limit mới 4, đưa position về 0.
3. `mark()` ở position 1; sau hai lần đọc đến position 3, `reset()` quay về 1, rồi đọc lại `20`.
4. `rewind()` đưa position về 0, giữ limit 4 nhưng **xóa mark**; `reset()` sau đó ném `InvalidMarkException`.
5. `clear()` đưa limit lên 8 nhưng **không xóa byte cũ**: `get(0)` vẫn đọc được 10 trong ví dụ. `get(0)` là phép đọc tuyệt đối nên position giữ ở 0. Điều này không có nghĩa dữ liệu cũ còn hợp lệ về mặt nghiệp vụ sau khi clear.

## 9. Ví dụ Java 17+: `compact` và dữ liệu đọc dở

Một sai sót phổ biến khi xử lý dữ liệu từ kênh I/O là nhận được một phần thông điệp, chỉ đọc một số byte rồi cần giữ phần chưa đọc cho lượt nhận tiếp theo. Nếu gọi `clear` ngay, chương trình có thể làm mất phần chưa xử lý khi nó bị ghi đè. `compact` giải quyết trường hợp này.

**Tệp `BufferCompactDemo.java`:**

```java
import java.nio.ByteBuffer;

public class BufferCompactDemo {
    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(6);

        b.put(new byte[] {10, 20, 30, 40, 50});
        System.out.println("Sau ghi: pos=" + b.position()
                + ", lim=" + b.limit());

        b.flip();
        System.out.println("Da xu ly: " + b.get() + ", " + b.get());
        System.out.println("Chua xu ly: " + b.remaining());

        b.compact();
        System.out.println("Sau compact: pos=" + b.position()
                + ", lim=" + b.limit());

        b.put((byte) 60);
        b.put((byte) 70);
        b.flip();

        System.out.print("Du lieu con lai:");
        while (b.hasRemaining()) {
            System.out.print(" " + b.get());
        }
        System.out.println();
    }
}
```

Chạy:

```bash
javac BufferCompactDemo.java
java BufferCompactDemo
```

**Stdout chính xác:**

```text
Sau ghi: pos=5, lim=6
Da xu ly: 10, 20
Chua xu ly: 3
Sau compact: pos=3, lim=6
Du lieu con lai: 30 40 50 60 70
```

`compact()` giữ ba byte `30 40 50` và chuyển chúng xuống đầu buffer. Position trở thành 3, có chỗ cho ba byte mới. Ghi thêm `60`, `70` đưa position lên 5; `flip()` thiết lập phần đọc là đúng năm byte `30 40 50 60 70`.

Lưu ý `compact()` trên buffer chỉ đọc sẽ ném `ReadOnlyBufferException`. Nếu phần dữ liệu chưa đọc gần bằng capacity, lần ghi mới vẫn có thể thiếu chỗ; chương trình cần xử lý tăng kích thước, giới hạn bản ghi hoặc chính sách nhận dữ liệu phù hợp.

## 10. Mark bị hủy chính xác khi nào?

Xét `ByteBuffer.allocate(10)`, ban đầu `position=0`, `limit=10`. Lần lượt:

```java
ByteBuffer b = ByteBuffer.allocate(10);
b.position(4);
b.mark();       // mark = 4

b.position(6);  // mark 4 vẫn hợp lệ
b.reset();      // trở về position 4

b.position(3);  // position < mark 4: mark bị xóa
// b.reset();    // sẽ ném InvalidMarkException
```

Ở một chuỗi thao tác khác:

```java
ByteBuffer b = ByteBuffer.allocate(10);
b.position(6).mark(); // mark 6
b.limit(5);           // position bị kéo xuống 5; mark 6 bị xóa
// b.reset();         // sẽ ném InvalidMarkException
```

Hai ví dụ này độc lập. Không nên hiểu `mark` là “điểm khôi phục chắc chắn mãi mãi”; nó chỉ tồn tại trong phạm vi trạng thái cho phép của buffer.

Khi cần nhiều điểm phục hồi, hoặc cần khôi phục sau những thao tác làm mất mark, ứng dụng có thể **lưu các giá trị position vào biến kiểu int** rồi gọi lại `position(savedPosition)` sau khi kiểm tra `savedPosition <= limit()`. Cách này không đồng nghĩa với `mark/reset` và vẫn phải bảo đảm dữ liệu/limit còn thích hợp.

## 11. Buffer đầy, Buffer rỗng và những ngoại lệ cần phân biệt

**Buffer đầy theo giai đoạn ghi** nghĩa là `position == limit` và không còn chỗ `put` tương đối. **Buffer đã đọc hết** cũng có `position == limit`, nhưng ý nghĩa nghiệp vụ khác. Trạng thái số học giống nhau; chu kỳ xử lý quyết định bước tiếp theo.

| Tình huống | Kết quả thường gặp |
| --- | --- |
| `get()` khi `position == limit` | `BufferUnderflowException` |
| `put(byte)` khi `position == limit` trên buffer có thể ghi | `BufferOverflowException` |
| `get(-1)` hoặc `get(index >= limit)` | `IndexOutOfBoundsException` |
| `position(-1)` hoặc `position(limit + 1)` | `IllegalArgumentException` |
| `limit(capacity + 1)` | `IllegalArgumentException` |
| `reset()` khi không có mark | `InvalidMarkException` |
| Ghi vào buffer chỉ đọc | `ReadOnlyBufferException` |

`remaining()` và `hasRemaining()` giúp tránh nhiều trường hợp đọc/ghi quá limit:

```java
while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Xử lý value.
}
```

Đây là đoạn minh họa; để biên dịch độc lập phải có biến `buffer` kiểu phù hợp và định nghĩa việc xử lý. Không được suy ra rằng một vòng lặp như vậy tự hiểu ranh giới thông điệp hay giao thức. Nó chỉ đọc đến `limit` hiện tại.

Trong đọc/ghi với `FileChannel`, lượng byte xử lý có thể nhỏ hơn `remaining()` mong muốn trong một lần gọi; nên viết vòng lặp đúng theo hợp đồng API kênh, xử lý EOF và trường hợp tiến độ bằng 0 khi áp dụng. `flip`, `compact`, `clear` chỉ quản lý **trạng thái buffer**; chúng không tự đọc dữ liệu từ hệ thống tệp hoặc gửi byte ra mạng.

## 12. Ứng dụng vào chu trình NIO đọc rồi xử lý dữ liệu

Một chu trình thông dụng khi đọc từ nguồn byte vào `ByteBuffer`:

```text
Buffer ban đầu:        position=0, limit=capacity
       |
       v
Nguồn ghi vào Buffer:  position tăng theo byte nhận được
       |
       v
flip():                limit=oldPosition, position=0
       |
       v
Xử lý dữ liệu:         đọc các byte, position tăng
       |
       +-- Đã xử lý hết mọi byte:
       |        clear() --> chuẩn bị ghi lượt mới
       |
       +-- Còn byte chưa xử lý:
                compact() --> giữ phần dư, chuẩn bị ghi tiếp
```

Chọn `clear` hay `compact` phụ thuộc việc **còn cần giữ các byte từ position đến limit hay không**. Ví dụ khi nhận từng mảnh một thông điệp có độ dài biến đổi, parser có thể chưa đủ dữ liệu để giải mã một record; `compact` giữ phần chưa đủ để nhận tiếp.

Đối với text UTF-8, ký tự có thể bị chia giữa hai lần nhận. Không nên ép mỗi chunk bytes thành `String` độc lập rồi mất dữ liệu ký tự dở; phải dùng decoder xử lý trạng thái hoặc cơ chế gom byte theo giao thức. Đây là ứng dụng trực tiếp của `position`, `limit` và `compact`.

Khi **ghi dữ liệu từ ứng dụng vào kênh**, quy trình thường đi ngược lại: `put` để chuẩn bị dữ liệu → `flip` để kênh lấy byte → lặp `write` đến khi buffer không còn remaining → `clear` hoặc `compact` phù hợp với tình trạng ghi dở. Điều quan trọng là theo dõi rõ buffer đang ở pha ghi vào buffer hay pha đọc ra khỏi buffer.

## 13. `slice`, `duplicate`, `asReadOnlyBuffer` và trạng thái độc lập

Một `ByteBuffer` có thể tạo view:

- `duplicate()` tạo buffer chia sẻ cùng nội dung, nhưng giữ **position, limit và mark độc lập** với buffer gốc; trạng thái ban đầu sao chép giá trị hiện có.
- `slice()` tạo view của vùng từ position hiện tại đến limit hiện tại. View mới có `position=0`, `limit=capacity=remaining` của buffer gốc tại thời điểm tạo và chia sẻ dữ liệu vùng ấy.
- `asReadOnlyBuffer()` tạo view chỉ đọc, chia sẻ nội dung với trạng thái position/limit/mark riêng. Mọi thao tác ghi qua view này bị từ chối.

**Chia sẻ nội dung không có nghĩa chia sẻ position.** Dịch position ở view không trực tiếp dịch position ở buffer gốc; tuy nhiên ghi dữ liệu qua một view có thể thay đổi byte mà view khác nhìn thấy. Các view cũng không tự bảo đảm an toàn luồng.

Ví dụ nhỏ:

```java
ByteBuffer base = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
base.position(1);
base.limit(3);

ByteBuffer view = base.slice();
System.out.println(view.capacity()); // 2
System.out.println(view.position()); // 0
System.out.println(view.limit());    // 2
System.out.println(view.get());      // 20
System.out.println(base.position()); // 1 (không đổi)
```

View có hai byte tương ứng `20, 30`, có chỉ số riêng `0,1`. Với buffer được cấp phát direct hoặc memory-mapped, chuyện sở hữu tài nguyên và vòng đời backing storage cũng cần được thiết kế phù hợp; các trục này độc lập với các bất biến capacity/position/limit/mark.

## 14. Lỗi phổ biến và cách sửa

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Ghi bằng `put` rồi đọc ngay bằng `get` mà quên `flip()` | Position đang nằm sau dữ liệu vừa ghi | `flip()` trước pha đọc |
| Tưởng `flip()` đảo thứ tự phần tử | Flip chỉ thay trạng thái | Theo dõi limit/position đúng công thức |
| Dùng `clear()` để xóa bí mật | Clear không ghi đè nội dung | Có phương án xóa/ghi đè dữ liệu phù hợp và quản lý vòng đời bộ nhớ |
| Dùng `clear()` khi còn bytes chưa xử lý | Phần dư dễ bị ghi đè | `compact()` khi cần giữ remaining |
| Dùng `rewind()` để bắt đầu pha ghi đầy capacity | Rewind giữ limit cũ | Nếu bỏ dữ liệu cũ và muốn ghi lại toàn bộ, dùng `clear()` |
| Gọi `reset()` sau `flip/clear/rewind/compact` | Mark đã bị loại bỏ | Đặt `mark()` lại ở pha thích hợp |
| Nhầm capacity với số byte đã ghi | Có thể đọc cả vùng chưa hợp lệ | Dùng `flip` để đặt limit theo lượng đã ghi |
| Gọi `get()` khi `remaining() == 0` | Underflow | Kiểm tra `hasRemaining()`, hoặc xử lý ngoại lệ có chủ đích |
| Gọi `put()` khi `position == limit` | Overflow | Kiểm tra không gian, chuyển pha hoặc dùng buffer lớn hơn |
| Nghĩ `get(index)` làm position tăng | Đây là truy cập tuyệt đối | Dùng `get()` nếu muốn tăng position |
| Nhầm vị trí trong `IntBuffer` là byte offset | Vị trí của IntBuffer theo phần tử int | Nhớ mỗi loại buffer có đơn vị phần tử riêng |
| Dùng chung buffer thay đổi position giữa nhiều luồng | Trạng thái có thể bị xen kẽ | Đồng bộ hoặc phân chia quyền sở hữu buffer rõ ràng |

## 15. Bài tập kiểm tra trạng thái

Với buffer mới:

```java
ByteBuffer b = ByteBuffer.allocate(6);
b.put((byte) 1);
b.put((byte) 2);
b.put((byte) 3);
b.flip();
b.get();
b.mark();
b.get();
b.compact();
```

**Hãy dự đoán position, limit, capacity sau mỗi bước quan trọng.**

Đáp án:

1. Mới tạo: `capacity=6`, `position=0`, `limit=6`.
2. Sau ba `put`: `position=3`, `limit=6`, dữ liệu đã ghi `1,2,3`.
3. Sau `flip`: `position=0`, `limit=3`.
4. Sau `get()` thứ nhất: `position=1`, lấy byte `1`.
5. `mark()` đặt mark tại **1**; không thay đổi position.
6. Sau `get()` thứ hai: `position=2`, lấy byte `2`.
7. Trước `compact`, `remaining = 3 - 2 = 1`, byte chưa đọc là **3**.
8. Sau `compact`: byte `3` được chuyển về index 0; `position=1`, `limit=6`, `capacity=6`, **mark không còn**. Buffer sẵn sàng ghi tiếp từ offset 1.

Nếu sau bước cuối gọi `reset()`, chương trình sẽ ném `InvalidMarkException` vì `compact()` loại bỏ mark.

## 16. Ghi nhớ

**Bộ bốn trạng thái luôn tuân theo `0 <= position <= limit <= capacity`**, còn mark (nếu tồn tại) phải nằm trong `[0, position]`. `position` là nơi thao tác tương đối tiếp theo, `limit` là ranh giới trên độc quyền, `capacity` là sức chứa cố định, `mark` dùng để nhớ và phục hồi position.

Khi viết logic I/O, hãy luôn biết buffer ở giai đoạn nào:

- **Ghi xong → đọc:** `flip()`.
- **Đọc xong và bỏ dữ liệu cũ → ghi lại:** `clear()`.
- **Cần đọc lại dữ liệu trong limit:** `rewind()`.
- **Chưa đọc hết và cần nhận/ghi thêm:** `compact()`.
- **Chỉ muốn trở về một vị trí đã đánh dấu:** `mark()` rồi `reset()`, miễn mark chưa bị hủy.

Tài liệu tham khảo: Java SE 17 API — `java.nio.Buffer`, `java.nio.ByteBuffer`, `java.nio.InvalidMarkException` và `java.nio.channels.FileChannel`.
