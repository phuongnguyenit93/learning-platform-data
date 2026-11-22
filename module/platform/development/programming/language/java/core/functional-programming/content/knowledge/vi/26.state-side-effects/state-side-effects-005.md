# Dùng `collect()` thay cho bộ tích lũy bên ngoài trong Java Stream

Trong lập trình hàm với Java Stream, một lỗi phổ biến là tạo `List`, `Map`, bộ đếm hoặc `StringBuilder` ở **bên ngoài pipeline**, rồi dùng `forEach()`, `map()` hoặc `peek()` để cập nhật chúng. Mã đó có thể có vẻ hoạt động khi chạy tuần tự, nhưng trở nên khó kiểm thử, phụ thuộc trạng thái và dễ gặp **race condition** khi chuyển sang `parallelStream()`.

`collect()` là terminal operation dùng để **gom phần tử thành kết quả** theo một hợp đồng rõ ràng. Thay vì để lambda tự ý thay đổi một biến bên ngoài, ta giao việc tạo, cập nhật và gộp các container kết quả cho cơ chế thu thập của Stream.

Mục tiêu của bài: nhận diện bộ tích lũy bên ngoài, chuyển thành `collect()` thích hợp, hiểu cách thu thập tuần tự/song song, và chọn giữa `collect()`, `reduce()` cùng các API tổng hợp chuyên biệt.

## 1. Thế nào là bộ tích lũy bên ngoài?

Một bộ tích lũy bên ngoài (*external accumulator*) là trạng thái được khai báo ngoài pipeline nhưng bị callback trong pipeline thay đổi:

```java
List<String> result = new ArrayList<>();

names.stream()
        .filter(name -> !name.isBlank())
        .forEach(name -> result.add(name.trim()));
```

Đây là **đoạn minh họa cần các import** `java.util.List`, `java.util.ArrayList` và một biến `names` kiểu `List<String>`; không phải chương trình độc lập.

Với một stream tuần tự, danh sách có thể chứa đúng các tên mong muốn. Tuy vậy:

- Kết quả là tác dụng phụ trên `result`, không phải giá trị do pipeline trả về.
- Logic biến đổi và logic quản lý trạng thái bị trộn chung.
- Ai khác giữ tham chiếu tới `result` có thể quan sát hoặc sửa nó trong lúc xử lý.
- Việc thay `stream()` thành `parallelStream()` làm nhiều callback có thể cùng gọi `ArrayList.add`: **không an toàn khi ghi đồng thời**.

Nếu bài toán chỉ cần một list kết quả, hãy viết theo hướng dữ liệu:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::trim)
        .toList();
```

Ở đây, `filter()` và `map()` không sửa trạng thái bên ngoài; terminal `toList()` thu các kết quả thành một danh sách. Lưu ý `Stream.toList()` từ Java 16 trả list **không thể sửa**.

Nếu muốn sử dụng `collect()`:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::trim)
        .collect(Collectors.toList());
```

Đoạn này cần `import java.util.stream.Collectors;`. `Collectors.toList()` không bảo đảm một loại list, khả năng thay đổi hay thread-safety cụ thể. Nếu cần `ArrayList` có thể sửa, dùng `Collectors.toCollection(ArrayList::new)`.

## 2. `collect()` đưa trạng thái về bên trong cơ chế Stream

Với `Stream<T>`, hai nhóm API thường gặp:

```java
<R,A> R collect(Collector<? super T,A,R> collector)

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R,? super T> accumulator,
        BiConsumer<R,R> combiner
)
```

Đây là **chữ ký API rút gọn**, không phải class Java độc lập.

Dạng nhận `Collector` là phổ biến nhất:

```java
Map<String, Long> counts = names.stream()
        .collect(Collectors.groupingBy(
                String::trim,
                Collectors.counting()
        ));
```

Pipeline mô tả: phân nhóm theo chuỗi sau `trim`, sau đó đếm mỗi nhóm. Không cần tạo `HashMap` trước rồi cập nhật bằng tay.

Dạng ba đối số cung cấp ba hành vi cụ thể:

1. **`supplier`** tạo container kết quả mới.
2. **`accumulator`** đưa một phần tử đầu vào container đó.
3. **`combiner`** gộp hai container trung gian khi cần.

Ví dụ:

```java
List<String> labels = names.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
```

