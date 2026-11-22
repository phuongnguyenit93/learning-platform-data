# Dùng unordered để bỏ ràng buộc thứ tự

## 1. Vì sao Stream cần biết thứ tự?

Trong **JAVA_STREAM_API**, một pipeline khai báo thường bắt đầu bằng nguồn dữ liệu, đi qua các phép biến đổi như `filter`, `map`, `distinct`, `sorted`, `limit` rồi kết thúc bằng `collect`, `reduce` hoặc terminal operation khác. Cùng một tập phần tử, nhưng **thứ tự phần tử** có thể làm thay đổi ý nghĩa của một số operation.

Ví dụ, khi xử lý các giao dịch theo thời gian, “lấy 3 giao dịch đầu tiên” khác với “lấy 3 giao dịch bất kỳ”. Nhưng khi chỉ cần biết có bao nhiêu mã sản phẩm khác nhau, thứ tự thường không còn quan trọng. Java Stream API dùng khái niệm **encounter order** (thứ tự gặp phần tử) để mô tả ràng buộc này.

`unordered()` là một **intermediate operation** cho phép loại bỏ ràng buộc encounter order khỏi pipeline. Nó đặc biệt hữu ích khi những operation phía sau không cần giữ “phần tử nào đến trước” và thư viện có thể tận dụng quyền tự do đó trong quá trình thực thi, nhất là với parallel stream.

~~~text
Nguồn có encounter order                 Nguồn/pipeline không có encounter order
     [9, 2, 7, 4, 1, 8]                           {9, 2, 7, 4, 1, 8}
                |                                         |
          stream()                                      stream()
                |                                         |
       giữ thứ tự gặp                         unordered() hoặc nguồn vốn unordered
                |                                         |
          limit(3)                                   limit(3)
                |                                         |
           [9, 2, 7]                              3 phần tử bất kỳ
                |                                         |
      ý nghĩa: 3 đầu tiên                   không bảo đảm là 3 đầu tiên
~~~

**Điều quan trọng:** `unordered()` **không xáo trộn danh sách**, **không bảo đảm kết quả sẽ đổi thứ tự** và **không phải cơ chế lấy mẫu ngẫu nhiên**. Nó thay đổi những gì pipeline **phải bảo đảm**, chứ không yêu cầu tạo một phép hoán vị cụ thể.

## 2. Nguồn nào có encounter order?

Thứ tự gặp phần tử thường được quy định bởi nguồn và các operation trung gian:

| Nguồn hoặc operation | Bảo đảm encounter order? | Minh họa |
| --- | --- | --- |
| `List.stream()`, `ArrayList.stream()` | Có | Theo thứ tự phần tử trong danh sách. |
| `IntStream.range(1, 5)` | Có | Theo thứ tự 1, 2, 3, 4. |
| `LinkedHashSet.stream()` | Có | Theo thứ tự lặp được xác định của `LinkedHashSet`. |
| `HashSet.stream()` | Không | Không có thứ tự gặp được cam kết. |
| `HashMap.entrySet().stream()` | Không | Không có thứ tự gặp được cam kết. |
| `Stream.generate(...)` | Không | Nguồn sinh vô hạn, không có encounter order. |
| `sorted()` | Có trên luồng đầu ra đã sắp xếp | Sắp xếp bằng thứ tự tự nhiên hoặc comparator. |
| `unordered()` | Bỏ ràng buộc | Các operation phía sau không cần giữ thứ tự nguồn. |

Đừng nhầm **thứ tự xuất hiện khi in ra một lần** với **encounter order được API bảo đảm**. Một `HashSet` có thể thường in các phần tử theo cùng thứ tự trên nhiều lần chạy, nhưng không vì thế mà trở thành nguồn có encounter order.

Ví dụ:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

List<Integer> orderedList = List.of(9, 2, 7, 4, 1, 8);
Set<Integer> orderedSet = new LinkedHashSet<>(orderedList);

