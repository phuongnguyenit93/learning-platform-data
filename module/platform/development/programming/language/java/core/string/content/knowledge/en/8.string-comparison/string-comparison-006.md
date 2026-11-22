# `String.compareToIgnoreCase()` và `String.CASE_INSENSITIVE_ORDER` trong Java

## 1. Bài toán: sắp xếp chuỗi mà không phân biệt chữ hoa/chữ thường

Khi sắp xếp từ khóa, tên lệnh hoặc danh sách văn bản, thứ tự mặc định của `String.compareTo()` có thể không phù hợp nếu chỉ muốn bỏ qua khác biệt giữa chữ hoa và chữ thường. Java cung cấp hai API bổ sung cho cùng quy tắc so sánh:

- `a.compareToIgnoreCase(b)`: **phương thức trên một `String`**, trả về số âm, 0 hoặc số dương theo thứ tự từ điển *không phân biệt hoa/thường*.
- `String.CASE_INSENSITIVE_ORDER`: **đối tượng `Comparator<String>` có sẵn**, áp dụng thứ tự tương đương `compareToIgnoreCase` cho hai chuỗi được truyền vào. Nó đặc biệt tiện khi một API yêu cầu `Comparator`, chẳng hạn `List.sort`, `Arrays.sort`, `TreeSet` và `TreeMap`.

Cả hai đều so sánh **giá trị văn bản**, không so địa chỉ tham chiếu. Cả hai đều **không phụ thuộc `Locale`**, không biến đổi nội dung đầu vào, và không phải bộ quy tắc sắp xếp ngôn ngữ tự nhiên. Phân biệt rất quan trọng: bỏ qua hoa/thường không đồng nghĩa với bỏ qua dấu tiếng Việt, chuẩn hóa Unicode hay sắp xếp đúng theo từ điển của một quốc gia.

Mục tiêu sau bài:
1. Biết dùng `compareToIgnoreCase` để so hai chuỗi và đọc đúng dấu của kết quả.
2. Biết truyền `CASE_INSENSITIVE_ORDER` cho thuật toán sắp xếp và tập hợp có thứ tự.
3. Hiểu tại sao `compare(...) == 0` có thể khác `String.equals(...)` và hệ quả với `TreeSet`/`TreeMap`.
4. Nhận biết giới hạn Unicode/`Locale`, cách xử lý `null` và cách chọn tie-breaker khi cần giữ các chuỗi khác nhau về chữ hoa/thường.

## 2. `compareToIgnoreCase(String str)`: cú pháp và giá trị trả về

Khai báo API (Java 17+):

```java
public int compareToIgnoreCase(String str)
```

Gọi trên chuỗi bên trái; tham số `str` là chuỗi bên phải. Quy tắc đọc:

| Giá trị trả về | Diễn giải |
| --- | --- |
| `< 0` | Chuỗi bên trái đứng **trước** chuỗi bên phải theo thứ tự bỏ qua hoa/thường |
| `== 0` | Hai chuỗi được coi là **ngang hàng** theo quy tắc so sánh này |
| `> 0` | Chuỗi bên trái đứng **sau** chuỗi bên phải theo quy tắc này |

Ví dụ biểu thức (đặt trong một phương thức, chẳng hạn `main`):

```java
System.out.println("Java".compareToIgnoreCase("jAVA") == 0); // true
System.out.println("alpha".compareToIgnoreCase("BETA") < 0);  // true
System.out.println("Zulu".compareToIgnoreCase("apple") > 0); // true
System.out.println("cat".compareToIgnoreCase("CAtS") < 0);   // true
System.out.println("ab".compareToIgnoreCase("aB") == 0);     // true
```

**Chỉ dựa vào dấu, không dựa vào trị tuyệt đối**: API bảo đảm kết quả âm/0/dương tương ứng thứ tự, không nên viết kiểm tra như `compareToIgnoreCase(b) == -1` để kết luận đứng trước. Dùng `< 0`, `== 0` hoặc `> 0`.

