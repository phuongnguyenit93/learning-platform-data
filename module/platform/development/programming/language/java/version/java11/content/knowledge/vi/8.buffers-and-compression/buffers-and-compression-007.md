# Vòng lặp xử lý khi chưa có đủ đầu vào hoặc đầu ra khi nén và giải nén

## 1. Bản chất của vấn đề

Khi làm việc với `ByteBuffer`, `java.util.zip.Deflater` và `java.util.zip.Inflater`, **một lần gọi `deflate()` hoặc `inflate()` không bảo đảm xử lý hết dữ liệu**. Dữ liệu đầu vào có thể đến từng khối, trong khi bộ đệm đầu ra có kích thước giới hạn. Ví dụ, đầu ra cần 8.000 byte nhưng buffer chỉ chứa 128 byte, nên chương trình phải tiêu thụ 128 byte đã tạo rồi tiếp tục xử lý.

Từ Java 11, `Deflater` và `Inflater` hỗ trợ trực tiếp `ByteBuffer` qua các overload `setInput(ByteBuffer)`, `deflate(ByteBuffer)`, `inflate(ByteBuffer)`. Những API này vẫn có trong JDK hiện đại. Quy tắc điều khiển vòng lặp cũng áp dụng với các overload dùng `byte[]`.

Cần phân biệt rõ **ba điều kiện**: bộ nén/giải nén đang thiếu input, buffer output không đủ chỗ, và toàn bộ luồng nén thực sự kết thúc. Không được dùng kết quả trả về `0` của một lần gọi làm tín hiệu kết thúc duy nhất.

## 2. Các trạng thái quyết định hành động

| Điều kiện | Ý nghĩa | Hành động |
| --- | --- | --- |
| `deflater.needsInput()` | Bộ nén đã tiêu thụ phần input được cung cấp | Nếu nguồn còn dữ liệu thì cấp khối kế tiếp; nếu đã biết EOF, gọi `finish()` theo đúng thời điểm. |
| `deflater.finished()` | Đã nén xong sau tín hiệu `finish()` và xuất hết kết quả | Dừng vòng lặp nén. |
| `inflater.needsInput()` | Bộ giải nén không còn byte nén đang chờ | Cấp thêm byte nén nếu còn nguồn; nếu EOF thực sự nhưng chưa `finished()`, xử lý như luồng nén chưa hoàn chỉnh. |
| `inflater.needsDictionary()` | Luồng nén yêu cầu từ điển định sẵn | Cung cấp đúng từ điển hoặc báo lỗi không hỗ trợ. |
| `inflater.finished()` | Đã gặp điểm kết thúc hợp lệ của luồng nén | Dừng vòng lặp giải nén; xét byte dư nếu giao thức cần. |
| `produced > 0` | Lần gọi hiện tại đã ghi `produced` byte kết quả | Tiêu thụ chính xác số byte đó, dọn output rồi gọi tiếp khi cần. |
| `produced == 0` | Lần gọi hiện tại chưa tạo byte kết quả | Kiểm tra các trạng thái trên, dung lượng buffer và khả năng tiến triển; **không lặp vô hạn**. |

**`needsInput()` không có nghĩa nguồn ngoài đã kết thúc.** Nó chỉ diễn tả phần dữ liệu đã cấp cho đối tượng nén/giải nén không còn đủ. Nếu một socket đang chờ dữ liệu mới, cần chờ hoặc quay về event loop, thay vì gọi `inflate()` liên tiếp trên cùng trạng thái.

Tương tự, `finished()` mới là điều kiện hoàn tất thực sự. Một lần nhận đủ số byte làm đầy output không chứng tỏ input đã được xử lý hết.

## 3. Cơ chế `ByteBuffer`: `clear()`, `flip()` và tiêu thụ dữ liệu

Khi dùng `deflate(ByteBuffer)` hoặc `inflate(ByteBuffer)`, buffer kết quả ở **chế độ ghi**:

1. `output.clear()` đặt lại `position = 0`, `limit = capacity` để chuẩn bị chỗ ghi. Chỉ làm việc này **sau khi** dữ liệu kết quả cũ đã được tiêu thụ; `clear()` không tự xóa bộ nhớ hay gửi dữ liệu.
2. `int n = inflater.inflate(output)` hoặc `deflater.deflate(output)` ghi tối đa `output.remaining()` byte và làm tăng `position` theo số byte thực sự tạo. `n` cho biết số byte kết quả lần này.
3. `output.flip()` đặt `limit` thành vị trí cuối dữ liệu vừa ghi và đưa `position` về 0, giúp đọc đúng vùng kết quả.
4. Đọc/ghi hết các byte nằm trong vùng `position..limit`, rồi mới chuẩn bị lần ghi tiếp theo.

Nếu đầu ra được ghi sang một channel mà `channel.write(output)` chỉ nhận **một phần** dữ liệu, phải giữ lại phần chưa ghi. Gọi `clear()` quá sớm sẽ làm mất dữ liệu. Có thể tiếp tục ghi cho đến khi `!output.hasRemaining()`; một pipeline phức tạp hơn có thể dùng `compact()` để bảo toàn những byte chưa tiêu thụ.

Với `setInput(ByteBuffer)`, `Deflater` và `Inflater` tăng `position` của **input buffer** theo số byte đã dùng. Không được tùy tiện đổi nội dung, `position` hoặc `limit` của buffer này trong lúc tác vụ đang dùng nó. Khi nạp theo khối, chỉ cấp khối tiếp theo khi `needsInput()` thích hợp.

## 4. Ví dụ Java 11+ chạy được: input 3 byte, output 5–7 byte

Ví dụ này cố ý dùng buffer cực nhỏ để thể hiện nhu cầu lặp lại. Bộ nén `Deflater` nhận input đầy đủ nhưng chỉ có output 7 byte. Bộ giải nén `Inflater` nhận dữ liệu nén theo từng khối tối đa 3 byte và trả output vào buffer 5 byte. Hai phía dùng định dạng **zlib mặc định** tương thích nhau.

Tạo tệp **`CompressionBufferLoopDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

public class CompressionBufferLoopDemo {
    public static void main(String[] args) throws Exception {
        String text = "Java11-".repeat(16);
        byte[] original = text.getBytes(StandardCharsets.UTF_8);

        byte[] compressed = compress(original);
        byte[] restored = decompress(compressed);

        System.out.println("originalBytes=" + original.length);
        System.out.println("compressedNonEmpty=" + (compressed.length > 0));
        System.out.println("roundTrip=" + Arrays.equals(original, restored));
        System.out.println("prefix=" +
                new String(restored, StandardCharsets.UTF_8).substring(0, 14));
    }

    private static byte[] compress(byte[] data) {
        Deflater deflater = new Deflater();
        try {
            deflater.setInput(ByteBuffer.wrap(data));
            deflater.finish(); // Ví dụ đã cấp toàn bộ dữ liệu nguồn.

            ByteArrayOutputStream sink = new ByteArrayOutputStream();
            ByteBuffer output = ByteBuffer.allocate(7);

            while (!deflater.finished()) {
                output.clear();
                int produced = deflater.deflate(output);

                if (produced == 0 && !deflater.finished()) {
                    throw new IllegalStateException(
                            "Deflater không tiến triển sau finish()");
                }

                output.flip();
                byte[] part = new byte[output.remaining()];
                output.get(part);
                sink.writeBytes(part);
            }
            return sink.toByteArray();
        } finally {
            deflater.end();
        }
    }

    private static byte[] decompress(byte[] compressed)
            throws DataFormatException, EOFException {
        Inflater inflater = new Inflater();
        try {
            ByteArrayOutputStream sink = new ByteArrayOutputStream();
            ByteBuffer output = ByteBuffer.allocate(5);
            int nextInputOffset = 0;

            while (!inflater.finished()) {
                if (inflater.needsDictionary()) {
                    throw new IllegalStateException(
                            "Luồng nén yêu cầu từ điển");
                }

                if (inflater.needsInput()) {
                    if (nextInputOffset == compressed.length) {
                        throw new EOFException(
                                "Hết input trước khi giải nén hoàn tất");
                    }

                    int length = Math.min(
                            3, compressed.length - nextInputOffset);
                    ByteBuffer fragment = ByteBuffer.wrap(
                            compressed, nextInputOffset, length);
                    inflater.setInput(fragment);
                    nextInputOffset += length;
                }

                output.clear();
                long bytesReadBefore = inflater.getBytesRead();
                int produced = inflater.inflate(output);

                if (produced > 0) {
                    output.flip();
                    byte[] part = new byte[output.remaining()];
                    output.get(part);
                    sink.writeBytes(part);
                    continue;
                }

                if (inflater.finished()) {
                    break;
                }
                if (inflater.needsDictionary()) {
                    throw new IllegalStateException(
                            "Thiếu từ điển giải nén");
                }
                if (inflater.needsInput()) {
                    continue; // Vòng lặp sau cấp thêm input.
                }
                if (inflater.getBytesRead() > bytesReadBefore) {
                    continue; // Có tiêu thụ input dù chưa tạo output.
                }
                throw new IllegalStateException(
                        "Inflater không tiến triển");
            }
            return sink.toByteArray();
        } finally {
            inflater.end();
        }
    }
}
```

