# Chuẩn hóa văn bản bằng `Normalizer`

Hai chuỗi Unicode có thể hiển thị giống nhau nhưng chứa các dãy code point khác nhau. Ví dụ, chữ `ắ` tiếng Việt có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ `a` cùng các combining marks. `String.equals()` so sánh chính xác các code unit UTF-16 nên hai chuỗi này không bằng nhau nếu chưa chuẩn hóa.

`java.text.Normalizer` chuyển văn bản sang một trong bốn dạng chuẩn Unicode: NFC, NFD, NFKC hoặc NFKD. Với văn bản thông thường, NFC thường là lựa chọn phù hợp để lưu trữ, trao đổi và so sánh các chuỗi tương đương về mặt canonical. NFKC/NFKD loại bỏ thêm một số khác biệt tương thích nên có thể thay đổi ý nghĩa hoặc cách trình bày; chỉ dùng chúng khi quy tắc của miền dữ liệu yêu cầu.

`Normalizer` là API Java SE chính thức từ Java 6, không phải tính năng mới hay preview của Java 26. Điểm cần quan tâm khi nâng cấp là dữ liệu Unicode mà runtime hỗ trợ: JDK 26 và JDK 27 dùng Unicode 17.0. Unicode 18.0 đã được phát hành vào tháng 9-2026, nhưng không nên giả định JDK 27 đã tích hợp phiên bản đó.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao hai chuỗi nhìn giống nhau có thể khác nhau khi so sánh bằng `String.equals()`.
- Phân biệt canonical equivalence và compatibility equivalence.
- Chọn đúng NFC, NFD, NFKC hoặc NFKD theo mục đích sử dụng.
- Dùng `Normalizer.normalize()` và `Normalizer.isNormalized()` trong Java.
- Chuẩn hóa dữ liệu trước khi so sánh, tạo khóa tìm kiếm hoặc lưu trữ có quy tắc thống nhất.
- Hiểu vì sao chuẩn hóa không đồng nghĩa với chuyển chữ hoa/thường, bỏ dấu, transliteration hoặc phát hiện ký tự giả mạo.
- Xử lý đúng rủi ro khi dùng NFKC với định danh, mật khẩu và nội dung đa ngôn ngữ.
- Nhận biết ảnh hưởng của phiên bản Unicode trong JDK tới các code point mới.

## 1. Vì sao cần chuẩn hóa Unicode?

Unicode biểu diễn văn bản bằng các code point; một grapheme hiển thị có thể gồm một hoặc nhiều code point. Một số chữ có thể được biểu diễn bằng nhiều dãy code point tương đương. Chẳng hạn chữ `ắ` có thể dùng:

- Dạng dựng sẵn: U+1EAF `LATIN SMALL LETTER A WITH BREVE AND ACUTE`.
- Dạng phân rã: U+0061 `LATIN SMALL LETTER A`, U+0306 `COMBINING BREVE`, U+0301 `COMBINING ACUTE ACCENT`.

Hai cách biểu diễn trên có cùng ý nghĩa văn bản và được Unicode xem là canonically equivalent. Tuy nhiên, Java `String.equals()` so sánh dãy UTF-16 code unit nên kết quả trước khi chuẩn hóa là `false`:

```java
String composed = "\u1EAF";
String decomposed = "a\u0306\u0301";

System.out.println(composed.equals(decomposed)); // false
```

Điều này có thể gây ra lỗi khi:

- Tìm kiếm một tên tiếng Việt được lưu ở dạng dựng sẵn nhưng người dùng nhập ở dạng phân rã.
- Kiểm tra trùng lặp username hoặc tên hiển thị.
- Tạo khóa `Map`, unique key trong database hoặc cache key từ văn bản.
- So sánh dữ liệu nhận từ nhiều hệ điều hành, bàn phím, API hoặc hệ thống lưu trữ.
- Trao đổi dữ liệu với hệ thống dùng một dạng chuẩn Unicode khác.

Chuẩn hóa chuyển các chuỗi tương đương về cùng một dạng được chọn. Sau khi chuẩn hóa NFC, ví dụ trên có thể so sánh bằng `String.equals()`.

## 2. Bốn dạng chuẩn NFC, NFD, NFKC và NFKD

