# InputStreamReader: nối luồng byte với ký tự trong Java

`InputStreamReader` là cầu nối từ **`InputStream` (byte)** sang **`Reader` (ký tự)**. Nó dùng bộ giải mã của một `Charset` để diễn giải các byte theo một bảng mã xác định, rồi trả về các đơn vị `char` của Java (UTF-16). Nhờ đó, chương trình có thể đọc văn bản từ file, socket hoặc nguồn byte khác mà không tự giải mã từng byte.

Đây là chủ đề thuộc **luồng ký tự**: cần hiểu luồng byte ở tầng dưới, ý nghĩa của encoding và cách đọc đúng văn bản bằng API `Reader`.

## 1. Vì sao cần chuyển từ byte sang ký tự?

Máy tính truyền/lưu trữ file dưới dạng byte; chữ viết là ký tự Unicode. **Một byte không nhất thiết tương ứng với một ký tự**:

- Trong UTF-8, ký tự ASCII thường chiếm 1 byte, ký tự như `é` chiếm 2 byte, ký tự `☕` chiếm 3 byte, nhiều emoji chiếm 4 byte.
- Trong Java, một `char` là **một đơn vị mã UTF-16** (16 bit), không bảo đảm biểu diễn trọn một Unicode code point. Ví dụ emoji `🙂` cần **hai** `char` (surrogate pair).
- Cùng một chuỗi byte có thể thành văn bản khác nhau nếu giải mã bằng charset khác; byte không hợp lệ theo charset đã chọn còn có thể làm mất dữ liệu hoặc gây lỗi.

`InputStream` chỉ cung cấp byte, chẳng hạn `read()` trả về một byte dưới dạng số `0..255` hoặc `-1` khi EOF. Nếu muốn đọc văn bản, ta cần **giải mã nhiều byte thành ký tự khi cần**. Đó là trách nhiệm của `InputStreamReader`.

```text
File / mạng / vùng nhớ
        |
        | dãy byte (ví dụ UTF-8: 43 61 66 C3 A9)
        v
     InputStream
        |
        | giải mã theo Charset
        v
  InputStreamReader
        |
        | Java char (UTF-16): C  a  f  é
        v
       Reader  ---> xử lý văn bản
```

Chuỗi byte ở sơ đồ là chữ `Café` trong UTF-8. Cặp byte `C3 A9` cùng mã hóa chữ `é`; nếu tự ép từng byte thành `char`, chương trình không thể giải mã đúng.

## 2. Cách tạo `InputStreamReader`

Định dạng cơ bản:

```java
InputStream input = /* nguồn byte đã mở */;
Reader reader = new InputStreamReader(input, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa**, yêu cầu biến `input` và các import thích hợp. Hãy chọn charset theo **định dạng thực tế của dữ liệu**, ví dụ:

```java
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

// Ví dụ khi đã có InputStream input:
InputStreamReader reader =
        new InputStreamReader(input, StandardCharsets.UTF_8);
