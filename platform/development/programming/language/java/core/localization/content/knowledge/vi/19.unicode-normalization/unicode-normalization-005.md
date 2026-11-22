# Ảnh hưởng của chuẩn hóa Unicode đến so sánh, tìm kiếm và khóa dữ liệu trong Java

## 1. Cùng cách hiển thị, khác dữ liệu nhị phân

Trong các ứng dụng đa ngôn ngữ, hai chuỗi có thể **trông giống nhau** nhưng không có cùng dãy ký tự Unicode. Điều đó ảnh hưởng trực tiếp đến:

- So sánh bằng `String.equals()`, `compareTo()`, `equalsIgnoreCase()`.
- Tìm kiếm bằng `contains()`, `indexOf()`, các chỉ mục văn bản hoặc bộ máy search.
- Khóa của `HashMap`, `HashSet`, cache, bảng dữ liệu, chỉ mục UNIQUE, slug và mã định danh.
- Tính nhất quán khi hệ thống nhận input từ bàn phím, trình duyệt, file, API hoặc nhiều hệ điều hành khác nhau.

Ví dụ chữ **é** có thể xuất hiện dưới hai cách biểu diễn:

```text
Dạng dựng sẵn (precomposed):  U+00E9          é
Dạng kết hợp (decomposed):    U+0065 U+0301   e + dấu sắc kết hợp
```

Hai dãy trên là **tương đương chuẩn tắc** (*canonically equivalent*) theo Unicode, nhưng khác số lượng mã ký tự. Trong Java:

```java
String composed = "caf\u00E9";
String decomposed = "cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.length());           // 4
System.out.println(decomposed.length());         // 5
```

`String.equals()` so sánh nội dung ký tự được lưu, không tự chuẩn hóa Unicode. `String.length()` đếm **UTF-16 code units**, không phải số ký tự người dùng nhìn thấy. Vì vậy, chỉ nhìn giao diện hoặc dùng font hiển thị là không đủ để quyết định hai chuỗi có cùng **khóa dữ liệu** hay không.

Mục tiêu của bài là xác định **khi nào cần chuẩn hóa**, sử dụng `java.text.Normalizer` trong Java 17+, lựa chọn quy tắc so sánh/tìm kiếm, và tránh biến chuẩn hóa thành một thao tác gây mất dữ liệu hoặc tạo lỗ hổng trong việc định danh.

## 2. Unicode normalization là gì?

*Unicode normalization* chuyển đổi chuỗi về một trong những dạng được xác định bởi Tiêu chuẩn Unicode để các cách biểu diễn tương đương có thể được xử lý nhất quán. Java cung cấp:

```java
import java.text.Normalizer;

String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);
```

Các dạng chính:

| Dạng | Tên | Ý nghĩa khái quát | Trường hợp thường gặp |
|---|---|---|---|
| `NFD` | Canonical Decomposition | Phân rã ký tự theo tương đương chuẩn tắc | Xử lý dấu kết hợp, phân tích ký tự |
| `NFC` | Canonical Decomposition + Composition | Phân rã chuẩn tắc rồi tái tổ hợp theo quy tắc Unicode | Lưu trữ/so sánh văn bản khi muốn dạng chuẩn tắc ổn định |
| `NFKD` | Compatibility Decomposition | Phân rã cả các ký tự tương thích | Chỉ dùng khi ý nghĩa nghiệp vụ cho phép gộp dạng trình bày |
| `NFKC` | Compatibility Decomposition + Composition | Phân rã tương thích rồi tái tổ hợp | Một số quy trình tìm kiếm hoặc chuẩn hóa định danh được thiết kế rõ ràng |

**Canonical equivalence khác compatibility equivalence.** NFD/NFC dựa trên tương đương chuẩn tắc, còn NFKD/NFKC có thể làm mất sự phân biệt giữa nhiều ký tự được coi là tương thích về dạng trình bày.

Ví dụ NFKC có thể chuyển:

```text
Ký tự gốc:       ﬁ   Ａ   ①
Sau NFKC:        fi  A    1
```

NFKC **không chỉ gộp ký tự có dấu**; nó có thể thay đổi các hình thức chữ cái, chữ số, chỉ số và ligature. Do đó, **không mặc định dùng NFKC để thay thế dữ liệu văn bản người dùng**. Chọn form phải dựa trên hợp đồng định danh hoặc chính sách tìm kiếm.

`Normalizer.isNormalized(text, form)` kiểm tra một chuỗi đã ở dạng cần thiết chưa, hữu ích cho validation, logging có kiểm soát và tối ưu hóa khi cần.

## 3. Một chương trình Java 17+ cho thấy sự khác nhau

Tạo file `UnicodeEqualityDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Map;

public class UnicodeEqualityDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println(
                "rawEquals=" + composed.equals(decomposed));
        System.out.println(
                "lengths=" + composed.length()
                        + "," + decomposed.length());

        String left = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("nfcEquals=" + left.equals(right));
        System.out.println(
                "nfcLengths=" + left.length()
                        + "," + right.length());

        Map<String, String> map = new HashMap<>();
        map.put(composed, "found");

        System.out.println("lookupRaw=" + map.get(decomposed));
        System.out.println("lookupNfc=" + map.get(right));

        String compatibility = "X\uFB01\uFF21\u2460";
        System.out.println(
                "nfkc=" + Normalizer.normalize(
                        compatibility, Normalizer.Form.NFKC));
    }
}
```

