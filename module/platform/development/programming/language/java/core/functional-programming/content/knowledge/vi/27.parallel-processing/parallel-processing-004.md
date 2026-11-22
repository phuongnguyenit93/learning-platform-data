# Tính kết hợp, không can thiệp nguồn và không giữ trạng thái dùng chung khi dùng Parallel Stream trong Java

## 1. Vì sao phải tuân thủ ba nguyên tắc này?

Java Stream cho phép chuyển nhiều pipeline tuần tự sang xử lý song song bằng `parallel()` hoặc `parallelStream()`:

~~~java
int total = List.of(10, 20, 30, 40).parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Đối với dữ liệu đơn giản, kết quả là `100`. Nhưng chỉ thêm `parallel()` không khiến **mọi phép tính và mọi side effect** trở nên an toàn. Trong pipeline song song, Stream framework có thể chia dữ liệu thành nhiều phần, chạy callback trên các thread khác nhau, rồi kết hợp kết quả. Cách chạy cụ thể, số task và thứ tự callback không phải thứ mà chương trình nên dựa vào.

Ba nguyên tắc trọng tâm của bài học:

1. **Tính kết hợp (associativity):** phép gộp từng phần phải cho kết quả hợp lệ khi framework thay đổi cách chia nhóm, ví dụ cộng số nguyên phù hợp; phép trừ nói chung không kết hợp.
2. **Không can thiệp nguồn (non-interference):** callback không được sửa hoặc gây thay đổi nguồn dữ liệu đang được Stream duyệt, trừ trường hợp nguồn và API có quy tắc đặc biệt cho phép.
3. **Không giữ trạng thái dùng chung có thể biến đổi (stateless behavioral parameters):** `map`, `filter`, `reduce` và các callback nên phụ thuộc vào đầu vào cùng dữ liệu ổn định, không phụ thuộc bộ đếm hoặc danh sách chung bị các worker thay đổi.

Ba nguyên tắc liên quan nhưng không phải một: một lambda có thể không sửa nguồn nhưng vẫn không an toàn vì tăng một biến đếm chung; một phép giảm có thể không có side effect nhưng vẫn cho kết quả khác giữa tuần tự và song song vì toán tử không kết hợp; một phép cộng kết hợp đúng vẫn có thể bị hỏng khi source bị mutate trong lúc duyệt.

**Mục tiêu:** sau bài này, bạn sẽ biết đọc pipeline để kiểm tra tính kết hợp, identity/combiner, tính không can thiệp và sự phụ thuộc trạng thái; viết `reduce`/`collect` đúng; tránh race condition; phân biệt tính đúng với hiệu năng và biết khi nào không cần chạy song song.

Các ví dụ dùng **Java 17+**.

## 2. Cơ chế chạy song song của Stream

### 2.1. Một pipeline có thể được chia rồi gộp

Với tổng `[10,20,30,40]`, cách nhìn khái niệm:

~~~text
Source: [10, 20, 30, 40]
          |
       split work
       /        \
 [10, 20]     [30, 40]
     |             |
    30            70
       \          /
         combine
            |
           100
~~~

Đây chỉ là sơ đồ để hiểu nguyên tắc, **không** phải cam kết JVM chia chính xác hai nhánh. Framework có thể sử dụng nhiều mức tách, các task được scheduling khác nhau và tối ưu hóa pipeline.

Nếu phép gộp thỏa tính kết hợp cùng identity phù hợp, cách chia thành từng phần không làm thay đổi kết quả toán học. Nếu phép gộp không kết hợp, kết quả có thể phụ thuộc cấu trúc cây giảm và trở nên khó dự đoán.

### 2.2. Parallel không có nghĩa callback chạy theo thứ tự nguồn

~~~java
IntStream.range(0, 6)
        .parallel()
        .forEach(System.out::println);
~~~

Đây là mảnh mã nằm trong phương thức với import `java.util.stream.IntStream`. **Không có stdout theo thứ tự cố định** cho `forEach` trên parallel Stream. Các phần tử vẫn thuộc dãy `0..5`, nhưng các lệnh in là side effect có thể diễn ra trên nhiều thread.

Nếu chỉ cần tính kết quả, hãy dùng terminal operation hỗ trợ reduction/collection:

~~~java
List<Integer> numbers = IntStream.range(0, 6)
        .parallel()
        .boxed()
        .toList(); // [0, 1, 2, 3, 4, 5]
~~~

Nguồn `range` có encounter order, và `toList()` thu theo thứ tự đó. Tính có thứ tự của danh sách kết quả **không đồng nghĩa** callback ở các giai đoạn trước đã chạy tuần tự.

### 2.3. Không dùng parallel để che lỗi thuật toán

Nếu pipeline viết sai quy tắc dữ liệu, chạy tuần tự có thể tình cờ cho kết quả mong muốn vì callback được gọi theo thứ tự dễ quan sát; chạy song song làm lỗi lộ rõ. Cách sửa là **thay hợp đồng phép toán hoặc loại bỏ shared mutable state**, không cố định số thread, thêm `sleep` hay khóa toàn bộ chương trình để “bắt thứ tự” mà không giải quyết thiết kế.

## 3. Tính kết hợp: định nghĩa và ví dụ

