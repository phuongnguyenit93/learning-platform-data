# Vì sao không sửa collection dùng chung trong reduce

## 1. Mục tiêu và vấn đề cần hiểu

`reduce` của Java Stream là phép **rút gọn** nhiều phần tử thành một kết quả bằng các hàm kết hợp. Ví dụ: tính tổng, tìm giá trị lớn nhất, tính tổng điểm theo quy tắc nghiệp vụ. Khi viết:

```java
int sum = java.util.List.of(1, 2, 3, 4)
    .parallelStream()
    .reduce(0, Integer::sum);
```

ta mô tả **cách kết hợp các giá trị** thay vì tự duy trì một biến tổng dùng chung. Nhờ đó, Stream có thể chia dữ liệu thành nhiều phần, xử lý riêng và gộp kết quả mà không cần người lập trình tự khóa một biến tổng.

Ngược lại, cách dùng `reduce` với một `ArrayList`/`HashMap` có thể thay đổi và liên tục `add`/`put` vào cùng một đối tượng thường là **sai hợp đồng của reduce**:

```java
// SAI: chỉ là đoạn minh họa, không dùng trong chương trình thật.
java.util.List<String> shared = new java.util.ArrayList<>();
java.util.List<String> result = names.parallelStream().reduce(
    shared,
    (list, name) -> {
        list.add(name);       // Thay đổi chính đối tượng nhận vào.
        return list;
    },
    (left, right) -> {
        left.addAll(right);   // Thay đổi một kết quả trung gian.
        return left;
    }
);
```

Trong đoạn trên, `names` được hiểu là một `List<String>` đã có từ trước. Không nên kết luận rằng code đúng chỉ vì đôi khi chạy tuần tự cho ra một danh sách trông hợp lý. Vấn đề nằm ở **trạng thái dùng chung, tính thuần của các hàm reduce và tính đúng đắn khi Stream phân tách công việc**.

Quy tắc cốt lõi:

> **`reduce` dùng để tạo giá trị rút gọn qua các hàm kết hợp hợp lệ; `collect` dùng cho mutable reduction, tức tạo và thay đổi các vùng chứa kết quả riêng biệt.**

Cả `reduce` và `collect` vẫn là các API đang được sử dụng trong Java hiện đại. Ví dụ chạy đầy đủ bên dưới dành cho Java 17 trở lên; các overload `reduce` và `collect` cốt lõi đã có từ Java 8.

## 2. Hợp đồng của reduce: identity, accumulator, combiner

Các dạng thường gặp:

```java
T reduce(T identity, BinaryOperator<T> accumulator);

Optional<T> reduce(BinaryOperator<T> accumulator);

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Chữ ký ở trên là **trích yếu API để học**, không phải các method có thể đặt độc lập trong một lớp và biên dịch như chương trình.

Với dạng ba tham số:

- **`identity`**: phần tử trung hòa, ví dụ `0` đối với phép cộng; cũng là kết quả khi stream rỗng.
- **`accumulator`**: nhận kết quả trung gian và một phần tử mới, **trả về** kết quả trung gian mới.
- **`combiner`**: kết hợp hai kết quả trung gian, quan trọng khi thực thi song song.

Các điều kiện về tính đúng đắn:

1. **Tính trung hòa:** `combiner.apply(identity, u)` phải tương đương `u` với mọi kết quả trung gian `u` hợp lệ. Với dạng hai tham số, `accumulator.apply(identity, t)` phải tương đương `t`.
2. **Tính kết hợp (associativity):** có thể đổi cách nhóm phép kết hợp mà vẫn thu được kết quả tương đương, ví dụ `(a + b) + c = a + (b + c)` trong bài toán số nguyên thông thường.
3. **Tính tương thích:** trong dạng ba tham số, `combiner.apply(u, accumulator.apply(identity, t))` phải tương đương `accumulator.apply(u, t)`.
4. **`Non-interfering`:** không sửa nguồn dữ liệu đang được stream duyệt; **`stateless`:** kết quả không phụ thuộc vào trạng thái bên ngoài thay đổi trong khi chạy pipeline.

Khi thực thi song song, Stream **được quyền** chia đầu vào và kết hợp các kết quả từng phần theo cách khác với vòng lặp tuần tự. Các yêu cầu trên cho phép nhiều cách phân chia đều cho cùng một kết quả đúng. Nếu một hàm vừa đổi đối tượng đang dùng làm identity, vừa thay đổi các kết quả trung gian tại chỗ, các phép đồng nhất đại số trở nên khó giữ và cùng một tham chiếu mutable có thể bị nhiều nhánh sử dụng.

**Lưu ý:** Thao tác `reduce` không hứa chạy `accumulator` theo một thứ tự tuần tự cố định. Đừng đưa hành động cần thứ tự hoặc dựa vào thời điểm thực thi vào hàm này.

## 3. Vì sao mutable collection trong reduce dễ hỏng?

### 3.1. `identity` là giá trị cung cấp sẵn, không phải một factory

`reduce(new ArrayList<>(), ...)` nhận **một đối tượng cụ thể** làm `identity`, không nhận một `Supplier` để cấp một danh sách mới cho từng nhánh. Nếu nhiều phần của phép rút gọn dùng chung tham chiếu này, cùng một `ArrayList` có thể bị thay đổi từ nhiều luồng. `ArrayList` thông thường không được thiết kế cho cập nhật đồng thời.

Một hình dung về khả năng thực thi song song (không phải lịch thực thi bắt buộc):

```text
                  identity = cùng List L
                     /           \
            nhánh xử lý 1      nhánh xử lý 2
            L.add("A")         L.add("B")
                     \           /
                combiner(L, L)?
```

Ở trường hợp `left` và `right` cùng trỏ tới `L`, câu lệnh `left.addAll(right)` còn có thể nhân đôi dữ liệu thay vì gộp hai kết quả độc lập. Thứ tự và số lượng phần tử thực tế phụ thuộc vào cách thực thi, vì vậy **không có đầu ra cố định nào được bảo đảm cho code sai**. Khi cập nhật đồng thời, còn có nguy cơ mất dữ liệu hoặc hành vi không ổn định.

### 3.2. Side effect phá ý nghĩa phép reduce

Ở một hàm đúng kiểu rút gọn giá trị:

```java
(a, b) -> a + b
```

đầu vào không bị thay đổi. Trong khi đó:

```java
(list, item) -> {
    list.add(item);
    return list;
}
```

trả về lại **chính đối tượng đã bị sửa**. Kết quả của lần gọi sau có thể chịu ảnh hưởng của những lần gọi khác và của các alias bên ngoài. Đây không phải cách biểu đạt phép rút gọn không có trạng thái mà Stream API yêu cầu.

Cách viết `new ArrayList<>(list)` trước khi thêm phần tử có thể tránh sửa chính đối tượng truyền vào, nhưng liên tục sao chép cả danh sách thường tốn bộ nhớ và thời gian; nếu mục tiêu là tạo collection thì **`collect` diễn đạt ý định rõ ràng và hiệu quả hơn**.

### 3.3. Đồng bộ hóa không tự sửa hợp đồng đại số

Bọc identity bằng `Collections.synchronizedList(...)` có thể giúp đồng bộ các lời gọi cập nhật riêng lẻ, nhưng **không tự sửa** việc dùng chung identity, vấn đề alias, ràng buộc identity/combiner hoặc thứ tự kết quả. Bài toán không chỉ là thiếu khóa.

## 4. Ví dụ chạy được: code sai có thể trông đúng khi sequential

Lưu **BadReduceDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class BadReduceDemo {
    public static void main(String[] args) {
        List<String> seed = new ArrayList<>();

        // Ví dụ cố ý SAI để quan sát tác dụng phụ.
        List<String> result = List.of("A", "B").stream().reduce(
            seed,
            (acc, value) -> {
                acc.add(value);
                return acc;
            },
            (left, right) -> {
                left.addAll(right);
                return left;
            }
        );

        System.out.println("same object: " + (seed == result));
        System.out.println("seed after: " + seed);
    }
}
```