System.out.println(orderedList.stream().limit(3).toList()); // [9, 2, 7]
System.out.println(orderedSet.stream().limit(3).toList());  // [9, 2, 7]
~~~

Với nguồn có thứ tự, các phép như `map` và `filter` thông thường giữ encounter order của phần tử còn lại. Một số operation có thể **thay đổi** thứ tự (như `sorted`) hoặc **bỏ ràng buộc thứ tự** (như `unordered`).

## 3. Cách dùng `Stream.unordered()`

Chữ ký của operation trên `Stream<T>`:

~~~java
Stream<T> unordered()
~~~

`IntStream`, `LongStream` và `DoubleStream` cũng có `unordered()` tương ứng. Operation này không biến đổi giá trị phần tử và không trực tiếp loại phần tử; nó trả về một Stream tương đương mà **không còn bị ràng buộc encounter order**. Nếu Stream đã unordered, API có thể trả về chính Stream đó.

Ví dụ Java 17+:

~~~java
import java.util.List;

public class UnorderedBasics {
    public static void main(String[] args) {
        List<Integer> values = List.of(9, 2, 7, 4, 1, 8);

        List<Integer> result = values.stream()
            .unordered()
            .toList();

        System.out.println(result);
        // Có thể vẫn là [9, 2, 7, 4, 1, 8].
        // KHÔNG được dựa vào thứ tự này như một bảo đảm.
    }
}
~~~

Trong nhiều trường hợp chạy tuần tự, kết quả quan sát được vẫn giống danh sách gốc. Điều đó không làm `unordered()` trở thành thao tác vô nghĩa: nó đã **nới hợp đồng** cho toàn bộ các operation về sau. Khi thêm `parallel()`, `distinct()`, `limit()` hoặc thay đổi cách xử lý bên dưới, sự khác biệt có thể trở nên rõ rệt.

### `unordered()` là lazy

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = List.of(1, 2, 3, 4).stream()
    .unordered()
    .filter(n -> n % 2 == 0);

// Mới tạo pipeline; chưa cần duyệt phần tử.
List<Integer> evens = pipeline.toList();
~~~

`toList()` là terminal operation kích hoạt tính toán và trả về danh sách không sửa đổi được. Không dùng lại `pipeline` cho terminal operation khác sau khi đã gọi `toList()`.

## 4. Tác động với `limit` và `skip`

### 4.1. `limit(n)`: “n phần tử đầu tiên” hay “n phần tử bất kỳ”?

Với encounter order, `limit(n)` giữ **n phần tử đầu tiên** trong thứ tự gặp. Sau `unordered()`, nó chỉ cần trả một tập con có không quá `n` phần tử, và với nguồn hữu hạn có ít nhất `n` phần tử thường trả đúng `n` phần tử, nhưng **không bảo đảm là những phần tử đầu tiên của nguồn**.

~~~java
import java.util.List;

List<Integer> numbers = List.of(9, 2, 7, 4, 1, 8);

List<Integer> firstThree = numbers.stream()
    .limit(3)
    .toList();

List<Integer> anyThree = numbers.parallelStream()
    .unordered()
    .limit(3)
    .toList();

System.out.println(firstThree); // [9, 2, 7]
System.out.println(anyThree);   // 3 giá trị từ nguồn; thứ tự và giá trị được chọn không được cam kết.
~~~

Đừng viết kiểm thử mong đợi `anyThree.equals(List.of(9, 2, 7))`. Kiểm thử phù hợp có thể xác minh số lượng, mọi phần tử đều có trong nguồn và không có phần tử nào nằm ngoài phạm vi mong đợi:

~~~java
import java.util.HashSet;

if (anyThree.size() != 3
        || !new HashSet<>(numbers).containsAll(anyThree)) {
    throw new AssertionError("Kết quả không đáp ứng điều kiện chọn 3 phần tử");
}
~~~