Chạy:

```bash
javac UnicodeEqualityDemo.java
java UnicodeEqualityDemo
```

Đầu ra được kiểm chứng bằng JDK:

```text
rawEquals=false
lengths=4,5
nfcEquals=true
nfcLengths=4,4
lookupRaw=null
lookupNfc=found
nfkc=XfiA1
```

Giải thích:

1. `composed` và `decomposed` có cùng cách hiển thị thông dụng nhưng `equals()` trả `false`.
2. Sau khi chuẩn hóa cả hai về `NFC`, chúng có cùng nội dung và `equals()` trả `true`.
3. `HashMap` đã lưu khóa theo dạng dựng sẵn, nên truy vấn bằng dạng phân rã không được khớp. Truy vấn bằng dạng đã chuẩn hóa NFC thì tìm được.
4. `NFKC` chuyển ligature `ﬁ` thành `fi`, chữ Latin full-width `Ａ` thành `A`, số khoanh tròn `①` thành `1`. Điều này có thể hữu ích cho tìm kiếm linh hoạt, nhưng không phù hợp với mọi thao tác bảo toàn nguyên văn.

`HashMap` không có quy tắc Unicode đặc biệt cho khóa chuỗi: nó dựa vào `String.equals()` và `hashCode()`. Hai chuỗi canonical-equivalent chỉ được xem là một khóa khi **ứng dụng chủ động đưa cả hai về cùng dạng**.

## 4. So sánh: equals, compareTo, equalsIgnoreCase và Collator khác nhau

### `String.equals()`: so sánh chính xác nội dung được lưu

`equals()` là phép so sánh phù hợp nếu domain yêu cầu **đúng dãy ký tự**. Nó không tự sửa case, dấu kết hợp hoặc kiểu ký tự tương thích. Kể cả khi nội dung nhìn giống nhau, `equals()` có thể trả `false` do cách biểu diễn Unicode khác nhau.

Sau khi bạn chuẩn hóa **hai bên** về một form được thống nhất, `equals()` có thể dùng để xét bằng nhau trong không gian chuẩn hóa:

```java
static boolean canonicallyEqual(String a, String b) {
    return Normalizer.normalize(
            a, Normalizer.Form.NFC).equals(
            Normalizer.normalize(b, Normalizer.Form.NFC));
}
```

Đây là **mảnh code** để đặt trong class có import `Normalizer`. Với `NFC`, mục đích là so sánh các chuỗi tương đương chuẩn tắc. Nó **không** tự bỏ dấu, bỏ khác biệt chữ hoa/thường hay gộp mọi ký tự nhìn giống nhau.

### `String.compareTo()`: thứ tự UTF-16, không phải sắp xếp theo ngôn ngữ

`String.compareTo()` không tương đương sắp xếp từ điển trong một ngôn ngữ cụ thể. Nó dựa trên thứ tự so sánh của nội dung ký tự Java. Ngay cả sau khi chuẩn hóa NFC, thứ tự này không trở thành thứ tự từ vựng đúng cho tiếng Việt, tiếng Pháp hoặc các ngôn ngữ có dấu.

Dùng `Collator` khi mục tiêu là **sắp xếp hoặc so sánh có cân nhắc ngôn ngữ**.

### `String.equalsIgnoreCase()`: không phải Unicode case folding đầy đủ

`equalsIgnoreCase()` có logic bỏ qua hoa/thường của Java nhưng không thay thế một chính sách canonicalization quốc tế đầy đủ. Ví dụ `Straße` và `STRASSE` có quan hệ case-folding đặc biệt trong một số quy tắc Unicode/ngôn ngữ, nhưng không thể mặc định `equalsIgnoreCase()` hoặc `toLowerCase()` của Java sẽ luôn biến chúng thành một chuỗi giống nhau.

Ngoài ra, so sánh bỏ qua case và chuẩn hóa Unicode là **hai chiều độc lập**: chuỗi có dấu dựng sẵn và dấu kết hợp vẫn cần một chính sách chuẩn hóa nhất quán.

### `Collator`: đối chiếu theo Locale, phục vụ UI và tìm kiếm linh hoạt

`java.text.Collator` cho phép so sánh chuỗi theo quy tắc địa phương. Mức `strength` ảnh hưởng các khác biệt được xét:

- `PRIMARY`: thường bỏ qua những khác biệt thứ cấp như dấu và một số khác biệt hoa/thường, tùy locale và bộ quy tắc.
- `SECONDARY`: thường phân biệt dấu nhưng có thể bỏ qua khác biệt chữ hoa/thường theo locale.
- `TERTIARY`: thường xét thêm khác biệt kiểu chữ hoa/thường và các đặc tính phụ thuộc ngôn ngữ.
- `IDENTICAL`: mức phân biệt rất cao; không đơn giản là `String.equals()`.

Các mô tả trên là **định hướng**, không phải bảng quy tắc áp được y nguyên cho mọi ngôn ngữ. Bản địa hóa có thể thay đổi cách so sánh từng chữ cái.

