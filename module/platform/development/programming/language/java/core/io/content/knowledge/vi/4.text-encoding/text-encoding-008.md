# Malformed input, unmappable character và chính sách xử lý trong Java

Trong ứng dụng Java, chuyển đổi văn bản giữa **byte** và **ký tự** không phải lúc nào cũng thành công. Hai loại lỗi quan trọng của Java Charset API là **malformed input** (chuỗi đơn vị đầu vào không hợp lệ theo quy tắc mã hóa) và **unmappable character** (dữ liệu đầu vào hợp lệ, nhưng không có biểu diễn tương ứng trong bộ mã đích). Java cho phép quyết định **báo lỗi**, **thay thế** hoặc **bỏ qua** khi gặp từng loại lỗi.

Bài này thuộc phần **Mã hóa văn bản** của Java I/O. Mục tiêu là phân biệt chính xác hai loại lỗi, hiểu thời điểm chúng xuất hiện trong quá trình encode/decode, cấu hình `CharsetDecoder` / `CharsetEncoder` với `CodingErrorAction` và chọn chính sách phù hợp để tránh âm thầm mất hoặc làm sai dữ liệu.

## 1. Đặt đúng ranh giới: byte, UTF-16 và Charset

Các đối tượng Java như `String`, `char[]` và `CharBuffer` chứa các **UTF-16 code unit**. Trong khi đó, file, socket hoặc `ByteBuffer` chứa **byte**. Charset quyết định cách biến đổi hai dạng biểu diễn:

```text
DECODE (giải mã):
byte[] / ByteBuffer -- CharsetDecoder (ví dụ UTF-8) --> char / CharBuffer / String

ENCODE (mã hóa):
String / CharBuffer -- CharsetEncoder (ví dụ US-ASCII) --> byte[] / ByteBuffer
```

Một `char` của Java dài 16 bit. Ký tự Unicode ngoài BMP như `😊` là **hai UTF-16 code unit** tạo thành một surrogate pair. Charset encoder đọc các code unit và phải hiểu đúng các cặp này để tạo byte. Không thể giả sử mọi `char` đều là một Unicode code point, cũng như không thể giả sử mỗi code point chỉ có một byte.

Trong Java, các API chính là:

- `java.nio.charset.Charset`: mô tả bộ mã ký tự, chẳng hạn `StandardCharsets.UTF_8` hay `StandardCharsets.US_ASCII`.
- `CharsetDecoder`: diễn giải byte thành ký tự.
- `CharsetEncoder`: diễn giải ký tự thành byte.
- `CoderResult`: kết quả thấp tầng khi mã hóa/giải mã từng phần; phân biệt thành công, thiếu dữ liệu, thiếu không gian hoặc lỗi.
- `CodingErrorAction`: quy định cách xử lý **mỗi nhóm lỗi** gồm `REPORT`, `REPLACE` và `IGNORE`.
- `MalformedInputException` và `UnmappableCharacterException`: các ngoại lệ báo loại lỗi tương ứng khi sử dụng chế độ `REPORT` và phương thức one-shot phù hợp.

Các bộ mã như UTF-8 và US-ASCII là hai ví dụ giúp nhìn rõ hai lỗi, nhưng nguyên tắc xử lý áp dụng cho nhiều charset khác.

## 2. Malformed input: dữ liệu đầu vào không hợp lệ

**Malformed input** nghĩa là các byte hoặc các UTF-16 code unit ở phía đầu vào **vi phạm quy tắc cấu trúc** của bộ mã đang dùng. Nội dung đó không phải một chuỗi mã hóa hợp lệ để xử lý đầy đủ.

### Khi giải mã (byte → char)

Giả sử chương trình giải mã theo UTF-8. Byte `0xC3` mở đầu một chuỗi UTF-8 gồm hai byte, nhưng byte kế tiếp `0x28` (dấu `(`) **không phải continuation byte** hợp lệ. Cặp `C3 28` do đó có lỗi cấu trúc.

Ví dụ dãy byte:

```text
43 C3 28 44
 C  ?  (  D
```

- `43` là chữ `C` trong ASCII/UTF-8.
- `C3` cần thêm một continuation byte hợp lệ nhưng không có, nên đây là **malformed input**.
- `28` tự nó là ký tự `(` hợp lệ trong UTF-8, và bộ giải mã có thể xử lý tiếp sau phần đầu vào hỏng tùy thuật toán, như minh họa ở ví dụ Java phía dưới.
- `44` là chữ `D` hợp lệ.

