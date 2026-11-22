# Trách nhiệm chọn mã hóa ở lớp đọc, ghi bên ngoài khi dùng `Reader.transferTo`

*Chủ đề cha: `Reader.transferTo` — Java 10 trở đi. Bài viết phân biệt luồng byte, luồng ký tự và vị trí lựa chọn `Charset`; chỉ dùng các nguyên tắc, API vẫn phù hợp với Java hiện đại. Các chương trình hoàn chỉnh chạy trên JDK 17 trở lên.*

## 1. Điều quan trọng nhất

`Reader.transferTo(Writer)` **chuyển các ký tự đã được `Reader` đọc sang một `Writer`**, theo thứ tự đọc được. Phương thức này **không có tham số charset** và **không tự quyết định phải dùng UTF-8, ISO-8859-1, UTF-16 hay một mã hóa khác**.

Mã hóa (encoding) hoặc giải mã (decoding) xảy ra ở **ranh giới giữa byte và ký tự**:

- **Phía đọc:** byte của file, mạng hoặc `InputStream` phải được **giải mã** thành ký tự thông qua `InputStreamReader`, `Files.newBufferedReader` hoặc một lớp đọc đã biết charset.
- **Ở giữa:** `Reader.transferTo(Writer)` đọc và ghi **`char`**, không xử lý trực tiếp byte.
- **Phía ghi:** khi đích là file hoặc `OutputStream`, `OutputStreamWriter` hoặc `Files.newBufferedWriter` **mã hóa** ký tự thành byte với charset được chọn.
- Nếu đích là `StringWriter`, dữ liệu chỉ đi vào bộ đệm ký tự trong bộ nhớ; **không có bước mã hóa ra byte ở đích đó**.

Sơ đồ:

```text
Byte đầu vào               Ký tự Java                  Byte đầu ra
[file, InputStream]       [Reader / Writer]             [file, OutputStream]
       |                         |                              ^
       |   decode bằng           |  Reader.transferTo(Writer)   | encode bằng
       +--> InputStreamReader -->+------------------------------+--> OutputStreamWriter
            + Charset                                         + Charset

           Chọn charset ở lớp bao ngoài, KHÔNG ở transferTo
```

Ví dụ Java 17+:

```java
// Đoạn minh họa; input và output là các InputStream/OutputStream đã có:
try (var reader = new java.io.InputStreamReader(
             input, java.nio.charset.StandardCharsets.UTF_8);
     var writer = new java.io.OutputStreamWriter(
             output, java.nio.charset.StandardCharsets.UTF_8)) {
    long charactersTransferred = reader.transferTo(writer);
    // charactersTransferred là số đơn vị char được chuyển, không phải số byte.
}
```

Ở đây `StandardCharsets.UTF_8` được chỉ định **hai lần tại hai ranh giới**: giải mã đầu vào và mã hóa đầu ra. Không phải vì `transferTo` cần biết UTF-8; nó không biết charset nào đang được sử dụng.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc đúng chữ ký `long Reader.transferTo(Writer out) throws IOException`.
2. Xác định lớp nào chịu trách nhiệm **bytes → chars** và lớp nào chịu trách nhiệm **chars → bytes**.
3. Chọn `StandardCharsets.UTF_8` tường minh khi hợp đồng file/protocol yêu cầu UTF-8, hoặc chọn charset khác **chỉ khi nguồn/đích thực sự có hợp đồng mã hóa đó**.
4. Phân biệt **số đơn vị `char`**, **số Unicode code point** và **số byte**; tránh dùng giá trị trả về để suy ra dung lượng file.
5. Hiểu `transferTo` không tự đóng hay flush mọi tầng; dùng `try-with-resources` đúng cách.
6. Tránh lỗi đọc sai encoding, ghi ra charset không biểu diễn được ký tự, xử lý byte đầu vào không hợp lệ và nhầm lẫn về charset mặc định.
7. Viết code để bảo toàn nội dung văn bản khi chuyển qua hai encoding khác nhau; phân biệt việc đó với **copy file nguyên byte**.
8. Kiểm thử dữ liệu có dấu tiếng Việt, emoji, file rỗng, newline, byte lỗi và đường dẫn I/O thực tế.

## 3. `Reader.transferTo` có hợp đồng gì?

Chữ ký API Java:

```java
public long transferTo(Writer out) throws IOException
```

*Chữ ký này chỉ để tham khảo API; không phải một khai báo method độc lập để đặt ngoài lớp.*

Phương thức `Reader.transferTo` được bổ sung từ **Java 10** và vẫn sử dụng trong Java hiện đại. Nó đọc các ký tự còn lại từ Reader, ghi vào Writer theo thứ tự đọc, trả về `long` là **số ký tự được chuyển**, và để Reader ở trạng thái cuối luồng (EOF) khi thành công.

| Khía cạnh | Hợp đồng cần nhớ |
| --- | --- |
| Đầu vào | `Reader` đã được mở, ở vị trí đọc hiện tại |
| Đầu ra | Một `Writer` không được `null` |
| Chuyển gì? | Ký tự/đơn vị `char` của luồng văn bản |
| Có tham số `Charset`? | **Không** |
| Giá trị trả về | `long`, số ký tự đã chuyển, **không phải byte** |
| Thứ tự | Giữ nguyên thứ tự ký tự được đọc |
| Vị trí Reader sau khi hoàn tất | Ở cuối phần dữ liệu còn lại |
| Tự đóng Reader/Writer? | **Không** |
| Tự bảo đảm flush mọi Writer? | **Không được giả định**; kiểm soát bằng `flush`/`close` |
| Khi lỗi đọc/ghi | `IOException`, có thể đã chuyển được một phần |
| Nếu `out == null` | `NullPointerException` |

`transferTo` không cần biết Reader hiện là `StringReader`, `BufferedReader` hay `InputStreamReader`. Cũng không cần biết Writer là `StringWriter`, `BufferedWriter` hay `OutputStreamWriter`. **Chính lớp cụ thể và cách khởi tạo nó** xác định có bước chuyển giữa byte và ký tự hay không.

### 3.1. `transferTo` không đảm bảo sao chép một file nguyên trạng byte

Văn bản có thể được giữ nguyên ở cấp ký tự nhưng **bytes đầu ra khác bytes đầu vào** nếu các charset khác nhau, có phép chuẩn hóa/biến đổi ngoài `transferTo`, hoặc các quy tắc biểu diễn dữ liệu khác nhau.

