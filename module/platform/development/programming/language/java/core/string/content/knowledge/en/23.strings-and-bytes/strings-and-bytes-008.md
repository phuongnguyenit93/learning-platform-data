# Đối chiếu chuỗi qua ranh giới tệp, console và dữ liệu truyền trong Java

## Mục tiêu

Khi một chuỗi tiếng Việt hoặc emoji trông đúng trong chương trình nhưng bị lỗi sau khi lưu tệp, in ra terminal hay gửi cho dịch vụ khác, câu hỏi cần đặt ra là: **bên gửi đã biến ký tự thành byte bằng quy tắc nào, và bên nhận đang biến byte trở lại thành ký tự bằng quy tắc nào?**

Sau bài học, bạn có thể kiểm tra một chuỗi ở ba mức **ký tự Unicode, đơn vị UTF-16 và byte**, đối chiếu kết quả qua tệp/console/dữ liệu truyền, phát hiện sai lệch charset, BOM, xuống dòng và chuẩn hóa Unicode, rồi thiết kế quy trình truyền nhận có thể kiểm chứng trong Java 17+.

## 1. Ba lớp cần phân biệt khi so sánh chuỗi

Trong Java, `String` là chuỗi bất biến được biểu diễn theo các **đơn vị mã UTF-16**. Khi lưu ra tệp hoặc truyền trên mạng, chương trình phải **mã hóa** (`encode`) chuỗi thành `byte[]`; ở đầu nhận, các byte được **giải mã** (`decode`) theo một `Charset` để có chuỗi trở lại.

```text
String trong Java ── encode với charset ──> byte[] ── ghi tệp / truyền đi
String trong Java <── decode với charset ─── byte[] <── đọc tệp / nhận về
```

Đây là ba phép so sánh khác nhau:

| Câu hỏi | API dùng trong Java | Ý nghĩa |
| --- | --- | --- |
| Hai chuỗi có cùng dãy đơn vị mã UTF-16? | `a.equals(b)` | So sánh nội dung `String` chính xác, phân biệt chữ hoa/thường và dạng Unicode khác nhau |
| Hai chuỗi có cùng dãy Unicode code point? | `s.codePoints()` | Quan sát ký tự theo code point, tránh nhầm một emoji với hai đơn vị UTF-16 |
| Hai bản ghi có đúng cùng các byte? | `Arrays.equals(bytesA, bytesB)` | Kiểm tra dữ liệu được lưu/truyền thực sự giống nhau |
| Byte có hợp lệ theo charset dự kiến? | `CharsetDecoder` với `CodingErrorAction.REPORT` | Phát hiện dãy byte lỗi trước khi chấp nhận nội dung |

**Ví dụ:** chuỗi `"A😀"` có `String.length() == 3` (một đơn vị cho `A`, hai đơn vị UTF-16 cho emoji), nhưng chỉ có **2 Unicode code point**. Mã hóa UTF-8 cho ra **5 byte**: `41 f0 9f 98 80`. Độ dài `String` không phải số ký tự người đọc nhận thấy, và càng không phải số byte.

```java
String text = "A\uD83D\uDE00";
System.out.println(text.length());                        // 3 đơn vị UTF-16
System.out.println(text.codePointCount(0, text.length())); // 2 code point
System.out.println(text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length); // 5 byte
```

Đoạn trên là mã minh họa có thể chạy trong `jshell`; hai mã `\uD83D\uDE00` là surrogate pair của emoji 😀. Không cắt một `String` tại chỉ số tùy ý nếu có thể chia đôi một surrogate pair; với văn bản thực tế, khái niệm "ký tự người dùng nhìn thấy" (grapheme cluster) còn có thể gồm nhiều code point.

## 2. Charset là hợp đồng giữa các ranh giới