Ví dụ:

```java
Collator collator = Collator.getInstance(Locale.FRENCH);
collator.setStrength(Collator.PRIMARY);

boolean equivalentForSearch =
        collator.compare("cafe", "caf\u00E9") == 0;
```

Với bộ quy tắc Pháp thông dụng, `equivalentForSearch` là `true` ở mức PRIMARY; đây là **quy tắc đối chiếu được lựa chọn**, không có nghĩa hai chuỗi giống byte hoặc có cùng identity.

**Cảnh báo:** `Collator` mutable và không phải lựa chọn mặc định để làm `equals/hashCode` của khóa `HashMap`. Không được dùng `Collator.compare(a,b)==0` tại một nơi, nhưng lưu/truy xuất khóa bằng `String.equals()` ở nơi khác rồi mong hai cơ chế nhất quán.

## 5. So sánh chuẩn tắc và so sánh theo ngôn ngữ là hai bài toán

Giả sử có ba giá trị:

```text
A: "café"   với U+00E9
B: "café"  với U+0065 + U+0301
C: "cafe"   không có dấu
```

- `A` và `B` **canonical equivalent**. Nếu đưa cả hai về NFC, `equals()` trả true.
- `A` và `C` **không** canonical equivalent. NFC không xóa dấu để tạo ra `cafe`.
- Một chính sách tìm kiếm **không phân biệt dấu** có thể muốn cả `A`, `B` và `C` cùng khớp. Đó là yêu cầu search/collation riêng, không phải định nghĩa của NFC.

Vì vậy, phải tách hai chức năng:

1. **Khóa dữ liệu / identity:** xác định khi nào hai giá trị được xem là *cùng một thực thể*.
2. **Tìm kiếm / matching:** xác định khi nào truy vấn *có liên quan* đến một bản ghi, kể cả khi khác dấu, cách viết hoặc hoa/thường.

Một cơ chế “search-friendly” thường cố ý có nhiều false positives hơn cơ chế khóa duy nhất. Không nên dùng quy tắc search mềm để ghi đè identity hoặc hợp nhất dữ liệu nếu nghiệp vụ không chấp nhận.

## 6. Ảnh hưởng đến HashMap, HashSet và cache

`Map<String, V>` và `Set<String>` chuẩn dùng `equals()/hashCode()` của `String`. Do đó, nếu một bên dùng NFC còn bên kia dùng NFD, có thể xảy ra:

- `map.get(key)` trả `null` dù giao diện hiển thị có vẻ đúng.
- `set.add(...)` chấp nhận hai chuỗi giống nhau bằng mắt thường như **hai phần tử**.
- Cache miss xảy ra liên tục giữa các hệ thống tạo văn bản theo dạng Unicode khác nhau.
- Hai tài khoản có tên hiển thị giống nhau nhưng khóa username khác nhau, nếu hệ thống định nghĩa username bằng raw string.

Một hàm canonicalization đơn giản cho **khóa văn bản được phép dùng NFC**:

```java
static String canonicalKey(String input) {
    Objects.requireNonNull(input, "input");
    return Normalizer.normalize(
            input, Normalizer.Form.NFC);
}
```

Dùng **cùng một hàm** khi insert và lookup:

```java
Map<String, String> accounts = new HashMap<>();

accounts.put(canonicalKey("caf\u00E9"), "account-42");

String account = accounts.get(
        canonicalKey("cafe\u0301"));
```

Hai đoạn này là **mảnh code**, cần import `java.util.Objects`, `java.text.Normalizer`, `java.util.Map` và `java.util.HashMap` cùng phương thức `canonicalKey` trong class.

Điều cần nhớ không phải “NFC làm mọi khóa bằng nhau”, mà là **mọi đường vào cùng một miền khóa phải tuân theo chính sách giống nhau**.

### Không normalize khi đọc mà bỏ qua lúc ghi

Nếu bản ghi cũ lưu raw NFD, trong khi bản ghi mới dùng NFC, việc chuẩn hóa chỉ ở phía request **không sửa được** chỉ mục cũ và có thể tiếp tục gây miss. Cần kế hoạch di chuyển dữ liệu và tái tạo index, cache hoặc khóa phù hợp.

### Khóa là identity khác với nội dung hiển thị

Trong một hệ thống tốt, display name có thể giữ nguyên cách viết người dùng để hiển thị; khóa nội bộ có thể là một ID không đổi. Nếu cần unique username, nên lưu thêm **canonical_username** theo chính sách đã định nghĩa, thay vì thay đổi tự động mọi trường hiển thị.

Không nên sửa key trong một `HashMap` đang dùng theo kiểu “đổi thuộc tính rồi giữ nguyên hash”; `String` immutable, nhưng thay cách tính key ở các tầng mà không reindex/rebuild vẫn làm logic sai.

## 7. Ví dụ Java 17+ hoàn chỉnh: so khớp khóa sau normalize

Lưu thành `CanonicalKeyDemo.java`:

