# Phân biệt `filter()` với `takeWhile()` trong Java Stream

Hai thao tác trung gian `filter()` và `takeWhile()` đều nhận một `Predicate<T>` để kiểm tra từng phần tử của stream và đều trả lại `Stream<T>`. Khác biệt quyết định nằm ở **phạm vi lấy phần tử**:

- **`filter(predicate)`**: giữ **mọi phần tử thỏa điều kiện** trong stream. Một phần tử không thỏa điều kiện không làm `filter` ngừng xét những phần tử phía sau.
- **`takeWhile(predicate)`**: trên **stream có encounter order**, chỉ giữ **đoạn liên tiếp dài nhất từ đầu** mà tất cả phần tử đều thỏa điều kiện. Gặp phần tử đầu tiên không thỏa điều kiện, `takeWhile` kết thúc đoạn được lấy; những phần tử phía sau không nằm trong kết quả, kể cả khi chúng thỏa điều kiện.
- Trên **stream không có encounter order**, `takeWhile` không có khái niệm “đoạn đầu” cố định; API cho phép chọn một tập con bất kỳ của các phần tử thỏa predicate, nên không nên dùng nó để diễn đạt việc lấy tiền tố theo thứ tự.

`filter` có từ Java 8; `takeWhile` được bổ sung cho `Stream`, `IntStream`, `LongStream` và `DoubleStream` từ **Java 9**. Tất cả ví dụ dưới đây chạy với **Java 17 trở lên**.

## 1. Ví dụ trực quan: điều kiện đúng lại ở phía sau

Xét dãy có thứ tự:

~~~text
Giá trị:       2    4    7    8    10    3    12
Là số chẵn?    ✓    ✓    ✗    ✓     ✓    ✗     ✓

filter(chẵn)       → [2, 4, 8, 10, 12]
takeWhile(chẵn)    → [2, 4]
~~~

`filter` xét điều kiện cho các phần tử ở mọi vị trí cần thiết để thu được kết quả. `takeWhile` chỉ lấy `2` và `4` vì `7` là **phần tử đầu tiên không thỏa điều kiện**. Việc `8`, `10` và `12` chẵn không làm chúng xuất hiện trở lại sau `7`.

Tạo file `FilterTakeWhileDemo.java`:

~~~java
import java.util.List;

public class FilterTakeWhileDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 4, 7, 8, 10, 3, 12);

        List<Integer> filtered = numbers.stream()
                .filter(n -> n % 2 == 0)
                .toList();

        List<Integer> prefix = numbers.stream()
                .takeWhile(n -> n % 2 == 0)
                .toList();

        List<Integer> remainder = numbers.stream()
                .dropWhile(n -> n % 2 == 0)
                .toList();

        System.out.println("filter=" + filtered);
        System.out.println("takeWhile=" + prefix);
        System.out.println("dropWhile=" + remainder);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 FilterTakeWhileDemo.java
java FilterTakeWhileDemo
~~~

Kết quả:

~~~text
filter=[2, 4, 8, 10, 12]
takeWhile=[2, 4]
dropWhile=[7, 8, 10, 3, 12]
~~~

`dropWhile` được nêu để đối chiếu: với ordered stream, nó **bỏ đoạn đầu thỏa predicate**, sau đó giữ toàn bộ phần còn lại (kể cả những phần tử thỏa predicate ở phía sau). Vì vậy `takeWhile` và `dropWhile` có thể chia một nguồn có thứ tự thành **tiền tố** và **phần dư**, còn `filter` phân loại theo điều kiện trên toàn bộ nguồn.

## 2. Đọc chữ ký: cả hai không đổi kiểu phần tử

Hai phương thức trong `Stream<T>` có thể hình dung như sau:

~~~java
// Chữ ký API minh họa, không phải lớp Java độc lập:
Stream<T> filter(Predicate<? super T> predicate);
Stream<T> takeWhile(Predicate<? super T> predicate);
~~~

Một `Predicate<T>` có phép thử `boolean test(T value)`. Cả hai phương thức nhận hành vi `T -> boolean` và vẫn trả một `Stream<T>`. Do đó, với `Stream<Order>`, phần tử trong stream sau `filter` hoặc `takeWhile` **vẫn là `Order`**; muốn chuyển sang `String`, `int` hay DTO thì dùng `map` hoặc `mapToInt` ở bước khác.

Ví dụ kiểu tĩnh:

