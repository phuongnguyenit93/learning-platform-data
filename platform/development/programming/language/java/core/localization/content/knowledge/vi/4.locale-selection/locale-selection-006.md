# Phân biệt lọc nhiều kết quả với chọn một kết quả phù hợp

## 1. Bài toán chọn locale trong ứng dụng Java

Giả sử ứng dụng có bản địa hóa cho `fr-FR`, `fr-CA`, `en-US`, `en-GB` và `vi-VN`. Người dùng gửi thứ tự ưu tiên:

```text
fr-CA, fr;q=0.9, en;q=0.6
```

Ứng dụng cần trả lời **hai câu hỏi khác nhau**:

1. **Có những locale nào đáp ứng các ngôn ngữ người dùng chấp nhận?** Kết quả là *một danh sách*, có thể dùng để hiển thị lựa chọn hoặc thu hẹp danh sách nội dung.
2. **Nên sử dụng đúng một locale nào cho phiên làm việc hoặc tài nguyên cần trả về?** Kết quả là *một ứng viên tốt nhất theo cơ chế lookup*, hoặc không có ứng viên.

Java hỗ trợ hai cơ chế trong RFC 4647 — **filtering** và **lookup** — thông qua `java.util.Locale`. Điểm dễ nhầm là tên gọi “lọc” và “chọn” có vẻ giống nhau, nhưng **điều kiện khớp, số lượng kết quả, cách tìm fallback và cách ứng dụng xử lý kết quả** không giống nhau.

## 2. Hai phương thức chính và kiểu dữ liệu

| Tiêu chí | Filtering — `Locale.filter(...)` | Lookup — `Locale.lookup(...)` |
| --- | --- | --- |
| Mục tiêu | Tìm **tất cả** locale phù hợp với danh sách ưu tiên | Tìm **một** locale phù hợp nhất theo thuật toán lookup |
| Đầu vào chính | `List<Locale.LanguageRange>` và `Collection<Locale>` | Cùng hai kiểu đầu vào |
| Kiểu trả về | `List<Locale>` | `Locale` |
| Khi không có kết quả | Danh sách rỗng | `null` |
| Khớp theo range | Cho phép ngôn ngữ tổng quát `fr` khớp các tag cụ thể hơn như `fr-FR`, `fr-CA` | Thử range cụ thể theo thứ tự ưu tiên và cắt dần subtag để tìm một **tag khớp theo quy tắc lookup** |
| Dùng khi | Danh sách các lựa chọn, bộ lọc nhiều bản dịch/ngôn ngữ | Quyết định một locale để phục vụ yêu cầu |
| Biến thể với chuỗi | `Locale.filterTags(...)` trả `List<String>` | `Locale.lookupTag(...)` trả `String` hoặc `null` |

**Không được hiểu `lookup` đơn giản là `filter(...).get(0)`.** RFC 4647 định nghĩa hai cơ chế khớp khác nhau. Vì thế có trường hợp filtering trả một hoặc nhiều locale nhưng lookup lại trả `null` — ví dụ được chứng minh ở phần 5.

Việc `filter` trả nhiều lựa chọn không có nghĩa tất cả bản dịch hoặc chức năng của ứng dụng đều thực sự đã sẵn sàng. Tập ứng viên phải là các locale **mà sản phẩm hỗ trợ**, không tùy tiện thay bằng toàn bộ `Locale.getAvailableLocales()` của JDK.

## 3. Đầu vào: language range, danh sách ưu tiên và trọng số

`Locale.LanguageRange` biểu diễn **phạm vi ngôn ngữ cần khớp**. `Locale.LanguageRange.parse(...)` đọc danh sách ưu tiên ở dạng thường thấy trong giá trị header HTTP `Accept-Language`:

```java
List<Locale.LanguageRange> priority =
        Locale.LanguageRange.parse("fr-CA, fr;q=0.9, en;q=0.6");
```

Trong đó:

- `fr-CA` là yêu cầu tiếng Pháp tại Canada, mặc định có trọng số `q=1.0`.
- `fr;q=0.9` là tiếng Pháp nói chung, mức ưu tiên thấp hơn.
- `en;q=0.6` là tiếng Anh, mức ưu tiên thấp hơn nữa.
- Trọng số theo cú pháp `q` trong `[0,1]`; giá trị cao hơn được xử lý trước. Nếu cần tự tạo phạm vi: `new Locale.LanguageRange("fr", 0.9)`.

