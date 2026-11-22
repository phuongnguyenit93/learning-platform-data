# Hợp đồng dấu, bắc cầu và các nhóm có kết quả so sánh bằng 0

## 1. Comparator định nghĩa một quan hệ thứ tự, không chỉ một công thức sắp xếp

`java.util.Comparator<T>` biểu diễn quy tắc so sánh hai giá trị cùng kiểu `T`. Phương thức trung tâm là:

```java
int compare(T a, T b);
```

Đó là **chữ ký minh họa từ interface**, không phải một chương trình chạy độc lập. Khi gọi `compare(a, b)`, ý nghĩa của **dấu** kết quả là:

| Giá trị trả về | Ý nghĩa |
| --- | --- |
| Nhỏ hơn `0` | `a` đứng trước `b`. |
| Bằng `0` | `a` và `b` thuộc **cùng nhóm tương đương theo comparator**. |
| Lớn hơn `0` | `a` đứng sau `b`. |

Số cụ thể không quan trọng: `-7` và `-1` đều biểu diễn “nhỏ hơn”; `42` và `1` đều biểu diễn “lớn hơn”. Vì vậy hãy kiểm tra `compare(a,b) < 0`, `== 0`, `> 0` hoặc dùng `Integer.signum(...)` khi cần so dấu. Đừng gắn ý nghĩa thứ hạng, khoảng cách hay mức chênh lệch nghiệp vụ trực tiếp vào trị tuyệt đối của kết quả.

Một `Comparator` **hợp lệ** phải cho quan hệ có tính nhất quán trên toàn bộ miền đối tượng được phép so. Nếu chỉ cho kết quả có vẻ đúng trong vài cặp nhưng vi phạm hợp đồng dấu hoặc tính bắc cầu, `List.sort`, `Collections.sort`, `Arrays.sort`, `TreeSet` và `TreeMap` có thể hoạt động không đúng điều ta mong đợi. Một số thuật toán sắp xếp có thể phát hiện vi phạm và ném `IllegalArgumentException: Comparison method violates its general contract!`; không được dựa vào việc lỗi chắc chắn bị phát hiện hay luôn xuất hiện.

## 2. Hợp đồng dấu: đảo thứ tự đối số phải đảo dấu

Với các đối tượng hợp lệ `x` và `y`, Comparator yêu cầu:

```text
sgn(compare(x, y)) == -sgn(compare(y, x))
```

Trong đó `sgn(n)` là dấu của `n`: `-1`, `0` hoặc `1`. Nói cách khác:

- Nếu `compare(x, y) < 0` thì `compare(y, x) > 0`.
- Nếu `compare(x, y) > 0` thì `compare(y, x) < 0`.
- Nếu `compare(x, y) == 0` thì `compare(y, x) == 0`.

Đây là quy tắc **đối xứng về dấu**; không phải yêu cầu hai kết quả nguyên phải đối nhau về trị số. Ví dụ `compare(x,y) == -10` và `compare(y,x) == 5` vẫn thỏa điều kiện dấu, dù thường dễ hiểu hơn nếu comparator trả `-1`, `0`, `1`. Điều kiện này cũng có hệ quả: nếu lời gọi một chiều ném exception cho một cặp, chiều đảo không được tùy tiện trả một dấu có nghĩa như thể cặp hợp lệ.

Cách triển khai chuẩn khi so trường nguyên:

```java
Comparator<Task> byPriority =
        Comparator.comparingInt(Task::priority);
```

*Đoạn này giả định kiểu `Task` có accessor `priority()` trả về `int` và được đặt trong nơi có thể khai báo biến; chương trình hoàn chỉnh ở mục 6.*

`Comparator.comparingInt` dùng phép so số nguyên đúng quy tắc; khi hai giá trị bằng nhau, kết quả bằng `0`, còn khi chênh lệch thì kết quả mang dấu tương ứng.

### Vì sao không viết phép trừ một cách máy móc?

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

