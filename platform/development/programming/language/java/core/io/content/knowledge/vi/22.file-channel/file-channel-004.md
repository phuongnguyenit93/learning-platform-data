# FileChannel: size, truncate và giới hạn thay đổi độ dài tệp

## 1. Kích thước tệp và vị trí channel là hai khái niệm khác nhau

Trong Java NIO, `java.nio.channels.FileChannel` cho phép truy cập tệp theo byte, đọc và ghi tại các vị trí nhất định, đồng thời truy vấn hoặc thu nhỏ kích thước. Ba khái niệm chính:

- `size()`: **độ dài tệp hiện tại**, tính bằng byte, trả về `long`.
- `position()` và `position(long)`: **vị trí hiện tại của channel** để đọc/ghi tiếp; vị trí không nhất thiết trùng độ dài.
- `truncate(long)`: **cắt phần đuôi** nếu tệp lớn hơn kích thước yêu cầu; không mở rộng tệp.

Ví dụ tệp có tám byte ASCII:

~~~text
Index:        0 1 2 3 4 5 6 7 | 8
Content:      A B C D E F G H | EOF
Size = 8
Position có thể là 0, 3, 8, 100...
~~~

**Đặt `position(100)` không tạo thêm 92 byte.** Position là con trỏ logic. Độ dài thường thay đổi do ghi dữ liệu vượt EOF hoặc do cắt tệp.

`FileChannel` triển khai `SeekableByteChannel` và bổ sung các thao tác đọc/ghi tại offset tường minh, mapping, file lock, và đồng bộ dữ liệu (`force`). Bài này tập trung vào **kích thước và việc thay đổi kích thước** của tệp, không dùng position làm đại diện cho size.

## 2. Mở FileChannel đúng chế độ để thay đổi tệp

Ví dụ mở một tệp đã có, vừa đọc vừa ghi:

~~~java
Path path = Path.of("data.bin");
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    System.out.println(channel.size());
}
~~~

Đây là mảnh mã minh họa, cần import `java.nio.file.*` và `java.nio.channels.FileChannel`, cũng như một tệp `data.bin` đang tồn tại.

Các tùy chọn cần phân biệt:

| Tùy chọn | Tác dụng |
| --- | --- |
| `READ` | Cho phép đọc; không đủ quyền để thay đổi độ dài. |
| `WRITE` | Cho phép ghi/truncate khi filesystem và quyền hệ điều hành cho phép. |
| `CREATE` | Tạo tệp nếu chưa có khi đi cùng tùy chọn ghi thích hợp. |
| `CREATE_NEW` | Chỉ tạo mới; không vô tình dùng tệp đã tồn tại. |
| `TRUNCATE_EXISTING` | Khi mở để ghi, tệp có sẵn bị cắt còn **0 byte ngay lúc mở**. |
| `APPEND` | Ghi nối cuối theo ngữ nghĩa provider; không phù hợp khi cần kiểm soát offset ghi. |

Không truyền options cho `FileChannel.open(path)` thì mặc định là `READ`. Muốn sửa nội dung hoặc gọi `truncate`, phải mở channel có quyền `WRITE` và bảo đảm hệ thống tệp không cấm thao tác.

**`TRUNCATE_EXISTING` khác `channel.truncate(n)`:** option thứ nhất tác động **khi mở**, còn phương thức thứ hai tác động **tại thời điểm được gọi**. Nếu cần sửa vài byte đầu của tệp có nội dung quan trọng, tránh thêm `TRUNCATE_EXISTING` theo thói quen vì nó có thể xóa sạch nội dung ngay lập tức.

Quản lý vòng đời bằng `try-with-resources` để đóng channel sau khi dùng. Khi thao tác với tệp đang được nhiều tiến trình truy cập, việc chỉ đóng channel không thay thế đồng bộ hóa và bảo đảm nhất quán của ứng dụng.

## 3. `size()` trả về số byte nào?

Chữ ký:

~~~java
long size() throws IOException;
~~~

