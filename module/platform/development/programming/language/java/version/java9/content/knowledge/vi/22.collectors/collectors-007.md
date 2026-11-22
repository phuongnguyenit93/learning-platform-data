# Kiểm tra kiểu kết quả và khả năng thu song song

Khi dùng Stream API, một Collector quyết định cách các phần tử được tích lũy và kiểu kết quả cuối cùng mà `collect` trả về. Muốn chọn collector đúng, cần hiểu ba kiểu generic của `Collector<T, A, R>`, hợp đồng kết hợp các phần kết quả và ba đặc tính `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`.

Một điểm quan trọng: **parallel stream không bắt buộc phải dùng concurrent collector**. Collector thông thường vẫn có thể thu song song an toàn nhờ các vùng tích lũy riêng cho từng phần dữ liệu rồi kết hợp chúng. Concurrent reduction là một cơ chế riêng, chỉ được dùng khi collector và stream đáp ứng các điều kiện tương ứng.

## 1. Đọc kiểu generic Collector<T, A, R>

Interface `Collector<T, A, R>` mô tả ba kiểu:

- `T`: kiểu phần tử đầu vào của Stream.
- `A`: kiểu container trung gian dùng để tích lũy kết quả.
- `R`: kiểu kết quả được trả về sau khi hoàn tất collector.

Ví dụ:

~~~java
List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.toList());
~~~

Ở đây phần tử đầu vào là `String`, kết quả được khai báo là `List<String>`. Kiểu container trung gian thực tế do collector quyết định và không phải lúc nào cũng giống kiểu kết quả.

Một collector có thể dùng kiểu trung gian khác kiểu kết quả. Ví dụ, collector có thể tích lũy vào một `ArrayList`, sau đó finisher tạo một List unmodifiable để trả về. Vì vậy, khi đọc chữ ký collector, hãy phân biệt `A` với `R`, không suy luận container nội bộ chỉ từ kiểu biến nhận kết quả.

## 2. Bốn thành phần của Collector

Collector được mô tả bởi các hàm chính:

| Thành phần | Vai trò |
|---|---|
| `supplier()` | Tạo container tích lũy rỗng mới |
| `accumulator()` | Thêm một phần tử Stream vào container |
| `combiner()` | Kết hợp hai container tích lũy độc lập |
| `finisher()` | Chuyển container trung gian thành kết quả cuối cùng |

Ngoài ra, `characteristics()` khai báo những đặc tính của collector để Stream implementation có thể chọn chiến lược thu thập phù hợp.

Ví dụ một collector tự định nghĩa có thể dùng `ArrayList` làm container trung gian và trả về bản sao unmodifiable:

~~~java
Collector<String, List<String>, List<String>> snapshotCollector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf
        );
~~~

Trong ví dụ này:

- `T` là `String`.
- `A` là `List<String>` được dùng để tích lũy.
- `R` cũng là `List<String>`, nhưng kết quả được tạo qua `List.copyOf`.
- `supplier` tạo một ArrayList mới.
- `accumulator` thêm một String.
- `combiner` nối phần bên phải vào phần bên trái.
- `finisher` trả về một bản sao unmodifiable.

Dù `A` và `R` có cùng kiểu khai báo ở ví dụ này, finisher vẫn thực hiện một bước chuyển đổi. Collector vì thế không khai báo `IDENTITY_FINISH`.

## 3. Ba Collector.Characteristics

`Collector.Characteristics` là tập các cờ mô tả cách collector có thể được thực thi.

**IDENTITY_FINISH**

Finisher có thể được bỏ qua vì container tích lũy `A` có thể được sử dụng trực tiếp như kết quả `R`. Khi đặc tính này có mặt, kiểu trung gian và kiểu kết quả phải tương thích theo hợp đồng identity finish.

Nếu finisher cần tạo bản sao, đóng gói, chuyển kiểu hoặc làm kết quả unmodifiable, collector không được khai báo đặc tính này.

**UNORDERED**

Kết quả thu thập không cam kết giữ encounter order của Stream. Điều này cho phép implementation tự do hơn khi kết hợp các phần kết quả.

Không nên khai báo `UNORDERED` nếu kết quả phải giữ đúng thứ tự đầu vào. Cờ này không có nghĩa mọi lần chạy chắc chắn sẽ đảo thứ tự; nó có nghĩa collector không yêu cầu bảo toàn thứ tự đó.

**CONCURRENT**

Accumulator của collector có thể được gọi đồng thời trên cùng một result container. Container và logic accumulator phải hỗ trợ cách truy cập đồng thời này.

Đặc tính này không đồng nghĩa với việc mọi parallel stream đều thu thập bằng một container dùng chung. Điều kiện để concurrent reduction thực sự được sử dụng còn phụ thuộc vào encounter order và đặc tính `UNORDERED`.