Đây là snippet bên trong phương thức, cần `java.util.List`, `java.util.ArrayList`. Mỗi container do supplier tạo là một `ArrayList` mới; `List::add` cập nhật container đang được Stream quản lý, không cập nhật một list chia sẻ do bên ngoài tạo trước; `List::addAll` gộp các danh sách trung gian.

**Quan trọng:** `combiner` của dạng `collect(supplier, accumulator, combiner)` có kiểu **`BiConsumer<R,R>` trả `void`**, khác với `BinaryOperator<A>` **trả về `A`** trong custom `Collector.of(...)`.

## 3. Ví dụ Java 17+ chạy hoàn chỉnh

Lưu thành tệp `CollectInsteadOfSideEffectsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class CollectInsteadOfSideEffectsDemo {
    record Order(String region, String code, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("HN", "A", 2),
                new Order("HCM", "B", 4),
                new Order("HN", "C", 3)
        );

        List<String> labels = orders.parallelStream()
                .map(order -> order.code() + "=" + order.quantity())
                .collect(
                        ArrayList::new,
                        List::add,
                        List::addAll
                );

        Map<String, Integer> totalsByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.summingInt(Order::quantity)
                ));

        int totalQuantity = orders.parallelStream()
                .mapToInt(Order::quantity)
                .sum();

        List<Integer> largeQuantities = orders.stream()
                .filter(order -> order.quantity() >= 3)
                .map(Order::quantity)
                .toList();

        String codes = orders.stream()
                .map(Order::code)
                .collect(Collectors.joining(","));

        System.out.println("labels = " + labels);
        System.out.println("totalsByRegion = " + totalsByRegion);
        System.out.println("totalQuantity = " + totalQuantity);
        System.out.println("largeQuantities = " + largeQuantities);
        System.out.println("codes = " + codes);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 CollectInsteadOfSideEffectsDemo.java
java CollectInsteadOfSideEffectsDemo
```

Stdout chính xác:

```text
labels = [A=2, B=4, C=3]
totalsByRegion = {HCM=4, HN=5}
totalQuantity = 9
largeQuantities = [4, 3]
codes = A,B,C
```

**Vì sao kết quả này ổn định?**

- Nguồn `List` có encounter order; phép `map` không đổi thứ tự logic. `collect(ArrayList::new, List::add, List::addAll)` trên ordered stream duy trì thứ tự kết quả `A=2, B=4, C=3`, dù việc xử lý có thể diễn ra song song.
- `groupingBy(..., TreeMap::new, summingInt(...))` tổng hợp số lượng theo khu vực và yêu cầu `TreeMap` sắp xếp key: `HCM` trước `HN`. Tổng HN là `2 + 3 = 5`.
- `mapToInt(...).sum()` là phép rút gọn nguyên thủy thích hợp để tính tổng; không cần một `AtomicInteger` bên ngoài.
- `toList()` thu kết quả của `filter`/`map` thành một list theo thứ tự nguồn.
- `joining(",")` kết hợp chuỗi trực tiếp, tránh tự quản lý `StringBuilder` ở ngoài.

Ví dụ sử dụng những collector chuẩn và phép toán tổng hợp đã được Java thiết kế phù hợp với cơ chế Stream. Không cần tự đồng bộ hóa một collection dùng chung.

## 4. Vì sao `parallelStream().forEach(list::add)` không phải `collect()`?

Một ví dụ **sai thiết kế**:

```java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(output::add);
```

Đây là đoạn minh họa đặt trong phương thức, cần `java.util.List`, `java.util.ArrayList` và `java.util.stream.IntStream`. `ArrayList` không hỗ trợ ghi đồng thời từ nhiều luồng nếu không đồng bộ; kết quả có thể mất phần tử, thứ tự bất định, thậm chí có lỗi trong quá trình cập nhật. **Không chạy mã này để lấy dữ liệu đáng tin cậy.**

Bản đúng, không cần biến chia sẻ:

```java
List<Integer> output = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
```

Hoặc, nếu cần một `ArrayList` cụ thể có thể sửa:

```java
List<Integer> output = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
```

Cả hai phương án dùng ordered `IntStream.range`, nên kết quả list có các số từ `0` đến `9_999` theo encounter order. Bản `toList` không sửa được; bản `toCollection(ArrayList::new)` trả một `ArrayList` mutable.

### `Collections.synchronizedList(...)` hoặc `AtomicInteger` có giải quyết mọi vấn đề không?

