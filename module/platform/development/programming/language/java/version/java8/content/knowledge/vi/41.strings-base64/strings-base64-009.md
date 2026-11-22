# Charset, đầu vào sai và giới hạn bộ nhớ khi làm việc với chuỗi và Base64 trong Java

> **Module:** Java 8 — **Chuỗi và Base64**. Bài trình bày cách chuyển đổi **Unicode String ↔ bytes ↔ Base64 text** đúng charset, phân biệt **dữ liệu Base64 sai cú pháp** với **bytes không hợp lệ theo charset**, chọn chính sách **REPORT/REPLACE/IGNORE**, và bảo vệ ứng dụng trước payload quá lớn bằng **kiểm tra kích thước + xử lý stream có giới hạn**. Các API trọng tâm thuộc Java 8 và còn sử dụng trong các JDK hiện hành.

## 1. Phân biệt ba tầng dữ liệu trước khi viết code

Một trong các lỗi phổ biến nhất là nghĩ rằng Base64 tự chứa thông tin Unicode. Thực tế luồng chuyển đổi là:

~~~text
Chuỗi Unicode của Java
    String
       |
       | getBytes(StandardCharsets.UTF_8)
       v
Dãy byte UTF-8
    byte[]
       |
       | Base64.getEncoder().encodeToString(bytes)
       v
Văn bản Base64 (ký tự ASCII)
    String
       |
       | Base64.getDecoder().decode(base64)
       v
Dãy byte ban đầu
    byte[]
       |
       | decode UTF-8: new String(bytes, UTF_8)
       | hoặc CharsetDecoder nếu cần kiểm tra lỗi nghiêm ngặt
       v
Chuỗi Unicode được tái tạo
    String
~~~

Ở mỗi mũi tên, API giải quyết **một bài toán riêng**:

1. **Charset:** cách ánh xạ ký tự Unicode thành bytes và ngược lại; ví dụ `UTF-8`, `US-ASCII`, `ISO-8859-1`.
2. **Base64:** cách ánh xạ **bytes bất kỳ** thành các ký tự an toàn để truyền trong giao thức văn bản, sau đó khôi phục đúng bytes.
3. **Kiểm soát tài nguyên:** giới hạn kích thước, thời gian, filesystem/network I/O, buffering và chính sách lỗi khi dữ liệu không đáng tin cậy.

**Base64 không phải charset.** Nó không thay thế UTF-8; Base64 có thể biểu diễn ảnh, ZIP, encrypted bytes hoặc text bytes. Không thể suy ra dữ liệu giải mã là String hợp lệ chỉ vì Base64 đúng cú pháp.

### 1.1. Một đường round-trip đúng

~~~java
String original = "Xin chào";

byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(utf8);

byte[] decoded = Base64.getDecoder().decode(encoded);

String restored = new String(decoded, StandardCharsets.UTF_8);

// original.equals(restored) == true.
~~~

Đây là **đoạn minh họa Java 8**, cần `import java.nio.charset.StandardCharsets;` và `import java.util.Base64;`. Nếu text chứa emoji hoặc ký tự ngoài ASCII, round-trip vẫn đúng khi bytes và charset được chọn thống nhất.

### 1.2. Mẫu sai do chuyển trực tiếp qua default charset

~~~java
// Không nên dùng ở ranh giới dữ liệu nếu charset chưa được thỏa thuận:
byte[] bytes = original.getBytes();
String restored = new String(bytes);
~~~

Hai lệnh trên dùng **default charset của môi trường**, mà giả định của code có thể thay đổi giữa phiên bản JDK, cấu hình chạy, hệ điều hành hoặc service khác. Trong Java 8, default charset chịu ảnh hưởng hệ thống. Java hiện đại có các thay đổi để ưu tiên UTF-8 trong nhiều trường hợp, nhưng vẫn nên **quy định charset tường minh khi trao đổi dữ liệu**.

**Nguyên tắc:** nếu giao thức nói UTF-8, code Java phải dùng `StandardCharsets.UTF_8` ở cả hai chiều và ở tất cả nơi liên quan, không chỉ một nơi.

## 2. Charset là gì? String trong Java thực sự chứa gì?

### 2.1. String không đồng nghĩa byte[]

`String` trong Java biểu diễn chuỗi ký tự Unicode ở mức abstraction công khai. Các API `length()` và `charAt()` làm việc theo **UTF-16 code units**. Một code point ngoài BMP (ví dụ emoji) thường cần **hai `char`** (surrogate pair).

~~~java
String symbol = "\uD83D\uDE00";

// symbol.length() == 2 (hai UTF-16 code units).
// symbol.codePointCount(0, symbol.length()) == 1.
// symbol.getBytes(StandardCharsets.UTF_8).length == 4.
~~~

Đoạn minh họa ở Java 8. Do đó:

- `String.length()` **không** là số bytes UTF-8.
- `String.length()` **không luôn** bằng số Unicode code points.
- Kích thước text khi truyền phụ thuộc charset.
- Kích thước bộ nhớ String còn phụ thuộc cách runtime/JDK biểu diễn và overhead của object; không lấy `2*length` làm dự toán bộ nhớ chính xác cho mọi JVM hiện đại.

### 2.2. UTF-8 và các charset chuẩn

`StandardCharsets` chứa các hằng số thường dùng có từ Java 7, hoàn toàn hợp lệ trong Java 8:

| Charset | Ý nghĩa | Lưu ý thực tế |
| --- | --- | --- |
| `UTF_8` | Unicode encoding dạng byte biến độ dài | Thường dùng cho JSON, API, text files |
| `US_ASCII` | Bộ ký tự ASCII 7-bit | Không mã hóa đầy đủ tiếng Việt/emoji |
| `ISO_8859_1` | Một bảng ký tự đơn byte | Không hỗ trợ Unicode đầy đủ |
| `UTF_16` | UTF-16 charset | Byte order/BOM có ý nghĩa; không mặc định là UTF-8 |
| `UTF_16BE` | UTF-16 big-endian | Cần biết rõ encoding format |
| `UTF_16LE` | UTF-16 little-endian | Cần biết rõ encoding format |

Hầu hết giao thức hiện đại sử dụng UTF-8 cho text. Nhưng việc quyết định charset phải đến từ **đặc tả giao thức hoặc metadata đáng tin**, không suy luận bằng cách đoán tên file hay áp dụng “chuẩn mới nhất” lên dữ liệu cũ.

### 2.3. Unicode, UTF-8 và Base64 không đổi nghĩa văn bản

Base64 chỉ giữ nguyên bytes. Nếu đã dùng **sai charset ở chiều encode**, Base64 vẫn có thể khôi phục **đúng các bytes sai**. Không có một bước Base64 “tự sửa” ký tự tiếng Việt hoặc emoji.

~~~text
"Xin chào"
      |
      | Sai charset -> bytes bị thay bằng '?' hoặc diễn giải lệch
      v
Bytes sai nhưng vẫn là bytes hợp lệ
      |
      | Encode Base64 hoàn toàn thành công
      v
Chuỗi Base64 có cú pháp hợp lệ nhưng không thể phục hồi text gốc
~~~

Vì vậy lỗi hiển thị `"chÃ o"` hoặc ký tự thay thế là vấn đề **charset/đọc dữ liệu**, không giải quyết chỉ bằng việc đổi `Base64.getEncoder()` sang encoder khác.

## 3. Chọn charset tường minh trong Java 8

### 3.1. Với String.getBytes

~~~java
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
~~~

Phương thức nhận `Charset` tạo byte[] theo charset đã chọn. Nếu có ký tự không mã hóa được, overload này dùng **replacement bytes** mặc định của charset; nó không tự ném `CharacterCodingException` để caller bắt.

Muốn **từ chối** thay vì thay thế khi text không thể encode, dùng `CharsetEncoder` với `CodingErrorAction.REPORT`, được trình bày ở mục 5.

### 3.2. Với new String(byte[], Charset)

~~~java
String message = new String(bytes, StandardCharsets.UTF_8);
~~~

Overload nhận `Charset` có contract **thay thế các chuỗi byte malformed/unmappable bằng replacement string mặc định**. Nó thích hợp khi dữ liệu lỗi được phép hiển thị với ký tự thay thế; **không** thích hợp nếu dữ liệu phải hoàn toàn hợp lệ và tuyệt đối không mất thông tin.

### 3.3. Với file text

Trong Java 8:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng; tránh giữ toàn bộ file nếu rất lớn.
    }
}
~~~

Đây là **đoạn minh họa**, cần import `java.io.BufferedReader`, `java.nio.file.Files`, `java.nio.file.Path` và `StandardCharsets`. `Files.newBufferedReader` nhận charset tường minh, có thể báo malformed/unmappable input qua I/O exception. Nhưng đọc một dòng quá dài vẫn có thể tiêu tốn bộ nhớ lớn; cần policy giới hạn số ký tự/dòng khi dữ liệu không đáng tin.