Ngược lại, nếu muốn **copy byte nguyên trạng** (ví dụ file ảnh, ZIP, dữ liệu nhị phân hoặc văn bản phải bảo toàn từng byte), nên dùng API byte-oriented như `InputStream.transferTo(OutputStream)` hoặc `Files.copy`, không giải mã và mã hóa qua Reader/Writer.

## 4. `Reader` và `Writer` làm việc ở tầng ký tự

Java phân biệt:

| Nhóm API | Đơn vị làm việc chính | Có biết charset? |
| --- | --- | --- |
| `InputStream` / `OutputStream` | Byte | Không tự chuyển byte thành văn bản |
| `Reader` / `Writer` | Ký tự `char` | Bản thân lớp trừu tượng không định nghĩa charset |
| `InputStreamReader` | Byte → ký tự | Có `Charset` / `CharsetDecoder` khi xây dựng |
| `OutputStreamWriter` | Ký tự → byte | Có `Charset` / `CharsetEncoder` khi xây dựng |
| `Files.newBufferedReader(path, cs)` | Đọc ký tự từ file | Charset được chỉ rõ |
| `Files.newBufferedWriter(path, cs)` | Ghi ký tự ra file | Charset được chỉ rõ |
| `StringReader` / `StringWriter` | Chuỗi ký tự trong bộ nhớ | Không mã hóa/giải mã byte |
| `BufferedReader` / `BufferedWriter` | Bộ đệm ký tự | Không tự thay đổi charset của tầng bao dưới |

Khi bạn viết:

```java
var reader = new java.io.InputStreamReader(
        inputStream,
        java.nio.charset.StandardCharsets.UTF_8);
```

thì `InputStreamReader` giải mã **bytes** của `inputStream` theo UTF-8. Sau đó `reader.read(...)` trả các đơn vị `char` đã giải mã. Một `BufferedReader` bao quanh reader chỉ giúp việc đọc ký tự hiệu quả/thêm API tiện ích; nó không tự kiểm tra hay thay đổi encoding.

Tương tự:

```java
var writer = new java.io.OutputStreamWriter(
        outputStream,
        java.nio.charset.StandardCharsets.UTF_8);
```

`OutputStreamWriter` nhận đơn vị `char` và mã hóa chúng thành UTF-8 khi ghi tới `outputStream`. Một `BufferedWriter` bao quanh writer giữ ký tự trong bộ đệm nhưng không chọn encoding mới.

**Nguyên tắc:** Lỗi encoding phải được xử lý ở nơi byte gặp ký tự, **không** bằng cách thêm tham số tưởng tượng vào `transferTo`.

## 5. Ví dụ 1 — UTF-8 ở cả hai đầu

Tạo tệp **`CharsetBoundaryDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetBoundaryDemo {
    public static void main(String[] args) throws Exception {
        // Biểu diễn "Café 🌱" bằng Unicode escape để mã nguồn là ASCII.
        var text = "Caf\u00e9 \uD83C\uDF31";
        var inputBytes = text.getBytes(StandardCharsets.UTF_8);
        var destination = new ByteArrayOutputStream();

        long characters;
        try (var reader = new InputStreamReader(
                     new ByteArrayInputStream(inputBytes),
                     StandardCharsets.UTF_8);
             var writer = new OutputStreamWriter(
                     destination,
                     StandardCharsets.UTF_8)) {
            characters = reader.transferTo(writer);
        }

        var outputBytes = destination.toByteArray();

        System.out.println("sameText="
                + text.equals(new String(outputBytes,
                        StandardCharsets.UTF_8)));
        System.out.println("chars=" + characters);
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("inputBytes=" + inputBytes.length);
        System.out.println("outputBytes=" + outputBytes.length);
        System.out.println("sameBytes="
                + Arrays.equals(inputBytes, outputBytes));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CharsetBoundaryDemo.java
java CharsetBoundaryDemo
```

Stdout chính xác:

```text
sameText=true
chars=7
codePoints=6
inputBytes=10
outputBytes=10
sameBytes=true
```

Giải thích:

1. `text` chứa các ký tự đại diện cho `Café 🌱`; `\u00e9` tạo chữ `é` và cặp `\uD83C\uDF31` biểu diễn ký tự emoji `🌱` bằng một surrogate pair trong UTF-16.
2. Chuỗi này có **7 đơn vị `char` UTF-16**, **6 Unicode code point** nhưng khi mã hóa UTF-8 dùng **10 byte**.
3. Reader giải mã 10 byte UTF-8 thành 7 đơn vị `char`; `transferTo` trả `7` chứ không phải `10`.
4. Writer mã hóa các đơn vị ký tự về UTF-8 nên đầu ra có 10 byte, bằng dãy byte đầu vào trong ví dụ.
5. Kết quả `sameText=true` chứng tỏ nội dung ký tự đúng. `sameBytes=true` chỉ đúng vì hai đầu cùng sử dụng cùng encoding và không có biến đổi nào khác trong ví dụ.

**Đừng đồng nhất giá trị trả về của `transferTo` với `String.codePointCount` hay `byte[].length`.** Các khái niệm này có thể cho ba con số khác nhau khi văn bản chứa ký tự ngoài BMP, dấu tiếng Việt hoặc các encoding đa byte.

### 5.1. Vì sao đóng Writer trước khi lấy byte?

Trong code, `try-with-resources` đóng `writer` trước khi đọc `destination.toByteArray()`. `OutputStreamWriter` có thể giữ byte cần ghi trong bộ đệm mã hóa; đóng hoặc flush Writer theo đúng lifecycle giúp dữ liệu được đưa xuống byte stream trước khi kiểm tra kết quả.

Không hiểu lầm rằng chính `reader.transferTo(writer)` luôn gọi `writer.flush()`. API `transferTo` không cam kết đóng Reader/Writer; ứng dụng phải quản lý kết thúc việc ghi.

## 6. Charset đúng ở bên đọc quan trọng trước tiên

Giả sử byte nguồn thật sự là UTF-8 nhưng được giải mã nhầm là ISO-8859-1:

```java
var utf8 = "Caf\u00e9".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

// Sai nếu hợp đồng nguồn là UTF-8:
var wrongReader = new java.io.InputStreamReader(
        new java.io.ByteArrayInputStream(utf8),
        java.nio.charset.StandardCharsets.ISO_8859_1);
```