`size()` trả độ dài **logic hiện tại** của tệp mà channel đại diện, không phải vị trí đọc/ghi, số phần tử đang có trong ByteBuffer hay dung lượng đĩa đã cấp phát.

~~~text
Tệp ASCII "HELLO"
size() = 5
position() = 2
~~~

Độ dài có đơn vị **byte**. Với UTF-8, chuỗi tiếng Việt thường có số byte lớn hơn số ký tự nhìn thấy. Không dùng `String.length()` hoặc số dòng văn bản để dự đoán chính xác `size()`, trừ khi đã xác định encoding và tính độ dài byte thực sự.

Kiểu trả về `long` cho phép biểu diễn kích thước tệp lớn hơn giới hạn `int`. Tuy vậy, **hỗ trợ API không bảo đảm hệ thống tệp chấp nhận mọi kích thước trong phạm vi của `long`**. Kích thước tối đa, quota, dung lượng vật lý và quyền ghi phụ thuộc filesystem/provider/hệ điều hành.

Một tệp sparse có thể báo `size()` lớn nhưng không chiếm cùng từng ấy byte lưu trữ vật lý. Tương tự, `size()` là giá trị **ở thời điểm gọi**; tác vụ khác có thể kéo dài hoặc cắt file ngay sau đó. Không coi `size()` là snapshot giao dịch hay cơ chế khóa.

Khi chỉ có `Path`, `Files.size(path)` cũng có thể đọc metadata kích thước. Khi đang thao tác trên một `FileChannel` đã mở, `channel.size()` gắn trực tiếp với cùng kênh đang sử dụng nhưng vẫn không loại bỏ race condition với người ghi khác.

## 4. `position()` có thể khác `size()`, kể cả vượt EOF

FileChannel có hai phương thức:

~~~java
long position() throws IOException;
FileChannel position(long newPosition) throws IOException;
~~~

Ví dụ:

~~~text
File content: ABCDEF
size = 6
position(2) → đọc/ghi tương đối tiếp theo bắt đầu ở offset 2
position(6) → đang ở EOF
position(100) → vượt EOF; file vẫn có size = 6
~~~

Đặt vị trí lớn hơn EOF là hợp lệ. Gọi `read(buffer)` ở vị trí sau EOF của file thông thường sẽ trả `-1` nếu không có dữ liệu; riêng việc tìm vị trí không tự làm file lớn hơn. Đặt vị trí âm sẽ ném `IllegalArgumentException`.

Mỗi lần `channel.read(dst)` thành công với `n` byte, channel position tăng `n`. `channel.write(src)` thành công với `n` byte cũng đẩy channel position tiến tương ứng. Đồng thời, `ByteBuffer.position()` cũng tăng theo số byte đã chuyển. Đây là **hai đối tượng, hai vị trí khác nhau**.

`channel.position(0)` đưa điểm đọc tệp về đầu nhưng không tự gọi `buffer.clear()` hoặc `buffer.flip()`. Ngược lại, `buffer.flip()` chỉ chuẩn bị đọc byte đã nhận vào buffer, không chuyển position của channel.

## 5. Hợp đồng `truncate(long)`: chỉ thu nhỏ

Chữ ký:

~~~java
FileChannel truncate(long size) throws IOException;
~~~

Gọi `truncate(newSize)` áp dụng các quy tắc:

1. Nếu `newSize < oldSize`, tệp mất các byte nằm từ offset `newSize` trở về sau và kích thước thành `newSize`.
2. Nếu `newSize >= oldSize`, độ dài file **không đổi**. Phương thức không điền thêm dữ liệu.
3. Nếu vị trí hiện tại lớn hơn `newSize`, vị trí sẽ được đặt về `newSize`; nếu không lớn hơn thì giữ nguyên.
4. `newSize < 0` gây `IllegalArgumentException`.
5. Không có quyền ghi gây `NonWritableChannelException`; filesystem, thiết bị, quota hoặc các điều kiện I/O khác có thể gây `IOException`.

Ví dụ file `ABCDEFGH` (8 byte):

~~~text
Offset:     0 1 2 3 4 5 6 7
Before:     A B C D E F G H
            position=3; size=8

