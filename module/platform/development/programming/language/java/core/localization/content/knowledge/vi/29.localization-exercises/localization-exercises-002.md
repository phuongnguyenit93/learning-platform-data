# Chọn locale từ danh sách ưu tiên và danh sách được hỗ trợ trong Java

## 1. Bài toán thực tế: người dùng muốn tiếng Pháp, máy chủ có tiếng Việt, Đức và Anh

Một ứng dụng Java đa ngôn ngữ có thể có nhiều bộ tài nguyên dịch, nhưng **không hỗ trợ tất cả các locale trên thế giới**. Trong khi đó, trình duyệt hoặc tài khoản người dùng thường gửi **nhiều ngôn ngữ theo thứ tự ưu tiên**, không phải một ngôn ngữ duy nhất.

Ví dụ HTTP request có header:

```http
Accept-Language: fr-CA,fr;q=0.9,de-DE;q=0.8,en-US;q=0.6
```

Điều này thể hiện người dùng ưu tiên:

1. `fr-CA` — tiếng Pháp tại Canada, mặc định trọng số `q=1.0`.
2. `fr` — tiếng Pháp nói chung, `q=0.9`.
3. `de-DE` — tiếng Đức tại Đức, `q=0.8`.
4. `en-US` — tiếng Anh tại Hoa Kỳ, `q=0.6`.

Nếu sản phẩm chỉ thực sự có bản dịch `vi-VN`, `de-DE` và `en-US` thì nên chọn locale nào? **`de-DE`**, vì đó là mục cao nhất trong danh sách ưu tiên có thể đáp ứng theo chính sách đối chiếu đã chọn.

Nhưng nếu hệ thống có `fr-FR` mà **không** có `fr-CA` thì vấn đề tinh tế hơn: có coi tiếng Pháp tại Pháp là bản thay thế chấp nhận được cho `fr-CA` hay không? Quy tắc **lookup** chuẩn RFC 4647 không luôn tự chọn một “locale cùng ngôn ngữ” bất kỳ; **filtering** và chính sách product fallback có thể cho hành vi khác.

Trong Java 17, các API trọng tâm là:

- `Locale.LanguageRange.parse(headerValue)`: parse danh sách **language ranges** kèm trọng số.
- `Locale.lookup(priorityList, supportedLocales)`: tìm **một** locale phù hợp nhất theo RFC 4647 lookup.
- `Locale.filter(priorityList, supportedLocales)`: lấy danh sách locale phù hợp theo cơ chế filtering.
- `Locale.lookupTag(...)` / `Locale.filterTags(...)`: phiên bản làm việc với BCP 47 tag `String`.
- `Locale.forLanguageTag("vi-VN")`: tạo Locale từ BCP 47 tag.
- `ResourceBundle.getBundle(baseName, locale)`: nạp bản dịch **sau khi đã quyết định locale**, với cơ chế lựa chọn bundle/fallback riêng.

**Mục tiêu:** chọn một locale **thuộc tập sản phẩm thực sự hỗ trợ**, phù hợp thứ tự ưu tiên người dùng và fallback đã định nghĩa; không nhầm “locale Java có dữ liệu định dạng” với “ứng dụng có bản dịch”, không dùng JVM default locale để quyết định thay người dùng.

## 2. Phân biệt bốn khái niệm

| Khái niệm | Ví dụ | Ai quyết định? |
| --- | --- | --- |
| **User language preferences** | `fr-CA,fr;q=0.9,en-US;q=0.5` | Người dùng/browser/header |
| **Language range** | `fr-CA`, `fr`, `en-US`, `*` | Chuỗi yêu cầu đối chiếu theo RFC 4647 |
| **Supported locales** | `vi-VN`, `en-US`, `de-DE` | Sản phẩm/deployment có bản dịch và QA |
| **Application default/fallback** | `en-US` hoặc `vi-VN` | Chính sách rõ ràng của sản phẩm |

Một `LanguageRange` là **mẫu ưu tiên**; không nhất thiết là đối tượng `Locale` đã đầy đủ các thuộc tính ngôn ngữ, chữ viết và vùng. `"fr"` là một range chỉ muốn tiếng Pháp, còn `"fr-CA"` chỉ định thêm Canada; `"*"` là wildcard.

Một `Locale` như `Locale.forLanguageTag("fr-FR")` lại là một lựa chọn cụ thể có thể dùng để định dạng/ngôn ngữ.

**Danh sách hỗ trợ** phải dựa vào sản phẩm, ví dụ bộ `messages` thực sự được dịch và kiểm thử:

```text
SUPPORTED = [vi-VN, en-US, de-DE, fr-FR]
DEFAULT   = en-US
```

**Không dùng `Locale.getAvailableLocales()` làm danh sách bản dịch được hỗ trợ.** API đó mô tả locale data của runtime Java (số, ngày, tên vùng…), không cam kết sản phẩm có `messages_vi.properties`, `messages_fr.properties` hay bản dịch UI hoàn chỉnh.

### Locale khác zone, currency và UI direction

Chọn `fr-FR` không tự đổi dữ liệu tiền USD thành EUR; chọn `ja-JP` không có nghĩa bắt buộc dùng lịch niên hiệu Nhật. Múi giờ được chọn bằng `ZoneId`, hệ lịch bằng `Chronology` và currency bằng `Currency`/hợp đồng nghiệp vụ. Locale chủ yếu là **ngữ cảnh ngôn ngữ/định dạng**.

## 3. Cấu trúc BCP 47 language tag

Một language tag có thể mô tả:

```text
language  - script - region - variants - extensions
zh        - Hant   - TW
sr        - Latn   - RS
pt                 - BR
en                 - US
```

| Phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Language | `vi`, `en`, `de`, `tr` | Ngôn ngữ |
| Script | `Hans`, `Hant`, `Latn`, `Cyrl` | Hệ chữ |
| Region | `VN`, `US`, `BR` | Vùng |
| Variant | Một subtag đã đăng ký | Biến thể cụ thể |
| Unicode extension | `u-ca-buddhist`, `u-nu-latn` | Calendar/numbering preferences khi API hỗ trợ |

`zh-Hant-TW` (tiếng Trung chữ phồn thể tại Đài Loan) khác `zh-Hans-CN` (chữ giản thể tại Trung Quốc). Vì thế **không nên chỉ so hai chữ cái đầu của language tag** rồi suy bản dịch nào cũng thay thế được cho bản dịch nào.

