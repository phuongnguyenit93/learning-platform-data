# Vì sao Base64, escape và chuyển charset là các thao tác khác nhau

## 1. Ba bài toán khác nhau dù đều hay được gọi là “encode”

Trong Java, ta thường cần đưa văn bản vào file, truyền dữ liệu nhị phân qua một giao thức chỉ nhận ký tự, hoặc nhúng văn bản vào JSON/HTML. Cả ba tình huống đều có thể xuất hiện từ *encoding*, nhưng thực chất là ba loại biến đổi có **đầu vào, đầu ra và mục đích khác nhau**:

- **Mã hóa ký tự bằng charset** (*character encoding/decoding*): quy định cách chuyển **ký tự trong `String` ↔ byte**. Ví dụ UTF-8 biến ký tự `é` thành hai byte `C3 A9`. Khi **chuyển charset (transcoding)**, ta giải mã dãy byte theo charset nguồn rồi mã hóa văn bản theo charset đích.
- **Base64**: biến **byte ↔ chuỗi ký tự ASCII từ bảng chữ cái Base64** nhằm mang dữ liệu nhị phân qua môi trường dạng văn bản. Base64 không biết byte ban đầu là tiếng Việt, ảnh hay file ZIP. Nó cũng **không phải mã hóa bảo mật**.
- **Escape**: biểu diễn các ký tự có ý nghĩa đặc biệt một cách an toàn, đúng cú pháp trong **một ngữ cảnh cụ thể**, như `\"` trong Java string literal, `\n` khi hiển thị dấu xuống dòng, `&lt;` trong HTML, hoặc `\\` trong chuỗi JSON. Escape không tự quyết định cách lưu ký tự thành byte.

Điểm mấu chốt là: **Base64 giải quyết việc biểu diễn byte dưới dạng ký tự**, **charset giải quyết ánh xạ văn bản và byte**, còn **escape giải quyết ý nghĩa cú pháp của ký tự trong một ngữ cảnh**. Chúng có thể xuất hiện liên tiếp trong một quy trình, nhưng không thay thế được nhau.

## 2. So sánh trực tiếp

| Tiêu chí | Charset / chuyển charset | Base64 | Escape / unescape |
| --- | --- | --- | --- |
| Câu hỏi giải quyết | “Những ký tự này thành byte nào, và ngược lại?” | “Làm sao biểu diễn các byte bằng ký tự ASCII?” | “Ký tự này phải viết thế nào để không bị hiểu là cú pháp?” |
| Đầu vào điển hình | `String` khi encode; `byte[]` khi decode | `byte[]` khi encode; chuỗi Base64 khi decode | Văn bản/ký tự cần nhúng vào ngữ cảnh |
| Đầu ra điển hình | `byte[]` hoặc `String` | Chuỗi ký tự Base64 hoặc `byte[]` | Chuỗi biểu diễn đã escape hoặc nội dung đã unescape |
| Quy tắc phụ thuộc | Charset như UTF-8, ISO-8859-1 | Bảng chữ cái Base64 thường hoặc URL-safe, padding | Cú pháp Java, JSON, HTML, regex, URL... |
| Có hiểu nội dung văn bản? | Có: giải nghĩa byte là ký tự theo charset đã chọn | Không: xử lý byte theo nhóm bit | Có ngữ cảnh cú pháp; không nhất thiết hiểu mã hóa byte |
| Có tạo tính bí mật? | Không | Không | Không |
| Sai kiểu thường gặp | Mojibake `HÃ©`, ký tự thay thế | Chuỗi Base64 sai alphabet/padding | Dấu nháy, xuống dòng hoặc ký tự đặc biệt bị hiểu sai |

Ví dụ có thể hình dung bằng luồng dữ liệu:

```text
String: "Hé"
    | getBytes(UTF_8)           [mã hóa ký tự bằng UTF-8]
    v
byte[]: 48 C3 A9
    | Base64.getEncoder()       [mã hóa Base64 trên byte]
    v
String Base64: "SMOp"
    | Base64.getDecoder()       [đảo Base64: lấy lại byte]
    v
byte[]: 48 C3 A9
    | new String(bytes, UTF_8)  [giải mã byte thành ký tự]
    v
String: "Hé"
```

Dòng `SMOp` **không phải “chuỗi Hé đã đổi sang charset Base64”**. Base64 là cách biểu diễn ba byte `48 C3 A9`; thông tin UTF-8 do bước phía trước quyết định. Nếu nhận lại những byte đó nhưng dùng sai charset, văn bản có thể sai dù Base64 đã decode chính xác.