Đây là cách viết **không an toàn** trên toàn miền `int` vì phép trừ có thể tràn số nguyên. Ví dụ:

```java
int a = Integer.MIN_VALUE;
int b = 1;

System.out.println(a - b);             // 2147483647: tràn số
System.out.println(Integer.compare(a, b)); // -1: đúng thứ tự
```

Dùng `Integer.compare(a,b)`, `Long.compare(...)` hay các factory như `comparingInt`, `comparingLong`, `comparingDouble`. Tương tự, đừng đảo comparator bằng cách tùy tiện `-compare(a,b)`: nếu kết quả là `Integer.MIN_VALUE` thì dấu của phép phủ định vẫn có thể sai do overflow. `comparator.reversed()` hoặc đổi thứ tự đối số một cách phù hợp sẽ diễn đạt rõ ý hơn.

## 3. Tính bắc cầu: không được có vòng thứ tự

Hợp đồng Comparator yêu cầu:

```text
compare(x, y) > 0 và compare(y, z) > 0
    => compare(x, z) > 0
```

Nhờ tính đối xứng dấu, phát biểu tương đương cho chiều “nhỏ hơn” là:

```text
x < y và y < z  =>  x < z
```

Ví dụ các ưu tiên `1 < 2 < 3` thì phải có `1 < 3`. Nếu comparator kết luận `A < B`, `B < C` nhưng lại `C < A`, ta có một chu trình không thể sắp thành thứ tự nhất quán. Một comparator kiểu “kéo–búa–bao” định nghĩa A thắng B, B thắng C, C thắng A có thể hữu ích cho trò chơi nhưng **không thích hợp làm quy tắc sort**.

Tính bắc cầu phải đúng với **mọi bộ ba** giá trị hợp lệ, không chỉ ba trường hợp thường gặp. Với comparator nhiều tiêu chí, nên so lần lượt từng trường theo một thứ tự ưu tiên xác định, rồi chỉ dùng tiêu chí tiếp theo khi tiêu chí trước bằng nhau. `thenComparing(...)` giúp thể hiện quy tắc này.

Ví dụ một comparator được xây dựng từ các thành phần đã có thứ tự hợp lệ:

```java
Comparator<Task> ordering = Comparator
        .comparingInt(Task::priority)
        .thenComparing(Task::team)
        .thenComparing(Task::code);
```

*Đây là đoạn minh họa trong một lớp/phương thức có kiểu `Task`. `team()` và `code()` trả `String` không `null`.*

Thứ tự là: ưu tiên nhỏ đứng trước; nếu cùng ưu tiên thì so tên nhóm; nếu cùng cả hai thì so mã nhiệm vụ. Với `String` dùng thứ tự tự nhiên, một bộ tiêu chí như vậy thường dễ phân tích và kiểm tra tính bắc cầu hơn một chuỗi `if` trả các dấu tùy ý.

## 4. Kết quả compare == 0 tạo nhóm tương đương theo thứ tự

Một điểm thường bị bỏ qua: `compare(x,y) == 0` **không bắt buộc có nghĩa `x.equals(y)`**.

Ví dụ, comparator chỉ xét `priority`:

```java
Comparator<Task> byPriority =
        Comparator.comparingInt(Task::priority);
```

Các tác vụ sau có thể đều có ưu tiên `2`:

```text
Task(team="alpha", priority=2, code="A")
Task(team="alpha", priority=2, code="B")
Task(team="beta",  priority=2, code="C")
```

Chúng khác nhau về `team` hoặc `code` nên có thể không bằng nhau theo `equals()`, nhưng comparator trả `0` cho mọi cặp trong nhóm ưu tiên `2`. Đây là quyết định **cố ý bỏ qua các tiêu chí không thuộc thứ tự**, khiến comparator nhìn cả nhóm như một mức hạng chung.

Định nghĩa quan hệ `x ~ y` khi `compare(x,y) == 0`. Với một comparator hợp lệ, quan hệ này phải là một **quan hệ tương đương**:

