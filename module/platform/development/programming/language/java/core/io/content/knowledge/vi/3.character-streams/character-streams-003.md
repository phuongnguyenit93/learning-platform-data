# EOF của `Reader` và số ký tự thực tế đã đọc trong Java

Khi đọc văn bản bằng `java.io.Reader`, hai quy tắc quyết định tính đúng đắn:

1. **EOF (end of file/end of stream)** được báo bằng `-1` ở các phương thức `read(...)`, tức luồng ký tự đã kết thúc.
2. **Số ký tự đọc được có thể nhỏ hơn kích thước vùng đích.** Giá trị `int n` do `read(...)` trả về mới là số đơn vị `char` đã thực sự nhận, nên chỉ xử lý đúng `n` phần tử mới trong buffer.

**Đọc ngắn (short read) chưa phải EOF.** Ngay cả khi mảng đủ lớn, một lần đọc có thể nhận ít dữ liệu hơn yêu cầu, vì vậy cần lặp cho đến `-1` khi muốn đọc hết. Mặt khác, `char` của Java là một **đơn vị mã UTF-16**; đếm `char` không luôn giống đếm Unicode code point, ký tự người dùng nhìn thấy hay byte.

## 1. `Reader` là gì và mỗi phương thức trả về gì?

`Reader` là API đọc luồng **ký tự**; `InputStream` đọc luồng **byte**. Những triển khai phổ biến:

- `StringReader`: đọc dữ liệu đã nằm trong `String`.
- `InputStreamReader`: giải mã byte từ `InputStream` bằng một `Charset` như UTF-8.
- `BufferedReader`: thêm bộ đệm và hỗ trợ `readLine()`.
- `Files.newBufferedReader(path, StandardCharsets.UTF_8)`: mở tệp văn bản với charset chỉ định rõ.

| Phương thức | Giá trị thành công | Hết luồng | Ý nghĩa |
| --- | --- | --- | --- |
| `int read()` | Một đơn vị UTF-16 trong khoảng `0..65535` | `-1` | Không trả trực tiếp `char`, để dành giá trị âm biểu thị EOF. |
| `int read(char[] dst)` | Số đơn vị `char` mới ghi, tối đa `dst.length` | `-1` khi yêu cầu đọc dương và hết dữ liệu | Có thể nhỏ hơn kích thước mảng. |
| `int read(char[] dst, int off, int len)` | Số `char` ghi vào `dst` từ chỉ số `off` | `-1` khi yêu cầu dương và EOF | `off` là vị trí trong mảng, **không phải offset trong file**. |
| `int read(CharBuffer target)` | Số `char` mới thêm vào `target` | `-1` khi yêu cầu dương và EOF | Giới hạn bởi `target.remaining()`. |
| `String readLine()` của `BufferedReader` | Nội dung dòng, có thể là `""` | `null` | Dấu kết thúc dòng bị bỏ khỏi kết quả. |

`Reader.read(...)` và `BufferedReader.readLine()` **không dùng chung tín hiệu EOF**: nhóm đầu trả `int` với dấu `-1`; `readLine()` trả `null`.

## 2. EOF của `Reader.read()` phải kiểm tra khi kết quả còn là `int`

`Reader.read()` trả `-1` khi đã hết dữ liệu, còn các giá trị không âm từ `0` đến `65535` đều có thể biểu diễn một đơn vị `char`. Ép về `char` quá sớm sẽ làm mất khả năng phân biệt EOF.

Sai (đoạn minh họa, giả định `reader` đã tồn tại):

```java
char ch = (char) reader.read();
if (ch == -1) {
    // Không phát hiện EOF được vì đã ép kiểu.
}
```

Khi ép `-1` sang `char`, kết quả trở thành `0xFFFF`. Đúng là giữ `int` cho tới khi đã kiểm tra:

```java
int value;
while ((value = reader.read()) != -1) {
    char ch = (char) value;
    // Lúc này ch chắc chắn là dữ liệu đã đọc.
}
```

Chương trình Java 17+ độc lập sau cho thấy giá trị `0xFFFF` khác EOF:

```java
// ReaderEofDemo.java
import java.io.Reader;
import java.io.StringReader;

public class ReaderEofDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader =
                     new StringReader("A" + (char) 0xFFFF)) {
            System.out.println(reader.read());
            System.out.println(reader.read());
            System.out.println(reader.read());
        }
    }
}
```

