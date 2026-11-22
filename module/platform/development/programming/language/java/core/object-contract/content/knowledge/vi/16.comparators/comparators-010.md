# `Comparator.equals()` khác với `compare() == 0` cho hai phần tử

## 1. Hai lời gọi có ý nghĩa khác nhau

Trong Java, `Comparator<T>` biểu diễn **một quy tắc so sánh và sắp xếp các đối tượng kiểu `T`**. Interface này khai báo phương thức cốt lõi `int compare(T a, T b)` và có phương thức `boolean equals(Object obj)` kế thừa từ `Object`; một lớp comparator **có thể** ghi đè `equals` để định nghĩa khi nào hai **comparator** tương đương.

Điểm quan trọng là **đối tượng đang được so sánh khác nhau**:

- `comparator.compare(a, b) == 0`: hỏi **hai phần tử `a` và `b` có ngang nhau theo thứ tự mà comparator định nghĩa hay không**. Kết quả không trực tiếp nói rằng `a.equals(b)` là `true`.
- `comparator.equals(otherComparator)`: hỏi **đối tượng comparator hiện tại có bằng một đối tượng comparator khác hay không**. Đây là một lời gọi `equals(Object)` trên chính comparator, không phải phép kiểm tra bằng nhau của hai phần tử dữ liệu.

Ví dụ sơ lược:

~~~java
Comparator<String> comparator = String.CASE_INSENSITIVE_ORDER;
boolean samePosition = comparator.compare("Java", "JAVA") == 0;
boolean sameValue = "Java".equals("JAVA");
~~~

`samePosition` là `true` vì comparator không phân biệt chữ hoa/thường; `sameValue` là `false` vì `String.equals` có phân biệt chữ hoa/thường. Trong khi đó, `comparator.equals(anotherComparator)` là câu hỏi về **hai chiến lược sắp xếp**.

**Không đánh đồng ba biểu thức**:

| Biểu thức | Chủ thể được so sánh | Ý nghĩa |
| --- | --- | --- |
| `a == b` | Hai tham chiếu phần tử | Có cùng đối tượng hay không |
| `a.equals(b)` | Hai phần tử | Có bằng nhau theo hợp đồng `equals` của phần tử hay không |
| `c.compare(a, b) == 0` | Hai phần tử qua bộ so sánh `c` | Có tương đương trong **thứ tự do `c` định nghĩa** hay không |
| `c.equals(d)` | Hai comparator `c` và `d` | Có được comparator coi là hai bộ so sánh bằng nhau hay không |

## 2. Giá trị âm, bằng 0, dương của `compare(a, b)`

`compare(a,b)` trả số âm nếu a đứng trước b, số dương nếu đứng sau, và `0` nếu hai phần tử thuộc cùng nhóm tương đương theo **quy tắc đang chọn**. Không bắt buộc trả chính xác `-1` hoặc `1`, và cũng không có nghĩa `a.equals(b)` phải là `true` khi kết quả so sánh bằng 0.

~~~text
a ~ b  ⇔  comparator.compare(a, b) == 0
~~~

Ví dụ, một comparator theo độ dài sẽ trả `0` cho `"cat"` và `"dog"`, dù `String.equals` trả `false`. Hợp đồng vẫn yêu cầu đối dấu khi đảo đối số, tính bắc cầu và quan hệ nhất quán với mọi phần tử thứ ba; chi tiết toán học nằm ở bài về hợp đồng dấu và nhóm 0.

Điểm đặc biệt cần nhớ trong **bài này** là `comparatorA.equals(comparatorB)` hoàn toàn không sử dụng `compare(a,b)` để kiểm tra bằng nhau của **hai phần tử**. Nó hỏi hai *đối tượng bộ so sánh* có bằng nhau không; ý nghĩa chính xác được phân tích ở mục tiếp theo.
## 3. Ví dụ chạy được: bằng nhau trong thứ tự khác bằng nhau của `String`

Tạo tệp `ComparatorZeroDemo.java`:

