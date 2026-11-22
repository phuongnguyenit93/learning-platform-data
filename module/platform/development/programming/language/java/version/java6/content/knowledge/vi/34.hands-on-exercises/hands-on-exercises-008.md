# Chuẩn hóa văn bản tiếng Việt và kiểm thử Locale Service Provider trong Java

Một chuỗi nhìn giống hệt nhau trên màn hình **không nhất thiết giống nhau ở mức Unicode**. Ví dụ chữ tiếng Việt **ấ** có thể được mã hóa bằng **một ký tự dựng sẵn** hoặc bằng chữ **a** cộng hai dấu kết hợp. Điều này ảnh hưởng tới tìm kiếm chính xác, deduplication, kiểm thử dữ liệu, indexes và giao tiếp giữa hệ thống. Bên cạnh chuẩn hóa Unicode, Java còn có cơ chế **locale-sensitive data providers** cho số, ngày, tên địa phương và collation. Hai vấn đề này **liên quan nhưng không thay thế nhau**.

Bài thuộc nhóm **Thực hành** với đề bài **“Chuẩn hóa văn bản tiếng Việt và kiểm thử locale provider”**. Mục tiêu là vừa làm sạch và đối chiếu chuỗi tiếng Việt **đúng theo chuẩn Unicode**, vừa đóng gói một **Locale Service Provider (SPI) có thật**, thử nó bằng **hai JVM riêng** với thứ tự ưu tiên `SPI,CLDR` và `CLDR,SPI`. Chỉ sử dụng API **còn áp dụng trong Java 17+ và Java SE 26**; không dựa vào `COMPAT/JRE` locale providers đã bị loại bỏ khỏi JDK hiện hành.

**Chương trình đã được kiểm chứng trên JDK trong môi trường làm việc:** hai source Java, một SPI JAR chứa `META-INF/services`, biên dịch bằng `javac --release 17 -encoding UTF-8`; chạy hai JVM riêng theo hai thứ tự provider; **mỗi JVM 33/33 assertions PASS**. Lab kiểm tra `Normalizer`, `Collator`, `BreakIterator`, tìm kiếm bỏ dấu có ý thức, `DecimalFormatSymbolsProvider`, service discovery, cấu hình và fallback. Ký hiệu đặc biệt `!` và `^` trong provider là **sentinels kiểm thử**, **không phải chuẩn ký hiệu định dạng số Việt Nam**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Unicode **code point**, Java UTF-16 `char`, code point sequence và chuỗi nhìn thấy trên màn hình.
2. Giải thích tại sao `"ấ"` và `"a\u0302\u0301"` có thể **canonical equivalent** nhưng `String.equals` trả false trước khi chuẩn hóa.
3. Dùng `java.text.Normalizer` với `Form.NFC`, `NFD`, `NFKC` và `NFKD`.
4. Dùng `Normalizer.isNormalized` và kiểm tra idempotence của bước chuẩn hóa.
5. Biết tại sao **NFKC/NFKD có thể làm mất khác biệt về mặt ký hiệu/ý nghĩa sản phẩm**.
6. Hiểu **bỏ dấu** để tạo search key khác với **chuẩn hóa Unicode** để lưu/display.
7. Xử lý riêng **đ/Đ**, vì Unicode NFD không biến chúng thành d/D.
8. Dùng `Locale.forLanguageTag("vi-VN")`, tránh phụ thuộc vào default locale của máy.
9. Dùng `Collator` với `CANONICAL_DECOMPOSITION` cho so sánh locale-sensitive, không dùng so code point thay thế quy tắc sắp xếp ngôn ngữ.
10. Dùng `BreakIterator` như một công cụ phân tách text, đồng thời biết phạm vi hỗ trợ và hạn chế.
11. Phân biệt **CLDR**, **SPI**, **HOST** providers trong Java SE 26 và biết nguồn CLDR mặc định.
12. Tạo `DecimalFormatSymbolsProvider` theo hợp đồng `LocaleServiceProvider` và đăng ký ở `META-INF/services`.
13. Dùng `ServiceLoader` để chứng minh provider có mặt trên application classpath.
14. Chạy JVM với `-Djava.locale.providers=SPI,CLDR` và `-Djava.locale.providers=CLDR,SPI` để kiểm tra thứ tự ưu tiên.
15. Hiểu vì sao nên truyền system property lúc **JVM khởi động** thay vì thay đổi giữa lúc chương trình chạy.
16. Phân biệt **có thể tìm thấy provider qua ServiceLoader** với **provider có thực sự được chọn bởi locale adapter**.
17. Dùng `DecimalFormatSymbols` và `DecimalFormat` để xác minh thay đổi ký tự và round-trip parse/format.
18. Tổ chức negative controls, test dữ liệu đúng/sai, bảo vệ dữ liệu Unicode gốc khỏi biến đổi mất thông tin.
19. Đọc kết quả 33 PASS checks ở từng JVM và áp dụng cho regression tests khi nâng JDK/CLDR.

## 2. Vì sao văn bản tiếng Việt dễ có nhiều biểu diễn Unicode?

Tiếng Việt dùng nhiều dấu: sắc, huyền, hỏi, ngã, nặng, mũ, móc, dấu breve, cùng các chữ **đ/Đ**. Các ký tự có dấu có thể được mã hóa theo nhiều cách *canonically equivalent*.

Ví dụ chữ **ấ**:

```text
Biểu diễn dựng sẵn (precomposed):
  U+1EA5 LATIN SMALL LETTER A WITH CIRCUMFLEX AND ACUTE
  "ấ"

Biểu diễn phân rã (decomposed):
  U+0061 LATIN SMALL LETTER A
  U+0302 COMBINING CIRCUMFLEX ACCENT
  U+0301 COMBINING ACUTE ACCENT
  "a" + ◌̂ + ◌́

Nhìn như cùng một chữ tiếng Việt.
Nhưng hai chuỗi ký tự khác nhau trước normalize.
```

Trong Java:

```java
String composed = "\u1EA5";
String decomposed = "a\u0302\u0301";

System.out.println(composed.equals(decomposed)); // false
```

Đây là **mảnh code**. `String.equals` so các `char` theo thứ tự, **không tự normalize Unicode**. Nếu dùng chúng làm key trong `HashMap`/`HashSet`, hai chuỗi này ban đầu có thể là hai keys khác nhau.

### 2.1. Java String dùng UTF-16

`String.length()` đếm **UTF-16 code units**, không phải số chữ người đọc nhìn thấy. Trong ví dụ:

- `composed` thường có một code point, một `char` vì U+1EA5 thuộc BMP.
- `decomposed` có ba code points và ba `char`.
- Một emoji ngoài BMP thường cần hai `char` cho một Unicode code point.
- Một cụm chữ hiển thị (*grapheme cluster*) có thể gồm nhiều code points, đặc biệt khi có combining marks.

Đếm code points bằng `codePointCount` khi cần đơn vị Unicode; khi cần **grapheme clusters cho giao diện**, phải dùng công cụ phân đoạn phù hợp như `BreakIterator`, đồng thời kiểm tra khả năng xử lý của phiên bản JDK/thư viện đối với các loại cụm phức tạp.

### 2.2. “UTF-8” không phải một dạng Normalizer.Form

UTF-8, UTF-16 là **cách mã hóa code points thành bytes/code units**; NFC/NFD là **quy tắc chuẩn hóa chuỗi code points**. Một file UTF-8 có thể chứa chuỗi NFC hoặc NFD. Mở file bằng UTF-8 **không tự chuyển dữ liệu sang NFC**.

Cũng không nên nhầm:

- `new String(bytes, StandardCharsets.UTF_8)`: giải mã bytes thành Unicode text.
- `Normalizer.normalize(text, Normalizer.Form.NFC)`: chuẩn hóa biểu diễn Unicode của text.
- `text.toLowerCase(Locale.ROOT)`: ánh xạ chữ hoa/thường theo rules, không phải normalization.
- `Collator.compare(a,b)`: so sánh locale-sensitive, không phải biến đổi hai chuỗi thành cùng dữ liệu.

## 3. Bốn dạng Unicode Normalization trong Java

`java.text.Normalizer.Form` định nghĩa:

| Form | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `NFC` | Canonical decomposition rồi canonical composition. | Chuẩn chung cho text lưu trữ/trao đổi, giảm những khác biệt biểu diễn dấu. |
| `NFD` | Canonical decomposition. | Phân tích base character + combining marks, chuẩn bị search-fold có chủ đích. |
| `NFKC` | Compatibility decomposition rồi composition. | Một số search/filter chuyên biệt có chấp nhận mất phân biệt compatibility. |
| `NFKD` | Compatibility decomposition. | Phân tích tương đương compatibility trong pipeline được kiểm soát. |

`NFKC` và `NFKD` **không tương đương với NFC/NFD** về lượng thông tin giữ lại. Ví dụ ký hiệu số **①** (U+2460) qua `NFKC` thành **1**, nhưng qua `NFC` vẫn là **①**. Tương tự, một số ký tự ligature, fullwidth forms và presentation forms có compatibility mappings.