### 3.1. Định nghĩa toán học

Một phép toán hai ngôi `⊕` là **kết hợp** nếu:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

với mọi `a`, `b`, `c` thuộc miền dữ liệu mà phép toán có nghĩa.

Ví dụ phép cộng số nguyên theo ngữ nghĩa Java `int` có tính kết hợp theo phép cộng modulo 2^32 (dù kết quả có thể overflow so với giá trị toán học dự định). `Integer::sum` phù hợp khi bài toán cho phép hoặc đã kiểm soát giới hạn số. Phép nối chuỗi là kết hợp theo nội dung:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
~~~

**Tính kết hợp không có nghĩa tính giao hoán:** `"A" + "B"` khác `"B" + "A"`, nhưng nối chuỗi vẫn kết hợp. Đối với một ordered Stream, reduction hợp lệ vẫn phải tôn trọng encounter order theo hợp đồng áp dụng.

### 3.2. Phép trừ không kết hợp

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Hai cách nhóm tạo kết quả khác nhau. Vì vậy không dùng phép trừ làm phép kết hợp tùy ý của parallel reduction:

~~~java
int result = IntStream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

Đây là **ví dụ phản diện**. Không viết stdout cụ thể và không tin kết quả sẽ luôn bằng phép giảm từ trái sang phải, vì combiner không thỏa tính kết hợp và identity đúng như yêu cầu. Dù chạy tuần tự cho một giá trị dễ đoán, nó không hợp thức hóa việc dùng toán tử ấy khi framework chia nhóm.

### 3.3. Phép chia, phép so sánh trạng thái và nối theo thời gian

Phép chia số nguyên thông thường cũng không kết hợp. Các hàm sử dụng timestamp tại thời điểm gọi, số random không được kiểm soát hoặc trạng thái global có thể cho kết quả khác nhau theo cách scheduling, ngay cả khi có vẻ viết giống một phép binary operator.

Khi một phép toán không kết hợp nhưng bài toán đòi thứ tự nghiêm ngặt (ví dụ phép trừ liên tiếp), dùng **pipeline tuần tự và thứ tự tường minh**, hoặc biến đổi thuật toán sang một dạng phép gộp kết hợp có nghĩa tương đương nếu có.

### 3.4. Floating-point: cần xét tính ổn định số học

Trong toán học, cộng số thực kết hợp. Nhưng `double`/`float` IEEE 754 bị làm tròn nên `(a+b)+c` có thể khác `a+(b+c)` ở mức bit. Do đó không nên cam kết kết quả reduction floating-point bằng nhau tuyệt đối giữa mọi cách chia nhóm.

Ví dụ về mặt số học máy:

~~~text
a = 1e16
b = -1e16
c = 1.0

(a + b) + c  --> 1.0
a + (b + c)  --> 0.0 (do làm tròn b + c)
~~~

Hãy định nghĩa tolerance, độ chính xác, tính lặp lại và thứ tự đánh giá theo yêu cầu. Đối với tiền, ưu tiên mô hình số chính xác phù hợp như `BigDecimal` và quy tắc làm tròn rõ ràng thay vì mặc định cộng `double` song song là phép toán toán học chính xác.

## 4. Identity và `reduce` phải tương thích với combiner

### 4.1. Phép giảm với identity đúng

~~~java
int sum = IntStream.rangeClosed(1, 10)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(sum); // 55
~~~

Identity của cộng là `0` vì `0 + x = x` và `x + 0 = x`. `Integer::sum` là phép gộp cùng ngữ nghĩa trên mọi nhánh. Đây là ví dụ thích hợp cho parallel reduction, miễn miền số phù hợp.

### 4.2. Identity không phải giá trị khởi tạo tùy ý

Ví dụ dễ sai:

~~~java
int result = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(10, Integer::sum);
~~~

`10` **không** là identity của phép cộng. Nó có thể được đưa vào các nhánh giảm khác nhau, làm kết quả lệ thuộc cách phân chia. Nếu muốn cộng thêm `10` đúng một lần, hãy tách bước:

~~~java
int result = 10 + IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(result); // 20
~~~

Không dựa vào kết quả ngẫu nhiên của anti-pattern thứ nhất để kết luận nó đúng trên mọi cách chạy.

### 4.3. `reduce(identity, accumulator, combiner)`

Với `Stream<T>` có overload:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Đây là **chữ ký phương thức thư viện được giản lược**, không phải một method cần viết. `accumulator` đưa phần tử `T` vào kết quả từng phần kiểu `U`, còn `combiner` gộp hai `U`. Cần thỏa tính tương thích và kết hợp theo hợp đồng reduce. Một dạng điều kiện quan trọng:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

trong ngữ nghĩa kết quả dự kiến. Đây là minh họa luật tương thích của combiner/accumulator, không phải phép so sánh reference bằng toán tử `==` cho mọi object.

Ví dụ hợp lệ:

~~~java
int total = Stream.of(10, 20, 30, 40)
        .parallel()
        .reduce(
                0,
                Integer::sum,
                Integer::sum
        );
System.out.println(total); // 100
~~~

`0` là identity, `Integer::sum` cho accumulator/combiner có cùng nghĩa kết hợp, không lưu trạng thái chung.

