# Ý nghĩa của kết quả `0` và EOF `-1` khi đọc NIO Channel

## 1. Câu hỏi cốt lõi

Khi gọi `int n = channel.read(buffer)` trong Java NIO, giá trị `n` không phải nội dung byte vừa đọc. Nó là **số byte đã chuyển từ channel vào `ByteBuffer` trong đúng lần gọi đó**, hoặc dấu hiệu kết thúc luồng vào (end-of-stream, thường gọi EOF). Theo hợp đồng `ReadableByteChannel.read(ByteBuffer)`:

- **`n > 0`**: đọc thành công đúng `n` byte; chỉ từng ấy byte vừa được thêm vào vùng còn lại của buffer.
- **`n == 0`**: lần gọi không chuyển được byte nào. Có thể vì buffer không còn chỗ (`remaining() == 0`), vì channel không có byte sẵn ngay lúc đó (đặc biệt ở chế độ non-blocking), hoặc điều kiện cụ thể khác được API cho phép. **`0` không phải EOF.**
- **`n == -1`**: channel báo đã đến **cuối luồng đọc**. Không có byte mới nào được chuyển trong lần gọi này.
- **Ngoại lệ**: lỗi I/O hoặc trạng thái channel không hợp lệ được báo qua exception, không được “mã hóa” thành `0` hay `-1`.

Bài học thuộc nhóm **Java Core I/O → NIO Channel**. Mục tiêu là đọc chính xác kết quả của `read`, phân biệt file với socket, blocking với non-blocking, và thiết kế vòng lặp không rơi vào mất dữ liệu hoặc busy loop.

## 2. Hợp đồng đầy đủ của `read(ByteBuffer)`

Cho `dst` là `ByteBuffer` nhận dữ liệu. Ngay trước lời gọi:

```text
p = dst.position()
r = dst.remaining() = dst.limit() - dst.position()
```

Channel cố đọc **tối đa `r` byte**. Nếu đọc được `n` byte (`0 <= n <= r`), các byte được ghi bắt đầu tại chỉ số `p`, `dst.position()` tăng thành `p + n`, và `dst.limit()` giữ nguyên. Nếu trả `-1`, lần đọc đã chạm EOF; không có byte mới nào được ghi.

Ví dụ giả định buffer còn 5 vị trí:

```text
Trước read:  position=3, limit=8, remaining=5
read trả 2:  position=5, limit=8, remaining=3
read trả 0:  position=3, limit=8, remaining=5   (nếu xuất phát từ trạng thái đầu)
read trả -1: không có byte mới; chưa chuyển sang một vùng dữ liệu mới
```

Không được suy luận “đọc được ít hơn dung lượng yêu cầu là EOF”. Channel có thể trả `1` byte dù sau đó vẫn còn nhiều dữ liệu. Mỗi lần `read` chỉ báo kết quả *của lần đọc đó*.

| Kết quả từ `read(dst)` | Dữ liệu mới | Ý nghĩa cần hiểu | Hướng xử lý thường gặp |
| --- | --- | --- | --- |
| `1 .. dst.remaining()` trước lời gọi | Có đúng `n` byte | Có tiến triển; chưa khẳng định đã đọc hết | `flip()`, xử lý byte nhận được hoặc tích lũy khung dữ liệu |
| `0` | Không có | Chưa kết luận hết dữ liệu | Kiểm tra `remaining`, trạng thái blocking và cơ chế chờ |
| `-1` | Không có | Đã đến cuối input stream tại thời điểm gọi | Kết thúc việc đọc; xử lý phần dữ liệu đang đệm |
| Ném `IOException` hoặc ngoại lệ liên quan | Không có số byte trả về bình thường | I/O thất bại hoặc channel bị đóng/ngắt | Xử lý lỗi, đóng tài nguyên theo chính sách |

`remaining()` được tính **trước khi gọi** nếu muốn biết độ dài tối đa lần đọc, và **sau khi gọi** để biết số vị trí còn trống. Khi `read` trả `0`, state của buffer không tự chuyển sang chế độ đọc: `flip()` và `clear()` vẫn phải do ứng dụng quyết định.

