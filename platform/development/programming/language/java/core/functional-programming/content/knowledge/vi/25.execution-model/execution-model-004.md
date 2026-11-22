# Thao tác không giữ trạng thái và thao tác phải giữ trạng thái trong Java Stream

## 1. Đặt vấn đề: vì sao hai pipeline trông giống nhau nhưng có chi phí khác nhau?

Java Stream API cho phép nối các phép biến đổi dữ liệu thành một pipeline:

~~~java
List<Integer> values = List.of(7, 4, 7, 2, 4, 9);

List<Integer> result = values.stream()
        .filter(n -> n >= 4)
        .distinct()
        .sorted()
        .toList();
~~~

Các phần tử đi qua `filter`, `distinct` và `sorted` rồi được thu thành List. Tuy nhiên, ba thao tác trung gian này không có cùng cơ chế:

- `filter` quyết định giữ hay bỏ **một phần tử dựa trên chính phần tử đó**, không cần nhớ toàn bộ những phần tử trước.
- `distinct` phải xác định phần tử đã xuất hiện hay chưa để loại trùng; nó **có thể cần nhớ những phần tử đã gặp**.
- `sorted` cần tạo thứ tự so sánh giữa các phần tử; với dữ liệu tổng quát, nó **có thể cần đệm phần lớn hoặc toàn bộ phần tử** trước khi phát đầu ra được sắp.

Trong tài liệu Java Stream, đây là hai nhóm **stateless intermediate operations** (thao tác trung gian không giữ trạng thái giữa các phần tử) và **stateful intermediate operations** (thao tác trung gian cần trạng thái/phụ thuộc vào phần tử khác hoặc vị trí trong luồng).

Sự khác biệt này ảnh hưởng đến tính lazy, khả năng kết thúc sớm, bộ nhớ, hiệu năng parallel Stream và tính đúng của logic khi thứ tự thao tác thay đổi.

### Sau bài học, bạn sẽ:

1. Định nghĩa chính xác `stateless` và `stateful` trong **ngữ cảnh thao tác trung gian Stream**.
2. Phân loại `map`, `filter`, `flatMap`, `peek`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile`.
3. Phân biệt **trạng thái nội bộ của operation** với **lambda có side effect và shared mutable state**.
4. Giải thích tại sao `sorted().limit(n)` khác `limit(n).sorted()`.
5. Hiểu yêu cầu encounter order của `distinct`, `limit`, `takeWhile` khi chạy song song.
6. Hiểu pipeline lazy, terminal operation, short-circuit và các trường hợp tối ưu hóa có thể bỏ qua việc gọi một số lambda.
7. Chạy một chương trình Java 17 hoàn chỉnh, dự đoán stdout và tránh những lỗi thường gặp.

## 2. Kiến thức nền: nguồn, thao tác trung gian và terminal operation

Một pipeline Stream thường gồm:

~~~text
Nguồn
  |
  v
Intermediate operations (0 hoặc nhiều)
  |
  v
Terminal operation
  |
  v
Kết quả hoặc side effect
~~~

Ví dụ:

~~~java
List<String> result = Stream.of(" a ", "bb", " c ", "dd")
        .map(String::trim)
        .filter(s -> s.length() == 1)
        .toList();

System.out.println(result); // [a, c]
~~~

Ở đây:

- `Stream.of(...)` tạo nguồn.
- `map(...)` và `filter(...)` là **intermediate operations**: trả Stream mới để tiếp tục pipeline.
- `toList()` là **terminal operation**: yêu cầu đánh giá pipeline và thu kết quả.

Các intermediate operations thường **lazy**: biểu thức `stream.map(...).filter(...)` có thể chỉ dựng pipeline chứ chưa duyệt dữ liệu. Một terminal operation như `toList`, `findFirst`, `count` hoặc `forEach` thường là thời điểm pipeline được đánh giá. Chi tiết tối ưu hóa tùy thao tác và đặc tính nguồn; **không cam kết mọi lambda trung gian sẽ luôn được gọi với số lần cố định**.

### 2.1. Lưu ý: Stream không phải collection có thể chạy lại

~~~java
Stream<String> stream = Stream.of("a", "b");
long count = stream.count();
// stream.toList(); // Không được dùng lại Stream đã tiêu thụ.
~~~

Một Stream thường chỉ có thể được tiêu thụ một lần; nếu cần phép xử lý thứ hai, tạo Stream mới từ nguồn có thể duyệt lại hoặc lưu dữ liệu phù hợp vào collection.

### 2.2. Trọng tâm của bài là intermediate operations

`stateless`/`stateful` trong bài được dùng để mô tả **đặc tính của phép biến đổi trung gian**. Các terminal operations có cách tính toán, yêu cầu kết hợp và short-circuit riêng; không nên dùng cách phân loại của intermediate operations để khẳng định mọi terminal operation đều thu hoặc giữ toàn bộ dữ liệu.

## 3. Stateless intermediate operation là gì?

Một thao tác trung gian **stateless** không cần ghi nhớ kết quả xử lý các phần tử trước để quyết định cách xử lý **một phần tử mới**. Về mô hình, mỗi phần tử có thể xử lý độc lập bằng hàm đã cung cấp.

### 3.1. `filter`: quyết định dựa vào từng phần tử

~~~java
List<Integer> filtered = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .filter(n -> n >= 4)
        .toList();

System.out.println(filtered); // [7, 4, 7, 4, 9]
~~~

Predicate `n -> n >= 4` chỉ đọc `n`. Để biết `7` có được giữ hay không, nó **không cần biết** phần tử trước là `4` hay `9`.

### 3.2. `map`: biến đổi từng phần tử

~~~java
List<String> labels = List.of(1, 2, 3).stream()
        .map(n -> "item-" + n)
        .toList();

System.out.println(labels); // [item-1, item-2, item-3]
~~~

`map` nhận một phần tử và tạo giá trị tương ứng. Với hàm thuần, có thể áp dụng `map` độc lập trên các phần tử.

### 3.3. `flatMap`: một phần tử tạo một Stream con

~~~java
List<String> words = Stream.of("red blue", "green")
        .flatMap(line -> Arrays.stream(line.split(" ")))
        .toList();

System.out.println(words); // [red, blue, green]
~~~

`flatMap` được phân loại là stateless intermediate operation. Mapper tạo một Stream con từ **phần tử hiện tại**; không cần duy trì tập các phần tử trước để quyết định xử lý phần tử mới.

Điều này **không có nghĩa** mọi Stream con rẻ hoặc không giữ tài nguyên: mapper có thể tạo Stream lớn, mở I/O hoặc gây lỗi. Cần quản lý tài nguyên và chi phí riêng. Trong ngữ nghĩa `Stream.flatMap`, các mapped Stream được đóng sau khi nội dung của chúng được đưa vào pipeline theo hợp đồng API.

### 3.4. `peek` cũng là thao tác trung gian stateless nhưng không nên gánh logic nghiệp vụ

~~~java
List<Integer> values = Stream.of(1, 2, 3)
        .peek(n -> System.out.println("saw " + n))
        .toList();
~~~

`peek` về phân loại API là stateless intermediate operation. Tuy nhiên, action `println` có **side effect**. Không suy ra rằng `peek` sẽ chạy đúng một lần cho mỗi phần tử trong mọi pipeline: một số terminal operations và tối ưu hóa có thể không duyệt các bước không cần thiết. `peek` phù hợp hỗ trợ debug có kiểm soát hơn là làm nhiệm vụ ghi dữ liệu, đếm nghiệp vụ hoặc phát sự kiện bắt buộc.

### 3.5. Những điểm chung của các thao tác stateless

| Thao tác | Xử lý một phần tử | Có cần nhớ các phần tử khác để xác định kết quả của phần tử đó? |
| --- | --- | --- |
| `map(f)` | Chuyển giá trị sang `f(value)` | Không |
| `filter(p)` | Giữ nếu `p(value)` là true | Không |
| `mapToInt(f)` | Chuyển sang primitive int | Không |
| `flatMap(f)` | Mở rộng phần tử thành Stream con | Không theo phân loại operation |
| `peek(action)` | Thực hiện action quan sát | Không theo phân loại operation, nhưng action có thể có side effect |

Đặc tính stateless giúp việc xử lý theo từng phần tử và pipeline fusion dễ hơn, nhưng không có nghĩa **mỗi lambda của người dùng chắc chắn thuần, thread-safe hoặc không dùng trạng thái**. Đây là hai vấn đề khác nhau.

## 4. Stateful intermediate operation là gì?

Một phép trung gian **stateful** có thể cần thông tin từ phần tử đã gặp, vị trí trong encounter order hoặc dữ liệu tổng thể để xác định phần tử nào được đưa ra và theo thứ tự nào.

### 4.1. `distinct`: ghi nhớ dữ liệu để bỏ trùng

~~~java
List<Integer> unique = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .distinct()
        .toList();

System.out.println(unique); // [7, 4, 2, 9]
~~~

Để quyết định giữ `7` thứ hai hay không, `distinct` phải biết đã gặp một `7` tương đương trước đó. Trên reference Stream, tiêu chuẩn trùng dựa trên `Object.equals(Object)` và quy tắc hash/equality phù hợp; **không phải comparator của `sorted`**.

Với Stream có encounter order, `distinct` được bảo đảm **ổn định**: khi có các phần tử trùng nhau theo `equals`, phần tử xuất hiện đầu tiên theo encounter order được giữ. Với Stream unordered, không có bảo đảm chọn bản sao nào trong các phần tử bằng nhau.

### 4.2. `sorted`: tạo thứ tự tổng thể

~~~java
List<Integer> sorted = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .sorted()
        .toList();

System.out.println(sorted); // [2, 4, 4, 7, 7, 9]
~~~

Để phát ra giá trị nhỏ nhất đầu tiên với comparator tùy ý, `sorted` về nguyên tắc cần biết những giá trị đến sau. Nó là **stateful intermediate operation**, có thể phải đệm dữ liệu để sắp. Trên ordered Stream, `sorted` được bảo đảm ổn định: các phần tử comparator coi là bằng nhau giữ thứ tự tương đối theo encounter order. Với unordered Stream, không có bảo đảm ổn định giữa các phần tử so sánh bằng 0.

`sorted(Comparator)` dựa vào hợp đồng comparator. Một comparator sai tính bắc cầu hoặc phụ thuộc random/shared mutation có thể làm kết quả sai hoặc gây lỗi, bất kể Stream được dùng tuần tự hay song song.

### 4.3. `limit` và `skip`: phụ thuộc vị trí

~~~java
List<Integer> first = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .limit(3)
        .toList();

List<Integer> tail = List.of(7, 4, 7, 2, 4, 9)
        .stream()
        .skip(3)
        .toList();

System.out.println(first); // [7, 4, 7]
System.out.println(tail);  // [2, 4, 9]
~~~

`limit(n)` cần biết đã phát bao nhiêu phần tử; `skip(n)` cần biết bao nhiêu phần tử phải bỏ trước khi phát kết quả. Đây là những **stateful intermediate operations**; trên ordered Stream chúng phụ thuộc encounter order. `limit` còn là **short-circuiting intermediate operation**: nó có thể giới hạn lượng dữ liệu cần xử lý.

Với unordered Stream, các phép này không nhất thiết chọn “n phần tử đầu” theo một thứ tự gốc cố định, vì nguồn không có encounter order cần bảo toàn. Không dựa vào một lần chạy để suy ra thứ tự được cam kết.

### 4.4. `takeWhile` và `dropWhile`: phụ thuộc prefix của ordered Stream

Từ Java 9:

~~~java
List<Integer> input = List.of(7, 4, 7, 2, 4, 9);

List<Integer> prefix = input.stream()
        .takeWhile(n -> n >= 4)
        .toList();

List<Integer> remainder = input.stream()
        .dropWhile(n -> n >= 4)
        .toList();

System.out.println(prefix);    // [7, 4, 7]
System.out.println(remainder); // [2, 4, 9]
~~~

**Đừng nhầm `takeWhile` với `filter`.**

- `filter(n -> n >= 4)` chọn **tất cả** phần tử thỏa predicate ở mọi vị trí: `[7, 4, 7, 4, 9]`.
- `takeWhile(n -> n >= 4)` trên ordered Stream lấy **prefix dài nhất** gồm những phần tử liên tiếp thỏa predicate, và dừng khi gặp `2`.
- `dropWhile(n -> n >= 4)` trên ordered Stream bỏ **prefix đó**, rồi trả phần còn lại, bao gồm `2` và các giá trị sau nó dù có thể thỏa predicate.

Hai operation này là stateful và thường tương tác mạnh với encounter order. Trên unordered Stream, Javadoc cho phép lựa chọn tập con phần tử thỏa predicate theo những ràng buộc khác, nên không suy ra ngữ nghĩa prefix giống ordered Stream.

### 4.5. Bảng phân loại các operation quan trọng

| Intermediate operation | Nhóm | Cần nhớ gì theo mô hình? | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `map`, `mapToInt` | Stateless | Không cần lịch sử phần tử | Mapper nên non-interfering và stateless |
| `filter` | Stateless | Không cần lịch sử phần tử | Không phải `takeWhile` |
| `flatMap` | Stateless | Không cần lịch sử phần tử | Stream con có thể tốn tài nguyên |
| `peek` | Stateless | Không cần lịch sử theo operation | Side effect không được đảm bảo về số lần |
| `distinct` | Stateful | Những giá trị đã xuất hiện | Ordered: giữ bản đầu của phần tử trùng |
| `sorted` | Stateful | Tập phần tử cần so sánh/xếp thứ tự | Có thể phải đệm dữ liệu |
| `limit(n)` | Stateful, short-circuiting | Số phần tử đã phát | `n` phải không âm |
| `skip(n)` | Stateful | Số phần tử đã bỏ | `n` phải không âm |
| `takeWhile` | Stateful, short-circuiting | Trạng thái prefix thỏa predicate | Khác `filter` |
| `dropWhile` | Stateful | Trạng thái prefix phải bỏ | Khác `filter` |

Không có quy tắc rằng **mọi stateful operation đều cần đệm toàn bộ nguồn**. `limit` thường chỉ cần đếm số phần tử đã chọn, còn `sorted` có thể cần giữ nhiều phần tử. “Stateful” nói lên **phụ thuộc trong xử lý**, không định nghĩa dung lượng bộ nhớ cố định.

## 5. Java 17 hoàn chỉnh: quan sát sự khác nhau

Tạo tệp **`StatefulStreamDemo.java`**:

~~~java
import java.util.List;

public class StatefulStreamDemo {

    record Reading(String id, int score) {}

    public static void main(String[] args) {
        List<Reading> readings = List.of(
                new Reading("A", 7),
                new Reading("B", 4),
                new Reading("C", 7),
                new Reading("D", 2),
                new Reading("E", 4),
                new Reading("F", 9)
        );

        // Stateless: mỗi Reading được filter và map độc lập.
        System.out.println("stateless=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .toList());

        // Stateful: cần biết giá trị đã gặp để distinct.
        System.out.println("distinct=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .distinct()
                .toList());

        // Stateful: sorted phải định thứ tự giữa các phần tử.
        System.out.println("sorted=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .sorted()
                .toList());

        // Hai thứ tự thao tác tạo kết quả khác nhau.
        System.out.println("sort-then-limit=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .sorted()
                .limit(3)
                .toList());

        System.out.println("limit-then-sort=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .limit(3)
                .sorted()
                .toList());

        System.out.println("skip=" + readings.stream()
                .filter(r -> r.score() >= 4)
                .map(Reading::score)
                .skip(2)
                .toList());

        // takeWhile/dropWhile nhìn prefix của ordered Stream.
        System.out.println("takeWhile=" + readings.stream()
                .takeWhile(r -> r.score() >= 4)
                .map(Reading::id)
                .toList());

        System.out.println("dropWhile=" + readings.stream()
                .dropWhile(r -> r.score() >= 4)
                .map(Reading::id)
                .toList());

        // List.parallelStream() vẫn có encounter order.
        System.out.println("parallel-distinct="
                + readings.parallelStream()
                        .filter(r -> r.score() >= 4)
                        .map(Reading::score)
                        .distinct()
                        .toList());
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 StatefulStreamDemo.java
java StatefulStreamDemo
~~~

**Stdout chính xác:**

~~~text
stateless=[7, 4, 7, 4, 9]
distinct=[7, 4, 9]
sorted=[4, 4, 7, 7, 9]
sort-then-limit=[4, 4, 7]
limit-then-sort=[4, 7, 7]
skip=[7, 4, 9]
takeWhile=[A, B, C]
dropWhile=[D, E, F]
parallel-distinct=[7, 4, 9]
~~~

### 5.1. Giải thích từng kết quả

**`stateless`:** `Reading D` có score 2 nên bị filter; các score còn lại vẫn theo encounter order từ `List` là `[7,4,7,4,9]`. `map(Reading::score)` chỉ lấy score hiện tại.

**`distinct`:** `7` thứ hai và `4` thứ hai bị loại. Ordered Stream giữ lần gặp đầu theo `equals` của `Integer`, cho `[7,4,9]`.

**`sorted`:** cùng 5 score sau filter nhưng được sắp tăng thành `[4,4,7,7,9]`; có trùng vì `sorted` không phải `distinct`.

**`sort-then-limit`:** sắp toàn bộ dãy đã lọc theo số tăng, sau đó lấy 3 giá trị đầu, được `[4,4,7]`.

**`limit-then-sort`:** lấy ba giá trị đầu của dãy đã lọc `[7,4,7]` rồi mới sắp, thành `[4,7,7]`. Không thể tùy ý hoán đổi hai thao tác.

**`skip`:** bỏ hai phần tử đầu `7,4` của dãy đã lọc, còn `[7,4,9]`.

**`takeWhile`:** với nguồn gốc `A(7), B(4), C(7), D(2), E(4), F(9)`, predicate đúng đến C rồi sai ở D; lấy các ID `[A,B,C]`.

**`dropWhile`:** bỏ đúng prefix A,B,C rồi giữ từ D đến F, cho `[D,E,F]`.

**`parallel-distinct`:** ordered List vẫn giữ encounter order dù thực thi song song; `distinct` giữ bản xuất hiện đầu theo hợp đồng, kết quả `[7,4,9]`. `toList` thu theo encounter order của pipeline; không dựa vào thứ tự chạy task để giải thích đầu ra.

## 6. Thứ tự thao tác có làm thay đổi kết quả không?

Có. Một số cặp intermediate operations có thể đổi chỗ trong các điều kiện xác định, nhưng không được giả định rằng chúng luôn giao hoán.

### 6.1. `sorted().limit(n)` và `limit(n).sorted()`

~~~java
List<Integer> input = List.of(9, 1, 7, 2, 5);

List<Integer> smallestTwo = input.stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> firstTwoSorted = input.stream()
        .limit(2)
        .sorted()
        .toList();

System.out.println(smallestTwo);    // [1, 2]
System.out.println(firstTwoSorted); // [1, 9]
~~~

- `sorted().limit(2)` có nghĩa tìm hai giá trị nhỏ nhất toàn bộ input theo comparator.
- `limit(2).sorted()` có nghĩa **lấy hai phần tử đầu theo encounter order**, sau đó chỉ sắp hai phần tử ấy.

Ở phép thứ nhất, `sorted` có thể phải quan sát nhiều hoặc toàn bộ phần tử **trước khi** `limit` cho phép phát hai kết quả. Ở phép thứ hai, `limit` ở trước giúp giảm lượng dữ liệu phải sắp nhưng cũng làm bài toán **khác ý nghĩa**.

### 6.2. `filter().limit(n)` và `limit(n).filter()`

~~~java
List<Integer> input = List.of(1, 2, 3, 4, 5);

List<Integer> firstTwoEven = input.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

List<Integer> filteredFirstTwo = input.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(firstTwoEven);    // [2, 4]
System.out.println(filteredFirstTwo); // [2]
~~~

Lấy **hai số chẵn đầu tiên** khác với **chỉ xem hai phần tử đầu rồi lọc số chẵn**. Cần xuất phát từ yêu cầu nghiệp vụ trước khi tối ưu pipeline.

### 6.3. `distinct().limit(n)` và `limit(n).distinct()`

~~~java
List<Integer> input = List.of(1, 1, 2, 3);

System.out.println(input.stream()
        .distinct().limit(2).toList()); // [1, 2]

System.out.println(input.stream()
        .limit(2).distinct().toList()); // [1]
~~~

Phép thứ nhất lấy hai giá trị **khác nhau** đầu tiên. Phép thứ hai chỉ xử lý hai phần tử đầu, rồi bỏ trùng trong hai phần tử đó.

### 6.4. `filter` và `map` có thể đổi thứ tự không?

Chỉ khi predicate và mapper có quan hệ kiểu/logic tương thích, phép chuyển đổi giữ thông tin cần lọc, và không làm thay đổi exception hay side effect quan sát được. Không tùy tiện đổi `filter` trước/sau `map` theo cảm giác.

Ví dụ muốn lọc dựa trên `Reading.score` thì đặt `filter(r -> r.score() >= 4)` trước `map(Reading::id)`; nếu map sang ID trước, predicate không còn dữ liệu score để xét.

## 7. Stateless operation không đồng nghĩa lambda có state là đúng

Đây là một nhầm lẫn quan trọng nhất của bài.

Một `map` vẫn là **stateless intermediate operation theo phân loại Stream**, nhưng bạn hoàn toàn có thể truyền vào một lambda **giữ hoặc sửa shared mutable state**. Điều đó có thể dẫn đến hành vi khó dự đoán và vi phạm yêu cầu *stateless, non-interfering* của behavioral parameters trong Stream API.

### 7.1. Anti-pattern: dùng biến đếm ngoài lambda

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> labels = names.parallelStream()
        .map(name -> counter.incrementAndGet() + ":" + name)
        .toList();
~~~

Đây là **mã minh họa anti-pattern**, với `names` kiểu `List<String>` và import `AtomicInteger`. Dù `AtomicInteger` hỗ trợ cập nhật nguyên tử, số thứ tự gắn vào tên phụ thuộc thứ tự scheduling khi pipeline song song. Nó **không đảm bảo** tên đứng đầu encounter order nhận số `1`.

Nếu yêu cầu đánh số theo vị trí input, dùng index tường minh từ danh sách khi phù hợp:

~~~java
List<String> labels = IntStream.range(0, names.size())
        .mapToObj(i -> (i + 1) + ":" + names.get(i))
        .toList();
~~~

Đây là mảnh mã cần import `IntStream`. Với List hỗ trợ truy cập ngẫu nhiên hiệu quả, cách này thể hiện rõ vị trí; với `LinkedList` và `get(i)` lặp lại, cần cân nhắc chi phí truy cập.

### 7.2. Anti-pattern: can thiệp nguồn trong khi stream chạy

~~~java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

List<Integer> result = source.stream()
        .map(n -> {
            source.add(n * 10); // Không được làm.
            return n;
        })
        .toList();
~~~

Đây là **mã cố ý sai về hợp đồng non-interference**. Việc mutate nguồn dữ liệu trong khi pipeline đang duyệt có thể gây `ConcurrentModificationException` hoặc hành vi không đáng tin; không dùng `map` để thay đổi collection nguồn.

### 7.3. Hàm thuần giúp pipeline dễ lập luận hơn

~~~java
List<String> labels = names.stream()
        .filter(name -> name.length() >= 2)
        .map(String::toUpperCase)
        .toList();
~~~

Cả hai lambda đều không sửa state ngoài; đầu ra phụ thuộc dữ liệu đầu vào. Đây là kiểu kết hợp nên ưu tiên, đặc biệt khi muốn chuyển từ sequential sang parallel mà vẫn giữ tính đúng.

Không phải mọi lambda cần tuyệt đối “không side effect” trong tất cả API, nhưng các behavioral parameters đưa vào phép toán Stream nên đáp ứng các yêu cầu về không can thiệp nguồn, tính stateless và đồng bộ thích hợp. Đừng trộn đặc tính của phép toán với đặc tính triển khai lambda.

## 8. Stateful operations và encounter order

### 8.1. Encounter order là gì?

**Encounter order** là thứ tự phần tử được nguồn Stream định nghĩa và các thao tác liên quan phải tôn trọng khi pipeline còn mang đặc tính ordered.

- `List.stream()` có encounter order theo thứ tự trong List.
- `Stream.of("A","B","C")` có thứ tự theo các phần tử đầu vào.
- `HashSet.stream()` **không bảo đảm encounter order**.
- `unordered()` có thể gỡ ràng buộc thứ tự khỏi pipeline.

Với stateful operations, encounter order thường ảnh hưởng đáng kể đến ngữ nghĩa hoặc chi phí xử lý.

### 8.2. Ordered `distinct` giữ bản đầu; unordered thì không

~~~java
record Item(String key, String label) {}

List<Item> source = List.of(
        new Item("x", "first"),
        new Item("x", "second")
);
~~~

Record trên theo `equals` mặc định **không trùng nhau**, vì `label` khác. Để `distinct` chỉ xem `key` là khóa trùng, không thể giả định `distinct` tự dùng `Item.key()`: cần định nghĩa equality của đối tượng phù hợp, hoặc có collector/map xử lý theo khóa và chính sách giữ phần tử. Đừng dùng comparator `Item::key` rồi mong `distinct()` phân biệt theo comparator.

Một ví dụ đơn giản đúng:

~~~java
List<String> source = List.of("A", "B", "A", "C");
System.out.println(source.stream().distinct().toList());
// [A, B, C]
~~~

`String.equals` xác định hai giá trị `"A"` trùng nhau; trên ordered Stream, lần `"A"` đầu được giữ.

### 8.3. Ordered `sorted` ổn định theo comparator

~~~java
record Task(String id, int priority) {}

List<Task> tasks = List.of(
        new Task("C", 2),
        new Task("B", 1),
        new Task("A", 2)
);

List<String> ids = tasks.stream()
        .sorted(Comparator.comparingInt(Task::priority))
        .map(Task::id)
        .toList();

System.out.println(ids); // [B, C, A]
~~~

Với `priority=2`, Task C xuất hiện trước A trong nguồn, nên sort ổn định giữ C trước A. Nếu nguồn đã `unordered()`, không có cam kết về thứ tự tương đối của hai Task cùng priority, dù comparator vẫn sắp đúng theo priority.

### 8.4. Ordered `limit` và `skip` có vị trí rõ

`limit(3)` trên ordered Stream lấy ba phần tử đầu theo encounter order. `skip(3)` bỏ ba phần tử đầu. Trên unordered Stream, khi yêu cầu chỉ là lấy bất kỳ tối đa `n` phần tử, việc gỡ ràng buộc thứ tự có thể cho phép tối ưu parallel, nhưng **thay đổi nghĩa** nếu nghiệp vụ cần “những bản ghi đầu tiên”.

`unordered()` **không phải phép shuffle**; nó chỉ bỏ bảo đảm về encounter order. Kết quả có thể tình cờ trông như thứ tự cũ nhưng không được dùng làm hợp đồng.

## 9. Lazy execution, fusion và short-circuit

### 9.1. Vì sao stateless operations dễ xử lý liên tiếp?

Với pipeline:

~~~java
List<String> output = source.stream()
        .filter(n -> n > 0)
        .map(n -> "N=" + n)
        .toList();
~~~

Một implementation có thể duyệt phần tử `n`, lọc rồi map trước khi tiếp tục phần tử kế tiếp; không cần tạo một List tạm chứa **toàn bộ** phần tử sau `filter` rồi một List tạm khác sau `map`. Đây là hình dung **pipeline fusion** giúp hiểu cơ chế xử lý. Không nên dùng mô hình này để dự đoán mọi chi tiết nội bộ của JDK hay số lần gọi lambda với mọi terminal operation.

### 9.2. Stateful operation có thể chặn việc phát đầu ra

`sorted` thường phải xem các phần tử trong nguồn trước khi biết phần tử nhỏ nhất để phát. `distinct` cũng phải giữ thông tin về giá trị đã gặp. Một pipeline có stateful stage có thể cần **buffer hoặc synchronization** làm thay đổi chi phí xử lý.

Dù vậy, **stateful không đồng nghĩa luôn đệm toàn bộ nguồn**: `limit(n)` có thể ngừng sớm, `skip(n)` cần đếm, `takeWhile` trên ordered Stream có thể dừng khi gặp phần tử không thỏa predicate. Tính chính xác của nhu cầu bộ nhớ phụ thuộc operation, source, kích thước và cách thực thi.

### 9.3. Short-circuit không bảo đảm mọi pipeline kết thúc nhanh

~~~java
List<Integer> firstThree = IntStream.iterate(1, n -> n + 1)
        .limit(3)
        .boxed()
        .toList();

System.out.println(firstThree); // [1, 2, 3]
~~~

`limit(3)` cho phép dừng pipeline trên nguồn vô hạn được tạo bởi `iterate`. Nhưng:

~~~java
// Có thể không bao giờ cho kết quả:
IntStream.iterate(1, n -> n + 1)
        .sorted()
        .limit(3)
        .toArray();
~~~

Đây là **anti-pattern**, không chạy để chờ stdout. `sorted` phải xử lý một nguồn không có điểm kết thúc trước khi biết thứ tự toàn cục; `limit` đặt sau `sorted` không làm phép sort vô hạn trở nên hữu hạn.

Nếu bài toán cho phép, đặt giới hạn hữu hạn **trước** sort:

~~~java
int[] values = IntStream.iterate(1, n -> n + 1)
        .limit(3)
        .sorted()
        .toArray();
~~~

Đoạn này xử lý ba phần tử. Khi thay đổi thứ tự, luôn kiểm tra nghĩa của kết quả, không chỉ tốc độ.

### 9.4. Tối ưu hóa có thể bỏ gọi một số action

~~~java
long n = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();
~~~

**Không coi việc in ba dòng là hợp đồng.** Nguồn List có kích thước đã biết, `count()` có thể tính số lượng mà không duyệt từng phần tử và không chạy `peek`. Tương tự, vài stage không làm thay đổi số lượng có thể được bỏ qua nếu terminal operation không cần kết quả của chúng.

Nếu yêu cầu nghiệp vụ là gửi log, cập nhật số liệu hoặc phát event **mỗi phần tử**, đừng phụ thuộc vào `peek` trong pipeline mà phép tính cuối có thể tối ưu hóa; hãy dùng cơ chế xử lý tường minh với đặc tả side effect và lỗi phù hợp.

## 10. Sequential và parallel: chi phí stateful operation

### 10.1. Stateless có tiềm năng xử lý độc lập

`map` và `filter` với behavioral parameters không can thiệp, stateless có thể xử lý nhiều phần tử độc lập, nên thường thuận lợi cho parallel execution. Nhưng **không có cam kết tự động nhanh hơn**: việc tách công việc, phối hợp kết quả, boxing, cache locality và kích thước dữ liệu có thể làm parallel chậm hơn sequential.

Nếu phép biến đổi rất nhẹ trên tập nhỏ, overhead của parallel Stream có thể chiếm phần lớn thời gian. Hãy đo trên workload thật khi hiệu năng là mục tiêu.

### 10.2. `distinct` với ordered parallel có thể tốn buffer/coordination

Trên ordered Stream, `distinct` phải tôn trọng việc giữ lần xuất hiện đầu tiên của mỗi giá trị. Với parallel Stream, giữ ổn định theo encounter order có thể cần **nhiều buffer hoặc phối hợp giữa các task** và tạo chi phí đáng kể.

Javadoc cho phép cân nhắc `unordered()` nếu **ngữ nghĩa không đòi giữ bản đầu**; điều đó có thể cải thiện hiệu năng một số workload. Nhưng dùng `unordered()` không được làm mất yêu cầu nghiệp vụ cần bảo toàn thứ tự.

### 10.3. `sorted` trên ordered parallel vẫn có tính ổn định

`parallelStream().sorted(comparator)` trên nguồn ordered vẫn có bảo đảm ổn định của `sorted`. Tuy nhiên, phép sắp xếp là stateful, có thể phải phối hợp/sắp xếp phần dữ liệu rồi gộp. Không suy ra rằng nó luôn nhanh hơn sort tuần tự.

Nếu dữ liệu được sort chỉ để lấy một phần tử max/min, có thể dùng `max(comparator)` hoặc `min(comparator)` thay vì tạo một List đã sort. Chọn dựa trên yêu cầu: “lấy một giá trị lớn nhất” khác “xuất toàn bộ thứ tự”.

### 10.4. Ordered `limit`/`skip` trong parallel có thể đắt

Với:

~~~java
List<Integer> first = IntStream.range(0, 1_000)
        .parallel()
        .limit(10)
        .boxed()
        .toList();
~~~

Dãy nguồn có encounter order, nên kết quả phải là các giá trị 0 đến 9. Yêu cầu “mười phần tử đầu” trong parallel có thể cần phối hợp chặt chẽ để biết đúng vị trí. Nếu bài toán thực sự chỉ cần **bất kỳ mười phần tử**, `unordered()` có thể nới lỏng thứ tự và giúp tối ưu; nhưng đầu ra không còn cam kết chứa mười số đầu theo nguồn.

### 10.5. `forEach` và `forEachOrdered` khác nhau

~~~java
IntStream.range(0, 10)
        .parallel()
        .forEach(System.out::println);
~~~

Không có stdout cố định theo thứ tự: `forEach` không cam kết thứ tự thực thi action trên parallel Stream. Điều đó **không có nghĩa** `map`, `sorted` hoặc `distinct` trước nó làm sai kết quả dữ liệu.

Nếu cần hành động được thực thi theo encounter order:

~~~java
IntStream.range(0, 10)
        .parallel()
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` cam kết order của action theo encounter order, có thể làm giảm lợi ích parallel. Nếu chỉ cần dữ liệu có thứ tự để kiểm thử, dùng `toList()` rồi so sánh List thay vì dựa vào thứ tự log từ nhiều thread.