### 4.4. Anti-pattern: combiner làm việc khác accumulator

~~~java
int wrong = Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(
                0,
                Integer::sum,
                (left, right) -> left - right
        );
~~~

**Không sử dụng**: accumulator đang cộng nhưng combiner trừ, không thỏa điều kiện tương thích. Kết quả có thể phụ thuộc cách phân nhóm và khác kết quả tuần tự. Đừng cố “kiểm thử trên một bộ dữ liệu” rồi dựa vào một cách chia nhóm implementation hiện tại để bảo vệ mã này.

### 4.5. Đừng dùng mutable identity trong `reduce`

Sai lầm thường gặp:

~~~java
// Không nên: dùng cùng StringBuilder mutable làm identity.
StringBuilder result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                StringBuilder::append,
                StringBuilder::append
        );
~~~

Các overload của `reduce` không được thiết kế để nhận một mutable identity rồi dùng accumulator thay đổi chính object đó. Có thể gây chia sẻ reference giữa các nhánh, vi phạm yêu cầu identity/combiner, tạo kết quả sai hoặc hành vi khó đoán. Cách đúng để thu `String` là `Collectors.joining()`; để thu List, dùng `collect(...)` hoặc `toList()`. Với dữ liệu bất biến hoặc các giá trị mới sau mỗi accumulator, `reduce` có thể phù hợp.

## 5. Không can thiệp nguồn (non-interference)

### 5.1. Stream duyệt nguồn, callback không được sửa nguồn

Ví dụ **sai**:

~~~java
List<Integer> source = new ArrayList<>(
        List.of(1, 2, 3, 4));

source.parallelStream()
        .forEach(n -> source.add(n * 10));
~~~

Đoạn trên cố sửa `ArrayList` đang được Stream duyệt. Đây là **source interference**. Tùy timing, có thể phát sinh `ConcurrentModificationException`, mất dữ liệu, kết quả bất thường hoặc hành vi không xác định theo hợp đồng. Không thể dựa vào việc luôn có exception để phát hiện lỗi, và không nên chạy thử đoạn này trong hệ thống có dữ liệu quan trọng.

Ngay cả trong pipeline tuần tự, callback can thiệp vào nguồn `ArrayList` trong lúc traversal cũng không hợp lệ theo các ràng buộc của Stream API. Parallel chỉ làm các lỗi race phức tạp hơn.

### 5.2. Không mutate nguồn trong `filter`/`map`/`peek`

Một ví dụ phản diện khác:

~~~java
List<String> names = new ArrayList<>(
        List.of("An", "Binh"));

List<String> result = names.parallelStream()
        .map(name -> {
            names.remove(name); // Sai: can thiệp source.
            return name.toUpperCase();
        })
        .toList();
~~~

Tương tự, việc thêm/xóa entry trong Map đang được Stream duyệt, hoặc sửa phần tử/khóa theo cách thay đổi cấu trúc dữ liệu nguồn trong khi pipeline đánh giá, có thể vi phạm hợp đồng. `peek` thường dùng để quan sát/debug, **không phải đường tắt hợp lệ** để mutate nguồn hay bảo đảm một side effect chạy đúng một lần.

### 5.3. Nên giữ nguồn ổn định trong thời gian thực thi

~~~java
List<Integer> source = List.of(1, 2, 3, 4);

List<Integer> transformed = source.parallelStream()
        .map(n -> n * 10)
        .toList();

System.out.println(transformed); // [10, 20, 30, 40]
~~~

`List.of` là unmodifiable và chứa `Integer` (immutable), nên giảm rõ nguy cơ can thiệp nguồn. Nhưng không phải mọi `List` unmodifiable đều đảm bảo toàn bộ **object phần tử** không đổi: nếu chứa các object mutable, chúng vẫn có thể bị cập nhật qua reference khác.

Nếu nguồn là collection mutable nhưng quá trình xử lý cần snapshot nhất quán, hãy thiết kế vòng đời: tạo bản sao cấu trúc phù hợp khi không có cập nhật đồng thời không kiểm soát, hoặc phối hợp khóa/transaction ở ranh giới lấy snapshot theo hợp đồng. Chỉ viết `new ArrayList<>(source)` **không** tự giải quyết việc một thread khác đang đồng thời mutate source trong lúc copy.

### 5.4. Ngoại lệ từ nguồn concurrent

Một số nguồn được thiết kế cho concurrent updates, như các collection đồng thời có đặc tính spliterator phù hợp. Stream framework cho phép khác biệt theo hợp đồng nguồn, nhưng các guarantee về snapshot, ordering và visibility **phải đọc từ API cụ thể**, không tự suy luận rằng mọi `Collection` đều an toàn khi bị mutate.

Trong mã ứng dụng thông thường, lời khuyên an toàn nhất vẫn là: **không sửa nguồn trong lúc stream đang duyệt** trừ khi nguồn và bài toán cho phép có chủ đích, và phải chấp nhận semantics được ghi trong Javadoc của nguồn đó.

## 6. Stateless callback và shared mutable state

### 6.1. Lambda thuần không dựa vào dữ liệu thay đổi bên ngoài

