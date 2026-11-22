# Phân tích danh sách ưu tiên ngôn ngữ bằng Locale.LanguageRange.parse trong Java

## 1. Danh sách ưu tiên ngôn ngữ là gì?

Người dùng có thể chấp nhận nhiều ngôn ngữ nhưng không thích tất cả ngang nhau. Trong HTTP, header `Accept-Language` có thể truyền danh sách ưu tiên như sau:

```http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.7,en;q=0.5
```

Trong chuỗi này, dấu phẩy phân cách các **language range**; `q` (*quality value*) biểu thị trọng số ưu tiên của từng range. Java cung cấp `java.util.Locale.LanguageRange.parse(String)` để phân tích chuỗi thành một **Language Priority List** dạng `List<Locale.LanguageRange>`.

Mỗi đối tượng `LanguageRange` cho phép đọc:

- `getRange()`: language range sau khi chuẩn hóa, chẳng hạn `"vi-vn"`, `"en-us"` hoặc `"*"`.
- `getWeight()`: trọng số ưu tiên dạng `double`, từ `0.0` đến `1.0`.

**Phân tích không phải lựa chọn:** `parse` chỉ tạo danh sách. Nó không biết ứng dụng có những ngôn ngữ nào, không tải bản dịch và không tự chọn bản địa hóa cuối cùng. Sau `parse`, ứng dụng mới áp dụng `Locale.filter`, `Locale.filterTags`, `Locale.lookup` hoặc `Locale.lookupTag` lên tập locale thực sự được hỗ trợ.

## 2. Cú pháp language range và trọng số `q`

`LanguageRange.parse` hỗ trợ các kiểu input thông dụng:

```text
vi,en;q=0.5
Accept-Language: vi,en;q=0.5
vi,en
```

Cú pháp language range được mô tả bởi **RFC 4647**, liên quan với language tag BCP 47. Hai loại range quan trọng:

| Dạng | Ví dụ | Ý nghĩa |
|---|---|---|
| Basic | `vi` | Ưu tiên ngôn ngữ tiếng Việt |
| Basic | `en-US` | Ưu tiên tiếng Anh tại Hoa Kỳ |
| Basic wildcard | `*` | Mẫu khớp bất kỳ, tùy thuật toán matching |
| Extended | `zh-Hant-*` | Tiếng Trung chữ Hán phồn thể, phần sau tùy ý |
| Extended | `*-CH` | Mẫu có region `CH` khi dùng extended filtering |

Một basic range có một nhóm 1–8 chữ cái, có thể kèm các nhóm `-` và 1–8 ký tự chữ/số; hoặc chỉ có `*`. Extended range cho phép `*` ở một số vị trí subtag. Dấu `*` là **ký tự mẫu**, không phải tên của một ngôn ngữ có thể dịch.

Bảng quy tắc `q`:

| Giá trị | Diễn giải |
|---|---|
| Không có `q` | Mặc định `1.0`, tương ứng `MAX_WEIGHT` |
| `q=1.0` | Mức ưu tiên tối đa |
| `q=0.8` | Có ưu tiên nhưng thấp hơn `1.0` |
| `q=0` | Mức thấp nhất `MIN_WEIGHT`; trong ngữ cảnh HTTP thường nghĩa là không chấp nhận range đó |
| `q=1.2` hoặc `q=-0.1` | Sai vì nằm ngoài khoảng `[0.0, 1.0]`; `parse` ném `IllegalArgumentException` |

Không cộng các trọng số để ra 1; chúng **không phải xác suất**. `q` cũng không phải điểm chất lượng bản dịch. Dấu `;q=` gắn với range ngay trước nó, còn dấu phẩy ngăn các range khác nhau.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu mã vào tệp `LanguagePriorityDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LanguagePriorityDemo {
    public static void main(String[] args) {
        String header =
                "Accept-Language: en-US;q=0.6, vi;q=1.0, fr;q=0.8, en-GB;q=0.3";

        List<Locale.LanguageRange> preferences =
                Locale.LanguageRange.parse(header);

        for (Locale.LanguageRange preference : preferences) {
            System.out.printf(
                    "%s -> %.1f%n",
                    preference.getRange(),
                    preference.getWeight());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LanguagePriorityDemo.java
java LanguagePriorityDemo
```

