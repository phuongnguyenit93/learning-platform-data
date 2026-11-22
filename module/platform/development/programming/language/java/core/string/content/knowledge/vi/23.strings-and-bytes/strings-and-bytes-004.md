# Độ dài UTF-8 không bằng `String.length()` trong Java

Một `String` Java là chuỗi văn bản Unicode được biểu diễn bằng các **đơn vị mã UTF-16** (UTF-16 code units). Ngược lại, UTF-8 là cách **mã hóa văn bản thành byte**. Vì vậy, hai biểu thức sau đo hai đại lượng khác nhau:

~~~java
int utf16Units = text.length();
int utf8Bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
~~~

`text.length()` trả về số đơn vị mã UTF-16 trong chuỗi; `getBytes(StandardCharsets.UTF_8).length` trả về số byte sau khi mã hóa chuỗi sang UTF-8. Cần phân biệt chúng khi giới hạn kích thước dữ liệu, tính kích thước nội dung gửi qua mạng, lưu trữ hoặc cắt chuỗi.

## 1. Ba cách đếm dễ bị nhầm

| Đại lượng | Java API | Đo điều gì? |
| --- | --- | --- |
| Đơn vị mã UTF-16 | `text.length()` | Số giá trị `char` cấu thành `String` |
| Unicode code point | `text.codePointCount(0, text.length())` | Số code point trong chuỗi; một code point ngoài BMP thường chiếm hai `char` |
| Số byte UTF-8 | `text.getBytes(StandardCharsets.UTF_8).length` | Độ dài của mảng byte sau khi mã hóa UTF-8 |

**Không đồng nhất cả ba với “số ký tự người dùng nhìn thấy”.** Chẳng hạn, chữ `é` có thể biểu diễn bằng một code point `U+00E9` hoặc bằng `e` cộng dấu sắc kết hợp `U+0301` (hai code point). Nhiều emoji gia đình, cờ hoặc emoji kèm biến thể được tạo thành từ nhiều code point nhưng hiển thị như một cụm ký tự. Đếm *grapheme cluster* (cụm chữ hiển thị) là bài toán riêng.

### Vì sao Java `String.length()` đếm UTF-16?

Trong Java, phương thức `length()` có ngữ nghĩa lịch sử là đếm số đơn vị mã UTF-16, không phải số byte trên đĩa hoặc số Unicode code point.

- Các code point trong vùng BMP (`U+0000` đến `U+FFFF`), trừ vùng surrogate, thường cần **một** đơn vị mã UTF-16.
- Một code point bổ sung ngoài BMP (`U+10000` đến `U+10FFFF`), chẳng hạn `😀` (`U+1F600`), cần **hai** đơn vị mã UTF-16: một cặp surrogate.
- `String` Java có thể chứa surrogate đơn lẻ không hợp lệ; khi đó độ dài vẫn đếm đơn vị mã, nhưng việc mã hóa sang byte phải xử lý chuỗi UTF-16 không hợp lệ.

Ví dụ: `"A😀B"` chứa ba code point (`A`, `😀`, `B`), nhưng `length()` trả về **4** vì emoji chiếm hai đơn vị mã UTF-16.

### Vì sao UTF-8 có số byte khác?

Với một Unicode code point hợp lệ, UTF-8 dùng độ dài thay đổi:

| Khoảng code point | Số byte UTF-8 | Ví dụ |
| --- | ---: | --- |
| `U+0000`–`U+007F` | 1 | `A` |
| `U+0080`–`U+07FF` | 2 | `é` (`U+00E9`) |
| `U+0800`–`U+FFFF` (không gồm surrogate) | 3 | `ệ` (`U+1EC7`) |
| `U+10000`–`U+10FFFF` | 4 | `😀` (`U+1F600`) |

Vì `char` trong Java là một đơn vị mã UTF-16 còn byte UTF-8 thuộc một mã hóa khác, **không tồn tại công thức chung** kiểu `utf8Bytes = text.length()`, `text.length() * 2` hoặc `text.length() * 3`. Phải dùng mã hóa UTF-8 thực tế, hoặc thuật toán dựa trên từng code point hợp lệ.

## 2. Ví dụ dễ kiểm chứng

