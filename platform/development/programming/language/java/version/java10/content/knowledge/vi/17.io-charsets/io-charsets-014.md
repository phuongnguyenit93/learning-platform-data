# Kiểm thử dữ liệu tiếng Việt với bộ mã đầu vào và đầu ra khác nhau (Java 10+)

## 1. Vấn đề cần giải quyết

Một ứng dụng Java có thể nhận tệp văn bản từ hệ thống A bằng **UTF-8** nhưng phải xuất sang hệ thống B bằng **UTF-16LE**; hoặc đọc nội dung tiếng Việt từ mạng, kiểm tra rồi ghi một tệp UTF-8 mới. Chỉ nhìn thấy chữ “Tiếng Việt” hiển thị đúng trên màn hình **chưa đủ** để kết luận việc chuyển mã đã chính xác.

Dữ liệu tiếng Việt là bộ kiểm thử hữu ích vì có các ký tự như `ă, â, ê, ô, ơ, ư, đ` và nhiều dấu thanh. Nếu chương trình đọc byte bằng charset không đúng, chuỗi có thể bị biến thành *mojibake* (chữ bị loạn mã), bị thay bằng dấu hỏi, hoặc ném lỗi giải mã. Ngược lại, khi writer dùng charset không biểu diễn được ký tự đích, dữ liệu cũng có thể bị mất.

Từ Java 10, chúng ta có thể dùng `Reader.transferTo(Writer)` để chuyển dữ liệu ở **tầng ký tự** từ một Reader sang một Writer; các API `Charset`, `Files.newBufferedReader`, `Files.newBufferedWriter` và `CharsetDecoder/CharsetEncoder` vẫn là cách xử lý đúng trong Java hiện đại.

**Mục tiêu của bài:** thực hiện và kiểm thử một đường đi cụ thể:

`Tệp UTF-8 → giải mã đúng → String/ký tự Java → mã hóa UTF-16LE → tệp mới → giải mã UTF-16LE → xác nhận nội dung → mã hóa lại UTF-8 → kiểm tra byte.`

Bài còn bao gồm các test lỗi có chủ đích: chọn sai charset đầu vào, dữ liệu byte không hợp lệ, charset đầu ra không chứa tiếng Việt, khác chuẩn hóa Unicode và các tình huống BOM.

Sau bài này, bạn cần phân biệt được **text equality**, **byte equality**, **charset conversion**, **Unicode normalization** và **mất dữ liệu do lỗi encoding**; viết test độc lập môi trường và không dựa vào charset mặc định của máy chạy.

## 2. Charset là hợp đồng chuyển đổi byte ↔ ký tự

`Charset` quy định cách diễn dịch các byte thành ký tự khi **đọc** và cách biến ký tự thành byte khi **ghi**:

```text
INPUT BYTES --[CharsetDecoder: inputCharset]--> Java characters
Java characters --[CharsetEncoder: outputCharset]--> OUTPUT BYTES
```

Một số điểm mấu chốt:

1. Byte không tự mang thông tin chắc chắn về charset. Hệ thống gửi phải định nghĩa charset trong protocol, metadata hoặc tài liệu định dạng.
2. `String` trong Java đại diện cho chuỗi ký tự ở mức Unicode, không phải mảng byte UTF-8 hay UTF-16LE của file. `String.length()` đếm **UTF-16 code units**, không đếm byte hoặc luôn là số ký tự con người nhìn thấy.
3. Hai tệp có thể dùng **bộ byte khác nhau** nhưng giải mã thành **cùng một String**. Đó chính là mục đích của việc chuyển mã.
4. Nếu cùng một dãy byte bị đọc bằng charset sai, `String` tạo ra có thể khác ngay từ đầu. Đổi charset **khi ghi** không sửa được dữ liệu đã bị diễn dịch sai một cách đáng tin cậy.
5. Charset không tự chuẩn hóa Unicode về NFC/NFD; **giải mã đúng byte** và **chuẩn hóa các code point** là hai thao tác khác nhau.

Ví dụ:

```java
var text = "Tiếng Việt";
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
String restored = new String(bytes,
        java.nio.charset.StandardCharsets.UTF_8);

System.out.println(text.equals(restored)); // true
```

Đây là ví dụ trong thân một phương thức. Dùng **cùng charset** ở hai chiều của một đường truyền byte là điều kiện thông thường để khôi phục text không mất mát.

## 3. Chọn bộ ký tự: đầu vào và đầu ra có thể khác nhau

Các charset chuẩn luôn được Java SE hỗ trợ và còn hữu ích hiện nay:

| Charset | Khi nào nên dùng | Lưu ý khi test |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Mặc định khuyến nghị cho trao đổi văn bản hiện đại | Hỗ trợ đầy đủ Unicode, số byte không bằng số `char` |
| `StandardCharsets.UTF_16LE` | Khi định dạng đầu ra quy định UTF-16 little-endian | Hai byte mỗi UTF-16 code unit; encoder không tự ghi BOM |
| `StandardCharsets.UTF_16BE` | Khi định dạng quy định UTF-16 big-endian | Khác thứ tự byte so với UTF-16LE; không tự ghi BOM |
| `StandardCharsets.UTF_16` | Khi giao thức quy định UTF-16 với chính sách BOM | Cần hiểu quy tắc BOM của charset này |
| `StandardCharsets.ISO_8859_1` | **Chỉ dùng làm negative test ở bài này** | Không biểu diễn đầy đủ tiếng Việt; không nên dùng làm output cho dữ liệu Unicode tiếng Việt |

**Không có quy tắc đầu vào và đầu ra phải cùng charset.** Chuyển mã UTF-8 → UTF-16LE là hợp lệ nếu cả hai charset biểu diễn được toàn bộ dữ liệu và chương trình dùng đúng charset ở hai biên.

Chọn charset theo **định dạng được thỏa thuận**, không chọn vì tên hệ điều hành, vùng địa lý hoặc file có đuôi `.txt`. Nếu phía nhận cần UTF-8, xuất UTF-8; nếu đặc tả bắt buộc UTF-16LE, xuất UTF-16LE. Một file có thể mở được trên editor không phải bằng chứng encoder được chọn đúng.

### Charset mặc định và các phiên bản Java