Đầu ra:

```text
vi -> 1.0
fr -> 0.8
en-us -> 0.6
en-gb -> 0.3
```

Điều cần quan sát: `vi` được đưa lên đầu dù xuất hiện sau `en-US` trong chuỗi gốc; danh sách được **sắp xếp theo trọng số giảm dần**. Các range `en-US`, `en-GB` được chuẩn hóa thành chữ thường ở `getRange()`. `printf("%.1f")` chỉ dùng để biểu diễn ví dụ; không làm tròn giá trị `double` trước khi thực hiện logic ưu tiên.

`parse` trả một `List` có thể sửa đổi. Tuy nhiên, khi phân tích header từ người dùng, nên chuyển danh sách kết quả qua bước matching mà không vô tình sắp xếp lại hoặc sửa trọng số.

## 4. Thứ tự ưu tiên, trường hợp trùng và equivalent range

### Không có `q`

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("vi,en-US,fr");
```

Tất cả range có trọng số `1.0`. Thứ tự khai báo `vi` → `en-us` → `fr` được giữ theo ưu tiên của danh sách gốc. Với input không có `q`, mục đứng trước thể hiện ưu tiên trước.

### Có `q`

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("en-US;q=0.4,vi;q=0.9,fr;q=0.6");
```

Kết quả được sắp thành `vi (0.9)` → `fr (0.6)` → `en-us (0.4)`. Do vậy không nên xử lý trực tiếp thứ tự chuỗi đầu vào khi có trọng số.

### Range trùng nhau: giữ **lần xuất hiện đầu tiên**

```java
List<Locale.LanguageRange> ranges = Locale.LanguageRange.parse(
        "en-US;q=0.2, fr;q=0.8, en-US;q=0.9");

for (Locale.LanguageRange range : ranges) {
    System.out.printf("%.1f %s%n",
            range.getWeight(), range.getRange());
}
```

Đầu ra:

```text
0.8 fr
0.2 en-us
```

`en-US` thứ hai có trọng số `0.9` **không thay thế** mục đầu tiên `0.2`. Java chỉ giữ lần xuất hiện đầu của range trùng, sau đó sắp xếp danh sách theo trọng số.

### IANA equivalents: output có thể dài hơn input

`parse` tự bổ sung các **language range tương đương** có trong dữ liệu IANA Language Subtag Registry. Ví dụ mã cũ `iw` (Hebrew) và mã mới `he`:

```java
List<Locale.LanguageRange> ranges =
        Locale.LanguageRange.parse("iw,en;q=0.5");
```

Trên Java 17+, danh sách có các mục sau:

| Range | Weight |
|---|---:|
| `iw` | 1.0 |
| `he` | 1.0 |
| `en` | 0.5 |

Hai mã Hebrew cùng mức ưu tiên; việc thêm `he` giúp bước matching phát hiện tag hỗ trợ dùng mã mới. **Số phần tử sau parse có thể lớn hơn số mục được ngăn bằng dấu phẩy.** Không viết logic giả định một input range sẽ cho đúng một object. Danh sách tương đương có thể phụ thuộc dữ liệu IANA/JDK theo phiên bản.

## 5. Phân biệt `Locale.LanguageRange` với `Locale`

Một `Locale` như `Locale.forLanguageTag("en-US")` mô tả một đối tượng locale cụ thể. `LanguageRange("en")` mô tả **một yêu cầu matching**, có thể đối chiếu với nhiều tag như `en-US`, `en-GB` theo quy tắc filtering.

- `Locale.forLanguageTag("vi-VN")` nhận **một** language tag BCP 47.
- `Locale.LanguageRange.parse("vi-VN, en;q=0.7")` nhận **danh sách** range gắn trọng số.
- `Locale.filterTags(priorityList, supportedTags)` tìm **nhiều** tag được hỗ trợ phù hợp.
- `Locale.lookupTag(priorityList, supportedTags)` tìm **một** tag được hỗ trợ theo quy tắc lookup, hoặc trả `null`.

