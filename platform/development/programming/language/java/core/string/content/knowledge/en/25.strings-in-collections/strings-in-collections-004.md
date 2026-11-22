# Sắp xếp List<String> theo thứ tự tự nhiên hoặc Comparator trong Java

## Mục tiêu bài học

Khi có danh sách chuỗi `List<String>`, bạn thường muốn hiển thị từ A đến Z, từ Z đến A, không phân biệt chữ hoa/chữ thường, theo độ dài hoặc theo quy tắc ngôn ngữ. Java cung cấp thứ tự **tự nhiên** của `String` và cơ chế `Comparator` để định nghĩa thứ tự tùy chỉnh.

Sau bài này, bạn có thể:

- Dùng `List.sort(null)`, `Collections.sort(list)` hoặc `list.sort(Comparator.naturalOrder())` để sắp xếp tăng dần theo thứ tự tự nhiên.
- Giải thích cách `String.compareTo` so sánh thứ tự từ điển theo đơn vị UTF-16 và vì sao kết quả không đồng nghĩa với thứ tự bảng chữ cái tiếng Việt.
- Viết `Comparator` cho thứ tự giảm dần, độ dài, nhiều tiêu chí và so sánh không phân biệt hoa thường.
- Phân biệt sắp xếp **trực tiếp trên list** với tạo **list mới** qua Stream.
- Xử lý phần tử `null`, list không hỗ trợ chỉnh sửa, yêu cầu sắp xếp ổn định và lưu ý khi dùng `Collator`.

## 1. Sắp xếp tự nhiên là gì?

`String` cài đặt `Comparable<String>`. Vì thế, mỗi chuỗi có thể so sánh với chuỗi khác qua:

~~~java
int result = first.compareTo(second);
~~~

Theo quy ước của `Comparable`:

- `result < 0`: `first` đứng trước `second`.
- `result == 0`: hai chuỗi có thứ tự bằng nhau theo phép so sánh đó.
- `result > 0`: `first` đứng sau `second`.

`String.compareTo` xét các đơn vị mã **UTF-16** theo thứ tự từ trái sang phải, sử dụng giá trị số của các `char` khác nhau đầu tiên; nếu mọi code unit đã xét bằng nhau nhưng một chuỗi ngắn hơn, chuỗi ngắn hơn đứng trước. Vì vậy, chữ hoa Latin `A` có mã nhỏ hơn chữ thường `a`: thứ tự tự nhiên **phân biệt chữ hoa/chữ thường**. Với ký tự có dấu hoặc các ký tự ngoài ASCII, kết quả là trật tự theo UTF-16, không mặc định là thứ tự từ điển của ngôn ngữ tự nhiên.

Ví dụ:

~~~java
System.out.println("Apple".compareTo("apple") < 0); // true
System.out.println("app".compareTo("apple") < 0);   // true
System.out.println("cat".compareTo("car") > 0);     // true
~~~

**Ghi nhớ:** “natural order” của `String` là thứ tự được định nghĩa bởi `String.compareTo`. Nó không tự loại dấu, không bỏ qua chữ hoa/chữ thường và không đọc quy tắc sắp xếp tiếng Việt hoặc tiếng Nhật.

## 2. Sắp xếp trực tiếp List<String>

Ba cách phổ biến dưới đây có cùng ý nghĩa sắp xếp tăng dần theo thứ tự tự nhiên khi list không có `null`:

~~~java
Collections.sort(list);
list.sort(null);
list.sort(Comparator.naturalOrder());
~~~

- `Collections.sort(list)` là API tiện ích quen thuộc; về bản chất ủy quyền cho việc sắp xếp list.
- `list.sort(null)` dùng thứ tự tự nhiên của phần tử.
- `list.sort(Comparator.naturalOrder())` biểu đạt rõ rằng comparator là thứ tự tự nhiên.

Cả ba cách **thay đổi thứ tự phần tử của chính list**. Chúng không tạo `List` mới và yêu cầu list có hỗ trợ thao tác `set`/sắp xếp vị trí. Không phải mọi triển khai `List` đều cho phép điều này.

### Ví dụ Java 17+ chạy độc lập