## 3. Charset: `String` và `byte[]` là hai loại dữ liệu khác nhau

Trong Java, `String` biểu diễn chuỗi ký tự Unicode; còn `byte[]` chỉ là các giá trị byte, **không kèm nhãn charset**. Để gửi hoặc ghi một chuỗi thành byte, phải xác định quy tắc mã hóa ký tự:

```java
import java.nio.charset.StandardCharsets;

String text = "Hé";
byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(utf8Bytes, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa đặt trong phương thức; chương trình độc lập đầy đủ có ở phần 6.

Với `"Hé"`:

- UTF-8: `48 C3 A9` — `H` có byte `48`, `é` có hai byte `C3 A9`.
- ISO-8859-1: `48 E9` — `é` được biểu diễn bằng một byte `E9`.
- Cả hai là cách biểu diễn **cùng văn bản** theo hai charset khác nhau; số byte không nhất thiết bằng `String.length()`.

### Chuyển charset đúng nghĩa là gì?

Giả sử có `byte[] oldBytes` được biết chắc là mã hóa theo ISO-8859-1, và hệ thống nhận cần UTF-8:

```java
String unicodeText = new String(oldBytes, StandardCharsets.ISO_8859_1);
byte[] newBytes = unicodeText.getBytes(StandardCharsets.UTF_8);
```

Đó là thao tác **transcoding**: *giải mã byte với charset nguồn → có văn bản → mã hóa văn bản bằng charset đích*. Không thể chỉ đổi tên charset hoặc đặt Base64 lên mảng byte rồi coi dữ liệu đã thành UTF-8.

Nếu giải mã byte UTF-8 `48 C3 A9` bằng ISO-8859-1, Java cho `HÃ©`, hiện tượng thường gọi là **mojibake**. Điều này không cho thấy Base64 hỏng; lỗi nằm ở bước diễn giải byte thành ký tự.

**Cẩn thận với dữ liệu không hợp lệ hoặc không thể biểu diễn:** các overload tiện lợi như `new String(bytes, charset)` có thể dùng ký tự thay thế cho chuỗi byte lỗi theo cơ chế của API; `String.getBytes(charset)` có thể thay thế ký tự không mã hóa được. Nếu ứng dụng bắt buộc phát hiện lỗi thay vì thay thế, hãy cấu hình `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction.REPORT` và xử lý exception. Với văn bản Unicode có thể chứa nhiều ngôn ngữ, UTF-8 thường là lựa chọn phù hợp cho trao đổi dữ liệu.

Ưu tiên **khai báo charset tường minh** bằng `StandardCharsets.UTF_8` khi đọc/ghi; đừng buộc người đọc phải suy đoán `getBytes()` hay `new String(bytes)` dùng charset mặc định nào của môi trường.

## 4. Base64 làm gì với byte?

Base64 đọc luồng byte theo nhóm bit, ánh xạ các nhóm 6 bit thành ký tự ASCII và có thể bổ sung dấu `=` làm padding. Theo dạng thông dụng, **3 byte → 4 ký tự Base64**; với 1 hoặc 2 byte cuối, kết quả được padding để hoàn chỉnh nhóm 4 ký tự. Vì vậy Base64 thường làm **dữ liệu lớn hơn**, không phải nén.

Trong Java, dùng `java.util.Base64`:

```java
byte[] bytes = "Hé".getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(bytes); // "SMOp"
byte[] decoded = Base64.getDecoder().decode(encoded);
String text = new String(decoded, StandardCharsets.UTF_8); // "Hé"
```

Lưu ý: `Base64.getEncoder()` nhận **byte**, không nhận trực tiếp `String`; hàm `encodeToString` trả về các ký tự Base64 do encoder tạo ra. Bước `getBytes(UTF_8)` là quyết định riêng và cần được phía nhận biết để khôi phục văn bản ban đầu.

### Một luồng sai charset vẫn có Base64 hoàn toàn hợp lệ

Giả sử lấy chuỗi `"Hé"`, chuyển thành byte UTF-8 rồi Base64 thành `SMOp`. Phía nhận decode Base64 ra đúng `48 C3 A9` nhưng viết:

```java
String wrong = new String(
        Base64.getDecoder().decode("SMOp"),
        StandardCharsets.ISO_8859_1
); // "HÃ©"
```

Base64 đã hoàn thành chính xác trách nhiệm của nó; **chuỗi sai do chọn ISO-8859-1 thay vì UTF-8**. Việc “thử Base64 một lần nữa” không sửa được lỗi charset.

### Base64 không mã hóa bí mật và không xác minh tính toàn vẹn

Ai có chuỗi Base64 đều có thể decode dữ liệu. Base64 không cung cấp mật khẩu, mã hóa đối xứng, tính bí mật, chữ ký hoặc kiểm tra nguồn gốc. Nếu cần bảo vệ thông tin, phải áp dụng cơ chế bảo mật phù hợp như TLS và mã hóa/xác thực thực sự; Base64 chỉ có thể là lớp biểu diễn bổ sung.

Có nhiều biến thể: `Base64.getEncoder()` dùng alphabet thông dụng với `+` và `/`; `Base64.getUrlEncoder()` dùng alphabet URL-safe với `-` và `_`. Chọn đúng biến thể theo giao thức đang dùng; `withoutPadding()` chỉ nên sử dụng khi định dạng trao đổi cho phép. URL-safe Base64 vẫn **khác** phần trăm hóa URL (*percent-encoding*).

## 5. Escape là quy tắc cú pháp, không phải quy tắc byte

Một chuỗi chứa ký tự đặc biệt có thể làm hỏng cấu trúc nơi nó được nhúng vào. Escape xử lý vấn đề **ký tự nào có nghĩa đặc biệt trong ngữ cảnh đó**.

### Escape trong Java string literal

Đoạn mã nguồn:

```java
String message = "A\nB";
```

Trong file Java, ký hiệu `\n` biểu diễn **một ký tự xuống dòng** trong giá trị runtime. Sau khi chương trình chạy, `message` không còn giữ dấu `\` và chữ `n` riêng lẻ tại vị trí đó. Trình biên dịch Java đã diễn giải cú pháp escape.

Ngược lại:

```java
String visible = message.replace("\n", "\\n");
```

`visible` chứa ký tự `A`, `\`, `n`, `B`. Đó là một **cách biểu diễn có escape** để nhìn thấy xuống dòng trên cùng một dòng, chứ không phải chuyển charset. Nếu mã hóa cả hai `String` thành UTF-8, giá trị đầu là `41 0A 42`, còn giá trị sau là `41 5C 6E 42`.

Phép `replace` phía trên **chỉ là minh họa cho một ký tự xuống dòng**; nó chưa phải bộ serialize/unescape đầy đủ. Ví dụ, nếu dữ liệu gốc đã chứa hai ký tự `\` và `n`, chỉ dùng `replace("\\n", "\n")` để “giải escape” sẽ không phân biệt được đâu là ký tự gốc và đâu là ký hiệu được thêm sau đó. Định dạng escape cần quy tắc bao gồm cả việc xử lý **dấu backslash có sẵn**.

### Escape phụ thuộc nơi sử dụng

| Ngữ cảnh | Vấn đề | Ví dụ minh họa |
| --- | --- | --- |
| Java string literal | Dấu nháy, backslash, ký tự xuống dòng có cú pháp riêng | `"He said \"Hi\""` |
| JSON string | Dấu `"` và `\` phải escape; ký tự điều khiển phải biểu diễn đúng quy tắc JSON | Giá trị chứa xuống dòng được serialize thành `\n` bên trong JSON string |
| HTML text | Các dấu `&` và `<` có thể mở entity hoặc markup | `<` thành `&lt;` trong phần văn bản HTML |
| Regex | `.`, `*`, `+`, `[` ... là toán tử | Regex khớp dấu chấm literal trong Java: `"\\."` |
| URL | Một số byte cần được percent-encode theo thành phần URL | Khoảng trắng UTF-8 trong phần URL tương ứng có thể biểu diễn `%20` |

