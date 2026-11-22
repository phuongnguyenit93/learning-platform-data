# Locale.filter, filterTags, lookup và lookupTag trong Java

**`java.util.Locale`** cung cấp bốn phương thức matching ngôn ngữ rất hữu ích trong ứng dụng quốc tế hóa (*internationalization — i18n*): **`Locale.filter`, `Locale.filterTags`, `Locale.lookup` và `Locale.lookupTag`**. Chúng được bổ sung trong **Java 8**, triển khai cơ chế **lọc** (*filtering*) và **chọn ngôn ngữ phù hợp nhất** (*lookup*) theo **RFC 4647 Matching of Language Tags**. Đây vẫn là các API chính thức, còn áp dụng ở Java hiện đại.

Tình huống: phía người dùng muốn `fr-CA, en-US;q=0.8`, còn server cung cấp một tập locales giới hạn. Ta cần biết **những locale nào đáp ứng** để hiển thị danh sách, hoặc **chọn đúng một locale** để lấy nội dung. Nếu coi lọc và lookup là một, xử lý không tìm thấy sai, hoặc tự thực hiện so khớp String bằng `startsWith`, ứng dụng có thể ưu tiên nhầm ngôn ngữ, trả khác kết quả tiêu chuẩn hoặc vô tình dựa vào default locale của JVM.

Bài thuộc mục **Ngôn ngữ và locale**. Nội dung bao gồm: BCP 47 language tags; `Locale.LanguageRange` và danh sách ưu tiên có trọng số `q`; so sánh `filter`/`filterTags` với `lookup`/`lookupTag`; **basic vs extended filtering** và năm giá trị `Locale.FilteringMode`; phân biệt kết quả rỗng với `null`; ưu tiên, chữ hoa/thường, duplicate, aliases theo IANA; thiết kế fallback ứng dụng và xử lý `Accept-Language`. Có **sáu chương trình Java 17+ đầy đủ và output đã chạy trên OpenJDK 24**, cùng checklist review, kiểm thử và liên kết JavaDoc hiện hành. **Bốn phương thức matching và các enum/range cốt lõi cũng hoạt động trên Java 8**; những cú pháp Java mới hơn trong chương trình được ghi chú ở phần phiên bản.

## 1. Vấn đề: người dùng muốn một ngôn ngữ, ứng dụng hỗ trợ tập giới hạn

Giả sử server có các resource tương ứng:

```text
Supported:
  vi-VN
  en-US
  en-GB
  fr-FR

User preferences:
  fr-CA, en-GB;q=0.9, vi-VN;q=0.8
```

Nếu cần biết **tất cả ngôn ngữ có thể đáp ứng**, dùng `Locale.filter` hoặc `Locale.filterTags`. Kết quả có thể gồm nhiều phần tử.

Nếu cần **chọn đúng một locale cho trang hiện tại**, dùng `Locale.lookup` hoặc `Locale.lookupTag` rồi áp policy fallback khi kết quả `null`.

Với tập trên, **`fr-CA` không tự động được coi là trùng `fr-FR`**: khác vùng. `en-GB` được cung cấp và có thể là kết quả lookup. `vi-VN` còn là lựa chọn tiếp theo. Nếu không kết quả nào khớp, Java không mặc định chọn `Locale.getDefault()` cho bạn; ứng dụng phải chọn một fallback rõ.

**Ngôn ngữ được chọn không phải dịch tự động**. API chỉ giúp chọn locale/tag từ tập hỗ trợ, không sinh ra bản dịch, không đảm bảo resource tồn tại, và không áp dụng một thứ tự vùng “có vẻ gần” mà tiêu chuẩn không quy định.

## 2. BCP 47 language tag là gì?

**BCP 47** dùng chuỗi các *subtag* cách nhau bởi dấu **`-`**. Một số mẫu:

| Language tag | Ý nghĩa thông thường |
| --- | --- |
| `en` | Tiếng Anh, chưa chỉ rõ vùng |
| `en-US` | Tiếng Anh ở Hoa Kỳ |
| `en-GB` | Tiếng Anh ở Anh |
| `fr-CA` | Tiếng Pháp ở Canada |
| `fr-FR` | Tiếng Pháp ở Pháp |
| `zh-Hant-TW` | Tiếng Trung, chữ truyền thống, vùng Đài Loan |
| `zh-Hans-CN` | Tiếng Trung, chữ giản thể, vùng Trung Quốc |
| `sr-Latn-RS` | Tiếng Serbia, chữ Latin, vùng Serbia |
| `vi-VN` | Tiếng Việt ở Việt Nam |

Subtag đầu là mã **ngôn ngữ**; sau đó có thể có **script**, **region**, **variant** và **extensions**. Script, region và locale không đồng nghĩa nhau. `zh-Hant-TW` không chỉ là `zh-TW` được viết dài hơn: nó nói rõ hệ chữ viết.

Để tạo Java Locale từ tag chuẩn:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale traditional = Locale.forLanguageTag("zh-Hant-TW");

System.out.println(vietnamese.toLanguageTag());
System.out.println(traditional.toLanguageTag());
```

Đây là snippet trong phương thức có `import java.util.Locale;`. `Locale.forLanguageTag` và `toLanguageTag` có từ Java 7, dùng được trong Java 8+.

Cần phân biệt **Locale object** với **tag String**. `Locale.filter`/`lookup` làm việc với `Collection<Locale>`; `filterTags`/`lookupTag` làm việc với `Collection<String>`. Các phương thức matching dựa trên BCP 47, không dùng `Locale.toString()` (dạng underscore như `en_US`) để làm tag đầu vào.

## 3. Language Range khác Locale tag cụ thể

**Language range** là mẫu ưu tiên ngôn ngữ. Ví dụ:
- `en` là range cơ bản, có thể lọc ra `en`, `en-US`, `en-GB`.
- `en-US` là range cụ thể hơn; basic filtering khớp `en-US` và các phần mở rộng theo subtag boundary, không khớp `en-GB`.
- `de-*-DE` là **extended language range** với wildcard ở giữa.
- `*` là wildcard tổng quát; việc dùng trong **filter** và **lookup** khác nhau.

Một **language tag** như `en-US` mô tả một locale được hỗ trợ; một **range** `en` mô tả tập ứng viên phù hợp với preference đó khi filtering. Đừng coi dấu `*` là regex tùy ý: RFC 4647 có quy tắc riêng, không phải Java `Pattern`.

Trong Java, range được đại diện bằng:

```java
Locale.LanguageRange language = new Locale.LanguageRange("en");
Locale.LanguageRange weighted =
        new Locale.LanguageRange("fr-CA", 0.9);
```

Constructor kiểm tra cú pháp range và trọng số. Nó **không kiểm tra mọi subtag trong IANA registry** để chứng minh một ngôn ngữ thực sự có bản dịch.

## 4. Language Priority List và `q`

HTTP header `Accept-Language` thường diễn đạt ưu tiên như sau:

```http
Accept-Language: fr-CA, en-US;q=0.8, fr;q=0.4
```

Các range được sắp theo **trọng số `q`**:
- `fr-CA` mặc định `q=1.0`.
- `en-US` có `q=0.8`.
- `fr` có `q=0.4`.
- Giá trị `q` trong khoảng **0.0 tới 1.0**.
- `q=0` biểu đạt mức chấp nhận thấp nhất/loại khỏi lựa chọn trong semantics matching; không dùng nó làm một preference tích cực.
- Nếu nhiều range cùng trọng số, đừng tự giả định thuật toán match dựa trên một locale “gần gũi theo tự nhiên” chưa được chuẩn hóa.

API chính:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse(
                "fr-CA, en-US;q=0.8, fr;q=0.4");
```

Đây là snippet cần `import java.util.*;`, dùng được Java 8+. `parse` cho phép cả text có tiền tố `Accept-Language:` như trong HTTP lẫn danh sách range không có tiền tố. Nó thực hiện **syntactic check**, sắp theo priority/weight và có thể thêm **equivalent ranges** từ dữ liệu IANA; do đó số phần tử list **không bắt buộc bằng** số token trong chuỗi đầu vào.