Java 18 đưa UTF-8 thành charset mặc định của nhiều API Java SE theo **JEP 400**; ở Java 17 trở xuống, charset mặc định của JVM có thể phụ thuộc môi trường. Một số cấu hình/runtime vẫn cho phép điều chỉnh theo cơ chế được hỗ trợ. Do đó, kể cả trên JDK hiện đại, **đoạn code xử lý dữ liệu trao đổi giữa hệ thống nên chọn charset tường minh**.

```java
import java.nio.charset.StandardCharsets;

// ĐỌC có charset:
var reader = java.nio.file.Files.newBufferedReader(
        inputPath, StandardCharsets.UTF_8);

// GHI có charset:
var writer = java.nio.file.Files.newBufferedWriter(
        outputPath, StandardCharsets.UTF_16LE);
```

Đây là mã minh họa cần `inputPath/outputPath` trong một phương thức có xử lý `IOException` và đóng resource. Bản đầy đủ ở mục 11 dùng `try-with-resources`.

**Lưu ý chính xác:** overload `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path)` không truyền charset đã dùng **UTF-8** từ Java 8, nên không nên nói tất cả API không truyền charset luôn dùng default. Các API Java khác có chính sách riêng. Để bài test dễ đọc và tránh nhầm lẫn, vẫn truyền `StandardCharsets.UTF_8` rõ ràng ở mọi điểm quan trọng.

## 4. Thiết kế dữ liệu kiểm thử tiếng Việt có tính phân biệt cao

Một test chỉ chứa `"Hello"` hoặc chữ không dấu gần như **không thể phát hiện** việc chọn nhầm một số charset tương thích ASCII. Dữ liệu test cần bao gồm nhiều nhóm:

- Dấu thanh và nguyên âm: `á, à, ả, ã, ạ; ă, â, ê, ô, ơ, ư`.
- Chữ `đ/Đ`: dễ phát hiện lỗi chuyển mã trong nguồn tiếng Việt.
- Từ/cụm có dấu phức tạp: `Tiếng Việt`, `Trường học`, `Hà Nội`, `Cần Thơ`, `đậm đà`, `Ước mơ`.
- Dấu câu và ký hiệu ngoài ASCII: ví dụ dấu gạch dài `–`.
- Ký tự ngoài BMP: emoji `😀` để xác nhận xử lý surrogate pair và đếm ký tự.
- Dấu xuống dòng và khoảng trắng: xác nhận định dạng và phép chuyển mã không vô tình làm thay đổi nội dung.
- Khi cần: cả dạng Unicode **NFC/NFD** để phát hiện các giả định sai về cách biểu diễn dấu.

Đoạn dữ liệu ở ví dụ chạy đầy đủ:

```java
private static final String SAMPLE =
        "Tiếng Việt: Trường học, Hà Nội, Cần Thơ, đậm đà – \uD83D\uDE00\n" +
        "Dòng hai: Ước mơ và tiếng nói.";
```

Trong Java source, hai chuỗi `\uD83D\uDE00` biểu diễn một cặp surrogate của emoji, `\n` là newline. Đừng đoán số ký tự bằng cách nhìn độ dài hiển thị của dòng.

**Bộ mẫu dùng để test phải được kiểm soát.** Lưu tệp mã nguồn mẫu bằng UTF-8 và khi biên dịch trên môi trường có charset mặc định không chắc chắn, truyền `javac -encoding UTF-8`. Nếu dữ liệu mẫu ban đầu đã bị ghi sai ngay trong source code, mọi bước round-trip về sau có thể chỉ xác minh một chuỗi đã hỏng.

## 5. Chuyển mã đúng: giải mã đầu vào, mã hóa đầu ra

Mẫu cơ bản của việc chuyển UTF-8 → UTF-16LE:

```java
static long convert(
        java.nio.file.Path source,
        java.nio.file.Path target) throws java.io.IOException {

    try (var reader = java.nio.file.Files.newBufferedReader(
                 source, java.nio.charset.StandardCharsets.UTF_8);
         var writer = java.nio.file.Files.newBufferedWriter(
                 target, java.nio.charset.StandardCharsets.UTF_16LE)) {

        return reader.transferTo(writer); // Java 10+
    }
}
```

Các đặc tính:

1. `newBufferedReader(source, UTF_8)` diễn dịch **byte UTF-8 của tệp nguồn** thành ký tự Java.
2. `Reader.transferTo(writer)` truyền **các ký tự**, không “copy raw bytes”. Điều này cho phép charset đích **khác** charset nguồn.
3. `newBufferedWriter(target, UTF_16LE)` mã hóa ký tự nhận được thành byte UTF-16 little-endian.
4. `try-with-resources` đóng cả Reader và Writer kể cả khi có exception. Đặc biệt, đóng Writer giúp hoàn tất việc xả buffer theo hợp đồng của tài nguyên.
5. `transferTo` trả **số ký tự đã chuyển** (các đơn vị `char` Java), không phải số byte trong input/output.
6. Nếu I/O hoặc việc giải/mã hóa thất bại, thao tác có thể đã ghi **một phần tệp đích**; không nên xuất bản tệp đó như dữ liệu đã chuyển thành công.

Cùng nguyên tắc để chuyển ngược UTF-16LE → UTF-8:

```java
try (var reader = java.nio.file.Files.newBufferedReader(
             utf16File, java.nio.charset.StandardCharsets.UTF_16LE);
     var writer = java.nio.file.Files.newBufferedWriter(
             backUtf8File, java.nio.charset.StandardCharsets.UTF_8)) {
    reader.transferTo(writer);
}
```

Đoạn trên giả định các đường dẫn được khai báo hợp lệ. Không đọc file UTF-16LE bằng `UTF_8` rồi mong Writer UTF-8 tự “sửa” nó. Charset **đầu vào phải đúng** trước khi bất kỳ logic nghiệp vụ nào sử dụng text.

## 6. Chọn phép xác minh phù hợp: String bằng nhau hay byte bằng nhau?

Có **hai câu hỏi kiểm thử** khác nhau:

**A. Chuyển mã khác charset có làm thay đổi nội dung Unicode không?**

```java
String sourceText = readText(utf8Source, StandardCharsets.UTF_8);
String convertedText = readText(utf16Target, StandardCharsets.UTF_16LE);

boolean contentPreserved = sourceText.equals(convertedText);
```

Đối với phép chuyển mã không có chuyển đổi nội dung, `contentPreserved` phải là `true`.