Java `Locale.forLanguageTag` hiểu cú pháp BCP 47 nhưng **không xác minh rằng mọi tag đều là một locale mà sản phẩm có tài nguyên**. Một tag có vẻ hợp lệ vẫn có thể không có bundle dịch. Nếu input cần kiểm tra cú pháp nghiêm ngặt, có thể dùng `new Locale.Builder().setLanguageTag(tag).build()` và bắt `IllformedLocaleException`; tuy nhiên việc cú pháp hợp lệ vẫn không chứng minh tag có trong registry, đã dịch hoặc đã QA.

### Đừng dùng toString() để làm language tag giao thức

`Locale.toString()` có dạng truyền thống như `en_US`, còn BCP 47 dùng `en-US`. Với HTTP và profile trao đổi qua API, nên lưu `locale.toLanguageTag()` và parse bằng `Locale.forLanguageTag(...)`.

## 4. Header Accept-Language và trọng số q

Trong HTTP, `Accept-Language` là một danh sách lựa chọn theo mức độ ưu tiên. Ví dụ:

```http
Accept-Language: de-DE,de;q=0.9,en-US;q=0.6,en;q=0.4
```

- Không có `q` → mặc định trọng số 1.0.
- `q=0.9` → ít ưu tiên hơn mục `q=1.0`.
- `q=0` trong HTTP mang nghĩa **không chấp nhận** range đó.
- `*` có nghĩa chấp nhận một language tag không được chỉ rõ hơn, theo quy tắc matching thích hợp.
- Thứ tự/weight không nhất thiết trùng với thứ tự từ trái sang phải: ứng dụng phải parse và đối chiếu theo priority list thực sự.

Java có:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse(
                "de-DE,de;q=0.9,en-US;q=0.6,en;q=0.4");
```

Đoạn này nằm trong method có import `java.util.*`.

`LanguageRange.parse`:

- Chấp nhận danh sách phân cách bằng dấu phẩy và trọng số `;q=...`.
- Sắp xếp danh sách kết quả theo mức ưu tiên/weight giảm dần.
- Có thể thêm language ranges **tương đương** từ registry (chẳng hạn mã ngôn ngữ cũ và mới), vì thế số phần tử trả về có thể khác số range người dùng viết.
- Loại bỏ những lần lặp của cùng range theo quy tắc API.
- Kiểm tra cú pháp, **không xác thực nội dung dịch hay sự tồn tại của từng mã trong registry**.
- Có thể ném `IllegalArgumentException` khi language range hoặc weight không hợp lệ.

**Không tự parse Accept-Language bằng `split(",")` rồi lấy mục đầu** nếu sản phẩm muốn tôn trọng `q`, alias và chính sách đối chiếu. Cũng không tự dùng `Locale.forLanguageTag(header)` trực tiếp cho cả header chứa nhiều ranges; đó không phải API parse danh sách ưu tiên.

### 4.1. q=0 và HTTP acceptability

RFC HTTP định nghĩa `q=0` là một ngôn ngữ không được chấp nhận. Tuy nhiên `Locale.LanguageRange.parse` và `Locale.lookup/filter` là **API đối chiếu RFC 4647**, không thay thế toàn bộ bộ máy nội dung negotiation của HTTP.

Nếu header chứa `en;q=0, *;q=0.5`, cần quyết định rõ cách **ngăn ngôn ngữ đã bị từ chối** khi wildcard có thể phù hợp nhiều mục. Không đơn giản bỏ range q=0 rồi để wildcard chọn lại đúng ngôn ngữ đã bị cấm. Một HTTP negotiation đầy đủ phải áp quy tắc acceptability/exclusions của sản phẩm hay framework phù hợp. Không khẳng định `Locale.lookup` tự thi hành mọi quy tắc `q=0` của RFC 9110.

Trong ví dụ Java học thuật, ta dùng các q dương để minh họa kết quả ổn định; phần thiết kế production sẽ giải thích cách bảo vệ trước header bất thường.

## 5. Hai cơ chế RFC 4647: lookup và filtering

### 5.1. Lookup — tìm một locale gần nhất theo thứ tự ưu tiên

`Locale.lookup(...)` trả **một Locale hoặc null**:

```java
Locale chosen = Locale.lookup(priorities, supported);
```

Thuật toán **progressive truncation** theo RFC 4647: với range như `zh-Hant-TW`, thử `zh-Hant-TW`, rồi `zh-Hant`, rồi `zh`; nếu không được thì thử range tiếp theo theo priority. Điều này **không có nghĩa** nó chọn mọi tag bắt đầu cùng ngôn ngữ.

Ví dụ quan trọng:

```text
User priority: en-GB
Supported:     en-US

Locale.lookup(...) → null
```

Vì `en-GB` sẽ được thử cụ thể rồi rút thành `en`, nhưng danh sách supported chỉ có `en-US`, **không có tag `en`**. Lookup không tự biến `en-GB` thành `en-US` qua một “nearest region” ngầm.

Tương tự, nếu ưu tiên `fr-CA,fr;q=0.9,en-US;q=0.6` và supported gồm `fr-FR`, `en-US`, thì lookup có thể chọn **en-US** vì range `fr` trong lookup không khớp chính xác tag `fr-FR`. Đây không phải bug Java; đó là **một thuật toán đối chiếu cụ thể**.

Đặc biệt, wildcard `*` được **bỏ qua trong lookup**. Nếu priority list chỉ có `*`, kết quả lookup có thể là `null` dù supported không rỗng. Caller phải có default/fallback rõ.

### 5.2. Filtering — lấy những locale được range bao hàm

`Locale.filter(...)` trả một danh sách:

```java
List<Locale> matches = Locale.filter(
        priorities, supported);