Một điểm dễ sai: `Locale.LanguageRange.parse` trả `List<LanguageRange>` đã được xử lý; **không phải** `List<Locale>`. Truyền thẳng vào `Locale.filter`/`lookup` với tập các supported locales.

## 5. Bốn phương thức matching: bảng so sánh

| Phương thức | Tham số 2 | Kết quả | Khi không tìm thấy |
| --- | --- | --- | --- |
| `Locale.filter(priority, locales)` | `Collection<Locale>` | `List<Locale>` chứa mọi locale phù hợp, không trùng | **List rỗng** |
| `Locale.filterTags(priority, tags)` | `Collection<String>` | `List<String>` chứa mọi tag phù hợp, giữ cách viết tag được chọn | **List rỗng** |
| `Locale.lookup(priority, locales)` | `Collection<Locale>` | **Một `Locale`** được chọn theo lookup | **`null`** |
| `Locale.lookupTag(priority, tags)` | `Collection<String>` | **Một String** là tag được chọn | **`null`** |

Hai phương thức lọc còn có overload nhận `Locale.FilteringMode`. Hai phương thức lookup **không có overload FilteringMode** vì chúng thực hiện cơ chế lookup theo RFC 4647, không phải lọc theo các mode của `filter`.

Các method matching này đều là **static methods của `java.util.Locale`** (Java 8+). `filterTags` không trả Locale object; `lookup` không trả List.

Các tham số collection và preference list không được `null`; JavaDoc khai báo `NullPointerException` khi danh sách phù hợp bị null. Ứng dụng nên chủ động kiểm tra input của API thay vì dùng `null` như tín hiệu “người dùng không nhập header”.

## 6. Basic filtering: range khớp prefix theo **ranh giới subtag**

Basic filtering không phải `String.contains` hoặc `String.startsWith` tùy tiện. Một range `en` khớp:
- `en`;
- `en-US`;
- `en-GB`;
- `en-Latn-US` (nếu tag hợp lệ và được cung cấp).

Nhưng không khớp `fr-EN` hay một tag bắt đầu bằng chuỗi chữ cái gần giống mà không có subtag boundary. Các kết quả được trả theo ưu tiên/weight của ranges và collection input theo quy tắc matching.

Ví dụ:

```java
List<Locale.LanguageRange> preferred =
        Locale.LanguageRange.parse("fr;q=0.9,en;q=0.6");

List<String> offered = List.of(
        "en-US", "fr-CA", "fr-FR",
        "en-GB", "vi-VN");

List<String> matched = Locale.filterTags(
        preferred, offered);
```

Đây là **snippet Java 9+** vì dùng `List.of`; API Locale Java 8. Java 8 có thể thay bằng `Arrays.asList`. Kết quả logic: `fr-CA`, `fr-FR`, sau đó `en-US`, `en-GB`. `vi-VN` không nằm trong ưu tiên.

Kết quả `filterTags` là một list **mới, có thể sửa đổi**, không phải view gắn với danh sách input. Tuy vậy, sửa list kết quả **không** tự cập nhật supported locale config của server.

## 7. Chương trình 1 — `Locale.filter` và `filterTags`

Tạo tệp `BasicFilterDemo.java`:

```java
import java.util.*;
import java.util.stream.*;

public class BasicFilterDemo {
    static List<String> tags(List<Locale> locales) {
        return locales.stream()
                .map(Locale::toLanguageTag)
                .toList();
    }

    public static void main(String[] args) {
        List<String> offered = List.of(
                "en-US", "fr-CA", "fr-FR",
                "en-GB", "vi-VN", "FR-ca");

        List<Locale.LanguageRange> priority =
                Locale.LanguageRange.parse(
                        "fr;q=0.9,en;q=0.6");

        System.out.println(
                "tags=" +
                Locale.filterTags(priority, offered));

        List<Locale> locales = offered.stream()
                .map(Locale::forLanguageTag)
                .toList();

        System.out.println(
                "locales=" +
                tags(Locale.filter(priority, locales)));

        System.out.println(
                "fr-only=" +
                Locale.filterTags(
                        Locale.LanguageRange.parse("fr"),
                        offered));

        System.out.println(
                "no-match=" +
                Locale.filterTags(
                        Locale.LanguageRange.parse("ja"),
                        offered));
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac -encoding UTF-8 BasicFilterDemo.java
java BasicFilterDemo
```

Đầu ra đã kiểm thử:

```text
tags=[fr-CA, fr-FR, en-US, en-GB]
locales=[fr-CA, fr-FR, en-US, en-GB]
fr-only=[fr-CA, fr-FR]
no-match=[]
```

**Giải thích chi tiết**:
- Range `fr` có weight 0.9 nên các tag Pháp được xếp trước range `en` weight 0.6.
- `fr-CA` và `FR-ca` là trùng theo matching **không phân biệt chữ hoa/thường**; `filterTags` chỉ trả một kết quả (dạng xuất hiện đầu tiên là `fr-CA`).
- `filter` dùng `Locale.forLanguageTag` chuyển String sang Locale object rồi trả `List<Locale>`, nên `toLanguageTag` cho cách viết canonical `fr-CA`.
- Không có Nhật trong offered nên `no-match=[]`, không phải null.
- **Không dùng `toString` của Locale** để so sánh tags: `Locale.forLanguageTag("fr-CA").toString()` có thể là `fr_CA`; RFC language tags dùng dấu `-`.

**Phiên bản**: `List.of` (Java 9+) và `Stream.toList` (Java 16+); đây là ví dụ JDK 17+. Trên Java 8, chuyển `List.of` thành `Arrays.asList` và `stream.toList()` thành `stream.collect(Collectors.toList())`.

## 8. Tại sao `filterTags` khác `filter` dù có thể cùng kết quả?

Cả hai dùng cùng cơ chế lọc, nhưng có khác biệt kiểu và presentation.

**`filterTags`**:
- Nhận `Collection<String>` gồm language tags.
- Trả các **String** matched.
- Giữ **case gốc** của tag được chọn; matching không phân biệt hoa/thường.
- Nếu danh sách input chứa cùng tag nhưng khác case (`de-ch` và `de-CH`), chỉ giữ **một**; theo JavaDoc, lựa chọn đầu tiên trong iteration được giữ.
- Thuận tiện khi ứng dụng lưu catalog dưới dạng String keys, cache keys hoặc metadata BCP 47.

**`filter`**:
- Nhận `Collection<Locale>`.
- Trả `List<Locale>` với các locale không trùng nhau.
- Dùng khi API downstream (formatting, ResourceBundle, DateTimeFormatter, NumberFormat) cần Locale object.
- Không buộc client biến danh sách Locale thành tags thủ công chỉ để lọc.

Không coi `filterTags` là một cách “dịch” tag thành Locale. Nó giữ các tag String đã cung cấp. Nếu một tag String không hợp lệ, hành vi parsing/matching và việc downstream dùng nó có thể khác; nên validate catalog khi khởi tạo ứng dụng.

## 9. Lookup chọn **một ứng viên** theo RFC 4647

Trong khi filtering coi một range cơ bản như **prefix chấp nhận nhiều tags**, lookup coi range ưu tiên là **tag cụ thể nhất cần tìm**. Nó thử matching ở cấp hiện tại; nếu không có, **lần lượt cắt bớt subtag từ phải sang trái** theo quy tắc RFC 4647, rồi mới chuyển sang range ưu tiên kế tiếp.

Với priority:
```text
zh-Hant-TW, en-US;q=0.7
```

Thuật toán sẽ xét lần lượt theo cách hiểu:
```text
zh-Hant-TW
zh-Hant
zh
en-US
en
```

Nếu ứng dụng có `zh-Hant` nhưng không có `zh-Hant-TW`, lookup có thể trả `zh-Hant`. Nếu chỉ có `zh-Hans-CN` thì **không** được xem là tương đương `zh-Hant`; nó khác script, phải tiếp tục theo matching rules.

**Đặc điểm cực kỳ quan trọng**: với preference chỉ có `en` và candidates chỉ chứa `en-US`, Java `lookupTag` trả **`null`** trong thử nghiệm này; trong khi `filterTags` với range `en` trả `en-US`. Nói cách khác, **lookup không đơn giản là lấy phần tử đầu của filter result**.