### 3.4. Không dựa vào String(byte[]) khi xử lý payload API

~~~java
// Phản ví dụ khi giao thức đã quy định UTF-8:
String decoded = new String(payloadBytes);
~~~

Đoạn này phụ thuộc default charset; nếu service producer và consumer không cùng charset, dữ liệu có thể lệch. Dùng `new String(payloadBytes, StandardCharsets.UTF_8)` hoặc strict decoder theo contract.

### 3.5. Charset bắt buộc phải thống nhất qua từng thành phần

Một hệ thống thường có nhiều chặng:

~~~text
HTTP client -> API Gateway -> Service -> Queue -> Consumer -> Database
~~~

Nếu một chặng dùng UTF-8 nhưng một chặng dùng ISO-8859-1 hoặc xử lý bytes như text ASCII, Base64 payload ở giữa vẫn có thể chứa bytes nguyên vẹn nhưng **String sau cùng bị diễn giải sai**. Hãy định nghĩa encoding ở giao thức và truyền metadata cần thiết một cách đáng tin cậy.

## 4. Lỗi đầu vào loại một: Base64 sai cú pháp

`java.util.Base64` có từ Java 8. Các decoder cho Basic, URL và MIME có **quy tắc chấp nhận ký tự khác nhau**.

### 4.1. Base64 Basic

~~~java
byte[] data = Base64.getDecoder().decode("SGVsbG8=");

String text = new String(data, StandardCharsets.US_ASCII);
// text.equals("Hello") == true.
~~~

Basic decoder dùng alphabet Base64 chuẩn (chữ cái, số, `+`, `/`, `=` theo quy tắc padding); nó **từ chối ký tự ngoài alphabet**, ví dụ space giữa token.

~~~java
try {
    Base64.getDecoder().decode("SGV sbG8=");
} catch (IllegalArgumentException ex) {
    // Sai cú pháp Base64 theo Basic decoder.
}
~~~

`IllegalArgumentException` biểu diễn lỗi format, **không** phải lỗi charset của bytes sau giải mã. Với API không tin cậy, nên phân loại thành lỗi input rõ ràng thay vì trả HTTP 500 chung.

### 4.2. Base64 URL-safe

URL-safe thay hai ký tự alphabet:

| Basic Base64 | URL-safe Base64 |
| --- | --- |
| `+` | `-` |
| `/` | `_` |

~~~java
byte[] data = {
        (byte) 0xFB, (byte) 0xFF, (byte) 0xEF
};

String token = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(data);

// token.equals("-__v") == true.
// Arrays.equals(data, Base64.getUrlDecoder().decode(token)) == true.
~~~

Đây là **đoạn minh họa**, cần import `java.util.Arrays`. Basic decoder **không** chấp nhận `-`/`_` của token này. Chọn đúng cặp encoder/decoder theo contract của giao thức (ví dụ một token URL-safe), không đoán từ “trông giống Base64”.

### 4.3. Base64 MIME

`Base64.getMimeDecoder()` có chủ đích **bỏ qua line separators và các ký tự không thuộc Base64 alphabet** khi giải mã theo MIME. Đây là lựa chọn đúng cho dữ liệu MIME có format tương ứng, nhưng có thể **quá khoan dung** nếu API bảo mật mong muốn Basic/URL token với cú pháp nghiêm ngặt.

~~~java
byte[] bytes = Base64.getMimeDecoder().decode("SGV sbG8=");

// new String(bytes, StandardCharsets.US_ASCII).equals("Hello") == true.
~~~

Nếu ứng dụng tự động dùng MIME decoder để “chữa” mọi token nhập sai, dữ liệu chứa ký tự bất thường có thể được chấp nhận ngoài ý muốn. **Dùng MIME chỉ khi format thực sự là MIME**, không mặc định như một bộ lọc xác thực đầu vào.

### 4.4. Padding `=` và missing padding

Theo Javadoc Java 8, decoder chấp nhận Base64 unit cuối có 2 hoặc 3 ký tự **không kèm padding** và xử lý tương tự đã được thêm dấu `=` thích hợp. Nếu đã có padding, số dấu phải hợp lệ.

~~~java
String a = new String(
        Base64.getDecoder().decode("SGVsbG8"),
        StandardCharsets.US_ASCII);

// a.equals("Hello") == true (thiếu '=' nhưng vẫn được nhận).
~~~

**Điểm dễ sai:** Không mặc định rằng `Base64.getDecoder()` “luôn từ chối chuỗi không có `=`”. Nếu giao thức đòi biểu diễn **canonical** có padding, caller có thể phải kiểm tra format **riêng** (ví dụ giải mã, mã hóa lại theo profile chuẩn rồi so sánh nguyên văn).

### 4.5. Một số dấu bằng thừa không phải lúc nào hợp lệ

`SGVsbG8=` là encoding hợp lệ cho “Hello”. Thêm `=` tùy tiện vào cuối hoặc đặt giữa token có thể làm decoder từ chối. Không viết logic “cứ bổ sung padding cho đến khi decode được” vì có thể làm mất kiểm soát format đầu vào.

### 4.6. Decode(String) và vấn đề charset

`Base64.Decoder.decode(String)` được định nghĩa tương đương việc decode bytes từ String theo `ISO_8859_1`. Nhưng ký tự Base64 Basic/URL chuẩn chỉ sử dụng ASCII. Với input text hợp lệ, đừng tưởng rằng decode(String) sẽ dùng UTF-8 rồi chuyển Unicode tùy ý.

Nếu API nhận Base64 string, kiểm tra **profile alphabet và chiều dài** trước decode theo contract của endpoint. Với stream, decoder nhận bytes và không cần dựng String trung gian.

### 4.7. Base64 không phải kiểm tra nội dung

Một chuỗi Base64 hoàn toàn hợp lệ có thể chứa:

- Bytes không phải UTF-8.
- File khác loại khai báo.
- Dữ liệu nén rất lớn sau khi giải nén.
- Nội dung đã bị thay đổi.
- Nội dung nguy hiểm khi được parser khác xử lý.

**Giải mã Base64 thành công chỉ chứng minh format Base64 hợp lệ theo decoder đã chọn**, không chứng minh nội dung an toàn, có chữ ký hợp lệ hay đáng tin.

## 5. Lỗi đầu vào loại hai: bytes không đúng charset

### 5.1. Ví dụ UTF-8 malformed

Hai bytes:

~~~text
C3 28
~~~

`0xC3` là byte mở đầu một chuỗi UTF-8 nhiều byte, nhưng `0x28` không phải continuation byte hợp lệ. Vì vậy toàn dãy không là UTF-8 hợp lệ.

~~~java
byte[] malformed = {
        (byte) 0xC3, (byte) 0x28
};

String lenient = new String(malformed, StandardCharsets.UTF_8);

// lenient có ký tự thay thế U+FFFD.
~~~

Đoạn Java 8 minh họa cho **chế độ thay thế**, không phải phát hiện lỗi nghiêm ngặt. Tùy charset và dữ liệu, một hoặc nhiều input units có thể được thay bằng replacement character.

### 5.2. CharsetDecoder REPORT: khi phải từ chối input không hợp lệ

~~~java
static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Đây là **method minh họa** cần import `ByteBuffer`, `CharacterCodingException`, `CodingErrorAction`. Các method này có trong Java 8.

Khi gặp malformed UTF-8, `decode` ném `MalformedInputException` (một loại `CharacterCodingException`). Nếu gặp input hợp lệ theo charset nhưng không ánh xạ được thành ký tự, decoder có thể ném `UnmappableCharacterException`.

### 5.3. CharsetDecoder mặc định khác String constructor

| Cách gọi | Khi bytes malformed/unmappable | Khi nên dùng |
| --- | --- | --- |
| `new String(bytes, UTF_8)` | **REPLACE** theo contract | UI hiển thị lỗi được phép thay thế |
| `StandardCharsets.UTF_8.decode(ByteBuffer)` | Convenience method **REPLACE** | Chuyển ByteBuffer khi chấp nhận thay thế |
| `UTF_8.newDecoder().decode(ByteBuffer)` | Decoder mặc định **REPORT** | Cần biết đầu vào có hợp lệ không |
| `newDecoder().onMalformedInput(REPORT)...` | **REPORT** rõ ràng | API validation nghiêm ngặt |
| `newDecoder().onMalformedInput(IGNORE)...` | Bỏ input sai | Chỉ khi nghiệp vụ chủ ý cho phép mất dữ liệu |