Unicode Standard Annex #15 định nghĩa bốn normalization forms. Có hai lựa chọn độc lập: decomposition có giữ khác biệt tương thích hay không, và có composition lại thành ký tự dựng sẵn hay không.

| Form | Tên | Quy tắc | Mục đích thường gặp |
|---|---|---|---|
| NFC | Canonical Decomposition, followed by Canonical Composition | Phân rã canonical rồi ghép lại khi có thể | Dạng chuẩn phổ biến cho văn bản trao đổi và lưu trữ |
| NFD | Canonical Decomposition | Phân rã canonical, không ghép lại | Xử lý nội bộ, phân tích combining marks |
| NFKC | Compatibility Decomposition, followed by Canonical Composition | Phân rã cả các dạng tương thích rồi ghép lại khi có thể | Định danh hoặc khóa so sánh có quy tắc compatibility rõ ràng |
| NFKD | Compatibility Decomposition | Phân rã canonical và compatibility, không ghép lại | Xử lý nội bộ khi cần nhìn thấy các thành phần phân rã |

**Canonical equivalence** giữ lại khác biệt về mặt ý nghĩa của ký tự và chỉ thống nhất những cách biểu diễn được Unicode định nghĩa là tương đương canonical. NFC và NFD tạo cùng một dạng tương đương canonical, nhưng một dạng ghép và một dạng phân rã.

**Compatibility equivalence** còn gộp một số ký tự có hình thức hoặc cách trình bày khác nhưng được định nghĩa là tương đương trong một số ngữ cảnh. NFKC và NFKD có thể biến đổi các ký tự như ligature, chữ full-width, chữ số khoanh tròn hoặc superscript. Những biến đổi này có thể làm mất phân biệt mà nội dung gốc muốn giữ.

### Ví dụ canonical: chữ tiếng Việt

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;

String composed = "\u1EAF";       // ắ dựng sẵn
String decomposed = "a\u0306\u0301"; // a + breve + acute

String nfc = Normalizer.normalize(decomposed, Form.NFC);
String nfd = Normalizer.normalize(composed, Form.NFD);

System.out.println(nfc.equals(composed)); // true
System.out.println(nfd.equals(decomposed)); // true
```

NFC ghép các thành phần thành chữ dựng sẵn khi Unicode có phép composition phù hợp. NFD làm điều ngược lại bằng cách phân rã chữ dựng sẵn thành các thành phần canonical.

### Ví dụ compatibility: full-width và ligature

```java
String fullWidth = "\uFF21\uFF22\uFF23"; // ＡＢＣ
String ligature = "\uFB03";               // ﬃ

System.out.println(Normalizer.normalize(fullWidth, Form.NFC));
// ＡＢＣ: NFC giữ khác biệt compatibility

System.out.println(Normalizer.normalize(fullWidth, Form.NFKC));
// ABC

System.out.println(Normalizer.normalize(ligature, Form.NFKC));
// ffi
```

NFKC có thể hữu ích khi một miền định danh muốn xem chữ full-width tương đương với chữ ASCII hoặc muốn gộp ligature với chuỗi chữ tương ứng. Nhưng nếu văn bản cần giữ nguyên cách trình bày, typography hoặc ý nghĩa của ký hiệu, NFKC có thể làm mất thông tin.

## 3. Dùng `Normalizer.normalize()` và `isNormalized()`

`Normalizer` nằm trong package `java.text`. Hai phương thức chính là:

```java
public static String normalize(CharSequence src, Normalizer.Form form)
public static boolean isNormalized(CharSequence src, Normalizer.Form form)
```

`normalize()` trả về một `String` ở dạng chuẩn được yêu cầu. `isNormalized()` kiểm tra chuỗi đã ở dạng đó hay chưa; phương thức này không tạo ra bản sao đã chuẩn hóa. Cả hai ném `NullPointerException` nếu đối số nguồn hoặc form là `null`.

Ví dụ tạo hàm chuẩn hóa NFC dùng chung:

```java
import java.text.Normalizer;
import java.util.Objects;

