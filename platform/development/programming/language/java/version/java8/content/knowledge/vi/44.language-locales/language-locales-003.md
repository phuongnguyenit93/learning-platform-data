# Locale — Matching theo tập ngôn ngữ hoặc một ngôn ngữ phù hợp nhất (Java 8+)

**Chủ đề cha:** Ngôn ngữ và locale. **Đề bài:** Phân biệt hai cơ chế *language matching* của `java.util.Locale` trong Java 8+: **filtering** để tìm **tập tất cả locale/language tag phù hợp**, và **lookup** để tìm **một locale/language tag phù hợp nhất** theo danh sách ưu tiên của người dùng. Nắm `Locale.LanguageRange`, trọng số `q`, `Locale.filter`, `filterTags`, `lookup`, `lookupTag`, `Locale.FilteringMode`, wildcard `*`, language tag BCP 47 và quy tắc RFC 4647. Biết khi nào cần fallback của ứng dụng, vì "phù hợp nhất theo RFC 4647" không phải là thuật toán đo khoảng cách ngôn ngữ hoặc fallback resource bundle.

**Phiên bản:** Các phương thức locale matching và `Locale.LanguageRange` có từ **Java 8**; tất cả vẫn được hỗ trợ trong Java hiện hành. Ví dụ hoàn chỉnh dùng **JDK 17+**, không cần thư viện bên ngoài. Chỉ trình bày API và kiến thức vẫn áp dụng, không sử dụng kỹ thuật bản địa hóa cũ đã lỗi thời.

> **Nhớ nhanh:** `Locale.filter(priorityList, availableLocales)` trả **List<Locale>**, `Locale.filterTags(priorityList, availableTags)` trả **List<String>**. Chúng có thể trả **nhiều lựa chọn** hoặc danh sách rỗng. `Locale.lookup(priorityList, availableLocales)` trả **một Locale hoặc null**, `Locale.lookupTag(priorityList, availableTags)` trả **một String hoặc null**. Filtering và lookup **không hoán đổi cho nhau**: một yêu cầu `en` có thể lọc ra cả `en-US` và `en-GB`, trong khi lookup chỉ có các tag đó có thể trả `null` nếu **không có tag đúng `en`** trong tập cung cấp.

## 1. Khi ứng dụng cần "matching" ngôn ngữ?

Giả sử dịch vụ có bản dịch giao diện cho các language tags:

```text
vi-VN, vi, en-US, en-GB, fr-FR, ja-JP
```

Người dùng hoặc browser gửi thứ tự mong muốn:

```text
fr-CA, en-GB;q=0.9, vi;q=0.8, en;q=0.5
```

Ứng dụng có thể hỏi một trong hai điều khác nhau:

1. **"Tất cả bản dịch nào phù hợp với các sở thích?"** Ví dụ cho người dùng chọn trong danh sách, đưa nhiều kết quả cho bộ chọn ngôn ngữ, xây danh sách các lựa chọn khả dụng. Đó là **filtering**.
2. **"Chọn đúng một bản dịch tốt nhất để trả response?"** Ví dụ quyết định ngôn ngữ của một thông báo hoặc tài liệu. Đó là **lookup**, có thể cần fallback nghiệp vụ nếu Java trả null.

Trong ví dụ này, kết quả thực tế của Java là:
- `filter`: `en-GB`, `vi-VN`, `vi`, `en-US`.
- `lookup`: `en-GB`.

Vì sao không có `fr-FR`? Preference `fr-CA` **không** tự đồng nghĩa `fr-FR`. Nếu sản phẩm muốn "French vùng bất kỳ" thì client cần cung cấp range `fr` hoặc ứng dụng cần thêm **policy fallback** rõ ràng. Đừng ngầm biến lựa chọn vùng quốc gia thành cùng một locale chỉ vì hai locale có phần ngôn ngữ `fr`.

### 1.1. Bốn danh từ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Language tag** | Chuỗi định danh ngôn ngữ theo BCP 47 | `vi-VN`, `zh-Hant-TW` |
| **Locale** | Đối tượng Java gồm language, script, region, variant/extensions… | `Locale.forLanguageTag("vi-VN")` |
| **Language range** | Mẫu ưu tiên do user đưa ra để so khớp một hoặc nhiều tags | `vi`, `en-US`, `zh-*-TW`, `*` |
| **Language Priority List** | Danh sách các `Locale.LanguageRange` đã sắp theo mức ưu tiên/trọng số | `Locale.LanguageRange.parse("vi,en;q=0.5")` |

**Language range không phải lúc nào là language tag hợp lệ để tạo locale cụ thể.** Range `*` hoặc `zh-*-TW` là mẫu so khớp, không đại diện cho một bản dịch thật. Không đưa chúng vào `Locale.forLanguageTag` rồi nghĩ có sẵn một locale ứng dụng có thể hiển thị.

### 1.2. Chuẩn liên quan

- **BCP 47 / RFC 5646:** Ngữ pháp, thành phần language/script/region/variant/extension của language tag.
- **RFC 4647:** Các cơ chế matching language tags: *filtering* và *lookup*.
- **HTTP Accept-Language:** Một nguồn cung cấp danh sách ưu tiên từ browser, thường có trọng số `q`. Cần xem xét chính sách HTTP thực tế và giới hạn input bên ngoài thay vì tin mọi chuỗi từ client đều hợp lệ.

Java `Locale` cung cấp công cụ matching theo RFC 4647. Nó **không** tự bảo đảm ứng dụng có resource file, dịch đúng nội dung, hợp lệ hóa policy pháp lý hoặc chọn bản dịch "gần nhất về mặt văn hóa".

## 2. `Locale.LanguageRange`: Biểu diễn sở thích người dùng

Một range có:
- `getRange()`: tên range chuẩn hóa để matching, ví dụ `en-us`, `vi`, `*`.
- `getWeight()`: trọng số `double` trong khoảng **0.0..1.0**.
- `MAX_WEIGHT` là `1.0`; `MIN_WEIGHT` là `0.0`.
- `new Locale.LanguageRange(range)`: tạo range với trọng số mặc định.
- `new Locale.LanguageRange(range, weight)`: tạo range có trọng số.
- `Locale.LanguageRange.parse(String)`: phân tích danh sách phân cách bằng dấu phẩy, sắp xếp ưu tiên.

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse(
                "vi-VN,en-US;q=0.8,en;q=0.5");
```

Đây là đoạn **trong phương thức**, import `java.util.List` và `java.util.Locale`.

Trong chuỗi có trọng số:
- Không ghi `q` → trọng số mặc định `1.0`.
- `q=0.8` ưu tiên thấp hơn `q=1.0`.
- `q=0.0` nói rằng ngôn ngữ đó **không được chấp nhận** trong matching.
- `q` ngoài khoảng hoặc một range sai cú pháp có thể làm `parse` ném `IllegalArgumentException`; `null` gây `NullPointerException`.

### 2.1. Danh sách được sắp theo trọng số, không chỉ theo vị trí trong header

Ví dụ:

```text
en-US;q=0.4, vi-VN, fr;q=0.7
```

Thứ tự xử lý là:
1. `vi-VN` — weight `1.0`.
2. `fr` — weight `0.7`.
3. `en-US` — weight `0.4`.

`Locale.LanguageRange.parse` sắp danh sách theo ưu tiên từ cao xuống thấp. Không đọc `ranges.get(0)` rồi kết luận đó chắc chắn là ngôn ngữ tốt nhất **được server hỗ trợ**; nó chỉ là **preference range** đầu tiên, có thể không match một tag nào.

### 2.2. Tại sao không tự parse bằng split(",") và split(";q=")?

Tách chuỗi thủ công rất dễ bỏ sót:
- Khoảng trắng trong list.
- Trọng số không hợp lệ hoặc ngoài [0,1].
- Range trùng lặp.
- Trọng số mặc định.
- Case-insensitive matching.
- Các language range tương đương theo IANA Language Subtag Registry.
- Extended language range có dấu `*` trong từng subtag.

`LanguageRange.parse` xử lý cú pháp theo hợp đồng Java và có thể tự bổ sung những range tương đương đã biết từ registry. Nhưng nó **chỉ kiểm tra cú pháp range**, không thay thế việc kiểm tra IANA registry, giới hạn input/HTTP header, authorization hay toàn bộ business rules.

### 2.3. Tập ưu tiên có thể nhiều phần tử hơn số range nhập

Javadoc lưu ý parser có thể bổ sung equivalent language ranges dựa trên dữ liệu registry. Một số mã ngôn ngữ/địa lý có alias hoặc dạng preferred mới. Vì vậy không nên luôn assert:

```java
ranges.size() == header.split(",").length
```

Đây là **phản ví dụ** nếu muốn khẳng định số lượng: parser có thể thêm equivalents. Nếu nghiệp vụ cần lưu "client đã gửi chính xác bao nhiêu range", lưu input/hình thức parse riêng có giới hạn, không suy từ số phần tử sau khi parser mở rộng.

Các mã cũ như `iw` liên quan tiếng Hebrew có thể được Java ánh xạ/tạo equivalent `he`; đây là **giải thích khả năng tương thích**, không phải lời khuyên dùng mã cũ cho dữ liệu mới. Luôn ưu tiên language tags hiện hành khi cấu hình tài nguyên.

## 3. Filtering: Trả một tập các locale phù hợp

Hai API tương ứng:

```java
List<Locale> matches =
        Locale.filter(priorityList, availableLocales);