1. **Phản xạ:** `compare(x,x) == 0`.
2. **Đối xứng:** `compare(x,y) == 0` thì `compare(y,x) == 0`.
3. **Bắc cầu:** nếu `compare(x,y) == 0` và `compare(y,z) == 0` thì `compare(x,z) == 0`.

Hơn nữa, hai phần tử đã nằm **cùng nhóm 0** phải có cùng quan hệ thứ tự với **mọi phần tử thứ ba**:

```text
compare(x, y) == 0
    => sgn(compare(x, z)) == sgn(compare(y, z))
       với mọi z hợp lệ
```

Ví dụ, nếu `x` và `y` cùng nhóm ưu tiên 2, còn `z` có ưu tiên 5, thì cả hai phải đứng trước `z`. Không được cho `x < z` nhưng `y > z` vì như vậy một nhóm tương đương lại tự mâu thuẫn.

Điều kiện này đôi khi gọi là **nhất quán của nhóm có compare bằng 0**; nó mạnh hơn câu “chỉ cần comparator có đối xứng dấu”. Một phép so tùy biến có thể trả `0` cho cặp đặc biệt nhưng vẫn vi phạm quy tắc khi gặp phần tử thứ ba.

### Ví dụ một nhóm 0 sai về logic

Giả sử trên số nguyên, ta đặc cách `1` và `3` “bằng nhau” (compare bằng 0), nhưng mọi cặp còn lại dùng thứ tự số tự nhiên. Khi so với `2`:

- `compare(1,3) == 0`.
- `compare(1,2) < 0` vì `1 < 2`.
- `compare(3,2) > 0` vì `3 > 2`.

`1` và `3` đã được tuyên bố cùng nhóm nhưng lại đứng hai phía khác nhau của `2`. Đó là comparator sai hợp đồng; không thể sửa bằng cách chỉ đổi cách sort. Muốn nhóm theo quy tắc khác, phải **định nghĩa thứ tự trên các nhóm** sao cho mọi thành viên của cùng nhóm có cùng kết quả dấu với mọi nhóm khác.

## 5. Quan hệ của Comparator với equals()

Java phân biệt hai quan hệ:

- `x.equals(y)`: bình đẳng logic do kiểu `x` định nghĩa.
- `comparator.compare(x,y) == 0`: tương đương theo thứ tự mà comparator cụ thể cung cấp.

Một comparator được xem là **consistent with equals** khi với mọi cặp thuộc miền so sánh, `compare(x,y) == 0` khi và chỉ khi `x.equals(y)`. Đây là đặc tính **được khuyến nghị mạnh** nếu comparator dùng trong sorted set/sorted map với ngữ nghĩa khóa của `Set`/`Map`; không phải mọi comparator đều bắt buộc phân biệt đối tượng theo `equals()`.

Ví dụ khác nhau có chủ đích:

```java
String a = "Java";
String b = "JAVA";

System.out.println(a.equals(b));                  // false
System.out.println(
        String.CASE_INSENSITIVE_ORDER.compare(a, b)); // 0
```

Với `String.CASE_INSENSITIVE_ORDER`, hai chuỗi thuộc cùng nhóm sắp xếp không phân biệt chữ hoa/thường, nhưng `String.equals()` vẫn phân biệt chữ hoa/thường. Quan hệ này **không consistent with equals**.

Đặc biệt với `BigDecimal`:

```java
BigDecimal one = new BigDecimal("1.0");
BigDecimal another = new BigDecimal("1.00");

System.out.println(one.compareTo(another)); // 0
System.out.println(one.equals(another));    // false
```

*Đoạn minh họa cần `import java.math.BigDecimal;`.* `BigDecimal.compareTo` xem hai số cùng giá trị số là tương đương theo thứ tự, còn `equals` xét cả `scale`. Comparator theo thứ tự tự nhiên của `BigDecimal` vì thế không consistent with equals.