**Cẩn trọng:** Không phải mọi cách chuyển charset đều mặc định REPORT. `CharsetDecoder` mới tạo có default REPORT, nhưng `new String(bytes, Charset)` và `Charset.decode` convenience method đặt chính sách REPLACE.

### 5.4. CodingErrorAction: REPORT, REPLACE và IGNORE

- `REPORT`: dừng với thông tin lỗi; phù hợp kiểm tra dữ liệu phải hợp lệ.
- `REPLACE`: thay những đơn vị dữ liệu lỗi bằng replacement string/bytes; phù hợp hiển thị khoan dung khi mất dữ liệu được chấp nhận.
- `IGNORE`: bỏ đơn vị lỗi; có thể làm mất thông tin hoặc bỏ qua ký tự theo cách không mong muốn, đặc biệt nguy hiểm nếu dùng để kiểm tra security identifiers.

**Không có chính sách “luôn đúng”.** Một log viewer có thể chấp nhận REPLACE để tiếp tục hiển thị; một API nhận tên người dùng, dữ liệu tài chính hoặc nội dung ký số thường phải có validation nghiêm ngặt.

### 5.5. Mã hóa ký tự không được hỗ trợ

Không chỉ chiều **bytes → String** mới có lỗi. Chiều **String → bytes** cũng có thể gặp ký tự không tồn tại trong charset mục tiêu.

~~~java
String name = "Tiếng Việt";

byte[] replacement = name.getBytes(StandardCharsets.US_ASCII);
// Một số ký tự không thể biểu diễn bằng US-ASCII sẽ bị thay thế.
~~~

Nếu không cho phép mất dữ liệu, dùng `CharsetEncoder` với `REPORT`:

~~~java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ByteBuffer data = encoder.encode(CharBuffer.wrap(name));
} catch (CharacterCodingException ex) {
    // Từ chối nội dung không mã hóa được bằng US-ASCII.
}
~~~

Đây là **đoạn minh họa** cần `CharsetEncoder`, `CharBuffer`. Không tự động chuyển mọi chuỗi tiếng Việt sang ASCII bằng cách silently thay bằng `?` nếu dữ liệu phải round-trip toàn vẹn.

### 5.6. Không reuse CharsetDecoder giữa nhiều thread

`CharsetDecoder` và `CharsetEncoder` là stateful engines và **không thread-safe** theo hợp đồng. Với nhiều request song song, tạo decoder/encoder cho mỗi operation hoặc quản lý pooling với synchronization/reset đúng. Ngược lại, `StandardCharsets.UTF_8` là một Charset object dùng làm cấu hình, không cần mỗi request tự tạo Charset mới.

### 5.7. Java String có thể chứa surrogate không ghép hợp lệ

`String` dựa trên UTF-16 code units; về mặt kỹ thuật, code có thể tạo String với một surrogate không có cặp tương ứng. Khi encode sang UTF-8, đây là malformed character input. `getBytes(UTF_8)` có thể thay thế; `CharsetEncoder(REPORT)` phát hiện lỗi.

Đừng đồng nhất “Java String object đã tạo” với “mọi ký tự đều chắc chắn có biểu diễn Unicode scalar hợp lệ để xuất UTF-8 mà không mất dữ liệu”.

## 6. Lỗi đầu vào loại ba: đúng Base64 nhưng không đúng loại nội dung

Giả sử client gửi một field được mô tả là file PNG. Chuỗi Base64 của một PDF hoặc bytes ngẫu nhiên vẫn có thể decode thành công. Vì vậy ứng dụng cần một pipeline tách riêng:

~~~text
Base64 string / encoded byte stream
        |
        | Kiểm tra input length / alphabet
        v
Base64 decoding (giới hạn output bytes)
        |
        | Validate decoded size
        v
Chọn decoder/parser theo content contract
        |
        | MIME / magic bytes / schema / strict charset
        v
Validation nghiệp vụ
        |
        | Sau đó mới lưu trữ hoặc xử lý side effect
        v
Kết quả
~~~

**Không** dùng Base64 làm bằng chứng file không có malware, không có payload parser, hay đã được xác thực. Base64 cũng **không mã hóa bảo mật**: ai có token đều có thể giải mã bytes nếu không có biện pháp bảo mật riêng.

### 6.1. Text field thì cần validate text

Nếu endpoint quy định “payload là UTF-8 text”:

1. Decode Base64 theo profile.
2. Áp dụng **giới hạn decoded bytes**.
3. Decode UTF-8 bằng `CharsetDecoder(REPORT)` nếu yêu cầu tuyệt đối đúng.
4. Kiểm tra độ dài và cấu trúc **String** theo business schema.
5. Chỉ sau đó chuyển tiếp tới logic ứng dụng.

### 6.2. File upload thì không mặc định decode thành String

Ảnh, ZIP, PDF và dữ liệu mã hóa nên được xử lý như **bytes**; không nên dùng:

~~~java
// PHẢN VÍ DỤ cho binary file:
String fileText = new String(
        Base64.getDecoder().decode(base64),
        StandardCharsets.UTF_8);
~~~

Lệnh trên có thể thay thế byte sequences malformed bằng Unicode replacement, sau đó re-encode sẽ **làm đổi nội dung binary**. Với file upload, stream bytes ra vùng tạm có size limit, sau đó phân tích file type và kiểm tra an toàn bằng công cụ phù hợp.

### 6.3. Content-Type không phải bằng chứng an toàn

Header `Content-Type: image/png` hoặc tên `photo.png` do client khai báo có thể sai. Sau Base64 decode, cần validate file signature/parser theo security policy; không chỉ dựa vào extension hoặc Content-Type.

### 6.4. Canonicalization không thay thế authentication

Một hệ thống cần token Base64 chuẩn có thể so sánh `reEncode(decode(input))` với input theo chính sách padding/alphabet. Nhưng **token canonical không chứng minh token do hệ thống đáng tin phát hành**. Cần chữ ký số, MAC hoặc cơ chế authentication phù hợp.

## 7. Giới hạn bộ nhớ: tại sao một String Base64 lớn có thể gây OOM?

### 7.1. Base64 làm tăng kích thước biểu diễn

Với `n` bytes, Basic Base64 có padding và không xuống dòng thường tạo số ký tự:

~~~text
encodedLength = 4 * ceil(n / 3)
~~~

Ví dụ:

~~~text
Raw binary size: 10 MiB = 10,485,760 bytes
Base64 Basic characters (with padding): 13,981,016
Tăng xấp xỉ 33% về lượng ký tự truyền tải
~~~

Số này **chưa kể JSON quotes, metadata, String/object overhead, arrays, wire framing hoặc lưu trữ**. MIME Base64 còn có thể thêm separators.

### 7.2. Array allocations xuất hiện ở từng chặng

Một implementation dễ viết:

~~~java
String encoded = obtainHugeString();
byte[] raw = Base64.getDecoder().decode(encoded);
String text = new String(raw, StandardCharsets.UTF_8);
~~~

Đoạn này là **phản ví dụ về memory safety**, với `obtainHugeString()` chỉ là tên giả. Nó có thể giữ đồng thời:

- String Base64 rất lớn.
- Temporary representation/byte[] dùng bởi decode.
- Byte[] decoded lớn.
- String mới từ bytes, có thể có internal storage thêm.
- Các copies khác do JSON parser, HTTP stack hoặc application.

**Không lấy công thức `4*ceil(n/3)` làm ước lượng bộ nhớ heap chính xác.** Nó chỉ là số ký tự Base64, không phải total live heap. Với payload lớn, các copies liên tiếp có thể làm tiêu tốn nhiều lần raw payload size.

### 7.3. Bộ nhớ không chỉ tăng vì Base64

Nếu bạn giải nén archive hoặc decode ảnh sau Base64, kích thước sau bước kế tiếp có thể lớn hơn rất nhiều. Giới hạn decoded Base64 bytes **chưa đủ** để ngăn một file nén nhỏ mở ra nhiều GB hoặc ảnh có dimensions quá lớn.

Áp dụng các ngân sách riêng:

- Input encoded size.
- Decoded byte size.
- Decompressed/parsed logical size.
- Per-record/line size.
- CPU time, recursion/depth, count.
- Concurrent requests và tổng memory budget của service.

## 8. Đặt giới hạn trước và trong quá trình decode

### 8.1. Kiểm tra độ dài encoded input trước cấp phát lớn

Nếu endpoint nhận String Base64, kiểm tra `input.length()` **ngay khi có String** để từ chối rõ ràng payload vượt policy. Nhưng lưu ý: khi `String` đã được tạo từ một HTTP/JSON body không giới hạn, ứng dụng **đã trả giá bộ nhớ trước khi tới kiểm tra**.