```java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CanonicalKeyDemo {
    private static String key(String raw) {
        return Normalizer.normalize(
                raw, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String a = "caf\u00E9";
        String b = "cafe\u0301";

        Set<String> rawSet = new HashSet<>();
        rawSet.add(a);
        rawSet.add(b);
        System.out.println("rawSetSize=" + rawSet.size());

        Set<String> canonicalSet = new HashSet<>();
        canonicalSet.add(key(a));
        canonicalSet.add(key(b));
        System.out.println(
                "canonicalSetSize=" + canonicalSet.size());

        Map<String, Integer> counts = new HashMap<>();
        counts.put(key(a), 7);
        System.out.println("lookup=" + counts.get(key(b)));

        System.out.println("canonicalEquals=" +
                key(a).equals(key(b)));
    }
}
```

Chạy:

```bash
javac CanonicalKeyDemo.java
java CanonicalKeyDemo
```

Kết quả:

```text
rawSetSize=2
canonicalSetSize=1
lookup=7
canonicalEquals=true
```

Điều này minh họa **hệ quả trực tiếp lên identity của Set/Map**. Khi chính sách username cho phép coi hai dạng Unicode canonically equivalent là một, chuẩn hóa trước khi lưu giúp phát hiện trùng. Nhưng khi nhập danh sách sản phẩm hoặc nội dung văn bản mà **hai cách viết cần giữ riêng**, chuẩn hóa có thể không phải hành vi mong muốn.

**Cẩn thận khi gộp dữ liệu:** nếu hai bản ghi lịch sử vốn phân biệt bằng raw strings nhưng sau NFC lại có cùng khóa, migration cần chính sách xử lý xung đột. Không được âm thầm bỏ một bản ghi hoặc chọn ngẫu nhiên tài khoản “thắng” khi phát hiện collision.

## 8. Tìm kiếm trong chuỗi: contains và indexOf có thể bỏ sót

Các phương thức cơ bản của `String` như `contains()` và `indexOf()` tìm dãy ký tự, không tự tìm theo tương đương Unicode.

Ví dụ:

```java
String text = "cafe\u0301";
String query = "\u00E9";

System.out.println(text.contains(query)); // false
```

Trong văn bản, người dùng nhìn thấy `café` và có thể nghĩ tìm chữ `é` phải khớp. Nhưng đoạn văn bản dùng hai code points `e` + dấu kết hợp, còn query chứa một code point `é` dựng sẵn.

Một cách xử lý **tìm kiếm chính xác nhưng đồng nhất dạng chuẩn tắc**:

```java
String normalizedText = Normalizer.normalize(
        text, Normalizer.Form.NFC);
String normalizedQuery = Normalizer.normalize(
        query, Normalizer.Form.NFC);

boolean found = normalizedText.contains(normalizedQuery);
```

`found` là `true`. Trước khi dùng kỹ thuật này với một kho tài liệu lớn, xem xét:

- Chuẩn hóa cả **tài liệu** và **query**, không chỉ một phía.
- Chọn một form duy nhất; không trộn dữ liệu NFC với NFKC rồi so sánh như một hệ thống nhất quán.
- Nên chuẩn hóa/index dữ liệu tại thời điểm ingestion thay vì lặp lại chi phí với mọi truy vấn, nếu kiến trúc yêu cầu hiệu năng.
- Nếu cần search theo locale với bỏ dấu, bỏ hoa/thường hoặc biến thể từ ngữ, `String.contains()` sau NFC **chưa đủ**; nên dùng engine có analyzer/collation phù hợp.

### Vị trí tìm thấy trên chuỗi normalized không phải vị trí của chuỗi raw

Một cạm bẫy quan trọng cho chức năng bôi sáng kết quả tìm kiếm:

```text
raw:        "cafe" + combining acute
NFC:        "café"
raw length: 5
NFC length: 4
```

Một `indexOf()` trên chuỗi normalized trả offset theo **UTF-16 của chuỗi normalized**. Nó không tự ánh xạ sang offset trong chuỗi gốc để đặt highlight. NFD/NFC/NFKC có thể thay đổi độ dài, thứ tự hoặc dãy mã Unicode.

Nếu UI muốn tô đúng vị trí trong raw text, phải **giữ bản đồ offset** trong pipeline tokenizer/search, hoặc render từ cùng bản normalized đã tạo index, với một quy tắc bảo toàn selection rõ ràng. Không dùng chỉ số từ search index rồi cắt trực tiếp raw string khi không chắc hệ offset khớp nhau.

## 9. Collator và ví dụ Java 17+ về tìm kiếm linh hoạt

Một bài toán khác là người dùng gõ `cafe` nhưng muốn tìm `café`. NFC không xóa dấu. `Collator` với `Locale.FRENCH` và mức `PRIMARY` có thể xem các dạng này tương đương trong so sánh ngôn ngữ.

Tạo `LocaleComparisonDemo.java`:

```java
import java.text.Collator;
import java.text.Normalizer;
import java.util.Locale;

public class LocaleComparisonDemo {
    public static void main(String[] args) {
        String plain = "cafe";
        String accented = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("rawContains=" +
                decomposed.contains("\u00E9"));

        String nfcText = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("nfcContains=" +
                nfcText.contains("\u00E9"));

        Collator collator =
                Collator.getInstance(Locale.FRENCH);

        collator.setStrength(Collator.PRIMARY);
        System.out.println("primaryEquals=" +
                (collator.compare(plain, accented) == 0));

        collator.setStrength(Collator.TERTIARY);
        System.out.println("tertiaryEquals=" +
                (collator.compare(plain, accented) == 0));
    }
}
```