Các ví dụ malformed UTF-8 khác gồm continuation byte đứng lẻ, chuỗi mã hóa quá dài (overlong), byte mở đầu không hợp lệ, dữ liệu kết thúc khi chuỗi nhiều byte chưa hoàn thành và byte sequence mã hóa surrogate/code point vượt giới hạn Unicode.

Không nên khắc phục bằng cách xem mỗi byte là `char` hay tự bỏ byte có bit cao. Cần phân tích đúng charset và chính sách lỗi.

### Khi mã hóa (char → byte)

Malformed input cũng có thể phát sinh ở **encoder**. Một UTF-16 **high surrogate** không được theo sau bởi low surrogate tương ứng (hoặc low surrogate đứng riêng) là chuỗi UTF-16 không hợp lệ. Ví dụ `"\uD83D!"` chứa high surrogate đơn lẻ rồi đến `!`. Dù bộ mã đích là UTF-8, encoder cũng không thể biến chuỗi UTF-16 hỏng này thành Unicode text hợp lệ.

Điều cần phân biệt: ký tự `😊` có **hai** `char` vẫn là hợp lệ khi chúng tạo thành một surrogate pair đúng thứ tự. Không được coi “hai char cho một ký tự” là lỗi.

## 3. Unmappable character: đầu vào hợp lệ nhưng không biểu diễn được

**Unmappable** nghĩa là dữ liệu đầu vào đã hợp lệ theo dạng nguồn, nhưng **bộ mã đích không thể biểu diễn ý nghĩa ký tự đó**.

Ví dụ quen thuộc:

- `"Café"` là chuỗi Java hợp lệ.
- `US-ASCII` chỉ biểu diễn các ký tự có code point `U+0000..U+007F`.
- Chữ `é` (U+00E9) nằm ngoài phạm vi US-ASCII, nên mã hóa `"Café"` sang US-ASCII gặp **unmappable character**; nó **không phải** malformed UTF-16.

**Decoder cũng có thể báo unmappable** nếu một byte sequence hợp lệ theo cấu trúc của charset nhưng charset đó không ánh xạ nó sang ký tự. Việc một dãy byte cụ thể được phân loại malformed hay unmappable phụ thuộc **quy tắc charset và bộ mã hóa/giải mã**, không thể kết luận chỉ từ một byte “lớn hơn 127”. Trong UTF-8, các byte sequence không hợp lệ thường được báo malformed.

### So sánh hai loại lỗi

| Trường hợp | Malformed input | Unmappable character |
|---|---|---|
| Bản chất | Đầu vào vi phạm **cú pháp/cấu trúc** của cách biểu diễn | Đầu vào **hợp lệ**, nhưng không có ánh xạ sang biểu diễn đích |
| Ví dụ decoder | UTF-8 `C3 28` | Dãy byte hợp lệ nhưng không ánh xạ sang Unicode trong một charset cụ thể |
| Ví dụ encoder | UTF-16 high surrogate đứng lẻ khi chuyển sang UTF-8 | `é` khi chuyển từ Java text sang US-ASCII |
| Kết quả khi `REPORT` | `MalformedInputException` | `UnmappableCharacterException` |
| Thông số cấu hình | `onMalformedInput(...)` | `onUnmappableCharacter(...)` |
| Rủi ro nếu thay/bỏ | Che giấu byte đầu vào bị hỏng | Mất ký tự gốc khi chuyển sang bộ mã không hỗ trợ |

Đừng dùng `UnmappableCharacterException` làm tên gọi chung cho mọi “lỗi Unicode”, hoặc dùng `MalformedInputException` để chỉ việc font không hiển thị được emoji. **Thiếu glyph trong font** là vấn đề hiển thị, khác với việc charset encode/decode thành công hay không.

## 4. Ba chính sách xử lý: REPORT, REPLACE, IGNORE

`java.nio.charset.CodingErrorAction` định nghĩa ba lựa chọn dùng riêng cho **malformed** và **unmappable**:

| Chính sách | Hành vi | Hệ quả |
|---|---|---|
| `REPORT` | Báo lỗi cho caller; trong one-shot encode/decode thông thường sẽ ném `CharacterCodingException` tương ứng | Phát hiện dữ liệu sai và giữ caller chủ động xử lý |
| `REPLACE` | Thay chuỗi đầu vào gây lỗi bằng chuỗi hoặc byte thay thế đã cấu hình | Cho phép tiếp tục nhưng có thể **mất thông tin gốc** |
| `IGNORE` | Bỏ phần đầu vào gây lỗi, tiếp tục với phần còn lại | Dễ gây **mất dữ liệu âm thầm** và thay đổi nội dung |