Cần đặt request/body-size limit tại HTTP server, gateway hoặc streaming parser **trước** bước load toàn bộ thành String.

### 8.2. Giới hạn decoded bytes trước xử lý nghiệp vụ

Một ví dụ giới hạn 16 bytes sau decode:

~~~java
if (raw.length > 16) {
    throw new IllegalArgumentException("decoded data exceeds limit");
}
~~~

Điểm yếu: nếu `raw` đã là một byte[] 2 GB, kiểm tra `raw.length` quá muộn để bảo vệ allocation. Chọn decoder streaming và **dừng khi vượt giới hạn**, như chương trình Java 8 runnable ở mục 12.

### 8.3. Ước lượng kích thước để reject sớm

Với Basic Base64 có padding đúng profile, lượng decoded bytes thường xấp xỉ `3/4` độ dài encoded. Có thể dùng upper bound thận trọng như:

~~~text
max decoded bytes <= 3 * ceil(encodedChars / 4)
~~~

Khi tính với giá trị không tin cậy:

- Dùng `long` thay vì phép nhân `int` dễ tràn.
- Tránh `encodedChars + 3` nếu có nguy cơ vượt miền số.
- Nếu MIME cho phép bỏ qua nhiều ký tự, encoded input có thể dài hơn rất nhiều mà decoded output vẫn nhỏ.
- Nếu input có padding hoặc thiếu padding được decoder chấp nhận, kích thước thật phụ thuộc số ký tự hợp lệ cuối.
- Dù đã ước lượng, **vẫn cần kiểm tra giới hạn trong khi stream decode**, không dựa hoàn toàn vào công thức.

### 8.4. Giới hạn encoded input và decoded output đều cần thiết

Nếu chỉ giới hạn output bytes nhưng cho phép sender gửi chuỗi Base64 rất dài chỉ chứa kí tự bị MIME decoder bỏ qua, CPU/traffic vẫn có thể lớn. Nếu chỉ giới hạn encoded input nhưng sau đó giải nén dữ liệu, memory có thể nổ ở bước decompression.

Một policy hoàn chỉnh cần cân đối cả **encoded**, **decoded**, **decompressed** và số request đồng thời. Với endpoint gửi file, ưu tiên cấu hình max request body size ở tầng nhận.

### 8.5. Không dùng Base64.encodeToString cho file quá lớn

`Base64.getEncoder().encodeToString(bigArray)` cần một byte[] nguồn và một String đầu ra. Nếu nguồn là file nhiều GB, đọc hết file vào RAM rồi encode là không hợp lý. Dùng stream wrapper ghi ra file/socket/pipeline với giới hạn và backpressure thích hợp.

### 8.6. Kiểm soát thời gian và hủy tác vụ

Ngay cả khi output dưới limit, một stream từ nguồn chậm vô hạn có thể giữ request thread quá lâu. Cần thiết kế timeout, request cancellation, bounded worker pools và giới hạn I/O ở tầng transport/storage. `Base64.Decoder.wrap(InputStream)` không tự đặt deadline network cho bạn.

## 9. Base64 streaming trong Java 8

### 9.1. Encoder.wrap(OutputStream)

~~~java
try (InputStream source = Files.newInputStream(inputPath);
     OutputStream fileOutput = Files.newOutputStream(encodedPath);
     OutputStream base64Output =
             Base64.getEncoder().wrap(fileOutput)) {

    byte[] buffer = new byte[8192];
    int count;
    while ((count = source.read(buffer)) != -1) {
        base64Output.write(buffer, 0, count);
    }
}
~~~

Đây là **đoạn minh họa** với paths có sẵn. `Base64.Encoder.wrap(OutputStream)` trả một output stream nhận bytes thô và ghi bytes Base64 sang destination. **Đóng wrapper** là cần thiết để flush các bytes còn lại của nhóm cuối và hoàn tất padding theo profile. `close()` của wrapper cũng đóng output stream nằm dưới.

**Không** chỉ gọi `flush()` rồi nghĩ block cuối đã chắc được xuất ra: một encoder đang giữ 1–2 bytes để hoàn thành nhóm Base64 cần `close` khi kết thúc.

### 9.2. Decoder.wrap(InputStream)

~~~java
try (InputStream encoded = Files.newInputStream(encodedPath);
     InputStream decoded =
             Base64.getDecoder().wrap(encoded);
     OutputStream output = Files.newOutputStream(decodedPath)) {

    byte[] buffer = new byte[8192];
    int count;
    while ((count = decoded.read(buffer)) != -1) {
        output.write(buffer, 0, count);
    }
}
~~~

Đây là **đoạn minh họa**, không thực hiện size limit; với dữ liệu untrusted, thêm bộ đếm `long total` và kiểm tra trước mỗi `output.write`. `Decoder.wrap` có thể báo bytes Base64 lỗi bằng `IOException` khi đọc.

### 9.3. Đóng wrapper ảnh hưởng stream phía dưới

Encoder wrapper đóng output stream gốc; decoder wrapper đóng input stream gốc. Nếu caller vẫn cần dùng underlying stream sau đó, phải thiết kế ownership hoặc wrapper không tự đóng phù hợp, không tùy tiện close chồng nhau trong pipeline dùng chung.

### 9.4. Không cắt Base64 chunks rồi decode riêng tùy ý

Base64 encode nhóm mỗi 3 bytes thành 4 ký tự; một đoạn input cắt ngang nhóm có thể chứa sequence chưa đủ và tạo kết quả sai khi decode riêng.

**Đúng:** dùng một stream encoder/decoder xuyên suốt toàn bộ payload để giữ trạng thái nhóm giữa các lần đọc buffer. Nếu giao thức chủ đích chia thành nhiều thông điệp Base64 độc lập, mỗi chunk phải có ranh giới encoder riêng và contract riêng.

### 9.5. Không coi Base64 Decoder stream là parser text

`Base64.getDecoder().wrap(encodedInput)` trả **decoded bytes**, không trả Unicode chars. Nếu payload là text UTF-8, bên trên có thể dùng `InputStreamReader` với `CharsetDecoder(REPORT)` để xử lý ký tự, kèm giới hạn bytes/chars.

Ví dụ:

~~~java
CharsetDecoder strictUtf8 =
        StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

try (InputStream encoded = Files.newInputStream(path);
     InputStream decoded = Base64.getDecoder().wrap(encoded);
     Reader text = new InputStreamReader(decoded, strictUtf8);
     BufferedReader reader = new BufferedReader(text)) {
    // Đọc nội dung text, kiểm soát size/dòng theo contract.
}
~~~

Đây là **đoạn minh họa**; cần import `Reader`, `InputStreamReader`, `BufferedReader`, `CharsetDecoder`, `CodingErrorAction`. Một `Reader` có thể đã buffer dữ liệu khi kiểm tra characters; do đó vẫn cần **giới hạn bytes ở trước** nếu payload không đáng tin.

## 10. Bounded streaming decoder: mẫu an toàn hơn cho đầu vào

Một helper đơn giản có thể trả byte[] **chỉ khi decoded output không vượt mức được cấp**:

~~~java
static byte[] decodeWithLimit(InputStream encoded, long maxBytes)
        throws IOException {
    if (maxBytes < 0L) {
        throw new IllegalArgumentException("negative byte limit");
    }
    try (InputStream decoded = Base64.getDecoder().wrap(encoded);
         ByteArrayOutputStream output = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[1024];
        long total = 0L;
        int count;
        while ((count = decoded.read(buffer)) != -1) {
            total += count;
            if (total > maxBytes) {
                throw new IOException("decoded payload exceeds limit");
            }
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }
}
~~~

Đây là **method minh họa** và nằm trong chương trình hoàn chỉnh ở mục 12. Nó đặt giới hạn ngay trong lúc đọc decoded bytes, trước khi viết chunk mới vào output.

### 10.1. Mẫu này bảo vệ điều gì?

- Mỗi vòng lặp chỉ đọc tối đa 1.024 decoded bytes.
- Tổng `total` tính bằng `long`, được so với `maxBytes`.
- Nếu vượt hạn mức, ném `IOException` và đóng stream.
- Dùng `try-with-resources` để giải phóng wrapper.
- Nếu thành công, trả byte[] chứa nội dung với độ dài không vượt policy.

### 10.2. Mẫu này chưa giải quyết điều gì?

- Nó dùng `ByteArrayOutputStream`, nên **vẫn giữ decoded bytes trong memory**, nhưng được giới hạn bởi `maxBytes`; phù hợp **payload nhỏ/vừa** chứ không thay thế file streaming.
- Nó **chưa giới hạn tổng encoded bytes** mà input stream tiêu thụ. Tầng HTTP/server phải đặt limit hoặc dùng bounded source wrapper.
- Nó **chưa giải nén** nội dung. Với ZIP/GZIP, còn cần giới hạn sau giải nén.
- Nó không phân biệt file text hay binary: kết quả là byte[].
- Nó không tự xác thực dữ liệu, virus scan, signature, schema hoặc content type.
- `maxBytes` quá lớn so với heap vẫn nguy hiểm. Limit phải tính theo memory budget thực tế và số requests đồng thời.
- `ByteArrayOutputStream.toByteArray()` thường tạo một bản sao của dữ liệu để trả ra; phép copy cũng cần được tính vào memory plan.

### 10.3. Khi payload lớn, không tạo byte[] kết quả

Nếu raw payload cho phép tới nhiều GB, tốt hơn là stream tới file tạm có quota:

~~~java
long total = 0L;
try (InputStream source = obtainBoundedEncodedStream();
     InputStream decoded = Base64.getDecoder().wrap(source);
     OutputStream target = Files.newOutputStream(tempPath)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = decoded.read(buffer)) != -1) {
        total += n;
        if (total > maxDecodedBytes) {
            throw new IOException("decoded payload too large");
        }
        target.write(buffer, 0, n);
    }
}
~~~