```

Thư viện `java.nio.charset.StandardCharsets` cung cấp những charset thông dụng như `UTF_8`, `UTF_16`, `ISO_8859_1`, `US_ASCII`; không cần viết chuỗi tên charset tùy ý cho các trường hợp này.

Nên **truyền charset tường minh**. Hàm tạo `new InputStreamReader(input)` dùng *default charset* của môi trường; Java 18+ mặc định là UTF-8 theo JEP 400 trong hầu hết trường hợp thông thường, nhưng mã học tập hoặc hệ thống chạy trên nhiều phiên bản/môi trường vẫn không nên ngầm giả định encoding. Charset đúng phải do chuẩn định dạng, protocol hoặc cấu hình nguồn dữ liệu quy định.

Nếu nguồn là UTF-8 mà bạn dùng ISO-8859-1, các byte `C3 A9` thường được diễn giải thành `Ã©` thay vì `é` (*mojibake*). **Đổi charset chỉ hợp lý khi bạn biết charset gốc**, không phải một cách sửa mọi lỗi hiển thị.

## 3. `InputStreamReader` giải mã như thế nào?

`InputStreamReader` kế thừa `Reader`; các thao tác đọc trả về ký tự đã giải mã:

| API | Giá trị trả về | Ý nghĩa |
| --- | --- | --- |
| `reader.read()` | `int` từ `0` đến `65535`, hoặc `-1` | Một đơn vị `char` (UTF-16) hoặc EOF |
| `reader.read(char[])` | `int` là số `char` đã đọc, hoặc `-1` | Số đơn vị `char` hợp lệ trong mảng |
| `reader.read(char[], off, len)` | `int` là số `char` đã đọc, hoặc `-1` | Ghi ký tự bắt đầu từ vị trí `off` |
| `reader.close()` | không có giá trị | Đóng reader và đóng cả luồng nguồn bên dưới |

Với `read(char[])`, số `n` trả về là **số phần tử `char` hợp lệ**, không phải số byte đã tiêu thụ; một `char[]` có thể còn các phần tử cũ từ lần đọc trước. Do đó phải xử lý đúng `n` ký tự:

```java
char[] buffer = new char[1024];
int n;

while ((n = reader.read(buffer)) != -1) {
    text.append(buffer, 0, n);  // text là một StringBuilder đã khai báo
}
```

Sai lầm thường gặp là `text.append(buffer)`, vì như vậy mỗi vòng sẽ thêm **toàn bộ buffer**, kể cả phần dư chưa được thay đổi. Vòng lặp ví dụ giả định buffer có chiều dài dương và `reader` tuân theo hợp đồng `Reader`; không suy luận EOF chỉ vì một lần đọc ngắn.

Một lần `reader.read(buffer)` không bắt buộc lấp đầy mảng. Bên dưới, bộ giải mã có thể đọc trước nhiều byte, giữ lại byte của một chuỗi đa byte chưa đầy đủ và ghép với byte của lần đọc tiếp theo. **Ranh giới của các lần đọc byte không phải ranh giới ký tự.**

Chẳng hạn `é` là `C3 A9` trong UTF-8. Nếu nguồn trả `C3` ở một lần đọc và `A9` ở lần đọc sau, bộ giải mã cần giữ trạng thái để tạo được ký tự `é`. Tự gọi `new String(bytes, UTF_8)` trên từng mảnh byte độc lập có nguy cơ giải mã sai khi một chuỗi UTF-8 bị cắt đôi.

## 4. Chương trình Java 17+ chạy độc lập

Ví dụ này ép nguồn `InputStream` chỉ cung cấp tối đa **1 byte mỗi lần đọc vào mảng**. Trong khi đó, `InputStreamReader` vẫn phải tái tạo đúng các ký tự có encoding UTF-8 dài hơn một byte. Việc dùng `char[2]` cũng minh họa cách chỉ thêm đúng số `char` mà `read` trả về.

Lưu nội dung dưới đây thành file **`InputStreamReaderDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class InputStreamReaderDemo {

    public static void main(String[] args) throws IOException {
        String expected = "Café ☕";
        byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);
        StringBuilder actual = new StringBuilder();

        try (InputStream input = new OneByteAtATimeStream(
                    new ByteArrayInputStream(utf8));
             Reader reader = new InputStreamReader(
                    input, StandardCharsets.UTF_8)) {

            char[] chars = new char[2];
            int charsRead;

            while ((charsRead = reader.read(chars)) != -1) {
                actual.append(chars, 0, charsRead);
            }
        }

        System.out.println("UTF-8 bytes: " + utf8.length);
        System.out.println("Java char units: " + actual.length());
        System.out.println("Text: " + actual);
        System.out.println("Matches: " + expected.contentEquals(actual));
    }

    private static final class OneByteAtATimeStream
            extends FilterInputStream {

        private OneByteAtATimeStream(InputStream source) {
            super(source);
        }

        @Override
        public int read(byte[] b, int off, int len)
                throws IOException {
            return super.read(b, off, Math.min(len, 1));
        }
    }
}
```

Trong terminal có JDK 17+:

```bash
javac -encoding UTF-8 InputStreamReaderDemo.java
java InputStreamReaderDemo
```

**Kết quả chuẩn (stdout):**

```text
UTF-8 bytes: 9
Java char units: 6
Text: Café ☕
Matches: true
```

Giải thích:

1. Chuỗi `Café ☕` có **9 byte UTF-8**: ba chữ ASCII `C`, `a`, `f` = 3 byte; `é` = 2 byte; dấu cách = 1 byte; `☕` = 3 byte.
2. Chuỗi giải mã gồm **6 đơn vị `char` UTF-16**: `C`, `a`, `f`, `é`, dấu cách và `☕`. Trường hợp này không chứa ký tự ngoài Basic Multilingual Plane, nên mỗi ký tự vừa nêu chiếm một `char`.
3. `OneByteAtATimeStream` mô phỏng đầu vào có các lần đọc byte ngắn, buộc bộ giải mã nối nhiều lần đọc để tạo `é` và `☕`.
4. `actual.append(chars, 0, charsRead)` chỉ lấy phần mới có dữ liệu. `contentEquals` xác nhận chuỗi đọc giống chuỗi ban đầu.

Lớp `OneByteAtATimeStream` chỉ phục vụ bài thử: các `InputStream` thực tế không bảo đảm số byte mỗi lần đọc như vậy. Phần quan trọng để dùng trong ứng dụng là `InputStreamReader(input, StandardCharsets.UTF_8)` và vòng lặp `Reader.read(char[])`.

## 5. Đọc văn bản từ tệp

Với đường dẫn `Path` và encoding đã biết, có thể mở luồng byte và bọc bằng `InputStreamReader`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static String readUtf8File(Path path) throws IOException {
    StringBuilder text = new StringBuilder();

    try (InputStream input = Files.newInputStream(path);
         Reader reader = new InputStreamReader(
                 input, StandardCharsets.UTF_8)) {

        char[] chars = new char[4096];
        int n;

        while ((n = reader.read(chars)) != -1) {
            text.append(chars, 0, n);
        }
    }

    return text.toString();
}
```