static String normalizeForStorage(String input) {
    Objects.requireNonNull(input, "input");
    return Normalizer.normalize(input, Normalizer.Form.NFC);
}
```

Có thể kiểm tra trước khi chuẩn hóa:

```java
String input = "a\u0306\u0301";

if (!Normalizer.isNormalized(input, Normalizer.Form.NFC)) {
    input = Normalizer.normalize(input, Normalizer.Form.NFC);
}
```

Không bắt buộc phải gọi `isNormalized()` trước mỗi lần `normalize()`. Nếu ứng dụng luôn chuẩn hóa ở ranh giới nhập dữ liệu, có thể chuẩn hóa trực tiếp và tránh một lượt kiểm tra riêng. `isNormalized()` hữu ích khi cần xác thực đầu vào phải ở dạng chuẩn hoặc muốn đo/kiểm tra dữ liệu đã lưu.

Chuẩn hóa là phép biến đổi idempotent: chuẩn hóa một chuỗi đã ở dạng đó lần nữa không làm thay đổi kết quả.

```java
String once = Normalizer.normalize(input, Normalizer.Form.NFC);
String twice = Normalizer.normalize(once, Normalizer.Form.NFC);

System.out.println(once.equals(twice)); // true
```

## 4. Chọn NFC cho văn bản thông thường

Với tên người, địa chỉ, nội dung bài viết, tên sản phẩm và văn bản đa ngôn ngữ, NFC thường là lựa chọn thực tế để thống nhất biểu diễn canonical mà không gộp thêm các khác biệt compatibility. NFC cũng tương thích tốt với dữ liệu chuyển đổi từ nhiều bảng mã cũ vốn thường sử dụng các ký tự dựng sẵn.

Một quy trình nhập dữ liệu có thể thực hiện:

1. Giải mã byte thành văn bản bằng charset được giao thức chỉ định, thường là UTF-8.
2. Kiểm tra dữ liệu theo quy tắc đầu vào của ứng dụng.
3. Chuẩn hóa chuỗi sang NFC.
4. Lưu hoặc tạo khóa so sánh từ chuỗi đã chuẩn hóa.
5. Khi truy vấn, áp dụng cùng một quy tắc NFC trước khi tìm kiếm hoặc so sánh.

Ví dụ dùng NFC cho khóa tên hiển thị:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;

static String displayNameKey(String input) {
    return Normalizer.normalize(input, Normalizer.Form.NFC);
}

Map<String, String> displayNames = new HashMap<>();

displayNames.put(displayNameKey("\u1EAF"), "Tên đã đăng ký");

String query = "a\u0306\u0301";
System.out.println(displayNames.get(displayNameKey(query)));
// Tên đã đăng ký
```

Trong hệ thống thực tế, nên quy định rõ dữ liệu lưu trong database đã được chuẩn hóa hay chỉ có comparison key chuẩn hóa. Nếu giữ cả văn bản gốc để hiển thị/audit, hãy lưu riêng trường hiển thị và khóa so sánh. Unique index phải áp dụng cùng chính sách chuẩn hóa với tầng ứng dụng để tránh hai tầng coi dữ liệu là khác nhau.

## 5. NFC/NFD không phải là bỏ dấu

NFD phân rã chữ có dấu thành chữ nền và combining marks. Nó không tự xóa dấu. Ví dụ:

```java
String text = "Tiếng Việt";
String decomposed = Normalizer.normalize(text, Normalizer.Form.NFD);

System.out.println(decomposed);
// Các chữ có dấu được biểu diễn bằng chữ nền và combining marks.
```

Nếu muốn tìm kiếm không phân biệt dấu, đó là một phép biến đổi riêng, thường được gọi là accent-insensitive search. Có thể xây dựng search key bằng cách phân rã NFD rồi loại các Unicode mark, nhưng thao tác này có tính mất mát và phụ thuộc ngôn ngữ.

Ví dụ minh họa hẹp cho một search index tiếng Việt/Latin:

```java
import java.text.Normalizer;
import java.util.Locale;

static String latinSearchKey(String input) {
    String decomposed = Normalizer.normalize(
            input, Normalizer.Form.NFD);

    StringBuilder result = new StringBuilder();
    decomposed.codePoints()
            .filter(cp -> {
                int type = Character.getType(cp);
                return type != Character.NON_SPACING_MARK
                        && type != Character.COMBINING_SPACING_MARK
                        && type != Character.ENCLOSING_MARK;
            })
            .forEach(result::appendCodePoint);

    return result.toString().toLowerCase(Locale.ROOT);
}
```