truncate(5)

After:      A B C D E
            position=3; size=5
~~~

Nếu trước khi gọi `truncate(5)`, channel đang ở `position=8` thì vị trí sẽ bị đưa về 5. Nếu gọi `truncate(100)` trên tệp 5 byte, **tệp vẫn 5 byte**.

### Cắt tệp về 0 byte

`truncate(0)` cắt toàn bộ nội dung. Đây là thao tác mất dữ liệu thực sự, không phải “đặt position về 0”. Nó đặc biệt nguy hiểm khi nhắm nhầm file log, file dữ liệu nhị phân hoặc file đang được ứng dụng khác sử dụng.

`truncate(n)` trả về chính channel để có thể gọi tiếp phương thức nếu phù hợp; việc trả về đối tượng không có nghĩa thao tác được đặt lịch chạy bất đồng bộ.

## 6. Muốn tăng độ dài: ghi dữ liệu sau EOF

Để tạo thêm byte ở cuối, có thể đặt position tại EOF rồi ghi:

~~~java
channel.position(channel.size());
ByteBuffer bytes = ByteBuffer.wrap(new byte[] {'X', 'Y'});
while (bytes.hasRemaining()) {
    int n = channel.write(bytes);
    if (n == 0) {
        throw new IOException("Write made no progress");
    }
}
~~~

Mảnh minh họa trên cần có `channel` đã mở quyền `WRITE`, import `java.nio.ByteBuffer` và `java.io.IOException`. Chỉ dùng vòng lặp có chính sách xử lý lỗi/tiến độ thích hợp; ví dụ chọn ném lỗi nếu ghi 0 byte thay vì quay mãi không tiến triển.

Nếu tệp dài 4 byte và đặt `position(10)` rồi ghi thành công đúng 1 byte:

~~~text
Before:        A B C D
Offsets:       0 1 2 3 | EOF=4

write 'Z' at offset 10

After:         A B C D ? ? ? ? ? ? Z
Offsets:       0 1 2 3 4 5 6 7 8 9 10 | EOF=11
position=11, size=11
~~~

**Không giả định các byte đánh dấu `?` luôn bằng 0.** Giá trị byte trong khoảng từ EOF cũ đến điểm bắt đầu ghi mới không được hợp đồng chung của `FileChannel` bảo đảm. Filesystem có thể sử dụng sparse holes hoặc cách lưu trữ khác. Nếu dữ liệu yêu cầu khoảng trống chứa byte cụ thể, hãy **ghi rõ nội dung đệm** vào khoảng đó.

Ghi tại offset đã tồn tại là **ghi đè**, không phải chèn làm dịch chuyển phần đuôi:

~~~text
Before: ABCDEFGH   size=8
position(2), write "xy"
After:  ABxyEFGH   size=8
~~~

Do đó, size chỉ tăng khi ghi qua EOF (hoặc tác vụ khác thay đổi file). Những lần ghi thay thế byte bên trong tệp có thể không thay đổi size.

## 7. Ví dụ Java 17+: size, truncate, vị trí vượt EOF và mở rộng

Chương trình dùng tệp tạm, chỉ chứa byte ASCII để không có nhầm lẫn giữa ký tự và byte. Nó không in tên file ngẫu nhiên và không đọc vùng gap chưa xác định, nên stdout ổn định trên default filesystem thông dụng.

