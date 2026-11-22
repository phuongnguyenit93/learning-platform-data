# Locale.LanguageRange và thứ tự ưu tiên ngôn ngữ trong Java 8+

> **Chủ đề cha:** Ngôn ngữ và locale. Khi ứng dụng hỗ trợ nhiều bản dịch, người dùng có thể gửi danh sách ngôn ngữ theo độ ưu tiên (ví dụ HTTP `Accept-Language: vi-VN, en-US;q=0.8, en;q=0.6`). `java.util.Locale.LanguageRange` biểu diễn **một phạm vi ngôn ngữ có trọng số**. `Locale.LanguageRange.parse`, `Locale.filter`/`filterTags` và `Locale.lookup`/`lookupTag` so khớp các ưu tiên với những ngôn ngữ **ứng dụng thật sự hỗ trợ**. Đây là API từ Java 8, triển khai cơ chế language matching của RFC 4647 và vẫn còn áp dụng trên JDK hiện đại.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt `Locale` với `Locale.LanguageRange` và BCP 47 language tags.
2. Đọc một *Language Priority List* từ HTTP `Accept-Language` hoặc chuỗi tùy chọn, hiểu trọng số `q`.
3. Tạo/đọc `LanguageRange` bằng constructor, `parse`, `getRange`, `getWeight`, `MIN_WEIGHT` và `MAX_WEIGHT`.
4. Giải thích vì sao thứ tự ưu tiên **theo q giảm dần**, không nhất thiết bằng thứ tự xuất hiện trong header.
5. Dùng `filter/filterTags` để lấy **nhiều** candidate và `lookup/lookupTag` để chọn **một** candidate tốt nhất.
6. Phân biệt basic/extended ranges, `Locale.FilteringMode` và wildcard `*`.
7. Xử lý `q=0`, danh sách không khớp, input sai cú pháp, duplicates và alias ranges.
8. Thiết kế fallback rõ ràng dựa trên tập ngôn ngữ có sẵn, không dựa vào JVM default.
9. Không nhầm language negotiation với quyền truy cập, timezone, quốc gia, resource loading hay định dạng tiền tệ.
10. Chạy một chương trình Java 8 hoàn chỉnh có kiểm thử parse, filter, lookup, extended modes, custom equivalents và fallback.

## 2. Locale, language tag và language range

`Locale` đại diện cấu hình ngôn ngữ/vùng/script/extension để dùng cho internationalization. `Locale.toLanguageTag()` xuất một BCP 47 language tag như `vi-VN`, `en-US`, `en-GB` hoặc `zh-Hant-TW`.

```java
Locale vn = Locale.forLanguageTag("vi-VN");
Locale uk = Locale.forLanguageTag("en-GB");
System.out.println(vn.toLanguageTag()); // vi-VN.
System.out.println(uk.getLanguage());    // en.
```

`Locale.LanguageRange` thì là **một pattern chọn ngôn ngữ**, có thể khớp nhiều tags. Ví dụ `"en"` khớp những tags tiếng Anh như `"en-US"`, `"en-GB"`. `"zh-*-TW"` chứa wildcard giữa các subtags, là extended range.

```java
Locale.LanguageRange wanted =
        new Locale.LanguageRange("en", 0.8);

String range = wanted.getRange();  // "en".
double weight = wanted.getWeight(); // 0.8.
```

Các vai trò khác nhau:

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| BCP 47 language tag | `en-US` | Mô tả ngôn ngữ/vùng |
| `Locale` | `Locale.forLanguageTag("en-US")` | Dùng ở formatter/resource API |
| `Locale.LanguageRange` | `new LanguageRange("en",0.8)` | Pattern và mức ưu tiên |
| Language Priority List | `en-GB,vi;q=0.7,en;q=0.5` | Nhiều ngôn ngữ muốn chọn theo thứ tự |
| Supported tags | `[vi-VN,en-US,en-GB]` | Tập bản dịch thực có trong ứng dụng |
| `lookup` | Trả một `Locale` hoặc `null` | Chọn best candidate |
| `filter` | Trả danh sách `Locale` | Tìm tất cả candidate phù hợp |

Một `LanguageRange` **không chứng minh** ứng dụng có resource tương ứng. Quyền quyết định danh sách hỗ trợ thuộc server/app.

## 3. Danh sách ưu tiên và trọng số `q`

Dạng HTTP ví dụ:

```http
Accept-Language: vi-VN, en-US;q=0.8, en;q=0.6, fr;q=0.4
```

| Range | Trọng số | Ý nghĩa |
| --- | ---: | --- |
| `vi-VN` | 1.0 mặc định | Ưu tiên cao nhất |
| `en-US;q=0.8` | 0.8 | Tiếng Anh/Mỹ sau vi-VN |
| `en;q=0.6` | 0.6 | Chấp nhận nhiều locale tiếng Anh |
| `fr;q=0.4` | 0.4 | Tiếng Pháp ưu tiên thấp hơn |

`Locale.LanguageRange.MAX_WEIGHT` là 1.0 và `MIN_WEIGHT` là 0.0. `q` nằm từ 0 đến 1; thiếu `q` tương đương 1.0. Trong matching, `q=0` thể hiện range **không được chấp nhận**. Giá trị lớn hơn được ưu tiên trước.

