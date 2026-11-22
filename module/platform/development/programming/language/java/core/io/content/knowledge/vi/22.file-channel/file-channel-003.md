# FileChannel: đọc/ghi tại vị trí tuyệt đối mà không đổi position

## 1. Bài toán: truy cập một vùng tệp mà vẫn giữ nguyên vị trí hiện tại

Trong Java NIO, `java.nio.channels.FileChannel` cung cấp hai kiểu thao tác đọc/ghi:

- **Theo vị trí hiện tại của channel**: `read(ByteBuffer dst)` và `write(ByteBuffer src)`.
- **Theo vị trí tuyệt đối được chỉ định** (*positional I/O*): `read(ByteBuffer dst, long position)` và `write(ByteBuffer src, long position)`.

Điểm khác biệt cốt lõi: **hai phương thức có đối số `long position` thực hiện I/O tại offset byte được truyền vào, nhưng không sửa vị trí hiện tại của chính `FileChannel`**. Chúng rất hữu ích khi cần đọc header, cập nhật một bản ghi hoặc lấy một đoạn dữ liệu ở offset xác định mà không làm lệch luồng xử lý tuần tự đang dùng chung channel.

Phải phân biệt ba giá trị khác nhau:

1. **`channel.position()`**: offset byte hiện tại của *tệp* trên channel; được sử dụng và thường thay đổi bởi `read(dst)`/`write(src)` không truyền offset.
2. **Tham số `position` trong `read(dst, position)` hoặc `write(src, position)`**: offset byte *tuyệt đối* cho lần thao tác đó; **không phải** số byte dịch tương đối so với `channel.position()`.
3. **`buffer.position()`**: vị trí tiếp theo bên trong `ByteBuffer`; **vẫn tăng** khi có byte thực sự được đọc vào hoặc ghi ra buffer, kể cả trong I/O có offset tuyệt đối.

Ví dụ channel đang ở offset 100. Gọi `channel.read(dst, 20)` sẽ tìm đọc từ byte thứ 21 của tệp (offset 20). Sau khi đọc được 8 byte, `channel.position()` vẫn là **100**, trong khi `dst.position()` tăng **8** từ vị trí ban đầu của buffer.

## 2. API và điều kiện sử dụng

Các phương thức trọng tâm của `FileChannel`:

```java
int read(ByteBuffer dst) throws IOException;
int read(ByteBuffer dst, long position) throws IOException;

int write(ByteBuffer src) throws IOException;
int write(ByteBuffer src, long position) throws IOException;

long position() throws IOException;
FileChannel position(long newPosition) throws IOException;
long size() throws IOException;
```

Đây là chữ ký API rút gọn để minh họa, không phải chương trình hoàn chỉnh.

| Phương thức | Vị trí bắt đầu trên tệp | Thay đổi `channel.position()`? | Thay đổi `ByteBuffer.position()`? |
| --- | --- | --- | --- |
| `read(dst)` | Vị trí hiện tại của channel | Có khi đọc được byte | Có khi đọc được byte |
| `write(src)` | Vị trí hiện tại của channel | Có khi ghi được byte | Có khi ghi được byte |
| `read(dst, offset)` | Offset truyền vào | **Không** | **Có** khi đọc được byte |
| `write(src, offset)` | Offset truyền vào | **Không** | **Có** khi ghi được byte |
| `channel.position(newPosition)` | Đổi vị trí channel cho I/O tiếp theo | **Có** | Không |

**Offset là số byte bắt đầu từ 0.** Truyền offset âm cho thao tác positional I/O ném `IllegalArgumentException`. Đừng nhầm offset 0 là “byte thứ 0” theo cách đếm người dùng: đó là **byte thứ nhất** của tệp.

`FileChannel` có thể được tạo bằng `FileChannel.open(path, options...)` hoặc lấy từ các API liên quan như `FileInputStream.getChannel()`, `FileOutputStream.getChannel()`, `RandomAccessFile.getChannel()`. Khả năng đọc/ghi phụ thuộc quyền và mode mở, không chỉ kiểu Java.

Ví dụ mở kênh có quyền đọc và ghi:

```java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    // read/write với offset tuyệt đối
}
```