Trong ví dụ trên, thứ tự thử theo độ ưu tiên là `fr-CA` → `fr` → `en`. Hai phương thức đều nhận **danh sách range**, nhưng diễn giải cách khớp khác nhau.

**Phân biệt language range với language tag:**

- `fr`, `fr-CA`, `en` trong danh sách ưu tiên là **các tiêu chí truy vấn**.
- `fr-FR`, `fr-CA`, `en-GB` trong tập hỗ trợ là **các ứng viên thực tế**.
- `fr` theo filtering có thể khớp nhiều tag bắt đầu bằng `fr-`; theo lookup, không nên giả định tag `fr` sẽ tự động chọn một biến thể bất kỳ như `fr-FR`.

Một **basic language range** có thể là `en`, `en-US` hoặc `*`. Những mẫu chứa wildcard ở giữa như `zh-*-TW` là **extended language range**; lựa chọn chế độ lọc được bàn ở phần 7.

## 4. Ví dụ Java 17+: so sánh filtering với lookup trên cùng dữ liệu

Tạo tệp **`LocaleSelectionDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class LocaleSelectionDemo {
    private static String tags(List<Locale> locales) {
        return locales.stream()
                .map(Locale::toLanguageTag)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-CA"),
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("en-US"));

        List<Locale.LanguageRange> priorities =
                Locale.LanguageRange.parse("fr-CA, fr;q=0.9, en;q=0.6");

        List<Locale> matches = Locale.filter(priorities, supported);
        Locale selected = Locale.lookup(priorities, supported);

        System.out.println("filter: " + tags(matches));
        System.out.println("lookup: " +
                (selected == null ? "(none)" : selected.toLanguageTag()));
    }
}
```

Chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 LocaleSelectionDemo.java
java -cp . LocaleSelectionDemo
```

Kết quả:

```text
filter: fr-CA, fr-FR, en-GB, en-US
lookup: fr-CA
```

**Vì sao filtering trả bốn kết quả?**

1. Range `fr-CA` khớp `fr-CA`.
2. Range `fr` khớp `fr-FR` và `fr-CA`; locale `fr-CA` đã có nên không bị lặp.
3. Range `en` khớp `en-GB` và `en-US`.
4. `vi-VN` không khớp range nào nên bị loại. Kết quả ưu tiên các nhóm theo trọng số/range và giữ thứ tự ứng viên thích hợp trong nhóm; **không phải sắp xếp theo alphabet**.

`Locale.filter` trả danh sách các locale khớp và bảo đảm locale khớp không xuất hiện trùng. Nó **không tự quyết định** ứng dụng phải sử dụng locale nào.

**Vì sao lookup chỉ trả `fr-CA`?**

Range `fr-CA` có độ ưu tiên cao nhất và tồn tại ứng viên `fr-CA` khớp chính xác. `Locale.lookup` dừng sau khi tìm được kết quả thích hợp đầu tiên theo thuật toán, không cần liệt kê các lựa chọn `fr-FR`, `en-GB`, `en-US`.

### Cách sử dụng kết quả

Đối với trang “Ngôn ngữ đang có”, hãy dùng danh sách filtering để hiển thị mọi lựa chọn tương thích:

```java
List<Locale> choices = Locale.filter(priorities, supported);
```

Đối với quyết định giao diện của một request, hãy chọn một locale và xử lý trường hợp không khớp:

```java
Locale selected = Locale.lookup(priorities, supported);
if (selected == null) {
    selected = Locale.forLanguageTag("en-US"); // mặc định của sản phẩm
}
```

Hai đoạn trên **chỉ là trích đoạn** dùng các biến `priorities` và `supported` đã tạo trong chương trình hoàn chỉnh; không phải hai tệp Java độc lập.

## 5. Phản ví dụ quan trọng: filter có kết quả nhưng lookup không có

Một lỗi phổ biến là nghĩ `Locale.lookup` luôn chọn phiên bản vùng nào đó nếu người dùng chỉ yêu cầu ngôn ngữ tổng quát.

Giả sử ứng dụng chỉ có `fr-FR`, `en-GB`, `en-US`, và người dùng yêu cầu riêng `fr`. Với **basic filtering**, `fr` khớp `fr-FR` vì tag ứng viên là dạng cụ thể hơn cùng ngôn ngữ. Nhưng **lookup** cần tìm tag phù hợp theo thuật toán tìm kiếm chính xác/cắt subtag của *range*; `fr` không tự mở rộng thành `fr-FR`, nên nếu không có ứng viên tag `fr`, lookup có thể trả `null`.

Tạo **`FilteringVsLookupDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class FilteringVsLookupDemo {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("en-US"));

        List<Locale.LanguageRange> french =
                Locale.LanguageRange.parse("fr");

        System.out.println("filter(fr): " + Locale.filter(
                french, supported).stream()
                .map(Locale::toLanguageTag).toList());

        System.out.println("lookup(fr): " +
                Locale.lookup(french, supported));

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse("fr-CA, en-US;q=0.7");

        Locale best = Locale.lookup(preferences, supported);
        System.out.println("lookup(fr-CA, en-US): " +
                (best == null ? "(none)" : best.toLanguageTag()));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FilteringVsLookupDemo.java
