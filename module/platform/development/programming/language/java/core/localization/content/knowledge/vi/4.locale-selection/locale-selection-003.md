# Locale.LanguageRange và trọng số ưu tiên

## 1. Vì sao phải thương lượng ngôn ngữ?

Trong ứng dụng đa ngôn ngữ, người dùng có thể chấp nhận nhiều ngôn ngữ với mức ưu tiên khác nhau. Ví dụ một trình duyệt gửi:

```http
Accept-Language: fr-CA, fr;q=0.8, en-US;q=0.6, en;q=0.4
```

Người dùng ưu tiên tiếng Pháp Canada (`fr-CA`); nếu không thể phục vụ thì tiếp theo là tiếng Pháp nói chung (`fr`), tiếng Anh Mỹ (`en-US`), và tiếng Anh (`en`). Ứng dụng phải so khớp danh sách đó với **những bản dịch thực sự có sẵn**, sau đó chọn phương án hợp lệ hoặc fallback được cấu hình.

Java cung cấp `java.util.Locale.LanguageRange` và các phương thức `Locale.filter`, `Locale.filterTags`, `Locale.lookup`, `Locale.lookupTag` để thực hiện một phần quan trọng của quy trình này theo RFC 4647. Cơ chế xuất hiện từ Java 8 và dùng tốt trên Java 17+.

Phân biệt ba khái niệm:

- **Language tag**: mã BCP 47 xác định ngôn ngữ hoặc biến thể, như `en`, `en-US`, `zh-Hant-TW`.
- **Language range**: biểu thức đối chiếu một hay nhiều tag, như `en`, `fr-CA`, `*`, `zh-Hant-*`.
- **Language Priority List**: danh sách `Locale.LanguageRange` theo thứ tự ưu tiên, trong đó mỗi mục có một trọng số `weight`.

Một `LanguageRange` **không** phải đối tượng `Locale` đã chọn, và cũng không đại diện cho tệp bản dịch. Nó là **điều kiện và mức độ ưu tiên** để chọn từ các ngôn ngữ hệ thống có.

## 2. Cấu trúc và API của `Locale.LanguageRange`

| API | Tác dụng |
| --- | --- |
| `new Locale.LanguageRange("fr-CA")` | Tạo range với weight mặc định `1.0` |
| `new Locale.LanguageRange("en-US", 0.6)` | Tạo range có trọng số `0.6` |
| `getRange()` | Trả về range, ví dụ `"en-us"` |
| `getWeight()` | Trả về mức ưu tiên kiểu `double` |
| `MIN_WEIGHT` | `0.0` |
| `MAX_WEIGHT` | `1.0` |
| `Locale.LanguageRange.parse(text)` | Parse danh sách ưu tiên từ chuỗi |
| `parse(text, map)` | Parse rồi tùy biến bằng ánh xạ tương đương |
| `mapEquivalents(list, map)` | Tạo danh sách được tùy biến theo các range tương đương |

Hàm dựng kiểm tra cú pháp language range và khoảng trọng số `0.0` đến `1.0`. Range `null` gây `NullPointerException`; cú pháp sai hoặc weight ngoài khoảng gây `IllegalArgumentException`. Việc kiểm tra cú pháp không đồng nghĩa xác thực một subtag đã được đăng ký trong IANA, và không chứng minh ứng dụng có bản dịch cho ngôn ngữ tương ứng.

RFC 4647 phân biệt:

- **Basic language range**: `en`, `ja-JP`, `fr-CA` hoặc `*` (wildcard toàn bộ).
- **Extended language range**: `*-CH`, `es-*`, `zh-Hant-*`. Wildcard có thể xuất hiện trong một thành phần của range.

Sự phân biệt này quan trọng khi chọn filtering mode. Chữ hoa/thường của language tag không ảnh hưởng kết quả matching; API dùng đối chiếu không phân biệt case.

## 3. Trọng số `q` hoạt động thế nào?

Trong danh sách `Accept-Language`, `q` là *quality value*, thể hiện mức độ ưa thích:

```text
fr-CA, fr;q=0.8, en-US;q=0.6, en;q=0.4
```