Đoạn mã này giả định `path` là một `Path` hợp lệ và đã import các lớp cần thiết. Chế độ `READ`/`WRITE` cần được chỉ định phù hợp với hoạt động; đọc channel không được mở đọc có thể ném `NonReadableChannelException`, ghi channel không được mở ghi có thể ném `NonWritableChannelException`.

## 3. Minh họa hai loại position độc lập

Giả sử tệp chứa tám byte ASCII:

```text
Tệp:      A   B   C   D   E   F   G   H
Offset:   0   1   2   3   4   5   6   7
                                  ^
                         channel.position() = 6
```

Ta tạo `ByteBuffer.allocate(3)` với `buffer.position() == 0` và gọi:

```java
int count = channel.read(buffer, 2);
```

Nếu lời gọi đọc được đủ ba byte:

```text
Tệp được lấy từ offset 2: C D E
Tổng byte đã đọc: 3
channel.position(): 6       (không thay đổi)
buffer.position(): 3        (tăng từ 0 lên 3)
buffer.limit(): 3           (không thay đổi, vì allocate(3))
```

Nếu chỉ đọc được một byte, `count=1` và `buffer.position()=1`. **Không được khẳng định một lần gọi luôn đọc đủ ba byte.**

Với thao tác ghi, giả sử `src` có dữ liệu `X Y`, `src.position()==0`, `src.limit()==2`. Gọi `channel.write(src, 4)` để ghi vào offset 4 sẽ thay byte `E, F` bằng `X, Y` nếu đã ghi đủ hai byte. `channel.position()` vẫn là 6; `src.position()` trở thành 2.

**Positional I/O không làm thay đổi vị trí channel**, nhưng **vẫn có thể thay đổi nội dung tệp, kích thước tệp, và vị trí của buffer**. Nó cũng không tự khóa dữ liệu để ngăn luồng hoặc tiến trình khác sửa đồng thời.

## 4. Ví dụ Java 17+ chạy độc lập: đối chiếu position trước và sau

Ví dụ này tạo tệp tạm chứa năm byte ASCII `ABCDE`, đặt `FileChannel.position(2)`, đọc hai byte từ offset 0 và ghi `XY` vào offset 3.

Để bảo đảm đúng số byte cần xử lý, chương trình lặp khi thao tác chưa hoàn tất. Mỗi lần đọc/ghi tiếp phải tính **offset tuyệt đối ban đầu + tổng số byte đã xử lý**, vì bản thân channel không tự tăng position khi dùng positional I/O.