Với bài toán **top 3 nhỏ nhất**, bỏ thứ tự trước `limit` là sai mục tiêu. Phải sắp xếp theo tiêu chí cần chọn:

~~~java
List<Integer> smallest = numbers.stream()
    .unordered()
    .sorted()
    .limit(3)
    .toList();

System.out.println(smallest); // [1, 2, 4]
~~~

`sorted()` thiết lập thứ tự của Stream đầu ra, vì vậy `limit(3)` sau nó có ý nghĩa là lấy ba giá trị nhỏ nhất.

### 4.2. `skip(n)`: bỏ phần tử đầu hay bỏ một số phần tử?

~~~java
List<Integer> remainingInOrder = numbers.stream()
    .skip(2)
    .toList();

System.out.println(remainingInOrder); // [7, 4, 1, 8]

List<Integer> remainingWithoutOrder = numbers.parallelStream()
    .unordered()
    .skip(2)
    .toList();

// Bỏ 2 phần tử bất kỳ; không được khẳng định đã bỏ 9 và 2.
~~~

Nếu mục tiêu là phân trang hoặc xử lý theo mốc thứ tự, **không dùng `unordered` trước `skip` / `limit`**. Phân trang yêu cầu thứ tự xác định, tốt nhất là một khóa sắp xếp rõ ràng và xử lý nhất quán giữa các lần truy vấn.

### 4.3. Vị trí của `unordered` quan trọng

~~~java
// A: limit thực hiện khi pipeline vẫn có encounter order.
var a = numbers.stream().limit(3).unordered().toList();

// B: limit không còn phải chọn 3 phần tử đầu.
var b = numbers.stream().unordered().limit(3).toList();
~~~

Ở A, tập giá trị được chọn đã bị ràng buộc bởi `limit(3)` theo thứ tự nguồn; `unordered` phía sau chỉ bỏ yêu cầu về thứ tự **xuất kết quả**. Ở B, `limit(3)` có quyền lựa chọn bất kỳ ba phần tử. Đây là khác biệt về **ngữ nghĩa**, không phải chỉ về hiệu năng.

## 5. Tác động với `distinct`: loại trùng khi không cần giữ phần tử đầu

`distinct()` loại các phần tử trùng nhau theo `Object.equals`. Trên Stream **có encounter order**, operation này ổn định: đối với các phần tử bằng nhau, phần tử xuất hiện đầu tiên được giữ lại. Trên Stream **unordered**, tính ổn định đó không được bảo đảm.

~~~java
import java.util.List;

List<String> labels = List.of("A", "B", "A", "C", "B");

List<String> orderedDistinct = labels.stream()
    .distinct()
    .toList();

System.out.println(orderedDistinct); // [A, B, C]

List<String> unorderedDistinct = labels.parallelStream()
    .unordered()
    .distinct()
    .toList();

// Vẫn gồm A, B, C, mỗi giá trị đúng một lần.
// Thứ tự xuất kết quả không được bảo đảm.
~~~

Với chuỗi trong ví dụ, các giá trị trùng nhau không có khác biệt quan sát được ngoài vị trí. Với object có nhiều thuộc tính nhưng được xem là bằng nhau theo một khóa, việc chọn **đại diện nào** mới đáng chú ý. Nếu nghiệp vụ yêu cầu “giữ bản ghi đầu tiên theo thời gian”, hãy giữ encounter order và xác định rõ comparator/chiến lược chọn.

### Vì sao `unordered` đôi khi cải thiện hiệu năng của `distinct`?

Với ordered parallel stream, `distinct` cần bảo toàn tính ổn định và thứ tự phần tử. Điều này có thể kéo theo đồng bộ và lưu trữ đáng kể. Với unordered parallel stream, implementation được phép chọn một phần tử bất kỳ trong mỗi nhóm trùng và có thêm lựa chọn để xử lý đồng thời.

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Set<Integer> unique = IntStream.range(0, 1_000_000)
    .parallel()
    .map(n -> n % 1000)
    .unordered()
    .distinct()
    .boxed()
    .collect(Collectors.toSet());