Dù chuỗi input không xếp theo q, `Locale.LanguageRange.parse` trả priority list được sắp theo **trọng số giảm dần**:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse(
                "fr;q=0.2, vi;q=0.8, en;q=1.0");
// Kết quả có thứ tự en (1.0), vi (0.8), fr (0.2).
```

Nếu nhiều items có q bằng nhau, đừng tùy tiện diễn giải chúng là một chính sách “đúng quốc gia” hoặc một ranking cố định vượt ngoài hợp đồng API. Nếu cần tie-break theo sản phẩm, quy định rõ ở tầng ứng dụng và dùng collection input ổn định.

### 3.1. q không phải chất lượng bản dịch

`q=0.8` phản ánh **ý muốn** của người dùng, không có nghĩa bản dịch chính xác 80%, người dùng cư trú tại đó hoặc muốn dùng đồng tiền của quốc gia đó. Locale/region, currency, legal jurisdiction, timezone và authorization cần được model hóa riêng.

## 4. `Locale.LanguageRange.parse`

Chữ ký được hỗ trợ:

```java
static List<Locale.LanguageRange> parse(String ranges);

static List<Locale.LanguageRange> parse(
        String ranges, Map<String,List<String>> map);
```

Đầu vào chấp nhận chuỗi ranges phân cách bằng dấu phẩy hoặc dạng có tiền tố `Accept-Language:`:

```java
List<Locale.LanguageRange> a = Locale.LanguageRange.parse(
        "vi-VN, en-US;q=0.8, en;q=0.6");

List<Locale.LanguageRange> b = Locale.LanguageRange.parse(
        "Accept-Language: vi-VN, en-US;q=0.8, en;q=0.6");
```

Framework HTTP thường đã trả riêng **giá trị** header, không chứa prefix `Accept-Language:`. Khi đó chỉ cần đưa giá trị vào `parse`; không tự thêm tên header lần nữa.

### 4.1. Lấy range và q bằng getter

```java
for (Locale.LanguageRange r : a) {
    String normalizedRange = r.getRange();
    double q = r.getWeight();
    // Sử dụng dữ liệu có kiểu.
}
```

`getRange()` thường trả range đã chuẩn hóa chữ thường, ví dụ `"en-gb"`. `getWeight()` trả trọng số số học. `toString()` có ích cho debug, nhưng không nên dùng chuỗi hiển thị rồi split thành một protocol riêng.

### 4.2. Syntax hợp lệ khác resource thực có

`parse` kiểm tra cú pháp range/weight nhưng **không xác minh với toàn bộ IANA Language Subtag Registry** và không kiểm tra bản dịch trên server.

```java
Locale.LanguageRange.parse("en;q=1.5");
// IllegalArgumentException: weight ngoài [0,1].

Locale.LanguageRange.parse("en_US");
// IllegalArgumentException: underscore không hợp lệ.
```

BCP 47 và language range sử dụng dấu nối `-`; không biến kiểu hiển thị `Locale.toString()` có dấu underscore thành một HTTP language tag tùy tiện. Với dữ liệu trusted, `Locale.toLanguageTag()` giúp chuẩn hóa format BCP 47.

### 4.3. Constructor và constants

```java
Locale.LanguageRange english = new Locale.LanguageRange("en", 0.7);
Locale.LanguageRange vietnamese = new Locale.LanguageRange("vi");

double maxWeight = Locale.LanguageRange.MAX_WEIGHT; // 1.0.
double minWeight = Locale.LanguageRange.MIN_WEIGHT; // 0.0.
```

Constructor cũng kiểm tra range/weight. Không kỳ vọng `new LanguageRange("en",2.0)` tự kẹp thành 1.0. Trước khi parse input ngoài, nên áp dụng giới hạn kích thước và số mục theo chính sách API của ứng dụng.

### 4.4. Duplicate và equivalent language ranges

`parse` loại trùng các range theo quy tắc API; thêm cùng range hai lần không phải là hai lá phiếu để cộng q. Java còn có cơ chế mở rộng các **equivalent ranges** được biết cho một số mã ngôn ngữ/alias. Do đó với một số input có mã cũ/tên mới, danh sách có thể có **nhiều phần tử hơn số mục ban đầu**; đừng hard-code size từ số dấu phẩy nếu input không bị giới hạn.

Sự tương đương của language ranges **không có nghĩa** chắc chắn có một bản dịch tương đương ở server. Bạn vẫn phải so khớp với tập supported tags thực tế.

## 5. Filtering: `filterTags` / `filter`

**Filtering** lấy **tất cả** candidate khớp các ranges trong priority list, theo độ ưu tiên. Ví dụ server hỗ trợ:

```java
List<String> supported = Arrays.asList(
        "vi-VN", "en-US", "en-GB", "fr-FR", "ja-JP");

List<Locale.LanguageRange> wanted =
        Locale.LanguageRange.parse(
                "en-GB, vi-VN;q=0.9, en;q=0.7, fr;q=0.4");