Khi đối tượng là khóa của `TreeMap` hoặc phần tử `TreeSet`, cần biết chính xác mục đích: **muốn gộp theo một tiêu chí**, hay **muốn phân biệt tất cả các giá trị khác nhau theo equals**? Cả hai nhu cầu đều hợp lý, nhưng tạo ra hành vi khác nhau.

## 6. Ví dụ Java 17+ chạy được: dấu, bắc cầu, nhóm 0, TreeSet và TreeMap

Lưu chương trình sau vào tệp `ComparatorContractDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorContractDemo {

    record Task(String team, int priority, String code) {}

    public static void main(String[] args) {
        Task a = new Task("alpha", 2, "A");
        Task b = new Task("alpha", 2, "B");
        Task c = new Task("beta", 4, "C");
        Task d = new Task("beta", 2, "D");
        Task e = new Task("beta", 6, "E");

        Comparator<Task> byPriority =
                Comparator.comparingInt(Task::priority);

        // Quy tắc dấu và đối xứng dấu.
        System.out.println(byPriority.compare(a, b));
        System.out.println(a.equals(b));
        System.out.println(Integer.signum(byPriority.compare(a, c)));
        System.out.println(Integer.signum(byPriority.compare(c, a)));

        // Tính bắc cầu: 2 < 4 < 6 nên 2 < 6.
        boolean transitive =
                byPriority.compare(a, c) < 0
                && byPriority.compare(c, e) < 0
                && byPriority.compare(a, e) < 0;
        System.out.println(transitive);

        // TreeSet coi các Task cùng priority là tương đương.
        Set<Task> grouped = new TreeSet<>(byPriority);
        grouped.add(a);
        grouped.add(b);
        grouped.add(c);
        grouped.add(d);
        grouped.add(e);
        System.out.println(grouped.size());
        System.out.println(grouped.contains(
                new Task("unknown", 2, "Z")));

        // TreeMap cũng xác định khóa tương đương theo comparator.
        Map<Task, String> map = new TreeMap<>(byPriority);
        map.put(a, "đầu tiên");
        map.put(b, "cập nhật");
        System.out.println(map.size());
        System.out.println(map.get(a));

        // Thêm tie-breaker để phân biệt cả ba thành phần của record.
        Comparator<Task> byAllFields = byPriority
                .thenComparing(Task::team)
                .thenComparing(Task::code);
        Set<Task> distinct = new TreeSet<>(byAllFields);
        distinct.add(a);
        distinct.add(b);
        distinct.add(c);
        distinct.add(d);
        distinct.add(e);
        System.out.println(distinct.size());
        System.out.println(Integer.signum(byAllFields.compare(a, b)));

        // Hai ví dụ compare == 0 nhưng equals() là false.
        String s1 = "Java";
        String s2 = "JAVA";
        System.out.println(s1.equals(s2));
        System.out.println(
                String.CASE_INSENSITIVE_ORDER.compare(s1, s2));

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println(x.compareTo(y));
        System.out.println(x.equals(y));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac ComparatorContractDemo.java
java ComparatorContractDemo
```

Đầu ra chính xác:

```text
0
false
-1
1
true
3
true
1
cập nhật
5
-1
false
0
0
false
```

Diễn giải từng phần:

1. `byPriority.compare(a,b)` in `0` vì cùng ưu tiên `2`, nhưng `a.equals(b)` in `false` vì `Task` là record với ba component, trong đó `code` khác nhau.
2. `Integer.signum(compare(a,c))` in `-1`; đảo chiều thành `compare(c,a)` cho `1`. Đây là quan hệ dấu đối xứng.
3. Ba phép so 2, 4 và 6 cho `true` ở kiểm tra bắc cầu.
4. `TreeSet` với `byPriority` có ba nhóm tương đương theo các mức ưu tiên `2`, `4`, `6`, nên `size()` là `3`. `contains(new Task("unknown",2,"Z"))` là `true` dù record mới không equals với `a`, `b` hay `d`, vì comparator xem cùng ưu tiên là cùng khóa sắp xếp.
5. `TreeMap` dùng comparator để xác định khóa: thêm `a` rồi `b` (cùng ưu tiên) chỉ tạo **một mapping**; lệnh thứ hai thay giá trị thành `cập nhật`, nên `size()` là `1`.
6. `byAllFields` bổ sung `team` và `code` để tách các nhóm cùng `priority`. Năm record trong ví dụ đều khác nhau theo ba thành phần nên `TreeSet` có `5` phần tử; trong nhóm cùng ưu tiên và cùng team, `"A"` đứng trước `"B"`, trả dấu âm.
7. Hai cặp `String` và `BigDecimal` minh họa `compare == 0` nhưng `equals() == false` theo hai lý do khác nhau: bỏ qua phân biệt chữ hoa/thường và bỏ qua khác biệt scale.

## 7. Vì sao TreeSet và TreeMap coi compare == 0 là cùng phần tử/khóa?

`TreeSet` sử dụng thứ tự tự nhiên (`Comparable`) hoặc một `Comparator` được cung cấp để xác định vị trí phần tử và xem hai phần tử có tương đương trong cây hay không. `TreeMap` áp dụng nguyên tắc tương tự cho khóa. Do đó, đối với các cấu trúc này:

```text
compare(a, b) == 0
    ⇒ TreeSet xem a và b tương đương để lưu/tìm phần tử.
    ⇒ TreeMap xem a và b là cùng khóa để lưu/tìm mapping.
```

**Hệ quả thực tế:** `TreeSet` với comparator chỉ xét `priority` không giữ được nhiều `Task` khác nhau trong cùng một priority. Nó là tập hợp **mức ưu tiên** theo nghĩa comparator, không phải tập hợp tất cả tác vụ phân biệt theo record equality.

Nếu đó là chủ ý — ví dụ chỉ cần một đại diện cho mỗi nhóm ưu tiên — comparator theo một trường là hợp lý. Nếu muốn giữ **mọi tác vụ khác nhau**, hãy bổ sung tie-breaker đủ để phân biệt chúng.

Ví dụ:

```java
Comparator<Task> byPriorityThenTeamThenCode =
        Comparator.comparingInt(Task::priority)
                .thenComparing(Task::team)
                .thenComparing(Task::code);
```

*Đoạn minh họa dành cho cùng record `Task` ở mục 6.*

Với record ba thành phần của ví dụ, compare bằng 0 khi cả ba thành phần giống nhau, nên phù hợp với record `equals()`. Nhưng nếu đổi `Task` thành entity có equality **chỉ theo ID**, comparator ba trường trạng thái có thể không còn phù hợp. Cần so tiêu chí thứ tự với định nghĩa identity thật sự của lớp; chỉ thêm tie-breaker “cho chắc” mà không hiểu equality có thể gây một kiểu sai khác.

Tài liệu Java khuyến nghị lưu ý rõ khi comparator có ordering **inconsistent with equals**, bởi `SortedSet` và `SortedMap` được thiết kế để tuân theo các hợp đồng tổng quát `Set`/`Map` vốn mô tả equality theo `equals()`. Một `TreeSet` dùng comparator inconsistent vẫn vận hành theo quy tắc comparator; nhưng kết quả có thể không thỏa trực giác và hợp đồng bình đẳng của `Set` nói chung.

Phân biệt thêm: `HashSet`/`HashMap` thông thường dùng `equals()/hashCode()`, **không sử dụng Comparator** để gộp khóa. Vì vậy cùng một cặp phần tử có thể được `HashSet` giữ thành hai mục trong khi `TreeSet` có comparator xem chúng là một.

## 8. Những cách tạo Comparator hợp lệ và dễ bảo trì

Java hỗ trợ API composition để tránh tự viết dấu so sánh tùy hứng:

| API | Vai trò |
| --- | --- |
| `Comparator.comparing(keyExtractor)` | So theo khóa có thứ tự tự nhiên. |
| `Comparator.comparingInt/Long/Double(...)` | So khóa nguyên thủy theo thứ tự chuẩn và tránh phép trừ nguy hiểm. |
| `thenComparing(...)` | Dùng tiêu chí phụ khi tiêu chí trước cho kết quả `0`. |
| `reversed()` | Đảo toàn bộ thứ tự của comparator. |
| `Comparator.naturalOrder()` | Dùng thứ tự tự nhiên của kiểu có `Comparable`. |
| `Comparator.reverseOrder()` | Dùng thứ tự tự nhiên đảo chiều. |
| `Comparator.nullsFirst(...)` và `nullsLast(...)` | Quy định vị trí `null` nếu miền dữ liệu có thể chứa null. |

Ví dụ cần ưu tiên **cao trước**, sau đó mã theo thứ tự tăng:

```java
Comparator<Task> order = Comparator
        .comparingInt(Task::priority)
        .reversed()
        .thenComparing(Task::code);
```

*Đoạn minh họa áp dụng vào record `Task` ở mục 6.* Lưu ý vị trí `reversed()`: gọi **trước** `thenComparing` nghĩa là chỉ tiêu chí ưu tiên được đảo, còn `code` vẫn tăng dần. Nếu viết `Comparator.comparingInt(...).thenComparing(...).reversed()`, **toàn bộ thứ tự kết hợp** sẽ được đảo, kể cả tiêu chí phụ.

Khi trường có thể `null`, cần quyết định rõ:

```java
Comparator<String> nullableNames =
        Comparator.nullsFirst(Comparator.naturalOrder());
```

Nó cho `null` đứng trước các chuỗi khác và dùng thứ tự tự nhiên cho các chuỗi không null. `Comparator.naturalOrder()` tự thân không chấp nhận so một giá trị `null`. Không tạo quy tắc null tùy tiện dẫn đến tình trạng `compare(null,x)` trả cùng dấu với `compare(x,null)`.

Một số factory tạo comparator theo khóa của object yêu cầu key phù hợp để so. Nếu key extractor trả nullable mà chưa xử lý, `NullPointerException` có thể xuất hiện khi sort; hãy dùng comparator khóa có chính sách null rõ ràng, hoặc thiết kế dữ liệu không chứa null.

## 9. Tính ổn định của thứ tự khác với tính hợp lệ của Comparator

“Stable sort” có nghĩa các phần tử được comparator xem là bằng nhau (`compare == 0`) giữ **thứ tự tương đối ban đầu** sau khi sort. Điều này **không biến hai phần tử thành cùng object**, cũng không làm chúng `equals()` nhau.

Ví dụ danh sách chứa:

```text
Task A: priority=2
Task B: priority=1
Task C: priority=2
```

Nếu sort ổn định theo `priority` tăng dần, kết quả là `B, A, C`: A và C vẫn nằm cạnh nhau trong nhóm priority 2 theo thứ tự ban đầu. `List.sort` trong Java có cam kết sort ổn định. Tuy nhiên, **TreeSet** với cùng comparator sẽ giữ một phần tử đại diện cho nhóm priority 2, bởi đây là cấu trúc set theo thứ tự so sánh, không phải sắp xếp list.

Tính ổn định của một thuật toán sort **không sửa được** comparator sai hợp đồng. Một comparator thay kết quả theo đồng hồ, số ngẫu nhiên hoặc trạng thái mutable trong lúc sắp xếp có thể khiến kết quả không nhất quán dù thuật toán được cam kết stable.

Khi áp dụng comparator vào sorted collection dài hạn, dữ liệu tham gia so sánh cũng nên ổn định trong thời gian đối tượng là phần tử/khóa; nếu thay đổi trường sắp xếp sau khi insert vào `TreeSet`/`TreeMap`, cấu trúc cây không tự sắp lại theo vị trí mới, dẫn đến lỗi tra cứu khó hiểu.