Wildcard `*` đứng một mình được **bỏ qua trong lookup**, khác với filter có thể dùng nó để chọn mọi candidates. Đừng dùng `lookupTag(parse("*"), tags)` với kỳ vọng lấy tag đầu tiên.

## 10. Chương trình 2 — lookup và fallback từng subtag

Tạo `LookupDemo.java`:

```java
import java.util.*;

public class LookupDemo {
    public static void main(String[] args) {
        List<String> offered = List.of(
                "zh-Hant", "en-GB", "en", "fr-FR");

        List<Locale.LanguageRange> priority =
                Locale.LanguageRange.parse(
                        "zh-Hant-TW,en-US;q=0.7");

        System.out.println(
                "lookupTag fallback=" +
                Locale.lookupTag(priority, offered));

        List<Locale> locales = offered.stream()
                .map(Locale::forLanguageTag)
                .toList();

        Locale best = Locale.lookup(priority, locales);

        System.out.println(
                "lookup locale=" +
                (best == null
                        ? "null"
                        : best.toLanguageTag()));

        System.out.println(
                "second choice=" +
                Locale.lookupTag(
                        priority,
                        List.of("zh-Hans-CN", "en-US", "en-GB")));

        System.out.println(
                "wildcard lookup=" +
                Locale.lookupTag(
                        Locale.LanguageRange.parse("*"),
                        offered));

        System.out.println(
                "en-only lookup=" +
                Locale.lookupTag(
                        Locale.LanguageRange.parse("en"),
                        List.of("en-US")));

        System.out.println(
                "en-only filter=" +
                Locale.filterTags(
                        Locale.LanguageRange.parse("en"),
                        List.of("en-US")));
    }
}
```

```bash
javac -encoding UTF-8 LookupDemo.java
java LookupDemo
```

```text
lookupTag fallback=zh-Hant
lookup locale=zh-Hant
second choice=en-US
wildcard lookup=null
en-only lookup=null
en-only filter=[en-US]
```

Diễn giải:
- `zh-Hant-TW` không có, nhưng `zh-Hant` có → chọn `zh-Hant`.
- Nếu offered chỉ chứa `zh-Hans-CN` và các English variants, preference `zh-Hant-TW` không tìm thấy script thích hợp; preference tiếp theo `en-US` được chọn.
- `*` là wildcard có ý nghĩa ở filtering nhưng **không tạo best match** trong lookup.
- `en` khi lookup không tự trở thành `en-US`; ứng dụng cần **policy fallback riêng** nếu muốn chọn một locale vùng khi chỉ có preference ngôn ngữ.
- Đây là ví dụ cho thấy `Locale.filter(...).get(0)` và `Locale.lookup(...)` **không phải hai cách viết tương đương**.

## 11. `lookupTag` trả String, `lookup` trả Locale hoặc null

`Locale.lookup(priority, locales)`:
- Tham số 2 là `Collection<Locale>`.
- Kết quả là **`Locale`** hoặc **`null`** nếu không match.
- Không tự trả `Locale.getDefault()`; caller quyết định fallback.
- Không bảo đảm dựa trên tài nguyên dịch thực sự đã có (bạn phải truyền supported Locale đúng).

`Locale.lookupTag(priority, tags)`:
- Tham số 2 là `Collection<String>`.
- Kết quả là **String tag** được chọn, **giữ case gốc**.
- Trả **`null`** nếu không match.
- Nếu có nhiều tags tương đương theo matching, iteration order có thể ảnh hưởng lựa chọn; ưu tiên danh sách input có thứ tự ổn định.

Mẫu an toàn:

```java
Locale selected =
        Locale.lookup(priorities, supportedLocales);

if (selected == null) {
    selected = applicationFallback;
}
```

Đây là snippet trong method có `priorities`, `supportedLocales`, `applicationFallback` khai báo hợp lệ. Fallback nên là **một locale thực sự được ứng dụng hỗ trợ**; đừng dùng `Locale.getDefault()` vô điều kiện vì server timezone/region và ngôn ngữ máy deploy có thể khác trải nghiệm mong muốn.

Nếu `filter` trả List rỗng, dùng `isEmpty()`; **không** kiểm tra `filter(...) == null`. Nếu `lookup` trả null, kiểm tra rõ trước khi gọi `toLanguageTag()` hoặc `getLanguage()`.

## 12. FilteringMode có những lựa chọn nào?

`Locale.FilteringMode` (Java 8+) gồm **năm giá trị**:

| Mode | Hành vi |
| --- | --- |
| `AUTOSELECT_FILTERING` | Mặc định: nếu tất cả ranges là basic thì dùng basic; nếu có extended range thì chọn extended |
| `EXTENDED_FILTERING` | Áp **extended filtering** bất kể ranges ở dạng basic hay extended |
| `IGNORE_EXTENDED_RANGES` | Dùng basic filtering và **bỏ qua** extended ranges |
| `MAP_EXTENDED_RANGES` | Chuyển các extended ranges sang basic ranges trước khi lọc |
| `REJECT_EXTENDED_RANGES` | Ném `IllegalArgumentException` nếu priority list chứa extended range |

Mặc định:

```java
Locale.filterTags(priority, tags)
```

tương đương:

```java
Locale.filterTags(
        priority, tags,
        Locale.FilteringMode.AUTOSELECT_FILTERING)
```

Điều tương tự đúng với `Locale.filter`. Các mode **không** phải sort modes hay quy tắc chọn locale mặc định. Chúng thay đổi **kiểu thuật toán matching** đối với basic/extended language ranges.

**Chú ý**: `IGNORE_EXTENDED_RANGES` không trả null khi không còn range khớp; `filterTags` vẫn trả **List rỗng**. `REJECT_EXTENDED_RANGES` trả exception thay vì “null”.

## 13. Extended filtering: khác basic ở wildcard và các subtags trung gian

Ví dụ range **`de-DE`** là basic range. Basic filtering thường chỉ khớp `de-DE` và `de-DE-1996`, **không** khớp `de-Latn-DE` vì `Latn` chen giữa `de` và `DE`.

Extended filtering có thể phù hợp với những tags có script chen giữa khi so `de-DE`, bởi cơ chế extended cho phép tìm các non-wildcard subtags theo thứ tự và bỏ qua một số subtags trung gian theo quy tắc. Range `de-*-DE` biểu đạt rõ ý cho phép một vị trí wildcard giữa language và region.

Cây ví dụ:

```text
de
de-DE
de-Deva
de-Deva-DE
de-Latn-DE
de-DE-1996
de-Latn-DE-1996
en-US
```

Với `de-*-DE`:
- `AUTOSELECT_FILTERING` nhận biết range extended và chọn extended.
- `EXTENDED_FILTERING` cũng dùng extended.
- `IGNORE_EXTENDED_RANGES` bỏ range `de-*-DE`, nên không có match trong ví dụ chỉ có một range đó.
- `MAP_EXTENDED_RANGES` biến `de-*-DE` thành `de-DE` rồi basic filter.
- `REJECT_EXTENDED_RANGES` từ chối input bằng exception.

**Không tự triển khai extended matching bằng String regex đơn giản**: RFC 4647 có quy tắc subtag, wildcard, singleton extension và thứ tự; code tự viết dễ cho kết quả khác JavaDoc.

## 14. Chương trình 3 — toàn bộ năm FilteringMode

Tạo `FilteringModeDemo.java`:

```java
import java.util.*;

public class FilteringModeDemo {
    public static void main(String[] args) {
        List<String> tags = List.of(
                "de", "de-DE", "de-Deva",
                "de-Deva-DE", "de-Latn-DE",
                "de-DE-1996", "de-Latn-DE-1996",
                "en-US");

        List<Locale.LanguageRange> priority =
                Locale.LanguageRange.parse("de-*-DE");

        for (Locale.FilteringMode mode :
                Locale.FilteringMode.values()) {

            try {
                System.out.println(
                        mode + "=" +
                        Locale.filterTags(
                                priority, tags, mode));
            } catch (IllegalArgumentException ex) {
                System.out.println(
                        mode + "=IllegalArgumentException");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 FilteringModeDemo.java
java FilteringModeDemo
```