### 3.1. Ví dụ NFC/NFD

```java
String a = "\u1EA5";
String b = "a\u0302\u0301";

String normA = Normalizer.normalize(a, Normalizer.Form.NFC);
String normB = Normalizer.normalize(b, Normalizer.Form.NFC);
boolean same = normA.equals(normB); // true
```

NFC và NFD bảo toàn **canonical equivalence**, không bảo đảm mọi chuỗi “nhìn giống” nhau có cùng normalized bytes. Các biến thể chữ, dấu câu, chữ số và homoglyphs không nhất thiết được giải quyết bởi Unicode normalization.

### 3.2. Kiểm tra và tính idempotent

Một pipeline chuẩn hóa tốt cần idempotent:

```java
String once = Normalizer.normalize(input, Normalizer.Form.NFC);
String twice = Normalizer.normalize(once, Normalizer.Form.NFC);
boolean stable = once.equals(twice); // true
```

Với chuỗi đầu vào đã ở đúng form, `Normalizer.isNormalized(input, NFC)` cho true; với chuỗi phân rã `"a\u0302\u0301"`, kết quả `isNormalized(...,NFC)` là false.

Đừng normalize theo cảm tính nhiều lần bằng cách vừa NFC vừa NFD rồi quên đặc tả output. Xác định một **canonical storage form**, phổ biến là NFC, và ghi rõ version/policy của application.

### 3.3. Vì sao NFC là default hợp lý cho text gốc?

NFC có xu hướng giữ khác biệt **semantic canonical** trong khi hợp nhất các chuỗi có cùng Unicode canonical content. Dữ liệu tên người, địa chỉ và nội dung tìm kiếm thường cần giữ **dấu tiếng Việt thật**; NFC giúp so canonical form mà không cố ý xóa dấu.

Nhưng NFC **không tự chữa**:
- Tên viết sai chính tả.
- Input khác spacing hoặc punctuation.
- `Đ` khác `D`.
- Ký tự tương tự nhau thuộc script khác.
- Các định dạng số/ngày khác locale.
- Các lỗi nhập liệu hoặc diacritic placement không tương đương Unicode.

## 4. Bỏ dấu để tìm kiếm khác với chuẩn hóa để lưu trữ

Một chức năng tìm kiếm “không phân biệt dấu” có thể cần biến `Đặng Văn Nam` thành search key `dang van nam`. Đó là **business-specific lossy transformation**, không phải `Normalizer.Form.NFC` tự làm.

Một pipeline minh họa:

1. Chuẩn hóa khoảng trắng Unicode theo policy ứng dụng.
2. Chuyển chuỗi về **NFD**.
3. Loại **combining marks** theo Unicode category `\p{M}`.
4. Ánh xạ riêng `Đ → D`, `đ → d` nếu business muốn chúng tương đương trong search.
5. Chuyển thành lowercase với `Locale.ROOT` để có key nhất quán không phụ thuộc default locale.
6. Lưu key vào **field/index riêng**; luôn giữ văn bản hiển thị gốc hoặc NFC.

```java
private static final Pattern MARKS = Pattern.compile("\\p{M}+");
private static final Pattern SPACES =
        Pattern.compile("[\\p{Z}\\s]+");

static String searchKey(String input) {
    String trimmed = SPACES.matcher(input)
            .replaceAll(" ").strip();
    String decomposed = Normalizer.normalize(
            trimmed, Normalizer.Form.NFD);
    String withoutMarks = MARKS.matcher(decomposed).replaceAll("");
    return withoutMarks.replace('\u0110', 'D')
            .replace('\u0111', 'd')
            .toLowerCase(Locale.ROOT);
}
```

Đây là **mảnh code** cần imports `Pattern`, `Normalizer`, `Locale` và kiểm tra null từ caller; chương trình hoàn chỉnh ở mục 12 dùng chính xác logic này.

### 4.1. Đặc biệt: đ/Đ không mất nét gạch khi NFD

Với `Đặng`:

```text
NFD("Đặng") => Đ + a + combining breve + combining dot-below + n + g
Xóa \p{M} => "Đang"
Ánh xạ Đ -> D => "Dang"
lowercase Locale.ROOT => "dang"
```

**Không giả định `NFD` + remove marks đã biến `đ` thành `d`**: `đ` không phân rã canonically thành `d` và dấu gạch. Cần quy tắc riêng nếu hệ thống cố ý hỗ trợ tìm không dấu kiểu đó.

### 4.2. Search key là mất thông tin — không dùng để xác định danh tính

`searchKey("má")` và `searchKey("ma")` có thể cùng cho `ma`. Hai chuỗi nguồn khác nhau, có thể có nghĩa khác nhau. Tương tự:

- `Đặng` và `Dang` có thể cùng key sau mapping.
- Các dấu phân biệt từ tiếng Việt có thể bị xóa.
- Search keys có thể collision dù hai tên pháp lý khác nhau.

Vì vậy:
- **Không lưu đè** tên người/tên đường có dấu bằng search key.
- Không coi search key là unique identifier, password normalization, chữ ký số hoặc bằng chứng pháp lý.
- Dùng primary key độc lập, lưu full original/NFC text để hiển thị.
- Với search nhiều ngôn ngữ, cần chính sách per-language chứ không áp Việt hóa `đ` cho mọi script.
- Cân nhắc full-text search engine/tokenizer/locale-specific collation nếu cần tìm kiếm nâng cao.
- Khi đổi normalization/search policy, cần **rebuild index** và kiểm tra collisions.

### 4.3. Khoảng trắng Unicode

`String.trim()` chỉ xử lý một tập ký tự nhỏ, không bao phủ mọi whitespace Unicode. `String.strip()` dùng `Character.isWhitespace`, nhưng một số không-ngắt-dòng (NBSP) không được xử lý như bạn mong muốn. Lab dùng:

```java
Pattern.compile("[\\p{Z}\\s]+")
```

để gom Unicode separator categories và whitespace mẫu thành một ASCII space, rồi `strip()`. Nó xử lý các ví dụ `U+00A0` (NBSP), `U+2003` (EM SPACE) và `U+202F` (NARROW NBSP). **Đó là chính sách search index**, không phải bước phải làm cho mọi văn bản: khi hiển thị/biên tập tài liệu, NBSP có thể có chức năng định dạng cần giữ.

Các ký tự đặc biệt như zero-width joiner hoặc bidi controls không nhất thiết thuộc `\p{Z}`; nếu ứng dụng cần phòng chống confusable/invisible text attacks, cần chính sách bảo mật Unicode riêng.

## 5. Collator: sắp xếp/so sánh không đồng nghĩa normalize

`Collator` thuộc `java.text` hỗ trợ so sánh các chuỗi theo locale, không chỉ theo code-unit order.

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vi);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

boolean equivalent =
        collator.compare("\u1EA5", "a\u0302\u0301") == 0;
```

Đây là **mảnh code**, không độc lập. Lab đã kiểm chứng so sánh bằng nhau cho cặp chữ `ấ` dạng dựng sẵn/phân rã trên runtime JDK đã thử.

### 5.1. Các mức strength của Collator

| Strength | Ý nghĩa tổng quát |
| --- | --- |
| `Collator.PRIMARY` | Khác biệt cơ bản; thường bỏ qua một số dấu/case theo collation rules. |
| `Collator.SECONDARY` | Xét các khác biệt thứ cấp, thường gồm dấu. |
| `Collator.TERTIARY` | Xét thêm các khác biệt thứ ba, thường gồm case/variants. |
| `Collator.IDENTICAL` | Mức chi tiết nhất, xét nhiều khác biệt Unicode hơn. |

**Không khẳng định** ở `PRIMARY` toàn bộ cặp chữ tiếng Việt chỉ khác dấu luôn bằng nhau. Quy tắc collation tùy ngôn ngữ, provider và version. Với tìm kiếm không dấu theo business policy, dùng search key riêng hoặc search engine có analyzer phù hợp; với **sắp xếp hiển thị theo locale**, dùng Collator và test trên JDK/locale provider thực.

### 5.2. Decomposition của Collator

- `NO_DECOMPOSITION`: không tự thực hiện canonical decomposition cho collation.
- `CANONICAL_DECOMPOSITION`: dùng canonical decomposition khi so sánh.
- `FULL_DECOMPOSITION`: xét compatibility decomposition theo contract.

Đó là **cấu hình so sánh**, không thay đổi bản thân chuỗi đầu vào. `Collator` không sửa Unicode text của application.

### 5.3. Không hardcode toàn bộ thứ tự sắp xếp theo CLDR

Oracle JDK 26 dùng CLDR mặc định cho nhiều dịch vụ locale, nhưng tài liệu supported locales nêu **Collator/BreakIterator data không dùng CLDR data** theo cách giống các dịch vụ số/ngày. Hành vi collation cũng có thể thay đổi theo JDK/provider và locale extensions. Bài chỉ assert **canonical equivalence** sau khi bật `CANONICAL_DECOMPOSITION`, **không hardcode một danh sách dài chữ Việt theo “chuẩn từ điển”** khi chưa xác minh môi trường mục tiêu.

Khi cần thứ tự tiếng Việt chuẩn cho product:
1. Xác định locale `vi-VN`.
2. Chọn strength/decomposition rõ ràng.
3. Test tập từ có `a, ă, â, d, đ, e, ê` và dấu thanh.
4. So các JDK versions/providers/cơ sở dữ liệu liên quan.
5. Không trộn một comparator version với dữ liệu persisted sort keys được sinh bởi version khác mà không kiểm tra compatibility.

### 5.4. Collator không làm String.equals thay đổi

Dù `collator.compare(a,b)==0`, `a.equals(b)` vẫn có thể false. Một `TreeSet` dùng Collator làm comparator có thể xem những strings khác `equals` là trùng. Điều đó cần được thiết kế có chủ ý, đặc biệt trong unique indexes và dữ liệu tên người.

## 6. BreakIterator và cụm ký tự hiển thị

`BreakIterator.getCharacterInstance(locale)` cung cấp ranh giới ký tự theo locale/runtime, giúp xử lý những cụm có combining marks tốt hơn cách đếm thô `String.length()`.

Ví dụ với chữ `ấ`:

- Precomposed: một code point.
- Decomposed `a + ◌̂ + ◌́`: ba code points.
- Trong lab JDK đã thử, `BreakIterator.getCharacterInstance(vi-VN)` xem cả hai biểu diễn là **một cụm ký tự**.

Không suy rộng thành “BreakIterator luôn đếm đúng mọi emoji family/ZWJ grapheme” trên mọi JDK; thuật toán segmentation và dữ liệu Unicode evolve. Khi UI cần đi theo Unicode Extended Grapheme Cluster mới nhất, phải test đúng JDK/ICU/library áp dụng cho deployment.

**Phân biệt**:
- Unicode normalization: canonical/compatibility representation.
- Case mapping: uppercase/lowercase.
- Collation: thứ tự so sánh.
- Segmentation: ranh giới grapheme/word/sentence.
- Encoding: bytes/code units.
- Locale data provider: nguồn dữ liệu cho các dịch vụ nhạy cảm locale.

## 7. Locale vi-VN theo BCP 47

Cách tạo locale hiện hành:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
System.out.println(vi.toLanguageTag()); // vi-VN
```