~~~java
import java.util.Comparator;

public class ComparatorZeroDemo {
    public static void main(String[] args) {
        Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;

        String a = new String("Java");
        String b = new String("JAVA");
        String c = "Spring";

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("compare(a,b)==0: " + (ignoreCase.compare(a, b) == 0));
        System.out.println("compare(a,c)<0: " + (ignoreCase.compare(a, c) < 0));
        System.out.println("compare(c,a)>0: " + (ignoreCase.compare(c, a) > 0));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ComparatorZeroDemo.java
java ComparatorZeroDemo
~~~

Stdout:

~~~text
a == b: false
a.equals(b): false
compare(a,b)==0: true
compare(a,c)<0: true
compare(c,a)>0: true
~~~

Phân tích:

1. `new String("Java")` và `new String("JAVA")` tạo hai đối tượng String riêng.
2. `String.equals` phân biệt hoa/thường nên trả `false`.
3. `String.CASE_INSENSITIVE_ORDER` bỏ qua khác biệt hoa/thường khi so, nên `compare(a,b)` trả `0`.
4. Với `"Java"` và `"Spring"`, thứ tự không phân biệt hoa/thường vẫn đặt `Java` trước `Spring`.

Kết quả trên chứng minh rằng **tương đương trong comparator không đồng nghĩa bằng nhau theo `equals` của phần tử**.

## 4. `Comparator.equals(Object)` thực sự so sánh điều gì?

`Comparator.equals(Object)` mang hợp đồng của `Object.equals` (phản xạ, đối xứng, bắc cầu, nhất quán và không bằng `null`). Tài liệu `Comparator` còn nêu ý nghĩa đặc biệt nếu comparator **tự định nghĩa** sự bằng nhau: hai comparator được coi bằng nhau phải tạo ra **cùng thứ tự**, tức dấu của kết quả `compare` tương ứng giống nhau đối với mọi cặp phần tử trong miền so sánh.

Có hai trường hợp quan trọng:

**Trường hợp 1: comparator không ghi đè `equals`.** Phương thức kế thừa `Object.equals` thường chỉ trả `true` khi đang so **chính cùng một instance comparator**. Hai instance khác nhau có cùng thuật toán so sánh vẫn có thể `equals` trả `false`. Điều này hợp lệ: không bắt buộc comparator phải so bằng nhau theo “mã thuật toán giống nhau”.

**Trường hợp 2: lớp comparator chủ động ghi đè `equals`.** Lớp có thể cho hai comparator bằng nhau nếu chúng giữ cùng cấu hình và chắc chắn tạo cùng quy tắc thứ tự. Nếu ghi đè `equals` thì phải ghi đè `hashCode` tương ứng theo hợp đồng đối tượng. Kết quả `equals` là `true` phải đủ để bảo đảm chúng có cùng thứ tự; ngược lại, **hai comparator cùng hành vi so sánh chưa bắt buộc `equals` trả `true`**.

Không thể chỉ thử vài cặp dữ liệu rồi tuyên bố hai comparator tương đương với mọi giá trị. Hợp đồng về thứ tự là yêu cầu trên **toàn bộ miền giá trị mà chúng hỗ trợ**.

### Ví dụ chạy được: hai comparator cùng thuật toán nhưng không `equals`

Tạo tệp `ComparatorIdentityDemo.java`:

~~~java
import java.util.Comparator;

public class ComparatorIdentityDemo {
    static final class ByLength implements Comparator<String> {
        @Override
        public int compare(String a, String b) {
            return Integer.compare(a.length(), b.length());
        }
        // Không override equals(Object): kế thừa Object.equals.
    }

    public static void main(String[] args) {
        ByLength first = new ByLength();
        ByLength second = new ByLength();

        System.out.println("same comparator object: " + (first == second));
        System.out.println("comparators equal: " + first.equals(second));
        System.out.println("first compares: " + first.compare("dog", "cat"));
        System.out.println("second compares: " + second.compare("dog", "cat"));
        System.out.println("element objects equal: " + "dog".equals("cat"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ComparatorIdentityDemo.java
java ComparatorIdentityDemo
~~~

Stdout:

~~~text
same comparator object: false
comparators equal: false
first compares: 0
second compares: 0
element objects equal: false
~~~

Hai `ByLength` là hai object comparator riêng, vì vậy `first.equals(second)` là `false`. Cả hai đều cho `"dog"` và `"cat"` cùng độ dài, nên `compare(...)` trả `0`. Điều đó **không cho phép kết luận** rằng `first.equals(second)` phải là `true`; nó còn cho thấy `compare == 0` không liên quan trực tiếp đến `String.equals`.

## 5. Ví dụ ghi đè `Comparator.equals` theo cấu hình thứ tự

Khi ứng dụng có một loại comparator rõ ràng với tham số cấu hình xác định thứ tự, có thể tự định nghĩa `equals/hashCode` cho **đối tượng comparator**.

Tạo tệp `ConfiguredComparatorDemo.java`:

~~~java
import java.util.Comparator;

public class ConfiguredComparatorDemo {
    static final class ByRemainder implements Comparator<Integer> {
        private final int divisor;

        ByRemainder(int divisor) {
            if (divisor <= 0) {
                throw new IllegalArgumentException("divisor must be positive");
            }
            this.divisor = divisor;
        }

        @Override
        public int compare(Integer a, Integer b) {
            return Integer.compare(
                    Math.floorMod(a, divisor),
                    Math.floorMod(b, divisor)
            );
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof ByRemainder other)) return false;
            return divisor == other.divisor;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(divisor);
        }
    }

    public static void main(String[] args) {
        ByRemainder by10a = new ByRemainder(10);
        ByRemainder by10b = new ByRemainder(10);
        ByRemainder by5 = new ByRemainder(5);

        System.out.println("same instance: " + (by10a == by10b));
        System.out.println("same comparator configuration: "
                + by10a.equals(by10b));
        System.out.println("matching comparator hashes: "
                + (by10a.hashCode() == by10b.hashCode()));
        System.out.println("different configuration: " + by10a.equals(by5));
        System.out.println("12 versus 22: " + by10a.compare(12, 22));
        System.out.println("12.equals(22): " + Integer.valueOf(12).equals(22));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConfiguredComparatorDemo.java
java ConfiguredComparatorDemo
~~~

Stdout:

~~~text
same instance: false
same comparator configuration: true
matching comparator hashes: true
different configuration: false
12 versus 22: 0
12.equals(22): false
~~~

Trong ví dụ này, hai comparator có cùng `divisor` luôn áp dụng cùng công thức nên `equals` có thể trả `true`, và `hashCode` dựa trên cùng trường đó. Tuy nhiên hai số `12` và `22` vẫn là **hai Integer không bằng nhau**, dù kết quả chia lấy dư cho 10 đều bằng 2 và comparator trả 0.

`ByRemainder` cố ý chỉ xét phần dư nên **không nhất quán với `Integer.equals`**. Đây là một thứ tự theo nhóm/phần dư, không phải thứ tự số nguyên tự nhiên. Không áp dụng kiểu comparator này cho `TreeSet<Integer>` nếu muốn tập chứa **mọi số nguyên khác nhau**.

Lưu ý `compare` trong ví dụ yêu cầu các đối số `Integer` không `null` (unboxing vào `Math.floorMod` có thể ném `NullPointerException` nếu nhận null). Nếu cần hỗ trợ null, có thể bao comparator bằng `Comparator.nullsFirst` hoặc `Comparator.nullsLast` với chính sách phù hợp.

## 6. “Consistent with equals” là thuộc tính của quan hệ sắp xếp

Một thứ tự do `Comparator` định nghĩa được gọi là **nhất quán với `equals` của phần tử** khi, với mọi `a`, `b` thuộc miền so sánh:

~~~text
comparator.compare(a, b) == 0  ⇔  a.equals(b)
~~~

Đây là quan hệ giữa **`compare` và `equals` của phần tử**, hoàn toàn khác với `comparator.equals(otherComparator)`.

Ví dụ:

- `Comparator.naturalOrder()` trên `Integer` có quan hệ `compare(a,b)==0` phù hợp với `Integer.equals`.
- `String.CASE_INSENSITIVE_ORDER` **không** nhất quán với `String.equals` vì `"Java"` và `"JAVA"` có thứ tự bằng nhau nhưng `equals` là `false`.
- Comparator `Comparator.comparingInt(String::length)` không nhất quán với `String.equals` vì hai chuỗi khác nhau vẫn có thể cùng độ dài.
- Một comparator chỉ so `Person.id` chỉ nhất quán với `Person.equals` nếu `equals` của Person cũng định nghĩa bằng nhau đúng theo `id` trong toàn bộ miền đối tượng.

Comparator không nhất quán với `equals` không phải lúc nào cũng là lỗi. Nó phù hợp cho **sắp xếp theo nhóm, so không phân biệt hoa/thường, gom các giá trị cùng khóa**. Nhưng khi dùng trong những collection xác định tính duy nhất dựa trên so sánh thứ tự, sự khác biệt có hệ quả lớn.

### Phân biệt quan hệ bằng nhau với việc ưu tiên sắp xếp

Nếu muốn sắp theo độ dài nhưng **không** coi hai chuỗi cùng độ dài là một giá trị duy nhất, có thể thêm tiêu chí phụ:

~~~java
Comparator<String> byLengthThenNatural =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
~~~

Đoạn mã này là **mảnh minh họa trong ngữ cảnh đã `import java.util.Comparator;`**, không phải một tệp chương trình độc lập. `thenComparing` chỉ áp dụng so thứ hai khi tiêu chí độ dài trả 0. Với hai chuỗi khác nhau `"dog"` và `"cat"`, tiêu chí phụ phân biệt được chúng. Trên String, cách so tổng hợp này nhất quán với `String.equals`: trả 0 chỉ khi nội dung chuỗi giống nhau (trong miền không null). Đối với loại phần tử khác, phải chọn tiêu chí phụ thực sự phân biệt các đối tượng mà `equals` xem là khác.

## 7. Hệ quả đối với `TreeSet`

`TreeSet` là tập có sắp xếp. Khi được tạo với một comparator, nó dùng kết quả so sánh thứ tự để quyết định vị trí và **tính trùng nhau** của phần tử: nếu `compare(a,b)==0`, tập xem chúng như cùng một phần tử theo cấu trúc cây.

Tạo tệp `TreeSetComparatorDemo.java`:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class TreeSetComparatorDemo {
    public static void main(String[] args) {
        Comparator<String> ignoreCase = String.CASE_INSENSITIVE_ORDER;

        Set<String> tree = new TreeSet<>(ignoreCase);
        System.out.println("tree first add: " + tree.add("Java"));
        System.out.println("tree second add: " + tree.add("JAVA"));
        System.out.println("tree size: " + tree.size());
        System.out.println("tree contains java: " + tree.contains("java"));
        System.out.println("tree first element: " + tree.iterator().next());

        Set<String> hash = new HashSet<>();
        hash.add("Java");
        hash.add("JAVA");
        System.out.println("hash size: " + hash.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 TreeSetComparatorDemo.java
java TreeSetComparatorDemo
~~~

Stdout:

~~~text
tree first add: true
tree second add: false
tree size: 1
tree contains java: true
tree first element: Java
hash size: 2
~~~

Giải thích:

1. `TreeSet` đưa `"Java"` vào tập.
2. Khi thêm `"JAVA"`, comparator không phân biệt hoa/thường trả 0 so với `"Java"`, nên `TreeSet` coi đây là phần tử đã có và `add` trả `false`.
3. Tập vẫn chứa phần tử đầu tiên `"Java"`; `contains("java")` trả `true` theo comparator.
4. `HashSet` dùng `hashCode` và `equals` của `String`, hai chuỗi khác nội dung về chữ hoa/thường nên cả hai được lưu.

**Điểm thiết kế quan trọng:** Các lớp sorted set hoạt động đúng theo **quy tắc comparator**, nhưng để đáp ứng trọn hợp đồng `Set` về tính bằng nhau giữa phần tử, thứ tự phải **nhất quán với `equals`**. Khi comparator không nhất quán, hành vi của sorted set vẫn được xác định theo cấu trúc cây nhưng khác trực giác về `Set` thông thường và có thể vi phạm hợp đồng chung của `Set` đối với tập dựa trên `equals`.

Dùng `TreeSet` với comparator không nhất quán là hợp lý khi bạn **thật sự muốn gộp những phần tử thuộc cùng lớp thứ tự**. Nếu muốn chỉ sắp xếp theo một trường nhưng vẫn giữ tất cả các đối tượng khác nhau, hãy bổ sung tiêu chí phụ nhất quán.

## 8. Hệ quả tương tự với `TreeMap`

`TreeMap` sử dụng comparator để sắp xếp **khóa** và xác định khi nào hai khóa được coi tương đương. Nếu comparator trả 0, thao tác `put` cho khóa mới có thể **ghi đè giá trị** của entry đã có, dù `key1.equals(key2)` là `false`.

Tạo tệp `TreeMapComparatorDemo.java`:

~~~java
import java.util.Map;
import java.util.TreeMap;

public class TreeMapComparatorDemo {
    public static void main(String[] args) {
        Map<String, String> map =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

        System.out.println("first put: " + map.put("Java", "first"));
        System.out.println("second put: " + map.put("JAVA", "second"));
        System.out.println("size: " + map.size());
        System.out.println("lookup java: " + map.get("java"));
        System.out.println("original key kept: " + map.keySet().iterator().next());
        System.out.println("key equals: " + "Java".equals("JAVA"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 TreeMapComparatorDemo.java
java TreeMapComparatorDemo
~~~

Stdout:

~~~text
first put: null
second put: first
size: 1
lookup java: second
original key kept: Java
key equals: false
~~~

Lần `put("JAVA", "second")` tìm thấy một khóa tương đương thứ tự với `"Java"`, nên cập nhật **value** của entry đó thay vì thêm entry mới. Tên khóa lưu ban đầu trong cây vẫn là `"Java"` trong ví dụ. Vì thế:

- `TreeMap` có một entry thay vì hai.
- `get("java")` tìm được giá trị mới `"second"`.
- `String.equals("Java","JAVA")` vẫn là `false`.

Giống `TreeSet`, `TreeMap` hoạt động theo comparator được cung cấp; muốn tuân trọn hợp đồng chung của `Map` dựa trên `equals` của khóa thì comparator cần nhất quán với `equals`.

## 9. Điều gì xảy ra khi dùng `sort`, `min/max` hoặc `binarySearch`?

Ở phép **sắp xếp** (`List.sort`, `Arrays.sort`, `Collections.sort`), comparator chỉ quyết định thứ tự. Hai phần tử được `compare` trả 0 có thể vẫn là hai đối tượng riêng và vẫn có mặt trong danh sách sau khi sort. Sắp xếp không tự gộp các phần tử.

Ví dụ một danh sách chứa `"Java"` và `"JAVA"` sau khi `sort(String.CASE_INSENSITIVE_ORDER)` vẫn có **hai phần tử**. Tính ổn định của phương thức sắp xếp được công bố cho những API cụ thể, ví dụ `List.sort` đảm bảo không đảo thứ tự của các phần tử mà comparator coi là bằng nhau.

Tương tự:

- `Collections.min/max` với comparator chọn cực trị **theo thứ tự của comparator**; một phần tử cực trị không nhất thiết bằng phần tử khác đang cùng lớp thứ tự theo `equals`.
- `Collections.binarySearch(list, key, comparator)` có thể tìm một phần tử mà `compare(found,key)==0`, không cần `found.equals(key)`; danh sách phải được sắp theo comparator phù hợp trước. Nếu có nhiều kết quả tương đương thứ tự, không bảo đảm chọn vị trí cụ thể nào.

### Ví dụ chạy được: danh sách không tự gộp phần tử

Tạo tệp `SortKeepsElementsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortKeepsElementsDemo {
    public static void main(String[] args) {
        Comparator<String> byLength =
                Comparator.comparingInt(String::length);

        List<String> words = new ArrayList<>(
                List.of("dog", "a", "cat")
        );
        words.sort(byLength);

        System.out.println("sorted: " + words);
        System.out.println("size: " + words.size());
        System.out.println("dog vs cat: " + byLength.compare("dog", "cat"));
        System.out.println("dog equals cat: " + "dog".equals("cat"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SortKeepsElementsDemo.java
java SortKeepsElementsDemo
~~~

Stdout:

~~~text
sorted: [a, dog, cat]
size: 3
dog vs cat: 0
dog equals cat: false
~~~

Hai chuỗi cùng độ dài vẫn được giữ. `List.sort` là phép **sắp xếp**, còn `TreeSet` áp dụng quy tắc tương đương thứ tự vào **tính duy nhất** phần tử.

## 10. Cách tạo comparator thích hợp với ý định nghiệp vụ

### Nếu cần gom phần tử theo một khóa

Nếu miền nghiệp vụ coi tên không phân biệt hoa/thường là cùng một khóa, `String.CASE_INSENSITIVE_ORDER` với `TreeMap` hoặc `TreeSet` có thể phù hợp. Hãy mô tả rõ rằng tính duy nhất là theo **khóa chuẩn hóa** hoặc **lớp tương đương do comparator quy định**; đừng nhầm đây là `String.equals`.

Nếu muốn quản lý chính xác cách chuẩn hóa, cân nhắc chuyển dữ liệu sang một kiểu khóa riêng có `equals/hashCode` phản ánh quan hệ đó, ví dụ cấu trúc chứa tên đã chuẩn hóa một cách nhất quán. Với ngôn ngữ tự nhiên và đa ngôn ngữ, so sánh/chuẩn hóa Unicode, locale và quy tắc chữ hoa/thường cần được thiết kế cụ thể; không nên mặc định mọi cách so chuỗi đều có cùng hợp đồng.

### Nếu cần bảo tồn mọi phần tử khác nhau

Comparator nên có **tie-breaker** để phân biệt các phần tử khác nhau theo `equals`. Với String:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
~~~

Với lớp tùy biến, nếu `equals` dựa trên `id`, có thể thêm so sánh `id` làm tie-breaker (miễn là `id` có ngữ nghĩa phù hợp). Nhưng **đừng dùng `System.identityHashCode` như một tie-breaker duy nhất** để bảo đảm phân biệt mọi đối tượng: hash có thể trùng nhau. Cũng không thể chỉ thêm tiêu chí phụ tùy ý rồi mặc định comparator đã nhất quán với mọi định nghĩa `equals`.

### Nếu muốn so hai comparator có bằng nhau hay không

Hãy dùng `comparatorA.equals(comparatorB)` khi mục tiêu **thật sự là đối tượng comparator**; kết quả `false` có thể chỉ do chúng là hai instance khác nhau. Trong nhiều ứng dụng, không cần kiểm tra sự bằng nhau của hai comparator: chỉ cần chọn đúng một comparator và truyền dùng lại.

Nếu xây dựng một **lớp comparator có cấu hình** và muốn dùng nó làm khóa cache/configuration, có thể triển khai `equals` và `hashCode` dựa trên các tham số xác định thứ tự. Điều này là lựa chọn thiết kế **độc lập** với quy tắc `compare(a,b)==0` trên dữ liệu.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| `c.equals(d)` tương đương `c.compare(a,b)==0`. | Hai vế có **đối tượng so sánh khác nhau**: comparator với comparator, phần tử với phần tử. |
| `compare(a,b)==0` thì `a.equals(b)` luôn `true`. | Chỉ đúng khi comparator **nhất quán với equals** trên miền phần tử liên quan. |
| Hai comparator dùng cùng thuật toán thì `c.equals(d)` luôn `true`. | Không nhất thiết: `equals` có thể kế thừa từ `Object` và so danh tính instance. |
| `c.equals(d)==false` nghĩa là tồn tại cặp phần tử mà hai comparator sắp khác nhau. | Sai: equals trả false **không chứng minh** hai comparator tạo thứ tự khác. |
| Comparator phải trả đúng `-1`, `0`, `1`. | Hợp đồng chỉ quy định dấu âm/0/dương. |
| `TreeSet` quyết định phần tử trùng bằng `a.equals(b)`. | Với comparator cung cấp, cây dùng `compare(a,b)==0` để quyết định tương đương thứ tự. |
| `TreeMap.put` hai khóa có `equals` khác nhau luôn tạo hai entry. | Có thể chỉ còn một entry nếu comparator coi chúng tương đương (`compare==0`). |
| `sort` loại bớt phần tử có `compare==0`. | Sắp xếp không gộp phần tử; danh sách giữ nguyên số lượng. |
| Chỉ cần thêm tie-breaker theo một hash là luôn có total order đúng. | Hash có thể trùng; cần tiêu chí phụ phù hợp với ngữ nghĩa đối tượng. |
| `Comparator.equals` phải được ghi đè trong mọi comparator. | Không bắt buộc; kế thừa `Object.equals` là hợp lệ. |

## 12. Checklist kiểm tra thiết kế

Khi viết hoặc sử dụng một `Comparator<T>`:

1. Xác định **quy tắc sắp xếp** của `compare(a,b)` và những trường nào tham gia.
2. Hỏi rõ: hai phần tử được `compare` trả 0 có cần coi như **cùng khóa** không, hay chỉ cùng mức ưu tiên/nhóm?
3. So đối chiếu với `a.equals(b)`: comparator có **consistent with equals** trong miền sử dụng không?
4. Nếu dùng `TreeSet`/`TreeMap`, kiểm tra kỹ trường hợp `compare(a,b)==0` nhưng `a.equals(b)==false` để tránh vô tình gộp phần tử hoặc ghi đè giá trị.
5. Nếu chỉ cần sắp xếp List, đừng cho rằng hai phần tử `compare==0` sẽ bị xóa hay trộn.
6. Với nhiều tiêu chí, dùng `Comparator.comparing(...).thenComparing(...)` và chọn tie-breaker theo ngữ nghĩa mong muốn.
7. Đảm bảo comparator tuân quy tắc về dấu, bắc cầu, và sự nhất quán của các phần tử tương đương; tránh viết `return a - b` cho `int` vì tràn số có thể tạo kết quả sai, dùng `Integer.compare(a,b)`.
8. Nếu comparator có trạng thái hoặc cấu hình thay đổi trong lúc đang dùng bởi một `TreeSet`/`TreeMap`, thứ tự cây có thể không còn hợp lệ; nên giữ cấu hình so sánh **ổn định** suốt vòng đời sử dụng.
9. Chỉ đánh giá `comparatorA.equals(comparatorB)` khi thực sự cần so **hai comparator**. Nếu tự override phương thức này, phải đảm bảo kết quả `true` suy ra cùng thứ tự và giữ hợp đồng với `hashCode()`.

**Ghi nhớ:** `Comparator.equals(Object)` trả lời liệu **hai đối tượng bộ so sánh** có được coi bằng nhau hay không; `Comparator.compare(a,b)==0` trả lời liệu **hai phần tử** có tương đương theo một quy tắc thứ tự hay không. Quan hệ thứ hai chỉ trùng `a.equals(b)` khi comparator nhất quán với equals. Phân biệt ba quan hệ này giúp tránh các lỗi khó phát hiện với `TreeSet`, `TreeMap` và việc định nghĩa tính duy nhất của dữ liệu.