`wrongReader` nhận được byte nhưng tạo **ký tự sai** (mojibake). `transferTo` chỉ sao chép ký tự sai đó sang Writer; nó **không thể suy ra** người dùng vốn muốn giải mã chúng theo UTF-8. Việc ghi ra UTF-8 sau khi đã giải mã nhầm sẽ mã hóa một chuỗi sai thành byte UTF-8 hợp lệ — dữ liệu gốc vẫn sai về nghĩa.

Điều cần nhớ:

- Chọn charset đọc theo **hợp đồng của byte đầu vào**: tài liệu định dạng file, HTTP `Content-Type`/charset khi phù hợp, cấu hình trao đổi hoặc metadata xác thực.
- Không đoán charset qua việc “nhìn vẫn đọc được chữ” trên vài mẫu ASCII. Nhiều encoding dùng chung byte cho chữ ASCII cơ bản nhưng khác ở ký tự có dấu.
- Một chuỗi đã bị giải mã sai không được tự động “chữa” chỉ bằng việc chọn UTF-8 cho Writer.
- Nếu dữ liệu đến từ bên thứ ba không công bố mã hóa, cần chính sách phát hiện/validate rõ ràng. `Reader.transferTo` **không phải API dò charset**.

**Không khuyên dùng mặc định ISO-8859-1 hoặc encoding phụ thuộc locale cho mọi dữ liệu**. UTF-8 là lựa chọn thông dụng cho dữ liệu văn bản hiện đại khi hợp đồng nguồn/đích thực sự là UTF-8; với dữ liệu lịch sử hoặc protocol có charset khác, chọn đúng charset đã quy định.

## 7. Charset ở bên ghi cũng phải có chủ đích

Kể cả Reader đã giải mã đúng, Writer có thể làm mất dữ liệu nếu encoding đích không thể biểu diễn một số ký tự. Ví dụ ISO-8859-1 không biểu diễn được emoji `🌱`. Trong cấu hình encoder mặc định, một số lớp có thể dùng ký tự thay thế cho dữ liệu không biểu diễn được; không được coi đó là việc chuyển đổi không mất mát.

Hai trường hợp:

```java
// Đọc dữ liệu UTF-8 và ghi ra UTF-8 (đúng nếu đích yêu cầu UTF-8):
var safeWriter = new java.io.OutputStreamWriter(
        output,
        java.nio.charset.StandardCharsets.UTF_8);

// Chỉ dùng khi đích thực sự yêu cầu ISO-8859-1:
var latin1Writer = new java.io.OutputStreamWriter(
        output,
        java.nio.charset.StandardCharsets.ISO_8859_1);
```

Các dòng trên là minh họa riêng; `output` là một `OutputStream` đã có. Không tạo hai Writer cùng thao tác lên một OutputStream rồi dùng xen kẽ mà không quản lý vòng đời.

Nếu đích yêu cầu ISO-8859-1, đầu vào chứa ký tự không biểu diễn được cần một **chính sách**: từ chối dữ liệu, chuyển đổi được phép theo nghiệp vụ, hoặc chọn định dạng/charset đích khác nếu hệ thống cho phép. Không tự biến mọi ký tự lạ thành dấu hỏi `?` vì điều đó có thể làm mất thông tin.

## 8. Ví dụ 2 — Chuyển mã có chủ đích từ ISO-8859-1 sang UTF-8

Tạo **`ReencodingDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

public class ReencodingDemo {
    public static void main(String[] args) throws Exception {
        // "Café déjà" chỉ dùng các ký tự biểu diễn được trong ISO-8859-1.
        var text = "Caf\u00e9 d\u00e9j\u00e0";

        var latinBytes = text.getBytes(StandardCharsets.ISO_8859_1);
        var target = new ByteArrayOutputStream();

        long characters;
        try (var reader = new InputStreamReader(
                     new ByteArrayInputStream(latinBytes),
                     StandardCharsets.ISO_8859_1);
             var writer = new OutputStreamWriter(
                     target,
                     StandardCharsets.UTF_8)) {
            characters = reader.transferTo(writer);
        }

        System.out.println("latinBytes=" + latinBytes.length);
        System.out.println("characters=" + characters);
        System.out.println("utf8Bytes=" + target.size());
        System.out.println("correctText="
                + text.equals(new String(
                        target.toByteArray(), StandardCharsets.UTF_8)));
    }
}
```

Chạy:

```bash
javac --release 17 ReencodingDemo.java
java ReencodingDemo
```

Stdout:

```text
latinBytes=9
characters=9
utf8Bytes=12
correctText=true
```

Đây là **transcoding** (đổi biểu diễn byte qua ký tự):

1. Reader được khởi tạo với `ISO_8859_1` vì byte nguồn đang được định dạng theo ISO-8859-1.
2. `transferTo` chuyển **9 đơn vị `char`** mà không quan tâm byte sẽ được mã hóa ra sao.
3. Writer được khởi tạo với `UTF_8` vì đích cần UTF-8.
4. Đầu ra có **12 byte**, không bằng 9 byte đầu vào, nhưng nội dung ký tự được khôi phục chính xác khi đọc lại bằng UTF-8.

**Không coi sự thay đổi số byte là lỗi**. Sự khác nhau là kết quả bình thường khi hai encoding biểu diễn cùng văn bản bằng lượng byte khác nhau.

## 9. Files API: đặt charset ở lúc mở Reader/Writer

Với file văn bản, nên dùng phương thức có tham số `Charset` rõ:

```java
// Đoạn minh họa trong một method throws IOException:
try (var reader = java.nio.file.Files.newBufferedReader(
             sourcePath, java.nio.charset.StandardCharsets.UTF_8);
     var writer = java.nio.file.Files.newBufferedWriter(
             targetPath, java.nio.charset.StandardCharsets.UTF_8)) {
    long chars = reader.transferTo(writer);
}
```

`sourcePath` và `targetPath` là các biến `Path` đã có. Khi dùng `newBufferedReader`, lớp này mở nguồn byte, giải mã theo charset bạn chọn và trả `BufferedReader`. Với `newBufferedWriter`, ký tự được mã hóa thành byte theo charset chỉ định.

Tại sao nên ghi rõ hai lần `StandardCharsets.UTF_8`?