`vi` là language, `VN` là region. `Locale` là **mô tả quy tắc/ngữ cảnh**, không đảm bảo mọi dịch vụ đều có chính xác dữ liệu native trong mọi JVM.

### 7.1. Default locale và explicit locale

Các factory methods có overload không truyền `Locale` sẽ dùng default locale thích hợp, thường là `Locale.Category.FORMAT` cho số/ngày. Nếu CI chạy ở US và developer laptop chạy ở Việt Nam, kết quả có thể khác.

Để test deterministic:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(
                Locale.forLanguageTag("vi-VN"));
```

Không đổi `Locale.setDefault(...)` cho toàn JVM khi chỉ cần định dạng một thao tác. Thay default locale ảnh hưởng các thread/parts của ứng dụng, dễ gây state leakage trong tests.

### 7.2. Locale extension không luôn được provider hiểu

BCP 47 có Unicode locale extensions như `u-nu-latn` cho numbering system. Theo `LocaleServiceProvider`, implementation mặc định của `isSupportedLocale` **bỏ qua extensions** khi so với `getAvailableLocales`. Provider cần override nếu thực sự có nhu cầu phân biệt numbering systems/extensions.

Lab chỉ nhận `vi-VN` cơ bản; không hứa hỗ trợ mọi `vi-VN-u-...` trong provider. Khi phát triển production provider, đánh giá `getUnicodeLocaleType`, `isSupportedLocale` và factory method contract theo từng service.

## 8. Java locale providers hiện hành: CLDR, SPI, HOST

Trong Java SE 26, nguồn dữ liệu locale của JDK reference implementation gồm:

| Keyword | Nguồn | Điểm quan trọng |
| --- | --- | --- |
| `CLDR` | Unicode Common Locale Data Repository qua JDK. | **Mặc định** trong JDK hiện hành; dữ liệu/patterns có thể đổi giữa versions. |
| `SPI` | `LocaleServiceProvider` implementations từ application classpath/module path. | Cần khai báo `SPI` trong `java.locale.providers` nếu muốn dùng provider tự viết. |
| `HOST` | Cài đặt locale của hệ điều hành nếu runtime hỗ trợ. | Không có trên mọi OS/JVM; tùy default locale và khả năng host. |

**Không dùng `COMPAT` hoặc `JRE` làm giải pháp cho JDK 26**: Oracle JDK 26 Supported Locales nêu legacy `COMPAT/JRE` providers đã bị loại bỏ. Trong bài này, ta chỉ kiểm thử thứ tự **`SPI,CLDR`** và **`CLDR,SPI`**, không phụ thuộc vào host custom settings.

### 8.1. Thứ tự providers quyết định ai được dùng

```bash
java -Djava.locale.providers=SPI,CLDR ...
java -Djava.locale.providers=CLDR,SPI ...
```

Ở JVM đầu, Java tìm **SPI trước** cho dịch vụ/locale được yêu cầu; nếu không có, tìm CLDR.

Ở JVM sau, Java tìm **CLDR trước**; với locale vi-VN do JDK hỗ trợ, CLDR có thể thắng, dù SPI JAR đã được cài và `ServiceLoader` vẫn tìm thấy provider.

**Không phải mọi locale service dùng cùng một implementation bên dưới**; precedence là cơ chế tìm kiếm theo **service type và requested locale**, không phải một công tắc “đổi toàn bộ runtime thành plugin”.

### 8.2. Cài JVM property trước lúc khởi tạo services

Javadoc `LocaleServiceProvider` nói `java.locale.providers` được đọc và cache khi class/provider mechanism được khởi tạo. Vì vậy **đặt bằng launcher flag** ngay từ đầu:

```bash
java -Djava.locale.providers=SPI,CLDR ...
```

Không dùng:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
```

sau khi các locale services đã được dùng rồi mong tất cả provider caches tự cập nhật. **Hai lần chạy phải là hai JVM riêng** để tránh state/cache leak.

### 8.3. CLDR version không ổn định mãi

Javadoc Java SE 26 ghi JDK 26 dùng **CLDR 48**, còn Java 17 dùng phiên bản CLDR cũ hơn. Khi nâng JDK, number separators, date patterns, currency names và locale names có thể đổi. Tránh viết tests buộc literal output của CLDR khi business requirement chỉ là đúng format/parse logic; nếu hệ thống phải có output chính xác từng ký tự, quản lý pattern/locale/provider/JDK version rõ ràng.

## 9. LocaleServiceProvider SPI: hợp đồng đóng gói

`java.util.spi.LocaleServiceProvider` là base class cho các provider cụ thể, như:

- `java.text.spi.DecimalFormatSymbolsProvider`.
- `java.text.spi.NumberFormatProvider`.
- `java.text.spi.DateFormatProvider`.
- `java.text.spi.CollatorProvider`.
- `java.text.spi.BreakIteratorProvider`.
- Các `java.util.spi.*Provider` cho localized names/calendars/time zones.

Mỗi loại service có method factories riêng. Lab này chọn **`DecimalFormatSymbolsProvider`** vì có thể kiểm tra lựa chọn provider bằng **hai ký tự sentinel** rất rõ và hoàn toàn không cần kế toán dữ liệu số thực tế.

### 9.1. Phải implements đúng abstract methods

`DecimalFormatSymbolsProvider` yêu cầu:

- `Locale[] getAvailableLocales()`: những locales provider có thể hỗ trợ.
- `DecimalFormatSymbols getInstance(Locale locale)`: một instance cho locale được yêu cầu.
- `isSupportedLocale(Locale)` kế thừa từ base class; implementation mặc định so với `getAvailableLocales()` sau khi strip extensions.

Trong lab, provider công bố đúng **`vi-VN`**, không nhận `Locale.US`. `getInstance(Locale.US)` ném `IllegalArgumentException` vì không hỗ trợ; `getInstance(null)` ném `NullPointerException` theo contract. **Không sửa `Locale.getDefault()`** và không lén override toàn bộ locale services.

### 9.2. META-INF/services descriptor

Một provider trên application **classpath** phải có resource:

```text
META-INF/services/java.text.spi.DecimalFormatSymbolsProvider
```

với nội dung một dòng UTF-8:

```text
demo.vn.spi.VietnameseSymbolsProvider
```

Đây là **tên đầy đủ của provider class**, không phải tên service file chứa .class. File service descriptor phải có đúng path/name và được đưa vào JAR. Nếu jar có class provider nhưng không có descriptor, `ServiceLoader` không tìm thấy và locale adapter SPI cũng không thể chọn provider theo cách này.

Với **named module**, cách chuẩn là `provides java.text.spi.DecimalFormatSymbolsProvider with ...;` trong `module-info.java`. Bài dùng classpath JAR để dễ biên dịch với `--release 17`; không pha cả hai packaging modes trong một lab.

### 9.3. SPI phải được visible với system class loader

