# SortedSet, NavigableSet và thứ tự do comparator quyết định

Trong Java 21, `SortedSet` và `NavigableSet` biểu diễn tập hợp không trùng lặp có thứ tự được quyết định bởi natural ordering hoặc một `Comparator`. Khác với `LinkedHashSet`, thứ tự của chúng không dựa trên thời điểm chèn phần tử. Mỗi phần tử được đặt vào vị trí do quy tắc so sánh xác định.

Từ Java 21, `SortedSet` cũng là một `SequencedSet`. Vì vậy, sorted set có thể cung cấp góc nhìn theo thứ tự thuận hoặc đảo ngược, đồng thời vẫn giữ nguyên nguyên tắc sắp xếp. Đây là điểm cần nhớ khi sử dụng các API đầu/cuối: `addFirst()` và `addLast()` không thể tùy ý thay đổi vị trí trong một sorted set, vì làm vậy sẽ phá vỡ thứ tự do comparator quyết định.

## SortedSet và NavigableSet khác nhau thế nào?

`SortedSet` mở rộng `Set` và cung cấp thứ tự duyệt ổn định theo comparator. Nó có các thao tác cơ bản như lấy phần tử đầu/cuối và tạo các tập hợp con theo khoảng giá trị.

`NavigableSet` mở rộng `SortedSet`, bổ sung các thao tác tìm phần tử gần một giá trị cho trước và các biến thể tạo range view có thể chỉ định rõ biên bao gồm hay không.

| Interface | Khả năng chính | Khi phù hợp |
| --- | --- | --- |
| `Set` | Không cho phép phần tử trùng lặp theo quy tắc equality của implementation | Chỉ cần tính duy nhất, không cần thứ tự |
| `SortedSet` | Duyệt theo natural ordering hoặc comparator; lấy đầu/cuối; tạo range view | Cần thứ tự sắp xếp và thao tác khoảng cơ bản |
| `NavigableSet` | Có toàn bộ khả năng của `SortedSet`, thêm `lower`, `floor`, `ceiling`, `higher`, `pollFirst`, `pollLast` và range view có biên inclusive | Cần tìm phần tử lân cận hoặc điều hướng theo thứ tự |

`TreeSet` là một implementation phổ biến của `NavigableSet`. Trong Java 21, nó cũng là `SequencedSet`, nên có thể dùng các phương thức của những interface này thông qua kiểu tham chiếu phù hợp.

## Thứ tự được quyết định bởi natural ordering hoặc Comparator

Nếu không truyền comparator, sorted set sử dụng natural ordering của phần tử. Kiểu phần tử thường phải triển khai `Comparable`. Ví dụ, `Integer` được sắp xếp tăng dần theo giá trị:

```java
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> scores = new TreeSet<>();
scores.add(70);
scores.add(90);
scores.add(80);

System.out.println(scores); // [70, 80, 90]
```

Nếu cần quy tắc khác, truyền `Comparator` vào constructor. Ví dụ sau sắp xếp điểm giảm dần:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> scores = new TreeSet<>(Comparator.<Integer>reverseOrder());
scores.addAll(List.of(70, 90, 80));

System.out.println(scores); // [90, 80, 70]
System.out.println(scores.first()); // 90
System.out.println(scores.last());  // 70
```

`first()` và `last()` luôn được hiểu theo thứ tự của sorted set. Khi dùng comparator đảo ngược, phần tử đầu tiên là phần tử đứng trước theo comparator, nên không nhất thiết là giá trị nhỏ nhất theo thứ tự tự nhiên.

Với comparator tùy chỉnh, kết quả so sánh có ý nghĩa như sau:

- Giá trị âm: phần tử thứ nhất đứng trước phần tử thứ hai.
- Giá trị `0`: hai phần tử được xem là cùng một vị trí theo thứ tự của sorted set.
- Giá trị dương: phần tử thứ nhất đứng sau phần tử thứ hai.

Ví dụ, có thể sắp xếp tên theo độ dài trước, rồi theo thứ tự chữ cái để phân biệt các tên cùng độ dài:

```java
import java.util.Comparator;
import java.util.List;
import java.util.SortedSet;
import java.util.TreeSet;