**Tệp `PositionalFileChannelDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PositionalFileChannelDemo {
    static int readExactly(FileChannel channel, ByteBuffer dst, long offset)
            throws IOException {
        int total = 0;
        while (dst.hasRemaining()) {
            int n = channel.read(dst, offset + total);
            if (n == -1) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            total += n;
        }
        return total;
    }

    static int writeExactly(FileChannel channel, ByteBuffer src, long offset)
            throws IOException {
        int total = 0;
        while (src.hasRemaining()) {
            int n = channel.write(src, offset + total);
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("positional-", ".txt");

        try {
            Files.writeString(path, "ABCDE", StandardCharsets.US_ASCII);

            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                channel.position(2);
                System.out.println("Vi tri kenh ban dau: "
                        + channel.position());

                ByteBuffer dst = ByteBuffer.allocate(2);
                int read = readExactly(channel, dst, 0);
                System.out.println("So byte da doc: " + read);
                System.out.println("Vi tri kenh sau doc: "
                        + channel.position());
                System.out.println("Vi tri buffer sau doc: "
                        + dst.position());

                dst.flip();
                System.out.println("Noi dung doc: "
                        + StandardCharsets.US_ASCII.decode(dst));

                ByteBuffer src = ByteBuffer.wrap(
                        "XY".getBytes(StandardCharsets.US_ASCII));
                int written = writeExactly(channel, src, 3);

                System.out.println("So byte da ghi: " + written);
                System.out.println("Vi tri kenh sau ghi: "
                        + channel.position());
                System.out.println("Vi tri buffer sau ghi: "
                        + src.position());
                System.out.println("Kich thuoc tep: " + channel.size());
            }

            System.out.println("Noi dung tep: "
                    + Files.readString(path, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa mã nguồn:

```bash
javac PositionalFileChannelDemo.java
java PositionalFileChannelDemo
```

**Stdout chính xác nếu các thao tác I/O thành công:**

```text
Vi tri kenh ban dau: 2
So byte da doc: 2
Vi tri kenh sau doc: 2
Vi tri buffer sau doc: 2
Noi dung doc: AB
So byte da ghi: 2
Vi tri kenh sau ghi: 2
Vi tri buffer sau ghi: 2
Kich thuoc tep: 5
Noi dung tep: ABCXY
```

Giải thích:

1. `channel.position(2)` đặt offset hiện tại của channel bằng 2.
2. `readExactly(channel, dst, 0)` đọc hai byte từ offset 0 và 1, không tác động tới position=2 của channel. Buffer đọc nhận dữ liệu nên position của **`dst`** tăng từ 0 lên 2.
3. `dst.flip()` làm position của buffer về 0 và limit bằng 2, để decoder đọc đúng `AB`. Phương thức này cũng không đổi vị trí channel.
4. `writeExactly(channel, src, 3)` ghi hai byte `X Y` tại offset 3 và 4. Position của channel vẫn 2; position của **`src`** tăng từ 0 lên 2.
5. Lệnh ghi **thay thế** `D E` trong tệp `ABCDE`, nên tệp thành `ABCXY` và vẫn dài 5 byte.

Như vậy trong cùng một chương trình có **ba vị trí không bị trộn lẫn**: `channel.position()` (đang là 2), `dst.position()` và `src.position()` (đều đã tăng trong các thao tác tương ứng).

## 5. Vì sao phải xử lý partial read và partial write?

Các phương thức `read(ByteBuffer, long)` và `write(ByteBuffer, long)` trả về **số byte thực sự được chuyển trong lần gọi**, không bảo đảm tiêu thụ hết `buffer.remaining()`.

### Đọc theo offset

Một hàm đọc đủ `N` byte từ offset cố định cần duy trì:

\[
nextOffset = startOffset + bytesReadSoFar
\]

Giả sử cần đọc 6 byte từ offset 100 nhưng ba lần `read` lần lượt trả về 2, 3 và 1:

| Lần | Offset truyền vào | Số byte đọc | Tổng đã đọc | Channel position |
| --- | ---: | ---: | ---: | --- |
| 1 | 100 | 2 | 2 | Giữ nguyên |
| 2 | 102 | 3 | 5 | Giữ nguyên |
| 3 | 105 | 1 | 6 | Giữ nguyên |

Nếu **liên tục gọi `read(dst, 100)` với cùng offset 100**, lần thứ hai có thể đọc lại byte đã đọc trước đó vào phần kế tiếp của buffer. Đây là một trong những lỗi dễ mắc nhất khi chuyển từ API đọc tuần tự sang positional I/O.

Đối với `read`:

- `n > 0`: đã nhận `n` byte.
- `n == 0`: lần đó không có tiến độ, cần xem lại khả năng buffer đã hết chỗ, trạng thái tệp hoặc điều kiện I/O.
- `n == -1`: EOF, không còn byte tại vị trí yêu cầu để đọc. Nếu muốn đúng `N` byte, phải xử lý thiếu dữ liệu.

Nếu buffer có `remaining()==0`, không cần gọi I/O: số byte cần chuyển là 0. Các ví dụ `readExactly`/`writeExactly` ở trên dùng vòng `while (hasRemaining())` nên dừng ngay khi đã đủ.

### Ghi theo offset

Với `write(src, startOffset)`, nếu chỉ ghi được `n` byte thì `src.position()` tăng `n`, nhưng lần gọi tiếp theo vẫn phải cung cấp `startOffset + n`. Không làm vậy có thể **ghi đè** những byte vừa chuyển ở đầu vùng đích.

Giả sử cần ghi 5 byte vào offset 200, hai lần ghi trả về 2 rồi 3:

```text
write(src, 200)  --> ghi 2 byte đầu, src.position tăng 2
write(src, 202)  --> ghi 3 byte còn lại
```

Gọi `write(src, 200)` hai lần sẽ không tự biến offset thành 202, vì vị trí tham số là tuyệt đối.

Mẫu vòng lặp an toàn cho bài toán **yêu cầu ghi đủ**:

```java
long startOffset = 200L;
long transferred = 0L;

