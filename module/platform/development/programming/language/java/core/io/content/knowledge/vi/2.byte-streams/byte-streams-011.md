# `InputStream.nullInputStream()`, `OutputStream.nullOutputStream()` và tình huống sử dụng

## Mục tiêu

Trong Java I/O, đôi khi chương trình cần một nguồn byte **chủ động không có dữ liệu** hoặc một đích ghi **chủ động bỏ qua mọi byte nhận được**. Java cung cấp sẵn hai factory method:

- `InputStream.nullInputStream()`: tạo một `InputStream` rỗng, ở trạng thái EOF ngay từ đầu.
- `OutputStream.nullOutputStream()`: tạo một `OutputStream` nhận thao tác ghi nhưng **loại bỏ** các byte, không lưu hay chuyển chúng đến tệp, bộ nhớ hoặc mạng.

Cả hai API xuất hiện từ **Java 11** và dùng trực tiếp được trong Java 17+. Bài học phân biệt chúng với tham chiếu Java `null`, giải thích hành vi khi mở/đóng luồng, cung cấp ví dụ chạy được và chỉ ra lúc nên hoặc không nên sử dụng.

## 1. “Null stream” không có nghĩa là một biến bằng `null`

Hai cách khai báo dưới đây hoàn toàn khác nhau:

```java
InputStream missing = null;                    // Không có đối tượng nào.
InputStream empty = InputStream.nullInputStream(); // Có đối tượng InputStream hợp lệ.
```

Gọi `missing.read()` sẽ gây `NullPointerException`. Với `empty`, phương thức `read()` có hành vi bình thường của một nguồn đã đến cuối dữ liệu: trả về `-1` (trong khi luồng còn mở).

Tương tự:

```java
OutputStream missing = null;
OutputStream discard = OutputStream.nullOutputStream();
```

`missing.write(65)` gây `NullPointerException`; `discard.write(65)` được chấp nhận khi luồng còn mở, nhưng byte `65` không được lưu ở đâu cả.

Tên “null” ở đây diễn tả **nguồn rỗng** hoặc **đích bỏ dữ liệu**, không phải tham chiếu rỗng. Hai factory method trả về những đối tượng thật triển khai đúng hợp đồng của `InputStream` và `OutputStream`.

## 2. `InputStream.nullInputStream()`: luồng byte rỗng, EOF tức thì

Chữ ký API:

```java
public static InputStream nullInputStream()
```

Khi **chưa đóng**, luồng này không chứa byte nào:

| Thao tác | Kết quả có ý nghĩa |
| --- | --- |
| `read()` | Trả về `-1` (EOF). |
| `read(byte[])` hoặc `read(byte[], off, len)` | Với yêu cầu đọc có độ dài dương: EOF, thường biểu diễn bằng `-1`; yêu cầu đọc 0 byte trả `0`. |
| `available()` | Trả `0`. |
| `readAllBytes()` | Trả về mảng byte rỗng. |
| `readNBytes(n)` | Không có byte để đọc; kết quả là mảng rỗng khi `n >= 0`. |
| `skip(n)` | Không bỏ qua byte nào: trả `0` với `n > 0`. |
| `transferTo(out)` | Không chuyển byte nào: trả `0`, miễn tham số đích hợp lệ. |
| `markSupported()` | Trả `false`; `mark()` không có tác dụng, `reset()` ném `IOException`. |

**EOF không phải lỗi.** Khi chưa đóng, kết quả `read() == -1` nghĩa là nguồn đã hết dữ liệu theo hợp đồng đọc stream. Nó không có nghĩa là “đang chờ mạng” hay “chưa nhận được dữ liệu”. Một `InputStream` khác có thể trả `available() == 0` mà vẫn chưa EOF; riêng `nullInputStream()` cố ý diễn tả dữ liệu đã kết thúc.

### Ví dụ đầy đủ: nguồn rỗng

Tạo tệp **`NullInputDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;

public class NullInputDemo {
    public static void main(String[] args) throws IOException {
        try (InputStream in = InputStream.nullInputStream()) {
            System.out.println("available = " + in.available());
            System.out.println("read = " + in.read());
            System.out.println("bytes = " + in.readAllBytes().length);
            System.out.println("skip = " + in.skip(10));
            System.out.println("mark supported = " + in.markSupported());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac NullInputDemo.java
java NullInputDemo
```

Kết quả chính xác:

```text
available = 0
read = -1
bytes = 0
skip = 0
mark supported = false
```

Ở chương trình này, `available() == 0` đi cùng EOF vì **loại nguồn cụ thể** là `nullInputStream()`. Không suy rộng điều đó sang socket, pipe hay mọi kiểu `InputStream`.

## 3. `OutputStream.nullOutputStream()`: nhận ghi nhưng không giữ byte

Chữ ký API:

```java
public static OutputStream nullOutputStream()
```

Khi **chưa đóng**, các thao tác `write(int)`, `write(byte[])` và `write(byte[], off, len)` không tạo đầu ra. Byte đã gửi vào bị bỏ đi. `flush()` không có công việc cần làm, vì không có dữ liệu đệm để đẩy ra tệp hay thiết bị.

### Ví dụ đầy đủ: ghi thành công nhưng không tạo kết quả lưu trữ

Tạo tệp **`NullOutputDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class NullOutputDemo {
    public static void main(String[] args) throws IOException {
        try (OutputStream out = OutputStream.nullOutputStream()) {
            byte[] message = "Hello, Java".getBytes(StandardCharsets.UTF_8);
            out.write(message);
            out.write('!');
            out.flush();
            System.out.println("write operations completed");
        }
        System.out.println("no payload was stored");
    }
}
```

Biên dịch và chạy:

```bash
javac NullOutputDemo.java
java NullOutputDemo
```

Kết quả chính xác:

```text
write operations completed
no payload was stored
```

`System.out.println(...)` vẫn hiển thị ở console vì đoạn mã ghi trực tiếp lên `System.out`. Chỉ các byte được gửi tới đối tượng `out` từ `nullOutputStream()` mới bị bỏ đi.

**Lưu ý về hiệu năng:** việc ghi vào đích này không thực hiện I/O lưu trữ thực tế. Tuy nhiên, mọi công việc *trước khi ghi* (tạo dữ liệu, mã hóa, nén, tính toán, đọc nguồn) vẫn có thể tốn thời gian và bộ nhớ. Vì thế, “không có đầu ra” không có nghĩa toàn bộ pipeline miễn phí.

## 4. Đóng luồng rồi thì sao?

Hai factory method đều trả về stream **đang mở**. `close()` đặt chúng vào trạng thái đóng; gọi `close()` thêm lần nữa không có tác dụng.

- **`InputStream.nullInputStream()`:** sau khi đóng, các phương thức I/O như `read()`, `available()`, `readAllBytes()`, `skip()` và `transferTo()` ném `IOException`. Kết quả `-1` chỉ mô tả luồng rỗng **khi còn mở**. `reset()` cũng ném `IOException`; `markSupported()` vẫn không hỗ trợ đánh dấu.
- **`OutputStream.nullOutputStream()`:** sau khi đóng, các thao tác `write(...)` ném `IOException`. Theo đặc tả của factory này, `flush()` vẫn là thao tác không làm gì, kể cả khi không có dữ liệu cần đẩy ra; không nên dùng `flush()` để xác nhận stream còn mở.
- **`try-with-resources`:** cách thường dùng để bảo đảm gọi `close()` đúng lúc, nhất là khi cùng một hàm có thể nhận một stream thật thay cho null stream.

### Kiểm chứng ngoại lệ sau khi đóng

Tạo tệp **`ClosedNullStreamsDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class ClosedNullStreamsDemo {
    public static void main(String[] args) throws IOException {
        InputStream in = InputStream.nullInputStream();
        in.close();
        in.close(); // Đóng lại vẫn hợp lệ.

        try {
            in.read();
        } catch (IOException e) {
            System.out.println("closed input: IOException");
        }

        OutputStream out = OutputStream.nullOutputStream();
        out.close();
        out.close(); // Đóng lại vẫn hợp lệ.

        try {
            out.write(42);
        } catch (IOException e) {
            System.out.println("closed output: IOException");
        }
    }
}
```

Chạy:

```bash
javac ClosedNullStreamsDemo.java
java ClosedNullStreamsDemo
```

Kết quả:

```text
closed input: IOException
closed output: IOException
```

Phân biệt **“rỗng”** với **“đã đóng”**: một luồng rỗng đang mở vẫn xử lý thao tác đọc hợp lệ bằng EOF; luồng đã đóng không còn cho phép đọc/ghi như trên.

## 5. Những tình huống sử dụng thực tế

### Tình huống A: tham số `InputStream` tùy chọn, muốn biểu diễn “không có dữ liệu”