Đây chỉ là ví dụ tạo khóa tìm kiếm phụ cho miền đã xác định. Không dùng nó để ghi đè văn bản gốc hoặc để so sánh danh tính chính thức. Trong tiếng Việt, bỏ dấu có thể gộp những từ khác nghĩa như `ma`, `má`, `mà`, `mả`, `mã`, `mạ`. Trong nhiều hệ chữ khác, combining marks là thành phần thiết yếu của nguyên âm hoặc phụ âm; loại bỏ chúng có thể phá hủy văn bản.

Nếu yêu cầu là tìm kiếm gần đúng hoặc không phân biệt dấu, hãy giữ nguyên giá trị gốc, tạo search key riêng và mô tả rõ các khác biệt nào được phép gộp. Với tìm kiếm theo ngôn ngữ, `Collator` hoặc thư viện tìm kiếm đa ngôn ngữ có thể phù hợp hơn một phép xóa mark toàn cục.

## 6. NFKC/NFKD có thể làm mất phân biệt

Compatibility decomposition được thiết kế để gộp những dạng trình bày mà một ứng dụng nhất định muốn coi là tương đương. Một số ví dụ:

| Ký tự đầu vào | NFC | NFKC | Thay đổi |
|---|---|---|---|
| `Ａ` (full-width A) | `Ａ` | `A` | Gộp full-width với ASCII |
| `ﬃ` (ligature ffi) | `ﬃ` | `ffi` | Gộp ligature với chuỗi chữ |
| `①` (circled digit one) | `①` | `1` | Bỏ dạng trang trí/khoanh tròn |
| `²` (superscript two) | `²` | `2` | Bỏ dạng trình bày superscript |

Các thay đổi này có thể có ích cho khóa định danh hoặc dữ liệu tìm kiếm có profile rõ ràng. Chúng không phù hợp để áp dụng mặc định cho nội dung hiển thị, văn bản khoa học, toán học, tài liệu có kiểu chữ đặc biệt hoặc dữ liệu mà người dùng mong đợi giữ nguyên.

Ví dụ, NFKC biến `²` thành `2`; nếu nội dung là công thức `m²`, kết quả có thể không còn thể hiện cách viết số mũ mà tác giả muốn giữ. Tương tự, `①` có thể là số thứ tự trang trí có ý nghĩa bố cục, không phải chữ số `1` trong mọi ngữ cảnh.

NFKC không phải phép transliteration và không thay mọi ký tự nhìn giống nhau thành một. Chẳng hạn chữ Latin `a` và chữ Cyrillic `а` là hai code point khác nhau; NFKC không tự biến chúng thành cùng một chữ.

## 7. Chuẩn hóa, chữ hoa/thường và so sánh theo locale là các việc khác nhau

`Normalizer` không thực hiện case folding. NFC của `Java` vẫn khác NFC của `java`. Nếu nghiệp vụ cần so sánh không phân biệt chữ hoa/thường, phải thêm quy tắc casing phù hợp.

```java
import java.text.Normalizer;
import java.util.Locale;

static String caseInsensitiveKey(String input) {
    String normalized = Normalizer.normalize(
            input, Normalizer.Form.NFC);
    return normalized.toLowerCase(Locale.ROOT);
}
```

`Locale.ROOT` tránh phụ thuộc locale mặc định của máy, nhưng `toLowerCase(Locale.ROOT)` vẫn không phải full Unicode case folding. Một số chữ có quy tắc case mapping đặc biệt hoặc ánh xạ nhiều ký tự; nếu cần so khớp identifier không phân biệt case theo Unicode, dùng quy tắc case folding được đặc tả rõ thay vì tự coi lowercase là tương đương.

Nếu cần sắp xếp hoặc so sánh theo quy tắc ngôn ngữ, dùng `java.text.Collator` với locale thích hợp. Chuẩn hóa chuỗi không thay thế collation: NFC giúp thống nhất cách biểu diễn, còn Collator quyết định thứ tự và mức độ phân biệt theo ngôn ngữ.