List<String> matching = Locale.filterTags(wanted, supported);
// [en-GB, vi-VN, en-US, fr-FR].
```

Giải thích:
- `en-GB` có q=1.0 nên đứng đầu.
- `vi-VN` q=0.9 đứng tiếp.
- `en` q=0.7 khớp thêm `en-US`; `en-GB` đã có, không lặp lại.
- `fr` q=0.4 khớp `fr-FR`.
- `ja-JP` không có range khớp, nên không xuất hiện.

`Locale.filterTags` trả `List<String>`, giữ cách viết tag của các candidate được chọn và loại các kết quả trùng theo hợp đồng. `Locale.filter` làm điều tương đương trên `Collection<Locale>` và trả `List<Locale>`:

```java
List<Locale> supportedLocales = Arrays.asList(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"),
        Locale.forLanguageTag("en-GB"),
        Locale.forLanguageTag("fr-FR"));

List<Locale> matchingLocales =
        Locale.filter(wanted, supportedLocales);
```

Nếu UI muốn hiển thị nhiều tùy chọn tương thích, hoặc ứng dụng muốn danh sách tags phù hợp, dùng `filter`. Nó **không** phải lựa chọn ngôn ngữ đơn duy nhất.

### 5.1. Matching không phân biệt chữ hoa/thường

`"en-us"` có thể khớp `"en-US"`; kết quả `filterTags` vẫn có thể giữ cách viết từ input supported tag. Với các tags trùng chỉ khác case, collection có thứ tự không ổn định như `HashSet` có thể khiến biến thể case được giữ không dự đoán được. Hãy chuẩn hóa supported tags từ cấu hình trusted và ưu tiên danh sách `List` rõ thứ tự nếu muốn output/test ổn định.

## 6. Lookup: `lookupTag` / `lookup`

**Lookup** chọn một candidate tốt nhất theo ưu tiên RFC 4647:

```java
String bestTag = Locale.lookupTag(wanted, supported);
// "en-GB".

Locale bestLocale =
        Locale.lookup(wanted, supportedLocales);
// Locale đại diện "en-GB".
```

`lookupTag` trả `String`, `lookup` trả `Locale`; **cả hai có thể trả `null`** khi không khớp. Không nhầm `lookup` với `filter(...).get(0)`: filtering và lookup là hai thuật toán RFC 4647 khác nhau, có thể cho kết quả khác ở các tình huống đặc hiệu/script/region.

### 6.1. Lookup giảm dần mức cụ thể

Nếu request là `zh-Hant-TW`, thuật toán lookup có thể tìm `zh-Hant-TW` trước, rồi các mức rút gọn như `zh-Hant`, `zh`, sau đó mới thử language range ưu tiên thấp hơn, theo quy tắc RFC 4647.

Matching dựa trên **subtag boundaries**, không phải so sánh `startsWith("en")` tùy tiện. `en` không phải mọi chuỗi bắt đầu bằng ba ký tự đó; sử dụng API thay vì tự viết thuật toán prefix.

### 6.2. Fallback phải rõ ràng

```java
String missing = Locale.lookupTag(
        Locale.LanguageRange.parse("ko-KR"), supported);
// null.

String selected = missing != null ? missing : "en-US";
// Chọn default của app; giả sử en-US có trong supported.
```

Không suy đoán “người dùng chắc chắn muốn tiếng Anh” khi lookup thất bại. Server phải định nghĩa một default **có bản dịch thực**, phù hợp sản phẩm và hợp đồng HTTP. `Locale.getDefault()` của JVM không nhất thiết là default mong muốn và có thể khác giữa các môi trường triển khai.

### 6.3. Wildcard `*` khác nhau giữa hai thuật toán

`*` là range đặc biệt: trong **lookup**, nó bị **bỏ qua**; nếu chỉ có wildcard, kết quả lookup có thể là `null`:

```java
String selected = Locale.lookupTag(
        Locale.LanguageRange.parse("*"), supported);
// null.
```

Trong **filtering**, wildcard có nghĩa chọn một tập matching rộng theo quy tắc filter. Không coi wildcard luôn đồng nghĩa “lấy language đầu tiên trong supported”. Chọn fallback explicit khi cần một kết quả đơn.


## 7. Basic, extended range và FilteringMode

| Kiểu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Basic range | `en`, `en-US`, `vi-VN`, `*` | Một dãy subtags cơ bản hoặc wildcard toàn phần |
| Extended range | `zh-*-TW`, `zh-Hant-*`, `*-CH` | Wildcard có thể nằm giữa/vị trí subtag |

Java cung cấp `Locale.FilteringMode`:

- `AUTOSELECT_FILTERING`: chế độ mặc định; dùng basic filtering nếu danh sách chỉ có basic ranges, nếu có extended ranges thì chọn extended filtering.
- `EXTENDED_FILTERING`: luôn dùng extended filtering.
- `IGNORE_EXTENDED_RANGES`: bỏ qua extended ranges trong danh sách.
- `MAP_EXTENDED_RANGES`: ánh xạ extended ranges về dạng basic theo quy tắc của API.
- `REJECT_EXTENDED_RANGES`: từ chối extended ranges bằng `IllegalArgumentException`.

Ví dụ:

```java
List<String> chineseTags = Arrays.asList(
        "zh-Hant-TW", "zh-TW", "zh-Hans-CN", "en-US");