List<String> tagMatches =
        Locale.filterTags(priorityList, availableTags);
```

Đây là **chữ ký sử dụng trong phương thức**; các biến `priorityList`, `availableLocales`, `availableTags` phải đã được khai báo với kiểu phù hợp.

Đặc điểm:
1. Trả **một danh sách** — có thể gồm nhiều phần tử, một phần tử hoặc rỗng.
2. Kết quả **sắp theo ưu tiên/trọng số** trong priority list.
3. Chỉ trả những locale/tags **được đưa vào tập cung cấp**; Java không tự tạo bản dịch mới.
4. Matching **không phân biệt chữ hoa/thường** của language tags.
5. Các kết quả matching trùng lặp được loại bỏ theo hợp đồng; `filterTags` bảo toàn cách viết hoa/thường của tag được chọn từ tập nguồn.
6. Nếu có nhiều lựa chọn trong cùng mức ưu tiên, **thứ tự collection input có thể ảnh hưởng cách xuất hiện**; dùng `List` có thứ tự thay vì `HashSet` khi output/UX đòi kết quả xác định.
7. Nếu không có match, trả **danh sách rỗng** — không trả null cho toàn danh sách.

### 3.1. Basic filtering hiểu range `en` như thế nào?

Với language range `en` và các tag:

```text
en-US
en-GB
fr-FR
```

`Locale.filterTags(parse("en"), tags)` trả:

```text
[en-US, en-GB]
```

Trong **basic filtering**, `en` là một tiền tố ngôn ngữ ở **ranh giới subtag**. Nó có thể match tag đầy đủ `en`, `en-US`, `en-GB`, `en-Latn-US`… nhưng không match chữ `eng` chỉ vì cả hai bắt đầu bằng hai ký tự "en". So khớp có cấu trúc dấu `-`, không chỉ là `String.startsWith` tùy tiện.

### 3.2. Lọc không phải "tất cả locale có cùng ngôn ngữ" theo ngữ nghĩa tổng quát

Range `fr-CA` không basic-filter-match `fr-FR` hay `fr` vì nó chỉ định cụ thể vùng CA. Nếu muốn rộng hơn, bổ sung `fr` trong priority list; nếu muốn fallback theo bản đồ vùng/script riêng của ứng dụng, hãy cấu hình rõ.

Một range `zh-Hant` có thể lọc `zh-Hant-TW` và `zh-Hant-HK`, nhưng không tự hiểu rằng `zh-CN` có cùng writing system, vì script khác hoặc tag không mô tả cùng thông tin. Script/region là dữ liệu xác định locale, không phải chuỗi tùy tiện cắt bỏ mà không xét yêu cầu.

### 3.3. Filtering là danh sách ứng viên, chưa chắc là thứ tự UX mong muốn

Ứng dụng có thể muốn hiển thị tên bản địa `Locale.getDisplayName(locale)`, sắp xếp theo tên, nhóm theo region, hoặc đặt ngôn ngữ người dùng ở đầu. Danh sách filtering theo **priority list** là dữ liệu matching. Nếu muốn sắp xếp lại để hiển thị, hãy giữ riêng:
- Thứ tự **ưu tiên để lựa chọn**.
- Thứ tự **hiển thị UX**.

Không sort matches theo alphabet rồi vô tình lấy phần tử đầu làm ngôn ngữ "ưu tiên nhất" sau khi đã thay đổi thứ tự từ bộ lọc.

## 4. Java 17+ runnable: Filtering theo priority list

Tạo file **`LocaleFilteringDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class LocaleFilteringDemo {
    public static void main(String[] args) {
        List<Locale> available = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("vi"),
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("ja-JP"));

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(
                        "fr-CA, en-GB;q=0.9, vi;q=0.8, en;q=0.5");

        List<Locale> matches =
                Locale.filter(preferences, available);

        List<String> tags = available.stream()
                .map(Locale::toLanguageTag)
                .toList();

        System.out.println("Offered: " + tags);
        System.out.println("Filtered: "
                + matches.stream()
                        .map(Locale::toLanguageTag)
                        .toList());
        System.out.println("Filtered tags: "
                + Locale.filterTags(preferences, tags));

        Locale best = Locale.lookup(preferences, available);
        System.out.println("Lookup: "
                + (best == null
                        ? "<no match>"
                        : best.toLanguageTag()));

        String bestTag =
                Locale.lookupTag(preferences, tags);
        System.out.println("Lookup tag: " + bestTag);
    }
}
```

Chạy:

```bash
javac --release 17 LocaleFilteringDemo.java
java LocaleFilteringDemo
```

**Stdout:**

```text
Offered: [vi-VN, vi, en-US, en-GB, fr-FR, ja-JP]
Filtered: [en-GB, vi-VN, vi, en-US]
Filtered tags: [en-GB, vi-VN, vi, en-US]
Lookup: en-GB
Lookup tag: en-GB
```

**Giải thích:**

1. `fr-CA` có weight 1.0 nhưng không match `fr-FR` do region khác; không ép ngôn ngữ Pháp mặc định sang Pháp-Pháp.
2. `en-GB` có weight 0.9 và match chính xác, nên xuất hiện đầu và được lookup chọn.
3. `vi` có weight 0.8, basic-filter-match cả `vi-VN` và `vi`, giữ thứ tự trong tập input.
4. `en` weight 0.5 match `en-US`; `en-GB` đã được trả từ range ưu tiên hơn nên không lặp.
5. `ja-JP` không match range nào, bị loại.
6. `filterTags` trả các **String tag** thay vì `Locale`; cả hai biểu diễn matching tương đương trong ví dụ vì các tag được sinh từ chính Locale.
7. Không cần gọi `Locale.setDefault`; thuật toán dùng danh sách supported tường minh.

`Stream.toList()` trong ví dụ được bổ sung từ Java 16, phù hợp với JDK 17+. Khi viết code chạy **Java 8 chính xác**, thay `.toList()` bằng `.collect(Collectors.toList())` và `List.of(...)` bằng `Arrays.asList(...)`.

## 5. Lookup: Chỉ một lựa chọn "best match" theo RFC 4647

API:

```java
Locale bestLocale =
        Locale.lookup(priorityList, availableLocales);

String bestTag =
        Locale.lookupTag(priorityList, availableTags);
```

Khác với filtering:
- Trả **một** kết quả hoặc `null` nếu không có match.
- Dựa trên **priority/weight** của các range.
- Tìm theo nguyên tắc **lookup từ cụ thể đến ít cụ thể hơn**.
- Mỗi bước cắt bớt phần cuối của range khi không có tag khớp, theo quy tắc của RFC 4647.
- Wildcard toàn phần `*` **bị bỏ qua** trong lookup.
- Nó không phải thuật toán ngôn ngữ học để đo "khoảng cách" giữa các vùng hay scripts.

### 5.1. Quy tắc cắt range từng bước

Ví dụ preference `zh-Hant-TW`:

```text
zh-Hant-TW  ->  zh-Hant  ->  zh
```

Java thử các mức từ cụ thể tới tổng quát hơn theo thuật toán lookup. Nếu available có tag `zh-Hant`, kết quả có thể là `zh-Hant`; nếu chỉ có `zh-Hant-TW` thì chọn tag đó. Nếu chỉ có `zh-Hant-HK`, **không** tự nhảy từ `zh-Hant-TW` sang `zh-Hant-HK` chỉ vì chung script; lookup sẽ tìm tag chính xác theo các bước cắt đã được định nghĩa.

Ví dụ `fr-CA`:
- Thử `fr-CA`.
- Nếu không có, thử `fr`.
- Không tự thử `fr-FR`.

Vì vậy, với offered chỉ có `fr-FR`, kết quả lookup cho `fr-CA` có thể **null**. Với offered `fr` và `fr-FR`, lookup có thể trả `fr` vì đó là tag cụ thể được tìm thấy ở bước rút gọn.

### 5.2. Lookup không tương đương basic filtering

Tình huống:

```text
Preference range: en
Offered tags:     en-US, en-GB, fr-FR

