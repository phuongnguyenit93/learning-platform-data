# Locale.filter, filterTags, lookup và lookupTag trong Java

## 1. Vì sao cần chọn locale?

Một hệ thống có thể cung cấp bản dịch tiếng Việt (`vi-VN`), tiếng Anh Mỹ (`en-US`), tiếng Anh Anh (`en-GB`), tiếng Pháp tại Pháp (`fr-FR`) và tiếng Pháp Canada (`fr-CA`). Một người dùng lại ưu tiên tiếng Pháp Canada, sau đó tiếng Pháp nói chung, cuối cùng tiếng Anh. Chương trình cần so sánh **những ngôn ngữ người dùng chấp nhận** với **những phiên bản ứng dụng thực sự hỗ trợ** để quyết định sẽ hiển thị bản dịch nào.

Không nên so sánh hai chuỗi locale bằng `equals` rồi dừng lại: yêu cầu `fr` có thể phù hợp nhiều phiên bản `fr-FR`, `fr-CA`; yêu cầu `zh-Hant-HK` có thể cần hạ dần mức cụ thể để tìm `zh-Hant`.

Java 8+ có bốn phương thức tĩnh thuộc `java.util.Locale` triển khai cơ chế **language matching** của RFC 4647:

- `Locale.filter`: lấy **danh sách các `Locale`** đáp ứng dải ngôn ngữ ưu tiên.
- `Locale.filterTags`: lấy **danh sách chuỗi language tag** đáp ứng dải ưu tiên.
- `Locale.lookup`: tìm **một `Locale` phù hợp nhất**, hoặc `null`.
- `Locale.lookupTag`: tìm **một chuỗi language tag phù hợp nhất**, hoặc `null`.

Hai họ thao tác **filtering** và **lookup** không có cùng quy tắc. Bài này tập trung vào việc chọn locale; sau khi chọn được một locale hợp lệ, các bước tải `ResourceBundle`, định dạng số/ngày và dịch nội dung vẫn là trách nhiệm riêng.

## 2. Ngôn ngữ, vùng và language range

Language tag theo BCP 47 thường có các thành phần như:

| Tag | Thành phần | Ý nghĩa |
| --- | --- | --- |
| `vi` | Language | Tiếng Việt, không chỉ định vùng |
| `vi-VN` | Language + region | Tiếng Việt trong ngữ cảnh Việt Nam |
| `en-US` | Language + region | Tiếng Anh tại Mỹ |
| `en-GB` | Language + region | Tiếng Anh tại Anh |
| `zh-Hant-TW` | Language + script + region | Tiếng Trung, chữ phồn thể, vùng Đài Loan |

Một **language range** diễn tả điều kiện tìm kiếm từ phía người dùng, không nhất thiết là language tag hoàn chỉnh có đúng một vùng. Ví dụ `en` là dải bao gồm nhiều phiên bản tiếng Anh khi lọc; `en-GB` cụ thể hơn; `*` là dải ký tự đại diện. Trong cú pháp **extended language range**, dấu `*` còn có thể xuất hiện ở giữa, chẳng hạn `de-*-DE`.

Danh sách có thứ tự ưu tiên của các language range được Java biểu diễn bằng `List<Locale.LanguageRange>`. Đây là đầu vào thứ nhất của cả bốn phương thức.

### 2.1. Tạo Language Priority List

Dùng `Locale.LanguageRange.parse(...)` để phân tích chuỗi ưu tiên, ví dụ giá trị của HTTP `Accept-Language`:

```java
import java.util.List;
import java.util.Locale;

List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("fr-CA,fr;q=0.8,en;q=0.5");
```

Ý nghĩa:

| Dải | Trọng số `q` | Ý định |
| --- | ---: | --- |
| `fr-CA` | 1.0 (mặc định) | Ưu tiên tiếng Pháp Canada |
| `fr` | 0.8 | Nếu không phù hợp, xét tiếng Pháp nói chung |
| `en` | 0.5 | Sau cùng có thể chấp nhận tiếng Anh |

`q` là trọng số ưu tiên, nằm trong khoảng `0.0` đến `1.0`; giá trị lớn có mức ưu tiên cao hơn. Khi bị bỏ qua, `q=1.0`. `parse` trả về các range đã được sắp theo mức ưu tiên/trọng số giảm dần và có thể bổ sung các range tương đương theo dữ liệu registry; vì vậy không nên tự giả định danh sách sau parse luôn chỉ chứa đúng các phần tử viết trong chuỗi đầu vào. Nếu range lặp, parser giữ lần xuất hiện đầu tiên. Range hoặc trọng số sai cú pháp có thể gây `IllegalArgumentException`.