Lệnh biên dịch và chạy (JDK 17+; mã chỉ sử dụng API từ Java 11):

```bash
javac CompressionBufferLoopDemo.java
java CompressionBufferLoopDemo
```

**Stdout chính xác:**

```text
originalBytes=112
compressedNonEmpty=true
roundTrip=true
prefix=Java11-Java11-
```

Chuỗi `"Java11-"` dài 7 byte UTF-8, lặp 16 lần thành **112 byte**. Dữ liệu sau giải nén bằng đúng byte nguồn nên `roundTrip=true`. Độ dài compressed phụ thuộc thuật toán/cấu hình và không được giả định cố định, vì vậy ví dụ chỉ xác nhận có output nén.

**Vòng lặp nén:** sau `setInput` và `finish`, `deflate(output)` chỉ ghi được tối đa 7 byte. Chương trình `flip()`, lấy đúng byte đã tạo, ghi vào `ByteArrayOutputStream`, rồi `clear()` cho lần sau, đến khi `deflater.finished()`. Cờ `finish()` là tín hiệu rằng **không có thêm input**; nó không có nghĩa lần gọi ngay sau đó chắc chắn đủ chỗ chứa mọi output.

**Vòng lặp giải nén:** nếu `inflater.needsInput()` và vẫn còn byte nén, chương trình cấp thêm một mảnh tối đa 3 byte. Mỗi lần `inflate(output)` có thể tạo tối đa 5 byte; nếu có kết quả, nó được tiêu thụ rồi mới gọi tiếp. Nếu chưa `finished()` mà input đã thực sự hết, ví dụ ném `EOFException`. Nếu luồng đòi từ điển chưa được cấp, ví dụ báo lỗi rõ ràng. Nếu không có output, không cần input mới và cũng không tiêu thụ input, ví dụ coi đó là trạng thái không tiến triển thay vì lặp mãi.

`ByteArrayOutputStream` trong chương trình chỉ giúp thu kết quả để so sánh. Với dữ liệu lớn, nên chuyển các `part` sang stream/channel đích từng khối, có giới hạn dung lượng.

## 5. Khi chưa có đủ input

`Inflater.needsInput()` cho biết input đã cấp cho inflater hết; lúc này phải quyết định dựa trên **nguồn dữ liệu thật**:

- Nguồn còn byte: đọc thêm rồi `setInput(...)`.
- Nguồn bất đồng bộ hiện chưa có dữ liệu: đợi event có thể đọc tiếp, không gọi `inflate()` liên tục.
- Nguồn đã EOF và `finished()==false`: nếu đang giải mã một luồng zlib phải hoàn chỉnh, báo dữ liệu nén bị thiếu/cắt cụt.
- Luồng yêu cầu từ điển (`needsDictionary()==true`): cấp từ điển khớp với bên nén; đọc thêm input đơn thuần không giải quyết điều kiện này.

Phân biệt giá trị trả về từ nguồn I/O: `-1` ở `InputStream.read` thể hiện cuối luồng; trong `SocketChannel` chế độ không chặn, một lần `read(ByteBuffer)` có thể trả `0` vì **chưa đọc được byte nào**, không phải EOF. Cần theo hợp đồng của API cụ thể và mô hình I/O của chương trình.