Filtering -> [en-US, en-GB]
Lookup    -> null
```

Vì basic filtering hiểu `en` là tiền tố chấp nhận những tag dài hơn; lookup muốn tìm tag `en` trong tập available khi range đã là `en`, không tự thêm vùng US/GB. Đây là khác biệt trọng tâm của bài.

**Đừng viết `Locale.lookup(parse("en"), supported)` rồi kỳ vọng `en-US` được chọn nếu server chỉ lưu resource `en-US`.** Khi muốn một lựa chọn đầu tiên trong tập phù hợp theo **filtering**, gọi `Locale.filterTags(...).get(0)` **sau khi kiểm tra không rỗng**; nhưng đó là **policy khác lookup** và nên được đặt tên rõ.

### 5.3. Lookup không thay thế quyết định fallback

Nếu không có match:
- `Locale.lookup` trả **null**.
- `Locale.lookupTag` trả **null**.

Ứng dụng phải định nghĩa fallback, ví dụ `en-US` khi chỉ có bộ resources tiếng Anh và tiếng Việt, hoặc locale đã được người dùng thiết lập trong profile. Không nên mặc định dùng `Locale.getDefault()` khi yêu cầu response được phục vụ bởi server đa ngôn ngữ, vì default của JVM có thể phụ thuộc môi trường hoặc cấu hình process.

## 6. Java 17+ runnable: Khác biệt giữa filter và lookup

Tạo file **`LocaleLookupDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class LocaleLookupDemo {
    public static void main(String[] args) {
        List<String> english =
                List.of("en-US", "en-GB", "fr-FR");

        List<Locale.LanguageRange> en =
                Locale.LanguageRange.parse("en");

        System.out.println("Filter en: "
                + Locale.filterTags(en, english));
        System.out.println("Lookup en: "
                + Locale.lookupTag(en, english));

        List<Locale.LanguageRange> frenchCanada =
                Locale.LanguageRange.parse("fr-CA");

        System.out.println("Lookup fr-CA with fr-FR: "
                + Locale.lookupTag(
                        frenchCanada, List.of("fr-FR")));
        System.out.println("Filter fr with fr-FR: "
                + Locale.filterTags(
                        Locale.LanguageRange.parse("fr"),
                        List.of("fr-FR")));
        System.out.println("Lookup fr-CA with fr: "
                + Locale.lookupTag(
                        frenchCanada,
                        List.of("fr", "fr-FR")));

        List<Locale.LanguageRange> chinese =
                Locale.LanguageRange.parse("zh-Hant-TW");

        System.out.println("Lookup zh-Hant-TW: "
                + Locale.lookupTag(
                        chinese,
                        List.of("zh-Hant", "zh", "en-US")));

        System.out.println("Wildcard filter: "
                + Locale.filterTags(
                        Locale.LanguageRange.parse("*"),
                        List.of("en-US", "vi-VN")));
        System.out.println("Wildcard lookup: "
                + Locale.lookupTag(
                        Locale.LanguageRange.parse("*"),
                        List.of("en-US", "vi-VN")));
    }
}
```

Chạy:

```bash
javac --release 17 LocaleLookupDemo.java
java LocaleLookupDemo
```

**Stdout:**

```text
Filter en: [en-US, en-GB]
Lookup en: null
Lookup fr-CA with fr-FR: null
Filter fr with fr-FR: [fr-FR]
Lookup fr-CA with fr: fr
Lookup zh-Hant-TW: zh-Hant
Wildcard filter: [en-US, vi-VN]
Wildcard lookup: null
```

**Đọc output:**

- `lookup en: null` không phải lỗi Java, mà là đúng hợp đồng lookup khi offered không chứa tag `en`.
- `lookup fr-CA with fr-FR: null` cho thấy **không có fallback vùng tự động**.
- `lookup fr-CA with fr: fr` vì range có thể rút gọn thành `fr`.
- `lookup zh-Hant-TW: zh-Hant` vì offered chứa tag `zh-Hant`, một bước rút gọn phù hợp.
- Wildcard `*` có thể match mọi tag ở filtering, nhưng bị bỏ qua trong lookup, nên **null**.
- Thứ tự offered ở ví dụ được cố định bằng `List.of` để kết quả filtering không phụ thuộc thứ tự duyệt một `Set`.

## 7. Trọng số `q`, danh sách ưu tiên và cách các tag được sắp

Trọng số cho biết mức người dùng chấp nhận/ưu tiên:
- `q=1.0`: mức cao nhất; mặc định khi không ghi q.
- `q=0.7`: mức thấp hơn.
- `q=0.0`: **không chấp nhận** range đó.
- Các range cùng trọng số có thể cần quy tắc thứ tự đầu vào; không tự dựng thuật toán "tự nhiên" trên tên tag.

### 7.1. Kết quả theo trọng số

Header:

```text
en-US;q=0.4, vi-VN, fr;q=0.7
```

Server hỗ trợ:

```text
fr-FR, vi-VN, en-US, ja-JP
```

Kết quả:
- Priority list được sắp thành `vi-VN` (1.0), `fr` (0.7), `en-US` (0.4).
- Filtering: `[vi-VN, fr-FR, en-US]`.
- Lookup: `vi-VN`.

### 7.2. `q=0` không được cấp quyền chỉ vì là một match cú pháp

Một header:

```text
fr-CA;q=0, en-US;q=0.8
```

cho biết `fr-CA` không được chấp nhận. Java matching trong trường hợp này chọn `en-US` nếu supported có nó.

Khi header còn chứa wildcard, một tag thuộc range cấm cụ thể không nên lọt vào qua wildcard ở cơ chế matching của Java. Ví dụ đã được kiểm chứng:

```text
en;q=0, *;q=0.5
```

Với offered `en-US`, `en-GB`, `fr-FR`, `Locale.filterTags` chỉ trả `[fr-FR]`.

**Lưu ý chính sách fallback:** Nếu ứng dụng tự fallback về `en-US` sau khi `filter/lookup` trả không có match, ứng dụng có thể đã **bỏ qua lời từ chối q=0** của client. Fallback là quyết định của sản phẩm/protocol, không phải bảo đảm Java sẽ tự đảm bảo chấp nhận của người dùng sau khi bạn tự chọn giá trị ngoài thuật toán. Với phản hồi HTTP có đàm phán nội dung, hãy xác định rõ chính sách trường hợp không tìm được representation chấp nhận được.

### 7.3. Parse có thể tự bổ sung equivalents

Một language range có thể được parser mở rộng thành nhiều range tương đương. Do đó không hard-code số lượng/tên phần tử parse cho mọi alias trên tất cả phiên bản dữ liệu IANA, trừ khi ví dụ chọn những tag không có alias phát sinh hoặc test đã gắn với JDK cụ thể.

Ứng dụng không nên tự reorder priority list theo thứ tự chữ cái sau khi parse, vì việc này sẽ phá trọng số mà user gửi.

## 8. Java 17+ runnable: Parse, trọng số và q=0

Tạo file **`WeightedLanguageMatchingDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class WeightedLanguageMatchingDemo {
    public static void main(String[] args) {
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(
                        "en-US;q=0.4, vi-VN, fr;q=0.7");

        System.out.println("Priorities:");
        for (Locale.LanguageRange range : preferences) {
            System.out.println("  " + range.getRange()
                    + " = " + range.getWeight());
        }

        List<String> offered = List.of(
                "fr-FR", "vi-VN", "en-US", "ja-JP");

        System.out.println("Filter weighted: "
                + Locale.filterTags(preferences, offered));
        System.out.println("Lookup weighted: "
                + Locale.lookupTag(preferences, offered));

        List<Locale.LanguageRange> excludes =
                Locale.LanguageRange.parse(
                        "fr-CA;q=0, en-US;q=0.8");

        System.out.println("q=0 filter: "
                + Locale.filterTags(
                        excludes, List.of("fr-CA", "en-US")));
        System.out.println("q=0 lookup: "
                + Locale.lookupTag(
                        excludes, List.of("fr-CA", "en-US")));

        List<Locale.LanguageRange> header =
                Locale.LanguageRange.parse(
                        "Accept-Language: vi-VN, en;q=0.5");

        System.out.println("Header filter: "
                + Locale.filterTags(
                        header,
                        List.of("en-GB", "vi-VN", "en-US")));
    }
}
```

Chạy:

```bash
javac --release 17 WeightedLanguageMatchingDemo.java
java WeightedLanguageMatchingDemo
```

**Stdout:**

```text
Priorities:
  vi-vn = 1.0
  fr = 0.7
  en-us = 0.4