## 10. Các lỗi Comparator phổ biến

### 10.1. Trả 1 cho mọi cặp không bằng nhau

```java
// SAI: nếu a < b và b > a đều trả 1, vi phạm đối xứng dấu.
Comparator<Integer> bad = (a, b) ->
        a.equals(b) ? 0 : 1;
```

Nếu hai giá trị khác nhau, so theo cả hai chiều đều cho dấu dương. Không có thứ tự nhất quán.

### 10.2. Tạo chu kỳ

Một luật “0 trước 1, 1 trước 2, nhưng 2 lại trước 0” vi phạm tính bắc cầu. Comparator dành cho sort phải áp dụng quan hệ thứ tự xuyên suốt trên tất cả cặp và bộ ba.

### 10.3. Cho hai giá trị bằng 0 nhưng bất đồng khi so với giá trị thứ ba

Nhóm `x ~ y` không thể đứng hai phía khác nhau của `z`. Nếu comparator dùng luật ngoại lệ cho một cặp mà không thiết kế cả lớp tương đương, dễ vi phạm điều kiện dấu cho nhóm 0.

### 10.4. Dùng phép trừ số nguyên

`(a,b) -> a.age() - b.age()` có thể sai trên miền `int` vì overflow. Sử dụng `Integer.compare` hoặc `Comparator.comparingInt`. Với `long`, phép ép hiệu thành `int` còn nguy hiểm hơn.

### 10.5. Nhầm compare bằng 0 với equals bằng true

`String.CASE_INSENSITIVE_ORDER` và `BigDecimal.compareTo` là những ví dụ compare bằng 0 không đồng nghĩa equals. Trong `TreeSet` hoặc `TreeMap`, điều này thay đổi cách gộp dữ liệu.

### 10.6. Dùng tie-breaker thiếu hoặc thừa

Comparator chỉ xét `lastName` sẽ gộp nhiều người trùng họ trong `TreeSet`. Nhưng comparator xét trạng thái mutable hoặc timestamp ngoài identity có thể làm cùng entity bị coi là khác nhau sau cập nhật. Phải xác định rõ điều kiện một “nhóm 0” có ý nghĩa gì với nghiệp vụ và collection đích.

### 10.7. Phá hợp đồng khi giá trị có null hoặc đặc biệt

So `double` bằng phép `a < b ? -1 : a > b ? 1 : 0` sẽ coi nhiều trường hợp `NaN` là tương đương với giá trị khác, dẫn đến logic kỳ lạ. `Double.compare` có quy tắc rõ cho `NaN` và số âm không (`-0.0`); dùng `Comparator.comparingDouble` thường an toàn hơn cách so bằng các toán tử quan hệ tùy biến. Nếu domain muốn coi các giá trị đặc biệt tương đương theo cách riêng, hãy xác định quy tắc chuẩn hóa trước và kiểm tra toàn bộ hợp đồng.

## 11. Kiểm tra hợp đồng Comparator bằng các tập dữ liệu đại diện

Với comparator `cmp` và tập các giá trị có ý nghĩa, có thể kiểm tra các quan hệ bằng assertions hoặc unit test:

```java
// Minh họa mã kiểm tra đặt trong phương thức test, với cmp và
// List<Task> samples đã được thiết lập.
for (Task x : samples) {
    for (Task y : samples) {
        int xy = Integer.signum(cmp.compare(x, y));
        int yx = Integer.signum(cmp.compare(y, x));
        if (xy != -yx) {
            throw new AssertionError("Vi phạm đối xứng dấu");
        }
        for (Task z : samples) {
            int yz = Integer.signum(cmp.compare(y, z));
            int xz = Integer.signum(cmp.compare(x, z));
            if (xy > 0 && yz > 0 && xz <= 0) {
                throw new AssertionError("Vi phạm bắc cầu");
            }
            if (xy == 0 && xz != yz) {
                throw new AssertionError("Nhóm compare==0 không nhất quán");
            }
        }
    }
}
```