## 8. Định danh và bảo mật Unicode

Chuẩn hóa có thể giảm một số cách biểu diễn khác nhau của cùng một identifier, nhưng riêng `Normalizer` không đủ để xây dựng chính sách username an toàn.

Với định danh, cần xác định ít nhất:

- Form chuẩn nào được dùng: NFC hay một profile dựa trên NFKC.
- Có phân biệt chữ hoa/thường hay không; nếu không, dùng simple/full case folding theo đặc tả.
- Những script, ký tự, combining marks, default-ignorable code points và ký tự điều khiển nào được phép.
- Có cho phép identifier trộn nhiều script không.
- Cách phát hiện identifier nhìn giống nhau nhưng dùng code point khác nhau.
- Phiên bản Unicode và dữ liệu bảo mật được dùng khi tạo comparison key.

Unicode Standard Annex #31 mô tả profile cho identifier, trong đó có `toNFKC_Casefold`. Phép biến đổi này kết hợp compatibility normalization, case folding và loại bỏ một số default-ignorable code points. Java `Normalizer` chỉ cung cấp NFC, NFD, NFKC và NFKD; nó không cung cấp trực tiếp `toNFKC_Casefold` hay full case folding. Nếu cần profile này, dùng thư viện Unicode chuyên dụng như ICU4J và tuân thủ phiên bản dữ liệu Unicode đã chọn.

Unicode Technical Standard #39 mô tả cơ chế phát hiện confusable và mixed-script. Ví dụ, một identifier có thể trộn chữ Latin với chữ Cyrillic nhìn gần giống nhau. NFC/NFKC không tự phát hiện hoặc loại bỏ kiểu giả mạo này. Hệ thống quản lý tài khoản, domain, tên tổ chức và định danh công khai nên có thêm chính sách script restriction, confusable detection, hiển thị cảnh báo và kiểm tra trùng lặp phù hợp.

### Không tự động chuẩn hóa mọi mật khẩu

Mật khẩu là dữ liệu xác thực, nên không tự áp dụng NFKC hoặc bỏ dấu chỉ vì muốn “làm sạch” chuỗi. Việc biến đổi có thể khiến hai chuỗi người dùng nhập khác nhau trở thành cùng một credential hoặc khiến người dùng không đăng nhập được nếu luồng đăng ký và xác thực áp dụng chính sách khác nhau.

Chỉ chuẩn hóa mật khẩu khi tiêu chuẩn giao thức hoặc chính sách xác thực của sản phẩm quy định rõ. Nếu có quy tắc đó, phải áp dụng nhất quán ở cả đăng ký, đổi mật khẩu và xác thực; ghi nhận phiên bản quy tắc để có thể nâng cấp mà không làm người dùng mất quyền truy cập.

## 9. Chuẩn hóa không đóng kín dưới phép nối chuỗi

Một đặc điểm dễ bỏ sót của Unicode normalization là hai chuỗi riêng lẻ đã chuẩn hóa không bảo đảm chuỗi ghép của chúng vẫn chuẩn hóa. Ví dụ:

```java
String left = Normalizer.normalize("a", Normalizer.Form.NFC);
String right = Normalizer.normalize("\u0302", Normalizer.Form.NFC);

String joined = left + right;

System.out.println(Normalizer.isNormalized(
        joined, Normalizer.Form.NFC)); // false

String normalizedJoined = Normalizer.normalize(
        joined, Normalizer.Form.NFC);
System.out.println(normalizedJoined); // â
```

`left` và `right` đều đã ở NFC, nhưng khi ghép chữ `a` với combining circumflex, chúng có thể kết hợp thành `â`. Vì vậy, nếu ứng dụng nối các mảnh văn bản độc lập, hãy chuẩn hóa lại kết quả tại ranh giới ghép khi cần bảo đảm toàn bộ chuỗi đầu ra ở NFC.

Theo UAX #15, các dạng chuẩn đóng dưới thao tác lấy substring, nhưng không đóng dưới phép concatenation tổng quát. Đừng chỉ kiểm tra từng trường hoặc từng mảnh trước khi ghép rồi cho rằng kết quả cuối cùng đã chuẩn hóa.