while (src.hasRemaining()) {
    int n = channel.write(src, startOffset + transferred);
    if (n == 0) {
        throw new IOException("No write progress");
    }
    transferred += n;
}
```

Đây là đoạn mã minh họa cần `src` và `channel` được khai báo, không phải chương trình độc lập. Với `FileChannel` và tệp thường, lỗi không có tiến độ thường cần được xử lý như tình huống bất thường. Cơ chế backoff/đợi hoặc giới hạn số lần thử phải được thiết kế theo lớp channel và yêu cầu ứng dụng, thay vì quay vòng vô hạn.

### Tại sao không dùng `channel.position(...)` trước mỗi thao tác?

Có thể gọi `channel.position(offset); channel.read(buffer);`, nhưng cách đó **thay đổi trạng thái position dùng chung**. Khi cần truy cập một vùng bất kỳ mà bảo toàn position cho thao tác tuần tự khác, dùng trực tiếp `channel.read(buffer, offset)` hoặc `channel.write(buffer, offset)` rõ mục đích hơn.

## 6. Đọc header khi channel vẫn tiếp tục xử lý tuần tự

Một tình huống phổ biến là:

1. Reader đã đọc tuần tự đến offset 512.
2. Ứng dụng muốn kiểm tra lại 16 byte header ở offset 0.
3. Reader sau đó cần tiếp tục từ offset 512.

Nếu tạm gọi `channel.position(0)`, đọc header rồi `channel.position(512)`, chương trình phải tự lưu/khôi phục vị trí và kiểm soát việc truy cập đồng thời. Với positional read:

```java
long previous = channel.position(); // ví dụ 512

ByteBuffer header = ByteBuffer.allocate(16);
int read = channel.read(header, 0);