| Chuỗi | `length()` | Code point | Byte UTF-8 | Giải thích |
| --- | ---: | ---: | ---: | --- |
| `"Hello"` | 5 | 5 | 5 | Mọi ký tự đều là ASCII, mỗi ký tự 1 byte UTF-8 |
| `"Việt"` | 4 | 4 | 6 | `V`, `i`, `t`: mỗi chữ 1 byte; `ệ`: 3 byte |
| `"A😀B"` | 4 | 3 | 6 | `A`: 1 byte; `😀`: 4 byte; `B`: 1 byte |
| `"e\u0301"` | 2 | 2 | 3 | `e` (1 byte) và dấu sắc kết hợp `U+0301` (2 byte) |
| `"\u00E9"` (`é`) | 1 | 1 | 2 | `é` dạng dựng sẵn (`U+00E9`): 2 byte |

Trong hai hàng cuối, biểu diễn Java `"\u0301"` và `"\u00E9"` dùng ký pháp Unicode escape. Dù người đọc có thể thấy hai cách biểu diễn chữ `é` giống nhau, số đơn vị mã, code point và byte vẫn khác.

## 3. Chương trình Java 17+ đo từng giá trị

Tạo file `Utf8LengthDemo.java` với nội dung:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8LengthDemo {
    public static void main(String[] args) {
        inspect("ASCII", "Hello");
        inspect("Vietnamese", "Vi\u1EC7t");
        inspect("Emoji", "A\uD83D\uDE00B");
        inspect("Combining", "e\u0301");
        inspect("Precomposed", "\u00E9");
    }

    private static void inspect(String name, String text) {
        int utf16Units = text.length();
        int codePoints = text.codePointCount(0, text.length());
        int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

        System.out.printf(
                "%s: length=%d, codePoints=%d, utf8Bytes=%d%n",
                name, utf16Units, codePoints, utf8Bytes
        );
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Utf8LengthDemo.java
java Utf8LengthDemo
~~~

Kết quả chuẩn:

~~~text
ASCII: length=5, codePoints=5, utf8Bytes=5
Vietnamese: length=4, codePoints=4, utf8Bytes=6
Emoji: length=4, codePoints=3, utf8Bytes=6
Combining: length=2, codePoints=2, utf8Bytes=3
Precomposed: length=1, codePoints=1, utf8Bytes=2
~~~

Ở đây ký tự có dấu và emoji được viết dưới dạng Unicode escape để chương trình minh họa có thể sao chép thuận lợi ngay cả khi cách hiển thị/phông chữ của terminal khác nhau. `StandardCharsets.UTF_8` chỉ rõ charset, tránh phụ thuộc charset mặc định của môi trường.

Một số điều cần nhận ra từ bảng:

1. Với ASCII, ba cách đếm tình cờ bằng nhau; kết quả đó **không** đúng cho toàn bộ Unicode.
2. Với chữ `ệ`, một code point là một đơn vị mã UTF-16 nhưng mã hóa thành ba byte UTF-8.
3. Với `😀`, Java đếm hai đơn vị mã UTF-16, Unicode đếm một code point, UTF-8 dùng bốn byte.
4. Hai cách biểu diễn `é` cho biết cùng hình thức hiển thị không bảo đảm cùng biểu diễn nhị phân.

## 4. Đếm byte đúng cách và lựa chọn charset

Muốn biết số byte UTF-8, hãy **chỉ rõ UTF-8** ở đúng nơi chuyển chuỗi thành byte:

~~~java
import java.nio.charset.StandardCharsets;

String text = "Dữ liệu";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
int byteCount = payload.length;
~~~

Đây là đoạn mã minh họa để dùng bên trong chương trình. `payload.length` là kích thước của **chính mảng byte vừa tạo**; giá trị là số byte, không phải số ký tự.

Nên tránh:

~~~java
// Không đo kích thước UTF-8:
int wrongBytes = text.length();

// Không nên để charset phụ thuộc môi trường:
byte[] platformDependent = text.getBytes();
~~~

`getBytes()` không truyền tham số dùng charset mặc định của JVM. Charset mặc định có thể phụ thuộc phiên bản Java, cấu hình và cách khởi động. Khi yêu cầu là **UTF-8**, hãy dùng overload `getBytes(StandardCharsets.UTF_8)` để thể hiện rõ ý định.

**Giới hạn của cách đếm này:** nó đo chuỗi sau khi mã hóa thành UTF-8, không nhất thiết là số byte thực tế của toàn bộ tài liệu HTTP, JSON, file nén hoặc bản tin mạng. Những lớp đó có thể thêm dấu nháy, escape, dấu phân cách, header, BOM, framing hoặc thay đổi biểu diễn. Ví dụ nội dung Java `"😀"` được mã hóa UTF-8 trực tiếp thành 4 byte, nhưng trong một định dạng JSON nếu serializer chọn escape thành `"\uD83D\uDE00"` thì số byte của văn bản JSON được phát ra sẽ khác. Phải đo **đúng byte của payload cuối cùng** nếu giao thức đặt giới hạn theo payload được truyền đi.

### Chuỗi UTF-16 không hợp lệ

Một `String` Java có thể chứa một surrogate không ghép cặp, ví dụ `"\uD800"`. Đây không phải một Unicode scalar value hợp lệ để mã hóa trực tiếp thành UTF-8. `String.getBytes(StandardCharsets.UTF_8)` sử dụng hành vi thay thế cho đầu vào không hợp lệ; byte thu được phản ánh kết quả thay thế, không phải bản mã UTF-8 của một code point hợp lệ. Nếu cần từ chối dữ liệu sai định dạng, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` thay vì chấp nhận thay thế âm thầm:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Demo {
    public static void main(String[] args) {
        String text = "Java \uD83D\uDE00";

        try {
            ByteBuffer bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(text));
            System.out.println(bytes.remaining());
        } catch (CharacterCodingException ex) {
            System.out.println("Invalid Unicode input");
        }
    }
}
~~~

Đây là chương trình độc lập `StrictUtf8Demo.java`; lệnh chạy:

~~~bash
javac -encoding UTF-8 StrictUtf8Demo.java
java StrictUtf8Demo
~~~

Kết quả:

~~~text
9
~~~

Giải thích: `"Java "` chiếm 5 byte UTF-8 và emoji chiếm 4 byte. `remaining()` đếm số byte còn lại trong `ByteBuffer` ngay sau khi mã hóa. Nếu thay chuỗi hợp lệ bằng một surrogate đứng đơn lẻ, encoder cấu hình `REPORT` sẽ báo lỗi và nhánh `catch` chạy.

## 5. Cắt chuỗi theo hạn mức byte mà không phá vỡ UTF-8

Giả sử một hệ thống chỉ cho phép **5 byte UTF-8**. Chuỗi `"A😀B"` dài 4 đơn vị UTF-16 nhưng chiếm 6 byte. Cắt tùy ý mảng byte hoặc dùng `substring(0, 5)` sẽ sai: `substring` nhận vị trí **UTF-16 code unit**, không nhận byte, và vị trí 5 còn vượt quá độ dài chuỗi này.

Cách an toàn cho **chuỗi UTF-16 hợp lệ** là duyệt từng code point, cộng đúng số byte UTF-8 của code point đó và dừng trước khi vượt hạn mức. Ví dụ tạo file `Utf8PrefixDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8PrefixDemo {
    public static void main(String[] args) {
        String input = "A\uD83D\uDE00B";

        String prefix = prefixWithinUtf8Bytes(input, 5);
        System.out.println(prefix.length());
        System.out.println(prefix.codePointCount(0, prefix.length()));
        System.out.println(prefix.getBytes(StandardCharsets.UTF_8).length);
        System.out.println(prefix.equals("A\uD83D\uDE00"));
    }

    public static String prefixWithinUtf8Bytes(String input, int maxBytes) {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must be nonnegative");
        }

        StringBuilder result = new StringBuilder();
        int written = 0;

        for (int offset = 0; offset < input.length();) {
            int codePoint = input.codePointAt(offset);

            // Một surrogate đứng đơn lẻ biểu thị UTF-16 không hợp lệ.
            if (codePoint >= Character.MIN_SURROGATE
                    && codePoint <= Character.MAX_SURROGATE) {
                throw new IllegalArgumentException("Invalid UTF-16 input");
            }

            int utf8Width;
            if (codePoint <= 0x7F) {
                utf8Width = 1;
            } else if (codePoint <= 0x7FF) {
                utf8Width = 2;
            } else if (codePoint <= 0xFFFF) {
                utf8Width = 3;
            } else {
                utf8Width = 4;
            }

            if (utf8Width > maxBytes - written) {
                break;
            }

            result.appendCodePoint(codePoint);
            written += utf8Width;
            offset += Character.charCount(codePoint);
        }

        return result.toString();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 Utf8PrefixDemo.java
java Utf8PrefixDemo
~~~

Kết quả:

~~~text
3
2
5
true
~~~

Giới hạn là 5 byte nên prefix hợp lệ dài nhất theo **thứ tự từ đầu chuỗi** là `"A😀"`: `A` cần 1 byte, emoji cần 4 byte, tổng 5. Chuỗi này có 3 đơn vị mã UTF-16 và 2 code point. Chữ `B` cuối sẽ vượt hạn mức.

Hàm trên chủ ý từ chối surrogate đơn lẻ; sử dụng `maxBytes - written` thay cho cộng vào số byte đã dùng để tránh phép cộng vượt miền `int` trong trường hợp cực lớn. Hàm dừng tại code point, vì thế không tạo nửa surrogate pair hoặc nửa chuỗi byte UTF-8.

**Tuy nhiên, “không cắt giữa code point” vẫn chưa bảo đảm “không cắt giữa cụm chữ người dùng nhìn thấy”.** Chẳng hạn `e` và dấu kết hợp `U+0301` là hai code point thuộc cùng một chữ hiển thị. Khi giao diện yêu cầu cắt theo grapheme cluster (hoặc xử lý emoji nhiều thành phần), phải có quy tắc phân đoạn cụm chữ phù hợp, sau đó kiểm tra hạn mức byte trên từng cụm. Tránh coi `codePointCount` là giải pháp chung cho mọi bài toán đếm ký tự giao diện.

## 6. Unicode normalization: trông giống nhau vẫn khác byte

Hai chuỗi sau thường hiển thị giống nhau nhưng khác biểu diễn:

~~~java
String decomposed = "e\u0301"; // e + dấu sắc kết hợp
String composed = "\u00E9";   // é dựng sẵn
~~~

| Biểu diễn | UTF-16 units | Code points | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `decomposed` | 2 | 2 | 3 |
| `composed` | 1 | 1 | 2 |

Nếu yêu cầu nghiệp vụ cần dạng Unicode chuẩn hóa, Java có `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
boolean sameRepresentation = normalized.equals(composed); // true
~~~

Đây là đoạn minh họa trong phương thức. `NFC` có thể kết hợp các chuỗi decomposed thành dạng dựng sẵn khi Unicode cho phép; vì vậy có thể thay đổi cả số code point lẫn số byte. **Chỉ chuẩn hóa khi quy định dữ liệu hoặc yêu cầu nghiệp vụ cho phép**, không âm thầm chuẩn hóa một payload đã được ký số, băm, so sánh byte chính xác hoặc lưu theo chuẩn giữ nguyên đầu vào.

Để kiểm tra đồng nhất ở mức byte, chuẩn hóa (nếu cần) phải là một bước đã thống nhất ở cả bên gửi và bên nhận trước khi so sánh/mã hóa.

## 7. Ứng dụng thực tế

### Giới hạn độ dài khi ghi dữ liệu

Nếu quy định lưu trữ là “tối đa 1.024 **byte UTF-8**”, không được thay bằng `text.length() <= 1024`. Cần so sánh kết quả của `getBytes(StandardCharsets.UTF_8).length` với 1.024, sau khi đã xác định quy tắc xử lý normalization và dữ liệu không hợp lệ. Một giới hạn theo “ký tự” của cơ sở dữ liệu có thể có ngữ nghĩa riêng, vì vậy cần đọc tài liệu của chính cột và hệ quản trị trước khi suy ra byte limit.

### HTTP hoặc nội dung truyền qua mạng

Với request body đúng bằng các byte của `text.getBytes(StandardCharsets.UTF_8)`, số byte có thể tính từ `payload.length`. Trường `Content-Length` (khi giao thức sử dụng) nói về số byte của thông điệp body theo framing áp dụng, không phải số đơn vị UTF-16 của chuỗi nguồn. Nếu JSON serializer hoặc lớp truyền thông thay đổi nội dung, phải căn theo byte cuối cùng mà lớp đó xuất ra.

### Đọc dữ liệu và giải mã

Khi nhận byte UTF-8, thao tác chuyển ngược là:

~~~java
import java.nio.charset.StandardCharsets;

byte[] payload = /* byte từ nguồn dữ liệu */;
String decoded = new String(payload, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa, trong đó `payload` phải được cung cấp từ nguồn thực tế. `decoded.length()` tiếp tục là số đơn vị mã UTF-16, **không phải** `payload.length`. Bộ giải mã có thể thay thế chuỗi byte UTF-8 không hợp lệ; nếu cần từ chối đầu vào sai, sử dụng `CharsetDecoder` với `CodingErrorAction.REPORT`.

### Kiểm thử dữ liệu đa ngôn ngữ

Nên có các ca kiểm thử với ASCII, tiếng Việt có dấu, chữ ngoài BMP (emoji), dấu kết hợp, chuỗi rỗng và ranh giới dung lượng (ví dụ đúng 5 byte và vượt 5 byte). Nếu hệ thống có đầu vào không tin cậy, kiểm thử cả surrogate đơn lẻ hoặc byte UTF-8 lỗi theo hợp đồng xử lý của hệ thống.

## 8. Lỗi thường gặp

1. **Dùng `length()` để kiểm tra kích thước UTF-8.** Với `"Việt"`, phép kiểm tra thấy 4 nhưng UTF-8 thực tế cần 6 byte. Sửa bằng cách mã hóa UTF-8 rõ ràng hoặc dùng thuật toán đếm đã kiểm chứng.
2. **Mặc định một `char` luôn là một ký tự Unicode.** `😀` chiếm hai `char`. Nếu duyệt đơn vị mã riêng lẻ để mã hóa/cắt có thể tách cặp surrogate; nên duyệt code point khi bài toán cần code point.
3. **Lấy `codePointCount` thay số byte.** `"A😀B"` có 3 code point nhưng cần 6 byte UTF-8.
4. **Cắt mảng byte UTF-8 ở vị trí bất kỳ rồi giải mã.** Có thể cắt giữa byte đầu và byte tiếp nối của cùng code point, tạo UTF-8 không hợp lệ hoặc ký tự thay thế. Cắt ở ranh giới code point; nếu hiển thị cho người dùng, xét thêm ranh giới grapheme cluster.
5. **Dùng `getBytes()` không nêu charset.** Kết quả không thể hiện rõ yêu cầu UTF-8. Dùng `getBytes(StandardCharsets.UTF_8)`.
6. **Cho rằng hai chuỗi nhìn giống nhau luôn cùng byte.** Các dạng Unicode dựng sẵn/kết hợp và chuỗi chứa ký tự vô hình có thể khác nhau. Xác định quy ước normalization và so sánh theo đúng yêu cầu.
7. **Đếm byte của chuỗi nguồn rồi coi là byte của toàn bộ JSON/HTTP.** Serialization có thể thêm escape, dấu nháy và metadata. Giới hạn theo payload cần đo sản phẩm cuối cùng.

## 9. Bài luyện tập có đáp án

**Bài 1.** Với `String s = "A😀B";`, ba giá trị sau là bao nhiêu?

~~~java
s.length();
s.codePointCount(0, s.length());
s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
~~~

**Đáp án:** `4`, `3` và `6`. UTF-16 dùng hai đơn vị mã cho emoji; UTF-8 dùng bốn byte.

**Bài 2.** Bộ đệm cho phép tối đa 4 byte UTF-8. Có thể giữ nguyên `"A😀B"` không? Nếu phải giữ prefix theo code point, prefix dài nhất là gì?

**Đáp án:** Không, chuỗi ban đầu chiếm 6 byte. Prefix dài nhất theo thứ tự từ đầu chuỗi là `"A"` (1 byte), vì thêm `😀` cần 4 byte nữa và sẽ vượt 4 byte. Không được giữ “nửa emoji”.

**Bài 3.** Dữ liệu `"e\u0301"` và `"\u00E9"` đều hiển thị dạng `é`. Có chắc `getBytes(UTF_8).length` bằng nhau không?

**Đáp án:** Không. Dạng decomposed chiếm 3 byte, dạng composed chiếm 2 byte. Có thể chuẩn hóa theo NFC khi hợp đồng dữ liệu cho phép.

**Bài 4.** Một API nhận JSON giới hạn 100 byte body. Lấy `String.length()` của một thuộc tính để quyết định có vượt giới hạn không?

**Đáp án:** Không. Phải xét JSON được serialize thực tế bằng encoding của request body; một thuộc tính có thể chứa ký tự được escape và body còn chứa tên trường, dấu nháy, ngoặc và các trường khác.

## 10. Ghi nhớ

- `String.length()` → **đơn vị mã UTF-16**.
- `codePointCount(...)` → **Unicode code point**.
- `getBytes(StandardCharsets.UTF_8).length` → **số byte sau khi mã hóa UTF-8**.
- Cả ba phép đếm đều không tự động trả lời “bao nhiêu ký tự người dùng nhìn thấy”.
- Cần giới hạn **byte** thì kiểm tra bằng **byte thực tế**; cắt theo byte phải tôn trọng ranh giới Unicode và, khi cần, ranh giới cụm chữ.

Tài liệu API: [`String.length()` và `codePointCount`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html), [`StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html) và [`Normalizer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).