Lưu thành `FileChannelLengthDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelLengthDemo {

    static void writeAscii(FileChannel ch, String text) throws IOException {
        ByteBuffer src = ByteBuffer.wrap(
                text.getBytes(StandardCharsets.US_ASCII));
        while (src.hasRemaining()) {
            if (ch.write(src) == 0) {
                throw new IOException("No write progress");
            }
        }
    }

    static String readExactly(FileChannel ch, int bytes) throws IOException {
        ByteBuffer dst = ByteBuffer.allocate(bytes);
        while (dst.hasRemaining()) {
            int n = ch.read(dst);
            if (n == -1) {
                throw new EOFException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
        }
        dst.flip();
        return StandardCharsets.US_ASCII.decode(dst).toString();
    }

    static void state(String title, FileChannel ch) throws IOException {
        System.out.println(title + ": position=" + ch.position()
                + ", size=" + ch.size());
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("length-demo-", ".bin");
        try {
            try (FileChannel ch = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                state("initial", ch);

                writeAscii(ch, "ABCDEFGH");
                state("written", ch);

                ch.position(3);
                ch.truncate(5);
                state("truncate 5", ch);

                ch.position(100);
                state("seek 100", ch);

                ch.truncate(4);
                state("truncate 4", ch);

                ch.truncate(20);
                state("truncate 20", ch);

                ch.position(0);
                System.out.println("prefix=" + readExactly(ch, 4));
                state("after read", ch);

                ch.position(6);
                writeAscii(ch, "Z");
                state("write beyond EOF", ch);

                ch.truncate(2);
                state("truncate 2", ch);

                ch.position(0);
                System.out.println("final=" + readExactly(ch, 2));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac FileChannelLengthDemo.java
java FileChannelLengthDemo
~~~

Stdout:

~~~text
initial: position=0, size=0
written: position=8, size=8
truncate 5: position=3, size=5
seek 100: position=100, size=5
truncate 4: position=4, size=4
truncate 20: position=4, size=4
prefix=ABCD
after read: position=4, size=4
write beyond EOF: position=7, size=7
truncate 2: position=2, size=2
final=AB
~~~

Diễn giải các mốc:

1. Tệp tạm mới có size 0; mở `READ, WRITE` không phá hủy nội dung. Position ban đầu bằng 0.
2. Ghi đủ 8 byte `ABCDEFGH`: position tăng lên 8, size thành 8.
3. Seek đến offset 3 rồi `truncate(5)`: còn `ABCDE`, size=5, position vẫn 3 vì nằm trước giới hạn mới.
4. `position(100)` không tăng size; phép in tiếp theo cho thấy size vẫn bằng 5.
5. `truncate(4)` làm mất `E` và đưa position từ 100 về 4.
6. `truncate(20)` không làm tệp dài ra; size và position trong trường hợp này đều vẫn 4.
7. Đọc từ đầu được `ABCD`. Hàm `readExactly` đọc đúng số byte yêu cầu, kiểm tra EOF, rồi `flip` buffer trước khi decode.
8. Ghi `Z` tại offset 6: size thành 7, position thành 7. Ví dụ không suy đoán nội dung ở offset 4 và 5.
9. `truncate(2)` cắt tệp còn `AB`, kéo position về 2; đọc lại từ đầu xác nhận `AB`.
10. `try-with-resources` đóng channel; `finally` xóa file tạm ngay cả khi thao tác I/O thất bại.

Chương trình dùng cách ném `IOException` khi đọc/ghi không tiến triển. Với kênh không chặn trong hệ thống ứng dụng thực tế, cần cơ chế chờ/tái thử thích hợp. Phần lõi của bài là hợp đồng `FileChannel` với tệp thông thường, không phải thiết kế xử lý non-blocking I/O.

## 8. Các overload có offset riêng và tác động tới size

Ngoài `read(dst)` và `write(src)` sử dụng position chung, `FileChannel` hỗ trợ:

~~~java
int read(ByteBuffer dst, long position);
int write(ByteBuffer src, long position);
~~~

Ở đây `position` truyền vào là offset **riêng của lần gọi**, không làm đổi `channel.position()`. Tuy nhiên `ByteBuffer.position()` vẫn tiến theo số byte đọc/ghi.

Với ghi theo offset:

~~~java
ch.position(2);
ByteBuffer payload = ByteBuffer.wrap(new byte[] {'X', 'Y'});
int count = ch.write(payload, 100);
// ch.position() vẫn là 2.
// ch.size() có thể tăng nếu ghi thành công vượt EOF.
~~~

Đây là mảnh mã minh họa với biến `ch` đã tồn tại và có quyền ghi. `count` có thể nhỏ hơn 2; nếu cần ghi hết, hãy kiểm tra số byte thực tế và lặp với offset mới dựa trên tổng số byte đã ghi. Không lặp cố định cùng offset 100 nếu mục tiêu là hoàn thành phần byte còn lại.

Bảng tác động:

| Phương thức | Đổi position chung? | Có thể đổi size? |
| --- | --- | --- |
| `position(newPosition)` | Có | Không |
| `size()` | Không | Không |
| `read(dst)` | Có khi đọc được byte | Bản thân đọc không mở rộng |
| `write(src)` | Có khi ghi được byte | Có nếu ghi vượt EOF |
| `read(dst, offset)` | Không | Bản thân đọc không mở rộng |
| `write(src, offset)` | Không | Có nếu ghi vượt EOF |
| `truncate(newSize)` | Có thể kéo position xuống | Có thể giảm; không tăng |

Tác vụ khác vẫn có thể thay đổi tệp đồng thời, nên bảng mô tả **tác động trực tiếp** của mỗi lời gọi.

## 9. Những giới hạn thật sự của việc thay đổi độ dài

### Giới hạn filesystem, quota và quyền

Các phương thức dùng `long` không bảo đảm bạn có thể tạo tệp dài tùy ý. Kích thước tối đa phụ thuộc filesystem, runtime, provider, quota, dung lượng, quyền ghi, giới hạn của thiết bị và tài nguyên tiến trình.

Nếu không thể ghi hoặc cắt tệp, thao tác có thể ném `IOException` hoặc các ngoại lệ được API xác định như `NonWritableChannelException`. Tệp trên filesystem chỉ đọc và tệp đang bị kiểm soát bởi tiến trình khác có thể có những hạn chế khác nhau.

### Dữ liệu bị mất khi truncate

`truncate` có thể cắt qua giữa record của file nhị phân/log. Nếu cấu trúc file gồm header, độ dài, checksum, index, footer thì việc thu nhỏ có thể làm cả file không còn hợp lệ. Trước khi truncate cần hiểu **ranh giới dữ liệu hợp lệ** và có cơ chế backup/phục hồi nếu dữ liệu quan trọng.

~~~text
[record A][record B][record C][record D đang ghi dở]
                           ^
                  cuối record C hợp lệ
~~~

Một chiến lược phục hồi có thể xác minh bản ghi hợp lệ cuối cùng và cắt phần dở sau đó. Vị trí truncate phải là offset **theo byte** đã kiểm chứng, không phải số dòng hay số ký tự hiển thị.

### Đồng thời và trạng thái size không ổn định

Hai thread dùng chung một channel có thể tác động lên position chung; hai channel/tiến trình khác nhau có thể cùng sửa tệp. Mẫu:

~~~java
long end = ch.size();
ch.position(end);
ch.write(data);
~~~

là mảnh minh họa và **không phải một giao dịch append nguyên tử** khi có writer khác. Hai bên có thể cùng nhìn một `end` và ghi đè nhau. Cần chiến lược sở hữu channel, đồng bộ truy cập, file lock khi thích hợp hoặc cơ chế append đáp ứng yêu cầu nền tảng.

Tương tự, đọc size rồi dùng nó như một giới hạn bất biến sẽ sai nếu tiến trình khác truncate file ngay sau đó. Nếu cần tính nhất quán cao, hãy phối hợp tại cấp độ ứng dụng và quản lý dữ liệu theo transaction/protocol phù hợp.

### Mapping và các vùng tệp đã cắt bỏ

Nếu ứng dụng đang sử dụng `MappedByteBuffer` trên vùng bị truncate, việc truy cập vùng map không còn được file backing hỗ trợ có thể dẫn tới lỗi nghiêm trọng hoặc ngoại lệ tùy nền tảng/runtime. Không cắt file bên dưới các vùng mapping đang được thread khác sử dụng mà chưa xử lý vòng đời và đồng bộ của mapping.

### Bền vững của dữ liệu

`truncate()` trả về không đồng nghĩa mọi thay đổi đã bền vững trên thiết bị sau mất điện. `FileChannel.force(boolean metaData)` cung cấp yêu cầu đồng bộ các cập nhật phù hợp theo hợp đồng API; mức độ bảo đảm phụ thuộc provider, OS và thiết bị. `force` không biến nhiều thao tác `write` và `truncate` thành một giao dịch nguyên tử.

## 10. Các lỗi phổ biến và cách sửa

**Nhầm 1 — Dùng `truncate` để tăng độ dài.** `truncate(1024)` trên tệp 10 byte không tạo 1.014 byte mới. Phải ghi vượt EOF nếu thực sự cần tăng size.

**Nhầm 2 — Coi position là size.** Đặt `position(100)` không thay đổi `size()`. Hỏi trực tiếp `channel.size()` và nhớ nó có thể thay đổi đồng thời.

**Nhầm 3 — Mở nhầm `TRUNCATE_EXISTING`.** Khi muốn cập nhật tệp cũ, option này có thể xóa nội dung ngay trước khi bạn seek tới offset cần sửa.

**Nhầm 4 — Mở channel chỉ đọc rồi gọi `truncate`.** Cần quyền `WRITE` và filesystem hỗ trợ. Đừng bắt mọi exception như “file không tồn tại”; phải phân biệt lỗi quyền, IO, giá trị âm và trạng thái đóng.

**Nhầm 5 — Đếm offset theo ký tự.** FileChannel làm việc với byte; ký tự UTF-8 có thể chiếm nhiều byte. Với dữ liệu text, cần mã hóa thành byte và xác định ranh giới hợp lệ.

**Nhầm 6 — Ghi giữa file và mong dữ liệu tự chèn.** `write` ghi đè; muốn chèn phải dịch phần đuôi hoặc tạo file mới bằng thuật toán phù hợp.

**Nhầm 7 — Tưởng vùng gap sau khi ghi vượt EOF chắc chắn chứa 0.** Nội dung gap không được API bảo đảm chung; nếu cần định dạng deterministic, ghi byte đệm rõ ràng.

**Nhầm 8 — Bỏ qua kết quả `write`.** Một lần write có thể chưa tiêu thụ toàn bộ buffer. Dùng `hasRemaining()`, số byte trả về, và xử lý trường hợp không tiến triển.

**Nhầm 9 — Cắt file đang được ghi bởi tác vụ khác.** Không có phối hợp, có thể mất record, sai checksum hoặc khiến reader đang đọc phần đuôi thất bại.

## 11. Tự kiểm tra

1. Tệp 12 byte, position=3; gọi `truncate(8)`. Kết quả: **size=8, position=3**.
2. Tệp 12 byte, position=11; gọi `truncate(8)`. Kết quả: **size=8, position=8**.
3. Tệp 4 byte; gọi `truncate(20)`. Kết quả: **size vẫn 4**.
4. Tệp 4 byte; gọi `position(10)`. Kết quả: **size vẫn 4** nếu chưa ghi hoặc bị thay đổi bên ngoài.
5. Tệp 4 byte; ghi thành công một byte ở offset 10. Kết quả: **size=11**; không được giả định byte ở offset 4–9 bằng 0.
6. Tệp `ABCDEFGH`, ghi `xy` tại offset 2. Kết quả **`ABxyEFGH`**, size vẫn 8.
7. Tại sao không dùng `TRUNCATE_EXISTING` khi sửa một header? Vì nó có thể cắt tệp còn 0 byte ngay lúc mở.
8. `write(payload, 100)` có thay đổi `channel.position()` không? **Không**. Có thể thay đổi size nếu ghi qua EOF.
9. Gọi `size()` trước khi một writer khác thao tác có bảo đảm kích thước giữ nguyên không? **Không**; đây chỉ là một phép quan sát.

**Ghi nhớ:** `size()` đo **độ dài hiện tại theo byte**; `position()` xác định **vị trí đọc/ghi tiếp theo**; `truncate(n)` **thu nhỏ** file khi cần và có thể kéo position xuống, nhưng **không mở rộng** file. Muốn tăng độ dài phải ghi dữ liệu ngoài EOF, đồng thời xử lý byte gap, giới hạn môi trường, tính nhất quán và quyền I/O.
