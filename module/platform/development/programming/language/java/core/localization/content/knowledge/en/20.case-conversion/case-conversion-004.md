# Locale.ROOT cho định danh kỹ thuật khi phù hợp trong Java

## 1. Vấn đề: định danh kỹ thuật không nên phụ thuộc ngôn ngữ của máy chạy

Khi ứng dụng chuyển chuỗi thành chữ thường/chữ hoa, cách biến đổi có thể **phụ thuộc `Locale`**. Với văn bản giao diện, điều này là cần thiết để tôn trọng quy tắc ngôn ngữ; nhưng với một **định danh kỹ thuật** như tên field của giao thức, mã cấu hình hoặc key quy ước ASCII, kết quả biến đổi thay đổi theo locale mặc định có thể làm hỏng việc tra cứu và kiểm thử.

Ví dụ Java:

```java
String name = "TITLE";

String root = name.toLowerCase(Locale.ROOT); // "title"
String turkish = name.toLowerCase(
        Locale.forLanguageTag("tr-TR"));    // "t\u0131tle" (i không chấm)
```

Hai chuỗi trông hơi giống nhau nhưng khác code point: trong tiếng Thổ Nhĩ Kỳ, chữ hoa `I` có chữ thường tương ứng `ı` (U+0131, *dotless i*). Nếu ứng dụng dùng `name.toLowerCase()` không truyền locale, phương thức dựa vào **default locale**, và một service được chạy với locale khác có thể tạo ra **key khác nhau từ cùng đầu vào**.

Khi chính sách kỹ thuật cần chuyển chữ hoa/thường **không phụ thuộc một ngôn ngữ cụ thể**, `Locale.ROOT` là lựa chọn thường thích hợp:

```java
String canonical = rawKey.toLowerCase(Locale.ROOT);
```

Tuy vậy, **không phải mọi định danh đều nên bị chuyển chữ thường**, và **Locale.ROOT không phải một bộ Unicode case folding, validator hoặc sanitizer hoàn chỉnh**. Quy tắc quyết định phải xuất phát từ đặc tả định danh và dữ liệu nguồn.

### Mục tiêu

- Hiểu `Locale.ROOT` là gì và khác locale mặc định như thế nào.
- Biết khi nào dùng `toLowerCase(Locale.ROOT)` / `toUpperCase(Locale.ROOT)` cho **technical identifier**.
- Nhận diện bẫy Turkish-I, biến đổi có thể tăng số code point, Unicode normalization và các trường hợp Unicode phức tạp.
- Phân biệt **identifier có quy tắc ASCII**, **identifier Unicode**, **text bản địa hóa**, **username**, **password**, **URL/path/database key**.
- Viết mã Java 17+ kiểm tra grammar trước khi chuẩn hóa khi hợp đồng quy định ASCII.
- Tránh lỗi bảo mật do chuẩn hóa không nhất quán, trùng key, giả định mọi so sánh không phân biệt hoa/thường đều giống nhau.

## 2. Locale.ROOT là gì?

`java.util.Locale.ROOT` là một hằng `Locale` đại diện cho **locale trung lập về ngôn ngữ, quốc gia và biến thể**: không chỉ định một ngôn ngữ/địa phương cụ thể. Nó hữu ích ở những thao tác muốn quy tắc xử lý tổng quát, không lấy văn hóa của máy làm nguồn điều khiển.

So sánh các lựa chọn:

| Lựa chọn | Ý nghĩa | Rủi ro hoặc mục đích |
| --- | --- | --- |
| `Locale.ROOT` | Locale trung lập, không gắn một ngôn ngữ/địa phương. | Phù hợp cho một số phép biến đổi kỹ thuật có ý nghĩa trung lập. |
| `Locale.ENGLISH` | Ngôn ngữ tiếng Anh. | Có thể hợp với hành vi gắn tiếng Anh, nhưng biểu đạt khác ROOT về ý nghĩa. |
| `Locale.US` | Ngôn ngữ/vùng tiếng Anh tại Hoa Kỳ. | Dùng khi định dạng theo quy ước Hoa Kỳ, không phải mặc định của mọi giao thức. |
| `Locale.forLanguageTag("tr-TR")` | Tiếng Thổ Nhĩ Kỳ ở Thổ Nhĩ Kỳ. | Quy tắc chữ I khác tiếng Anh. |
| `Locale.getDefault()` | Locale mặc định của JVM. | Có thể thay đổi giữa máy chạy, CI, container, test. |
| `Locale.getDefault(Locale.Category.FORMAT)` | Mặc định cho định dạng số/ngày giờ. | Không thay thế locale trung lập của tên key kỹ thuật. |