Ví dụ phù hợp:

~~~java
int multiplier = 10;

List<Integer> values = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * multiplier)
        .boxed()
        .toList();

System.out.println(values); // [10, 20, 30, 40, 50]
~~~

`multiplier` là local effectively final. Mỗi lần chạy `map` chỉ dùng input `n` và hằng số ổn định, không mutate shared state. Cùng một input cho cùng một output trong điều kiện đó.

**Stateless không có nghĩa lambda tuyệt đối không được đọc biến ngoài.** Đọc một cấu hình immutable ổn định là khác hoàn toàn với cập nhật một `counter` dùng chung hoặc đọc trạng thái bị thay đổi đồng thời không có hợp đồng.

### 6.2. Shared `ArrayList` là anti-pattern

~~~java
List<Integer> shared = new ArrayList<>();

IntStream.range(0, 1000)
        .parallel()
        .forEach(shared::add); // Sai: ArrayList không thread-safe.
~~~

Ở đây source `IntStream.range` không bị mutate, nhưng List kết quả **là trạng thái chung được các task cập nhật đồng thời**. Điều này có thể gây race, mất phần tử hoặc trạng thái không nhất quán.

Thay bằng terminal collection:

~~~java
List<Integer> result = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();
~~~

Khi cần List mutable sau bước thu:

~~~java
List<Integer> result = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Stream framework quản lý accumulation và combine theo hợp đồng collector, không yêu cầu mọi thread tự ghi vào **cùng một ArrayList bên ngoài**.

### 6.3. Counter chung cũng là stateful

~~~java
AtomicInteger counter = new AtomicInteger();

List<Integer> values = IntStream.range(0, 100)
        .parallel()
        .map(n -> {
            counter.incrementAndGet();
            return n * 2;
        })
        .boxed()
        .toList();
~~~

`AtomicInteger` làm phép tăng **atomic**, nhưng lambda vẫn là **stateful behavioral parameter** và tạo side effect. Trong Stream, một số tối ưu hóa có thể bỏ qua các thao tác trung gian không cần thiết; callback không nên được dùng làm nguồn sự thật duy nhất cho số lần xử lý. `AtomicInteger` không tự biến pipeline thành thiết kế stateless hoặc bảo đảm thứ tự gọi.

Nếu mục tiêu là số phần tử, dùng:

~~~java
long count = IntStream.range(0, 100)
        .parallel()
        .count(); // 100
~~~

Nếu mục tiêu tính tổng, dùng `sum()` hoặc `reduce` hợp lệ. Nếu mục tiêu đánh số theo encounter order, hãy sử dụng index từ nguồn có thứ tự, chẳng hạn `IntStream.range(0, size)`, thay vì một counter cạnh tranh giữa thread.

### 6.4. “Thread-safe” không đồng nghĩa “phù hợp với Stream”

Thay `ArrayList` bằng `Collections.synchronizedList(...)` hoặc `ConcurrentLinkedQueue` có thể giảm một số race nhất định, nhưng không tự đảm bảo thứ tự encounter, không sửa được logic gộp không kết hợp và không giải quyết side effect không mong muốn. Một pipeline dựa vào việc các callback chạy chính xác theo một trật tự vẫn có thể sai dù collection dùng để lưu được đồng bộ.

**Ưu tiên thu kết quả với `collect`/`toList` và diễn đạt phép toán thành reduction**, thay vì đưa một concurrent container vào callback để tự điều phối các task.

## 7. `collect` có mutable accumulator: tại sao vẫn an toàn?

### 7.1. Mutation do framework điều phối khác mutation chung tùy tiện

Collector có thể dùng mutable container nội bộ:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

`ArrayList` không thread-safe nếu bị nhiều thread tùy tiện mutate chung, nhưng `collect` có supplier, accumulator và combiner giúp framework điều phối các container/partial results đúng hợp đồng. Điểm quan trọng là **container được quản lý bởi Collector**, không bị một lambda độc lập ghi vào một shared List bên ngoài.

Kết quả sau khi thu là `ArrayList` mutable, nhưng **không được suy ra an toàn khi nhiều thread cùng ghi sau đó**. Tính đúng của parallel collection và thread safety của object kết quả sau collection là hai vấn đề khác nhau.

### 7.2. Một collector chuẩn cho tổng theo nhóm

~~~java
Map<String, Integer> totals = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::team,
                TreeMap::new,
                Collectors.summingInt(Order::amount)));
~~~

Đây là mảnh mã trong class có `record Order(String team, int amount) {}`, nguồn `orders` kiểu `List<Order>`, và import `Map`, `TreeMap`, `Collectors`. `groupingBy` phân nhóm, downstream `summingInt` cộng số tiền, `TreeMap` giúp thứ tự khóa được xác định khi in.

Với dữ liệu `("A",10),("B",20),("A",30),("B",40)`, Map theo nhóm là `{A=40, B=60}`. Collector framework lo việc tích lũy/kết hợp; người viết không cần `HashMap` chung cùng `merge` không đồng bộ trong `forEach`.

### 7.3. `groupingByConcurrent` không phải thay thế mặc định