| Range | q | Nghĩa trong ví dụ |
| --- | ---: | --- |
| `fr-CA` | `1.0` | Ưu tiên cao nhất; không khai báo q thì mặc định 1.0 |
| `fr` | `0.8` | Ưu tiên kế tiếp |
| `en-US` | `0.6` | Chấp nhận với độ ưu tiên thấp hơn |
| `en` | `0.4` | Phương án sau cùng trong danh sách này |

Các trọng số **không phải xác suất** và không cần có tổng bằng 1.0. Đó là các mức ưu tiên tương đối. Nếu range ở mức ưu tiên cao nhất không khớp bất kỳ nội dung được hỗ trợ nào, ứng dụng tiếp tục xem các lựa chọn khác.

- Trọng số hợp lệ từ `0.0` đến `1.0`; bỏ qua `q` thì lấy `1.0`.
- `q=0` biểu thị không chấp nhận phạm vi tương ứng trong HTTP. Khi Java filtering trên các range cơ bản, range có weight 0 bị loại khỏi lựa chọn.
- Với danh sách không có `q`, thứ tự xuất hiện là thứ tự ưu tiên.
- Khi parse danh sách có `q`, Java sắp xếp theo trọng số giảm dần. Không tự sắp xếp lại theo tên language tag.
- Khi một range xuất hiện nhiều lần trong chuỗi đầu vào, Java giữ **lần xuất hiện đầu tiên**, không cộng hay lấy trung bình các weight.

Vì mức ưu tiên khác khả năng cung cấp, ứng dụng cần danh sách hỗ trợ (supported languages) riêng.

## 4. Parse một danh sách ưu tiên

`Locale.LanguageRange.parse(String)` nhận chuỗi phân cách bằng dấu phẩy và cả dạng có tiền tố `Accept-Language:`. Nó kiểm tra cú pháp, đọc `q`, sắp xếp danh sách theo ưu tiên và có thể bổ sung mã ngôn ngữ tương đương theo IANA.

Ví dụ Java 17+ chạy độc lập:

```java
import java.util.List;
import java.util.Locale;

public class LanguageRangeParseDemo {
    public static void main(String[] args) {
        String header = "fr-CA, fr;q=0.8, en-US;q=0.6, en;q=0.4";
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(header);

        for (Locale.LanguageRange preference : preferences) {
            System.out.printf(Locale.ROOT, "%s -> %.1f%n",
                    preference.getRange(),
                    preference.getWeight());
        }
    }
}
```

Lưu `LanguageRangeParseDemo.java` bằng UTF-8; chạy với JDK 17+:

```bash
javac -encoding UTF-8 LanguageRangeParseDemo.java
java LanguageRangeParseDemo
```

Stdout:

```text
fr-ca -> 1.0
fr -> 0.8
en-us -> 0.6
en -> 0.4
```

`getRange()` trả range dạng chữ thường, `getWeight()` trả số. Dùng `Locale.ROOT` trong `printf` để cố định cách hiển thị dấu thập phân của ví dụ, độc lập locale mặc định của máy.

**Lưu ý về alias:** `parse` có thể thêm mã tương đương trong IANA Language Subtag Registry. Ví dụ, mã Hebrew cũ `iw` có thể đi cùng `he` với cùng trọng số. Vì thế số phần tử sau parse có thể lớn hơn số range gốc. Đừng viết code giả định phần tử đầu là range thứ nhất trong header và mọi header chỉ sinh đúng từng ấy phần tử.

## 5. Filtering và lookup: tìm tất cả hay chọn một?

Java hỗ trợ hai họ phương thức đối chiếu:

| Họ API | Đầu vào có sẵn | Kết quả |
| --- | --- | --- |
| `Locale.filter(...)` | `Collection<Locale>` | Nhiều `Locale` khớp, có thứ tự |
| `Locale.filterTags(...)` | `Collection<String>` chứa BCP 47 tag | Nhiều string tag khớp, có thứ tự |
| `Locale.lookup(...)` | `Collection<Locale>` | Một `Locale` tốt nhất, hoặc `null` |
| `Locale.lookupTag(...)` | `Collection<String>` | Một string tag tốt nhất, hoặc `null` |

