# Chuỗi escape không hợp lệ và `IllegalArgumentException` khi giải mã dữ liệu biểu mẫu

*Ngữ cảnh Java 10 — Mã hóa dữ liệu biểu mẫu. Bài học dùng `java.net.URLDecoder` và `URLEncoder` với overload nhận `Charset` được bổ sung từ Java 10; đối chiếu hành vi với tài liệu Java hiện hành và ví dụ Java 17+ chạy được. Trọng tâm: **khi nào chuỗi `%HH` sai cú pháp**, khi nào xảy ra `IllegalArgumentException`, và tại sao byte UTF-8 lỗi là một trường hợp khác.*

## 1. Kết luận nhanh

Dữ liệu HTML form kiểu `application/x-www-form-urlencoded` sử dụng một quy tắc escape đặc biệt:

- Dấu `+` biểu diễn **dấu cách** U+0020.
- Chuỗi `%HH` biểu diễn **một byte**, trong đó `H` là **một chữ số hexadecimal ASCII** thuộc `0–9`, `A–F` hoặc `a–f`.
- Một hoặc nhiều byte được percent-encode liền nhau có thể tạo thành ký tự Unicode theo charset được chỉ định, thông thường là **UTF-8**.
- Dấu phần trăm muốn xuất hiện như dữ liệu thường phải được encode thành `%25`.
- Dấu cộng thật muốn xuất hiện trong giá trị phải được encode thành `%2B`.

Ví dụ:

~~~java
String value = URLDecoder.decode("name=Lan+Anh%26Co", StandardCharsets.UTF_8);
// Kết quả: "name=Lan Anh&Co"
~~~

Trên các triển khai OpenJDK hiện hành, những escape sai cú pháp như `"%"`, `"%A"`, `"%GG"` thường khiến `URLDecoder.decode(...)` ném **`IllegalArgumentException`**. Javadoc chung vẫn lưu ý cách xử lý chuỗi escape bất hợp lệ có thể tùy implementation: một implementation có thể để nguyên chuỗi bất hợp lệ hoặc ném ngoại lệ. Vì vậy, **đừng tuyên bố mọi implementation Java chắc chắn ném cùng một lỗi cho từng chuỗi bất hợp lệ**.

Một phân biệt rất quan trọng:

- `"%GG"`: **sai cú pháp percent-escape**, vì `G` không phải chữ số hex → trên OpenJDK thông dụng ném `IllegalArgumentException`.
- `"%C3%28"`: **đúng cú pháp percent-escape** vì `C3` và `28` đều là hex hợp lệ, nhưng các byte ấy **không tạo thành chuỗi UTF-8 hợp lệ** → `URLDecoder.decode(..., UTF_8)` có thể trả về ký tự thay thế `U+FFFD`, **không nhất thiết ném `IllegalArgumentException`**.

Điều đó ảnh hưởng trực tiếp tới validation, bảo mật, xử lý lỗi HTTP 400 và kiểm thử.

## 2. Đúng bối cảnh: form encoding chứ không phải mọi loại URL

`URLDecoder` là bộ giải mã **HTML form**; nó không phải một bộ giải mã chung cho tất cả các thành phần URI. Tên đầy đủ trong Java:

~~~java
java.net.URLDecoder
java.net.URLEncoder
~~~

Các API này hỗ trợ `application/x-www-form-urlencoded`, thường gặp ở thân form POST hoặc query string được xử lý theo quy ước form. Ngữ nghĩa của ký tự `+` là điểm khác biệt đáng nhớ:

~~~java
URLDecoder.decode("a+b", StandardCharsets.UTF_8);   // "a b"
URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8); // "a+b"
~~~

Trong một đường dẫn URL thông thường, `+` không tự mặc định tương đương dấu cách theo quy tắc của `URLDecoder`. Đưa nguyên đường dẫn, fragment hoặc URL đầy đủ vào `URLDecoder` có thể làm **thay đổi dữ liệu không mong muốn**. Hãy dùng API URI/framework tương ứng với thành phần URI cần xử lý; chỉ dùng form decoder cho **giá trị thực sự được form-encode**.

**Đặc biệt:** URL query string là một cấu trúc gồm **tên tham số và giá trị**, thường có dấu `&` và `=` làm delimiters. `URLDecoder` chỉ giải mã **một chuỗi theo quy tắc form**, không tự xác định đâu là tên tham số, đâu là giá trị hay đâu là dấu phân cách thực sự.

## 3. Quy tắc `%HH`: ký tự `%` không phải dữ liệu thường

Dạng hợp lệ:

~~~text
%20  -> byte 0x20  -> dấu cách trong UTF-8
%2B  -> byte 0x2B  -> dấu cộng +
%25  -> byte 0x25  -> dấu %
%26  -> byte 0x26  -> dấu &
%3D  -> byte 0x3D  -> dấu =
%C3%A9 -> bytes C3 A9 -> ký tự é trong UTF-8
~~~

Hai vị trí sau `%` **phải tồn tại** và phải là chữ số hex hợp lệ. Do đó:

~~~text
%          Thiếu cả hai chữ số hex
%2         Thiếu chữ số hex thứ hai
%A         Thiếu chữ số hex thứ hai
%GG        G không phải chữ số hex
%2Z        Z không phải chữ số hex
%Z2        Z không phải chữ số hex
%u0041     Không phải cú pháp %HH; %u không hợp lệ trong form encoding
~~~

**Không có escape `%uXXXX` trong quy tắc HTML form encoding.** Đây là điểm dễ nhầm với một số dạng escape của ngôn ngữ lập trình hoặc cú pháp lịch sử không thuộc chuẩn xử lý biểu mẫu. Để encode Unicode, cần mã hóa ký tự thành **byte theo charset**, sau đó percent-encode từng byte cần escape.

Ví dụ chữ `é` trong UTF-8:

~~~text
é  -> UTF-8: C3 A9  -> %C3%A9
~~~

Không encode thành `%u00E9` rồi yêu cầu `URLDecoder` hiểu như JavaScript Unicode escape.

### 3.1. Hex chữ hoa và chữ thường

Cả `%2B` và `%2b` đều hợp lệ: chữ hex `A–F` và `a–f` biểu diễn cùng giá trị nibble. Trong một hệ thống muốn canonical encoding, có thể chuẩn hóa cách viết, nhưng **việc viết hoa chữ hex không phải điều kiện để decode hợp lệ**.