```bash
javac BadReduceDemo.java
java BadReduceDemo
```

Đầu ra với pipeline tuần tự trong ví dụ:

```text
same object: true
seed after: [A, B]
```

**Giải thích:** `seed` vốn là danh sách trống, nhưng sau terminal operation nó đã bị thay đổi. `result` và `seed` cùng trỏ đến một đối tượng. Output `[A, B]` trông đúng nhưng che giấu side effect. Việc thay `stream()` thành `parallelStream()` không phải phép biến đổi an toàn: lúc đó runtime có thể thực hiện tích lũy và kết hợp theo nhiều nhánh. Không lấy đầu ra của một lần chạy parallel làm chứng cứ thuật toán đúng.

**Ghi nhớ cách phát hiện:** Nếu `accumulator` hoặc `combiner` của `reduce` gọi `add`, `addAll`, `put`, `append` trên một đối tượng mutable được cấp làm `identity`, hãy xem lại thiết kế. Với mục tiêu tạo collection, gần như luôn nên chuyển sang `collect`.

## 5. Giải pháp 1: reduce trên giá trị không bị sửa

Khi đích là **một giá trị tổng hợp**, dùng kết hợp trả về giá trị mới và không sửa nguồn.

Lưu **PureReduceDemo.java**:

```java
import java.util.List;

public class PureReduceDemo {
    public static void main(String[] args) {
        List<Integer> scores = List.of(1, 2, 3, 4);

        int sum = scores.parallelStream()
                        .reduce(0, Integer::sum);

        int doubledSum = scores.parallelStream()
            .reduce(
                0,
                (subtotal, n) -> subtotal + n * 2,
                Integer::sum
            );

        System.out.println("sum=" + sum);
        System.out.println("doubled=" + doubledSum);
    }
}
```

```bash
javac PureReduceDemo.java
java PureReduceDemo
```

Đầu ra xác định:

```text
sum=10
doubled=20
```

Ở cả hai phép rút gọn, mỗi lần kết hợp tạo ra kết quả số mới về mặt giá trị; không có `ArrayList`/`Map` dùng chung để bị sửa. `0` là phần tử trung hòa của phép cộng, và `Integer::sum` có tính kết hợp theo phép cộng số nguyên Java; nhờ vậy cách chia nhóm trong parallel không làm đổi kết quả của các dữ liệu này.

Nếu chỉ tính tổng từ phần tử số nguyên, còn có cách ngắn gọn:

```java
// Đoạn minh họa, không phải chương trình Java độc lập.
int total = scores.parallelStream().mapToInt(Integer::intValue).sum();
```

`mapToInt(...).sum()` làm rõ ý định tính tổng; không cần dùng dạng ba tham số khi phép toán đơn giản.

## 6. Giải pháp 2: collect tạo collection đúng cách