`java.nio.charset.StandardCharsets.UTF_8` xác định rõ cách ánh xạ Unicode ↔ byte. Nếu ghi UTF-8 mà đọc với `ISO_8859_1` hoặc Windows-1252, byte có thể còn nguyên nhưng **ký tự sau giải mã khác đi**, thường thấy như chuỗi kiểu `"Ã..."` (mojibake). Ngược lại, nếu mã hóa bằng charset không hỗ trợ ký tự nguồn, dữ liệu có thể bị thay bằng dấu hỏi hoặc ký tự thay thế và không thể khôi phục chỉ bằng việc đổi charset khi đọc.

| Nội dung | UTF-8 | UTF-16BE | Nhận xét |
| --- | --- | --- | --- |
| `A` (U+0041) | `41` | `00 41` | Cùng ký tự, số byte khác nhau |
| `é` (U+00E9) | `c3 a9` | `00 e9` | Nếu đọc `c3 a9` bằng Latin-1 sẽ không nhận lại `é` |
| 😀 (U+1F600) | `f0 9f 98 80` | `d8 3d de 00` | UTF-16 dùng surrogate pair |
 
Trong thực hành hiện đại, **chọn UTF-8 làm hợp đồng trao đổi mặc định** khi không có định dạng giao thức riêng; hai đầu phải nhất trí trên cùng charset. Trong Java 17, không giả định mọi API đều dùng một charset giống nhau. Các overload có truyền `Charset` rõ ràng giúp mã nguồn dễ hiểu và tránh khác biệt theo máy chạy.

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa, giả sử `text` đã tồn tại. `getBytes(UTF_8)` mã hóa; `new String(bytes, UTF_8)` giải mã. Cặp thao tác này cần giữ **đúng byte thực sự đi qua ranh giới**, không mã hóa thành byte rồi quay lại chuỗi bằng charset khác ở giữa.

## 3. Ví dụ chạy được: kiểm tra đồng thời tệp và "dữ liệu truyền"

Chương trình sau tạo dữ liệu nguồn, lấy byte UTF-8 làm payload truyền, ghi chính các byte ấy vào tệp tạm, rồi kiểm tra cả byte lẫn `String` khi đọc về. Nó dùng một phép giải mã sai để cho thấy vì sao **byte không thay đổi vẫn có thể hiển thị sai**.

Lưu thành `BoundaryRoundTrip.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;

public class BoundaryRoundTrip {
    public static void main(String[] args) throws IOException {
        // \u00E0 là à; \uD83D\uDE00 là 😀; \n là LF.
        String original = "Xin ch\u00E0o \uD83D\uDE00\n";

        // Giả lập payload mà bên gửi đưa vào kênh truyền.
        byte[] wire = original.getBytes(StandardCharsets.UTF_8);
        String received = new String(wire, StandardCharsets.UTF_8);

        Path file = Files.createTempFile("string-boundary-", ".txt");
        try {
            Files.write(file, wire);
            byte[] disk = Files.readAllBytes(file);
            String restored = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("file-bytes-match=" + Arrays.equals(wire, disk));
            System.out.println("file-text-match=" + original.equals(restored));
            System.out.println("wire-text-match=" + original.equals(received));

            String wrong = new String(disk, StandardCharsets.ISO_8859_1);
            System.out.println("wrong-charset-match=" + original.equals(wrong));

            String composed = "\u00E9";
            String decomposed = "e\u0301";
            System.out.println("unicode-equal-before=" + composed.equals(decomposed));
            System.out.println("unicode-equal-after=" + composed.equals(
                    Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

            String probe = "A\uD83D\uDE00";
            byte[] encodedProbe = probe.getBytes(StandardCharsets.UTF_8);
            System.out.println("utf16-units=" + probe.length());
            System.out.println("code-points=" + probe.codePointCount(0, probe.length()));
            System.out.println("utf8-length=" + encodedProbe.length);
            System.out.println("utf8-hex=" + HexFormat.of().formatHex(encodedProbe));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac BoundaryRoundTrip.java
java BoundaryRoundTrip
```

Kết quả chuẩn (không phụ thuộc khả năng hiển thị emoji của terminal vì chỉ in các nhãn ASCII và số):