Nếu sử dụng input `ByteBuffer` có thể tái sử dụng, phải xử lý các byte chưa tiêu thụ đúng cách, không ghi đè chúng trước khi bộ giải nén xong. Ví dụ dùng `ByteBuffer.wrap(compressed, nextInputOffset, length)` cho từng mảnh và không tái sử dụng vùng đó cho mục đích khác.

## 6. Khi chưa có đủ output

Nếu `inflate(output)` tạo `n > 0` byte rồi đầy buffer, **đó là một kết quả hợp lệ**. Dữ liệu nén chưa chắc đã hết. Tiêu thụ đúng số byte vừa tạo, làm mới vùng đầu ra và tiếp tục gọi `inflate()`.

Ví dụ logic minh họa (đã bỏ qua phần nhập input và xử lý từ điển nên **không phải chương trình độc lập**):

```java
output.clear();
int n = inflater.inflate(output);
if (n > 0) {
    output.flip();
    while (output.hasRemaining()) {
        consumeOneByte(output.get()); // Hàm ứng dụng tự định nghĩa.
    }
}
```

`consumeOneByte` không thuộc JDK; trong chương trình chạy được bên trên, việc tiêu thụ được thực hiện bằng `output.get(part)` và `sink.writeBytes(part)`.

Nếu destination là channel có thể chỉ ghi một phần, **không gọi `clear()` khi output còn `hasRemaining()`**. Hãy tiếp tục ghi hoặc giữ phần còn lại bằng `compact()` theo thiết kế pipeline. Bộ đệm có `capacity == 0` hay `remaining() == 0` không thể nhận output mới, nên không thể tạo tiến triển chỉ bằng cách gọi mãi `deflate`/`inflate`.

## 7. Nén streaming: đợi input và gọi `finish()` đúng thời điểm

Khi nén từ một nguồn đang đọc dần:

1. Nếu `deflater.needsInput()` và nguồn còn dữ liệu, lấy khối kế tiếp qua `setInput(...)`.
2. Sau mỗi lần `deflate(...)`, chuyển `n` byte đã tạo ra nơi nhận và tiếp tục.
3. Nếu nguồn tạm thời chưa có dữ liệu, đợi nguồn; **không busy loop**.
4. Khi nguồn **thực sự EOF** và đã cung cấp toàn bộ input, gọi `deflater.finish()` đúng một lần.
5. Tiếp tục lấy output sau `finish()` cho tới `deflater.finished()`.

Không được gọi `finish()` ngay sau khối đầu tiên nếu ứng dụng còn có thể cung cấp khối tiếp. `needsInput()==true` không đồng nghĩa với “đã đạt cuối input toàn bộ”. Với luồng đang truyền liên tục, chế độ flush (`NO_FLUSH`, `SYNC_FLUSH`, `FULL_FLUSH`) còn ảnh hưởng đến thời điểm byte nén được xuất ra; nên dùng `NO_FLUSH` mặc định nếu không có yêu cầu cụ thể để nhận dữ liệu kịp thời.

Các overload dùng `byte[]` có cùng ý tưởng điều khiển: `int n = deflater.deflate(buffer)` hoặc `int n = inflater.inflate(buffer)`; chỉ xử lý đoạn `buffer[0..n)`, lặp cho tới trạng thái hoàn tất hoặc cho tới khi cần nguồn mới. Không thể suy ra nén/giải nén xong từ điều kiện `n < buffer.length`.

## 8. Phát hiện và xử lý trạng thái không tiến triển

Đoạn mã sau **cố ý sai**:

```java
while (!inflater.finished()) {
    inflater.inflate(output);
}
```

Nếu input đã hết, output không còn chỗ, hoặc thiếu từ điển, vòng lặp có thể chạy liên tục mà không tiến triển. Một cơ chế an toàn cần kiểm tra:

1. **Output:** có tạo byte mới không (`n > 0`)? Nếu có, xử lý chúng.
2. **Hoàn tất:** `finished()` đã đúng chưa?
3. **Từ điển:** `needsDictionary()` đúng chưa? Có thể cấp đúng từ điển không?
4. **Input:** `needsInput()` đúng chưa? Nguồn có byte tiếp theo hay đã EOF?
5. **Tiến triển:** nếu `n == 0` mà các trạng thái trên không quyết định được, có thực sự tiêu thụ input hay đổi trạng thái không? Có thể theo dõi `getBytesRead()` và `getBytesWritten()` (kiểu `long`). Không được tiếp tục vô hạn khi mọi thứ đứng yên.