Đây là **phương thức minh họa** cần đặt bên trong một class; đưa `import` lên đầu file. `try-with-resources` đảm bảo đóng reader và stream kể cả khi phát sinh `IOException`. Việc đóng reader vốn đã đóng stream bên dưới; khai báo cả hai tài nguyên như ví dụ giúp thể hiện rõ chủ sở hữu, nhưng cũng có thể chỉ quản lý trực tiếp reader:

```java
try (Reader reader = new InputStreamReader(
        Files.newInputStream(path), StandardCharsets.UTF_8)) {
    // Đọc ký tự bằng reader
}
```

Nếu chỉ cần đọc văn bản từ file, `Files.newBufferedReader(path, StandardCharsets.UTF_8)` thường ngắn gọn hơn. Nó trả về `BufferedReader`, phù hợp khi muốn dùng `readLine()`. Dù dùng API nào, vẫn phải xác định đúng charset của dữ liệu.

**Lưu ý kích thước:** Gom toàn bộ tệp vào một `StringBuilder` sẽ dùng bộ nhớ tỷ lệ với kích thước văn bản; với file lớn, nên xử lý từng khối hoặc từng dòng thay vì giữ toàn bộ nội dung trong RAM.

## 6. Khi cần `BufferedReader`

`InputStreamReader` chuyển byte thành ký tự; `BufferedReader` thêm lớp đệm ký tự và các tiện ích như `readLine()`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

static void printLines(InputStream input) throws IOException {
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {
        String line;

        while ((line = reader.readLine()) != null) {
            System.out.println(line);
        }
    }
}
```

Đây là phương thức minh họa cần đặt trong một class, với `input` là stream mà phương thức **được phép đóng**. `readLine()` trả `null` khi EOF và bỏ ký tự kết thúc dòng (CR, LF hoặc CRLF) khỏi chuỗi kết quả. Nếu phải bảo toàn nguyên văn dấu xuống dòng, dùng vòng lặp `read(char[])` hoặc logic xử lý ký tự phù hợp.

Luồng lớp bọc:

```text
InputStream (byte)
   -> InputStreamReader (decode bytes thành char)
      -> BufferedReader (đệm ký tự, readLine)
         -> ứng dụng