```text
AUTOSELECT_FILTERING=[de-DE, de-Deva-DE, de-Latn-DE, de-DE-1996, de-Latn-DE-1996]
EXTENDED_FILTERING=[de-DE, de-Deva-DE, de-Latn-DE, de-DE-1996, de-Latn-DE-1996]
IGNORE_EXTENDED_RANGES=[]
MAP_EXTENDED_RANGES=[de-DE, de-DE-1996]
REJECT_EXTENDED_RANGES=IllegalArgumentException
```

`MAP_EXTENDED_RANGES` **không** thể suy là “giữ tất cả candidates chỉ cần có de và DE ở đâu đó”; nó loại dấu `*` và tạo basic range `de-DE`, vì vậy `de-Latn-DE` không khớp basic mode. `AUTOSELECT` với extended range cho phép match `de-Latn-DE`.

Tất cả các phương thức/enum được dùng trong chương trình này thuộc Java 8+, trừ `List.of` (Java 9+). Nếu cần Java 8 compile, thay `List.of` bằng `Arrays.asList`; các method Locale không thay đổi.

## 15. Vì sao `AUTOSELECT_FILTERING` không phải luôn Basic?

Nhiều người nghĩ vì `filterTags` JavaDoc nhắc đến *basic filtering*, nên overload mặc định luôn dùng basic. Thực tế JavaDoc nói **mặc định tương đương `AUTOSELECT_FILTERING`**:
- **Tất cả ranges là basic** → basic filtering.
- **Có ít nhất một extended range** → extended filtering cho list.

Điều này có nghĩa một request header chứa wildcard ở vị trí không phải toàn bộ string có thể làm cách matching đổi cho các ranges khác cùng list. Nếu ứng dụng chỉ cho phép basic ranges do yêu cầu giao thức hoặc an toàn thao tác, cân nhắc **`REJECT_EXTENDED_RANGES`** để phát hiện vi phạm thay vì lặng lẽ đổi sang extended.

Ví dụ về chính sách:

```java
List<String> accepted = Locale.filterTags(
        priority,
        supportedTags,
        Locale.FilteringMode.REJECT_EXTENDED_RANGES);
```

Đây là snippet trong method với các biến có sẵn. Nó **không phải khuyến nghị áp dụng bắt buộc cho mọi HTTP Accept-Language**: HTTP có thể dùng basic ranges phù hợp, nhưng ứng dụng phải quyết định policy của mình theo contract. `REJECT` hữu ích khi input được cam kết chỉ có basic syntax.

Một điều khác: `lookup`/`lookupTag` **không nhận FilteringMode**; đừng cố ép `MAP_EXTENDED_RANGES` vào lookup khi API không có overload đó.

## 16. Parse: từ header sang ưu tiên có trọng số

`Locale.LanguageRange.parse` (Java 8+) nhận:
- `"ja,en;q=0.4"`;
- `"Accept-Language: ja,en;q=0.4"`;
- `"fr-CA,en-US;q=0.8,fr;q=0.4"`.

Trọng số mặc định là `MAX_WEIGHT` = 1.0; tối thiểu `MIN_WEIGHT` = 0.0. `getRange()` cho range canonicalized theo cách Java lưu; `getWeight()` cho weight.

**Điểm tinh tế**:
1. Parsing **chỉ kiểm cú pháp**, không xác minh file dịch cho ngôn ngữ đó tồn tại hoặc mã vùng thực sự được hỗ trợ.
2. `parse` sắp range theo weight/priority. Không nên tự sort lại theo alphabet vì làm sai preference.
3. Nếu một range lặp lại, theo JavaDoc chỉ **lần đầu** được đưa vào priority list, không cộng/trung bình weights.
4. `parse` có thể **mở rộng tương đương** dựa trên IANA Language Subtag Registry, ví dụ từ mã cũ `iw` (Hebrew) tới `he`.
5. Mã vùng/script liên quan đến BCP 47. Đừng dùng một bảng tự chế cứng rồi coi Java sẽ luôn khớp đúng bảng đó.

Nếu header từ client không hợp lệ (sai weight, sai range), `parse` ném `IllegalArgumentException`. Bạn cần API-level policy để trả response lỗi, coi header là chưa cung cấp, hoặc chuyển sang fallback; không để một request hỏng phá vỡ toàn bộ request handling ngoài ý muốn.

## 17. Chương trình 4 — q weights, duplicate và aliases

Tạo `LanguageRangeDemo.java`:

```java
import java.util.*;

public class LanguageRangeDemo {
    public static void main(String[] args) {
        List<Locale.LanguageRange> p =
                Locale.LanguageRange.parse(
                        "Accept-Language: " +
                        "fr-CA,en-US;q=0.8,fr;q=0.4");

        for (Locale.LanguageRange range : p) {
            System.out.printf(
                    Locale.ROOT,
                    "%s=%.1f%n",
                    range.getRange(),
                    range.getWeight());
        }

        List<Locale.LanguageRange> duplicates =
                Locale.LanguageRange.parse(
                        "en-US;q=0.7,en-US;q=0.2,fr");

        System.out.println(
                "duplicates=" +
                duplicates.stream()
                        .map(x -> x.getRange()
                                + ":" + x.getWeight())
                        .toList());

        List<Locale.LanguageRange> aliases =
                Locale.LanguageRange.parse(
                        "iw,en-US;q=0.7");

        System.out.println(
                "aliases=" +
                aliases.stream()
                        .map(Locale.LanguageRange::getRange)
                        .toList());

        try {
            Locale.LanguageRange.parse("en;q=1.1");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad-q=IllegalArgumentException");
        }

        try {
            Locale.LanguageRange.parse("en-!");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad-range=IllegalArgumentException");
        }
    }
}
```

```bash
javac -encoding UTF-8 LanguageRangeDemo.java
java LanguageRangeDemo
```

```text
fr-ca=1.0
en-us=0.8
fr=0.4
duplicates=[fr:1.0, en-us:0.7]
aliases=[iw, he, en-us]
bad-q=IllegalArgumentException
bad-range=IllegalArgumentException
```

Diễn giải:
- `fr-CA` được lưu thành range `fr-ca`, có q mặc định 1.0.
- `fr` với q=0.4 được xếp sau `en-us` q=0.8, dù xuất hiện trước/sau ở chỗ nào trong chuỗi.
- Duplicated `en-US` chỉ giữ range đầu tiên (q=0.7), còn `fr` không weight có q=1.0.
- `iw` là mã Hebrew cũ; parser có thể đưa thêm `he` tương đương theo registry.
- q=1.1 ngoài miền hợp lệ; `en-!` có syntax lỗi, đều ném `IllegalArgumentException`.

**Kết quả alias có thể liên quan dữ liệu registry đi kèm JDK**. Nếu ứng dụng kiểm tra bản dịch theo tên hoặc cần output exact lâu dài, nên test trên JDK được triển khai, dùng tag tiêu chuẩn hiện hành và tránh mặc định mọi alias nhất định luôn tồn tại ở mọi runtime.

## 18. Trọng số `q=0`, wildcard `*` và lựa chọn ứng dụng

Một vài câu hỏi thường gặp:

**Nếu q=0?** Theo matching có trọng số, `q=0` không phải ưu tiên tích cực. Thử nghiệm trên JDK hiện dùng:
```java
Locale.filterTags(
        Locale.LanguageRange.parse("en;q=0"),
        List.of("en", "en-US", "fr")); // []
```

```java
Locale.lookupTag(
        Locale.LanguageRange.parse("en;q=0"),
        List.of("en", "en-US", "fr")); // null
```

Đây là snippets JDK 17+ do dùng `List.of`. Trong môi trường HTTP, phải hiểu semantics của `Accept-Language` và chính sách resource của ứng dụng; đừng dùng q=0 để gắn nhãn ưu tiên cao hoặc làm fallback cưỡng bức.

**Nếu chỉ có wildcard `*`?**
- `filterTags(parse("*"), tags)` có thể trả mọi candidate tags (được Java filter).
- `lookupTag(parse("*"), tags)` trả null do wildcard độc lập bị bỏ qua khi lookup.