Có thể tạo trực tiếp khi cấu hình đã có cấu trúc:

```java
List<Locale.LanguageRange> priorities = List.of(
        new Locale.LanguageRange("fr-CA", 1.0),
        new Locale.LanguageRange("fr", 0.8),
        new Locale.LanguageRange("en", 0.5)
);
```

Với cách tự tạo, chính chương trình phải đưa `List` về thứ tự ưu tiên phù hợp; matcher nhận một **priority list đã được sắp xếp**, không có nhiệm vụ sửa mọi danh sách nhập sai thứ tự. Trong ví dụ không cần xây thủ công vì `parse` đã có cơ chế xử lý.

Lưu ý `Locale.forLanguageTag("en-US")` tạo **một `Locale`**, còn `Locale.LanguageRange.parse("en-US,en;q=0.7")` tạo **danh sách tiêu chí lựa chọn**. Hai loại đối tượng đảm nhiệm hai vai trò khác nhau.

## 3. Bốn API và kiểu dữ liệu đầu vào/đầu ra

| Phương thức | Danh sách khả dụng nhận vào | Trả về | Khi nào dùng |
| --- | --- | --- | --- |
| `Locale.filter(priorityList, locales)` | `Collection<Locale>` | `List<Locale>` | Cần tất cả locale phù hợp để chọn/hiển thị |
| `Locale.filterTags(priorityList, tags)` | `Collection<String>` | `List<String>` | Catalog bản dịch đang lưu dạng chuỗi BCP 47 |
| `Locale.lookup(priorityList, locales)` | `Collection<Locale>` | `Locale` hoặc `null` | Cần một locale phù hợp nhất |
| `Locale.lookupTag(priorityList, tags)` | `Collection<String>` | `String` hoặc `null` | Cần một tag duy nhất để tra khóa tài nguyên |

Cả bốn đều là **static method của `Locale`** và có từ Java 8. Hai phương thức `filter` và `filterTags` còn có overload nhận `Locale.FilteringMode` để lựa chọn cách xử lý **extended language range**. Hai phương thức `lookup`/`lookupTag` không có tham số `FilteringMode`.

Danh sách locale/tag khả dụng phải phản ánh chính xác những bản dịch thực sự được triển khai. Việc máy ảo Java nhận ra một locale hoặc `Locale.getAvailableLocales()` liệt kê locale đó không chứng minh ứng dụng đã có bản dịch cho nó.

## 4. Filtering: lấy tất cả lựa chọn phù hợp

Với **basic filtering** (RFC 4647), một range là dạng tiền tố từ đầu language tag và chỉ khớp tại **ranh giới subtag**. Ví dụ:

| Range | Tag khả dụng | Basic filtering | Giải thích |
| --- | --- | --- | --- |
| `en` | `en-US` | Khớp | `en` là tiền tố nguyên subtag |
| `en` | `en-GB` | Khớp | Cùng ngôn ngữ |
| `en-US` | `en` | Không | Candidate thiếu region |
| `en-US` | `en-US-x-demo` | Khớp | Candidate cụ thể hơn và tiếp nối sau dấu `-` |
| `en` | `eng` | Không | Không khớp subtag nguyên vẹn |
| `fr` | `en-US` | Không | Khác language |

Vì vậy, với danh sách khả dụng `[en-US, en-GB, fr-FR]`, lọc bằng range `en` trả về cả `en-US` và `en-GB`, không chỉ một bản dịch đầu tiên. Với nhiều range, các kết quả được sắp theo mức ưu tiên/trọng số của range, loại bỏ bản trùng khớp. **Trong cùng một mức ưu tiên, thứ tự duyệt các ứng viên khả dụng có thể tác động đến thứ tự kết quả**: nên truyền `List` có thứ tự ổn định khi thứ tự hiển thị có ý nghĩa.

Mặc định `Locale.filter(priorityList, locales)` tương đương dùng `Locale.FilteringMode.AUTOSELECT_FILTERING`. Nó dùng basic filtering nếu danh sách chỉ có range dạng basic, hoặc extended filtering nếu có extended range.