Lưu vào `NaturalSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class NaturalSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("banana", "Apple", "apple", "Banana", "Zebra", "áo"));

        words.sort(Comparator.naturalOrder());
        System.out.println(words);

        words.sort(Comparator.reverseOrder());
        System.out.println(words);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NaturalSortDemo.java
java NaturalSortDemo
~~~

Kết quả:

~~~text
[Apple, Banana, Zebra, apple, banana, áo]
[áo, banana, apple, Zebra, Banana, Apple]
~~~

Lý do: `A`, `B`, `Z` là các code unit Latin in hoa đứng trước `a`, `b`, còn chữ `á` (`U+00E1`) đứng sau `b` trong phép so sánh tự nhiên ở ví dụ này. `Comparator.reverseOrder()` đảo thứ tự tự nhiên. Với dữ liệu mang ý nghĩa ngôn ngữ, hãy xem phần `Collator` bên dưới.

**Lưu ý:** `List.of("a", "b")` trả về list không chỉnh sửa được. Vì thế, ví dụ trên phải bọc trong `new ArrayList<>(...)` trước khi gọi `sort`. Nếu sort trực tiếp `List.of(...)`, thao tác có thể ném `UnsupportedOperationException`.

## 3. Comparator hoạt động như thế nào?

`Comparator<String>` mô tả quy tắc so sánh hai chuỗi:

~~~java
Comparator<String> byLength = (left, right) ->
        Integer.compare(left.length(), right.length());
~~~

Giá trị trả về là âm, không hoặc dương với ý nghĩa tương tự `compareTo`. Trong Java hiện đại, bạn thường không cần viết lambda so sánh độ dài bằng tay:

~~~java
Comparator<String> byLength = Comparator.comparingInt(String::length);
~~~

`Comparator.comparingInt` đọc khóa kiểu `int` từ mỗi phần tử; ở đây khóa là `length()`. Comparator có thể được truyền cho `List.sort`, `Stream.sorted`, `Collections.sort` hoặc các API khác có nhận thứ tự so sánh.

**Không nên viết** `left.length() - right.length()` làm kết quả so sánh khi khóa có thể là số nguyên lớn tùy ý, vì phép trừ có thể tràn số. Dùng `Integer.compare` hoặc `comparingInt` giúp tránh lỗi này. Với `String.length()` thực tế không âm, `comparingInt` vẫn rõ ý định hơn.

### Sắp xếp theo độ dài, rồi theo chữ cái

Nếu chỉ dùng độ dài, những chuỗi bằng độ dài sẽ được coi là ngang nhau. `thenComparing` thêm tiêu chí phụ để kết quả dễ dự đoán:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class LengthSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("pear", "fig", "apple", "kiwi", "plum", "fig"));

        Comparator<String> lengthThenNatural =
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder());

        words.sort(lengthThenNatural);
        System.out.println(words);

        words.sort(Comparator.comparingInt(String::length)
                .reversed()
                .thenComparing(Comparator.naturalOrder()));
        System.out.println(words);
    }
}
~~~

Lưu `LengthSortDemo.java` rồi chạy:

~~~bash
javac -encoding UTF-8 LengthSortDemo.java
java LengthSortDemo
~~~

Kết quả:

~~~text
[fig, fig, kiwi, pear, plum, apple]
[apple, kiwi, pear, plum, fig, fig]
~~~

Giải thích:

1. Lần sort đầu: độ dài tăng dần, nếu bằng nhau thì so sánh tự nhiên. `fig` (3 ký tự) trước các từ 4 ký tự; `apple` (5 ký tự) cuối.
2. Lần sort sau: độ dài giảm dần; khi độ dài bằng nhau thì vẫn so sánh tự nhiên tăng dần, bởi `reversed()` được đặt **trước** `thenComparing(...)`.

Thứ tự gọi rất quan trọng:

~~~java
Comparator<String> a = Comparator
        .comparingInt(String::length)
        .reversed()
        .thenComparing(Comparator.naturalOrder());

// Khác với comparator dưới đây:
Comparator<String> b = Comparator
        .comparingInt(String::length)
        .thenComparing(Comparator.naturalOrder())
        .reversed();
~~~

Ở `a`, chỉ tiêu chí độ dài bị đảo rồi thêm tiêu chí phụ tăng dần; ở `b`, **toàn bộ comparator ghép** bị đảo, bao gồm cả tiêu chí phụ. Chọn cách viết dựa vào yêu cầu nghiệp vụ.

## 4. Sắp xếp List không phân biệt chữ hoa/thường

`String.CASE_INSENSITIVE_ORDER` dùng quy tắc so sánh không phân biệt hoa/thường của `String`:

~~~java
List<String> words = new ArrayList<>(
        List.of("apple", "Banana", "banana", "Apple", "pear"));
words.sort(String.CASE_INSENSITIVE_ORDER);
System.out.println(words); // [apple, Apple, Banana, banana, pear]
~~~

`List.sort` **ổn định**: khi comparator trả `0` cho `"apple"` và `"Apple"`, thứ tự giữa chúng vẫn giữ như lúc đầu. List không loại phần tử dù comparator coi chúng ngang nhau.

Khi cần thứ tự xác định giữa những biến thể cùng kiểu chữ, thêm tiêu chí phụ:

~~~java
words.sort(String.CASE_INSENSITIVE_ORDER
        .thenComparing(Comparator.naturalOrder()));
System.out.println(words); // [Apple, apple, Banana, banana, pear]
~~~

`CASE_INSENSITIVE_ORDER` không phải bộ sắp xếp ngôn ngữ học cho mọi locale. Và nếu dùng comparator này trong `TreeMap` hoặc `TreeSet`, kết quả `compare == 0` có thể **gộp các khóa khác nhau theo `equals`**. Bài tiếp theo về mối quan hệ Comparator/equals phân tích chính xác hành vi đó.

## 5. Sắp xếp String theo ngôn ngữ: Collator

Với giao diện hướng tới người đọc ở một ngôn ngữ cụ thể, thứ tự tự nhiên của `String` hoặc `CASE_INSENSITIVE_ORDER` có thể không phù hợp. Chẳng hạn khi sắp xếp danh sách từ, tên người hoặc nhãn hiển thị tiếng Việt, thứ tự chữ có dấu và quy tắc so sánh có thể khác với thứ tự mã UTF-16.

`java.text.Collator` là bộ so sánh ký tự phụ thuộc `Locale`:

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class LocaleSortDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        Collator collator = Collator.getInstance(locale);

        List<String> words = new ArrayList<>(
                List.of("áo", "An", "ăn", "anh", "Ánh", "ao"));
        words.sort(collator);

        System.out.println(words);
    }
}
~~~

Lưu `LocaleSortDemo.java`; chạy `javac -encoding UTF-8 LocaleSortDemo.java` và `java LocaleSortDemo`. Mảng in ra được sắp xếp theo **quy tắc collation mà JDK/provider đang cung cấp cho `vi-VN`**. Thứ tự cụ thể có thể khác giữa phiên bản JDK hoặc dữ liệu locale, nên không cố ghi cứng một stdout có dấu cho ví dụ này. Hãy chạy và xác minh trên runtime mục tiêu của ứng dụng.

### Độ mạnh so sánh và tính nhất quán

`Collator` có các mức `PRIMARY`, `SECONDARY`, `TERTIARY` để phân biệt những đặc điểm ký tự khác nhau (chẳng hạn cơ sở chữ cái, dấu phụ, cách viết hoa), tùy dữ liệu collation của locale. Ví dụ:

~~~java
collator.setStrength(Collator.PRIMARY);
words.sort(collator);
~~~

Ở một số locale/cặp chuỗi, mức `PRIMARY` có thể coi nhiều biến thể là ngang nhau. Nên xác định chính sách sản phẩm về dấu và chữ hoa thay vì nghĩ `PRIMARY` luôn tương đương với “bỏ tất cả dấu”. Với nội dung quốc tế hóa, cần kiểm thử các cặp từ thực tế.

`Collator` có trạng thái cấu hình và không nên chỉnh cùng một đối tượng đang được dùng đồng thời mà không đồng bộ. Nếu muốn bảo đảm thứ tự hoàn toàn xác định khi hai chuỗi bằng nhau theo collation, bạn có thể bổ sung tiêu chí phụ tự nhiên:

~~~java
Comparator<String> localeOrder = (left, right) -> collator.compare(left, right);
words.sort(localeOrder.thenComparing(Comparator.naturalOrder()));
~~~

Lưu ý: tiêu chí phụ làm rõ cách xử lý trường hợp comparator collation trả về `0`; nó không thay thế bản thân quy tắc ngôn ngữ. Khi kết quả được lưu cố định, truyền qua nhiều hệ thống hoặc dùng làm khóa index, còn cần quản lý phiên bản/dữ liệu collation để tránh thay đổi thứ tự giữa các môi trường.

## 6. Null trong danh sách và đối tượng không chỉnh sửa được

`Comparator.naturalOrder()` và `String.compareTo` không tự hỗ trợ `null`. Khi list có phần tử `null`, sort theo tự nhiên có thể ném `NullPointerException`. Nếu quy tắc dữ liệu cho phép giá trị thiếu, hãy chọn nơi đặt nó:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                Arrays.asList("pear", null, "apple"));

        words.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println(words);

        words.sort(Comparator.nullsFirst(Comparator.naturalOrder()));
        System.out.println(words);
    }
}
~~~

Lưu `NullSortDemo.java`, biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NullSortDemo.java
java NullSortDemo
~~~

Kết quả:

~~~text
[apple, pear, null]
[null, apple, pear]
~~~

`Comparator.nullsLast(inner)` đặt `null` sau mọi chuỗi khác; `nullsFirst(inner)` đặt lên đầu. Comparator bên trong vẫn quyết định thứ tự của các chuỗi khác `null`.

Ngoài ra, nên phân biệt:

| Khởi tạo hoặc nguồn | Có thể sort trực tiếp? | Ghi chú |
| --- | --- | --- |
| `new ArrayList<>(...)` | Có | Có thể thay đổi thứ tự phần tử |
| `Arrays.asList(...)` | Thường có | Kích thước cố định nhưng hỗ trợ thay phần tử theo vị trí qua `set` |
| `List.of(...)` | Không | List không chỉnh sửa được; gọi `sort` ném `UnsupportedOperationException` |
| `stream.toList()` (Java 16+) | Không | List trả về không chỉnh sửa được |
| `Collections.unmodifiableList(...)` | Không | View chặn thao tác thay đổi |

Khi chưa biết list nguồn có thể chỉnh sửa hay không, **tạo bản sao** trước:

~~~java
List<String> sorted = new ArrayList<>(source);
sorted.sort(Comparator.naturalOrder());
~~~

Cách này còn giữ nguyên thứ tự của `source`, giúp tránh gây tác dụng phụ lên dữ liệu ở nơi khác. Nếu nguồn có thể chứa `null`, hãy dùng một comparator có `nullsFirst`/`nullsLast` như trên.

## 7. Tạo danh sách đã sắp xếp mà không làm đổi list gốc

`List.sort` thay đổi trực tiếp dữ liệu nguồn. Nếu chỉ muốn tính một kết quả hiển thị mới, hãy tạo bản sao hoặc dùng Stream:

~~~java
import java.util.Comparator;
import java.util.List;

public class StreamSortedDemo {
    public static void main(String[] args) {
        List<String> original = List.of("pear", "apple", "banana");

        List<String> sorted = original.stream()
                .sorted(Comparator.naturalOrder())
                .toList();

        System.out.println(original);
        System.out.println(sorted);
    }
}
~~~

Lưu `StreamSortedDemo.java` và chạy `javac -encoding UTF-8 StreamSortedDemo.java` rồi `java StreamSortedDemo`:

~~~text
[pear, apple, banana]
[apple, banana, pear]
~~~

`Stream.sorted` là phép trung gian, trả về một stream mới có thứ tự đã mô tả. `toList()` (Java 16+) là thao tác kết thúc tạo list kết quả và list ấy **không chỉnh sửa được**. `original` vẫn giữ nguyên.

So sánh nhanh:

- `list.sort(comparator)`: sắp xếp trực tiếp một list có thể chỉnh sửa; phương thức trả về `void`.
- `Collections.sort(list, comparator)`: cũng thay đổi list trực tiếp.
- `list.stream().sorted(comparator).toList()`: tạo list kết quả, không thay đổi nguồn, kết quả không chỉnh sửa được.
- `new ArrayList<>(list)` rồi `sort`: tạo list độc lập **và** có thể tiếp tục chỉnh sửa sau khi sort.

Hãy chọn dựa trên yêu cầu ownership/mutability của danh sách, không chỉ vì cú pháp nào ngắn.

## 8. Comparator đúng nghĩa cần tuân thủ các quy tắc nào?

Comparator nên có thứ tự nhất quán:

1. **Phản đối xứng về dấu:** dấu của `compare(a, b)` phải đối ngược dấu của `compare(b, a)`.
2. **Bắc cầu:** nếu `a` đứng trước `b` và `b` đứng trước `c` thì `a` phải đứng trước `c`.
3. **Nhất quán ở trường hợp bằng nhau:** nếu `compare(a, b) == 0`, việc so sánh `a` và `b` với một giá trị `c` phải cho quan hệ tương thích.
4. Tránh comparator có trạng thái thay đổi hoặc phụ thuộc thời điểm/ngẫu nhiên trong lúc sort.

Comparator không tuân thủ contract có thể tạo thứ tự khó đoán, và một số thuật toán sort có thể ném `IllegalArgumentException` khi phát hiện quan hệ so sánh vi phạm contract.

**Phân biệt `equals` với `compare == 0`:** `String.CASE_INSENSITIVE_ORDER.compare("Apple", "apple") == 0`, nhưng `"Apple".equals("apple")` là `false`. Đối với `List.sort`, hai phần tử vẫn được giữ lại; danh sách không tự xóa bản sao theo comparator. Nhưng nếu đem comparator đó vào `TreeSet` hoặc `TreeMap`, kết quả `compare == 0` có thể làm hai key được coi là cùng một key xét theo tập/bản đồ có thứ tự. Khi thiết kế comparator cho các collection đó, hãy cân nhắc độ nhất quán với `equals` và chính sách khóa nghiệp vụ.

### Tính ổn định và hiệu năng

`List.sort` yêu cầu sắp xếp **ổn định**: khi comparator xem hai phần tử bằng nhau, thứ tự tương đối ban đầu được giữ. Chi phí so sánh và số lần so sánh phụ thuộc độ dài danh sách, phân bố dữ liệu và các thao tác của comparator. Sắp xếp nói chung thường được phân tích theo mức `O(n log n)` phép so sánh cho trường hợp điển hình, nhưng việc so sánh chuỗi có thể còn phải duyệt nhiều ký tự để tìm điểm khác nhau.

Với dữ liệu lớn, tránh làm phép biến đổi tốn kém (ví dụ chuẩn hóa nhiều lần hoặc đọc dữ liệu ngoài) trong mỗi lời gọi comparator. Có thể tính khóa trước và sắp xếp theo khóa đã chuẩn bị nếu chi phí đó đáng kể. Không nên tối ưu sớm khi danh sách nhỏ và comparator đã dễ hiểu.

## 9. Các lỗi thường gặp

**Lỗi 1 — Tưởng tự nhiên tức là A–Z của tiếng Việt.** `compareTo` dựa trên UTF-16, không có ý thức về bộ chữ cái/ngôn ngữ. Dùng `Collator` với `Locale` thích hợp cho danh sách hiển thị theo quy tắc ngôn ngữ, rồi kiểm thử trên JDK thực tế.

**Lỗi 2 — Gọi sort trên List.of.** `List.of` không cho sửa nội dung. Tạo `new ArrayList<>(...)` hoặc dùng `stream().sorted(...).toList()`.

**Lỗi 3 — Có null nhưng dùng naturalOrder.** Nếu dữ liệu cho phép `null`, phải quyết định đặt null đầu/cuối bằng `Comparator.nullsFirst` hoặc `nullsLast`, hoặc loại bỏ trước khi sort nếu nghiệp vụ cho phép.

**Lỗi 4 — Nhầm thứ tự tự nhiên và không phân biệt hoa thường.** `Comparator.naturalOrder()` phân biệt `"Apple"` và `"apple"`; `String.CASE_INSENSITIVE_ORDER` thì có thể coi chúng bằng nhau. Khi cần sắp xếp có thứ tự phụ xác định, dùng `thenComparing(Comparator.naturalOrder())`.

**Lỗi 5 — Đặt reversed() sai vị trí.** `comparingInt(...).reversed().thenComparing(...)` đảo tiêu chí chính, còn `comparingInt(...).thenComparing(...).reversed()` đảo toàn bộ thứ tự đã ghép.

**Lỗi 6 — Dùng toLowerCase() không nêu rõ locale để tạo sort key.** Quy tắc đổi chữ hoa/thường có thể thay đổi theo locale; biến đổi có thể làm tăng số ký tự, và khóa đã đổi chữ không nhất thiết phản ánh collation đúng. Nếu mục tiêu là so sánh không phân biệt hoa thường đơn giản, dùng `CASE_INSENSITIVE_ORDER`; nếu theo ngôn ngữ, dùng `Collator` với locale cụ thể.

**Lỗi 7 — Dùng phép trừ để viết Comparator số.** Thay `a.length() - b.length()` bằng `Integer.compare(a.length(), b.length())` hoặc `Comparator.comparingInt(String::length)`.

**Lỗi 8 — Comparator không ổn định về mặt logic.** Tránh comparator trả giá trị khác nhau cho cùng cặp phần tử trong một lần sort; không dùng biến ngẫu nhiên hoặc dữ liệu có thể thay đổi bất chợt làm khóa so sánh.

**Lỗi 9 — Muốn giữ nguồn nhưng gọi List.sort.** `sort` thay đổi list đang có. Dùng bản sao hoặc `stream().sorted(...).toList()` khi cần kết quả độc lập.

**Lỗi 10 — Nhầm comparator với kiểm tra bằng nhau của Collection.** `List.sort` chỉ đổi thứ tự, không xóa phần tử trùng và không thay đổi `String.equals`. `TreeSet` và `TreeMap` thì dùng comparator để nhận diện khóa trùng theo trật tự so sánh.

## 10. Bài tập thực hành

Cho danh sách:

~~~java
List<String> names = new ArrayList<>(
        List.of("bob", "Amy", "ann", "BOB", "Joe"));
~~~

Hãy dự đoán kết quả sau ba phép sort độc lập, mỗi lần bắt đầu từ dữ liệu ban đầu (tạo list mới cho mỗi phép):

1. `names.sort(Comparator.naturalOrder())`.
2. `names.sort(String.CASE_INSENSITIVE_ORDER)`.
3. `names.sort(Comparator.comparingInt(String::length).thenComparing(Comparator.naturalOrder()))`.

Chương trình tự kiểm tra:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortPractice {
    public static void main(String[] args) {
        List<String> original = List.of("bob", "Amy", "ann", "BOB", "Joe");

        List<String> natural = new ArrayList<>(original);
        natural.sort(Comparator.naturalOrder());
        System.out.println("Natural: " + natural);

        List<String> insensitive = new ArrayList<>(original);
        insensitive.sort(String.CASE_INSENSITIVE_ORDER);
        System.out.println("Ignore case: " + insensitive);

        List<String> byLength = new ArrayList<>(original);
        byLength.sort(Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder()));
        System.out.println("Length: " + byLength);
    }
}
~~~

Lưu thành `SortPractice.java` và chạy:

~~~bash
javac -encoding UTF-8 SortPractice.java
java SortPractice
~~~

Kết quả:

~~~text
Natural: [Amy, BOB, Joe, ann, bob]
Ignore case: [Amy, ann, bob, BOB, Joe]
Length: [Amy, BOB, Joe, ann, bob]
~~~

Ở ví dụ thứ ba, mọi tên đều dài ba code unit UTF-16, nên tiêu chí độ dài không phân biệt được phần tử nào; tiêu chí phụ tự nhiên quyết định kết quả, giống lần sort đầu.

**Thử mở rộng:** thêm `"Bình"`, `"Binh"` và `"Ánh"` rồi so sánh kết quả với `Comparator.naturalOrder()`, `String.CASE_INSENSITIVE_ORDER` và `Collator.getInstance(Locale.forLanguageTag("vi-VN"))`. Không suy diễn thứ tự tiếng Việt từ UTF-16; hãy xem kết quả trên runtime bạn dùng.

## Checklist khi áp dụng

- Danh sách có được phép chỉnh sửa không? Nếu không, tạo bản sao hoặc dùng `Stream.sorted`.
- Muốn thứ tự theo mã UTF-16, không phân biệt hoa/thường, theo độ dài hay theo ngôn ngữ? Chọn comparator phù hợp.
- Có `null` không? Quy định xử lý `nullsFirst`/`nullsLast` hoặc loại bỏ có chủ đích.
- Có nhiều tiêu chí không? Dùng `comparingInt`, `thenComparing` và đặt `reversed()` đúng chỗ.
- Có phần tử bằng nhau theo comparator không? Xác định có cần tiêu chí phụ, đồng thời tận dụng tính ổn định của `List.sort`.
- Kết quả có ảnh hưởng tới `TreeSet`/`TreeMap` hoặc phải nhất quán trên nhiều JDK/locale không? Kiểm tra semantics của comparator, `equals` và collation trước khi dùng làm hợp đồng dữ liệu.

## Tài liệu tham khảo chính thức

- [Java SE 17 — List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))
- [Java SE 17 — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 — String.compareTo và CASE_INSENSITIVE_ORDER](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — Collections.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Java SE 17 — Stream.sorted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator))
