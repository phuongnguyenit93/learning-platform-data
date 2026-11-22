# Phân biệt hoa–thường, dấu và quy tắc ngôn ngữ khi so sánh chuỗi Java

## 1. “Hai chuỗi giống nhau” là yêu cầu chưa đủ rõ

Ứng dụng Java đa ngôn ngữ thường phải tìm kiếm tên người, sắp xếp từ điển, kiểm tra mã định danh và đối chiếu nội dung. Mỗi mục tiêu cần một **chính sách so sánh khác nhau**.

| Cặp văn bản | Khác biệt | Vì sao quan trọng? |
| --- | --- | --- |
| `Java` / `java` | Hoa–thường | Có thể bỏ qua trong tìm kiếm nhưng không nhất thiết trong mã định danh |
| `cafe` / `café` | Dấu | Tìm kiếm tiếng Pháp có thể chấp nhận gần đúng, bản gốc vẫn khác |
| `ma` / `má` / `mã` / `mạ` | Thanh điệu tiếng Việt | Bỏ dấu có thể gộp **những từ khác nghĩa** |
| `I` / `ı` / `İ` / `i` | Case theo tiếng Thổ Nhĩ Kỳ | Quy tắc đối chiếu khác tiếng Anh |
| `Straße` / `Strasse` | `ß` và `ss` tiếng Đức | Có thể tương đương ở một mức collation nhưng không bằng nhau theo `String.equals` |
| `café` / `cafe\u0301` | Hai biểu diễn Unicode của `é` | Tương đương chuẩn tắc, nhưng `String.equals` chưa chắc true |

Trước khi dùng API, hãy quyết định: yêu cầu **bằng từng ký tự**, **bỏ qua case**, **so sánh theo quy tắc ngôn ngữ**, hay **tìm kiếm khoan dung dấu**? Không nên lấy cùng một phép biến đổi cho cả bốn.

**Nguyên tắc chính:** khác biệt hoa–thường và dấu không chỉ là trình bày. Trong nhiều ngôn ngữ, chúng thay đổi nghĩa hoặc cách viết của từ. Collation (đối chiếu theo locale) là một **quy tắc sắp xếp/so khớp**, không phải bằng chứng hai thực thể là một.

## 2. String.equals, equalsIgnoreCase và compareTo

Các phương thức lõi của `String` có hợp đồng:

| API | So sánh gì? | Theo Locale? |
| --- | --- | --- |
| `a.equals(b)` | Hai chuỗi cùng các UTF-16 code unit ở cùng vị trí | Không |
| `a.compareTo(b)` | Thứ tự lexicographic theo UTF-16 | Không |
| `a.equalsIgnoreCase(b)` | So case-insensitive theo thuật toán của `String` | **Không** |
| `a.compareToIgnoreCase(b)` | Thứ tự bỏ qua case của `String` | **Không** |
| `String.CASE_INSENSITIVE_ORDER` | Comparator theo `compareToIgnoreCase` | **Không** |
| `Collator.getInstance(locale).compare(a,b)` | Thứ tự collation của một ngôn ngữ | **Có** |

`equalsIgnoreCase` rất tiện khi so tên từ khóa kỹ thuật đơn giản, nhưng **không phải bộ so khớp ngôn ngữ toàn diện**. Nó không tự xóa dấu hay thực hiện mọi phép mở rộng nhiều ký tự như `ß → ss`.

### Ví dụ chạy độc lập Java 17+

Tạo `StringComparisonDemo.java`:

~~~java
public class StringComparisonDemo {
    public static void main(String[] args) {
        String first = "Java";
        String second = "java";

        System.out.println("equals: " + first.equals(second));
        System.out.println("equalsIgnoreCase: "
                + first.equalsIgnoreCase(second));
        System.out.println("compareTo zero: "
                + (first.compareTo(second) == 0));
        System.out.println("Accent ignored: "
                + "cafe".equalsIgnoreCase("café"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StringComparisonDemo.java
java StringComparisonDemo
~~~

Đầu ra:

~~~text
equals: false
equalsIgnoreCase: true
compareTo zero: false
Accent ignored: false
~~~

`compareTo` không phải quy tắc sắp xếp tên theo tiếng Việt, tiếng Pháp hay tiếng Đức. Nó dùng giá trị các đơn vị UTF-16. Khi cần sắp xếp theo ngôn ngữ của người đọc, dùng `Collator`.

## 3. Collator: so sánh chuỗi theo Locale

`java.text.Collator` cung cấp phép so sánh và sắp xếp văn bản theo locale:

~~~java
Locale locale = Locale.forLanguageTag("fr-FR");
Collator col = Collator.getInstance(locale);
int result = col.compare("cafe", "café");
~~~

Đây là **mảnh mã trong một phương thức**, cần import `java.text.Collator` và `java.util.Locale`.

Quy tắc trả kết quả giống `Comparator`:

- Âm: chuỗi thứ nhất đứng trước.
- `0`: hai chuỗi tương đương **theo cấu hình collator hiện tại**.
- Dương: chuỗi thứ nhất đứng sau.

Không diễn giải `compare(a,b)==0` là `a.equals(b)`. Trong một chế độ so sánh ít phân biệt, `cafe` và `café` có thể ngang nhau dù chúng là hai chuỗi khác nhau.

### Strength: mức độ phân biệt

| Thuộc tính | Ý nghĩa thông thường | Ứng dụng |
| --- | --- | --- |
| `Collator.PRIMARY` | Xét khác biệt chữ cơ sở; nhiều locale bỏ qua case và một số dấu | So gần đúng/tìm kiếm theo locale |
| `Collator.SECONDARY` | Xét thêm các khác biệt thứ cấp, thường là dấu | Phân biệt accent khi ngôn ngữ yêu cầu |
| `Collator.TERTIARY` | Xét thêm các khác biệt như chữ hoa–thường | Sắp xếp chi tiết hơn |
| `Collator.IDENTICAL` | Cấp phân biệt cao nhất theo cơ chế collation | Không được nhầm với `String.equals` |

Các mức này không có nghĩa “PRIMARY xóa mọi dấu, SECONDARY chỉ kiểm tra dấu, TERTIARY chỉ kiểm tra hoa–thường” trong **mọi locale**. Mức độ và quy tắc thực tế phụ thuộc ngôn ngữ, provider và dữ liệu JDK.

### Ví dụ chạy độc lập

Tạo `CollatorStrengthDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    public static void main(String[] args) {
        Collator fr = Collator.getInstance(Locale.FRENCH);

        fr.setStrength(Collator.PRIMARY);
        System.out.println("PRIMARY cafe/café: "
                + (fr.compare("cafe", "café") == 0));

        fr.setStrength(Collator.SECONDARY);
        System.out.println("SECONDARY cafe/café: "
                + (fr.compare("cafe", "café") == 0));

        fr.setStrength(Collator.TERTIARY);
        System.out.println("TERTIARY Cafe/cafe: "
                + (fr.compare("Cafe", "cafe") == 0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CollatorStrengthDemo.java
java CollatorStrengthDemo
~~~

Kết quả trong dữ liệu collation tiếng Pháp phổ biến:

~~~text
PRIMARY cafe/café: true
SECONDARY cafe/café: false
TERTIARY Cafe/cafe: false
~~~

Đây là các kết quả theo chính sách so sánh. Chúng **không sửa** ký tự trong chuỗi `"café"` và không có nghĩa mọi từ khác dấu đều là một.

## 4. Tiếng Thổ Nhĩ Kỳ: quy tắc I, İ, i, ı

Tiếng Thổ Nhĩ Kỳ là ví dụ nổi bật cho sự khác nhau giữa case-insensitive chung và đối chiếu theo locale:

- `I`: chữ I hoa **không chấm**.
- `ı`: chữ i thường **không chấm**.
- `İ`: chữ I hoa **có chấm**.
- `i`: chữ i thường **có chấm**.

Trong cách chuyển chữ tiếng Thổ Nhĩ Kỳ, cặp `I/ı` đi với nhau, còn `İ/i` đi với nhau.

### Ví dụ Java 17+ đầy đủ

Tạo `TurkishCaseDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class TurkishCaseDemo {
    public static void main(String[] args) {
        Locale tr = Locale.forLanguageTag("tr-TR");

        System.out.println("ROOT I lower: "
                + "I".toLowerCase(Locale.ROOT));
        System.out.println("TR I lower: "
                + "I".toLowerCase(tr));
        System.out.println("TR i upper: "
                + "i".toUpperCase(tr));

        System.out.println("equalsIgnoreCase I/i: "
                + "I".equalsIgnoreCase("i"));
        System.out.println("equalsIgnoreCase I/ı: "
                + "I".equalsIgnoreCase("ı"));

        Collator col = Collator.getInstance(tr);
        col.setStrength(Collator.PRIMARY);
        System.out.println("TR PRIMARY I/ı: "
                + (col.compare("I", "ı") == 0));
        System.out.println("TR PRIMARY I/i: "
                + (col.compare("I", "i") == 0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TurkishCaseDemo.java
java TurkishCaseDemo
~~~

Kết quả thông dụng của JDK:

~~~text
ROOT I lower: i
TR I lower: ı
TR i upper: İ
equalsIgnoreCase I/i: true
equalsIgnoreCase I/ı: true
TR PRIMARY I/ı: true
TR PRIMARY I/i: false
~~~

**Ý nghĩa:** `String.equalsIgnoreCase` không biết locale tiếng Thổ Nhĩ Kỳ, còn `Collator(tr-TR, PRIMARY)` áp dụng quy tắc đối chiếu theo ngôn ngữ. Vì vậy hai phương thức có thể đưa ra **kết luận khác nhau** trên cùng cặp chuỗi.

Trong một hệ thống có người dùng nhiều ngôn ngữ, **không** dùng `String.toLowerCase()` không tham số để tạo khóa kỹ thuật: nó dùng locale mặc định JVM. Nếu trường dữ liệu kỹ thuật được định nghĩa theo quy tắc trung lập, dùng `Locale.ROOT` **khi đúng hợp đồng**; nếu đang xử lý ngôn ngữ tự nhiên, cân nhắc locale của người dùng.

## 5. Tiếng Đức: ß và ss

`"Straße"` và `"Strasse"` không bằng nhau theo `String.equals`. `equalsIgnoreCase` cũng không biến một ký tự `ß` thành hai ký tự `ss` để làm chúng bằng nhau.

Tuy nhiên, một collator tiếng Đức ở mức PRIMARY có thể xem chúng tương đương theo quy tắc collation.

Tạo `GermanCollationDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class GermanCollationDemo {
    public static void main(String[] args) {
        String a = "Straße";
        String b = "Strasse";

        System.out.println("equals: " + a.equals(b));
        System.out.println("equalsIgnoreCase: "
                + a.equalsIgnoreCase(b));

        Collator de = Collator.getInstance(Locale.GERMAN);
        de.setStrength(Collator.PRIMARY);

        System.out.println("DE PRIMARY: "
                + (de.compare(a, b) == 0));
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 GermanCollationDemo.java
java GermanCollationDemo
~~~

Kết quả với dữ liệu tiếng Đức phổ biến:

~~~text
equals: false
equalsIgnoreCase: false
DE PRIMARY: true
~~~

Kết luận là **các thuật toán đang thực hiện các mục tiêu khác nhau**, không phải `Collator` đã sửa dữ liệu gốc. Không thay tên `Straße` thành `Strasse` trong cơ sở dữ liệu chỉ vì muốn tìm kiếm gần đúng.

## 6. Dấu và Unicode normalization không phải cùng vấn đề

Hai chuỗi có thể chứa cùng chữ có dấu dưới **hai dạng Unicode tương đương chuẩn tắc**:

~~~text
"café"       : c a f U+00E9
"cafe\u0301" : c a f e U+0301
~~~

`U+0301` là *COMBINING ACUTE ACCENT*. `String.equals` so sánh UTF-16 code unit, không tự đưa hai dạng về chuẩn NFC.

Java hỗ trợ `java.text.Normalizer`:

~~~java
String aNfc = Normalizer.normalize(a, Normalizer.Form.NFC);
String bNfc = Normalizer.normalize(b, Normalizer.Form.NFC);
boolean sameCanonicalText = aNfc.equals(bNfc);
~~~

Đây là mảnh mã trong method, cần import `java.text.Normalizer`, có biến `a` và `b`.

### Ví dụ Java 17+ độc lập

Tạo `CanonicalComparisonDemo.java`:

~~~java
import java.text.Normalizer;

public class CanonicalComparisonDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("Raw lengths: "
                + composed.length() + " / " + decomposed.length());

        String left = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String right = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: " + left.equals(right));
        System.out.println("Accent retained: "
                + left.equals("café"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CanonicalComparisonDemo.java
java CanonicalComparisonDemo
~~~

Đầu ra:

~~~text
Raw equals: false
Raw lengths: 4 / 5
NFC equals: true
Accent retained: true
~~~

**NFC giữ dấu**: sau normalization, `café` vẫn khác `cafe`. NFC/NFD xử lý **cách biểu diễn tương đương** chứ không nhằm bỏ thông tin ngữ nghĩa.

### Strength và decomposition của Collator

Ngoài `setStrength`, `Collator` có `setDecomposition`:

- `NO_DECOMPOSITION`: không yêu cầu phân rã trước khi collation.
- `CANONICAL_DECOMPOSITION`: cho phép xử lý phân rã chuẩn tắc.
- `FULL_DECOMPOSITION`: xét cả phân rã tương thích theo cơ chế collation.

Ví dụ:

~~~java
Collator fr = Collator.getInstance(Locale.FRENCH);
fr.setStrength(Collator.SECONDARY);
fr.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
~~~

Đây là mảnh mã trong method, cần import `java.text.Collator` và `java.util.Locale`.

**Decomposition khác strength**: một thuộc tính về cách diễn giải biểu diễn Unicode, một thuộc tính về mức khác biệt trong so khớp. `FULL_DECOMPOSITION` không phải “xóa mọi dấu”; `Collator.IDENTICAL` cũng không phải tên khác của `String.equals`.

## 7. Bỏ dấu là phép biến đổi mất thông tin

Một cách tạo khóa tìm kiếm khoan dung dấu thường thấy:

~~~java
String searchKey = Normalizer
        .normalize(source, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "")
        .toLowerCase(Locale.ROOT);
~~~

Đây là mảnh mã trong method, cần import `java.text.Normalizer` và `java.util.Locale`.

Nó gồm **ba phép biến đổi**:

1. Phân rã Unicode canonical (NFD).
2. Xóa ký tự có Unicode general category Mark (`\p{M}`).
3. Chuyển chữ thường theo `Locale.ROOT`.

Điều này **không trung lập**: `ma`, `má`, `mà`, `mả`, `mã` và `mạ` đều có thể thành `ma`, dù khác nghĩa tiếng Việt. Hơn nữa, xóa Mark có thể làm mất thành phần thiết yếu của nhiều hệ chữ khác, và **không** đảm bảo tạo ASCII: `Đ/đ` hay `ß` không nhất thiết được chuyển thành chữ Latin cơ sở.

| Cơ chế | Vai trò | Có thay đổi văn bản nguồn không? |
| --- | --- | --- |
| `Normalizer.Form.NFC` | Thống nhất tương đương chuẩn tắc | Tạo dạng khác nhưng giữ sự phân biệt dấu có nghĩa |
| `Collator.PRIMARY` | So theo mức collation phù hợp locale | Không sửa chuỗi nguồn |
| `NFD + xóa \p{M}` | Tạo bản không dấu gần đúng | **Có, mất thông tin** |
| Transliteration | Chuyển hệ chữ theo quy tắc | Có thể mất thông tin; không phải normalization |
| Case mapping | Chuyển hoa–thường | Có thể thay đổi ký tự/độ dài, tùy locale |

**Thực hành an toàn:** lưu bản gốc có dấu; nếu cần tìm kiếm khoan dung, tạo search key **phụ** hoặc dùng khả năng collation của search engine/database. Giữ ID riêng để xử lý collision.

## 8. So sánh để sắp xếp và so sánh để định danh là hai việc khác nhau

`List.sort(collator)` cho phép sắp danh sách tên theo locale. Nhưng comparator có thể xem hai chuỗi **ngang nhau** khi strength thấp.

Điều này ảnh hưởng đến những collection dùng comparator để quyết định tính duy nhất như `TreeSet` và `TreeMap`.

### Ví dụ Java 17+ đầy đủ về TreeSet

Tạo `CollationCollisionDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;
import java.util.TreeSet;

public class CollationCollisionDemo {
    public static void main(String[] args) {
        Collator fr = Collator.getInstance(Locale.FRENCH);
        fr.setStrength(Collator.PRIMARY);

        String first = "cafe";
        String second = "café";

        TreeSet<String> set = new TreeSet<>(fr);
        set.add(first);
        set.add(second);

        System.out.println("String equals: "
                + first.equals(second));
        System.out.println("Collator equals: "
                + (fr.compare(first, second) == 0));
        System.out.println("TreeSet size: " + set.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CollationCollisionDemo.java
java CollationCollisionDemo
~~~

Kết quả thông dụng với tiếng Pháp:

~~~text
String equals: false
Collator equals: true
TreeSet size: 1
~~~

`TreeSet` dùng comparator để xác định hai phần tử có trùng hay không, vì vậy hai chuỗi khác nhau về UTF-16 có thể bị coi là cùng khóa. Đây **không phải lỗi của TreeSet** mà là hệ quả của chính sách so sánh bạn chọn.

### Cách giữ cả hai giá trị khi sắp xếp

Nếu chỉ cần thứ tự hiển thị, có thể dùng `List.sort(collator)` rồi giữ từng bản ghi với ID độc lập. Nếu cần comparator phân biệt các giá trị gốc, bổ sung tie-breaker:

~~~java
Comparator<String> displayOrder = (left, right) -> {
    int result = collator.compare(left, right);
    return result != 0 ? result : left.compareTo(right);
};
~~~

Đây là mảnh mã trong method, cần import `java.util.Comparator` và có biến `collator` kiểu `Collator` đã cấu hình. Tie-breaker `String.compareTo` chỉ dùng **khi collator coi ngang nhau** để giữ một thứ tự ổn định/dễ phân biệt, không thay thế quy tắc collation chính. Với bản ghi có cùng tên nhưng ID khác, tie-break theo ID là cách làm đáng tin hơn.

## 9. Sắp xếp theo locale bằng List.sort

Ví dụ Java 17+ không cố định thứ tự phụ thuộc dữ liệu provider:

Tạo `LocaleSortDemo.java`:

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class LocaleSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("été", "eclair", "École", "eleve")
        );
        Collator fr = Collator.getInstance(Locale.FRENCH);
        fr.setStrength(Collator.TERTIARY);

        words.sort(fr);

        boolean sorted = true;
        for (int i = 1; i < words.size(); i++) {
            if (fr.compare(words.get(i - 1), words.get(i)) > 0) {
                sorted = false;
                break;
            }
        }
        System.out.println("Count: " + words.size());
        System.out.println("Sorted using French collation: " + sorted);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LocaleSortDemo.java
java LocaleSortDemo
~~~

Đầu ra:

~~~text
Count: 4
Sorted using French collation: true
~~~

Chương trình kiểm tra **tính chất được sắp xếp theo collator hiện dùng**, thay vì dựa vào một thứ tự ký tự cố định có thể đổi khi JDK cập nhật dữ liệu CLDR/provider.

`Collator` có trạng thái mutable qua `setStrength` và `setDecomposition`. Không chia sẻ một instance rồi đổi cấu hình liên tục theo từng request đa luồng. Tạo/copy cấu hình theo tác vụ hoặc kiểm soát đồng bộ phù hợp.

## 10. CollationKey cho nhiều lần so sánh

Nếu phải so sánh một tập chuỗi lớn rất nhiều lần, có thể tạo `CollationKey` từ collator đã cấu hình:

~~~java
Collator fr = Collator.getInstance(Locale.FRENCH);
fr.setStrength(Collator.PRIMARY);

CollationKey first = fr.getCollationKey("cafe");
CollationKey second = fr.getCollationKey("café");

int result = first.compareTo(second);
~~~

Đây là mảnh mã trong method, cần import `java.text.Collator`, `java.text.CollationKey` và `java.util.Locale`.

### Ví dụ đầy đủ

Tạo `CollationKeyDemo.java`:

~~~java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;

public class CollationKeyDemo {
    public static void main(String[] args) {
        Collator fr = Collator.getInstance(Locale.FRENCH);
        fr.setStrength(Collator.PRIMARY);
        fr.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

        CollationKey a = fr.getCollationKey("cafe");
        CollationKey b = fr.getCollationKey("café");

        System.out.println("Direct equivalent: "
                + (fr.compare("cafe", "café") == 0));
        System.out.println("Key equivalent: "
                + (a.compareTo(b) == 0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CollationKeyDemo.java
java CollationKeyDemo
~~~

Kết quả trong dữ liệu tiếng Pháp thông dụng:

~~~text
Direct equivalent: true
Key equivalent: true
~~~

**Chỉ so các CollationKey được tạo từ cấu hình tương thích**, tức cùng locale, strength, decomposition và các quy tắc liên quan. Không dùng byte của `CollationKey.toByteArray()` làm mã định danh, chữ ký hoặc khóa lưu trữ lâu dài mà không có hợp đồng quản lý phiên bản: dữ liệu collation có thể thay đổi khi nâng JDK/provider.

## 11. Hoa–thường không chỉ là đổi từng char

`String.toLowerCase(Locale)` và `String.toUpperCase(Locale)` là các phép **biến đổi chuỗi**, khác với `equalsIgnoreCase`. Một phép case mapping Unicode có thể đổi độ dài chuỗi: ví dụ chữ `İ` trong một số bối cảnh lowercasing có thể được biểu diễn thành `i` + combining dot.

Những sai lầm cần tránh:

- Dùng `Character.toLowerCase(char)` rồi nghĩ đã xử lý mọi phép biến đổi case nhiều code point.
- Dùng `toLowerCase()` mặc định cho khóa hệ thống và ngạc nhiên khi đổi server locale.
- Dùng `Locale.ROOT` cho so tên người và mặc định quy tắc ấy đúng cho mọi ngôn ngữ.
- Dùng `equalsIgnoreCase` để suy ra hai tên chính thức hoặc hai tài khoản luôn tương đương.

Khi cần đối chiếu ngôn ngữ, hãy dùng một công cụ có chính sách locale rõ. Khi cần xử lý **mã kỹ thuật**, hãy định nghĩa schema: có phân biệt ASCII hoa/thường không, có cho Unicode không, có normalization nào, có cho phép ký tự confusable không. `Collator` và xóa dấu **không phải bộ xác thực bảo mật**.

## 12. Thiết kế dữ liệu: giữ bản gốc và hỗ trợ tìm kiếm hợp lý

Ví dụ danh bạ có ba tên `Ma`, `Má`, `Mã`. Nếu hệ thống chỉ giữ một khóa `ma` sau khi bỏ dấu, nó sẽ mất thông tin phân biệt.

Một thiết kế tốt hơn:

~~~text
Bản ghi:
  id = 101, displayName = "Ma"
  id = 102, displayName = "Má"
  id = 103, displayName = "Mã"

Bộ tìm kiếm:
  nhập "ma"
       |
       +--> kết quả so khớp chính xác theo bản gốc
       +--> kết quả tương đương hoa/thường
       +--> kết quả gần đúng theo chính sách không dấu

Giao diện:
  hiển thị lại đúng "Ma", "Má", "Mã"
  giữ các ID độc lập
~~~

Tìm kiếm không dấu có thể là tính năng tốt nếu được người dùng mong đợi, nhưng phải có ranking và giải quyết collision. Không dựa trên nó để quyết định tính duy nhất của tài khoản hoặc văn bản pháp lý.

Đối với password, token, khóa giao thức, mã xác thực, chữ ký số, đường dẫn bảo vệ quyền truy cập, phải tuân thủ **quy tắc so sánh của giao thức đó**. Collation theo ngôn ngữ thường không phù hợp và có thể khiến các chuỗi khác nhau bị đánh đồng.

## 13. Locale mặc định, provider và tính tái lập

`Collator.getInstance()` không có tham số có thể dùng default locale của JVM. Nếu trên máy phát triển locale mặc định khác production, thứ tự sắp xếp có thể khác. Với hệ thống nhiều người dùng:

~~~java
Locale viewer = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(viewer);
collator.setStrength(Collator.TERTIARY);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
~~~

Đây là mảnh mã trong method, cần import `java.util.Locale` và `java.text.Collator`.

Một phép kiểm thử collation đáng tin phải ghi rõ **locale**, **strength**, **decomposition**, **JDK/provider** và **mục tiêu**. Một phiên bản Java mới có thể cập nhật dữ liệu ngôn ngữ, khiến thứ tự các mục thay đổi mà không phải do lỗi chương trình.

Nếu sản phẩm có thứ tự từ điển pháp lý hoặc chỉ mục tìm kiếm được persisted, hãy có chiến lược versioning/rebuild khi nâng dữ liệu collation. Đừng gắn cứng output sắp xếp Unicode vào một thứ tự UTF-16 hay mặc định của máy chạy.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi `equalsIgnoreCase` là so sánh theo locale | Sai với quan hệ `I/i/ı/İ` tiếng Thổ Nhĩ Kỳ | Dùng `Collator(locale)` khi mục tiêu là ngôn ngữ |
| Dùng `compareTo` để sắp tên tiếng Việt | Thứ tự theo UTF-16 thay vì từ điển | Dùng collator có locale phù hợp |
| Nghĩ `PRIMARY` chỉ xóa dấu | Có thể gộp cả case và nhiều khác biệt thứ cấp | Hiểu đây là mức tương đương collation |
| Nghĩ `IDENTICAL` là `String.equals` | Nhầm quy tắc normalization và collation | Dùng so sánh chính xác riêng theo schema |
| Nghĩ NFC loại bỏ dấu | Thay đổi dữ liệu ngoài ý muốn | NFC chỉ chuẩn hóa biểu diễn Unicode |
| Xóa `\p{M}` trên bản gốc | Mất nghĩa và collision | Giữ bản gốc, search key phụ nếu cần |
| Bỏ dấu được xem là transliteration toàn cầu | Không xử lý hết `Đ/ß/ł` và nhiều hệ chữ | Có chính sách chuyển tự theo ngôn ngữ |
| Không truyền locale | Kết quả phụ thuộc máy chủ | Truyền `Locale` tường minh |
| Dùng Collator.PRIMARY làm uniqueness trong TreeSet | Gộp mất mục khác nhau | Dùng ID/tie-breaker phù hợp |
| Persist CollationKey làm identifier | Có thể không ổn định qua provider | Tái tạo key theo phiên bản quy tắc |
| Dùng chung Collator mutable đa luồng | Trạng thái có thể thay đổi giữa request | Tạo instance theo tác vụ hoặc đồng bộ |

## 15. Checklist kiểm thử và bài tập

### Checklist

1. Kiểm thử `Java/java` với `String.equals` và `equalsIgnoreCase`.
2. Kiểm thử `cafe/café` với `fr-FR` ở PRIMARY, SECONDARY, TERTIARY.
3. Kiểm thử `I/ı` và `I/i` với `tr-TR`, so với `equalsIgnoreCase`.
4. Kiểm thử `Straße/Strasse` với `de-DE`.
5. Kiểm thử Unicode dựng sẵn/phân rã qua NFC.
6. Kiểm thử `ma/má/mã` để bảo đảm giữ các mục khác nhau trong dữ liệu nguồn.
7. Kiểm thử `TreeSet`/`TreeMap` khi comparator trả 0 cho hai chuỗi khác nhau.
8. Kiểm thử các CollationKey được tạo bằng **cùng cấu hình**.
9. Kiểm thử phiên bản Java/provider thực tế khi kết quả thứ tự phải tái lập.
10. Kiểm thử đa luồng nếu dùng cache các collator có thể thay đổi trạng thái.

### Bài tập

1. Với `cafe` và `café`, giải thích tại sao `equalsIgnoreCase` trả false nhưng `Collator(fr-FR, PRIMARY)` có thể xem tương đương.
2. Với `tr-TR`, in lowercasing của `I` và uppercasing của `i`. Giải thích quy tắc dotted/dotless I.
3. So sánh `Straße` và `Strasse` bằng `equals`, `equalsIgnoreCase` và `Collator` tiếng Đức ở PRIMARY. Vì sao không được sửa bản gốc theo comparator?
4. Tạo `"caf\u00E9"` và `"cafe\u0301"`. Kiểm tra trước/sau `Normalizer.Form.NFC`.
5. Tạo `TreeSet<String>` với Collator PRIMARY, thêm `cafe` và `café`. Giải thích tại sao số lượng phần tử có thể bằng 1.
6. Tìm cách sắp xếp danh sách tên vẫn giữ từng bản ghi bằng ID, dù có các tên tương đương collation.
7. Thiết kế tìm kiếm không dấu cho `Ma/Má/Mã` với ranking nhưng không gộp ID.
8. Phân biệt `Collator.setStrength` với `setDecomposition`.
9. Tại sao không nên dùng `CollationKey.toByteArray()` làm một dạng mã định danh bền vững?
10. Với một ứng dụng đa ngôn ngữ, xác định nơi nào cần so sánh **exact**, nơi nào cần **locale-aware**, và nơi nào cho phép **accent-insensitive**.

**Ghi nhớ:** hoa–thường, dấu và quy tắc sắp xếp thuộc **nhiều lớp khác nhau**. `String.equals`/`equalsIgnoreCase` không có chính sách locale; `Collator` so sánh theo locale với các mức PRIMARY/SECONDARY/TERTIARY/IDENTICAL; `Normalizer` xử lý tương đương Unicode nhưng **không** xóa dấu. Hãy chọn API theo mục tiêu, bảo toàn nội dung gốc, truyền locale rõ và không đánh đồng “tương đương khi tìm kiếm” với “cùng một định danh”.

### Tài liệu tham khảo

- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) — so sánh theo locale, strength và decomposition.
- [Java SE 17 — CollationKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html) — hiệu quả khi so sánh nhiều lần và quy tắc dùng key.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) — equals, equalsIgnoreCase, compareTo, case conversion.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) — Unicode NFC/NFD/NFKC/NFKD.
- [Unicode Technical Standard #10](https://www.unicode.org/reports/tr10/) — Unicode Collation Algorithm.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/) — Unicode Normalization Forms.