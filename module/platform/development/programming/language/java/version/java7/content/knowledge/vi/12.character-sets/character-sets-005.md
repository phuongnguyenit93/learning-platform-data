# Xử lý dữ liệu không hợp lệ bằng `CharsetDecoder` và `CharsetEncoder` trong Java

## 1. Vì sao cần kiểm soát lỗi chuyển mã?

Ứng dụng thường phải nhận dữ liệu từ file, HTTP, hàng đợi, cơ sở dữ liệu hoặc thiết bị, rồi chuyển giữa **byte** và **ký tự Unicode**. Trong Java, kiểu `String` / `CharBuffer` lưu dữ liệu dưới dạng các *UTF-16 code units*, còn file hay giao thức truyền qua các byte theo một **charset** cụ thể: UTF-8, US-ASCII, UTF-16...

Có ít nhất hai tình huống không thể chuyển đổi bình thường:

- **Byte đầu vào không hợp lệ** theo charset đã chọn, ví dụ byte `0xC3` trong UTF-8 mà không có byte tiếp theo hợp lệ.
- **Ký tự Unicode không thể biểu diễn** trong charset đầu ra, ví dụ `é` khi xuất văn bản thành US-ASCII.

Nếu chỉ muốn hiển thị một đoạn văn không đáng tin cậy, ứng dụng có thể chấp nhận ký tự thay thế. Nếu đang kiểm tra chữ ký số, định danh, cấu trúc dữ liệu, số tài khoản hoặc giao thức bắt buộc UTF-8 hợp lệ, việc âm thầm thay thế/bỏ ký tự có thể khiến dữ liệu bị hiểu sai.

Hai lớp chuẩn trong `java.nio.charset` giải quyết bài toán theo chính sách rõ ràng:

- `CharsetDecoder`: **byte → ký tự Unicode**.
- `CharsetEncoder`: **ký tự Unicode → byte**.

Cả hai cho phép chọn cách xử lý dữ liệu lỗi, thay vì mặc định phó mặc cho hành vi của các API tiện dụng. Các API này vẫn được dùng trên **Java hiện đại**, kể cả Java 21; bài không khuyến nghị API đã legacy hoặc dựa vào charset mặc định của máy.

**Kết quả học tập:** phân biệt `malformed` và `unmappable`, cấu hình `REPORT`/`REPLACE`/`IGNORE`, kiểm thử kết quả lossless/lossy, xử lý `ByteBuffer`/`CharBuffer` theo lô và theo luồng, hiểu `CoderResult`/`flush`, lựa chọn chính sách phù hợp với dữ liệu sản xuất.

## 2. Hai chiều chuyển đổi và điểm phát sinh lỗi

~~~text
ByteBuffer -- CharsetDecoder --> CharBuffer / String
              ^
              | cấu hình cách xử lý byte lỗi

CharBuffer / String -- CharsetEncoder --> ByteBuffer
                        ^
                        | cấu hình cách xử lý ký tự không biểu diễn được
~~~

Đây là sơ đồ dữ liệu, không phải mã Java.

| Khía cạnh | `CharsetDecoder` | `CharsetEncoder` |
| --- | --- | --- |
| Đầu vào | `ByteBuffer` | `CharBuffer` |
| Đầu ra | `CharBuffer` | `ByteBuffer` |
| Tạo đối tượng | `charset.newDecoder()` | `charset.newEncoder()` |
| Chuyển đổi trọn gói | `decode(ByteBuffer)` | `encode(CharBuffer)` |
| Chuyển đổi tăng dần | `decode(in, out, endOfInput)` | `encode(in, out, endOfInput)` |
| Xử lý malformed | `onMalformedInput(action)` | `onMalformedInput(action)` |
| Xử lý unmappable | `onUnmappableCharacter(action)` | `onUnmappableCharacter(action)` |
| Cấu hình replacement | `replaceWith(String)` | `replaceWith(byte[])` |
| Kết thúc một phiên tăng dần | `flush(CharBuffer)` | `flush(ByteBuffer)` |

**Không nhầm đơn vị:** `byte` trong `ByteBuffer` không phải một ký tự; `char` trong Java là một **UTF-16 code unit**, không nhất thiết là một code point Unicode hoàn chỉnh. Ký tự ngoài Basic Multilingual Plane có thể cần **cặp surrogate**; nếu tách cặp đó không đúng trong một phiên encoding, dữ liệu có thể bị coi là malformed.

### 2.1. Malformed input là gì?

*Malformed* nghĩa là các đơn vị đầu vào **không tạo thành chuỗi hợp lệ** theo charset/biểu diễn đầu vào.

Ví dụ:

- Decoder UTF-8 nhận byte `0xC3` nhưng byte kế tiếp lại là `0x28`, không phải continuation byte `0x80..0xBF`. Đó là một chuỗi UTF-8 **malformed**.
- Encoder UTF-8 nhận một `char` *high surrogate* `\\uD800` mà không có *low surrogate* tương ứng, khiến chuỗi UTF-16 đầu vào **malformed**.

Lỗi loại này thường được báo bằng `MalformedInputException` khi dùng phương thức chuyển đổi trọn gói trong chế độ `REPORT`.

### 2.2. Unmappable character là gì?

*Unmappable* nghĩa là chuỗi đầu vào **hợp lệ về hình thức**, nhưng **không thể ánh xạ** sang ký tự/byte hợp lệ của charset đầu ra.

Ví dụ: `é` (U+00E9) là ký tự Unicode hợp lệ, nhưng US-ASCII không có mã byte biểu diễn nó. `CharsetEncoder` dùng `StandardCharsets.US_ASCII` sẽ báo `UnmappableCharacterException` khi cấu hình `REPORT`.

Trong chiều decode, một charset cũng có thể có byte sequence hợp lệ về mặt cấu trúc nhưng không ánh xạ được tới ký tự Unicode; các lỗi này được xử lý qua `onUnmappableCharacter`. Tuy nhiên, **không phải mỗi charset đều có thể tái hiện cả hai loại lỗi** với mọi chuỗi; ví dụ UTF-8 không cần `UnmappableCharacterException` cho trường hợp byte `0xC3 0x28`, vì đó là malformed.

### 2.3. So sánh nhanh

