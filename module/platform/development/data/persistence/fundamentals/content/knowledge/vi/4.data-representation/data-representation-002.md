# Mã hóa ký tự, Unicode và lựa chọn charset

> **Chương:** Biểu diễn dữ liệu  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Phạm vi:** Biểu diễn, lưu trữ và truy xuất văn bản trong ứng dụng Java, từ Unicode và mã hóa byte đến thiết kế schema, truy vấn, chỉ mục, bảo mật, khôi phục và tiến hóa dữ liệu.

## 1. Vấn đề thực tế: dữ liệu vẫn còn nhưng chữ đã hỏng

Một ứng dụng Java nhận tên khách hàng **“Nguyễn Thị Ánh”**, ghi xuống tệp rồi nhập vào cơ sở dữ liệu. Ở giao diện nhập, tên hiển thị đúng; sau khi xuất báo cáo CSV, một số ký tự trở thành dấu hỏi hoặc chuỗi vô nghĩa. Cùng lúc, một khách hàng khác nhập tên có emoji và gặp lỗi lưu dữ liệu.

Những sự cố đó có thể xảy ra dù ứng dụng đã chọn một hệ quản trị cơ sở dữ liệu có khả năng lưu bền vững. Persistence giải quyết việc **giữ lại dữ liệu qua thời gian**; còn biểu diễn dữ liệu quyết định **các byte được hiểu thành ký tự nào** khi ghi và đọc lại.

Ví dụ, ký tự `é` được biểu diễn trong UTF-8 bằng hai byte `C3 A9`. Nếu những byte này bị đọc nhầm là Windows-1252, chúng có thể xuất hiện thành `Ã©`. Dữ liệu nguyên gốc vẫn có thể nằm trong tệp, nhưng quá trình giải mã đã dùng sai charset.

Hệ thống lưu trữ đáng tin cậy phải thỏa cả hai mục tiêu:

1. **Độ bền (durability):** dữ liệu đã được xác nhận ghi thành công có thể được phục hồi theo cam kết của hệ thống.
2. **Tính toàn vẹn biểu diễn:** văn bản được mã hóa, truyền, lưu và giải mã nhất quán, giữ đúng nội dung mà nghiệp vụ muốn bảo toàn.

Sau bài học, người học có thể:

- Giải thích sự khác nhau giữa **ký tự**, **Unicode code point**, **UTF-16 code unit**, **grapheme cluster**, **charset** và **encoding**.
- Phân biệt UTF-8, UTF-16, UTF-32 và các charset cũ; chọn charset phù hợp cho tệp, API và cơ sở dữ liệu.
- Dùng API Java chỉ định charset rõ ràng khi đọc/ghi byte, phát hiện dữ liệu mã hóa không hợp lệ và chuẩn hóa Unicode khi cần.
- Hiểu ảnh hưởng của Unicode tới so sánh chuỗi, ràng buộc duy nhất, độ dài trường, chỉ mục và tìm kiếm.
- Xác định điểm phát sinh mojibake, lập kế hoạch chuyển đổi dữ liệu và kiểm thử xuyên toàn bộ đường đi của persistence.

## 2. Unicode là tập mã ký tự; UTF-8 là cách mã hóa thành byte

**Unicode** là tiêu chuẩn gán định danh số cho các ký tự và ký hiệu văn bản. Những định danh đó gọi là **code point**, thường viết dạng `U+XXXX` hoặc `U+XXXXX`.

Ví dụ:

| Văn bản | Unicode code point | Ghi chú |
| --- | --- | --- |
| `A` | `U+0041` | Chữ Latin A |
| `á` | `U+00E1` | Chữ a có dấu sắc dạng dựng sẵn |
| `ắ` | `U+1EAF` | Chữ a có dấu breve và sắc dạng dựng sẵn |
| `€` | `U+20AC` | Ký hiệu euro |
| `😀` | `U+1F600` | Emoji ngoài Basic Multilingual Plane |

Unicode không quy định rằng mọi code point phải chiếm đúng một byte, hai byte hay bốn byte trong mọi hệ thống. Để lưu hoặc truyền văn bản, ta chọn một **Unicode Transformation Format** như UTF-8 hoặc UTF-16 nhằm chuyển chuỗi code point thành các đơn vị mã hóa rồi thành byte.

> **Điểm cốt lõi:** `U+1F600` là định danh Unicode của emoji. Dãy byte `F0 9F 98 80` là cách UTF-8 mã hóa emoji đó. Hai thứ thuộc hai tầng khái niệm khác nhau.

### 2.1. Ký tự nhìn thấy không luôn là một code point

Người dùng nhìn thấy một **ký tự hiển thị** (*grapheme cluster*), nhưng nó có thể gồm nhiều code point. Ví dụ, chữ `ắ` có thể được lưu dưới hai dạng tương đương theo chuẩn hóa Unicode:

~~~text
Dạng dựng sẵn:
    U+1EAF  LATIN SMALL LETTER A WITH BREVE AND ACUTE

Dạng phân rã:
    U+0061  LATIN SMALL LETTER A
    U+0306  COMBINING BREVE
    U+0301  COMBINING ACUTE ACCENT
~~~

Cả hai cách có thể hiển thị như cùng một chữ “ắ”, nhưng **dãy code point và dãy byte khác nhau**. Một emoji gia đình hoặc cờ có thể còn gồm nhiều code point ghép với nhau.

Vì vậy, cần phân biệt:

| Đơn vị | Dùng để làm gì? | Có phải “số ký tự người dùng nhìn thấy” không? |
| --- | --- | --- |
| **Byte** | Lưu, truyền, tính kích thước dữ liệu | Không |
| **Code unit** | Đơn vị của UTF-8/UTF-16/UTF-32 | Không |
| **Code point** | Định danh Unicode | Không nhất thiết |
| **Grapheme cluster** | Nhóm code point tạo một ký tự hiển thị | Gần với điều người dùng nhận biết hơn |

Trong Java, `String.length()` trả về **số UTF-16 code unit**, không phải số ký tự người dùng nhìn thấy.

## 3. Charset và các cách mã hóa thường gặp