List<Locale.LanguageRange> requested =
        Locale.LanguageRange.parse("zh-*-TW");

List<String> matches = Locale.filterTags(
        requested, chineseTags,
        Locale.FilteringMode.EXTENDED_FILTERING);
// [zh-Hant-TW, zh-TW].
```

Ở đây range kết thúc bằng `TW` chấp nhận cả `zh-Hant-TW` và `zh-TW` theo extended filtering. `zh-Hans-CN` không khớp. Một cách tự kiểm tra `tag.startsWith("zh-")` sẽ không bảo toàn đầy đủ script/region constraints.

Nếu endpoint chỉ cho phép basic ranges:

```java
try {
    Locale.filterTags(
        requested, chineseTags,
        Locale.FilteringMode.REJECT_EXTENDED_RANGES);
    throw new AssertionError("Expected exception");
} catch (IllegalArgumentException expected) {
    // Range extended bị từ chối theo policy.
}
```

**Chú ý:** Những snippet có `wanted`, `supported`, `chineseTags`... là đoạn học độc lập trong ngữ cảnh đã mô tả, không phải tất cả đều là file biên dịch riêng. Chương trình `LanguagePriorityDemo.java` phía sau có class và import đầy đủ.

## 8. `q=0`, duplicates và các góc cạnh

### 8.1. q=0 không có nghĩa “ưu tiên thấp nhưng vẫn chấp nhận”

```java
List<Locale.LanguageRange> none =
        Locale.LanguageRange.parse("fr;q=0");

List<String> offered = Arrays.asList("fr-FR", "en-US");

List<String> filtered = Locale.filterTags(none, offered);
// [].
```

`q=0` là mức trọng số tối thiểu và kết quả filter mẫu không chọn `fr-FR`. Với HTTP clients, q=0 thường được dùng để nói “không chấp nhận ngôn ngữ này”. Không bỏ q=0 khi tự viết thuật toán matching.

### 8.2. Duplicate range không phải một “phiếu bầu” mới

`Locale.LanguageRange.parse("fr,fr;q=0.2,en")` không nên được tính như hai preferences tiếng Pháp khác nhau. API loại các range trùng theo chính sách parse. Nếu doanh nghiệp cần preference histories hay tie-break cụ thể, lưu riêng mô hình dữ liệu ấy.

### 8.3. List rỗng, input null, invalid syntax

Các method `LanguageRange.parse` / `Locale.lookupTag` / `filterTags` có hợp đồng exception/return rõ. `parse(null)` dẫn tới `NullPointerException`, còn range/weight ill-formed dẫn tới `IllegalArgumentException`. Khi không có candidate khớp, `lookupTag` trả `null` và `filterTags` trả list rỗng. Kiểm tra null/empty header **trước** parse, rồi lựa chọn fallback hoặc phản hồi lỗi theo chính sách API.

Đừng dùng `get(0)` trên danh sách filter không kiểm tra rỗng. Đừng lấy `Locale.forLanguageTag` làm công cụ xác thực đầy đủ mọi mã ngôn ngữ từ header: việc chọn `Locale` và việc parse/filter ranges có hợp đồng khác nhau.

### 8.4. q không xác định country/timezone

Một người dùng có thể yêu cầu `en-GB` trong khi đang dùng múi giờ Châu Á. `Accept-Language` không xác định đơn vị tiền, nơi cư trú, giờ địa phương, hay quyền truy cập. Không dùng preference header như một security boundary.

## 9. Custom language equivalents

`Locale.LanguageRange.mapEquivalents` có thể tạo priority list mới từ một map tương đương theo **chính sách ứng dụng**.

```java
Map<String, List<String>> equivalents = new LinkedHashMap<>();
equivalents.put("es", Arrays.asList("es", "es-mx"));

List<Locale.LanguageRange> custom =
        Locale.LanguageRange.mapEquivalents(
                Locale.LanguageRange.parse("es,en;q=0.8"),
                equivalents);
// Ranges trong ví dụ: es, es-mx, en.
```

Mapping `es → es/es-mx` là **ví dụ tùy biến** chứ không phải quy tắc bắt buộc mọi website. Có overload `parse(String, Map)` cũng áp dụng mapping trong quá trình parse. Đừng mở rộng range theo alias nội bộ mà chưa có sự đồng ý của product language policy.

**Tương đương ngôn ngữ không tự tạo resource bundle.** Phạm vi mở rộng vẫn phải được khớp với tập supported locales của ứng dụng; việc có `es-mx` trong priority list không khiến file dịch tiếng Mexico tự xuất hiện.

## 10. Locale mặc định của JVM không đại diện user request

```java
Locale jvmDefault = Locale.getDefault();
Locale displayDefault =
        Locale.getDefault(Locale.Category.DISPLAY);
Locale formatDefault =
        Locale.getDefault(Locale.Category.FORMAT);
```

Đây là cài đặt môi trường JVM, không phải preferences riêng của mỗi request. **Không gọi `Locale.setDefault` mỗi khi nhận một HTTP request** để đổi ngôn ngữ: đó là thiết lập dùng chung, có thể ảnh hưởng threads/requests khác.

Sau khi lookup chọn `selectedLocale`, truyền nó vào formatter/resource:
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(selectedLocale)` để hiển thị ngày.
- `NumberFormat.getNumberInstance(selectedLocale)` để format số.
- `ResourceBundle.getBundle(baseName, selectedLocale)` hoặc hệ thống message bundle của app để lấy chuỗi dịch.