```bash
javac ReaderEofDemo.java
java ReaderEofDemo
```

Đầu ra:

```text
65
65535
-1
```

`65` biểu diễn `A`; `65535` là giá trị `char` `0xFFFF`; `-1` mới là EOF. Giá trị `0` cũng có thể là nội dung ký tự NUL, **không có nghĩa là EOF** khi gọi `read()` không tham số.

### EOF khác “chưa nhận được dữ liệu”

Một `Reader` có thể đọc từ file, bộ nhớ, socket hoặc nguồn tương tác. Với nguồn như socket, lời gọi `read` ở chế độ blocking có thể **đợi** dữ liệu đến hoặc đầu truyền kết thúc. Chưa có byte đến ngay lúc đó không có nghĩa là EOF. Nếu reader có bộ đệm, dữ liệu còn đệm vẫn được trả trước khi EOF xuất hiện.

`Reader.ready()` **không phải phép kiểm tra EOF**: `false` không đủ để suy ra hết dữ liệu, còn việc `true` nói về điều kiện sẵn sàng đọc theo hợp đồng của implementation. Đóng reader bằng `close()` cũng khác EOF; đọc sau khi đóng thường ném `IOException`, không phải cách chuẩn để nhận `-1`.

## 3. `read(char[])`: `n` là số ký tự vừa được ghi, không phải dung lượng buffer

Khi gọi `int n = reader.read(buffer)`:

- `n > 0`: có `n` đơn vị UTF-16 mới được chép vào `buffer[0]` đến `buffer[n - 1]`.
- `n == -1`: đã tới EOF nếu lời gọi yêu cầu đọc dương.
- `n == 0`: có thể xảy ra với yêu cầu đọc có độ dài 0 (xem phần tiếp theo); không được dùng nó thay cho EOF.

Ví dụ một mảng dài 4 đọc chuỗi dài 5:

```java
// ReaderChunkDemo.java
import java.io.Reader;
import java.io.StringReader;

public class ReaderChunkDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("ABCDE")) {
            char[] buffer = new char[4];
            int n;

            while ((n = reader.read(buffer)) != -1) {
                System.out.println("n=" + n
                        + ", chunk=" + new String(buffer, 0, n));
            }
            System.out.println("next=" + reader.read(buffer));
        }
    }
}
```

```bash
javac ReaderChunkDemo.java
java ReaderChunkDemo
```

Đầu ra:

```text
n=4, chunk=ABCD
n=1, chunk=E
next=-1
```

Lần thứ hai chỉ ký tự `E` là mới. Phần còn lại trong mảng vẫn có thể chứa `BCD` của lần đọc trước. Vì vậy `new String(buffer)` hoặc `System.out.print(buffer)` sẽ vô tình in **dữ liệu cũ**. Dùng `new String(buffer, 0, n)` hoặc `writer.write(buffer, 0, n)` để chỉ xử lý đúng phần mới nhận.

**Không kết luận EOF từ short read:** một lần đọc 2/4096 ký tự chỉ cho biết có hai ký tự được trả ở lần đó. Lần sau vẫn có thể nhận thêm. Khi đọc hết luồng, điều kiện kết thúc là `-1`, không phải `n < buffer.length`.

Ví dụ sao chép ký tự theo khối, giả định `reader` và `writer` đều đã mở:

```java
char[] buffer = new char[8192];
int n;
long total = 0;

while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
    writer.write(buffer, 0, n);
    total += n;
}
```

Đây là **đoạn minh họa**, không phải một class độc lập. `writer.write` nhận số lượng `n` vừa đọc, còn `total` cộng số đơn vị `char` thực tế. Nếu cộng `buffer.length`, tổng sẽ sai ở các lần đọc ngắn.

### `off`, `len` và trường hợp độ dài bằng 0

`read(dst, off, len)` yêu cầu tối đa `len` `char` được ghi vào mảng `dst`, bắt đầu từ chỉ số `off`. Với `off=3`, `len=4`, `n=2`, chỉ phần tử `dst[3]`, `dst[4]` vừa được cập nhật. Không được hiểu `off` là vị trí trong file.