**Filtering** hỏi “mọi tag nào phù hợp với ưu tiên của người dùng?”. Với range cơ bản `fr`, cả `fr-FR` và `fr-CA` có thể khớp.

**Lookup** hỏi “tag cụ thể nào là lựa chọn gần nhất?”. Theo RFC 4647, nó thử từ range có mức ưu tiên cao rồi dần rút các subtag để tìm ứng viên. Ví dụ `zh-Hant-TW` có thể hạ xuống `zh-Hant`, rồi `zh`. Lookup không phải một thuật toán đo mức độ gần nhau về ngữ nghĩa của tất cả ngôn ngữ.

Ví dụ chạy được trên JDK 17+:

```java
import java.util.List;
import java.util.Locale;

public class LanguageMatchingDemo {
    public static void main(String[] args) {
        List<String> supported = List.of(
                "en-US", "fr-FR", "fr-CA", "vi-VN");
        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(
                        "fr-CA, en-US;q=0.8, fr;q=0.5");

        System.out.println(Locale.filterTags(preferences, supported));
        System.out.println(Locale.lookupTag(preferences, supported));

        var chinese =
                Locale.LanguageRange.parse("zh-Hant-TW, en-US;q=0.8");
        System.out.println(Locale.lookupTag(
                chinese,
                List.of("zh-Hant", "en-US", "zh-Hans-CN")));
    }
}
```

Lưu `LanguageMatchingDemo.java`, sau đó:

```bash
javac -encoding UTF-8 LanguageMatchingDemo.java
java LanguageMatchingDemo
```

Stdout:

```text
[fr-CA, en-US, fr-FR]
fr-CA
zh-Hant
```

Hàng thứ nhất trả **mọi** tag khớp theo ưu tiên; hàng thứ hai chỉ chọn `fr-CA`; hàng thứ ba chứng minh `lookupTag` có thể tìm `zh-Hant` khi không có `zh-Hant-TW`.

Khi không có ứng viên phù hợp, `lookupTag` và `lookup` trả `null`. Ứng dụng phải kiểm tra kết quả trước khi dùng và quyết định một fallback cụ thể.

## 6. Wildcard và chế độ lọc

Basic range `*` đại diện cho wildcard toàn bộ và có thể giúp filtering trả nhiều tag. Nhưng với lookup, **range chỉ gồm `*` bị bỏ qua**, nên không được xem `*` là bảo đảm lookup sẽ chọn một tag bất kỳ.

Với extended ranges như `zh-Hant-*` hoặc `*-CH`, có thể gọi:

```java
Locale.filterTags(preferences, supportedTags,
        Locale.FilteringMode.EXTENDED_FILTERING)
```

Các giá trị trong `Locale.FilteringMode`:

- `AUTOSELECT_FILTERING`: hành vi mặc định, tự chọn cách lọc dựa trên range.
- `EXTENDED_FILTERING`: sử dụng extended filtering.
- `IGNORE_EXTENDED_RANGES`: bỏ qua các range mở rộng.
- `MAP_EXTENDED_RANGES`: ánh xạ range mở rộng sang dạng cơ bản để lọc.
- `REJECT_EXTENDED_RANGES`: phát sinh `IllegalArgumentException` nếu danh sách chứa extended range.

Không nên tự xử lý wildcard bằng `startsWith` hoặc regex tùy tiện vì dễ làm sai ranh giới subtag và các quy tắc RFC. Hãy chọn filtering mode dựa trên phạm vi mà sản phẩm muốn chấp nhận.

Ví dụ ngắn chứng minh `q=0` không được chọn trong filtering:

```java
import java.util.List;
import java.util.Locale;

public class ZeroWeightDemo {
    public static void main(String[] args) {
        var ranges = Locale.LanguageRange.parse("en;q=0, fr;q=1");
        var supported = List.of("en-US", "fr-FR");
        System.out.println(Locale.filterTags(ranges, supported));
    }
}
```

Lưu `ZeroWeightDemo.java`, chạy:

```bash
javac -encoding UTF-8 ZeroWeightDemo.java
java ZeroWeightDemo
```

Stdout:

```text
[fr-FR]
```