```

Không bọc `InputStreamReader` khi dữ liệu thực chất là ảnh, ZIP hay định dạng nhị phân tùy ý; hãy tiếp tục thao tác bằng `InputStream`. Dùng `Reader` chỉ khi byte thực sự chứa văn bản được mã hóa bằng một charset xác định.

## 7. Charset, byte lỗi và Unicode

### Charset sai gây văn bản sai

`InputStreamReader` không tự động đoán đúng encoding. Cần xác định charset qua chuẩn tệp, header giao thức (`Content-Type`/`charset` khi đáng tin), tài liệu nguồn hoặc cấu hình thống nhất của hệ thống. Một file có BOM không tự động khiến mọi cách tạo `InputStreamReader` đều tự nhận diện charset và loại bỏ BOM; cách xử lý BOM phụ thuộc encoding/bộ giải mã và ứng dụng. Đừng dựa vào cơ chế suy đoán.

### Byte không hợp lệ và chính sách giải mã

Khi dùng constructor nhận `Charset`, Java thường cấu hình decoder để **thay chuỗi byte lỗi/không ánh xạ được** bằng ký tự thay thế (hay thấy là `�` với UTF-8). Do đó nhận được một chuỗi `String` không chứng minh rằng dữ liệu nguồn hoàn toàn hợp lệ.

Nếu cần **từ chối dữ liệu UTF-8 lỗi** thay vì âm thầm thay thế, truyền `CharsetDecoder` với chế độ `REPORT`:

```java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