| Input | Chiều chuyển | Charset | Vấn đề | Hướng xử lý đúng |
| --- | --- | --- | --- | --- |
| `41 C3 28 42` | Decode | UTF-8 | `C3 28` malformed | Report, replace hoặc ignore theo chính sách |
| `AéB` | Encode | US-ASCII | `é` unmappable | Report, replace hoặc dùng charset có thể biểu diễn `é` |
| Một `\\uD800` đơn lẻ | Encode | UTF-8 | UTF-16 malformed | Report/replace/ignore; nếu đang streaming thì chờ thêm input trước EOF |
| `€` (U+20AC) | Encode | UTF-8 | Hợp lệ, ánh xạ được | Cho ra `E2 82 AC` |
| `A` | Encode | US-ASCII | Hợp lệ, ánh xạ được | Cho ra `41` |

Lưu ý: chữ `\\uD800` ở bảng là cách ký hiệu code unit, **không phải ký tự Unicode độc lập hợp lệ** cần hiển thị cho người dùng.

## 3. Ba chính sách `CodingErrorAction`

Khi tạo decoder/encoder, ta có thể cấu hình **riêng** hành vi khi malformed và khi unmappable:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Đây là đoạn minh họa cần import `CharsetDecoder`, `CharsetEncoder`, `StandardCharsets` và `CodingErrorAction` từ `java.nio.charset`.

| Action | Khi dữ liệu lỗi | Có mất dữ liệu gốc? | Khi nên cân nhắc |
| --- | --- | --- | --- |
| `CodingErrorAction.REPORT` | Báo lỗi cho caller: `CharacterCodingException` ở API trọn gói, hoặc `CoderResult` lỗi ở API tăng dần | Không tự ý chuyển dữ liệu sai thành dữ liệu hợp lệ | Dữ liệu có hợp đồng bắt buộc đúng charset; import/validation, định danh, giao thức |
| `CodingErrorAction.REPLACE` | Bỏ chuỗi đơn vị bị lỗi và thêm giá trị replacement | **Có**, không khôi phục nguyên bản từ kết quả đã thay | Hiển thị nội dung có thể chấp nhận mất một phần |
| `CodingErrorAction.IGNORE` | Bỏ qua chuỗi đơn vị bị lỗi, không thêm gì | **Có**, thường khó phát hiện đoạn bị mất | Chỉ khi nghiệp vụ chủ động cho phép loại bỏ và có kiểm toán thích hợp |

**Giá trị mặc định của đối tượng mới:** theo Javadoc, `CharsetDecoder.newDecoder()` và `CharsetEncoder.newEncoder()` mặc định chọn **`REPORT` cho cả malformed lẫn unmappable**. Vì muốn code minh bạch và không lệ thuộc thói quen nhớ mặc định, ví dụ nghiêm ngặt có thể khai báo action tường minh.

**Cảnh báo về các API tiện dụng:** điều này **không** có nghĩa `new String(bytes, charset)` hay `charset.decode(buffer)` cũng mặc định báo lỗi. Nhiều API chuyển đổi tiện dụng cấu hình **replacement** để tạo ra kết quả kể cả khi input lỗi. Phần 5 có kiểm thử xác nhận sự khác biệt.

### 3.1. Chọn chính sách khác nhau cho từng loại lỗi

Có thể xem malformed là lỗi không chấp nhận, nhưng cho phép thay thế unmappable:

~~~java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);
~~~

Đây là đoạn minh họa: input UTF-16 malformed bị báo lỗi, còn một ký tự Unicode hợp lệ ngoài US-ASCII được thay bằng replacement byte. Cách chọn phải phản ánh **hợp đồng của dữ liệu**, không phải cố gắng xóa cảnh báo.

Tương tự, decoder có hai cấu hình độc lập. `onMalformedInput` không đồng thời tự đổi `onUnmappableCharacter`, và ngược lại.

## 4. Phương thức trọn gói: kiểm soát checked exception

Một cách dễ dùng decoder để **kiểm tra UTF-8 nghiêm ngặt**:

~~~java
static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
~~~

Đây là phương thức cần đặt trong một lớp và import `ByteBuffer`, `CharsetDecoder`, `CodingErrorAction`, `CharacterCodingException`, `StandardCharsets`. Không dùng `String` constructor nếu yêu cầu **phải phát hiện** byte sai.

Với một buffer đầu vào trọn vẹn, `CharsetDecoder.decode(ByteBuffer)` tự thực hiện **reset → decode → flush**, trả `CharBuffer` ở trạng thái có thể đọc; khi gặp dữ liệu lỗi theo `REPORT`, nó ném `CharacterCodingException`, thường là subtype:

- `MalformedInputException` đối với byte sequence không hợp lệ.
- `UnmappableCharacterException` đối với sequence hợp lệ nhưng không ánh xạ được.

Chiều ngược lại:

~~~java
static ByteBuffer encodeAsciiStrict(String value)
        throws CharacterCodingException {
    CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    return encoder.encode(CharBuffer.wrap(value));
}
~~~

Đây là phương thức minh họa trong một lớp. Với `"AéB"`, US-ASCII không thể mã hóa `é` và phương thức sẽ ném `UnmappableCharacterException`. Nếu nghiệp vụ yêu cầu giữ được tiếng Việt hoặc nhiều ký tự quốc tế, cân nhắc **UTF-8** thay vì cố tình thay thế dữ liệu qua US-ASCII.

### 4.1. Vì sao phải đọc dữ liệu từ vị trí buffer hiện tại?

`ByteBuffer.wrap(bytes)` tạo buffer có `position = 0` và `limit = bytes.length`. `decode` chỉ đọc dữ liệu trong phần `remaining()`. `CharBuffer.wrap(text)` cũng tương tự trong chiều ngược.

Các phương thức mã hóa/giải mã **tiêu thụ dữ liệu từ vị trí hiện tại**, có thể làm thay đổi `position` của input buffer. Không tự giả định buffer ban đầu luôn còn nguyên vị trí sau khi chuyển đổi. Khi cần đọc lại đầu vào, chuẩn bị buffer mới hoặc dùng `duplicate()`/`asReadOnlyBuffer()` phù hợp.

## 5. Chương trình Java 21 đầy đủ — kiểm thử ba action, thay thế tùy chỉnh và dữ liệu chia khối