Không truyền nguyên header `Accept-Language` cho `Locale.forLanguageTag(...)`: đầu vào có dấu phẩy và `q` là chuỗi danh sách, không phải một tag đơn.

## 6. Matching sau `parse`: filtering khác lookup

`parse` không xác định ngôn ngữ phục vụ. Bước tiếp theo phải biết tập các locale mà dịch vụ thực sự cung cấp. Ví dụ có ba ngôn ngữ hỗ trợ `fr-FR`, `en-US`, `vi-VN`.

Tạo tệp `LanguageMatchingDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LanguageMatchingDemo {
    public static void main(String[] args) {
        List<Locale.LanguageRange> priorities =
                Locale.LanguageRange.parse(
                        "fr-CA, fr;q=0.8, en-US;q=0.5");

        List<String> supported =
                List.of("fr-FR", "en-US", "vi-VN");

        System.out.println(Locale.filterTags(priorities, supported));
        System.out.println(Locale.lookupTag(priorities, supported));
    }
}
```

Chạy:

```bash
javac LanguageMatchingDemo.java
java LanguageMatchingDemo
```

Output đã kiểm tra:

```text
[fr-FR, en-US]
en-US
```

**Vì sao khác nhau?** `filterTags` dùng quy tắc filtering của RFC 4647 và tìm được `fr-FR` từ range `fr`. `lookupTag` dùng thuật toán lookup, so các range theo ưu tiên và quy tắc rút bớt subtags; nó không tự suy ra `fr-CA` cần fallback sang `fr-FR` như con người có thể mong muốn. Với tập ứng viên này, lookup tìm được `en-US`.

Đừng coi `lookupTag` là fuzzy matching theo văn hóa. Nếu sản phẩm muốn quy tắc riêng `fr-CA` → `fr-FR`, phải thiết kế rõ bằng tập ưu tiên/ánh xạ hoặc cơ chế fallback của sản phẩm. `filterTags` dùng để liệt kê các lựa chọn phù hợp; `lookupTag` dùng khi cần một tag phù hợp theo lookup.

Khi danh sách ứng viên là `Collection<Locale>` thay vì `Collection<String>`, chọn `Locale.filter(...)` hoặc `Locale.lookup(...)`. Các phương thức `*Tags` chỉ thao tác với chuỗi tag.

## 7. Wildcard, extended range, `q=0` và chế độ filtering

**Wildcard `*`:** `"vi;q=1.0,*;q=0.1"` cho phép cân nhắc các tag khác khi không có lựa chọn ưu tiên cao phù hợp, tùy thuật toán matching. Dấu `*` không phải một bản dịch hay mã locale riêng.

**Extended range:** `"zh-Hant-*"` và `"*-CH"` hợp lệ dưới cú pháp extended language range. Khi gọi `Locale.filterTags` với các mẫu này, phải hiểu `Locale.FilteringMode`, nhất là `EXTENDED_FILTERING`. Một số chế độ chuyển extended range thành basic range, bỏ qua hoặc từ chối chúng. Không mặc định rằng tất cả chế độ có cùng semantics của dấu `*` trong subtags.

**Trọng số `q=0`:** Trong HTTP, q=0 thể hiện không muốn phạm vi ngôn ngữ tương ứng. `parse` vẫn trả phần tử này với `getWeight()==0.0`. Quy tắc lọc/loại trừ thuộc bước matching, đặc biệt cần kiểm thử khi có wildcard và nhiều range chồng lấn. Đừng tự chọn phần tử thứ nhất sau `parse` hoặc lấy tất cả range có `q` không âm và coi chúng đều được chấp nhận.

## 8. Phát hiện input sai cú pháp

`LanguageRange.parse` thực hiện **syntactic validation**, không xác nhận mỗi mã nằm trong IANA Language Subtag Registry hoặc có bản dịch trên server.