**Không tồn tại một hàm “escape mọi thứ” dùng an toàn cho mọi ngữ cảnh.** HTML text khác HTML attribute; JSON string khác regex; từng phần của URL cũng có quy tắc riêng. Với JSON hoặc HTML trong ứng dụng thực tế, ưu tiên thư viện serializer/encoder phù hợp với đúng ngữ cảnh thay vì tự nối chuỗi hoặc thay vài ký tự bằng tay.

### Thứ tự xử lý có thể quan trọng

Khi ghi JSON chứa chuỗi Base64 của file nhị phân, ta có thể:

1. Mã hóa `byte[]` thành **Base64 string**.
2. Đưa **Base64 string** vào một trường dữ liệu của đối tượng JSON.
3. Dùng JSON serializer để escape ký tự và dựng JSON đúng cú pháp.
4. Khi gửi JSON qua mạng, mã hóa **toàn bộ văn bản JSON** thành byte theo charset của giao thức (thông thường UTF-8).

Ở phía nhận, làm ngược các lớp thích hợp: đọc byte JSON thành văn bản theo charset quy định → JSON parser lấy giá trị string → Base64 decoder khôi phục byte gốc. JSON escape và Base64 tác động lên **những lớp khác nhau**. Nếu byte gốc là file ảnh, **không được tùy tiện tạo `String` từ byte ảnh rồi `getBytes` lại**; truyền byte trực tiếp qua Base64.

