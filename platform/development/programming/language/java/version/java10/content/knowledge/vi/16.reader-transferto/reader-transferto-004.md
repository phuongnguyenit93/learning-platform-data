# Phân biệt luồng ký tự với luồng byte khi sử dụng `Reader.transferTo`

*Chủ đề Java 10 — `Reader.transferTo`. Bài Knowledge này dùng các API Java hiện đại vẫn áp dụng trên Java 17+ và những phiên bản JDK mới. Mục tiêu: biết khi nào chuyển **ký tự**, khi nào chuyển **byte**, vì sao số lượng chuyển khác nhau và cách dùng đúng charset để không làm hỏng dữ liệu.*

## 1. Câu trả lời ngắn gọn

Java cung cấp hai họ API đọc/ghi dữ liệu có mục đích khác nhau:

- **Luồng byte**: `InputStream` đọc các byte, `OutputStream` ghi các byte. Dùng khi cần giữ nguyên dữ liệu nhị phân hoặc cần kiểm soát chính xác từng byte.
- **Luồng ký tự**: `Reader` đọc các đơn vị ký tự Java (giá trị `char`, tương ứng đơn vị mã UTF-16), `Writer` ghi các đơn vị ký tự. Dùng khi dữ liệu được hiểu là **văn bản** và việc giải mã/mã hóa có ý nghĩa.
- **Cầu nối giữa hai loại**: `InputStreamReader` giải mã **byte → ký tự** bằng một `Charset`; `OutputStreamWriter` mã hóa **ký tự → byte** bằng một `Charset`.

Java 10 bổ sung phương thức:

~~~java
long numberOfChars = reader.transferTo(writer);
~~~

`Reader.transferTo(Writer)` **đọc tất cả ký tự còn lại** từ một `Reader` rồi ghi chúng vào một `Writer` **theo thứ tự đọc**. Giá trị `long` trả về là **số đơn vị ký tự được chuyển**, **không phải số byte**. Khi hoàn tất thành công, reader ở vị trí cuối luồng. Phương thức **không tự đóng reader hoặc writer**.

Đối chiếu với API byte:

~~~java
long numberOfBytes = inputStream.transferTo(outputStream);
~~~

`InputStream.transferTo(OutputStream)` có từ Java 9, đọc/ghi **byte** và trả **số byte** được chuyển. Hai phương thức giống tên nhưng khác đối tượng, kiểu dữ liệu và ý nghĩa số đếm.

**Quy tắc lựa chọn:** Nếu phải bảo toàn chính xác file ZIP, ảnh, PDF, dữ liệu mã hóa hay nội dung binary bất kỳ, dùng luồng **byte**. Nếu đang xử lý nội dung **text** và muốn chuyển giữa Reader/Writer hoặc đổi charset một cách có chủ đích, dùng luồng **ký tự**.

## 2. Bảng so sánh trực tiếp

| Thuộc tính | Luồng byte | Luồng ký tự |
| --- | --- | --- |
| Lớp đầu vào | `InputStream` | `Reader` |
| Lớp đầu ra | `OutputStream` | `Writer` |
| Đơn vị dữ liệu | Byte 8 bit | `char` Java, một đơn vị mã UTF-16 16 bit |
| Transfer API | `InputStream.transferTo(OutputStream)` | `Reader.transferTo(Writer)` |
| Mốc có API `transferTo` | Java 9 | Java 10 |
| Giá trị trả về | `long`, số byte được chuyển | `long`, số đơn vị ký tự được chuyển |
| Charset | Không tự giải mã/mã hóa nội dung | Cần chú ý charset tại điểm nối byte/ký tự |
| Bảo toàn dữ liệu binary | Phù hợp | Không phù hợp vì giải mã/mã hóa có thể đổi byte |
| Tình huống điển hình | Sao chép ảnh, ZIP, payload binary | Chuyển văn bản, đọc chuỗi, ghi tài liệu text |
| Kết thúc transfer | Đọc đến EOF, không tự đóng hai luồng | Đọc đến EOF, không tự đóng hai luồng |
| Ví dụ nguồn trong bộ nhớ | `ByteArrayInputStream` | `StringReader` |
| Ví dụ đích trong bộ nhớ | `ByteArrayOutputStream` | `StringWriter` |

Đừng nhầm `java.io.Reader`/`Writer` với `java.util.stream.Stream`. Java Stream API (`map`, `filter`, `collect`) phục vụ xử lý chuỗi phần tử; nó không phải một lớp thay thế trực tiếp cho I/O stream đọc/ghi tệp.

## 3. Vì sao số ký tự không bằng số byte?

Đây là điểm quan trọng nhất của đề bài. Một ký tự Unicode có thể cần nhiều byte khi được mã hóa bằng UTF-8. Trong Java, kiểu `char` biểu diễn **một đơn vị mã UTF-16**, nên một code point ngoài Basic Multilingual Plane (ví dụ emoji) dùng **hai** giá trị `char` (một surrogate pair).

Ví dụ chuỗi gồm:

- `A`: một code point, một `char`, một byte UTF-8.
- `é`: một code point, một `char`, hai byte UTF-8.
- `你`: một code point, một `char`, ba byte UTF-8.
- `😀`: một code point, **hai `char`**, bốn byte UTF-8.

Tổng:

| Chỉ số đo | Kết quả |
| --- | ---: |
| Số Unicode code point | 4 |
| Số đơn vị UTF-16 (`String.length()`) | 5 |
| Số byte khi mã hóa UTF-8 | 10 |
| Kết quả `Reader.transferTo` trên chuỗi đó | 5 |
| Kết quả `InputStream.transferTo` trên byte UTF-8 của chuỗi | 10 |

Đoạn code dùng Unicode escapes để nguồn Java không phụ thuộc việc trình soạn thảo đang hiển thị đúng các ký tự ngoài ASCII:

~~~java
String text = "A\u00E9\u4F60\uD83D\uDE00";

var utf8 = text.getBytes(StandardCharsets.UTF_8);
System.out.println(text.length());                         // 5
System.out.println(text.codePointCount(0, text.length())); // 4
System.out.println(utf8.length);                           // 10
~~~

Đây là **đoạn trích trong một phương thức**, cần import `StandardCharsets`. Tệp Java chạy đầy đủ được trình bày tại mục 8.

**Không đồng nhất ba phép đếm:**

1. **Byte**: kích thước dữ liệu đã mã hóa (ở đây là UTF-8).
2. **UTF-16 code unit / Java `char`**: đơn vị mà `Reader` và `Writer` trao đổi.
3. **Unicode code point**: đơn vị ký tự Unicode trừu tượng, có thể tương ứng một hoặc hai `char` Java.