Có thể xem tập đặc tính của một collector bằng:

~~~java
System.out.println(Collectors.toList().characteristics());
System.out.println(Collectors.toSet().characteristics());
System.out.println(Collectors.groupingByConcurrent(
        value -> value
).characteristics());
~~~

Các collector chuẩn có thể có những tập đặc tính khác nhau. Hãy đọc kết quả hoặc tài liệu API khi quyết định cách sử dụng; đừng tự thêm cờ cho collector tùy chỉnh nếu không đáp ứng đầy đủ hợp đồng.

## 4. Parallel stream vẫn dùng được collector không concurrent

Một collector không có `CONCURRENT` vẫn có thể được sử dụng với parallel stream.

Với collector thông thường, quá trình thu thập song song thường hoạt động theo cách:

1. Stream chia dữ liệu thành các phần.
2. Mỗi phần có container tích lũy riêng được tạo bởi supplier.
3. Các worker tích lũy phần tử vào container riêng của mình.
4. Combiner kết hợp các container trung gian thành kết quả tổng hợp.
5. Finisher chạy nếu collector có bước hoàn thiện riêng.

Do các container được cô lập trong quá trình tích lũy, accumulator không cần tự đồng bộ hóa chỉ vì pipeline đang chạy song song. Điều kiện quan trọng là supplier tạo container độc lập và combiner kết hợp đúng các kết quả đó.

Ví dụ:

~~~java
List<Integer> values = IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toList());
~~~

`Collectors.toList()` không phải concurrent collector, nhưng vẫn có thể thu thập từ parallel stream. Stream framework tạo và kết hợp các vùng tích lũy theo hợp đồng của collector.

Không thay cách này bằng việc sửa một ArrayList dùng chung trong `forEach`:

~~~java
List<Integer> unsafe = new ArrayList<>();

IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(unsafe::add); // Không an toàn khi nhiều thread cùng sửa ArrayList
~~~

Đoạn code cuối có nhiều thread cùng gọi `add` trên một ArrayList không thread-safe. Dùng `collect` để Stream quản lý quá trình tích lũy và kết hợp.

## 5. Khi nào xảy ra concurrent reduction?

Concurrent reduction cho phép nhiều thread gọi accumulator đồng thời trên cùng một result container thay vì giữ container riêng cho từng phần rồi kết hợp.

Điều kiện để Stream có thể chọn concurrent reduction là:

- Pipeline chạy song song.
- Collector có đặc tính `CONCURRENT`.
- Và stream không có encounter order, hoặc collector cũng có đặc tính `UNORDERED`.

Nếu collector concurrent nhưng không unordered, concurrent reduction chỉ phù hợp khi stream không yêu cầu encounter order. Điều này bảo vệ ngữ nghĩa thứ tự của những pipeline có thứ tự.

Ví dụ một collector concurrent phù hợp với dữ liệu không cần thứ tự:

~~~java
ConcurrentMap<String, Long> counts = words.parallelStream()
        .collect(Collectors.toConcurrentMap(
                word -> word,
                word -> 1L,
                Long::sum
        ));
~~~

`toConcurrentMap` tạo kết quả dạng `ConcurrentMap` và hỗ trợ gộp các giá trị trùng key bằng hàm merge `Long::sum`. Kết quả là số lần xuất hiện của mỗi từ.

Không được suy luận rằng chỉ cần gọi `parallel()` là mọi collector sẽ dùng chung một container. Với collector không có `CONCURRENT`, Stream có thể dùng các container độc lập và combiner.

## 6. Chọn giữa groupingBy và groupingByConcurrent

Hai collector này có mục đích gần nhau nhưng đặc tính thực thi khác nhau.

~~~java
Map<String, List<String>> grouped = words.parallelStream()
        .collect(Collectors.groupingBy(String::toLowerCase));

ConcurrentMap<String, List<String>> concurrentGrouped = words.parallelStream()
        .collect(Collectors.groupingByConcurrent(String::toLowerCase));
~~~

- `groupingBy` tạo Map theo key. Khi dùng với parallel stream, các Map trung gian có thể cần được kết hợp; việc merge Map lớn có thể tốn chi phí.
- `groupingByConcurrent` trả về `ConcurrentMap` và là concurrent, unordered collector. Nó có thể thu thập trực tiếp vào cấu trúc đồng thời khi điều kiện concurrent reduction được đáp ứng.

Chọn `groupingByConcurrent` khi thứ tự encounter không phải yêu cầu và dữ liệu đủ lớn để việc thu thập đồng thời có lợi. Nếu cần kết quả theo thứ tự đầu vào, dùng `groupingBy` hoặc một cấu trúc có hợp đồng thứ tự phù hợp.