// unique chứa 1000 giá trị: 0 đến 999.
~~~

Ở ví dụ này, ta chỉ quan tâm tập giá trị, không quan tâm thứ tự. `Collectors.toSet()` tự nó cũng không cam kết encounter order của tập trả về.

Không vì vậy mà mọi pipeline `unordered().distinct()` đều nhanh hơn: nếu nguồn nhỏ, xử lý tuần tự, hoặc chi phí chính nằm ở nguồn và hàm ánh xạ, chênh lệch có thể không đáng kể. Hãy benchmark khi tối ưu là mục tiêu.

## 6. `takeWhile` và `dropWhile` thay đổi ý nghĩa rõ rệt

Từ **Java 9**, `takeWhile(predicate)` và `dropWhile(predicate)` có hành vi phụ thuộc encounter order.

Với **ordered stream**:
- `takeWhile` giữ **tiền tố dài nhất** của các phần tử liên tiếp thỏa predicate.
- `dropWhile` bỏ **tiền tố dài nhất** đó, giữ phần còn lại.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 1, 6, 8);

List<Integer> prefix = values.stream()
    .takeWhile(n -> n % 2 == 0)
    .toList();

List<Integer> afterPrefix = values.stream()
    .dropWhile(n -> n % 2 == 0)
    .toList();

System.out.println(prefix);      // [2, 4]
System.out.println(afterPrefix); // [1, 6, 8]
~~~

Phần tử `1` làm `takeWhile` dừng giữ phần tử theo tiền tố, dù `6` và `8` vẫn thỏa điều kiện.

Với **unordered stream**, khái niệm “tiền tố” không còn có nghĩa. Nếu một số nhưng không phải tất cả phần tử thỏa predicate:

| Operation | Điều được phép khi unordered |
| --- | --- |
| `takeWhile(p)` | Chọn **bất kỳ tập con nào** của các phần tử thỏa `p`, kể cả tập rỗng. |
| `dropWhile(p)` | Bỏ **bất kỳ tập con nào** của các phần tử thỏa `p`, kể cả không bỏ phần tử nào; phần tử không thỏa phải được giữ. |

~~~java
List<Integer> take = values.parallelStream()
    .unordered()
    .takeWhile(n -> n % 2 == 0)
    .toList();

List<Integer> drop = values.parallelStream()
    .unordered()
    .dropWhile(n -> n % 2 == 0)
    .toList();

// take có thể chứa một tập con bất kỳ của {2, 4, 6, 8}.
// drop luôn chứa 1; các số chẵn còn lại không được cam kết.
~~~

Không được kỳ vọng `take` bằng `[2, 4]` hay `drop` bằng `[1, 6, 8]`. Cũng không nên dùng `takeWhile` trên Stream unordered để thay thế `filter`:

~~~java
List<Integer> allEven = values.stream()
    .unordered()
    .filter(n -> n % 2 == 0)
    .sorted()
    .toList();

System.out.println(allEven); // [2, 4, 6, 8]
~~~

**Phân biệt:** `filter` giữ *mọi* phần tử thỏa predicate, độc lập với encounter order. `takeWhile` có ngữ nghĩa tiền tố với ordered stream; trên unordered stream, nó được phép chỉ giữ *một tập con*.

Tương tự, nếu muốn bỏ *mọi* phần tử thỏa điều kiện `p`, dùng `filter(p.negate())` hoặc `filter(x -> !p.test(x))`, thay vì dựa vào `dropWhile` sau `unordered`.

## 7. `findFirst`, `findAny` và terminal operation có thứ tự

`findFirst()` trả về phần tử đầu tiên **nếu Stream có encounter order**. Khi Stream đã unordered, nó có thể trả về **bất kỳ phần tử nào**. `findAny()` chủ động cho phép chọn bất kỳ phần tử để tối ưu thực thi, đặc biệt trên parallel stream.

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> queue = List.of(10, 20, 30, 40);