Không. Một list đồng bộ hóa có thể làm thao tác `add` an toàn khỏi race khi nhiều luồng cập nhật, nhưng:

- Thứ tự các lời gọi `forEach` trên parallel stream **không được bảo đảm** theo encounter order.
- Logic vẫn phụ thuộc vào tác dụng phụ bên ngoài; dễ gây khó khăn khi tái sử dụng hoặc kiểm thử.
- Đồng bộ hóa có thể trở thành điểm tranh chấp khi dữ liệu lớn.

Tương tự, `AtomicInteger` giúp thao tác cộng vào một bộ đếm dùng chung có tính nguyên tử, nhưng việc dùng nó trong `map` hoặc `peek` không biến pipeline thành phép tổng hợp rõ nghĩa; các callback trung gian có thể bị tối ưu hóa hoặc short-circuit theo terminal operation.

Nếu mục tiêu là đếm phần tử, dùng `count()`; nếu mục tiêu là tổng số nguyên, dùng `mapToInt(...).sum()`; nếu mục tiêu là nhiều thống kê, chọn downstream collector tương ứng.

## 5. Tư duy “mỗi nhánh có container riêng” khi thu thập song song

Một collector đúng cho phép Java tổ chức việc tích lũy giống như sau:

```text
Nguồn có thứ tự:  A  B  C  D
                   \ /   \ /
                nhóm 1  nhóm 2
                   |       |
             supplier() supplier()
                   |       |
                add A,B  add C,D
                   \       /
                    combiner
                       |
                 [A, B, C, D]
```

Sơ đồ chỉ là mô hình: Java có thể chia thành số nhóm khác và thực thi các callback trên các luồng khác nhau.

Tính đúng đòi hỏi:

- **Supplier** cung cấp container ban đầu phù hợp; với collection mutable, mỗi lần gọi phải tạo container độc lập, không trả về cùng một instance chia sẻ.
- **Accumulator** cập nhật container được cung cấp; không sửa nguồn stream hoặc một trạng thái dùng chung khác.
- **Combiner** gộp tất cả dữ liệu quan trọng của hai container và không đánh mất hay nhân đôi phần tử.
- **Identity và associativity**: gộp với container rỗng không đổi kết quả; đổi cách chia/gộp các nhóm không đổi kết quả quan sát được theo hợp đồng thứ tự.

Không phải `ArrayList` bỗng trở thành thread-safe khi dùng `collect`. Điểm khác biệt là Stream có thể **quản lý container riêng cho từng nhánh** của collector không mang characteristic `CONCURRENT`, rồi gộp chúng. Chẳng hạn `Collectors.toList()` dùng được với parallel stream mà không yêu cầu một `ArrayList` chung cho mọi luồng.

## 6. Dùng collector chuẩn trước khi tự viết collector

Hầu hết bài toán thông dụng đã có collector sẵn:

| Cần kết quả | Giải pháp |
| --- | --- |
| Danh sách phần tử | `toList()` hoặc `collect(Collectors.toList())` |
| `ArrayList` mutable | `collect(Collectors.toCollection(ArrayList::new))` |
| Tập phần tử phân biệt | `collect(Collectors.toSet())` |
| Tập có thứ tự tự nhiên | `collect(Collectors.toCollection(TreeSet::new))` |
| Chuỗi nối với dấu phân cách | `collect(Collectors.joining(","))` |
| Nhóm theo thuộc tính | `collect(Collectors.groupingBy(keyFn))` |
| Nhóm và đếm | `collect(Collectors.groupingBy(keyFn, Collectors.counting()))` |
| Nhóm rồi tính tổng | `collect(Collectors.groupingBy(keyFn, Collectors.summingInt(valueFn)))` |
| Chia thành hai nhánh `true/false` | `collect(Collectors.partitioningBy(predicate))` |
| Thống kê count/sum/min/max/average | `collect(Collectors.summarizingInt(valueFn))` |

`Collectors.toSet()` không bảo đảm loại set hoặc thứ tự iteration. `Collectors.toList()` không có cam kết chung về khả năng sửa list. Khi cần một cấu trúc cụ thể, chọn `toCollection(factory)` hoặc overload `groupingBy(classifier, mapFactory, downstream)`.