Filter weighted: [vi-VN, fr-FR, en-US]
Lookup weighted: vi-VN
q=0 filter: [en-US]
q=0 lookup: en-US
Header filter: [vi-VN, en-GB, en-US]
```

**Lưu ý:** `LanguageRange.parse` chấp nhận cả dạng danh sách `"vi-VN,en;q=0.5"` và dạng có tiền tố `"Accept-Language: ..."` theo Javadoc. Nếu framework HTTP đã cung cấp riêng giá trị header (không gồm tên header), truyền giá trị đó; không tự ghép chuỗi hoặc parse nhiều lần khi không cần.

## 9. Wildcard và extended language ranges

Có hai dạng range cơ bản:

1. **Basic language range:** ví dụ `vi`, `en-US`, `fr-CA` hoặc wildcard toàn phần `*`.
2. **Extended language range:** có dấu `*` ở vị trí subtag, ví dụ `zh-*-TW`, `es-*` hoặc `*-CH`.

Extended range cho phép matching linh hoạt hơn một tiền tố đơn giản. Ví dụ `zh-*-TW` có thể match `zh-Hant-TW`, dù có subtag `Hant` ở giữa.

**Đừng hiểu `*` như biểu thức chính quy bất kỳ** hay SQL `LIKE`. Đây là cú pháp range theo RFC 4647, có những điều kiện về vị trí subtag, thứ tự và matching; khi cần behavior chính xác, dùng API và bộ test thay vì tự xây regex.

### 9.1. `Locale.FilteringMode`

Các lựa chọn chính:

| Mode | Tác động |
| --- | --- |
| `AUTOSELECT_FILTERING` | Mặc định; Java tự chọn basic hoặc extended filtering tùy danh sách range |
| `EXTENDED_FILTERING` | Áp dụng cơ chế extended filtering |
| `IGNORE_EXTENDED_RANGES` | Bỏ qua extended ranges; dùng các basic ranges còn lại |
| `MAP_EXTENDED_RANGES` | Chuyển extended range sang dạng basic theo quy tắc mapping của JDK/RFC trước khi filtering |
| `REJECT_EXTENDED_RANGES` | Ném `IllegalArgumentException` khi gặp extended range |

Nếu overload `Locale.filter`/`filterTags` **không** nhận `FilteringMode`, hành vi tương đương `AUTOSELECT_FILTERING`.

### 9.2. Đừng tự đồng nhất `IGNORE` và `MAP`

Một extended range có thể bị:
- Bỏ hoàn toàn khi dùng `IGNORE_EXTENDED_RANGES`.
- Chuyển thành mẫu basic khác khi dùng `MAP_EXTENDED_RANGES`.

Hai cách có thể tình cờ cho cùng kết quả trên **một tập tags**, nhưng không có nghĩa semantics giống nhau. Khi ứng dụng muốn reject những mẫu wildcard không hỗ trợ, chọn `REJECT_EXTENDED_RANGES` rồi xử lý exception ở ranh giới nhận input, thay vì lặng lẽ làm mất ý thích của người dùng.

### 9.3. Tại sao extended filtering có thể khác basic filtering?

Với `zh-*-TW` và offered `zh-Hant-TW`, wildcard có thể cho phép subtag `Hant` ở giữa. Một basic range không có cấu trúc đó không diễn đạt cùng ý nghĩa. Không tự chuyển tất cả extended ranges thành `zh`; việc này có thể mở rộng tập match sang tài nguyên Simplified Chinese không phù hợp cho preference Traditional Chinese.

## 10. Java 17+ runnable: So sánh các FilteringMode

Tạo file **`ExtendedLanguageRangeDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class ExtendedLanguageRangeDemo {
    public static void main(String[] args) {
        List<String> offered = List.of(
                "zh-Hans-CN",
                "zh-Hant-TW",
                "zh-Hant-HK",
                "zh-CN",
                "en-US",
                "en-GB",
                "de-CH",
                "fr-FR");

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(
                        "zh-*-TW, en;q=0.5");

        System.out.println("AUTO: "
                + Locale.filterTags(preferences, offered));
        System.out.println("EXTENDED: "
                + Locale.filterTags(
                        preferences,
                        offered,
                        Locale.FilteringMode.EXTENDED_FILTERING));
        System.out.println("IGNORE: "
                + Locale.filterTags(
                        preferences,
                        offered,
                        Locale.FilteringMode.IGNORE_EXTENDED_RANGES));
        System.out.println("MAP: "
                + Locale.filterTags(
                        preferences,
                        offered,
                        Locale.FilteringMode.MAP_EXTENDED_RANGES));

        try {
            Locale.filterTags(
                    preferences,
                    offered,
                    Locale.FilteringMode.REJECT_EXTENDED_RANGES);
            System.out.println("REJECT: no exception");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "REJECT: IllegalArgumentException");
        }
    }
}
```

Chạy:

```bash
javac --release 17 ExtendedLanguageRangeDemo.java
java ExtendedLanguageRangeDemo
```

**Stdout:**

```text
AUTO: [zh-Hant-TW, en-US, en-GB]
EXTENDED: [zh-Hant-TW, en-US, en-GB]
IGNORE: [en-US, en-GB]
MAP: [en-US, en-GB]
REJECT: IllegalArgumentException
```

**Diễn giải:**

- `AUTO` chọn extended filtering vì có range `zh-*-TW`, nên match `zh-Hant-TW`.
- `EXTENDED` cho cùng kết quả trong ví dụ này.
- `IGNORE` bỏ qua preference mở rộng, chỉ còn `en` có trọng số 0.5.
- `MAP` chuyển dạng range; với **tập offered cụ thể** ở demo này, kết quả cũng chỉ là English.
- `REJECT` từ chối extended range bằng exception có kiểm soát; không lén nhận một language tag không hợp lệ.
- Không suy ra rằng `MAP` và `IGNORE` **luôn tương đương** từ một lần kiểm thử.

## 11. Chọn giữa `Locale.filter` và `filterTags`

Hai API có semantics matching tương tự nhưng kiểu đầu vào/đầu ra khác nhau:

| Mục tiêu | API |
| --- | --- |
| Có sẵn các đối tượng `Locale` trong ứng dụng | `Locale.filter(List<LanguageRange>, Collection<Locale>)` |
| Có các chuỗi BCP 47 dùng làm key của resource, file, database | `Locale.filterTags(List<LanguageRange>, Collection<String>)` |
| Chọn duy nhất một `Locale` | `Locale.lookup(...)` |
| Chọn duy nhất một key/tag trong danh sách nguồn | `Locale.lookupTag(...)` |

### 11.1. Vì sao phải giữ tag gốc?

Nếu các tài nguyên ứng dụng được lập chỉ mục theo String `"en-GB"`, việc chuyển qua `Locale.forLanguageTag` rồi `toLanguageTag` có thể canonicalize khác cách viết/alias. `filterTags` trả **một trong các chuỗi tag được cung cấp**, bảo toàn case theo Javadoc, giúp dùng trực tiếp như key của resource khi bộ tag đã hợp lệ.

Nếu ứng dụng muốn chuẩn hóa tags trước khi lưu, hãy canonicalize **có chủ đích tại lúc ingest** và giữ mapping sang resource ID chính xác. Không tùy tiện biến `en-GB` thành `en-gb` rồi lấy làm tên tệp khi file system của hệ thống có phân biệt hoa/thường.

### 11.2. Phân biệt case-insensitive matching và so sánh String

`Locale.filterTags` match ngôn ngữ **không phân biệt case**. Nhưng Java `String.equals` là **case-sensitive**. `"en-us".equals("EN-US")` trả false, còn matching theo RFC 4647 coi hai tag cùng ngữ nghĩa phân loại. Nếu tài nguyên lưu key theo nguyên bản, không dùng so sánh String thủ công để thay thế thuật toán matching.

Javadoc của `filterTags` cũng cho biết nếu tập offered có tag trùng nhau chỉ khác chữ hoa/thường, kết quả giữ **bản được gặp đầu tiên**. Nếu offered là một `HashSet` không có thứ tự duyệt ổn định, dạng casing được trả về có thể thay đổi. Dùng `List` có thứ tự hoặc chuẩn hóa có policy rõ.

### 11.3. Không nên dùng `Locale.getAvailableLocales()` như tập bản dịch thực tế

`Locale.getAvailableLocales()` trả các locale mà runtime/provider hỗ trợ cho **locale-sensitive operations** của Java. Nó **không** có nghĩa service của bạn có file dịch, nội dung pháp lý hay email template cho tất cả những locale đó.

Danh sách `availableLocales` cung cấp cho matching nên được suy ra từ **những tài nguyên thật sự được triển khai**. Nếu dùng list từ JDK, `Locale.lookup` có thể trả một locale mà ứng dụng không hề có bản dịch.

## 12. Chọn best tag thực tế cho ứng dụng web

Giả sử một web app chỉ có ba bộ resources:

```text
en-US
fr-FR
vi-VN
```

Ứng dụng muốn chọn **một tài nguyên cụ thể** cho response. Có hai chính sách khác nhau:

- **Strict RFC lookup:** ưu tiên match chính xác theo các bước rút gọn range; `Locale.lookupTag` có thể trả null, kể cả filtering tìm được một tag cùng ngôn ngữ.
- **Filter-first policy:** lọc toàn bộ tags và lấy phần tử đầu nếu có match; cho phép range rộng `vi` match `vi-VN`. Đây là policy ứng dụng xây trên `Locale.filterTags`, **không được gọi nhầm là RFC lookup**.

Nếu ứng dụng muốn `fr-CA` có thể dùng tài nguyên `fr-FR`, nên quy định rõ một fallback range `fr` (trong preferences hoặc policy phía server). Không biến mọi locale French thành interchangeable nếu biến thể ngôn ngữ/thuật ngữ pháp lý giữa vùng là vấn đề.

### 12.1. Java 17+: Hàm chọn locale với fallback cố định

Tạo file **`LanguageNegotiationDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class LanguageNegotiationDemo {
    static String chooseUsingFilter(
            String acceptLanguage,
            List<String> offered,
            String fallback) {

        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return fallback;
        }

        try {
            List<Locale.LanguageRange> preferences =
                    Locale.LanguageRange.parse(acceptLanguage);

            List<String> matches =
                    Locale.filterTags(preferences, offered);

            return matches.isEmpty()
                    ? fallback
                    : matches.get(0);
        } catch (IllegalArgumentException ex) {
            // Policy demo: invalid header -> configured fallback.
            return fallback;
        }
    }

    public static void main(String[] args) {
        List<String> offered =
                List.of("en-US", "fr-FR", "vi-VN");
        String fallback = "en-US";

        System.out.println("French regional fallback: "
                + chooseUsingFilter(
                        "fr-CA, fr;q=0.8, en-US;q=0.5",
                        offered, fallback));

        System.out.println("No French generic: "
                + chooseUsingFilter(
                        "fr-CA, en-US;q=0.5",
                        offered, fallback));

        System.out.println("Vietnamese: "
                + chooseUsingFilter(
                        "vi;q=1.0,en;q=0.3",
                        offered, fallback));

        System.out.println("No match: "
                + chooseUsingFilter(
                        "de-DE",
                        offered, fallback));

        System.out.println("Invalid header: "
                + chooseUsingFilter(
                        "en;q=1.5",
                        offered, fallback));

        System.out.println("Wildcard: "
                + chooseUsingFilter(
                        "*",
                        offered, fallback));
    }
}
```

Chạy:

```bash
javac --release 17 LanguageNegotiationDemo.java
java LanguageNegotiationDemo
```

**Stdout:**

```text
French regional fallback: fr-FR
No French generic: en-US
Vietnamese: vi-VN
No match: en-US
Invalid header: en-US
Wildcard: en-US
```

**Điểm cần hiểu:**

1. `fr-CA,fr;q=0.8` có range `fr` đủ rộng để filter-match `fr-FR`. Điều này là kết quả của **range bổ sung `fr`**, không phải suy luận vùng tự động.
2. `fr-CA,en-US;q=0.5` không match French resource, nhưng match `en-US`, nên chọn English.
3. `vi` match `vi-VN` khi filtering.
4. Nếu không có match, ứng dụng sử dụng fallback đã cấu hình và nằm trong tập offered.
5. Header lỗi `q=1.5` dẫn đến `IllegalArgumentException`, được xử lý thành fallback theo **policy minh họa**.
6. Với wildcard `*`, mọi offered đều là ứng viên; phần tử đầu `en-US` được chọn.
7. Code xử lý một request, không dùng state global `Locale.setDefault`. Nhưng trong hệ thống thật, cần thêm **giới hạn kích thước header, logging/metrics an toàn, chính sách q=0 và HTTP error status**; code demo không phải một bộ HTTP content negotiation hoàn chỉnh.

### 12.2. Khi nào cần HTTP 406 hoặc fallback khác?

Nếu client chỉ chấp nhận các ngôn ngữ ứng dụng không có, dùng `en-US` mặc định có thể phù hợp với một trang web phổ thông nhưng không phù hợp với một API cam kết tuân thủ Accept-Language nghiêm ngặt. Tùy thiết kế HTTP content negotiation, server có thể trả **406 Not Acceptable**, hoặc vẫn trả response với một ngôn ngữ mặc định đã nêu rõ, và gắn `Content-Language`.

Đây là **quyết định sản phẩm/API**, không phải việc `Locale.filterTags` tự đảm nhiệm. Nếu một tag bị loại bởi `q=0` mà server vẫn fallback về chính tag đó, hãy coi đó là tình huống cần giải quyết policy rõ, không gọi là matching thành công.

### 12.3. Cache theo Accept-Language

Nếu cùng URL có thể trả các bản dịch khác nhau dựa vào `Accept-Language`, HTTP caches cần biết lựa chọn representation phụ thuộc header nào. `Vary: Accept-Language` thường phù hợp; nếu dùng CDN cache key riêng hoặc user profile language, policy caching phải được thiết kế tương thích. Không trộn response tiếng Việt của user A với response tiếng Anh của user B vì chỉ cache theo URL.

## 13. Không có khoảng cách ngôn ngữ ngầm định

Đây là giới hạn quan trọng của đề bài "**ngôn ngữ phù hợp nhất**":

`Locale.lookup` chọn "best match" **theo RFC 4647**, không phải:
- Khoảng cách ngôn ngữ theo CLDR likely subtags.
- Tự map Chinese Traditional giữa các quốc gia.
- Tự chọn "fr-FR" vì "fr-CA" cùng ngôn ngữ.
- Dịch máy từ một ngôn ngữ sang ngôn ngữ khác.
- Quyết định chính sách fallback quốc gia của ứng dụng.
- Xác minh user hiểu ngôn ngữ đó.
- Chọn resource thật tồn tại trong database/template system.

Khi sản phẩm thực sự cần **best-fit theo ngữ nghĩa bản địa hóa**, phải thiết kế thuật toán hoặc sử dụng thư viện/locale data có contract rõ (và kiểm thử các script, region, variant). Không nói rằng Java filter/lookup là lỗi vì nó không chọn locale "gần nhất" bằng cách mà sản phẩm mong muốn: thuật toán RFC được thiết kế khác.

### 13.1. Với Chinese, script đặc biệt quan trọng

`zh-Hans` và `zh-Hant` là hai script conventions khác nhau. Một người dùng yêu cầu `zh-Hant-TW` có thể chấp nhận `zh-Hant`, nhưng hệ thống không nên tự fallback sang `zh-Hans-CN` chỉ vì language code chung là `zh`.

Nếu cần fallback business từ `zh-Hant-TW` → `zh-Hant` → `zh` → app default, hãy **định nghĩa danh sách tài nguyên thực tế** và điều kiện cho từng bước. RFC lookup hỗ trợ cách rút gọn range, nhưng không cho phép mọi sự mở rộng ngược từ `zh` sang bất kỳ tag region nào.

### 13.2. Với English, "en" và "en-US" khác nhau

Một resource key `en` có thể là bản dịch trung tính; `en-US` có thể mang quy tắc chính tả/ngày tháng của Mỹ; `en-GB` có thể khác. `Locale.lookup(parse("en"), List.of("en-US","en-GB"))` trả null, như đã minh họa, vì không có `en`. Lúc đó ứng dụng có thể:
- Thêm một resource "en" trung tính.
- Dùng filter-first policy với thứ tự offered có kiểm soát.
- Khai báo fallback mặc định, ví dụ `en-US`.
- Sử dụng thư viện best-fit với quy tắc/CLDR được kiểm chứng.

Chọn cách nào tùy yêu cầu sản phẩm; không coi thứ tự tình cờ của `HashSet` là business priority.

## 14. Locale matching, ResourceBundle và Locale mặc định là các tầng khác nhau

`ResourceBundle.getBundle(baseName, locale)` có cơ chế tìm resource bundle theo danh sách ứng viên và fallback riêng. Nó **không tương đương** `Locale.lookup` và không đảm bảo hoạt động giống RFC 4647.

Quy trình rõ ràng hơn:

```text
Accept-Language / user profile preferences
        |
        | LanguageRange.parse + filter/lookup + app policy
        v