**Nếu không gửi header?** Đừng cố `parse(null)` hoặc `parse("")` mà không xử lý; hãy chọn fallback policy của app. Nếu caller gửi header syntactically ill-formed, quyết định nên reject hay fallback theo API contract. Ứng dụng có thể lưu raw header cho debug với biện pháp tránh log thông tin nhạy cảm, nhưng không tự tin rằng parsing tự động kiểm soát mọi input nguy hiểm.

Wildcard **không** mang ý nghĩa “dịch ra bất kỳ ngôn ngữ nào rồi lấy gần nhất”; nó chỉ nói về matching một tập supported tags đã có.

## 19. Case-insensitive matching và duplicate tags

Matching RFC 4647 **không phân biệt chữ hoa/thường** khi xét language tags, nhưng `Locale.filterTags` và `lookupTag` **giữ cách viết ban đầu** của kết quả String được chọn.

Ví dụ candidates:
```text
de-ch
de-CH
de-DE
en-US
```

Khi filter range `de`, `de-ch` và `de-CH` được xem là một matching tag duplicate khác case. JavaDoc cho biết **first encountered tag** được giữ. `lookupTag` nếu khớp `de-CH` cũng trả dạng được thấy đầu tiên, ví dụ `de-ch`.

Điều này quan trọng nếu catalog tags được lưu bằng String:
- Dùng một collection có thứ tự, ví dụ `List`, để kết quả ổn định.
- Không dựa vào iteration order của `HashSet` cho việc quyết định tag trong trường hợp duplicate/candidates tương đương.
- Từ phía ứng dụng, nên **chuẩn hóa catalog tags một lần** (ví dụ qua `Locale.forLanguageTag(...).toLanguageTag()` nếu hợp lệ) và tránh duplicate.
- Đừng dùng `equals` phân biệt chữ hoa/thường làm bước duy nhất nếu giao thức khẳng định matching case-insensitive.

Với `List<Locale>`, `Locale` objects đã mang cấu trúc language/script/region; khi in `toLanguageTag` thường nhận dạng normalized theo BCP 47. `Locale.filter` trả **Locale**, không giữ nguyên chữ hoa của raw input String.

## 20. Chương trình 5 — case, duplicate và lookupTag

Tạo `CaseAndDedupDemo.java`:

```java
import java.util.*;

public class CaseAndDedupDemo {
    public static void main(String[] args) {
        List<String> tags = List.of(
                "de-ch", "de-CH", "de-DE", "en-US");

        List<Locale.LanguageRange> range =
                Locale.LanguageRange.parse("de");

        System.out.println(
                "filterTags=" +
                Locale.filterTags(range, tags));

        List<Locale> locales = tags.stream()
                .map(Locale::forLanguageTag)
                .toList();

        System.out.println(
                "filter locales=" +
                Locale.filter(range, locales)
                        .stream()
                        .map(Locale::toLanguageTag)
                        .toList());

        System.out.println(
                "lookupTag preserves case=" +
                Locale.lookupTag(
                        Locale.LanguageRange.parse("de-CH"),
                        tags));

        System.out.println(
                "lookupTag no exact de=" +
                Locale.lookupTag(range, tags));
    }
}
```

```bash
javac -encoding UTF-8 CaseAndDedupDemo.java
java CaseAndDedupDemo
```

```text
filterTags=[de-ch, de-DE]
filter locales=[de-CH, de-DE]
lookupTag preserves case=de-ch
lookupTag no exact de=null
```

`filterTags` chọn `de-ch` vì đây là biến thể xuất hiện đầu tiên trong danh sách input. `filter` nhận hai Locale objects được tạo từ `de-ch` và `de-CH` nhưng loại duplicate, in normalized `de-CH`. `lookupTag` tìm range `de-CH` và trả case input được giữ là `de-ch`.

Hàng cuối tiếp tục minh họa sự khác nhau giữa filter/lookup: range `de` lọc được `de-ch` và `de-DE`, nhưng lookup không tự nâng một range ngắn `de` lên tag vùng `de-CH` khi không có tag `de` độc lập.

## 21. Xây dựng locale negotiation cho một ứng dụng web

Các bước an toàn:
1. Ứng dụng định nghĩa một **supported locale catalog** thật sự có resources; ví dụ `vi-VN`, `en-US`, `en-GB`, `fr-FR`.
2. Chọn một **fallback locale** chắc chắn nằm trong catalog, ví dụ `vi-VN`.
3. Đọc header `Accept-Language` nếu request có cung cấp; giới hạn length và format theo HTTP/framework.
4. Dùng `Locale.LanguageRange.parse` để tạo priority list.
5. Dùng `Locale.lookup` cho **chọn đúng một locale** nếu đây là policy của ứng dụng.
6. Nếu lookup null, dùng fallback đã định nghĩa. Có thể áp **policy tùy biến** nếu sản phẩm muốn chọn một vùng trong cùng ngôn ngữ (nhưng không được nói đó là hành vi tự động của `lookup`).
7. Chỉ sau khi chọn được locale hợp lệ mới gọi `ResourceBundle`/formatting/rendering.
8. Nếu response cache/CDN phụ thuộc header, thiết kế cache key và `Vary: Accept-Language` phù hợp để tránh gửi nhầm language response.
9. Cân nhắc preference do người dùng chọn trong tài khoản/URL có thể **ưu tiên hơn header** theo quy tắc sản phẩm.
10. Log các tình huống không match mà không ghi vô hạn raw header từ request không tin cậy.

**Không lấy danh sách supported từ `Locale.getAvailableLocales()` rồi coi mọi locale JVM biết đều có bản dịch trong ứng dụng**. Tập locale của JDK phản ánh locale data provider chứ không đồng nghĩa bộ resource của sản phẩm. Hãy lấy supported list từ catalog ngôn ngữ thực tế.

## 22. Chương trình 6 — lọc, chọn và fallback cho trang web

Tạo `LocaleNegotiationDemo.java`:

```java
import java.util.*;

public class LocaleNegotiationDemo {
    static Locale choose(
            String raw,
            List<Locale> supported,
            Locale fallback) {

        List<Locale.LanguageRange> priorities =
                Locale.LanguageRange.parse(raw);

        Locale best = Locale.lookup(
                priorities, supported);

        return best != null ? best : fallback;
    }

    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-FR"));

        String header =
                "fr-CA,en-GB;q=0.9,vi-VN;q=0.8";

        List<Locale.LanguageRange> priority =
                Locale.LanguageRange.parse(header);

        System.out.println(
                "filtered=" +
                Locale.filter(priority, supported)
                        .stream()
                        .map(Locale::toLanguageTag)
                        .toList());

        System.out.println(
                "selected=" +
                choose(
                        header,
                        supported,
                        Locale.forLanguageTag("vi-VN"))
                        .toLanguageTag());

        System.out.println(
                "fallback=" +
                choose(
                        "ja-JP,de-DE",
                        supported,
                        Locale.forLanguageTag("vi-VN"))
                        .toLanguageTag());

        System.out.println(
                "all-no=" +
                Locale.filterTags(
                        Locale.LanguageRange.parse("ja"),
                        List.of("vi-VN", "en-US"))
                        .isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 LocaleNegotiationDemo.java
java LocaleNegotiationDemo
```

```text
filtered=[en-GB, vi-VN]
selected=en-GB
fallback=vi-VN
all-no=true
```

Giải thích:
- Server có `fr-FR` nhưng user muốn `fr-CA`. Basic filtering không coi hai locale đó là trùng; `fr-FR` không xuất hiện trong `filtered`.
- `en-GB` là candidate phù hợp mức q=0.9; `vi-VN` cũng phù hợp mức q=0.8.
- `Locale.lookup` chọn `en-GB`.
- Nếu user chỉ muốn Nhật/Đức mà server không có candidate phù hợp, `lookup` trả null; method `choose` áp fallback sản phẩm `vi-VN`.
- `all-no=true` chứng minh lọc không match trả List rỗng.

**Hạn chế của demo:** `choose` giả định raw header cú pháp hợp lệ và fallback thuộc supported list. API production phải xử lý header rỗng/sai cú pháp, validation supported catalog, app-specific preferences và cache policy. Không dùng `Locale.getDefault()` bất chợt để lấp chỗ trống vì default JVM có thể khác môi trường deploy.

## 23. Nếu chỉ hỗ trợ `en-US` mà user chỉ gửi `en` thì sao?

