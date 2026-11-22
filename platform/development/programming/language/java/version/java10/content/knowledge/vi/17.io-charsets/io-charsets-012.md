# Hành vi với chuỗi byte không hợp lệ theo từng API trong Java I/O

## 1. Vì sao cùng một dãy byte có thể bị xử lý khác nhau?

Trong Java, **byte** và **ký tự** không phải cùng một khái niệm. `byte[]` chỉ là dữ liệu nhị phân; muốn biến nó thành `String` hoặc ký tự đọc từ `Reader`, ta phải **giải mã** (*decode*) theo một `Charset` như `StandardCharsets.UTF_8`.

Vấn đề xuất hiện khi dãy byte **không phải biểu diễn hợp lệ của văn bản trong charset được chọn**. Chẳng hạn với UTF-8, byte mở đầu của một ký tự nhiều byte có thể bị theo sau bởi một byte không phù hợp. Các API Java **không bắt buộc xử lý lỗi ấy giống nhau**:

- Một nhóm API **thay thế đoạn lỗi** bằng ký tự thay thế, rồi vẫn trả về văn bản.
- Một nhóm API **báo lỗi** bằng ngoại lệ thay vì âm thầm tạo văn bản bị mất thông tin.
- `CharsetDecoder` cho phép ứng dụng chọn **REPORT**, **REPLACE** hoặc **IGNORE**.
- Các API chỉ đọc/ghi **byte thô** không thực hiện bước giải mã nên không phát hiện “UTF-8 sai” chỉ vì dữ liệu không hợp lệ cho UTF-8.

Điểm liên quan trực tiếp đến **Java 10** là `ByteArrayOutputStream.toString(Charset)`, overload nhận đối tượng `Charset` được bổ sung từ Java 10. Nó có chính sách **thay thế chuỗi byte không hợp lệ**, khác với các API đọc tệp văn bản `Files.readString` hoặc `Files.newBufferedReader` nghiêm ngặt.

Bài này giải thích **“Hành vi với chuỗi byte không hợp lệ theo từng API”**, thuộc chủ đề **Charset trong I/O**. Nội dung ưu tiên hợp đồng API **vẫn đang áp dụng trong Java hiện đại**, không dựa vào các hàm chuyển đổi không chuẩn hoặc hành vi lỗi thời.

### Mục tiêu sau bài học

- Phân biệt **malformed input**, **unmappable character**, **charset không đúng** và **byte thô chưa được decode**.
- Dự đoán API nào thay thế dữ liệu lỗi, API nào ném ngoại lệ và lỗi xảy ra **tại thời điểm nào**.
- Sử dụng `StandardCharsets.UTF_8` rõ ràng, không dựa vào charset mặc định của môi trường.
- Hiểu `CodingErrorAction.REPORT`, `REPLACE`, `IGNORE`, cùng `MalformedInputException` và `UnmappableCharacterException`.
- Chọn cách đọc byte, đọc văn bản “chấp nhận lỗi”, hoặc đọc văn bản “từ chối lỗi” phù hợp với tính toàn vẹn dữ liệu.
- Viết chương trình Java 17+ so sánh các API trên **cùng một mảng byte lỗi**, với stdout được kiểm chứng.

## 2. Byte không hợp lệ phải được hiểu trong ngữ cảnh charset

### 2.1. Cùng một byte có thể có ý nghĩa khác nhau với các charset

Một mảng byte không “tự khai báo” rằng nó là UTF-8, UTF-16 hay một encoding khác. Việc decode chỉ đúng khi **charset được chọn khớp cách dữ liệu đã được tạo**. Những byte hợp lệ theo một charset có thể không hợp lệ theo charset khác; thậm chí khi không lỗi cú pháp, giải mã nhầm charset vẫn có thể cho văn bản sai (*mojibake*).

Ví dụ:

~~~java
var bytes = "Tiếng Việt".getBytes(java.nio.charset.StandardCharsets.UTF_8);
var text = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
System.out.println(text); // Tiếng Việt
~~~

Khi encoder và decoder dùng đúng UTF-8, văn bản được khôi phục. Nếu thay charset giải mã bằng một charset khác, Java có thể trả về chuỗi sai **mà không hề phát hiện lỗi** nếu các byte vẫn hợp lệ theo charset đã chọn.

**Kết luận:** việc decoder không ném ngoại lệ **không chứng minh** bạn đã dùng đúng encoding của nguồn.

### 2.2. Malformed input: chuỗi byte không đúng cấu trúc encoding

Xét hai byte:

~~~java
byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
~~~

Trong UTF-8, `0xC3` mở đầu một chuỗi hai byte và cần byte tiếp theo dạng continuation `10xxxxxx`. Nhưng `0x28` là byte ASCII của ký tự `(`, không phải continuation. Vì thế dãy `C3 28` chứa một **malformed UTF-8 sequence**.

Một decoder thay thế lỗi có thể cho:

~~~text
U+FFFD U+0028
~~~

- `U+FFFD`: **REPLACEMENT CHARACTER**, thường hiển thị là `�`.
- `U+0028`: ký tự `(` được đọc hợp lệ từ byte `0x28`.

Đây là ví dụ UTF-8 cụ thể đã được kiểm chứng trong JDK. **Không suy rộng** rằng mọi dãy byte hỏng đều tạo đúng một ký tự `U+FFFD`: số đoạn lỗi, cách nhóm byte lỗi và chuỗi thay thế phụ thuộc encoding và decoder.

### 2.3. Truncated input: dữ liệu bị cắt giữa một ký tự

Một byte sequence có thể đang chờ thêm byte trong lúc đọc từng khối nhưng trở thành lỗi **khi đến cuối input**:

~~~java
byte[] truncated = {(byte) 0xE2, (byte) 0x82};
~~~

Đây là phần đầu của một chuỗi UTF-8 cần ba byte nhưng mới có hai. Nếu còn dữ liệu ở buffer tiếp theo, decoder phải ghép đủ các phần. Nếu **kết thúc luồng** mà không có byte còn lại, đây là malformed input.

**Không được** tự decode mỗi chunk độc lập bằng `new String(chunk, UTF_8)` khi một ký tự có thể nằm vắt qua ranh giới chunk. Cách đó có thể tạo `U+FFFD` giả, dù toàn bộ luồng byte hoàn toàn hợp lệ. Dùng một decoder/reader duy trì trạng thái qua các lần đọc.

### 2.4. Unmappable character khác malformed input

Theo `CharsetDecoder`, có hai loại lỗi giải mã:

| Loại | Ý nghĩa | Ví dụ khái niệm |
| --- | --- | --- |
| **Malformed input** | Các byte không phải chuỗi mã hợp lệ theo charset đang dùng. | `C3 28` trong UTF-8. |
| **Unmappable character** | Chuỗi byte hợp lệ về cấu trúc encoding nhưng không ánh xạ được thành ký tự Unicode. | Có thể gặp với một số charset/bảng ánh xạ đặc thù. |

Cả hai đều có thể được xử lý theo ba chính sách **REPORT**, **REPLACE** và **IGNORE**, nhưng được cấu hình riêng qua `onMalformedInput` và `onUnmappableCharacter`.

Đối với UTF-8 chuẩn, ví dụ `C3 28` là **malformed**, không cần cố gán nó vào loại unmappable. Khi kiểm thử một API thực tế, hãy dựa vào định nghĩa charset và ngoại lệ thực sự phát sinh.

## 3. Ba chính sách giải mã: REPORT, REPLACE, IGNORE

`CharsetDecoder` cho phép ứng dụng chọn cách xử lý lỗi:

| Chính sách | Khi gặp chuỗi byte lỗi | Phù hợp khi |
| --- | --- | --- |
| `CodingErrorAction.REPORT` | Báo lỗi tới caller; với các phép giải mã tiện ích của decoder, có thể ném `MalformedInputException` hoặc `UnmappableCharacterException`. | Dữ liệu phải đúng charset, cần phát hiện lỗi và không làm mất thông tin ngầm. |
| `CodingErrorAction.REPLACE` | Thay đoạn lỗi bằng chuỗi thay thế của decoder, mặc định thường là `U+FFFD`. | Dữ liệu dùng để hiển thị, có chính sách chấp nhận mất một phần thông tin. |
| `CodingErrorAction.IGNORE` | Bỏ qua đoạn đầu vào lỗi. | Chỉ khi nghiệp vụ **cho phép mất dữ liệu không ghi dấu**, thường không nên là mặc định. |

**Mặc định của `CharsetDecoder` mới tạo bởi `charset.newDecoder()` là `REPORT`** cho cả malformed và unmappable errors. Nhưng điều đó **không có nghĩa mọi API nhận `Charset` đều REPORT**. Một số API tạo decoder với chính sách REPLACE, còn một số API đọc file text lựa chọn báo lỗi nghiêm ngặt.

Có thể cấu hình tường minh:

~~~java
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);
~~~

Nếu yêu cầu nghiêm ngặt:

~~~java
var strictDecoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Đặt cả hai hành động giúp contract rõ ràng dù default hiện tại cũng là REPORT. `CharsetDecoder` có **trạng thái xử lý**, nên không tùy tiện chia sẻ cùng một instance đang decode giữa nhiều luồng.

## 4. Bảng so sánh hành vi theo từng API

Bảng này tập trung vào **các overload dùng charset tường minh**, tránh nhầm với overload dựa vào charset mặc định:

| API | Đầu vào/đầu ra | Hành vi khi byte decode không hợp lệ | Lưu ý phiên bản |
| --- | --- | --- | --- |
| `new String(bytes, charset)` | `byte[] → String` | **REPLACE** theo chuỗi thay thế của charset. | API đang được hỗ trợ. |
| `ByteArrayOutputStream.toString(charset)` | Byte đã ghi vào buffer → `String` | **REPLACE**. | **Thêm từ Java 10**. |
| `charset.decode(ByteBuffer)` | ByteBuffer → CharBuffer | **REPLACE** (convenience method). | Vẫn hỗ trợ. |
| `charset.newDecoder().decode(ByteBuffer)` | ByteBuffer → CharBuffer | Mặc định **REPORT**, ném `CharacterCodingException` thích hợp. | Vẫn hỗ trợ. |
| Decoder với `REPLACE` | ByteBuffer → CharBuffer | Thay phần không hợp lệ. | Tùy chỉnh. |
| Decoder với `IGNORE` | ByteBuffer → CharBuffer | Bỏ byte lỗi. | Có nguy cơ mất dữ liệu. |
| `new InputStreamReader(in, charset)` | InputStream → Reader | Thường **REPLACE** theo mặc định của constructor dùng `Charset`. | Vẫn hỗ trợ. |
| `new InputStreamReader(in, charsetDecoder)` | InputStream → Reader | Theo chính sách của **decoder được truyền vào**; decoder mới mặc định REPORT. | Vẫn hỗ trợ. |
| `Files.readString(path, charset)` | File → String | **Báo IOException** khi gặp malformed/unmappable. | **Java 11+**. |
| `Files.readAllLines(path, charset)` | File → List<String> | **Báo IOException** khi đọc bytes lỗi. | Vẫn hỗ trợ. |
| `Files.newBufferedReader(path, charset)` | File → BufferedReader | **Các lời gọi đọc** báo IOException khi gặp bytes lỗi. | Vẫn hỗ trợ. |
| `Files.lines(path, charset)` | File → Stream<String> | Có thể ném **UncheckedIOException** lúc tiêu thụ Stream nếu lỗi giải mã xảy ra sau khi mở file. | Vẫn hỗ trợ. |
| `Files.readAllBytes(path)` | File → byte[] | **Không decode**, nên không đánh giá UTF-8 hợp lệ hay không. | Vẫn hỗ trợ. |
| `InputStream.read(...)` | InputStream → byte[] | **Không decode**, chỉ đọc byte thô. | Vẫn hỗ trợ. |

**Lưu ý về cách diễn đạt:** các API `Files` báo lỗi dưới hợp đồng `IOException`; kiểu con cụ thể trong ví dụ UTF-8 là `MalformedInputException`. Đừng giả định mọi lỗi đọc file đều do charset: không tồn tại file, thiếu quyền đọc hoặc lỗi đĩa cũng có thể là IOException.

## 5. `new String(byte[], Charset)`: thay thế dữ liệu lỗi

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;

byte[] invalid = {(byte) 0xC3, (byte) 0x28};
String text = new String(invalid, StandardCharsets.UTF_8);

System.out.println(text); // �(
~~~

Theo JavaDoc, constructor **luôn thay thế malformed-input và unmappable-character sequences** bằng chuỗi thay thế mặc định của charset. Với ví dụ UTF-8, chữ `�` biểu thị `U+FFFD`.

Điều đáng chú ý:

1. Caller **không nhận ngoại lệ decode** chỉ vì dãy byte không hợp lệ.
2. `text` vẫn được tạo và có thể mang **dấu hiệu thay thế**.
3. Một phần thông tin byte gốc **đã mất** khi chuyển sang chuỗi.
4. Việc thấy `U+FFFD` trong `String` **không đủ chứng minh** lỗi phát sinh khi decode: ký tự `U+FFFD` cũng có thể đã hiện diện hợp lệ trong nguồn.

Nếu phải đảm bảo byte là UTF-8 hợp lệ, **đừng dùng riêng constructor này như bước validation**. Hãy dùng decoder strict hoặc một API đọc file nghiêm ngặt, và xử lý ngoại lệ rõ ràng.

### 5.1. Vì sao nên chỉ rõ charset?

~~~java
var text = new String(bytes, StandardCharsets.UTF_8);
~~~

rõ ràng hơn:

~~~java
// Không nên dùng nếu định dạng dữ liệu đã có encoding cụ thể:
var text = new String(bytes);
~~~

Overload không chỉ rõ charset phụ thuộc quy tắc charset mặc định của runtime và có những khác biệt tài liệu về dữ liệu không hợp lệ. Dù các JDK hiện đại có chính sách charset mặc định được tiêu chuẩn hóa hơn, **dữ liệu giao tiếp vẫn nên được giải mã theo charset được quy định trong giao thức hoặc định dạng file**, không phỏng đoán theo môi trường.

### 5.2. Việc thay thế xảy ra trước khi bạn kiểm tra String

Một khi đã gọi `new String(bytes, UTF_8)` và nhận chuỗi thay thế, bạn thường không thể dựng lại **chính xác byte lỗi** từ `text.getBytes(UTF_8)`. Mã `U+FFFD` sẽ được mã hóa thành UTF-8 hợp lệ của ký tự thay thế, không phải byte `0xC3` đã hỏng.

Nếu cần giữ bằng chứng gốc để phân tích log hoặc sửa dữ liệu, hãy **giữ bản byte[] gốc**, ít nhất cho tới khi xác thực xong.

## 6. `ByteArrayOutputStream.toString(Charset)`: điểm đáng nhớ của Java 10

`ByteArrayOutputStream` giữ dữ liệu trong bộ nhớ dưới dạng byte. Từ **Java 10**, phương thức:

~~~java
public String toString(Charset charset)
~~~

cho phép giải mã bytes đã tích lũy bằng một `Charset` cụ thể.

Ví dụ:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

byte[] invalid = {(byte) 0xC3, (byte) 0x28};

var buffer = new ByteArrayOutputStream();
buffer.write(invalid, 0, invalid.length);

var decoded = buffer.toString(StandardCharsets.UTF_8);
System.out.println(decoded); // �(
~~~

**Hợp đồng:** `toString(Charset)` **REPLACE** malformed và unmappable sequences, giống cơ chế của `new String(bytes, charset)` trong tình huống này. Nó **không ném `MalformedInputException`** để báo lỗi giải mã.

### 6.1. Đọc byte thô không phải decode

Hai lời gọi này có mục đích khác nhau:

~~~java
byte[] exactBytes = buffer.toByteArray(); // byte gốc, giữ nguyên C3 28
String displayText = buffer.toString(StandardCharsets.UTF_8); // text thay thế lỗi
~~~

- `toByteArray()` trả một bản sao của dữ liệu byte trong buffer, **không giải mã**.
- `toString(Charset)` giải mã và có thể thay dữ liệu không hợp lệ.
- Việc tạo chuỗi **không sửa lại byte đang lưu trong buffer**.

Nếu dữ liệu có thể không phải text, hãy xử lý `byte[]` như byte cho tới khi biết định dạng và charset chính xác.

### 6.2. Đừng nhầm overload có và không có Charset

`ByteArrayOutputStream.toString()` không tham số dùng charset mặc định; `toString(Charset)` nêu rõ encoding; những overload nhận tên charset theo `String` cũng tồn tại. Đối với dữ liệu có định dạng xác định, ưu tiên `toString(StandardCharsets.UTF_8)` thay vì bỏ charset.

**Không dùng overload `toString(int hibyte)` đã bị deprecated.** Nó không thực hiện chuyển đổi byte sang ký tự theo một charset đúng nghĩa, không phù hợp kiến thức Java hiện đại.

### 6.3. Khi cần đọc nghiêm ngặt từ ByteArrayOutputStream

Nếu byte trong buffer phải là UTF-8 hợp lệ:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

var text = StandardCharsets.UTF_8
        .newDecoder()                  // mặc định REPORT
        .decode(ByteBuffer.wrap(buffer.toByteArray()))
        .toString();                    // có thể ném CharacterCodingException
~~~

Đặt mã trong phương thức xử lý hoặc khai báo `CharacterCodingException`/`IOException` phù hợp. **Không thể chuyển `ByteArrayOutputStream.toString(Charset)` từ REPLACE sang REPORT chỉ bằng một tham số khác**; phải dùng decoder có chính sách bạn muốn.

## 7. `Charset.decode(ByteBuffer)` khác `CharsetDecoder.decode(ByteBuffer)`

Hai lời gọi trông rất giống nhau nhưng có hợp đồng khác:

~~~java
var utf8 = java.nio.charset.StandardCharsets.UTF_8;

// Convenience API: sử dụng chính sách REPLACE
var lenient = utf8.decode(java.nio.ByteBuffer.wrap(invalid));

// Decoder được tạo mới: mặc định REPORT
var strict = utf8.newDecoder().decode(
        java.nio.ByteBuffer.wrap(invalid));
~~~

Với byte `C3 28`:

- `utf8.decode(...)` trả `CharBuffer` có ký tự thay thế rồi `(`.
- `utf8.newDecoder().decode(...)` **ném `MalformedInputException`** trong trường hợp được minh họa.

JavaDoc của `Charset.decode` mô tả phép tiện ích này gần tương đương tạo decoder với `onMalformedInput(REPLACE)` và `onUnmappableCharacter(REPLACE)`. **Đừng suy luận rằng mọi phương thức có tên `decode` đều strict.**

### 7.1. Dùng `CharsetDecoder` với cấu hình tường minh

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var utf8 = StandardCharsets.UTF_8;

// Strict: có lỗi thì báo.
var report = utf8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

// Lenient: có lỗi thì thay thế.
var replace = utf8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);

// Lossy: có lỗi thì bỏ.
var ignore = utf8.newDecoder()
        .onMalformedInput(CodingErrorAction.IGNORE)
        .onUnmappableCharacter(CodingErrorAction.IGNORE);
~~~

**Ví dụ kết quả với `C3 28`:**

| Decoder | Kết quả |
| --- | --- |
| `report.decode(ByteBuffer.wrap(invalid))` | `MalformedInputException` |
| `replace.decode(ByteBuffer.wrap(invalid))` | `U+FFFD U+0028` |
| `ignore.decode(ByteBuffer.wrap(invalid))` | `U+0028`, bỏ mất byte lỗi |

Không chọn `IGNORE` chỉ vì muốn “đọc được file”: nó có thể làm biến mất ký tự phân tách, giá trị quan trọng hoặc một phần văn bản mà ứng dụng cần để kiểm tra tính toàn vẹn.

### 7.2. `CodingErrorAction.REPLACE` có thể dùng chuỗi thay thế khác

`CharsetDecoder.replaceWith(String)` cho phép đặt chuỗi thay thế tùy chỉnh nếu hợp lệ với decoder; mặc định với decoder chuẩn thường là `U+FFFD`.

~~~java
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith("?");
~~~

Khi muốn hiển thị dữ liệu lỗi, dùng ký tự thay thế có thể hữu ích. Nhưng thay bằng `?` làm giảm khả năng phân biệt dấu hỏi thật với dữ liệu lỗi, nên phải chọn theo nhu cầu.

### 7.3. Đừng chia sẻ decoder đang hoạt động giữa các luồng

Một `CharsetDecoder` có trạng thái và quy trình `reset/decode/flush` riêng. Hãy dùng **decoder mới cho mỗi hoạt động decode độc lập** hoặc quản lý vòng đời chính xác. Một instance đang decode không phải một dịch vụ stateless tùy ý chia sẻ đồng thời.

Với decode theo nhiều buffer, cần hiểu `CoderResult.UNDERFLOW`, `OVERFLOW`, `endOfInput` và `flush()`. Nếu không cần xử lý byte ở tầng rất thấp, **`InputStreamReader` dùng một decoder được cấu hình đúng** thường dễ bảo trì hơn.

## 8. `InputStreamReader`: truyền Charset hay truyền CharsetDecoder?

`InputStreamReader` là cầu nối từ `InputStream` (byte) sang `Reader` (ký tự). Nó có hai constructor đáng phân biệt.

### 8.1. `InputStreamReader(InputStream, Charset)`: thay thế dữ liệu lỗi

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

byte[] invalid = {(byte) 0xC3, (byte) 0x28};

try (var reader = new InputStreamReader(
        new ByteArrayInputStream(invalid),
        StandardCharsets.UTF_8)) {
    // reader.read(...) trả các ký tự bao gồm U+FFFD thay cho byte lỗi
}
~~~

Với constructor nhận **`Charset`**, ví dụ Java 17+/JDK hiện đại trên byte `C3 28` cho ký tự `U+FFFD` và `(`. Nó **không tương đương mặc định strict** với `Files.newBufferedReader(path, UTF_8)`.

### 8.2. `InputStreamReader(InputStream, CharsetDecoder)`: theo decoder được truyền

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder(); // mặc định REPORT

try (var reader = new InputStreamReader(
        new ByteArrayInputStream(invalid),
        decoder)) {
    reader.read(); // có thể ném MalformedInputException
}
~~~

**Bước khác biệt nằm ở đối số thứ hai**:

- `StandardCharsets.UTF_8` có kiểu **`Charset`**.
- `StandardCharsets.UTF_8.newDecoder()` có kiểu **`CharsetDecoder`**.

Nếu decoder đã cấu hình `REPLACE` hoặc `IGNORE`, `InputStreamReader` sẽ sử dụng chính sách đó.

### 8.3. Lỗi có thể xuất hiện khi gọi `read()`, không phải khi mở reader

`InputStreamReader` tạo ra một đối tượng Reader trước khi bạn bắt đầu đọc. Các byte hỏng thường chỉ được phát hiện **khi quá trình đọc thật sự decode tới chúng**.

Nếu bạn cần kiểm tra **toàn bộ** tài liệu là UTF-8 hợp lệ, phải thực sự **đọc tới cuối** theo một decoder strict. Chỉ tạo Reader, kiểm tra `ready()` hoặc đọc vài ký tự đầu không chứng minh phần còn lại của file hợp lệ.

### 8.4. Đọc theo chunks không được tự làm đứt ký tự đa byte

`InputStreamReader` quản lý trạng thái byte và ký tự qua các lần gọi `read()`; một ký tự UTF-8 chia qua hai lần đọc không nên bị xem là malformed nếu luồng còn byte hoàn chỉnh.

Đối chiếu phản mẫu:

~~~java
// PHẢN MẪU nếu mỗi chunk có thể kết thúc giữa một ký tự UTF-8:
// while ((n = in.read(bytes)) != -1) {
//     text.append(new String(bytes, 0, n, StandardCharsets.UTF_8));
// }
~~~

Ở phản mẫu, `new String` giải mã từng mảnh độc lập và có thể chèn `U+FFFD` ngay giữa một ký tự hợp lệ. **Giải pháp:** dùng một Reader/CharsetDecoder xuyên suốt stream và đúng quy trình hết input.

## 9. `Files` đọc văn bản: chính sách báo lỗi

Các API đọc văn bản của `java.nio.file.Files` sử dụng hợp đồng khác với `new String(bytes, charset)`. Khi phát hiện malformed hoặc unmappable byte sequence, chúng **báo IOException** thay vì âm thầm thay thế và trả chuỗi theo cách của String constructor.

### 9.1. `Files.readString(path, charset)` — Java 11+

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data.txt");

String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Nếu bytes trong file không hợp lệ với UTF-8, lời gọi có thể ném `MalformedInputException` (một loại `IOException`) hoặc lỗi decode phù hợp khác. **Không giống** `new String(Files.readAllBytes(path), UTF_8)`, vốn dùng chính sách REPLACE.

Cách dùng mặc định:

~~~java
var text = Files.readString(path); // tương đương dùng UTF-8
~~~

`readString(path)` và `readString(path, UTF_8)` vẫn có thể báo lỗi khi byte UTF-8 không hợp lệ. `Files.readString` bắt đầu có từ **Java 11**, nên đây là ví dụ API hiện đại chạy trên Java 17+, **không phải API được giới thiệu từ Java 10**.

Phương thức này đọc toàn bộ file vào String, thích hợp với file nhỏ/vừa; không nên dùng để nạp dữ liệu text có kích thước cực lớn một cách máy móc.

### 9.2. `Files.readAllLines(path, charset)`

~~~java
var lines = Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

Tương tự, khi đọc toàn bộ dòng mà gặp byte malformed/unmappable, phương thức báo `IOException`. Nó **không bảo đảm cứ có vài dòng hợp lệ đầu tiên thì sẽ trả chúng và bỏ phần lỗi**. Nếu thao tác không hoàn thành, caller nhận lỗi.

### 9.3. `Files.newBufferedReader(path, charset)`

~~~java
try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // sử dụng các dòng hợp lệ
    }
}
~~~

JavaDoc nói **các phương thức `Reader` đọc file ném `IOException` nếu gặp malformed hoặc unmappable byte sequence**.

Một khác biệt dễ bỏ sót:

~~~java
// Có thể thay thế byte lỗi:
new java.io.BufferedReader(new java.io.InputStreamReader(
        Files.newInputStream(path), StandardCharsets.UTF_8));

// Báo lỗi khi byte sai charset:
Files.newBufferedReader(path, StandardCharsets.UTF_8);
~~~

**Hai cách đều trả `BufferedReader` nhưng không nhất thiết có cùng chính sách lỗi.** Đừng nhìn kiểu return mà suy luận hành vi decode; hãy xem API tạo Reader và decoder bên trong.

### 9.4. `Files.lines(path, charset)`: lỗi có thể xuất hiện khi Stream được tiêu thụ

~~~java
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    System.err.println("Error while reading stream: " + ex.getCause());
}
~~~

`Files.lines` tạo một Stream dòng **lazy**, giữ tài nguyên file mở cho tới khi đóng. Nếu mở file thất bại, bản thân `Files.lines` có thể ném **checked `IOException`**. Nếu byte lỗi được phát hiện **sau khi Stream đã trả về**, JavaDoc nói lỗi I/O đó sẽ được bọc trong **`UncheckedIOException`** tại thao tác Stream gây việc đọc, chẳng hạn `forEach` hoặc `toList`.

**Cẩn thận với code:** đoạn minh họa trên nằm trong phương thức đã khai báo `throws IOException` hoặc có một `catch (IOException)` bên ngoài. Catch `UncheckedIOException` không thay thế việc xử lý lỗi checked khi mở file.

Một mẫu xử lý cả hai:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    var selected = lines.filter(s -> !s.isBlank()).toList();
    System.out.println(selected.size());
} catch (UncheckedIOException ex) {
    // Lỗi đọc/decode sau khi Stream đã được mở.
    throw new java.io.IOException("Invalid text while streaming", ex.getCause());
} catch (java.io.IOException ex) {
    // Lỗi mở file hoặc lỗi I/O khác.
    throw ex;
}
~~~

Đoạn trên là ví dụ khi phương thức bao quanh **khai báo `throws IOException`**. Việc chuyển `UncheckedIOException` trở lại checked `IOException` là một lựa chọn tổ chức lỗi của ứng dụng, không phải bắt buộc.

**Ranh giới quan trọng:** chỉ tạo `Stream` chưa có nghĩa toàn bộ file đã được kiểm chứng. Nếu pipeline dừng sớm nhờ `findFirst` hoặc `limit`, nó có thể **chưa chạm tới đoạn byte lỗi ở cuối file**.

## 10. `Files.readAllBytes` và InputStream: không kiểm tra encoding

~~~java
byte[] raw = Files.readAllBytes(path);
~~~

Phương thức này chỉ đọc **byte thô**, không biết chúng là JPEG, ZIP, UTF-8 hay dữ liệu giao thức riêng. Nếu file chứa `C3 28`, `Files.readAllBytes` vẫn có thể trả đúng hai byte này mà không có lỗi charset.

Tương tự:

~~~java
try (var in = Files.newInputStream(path)) {
    byte[] raw = in.readAllBytes(); // chỉ đọc byte, không decode
}
~~~

**Lỗi I/O vẫn có thể xảy ra**, ví dụ file không tồn tại hoặc bị đọc lỗi. Nhưng đó không phải lỗi “UTF-8 sai” do một decoder phát hiện.

Lợi ích của giữ byte thô:

- Có thể xác thực bằng decoder strict sau khi đã biết charset.
- Có thể ghi hash hoặc giữ mẫu byte lỗi để gỡ sự cố.
- Có thể chọn decoder REPLACE/IGNORE sau khi đã hiểu chính sách dữ liệu.
- Có thể truyền byte nguyên bản tới thành phần có trách nhiệm giải mã đúng giao thức.

**Phản mẫu:** gọi `Files.readAllBytes` rồi ngầm tin rằng dữ liệu chắc chắn hợp lệ chỉ vì lệnh đọc không báo exception.

## 11. Lỗi phát hiện ở thời điểm nào?

| API | Khi nào có thể phát hiện lỗi decode? | Kiểu kết quả/lỗi |
| --- | --- | --- |
| `new String(bytes, UTF_8)` | Ngay khi xây dựng String, nhưng xử lý bằng REPLACE. | Chuỗi có ký tự thay thế. |
| `ByteArrayOutputStream.toString(UTF_8)` | Khi gọi chuyển buffer thành String, nhưng REPLACE. | Chuỗi có ký tự thay thế. |
| `UTF_8.decode(buffer)` | Khi decode toàn bộ buffer, nhưng REPLACE. | `CharBuffer` có ký tự thay thế. |
| `UTF_8.newDecoder().decode(buffer)` | Trong lời gọi decode. | Checked `CharacterCodingException` khi lỗi. |
| `InputStreamReader(in, UTF_8.newDecoder())` | Khi `read` decode tới byte lỗi. | `IOException`/`MalformedInputException`. |
| `Files.readString` | Khi thực hiện lời gọi đọc file. | Checked `IOException`. |
| `Files.readAllLines` | Khi thực hiện lời gọi đọc file. | Checked `IOException`. |
| `Files.newBufferedReader` | Khi dùng Reader để đọc đến lỗi. | Checked `IOException` trong thao tác đọc. |
| `Files.lines` | Có thể khi mở file hoặc khi terminal operation tiêu thụ Stream. | `IOException` khi mở; `UncheckedIOException` sau khi Stream trả về. |
| `Files.readAllBytes` | Không có bước decode để phát hiện lỗi charset. | Byte thô hoặc lỗi I/O không liên quan giải mã. |