Một yêu cầu với `len == 0` hợp lệ (nếu `off` hợp lệ) sẽ trả `0` mà không tiêu thụ ký tự. Có thể nhận `0` **ngay cả khi reader đang ở EOF**. Ví dụ xác định của `StringReader`:

```java
// ReaderZeroLengthDemo.java
import java.io.Reader;
import java.io.StringReader;

public class ReaderZeroLengthDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("K")) {
            char[] buffer = new char[3];
            System.out.println("empty=" + reader.read(buffer, 0, 0));
            System.out.println("first=" + reader.read(buffer, 0, 3));
            System.out.println("eof=" + reader.read(buffer, 0, 3));
            System.out.println("emptyAfterEof=" + reader.read(buffer, 0, 0));
        }
    }
}
```

```bash
javac ReaderZeroLengthDemo.java
java ReaderZeroLengthDemo
```

Đầu ra:

```text
empty=0
first=1
eof=-1
emptyAfterEof=0
```

Tương tự, `read(CharBuffer)` với buffer không còn `remaining()` không yêu cầu thêm ký tự. Nếu `off`, `len` âm hoặc khoảng ghi vượt ra ngoài mảng, tham số không hợp lệ và có thể ném `IndexOutOfBoundsException`.

## 4. Đọc đúng N ký tự phải lặp đến khi đủ hoặc gặp EOF sớm

Một lần `read(dst, off, len)` **không bảo đảm** lấy đủ `len` ký tự; điều này đặc biệt quan trọng khi giao thức hoặc cấu trúc file quy định số ký tự cần nhận. Muốn lấy đúng N đơn vị UTF-16, hãy cộng dồn `n`, và báo lỗi nếu `-1` xuất hiện trước khi đủ.

Ví dụ Java 17+ độc lập:

```java
// ReaderExactDemo.java
import java.io.EOFException;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;

public class ReaderExactDemo {
    static String readExactly(Reader reader, int expected)
            throws IOException {
        if (expected < 0) {
            throw new IllegalArgumentException("expected must be >= 0");
        }

        char[] result = new char[expected];
        int filled = 0;

        while (filled < expected) {
            int n = reader.read(result, filled, expected - filled);

            if (n == -1) {
                throw new EOFException(
                        "expected=" + expected + ", actual=" + filled);
            }
            if (n == 0) {
                throw new IOException("Reader made no progress");
            }
            filled += n;
        }

        return new String(result);
    }

    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("ABC")) {
            System.out.println(readExactly(reader, 2));
            try {
                System.out.println(readExactly(reader, 2));
            } catch (EOFException ex) {
                System.out.println(ex.getMessage());
            }
        }
    }
}
```

```bash
javac ReaderExactDemo.java
java ReaderExactDemo
```

Đầu ra:

```text
AB
expected=2, actual=1
```

Lượt đầu lấy đủ `AB`. Lượt sau lấy được `C` rồi EOF, nên lỗi ghi rõ mới có 1/2 ký tự. Nhánh `n == 0` tránh busy loop nếu một `Reader` tùy biến trả 0 khi yêu cầu đọc dương mà không tiến triển; với các triển khai tuân hợp đồng thông thường, đọc với `len > 0` sẽ trả số dương hoặc `-1`. Trường hợp `expected == 0` trả `""` mà không đọc; không được coi đây là dấu hiệu EOF.

Nếu chỉ muốn xử lý **toàn bộ luồng**, không cần `readExactly`: dùng vòng lặp đọc đến `-1` và xử lý mỗi khối mới nhận.

## 5. Số `char` từ `Reader` khác số byte và Unicode code point

Mỗi Java `char` là **một code unit UTF-16** 16-bit. Unicode code point bên ngoài BMP (ví dụ emoji) dùng **hai** đơn vị mã (surrogate pair). Phân biệt:

- **Byte:** phụ thuộc cách mã hóa ký tự thành byte, ví dụ UTF-8.
- **`char` / code unit UTF-16:** đơn vị mà `Reader.read` trả và `String.length()` đếm.
- **Unicode code point:** có thể cần một hoặc hai code unit UTF-16.
- **Grapheme cluster:** ký tự mà người dùng cảm nhận; có thể gồm nhiều code point, chẳng hạn chữ có dấu kết hợp.

Chuỗi `"A😀B"` là một ví dụ: ba code point, bốn `char`, sáu byte UTF-8. Ví dụ độc lập dùng `InputStreamReader` để giải mã UTF-8 và cộng tổng từ giá trị `n` thực tế:

```java
// ReaderCharCountDemo.java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class ReaderCharCountDemo {
    public static void main(String[] args) throws Exception {
        String original = "A😀B";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        StringBuilder decoded = new StringBuilder();
        int actualChars = 0;

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8),
                StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int n;

            while ((n = reader.read(buffer)) != -1) {
                decoded.append(buffer, 0, n);
                actualChars += n;
            }
        }

        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("readChars=" + actualChars);
        System.out.println("codePoints="
                + decoded.codePointCount(0, decoded.length()));
        System.out.println("roundTrip=" + original.contentEquals(decoded));
    }
}
```

```bash
javac -encoding UTF-8 ReaderCharCountDemo.java
java ReaderCharCountDemo
```

Đầu ra:

```text
utf8Bytes=6
readChars=4
codePoints=3
roundTrip=true
```

Đoạn mã không giả định cách chia chunk cố định. Khi xử lý văn bản theo chunk, cần chú ý **surrogate pair có thể nằm ở biên giữa hai chunk**. Nếu phải xử lý Unicode code point hoặc encode lại từng chunk riêng lẻ, cần giữ trạng thái để không tách sai cặp. Ví dụ trên ghép hoàn chỉnh vào `StringBuilder` trước khi đếm code point.

`InputStreamReader` làm việc qua **bộ giải mã byte → char**. Một byte UTF-8 không nhất thiết tạo ra một `char`; reader có thể đọc trước nhiều byte vào bộ đệm. Vì vậy không suy số byte từ `read` của `Reader`, và không suy EOF của reader chỉ từ số byte đã lấy ở tầng dưới.

## 6. `BufferedReader.readLine()`: `null` mới là EOF, `""` vẫn là một dòng

`BufferedReader.readLine()` trả về nội dung của một dòng, bỏ delimiter `\n`, `\r` hoặc `\r\n`. Dòng rỗng được biểu diễn bằng `""` (chuỗi có độ dài 0). Chỉ khi không còn dòng nào để đọc, phương thức mới trả `null`.

```java
// ReaderLinesDemo.java
import java.io.BufferedReader;
import java.io.StringReader;

public class ReaderLinesDemo {
    public static void main(String[] args) throws Exception {
        try (BufferedReader reader = new BufferedReader(
                new StringReader("alpha\n\nomega"))) {
            String line;
            int lineNumber = 0;

            while ((line = reader.readLine()) != null) {
                System.out.println(++lineNumber + ": <" + line + ">");
            }
            System.out.println("eof=" + (reader.readLine() == null));
        }
    }
}
```

```bash
javac ReaderLinesDemo.java
java ReaderLinesDemo
```

Đầu ra:

```text
1: <alpha>
2: <>
3: <omega>
eof=true
```

Dòng thứ hai là một **dòng rỗng hợp lệ**; không được bỏ qua vì tưởng EOF. Trường hợp `"alpha\n"` trả `"alpha"` rồi `null`: dấu xuống dòng kết thúc dòng đang có, không tự tạo thêm một dòng rỗng thứ hai. Trường hợp `"\n"` trả `""` rồi `null`.

Nếu cần giữ nguyên dấu xuống dòng trong dữ liệu, `readLine()` không phù hợp vì nó loại bỏ các delimiter; hãy đọc từng khối `char` hoặc lưu dấu ngắt theo định dạng riêng.

## 7. Ví dụ với tệp UTF-8 và tổng số ký tự thực tế

Chương trình độc lập dưới đây tạo hai tệp tạm, sao chép văn bản qua `Reader`/`Writer`, đếm đúng `n` của từng lần đọc, đóng tài nguyên rồi so sánh dữ liệu:

```java
// ReaderFileDemo.java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReaderFileDemo {
    public static void main(String[] args) throws Exception {
        Path source = Files.createTempFile("reader-src-", ".txt");
        Path target = Files.createTempFile("reader-dst-", ".txt");

        try {
            Files.writeString(source, "Xin chào\nJava IO\n",
                    StandardCharsets.UTF_8);

            long copiedChars = 0;
            try (Reader reader = Files.newBufferedReader(
                         source, StandardCharsets.UTF_8);
                 Writer writer = Files.newBufferedWriter(
                         target, StandardCharsets.UTF_8)) {
                char[] buffer = new char[5];
                int n;

                while ((n = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, n);
                    copiedChars += n;
                }
            }

            System.out.println("copiedChars=" + copiedChars);
            System.out.println("sameText=" + Files.readString(
                    source, StandardCharsets.UTF_8).equals(
                    Files.readString(target, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
        }
    }
}
```