`Locale.ROOT` không có nghĩa **English**: một key kỹ thuật không tự biến thành tiếng Anh; nó chỉ cho các API locale-aware một đối tượng locale không được ràng buộc với ngôn ngữ cụ thể. Cần hiểu từng API sẽ xử lý ROOT ra sao, không tự suy rằng mọi phương thức Java dùng ROOT đều “quốc tế hóa đúng” trong mọi tình huống.

### Cách dùng thường gặp

```java
String normalizedHeader = "X-REQUEST-ID"
        .toLowerCase(Locale.ROOT); // "x-request-id"

String normalizedSetting = "SERVER_MODE"
        .toLowerCase(Locale.ROOT); // "server_mode"
```

Các ví dụ này chỉ đúng về **mặt quy tắc kỹ thuật** nếu đặc tả của header/setting cho phép so sánh không phân biệt chữ hoa/chữ thường. Đối với định danh **case-sensitive**, việc chuyển chữ thường là thay đổi giá trị, nên phải giữ nguyên.

## 3. Vì sao toLowerCase() không tham số nguy hiểm với key kỹ thuật?

Trong Java:

```java
value.toLowerCase()
```

tương ứng thao tác chữ thường theo **locale mặc định của môi trường**, không có bảo đảm luôn dùng những phép biến đổi Latin/ASCII người viết đang nghĩ đến. Chạy cùng code ở hai môi trường có thể sinh ra kết quả khác.

Cụ thể với `"TITLE"`:

| API | Kết quả mô tả |
| --- | --- |
| `"TITLE".toLowerCase(Locale.ROOT)` | `title`, code points `U+0074 U+0069 U+0074 U+006C U+0065`. |
| `"TITLE".toLowerCase(Locale.ENGLISH)` | `title` trong ví dụ. |
| `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))` | `tıtle`, với ký tự thứ hai là `U+0131`. |
| `"TITLE".toLowerCase()` | Phụ thuộc `Locale.getDefault()`; không phù hợp làm key ổn định nếu default locale không được cố định. |

Một lỗi thường gặp:

```java
Map<String, String> settings = Map.of("title", "enabled");
String input = "TITLE";
String lookedUp = settings.get(input.toLowerCase());
// Có thể nhận null trên JVM có default locale tiếng Thổ Nhĩ Kỳ.
```

Đoạn này là **mã minh họa trong phương thức**, không phải chương trình độc lập. Sai lầm không phải vì tiếng Thổ Nhĩ Kỳ “không chuẩn”, mà vì **một định danh kỹ thuật đã bị xử lý theo một quy tắc ngôn ngữ không nằm trong đặc tả của nó**.

Cách sửa khi domain đã quy định tên key không phân biệt hoa/thường và cần phép chuyển đổi trung lập:

```java
String lookedUp = settings.get(
        input.toLowerCase(Locale.ROOT));
```

**Không sửa bằng `Locale.setDefault(Locale.US)` toàn JVM.** Mặc định JVM là trạng thái chung, dễ làm test hoặc luồng xử lý khác bị ảnh hưởng. Dữ liệu UI thực sự cần tiếng Thổ Nhĩ Kỳ lại phải được phép định dạng theo tiếng Thổ Nhĩ Kỳ.

## 4. Định danh nào nên dùng Locale.ROOT?

Từ khóa **“khi phù hợp”** là quan trọng nhất. Trước khi gọi `toLowerCase(Locale.ROOT)`, hãy hỏi hai điều:

1. **Đặc tả có quy định identifier được so sánh không phân biệt hoa/thường không?**
2. **Đặc tả có quy định cách chuẩn hóa cụ thể không?** Nếu có, tuân theo đặc tả đó; ROOT là một công cụ có thể giúp thực hiện một phần, không thay thế đặc tả.

### Trường hợp thường phù hợp

- **Tên tùy chọn cấu hình nội bộ** do nhóm tự định nghĩa là case-insensitive, chỉ cho phép ASCII, ví dụ `SERVER_MODE` và `server_mode` cùng chỉ một setting.
- **Tên header hoặc token giao thức** được giao thức định nghĩa là ASCII và case-insensitive, nếu dự án thực sự cần chuyển sang một dạng canonical string để map lookup.
- **Tên định danh kỹ thuật nhập từ một nguồn nhiều môi trường** có quy ước rõ: bộ ký tự, dấu phân cách, so sánh không phân biệt case và dạng canonical.
- **Tên lệnh/tùy chọn dòng lệnh** nếu CLI của ứng dụng đã quyết định chấp nhận nhiều cách viết hoa/thường.

Trong các trường hợp trên, kiểm soát **grammar** trước/đồng thời với phép chuyển chữ thường thường đáng tin hơn là áp `toLowerCase(Locale.ROOT)` lên chuỗi tùy ý.

### Trường hợp không nên tự tiện biến đổi