**Giá trị mặc định của `CharsetDecoder` và `CharsetEncoder` mới tạo là `REPORT` cho cả hai loại lỗi.** Nhưng các API tiện ích bọc quanh charset có thể chọn mặc định **thay thế**. Vì thế phải kiểm tra hợp đồng của API đang gọi; đừng suy ra mọi cách chuyển mã đều có chung chính sách.

Cấu hình thông qua:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Đây là **đoạn minh họa**, đặt trong lớp có import `java.nio.charset.*` hoặc import các kiểu cần dùng. Hai phép cấu hình **độc lập**. Ví dụ có thể `REPORT` với malformed nhưng `REPLACE` với unmappable khi chuyển sang một charset cũ, nếu nghiệp vụ quy định đúng như vậy. Tuy nhiên, mọi cách thay/bỏ dữ liệu đều cần giải thích rõ với người dùng hoặc gắn cảnh báo/log nếu tính toàn vẹn quan trọng.

### REPLACE thực sự thay bằng gì?

- `CharsetDecoder` thường dùng ký tự thay thế Unicode `U+FFFD` (hiển thị như `�`). Có thể đổi chuỗi thay thế bằng `decoder.replaceWith("...")` nếu hợp lệ theo các giới hạn của decoder.
- `CharsetEncoder` thay bằng một hoặc nhiều **byte**; `US_ASCII.newEncoder()` thường dùng byte `?` (`0x3F`) làm replacement. Có thể cấu hình `encoder.replaceWith(byte[])` nhưng byte thay thế phải được charset chấp nhận theo hợp đồng của encoder.
- Việc thấy `?` hoặc `�` trong kết quả **không chứng minh** chính xác dữ liệu gốc bị lỗi gì: ký tự này cũng có thể vốn tồn tại trong nội dung gốc.

Sau khi thay thế, **không thể tự khôi phục** byte hoặc ký tự đã mất chỉ từ kết quả. `IGNORE` còn nguy hiểm hơn vì không giữ lại cả dấu vết của phần bị lỗi.

## 5. Ví dụ 1 — malformed UTF-8 dưới ba chính sách