`Collectors.groupingByConcurrent` có thể giúp thu concurrent trong một số pipeline, nhưng có khác biệt về thứ tự và đặc tính collector. Khi bài toán **phải giữ encounter order của các phần tử trong từng nhóm**, không tự thay `groupingBy` bằng `groupingByConcurrent` rồi kỳ vọng cùng thứ tự. Cần đọc hợp đồng collector và yêu cầu thực tế.

Một phép `toConcurrentMap` với khóa trùng phải có merge function phù hợp; nếu kết quả cần đúng khi gộp khác thứ tự, phép merge cũng phải có các tính chất đại số phù hợp, thường cần tính kết hợp và có thể cần tính giao hoán nếu không thể dựa vào encounter order. Không dùng logic gộp chỉ đúng với một thứ tự tình cờ.

## 8. Chương trình Java 17 độc lập

Ví dụ sau **không có side effect dùng chung trong pipeline** và nguồn là `List.of` không sửa được. Phép giảm có identity và toán tử cộng phù hợp; collector nhóm để framework xử lý tích lũy.

Tạo tệp **`ParallelRulesDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelRulesDemo {

    record Order(String team, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 10),
                new Order("B", 20),
                new Order("A", 30),
                new Order("B", 40)
        );

        int sequential = orders.stream()
                .mapToInt(Order::amount)
                .sum();

        int parallel = orders.parallelStream()
                .mapToInt(Order::amount)
                .sum();

        int reduced = orders.parallelStream()
                .map(Order::amount)
                .reduce(0, Integer::sum);

        Map<String, Integer> totals = orders.parallelStream()
                .collect(Collectors.groupingBy(
                        Order::team,
                        TreeMap::new,
                        Collectors.summingInt(Order::amount)));

        List<String> labels = orders.parallelStream()
                .map(o -> o.team() + ":" + o.amount())
                .toList();

        long evens = IntStream.rangeClosed(1, 10)
                .parallel()
                .filter(n -> n % 2 == 0)
                .count();

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("reduced=" + reduced);
        System.out.println("byTeam=" + totals);
        System.out.println("labels=" + labels);
        System.out.println("evens=" + evens);
        System.out.println("sourceSize=" + orders.size());
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 ParallelRulesDemo.java
java ParallelRulesDemo
~~~

**Stdout chính xác:**

~~~text
sequential=100
parallel=100
reduced=100
byTeam={A=40, B=60}
labels=[A:10, B:20, A:30, B:40]
evens=5
sourceSize=4
~~~

Giải thích:

1. `sequential` và `parallel` cùng trả `100` vì đều cộng bốn số nguyên nhỏ trong miền an toàn, không thay đổi nguồn hoặc cập nhật state chung.
2. `reduced=100` dùng `reduce(0,Integer::sum)`: identity `0` và phép cộng kết hợp phù hợp để gộp các partial results.
3. `byTeam` có nhóm A gồm 10+30=40, nhóm B gồm 20+40=60. `TreeMap` làm thứ tự in khóa `A` rồi `B` dự đoán được.
4. `labels` dùng callback `map` chỉ dựa vào từng `Order` bất biến; `List.of` có encounter order và `toList()` giữ thứ tự, dù callback có thể chạy trên nhiều thread.
5. Trong khoảng từ 1 tới 10 bao gồm cả hai đầu, có 5 số chẵn: `2,4,6,8,10`.
6. `sourceSize=4` xác nhận pipeline không can thiệp cấu trúc nguồn; dữ liệu nguồn là một List không sửa được chứa record chỉ có `String` và `int`.

Chương trình **không** in tên thread hoặc dự đoán thứ tự `parallel().forEach`, vì đó không phải bảo đảm cần dựa vào để kiểm tra kết quả.

## 9. Phân tích các lỗi trong code thực tế

### 9.1. Đếm bằng local captured variable không hợp lệ

~~~java
int counter = 0;

// Không biên dịch: counter phải final/effectively final.
IntStream.range(0, 100).parallel()
        .forEach(n -> counter++);
~~~

Java không cho lambda gán lại local được capture. Việc thay bằng `AtomicInteger` có thể làm code biên dịch và phép tăng atomic, nhưng vẫn tạo behavioral parameter stateful. Khi yêu cầu chỉ là đếm phần tử, dùng `count()`.

### 9.2. Tổng bằng shared mutable array

~~~java
int[] total = {0};

IntStream.rangeClosed(1, 1000).parallel()
        .forEach(n -> total[0] += n);
~~~

Đây là anti-pattern có thể **race**: cập nhật `total[0]` không atomic, nhiều thread có thể đọc giá trị cũ rồi ghi đè. Có thể ra tổng sai, không nhất thiết lỗi hoặc exception.

Sửa:

~~~java
int total = IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();

System.out.println(total); // 500500
~~~

Đây là reduction chuẩn. Nếu tổng vượt `int`, đổi sang `mapToLong` hoặc `LongStream`/kiểu số phù hợp; việc chạy song song không ngăn overflow.

### 9.3. Phụ thuộc thứ tự callback

~~~java
List<String> messages = List.of("first", "second", "third");

messages.parallelStream()
        .map(String::toUpperCase)
        .forEach(System.out::println);
~~~

Không có stdout theo thứ tự cố định. Nếu yêu cầu hiển thị đúng encounter order, có thể thu `toList()` rồi in tuần tự hoặc dùng `forEachOrdered`:

~~~java
messages.parallelStream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` bảo đảm thứ tự action theo encounter order của ordered Stream, nhưng **không làm mọi logic mutable bên ngoài trở thành thread-safe**, và yêu cầu giữ thứ tự có thể hạn chế lợi ích song song.