### 3.2. Dấu phần trăm trong dữ liệu phải được encode

~~~java
var raw = "discount=20%";
var encoded = URLEncoder.encode(raw, StandardCharsets.UTF_8);
// "discount%3D20%25"
~~~

Nếu gửi trực tiếp `"discount=20%"` như một thành phần form-encoded cần giải mã, ký tự `%` ở cuối có thể bị xem là mở đầu một escape thiếu dữ liệu. Đừng dùng thao tác thay chuỗi `" " -> "+"` như một bộ encoder: nó không xử lý được dấu phần trăm, dấu cộng và các ký tự khác.

## 4. `URLDecoder.decode(String, Charset)` — overload Java 10 còn áp dụng

Với Java 10 trở lên, có thể chỉ rõ charset bằng một object kiểu `Charset`:

~~~java
String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
~~~

Chữ ký:

~~~java
public static String decode(String s, Charset charset)
~~~

Nó nằm trong `java.net.URLDecoder` và **không khai báo checked exception**. Khi chuỗi escape sai cú pháp và implementation quyết định từ chối, caller có thể nhận `IllegalArgumentException`.

Các trường hợp khác:

- `s == null` → `NullPointerException`.
- `charset == null` → `NullPointerException`.
- `s` hợp lệ về cú pháp nhưng chứa byte không giải mã hợp lệ theo charset → **chính sách thay thế ký tự lỗi** của phương thức; không đồng nhất với lỗi percent-escape.
- `s` rỗng → kết quả là chuỗi rỗng.
- Một dấu `+` không có percent-escape vẫn được đổi thành dấu cách khi decode form.

So với overload cũ:

~~~java
URLDecoder.decode(encoded, "UTF-8");
~~~

Dạng nhận `String enc` vẫn tồn tại và có thể ném checked `UnsupportedEncodingException` khi tên encoding không được hỗ trợ. Dạng nhận `Charset` có ưu điểm dùng hằng được compiler nhận biết, ví dụ `StandardCharsets.UTF_8`, và tránh lookup tên charset bằng chuỗi.

Overload không chỉ định charset:

~~~java
URLDecoder.decode(encoded);
~~~

đã bị **deprecated**, vì kết quả có thể phụ thuộc charset mặc định. Bài học hiện hành nên ưu tiên overload nhận `Charset`, nhất là đối với giao thức có encoding xác định. Không nên nhầm `IllegalArgumentException` do percent sai với `UnsupportedEncodingException` của overload nhận tên charset.

## 5. Phân biệt ba loại vấn đề thường bị gộp nhầm

| Tình huống | Ví dụ | Ý nghĩa | Xử lý |
| --- | --- | --- | --- |
| **Escape sai cú pháp** | `"%GG"` | Không thể đọc thành một byte hex | Trên OpenJDK ném `IllegalArgumentException`; kiểm tra grammar nếu cần quy tắc độc lập implementation |
| **Escape thiếu chữ số** | `"abc%"`, `"abc%4"` | Một `%` không đi kèm đủ hai nibble | Trên OpenJDK ném `IllegalArgumentException` |
| **Escape hợp lệ, byte charset sai** | `"%C3%28"` dùng UTF-8 | Hai triplet đều hợp lệ, nhưng byte sequence không phải UTF-8 hợp lệ | `URLDecoder` có thể thay bằng `U+FFFD`; dùng strict `CharsetDecoder` nếu yêu cầu từ chối |
| **Escape hợp lệ, byte điều khiển** | `"%00"` | Byte NUL là giá trị percent hợp lệ | Decode có thể tạo ký tự điều khiển; validation nghiệp vụ phải tự quyết định chấp nhận |
| **Dữ liệu được decode hai lần** | `"%252B"` | Lần 1 ra `"%2B"`, lần 2 ra `"+"` | Decode đúng một lần ở ranh giới form; tránh double decoding |
| **Dùng sai bối cảnh** | `"a+b"` là một path literal | `URLDecoder` đổi `+` thành space | Không dùng form decoder cho URL path nói chung |
| **Charset khác với nguồn** | `"%E9"` nhưng dùng UTF-8 thay vì ISO-8859-1 | Byte hợp lệ về percent nhưng không phù hợp encoding được cho | Xác định charset theo hợp đồng, không đoán ngẫu nhiên |

Từ bảng trên, `IllegalArgumentException` không phải một công cụ phát hiện **tất cả** văn bản lỗi và cũng không phải một sanitizer. Nó xử lý một nhóm lỗi cú pháp theo implementation. Với dữ liệu đầu vào quan trọng, cần validation theo lớp.

### 5.1. Không coi `%00` là một malformed escape

~~~java
String value = URLDecoder.decode("%00", StandardCharsets.UTF_8);
// value chứa U+0000, không phải chuỗi rỗng.
~~~

Byte `00` là hexadecimal hợp lệ. Nếu ứng dụng không cho control characters trong tên file, token, mã sản phẩm hoặc dữ liệu đăng nhập, phải **kiểm tra sau decode**, không dựa vào ngoại lệ của URLDecoder. Điều tương tự áp dụng cho một số ký tự phân cách/điều khiển khác được percent-encode hợp lệ.

### 5.2. Không dựa vào nội dung thông báo của ngoại lệ

`IllegalArgumentException` là loại exception hữu ích để phát hiện lỗi, nhưng **thông báo lỗi** có thể khác giữa phiên bản JDK/implementation. Không nên:

~~~java
if (e.getMessage().contains("hex")) {
    // Quyết định nghiệp vụ quan trọng dựa trên thông báo.
}
~~~

Thay vào đó, bắt đúng loại ngoại lệ, ghi nhận mã lỗi nội bộ theo chính sách và trả thông báo an toàn cho người gửi. Khi cần phân loại chi tiết “thiếu hai chữ số” với “không phải hex”, sử dụng **validator riêng** với mã lỗi ổn định.

## 6. Vì sao `%C3%28` không giống `%GG`?

Xét hai đầu vào:

~~~text
%GG
%C3%28
~~~

Với `%GG`, không thể đổi `GG` thành byte — đây là lỗi ở bước **phân tích percent-escape**.

Với `%C3%28`:

- `%C3` → byte `C3`.
- `%28` → byte `28` (ký tự `(` ở bảng ASCII).
- Hai byte này không phải một chuỗi UTF-8 hợp lệ vì byte `C3` cần một byte tiếp diễn phù hợp, nhưng `28` không phải continuation byte.