System.out.println(channel.position() == previous);
```

Lệnh in là `true` nếu những tác động khác không thay đổi position đồng thời. Nhưng **`read` có thể trả về ít hơn 16**, và `header.position()` chỉ tăng bằng số byte đọc được. Nếu cần đủ header, dùng vòng lặp có offset tăng theo lượng đã nhận, kèm kiểm tra EOF như `readExactly` ở ví dụ chạy được.

**Lợi ích chính** là thao tác đọc header không tự gây thay đổi `channel.position()`. Tuy nhiên nội dung tệp vẫn có thể bị tiến trình khác sửa giữa các lần đọc; positional I/O **không bảo đảm snapshot nhất quán**.

## 7. Cập nhật bản ghi cố định bằng positional write

Giả sử một file chứa nhiều bản ghi độ dài cố định:

| Trường | Cách mã hóa | Số byte |
| --- | --- | ---: |
| `id` | `int` big-endian | 4 |
| `quantity` | `int` big-endian | 4 |
| Tổng |  | **8** |

Bản ghi thứ `index` (tính từ 0) bắt đầu tại:

\[
recordOffset = (long) index \times 8
\]

Trường `quantity` bắt đầu ở `recordOffset + 4`. Nếu muốn đổi số lượng của bản ghi có index=2, offset cần ghi là `2 * 8 + 4 = 20`.

Bằng `ByteBuffer` ta có thể mã hóa số nguyên rồi ghi 4 byte tại đúng offset mà không thay đổi channel position.

**Tệp `PositionalRecordDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PositionalRecordDemo {
    private static final int RECORD_SIZE = 8;

    private static void writeAll(
            FileChannel channel, ByteBuffer src, long offset)
            throws IOException {
        long written = 0;
        while (src.hasRemaining()) {
            int n = channel.write(src, offset + written);
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
            written += n;
        }
    }

    private static void readAll(
            FileChannel channel, ByteBuffer dst, long offset)
            throws IOException {
        long read = 0;
        while (dst.hasRemaining()) {
            int n = channel.read(dst, offset + read);
            if (n == -1) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            read += n;
        }
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("records-", ".bin");

        try {
            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer records = ByteBuffer.allocate(3 * RECORD_SIZE);
                records.order(ByteOrder.BIG_ENDIAN);
                records.putInt(101).putInt(5);
                records.putInt(102).putInt(7);
                records.putInt(103).putInt(9);
                records.flip();
                writeAll(channel, records, 0);

                channel.position(6);
                System.out.println("Vi tri truoc: "
                        + channel.position());

                long quantityOffset = 2L * RECORD_SIZE + 4;
                ByteBuffer update = ByteBuffer.allocate(4);
                update.order(ByteOrder.BIG_ENDIAN);
                update.putInt(90).flip();
                writeAll(channel, update, quantityOffset);

                ByteBuffer result = ByteBuffer.allocate(RECORD_SIZE);
                result.order(ByteOrder.BIG_ENDIAN);
                readAll(channel, result, 2L * RECORD_SIZE);
                result.flip();

                System.out.println("Ban ghi index 2: "
                        + result.getInt() + ", " + result.getInt());
                System.out.println("Vi tri sau: "
                        + channel.position());
                System.out.println("Do dai file: " + channel.size());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PositionalRecordDemo.java
java PositionalRecordDemo
```

**Stdout chính xác trong điều kiện I/O thành công:**

```text
Vi tri truoc: 6
Ban ghi index 2: 103, 90
Vi tri sau: 6
Do dai file: 24
```

Lý do:

- Ba bản ghi, mỗi bản ghi 8 byte, tạo file 24 byte.
- Ban đầu bản ghi index 2 là `id=103, quantity=9` tại offset 16–23.
- `writeAll(..., 20)` thay chính xác 4 byte của `quantity` bằng số nguyên 90 theo big-endian.
- `readAll(..., 16)` đọc lại toàn bộ bản ghi để lấy `103,90`.
- Cả hai thao tác có offset tường minh đều không làm thay đổi `channel.position()` đang là 6.

**Giới hạn của ví dụ:** việc ghi 4 byte và đọc lại chưa tạo thành giao dịch nguyên tử trong trường hợp nhiều writer cùng truy cập. Với file có dữ liệu quan trọng, cần thiết kế kiểm soát khóa, phối hợp writer, xử lý crash và cấu trúc nhất quán riêng. `channel.position()==6` chỉ chứng minh trạng thái con trỏ được bảo toàn; **không chứng minh thao tác cập nhật là atomic**.

## 8. ByteBuffer vẫn thay đổi position, limit không tự thay đổi

Hợp đồng `FileChannel.read(dst, offset)` đọc byte vào buffer từ `dst.position()` hiện tại tới `dst.limit()`:

```text
dst ban đầu: capacity=10, position=3, limit=7
remaining = 4

Nếu read(dst, 100) trả về 2:
dst.position() trở thành 5
dst.limit() vẫn 7
dst.capacity() vẫn 10
channel.position() không đổi
```

Tương tự, `write(src, offset)` tiêu thụ dữ liệu từ `src.position()` đến `src.limit()`, làm position của buffer tăng theo số byte ghi thành công.

Khi chuẩn bị dữ liệu cho channel:

- `put(...)` ghi vào buffer và tăng `buffer.position()`.
- `flip()` chuyển sang chế độ lấy dữ liệu ra: `limit=position` cũ, `position=0`.
- `write(buffer, offset)` tiêu thụ byte từ buffer, tăng `buffer.position()`.
- `clear()` chỉ thiết lập lại trạng thái để dùng lại buffer, **không xóa byte**.
- `compact()` dùng khi cần giữ phần chưa tiêu thụ rồi ghi thêm.

Đặc biệt, **`ByteBuffer.get(index)` / `put(index, value)`** cũng là thao tác tuyệt đối nhưng áp dụng với **chỉ số trong buffer**. Chúng thường không đổi `buffer.position()`; đừng nhầm với `FileChannel.read(dst, fileOffset)`, vốn vẫn thay đổi `dst.position()`. Hai API có chữ “absolute” nhưng trạng thái mà chúng bảo toàn **khác nhau**.

## 9. Những trường hợp biên cần thiết kế rõ

### 9.1. Offset bằng hoặc vượt EOF

Giả sử file dài 10 byte, offset hợp lệ của byte hiện có là 0–9. `channel.read(dst, 10)` với buffer còn chỗ sẽ gặp EOF và thông thường trả về `-1`. `channel.read(dst, 20)` cũng không thể đọc ra byte từ vùng chưa có dữ liệu. **Positional read không tự kéo dài file.**

Cần chú ý khi `dst.remaining()==0`: không có yêu cầu truyền byte. Đừng dùng buffer trống để kiểm tra EOF; hãy kiểm tra `size()` hoặc thử đọc với một buffer còn chỗ, xử lý giá trị trả về theo hợp đồng. Không nên dựa vào giá trị cố định của một lời gọi đọc độ dài 0 làm cách kết luận tệp đã kết thúc.

### 9.2. Ghi vượt EOF

`channel.write(src, offset)` với offset lớn hơn kích thước file có thể mở rộng file nếu có byte thực sự được ghi. Ví dụ file dài 10 và ghi một byte tại offset 20 có thể khiến kích thước mới thành 21. Các byte nằm giữa EOF cũ và vùng vừa ghi **không được bảo đảm có giá trị xác định bởi hợp đồng `FileChannel`**.

Nếu định dạng tệp yêu cầu vùng trống được khởi tạo bằng 0 hoặc giá trị khác, chương trình phải thực hiện việc khởi tạo theo thiết kế. Việc chỉ di chuyển position tuyệt đối mà không ghi byte **không mở rộng tệp**.

### 9.3. Không truy cập offset âm

`read(dst, -1)` hoặc `write(src, -1)` vi phạm điều kiện tham số và ném `IllegalArgumentException`. Nên xác thực offset và độ dài trước khi đưa vào API; đặc biệt chú ý phép cộng `startOffset + bytesTransferred` và phép nhân `recordIndex * recordSize` để không tràn `long`.

Nếu đọc một bản ghi đã tồn tại, kiểm tra dữ liệu còn trong giới hạn, ví dụ:

```java
if (offset < 0 || length < 0
        || offset > channel.size()
        || length > channel.size() - offset) {
    throw new IOException("Record outside file");
}
```

Đây là đoạn mã minh họa, giả định `offset` và `length` là số nguyên `long`, `channel` đã mở. Dạng `length > size - offset` tránh tràn số khi tính `offset + length`, nhưng chỉ kiểm tra **trạng thái tại thời điểm gọi**; một tiến trình khác vẫn có thể sửa file sau đó.

### 9.4. Channel mở với mode không tương thích

`FileChannel.open(path, READ)` không cho phép `write`; `FileChannel.open(path, WRITE)` không cho phép `read`. Các ngoại lệ có thể là `NonWritableChannelException`/`NonReadableChannelException`.

Nếu mở file ở chế độ `APPEND`, hành vi của **positional write** có thể phụ thuộc hệ thống: đặc tả Java nêu hiệu ứng của positional write trong khi mở append là không xác định theo triển khai. **Tránh kết hợp `APPEND` với positional write khi cần bảo đảm ghi đúng offset**; dùng mode ghi thích hợp và tự quy định chiến lược append nếu nghiệp vụ yêu cầu.

### 9.5. Buffer chỉ đọc, channel đóng và lỗi I/O

Đọc byte vào `ByteBuffer` chỉ đọc là không hợp lệ và có thể gây `ReadOnlyBufferException`. Channel đóng có thể gây `ClosedChannelException`; hoạt động I/O cũng có thể gặp lỗi hệ thống, khóa hoặc ngắt luồng.

Dù `isOpen()` trả về `true`, channel có thể bị đóng trước thao tác tiếp theo. Xử lý lỗi tại chính lần `read` hoặc `write` và đóng channel bằng `try-with-resources`.

## 10. Positional I/O và truy cập đồng thời

Positional I/O đặc biệt hữu ích khi nhiều thao tác cần vùng offset khác nhau mà không muốn chạy cặp lệnh `channel.position(x)` → `read/write` qua một con trỏ channel dùng chung.

**Nhưng nó không tự biến mọi thao tác thành an toàn luồng hoặc nguyên tử.**

Cần phân biệt:

1. **Vị trí channel được bảo toàn:** mỗi lệnh `read(buffer, offset)`/`write(buffer, offset)` không sửa `channel.position()`.
2. **Buffer vẫn là trạng thái thay đổi được:** nếu nhiều luồng dùng chung **một `ByteBuffer`**, position/limit của buffer có thể bị thay đổi xen kẽ.
3. **Nội dung tệp vẫn dùng chung:** hai writer cùng ghi vào vùng chồng lấn có thể cạnh tranh; reader có thể gặp dữ liệu thay đổi trong lúc xử lý.
4. **Mức song song của file operation tùy triển khai:** hợp đồng `FileChannel` không bảo đảm rằng tất cả positional I/O chạy đồng thời hoặc được nguyên tử hóa theo bản ghi.

Khi xử lý nhiều luồng, mỗi tác vụ nên có buffer và phạm vi offset riêng, kèm cơ chế phối hợp/khóa khi có vùng dữ liệu chồng lấn. `FileLock` có thể hỗ trợ một số mô hình phối hợp giữa tiến trình, nhưng cần hiểu phạm vi và giới hạn khóa theo hệ điều hành và hệ thống tệp; khóa cũng không thay thế xử lý crash, flush, hoặc giao dịch cập nhật tệp.

**Tại sao quan trọng?** Nếu luồng A gọi `channel.position(100)` rồi chưa kịp `read(dst)`, luồng B thay position thành 200, luồng A có thể đọc sai offset nếu thiếu đồng bộ. Thay bằng `read(dst, 100)` giúp luồng A truyền đúng offset cho thao tác của mình. Tuy vậy, vẫn phải giữ buffer riêng và kiểm soát người ghi dữ liệu.

## 11. Khi nào nên dùng positional I/O?

Các tình huống phù hợp:

| Tình huống | Ý nghĩa của offset tuyệt đối |
| --- | --- |
| Đọc header trong khi vẫn xử lý tuần tự phần thân | Không phải lưu/khôi phục channel position |
| Đọc bản ghi có độ dài cố định | Tính `offset = index * recordSize` |
| Cập nhật một trường nhị phân tại offset biết trước | Ghi đè đúng vùng cần sửa |
| Đọc nhiều đoạn khác nhau theo chỉ mục | Mỗi đoạn dùng offset tường minh |
| Nhiều tác vụ độc lập xử lý các vùng tệp tách biệt | Tránh thay đổi con trỏ tệp do từng lệnh positional I/O |

Không phải lúc nào positional I/O cũng cần thiết. Nếu ứng dụng chỉ tuần tự đọc toàn bộ file một lần, `channel.read(buffer)` trong một vòng lặp đơn giản có thể dễ hiểu hơn. Nếu cần thao tác giống file pointer chung, `channel.position(...)` vẫn là API phù hợp khi có kiểm soát luồng truy cập.

Positional I/O không bắt buộc nhanh hơn. Hiệu năng phụ thuộc hệ thống tệp, thiết bị lưu trữ, cache, kích thước buffer, kiểu truy cập, mức độ song song và bản chất dữ liệu. Khi tối ưu, nên đo với khối lượng công việc thực tế.

## 12. So sánh với `RandomAccessFile.seek` và ByteBuffer absolute get/put

| API | Vị trí chỉ định thuộc về | Tác động lên trạng thái |
| --- | --- | --- |
| `RandomAccessFile.seek(offset)` | File pointer của `RandomAccessFile` | **Đổi** vị trí tệp dùng cho thao tác tiếp theo |
| `FileChannel.position(offset)` | Vị trí hiện tại của channel | **Đổi** vị trí tệp dùng cho thao tác tiếp theo |
| `FileChannel.read(dst, offset)` | Offset tệp riêng của lần đọc | **Giữ** channel position; tăng `dst.position()` khi đọc được byte |
| `FileChannel.write(src, offset)` | Offset tệp riêng của lần ghi | **Giữ** channel position; tăng `src.position()` khi ghi được byte |
| `ByteBuffer.get(index)` | Chỉ số trong buffer | Thường **giữ** `buffer.position()` |
| `ByteBuffer.put(index, byte)` | Chỉ số trong buffer | Thường **giữ** `buffer.position()` |

Nếu `FileChannel` lấy qua `RandomAccessFile.getChannel()`, hai đối tượng có quan hệ về file position. Positional I/O không đổi file position đó, nhưng gọi `seek` hoặc `position(long)` trên một bên có thể ảnh hưởng tới vị trí quan sát từ bên kia. Tránh trộn các API rồi suy diễn chúng có hai con trỏ tệp độc lập.

## 13. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tưởng `read(dst, offset)` cập nhật `channel.position()` | Lần đọc tuần tự sau vẫn bắt đầu tại offset cũ | Hiểu rõ hai dạng read; chỉ dùng `position(long)` khi thật sự muốn đổi vị trí channel |
| Tưởng positional I/O không đổi **bất kỳ** position nào | Buffer position vẫn thay đổi; xử lý sai dữ liệu | Kiểm tra riêng `channel.position()` và `buffer.position()` |
| Lặp `read(dst, sameOffset)` dù đã đọc được một phần | Dữ liệu bị đọc trùng từ cùng offset | Cộng dồn `bytesRead` vào offset mỗi lần |
| Lặp `write(src, sameOffset)` khi ghi một phần | Byte sau ghi đè byte trước | Dùng `startOffset + bytesWritten` |
| Không `flip` buffer sau khi tự `put` trước lúc ghi ra channel | Ghi sai vùng buffer | `flip()` trước pha tiêu thụ |
| Tưởng một lần `read/write` luôn chuyển hết remaining | Đọc thiếu/ghi thiếu | Lặp có kiểm tra progress, EOF và điều kiện I/O |
| Dùng tham số offset là chỉ số bản ghi | Truy cập sai byte | Nhân `index * recordSize` với số học `long` |
| Ghi offset vượt EOF và tưởng vùng trống tự bằng zero | Dữ liệu trung gian không có giá trị bảo đảm | Khởi tạo byte theo định dạng |
| Dùng `APPEND` với positional write để bảo đảm offset | Hành vi phụ thuộc triển khai | Mở channel với các option đọc/ghi thích hợp, tránh APPEND |
| Dùng chung một `ByteBuffer` từ nhiều luồng | Dễ race trên buffer position/limit | Mỗi tác vụ dùng buffer riêng hoặc đồng bộ |
| Tin positional write là giao dịch nguyên tử | Có thể gặp ghi một phần hoặc dữ liệu chồng lấn | Thiết kế phối hợp writer, phục hồi và nhất quán |

## 14. Bài tập tự kiểm tra

Giả sử file có 10 byte, `channel.position()==7`, và `ByteBuffer dst` có `capacity=6`, `position=1`, `limit=5`. Chương trình gọi:

```java
int n = channel.read(dst, 2);
```

Nếu lần gọi trả về `n==3`, kết quả chắc chắn nào có thể kết luận?

- **Channel position** vẫn là **7**.
- **Buffer position** tăng từ **1** lên **4**.
- **Buffer limit** vẫn là **5**, capacity vẫn 6.
- Ba byte được yêu cầu bắt đầu từ offset **2** của tệp và được đặt vào buffer bắt đầu tại index **1**.
- `dst.remaining()` lúc này bằng `5 - 4 = 1`.

Nếu muốn đọc nốt một byte nữa của đoạn tệp liền kề vào buffer, offset lần đọc tiếp theo phải là **`2 + 3 = 5`**. Lệnh `read(dst, 2)` lần nữa sẽ quay lại offset 2, dù buffer position lúc ấy đã là 4.

Đây là sự khác biệt quan trọng giữa **offset đầu vào cố định của tệp** và **position tự dịch của ByteBuffer**.

## 15. Ghi nhớ

1. **`FileChannel.read(dst, offset)` và `write(src, offset)` thao tác tại offset byte tuyệt đối mà không thay đổi `FileChannel.position()`.**
2. **`ByteBuffer.position()` vẫn di chuyển** theo số byte đã đọc/ghi thành công. Dữ liệu phải được chuẩn bị đúng `position/limit`.
3. Positional I/O có thể chỉ chuyển **một phần** buffer; nếu cần làm đủ, lặp với **`offset + tổng byte đã chuyển`**, xử lý EOF và lỗi không có tiến độ.
4. Positional write có thể thay đổi kích thước tệp, và dùng positional I/O không tạo tính nhất quán hay nguyên tử tự động.
5. Chú ý quyền mở channel, offset không âm, tràn số, EOF, APPEND và các truy cập đồng thời.
6. Khi muốn **đổi vị trí hiện tại** của channel, dùng `position(long)`; khi muốn **truy cập một offset mà giữ vị trí channel**, dùng các overload có tham số `long position`.

**Tài liệu tham khảo:** Java SE 17 API — `java.nio.channels.FileChannel`, `java.nio.ByteBuffer`, `java.nio.file.StandardOpenOption` và `java.io.RandomAccessFile`.
