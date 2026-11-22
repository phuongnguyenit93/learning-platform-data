# `Collator.getInstance` theo `Locale`: so sánh và sắp xếp chuỗi đúng ngôn ngữ trong Java

## 1. Vì sao thứ tự chữ cái không giống nhau ở mọi ngôn ngữ?

Khi hiển thị danh sách tên người, tên địa điểm, danh mục sản phẩm hoặc thuật ngữ cho người dùng quốc tế, cách sắp xếp theo mã Unicode thường **không tương đương cách sắp xếp mà người bản ngữ mong đợi**.

Ví dụ, ở tiếng Thụy Điển, các chữ `å`, `ä`, `ö` có vị trí riêng ở cuối bảng chữ cái, sau `z`; trong cách so sánh tiếng Đức thông dụng, `ä` thường được xếp gần `a`, trước `z`. Cùng hai chuỗi `"ä"` và `"z"`, kết quả có thể khác tùy ngôn ngữ:

```text
Locale Thụy Điển (sv-SE):  z < ä
Locale Đức       (de-DE): ä < z
```

Do đó, không thể lấy `String.compareTo()` hoặc `Collections.sort(list)` với thứ tự Unicode mặc định làm định nghĩa duy nhất cho **sắp xếp ngôn ngữ tự nhiên**.

Java cung cấp `java.text.Collator`: một bộ so sánh (*collation*) có khả năng áp dụng quy tắc theo `Locale`. Cách tạo thường gặp:

```java
Collator collator =
        Collator.getInstance(Locale.forLanguageTag("vi-VN"));
```

Sau đó:

```java
int result = collator.compare("a", "ă");
```

Dấu của `result` cho biết thứ tự theo **quy tắc collation của formatter đó**. Giá trị chính xác phụ thuộc locale, mức phân biệt, cách xử lý dấu và dữ liệu locale runtime.

**Chủ đề cốt lõi:** `Collator.getInstance(locale)` lấy bộ so sánh **dành cho locale yêu cầu**. Nó không dịch văn bản, không chuẩn hóa toàn bộ dữ liệu, không bảo đảm thứ tự giống nhau ở mọi JDK và không mặc nhiên biến phép so sánh thành kiểm tra bằng nhau về mặt định danh.

## 2. `Collator` là gì và khác `String.compareTo()` ra sao?

| Đặc điểm | `String.compareTo(...)` | `Collator.compare(...)` |
| --- | --- | --- |
| Cơ sở so sánh | Thứ tự đơn vị mã UTF-16, theo quy tắc `String` | Quy tắc collation của `Locale` và cấu hình `Collator` |
| Phụ thuộc `Locale` | Không | Có |
| Dấu và chữ hoa/thường | Khác mã có thể khác thứ tự, không xét ngữ nghĩa ngôn ngữ | Có thể điều chỉnh mức phân biệt |
| Sắp xếp tên, từ trong giao diện | Không luôn phù hợp | Thường phù hợp hơn nếu chọn đúng locale |
| Thứ tự ổn định qua dữ liệu locale mới | Theo quy tắc `String`, độc lập dữ liệu CLDR | Có thể thay đổi theo JDK, nhà cung cấp dữ liệu, quy tắc collation |
| Dùng làm định danh/chữ ký/hash? | Vẫn cần hợp đồng riêng | **Không** nên dùng thay byte equality hoặc định danh bảo mật |

`Collator` là lớp trừu tượng trong package `java.text`, triển khai giao diện `Comparator<Object>` và `Cloneable`. Các triển khai cụ thể, như `RuleBasedCollator`, thực hiện chính sách so sánh. Phần lớn mã ứng dụng chỉ cần dùng factory `getInstance`, không cần tự định nghĩa toàn bộ quy tắc.

`compare(a,b)` trả một `int`:

- Giá trị **âm**: `a` đứng trước `b`.
- **0**: `a` và `b` được xem là **tương đương theo cấu hình collation hiện tại**.
- Giá trị **dương**: `a` đứng sau `b`.

**Không so sánh đúng `-1` hoặc `1`**: hợp đồng `Comparator` chỉ yêu cầu dấu âm/0/dương. Dùng `Integer.signum(result)` nếu muốn hiển thị dấu chuẩn hóa trong ví dụ.