| Input | Xử lý |
|---|---|
| `"vi,en;q=0.5"` | Hợp lệ |
| `"en;q=0"` | Hợp lệ, trọng số bằng 0 |
| `"en;q=1.2"` | `IllegalArgumentException` vì trọng số lớn hơn 1 |
| `"en;q=-0.1"` | `IllegalArgumentException` vì trọng số âm |
| `"en--US"` | `IllegalArgumentException` vì có subtag rỗng |
| `null` | `NullPointerException` |
| Mã đúng mẫu nhưng không có trong bảng hỗ trợ | Có thể parse thành công; xử lý ở bước hỗ trợ/matching |

Tạo tệp `ParseLanguageRangesSafely.java`:

```java
import java.util.List;
import java.util.Locale;

public class ParseLanguageRangesSafely {
    public static void main(String[] args) {
        String raw = "en;q=1.2";

        try {
            List<Locale.LanguageRange> ranges =
                    Locale.LanguageRange.parse(raw);
            System.out.println("Parsed: " + ranges.size());
        } catch (IllegalArgumentException exception) {
            System.out.println("Invalid language preferences");
        }
    }
}
```

Chạy `javac ParseLanguageRangesSafely.java` và `java ParseLanguageRangesSafely`. Kết quả:

```text
Invalid language preferences
```

Với dữ liệu header thật, kiểm tra `null`, dữ liệu trống và giới hạn độ dài, bắt `IllegalArgumentException`, rồi fallback theo **chính sách ứng dụng**. Nếu đầu vào bị lỗi, không dùng giá trị chưa kiểm tra để xây dựng đường dẫn tài nguyên hoặc tự đổi default locale chung của toàn máy chủ.

## 9. Overload `parse(String, Map)`: ánh xạ tương đương tùy chỉnh

Ngoài `parse(String)`, Java còn có:

```java
List<Locale.LanguageRange> result =
        Locale.LanguageRange.parse(raw, equivalents);
```

Trong đó `equivalents` là `Map<String, List<String>>` định nghĩa những range ứng dụng muốn coi là tương đương. Nó hoạt động tương đương:

```java
Locale.LanguageRange.mapEquivalents(
        Locale.LanguageRange.parse(raw),
        equivalents);
```

Ví dụ minh họa, nếu đã có biến `raw` và import `java.util.Map`, `java.util.List`:

```java
Map<String, List<String>> equivalents =
        Map.of("zh", List.of("zh-hans", "zh-hant"));
List<Locale.LanguageRange> preferences =
        Locale.LanguageRange.parse(raw, equivalents);
```

Ánh xạ này diễn ra sau phần bổ sung equivalent từ IANA và giữ trọng số gốc. Tuy nhiên, **đây chỉ là ví dụ API**, không phải khuyến nghị trộn hai hệ chữ Hán làm một; trong giao diện thật, `zh-Hans` và `zh-Hant` có thể cần bản dịch riêng biệt. Chỉ áp dụng custom map khi có quy tắc nghiệp vụ được thiết kế rõ, không coi nó là cách bổ sung bản dịch vào server.

## 10. Một chính sách fallback hoàn chỉnh

Giả sử sản phẩm hỗ trợ đúng `vi-VN`, `en-US` và `fr-FR`. Ta có thể chọn một tag bằng `lookupTag`; nếu không tìm được hoặc chuỗi đầu vào sai, trả về locale mặc định **đã được server hỗ trợ**.

Tạo tệp `SelectSupportedLocale.java`:

```java
import java.util.List;
import java.util.Locale;

public class SelectSupportedLocale {
    private static final List<String> SUPPORTED =
            List.of("vi-VN", "en-US", "fr-FR");

    public static String select(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return "en-US";
        }

        try {
            List<Locale.LanguageRange> priorities =
                    Locale.LanguageRange.parse(acceptLanguage);

            String match = Locale.lookupTag(priorities, SUPPORTED);
            return match != null ? match : "en-US";
        } catch (IllegalArgumentException exception) {
            return "en-US";
        }
    }

    public static void main(String[] args) {
        System.out.println(select("fr-FR,vi-VN;q=0.7"));
        System.out.println(select("ja-JP"));
        System.out.println(select("en;q=1.5"));
    }
}
```