Optional<Integer> first = queue.parallelStream()
    .findFirst(); // 10 (nguồn ordered)

Optional<Integer> any = queue.parallelStream()
    .unordered()
    .findFirst(); // Có thể là 10, 20, 30 hoặc 40.

Optional<Integer> alsoAny = queue.parallelStream()
    .findAny(); // Không bảo đảm trả phần tử đầu tiên.
~~~

Nếu cần “yêu cầu sớm nhất”, dùng `findFirst` trên nguồn được xác định thứ tự. Nếu chỉ cần “tìm một yêu cầu phù hợp bất kỳ”, `findAny` diễn đạt đúng yêu cầu và thường không cần gọi `unordered` riêng chỉ để lấy một phần tử.

### `forEach` và `forEachOrdered`

Ngay cả khi nguồn ordered, `forEach` trên parallel stream **không bảo đảm** thứ tự thực hiện action. Ngược lại, `forEachOrdered` thực hiện action theo encounter order *nếu encounter order tồn tại*:

~~~java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::println); // 1, 2, 3, 4, 5 theo thứ tự.
~~~

Sau `unordered()`, `forEachOrdered` không thể khôi phục thứ tự gốc đã bị bỏ ràng buộc:

~~~java
IntStream.rangeClosed(1, 5)
    .parallel()
    .unordered()
    .forEachOrdered(System.out::println);

// Không được mong đợi luôn in 1, 2, 3, 4, 5.
~~~

Lưu ý: `forEachOrdered` vẫn thực thi các action theo quan hệ *happens-before* giữa phần tử được xử lý trước và phần tử sau trong thứ tự do operation áp dụng; điều đó không biến Stream unordered thành Stream có thứ tự nguồn.

Nếu đầu ra cần hiển thị theo thứ tự, cách dễ kiểm tra hơn là **thu thập thành giá trị, sắp xếp rõ ràng**, rồi in/ghi dữ liệu theo trình tự đã xác định. Tác dụng phụ trong `forEach`, `peek` hoặc các lambda trung gian không phù hợp để chứng minh encounter order.

## 8. `sorted()` tạo thứ tự mới: bỏ thứ tự cũ không đồng nghĩa với không thể sắp xếp

`unordered()` cho phép Stream bỏ encounter order hiện tại, nhưng operation `sorted()` ở phía sau sẽ đưa các phần tử vào **thứ tự sắp xếp**.

~~~java
import java.util.List;

List<Integer> numbers = List.of(9, 2, 7, 4, 1, 8);

List<Integer> sortedValues = numbers.parallelStream()
    .unordered()
    .sorted()
    .toList();

System.out.println(sortedValues); // [1, 2, 4, 7, 8, 9]
~~~

Khi các phần tử có **khóa so sánh bằng nhau**, cần phân biệt “sắp xếp theo khóa” và “thứ tự hoàn toàn xác định”. API cam kết phép sort **ổn định** với ordered stream; với unordered stream không có bảo đảm về tính ổn định.

Ví dụ danh sách giao dịch có cùng mức ưu tiên:

~~~java
import java.util.Comparator;
import java.util.List;

record Ticket(int priority, String code) {}

List<Ticket> tickets = List.of(
    new Ticket(1, "B"),
    new Ticket(1, "A"),
    new Ticket(2, "C")
);

// Các ticket có cùng priority không có thứ tự tương đối được cam kết:
List<Ticket> byPriority = tickets.stream()
    .unordered()
    .sorted(Comparator.comparingInt(Ticket::priority))
    .toList();

// Muốn thứ tự xác định, dùng khóa phụ để phá hòa:
List<Ticket> deterministic = tickets.stream()
    .unordered()
    .sorted(
        Comparator.comparingInt(Ticket::priority)
            .thenComparing(Ticket::code)
    )
    .toList();