```text
file-bytes-match=true
file-text-match=true
wire-text-match=true
wrong-charset-match=false
unicode-equal-before=false
unicode-equal-after=true
utf16-units=3
code-points=2
utf8-length=5
utf8-hex=41f09f9880
```

Giải thích: `wire` là dữ liệu byte mà một giao thức truyền thực tế phải mang đi; `disk` là byte nằm trên tệp. `Arrays.equals(wire, disk)` xác nhận từng byte giống nhau. `original.equals(restored)` xác nhận nội dung giải mã giống dữ liệu nguồn. `original.equals(wrong)` là `false` vì cùng byte đã bị giải mã theo charset khác.

Trong hệ thống thật, thay "giả lập payload" bằng byte thu được **sau khi đi qua mạng/hàng đợi/message broker**; chỉ gọi `getBytes(UTF_8)` ở đầu nhận từ chuỗi gốc sẽ bỏ qua khả năng dữ liệu đã bị thay đổi trên đường truyền.

## 4. Đối chiếu qua ranh giới tệp

### Ghi và đọc chuỗi với charset rõ ràng

Java 11+ có các phương thức `Files.writeString` và `Files.readString`; chúng dùng UTF-8 nếu không truyền charset. Để hợp đồng được hiển thị ngay trong code, có thể truyền tường minh:

```java
Files.writeString(path, source, StandardCharsets.UTF_8);
String actual = Files.readString(path, StandardCharsets.UTF_8);
boolean sameText = source.equals(actual);
```

Đoạn trên minh họa trong ngữ cảnh đã có các biến `path` (`Path`) và `source` (`String`), cùng xử lý `IOException`. Với dữ liệu nhị phân hoặc khi cần kiểm tra chính xác byte, dùng `Files.write(path, byte[])` và `Files.readAllBytes(path)`.

Một số API cũ hoặc overload không có charset rõ ràng, ví dụ `new FileReader(file)` trong Java 17, dùng charset mặc định của runtime. Không nên trộn tùy tiện cách đọc/ghi dựa trên mặc định với cách cố định UTF-8. Java 18+ chuẩn hóa mặc định UTF-8 cho nhiều API qua JEP 400, nhưng điều đó không làm mọi luồng console và mọi tệp lịch sử tự động trở thành UTF-8.

### BOM, xuống dòng và biến đổi ngoài ý muốn

- **BOM (Byte Order Mark):** Một tệp UTF-8 có thể bắt đầu bằng ba byte `ef bb bf`. Khi giải mã UTF-8 thành chuỗi, dấu này có thể hiện thành ký tự đầu `U+FEFF`; `"header".equals(text)` khi ấy là `false` dù màn hình không cho thấy dấu lạ. Chỉ loại BOM theo chính sách định dạng tệp đã thống nhất, không xóa mọi `U+FEFF` tùy tiện giữa nội dung.
- **Xuống dòng:** `\n` (LF) và `\r\n` (CRLF) là các dãy khác nhau cả ở `String` và byte. API `readAllLines` trả về các dòng **không giữ ký tự kết thúc dòng**; việc ghép lại có thể thay đổi dữ liệu. Nếu cần đối chiếu nguyên vẹn, ưu tiên `readString` hoặc byte thô.
- **Đầu/cuối văn bản:** `trim()`, `strip()`, việc tự thêm `println` hoặc bộ lọc chuyển đổi newline có thể đổi nội dung. Ghi lại các bước biến đổi này khi truy tìm khác biệt.
- **Byte không tương thích charset:** Phương thức tạo `String` tiện lợi có thể thay byte lỗi bằng `U+FFFD`. Một chuỗi đọc được không tự chứng minh rằng toàn bộ byte đều hợp lệ theo định dạng đã cam kết.

Khi biết định dạng tệp cho phép BOM ở đầu, có thể kiểm tra:

```java
if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
    text = text.substring(1);
}
```

Đây chỉ là đoạn minh họa sau khi đã đọc tệp thành biến `text`. Việc loại BOM nên diễn ra **một lần tại ranh giới nhập dữ liệu**, có ghi rõ quy định.