| Dữ liệu | Vì sao không tự chuyển chữ thường? | Hướng xử lý |
| --- | --- | --- |
| **Token API, mật khẩu, chữ ký, hash** | Thường là dữ liệu phân biệt chính xác từng byte/ký tự. | Giữ nguyên, so sánh theo đặc tả bảo mật; tránh biến đổi tùy tiện. |
| **UUID, mã giao thức có parser riêng** | Format chuẩn có thể đã được định nghĩa bởi API/parser. | Dùng `UUID.fromString` hoặc parser chính thức khi thích hợp. |
| **Tên file, đường dẫn** | Hệ file có quy tắc case sensitivity/normalization khác nhau. | Dùng API đường dẫn và chính sách của nền tảng, không tự “lowercase path”. |
| **URL đầy đủ** | Chỉ một số thành phần có quy tắc không phân biệt hoa/thường; path/query thường có ý nghĩa case-sensitive. | Parse URL/URI theo cấu trúc và xử lý từng thành phần đúng chuẩn. |
| **Username, email address** | Case sensitivity, Unicode, collation và identity policy do hệ thống sở hữu quyết định. | Định nghĩa rõ chính sách tài khoản, tránh giả định email local-part hay username toàn cục case-insensitive. |
| **Tên riêng, tiêu đề, câu giao diện** | Quy tắc chữ hoa/thường phụ thuộc ngôn ngữ người dùng. | Truyền `Locale` phù hợp của văn bản. |
| **Mã định danh Unicode tùy ý** | ROOT lowercase chưa chắc là phép **Unicode case folding** mong muốn. | Định nghĩa Unicode profile và dùng normalization/case-folding phù hợp. |
| **Database key có collation riêng** | Collation/normalization và Java lowering có thể không trùng. | Đồng bộ đặc tả giữa application và database. |

Đặc biệt, nếu quy tắc định danh nói “case-sensitive”, `Locale.ROOT` vẫn **không cho phép** chuyển dữ liệu. Ví dụ key JSON object và tên field trong một API có thể được phân biệt theo chữ hoa/chữ thường; việc gộp `"UserID"` với `"userId"` có thể phá hợp đồng.

## 5. Quy tắc an toàn cho identifier ASCII

Nếu hệ thống thiết kế key theo **ASCII** và case-insensitive, một cách dễ bảo trì là:

1. **Kiểm tra đầu vào** đúng tập ký tự mà đặc tả cho phép.
2. **Chuyển sang dạng canonical** bằng `Locale.ROOT` nếu đặc tả nói hai dạng case tương đương.
3. **Dùng dạng canonical nhất quán** khi lưu và tìm.
4. **Định nghĩa chính sách khi trùng key sau chuyển đổi**, không âm thầm ghi đè.

Giả sử ứng dụng chấp nhận key có chữ cái ASCII đầu tiên, theo sau là chữ ASCII, số, dấu gạch dưới hoặc gạch nối:

```text
[A-Za-z][A-Za-z0-9_-]*
```

Mẫu này chỉ là **hợp đồng của ví dụ**, không phải cú pháp bắt buộc cho mọi key kỹ thuật hay mọi HTTP header. Khi input là `SERVER_MODE`, `server_mode` hoặc `Server_Mode`, chúng đều hợp grammar và có thể canonicalize thành `server_mode`.

Mã minh họa:

```java
private static final Pattern TECHNICAL_KEY =
        Pattern.compile("[A-Za-z][A-Za-z0-9_-]*");

static String canonicalAsciiKey(String key) {
    if (key == null || !TECHNICAL_KEY.matcher(key).matches()) {
        throw new IllegalArgumentException("Invalid technical key");
    }
    return key.toLowerCase(Locale.ROOT);
}
```

Đoạn này thuộc phạm vi một class Java, cần import `java.util.Locale` và `java.util.regex.Pattern`; chương trình đầy đủ ở mục 8.

### Vì sao validate trước khi lower?

Nếu input chứa một ký tự không thuộc grammar ASCII, việc lowercase có thể thay đổi số lượng code point hoặc tạo ra chuỗi vô tình giống một key hợp lệ/khác. Một validator rõ ràng **từ chối** thay vì lặng lẽ chấp nhận giá trị ngoài đặc tả.

Với giao thức có grammar khác, không dùng regex mẫu bên trên; phải dùng grammar của giao thức thật. Ngoài ra, một số giao thức chuẩn hóa tên ASCII theo cách không yêu cầu Unicode case conversion; nếu cần đạt chính xác một chuẩn, áp chuẩn đó.

### Không dùng lowercase để thay thế sanitization

`Locale.ROOT` không loại bỏ đường dẫn `../`, ký tự điều khiển, ký tự không nhìn thấy, chuỗi SQL hay các ký tự có ý nghĩa riêng trong một ngữ cảnh. Với header/CLI/key, hãy tách rõ **validation**, **canonicalization**, **escaping tại output** và **authorization**. Không có một phép chuyển chữ hoa/thường nào thay thế được bốn trách nhiệm ấy.