Javadoc yêu cầu locale-sensitive provider phải nhìn thấy từ **system class loader**. Đặt JAR trong application classpath hoặc module path hợp lệ. Việc provider class tồn tại trong một plugin classloader cô lập không bảo đảm JDK locale factory sẽ dùng được. Khi debug, kiểm tra JAR/resource discovery và loader của provider.

## 10. Cấu trúc dự án lab

Tạo một thư mục mới dành cho thử nghiệm:

```text
vi-normalization-spi/
  src/
    provider/
      demo/vn/spi/VietnameseSymbolsProvider.java
      META-INF/services/java.text.spi.DecimalFormatSymbolsProvider
    app/
      VietnameseLocaleLab.java
  out/
    provider/                   (javac output)
    app/                        (javac output)
  vi-locale-spi.jar             (provider class + service descriptor)
```

Các tệp nguồn Java **độc lập**, không sửa thư viện JDK hoặc cấu hình global. Provider JAR chỉ có một class thuộc namespace `demo.vn.spi` và descriptor.

Chọn cặp sentinel:

- **`!`** là decimal separator do SPI trả khi được chọn.
- **`^`** là grouping separator do SPI trả khi được chọn.
- Trên CLDR-first, ứng dụng kiểm tra hai separator **không phải sentinel**.

**Quan trọng:** các sentinel không phải quy ước số tiếng Việt; ví dụ này chỉ chứng minh **provider lookup order**. Không dùng các ký tự đó cho tiền tệ, bảng giá hoặc báo cáo thật.

## 11. File 1: VietnameseSymbolsProvider.java

**Đường dẫn:** `src/provider/demo/vn/spi/VietnameseSymbolsProvider.java`

```java
package demo.vn.spi;

import java.text.DecimalFormatSymbols;
import java.text.spi.DecimalFormatSymbolsProvider;
import java.util.Locale;

public final class VietnameseSymbolsProvider
        extends DecimalFormatSymbolsProvider {
    private static final Locale VI_VN = Locale.forLanguageTag("vi-VN");

    public VietnameseSymbolsProvider() { }

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { VI_VN };
    }

    @Override
    public DecimalFormatSymbols getInstance(Locale locale) {
        if (locale == null) throw new NullPointerException("locale");
        if (!isSupportedLocale(locale)) {
            throw new IllegalArgumentException("Unsupported: " + locale);
        }
        DecimalFormatSymbols result =
                DecimalFormatSymbols.getInstance(Locale.ROOT);
        result.setDecimalSeparator('!');
        result.setGroupingSeparator('^');
        return result;
    }
}
```

### 11.1. Giải thích

- `DecimalFormatSymbolsProvider` là type **SPI cụ thể**, không cần tự viết `ServiceLoader`.
- `getAvailableLocales()` liệt kê `vi-VN` đúng như lab muốn.
- `getInstance` tự kiểm tra locale, tạo symbol set từ `Locale.ROOT` rồi đổi hai ký tự để **nhận diện provider**.
- Vì provider này chỉ hỗ trợ `vi-VN`, gọi `DecimalFormatSymbols.getInstance(Locale.ROOT)` trong nó không tự quay lại provider vi-VN; lab đã kiểm chứng runtime không có recursion.
- Một provider production phải cung cấp locale data chuẩn, không dùng sentinels.
- `getInstance` trả một đối tượng `DecimalFormatSymbols` mới; không chia sẻ một mutable singleton giữa threads/callers.
- `isSupportedLocale` mặc định bỏ qua locale extensions, nên nếu cần tính chính xác extensions của numbering system, hãy override theo policy.

### 11.2. Một cảnh báo về dịch vụ

`DecimalFormatSymbolsProvider` phục vụ **DecimalFormatSymbols factory**. Nó không đồng nghĩa tự override **mọi** `NumberFormat.getNumberInstance` hoặc `DateTimeFormatter`. Những dịch vụ đó có factory/provider API và pipeline riêng. Lab gọi trực tiếp `DecimalFormatSymbols.getInstance(VI)`, rồi tự tạo `new DecimalFormat("#,##0.00", symbols)` để kiểm chứng tác động của symbols một cách có chủ đích.

## 12. File 2: VietnameseLocaleLab.java — chương trình đầy đủ

**Đường dẫn:** `src/app/VietnameseLocaleLab.java`

Mỗi JVM chạy cùng class, nhưng tham số cuối là `SPI` hoặc `CLDR` để xác minh mode được yêu cầu. Chương trình kiểm tra cả normalization và provider discovery/selection. `check(...)` ném `AssertionError` khi bất kỳ điều kiện nào không đúng; khi toàn bộ 33 điều kiện thành công, nó in `checks=33/33`.

```java
import java.text.BreakIterator;
import java.text.Collator;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.Normalizer;
import java.text.ParsePosition;
import java.text.spi.DecimalFormatSymbolsProvider;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.ServiceLoader;
import java.util.regex.Pattern;

public final class VietnameseLocaleLab {
    private static final Locale VI = Locale.forLanguageTag("vi-VN");
    private static final Pattern MARKS = Pattern.compile("\\p{M}+");
    private static final Pattern SPACES = Pattern.compile("[\\p{Z}\\s]+");
    private static int passed;

    private static void check(String name, boolean actual) {
        if (!actual) throw new AssertionError(name);
        passed++;
        System.out.println(name + "=PASS");
    }

    private static String nfc(String input) {
        return Normalizer.normalize(input, Normalizer.Form.NFC);
    }

    private static String searchKey(String input) {
        String trimmed = SPACES.matcher(input).replaceAll(" ").strip();
        String decomposed = Normalizer.normalize(
                trimmed, Normalizer.Form.NFD);
        String withoutMarks = MARKS.matcher(decomposed).replaceAll("");
        return withoutMarks.replace('\u0110','D')
                .replace('\u0111','d').toLowerCase(Locale.ROOT);
    }

    private static int boundaries(BreakIterator iterator, String input) {
        iterator.setText(input);
        int count = 0;
        for (int pos = iterator.first(), next = iterator.next();
                next != BreakIterator.DONE;
                pos = next, next = iterator.next()) {
            if (next <= pos) throw new AssertionError("Invalid boundary");
            count++;
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 1 ? args[0] : "";
        check("validMode", mode.equals("SPI") || mode.equals("CLDR"));
        check("localeBCP47", VI.toLanguageTag().equals("vi-VN"));

        String composed = "\u1EA5";  // Vietnamese 'ấ'
        String decomposed = "a\u0302\u0301";
        check("rawStringsDiffer", !composed.equals(decomposed));
        check("nfcCanonicalEquality",
                nfc(composed).equals(nfc(decomposed)));
        check("nfdCanonicalEquality",
                Normalizer.normalize(composed, Normalizer.Form.NFD)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFD)));
        check("nfcOneCodePoint",
                nfc(composed).codePointCount(0,nfc(composed).length()) == 1);
        String nfd = Normalizer.normalize(composed, Normalizer.Form.NFD);
        check("nfdThreeCodePoints",
                nfd.codePointCount(0,nfd.length()) == 3);
        check("nfcIdempotent", nfc(nfc(decomposed)).equals(nfc(decomposed)));
        check("isNormalized",
                Normalizer.isNormalized(nfc(decomposed), Normalizer.Form.NFC)
                && !Normalizer.isNormalized(decomposed, Normalizer.Form.NFC));
        check("nfcNotCompatibilityFold", !nfc("\u2460").equals("1"));
        check("nfkcCompatibilityFold", Normalizer.normalize(
                "\u2460", Normalizer.Form.NFKC).equals("1"));
        check("markRemovalLeavesStrokeD",
                MARKS.matcher(Normalizer.normalize(
                        "\u0110\u1EB7ng", Normalizer.Form.NFD))
                        .replaceAll("").equals("\u0110ang"));
        check("searchKeyVietnamese",
                searchKey(" \u00A0\u0110\u1EB7ng\u2003V\u0103n\u202FN\u1EA1m ")
                        .equals("dang van nam"));
        check("searchKeyCanonicalInvariant",
                searchKey(composed).equals(searchKey(decomposed)));
        check("searchKeyLosesMeaning",
                searchKey("m\u00E1").equals(searchKey("ma"))
                && !"m\u00E1".equals("ma"));
        check("unicodeWhitespaceCollapsed",
                SPACES.matcher("a\u00A0\u2003b\u202Fc")
                        .replaceAll(" ").equals("a b c"));

        Collator collator = Collator.getInstance(VI);
        collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
        check("collatorCanonicalEquality",
                collator.compare(composed,decomposed) == 0);
        check("collatorUsesCanonicalDecomposition",
                collator.getDecomposition() == Collator.CANONICAL_DECOMPOSITION);
        check("collatorSelfEquality",
                collator.compare("\u0110\u1EB7ng", "\u0110\u1EB7ng") == 0);
        check("breakIteratorVietnameseCharacter",
                boundaries(BreakIterator.getCharacterInstance(VI),
                        composed) == 1
                && boundaries(BreakIterator.getCharacterInstance(VI),
                        decomposed) == 1);

        List<DecimalFormatSymbolsProvider> providers = new ArrayList<>();
        ServiceLoader.load(DecimalFormatSymbolsProvider.class)
                .forEach(providers::add);
        DecimalFormatSymbolsProvider own = providers.stream()
                .filter(p->p.getClass().getName()
                        .equals("demo.vn.spi.VietnameseSymbolsProvider"))
                .findFirst().orElseThrow();
        check("providerDiscovered", own != null);
        check("providerViVNAdvertised",
                List.of(own.getAvailableLocales()).contains(VI)
                && own.isSupportedLocale(VI));
        check("providerNotForUS", !own.isSupportedLocale(Locale.US));
        check("providerDirectInstance",
                own.getInstance(VI).getDecimalSeparator() == '!'
                && own.getInstance(VI).getGroupingSeparator() == '^');

        boolean rejected = false;
        try { own.getInstance(Locale.US); }
        catch(IllegalArgumentException expected) { rejected = true; }
        check("providerDirectRejectsUS", rejected);

        boolean spiMode = mode.equals("SPI");
        String setting = System.getProperty("java.locale.providers");
        check("providerOrderCLI",
                (spiMode && setting.equals("SPI,CLDR"))
                || (!spiMode && setting.equals("CLDR,SPI")));

        DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(VI);
        check("spiChosenOnlyWhenFirst",
                (symbols.getDecimalSeparator() == '!') == spiMode);
        check("spiGroupingOnlyWhenFirst",
                (symbols.getGroupingSeparator() == '^') == spiMode);
        DecimalFormat fmt = new DecimalFormat("#,##0.00", symbols);
        String formatted = fmt.format(12345.67);
        check("explicitSymbolFormatting",
                spiMode ? formatted.equals("12^345!67")
                        : !formatted.contains("!"));
        ParsePosition position = new ParsePosition(0);
        Number parsed = fmt.parse(formatted,position);
        check("parseRoundTrip",
                parsed!=null && Math.abs(parsed.doubleValue()-12345.67)<0.000001
                && position.getIndex()==formatted.length());
        DecimalFormatSymbols us = DecimalFormatSymbols.getInstance(Locale.US);
        check("fallbackUS",
                us.getDecimalSeparator()=='.'
                && us.getGroupingSeparator()==',');
        check("normalizationProviderIndependent", nfc(decomposed).equals(composed));
        check("explicitCaseMappingLocale",
                "\u0110\u1EB6NG".toLowerCase(Locale.ROOT).equals("\u0111\u1EB7ng"));
        System.out.println("checks="+passed+"/"+passed);
    }
}
```