Comparator<String> byLengthThenName =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());

SortedSet<String> names = new TreeSet<>(byLengthThenName);
names.addAll(List.of("Lan", "An", "Binh", "Chi"));

System.out.println(names); // [An, Chi, Lan, Binh]
```

Comparator là một phần của quy tắc dữ liệu, không chỉ là cách trình bày. Thay đổi comparator có thể làm thay đổi vị trí phần tử, kết quả tìm kiếm, range view và cả việc hai giá trị có bị xem là trùng nhau hay không.

## Quan hệ giữa Comparator và tính duy nhất của Set

Với `TreeSet`, hai phần tử được xem là trùng nhau nếu comparator trả về `0` khi so sánh chúng. Điều này có thể khác với `equals()`.

Ví dụ, `BigDecimal.compareTo()` xem `4.0` và `4.00` có cùng giá trị số, nhưng `BigDecimal.equals()` xem chúng khác nhau vì scale khác nhau:

```java
import java.math.BigDecimal;
import java.util.TreeSet;

var values = new TreeSet<BigDecimal>();
values.add(new BigDecimal("4.0"));
values.add(new BigDecimal("4.00"));

System.out.println(values.size()); // 1
System.out.println(values.first()); // 4.0
```

Sorted set chỉ giữ một phần tử vì natural ordering của `BigDecimal` trả về `0` cho hai giá trị này. Đây là hành vi đúng theo quy tắc sắp xếp của `TreeSet`, nhưng comparator không nhất quán với `equals()` nên cách dùng này không tuân thủ đầy đủ hợp đồng tổng quát của `Set`.

Nếu ứng dụng cần giữ cả hai biểu diễn, hãy bổ sung tiêu chí phân biệt vào comparator hoặc dùng một collection khác phù hợp. Với chuỗi, chẳng hạn comparator không phân biệt hoa thường có thể gom `"An"` và `"AN"` thành cùng một phần tử. Có thể thêm tie-breaker để phân biệt chúng:

```java
import java.util.Comparator;
import java.util.TreeSet;

Comparator<String> caseInsensitiveThenExact =
        String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder());

var names = new TreeSet<>(caseInsensitiveThenExact);
names.add("An");
names.add("AN");

System.out.println(names.size()); // 2
```

Hãy ưu tiên comparator nhất quán với `equals()` khi sorted set được sử dụng như một `Set` thông thường. Comparator cũng cần có thứ tự nhất quán, có tính bắc cầu và không thay đổi hành vi trong khi các phần tử đang được lưu trong cây. Không sửa các trường dùng để so sánh của phần tử khi chúng đang nằm trong `TreeSet`, vì cấu trúc cây không tự sắp xếp lại sau thay đổi đó.

## Các thao tác điều hướng của NavigableSet

`NavigableSet` cung cấp bốn thao tác tìm phần tử gần một giá trị:

| Phương thức | Ý nghĩa với thứ tự comparator |
| --- | --- |
| `lower(e)` | Phần tử lớn nhất đứng trước `e` |
| `floor(e)` | Phần tử lớn nhất đứng trước hoặc bằng `e` |
| `ceiling(e)` | Phần tử nhỏ nhất đứng sau hoặc bằng `e` |
| `higher(e)` | Phần tử nhỏ nhất đứng sau `e` |

Ví dụ với thứ tự số tự nhiên:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> numbers = new TreeSet<>(
        List.of(10, 20, 30, 40, 50));

System.out.println(numbers.lower(30));   // 20
System.out.println(numbers.floor(30));   // 30
System.out.println(numbers.ceiling(31)); // 40
System.out.println(numbers.higher(30));  // 40
```

Nếu không có phần tử thỏa mãn, các phương thức này trả về `null`. Nếu cần lấy và đồng thời loại bỏ phần tử ở đầu hoặc cuối theo thứ tự hiện tại, dùng `pollFirst()` hoặc `pollLast()`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> numbers = new TreeSet<>(List.of(10, 20, 30));