// [Ticket[priority=1, code=A], Ticket[priority=1, code=B],
//  Ticket[priority=2, code=C]]
~~~

Nếu comparator vẫn coi hai phần tử khác nhau là bằng nhau, thứ tự tương đối của chúng có thể tiếp tục không được xác định trên Stream unordered. Khi cần kết quả có thứ tự hoàn toàn, hãy chọn một bộ khóa so sánh đủ phân biệt các phần tử theo yêu cầu.

## 9. Dùng `unordered()` trong pipeline song song có chọn lọc

Bỏ ràng buộc thứ tự thường có ý nghĩa nhất khi **không cần encounter order** và có một operation phải tốn chi phí để giữ nó.

Ví dụ nghiệp vụ: một triệu mã sản phẩm có thể có mã trùng. Hệ thống chỉ cần **tập mã phân biệt**, không cần mã nào xuất hiện trước:

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Set<Integer> uniqueIds = IntStream.range(0, 1_000_000)
    .parallel()
    .map(n -> n % 10_000)
    .unordered()
    .distinct()
    .boxed()
    .collect(Collectors.toSet());

System.out.println(uniqueIds.size()); // 10000
~~~

Trong tình huống này, việc giữ thứ tự của các mã sau `distinct` không có ý nghĩa đối với kết quả `Set`. Bỏ ràng buộc có thể giúp triển khai `distinct` trên parallel stream ít bị giới hạn hơn.

Ví dụ khác: cần **bất kỳ 100 mẫu hợp lệ** trong nguồn lớn để kiểm tra nhanh:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> samples = IntStream.range(0, 1_000_000)
    .parallel()
    .unordered()
    .filter(n -> n % 100 == 0)
    .limit(100)
    .boxed()
    .toList();

// samples có 100 số chia hết cho 100, chọn từ nguồn.
// Không bảo đảm đây là 100 số nhỏ nhất.
// Đây cũng không phải mẫu ngẫu nhiên đồng đều.
~~~

Nếu yêu cầu là “100 bản ghi đầu tiên theo thời gian”, “100 khách có điểm cao nhất”, hoặc “mẫu ngẫu nhiên đúng phân phối”, các yêu cầu ấy cần một **thuật toán riêng với tiêu chí rõ ràng**. `unordered().limit(100)` không đáp ứng chúng.

### Vì sao có thể nhanh hơn?

- `distinct` trên ordered parallel stream phải giữ bản ghi đại diện xuất hiện đầu tiên theo encounter order; bỏ ràng buộc có thể giảm đồng bộ và ràng buộc trong quá trình hợp nhất.
- `limit` / `skip` trên ordered parallel stream phải xác định phần tử đầu theo thứ tự nguồn, có thể đòi hỏi phối hợp giữa nhiều nhánh.
- `takeWhile` / `dropWhile` trên ordered parallel stream phải xác định tiền tố, nên có thể tốn công phối hợp; với unordered stream, hợp đồng linh hoạt hơn.
- Nguồn vốn unordered (ví dụ `HashSet`) thường không được hưởng thêm điều gì chỉ bởi gọi `unordered()`.

Không có bảo đảm rằng gọi `unordered()` luôn nhanh hơn, dùng ít bộ nhớ hơn hay khiến Stream tự động chạy song song. Nó không thay thế `parallel()` và không giải quyết tranh chấp state, I/O chậm hay thuật toán có độ phức tạp cao.

### Đặt phép `unordered()` ở đâu?

Trong pipeline, thứ tự operation ảnh hưởng đến ngữ nghĩa:

~~~java
// Nới ràng buộc trước distinct và limit:
var anyDistinct = numbers.parallelStream()
    .unordered()
    .distinct()
    .limit(3)
    .toList();

// Sắp xếp trước khi limit để chọn 3 giá trị nhỏ nhất:
var smallestDistinct = numbers.parallelStream()
    .unordered()
    .distinct()
    .sorted()
    .limit(3)
    .toList();