Tạo tệp `MalformedUtf8Demo.java` (Java 17+):

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedUtf8Demo {
    private static String decode(byte[] bytes, CodingErrorAction action)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = {'C', (byte) 0xC3, '(', 'D'};
        try {
            decode(bytes, CodingErrorAction.REPORT);
        } catch (CharacterCodingException e) {
            System.out.println("REPORT=" + e.getClass().getSimpleName());
        }
        String replaced = decode(bytes, CodingErrorAction.REPLACE);
        System.out.println("REPLACE=" + replaced.replace("\uFFFD", "<U+FFFD>"));
        System.out.println("IGNORE=" + decode(bytes, CodingErrorAction.IGNORE));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 MalformedUtf8Demo.java
java MalformedUtf8Demo
```

Kết quả đã kiểm tra:

```text
REPORT=MalformedInputException
REPLACE=C<U+FFFD>(D
IGNORE=C(D
```

Ở đây `C3` là byte có vấn đề. Khi `REPORT`, `CharsetDecoder.decode(ByteBuffer)` báo `MalformedInputException`, là lớp con của `CharacterCodingException`. Khi `REPLACE`, phần malformed được thay bằng `U+FFFD`; mã nguồn **chỉ đổi U+FFFD thành chuỗi `<U+FFFD>` lúc in** để kết quả không phụ thuộc font terminal. Khi `IGNORE`, phần malformed bị loại khỏi kết quả.

Trong một bộ dữ liệu khác, số byte bị xem là cùng một lỗi và cách bộ giải mã phục hồi tiếp sau lỗi sẽ phụ thuộc charset/sequence cụ thể. Không nên tổng quát hóa quy tắc “bỏ đúng một byte” từ ví dụ này.

Một decoder có trạng thái; mỗi lượt xử lý độc lập trong ví dụ dùng `newDecoder()` để không tái sử dụng trạng thái sau lỗi hoặc sau khi giải mã hoàn tất.

## 6. Ví dụ 2 — unmappable US-ASCII và surrogate bị lỗi

Tạo tệp `EncoderActionsDemo.java` (Java 17+):

```java
import java.nio.CharBuffer;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class EncoderActionsDemo {
    private static String ascii(String input, CodingErrorAction action)
            throws CharacterCodingException {
        CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action);
        ByteBuffer bytes = encoder.encode(CharBuffer.wrap(input));
        byte[] result = new byte[bytes.remaining()];
        bytes.get(result);
        return new String(result, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        String text = "Caf\u00E9";
        try {
            ascii(text, CodingErrorAction.REPORT);
        } catch (CharacterCodingException e) {
            System.out.println("ASCII REPORT=" + e.getClass().getSimpleName());
        }
        System.out.println("ASCII REPLACE=" + ascii(text, CodingErrorAction.REPLACE));
        System.out.println("ASCII IGNORE=" + ascii(text, CodingErrorAction.IGNORE));

        String broken = "\uD83D!";
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .encode(CharBuffer.wrap(broken));
        } catch (CharacterCodingException e) {
            System.out.println("UTF-8 broken surrogate=" + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 EncoderActionsDemo.java
java EncoderActionsDemo
```

```text
ASCII REPORT=UnmappableCharacterException
ASCII REPLACE=Caf?
ASCII IGNORE=Caf
UTF-8 broken surrogate=MalformedInputException
```

Với `"Café"`, chữ `é` là Unicode hợp lệ nhưng US-ASCII không có biểu diễn, vì vậy `REPORT` ném `UnmappableCharacterException`. Trong Java US-ASCII encoder này, `REPLACE` dùng byte `?`; `IGNORE` xóa chữ `é` khỏi đầu ra. Việc biến `"Café"` thành `"Caf?"` hoặc `"Caf"` rõ ràng là **biến đổi mất mát**.

Biến `broken` chứa high surrogate `\uD83D` không đi cùng low surrogate. Đó là **malformed input của encoder**, kể cả khi charset đích là UTF-8 có thể biểu diễn mọi Unicode scalar value hợp lệ. Không thể “sửa” lỗi này chỉ bằng cách đổi mã đích từ ASCII sang UTF-8.

**Lưu ý về mã nguồn:** Java biên dịch escape `\u00E9` thành chữ `é`, còn `\uD83D` cố ý tạo high surrogate đơn lẻ để minh họa dữ liệu UTF-16 hỏng; đừng đem chuỗi `broken` vào luồng dữ liệu thật rồi coi đó là text hợp lệ.

## 7. Ví dụ 3 — chính sách lỗi thay đổi theo API Reader

Một nhầm lẫn thường thấy: cấu hình `CharsetDecoder.newDecoder()` mặc định `REPORT`, rồi suy ra mọi `Reader` dùng UTF-8 cũng mặc định báo lỗi. **Không đúng với mọi constructor**.

Tạo tệp `ReaderPolicyDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.io.StringWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;

public class ReaderPolicyDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {'A', (byte) 0xC3, '(', 'B'};
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            StringWriter output = new StringWriter();
            reader.transferTo(output);
            System.out.println("simple reader="
                    + output.toString().replace("\uFFFD", "<U+FFFD>"));
        }

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT))) {
            reader.transferTo(new StringWriter());
        } catch (MalformedInputException e) {
            System.out.println("strict reader=" + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ReaderPolicyDemo.java
java ReaderPolicyDemo
```

```text
simple reader=A<U+FFFD>(B
strict reader=MalformedInputException
```

Hai đoạn đọc **cùng một dãy byte**. Constructor `InputStreamReader(InputStream, Charset)` xử lý malformed/unmappable bằng cơ chế thay thế; constructor `InputStreamReader(InputStream, CharsetDecoder)` dùng **decoder do người gọi cấu hình**, nên `REPORT` được giữ và ngoại lệ xuất hiện **khi đọc**, cụ thể trong `transferTo`.

Nếu ứng dụng cần *đọc file thất bại ngay khi có văn bản không hợp lệ*, nên chọn đường đọc/cấu hình có `REPORT`. Nếu ứng dụng là trình xem file có chủ đích cho phép ký tự thay thế, `REPLACE` có thể hợp lý. Đừng để constructor tiện dụng vô tình quyết định chính sách bảo toàn dữ liệu quan trọng.

Đối với `InputStreamReader`, việc đóng `Reader` cũng đóng `InputStream` bên dưới. Lỗi chuyển mã có thể ném trong vòng lặp đọc hoặc khi hoàn tất đọc, không nhất thiết ngay lúc tạo đối tượng reader.

## 8. Một số API “tiện dụng” có mặc định khác nhau

| API hoặc cách gọi | Chính sách / điểm cần kiểm tra |
|---|---|
| `charset.newDecoder().decode(buffer)` | Decoder mới mặc định `REPORT` cho malformed và unmappable; có thể đổi trước khi decode |
| `charset.newEncoder().encode(buffer)` | Encoder mới mặc định `REPORT` cho hai loại lỗi; có thể cấu hình từng loại |
| `new String(bytes, charset)` | Java API thay các chuỗi byte malformed/unmappable bằng replacement; không dùng khi yêu cầu phát hiện mọi lỗi |
| `string.getBytes(charset)` | Java API thay chuỗi ký tự không mã hóa được bằng replacement byte; không phải đường báo lỗi strict |
| `new InputStreamReader(input, charset)` | Xử lý malformed/unmappable bằng replacement |
| `new InputStreamReader(input, decoder)` | Giữ chính sách do `CharsetDecoder` được truyền vào |
| `new OutputStreamWriter(output, charset)` | Xử lý malformed/unmappable bằng replacement |
| `new OutputStreamWriter(output, encoder)` | Giữ chính sách do `CharsetEncoder` được truyền vào |

**Đừng nhầm “cho phép ghi xong” với “dữ liệu đã được ghi chính xác”.** Ví dụ `text.getBytes(StandardCharsets.US_ASCII)` có thể hoàn tất thành công với một byte `?` thay cho `é`. Nếu muốn xác nhận lossless khi chuyển đổi giữa bộ mã, cần dùng encoder/decoder strict hoặc kiểm tra đầu vào/khả năng biểu diễn một cách có kiểm soát.

Với `Files.newBufferedReader(path, charset)`, `Files.readString(path, charset)` và các API file bậc cao khác, hãy đọc contract về malformed/unmappable của **chính phương thức đó**. Khi chính sách phải kiểm soát chặt, dùng `InputStreamReader` cùng `CharsetDecoder` tự cấu hình là cách biểu đạt ý định rõ ràng.

## 9. Cấu hình REPLACE tường minh và lựa chọn ký tự thay thế

Để decoder dùng `?` thay `U+FFFD` cho lỗi malformed (khi cấu hình cho phép):

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .replaceWith("?");
```

Đây là **mã minh họa**: cần import các lớp `CharsetDecoder`, `CodingErrorAction` và `StandardCharsets`. Chuỗi replacement của decoder phải hợp lệ về độ dài theo `maxCharsPerByte()`, không thể truyền chuỗi dài tùy ý. Nó được chèn vào **luồng ký tự đầu ra**, không phải byte.

Đối với encoder US-ASCII, có thể yêu cầu thay ký tự unmappable bằng byte đại diện cho `?`:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith(new byte[] {(byte) '?'});
```

Đây cũng là **mã minh họa**, cần import `CharsetEncoder`, `CodingErrorAction` và `StandardCharsets`. Mảng replacement phải hợp lệ cho charset, và có giới hạn kích thước. Thực tế có thể đặt `REPLACE` cho unmappable nhưng `REPORT` cho malformed để tránh bỏ qua cấu trúc Unicode hỏng trong khi hỗ trợ chuyển mã theo chính sách mất mát đã thỏa thuận.

**Cảnh báo:** Dùng dấu `?` làm replacement khiến không phân biệt được dấu hỏi hợp lệ vốn có trong text và dấu hỏi do chuyển mã lỗi. Đừng viết thuật toán “đếm dấu `?` để biết số lỗi” nếu không có thông tin bổ sung.

## 10. Khi nào chọn chính sách nào?

### REPORT — ưu tiên khi yêu cầu toàn vẹn dữ liệu

Chọn **`REPORT`** cho tình huống dữ liệu sai cần được phát hiện và xử lý:

- File cấu hình, dữ liệu lưu trữ nguồn, gói tin theo giao thức quy định UTF-8 nghiêm ngặt.
- Định danh, tên trường, mã ký, khóa tra cứu hoặc nội dung mà thay một ký tự có thể đổi ý nghĩa.
- Luồng nhập dữ liệu (ingest) cần báo chất lượng, ghi nhận lỗi và cho phép xử lý lại từ **byte gốc**.
- Khi chuyển sang một charset đích không đủ biểu diễn text, caller phải quyết định dùng UTF-8, từ chối thao tác, hoặc một phép chuyển đổi đã được phê duyệt.

Nên bắt `MalformedInputException` và `UnmappableCharacterException` ở biên mà chương trình có ngữ cảnh để xử lý. Ngoại lệ mang **độ dài đoạn lỗi** qua `inputLength()`; nó không tự cung cấp đầy đủ file path, vị trí byte tuyệt đối hay byte gốc. Hãy bổ sung ngữ cảnh một cách an toàn từ nguồn mà ứng dụng sở hữu.

Đối với xử lý incremental, `CharsetDecoder.decode(input, output, endOfInput)` có thể trả `CoderResult.malformedForLength(n)` hoặc `unmappableForLength(n)` thay vì trực tiếp ném ngoại lệ; caller phải kiểm tra kết quả và có thể gọi `throwException()` nếu muốn hành vi strict. `CoderResult.UNDERFLOW`/`OVERFLOW` là trạng thái vận hành bộ đệm, **không mặc nhiên là lỗi dữ liệu**.

### REPLACE — phù hợp khi cần tiếp tục và chấp nhận mất mát

Chọn **`REPLACE`** khi hiển thị nội dung lỗi một cách khoan dung có giá trị hơn việc dừng toàn bộ, chẳng hạn trình xem log hỏng hoặc công cụ khám phá văn bản ngoại lai. Lúc đó nên ghi rõ:

- Charset nguồn và cách phát hiện/khai báo nó.
- Ký tự/byte thay thế, và vị trí đã được thay nếu hệ thống cần khả năng truy vết.
- Nguồn dữ liệu gốc còn được lưu nếu cần phân tích lỗi.
- Đầu ra chỉ là **bản trình bày đã sửa theo chính sách**, không chứng minh đúng bằng dữ liệu ban đầu.

Không dùng `REPLACE` âm thầm trước khi tính hash, ký dữ liệu hoặc so sánh định danh mà các byte/ký tự chính xác là thiết yếu.

### IGNORE — chỉ dùng khi chủ đích bỏ dữ liệu lỗi

`IGNORE` xóa phần đầu vào gây lỗi. Nó có thể biến `"Café"` thành `"Caf"` hoặc loại byte lỗi giữa hai đoạn hợp lệ, làm dính các từ/định danh vốn tách biệt. Chỉ dùng khi yêu cầu nghiệp vụ **chấp nhận loại bỏ**, có thông tin giám sát phù hợp và tác động đã được đánh giá. Nếu mong muốn “tiếp tục đọc nhưng không giấu lỗi”, `REPLACE` kèm cảnh báo thường dễ chẩn đoán hơn.

**Không có chính sách duy nhất luôn tối ưu.** Quyết định dựa trên hợp đồng dữ liệu và rủi ro mất mát, không dựa vào việc một cách có ném exception hay không.

## 11. Xử lý dữ liệu streaming và lỗi xảy ra ở ranh giới buffer

Khi đọc qua `InputStreamReader`, `Reader` hoặc NIO buffer, lỗi chuyển mã thường chỉ xuất hiện **trong lúc thực sự đọc/ghi**. Khi một chuỗi UTF-8 nhiều byte bị chia giữa hai chunk, bộ giải mã cần giữ trạng thái để đợi chunk sau. **Thiếu byte trong một chunk chưa chắc malformed**, trừ khi đã xác nhận **kết thúc đầu vào** mà chuỗi vẫn chưa đầy đủ.

Nếu gọi trực tiếp phiên bản incremental của `CharsetDecoder`, cần tuân thủ trình tự trạng thái:

1. Chuẩn bị `ByteBuffer` và `CharBuffer`; gọi `decode(input, output, false)` cho phần đầu vào còn tiếp tục.
2. Với `UNDERFLOW`, xem xét có cần bổ sung byte hay đã hết input; `OVERFLOW` nghĩa là cần thêm chỗ ở output buffer.
3. Khi không còn byte nữa, gọi `decode(input, output, true)` để bộ giải mã xác nhận kết thúc; dữ liệu cuối còn dở có thể được báo malformed.
4. Hoàn tất `flush(output)` và xử lý kết quả. `reset()` trước một luồng nội dung mới nếu tái sử dụng decoder đúng trạng thái cho phép.
5. Nếu đang dùng `REPORT`, kiểm tra `CoderResult.isError()` và xử lý/báo lỗi; đừng bỏ qua kết quả rồi đi tiếp như thể giải mã thành công.

Quy trình trên là **mô tả cơ chế, không phải chương trình hoàn chỉnh**. Với bài toán đọc văn bản thông thường, `InputStreamReader`/`BufferedReader` cùng decoder cấu hình sẵn giúp tránh phải tự quản lý trạng thái coder. Nếu tự viết bộ xử lý từng chunk, tuyệt đối không tạo một decoder mới cho **mỗi** đoạn byte tùy ý: một sequence hợp lệ bị chia giữa hai chunk có thể bị coi thành các đoạn malformed.

Một ví dụ khác: high surrogate nằm cuối một `CharBuffer` và low surrogate ở buffer tiếp theo có thể hợp lệ khi mã hóa cùng phiên làm việc. Đừng tự coi mỗi `CharBuffer` như một chuỗi độc lập nếu muốn bảo toàn Unicode xuyên ranh giới buffer.

## 12. Ghi nhận lỗi, phục hồi và kiểm tra chất lượng dữ liệu

Một pipeline nhập văn bản đáng tin cậy nên trả lời được:

1. **Charset là gì?** Charset là một phần của hợp đồng file/giao thức; không nên tự gán UTF-8 hay Windows-1252 chỉ vì byte có vẻ “đọc được”.
2. **Nguồn byte gốc có được giữ lại không?** Nếu chỉ giữ bản text sau `REPLACE`/`IGNORE`, không thể khôi phục chính xác dữ liệu cũ.
3. **Có phân biệt loại lỗi không?** `MalformedInputException` chỉ cấu trúc đầu vào sai; `UnmappableCharacterException` chỉ mapping không tồn tại. Ở UI/log, ghi loại lỗi và thao tác đang thực hiện (encode hay decode).
4. **Bên nào quyết định chính sách?** Lớp reader/writer tiện dụng có thể thay dữ liệu ngầm. Khi strictness quan trọng, truyền `CharsetDecoder` / `CharsetEncoder` được cấu hình rõ ràng.
5. **Có thể dùng lại cùng byte sau lỗi không?** Dữ liệu lưu ở bộ nhớ / file có thể được xử lý lại bằng một decoder mới hoặc bằng pipeline retry có kiểm soát; không tự tái sử dụng coder đã ở trạng thái không hợp lệ.
6. **Có kiểm tra round-trip không?** Với một charset giới hạn, encode rồi decode có thể không trả lại text ban đầu nếu đã có replacement. Khi tính lossless quan trọng, kiểm tra sự phù hợp của charset và dùng `REPORT` trước khi lưu.

### Một tình huống thực tế

Một hệ thống xuất dữ liệu khách hàng sang US-ASCII, trong khi tên có dấu. Nếu để `getBytes(US_ASCII)` tự thay `é` thành `?`, tên sau khi lưu có thể bị hỏng vĩnh viễn mà hệ thống không báo lỗi. Cách làm phù hợp hơn là:

- Nếu định dạng đích chấp nhận UTF-8, **chọn UTF-8** và ghi rõ charset.
- Nếu định dạng bắt buộc US-ASCII, encode bằng `CharsetEncoder` có `REPORT`; báo người dùng những trường không thể xuất hoặc áp dụng phép chuyển tự (transliteration) đã được yêu cầu và kiểm chứng.
- Chỉ dùng `REPLACE`/`IGNORE` khi hợp đồng xuất dữ liệu cho phép mất ký tự.

**Transliteration** như đổi `"é"` thành `"e"` là quy tắc biến đổi ngôn ngữ riêng, **không đồng nghĩa** với chính sách `CodingErrorAction.REPLACE` và không tự có trong bộ mã ASCII.

## 13. Lỗi thường gặp

1. **Nhầm malformed và unmappable.** `C3 28` là UTF-8 malformed; `é` trong Java text chuyển sang US-ASCII là unmappable.
2. **Cho rằng UTF-8 xử lý được mọi chuỗi `String`.** UTF-8 mã hóa các Unicode scalar value; `String` có thể chứa UTF-16 surrogate lẻ, vốn là malformed.
3. **Bỏ qua charset.** Cùng byte có thể hợp lệ ở charset này nhưng sai ở charset khác. Phân tích lỗi luôn đi cùng charset thực tế.
4. **Tưởng `newDecoder()` và `new String(bytes, charset)` xử lý lỗi giống nhau.** Decoder mới mặc định `REPORT`; constructor `String` dạng này thay dữ liệu lỗi.
5. **Dùng `IGNORE` để “sửa lỗi encoding”.** Nó bỏ dữ liệu, không khôi phục byte gốc hay chữa đúng charset.
6. **Xem replacement là không mất mát.** Một `?` hoặc `U+FFFD` không đủ để tái dựng phần đã bị thay.
7. **Quên xử lý lúc đọc/ghi.** Cấu hình strict có thể ném exception trong vòng lặp I/O hoặc khi hoàn tất, không phải ngay tại constructor.
8. **Tạo decoder mới tại mỗi chunk.** Chuỗi nhiều byte nằm qua ranh giới chunk có thể bị hỏng giả. Dùng một decoder có trạng thái cho cả dữ liệu liên tục.
9. **Bỏ qua `CoderResult`.** Trong API incremental, `UNDERFLOW`/`OVERFLOW` phải được xử lý đúng, và `isError()` cần có hành vi rõ ràng.
10. **Ghi vào log cả dữ liệu thô nhạy cảm để điều tra lỗi.** Ghi loại lỗi, vị trí/phạm vi và metadata cần thiết; hạn chế hiển thị byte nguồn nếu chúng có thể chứa dữ liệu riêng tư.
11. **Hiểu nhầm sự cố font là sự cố charset.** Dữ liệu giải mã đúng vẫn có thể hiện ô vuông nếu font thiếu glyph; đó là tầng hiển thị.
12. **Dùng charset cũ thay vì xác nhận yêu cầu.** Nếu cần giữ tiếng Việt và emoji, UTF-8 thường là lựa chọn thích hợp; chỉ chọn bộ mã giới hạn khi giao thức/hệ thống yêu cầu.

## 14. Tự kiểm tra

**Câu 1.** Decoder UTF-8 gặp byte `E2 82` rồi kết thúc input. Loại lỗi nào phù hợp?  
**Đáp án:** malformed, vì sequence UTF-8 ba byte bị thiếu byte cuối khi thật sự EOF. Nếu mới là cuối *chunk* nhưng còn byte ở chunk tiếp theo, coder phải chờ thêm dữ liệu.

**Câu 2.** Encoder US-ASCII gặp chuỗi `"Hòa"` hợp lệ. Loại lỗi nào khi đụng chữ có dấu?  
**Đáp án:** unmappable. Không phải Unicode hỏng; bộ mã US-ASCII không biểu diễn được các code point đó.

**Câu 3.** `REPORT` khác `REPLACE` ở đâu?  
**Đáp án:** `REPORT` đưa lỗi tới caller, còn `REPLACE` chèn ký tự/byte đại diện và tiếp tục, thường mất khả năng phục hồi dữ liệu gốc.

**Câu 4.** Một ứng dụng đọc file bằng `new String(bytes, UTF_8)` và không gặp exception. Có bảo đảm file chứa UTF-8 hợp lệ không?  
**Đáp án:** không. API này có chính sách thay chuỗi không hợp lệ; cần decoder strict để xác minh.

**Câu 5.** Một file chứa tên quan trọng, có thể tự loại byte lỗi bằng `IGNORE` trước khi lưu không?  
**Đáp án:** không nên. Nếu hợp đồng dữ liệu đòi hỏi chính xác, hãy `REPORT` để xử lý tại nguồn hoặc yêu cầu sửa dữ liệu.

**Câu 6.** `InputStreamReader(input, UTF_8.newDecoder().onMalformedInput(REPORT))` có thể ném lỗi lúc nào?  
**Đáp án:** khi thao tác đọc thực sự yêu cầu decoder xử lý byte lỗi, ví dụ trong `read()` hoặc `transferTo()`.

## Kết luận

**Malformed input** là dữ liệu đầu vào **sai cấu trúc mã hóa**; **unmappable character** là dữ liệu hợp lệ nhưng **không có ánh xạ trong bộ mã đích**. Java tách hai nhóm để cho phép cấu hình độc lập với `onMalformedInput(...)` và `onUnmappableCharacter(...)`. Chọn `REPORT` khi cần giữ toàn vẹn và phát hiện dữ liệu sai; `REPLACE` khi có chủ đích hiển thị/tiếp tục với mất mát được chấp nhận; `IGNORE` chỉ khi việc loại bỏ đã được quy định rõ. Đồng thời phải hiểu hợp đồng của API cấp cao đang dùng vì `CharsetEncoder`/`CharsetDecoder` và các constructor tiện dụng không nhất thiết có cùng mặc định.

### Tài liệu Java SE 17

- [`CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [`CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [`CoderResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [`MalformedInputException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html), [`UnmappableCharacterException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/UnmappableCharacterException.html)
- [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