## 3. `0`: không có tiến triển, nhưng có hai tình huống rất khác nhau

### 3.1. Buffer hết chỗ

Nếu `buffer.remaining() == 0`, không có vị trí nào để channel ghi thêm byte. Một lần đọc với buffer không có chỗ có thể trả `0` ngay cả khi file hoặc socket còn dữ liệu. Phép đọc **không thử được xem sau đó có byte mới hay EOF hay không** theo cách có ý nghĩa cho việc điều khiển luồng.

```java
ByteBuffer dst = ByteBuffer.allocate(4);
dst.position(dst.limit()); // remaining() == 0
int n = channel.read(dst); // thường là 0 vì không có chỗ chứa
```

Đây là đoạn minh họa trong một phương thức có biến `channel`, không phải một chương trình độc lập. Đối với `ReadableByteChannel` cơ bản, kết quả khi yêu cầu 0 byte phụ thuộc quy tắc API và triển khai tại trạng thái cụ thể; **không dựa vào `read(emptyBuffer)` để phát hiện EOF**. Lỗi thường gặp là quên `clear()` hoặc `compact()` trước lượt nhận dữ liệu mới.

### 3.2. Chưa có dữ liệu sẵn trên non-blocking socket

`SocketChannel` ở chế độ non-blocking (`configureBlocking(false)`) có thể trả `0` khi socket đã sẵn sàng sử dụng nhưng **ngay lúc gọi không có byte nào có thể lấy được**. Kết quả này không đồng nghĩa phía bên kia đóng kết nối. Byte tiếp theo có thể đến sau.

```java
int n = socketChannel.read(buffer);

if (n > 0) {
    // Đã nhận n byte.
} else if (n == 0) {
    // Chưa đọc được byte nào ngay lúc này: chờ sự kiện hoặc thời điểm phù hợp.
} else { // -1
    // Input đã kết thúc.
}
```

Đoạn trên là mã minh họa, giả sử `socketChannel` đã mở và `buffer` đã sẵn sàng nhận dữ liệu. Trong ứng dụng dùng `Selector`, khi `0` xuất hiện, thường trả điều khiển về event loop và tiếp tục chờ `OP_READ`, đồng thời điều chỉnh interest ops khi cần. Đừng gọi `read` liên tục trong một `while` rỗng chỉ để đợi byte mới: điều đó dễ làm CPU tăng vọt.

### 3.3. Blocking channel khác non-blocking ra sao?

Hợp đồng `ReadableByteChannel` bảo đảm với channel ở **blocking mode** và `dst.remaining() > 0`, lời gọi sẽ chờ đến khi đọc được ít nhất một byte. Nếu kết thúc trước khi đọc được byte, việc kết thúc luồng sẽ được biểu diễn bằng `-1`; lỗi I/O được báo riêng bằng ngoại lệ.

Đối với `FileChannel`, chế độ non-blocking của `SocketChannel` không áp dụng trực tiếp: file thông thường được đọc theo vị trí của file và có thể nhanh chóng đạt EOF. Nếu buffer đã có chỗ và file còn dữ liệu, số byte đọc được có thể nhỏ hơn yêu cầu; không lấy `0` làm dấu hiệu “file đã hết”.

Lưu ý: nhiều phương thức API, loại channel và hệ thống tệp có khác biệt chi tiết. Luôn dùng hợp đồng của channel thực tế thay vì suy luận từ một demo socket.

## 4. `-1`: dấu hiệu end-of-stream (EOF)

`-1` là một **giá trị sentinel** nằm ngoài miền số byte đã đọc `0 .. remaining()`. Nó cho biết không thể nhận byte tiếp theo do đầu vào đã kết thúc trong lần đọc này.

Với file:

- Nếu file chứa ba byte `ABC`, một lần đọc buffer 2 byte trả `2` (`AB`), lần sau trả `1` (`C`), lần sau nữa trả `-1`.
- Đọc file rỗng bằng buffer còn chỗ thường nhận ngay `-1`.
- Vị trí đọc tệp đã chạm cuối dữ liệu hiện có; không có ý nghĩa “đang đợi có file mới”.
- Nếu một tiến trình khác bổ sung byte vào file đang mở sau đó, khả năng đọc tiếp phụ thuộc thời điểm, vị trí và tính nhất quán của file/provider. Không coi EOF của file đang bị cập nhật đồng thời là sự kiện bất biến của cả thế giới.

Với TCP socket:

- `-1` từ `SocketChannel.read` cho biết **phía nhận của stream đã tới cuối**; thường là peer đóng kênh gửi dữ liệu một cách có trật tự hoặc gọi `shutdownOutput()`.
- TCP hỗ trợ **half-close**: peer có thể ngừng gửi nhưng vẫn còn khả năng nhận dữ liệu. Do đó EOF ở chiều đọc **không khẳng định cả hai chiều kết nối đều đã đóng**.
- Nếu peer reset kết nối hoặc I/O lỗi, Java có thể ném `IOException` thay vì trả `-1`. Đây không phải EOF bình thường.
- Byte đã đến trước tín hiệu kết thúc vẫn phải được xử lý. Ví dụ nếu buffer còn một phần khung ứng dụng chưa hoàn chỉnh, khi gặp `-1` phải quyết định đó là bản tin hợp lệ cuối hay lỗi dữ liệu bị cắt, tùy giao thức.

**Phân biệt:** `0` là “không có byte được truyền trong lượt này”; `-1` là “đã chạm điểm kết thúc input”. Cả hai đều không thêm byte vào buffer, nhưng **dẫn tới hành động hoàn toàn khác nhau**.

## 5. Ví dụ Java 17+ chạy độc lập: `0`, số dương và EOF `-1`