**B. Chuyển ngược về charset ban đầu có khôi phục byte không?**

```java
byte[] before = java.nio.file.Files.readAllBytes(utf8Source);
byte[] after = java.nio.file.Files.readAllBytes(backToUtf8);

boolean bytesPreserved = java.util.Arrays.equals(before, after);
```

Nếu input và output dùng cùng quy tắc UTF-8, nguồn không có metadata/BOM được xử lý khác, nội dung không bị normalize/thay newline và byte đầu vào hợp lệ, ta có thể kỳ vọng byte sau round-trip **khớp chính xác**. Đây là phép thử mạnh.

**Không so byte trực tiếp giữa tệp UTF-8 và UTF-16LE** rồi kết luận “lỗi” vì chúng khác nhau: khác biệt byte **là mục đích** của chuyển mã. Ở đây:

- UTF-8 input và UTF-16LE output: **text equality**.
- UTF-8 input và UTF-8 được chuyển ngược: **byte equality** trong điều kiện kiểm thử được kiểm soát.
- Kết quả đúng về *ký tự* không đồng nghĩa mọi metadata hoặc byte representation của file có giá trị tương đương. Tệp có thể khác BOM, newline, normalization hoặc định dạng bao ngoài nếu có bước xử lý bổ sung.

## 7. Vì sao “đúng charset output” chưa đủ nếu input đã giải mã sai?

Ví dụ lấy byte UTF-8 của chữ `"Tiếng Việt"` rồi giải mã thành ISO-8859-1:

```java
var original = "Tiếng Việt";
byte[] utf8Bytes = original.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

var incorrect = new String(utf8Bytes,
        java.nio.charset.StandardCharsets.ISO_8859_1);

System.out.println(original.equals(incorrect)); // false
```

Đây là **negative test** cố tình dùng sai charset. ISO-8859-1 có thể giải mã mọi giá trị byte nhưng không thể tự hiểu rằng dữ liệu đầu vào là UTF-8. Kết quả thường được gọi là *mojibake*.

Sau khi có `incorrect`, ghi nó bằng UTF-8 sẽ tạo ra **byte UTF-8 hợp lệ của text đã sai**, chứ không đảm bảo trở lại tiếng Việt gốc. Vì vậy:

1. Chọn đúng charset tại **điểm đi từ byte vào ký tự**.
2. So sánh text với **mẫu chuẩn đáng tin** sau bước giải mã.
3. Không coi một lần decode không ném exception là bằng chứng charset đúng.
4. Không chạy một chuỗi “encode/decode khác charset” tùy tiện để cứu dữ liệu đã hỏng.
5. Khi tích hợp thực tế, yêu cầu đối tác công bố charset chính xác của input trong specification hoặc metadata có thể tin cậy.

Nếu một byte stream không có thông tin charset, thuật toán “đoán encoding” chỉ là heuristic và có thể mơ hồ. Với API yêu cầu tính toàn vẹn, cần chính sách khai báo hoặc từ chối không xác định, thay vì đoán rồi âm thầm mất dấu tiếng Việt.

## 8. Kiểm tra dữ liệu byte bị lỗi: decoder strict thay vì thay thế âm thầm

Có hai nhóm sai sót:

- **Malformed input:** chuỗi byte không hợp lệ theo quy tắc charset được chọn. Ví dụ `C3 28` không hợp lệ như UTF-8 vì `C3` cần một continuation byte đúng định dạng.
- **Unmappable character:** một ký tự không thể được biểu diễn trong charset đích, chẳng hạn nhiều ký tự tiếng Việt khi cố ghi thành ISO-8859-1.

Các API convenience và các đường đi qua decoder có thể có chính sách xử lý lỗi khác nhau. Ví dụ constructor `new String(bytes, charset)` có thể **thay thế** chuỗi không hợp lệ; nếu cần đảm bảo không mất dữ liệu, dùng decoder/encoder với:

```java
import java.nio.charset.CodingErrorAction;

var decoder = java.nio.charset.StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Khi có byte không hợp lệ:

```java
byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

try {
    decoder.decode(java.nio.ByteBuffer.wrap(invalidUtf8));
} catch (java.nio.charset.CharacterCodingException ex) {
    System.out.println(ex.getClass().getSimpleName());
    // MalformedInputException với mẫu byte này.
}
```

Nếu cần Reader trên stream có chính sách strict, dùng `InputStreamReader(InputStream, CharsetDecoder)` với decoder đã cấu hình. Bản chạy đầy đủ có phương thức `decodeStrict(...)` dùng đúng cách đó.

**Lưu ý:** `Files.newBufferedReader(path, charset)` cũng quy định việc đọc ném `IOException` nếu gặp byte sequence malformed/unmappable; `Files.newBufferedWriter(path, charset)` báo `IOException` khi ký tự không thể mã hóa bằng charset. Vì có buffering, lỗi ghi có thể xuất hiện lúc `write`, `flush` **hoặc `close`**. Không bắt lỗi tại riêng một lệnh `write` rồi coi file đã hoàn chỉnh.

### Khi nào nên dùng `REPORT` thay vì `REPLACE`?

- Dữ liệu hồ sơ, thông tin định danh, tên riêng hoặc nội dung tiếng Việt cần giữ chính xác: **REPORT** và dừng/đánh dấu lỗi là lựa chọn an toàn.
- Tài liệu hiển thị không quan trọng bằng việc tiếp tục xử lý có thể cho phép replacement theo chính sách cụ thể, nhưng phải công bố **mất dữ liệu** và có test chấp nhận.
- Không dùng ký tự `?` hoặc `�` làm “cách khắc phục” âm thầm nếu một phép chuyển mã được yêu cầu bảo toàn nội dung.

## 9. Kiểm thử charset đầu ra không thể biểu diễn tiếng Việt

`CharsetEncoder` có thể được cấu hình kiểm soát trường hợp ký tự không được hỗ trợ:

```java
var encoder = java.nio.charset.StandardCharsets.ISO_8859_1
        .newEncoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);