Dù `en-US` nằm trong danh sách hỗ trợ, `en` có `q=0` nên không được trả về. Trong triển khai giao thức HTTP đầy đủ, cần tiếp tục xét những yêu cầu của HTTP như các range chồng lấn. Không nên thay thế mọi quy tắc thương lượng HTTP bằng một hàm tự sắp xếp đơn giản.

## 7. Ví dụ chọn ngôn ngữ có fallback

Giả sử ứng dụng có tài nguyên chỉ cho `vi-VN`, `en-US` và `fr-FR`. Không nên dùng `Locale.getAvailableLocales()` làm danh sách ngôn ngữ hỗ trợ: JDK có thể biết cách định dạng dữ liệu cho một ngôn ngữ mà ứng dụng chưa có bản dịch UI của ngôn ngữ đó.

Một quy trình rõ ràng là nhận danh sách ưu tiên, parse, lookup trong tập hỗ trợ, rồi fallback theo chính sách sản phẩm:

```java
import java.util.List;
import java.util.Locale;

public class SelectLanguageDemo {
    private static final List<String> SUPPORTED =
            List.of("vi-VN", "en-US", "fr-FR");
    private static final String DEFAULT_TAG = "vi-VN";

    static String selectLanguage(String headerValue) {
        if (headerValue == null || headerValue.isBlank()) {
            return DEFAULT_TAG;
        }

        List<Locale.LanguageRange> ranges =
                Locale.LanguageRange.parse(headerValue);
        String chosen = Locale.lookupTag(ranges, SUPPORTED);

        return chosen == null ? DEFAULT_TAG : chosen;
    }

    public static void main(String[] args) {
        System.out.println(selectLanguage("fr-FR, en-US;q=0.5"));
        System.out.println(selectLanguage("ja-JP"));
        System.out.println(selectLanguage(null));
    }
}
```

Lưu `SelectLanguageDemo.java`, chạy:

```bash
javac -encoding UTF-8 SelectLanguageDemo.java
java SelectLanguageDemo
```

Stdout:

```text
fr-FR
vi-VN
vi-VN
```

Trong ví dụ, `Locale.LanguageRange.parse` sẽ ném `IllegalArgumentException` nếu header sai cú pháp. Hàm trên để exception lan ra ngoài nhằm tách việc chọn ngôn ngữ khỏi chính sách xử lý HTTP. Tại ranh giới request của ứng dụng thật, cần giới hạn chiều dài header, quyết định trả lỗi hay fallback, và kiểm tra input trước khi tạo response.

Nếu người dùng chọn trực tiếp ngôn ngữ trong phần cài đặt tài khoản, sản phẩm có thể áp dụng lựa chọn ấy trước `Accept-Language`. Header phản ánh sở thích được gửi từ client, không nhất thiết là lựa chọn cuối cùng mà người dùng đã thiết lập trong ứng dụng.

Sau khi chọn được tag, ứng dụng có thể tạo đối tượng `Locale.forLanguageTag(chosen)` cho những API định dạng theo locale. Khi dùng `ResourceBundle` hay framework dịch UI, cần kiểm tra quy tắc lookup và fallback tài nguyên riêng; matching thành công không tự tạo bản dịch thiếu.

## 8. Range tương đương và `mapEquivalents`

Trong dữ liệu ngôn ngữ có những mã cũ được thay bằng mã hiện hành. `parse` có thể bổ sung range tương đương theo IANA để hỗ trợ tìm tag tương ứng. Đối với yêu cầu đặc thù, có thêm:

```java
Locale.LanguageRange.parse(
        String ranges,
        Map<String, List<String>> map)

Locale.LanguageRange.mapEquivalents(
        List<Locale.LanguageRange> priorityList,
        Map<String, List<String>> map)
```

Bản parse có map tương đương `mapEquivalents(parse(ranges), map)`. Các range được ánh xạ mang trọng số của range gốc. Nhưng ánh xạ tùy chỉnh **có thể thay thế** hoặc **mở rộng** tùy cách khai báo map; nếu muốn giữ cả range gốc, phải đưa lựa chọn ấy vào danh sách tương đương. Đây là chính sách có tác động đến kết quả thương lượng, cần có lý do nghiệp vụ rõ ràng.