**ResourceBundle có cơ chế fallback khác**, không tự được `Locale.lookup` vận hành. Nếu translation key thiếu trong bundle đã chọn, app cần một fallback resource/key riêng. Locale cho ngôn ngữ cũng không tự đặt timezone cho từng người dùng.

## 11. Chọn ngôn ngữ trong HTTP/API production

Giả sử server quản trị bộ hỗ trợ:
`[vi-VN, en-US, en-GB, fr-FR, ja-JP]`.
Một luồng lựa chọn rõ ràng là:

```text
HTTP Accept-Language (không tin cậy)
    |
    v
Giới hạn độ dài header / số ranges
    |
    v
Locale.LanguageRange.parse(header)
    |
    v
Locale.lookupTag(priorityList, SUPPORTED_TAGS)
    |
    +-- Có match => dùng supported tag đó
    +-- Không match => explicit fallback của ứng dụng
    |
    v
Chọn resource/formatter và response Content-Language
```

### 11.1. Ví dụ negotiation có fallback

```java
private static final List<String> SUPPORTED =
        Collections.unmodifiableList(Arrays.asList(
                "vi-VN", "en-US", "en-GB", "fr-FR", "ja-JP"));
private static final String DEFAULT_TAG = "en-US";

static String negotiate(String header) {
    if (header == null || header.trim().isEmpty()) {
        return DEFAULT_TAG;
    }
    try {
        List<Locale.LanguageRange> requested =
                Locale.LanguageRange.parse(header);
        String selected = Locale.lookupTag(requested, SUPPORTED);
        return selected == null ? DEFAULT_TAG : selected;
    } catch (IllegalArgumentException malformed) {
        return DEFAULT_TAG;
    }
}
```

Snippet trên cần đặt trong một class với import `java.util.*`. Nó chỉ minh họa fallback: API strict có thể từ chối input lỗi bằng 400 thay vì fallback. **Giới hạn header length và số ranges trước khi parse** để tránh request quá lớn. Trong production, `DEFAULT_TAG` phải có trong supported tags và được tích hợp với chính sách profile/URL/header của ứng dụng.

### 11.2. Một số nguyên tắc vận hành

- **Tập supported** phải đến từ cấu hình có bản dịch thật; không cho user đưa một header bất kỳ rồi chọn file path/SQL resource trực tiếp từ raw input.
- **Explicit preference** từ user profile/URL có thể ưu tiên hơn HTTP header, nếu product quy định như vậy. Định nghĩa thứ tự một lần thay vì mỗi endpoint làm khác nhau.
- **Response metadata** nên phản ánh ngôn ngữ thực tế được chọn, có thể dùng HTTP `Content-Language`. Khi cache nội dung theo ngôn ngữ, cân nhắc `Vary: Accept-Language` và key cache được chuẩn hóa; tránh tạo key riêng cho mọi tổ hợp chuỗi header vô hạn.
- **Privacy:** Không ghi toàn bộ Accept-Language header vào log nếu không cần; danh sách preferences có thể hé lộ thông tin không thiết yếu.
- **Error handling:** Header ill-formed có thể báo lỗi hoặc fallback; không gây NPE hoặc 500 không kiểm soát. Khi không khớp, `lookupTag` trả null chứ không tự chọn một bản dịch.
- **Kiểm thử bằng supported tags thực tế:** Đừng chỉ test en/vi nếu ứng dụng có nhiều script, region, aliases hoặc tags có extension.

## 12. Bài toán thực tế và cách chọn API

| Nhu cầu | API/thiết kế phù hợp |
| --- | --- |
| Đọc chuỗi `Accept-Language` | `Locale.LanguageRange.parse` |
| Chỉ một bản dịch tốt nhất | `Locale.lookup/lookupTag` + fallback |
| Danh sách tất cả ngôn ngữ tương thích | `Locale.filter/filterTags` |
| BCP 47 string → Locale | `Locale.forLanguageTag` |
| Locale → BCP 47 string | `Locale.toLanguageTag` |
| Có `zh-*-TW` hoặc `*-CH` | `Locale.filter` với FilteringMode thích hợp |
| Chỉ cho basic ranges | `REJECT_EXTENDED_RANGES` (hoặc policy xác thực) |
| Mở rộng alias theo quy tắc riêng | `LanguageRange.mapEquivalents` |
| Chọn resource đã dịch | ResourceBundle/app resource layer sau negotiation |
| Chọn timezone/currency/business region | Nguồn dữ liệu riêng; không suy từ language weight |
| Có header lỗi/không match | Validation và default đã được product quyết định |

## 13. Chương trình Java 8 hoàn chỉnh

Chương trình bên dưới sử dụng **các supported tags có thứ tự cố định** để output xác định. Nó kiểm tra: parse prefix HTTP; q; filter và lookup; filter extended; reject extended; q=0; wildcard lookup; không khớp; fallback; custom equivalents; từ chối cú pháp sai. Không phụ thuộc máy chủ HTTP hay Locale mặc định của JVM.