try {
    encoder.encode(java.nio.CharBuffer.wrap("Tiếng Việt"));
    System.out.println("unexpected success");
} catch (java.nio.charset.CharacterCodingException ex) {
    System.out.println(ex.getClass().getSimpleName());
    // UnmappableCharacterException.
}
```

ISO-8859-1 chỉ đóng vai trò **ví dụ âm tính nhằm chứng minh giới hạn của bảng mã**, không phải charset được khuyến nghị cho việc lưu tiếng Việt. Với dữ liệu đa ngôn ngữ, ưu tiên UTF-8 trừ khi giao thức có yêu cầu khác.

Một negative test tốt phải **kỳ vọng lỗi**: nếu tự động thay ký tự không thể biểu diễn bằng `?`, file có thể trông hợp lệ nhưng đã mất nội dung. Với thông tin không thể mất dấu, hãy test bằng cách xác minh encoder báo lỗi hoặc text round-trip không bằng text gốc theo chính sách dự án.

## 10. Unicode normalization: khác nhau ở code point dù nhìn giống nhau

Tiếng Việt có dấu có thể được biểu diễn bằng:

- **NFC:** dùng ký tự ghép sẵn khi có thể, ví dụ nhiều dạng chữ có dấu.
- **NFD:** phân rã thành ký tự cơ sở và các dấu kết hợp (*combining marks*).

Hai chuỗi đôi khi **nhìn giống nhau** khi hiển thị nhưng có dãy code point khác, nên `String.equals()` trả `false`. Ví dụ:

```java
import java.text.Normalizer;

String nfc = "Tiếng Việt";
String nfd = Normalizer.normalize(nfc, Normalizer.Form.NFD);

System.out.println(nfc.equals(nfd)); // false với mẫu này
System.out.println(nfc.equals(
        Normalizer.normalize(nfd, Normalizer.Form.NFC))); // true
```

**Không nhầm normalization với charset conversion.** UTF-8 có thể mã hóa cả NFC và NFD một cách hợp lệ. Chuyển UTF-8 → UTF-16LE **không tự đổi** dạng chuẩn hóa. Nếu ứng dụng có yêu cầu so sánh/search/dedup tên tiếng Việt theo cách thống nhất, phải lựa chọn normalization policy một cách **độc lập**.

Mẫu kiểm thử:

1. Chuẩn hóa input và output cùng một dạng (thường NFC) **chỉ khi nghiệp vụ cho phép**.
2. So sánh text sau normalization để kiểm tra tương đương ở mức biểu diễn Unicode.
3. Nếu yêu cầu **bảo toàn nguyên bản**, vẫn giữ test `String.equals()` hoặc byte round-trip để phát hiện thay đổi normalization ngoài ý muốn.
4. Khi xử lý định danh, ký số, hashing hoặc file phải giống nguyên văn, **không normalize tùy tiện** vì điều đó thay đổi chuỗi byte và có thể thay đổi ý nghĩa của hợp đồng dữ liệu.

Case negative sai charset và case negative NFC/NFD phải được phân loại riêng; áp dụng `Normalizer` không phải cách sửa *mojibake*.

## 11. Chương trình Java 10+ hoàn chỉnh đã kiểm chứng

Tạo tệp **`VietnameseCharsetIoDemo.java`** và lưu bằng **UTF-8**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.io.Writer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;

public final class VietnameseCharsetIoDemo {
    private static final String SAMPLE =
            "Tiếng Việt: Trường học, Hà Nội, Cần Thơ, đậm đà – \uD83D\uDE00\n" +
            "Dòng hai: Ước mơ và tiếng nói.";

    static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    static String readAll(Reader reader) throws IOException {
        char[] buffer = new char[512];
        var result = new StringBuilder();
        for (int count; (count = reader.read(buffer)) != -1;) {
            result.append(buffer, 0, count);
        }
        return result.toString();
    }

    static String readText(Path file, Charset charset) throws IOException {
        try (var reader = Files.newBufferedReader(file, charset)) {
            return readAll(reader);
        }
    }

    static long transcode(Path from, Charset inputEncoding,
                          Path to, Charset outputEncoding) throws IOException {
        try (var reader = Files.newBufferedReader(from, inputEncoding);
             var writer = Files.newBufferedWriter(to, outputEncoding)) {
            return reader.transferTo(writer);
        }
    }

    static String decodeStrict(byte[] bytes, Charset charset) throws IOException {
        var decoder = charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try (var reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), decoder)) {
            return readAll(reader);
        }
    }

    public static void main(String[] args) throws Exception {
        Path folder = Files.createTempDirectory("vn-charset-");
        Path utf8File = folder.resolve("source-utf8.txt");
        Path utf16File = folder.resolve("converted-utf16le.txt");
        Path backFile = folder.resolve("back-utf8.txt");

        try {
            Files.write(utf8File, SAMPLE.getBytes(StandardCharsets.UTF_8));
            long moved = transcode(utf8File, StandardCharsets.UTF_8,
                    utf16File, StandardCharsets.UTF_16LE);

            String restored = readText(utf16File, StandardCharsets.UTF_16LE);
            require(SAMPLE.equals(restored), "UTF-8 to UTF-16LE text changed");
            require(moved == SAMPLE.length(), "Character count changed");
            System.out.println("utf8ToUtf16le=" + SAMPLE.equals(restored));
            System.out.println("charsMoved=" + moved
                    + ", codePoints=" + SAMPLE.codePointCount(0, SAMPLE.length()));
            System.out.println("utf8Bytes=" + Files.size(utf8File)
                    + ", utf16leBytes=" + Files.size(utf16File));

            long movedBack = transcode(utf16File, StandardCharsets.UTF_16LE,
                    backFile, StandardCharsets.UTF_8);
            byte[] originalBytes = Files.readAllBytes(utf8File);
            byte[] finalBytes = Files.readAllBytes(backFile);
            require(Arrays.equals(originalBytes, finalBytes),
                    "UTF-8 round-trip bytes changed");
            System.out.println("roundTripUtf8Bytes="
                    + Arrays.equals(originalBytes, finalBytes));
            System.out.println("reverseCharsMoved=" + movedBack);

            String wrong = new String(originalBytes, StandardCharsets.ISO_8859_1);
            System.out.println("wrongInputCharsetSameText=" + SAMPLE.equals(wrong));

            var strictUtf8 = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);
            byte[] malformed = {(byte) 0xC3, (byte) 0x28};
            try {
                strictUtf8.decode(java.nio.ByteBuffer.wrap(malformed));
                System.out.println("malformedUtf8=unexpected-success");
            } catch (CharacterCodingException expected) {
                System.out.println("malformedUtf8=" + expected.getClass().getSimpleName());
            }

            var strictLatin1 = StandardCharsets.ISO_8859_1.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);
            try {
                strictLatin1.encode(CharBuffer.wrap(SAMPLE));
                System.out.println("unmappableOutput=unexpected-success");
            } catch (CharacterCodingException expected) {
                System.out.println("unmappableOutput=" + expected.getClass().getSimpleName());
            }

            String nfd = Normalizer.normalize(SAMPLE, Normalizer.Form.NFD);
            System.out.println("sameTextNfdByEquals=" + SAMPLE.equals(nfd));
            System.out.println("sameAfterNfc=" + SAMPLE.equals(
                    Normalizer.normalize(nfd, Normalizer.Form.NFC)));

            byte[] utf16Bytes = Files.readAllBytes(utf16File);
            System.out.println("utf16leStartsWithTAndNull="
                    + (utf16Bytes[0] == (byte) 'T' && utf16Bytes[1] == 0));
            System.out.println("strictUtf8Valid=" + SAMPLE.equals(
                    decodeStrict(originalBytes, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(backFile);
            Files.deleteIfExists(utf16File);
            Files.deleteIfExists(utf8File);
            Files.deleteIfExists(folder);
        }
    }
}
```