### 12.1. Vì sao dùng ServiceLoader riêng để kiểm tra?

`ServiceLoader.load(DecimalFormatSymbolsProvider.class)` chỉ xác nhận **service descriptor và class provider được phát hiện**, không chứng minh Java locale factory đã chọn nó. Mã tiếp tục gọi `DecimalFormatSymbols.getInstance(VI)` và kiểm tra sentinel characters theo thứ tự providers.

Như vậy có ba tầng kiểm thử:

1. **Provider JAR discovery**: `providerDiscovered` và `providerViVNAdvertised`.
2. **Provider trực tiếp**: `providerDirectInstance` xác nhận nội dung nó trả.
3. **Locale factory integration**: `spiChosenOnlyWhenFirst` và `spiGroupingOnlyWhenFirst` xác minh actual selection qua JDK.

Nếu tầng 1 PASS nhưng tầng 3 FAIL, nguyên nhân có thể là `java.locale.providers` chưa bao gồm `SPI`, thứ tự bị đảo, locale không được công bố, hoặc provider JAR không visible đúng loader.

### 12.2. Vì sao DecimalFormat lại được tạo với symbols rõ ràng?

Lab dùng:

```java
DecimalFormat fmt = new DecimalFormat("#,##0.00", symbols);
```

để xác nhận ngay cả khi ký hiệu provider là `!`/`^`, Java vẫn có thể format và parse nhất quán theo pattern. `DecimalFormatSymbolsProvider` **không phải** `NumberFormatProvider`; không suy rằng `NumberFormat.getNumberInstance(VI)` chắc chắn bị thay đổi bởi SPI này trong mọi implementation.

`NumberFormat`/`DecimalFormat` cũng **không nên được chia sẻ mutable instance giữa threads** nếu không có đồng bộ. Tạo instance phù hợp từng request/thread hoặc dùng formatter immutable khác theo API tương ứng.

## 13. Biên dịch, đóng gói và chạy trên Windows PowerShell

Từ thư mục `vi-normalization-spi` chứa `src`:

```powershell
New-Item -ItemType Directory -Force out/provider,out/app | Out-Null

javac --release 17 -encoding UTF-8 -d out/provider src/provider/demo/vn/spi/VietnameseSymbolsProvider.java
javac --release 17 -encoding UTF-8 -d out/app src/app/VietnameseLocaleLab.java

jar --create --file vi-locale-spi.jar -C out/provider . -C src/provider META-INF/services

java '-Djava.locale.providers=SPI,CLDR' -cp 'out/app;vi-locale-spi.jar' VietnameseLocaleLab SPI

java '-Djava.locale.providers=CLDR,SPI' -cp 'out/app;vi-locale-spi.jar' VietnameseLocaleLab CLDR
```

**Tạo tệp descriptor** tại `src/provider/META-INF/services/java.text.spi.DecimalFormatSymbolsProvider` với một dòng tên provider class. Đảm bảo file UTF-8. Lệnh `jar --create` đưa cả `out/provider` và `META-INF/services` vào JAR.

**Điểm quan trọng:** dấu `;` trong `-cp` là separator của Windows classpath. Phải chạy từ đúng thư mục lab để `out/app` và `vi-locale-spi.jar` được tìm thấy. Hai lần `java` ở đây là **hai JVM processes khác nhau**, tránh provider cache trong cùng JVM.

### 13.1. Lệnh tương đương trên Bash (Linux/macOS)

```bash
mkdir -p out/provider out/app

javac --release 17 -encoding UTF-8 -d out/provider \
  src/provider/demo/vn/spi/VietnameseSymbolsProvider.java

javac --release 17 -encoding UTF-8 -d out/app \
  src/app/VietnameseLocaleLab.java

jar --create --file vi-locale-spi.jar \
  -C out/provider . -C src/provider META-INF/services

java '-Djava.locale.providers=SPI,CLDR' \
  -cp 'out/app:vi-locale-spi.jar' VietnameseLocaleLab SPI

java '-Djava.locale.providers=CLDR,SPI' \
  -cp 'out/app:vi-locale-spi.jar' VietnameseLocaleLab CLDR
```

Dấu `:` ở đây là separator classpath trên Linux/macOS. **Lệnh Bash là hướng dẫn tương ứng**, còn kết quả kiểm chứng 33/33 từ môi trường làm việc đã thực sự chạy trên Windows PowerShell/JDK với classpath `;`.

### 13.2. Kiểm tra nội dung JAR

```bash
jar --list --file vi-locale-spi.jar
```

Xác minh có **cả**:

```text
demo/vn/spi/VietnameseSymbolsProvider.class
META-INF/services/java.text.spi.DecimalFormatSymbolsProvider
```

Nếu descriptor không có trong JAR, hãy sửa packaging, không tự suy từ sự tồn tại của `VietnameseSymbolsProvider.class` mà service discovery đã hoạt động.

### 13.3. Không dùng các cờ locale đã lỗi thời

Trên JDK hiện hành, **không** dùng `-Djava.locale.providers=COMPAT,SPI` hoặc `JRE` như mẹo fallback; legacy providers đó đã bị gỡ. Hãy thử với `SPI,CLDR` và `CLDR,SPI` hoặc thêm `HOST` khi JDK/OS có hỗ trợ và có yêu cầu riêng.

## 14. Stdout đã kiểm chứng ở cả hai chế độ

**Một lần chạy `VietnameseLocaleLab SPI` và một lần chạy `VietnameseLocaleLab CLDR` đều in chính xác các dòng Java stdout sau trên JDK đã kiểm thử:**

```text
validMode=PASS
localeBCP47=PASS
rawStringsDiffer=PASS
nfcCanonicalEquality=PASS
nfdCanonicalEquality=PASS
nfcOneCodePoint=PASS
nfdThreeCodePoints=PASS
nfcIdempotent=PASS
isNormalized=PASS
nfcNotCompatibilityFold=PASS
nfkcCompatibilityFold=PASS
markRemovalLeavesStrokeD=PASS
searchKeyVietnamese=PASS
searchKeyCanonicalInvariant=PASS
searchKeyLosesMeaning=PASS
unicodeWhitespaceCollapsed=PASS
collatorCanonicalEquality=PASS
collatorUsesCanonicalDecomposition=PASS
collatorSelfEquality=PASS
breakIteratorVietnameseCharacter=PASS
providerDiscovered=PASS
providerViVNAdvertised=PASS
providerNotForUS=PASS
providerDirectInstance=PASS
providerDirectRejectsUS=PASS
providerOrderCLI=PASS
spiChosenOnlyWhenFirst=PASS
spiGroupingOnlyWhenFirst=PASS
explicitSymbolFormatting=PASS
parseRoundTrip=PASS
fallbackUS=PASS
normalizationProviderIndependent=PASS
explicitCaseMappingLocale=PASS
checks=33/33
```