Đây là ca dễ xuất hiện nhất trong ứng dụng có language-specific resources theo region.

```java
List<String> tags = List.of("en-US");
List<Locale.LanguageRange> languageOnly =
        Locale.LanguageRange.parse("en");

System.out.println(
        Locale.filterTags(languageOnly, tags));
System.out.println(
        Locale.lookupTag(languageOnly, tags));
```

Đây là snippet JDK 17+, output:
```text
[en-US]
null
```

**Không được giải thích** rằng lookup “tự chọn en-US vì en khớp một phần”; lookup là thuật toán khác filtering. Có ba phương án rõ ràng cho ứng dụng:
- **Policy 1:** lưu cả resource locale `en` trong supported catalog nếu cần lookup đúng generic English.
- **Policy 2:** đặt một **explicit language-to-default-region mapping**, ví dụ `en → en-US`, xử lý trước/hoặc sau matching; đây là quy tắc sản phẩm, phải kiểm thử.
- **Policy 3:** chọn fallback cố định đã hỗ trợ, bất kể language-only preference.

Nếu cần thỏa hiệp “chỉ có một candidate English region thì chọn nó”, có thể cân nhắc `filter` cho bước fallback khi lookup null, **nhưng phải xác định ưu tiên** và tránh việc filter cho nhiều variants mà thứ tự chỉ dựa vào collection. Đừng đổi `lookup` thành `filter(...).get(0)` mà không ghi nhận thay đổi semantics.

## 24. `Locale.forLanguageTag`, `Locale.Builder` và tag validation

Có ba mục tiêu khác nhau:
1. **Parse một tag** thành Locale: `Locale.forLanguageTag("zh-Hant-TW")`.
2. **Tạo Locale đã kiểm tra syntax** theo từng field: `new Locale.Builder().setLanguageTag("zh-Hant-TW").build()`.
3. **Match preference** với offered catalog: `Locale.filter`/`lookup`.

`Locale.forLanguageTag` có thể xử lý một vài input không hoàn chỉnh bằng cách bỏ phần không hợp lệ theo contract, nên nếu bạn cần **fail-fast về cú pháp** cho supported tags do admin cấu hình, cân nhắc `Locale.Builder` (ném `IllformedLocaleException` khi tag không đúng syntax). Cũng cần lưu ý **syntactically well-formed** không bảo đảm ngôn ngữ/vùng đã đăng ký hoặc resource translation tồn tại.

Đừng dùng `Locale.toString()` để xuất BCP 47 tag: từ Locale được chọn, dùng `toLanguageTag()`. Với Java 8, `new Locale("en","US")` từng phổ biến và vẫn có trên runtime cũ, nhưng tài liệu JDK hiện đại khuyến nghị **`Locale.of(...)`** cho khởi tạo trực tiếp ở phiên bản mới; `Locale.of` là API bổ sung sau Java 8. Để code portable Java 8+ và biểu diễn đúng BCP 47, `Locale.forLanguageTag` là lựa chọn tốt.

**Special Note phiên bản:** Một vài constructor Locale cũ được đánh dấu deprecated trong JDK hiện đại; bài này không dựa vào chúng. Các method matching đang học **không bị deprecated** theo tài liệu Java SE 26.

## 25. LanguageRange.parse có alias expansion tự động

Đầu vào `iw` (mã Hebrew cũ) có thể được parser mở rộng thành `he` theo dữ liệu tương đương trong IANA. Ví dụ chương trình `LanguageRangeDemo` đã in:

```text
aliases=[iw, he, en-us]
```

Điều đó có tác dụng thực tế: user hoặc hệ thống cũ gửi một language range historical, trong khi supported catalog dùng tag hiện hành; matching có thể tìm được tương đương mà bạn không tự duy trì bảng đổi mã.

Nhưng đừng nhầm:
- “Parser mở rộng equivalents” **không có nghĩa** nó tự dịch resource.
- “Một số mã có alias” **không có nghĩa** mọi ngôn ngữ có từ đồng nghĩa được mở rộng tự động.
- “Equivalent language code” **không có nghĩa** `fr-CA` và `fr-FR` là cùng locale.
- “Matching syntax” **không có nghĩa** Java xác thực quốc gia tồn tại trong IANA theo cách đầy đủ.
- “JDK data” có thể thay đổi giữa versions, cần kiểm thử nếu project phụ thuộc vào exact expansion list.

Nếu sản phẩm có mapping riêng, `Locale.LanguageRange.mapEquivalents(priority,map)` và overload `parse(ranges,map)` cho phép tùy biến mapping. Chỉ thêm map khi có yêu cầu nghiệp vụ cụ thể và kiểm tra duplicate/trọng số; đừng tự sửa alias mà không biết cách Java đã expand.

## 26. Kết quả có thứ tự nhưng không phải bảng xếp hạng “gần về văn hóa”

`filter`/`filterTags` sắp theo priority/weight của language ranges. `lookup`/`lookupTag` chọn theo thứ tự xét preference và truncation. Cả hai thực hiện **matching chuỗi con BCP 47 theo RFC 4647**, không phải học máy đo “gần giống ngôn ngữ” hoặc tìm quốc gia gần nhau.

Ví dụ `pt-PT` và `pt-BR` cùng là Portuguese nhưng vùng khác; mức độ tương thích của translation tùy domain. RFC 4647 không tự đánh giá khác biệt văn hóa, date formatting, số thập phân hay chính sách pháp lý. Nếu chỉ có một locale vùng và bạn muốn fallback sang vùng khác cùng language, hãy **định nghĩa rõ** thứ tự fallback và xác minh tài nguyên phù hợp.

Một bẫy khác: quan sát `filterTags` trả List có thứ tự rồi dùng phần tử đầu tiên làm **best match**. Kết quả này có thể là lựa chọn đúng cho **policy riêng**, nhưng **không phải kết quả `lookupTag` theo RFC 4647** trong mọi trường hợp, như ví dụ range `en` đã chứng minh.

Với nhiều candidates đồng mức, nên cung cấp `List` có thứ tự do ứng dụng định nghĩa. `HashSet` hoặc collection không giữ thứ tự có thể làm lựa chọn case-duplicate/first matching tag thay đổi qua lần chạy.

## 27. Empty result, null, exception và fallback

Bảng tình huống:

| Tình huống | Hành vi | Xử lý ứng dụng |
| --- | --- | --- |
| `filter` không match | `List<Locale>` rỗng | `isEmpty()` / hiển thị không có lựa chọn |
| `filterTags` không match | `List<String>` rỗng | `isEmpty()` |
| `lookup` không match | `null` | Fallback locale từ catalog |
| `lookupTag` không match | `null` | Fallback tag từ catalog |
| `parse` gặp q hoặc range không hợp lệ | `IllegalArgumentException` | Reject hoặc fallback theo contract |
| `REJECT_EXTENDED_RANGES` gặp range extended | `IllegalArgumentException` | Thông báo policy/nhận basic ranges |
| `filter`/`lookup` nhận collection null | `NullPointerException` | Validate input trước |
| Catalog support rỗng | Không có match | Policy phải xử lý thiếu resource/config |
| Header không được cung cấp | Không gọi `parse(null)` | Dùng user preference/app default |
| Catalog có duplicate tags khác case | Lọc loại trùng, giữ case đầu với filterTags | Chuẩn hóa catalog và thứ tự |

Câu hỏi cần quyết định **trước khi code**: Fallback theo “application default”, theo “browser locale”, theo “user profile” hay theo “first supported” ? Các lựa chọn đều là **quy tắc sản phẩm**, không phải điều `Locale.lookup` tự suy.

Cẩn thận tình huống **malformed header**: lựa chọn “im lặng về fallback” có thể hợp lý cho website public, nhưng một API có contract strict có thể trả lỗi. Cùng một header có thể đi qua proxy/framework khác nhau; code phải có kiểm thử integration.

## 28. HTTP Accept-Language không thay thế preference chủ động của user

Header từ client là một gợi ý hữu ích, nhưng người dùng có thể chọn language cụ thể trong ứng dụng. Một thứ tự chính sách thường được cân nhắc:
1. **Lựa chọn explicit** trong profile/URL/cookie đã xác thực.
2. **Accept-Language** khi chưa có lựa chọn explicit.
3. **Fallback locale** của ứng dụng khi không match.