Đây là **đoạn minh họa**, `obtainBoundedEncodedStream()`, `tempPath`, `maxDecodedBytes` do ứng dụng cung cấp. Code production còn phải xử lý dọn file tạm **nếu đang ghi mà ném exception**, giới hạn số file đồng thời, atomic publish/rename nếu phù hợp và xác thực nội dung trước khi công bố.

### 10.4. Định nghĩa hợp đồng khi vượt hạn mức

Với API, một kết quả hợp lý khi body quá lớn là trả lỗi request size theo tầng HTTP hoặc business error có mã rõ, **không tiếp tục giải mã**. Không chuyển `IOException` do size limit thành một “String rỗng” rồi cho nghiệp vụ xử lý như dữ liệu hợp lệ.

### 10.5. Đặt tối đa số requests đồng thời

Giới hạn 10 MiB cho mỗi request **không tự** bảo đảm service an toàn nếu 1.000 requests cùng lúc giữ payload 10 MiB và nhiều bản sao. Hãy tính tổng memory concurrency budget, sử dụng queue/backpressure và streaming khi cần.

## 11. Kiểm tra tính toàn vẹn và nội dung sau khi decode

### 11.1. Base64 không có integrity check

Nếu một ký tự trong chuỗi Base64 thay đổi nhưng vẫn thuộc alphabet hợp lệ, decoder có thể trả **bytes khác** mà không ném exception. Do đó Base64 không phải checksum, MAC hoặc digital signature.

Với dữ liệu cần integrity:

- Xác định checksum/hash nếu chỉ cần phát hiện lỗi truyền không mang yếu tố đối kháng.
- Dùng MAC/chữ ký được thiết kế đúng nếu cần chống giả mạo.
- Dùng TLS bảo vệ kênh truyền; dữ liệu lưu lâu có thể cần thêm bảo vệ at-rest.
- Không tự thiết kế thuật toán mật mã từ Base64.

### 11.2. MIME decoder quá khoan dung có thể che lỗi

Ví dụ Basic decoder bác bỏ whitespace, còn MIME decoder bỏ qua nó. Nếu endpoint token định nghĩa alphabet chặt chẽ, một attacker có thể thêm những ký tự bị bỏ qua mà ứng dụng vẫn coi token hợp lệ nếu dùng MIME. Đây là vấn đề **parser inconsistency** khi các hệ thống cùng xử lý token theo những quy tắc khác nhau.

### 11.3. Strict charset decode không chứng minh nội dung hợp lệ về ngữ nghĩa

Dữ liệu UTF-8 có thể well-formed nhưng vẫn chứa:

- Control characters không được endpoint cho phép.
- String không thỏa regex/schema.
- HTML/SQL đặc biệt cần escape/sanitize đúng context.
- Unicode confusables hoặc các dạng normalization khác nhau.

**Đúng UTF-8 chỉ là điều kiện encoding**; validation nội dung cần chính sách riêng. Không tự dùng `String.trim()` hay lowercasing làm biện pháp security chung.

### 11.4. Unicode normalization là bước riêng

Hai chuỗi có thể hiển thị gần giống nhưng được biểu diễn bằng code points khác nhau. Nếu nghiệp vụ cần chuẩn hóa, cân nhắc `java.text.Normalizer` (ví dụ `Normalizer.Form.NFC`). **Base64 và charset decoder không mặc định thay thế bước normalization đó**. Với identifier an toàn, phải có policy chống spoofing đúng hơn chỉ NFC.

### 11.5. BOM và tiền tố dữ liệu

Một file có UTF-8 BOM sẽ có ba bytes `EF BB BF` đầu tiên. Không mặc định mọi parser Java tự xóa BOM giống nhau. Hãy xác định protocol có cho BOM hay không, và nếu cho thì xử lý chủ động ở boundary trước khi parse schema nếu cần.

Với data URI, một String như `data:image/png;base64,...` **không phải token Base64 thuần**; phải parse và validate scheme/media type/prefix rồi mới đưa phần payload qua decoder. Không chỉ `replaceAll("data:.*base64,","")` bừa bãi trên input không tin cậy.

## 12. Chương trình Java 8 hoàn chỉnh: charset, input lỗi và byte limit

Chương trình sau tự kiểm thử:

1. Round-trip chuỗi có tiếng Việt và emoji qua UTF-8 + Base64.
2. Byte length khác UTF-16 code-unit count.
3. Dùng sai charset làm text khác gốc.
4. `new String(bytes, UTF_8)` dùng replacement với input UTF-8 malformed.
5. Strict `CharsetDecoder` bác bỏ malformed bytes.
6. Strict ASCII `CharsetEncoder` bác bỏ text Unicode không biểu diễn được.
7. Basic Base64 bác bỏ whitespace; MIME decoder chấp nhận theo profile.
8. Java decoder chấp nhận một dạng Base64 thiếu padding hợp lệ.
9. URL alphabet khác Basic và cần decoder tương ứng.
10. Encoder stream chỉ hoàn tất block cuối khi đóng.
11. Decode stream có limit 5 bytes hoạt động; vượt 16 bytes bị chặn.
12. Công thức kích thước Base64 của 10 MiB raw.

Lưu toàn bộ thành **CharsetBase64LimitsDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

public final class CharsetBase64LimitsDemo {
    private static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    private static byte[] decodeWithLimit(InputStream encoded, long maxBytes)
            throws IOException {
        if (maxBytes < 0L) {
            throw new IllegalArgumentException("negative byte limit");
        }
        try (InputStream decoded = Base64.getDecoder().wrap(encoded);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[1024];
            long total = 0L;
            int count;
            while ((count = decoded.read(buffer)) != -1) {
                total += count;
                if (total > maxBytes) {
                    throw new IOException("decoded payload exceeds limit");
                }
                output.write(buffer, 0, count);
            }
            return output.toByteArray();
        }
    }