## 6. Java 17+ runnable: thấy rõ ba phép biến đổi

Tạo tệp `EncodingLayersDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;

public class EncodingLayersDemo {
    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase().formatHex(bytes);
    }

    public static void main(String[] args) {
        String text = "Hé";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] latin1 = text.getBytes(StandardCharsets.ISO_8859_1);
        String base64 = Base64.getEncoder().encodeToString(utf8);
        byte[] decodedBytes = Base64.getDecoder().decode(base64);
        String restored = new String(decodedBytes, StandardCharsets.UTF_8);
        String wrong = new String(utf8, StandardCharsets.ISO_8859_1);

        String original = "A\nB";
        String escaped = original.replace("\n", "\\n");

        System.out.println("text: " + text);
        System.out.println("utf8: " + hex(utf8));
        System.out.println("latin1: " + hex(latin1));
        System.out.println("base64: " + base64);
        System.out.println("decoded bytes: " + hex(decodedBytes));
        System.out.println("round-trip: " + text.equals(restored));
        System.out.println("wrong charset: " + wrong);
        System.out.println("newline bytes: "
                + hex(original.getBytes(StandardCharsets.UTF_8)));
        System.out.println("escaped text: " + escaped);
        System.out.println("escaped bytes: "
                + hex(escaped.getBytes(StandardCharsets.UTF_8)));
        System.out.println("escaped differs: " + !original.equals(escaped));
    }
}
```

Lệnh biên dịch/chạy trong thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 EncodingLayersDemo.java
java EncodingLayersDemo
```

Stdout đã được kiểm chứng:

```text
text: Hé
utf8: 48 C3 A9
latin1: 48 E9
base64: SMOp
decoded bytes: 48 C3 A9
round-trip: true
wrong charset: HÃ©
newline bytes: 41 0A 42
escaped text: A\nB
escaped bytes: 41 5C 6E 42
escaped differs: true
```

**Đọc kết quả theo đúng lớp:**

- `utf8` và `latin1` khác nhau vì **charset** khác nhau; một đối tượng `String` nguồn vẫn là `"Hé"`.
- `base64` là chuỗi ASCII `SMOp` biểu diễn chính xác **ba byte UTF-8**, không trực tiếp biểu diễn ký tự Unicode theo quy tắc charset.
- `decoded bytes` bằng dữ liệu đầu vào `utf8`; phục hồi đúng chữ khi dùng lại `UTF_8`.
- `wrong charset` thành `HÃ©`: mất nghĩa văn bản vì chọn cách đọc byte sai.
- `newline bytes` có byte `0A` thật, còn `escaped bytes` có hai byte `5C 6E` tương ứng dấu `\` và chữ `n`. Trường hợp này là **biến đổi văn bản để hiển thị**, không phải Base64 hay đổi charset.
- `HexFormat` (Java 17+) ở đây chỉ dùng để **in byte thành các cặp chữ số thập lục phân để quan sát**. Hex cũng là một cách biểu diễn byte, khác với charset và khác với ý nghĩa cú pháp escape.

## 7. Chọn đúng thao tác theo yêu cầu

**Tình huống A — đọc file văn bản UTF-8:** Đọc byte rồi decode bằng UTF-8; ghi file bằng cách encode `String` sang UTF-8. Các API như `Files.readString(path, StandardCharsets.UTF_8)` và `Files.writeString(path, text, StandardCharsets.UTF_8)` biểu diễn rõ chủ ý. Không cần Base64 nếu định dạng file chấp nhận byte văn bản trực tiếp.

**Tình huống B — chuyển file ISO-8859-1 sang UTF-8:** Decode byte bằng ISO-8859-1 thành `String`, sau đó encode thành byte UTF-8. Nếu byte ban đầu đã bị hiểu sai hoặc dữ liệu chứa ký tự không biểu diễn được, phải đánh giá dữ liệu gốc thay vì kỳ vọng một lớp Base64 sửa được.

**Tình huống C — đưa ảnh hoặc file ZIP vào trường JSON:** Base64 encode trực tiếp **byte[] của file** rồi đặt chuỗi kết quả vào đối tượng JSON. Đừng gọi `new String(imageBytes, UTF_8)` vì ảnh không phải văn bản UTF-8. Dùng JSON serializer cho phần cú pháp JSON.

**Tình huống D — nhúng nội dung người dùng vào HTML hoặc JSON:** Escape/serialize **đúng ngữ cảnh đầu ra**. Base64 không tự làm HTML/JSON an toàn; đổi charset cũng không làm mất ý nghĩa cú pháp của dấu `<`, `"` hoặc `&`.