## 10. Phiên bản Unicode của runtime ảnh hưởng tới code point mới

`Normalizer` dựa trên dữ liệu Unicode của JDK đang chạy. Cần phân biệt phiên bản Java với phiên bản Unicode được tích hợp:

| Runtime | Phiên bản Unicode được xác nhận | Ghi chú |
|---|---|---|
| JDK 25 | Unicode 16.0 | Có thể chưa nhận diện các code point được thêm từ Unicode 17 trở đi |
| JDK 26 | Unicode 17.0 | Release notes xác nhận `Normalizer` hỗ trợ UAX #15 của Unicode 17.0 |
| JDK 27 | Unicode 17.0 | `Character` API của JDK 27 vẫn ghi Unicode 17.0 |
| Unicode Standard hiện hành tại 27-11-2026 | Unicode 18.0 | Được Unicode Consortium phát hành ngày 16-09-2026; không đồng nghĩa JDK 27 đã cập nhật lên bản này |

Unicode có chính sách normalization stability mạnh: với các ký tự đã được gán trong cả phiên bản Unicode cũ và mới, kết quả NFC/NFD/NFKC/NFKD không thay đổi giữa các phiên bản. Tuy nhiên, một code point chưa được gán trong phiên bản Unicode mà runtime hỗ trợ có thể được gán ý nghĩa hoặc decomposition trong phiên bản Unicode sau. Vì vậy, chuỗi chứa ký tự mới hơn runtime có thể chưa ở dạng chuẩn theo một runtime mới hơn.

Điều này quan trọng khi nhiều service dùng các JDK có phiên bản Unicode khác nhau để tạo username key, unique key hoặc chữ ký dữ liệu. Hãy thống nhất phiên bản runtime hoặc dùng một thư viện Unicode có phiên bản dữ liệu được quản lý rõ ràng. Với giao thức cần kết quả ổn định qua các phiên bản, hãy xác định profile và phiên bản Unicode cụ thể; UAX #15 có mô tả Normalization Process for Stabilized Strings (NPSS), trong đó chuỗi chứa code point chưa được gán theo phiên bản được chọn phải bị từ chối. `java.text.Normalizer` không cung cấp một chế độ NPSS riêng.

## 11. Lưu trữ và so sánh dữ liệu đã chuẩn hóa

Một hệ thống có thể chọn một trong hai cách:

**Cách A — chuẩn hóa nội dung trước khi lưu:** mọi dữ liệu đầu vào được chuyển sang NFC và trường chính lưu giá trị NFC. Cách này giúp truy vấn trực tiếp và tránh nhiều dạng canonical-equivalent trong database. Cần có migration cho dữ liệu cũ và quy tắc thống nhất giữa các service.

**Cách B — giữ nội dung gốc, lưu comparison key riêng:** trường display giữ chuỗi người dùng nhập, còn một cột normalized key được tạo theo profile. Unique constraint và lookup dùng normalized key; giao diện có thể hiển thị bản gốc hoặc bản NFC theo yêu cầu sản phẩm.

Ví dụ mô hình:

```java
record PersonName(String displayText, String comparisonKey) {
    static PersonName fromInput(String input) {
        String nfc = Normalizer.normalize(
                input, Normalizer.Form.NFC);
        return new PersonName(input, nfc);
    }
}
```

Nếu comparison key còn áp dụng case folding, NFKC hoặc bỏ dấu, hãy đặt tên field thể hiện chính sách cụ thể và version hóa quy tắc khi cần. Không dùng một cột chung tên `cleaned_text` cho nhiều phép biến đổi khác nhau.

Khi đổi chính sách chuẩn hóa hoặc nâng phiên bản Unicode, không âm thầm tạo key mới cho toàn bộ dữ liệu mà chưa kiểm tra xung đột. Hai identifier trước đây khác nhau có thể trở thành cùng key sau khi profile mới thay đổi. Hãy chạy migration thử, phát hiện collision, định nghĩa cách xử lý và bảo đảm unique constraint không bị vi phạm.

## 12. Kiểm thử normalization bằng JUnit