Biên dịch và chạy trên JDK có hỗ trợ `--release 10`:

```bash
javac -encoding UTF-8 --release 10 VietnameseCharsetIoDemo.java
java VietnameseCharsetIoDemo
```

`-encoding UTF-8` ở đây buộc **mã hóa của file mã nguồn Java**, khác với các charset tệp dữ liệu được chọn tường minh trong chương trình. Ví dụ đã được kiểm tra về khả năng biên dịch/chạy với mức ngôn ngữ Java 10.

**Stdout chính xác đã đối chiếu:**

```text
utf8ToUtf16le=true
charsMoved=83, codePoints=82
utf8Bytes=116, utf16leBytes=166
roundTripUtf8Bytes=true
reverseCharsMoved=83
wrongInputCharsetSameText=false
malformedUtf8=MalformedInputException
unmappableOutput=UnmappableCharacterException
sameTextNfdByEquals=false
sameAfterNfc=true
utf16leStartsWithTAndNull=true
strictUtf8Valid=true
```

Ý nghĩa của các dòng:

1. `utf8ToUtf16le=true` chứng minh text giải mã từ tệp UTF-16LE giống **chính xác** mẫu Unicode ban đầu.
2. `charsMoved=83, codePoints=82` cho thấy Java đếm một emoji thành **hai `char` surrogate**, nhưng là **một code point**. `Reader.transferTo` trả số UTF-16 code units đã chuyển trong ca này.
3. `utf8Bytes=116, utf16leBytes=166` xác nhận hai cách mã hóa lưu cùng text bằng **số byte khác nhau**, không phải lỗi.
4. `roundTripUtf8Bytes=true` và `reverseCharsMoved=83` chứng minh chuyển ngược và kiểm tra byte chính xác với mẫu đã kiểm soát.
5. `wrongInputCharsetSameText=false` là negative test: giải mã các byte UTF-8 bằng charset khác làm thay đổi text, dù có thể không ném lỗi.
6. `malformedUtf8=MalformedInputException` chứng minh decoder strict từ chối byte không hợp lệ.
7. `unmappableOutput=UnmappableCharacterException` chứng minh charset đầu ra thiếu khả năng biểu diễn dấu tiếng Việt được báo lỗi.
8. `sameTextNfdByEquals=false`, `sameAfterNfc=true` phân biệt **Unicode normalization** với lựa chọn charset.
9. `utf16leStartsWithTAndNull=true` xác nhận hai byte đầu của UTF-16LE chứa `T` là `54 00` theo hệ hex, không tự có BOM.
10. `strictUtf8Valid=true` là đối chứng tích cực: cùng decoder strict vẫn chấp nhận byte UTF-8 hợp lệ.

Test tạo tệp trong thư mục tạm, đọc/ghi bằng charset tường minh, kiểm tra và xóa các tệp trong `finally`. Nó không cần kết nối mạng hoặc thư viện ngoài Java SE. Kết quả chỉ khẳng định đúng các phép thử trên **bộ mẫu đã nêu**, không tự thay thế cho kiểm thử tích hợp với dữ liệu thực của đối tác.

## 12. Mẹo tách nguyên nhân sai khi thấy chữ tiếng Việt bị lỗi

Khi xuất hiện `"Tiáº¿ng"`, dấu hỏi hoặc ký tự thay thế, cần kiểm tra từng bước theo thứ tự:

**Bước 1 — Xác nhận byte gốc.** Thu thập kích thước, một mẫu hex không chứa dữ liệu nhạy cảm, file hash và metadata charset từ phía gửi. Không mở file bằng editor rồi ghi lại ngay vì editor có thể tự đổi charset/BOM/newline.

**Bước 2 — Xác nhận input charset.** Charset do giao thức quy định là gì? UTF-8, UTF-16LE hay UTF-16BE? Nếu file có BOM, đã xử lý đúng theo chính sách định dạng chưa? Không suy luận từ hệ điều hành.

**Bước 3 — Decode strict.** Với UTF-8, thử decoder cấu hình `REPORT` hoặc `Files.newBufferedReader(path, UTF_8)` để phát hiện chuỗi byte không hợp lệ. Nếu decode thành công mà text sai, có thể là **sai charset nhưng byte vẫn hợp lệ**, hoặc dữ liệu đã bị lỗi ở nguồn.

**Bước 4 — Kiểm tra text trước khi ghi.** So sánh `String` với mẫu chuẩn bằng `equals()`, kiểm tra code points ở vị trí nghi ngờ, và thử NFC/NFD **chỉ để phân loại** nếu khác biệt do dạng dấu kết hợp.

**Bước 5 — Xác nhận output charset.** Writer có được tạo với đúng charset mà phía nhận yêu cầu? Charset có biểu diễn được mọi ký tự không? Khi cần toàn vẹn, phải báo lỗi nếu unmappable, không tự thay ký tự.

**Bước 6 — Đọc ngược tệp xuất.** Mở tệp bằng chính charset đã xuất, so sánh text. Nếu công việc có thể đảo ngược và dữ liệu được kiểm soát, chuyển lại encoding ban đầu và so byte.