Tài liệu Java hiện hành của `URLDecoder.decode(String,Charset)` ghi rằng **byte lỗi được thay bằng giá trị thay thế của Charset**. Ví dụ:

~~~java
var decoded = URLDecoder.decode("%C3%28", StandardCharsets.UTF_8);
System.out.println(decoded.equals("\uFFFD(")); // true trên JDK được kiểm thử
~~~

Ký tự `\uFFFD` là **Unicode Replacement Character**. Sự hiện diện của ký tự này không phải lúc nào cũng chứng minh byte đầu vào lỗi: một client có thể gửi **chính ký tự U+FFFD hợp lệ** dưới dạng `%EF%BF%BD`. Vì vậy, không nên xây một bộ phân tích UTF-8 strict chỉ bằng cách kiểm tra `result.contains("\uFFFD")`; cách ấy có thể từ chối dữ liệu hợp lệ.

Muốn phân biệt một chuỗi byte UTF-8 bị hỏng với một chuỗi Unicode U+FFFD được gửi hợp lệ, phải kiểm tra **chính bytes** bằng `CharsetDecoder` với hành động `CodingErrorAction.REPORT`, thay vì chỉ nhìn kết quả String đã qua cơ chế replacement.

## 7. Xử lý ngoại lệ bằng `try/catch` và trả lỗi đầu vào hợp lý

Một ví dụ rất thường gặp ở tầng nhận request:

~~~java
static String decodeFormField(String encoded) {
    try {
        return URLDecoder.decode(encoded, StandardCharsets.UTF_8);
    } catch (IllegalArgumentException malformedEscape) {
        throw new BadRequestException("Malformed form encoding", malformedEscape);
    }
}
~~~

Đây là **pseudocode tích hợp**: `BadRequestException` phải là exception do framework/ứng dụng định nghĩa để trả HTTP 400; nó **không phải class có sẵn trong Java SE**. Ví dụ đầy đủ chạy độc lập bên dưới dùng `IllegalArgumentException` để tránh phụ thuộc framework.

Chính sách xử lý nên gồm:

1. **Chỉ decode một trường có đúng bối cảnh form-encoding.**
2. **Chỉ rõ Charset**, thông thường UTF-8.
3. **Bắt `IllegalArgumentException` cho escape sai** nếu implementation ném; không bắt chung mọi `RuntimeException` rồi che lỗi lập trình không liên quan.
4. **Xác thực giới hạn độ dài và format nghiệp vụ**: null/blank, phạm vi ký tự, dấu phân cách, mã sản phẩm, email, v.v.
5. **Quyết định chính sách malformed UTF-8**: chấp nhận replacement hay từ chối. Nếu phải từ chối, dùng decoder strict phù hợp.
6. **Đảm bảo không decode lần thứ hai** sau khi middleware/framework đã decode cho bạn.
7. **Không lộ thông tin nhạy cảm trong logs**; một input form có thể chứa token, mật khẩu hoặc dữ liệu cá nhân. Log mã lỗi, vị trí không nhạy cảm hoặc thông tin đã được che theo chính sách.

Với API web, phản hồi thích hợp thường là lỗi client input như **400 Bad Request**. Tuy nhiên, ứng dụng/framework có thể đã tự parse form và trả lỗi trước khi code của bạn chạy; không nhất thiết phải tự gọi URLDecoder trong controller.

## 8. Viết bộ kiểm tra nghiêm ngặt cho percent-escape và UTF-8

Khi nghiệp vụ yêu cầu **từ chối** cả percent sai và byte UTF-8 sai (thay vì cho ký tự thay thế), có thể triển khai hai kiểm tra:

- **Grammar percent-escape**: một `%` phải được theo sau bởi chính xác hai chữ số **hex ASCII**.
- **Decode bytes strict**: dùng `CharsetDecoder` với `onMalformedInput(REPORT)` và `onUnmappableCharacter(REPORT)`.

Mẫu dưới đây minh họa một **bộ giải mã cho một giá trị form đã được tách khỏi cấu trúc query**, không thay thế toàn bộ parser HTTP hay framework, không tự xử lý charset không phải UTF-8. Nó giữ `+` thành space và dùng các cụm `%HH` liên tiếp như một dãy byte UTF-8:

~~~java
static int asciiHex(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static String decodeStrictUtf8Form(String formValue) {
    if (formValue == null) {
        throw new NullPointerException("formValue");
    }
    StringBuilder text = new StringBuilder();
    for (int i = 0; i < formValue.length();) {
        char c = formValue.charAt(i);
        if (c == '+') {
            text.append(' ');
            i++;
            continue;
        }
        if (c != '%') {
            text.append(c);
            i++;
            continue;
        }

        var bytes = new ByteArrayOutputStream();
        while (i < formValue.length() && formValue.charAt(i) == '%') {
            if (i + 2 >= formValue.length()) {
                throw new IllegalArgumentException("Incomplete %HH escape");
            }
            int hi = asciiHex(formValue.charAt(i + 1));
            int lo = asciiHex(formValue.charAt(i + 2));
            if (hi < 0 || lo < 0) {
                throw new IllegalArgumentException("Non-hexadecimal %HH escape");
            }
            bytes.write((hi << 4) | lo);
            i += 3;
        }

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            text.append(decoder.decode(ByteBuffer.wrap(bytes.toByteArray())));
        } catch (CharacterCodingException failure) {
            throw new IllegalArgumentException("Invalid UTF-8 escape bytes", failure);
        }
    }
    return text.toString();
}
~~~

Đây là **hai phương thức trong một lớp**, cần import `ByteArrayOutputStream`, `ByteBuffer`, `StandardCharsets`, `CodingErrorAction`, `CharacterCodingException`. Chương trình runnable ở mục 9 sử dụng chính cách viết này.

**Vì sao dùng `asciiHex` mà không dùng bừa `Character.digit(c,16)`?** Một số phương thức nhận biết chữ số Unicode ngoài ASCII, trong khi cú pháp percent-escape của form phải dùng chữ số hex **ASCII**. `asciiHex` tránh vô tình chấp nhận ký tự giống hex nhưng không thuộc grammar percent.