`compare(a,b)==0` **không đồng nghĩa** `a.equals(b)`. Chẳng hạn khi cấu hình bỏ qua dấu, `"resume"` và `"résumé"` có thể bằng nhau về collation nhưng vẫn là hai chuỗi Java khác nhau.

## 3. Factory `getInstance` và cách chọn `Locale`

Có hai overload chính:

```java
Collator.getInstance()
Collator.getInstance(Locale desiredLocale)
```

- `getInstance()` lấy bộ so sánh theo **default locale của JVM**.
- `getInstance(locale)` yêu cầu bộ so sánh theo locale tường minh, ví dụ `Locale.US`, `Locale.GERMANY`, `Locale.forLanguageTag("sv-SE")`, `Locale.forLanguageTag("vi-VN")`.

Trong ứng dụng đa người dùng, nên truyền **locale của thao tác sắp xếp** thay vì ngầm định default locale server:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);
```

Đây là đoạn mã minh họa, cần import `java.util.Locale` và `java.text.Collator`.

**Cách xác định locale:** nếu sắp xếp danh sách cho người dùng theo giao diện tiếng Việt, có thể dùng `vi-VN`. Nhưng dữ liệu có thể gồm nhiều ngôn ngữ, hoặc sản phẩm có yêu cầu collation độc lập locale giao diện (ví dụ danh mục tra cứu toàn cầu). Khi đó phải **quy định rõ locale sắp xếp của danh sách**, không suy từ địa chỉ IP, timezone hay ngôn ngữ server.

### Locale có được hỗ trợ không?

`Collator.getAvailableLocales()` trả danh sách các locale được runtime và các provider collation đang cài đặt công bố hỗ trợ. Nhưng:

- Danh sách có thể khác giữa runtime/vendor và provider.
- `getInstance(locale)` có thể sử dụng dữ liệu fallback phù hợp nếu không tìm được chính xác biến thể yêu cầu, chứ không phải bộ quy tắc độc nhất được bảo đảm cho mọi language tag.
- Đừng coi việc tạo được `Locale.forLanguageTag("xx-YY")` là chứng cứ Java có đầy đủ dữ liệu collation riêng cho locale đó.
- Một số Unicode locale extensions (ví dụ collation identifier) có thể được provider nhận biết; **không** nên giả định mọi JDK/provider hiểu và áp dụng mọi extension. Hãy kiểm thử locale tag thực sự được hỗ trợ.

`Locale.getDefault()` là trạng thái môi trường có thể bị thay đổi và làm kết quả sắp xếp thiếu ổn định. Đối với dữ liệu giao thức/API cần một thứ tự cố định, đừng đổi theo `Locale.getDefault()` một cách ngầm định.

## 4. Ví dụ chạy được: cùng chữ, thứ tự Thụy Điển khác Đức

Tạo **`CollatorLocaleDemo.java`**:

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class CollatorLocaleDemo {
    private static void show(Locale locale, List<String> source) {
        Collator collator = Collator.getInstance(locale);
        List<String> sorted = new ArrayList<>(source);

        sorted.sort((a, b) -> collator.compare(a, b));

        System.out.println(locale.toLanguageTag() + ": " + sorted);
        System.out.println("compare(ä,z)=" +
                Integer.signum(collator.compare("ä", "z")));
    }

    public static void main(String[] args) {
        List<String> words = List.of("z", "ä", "a", "ö");

        show(Locale.forLanguageTag("sv-SE"), words);
        show(Locale.GERMANY, words);
    }
}
```

Biên dịch/chạy bằng JDK 17+ với tệp mã nguồn UTF-8:

```bash
javac -encoding UTF-8 CollatorLocaleDemo.java
java -cp . CollatorLocaleDemo
```

**Đầu ra tham khảo** với bộ dữ liệu collation hiện đại thường gặp của JDK:

```text
sv-SE: [a, z, ä, ö]
compare(ä,z)=1
de-DE: [a, ä, ö, z]
compare(ä,z)=-1
```

**Vì sao khác nhau?** `Collator.getInstance` chọn quy tắc ngôn ngữ. Với `sv-SE`, `ä` đứng **sau** `z`; với `de-DE`, nó được đặt **trước** `z`. Mặc dù hai lần chạy dùng cùng bốn chuỗi nguồn, trình tự sau khi sort khác nhau.