**Chú ý lỗi trùng key:** `Collectors.toMap(keyFn, valueFn)` hai đối số thường ném `IllegalStateException` nếu sinh key trùng. Nếu dữ liệu có nhiều bản ghi cùng key, hãy dùng `groupingBy` hoặc cung cấp merge function rõ nghĩa cho `toMap`.

## 7. Khi nào nên viết `Collector.of(...)`?

Nếu cần tích lũy nhiều trường và tạo một kết quả riêng, custom collector có thể phù hợp. Ví dụ gom **số lượng bản ghi** và **tổng số sản phẩm** chỉ trong một lượt:

```java
import java.util.List;
import java.util.stream.Collector;

public class CustomCollectExample {
    record Order(int quantity) {}
    record Summary(long count, long total) {}

    static final class Acc {
        long count;
        long total;

        void add(Order order) {
            count++;
            total += order.quantity();
        }

        Acc merge(Acc other) {
            count += other.count;
            total += other.total;
            return this;
        }

        Summary finish() {
            return new Summary(count, total);
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(new Order(2), new Order(3));

        Collector<Order, Acc, Summary> collector = Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish
        );

        Summary summary = orders.parallelStream().collect(collector);
        System.out.println(summary);
    }
}
```

Lưu file `CustomCollectExample.java`, chạy:

```bash
javac CustomCollectExample.java
java CustomCollectExample
```

Stdout:

```text
Summary[count=2, total=5]
```

Ở đây `Acc` mutable **chỉ là trạng thái nội bộ do collector sở hữu**. Bên ngoài pipeline chỉ nhận `Summary` là record giá trị, không nhận một accumulator đang được cập nhật dở.

`Acc::merge` gộp đầy đủ cả hai trường nên kết quả không phụ thuộc cách chia nhánh. Nếu supplier bắt đầu với `count=1`, hoặc combiner cộng thêm một số không thuộc dữ liệu, chạy song song có thể bị đếm thừa. Nếu `Acc` không thread-safe, **không** khai báo `Collector.Characteristics.CONCURRENT`.

Custom collector không phải lựa chọn đầu tiên cho những phép `sum()`, `count()` hoặc `joining()` đơn giản; API chuẩn thường ngắn và ít rủi ro hơn.

## 8. Phân biệt `collect()` và `reduce()`

Hai terminal operation đều tổng hợp dữ liệu nhưng phục vụ các cách tích lũy khác nhau:

| Tiêu chí | `reduce()` | `collect()` |
| --- | --- | --- |
| Bản chất | **Rút gọn giá trị** bằng một phép toán kết hợp | **Thu thập vào container** và có thể biến đổi thành kết quả cuối |
| Trạng thái tích lũy | Thường nên bất biến và được thay bằng giá trị mới | Có thể là container mutable bên trong collector |
| Identity | Giá trị đơn vị của phép kết hợp | Trạng thái container trống do supplier tạo |
| Parallel | Yêu cầu phép toán associative, identity đúng | Yêu cầu supplier, accumulator, combiner đúng hợp đồng |
| Ví dụ | `reduce(0, Integer::sum)` | `collect(Collectors.toList())` |

Không dùng `reduce` với một `ArrayList` hoặc `StringBuilder` mutable **làm identity dùng chung** rồi mutate nó trong accumulator; cách này dễ vi phạm hợp đồng reduce khi song song. Thay vào đó, dùng `collect()` với supplier tạo container mới.

Đối với các phép chuyên biệt, ưu tiên API ngắn nhất:

```java
long count = orders.stream().count();
int total = orders.stream().mapToInt(Order::quantity).sum();
```

Đây là snippet trong class có record `Order` và biến `orders` như ví dụ đầy đủ. Không cần `collect` chỉ để đếm hay tính tổng.

## 9. `map`/`peek` không phải nơi thực thi logic tích lũy bắt buộc

Một anti-pattern thường gặp:

```java
AtomicInteger counter = new AtomicInteger();

long count = Stream.of("A", "B", "C")
        .peek(x -> counter.incrementAndGet())
        .count();
```

Đây là snippet minh họa **sai thiết kế** và cần `java.util.concurrent.atomic.AtomicInteger`, `java.util.stream.Stream`. Trên các nguồn có kích thước đã biết, implementation có thể tính `count()` mà **không gọi `peek` cho mọi phần tử**; vì vậy `counter` không được xem như bộ đếm đáng tin cậy của pipeline. Một biến nguyên tử không bảo đảm rằng các callback sẽ chạy.