Đây là **ví dụ policy**, không phải luật bắt buộc của Java. Nếu sản phẩm đã có quy định khác, tuân thủ quy định đó.

Với response caching, trang theo locale có thể cần một key chứa locale đã chọn và header **`Vary: Accept-Language`** nếu nội dung thực tế phụ thuộc header và cache HTTP được dùng. Nếu user profile ảnh hưởng nội dung, cache còn có các giới hạn khác. Không đơn giản dùng một cache entry không phân biệt ngôn ngữ cho tất cả user.

Một số HTTP APIs chỉ chấp nhận ngôn ngữ theo language code hơn là region. Hãy xác định tập `supportedTags` thật và có thể tạo một tầng custom fallback, nhưng **đừng dùng matching như công cụ xác thực bảo mật**. Header là input ngoài, cần độ dài hợp lý, parsing/catch và tránh log kích thước không giới hạn.

## 29. So sánh với ResourceBundle fallback

`ResourceBundle.getBundle(baseName,locale)` có **cơ chế candidate locale và fallback** riêng để tìm properties/resource. Nó **không đồng nhất** với `Locale.lookup` hay `Locale.filter`.

Ví dụ có một bundle `messages_en_US.properties` và request `en`. `Locale.lookupTag(parse("en"), List.of("en-US"))` có thể trả `null`; ResourceBundle có quy tắc candidate/fallback riêng để tìm resource theo tên và default locale. Nếu dùng Locale matching trước ResourceBundle, bạn phải biết **hai tầng logic** và không giả định `lookup` đã chứng minh chắc resource file tồn tại.

Một workflow tốt:
- Khai báo **supported locales** từ những resource mà bạn thực sự triển khai.
- Negotiation một Locale dựa trên supported list và policy.
- Dùng Locale đã chọn để lấy ResourceBundle.
- Test “bundle có tồn tại đúng locale đó?” và “fallback resource” riêng.
- Không kết luận JVM `getAvailableLocales()` có locale nào thì ứng dụng cũng cung cấp content ngôn ngữ đó.

Đây cũng là lý do nên tách một service `negotiateLocale(request, supported)` khỏi code đọc/format resource. Những thay đổi product policy sẽ dễ review hơn, và test matching không cần khởi tạo toàn bộ ứng dụng.

## 30. Tương thích Java 8 và JDK hiện hành

| API/cú pháp | Java 8 | Java 17+ hiện đại |
| --- | --- | --- |
| `Locale.filter` / `Locale.filterTags` | Có | Còn hỗ trợ |
| `Locale.lookup` / `Locale.lookupTag` | Có | Còn hỗ trợ |
| `Locale.LanguageRange.parse` | Có | Còn hỗ trợ |
| `Locale.FilteringMode` | Có | Còn hỗ trợ |
| `Locale.forLanguageTag` / `toLanguageTag` | Có | Còn hỗ trợ |
| `Locale.Builder` | Có | Còn hỗ trợ |
| `Arrays.asList` | Có | Có |
| `List.of` | Không | Có (Java 9+) |
| `Stream.toList` | Không | Có (Java 16+) |
| `Locale.of("en","US")` | Không | Có ở JDK mới (Java 19+) |
| Locale constructors truyền thống | Có | Một số được đánh dấu deprecated; ưu tiên factory/tag |

Sáu chương trình bài này dùng `List.of`/`Stream.toList` nên biên dịch bằng **JDK 17+**, nhưng APIs **đúng chủ đề đều Java 8-compatible**. Để chuyển ví dụ sang Java 8:
- `List.of(a,b)` → `Arrays.asList(a,b)`.
- `stream.toList()` → `stream.collect(Collectors.toList())`.
- Không gọi `Locale.of(...)` nếu cần chạy trên Java 8.
- Giữ nguyên `Locale.forLanguageTag`, `LanguageRange.parse` và matching methods.

Việc JDK mới cải thiện locale data/CLDR có thể thay một số dữ liệu hiển thị/alias, nên nếu đầu ra exact là yêu cầu của hệ thống, test trên JDK mục tiêu chứ không tự kết luận mọi JVM sẽ in một tên vùng giống hệt.

## 31. Hiệu năng, cache và an toàn đa luồng

**Locale objects và matching results không buộc phải tái tạo cho mọi dòng text.** Với một request có language header, thông thường parse/lookup **một lần trên supported catalog**, giữ Locale đã chọn trong request context, rồi dùng xuyên suốt các bước format/render.

Thực hành:
- Giữ `List<Locale> supported` ổn định và immutable hoặc bảo vệ khỏi concurrent mutation.
- Cache kết quả negotiation nếu có nhu cầu và phải xét cache key đủ các biến: raw/canonical preferences, supported list version, policy version.
- Không cache vô hạn theo raw header không tin cậy; attacker có thể đưa vô số header khác nhau gây memory growth.
- Không sửa shared `ArrayList` supported locales giữa lúc request khác đang matching.
- Không chuyển `Locale.setDefault` thành cơ chế chọn locale theo từng request; đây là **global JVM state**, làm các threads/request ảnh hưởng nhau.
- Ưu tiên truyền Locale rõ ràng tới formatter/ResourceBundle/business logic.
- Với số supported locales nhỏ, hiệu năng parse/filter thường không phải nút thắt chính; **đo trước khi tạo một lớp cache phức tạp**.

Không dùng một `HashSet` không có thứ tự nếu lựa chọn duplicate-case/first match cần deterministic. Hãy normalize và xác định thứ tự catalog ngay lúc khởi tạo ứng dụng.

## 32. Checklist kiểm thử Locale matching

**Kiểm thử cơ bản**:
- Range `fr` match `fr-CA`/`fr-FR` bằng `filter`.
- Range `en` match `en-US` qua `filterTags` nhưng `lookupTag` có thể null nếu thiếu `en` chính xác.
- Priority có `q` khác nhau làm thứ tự filter phù hợp.
- Parse header với/không có tiền tố `Accept-Language:`.
- Parse có duplicate range chỉ giữ lần đầu.
- Alias cũ/hiện hành được xử lý đúng với JDK target.

**Kiểm thử nâng cao**:
- `de-*-DE` dưới tất cả năm FilteringMode.
- `REJECT_EXTENDED_RANGES` ném IllegalArgumentException.
- `lookup` thử truncation `zh-Hant-TW → zh-Hant`.
- `lookupTag` không match trả null, `filterTags` không match trả List rỗng.
- Wildcard `*` trong filtering và lookup có hành vi khác.
- Tags trùng khác case, thứ tự input có thể ảnh hưởng case được giữ.
- Header có q=0, q sai, range sai; policy lỗi/fallback.
- Supported catalog rỗng, duplicate, hoặc thiếu fallback.
- User profile preference có được ưu tiên theo chính sách sản phẩm?
- Thay JDK/locale data có làm alias list hoặc formatting khác?
- Cache có phân biệt các kết quả ngôn ngữ?
- Không dùng `Locale.setDefault` toàn cục trong request handler.

Một bộ test tốt nên assert **các kết quả matching theo tiêu chuẩn và business policy**, không chỉ xem code không ném exception. Bài có sáu chương trình mô phỏng đủ các nhóm cơ bản, lookup, modes, parsing, case/dedup và negotiation.