*Đây là đoạn minh họa **không độc lập**; cần có `Task`, `samples` và `cmp` để chạy. Vòng lặp ba tầng có chi phí `O(n³)`, chỉ phù hợp với tập mẫu nhỏ trong kiểm thử.* Nó kiểm tra đối xứng dấu, bắc cầu theo chiều lớn hơn, và nhất quán với phần tử thứ ba cho những mẫu đã cung cấp.

Một bộ ca hữu ích nên bao gồm: các giá trị bằng nhau theo comparator nhưng không `equals()`, các phần tử ở gần ranh giới giữa nhóm, thứ tự đảo chiều, giá trị `Integer.MIN_VALUE/MAX_VALUE` nếu so số, dữ liệu có `null` nếu được cho phép, chuỗi khác chữ hoa/thường, và các khóa của `TreeSet`/`TreeMap` sau khi thêm. Kiểm tra trên mẫu không phải chứng minh toán học cho toàn bộ miền đầu vào, nên thiết kế comparator bằng các thành phần thứ tự chuẩn vẫn rất quan trọng.

## 12. Tự kiểm tra

**Câu 1.** Comparator trả `-20` cho `compare(a,b)` và `5` cho `compare(b,a)` có vi phạm quy tắc dấu không?  
**Đáp án:** Không; dấu lần lượt âm và dương. Không yêu cầu trị tuyệt đối trùng nhau.

**Câu 2.** Nếu `compare(a,b)==0`, `compare(a,c)<0` nhưng `compare(b,c)>0`, comparator hợp lệ không?  
**Đáp án:** Không. Hai phần tử cùng nhóm 0 phải có cùng quan hệ dấu với mọi `c`.

**Câu 3.** Có thể dùng Comparator chỉ so `priority` với `List.sort` khi muốn giữ các tác vụ cùng ưu tiên theo thứ tự đầu vào không?  
**Đáp án:** Có, với `List.sort` ổn định. Chúng vẫn là các phần tử riêng trong list; đây không phải là phép gộp.

**Câu 4.** Với `TreeSet<Task>` dùng comparator chỉ xét priority, thêm hai task khác mã nhưng cùng priority thì `size()` tăng hai lần không?  
**Đáp án:** Không. Comparator trả 0 nên `TreeSet` xem chúng tương đương.

**Câu 5.** `Comparator` có bắt buộc `compare(x,y)==0` khi và chỉ khi `x.equals(y)` không?  
**Đáp án:** Không bắt buộc trong mọi mục đích, nhưng đây là tính nhất quán với equals rất đáng quan tâm khi dùng trong sorted set/map.

**Câu 6.** `a - b` là cách triển khai comparator cho `int` có luôn đúng không?  
**Đáp án:** Không, vì overflow. Dùng `Integer.compare(a,b)` hoặc comparator factory.

**Câu 7.** Vì sao comparator có chu trình `A < B < C < A` không thể dùng an toàn để sort?  
**Đáp án:** Nó vi phạm tính bắc cầu nên không có thứ tự tổng quát nhất quán để thuật toán sắp xếp duy trì.

**Câu 8.** Khi bổ sung `thenComparing` sau tiêu chí đầu, nhóm `compare == 0` thay đổi ra sao?  
**Đáp án:** Một nhóm theo tiêu chí đầu có thể được chia thành các nhóm nhỏ theo tiêu chí tiếp. Những cặp vẫn bằng nhau theo mọi tiêu chí mới tiếp tục có `compare == 0`.

**Điểm cần nhớ:** Comparator hợp lệ tuân thủ **đối xứng về dấu, tính bắc cầu và nhất quán của các nhóm có `compare == 0`**. Kết quả bằng 0 mô tả **tương đương theo quy tắc sắp xếp**, không mặc nhiên là `equals()`; hệ quả này đặc biệt quan trọng khi dùng comparator làm chính sách khóa của `TreeSet` và `TreeMap`.