**Giới hạn của ví dụ:** Phương thức này nhận **một String đã có** và minh họa kiểm tra các chuỗi escape, không tự parse delimiters của `a=b&c=d` và không thực thi tất cả giới hạn ứng dụng (độ dài, ký tự điều khiển, canonical encoding, v.v.). Nó giữ nguyên ký tự không bị percent-encode trong String nguồn; khi thiết kế parser nhận raw HTTP bytes, còn phải xác định đúng quy tắc chuyển raw bytes thành text. Nếu framework đã cung cấp giá trị form được decode sẵn, **không decode lần nữa**.

### 8.1. Vì sao bộ giải mã xử lý các escape liên tiếp thành một cụm?

Một ký tự Unicode có thể được biểu diễn bằng nhiều byte UTF-8. Ví dụ:

~~~text
%C3%A9 -> bytes C3 A9 -> é
%E2%82%AC -> bytes E2 82 AC -> ký tự €
%F0%9F%98%80 -> bytes F0 9F 98 80 -> một emoji Unicode
~~~

Nếu decode từng `%HH` riêng lẻ thành một String UTF-8 rồi nối lại, các byte dẫn và byte tiếp diễn sẽ bị tách rời — dẫn tới lỗi. Vì vậy cần gom các escape liên tiếp thành một `byte[]` và decode **một lần cho cả cụm**.

Trong parser chuyên nghiệp, một cách hiện thực khác là nhận thẳng byte gốc theo quy tắc form của framework/protocol và decode toàn bộ theo charset được chỉ định; ví dụ này chỉ phục vụ minh họa nguyên tắc ở Java SE.

### 8.2. Có cần tự viết decoder ở mọi ứng dụng không?

**Không.** Với web framework hiện hành, ưu tiên dùng parser form chuẩn của framework thay vì tự ghép các quy tắc percent. Chỉ viết/customize một decoder strict khi yêu cầu thực sự bắt buộc, và phải kiểm thử đầy đủ (đầu vào malformed, null, UTF-8 lỗi, Unicode hợp lệ, độ dài, các dấu phân cách, normalization). Tránh tạo parser riêng trùng lặp với parser chuẩn.

## 9. Chương trình Java 17+ hoàn chỉnh và đã kiểm thử

Đoạn sau dùng cả `URLEncoder` và `URLDecoder`, minh họa escape hợp lệ/sai, khác biệt giữa malformed percent và malformed UTF-8, một decoder strict, double decoding, ranh giới phân tách query và đầu vào null.

~~~java
// File: InvalidFormEscapeDemo.java
import java.io.ByteArrayOutputStream;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class InvalidFormEscapeDemo {

    static int asciiHex(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        return -1;
    }

    static String decodeStrictUtf8Form(String formValue) {
        if (formValue == null) {
            throw new NullPointerException("formValue");
        }
        StringBuilder text = new StringBuilder();

        for (int i = 0; i < formValue.length();) {
            char c = formValue.charAt(i);
            if (c == '+') {
                text.append(' ');
                i++;
                continue;
            }
            if (c != '%') {
                text.append(c);
                i++;
                continue;
            }
            var encodedBytes = new ByteArrayOutputStream();
            while (i < formValue.length() && formValue.charAt(i) == '%') {
                if (i + 2 >= formValue.length()) {
                    throw new IllegalArgumentException("Incomplete %HH escape");
                }
                int high = asciiHex(formValue.charAt(i + 1));
                int low = asciiHex(formValue.charAt(i + 2));
                if (high < 0 || low < 0) {
                    throw new IllegalArgumentException("Non-hexadecimal %HH escape");
                }
                encodedBytes.write((high << 4) | low);
                i += 3;
            }

            var decoder = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);
            try {
                text.append(decoder.decode(ByteBuffer.wrap(
                        encodedBytes.toByteArray())));
            } catch (CharacterCodingException malformedUtf8) {
                throw new IllegalArgumentException(
                        "Invalid UTF-8 escape bytes", malformedUtf8);
            }
        }
        return text.toString();
    }

    static void checkMalformedPercent(String raw) {
        try {
            URLDecoder.decode(raw, StandardCharsets.UTF_8);
            System.out.println(raw + " -> accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println(raw + " -> IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        String original = "a+b c&x=%";
        String encoded = URLEncoder.encode(original, StandardCharsets.UTF_8);
        System.out.println("encoded = " + encoded);
        System.out.println("round trip = " +
                original.equals(URLDecoder.decode(encoded, StandardCharsets.UTF_8)));
        System.out.println("form plus = " +
                URLDecoder.decode("a+b", StandardCharsets.UTF_8));
        System.out.println("escaped plus = " +
                URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8));
        System.out.println("escaped percent = " +
                URLDecoder.decode("%25", StandardCharsets.UTF_8));

        for (String malformed :
                new String[] {"%", "%2", "%GG", "%2Z", "a%u0041"}) {
            checkMalformedPercent(malformed);
        }

        String invalidUtf8 = URLDecoder.decode("%C3%28", StandardCharsets.UTF_8);
        System.out.println("malformed UTF8 replaced = " +
                invalidUtf8.equals("\uFFFD("));
        System.out.println("valid replacement code point = " +
                URLDecoder.decode("%EF%BF%BD", StandardCharsets.UTF_8)
                        .equals("\uFFFD"));

        try {
            decodeStrictUtf8Form("%C3%28");
            System.out.println("strict UTF8 rejected = false");
        } catch (IllegalArgumentException expected) {
            System.out.println("strict UTF8 rejected = true");
        }
        System.out.println("strict valid = " +
                decodeStrictUtf8Form("name=Lan+Anh%26Co")
                        .equals("name=Lan Anh&Co"));

        String once = URLDecoder.decode("%253Ctag%253E", StandardCharsets.UTF_8);
        String twice = URLDecoder.decode(once, StandardCharsets.UTF_8);
        System.out.println("first decode = " + once);
        System.out.println("second decode = " + twice);

        String rawQuery = "tag=Java%26Kotlin&x=1";
        System.out.println("raw query = " + rawQuery);
        System.out.println("decoded entire query = " +
                URLDecoder.decode(rawQuery, StandardCharsets.UTF_8));

        try {
            URLDecoder.decode(null, StandardCharsets.UTF_8);
            System.out.println("null input rejected = false");
        } catch (NullPointerException expected) {
            System.out.println("null input rejected = true");
        }
    }
}
~~~

Lưu tên tệp `InvalidFormEscapeDemo.java` và biên dịch bằng JDK 17+:

~~~bash
javac --release 17 InvalidFormEscapeDemo.java
java InvalidFormEscapeDemo
~~~