System.out.println(numbers.pollFirst()); // 10
System.out.println(numbers.pollLast());  // 30
System.out.println(numbers);             // [20]
```

Đầu và cuối ở đây vẫn dựa trên comparator. Với comparator đảo ngược, `pollFirst()` lấy phần tử đứng đầu theo thứ tự đảo ngược.

## Tạo tập hợp con theo khoảng giá trị

`SortedSet` có `subSet(from, to)`, `headSet(to)` và `tailSet(from)`. Theo hợp đồng của `SortedSet`, `subSet(from, to)` bao gồm biên dưới và loại trừ biên trên; `headSet(to)` loại trừ biên trên; `tailSet(from)` bao gồm biên dưới.

`NavigableSet` bổ sung overload cho phép chỉ định rõ mỗi biên có được bao gồm hay không:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> numbers = new TreeSet<>(
        List.of(10, 20, 30, 40, 50));

NavigableSet<Integer> range = numbers.subSet(20, true, 40, false);
System.out.println(range); // [20, 30]

NavigableSet<Integer> upToThirty = numbers.headSet(30, true);
System.out.println(upToThirty); // [10, 20, 30]

NavigableSet<Integer> fromThirty = numbers.tailSet(30, false);
System.out.println(fromThirty); // [40, 50]
```

Các tập hợp con này là view có liên kết với tập hợp gốc, không phải bản sao độc lập. Thay đổi qua view được phản ánh ở tập hợp gốc nếu thao tác nằm trong phạm vi hợp lệ; thay đổi trên tập hợp gốc cũng được nhìn thấy qua view. Thử thêm một phần tử nằm ngoài khoảng vào view có thể ném `IllegalArgumentException`.

Các biên của range luôn được hiểu theo thứ tự của comparator. Với comparator đảo ngược, khoảng `subSet(from, ..., to, ...)` cũng phải được xác định theo chiều đảo ngược đó; nếu `from` đứng sau `to` theo comparator, lời gọi sẽ không hợp lệ.

Nếu cần dữ liệu độc lập, hãy sao chép các phần tử từ view sang một collection khác. Đừng giữ view lâu hơn phạm vi mà quy tắc biên của nó còn phù hợp với logic ứng dụng.

## SortedSet trong Java 21 là SequencedSet, nhưng không cho phép tự đặt đầu/cuối

Java 21 đưa các collection có thứ tự vào cùng mô hình `SequencedCollection`. `SortedSet` mở rộng `SequencedSet`, nên có thể dùng các phương thức như `getFirst()`, `getLast()` và `reversed()` bên cạnh các API sắp xếp đã có.

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> numbers = new TreeSet<>(List.of(10, 20, 30));

System.out.println(numbers.getFirst()); // 10
System.out.println(numbers.getLast());  // 30
System.out.println(numbers.reversed()); // [30, 20, 10]
```

`reversed()` trả về view theo thứ tự đảo ngược, không tạo một cây mới độc lập. Comparator của view đảo ngược cũng phản ánh chiều sắp xếp ngược lại. Thay đổi hợp lệ qua view được phản ánh trong tập hợp gốc.

Tuy nhiên, `SortedSet` không cho phép tùy ý chèn một phần tử vào đầu hoặc cuối bằng `addFirst()` hay `addLast()`. Các phương thức này ném `UnsupportedOperationException` vì vị trí phần tử phải do natural ordering hoặc comparator quyết định. `TreeSet` cũng tuân theo quy tắc đó.

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

NavigableSet<Integer> numbers = new TreeSet<>(List.of(10, 20, 30));

numbers.add(25); // Hợp lệ: 25 được đặt theo thứ tự comparator.
// Mỗi lời gọi sau, nếu chạy riêng, đều ném UnsupportedOperationException:
// numbers.addFirst(5);
// numbers.addLast(40);
```