Có **33 dòng PASS + 1 dòng tổng kết mỗi JVM**; **hai lần riêng đều đạt 33/33**, tổng cộng **66 assertions** được thực thi qua hai cấu hình. Không phải 33 assertions “chỉ chạy một lần rồi đoán kết quả JVM thứ hai”.

### 14.1. Bản chất của phép kiểm tra SPI/CLDR

Trong nhánh `SPI`:
- `-Djava.locale.providers=SPI,CLDR` được đọc từ system property.
- `DecimalFormatSymbols.getInstance(vi-VN)` trả decimal separator `!` và grouping separator `^` từ provider tự viết.
- `new DecimalFormat("#,##0.00", symbols).format(12345.67)` trả `12^345!67` trong môi trường thử.
- `parse` round-trip trả giá trị tương ứng.
- `Locale.US` không bị provider vi-VN can thiệp.

Trong nhánh `CLDR`:
- `-Djava.locale.providers=CLDR,SPI` được đọc từ system property.
- `DecimalFormatSymbols.getInstance(vi-VN)` **không** trả sentinel `!`/`^`, vì CLDR được ưu tiên.
- `ServiceLoader` **vẫn tìm thấy** `VietnameseSymbolsProvider`; điều này chứng minh **discovered ≠ selected**.
- `DecimalFormat` parse/format round-trip vẫn hoạt động với symbols CLDR.
- Các assertions Unicode/Collator/BreakIterator vẫn PASS; normalization không phụ thuộc vào ưu tiên decimal-symbol provider.

**Không assert một dấu phân cách số Việt Nam mặc định cố định qua mọi CLDR version.** Lab chỉ cần sentinel trong SPI-first và **absence of sentinel** trong CLDR-first, đủ chứng minh provider ordering mà không khóa cứng các chi tiết CLDR có thể thay đổi.

## 15. Giải thích 33 kiểm tra theo nhóm

### 15.1. Locale và Normalizer (16 checks)

- `validMode`: chương trình nhận đúng mode `SPI`/`CLDR`.
- `localeBCP47`: `vi-VN` được parse và xuất đúng tag.
- `rawStringsDiffer`: hai biểu diễn Unicode khác nhau trước normalize.
- `nfcCanonicalEquality`/`nfdCanonicalEquality`: canonical variants trở về cùng form.
- `nfcOneCodePoint`/`nfdThreeCodePoints`: số code points thay đổi theo form.
- `nfcIdempotent`/`isNormalized`: normalize ổn định, phát hiện đúng chuỗi chưa NFC.
- `nfcNotCompatibilityFold`/`nfkcCompatibilityFold`: chữ số khoanh tròn **①** không bị NFC đổi thành **1**, nhưng NFKC đổi thành **1**.
- `markRemovalLeavesStrokeD`: xóa combining marks không biến `Đ` thành `D`.
- `searchKeyVietnamese`: `Đặng Văn Nam` có NBSP và Unicode spaces sinh search key `dang van nam` theo policy.
- `searchKeyCanonicalInvariant`: search key giống nhau dù nguồn là composed/decomposed.
- `searchKeyLosesMeaning`: `má` và `ma` bị nhập làm một search key.
- `unicodeWhitespaceCollapsed`: gom Unicode separators theo policy.

### 15.2. Collator và BreakIterator (4 checks)

- `collatorCanonicalEquality`: hai biểu diễn chữ `ấ` so như tương đương sau bật canonical decomposition.
- `collatorUsesCanonicalDecomposition`: đọc lại đúng mode đã set.
- `collatorSelfEquality`: comparator phản xạ với chính chuỗi `Đặng`.
- `breakIteratorVietnameseCharacter`: một chữ `ấ` composed hoặc decomposed có một character boundary group trong lab.

### 15.3. SPI discovery, hợp đồng provider (5 checks)

- `providerDiscovered`: `ServiceLoader` tìm đúng class đã đóng gói.
- `providerViVNAdvertised`: `getAvailableLocales`/`isSupportedLocale` công bố vi-VN.
- `providerNotForUS`: provider không đòi xử lý Locale.US.
- `providerDirectInstance`: method của provider tạo đúng hai sentinels.
- `providerDirectRejectsUS`: direct call với locale không hỗ trợ ném đúng exception.

### 15.4. Thứ tự provider và fallback (8 checks)

- `providerOrderCLI`: JVM có đúng property tương ứng mode.
- `spiChosenOnlyWhenFirst`: decimal symbol `!` xuất hiện **chỉ trong SPI-first**.
- `spiGroupingOnlyWhenFirst`: grouping symbol `^` xuất hiện **chỉ trong SPI-first**.
- `explicitSymbolFormatting`: format với symbols đã lấy; SPI-first tạo text sentinel.
- `parseRoundTrip`: parse đủ cả formatted input và giữ numerical value.
- `fallbackUS`: Locale.US vẫn có symbols chuẩn và provider vi-VN không làm thay đổi.
- `normalizationProviderIndependent`: NFC Unicode không phụ thuộc provider ưu tiên.
- `explicitCaseMappingLocale`: gọi toLowerCase với Locale.ROOT rõ ràng, không dựa vào default locale.

## 16. Kiểm thử âm và các trường hợp biên nên bổ sung

| Case | Thực hiện | Kỳ vọng |
| --- | --- | --- |
| Thiếu `META-INF/services` | Build JAR chỉ có provider.class. | ServiceLoader không phát hiện provider qua descriptor. |
| Descriptor sai tên interface | Đặt file khác `java.text.spi.DecimalFormatSymbolsProvider`. | Không có provider theo service type đúng. |
| Descriptor sai class name | Class không tồn tại/không loadable. | `ServiceConfigurationError` hoặc lỗi service lookup. |
| Không có `SPI` trong property | Chạy `-Djava.locale.providers=CLDR`. | Không chọn SPI trong locale factory, dù JAR vẫn có. |
| Đổi provider order | Chạy hai JVM độc lập. | Sentinels chỉ chọn ở SPI-first. |
| Chỉ chạy trong cùng một JVM | Đổi System.setProperty sau factory call. | Không bảo đảm provider caches được cập nhật. |
| Provider chỉ hỗ trợ vi-VN | Gọi provider direct với Locale.US. | `IllegalArgumentException`. |
| Null locale | `getInstance(null)` trên provider direct. | `NullPointerException`. |
| Unicode composed/decomposed | `ấ` dựng sẵn và phân rã. | NFC/NFD canonically equal. |
| NFKC vs NFC | `①` vs `1`. | Chỉ compatibility normalization nhập làm một. |
| Đ/đ | `Đặng` qua NFD+remove marks. | Vẫn còn Đ; mapping riêng nếu muốn d. |
| Whitespace Unicode | NBSP, EM SPACE, NARROW NBSP. | Search policy gom spaces, không ảnh hưởng raw display field. |
| Search collision | `ma` và `má`. | Search key có thể trùng; ID vẫn độc lập. |
| Dấu thứ tự khác nhau | Combining marks reordered. | Normalize về canonical order nếu canonically equivalent. |
| Unicode extension | `vi-VN-u-nu-latn`. | Provider phải xác định có nhận extension không, không giả định. |
| JDK/CLDR upgrade | Chạy lại formatting tests. | Đánh giá thay đổi output theo version, tránh false regression. |
| Multi-thread formatter | Chia sẻ một DecimalFormat instance. | Cần thread-safety strategy riêng; không coi object mutable là safe. |
| Homoglyph/invisible text | Unicode confusables/zero-width. | Cần security normalization và validation policy riêng. |

Để có test CI ổn định, hãy **đặt môi trường locale rõ ràng**, dùng hai child JVM (hoặc hai job/processes) và assert đúng các semantics thay vì dựa vào output hiện tại của một bản CLDR.

## 17. Tránh các cách hiểu sai về locale provider

### 17.1. Provider “được tìm thấy” chưa chắc “được chọn”

`ServiceLoader.load(...).findFirst()` có thể tìm được provider từ classpath trong cả hai JVM, nhưng khi `java.locale.providers=CLDR,SPI` và CLDR hỗ trợ locale đó, locale factory có thể không dùng provider tự viết. Thứ tự lookup ưu tiên **được cấu hình khi khởi động JVM**.

### 17.2. Locale vi-VN không phải “tự động xóa dấu”

`Locale.forLanguageTag("vi-VN")` không biến `Đà Nẵng` thành `da nang`. Nó giúp factory chọn dữ liệu locale, còn bỏ dấu là một thuật toán search-fold do ứng dụng quyết định.

### 17.3. NFC không làm tiếng Việt thành ASCII

NFC chủ yếu chuẩn hóa dạng Unicode tương đương, không xóa dấu. Nếu yêu cầu là hiển thị đúng tên Việt, **giữ NFC text**, không gọi regex remove marks.