Ngoài ra, “ký tự người dùng nhìn thấy” (*grapheme cluster*) có thể chứa nhiều code point, ví dụ chữ cái kết hợp dấu. Vì vậy số ký tự hiển thị cũng không phải lúc nào bằng số code point. `Reader.transferTo` **không** đếm grapheme cluster.

## 4. `Reader.transferTo(Writer)` hoạt động ra sao?

Chữ ký chính:

~~~java
public long transferTo(Writer out) throws IOException
~~~

Cách dùng:

~~~java
try (var reader = new StringReader("Hello Java");
     var writer = new StringWriter()) {
    long chars = reader.transferTo(writer);
    System.out.println(chars);             // 10
    System.out.println(writer.toString()); // Hello Java
}
~~~

Đoạn này cần import `StringReader`, `StringWriter` và đặt trong phương thức có xử lý `IOException`. `StringReader` là đầu vào ký tự từ một `String`; `StringWriter` gom ký tự thành một bộ đệm trong bộ nhớ.

Hành vi chính của `transferTo`:

1. Bắt đầu ở **vị trí đọc hiện tại** của reader; không tự reset về đầu.
2. Đọc các ký tự còn lại tới EOF của reader.
3. Ghi chúng sang writer theo đúng thứ tự đọc.
4. Trả `long` là số đơn vị ký tự đã chuyển.
5. Khi thành công, reader nằm ở cuối luồng.
6. Không tự đóng reader hay writer.
7. Có thể chặn khi cần đợi đầu vào hoặc đích ghi; với nguồn vô hạn không có EOF, lời gọi có thể tiếp tục chờ vô hạn.
8. Có thể ném `IOException` nếu xảy ra lỗi I/O. Trong trường hợp lỗi giữa chừng, một phần nội dung có thể đã được ghi; không bảo đảm rollback.

Nếu đối số `out` bằng `null`, phương thức ném `NullPointerException`. Dùng một writer thực sự, không dùng `reader.transferTo(null)` với kỳ vọng bỏ qua dữ liệu.

### 4.1. Đọc từ vị trí hiện tại, không phải luôn toàn bộ nguồn

~~~java
var reader = new StringReader("ABCDE");
reader.read();                   // Đã đọc A.
var writer = new StringWriter();

long count = reader.transferTo(writer);
// count == 4; writer.toString().equals("BCDE")
~~~

`transferTo` không mở lại nguồn, không đọc lại những ký tự đã bị tiêu thụ. Điều này đặc biệt quan trọng khi reader được chia sẻ với một parser khác: nếu parser đọc trước một đoạn, transfer chỉ chuyển phần **còn lại**.

### 4.2. Không tự đóng hoặc flush writer

~~~java
var reader = new StringReader("Hi");
var writer = new StringWriter();
reader.transferTo(writer);
writer.write("!");
// writer.toString() là "Hi!"
~~~

Trong ví dụ này writer vẫn dùng tiếp được vì `transferTo` không đóng nó. Tuy nhiên, việc chuyển dữ liệu sang một `BufferedWriter` hay `OutputStreamWriter` có **đệm đầu ra** không đồng nghĩa các byte đã lập tức được đẩy ra thiết bị/tệp/đường truyền. Nếu tiếp tục giữ writer mở và cần đích nhận dữ liệu ngay, hãy gọi `writer.flush()` theo hợp đồng của writer.

Nếu writer sở hữu tài nguyên, nên sử dụng **try-with-resources** để tự động đóng đúng chỗ; khi đóng, writer cụ thể có thể flush dữ liệu còn trong bộ đệm trước khi giải phóng tài nguyên.

### 4.3. Lỗi giữa chừng không phải một transaction

Giả sử reader đọc được 100 ký tự rồi đích ghi gặp lỗi mạng. `transferTo` có thể ném `IOException` **sau khi đã ghi một phần**. Không có bảo đảm rollback nội dung đích. Phải định nghĩa chiến lược xử lý thất bại như xóa tệp đích chưa hoàn thành, ghi ra tệp tạm rồi đổi tên sau khi copy thành công, hoặc đánh dấu job thất bại để làm lại theo giao thức có kiểm soát.

Với nguồn/đích có đóng bất đồng bộ hay thread bị interrupt khi đang chuyển, cách hành xử có thể phụ thuộc implementation reader/writer. Không dùng `interrupt` làm cơ chế hủy luôn đáng tin cậy cho mọi loại I/O; thiết kế timeout/cancellation theo loại kết nối thực tế.

## 5. `InputStream.transferTo(OutputStream)` khác ở đâu?

Một API tương ứng cho dữ liệu thô:

~~~java
byte[] original = {0, 1, (byte) 0xFF};

try (var input = new ByteArrayInputStream(original);
     var output = new ByteArrayOutputStream()) {
    long count = input.transferTo(output);
    System.out.println(count); // 3
    System.out.println(Arrays.equals(original, output.toByteArray())); // true
}
~~~

Đoạn code trên cần import `ByteArrayInputStream`, `ByteArrayOutputStream` và `Arrays`. Không có bước giải mã thành Unicode: byte `0xFF` được sao chép nguyên trạng dù nó **không phải một byte UTF-8 hợp lệ đứng một mình**.

Vì vậy, với file có format binary hoặc cần bảo toàn **byte-for-byte**, chọn `InputStream`/`OutputStream` hoặc API sao chép byte khác như `Files.copy`. `Reader`/`Writer` không phù hợp với việc sao chép tệp ZIP, ảnh JPEG/PNG, các bản ghi binary, tệp nén hay payload mã hóa.

### 5.1. Tại sao không dùng `Reader` cho ZIP hoặc ảnh?

Khi đưa byte vào `InputStreamReader`, nó áp dụng một bộ giải mã ký tự theo charset. Một dãy byte bất kỳ có thể không hợp lệ theo charset đó. Decoder có thể thay byte lỗi bằng ký tự thay thế hoặc ném lỗi, tùy cấu hình. Khi đưa các ký tự thu được vào `OutputStreamWriter`, encoder tạo ra byte mới. Dữ liệu có thể **không còn trùng** với byte ban đầu.

Ví dụ:

~~~java
byte[] binary = {0, (byte) 0xFF, 1};
byte[] roundTrip = new String(binary, StandardCharsets.UTF_8)
        .getBytes(StandardCharsets.UTF_8);