**Stdout đã xác nhận khi chạy trên OpenJDK/JDK 24 (target Java 17):**

~~~text
encoded = a%2Bb+c%26x%3D%25
round trip = true
form plus = a b
escaped plus = a+b
escaped percent = %
% -> IllegalArgumentException
%2 -> IllegalArgumentException
%GG -> IllegalArgumentException
%2Z -> IllegalArgumentException
a%u0041 -> IllegalArgumentException
malformed UTF8 replaced = true
valid replacement code point = true
strict UTF8 rejected = true
strict valid = true
first decode = %3Ctag%3E
second decode = <tag>
raw query = tag=Java%26Kotlin&x=1
decoded entire query = tag=Java&Kotlin&x=1
null input rejected = true
~~~

### 9.1. Phân tích kết quả

1. `URLEncoder.encode` chuyển dấu cộng thật thành `%2B`, dấu cách thành `+`, dấu `&` thành `%26`, dấu `=` thành `%3D` và dấu `%` thành `%25`. Giải mã bằng cùng UTF-8 trả đúng chuỗi ban đầu.
2. `"a+b"` trong form là `"a b"`; còn `"a%2Bb"` trả dấu `+` thật.
3. Năm chuỗi `%`, `%2`, `%GG`, `%2Z` và `a%u0041` đều bị OpenJDK ném `IllegalArgumentException` do percent-escape không đúng grammar.
4. `%C3%28` có hai escape hợp lệ nhưng byte UTF-8 sai. JDK giải mã thành `U+FFFD` rồi `(`, vì vậy biến `malformed UTF8 replaced` là `true`.
5. `%EF%BF%BD` mã hóa hợp lệ chính ký tự `U+FFFD`. Vì vậy không thể đánh giá dữ liệu malformed chỉ bằng việc nhìn thấy `U+FFFD` sau decode.
6. `decodeStrictUtf8Form` dùng `CodingErrorAction.REPORT` nên từ chối dãy byte UTF-8 sai. Chuỗi hợp lệ `name=Lan+Anh%26Co` vẫn decode đúng.
7. Dữ liệu `%253Ctag%253E` được decode một lần thành `%3Ctag%3E`, decode lần hai thành `<tag>`. Đây là minh họa vì sao **double decoding làm thay đổi nghĩa dữ liệu**, không phải một thao tác an toàn mặc định.
8. Decode **toàn bộ** `tag=Java%26Kotlin&x=1` làm `%26` thành ký tự `&` mới, có thể khiến một bộ parser thô phía sau hiểu sai cấu trúc tham số.
9. Truyền `null` làm đầu vào của overload nhận `Charset` ném `NullPointerException`, không phải `IllegalArgumentException`.

Phần in “accepted” trong `checkMalformedPercent` tồn tại để minh họa việc Javadoc để ngỏ cách ứng xử của implementation. Trên JDK đã kiểm thử, tất cả ví dụ malformed trong mảng đều in `IllegalArgumentException`; không suy rộng sang một bảo đảm tuyệt đối cho mọi triển khai.

## 10. Nguyên tắc parse query: phân tách cấu trúc trước, decode từng thành phần

Xét query thô:

~~~text
tag=Java%26Kotlin&x=1
~~~

Một parser đúng cần hiểu đó là:

~~~text
Tên tham số: tag
Giá trị encoded: Java%26Kotlin
Giá trị decoded: Java&Kotlin

Tên tham số: x
Giá trị encoded: 1
Giá trị decoded: 1
~~~

Nếu decode toàn bộ query trước:

~~~java
String wrong = URLDecoder.decode(
        "tag=Java%26Kotlin&x=1",
        StandardCharsets.UTF_8
);
// "tag=Java&Kotlin&x=1"
~~~

Sau đó chia `wrong` theo `&` thì ký tự `&` vốn thuộc **giá trị** sẽ bị hiểu nhầm là delimiter. Đây là lỗi parsing có thể làm sai số lượng và nội dung tham số.

Khi bắt buộc tự parse một query đơn giản, nguyên tắc là:

1. Dùng **chuỗi raw query chưa decode**.
2. Xác định các ranh giới `&` theo quy tắc của giao thức; một ký tự `%26` được xem là phần của giá trị encoded, **không phải** dấu phân tách thô.
3. Trong mỗi cặp tham số, tách theo dấu `=` phân cách **đầu tiên**; dấu `=` còn lại trong giá trị cần được xử lý theo hợp đồng.
4. Decode **tên và giá trị** riêng bằng UTF-8, mỗi phần **một lần**.
5. Quy định cách xử lý tham số trùng tên, giá trị rỗng, không có dấu `=`, độ dài và giới hạn số lượng tham số.

**Không dùng ví dụ này để xây HTTP parser production từ đầu.** Khi có framework Web, hãy để parser đã được kiểm chứng của framework xử lý `application/x-www-form-urlencoded` rồi nhận các tham số đã giải mã. Những framework khác nhau có thể áp dụng chính sách riêng về giá trị lỗi; cần xác định rõ boundary và không decode lặp lại.

## 11. Double decoding: input hợp lệ nhưng nhiều lần giải mã sẽ đổi nghĩa

`URLDecoder.decode` không phải một hàm idempotent. **Idempotent** nghĩa là áp dụng nhiều lần vẫn cùng kết quả; form decoder không có tính chất ấy.

~~~java
var once = URLDecoder.decode("%253Ctag%253E", StandardCharsets.UTF_8);
// "%3Ctag%3E"

var twice = URLDecoder.decode(once, StandardCharsets.UTF_8);
// "<tag>"
~~~

`%25` trong dữ liệu đầu vào chính là dấu phần trăm được mã hóa. Sau lần decode đầu, nó trở thành ký tự `%` trong giá trị **thật**, không có nghĩa ta phải diễn giải giá trị thật ấy như một encoded string mới.

### 11.1. Tại sao đây là vấn đề về bảo mật?

Một hệ thống có thể validate input ở một tầng, rồi lại decode nó ở tầng sau, làm input được kiểm tra ban đầu khác input được sử dụng cuối cùng. Một số ký tự đặc biệt như `<`, `>`, `/`, `&`, `=` hoặc ký tự điều khiển có thể thay đổi cách parser phía sau hiểu dữ liệu.

Biện pháp:

- Xác định **đúng một ranh giới decode**.
- Validate dựa trên **giá trị đã decode đúng một lần**.
- Tránh chuyển lại một String đã decode cho một hàm mong đợi encoded input.
- Khi xuất dữ liệu sang HTML, SQL, shell hoặc đường dẫn tệp, áp dụng **biện pháp escaping/parameterization theo ngữ cảnh đích**, chứ không trông chờ URL decoding làm dữ liệu “an toàn”.

`IllegalArgumentException` cho chuỗi malformed không ngăn được double decoding vì `%253C...` hoàn toàn hợp lệ về grammar. Hai lỗi này thuộc hai tầng khác nhau.

## 12. Tính đúng của charset và dữ liệu Unicode

Một percent-escaped byte chỉ có thể được hiểu là ký tự khi biết encoding. Đối với form hiện đại, UTF-8 thường là lựa chọn nên dùng; tuy nhiên, phải tuân theo hợp đồng cụ thể của hệ thống giao tiếp.

Ví dụ:

~~~text
%C3%A9 -> bytes C3 A9 -> é (UTF-8)
%E2%82%AC -> bytes E2 82 AC -> € (UTF-8)
%F0%9F%98%80 -> bytes F0 9F 98 80 -> emoji (UTF-8)
~~~

Trong UTF-8, một ký tự Unicode có thể cần nhiều byte. Vì thế không phải cứ có escape `%HH` hợp lệ về hex là kết quả giải mã thành Unicode hợp lệ. Nếu byte bị cắt mất hoặc bị trộn sai thứ tự, bộ giải mã strict có thể báo lỗi.

### 12.1. Không tự ý đổi charset để “hết lỗi”

Nếu byte nguồn được định nghĩa là UTF-8 nhưng có byte không hợp lệ, một ứng dụng không nên thử hết các charset cho đến khi nhận được chữ nhìn có vẻ hợp lý rồi chấp nhận. Điều này có thể tạo khác biệt diễn giải giữa các service và làm sai dữ liệu.

Đúng hơn:

- Xác định và tài liệu hóa charset ở giao diện nhận dữ liệu.
- Yêu cầu bên gửi tuân thủ.
- Với malformed byte sequences, quyết định **từ chối** hoặc **thay thế** có chủ đích; phải thống nhất ở các tầng.
- Nếu cần liên thông một nguồn legacy có charset khác, thiết kế bước chuyển đổi riêng và có test.

### 12.2. `null` là một loại lỗi khác

~~~java
URLDecoder.decode(null, StandardCharsets.UTF_8); // NullPointerException
URLDecoder.decode("%20", null);                   // NullPointerException
~~~

Đừng bắt mọi `NullPointerException` rồi nói “percent escape lỗi”: điều đó có thể che mất lỗi lập trình truyền tham số null. Trên API nhận request, cần kiểm tra trường bắt buộc có tồn tại, rỗng, null hay không; chỉ sau đó giải mã/validate nội dung.

## 13. `URLEncoder` giúp tránh tạo escape sai ngay từ đầu

Để chuyển một **giá trị thô** sang dạng form-encoded, nên dùng:

~~~java
String encoded = URLEncoder.encode(rawValue, StandardCharsets.UTF_8);
~~~

Không nên tự xây encoder bằng chuỗi thay thế:

~~~java
// Cách xử lý sai, chỉ minh họa ngộ nhận:
String encoded = rawValue.replace(" ", "+");
~~~

Cách sai ở trên bỏ sót ít nhất:

- Dấu cộng thật `+` sẽ bị `URLDecoder` hiểu thành space.
- Dấu phần trăm thật `%` có thể tạo escape thiếu chữ số.
- Dấu `&`/`=` có thể làm parser nhầm tên và giá trị.
- Ký tự Unicode phải được mã hóa thành byte theo charset rồi percent-encode phù hợp.

Ví dụ đúng:

~~~java
String rawValue = "a+b c&x=%";
String encoded = URLEncoder.encode(rawValue, StandardCharsets.UTF_8);
// "a%2Bb+c%26x%3D%25"

String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
// "a+b c&x=%"
~~~

**Không encode toàn bộ query string `a=1&b=2` như một giá trị duy nhất** khi bạn muốn giữ `&` và `=` là các dấu phân tách tham số. Encode riêng tên và giá trị, rồi ghép cặp theo quy tắc của format, hoặc dùng URI/form builder của framework.

## 14. Trả HTTP 400, lỗi hệ thống và logging

Khi một application server nhận form-encoded data không hợp lệ, có ba loại lỗi cần phân biệt:

| Phân loại | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| Client gửi escape malformed | `"user=%GG"` | Từ chối request hoặc trường đó, thường mã lỗi client như HTTP 400 |
| Client gửi byte theo encoding sai | `"%C3%28"` với hợp đồng UTF-8 strict | Từ chối khi chính sách yêu cầu UTF-8 hợp lệ, thay vì âm thầm sửa dữ liệu |
| Lỗi lập trình/config server | Truyền charset `null` hoặc decode lặp vô ý | Sửa code/config, không tự quy mọi lỗi thành dữ liệu client sai |

Không gửi stack trace của Java ra ngoài API cho client. Có thể trả thông báo trung tính:

~~~text
Invalid form encoding
~~~

Ở phía server, log theo tiêu chí điều tra được mà không để lộ dữ liệu bí mật. Ví dụ nên tránh log nguyên một chuỗi chứa access token hoặc mật khẩu chỉ để biết percent escape sai ở đâu. Khi cần chi tiết, log lỗi grammar đã được phân loại, request ID và thông tin không nhạy cảm.

### 14.1. Chính sách “replace” có thể che giấu lỗi dữ liệu

Nếu URLDecoder thay malformed UTF-8 bằng `U+FFFD`, request có thể không bị từ chối dù giá trị đã bị biến dạng. Điều này có thể chấp nhận trong một số UI văn bản tự do, nhưng không phù hợp với nhiều định danh, khóa phân quyền hoặc dữ liệu phải so khớp chính xác.

Với những trường cần chính xác, nên:

1. Parse percent syntax rõ ràng.
2. Decode UTF-8 strict ở ranh giới byte.
3. Validate dữ liệu đã decode.
4. So khớp/ghi dữ liệu theo chính sách thống nhất.

### 14.2. Giới hạn kích thước dữ liệu trước khi xử lý