## 5. Đối chiếu qua console

`System.out.println(text)` đi qua một `PrintStream`, lớp mã hóa ký tự của console/terminal và phần mềm hiển thị. Dòng chữ nhìn thấy trên màn hình là **kết quả trình bày**, không phải phép kiểm chứng rằng byte UTF-8 hay Unicode gốc còn nguyên.

Những nơi có thể xảy ra khác biệt gồm: charset của terminal hoặc output stream, shell/IDE xử lý Unicode, phông chữ không có glyph, cấu hình chuyển hướng stdout sang tệp, và newline mà `println` tự thêm. Ví dụ một emoji có thể thành hình vuông do thiếu glyph dù byte hợp lệ. Ngược lại, khi code ghi đúng chuỗi ra console nhưng redirect sang tệp theo encoding khác, đọc tệp ấy bằng UTF-8 có thể lỗi.

Cách kiểm tra đáng tin hơn là ghi **bản chẩn đoán ASCII** bên cạnh nội dung:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String text = "A\uD83D\uDE00";
System.out.println("utf8=" +
        HexFormat.of().formatHex(text.getBytes(StandardCharsets.UTF_8)));
text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Đây là đoạn minh họa có thể chạy trong `jshell`. Với chuỗi này, kết quả là:

```text
utf8=41f09f9880
U+0041
U+1F600
```

`codePoints()` cho thấy giá trị Unicode của từng code point; `HexFormat` cho thấy byte khi **chủ động mã hóa UTF-8**. Các số này không nhất thiết chính là byte do `System.out` gửi xuống terminal. Để kiểm tra file stdout đã redirect, cần xem trực tiếp byte của file đó.

Đối với nhập từ `System.in`, đừng vô tình dùng bộ đọc mặc định khác với charset mà phía terminal gửi. Nếu đã xác nhận input là UTF-8, có thể tạo `new InputStreamReader(System.in, StandardCharsets.UTF_8)` (trong một `BufferedReader`); nếu terminal thực tế gửi charset khác, việc ép UTF-8 ở Java sẽ không tự sửa dữ liệu. `System.console()` có thể trả về `null` trong IDE hoặc lúc redirect, nên không giả định chương trình luôn gắn console tương tác.

## 6. Đối chiếu qua dữ liệu truyền (HTTP, socket, message)

Một giao thức truyền byte không tự biết "chuỗi Java" là gì. Bên gửi phải **quy định mã hóa payload**; bên nhận phải giải mã nhất quán. Với nội dung dạng text truyền qua HTTP, có thể công bố charset trong `Content-Type`, chẳng hạn:

```http
Content-Type: text/plain; charset=UTF-8
```

Nếu không có `charset` hoặc định dạng giao thức quy định riêng, bên nhận phải áp dụng quy tắc của giao thức đó; không nên đoán charset từ cách chữ hiển thị. Trong Java HTTP Client (Java 11+), một cặp lựa chọn có charset tường minh là:

```java
// Trích đoạn minh họa; giả sử đã có HttpRequest.Builder builder,
// HttpResponse<byte[]> response, và String text.
builder.header("Content-Type", "text/plain; charset=UTF-8")
       .POST(HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8));

byte[] receivedBytes = response.body();
String receivedText = new String(receivedBytes, StandardCharsets.UTF_8);
```

Hai đoạn trên minh họa hai phía khác nhau; đây **không** phải chương trình độc lập gửi request. Khi kết nối thật, kiểm tra header mà dịch vụ gửi về trước khi quyết định charset giải mã. Một cách khác là chọn `BodyHandlers.ofString(StandardCharsets.UTF_8)` nếu hợp đồng đầu nhận đã chắc chắn. Với socket, dùng `OutputStreamWriter` và `InputStreamReader` cùng charset; còn giao thức nhị phân thì xử lý frame và chiều dài ở cấp byte.