Biên dịch/chạy:

```bash
javac LocaleComparisonDemo.java
java LocaleComparisonDemo
```

Kết quả đã kiểm chứng trong môi trường JDK với dữ liệu locale tương ứng:

```text
rawContains=false
nfcContains=true
primaryEquals=true
tertiaryEquals=false
```

Diễn giải:

- `rawContains` là false vì hai cách mã hóa chữ có dấu không trùng dãy ký tự.
- `nfcContains` là true vì đã chuẩn hóa về cùng dạng.
- Ở `PRIMARY`, collator Pháp trong ví dụ bỏ qua khác biệt dấu này.
- Ở `TERTIARY`, sự khác biệt giữa `cafe` và `café` lại được xét.

Lưu ý rằng `Collator.compare(a,b)==0` là **tương đương theo cấu hình collation**, không phải khẳng định hai chuỗi có cùng Unicode code points hoặc cùng tên người/cùng tài khoản.

`Collator` có thể cấu hình decomposition và strength; hành vi chi tiết phụ thuộc locale/provider và các phiên bản dữ liệu collation. Nếu cần chỉ mục tìm kiếm lớn, dùng engine có analyzer tương ứng và test bằng dữ liệu thực; `Collator` là công cụ so sánh/sắp xếp, không phải một hệ thống full-text search với stemming, tokenization và ranking.

## 10. Chuẩn hóa Unicode không đồng nghĩa chuyển chữ thường

Nhiều hệ thống muốn có tên đăng nhập không phân biệt case. Khi đó NFC **chưa đủ**:

```text
"User" và "user" đều đã NFC, nhưng không bằng nhau bằng String.equals().
```

Một pipeline minh họa cho **khóa case-insensitive đơn giản**:

```java
static String simpleCanonicalUsername(String raw) {
    String lowered = raw.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(
            lowered, Normalizer.Form.NFC);
}
```

Đây chỉ là **chính sách ví dụ**, không phải Unicode case folding đầy đủ và không phù hợp tự động cho mọi ngôn ngữ. Chọn `Locale.ROOT` giúp tránh hành vi phụ thuộc locale mặc định của máy khi xử lý định danh “ngôn ngữ-trung lập”.

### Vì sao phải nói rõ đây không phải full case folding?

Java `String.toLowerCase(Locale.ROOT)` có thể ánh xạ một ký tự thành **nhiều code points**. Ví dụ chữ hoa `İ` (Latin Capital Letter I with Dot Above, U+0130) khi đổi về chữ thường theo `Locale.ROOT` có thể tạo dãy `i` + dấu chấm kết hợp, chứ không chỉ một ký tự ASCII `i`.

Ngược lại, `Straße` và `STRASSE` không trở thành cùng chuỗi chỉ nhờ phép lowercase đơn giản của Java. Các quy tắc chữ hoa/thường có thể phụ thuộc ngôn ngữ, cách case folding và chuẩn Unicode được dùng.

Nếu sản phẩm cần **Unicode caseless matching chính xác theo một chuẩn cụ thể**, cần có chính sách Unicode case folding phù hợp, có thể dùng thư viện chuyên dụng hỗ trợ full case folding và version dữ liệu Unicode đã được quy định. Không được thay đổi thuật toán canonical username sau khi có tài khoản mà không lên kế hoạch migration và xử lý va chạm.

### Thứ tự các phép biến đổi có thể quan trọng

Case mapping đôi khi tạo ra ký tự kết hợp mới. Do đó, nếu pipeline gồm lowercase và normalization, hãy xác định **thứ tự chính thức** và giữ nó nhất quán. Ví dụ `lowercase → NFC` khác về mặt chính sách so với chỉ `NFC` hoặc chỉ lowercase. Một số hệ thống định danh dùng tiêu chuẩn riêng (như IDNA cho domain) và không thể thay bằng hai lời gọi trên.

## 11. NFC và NFKC: thế nào là đúng cho khóa dữ liệu?

Hai chính sách thường bị nhầm:

**Chính sách A: canonical equivalence.** Nếu hệ thống muốn xem `café` dựng sẵn và `cafe + combining acute` là cùng chuỗi, dùng NFC có thể hợp lý. Nó không đồng nhất `cafe` với `café`, và không cố đồng nhất mọi glyph trông giống nhau.

**Chính sách B: compatibility equivalence.** Nếu hệ thống muốn các ký tự full-width, ligature hoặc số dạng trình bày được gộp với dạng thông dụng, NFKC có thể là một bước trong pipeline **đã được thiết kế và công bố**.

| Chuỗi | NFC | NFKC | Rủi ro nếu dùng cho identity |
|---|---|---|---|
| `caf\u00E9` dạng dựng sẵn | `café` | `café` | Thường là canonical equivalence dự kiến |
| `cafe\u0301` dạng phân rã | `café` | `café` | Gộp hai cách biểu diễn chuẩn tắc |
| `ﬁ` | Giữ `ﬁ` | `fi` | Gộp ligature với hai chữ cái |
| `Ａ` (full-width A) | Giữ `Ａ` | `A` | Gộp kiểu ký tự full-width |
| `①` | Giữ `①` | `1` | Gộp chữ số khoanh tròn với chữ số thông thường |