### 10.6. Stateful operation và shared mutable state là hai loại vấn đề

`sorted` có thể cần state nội bộ **do thư viện quản lý**. Điều đó không cho phép bạn tự mutate `ArrayList` chung trong `parallel().forEach(shared::add)`. Các collector và API Stream có cơ chế phối hợp theo hợp đồng, còn mutation ngoài pipeline phải được thiết kế an toàn riêng.

## 11. Primitive Streams và thống kê

Cùng ý tưởng stateless/stateful áp dụng cho `IntStream` và `LongStream`:

~~~java
int[] values = IntStream.rangeClosed(1, 8)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toArray();

System.out.println(Arrays.toString(values)); // [4, 8, 12, 16]
~~~

`filter` và `map` ở đây stateless. Nếu thêm `distinct()` hoặc `sorted()`, những stage đó stateful.

Thay vì sort một dãy số để tính tổng:

~~~java
long sum = IntStream.rangeClosed(1, 100)
        .mapToLong(n -> n)
        .sum();
~~~

Đây là một **terminal reduction**, không cần sắp xếp. `IntStream.sum()` trả `int` và có thể overflow với miền lớn; `mapToLong` giúp mở rộng miền tích lũy trong ví dụ, dù `long` vẫn có giới hạn.

**Lưu ý:** không nên nghĩ `IntStream` luôn nhanh hơn các pipeline reference trong mọi bài toán; cần xét kiểu dữ liệu, boxing, đặc tính source, cost của lambda, và đo hiệu năng khi thực sự cần.