// Giả sử đã có InputStream input:
InputStreamReader reader = new InputStreamReader(
        input,
        StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
);
```

Đoạn mã minh họa này chưa bao gồm thao tác đọc và đóng tài nguyên. Khi đọc gặp byte không hợp lệ, decoder báo lỗi qua `IOException` cụ thể, chẳng hạn `MalformedInputException`. Chính sách `REPLACE` có thể phù hợp khi ưu tiên tiếp tục hiển thị, còn `REPORT` phù hợp khi tính toàn vẹn dữ liệu quan trọng.

### Một `char` không nhất thiết bằng một ký tự người dùng thấy

`InputStreamReader` trả về **các đơn vị UTF-16**. Ví dụ chuỗi `"A🙂"` có 5 byte UTF-8, nhưng `String.length()` bằng 3 vì `A` chiếm một `char` và `🙂` chiếm một cặp surrogate (hai `char`). Số Unicode code point là 2, còn số *grapheme cluster* hiển thị trong trường hợp này cũng là 2. Những khái niệm này khác nhau với các dấu kết hợp hoặc emoji ghép phức tạp.

`Reader.read(char[])` có thể kết thúc một lượt đọc ở giữa cặp surrogate. Việc ghép tất cả các đoạn `char` theo đúng thứ tự vẫn giữ nguyên chuỗi; tuy nhiên, đừng coi **mỗi đoạn `char[]`** hoặc **mỗi `char`** là một ký tự Unicode hoàn chỉnh. Nếu cần xử lý từng code point, hãy dùng các API Unicode của `String`/`Character` hoặc thuật toán giữ trạng thái qua ranh giới buffer.

## 8. Vòng đời, buffering và ranh giới dữ liệu

- **Đóng luồng đúng chủ sở hữu:** `InputStreamReader.close()` đóng `InputStream` được bọc. Nếu đang đọc từ `System.in` và muốn tiếp tục sử dụng console, cân nhắc không đóng wrapper tại thời điểm đó.
- **Decoder có thể đọc trước:** một lần `Reader.read()` có thể khiến tầng dưới lấy nhiều byte để duy trì bộ đệm và giải mã. Sau khi bọc stream bằng reader, không tùy tiện xen kẽ `input.read()` trực tiếp với `reader.read()` trên cùng stream; việc đọc trước sẽ làm khó dự đoán vị trí dữ liệu.
- **Lỗi I/O:** `read` và `close` có thể ném `IOException`. Dùng `try-with-resources` và để tầng gọi quyết định thông báo/khôi phục nếu có lỗi.
- **Không cố dự đoán số byte từ số char:** byte UTF-8, đơn vị `char` UTF-16 và Unicode code point là ba thước đo khác nhau.
- **Luồng theo chiều ngược:** `OutputStreamWriter` chuyển các `char` từ `Writer` thành byte theo `Charset` để ghi ra `OutputStream`. Dùng cùng charset ở hai đầu khi giao thức yêu cầu, ví dụ UTF-8.

## 9. Các lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `(char) input.read()` cho mọi văn bản | Đọc từng byte, làm hỏng ký tự mã hóa bằng nhiều byte | Dùng `InputStreamReader` với charset đúng |
| `new InputStreamReader(input)` mà không quan tâm môi trường | Ngầm phụ thuộc default charset | Ghi rõ `StandardCharsets.UTF_8` hoặc charset thực tế |
| `new String(bytesChunk, UTF_8)` cho từng khối độc lập | Có thể cắt đôi mã UTF-8 giữa hai khối | Giải mã trạng thái liên tục bằng `InputStreamReader` |
| `builder.append(buffer)` sau `read(char[])` | Thêm cả ký tự cũ ở cuối mảng | `builder.append(buffer, 0, charsRead)` |
| Coi `charsRead` là số byte | Một ký tự có thể cần nhiều byte và ngược lại | Phân biệt số byte, số `char`, số code point |
| Dừng sau lần đọc thiếu `buffer.length` | Luồng còn dữ liệu ở các lần sau | Chỉ EOF khi `read` trả `-1` |
| Bọc dữ liệu ảnh/ZIP trong reader | Giải mã làm thay đổi byte gốc | Dùng `InputStream`/`OutputStream` cho nhị phân |
| Đóng reader rồi lại dùng input bên dưới | `close()` đóng cả stream nguồn | Quy định rõ vòng đời và chủ sở hữu |
| Giả định đầu vào hỏng luôn ném lỗi | Decoder mặc định có thể thay thế chuỗi lỗi | Cấu hình `CharsetDecoder` với `REPORT` |

## 10. Tự kiểm tra

1. Byte UTF-8 của `é` là `C3 A9`. Nếu nguồn trả hai byte này ở hai lượt đọc khác nhau, nên tự đổi từng byte thành `char` không? **Không.** `InputStreamReader` giữ trạng thái giải mã để tạo ký tự đúng.
2. `reader.read(buffer)` trả `3` trong khi `buffer.length == 1024`. Phải thêm bao nhiêu đơn vị `char` vào kết quả? **Chỉ 3**, bằng `append(buffer, 0, 3)`.
3. `Reader.read()` trả `-1` có nghĩa là gì? **Hết luồng ký tự**, không có thêm ký tự để đọc.
4. Một chuỗi Java có `String.length() == 3` có luôn là 3 Unicode code point không? **Không**; ký tự ngoài BMP có thể cần hai đơn vị `char`.
5. Đọc file UTF-8 theo dòng nên kết hợp những lớp nào? **`InputStream` → `InputStreamReader`(UTF-8) → `BufferedReader`**, hoặc dùng `Files.newBufferedReader`.
6. Gặp UTF-8 sai và yêu cầu báo lỗi ngay: cần gì? **`CharsetDecoder` cấu hình `CodingErrorAction.REPORT`**, không chỉ dựa vào constructor mặc định.

**Ghi nhớ:** `InputStreamReader` chịu trách nhiệm **giải mã liên tục byte → UTF-16 char theo charset đã chọn**; vòng lặp `Reader.read(char[])` xử lý đúng **số char vừa đọc**, còn `BufferedReader` bổ sung đệm và đọc theo dòng khi cần.