```bash
javac -encoding UTF-8 ReaderFileDemo.java
java ReaderFileDemo
```

Đầu ra:

```text
copiedChars=17
sameText=true
```

`"Xin chào\n"` gồm 9 code unit UTF-16, `"Java IO\n"` gồm 8; tổng là **17 `char`**. Mảng đệm chỉ có 5 vị trí, nhưng kết quả cuối cùng không phụ thuộc cách `Reader` chia các lượt đọc. `try-with-resources` bảo đảm writer được đóng trước khi đọc lại tệp đích, nên dữ liệu đã được ghi xong.

Đối với tệp lớn, đọc từng khối như thế này giúp tránh nạp cả file thành một `String` trong RAM. Từ Java 10 còn có `Reader.transferTo(Writer)`, phương thức sao chép đến EOF và trả về tổng số `char` đã chuyển, nhưng không tự đóng reader/writer.

## 8. Các nhầm lẫn và lỗi phổ biến

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Ép `reader.read()` sang `char` rồi mới so với `-1` | Sentinel EOF bị mất khi ép kiểu | Kiểm tra kết quả `int` trước. |
| Gọi `read(buffer)` rồi xử lý toàn bộ `buffer` | Phần chưa ghi có thể còn dữ liệu cũ | Chỉ xử lý `buffer[0..n)` khi `n > 0`. |
| Coi `n < buffer.length` là EOF | Short read chưa chắc là hết nguồn | Lặp đến `-1`. |
| Cộng `buffer.length` vào số ký tự đã đọc | Đếm cả vùng không có dữ liệu mới | Cộng chính xác `n`. |
| Chỉ gọi `read` một lần để lấy N ký tự | Có thể lấy thiếu | Lặp cộng dồn; xử lý EOF sớm. |
| Dùng `len == 0` để dò EOF | Trả `0` dù nguồn có thể đang ở EOF | Đọc với yêu cầu dương để nhận `-1`. |
| Coi `readLine().isEmpty()` là kết thúc | Dòng rỗng khác `null`, EOF gây NPE | Kiểm tra `line != null`. |
| Dùng `ready()` để dò EOF | Sự sẵn sàng không tương đương hết nguồn | Đọc và xét giá trị trả về. |
| Coi số `char` là số byte hoặc code point | Unicode/charset có thể dùng nhiều đơn vị | Xác định rõ loại đơn vị cần đếm. |
| Không đóng `Reader` | Rò rỉ file descriptor/nguồn lực | Dùng `try-with-resources`. |

### Tự kiểm tra

1. `char[] b = new char[100]`; `reader.read(b)` trả `7`. **Chỉ bảy ký tự đầu của mảng là dữ liệu mới**, không phải cả 100.
2. Lần đọc vào mảng dài 100 trả `7`. Lần sau có chắc `-1`? **Không.** Đọc ngắn chưa chứng minh EOF.
3. `readLine()` trả `""`. Đã tới EOF? **Không thể suy ra như vậy:** đây là dòng rỗng; EOF được biểu diễn bằng `null`.
4. `read(array, 5, 2)` trả `1`. Ký tự mới nằm ở **`array[5]`**, không phải vị trí 5 trong tệp.
5. `read(array, 0, 0)` có thể trả `0` ngay ở EOF? **Có**, vì không yêu cầu lấy thêm ký tự.
6. `"A😀B"` gồm bao nhiêu byte UTF-8, `char` và code point? **6 byte, 4 `char`, 3 code point**.

**Quy tắc cốt lõi:** Với `Reader.read(...)`, **`-1` là EOF; giá trị không âm là số đơn vị `char` thực tế đã đọc** (khi yêu cầu chiều dài 0 thì trả 0). Với `BufferedReader.readLine()`, **`null` là EOF; chuỗi rỗng `""` vẫn là một dòng hợp lệ**. Luôn sử dụng giá trị trả về của chính lần đọc đang thực hiện để quyết định phần dữ liệu nào được xử lý.