Kiểm thử nên xác nhận canonical equivalence, compatibility mapping, tính idempotent, hành vi `isNormalized()` và trường hợp ghép chuỗi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.text.Normalizer;
import java.text.Normalizer.Form;

import org.junit.jupiter.api.Test;

class NormalizerTest {
    @Test
    void canonicalFormsProduceEquivalentText() {
        String composed = "\u1EAF";
        String decomposed = "a\u0306\u0301";

        assertFalse(composed.equals(decomposed));
        assertEquals(composed,
                Normalizer.normalize(decomposed, Form.NFC));
        assertEquals(decomposed,
                Normalizer.normalize(composed, Form.NFD));
    }

    @Test
    void compatibilityFormFoldsPresentationDifferences() {
        assertEquals("ABC", Normalizer.normalize(
                "\uFF21\uFF22\uFF23", Form.NFKC));
        assertEquals("ffi", Normalizer.normalize("\uFB03", Form.NFKC));
    }

    @Test
    void normalizationIsIdempotent() {
        String once = Normalizer.normalize(
                "a\u0306\u0301", Form.NFC);
        String twice = Normalizer.normalize(once, Form.NFC);

        assertEquals(once, twice);
        assertTrue(Normalizer.isNormalized(once, Form.NFC));
    }

    @Test
    void concatenationCanRequireRenormalization() {
        String joined = "a" + "\u0302";

        assertFalse(Normalizer.isNormalized(joined, Form.NFC));
        assertEquals("\u00E2", Normalizer.normalize(joined, Form.NFC));
    }
}
```

Các test dùng code point escape để người đọc có thể nhận diện chính xác dữ liệu đầu vào, không phụ thuộc editor có hiển thị combining marks hay không. Khi viết test cho Unicode, nên có cả trường hợp code point dựng sẵn, chuỗi phân rã, nhiều combining marks, ký tự supplementary và dữ liệu từ các script ứng dụng thực sự hỗ trợ.

## 13. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| Dùng `String.equals()` trực tiếp cho dữ liệu Unicode chưa chuẩn hóa | Hai chuỗi canonical-equivalent có thể khác code unit | Chuẩn hóa cả hai theo cùng một form trước khi so sánh |
| Chọn NFKC cho mọi văn bản | Compatibility normalization có thể gộp ligature, full-width, superscript và khác biệt trình bày | Dùng NFC cho văn bản thông thường; chỉ chọn NFKC theo profile cụ thể |
| Nghĩ NFD tự động bỏ dấu | NFD chỉ phân rã, vẫn giữ combining marks | Nếu cần tìm không dấu, xây search key mất mát riêng và giới hạn theo ngôn ngữ |
| Dùng `toLowerCase()` thay cho case folding Unicode | Lowercase và full case folding không tương đương | Định nghĩa chính sách casing; dùng thư viện Unicode nếu cần full case folding |
| Dùng normalization để chống homoglyph | Ký tự Latin/Cyrillic giống hình vẫn có thể khác nhau sau NFKC | Dùng profile identifier và confusable detection theo UTS #39 |
| Chuẩn hóa từng mảnh rồi ghép mà không kiểm tra lại | Normalization forms không đóng dưới concatenation | Chuẩn hóa chuỗi sau khi ghép nếu cần bảo đảm form |
| Tự chuẩn hóa mật khẩu | Có thể thay đổi credential và gây không nhất quán đăng nhập | Chỉ làm theo chuẩn/policy xác thực được xác định rõ |
| Cho rằng mọi JDK dùng cùng Unicode data | Phiên bản Unicode thay đổi theo JDK | Kiểm tra Unicode version của runtime và thống nhất profile giữa service |

## 14. Trạng thái API và khả năng tương thích

| Thành phần | Trạng thái |
|---|---|
| `java.text.Normalizer` | API Java SE chính thức từ Java 6 |
| `Normalizer.Form.NFC`, `NFD`, `NFKC`, `NFKD` | API chính thức; không cần `--enable-preview` |
| `Normalizer.normalize()` và `isNormalized()` | API chính thức; có trong JDK 26/27 |
| Unicode data của JDK 26 | Unicode 17.0 |
| Unicode data của JDK 27 | Unicode 17.0 theo `Character` API |
| Unicode 18.0 | Đã phát hành bởi Unicode Consortium; chưa được xác nhận là dữ liệu Unicode của JDK 27 |

`java.text` thuộc module `java.base`; không cần thêm module hoặc dependency để dùng `Normalizer`. Nếu yêu cầu full case folding, NFKC_Casefold, identifier profile hoặc confusable detection, API `Normalizer` không bao phủ đầy đủ; chọn thư viện Unicode chuyên dụng và quản lý phiên bản dữ liệu của nó.

## 15. Bài tập thực hành

Một hệ thống lưu tên người dùng tiếng Việt và cần tìm kiếm tên khi người dùng nhập từ nhiều thiết bị. Dữ liệu có thể chứa chữ dựng sẵn hoặc combining sequence. Hệ thống cũng có username không phân biệt chữ hoa/thường và phải tránh gộp nhầm các identifier có ký tự tương tự về hình thức.

**Yêu cầu:**

1. Tạo hai chuỗi biểu diễn `ắ`: U+1EAF và `a` + U+0306 + U+0301.
2. So sánh hai chuỗi trước và sau khi chuẩn hóa NFC.
3. Thử NFD và quan sát code point của kết quả.
4. Thử NFKC với full-width Latin, ligature `ﬃ`, circled digit `①` và superscript `²`; ghi nhận khác biệt bị gộp.
5. Xây hàm tạo display key NFC và kiểm tra lookup bằng chuỗi canonical-equivalent.
6. Tạo search key không dấu cho một tập dữ liệu tiếng Việt thử nghiệm; chứng minh vì sao search key không được dùng làm danh tính hoặc unique key chính thức.
7. Giải thích vì sao `toLowerCase(Locale.ROOT)` không phải full Unicode case folding và vì sao NFKC không phát hiện chữ Latin/Cyrillic confusable.
8. Đề xuất profile identifier dùng UAX #31 và cơ chế phát hiện confusable theo UTS #39.
9. Kiểm tra dữ liệu Unicode version của JDK 26/27 và mô tả cách nâng cấp khi Unicode mới được hỗ trợ.

**Kết quả mong đợi:**

- Hai chuỗi `ắ` có thể khác trước chuẩn hóa nhưng giống nhau sau NFC.
- NFD phân rã ký tự mà không tự loại bỏ combining marks.
- NFKC gộp một số khác biệt compatibility và có thể làm mất thông tin trình bày.
- Ứng dụng dùng cùng normalization form cho cả dữ liệu ghi và dữ liệu truy vấn.
- Search key không dấu được tách khỏi dữ liệu gốc và khóa định danh.
- Người học phân biệt normalization, case folding, collation và confusable detection.
- Không coi `Normalizer` là API preview của Java 26; chỉ Unicode data của runtime là yếu tố cần theo dõi khi nâng cấp.

## Tài liệu tham khảo

- [Normalizer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): API `normalize`, `isNormalized` và bốn normalization forms.
- [JDK 26 Release Notes — Support for Unicode 17.0](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): phiên bản Unicode và việc `Normalizer` hỗ trợ UAX #15 Unicode 17.0.
- [Character — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html): xác nhận JDK 27 sử dụng Unicode 17.0.
- [Unicode Standard Annex #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): định nghĩa NFC, NFD, NFKC, NFKD, normalization stability và concatenation.
- [Unicode FAQ — Normalization](https://www.unicode.org/faq/normalization.html): hướng dẫn chọn NFC/NFD cho văn bản và NFKC/NFKD cho các miền cần compatibility matching.
- [Unicode Character Encoding Stability Policy](https://www.unicode.org/policies/stability_policy.html): cam kết normalization stability cho các ký tự đã được gán.
- [Unicode Standard Annex #31: Unicode Identifiers and Syntax](https://www.unicode.org/reports/tr31/): identifier profiles, normalization, case folding và `toNFKC_Casefold`.
- [Unicode Technical Standard #39: Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): confusable detection, mixed-script và các cơ chế bảo vệ identifier.
- [Unicode 18.0.0](https://www.unicode.org/versions/Unicode18.0.0/): phiên bản Unicode được phát hành ngày 16-09-2026.