~~~java
// Minh họa nằm trong một phương thức, đã có orders: List<Order>
Stream<Order> source = orders.stream();
Stream<Order> selected = source.filter(o -> o.amount() > 100);
// Hoặc trên một stream mới:
Stream<Order> prefix = orders.stream().takeWhile(o -> o.amount() > 100);
~~~

Lưu ý một `Stream` chỉ được dùng cho một pipeline: không gọi cả `filter` và `takeWhile` trên **cùng instance đã nối/tiêu thụ** để so sánh; hãy tạo hai stream độc lập từ nguồn như chương trình ở mục 1.

## 3. Khác biệt quan trọng: vị trí của phần tử không thỏa

Với stream có thứ tự gặp (*encounter order*), `takeWhile` phụ thuộc **vị trí**, không chỉ giá trị:

| Đầu vào | Predicate | `filter` | `takeWhile` |
| --- | --- | --- | --- |
| `[1, 2, 3, 4]` | `n < 3` | `[1, 2]` | `[1, 2]` |
| `[1, 4, 2, 5]` | `n < 3` | `[1, 2]` | `[1]` |
| `[4, 1, 2]` | `n < 3` | `[1, 2]` | `[]` |
| `[1, 2, 3]` | `n > 5` | `[]` | `[]` |
| `[1, 2, 3]` | `n > 0` | `[1, 2, 3]` | `[1, 2, 3]` |
| `[]` | Bất kỳ predicate hợp lệ | `[]` | `[]` |

Hai thao tác chỉ cho ra cùng kết quả khi **mọi phần tử thỏa predicate nằm trước mọi phần tử không thỏa** trong thứ tự mà stream đang xử lý, hoặc thuộc trường hợp đặc biệt toàn bộ đúng/toàn bộ sai/trống. Nếu một phần tử đúng xuất hiện sau phần tử sai đầu tiên, `filter` vẫn có thể giữ nó, còn `takeWhile` thì không.

Sơ đồ dưới đây cho thấy hai cách tiếp cận:

~~~text
Ordered stream: [A✓, B✓, C✗, D✓, E✓]

filter(p)     → [A, B, D, E]
takeWhile(p)  → [A, B]
                        ↑
                dừng lấy tại C✗
~~~

**Dấu dừng trên là mô hình kết quả/tiền tố của ordered stream.** Cách thực thi và số lượt gọi predicate thực tế có thể thay đổi theo nguồn, terminal operation, tối ưu hóa và đặc biệt khi thực thi song song; không đặt logic nghiệp vụ trong side effect của predicate.

## 4. Encounter order quyết định ý nghĩa `takeWhile`

Các nguồn như `List`, `ArrayList`, `IntStream.range(...)` hoặc `Stream.of(...)` thường có encounter order xác định. Với ordered stream, `takeWhile` giữ **longest prefix** phù hợp điều kiện và bảo toàn thứ tự các phần tử được lấy.

Trái lại, `HashSet.stream()` không bảo đảm encounter order; `unordered()` cũng loại bỏ ràng buộc thứ tự của pipeline. Trên một stream **unordered**, `takeWhile` có quyền chọn **bất kỳ tập con** các phần tử phù hợp predicate. Không thể dự đoán chính xác tập con nào, cũng không có cơ sở nói “gặp phần tử đầu tiên không phù hợp” theo một thứ tự nghiệp vụ cố định.

~~~java
// Minh họa: không dựa vào kết quả cụ thể của nhánh unordered().
java.util.stream.Stream.of(1, 2, 8, 3, 4)
        .unordered()
        .takeWhile(n -> n < 5)
        .forEach(System.out::println);
~~~

Các giá trị xuất hiện, nếu có, phải thỏa `n < 5`; **không có bảo đảm** kết quả đúng `[1, 2]` hoặc là toàn bộ `[1, 2, 3, 4]`. Nếu ứng dụng cần tiền tố theo thứ tự, cần một nguồn/pipeline giữ encounter order và không gọi `unordered()`.

Với `filter`, unordered stream không làm mất ý nghĩa **chọn tất cả phần tử thỏa predicate** trong một phép tiêu thụ đầy đủ, nhưng thứ tự đầu ra có thể không được bảo đảm. Với terminal operation short-circuit (như `findAny`), pipeline có thể không tiêu thụ hết nguồn; đừng suy từ lần chạy không đầy đủ rằng `filter` đã xét toàn bộ các phần tử.

## 5. `takeWhile` cần dữ liệu có ý nghĩa tiền tố