- Đọc mã nguồn là biết hợp đồng mã hóa của cả nguồn lẫn đích.
- Code không phụ thuộc người khác chọn mặc định của constructor nào hoặc runtime được cấu hình ra sao.
- Dễ đổi một bên nếu cần **chuyển mã có chủ đích**, không phải copy byte.
- Dễ review khi xử lý dữ liệu tiếng Việt, dữ liệu từ mạng hoặc file xuất cho hệ thống khác.

**Chi tiết Java hiện đại cần biết:** các overload `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path)` **không truyền charset** vẫn dùng **UTF-8 theo hợp đồng của chính Files API**, kể cả ở Java 17. Vì vậy không nên tuyên bố mọi cách bỏ tham số charset đều “không xác định”. Tuy nhiên, ghi charset tường minh vẫn giúp hợp đồng trở nên dễ nhận biết và thống nhất với những API khác dùng default charset.

## 10. Ví dụ 3 — Copy file văn bản UTF-8 bằng `Reader.transferTo`

Tạo **`FileCharsetTransferDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileCharsetTransferDemo {
    public static void main(String[] args) throws Exception {
        var directory = Files.createTempDirectory("reader-transfer-demo-");
        var source = directory.resolve("source.txt");
        var target = directory.resolve("target.txt");

        try {
            // "Café 🌱", newline, "Java", newline.
            var text = "Caf\u00e9 \uD83C\uDF31\nJava\n";
            Files.writeString(source, text, StandardCharsets.UTF_8);

            long characters;
            try (var reader = Files.newBufferedReader(
                         source, StandardCharsets.UTF_8);
                 var writer = Files.newBufferedWriter(
                         target, StandardCharsets.UTF_8)) {
                characters = reader.transferTo(writer);
            }

            var copiedText = Files.readString(
                    target, StandardCharsets.UTF_8);

            System.out.println("sameText=" + text.equals(copiedText));
            System.out.println("chars=" + characters);
            System.out.println("utf8Bytes=" + Files.size(target));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FileCharsetTransferDemo.java
java FileCharsetTransferDemo
```

Stdout:

```text
sameText=true
chars=13
utf8Bytes=16
```

Chương trình tạo thư mục và hai file tạm, **không ghi đè dữ liệu dự án**, và dọn chúng trong `finally`. Nội dung gốc có **13 đơn vị `char`** (gồm newline và emoji là cặp surrogate) nhưng file UTF-8 có **16 byte**.

Trong ứng dụng thật, không cần tự tạo file tạm nếu đã có `sourcePath` và `targetPath`. Hãy quyết định quy tắc **ghi đè hay không ghi đè** trước khi mở Writer: `Files.newBufferedWriter` có các `OpenOption` cho mục đích này. Nếu không chỉ định option, nó thường tạo file nếu chưa có và ghi đè nội dung hiện có từ đầu; nếu cần từ chối ghi đè, hãy chọn `StandardOpenOption.CREATE_NEW` cùng các option phù hợp.

### 10.1. Chọn kiểu copy theo yêu cầu

| Mục tiêu | API phù hợp | Tại sao |
| --- | --- | --- |
| Bảo toàn toàn bộ **byte** không cần hiểu văn bản | `Files.copy` hoặc `InputStream.transferTo(OutputStream)` | Không giải mã/mã hóa, dùng cho cả file nhị phân |
| Đọc text theo một charset, ghi text theo charset khác | `Reader.transferTo(Writer)` với Reader/Writer cấu hình charset | Cho phép transcoding ở hai ranh giới |
| Chỉ muốn kết quả thành `String` trong bộ nhớ | `Reader.transferTo(new StringWriter())` | Không có byte output/charset ở phía StringWriter |
| Cần biến đổi từng dòng hoặc nội dung | `BufferedReader`, xử lý chuỗi/line rồi ghi | `transferTo` không tự cắt/sửa dòng |
| Cần thay thế nội dung file nguyên byte | `Files.copy(source, target, ...)` với chính sách đích phù hợp | Rõ ý định byte-copy, không làm văn bản bị decode sai |

Đừng sử dụng Reader/Writer để sao chép file ảnh, ZIP hay nội dung binary bất kỳ: các chuỗi byte đó có thể không biểu diễn văn bản hợp lệ dưới một charset nào bạn đã chọn.

## 11. Charset mặc định: điểm cần hiểu đúng giữa Java 17 và Java hiện đại

Có hai vấn đề khác nhau:

1. Một số **constructor/API** dùng `Charset.defaultCharset()` khi bạn không truyền charset.
2. Một số **Files API** có hợp đồng riêng là UTF-8 dù không truyền charset.

Trên **JDK 17 trở xuống**, charset mặc định của JVM thường phụ thuộc môi trường/locale khi khởi động. **Từ JDK 18**, JEP 400 đưa UTF-8 thành charset mặc định cho các Java SE API liên quan, với những cơ chế tương thích và ngoại lệ I/O console được tài liệu hóa. Điều đó giúp hành vi thống nhất hơn, nhưng **không có nghĩa mọi file đầu vào trên thế giới đều là UTF-8**.

So sánh:

```java
// Chọn charset theo hợp đồng file, rõ ràng ở mọi bản JDK hỗ trợ API:
new java.io.InputStreamReader(
        inputStream,
        java.nio.charset.StandardCharsets.UTF_8);

// Nếu chỉ dùng constructor không truyền Charset,
// hành vi phụ thuộc default charset của API/JDK:
new java.io.InputStreamReader(inputStream);

// Files.newBufferedReader(path) dùng UTF-8 theo hợp đồng Files API:
java.nio.file.Files.newBufferedReader(path);
```

Đây là các dòng minh họa trong method với `inputStream`/`path` đã có; không phải một chương trình độc lập. Với dữ liệu trao đổi hoặc file có charset được chỉ định, hãy **truyền charset rõ ràng**, kể cả khi môi trường hiện tại mặc định UTF-8.

Không nên cố “chữa” encoding sai bằng việc thay đổi `file.encoding` toàn JVM trong ứng dụng như biện pháp đầu tiên. Hãy bắt đầu từ **hợp đồng nguồn/đích** và chọn đúng Reader/Writer.

## 12. Trách nhiệm ở các tầng của một ứng dụng thực tế

### 12.1. Đầu vào file

Nếu nhà cung cấp nói file là UTF-8:

```java
try (var reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    // Đọc hoặc reader.transferTo(writer)
}
```