Tạo file `src/main/java/demo/CharsetCodingErrorExample.java`:

~~~java
package demo;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public final class CharsetCodingErrorExample {
    private CharsetCodingErrorExample() {}

    static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static String hex(ByteBuffer value) {
        ByteBuffer copy = value.asReadOnlyBuffer();
        StringJoiner joiner = new StringJoiner(" ");
        while (copy.hasRemaining()) {
            joiner.add(String.format(Locale.ROOT, "%02X", Byte.toUnsignedInt(copy.get())));
        }
        return joiner.toString();
    }

    static String decodeUtf8(byte[] input, CodingErrorAction action)
            throws CharacterCodingException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action);
        return decoder.decode(ByteBuffer.wrap(input)).toString();
    }

    static ByteBuffer encodeAscii(String input, CodingErrorAction action)
            throws CharacterCodingException {
        CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action);
        return encoder.encode(CharBuffer.wrap(input));
    }

    static void decodeSplitUtf8() throws CharacterCodingException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);
        ByteBuffer in = ByteBuffer.allocate(8);
        CharBuffer out = CharBuffer.allocate(8);

        in.put(new byte[] {(byte) 0xE2, (byte) 0x82});
        in.flip();
        CoderResult first = decoder.decode(in, out, false);
        System.out.println("stream-first=" + first + ",remaining=" + in.remaining());

        in.compact();
        in.put(new byte[] {(byte) 0xAC, (byte) '!'});
        in.flip();
        CoderResult second = decoder.decode(in, out, true);
        System.out.println("stream-final=" + second + ",remaining=" + in.remaining());

        CoderResult flushed = decoder.flush(out);
        System.out.println("stream-flush=" + flushed);

        out.flip();
        System.out.println("stream-points=" + codePoints(out.toString()));
    }

    static void incompleteAtEof() {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);
        ByteBuffer in = ByteBuffer.wrap(new byte[] {(byte) 0xE2, (byte) 0x82});
        CharBuffer out = CharBuffer.allocate(8);
        CoderResult beforeEof = decoder.decode(in, out, false);
        CoderResult atEof = decoder.decode(in, out, true);
        System.out.println("incomplete-before-eof=" + beforeEof);
        System.out.println("incomplete-at-eof=" + atEof);
        try {
            atEof.throwException();
        } catch (CharacterCodingException ex) {
            System.out.println("incomplete-error=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws CharacterCodingException {
        byte[] brokenUtf8 = {0x41, (byte) 0xC3, 0x28, 0x42};
        try {
            decodeUtf8(brokenUtf8, CodingErrorAction.REPORT);
        } catch (CharacterCodingException ex) {
            System.out.println("utf8-report=" + ex.getClass().getSimpleName());
        }
        System.out.println("utf8-replace="
                + codePoints(decodeUtf8(brokenUtf8, CodingErrorAction.REPLACE)));
        System.out.println("utf8-ignore="
                + codePoints(decodeUtf8(brokenUtf8, CodingErrorAction.IGNORE)));

        CharsetDecoder customDecoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPLACE)
                .replaceWith("*");
        System.out.println("utf8-custom="
                + codePoints(customDecoder.decode(ByteBuffer.wrap(brokenUtf8)).toString()));
        System.out.println("string-constructor="
                + codePoints(new String(brokenUtf8, StandardCharsets.UTF_8)));

        String text = "A\\u00E9B";
        try {
            encodeAscii(text, CodingErrorAction.REPORT);
        } catch (CharacterCodingException ex) {
            System.out.println("ascii-report=" + ex.getClass().getSimpleName());
        }
        System.out.println("ascii-replace="
                + hex(encodeAscii(text, CodingErrorAction.REPLACE)));
        System.out.println("ascii-ignore="
                + hex(encodeAscii(text, CodingErrorAction.IGNORE)));

        CharsetEncoder customEncoder = StandardCharsets.US_ASCII.newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPLACE)
                .replaceWith(new byte[] {0x21});
        System.out.println("ascii-custom="
                + hex(customEncoder.encode(CharBuffer.wrap(text))));

        String unpairedHighSurrogate = "\\uD800";
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(unpairedHighSurrogate));
        } catch (CharacterCodingException ex) {
            System.out.println("surrogate-report=" + ex.getClass().getSimpleName());
        }
        System.out.println("surrogate-replace="
                + hex(StandardCharsets.UTF_8.newEncoder()
                        .onMalformedInput(CodingErrorAction.REPLACE)
                        .encode(CharBuffer.wrap(unpairedHighSurrogate))));

        decodeSplitUtf8();
        incompleteAtEof();
    }
}
~~~

Từ thư mục chứa `src/`, dùng JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/CharsetCodingErrorExample.java
java -cp out demo.CharsetCodingErrorExample
~~~

**Stdout chính xác** (kiểm thử trên Java 21):

~~~text
utf8-report=MalformedInputException
utf8-replace=U+0041 U+FFFD U+0028 U+0042
utf8-ignore=U+0041 U+0028 U+0042
utf8-custom=U+0041 U+002A U+0028 U+0042
string-constructor=U+0041 U+FFFD U+0028 U+0042
ascii-report=UnmappableCharacterException
ascii-replace=41 3F 42
ascii-ignore=41 42
ascii-custom=41 21 42
surrogate-report=MalformedInputException
surrogate-replace=3F
stream-first=UNDERFLOW,remaining=2
stream-final=UNDERFLOW,remaining=0
stream-flush=UNDERFLOW
stream-points=U+20AC U+0021
incomplete-before-eof=UNDERFLOW
incomplete-at-eof=MALFORMED[2]
incomplete-error=MalformedInputException
~~~

**Chú ý về định dạng đầu ra:** ví dụ cố ý in code point `U+XXXX` và byte hex thay vì ký tự `�` trực tiếp, để stdout kiểm tra được ngay cả khi terminal dùng thiết lập hiển thị khác nhau. Các giá trị hex trong output **không có tiền tố `0x`**; `41 3F 42` tương ứng ba byte `0x41 0x3F 0x42`.

### 5.1. Giải thích nhóm UTF-8