Thứ tự là **từ điển** (lexicographical): so lần lượt các code point sau khi áp dụng quy tắc bỏ qua hoa/thường; tại khác biệt đầu tiên, giá trị đã chuẩn hóa quyết định thứ tự. Nếu phần đầu tương đương nhưng một chuỗi còn phần tiếp theo, chuỗi ngắn hơn đứng trước. Đây là thứ tự có thể dùng để sắp xếp; nó không đánh giá từ vựng, ý nghĩa hay ngôn ngữ tự nhiên.

## 3. Java xác định “không phân biệt hoa/thường” như thế nào?

Theo hợp đồng `String.compareToIgnoreCase` của Java SE 17, so sánh bỏ qua hoa/thường theo phép biến đổi từng **Unicode code point** bằng:

```java
Character.toLowerCase(Character.toUpperCase(codePoint))
```

Biểu thức này là **minh họa cho phép chuẩn hóa từng code point**, không phải chương trình độc lập hay lời khuyên tự viết lại comparator. Java sử dụng định nghĩa API của chính nó; bạn nên dùng trực tiếp `compareToIgnoreCase` hoặc `CASE_INSENSITIVE_ORDER`.

Hệ quả:
- `"Java"` và `"jAVA"` được xếp ngang hàng, vì khác biệt chỉ ở hoa/thường theo quy tắc Java.
- Đây là phép so **không xét `Locale`**. Nó không biết yêu cầu sắp xếp đặc thù tiếng Việt, tiếng Thổ Nhĩ Kỳ hoặc một bộ quy tắc ngôn ngữ khác.
- Quy tắc này không phải phép *full Unicode case folding* có thể mở rộng một ký tự thành nhiều ký tự. Ví dụ chữ `ß` trong `"Straße"` không tự tương đương chuỗi hai chữ `"SS"` trong `"STRASSE"`.
- Nó cũng không tự chuẩn hóa biểu diễn Unicode như dạng tiền tổ hợp so với base character kèm dấu kết hợp; hai chuỗi nhìn giống nhau có thể gồm các code point khác nhau.
- So sánh không chỉnh sửa `String`; chỉ tính thứ tự từ nội dung hiện tại.

Ví dụ với những chữ Latin thường dùng không dấu thì hành vi rất dễ đoán, nhưng không nên suy từ đó rằng đây là bộ công cụ so sánh văn bản theo ngôn ngữ tự nhiên.

## 4. `String.CASE_INSENSITIVE_ORDER`: Comparator dùng lại cùng quy tắc

`String.CASE_INSENSITIVE_ORDER` là một trường `public static final Comparator<String>` có trong lớp `String`. Comparator này so sánh `a` và `b` theo thứ tự tương đương:

```java
a.compareToIgnoreCase(b)
```

Điểm khác nhau nằm ở **cách sử dụng**, không phải mục tiêu so sánh:

| Tiêu chí | `a.compareToIgnoreCase(b)` | `String.CASE_INSENSITIVE_ORDER.compare(a,b)` |
| --- | --- | --- |
| Loại API | Phương thức instance của `String` | Phương thức của một `Comparator<String>` |
| Đầu vào | Biến nhận `a` và một đối số `b` | Hai đối số `a` và `b` |
| Kết quả | Số âm/0/dương | Cùng quy tắc âm/0/dương |
| Dùng trực tiếp khi cần so hai giá trị | Rất thuận tiện | Hợp lệ, nhưng dài hơn |
| Dùng với `List.sort`, `TreeSet`, `TreeMap` | Cần bọc trong lambda/method reference | Truyền trực tiếp comparator có sẵn |
| Phụ thuộc `Locale` | Không | Không |

Ví dụ độc lập, lưu `CaseInsensitiveBasics.java`:

```java
import java.util.Comparator;

public class CaseInsensitiveBasics {
    public static void main(String[] args) {
        String left = "Java";
        String right = "jAVA";
        Comparator<String> order = String.CASE_INSENSITIVE_ORDER;

        System.out.println(left.equals(right));
        System.out.println(left.equalsIgnoreCase(right));
        System.out.println(left.compareTo(right) == 0);
        System.out.println(left.compareToIgnoreCase(right));
        System.out.println(order.compare(left, right));
        System.out.println(order.compare("alpha", "BETA") < 0);
        System.out.println(order.compare("Zulu", "apple") > 0);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 CaseInsensitiveBasics.java
java CaseInsensitiveBasics
```