System.out.println(Arrays.equals(binary, roundTrip)); // false
~~~

`0xFF` là byte đơn lẻ không hợp lệ trong UTF-8. `new String(byte[], charset)` thay thế nội dung không hợp lệ theo hợp đồng của nó, nên mã hóa lại không tạo byte gốc. Dữ liệu nhị phân bị biến đổi ngay cả khi **đọc và ghi cùng một tên charset UTF-8**.

### 5.2. Đừng dùng binary round-trip như một cách kiểm tra text

Nếu đầu vào là văn bản UTF-8 hợp lệ và cả hai đầu dùng đúng UTF-8, pipeline decode → encode có thể trả đúng byte gốc cho ví dụ cơ bản. Nhưng **mục tiêu của Writer là tạo biểu diễn byte theo charset**, không phải cam kết mọi dãy byte đầu vào sẽ được bảo toàn.

Các trường hợp phải xét riêng bao gồm byte lỗi, BOM, charset khác nhau, lựa chọn chính sách decoder/encoder, ký tự không được hỗ trợ ở đích và các bước xử lý text khác (chuẩn hóa, thay dòng, bỏ dấu...). Muốn hợp đồng bảo toàn byte, không đi qua tầng ký tự.

## 6. Hai cầu nối giữa byte và ký tự

Java có hai lớp quan trọng để chuyển giữa hai miền:

~~~text
             ĐỌC VĂN BẢN TỪ BYTE
  byte[] / InputStream
            |
            | InputStreamReader(..., charset)
            v
     Reader / ký tự Java
            |
            | Reader.transferTo(...)
            v
     Writer / ký tự Java
            |
            | OutputStreamWriter(..., charset)
            v
     OutputStream / byte[]
             GHI VĂN BẢN RA BYTE
~~~

### 6.1. `InputStreamReader`: byte → ký tự

~~~java
var reader = new InputStreamReader(
        new ByteArrayInputStream(utf8Bytes),
        StandardCharsets.UTF_8);
~~~

`InputStreamReader` giải mã byte theo `UTF_8` thành các `char` mà Reader cung cấp. Reader **không thể tự suy ra charset chính xác từ mọi luồng byte**. Hãy lấy charset từ định dạng file, HTTP header có ý nghĩa, protocol hoặc hợp đồng dữ liệu, thay vì đoán bừa.

Nhiều reader có thể đọc trước (*read-ahead*) thêm byte từ input để giải mã hiệu quả. Nếu đang dùng `InputStreamReader`, không nên đan xen tự tiện việc đọc trực tiếp từ chính underlying `InputStream` rồi quay lại đọc reader; vị trí và bộ đệm decoder có thể khiến kết quả khó dự đoán.

### 6.2. `OutputStreamWriter`: ký tự → byte

~~~java
var writer = new OutputStreamWriter(
        destinationOutputStream,
        StandardCharsets.UTF_8);
~~~

`OutputStreamWriter` nhận `char` Java, chuyển thành byte UTF-8 rồi ghi sang `OutputStream`. Nếu muốn tạo văn bản UTF-16LE ở đích, thay bằng `StandardCharsets.UTF_16LE`; **số đơn vị ký tự mà `Reader.transferTo` trả về có thể vẫn bằng nhau**, nhưng số byte/định dạng byte của tệp đích sẽ khác.

### 6.3. Về `BufferedReader` và `BufferedWriter`

Có thể bọc các cầu nối để đọc/ghi văn bản thuận tiện và giảm số thao tác I/O:

~~~java
var reader = new BufferedReader(
        new InputStreamReader(sourceBytes, StandardCharsets.UTF_8));
var writer = new BufferedWriter(
        new OutputStreamWriter(targetBytes, StandardCharsets.UTF_8));

long chars = reader.transferTo(writer);
writer.flush();
~~~

Đoạn này giả định `sourceBytes` là `InputStream`, `targetBytes` là `OutputStream` đã được cung cấp và tài nguyên được đóng ở scope sở hữu chúng. Dùng try-with-resources khi tạo reader/writer trong method thực tế.

`BufferedReader` và `BufferedWriter` vẫn thuộc **luồng ký tự**. Bọc buffer không biến chúng thành luồng byte và cũng không thay đổi ý nghĩa `chars` — vẫn là số đơn vị ký tự.

## 7. Charset nên luôn được nêu rõ ở ranh giới I/O

### 7.1. Vì sao charset mặc định có thể nguy hiểm?

Các overload không truyền charset có thể phụ thuộc cấu hình JVM/môi trường. Java 18 trở đi chuẩn hóa default charset về UTF-8 trong phần lớn tình huống thông thường theo JEP 400; các hệ thống chạy Java 17 trở xuống có thể có default charset phụ thuộc môi trường. Trong cả hai trường hợp, **giao thức/tệp có định dạng xác định vẫn nên chỉ rõ charset**.

Đúng khi hợp đồng dữ liệu là UTF-8:

~~~java
new InputStreamReader(input, StandardCharsets.UTF_8)
new OutputStreamWriter(output, StandardCharsets.UTF_8)
~~~

Cẩn trọng:

~~~java
new InputStreamReader(input)  // Không nêu rõ charset.
new OutputStreamWriter(output) // Không nêu rõ charset.
~~~

Không mặc định một file có phần mở rộng `.txt` chắc chắn UTF-8. Kiểm tra tài liệu định dạng hoặc siêu dữ liệu đáng tin cậy. Với byte không phải UTF-8, dùng charset đúng được chỉ định; nếu không biết mã hóa, có thể cần quy trình phát hiện/trao đổi charset có kiểm soát, không đơn giản “cứ thử UTF-8”.

### 7.2. Khi chuyển mã (transcoding)

Một trường hợp có chủ đích:

~~~java
try (var reader = new InputStreamReader(input, StandardCharsets.ISO_8859_1);
     var writer = new OutputStreamWriter(output, StandardCharsets.UTF_8)) {
    long chars = reader.transferTo(writer);
}
~~~

Đây là **đoạn trích trong phương thức** có `input` và `output` là các byte streams đã được khởi tạo. Nó giải mã văn bản Latin-1 thành ký tự Java, rồi mã hóa sang UTF-8. Giá trị trả về `chars` là **số đơn vị UTF-16 đã chuyển**, không phải kích thước byte Latin-1 đầu vào và cũng không phải kích thước byte UTF-8 đầu ra.