Dữ liệu gốc `41 C3 28 42` biểu diễn chữ `A`, sau đó là chuỗi không hợp lệ vì `C3` không được theo sau bởi continuation byte, rồi `(` và `B`.

- `REPORT` báo `MalformedInputException`. Input phải được xử lý là lỗi thay vì tự động hợp thức hóa.
- `REPLACE` thay đơn vị lỗi bằng ký tự Unicode replacement `U+FFFD`, nên kết quả có code points `U+0041 U+FFFD U+0028 U+0042`.
- `IGNORE` bỏ lỗi mà không đưa replacement vào kết quả: chỉ còn `A(B` với ba code points.
- `replaceWith("*")` cho phép chọn replacement string của decoder; `U+002A` là dấu `*`.
- `new String(brokenUtf8, StandardCharsets.UTF_8)` cho kết quả có `U+FFFD`. Constructor tiện dụng này **không phải API kiểm tra strict UTF-8**; nó thay input malformed theo hợp đồng.

Điểm cốt lõi: `IGNORE` và `REPLACE` cho kết quả **không thể phục hồi chính xác byte gốc từ text đã chuyển**. Không dùng hai chính sách này nếu dữ liệu đang cần xác thực cú pháp ở byte-level hoặc phải bảo đảm chuyển đổi không mất thông tin.

### 5.2. Giải thích nhóm US-ASCII

Chuỗi đầu vào là `AéB`. US-ASCII biểu diễn được `A` và `B`, nhưng không thể biểu diễn `é`:

- `REPORT` ném `UnmappableCharacterException`.
- `REPLACE` dùng replacement mặc định của encoder US-ASCII trong môi trường kiểm thử, là byte `3F` (`?`), tạo kết quả `41 3F 42`.
- `IGNORE` bỏ `é`, chỉ còn `41 42`.
- `replaceWith(new byte[] {0x21})` thay bằng `!`, nên nhận `41 21 42`. Byte replacement do caller cấu hình phải hợp lệ trong charset đích.

Không khẳng định replacement của **mọi charset** đều là dấu `?`. Javadoc nói default replacement của encoder **thường**, nhưng không luôn luôn, là `?`. Muốn biết chính xác, lấy `encoder.replacement()` hoặc đặt giá trị tường minh và kiểm tra tính hợp lệ.

### 5.3. Vì sao lone surrogate là malformed, không phải unmappable?

Java String/CharBuffer dựa trên UTF-16 code units. Một *high surrogate* đứng đơn lẻ không tạo thành một chuỗi UTF-16 well-formed. Vì vậy `StandardCharsets.UTF_8.newEncoder()` phát hiện `MalformedInputException` khi `REPORT`.

Khi chọn `REPLACE` trên encoder UTF-8 trong ví dụ, replacement bytes thực tế là `3F`. Điều này **khác** với decoder UTF-8 mặc định sử dụng ký tự replacement `U+FFFD`. Cùng tên action, nhưng **đơn vị replacement của hai chiều khác nhau**: decoder tạo `String`, encoder tạo `byte[]`.

## 6. Dùng phương thức tăng dần: `CoderResult`, `endOfInput`, `flush`

Đối với file/stream rất lớn, dữ liệu có thể đến theo nhiều khối và một ký tự có thể bị cắt qua **ranh giới buffer**. Khi đó dùng:

~~~java
CoderResult result = decoder.decode(in, out, endOfInput);
~~~

Đây là đoạn minh họa; `in` là `ByteBuffer`, `out` là `CharBuffer`, và `endOfInput` cho biết liệu còn input sẽ được bổ sung sau khối hiện tại không.

Khác với phương thức `decode(ByteBuffer)` trọn gói ném `CharacterCodingException` khi `REPORT`, phương thức tăng dần trả về một **`CoderResult`** để caller xử lý vòng lặp.

| `CoderResult` | Ý nghĩa | Caller cần làm |
| --- | --- | --- |
| `UNDERFLOW` | Đã xử lý hết phần hiện có hoặc cần thêm input để hoàn tất một sequence | Nếu còn dữ liệu sẽ đến, giữ byte chưa tiêu thụ và nạp thêm; nếu là EOF thật, dùng `endOfInput=true` |
| `OVERFLOW` | Output buffer không đủ chỗ cho kết quả tiếp theo | `flip()`, tiêu thụ/ghi output, `clear()` hoặc `compact()` rồi gọi tiếp |
| `isMalformed()` | Gặp dữ liệu đầu vào sai cấu trúc, khi action là `REPORT` | Báo lỗi hoặc dùng `result.throwException()`; xem `result.length()` nếu cần xác định số input units bị lỗi |
| `isUnmappable()` | Input hợp lệ nhưng không ánh xạ được, khi action là `REPORT` | Xử lý như lỗi chính sách mã hóa/giải mã; không tự im lặng bỏ dữ liệu |

`result.isError()` trả true cho malformed hoặc unmappable, **không** cho overflow/underflow. Khi cần ném đúng checked exception từ một `CoderResult` lỗi, gọi `result.throwException()` trong nhánh `isError()`. Không gọi bừa trên `UNDERFLOW`/`OVERFLOW` chỉ để “kiểm tra”, vì hành vi ném của các trạng thái đó khác lỗi chuyển mã.

### 6.1. Một byte sequence UTF-8 bị cắt giữa hai khối

Ký tự `€` (U+20AC) được mã hóa UTF-8 thành `E2 82 AC`. Trong chương trình ở phần 5:

1. Khối đầu chỉ chứa `E2 82`; decoder được gọi với `endOfInput=false`. Kết quả `UNDERFLOW`, **còn 2 byte chưa xử lý**.
2. `in.compact()` giữ những byte còn lại, cho phép đưa `AC` và `!` vào sau đó.
3. Sau `in.flip()`, gọi `decode(in, out, true)` với **khối cuối**. Kết quả `UNDERFLOW`, không còn byte chưa xử lý.
4. Gọi `decoder.flush(out)` và kiểm tra kết quả, rồi `out.flip()` để đọc codepoints.
5. Kết quả là `U+20AC U+0021` — ký tự Euro và dấu chấm than, **không** có lỗi giả ở ranh giới khối.