    public static void main(String[] args) throws Exception {
        String original = "Xin ch\u00E0o \uD83D\uDE00";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String base64 = Base64.getEncoder().encodeToString(utf8);
        byte[] decoded = Base64.getDecoder().decode(base64);
        System.out.println("utf8 round trip = "
                + original.equals(decodeUtf8Strict(decoded)));
        System.out.println("utf8 bytes exceed UTF16 units = "
                + (utf8.length > original.length()));
        System.out.println("wrong charset changes text = "
                + !original.equals(new String(utf8,
                        StandardCharsets.ISO_8859_1)));

        byte[] malformed = { (byte) 0xC3, (byte) 0x28 };
        String lenient = new String(malformed, StandardCharsets.UTF_8);
        System.out.println("lenient replacement = "
                + (lenient.indexOf('\uFFFD') >= 0));
        try {
            decodeUtf8Strict(malformed);
            System.out.println("strict UTF8 rejects malformed = false");
        } catch (CharacterCodingException expected) {
            System.out.println("strict UTF8 rejects malformed = true");
        }

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(original));
            System.out.println("strict ASCII rejects Unicode = false");
        } catch (CharacterCodingException expected) {
            System.out.println("strict ASCII rejects Unicode = true");
        }

        String withWhitespace = "SGV sbG8=";
        try {
            Base64.getDecoder().decode(withWhitespace);
            System.out.println("basic Base64 rejects whitespace = false");
        } catch (IllegalArgumentException expected) {
            System.out.println("basic Base64 rejects whitespace = true");
        }
        System.out.println("MIME ignores whitespace = "
                + "Hello".equals(new String(
                        Base64.getMimeDecoder().decode(withWhitespace),
                        StandardCharsets.US_ASCII)));
        System.out.println("missing Base64 padding accepted = "
                + "Hello".equals(new String(
                        Base64.getDecoder().decode("SGVsbG8"),
                        StandardCharsets.US_ASCII)));

        byte[] rawBinary = {(byte) 0xFB, (byte) 0xFF, (byte) 0xEF};
        String urlToken = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(rawBinary);
        System.out.println("URL alphabet token = " + urlToken);
        System.out.println("URL round trip = "
                + Arrays.equals(rawBinary,
                        Base64.getUrlDecoder().decode(urlToken)));
        try {
            Base64.getDecoder().decode(urlToken);
            System.out.println("basic decoder rejects URL token = false");
        } catch (IllegalArgumentException expected) {
            System.out.println("basic decoder rejects URL token = true");
        }

        ByteArrayOutputStream encodedOutput = new ByteArrayOutputStream();
        try (OutputStream wrapping =
                     Base64.getEncoder().wrap(encodedOutput)) {
            wrapping.write("Hello".getBytes(StandardCharsets.US_ASCII));
        }
        System.out.println("stream encoder closed = "
                + "SGVsbG8=".equals(encodedOutput.toString("US-ASCII")));
        byte[] small = decodeWithLimit(new ByteArrayInputStream(
                encodedOutput.toByteArray()), 5L);
        System.out.println("bounded decode = "
                + "Hello".equals(new String(small,
                        StandardCharsets.US_ASCII)));
        byte[] tooLarge = new byte[17];
        byte[] encodedLarge = Base64.getEncoder().encode(tooLarge);
        try {
            decodeWithLimit(new ByteArrayInputStream(encodedLarge), 16L);
            System.out.println("decoded size limit enforced = false");
        } catch (IOException expected) {
            System.out.println("decoded size limit enforced = true");
        }

        long rawLength = 10L * 1024L * 1024L;
        long encodedLength = 4L * ((rawLength + 2L) / 3L);
        System.out.println("10MiB encoded chars = " + encodedLength);
    }
}
~~~

Biên dịch với JDK có hỗ trợ target Java 8:

~~~bash
javac --release 8 CharsetBase64LimitsDemo.java
java CharsetBase64LimitsDemo
~~~

Trên JDK 8, dùng `javac CharsetBase64LimitsDemo.java`. Mã nguồn chỉ sử dụng APIs có trong Java 8. Nếu chạy trên một JDK mới, compiler có thể cảnh báo target 8 đã cũ; bản thân các API minh họa vẫn được hỗ trợ.

**Stdout được chạy xác minh:**

~~~text
utf8 round trip = true
utf8 bytes exceed UTF16 units = true
wrong charset changes text = true
lenient replacement = true
strict UTF8 rejects malformed = true
strict ASCII rejects Unicode = true
basic Base64 rejects whitespace = true
MIME ignores whitespace = true
missing Base64 padding accepted = true
URL alphabet token = -__v
URL round trip = true
basic decoder rejects URL token = true
stream encoder closed = true
bounded decode = true
decoded size limit enforced = true
10MiB encoded chars = 13981016
~~~

### 12.1. Giải thích kết quả UTF-8

`original` chứa tiếng Việt và một emoji thông qua Unicode escapes, để source code có thể lưu dưới ASCII mà vẫn biên dịch/chạy được. `String.length()` đếm UTF-16 units, còn UTF-8 encode tạo số bytes khác. Khi dùng UTF-8 ở cả hai chiều và Base64 chỉ làm bước chuyển bytes, round-trip true.

Nếu dùng `ISO_8859_1` để giải mã các bytes UTF-8 của original, mỗi byte được ánh xạ khác và String tạo ra không bằng bản gốc; chương trình in `wrong charset changes text = true`.

### 12.2. Giải thích malformed bytes

Dãy `C3 28` không phải UTF-8 hợp lệ. Constructor `new String(malformed, UTF_8)` dùng replacement, nên kết quả có U+FFFD. Strict decoder với REPORT ném `CharacterCodingException`, chương trình in true khi bắt exception. Cách xử lý nào đúng phụ thuộc đặc tả dữ liệu nhập.

### 12.3. Giải thích ASCII encoder

Một text có tiếng Việt/emoji không thể được mã hóa đầy đủ bằng ASCII. Encoder với `REPORT` từ chối thay vì thay các ký tự không biểu diễn được, nên in `strict ASCII rejects Unicode = true`.

### 12.4. Giải thích các Base64 variants

`"SGV sbG8="` có space nên Basic decoder từ chối, còn MIME decoder bỏ qua space và khôi phục “Hello”. `"SGVsbG8"` thiếu padding nhưng hợp lệ theo decoder Java 8 nên cũng tạo “Hello”.

Ba bytes `FB FF EF` cho URL-safe token `-__v`. `Base64.getUrlDecoder` khôi phục đúng bytes; Basic decoder bác token này do chứa dấu `-`/`_`.

### 12.5. Vì sao đóng encoder stream?

`Base64.getEncoder().wrap` có thể giữ bytes chưa đủ nhóm 3. Khi wrapper được đóng, nó phát output còn lại và padding; “Hello” được encode đúng thành `SGVsbG8=`. Nếu chỉ flush thay vì close ở cuối payload, code có thể không hoàn tất block cuối.

### 12.6. Giới hạn decoded bytes

`decodeWithLimit(...,5L)` chấp nhận “Hello” đúng 5 bytes. Khi decoder xử lý 17 bytes nhưng policy chỉ cho 16, helper ném IOException. Nó dừng khi vượt limit, thay vì tạo một byte[] 17 bytes ở **đầu ra helper**, dù bản thân test đã tạo dữ liệu 17 bytes trong memory để làm fixture.

### 12.7. Base64 tăng size

10 MiB = 10.485.760 raw bytes. `4 * ((n+2)/3)` với số học long cho `13.981.016` ký tự Base64 Basic có padding. Trong một HTTP JSON request, tổng memory/network footprint còn có metadata, quotes, parsing copies và concurrency overhead.

## 13. Những lỗi phổ biến và cách khắc phục

### Lỗi 1 — Nghĩ Base64 mã hóa ký tự

Base64 chuyển **bytes ↔ ký tự Base64**, không biết text charset. **Sửa:** chọn UTF-8 trước khi encode String và sau khi decode bytes.

### Lỗi 2 — Dùng default charset khi hệ thống trao đổi dữ liệu

`getBytes()` và `new String(bytes)` không ghi rõ charset. **Sửa:** truyền `StandardCharsets.UTF_8` hoặc charset đã quy định.

### Lỗi 3 — Dùng new String(decodedBase64,UTF_8) cho ảnh/ZIP

Binary có thể chứa bytes không hợp lệ UTF-8 và bị thay thế. **Sửa:** giữ binary bytes để parser/file writer xử lý.

### Lỗi 4 — Nghĩ Base64 hợp lệ là UTF-8 hợp lệ

Không đúng. **Sửa:** kiểm tra strict UTF-8 riêng nếu content contract nói text UTF-8.

### Lỗi 5 — Nghĩ new String(bytes,Charset) tự ném lỗi malformed

Nó dùng replacement theo contract. **Sửa:** dùng `CharsetDecoder(REPORT)` khi phải reject.

### Lỗi 6 — Dùng REPLACE trong validation bảo mật

Input lỗi có thể biến thành ký tự replacement và đi qua quy tắc không mong đợi. **Sửa:** reject bytes malformed/unmappable trước bước validation domain.

### Lỗi 7 — Dùng IGNORE để “sửa” input sai

Bỏ bytes có thể làm text biến đổi và va chạm identity. **Sửa:** chỉ IGNORE khi business thực sự cho phép mất dữ liệu.

### Lỗi 8 — Mã hóa Unicode sang ASCII rồi nghĩ round-trip đúng

ASCII không biểu diễn tiếng Việt/emoji. **Sửa:** dùng UTF-8 hoặc strict CharsetEncoder nếu charset bị cố định.

### Lỗi 9 — Dùng chung CharsetDecoder instance giữa threads

Decoder là stateful và không thread-safe. **Sửa:** tạo per-operation hoặc đồng bộ/pooling đúng.

### Lỗi 10 — Dùng Base64 MIME decoder cho token yêu cầu cú pháp chặt

MIME bỏ qua ký tự không thuộc alphabet, có thể làm input sai vẫn được nhận. **Sửa:** dùng Basic/URL decoder phù hợp và thêm canonical validation khi cần.

### Lỗi 11 — Nghĩ Basic decoder luôn yêu cầu padding

Java decoder cho phép một số unit cuối thiếu padding. **Sửa:** nếu contract đòi canonical padding, kiểm tra riêng.