**Charset** là tập ký tự cùng ánh xạ giữa ký tự và dạng mã hóa. Khi nói “đọc văn bản bằng UTF-8”, ta yêu cầu bộ giải mã dùng quy tắc UTF-8 để diễn giải chuỗi byte thành văn bản.

| Charset/encoding | Cách biểu diễn | Ưu điểm, phạm vi và lưu ý |
| --- | --- | --- |
| **UTF-8** | 1–4 byte cho mỗi Unicode scalar value | Tương thích ASCII ở các ký tự ASCII; phù hợp hầu hết API, JSON, tệp và hệ thống hiện đại |
| **UTF-16LE / UTF-16BE** | 1 hoặc 2 code unit 16-bit cho code point hợp lệ | Có thứ tự byte little/big endian; code point ngoài BMP cần cặp surrogate |
| **UTF-32LE / UTF-32BE** | Mỗi code point được mã hóa trong một đơn vị 32-bit | Dễ định vị code point nhưng thường tốn chỗ cho văn bản thông dụng |
| **US-ASCII** | 1 byte, tập ký tự giới hạn | Không mã hóa đầy đủ tiếng Việt hay emoji |
| **ISO-8859-1 / Windows-1252 và bộ mã cũ** | Thường 1 byte với bộ ký tự hạn chế | Cần biết chính xác bảng mã khi nhập dữ liệu lịch sử; không phù hợp làm mặc định cho dữ liệu Unicode mới |

**UTF-8 thường là lựa chọn mặc định cho dữ liệu văn bản cần lưu và trao đổi giữa nhiều hệ thống.** Nó mã hóa đủ mọi Unicode scalar value hợp lệ, không phụ thuộc endian và giữ nguyên byte cho vùng ASCII.

UTF-8 không đồng nghĩa với ASCII: một file chứa toàn ASCII có cùng byte khi mã hóa bằng UTF-8, nhưng một file tiếng Việt hoặc emoji cần các byte bổ sung.

### 3.1. Ví dụ kích thước byte

| Văn bản | UTF-8 (hex) | Số byte UTF-8 | Số UTF-16 code unit |
| --- | --- | ---: | ---: |
| `A` | `41` | 1 | 1 |
| `á` | `C3 A1` | 2 | 1 |
| `ắ` (dạng NFC) | `E1 BA AF` | 3 | 1 |
| `😀` | `F0 9F 98 80` | 4 | 2 |
| `a + ◌̆ + ◌́` (dạng phân rã của “ắ”) | `61 CC 86 CC 81` | 5 | 3 |

Lưu ý: ký tự hiển thị “ắ” ở hai hàng cuối liên quan có thể trông giống nhau, nhưng độ dài và dãy byte khác nhau. Các số trong bảng áp dụng đúng dãy code point được mô tả.

### 3.2. Byte Order Mark (BOM)

**BOM** là dấu ở đầu một số luồng văn bản giúp báo thứ tự byte hoặc nhận diện định dạng. UTF-16 thường cần xác định **LE/BE** nếu nguồn không có hợp đồng rõ. UTF-8 không cần BOM để xác định thứ tự byte; nếu có, BOM UTF-8 là dãy `EF BB BF`.

Khi nhập CSV hoặc tệp văn bản:

- Một tệp UTF-8 **có BOM** có thể khiến bộ đọc coi ký tự `U+FEFF` là một phần của tên cột đầu tiên nếu không xử lý.
- Một tệp UTF-8 **không BOM** vẫn là tệp UTF-8 hợp lệ.
- Không nên tự thêm/xóa BOM ngẫu nhiên; hãy định nghĩa định dạng đầu vào, bộ đọc và quy tắc kiểm tra nhất quán.

## 4. Java String: code unit, code point và byte

API `String` của Java sử dụng **ngữ nghĩa đánh chỉ số theo UTF-16 code unit**. Code point ngoài vùng Basic Multilingual Plane được thể hiện bởi **cặp surrogate** trong các thao tác ký tự của Java.

Ví dụ Java 17+:

~~~java
import java.nio.charset.StandardCharsets;

public class UnicodeMeasure {
    public static void main(String[] args) {
        String text = "Aắ😀";

        System.out.println(text.length()); // 4 UTF-16 code units
        System.out.println(text.codePointCount(0, text.length())); // 3
        System.out.println(text.getBytes(StandardCharsets.UTF_8).length); // 8 bytes

        text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .forEach(System.out::println);
        // U+0041, U+1EAF, U+1F600
    }
}
~~~

Trong `"Aắ😀"`, chữ A chiếm 1 byte UTF-8, “ắ” chiếm 3 byte và emoji chiếm 4 byte; tổng cộng **8 byte**. Ở mức `String.length()`, emoji dùng hai UTF-16 code unit nên giá trị là **4**, còn số code point là **3**.

**Không dùng `substring(i, i + 1)` để cắt “một ký tự người dùng nhìn thấy” theo giả định mỗi ký tự là một code unit**: thao tác đó có thể cắt giữa cặp surrogate hoặc giữa chữ và dấu kết hợp. Với xử lý ký tự hiển thị, cần cơ chế phân đoạn grapheme theo chuẩn thích hợp; số code point cũng chưa đủ cho mọi ngôn ngữ/emoji.

Chi tiết cách JVM cất chuỗi trong heap có thể được tối ưu theo phiên bản, nhưng **hợp đồng API của `String` vẫn dựa trên UTF-16 code unit**. Không nên suy ra một Java `char` luôn tương đương một ký tự Unicode đầy đủ.

## 5. Hành trình của văn bản qua một ứng dụng Java

Một yêu cầu web lưu tên khách có thể đi qua nhiều ranh giới mã hóa:

~~~mermaid
flowchart LR
    A["Bàn phím / trình duyệt"] --> B["HTTP / JSON byte"]
    B --> C["Giải mã theo giao thức"]
    C --> D["String Java"]
    D --> E["JDBC / Driver"]
    E --> F[("Cơ sở dữ liệu")]
    F --> G["Driver đọc và giải mã"]
    G --> H["String Java khi truy xuất"]
    H --> I["API / CSV / giao diện"]
~~~

Điều cần bảo vệ là **ý nghĩa văn bản ở từng ranh giới**:

1. Request HTTP/JSON có định dạng văn bản thống nhất (JSON trao đổi giữa hệ thống theo RFC 8259 dùng UTF-8).
2. Bộ giải mã của ứng dụng đọc đúng byte và nhận ra dữ liệu không hợp lệ.
3. Logic Java xử lý `String` với quy tắc so sánh/chuẩn hóa đã xác định.
4. JDBC driver và kết nối database trao đổi text theo mã hóa phù hợp.
5. Database, schema và collation lưu giữ và so sánh dữ liệu theo hợp đồng.
6. Khi xuất CSV, XML hoặc ghi log, bộ mã đầu ra phải được chỉ định rõ.

**Lưu đúng byte nhưng giải mã sai** sẽ làm chữ hiển thị lỗi; **mã hóa lại từ chuỗi đã sai** có thể khiến lỗi trở thành dữ liệu mới được lưu bền vững. Vì vậy, nhận diện lỗi sớm có giá trị hơn việc cố “sửa chữ” sau khi đã ghi đè dữ liệu gốc.

## 6. Đọc và ghi tệp văn bản bằng charset tường minh

Với Java, có thể sử dụng `StandardCharsets.UTF_8` để tránh phụ thuộc ngầm vào charset mặc định của môi trường.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Path.of("data", "customer-name.txt");
        Files.createDirectories(file.getParent());

        String original = "Nguyễn Thị Ánh 😀";
        Files.writeString(file, original, StandardCharsets.UTF_8);

        String restored = Files.readString(file, StandardCharsets.UTF_8);
        System.out.println(restored);
        System.out.println(original.equals(restored)); // true
    }
}
~~~

Ví dụ minh họa **round trip ký tự** trong điều kiện tệp không hỏng và không có tác nhân khác thay đổi. `Files.writeString` không tự cung cấp transaction hay tất cả cam kết crash consistency: ghi dở, hỏng thiết bị, cạnh tranh giữa nhiều tiến trình hoặc mất điện vẫn phải được xử lý theo yêu cầu persistence.