**Độ dài payload** là số byte, không phải `String.length()`. Ví dụ `"A😀"` dài 3 đơn vị UTF-16 nhưng chiếm 5 byte UTF-8. Độ dài của frame, payload, hash hoặc `Content-Length` phải được tính từ byte thực sự gửi đi. Thư viện HTTP thường tự tính độ dài khi gửi body; tránh tự điền một giá trị bằng `text.length()`.

Cũng phải phân biệt **charset** (byte ↔ ký tự) với **truyền tải/biến đổi khác**: nén gzip, escaping JSON, Base64 và việc chuyển `\n` thành hai ký tự `\\n` trong dữ liệu JSON là các lớp xử lý riêng. Byte payload JSON có thể khác chuỗi hiển thị sau khi parser xử lý escape mà vẫn mang cùng giá trị văn bản theo giao thức.

## 7. Kiểm tra byte ngay tại ranh giới nhận

Ví dụ `new String(bytes, StandardCharsets.UTF_8)` có thể thay byte UTF-8 không hợp lệ bằng U+FFFD. Nếu một thông điệp cần giữ nguyên nội dung, kiểm tra **byte nhận được** trước khi đưa vào parser hoặc ghi đè dữ liệu nguồn:

~~~java
byte[] malformed = {(byte) 0xC3, 0x28};
try {
    String value = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(malformed))
            .toString();
    System.out.println(value);
} catch (CharacterCodingException error) {
    System.out.println("valid-utf8=false");
}
~~~

Đặt đoạn trong phương thức và import `java.nio.ByteBuffer` cùng các lớp `java.nio.charset.*` liên quan. Kết quả cho dữ liệu trên là `valid-utf8=false`. Kết quả giải mã strict chứng minh byte tuân thủ charset **đã chọn**, nhưng không tự chứng minh phía gửi đã chọn đúng charset theo giao thức. Bài **CharsetEncoder, CharsetDecoder và chính sách REPORT** đi sâu vào chuyển đổi nghiêm ngặt, bao gồm decoder theo luồng.

## 8. Hai chuỗi nhìn giống nhau vẫn có thể khác nhau

Unicode có thể biểu diễn ký tự có dấu theo nhiều cách. Chẳng hạn `"\u00E9"` (một code point `é`) và `"e\u0301"` (chữ `e` cộng dấu sắc kết hợp) thường nhìn giống nhau nhưng:

- `String.equals` ban đầu là `false` vì dãy đơn vị UTF-16 khác.
- UTF-8 byte cũng khác: `c3 a9` so với `65 cc 81`.
- Sau `Normalizer.normalize(value, Normalizer.Form.NFC)`, hai chuỗi trở nên bằng nhau.

```java
import java.text.Normalizer;

String first = "\u00E9";
String second = "e\u0301";
boolean rawEqual = first.equals(second); // false
boolean normalizedEqual = first.equals(
        Normalizer.normalize(second, Normalizer.Form.NFC)); // true
```

Đoạn trên là mã minh họa. **Chuẩn hóa phải là quyết định của hợp đồng dữ liệu**, không thực hiện bừa ở giữa chuỗi ký số, đường dẫn, mã định danh hay payload cần kiểm tra toàn vẹn byte: nó thay đổi biểu diễn nguồn. Nếu mục đích là hiển thị hoặc tìm kiếm không phân biệt biến thể chuẩn hóa, hãy thống nhất việc chuẩn hóa **trước khi so sánh** ở cả hai phía.

## 9. Quy trình chẩn đoán khi dữ liệu đi qua nhiều lớp

Khi dữ liệu khác giữa file, console và bên nhận, làm theo thứ tự sau:

1. **Chọn mốc chuẩn:** giữ `String` gốc tại bên gửi và `byte[]` ngay trước khi rời tiến trình. Nếu tệp là mốc chuẩn, lấy byte thô bằng `Files.readAllBytes`.
2. **Xác định hợp đồng:** ghi charset, định dạng payload, BOM có được phép hay không, quy ước newline, Unicode normalization, và các lớp nén/escape.
3. **Đối chiếu byte ở từng ranh giới:** dùng `Arrays.equals` khi có hai mảng byte, hoặc ghi kích thước và bản hex/hash của byte nguồn và byte nhận. Hash chỉ chứng minh byte đồng nhất theo mức tin cậy của thuật toán, không tự chứng minh ký tự đúng.
4. **Giải mã bằng charset đã thống nhất:** dùng `new String(bytes, charset)` nếu đầu vào đáng tin; dùng `CharsetDecoder` strict khi cần từ chối byte không hợp lệ.
5. **Đối chiếu nội dung Unicode:** so sánh bằng `String.equals`, xem `codePoints()` khi cần, kiểm tra BOM/newline/normalization nếu byte hoặc text chưa khớp.
6. **Cuối cùng mới đánh giá hiển thị:** so sánh terminal, editor, log viewer. Lỗi font hoặc cách hiển thị có thể khác với lỗi byte thật.

| Triệu chứng | Kiểm tra ưu tiên | Khả năng và hướng xử lý |
| --- | --- | --- |
| Tệp có chữ `Ã` hoặc ký tự lạ | Xem byte hex, charset lúc ghi và lúc đọc | Sai charset; thống nhất UTF-8 cho các đầu liên quan |
| Emoji hiện thành ô vuông ở console | Kiểm tra code point và UTF-8 hex trước khi in | Có thể do terminal/font; đừng đổi byte khi dữ liệu gốc đúng |
| File đọc về khác ở đầu chuỗi | Kiểm tra `ef bb bf`, `U+FEFF` | BOM; thống nhất chính sách xử lý |
| Hai chuỗi trông giống nhưng `equals` sai | Kiểm tra code point, dấu kết hợp, khoảng trắng/newline | Unicode normalization hoặc ký tự ẩn/khác dấu xuống dòng |
| API nhận sai số byte hay cắt payload | Đếm `byte[].length` và kiểm tra framing | Dùng số byte, không dùng `String.length()` |
| Đầu nhận có `�` (U+FFFD) | Giải mã strict từ byte gốc | Byte lỗi hoặc charset không khớp, không nên chấp nhận mất dữ liệu im lặng |
| Nội dung trong IDE đúng, redirect stdout bị lỗi | Xem byte của file redirect và encoding terminal | Console/luồng redirect có cấu hình mã hóa khác |

## 10. Bài tập tự kiểm tra

1. `String s = "A\uD83D\uDE00";` có `s.length()` bằng bao nhiêu? Có bao nhiêu code point? Mã hóa UTF-8 được bao nhiêu byte?
2. Một tệp lưu byte `c3 a9`. Đọc theo UTF-8 rồi theo ISO-8859-1 có giữ nguyên cùng ký tự không? Byte gốc có thay đổi chỉ bởi thao tác đọc không?
3. Hai hệ thống truyền `"e\u0301"` và `"\u00E9"`. Tại sao giao diện có thể hiển thị giống nhau dù `String.equals` là `false`? Trường hợp nào nên chuẩn hóa trước khi so sánh?
4. Nếu `System.out.println(text)` hiện ký tự lỗi, bạn nên kiểm tra `String.codePoints()`, hex UTF-8, hay đổi mã hóa tệp ngay? Vì sao?
5. Khi truyền `"A😀"` trong HTTP body UTF-8, có thể lấy `String.length()` làm độ dài body không?

**Gợi ý đáp án:** (1) 3 đơn vị UTF-16, 2 code point, 5 byte; (2) khác ký tự vì giải mã bằng charset khác, byte gốc không đổi; (3) khác cách biểu diễn Unicode, chỉ chuẩn hóa khi hợp đồng cho phép; (4) kiểm tra code point và hex để xác định lỗi dữ liệu hay lỗi hiển thị trước; (5) không, body UTF-8 có 5 byte.

### Tài liệu tham khảo

- [`String` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`StandardCharsets` và `CharsetDecoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/package-summary.html)
- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`Normalizer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