**Mutable reduction là việc hợp lệ**, nhưng phải có cơ chế tạo và hợp nhất các vùng chứa độc lập. API được thiết kế cho việc này là `collect`:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
);
```

Đây là chữ ký khái niệm; trong chương trình thực tế, `Stream.collect` đã được khai báo sẵn.

- **`supplier`:** tạo **container mới** mỗi lần được gọi, ví dụ `ArrayList::new`.
- **`accumulator`:** thay đổi container trung gian được cấp cho nó để đưa phần tử vào, ví dụ `ArrayList::add`.
- **`combiner`:** gộp các container trung gian, ví dụ `ArrayList::addAll`.

Điểm khác biệt quan trọng: với parallel stream và collector thông thường không có `CONCURRENT`, mỗi container trung gian do supplier tạo được sử dụng riêng cho phần tích lũy phù hợp rồi được kết hợp. Vì thế có thể dùng `ArrayList` làm container trung gian mà không phải dùng một `ArrayList` duy nhất cho tất cả luồng.

Lưu **SafeCollectDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class SafeCollectDemo {
    public static void main(String[] args) {
        List<String> input = List.of("an", "binh", "chi");

        // Cách 1: collector chuẩn, chỉ rõ cần ArrayList có thể sửa.
        List<String> mutable = input.parallelStream()
            .map(String::toUpperCase)
            .collect(Collectors.toCollection(ArrayList::new));

        // Cách 2: ba hàm của mutable reduction.
        List<String> manual = input.parallelStream()
            .map(String::toUpperCase)
            .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);

        // Cách 3: chỉ cần List kết quả không cho sửa (Java 16+).
        List<String> readOnly = input.parallelStream()
            .map(String::toUpperCase)
            .toList();

        System.out.println("mutable=" + mutable);
        System.out.println("manual=" + manual);
        System.out.println("readOnly=" + readOnly);
        System.out.println("input=" + input);
    }
}
```

```bash
javac SafeCollectDemo.java
java SafeCollectDemo
```

Đầu ra xác định:

```text
mutable=[AN, BINH, CHI]
manual=[AN, BINH, CHI]
readOnly=[AN, BINH, CHI]
input=[an, binh, chi]
```

**Giải thích:**

1. Nguồn `List` có encounter order; các cách gom kết quả trên bảo toàn thứ tự phần tử cho ví dụ này dù xử lý song song.
2. `Collectors.toCollection(ArrayList::new)` tạo kết quả kiểu `ArrayList` theo yêu cầu, có thể tiếp tục chỉnh sửa sau khi thu thập.
3. `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` minh họa cơ chế tạo container, thêm phần tử và gộp container.
4. `Stream.toList()` (có từ Java 16) trả danh sách **unmodifiable**; đừng dùng nếu sau đó phải gọi `add` hoặc `remove`. Khi đang học riêng API Java 8, có thể dùng `collect(Collectors.toList())`, nhưng **không được giả định** collector này cam kết một implementation hay khả năng chỉnh sửa cụ thể.
5. `input` vẫn là `[an, binh, chi]`: pipeline không sửa nguồn.

Ví dụ dùng `ArrayList` ở `collect` là **đúng** dù `ArrayList` không thread-safe, vì chương trình không cố ý đưa cùng một container vào mọi nhánh. Quan trọng là `supplier` phải cung cấp đối tượng mới mỗi lần; nếu viết `() -> sharedList` thì ta lại đưa trạng thái dùng chung vào phép gom và tự phá tính an toàn.

## 7. Phân biệt ba trường hợp thường bị nhầm

| Việc làm | Đúng/sai và lý do |
| --- | --- |
| `parallelStream().reduce(0, Integer::sum)` | **Đúng:** tính toán dựa trên các giá trị với identity và phép kết hợp phù hợp. |
| `parallelStream().reduce(new ArrayList<>(), (l,x) -> { l.add(x); return l; }, ...)` | **Sai:** thay đổi identity mutable, gây alias và có thể bị các nhánh song song dùng chung. |
| `parallelStream().collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` | **Đúng:** vùng chứa kết quả mới được tạo bởi supplier, rồi gộp các kết quả trung gian. |
| `parallelStream().forEach(sharedList::add)` với `ArrayList` bên ngoài | **Sai:** nhiều hành động trực tiếp sửa collection chung, có nguy cơ data race; thứ tự cũng không được bảo đảm. |
| `parallelStream().map(...).collect(Collectors.toCollection(ArrayList::new))` | **Đúng:** chuyển đổi các phần tử và thu thập bằng collector có cơ chế mutable reduction. |
| `stream().map(x -> { source.add(x); return x; })` khi `source` là collection đang duyệt | **Sai:** can thiệp vào nguồn đang được stream đọc; vi phạm yêu cầu non-interfering. |