## 6. Unicode case mapping: Locale.ROOT vẫn có quy tắc Unicode

**Case conversion** trong Java không phải lúc nào cũng biến một code point thành đúng một code point. Có những phép biến đổi tạo nhiều ký tự, hoặc phụ thuộc ngữ cảnh của chuỗi.

### 6.1. Dấu chấm trên chữ I

Xét chữ Latin capital I with dot above `İ` (U+0130):

```java
String dottedCapitalI = "\u0130";
String rootLower = dottedCapitalI.toLowerCase(Locale.ROOT);
```

Theo Unicode case mapping của Java 17, `rootLower` có hai code point:

```text
U+0069 U+0307
```

Tức chữ `i` và dấu chấm tổ hợp phía trên. Đây không phải một ký tự ASCII `i` đơn lẻ. Vì vậy, **Locale.ROOT không biến mọi chữ Unicode thành ASCII**, và một phép lowerCase không phải bộ lọc ký tự.

### 6.2. Chuyển chữ hoa có thể làm chuỗi dài thêm

Ví dụ chữ `ß` (U+00DF):

```java
String upper = "stra\u00DFe".toUpperCase(Locale.ROOT);
// "STRASSE"
```

Cùng một từ có thể đổi độ dài theo số ký tự/các code point sau khi case conversion. Không giả định:

```text
input.length() == input.toUpperCase(Locale.ROOT).length()
```

luôn đúng.

Đặc biệt, khi xây chỉ số substring, giới hạn độ dài hoặc khóa map, phải quyết định việc biến đổi nào được phép và xử lý vấn đề trùng key sau biến đổi.

### 6.3. Các phép biến đổi không phải Unicode case folding đầy đủ

Một số nhu cầu so sánh không phân biệt hoa/thường đòi quy tắc **Unicode case folding**, có thể kết hợp normalization và các quy tắc bổ sung; `toLowerCase(Locale.ROOT)` không tương đương thuật toán case folding đầy đủ cho mọi dữ liệu Unicode.

Ví dụ phân biệt:

- `String.toLowerCase(Locale.ROOT)`: trả một chuỗi chuyển chữ thường theo quy tắc Unicode/ROOT được Java sử dụng.
- `String.equalsIgnoreCase(...)`: so sánh không phân biệt hoa/thường theo quy tắc riêng của Java, **không có tham số Locale**.
- `Collator`: so sánh/sắp xếp văn bản tự nhiên theo locale, phù hợp với yêu cầu ngôn ngữ ở nhiều trường hợp, không phải công cụ tạo identifier canonical.
- Một thư viện Unicode chuyên dụng: có thể cung cấp case folding/normalization profile (chẳng hạn các chức năng tương ứng trong ICU4J), cần thiết kế và kiểm thử theo chính sách định danh cụ thể.

**Không suy luận `a.equalsIgnoreCase(b)` luôn giống `a.toLowerCase(Locale.ROOT).equals(b.toLowerCase(Locale.ROOT))`.** Hai thao tác có hợp đồng khác nhau, có thể cho kết quả khác với những ký tự Unicode đặc biệt.

## 7. Unicode normalization và vấn đề trùng key

Việc chuyển chữ hoa/thường không tự chuẩn hóa dạng dựng sẵn và dạng tổ hợp:

```java
String composed = "\u00E9";    // U+00E9: é
String decomposed = "e\u0301"; // U+0065 U+0301

System.out.println(composed.equals(decomposed)); // false
```

Hai chuỗi có thể trông giống nhau nhưng khác Unicode sequence. Nếu định danh **cho phép Unicode**, hệ thống phải định nghĩa liệu hai dạng ấy là cùng một identifier hay khác nhau.

Một chính sách có thể bao gồm:

- Giới hạn bộ ký tự cho phép.
- Chọn dạng normalization (ví dụ NFC khi đúng mục đích).
- Chọn thuật toán case-insensitive so sánh thích hợp.
- Chọn thứ tự xử lý normalization, case folding và các phép kiểm tra khác theo tiêu chuẩn đã chọn.
- Xử lý khóa trùng, cập nhật/migration dữ liệu cũ và lịch sử tên đăng nhập.
- Bảo vệ trước ký tự tương tự thị giác (*confusables*) và những ký tự vô hình nếu đây là identity có rủi ro bảo mật.

**Không tự áp NFKC hoặc lowercase toàn bộ username/password** khi chưa có hợp đồng. Những biến đổi này có thể thay đổi dữ liệu người dùng, gây trùng định danh hoặc phá tương thích với hệ thống có sẵn. Với identifier kỹ thuật chỉ dùng ASCII, kiểm tra ASCII grammar trước khi canonicalization sẽ tránh nhiều vấn đề phức tạp hơn.