Một locale hoặc resource key có trong danh sách supported
        |
        | Nạp tài nguyên đã triển khai
        v
ResourceBundle / template / database content
        |
        | Format theo locale đã chọn
        v
Response (Content-Language / cache policy rõ)
```

### 14.1. Đừng tự động coi JVM default là người dùng hiện tại

`Locale.getDefault()` thể hiện cấu hình locale mặc định của **process/JVM**, không phải preference của từng HTTP request. Gọi `Locale.setDefault(locale)` trong request handler là nguy hiểm vì thay đổi state **toàn ứng dụng**, có thể ảnh hưởng các request đang chạy khác hoặc code thư viện.

Dùng biến locale được **truyền tường minh** đến formatter, resource loader, message template, không để logic request thay đổi default toàn cục.

### 14.2. Matching không đảm bảo formatter đúng ngôn ngữ

Một locale được chọn để dịch text không nhất thiết đồng nghĩa cách định dạng số/ngày giờ của user cũng phải theo đúng tag resource đó. Ví dụ một người nói tiếng Anh tại Việt Nam có thể muốn giao diện tiếng Anh nhưng định dạng ngày/tiền tệ theo Việt Nam. Nên tách:
- **Content language preference**.
- **Regional formatting locale**.
- **Timezone**.
- **Currency/business region**.

Các trường này có thể liên quan nhưng không đồng nhất. `Locale.lookup` chỉ xử lý matching language tags, không quyết định timezone, currency hoặc luật thuế.

### 14.3. Kênh xác định preference

Khi chọn language của một người dùng đăng nhập, một hệ thống thường ưu tiên:
1. Lựa chọn thủ công của user hoặc profile (nếu có).
2. Preference của request (`Accept-Language`).
3. Fallback được sản phẩm cấu hình.

Đây là **một policy gợi ý**, không phải yêu cầu cố định của Java. Một số hệ thống cần tôn trọng header hơn profile trong ngữ cảnh phát nội dung, hoặc hỗ trợ quyền chọn khác theo từng tài liệu.

## 15. API BCP 47 và việc tạo Locale

Để tạo `Locale` từ một tag:

```java
Locale locale = Locale.forLanguageTag("zh-Hant-TW");