Không đánh đồng **container được tạo riêng để collect** với **collection bên ngoài bị nhiều nhánh cùng sửa**. Java Stream không cấm mọi thao tác thay đổi trạng thái; nó yêu cầu thay đổi trạng thái phải đặt đúng chỗ và tuân thủ hợp đồng của operation.

## 8. Vì sao sửa nguồn trong pipeline cũng nguy hiểm?

Giả sử có danh sách `source` dùng làm đầu vào:

```java
// SAI: chỉ minh họa việc can thiệp vào collection đang được duyệt.
java.util.List<Integer> source =
    new java.util.ArrayList<>(java.util.List.of(1, 2, 3));
source.stream().map(n -> {
    source.add(n + 10);
    return n;
}).toList();
```

Đây là ví dụ **không nên chạy trong mã thực tế**. Việc thêm phần tử khi stream đang duyệt `source` có thể gây `ConcurrentModificationException` hoặc biểu hiện không đáng tin, tùy nguồn và cách thực thi. Ngay cả khi không có ngoại lệ, pipeline vẫn vi phạm điều kiện non-interfering.

Thay vào đó, hãy tạo **kết quả riêng**:

```java
// Đoạn minh họa: xây List mới từ source, không sửa source.
java.util.List<Integer> transformed = source.stream()
    .map(n -> n + 10)
    .toList();
```

Nếu thực sự muốn cập nhật collection gốc, hãy hoàn tất việc đọc/tạo dữ liệu cần thiết trước rồi áp dụng một bước cập nhật rõ ràng, có kiểm soát. Đừng thực hiện cập nhật nguồn trong callback của stream đang đọc nguồn đó.

## 9. Những trường hợp đặc biệt và giới hạn

**9.1. Mutable object có bao giờ được dùng với reduce không?** Không phải tên lớp quyết định đúng/sai; điều quan trọng là hàm giảm có giữ được tính kết hợp, tính trung hòa, trạng thái độc lập và không can thiệp nguồn hay không. Tuy nhiên, nếu dữ liệu đang được tích lũy bằng cách **sửa trực tiếp một collection**, `collect` là API thích hợp, dễ chứng minh đúng và dễ bảo trì hơn.

**9.2. Nếu chạy tuần tự thì có thể bỏ qua hợp đồng không?** Không. Một chương trình sai hợp đồng có thể cho kết quả nhìn đúng khi sequential, nhưng dễ hỏng khi tái cấu trúc thành parallel, thay đổi cách chia việc hoặc khi đối tượng identity được sử dụng ở nơi khác. Viết đúng hợp đồng từ đầu.

**9.3. Thêm `synchronized` có giải quyết được không?** Việc khóa chỉ giải quyết một phần truy cập đồng thời, không bảo đảm các hàm reduction có ý nghĩa đại số đúng. Trong nhiều trường hợp, khóa còn làm mất lợi ích parallel.

**9.4. Collector nào cũng cho phép nhiều thread sửa cùng một container?** Không. Với phép gom thông thường, runtime có thể tạo nhiều container trung gian và gộp lại. Một số collector có đặc tính `CONCURRENT` có thể cho phép tích lũy vào container chung theo hợp đồng riêng của collector; khi tự viết collector kiểu đó, tác giả phải thiết kế đúng về đồng thời, không thể dùng `ArrayList` chia sẻ tùy tiện.

**9.5. Nếu cần giữ thứ tự gốc?** Xem encounter order của nguồn và đặc tính collector. Ví dụ từ `List` ordered kết hợp với các cách gom trong `SafeCollectDemo` giữ thứ tự; nhưng kết quả của `forEach` với parallel stream không được bảo đảm theo thứ tự. Nếu thứ tự là yêu cầu nghiệp vụ, đừng dùng `unordered()` hoặc giả định một nguồn như `HashSet` có thứ tự ổn định.