Các chuỗi encoded dài có thể gây tốn CPU/bộ nhớ dù cú pháp hợp lệ. Cần đặt giới hạn ở tầng server/framework: độ dài request, số trường, độ dài mỗi tên/giá trị, số lượng tham số trùng. Đây là **resource safety**, không được giải quyết bởi `IllegalArgumentException`.

## 15. Lỗi thường gặp và cách sửa

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Mọi chuỗi có `%` đều hợp lệ.” | `%` trong form là mở đầu `%HH`; phải có hai chữ số hex. |
| “`%u0041` là escape Unicode của URLDecoder.” | Không; form encoding dùng byte `%HH`. |
| “`%GG` là lỗi charset.” | Không; đó là lỗi cú pháp trước khi decode charset. |
| “`%C3%28` luôn ném IllegalArgumentException.” | Không; percent đúng cú pháp nhưng byte UTF-8 sai có thể được thay bằng U+FFFD. |
| “Chỉ cần thấy U+FFFD là chắc chắn input byte sai.” | Không; U+FFFD có thể là ký tự Unicode được encode hợp lệ. |
| “`decode(String, Charset)` ném UnsupportedEncodingException.” | Không; đây là overload nhận Charset, không khai báo checked exception đó. |
| “Dấu `+` trong mọi URL đều là dấu cách.” | Không; đó là quy tắc form decoding, không phải quy tắc chung cho URI path. |
| “`URLDecoder` tự biết query có bao nhiêu tham số.” | Không; nó giải mã String theo quy tắc form. |
| “Decode toàn bộ query trước khi split theo & là an toàn.” | Có thể làm `%26` trong giá trị biến thành delimiter giả. |
| “Decode hai lần luôn cho cùng kết quả.” | Sai; `%253C` thành `%3C` rồi thành `<`. |
| “Bắt IllegalArgumentException là đủ để bảo vệ mọi dữ liệu.” | Không; còn validation sau decode, byte charset lỗi, ký tự điều khiển và chính sách nghiệp vụ. |
| “`%00` là escape malformed.” | Không; đó là byte hex hợp lệ, có thể decode thành NUL. |
| “Các implementation Java buộc phải phát cùng message cho escape lỗi.” | Không có cam kết như vậy; thậm chí xử lý chuỗi bất hợp lệ có phạm vi implementation-specific. |
| “Có thể tự encode bằng cách thay space thành +.” | Không; còn `%`, `+`, `&`, `=` và Unicode. |
| “Có framework parse rồi vẫn nên gọi URLDecoder lần nữa.” | Không; dễ tạo double decoding. |
| “Charset mặc định luôn ổn định ở mọi JDK.” | Nên chỉ định charset tường minh theo giao thức; overload không charset đã deprecated. |
| “Không ném exception thì chuỗi chắc chắn an toàn cho SQL/HTML.” | Sai; sử dụng escaping/parameterization theo ngữ cảnh đích, độc lập với URLDecoder. |

## 16. Câu hỏi thực hành và đáp án

### Bài 1 — Dấu phần trăm trơ

~~~java
URLDecoder.decode("a%", StandardCharsets.UTF_8);
~~~

**Hỏi:** Trên OpenJDK hiện hành, chuyện gì xảy ra?

**Đáp án:** Ném `IllegalArgumentException` vì `%` thiếu hai chữ số hex. Javadoc chung vẫn dành phần xử lý malformed escape cho implementation; đừng dựa vào nội dung message cụ thể.

### Bài 2 — Hex thiếu ký tự

~~~java
URLDecoder.decode("%2", StandardCharsets.UTF_8);
~~~

**Đáp án:** `IllegalArgumentException` trên OpenJDK thông dụng do thiếu chữ số hex thứ hai.

### Bài 3 — Hex không hợp lệ

~~~java
URLDecoder.decode("x=%GG", StandardCharsets.UTF_8);
~~~

**Đáp án:** Lỗi percent syntax do `G` không phải hex. Trên OpenJDK thông dụng ném `IllegalArgumentException`, không phải `UnsupportedEncodingException`.

### Bài 4 — Dấu cộng trong form

~~~java
URLDecoder.decode("first+last", StandardCharsets.UTF_8);
URLDecoder.decode("first%2Blast", StandardCharsets.UTF_8);
~~~

**Đáp án:** Lần lượt `"first last"` và `"first+last"`. Dấu cộng literal phải được escape nếu dùng form encoding.

### Bài 5 — Dấu phần trăm thật

~~~java
URLDecoder.decode("rate%25", StandardCharsets.UTF_8);
~~~

**Đáp án:** `"rate%"`. `%25` là byte `0x25` tương ứng dấu `%`.

### Bài 6 — Byte lỗi nhưng percent đúng

~~~java
URLDecoder.decode("%C3%28", StandardCharsets.UTF_8);
~~~

**Đáp án:** Hai escape `%C3` và `%28` đều đúng grammar, nhưng byte không tạo thành UTF-8 hợp lệ. Phương thức có thể thay bằng ký tự thay thế. Nếu buộc phải reject, cần strict CharsetDecoder xử lý bytes; chỉ bắt `IllegalArgumentException` từ URLDecoder không đủ.

### Bài 7 — Encode chuỗi thô

~~~java
String raw = "a+b c&x=%";
String encoded = URLEncoder.encode(raw, StandardCharsets.UTF_8);
~~~

**Đáp án:** `"a%2Bb+c%26x%3D%25"`; decode một lần với UTF-8 trả về chuỗi thô ban đầu.

### Bài 8 — Decode lần thứ hai

~~~java
var once = URLDecoder.decode("%252B", StandardCharsets.UTF_8);
var twice = URLDecoder.decode(once, StandardCharsets.UTF_8);
~~~

**Đáp án:** `once` là `"%2B"`; `twice` là `"+"`. Hai lần giải mã có thể thay đổi giá trị, nên không làm khi input đã được framework decode.

### Bài 9 — Dấu phân cách bị escape

Query raw là:

~~~text
k=a%26b&c=d
~~~

**Đáp án:** Đây là hai cặp: `k` có giá trị `a&b`, `c` có giá trị `d`. Nếu decode toàn chuỗi trước khi phân tách, `%26` có thể bị nhầm là delimiter thật.

### Bài 10 — Null so với malformed escape

~~~java
URLDecoder.decode(null, StandardCharsets.UTF_8);
~~~

**Đáp án:** `NullPointerException`, không phải `IllegalArgumentException`. Chỉ bắt `IllegalArgumentException` để xử lý malformed percent không đồng nghĩa đã kiểm tra tham số null.