### Lỗi 12 — Dùng URL token với Basic decoder

`-` và `_` khác `+`/`/`. **Sửa:** ghép đúng encoder/decoder variant.

### Lỗi 13 — Nhầm lỗi Base64 với lỗi charset

Base64 sai ném IllegalArgumentException; bytes hợp lệ Base64 có thể không decode được UTF-8 strict. **Sửa:** phân tầng lỗi và log đúng boundary.

### Lỗi 14 — Dùng Base64 như encryption

Ai có token có thể decode. **Sửa:** TLS, encryption, authentication/MAC/chữ ký nếu cần bảo mật.

### Lỗi 15 — Tin token hợp lệ chứng minh file thuộc Content-Type khai báo

Client có thể khai báo sai. **Sửa:** validate file signature/schema/parser sau decode.

### Lỗi 16 — Không giới hạn HTTP request body trước khi tạo String

Khi kiểm tra `String.length()`, memory đã bị dùng. **Sửa:** cấu hình max body tại transport/gateway.

### Lỗi 17 — Kiểm tra raw.length sau khi decode một payload khổng lồ

Allocation đã xảy ra. **Sửa:** streaming decode, giới hạn trong vòng lặp, reject sớm.

### Lỗi 18 — Chỉ giới hạn decoded bytes, không giới hạn encoded bytes

MIME có thể bỏ qua nhiều ký tự; CPU và network vẫn bị tiêu tốn. **Sửa:** đặt cả hai limits ở các tầng đúng.

### Lỗi 19 — Giới hạn Base64 bytes nhưng không giới hạn giải nén

Một archive nhỏ có thể phình rất lớn. **Sửa:** giới hạn decompressed size/entry count/depth.

### Lỗi 20 — Đo memory bằng encodedLength * 1 rồi kết luận heap đủ

String, arrays, copies, parser và object overhead khác nhau. **Sửa:** benchmark memory trên runtime thực và concurrency budget.

### Lỗi 21 — Không đóng Base64 encoder stream

Phần 1–2 bytes cuối có thể chưa được emit/pad. **Sửa:** close wrapper ở cuối payload.

### Lỗi 22 — Không đóng decoder InputStream

Leak resources từ underlying stream. **Sửa:** try-with-resources và ownership rõ ràng.

### Lỗi 23 — Tự encode/decode từng arbitrary chunk

Nhóm Base64 là 3 bytes ↔ 4 chars; cắt giữa nhóm có thể làm sai. **Sửa:** giữ một stream encoder/decoder xuyên suốt.

### Lỗi 24 — Dùng ByteArrayOutputStream rồi gọi đó là hoàn toàn không tốn RAM

ByteArrayOutputStream vẫn lưu bytes trong heap. **Sửa:** dùng bounded in-memory cho payload nhỏ, stream-to-file cho payload lớn.

### Lỗi 25 — Dùng `InputStreamReader` nhưng không giới hạn decoded bytes

Reader có thể buffer và tiêu tốn tài nguyên. **Sửa:** áp giới hạn bytes ở tầng decoded stream trước khi decode charset.

### Lỗi 26 — Dựa vào UTF-8 decode để tự normalize Unicode

Decoder ánh xạ bytes thành code points, không mặc định áp chuẩn NFC. **Sửa:** định nghĩa normalization/identifier policy riêng nếu cần.

### Lỗi 27 — Nghĩ Base64 có integrity check

Một token khác vẫn có thể decode. **Sửa:** dùng checksum/MAC/chữ ký theo mục tiêu.

### Lỗi 28 — Nuốt mọi CharacterCodingException rồi trả String rỗng

Điều đó biến input sai thành dữ liệu hợp lệ trống. **Sửa:** phân loại lỗi input và dừng xử lý domain.

### Lỗi 29 — Dùng int cho mọi phép ước lượng kích thước

Phép nhân có thể overflow. **Sửa:** dùng long và kiểm tra ngưỡng với arithmetic an toàn.

### Lỗi 30 — Không giới hạn concurrency

Mỗi request được phép 10 MiB nhưng 1.000 requests cùng lúc có thể dùng quá RAM. **Sửa:** backpressure/bounded concurrency và resource budget.

### Lỗi 31 — Dùng charset không đúng để đưa String Base64 vào bytes

Alphabet Base64 hợp lệ là ASCII. **Sửa:** với token text, dùng String decoder đúng profile hoặc US_ASCII sau validation, không phụ thuộc platform default.

### Lỗi 32 — Dùng `Base64.getMimeDecoder()` để giải “mọi input hơi bẩn”

Việc bỏ qua random chars có thể che dữ liệu bị sửa. **Sửa:** dùng MIME chỉ khi giao thức là MIME.

### Lỗi 33 — Không xử lý temporary file khi decode thất bại

Một upload quá lớn/invalid có thể để lại file rác. **Sửa:** xóa/quarantine trong catch/finally và chỉ atomic publish khi validation thành công.

### Lỗi 34 — Tin Base64 encoded size là decoded size

Base64 thường lớn hơn raw khoảng 33%; nếu chọn limit sai chiều, có thể reject/chấp nhận không đúng. **Sửa:** đặt limits với đơn vị và giai đoạn rõ ràng.

### Lỗi 35 — Dùng String.length làm số Unicode code points

Emoji có thể dùng surrogate pair. **Sửa:** nếu cần đếm code points, dùng `codePointCount`; nếu cần bytes, encode đúng charset rồi kiểm tra bytes với limit phù hợp.

## 14. Checklist thiết kế endpoint nhận Base64

| Câu hỏi | Gợi ý đúng |
| --- | --- |
| Đầu vào là binary hay UTF-8 text? | Xác định trước khi decode thành String |
| Giao thức yêu cầu Basic, URL hay MIME? | Chọn đúng decoder |
| Có yêu cầu padding/canonical form? | Kiểm tra riêng, đừng dựa vào decoder mặc định |
| Request body tối đa bao nhiêu? | Giới hạn trước khi parse JSON/String |
| Encoded Base64 tối đa bao nhiêu? | Giới hạn ký tự/bytes theo transport |
| Decoded payload tối đa bao nhiêu? | Bounded streaming |
| Có giải nén sau decode không? | Giới hạn decompressed bytes/entry count |
| Cần UTF-8 well-formed không? | `CharsetDecoder(REPORT)` |
| Có được thay ký tự lỗi không? | Policy REPLACE rõ ràng |
| Có được bỏ bytes sai không? | Chỉ IGNORE khi nghiệp vụ cho phép |
| Có Unicode normalization? | Định nghĩa riêng |
| Có binary file type validation? | Kiểm tra parser/magic bytes |
| Có checksum/signature/authentication? | Đặt đúng tầng security |
| Có data URI prefix? | Parse prefix an toàn trước decode |
| Có tạo temp file? | Cleanup và atomic publish |
| Có nguy cơ giữ bytes nhiều lần? | Đo heap/allocation trên workload thật |
| Có nhiều requests đồng thời? | Concurrency/backpressure budget |
| Có timeout/network cancellation? | Áp ở transport/worker layer |
| Có logged input nhạy cảm? | Không log nguyên token/payload |
| Có cần phân loại lỗi? | Lỗi syntax vs charset vs size vs domain |

### 14.1. Ma trận kiểm thử tối thiểu

1. Chuỗi ASCII round-trip UTF-8/Base64.
2. Chuỗi tiếng Việt và emoji round-trip.
3. Empty input và empty output theo contract.
4. Invalid Base64 alphabet với Basic.
5. URL-safe alphabet và đúng URL decoder.
6. MIME line breaks trong trường hợp MIME hợp lệ.
7. Missing padding và padding sai.
8. Base64 hợp lệ nhưng bytes UTF-8 malformed.
9. UTF-8 hợp lệ nhưng text vi phạm business schema.
10. Ký tự Unicode không biểu diễn được trong ASCII, strict encoder reject.
11. Malformed surrogate trong Java String.
12. Encoded input bằng đúng ngưỡng và lớn hơn một ký tự.
13. Decoded bytes bằng đúng ngưỡng và lớn hơn một byte.
14. Input stream kết thúc ở ranh giới nhóm 3 bytes và dư 1–2 bytes.
15. Encoder wrapper close hoàn tất padded output.
16. Decoder wrapper đọc lỗi trả IOException đúng.
17. Nguồn dữ liệu chậm hoặc hủy request.
18. Số request đồng thời cao và memory budget.
19. Decompression bomb/ảnh dimensions lớn trong parser sau decode.
20. Cleanup sau khi size exceeded hoặc validation failed.
21. Không log token raw hay thông tin nhạy cảm.
22. Kiểm thử canonical representation nếu giao thức yêu cầu.