### Case conversion không tương đương việc bỏ dấu

`Locale.ROOT` không được thiết kế để “bỏ dấu tiếng Việt”. Việc loại bỏ dấu có thể làm thay đổi ý nghĩa tên riêng hoặc trùng nhiều chuỗi vốn khác nhau. Nếu ứng dụng cần tìm kiếm không phân biệt dấu, hãy thiết kế cơ chế search/index riêng với quy tắc locale và dữ liệu thử nghiệm phù hợp, không dùng lowercase ROOT như giải pháp chung.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo file **`RootIdentifierDemo.java`** với một validator cho **identifier ASCII do ứng dụng định nghĩa**, một hàm canonicalize bằng ROOT, cùng các phép thử Unicode thể hiện giới hạn của phương pháp.

```java
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class RootIdentifierDemo {

    private static final Pattern TECHNICAL_KEY =
            Pattern.compile("[A-Za-z][A-Za-z0-9_-]*");

    private static String canonicalAsciiKey(String raw) {
        if (raw == null
                || !TECHNICAL_KEY.matcher(raw).matches()) {
            throw new IllegalArgumentException(
                    "Invalid technical key");
        }
        return raw.toLowerCase(Locale.ROOT);
    }

    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String title = "TITLE";

        System.out.println("root="
                + title.toLowerCase(Locale.ROOT));
        System.out.println("turkishCodePoints="
                + codePoints(title.toLowerCase(
                        Locale.forLanguageTag("tr-TR"))));

        System.out.println("canonical="
                + canonicalAsciiKey("SERVER_MODE"));
        System.out.println("sameKey="
                + canonicalAsciiKey("SERVER_MODE").equals(
                        canonicalAsciiKey("server_mode")));

        try {
            canonicalAsciiKey("\u0130D");
            System.out.println("unicodeKey=ACCEPTED");
        } catch (IllegalArgumentException ex) {
            System.out.println("unicodeKey=REJECTED");
        }

        String dottedCapitalI = "\u0130";
        System.out.println("rootDottedICodePoints="
                + codePoints(dottedCapitalI.toLowerCase(
                        Locale.ROOT)));

        System.out.println("eszettUpper="
                + "stra\u00DFe".toUpperCase(Locale.ROOT));

        System.out.println("ignoreCase="
                + "i".equalsIgnoreCase(dottedCapitalI));
        System.out.println("rootLowerEqual="
                + "i".toLowerCase(Locale.ROOT).equals(
                        dottedCapitalI.toLowerCase(Locale.ROOT)));
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 RootIdentifierDemo.java
java RootIdentifierDemo
```

**Stdout đã kiểm tra về ngữ nghĩa trên Java 17:**

```text
root=title
turkishCodePoints=U+0074 U+0131 U+0074 U+006C U+0065
canonical=server_mode
sameKey=true
unicodeKey=REJECTED
rootDottedICodePoints=U+0069 U+0307
eszettUpper=STRASSE
ignoreCase=true
rootLowerEqual=false
```

### Giải thích kết quả

1. `root=title` cho kết quả nhất quán không phụ thuộc default locale của JVM.
2. `turkishCodePoints` minh họa chữ `I` biến thành `U+0131` dưới `tr-TR`, khác chữ `i` `U+0069` của ROOT.
3. `canonical` và `sameKey` cho thấy bộ key của ví dụ chấp nhận các tên ASCII khác case làm cùng một canonical key.
4. `unicodeKey=REJECTED` vì `U+0130` không thuộc grammar ASCII do ứng dụng chọn; nó bị từ chối **trước** khi lowercase.
5. `rootDottedICodePoints` cho thấy lowercase ROOT của `İ` có **hai** code point, không phải ASCII `i` đơn.
6. `eszettUpper` cho thấy Unicode uppercase có thể mở rộng chuỗi; đừng suy số ký tự sau biến đổi bằng độ dài trước biến đổi.
7. `ignoreCase=true` và `rootLowerEqual=false` chứng minh `equalsIgnoreCase` và so sánh sau ROOT lowercase **không phải cùng một quy tắc** đối với mọi Unicode string.

Chương trình không đổi `Locale.setDefault(...)`, không cần network, không dùng file và không phụ thuộc font/charset terminal cho các dòng kết quả, vì những ký tự đặc biệt được in dưới dạng mã `U+...`.

## 9. So sánh chuỗi kỹ thuật: normalize trước hay so sánh trực tiếp?

Đối với **định danh có đặc tả case-insensitive**:

- Nếu cần lưu key trong `Map`, index hoặc database, có thể chọn một **dạng canonical** và lưu ngay ở biên nhận dữ liệu. Nhờ đó, các thao tác lookup thống nhất.
- Nếu chỉ cần kiểm tra hai token có bằng nhau dưới một định nghĩa cụ thể, không nhất thiết phải tạo chuỗi lowercase mới; có thể dùng một phép so sánh tuân thủ chính đặc tả.
- `equalsIgnoreCase` là phép so sánh tiện dụng của Java, nhưng **không thay thế validation grammar** và không tương đương mọi Unicode case folding/collation.
- Với ASCII kỹ thuật, có thể dùng bộ so sánh ASCII case-insensitive phù hợp hoặc explicit canonical ASCII; cách nào cũng phải tuân theo luật của giao thức.

### Bảo đảm consistency giữa các lớp

Một hệ thống có thể tồn tại các nơi so sánh khác nhau:

| Lớp | Rủi ro nếu khác quy tắc |
| --- | --- |
| API request validation | Có thể chấp nhận tên Unicode không nằm trong danh sách key kỹ thuật. |
| Java Map cache | Dùng ROOT lowercase trong lookup nhưng dữ liệu seed dùng locale mặc định. |
| Database unique index | Collation có thể gộp hoặc phân biệt những cặp mà Java xử lý khác. |
| Message queue consumer | Phía gửi và nhận chuẩn hóa key bằng các thuật toán/phiên bản khác nhau. |
| File config | Tên trường trong tệp cấu hình có thể case-sensitive nhưng code lại gộp. |
| Authorization | Hai user/token khác nhau có thể bị gộp vì normalization không đúng. |

Định nghĩa **một hợp đồng canonicalization** ở điểm nhập dữ liệu và áp dụng nhất quán. Nếu đổi chính sách khi hệ thống đã có dữ liệu, cần kiểm tra các key cũ bị trùng sau khi chuyển đổi và có kế hoạch migration, không thay đổi âm thầm rồi coi mọi kết quả như cũ.

### Ví dụ trùng key

```text
Các key ban đầu:
    SERVER_MODE
    server_mode

Nếu đặc tả case-insensitive:
    canonical => server_mode
    canonical => server_mode

Kết quả: hai nguồn cùng một key.
```

Chính sách có thể là **reject duplicate**, ghi đè có chủ đích theo thứ tự ưu tiên được tài liệu hóa, hoặc phát hiện xung đột trong bước build. Chọn một cách rõ ràng, nhất là khi đây là cấu hình bảo mật hoặc tính năng điều khiển hành vi.

## 10. Locale dành cho người dùng: đừng lạm dụng ROOT

`Locale.ROOT` không phù hợp khi mục đích thực sự là **biến đổi văn bản tự nhiên theo ngôn ngữ cụ thể**. Ví dụ:

- Chữ hoa/chữ thường tiếng Thổ Nhĩ Kỳ và tiếng Azerbaijan có quy tắc đặc thù về `I/İ/i/ı`.
- Một số ngôn ngữ có quy tắc casing theo ngữ cảnh chữ đứng trước/sau hoặc những dấu phụ.
- Tên người, tiêu đề, thông điệp email và văn bản giao diện cần bảo toàn ý nghĩa và tôn trọng locale/guồng viết của người dùng.
- Tìm kiếm, sắp xếp chữ cái theo ngôn ngữ cần cơ chế so sánh và collation phù hợp; `String.compareTo` hoặc lowercase ROOT không phải giải pháp thay thế.
- Những hệ thống hỗ trợ đa ngôn ngữ có thể cần xử lý trường hợp người dùng nhập cùng văn bản theo các dạng Unicode khác nhau.

Khi xử lý nội dung thực sự là văn bản bản địa hóa:

```java
Locale displayLocale = Locale.forLanguageTag("tr-TR");
String userFacing = title.toLowerCase(displayLocale);
```

Với **identifier kỹ thuật ASCII case-insensitive**, làm như vậy lại có thể là sai. Quyết định phải dựa vào **loại dữ liệu và đặc tả**, không dựa vào “nên dùng ROOT cho tất cả” hay “nên dùng locale người dùng cho tất cả”.

### Locale không phải charset

`Locale.ROOT` không đổi encoding của file/HTTP, không giải quyết lỗi chữ bị `Ã...` do decode sai UTF-8 và không khôi phục dữ liệu bị mất ký tự. Locale dùng để quyết định quy tắc ngôn ngữ cho một số phép biến đổi; **`Charset`** mới quyết định cách đổi dữ liệu ký tự thành byte và ngược lại ở ranh giới I/O.

Nếu dữ liệu kỹ thuật được lưu trong JSON, cơ sở dữ liệu hay HTTP, phải định nghĩa thêm charset/escaping và so sánh dữ liệu ở tầng phù hợp. Không lấy kết quả lowerCase làm giải pháp xử lý lỗi mã hóa.

## 11. Kiểm thử để tránh locale-sensitive bugs

### Ma trận kiểm thử gợi ý