~~~

Với những phần tử phân biệt, `anyDistinct` chỉ cần chọn ba phần tử bất kỳ, còn `smallestDistinct` trả ba phần tử nhỏ nhất. Nếu dữ liệu có nhiều trùng lặp, `distinct` ở cả hai pipeline sẽ loại trùng trước khi cắt.

## 10. Những hiểu nhầm và sai sót dễ gặp

### Hiểu nhầm 1: `unordered()` xáo trộn ngẫu nhiên

~~~java
List<Integer> result = List.of(1, 2, 3, 4).stream()
    .unordered()
    .toList();
~~~

Kết quả có thể vẫn là `[1, 2, 3, 4]`. Không được khẳng định thứ tự sẽ đổi và cũng không được coi `unordered` là thuật toán lấy mẫu ngẫu nhiên.

Nếu thật sự muốn trộn một danh sách, hãy dùng thuật toán shuffle phù hợp:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

List<Integer> shuffled = new ArrayList<>(List.of(1, 2, 3, 4));
Collections.shuffle(shuffled, new Random(42)); // Seed cố định để tái lập kết quả.
~~~

Shuffle ở đây nhằm tạo một hoán vị. Nó khác hoàn toàn ý nghĩa hợp đồng của `unordered()`.

### Hiểu nhầm 2: cứ thêm `unordered` là parallel stream nhanh hơn

Không phải tất cả operation đều chịu chi phí giữ thứ tự ở mức đáng kể. Với một pipeline chỉ gồm `map` và `sum`, phần lớn phép tính đã có thể thực thi độc lập khi song song, còn việc bỏ ràng buộc có thể không đem lại lợi ích thực tế.

~~~java
long sum = IntStream.range(0, 1_000_000)
    .parallel()
    .unordered()
    .mapToLong(n -> (long) n * n)
    .sum();
~~~

`sum` yêu cầu phép cộng phù hợp kiểu dữ liệu. Mặt khác, ví dụ dùng `long` để tránh tràn số `int` trong phép nhân `n * n`; với các phép gộp không kết hợp hoặc số thực dấu chấm động, cách chia nhánh có thể ảnh hưởng kết quả tính toán và độ chính xác.

### Hiểu nhầm 3: `unordered()` cho phép callback có state không an toàn

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

List<Integer> result = IntStream.range(0, 1000)
    .parallel()
    .unordered()
    .boxed()
    .peek(shared::add) // Không an toàn: nhiều thread ghi ArrayList.
    .toList();
~~~

`unordered` chỉ thay đổi yêu cầu về encounter order, **không** làm callback có tác dụng phụ trở nên thread-safe. Đừng dùng `peek` để xây dựng danh sách kết quả; `toList()` hoặc collector phù hợp mới là cách xử lý chính thức. Các behavioral parameters vẫn cần **không can thiệp** và **không trạng thái** theo hợp đồng Stream.

### Hiểu nhầm 4: `distinct()` sau `unordered()` sẽ giữ đại diện xuất hiện đầu

Chỉ có `distinct()` trên Stream ordered mới cam kết tính ổn định theo encounter order. Nếu cần đúng bản ghi đầu tiên cho mỗi khóa, hãy xác định thứ tự, khóa trùng và quy tắc chọn đại diện thay vì tin vào kết quả một lần chạy.

### Hiểu nhầm 5: `unordered()` có thể tạo thứ tự phân trang ổn định

~~~java
// Không phù hợp cho phân trang có thứ tự:
var page = numbers.parallelStream()
    .unordered()
    .skip(2)
    .limit(2)
    .toList();
~~~

Hai lần chạy có thể chọn tập phần tử khác nhau khi parallel stream thay đổi cách phân chia. Với phân trang, cần thứ tự xác định bằng khóa và tiêu chí ổn định.

## 11. Bảng chọn nhanh: có nên bỏ encounter order?