Đặc biệt, `zh-Hans` và `zh-Hant` biểu thị các hệ chữ khác nhau; không tự coi mọi biến thể của tiếng Trung là có thể thay thế nhau. Mức độ phù hợp tùy tài nguyên thực sự của ứng dụng.

## 9. Lỗi phổ biến

1. **Cho rằng q là phần trăm/xác suất.** Các trọng số chỉ xếp ưu tiên và không cần cộng lại bằng 1.
2. **Tự split rồi sắp xếp theo alphabet.** Thứ tự và q phải được parser xử lý; các alias cũng cần xét.
3. **Nhầm language range với language tag cụ thể.** Range `fr` có thể khớp nhiều tag khi filtering.
4. **Tưởng filter và lookup tương đương.** Một phương thức trả nhiều ứng viên; phương thức còn lại chỉ chọn một và có quy tắc fallback theo subtag.
5. **Không xử lý lookup trả `null`.** Danh sách yêu cầu có thể không khớp bất kỳ bản dịch nào.
6. **Coi `*` là fallback tự động cho lookup.** Range chỉ gồm `*` bị bỏ qua trong lookup; fallback phải do ứng dụng quyết định.
7. **Bỏ qua extended range.** `*-CH` và `zh-Hant-*` cần lựa chọn mode rõ ràng.
8. **Giả định số mục sau parse bằng số mục header.** Parser có thể mở rộng alias IANA và loại range trùng.
9. **Dùng mọi locale của JDK làm nguồn dịch UI.** Tập locale JDK biết và tập nội dung sản phẩm cung cấp là hai chuyện khác nhau.
10. **Tin tưởng header từ bên ngoài tuyệt đối.** Header có thể trống, sai cú pháp hay dài bất thường; cần quy tắc xử lý tại ranh giới request.
11. **Phụ thuộc thứ tự `Set` không ổn định.** Khi nhiều ứng viên tương đương, thứ tự duyệt collection có thể ảnh hưởng lựa chọn. Dùng danh sách có thứ tự xác định khi cần kết quả ổn định.
12. **Tưởng thương lượng tag là toàn bộ hệ thống i18n.** Việc tải tài nguyên, định dạng số, ngày giờ và fallback bản dịch cần thêm chính sách riêng.

## 10. Kiểm thử một bộ chọn locale

Một bộ test có giá trị nên kiểm tra:

- Danh sách có nhiều q, q mặc định `1.0`, q bằng `0`, q ngoài khoảng hợp lệ.
- Range basic và extended, wildcard `*`, các filtering mode cần hỗ trợ.
- Kết quả `filterTags` có thể chứa nhiều ứng viên; `lookupTag` chọn một hoặc trả `null`.
- Trường hợp `zh-Hant-TW` rút còn `zh-Hant`; trường hợp không có ứng viên nào.
- Mã lịch sử có alias, range trùng lặp và range không hợp lệ.
- Header rỗng, `null`, dữ liệu lỗi và dài quá mức.
- Fallback sản phẩm khác với locale mặc định của server.
- Đầu ra nhất quán khi danh sách ngôn ngữ hỗ trợ được giữ thứ tự ổn định.

Có thể viết kiểm thử cho `selectLanguage` bằng các input xác định mà không phải thay `Locale.setDefault`; việc thương lượng không nên phụ thuộc locale mặc định của máy chạy.

## 11. Ghi nhớ

`Locale.LanguageRange` diễn đạt **ngôn ngữ nào người dùng muốn và mức độ ưu tiên của họ**. `parse` biến một chuỗi có `q` thành danh sách có cấu trúc. `filterTags` trả các tag phù hợp; `lookupTag` tìm một ứng viên tốt nhất. Quyết định cuối cùng vẫn phải dựa trên danh sách bản dịch thực có, chính sách fallback, xử lý đầu vào và cách tải tài nguyên.

Tài liệu chính thức để tra cứu thêm:

- [Oracle Java 21 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.LanguageRange.html)
- [Oracle Java 21 — Locale Matching](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647)
- [RFC 9110 — HTTP Accept-Language](https://www.rfc-editor.org/rfc/rfc9110#name-accept-language)