## 12. Thiết kế pipeline theo yêu cầu nghiệp vụ

Giả sử một hệ thống xử lý các giao dịch có trường `id`, `score` và thứ tự tiếp nhận:

- Nếu cần **lọc mọi giao dịch score >= 4**, dùng `filter`.
- Nếu cần **giữ giao dịch có id duy nhất và chọn lần nhận đầu**, hãy thiết kế equality/key rõ và một chiến lược giữ bản đầu theo encounter order; chỉ `distinct()` là đủ khi `equals` của object thể hiện đúng khóa đó.
- Nếu cần **xếp tất cả theo score**, dùng `sorted(comparator)`.
- Nếu cần **ba giao dịch score cao nhất**, có thể dùng `sorted(comparator.reversed()).limit(3)` cho tập dữ liệu hữu hạn, nhưng xét chi phí và chính sách tie-breaker.
- Nếu cần **ba giao dịch đầu tiên theo thời gian tiếp nhận**, dùng `limit(3)` với ordered source; đừng đặt `unordered()` trước nếu thứ tự là hợp đồng.
- Nếu cần **đọc cho tới khi gặp marker kết thúc**, `takeWhile` có thể phù hợp với ordered Stream; không được thay nó bằng `filter` vì filter có thể tiếp tục giữ phần tử sau marker.