System.out.println(locale.getLanguage()); // zh
System.out.println(locale.getScript());   // Hant
System.out.println(locale.getCountry());  // TW
System.out.println(locale.toLanguageTag()); // zh-Hant-TW
```

Đây là **đoạn trong phương thức**, sử dụng BCP 47 language tag.

### 15.1. `Locale.forLanguageTag` không phải validator nghiêm ngặt cho đầu vào xấu

`Locale.forLanguageTag` có xử lý những tag không well-formed theo contract, và không nhất thiết ném exception cho mọi lỗi cú pháp; có thể bỏ qua phần không parse được. Nếu cần **fail fast** khi ingest resource key, cân nhắc `new Locale.Builder().setLanguageTag(tag).build()` và xử lý `IllformedLocaleException` theo API tương ứng.

Tuy nhiên một tag **đúng cú pháp** chưa chắc đã có resource của ứng dụng, chưa chắc là preference hợp lệ của domain, và chưa chắc được IANA gán ở thời điểm hiện tại. Vẫn nên kiểm tra allowlist của các resource đã triển khai.

### 15.2. Tag input và output có thể thay đổi case/canonicalization

`Locale.toLanguageTag()` có thể xuất tag đã chuẩn hóa với language lowercase, script title-case và country uppercase. Không sử dụng kết quả `Locale.toString()` (thường dạng dấu gạch dưới/Java locale representation) làm bản thay thế cho BCP 47 language tag trong HTTP.

Ví dụ:
- BCP 47 language tag: `en-US`.
- Cách chuỗi Java locale truyền thống có thể là `en_US`.

Trong quy trình matching, dùng `toLanguageTag()` cho bộ `Locale` hoặc `filterTags/lookupTag` trên strings BCP 47 đã chuẩn hóa. Không dùng `String.startsWith("en_")` để mô phỏng matching chuẩn.

## 16. Quy tắc chọn thứ tự và tính xác định

Một vài yếu tố ảnh hưởng kết quả:

### 16.1. Trọng số khác nhau

Range weight cao hơn được xử lý trước. `Locale.LanguageRange.parse` đã tổ chức priority list theo quy tắc của mình. Không thêm một `sort(Comparator.comparing(LanguageRange::getRange))` vì nó có thể đảo sở thích user.

### 16.2. Một range match nhiều offered tags

Filtering trả tất cả offered tags match trong cùng range; cách duyệt collection offered có thể ảnh hưởng thứ tự. Với lookup có pattern chứa wildcard subtag và nhiều match, Javadoc chỉ rõ tag được gặp đầu tiên qua iterator của collection có thể được chọn. Vì vậy sử dụng **List có thứ tự ổn định** khi thứ tự trong nhóm là quyết định sản phẩm.

### 16.3. Trùng case và canonicalization

`filterTags` không phân biệt case khi matching, nhưng trả cách viết của tag theo offered collection. Nếu nhiều String biểu thị cùng tag chỉ khác case, bản được gặp đầu tiên có thể được giữ. Chuẩn hóa tag trước khi đưa vào danh sách supported giúp tránh output không nhất quán.

### 16.4. Không mặc định source Set có thứ tự

Một `HashSet<String>` có thể có thứ tự duyệt thay đổi giữa triển khai/tình huống. Không viết unit test khẳng định `Locale.lookupTag` luôn trả cùng lựa chọn khi có nhiều tag match ngang nhau nhưng offered được tạo từ HashSet không định thứ tự.

### 16.5. Duplicate priority ranges

`LanguageRange.parse` nêu nếu một range xuất hiện lặp trong input, chỉ lần đầu được đưa vào priority list; các equivalent ranges có thể được bổ sung. Không dùng danh sách lặp để "cộng trọng số" cho cùng một ngôn ngữ.

## 17. Thiết kế một hàm matching dễ kiểm thử

Một kiến trúc nhỏ có thể tách ba trách nhiệm:

**Bước 1 – Nhận và xác thực input.** Giới hạn kích thước header và số range mà sản phẩm chấp nhận; xử lý null/trống; dùng `LanguageRange.parse`, bắt exception hợp lệ; không mặc định header có thể được tin tưởng.

**Bước 2 – Matching bằng Java.** Dựa vào yêu cầu:
- Muốn danh sách các lựa chọn được chấp nhận → `filter`/`filterTags`.
- Muốn lựa chọn một tag theo RFC 4647 → `lookup`/`lookupTag`.
- Muốn một lựa chọn theo filter-first policy → `filterTags` rồi lấy đầu nếu có.

**Bước 3 – Policy fallback/representation.** Nếu không có match, thực hiện quy định sản phẩm/HTTP về fallback, lỗi, Content-Language, resource key và caching. Đây không phải một bước trong API Java matching.

### 17.1. Đảm bảo resource thực sự tồn tại

Dùng danh sách offered được xây từ bộ resource đã được deploy; chỉ chọn giá trị nằm trong đó. Trước khi truy cập file template:
- Dùng **map từ tag sang resource ID nội bộ**.
- Không tự nối raw Accept-Language vào path file.
- Không dùng range có wildcard làm tên file.
- Không trả về tag mà không có nội dung, chỉ vì `Locale.getAvailableLocales()` có nó.

### 17.2. Giới hạn input và log

Header có thể do client tùy ý gửi; parse một chuỗi quá dài hoặc có hàng nghìn range tiêu tốn CPU/bộ nhớ. Ứng dụng nên giới hạn request/header size theo gateway/framework, có thể giới hạn số lượng ranges và không ghi raw user header vào log không kiểm soát. Khi lỗi parse, log lý do đủ để quan sát nhưng tránh đưa toàn bộ input dài/nhạy cảm vào error response.

### 17.3. Caching

Nếu tập offered cố định, có thể giữ một danh sách immutable đã canonicalize. Không cần tạo lại tất cả `Locale` ở mỗi request. Nếu cache kết quả matching theo header, hãy cân nhắc giới hạn kích thước cache và tránh tạo một key mới cho mọi biến thể header tùy ý. Header negotiation thường có cardinality cao, nên memoization không giới hạn dễ gây memory growth.

### 17.4. Version dữ liệu IANA/Unicode/JDK

`LanguageRange.parse` có thể dùng dữ liệu equivalents theo registry do JDK cung cấp. Khác phiên bản JDK có thể khác dữ liệu alias/canonicalization, dù API cùng hợp đồng. Khi ứng dụng cần output cực kỳ ổn định, viết test cho những tags thuộc domain được hỗ trợ và chủ động pin runtime/data version trong môi trường production.

## 18. Các trường hợp biên phải kiểm thử

| Tình huống | Kết quả/điều cần kiểm tra |
| --- | --- |
| Priority list `en`, offered `en-US,en-GB` | `filterTags` trả hai, `lookupTag` có thể null |
| Priority list `fr-CA`, offered chỉ `fr-FR` | Không tự match chéo region |
| Preference `fr-CA`, offered `fr` | Lookup có thể rút gọn và chọn `fr` |
| Priority list `zh-Hant-TW`, offered `zh-Hant` | Lookup chọn `zh-Hant` |
| Range `*` trong filtering | Match các tags được cung cấp |
| Chỉ có range `*` trong lookup | `null` vì wildcard bị bỏ qua |
| `q=1` và `q=0.5` | Range q cao được ưu tiên |
| `q=0` | Ngôn ngữ bị từ chối không được đưa vào kết quả matching |
| `q` vượt [0,1] | `LanguageRange.parse` có thể ném `IllegalArgumentException` |
| Header null | API parse không chấp nhận null; caller xử lý |
| Offered rỗng | Filter list rỗng, lookup null |
| Không có language tag match | Filter rỗng, lookup null |
| Hai offered tags khác case | Matching case-insensitive; kiểm soát dạng output |
| Input offered không có thứ tự | Kết quả tie có thể phụ thuộc iteration |
| Có extended range `zh-*-TW` | AUTO/EXTENDED có thể match; REJECT ném exception |
| Chọn mode IGNORE | Extended ranges bị bỏ qua |
| Chọn mode MAP | Extended ranges được chuyển theo quy tắc, không tương đương IGNORE |
| Repeated priority range | Parser có thể gộp duplicate |
| Equivalence/alias | Parser có thể thêm ranges, không hard-code size |
| Truyền Locale thay cho String | Dùng `filter/lookup`, map kết quả bằng `toLanguageTag` |
| Server thiếu bundle dịch | Matching không tự tạo resource |
| User request thay đổi JVM default | Không dùng `setDefault` để phục vụ từng request |
| HTTP q=0 nhưng fallback vẫn chọn tag bị cấm | Lỗi **policy fallback**, không phải match thành công |
| Script Traditional/Simplified | Không map tùy tiện giữa `zh-Hant` và `zh-Hans` |
| Cache response khác ngôn ngữ | Xem xét `Vary: Accept-Language` và cache key |
| Dùng `Locale.forLanguageTag` để validate input | Không đủ nghiêm ngặt cho mọi malformed tag |

## 19. Java 17+: Bộ kiểm thử hợp đồng filtering và lookup

Tạo file **`LocaleMatchingChecks.java`**. Chương trình có hàm `check` chủ động ném `AssertionError`, không cần cờ `-ea`.

```java
import java.util.List;
import java.util.Locale;