### 17.4. Collator không làm data normalization trong DB

Sắp xếp bằng `Collator` hoặc DB collation không làm các chuỗi lưu trong database trở thành canonical equivalents. Dù `compare(a,b)==0`, primary key/index/HashMap có thể còn coi `a` và `b` khác nếu không có normalization contract riêng.

### 17.5. NFKC có thể xóa khác biệt mong muốn

NFKC phù hợp một số chính sách search/identifier compatibility, nhưng có thể biến các ký tự trình bày và compatibility symbols thành dạng khác. Không áp nó lên mọi free-form text, code, password hoặc pháp lý khi chưa có yêu cầu nghiệp vụ và threat model rõ.

### 17.6. “COMPAT/JRE provider” không còn là hướng dẫn cho JDK hiện hành

Các tài liệu Java 8–13 cũ có thể nhắc `JRE` hoặc `COMPAT`. JDK 26 Supported Locales công bố chúng đã bị loại bỏ. Trong bài này chỉ dùng `CLDR`, `SPI` và mô tả `HOST` khi có.

### 17.7. HOST provider không đồng nghĩa CLDR hay SPI

`HOST` có thể phản ánh lựa chọn định dạng của hệ điều hành, nhưng availability khác nhau theo OS/vendor. Nếu test muốn reproducible, không dựa vào việc Windows/macOS người dùng đã đổi regional settings.

## 18. Thiết kế pipeline dữ liệu tiếng Việt cho ứng dụng thật

Một mô hình thực tế cho tên hoặc địa chỉ:

```text
Received raw Unicode
      |
      +-- validate UTF input / length / control characters theo policy
      |
      +-- normalize NFC -> display/storage field (giữ dấu)
      |
      +-- derive searchKey:
      |       Unicode whitespace policy
      |       NFD + optional remove combining marks
      |       Đ/đ mapping
      |       case mapping Locale.ROOT
      |       -> normalized search index (mất thông tin)
      |
      +-- optional locale-aware sorting/display:
      |       Collator configured for vi-VN
      |
      +-- number/date display:
              DecimalFormatSymbols, NumberFormat,
              DateTimeFormatter with explicit Locale
```

### 18.1. Cần quyết định chỗ đặt normalization

- Input API: normalize NFC trước khi viết store nếu API contract cho phép.
- Ingestion batch: chuẩn hóa các file UTF-8 từ nhiều nguồn trước khi so với kho dữ liệu.
- Search index: build search keys một cách **versioned/reproducible**.
- Database: kiểm tra collation/normalization riêng; Java client normalization và DB collation không mặc nhiên đồng nhất.
- Output: giữ dấu và chữ viết hoa đúng như input/canonical policy; không dùng search key để hiển thị.

### 18.2. Không normalize một cách phá hoại

Nếu lưu duy nhất `dang van nam` thay `Đặng Văn Nam`, hệ thống mất thông tin chữ viết. Cần giữ raw/NFC field để hoàn nguyên. Tối thiểu có:

- `id`: định danh business/technical độc lập.
- `displayNameNfc`: văn bản Unicode hiển thị.
- `searchKeyV1`: field/tập khóa phục vụ tìm kiếm, có version.
- `policyVersion` hoặc metadata tương đương nếu pipeline có khả năng đổi.

Một thay đổi về Unicode library version/locale policy có thể làm key trùng khác đi, cần kế hoạch migrate/reindex và test dataset thực tế.

### 18.3. Sắp xếp khác tra cứu

Search không dấu có thể dùng `searchKey`/full-text analyzer. Sắp xếp tiếng Việt nên dùng Collator/collation phù hợp, **không sort search keys rồi nghĩ đó là thứ tự từ điển tiếng Việt**. Dữ liệu số và ngày cần formatter riêng; `Normalizer` không liên quan dấu phân cách hàng nghìn.

### 18.4. Không hardcode dấu phân cách số thành data contract

Một bộ test có output “1.234,56” trên máy này có thể thay đổi trên máy khác hoặc JDK khác nếu locale provider khác. Với machine-to-machine protocol, định nghĩa **định dạng trung lập** như JSON numbers/ISO date-time theo spec thay vì lấy localized display text làm storage format. Với UI, dùng locale có chủ đích.

## 19. Hướng dẫn xử lý sự cố và debug

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| Hai chữ nhìn như một nhưng `equals` false. | Composed vs decomposed Unicode. | NFC hai phía trước khi so theo canonical policy. |
| Search không dấu bỏ sót `Đ/đ`. | NFD không phân rã chữ gạch ngang. | Mapping riêng nếu business yêu cầu. |
| Search mất khác biệt `ma`/`má`. | Xóa combining marks là lossy. | Không dùng search key làm unique ID. |
| NFKC đổi ký hiệu `①` thành `1`. | Compatibility folding. | Dùng NFC cho display/storage khi cần giữ khác biệt. |
| `String.length` khác số chữ hiển thị. | UTF-16 code units/combining marks. | codePointCount/BreakIterator theo nhu cầu. |
| Collator sort khác thứ tự Unicode. | Locale-sensitive rules khác code-unit. | Kiểm tra strength/decomposition/provider. |
| Provider.class có trong JAR nhưng không chạy. | Thiếu `META-INF/services` hoặc module `provides`. | Kiểm tra JAR entries và descriptor. |
| ServiceLoader tìm thấy nhưng factory không dùng. | `CLDR` được ưu tiên hoặc `SPI` vắng trong property. | Kiểm tra launcher `-Djava.locale.providers`. |
| Test đổi System.setProperty nhưng không có hiệu lực. | Provider order đã được cached lúc khởi tạo. | Chạy một JVM mới với đúng CLI property. |
| `ServiceConfigurationError` khi load provider. | Descriptor sai class name, class không public/không loadable, lỗi khởi tạo. | Sửa packaging và constructor/provider class. |
| `IllegalArgumentException` khi provider direct Locale.US. | Locale không thuộc getAvailableLocales. | Validate input/only claim supported locales. |
| Symbols giống CLDR dù code mong sentinel. | Provider lookup order hoặc jar không visible. | Test 3 tầng discovery/direct/factory. |
| Date/number output thay đổi sau JDK upgrade. | CLDR version/locale data đổi. | Regression snapshots theo JDK target, version policy. |
| Định dạng số đúng ở app nhưng sai ở backend. | Default FORMAT locale khác, service provider khác. | Truyền explicit locale, cấu hình thống nhất. |
| Ký hiệu tiền tệ/số bất thường. | Sentinel provider test bị đưa vào production. | Không triển khai lab provider vào production. |
| DecimalFormat cho kết quả sai khi nhiều threads dùng chung. | Mutable formatter không được bảo vệ. | Tạo instance riêng hoặc đồng bộ. |
| Search/index có duplicate names. | Canonical variants hoặc lossy search key collisions. | Normalize NFC, business ID riêng, reindex có kiểm soát. |

## 20. Checklist kiểm thử end-to-end

- [ ] Source files lưu UTF-8, không phụ thuộc codepage của terminal?
- [ ] File test dùng Unicode escapes cho các ký tự cần xác định chính xác code point?
- [ ] Có kiểm tra `String.equals` trước normalize khác nhau?
- [ ] Có kiểm tra NFC và NFD canonical equivalence?
- [ ] Có kiểm tra `Normalizer.isNormalized`/idempotence?
- [ ] Có negative test NFKC compatibility mapping?
- [ ] Có test chữ Đ/đ và sự khác biệt so với remove marks?
- [ ] Có test mất thông tin của searchKey(`má`) vs searchKey(`ma`)?
- [ ] Có test Unicode whitespace (NBSP, EM SPACE, NARROW NBSP)?
- [ ] Có explicit `Locale.forLanguageTag("vi-VN")`?
- [ ] Có `Collator.CANONICAL_DECOMPOSITION` khi so composed/decomposed?
- [ ] Có xem BreakIterator theo version/runtime đúng phạm vi?
- [ ] Có service descriptor UTF-8 đúng path/name?
- [ ] Có public provider class và no-arg constructor?
- [ ] `getAvailableLocales` có vi-VN và không claim Locale.US?
- [ ] Có direct `getInstance(VI)` và negative `getInstance(Locale.US)`?
- [ ] Có `ServiceLoader` discovery test?
- [ ] Có integration test qua `DecimalFormatSymbols.getInstance(VI)`?
- [ ] Có **hai JVM độc lập** cho `SPI,CLDR` và `CLDR,SPI`?
- [ ] Provider order đặt ở launcher, không sửa sau initialization?
- [ ] Có xác nhận sentinels `!` và `^` chỉ ở SPI-first?
- [ ] Có fallback Locale.US không bị ảnh hưởng?
- [ ] Có test format/parse round-trip với symbols được chọn?
- [ ] Có đếm đúng **33/33** trong từng process?
- [ ] Có phân biệt text gốc NFC và search key mất dấu trong design?
- [ ] Có khóa version JDK/CLDR khi so output nhạy cảm?
- [ ] Có loại bỏ provider thử nghiệm khỏi production artifacts?
- [ ] Có lên kế hoạch reindex/migration khi thay policy Unicode/locale?