Trong ví dụ này, try-with-resources đóng các wrapper và theo đó đóng underlying streams. Nếu underlying stream do code khác sở hữu (ví dụ socket/protocol stream cần tiếp tục dùng), cần thiết kế rõ trách nhiệm đóng và giới hạn dữ liệu trước khi bọc; không vô tình đóng tài nguyên do bên khác quản lý.

### 7.3. Khi muốn báo lỗi thay vì thay ký tự hỏng

Một số convenience decoding API có thể dùng chính sách **thay thế** chuỗi byte không hợp lệ bằng ký tự replacement. Với dữ liệu quan trọng, có thể yêu cầu báo lỗi:

~~~java
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

decoder.decode(ByteBuffer.wrap(binaryBytes)); // Có thể ném CharacterCodingException.
~~~

Đoạn này giả định `binaryBytes` là `byte[]`, cần import `StandardCharsets`, `CodingErrorAction` và `ByteBuffer`; code gọi cần xử lý `CharacterCodingException`. Đối với I/O đọc streaming, có thể truyền `CharsetDecoder` đã cấu hình vào constructor `InputStreamReader` và xử lý lỗi giải mã phát sinh. Cần lựa chọn rõ: **báo lỗi**, **thay thế ký tự** hay chiến lược phù hợp khác. Đừng âm thầm thay byte hỏng nếu hợp đồng yêu cầu toàn vẹn văn bản.

## 8. Chương trình Java 17+ hoàn chỉnh, đã kiểm thử

Chương trình dưới đây minh họa trên một chuỗi chứa ASCII, ký tự có dấu, ký tự CJK và emoji. Nó so sánh **số code unit**, **code point**, **byte UTF-8**, hai overload `transferTo`, pipeline Reader/Writer qua charset bridge, dữ liệu binary không hợp lệ và quyền sở hữu writer.

~~~java
// File: ReaderVsByteTransferDemo.java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ReaderVsByteTransferDemo {
    public static void main(String[] args) throws Exception {
        String text = "A\u00E9\u4F60\uD83D\uDE00";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-16 code units = " + text.length());
        System.out.println("Unicode code points = " + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes = " + utf8.length);

        try (var source = new StringReader(text);
             var destination = new StringWriter()) {
            long chars = source.transferTo(destination);
            System.out.println("Reader transferred = " + chars);
            System.out.println("Reader content matches = " + text.equals(destination.toString()));
            System.out.println("Reader EOF = " + (source.read() == -1));
        }

        try (var source = new ByteArrayInputStream(utf8);
             var destination = new ByteArrayOutputStream()) {
            long bytes = source.transferTo(destination);
            System.out.println("InputStream transferred = " + bytes);
            System.out.println("Byte content matches = "
                    + Arrays.equals(utf8, destination.toByteArray()));
        }

        var encoded = new ByteArrayOutputStream();
        long bridgedChars;
        try (var reader = new BufferedReader(new InputStreamReader(
                    new ByteArrayInputStream(utf8), StandardCharsets.UTF_8));
             var writer = new BufferedWriter(
                    new OutputStreamWriter(encoded, StandardCharsets.UTF_8))) {
            bridgedChars = reader.transferTo(writer);
        }
        System.out.println("Bridge transferred chars = " + bridgedChars);
        System.out.println("Bridge bytes match = " + Arrays.equals(utf8, encoded.toByteArray()));

        byte[] binary = {0, (byte) 0xff, 1};
        byte[] textRoundTrip = new String(binary, StandardCharsets.UTF_8)
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Binary text round-trip identical = "
                + Arrays.equals(binary, textRoundTrip));

        try {
            var decoder = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);
            decoder.decode(ByteBuffer.wrap(binary));
            System.out.println("Strict UTF-8 rejected = false");
        } catch (CharacterCodingException expected) {
            System.out.println("Strict UTF-8 rejected = true");
        }

        var reader = new StringReader("Hi");
        var writer = new StringWriter();
        reader.transferTo(writer);
        writer.write("!");
        System.out.println("Writer still usable = " + writer.toString().equals("Hi!"));
        reader.close();
        writer.close();
    }
}
~~~

Lưu file dưới tên chính xác `ReaderVsByteTransferDemo.java`, rồi chạy từ thư mục chứa file:

~~~bash
javac --release 17 ReaderVsByteTransferDemo.java
java ReaderVsByteTransferDemo
~~~

Đầu ra chính xác đã kiểm chứng với JDK 24 và target Java 17:

~~~text
UTF-16 code units = 5
Unicode code points = 4
UTF-8 bytes = 10
Reader transferred = 5
Reader content matches = true
Reader EOF = true
InputStream transferred = 10
Byte content matches = true
Bridge transferred chars = 5
Bridge bytes match = true
Binary text round-trip identical = false
Strict UTF-8 rejected = true
Writer still usable = true
~~~

**Phân tích đầu ra theo từng phần:**

1. `text.length()` trả `5` vì emoji được biểu diễn bằng hai UTF-16 code unit. `codePointCount(...)` trả `4` vì chuỗi có bốn code point Unicode.
2. `utf8.length` là `10` vì số byte của các ký tự khi mã hóa UTF-8 lần lượt là `1 + 2 + 3 + 4`.
3. `StringReader.transferTo(StringWriter)` trả `5`, viết đúng các đơn vị ký tự; sau khi thành công, đọc tiếp trả `-1` (EOF). Kết quả Writer có cùng nội dung ký tự với nguồn.
4. `ByteArrayInputStream.transferTo(ByteArrayOutputStream)` trả `10` và mảng byte đích khớp chính xác byte nguồn.
5. Khi đi qua `InputStreamReader`/`OutputStreamWriter` cùng UTF-8, `Reader.transferTo` ở giữa vẫn đếm **5 đơn vị ký tự**. File/byte đích có thể gồm **10 byte**; ví dụ văn bản UTF-8 hợp lệ này round-trip chính xác.
6. `0xFF` trong mảng binary không phải UTF-8 hợp lệ; giải mã rồi mã hóa lại không bảo toàn các byte. Cấu hình decoder ở chế độ `REPORT` phát hiện lỗi thay vì âm thầm biến đổi nội dung.
7. `Reader.transferTo` không đóng `StringWriter`; ví dụ ghi thêm `!` sau khi transfer thành công.

**Lưu ý về kết quả tái lập:** Chương trình chỉ in số, boolean và chữ ASCII, nên không phụ thuộc khả năng hiển thị emoji/tiếng Việt của console. Nội dung Unicode vẫn được kiểm tra bằng `equals` và `Arrays.equals`.

## 9. Sao chép tệp văn bản bằng `Reader.transferTo`