Nếu ứng dụng chỉ nhìn vào kiểu ngoại lệ, hãy nhớ `MalformedInputException` và `UnmappableCharacterException` là các trường hợp cụ thể của `CharacterCodingException`, mà chính nó là một dạng `IOException`. `UncheckedIOException` là wrapper runtime chứa **cause `IOException`**.

**Đừng lấy thông điệp ngoại lệ cụ thể làm API contract.** JDK có thể báo thông tin byte/index khác nhau; dùng kiểu lỗi và ngữ cảnh do ứng dụng tự ghi.

## 12. Ví dụ Java 17+ hoàn chỉnh: cùng byte lỗi, nhiều API khác hành vi

Tạo file **`CharsetInvalidBytesDemo.java`**:

~~~java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.Locale;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CharsetInvalidBytesDemo {
    static String points(String s) {
        return s.codePoints()
                .mapToObj(code -> String.format(Locale.ROOT, "U+%04X", code))
                .collect(Collectors.joining(" "));
    }

    static String readAll(Reader reader) throws IOException {
        StringBuilder result = new StringBuilder();
        char[] buffer = new char[16];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            result.append(buffer, 0, count);
        }
        return result.toString();
    }

    public static void main(String[] args) throws IOException {
        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        Charset utf8 = StandardCharsets.UTF_8;

        System.out.println("String=" + points(new String(invalid, utf8)));

        ByteArrayOutputStream bytesOut = new ByteArrayOutputStream();
        bytesOut.write(invalid);
        System.out.println("ByteArrayOutputStream=" +
                points(bytesOut.toString(utf8)));

        System.out.println("Charset.decode=" +
                points(utf8.decode(ByteBuffer.wrap(invalid)).toString()));

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(invalid), utf8)) {
            System.out.println("InputStreamReader(Charset)=" +
                    points(readAll(reader)));
        }

        CharsetDecoder strict = utf8.newDecoder();
        try {
            strict.decode(ByteBuffer.wrap(invalid));
        } catch (MalformedInputException ex) {
            System.out.println("Decoder REPORT=" +
                    ex.getClass().getSimpleName());
        }

        CharsetDecoder replace = utf8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPLACE);
        System.out.println("Decoder REPLACE=" +
                points(replace.decode(ByteBuffer.wrap(invalid)).toString()));

        CharsetDecoder ignore = utf8.newDecoder()
                .onMalformedInput(CodingErrorAction.IGNORE);
        System.out.println("Decoder IGNORE=" +
                points(ignore.decode(ByteBuffer.wrap(invalid)).toString()));

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(invalid), utf8.newDecoder())) {
            readAll(reader);
        } catch (MalformedInputException ex) {
            System.out.println("InputStreamReader(Decoder)=" +
                    ex.getClass().getSimpleName());
        }

        Path file = Files.createTempFile("charset-invalid-demo-", ".bin");
        try {
            Files.write(file, invalid);
            System.out.println("Files.readAllBytes=" +
                    (Files.readAllBytes(file).length));

            try {
                Files.readString(file, utf8);
            } catch (MalformedInputException ex) {
                System.out.println("Files.readString=" +
                        ex.getClass().getSimpleName());
            }

            try {
                Files.readAllLines(file, utf8);
            } catch (MalformedInputException ex) {
                System.out.println("Files.readAllLines=" +
                        ex.getClass().getSimpleName());
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(file, utf8)) {
                readAll(reader);
            } catch (MalformedInputException ex) {
                System.out.println("Files.newBufferedReader=" +
                        ex.getClass().getSimpleName());
            }

            try (Stream<String> lines = Files.lines(file, utf8)) {
                lines.toList();
            } catch (UncheckedIOException ex) {
                System.out.println("Files.lines=" +
                        ex.getClass().getSimpleName() + "(" +
                        ex.getCause().getClass().getSimpleName() + ")");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CharsetInvalidBytesDemo.java
java CharsetInvalidBytesDemo
~~~

**Stdout đã được kiểm chứng trên JDK 24:**

~~~text
String=U+FFFD U+0028
ByteArrayOutputStream=U+FFFD U+0028
Charset.decode=U+FFFD U+0028
InputStreamReader(Charset)=U+FFFD U+0028
Decoder REPORT=MalformedInputException
Decoder REPLACE=U+FFFD U+0028
Decoder IGNORE=U+0028
InputStreamReader(Decoder)=MalformedInputException
Files.readAllBytes=2
Files.readString=MalformedInputException
Files.readAllLines=MalformedInputException
Files.newBufferedReader=MalformedInputException
Files.lines=UncheckedIOException(MalformedInputException)
~~~

### 12.1. Vì sao in Unicode code point thay cho ký tự lỗi?

Phương thức `points` biến mỗi code point thành chuỗi `U+XXXX`. Nhờ vậy, stdout **không phụ thuộc font hoặc khả năng hiển thị `�` của terminal**. Dãy `C3 28` trong UTF-8 được trình bày rõ thành `U+FFFD U+0028` khi dùng chính sách REPLACE.

Điều này hữu ích khi viết test hoặc log debug vấn đề encoding: hiển thị glyph có thể không đủ để phân biệt byte lỗi, ký tự replacement thật và lỗi font.

### 12.2. Tại sao `Files.lines` hiện dưới dạng `UncheckedIOException`?

Khác với `readString` đọc ngay, `Files.lines` trả Stream và trì hoãn việc đọc. Lỗi decode xuất hiện khi `lines.toList()` tiêu thụ dữ liệu. Vì đọc diễn ra **sau khi lời gọi `Files.lines` trả về**, API gói IOException vào `UncheckedIOException`.

Với các lỗi mở file, `Files.lines` vẫn khai báo `throws IOException`. Chương trình `main throws IOException` cho phép nhánh checked đó lan truyền; còn nhánh decode muộn được bắt bằng `UncheckedIOException`.

### 12.3. Tại sao `InputStreamReader(Charset)` và `InputStreamReader(Decoder)` khác nhau?

- Constructor nhận `Charset` sử dụng chính sách thay thế lỗi ở ví dụ.
- Constructor nhận `CharsetDecoder` tuân theo decoder **mặc định REPORT** được truyền vào.

Điểm quyết định là **hợp đồng khởi tạo decoder**, không phải “chúng đều có chữ Reader”.

### 12.4. Tại sao bài thử không sử dụng một file thực tế trong dự án?

Chương trình tạo **file tạm** chứa chính hai byte `C3 28`, đọc thử bằng các API khác nhau, rồi xóa file trong `finally`. Mọi phép thử cùng dùng một nội dung byte và charset UTF-8, tránh phụ thuộc vào file của người dùng hoặc encoding của terminal.

Đoạn code đóng Reader/Stream đúng cách bằng `try-with-resources`, nên vẫn phù hợp với thực hành I/O hiện đại.

## 13. Trường hợp byte lỗi nằm ở cuối file hoặc giữa các buffer

Lỗi không phải lúc nào cũng nằm ở byte đầu tiên.

Ví dụ file có:

~~~text
48 65 6C 6C 6F 0A E2 82
~~~

Các byte đầu là `Hello` và xuống dòng; `E2 82` là phần đầu chưa đủ của ký tự UTF-8 ba byte.

- `new String(bytes, UTF_8)` có thể trả `Hello` cùng ký tự thay thế ở cuối theo chính sách REPLACE.
- `Files.readString(path, UTF_8)` phải phát hiện lỗi khi đọc hết input và không thể hoàn tất trả String hợp lệ.
- `Files.newBufferedReader` có thể đọc một số ký tự/dòng trước rồi ném lỗi khi gặp đoạn cuối.
- `Files.lines` có thể cho bạn đọc một dòng đầu, rồi ném `UncheckedIOException` khi terminal operation đi đến đoạn lỗi.
- Nếu luồng bị đọc/chấm dứt **trước khi tới bytes lỗi**, bạn chưa chứng minh toàn bộ file hợp lệ.

**Không dùng short-circuiting làm kiểm tra tính hợp lệ của cả file:**

~~~java
// Chỉ kiểm tra dữ liệu mà pipeline thật sự đọc:
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    var first = lines.findFirst();
}
~~~

Nếu phần byte lỗi nằm ở cuối file, việc chỉ gọi `findFirst` có thể không đi đến vị trí ấy. Muốn xác thực tất cả bytes, cần giải mã toàn bộ theo chính sách REPORT.

## 14. Khi nào lỗi charset không được phát hiện dù kết quả bị sai?

Một trong những lỗi khó debug nhất là **mojibake**: byte hoàn toàn hợp lệ theo charset dùng để decode nhưng **không phải charset nguồn**.

Ví dụ nếu file thực sự được mã hóa theo charset A nhưng ứng dụng đọc theo charset B và các bytes hợp lệ theo B, cả decoder strict cũng có thể trả về một chuỗi sai mà **không ném `MalformedInputException`**.

Điều đó khác với dãy UTF-8 thật sự malformed:

| Tình huống | Strict decoder có phát hiện chắc chắn? |
| --- | --- |
| Dãy byte không hợp lệ trong charset đã chọn | Có, khi thực sự decode qua đoạn lỗi. |
| Dãy byte hợp lệ nhưng charset được chọn không đúng với nguồn | **Không nhất thiết**; có thể tạo văn bản sai. |
| Dữ liệu text đúng encoding nhưng nội dung nghiệp vụ không hợp lệ | Không; cần validation nghiệp vụ riêng. |
| Dữ liệu không phải text nhưng bị ép đọc thành UTF-8 | Có thể báo lỗi hoặc tạo chuỗi vô nghĩa tùy bytes. |

**Quy trình tốt:** xác định charset từ chuẩn giao thức, metadata, hợp đồng hệ thống hoặc format file; decode strict khi cần tính toàn vẹn; sau đó kiểm tra ý nghĩa văn bản theo ứng dụng. Không dùng `Charset.defaultCharset()` như một biện pháp tự động xác định mã hóa của dữ liệu bên ngoài.

## 15. Mất dữ liệu khi dùng REPLACE/IGNORE và khả năng round-trip

Giả sử dữ liệu gốc là:

~~~text
C3 28
~~~

Dùng `new String(bytes, UTF_8)` tạo chuỗi gồm `U+FFFD U+0028`. Khi mã hóa chuỗi này ngược lại sang UTF-8, `U+FFFD` có mã byte hợp lệ **khác với byte lỗi `C3` ban đầu**. Như vậy không thể trông đợi:

~~~java
byte[] original = {(byte) 0xC3, (byte) 0x28};
String decoded = new String(original, StandardCharsets.UTF_8);
byte[] encodedAgain = decoded.getBytes(StandardCharsets.UTF_8);

// Không được khẳng định original và encodedAgain giống nhau.
~~~

**REPLACE** giữ một chỉ dấu rằng dữ liệu không giải mã được, nhưng **không bảo đảm khôi phục byte gốc**. **IGNORE** còn làm mất hẳn dấu vết đoạn lỗi trong văn bản.

Nếu làm việc với chữ ký số, hash, dữ liệu pháp lý, dữ liệu giao dịch, dữ liệu cần kiểm toán hoặc bất kỳ đầu vào nào **không được biến đổi âm thầm**, nên giữ byte nguồn và chọn giải mã strict/báo lỗi.

Nếu chỉ hiển thị log lỗi hoặc nội dung người dùng có thể dung thứ sự mất mát, REPLACE có thể là lựa chọn đúng, nhưng nên thể hiện rõ chính sách trong thiết kế.

## 16. Phân biệt chiều giải mã và chiều mã hóa

Bài tập trung vào **byte → ký tự** (*decode*). Chiều ngược lại là **ký tự → byte** (*encode*), cũng có chính sách lỗi nhưng sử dụng API khác:

| Chiều | API tiện ích | API kiểm soát chi tiết |
| --- | --- | --- |
| Decode `byte[] → String` | `new String(bytes, charset)`, `charset.decode(buffer)` | `CharsetDecoder` với REPORT/REPLACE/IGNORE |
| Encode `String → byte[]` | `string.getBytes(charset)` | `CharsetEncoder` với REPORT/REPLACE/IGNORE |

Ví dụ:

~~~java
var text = "Tiếng Việt";

// Encoding theo UTF-8:
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

// Decoding theo UTF-8:
String decoded = new String(encoded, StandardCharsets.UTF_8);
~~~

Với `String.getBytes(Charset)`, JavaDoc nêu chính sách **thay thế** malformed/unmappable character sequences khi encode; muốn phát hiện lỗi thì dùng `CharsetEncoder`. Ví dụ một charset chỉ hỗ trợ tập ký tự hẹp có thể không biểu diễn được một số chữ Unicode; đây là lỗi **encode/unmappable** khác với byte UTF-8 malformed khi decode.

`Files.writeString(path, text, charset)` dùng hợp đồng ghi văn bản và có thể ném `IOException` nếu không encode được nội dung với charset đã chọn. Do đó cũng không nên giả định mọi đường đi từ String sang bytes sẽ cùng xử lý lỗi theo một kiểu.

## 17. Chọn API theo yêu cầu nghiệp vụ

### 17.1. Dữ liệu phải hợp lệ tuyệt đối: báo lỗi

Khi nhận một `byte[]` từ network hoặc message broker với hợp đồng UTF-8, dùng decoder strict:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes) throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Nếu dữ liệu malformed, caller nhận checked exception và có thể:

1. Từ chối request/message theo hợp đồng.
2. Ghi thông tin về nguồn, tên file, địa chỉ bản ghi và số byte.
3. Lưu mẫu bytes lỗi (được phép và có bảo vệ dữ liệu phù hợp).
4. Không thay thế byte lỗi bằng dấu `�` rồi xem như dữ liệu hợp lệ.

Có thể cấu hình `onMalformedInput(REPORT)` và `onUnmappableCharacter(REPORT)` tường minh để dễ đọc.

### 17.2. Dữ liệu dùng để hiển thị: chấp nhận REPLACE

Nếu đầu vào là text phục vụ hiển thị, ứng dụng đã chọn chấp nhận nội dung hỏng:

~~~java
static String decodeUtf8ForDisplay(byte[] bytes) {
    return new String(bytes, StandardCharsets.UTF_8);
}
~~~

Hãy hiểu rằng caller không biết có bao nhiêu lỗi decode đã được thay thế chỉ từ chuỗi trả về. Khi cần theo dõi chất lượng dữ liệu, có thể làm **validation riêng** hoặc đo lỗi ở một tầng đọc strict trước, thay vì suy đoán từ sự xuất hiện của `U+FFFD`.

### 17.3. File text: ưu tiên API đọc file tường minh

Với file text không quá lớn:

~~~java
String contents = Files.readString(path, StandardCharsets.UTF_8);
~~~

Lời gọi báo lỗi khi gặp bytes malformed/unmappable. Đây là một lựa chọn phù hợp nếu ứng dụng muốn **từ chối** file sai charset.

Nếu file lớn hoặc muốn đọc từng dòng:

~~~java
try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    // Đọc và xử lý từng dòng, xử lý IOException khi dữ liệu lỗi.
}
~~~

Nếu muốn Stream dòng:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    // Thực hiện terminal operation; chú ý UncheckedIOException khi đang đọc.
}
~~~

Nếu muốn **mặc định thay thế lỗi** thay vì báo lỗi, hãy chủ động xây dựng `InputStreamReader` với charset hoặc decoder cấu hình REPLACE, không mặc định rằng `Files.newBufferedReader` có cùng chính sách.

### 17.4. Dữ liệu nhị phân: đừng decode

Nếu file là ảnh, ZIP, PDF, âm thanh, dữ liệu mã hóa hoặc payload nhị phân:

~~~java
byte[] bytes = Files.readAllBytes(path);
~~~