Nếu file là ISO-8859-1 theo hợp đồng, truyền `StandardCharsets.ISO_8859_1` thay vì tự đoán UTF-8. Đuôi `.txt`, `.csv` hoặc tên file không đủ chứng minh charset.

### 12.2. Đầu vào mạng

Khi có `InputStream` từ HTTP hoặc protocol khác, quyết định charset theo **định dạng thông điệp và metadata đáng tin cậy**. Một số định dạng quy định UTF-8; một số protocol cung cấp charset trong header; có nơi cần xử lý BOM hoặc thông tin codec riêng. Không mặc định mọi dữ liệu mạng đều UTF-8 hoặc chỉ nhìn `Content-Type` mà bỏ qua đặc tả của định dạng.

Ví dụ lớp ranh giới:

```java
var reader = new java.io.InputStreamReader(
        networkInputStream, selectedCharset);
```

`selectedCharset` phải đến từ hợp đồng/configuration/logic validate phù hợp. `Reader.transferTo` không thể xác định nguồn của lựa chọn đó.

### 12.3. Đích ghi ra file hoặc mạng

Lớp phía xuất dữ liệu quyết định charset theo **hợp đồng với người nhận**:

```java
var writer = new java.io.OutputStreamWriter(
        networkOutputStream, targetCharset);
```

Nếu hợp đồng yêu cầu UTF-8, dùng `StandardCharsets.UTF_8`; nếu nơi nhận yêu cầu encoding khác, dùng encoding đó và kiểm tra các ký tự không thể biểu diễn. Các ví dụ trong mục này minh họa ranh giới, không độc lập biên dịch nếu chưa khai báo biến và xử lý đóng luồng.

### 12.4. Ranh giới ownership

Reader/Writer được đóng khi cần, tùy ai **sở hữu** luồng:

- Nếu phương thức mở file/luồng và chịu trách nhiệm toàn bộ vòng đời, `try-with-resources` là lựa chọn chuẩn.
- Nếu caller truyền một Writer do caller sở hữu và mong tiếp tục sử dụng nó, không nên tự ý đóng Writer trong helper nếu hợp đồng helper không nói như vậy.
- `reader.transferTo(writer)` **không đóng** cả Reader lẫn Writer; việc đóng Reader/Writer phải được quyết định ở lớp quản lý tài nguyên.

Không viết một helper gọi `transferTo` và mặc định nghĩ “copy xong là mọi tầng tự đóng”.

## 13. Khi encoding hoặc byte đầu vào không hợp lệ

### 13.1. Giải mã sai charset không phải lúc nào cũng ném exception

Ví dụ UTF-8 bị đọc bằng ISO-8859-1 thường vẫn cho một chuỗi ký tự (nhưng sai), vì byte 0x00–0xFF đều có ánh xạ trong ISO-8859-1. Do đó không có exception **không đồng nghĩa text đúng**.

Một bộ kiểm tra dữ liệu phù hợp nên so sánh với hợp đồng/nguồn tin cậy và có trường hợp test chứa chữ có dấu, biểu tượng hoặc những ký tự mà dữ liệu thực tế hỗ trợ.

### 13.2. Decoder có thể thay thế ký tự hoặc báo lỗi

Với byte không hợp lệ dưới charset đã chọn, hành vi phụ thuộc cách tạo lớp giải mã và chính sách xử lý lỗi. Khi cần từ chối dữ liệu sai một cách rõ ràng, dùng `CharsetDecoder` với `CodingErrorAction.REPORT`.

### 13.3. Encoder cũng có thể từ chối ký tự không biểu diễn được

Đầu ra ISO-8859-1 không biểu diễn được mọi ký tự Unicode. Khi không được phép mất dữ liệu, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để phát hiện ký tự ngoài miền charset.

Tạo **`StrictCodingDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;

public class StrictCodingDemo {
    public static void main(String[] args) throws Exception {
        var malformed = new byte[] {
                (byte) 0xC3, (byte) 0x28
        };

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);

        try (var reader = new InputStreamReader(
                     new ByteArrayInputStream(malformed), decoder);
             var writer = new StringWriter()) {
            reader.transferTo(writer);
        } catch (MalformedInputException ex) {
            System.out.println("malformed="
                    + ex.getClass().getSimpleName());
        }

        var output = new ByteArrayOutputStream();
        var encoder = StandardCharsets.ISO_8859_1.newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        // "Café 🌱" có emoji không biểu diễn được trong ISO-8859-1.
        try (var reader = new StringReader("Caf\u00e9 \uD83C\uDF31");
             var writer = new OutputStreamWriter(output, encoder)) {
            reader.transferTo(writer);
        } catch (UnmappableCharacterException ex) {
            System.out.println("unmappable="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 StrictCodingDemo.java
java StrictCodingDemo
```

Stdout:

```text
malformed=MalformedInputException
unmappable=UnmappableCharacterException
```

Dòng đầu mô phỏng byte không tạo được chuỗi UTF-8 hợp lệ. Dòng thứ hai thử mã hóa ký tự emoji sang ISO-8859-1, charset không biểu diễn được nó.

**Lưu ý thực tế:**

- Trong code production, cần xem xét cả `onMalformedInput` và `onUnmappableCharacter` tùy charset, loại lỗi đầu vào và chính sách dữ liệu. Ở đây chúng được cấu hình đủ để minh họa đúng hai lỗi cụ thể.
- Không bắt chung `IOException` rồi bỏ qua dữ liệu bị cắt dở; khi `transferTo` thất bại, Reader/Writer có thể đã chuyển được **một phần** văn bản.
- Nếu đích là file thật, quyết định có nên xóa file dở, ghi tạm rồi thay nguyên tử, hoặc báo lỗi kèm ngữ cảnh. `transferTo` không tự rollback nội dung Writer khi xảy ra lỗi.
- Dữ liệu lỗi có thể do mã hóa **không đúng**, không chỉ do nội dung bị hỏng; kiểm tra hợp đồng charset trước khi tùy tiện thay ký tự.

## 14. BOM và các rủi ro ngoài charset

Một số định dạng văn bản có **Byte Order Mark (BOM)** hoặc quy tắc riêng về newline, chuẩn hóa Unicode và cấu trúc dữ liệu. `Reader.transferTo` không tự quyết định phải giữ, loại bỏ hay thêm BOM.