Tương tự, dùng `map(x -> { externalList.add(x); return x; })` để ghi side effect là dễ sai khi pipeline bị short-circuit bởi `limit`, `findFirst`, `anyMatch` hoặc có tối ưu hóa. Kết quả đúng phải được suy ra từ **terminal operation được định nghĩa rõ**.

Nếu thật sự cần ghi file, gọi HTTP hay gửi thông báo, hãy đặt hành động ở ranh giới được điều phối có chủ ý với chính sách lỗi/retry, không cố thay `collect` thành một lệnh I/O ẩn trong `peek`.

## 10. Tính đúng khi có encounter order và parallelism

- `parallelStream()` không tự làm mất encounter order của `List`. Nếu collector giữ thứ tự, danh sách kết quả có thể vẫn theo thứ tự nguồn, dù callback chạy đồng thời.
- `parallelStream().forEach(action)` **không bảo đảm** thứ tự gọi `action` theo encounter order. Dùng nó để thêm vào list ngoài là sai cả về thread-safety và yêu cầu thứ tự.
- `forEachOrdered(action)` có thể yêu cầu các action chạy theo encounter order, nhưng nếu chỉ cần **một danh sách kết quả**, `collect` hoặc `toList` thể hiện ý định rõ hơn và dễ kiểm thử hơn.
- `Collectors.groupingByConcurrent(...)` có đặc tính concurrent/unordered; không nên mặc định nó giữ thứ tự phần tử trong từng nhóm. Chỉ sử dụng khi không yêu cầu encounter order hoặc đã thiết kế xử lý phù hợp.
- `Collector.Characteristics.CONCURRENT` chỉ được khai báo khi accumulator thật sự có thể bị gọi đồng thời trên cùng một container mà vẫn đúng. Một collector dùng được với parallel stream **không nhất thiết** có đặc tính này.

Đừng tự động chuyển mọi pipeline sang song song với kỳ vọng nhanh hơn. Với dữ liệu nhỏ, công việc nhẹ hoặc collector phải phối hợp thứ tự nghiêm ngặt, chi phí phân chia/gộp có thể lớn hơn lợi ích. Chọn cách viết đúng, sau đó đo hiệu năng bằng dữ liệu thực.

## 11. Kiểm thử hành vi thay vì kiểm tra biến trạng thái phụ

Một pipeline dễ kiểm thử là pipeline **trả về kết quả**:

```java
List<Integer> actual = List.of(1, 2, 3, 4).stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();

if (!actual.equals(List.of(20, 40))) {
    throw new AssertionError(actual);
}
```

Đây là đoạn minh họa bên trong một phương thức có `import java.util.List;`. Không cần mock `ArrayList` ngoài hay kiểm tra tác dụng phụ phát sinh ở `peek`.

Khi viết collector tùy chỉnh, nên kiểm thử:

1. **Stream rỗng:** `supplier` tạo đúng trạng thái ban đầu và finisher trả kết quả hợp đồng cho nguồn rỗng.
2. **Một phần tử:** accumulator không nhân đôi dữ liệu.
3. **Gộp container rỗng:** `combiner(a, supplier.get())` cho kết quả tương đương `a`.
4. **Chia nhóm:** kết quả khi gom `[a,b]` và `[c,d]` rồi merge giống thu thập tuần tự cả danh sách.
5. **Associativity:** những cách nhóm và ghép khác nhau tạo kết quả tương đương (với ordered collector, còn phải đúng thứ tự).
6. **Parallel vs sequential:** so sánh kết quả trên nhiều bộ dữ liệu; không chỉ chạy một lần rồi kết luận đúng.
7. **Tính độc lập:** supplier mỗi lần tạo container mới; không dùng chung mutable instance ngoài ý muốn.

Các luật cần được lập luận theo miền dữ liệu thật; một số phép toán dấu phẩy động có thể cho sai khác do làm tròn khi nhóm các phép cộng theo cách khác nhau.