```

Khác với lookup, một language range **`fr`** khi filtering có thể khớp `fr-FR`, `fr-CA` và nhiều biến thể `fr-...`. `Locale.filter` trả các locale phù hợp theo priority, loại trùng.

Tại sao cần cả hai API?

| Nhu cầu | API gợi ý | Kết quả |
| --- | --- | --- |
| Chọn một locale duy nhất bằng RFC 4647 lookup | `Locale.lookup` | `Locale` hoặc `null` |
| Lấy danh sách locale hợp với từng language range | `Locale.filter` | `List<Locale>` |
| Trình bày dropdown gợi ý các ngôn ngữ phù hợp | `Locale.filter` | Nhiều lựa chọn |
| Trả về BCP 47 tags thay vì Locale objects | `lookupTag` / `filterTags` | `String` hoặc list strings |
| Chọn fallback kinh doanh gần với ngôn ngữ yêu cầu | Chính sách ứng dụng dùng kết quả lookup/filter và mapping rõ | Một locale trong allowed set |

**Không tự gọi `filter(...).get(0)` khi danh sách rỗng**. Kiểm tra `isEmpty()` và giữ một fallback nằm trong supported locales.

### 5.3. Bảng phân biệt rõ ràng

| Header/preference | Supported | `lookup` | `filter` |
| --- | --- | --- | --- |
| `de-DE,de;q=0.9` | `de-DE, en-US` | `de-DE` | Bao gồm `de-DE` |
| `en-GB` | `en-US` | `null` | Không có `en-US` nếu chỉ range `en-GB` |
| `en` | `en-US` | `null` | Bao gồm `en-US` |
| `fr-CA,fr;q=0.9,en-US;q=0.7` | `fr-FR, en-US` | `en-US` | `fr-FR` rồi `en-US` |
| `*` | `de-DE, en-US` | `null` | Có thể chọn từ toàn bộ supported theo filtering |

Bảng dùng các trường hợp đơn giản để minh họa khác biệt. Nếu một ngôn ngữ có aliases, wildcard mở rộng hoặc dữ liệu provider đặc biệt, hãy kiểm tra danh sách cụ thể bằng API thực trên JDK mục tiêu.

## 6. Ví dụ Java 17 chạy độc lập: so sánh lookup với filter

Tạo tệp `LookupVsFilterDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class LookupVsFilterDemo {

    static String tags(List<Locale> locales) {
        return locales.stream()
                .map(Locale::toLanguageTag)
                .collect(Collectors.joining(", "));
    }

    static void inspect(String preference, List<Locale> supported) {
        List<Locale.LanguageRange> ranges =
                Locale.LanguageRange.parse(preference);

        Locale match = Locale.lookup(ranges, supported);
        List<Locale> matches = Locale.filter(ranges, supported);

        System.out.println("preference=" + preference);
        System.out.println("lookup=" +
                (match == null ? "null" : match.toLanguageTag()));
        System.out.println("filter=" + tags(matches));
    }

    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-US"));

        inspect("fr-CA,fr;q=0.9,en-US;q=0.7", supported);
        inspect("en", supported);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LookupVsFilterDemo.java
java LookupVsFilterDemo
```

Stdout xác định trên Java 17 với các language ranges trên:

```text
preference=fr-CA,fr;q=0.9,en-US;q=0.7
lookup=en-US
filter=fr-FR, en-US
preference=en
lookup=null
filter=en-US
```

**Diễn giải:**

- `fr-CA` không có trong supported; range `fr` giúp **filtering** tìm `fr-FR`, nhưng **lookup** cần tag `fr` chính xác sau khi rút ngắn.
- Range `en-US` xuất hiện sau trong danh sách priority và lookup chọn `en-US` khi đó là tag cụ thể được hỗ trợ.
- Range `en` một mình không làm lookup chọn `en-US`, nhưng filtering trả `en-US`.

Không nên quyết định API “nào đúng hơn” chỉ bằng việc một kết quả trực giác hơn. Hai cơ chế đúng theo **hai tiêu chí khác nhau**; kiến trúc sản phẩm phải nói rõ muốn xử lý “cùng ngôn ngữ nhưng khác vùng” như thế nào.

## 7. Xây chính sách chọn locale trong sản phẩm

Một sản phẩm thường cần trả lời trước khi viết code:

1. **Có những locale thực sự được dịch và hỗ trợ?** Từ catalog release, không từ `Locale.getAvailableLocales()`.
2. **Locale mặc định là gì?** Phải nằm trong supported set.
3. **Ưu tiên nào cao hơn?** Chọn ngôn ngữ thủ công trong UI? Cài đặt tài khoản? URL `/vi/`? Header browser?
4. **Cho phép fallback cùng ngôn ngữ khác vùng không?** Ví dụ `pt-AO → pt-PT` hoặc `pt-BR`, phải được product/linguist phê duyệt.
5. **Có hỗ trợ biến thể script không?** `zh-Hant` và `zh-Hans` không thể đổi tùy tiện.
6. **Khi không match thì làm gì?** Default công bố, lựa chọn ngôn ngữ, hoặc từ chối negotiation nếu đó là hợp đồng API.
7. **Có tôn trọng `q=0` và `*` như HTTP không?** Nếu có, cần dùng thư viện/framework negotiator phù hợp hoặc triển khai và test đầy đủ.
8. **Có giới hạn độ dài/số language ranges của header không?** Header từ client là input không đáng tin.
9. **Cache có phụ thuộc locale đã chọn không?** Tránh phục vụ bản dịch sai cho người dùng khác.

### 7.1. Thứ tự nguồn ưu tiên tham khảo

Một chính sách thường hợp lý (nhưng phải được sản phẩm quyết định) là:

```text
Người dùng chọn ngôn ngữ tường minh trong UI
          ↓ nếu chưa có
Cài đặt ngôn ngữ tài khoản
          ↓ nếu chưa có
Thông tin ngôn ngữ trong URL/route khi có
          ↓ nếu chưa có
Accept-Language của trình duyệt
          ↓ nếu không match
DEFAULT_LOCALE được sản phẩm hỗ trợ
```

Trong sản phẩm khác, URL có thể là nguồn ưu tiên cao hơn profile để tạo liên kết cố định có thể chia sẻ. Điều quan trọng là **thứ tự được định nghĩa và kiểm thử**, không phải thứ tự nào luôn đúng cho mọi ứng dụng.

Không dùng vị trí IP như bằng chứng chắc chắn cho ngôn ngữ. Một người Việt sống tại Đức có thể ưu tiên `vi-VN`; một máy có region Việt Nam vẫn có thể dùng giao diện `en-US`.

## 8. Java 17 runnable: một bộ chọn locale từ supported list

Ở mức cơ bản, ta có thể sử dụng `Locale.lookup` với fallback sản phẩm rõ ràng.

Tệp `LocaleNegotiatorDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiatorDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("de-DE"),
            Locale.forLanguageTag("fr-FR"));

    static Locale choose(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            List<Locale.LanguageRange> priorities =
                    Locale.LanguageRange.parse(acceptLanguage);

            Locale matched = Locale.lookup(priorities, SUPPORTED);
            return matched != null ? matched : DEFAULT_LOCALE;
        } catch (IllegalArgumentException ex) {
            // Chính sách demo: input sai cú pháp thì dùng default.
            return DEFAULT_LOCALE;
        }
    }

    public static void main(String[] args) {
        String[] examples = {
                "de-DE,de;q=0.9,en-US;q=0.8",
                "fr-CA,fr;q=0.9,en-US;q=0.7",
                "en-GB",
                "vi-VN,en-US;q=0.7",
                "*",
                "es-MX,es;q=0.8"
        };

        for (String header : examples) {
            System.out.println(
                    choose(header).toLanguageTag());
        }
    }
}
```

```bash
javac -encoding UTF-8 LocaleNegotiatorDemo.java
java LocaleNegotiatorDemo
```

Stdout:

```text
de-DE
en-US
vi-VN
vi-VN
vi-VN
vi-VN
```

Đây là **demo của chính sách RFC 4647 lookup + application default**:

- `de-DE` khớp trực tiếp.
- `fr-CA` và `fr` không khớp `fr-FR` trong lookup; `en-US` là range hợp lệ tiếp theo nên được chọn.
- `en-GB` không match tag `en-US`: fallback `vi-VN`.
- `vi-VN` khớp trực tiếp.
- Wildcard `*` bị bỏ qua trong lookup: fallback `vi-VN`.
- Không có `es-MX` hay `es` trong supported: fallback `vi-VN`.

**Không dùng code này làm HTTP negotiator production hoàn chỉnh:** nó chưa áp dụng giới hạn header, chưa xử lý `q=0`/HTTP exclusions, chưa lựa chọn fallback theo cùng ngôn ngữ, và chỉ bắt lỗi cú pháp ở mức API. Đó là lý do phải viết thêm contract và test tích hợp thay vì copy-paste một ví dụ cơ bản vào gateway.

## 9. Xử lý “cùng ngôn ngữ, khác vùng” có chủ ý

Người dùng `fr-CA` và sản phẩm chỉ có `fr-FR`. Có ít nhất ba chính sách hợp lệ tùy sản phẩm:

### Chính sách A: strict lookup, không tự đổi vùng

Chỉ dùng `Locale.lookup`. Nếu không match, thử range khác, rồi về default. Với header `fr-CA,fr;q=0.9,en-US;q=0.7`, có thể chọn `en-US` dù `fr-FR` được hỗ trợ.

Ưu điểm: dựa đúng RFC 4647 lookup, không ngầm tráo một vùng thành vùng khác.

Nhược điểm: một số người dùng có thể thích `fr-FR` hơn `en-US`. Cần giải thích policy.

### Chính sách B: filtering các language ranges rộng

Nếu người dùng khai rõ `fr` trong priority list, `Locale.filter` có thể trả `fr-FR`. Sản phẩm có thể chọn **phần tử đầu tiên** khi hợp đồng cho phép “bất kỳ locale thuộc ngôn ngữ mà người dùng chấp nhận”.

Ví dụ:

```java
List<Locale> filtered = Locale.filter(
        Locale.LanguageRange.parse("fr-CA,fr;q=0.9,en-US;q=0.7"),
        List.of(Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-US")));

Locale selected = filtered.isEmpty()
        ? Locale.forLanguageTag("en-US")
        : filtered.get(0);
```

Đây là đoạn minh họa trong method. `selected` là `fr-FR` theo filtering, khác với strict lookup.

**Lưu ý:** các range được filter có thể là wildcard/extended ranges. Cách chọn phần tử đầu tiên chỉ đúng nếu product contract cho phép dùng thứ tự API, bộ supported có thứ tự kiểm soát và đã giải quyết `q=0`/exclusion của HTTP.

### Chính sách C: mapping fallback đã được phê duyệt

Sản phẩm có thể có bảng mapping:

| User preference | Fallback được phép |
| --- | --- |
| `fr-CA` | `fr-FR` nếu localization team chấp nhận |
| `en-AU` | `en-GB` hoặc `en-US` theo phong cách nội dung |
| `pt-AO` | `pt-PT` hoặc chiến lược cụ thể |
| `zh-HK` | Ưu tiên `zh-Hant`, **không** tự chuyển sang `zh-Hans` |
| `sr-Latn` | Không tự đổi sang `sr-Cyrl` nếu tài nguyên chữ Latin là yêu cầu |

Một mapping như vậy là **policy nghiệp vụ**, không phải lựa chọn mà `Locale.lookup` tự suy ra. Cần quản lý version, review ngôn ngữ, kiểm thử các vùng không tương đương và đảm bảo kết quả vẫn nằm trong supported set.

## 10. Filter nâng cao và các language ranges có wildcard

RFC 4647 có hai dạng language range:

- **Basic ranges**, ví dụ `en`, `ja-JP`, `*`.
- **Extended ranges**, ví dụ `zh-Hant-*`, `*-CH`.

Java cung cấp `Locale.FilteringMode` cho việc lựa chọn hành vi:

| Mode | Ý nghĩa tổng quát |
| --- | --- |
| `AUTOSELECT_FILTERING` | Java tự chọn cơ chế filtering phù hợp loại ranges |
| `EXTENDED_FILTERING` | Dùng extended filtering |
| `IGNORE_EXTENDED_RANGES` | Bỏ các extended ranges |
| `MAP_EXTENDED_RANGES` | Ánh xạ extended ranges thành dạng basic phù hợp |
| `REJECT_EXTENDED_RANGES` | Ném lỗi khi có extended ranges |

Ví dụ rõ mode:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("zh-Hant-*");

List<Locale> filtered = Locale.filter(
        priorities,
        supportedLocales,
        Locale.FilteringMode.EXTENDED_FILTERING);
```

Đây là đoạn minh họa trong method với `supportedLocales` được xác định và import `java.util.Locale`/`java.util.List`.

### Khi nào extended ranges hữu ích?

Giả sử sản phẩm có nhiều region cùng **Traditional Chinese**: `zh-Hant-TW`, `zh-Hant-HK`. Một range `zh-Hant-*` thể hiện mong muốn ưu tiên chữ phồn thể dù không chỉ định region cụ thể. Còn `zh-Hans-CN` là simplified Chinese, không nên bị coi là match thay thế chỉ vì cùng `zh`.

**Cần ghi rõ:** wildcard trong locale range và `*` HTTP có thể khác cách được xử lý giữa lookup và filtering. Với lookup, một `*` đứng độc lập bị bỏ qua; với filtering, wildcard có thể bao hàm nhiều supported tags. Không áp logic kết quả filter cho lookup.

### Thứ tự supported list

Đừng dùng `HashSet`/collection không có thứ tự nếu policy cần kết quả ổn định khi nhiều candidate tương đương. Đối với `lookup`/`filterTags`, nếu nhiều tags cùng match theo wildcard hoặc có bản trùng khác chữ hoa, thứ tự đầu vào có thể ảnh hưởng tag được trả về. Định nghĩa một list được kiểm soát và tie-breaker của sản phẩm.

## 11. Từ locale được chọn đến ResourceBundle

Sau khi chọn được `selectedLocale`, ứng dụng thường dùng nó để nạp family bản dịch:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.Messages", selectedLocale);

String greeting = bundle.getString("greeting");
```

Đoạn code này minh họa trong method, cần import `java.util.ResourceBundle`. Ở đây `selectedLocale` đã được ứng dụng chọn từ danh sách `SUPPORTED`.

**Hai cơ chế khác nhau:**

1. **Locale negotiation:** chọn **một locale sản phẩm mong muốn sử dụng** từ danh sách ưu tiên và supported locales.
2. **ResourceBundle lookup:** tìm **bundle thực tế và từng key** với candidate locales, root/default fallback, classloader/module scope và caching theo `ResourceBundle`.

Nếu chọn `de-DE` mà không có `Messages_de_DE.properties` hoặc `Messages_de.properties`, ResourceBundle có thể fallback về bản khác theo chính sách mặc định. Điều đó không có nghĩa negotiation đã chọn đúng bản dịch `de-DE`. **Supported list phải phản ánh resource/bản dịch thực sự được phát hành**, không dựa vào việc `getBundle` không ném lỗi.

### ResourceBundle.getLocale() giúp chẩn đoán

Sau khi tải bundle, có thể gọi `bundle.getLocale()` để biết locale gắn với bundle kết quả. Nếu ứng dụng yêu cầu một locale cụ thể mà bundle thực sự được trả từ root, đây là tín hiệu thiếu translation coverage. Tuy nhiên, đôi khi `ResourceBundle` dùng inheritance/parent fallback cho từng key nên chỉ nhìn một bundle locale vẫn chưa đủ kiểm thử **toàn bộ key coverage**.

### Java 17 runnable: negotiate rồi lấy bản dịch

Chuẩn bị cấu trúc:

```text
project/
  src/demo/NegotiatedBundleDemo.java
  resources/demo/Messages.properties
  resources/demo/Messages_de.properties
  resources/demo/Messages_vi.properties
```

Nội dung `resources/demo/Messages.properties`:

```properties
hello=Hello
```

Nội dung `resources/demo/Messages_de.properties`:

```properties
hello=Hallo
```

Nội dung `resources/demo/Messages_vi.properties` (UTF-8):

```properties
hello=Xin chào
```

Lưu `src/demo/NegotiatedBundleDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class NegotiatedBundleDemo {
    private static final Locale FALLBACK =
            Locale.forLanguageTag("vi-VN");
    private static final List<Locale> SUPPORTED =
            List.of(FALLBACK,
                    Locale.forLanguageTag("en-US"),
                    Locale.forLanguageTag("de-DE"));

    static Locale choose(String header) {
        Locale match = Locale.lookup(
                Locale.LanguageRange.parse(header),
                SUPPORTED);
        return match != null ? match : FALLBACK;
    }

    public static void main(String[] args) {
        Locale selected = choose(
                "de-DE,de;q=0.8,en-US;q=0.5");

        ClassLoader loader =
                NegotiatedBundleDemo.class.getClassLoader();

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle messages = ResourceBundle.getBundle(
                "demo.Messages", selected, loader, control);

        System.out.println("selected=" +
                selected.toLanguageTag());
        System.out.println("bundleLocale=" +
                messages.getLocale().toLanguageTag());
        System.out.println("hello=" +
                messages.getString("hello"));
    }
}
```

Bash trong thư mục `project`:

```bash
mkdir -p out/demo
javac -encoding UTF-8 -d out src/demo/NegotiatedBundleDemo.java
cp resources/demo/Messages*.properties out/demo/
java -cp out demo.NegotiatedBundleDemo
```

Stdout:

```text
selected=de-DE
bundleLocale=de
hello=Hallo
```

Tại sao `bundleLocale=de` thay vì `de-DE`? Vì demo chỉ có `Messages_de.properties`, không có `Messages_de_DE.properties`. `getBundle` dùng ứng viên `de` khi tìm family, còn locale đã chọn cho giao diện vẫn là `de-DE`.

**Điểm thực hành:** việc bundle dùng một file `_de` phục vụ nhiều vùng Đức là chính sách tài nguyên hợp lệ **nếu bản dịch phù hợp ngữ nghĩa**. Không đồng nhất “bundle filename không có region” với lỗi; phải xét translation coverage theo product contract.

`ResourceBundle.Control` chủ yếu dùng cho classpath/unnamed module. Ở JPMS named modules, overload và khả năng dùng `Control` có hạn chế; có thể cần module-aware lookup hoặc `ResourceBundleProvider`. Demo này cố ý dùng classpath.

## 12. Một lựa chọn locale không giải quyết hết mọi thứ

Sau khi chọn `selectedLocale`, nhiều API khác nhau dùng nó:

```java
NumberFormat numberFormat =
        NumberFormat.getNumberInstance(selectedLocale);

DateTimeFormatter dateFormat =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(selectedLocale);

Collator collator =
        Collator.getInstance(selectedLocale);
```

Đây là đoạn trong method, cần import `java.text.NumberFormat`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle` và `java.text.Collator`.

Nhưng:

- `Locale` không tự quyết định `ZoneId` cho timestamp.
- `Locale` không tự quy đổi USD sang EUR.
- `Locale` không nhất thiết tự chọn `Chronology` non-ISO.
- `Locale` không bảo đảm bộ font hiện hành vẽ đúng Arabic/Hebrew/emoji.
- `Locale` không xử lý toàn bộ HTML/CSS `dir` hoặc Java Swing component orientation.
- `Locale` không tự load file dịch từ plugin loader/module khác.
- `Locale` không đảm bảo `ResourceBundle` nào cũng có đủ keys.

Một ứng dụng đa ngôn ngữ tốt có **locale negotiation rõ**, nhưng vẫn tách các mối quan tâm format/translation/data/layout.

## 13. Kết quả sai do trộn preferred locale với default JVM

Hãy tránh:

```java
Locale.setDefault(chosenLocale);
```

nếu `chosenLocale` đến từ một HTTP request. `Locale.setDefault` thay đổi **trạng thái JVM chung**, có thể khiến request khác thấy format/case/bundle lookup bị ảnh hưởng.

Ví dụ gây lỗi nổi tiếng:

```java
String key = "TITLE".toLowerCase();
```

Nếu JVM default locale là tiếng Thổ Nhĩ Kỳ, chữ `I` chuyển thành dotless `ı`, làm key sai khi code muốn `"title"` theo ASCII. Định danh máy nên dùng `toLowerCase(Locale.ROOT)` theo contract; văn bản hiển thị theo người dùng thì truyền `selectedLocale` vào API.

**Không áp dụng locale người dùng để parse JSON date/time wire format** trừ khi giao thức quy định rõ. API máy thường dùng ISO-8601; UI hiển thị theo locale là một tầng khác.

## 14. Validation đầu vào và xử lý header không đáng tin

`Accept-Language` đến từ client là dữ liệu đầu vào. Không nên tin nó tuyệt đối.

### 14.1. Độ dài và số mục

- Giới hạn độ dài header mà hệ thống chấp nhận theo yêu cầu vận hành.
- Giới hạn số language ranges/chuỗi sau parse nếu cần chống chi phí bất thường.
- Không lưu một header khổng lồ nguyên văn trong log hay cache key nếu không có kiểm soát.
- Khi nhận header trống/thiếu, sử dụng default hoặc preference khác đã được xác minh.
- `LanguageRange.parse` có thể ném `IllegalArgumentException` cho input không hợp lệ: có policy rõ thay vì để 500 vô cớ.

### 14.2. q=0, wildcard và sự nhất quán

- Header `en;q=0` yêu cầu **không chấp nhận English** theo semantics của HTTP.
- `*` có thể chấp nhận các tag khác, nhưng cần bảo đảm không vô hiệu hóa ngôn ngữ bị từ chối.
- Với `Locale.lookup`, `*` được bỏ qua; do đó phải có fallback.
- `Locale.filter` có thể trả nhiều mục và có policy khác lookup.
- Nếu sản phẩm áp đầy đủ HTTP Accept-Language negotiation, dùng implementation đã được kiểm thử theo RFC 9110 và RFC 4647, hoặc viết logic riêng cùng test cho exclusions/tie/weights.

### 14.3. Từ chối ngôn ngữ và fallback mặc định

Một nghịch lý cần giải quyết trong yêu cầu: nếu mọi locale supported đều bị từ chối (q=0), có nên vẫn trả default `en-US` không? Tùy sản phẩm:

- Với website thông thường, có thể chọn fallback UI để trang còn dùng được, nhưng cần hiểu rằng nó **không tuân sát yêu cầu acceptability của client**.
- Với API có hợp đồng thương lượng nội dung nghiêm ngặt, có thể trả `406 Not Acceptable` khi không thể cung cấp representation phù hợp.
- Với user chọn ngôn ngữ trong profile, có thể hỏi/chỉ dẫn chọn lại, hoặc cung cấp default công bố.

Không phải mọi website đều bắt buộc trả 406; RFC HTTP cho phép server cân nhắc cách phục vụ representation. Cần document lựa chọn, test cả trường hợp chặn hết ngôn ngữ, không để user-facing UI đột ngột đổi vì một header bất thường.

### 14.4. Privacy

Danh sách `Accept-Language` rất dài/cụ thể có thể tiết lộ sở thích ngôn ngữ hoặc tăng khả năng nhận diện fingerprinting. Chỉ thu thập và lưu những phần cần thiết cho sản phẩm. Không ghi lại header có nội dung không cần dùng; không suy quốc tịch/danh tính hoặc vị trí chính xác chỉ từ language tag.

## 15. Vấn đề cache và Content-Language

Nếu cùng một URL trả nhiều bản dịch theo `Accept-Language`, cache HTTP/CDN có thể phục vụ sai bản nếu không đưa ngôn ngữ vào chiến lược cache.

- Trả `Content-Language` khi response thật sự thể hiện ngôn ngữ phù hợp.
- Cân nhắc `Vary: Accept-Language` khi response thay đổi theo header này.
- Nếu chọn locale theo user profile/cookie/URL thay vì header, cache key và privacy policy phải tương ứng; `Vary: Accept-Language` **không tự giải quyết** mọi trường hợp.
- Với nội dung riêng tư, kiểm tra `Cache-Control` và phân vùng cache theo người dùng theo đúng chính sách.
- Không dùng `Accept-Language` làm cache key raw vô giới hạn nếu có nguy cơ cardinality quá lớn; cân nhắc normalized selected locale khi kiến trúc cho phép.

**Điểm quan trọng:** header input có thể gồm nhiều preference, nhưng nội dung response thường được tạo dưới **một selected locale cụ thể**. Cache nên gắn với phiên bản nội dung/lang chính xác, không chỉ với chuỗi tùy ý do client cung cấp.

## 16. Test đầy đủ các trường hợp biên

### 16.1. Ma trận kiểm thử lookup/filter

| Preference | Supported | Điều phải xác minh |
| --- | --- | --- |
| `de-DE,de;q=0.9,en-US;q=0.6` | `de-DE, en-US` | Lookup chọn de-DE |
| `fr-CA,fr;q=0.9,en-US;q=0.7` | `fr-FR, en-US` | Lookup chọn en-US; filtering ưu tiên fr-FR |
| `en-GB` | `en-US` | Lookup null, không tự chọn en-US |
| `en` | `en-US` | Lookup null; filter có en-US |
| `*` | `vi-VN, en-US` | Lookup null; policy fallback được định nghĩa |
| `es-MX,es;q=0.8` | `vi-VN, en-US` | Không match, dùng default |
| `zh-Hant-TW` | `zh-Hant, zh-Hans-CN` | Lookup có thể rút thành zh-Hant; không chọn Hans chỉ vì cùng zh |
| `tr-TR` | `tr-TR, en-US` | Case mapping/tr-TR đúng sau khi chọn |
| `ar-EG` | `ar-EG, en-US` | UI RTL ngoài logic locale lookup |
| Header trống/thiếu | Bất kỳ supported không rỗng | Default được dùng |
| Header malformed | Danh sách cố định | Không 500 không kiểm soát |
| `en;q=0,*;q=0.5` | `en-US, de-DE` | Không tái chọn ngôn ngữ bị từ chối qua wildcard nếu HTTP contract nghiêm |
| Equal q | Hai tags đều supported | Tie/priority có chính sách xác định |
| Duplicates/aliases | Bộ tags có alias | Không tự làm mất/nhân bản locale không đúng |
| Đổi supported list | Một locale bị bỏ ở release mới | Không chọn locale không còn tài nguyên dịch |

### 16.2. Kiểm thử hậu negotiation

Một locale được chọn xong vẫn cần test:

- `ResourceBundle.getBundle` tìm family và key bắt buộc đúng.
- Placeholder và `MessageFormat` không sai thứ tự hoặc escaping.
- Number/date/currency formatter đúng locale và parse round-trip.
- `Collator` sắp xếp từ theo ngôn ngữ, nhất là chữ I tiếng Thổ Nhĩ Kỳ.
- Font/line breaking và giao diện RTL nếu tiếng Ả Rập/Hebrew.
- Bản dịch dài không tràn nút/menu, screen reader đọc đúng.
- Không đổi dữ liệu canonical/API vì UI dùng locale khác.
- Đổi locale ở tài khoản giữa hai request phải đổi bundle/formatter và không làm request khác bị ảnh hưởng.

## 17. Test Java 17: assertion cho một chính sách rõ ràng

Tệp `LocaleNegotiationAssertions.java`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiationAssertions {
    static final Locale DEFAULT =
            Locale.forLanguageTag("vi-VN");
    static final List<Locale> SUPPORTED = List.of(
            DEFAULT,
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("de-DE"),
            Locale.forLanguageTag("fr-FR"));

    static Locale choose(String header) {
        if (header == null || header.isBlank()) {
            return DEFAULT;
        }
        Locale matched = Locale.lookup(
                Locale.LanguageRange.parse(header),
                SUPPORTED);
        return matched == null ? DEFAULT : matched;
    }

    static void check(String title, boolean condition) {
        if (!condition) {
            throw new AssertionError(title);
        }
        System.out.println("PASS " + title);
    }

    public static void main(String[] args) {
        check("exact-de", choose("de-DE").equals(
                Locale.forLanguageTag("de-DE")));

        check("next-preference",
                choose("fr-CA,fr;q=0.9,en-US;q=0.7")
                        .equals(Locale.forLanguageTag("en-US")));

        check("no-sibling-match",
                choose("en-GB").equals(DEFAULT));

        check("wildcard-default",
                choose("*").equals(DEFAULT));

        check("empty-default",
                choose("").equals(DEFAULT));

        check("supported-only",
                SUPPORTED.contains(
                        choose("es-MX,fr-FR;q=0.7")));
    }
}
```

```bash
javac -encoding UTF-8 LocaleNegotiationAssertions.java
java LocaleNegotiationAssertions
```

Stdout:

```text
PASS exact-de
PASS next-preference
PASS no-sibling-match
PASS wildcard-default
PASS empty-default
PASS supported-only
```

Bài test dùng `main` để chạy độc lập, không yêu cầu JUnit. Nó chưa có test header malformed (demo `choose` trong file assertion không bắt exception), vì test này tập trung **hành vi lookup hợp lệ**. Khi đưa vào sản phẩm, bổ sung `try/catch`, giới hạn input, q=0/HTTP acceptability và danh sách aliases/extended ranges.

## 18. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chọn luôn mục đầu của header `Accept-Language` | Có thể không supported; bỏ qua `q` | Parse `LanguageRange`, match với supported |
| Dùng `Locale.getAvailableLocales()` làm supported | Dữ liệu locale JDK khác translation coverage | Dùng supported list của sản phẩm |
| Gọi `Locale.forLanguageTag(wholeHeader)` | Header có nhiều ranges và `q`, không phải một tag | Dùng `LanguageRange.parse` |
| Giả định `Locale.lookup` chọn `en-US` cho `en-GB` | Lookup không chọn sibling region tự động | Định nghĩa language fallback riêng |
| Giả định `lookup("en")` match `en-US` | Lookup progressive nhưng không phải prefix filter | Dùng filter khi đó là semantics mong muốn |
| Dùng `filter(...).get(0)` khi rỗng | Ném `IndexOutOfBoundsException` | Kiểm tra empty và default |
| Coi wildcard `*` như locale thật | Không phải BCP 47 language tag cụ thể | Xử lý theo negotiation policy |
| Coi `q=0` như ưu tiên thấp nhưng vẫn được chấp nhận | Theo HTTP q=0 là không chấp nhận | Policy exclusions đúng RFC |
| Dùng `HashSet` không thứ tự cho lựa chọn có tie | Kết quả có thể thiếu tính xác định | Dùng ordered supported list và tie-breaker |
| Dùng `Locale.setDefault` per request | Gây race ở JVM đa người dùng | Truyền locale tường minh |
| Cho `ResourceBundle` fallback là bằng chứng “supported” | Có thể rơi về root bản dịch khác | Kiểm tra catalog/translation coverage |
| Quên script trong tag như `zh-Hant` | Có thể chọn sai hệ chữ | Chính sách script rõ |
| Dựa IP làm bằng chứng language | Không phản ánh preference cá nhân | Ưu tiên cài đặt tường minh |
| Không giới hạn header user-controlled | Có thể gây chi phí/DoS hoặc cache cardinality lớn | Giới hạn length/ranges |
| Coi chọn locale là đổi timezone/currency | Các giá trị độc lập | ZoneId/Currency/Chronology riêng |
| Để cache dùng locale của request trước | Phục vụ sai bản dịch | Key cache/Content-Language/Vary rõ |
| Chỉ test en-US | Bỏ qua phân biệt vùng/RTL/Turkish casing | Ma trận đa locale và UI test |
| Chặn toàn bộ request vì header thiếu | Header không bắt buộc luôn tồn tại | Default/policy thiếu header |

## 19. Bài tập và đáp án

**Bài 1.** User gửi `de-DE,de;q=0.8,en-US;q=0.5`. App có `vi-VN`, `en-US`, `de-DE`. Strict lookup chọn gì?

**Đáp án:** `de-DE` vì range đầu khớp cụ thể với supported.

**Bài 2.** User gửi `en-GB`, app chỉ có `en-US`. Vì sao `Locale.lookup` trả `null`?

**Đáp án:** Lookup rút dần `en-GB → en` nhưng supported không có tag `en`; `en-US` không phải match exact của `en` trong lookup. Muốn fallback cùng ngôn ngữ, phải có policy riêng hoặc dùng filtering trên một range thích hợp.

**Bài 3.** User gửi `en`, app có `en-US`. `Locale.filter` trả gì và `Locale.lookup` trả gì?

**Đáp án:** Filtering có thể trả `en-US`; lookup trả `null` nếu không có locale `en`.

**Bài 4.** Browser gửi `fr-CA,fr;q=0.9,en-US;q=0.7`; supported `fr-FR,en-US`. Vì sao lookup và filter khác nhau?

**Đáp án:** `fr` khi lọc có thể bao hàm `fr-FR`, nhưng khi lookup cần đối chiếu tag đầy đủ/được rút ngắn; `en-US` là range khớp tiếp theo. Chính sách product quyết định chọn strict lookup hay preferred language fallback.

**Bài 5.** `LanguageRange.parse` có thể trả nhiều phần tử hơn số range trong header vì sao?

**Đáp án:** Java có thể thêm các language ranges tương đương từ IANA Language Subtag Registry, ví dụ mã ngôn ngữ cũ/mới.

**Bài 6.** `q=0` có nghĩa gì trong `Accept-Language`?

**Đáp án:** Theo HTTP đó là không chấp nhận range; không đơn giản coi như một lựa chọn trọng số rất thấp hoặc để wildcard vô tình chọn lại nó.

**Bài 7.** Vì sao không dùng `Locale.getAvailableLocales()` để chọn locale hiển thị?

**Đáp án:** Nó cho biết locale data của JDK, không xác nhận sản phẩm có bản dịch và UI QA cho từng locale.

**Bài 8.** `zh-Hant-TW` và `zh-Hans-CN` cùng ngôn ngữ `zh`. Có nên tự đổi qua lại không?

**Đáp án:** Không. Script khác nhau; chỉ dùng fallback được người chịu trách nhiệm bản địa hóa phê duyệt.

**Bài 9.** Sau khi chọn `de-DE`, `ResourceBundle.getBundle` trả file `Messages_de.properties`. Đó là lỗi không?

**Đáp án:** Không nhất thiết. Bundle candidate `de` có thể phục vụ `de-DE`; kiểm tra coverage và nội dung theo contract.

**Bài 10.** Hai người dùng cùng endpoint nhưng khác `Accept-Language`. CDN cache trang theo URL duy nhất có thể gặp lỗi gì?

**Đáp án:** Có thể trả trang tiếng của người trước cho người sau. Cần thiết kế cache key/`Vary`/Content-Language phù hợp và kiểm tra dữ liệu riêng tư.

**Bài 11.** App dùng `Locale.setDefault(chosen)` khi nhận mỗi request; có nguy cơ gì?

**Đáp án:** Thay default JVM toàn cục, gây tác động chéo request và các thư viện format/case/bundle không nhận locale tường minh.

**Bài 12.** Bản dịch `fr-FR` không có, nhưng `Locale.getAvailableLocales()` có `fr-FR`. Có nên đưa nó vào `SUPPORTED`?

**Đáp án:** Không, trừ khi sản phẩm công bố hỗ trợ locale đó với tài nguyên/QA tương ứng. Có formatter JDK không đồng nghĩa có translation.

**Bài 13.** Khi client không gửi `Accept-Language`, hệ thống có nên đoán từ IP ngay không?

**Đáp án:** Không nên xem IP là nguồn chắc chắn. Dùng preference khác đã được người dùng chọn hoặc fallback product đã định nghĩa.

**Bài 14.** Vì sao không hard-code cả số/tháng/năm theo region khi đã chọn locale?

**Đáp án:** Java có locale formatting data theo CLDR/provider; lấy formatter tương ứng để trình bày. Đừng trộn nó với format máy cố định cho API.

## 20. Checklist triển khai production

- [ ] Danh sách `SUPPORTED_LOCALES` do sản phẩm xác nhận từ bản dịch + QA, không từ JDK available locales.
- [ ] `DEFAULT_LOCALE` thực sự nằm trong supported list.
- [ ] Thứ tự các nguồn ưu tiên (UI, profile, URL, header) có contract và test.
- [ ] Header `Accept-Language` được parse bằng API phù hợp và có validation/size limit.
- [ ] `q`, wildcard và `q=0` được xử lý theo chính sách HTTP đã chọn.
- [ ] Biết rõ đang dùng **lookup** hay **filtering** và có tests cho khác biệt `en-GB/en-US`.
- [ ] Quy tắc fallback theo language/script/region đã được review, không giả định sibling regions tương đương.
- [ ] Mọi kết quả lựa chọn đều thuộc supported set (trừ tình huống chủ động báo không chấp nhận).
- [ ] Khi không match, kết quả default/406/prompt người dùng được định nghĩa.
- [ ] Locale được truyền tường minh, không set default JVM theo request.
- [ ] Bundle được load đúng scope, key coverage và fallback đã kiểm thử.
- [ ] ZoneId/Chronology/Currency được quản lý riêng.
- [ ] Cache và Content-Language/Vary đúng thực tế nguồn lựa chọn.
- [ ] Test Turkish I, RTL, font, số/ngày theo từng locale thực sự hỗ trợ.
- [ ] Kết quả được theo dõi bằng metrics không lộ header/PII không cần thiết.

## 21. Tổng kết

**Chọn locale là một bài toán đối chiếu ưu tiên với khả năng hỗ trợ thực tế.** Người dùng có thể gửi nhiều language ranges kèm `q`; ứng dụng chỉ nên chọn trong **catalog locale có bản dịch** và phải có default chính sách rõ.

Java 17 cung cấp `Locale.LanguageRange.parse`, `Locale.lookup`/`lookupTag` và `Locale.filter`/`filterTags`. **Lookup** nhằm chọn một tag theo RFC 4647, có progressive truncation nhưng không tự chọn mọi locale cùng ngôn ngữ ở vùng khác. **Filtering** tìm tập tags được các ranges bao hàm, phù hợp những chính sách chấp nhận rộng hơn.

Đừng dùng `Locale.getAvailableLocales()` làm danh sách bản dịch; đừng nhầm negotiation với `ResourceBundle` fallback; đừng dùng `Locale.setDefault` theo request. Với HTTP production, bổ sung handling `q=0`/wildcard, input limits, preferences, cache và kiểm thử các ngôn ngữ đặc thù.

Một selector tốt không chỉ “trả một Locale”, mà còn phải **trả đúng locale được công bố hỗ trợ**, rõ nguyên nhân fallback, không làm sai ngôn ngữ, dữ liệu hay cache.

### Tài liệu tham khảo chính thức

- [Locale — BCP 47, RFC 4647 matching, lookup và filtering (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Locale.LanguageRange — parsing, weight và language priority list (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Locale.FilteringMode — cách lọc language ranges (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.FilteringMode.html)
- [ResourceBundle — bundles, fallback và modules (Oracle Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647.html)
- [RFC 9110 — HTTP Semantics, Accept-Language](https://www.rfc-editor.org/rfc/rfc9110.html)