### Bài 11 — Escape có byte điều khiển

~~~java
var value = URLDecoder.decode("%00", StandardCharsets.UTF_8);
~~~

**Đáp án:** `%00` đúng percent syntax và có thể decode thành một ký tự NUL. Nếu trường dữ liệu không được chứa ký tự điều khiển, phải có validation sau decode.

### Bài 12 — Ràng buộc implementation

**Hỏi:** Có nên viết test portability yêu cầu **mọi Java implementation** đều ném `IllegalArgumentException` cho `"%GG"` không?

**Đáp án:** Không. Javadoc cho phép có khác biệt trong việc xử lý chuỗi bất hợp lệ; nếu cần cùng một chính sách reject ở mọi môi trường, viết validator percent grammar riêng hoặc sử dụng parser đã có hợp đồng strict rõ ràng.

### Bài 13 — Ký tự thay thế hợp lệ

~~~java
URLDecoder.decode("%EF%BF%BD", StandardCharsets.UTF_8);
~~~

**Đáp án:** Nó decode thành `U+FFFD` từ một byte sequence UTF-8 **hợp lệ**. Không thể coi mọi String có ký tự thay thế là bằng chứng chắc chắn input sai.

### Bài 14 — Sai bối cảnh

Một path thực sự chứa dấu cộng `/docs/C++`. Có nên gọi URLDecoder lên toàn path không?

**Đáp án:** Không. Dấu cộng là ký tự literal trong path theo các quy tắc URI phù hợp; `URLDecoder` thuộc form encoding và đổi `+` thành space. Dùng URI/path parser hoặc framework API xử lý đúng thành phần.

### Bài 15 — Charset

Một hệ thống định nghĩa toàn bộ form được encode bằng UTF-8, nhưng client gửi dãy byte không hợp lệ. Có nên thử ISO-8859-1 và chấp nhận nếu trông giống chữ không?

**Đáp án:** Không nên. Hãy tuân thủ charset đã thỏa thuận và chính sách strict/replacement được xác định. Tự đoán charset gây khác biệt giải nghĩa và có thể làm sai các định danh.

## 17. Checklist để review code form decoding

- [ ] Đầu vào có **thực sự** dùng `application/x-www-form-urlencoded` không?
- [ ] Đã xác định điểm nào của framework/transport **đã decode** chưa để tránh double decoding?
- [ ] Đã dùng overload `decode(String, Charset)` và charset được chỉ định rõ chưa?
- [ ] Đã phân biệt `%HH` malformed với byte charset malformed chưa?
- [ ] Có validation percent syntax đủ hai chữ số **hex ASCII** khi nghiệp vụ cần reject portable không?
- [ ] Nếu đầu vào bắt buộc UTF-8 hợp lệ, có dùng giải mã strict thay vì mặc định replacement không?
- [ ] Dấu `+`, `%2B`, `%20` và `%25` đã được test đúng chưa?
- [ ] Có test các ca `%`, `%2`, `%GG`, `%2Z`, `%u0041` chưa?
- [ ] Có test Unicode nhiều byte như `%C3%A9`, `%E2%82%AC`, `%F0%9F%98%80` chưa?
- [ ] Có test `U+FFFD` được encode hợp lệ, không nhầm với malformed UTF-8 không?
- [ ] Có xử lý `null`, chuỗi rỗng và yêu cầu độ dài của field chưa?
- [ ] Có phân tách tên và giá trị query đúng cách **trước khi decode từng thành phần** không?
- [ ] Có quy định tham số trùng tên, giá trị trống hoặc thiếu dấu `=` không?
- [ ] Có từ chối control characters hay phân cách không hợp lệ theo nghiệp vụ sau decode không?
- [ ] Có trả lỗi client phù hợp thay vì biến mọi input sai thành lỗi hệ thống 500 không?
- [ ] Có tránh log dữ liệu nhạy cảm của form không?
- [ ] Có dùng URL/HTML/SQL/path escaping đúng **ngữ cảnh đích** sau parse không?
- [ ] Có giới hạn request length, số tham số và tài nguyên dùng để decode không?
- [ ] Có tránh phụ thuộc message `IllegalArgumentException` hoặc thứ tự lỗi nội bộ cụ thể không?
- [ ] Có xác định biên giới giữa **URI path**, **raw query** và **form body** chưa?

## 18. Tài liệu chính thức còn áp dụng

- [Java SE API — `URLDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLDecoder.html): quy tắc `+`, `%HH`, overload `decode(String, Charset)` (Since: 10), `IllegalArgumentException` cho escape malformed khi implementation phát hiện và chính sách thay thế byte lỗi.
- [Java SE API — `URLEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLEncoder.html): `encode(String, Charset)` (Since: 10), cách chuyển dữ liệu thô thành `application/x-www-form-urlencoded`.
- [Java SE 10 API — `URLDecoder`](https://docs.oracle.com/javase/10/docs/api/java/net/URLDecoder.html): xác nhận API nhận Charset xuất hiện trong Java 10.
- [Java SE API — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): giải mã byte strict và các chính sách xử lý malformed input/unmappable character.
- [Java SE API — `CodingErrorAction`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE` và `IGNORE`.
- [Java SE API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): hằng charset `UTF_8` và các lựa chọn chuẩn.
- [Java SE API — `URI`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URI.html): phân biệt các thành phần của URI và thao tác với raw/decoded components; không đồng nhất với form decoder.
- [Java SE API — `IllegalArgumentException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IllegalArgumentException.html): loại unchecked exception dùng để báo tham số không hợp lệ, khác `NullPointerException`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh charset mặc định hiện đại; dù vậy vẫn chỉ định charset tường minh ở ranh giới form/protocol.

**Ghi nhớ cuối cùng:** Trong dữ liệu biểu mẫu, `%` chỉ mở đầu một escape `%HH` có hai chữ số hex; escape thiếu hoặc sai chữ số có thể làm `URLDecoder` ném `IllegalArgumentException` trên OpenJDK. Nhưng byte percent-encoded **hợp lệ về grammar** vẫn có thể tạo UTF-8 không hợp lệ và được thay bằng `U+FFFD`. Hãy decode đúng một lần, tại đúng ranh giới form, bằng charset tường minh; nếu ứng dụng cần chính sách nghiêm ngặt, xác thực **cả grammar percent và byte charset** rồi kiểm tra dữ liệu nghiệp vụ sau decode.