public class LocaleMatchingChecks {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> english =
                List.of("en-US", "en-GB", "fr-FR");
        List<Locale.LanguageRange> en =
                Locale.LanguageRange.parse("en");

        check(Locale.filterTags(en, english)
                .equals(List.of("en-US", "en-GB")),
                "basic filtering");
        check(Locale.lookupTag(en, english) == null,
                "lookup must not extend en to en-US");
        System.out.println("Filter vs lookup: PASS");

        List<Locale.LanguageRange> region =
                Locale.LanguageRange.parse("fr-CA");

        check(Locale.lookupTag(
                region, List.of("fr-FR")) == null,
                "cross-region lookup");
        check("fr".equals(Locale.lookupTag(
                region, List.of("fr", "fr-FR"))),
                "lookup truncation");
        System.out.println("Regional truncation: PASS");

        List<Locale.LanguageRange> weighted =
                Locale.LanguageRange.parse(
                        "en-US;q=0.4, vi-VN, fr;q=0.7");

        List<String> offered =
                List.of("fr-FR", "vi-VN", "en-US");
        check(Locale.filterTags(weighted, offered)
                .equals(List.of("vi-VN", "fr-FR", "en-US")),
                "priority ordering");
        check("vi-VN".equals(Locale.lookupTag(
                weighted, offered)), "weighted lookup");
        System.out.println("Weighted priorities: PASS");

        List<Locale.LanguageRange> wild =
                Locale.LanguageRange.parse("*");
        check(Locale.filterTags(wild,
                        List.of("en-US", "vi-VN"))
                .equals(List.of("en-US", "vi-VN")),
                "wildcard filtering");
        check(Locale.lookupTag(
                wild, List.of("en-US", "vi-VN")) == null,
                "wildcard lookup");
        System.out.println("Wildcard: PASS");

        List<Locale.LanguageRange> extended =
                Locale.LanguageRange.parse(
                        "zh-*-TW, en;q=0.5");
        List<String> zh = List.of(
                "zh-Hans-CN", "zh-Hant-TW", "en-US");

        check(Locale.filterTags(extended, zh)
                .equals(List.of("zh-Hant-TW", "en-US")),
                "extended filtering");
        check(Locale.filterTags(
                        extended, zh,
                        Locale.FilteringMode.IGNORE_EXTENDED_RANGES)
                .equals(List.of("en-US")),
                "ignore extended");
        System.out.println("Extended ranges: PASS");

        List<Locale.LanguageRange> qZero =
                Locale.LanguageRange.parse(
                        "fr-CA;q=0,en-US;q=0.8");
        check(Locale.filterTags(
                        qZero, List.of("fr-CA", "en-US"))
                .equals(List.of("en-US")),
                "q=0 exclusion");
        System.out.println("q=0: PASS");