```text
false
true
false
0
0
true
true
```

Hai chuỗi khác nhau về nội dung chính xác, nên `equals` và `compareTo(... ) == 0` đều `false`. Nhưng `equalsIgnoreCase` là `true`, `compareToIgnoreCase` và comparator đều coi chúng ngang hàng.

`CASE_INSENSITIVE_ORDER` là comparator có thể tái sử dụng; nó cũng hỗ trợ serialization theo tài liệu API. Tên `CASE_INSENSITIVE_ORDER` là một **giá trị comparator**, không phải phương thức `CASE_INSENSITIVE_ORDER()`.

## 5. Sắp xếp danh sách: `List.sort`, `Arrays.sort` và method reference

Dùng `CASE_INSENSITIVE_ORDER` khi muốn sắp xếp nhiều phần tử:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class IgnoreCaseSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                Arrays.asList("banana", "Apple", "cherry", "apple", "BANANA"));

        words.sort(String.CASE_INSENSITIVE_ORDER);
        System.out.println(words);

        String[] cities = {"zoo", "Beta", "alpha"};
        Arrays.sort(cities, String.CASE_INSENSITIVE_ORDER);
        System.out.println(Arrays.toString(cities));
    }
}
```

Lưu thành `IgnoreCaseSortDemo.java`, rồi chạy:

```bash
javac -encoding UTF-8 IgnoreCaseSortDemo.java
java IgnoreCaseSortDemo
```

```text
[Apple, apple, banana, BANANA, cherry]
[alpha, Beta, zoo]
```

`List.sort` và `Arrays.sort` với comparator đều thực hiện sắp xếp ổn định cho các phần tử thích hợp: nếu comparator trả `0`, thứ tự tương đối ban đầu được giữ. Vì vậy `Apple` nằm trước `apple` như dữ liệu đầu vào; `banana` nằm trước `BANANA`. Hai chuỗi vẫn tồn tại trong list/array vì sắp xếp **không khử phần tử**.

Có thể viết:

```java
words.sort((a, b) -> a.compareToIgnoreCase(b));
// Hoặc:
words.sort(String::compareToIgnoreCase);
```

Đây chỉ là **snippet thay thế lệnh sort** bên trong ví dụ có `words` ở trên. Khi không thêm quy tắc khác, dùng `String.CASE_INSENSITIVE_ORDER` thường dễ đọc và nói rõ ý đồ hơn.

Để có danh sách mới mà không thay đổi list gốc, có thể dùng `words.stream().sorted(String.CASE_INSENSITIVE_ORDER).toList()` (Java 16+), chú ý phần tử thuộc list trả về không thể thêm/xóa theo API `Stream.toList()`.

## 6. `equals`, `equalsIgnoreCase` và “bằng nhau theo Comparator” là các khái niệm khác nhau

Đặt `a = "API"` và `b = "api"`. Khi đó:
- `a.equals(b)` là `false`: `String.equals` yêu cầu chuỗi code unit bằng nhau chính xác.
- `a.equalsIgnoreCase(b)` là `true`: so bằng nhau theo quy tắc bỏ qua hoa/thường.
- `a.compareToIgnoreCase(b) == 0` là `true`.
- `String.CASE_INSENSITIVE_ORDER.compare(a,b) == 0` là `true`.

`Comparator.compare(a,b) == 0` không có nghĩa hai đối tượng là cùng một đối tượng (`a == b`) và cũng không nhất thiết tương đương theo `a.equals(b)`.

Trong thuật ngữ `Comparator`, nếu `compare(a,b) == 0` luôn đi đôi với `a.equals(b)` đối với các giá trị hợp lệ, thứ tự được gọi là *consistent with equals*. `CASE_INSENSITIVE_ORDER` **không nhất quán với `String.equals`** vì nó có thể coi hai chuỗi khác chính tả hoa/thường là cùng một phần tử xét theo thứ tự.

Điều này không làm comparator sai. Nó chỉ có hệ quả rất quan trọng với các collection được tổ chức bằng comparator.

## 7. `TreeSet` và `TreeMap`: comparator có thể quyết định tính duy nhất của khóa

`TreeSet` dựa vào thứ tự do comparator cung cấp để nhận diện giá trị đã có. Nếu `compare(newElement, existingElement) == 0`, phần tử mới **không được thêm** dù `newElement.equals(existingElement)` là `false`.

`TreeMap` cũng xác định các khóa tương đương theo comparator. Ghi giá trị cho một khóa khác kiểu chữ hoa/thường có thể **thay thế value** của khóa đã tồn tại, thay vì tạo entry thứ hai.

Lưu `CaseInsensitiveCollections.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CaseInsensitiveCollections {
    public static void main(String[] args) {
        Set<String> sorted = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        sorted.add("java");
        sorted.add("JAVA");
        sorted.add("Java");
        sorted.add("Go");
        sorted.add("go");

        Set<String> hashed = new HashSet<>();
        hashed.add("java");
        hashed.add("JAVA");
        hashed.add("Java");

        System.out.println(sorted);
        System.out.println(sorted.size());
        System.out.println(sorted.contains("jAvA"));
        System.out.println(hashed.size());

        TreeMap<String, Integer> quantities =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        quantities.put("API", 10);
        quantities.put("api", 20);
        System.out.println(quantities.size());
        System.out.println(quantities.get("Api"));
        System.out.println(quantities.firstKey());
    }
}
```

```bash
javac -encoding UTF-8 CaseInsensitiveCollections.java
java CaseInsensitiveCollections
```

```text
[Go, java]
2
true
3
1
20
API
```

Phân tích:
1. `TreeSet` chỉ giữ `"java"` đầu tiên và `"Go"` đầu tiên. Các biến thể hoa/thường tiếp theo có `compare == 0` nên không tăng kích thước. `contains("jAvA")` trả `true` vì comparator tìm được nhóm tương đương.
2. `HashSet` thông thường dùng `equals`/`hashCode` của `String`: ba cách viết `java`, `JAVA` và `Java` khác nhau nên kích thước là 3.
3. `TreeMap` có một entry cho hai cách viết `API`/`api`; put thứ hai thay value thành 20. Khóa gốc `"API"` được giữ, nên `firstKey()` là `API` trong chương trình này.
4. Không dùng `CASE_INSENSITIVE_ORDER` cho `TreeSet` nếu yêu cầu phải **giữ đồng thời** các giá trị chỉ khác chữ hoa/thường. Nếu muốn gộp tên khóa bất kể chữ hoa/thường, hành vi gộp này lại có thể chính là điều mong muốn.

**Cẩn thận với hợp đồng `Set`/`Map`:** do comparator không nhất quán với `equals`, việc sử dụng một `TreeSet`/`TreeMap` có thứ tự không phân biệt hoa/thường có thể khiến chúng hành xử khác `HashSet`/`HashMap` hoặc kết quả so sánh collection khác kỳ vọng. Hãy mô tả quy tắc tương đương của khóa trong tài liệu API, nhất là khi truyền collection sang mã không biết comparator đang sử dụng.

## 8. Muốn bỏ qua hoa/thường khi xếp thứ tự, nhưng vẫn giữ mọi chuỗi khác nhau

Bài toán thường gặp: hiển thị `"API"` gần `"api"` nhưng **không muốn chúng bị xem như cùng khóa** trong `TreeSet`. Có thể thêm tiêu chí phụ (*tie-breaker*) sử dụng `String.compareTo` khi tiêu chí đầu coi hai chuỗi là ngang nhau:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class TieBreakerDemo {
    public static void main(String[] args) {
        Comparator<String> order =
                String.CASE_INSENSITIVE_ORDER
                      .thenComparing(Comparator.naturalOrder());

        TreeSet<String> words = new TreeSet<>(order);
        words.add("api");
        words.add("API");
        words.add("Api");
        words.add("go");

        System.out.println(words);
        System.out.println(words.size());
        System.out.println(order.compare("API", "api") == 0);
        System.out.println(order.compare("API", "API") == 0);
    }
}
```