java -cp . FilteringVsLookupDemo
```

Kết quả:

```text
filter(fr): [fr-FR]
lookup(fr): null
lookup(fr-CA, en-US): en-US
```

**Phân tích dòng cuối:** `fr-CA` không có trong tập hỗ trợ. Lookup có thể rút range xuống `fr`, nhưng cũng không có tag `fr` để khớp theo quy tắc lookup. Sau đó nó xét range kế tiếp `en-US` và tìm được ứng viên `en-US`. Thuật toán không tự chuyển `fr-CA` sang locale `fr-FR` chỉ vì cùng tiếng Pháp.

Vì vậy:

- **Filtering:** `fr` có thể liệt kê mọi bản địa hóa tiếng Pháp như `fr-FR`, `fr-CA`.
- **Lookup:** `fr` không mặc nhiên chọn một vùng cụ thể chưa được yêu cầu. Muốn chọn `fr-FR` làm bản địa hóa mặc định cho tiếng Pháp, **ứng dụng phải định nghĩa chính sách lựa chọn đó** (hoặc đưa vào danh sách ưu tiên/ứng viên một tag tương ứng).
- Nếu cần một locale ngay cả khi lookup trả `null`, hãy chọn một **fallback có chủ đích** nằm trong tập hỗ trợ đã được triển khai.

Đây là khác biệt về **cơ chế khớp**, không phải lỗi của Java.

## 6. Lookup không phải phương thức tự động tạo ra locale hợp lệ của sản phẩm

`Locale.lookup(...)` có thể trả `null`. Nếu ứng dụng gọi ngay `selected.toLanguageTag()`, sẽ có `NullPointerException`. Cần xử lý kết quả rỗng một cách rõ ràng.

Một cách triển khai chọn locale cho một request:

```java
import java.util.List;
import java.util.Locale;

public class ChooseLocaleDemo {
    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"));

    public static Locale choose(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return Locale.forLanguageTag("en-US");
        }