Không gọi `new String(bytes, UTF_8)` chỉ để “đọc file” nếu file **không phải text**. Việc replace byte nhị phân thành ký tự khiến dữ liệu không còn giữ nguyên.

### 17.5. Buffer tích lũy byte: hiểu chính sách của Java 10

Với một `ByteArrayOutputStream` nhận payload từ network:

~~~java
var payload = new java.io.ByteArrayOutputStream();
// ... ghi các byte vào payload

String display = payload.toString(StandardCharsets.UTF_8); // REPLACE
byte[] raw = payload.toByteArray();                         // không decode
~~~

Nếu API yêu cầu **UTF-8 hợp lệ**, hãy decode `raw` bằng `CharsetDecoder` REPORT thay vì coi `toString(Charset)` là bước validation.

## 18. Ngoại lệ và hướng xử lý đúng lớp

Một cách tổ chức mã rõ ràng:

~~~java
try {
    var text = Files.readString(path, StandardCharsets.UTF_8);
    // Xử lý text đã được decode thành công.
} catch (java.nio.charset.MalformedInputException ex) {
    // File có chuỗi byte malformed trong charset đã chọn.
} catch (java.nio.charset.UnmappableCharacterException ex) {
    // Chuỗi byte hợp lệ nhưng không ánh xạ được thành ký tự.
} catch (java.io.IOException ex) {
    // Các lỗi I/O khác: file không có, quyền, đọc file...
}
~~~

Mẫu trên cần nằm trong phương thức có biến `path` kiểu `Path` và các import phù hợp. Hai catch đầu là những **subclass của IOException**, nên phải bắt chúng **trước catch(IOException)**.

Với `CharsetDecoder.decode(ByteBuffer)`:

~~~java
try {
    var text = StandardCharsets.UTF_8.newDecoder()
            .decode(ByteBuffer.wrap(raw))
            .toString();
} catch (java.nio.charset.CharacterCodingException ex) {
    // Có lỗi coding theo chính sách REPORT.
}
~~~

Với `Files.lines`, lỗi decode trễ có thể xuất hiện qua `UncheckedIOException`; kiểm tra `ex.getCause()` để phân biệt khi cần. Đừng bắt mọi `RuntimeException` rồi coi tất cả là lỗi charset.

Trong xử lý batch, nếu một file hỏng và phải bỏ qua, hãy **ghi nhận file nào, charset nào và nguyên nhân** trước khi tiếp tục. Nếu dữ liệu bắt buộc không được thiếu, nên dừng hoặc chuyển lỗi lên tầng nghiệp vụ thay vì tiếp tục im lặng.

## 19. Các ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Cùng UTF-8 thì API nào cũng ném lỗi giống nhau.” | `String` và `ByteArrayOutputStream.toString(Charset)` REPLACE; `Files.readString` báo lỗi. | Đọc contract của API cụ thể. |
| “`charset.decode(buffer)` và `charset.newDecoder().decode(buffer)` giống nhau.” | Convenience `Charset.decode` REPLACE; decoder mới REPORT mặc định. | Dùng API đúng chính sách. |
| “`new String(bytes,UTF_8)` là validator UTF-8.” | Constructor thay thế byte hỏng, vẫn trả String. | Dùng decoder REPORT để xác thực. |
| “`ByteArrayOutputStream.toString(Charset)` từ Java 10 sẽ báo MalformedInputException.” | Nó dùng REPLACE theo JavaDoc. | Lấy `toByteArray()` và dùng strict decoder nếu cần. |
| “`InputStreamReader(in, UTF_8)` giống `Files.newBufferedReader(path,UTF_8)`.” | Chính sách xử lý byte lỗi khác nhau. | Dùng Reader với decoder tường minh hoặc Files theo hợp đồng. |
| “`Files.lines` lỗi sẽ luôn ném ngay khi mở Stream.” | Stream lazy; lỗi decode có thể xảy ra trong terminal operation. | Bắt `UncheckedIOException` ở lúc tiêu thụ, đóng Stream. |
| “`Files.readAllBytes` thành công tức file là UTF-8 hợp lệ.” | API không decode. | Kiểm tra bằng decoder strict nếu là text. |
| “Ký tự `�` chắc chắn do decoder thêm.” | Nó cũng có thể là ký tự hợp lệ có sẵn trong nguồn. | Giữ bytes gốc/validate khi cần chứng cứ. |
| “REPLACE cho phép khôi phục lại bytes lỗi bằng `getBytes`.” | Byte gốc đã bị thay bằng ký tự khác. | Lưu byte thô nếu cần round-trip chính xác. |
| “IGNORE không mất dữ liệu đáng kể.” | Byte lỗi biến mất mà không có dấu vết. | Chỉ dùng nếu contract cho phép bỏ dữ liệu. |
| “File có dòng đầu đọc được là toàn file hợp lệ.” | Lỗi có thể ở cuối; short-circuiting chưa đọc hết. | Decode toàn bộ để xác thực. |
| “UTF-8 không lỗi nghĩa là nội dung chữ chắc chắn đúng.” | Charset nguồn có thể sai nhưng byte vẫn hợp lệ. | Xác định encoding từ giao thức/metadata. |
| “Chia file thành chunk rồi `new String` từng chunk là an toàn.” | Có thể cắt giữa một ký tự nhiều byte. | Dùng decoder/Reader duy trì trạng thái. |
| “Mọi `IOException` đều là lỗi charset.” | I/O còn có lỗi file, quyền truy cập, thiết bị. | Phân loại ngoại lệ và ngữ cảnh. |
| “Các API nói trên đều có từ Java 10.” | `ByteArrayOutputStream.toString(Charset)` từ 10; `Files.readString` từ 11; nhiều API khác có trước. | Phân biệt lịch sử phiên bản, vẫn dùng API hiện đại. |

## 20. Bài tập kiểm tra và đáp án

### Bài 1 — String constructor

Cho:

~~~java
byte[] bad = {(byte) 0xC3, (byte) 0x28};
var s = new String(bad, StandardCharsets.UTF_8);
~~~

Hỏi `s` có được tạo thành công không, và có gì trong đó?

**Đáp án:** Có. `String(byte[], Charset)` dùng REPLACE; trong ví dụ UTF-8, kết quả chứa `U+FFFD` và ký tự `(` (`U+0028`).

### Bài 2 — Java 10 ByteArrayOutputStream

Dùng `ByteArrayOutputStream` ghi hai byte `C3 28` rồi gọi `toString(StandardCharsets.UTF_8)`. Có ném `MalformedInputException` không?

**Đáp án:** Không. Overload `toString(Charset)` từ Java 10 **thay thế đoạn lỗi**, không báo ngoại lệ decode. Nếu muốn strict, lấy byte bằng `toByteArray()` và dùng `CharsetDecoder` REPORT.

### Bài 3 — Hai cách gọi tên gần giống nhau

~~~java
var a = StandardCharsets.UTF_8.decode(ByteBuffer.wrap(bad));
var b = StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bad));
~~~

Khác biệt?

**Đáp án:** `a` dùng convenience method của `Charset` với REPLACE, còn `b` dùng decoder mặc định REPORT nên ném `MalformedInputException` trong ví dụ này. Lời gọi `b` còn yêu cầu xử lý/khai báo ngoại lệ checked.

### Bài 4 — Files.readString

File có bytes `C3 28`; gọi `Files.readString(path, UTF_8)` sẽ như thế nào?

**Đáp án:** API báo `IOException` do byte không hợp lệ. Trong ví dụ JDK 24, đó là `MalformedInputException`. Không nhận một String tự chứa `U+FFFD` như khi dùng `new String(Files.readAllBytes(path), UTF_8)`.

### Bài 5 — Stream dòng

Vì sao `Files.lines(path, UTF_8)` có thể đã trả về Stream nhưng `stream.toList()` lại ném `UncheckedIOException`?

**Đáp án:** Dữ liệu được đọc lazy. Lỗi phát sinh **sau khi** API tạo Stream, tại terminal operation, nên IOException được bọc trong `UncheckedIOException`. Vẫn cần đóng Stream đúng cách bằng try-with-resources.