**Bước 7 — Kiểm tra các lớp ngoài charset.** Editor/terminal, HTTP Content-Type, database client, CSV parser, newline converter hoặc hệ thống nhận có thể diễn dịch text khác. Java chương trình xử lý đúng UTF-8 không bảo đảm màn hình console cũng đang hiển thị UTF-8; không dựa duy nhất vào screenshot terminal để chứng minh dữ liệu file đúng.

## 13. BOM: UTF-16 khác UTF-16LE và UTF-16BE

**Byte-order mark (BOM)** là thông tin có thể xuất hiện ở đầu một số luồng dữ liệu Unicode để chỉ thứ tự byte hoặc báo nhận dạng encoding.

Theo đặc tả `StandardCharsets`:

- `UTF_16LE`: mã hóa little-endian; encoder **không tự ghi BOM**.
- `UTF_16BE`: mã hóa big-endian; encoder **không tự ghi BOM**.
- `UTF_16`: encoder dùng big-endian và ghi BOM, decoder có thể dùng BOM đầu luồng để xác định byte order; khi không có BOM, quy tắc mặc định của decoder có thể là big-endian theo charset.
- `UTF_8`: không cần BOM để phân biệt byte order; xử lý BOM nếu đầu vào có phụ thuộc hợp đồng dữ liệu/parser cụ thể, không tự thêm hoặc xóa tùy ý.

Ví dụ test của mục 11 xuất UTF-16LE, với ký tự đầu tiên là `T`, hai byte đầu là `54 00` (hex). Đây là kết quả được xác minh; không nên giả định mọi tệp UTF-16 được tạo bởi một nguồn khác đều không có BOM.

Nếu phía nhận yêu cầu **UTF-16LE không BOM**, chọn `UTF_16LE` và test byte đầu. Nếu phía nhận yêu cầu **UTF-16 kèm BOM**, hãy chọn và kiểm tra chế độ phù hợp theo spec của họ. Mismatch BOM có thể làm một file hiển thị khác hoặc có ký tự `U+FEFF` ngoài mong đợi.

Không coi một byte BOM là “ký tự tiếng Việt bị hỏng”; cần xác định nó thuộc **metadata encoding** hay đã được đưa vào nội dung text.

## 14. Java String, char, code point và số byte: ba số đo khác nhau

Chuỗi ví dụ chứa một emoji ngoài BMP. Java biểu diễn nó bằng **cặp surrogate UTF-16**:

```java
String text = "Hi \uD83D\uDE00";

int charUnits = text.length(); // 5
int codePoints = text.codePointCount(0, text.length()); // 4
int utf8Bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length; // 7
int utf16leBytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_16LE).length; // 10
```

Với `text`:

- 5 `char`/UTF-16 code units.
- 4 Unicode code points.
- 7 byte UTF-8.
- 10 byte UTF-16LE.

Với toàn bộ `SAMPLE` trong chương trình, số liệu thực tế là `83 char`, `82 code point`, `116 byte UTF-8` và `166 byte UTF-16LE`. Đây là dữ liệu chuẩn cho **mẫu cụ thể**, không phải công thức tổng quát “mỗi ký tự tiếng Việt chiếm đúng N byte UTF-8”.

Nếu nghiệp vụ yêu cầu **độ dài tối đa tính theo byte**, phải đo sau khi mã hóa bằng charset đích. Nếu yêu cầu **độ dài theo ký tự hiển thị**, Unicode grapheme cluster còn phức tạp hơn cả code point; không dùng `String.length()` như số chữ con người nhìn thấy. Chọn đơn vị đo rõ trong API, DB column, quota và test.

## 15. Newline, khoảng trắng và dữ liệu văn bản nhiều dòng

`Reader/Writer` khi đọc/ghi ký tự không tự chuyển toàn bộ newline thành dạng của hệ điều hành; nhưng một số API xử lý theo dòng hoặc các bước ứng dụng có thể thay đổi dấu xuống dòng.

Ví dụ:

```java
String text = "Dòng một\nDòng hai";
```

Nếu kiểm thử yêu cầu **byte equality** sau round-trip, tránh thay `\n` thành `\r\n` hoặc ngược lại ngoài ý muốn. Cũng cần bảo toàn khoảng trắng cuối dòng, tab, các dấu kết hợp Unicode và ký tự phân tách trường.

Các cách test:

- Test cả `\n` và `\r\n` nếu hệ thống thực tế hỗ trợ hai biến thể.
- Nếu phần mềm **có yêu cầu chuẩn hóa newline**, tách test này khỏi **charset conversion** và không đòi byte equality khi đã cố ý thay newline.
- Nếu dùng `BufferedReader.readLine()` rồi `Writer.write(line)`, nhớ rằng `readLine()` bỏ dấu kết thúc dòng; phải định nghĩa cách ghi lại newline. Với mục tiêu giữ nguyên các ký tự của nguồn, `Reader.transferTo` hoặc vòng đọc/ghi theo buffer thường thích hợp hơn.
- Với CSV/JSON/XML, xác định charset tại lớp byte và để parser xử lý cấu trúc; không dùng thao tác thay chuỗi thủ công để “sửa mã tiếng Việt” khi chưa xác định dữ liệu thực sự lỗi ở đâu.

## 16. Thiết kế test matrix cho tích hợp thực tế

Một bộ test có ý nghĩa nên bao gồm cả đường thành công và đường lỗi.