        try {
            List<Locale.LanguageRange> ranges =
                    Locale.LanguageRange.parse(acceptLanguage);
            Locale found = Locale.lookup(ranges, SUPPORTED);
            return found != null ? found : Locale.forLanguageTag("en-US");
        } catch (IllegalArgumentException invalidHeader) {
            return Locale.forLanguageTag("en-US");
        }
    }

    public static void main(String[] args) {
        System.out.println(choose("vi-VN, en-US;q=0.7").toLanguageTag());
        System.out.println(choose("ja-JP").toLanguageTag());
        System.out.println(choose(null).toLanguageTag());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ChooseLocaleDemo.java
java -cp . ChooseLocaleDemo
```

Kết quả:

```text
vi-VN
en-US
en-US
```

**Phạm vi ví dụ:** đây là cách thương lượng đơn giản cho hai locale **cụ thể**. `Locale.lookup` không tự dịch thông điệp và không bảo đảm rằng `ResourceBundle` tương ứng tồn tại. Danh sách `SUPPORTED` phải phản ánh bản dịch và các tính năng mà ứng dụng thực sự cam kết. Trong ứng dụng web, ngoài xử lý `Accept-Language`, thường cần ưu tiên lựa chọn ngôn ngữ đã lưu của người dùng theo chính sách sản phẩm, giới hạn kích thước header và xử lý đầu vào không hợp lệ.

Đối với yêu cầu “tiếng Việt” dưới dạng `vi`, nếu tập hỗ trợ chỉ có `vi-VN`, lookup không nhất thiết chọn `vi-VN`. Hãy cân nhắc mapping `vi → vi-VN`, bổ sung locale trung tính `vi` hoặc dùng một quy tắc lựa chọn được định nghĩa rõ. **Không được ngầm giả định** lookup luôn mở rộng language-only tag thành locale có region.

## 7. Filtering mode, wildcard và các biến thể của API

### 7.1. Basic filtering và extended filtering

Với **basic filtering**, range `en` khớp `en-US` và `en-GB`; range `en-US` khớp `en-US` và các tag có subtag tiếp theo thích hợp, nhưng không khớp `en-GB`. Phép so khớp không phân biệt chữ hoa/thường và phải tôn trọng **ranh giới subtag**, không đơn giản dùng `String.startsWith` cho chuỗi tùy ý.

Với **extended filtering**, range có thể chứa wildcard ở một vị trí giữa các subtag, ví dụ `zh-*-TW`. Java cho chỉ định `Locale.FilteringMode`:

- `AUTOSELECT_FILTERING`: mặc định của overload không có `mode`; tự chọn cách lọc phù hợp với loại range được cung cấp.
- `EXTENDED_FILTERING`: dùng quy tắc extended filtering.
- `IGNORE_EXTENDED_RANGES`: bỏ qua extended ranges để xử lý các basic ranges còn lại.
- `MAP_EXTENDED_RANGES`: chuyển extended ranges sang dạng cơ bản theo quy tắc ánh xạ.
- `REJECT_EXTENDED_RANGES`: báo lỗi khi danh sách chứa extended range.

Các chế độ này tác động đến **lọc**, không phải tham số của `Locale.lookup`. Không nên thay đổi mode để cố làm lookup có hành vi như filtering.

### 7.2. Dấu sao `*`

Range `*` trong filtering có thể khớp các ứng viên bất kể ngôn ngữ khi quy tắc lọc cho phép. **Lookup bỏ qua range chỉ gồm `*`**, nên `Locale.lookup(Locale.LanguageRange.parse("*"), supported)` không tự động chọn locale đầu tiên; nếu không có range khác khớp, kết quả là `null`.

Điều này quan trọng khi header `Accept-Language` chỉ nêu rằng người dùng chấp nhận ngôn ngữ bất kỳ: ứng dụng cần **chính sách mặc định**, chứ không thể trông chờ lookup luôn trả giá trị.

### 7.3. Các overload làm việc trên language tag dạng chuỗi

Nếu tập ứng viên được lưu dưới dạng chuỗi BCP 47:

```java
List<String> tags = List.of("fr-CA", "fr-FR", "en-US");
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("fr, en;q=0.5");

List<String> all = Locale.filterTags(ranges, tags);
String one = Locale.lookupTag(ranges, tags);
```

Đây là **trích đoạn** minh họa dùng `List` và `Locale`; cần import `java.util.List` và `java.util.Locale` trong một lớp Java khi sử dụng. `filterTags` trả nhiều tag; `lookupTag` trả một tag hoặc `null`. Chúng vẫn tuân theo hai cơ chế RFC 4647 khác nhau. Dùng API dạng `Locale` khi các phần tiếp theo của chương trình cần `Locale`; dạng tag hữu ích khi dữ liệu đầu vào/đầu ra là chuỗi.

## 8. Chọn cách dùng theo yêu cầu nghiệp vụ

| Tình huống | Hướng xử lý phù hợp | Lý do |
| --- | --- | --- |
| Liệt kê những ngôn ngữ giao diện mà người dùng có thể chọn | `Locale.filter` trên danh sách đã hỗ trợ | Cần **nhiều** ứng viên |
| Lọc danh sách tài liệu có bản dịch theo các ưu tiên | `Locale.filter` hoặc `filterTags` | Có thể trả nhiều tài liệu/ngôn ngữ |
| Chọn **một** ngôn ngữ để trả trang web | `Locale.lookup` rồi áp chính sách fallback | Cần một kết quả |
| Chọn **một** bản dịch email | `Locale.lookup`/`lookupTag` và kiểm tra có template | Không được giả định có template sau khi khớp |
| Người dùng yêu cầu `fr` nhưng chỉ có `fr-FR`, `fr-CA` | Cần quy tắc sản phẩm quyết định vùng mặc định hoặc hỏi người dùng | Filtering có nhiều ứng viên; lookup có thể không có kết quả |
| Không có range nào phù hợp | Fallback được định nghĩa rõ trong cấu hình | `filter` trả `[]`, `lookup` trả `null` |

**Quy trình gợi ý cho ứng dụng thực tế:**

1. Duy trì tập `supportedLocales` chỉ gồm những locale đã triển khai và kiểm thử, với thứ tự ổn định. Đừng dùng toàn bộ locale JVM làm danh sách “ứng dụng hỗ trợ”.
2. Xác định thứ tự nguồn ưu tiên: lựa chọn rõ ràng của người dùng, cấu hình tài khoản, tham số được cho phép, `Accept-Language`, mặc định ứng dụng.
3. Phân tích thành danh sách `LanguageRange` khi đầu vào là các range có trọng số; kiểm tra độ dài/định dạng đầu vào nếu nhận từ HTTP.
4. Dùng **filter** nếu nghiệp vụ cần trả nhiều lựa chọn; dùng **lookup** nếu cần quyết định một lựa chọn.
5. Nếu lookup trả `null`, dùng quy tắc fallback có chủ đích; nếu filter trả rỗng, hiển thị danh sách hoặc thông báo phù hợp.
6. Khi đã chọn locale, tiếp tục kiểm tra **tài nguyên thật** (`ResourceBundle`, bản dịch, mẫu hiển thị) và định dạng số/ngày phù hợp; khớp tag không thay thế bước bản địa hóa.
7. Kiểm thử các trường hợp: khớp chính xác, nhiều vùng cùng ngôn ngữ, thứ tự trọng số, không khớp, chỉ có `*`, range không hợp lệ và lựa chọn đã lưu của người dùng.

## 9. Những lỗi thường gặp

**Lỗi 1 — Lấy phần tử đầu của kết quả filtering và gọi đó là lookup.** Hai cơ chế có định nghĩa khớp khác nhau. Với range `fr` và duy nhất ứng viên `fr-FR`, filtering cho ra `[fr-FR]` trong khi lookup có thể là `null`. Không được coi hai cách là tương đương.

**Lỗi 2 — Dùng một `Locale` để thay cho cả danh sách ưu tiên.** Người dùng có thể chấp nhận `fr-CA`, sau đó `fr`, rồi `en` với trọng số. Nếu chỉ lấy chuỗi đầu tiên thì ứng dụng đánh mất các lựa chọn dự phòng do người dùng công bố.

**Lỗi 3 — Xử lý language range bằng so sánh chuỗi tùy tiện.** `en` và `en-US` có quan hệ subtag, nhưng `startsWith("en")` không tự thực hiện chuẩn RFC 4647, kiểm soát vùng, wildcard hoặc độ ưu tiên. Hãy dùng API matching.

**Lỗi 4 — Tưởng `Locale.lookup` luôn tìm được một kết quả.** Kết quả hợp lệ có thể là `null`; mọi chỗ dùng phải có nhánh xử lý trường hợp này.

**Lỗi 5 — Dùng tập ứng viên gồm mọi locale JDK biết.** Điều đó chỉ mô tả khả năng locale của runtime, không chứng minh các tệp ngôn ngữ và nội dung của sản phẩm đã có.

**Lỗi 6 — Nhầm lựa chọn locale với tải tài nguyên.** `Locale.filter` và `Locale.lookup` chỉ giải quyết **matching**; `ResourceBundle` và hệ thống i18n còn có fallback riêng, cần được kiểm thử.

**Lỗi 7 — Không kiểm soát trường hợp ưu tiên chỉ có `*`.** Filtering và lookup xử lý wildcard khác nhau; không được tự tin rằng lookup sẽ chọn locale bất kỳ.

## 10. Ghi nhớ

- `Locale.filter` trả về **danh sách tất cả locale phù hợp**, thích hợp cho bộ lọc hoặc danh sách lựa chọn.
- `Locale.lookup` trả về **một locale phù hợp nhất** theo cơ chế lookup, hoặc **`null`**. Nó không tương đương lấy phần tử đầu tiên của filtering.
- `Locale.LanguageRange.parse` giúp biểu diễn danh sách ưu tiên và trọng số (thường từ `Accept-Language`).
- **Range ngôn ngữ tổng quát `fr` có thể lọc được `fr-FR` nhưng lookup vẫn không chọn `fr-FR` nếu thiếu tag phù hợp theo lookup.** Muốn mặc định một vùng, sản phẩm cần chính sách rõ ràng.
- Hãy truyền **chỉ các locale ứng dụng thật sự hỗ trợ**, xử lý kết quả rỗng và kiểm thử nội dung sau khi chọn. Matching là bước chọn locale; chất lượng bản địa hóa là trách nhiệm tiếp theo.
