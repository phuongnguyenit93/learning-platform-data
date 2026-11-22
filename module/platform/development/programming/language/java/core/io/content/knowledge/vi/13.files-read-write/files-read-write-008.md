# APPEND và giới hạn kết hợp OpenOption khi đọc/ghi bằng `Files`

## 1. Mục tiêu bài học

Trong Java NIO.2, các phương thức của `java.nio.file.Files` có thể nhận những tùy chọn mở tệp (`OpenOption`) để quyết định tệp được **đọc, ghi mới, ghi đè, cắt ngắn hay ghi nối thêm**. Một lựa chọn quan trọng là `StandardOpenOption.APPEND`: dữ liệu mới được ghi vào **cuối tệp hiện có**, thay vì ghi từ đầu tệp.

Tuy nhiên, `APPEND` không thể kết hợp tùy ý với tất cả các `OpenOption`. Nếu cấu hình sai, chương trình có thể ném ngoại lệ, mất nội dung cũ, ghi trùng dữ liệu hoặc gặp vấn đề khi nhiều luồng/tiến trình cùng ghi.

Sau bài học, bạn cần:

- Hiểu `APPEND` có tác dụng gì, khác gì với `WRITE`, `CREATE`, `CREATE_NEW` và `TRUNCATE_EXISTING`.
- Biết **mặc định khi không truyền options** vào `Files.writeString`, `Files.write`, `Files.newBufferedWriter` và `Files.newOutputStream`.
- Phân biệt các tổ hợp hợp lệ, tổ hợp không hợp lệ và các trường hợp phụ thuộc filesystem/provider.
- Sử dụng đúng `Files.writeString`, `Files.newBufferedWriter`, `Files.newOutputStream` và `Files.newByteChannel` ở Java 17+.
- Nhận diện giới hạn về tạo file, charset, xuống dòng, đồng thời, atomicity, đồng bộ dữ liệu xuống đĩa và vòng đời tài nguyên.
- Chọn cách an toàn giữa **thêm bản ghi vào log** và **thay thế toàn bộ nội dung file**.

**Thông điệp trung tâm:** `APPEND` mô tả **vị trí ghi**, không tự có nghĩa “tạo file nếu thiếu”, “được đọc cùng một channel”, “ghi nguyên tử toàn bản ghi” hoặc “dữ liệu đã được lưu bền vững”.

## 2. `StandardOpenOption` và cách diễn giải

`OpenOption` là giao diện đánh dấu các tùy chọn khi mở file. Trong API NIO.2, enum `java.nio.file.StandardOpenOption` cung cấp các lựa chọn phổ biến:

| Tùy chọn | Mục đích chính | Lưu ý |
| --- | --- | --- |
| `READ` | Mở để đọc | Không dùng cùng `APPEND` trên `Files.newByteChannel` |
| `WRITE` | Mở để ghi | Không tự có nghĩa là append; có thể ghi từ vị trí hiện hành |
| `APPEND` | Ghi mỗi lần ở cuối tệp | Kéo theo ý nghĩa ghi; không kết hợp `READ` hoặc `TRUNCATE_EXISTING` khi mở byte channel |
| `CREATE` | Tạo tệp nếu chưa tồn tại | Nếu đã tồn tại, không tự cắt ngắn nội dung |
| `CREATE_NEW` | Chỉ tạo file mới | Thất bại nếu đường dẫn đã tồn tại; thích hợp tránh ghi vào tệp có sẵn |
| `TRUNCATE_EXISTING` | Cắt tệp đang tồn tại xuống 0 khi mở để ghi | **Không phải append**; thường làm mất nội dung cũ |
| `SYNC` | Yêu cầu đồng bộ nội dung và metadata theo hợp đồng mở file | Không bảo đảm mọi hệ thống có hỗ trợ/hiệu năng như nhau |
| `DSYNC` | Yêu cầu đồng bộ cập nhật nội dung theo hợp đồng | Không đồng nghĩa tính nguyên tử của từng bản ghi |
| `DELETE_ON_CLOSE` | Đề nghị xóa file khi đóng theo semantics provider | Không phải lựa chọn để giữ log lâu dài |
| `SPARSE` | Gợi ý tạo file thưa khi phù hợp | Tùy provider, không liên quan trực tiếp đến append |