**Lưu vào `LanguagePriorityDemo.java`:**


```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class LanguagePriorityDemo {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static String showRanges(List<Locale.LanguageRange> ranges) {
        return ranges.stream()
                .map(r -> r.getRange() + "=" + r.getWeight())
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        String acceptLanguage =
                "Accept-Language: en-GB, vi-VN;q=0.9, en;q=0.7, fr;q=0.4";
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(acceptLanguage);
        List<String> supported = Arrays.asList(
                "vi-VN", "en-US", "en-GB", "fr-FR", "ja-JP");
        List<String> filtered = Locale.filterTags(preferences, supported);
        String selectedTag = Locale.lookupTag(preferences, supported);

        List<Locale> availableLocales = supported.stream()
                .map(Locale::forLanguageTag)
                .collect(Collectors.toList());
        Locale filteredLocale = Locale.lookup(
                preferences, availableLocales);

        List<Locale.LanguageRange> sorted = Locale.LanguageRange.parse(
                "fr;q=0.2, vi;q=0.8, en;q=1.0");
        List<String> extendedCandidates = Arrays.asList(
                "zh-Hant-TW", "zh-TW", "zh-Hans-CN", "en-US");
        List<String> extended = Locale.filterTags(
                Locale.LanguageRange.parse("zh-*-TW"),
                extendedCandidates,
                Locale.FilteringMode.EXTENDED_FILTERING);

        boolean rejectedExtended = false;
        try {
            Locale.filterTags(
                    Locale.LanguageRange.parse("zh-*-TW"),
                    extendedCandidates,
                    Locale.FilteringMode.REJECT_EXTENDED_RANGES);
        } catch (IllegalArgumentException expected) {
            rejectedExtended = true;
        }

        List<String> qZero = Locale.filterTags(
                Locale.LanguageRange.parse("fr;q=0"),
                supported);
        String wildcardLookup = Locale.lookupTag(
                Locale.LanguageRange.parse("*"), supported);
        String missing = Locale.lookupTag(
                Locale.LanguageRange.parse("ko-KR"), supported);
        String fallback = missing != null ? missing : "en-US";

        Map<String, List<String>> equivalents = new LinkedHashMap<>();
        equivalents.put("es", Arrays.asList("es", "es-mx"));
        List<Locale.LanguageRange> customized =
                Locale.LanguageRange.mapEquivalents(
                        Locale.LanguageRange.parse("es,en;q=0.8"),
                        equivalents);
        List<String> customTags = customized.stream()
                .map(Locale.LanguageRange::getRange)
                .collect(Collectors.toList());

        boolean invalidWeight = false;
        try {
            Locale.LanguageRange.parse("en;q=1.5");
        } catch (IllegalArgumentException expected) {
            invalidWeight = true;
        }
        boolean invalidUnderscore = false;
        try {
            Locale.LanguageRange.parse("en_US");
        } catch (IllegalArgumentException expected) {
            invalidUnderscore = true;
        }

        System.out.println("Parsed: " + showRanges(preferences));
        System.out.println("Weight of vi-VN: "
                + preferences.get(1).getWeight());
        System.out.println("Filtered tags: " + filtered);
        System.out.println("Lookup tag: " + selectedTag);
        System.out.println("Lookup locale: "
                + filteredLocale.toLanguageTag());
        System.out.println("Sorted weights: " + showRanges(sorted));
        System.out.println("Extended filter: " + extended);
        System.out.println("Reject extended: " + rejectedExtended);
        System.out.println("q=0 filter: " + qZero);
        System.out.println("Wildcard lookup: " + wildcardLookup);
        System.out.println("Missing lookup: " + missing);
        System.out.println("Explicit fallback: " + fallback);
        System.out.println("Custom equivalents: " + customTags);
        System.out.println("Invalid weight rejected: " + invalidWeight);
        System.out.println("Invalid underscore rejected: "
                + invalidUnderscore);

        require(preferences.size() == 4, "Unexpected range count");
        require("en-gb".equals(preferences.get(0).getRange()),
                "Unexpected first preference");
        require(preferences.get(1).getWeight() == 0.9,
                "Unexpected q-value");
        require(filtered.equals(Arrays.asList(
                        "en-GB", "vi-VN", "en-US", "fr-FR")),
                "Unexpected filtering");
        require("en-GB".equals(selectedTag), "Unexpected lookupTag");
        require("en-GB".equals(filteredLocale.toLanguageTag()),
                "Unexpected lookup");
        require(sorted.get(0).getRange().equals("en")
                && sorted.get(1).getRange().equals("vi")
                && sorted.get(2).getRange().equals("fr"),
                "Weight order not descending");
        require(extended.equals(Arrays.asList(
                        "zh-Hant-TW", "zh-TW")),
                "Unexpected extended filtering");
        require(rejectedExtended, "Extended ranges not rejected");
        require(qZero.isEmpty(), "q=0 must not be offered");
        require(wildcardLookup == null && missing == null,
                "Expected no exact lookup");
        require("en-US".equals(fallback), "Wrong fallback");
        require(customTags.equals(Arrays.asList(
                        "es", "es-mx", "en")),
                "Incorrect custom equivalents");
        require(invalidWeight && invalidUnderscore,
                "Invalid input was not rejected");
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 17+ ở chế độ hỗ trợ Java 8 hoặc dùng compiler JDK 8:

```bash
javac --release 8 LanguagePriorityDemo.java
java LanguagePriorityDemo
```

**Stdout đã chạy và kiểm chứng trên OpenJDK 24:**


```text
Parsed: en-gb=1.0, vi-vn=0.9, en=0.7, fr=0.4
Weight of vi-VN: 0.9
Filtered tags: [en-GB, vi-VN, en-US, fr-FR]
Lookup tag: en-GB
Lookup locale: en-GB
Sorted weights: en=1.0, vi=0.8, fr=0.2
Extended filter: [zh-Hant-TW, zh-TW]
Reject extended: true
q=0 filter: []
Wildcard lookup: null
Missing lookup: null
Explicit fallback: en-US
Custom equivalents: [es, es-mx, en]
Invalid weight rejected: true
Invalid underscore rejected: true
Checks passed.
```

### 13.1. Giải thích stdout

- `Parsed` hiển thị thứ tự ranges và q sau parsing; `getRange()` chuẩn hóa chữ thường. `vi-vn` có q=0.9, `en-gb` có q=1.0 vì không khai báo.
- `Filtered tags` trả bốn tags theo ưu tiên đã thử, trong đó `en-US` khớp range `en` chung; `ja-JP` không khớp.
- `Lookup tag` và `Lookup locale` đều chọn `en-GB`, vì nó khớp range có q cao nhất.
- `Sorted weights` chứng minh `parse` sắp theo q giảm dần ngay cả khi chuỗi gốc liệt kê `fr` trước.
- `Extended filter` chọn `zh-Hant-TW` và `zh-TW`. `REJECT_EXTENDED_RANGES` ném `IllegalArgumentException` được chương trình kiểm tra.
- `q=0 filter` rỗng; `Wildcard lookup` và `Missing lookup` là null. `Explicit fallback` chọn `en-US` theo rule do ứng dụng giả định.
- `Custom equivalents` hiển thị list sau khi áp dụng mapping ứng dụng `es -> [es,es-mx]`.
- Hai input `en;q=1.5` và `en_US` bị từ chối vì không hợp lệ. `Checks passed` chỉ in khi tất cả điều kiện được xác nhận qua `AssertionError` chủ động, không cần flag `-ea`.

Không dựa vào cài đặt locale/múi giờ/ngày giờ của máy chạy; supported tags và inputs cố định. Một số mã có aliases mặc định trong runtime có thể mở rộng range list, nhưng ví dụ dùng những mã ổn định và kiểm tra chính những trường hợp đã chọn.

## 14. Sai lầm phổ biến

| Sai lầm | Tại sao sai | Cách xử lý |
| --- | --- | --- |
| Coi `Locale` và `LanguageRange` là một | Locale là đối tượng địa phương hóa; Range là pattern có trọng số | Dùng đúng API |
| Dùng `Locale.forLanguageTag` để parse cả Accept-Language header | Header chứa nhiều ranges và `;q=` | `LanguageRange.parse` |
| Lấy mục đầu header mà bỏ q | Ưu tiên có thể khác vị trí | Dùng priority list đã parse |
| Coi `q=0` vẫn chấp nhận | Mâu thuẫn mức preference tối thiểu | Tôn trọng q=0 |
| Tự split `toString()` để lấy q | Format hiển thị không phải protocol | `getRange/getWeight` |
| Tự so chuỗi `startsWith("en")` | Không xử lý đúng ranh giới subtags và RFC 4647 | `filter/lookup` |
| Dùng `filter().get(0)` không kiểm tra empty | Có thể ném `IndexOutOfBoundsException` | Kiểm tra rỗng hoặc `lookup` |
| Coi filtering và lookup giống hệt | Một trả nhiều, một chọn best theo thuật toán khác | Chọn API theo nhu cầu |
| Nghĩ `lookupTag("*",...)` chọn mục đầu | Lookup bỏ qua wildcard | Fallback rõ ràng |
| Nhầm `en_US` với BCP 47 range | Dấu underscore không phải separator hợp lệ | Dùng `en-US` |
| Không xử lý extended range | Có thể match sai script/region | Chọn `FilteringMode` |
| Coi alias mapping tạo bản dịch mới | Chỉ đổi priority list | Quản lý supported resources riêng |
| Dùng default locale JVM để đại diện người dùng | Server global không phải request locale | Truyền selected locale explicit |
| Gọi `Locale.setDefault` mỗi request | Race và ảnh hưởng toàn JVM | Không thay global state |
| Dùng Accept-Language để cấp quyền/tính tiền | Header không đáng tin; không phải region pháp lý | Chính sách quyền/giá riêng |
| Cache theo raw header không giới hạn | Rất nhiều key biến thể | Key theo selected tag/canonical policy |
| Tin input HTTP không cần giới hạn | Header dài, nhiều ranges, parse error | Validation và input limits |
| Coi matched locale bảo đảm mọi resource key tồn tại | Matching không load bản dịch | Resource fallback riêng |

## 15. Bài tập có đáp án

**1.** `new Locale.LanguageRange("en",0.8)` biểu diễn gì? — Phạm vi tiếng Anh có trọng số 0.8; nó không tự chọn `en-US` hoặc `en-GB`.

**2.** Trong `"vi-VN,en;q=0.6"`, q của `vi-VN` là mấy? — 1.0 mặc định.

**3.** Với `"fr;q=0.2, vi;q=0.8, en;q=1"`, `parse` ưu tiên range nào? — `en`, sau đó `vi`, rồi `fr`.

**4.** `filterTags` và `lookupTag` khác nhau thế nào? — Filter trả nhiều matching tags, lookup chỉ trả một tag tốt nhất hoặc null.

**5.** `Locale.filterTags(parse("en"),["vi-VN","en-US","en-GB"])` trả gì? — `[en-US,en-GB]` trên candidates có thứ tự như đã đưa.

**6.** Vì sao `lookupTag(parse("*"),tags)` có thể trả null? — Wildcard bị bỏ qua trong lookup; cần fallback explicit.

**7.** `Locale.LanguageRange.parse("en_US")` có hợp lệ không? — Không, dùng `en-US`.

**8.** `zh-*-TW` thuộc range nào? — Extended; dùng `EXTENDED_FILTERING` nếu muốn matching theo kiểu đó.

**9.** `q=0` có nên dùng như một range ưu tiên thấp được chọn khi hết cách? — Không; xử lý ngôn ngữ bị loại và fallback theo policy riêng.

**10.** Nếu lookup không khớp, có nên lấy `Locale.getDefault()` không? — Chỉ khi product **chủ đích** chọn đó; thường nên dùng default supported tag explicit.

**11.** Có thể gọi `Locale.setDefault(selected)` để phục vụ từng HTTP request không? — Không, vì thay đổi default có phạm vi JVM và ảnh hưởng request khác.

**12.** Nếu server đã chọn `vi-VN` mà thiếu một translation key thì ai giải quyết? — Tầng resource/bundle và fallback key; `LanguageRange`/`lookup` không tải resource.

**13.** Có thể coi `q=0.9` là bằng chứng người dùng đang sống ở Việt Nam không? — Không. Đó chỉ là trọng số preference.

**14.** Muốn dùng alias theo quy tắc sản phẩm, API nào? — `Locale.LanguageRange.mapEquivalents` hoặc `parse(String,Map)`, sau khi cân nhắc chính sách.

## 16. Ma trận QA gợi ý cho production

| Input header | Supported | Điều cần kiểm tra |
| --- | --- | --- |
| `vi-VN,en-US;q=0.8` | `vi-VN,en-US` | Chọn `vi-VN` |
| `en-GB,en;q=0.8` | `en-US,en-GB` | Chọn `en-GB` |
| `en;q=0.8,fr;q=0.5` | `en-US,fr-FR` | Chọn `en-US` |
| `ko-KR` | `vi-VN,en-US` | Lookup null, fallback explicit |
| `*` | `en-US,vi-VN` | Lookup null theo wildcard rule |
| `fr;q=0` | `fr-FR,en-US` | Không chọn `fr-FR` qua q0 |
| `zh-*-TW` | `zh-Hant-TW,zh-Hans-CN` | Extended mode chọn đúng TW |
| `en;q=1.5` | Bất kỳ | Parse ném `IllegalArgumentException` |
| `en_US` | Bất kỳ | Parse ném `IllegalArgumentException` |
| Header cực dài | Bất kỳ | Giới hạn input trước parse |
| Không có header | Bất kỳ | Dùng default supported |
| Preference profile khác header | Bất kỳ | Thứ tự ưu tiên theo product |

Bên cạnh unit tests, cần integration tests để bảo đảm **sau negotiation thật sự chọn đúng message bundle, số/ngày được format bằng selected locale, và fallback resource hoạt động**. Không coi unit test `lookup` thay thế toàn bộ kiểm thử i18n.

## 17. Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 27 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.LanguageRange.html): cú pháp basic/extended, q, parse, getters, alias mapping.
- [Oracle Java SE 27 — Locale](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html): RFC 4647 filtering/lookup, return types, matching và wildcard.
- [Oracle Java SE 27 — Locale.FilteringMode](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.FilteringMode.html): AUTOSELECT, EXTENDED, IGNORE, MAP, REJECT.
- [Oracle Java SE 8 — Locale.LanguageRange](https://docs.oracle.com/javase/8/docs/api/java/util/Locale.LanguageRange.html): đối chiếu API đã có từ Java 8.
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647): nguyên tắc language ranges, filtering và lookup.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa header `Accept-Language` trong HTTP hiện đại.

**Tóm tắt:** `Locale.LanguageRange` mô tả **ngôn ngữ mong muốn và trọng số `q`**; `parse` xây danh sách ưu tiên, `filter/filterTags` trả các ứng viên phù hợp, `lookup/lookupTag` chọn một ứng viên tốt nhất. Luôn so khớp với **supported languages thật**, xử lý `null` và q0/wildcard đúng hợp đồng, xác định fallback riêng, và không nhầm ngôn ngữ với authorization, timezone hay resource loading.