## 33. Lỗi phổ biến và cách tránh

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Gọi `Locale.lookup` rồi nghĩ trả List | API trả **một** Locale hoặc null | Phân biệt lookup vs filter |
| Gọi `Locale.filter` và test null khi không match | API trả **List rỗng** | `isEmpty()` |
| Gọi `lookupTag` với `Collection<Locale>` | Tham số cần String tags | Dùng `lookup` |
| Gọi `filterTags` rồi mong Locale objects | Trả Strings | Dùng `filter` nếu cần Locale |
| Cho rằng `filter(...).get(0)` luôn bằng `lookup` | Cơ chế khác nhau | Chọn đúng RFC 4647 behavior |
| Cho rằng lookup `en` tự chọn `en-US` | Lookup không phải prefix filtering | Explicit fallback mapping |
| Dùng `String.startsWith("en")` | Không tuân thủ subtag/mode | Dùng Locale matching |
| Dùng `Locale.toString()` làm BCP 47 tag | Thường có dấu `_` | `toLanguageTag()` |
| Dùng `en_US` như header BCP 47 | BCP 47 dùng `-` | `en-US` |
| Không parse `q` | Làm sai thứ tự preference | `LanguageRange.parse` |
| Tự sort priority alphabetically | Mất weight/priority | Giữ LanguageRange list |
| Gộp duplicate q theo trung bình | Java parse dùng range đầu tiên | Hiểu `parse` contract |
| Coi `*` trong lookup là “chọn mọi” | Standalone wildcard bị bỏ qua | Policy fallback riêng |
| Coi q=0 là ưu tiên cao | Sai weighting | Xử lý theo semantics và policy |
| Dùng extended range với `REJECT` mà không catch | Ném IllegalArgumentException | Catch/chặn input |
| Nghĩ `IGNORE_EXTENDED_RANGES` trả null | Filter luôn trả List | Expect [] |
| Chọn `MAP_EXTENDED_RANGES` mà tưởng giữ wildcard ở giữa | Chuyển sang basic | Hiểu cách map `de-*-DE → de-DE` |
| Cho rằng `AUTOSELECT` luôn basic | Có extended range → extended | Chọn mode có chủ đích |
| Cho rằng match phân biệt hoa thường | RFC matching case-insensitive | Dùng API chuẩn |
| Cho rằng `filterTags` tự lowercase output | Giữ case của matched tag đầu | Chuẩn hóa catalog nếu cần |
| Dùng HashSet input khi cần first case deterministic | Iteration order không ổn định | List theo thứ tự |
| Không xử lý `lookup == null` | NPE sau đó | Fallback locale |
| Lấy `Locale.getDefault()` làm ngôn ngữ người dùng | Default JVM không đại diện user | Application default rõ |
| Dùng `getAvailableLocales` làm supported translation list | JVM có dữ liệu nhưng app chưa có resource | Catalog thực tế |
| Coi Locale matching là translator | Chỉ chọn tag/locale | Tách i18n content |
| Dùng `Locale.setDefault` mỗi request | Global state gây cross-request effect | Truyền Locale explicit |
| Dùng `Locale.of` trong code Java 8 | Chưa có Java 8 | `Locale.forLanguageTag` |
| Dùng `List.of`/`Stream.toList` khi compile Java 8 | API JDK mới hơn | Arrays.asList/Collectors.toList |
| Không giới hạn header từ client | Abuse/memory/cache issues | Limit/validation/fallback |
| Quên vary locale trong cache | Có thể trả sai ngôn ngữ | Cache key/Vary theo policy |

## 34. Tự kiểm tra: 22 câu hỏi

**1. `Locale.filter` nhận dữ liệu ứng viên loại gì?**  
`Collection<Locale>` và trả `List<Locale>`.

**2. `Locale.filterTags` trả gì?**  
`List<String>` chứa tags phù hợp với preference.

**3. `Locale.lookup` trả gì khi không match?**  
`null`, không phải List rỗng.

**4. `Locale.lookupTag` trả gì khi không match?**  
`null`, không tự lấy app default.

**5. Cả bốn method được giới thiệu từ Java nào?**  
Java 8 và vẫn được hỗ trợ.

**6. LanguageRange được tạo từ header bằng API gì?**  
`Locale.LanguageRange.parse(String)`.

**7. `q=0.8` nghĩa là gì?**  
Trọng số ưu tiên/quality 0.8 trong Language Priority List.

**8. Không ghi `q` thì mặc định bao nhiêu?**  
1.0.

**9. `filterTags(parse("fr"), List.of("fr-CA","fr-FR"))` trả gì?**  
Cả `fr-CA` và `fr-FR` theo cơ chế basic filtering.

**10. `lookupTag(parse("en"), List.of("en-US"))` trả gì?**  
`null` trong case này; lookup không tự nâng generic tag sang region variant.

**11. `filterTags(parse("en"), List.of("en-US"))` thì sao?**  
Trả `[en-US]`.

**12. `lookupTag(parse("zh-Hant-TW"), List.of("zh-Hant"))`?**  
Trả `zh-Hant` do cơ chế cắt dần subtag.

**13. Wildcard `*` trong lookup có luôn chọn candidate đầu?**  
Không; wildcard độc lập được bỏ qua.

**14. Mặc định filtering mode là gì?**  
`AUTOSELECT_FILTERING`.

**15. Nếu có extended range thì `AUTOSELECT` chọn gì?**  
Extended filtering cho priority list.

**16. `IGNORE_EXTENDED_RANGES` gặp duy nhất `de-*-DE` trả gì?**  
List rỗng trong ví dụ, vì range bị bỏ qua.

**17. `MAP_EXTENDED_RANGES` xử lý `de-*-DE` như thế nào?**  
Chuyển thành basic `de-DE` và matching theo basic mode.

**18. `REJECT_EXTENDED_RANGES` xử lý range extended ra sao?**  
Ném `IllegalArgumentException`.

**19. `filterTags` có chuẩn hóa case input String trong kết quả không?**  
Không; giữ case của matched tag được chọn (duplicate khác case lấy first).

**20. `Locale.forLanguageTag` khác `LanguageRange.parse` ở đâu?**  
Cái đầu tạo một Locale từ tag; cái sau tạo priority list ranges để matching.

**21. Tại sao `Locale.getDefault()` không phải fallback bắt buộc?**  
Nó là default của JVM/deployment, không nhất thiết là ngôn ngữ sản phẩm hoặc người dùng.

**22. Locale matching có tự dịch content?**  
Không; nó chỉ chọn resource locale/tag từ danh sách đã hỗ trợ.

## 35. Tổng kết

- **`Locale.filter`** lọc tập `Locale`, trả nhiều kết quả dạng `List<Locale>`.
- **`Locale.filterTags`** lọc tập **String language tags**, trả nhiều String, giữ case matched tag.
- **`Locale.lookup`** chọn một `Locale` tốt nhất theo RFC 4647 lookup, hoặc `null`.
- **`Locale.lookupTag`** chọn một String tag, hoặc `null`.
- **Filtering và lookup là hai cơ chế khác nhau**, không coi `lookup` là lấy phần tử đầu của `filter`.
- **`Locale.LanguageRange.parse`** chuyển priority list/Accept-Language thành ranges kèm `q`, sắp priority, có thể expand aliases.
- **`FilteringMode` có năm lựa chọn**, đặc biệt `AUTOSELECT` dùng extended khi có extended ranges, `MAP` chuyển extended sang basic, `REJECT` ném exception.
- **Basic filtering** khớp prefix theo subtag boundary; **lookup** cắt dần range chi tiết hơn, và `*` độc lập được bỏ qua.
- **Không match:** filter trả **List rỗng**, lookup trả **null**. Ứng dụng có trách nhiệm chọn fallback locale.
- Matching **không phân biệt case**, nhưng `filterTags`/`lookupTag` có thể giữ case String gốc.
- Tập supported locales phải phản ánh **bản dịch/resource thực tế**, không phải mọi locale JVM có.
- API Java 8 còn được hỗ trợ hiện nay. Bài dùng cú pháp Java 17+ cho các ví dụ runnable, không đánh đồng `List.of`/`Stream.toList` với Java 8.

### Tài liệu chính thức, còn hiện hành

- [Oracle Java SE 26 — `Locale`: Locale Matching](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): `filter`, `filterTags`, `lookup`, `lookupTag`, RFC 4647, basic vs extended, semantics kết quả.
- [Oracle Java SE 26 — `Locale.LanguageRange`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.LanguageRange.html): `parse`, `getRange`, `getWeight`, aliases và `mapEquivalents`.
- [Oracle Java SE 26 — `Locale.FilteringMode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.FilteringMode.html): cả năm giá trị và các ví dụ kết quả.
- [Oracle Java SE 8 — `Locale`](https://docs.oracle.com/javase/8/docs/api/java/util/Locale.html): xác nhận các method matching có từ Java 8.
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647): cơ chế basic/extended filtering và lookup.
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): BCP 47 tag syntax và subtags.