**Lưu ý:** `UNDERFLOW` khi `endOfInput=false` và `in.remaining()>0` **không** chứng minh input hỏng. Nó có thể chỉ là một chuỗi hợp lệ bị tách, cần bổ sung byte tiếp theo.

### 6.2. Nếu input kết thúc thật trong lúc đang thiếu byte?

`incompleteAtEof()` thử cùng `E2 82` nhưng **không** có `AC` đi tiếp:

- Lần `decode(..., false)` trả `UNDERFLOW` vì còn khả năng có thêm byte.
- Lần cuối `decode(..., true)` trả `MALFORMED[2]` vì EOF xác nhận hai byte kia tạo thành sequence chưa hoàn chỉnh.
- `atEof.throwException()` ném `MalformedInputException` đúng theo trạng thái.

Điều này giải thích vì sao **không được tự báo malformed mỗi khi một lần đọc stream trả thiếu byte**. Chỉ khi biết chắc đã EOF mới xác định sequence còn dang dở là malformed (hoặc xử lý theo action khác).

### 6.3. Thứ tự gọi đúng cho decoder/encoder có trạng thái

Với một phiên tăng dần:

1. Tạo decoder/encoder mới hoặc gọi `reset()` **trước khi** bắt đầu phiên mới.
2. Gọi `decode`/`encode` với `endOfInput=false` cho các khối chưa phải cuối.
3. Ở lần cuối, gọi với `endOfInput=true` và tiếp tục xử lý `OVERFLOW` nếu output đầy.
4. Sau khi input cuối đã xử lý xong, gọi `flush(output)`. Nếu `flush` trả `OVERFLOW`, hãy tiêu thụ output rồi **gọi `flush` tiếp** đến khi `UNDERFLOW`.
5. Chỉ chuyển đối tượng decoder/encoder sang dữ liệu mới sau khi kết thúc phiên và `reset()` đúng cách.

Bỏ `flush()` hoặc gọi `decode(..., false)` sau khi phiên đã kết thúc không phải cách đúng để xử lý state. Với một số charset stateful, việc flush có thể tạo thêm output; không được giả định mọi charset chỉ có trạng thái đơn giản như UTF-8.

### 6.4. Quy tắc làm việc với buffer

- `flip()`: từ chế độ **ghi buffer** sang chế độ **đọc**.
- `compact()`: giữ phần input **chưa đọc**, chuyển chúng về đầu buffer để có chỗ thêm dữ liệu sau; rất quan trọng với byte sequence split.
- `clear()`: chuẩn bị buffer để ghi mới, **không lưu** phần input còn lại; dùng sai có thể mất byte chưa xử lý.
- `remaining()`: số phần tử giữa `position` và `limit`.
- `OVERFLOW`: phải giải phóng chỗ cho output. Tăng buffer mà không xử lý những ký tự/byte đã tạo có thể làm mất dữ liệu hoặc lặp lại.

`CharsetDecoder` và `CharsetEncoder` là các đối tượng **có trạng thái và không thread-safe**. Không dùng một instance đồng thời trên nhiều luồng hoặc cho nhiều luồng dữ liệu khác nhau. Tạo instance mới theo phiên, hoặc bảo đảm ownership và `reset()` tuần tự.

## 7. Mã hóa tăng dần khi UTF-16 surrogate pair bị tách

Tương tự UTF-8 bytes có thể bị chia khối, UTF-16 **high surrogate** và **low surrogate** có thể nằm ở hai lần bổ sung vào `CharBuffer`. Không báo malformed quá sớm khi chưa đến EOF.

Ví dụ độc lập tạo ký tự emoji U+1F600 bằng cặp `\\uD83D` + `\\uDE00`, sau đó mã hóa thành UTF-8. Tạo file `EncoderSplit.java`:

~~~java
import java.nio.*;
import java.nio.charset.*;

public class EncoderSplit {
    public static void main(String[] args) {
        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT);
        CharBuffer input = CharBuffer.allocate(4);
        ByteBuffer output = ByteBuffer.allocate(8);
        input.put('\\uD83D');
        input.flip();
        CoderResult first = encoder.encode(input, output, false);
        System.out.println("encoder-first=" + first + ",remaining=" + input.remaining());
        input.compact();
        input.put('\\uDE00');
        input.flip();
        CoderResult last = encoder.encode(input, output, true);
        System.out.println("encoder-final=" + last + ",remaining=" + input.remaining());
        System.out.println("encoder-flush=" + encoder.flush(output));
        output.flip();
        StringBuilder sb = new StringBuilder();
        while (output.hasRemaining()) {
            if (sb.length() != 0) {
                sb.append(" ");
            }
            sb.append(String.format("%02X",Byte.toUnsignedInt(output.get())));
        }
        System.out.println("encoder-hex=" + sb);
    }
}
~~~

Dùng JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all EncoderSplit.java
java EncoderSplit
~~~

**Stdout chính xác:**

~~~text
encoder-first=UNDERFLOW,remaining=1
encoder-final=UNDERFLOW,remaining=0
encoder-flush=UNDERFLOW
encoder-hex=F0 9F 98 80
~~~

Lần đầu encoder giữ lại **một high surrogate** trong input buffer (chưa tiêu thụ vì còn chờ low surrogate); sau `compact()` và bổ sung low surrogate, cả cặp được mã hóa thành bốn byte UTF-8 hợp lệ. Nếu high surrogate vẫn đứng đơn lẻ khi `endOfInput=true`, chính sách `REPORT` sẽ báo **malformed**.

Ví dụ trên dùng `StringBuilder` và `ByteBuffer` để in hex, không dựa vào terminal có hỗ trợ hiển thị emoji hay không.

## 8. Giá trị thay thế: decoder dùng `String`, encoder dùng `byte[]`

Hai phương thức tùy chỉnh có kiểu tham số **khác nhau**:

~~~java
decoder.replaceWith("*");                     // String cho text đầu ra
encoder.replaceWith(new byte[] {(byte) '?'}); // byte[] cho dữ liệu đầu ra
~~~

Đây là đoạn minh họa trong ngữ cảnh có decoder/encoder tương ứng. Giá trị replacement chỉ được sử dụng khi action cho loại lỗi đó là `REPLACE`.

### 8.1. `CharsetDecoder.replaceWith(String)`