**9.6. `reduce` với toán tử không kết hợp thì sao?** Dù không sửa collection, cách rút gọn vẫn có thể sai khi dùng phép không có tính kết hợp như trừ liên tiếp. Ví dụ `(10 - 3) - 2` khác `10 - (3 - 2)`. Đừng dùng `reduce` parallel với hàm không thỏa associativity và kỳ vọng cùng kết quả như vòng lặp tuần tự.

## 10. Quy trình chọn operation trong code review

Khi gặp một stream cần trả về kết quả, tự hỏi:

1. **Cần một scalar/summary** như tổng, min/max, điểm tổng hợp? → Dùng `reduce` với identity trung hòa và các hàm kết hợp hợp lệ; với tổng số nguyên có thể cân nhắc `mapToInt(...).sum()`.
2. **Cần tạo `List`, `Set`, `Map`, `StringBuilder` hoặc nhóm phần tử?** → Dùng `collect` với collector phù hợp, ví dụ `Collectors.toCollection`, `Collectors.toMap`, `Collectors.groupingBy` hoặc `Collectors.joining`.
3. **Có collection được khai báo bên ngoài pipeline và bị callback thêm/xóa phần tử?** → Kiểm tra ngay nguy cơ shared mutable state; thay bằng kết quả của `collect` hoặc xử lý tuần tự có chủ đích nếu thực sự cần side effect.
4. **Có thay đổi collection nguồn khi pipeline đang chạy?** → Cần bỏ hành vi gây interference, trừ khi dùng một nguồn concurrent được thiết kế và hợp đồng Stream cho phép; thông thường hãy tạo collection kết quả riêng.
5. **Có chạy parallel?** → Đảm bảo identity/accumulator/combiner thỏa hợp đồng, các collector tạo container độc lập khi cần, và thực sự đo hiệu năng trước khi kết luận parallel tốt hơn.

### Tự kiểm tra

**Câu 1.** Đoạn sau đúng hay sai?

```java
// Chỉ minh họa, input đã được định nghĩa là List<String>.
List<String> out = input.parallelStream()
    .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

**Trả lời:** Đúng; `collect` có `supplier` tạo container mới. Cần thêm import phù hợp trong chương trình thực tế.

**Câu 2.** Có nên giữ `new ArrayList<>()` làm identity trong `reduce` rồi sửa nó bằng `add` nếu chỉ chạy sequential?

**Trả lời:** Không nên. Cách này làm thay đổi identity, vi phạm ý nghĩa rút gọn dựa trên các hàm hợp lệ, và không an toàn khi pipeline có thể chạy parallel.

**Câu 3.** Tại sao `Collections.synchronizedList` không tự sửa được `reduce` sai?

**Trả lời:** Bởi vì thread safety của vài lời gọi `add` không giải quyết hợp đồng identity, các alias và chức năng của combiner. Nên đổi thuật toán sang `collect` phù hợp.

**Câu 4.** Khác biệt quan trọng giữa `reduce` và `collect` là gì?

**Trả lời:** `reduce` biểu diễn phép kết hợp các **giá trị** theo hợp đồng trung hòa/kết hợp; `collect` biểu diễn mutable reduction bằng cơ chế **tạo container, tích lũy, gộp**. Việc sửa mutable container riêng trong `collect` là hợp lệ; sửa cùng collection được dùng chung giữa các nhánh trong `reduce` là thiết kế sai.

## Tài liệu tham khảo API đang áp dụng

- [Oracle Java SE 25 — Stream API: `reduce` và `collect`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
- [Oracle Java SE 25 — Stream package: reduction, mutable reduction, non-interference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html).
- [Oracle Java SE 25 — Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html).

**Kết luận cần nhớ:** Tránh đưa collection mutable dùng chung vào `reduce`. Nếu muốn gom phần tử thành collection, hãy để `collect` tạo các vùng chứa đúng cách; nếu muốn tính một giá trị tổng hợp, hãy dùng `reduce` với identity trung hòa và accumulator/combiner không có side effect phá hợp đồng.