## 15. Bài tập tự kiểm tra và đáp án

**Câu 1.** Base64 có phải UTF-8 không?

**Đáp án:** Không. Base64 chuyển bytes thành ký tự ASCII và ngược lại; UTF-8 chuyển Unicode String thành bytes và ngược lại.

**Câu 2.** Tại sao phải dùng `StandardCharsets.UTF_8` khi encode/decode text?

**Đáp án:** Để tránh lệ thuộc default charset và giữ contract giữa producer/consumer, nhất là với ký tự tiếng Việt/emoji.

**Câu 3.** `String.length()` có bằng số bytes UTF-8 không?

**Đáp án:** Không. String.length đếm UTF-16 code units; UTF-8 bytes có độ dài khác tùy code point.

**Câu 4.** `Base64.getDecoder().decode("SGV sbG8=")` làm gì?

**Đáp án:** Ném `IllegalArgumentException` vì Basic decoder từ chối space nằm ngoài alphabet.

**Câu 5.** `Base64.getMimeDecoder()` trên cùng String làm gì?

**Đáp án:** Bỏ qua space theo MIME decoder và giải ra “Hello”.

**Câu 6.** `Base64.getDecoder()` có luôn từ chối input thiếu padding không?

**Đáp án:** Không. Javadoc cho phép unit cuối có 2/3 ký tự không padding theo quy tắc hợp lệ.

**Câu 7.** Basic và URL Base64 khác alphabet ở đâu?

**Đáp án:** Basic có `+` và `/`, URL-safe thay bằng `-` và `_`.

**Câu 8.** Base64 hợp lệ có đảm bảo bytes UTF-8 hợp lệ không?

**Đáp án:** Không. Một payload binary tùy ý có thể encode/decode Base64 hợp lệ nhưng không thể giải thành UTF-8 strict.

**Câu 9.** `new String(malformedBytes,UTF_8)` có luôn throw không?

**Đáp án:** Không. Overload nhận Charset dùng replacement khi malformed/unmappable.

**Câu 10.** Khi cần từ chối UTF-8 malformed phải làm gì?

**Đáp án:** Dùng `StandardCharsets.UTF_8.newDecoder().onMalformedInput(REPORT).onUnmappableCharacter(REPORT)` rồi decode ByteBuffer.

**Câu 11.** Mặc định `CharsetDecoder.newDecoder()` có REPORT hay REPLACE?

**Đáp án:** REPORT, khác một số convenience methods thay thế đầu vào lỗi.

**Câu 12.** Một text tiếng Việt được đưa sang US_ASCII thì sao?

**Đáp án:** Không thể mã hóa đầy đủ; `getBytes(US_ASCII)` có thể thay thế, còn CharsetEncoder(REPORT) từ chối.

**Câu 13.** Encoder/Decoder của charset có thread-safe để share không?

**Đáp án:** `CharsetDecoder`/`CharsetEncoder` là stateful engines, không thread-safe; không dùng một instance mutable chung không có synchronization.

**Câu 14.** Vì sao Base64 10 MiB raw thành khoảng 13,98 triệu ký tự?

**Đáp án:** Basic Base64 padded output có 4 ký tự cho mỗi nhóm 3 bytes, theo `4*ceil(n/3)`; 10 MiB ra 13.981.016 ký tự.

**Câu 15.** Tại sao kiểm tra raw.length sau khi decode không đủ chống OOM?

**Đáp án:** Vì byte[] quá lớn đã được cấp phát trước khi kiểm tra. Giải mã dạng stream và chặn ngay khi vượt limit.

**Câu 16.** `ByteArrayOutputStream` trong bounded decode có giữ dữ liệu trên heap không?

**Đáp án:** Có, nhưng nếu maxBytes nhỏ và hợp lý thì được chặn; với payload lớn nên stream-to-file.

**Câu 17.** `Base64.Encoder.wrap(OutputStream)` cần close để làm gì?

**Đáp án:** Để flush các bytes cuối và tạo padding/chuỗi hoàn chỉnh, đồng thời giải phóng underlying stream.

**Câu 18.** Có thể decode từng chunk Base64 bất kỳ bằng Decoder.decode rồi ghép bytes không?

**Đáp án:** Không an toàn nếu cắt giữa nhóm 4 ký tự; dùng stream decoder duy trì trạng thái.

**Câu 19.** Giới hạn Base64 decoded bytes có đủ bảo vệ khỏi ZIP bomb không?

**Đáp án:** Không. Cần giới hạn kích thước **sau giải nén** và số entry/depth/tài nguyên parser.

**Câu 20.** Base64 có chứng minh payload được xác thực không?

**Đáp án:** Không. Cần MAC/chữ ký hoặc authentication mechanism phù hợp.

**Câu 21.** Một String hợp lệ UTF-8 có tự đạt chuẩn Unicode normalization NFC không?

**Đáp án:** Không. Normalization là bước riêng theo policy ứng dụng.

**Câu 22.** Khi dùng MIME decoder, có cần giới hạn encoded input không?

**Đáp án:** Có. MIME có thể bỏ qua nhiều ký tự ngoài alphabet; decoded size nhỏ không loại trừ tiêu tốn CPU/network do input rất lớn.

## 16. Tổng kết

- **Charset, Base64 và giới hạn tài nguyên là ba vấn đề khác nhau.** UTF-8 mã hóa Unicode String thành bytes; Base64 mã hóa bytes thành text ASCII; giới hạn memory/I/O áp ở cả hai chiều.
- **`StandardCharsets.UTF_8` phải tường minh** khi giao thức quy định UTF-8. Default charset và charset mismatch là nguồn lỗi thường gặp, không phải lỗi của Base64.
- **Basic, URL-safe, MIME Base64 có chính sách parser khác nhau.** Basic/URL từ chối ký tự ngoài alphabet; MIME bỏ qua nhiều ký tự. Java decoder có thể chấp nhận missing padding hợp lệ.
- **Base64 decode thành công không chứng minh UTF-8 đúng.** Dùng strict `CharsetDecoder(REPORT)` khi input phải well-formed, thay vì mặc định `new String` cho phép replacement.
- **Encoding cũng có lỗi:** với text không biểu diễn được trong ASCII hay charset hạn chế, strict `CharsetEncoder(REPORT)` có thể từ chối thay vì làm mất dữ liệu.
- **Base64 làm tăng kích thước truyền tải khoảng một phần ba**, còn memory thực có thể lớn hơn do String, byte arrays và copies. Không đọc toàn bộ file lớn vào RAM khi có thể streaming.
- **Giới hạn encoded body lẫn decoded bytes**, và giới hạn nội dung sau giải nén/parse; sử dụng streaming, backpressure và concurrency limits.
- **Đóng Base64 streaming encoder** để phát phần output cuối; decoder stream cần try-with-resources để đóng đúng underlying resources.
- **Base64 không phải encryption/integrity/authentication.** File type, Unicode normalization, schema, TOCTOU, security và trust boundaries phải xử lý riêng.
- **Java 8 runnable demo đã kiểm chứng** round-trip, malformed UTF-8, strict encoder, Base64 variants, bounded streaming và tính kích thước. Những API này tiếp tục áp dụng trên JDK hiện đại.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Base64](https://docs.oracle.com/javase/8/docs/api/java/util/Base64.html)
- [Oracle Java SE 8 — Base64.Decoder](https://docs.oracle.com/javase/8/docs/api/java/util/Base64.Decoder.html)
- [Oracle Java SE 8 — Base64.Encoder](https://docs.oracle.com/javase/8/docs/api/java/util/Base64.Encoder.html)
- [Oracle Java SE 8 — CharsetDecoder](https://docs.oracle.com/javase/8/docs/api/java/nio/charset/CharsetDecoder.html)
- [Oracle Java SE 8 — CharsetEncoder](https://docs.oracle.com/javase/8/docs/api/java/nio/charset/CharsetEncoder.html)
- [Oracle Java SE 8 — CodingErrorAction](https://docs.oracle.com/javase/8/docs/api/java/nio/charset/CodingErrorAction.html)
- [Oracle Java SE 8 — StandardCharsets](https://docs.oracle.com/javase/8/docs/api/java/nio/charset/StandardCharsets.html)
- [Oracle Java SE 8 — String](https://docs.oracle.com/javase/8/docs/api/java/lang/String.html)
- [Oracle Java SE 8 — InputStreamReader](https://docs.oracle.com/javase/8/docs/api/java/io/InputStreamReader.html)
- [Oracle Java SE 8 — ByteArrayOutputStream](https://docs.oracle.com/javase/8/docs/api/java/io/ByteArrayOutputStream.html)
- [Oracle Java SE 26 — Base64](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html)
- [Oracle Java SE 26 — CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