NFKC có thể phá hủy một phân biệt có ý nghĩa trong tài liệu, thiết kế hoặc nội dung người dùng. Chỉ dùng khi **miền ứng dụng** xác nhận các khác biệt đó không ảnh hưởng identity.

Đừng xem Unicode normalization như công cụ loại bỏ toàn bộ ký tự nguy hiểm, xử lý homograph hay xóa mọi khác biệt hình ảnh. Có những ký tự **confusable** nhìn giống nhau nhưng không được Unicode normalization gộp lại. Ngược lại, NFKC có thể gộp những cặp mà ứng dụng muốn giữ riêng.

## 12. Tìm kiếm bỏ dấu: cần chính sách riêng

Một vài ứng dụng muốn `“hoa”` khớp `“hòa”` hay `“hoà”`. Có thể xây dựng *search key* bằng cách:

1. Chuẩn hóa NFD để phơi bày nhiều dấu kết hợp.
2. Xóa nhóm combining marks theo quy tắc tìm kiếm.
3. Chuẩn hóa về form đầu ra đã chọn.
4. Có thể thực hiện thêm case folding hoặc các thay thế có chủ đích.

Một ý tưởng mã minh họa:

```java
String stripped = Normalizer.normalize(
        input, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
```

**Cảnh báo bắt buộc:** đây chỉ là thao tác xóa combining marks, **không phải thuật toán tìm kiếm bỏ dấu đầy đủ cho mọi ngôn ngữ**. Nó có thể làm mất khác biệt ngữ nghĩa, không chuyển tất cả ký tự có gạch/nét đặc biệt (ví dụ `đ`) thành ký tự ASCII, và có thể phá văn bản của các ngôn ngữ mà dấu kết hợp là thành phần thiết yếu.

Với tiếng Việt, việc loại bỏ dấu phục vụ search cần xem xét cách xử lý `đ/Đ`, sắc/huyền/hỏi/ngã/nặng, các dấu tạo nguyên âm và chính sách phân biệt âm. Hệ thống phải quyết định có muốn `đ` và `d` khớp nhau không; không được ngầm coi đó là hệ quả chuẩn tắc của NFC/NFD.

Trong các hệ search, nên lưu **văn bản gốc** để hiển thị và lập **search index** riêng theo analyzer có kiểm soát. Search index được phép “mềm” hơn identity, nhưng không được dùng làm khóa duy nhất của tài khoản hoặc chứng minh hai thực thể là một.

## 13. Dữ liệu lưu trữ và UNIQUE: xử lý ngay ở biên ghi

Khi lưu chuỗi từ nhiều nguồn, có thể xảy ra:

- Client A gửi `café` dạng dựng sẵn.
- Client B gửi chuỗi tương đương dạng phân rã.
- Database với collation/index thô coi chúng khác nhau.
- Tầng Java normalize trong query nhưng bảng cũ chưa normalize, khiến đọc dữ liệu bị thiếu.

Một kiến trúc thường dùng:

```text
raw input
    |
    v
validate policy (allowed characters / length / domain rules)
    |
    v
canonicalize using chosen normalization + case policy
    |
    +--> raw/display value (preserve if required)
    |
    v
canonical key -> unique constraint / index / cache key
```

Nếu lưu cả `display_name` và `canonical_username`:

- `display_name` là nội dung hiển thị theo ý định người dùng, có thể giữ nguyên raw hoặc định dạng được phép.
- `canonical_username` phải được tạo theo **một hàm duy nhất**, có version/chính sách rõ ràng nếu lâu dài.
- Cột canonical cần có uniqueness ở **tầng lưu trữ** phù hợp, không chỉ kiểm tra trước bằng Java: hai request song song vẫn có thể tạo race nếu không có constraint hoặc cơ chế giao dịch tương đương.

Không giả định mọi DB có cùng **collation**. Một số hệ thống database có thể so sánh bỏ case/bỏ dấu hay canonical equivalent khác nhau, và các quy tắc này phụ thuộc sản phẩm, version và cấu hình cột/index. Cần kiểm thử trực tiếp **hợp đồng uniqueness thực tế** thay vì kết luận rằng DB tự hoạt động giống `Normalizer.normalize(..., NFC)`.

### Khi đổi chính sách canonicalization phải migration

Thay `NFC` bằng `NFKC` hoặc bổ sung case folding sau khi đã có dữ liệu có thể khiến hai tên trước đây khác nhau trở thành **cùng canonical key**.

Quy trình nên gồm:

1. Kiểm kê toàn bộ raw values và tính canonical key theo chính sách mới.
2. Phát hiện collision và giải quyết theo quy tắc kinh doanh **trước** khi áp UNIQUE.
3. Xây dựng lại các index/cache và kiểm thử đọc/ghi ở cả API cũ/mới.
4. Chuyển đổi trong transaction/chiến lược triển khai có kiểm soát; tránh hai version ứng dụng cùng lúc dùng hai chính sách nhận dạng khác nhau.
5. Giữ mapping/alias có chủ đích nếu cần tương thích dữ liệu cũ.