        boolean rejected = false;
        try {
            Locale.LanguageRange.parse("en-US;q=1.4");
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        check(rejected, "bad weight accepted");
        System.out.println("Input validation: PASS");

        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 LocaleMatchingChecks.java
java LocaleMatchingChecks
```

**Stdout:**

```text
Filter vs lookup: PASS
Regional truncation: PASS
Weighted priorities: PASS
Wildcard: PASS
Extended ranges: PASS
q=0: PASS
Input validation: PASS
All checks: PASS
```

**Tại sao bài test đáng tin:** Các case dựa vào list có thứ tự rõ, không dùng `HashSet` để quyết định tie; các language ranges đơn giản tránh phụ thuộc alias hiếm; q=0 và invalid weight được kiểm tra bằng điều kiện cụ thể; không assert tên thread, default Locale của JVM hoặc số locale mà runtime cung cấp.

## 20. Những lỗi phổ biến cần tránh

1. **Dùng `Locale.filter` khi chỉ muốn một kết quả nhưng quên xử lý danh sách có nhiều phần tử:** filter trả List.
2. **Dùng `Locale.lookup` khi cần tất cả lựa chọn:** lookup trả một Locale hoặc null.
3. **Nhầm `filterTags` trả Locale:** nó trả `List<String>`.
4. **Nhầm `lookupTag` trả list:** nó trả `String` hoặc null.
5. **Nghĩ `lookup(parse("en"), [en-US,en-GB])` phải chọn US:** lookup không mở rộng range `en` thành các tag dài hơn.
6. **Nghĩ `filter(parse("fr-CA"), [fr-FR])` sẽ match cùng ngôn ngữ:** region khác không được tự coi tương đương.
7. **Tưởng lookup và filtering luôn trả phần tử giống nhau:** chúng có tiêu chí khác nhau.
8. **Không kiểm tra `null` từ lookup:** có thể gây NPE khi gọi `toLanguageTag`.
9. **Lấy `matches.get(0)` trên kết quả lọc rỗng:** sẽ ném `IndexOutOfBoundsException`.
10. **Chọn fallback từ một ngôn ngữ không tồn tại trong offered:** response có thể không có resource.
11. **Dùng `Locale.getDefault()` làm preference của từng request:** default thuộc JVM/process.
12. **Gọi `Locale.setDefault` trong xử lý HTTP:** ảnh hưởng request khác.
13. **Dùng `Locale.getAvailableLocales` như danh sách file dịch:** runtime hỗ trợ định dạng không đồng nghĩa service có nội dung.
14. **Bỏ qua trọng số `q`:** thứ tự xuất hiện trong chuỗi không luôn bằng thứ tự ưu tiên.
15. **Bỏ qua `q=0` hoặc fallback vào tag đã bị từ chối:** vi phạm preference của client nếu policy yêu cầu tuân thủ.
16. **Parse thủ công bằng `split(",")` rồi viết prefix match:** dễ sai wildcard, equivalent ranges và weight.
17. **Giả định `LanguageRange.parse` chỉ trả đúng số range xuất hiện trong input:** parser có thể thêm equivalent ranges.
18. **Cho rằng `Locale.forLanguageTag` luôn ném lỗi khi tag không hợp lệ:** không đủ cho strict validation.
19. **Dùng `Locale.toString()` như BCP 47 language tag:** dạng Java underscore có thể khác.
20. **Tin `String.startsWith("en")` tương đương RFC 4647 basic filter:** không tuân ranh giới subtag.
21. **Đổi mọi extended ranges thành tag ngôn ngữ gốc:** có thể làm mất phân biệt script/region.
22. **Nhầm `FilteringMode.IGNORE` và `MAP` là một:** chúng có contract khác.
23. **Chọn `REJECT_EXTENDED_RANGES` nhưng không xử lý exception:** header hợp lệ ở dạng extended có thể làm ứng dụng trả lỗi ngoài dự định.
24. **Tin wildcard `*` cũng tạo kết quả lookup:** trong lookup `*` bị bỏ qua.
25. **Đưa wildcard range qua `Locale.forLanguageTag` và dùng làm resource key:** wildcard không phải locale cụ thể.
26. **Dùng HashSet rồi kỳ vọng thứ tự tie cố định:** iteration order không được bảo đảm.
27. **Sort alphabet các ranges sau parse rồi chọn match đầu:** làm mất ý nghĩa ưu tiên.
28. **Nhầm best match RFC với best-fit ngôn ngữ học:** không có cơ chế tính linguistic distance.
29. **Gộp resource locale với timezone/currency của user:** đó là các preference khác nhau.
30. **Cho rằng matching tự tải resource:** cần kết nối với ResourceBundle/templates thực tế.
31. **Không giới hạn độ dài/header count từ client:** có thể gây lãng phí CPU/memory.
32. **Dùng giá trị Accept-Language thô làm tên file:** không an toàn và không thuộc API matching.
33. **Cache nội dung dịch chỉ theo URL trong khi response phụ thuộc Accept-Language:** rủi ro trả nhầm ngôn ngữ.
34. **Không test script trong Chinese/Serbian hoặc region đặc thù:** fallback có thể sai sản phẩm.
35. **Viết test dựa vào toàn bộ output của parser alias trên mọi JDK:** dữ liệu registry có thể thay đổi.
36. **Khẳng định filter-first chính là RFC lookup:** lấy phần tử đầu của filtering là policy khác.
37. **Bắt mọi exception và trả một locale ngẫu nhiên:** nên định nghĩa fallback và xử lý input errors rõ.
38. **Giả định việc match không phân biệt case đồng nghĩa resource key cũng không phân biệt case:** hệ thống lưu file có thể case-sensitive.
39. **Dùng list offered không được quản lý** và không biết resource đã deploy chưa: kết quả matching có thể không phục vụ được.
40. **Mặc định locale hiển thị và language resource luôn phải giống nhau:** UI language và regional formatting có thể tách biệt.

## 21. Checklist thiết kế API chọn ngôn ngữ

- [ ] Tôi cần **danh sách ứng viên** hay **một best match**?
- [ ] Nếu cần danh sách, dùng `filter`/`filterTags` và xử lý kết quả rỗng?
- [ ] Nếu cần một match theo RFC, dùng `lookup`/`lookupTag` và xử lý `null`?
- [ ] Có phân biệt **filter-first policy** với **RFC lookup** không?
- [ ] Danh sách offered có **chỉ những resource đã triển khai** và thứ tự ổn định?
- [ ] Header/range được parse bằng `Locale.LanguageRange.parse` và kiểm soát input errors?
- [ ] Có hiểu parse sắp theo weight và có thể thêm equivalent ranges?
- [ ] Có bảo toàn `q=0` và phân biệt wildcard filter/lookup?
- [ ] Nếu dùng extended ranges, đã chọn `FilteringMode` rõ?
- [ ] Các vùng/script như `fr-CA` và `fr-FR` có fallback được sản phẩm xác nhận?
- [ ] Có tránh dùng `Locale.forLanguageTag` như strict validator duy nhất?
- [ ] Dùng `toLanguageTag` thay `toString` khi làm việc với BCP 47?
- [ ] Không thay global `Locale.setDefault` cho từng HTTP request?
- [ ] Có tách UI language khỏi currency/format/timezone nếu yêu cầu?
- [ ] Khi fallback, có bảo đảm resource tồn tại và chính sách q=0/HTTP phù hợp?
- [ ] Nếu phục vụ HTTP content negotiation, đã xem xét `Content-Language` và `Vary: Accept-Language`?
- [ ] Có giới hạn input size và cache cardinality, không dùng raw header làm path?
- [ ] Unit test có cover rỗng/null, weighted, wildcard, extended, script/region, q=0, invalid header?
- [ ] Test có dùng offered `List` có thứ tự khi kết quả tie phải xác định?
- [ ] Có hiểu matching không tự kiểm tra ngôn ngữ tài nguyên dịch đã được viết và kiểm duyệt?

## 22. Câu hỏi ôn tập

1. Khi nào cần filtering thay vì lookup?
2. `Locale.filter` trả kiểu gì? `Locale.lookup` trả kiểu gì nếu không có match?
3. `Locale.filterTags` khác `filter` ở đầu vào/đầu ra thế nào?
4. `Locale.lookupTag` trả gì khi không tìm được?
5. Một range `en` có basic-filter-match `en-GB` không?
6. Range `en` có lookup-match `en-GB` nếu server không có tag `en` không?
7. Vì sao `fr-CA` không tự chọn `fr-FR` trong lookup?
8. `zh-Hant-TW` có thể rút gọn thành những range nào ở lookup?
9. `LanguageRange.getWeight` có miền giá trị gì? Không ghi `q` nghĩa là bao nhiêu?
10. Một range có `q=0` có được xem là chấp nhận trong matching không?
11. `LanguageRange.parse` có luôn giữ nguyên thứ tự chuỗi ban đầu khi có q khác nhau không?
12. Vì sao parse có thể trả thêm range không có nguyên văn trong input?
13. Wildcard `*` trong filtering và lookup khác nhau ra sao?
14. `zh-*-TW` là basic hay extended language range?
15. `AUTOSELECT_FILTERING` có ý nghĩa gì?
16. `REJECT_EXTENDED_RANGES` có thể gây exception nào?
17. `Locale.filterTags(parse("vi"),["vi-VN"])` và `lookupTag(...)` có thể trả gì?
18. Nếu không có match trong danh sách bản dịch đã triển khai, Java có tự dịch hoặc tự chọn default không?
19. Vì sao không dùng `Locale.setDefault` trong request handler đa luồng?
20. Vì sao `ResourceBundle` và `Locale.lookup` không đồng nghĩa?
21. Khi tài nguyên lưu theo tag `en-US`, nên dùng `Locale.toString` hay `toLanguageTag`?
22. Vì sao HashSet offered có thể tạo kết quả không ổn định khi tie?
23. Nếu client chỉ định `fr-CA` nhưng app chỉ có `fr-FR`, những lựa chọn policy nào hợp lệ?
24. Làm sao tránh cache trả nhầm ngôn ngữ cho cùng URL?
25. Nếu app cần best-fit theo linguistic distance và CLDR, chỉ `Locale.lookup` có đủ không?

**Gợi ý đáp án:** (1) Khi cần tập tất cả locale/tags phù hợp. (2) `List<Locale>`; `Locale` hoặc `null`. (3) `filterTags` dùng `String` BCP 47, `filter` dùng `Locale`. (4) `null`. (5) Có. (6) Không, nếu chỉ có tag `en-GB`. (7) Lookup cắt range về `fr`, không tự mở rộng sang vùng FR. (8) `zh-Hant-TW` → `zh-Hant` → `zh`. (9) 0..1; mặc định 1. (10) Không. (11) Không, có sắp theo priority/weight. (12) Có các equivalents từ IANA registry. (13) Filter match nhiều tags, lookup bỏ qua `*`. (14) Extended. (15) Chọn basic/extended filtering tùy ranges. (16) `IllegalArgumentException`. (17) Filter trả `[vi-VN]`, lookup có thể `null`. (18) Không; cần fallback của ứng dụng. (19) Default của JVM là global state. (20) ResourceBundle có thuật toán tài nguyên/fallback riêng. (21) `toLanguageTag`. (22) Không có iteration order cố định. (23) Thêm range `fr`, filter-first, mapping riêng hoặc fallback mặc định theo policy. (24) Cache key/Vary theo ngôn ngữ được chọn. (25) Không.

**Kết luận:** `Locale.filter`/`filterTags` và `Locale.lookup`/`lookupTag` giải quyết **hai bài toán khác nhau**: tìm **một tập phù hợp** hay chọn **một tag phù hợp nhất theo RFC 4647**. Nắm cách `LanguageRange` thể hiện thứ tự ưu tiên/trọng số, trường hợp `q=0`, wildcard, extended ranges và cơ chế rút gọn lookup giúp tránh lỗi "không chọn được en-US dù user yêu cầu en" hoặc "fr-CA không tự chọn fr-FR". Với ứng dụng thực tế, match trên **danh sách bản dịch có thật**, định nghĩa fallback có kiểm soát, giữ request locale tách khỏi JVM default, và phân biệt **matching RFC** với **best-fit ngôn ngữ học** hoặc fallback của `ResourceBundle`. Đây là kỹ thuật Java 8+ vẫn áp dụng trong phiên bản Java hiện hành.

## Tài liệu chính thức và tiêu chuẩn còn áp dụng

- `Locale` (Java SE 26) — locale matching, `filter`, `filterTags`, `lookup`, `lookupTag` và giải thích RFC 4647: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html
- `Locale.LanguageRange` (Java SE 26) — basic/extended ranges, parse, weight, equivalents và mapEquivalents: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.LanguageRange.html
- `Locale.FilteringMode` (Java SE 26) — AUTOSELECT/EXTENDED/IGNORE/MAP/REJECT: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.FilteringMode.html
- `Locale.Builder` (Java SE 26) — tạo locale và stricter validation qua setLanguageTag: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html
- `ResourceBundle` (Java SE 26) — tra cứu tài nguyên địa phương hóa với fallback riêng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html
- **RFC 4647** — Matching of Language Tags: https://www.rfc-editor.org/rfc/rfc4647
- **RFC 5646** — Tags for Identifying Languages: https://www.rfc-editor.org/rfc/rfc5646
- **HTTP Accept-Language** — ngữ nghĩa lựa chọn representation và quality weights theo HTTP hiện hành: https://www.rfc-editor.org/rfc/rfc9110