Một API nhận `InputStream` không nhất thiết cần dữ liệu trong mọi trường hợp. Khi nghiệp vụ **thật sự cho phép đầu vào rỗng**, có thể thay `null` bằng stream rỗng để thuật toán xử lý thống nhất:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class OptionalInputDemo {
    static String readText(InputStream in) throws IOException {
        return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        try (InputStream empty = InputStream.nullInputStream()) {
            String text = readText(empty);
            System.out.println("text length = " + text.length());
        }
    }
}
```

Chạy `javac OptionalInputDemo.java` rồi `java OptionalInputDemo`:

```text
text length = 0
```

Cách này phù hợp khi “không có nội dung” là một giá trị nghiệp vụ hợp lệ, chẳng hạn body tùy chọn trong luồng xử lý dữ liệu. **Không tự thay dữ liệu bắt buộc bị thiếu bằng `nullInputStream()`**, vì sẽ che giấu lỗi và khiến ứng dụng nhầm là đã đọc một đầu vào rỗng hợp lệ.

### Tình huống B: chạy pipeline đầy đủ nhưng chủ động bỏ đầu ra

Khi cần kiểm tra việc *đọc, giải mã, nén hoặc chuyển dữ liệu* mà không muốn tạo tệp kết quả, có thể nối pipeline vào `OutputStream.nullOutputStream()`.

Tạo tệp **`DiscardTransferDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class DiscardTransferDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "Java I/O".getBytes(StandardCharsets.UTF_8);

        try (InputStream source = new ByteArrayInputStream(payload);
             OutputStream sink = OutputStream.nullOutputStream()) {
            long consumed = source.transferTo(sink);
            System.out.println("bytes consumed = " + consumed);
            System.out.println("next read = " + source.read());
        }
    }
}
```

Chạy:

```bash
javac DiscardTransferDemo.java
java DiscardTransferDemo
```

Kết quả:

```text
bytes consumed = 8
next read = -1
```

**Diễn giải:** `InputStream.transferTo(out)` đọc từ nguồn cho đến EOF, ghi các byte đã đọc vào `out` và trả về số byte được chuyển. Ở đây tám byte đã đi qua pipeline nên nguồn bị tiêu thụ; sink bỏ chúng đi. `consumed == 8` **không chứng minh có tám byte được lưu trên đĩa**.

Dùng cách này để kiểm thử logic đọc dữ liệu hoặc đo một phần chi phí xử lý là hợp lý, nhưng phép đo không phản ánh chi phí thực tế của việc ghi tệp hay truyền mạng.

### Tình huống C: bộ kiểm thử cần nguồn rỗng hoặc sink bỏ qua kết quả

- Đưa `InputStream.nullInputStream()` vào hàm parse để thử trường hợp file rỗng và xem hàm trả kết quả rỗng hay báo định dạng thiếu dữ liệu.
- Đưa `OutputStream.nullOutputStream()` vào hàm xuất báo cáo khi bài kiểm thử chỉ kiểm tra luồng xử lý, số bản ghi, số byte đã chuyển hoặc hành vi exception.
- Khi cần **khẳng định nội dung byte đã ghi chính xác**, phải dùng `ByteArrayOutputStream` hoặc đích có thể đọc lại. Sink bỏ dữ liệu không hỗ trợ assert trên payload.

Ví dụ thiết kế hàm cho phép đưa đầu ra từ bên ngoài:

```java
static void exportBytes(byte[] payload, java.io.OutputStream out)
        throws java.io.IOException {
    out.write(payload);
}
```

Đây là **đoạn mã minh họa phương thức**, không phải chương trình chạy độc lập. Người gọi có thể truyền `OutputStream.nullOutputStream()` khi có chủ ý bỏ đầu ra, hoặc `ByteArrayOutputStream` khi cần giữ lại dữ liệu để kiểm tra.

### Tình huống D: cung cấp triển khai mặc định rõ nghĩa cho một nhánh tùy chọn

Giả sử thành phần có `boolean shouldPersist`: chỉ khi `shouldPersist` đúng mới cần ghi ra file. Có thể chọn đầu ra theo điều kiện:

```java
// Đoạn mã minh họa, giả định biến target kiểu Path và shouldPersist đã có.
try (OutputStream out = shouldPersist
        ? java.nio.file.Files.newOutputStream(target)
        : OutputStream.nullOutputStream()) {
    produceReport(out);
}
```

`produceReport(OutputStream)` là phương thức của ứng dụng và chưa được định nghĩa trong snippet. Khi nhánh lưu tệp được chọn, cần xử lý đúng đường dẫn, quyền ghi và lỗi I/O. Nếu đầu ra là yêu cầu bắt buộc, chọn `nullOutputStream()` khi lỗi mở tệp **không phải** cách xử lý đúng: lỗi cần được báo cho người gọi.

## 6. So sánh với các lựa chọn thường gặp

| Lựa chọn | Có byte để đọc/ghi? | Có giữ được dữ liệu? | Phù hợp khi |
| --- | --- | --- | --- |
| `InputStream.nullInputStream()` | Đọc luôn EOF | Không có dữ liệu nguồn | Muốn biểu diễn đầu vào rỗng hợp lệ. |
| `new ByteArrayInputStream(new byte[0])` | Đọc luôn EOF | Đã có một mảng byte rỗng | Cần nguồn mảng, có thể mở rộng bằng dữ liệu byte thật. |
| `OutputStream.nullOutputStream()` | Chấp nhận ghi khi còn mở rồi bỏ byte | Không | Muốn tiêu thụ kết quả nhưng không lưu. |
| `ByteArrayOutputStream` | Chấp nhận ghi | Có, trong RAM | Kiểm tra, chuyển đổi hoặc thu thập payload để đọc lại. |
| `Files.newOutputStream(path)` | Chấp nhận ghi ra một tệp | Có, trên filesystem khi thành công | Cần lưu kết quả vào tệp. |

Các kiểu có thể cùng dùng một interface nhưng sở hữu ngữ nghĩa khác nhau. Vì thế, chọn chúng theo **mục đích giữ hay bỏ dữ liệu**, không chỉ vì chúng đều biên dịch được.

## 7. Cạm bẫy và giới hạn

1. **Đừng dùng luồng rỗng để hợp thức hóa thiếu dữ liệu.** Nếu hợp đồng yêu cầu file thật hoặc payload bắt buộc, hãy từ chối input thiếu thay vì trả kết quả rỗng âm thầm.
2. **Đừng hiểu tên `nullOutputStream` là “không bao giờ lỗi”.** Việc ghi vào stream đã đóng sẽ ném `IOException`; các bước *trước khi ghi* vẫn có thể ném ngoại lệ từ chính chúng.
3. **Đừng kỳ vọng sink lưu hay phát lại nội dung.** Không thể khôi phục các byte đã ghi vào `nullOutputStream()`; để kiểm tra nội dung phải sử dụng sink có lưu trữ.
4. **Đừng nhầm số byte đã xử lý với byte đã lưu.** Số byte từ `transferTo` đo lượng dữ liệu được chuyển qua lời gọi, kể cả khi đích bỏ dữ liệu.
5. **Đừng nhầm `available() == 0` của null input với quy tắc EOF chung.** Với network stream, `available() == 0` có thể chỉ là tạm thời không có byte sẵn. Quy tắc EOF chung vẫn là kiểm tra kết quả của thao tác `read()`.
6. **Đừng dùng null sink để đánh giá thông lượng tệp/mạng.** Loại bỏ công đoạn lưu/truyền sẽ làm phép đo khác tình huống thực tế; ghi rõ mình đo phần nào của pipeline.
7. **Phân biệt quyền sở hữu stream.** Hàm nhận `InputStream` từ bên ngoài thường không nên tự ý `close()` nếu hợp đồng cho người gọi sở hữu; với stream tạo nội bộ, `try-with-resources` là lựa chọn mặc định hợp lý.
8. **Quan tâm kích thước và giới hạn xử lý.** Bỏ kết quả không giới hạn lượng dữ liệu nguồn phải đọc; với nguồn lớn hoặc do người dùng gửi, vẫn cần giới hạn tài nguyên/timeout đúng loại nguồn.

## 8. Câu hỏi tự kiểm tra

**1. `InputStream.nullInputStream()` có tương đương khai báo `InputStream in = null` không?**

Không. Nó là một đối tượng stream hợp lệ. Khi chưa đóng, `in.read()` trả `-1` thay vì gây `NullPointerException`.

**2. Ghi 1 MiB vào `OutputStream.nullOutputStream()` thành công có đồng nghĩa tạo ra tệp 1 MiB không?**

Không. Dữ liệu đã bị loại bỏ. Không có tệp, không có buffer lưu nội dung được tạo bởi factory này.

**3. Sau khi `close()` một null input stream, `read()` trả `-1` hay ném ngoại lệ?**

Ném `IOException`. Giá trị `-1` là EOF của null input **còn mở**.

**4. Vì sao `InputStream.nullInputStream()` không thay thế được việc kiểm tra dữ liệu đầu vào bắt buộc?**

Vì stream rỗng luôn hợp lệ về mặt I/O và có thể khiến logic xử lý nhầm thiếu dữ liệu thành “file rỗng” theo nghiệp vụ. Nếu dữ liệu phải tồn tại thì nên báo lỗi rõ ràng.

**5. Khi nào nên dùng `ByteArrayOutputStream` thay `OutputStream.nullOutputStream()`?**

Khi cần đọc lại, so sánh hoặc khẳng định nội dung đã ghi. `nullOutputStream()` chỉ phù hợp khi chủ động bỏ nội dung.

## 9. Tài liệu tra cứu

- Java 17 API: [`InputStream.nullInputStream()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#nullInputStream()).
- Java 17 API: [`OutputStream.nullOutputStream()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html#nullOutputStream()).

**Ghi nhớ:** `nullInputStream()` là *đầu vào hợp lệ nhưng rỗng*; `nullOutputStream()` là *đầu ra hợp lệ nhưng cố ý bỏ byte*. Hai API giúp biểu diễn ý định rõ ràng ở các nhánh tùy chọn và trong kiểm thử. Chúng không thay thế dữ liệu bắt buộc, cơ chế ghi thật hoặc xử lý lỗi I/O.