| Trường hợp | Đầu vào | Điều cần chứng minh |
| --- | --- | --- |
| ASCII uppercase | `SERVER_MODE` | Canonical đúng `server_mode`. |
| ASCII mixed-case | `Server_Mode` | Canonical cùng key với lower-case nếu đặc tả cho phép. |
| Turkish-I | `TITLE` | ROOT giữ ASCII `i`; `tr-TR` có `U+0131`. |
| Unicode dotted I | `İD` | Grammar ASCII từ chối, không tự lặng lẽ biến đổi. |
| Unicode multi-codepoint lower | `İ` | ROOT lowercase thành `U+0069 U+0307`. |
| Uppercase expansion | `straße` | ROOT uppercase có thể tăng độ dài thành `STRASSE`. |
| Unicode normalization | `é` vs `e` + dấu tổ hợp | Xác nhận chính sách NFC nếu Unicode identifier được cho phép. |
| Case-sensitive identifier | `UserId` vs `userid` | Không gộp nếu đặc tả phân biệt. |
| Trùng sau canonicalization | `SERVER_MODE` và `server_mode` | Không silently overwrite nếu chính sách cấm. |
| Locale JVM khác | `en-US`, `tr-TR`, `vi-VN` | Kết quả canonical ASCII bằng ROOT không đổi. |
| Empty/null/Unicode spaces | `null`, `""`, `" NAME "` | Được xử lý theo validation, không tự làm sạch âm thầm. |
| ID kích thước lớn | Chuỗi rất dài | Có độ dài tối đa hợp đồng, kiểm tra sớm trước tạo nhiều chuỗi. |

**Đừng đổi default locale ngay trong test chạy song song chỉ để thử bẫy Turkish-I.** Chuyển `Locale` tường minh trong phép thử:

```java
String root = "TITLE".toLowerCase(Locale.ROOT);
String turkish = "TITLE".toLowerCase(
        Locale.forLanguageTag("tr-TR"));
```

Bạn sẽ thử được sự khác biệt mà không tác động các thread khác trong JVM. Với logic legacy thực sự dùng default locale, cần quản lý trạng thái chung và khôi phục đúng trong `try/finally`; không nên để các test loại đó chạy tùy tiện song song.

### Property-based testing hữu ích

Với grammar ASCII của ví dụ, bạn có thể sinh ngẫu nhiên key chỉ chứa `A-Z`, `a-z`, `0-9`, `_` và `-` để kiểm tra:

- Canonicalization **idempotent**: `canonical(canonical(x)).equals(canonical(x))`.
- Các key chỉ khác ASCII case cho cùng canonical value khi quy tắc cho phép.
- Kết quả không phụ thuộc default locale hoặc vị trí chạy.
- Input ngoài grammar bị reject trước khi xử lý, không bị biến thành key vô tình hợp lệ.
- Không tạo trùng key ngoài chính sách uniqueness.

Đối với Unicode identifiers, cần test các lớp ký tự được đặc tả cho phép, bản Unicode/JDK, normalization và confusables; không thể lấy random ASCII tests làm bằng chứng đầy đủ.

## 12. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng `toLowerCase()` không locale cho map key kỹ thuật | Kết quả phụ thuộc default locale JVM. | Dùng explicit ROOT **nếu** hợp đồng yêu cầu lowercase trung lập. |
| Dùng `Locale.US` cho mọi xử lý bất biến văn hóa | US là locale cụ thể, không diễn đạt ý nghĩa trung lập. | Xem xét `Locale.ROOT` cho phép biến đổi kỹ thuật trung lập. |
| Lowercase mọi tên file/path/URL | Có thành phần case-sensitive; hệ file và URL có đặc tả riêng. | Parse theo cấu trúc, tuân thủ đúng case policy. |
| Lowercase mật khẩu hoặc token | Thay đổi bí mật và ngữ nghĩa xác thực. | Giữ nguyên theo hợp đồng bảo mật. |
| Tin ROOT lower luôn cho ASCII | Unicode case mapping có thể tạo combining marks. | Validate ASCII grammar trước khi canonicalize nếu chỉ cho ASCII. |
| Tin upper/lower bảo toàn độ dài | `ß` có thể uppercase thành `SS`. | Không suy độ dài/index sau biến đổi từ trước biến đổi. |
| Coi `equalsIgnoreCase` giống so sánh sau ROOT lower | Hợp đồng khác nhau, có trường hợp kết quả khác. | Chọn đúng thuật toán cho bộ ký tự và đặc tả. |
| Dùng ROOT để phân loại, sắp xếp tên người | Không tôn trọng thứ tự và quy tắc ngôn ngữ. | Dùng `Locale`/`Collator` phù hợp. |
| Nghĩ lowercase giải quyết normalization | Các dãy code point tương đương có thể vẫn khác. | Định nghĩa Unicode normalization nếu cần. |
| Gộp key sau chuẩn hóa mà không kiểm tra trùng | Có thể gây overwrite hoặc sai quyền. | Xác định chính sách duplicate/migration. |
| Đổi `Locale.setDefault` trên từng request | Ảnh hưởng toàn JVM, dễ race. | Truyền locale vào API tường minh. |
| Tự tạo logic Unicode case folding không kiểm thử | Có thể bỏ sót ký tự/phiên bản Unicode. | Dùng chuẩn/libraries phù hợp cho định danh Unicode. |