Nghiệp vụ đúng cho `takeWhile` thường mang dạng: “lấy từ đầu cho đến khi gặp dấu mốc không còn thỏa điều kiện”.

Ví dụ phù hợp:

- Lấy chuỗi sự kiện đã xếp theo timestamp cho tới trước thời điểm cutoff.
- Đọc một dãy tăng dần và dừng tại ngưỡng.
- Lấy các dòng liên tiếp đầu tài liệu khi chúng còn là dòng header.
- Lấy các bản ghi đã sắp theo thứ tự ưu tiên cho tới khi độ ưu tiên thấp hơn ngưỡng.

Ví dụ **không phù hợp** nếu dữ liệu có thể thay đổi thứ tự hoặc xen kẽ giá trị:

- Chọn tất cả đơn hàng có tổng tiền từ 100 trở lên trong dữ liệu chưa sắp xếp.
- Chọn tất cả người dùng đang active trong một danh sách trộn active/inactive.
- Chọn tất cả phần tử khác null bất kể vị trí.

Ở các tình huống thứ hai, **`filter`** mới thể hiện đúng yêu cầu “tìm mọi phần tử đạt điều kiện”. `takeWhile` có thể âm thầm bỏ sót các phần tử hợp lệ ở sau phần tử đầu tiên không phù hợp.

## 6. Ví dụ nghiệp vụ: sắp xếp trước khi lấy tiền tố

Giả sử yêu cầu là “lấy mọi đơn hàng có điểm ưu tiên từ 50 trở lên”. Trên dữ liệu không sắp xếp, `takeWhile` không thay thế `filter`.

Tạo file `PriorityPipelineDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;

public class PriorityPipelineDemo {
    record Order(String id, int priority) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 90),
                new Order("B", 30),
                new Order("C", 75),
                new Order("D", 60)
        );

        List<String> filtered = orders.stream()
                .filter(o -> o.priority() >= 50)
                .map(Order::id)
                .toList();

        List<String> prefixBeforeSort = orders.stream()
                .takeWhile(o -> o.priority() >= 50)
                .map(Order::id)
                .toList();

        List<String> prefixAfterSort = orders.stream()
                .sorted(Comparator.comparingInt(Order::priority).reversed())
                .takeWhile(o -> o.priority() >= 50)
                .map(Order::id)
                .toList();

        System.out.println("filter=" + filtered);
        System.out.println("takeWhile original=" + prefixBeforeSort);
        System.out.println("takeWhile sorted=" + prefixAfterSort);
    }
}
~~~

~~~bash
javac --release 17 PriorityPipelineDemo.java
java PriorityPipelineDemo
~~~

Kết quả:

~~~text
filter=[A, C, D]
takeWhile original=[A]
takeWhile sorted=[A, C, D]
~~~

Tại phiên bản đã sắp xếp giảm dần, tất cả điểm lớn hơn hoặc bằng 50 nằm ở đầu; vì thế `takeWhile` có cùng **tập kết quả** với `filter` trong dữ liệu này. Tuy nhiên `sorted` thay đổi thứ tự đầu ra (và thường cần xử lý toàn bộ dữ liệu trước khi cấp phần tử), nên không được thêm `sorted` chỉ để khiến `takeWhile` trông giống `filter` nếu nghiệp vụ không cho phép đổi thứ tự.

## 7. `takeWhile` với nguồn vô hạn và thao tác dừng sớm

Trên một nguồn **có thứ tự và vô hạn**, `takeWhile` đặc biệt hữu ích nếu predicate có một **ngưỡng kết thúc thật sự sẽ được gặp**.

Tạo file `InfiniteStreamTakeWhileDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class InfiniteStreamTakeWhileDemo {
    public static void main(String[] args) {
        List<Integer> firstFive = IntStream.iterate(0, n -> n + 1)
                .takeWhile(n -> n < 5)
                .boxed()
                .toList();

        List<Integer> alsoFive = IntStream.iterate(0, n -> n + 1)
                .filter(n -> n < 5)
                .limit(5)
                .boxed()
                .toList();

        System.out.println("takeWhile=" + firstFive);
        System.out.println("filter and limit=" + alsoFive);
    }
}
~~~

~~~bash
javac --release 17 InfiniteStreamTakeWhileDemo.java
java InfiniteStreamTakeWhileDemo
~~~

Kết quả:

~~~text
takeWhile=[0, 1, 2, 3, 4]
filter and limit=[0, 1, 2, 3, 4]
~~~

Giải thích:

- `IntStream.iterate(0, n -> n + 1)` tạo dãy số tăng không có giới hạn kết thúc đã khai báo; ở phần đầu là 0, 1, 2, ...
- `takeWhile(n -> n < 5)` chọn tiền tố 0..4 và dừng khi đến 5, nên `toList()` hoàn tất.
- `filter(n -> n < 5).limit(5)` lấy năm phần tử phù hợp rồi dừng nhờ **`limit(5)`**, không phải nhờ `filter`.
- Nếu bỏ `limit(5)` và gọi terminal thu toàn bộ sau `filter(n -> n < 5)` trên dãy tăng vô hạn này, pipeline sẽ tiếp tục tìm phần tử phù hợp mà không có điểm kết thúc hữu hạn được bảo đảm. **Đừng chạy trường hợp đó chỉ để thử nghiệm**.

Không nên kết luận “có `takeWhile` thì mọi infinite stream đều kết thúc”: nếu predicate **luôn đúng**, stream có thể vẫn vô hạn; nếu predicate không có đặc tính đơn điệu, `takeWhile` sẽ dừng ngay tại lần sai đầu tiên, có thể bỏ nhiều giá trị đúng sau này.

## 8. Lazy evaluation và số lần gọi predicate

Cả `filter` và `takeWhile` là **intermediate operation**. Chúng tạo pipeline lazy; xử lý thực tế thường bắt đầu khi có terminal operation như `toList()`, `count()`, `forEach()`, `findFirst()` hoặc `anyMatch()`.

Ví dụ có in log khi predicate được đánh giá trong một stream tuần tự. File `PredicateTraceDemo.java`:

~~~java
import java.util.List;

public class PredicateTraceDemo {
    public static void main(String[] args) {
        List<Integer> input = List.of(2, 4, 7, 8);

        System.out.println("filter:");
        List<Integer> filtered = input.stream()
                .filter(n -> {
                    System.out.println("check " + n);
                    return n % 2 == 0;
                })
                .toList();
        System.out.println("result=" + filtered);

        System.out.println("takeWhile:");
        List<Integer> taken = input.stream()
                .takeWhile(n -> {
                    System.out.println("check " + n);
                    return n % 2 == 0;
                })
                .toList();
        System.out.println("result=" + taken);
    }
}
~~~

~~~bash
javac --release 17 PredicateTraceDemo.java
java PredicateTraceDemo
~~~

Kết quả trên pipeline tuần tự cụ thể này:

~~~text
filter:
check 2
check 4
check 7
check 8
result=[2, 4, 8]
takeWhile:
check 2
check 4
check 7
result=[2, 4]
~~~

Điểm cần hiểu là `takeWhile` có thể cắt một pipeline tuần tự sau lần sai đầu tiên, còn `filter` cần tiếp tục nếu terminal operation cần thu mọi phần tử hợp lệ. **Không viết chương trình phụ thuộc vào thứ tự hoặc số lượng callback được gọi**: với stream song song, nguồn khác, `limit`, `findAny`, `count` hay tối ưu hóa của JDK, việc đánh giá có thể khác. `Predicate` nên không có side effect, không phụ thuộc bộ đếm mutable hoặc trạng thái có thể thay đổi trong lúc chạy.

## 9. Stream song song và hiệu năng

Lợi ích về công việc phải làm của `takeWhile` phụ thuộc vào đặc tính nguồn và yêu cầu thứ tự:

| Tình huống | `filter` | `takeWhile` |
| --- | --- | --- |
| Finite ordered stream, cần toàn bộ kết quả | Thường phải xét toàn bộ dữ liệu để thu mọi phần tử hợp lệ. | Có khả năng dừng sau tiền tố đầu tiên bị cắt. |
| Ordered stream lớn chạy parallel | Các phần dữ liệu có thể được xử lý song song. | Giữ ràng buộc *longest prefix* có thể yêu cầu phối hợp nhiều tác vụ, đôi khi tốn chi phí đáng kể. |
| Unordered stream | Chọn phần tử theo predicate, không bảo đảm thứ tự đầu ra. | Có thể chọn tập con bất kỳ của phần tử phù hợp; không có ngữ nghĩa tiền tố cố định. |
| Infinite ordered stream với cutoff đạt được | Cần thêm cách kết thúc như `limit` hoặc terminal dừng sớm. | Có thể làm nguồn vô hạn thành pipeline hữu hạn nếu sẽ gặp một phần tử sai. |
| Kết quả chỉ cần phần tử đầu hợp lệ | `filter(...).findFirst()` có thể dừng sớm. | `takeWhile(...).findFirst()` trả phần tử đầu nếu nó thỏa, nếu không thì empty; không tìm qua phần tử sai đầu. |