### 12.1. Định nghĩa tiêu chí rồi mới tối ưu thứ tự thao tác

Thứ tự stage là một phần của ý nghĩa bài toán. Ví dụ:

~~~java
List<Integer> firstTwoPassing = values.stream()
        .filter(n -> n >= 4)
        .limit(2)
        .toList();
~~~

Đây là "hai số đầu tiên thỏa điều kiện". Đổi thành `limit(2).filter(...)` là "chỉ kiểm tra hai số đầu"; kết quả có thể khác. Tối ưu pipeline không được âm thầm thay đổi nghĩa.

### 12.2. Khi nào nên dùng vòng lặp thay vì Stream?

Một vòng `for` có thể rõ hơn nếu logic cần break/continue phức tạp, nhiều side effect bắt buộc theo thứ tự, transaction trên từng phần tử hoặc khôi phục lỗi theo từng bước. Stream phù hợp cho pipeline biến đổi và tổng hợp rõ ràng; nó không phải sự thay thế bắt buộc cho mọi cấu trúc lặp.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Tưởng `map` stateless nghĩa là lambda có thể mutate state ngoài an toàn | Sai thứ tự, race, non-interference | Lambda thuần hoặc kiểm soát state rõ |
| Dùng `filter` thay `takeWhile` | Không dừng ở phần tử sai đầu tiên | Chọn theo yêu cầu prefix hay toàn tập |
| Dùng `distinct` để loại trùng theo comparator | `distinct` dựa vào `equals` | Thiết kế equality hoặc cách nhóm theo khóa |
| Dùng `sorted` để loại trùng | Sort không loại phần tử bằng nhau | Thêm `distinct` khi đúng hợp đồng |
| Đổi `sorted().limit(n)` thành `limit(n).sorted()` | Thay tập dữ liệu được chọn | Chỉ đổi nếu bài toán cho phép |
| Dùng `parallel().forEach` để kiểm tra thứ tự | Action không cam kết encounter order | Dùng `toList` hoặc `forEachOrdered` |
| Nghĩ unordered source có “phần tử đầu tiên” cố định | Không có encounter order được bảo đảm | Chọn nguồn ordered hoặc sort/tie-breaker |
| Thêm `unordered()` để tăng tốc mà không xét yêu cầu | Mất bảo đảm chọn bản đầu/first n | Chỉ nới order khi không cần |
| Gọi `sorted` trên Stream vô hạn rồi `limit` | Có thể không bao giờ trả kết quả | Giới hạn nguồn hữu hạn trước khi sort |
| Gọi `peek` để tăng counter nghiệp vụ | Tối ưu hóa có thể bỏ action | Xử lý nghĩa vụ nghiệp vụ tường minh |
| Dùng Stream đã tiêu thụ lần thứ hai | `IllegalStateException` hoặc vi phạm lifecycle | Tạo Stream mới |
| Viết comparator `a-b` trên int cực trị | Có thể overflow, sai thứ tự | `Integer.compare`/`comparingInt` |
| Chạy `sorted` trên dữ liệu khổng lồ vô điều kiện | Có thể đệm lớn, thiếu bộ nhớ | Chọn reduction/top-k/giới hạn phù hợp |
| Mutate collection nguồn trong `map` | Có thể lỗi và kết quả không đáng tin | Không can thiệp nguồn trong pipeline |
| Tin parallel luôn nhanh hơn sequential | Overhead cao, contention | Benchmark workload thực |