Không giả định các List nằm trong Map trả về là collection thread-safe để ứng dụng tiếp tục sửa đồng thời sau khi collect hoàn tất. Đặc tính concurrent mô tả hợp đồng của collector trong quá trình tích lũy, không phải cam kết mọi đối tượng con trong kết quả đều thread-safe cho mọi thao tác về sau.

## 7. Kiểm tra kiểu kết quả của các collector thường dùng

Kiểu `R` có thể đọc từ chữ ký và kiểu đích của `collect`.

| Collector | Kiểu kết quả thường dùng | Lưu ý |
|---|---|---|
| `toList()` | `List<T>` | Không cam kết implementation, mutability, serializability hoặc thread-safety |
| `toSet()` | `Set<T>` | Không cam kết thứ tự encounter |
| `toCollection(factory)` | Kiểu collection được factory tạo | Dùng khi cần chỉ định collection cụ thể |
| `toMap(key, value)` | `Map<K,V>` | Key trùng có thể ném exception |
| `toConcurrentMap(...)` | `ConcurrentMap<K,V>` | Có merge overload để xử lý key trùng |
| `groupingBy(...)` | `Map<K,List<T>>` hoặc kiểu downstream | Gom phần tử theo key |
| `groupingByConcurrent(...)` | `ConcurrentMap<K,List<T>>` hoặc kiểu downstream | Thu thập theo nhóm bằng collector concurrent |
| `partitioningBy(...)` | `Map<Boolean,D>` | Chia thành hai nhóm true/false |
| `counting()` | `Long` | Đếm phần tử |
| `summingInt(...)` | `Integer` | Tổng giá trị int |
| `averagingInt(...)` | `Double` | Giá trị trung bình |
| `summarizingInt(...)` | `IntSummaryStatistics` | Count, sum, min, max, average |
| `joining()` | `String` | Nối các chuỗi |
| `collectingAndThen(downstream, finisher)` | Kiểu trả về của finisher | Finisher có thể đổi kiểu kết quả |

Các kiểu trên mô tả kiểu API trả về. Implementation cụ thể của List hoặc Map có thể không được cam kết. Nếu cần kiểu collection cụ thể, dùng `toCollection(ArrayList::new)`, `toCollection(TreeSet::new)` hoặc mapFactory phù hợp trong overload của `groupingBy`.

Cần phân biệt `Collectors.toList()` với `Stream.toList()`:

- `Collectors.toList()` là collector; tài liệu API không đảm bảo kiểu triển khai, khả năng sửa đổi hoặc thread-safety của List trả về.
- `Stream.toList()` được thêm từ Java 16 và trả về List unmodifiable.
- `Collectors.toUnmodifiableList()` được thêm từ Java 10 và tạo List unmodifiable.

Nếu cần List mutable, hãy chỉ định rõ:

~~~java
ArrayList<String> mutable = words.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Nếu cần List unmodifiable trên Java hiện đại, có thể dùng `Stream.toList()` hoặc collector unmodifiable phù hợp. Hãy chọn theo phiên bản Java mục tiêu và hợp đồng mà ứng dụng cần.

## 8. Xử lý key trùng trong toMap

`Collectors.toMap(keyMapper, valueMapper)` trả về Map. Nếu hai phần tử tạo ra cùng key, overload không có merge function sẽ ném `IllegalStateException`.

~~~java
Map<String, Integer> lengths = words.stream()
        .collect(Collectors.toMap(
                word -> word,
                String::length
        ));
~~~

Nếu nguồn có thể tạo key trùng, truyền merge function:

~~~java
Map<String, Integer> totalLengths = words.stream()
        .collect(Collectors.toMap(
                word -> word,
                String::length,
                Integer::sum
        ));
~~~

Nếu cần kiểu Map cụ thể, dùng overload có map supplier:

~~~java
Map<String, Integer> sorted = words.stream()
        .collect(Collectors.toMap(
                word -> word,
                String::length,
                Integer::sum,
                TreeMap::new
        ));
~~~

Với dữ liệu cần thu song song vào Map đồng thời, xem xét `toConcurrentMap` và cung cấp merge function khi key có thể trùng. Chỉ dùng collector concurrent nếu thứ tự và semantics của kết quả phù hợp.

## 9. Ví dụ hoàn chỉnh: kiểm tra kiểu và thu song song

Tạo file **CollectorTypesAndParallelDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class CollectorTypesAndParallelDemo {
    public static void main(String[] args) {
        List<String> words = List.of("red", "blue", "red", "green");

        List<String> collected = words.stream()
                .collect(Collectors.toList());

        Set<String> unique = words.stream()
                .collect(Collectors.toSet());

        Map<String, Long> counts = words.stream()
                .collect(Collectors.groupingBy(
                        word -> word,
                        Collectors.counting()
                ));

        ConcurrentMap<String, Long> parallelCounts = words.parallelStream()
                .collect(Collectors.toConcurrentMap(
                        word -> word,
                        word -> 1L,
                        Long::sum
                ));

        List<Integer> numbers = IntStream.rangeClosed(1, 1000)
                .parallel()
                .boxed()
                .collect(Collectors.toList());

        Collector<String, List<String>, List<String>> snapshotCollector =
                Collector.of(
                        ArrayList::new,
                        List::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf
                );

        List<String> snapshot = Stream.of("A", "B", "C", "D")
                .parallel()
                .collect(snapshotCollector);

        System.out.println("collected type: List, size=" + collected.size());
        System.out.println("unique size: " + unique.size());
        System.out.println("red count: " + counts.get("red"));
        System.out.println("parallel red count: " + parallelCounts.get("red"));
        System.out.println("parallel number count: " + numbers.size());
        System.out.println("snapshot: " + snapshot);

        try {
            snapshot.add("E");
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot is unmodifiable");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac CollectorTypesAndParallelDemo.java
java CollectorTypesAndParallelDemo
~~~

Kết quả stdout:

~~~text
collected type: List, size=4
unique size: 3
red count: 2
parallel red count: 2
parallel number count: 1000
snapshot: [A, B, C, D]
snapshot is unmodifiable
~~~

Giải thích:

- `collected` có kiểu kết quả khai báo là `List<String>`.
- `unique` có kiểu kết quả `Set<String>`; số phần tử còn 3 vì red trùng.
- `counts` là Map từ từ sang số lần xuất hiện.
- `parallelCounts` là ConcurrentMap thu thập bằng `toConcurrentMap`.
- `numbers` dùng parallel stream với collector `toList()` thông thường; parallel reduction không yêu cầu collector concurrent.
- `snapshotCollector` tích lũy bằng List mutable riêng, kết hợp các phần kết quả rồi dùng finisher `List.copyOf` để trả về List unmodifiable.

## 10. Quy tắc khi tự viết Collector

Collector tùy chỉnh phải đáp ứng hợp đồng identity và associativity để kết quả đúng dù Stream thực hiện tuần tự hay chia thành nhiều phần.

- Supplier phải tạo container rỗng phù hợp; mỗi lần gọi cần trả về container độc lập.
- Accumulator phải cập nhật container theo đúng một phần tử đầu vào.
- Combiner phải kết hợp hai container tương thích và bảo đảm kết quả tương đương với việc tích lũy toàn bộ phần tử theo hợp đồng.
- Finisher phải chuyển trạng thái tích lũy thành kết quả cuối cùng đúng kiểu `R`.
- Chỉ khai báo `IDENTITY_FINISH`, `UNORDERED`, `CONCURRENT` khi implementation đáp ứng chính xác ý nghĩa của từng cờ.

Với collector không concurrent, không chia sẻ container tích lũy giữa các worker. Với collector concurrent, accumulator và container phải thực sự hỗ trợ cập nhật đồng thời. Không đánh dấu collector là concurrent chỉ vì nó được dùng cùng parallel stream.

Predicate, mapper và accumulator cũng nên tránh tác dụng phụ không cần thiết lên nguồn hoặc trạng thái dùng chung. Dùng các hàm có tính kết hợp và không can thiệp vào dữ liệu đang xử lý giúp kết quả ổn định hơn.

## 11. Checklist chọn collector và chế độ thu thập

- Xác định kiểu phần tử đầu vào `T` và kiểu kết quả mong muốn `R`.
- Phân biệt container tích lũy `A` với kết quả cuối cùng `R`.
- Dùng `toCollection` hoặc mapFactory nếu cần implementation cụ thể.
- Dùng merge function khi key của `toMap` có thể trùng.
- Dùng collector thường với parallel stream khi cần kết quả có thứ tự hoặc khi collector không concurrent; Stream sẽ kết hợp các container riêng.
- Dùng collector `CONCURRENT` khi accumulator và container hỗ trợ đồng thời.
- Chỉ dựa vào concurrent reduction khi pipeline parallel và điều kiện `CONCURRENT` cùng quy tắc encounter order/`UNORDERED` được đáp ứng.
- Dùng `groupingByConcurrent` hoặc `toConcurrentMap` khi semantics unordered phù hợp với nghiệp vụ.
- Không chia sẻ ArrayList hoặc HashMap mutable để nhiều thread tự cập nhật trong `forEach`.
- Không suy luận mutability, thứ tự hoặc thread-safety từ kiểu interface List/Map.

Kiểm tra kiểu kết quả và đặc tính collector giúp chọn đúng API, tránh phụ thuộc vào implementation không được cam kết và hiểu rõ khi nào Stream có thể thu thập song song hoặc đồng thời.