### 9.4. Đọc biến cấu hình bị thay đổi đồng thời

~~~java
class Config {
    volatile int multiplier = 2;
}
~~~

Một lambda đọc `config.multiplier` trong khi thread khác thay giá trị có thể dùng các giá trị khác nhau cho những phần tử khác nhau. `volatile` giải quyết một số vấn đề visibility nhưng **không làm cấu hình thành bất biến**, và cũng không tự làm callback stateless. Nếu tất cả phần tử trong một lần xử lý phải dùng cùng cấu hình, nên chụp **giá trị cấu hình nhất quán trước khi bắt đầu** và capture một giá trị immutable.

### 9.5. Mutate object phần tử cũng có thể gây can thiệp

~~~java
record User(String name, List<String> tags) {}
~~~

Record giữ reference của `tags`; nếu list đó mutable và một callback sửa `tags` trong khi callback khác đọc cùng list, có thể xảy ra race và kết quả phụ thuộc timing. Record chỉ làm các field reference `final`, không tự làm object được tham chiếu immutable sâu.

Cách giảm rủi ro: xây model immutable ở cấp dữ liệu cần đọc, ví dụ tạo `List.copyOf(tags)` khi xây object (sau khi đã bảo đảm dữ liệu không null và không có cập nhật đồng thời không kiểm soát), hoặc tách bước mutation ra khỏi pipeline.

## 10. Kết hợp có luôn là giao hoán không?

**Không.** Phải phân biệt:

- **Associative:** đổi cách đặt ngoặc không đổi kết quả.
- **Commutative:** đổi chỗ hai đối số không đổi kết quả.
- **Identity:** có một giá trị trung hòa không đổi kết quả khi gộp.

Ví dụ nối chuỗi là **associative** với identity `""`, nhưng không giao hoán:

~~~text
"A" + "B" = "AB"
"B" + "A" = "BA"
~~~

Với ordered Stream và phép giảm tuân thủ hợp đồng, có thể kỳ vọng thứ tự phần tử theo encounter order ở kết quả. Tuy nhiên, nếu bạn chuyển pipeline sang `unordered()` hoặc collector có đặc tính `UNORDERED`/`CONCURRENT`, không thể dựa vào cùng thứ tự cho phép gộp nhạy với vị trí.

Đối với tổng số nguyên nhỏ, phép cộng vừa kết hợp vừa giao hoán theo ngữ nghĩa phép cộng modulo của Java. Nhưng **không nên kết luận chỉ cần có tính giao hoán là đủ**: combiner vẫn phải tương thích với accumulator, identity phải hợp lệ và các callback vẫn cần không can thiệp, không giữ trạng thái biến đổi chung.

## 11. Parallel Stream không tự động nhanh hơn

Parallel Stream có chi phí:

- Tách nguồn thành các spliterator partitions, phân phối công việc.
- Tạo/điều phối tác vụ và hợp nhất partial results.
- Chi phí đồng bộ hoặc giữ encounter order, đặc biệt ở một số stateful operations như `sorted`, `distinct`, `limit`.
- Cạnh tranh CPU, băng thông bộ nhớ và tài nguyên với các task khác.
- Thời gian phụ thuộc kích thước nguồn, tính độc lập của phần tử và lượng tính toán mỗi phần tử.

Với một danh sách rất nhỏ hoặc lambda đơn giản `n -> n + 1`, chạy song song có thể **chậm hơn** tuần tự. Nếu nguồn là thao tác I/O blocking, parallel Stream không mặc nhiên là mô hình concurrency tốt nhất; cần kiểm soát pool, giới hạn đồng thời, timeout và chính sách lỗi theo bài toán.

Không dùng hiệu năng làm lý do phá các nguyên tắc về associativity/non-interference/statelessness. Hãy viết phiên bản tuần tự đúng trước, so sánh kết quả trên dữ liệu thực, rồi benchmark với các số liệu có ý nghĩa nếu việc chạy song song thực sự cần thiết.

## 12. Bảng phân loại nhanh