### Bài 6 — InputStreamReader

~~~java
new InputStreamReader(in, StandardCharsets.UTF_8);
new InputStreamReader(in, StandardCharsets.UTF_8.newDecoder());
~~~

Hai constructor khác nhau ở đâu?

**Đáp án:** Constructor thứ nhất nhận `Charset` và có chính sách thay thế lỗi tương ứng; constructor thứ hai nhận `CharsetDecoder`, sử dụng hành động của decoder, mặc định REPORT nếu mới tạo. Với input malformed, cách thứ hai có thể ném `MalformedInputException` trong lúc đọc.

### Bài 7 — Dữ liệu lỗi nằm sau dòng đầu

Một file có dòng 1 hợp lệ và đoạn UTF-8 lỗi ở dòng 1000. Nếu dùng `Files.lines(path).findFirst()` và nhận dòng 1, có kết luận file hoàn toàn hợp lệ không?

**Đáp án:** Không. Terminal operation có thể dừng trước khi đọc tới lỗi. Muốn xác thực toàn file, phải decode toàn bộ bằng một đường strict.

### Bài 8 — REPLACE hay IGNORE?

Bản ghi nhập vào hệ thống thanh toán chứa byte UTF-8 lỗi. Có nên dùng IGNORE để “cố nhập được” không?

**Đáp án:** Không nên khi tính toàn vẹn dữ liệu là bắt buộc. IGNORE bỏ byte lỗi và có thể biến đổi nội dung quan trọng mà không báo. Dùng REPORT, từ chối đầu vào hoặc chuyển nó đến quy trình sửa dữ liệu có kiểm soát.

### Bài 9 — Mojibake

Một tệp được lưu theo encoding khác, nhưng `Files.readString(path, UTF_8)` vẫn đọc được và chữ có dấu hiển thị sai. Vì sao?

**Đáp án:** Byte có thể vẫn hợp lệ theo UTF-8 dù không phải mã hóa gốc. Strict decoder chỉ xác thực cấu trúc theo charset đã chọn, không tự xác định encoding đúng của nguồn. Cần metadata/hợp đồng dữ liệu.

### Bài 10 — Chunk boundary

Một ký tự UTF-8 dài ba byte bị chia hai byte ở chunk thứ nhất và một byte ở chunk thứ hai. Có nên dùng `new String(chunk, UTF_8)` cho mỗi chunk không?

**Đáp án:** Không. Từng chunk độc lập sẽ trông như chuỗi lỗi và có thể bị REPLACE sai. Dùng một `InputStreamReader` hoặc `CharsetDecoder` đúng quy trình xuyên suốt các chunk.

### Bài 11 — Encoding chiều ngược

Một chuỗi Unicode có ký tự không biểu diễn được trong charset đích. `String.getBytes(charset)` và `CharsetEncoder` mặc định có cùng chính sách không?

**Đáp án:** Không. `String.getBytes(Charset)` thay thế lỗi theo encoding, còn `CharsetEncoder` mới tạo mặc định REPORT. Đây là bài toán **ký tự → byte**, tách với lỗi decode byte hỏng.

### Bài 12 — Tính nguyên bản

Bạn nhận một payload cần kiểm tra checksum trên byte nguyên bản. Nên dùng `Files.readAllBytes` hay `Files.readString` rồi `getBytes`?

**Đáp án:** Dùng **byte thô** (`Files.readAllBytes` hoặc InputStream), không decode rồi encode lại. Chuyển đổi text có thể làm thay byte khi dữ liệu lỗi hoặc khi chọn sai charset, không phù hợp checksum/signature.

## 21. Checklist ứng dụng

- [ ] Tôi biết dữ liệu là text hay binary; không ép dữ liệu binary thành String.
- [ ] Tôi xác định charset theo hợp đồng, ưu tiên `StandardCharsets.UTF_8` khi chuẩn nguồn quy định UTF-8.
- [ ] Tôi hiểu “byte không hợp lệ” luôn là đánh giá **theo một charset cụ thể**.
- [ ] Tôi phân biệt malformed và unmappable, decode và encode.
- [ ] Tôi chọn **REPORT** cho dữ liệu phải hợp lệ, hoặc chủ động chấp nhận **REPLACE** khi hiển thị.
- [ ] Tôi không dùng `IGNORE` khi cần tính toàn vẹn dữ liệu.
- [ ] Tôi biết `String(byte[],Charset)` và `ByteArrayOutputStream.toString(Charset)` dùng REPLACE.
- [ ] Tôi nhớ `ByteArrayOutputStream.toString(Charset)` là overload Java 10 vẫn được dùng hiện nay.
- [ ] Tôi phân biệt `Charset.decode` (REPLACE) và `CharsetDecoder.decode` mới tạo (REPORT).
- [ ] Tôi phân biệt `InputStreamReader(InputStream,Charset)` và `InputStreamReader(InputStream,CharsetDecoder)`.
- [ ] Tôi biết `Files.readString`/`readAllLines`/`newBufferedReader` báo lỗi decoding.
- [ ] Tôi biết `Files.lines` có thể phát hiện lỗi khi terminal operation chạy và ném `UncheckedIOException`.
- [ ] Tôi không nhầm `Files.readAllBytes` thành validator encoding.
- [ ] Tôi không coi đọc một đoạn đầu thành công là xác thực cả file.
- [ ] Tôi đọc các chunk bằng decoder có trạng thái, không tách độc lập giữa một ký tự nhiều byte.
- [ ] Tôi giữ byte gốc nếu cần debug, hash, chữ ký, audit hoặc round-trip chính xác.
- [ ] Tôi không dựa vào thông điệp hoặc cách hiển thị ký tự replacement của một terminal cụ thể.
- [ ] Tôi phân biệt lỗi charset với lỗi I/O khác, và xử lý ở đúng ranh giới nghiệp vụ.

## 22. Tài liệu tham khảo chính thức đang được hỗ trợ

- [Java SE 25 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ByteArrayOutputStream.html): `toString(Charset)` **Since 10**, và chính sách luôn thay thế malformed/unmappable sequences.
- [Java SE 25 — `String`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): constructor `String(byte[], Charset)` dùng REPLACE, `getBytes(Charset)` và các overload khác.
- [Java SE 26 — `Charset.decode(ByteBuffer)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html#decode(java.nio.ByteBuffer)): convenience decode dùng REPLACE.
- [Java SE 25 — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): mặc định REPORT, `onMalformedInput`, `onUnmappableCharacter`, `replaceWith` và decode theo trạng thái.
- [Java SE 25 — `CodingErrorAction`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE`, `IGNORE`.
- [Java SE 25 — `InputStreamReader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html): bridge từ byte stream sang char stream, các constructor nhận `Charset` và `CharsetDecoder`.
- [Java SE 25 — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `readString`, `readAllLines`, `newBufferedReader`, `lines`, `readAllBytes`, ngoại lệ khi decode và tính lazy của Stream dòng.
- [Java SE 25 — `MalformedInputException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/MalformedInputException.html) và [`UnmappableCharacterException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/UnmappableCharacterException.html): phân loại lỗi character coding.
- [Java SE 25 — `CharsetEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): chính sách mã hóa trong chiều ký tự sang byte.
- [Java SE 25 — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/UncheckedIOException.html): wrapper cho I/O exception phát sinh từ API dạng Stream.

**Kết luận:** Không có một chính sách “byte lỗi” áp dụng cho mọi API Java. Với **Java 10 `ByteArrayOutputStream.toString(Charset)`**, dữ liệu malformed/unmappable bị **thay thế**; với **`CharsetDecoder` cấu hình REPORT** và các API đọc văn bản nghiêm ngặt của **`Files`**, lỗi được **báo**; còn các API byte thô **không decode**. Chọn API dựa trên yêu cầu **tính toàn vẹn dữ liệu**, thời điểm lỗi được phát hiện và khả năng chấp nhận mất thông tin.