```bash
javac -encoding UTF-8 TieBreakerDemo.java
java TieBreakerDemo
```

```text
[API, Api, api, go]
4
false
true
```

Với `String` không `null`, comparator ghép này chỉ trả 0 khi các chuỗi bằng nhau theo `String.equals`: tiêu chí đầu nhóm theo thứ tự bỏ qua hoa/thường; tiêu chí phụ chỉ áp dụng khi tiêu chí đầu bằng nhau, giúp tách các giá trị khác chữ hoa/thường. Nhờ đó có thể giữ đủ các biến thể trong `TreeSet`.

Lưu ý: đây là **thứ tự hai tầng**, không phải một kiểu so sánh hoàn toàn không phân biệt hoa/thường. Người đọc thấy các biến thể đứng gần nhau, nhưng có thứ tự nội bộ do cách so sánh chính xác của Java quyết định.

## 9. Giới hạn Unicode và `Locale`

### 9.1. Không thay thế full Unicode case folding

Java xử lý hoa/thường trên từng Unicode code point theo quy tắc Java nêu ở trên. Nó không bảo đảm hai chuỗi sẽ được xem ngang hàng nếu phép chuyển đổi ngôn ngữ đòi hỏi **mở rộng thành nhiều code point**.

Ví dụ Java độc lập, lưu `UnicodeCaseDemo.java`:

```java
public class UnicodeCaseDemo {
    public static void main(String[] args) {
        String german = "Stra\u00DFe"; // Straße
        String upper = "STRASSE";

        System.out.println(german.equalsIgnoreCase(upper));
        System.out.println(german.compareToIgnoreCase(upper) == 0);
        System.out.println("I".equalsIgnoreCase("\u0131"));
        System.out.println("\u0130".equalsIgnoreCase("i"));
    }
}
```

```bash
javac -encoding UTF-8 UnicodeCaseDemo.java
java UnicodeCaseDemo
```

```text
false
false
true
true
```

Với hai chuỗi Đức, `ß` và dãy `SS` không được gộp qua phép so sánh từng code point này. Ngược lại, hai ví dụ có `I` không dấu chấm, `ı` (`U+0131`) và `İ` (`U+0130`) cho thấy quy tắc bỏ qua hoa/thường **không xét ngữ cảnh ngôn ngữ**: kết quả đúng theo Java có thể không đúng theo cách người dùng tiếng Thổ Nhĩ Kỳ mong đợi.

Không nên viết `s.toLowerCase()` rồi `compareTo()` như một “bản thay thế tương đương”: `toLowerCase()` mặc định phụ thuộc `Locale.getDefault()`, có thể đổi độ dài chuỗi và có thể cho thứ tự khác `compareToIgnoreCase`. `toLowerCase(Locale.ROOT)` giúp loại bỏ phụ thuộc default locale cho bước chuyển chữ, nhưng vẫn không biến thao tác so sánh thành bộ quy tắc sắp xếp ngôn ngữ hay chuẩn hóa Unicode đầy đủ.

### 9.2. So sánh theo ngôn ngữ bằng `Collator` khi yêu cầu

Khi người dùng cần xếp tên người, tên địa danh hoặc từ vựng theo quy tắc của một ngôn ngữ, Java cung cấp `java.text.Collator`. Nó là giải pháp được thiết kế cho so sánh có xét `Locale`:

```java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

public class LocaleSortExample {
    public static void main(String[] args) {
        String[] names = {"I", "i", "\u0130", "\u0131"};
        Collator collator = Collator.getInstance(
                Locale.forLanguageTag("tr-TR"));
        collator.setStrength(Collator.SECONDARY);
        Arrays.sort(names, collator);
        System.out.println(Arrays.toString(names));
    }
}
```

Lưu thành `LocaleSortExample.java`. Chạy với:

```bash
javac -encoding UTF-8 LocaleSortExample.java
java LocaleSortExample
```

Đây là **chương trình có thể biên dịch/chạy**, nhưng bài không cố định stdout: thứ tự hiển thị với `Collator` có thể chịu ảnh hưởng của dữ liệu so sánh theo vùng/phiên bản JDK. `Collator.SECONDARY` thường cho phép khác biệt dấu trọng âm có ý nghĩa trong khi bỏ qua khác biệt hoa/thường ở nhiều locale; quy tắc cụ thể phụ thuộc ngôn ngữ. Hãy thử nghiệm với locale, tập dữ liệu và phiên bản JDK thực tế của ứng dụng.