## 21. Bài tập mở rộng

**A — Composed và decomposed.** Tạo `ấ` hai cách bằng Unicode escape, in `length/codePointCount/equals` trước và sau NFC.

**B — NFD nhiều dấu.** Dùng `Đặng`, `ẵ` và `ộ`; liệt kê Unicode code points sau NFD và so với NFC.

**C — Canonical idempotence.** Viết property-based test `NFC(NFC(s)) == NFC(s)` trên một tập chuỗi tiếng Việt và combining marks.

**D — Compatibility differences.** So `NFC/NFKC` với ký hiệu ①, fullwidth latin characters, ligatures; phân tích thông tin bị mất.

**E — Đ và d.** Thử bỏ combining marks trên `đ/Đ`, xác minh không thành d/D; thêm mapping đúng phạm vi của search.

**F — Whitespace.** Thử NBSP, thin space, EM SPACE và zero-width space; xác định ranh giới policy.

**G — Collation.** Sắp tập `An, Ân, Ăn, Đăng, Dang, Dâng` với Collator vi-VN theo nhiều strengths; kiểm tra trên JDK deployment, không giả định giống Unicode code-point order.

**H — BreakIterator.** Dùng character/word iterators cho câu tiếng Việt, kiểm tra word boundaries và grapheme clusters; đừng khẳng định word tokenizer hoàn chỉnh cho mọi ngữ cảnh.

**I — Descriptor bị thiếu.** Xây vi-locale-spi.jar không có service file; xem ServiceLoader có còn tìm được provider không.

**J — Descriptor sai.** Viết sai class name trong META-INF/services; ghi nhận lỗi ServiceConfigurationError.

**K — Đảo thứ tự.** Chạy JVM mới với `CLDR,SPI`; giải thích vì sao ServiceLoader thấy provider nhưng locale factory không chọn sentinel.

**L — Không khai báo SPI.** Chạy `-Djava.locale.providers=CLDR`; xác nhận provider test không được dùng cho vi-VN.

**M — Fallback.** Provider chỉ công bố vi-VN; thử Locale.US và một locale chưa có provider, phân tích lookup/fallback.

**N — Extension-aware provider.** Thử `vi-VN-u-nu-latn` và `vi-VN-u-nu-arab`. Thiết kế override `isSupportedLocale` nếu production service cần phân biệt numbering system.

**O — Number formatting.** Tạo DecimalFormat từ symbols rõ ràng, thử format/parse và kiểm tra ParsePosition tiêu thụ hết chuỗi.

**P — JDK upgrade.** Chạy test trong 2 JDK versions, ghi lại provider selection và định dạng số, không coi mọi ký tự CLDR khác nhau là bug.

**Q — Unique index.** Tìm các cặp tên khác nhau cùng search key; thiết kế cách giữ IDs và original NFC names.

**R — Security.** Thêm test Unicode confusables/bidi/invisible controls; phân biệt sanitization, normalization và authentication.

**S — Concurrency.** Tạo nhiều tasks định dạng số; dùng formatter riêng từng task và đối chiếu với chia sẻ một mutable formatter.

**T — Production acceptance.** Viết checklist rollout SPI provider: artifacts, package namespace, supported locales, fallback, tests, rollback và no sentinel leaks.

## 22. Câu hỏi tự kiểm tra

**1. NFC và UTF-8 là một không?** — Không. UTF-8 mã hóa bytes, NFC chuẩn hóa code points.

**2. Vì sao `String.equals` có thể khác trên hai chữ “ấ” nhìn giống nhau?** — Một chuỗi là U+1EA5, một chuỗi là a + combining marks; chưa normalize.

**3. Dùng API nào để chuẩn hóa?** — `Normalizer.normalize(text, Normalizer.Form.NFC)`.

**4. NFC có xóa dấu tiếng Việt không?** — Không, canonical normalization giữ ý nghĩa dấu.

**5. NFD làm gì?** — Canonical decomposition, cho thấy base character và combining marks.

**6. NFKC khác NFC ở đâu?** — Có compatibility mappings, có thể nhập các ký hiệu khác nhau thành cùng dạng.

**7. Vì sao không dùng search key bỏ dấu làm unique ID?** — Nhiều chuỗi khác nhau trùng key (ma/má), mất thông tin.

**8. NFD + remove marks có tự biến đ thành d không?** — Không; cần mapping riêng nếu muốn.

**9. Khi nào dùng Locale.ROOT?** — Một lựa chọn cho case mapping không phụ thuộc default locale trong pipeline kỹ thuật, không thay thế collation linguistics.

**10. Collator có sửa String gốc không?** — Không, nó thực hiện so sánh locale-sensitive.

**11. CANONICAL_DECOMPOSITION của Collator làm gì?** — Xem canonical variants đúng theo canonical decomposition khi so.

**12. BreakIterator có phải Unicode Normalizer không?** — Không; nó xác định ranh giới text.

**13. Java SE 26 locale provider mặc định là gì?** — CLDR.

**14. SPI nghĩa là gì ở đây?** — Locale-sensitive Service Provider Interface, như DecimalFormatSymbolsProvider.

**15. Descriptor của DecimalFormatSymbolsProvider nằm ở đâu?** — `META-INF/services/java.text.spi.DecimalFormatSymbolsProvider`.

**16. Có provider.class trong JAR đủ chưa?** — Chưa, classpath SPI còn cần descriptor đúng.

**17. Provider thử nghiệm công bố locale nào?** — vi-VN.

**18. Vì sao test trực tiếp provider và qua factory riêng?** — Discovery/direct return khác với locale-adapter selection.

**19. Đặt thứ tự provider thế nào?** — `-Djava.locale.providers=SPI,CLDR` hoặc `CLDR,SPI` lúc khởi động JVM.

**20. Vì sao phải hai JVM?** — Property provider order được cache khi cơ chế locale khởi tạo; đổi giữa runtime không đáng tin.

**21. `ServiceLoader` thấy SPI provider có bảo đảm nó được chọn không?** — Không; CLDR có thể được ưu tiên trước.

**22. Sentinels ! và ^ có phải định dạng số Việt Nam không?** — Không, chỉ kiểm tra provider selection.

**23. `DecimalFormatSymbolsProvider` có tự override mọi NumberFormat không?** — Không; các locale services khác có hợp đồng provider riêng.

**24. CLDR data có thể đổi khi nâng JDK không?** — Có; cần test lại phù hợp version.

**25. Có nên dùng COMPAT/JRE trên JDK 26 không?** — Không, legacy sources đó đã bị loại bỏ.

**26. Bài lab đạt bao nhiêu checks?** — **33/33 PASS trên mỗi trong hai JVM**, tổng 66 checks thực thi.

## 23. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD, canonical vs compatibility, isNormalized.
- [Oracle Java SE 26 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): getAvailableLocales, isSupportedLocale, classpath/module packaging, SPI/CLDR/HOST order, startup caching và JDK CLDR version.
- [Oracle Java SE 26 — DecimalFormatSymbolsProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/DecimalFormatSymbolsProvider.html): getInstance(Locale), supported locales và exception contract.
- [Oracle Java SE 26 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormatSymbols.html): locale factory, decimal/grouping symbols, installed provider visibility.
- [Oracle Java SE 26 — DecimalFormat](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html): formatting/parsing, pattern, symbol overrides, concurrency.
- [Oracle Java SE 26 — Collator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Collator.html): canonical decomposition và strength/locale rules.
- [Oracle Java SE 26 — BreakIterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/BreakIterator.html): character/word/sentence boundaries.
- [Oracle Java SE 26 — Locale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): BCP 47, extensions, default FORMAT/DISPLAY locales.
- [Oracle Java SE 26 — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): discovery qua META-INF/services hoặc module provides.
- [Oracle Java SE 26 — Internationalization Overview](https://docs.oracle.com/en/java/javase/26/intl/internationalization-overview.html): CLDR default, SPI/HOST và java.locale.providers.
- [Oracle — JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): các nguồn locale data hiện hành, COMPAT/JRE removed và Collator/BreakIterator data caveat.
- [Oracle Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): kiểm chứng API nguồn tương thích Java17.
- [Oracle Java SE 17 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): service provider contract trên Java17.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/): Unicode Normalization Forms và canonical equivalence.

**Ghi nhớ:** **NFC** giải quyết các biến thể mã hóa Unicode **tương đương canonical** của tiếng Việt; **bỏ dấu, mapping đ/Đ và làm lowercase** là một chính sách **tạo search key có mất thông tin**, phải tách khỏi dữ liệu gốc. `Collator`/`BreakIterator` giải quyết collation/segmentation, **không thay Normalizer**. Locale Provider SPI là cơ chế chọn nguồn dữ liệu cho một **locale service cụ thể**: triển khai service descriptor đúng, kiểm thử **discovered / direct call / factory selected** riêng, và dùng **hai JVM mới** cho `SPI,CLDR` so với `CLDR,SPI`. Bản lab Java17+ đã thực thi **33/33 PASS mỗi JVM** mà không dùng API lỗi thời.