## 12. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `parallelStream().forEach(sharedList::add)` | Race và thứ tự không xác định | `collect(toList())`, `toList()` hoặc `toCollection(...)` |
| Tăng `AtomicInteger` trong `peek` để đếm | Callback không bắt buộc được thực thi; phụ thuộc tác dụng phụ | `count()` |
| Lấy tổng qua biến `int[] sum` bên ngoài | Mutable state chia sẻ, không an toàn khi song song | `mapToInt(...).sum()` hoặc `reduce(0, Integer::sum)` |
| Tự cập nhật `HashMap` trong `forEach` | Race, merge sai hoặc mất dữ liệu | `groupingBy`, `toMap` với merge function |
| Supplier trả cùng một `ArrayList` chia sẻ | Các nhánh có thể cùng sửa cùng container | `ArrayList::new` tạo instance mới |
| Combiner quên dữ liệu của nhánh phải | Phép collect song song mất phần tử | Merge đầy đủ, đúng hướng và giữ order nếu cần |
| Tưởng `Collectors.toList()` luôn trả `ArrayList` sửa được | API không hứa loại/mutability | `toCollection(ArrayList::new)` |
| Dùng `reduce` với `StringBuilder` mutable identity | Vi phạm hợp đồng reduction song song | `Collectors.joining()` hoặc custom collector đúng |
| Dùng `forEachOrdered` chỉ để tạo một list kết quả | Tác dụng phụ không cần thiết và dễ bị buộc đồng bộ hóa | `toList()` hoặc `collect()` |
| Đánh dấu collector `CONCURRENT` với trạng thái không thread-safe | Race khi cùng cập nhật một container | Chỉ khai báo khi accumulator được thiết kế concurrent |

## Tự kiểm tra kiến thức

**Câu 1.** Vì sao `parallelStream().forEach(result::add)` với `ArrayList` bên ngoài không an toàn?

**Đáp án:** Các luồng có thể gọi `add` đồng thời trên cùng `ArrayList`, trong khi `ArrayList` không đồng bộ hóa cho thao tác ghi; thứ tự `forEach` song song cũng không được bảo đảm.

**Câu 2.** Chỉ cần danh sách kết quả theo thứ tự nguồn, chọn `forEachOrdered(list::add)` hay `toList()`?

**Đáp án:** Thường chọn `toList()` nếu phù hợp, hoặc `collect(...)` khi muốn một loại container cụ thể. Chúng biểu diễn kết quả thay vì đặt side effect vào callback.

**Câu 3.** Trong `collect(ArrayList::new, List::add, List::addAll)`, combiner làm gì?

**Đáp án:** Gộp dữ liệu của container thứ hai vào container thứ nhất khi các phần tích lũy cần hợp nhất. Nó là `BiConsumer`, không trả lại container.

**Câu 4.** Dùng `Collectors.toList()` có bảo đảm list kết quả là `ArrayList` mutable không?

**Đáp án:** Không. Nếu cần `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`.

**Câu 5.** Khi bài toán chỉ cần tổng số lượng, viết `collect` tự định nghĩa hay `mapToInt(...).sum()`?

**Đáp án:** Ưu tiên `mapToInt(...).sum()` vì diễn đạt trực tiếp phép tổng hợp nguyên thủy và không cần quản lý trạng thái của collector.

**Câu 6.** Custom collector dùng `Acc` mutable có thể chạy parallel nhưng không khai báo `CONCURRENT` không?

**Đáp án:** Có. Framework có thể giữ các container riêng cho từng nhánh rồi gộp. `CONCURRENT` chỉ dùng khi cùng một container có thể được cập nhật đồng thời an toàn.

## Ghi nhớ

- **Đừng gom kết quả bằng một biến mutable bên ngoài pipeline** nếu `collect()`, `toList()` hoặc phép tổng hợp chuyên biệt đã diễn đạt đúng bài toán.
- `collect()` tạo và quản lý trạng thái tích lũy **bên trong cơ chế Stream**, giúp mã bớt phụ thuộc tác dụng phụ bên ngoài và phù hợp hơn với parallel processing.
- Dùng collector chuẩn cho list, set, map, grouping, joining và thống kê; dùng `Collector.of` khi cần trạng thái tùy chỉnh thật sự.
- Supplier cần tạo container phù hợp; accumulator cập nhật container; combiner gộp đầy đủ, đúng thứ tự/ngữ nghĩa; các luật identity/associativity/equivalence phải được giữ.
- **Thread-safe external list** không tự làm một `forEach` song song có thứ tự; **atomic counter trong `peek`** cũng không biến callback thành phép đếm đáng tin.
- Phân biệt **thu thập kết quả** với **I/O và tác dụng phụ nghiệp vụ**: xử lý dữ liệu bằng pipeline, thực hiện tác động ra môi trường ở ranh giới có kiểm soát.