| Biểu thức/hành vi | Đánh giá khi song song | Nguyên nhân |
| --- | --- | --- |
| `map(n -> n * 2)` trên dữ liệu immutable | Phù hợp | Không sửa nguồn, stateless |
| `filter(n -> n > 0)` | Phù hợp | Predicate phụ thuộc input |
| `reduce(0, Integer::sum)` | Phù hợp nếu ngữ nghĩa overflow chấp nhận | Identity và phép cộng kết hợp |
| `reduce(0, (a,b) -> a-b)` | Sai cho parallel reduction tổng quát | Không kết hợp/identity không phù hợp |
| `reduce(10, Integer::sum)` | Sai ý định “thêm 10 một lần” | `10` không là identity |
| `parallel().forEach(sharedArrayList::add)` | Không an toàn | Shared mutable state, race |
| `parallel().boxed().toList()` | Phù hợp | Framework thu theo hợp đồng |
| `map(x -> { source.add(x); return x; })` | Không hợp lệ | Can thiệp nguồn đang duyệt |
| `map(x -> counter.getAndIncrement() + ":" + x)` | State-dependent | Atomic counter không bảo đảm encounter order |
| `collect(groupingBy(key, summingInt(value)))` | Phù hợp theo hợp đồng collector | Accumulator/combiner do framework quản lý |
| `peek(x -> sendEmail(x))` | Không phải cách thiết kế tác vụ nghiệp vụ an toàn | Side effect, tối ưu hóa, retry, lỗi và số lần thực thi |
| `parallel().forEachOrdered(action)` | Bảo toàn thứ tự action theo hợp đồng | Không phải giải pháp cho mọi state race |

## 13. Quy trình kiểm tra một pipeline trước khi gọi `parallel()`

1. **Nguồn là gì?** `List`, mảng, `HashSet`, file, database stream hay nguồn concurrent? Có encounter order không?
2. **Trong lúc chạy, nguồn có bị thay đổi không?** Callback, thread khác hoặc API bên ngoài có mutate nguồn? Nếu có, cần xem lại non-interference và hợp đồng source.
3. **Callback có stateful không?** Có đọc/ghi `AtomicInteger`, `ArrayList`, `HashMap`, field mutable, random chung, clock hoặc object state không?
4. **Phép reduction có kết hợp không?** Đổi cách nhóm có đổi kết quả không? Kiểm tra subtraction/division/floating point/rounding.
5. **Identity có trung hòa thật không?** `0` với tổng, `1` với nhân, `""` với nối chuỗi; đừng dùng giá trị “khởi tạo” tùy ý.
6. **Accumulator và combiner tương thích không?** Với 3-argument reduce, hai bước phải tạo cùng ý nghĩa kết quả.
7. **Có mutable identity trong `reduce` không?** Nếu có, chuyển sang `collect` đúng hợp đồng hoặc tạo giá trị bất biến.
8. **Muốn thứ tự kết quả hay thứ tự side effect?** `toList` và `forEach` có khác bảo đảm; dùng `forEachOrdered` khi đúng nghiệp vụ.
9. **Collector có được thiết kế để thu parallel không?** Ưu tiên built-in collectors và đọc characteristics của collector tùy biến.
10. **Kết quả có yêu cầu thread-safe sau khi thu không?** Quy trình collect an toàn không tự biến List/Map trả ra thành concurrent-safe.
11. **Có yêu cầu tính chính xác cao của tổng `double` không?** Kiểm tra sai số, số học và chính sách làm tròn.
12. **Có thực sự nhanh hơn không?** Đo số liệu và so sánh với tuần tự trên môi trường tải thực tế.

## 14. Bài tập thực hành

### Bài 1 — Phân biệt phép gộp kết hợp

Cho ba phép `a+b`, `a-b`, `a*b` trên số nguyên phù hợp. Thử ba giá trị `a=10`, `b=3`, `c=2`; tính `(a op b) op c` và `a op (b op c)`. Giải thích vì sao phép trừ không hợp lệ làm combiner cho parallel reduction, và vì sao identity của cộng khác identity của nhân.

### Bài 2 — Kiểm thử identity

Viết `IntStream.rangeClosed(1,4).parallel().reduce(0,Integer::sum)` và dự đoán `10`. Sau đó phân tích vì sao dùng identity `10` không có nghĩa “cộng 10 một lần”, rồi sửa bằng cách cộng thêm `10` **sau** một reduction có identity `0`.

### Bài 3 — Refactor shared ArrayList

Cho `List<Integer> result = new ArrayList<>(); IntStream.range(0,1000).parallel().forEach(result::add);`. Chuyển sang `boxed().toList()`. Nếu yêu cầu List mutable, viết `collect(Collectors.toCollection(ArrayList::new))`. Giải thích sự khác nhau giữa thread safety của object kết quả và việc framework thu dữ liệu đúng.

### Bài 4 — Không sửa nguồn

Tạo `ArrayList<String>` rồi viết một pipeline chỉ `filter`/`map` không sửa nguồn. So sánh với đoạn phản diện có `source.remove(...)` trong `map`. Giải thích vì sao không thể coi `ConcurrentModificationException` luôn là cơ chế phát hiện mọi can thiệp.

### Bài 5 — Tính tổng theo nhóm

Với nguồn record `Order(team, amount)` như chương trình phần 8, viết `parallelStream().collect(groupingBy(Order::team,TreeMap::new,summingInt(Order::amount)))`. Kết quả `{A=40,B=60}` theo thứ tự key khi in TreeMap. Đừng tự tạo `HashMap` mutable chung rồi gọi `put` trong `parallel().forEach`.

### Bài 6 — Side effect và encounter order

Dùng `IntStream.range(0,10).parallel().forEach(System.out::println)`; giải thích vì sao các dòng in có thể đảo. Thử `forEachOrdered` và so sánh. Nêu vì sao `forEachOrdered` không biến mọi cấu trúc dùng chung thành thread-safe.

### Bài 7 — Tổng floating point