### 13.1. Comparator phải hợp đồng

`sorted(Comparator)` đòi comparator có quan hệ so sánh nhất quán. Nếu comparator sử dụng giá trị mutable biến đổi giữa các lần so sánh, hoặc không bắc cầu, kết quả không đáng tin. Ưu tiên:

~~~java
Comparator<Reading> byScore =
        Comparator.comparingInt(Reading::score);
~~~

Đây là mảnh mã ở phạm vi có record `Reading` và import `Comparator`. Tránh tự viết `(a,b) -> a.score() - b.score()` khi phép trừ có thể overflow.

### 13.2. `limit` và `skip` yêu cầu số không âm

~~~java
Stream.of("A", "B").limit(-1); // Khi thực thi lời gọi, ném IllegalArgumentException.
Stream.of("A", "B").skip(-1);  // Tương tự.
~~~

Đây là các ví dụ cố ý lỗi. Theo Javadoc, đối số maxSize/n của `limit` và `skip` phải **không âm**. Khi giá trị lấy từ input, kiểm tra trước và báo lỗi phù hợp.

## 14. Bài tập thực hành

### Bài 1 — Phân loại thao tác

Phân nhóm `map`, `filter`, `peek`, `flatMap`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile` và `dropWhile` thành stateless và stateful. Với mỗi thao tác stateful, nêu một thông tin tối thiểu nó cần biết (đã gặp phần tử, vị trí, prefix hoặc thứ tự tổng thể).

### Bài 2 — Dự đoán output `distinct`

Với `List.of(4, 2, 4, 3, 2, 5)`, tính kết quả `stream().distinct().toList()`. **Đáp án:** `[4, 2, 3, 5]` vì nguồn có encounter order và `distinct` ổn định trên ordered Stream.

### Bài 3 — Đổi thứ tự `sorted` và `limit`

Với `[9,1,7,2,5]`, tính `sorted().limit(2)` và `limit(2).sorted()`. **Đáp án:** lần lượt `[1,2]` và `[1,9]`. Giải thích tại sao đây là hai yêu cầu khác nhau.

### Bài 4 — `filter` khác `takeWhile`

Với `[7,4,7,2,4,9]` và điều kiện `n >= 4`, dự đoán `filter`, `takeWhile` và `dropWhile`. **Đáp án:** `filter` = `[7,4,7,4,9]`; `takeWhile` = `[7,4,7]`; `dropWhile` = `[2,4,9]`.

### Bài 5 — Ngữ nghĩa song song

Dùng ordered `List<Integer>` với phần tử trùng. So sánh `stream().distinct().toList()` và `parallelStream().distinct().toList()`. Giải thích vì sao kết quả theo encounter order vẫn phải có tính ổn định; sau đó thử `parallelStream().forEach(System.out::println)` và giải thích vì sao stdout không được bảo đảm thứ tự.

### Bài 6 — Phân biệt stateless operation và stateful lambda

Viết một `map` dùng counter ngoài rồi chạy song song; chỉ ra vì sao giá trị counter gắn vào phần tử có thể khác thứ tự nguồn. Sửa bằng `IntStream.range(0, list.size()).mapToObj(i -> ...)` nếu dữ liệu và nhu cầu đánh số cho phép.

### Bài 7 — Source unordered

Tạo `HashSet<String>`, dùng `stream().distinct().limit(2)`. Hãy giải thích vì sao không có hợp đồng “hai phần tử đầu tiên của HashSet”. Đừng viết test kỳ vọng một cặp phần tử cụ thể trừ khi đã thêm quy tắc ordered thích hợp.

### Bài 8 — Vô hạn và giới hạn

So sánh `IntStream.iterate(1, n -> n+1).limit(10).sorted().toArray()` với `IntStream.iterate(1, n -> n+1).sorted().limit(10).toArray()`. Chỉ thực thi phiên bản thứ nhất. Giải thích vì sao phiên bản thứ hai không thích hợp.

### Bài 9 — Tối ưu nghiệp vụ

Một hệ thống cần tính tổng score của các bản ghi đã lọc. Chọn `filter` rồi `mapToInt(...).sum()` thay cho `sorted(...).collect(...).stream().sum()` nếu không cần thứ tự. Giải thích vì sao bỏ stateful sort tiết kiệm chi phí và không đổi kết quả của phép tổng khi điều kiện phù hợp.

### Bài 10 — Khả năng đúng của `peek`

Cho `Stream.of("a","b","c").peek(log).count()`. Giải thích vì sao không thể bảo đảm log chạy ba lần. Đề xuất cách thiết kế log bắt buộc thành một phần xử lý tường minh thay vì một side effect không được cam kết trong intermediate operation.

## 15. Câu hỏi tự kiểm tra

1. **Stateless intermediate operation nghĩa là gì?** Không cần giữ thông tin từ phần tử khác để xử lý từng phần tử hiện tại.
2. **Stateful intermediate operation nghĩa là gì?** Có thể cần ghi nhớ phần tử trước, vị trí, prefix hoặc dữ liệu tổng thể.
3. **`filter` và `map` là loại nào?** Stateless.
4. **`distinct` và `sorted` là loại nào?** Stateful.
5. **`limit`/`skip` có stateful không?** Có, chúng phụ thuộc vị trí/số lượng phần tử.
6. **`takeWhile` có giống `filter`?** Không; trên ordered Stream nó chỉ lấy prefix liên tiếp thỏa predicate.
7. **Stateful có nghĩa phải giữ toàn bộ Stream trong RAM?** Không; tùy operation.
8. **`sorted().limit(3)` có luôn bằng `limit(3).sorted()`?** Không; có thể khác phần tử.
9. **`distinct` dùng `equals` hay comparator?** Dùng `equals` để xác định trùng trên reference Stream.
10. **`parallelStream` trên List còn ordered không?** Có; parallel không tự bỏ encounter order.
11. **Vì sao `parallel().forEach` không giúp xác minh kết quả sort?** Side effect có thể chạy không theo encounter order.
12. **Một `map` có lambda sửa counter ngoài có được gọi là stateful operation không?** Operation `map` vẫn stateless theo phân loại API, nhưng lambda đã có state/side effect và không phù hợp yêu cầu stateless behavior.
13. **`peek` có thể thay logic nghiệp vụ bắt buộc chạy mỗi phần tử không?** Không đáng tin, vì có thể bị tối ưu bỏ.
14. **`unordered()` có trộn ngẫu nhiên dữ liệu không?** Không; nó loại bỏ ràng buộc order.
15. **Khi nào nên ưu tiên terminal reduction thay vì `sorted`?** Khi mục tiêu chỉ là tổng, đếm hoặc max/min và không cần sắp toàn bộ.

## 16. Checklist áp dụng trong dự án

- [ ] Đã xác định rõ nguồn Stream ordered hay unordered chưa?
- [ ] Mỗi lambda `map`/`filter` có tránh mutate source và shared state không?
- [ ] Có dùng `distinct` đúng tiêu chí `equals` không, hay yêu cầu thực tế là “trùng theo key”?
- [ ] `sorted` có thực sự cần, hay `max/min` hoặc reduction đủ?
- [ ] `limit/skip/takeWhile/dropWhile` có đúng ngữ nghĩa thứ tự phần tử không?
- [ ] Có thay đổi thứ tự stage mà chưa so sánh output trong các case biên không?
- [ ] Có đang dựa vào side effect trong `peek` hoặc `map` để bảo đảm số lần thực hiện không?
- [ ] Có gọi `sorted` trước khi giới hạn nguồn vô hạn hoặc quá lớn không?
- [ ] Nếu dùng parallel, có đo chi phí stateful operations và loại bỏ shared mutable state không?
- [ ] Nếu gọi `unordered()`, yêu cầu nghiệp vụ có thực sự không cần encounter order không?
- [ ] Các test có so sánh dữ liệu thu được, thay vì dựa vào thứ tự `println` trong `forEach` song song không?
- [ ] Đã kiểm thử đầu vào rỗng, trùng nhiều, dữ liệu không có phần tử thỏa predicate và trường hợp short-circuit chưa?

## 17. Tổng kết và tài liệu tham khảo

**Stateless intermediate operations** như `map`, `filter` và `flatMap` có thể xử lý từng phần tử mà không cần nhớ lịch sử các phần tử khác. **Stateful intermediate operations** như `distinct`, `sorted`, `limit`, `skip`, `takeWhile` và `dropWhile` có phụ thuộc vào phần tử trước, vị trí, prefix hoặc tập dữ liệu tổng thể. Phân loại này giúp giải thích tại sao một số pipeline xử lý theo từng phần tử dễ dàng, trong khi những pipeline khác có thể cần buffer hoặc phối hợp phức tạp.

Ba nguyên tắc nên ghi nhớ:

1. **Phân loại operation khác với tính đúng của lambda.** `map` vẫn là operation stateless ngay cả khi người viết truyền lambda có side effect; điều đó không biến hành vi stateful thành an toàn.
2. **Thứ tự thao tác là ngữ nghĩa chương trình.** `sorted().limit(n)` không tương đương `limit(n).sorted()`, và `filter` không đồng nghĩa `takeWhile`.
3. **Ordered/parallel/short-circuit ảnh hưởng hành vi và chi phí.** Không dựa vào thứ tự log của `forEach` song song, không tự bỏ encounter order nếu cần giữ bản đầu, và không kỳ vọng `limit` đặt sau `sorted` cứu được một nguồn vô hạn.

Để xác minh, đọc **Javadoc Java SE 17** của `java.util.stream.Stream` (`map`, `filter`, `flatMap`, `peek`, `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile`, `forEach`, `forEachOrdered`), tài liệu package `java.util.stream` về *stateless/stateful operations, non-interference, stateless behaviors, laziness, short-circuiting*, và `java.util.Spliterator` về `ORDERED`.