Đối với tệp lớn, có thể dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` và `Files.newBufferedWriter(...)`; nên xử lý theo luồng thay vì luôn đọc toàn bộ tệp vào một `String`. Đối với dữ liệu nhị phân như ảnh, PDF, file nén, **không giải mã tùy tiện thành String**; hãy dùng byte stream và hợp đồng định dạng riêng.

### 6.1. Charset mặc định không phải hợp đồng dữ liệu

Một số API cũ sử dụng charset mặc định nếu không truyền tham số. Trên các phiên bản Java và môi trường khác nhau, charset mặc định có thể khác nhau; Java 18 trở lên chuẩn hóa mặc định là UTF-8 trong phần lớn cấu hình thông thường theo JEP 400, song vẫn tồn tại ngoại lệ/cấu hình.

Vì thế, mã nguồn xử lý dữ liệu bền vững nên viết rõ `StandardCharsets.UTF_8` ở các điểm chuyển **văn bản ↔ byte**. Điều này giúp người khác đọc code biết chính xác hợp đồng tệp mà không phải đoán theo hệ điều hành hoặc máy chạy.

## 7. Giải mã không hợp lệ: phát hiện thay vì âm thầm thay ký tự

Nếu luồng byte không phải UTF-8 hợp lệ, một số API giải mã có thể **thay ký tự lỗi** bằng ký tự thay thế `�` (`U+FFFD`). Việc thay thế giúp hiển thị tiếp nhưng có thể làm mất khả năng khôi phục nội dung gốc.

Khi nhập dữ liệu cần chính xác, có thể yêu cầu bộ giải mã **báo lỗi**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Decode {
    static String decodeUtf8(byte[] bytes) throws CharacterCodingException {
        return StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
        System.out.println(decodeUtf8(valid)); // Tiếng Việt

        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        try {
            decodeUtf8(invalid);
        } catch (CharacterCodingException ex) {
            System.out.println("UTF-8 khong hop le");
        }
    }
}
~~~

Hai byte `C3 28` không phải một chuỗi UTF-8 hợp lệ: byte tiếp theo sau `C3` không phải continuation byte cần thiết. Nếu hệ thống tự thay bằng `U+FFFD` rồi lưu, dữ liệu đầu vào hỏng đã bị hợp thức hóa thành văn bản mới.

Với dữ liệu quan trọng, quy trình nhập nên:

- Xác định charset từ **hợp đồng nguồn** hoặc metadata đáng tin cậy.
- Giải mã với chính sách lỗi được quyết định rõ: báo lỗi, cách ly bản ghi hay thay thế có kiểm soát.
- Giữ byte gốc ở nơi an toàn nếu cần điều tra/khôi phục, cùng mã lỗi và nguồn nhập.
- Không tự động thử hàng loạt bảng mã rồi chấp nhận kết quả “trông có vẻ đúng” mà không kiểm chứng.

Các thuật toán phát hiện encoding dựa trên thống kê chỉ **ước đoán**. Một chuỗi byte có thể hợp lệ dưới nhiều charset, nhưng lại mang nghĩa hoàn toàn khác nhau.

## 8. Unicode normalization: cùng cách nhìn, khác dãy mã

Trong lưu trữ lâu dài, cùng một tên hoặc mã định danh có thể được nhập từ những thiết bị/hệ điều hành khác nhau. Một bên sinh Unicode dạng dựng sẵn, bên còn lại sinh chữ cái nền và dấu kết hợp.

**Unicode normalization** là quy trình biến đổi chuỗi về một dạng nhất quán.

| Dạng | Ý nghĩa | Sử dụng thận trọng |
| --- | --- | --- |
| **NFC** | Canonical composition; ưu tiên dạng dựng sẵn khi có thể | Thường hợp lý để thống nhất văn bản Unicode lưu và so khớp |
| **NFD** | Canonical decomposition | Hữu ích trong các bài toán phân tích dấu, tương thích một số nguồn |
| **NFKC** | Compatibility decomposition rồi composition | Có thể gộp ký tự khác nhau về nghĩa trình bày; phải xét yêu cầu nghiệp vụ |
| **NFKD** | Compatibility decomposition | Có thể làm mất khác biệt kiểu ký tự; không phải mặc định cho dữ liệu gốc |

Ví dụ Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class NormalizeDemo {
    public static void main(String[] args) {
        String nfc = "ắ";
        String nfd = Normalizer.normalize(nfc, Normalizer.Form.NFD);

        System.out.println(nfc.equals(nfd)); // false
        System.out.println(nfc.codePointCount(0, nfc.length())); // 1
        System.out.println(nfd.codePointCount(0, nfd.length())); // 3
        System.out.println(nfc.getBytes(StandardCharsets.UTF_8).length); // 3
        System.out.println(nfd.getBytes(StandardCharsets.UTF_8).length); // 5

        String canonical = Normalizer.normalize(nfd, Normalizer.Form.NFC);
        System.out.println(nfc.equals(canonical)); // true
    }
}
~~~

**Không phải mọi ký tự có hình dáng giống nhau đều canonically equivalent.** Một chữ Latin “a” và chữ từ bảng chữ cái khác có vẻ giống “a” có thể là code point khác và không được NFC hợp nhất. Chuẩn hóa NFC cũng **không** tự thực hiện chuyển chữ hoa thành chữ thường hoặc bỏ dấu để tìm kiếm.

### 8.1. Chuẩn hóa lúc nào?

Phụ thuộc loại dữ liệu:

- **Tên hiển thị:** có thể lưu dạng NFC để thống nhất biểu diễn; vẫn cần giữ nguyên thông tin người dùng mong muốn nếu sản phẩm đòi hỏi.
- **Khóa tìm kiếm/canonical key:** xác định rõ cách chuẩn hóa, case folding và phiên bản quy tắc; tính khóa ở một nơi thống nhất.
- **Mã định danh kỹ thuật:** cân nhắc giới hạn tập ký tự được phép (ví dụ ID ASCII) nếu yêu cầu nghiệp vụ cho phép.
- **Mật khẩu hoặc dữ liệu đã được ký/định danh bằng hash:** không tự ý chuẩn hóa khi chưa có quy tắc đã thỏa thuận; thay byte có thể thay kết quả kiểm chứng.
- **Văn bản pháp lý hoặc bản gốc cần bằng chứng byte:** giữ riêng byte nguồn nếu tính toàn vẹn bit là yêu cầu, cùng bản văn đã giải mã khi cần tìm kiếm.

Nếu đã có dữ liệu, đổi quy tắc chuẩn hóa có thể làm hai khóa trước đây khác nhau trở thành trùng nhau. Migration cần phát hiện collision và xử lý nghiệp vụ trước khi thêm ràng buộc duy nhất.

## 9. So sánh chuỗi, locale và collation không phải chuyện của UTF-8

Encoding trả lời **lưu thành byte thế nào**. **Collation** trả lời **so sánh và sắp xếp chuỗi thế nào**. Hai chuỗi có byte khác nhau có thể được xem như bằng nhau hoặc gần nhau tùy quy tắc collation, ngôn ngữ và cấu hình hệ quản trị.

Ví dụ, hệ thống tra cứu tên có thể muốn:

- Tìm không phân biệt hoa/thường: `An` và `an` được tìm chung.
- Tìm có phân biệt dấu: `ma`, `má`, `mà` là những từ khác nhau.
- Sắp xếp tên theo quy tắc ngôn ngữ của người dùng, không theo byte UTF-8.
- Ràng buộc khóa tài khoản độc lập với cách viết tên hiển thị.

Mỗi mục tiêu cần được định nghĩa riêng. Không nên suy rằng “lưu UTF-8” sẽ tự động đáp ứng việc so khớp không phân biệt dấu hoặc thứ tự từ điển tiếng Việt.

### 9.1. So sánh phía Java

`String.equals` so sánh các đơn vị ký tự của chuỗi, vì vậy hai chuỗi canonical equivalent nhưng chưa chuẩn hóa có thể trả về `false`.

`String.equalsIgnoreCase` có một số quy tắc bỏ qua khác biệt hoa/thường nhưng **không phải giải pháp hoàn chỉnh cho mọi ngôn ngữ, full case folding, normalization và collation**. Với sắp xếp hiển thị theo locale, Java cung cấp `java.text.Collator`; các đặc tính và dữ liệu locale cần được kiểm thử với bộ từ thực tế của ứng dụng.

Với khóa nghiệp vụ cần tính duy nhất, nên quy định một chính sách canonicalization riêng, có thử nghiệm và không phụ thuộc ngầm vào locale của máy chạy.

### 9.2. So sánh phía database

Database có thể áp dụng collation ở mức database, bảng, cột, biểu thức hoặc index tùy sản phẩm. Collation ảnh hưởng đến:

- Kết quả `ORDER BY`, phép so sánh, lọc theo chuỗi.
- Hành vi ràng buộc `UNIQUE` với một số kiểu/collation.
- Kế hoạch dùng index và việc thay đổi collation/index theo phiên bản.

Đừng giả định mọi database xử lý Unicode, ký tự hoa/thường và dấu giống nhau. Nếu một ứng dụng kiểm tra trùng bằng Java nhưng database dùng so sánh khác, kết quả giữa hai tầng có thể mâu thuẫn.

**Thiết kế an toàn:** định nghĩa rõ nội dung gốc cần hiển thị, khóa tìm kiếm đã chuẩn hóa (nếu cần), cùng các ràng buộc database tương ứng; dùng chính database để bảo đảm uniqueness ở thời điểm ghi đồng thời.

## 10. Unicode ảnh hưởng đến độ dài trường và dung lượng lưu trữ

Trường `VARCHAR(100)` không nên được diễn giải đơn giản thành “tối đa 100 byte” cho mọi hệ quản trị. Quy tắc độ dài có thể tính theo ký tự/code point hoặc byte tùy sản phẩm, kiểu cột và charset.

Ví dụ PostgreSQL trên database mã hóa UTF-8:

~~~sql
SELECT
    char_length('ắ') AS characters,
    octet_length('ắ') AS bytes;
-- characters = 1; bytes = 3 trong UTF-8
~~~

Ngay cả giới hạn theo ký tự/code point cũng không luôn tương đương **100 ký tự hiển thị** vì một grapheme cluster có thể gồm nhiều code point. Nếu sản phẩm yêu cầu giới hạn UI theo ký tự người dùng nhìn thấy, cần một cơ chế phân đoạn grapheme có kiểm chứng và quy tắc nhất quán giữa client/server.

### 10.1. Tại sao phải đo theo byte?

Byte quyết định các giới hạn như:

- Kích thước payload API và thông điệp hàng đợi.
- Dung lượng tệp, bản ghi, index và băng thông.
- Bộ nhớ khi serialize/deserialize và log dữ liệu.
- Giới hạn key/value ở một số hệ thống lưu trữ.

Ví dụ một trường gồm 100 ký tự ASCII có thể chiếm 100 byte UTF-8, còn 100 emoji đơn giản như `😀` có thể chiếm 400 byte UTF-8. Đây chưa kể JSON escaping, cấu trúc bản ghi, index overhead và compression.

Không được định kích thước message hoặc cột lưu trữ chỉ bằng `String.length()`. Nếu giao thức giới hạn byte, hãy đo **byte sau mã hóa đúng charset và định dạng truyền**.

### 10.2. Index trên văn bản

Chỉ mục cho tên, khóa tìm kiếm hoặc mô tả có thể lớn hơn khi văn bản dùng nhiều byte, và việc áp dụng collation có thể thay đổi quy tắc so sánh/chi phí. Với tìm kiếm không phân biệt dấu hoặc full text, có thể cần index hoặc cấu trúc tìm kiếm chuyên biệt tùy database.

Tránh tạo một index duy nhất trên mọi cột văn bản chỉ vì các cột chứa Unicode. Chọn index theo **mẫu đọc/ghi thực tế**, kiểm chứng query plan và tác động tới hiệu năng ghi.

## 11. Charset trong database và kết nối JDBC

Khi dùng cơ sở dữ liệu, cần hiểu ít nhất ba tầng:

1. **Dữ liệu trong Java:** `String` biểu diễn văn bản, được truy cập theo UTF-16 code unit.
2. **Giao thức kết nối/driver:** driver mã hóa và giải mã text khi gửi/nhận từ DB.
3. **Cấu hình lưu trữ của database:** charset, kiểu cột, collation và quy tắc chuyển đổi.

### 11.1. PostgreSQL

PostgreSQL có cấu hình encoding của database và client. Trong môi trường ứng dụng quốc tế, thông thường chọn database encoding `UTF8` để lưu đầy đủ Unicode được hỗ trợ.

Có thể kiểm tra bằng:

~~~sql
SHOW server_encoding;
SHOW client_encoding;

SELECT char_length('Tiếng Việt') AS characters,
       octet_length('Tiếng Việt') AS bytes;
~~~

Các thiết lập mã hóa client/server có quan hệ chuyển đổi trong kết nối; không nên cố “đổi charset” bằng cách lấy byte UTF-8 rồi chuyển thành chuỗi Latin-1 trước khi gửi qua JDBC. Hãy sử dụng `PreparedStatement.setString(...)` và để driver thực hiện trao đổi text theo cấu hình đúng.

Ví dụ minh họa:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

void saveCustomerName(Connection connection, long id, String name)
        throws SQLException {
    String sql = "UPDATE customers SET display_name = ? WHERE id = ?";
    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, name);
        statement.setLong(2, id);
        if (statement.executeUpdate() != 1) {
            throw new SQLException("Khong tim thay ban ghi can cap nhat");
        }
    }
}
~~~

Đoạn trên là phương thức minh họa đặt trong lớp Java, chưa thể tự biên dịch nếu tách khỏi lớp bao quanh. Hệ thống còn phải quản lý transaction, connection, quyền cập nhật và kiểm tra đầu vào theo nghiệp vụ.

### 11.2. MySQL/MariaDB

Trong các phiên bản MySQL/MariaDB có phân biệt bộ mã `utf8mb3` và `utf8mb4`, **`utf8mb4`** là lựa chọn dùng để lưu đầy đủ các ký tự Unicode có biểu diễn UTF-8 dài tới bốn byte, bao gồm nhiều emoji. Bộ mã ba byte không biểu diễn được những code point ngoài BMP.

Tùy phiên bản và sản phẩm, cần kiểm tra:

- Charset và collation của database, bảng, từng cột.
- Charset ở kết nối client/driver.
- Hành vi ràng buộc và index theo collation đang áp dụng.
- Dữ liệu cũ lưu bằng charset khác và giới hạn dung lượng/index khi chuyển đổi.

Không nên dựa vào tên cấu hình `utf8` một cách mơ hồ nếu phiên bản cụ thể có cách diễn giải khác; hãy xác định rõ `utf8mb4` theo tài liệu và môi trường triển khai.

### 11.3. Đọc byte như text hay text như byte?

Trường dữ liệu văn bản nên được lưu trong kiểu text phù hợp và truyền qua API text của driver. Trường dữ liệu nhị phân (ảnh, tệp nén, dữ liệu đã mã hóa, hash byte) nên dùng `BLOB`/`BYTEA` hoặc loại nhị phân tương ứng.

Nếu ứng dụng lấy byte nhị phân, gọi `new String(bytes, UTF_8)` rồi lưu lại, byte không hợp lệ có thể bị thay thế, khiến dữ liệu hỏng. Ngược lại, khi cần lưu một đoạn văn bản, đừng tự biến nó thành chuỗi hiển thị hex hoặc Base64 mà không có yêu cầu nghiệp vụ.

## 12. JSON, HTTP, CSV và trao đổi giữa hệ thống

### 12.1. JSON/HTTP

JSON giao tiếp giữa các hệ thống mở theo RFC 8259 phải sử dụng UTF-8. Đối với request/response JSON, nên thống nhất byte UTF-8 xuyên suốt trình duyệt, client, gateway và backend; để framework JSON thực hiện escaping/giải mã theo chuẩn.

Một số ký tự như dấu ngoặc kép, dấu gạch chéo ngược và ký tự điều khiển cần escape đúng quy tắc JSON. **JSON escaping khác với charset:** chuỗi JSON có thể chứa escape dạng `\uXXXX`, nhưng byte của tài liệu JSON khi truyền vẫn được mã hóa theo UTF-8.

Khi nhận input không tin cậy, giới hạn kích thước theo byte, độ sâu JSON, độ dài chuỗi và kiểm tra nội dung sau khi đã giải mã. Tránh dùng “đã parse JSON” làm bằng chứng dữ liệu nghiệp vụ đã hợp lệ.

### 12.2. CSV và tệp tích hợp

CSV không có một quy tắc charset thống nhất áp dụng cho mọi hệ thống và công cụ. Khi trao đổi CSV, cần nêu rõ:

| Thuộc tính | Ví dụ hợp đồng trao đổi |
| --- | --- |
| Charset | UTF-8 |
| BOM | Không BOM hoặc có BOM theo yêu cầu bộ đọc |
| Dấu phân cách | Dấu phẩy hoặc dấu chấm phẩy đã thống nhất |
| Quy tắc quote | Escape dấu phân cách, dấu quote và xuống dòng đúng định dạng |
| Newline | LF hoặc CRLF theo hợp đồng |
| Dấu số, ngày giờ | Định dạng độc lập locale khi trao đổi máy–máy |
| Kiểm tra nhập | Phát hiện byte không hợp lệ, cột thiếu, ký tự điều khiển không mong muốn |

Một CSV xuất ra để mở bằng bảng tính có thể cần khác CSV đưa vào pipeline tự động. Nếu bản ghi có giá trị bắt đầu bằng các ký tự được spreadsheet diễn giải như công thức, cần bảo vệ đường xuất phù hợp để tránh rủi ro **CSV formula injection**; chọn charset UTF-8 không giải quyết loại rủi ro này.

### 12.3. Log và sao lưu

Log cũng là dữ liệu văn bản được lưu bền vững trong nhiều hệ thống. Hãy quy định encoding UTF-8 cho logger/collector nếu có thể, bảo toàn lỗi đúng bối cảnh, đồng thời che thông tin nhạy cảm.

Backup/restore phải bảo toàn cả **byte của dữ liệu** và **metadata cần giải mã** như encoding, collation, phiên bản schema. Một bản dump “có dữ liệu” nhưng restore với cấu hình khác khiến chữ hiển thị sai vẫn là một sự cố toàn vẹn dữ liệu.

## 13. Lỗi mojibake và cách chẩn đoán

**Mojibake** là hiện tượng văn bản trở thành ký tự lạ vì byte được diễn giải theo encoding sai, đôi khi qua nhiều lần encode/decode.

Ví dụ một đường lỗi phổ biến:

~~~text
Ký tự ban đầu: é
Unicode:         U+00E9
Mã hóa UTF-8:    C3 A9
Đọc nhầm Windows-1252: Ã©
Ghi lại "Ã©" bằng UTF-8: C3 83 C2 A9
~~~

Ở bước cuối, file đã chứa một chuỗi văn bản khác. Chỉ đổi header “charset=utf-8” không tự biến `Ã©` trở lại `é`.

Các dấu hiệu và nguyên nhân thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `Ã©` hoặc các chuỗi tương tự | UTF-8 được giải mã như charset một byte | Kiểm tra byte gốc và charset tại điểm đọc |
| Dấu `�` xuất hiện | Dữ liệu không hợp lệ đã bị thay thế khi giải mã | Xác định bước tạo U+FFFD; tìm byte nguồn chưa mất |
| Chữ thành `?` | Charset ghi không biểu diễn được ký tự, hoặc chuyển đổi thay thế | Kiểm tra bộ mã của điểm ghi và chính sách encoder |
| Emoji không lưu được | Charset/cột/kết nối không hỗ trợ ký tự ngoài BMP | Kiểm tra encoding và cấu hình DB/driver |
| Hai tên nhìn như giống nhau nhưng truy vấn không khớp | Khác dạng normalization, collation hoặc ký tự tương tự | So code point, NFC/NFD, quy tắc tìm kiếm |
| Header CSV đầu tiên có ký tự lạ | BOM bị đọc thành dữ liệu | Kiểm tra byte `EF BB BF` đầu tệp |
| Ký tự đổi nghĩa sau export/import | Các hệ thống dùng charset khác nhau | Kiểm tra ranh giới xuất, tệp trung gian và nhập |

### Quy trình điều tra từng bước

1. **Khoanh vùng:** lỗi xuất hiện ở API response, màn hình, database, CSV hay log? So sánh cùng một bản ghi ở các điểm.
2. **Lấy một mẫu có thể tái hiện:** tên tiếng Việt, dấu kết hợp, emoji; ghi lại kết quả mong đợi và kết quả đang thấy.
3. **Giữ byte đầu vào nếu được phép:** kiểm tra dưới dạng hex và metadata nguồn; không ghi đè bản hỏng trước khi có bản sao.
4. **Kiểm tra charset từng biên:** input HTTP, thư viện CSV, `String` Java, driver và cấu hình DB, output exporter.
5. **Kiểm tra code point:** xem dữ liệu đã đổi nghĩa hay chỉ khác normalization/collation.
6. **Tìm chuyển đổi sai đầu tiên:** sửa ở ranh giới phát sinh lỗi, không chữa bằng các bước encode/decode chồng lên nhau.
7. **Thử phục hồi trên bản sao:** đánh giá có thể hoàn nguyên từ byte gốc hay đã bị thay thế không thể phục hồi.
8. **Bổ sung kiểm thử round trip** cho ngôn ngữ và định dạng thực tế.

**Không tự động thay `Ã` thành một ký tự khác trên toàn bộ database.** Dữ liệu thật có thể chứa các chuỗi đó hợp lệ; thao tác thay hàng loạt sẽ phá nội dung không bị lỗi.

## 14. Charset có liên hệ thế nào với bảo mật?

Lỗi mã hóa không chỉ làm hỏng hiển thị; nó còn có thể khiến nhiều tầng ứng dụng **diễn giải đầu vào khác nhau**.

- **Validation trước và sau giải mã:** bộ lọc trên raw bytes có thể bỏ sót ký tự sau khi giải mã hoặc sau normalization.
- **Identifier giả mạo:** các ký tự từ bảng chữ cái khác nhau có thể trông giống nhau (homoglyph/confusable); NFC không tự phát hiện mọi trường hợp.
- **Tính duy nhất:** nếu service coi hai tên đăng nhập khác nhau nhưng database coi chúng bằng nhau theo collation, yêu cầu có thể gặp lỗi hoặc xung đột khó đoán.
- **Chữ hoa/chữ thường theo locale:** quy tắc chuyển case phụ thuộc ngôn ngữ; không dùng những quy tắc ngầm định cho khóa bảo mật mà không kiểm thử.
- **Chữ ký và hash:** nếu một bên ký byte trước normalization và bên kia xác minh byte sau normalization, chữ ký có thể không khớp.
- **Log:** ký tự điều khiển và xuống dòng có thể làm giả nhiều dòng log; cần encode/escape phù hợp khi ghi.

Với dữ liệu có giá trị định danh, một quy trình hợp lý thường là:

1. Giải mã đầu vào bằng charset được quy định và chính sách lỗi rõ.
2. Thực hiện canonicalization theo **quy tắc của chính trường đó**, nếu nghiệp vụ cho phép.
3. Kiểm tra tập ký tự, chiều dài, định dạng và quyền truy cập.
4. Ghi giá trị gốc/giá trị chuẩn hóa theo thiết kế và dùng ràng buộc duy nhất tại database.
5. Giữ phiên bản/quy tắc canonicalization đủ ổn định để các phiên bản ứng dụng đồng ý với nhau.

Điều này không có nghĩa phải chuẩn hóa hoặc loại bỏ dấu trong mọi trường. Tên người, mật khẩu, văn bản tự do và mã kỹ thuật có yêu cầu khác nhau; cần quyết định rõ cho từng loại dữ liệu.

## 15. Migration charset khi dữ liệu đã tồn tại

Chuyển một hệ thống cũ sang UTF-8 đòi hỏi nhiều hơn việc đổi cấu hình. Nếu dữ liệu trước đó đã được giải mã sai, chuyển charset của cột có thể **giữ nguyên nội dung sai** hoặc làm nó tệ hơn.

Một quy trình an toàn:

1. **Khảo sát nguồn:** xác định hệ thống, encoding thật, nguồn tệp, bảng và trường có văn bản; lấy mẫu đại diện tiếng Việt, ngoại ngữ, ký tự đặc biệt.
2. **Sao lưu và kiểm tra restore:** đảm bảo có thể quay lại dữ liệu gốc; lưu byte và metadata phục vụ phân tích.
3. **Phân loại lỗi:** dữ liệu đúng nhưng encoding cũ, byte sai charset, mojibake đã được lưu như text, ký tự đã bị thay bằng `?` hoặc `�`.
4. **Lập quy tắc chuyển đổi có thể tái hiện:** mỗi loại dữ liệu có cách chuyển cụ thể; không dùng một phép thay chuỗi cho toàn bộ nguồn.
5. **Tạo bản migration thử nghiệm:** chuyển trên bản sao và so sánh nội dung, số hàng, khóa, trường dài, collation và ràng buộc.
6. **Đánh giá uniqueness/collision:** tên hoặc khóa sau chuẩn hóa/collation mới có thể trở thành trùng, cần chính sách giải quyết.
7. **Chuyển ứng dụng đồng bộ:** cấu hình JDBC, API, exporter, import và schema phải đọc/ghi theo cùng hợp đồng.
8. **Giám sát sau cutover:** kiểm tra tỷ lệ lỗi giải mã, ký tự thay thế mới, độ dài dữ liệu và hiệu năng truy vấn/index.

Nếu chuyển từ một charset legacy sang Unicode, hãy phân biệt **chuyển mã (transcoding)** với **sửa dữ liệu đã bị diễn giải sai**. Trường hợp byte gốc không còn và đã bị thay thành dấu hỏi, có thể không thể phục hồi chính xác từng ký tự; cần báo giới hạn này rõ ràng.

### 15.1. Schema evolution đi cùng migration

Đổi charset/collation có thể ảnh hưởng tới index, thứ tự sắp xếp, so khớp tìm kiếm và giới hạn chiều dài cột. Khi triển khai nhiều phiên bản ứng dụng, cần lên kế hoạch tương thích giữa bản cũ và bản mới, kiểm chứng trên kích thước dữ liệu đại diện và có phương án quay về.

Không nên coi migration đã hoàn tất chỉ vì câu lệnh thay đổi schema trả thành công. Cần thử **đọc lại toàn bộ lớp dữ liệu liên quan**, bao gồm API, file xuất và các tác vụ nền.

## 16. Hiệu năng và chi phí khi chọn charset

UTF-8 sử dụng số byte biến thiên; văn bản chủ yếu là ASCII thường nhỏ gọn. Tuy nhiên, kích thước thực còn phụ thuộc nội dung, nén dữ liệu, index và cấu trúc bản ghi.

Các điểm cần đo:

| Thành phần | Chỉ số nên xem | Tác động |
| --- | --- | --- |
| Trường text trong DB | Byte trung bình/tối đa, tốc độ tăng | Disk, bộ đệm dữ liệu và backup |
| Index trên text | Kích thước index, độ chọn lọc, query plan | Tốc độ tìm kiếm và chi phí insert/update |
| API JSON | Payload byte, thời gian encode/decode | Network và CPU |
| Java service | Allocation, GC, số lần chuyển byte ↔ String | Độ trễ và bộ nhớ |
| Export/import | Throughput, lỗi giải mã, dung lượng file | Kế hoạch batch, checkpoint |
| Tìm kiếm theo locale | Chi phí collation/normalization | CPU, index và tính nhất quán kết quả |

Không nên tối ưu bằng cách “bỏ dấu tiếng Việt để tiết kiệm byte”: thao tác đó làm mất thông tin nghiệp vụ. Nếu một hệ thống có khối lượng văn bản lớn, hãy đo nén, cấu trúc dữ liệu và mẫu truy vấn rồi chọn cách tối ưu không phá nội dung.

## 17. Bộ trường hợp kiểm thử tối thiểu

Để xác nhận dữ liệu tồn tại đúng từ API đến database và quay lại, nên có ít nhất các trường hợp:

| Trường hợp | Giá trị kiểm tra | Mục tiêu |
| --- | --- | --- |
| ASCII | `Order-123` | Tương thích với chuỗi cơ bản |
| Tiếng Việt dựng sẵn | `Nguyễn Thị Ánh` | Không mất dấu khi round trip |
| Dấu kết hợp | `ắ` ở NFC và NFD | Kiểm tra normalization, equality và độ dài |
| Ký tự ngoài BMP | `😀` | UTF-8 bốn byte, UTF-16 surrogate pair |
| Ngoại ngữ | `日本語 / العربية` | Không giả định dữ liệu chỉ dùng Latin |
| Emoji ghép | Một emoji gồm nhiều code point | Không cắt giữa grapheme cluster |
| Ký tự điều khiển | Tab, newline, quote | JSON/CSV/log escape đúng |
| Byte UTF-8 sai | `C3 28` | Từ chối hoặc xử lý lỗi theo hợp đồng |
| BOM UTF-8 | `EF BB BF` ở đầu file | Nhận diện theo định dạng nhập |
| Chuỗi dài | Văn bản gần giới hạn cột và payload | Kiểm tra số byte, độ dài và truncate |
| Case/collation | `An` so với `an` | Kết quả tìm kiếm và uniqueness đã thống nhất |
| Export/import | Ghi DB → CSV → import lại | Không đổi dữ liệu hoặc metadata ngoài dự kiến |

Kiểm thử **round trip** có thể gồm: tạo chuỗi đầu vào → ghi qua repository → commit → đọc lại trên kết nối/phiên xử lý khác → xuất API/file → nhập lại → so sánh theo hợp đồng đã chọn (so sánh nguyên văn hay so sánh sau normalization). Nên kiểm thử cả trường hợp rollback/lỗi ghi để không nhầm lỗi toàn vẹn dữ liệu với lỗi encoding.

### 17.1. Bài tập 1: đếm byte và code point

Cho chuỗi Java `"Aắ😀"`. Không chạy chương trình, hãy tính:

1. `String.length()`.
2. `codePointCount(0, length())`.
3. Số byte UTF-8.

**Gợi ý đáp án:** lần lượt **4 code unit**, **3 code point** và **8 byte**. Emoji dùng hai code unit và bốn byte UTF-8.

### 17.2. Bài tập 2: hai chuỗi nhìn giống nhau

Một bản ghi lưu chữ “ắ” dạng `U+1EAF`; bản ghi khác lưu dạng `U+0061 U+0306 U+0301`. Hãy giải thích vì sao `String.equals` có thể trả `false`, rồi dùng `Normalizer.normalize(..., Normalizer.Form.NFC)` để kiểm tra sự tương đương chuẩn tắc.

**Gợi ý:** normalize cả hai chuỗi về NFC trước khi so sánh theo quy tắc ứng dụng; không dùng thao tác này để thay thế yêu cầu collation/uniqueness trong DB.

### 17.3. Bài tập 3: lỗi chuyển mã

Một tệp chứa byte `C3 A9`, nhưng bộ đọc hiển thị `Ã©`. Xác định bộ mã có thể đã được dùng khi ghi và khi đọc; nêu vì sao việc lưu lại “Ã©” bằng UTF-8 khiến dữ liệu thay đổi.

**Gợi ý:** byte gốc là UTF-8 của `é`, nhưng bị đọc bằng Windows-1252; lần ghi lại tạo UTF-8 của chuỗi sai.

### 17.4. Bài tập 4: thiết kế trường tên đăng nhập

Ứng dụng cho phép tên đăng nhập Unicode không phân biệt hoa/thường. Hãy xác định: có cho phép ký tự dễ nhầm lẫn không, chuẩn hóa dạng nào, chính sách case folding/collation ra sao, lưu khóa canonical và ràng buộc unique tại đâu, xử lý collision khi migration thế nào.

**Gợi ý:** phải có một quy tắc thống nhất giữa ứng dụng và database; không thể chỉ dựa vào `String.toLowerCase()` theo locale mặc định rồi cho rằng mọi tên trùng đã được phát hiện.

## 18. Checklist chọn charset và thiết kế persistence cho văn bản

- [ ] Mọi ranh giới chuyển **byte ↔ text** có charset xác định rõ (ưu tiên UTF-8 khi phù hợp).
- [ ] Đã hiểu `String.length()` đếm UTF-16 code unit; giới hạn theo byte và grapheme được xử lý riêng.
- [ ] Có chính sách với byte không hợp lệ, U+FFFD và BOM khi import/export.
- [ ] Đã chọn nhu cầu normalization theo từng loại dữ liệu, phân biệt NFC/NFD với NFKC/NFKD.
- [ ] Quy tắc so sánh/ordering/case folding/collation phù hợp nghiệp vụ và nhất quán giữa Java/DB.
- [ ] Database, driver, connection và kiểu cột hỗ trợ đầy đủ ký tự cần lưu, bao gồm ký tự ngoài BMP nếu cần.
- [ ] Ràng buộc duy nhất, schema và index đã được kiểm tra với dữ liệu Unicode đại diện.
- [ ] Không chuyển dữ liệu nhị phân qua String; dữ liệu JSON/CSV/log được escape và mã hóa đúng định dạng.
- [ ] Có kịch bản migration, sao lưu, restore và phát hiện collision khi thay charset/collation.
- [ ] Đã kiểm thử round trip từ API tới database, qua restart, xuất file rồi nhập lại.
- [ ] Đã đo dung lượng byte, hiệu năng query/index, allocation và lỗi encode/decode theo khối lượng thực tế.

## 19. Tổng kết

**Unicode cho văn bản một hệ thống định danh ký tự; charset quyết định những ký tự ấy được biểu diễn bằng byte như thế nào.** Trong ứng dụng Java, `String` xử lý theo UTF-16 code unit, còn dữ liệu trao đổi và lưu trữ thường nên có hợp đồng mã hóa UTF-8 rõ ràng.

Thiết kế persistence đúng phải đảm bảo **đọc lại vẫn hiểu đúng dữ liệu đã ghi**: không giải mã nhầm, không làm mất dấu, không nhầm code point với ký tự hiển thị, không để collation và normalization âm thầm thay đổi tính duy nhất của khóa. Kết hợp lựa chọn charset với schema, query, index, giao dịch, bảo mật, sao lưu và kiểm thử xuyên suốt giúp dữ liệu văn bản của ứng dụng Java vừa bền vững, vừa toàn vẹn và có thể tiến hóa an toàn theo thời gian.