`takeWhile` không có bảo đảm luôn **nhanh hơn** `filter`. Với `parallel()` và ordered stream, `takeWhile` có thể tốn công duy trì giới hạn tiền tố; `filter` lại phù hợp việc xử lý độc lập từng phần tử hơn. Nếu cần tối ưu hiệu năng, đo bằng benchmark trên nguồn dữ liệu và terminal operation thực tế, tránh dựa vào số lần in log của predicate.

Nếu xử lý nguồn vốn không có thứ tự mà chỉ cần các phần tử thỏa điều kiện, `filter` thường biểu đạt yêu cầu rõ ràng hơn; không thêm `unordered()` vào `takeWhile` để “tăng tốc” khi nghiệp vụ yêu cầu giữ tiền tố theo thứ tự.

## 10. Phân biệt `takeWhile` với `limit`, `dropWhile` và `skip`

| Phương thức | Điều kiện giữ/bỏ | Kết quả trên ordered stream |
| --- | --- | --- |
| `filter(p)` | Giữ mọi phần tử thỏa `p`. | Các phần tử thỏa điều kiện ở mọi vị trí. |
| `takeWhile(p)` | Giữ tới ngay trước phần tử đầu tiên không thỏa `p`. | Tiền tố liên tiếp dài nhất thỏa `p`. |
| `dropWhile(p)` | Bỏ tiền tố liên tiếp dài nhất thỏa `p`. | Toàn bộ phần dư bắt đầu từ phần tử không thỏa đầu tiên. |
| `limit(n)` | Giữ tối đa `n` phần tử. | Tiền tố theo **số lượng**, không dùng predicate. |
| `skip(n)` | Bỏ `n` phần tử đầu. | Phần dư theo **số lượng**, không dùng predicate. |

Ví dụ nguồn `[1, 2, 9, 3, 4]` với `p(n) = n < 5`:

~~~text
filter(p)       → [1, 2, 3, 4]
takeWhile(p)    → [1, 2]
dropWhile(p)    → [9, 3, 4]
limit(2)        → [1, 2]
skip(2)         → [9, 3, 4]
~~~

Kết quả `limit(2)` tình cờ giống `takeWhile(p)` trong ví dụ, nhưng bản chất khác: nếu tiền tố đạt điều kiện dài 4 phần tử, `takeWhile` lấy 4 còn `limit(2)` chỉ lấy 2.

Với `dropWhile` trên unordered stream, tương tự `takeWhile`, kết quả không nên được diễn giải theo một tiền tố xác định. Nếu cần tách “phần đầu” và “phần còn lại”, hãy xác định encounter order của nguồn.

## 11. Thứ tự phép biến đổi trong pipeline rất quan trọng

Xét:

~~~java
// Giả sử source: Stream<Integer>.
source.filter(n -> n % 2 == 0).takeWhile(n -> n < 8);
~~~

Theo ví dụ nguồn `[2, 4, 7, 8, 10, 3, 12]`, `filter` trước sẽ tạo dãy hợp lệ `[2, 4, 8, 10, 12]`; `takeWhile(n < 8)` sau đó lấy `[2, 4]`.

Nhưng đổi thứ tự:

~~~java
source.takeWhile(n -> n < 8).filter(n -> n % 2 == 0);
~~~

`takeWhile(n < 8)` trên nguồn ban đầu lấy `[2, 4, 7]` rồi `filter` giữ `[2, 4]`. Trong dữ liệu này hai kết quả giống nhau, nhưng **không suy ra hai phép toán luôn hoán đổi được**.

Phản ví dụ rõ hơn với `[2, 9, 4, 6]`:

~~~text
filter(chẵn) → takeWhile(n < 8)
[2, 9, 4, 6] → [2, 4, 6] → [2, 4, 6]

takeWhile(n < 8) → filter(chẵn)
[2, 9, 4, 6] → [2] → [2]
~~~

`filter` đã loại phần tử 9 trước khi `takeWhile` được áp dụng trong nhánh đầu, nên nhánh đó tiếp tục được sang 4 và 6. Với nhánh sau, số 9 là điều kiện dừng tại thời điểm `takeWhile` chạy. Thứ tự bước trong pipeline là một phần của yêu cầu nghiệp vụ.

## 12. Giá trị null trong stream

Khi stream chứa giá trị `null`, cần phân biệt hai ý nghĩa:

~~~java
// Ví dụ độc lập với List.of: dùng Stream.of vì List.of không cho null.
java.util.stream.Stream.of("A", null, "B")
        .filter(java.util.Objects::nonNull)
        .toList();   // [A, B]

java.util.stream.Stream.of("A", null, "B")
        .takeWhile(java.util.Objects::nonNull)
        .toList();   // [A]
~~~

`filter(Objects::nonNull)` dùng để **loại bỏ mọi phần tử null** khỏi stream khi cần thu hết; `takeWhile(Objects::nonNull)` chỉ lấy **đoạn liên tiếp đầu tiên chưa gặp null**. Một phần tử null ở giữa trở thành dấu dừng, nên phần tử `"B"` phía sau bị bỏ khỏi kết quả.

Đây là hai ý nghĩa khác nhau: “loại tất cả null” và “đọc đến dấu phân cách null”. Nếu predicate tự gọi method của phần tử, ví dụ `s -> s.length() > 2`, phần tử null có thể ném `NullPointerException`; cần kiểm tra null trước hoặc dùng predicate null-safe theo đúng yêu cầu.

## 13. Sai lầm thường gặp

1. **Dùng `takeWhile` thay `filter` để lấy mọi phần tử hợp lệ.** `takeWhile` dừng tiền tố ở phần tử sai đầu tiên, bỏ cả các phần tử đúng phía sau.
2. **Tin vào thứ tự của `HashSet` hoặc pipeline `unordered()`.** `takeWhile` không thể được diễn giải theo tiền tố đã định nếu thiếu encounter order.
3. **Đặt `takeWhile` trước/sau `sorted` mà không xem lại ý nghĩa.** `sorted` thay đổi thứ tự và có thể khiến tập được lấy thay đổi, đồng thời thêm chi phí.
4. **Tưởng `takeWhile` thay đổi kiểu phần tử.** Cả hai đều trả `Stream<T>`; chỉ các bước như `map`/ `mapToInt` mới biến đổi phần tử/kiểu.
5. **Cho rằng `filter` tự làm nguồn vô hạn kết thúc.** Chỉ lọc phần tử không tạo dấu hết nguồn; muốn terminal thu hết phải có một cách kết thúc.
6. **Dựa vào số lần gọi predicate để thay đổi trạng thái.** Side effect có thể gây hành vi khác khi đổi terminal, thứ tự hay chạy parallel.
7. **Quên `takeWhile` có từ Java 9.** Dự án biên dịch với Java 8 không có API này; ví dụ dùng Java 17+.
8. **So sánh hiệu năng chỉ từ số phần tử kết quả.** Một pipeline có thể phải xử lý nhiều phần tử hoặc sắp xếp trước; chi phí phụ thuộc source, order, terminal và parallel.
9. **Lẫn `takeWhile` với `dropWhile`.** Một phương thức giữ tiền tố, phương thức kia bỏ tiền tố; cả hai xác định ranh giới dựa vào predicate trong ordered stream.
10. **Dùng `takeWhile(Objects::nonNull)` để loại mọi null.** Cách này cắt phần sau null đầu tiên; muốn loại null ở mọi vị trí cần `filter(Objects::nonNull)`.

## 14. Checklist chọn đúng API

Trước khi đặt `filter` hay `takeWhile` vào pipeline, hãy trả lời:

- Mục tiêu là **mọi phần tử thỏa điều kiện** hay **chỉ đoạn liên tiếp ở đầu**?
- Nguồn có encounter order được bảo đảm không?
- Một phần tử không đạt có thể xuất hiện trước phần tử đạt không?
- Có thể thu toàn bộ nguồn không, hay nguồn vô hạn cần cutoff?
- Các thao tác `sorted`, `distinct`, `map` và `filter` trước đó đã làm thay đổi thứ tự/điều kiện xét chưa?
- Nếu dùng parallel stream, có cần tối ưu giữ tiền tố theo thứ tự hay chỉ cần lọc theo predicate?
- Predicate có thuần, không side effect, xử lý null hợp lệ và ổn định trong suốt phép tiêu thụ không?

**Ghi nhớ:** trên ordered stream, `filter(p)` có nghĩa “giữ tất cả phần tử đạt `p`”, còn `takeWhile(p)` có nghĩa “giữ từ đầu đến trước phần tử đầu tiên trượt `p`”. Chỉ dùng `takeWhile` khi chính **ranh giới tiền tố** là điều bạn muốn biểu diễn.