Tạo file `ChannelReadResultDemo.java`. Chương trình sinh file tạm chứa đúng ba byte ASCII `ABC`, mở `FileChannel` đọc, thực hiện một phép đọc vào buffer có sức chứa 0 để minh họa `0`, rồi đọc file qua buffer có sức chứa 2 để thấy kết quả dương và `-1`.

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ChannelReadResultDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("nio-read-result-", ".txt");

        try {
            Files.write(path, "ABC".getBytes(StandardCharsets.US_ASCII));

            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ)) {

                ByteBuffer noSpace = ByteBuffer.allocate(0);
                int zero = channel.read(noSpace);
                System.out.println("Empty buffer: " + zero);
                System.out.println("File position: " + channel.position());

                ByteBuffer buffer = ByteBuffer.allocate(2);
                while (true) {
                    buffer.clear();               // Chuẩn bị nhận byte mới
                    int n = channel.read(buffer);

                    if (n == -1) {
                        System.out.println("Read: -1 (EOF)");
                        break;
                    }
                    if (n == 0) {
                        System.out.println("Read: 0 (no progress)");
                        continue;
                    }

                    buffer.flip();                // Chỉ xử lý n byte vừa đọc
                    byte[] bytes = new byte[n];
                    buffer.get(bytes);
                    String chunk = new String(bytes, StandardCharsets.US_ASCII);
                    System.out.println("Read: " + n + " (" + chunk + ")");
                }
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ChannelReadResultDemo.java
java ChannelReadResultDemo
```

Stdout trên JDK 17+ với file tạm được tạo thành công:

```text
Empty buffer: 0
File position: 0
Read: 2 (AB)
Read: 1 (C)
Read: -1 (EOF)
```

**Diễn giải từng bước:**

1. `ByteBuffer.allocate(0)` có `remaining() == 0`; `FileChannel.read(noSpace)` trả `0` và file position vẫn là `0`. Vì thế `0` ở đây **không thể** được diễn giải thành EOF.
2. `ByteBuffer.allocate(2)` cho phép đọc tối đa 2 byte. `read` đầu tiên lấy `AB`, tăng `buffer.position()` lên 2, đồng thời tiến file position thêm 2.
3. Vòng lặp tiếp theo `clear()` để nhận lượt mới; file chỉ còn `C`, nên `read` trả `1` thay vì `2`. Vẫn chưa phải EOF trong lần đọc đó.
4. Sau khi tiêu thụ `C`, lời gọi tiếp theo với buffer còn chỗ trả `-1`, vòng lặp kết thúc.
5. `flip()` giới hạn phạm vi đọc buffer về đúng số byte mới nhận. Dữ liệu cũ có thể còn trong backing storage; không dùng toàn bộ `buffer.array()` như nội dung hợp lệ.

Vòng `continue` khi `n==0` trong ví dụ này chỉ dùng cho **FileChannel với buffer luôn có sức chứa 2 và đã được `clear()`**; nó không phải chiến lược chờ an toàn cho `SocketChannel` non-blocking. Với socket non-blocking phải dùng `Selector`, callback hoặc cơ chế chờ phù hợp.

## 6. Không đánh đồng kết quả `read` với giá trị byte dữ liệu

Một byte trong file có thể mang giá trị 0 (`0x00`), hoặc `0xFF`. Điều đó **không đồng nghĩa** `read` trả `0` hoặc `-1`.

Ví dụ tệp gồm các byte `[0x00, 0xFF]`:

```java
ByteBuffer buffer = ByteBuffer.allocate(4);
int n = channel.read(buffer);
```

Đây là đoạn minh họa, cần nằm trong phương thức xử lý `IOException` và `channel` đang đọc đúng tệp. Nếu `read` lấy được cả hai byte, nó trả **`2`**. Byte `0x00` không phải “không đọc được”; byte `0xFF` không phải EOF. Giá trị `-1` thuộc kết quả **`int` của phương thức đọc**, không phải byte mà `ByteBuffer` chứa.

Đây cũng là lý do nhiều API Java chọn `int` cho kết quả đọc: chúng cần một sentinel âm bên ngoài số lượng byte hợp lệ. Với `InputStream.read()` (đọc một byte), `0 .. 255` là dữ liệu, còn `-1` mới là EOF; đừng nhầm nó với `ReadableByteChannel.read(ByteBuffer)` trả **số lượng byte**.

## 7. Tại sao `flip()`, `clear()` và `remaining()` ảnh hưởng việc hiểu `0`?

`read(ByteBuffer)` ghi vào **phần còn lại từ `position` tới `limit`**. Do đó luôn kiểm tra trạng thái buffer trước khi phân tích `0`.

```text
Buffer capacity 8:
  position=8, limit=8 => remaining=0 => không có chỗ ghi
  clear()             => position=0, limit=8 => có chỗ ghi
  read() trả 3        => position=3, limit=8
  flip()              => position=0, limit=3 => chỉ 3 byte được đọc
  consume 3 bytes     => position=3, limit=3
  compact()           => position=0, limit=8 => sẵn sàng ghi tiếp
```

- `clear()`: reset để **ghi mới từ đầu**; không xóa storage cũ. Dùng khi buffer không còn byte cần giữ lại.
- `flip()`: chuyển sang **đọc những byte đã được ghi** bằng cách đặt `limit` bằng `position` hiện tại, rồi `position=0`.
- `compact()`: dồn byte **chưa được tiêu thụ** về đầu, chuẩn bị ghi tiếp vào phần trống. Dùng trong giao thức streaming khi khung dữ liệu có thể đến qua nhiều lần `read`.
- `hasRemaining()`: hỏi còn phần tử trong khoảng `position .. limit` hiện tại hay không; không cho biết channel còn byte bên ngoài hay chưa.
- `remaining()==0` sau `flip()` chỉ nói vùng đọc của buffer rỗng; không kết luận luồng nguồn đã EOF.

Sai lầm kinh điển: `read` được `2` byte, rồi gọi `clear()` trước khi xử lý; ứng dụng quên giới hạn 2 byte mới và có thể đọc nhầm phần còn lại trong storage. Ngược lại, quên `clear()`/`compact()` sau khi đọc hết buffer làm lần `channel.read(buffer)` tiếp theo trả `0` dù nguồn vẫn còn byte.

## 8. Vòng lặp file channel đúng và lý do không chờ vô hạn

Khi đọc một file thông thường bằng `FileChannel` vào buffer luôn có `remaining()>0`, mẫu dễ hiểu là:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;

static long drain(FileChannel source) throws IOException {
    ByteBuffer buffer = ByteBuffer.allocate(8192);
    long total = 0;

    while (true) {
        buffer.clear();
        int n = source.read(buffer);

        if (n == -1) {
            return total;
        }
        if (n == 0) {
            // Với FileChannel và buffer còn chỗ, kiểm tra tình huống bất thường
            // hoặc chính sách phù hợp; không hiểu 0 là EOF.
            continue;
        }

        total += n;
        buffer.flip();
        while (buffer.hasRemaining()) {
            byte b = buffer.get();
            // Xử lý byte b; ở đây chỉ minh họa tiêu thụ dữ liệu.
        }
    }
}
```

Đây là **phương thức minh họa**, không phải file Java độc lập; đặt vào một class cùng import. Nó thống kê số byte đọc trong phiên đọc hiện tại và tiêu thụ byte trong buffer, không trả nội dung file. Trong ứng dụng thực tế, đừng giữ `continue` vô điều kiện nếu loại channel có thể liên tục trả `0`: cần cơ chế giới hạn/chờ phù hợp. Hàm gọi có trách nhiệm mở và đóng `FileChannel`; phương thức không tự đóng channel vì không sở hữu tài nguyên ấy.

Một số chi tiết quan trọng:

- `n < buffer.capacity()` **không có nghĩa** là EOF. Cứ lặp tiếp.
- Sau `-1`, dừng vòng `read`. Nếu còn byte đang giữ trong buffer ở logic cấp ứng dụng, phải hoàn tất xử lý hoặc báo lỗi khung dữ liệu không hoàn chỉnh.
- Đừng quên kiểm tra exception như `ClosedChannelException`, `AsynchronousCloseException`, `IOException`; `read` không dùng `0` làm mã báo lỗi.
- Nếu tài nguyên đọc có thể bị thay đổi, các lần đọc và vị trí file cần được điều phối; không suy diễn số lần gọi từ kích thước file đo trước.

## 9. Vòng lặp socket non-blocking: `0` dẫn tới cơ chế chờ, `-1` dẫn tới kết thúc input

Khác với file thông thường, socket kết nối tới luồng dữ liệu đến theo thời gian. Đặt `SocketChannel` ở chế độ non-blocking và đăng ký với `Selector` để tránh đợi bằng cách chiếm CPU.

Sơ đồ logic:

```text
Selector thông báo khả năng đọc
            |
      SocketChannel.read(dst)
         /       |         \
      n > 0     n == 0      n == -1
       |           |           |
  Có byte mới   Chưa có byte   EOF chiều đọc
  parse/tích    vào lúc này    xử lý phần đệm
  lũy dữ liệu   trở về loop    rồi kết thúc đọc
```

Khi `n>0`, đọc dữ liệu vào buffer, `flip()`, phân tích **chỉ những khung hoàn chỉnh**, sau đó `compact()` để giữ phần khung còn dở. Khi `n==0`, đừng xóa dữ liệu chưa xử lý trong buffer hoặc coi kết nối đã bị cắt; chỉ để event loop tiếp tục chờ. Khi `n==-1`, ứng dụng nên kết thúc việc chờ input trên kênh và quyết định cách đóng/half-close dựa vào giao thức.

Minh họa khung xử lý một sự kiện, **không phải một chương trình Java độc lập**:

```java
// socket đang mở, non-blocking; dst ở chế độ sẵn sàng để ghi.
// Phải quản lý chế độ đọc/ghi buffer giữa các callback.
int n = socket.read(dst);

if (n == -1) {
    // Peer đã kết thúc output; xử lý phần dữ liệu ứng dụng còn đệm.
    // Hủy đăng ký đọc / đóng theo quy tắc giao thức.
} else if (n == 0) {
    // Không tiến triển ngay lúc này; trả quyền cho event loop.
} else {
    dst.flip();
    // parseCompleteMessages(dst): chỉ tiêu thụ các thông điệp đủ byte.
    dst.compact();  // Giữ lại mọi byte của thông điệp chưa hoàn chỉnh.
}
```

Nếu `dst` đã đầy mà vẫn còn một thông điệp chưa hoàn chỉnh, `compact()` có thể vẫn để `remaining()==0` sau khi dồn. Lúc này cần **buffer lớn hơn hoặc chính sách giới hạn kích thước frame**, không gọi `read` vô hạn. `Selector` cũng có thể thức dậy nhưng lượt đọc thực tế vẫn trả `0`; readiness không phải lời hứa chắc chắn đọc được byte vào bất cứ thời điểm nào.

**Không xem `read()==0` như “server đã gửi packet rỗng”.** TCP là byte stream; không có một sự kiện read=0 tương đương “thông điệp kích thước 0”. Nếu giao thức ứng dụng có frame dài 0 byte, frame ấy phải được biểu diễn bằng header/độ dài riêng của giao thức.

## 10. Phân biệt `read` và `write`: `write()==0` cũng cần quan tâm

`WritableByteChannel.write(ByteBuffer)` trả số byte **đã lấy từ buffer để gửi/ghi** trong lần gọi, là giá trị từ `0` trở lên. Không dùng `-1` cho EOF ở thao tác `write`.

- `write() > 0`: đã tiêu thụ một phần hoặc toàn bộ byte còn lại trong `src`; `src.position()` tiến lên.
- `write() == 0`: lần đó không ghi được byte. Chẳng hạn `src.remaining()==0`, hoặc non-blocking socket chưa có khả năng ghi thêm ngay lúc đó.
- `write()` trả ít hơn `remaining()` ban đầu: **partial write**, không phải lỗi. Phần chưa ghi còn nằm trong buffer.
- Lỗi ghi, channel đóng hoặc trạng thái không phù hợp được báo bằng ngoại lệ thích hợp.

Với output channel kiểu blocking có tiến triển, mã thường viết:

```java
while (buffer.hasRemaining()) {
    destination.write(buffer);
}
```

Đây là đoạn minh họa. Với non-blocking socket, vòng lặp trên nếu `write` liên tục trả `0` sẽ **busy-spin**. Phải tạm dừng, đăng ký `OP_WRITE` khi còn dữ liệu cần gửi, và tiếp tục lúc socket có khả năng ghi. Không `clear()` khi còn byte chưa gửi, vì như vậy bạn đánh mất trạng thái những byte đang chờ.

## 11. EOF ở nhiều kiểu channel và API liên quan

| API / tình huống | `0` hoặc trường hợp không tiến triển | `-1` | Ghi chú |
| --- | --- | --- | --- |
| `ReadableByteChannel.read(ByteBuffer)` | Có thể `0`; phụ thuộc `remaining`, blocking, trạng thái channel | Cuối input stream | Hợp đồng cơ bản của các channel đọc |
| `FileChannel.read(ByteBuffer)` | Buffer rỗng có thể cho `0` | Vị trí đọc đã ở cuối file lúc gọi | Đọc ngắn vẫn là số dương |
| `SocketChannel.read(ByteBuffer)` non-blocking | Không có byte sẵn ngay lúc gọi có thể cho `0` | Input stream đã kết thúc | Cần event loop/selector |
| `SocketChannel.read(ByteBuffer)` blocking | Với buffer còn chỗ, lời gọi chờ cho tới khi đọc được byte hoặc EOF/lỗi | Input stream kết thúc | Không dùng `0` làm tín hiệu peer đóng |
| `ScatteringByteChannel.read(ByteBuffer[])` | Tổng số byte đọc có thể là `0` | Input stream kết thúc | Trả `long`, không phải `int`; các buffer lần lượt nhận dữ liệu |
| `AsynchronousFileChannel.read(...)` | Kết quả hoàn thành bất đồng bộ có thể `0` nếu không có chỗ hoặc không tiến triển | Đọc từ vị trí tại/cuối file | Nhận kết quả qua `Future<Integer>` hoặc callback, không nhận trực tiếp từ lệnh phát động |
| `WritableByteChannel.write(ByteBuffer)` | `0` = không ghi byte nào lượt này | Không dùng EOF `-1` | Ghi từng phần phải xử lý |
| `InputStream.read(byte[])` | Khi độ dài buffer bằng 0 hoặc theo hợp đồng stream cụ thể | EOF cũng là `-1` | API stream khác channel; xem hợp đồng mỗi overload |

### Với asynchronous channel, đọc khác về thời điểm nhận kết quả

`AsynchronousFileChannel.read(dst, position)` **trả `Future<Integer>`**, còn `read(dst, position, attachment, handler)` chuyển kết quả tới `CompletionHandler`. `0` và `-1` ở đây nằm trong **kết quả hoàn thành của hoạt động I/O**, không phải biến trả về trực tiếp từ việc phát lệnh.

Đối với `AsynchronousByteChannel`, nếu `dst.remaining()==0`, một lượt đọc bất đồng bộ có thể hoàn thành ngay với `0` mà không khởi động I/O thật. Nếu nhận `-1`, input đã hết. Với mọi asynchronous API, không được chỉnh trạng thái `ByteBuffer` tùy tiện trước khi tác vụ sử dụng buffer hoàn tất.

## 12. Những lỗi lập trình thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `if (n <= 0) break;` | Gộp `0` với `-1`; với non-blocking socket làm mất cơ hội đọc dữ liệu sẽ đến sau | Tách `n==-1`, `n==0`, `n>0` |
| `while (channel.read(buf) != -1) {}` | Không có xử lý buffer; nếu đầy sẽ tiếp tục trả `0` và lặp vô tận | `flip()`, tiêu thụ, `clear()`/`compact()` đúng lúc |
| `if (n < buf.capacity()) break;` | Đọc ngắn không bằng EOF | Chỉ dừng theo EOF, protocol hoặc điều kiện nghiệp vụ |
| `while (socket.read(buf)==0) {}` | Busy loop trên non-blocking I/O | Trả điều khiển về `Selector` hoặc scheduler |
| Nhận `0` thì đóng socket | `0` không báo đóng input | Tiếp tục theo dõi read readiness |
| Nhận `-1` rồi bỏ dữ liệu đã đọc ở lượt trước | Có thể còn partial frame trong buffer | Hoàn tất hoặc báo lỗi frame chưa đủ theo protocol |
| Đọc vào buffer đã đầy và kết luận file đã hết | Không còn chỗ nhận byte | Dùng `flip()`, tiêu thụ, `clear()` hoặc `compact()` |
| Lấy `buffer.array()` làm toàn bộ kết quả đọc | Mảng chứa cả byte cũ/không hợp lệ | Dùng `n`, `remaining()` sau `flip()` và offset thích hợp |
| Nhầm `0x00` là read `0`, `0xFF` là EOF | Một bên là giá trị byte, bên kia là lượng byte/sentinel | Đọc dữ liệu trong buffer; kiểm tra số trả về riêng |
| `write()==0` có nghĩa receiver đóng | Không tiến triển của write không phải bằng chứng kết nối chết | Đợi `OP_WRITE` hoặc xử lý exception |
| Bắt `IOException` và trả `-1` từ wrapper | Che giấu lỗi I/O thành EOF hợp lệ | Giữ loại lỗi hoặc chính sách retry/timeout minh bạch |

## 13. Tình huống thực tế

### A. Đọc toàn bộ file bất kỳ kích thước

Dùng buffer kích thước cố định, `read` nhiều lần, cộng số byte `n>0`, dừng khi `-1`. Không cần biết tổng dung lượng file trước khi đọc. Mỗi lần dùng `flip()` để xử lý dữ liệu mới nhận, `clear()` khi đã tiêu thụ hết.

### B. Giao thức mạng có độ dài thông điệp xác định

Giả sử header 4 byte mã hóa độ dài body. Một lần `read` có thể trả `1`, `2` hoặc `3` byte của header. Bất kỳ giá trị dương nào cũng là tiến triển; chưa đủ 4 byte thì phải tích lũy. Khi `read` trả `0`, chờ dữ liệu mới, không phát thông điệp sai; khi trả `-1` trước khi đủ header/body, báo frame bị cắt theo quy tắc ứng dụng.

### C. Đọc socket rồi ghi ra file

`SocketChannel.read` trả `0` trong non-blocking mode: để `Selector` chờ đợt tiếp theo. Khi `n>0`, `flip()` buffer và ghi đến khi toàn bộ dữ liệu được tiêu thụ (hoặc đặt phần còn lại vào hàng đợi output). Khi nhận `-1`, hoàn thành/đóng input và xử lý output còn tồn; không xóa dữ liệu chưa ghi chỉ vì nguồn đã EOF.

## 14. Câu hỏi tự kiểm tra

**1.** `channel.read(buffer)` trả `0`; có chắc đang ở cuối tệp?  
**Đáp án:** Không. Phải xem `buffer.remaining()`, loại channel, mode và trạng thái I/O. `0` chỉ cho biết lần gọi không đọc byte nào.

**2.** File có 5 byte, buffer dung lượng 8, lần đầu trả `5`; đã EOF chưa?  
**Đáp án:** Chưa thể kết luận từ riêng `5`. Một lần đọc tiếp với buffer có chỗ mới xác định EOF qua `-1` nếu không còn byte.

**3.** File có hai byte giá trị `0x00` và `0xFF`. `read(buffer)` lấy cả hai thì trả gì?  
**Đáp án:** `2`, vì kết quả là số byte, không phải nội dung byte.

**4.** `SocketChannel` non-blocking trả `0`; có nên gọi lại `read` hàng triệu lần ngay lập tức?  
**Đáp án:** Không. Trả điều khiển cho `Selector`/event loop hoặc cơ chế chờ phù hợp; kiểm soát buffer và đăng ký `OP_READ`.

**5.** `read` trả `-1` nhưng ứng dụng còn giữ một nửa bản tin trong buffer; có thể bỏ qua phần ấy không?  
**Đáp án:** Tùy đặc tả giao thức. Nếu một frame bắt buộc đầy đủ, phải báo truncation/protocol error; nếu nội dung cho phép kết thúc ở đó, xử lý phần còn lại theo luật nghiệp vụ.

**6.** Tại sao vòng lặp `while (channel.read(buffer) != -1)` nguy hiểm?  
**Đáp án:** Nó không tiêu thụ và tái chuẩn bị buffer; sau khi buffer đầy, lượt đọc có thể trả `0` liên tục. Không sử dụng giá trị dương đã đọc cũng có thể làm mất logic xử lý dữ liệu.

**7.** `write(src)` trả `0` nghĩa là gì?  
**Đáp án:** Lần gọi chưa ghi byte nào; không có sentinel `-1` cho EOF trong `write`. Có thể hết dữ liệu trong src hoặc channel non-blocking chưa sẵn sàng ghi.

## 15. Ghi nhớ

```text
READ:
    n > 0  -> đã nhận đúng n byte, xử lý dữ liệu mới
    n == 0 -> không có tiến triển; kiểm tra buffer và chờ nếu cần
    n == -1-> EOF input; dừng đọc và giải quyết dữ liệu đang đệm
    throws -> lỗi I/O hoặc trạng thái không hợp lệ; xử lý riêng

WRITE:
    n > 0  -> đã ghi n byte
    n == 0 -> không tiến triển; tránh busy loop
    không có -1 như tín hiệu EOF
```

Với NIO, **kết quả `0` là trạng thái của một lần gọi, còn `-1` là tín hiệu kết thúc luồng đọc**. Dữ liệu của ứng dụng vẫn phải được phân định bằng `ByteBuffer.position/limit` và quy tắc framing, thay vì chỉ dựa vào một lần đọc.

## Tài liệu tham khảo chính thức

- Java SE 21 — `ReadableByteChannel.read(ByteBuffer)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 21 — `FileChannel.read(ByteBuffer)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 21 — `SocketChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 21 — `WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html
- Java SE 21 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21 — `AsynchronousByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html
- Java SE 21 — `AsynchronousFileChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