Không hợp nhất hai tài khoản người dùng chỉ vì tên hiển thị hoặc search-key tương đương; identity cần dựa vào ID và quy tắc xác minh rõ ràng.

## 14. Bảo mật: chuẩn hóa không giải quyết toàn bộ spoofing

Chuẩn hóa Unicode có thể là một lớp của chiến lược an toàn, nhưng **không đủ** để chống giả mạo định danh:

- Ký tự Latin `a` và Cyrillic `а` có thể trông rất giống nhau; chúng không nhất thiết được NFC/NFKC biến thành cùng code point.
- Ký tự zero-width hoặc điều khiển hướng văn bản có thể ảnh hưởng cách hiển thị mà không tạo ra chuỗi giống theo `equals()`.
- Các ký tự compatibility có thể đổi thành dạng khác dưới NFKC, tạo collision không mong đợi.
- Input có dấu kết hợp bất thường hoặc đoạn Unicode dài có thể gây khó khăn về UI, giới hạn chiều dài và hiệu năng nếu không kiểm tra.
- Quy tắc case/collation không đồng nhất giữa phía client, server và database có thể làm sai kiểm soát truy cập nếu dùng chuỗi làm identity.

Nên xác định rõ **bộ ký tự được phép**, chiều dài theo đơn vị đo thích hợp, quy tắc normalization, xử lý script mixing/confusables theo nhu cầu và kiểu ID dùng trong authorization. Không được coi NFKC là một bộ lọc an ninh hay tự ý xóa mọi ký tự khác thường.

### Mật khẩu và chữ ký số

Đối với **mật khẩu**, không được âm thầm đổi normalization khi chưa có chính sách xác thực rõ ràng. Đổi input trước khi băm có thể khiến mật khẩu khác nhau thành cùng kết quả hoặc làm người dùng không đăng nhập được khi hệ thống được nâng cấp.

Đối với **chữ ký số, HMAC, hash của nội dung hoặc canonical request**, thay đổi một code point hoặc thứ tự combining marks sẽ thay **byte sequence** được ký/băm. Chỉ normalize nếu **giao thức chính thức** quy định và hai phía áp dụng chính xác cùng quy tắc. Không dùng `Normalizer` để “sửa dữ liệu” sau khi đã ký rồi mong chữ ký tiếp tục hợp lệ.

Phân biệt “so sánh văn bản cho người dùng” với “so sánh bytes giao thức/secret”. Đây là hai miền có yêu cầu khác nhau.

## 15. Unicode version và đồng bộ giữa các hệ thống

Unicode có các phiên bản và thư viện/driver/search engine có thể dùng các phiên bản dữ liệu normalization, case folding hoặc collation khác nhau.

Với các ký tự đã được xác định từ lâu, các dạng normalization thường có đặc tính ổn định cao, nhưng **không nên tự mặc định mọi engine sẽ có cùng cách so sánh, search ranking, case folding hoặc sorting**. Collation và case folding là những lĩnh vực đặc biệt cần kiểm thử theo version.

Một hợp đồng dữ liệu dùng lâu dài nên ghi rõ:

- Form normalization (`NFC` hay `NFKC`, hoặc không normalize).
- Có lowercase/case folding không, theo locale hay không.
- Có xóa dấu hoặc ký tự kết hợp không (thường chỉ dành cho search).
- Có trim whitespace không, có cho phép ký tự điều khiển và format characters không.
- Canonical key lưu ở đâu và constraint nào thực thi uniqueness.
- Version chính sách/schema và chiến lược migration nếu thay đổi.
- Các test vectors Unicode với trường hợp canonical equivalent, compatibility equivalent, case mapping đặc biệt và confusables.

Nếu client và server cùng chuẩn hóa, hãy **kiểm tra canonicalization ở biên tin cậy phía server**; không dựa duy nhất vào JavaScript client hoặc UI đã tự chuẩn hóa.

## 16. Checklist kiểm thử

| Nhóm kiểm thử | Input gợi ý | Kỳ vọng của chính sách NFC |
|---|---|---|
| Canonical equivalence | `caf\u00E9` và `cafe\u0301` | Cùng canonical key |
| Compatibility ligature | `ﬁ` và `fi` | NFC không mặc định gộp |
| Full-width | `Ａ` và `A` | NFC không mặc định gộp |
| Hoa/thường | `User` và `user` | NFC không tự gộp |
| Không dấu/có dấu | `cafe` và `café` | NFC không gộp |
| Ký tự confusable | Latin `a` và Cyrillic `а` | NFC không phải bộ phát hiện giả mạo |
| Tìm kiếm | Query `é` trong raw `e + combining acute` | Search raw có thể miss; normalized tìm được |
| Cache | Insert NFC, lookup NFD | Canonicalize cả hai trước lookup |
| Unique | Hai raw strings khác nhưng NFC giống nhau | Phát hiện collision ở canonical key |
| Unicode offset | Raw `cafe + combining acute` so với NFC `café` | Length/index có thể khác |
| Case đặc biệt | `İ`, `Straße` | Không giả định lowercase là full case folding |
| Password/dữ liệu ký | Dãy Unicode khác nhưng hiển thị giống | Không normalize ngoài hợp đồng |