Nếu input là văn bản UTF-8 và cần xuất ra văn bản UTF-8 ở tệp khác:

~~~java
// Đoạn code đặt trong phương thức throws IOException.
Path source = Path.of("input.txt");
Path destination = Path.of("output.txt");

try (var reader = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     var writer = Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {
    long chars = reader.transferTo(writer);
    System.out.println("Transferred UTF-16 code units: " + chars);
}
~~~

Cần import `java.nio.file.Path`, `java.nio.file.Files` và `java.nio.charset.StandardCharsets`. `Files.newBufferedReader` trả `BufferedReader`, `Files.newBufferedWriter` trả `BufferedWriter`, cả hai xử lý ký tự. Đây là cách gọn dùng API vẫn hiện hành trên Java 17+.

Các điểm phải kiểm tra khi chuyển sang production:

- **Charset nguồn và đích**: dùng đúng charset định dạng file yêu cầu.
- **Tệp đích**: `newBufferedWriter` với các tùy chọn mặc định có thể tạo hoặc ghi đè/truncate nội dung tệp đích; chỉ dùng khi bạn thực sự muốn hành vi đó.
- **Ngắt dòng**: `Reader.transferTo` chuyển các ký tự theo thứ tự; không tự tách dòng, không tự loại `\r` hoặc `\n`. Nếu muốn chuẩn hóa line ending, cần logic text riêng.
- **Lỗi giữa chừng**: writer có thể đã ghi một phần. Với dữ liệu quan trọng, cân nhắc ghi tệp tạm trong cùng filesystem, đóng/flush thành công rồi chuyển/đổi tên theo giao thức phù hợp để tránh công bố tệp nửa chừng.
- **Tệp lớn**: không cần gọi `Files.readString` để nạp toàn bộ file vào một `String` trước khi transfer. API Reader/Writer có thể xử lý theo luồng, nhưng bộ nhớ và hiệu năng thực tế tùy các wrapper/implementation.
- **Không biến đổi nội dung**: nếu mục đích là bản sao byte-for-byte của tệp văn bản, `Files.copy` hoặc luồng byte là lựa chọn rõ hơn. Dùng Reader/Writer khi việc giải mã/mã hóa **là chủ đích**.

### 9.1. Nếu cần bảo toàn byte

~~~java
try (var input = Files.newInputStream(source);
     var output = Files.newOutputStream(destination)) {
    long bytes = input.transferTo(output);
    System.out.println("Transferred bytes: " + bytes);
}
~~~

Đoạn này vẫn cần import `Files`, `Path` và phương thức có xử lý `IOException`. Nó hoạt động trên byte, không áp dụng charset, nên thích hợp với tệp binary và trường hợp bắt buộc giữ nguyên từng byte. Cân nhắc policy ghi đè đích giống phần trên.

Trong nhiều use case sao chép file thuần túy, `Files.copy(source, destination, ...)` còn thể hiện ý định rõ hơn và tránh viết vòng đời stream thủ công. API này cũng xử lý dữ liệu **byte**, không yêu cầu chuyển thành `Reader`.

## 10. Không nhầm `transferTo` với `readLine` hoặc biến đổi text

`Reader.transferTo` **chuyển nguyên chuỗi đơn vị ký tự còn lại**, không phân tích nội dung ở cấp dòng. `BufferedReader.readLine` lại là một thao tác khác: nó đọc một dòng và **không trả lại** dấu kết thúc dòng trong chuỗi kết quả.

Ví dụ:

~~~java
var text = "A\r\nB\n";
var reader = new StringReader(text);
var writer = new StringWriter();
reader.transferTo(writer);
// writer.toString().equals(text) == true
~~~

`transferTo` giữ `\r\n` và `\n` như các ký tự trong chuỗi được chuyển. Trái lại, nếu code tự duyệt `readLine()` và viết lại mỗi dòng bằng `newLine()`, output có thể đổi line ending theo nền tảng hoặc logic của ứng dụng. Vì vậy:

- Cần chuyển **text giữ nguyên các ký tự đang có** → `Reader.transferTo`.
- Cần phân tích và chuẩn hóa từng dòng → `BufferedReader.readLine` + logic xử lý rõ ràng.
- Cần giữ **nguyên từng byte** kể cả encoding và BOM → `InputStream`/`OutputStream` hoặc `Files.copy`.

Ngoài ra, `transferTo` không tự chuẩn hóa Unicode NFC/NFD; hai cách biểu diễn Unicode khác nhau có thể nhìn giống nhau trên màn hình nhưng là các chuỗi code unit khác nhau. Chuẩn hóa Unicode là một bước nghiệp vụ riêng, ví dụ dùng `java.text.Normalizer` khi thật sự cần.

## 11. Charset, BOM và giới hạn của “copy text”

### 11.1. Byte Order Mark

Một số định dạng UTF có thể có BOM (*byte-order mark*). BOM là thông tin ở **mức byte/encoding**, không phải một khái niệm tương đương “một ký tự nội dung người dùng nhìn thấy” trong mọi charset. Cách encoder/decoder xử lý BOM tùy charset cụ thể: `UTF-16`, `UTF-16BE`, `UTF-16LE` có hành vi khác nhau; UTF-8 có thể chứa BOM trong input.

Nếu mục tiêu là **giữ byte gốc không thay đổi**, Reader/Writer không đủ để cam kết giữ BOM y hệt. Nếu mục tiêu là chuyển đổi encoding theo quy tắc, phải quy định rõ xử lý BOM, không chỉ cùng gọi `transferTo`.

### 11.2. Charset không hỗ trợ một ký tự

Giả sử đầu vào có emoji nhưng writer đích dùng charset hạn chế như `US_ASCII`. Charset đó không biểu diễn trực tiếp emoji. Encoder có thể báo lỗi hoặc dùng ký tự thay thế theo chính sách. Vì thế việc `Reader.transferTo` chuyển “đúng số `char`” **không có nghĩa output byte biểu diễn đầy đủ mọi ký tự gốc**.

Với dữ liệu cần toàn vẹn, dùng encoder với chính sách `CodingErrorAction.REPORT` khi phù hợp:

~~~java
var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

var writer = new OutputStreamWriter(outputStream, encoder);
~~~

Đoạn này giả định `outputStream` đã tồn tại và sẽ được đóng theo scope sở hữu; import `StandardCharsets`, `CodingErrorAction`, `OutputStreamWriter`. Việc báo lỗi khi mã hóa ký tự không biểu diễn được làm rõ chất lượng dữ liệu và tránh âm thầm thay thế.

### 11.3. Khi nào cần quan tâm surrogate pair?

Java `Reader` và `Writer` làm việc với `char`; một code point có thể cần hai `char`. `transferTo` đếm đủ **hai** đơn vị cho một surrogate pair. Không tự cắt `char[]` thành từng ký tự rồi giả định mỗi `char` là một Unicode code point hoàn chỉnh.

Nếu muốn thao tác theo code point (ví dụ đếm số ký tự Unicode trừu tượng), hãy giải mã nội dung thành chuỗi/code point và dùng API phù hợp như `String.codePoints()` hoặc `codePointCount()`. Đây là lớp xử lý khác với API chuyển I/O.

Đối với giao diện người dùng, một grapheme cluster còn có thể gồm nhiều code point, nên không dùng `Reader.transferTo` để đếm “số chữ người dùng nhìn thấy”.

## 12. Xử lý ngoại lệ, trách nhiệm đóng và quyền sở hữu tài nguyên

### 12.1. Dùng try-with-resources để không rò rỉ tài nguyên

~~~java
try (Reader reader = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     Writer writer = Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {
    long chars = reader.transferTo(writer);
    // Có thể dùng giá trị chars cho metric hoặc kiểm tra logic.
}
~~~

Đoạn code cần import `Reader`, `Writer`, `Files`, `StandardCharsets` và `Path`; đặt trong method có xử lý `IOException`.

Thứ tự đóng theo try-with-resources là ngược thứ tự khai báo (writer đóng trước reader). Khi có exception, cơ chế này vẫn cố đóng tài nguyên, giúp hạn chế rò rỉ. Không phải `transferTo` tự đóng tài nguyên: **scope try-with-resources** mới chịu trách nhiệm đó.

### 12.2. Không vô tình đóng stream do bên khác sở hữu

Một ví dụ dễ gặp là nhận một `OutputStream` từ HTTP response hoặc một đối tượng được framework quản lý. Nếu bạn bọc nó bằng `OutputStreamWriter` rồi dùng try-with-resources, đóng wrapper có thể đóng cả underlying stream, đôi khi sớm hơn mong muốn của framework. Cần tuân thủ hợp đồng sở hữu tài nguyên: code tạo stream có chịu trách nhiệm đóng không? Framework có quản lý lifecycle không?

Không có một quy tắc “luôn đóng” áp dụng cho mọi stream được truyền vào. `Reader.transferTo` cố ý **không đóng** nguồn/đích để caller kiểm soát vòng đời.

### 12.3. Xử lý `IOException` có thể xuất hiện sau một phần transfer

~~~java
try (var reader = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     var writer = Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {
    reader.transferTo(writer);
} catch (IOException failure) {
    // Ghi nhận lỗi, xử lý file đích có thể chưa hoàn chỉnh theo chính sách ứng dụng.
    throw failure;
}
~~~

Đây là đoạn minh họa trong method khai báo `throws IOException`, không phải file Java độc lập. Đừng khẳng định đích luôn rỗng hay luôn được rollback sau exception. Với nguồn mạng, vấn đề có thể phức tạp hơn vì đã có dữ liệu ghi ra bên ngoài.

### 12.4. Không dùng `transferTo` với nguồn vô hạn nếu không có giới hạn

`transferTo` đọc **đến EOF**. Với một socket, một reader cung cấp dữ liệu liên tục, hoặc giao thức không có ranh giới kết thúc, lời gọi có thể chặn lâu hoặc không kết thúc. Nếu cần “chỉ đọc 1.000 ký tự”, “chỉ copy một bản tin” hoặc có deadline, nên dùng giao thức khung dữ liệu/giới hạn và vòng lặp đọc phù hợp; `transferTo` đơn thuần không có tham số maxChars hay timeout riêng.

## 13. Hiệu năng và phân bổ bộ nhớ

`Reader.transferTo` làm giảm code lặp kiểu đọc buffer rồi ghi buffer, chứ không phải lời cam kết “luôn nhanh nhất” hoặc “sao chép zero-copy”.

Vòng lặp thủ công tương đương về mặt ý tưởng:

~~~java
char[] buffer = new char[8192];
int n;
while ((n = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, n);
}
~~~

Đây là **đoạn minh họa trong method có Reader/Writer và xử lý IOException**. Với implementation chuẩn, `Reader.transferTo` cũng chuyển dữ liệu qua các lần đọc/ghi mà không yêu cầu người dùng tự giữ một `String` chứa toàn bộ nội dung.

Nhưng không nên suy ra mỗi tùy chọn đều có cùng chi phí:

- `StringReader`/`StringWriter` là các đối tượng trong bộ nhớ, phù hợp cho ví dụ, nhưng `StringWriter` tích lũy toàn bộ output thành chuỗi/buffer.
- Với file lớn, một pipeline `BufferedReader` → `BufferedWriter` có thể tránh nạp toàn bộ nội dung vào RAM, nhưng vẫn phụ thuộc bộ đệm và triển khai cụ thể.
- Khi chỉ copy byte, `InputStream.transferTo` hoặc `Files.copy` thường tránh được bước giải mã/mã hóa cần thiết cho Reader/Writer.
- Khi thực sự **chuyển charset**, chi phí decode/encode là chủ đích; không coi nó là “lãng phí” nếu định dạng đích yêu cầu.
- Với byte stream, một số hệ thống có thể tối ưu bằng cơ chế chuyên biệt ở tầng OS/API; không tự suy ra `Reader.transferTo` có cơ chế zero-copy tương tự.
- Muốn kết luận phương án nào nhanh hơn, benchmark đúng kích thước dữ liệu, thiết bị, charset, buffer và mẫu workload của hệ thống.

Giá trị `long` trả về không phải dung lượng bộ nhớ sử dụng. Nó đơn giản là số byte hoặc số code unit đã chuyển tùy API.

## 14. Các lỗi dễ gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`Reader.transferTo` copy byte.” | Nó chuyển **ký tự** giữa Reader và Writer. |
| “Giá trị trả về của `Reader.transferTo` là số byte file.” | Không; là số đơn vị ký tự UTF-16 đã chuyển. |
| “Một Unicode code point luôn bằng một Java `char`.” | Sai; code point ngoài BMP cần surrogate pair gồm hai `char`. |
| “Một Java `char` luôn tương đương một byte UTF-8.” | Không; encoding có độ dài biến đổi, chẳng hạn UTF-8. |
| “`Reader` tự đoán chính xác encoding của mọi file.” | Không; phải chọn charset theo hợp đồng dữ liệu. |
| “`Reader.transferTo` tự tạo byte đầu ra.” | Chỉ khi Writer đích là cầu nối sang byte; việc encode thuộc `OutputStreamWriter`. |
| “`InputStream.transferTo` và `Reader.transferTo` luôn trả cùng số.” | Không; đếm các đơn vị khác nhau. |
| “Có thể dùng Reader/Writer copy ảnh/ZIP an toàn.” | Không nên; byte binary có thể bị giải mã sai và mã hóa lại khác. |
| “Chỉ cần hai đầu UTF-8 thì mọi file binary được giữ nguyên.” | Sai; byte đầu vào có thể không phải UTF-8 hợp lệ. |
| “`transferTo` tự đóng cả hai luồng.” | Sai; caller quản lý close bằng try-with-resources hoặc hợp đồng riêng. |
| “`transferTo` luôn flush writer trước khi trả về.” | Không nên dựa vào điều đó; flush/close theo yêu cầu writer. |
| “`transferTo` luôn reset reader về đầu.” | Không; nó bắt đầu tại vị trí đọc hiện tại. |
| “`Reader.transferTo` tự thay đổi line endings.” | Không; nó chuyển ký tự theo thứ tự. |
| “`readLine` và `transferTo` cho output y hệt mọi lúc.” | Không; `readLine` bỏ dấu phân cách dòng trong chuỗi trả về. |
| “Đọc và encode lại văn bản luôn cho byte gốc, kể cả BOM/lỗi charset.” | Không; muốn copy byte chính xác hãy dùng byte stream. |
| “`transferTo` thất bại thì writer không có byte/ký tự nào.” | Sai; lỗi có thể xảy ra sau khi đã ghi một phần. |
| “`Reader.transferTo` hiểu luôn số ký tự hiển thị.” | Không; nó đếm UTF-16 code units, không phải grapheme clusters. |
| “Dùng `BufferedReader` làm kết quả trả về biến thành số byte.” | Không; buffer không đổi miền dữ liệu. |

## 15. Tình huống áp dụng thực tế

### 15.1. Sao chép file JSON có encoding xác định

JSON trên mạng thường được phát dưới dạng UTF-8 theo quy tắc tương ứng. Khi cần đọc/viết **dữ liệu text** và có lý do xử lý ở mức ký tự, dùng Reader/Writer kèm charset rõ. Nhưng nếu nhiệm vụ chỉ là lưu lại đúng **payload byte** nhận được để đối chiếu chữ ký số/hash, hãy giữ bản gốc bằng byte stream. Decode rồi encode lại có thể không giữ đúng dữ liệu dùng để xác thực chữ ký.

### 15.2. Chuyển đổi file từ một charset sang charset khác

Giả sử hệ thống cần đổi nội dung tệp từ ISO-8859-1 sang UTF-8. `Reader.transferTo` phù hợp làm bước chuyển các ký tự sau khi giải mã:

~~~java
try (var reader = new InputStreamReader(input, StandardCharsets.ISO_8859_1);
     var writer = new OutputStreamWriter(output, StandardCharsets.UTF_8)) {
    reader.transferTo(writer);
}
~~~

Cần xác định input thực sự là Latin-1; nếu dữ liệu gốc không dùng charset ấy, quá trình sẽ sai nội dung. Nếu có ký tự không biểu diễn được ở charset đích, chọn chính sách báo lỗi hoặc thay thế như mục 7.3 và 11.2.

### 15.3. Sao chép tệp PNG

Sử dụng:

~~~java
try (var in = Files.newInputStream(pngPath);
     var out = Files.newOutputStream(copyPath)) {
    in.transferTo(out);
}
~~~

Đây là đoạn trích trong method với `pngPath` và `copyPath` là `Path`. Không dùng `InputStreamReader` và `OutputStreamWriter` cho PNG: đó là dữ liệu binary.

### 15.4. Đọc template text rồi xuất sang Writer

Nếu đã có một `Reader` lấy từ template text và một `Writer` cho response text, `reader.transferTo(writer)` thể hiện đúng ý định chuyển toàn bộ phần ký tự còn lại. Nhưng nếu template cần thay biến, escape HTML, lọc dữ liệu hay biến đổi nội dung, `transferTo` đơn thuần **không thực hiện các xử lý đó**; phải chèn bước xử lý riêng và kiểm tra an toàn ở tầng nghiệp vụ.

### 15.5. Copy response trên socket

Cần cân nhắc ranh giới message và EOF. `transferTo` tiếp tục đọc cho đến khi Reader hết dữ liệu; trên kết nối persistent có nhiều bản tin, một stream có thể không EOF ngay sau bản tin hiện tại. Nếu protocol dùng chiều dài hoặc delimiter, cần cơ chế đọc theo frame; không gọi `transferTo` cho toàn socket với suy nghĩ “nó sẽ tự dừng sau một JSON”.

## 16. Bài tập thực hành có đáp án

### Câu 1 — Đơn vị trả về

~~~java
var source = new StringReader("ABC");
var destination = new StringWriter();
long transferred = source.transferTo(destination);
~~~

**Đáp án:** `transferred == 3`. Nó là số đơn vị ký tự, không phải độ dài byte của một charset nào đó.

### Câu 2 — UTF-8 và ký tự có dấu

~~~java
var text = "é";
var bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

**Đáp án:** `text.length() == 1` nhưng `bytes.length == 2`. Nếu truyền `text` qua `StringReader.transferTo(StringWriter)`, kết quả đếm là `1`.

### Câu 3 — Emoji

~~~java
var text = "\uD83D\uDE00";
~~~

**Đáp án:** `text.length() == 2`, `text.codePointCount(0,text.length()) == 1`, byte UTF-8 khi mã hóa có độ dài `4`. `Reader.transferTo` chuyển hai đơn vị `char`.

### Câu 4 — Byte stream

~~~java
byte[] input = {0, (byte) 0xFF, 1};
~~~

**Hỏi:** Cần copy byte chính xác sang đích, chọn API gì?

**Đáp án:** `InputStream.transferTo(OutputStream)` hoặc API sao chép byte tương đương. Không dùng `Reader`/`Writer` vì `0xFF` không phải UTF-8 hợp lệ đứng riêng.

### Câu 5 — Read sau transfer

~~~java
var reader = new StringReader("HELLO");
reader.read(); // H
var out = new StringWriter();
long n = reader.transferTo(out);
~~~

**Đáp án:** `n == 4`, `out.toString().equals("ELLO")` và đọc tiếp từ reader trả EOF `-1` khi transfer hoàn tất thành công.

### Câu 6 — Thay đổi charset

Input mã hóa bằng ISO-8859-1 và output yêu cầu UTF-8. Hỏi: `Reader.transferTo` nên đặt ở đâu?

**Đáp án:** Giữa `InputStreamReader(input, ISO_8859_1)` và `OutputStreamWriter(output, UTF_8)`. Reader đếm ký tự đã giải mã; hai đầu byte có độ dài có thể khác.

### Câu 7 — Writer đã đóng chưa?

~~~java
var source = new StringReader("Hi");
var destination = new StringWriter();
source.transferTo(destination);
destination.write("!");
~~~

**Đáp án:** Thành công; `transferTo` không đóng Writer. Nếu đích được đệm và cần giao dữ liệu ra ngay, gọi `flush()` theo hợp đồng. Scope sở hữu tài nguyên phải đảm nhận đóng.

### Câu 8 — Dữ liệu binary lỗi charset

`new String(binary, UTF_8).getBytes(UTF_8)` không còn giống byte nguồn. Vì sao?

**Đáp án:** Byte nguồn có thể không giải mã được thành văn bản UTF-8 hợp lệ, dẫn tới replacement hoặc xử lý lỗi; round-trip ký tự không bảo toàn mọi dãy byte nhị phân.

### Câu 9 — Copy và số dòng

Reader có hai dòng văn bản, một dòng kết thúc bằng CRLF, dòng kia kết thúc bằng LF. Hỏi `transferTo` có tự chuyển cả hai thành newline của hệ điều hành không?

**Đáp án:** Không. Nó chuyển các `char` như được đọc, giữ lại CR và LF. Nếu dùng `readLine` rồi `newLine` mới có khả năng viết lại line endings theo lựa chọn của chương trình.

### Câu 10 — Hủy chuyển dữ liệu mạng

`reader.transferTo(writer)` trên socket không có EOF và tiếp tục chặn. Nguyên nhân là gì?

**Đáp án:** Phương thức đọc đến EOF, không có giới hạn byte/char hay timeout riêng. Thiết kế ranh giới message, timeout và cách hủy theo contract của protocol/transport, hoặc vòng lặp đọc có giới hạn.

### Câu 11 — Kết quả khi IOException

Writer đã nhận một phần ký tự rồi ném `IOException`. Có thể tiếp tục và khẳng định file đích còn rỗng không?

**Đáp án:** Không. Output có thể đã ghi một phần; cần cleanup hoặc cơ chế xuất bản tệp chỉ khi hoàn thành.

### Câu 12 — `String.length` có đo số chữ đang nhìn thấy?

**Đáp án:** Không. `String.length` đếm UTF-16 code units, có thể khác code point và số grapheme cluster. `Reader.transferTo` dùng cùng đơn vị đếm ký tự Java trong trường hợp minh họa.

## 17. Checklist khi review code `Reader.transferTo`

- [ ] Nguồn là **text** hay **binary**? Nếu binary, có đang dùng sai Reader/Writer không?
- [ ] Đã xác định charset thực tế của input và định dạng charset output chưa?
- [ ] Reader/Writer có được khởi tạo và quản lý tài nguyên đúng không?
- [ ] Có hiểu số `long` trả về của Reader là **số UTF-16 code unit**, không phải số byte/code point?
- [ ] Có xử lý null, lỗi I/O, output ghi dở và tình huống writer không thể mã hóa ký tự không?
- [ ] Có dùng charset explicit thay vì vô tình dựa vào default không?
- [ ] Dữ liệu có chứa emoji/ký tự Unicode ngoài BMP? Có kiểm thử surrogate pair không?
- [ ] Nếu dữ liệu binary, có kiểm tra bằng `Arrays.equals` hoặc hash byte chứ không kiểm tra chuỗi decode/encode không?
- [ ] Nếu dùng `BufferedWriter` và còn giữ mở, đã flush khi cần chưa?
- [ ] Nếu dùng try-with-resources, có rõ ai sở hữu underlying streams không?
- [ ] Nguồn có EOF xác định không? Có cần timeout/giới hạn kích thước để tránh chuyển vô tận không?
- [ ] Có cần giữ nguyên BOM, line endings hay byte representation để xác thực chữ ký số không?
- [ ] Nếu cần chuyển mã, đã chọn policy `REPORT`/`REPLACE` cho dữ liệu lỗi và ký tự đích không hỗ trợ chưa?
- [ ] Nếu cần chuẩn hóa nội dung, có triển khai bước biến đổi text riêng thay vì kỳ vọng `transferTo` tự xử lý không?
- [ ] Với file lớn, đã tránh nạp toàn bộ vào `String` khi không cần và đo hiệu năng theo workload chưa?

## 18. Tài liệu chính thức còn hiệu lực

- [Java SE API — `Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): chuyển toàn bộ ký tự còn lại, trả số ký tự, không đóng đầu vào/đầu ra; có từ Java 10.
- [Java SE API — `InputStream.transferTo(OutputStream)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)): chuyển các byte, trả số byte; có từ Java 9.
- [Java SE API — `InputStreamReader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html): cầu nối byte → ký tự, giải mã theo charset.
- [Java SE API — `OutputStreamWriter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html): cầu nối ký tự → byte, mã hóa theo charset.
- [Java SE API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng charset chuẩn như UTF-8, ISO-8859-1, UTF-16LE.
- [Java SE API — `CharsetDecoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): báo lỗi/thay thế với byte không hợp lệ.
- [Java SE API — `Files.newBufferedReader` và `newBufferedWriter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): đọc/ghi file văn bản bằng charset xác định.
- [Java SE API — `Files.copy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): sao chép file byte, không đi qua tầng ký tự.
- [Java Language Specification — Unicode, Characters và `char`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.1): Java dùng UTF-16 code units cho `char` và source text processing.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh charset mặc định ở JDK 18+, lý do vẫn nên chỉ rõ charset cho định dạng dữ liệu.

**Tóm lại:** `Reader.transferTo(Writer)` thuộc miền **ký tự** và trả số **UTF-16 code units** được chuyển, còn `InputStream.transferTo(OutputStream)` thuộc miền **byte** và trả số **byte**. Dùng cầu nối `InputStreamReader`/`OutputStreamWriter` khi cần decode/encode có chủ đích, luôn nêu rõ charset, quản lý close/flush và lỗi I/O. Nếu yêu cầu giữ nguyên dữ liệu binary hoặc byte-for-byte, **không đưa dữ liệu qua Reader/Writer**.