## 13. Bài tập thực hành

**Bài 1 — Turkish-I:** in code point của `"TITLE".toLowerCase(Locale.ROOT)` và `"TITLE".toLowerCase(Locale.forLanguageTag("tr-TR"))`. Giải thích vì sao phép chuyển bằng `toLowerCase()` không tham số có thể làm một tên cấu hình khó lookup trong một số môi trường.

**Bài 2 — Identifier ASCII:** tự thiết kế grammar cho key config gồm chữ cái ASCII, chữ số và hai dấu `_`, `-`. Viết `canonicalAsciiKey` với validation trước khi chuyển chữ thường; thử `SERVER_MODE`, `server_mode`, `" SERVER_MODE "`, `İD` và chuỗi rỗng. Không tự trim hoặc thay dấu nếu đặc tả chưa cho phép.

**Bài 3 — Duplicate policy:** tạo một map nhận hai tên `SERVER_MODE` và `server_mode`; nếu canonical thành cùng một key, hãy lựa chọn reject duplicate hoặc chính sách ưu tiên rõ ràng. Viết test xác nhận không có ghi đè ngoài ý muốn.

**Bài 4 — Unicode mapping:** thử `"\u0130".toLowerCase(Locale.ROOT)` và `"stra\u00DFe".toUpperCase(Locale.ROOT)`, đếm `String.length()` và `codePointCount(...)` trước/sau biến đổi. Giải thích vì sao không thể dùng lower/upper như một hàm biến đổi một-một.

**Bài 5 — Chuỗi tự nhiên:** giả sử ứng dụng phục vụ tiếng Anh và tiếng Thổ Nhĩ Kỳ. Viết hai phương thức riêng: một phương thức canonicalize key ASCII kỹ thuật, một phương thức chuyển case cho văn bản giao diện dùng locale của người dùng. Nêu lý do không thể gộp cả hai thành một hàm `lowercase(String)` không tham số.

**Bài 6 — Unicode identifier:** nếu sản phẩm cho phép username Unicode, liệt kê cần có những quyết định nào về normalization, case-insensitive equivalence, ký tự confusable, giới hạn độ dài, duplicate và migration. Đừng tự dùng ROOT lowercase làm chính sách username hoàn chỉnh.

**Bài 7 — Kiểm thử đa môi trường:** dùng unit test chạy với default locale JVM khác nhau; xác minh kết quả của canonicalization ROOT luôn ổn định, trong khi code thiếu tham số locale có thể khác. Khi thay default trong test, bảo đảm cô lập và khôi phục giá trị cũ.

### Checklist hoàn thành

- [ ] Hiểu `Locale.ROOT` trung lập về ngôn ngữ/vùng và khác default locale JVM.
- [ ] Biết rằng `toLowerCase()` không tham số có thể phụ thuộc locale mặc định.
- [ ] Giải thích được bẫy chữ `I` trong tiếng Thổ Nhĩ Kỳ khi xử lý identifier kỹ thuật.
- [ ] Chỉ dùng ROOT lowercase khi **đặc tả cho phép case-insensitive canonicalization**.
- [ ] Phân biệt identifier ASCII với Unicode identifier cần normalization/case folding.
- [ ] Không dùng lowercase để xử lý password, token, path hoặc text giao diện ngoài chính sách.
- [ ] Nắm giới hạn Unicode: thay đổi độ dài, ký tự tổ hợp, `equalsIgnoreCase` khác ROOT lowercase.
- [ ] Có validation grammar, duplicate policy, test idempotence và kiểm thử nhiều locale.
- [ ] Không thay locale mặc định toàn JVM chỉ để xử lý một request.

**Kết luận:** `Locale.ROOT` là một lựa chọn tốt khi chuyển chữ hoa/thường cho **định danh kỹ thuật có đặc tả rõ, cần ổn định và không phụ thuộc ngôn ngữ**, đặc biệt khi cùng service chạy trên những JVM có locale mặc định khác nhau. Nhưng **“khi phù hợp” không đồng nghĩa “dùng ở mọi nơi”**: xác định grammar và case sensitivity trước, tránh biến đổi dữ liệu có ý nghĩa riêng, và dùng thuật toán Unicode/collation chuyên dụng nếu domain đòi hỏi.