**Chú ý:** Các API khác nhau có tập `OpenOption` hợp lệ và giá trị mặc định khác nhau. Không thể nói “mọi phương thức Files mở file với READ” hay “mọi tùy chọn có thể truyền cho mọi API”.

## 3. `APPEND` hoạt động thế nào?

Giả sử tệp `events.log` đang chứa:

```text
start
```

Nếu mở với `APPEND` rồi ghi `"stop\n"`, nội dung thành:

```text
start
stop
```

Không có hành động tự chèn dấu xuống dòng. Nếu tệp ban đầu là `"start"` (không có `\n` cuối), ghi `"stop\n"` ở chế độ append sẽ tạo `"startstop\n"`. Người lập trình phải quyết định rõ **format bản ghi và ranh giới dòng**.

### 3.1. APPEND khác WRITE

`WRITE` cho phép ghi vào file nhưng **không yêu cầu mọi lần ghi luôn ở cuối file**. Nếu mở channel chỉ với `WRITE`, vị trí ghi mặc định thường là đầu file (position 0); ghi dữ liệu mới có thể đè lên những byte đầu mà không xóa phần đuôi cũ.

Ví dụ khái niệm:

```text
Tệp cũ:              ABCDEF
WRITE từ position 0: 12CDEF    (ghi hai byte; phần đuôi cũ còn)
TRUNCATE + WRITE:    12        (xóa nội dung cũ trước khi ghi)
APPEND:              ABCDEF12  (ghi thêm vào cuối)
```

`APPEND` thường được dùng với các phương thức ghi nối tiếp, chẳng hạn `Files.writeString(path, data, UTF_8, APPEND)`, hoặc stream/channel đã mở với `APPEND`. Không cố mô phỏng append đồng thời bằng `channel.position(channel.size())`: giữa bước lấy size và ghi, một writer khác có thể thay đổi file.

### 3.2. APPEND có tự tạo file nếu thiếu không?

**Không nên giả định.** Khi truyền tường minh `APPEND` mà **không** `CREATE` hoặc `CREATE_NEW`, tệp phải tồn tại theo hợp đồng mở tương ứng, nếu không có thể ném `NoSuchFileException`.

Ví dụ nên dùng để tạo log nếu thiếu và nối thêm nếu đã tồn tại:

```java
Files.writeString(
        logPath,
        "event\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

Đây là **đoạn mã minh họa**, chưa khai báo `logPath` và import. Nếu file chưa tồn tại, `CREATE` cho phép tạo mới; nếu đã có, `APPEND` yêu cầu thêm dữ liệu vào cuối. `APPEND` thể hiện ý nghĩa ghi (đối với các API hỗ trợ) nên có thể ghi rõ cả `WRITE` nếu muốn diễn đạt chủ đích.

## 4. Mặc định nguy hiểm: không truyền `OpenOption`

Với những overload ghi file phổ biến sau:

```java
Files.writeString(path, text);
Files.writeString(path, text, StandardCharsets.UTF_8);
Files.write(path, bytes);
Files.newBufferedWriter(path, StandardCharsets.UTF_8);
Files.newOutputStream(path);
```

**Nếu không chỉ định tùy chọn mở tệp**, các API ghi này mặc định có tác dụng tương đương **`CREATE` + `TRUNCATE_EXISTING` + `WRITE`**: file chưa có thì tạo, file đã tồn tại thì cắt về rỗng trước khi ghi, và file được mở để ghi. Đây là lựa chọn phù hợp cho **ghi lại toàn bộ nội dung**, nhưng **không phù hợp để cập nhật log theo kiểu append**.

Điểm quan trọng: khi **đã truyền options tường minh**, bạn đang chọn chế độ mở; đừng mặc định `CREATE` và `TRUNCATE_EXISTING` vẫn tự được thêm vào. Chẳng hạn:

```java
Files.writeString(path, "line\n",
        StandardCharsets.UTF_8, StandardOpenOption.APPEND);