**Tình huống E — dấu phân cách trong URL:** Dùng quy tắc percent-encoding cho thành phần URL liên quan. URL-safe Base64 giúp bảng chữ cái bớt xung đột với một số ký tự đặc biệt, nhưng không thay thế quy tắc dựng và encode URI/URL.

**Tình huống F — truyền token hoặc dữ liệu nhạy cảm:** Base64 chỉ giúp biểu diễn dữ liệu; không bảo vệ khỏi người đọc có quyền truy cập token. Cần cơ chế kiểm soát truy cập, mã hóa/xác thực và giao thức vận chuyển phù hợp.

## 8. Lỗi phổ biến và bài tự kiểm tra

1. **Gọi Base64 là mã hóa bảo mật:** dữ liệu Base64 có thể decode dễ dàng, nên không được dùng để giấu mật khẩu.
2. **Decode Base64 thành `String` mà không chọn charset:** Base64 decoder trả về byte; nếu byte đó vốn là văn bản UTF-8, dùng `new String(bytes, StandardCharsets.UTF_8)`.
3. **Đổi charset bằng `new String(bytes, wrongCharset)`:** hành động này chỉ đổi cách diễn giải byte, có thể gây mojibake. Transcoding phải biết charset nguồn chính xác.
4. **Chuyển binary tùy ý qua `String`:** byte của file ảnh, ZIP hoặc dữ liệu nén không mặc định là văn bản; có thể gây thay thế dữ liệu khi decode sai.
5. **Tưởng `\n` và LF thực luôn giống nhau:** trong Java source `"\n"` là một LF, còn `"\\n"` là hai ký tự `\` và `n`. Mỗi cách có byte khác nhau sau khi encode.
6. **Dùng escape sai ngữ cảnh:** `Pattern.quote` dành cho **regex literal**, không phải JSON/HTML; HTML escaping không biến dữ liệu thành Base64.
7. **Nhầm URL-safe Base64 với URL percent-encoding:** chúng có bảng chữ cái, mục đích và quy tắc giải mã khác nhau.
8. **Bỏ qua dữ liệu lỗi:** Base64 decoder có thể báo lỗi khi gặp chuỗi không hợp lệ; charset decoder cấu hình nghiêm ngặt có thể phát hiện byte không giải mã được. Chọn chính sách lỗi rõ ràng ở ranh giới dữ liệu.

Thử trả lời ba câu để tự kiểm tra:

- Khi `"Hé"` trở thành ba byte `48 C3 A9`, thao tác đó là **UTF-8 encoding** hay Base64? → **UTF-8 encoding**.
- Khi ba byte đó trở thành `SMOp`, thao tác đó là **Base64** hay chuyển charset? → **Base64**.
- Khi một LF thực được biểu diễn cho người đọc là hai ký tự `\` và `n`, thao tác đó là **escape ký tự theo quy ước hiển thị** hay mã hóa Base64? → **Escape/biểu diễn văn bản**.

**Ghi nhớ:** **charset** gắn nghĩa ký tự với byte, **Base64** biểu diễn byte bằng chữ ASCII, còn **escape** biểu diễn ký tự cho đúng ngữ pháp tại nơi sử dụng. Khi ghép nhiều lớp, hãy ghi rõ thứ tự thao tác, kiểu dữ liệu sau từng bước và quy tắc đảo chiều để tránh nhầm mã hóa dữ liệu, trình bày cú pháp và bảo mật.