Tìm bộ ba số `double` mà `(a+b)+c` khác `a+(b+c)` do làm tròn. So sánh reduction tuần tự và song song trên nhiều phần tử; **không** viết test yêu cầu hai kết quả bitwise bằng nhau trong mọi điều kiện. Đề xuất chiến lược tolerance hoặc số chính xác nếu nghiệp vụ đòi tính lặp lại.

### Bài 8 — Atomic chưa đủ

Viết pipeline dùng `AtomicInteger.getAndIncrement()` làm số thứ tự cho phần tử trong `parallel().map(...)`. Giải thích vì sao số tăng là atomic nhưng không chắc khớp encounter order. Thay bằng `IntStream.range(0, list.size()).mapToObj(i -> i+":"+list.get(i))` nếu danh sách ổn định và có truy cập ngẫu nhiên hiệu quả.

### Bài 9 — Comparator/collector custom

Thiết kế một phép gộp theo key cần kết quả là tổng `long`, dùng `summingLong` hoặc `toMap` với merge `Long::sum`. Kiểm tra identity/associativity, overflow và loại Map cần cho thứ tự đầu ra. Không tự thay bằng merge trừ hay phương thức có side effect.

### Bài 10 — Lập checklist cho code thật

Chọn một pipeline của bạn có `parallelStream()`. Ghi rõ nguồn, thứ tự, các callback, vùng state được đọc/ghi, reduction/collector, identity, chính sách ngoại lệ và dữ liệu đầu ra. Đánh dấu điều kiện nào cần sửa trước khi cho chạy song song. Nếu không có lợi ích đáng kể, giải thích vì sao để tuần tự là quyết định hợp lý.

## 15. Tự kiểm tra kiến thức

**1. Associativity là gì?** Thay đổi cách nhóm phép gộp không thay đổi kết quả theo ngữ nghĩa cần bảo toàn.

**2. Phép trừ có thể dùng làm binary reduction song song tùy ý không?** Không, phép trừ không kết hợp.

**3. Identity của phép cộng là 10 nếu muốn cộng thêm 10 vào tổng?** Không; identity là 0, hãy cộng 10 sau reduction.

**4. Vì sao không dùng một `StringBuilder` chung làm identity trong `reduce`?** Vì accumulator mutate identity vi phạm hợp đồng reduction, có thể chia sẻ object giữa các nhánh.

**5. Non-interference nghĩa là gì?** Behavioral parameter không gây thay đổi nguồn đang được Stream duyệt trái với hợp đồng source.

**6. Không sửa nguồn nhưng ghi vào `ArrayList` chung thì có an toàn?** Không; vẫn có race do shared mutable result.

**7. Có thể đọc cấu hình immutable từ lambda không?** Có, nếu dữ liệu capture ổn định và callback không có state phụ thuộc thay đổi giữa các phần tử.

**8. `AtomicInteger` có làm lambda tự thành stateless không?** Không; nó chỉ cung cấp một số thao tác atomic trên shared state.

**9. Có cần tự đồng bộ `ArrayList` bên ngoài để thay `collect` không?** Không; nên dùng `collect`/`toList` theo hợp đồng phù hợp.

**10. Parallel Stream có bảo đảm `forEach` theo encounter order không?** Không. `forEachOrdered` dành cho yêu cầu thứ tự hành động.

**11. Một List do parallel `collect` trả về có tự thread-safe không?** Không, đó là câu hỏi riêng về object kết quả.

**12. Parallel có luôn nhanh hơn sequential không?** Không; chi phí điều phối, phân chia, combine và workload quyết định.

## 16. Tổng kết và tài liệu tham khảo

**Parallel Stream đúng cần dữ liệu nguồn ổn định, callback không can thiệp và không phụ thuộc trạng thái biến đổi dùng chung, đồng thời reduction có phép gộp kết hợp với identity/combiner tương thích.** Đây là điều kiện để framework có thể chia dữ liệu và gộp các partial results mà vẫn bảo toàn ngữ nghĩa. Chỉ thêm `parallel()` không bảo đảm kết quả đúng và cũng không chắc cải thiện hiệu năng.

Hãy ưu tiên `map`/`filter` thuần, `sum`/`count`/`reduce` hợp lệ và built-in collectors như `toList`, `toCollection`, `groupingBy`/`summingInt`. Không mutate nguồn trong callback, không tự cập nhật `ArrayList` hoặc counter chung và không dùng mutable identity trong `reduce`. Khi cần thứ tự action, hiểu rõ `forEachOrdered`; khi cần kết quả tính toán, ưu tiên reduction/collection hơn side effects. Với `double`, độ chính xác và tính lặp lại là yêu cầu số học cần đánh giá riêng.

**Nguồn chính thức:** Java Stream package documentation (Non-interference, Stateless behaviors, Reduction, Ordering, Side-effects); Javadoc Java SE 17 của `java.util.stream.Stream`, `IntStream`, `java.util.stream.Collectors` và `java.util.stream.Collector`; Java Language Specification về lambda và quy tắc capture. Tài liệu JDK nhấn mạnh tính non-interfering/stateless của behavioral parameters và các điều kiện identity, associativity, compatibility khi dùng reduction.