| Yêu cầu nghiệp vụ | Dùng `unordered()`? | Lý do |
| --- | --- | --- |
| Lấy 10 giao dịch sớm nhất | Không | “Sớm nhất” là ràng buộc thứ tự. |
| Tìm một giao dịch bất kỳ phù hợp | Có thể; hoặc dùng `findAny` | Không cần phần tử đầu tiên. |
| Đếm số giá trị phân biệt | Có thể | Số lượng không phụ thuộc encounter order. |
| Lấy một tập con bất kỳ từ nguồn lớn | Có thể | Chấp nhận kết quả không xác định về thành phần. |
| Lấy top N theo giá trị | Có thể trước `sorted`, sau đó `limit` | Thứ tự phải được tái thiết lập bởi comparator. |
| Cắt chuỗi xử lý khi gặp phần tử lỗi đầu tiên | Không | `takeWhile` / `dropWhile` cần ngữ nghĩa tiền tố. |
| Lấy mẫu ngẫu nhiên đồng đều | Không dùng làm thuật toán lấy mẫu | `unordered` không có bảo đảm ngẫu nhiên. |
| Phân trang kết quả cho người dùng | Không | Cần sắp xếp ổn định để tránh trang chồng lặp/thiếu. |
| Làm phẳng, map và tổng hợp không quan tâm thứ tự | Có thể, sau khi xác minh yêu cầu | Giảm ràng buộc không cần thiết, nhưng phải đo hiệu năng. |

## 12. Câu hỏi tự kiểm tra

1. **`unordered()` có xáo trộn Stream không?** Không. Nó bỏ ràng buộc encounter order; kết quả thực tế vẫn có thể giống thứ tự ban đầu.
2. **Tại sao `list.stream().limit(3)` có ý nghĩa khác `list.stream().unordered().limit(3)`?** Trường hợp đầu chọn ba phần tử đầu theo encounter order; trường hợp sau có thể chọn ba phần tử bất kỳ.
3. **Có thể dùng `unordered()` trước `distinct()` trên parallel stream để cải thiện hiệu năng không?** Có thể, khi không cần giữ phần tử đầu đại diện hoặc thứ tự kết quả; phải đo để xác nhận lợi ích thực tế.
4. **Trên unordered stream, `takeWhile` có giữ mọi phần tử thỏa predicate không?** Không. Nó có thể giữ bất kỳ tập con nào của các phần tử thỏa điều kiện; nếu cần giữ tất cả, dùng `filter`.
5. **`findFirst()` trên unordered stream luôn trả phần tử đầu danh sách gốc không?** Không. Khi không có encounter order, nó được phép trả phần tử bất kỳ.
6. **`unordered().sorted().limit(3)` có trả ba phần tử nhỏ nhất không?** Có, nếu comparator tạo thứ tự tương ứng và Stream có ít nhất ba giá trị; `sorted` thiết lập thứ tự cho đầu ra.
7. **`forEachOrdered` sau `unordered()` có khôi phục thứ tự ban đầu không?** Không. Nó chỉ tuân thủ encounter order nếu Stream có một thứ tự như vậy.
8. **Bỏ encounter order có nghĩa là lambda bên trong `map` và `peek` được phép cập nhật trạng thái dùng chung?** Không. Yêu cầu không can thiệp, không trạng thái và an toàn đồng thời vẫn áp dụng.

**Ghi nhớ:** `unordered()` là lời khai báo **“tôi không cần giữ encounter order từ đây về sau”**. Nó hữu ích khi bài toán cho phép chọn phần tử bất kỳ, loại trùng hoặc xử lý theo lô trên parallel stream. Hãy giữ thứ tự khi kết quả phụ thuộc “đầu tiên”, “theo thời gian”, “trang số N” hoặc “tiền tố”; dùng `sorted` để thiết lập thứ tự mới khi cần và kiểm tra hiệu năng bằng dữ liệu thực tế.