```

về ý định là **ghi nối vào file đã tồn tại**, không đảm bảo tạo file. Nếu cần tạo khi thiếu, hãy truyền cả `CREATE`.

### 4.1. Bảng so sánh các thao tác thường gặp

| Ý định | Gợi ý `OpenOption` | Kết quả với file đã có | Kết quả với file chưa có |
| --- | --- | --- | --- |
| Ghi thay toàn bộ nội dung | Không truyền options (mặc định) | Cắt ngắn rồi ghi | Tạo và ghi |
| Ghi thay toàn bộ, ghi rõ chế độ | `CREATE, WRITE, TRUNCATE_EXISTING` | Cắt ngắn rồi ghi | Tạo và ghi |
| Ghi thêm, tạo nếu thiếu | `CREATE, APPEND` | Nối cuối | Tạo và ghi |
| Ghi thêm nhưng bắt buộc file đã có | `APPEND` | Nối cuối | Thất bại |
| Chỉ tạo file mới, từ chối file cũ | `CREATE_NEW, WRITE` | Thất bại | Tạo và ghi |
| Ghi vào file cũ theo vị trí | `WRITE` | Ghi từ vị trí hiện hành, không tự truncate | Thường thất bại nếu không có CREATE |
| Mở để đọc | `READ` trong API byte channel tương ứng | Đọc file | Thường thất bại nếu không có file |

Đối với `Files.newByteChannel`, **không truyền options mặc định là mở để `READ`**, khác các phương thức ghi file nói trên. Không áp dụng cùng một “mặc định” cho mọi API trong `Files`.

## 5. Các kết hợp không hợp lệ hoặc gây hiểu lầm

### 5.1. `APPEND` + `TRUNCATE_EXISTING`

Hai ý định mâu thuẫn:

- `APPEND` muốn giữ nội dung đã có và ghi thêm ở cuối.
- `TRUNCATE_EXISTING` muốn cắt bỏ nội dung đã có khi mở để ghi.

Với `Files.newByteChannel`/`SeekableByteChannel`, hợp đồng API quy định **`APPEND` và `TRUNCATE_EXISTING` không được dùng đồng thời**; tổ hợp không hợp lệ sẽ ném `IllegalArgumentException`. Đừng hy vọng Java “truncates trước rồi append” như một tính năng tiêu chuẩn. Chọn một ý định rõ ràng.

### 5.2. `APPEND` + `READ`

Với `Files.newByteChannel`, `APPEND` không được kết hợp `READ`. Cách định nghĩa APPEND trong API mở byte channel không cho phép vừa dùng READ vừa APPEND như một chế độ chung; tổ hợp không hợp lệ có thể phát sinh `IllegalArgumentException` hoặc dạng con phù hợp.

Nếu cần vừa quan sát nội dung file vừa thêm bản ghi:

- Mở **một luồng đọc riêng** và **một luồng append riêng**, quản lý đồng thời theo thiết kế ứng dụng.
- Hoặc chọn cơ chế truy cập theo vị trí và khóa phù hợp khi cần thao tác phức tạp; không mặc định thay thế APPEND bằng seek-to-end là an toàn dưới concurrency.
- Nếu đang xây hệ thống log/queue, cân nhắc một writer chuyên trách và cơ chế đồng bộ thay vì nhiều nơi cùng ghi tùy tiện.

Không dùng `READ, APPEND` như một tổ hợp mặc định rồi bắt lỗi để đoán provider “có thể hỗ trợ”.

### 5.3. `APPEND` + `CREATE`

Đây là tổ hợp **thường hợp lệ và hữu ích** khi muốn thêm dữ liệu vào file nếu có hoặc tạo mới nếu chưa có:

```java
Files.writeString(logPath, message,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

`CREATE` không đòi file phải mới; nếu file đã tồn tại nó không tự xóa. Kết hợp với `APPEND` là tình huống log cơ bản.

### 5.4. `CREATE_NEW` + `APPEND`

`CREATE_NEW` có mục tiêu khác `CREATE`: nó chỉ cho phép mở file mới, từ chối nếu tên file đã có. Nếu file đang tồn tại, ngoại lệ như `FileAlreadyExistsException` là kết quả mong đợi dù có yêu cầu append.

Vì thế, đừng chọn `CREATE_NEW` khi yêu cầu nghiệp vụ là **tích lũy nhiều bản ghi trong một file log đã tồn tại**. `CREATE_NEW` phù hợp khi bạn cần tạo đầu ra độc nhất, không chạm vào dữ liệu cũ.

### 5.5. `SYNC`/`DSYNC` không bảo đảm atomic append

Các tùy chọn `SYNC` và `DSYNC` liên quan yêu cầu đồng bộ thay đổi xuống thiết bị lưu trữ theo semantics provider. Chúng không biến nhiều lời gọi ghi hoặc nhiều dòng log thành một transaction, không bảo đảm không có xen kẽ giữa writer khác, và không thay chính sách lock/ghi tuần tự.

Bộ đệm của `BufferedWriter` cũng có ảnh hưởng: gọi `flush()` chuyển dữ liệu đã gom xuống writer/stream bên dưới, nhưng không đồng nghĩa toàn bộ dữ liệu đã durable sau sự cố mất điện. Nếu yêu cầu durability nghiêm ngặt, tìm hiểu `FileChannel.force(...)`/cơ chế fsync và hành vi filesystem/hardware thực tế.

### 5.6. Tùy chọn không hỗ trợ và ngoại lệ

Tập tùy chọn hợp lệ tùy **phương thức, filesystem provider và nền tảng**. Khi dùng tùy chọn không được API/provider hỗ trợ, có thể gặp `UnsupportedOperationException`; khi tổ hợp không hợp lệ, có thể gặp `IllegalArgumentException`; khi không được cấp quyền hoặc lỗi mở/ghi, có thể gặp `IOException` hoặc ngoại lệ truy cập tương ứng.

Đừng gộp tất cả lỗi thành “file không tồn tại”. Đặc biệt, **`IOException` khi ghi** có thể xuất hiện sau khi một phần dữ liệu đã được thêm vào file.

## 6. Ví dụ Java 17+: `Files.writeString` tạo, append và truncate

Ví dụ này chủ động tạo thư mục tạm để không sửa file người dùng, sử dụng UTF-8 rõ ràng và kiểm chứng nội dung sau mỗi thao tác. Chương trình không giả định một đường dẫn cố định trên Windows/Linux/macOS.

Lưu thành **`AppendOptionsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class AppendOptionsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("append-options-");
        Path log = directory.resolve("events.log");
        Path created = directory.resolve("new.log");

        try {
            Files.writeString(log, "first\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            Files.writeString(log, "second\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.APPEND);

            Files.writeString(log, "third\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);

            System.out.println("Appended: "
                    + Files.readAllLines(log, StandardCharsets.UTF_8));

            Files.writeString(created, "created\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);

            System.out.println("Created on append: "
                    + Files.readString(created, StandardCharsets.UTF_8)
                           .equals("created\n"));

            Files.writeString(log, "reset\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            System.out.println("After truncate: "
                    + Files.readAllLines(log, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(created);
            Files.deleteIfExists(log);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 AppendOptionsDemo.java
java AppendOptionsDemo
```

**Stdout khi mọi thao tác filesystem thành công:**

```text
Appended: [first, second, third]
Created on append: true
After truncate: [reset]
```

**Giải thích:**

1. `CREATE_NEW, WRITE` tạo `events.log` và ghi dòng đầu tiên. Nếu file đã tồn tại, thao tác này phải thất bại thay vì ghi đè.
2. `APPEND` thêm `second\n` vào file đã có; không cần tự seek về cuối.
3. `CREATE, APPEND` thêm `third\n` nhưng cũng xử lý được trường hợp file chưa tồn tại (đã được chứng minh với `new.log`).
4. Sau append, `readAllLines` với file demo nhỏ tạo danh sách ba dòng đúng thứ tự. Với log lớn, không nên gọi `readAllLines` chỉ để xác minh.
5. `WRITE, TRUNCATE_EXISTING` xóa nội dung cũ trong `events.log` rồi ghi `reset\n`. Lúc này các dòng trước đó không còn.
6. Khối `finally` dọn file và thư mục đã tạo. Với code production, lỗi ghi và lỗi cleanup cần được quản lý theo chính sách ứng dụng.

Ví dụ dùng ký tự `\n` để đầu ra nhất quán. Trong ứng dụng phải quy định encoding và newline theo format; `APPEND` không tự thêm dấu phân cách.

## 7. Ví dụ Java 17+: append nhị phân với `newByteChannel`

Khi làm việc với dữ liệu byte, có thể dùng `Files.newByteChannel` để mở một `SeekableByteChannel`, truyền các `OpenOption` bằng `Set`. Đây là nơi cần đặc biệt tránh kết hợp `READ` hoặc `TRUNCATE_EXISTING` với `APPEND`.

Lưu thành **`AppendByteChannelDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;

public class AppendByteChannelDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("append-channel-");
        Path file = directory.resolve("data.bin");

        try {
            Files.write(file, new byte[] {'A'},
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            try (SeekableByteChannel channel = Files.newByteChannel(
                    file,
                    EnumSet.of(
                            StandardOpenOption.WRITE,
                            StandardOpenOption.APPEND))) {
                ByteBuffer buffer = ByteBuffer.wrap(
                        "BC".getBytes(StandardCharsets.US_ASCII));

                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
            }

            Files.write(file, new byte[] {'D'},
                    StandardOpenOption.APPEND);

            System.out.println("Content: "
                    + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 AppendByteChannelDemo.java
java AppendByteChannelDemo
```

**Stdout:**

```text
Content: ABCD
```

Chương trình:

- Tạo file mới với một byte `A`.
- Mở channel ở chế độ `WRITE, APPEND` và thêm hai byte `B`, `C`.
- Lặp khi `ByteBuffer.hasRemaining()` bởi giao diện channel có thể ghi ít byte hơn số byte đang còn trong buffer ở một lần gọi; không được coi một `write` luôn ghi toàn bộ `ByteBuffer`.
- Tiếp tục append byte `D` bằng `Files.write`.
- Đọc file demo nhỏ để xác nhận thứ tự `ABCD`.

**Ghi chú:** `SeekableByteChannel` cho phép thao tác vị trí, nhưng với `APPEND` thì cách ghi được điều khiển theo semantics append; đừng dựa vào `position(0)` để vượt qua ý nghĩa append. Khi cần sửa byte ở một vị trí tùy ý, mở với `READ`/`WRITE` theo một thiết kế khác, không kèm `APPEND`.

## 8. Dùng `Files.newBufferedWriter` khi ghi log văn bản

`newBufferedWriter` cung cấp writer có buffer để hạn chế nhiều thao tác ghi nhỏ. Khi cần append văn bản:

```java
// Đoạn minh họa: logPath là một Path hợp lệ.
try (java.io.BufferedWriter writer =
        java.nio.file.Files.newBufferedWriter(
                logPath,
                java.nio.charset.StandardCharsets.UTF_8,
                java.nio.file.StandardOpenOption.CREATE,
                java.nio.file.StandardOpenOption.APPEND)) {
    writer.write("event=started");
    writer.newLine();
}
```

Lưu ý thực hành:

- `try-with-resources` đóng writer và flush phần dữ liệu còn trong buffer khi đóng thành công; không bỏ quên đóng.
- `newLine()` tạo dấu xuống dòng theo nền tảng; nếu định dạng file yêu cầu LF nhất quán, ghi `"\n"` có chủ đích.
- Nếu nhiều luồng/tiến trình cùng append, buffer có thể gom hoặc chia việc ghi thành nhiều thao tác tới tầng dưới. Không coi một lần `writer.write("record")` là **một bản ghi nguyên tử** trên mọi filesystem.
- `newBufferedWriter` mở writer với charset cụ thể; thêm dữ liệu vào file mang encoding khác có thể tạo file lẫn encoding và khó đọc.
- Nếu chỉ định **`APPEND` mà không `CREATE`**, ứng dụng phải bảo đảm tệp hiện hữu hoặc xử lý lỗi không tìm thấy.
- Không dùng `TRUNCATE_EXISTING` trong cùng chế độ append để “dọn file cũ”: muốn xoay vòng log, phải có quy trình rotation riêng.

### 8.1. Chọn API theo kiểu dữ liệu

| Dữ liệu / yêu cầu | API gợi ý | Điểm cần xem |
| --- | --- | --- |
| Thêm một dòng văn bản ngắn | `Files.writeString` với `UTF_8, CREATE, APPEND` | Separator, encoding, writer khác |
| Thêm nhiều dòng liên tiếp | `Files.newBufferedWriter` với `CREATE, APPEND` | `close`/`flush`, concurrency |
| Thêm các block byte | `Files.newOutputStream` với `CREATE, APPEND` | Định dạng nhị phân, vòng đời stream |
| Cần `ByteBuffer`/channel | `Files.newByteChannel` với `WRITE, APPEND` | Không ghép `READ`/`TRUNCATE_EXISTING` |
| Ghi lại hoàn toàn file cấu hình | `Files.writeString` mặc định hoặc explicit `CREATE, WRITE, TRUNCATE_EXISTING` | Có thể mất bản cũ nếu lỗi giữa chừng |
| Chỉ tạo file mới, tránh file cũ | `CREATE_NEW, WRITE` | Xử lý file đã tồn tại |
| Ghi an toàn kiểu “replace” | Tệp tạm → verify → `Files.move` theo chính sách | `ATOMIC_MOVE` chỉ khi provider hỗ trợ |

`Files.writeString` thuận tiện cho lượng chữ nhỏ/vừa, nhưng không tự hiểu log rotation, locking hay độ dài tối đa của file.

## 9. APPEND khi nhiều thread hoặc tiến trình cùng ghi

### 9.1. “Ghi ở cuối file” không luôn có nghĩa “nguyên tử toàn bản ghi”

`APPEND` giúp vị trí ghi được xác lập ở cuối file theo hợp đồng provider. Tuy nhiên, việc dời vị trí đến EOF và ghi dữ liệu **có diễn ra như một thao tác nguyên tử không** là điều phụ thuộc hệ thống tệp/provider; không được khẳng định áp dụng chung cho mọi thiết bị hoặc mọi kích thước ghi.

Một record log như:

```text
2026-10-27 INFO started
```

có thể được writer chuyển thành một hoặc nhiều lần ghi dưới lớp buffer. Khi nhiều writer chạy đồng thời, phần byte của các record có thể xen kẽ hoặc thứ tự không trùng với thời điểm logic trong chương trình. `APPEND` cũng không ngăn tiến trình khác mở file ở chế độ truncate.

**Các chiến lược thực tế:**

1. Dùng **một writer chuyên trách** cho cùng một tệp log trong một tiến trình, chuyển bản ghi qua queue nếu cần.
2. Nếu có nhiều tiến trình, thống nhất protocol ghi/locking hoặc dùng hệ thống logging có hỗ trợ multi-process; không chỉ dựa vào `APPEND`.
3. Cân nhắc `FileChannel.lock()` trong môi trường hỗ trợ và tổ chức mọi writer cùng tuân thủ lock. File lock có thể phụ thuộc hệ điều hành/provider và không nhất thiết ngăn code bên ngoài không dùng lock.
4. Nếu cần tính nguyên tử giao dịch, hãy chọn kho dữ liệu/transaction phù hợp thay vì coi append file là database transaction.
5. Đo số byte và áp chính sách **file rotation**, retention, quota lưu trữ, thay vì để append làm đầy đĩa.

### 9.2. `APPEND` không bảo đảm thứ tự thông điệp nghiệp vụ

Ngay cả khi filesystem nối byte hợp lệ, nhiều thread có thể chuẩn bị record theo thứ tự khác thứ tự được ghi. Nếu trình tự là quan trọng, serialize ở tầng ứng dụng bằng sequence number hoặc một điểm ghi tuần tự. Đừng suy ra “event A xảy ra trước B” chỉ vì byte trong log xuất hiện trước.

### 9.3. Appending và durability

Với buffer, dữ liệu có thể còn ở heap trước khi flush; sau khi flush, dữ liệu có thể ở cache hệ điều hành; sau khi close, yêu cầu durability vẫn phụ thuộc storage stack. `SYNC`/`DSYNC` hoặc `FileChannel.force(...)` có thể được cân nhắc khi đặc tả yêu cầu ghi bền vững, nhưng **không** thay thế việc xử lý crash recovery, record framing, checksum hoặc writer đồng thời.

## 10. Hạn chế từ filesystem/provider và ngoại lệ

Các tùy chọn `StandardOpenOption` là hợp đồng API phổ biến, nhưng provider quyết định hỗ trợ nhiều chi tiết. Đặc biệt:

- **Tổ hợp không hợp lệ:** `APPEND` với `READ` hoặc `TRUNCATE_EXISTING` trong `newByteChannel` bị từ chối.
- **File thiếu:** chỉ có `APPEND` mà thiếu `CREATE`/`CREATE_NEW` không tự tạo.
- **Không có quyền:** có thể ném `AccessDeniedException` hoặc `IOException` tùy thao tác.
- **File đã tồn tại:** `CREATE_NEW` có thể ném `FileAlreadyExistsException`.
- **Tùy chọn không được hỗ trợ:** `UnsupportedOperationException` hoặc lỗi theo API/provider.
- **Đường dẫn là thư mục:** không phải tệp thường để ghi; việc mở sẽ thất bại.
- **Filesystem read-only, đầy đĩa, quota, mạng chập chờn:** lỗi I/O có thể xảy ra **sau khi một số byte đã ghi**.
- **Filesystem phân tán/network:** tính nguyên tử và khả năng quan sát append có thể khác filesystem cục bộ.
- **Symlink/đường dẫn bị thay thế:** kiểm tra “file này tồn tại” rồi mới mở có nguy cơ time-of-check-to-time-of-use; kiểm soát path theo threat model.

Nếu đang cập nhật tệp quan trọng, không chỉ quan tâm “API có ném lỗi không” mà còn cần biết **trạng thái file sau lỗi**. Append không rollback dữ liệu đã ghi; thay thế file trực tiếp bằng truncate cũng có thể làm hỏng bản cũ nếu thất bại giữa chừng.

## 11. Sai lầm thường gặp

1. **Quên `APPEND` khi ghi log:** `Files.writeString(path, line)` theo mặc định thường thay nội dung cũ bằng nội dung mới.
2. **Cho rằng `APPEND` tự tạo file:** cần `CREATE` nếu muốn file chưa tồn tại vẫn ghi thành công.
3. **Dùng `APPEND` và `TRUNCATE_EXISTING` đồng thời:** mục tiêu mâu thuẫn, tổ hợp không hợp lệ trong byte-channel API.
4. **Dùng `READ` cùng `APPEND` trong một channel:** không hợp lệ theo `Files.newByteChannel`.
5. **Nhầm `WRITE` là append:** `WRITE` đơn thuần không có semantics luôn ghi vào EOF.
6. **Gọi `position(size())` rồi ghi khi nhiều writer:** có nguy cơ race; không đồng nghĩa `APPEND`.
7. **Quên newline:** ghi `"a"` rồi `"b"` bằng append tạo `"ab"`, không tự chia dòng.
8. **Trộn charset:** nối UTF-8 vào file được mã hóa bằng charset khác làm nội dung không nhất quán.
9. **Không đóng writer/stream:** dữ liệu còn nằm trong buffer, tài nguyên có thể bị rò.
10. **Flush mỗi ký tự:** tăng số lời gọi xuống tầng dưới và thường làm giảm throughput.
11. **Coi append là transaction:** không có rollback, không bảo đảm toàn record được ghi nguyên tử trong mọi provider.
12. **Tin rằng `CREATE_NEW` có nghĩa “append nếu file có”:** ngược lại, nó từ chối file đã tồn tại.
13. **Quên xử lý ngoại lệ:** file có thể đã bị ghi một phần khi lỗi I/O xuất hiện.
14. **Không xét tăng trưởng không giới hạn:** appending dài ngày làm log lớn hoặc đầy ổ đĩa.
15. **Dùng `readAllLines` để xử lý toàn bộ file log rất lớn:** có thể tốn nhiều heap; đọc streaming theo dòng hoặc dùng công cụ log phù hợp.
16. **Nhầm cách ghi của API:** `newByteChannel` không có options mặc định khác với `writeString` và `newBufferedWriter`.

## 12. Kiểm thử cần có

Với ứng dụng dùng append, tối thiểu nên kiểm tra:

- **File chưa tồn tại:** `CREATE, APPEND` tạo file thành công; `APPEND` đơn lẻ thất bại theo hợp đồng.
- **File đã tồn tại:** sau hai lần append, nội dung cũ vẫn còn và dữ liệu mới đứng ở cuối.
- **Không truyền options:** `Files.writeString` ghi đè/truncate theo mặc định; tránh vô tình dùng cho log.
- **`CREATE_NEW` trên file đã có:** không được ghi đè.
- **Byte sequence:** append nhị phân giữ thứ tự và kích thước byte đúng.
- **Encoding:** UTF-8 với dấu tiếng Việt/emoji; tệp đích không trộn charset.
- **Newline:** phân biệt file có LF cuối và file không có LF cuối.
- **Nhiều writer:** thử tải đồng thời, kiểm tra số bản ghi, thứ tự khi cần và tình huống file rotate.
- **Lỗi I/O:** hết đĩa/quota, quyền truy cập, đóng stream; đánh giá bản ghi dở và retry để không tạo record trùng.
- **Provider khác nhau:** kiểm chứng nơi chạy thật (ổ đĩa cục bộ, mạng, filesystem ảo) nếu yêu cầu tính nguyên tử hoặc độ bền ghi đặc biệt.

## 13. Bài tập tự luyện

1. Giải thích vì sao `Files.writeString(path, "A")` rồi `Files.writeString(path, "B")` tạo kết quả khác `Files.writeString(path, "A", APPEND)` rồi `Files.writeString(path, "B", APPEND)` khi file đã tồn tại.
2. Viết chương trình tạo `journal.txt` nếu thiếu, mỗi lượt gọi ghi thêm một dòng UTF-8. Xác nhận nếu gọi ba lần, ba dòng cũ/mới vẫn tồn tại.
3. Thử dùng `APPEND` đơn lẻ với file chưa có; bắt và phân loại lỗi. Sửa code bằng `CREATE, APPEND`.
4. Thiết kế test phân biệt `WRITE`, `WRITE + TRUNCATE_EXISTING` và `APPEND` trên cùng nội dung gốc `ABCDEF`.
5. Với `Files.newByteChannel`, giải thích tại sao `APPEND + READ` và `APPEND + TRUNCATE_EXISTING` không hợp lệ. Chọn cách mở riêng cho nhu cầu đọc/ghi.
6. Ghi các byte `{1, 2}` rồi append `{3, 4}`; xác nhận tệp chứa `[1, 2, 3, 4]`, không có byte delimiter tự động.
7. Thử hai thread ghi 1.000 record mỗi thread. Tại sao không được coi một lần test thành công là bằng chứng append nguyên tử trên mọi filesystem?
8. Xây dựng chính sách rotation khi log vượt 10 MiB. Vì sao không chỉ kiểm tra `Files.size` rồi coi đó là bảo đảm chống ghi vượt ngưỡng dưới concurrency?
9. Giải thích khác biệt giữa `flush`, `close`, `SYNC`/`DSYNC` và `FileChannel.force` theo góc độ dữ liệu đi xuống tầng lưu trữ; lựa chọn cần dựa vào yêu cầu độ bền ghi và provider.
10. Nếu một lần ghi append báo lỗi sau khi một nửa record đã vào file, cơ chế retry mù quáng có thể gây lỗi gì? Đề xuất framing, checksum, sequence number hoặc hệ thống ghi chuyên dụng khi cần tính nhất quán.

## 14. Tổng kết

- `APPEND` là lựa chọn **ghi thêm ở cuối file**; nó không xóa nội dung cũ và cũng không tự thêm dòng, tự tạo file hay xử lý concurrent writers.
- `CREATE, APPEND` thường là lựa chọn phù hợp để viết file log và tạo mới nếu thiếu; `CREATE_NEW` lại chủ động **từ chối** file đã tồn tại.
- Các phương thức ghi `Files.writeString`, `Files.write`, `newBufferedWriter`, `newOutputStream` mặc định **tạo và truncate** nếu không đưa options; đừng quên quy tắc này.
- `Files.newByteChannel` có mặc định khác (đọc) và nghiêm cấm những kết hợp `APPEND + READ`, `APPEND + TRUNCATE_EXISTING`.
- `WRITE` riêng lẻ không đồng nghĩa append; `TRUNCATE_EXISTING` là hành động cắt nội dung cũ và không đi kèm mục tiêu append.
- Với hệ thống cần nhiều writer, durability, quota hay transaction, phải thiết kế **đồng bộ và xử lý lỗi ở tầng ứng dụng**, không đặt mọi kỳ vọng vào `APPEND`.

**Cách chọn an toàn:** Hỏi rõ chương trình định *tạo mới*, *ghi đè* hay *nối thêm*. Sau đó chọn tổ hợp `OpenOption` nhất quán, xác định hành vi khi file tồn tại/chưa tồn tại, đóng tài nguyên đúng cách và kiểm thử trên chính filesystem sẽ triển khai.