Để so sánh theo nhu cầu nghiệp vụ, cần quyết định thêm liệu dấu, ký tự kết hợp, khoảng trắng, ký tự đặc biệt và biến thể chính tả có được coi là ngang nhau hay không. Không có một comparator bỏ qua hoa/thường nào giải quyết tất cả những yêu cầu này.

## 10. `null`: phải chọn quy ước xử lý tường minh

`"abc".compareToIgnoreCase(null)` ném `NullPointerException`. `String.CASE_INSENSITIVE_ORDER.compare("abc", null)` cũng không cung cấp thứ tự cho `null`. Đừng trông chờ comparator mặc định tự đưa `null` lên đầu/cuối.

Khác biệt dễ bỏ sót: `"abc".equalsIgnoreCase(null)` trả `false`, vì đây là **phép kiểm tra bằng nhau**, không phải phép so thứ tự.

Khi một danh sách có thể chứa `null`, bọc comparator bằng `Comparator.nullsFirst` hoặc `Comparator.nullsLast`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullSafeSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                Arrays.asList("zulu", null, "Alpha", "beta"));

        Comparator<String> order =
                Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER);

        words.sort(order);
        System.out.println(words);
        System.out.println("abc".equalsIgnoreCase(null));
    }
}
```

```bash
javac -encoding UTF-8 NullSafeSortDemo.java
java NullSafeSortDemo
```

```text
[null, Alpha, beta, zulu]
false
```

`Comparator.nullsFirst` làm `null` đứng trước các chuỗi hợp lệ, `nullsLast` đưa nó về sau. Đối với hàm không cho phép `null` theo thiết kế, thường rõ ràng hơn nếu kiểm tra tham số ngay tại ranh giới API bằng `Objects.requireNonNull`.

## 11. Chọn API theo tình huống

| Nhu cầu | Chọn | Lý do |
| --- | --- | --- |
| So sánh thứ tự của đúng hai chuỗi, bỏ qua hoa/thường | `a.compareToIgnoreCase(b)` | Gọn, trả dấu thứ tự |
| Chỉ kiểm tra hai chuỗi có tương đương bỏ qua hoa/thường không | `a.equalsIgnoreCase(b)` | Diễn đạt ý định boolean trực tiếp; đối số `null` cho `false` |
| Sắp xếp list/array theo thứ tự bỏ qua hoa/thường | `String.CASE_INSENSITIVE_ORDER` | Truyền thẳng vào API nhận `Comparator<String>` |
| `TreeSet`/`TreeMap` cố ý gộp các biến thể hoa/thường | `String.CASE_INSENSITIVE_ORDER` | `compare == 0` định nghĩa cùng nhóm/khóa |
| Muốn nhóm các biến thể gần nhau nhưng giữ riêng từng cách viết | `CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` | Tiêu chí phụ tránh đồng nhất khóa khác nhau |
| Danh sách có `null` và cần quy định vị trí của nó | `Comparator.nullsFirst(...)` / `nullsLast(...)` | Tránh NPE, nói rõ chính sách |
| Sắp xếp theo ngôn ngữ của người dùng | `Collator.getInstance(locale)` | Quy tắc sắp xếp theo locale |
| So mã định danh giao thức hoặc khóa hệ thống với quy tắc riêng | Comparator/canonicalization được **định nghĩa theo đặc tả hệ thống** | Không mặc định rằng bỏ qua hoa/thường theo Java phù hợp cho mọi protocol |

Một ranh giới thiết kế khác: `String.CASE_INSENSITIVE_ORDER` dùng được với **`String`**. Nếu nguồn là `CharSequence` khác như `StringBuilder`, bạn phải chủ động quy định cách chuyển thành `String`, thời điểm chụp nội dung và việc dữ liệu mutable có được sửa trong lúc sắp xếp hay không. Không ép kiểu `CharSequence` sang `String` nếu đối tượng thực tế không phải `String`.

## 12. Lỗi phổ biến

1. **Nhầm `compareToIgnoreCase` trả `boolean`.** Nó trả `int`; dùng dấu âm/0/dương. Nếu chỉ hỏi bằng nhau, `equalsIgnoreCase` dễ đọc hơn.
2. **Kiểm tra `== -1` hoặc `== 1`.** API không hứa trả đúng ±1. Chỉ dùng `< 0`, `== 0`, `> 0`.
3. **Cho rằng `compare == 0` đồng nghĩa `equals == true`.** `"API"` và `"api"` là phản ví dụ rõ ràng.
4. **Dùng comparator này trong `TreeSet` rồi ngạc nhiên vì mất biến thể chữ hoa/thường.** Tập hợp có thứ tự xác định tính duy nhất bằng comparator; chọn tie-breaker nếu muốn giữ biến thể.
5. **Dùng `CASE_INSENSITIVE_ORDER` để sắp tên tiếng Việt theo từ điển.** Đây là quy tắc bỏ qua hoa/thường, không phải phép so `Locale`.
6. **Chuyển tất cả chuỗi về chữ thường trước khi so mà không chọn `Locale`.** `String.toLowerCase()` mặc định phụ thuộc locale và có thể làm biến đổi độ dài, ý nghĩa hoặc nội dung dữ liệu.
7. **Cho rằng mọi Unicode case equivalence đã được xử lý.** Phép biến đổi từng code point không phải full case folding có mở rộng hay chuẩn hóa Unicode.
8. **Đưa `null` vào sort mà không có chính sách.** Dùng `nullsFirst`/`nullsLast` hoặc loại bỏ/kiểm tra null rõ ràng.
9. **Sắp xếp rồi mong danh sách tự loại các chuỗi bằng nhau theo comparator.** `List.sort` chỉ sắp thứ tự; `TreeSet` mới có hành vi gộp phần tử bằng comparator.
10. **Tạo comparator tự viết không nhất quán hoặc phụ thuộc dữ liệu mutable.** Comparator phải tuân thủ tính phản đối xứng, bắc cầu và cho kết quả ổn định khi dùng trong cấu trúc dữ liệu có thứ tự.

## 13. Tự kiểm tra

Với chương trình dưới đây, hãy đoán kết quả trước khi chạy:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;

public class CompareQuiz {
    public static void main(String[] args) {
        System.out.println("Code".compareToIgnoreCase("cODE"));
        System.out.println("Code".equals("cODE"));

        String[] values = {"b", "A", "a"};
        Arrays.sort(values, String.CASE_INSENSITIVE_ORDER);
        System.out.println(Arrays.toString(values));

        Set<String> set = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        set.add("Key");
        set.add("KEY");
        System.out.println(set.size());
    }
}
```