- Replacement là một chuỗi ký tự Unicode cho output decoder.
- Theo Javadoc, replacement phải không null, không rỗng và không dài hơn `maxCharsPerByte()` theo ràng buộc của implementation.
- Giá trị mặc định thông thường của `CharsetDecoder` là ký tự Unicode replacement `\\uFFFD` (U+FFFD).
- Nếu dùng replacement đặc biệt như `"*"`, downstream có thể không phân biệt được dấu `*` xuất hiện thật với `*` do decoder đặt thay. Cân nhắc log lỗi hoặc giữ dữ liệu gốc khi cần chẩn đoán.

### 8.2. `CharsetEncoder.replaceWith(byte[])`

- Replacement là **chuỗi byte hợp lệ trong charset đầu ra**.
- Không null, không rỗng, không dài hơn `maxBytesPerChar()` và phải vượt qua kiểm tra **`isLegalReplacement(...)`** theo hợp đồng.
- Với US-ASCII, byte `0x21` (`!`) hợp lệ nên ví dụ cho kết quả `41 21 42`.
- Không mặc định sử dụng `EF BF BD` cho mọi encoder. `U+FFFD` là **ký tự Unicode**, trong khi byte replacement cho một charset cụ thể có thể khác hoàn toàn.
- Một chuỗi replacement sai có thể làm hỏng output protocol ngay cả khi các byte còn lại hợp lệ; hãy sử dụng giá trị có chủ đích và test round-trip khi cần.

**Không dùng `REPLACE` như một bộ lọc bảo mật.** Nó biến nhiều chuỗi dữ liệu gốc khác nhau thành một kết quả, có thể khiến hai định danh từng khác nhau trông giống nhau. Nếu cần xác thực chữ ký, khóa hoặc cấu trúc, dùng strict decoder/encoder và bác bỏ dữ liệu không hợp lệ.

## 9. Làm việc với file và stream trong ứng dụng

Khi cần đọc văn bản từ file theo UTF-8 và **báo lỗi nếu byte sai**, có thể truyền decoder cấu hình tường minh cho `InputStreamReader`:

~~~java
CharsetDecoder strictUtf8 = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(
        Files.newInputStream(path), strictUtf8)) {
    // Đọc reader bằng một buffer ký tự.
}
~~~

Đây là **đoạn minh họa**, cần `java.nio.file.Files`, `Path path`, `java.io.Reader`, `java.io.InputStreamReader` và các import charset tương ứng. `try-with-resources` giúp đóng reader và stream nền khi hoàn tất hoặc gặp lỗi. Các lỗi giải mã sẽ được báo qua cơ chế I/O của reader thay vì tự động biến input malformed thành văn bản hợp lệ.

Chiều ghi, muốn buộc charset đầu ra là US-ASCII và **từ chối ký tự không ánh xạ được**:

~~~java
CharsetEncoder strictAscii = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(
        Files.newOutputStream(path), strictAscii)) {
    writer.write(text);
}
~~~

Đây cũng là **đoạn minh họa**, cần `java.io.Writer`, `java.io.OutputStreamWriter`, `Path path` và `String text`. Trong thực tế, dùng **UTF-8** cho giao thức mới trừ khi đặc tả buộc một bảng mã hẹp hơn. Không đổi charset đầu ra chỉ để tránh một lỗi dữ liệu mà đặc tả bắt buộc xử lý đúng.

**Phân biệt:** cung cấp `CharsetDecoder`/`CharsetEncoder` đã cấu hình khác với chỉ cung cấp `Charset` cho constructor. Đừng mặc định mọi overload của Reader/Writer có cùng chính sách với một coder strict mà bạn tự tạo.

### 9.1. Không phụ thuộc charset mặc định của hệ thống

Tốt:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
~~~

Đây là các đoạn minh họa với biến `bytes`. Chúng **chỉ rõ charset**, tốt hơn việc ngầm dựa vào mặc định môi trường. Tuy nhiên, các API tiện dụng này **có thể thay thế dữ liệu không hợp lệ**, nên **không thay thế strict codec** khi dữ liệu cần được kiểm chứng.

Tách hai quyết định:

1. **Charset gì?** Ví dụ UTF-8, US-ASCII, UTF-16 theo giao thức.
2. **Làm gì khi input sai/không mã hóa được?** `REPORT`, `REPLACE` hoặc `IGNORE`.

Chỉ nói “dùng UTF-8” chưa đủ để giải thích chính sách chấp nhận dữ liệu lỗi.

## 10. Thiết kế xử lý lỗi, logging và tính toàn vẹn dữ liệu

### 10.1. Khuyến nghị chọn action theo mục đích

| Mục đích | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Import dữ liệu được ràng buộc bởi đặc tả UTF-8 hợp lệ | `REPORT` | Phát hiện sai lệch sớm, không âm thầm làm hỏng dữ liệu |
| Dữ liệu dùng định danh, cấu hình quan trọng hoặc quy tắc kinh doanh | `REPORT` | Không để replacement/ignore làm biến đổi giá trị |
| Hiển thị một đoạn văn do bên ngoài gửi tới mà người dùng vẫn cần đọc phần hợp lệ | `REPLACE` nếu sản phẩm cho phép | Tránh thất bại toàn màn hình, nhưng phải hiểu dữ liệu đã mất |
| Trích xuất văn bản phụ, chấp nhận bỏ đoạn sai theo hợp đồng rất rõ | `IGNORE` có kiểm soát | Dữ liệu có thể mất hoàn toàn ở vị trí lỗi, không còn dấu vết |
| Mã hóa văn bản Unicode sang US-ASCII | `REPORT` hoặc chuyển sang UTF-8 theo đặc tả | Tránh thay `é`, tiếng Việt hoặc emoji thành `?` tùy ý |
| Stream chia khối qua ranh giới của một ký tự | `decode(..., false)` cho khối chưa cuối, giữ input còn lại | Không báo nhầm malformed khi mới chỉ thiếu byte |
| Dữ liệu kết thúc khi còn thiếu byte/surrogate | Gọi lần cuối với `endOfInput=true` | Khi EOF thật, sequence không hoàn chỉnh mới là lỗi |
| Cần chẩn đoán lỗi codec trong pipeline | Ghi charset, loại lỗi, offset/độ dài và nguồn dữ liệu phù hợp | Tránh chỉ log replacement text làm mất nguyên nhân |