- Với UTF-16, lựa chọn `UTF_16`, `UTF_16LE` hoặc `UTF_16BE` có quy tắc byte order/BOM khác nhau. Chọn đúng charset và định dạng theo giao ước file.
- Với UTF-8, BOM nếu xuất hiện phải được xử lý theo yêu cầu định dạng/Reader cụ thể. Không mặc định `transferTo` là bộ loại BOM.
- `Reader.transferTo` giữ chuỗi ký tự được đọc (không tự thay `\r\n` thành `\n`, không tự `trim`, không tự normalize NFC/NFD). Nếu cần thay đổi, thực hiện phép biến đổi được mô tả rõ và kiểm thử nó.
- `BufferedReader.readLine()` **bỏ ký tự kết thúc dòng** trong giá trị trả về; đó là hành vi của `readLine`, không phải của `transferTo`.

**Không nhầm “đã chọn đúng charset” với “đã validate đúng văn bản nghiệp vụ”.** Một CSV cần xử lý delimiter/quote, JSON cần parser, dữ liệu Unicode có thể cần quy tắc chuẩn hóa/collation riêng. Việc copy ký tự đúng không tự bảo đảm file đầu ra hợp lệ với parser của hệ thống khác.

## 15. `Reader.transferTo` không tự đóng, không nên dùng lại nguồn sau EOF

Tạo **`ReaderWriterOwnershipDemo.java`**:

```java
import java.io.StringReader;
import java.io.StringWriter;

public class ReaderWriterOwnershipDemo {
    public static void main(String[] args) throws Exception {
        var reader = new StringReader("ABC");
        var writer = new StringWriter();

        var first = reader.transferTo(writer);
        var second = reader.transferTo(writer);

        // Writer vẫn dùng được sau transferTo.
        writer.write("!");

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("output=" + writer.toString());

        reader.close();
        writer.close();
    }
}
```

Chạy:

```bash
javac --release 17 ReaderWriterOwnershipDemo.java
java ReaderWriterOwnershipDemo
```

Stdout:

```text
first=3
second=0
output=ABC!
```

Lần thứ nhất chuyển ba `char` và để Reader ở EOF. Lần thứ hai không có ký tự còn lại nên trả 0. Writer vẫn chấp nhận `write("!")` sau `transferTo`, cho thấy `transferTo` **không đóng** Writer.

`StringReader` và `StringWriter` không liên quan đến byte nên ví dụ này **không chọn Charset**. Đây là bằng chứng bổ sung rằng việc chọn mã hóa không phải trách nhiệm của `transferTo`.

Với Reader khác, có thể dùng `mark/reset` nếu implementation hỗ trợ và logic phù hợp, nhưng **không được giả định mọi Reader có thể tua ngược**. Khi cần copy lại file, thông thường mở Reader mới từ nguồn.

## 16. Lỗi và ngoại lệ liên quan tới `transferTo`

### 16.1. Đích `null`

```java
var reader = new java.io.StringReader("Hello");
// reader.transferTo(null); // Ném NullPointerException
```

`Writer out` là tham số bắt buộc không null. Không liên quan đến mã hóa đầu vào.

### 16.2. Lỗi I/O trong lúc đang chuyển

Theo API, `transferTo` có thể ném `IOException` khi đọc Reader hoặc ghi Writer. Có thể đã ghi một phần dữ liệu trước khi gặp lỗi, nên không được giả định Reader vẫn ở vị trí cũ hay Writer chưa ghi gì.

Dùng `try-with-resources` để đóng tài nguyên do ứng dụng sở hữu. Nếu cần tính nguyên tử khi xuất file, dùng cách ghi file tạm rồi thay file đích theo chiến lược thích hợp; đừng coi `transferTo` là thao tác giao dịch.

### 16.3. Reader không có EOF trong một nguồn đang mở lâu dài

`Reader.transferTo` đọc **tới EOF**; với nguồn mạng/pipe liên tục chưa đóng hoặc chưa báo kết thúc, lời gọi có thể chờ dữ liệu rất lâu. Đây không phải API tự áp timeout hay copy chính xác N ký tự. Nếu cần giới hạn dữ liệu, kiểm soát Reader/connection, quy định điểm kết thúc hoặc tự tổ chức vòng đọc giới hạn.

Đặc biệt tránh dùng `transferTo` mù quáng trên nguồn không đáng tin cậy nếu ứng dụng cần giới hạn kích thước đầu vào: nó có thể tiếp tục ghi dữ liệu cho tới EOF mà không có giới hạn ký tự do bạn đặt.

## 17. So sánh `Reader.transferTo` và `InputStream.transferTo`

| Khía cạnh | `Reader.transferTo(Writer)` | `InputStream.transferTo(OutputStream)` |
| --- | --- | --- |
| Đơn vị | Ký tự Java | Byte |
| Giới thiệu | Java 10 | Java 9 |
| Giá trị trả về | Số ký tự chuyển | Số byte chuyển |
| Có decode/encode bên trong phương thức? | Không; phụ thuộc Reader/Writer bao ngoài | Không; chuyển byte |
| Dùng để chuyển mã ISO-8859-1 → UTF-8 | Có, bằng hai wrapper charset thích hợp | Không tự chuyển mã |
| Dùng cho file nhị phân | Không nên | Phù hợp |
| Có tự đóng nguồn/đích? | Không | Không |
| Tính nguyên tử khi lỗi I/O | Không bảo đảm | Không bảo đảm |

Ví dụ chỉ cần copy bytes:

```java
// Đoạn minh họa trong một method throws IOException:
try (var input = java.nio.file.Files.newInputStream(sourcePath);
     var output = java.nio.file.Files.newOutputStream(targetPath)) {
    long bytesTransferred = input.transferTo(output);
}
```

**Đừng dùng hai API lẫn lộn chỉ vì đều tên `transferTo`.** Nếu dữ liệu là văn bản cần diễn giải theo charset và có thể đổi encoding, dùng tầng character. Nếu mục tiêu là bảo toàn mọi byte, dùng tầng byte.

## 18. Chọn API đơn giản nhất đủ mục đích

Không phải mọi trường hợp đều cần `Reader.transferTo`:

| Tình huống | Gợi ý API |
| --- | --- |
| Đọc file văn bản nhỏ thành chuỗi | `Files.readString(path, charset)` |
| Ghi toàn bộ chuỗi vào file văn bản | `Files.writeString(path, content, charset)` |
| Sao chép file nguyên byte | `Files.copy` |
| Truyền văn bản từ một Reader vào Writer, không cần giữ toàn bộ trong RAM | `Reader.transferTo(writer)` |
| Xử lý từng dòng/biến đổi trước khi ghi | `BufferedReader.readLine()` hoặc `Files.lines` với đóng tài nguyên đúng cách |
| Chuyển mã giữa các charset đã biết | Reader/Writer có Charset khác nhau, có thể dùng `transferTo` |
| Yêu cầu phát hiện dữ liệu lỗi nghiêm ngặt | `CharsetDecoder`/`CharsetEncoder` với `REPORT` |
| Cần giới hạn số byte hoặc ký tự | Vòng đọc ghi được thiết kế với giới hạn và validation rõ ràng |

`Files.readString` tiện cho file nhỏ; với file lớn, việc nạp hết nội dung vào String có thể tốn bộ nhớ. `transferTo` là giải pháp streaming ở tầng ký tự. Tuy nhiên, việc streaming không tự bảo đảm giới hạn dung lượng hay chống quá tải; mã xử lý phải thiết kế theo nguồn và yêu cầu tài nguyên.

## 19. Các lỗi hiểu nhầm phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`Reader.transferTo` mặc định dùng UTF-8.” | Không: nó không có charset; Reader/Writer bao ngoài quyết định |
| “Chỉ cần đặt UTF-8 ở Writer là chữa được text đầu vào sai.” | Không: Reader giải mã sai trước đó đã tạo ký tự sai |
| “Reader/Writer copy text thì số byte phải bằng nhau.” | Không: transcoding có thể đổi số byte |
| “`transferTo` trả số byte đã ghi.” | Sai: trả số ký tự Java, thông thường tính theo đơn vị `char` UTF-16 |
| “Một emoji luôn là một `char`.” | Không: nhiều emoji là surrogate pair gồm hai `char` |
| “Dùng `InputStreamReader(input)` luôn là UTF-8 ở mọi JDK.” | Không đúng với JDK 17 và một số cấu hình tương thích; hãy ghi Charset khi giao ước yêu cầu |
| “`Files.newBufferedReader(path)` phụ thuộc default charset của hệ điều hành ở JDK 17.” | Sai: overload không Charset của Files dùng UTF-8 theo API |
| “`transferTo` tự đóng Reader và Writer.” | Sai: caller quản lý vòng đời |
| “Gọi xong `transferTo` thì Writer chắc chắn đã flush đầy đủ.” | Không được giả định; flush/close ở tầng sở hữu |
| “Không có exception thì charset chắc chắn đúng.” | Sai: giải mã nhầm có thể tạo mojibake hợp lệ về mặt kỹ thuật |
| “Ghi ISO-8859-1 sẽ tự giữ mọi emoji.” | Sai: charset này không biểu diễn mọi ký tự Unicode |
| “Mọi encoding error đều phải bị thay bằng ký tự `?`.” | Không: có thể cấu hình `CharsetDecoder`/`CharsetEncoder` để `REPORT` |
| “`transferTo` tự thêm/xóa newline hoặc BOM.” | Không: những thay đổi đó thuộc Reader/Writer/logic bổ sung hoặc định dạng file |
| “Copy văn bản bằng Reader bảo toàn byte của file gốc.” | Không nhất thiết, kể cả nếu nội dung chữ vẫn giống nhau |
| “`Reader.transferTo` luôn không thể chờ lâu.” | Có thể block khi chưa đến EOF hoặc Writer đích chậm |
| “Đặt Charset ở `BufferedReader` là đủ mà không cần xem `InputStreamReader`.” | BufferedReader chỉ bao Reader; decoder bên dưới mới quy định byte→char |

## 20. Bài tập có đáp án

### Bài 1 — Charset được chọn ở đâu?

```java
try (var reader = new InputStreamReader(input, StandardCharsets.UTF_8);
     var writer = new OutputStreamWriter(output, StandardCharsets.UTF_8)) {
    reader.transferTo(writer);
}
```

**Đáp án:** `InputStreamReader` chọn UTF-8 để giải mã byte đầu vào. `OutputStreamWriter` chọn UTF-8 để mã hóa ký tự ra byte. `transferTo` không chọn charset; nó chỉ chuyển ký tự.

### Bài 2 — Một số ký tự được tính như thế nào?

```java
var source = new java.io.StringReader("A\uD83C\uDF31");
var sink = new java.io.StringWriter();
var transferred = source.transferTo(sink);
```

**Đáp án:** `transferred == 3` vì chuỗi có `A` là một `char` và emoji `🌱` gồm hai `char` UTF-16. Số Unicode code point là 2. Không thể suy ra số byte chỉ từ `transferred`.

### Bài 3 — Mã hóa hai đầu khác nhau

Nguồn là ISO-8859-1, đích yêu cầu UTF-8. Nên đặt encoding tại đâu?

**Đáp án:** tạo `InputStreamReader(input, StandardCharsets.ISO_8859_1)` và `OutputStreamWriter(output, StandardCharsets.UTF_8)`. Sau đó dùng `reader.transferTo(writer)`; số byte có thể khác nhưng ký tự có thể giữ nguyên nếu được biểu diễn hợp lệ.

### Bài 4 — Đọc sai rồi ghi đúng

Một file UTF-8 được đọc bằng ISO-8859-1 và ghi lại bằng UTF-8. Kết quả đã được sửa đúng chưa?

**Đáp án:** **Không.** Reader đã tạo ký tự sai từ byte UTF-8; Writer chỉ mã hóa ký tự sai đó sang UTF-8. Phải đọc lại từ byte nguồn bằng charset đúng theo giao ước.

### Bài 5 — File lớn, không muốn nạp hết vào RAM

Có cần `Files.readString(source)` rồi `Files.writeString(target, ...)` không?

**Đáp án:** không bắt buộc. Có thể mở `Files.newBufferedReader(source, charset)` và `Files.newBufferedWriter(target, charset)` rồi gọi `transferTo`. Việc streaming tránh nạp toàn bộ nội dung một lúc; vẫn cần xem giới hạn dữ liệu, xử lý lỗi và ownership.

### Bài 6 — Có được tin charset mặc định?

Vì sao ghi rõ `StandardCharsets.UTF_8` vẫn có giá trị nếu JDK 18+ chọn UTF-8 làm mặc định?