Đây là ví dụ về **quy tắc collation theo ngôn ngữ**, không phải một hợp đồng về thứ tự chính xác cho mọi locale/JDK. Dữ liệu collation thường dựa vào hệ quy tắc ngôn ngữ và có thể thay đổi giữa các phiên bản runtime. Khi định nghĩa thứ tự lưu trữ hoặc phân trang bền vững, cần cố định hoặc quản lý version của quy tắc so sánh.

### Tránh làm mất thứ tự dữ liệu gốc

Ví dụ sao chép `source` sang `new ArrayList<>(source)` trước khi sắp xếp, vì `List.of(...)` là danh sách bất biến. Nếu gọi `sort` trực tiếp trên danh sách không hỗ trợ sửa đổi, thao tác sẽ không phù hợp. Ngoài ra, việc tạo bản sao giúp hiển thị hai locale mà không ảnh hưởng danh sách nguồn.

## 5. `Collator.setStrength`: “so sánh bằng nhau” phụ thuộc cấp độ

Bên cạnh locale, `Collator` còn có thuộc tính **strength**: mức độ khác biệt được coi là có ý nghĩa.

| Mức | Ý tưởng tổng quát | Ví dụ điển hình |
| --- | --- | --- |
| `PRIMARY` | Chỉ phân biệt những khác biệt chính ở cấp chữ cơ sở | Có thể coi `e` và `é`, `a` và `A` tương đương trong một số locale |
| `SECONDARY` | Bổ sung những khác biệt thứ cấp, thường gồm dấu | Có thể phân biệt `e` và `é`, chưa phân biệt chữ hoa/thường |
| `TERTIARY` | Bổ sung khác biệt cấp ba, thường gồm chữ hoa/thường | Có thể phân biệt `a` với `A` |
| `IDENTICAL` | Kiểm tra thêm những khác biệt nhỏ nhất của chuỗi khi các cấp trước bằng nhau | Có thể phân biệt biểu diễn Unicode trong một số chế độ decomposition |

**Lưu ý:** việc gán một tính năng ngôn ngữ vào primary/secondary/tertiary **phụ thuộc locale và provider**. Bảng trên là cách hiểu chung, **không** có nghĩa mọi dấu hoặc mọi cặp chữ cái ở tất cả ngôn ngữ được xếp cùng cấp. Ví dụ một chữ có dấu trong tiếng Việt có thể thuộc một lớp khác tùy quy tắc collation.

Cấu hình:

```java
Collator c = Collator.getInstance(Locale.US);
c.setStrength(Collator.PRIMARY);
```

Thao tác `setStrength` thay trạng thái của **instance hiện có**. Vì vậy **`Collator` không immutable**, khác với `DateTimeFormatter`.

### Chương trình kiểm chứng từng strength

Tạo **`CollatorStrengthDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    private static void show(String name, int level) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(level);

        System.out.println(name
                + ": e_vs_é="
                + Integer.signum(collator.compare("e", "é"))
                + ", a_vs_A="
                + Integer.signum(collator.compare("a", "A")));
    }

    public static void main(String[] args) {
        show("PRIMARY", Collator.PRIMARY);
        show("SECONDARY", Collator.SECONDARY);
        show("TERTIARY", Collator.TERTIARY);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java -cp . CollatorStrengthDemo
```

Kết quả tham khảo theo bộ dữ liệu US thông dụng:

```text
PRIMARY: e_vs_é=0, a_vs_A=0
SECONDARY: e_vs_é=-1, a_vs_A=0
TERTIARY: e_vs_é=-1, a_vs_A=-1
```

Ở `PRIMARY`, ví dụ coi hai chuỗi khác dấu hoặc khác chữ hoa/thường là tương đương. Khi tăng strength, những khác biệt đó bắt đầu có ý nghĩa. Không dùng `PRIMARY` cho kiểm tra trùng **tài khoản định danh** nếu nghiệp vụ yêu cầu phân biệt các chuỗi này.

`Collator.getInstance(locale)` có thể tạo formatter với cấu hình mặc định do runtime quyết định. Để kết quả ứng dụng chủ động, **đặt strength tường minh** khi nghiệp vụ yêu cầu; đừng giả định mặc định luôn phù hợp với chức năng tìm kiếm, sắp xếp, lọc hoặc kiểm tra trùng.