### 10.2. Đừng đồng nhất validation với Unicode normalization

Một chuỗi có thể **giải mã UTF-8 hợp lệ** nhưng vẫn chứa ký tự không mong muốn theo nghiệp vụ. Các bước khác có thể cần:

- Kiểm tra cú pháp/độ dài/biên giới trường theo đặc tả.
- Kiểm tra ký tự điều khiển, ký tự không cho phép, hoặc chính sách nhập tên/định danh.
- Cân nhắc Unicode normalization khi đặc tả yêu cầu — đó **không phải** nhiệm vụ của `CharsetDecoder`/`CharsetEncoder`.
- Nếu làm việc với chữ ký số hoặc hash, xác định dữ liệu ký/hash là **byte thô** hay text đã chuẩn hóa. Không tự ý decode với `REPLACE` trước khi xác thực.

Một decoder strict chỉ bảo đảm input hợp lệ theo **charset**, không chứng minh dữ liệu an toàn cho SQL, HTML, URL, path hay nghiệp vụ. Những tầng đó cần kiểm tra/escaping/parameterization riêng.

### 10.3. Phân biệt thất bại codec với thiếu dung lượng buffer

`OVERFLOW` trong `CoderResult` **không phải** lỗi input không hợp lệ. Nó chỉ cho biết buffer output đã đầy. Nếu hệ thống ném lỗi dữ liệu khi `OVERFLOW`, sẽ bác bỏ những input hoàn toàn hợp lệ chỉ vì chọn buffer nhỏ.

Ngược lại, `UNDERFLOW` cũng không tự chứng minh mọi input đã được giải mã trọn vẹn: nó có thể báo đang thiếu byte/surrogate và cần chờ khối tiếp theo. Cần xét **`remaining()`**, trạng thái EOF và thứ tự `flush`.

### 10.4. Quản lý exception và retry

- Với API trọn gói strict, bắt hoặc khai báo `CharacterCodingException`. Phân biệt subtype `MalformedInputException` và `UnmappableCharacterException` nếu chính sách xử lý khác nhau.
- Với API tăng dần, khi `CoderResult.isError()`, có thể gọi `throwException()` để nhận ngoại lệ tương ứng hoặc xử lý bằng policy rõ ràng.
- Khi một lần decoding đã thất bại, không nên cố tiếp tục trên **cùng coder đang ở trạng thái không xác định đối với nghiệp vụ** mà không có quy trình recovery chuẩn. Có thể phải `reset()` và chạy lại từ input sạch.
- Nếu log byte lỗi, tránh ghi thông tin nhạy cảm hoặc dữ liệu nhị phân toàn bộ. Log một **vị trí byte**, tên charset, độ dài lỗi và một đoạn bối cảnh đã được kiểm soát thường hữu ích hơn.

### 10.5. Thread safety và tái sử dụng

`CharsetDecoder` và `CharsetEncoder` là các đối tượng **stateful và không an toàn cho nhiều thread sử dụng đồng thời**. Tạo mới cho mỗi phiên chuyển đổi hoặc quản lý ownership sao cho mỗi instance chỉ được dùng tuần tự, tuân thủ `reset → input → final → flush`.

Một instance không được dùng để xử lý đồng thời hai luồng byte riêng biệt chỉ vì chúng cùng charset UTF-8. Chính `StandardCharsets.UTF_8` là đối tượng biểu diễn charset và có thể dùng để tạo coder mới; **coder mới** mới là đối tượng chứa trạng thái.

## 11. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gọi `new String(bytes, UTF_8)` rồi khẳng định bytes chắc chắn hợp lệ | Constructor thay malformed bằng replacement | Dùng `UTF_8.newDecoder().onMalformedInput(REPORT).decode(...)` |
| Cho rằng `REPLACE` giữ nguyên dữ liệu | Byte/ký tự lỗi đã bị thay và không khôi phục nguyên bản | Chỉ dùng khi mất dữ liệu được chấp nhận |
| Dùng `IGNORE` để sửa mọi input | Bỏ mất dữ liệu, có thể làm thay ý nghĩa identifier | Ưu tiên `REPORT`; nếu ignore phải có lý do nghiệp vụ |
| Chỉ cấu hình `onMalformedInput` | Lỗi `unmappable` vẫn theo action riêng | Thiết lập cả hai action khi cần một chính sách đầy đủ |
| Coi `C3 28` là unmappable | Nhầm cấu trúc UTF-8 sai với ký tự không biểu diễn được | Đây là **malformed** UTF-8 |
| Coi `é` trong US-ASCII là malformed Unicode | Phân loại lỗi sai | Đây là **unmappable** vì `é` hợp lệ nhưng không có byte US-ASCII |
| Dùng replacement bytes `EF BF BD` cho mọi encoder | Không hợp lệ với charset hẹp | `replaceWith(byte[])` phải dùng chuỗi byte hợp lệ của charset đó |
| Tách byte stream thành các chunk rồi decode mỗi chunk bằng decoder mới | Phá vỡ ký tự UTF-8 nhiều byte giữa chunk | Dùng một decoder tăng dần, giữ các byte chưa xử lý |
| Nhận `UNDERFLOW` với input còn byte rồi bỏ chúng | Mất các byte ở đầu một sequence chưa hoàn tất | `compact()` giữ input còn lại, sau đó nạp thêm |
| Nhận `OVERFLOW` rồi báo malformed | Nhầm thiếu chỗ output với lỗi dữ liệu | Drain/output buffer và gọi coder tiếp |
| Không gọi `endOfInput=true` cuối cùng | Không kiểm tra sequence thiếu byte ở EOF | Kết thúc phiên đúng trạng thái, rồi `flush` |
| Gọi lại coder sau khi hoàn tất mà không `reset()` | Có thể `IllegalStateException` hoặc sai trạng thái | Tạo coder mới hoặc reset trước phiên mới |
| Share một encoder/decoder cho nhiều luồng cùng lúc | Race condition và trạng thái bị trộn | Mỗi phiên độc lập dùng một coder |
| Chỉ kiểm tra charset nhưng quên kiểm tra dữ liệu nghiệp vụ | Text hợp lệ UTF-8 vẫn có thể sai schema | Validation và security xử lý tầng riêng |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Khi decoder UTF-8 nhận byte `C3` rồi `28`, đây là malformed hay unmappable? Vì sao?