Chạy:

```bash
javac SelectSupportedLocale.java
java SelectSupportedLocale
```

Đầu ra:

```text
fr-FR
en-US
en-US
```

Đây là một chính sách minh họa: dùng lookup và fallback `en-US`. Nó không bảo đảm rằng một range ngắn `vi` sẽ tự được mở rộng thành `vi-VN` theo mọi thuật toán. Nếu sản phẩm muốn hành vi đó, cần thực hiện quy tắc mapping/fallback rõ ràng và kiểm thử.

Quy trình thực tế thường là: nhận `Accept-Language` → `parse` → matching với danh sách supported locale → fallback khi không tìm thấy → tải bản dịch/định dạng bằng locale cuối cùng. `Content-Language` trong HTTP response (nếu được xuất) nên phản ánh **ngôn ngữ thực tế được phục vụ**, không đơn giản sao chép toàn bộ header sở thích đầu vào. Với `ResourceBundle`, tiếp tục kiểm thử cơ chế fallback của tài nguyên vì có thể không tồn tại bundle chính xác.

Không gọi `Locale.setDefault(...)` cho mỗi HTTP request: đây là trạng thái default chia sẻ trong tiến trình và có thể tác động tới request khác. Truyền locale đã chọn tường minh cho các formatter, parser và bộ tải tài nguyên.

## 11. Các lỗi thường gặp

1. **Dùng `Locale.forLanguageTag` để parse cả `Accept-Language`:** phương thức này xử lý một tag, không xử lý danh sách nhiều mục có `q`.
2. **Tin rằng mục đầu của input là ưu tiên cao nhất:** sai khi các `q` không đi theo thứ tự giảm dần; xem danh sách `parse` trả về.
3. **Coi trọng số là xác suất:** `q` không cần có tổng bằng 1.
4. **Lấy lần cuối của range trùng:** Java giữ **lần đầu tiên**, bất kể lần sau có trọng số cao hơn.
5. **Giả định một input tạo đúng một range:** equivalence từ IANA có thể làm số phần tử tăng.
6. **Bỏ qua trường hợp `q=0`:** nó là giá trị hợp lệ, cần được xử lý đúng ở matching.
7. **Coi wildcard là locale:** `*` là biểu thức range, không phải mã dịch.
8. **Giả định filtering và lookup giống nhau:** hai thuật toán có kết quả khác như ví dụ `fr-CA`.
9. **Đoán `parse` xác minh mã IANA:** API chỉ kiểm tra cú pháp; ứng dụng phải kiểm tra danh sách supported.
10. **Bỏ qua ngoại lệ/null:** input lỗi có thể làm gián đoạn request; cần fallback an toàn.
11. **Dùng tên ngôn ngữ hiển thị để matching:** so sánh tags/locale, không so chuỗi `getDisplayName()` đã bản địa hóa.
12. **Sửa default locale toàn cục theo người dùng:** dùng locale cục bộ theo request.

## 12. Câu hỏi tự kiểm tra

- Với `"en;q=0.4,vi;q=0.9,fr;q=0.7"`, kết quả ưu tiên là **vi → fr → en**.
- Với `"en-US;q=0.3,en-US;q=0.8"`, chỉ **en-us với trọng số 0.3** được giữ.
- Với `"iw,en;q=0.5"`, Java có thể thêm range **he** nhờ IANA equivalence.
- Với `q=0`, `parse` vẫn tạo range và giữ trọng số **0.0**.
- `parse` **không bảo đảm** server có bundle cho locale yêu cầu.
- Sau `parse`, dùng **filter** nếu cần các lựa chọn thỏa quy tắc lọc; dùng **lookup** khi cần một ứng viên theo quy tắc lookup, đồng thời xử lý `null` và fallback.

**Tham khảo:** [Java SE 17 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html) · [Java SE 17 — Locale Matching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647).