Ngay cả khi giá trị `5` hiện là nhỏ nhất hoặc `40` hiện là lớn nhất, không nên dùng thao tác định vị ở hai đầu. Sorted set bảo đảm vị trí bằng comparator, vì vậy hãy dùng `add()` và để cấu trúc tự xác định vị trí. Nếu nghiệp vụ yêu cầu thay đổi thứ tự thủ công theo lần truy cập hoặc cập nhật, hãy cân nhắc `LinkedHashSet` thay vì `TreeSet`.

## Null và comparator

Với natural ordering, `TreeSet` không thể so sánh `null` và thường ném `NullPointerException` khi thêm giá trị này. Một comparator tùy chỉnh có thể định nghĩa cách sắp xếp `null`, nhưng chỉ nên làm vậy nếu `null` thực sự là một giá trị hợp lệ trong mô hình. Dù comparator hỗ trợ `null`, các phương thức điều hướng trả về `null` khi không tìm thấy phần tử, nên kết quả `null` có thể gây khó phân biệt giữa một phần tử null và trường hợp không có kết quả. Trong nhiều ứng dụng, từ chối `null` ở đầu vào là lựa chọn rõ ràng hơn.

## Khi nào nên chọn SortedSet hoặc NavigableSet?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Chỉ cần loại bỏ trùng lặp, không cần thứ tự | `HashSet` |
| Cần duyệt theo thứ tự chèn và di chuyển phần tử ở hai đầu | `LinkedHashSet` / `SequencedSet` |
| Cần loại bỏ trùng lặp và sắp xếp theo comparator | `SortedSet`, thường dùng `TreeSet` |
| Cần tìm phần tử lân cận, lấy phần tử thấp/cao hoặc tạo khoảng inclusive | `NavigableSet` |
| Cần phần tử trùng lặp hoặc truy cập theo chỉ số | `List` |

Hãy chọn sorted set khi thứ tự là thuộc tính của dữ liệu, ví dụ xếp hạng, mốc thời gian hoặc mã được sắp theo quy tắc nghiệp vụ. Nếu thứ tự chỉ phản ánh lần thêm hoặc lần cập nhật gần nhất, một sequenced set dựa trên thứ tự chèn thường phù hợp hơn.

## Quy trình áp dụng trong dự án Java 21

1. **Xác định ý nghĩa của thứ tự.** Thứ tự có do comparator quyết định hay do thời điểm chèn/cập nhật?
2. **Chọn interface.** Dùng `SortedSet` cho thứ tự và range cơ bản; dùng `NavigableSet` nếu cần tìm phần tử lân cận hoặc thao tác biên chi tiết.
3. **Chọn comparator.** Xác định natural ordering hay comparator tùy chỉnh; dùng `thenComparing()` nếu cần tie-breaker.
4. **Kiểm tra equality.** Bảo đảm comparator không vô tình coi hai đối tượng khác nhau theo `equals()` là cùng một phần tử, trừ khi đó là quy tắc nghiệp vụ có chủ đích.
5. **Sử dụng range view cẩn thận.** Nhớ rằng `subSet`, `headSet`, `tailSet` và `reversed()` trả về view liên kết với tập hợp gốc.
6. **Không cố định vị trí thủ công.** Với sorted set, dùng `add()`; `addFirst()` và `addLast()` không được hỗ trợ vì comparator quyết định vị trí.
7. **Biên dịch theo Java 21.** `SortedSet` là `SequencedSet` từ Java 21, cho phép dùng `getFirst()`, `getLast()` và `reversed()` cùng các API sắp xếp hiện có.

`SortedSet` và `NavigableSet` phù hợp khi thứ tự của phần tử phải phản ánh một quy tắc so sánh nhất quán. Java 21 kết hợp chúng với mô hình Sequenced Collections để cung cấp góc nhìn đầu, cuối và đảo ngược thống nhất. Tuy vậy, thứ tự vẫn do comparator quyết định; hãy dùng `add()` để chèn phần tử và chỉ dùng `addFirst()`/`addLast()` với những sequenced set cho phép điều khiển vị trí.