**Đáp án:** code thể hiện hợp đồng dữ liệu rõ ràng, chạy nhất quán khi cần hỗ trợ JDK 17 hoặc API có quy tắc khác, và tránh phụ thuộc cấu hình môi trường. Quan trọng hơn, phải chọn đúng **charset của file/protocol**, không phải chọn theo mặc định JVM chỉ vì tiện.

### Bài 7 — Writer có tự đóng không?

```java
var reader = new java.io.StringReader("ABC");
var writer = new java.io.StringWriter();
reader.transferTo(writer);
writer.write("!");
```

**Đáp án:** hợp lệ, vì `transferTo` không đóng Writer. Kết quả trong Writer là `ABC!`. Tuy nhiên phải đóng những Reader/Writer sở hữu tài nguyên hệ thống theo đúng vòng đời của ứng dụng.

### Bài 8 — Lỗi mã hóa nghiêm ngặt

Một file có chuỗi byte không hợp lệ dưới UTF-8 và ứng dụng không chấp nhận ký tự thay thế. Cần làm gì?

**Đáp án:** dùng `CharsetDecoder` với `onMalformedInput(CodingErrorAction.REPORT)` (và `onUnmappableCharacter(REPORT)` theo hợp đồng), rồi mở Reader từ decoder đó. Không dùng `transferTo` làm công cụ validate charset; lỗi phát sinh từ lớp giải mã.

### Bài 9 — Khi nào chọn `InputStream.transferTo`?

**Đáp án:** khi cần copy byte (ví dụ tệp ảnh, ZIP, hoặc văn bản cần bảo toàn chính xác byte gốc) mà không phải đọc/ghi ký tự. Nếu cần chuyển văn bản từ ISO-8859-1 sang UTF-8, phải có decoder và encoder ở hai bên; `InputStream.transferTo` không tự thực hiện việc đó.

### Bài 10 — Mã hóa không phải validation

Giả sử đã dùng UTF-8 đúng cho một file CSV nhưng parser báo lỗi delimiter. `Reader.transferTo` có chữa được không?

**Đáp án:** không. Charset giải quyết byte ↔ ký tự; CSV có cú pháp và quy tắc escape/quote riêng. Cần parser/validator đúng định dạng hoặc sửa dữ liệu nguồn, không thay charset tùy tiện.

## 21. Checklist ứng dụng thực tế

Trước khi triển khai một đoạn code dùng `Reader.transferTo`:

1. **Nguồn là văn bản hay binary?** Nếu binary, dùng byte-oriented copy.
2. **Nguồn byte thật sự dùng charset nào?** Theo đặc tả hoặc metadata xác thực, không đoán từ phần mở rộng file.
3. **Reader nào thực hiện decode?** `InputStreamReader` hay `Files.newBufferedReader` và tham số Charset cụ thể.
4. **Đích cần charset gì?** Theo hợp đồng bên nhận; `OutputStreamWriter` hoặc `Files.newBufferedWriter` phải phù hợp.
5. **Có đang mong `transferTo` tự chọn encoding không?** Nếu có, thiết kế đang đặt sai trách nhiệm.
6. **Có kiểm thử chữ có dấu, emoji và newline không?** ASCII đơn thuần không phơi bày sai charset.
7. **Có kiểm tra số byte riêng không?** `transferTo` trả ký tự, cần `Files.size` hoặc đếm bytes ở tầng byte.
8. **Có thể có byte malformed hoặc ký tự không biểu diễn được không?** Chọn chính sách `REPORT`/thay thế theo hợp đồng và kiểm thử lỗi.
9. **Có BOM hay quy tắc text format riêng không?** Tách khỏi trách nhiệm `transferTo`.
10. **Ai sở hữu Reader và Writer?** Dùng `try-with-resources` khi phương thức chịu trách nhiệm mở/đóng.
11. **Có cần flush/close trước khi đọc kết quả?** Không phụ thuộc vào `transferTo` để thực hiện việc đó.
12. **Nguồn có vô hạn hoặc rất lớn không?** Kiểm soát EOF, timeout, giới hạn dữ liệu và tài nguyên.
13. **Nếu lỗi xảy ra giữa chừng, file đích có thể dở không?** Xử lý rollback/thay file theo nhu cầu ứng dụng.
14. **Có cần bảo toàn byte tuyệt đối không?** Nếu có, chọn `Files.copy`/`InputStream.transferTo`.
15. **Đã phân biệt JDK default charset với Files API default chưa?** Chọn API theo hợp đồng thực tế, không theo suy đoán.
16. **Có cần charset khác giữa hai đầu không?** Khi transcoding có chủ đích, chỉ định riêng từng phía.
17. **Test có phụ thuộc terminal/console encoding không?** Ưu tiên so sánh byte hoặc String đọc lại với charset xác định thay vì dựa vào giao diện hiển thị.

## 22. Tổng kết

**`Reader.transferTo(Writer)` là thao tác chuyển ký tự, không phải bộ chọn mã hóa.** Ở phía đọc, `InputStreamReader` hoặc `Files.newBufferedReader` chuyển byte → ký tự bằng Charset được chọn. Ở phía ghi, `OutputStreamWriter` hoặc `Files.newBufferedWriter` chuyển ký tự → byte bằng Charset được chọn. Hai phía có thể dùng cùng UTF-8, hoặc khác nhau khi ứng dụng phải chuyển mã.

Giá trị `long` trả về đếm **đơn vị ký tự Java** chứ không phải số byte; Unicode ngoài BMP như emoji có thể cần hai `char`. Phương thức không tự đóng Reader/Writer, không tự đảm bảo flush mọi tầng và không thay thế validation, chính sách xử lý malformed input hoặc quản lý lỗi I/O.

Khi viết code hiện đại, hãy **chọn charset tại ranh giới byte–ký tự**, khai báo rõ hợp đồng của nguồn và đích, dùng `try-with-resources`, kiểm thử dữ liệu phi ASCII và chọn byte-copy nếu cần bảo toàn dữ liệu nguyên byte. Đó là cách khai thác `Reader.transferTo` từ Java 10 tới nay mà không giao nhầm trách nhiệm mã hóa cho một API chỉ làm việc với ký tự.

### Tài liệu API tham khảo

- [Reader.transferTo — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html)
- [Files.newBufferedReader / newBufferedWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StandardCharsets — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)