### filter so với filterTags

Hai phương thức áp dụng cùng ý tưởng filtering nhưng khác kiểu dữ liệu:

```java
List<Locale> locales = List.of(
        Locale.forLanguageTag("en-US"),
        Locale.forLanguageTag("en-GB"),
        Locale.forLanguageTag("fr-FR")
);
List<Locale.LanguageRange> ranges = Locale.LanguageRange.parse("en");

List<Locale> selectedLocales = Locale.filter(ranges, locales);

List<String> tags = List.of("en-US", "en-GB", "fr-FR");
List<String> selectedTags = Locale.filterTags(ranges, tags);
```

`selectedLocales` chứa hai đối tượng `Locale`; `selectedTags` chứa hai chuỗi `"en-US"` và `"en-GB"`. `filterTags` giữ nguyên kiểu chữ của tag đầu vào được chọn (ví dụ tag `"en-us"` vẫn có thể được trả về dạng `"en-us"`) dù thao tác so khớp không phân biệt hoa/thường. Các tag chỉ khác nhau ở chữ hoa/thường được xem là trùng cho mục đích kết quả; giữ phiên bản xuất hiện trước.

**Kết quả không khớp:** filtering trả về `List` rỗng, không phải `null`. Một danh sách có nhiều kết quả cũng không có nghĩa hệ thống nên trả đồng thời nhiều bản dịch cho một người; kết quả có thể dùng để gợi ý lựa chọn hoặc kiểm tra khả năng hỗ trợ.

## 5. Lookup: tìm một lựa chọn phù hợp nhất

**Lookup không chỉ là `filter(...).get(0)`.** RFC 4647 xem mỗi language range là một mong muốn *cụ thể nhất*, rồi thử **giảm dần độ cụ thể** cho đến khi tìm được tag khả dụng.

Ví dụ danh sách ưu tiên có range `zh-Hant-HK`. Nếu hệ thống chỉ có `zh-Hant` và `en-GB`, lookup thử:

```text
zh-Hant-HK  → không có
zh-Hant     → có, chọn zh-Hant
```

Trong trường hợp đó, `Locale.lookup(...)` có thể chọn `zh-Hant`, còn `Locale.filter(...)` không trả `zh-Hant` cho range `zh-Hant-HK` vì ứng viên ít cụ thể hơn phạm vi yêu cầu; nếu priority list còn `en-GB` thì filter trả `en-GB`.

Một ví dụ **rất dễ nhầm**:

```java
List<Locale> supported = List.of(Locale.US, Locale.UK);
List<Locale.LanguageRange> requested = Locale.LanguageRange.parse("en");

System.out.println(Locale.filter(requested, supported)
        .stream().map(Locale::toLanguageTag).toList());
System.out.println(Locale.lookup(requested, supported));
```

Kết quả trên JDK 17+:

```text
[en-US, en-GB]
null
```

Vì filtering `en` chấp nhận các tag cụ thể hơn `en-US`/`en-GB`, nhưng lookup với range đúng bằng `en` trước hết cần tag `en` (và không có subtag nào để cắt tiếp). Một ứng dụng cần fallback từ `en` sang `en-US` phải **chủ động quy định fallback nghiệp vụ**, thêm một range thích hợp vào danh sách ưu tiên hoặc cung cấp tag `en` nếu thật sự có bản dịch đó. Không mặc định hai cơ chế tương đương.

### lookup và lookupTag

`Locale.lookup` trả về một `Locale`; `Locale.lookupTag` trả về một `String`, giữ kiểu chữ của tag khả dụng được chọn. Nếu không có ứng viên phù hợp, cả hai trả `null`. Dải `*` **bị bỏ qua khi lookup**; riêng `Locale.lookup(Locale.LanguageRange.parse("*"), supported)` không tự động chọn một locale bất kỳ.

Nếu một range có dấu `*` trong subtag và nhiều ứng viên có cùng mức phù hợp, thứ tự duyệt các ứng viên có thể quyết định ứng viên đầu tiên; nên dùng danh sách khả dụng có thứ tự ổn định và định nghĩa fallback rõ ràng.

## 6. Ví dụ Java 17+ chạy độc lập, đầy đủ bốn phương thức

Ví dụ dưới đây dùng danh sách khả dụng có thứ tự cố định và các range phổ biến để kết quả dễ kiểm chứng. Tạo file **`LocaleMatchingDemo.java`** với nội dung:

```java
import java.util.List;
import java.util.Locale;

public class LocaleMatchingDemo {
    private static List<String> languageTags(List<Locale> locales) {
        return locales.stream().map(Locale::toLanguageTag).toList();
    }

    public static void main(String[] args) {
        List<Locale> available = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("fr-CA")
        );

        List<String> tags = languageTags(available);
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse("fr-CA,fr;q=0.8,en;q=0.5");

        List<Locale> filtered = Locale.filter(preferences, available);
        List<String> filteredTags = Locale.filterTags(preferences, tags);
        Locale bestLocale = Locale.lookup(preferences, available);
        String bestTag = Locale.lookupTag(preferences, tags);

        System.out.println("filter: " + languageTags(filtered));
        System.out.println("filterTags: " + filteredTags);
        System.out.println("lookup: " + (
                bestLocale == null ? "null" : bestLocale.toLanguageTag()));
        System.out.println("lookupTag: " + bestTag);

        List<Locale> availableForFallback = List.of(
                Locale.forLanguageTag("zh-Hant"),
                Locale.forLanguageTag("en-GB")
        );
        List<Locale.LanguageRange> fallbackPreferences =
                Locale.LanguageRange.parse("zh-Hant-HK,en-GB;q=0.7");

        System.out.println("fallback filter: "
                + languageTags(Locale.filter(
                        fallbackPreferences, availableForFallback)));

        Locale fallbackBest =
                Locale.lookup(fallbackPreferences, availableForFallback);
        System.out.println("fallback lookup: " + (
                fallbackBest == null ? "null" : fallbackBest.toLanguageTag()));

        System.out.println("wildcard lookup: "
                + Locale.lookup(
                        Locale.LanguageRange.parse("*"), available));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 LocaleMatchingDemo.java
java LocaleMatchingDemo
```

Stdout:

```text
filter: [fr-CA, fr-FR, en-US, en-GB]
filterTags: [fr-CA, fr-FR, en-US, en-GB]
lookup: fr-CA
lookupTag: fr-CA
fallback filter: [en-GB]
fallback lookup: zh-Hant
wildcard lookup: null
```

Giải thích theo thứ tự:

1. `filter` xem `fr-CA` là ưu tiên cao nhất, sau đó `fr` cho phép lấy thêm `fr-FR`; tiếp theo `en` lấy hai phiên bản tiếng Anh. `fr-CA` không bị lặp lại dù vừa khớp range cụ thể `fr-CA` vừa khớp range `fr`.
2. `filterTags` có cùng tập kết quả, nhưng là chuỗi thay vì `Locale`.
3. `lookup` và `lookupTag` chọn `fr-CA` vì catalog hỗ trợ đúng tag ưu tiên nhất.
4. Với yêu cầu `zh-Hant-HK`, `filter` không xem tag `zh-Hant` là ứng viên dài đủ để khớp range đó; range ưu tiên kế tiếp `en-GB` khớp, nên kết quả filter là `[en-GB]`.
5. `lookup` tiến hành rút gọn `zh-Hant-HK` xuống `zh-Hant` và chọn được một phiên bản phù hợp hơn trước khi xét `en-GB`.
6. Lookup chỉ với `*` trả `null`. Nếu hệ thống muốn luôn có một bản dịch mặc định, phải xác định nó tường minh trong chính sách của sản phẩm.

Ví dụ dùng các API đã tồn tại từ Java 8; `Stream.toList()` là API từ **Java 16**, vì thế tệp này chọn **Java 17+**. Với Java 8–15, thay phần `.toList()` bằng `.collect(java.util.stream.Collectors.toList())` và dùng JDK tương ứng.

## 7. FilteringMode: basic và extended filtering

Một range basic như `de-DE` yêu cầu các subtag liền nhau từ đầu; nó khớp `de-DE` và `de-DE-1996`, nhưng không khớp `de-Latn-DE`.

Extended filtering cho phép wildcard ở giữa, chẳng hạn `de-*-DE` có thể khớp `de-DE`, `de-Deva-DE` và `de-Latn-DE`. Ngay cả với range basic, nếu chủ động chọn `EXTENDED_FILTERING`, mô hình extended có thể trả thêm các tag có script chen giữa language và region.

Các giá trị `Locale.FilteringMode`:

| Mode | Hành vi |
| --- | --- |
| `AUTOSELECT_FILTERING` | Mặc định: chỉ basic range → basic filtering; có ít nhất một extended range → extended filtering |
| `EXTENDED_FILTERING` | Luôn dùng extended filtering |
| `IGNORE_EXTENDED_RANGES` | Bỏ qua các extended range rồi áp dụng basic filtering |
| `MAP_EXTENDED_RANGES` | Chuyển extended range về dạng basic trước khi lọc; `de-*-DE` trở thành `de-DE` |
| `REJECT_EXTENDED_RANGES` | Gặp extended range thì ném `IllegalArgumentException` |

Ví dụ độc lập (đưa các dòng sau vào một phương thức như `main` của Java 17+):

```java
List<String> tags = List.of(
        "de-DE", "de-Deva-DE", "de-Latn-DE", "en-US"
);
List<Locale.LanguageRange> ranges = List.of(
        new Locale.LanguageRange("de-*-DE")
);

System.out.println(Locale.filterTags(
        ranges, tags, Locale.FilteringMode.EXTENDED_FILTERING));
System.out.println(Locale.filterTags(
        ranges, tags, Locale.FilteringMode.MAP_EXTENDED_RANGES));
System.out.println(Locale.filterTags(
        ranges, tags, Locale.FilteringMode.IGNORE_EXTENDED_RANGES));
```

Kết quả:

```text
[de-DE, de-Deva-DE, de-Latn-DE]
[de-DE]
[]
```

Đoạn này là **snippet đặt trong phương thức**, không phải chương trình Java độc lập; nó dùng import `java.util.List` và `java.util.Locale` như ví dụ đầy đủ trước đó. Default `AUTOSELECT_FILTERING` cũng chọn extended filtering trong ví dụ vì có range `de-*-DE`.

**Giới hạn quan trọng:** `FilteringMode` chỉ thuộc họ filtering; nó không biến `lookup` thành filter và không tạo khả năng “đoán đúng tiếng người dùng muốn” ngoài các quy tắc của RFC 4647.

## 8. Thiết kế bộ chọn locale cho ứng dụng

Một luồng xử lý thực tế có thể gồm:

1. **Xác định catalog hỗ trợ thực sự**, ví dụ `List<String> supportedTags = List.of("vi-VN", "en-US", "fr-FR")`. Dùng danh sách có thứ tự cố định. Catalog phải tương ứng những bundle/template có nội dung sử dụng được; `Locale.getAvailableLocales()` không thay thế catalog của ứng dụng.
2. **Xác định nguồn ưu tiên**: locale do người dùng chọn trong hồ sơ thường nên được ưu tiên hơn ngôn ngữ tự động đoán từ browser; nếu cần đọc `Accept-Language`, phân tích `Locale.LanguageRange.parse(...)`. Đừng tự động mặc định header HTTP là yêu cầu bắt buộc vượt mọi lựa chọn của người dùng.
3. **Lựa chọn chiến lược**. Dùng `filterTags`/`filter` nếu cần hiển thị danh sách có thứ tự cho người dùng hoặc xác định mọi bản phù hợp. Dùng `lookupTag`/`lookup` nếu cần một lựa chọn theo cơ chế lookup của RFC 4647.
4. **Xử lý không khớp**. Sau lookup, kiểm tra `null`; sau filter, kiểm tra `isEmpty()`. Chọn fallback từ **catalog hỗ trợ** theo quy tắc sản phẩm, ví dụ `"vi-VN"` là mặc định của một dịch vụ chỉ dành cho người Việt. Đừng tự suy ra `"en-US"` là fallback toàn cầu.
5. **Tải đúng tài nguyên**. Khi đã chọn locale/tag, truyền vào `ResourceBundle` hoặc framework dịch/format tương ứng. Cần kiểm tra key thông điệp còn thiếu và fallback của cơ chế bundle riêng; kết quả matching không đảm bảo mọi key đều đã được dịch.
6. **Kiểm thử các chính sách đặc biệt**. Ví dụ, ứng dụng có thể cần ánh xạ `"en"` sang `"en-US"` nếu catalog chỉ có phiên bản tiếng Anh Mỹ. Đây là **quyết định sản phẩm**, nên cấu hình và kiểm thử tường minh thay vì giả định `lookup("en")` tự chọn `en-US`.