Ngoài unit test đơn lẻ, nên kiểm thử **end-to-end** qua HTTP, database, cache và search index để phát hiện tầng nào đang thực hiện chuẩn hóa hoặc đối chiếu khác với hệ thống còn lại.

## 17. Lỗi phổ biến cần tránh

1. **Cho rằng giống nhau trên màn hình thì `String.equals()` phải true.** Unicode cho phép nhiều dãy ký tự canonical-equivalent.
2. **Chỉ normalize một bên.** Insert và lookup phải thống nhất form.
3. **Dùng NFKC mặc định cho tất cả văn bản.** Compatibility normalization có thể gộp những ký tự cần giữ phân biệt.
4. **Nhầm normalize với lowercase hoặc bỏ dấu.** Đây là các thao tác và chính sách khác nhau.
5. **Dùng `equalsIgnoreCase()` như full Unicode case folding.** Không bảo đảm mọi quy tắc case đặc biệt.
6. **Dùng Collator PRIMARY làm bằng chứng hai tài khoản là một.** Nó là tương đương tìm kiếm/sắp xếp theo locale, không phải identity.
7. **Dùng `String.contains()` trên raw Unicode và mong match canonical equivalents.** Chuẩn hóa cả text/query hoặc dùng search engine phù hợp.
8. **Lấy index từ chuỗi normalized để cắt raw string.** Offset có thể lệch do thay đổi UTF-16 length.
9. **Dựa vào DB collation mặc định mà không kiểm thử.** Unique/sort/search khác nhau theo DB/version/config.
10. **Thay đổi canonicalization sau triển khai mà không migration.** Có thể gây collisions, cache misses và mất liên kết dữ liệu.
11. **Đặt secret/password/hash input qua normalization vô điều kiện.** Có thể phá giao thức hoặc thay ý nghĩa xác thực.
12. **Tin rằng NFC/NFKC tự chống homograph.** Confusable characters là vấn đề bổ sung, không được giải quyết toàn bộ bởi normalization.
13. **Chỉ xử lý ở client.** Server cần áp dụng chính sách canonicalization ở biên tin cậy.
14. **Dùng search key bỏ dấu làm unique key.** Quy tắc tìm kiếm linh hoạt thường quá rộng để làm định danh.
15. **Coi `length()` là số ký tự nhìn thấy.** `String.length()` đếm UTF-16 code units; normalization có thể làm length thay đổi.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `"caf\u00E9".equals("cafe\u0301")` có thể false?  
**Đáp án:** Hai chuỗi dùng dãy Unicode khác nhau: ký tự dựng sẵn so với base letter + combining mark. `String.equals()` không tự normalize.

**Câu 2.** Chuẩn hóa cả hai về NFC rồi so sánh có giải quyết được trường hợp đó không?  
**Đáp án:** Có, vì hai dạng tương đương chuẩn tắc sẽ về cùng biểu diễn NFC trong ví dụ.

**Câu 3.** NFC có biến `cafe` thành `café` không?  
**Đáp án:** Không. Chúng không tương đương chuẩn tắc.

**Câu 4.** `NFKC` có thể đổi `ﬁ` thành `fi` không?  
**Đáp án:** Có. Đây là compatibility mapping; phải cân nhắc tác động lên identity.

**Câu 5.** Nếu `HashMap` lưu khóa NFC và client gửi NFD thì nên làm gì?  
**Đáp án:** Chuẩn hóa mọi khóa khi ghi và tra cứu theo cùng chính sách; dữ liệu lịch sử cần migration nếu chưa tuân theo.

**Câu 6.** `Collator` ở mức PRIMARY có phù hợp làm UNIQUE username cho mọi sản phẩm không?  
**Đáp án:** Không mặc định. Nó có thể gộp khác biệt dấu/chữ tùy locale; identity cần quy tắc riêng và sự nhất quán ở database.

**Câu 7.** Kết quả `indexOf()` sau normalize có thể dùng trực tiếp lên raw text không?  
**Đáp án:** Không bảo đảm. Normalization có thể thay đổi số UTF-16 code units; cần mapping hoặc render cùng văn bản chuẩn hóa.

**Câu 8.** NFC hoặc NFKC có loại bỏ hết ký tự giả mạo nhìn giống nhau không?  
**Đáp án:** Không. Phát hiện confusable, kiểm soát script, security identifiers và chính sách Unicode cần thiết kế riêng.

## 19. Ghi nhớ

**Unicode normalization là một phần của hợp đồng dữ liệu, không phải bộ lọc “làm sạch” chung cho mọi trường.** Khi dùng để so sánh, tìm kiếm và tạo khóa:

- Chọn `NFC` cho tương đương chuẩn tắc nếu domain muốn hai cách mã hóa cùng một chữ được xem là giống nhau.
- Chỉ chọn `NFKC` khi các khác biệt tương thích được phép mất đi.
- Tách **canonical identity key** khỏi **display value** và **search key**.
- Normalize nhất quán ở mọi đường ghi/đọc; xử lý collision và UNIQUE ở tầng lưu trữ.
- Không nhầm normalizer với case folding, collation, xử lý dấu hay phòng chống Unicode spoofing.

**Tài liệu chính thức:** [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) · [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) · [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) · [Unicode Standard Annex #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/).