## 6. `setDecomposition`: chuẩn hóa canonical và so sánh

Unicode cho phép một số ký tự có nhiều cách biểu diễn canonical-equivalent. Ví dụ:

```text
"é"       = U+00E9
"é"  = U+0065 U+0301
```

`Collator` có thuộc tính **decomposition**, điều khiển việc xử lý các chuỗi đã tổ hợp/phân rã trong quá trình collation:

- `Collator.NO_DECOMPOSITION`: không yêu cầu phân rã canonical trong quá trình so sánh.
- `Collator.CANONICAL_DECOMPOSITION`: xử lý phân rã canonical khi so sánh.
- `Collator.FULL_DECOMPOSITION`: xử lý thêm các dạng compatibility decomposition, có thể ảnh hưởng cách so khớp.

Thay đổi bằng `setDecomposition(...)`. Giá trị này độc lập về mặt API với `setStrength(...)`, nhưng hai cấu hình phối hợp quyết định kết quả `compare`.

**Phân biệt `Collator` với `Normalizer`:**

```java
Collator collator = Collator.getInstance(Locale.US);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

`Collator` so sánh **hai chuỗi** bằng quy tắc ngôn ngữ; nó không trả chuỗi đã chuẩn hóa để lưu. `Normalizer.normalize(text, Normalizer.Form.NFC)` tạo một **chuỗi mới** ở normal form đã chọn; nó không thay thế collation theo locale.

Một ví dụ có thể chạy:

Tạo **`CollatorDecompositionDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorDecompositionDemo {
    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        System.out.println("String.equals=" + a.equals(b));
        System.out.println("Collator.equal=" +
                (collator.compare(a, b) == 0));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 CollatorDecompositionDemo.java
java -cp . CollatorDecompositionDemo
```

Kết quả:

```text
String.equals=false
Collator.equal=true
```

Điều này minh họa sự khác nhau giữa **giá trị chuỗi chính xác** và **tương đương khi so sánh theo collation**. Không dùng `collator.compare(a,b)==0` để suy ra hai chuỗi bằng nhau từng code unit, byte, code point hoặc có cùng giá trị hash.

## 7. Dùng `Collator` để sắp xếp `List<String>`

Cách trực tiếp:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);

List<String> names = new ArrayList<>(
        List.of("An", "Bình", "Ánh", "Dũng"));

names.sort((a, b) -> collator.compare(a, b));
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập; cần import `Collator`, `Locale`, `List`, `ArrayList`.

Một số lựa chọn tương đương tùy API:

```java
names.sort(collator::compare);
Collections.sort(names, collator::compare);
```

`Collator` triển khai `Comparator<Object>` nên có thể dùng lambda hoặc method reference để làm rõ kiểu `String`. Lệnh `List.sort` sắp xếp **tại chỗ**, vì vậy danh sách phải hỗ trợ chỉnh sửa.

**Không nên làm:**

```java
// Không phải quy tắc sắp xếp ngôn ngữ tự nhiên:
names.sort(String::compareTo);
```

Đoạn trên có thể hợp lệ với dữ liệu giao thức hoặc khóa hệ thống cần thứ tự mã Unicode, nhưng không được coi là thay thế cho sắp xếp tên theo locale của người dùng.

### Định nghĩa tie-breaker khi hai giá trị bằng nhau theo collation

Nếu ở strength thấp, hai chuỗi có thể `compare(...) == 0`, `List.sort` trên Java là **stable sort**: các phần tử bằng nhau theo comparator giữ thứ tự tương đối. Trong một giao diện có đầu vào từ nhiều nguồn khác nhau, một kết quả xếp thứ tự tổng thể ổn định qua lần tải có thể cần tiêu chí phụ.

Ví dụ:

```java
Comparator<String> comparator = (a, b) -> {
    int byLocale = collator.compare(a, b);
    return byLocale != 0 ? byLocale : a.compareTo(b);
};
names.sort(comparator);
```

Đoạn này giả định `collator` và `names` đã được tạo, cần import `Comparator`. Nó chọn thứ tự code-unit như **tie-breaker**. Tuy nhiên, chỉ dùng tie-breaker khi **mục tiêu là sắp xếp có thứ tự xác định**; nếu nghiệp vụ muốn xem hai chuỗi như cùng một tên cho mục đích tra cứu, đừng trộn quy tắc này với định nghĩa “bằng nhau” mà không giải thích.

## 8. Cảnh báo với `TreeSet`, `TreeMap` và ý nghĩa `compare == 0`

Đây là một lỗi thiết kế rất phổ biến.

`TreeSet` và `TreeMap` sử dụng comparator để quyết định hai khóa có **tương đương trong cấu trúc sắp xếp** hay không. Nếu comparator trả `0`, hai chuỗi có thể được xem là **cùng một khóa**, dù `String.equals` trả `false`.

Ví dụ chạy được, tạo **`CollatorSetDemo.java`**:

```java
import java.text.Collator;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class CollatorSetDemo {
    public static void main(String[] args) {
        String first = "resume";
        String second = "résumé";

        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);

        Set<String> set = new TreeSet<>(
                (a, b) -> collator.compare(a, b));

        set.add(first);
        set.add(second);

        System.out.println("equals=" + first.equals(second));
        System.out.println("collationEqual=" +
                (collator.compare(first, second) == 0));
        System.out.println("setSize=" + set.size());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CollatorSetDemo.java
java -cp . CollatorSetDemo
```

Kết quả minh họa với locale US:

```text
equals=false
collationEqual=true
setSize=1
```

**Giải thích:** `TreeSet` dùng comparator để xác định tính duy nhất. Vì `PRIMARY` coi hai từ tương đương ở ví dụ, tập hợp chỉ giữ **một phần tử**, không phải hai.

Đây có thể là hành vi có chủ đích nếu làm một danh sách từ được gộp theo phát âm/cách viết; nhưng thường **không đúng** nếu cần giữ mỗi mã người dùng hoặc chuỗi dữ liệu chính xác. Khi xây cấu trúc set/map, phải quyết định rõ liệu “bằng nhau” nghĩa là bằng nhau về ngôn ngữ hay bằng nhau về định danh. Nếu cần hai khái niệm cùng lúc, nên lưu danh tính theo khóa riêng và chỉ dùng collator để sắp xếp phần hiển thị.

**Không thay đổi strength hoặc decomposition của comparator sau khi đã đưa nó vào `TreeSet`/`TreeMap` có dữ liệu.** Việc thay thứ tự so sánh trong lúc cấu trúc đang giữ phần tử có thể phá các giả định về thứ tự và tra cứu.

## 9. `CollationKey`: khi phải so sánh nhiều lần

Mỗi lần `Collator.compare(a,b)`, bộ so sánh có thể phải xử lý nhiều quy tắc ngôn ngữ. Nếu một danh sách lớn được sort nhiều lần hoặc dùng cùng các chuỗi trong nhiều lần so sánh, Java có `CollationKey`:

```java
CollationKey key = collator.getCollationKey(text);
```

Các khóa được sinh từ **cùng cấu hình collation** có thể so sánh bằng `keyA.compareTo(keyB)`. Mẫu này có ích khi chuyển đổi mỗi chuỗi sang khóa một lần rồi dùng chúng trong quá trình sắp xếp.

Ví dụ độc lập **`CollationKeyDemo.java`**:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;

public class CollationKeyDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);

        CollationKey apple = collator.getCollationKey("apple");
        CollationKey banana = collator.getCollationKey("banana");

        System.out.println("appleBeforeBanana=" +
                (apple.compareTo(banana) < 0));
        System.out.println("sameLocale=" +
                apple.getSourceString().equals("apple"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CollationKeyDemo.java
java -cp . CollationKeyDemo
```

Kết quả:

```text
appleBeforeBanana=true
sameLocale=true
```

**Không đem `CollationKey` từ hai collator khác nhau ra so sánh** — đặc biệt nếu locale, strength, decomposition hoặc dữ liệu provider khác. `CollationKey` dùng trong phạm vi một **collation profile** nhất quán, không phải khóa phân loại chung cho mọi locale.

Đừng xem bytes của collation key là định dạng lưu trữ bền vững độc lập phiên bản. Nếu dùng làm chỉ mục sort trong cơ sở dữ liệu/cache, cần chính sách invalidation hoặc xây lại khi nâng cấp quy tắc collation, dữ liệu CLDR, JDK hoặc thay strength.

### Khi nào chọn `compare` hay `CollationKey`?

- **Một hoặc vài lần so sánh:** gọi `collator.compare(a,b)` trực tiếp, đơn giản hơn.
- **Nhiều lần so sánh cùng tập chuỗi:** cân nhắc tạo `CollationKey` một lần; đo hiệu năng và chi phí bộ nhớ.
- **Dữ liệu lớn trong database:** cần khảo sát collation của DB và cách đồng bộ với Java; đừng tạo toàn bộ khóa Java trong bộ nhớ khi truy vấn DB đã hỗ trợ sort đúng ngôn ngữ và quy tắc nhất quán.

## 10. Phân biệt so sánh ngôn ngữ với chuẩn hóa Unicode

`Normalizer` xử lý các biểu diễn Unicode theo dạng canonical hoặc compatibility: `NFC`, `NFD`, `NFKC`, `NFKD`. Trong khi đó, `Collator` thực hiện **thứ tự so sánh theo locale**, có thể coi những chuỗi khác code point là tương đương ở một strength nhất định.

| Nhu cầu | API hoặc cơ chế nên cân nhắc |
| --- | --- |
| Đưa `é` dựng sẵn và `e + dấu sắc` về một biểu diễn canonical | `Normalizer.normalize(..., NFC)` hoặc NFD tùy hợp đồng |
| Sắp xếp tên tiếng Việt theo quy tắc ngôn ngữ | `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` |
| Không phân biệt một số dấu/chữ hoa trong so khớp | Collation strength theo locale, hoặc search index chuyên dụng |
| So sánh ID chính xác từng ký tự Java | `String.equals` cùng hợp đồng canonicalization/validation đã công bố |
| So sánh dữ liệu mật mã, chữ ký, token | Quy tắc byte/encoding/protocol cụ thể; không dùng collator |
| Phân đoạn từ, tìm kiếm mờ, bỏ dấu có chọn lọc | Search engine/thuật toán riêng, không chỉ `Collator` |

`Collator` **không tự làm sạch input, không xóa ký tự điều khiển, không ngăn homograph attacks** và không tự xác thực danh tính. Hai chữ trông giống nhau ở hai script khác nhau có thể có quy tắc so sánh khác nhau; không suy ra security policy từ một kết quả `compare`.

Đối với dữ liệu Unicode không đồng nhất, nên xác định profile chuẩn hóa trước khi lưu/index; dùng collation theo locale khi **hiển thị hoặc tìm kiếm theo ngôn ngữ**. Hai bước bổ sung nhau, không thay thế nhau.

## 11. Dùng `Collator` trong ứng dụng đa luồng

`Collator` có các setter như `setStrength` và `setDecomposition`, vì vậy nó là **đối tượng mutable**. Không nên có một singleton `Collator` rồi thay strength/locale theo từng request.

Một số triển khai JDK có thể đồng bộ hóa phần so sánh nội bộ để bảo đảm hoạt động đồng thời, nhưng việc nhiều luồng chia sẻ cùng một `RuleBasedCollator` vẫn có thể dẫn đến **contention** đáng kể; điều này không biến thay đổi cấu hình đồng thời thành một thiết kế an toàn. Chiến lược thận trọng:

- Tạo `Collator.getInstance(locale)` riêng cho từng tác vụ/luồng hoặc dùng `clone()` từ **formatter mẫu đã thiết lập xong**.
- Không thay strength/decomposition khi các luồng khác đang so sánh bằng cùng instance.
- Nếu cache, giữ **cấu hình bất biến ở mức ứng dụng**: không cho caller sửa trực tiếp một object cache chung; cân nhắc tạo bản clone cho từng tác vụ.
- Dùng comparator có cấu hình ổn định trong suốt **toàn bộ lần sắp xếp**; không thay đổi các thuộc tính trong lúc sort.
- Đo hiệu năng trên workload thực tế nếu có nhiều request; đừng chọn cache chung chỉ để giảm số lần khởi tạo mà tạo điểm nghẽn.

Ví dụ kỹ thuật:

```java
Collator template = Collator.getInstance(locale);
template.setStrength(Collator.TERTIARY);

// Mỗi tác vụ có một bản riêng, không sửa template:
Collator local = (Collator) template.clone();
```

Đây là **đoạn mã minh họa**, giả định `locale` đã có; cần import `Collator`. Nếu `template` được công bố cho các thread khác, phải ngăn bên khác sửa nó trong quá trình dùng làm khuôn.

Khác với `DateTimeFormatter` của `java.time`, `Collator` **không có hợp đồng bất biến** chỉ vì nó được cất vào biến `static final`.

## 12. Hệ quả khi phân trang, lưu trong database và xuất file

Cần phân biệt hai trường hợp:

**Hiển thị danh sách cho một người dùng:** sử dụng collator theo locale và strength tương ứng có thể tạo thứ tự tự nhiên.

**Lưu thứ tự bền vững/phân trang đồng nhất trên server-client:** nếu máy chủ dùng collation của database nhưng ứng dụng Java dùng `Collator` với quy tắc khác, kết quả `ORDER BY`, ranh giới trang hoặc thứ tự của các phần tử bằng nhau có thể khác. Khi đó:

1. Xác định **một nguồn quy tắc sort chính** cho dữ liệu được phân trang.
2. Ghi rõ locale, version và strength nếu cần tái tạo kết quả.
3. Có tiêu chí phụ ổn định (ví dụ ID) để phá hòa khi nhiều chuỗi collation-equivalent.
4. Không dùng collation key của một runtime làm khóa vĩnh viễn mà không có chiến lược versioning.
5. Kiểm thử khi nâng cấp JDK, provider locale, dữ liệu CLDR hoặc collation của database.

Nếu một hệ thống hỗ trợ nhiều locale mà vẫn dùng **một chỉ mục duy nhất** cho mọi người dùng, cần cân nhắc hiệu năng, quyền lựa chọn locale sắp xếp và yêu cầu nhất quán nghiệp vụ. Không có một thứ tự alphabet “phổ quát” tối ưu cho mọi ngôn ngữ.

## 13. Sai lầm thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `String.compareTo` để sắp xếp tên đa ngôn ngữ | Thứ tự theo UTF-16 thay vì quy ước ngôn ngữ | Dùng `Collator.getInstance(locale)` |
| Dùng `Collator.getInstance()` trên server mà không quản lý default locale | Kết quả có thể phụ thuộc môi trường | Truyền `Locale` tường minh |
| Nghĩ `getInstance(locale)` tự dịch dữ liệu | Không có bản dịch nào được tạo | Tách localization tài nguyên khỏi collation |
| Cho rằng mọi `Locale` đều có quy tắc hỗ trợ đầy đủ | Có thể phải dùng fallback/provider khác | Kiểm tra runtime thực tế và `getAvailableLocales` |
| Coi `compare()==0` là `String.equals` | Gộp nhầm dữ liệu hoặc tài khoản | Chọn khái niệm bằng nhau cho từng nghiệp vụ |
| Dùng `PRIMARY` trong `TreeSet` giữ các chuỗi khác dấu | Có thể mất phần tử như `resume`/`résumé` | Dùng khóa định danh riêng hoặc comparator phù hợp |
| Thay `setStrength` sau khi `TreeMap` đã có dữ liệu | Phá trật tự/tra cứu của cây | Cố định comparator khi tạo cấu trúc |
| Lưu collation key vĩnh viễn | Không có cam kết độc lập phiên bản/locale | Quản lý version và xây lại khi đổi policy |
| So sánh `CollationKey` từ hai collator khác nhau | Kết quả không có nghĩa theo một profile duy nhất | Chỉ so sánh khóa cùng profile |
| Nghĩ `setDecomposition` thay `Normalizer.normalize` | Không tạo chuỗi chuẩn hóa để lưu | Dùng `Normalizer` khi cần chuẩn hóa dữ liệu |
| Chia sẻ singleton mutable rồi sửa strength theo từng user | Nhiễu cấu hình giữa các request | Per-task clone/instance riêng, cấu hình ổn định |
| Tin snapshot sort đúng mọi JDK/version | Dữ liệu locale và collation có thể thay đổi | Kiểm thử môi trường thực, versioning khi cần |
| Dùng collation như phép xác thực/security | Có thể gộp nhiều chuỗi khác mã hóa | Bảo mật phải theo profile định danh và quy tắc byte/canonical |

## 14. Quy trình ứng dụng và kiểm thử

Khi bổ sung sắp xếp theo locale cho một tính năng:

1. **Xác định phạm vi:** danh sách tên người, thành phố, từ điển, danh mục; kết quả hiển thị hay khóa lưu trữ?
2. **Chọn locale tường minh:** từ cài đặt người dùng hoặc chính sách sản phẩm; không lấy ngầm locale JVM nếu tính năng phục vụ nhiều người.
3. **Chọn strength/decomposition:** xác định có cần phân biệt dấu, chữ hoa/thường, hay giữ mọi khác biệt; kiểm thử đúng nhóm ngôn ngữ được hỗ trợ.
4. **Tạo một collator cho một lần sort:** cấu hình xong trước khi sắp xếp, không thay đổi khi comparator đang được dùng.
5. **Phân biệt equality và ordering:** nếu dùng `TreeSet/TreeMap` hoặc kiểm tra trùng, xác định rõ hệ quả của `compare()==0`.
6. **Dữ liệu Unicode:** có chính sách lưu/chuẩn hóa riêng khi cần; không dùng collation thay validation.
7. **Phân trang/DB:** đồng bộ quy tắc sort giữa Java, truy vấn và API; có tie-breaker ổn định.
8. **Kiểm thử khác locale:** tiếng Thụy Điển/Đức cho `ä`, tiếng Việt có dấu, dữ liệu pha nhiều script, những từ khác nhau chỉ ở case hoặc dấu.
9. **Kiểm thử thay đổi runtime:** cập nhật JDK/CLDR/provider có thể đổi thứ tự; ghi nhận dữ liệu locale và hạn chế snapshot quá cứng khi không cần thiết.
10. **Đo hiệu năng:** nếu sort khối lượng lớn nhiều lần, so sánh chi phí trực tiếp với `CollationKey`; không mặc định khóa cache là tối ưu.

Một phép thử ngắn về hợp đồng locale (không kiểm tra toàn bộ thứ tự của bảng chữ cái) có thể dùng:

```java
import java.text.Collator;
import java.util.Locale;

public class CollatorAssertions {
    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Collation assertion failed");
        }
    }

    public static void main(String[] args) {
        Collator swedish = Collator.getInstance(
                Locale.forLanguageTag("sv-SE"));
        Collator german = Collator.getInstance(Locale.GERMANY);

        require(swedish.compare("ä", "z") > 0);
        require(german.compare("ä", "z") < 0);

        Collator us = Collator.getInstance(Locale.US);
        us.setStrength(Collator.PRIMARY);
        require(us.compare("resume", "résumé") == 0);

        require(!"resume".equals("résumé"));
        System.out.println("4 checks passed");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CollatorAssertions.java
java -cp . CollatorAssertions
```

Kết quả trên JDK có các quy tắc collation tương ứng như ví dụ:

```text
4 checks passed
```

Vì kết quả sort phụ thuộc dữ liệu locale, những assertion này phù hợp như **regression tests cho runtime đã lựa chọn**, không nên coi là chứng minh độc lập mọi phiên bản và provider. Nếu provider thay đổi, cần đánh giá thay đổi collation có chấp nhận được theo yêu cầu của sản phẩm hay không.

## 15. Tổng kết

- Dùng **`Collator.getInstance(Locale)`** khi cần so sánh/sắp xếp chuỗi theo ngôn ngữ cụ thể; tránh phụ thuộc default locale của server.
- `Collator.compare(a,b)` trả **âm, 0, dương** theo quy tắc locale và cấu hình, không phải theo `String.compareTo`.
- `setStrength` kiểm soát mức khác biệt được coi là đáng kể; `setDecomposition` ảnh hưởng xử lý phân rã Unicode khi so sánh.
- `compare()==0` có thể xảy ra với các chuỗi **không bằng nhau theo `String.equals`**. Đặc biệt cẩn thận với `TreeSet`, `TreeMap` và xác thực định danh.
- Dùng `CollationKey` khi có nhiều phép so sánh lặp với cùng profile, nhưng không trộn khóa giữa các collator hoặc dùng làm dữ liệu lưu trữ không version.
- `Collator` **mutable**; cấu hình ổn định trước khi sort, cân nhắc instance riêng/clone trong môi trường nhiều luồng.
- **Locale, strength, decomposition, provider và dữ liệu runtime** đều có thể ảnh hưởng thứ tự. Đối với phân trang và dữ liệu bền vững, phải thiết kế quy tắc sort nhất quán giữa Java và hệ thống lưu trữ.