Ví dụ hàm áp dụng `lookupTag` với fallback có kiểm tra:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class SupportedLanguage {
    public static String select(String request, List<String> supported,
                                String defaultTag) {
        Objects.requireNonNull(request);
        Objects.requireNonNull(supported);
        if (!supported.contains(defaultTag)) {
            throw new IllegalArgumentException("Default locale is unsupported");
        }

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(request);
        String choice = Locale.lookupTag(preferences, supported);
        return choice == null ? defaultTag : choice;
    }

    public static void main(String[] args) {
        List<String> supported = List.of("vi-VN", "en-US", "fr-FR");
        System.out.println(select("fr-FR,en-US;q=0.5",
                supported, "vi-VN"));
        System.out.println(select("de-DE",
                supported, "vi-VN"));
    }
}
```

Lưu thành `SupportedLanguage.java`, chạy bằng:

```bash
javac -encoding UTF-8 SupportedLanguage.java
java SupportedLanguage
```

Kết quả:

```text
fr-FR
vi-VN
```

Ở đây catalog là `List<String>`, vì vậy việc chọn bằng `lookupTag` không mất công chuyển sang `Locale` khi mục tiêu chỉ là khóa chuỗi BCP 47. Hàm kiểm tra `defaultTag` thuộc danh sách, bảo đảm fallback không trỏ đến một bản dịch mà chính ứng dụng không hỗ trợ. Trong hệ thống thật, hãy chuẩn hóa và kiểm tra tag, kiểm soát độ dài/số lượng range do client gửi, thống nhất quy tắc so sánh tag và xử lý `IllegalArgumentException` của header không hợp lệ trước khi đưa lựa chọn vào luồng hiển thị.

### Một số vấn đề về chiến lược lựa chọn

**Filter và lookup mang ý nghĩa khác nhau**. Filter hữu ích khi hiển thị tất cả tùy chọn hợp lệ; lookup hữu ích khi tuân theo cách chọn một tag theo RFC 4647. Nếu muốn “chọn phần tử đầu tiên trong danh sách sau khi filter”, cần ghi rõ đó là **chính sách ứng dụng dựa trên filtering**, không gọi nó là `Locale.lookup`.

**Ưu tiên và thứ tự đầu vào**. `LanguageRange.parse` xử lý `q`, nhưng trong trường hợp đồng mức ưu tiên hoặc các wildcard, thứ tự của tập ứng viên có thể ảnh hưởng lựa chọn. Không dùng `HashSet` làm đầu vào nếu sản phẩm cần thứ tự ổn định trong các tình huống đồng hạng. Cũng không được xem trọng số `q` là xác suất hoặc điểm chất lượng bản dịch.

**Không có “dịch gần đúng” tự động**. `fr-FR` và `fr-CA` có thể dùng chung ngôn ngữ nhưng khác biệt thuật ngữ/ngữ cảnh; `zh-Hans` và `zh-Hant` còn khác hệ chữ. Lookup có quy tắc bỏ dần subtag, **không phải mô hình thông minh tự chuyển nội dung hoặc đánh giá nghĩa**. Ứng dụng vẫn cần quyết định chấp nhận variant/region khác đến đâu và kiểm chứng ngôn ngữ trên nội dung.

**Tách locale ra khỏi múi giờ và giao dịch**. Locale được chọn là đầu vào cho việc trình bày. Nó không quyết định `ZoneId` của người dùng hay tiền tệ thực tế của đơn hàng; các ràng buộc nghiệp vụ phải được xử lý riêng.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Lấy `filter(...).get(0)` và gọi đó là lookup | Sai quy tắc rút gọn subtag, có thể chọn phiên bản không mong muốn | Chọn đúng một trong hai cơ chế và kiểm thử kết quả |
| Cho rằng `lookup("en")` sẽ tìm `en-US` khi chỉ có `en-US` | Có thể nhận `null` do lookup không mở rộng yêu cầu `en` thành `en-US` | Định nghĩa fallback rõ ràng hoặc đưa bản `en` vào catalog |
| Dùng `Locale.US` khi muốn diễn tả mọi tiếng Anh | Áp đặt region US | Dùng range `en` khi cần tất cả tiếng Anh; chọn region khi cần cụ thể |
| Truyền `List<String>` cho `filter` | Không đúng kiểu tham số | Dùng `filterTags` hoặc chuyển thành `List<Locale>` |
| Nhận `null` từ lookup rồi gọi `toLanguageTag()` ngay | `NullPointerException` | Kiểm tra `null` và fallback có kiểm soát |
| Giả định filter không bao giờ rỗng | Không có bản dịch đáp ứng mà UI vẫn xử lý như có | Kiểm tra `isEmpty()` |
| Quên thứ tự ưu tiên/trọng số | Kết quả sai ý định người dùng | Dùng `LanguageRange.parse` hoặc danh sách đã sắp rõ ràng |
| Dùng range extended với `REJECT_EXTENDED_RANGES` | `IllegalArgumentException` | Chọn mode phù hợp, hoặc giới hạn cú pháp đầu vào |
| Cho rằng `*` trong lookup là mặc định tự động | Lookup có thể trả `null` | Xác định default tag từ catalog ứng dụng |
| Trộn language tag với tên hiển thị hoặc `toString()` | Sai dạng BCP 47 khi matching | Dùng `toLanguageTag()`, `forLanguageTag()` |
| Đưa `Locale.getAvailableLocales()` vào catalog dịch | Hiển thị ngôn ngữ ứng dụng chưa dịch | Quản lý danh sách nội dung được hỗ trợ độc lập |
| Không khống chế dữ liệu từ client | Header rác hoặc dài gây lỗi parser/tiêu tốn tài nguyên | Giới hạn input, bắt lỗi và fallback theo chính sách |

## 10. Bài tập tự kiểm tra

**Bài 1.** Catalog gồm `[en-US, en-GB, fr-FR]`; priority list chỉ là `en`. Kết quả `filter` và `lookup`?

**Đáp án:** `filter` trả `[en-US, en-GB]`; `lookup` trả `null` vì không có tag `en`. Cần fallback ứng dụng nếu muốn chọn một phiên bản tiếng Anh.

**Bài 2.** Catalog gồm `[zh-Hant, en-US]`; priority list `zh-Hant-TW,en-US;q=0.5`. Vì sao kết quả lookup khác filter?

**Đáp án:** Lookup cắt `zh-Hant-TW` xuống `zh-Hant` và chọn được tag ấy; filter không chọn `zh-Hant` cho range dài hơn `zh-Hant-TW`, nên có thể chọn `en-US` ở range tiếp theo.

**Bài 3.** Khi catalog là các chuỗi `"vi-VN"`, `"en-US"`, `"fr-FR"`, muốn một chuỗi tag tốt nhất phải dùng phương thức nào?

**Đáp án:** `Locale.lookupTag(priorityList, tags)`, sau đó kiểm tra `null`. Nếu cần mọi tag phù hợp, dùng `Locale.filterTags`.

**Bài 4.** Nếu range có dạng `de-*-DE` thì mode nào tự dùng extended filtering?

**Đáp án:** `AUTOSELECT_FILTERING`. Dùng `REJECT_EXTENDED_RANGES` sẽ ném `IllegalArgumentException`. Dùng `MAP_EXTENDED_RANGES` chuyển về `de-DE` rồi thực hiện basic filtering.

**Bài 5.** `Locale.lookupTag(...)` trả `null`. Có nên mặc định `en-US` không?

**Đáp án:** Chỉ khi đó là fallback được **sản phẩm định nghĩa và hỗ trợ thật**. Không có locale fallback chung cho mọi ứng dụng.

## 11. Ghi nhớ và tài liệu

- `filter`/`filterTags` trả về **tất cả** các locale/tag phù hợp theo cơ chế filtering; khi không khớp trả danh sách rỗng.
- `lookup`/`lookupTag` chọn **một** locale/tag theo cơ chế lookup và có thể rút gọn subtag; khi không khớp trả `null`.
- Cả bốn nhận `List<Locale.LanguageRange>` làm tiêu chí. Dùng `LanguageRange.parse(...)` để xử lý danh sách ưu tiên có trọng số `q`.
- Chỉ `filter`/`filterTags` có `FilteringMode`. Chế độ mặc định tự chọn basic/extended dựa trên loại language range.
- Hãy cung cấp catalog thực sự được hỗ trợ, đầu vào có thứ tự ổn định, fallback rõ ràng và kiểm thử những trường hợp không khớp hoặc người dùng yêu cầu ngôn ngữ chung.

Tài liệu chính thức:

- [Java SE 21 — Locale và Locale Matching](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Java SE 21 — Locale.FilteringMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.FilteringMode.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647)