| Ca thử | Input | Output dự kiến | Điều kiểm tra |
| --- | --- | --- | --- |
| T1 — cùng charset | UTF-8 hợp lệ | UTF-8 | Text và byte round-trip khớp |
| T2 — khác charset | UTF-8 hợp lệ | UTF-16LE | Text giải mã từ output khớp input |
| T3 — đảo chiều | UTF-16LE hợp lệ | UTF-8 | Text khớp, và byte gốc UTF-8 được khôi phục với fixture kiểm soát |
| T4 — sai input charset | Byte UTF-8 nhưng decode ISO-8859-1 | String sai | Negative test phát hiện mismatch text, không nhất thiết ném lỗi |
| T5 — malformed bytes | Byte `C3 28` đọc như UTF-8 strict | Lỗi | `MalformedInputException` hoặc lỗi decoding thích hợp |
| T6 — output không đủ ký tự | Unicode tiếng Việt → ISO-8859-1 strict | Lỗi | `UnmappableCharacterException`, không âm thầm thay thế |
| T7 — NFC/NFD | Hai chuỗi nhìn giống nhưng khác code point | Theo policy | Phân biệt exact equality với canonical equivalence |
| T8 — emoji/non-BMP | Có emoji | Bảo toàn | Không cắt hỏng surrogate pair |
| T9 — newline/whitespace | Nhiều dòng và khoảng trắng | Theo yêu cầu | Không đổi nội dung ngoài ý muốn |
| T10 — BOM | Input/output có/không BOM theo spec | Theo spec | Kiểm tra byte đầu và quy tắc decoder |
| T11 — nguồn lớn | Nhiều ký tự tiếng Việt và emoji | Bảo toàn | Streaming và tài nguyên phù hợp |
| T12 — lỗi I/O | Reader/Writer ném IOException | Không công bố kết quả dở dang | Cleanup và xử lý phần file đã ghi |

Một số lưu ý khi xây dựng automation:

- Test tên/chuỗi/ký tự phải có **expected value từ nguồn độc lập đáng tin**, không tự tạo expected bằng đúng hàm đang được kiểm thử nếu muốn phát hiện lỗi của chính hàm đó.
- Không dùng `System.out.println(text)` làm assertion duy nhất; console hoặc font có thể hiển thị sai dù chuỗi trong bộ nhớ đúng.
- Kiểm tra **byte thực** bằng `Files.readAllBytes`/hex/hash khi cần bảo toàn tệp, và **String thực** khi cần bảo toàn nội dung.
- Khi test `IOException`, phải xác nhận file xuất **không được xuất bản** nếu chưa hoàn thành chuyển mã.
- Với hệ thống trao đổi qua HTTP, kiểm tra header charset, dạng payload thật và byte body; đừng suy luận từ việc browser hiển thị ổn.
- Với database, kiểm tra charset/collation ở tầng lưu trữ và driver theo giao thức được hỗ trợ; Java Unicode đúng ở một tầng không khắc phục encoding sai ở tầng khác.

## 17. Tránh những cách làm gây lỗi dữ liệu

### 17.1. Dùng default charset không kiểm soát

```java
// Không nên làm khi đặc tả nguồn ghi UTF-8 nhưng máy chạy có thể khác:
// new InputStreamReader(inputStream);
// text.getBytes();
```

Hãy viết:

```java
new java.io.InputStreamReader(
        inputStream, java.nio.charset.StandardCharsets.UTF_8);

text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

Đây là các expression minh họa cần được đặt trong ngữ cảnh hợp lệ. Điều quan trọng là charset **được nêu trực tiếp**.

### 17.2. Chọn UTF-8 cho đầu ra nhưng đọc nguồn bằng sai encoding

Sai ở bước giải mã rồi ghi đúng ở bước mã hóa sẽ khiến dữ liệu bị hỏng theo cách hợp lệ về mặt byte. Điều cần sửa là xác định đúng charset input; nếu không biết, hãy báo không chắc chắn thay vì “đoán đại”.

### 17.3. So sánh byte của hai charset khác nhau

UTF-8 và UTF-16LE cho dãy byte khác nhau dù cùng nội dung. Trong test chuyển mã, so sánh **text** sau decode, không so trực tiếp input bytes với output bytes.

### 17.4. Cho phép replacement mà không có yêu cầu

Khi một ký tự tiếng Việt không có trong charset đích, một số API có thể chèn ký tự thay thế. Với tên riêng hoặc dữ liệu nghiệp vụ, đây là mất mát không thể phục hồi đáng tin. Dùng encoder strict và test ngoại lệ.

### 17.5. Nghĩ tất cả ký tự tiếng Việt đều chiếm một byte hoặc một char

Không đúng. UTF-8 có độ dài biến đổi; Java String dùng UTF-16 code units; dấu kết hợp và emoji làm việc đếm phức tạp hơn.

### 17.6. Nghĩ BOM ở UTF-16LE và UTF-16 là như nhau

Không đúng: UTF-16LE/BE và UTF-16 có quy tắc BOM/byte order khác nhau. Chọn charset và kiểm tra byte theo spec.

### 17.7. Dùng Normalizer để “chữa mojibake”

Normalizer thay dạng Unicode, không tự suy ra charset gốc của dữ liệu đã giải mã sai. Chỉ normalize khi chính sách canonical equivalence đòi hỏi.

### 17.8. Ghi trực tiếp file đích sản xuất trước khi xác minh

Nếu writer bị lỗi sau khi ghi một phần, file có thể bị bỏ dở hoặc đã bị truncate. Với dữ liệu quan trọng, ghi vào **tệp tạm trong cùng khu vực lưu trữ**, xác minh kết quả rồi mới publish bằng cơ chế thay thế file thích hợp; tính atomic của bước move phải được kiểm chứng cho filesystem/provider đang dùng.

### 17.9. Quên đóng Reader/Writer hoặc không xử lý lỗi close

Nếu output có buffering, lỗi encoding có thể chỉ xuất hiện khi flush/close. Dùng `try-with-resources` và để exception lan theo hợp đồng, thay vì bỏ qua thất bại ở cuối luồng.

### 17.10. Chạy test chỉ với chuỗi ASCII

Một testcase như `"Hello World"` không kiểm tra đủ lớp ký tự tạo nên tiếng Việt. Cần fixture với dấu, `đ`, ký tự ngoài BMP, newline và dạng normalization.

## 18. Checklist dành cho code review và QA

- [ ] Xác định **input charset** từ hợp đồng nguồn, không đoán bằng file extension.
- [ ] Xác định **output charset** từ hợp đồng đích; có cần BOM không?
- [ ] Dùng `StandardCharsets` hoặc Charset tường minh trong mọi biên đọc/ghi quan trọng.
- [ ] Test chứa đủ dấu tiếng Việt, `đ/Đ`, chữ hoa/chữ thường, newline và ký tự ngoài BMP nếu hệ thống cho phép.
- [ ] Có **positive test** UTF-8 → UTF-16LE → decode UTF-16LE với `String.equals()`.
- [ ] Có **round-trip test** về UTF-8 với so byte khi kỳ vọng bảo toàn nguyên dạng.
- [ ] Có negative test sai input charset ngay cả khi decoder không ném lỗi.
- [ ] Có test malformed UTF-8 và output unmappable trong chế độ strict.
- [ ] Không nhầm khác byte do charset với lỗi Unicode normalization.
- [ ] Chính sách NFC/NFD rõ ràng, nhất là dữ liệu tìm kiếm/so sánh và định danh.
- [ ] Đếm đúng đơn vị: bytes, UTF-16 code units, code points hoặc grapheme clusters.
- [ ] Với file tạm và Writer buffered, xử lý close/IOException và không publish file dở dang.
- [ ] Test không phụ thuộc charset mặc định, locale, editor hay console font.
- [ ] Có test tài liệu, metadata/BOM và parser ở cả hai đầu tích hợp.
- [ ] Tất cả biến thể expected/actual được kiểm tra bằng assertion hoặc logic phát hiện lỗi, không chỉ nhìn console.

## 19. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Một tệp UTF-8 chứa `"Tiếng Việt"`; chương trình đọc bằng UTF-16LE rồi ghi UTF-8. Có bảo đảm text đích đúng không?

**Đáp án:** Không. Giải mã sai đầu vào có thể gây lỗi hoặc tạo text sai. Cần giải mã bằng UTF-8 trước khi ghi ở charset đích.

**Câu 2.** Khi chuyển UTF-8 → UTF-16LE, so sánh byte hai tệp thấy khác. Có phải lỗi?

**Đáp án:** Không. Hai charset biểu diễn cùng ký tự thành dãy byte khác. Kiểm tra text sau khi decode output bằng UTF-16LE.

**Câu 3.** UTF-8 → UTF-16LE → UTF-8, dưới fixture kiểm soát, bạn nên kiểm tra gì?

**Đáp án:** Text equality sau mỗi bước giải mã và byte equality giữa file UTF-8 ban đầu và file UTF-8 cuối cùng, với điều kiện không normalize, thêm BOM hoặc đổi newline.

**Câu 4.** Vì sao `new String(utf8Bytes, ISO_8859_1)` có thể trả chuỗi mà không ném lỗi nhưng vẫn sai tiếng Việt?

**Đáp án:** Charset đó có thể giải mã mọi byte thành một ký tự nhưng diễn dịch byte UTF-8 sai. Một lần decode thành công không đủ chứng minh input charset đúng.

**Câu 5.** `CodingErrorAction.REPORT` giúp gì?

**Đáp án:** Cho phép decoder/encoder báo lỗi malformed hoặc unmappable thay vì âm thầm thay thế ký tự. Đây là lựa chọn phù hợp khi bảo toàn dữ liệu là yêu cầu.

**Câu 6.** ISO-8859-1 có phải charset nên dùng để ghi toàn bộ tiếng Việt hiện đại không?

**Đáp án:** Không. Nó không biểu diễn đầy đủ ký tự tiếng Việt; bài dùng nó làm negative test. Ưu tiên UTF-8 nếu giao thức không quy định khác.

**Câu 7.** Chuỗi `"Hi 😀"` có bao nhiêu `char` Java, Unicode code point và byte UTF-8?

**Đáp án:** Lần lượt **5**, **4**, **7**. Emoji là một code point nhưng gồm một cặp surrogate UTF-16.

**Câu 8.** Hai chuỗi nhìn như `"Tiếng Việt"` nhưng một NFC, một NFD, có thể `equals()` khác nhau không?

**Đáp án:** Có. Dãy code point khác nhau. Nếu nghiệp vụ cho phép canonical equivalence, normalize cùng dạng trước khi so sánh; không dùng normalization tùy tiện khi phải giữ bytes gốc.

**Câu 9.** `UTF_16LE` có mặc định ghi BOM giống `UTF_16` không?

**Đáp án:** Không. Encoder UTF-16LE không tự thêm BOM; chế độ UTF-16 có quy tắc khác. Kiểm tra theo spec của hệ thống nhận.

**Câu 10.** Vì sao nên lưu file Java test bằng UTF-8 và truyền `javac -encoding UTF-8`?

**Đáp án:** Để các ký tự tiếng Việt trực tiếp trong literal nguồn được compiler diễn dịch đúng bất kể charset mặc định của môi trường biên dịch.

**Câu 11.** Nếu Writer đang dùng charset không hỗ trợ một ký tự tiếng Việt, khi nào lỗi có thể được phát hiện?

**Đáp án:** Với `Files.newBufferedWriter`, ngoại lệ I/O do lỗi encoding có thể xuất hiện khi ghi, flush hoặc close vì buffering. Phải xử lý toàn bộ lifecycle.

**Câu 12.** Có thể kết luận byte output đúng chỉ vì terminal in ra câu tiếng Việt nhìn bình thường không?

**Đáp án:** Không. Terminal, console charset và font là một lớp khác. Phải kiểm tra byte file, charset được khai báo và text giải mã lại.

## 20. Tài liệu tham khảo chính thức đang áp dụng

- [Java SE — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, UTF-16, UTF-16BE, UTF-16LE và các charset chuẩn được bảo đảm.
- [Java SE — `Charset` và quy tắc BOM](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): charset, decoder/encoder và hành vi UTF-16.
- [Java SE — `Files.newBufferedReader/newBufferedWriter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): chọn charset đọc/ghi, cách báo lỗi malformed/unmappable, tính buffering.
- [Java SE — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): giải mã byte thành ký tự, chính sách xử lý lỗi.
- [Java SE — `CharsetEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát ký tự không thể mã hóa.
- [Java SE — `CodingErrorAction`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE`, `IGNORE`.
- [Java SE — `Reader.transferTo`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): chuyển các ký tự còn lại từ Reader sang Writer từ Java 10.
- [Java SE — `Normalizer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html): các dạng chuẩn hóa Unicode NFC/NFD.
- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ Java 18.
- [Oracle — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): tác động của charset mặc định giữa các thế hệ Java.

**Kết luận:** Khi đọc và ghi tiếng Việt với **charset khác nhau**, hãy nêu rõ charset ở **cả hai biên**, kiểm tra **String sau khi decode** và thực hiện **byte round-trip** khi điều kiện cho phép. Thêm strict decoding/encoding, dữ liệu có dấu và emoji, NFC/NFD, BOM và chính sách lỗi file để bảo đảm chuyển mã thực sự giữ nguyên nội dung — thay vì chỉ trông có vẻ đúng trên màn hình.