Lưu thành `CompareQuiz.java`, chạy:

```bash
javac -encoding UTF-8 CompareQuiz.java
java CompareQuiz
```

```text
0
false
[A, a, b]
1
```

Giải thích: hai biến thể `Code/cODE` so thứ tự bằng nhau nhưng không bằng nhau chính xác; mảng được sắp ổn định với `A` và `a` đứng gần nhau; `TreeSet` chỉ giữ một khóa khi comparator cho kết quả 0.

**Ghi nhớ:** `compareToIgnoreCase` và `String.CASE_INSENSITIVE_ORDER` dùng **cùng quy tắc thứ tự bỏ qua chữ hoa/thường**, nhưng cách đưa vào API khác nhau. Comparator ảnh hưởng trực tiếp đến cách `TreeSet`/`TreeMap` nhận diện khóa, vì vậy luôn quyết định rõ có muốn gộp các biến thể hoa/thường hay không và liệu ngôn ngữ/Unicode của bài toán có cần xử lý riêng.

## Tài liệu Java SE 17 chính thức

- [`String.compareToIgnoreCase`, `equalsIgnoreCase` và `String.CASE_INSENSITIVE_ORDER` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Comparator`, `thenComparing`, `nullsFirst`, `nullsLast` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [`TreeSet` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [`TreeMap` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
- [`Collator` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