Trong một ứng dụng bất đồng bộ, “đợi input” thường có nghĩa nhường quyền cho event loop hoặc chờ readiness; không nên gọi `Thread.sleep` liên tục như cách sửa kiến trúc vòng lặp. Cần báo lỗi minh bạch khi stream bị cắt cụt/hỏng hoặc khi thuật toán yêu cầu dữ liệu không sẵn có.

## 9. Các lưu ý về định dạng, byte dư và an toàn

- `Deflater()`/`Inflater()` mặc định dùng định dạng **zlib**, không phải GZIP. Với GZIP dùng `GZIPInputStream`/`GZIPOutputStream`; raw DEFLATE cần phối hợp lựa chọn `nowrap` ở hai phía.
- `Inflater.inflate(...)` có thể ném checked `DataFormatException` cho dữ liệu nén sai định dạng; phải xử lý hoặc khai báo.
- Một stream giải nén có thể yêu cầu dictionary; `needsDictionary()` cần được xử lý, không được giả vờ rằng chỉ cấp input là đủ.
- Sau `Inflater.finished()`, `getRemaining()` cho biết số byte nén đã cấp nhưng chưa dùng; điều này quan trọng nếu đầu vào chứa nhiều gói hoặc phần theo sau stream.
- Dữ liệu nén nhỏ có thể bung thành dữ liệu rất lớn. Nếu nguồn không tin cậy, áp dụng **giới hạn tổng số byte giải nén**, kích thước buffer và thời gian xử lý; tránh tích lũy vô hạn trong RAM.
- `Deflater` và `Inflater` giữ tài nguyên native; gọi `end()` trong `finally` để giải phóng. Đây là cách tương thích với Java 11 và hiện vẫn có giá trị.
- Không thay đổi buffer input hay đối tượng nén/giải nén đồng thời từ luồng khác khi một thao tác đang dùng nó; cần có cơ chế đồng bộ nếu chia sẻ.

## 10. Tự kiểm tra

**Câu 1:** `inflate()` trả `0`. Đã kết thúc giải nén chưa?

**Đáp án:** Chưa thể kết luận. Kiểm tra `finished()`, `needsInput()`, `needsDictionary()` và tiến triển; `0` chỉ nói rằng chưa tạo byte output lần này.

**Câu 2:** Output 128 byte bị đầy, nhưng `inflater.finished()==false`. Làm gì?

**Đáp án:** Tiêu thụ 128 byte đã tạo, chuẩn bị lại buffer và gọi tiếp. Không được bỏ output hay kết luận hết stream.

**Câu 3:** `deflater.needsInput()` đúng và nguồn socket chưa EOF. Có được gọi `finish()` không?

**Đáp án:** Không. Cần chờ/thêm input. Chỉ gọi `finish()` khi biết sẽ không còn dữ liệu nguồn cho stream này.

**Câu 4:** Nguồn nén đã EOF và `inflater.needsInput()==true` nhưng `finished()==false`. Làm gì?

**Đáp án:** Với luồng zlib cần hoàn chỉnh, báo thiếu input/cắt cụt; không lặp `inflate()` vô hạn.

**Câu 5:** Vì sao phải `flip()` sau `inflate(ByteBuffer)`?

**Đáp án:** Vì `inflate` đang ghi và tăng `position`; `flip()` chuyển buffer sang trạng thái đọc đúng đoạn vừa được ghi.

**Ghi nhớ:** Một lần `deflate()`/`inflate()` chỉ xử lý **một phần** dữ liệu có thể có. Tiếp tục khi còn output, cấp thêm input khi `needsInput()`, xử lý dictionary khi cần, theo dõi tiến triển để tránh busy loop, và chỉ coi luồng hoàn tất khi `finished()` hoặc kết thúc bằng lỗi có nguyên nhân rõ ràng.

**Tài liệu API:** [Oracle Java SE 11 — Deflater](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Deflater.html), [Inflater](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Inflater.html); [Oracle Java SE 25 — Inflater](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/Inflater.html).