**Đáp án:** **Malformed**, vì `28` không phải UTF-8 continuation byte hợp lệ cho `C3`; cấu trúc chuỗi byte không phù hợp UTF-8.

**Câu 2.** Khi encoder US-ASCII nhận ký tự `é`, `REPORT` báo lỗi nào?

**Đáp án:** `UnmappableCharacterException` vì ký tự Unicode `é` hợp lệ nhưng US-ASCII không có mã tương ứng.

**Câu 3.** `REPLACE` và `IGNORE` có thể tạo ra cùng chuỗi byte gốc khi round-trip không?

**Đáp án:** Không thể bảo đảm. Cả hai chính sách đều có thể mất thông tin gốc; replacement làm thay dữ liệu, ignore bỏ dữ liệu. Chỉ sử dụng khi chấp nhận tính *lossy*.

**Câu 4.** Tại sao một decoder mới mặc định `REPORT` nhưng `new String(bytes, UTF_8)` có thể tạo ra `U+FFFD` mà không ném?

**Đáp án:** Chúng là **API khác nhau với hợp đồng xử lý lỗi khác nhau**. Đối tượng `CharsetDecoder` mới mặc định strict; constructor `String` với charset cụ thể được thiết kế để thay malformed/unmappable thay vì báo checked exception.

**Câu 5.** Một chunk UTF-8 chứa `E2 82` và server vẫn còn truyền dữ liệu. Có được báo malformed ngay khi `decode(..., false)` trả `UNDERFLOW` với 2 byte còn lại không?

**Đáp án:** Không. Cần giữ byte chưa xử lý và chờ chunk có `AC` để hoàn tất `€`. Nếu EOF thật xảy ra mà không có byte cuối, lần `decode(..., true)` với `REPORT` sẽ báo malformed.

**Câu 6.** Decoder tăng dần trả `OVERFLOW` nhưng input vẫn còn. Nên làm gì?

**Đáp án:** Tiêu thụ/ghi những ký tự đã có trong output buffer, chuẩn bị lại chỗ trống và **gọi `decode` tiếp**. `OVERFLOW` không phải lỗi mã hóa.

**Câu 7.** Decoder và encoder dùng `replaceWith` với cùng kiểu tham số không?

**Đáp án:** Không. Decoder dùng `replaceWith(String)`; encoder dùng `replaceWith(byte[])`. Byte replacement phải hợp lệ trong charset đích.

**Câu 8.** `CharsetEncoder` gặp lone high surrogate `\\uD800` ở cuối input và charset UTF-8. `REPORT` báo gì?

**Đáp án:** `MalformedInputException` vì chuỗi UTF-16 đầu vào không well-formed; không phải `UnmappableCharacterException`.

**Câu 9.** Có thể dùng chung một `CharsetDecoder` cho hai HTTP requests cùng lúc nếu cả hai đều là UTF-8 không?

**Đáp án:** Không an toàn; coder có trạng thái và không thread-safe. Nên tạo decoder riêng cho từng phiên, hoặc bảo vệ việc sử dụng tuần tự và `reset()` thích hợp.

## 13. Checklist và tài liệu chính thức

- [ ] Chọn charset tường minh, ví dụ `StandardCharsets.UTF_8`, không phụ thuộc charset mặc định.
- [ ] Phân biệt `malformed` (đầu vào sai cấu trúc) với `unmappable` (đầu vào hợp lệ nhưng không ánh xạ được).
- [ ] Chọn `REPORT` nếu dữ liệu phải giữ nguyên/integrity quan trọng; `REPLACE`/`IGNORE` là quyết định chấp nhận mất dữ liệu.
- [ ] Thiết lập riêng `onMalformedInput` và `onUnmappableCharacter` theo hợp đồng.
- [ ] Nhớ decoder replacement là `String`, encoder replacement là `byte[]`; kiểm tra `isLegalReplacement` khi tùy chỉnh byte replacement.
- [ ] Dùng `CharsetDecoder.decode(ByteBuffer)` / `CharsetEncoder.encode(CharBuffer)` cho dữ liệu trọn gói cần kiểm soát exception.
- [ ] Với streaming, bảo toàn input còn lại qua `compact()`, xử lý `UNDERFLOW`/`OVERFLOW` đúng nghĩa.
- [ ] Gọi `endOfInput=true` ở lần cuối và `flush` sau đó; `reset` trước phiên mới.
- [ ] Không share một coder có trạng thái cho nhiều luồng.
- [ ] Không tự coi Unicode hợp lệ là dữ liệu an toàn theo nghiệp vụ; validation và escaping ở tầng riêng.
- [ ] Dùng `javac --release 21 -Xlint:all` và đối chiếu stdout các trường hợp lỗi/không lỗi.

**Tài liệu chính thức (API còn áp dụng trong Java hiện đại):**

- [Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): decode, malformed/unmappable, replacement, trình tự streaming và thread safety.
- [Java SE 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html): encode, `replaceWith(byte[])`, `isLegalReplacement(...)` và `flush`.
- [Java SE 21 — CodingErrorAction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE`, `IGNORE`.
- [Java SE 21 — CoderResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CoderResult.html): `UNDERFLOW`, `OVERFLOW`, `isMalformed`, `isUnmappable` và `throwException`.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn không cần tra tên qua chuỗi tùy ý.
- [Java SE 21 — InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html) và [OutputStreamWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStreamWriter.html): tích hợp coder cấu hình riêng vào I/O.
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): phân biệt tiện ích chuyển đổi byte/charset với strict coder.

**Kết luận:** `CharsetDecoder` và `CharsetEncoder` giúp biến chuyện “dữ liệu mã hóa sai” thành một **chính sách rõ ràng**. `REPORT` bảo toàn yêu cầu tính hợp lệ, `REPLACE` thay thế có mất mát, `IGNORE` loại bỏ dữ liệu. Với streaming, cần xử lý đủ input chưa hoàn chỉnh, output buffer, EOF và flush. Đây là những kiến thức vẫn dùng trực tiếp trên JDK hiện đại, không phải quy trình legacy.
