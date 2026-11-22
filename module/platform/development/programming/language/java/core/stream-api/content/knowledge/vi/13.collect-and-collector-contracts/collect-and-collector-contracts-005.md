# Đặc tính IDENTITY_FINISH, UNORDERED và CONCURRENT

Khi gọi `stream.collect(collector)`, người lập trình thường nhìn thấy kết quả như `List`, `Map` hoặc một thống kê tổng hợp. Bên trong, Java Stream API cần biết **có thể tạo nhiều bộ tích lũy rồi gộp không**, **có cần giữ thứ tự gặp phần tử không**, và **có được phép cho các luồng cùng tích lũy vào một bộ chứa không**. Ba đặc tính của `Collector.Characteristics` — `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT` — diễn đạt những cam kết đó.

Bài học thuộc chương **Cơ chế collect và Collector** của module `JAVA_STREAM_API`. Mục tiêu là hiểu đúng hợp đồng của ba đặc tính, cách chúng tương tác với pipeline lazy, `filter`, `map`, `collect` và `parallel()`, cách tự xây Collector không khai báo sai khả năng, và lúc nào nên dùng các collector chuẩn như `toList`, `groupingBy`, `groupingByConcurrent`. Những quyết định này liên quan trực tiếp đến trạng thái chia sẻ, thứ tự kết quả, tính đúng đắn và chi phí hiệu năng.

> Các API cốt lõi được trình bày ở đây có từ Java 8. Mã ví dụ dùng `Arrays.asList` và `Collectors` để có thể áp dụng cho những dự án còn ở Java 8.

## 1. Collector là hợp đồng rút gọn dữ liệu

Một `Collector<T, A, R>` mô tả cách tổng hợp dữ liệu:

- `T`: kiểu phần tử đầu vào của Stream.
- `A`: kiểu **bộ tích lũy trung gian** (*accumulation type*).
- `R`: kiểu **kết quả cuối** sau khi hoàn tất.

Ví dụ khi đếm số từ, `T` có thể là `String`, `A` là một bộ đếm có thể thay đổi, còn `R` là `Long`.

Một Collector có năm thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `supplier()` | Tạo bộ tích lũy `A` mới |
| `accumulator()` | Thêm một phần tử `T` vào bộ tích lũy `A` |
| `combiner()` | Gộp hai bộ tích lũy `A` thành một `A` |
| `finisher()` | Chuyển `A` thành kết quả `R` |
| `characteristics()` | Khai báo các tính chất mà trình thực thi được phép dựa vào |

Minh họa về mặt logic:

```text
                Stream<T>
                    |
         filter / map / flatMap
                    |
             collect(collector)
                    |
          +---------+---------+
          |                   |
      supplier()          supplier()
          |                   |
       A nhánh 1           A nhánh 2
          |                   |
     accumulator          accumulator
          |                   |
          +------ combiner ---+
                    |
                  A gộp
                    |
                 finisher
                    |
                  R cuối
```

Sơ đồ có hai nhánh để giải thích `combiner`, không phải lời hứa Java luôn phân luồng như vậy. Collector có thể chạy tuần tự hoặc song song; tùy đặc tính, Java cũng có thể tích lũy đồng thời vào **cùng một bộ chứa** thay vì dùng nhiều bộ chứa riêng.

`collect` là **terminal operation**: việc gọi nó kích hoạt pipeline lazy và tiêu thụ Stream. Nó không tự đóng một nguồn I/O cần `close()`, chẳng hạn Stream do `Files.lines` trả về; trách nhiệm đóng tài nguyên vẫn phải được xử lý riêng.

## 2. Bảng ý nghĩa của ba Characteristics

Trong Java, tập đặc tính được biểu diễn bằng enum `Collector.Characteristics`.

| Đặc tính | Cam kết của Collector | Điều **không** nên suy luận |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher tương đương phép đồng nhất: kết quả tích lũy có thể dùng trực tiếp làm kết quả cuối | Không có nghĩa bộ chứa bất biến, không có nghĩa thread-safe |
| `UNORDERED` | Phép tổng hợp không cam kết duy trì encounter order của các phần tử đầu vào | Không có nghĩa dữ liệu bị xáo trộn ngẫu nhiên; không tự tạo concurrency |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời từ nhiều luồng trên **cùng một** bộ chứa | Không có nghĩa nguồn tự thành parallel; không đồng nghĩa với `UNORDERED` |

Ba đặc tính **không loại trừ lẫn nhau**. Một collector có thể có nhiều đặc tính cùng lúc, hoặc không khai báo đặc tính nào. Mỗi đặc tính cần được chứng minh bằng thiết kế thật của `supplier`, `accumulator`, `combiner`, `finisher`; không phải là công tắc “bật tối ưu” mà có thể chọn tùy thích.

## 3. IDENTITY_FINISH: bộ tích lũy cũng là kết quả cuối

`IDENTITY_FINISH` nghĩa là hàm `finisher` thực chất không phải chuyển đổi: sau khi tích lũy, Java có thể sử dụng chính đối tượng kiểu `A` làm kết quả `R`. Theo hợp đồng, phép chuyển từ `A` sang `R` phải hợp lệ, kể cả khi implementation bỏ qua việc gọi `finisher()` và chuyển kiểu trực tiếp.

Ví dụ tạo Collector thu thập `String` vào `ArrayList<String>`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.stream.Collector;

Collector<String, ArrayList<String>, ArrayList<String>> listCollector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );

ArrayList<String> values = Arrays.asList("A", "B", "C")
        .stream()
        .collect(listCollector);

System.out.println(values); // [A, B, C]
System.out.println(listCollector.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // true
```

Ở overload `Collector.of(supplier, accumulator, combiner, characteristics...)` không có hàm finisher riêng, `IDENTITY_FINISH` được khai báo tự động. Ở đây `A` và `R` cùng là `ArrayList<String>`, nên có thể trả trực tiếp container sau khi kết hợp.

Điểm cần nhớ: danh sách này vẫn **mutable** và không mặc nhiên an toàn cho nhiều luồng cùng thêm phần tử. `IDENTITY_FINISH` chỉ nói về bước hoàn tất, không cấp thêm bảo đảm về an toàn luồng hay kiểu collection cụ thể.

### Không có IDENTITY_FINISH khi cần chuyển kiểu kết quả

Muốn ghép văn bản thành `String` từ bộ chứa `StringJoiner`:

```java
import java.util.Arrays;
import java.util.StringJoiner;
import java.util.stream.Collector;

Collector<String, StringJoiner, String> joining =
        Collector.of(
                () -> new StringJoiner(", "),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
        );

String text = Arrays.asList("Java", "Stream", "API")
        .stream()
        .collect(joining);

System.out.println(text); // Java, Stream, API
System.out.println(joining.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // false
```

`A` là `StringJoiner` nhưng `R` là `String`. Nếu khai báo sai `IDENTITY_FINISH` cho collector này, trình thực thi được phép bỏ qua `StringJoiner::toString` và coi bộ chứa là kết quả. Đây là **vi phạm hợp đồng**, có thể dẫn đến kết quả sai hoặc lỗi chuyển kiểu.

Cũng không được khai báo `IDENTITY_FINISH` nếu bước cuối cần sao chép container, làm bất biến kết quả, chuẩn hóa hoặc tính một chỉ số từ bộ tích lũy.

### collectingAndThen thay đổi ý nghĩa bước hoàn tất

`Collectors.collectingAndThen(downstream, finisher)` bổ sung phép biến đổi **sau** khi downstream hoàn thành. Ví dụ tạo danh sách không thể chỉnh sửa từ kết quả:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, List<String>> readonly =
        Collectors.collectingAndThen(
                Collectors.toList(),
                Collections::unmodifiableList
        );

List<String> result = Arrays.asList("A", "B")
        .stream()
        .collect(readonly);

System.out.println(result); // [A, B]
System.out.println(readonly.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // false
```

Vì có finisher mới, đặc tính `IDENTITY_FINISH` không còn được giữ lại. `Collections.unmodifiableList` tạo **lớp nhìn không sửa được** trên danh sách bên trong; nó không tự sao chép dữ liệu. Khi cần một bản sao bất biến có ngữ nghĩa khác, thiết kế finisher phù hợp và vẫn **không** khai báo `IDENTITY_FINISH`.

**Một lưu ý quan trọng:** `Collectors.toList()` không cam kết kết quả thuộc `ArrayList`, có tính mutable hay thread-safe. Không dựa vào lớp cài đặt hiện tại của JDK để tự suy ra hợp đồng ổn định cho mọi phiên bản.

## 4. UNORDERED: không đòi hỏi encounter order

*Encounter order* là thứ tự gặp phần tử do nguồn và các thao tác trung gian xác định. Ví dụ `List.stream()` có thứ tự theo vị trí danh sách, còn nguồn như `HashSet` không cam kết một thứ tự gặp cố định.

`UNORDERED` nói rằng **Collector không yêu cầu bảo toàn encounter order trong kết quả**. Đây là đặc tính **của phép thu thập**, khác với `stream.unordered()` là thao tác trung gian trên pipeline.

Ví dụ so sánh một danh sách và một tập:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> source = Arrays.asList("B", "A", "B", "C");

List<String> asList = source.stream()
        .collect(Collectors.toList());

Set<String> asSet = source.stream()
        .collect(Collectors.toSet());

System.out.println(asList); // [B, A, B, C]
System.out.println(asSet.size());  // 3
System.out.println(asSet.contains("A")); // true
```

`Collectors.toList()` thu thập các phần tử theo encounter order khi nguồn có thứ tự. `Collectors.toSet()` được quy định là **unordered collector**: điều quan trọng là các phần tử khác nhau có mặt trong tập, không phải thứ tự khi duyệt `Set`.

Đừng khẳng định `asSet` luôn in thành `[A, B, C]` hay một thứ tự cụ thể: loại Set và thứ tự duyệt không được bảo đảm bởi `toSet()`.

### UNORDERED không có nghĩa xáo trộn dữ liệu

`UNORDERED` không phải yêu cầu sắp xếp ngẫu nhiên. Java **được phép** thực thi một cách giữ thứ tự trong một số trường hợp, nhưng người sử dụng **không được phụ thuộc vào điều đó**. Nó cũng không tự loại trùng: loại trùng là quyết định của Collector cụ thể, như `toSet()`.

Tương tự, `stream.unordered()` chỉ bỏ ràng buộc thứ tự của pipeline, không tạo một thao tác `shuffle`. Nếu nghiệp vụ cần “ba đơn hàng đầu tiên theo thời gian”, việc sử dụng nguồn unordered hoặc collector unordered sẽ không tự bảo vệ ý nghĩa “đầu tiên”.

### Thứ tự sắp xếp của kết quả là vấn đề riêng

Một collection có thể áp dụng **thứ tự nội tại** mà không có nghĩa phải giữ encounter order của nguồn. Ví dụ:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

Set<Integer> sortedValues = Arrays.asList(9, 2, 9, 4)
        .stream()
        .collect(Collectors.toCollection(TreeSet::new));

System.out.println(sortedValues); // [2, 4, 9]
```

Thứ tự này do `TreeSet` sắp xếp theo quy tắc so sánh, không phải thứ tự gặp `9, 2, 9, 4`. Đặc tính `UNORDERED` nói về việc collector có bắt buộc giữ encounter order hay không; nó không có nghĩa cấu trúc kết quả không thể có thứ tự riêng.

## 5. CONCURRENT: nhiều luồng có thể tích lũy vào cùng một A

`CONCURRENT` là cam kết mạnh hơn việc “đôi khi chạy với `parallelStream()`”. Nó cho phép trình thực thi gọi `accumulator` đồng thời từ nhiều luồng **trên chính cùng một đối tượng bộ tích lũy `A`**.

Vì vậy, bộ chứa và hành vi cập nhật **phải chịu được các lời gọi đồng thời**. Một `ArrayList` thông thường không tự đáp ứng hợp đồng này, dù `combiner` của nó có thể gộp hai danh sách độc lập một cách hợp lệ.

Nhưng cần phân biệt hai chiến lược thu thập:

```text
Chiến lược A: nhiều container độc lập
  supplier -> A1 --\
                    +-- combiner -> A cuối
  supplier -> A2 --/

Chiến lược B: cùng một container
  luồng 1 -- accumulator --\
  luồng 2 -- accumulator ---+--> A dùng chung
  luồng 3 -- accumulator --/
          (A phải an toàn cho cập nhật đồng thời)
```

Một Stream chạy parallel **không bắt buộc** sử dụng chiến lược B; Java có thể chọn cách phân mảnh, kết hợp và tối ưu tùy đặc tính. Ngược lại, việc có `CONCURRENT` cũng **không tự biến** một `stream()` tuần tự thành `parallelStream()`.

### Collector chuẩn: groupingByConcurrent

`Collectors.groupingByConcurrent` là lựa chọn phù hợp khi muốn gom nhóm vào `ConcurrentMap` mà không yêu cầu giữ encounter order trong các nhóm:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

List<String> names = Arrays.asList(
        "java", "junit", "spring", "sql", "streams"
);

ConcurrentMap<Character, Long> counts = names.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                text -> text.charAt(0),
                Collectors.counting()
        ));

System.out.println(counts.get('j')); // 2
System.out.println(counts.get('s')); // 3
```

Kết quả là một `ConcurrentMap`, nhưng thứ tự duyệt các khóa **không được bảo đảm**. `groupingByConcurrent` là một collector **concurrent và unordered**. Việc một downstream collector như `counting()` không tự tuyên bố `CONCURRENT` không có nghĩa phải tự ý chia sẻ container downstream: implementation của `groupingByConcurrent` chịu trách nhiệm phối hợp cập nhật theo hợp đồng của nó.

Nếu muốn nhóm thành danh sách theo đúng thứ tự gặp phần tử, `groupingByConcurrent(..., toList())` **không bảo đảm thứ tự phần tử của danh sách trong từng nhóm**. Ngoài ra, việc trả về `ConcurrentMap` không làm cho mọi giá trị mutable bên trong map (như `ArrayList`) tự nhiên an toàn cho thay đổi đồng thời **sau** khi thu thập. Phải phân biệt an toàn trong quá trình collect và an toàn khi các luồng ngoài truy cập/chỉnh sửa kết quả.

### So sánh groupingBy và groupingByConcurrent

| Collector | Kết quả thông thường | Cam kết quan trọng |
| --- | --- | --- |
| `groupingBy(classifier)` | `Map<K,List<T>>` | Không phải concurrent collector; có thể phải gộp map khi chạy song song |
| `groupingByConcurrent(classifier)` | `ConcurrentMap<K,List<T>>` | Concurrent, unordered; **không** giữ encounter order của các phần tử theo nhóm |
| `groupingBy(classifier, downstream)` | `Map<K,D>` | Theo hợp đồng của downstream và collector ngoài |
| `groupingByConcurrent(classifier, downstream)` | `ConcurrentMap<K,D>` | Collector ngoài concurrent và unordered; downstream có thể được phối hợp an toàn trong lúc thu thập |

Không nên tuyên bố rằng `groupingByConcurrent` **luôn nhanh hơn** `groupingBy`. Chi phí tranh chấp khóa, số nhóm khác nhau, kích thước nguồn, downstream collector và đặc điểm phân hoạch quyết định kết quả đo thực tế.

## 6. Khi nào Java được phép thu thập concurrent vào một container?

Ba yếu tố cần xem đồng thời:

1. Stream đang chạy **parallel** hay **sequential**?
2. Collector có đặc tính `CONCURRENT` không?
3. Stream có encounter order cần giữ không, và Collector có `UNORDERED` không?

Điều kiện thực tế để framework **được phép** dùng chiến lược một container chia sẻ trong phép collect song song là: Collector `CONCURRENT` **và** (Stream không có encounter order **hoặc** Collector `UNORDERED`). Việc đáp ứng điều kiện không có nghĩa framework buộc phải chọn cách này trong mọi trường hợp.

| Stream | Collector | Có thể tích lũy chung theo hợp đồng? | Lý do |
| --- | --- | --- | --- |
| Sequential | `CONCURRENT + UNORDERED` | Không cần concurrent | Chỉ một luồng xử lý pipeline |
| Parallel, có encounter order | Chỉ `CONCURRENT` | Không dùng chiến lược chung nếu nó phá encounter order | Collector chưa từ bỏ yêu cầu thứ tự |
| Parallel, có encounter order | `CONCURRENT + UNORDERED` | **Có** | Collector cho phép bỏ ràng buộc thứ tự |
| Parallel, không có encounter order | Chỉ `CONCURRENT` | **Có** | Không còn yêu cầu bảo toàn encounter order |
| Parallel, bất kỳ nguồn | Chỉ `UNORDERED` | Không đủ để chia sẻ cùng container | Không tuyên bố accumulator an toàn khi đồng thời |
| Parallel, bất kỳ nguồn | Chỉ `IDENTITY_FINISH` | Không đủ để chia sẻ cùng container | Đặc tính finisher không nói về concurrency |

Cách ghi nhớ ngắn: **`CONCURRENT` trả lời “có an toàn khi cập nhật chung không?”; `UNORDERED` trả lời “có được bỏ yêu cầu thứ tự không?”**. Cả hai điều kiện có thể cùng cần để đạt con đường tối ưu thu thập đồng thời trên một Stream vốn có thứ tự.

Đừng nhầm với `Collectors.toConcurrentMap`: các biến thể Collector được thiết kế để tạo `ConcurrentMap` thường là concurrent và unordered, nhưng vẫn phải chọn merge function phù hợp khi trùng khóa. Một collector tự tạo trả về `ConcurrentHashMap` **không tự động** mang đặc tính `CONCURRENT` nếu chưa thiết kế accumulator phù hợp và khai báo đúng.

## 7. Tự xây Collector có CONCURRENT + UNORDERED

Ví dụ tính tổng số nguyên từ `Stream<Integer>` bằng `LongAdder`, một bộ đếm hỗ trợ cập nhật đồng thời. Đây là ví dụ về cách định nghĩa đặc tính cho collector tự viết; nếu chỉ cần tổng số nguyên, `mapToLong(...).sum()` thường là lựa chọn đơn giản hơn.

```java
import java.util.stream.Collector;
import java.util.stream.IntStream;
import java.util.concurrent.atomic.LongAdder;

Collector<Integer, LongAdder, Long> sumCollector =
        Collector.of(
                LongAdder::new,
                (adder, number) -> adder.add(number),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );

long total = IntStream.rangeClosed(1, 100_000)
        .boxed()
        .parallel()
        .collect(sumCollector);

System.out.println(total); // 5000050000
System.out.println(sumCollector.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // false
```

Phân tích:

- `supplier` tạo `LongAdder` mới. Mỗi bộ đếm có trạng thái ban đầu bằng 0.
- `accumulator` thêm một `Integer` vào tổng và an toàn nếu nhiều luồng cập nhật cùng `LongAdder`.
- `combiner` gộp tổng của container phải vào container trái. Nó vẫn phải đúng ngay cả khi một đường thực thi cụ thể không gọi nó.
- `finisher` dùng `LongAdder::sum` để chuyển `A = LongAdder` thành `R = Long`.
- `CONCURRENT` đúng vì accumulator có thể chạy trên cùng bộ đếm.
- `UNORDERED` đúng vì phép tổng ở đây không cần thứ tự gặp phần tử.
- **Không** có `IDENTITY_FINISH` vì `LongAdder` không thể dùng trực tiếp như `Long`.

Với phạm vi `1..100_000`, tổng nằm trong miền `long`. Nếu tổng có thể tràn `long`, hoặc nếu phép tổng sử dụng số thực có sai số làm tròn, cần xem lại loại dữ liệu và hợp đồng tương đương. Việc dùng `LongAdder` không tự bảo đảm mọi bài toán số học đúng.

### Nguy cơ khi dùng ArrayList mà khai báo CONCURRENT

Không làm theo cách dưới đây:

```java
import java.util.ArrayList;
import java.util.stream.Collector;

// VÍ DỤ SAI: ArrayList::add không an toàn khi nhiều luồng cùng thêm.
Collector<Integer, ArrayList<Integer>, ArrayList<Integer>> unsafe =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
```

Khi framework dùng tích lũy chung, hai luồng có thể đồng thời sửa cùng `ArrayList`, gây mất dữ liệu hoặc trạng thái không hợp lệ. `CONCURRENT` không tạo khóa hay tự động đồng bộ. Nếu muốn gom danh sách theo thứ tự encounter order, bỏ hai đặc tính được khai báo sai và dùng `Collectors.toList()` hoặc một collector giữ đúng hợp đồng.

Không nên thử tăng kích thước `ArrayList` trước hay dùng `Collections.synchronizedList` như một cách “vá” máy móc. Dù đồng bộ hóa có thể giúp một số cập nhật an toàn, vẫn cần xác minh cả thứ tự, hiệu năng, identity, combiner và chính xác là kết quả nào được cam kết.

## 8. IDENTITY_FINISH, UNORDERED và CONCURRENT tương tác với nhau thế nào?

Ba đặc tính trực giao về ý nghĩa: một collector có thể giữ bất kỳ tổ hợp **hợp lệ** nào, nếu các hàm bên trong thật sự thỏa hợp đồng.

| Tổ hợp | Ví dụ ý nghĩa | Lưu ý |
| --- | --- | --- |
| Không khai báo đặc tính nào | Tích lũy vào `StringJoiner` rồi đổi thành `String`, yêu cầu thứ tự | Dùng finisher thật; không giả định concurrent |
| `IDENTITY_FINISH` | Gộp trực tiếp vào `ArrayList` và trả lại container | Không có an toàn luồng |
| `UNORDERED` | Gom tập không quan tâm encounter order | Chỉ bỏ ràng buộc thứ tự |
| `CONCURRENT` | Container hỗ trợ cập nhật chung, nhưng Collector vẫn quan tâm thứ tự khi có encounter order | Không tự cấp quyền bỏ thứ tự |
| `CONCURRENT + UNORDERED` | Đếm/tổng hợp dùng cấu trúc thread-safe và không quan tâm thứ tự | Có thể tận dụng tích lũy chung trên parallel Stream có thứ tự |
| `IDENTITY_FINISH + CONCURRENT + UNORDERED` | Trả trực tiếp một container đồng thời, không cần finisher chuyển kiểu | Vẫn phải chứng minh combiner, accumulator đúng |

Lấy kết quả của `collector.characteristics()` để **kiểm tra điều đã khai báo**, không coi nó như phép thử tự động xác nhận code thread-safe.

```java
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, Set<String>> toSet = Collectors.toSet();

boolean unordered = toSet.characteristics()
        .contains(Collector.Characteristics.UNORDERED);

System.out.println(unordered); // true
```

Trong chương trình thực tế, một bộ sưu tập trả về có thể có những đặc tính tùy theo overload và downstream collector; nếu cần quyết định thiết kế dựa vào characteristic, hãy đọc hợp đồng API của collector cụ thể thay vì đoán từ tên phương thức.

## 9. Hiểu đúng về hợp đồng Collector và tối ưu hiệu năng

Các đặc tính chỉ hữu ích khi năm hàm của Collector tuân thủ các quy tắc nền tảng:

### 9.1. Identity và phép gộp có tính kết hợp

`supplier` phải tạo container “rỗng” đúng nghĩa. `combiner(a, supplier.get())` phải cho kết quả tương đương `a`. Khi gộp ba container `a, b, c`, cách chia nhóm phải cho kết quả tương đương về nghiệp vụ. Đây là điều kiện để Stream có thể rút gọn theo nhiều nhánh.

### 9.2. Accumulator và combiner phải tương thích

Gộp một giá trị `t` vào `a` trực tiếp phải tương đương với việc gộp `a` và container mới chứa riêng `t`:

```text
accumulate(a, t)
  tương đương với
combine(a, accumulate(supplier(), t))
```

Đây là cách kiểm tra tư duy, không phải biểu thức Java có thể gọi nguyên xi: `accumulator` thường là `void`, nên sơ đồ dùng khái niệm trạng thái trước/sau.

### 9.3. Tránh tác dụng phụ ngoài Collector

Đừng sửa `List` nguồn từ `filter`, tăng biến đếm dùng chung trong `map` hoặc ghi vào một `HashMap` bên ngoài trong khi pipeline parallel chạy. Các đặc tính của `Collector` **không bảo vệ** những side effect ở pipeline phía trước Collector.

### 9.4. Chi phí không chỉ nằm ở số luồng

`CONCURRENT` có thể tránh chi phí tạo nhiều container và combine, nhưng có thể gây tranh chấp cùng một cấu trúc. `UNORDERED` có thể cho phép chiến lược linh hoạt hơn, nhưng nếu nghiệp vụ cần kết quả theo thứ tự thì đánh đổi đó không hợp lệ. `IDENTITY_FINISH` có thể tránh phép chuyển đổi cuối, nhưng lợi ích nhỏ nếu phần lớn thời gian dành cho I/O, hash, truy vấn DB hoặc sắp xếp.

Một phép tối ưu chỉ có ý nghĩa khi **vẫn giữ đúng hợp đồng dữ liệu**. Hãy đo với kích thước đầu vào, phân bố khóa, tỷ lệ trùng, kiểu collector, đặc tính `Spliterator` và JDK thực tế.

## 10. Ví dụ tổng hợp: chọn đúng collector cho báo cáo sự kiện

Giả sử các sự kiện có mã loại như `"INFO"`, `"WARN"` và `"ERROR"`. Hai yêu cầu khác nhau nên dẫn đến hai cách thu thập khác nhau.

### Yêu cầu A: giữ nguyên chuỗi sự kiện theo thứ tự

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> events = Arrays.asList(
        "INFO: started",
        "WARN: slow",
        "INFO: resumed",
        "ERROR: failed"
);

List<String> visible = events.parallelStream()
        .filter(line -> line.startsWith("INFO"))
        .collect(Collectors.toList());

System.out.println(visible);
// [INFO: started, INFO: resumed]
```

Vì muốn hiển thị theo encounter order của danh sách, **không** khai báo `UNORDERED` cho một collector danh sách tự chế. `parallelStream()` không mặc nhiên làm mất encounter order của `collect(toList())`.

### Yêu cầu B: chỉ đếm số sự kiện từng loại

```java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = events.parallelStream()
        .map(line -> line.substring(0, line.indexOf(':')))
        .collect(Collectors.groupingByConcurrent(
                category -> category,
                Collectors.counting()
        ));

System.out.println(counts.get("INFO"));  // 2
System.out.println(counts.get("WARN"));  // 1
System.out.println(counts.get("ERROR")); // 1
```

Lúc này thứ tự sự kiện không ảnh hưởng đến số lượng mỗi loại. `groupingByConcurrent` phù hợp với cách tổng hợp không cần encounter order; song vẫn không có bảo đảm nó nhanh hơn với dữ liệu nhỏ. `map` ở ví dụ giả định mọi dòng có dấu `:`; trên dữ liệu thực phải xử lý trường hợp đầu vào sai định dạng trước khi cắt chuỗi.

Nếu cần **đếm theo loại đồng thời lưu thứ tự các sự kiện trong từng loại**, đừng dùng `groupingByConcurrent(..., toList())` rồi mặc định các danh sách sẽ giữ encounter order. Hãy dùng collector giữ thứ tự phù hợp, hoặc thiết kế khóa/thứ tự hiển thị rõ ràng ở bước sau.

## 11. Các lỗi dễ mắc

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Khai báo `IDENTITY_FINISH` khi `A` là `StringBuilder` và `R` là `String` | Finisher chuyển kiểu có thể bị bỏ qua | Bỏ `IDENTITY_FINISH`, giữ finisher thật |
| Suy ra `IDENTITY_FINISH` đồng nghĩa với kết quả immutable | Trạng thái vẫn có thể sửa được | Quyết định tính bất biến bằng kiểu kết quả và finisher |
| Suy ra `UNORDERED` nghĩa là tự xáo trộn phần tử | Đây chỉ là sự từ bỏ cam kết thứ tự | Đừng dựa vào thứ tự tình cờ khi không được bảo đảm |
| Khai báo `UNORDERED` cho Collector cần bảo toàn encounter order | Kết quả có thể đổi thứ tự trong parallel | Bỏ `UNORDERED` hoặc sửa yêu cầu nghiệp vụ |
| Khai báo `CONCURRENT` cho `ArrayList::add` | Cùng container bị nhiều luồng sửa không an toàn | Chọn collector đúng hoặc container concurrent phù hợp |
| Cho rằng `parallel()` bắt buộc kích hoạt cùng container | Java có thể tạo nhiều container và gộp | Viết combiner đúng trong mọi trường hợp |
| Cho rằng `CONCURRENT` bắt buộc có `UNORDERED` | Hai cam kết khác nhau | Giữ `UNORDERED` chỉ khi nghiệp vụ cho phép |
| Cho rằng `ConcurrentMap<K,List<V>>` bảo đảm List an toàn để sửa ở mọi lúc | Thread-safety của map không lan sang giá trị mutable | Quản lý vòng đời và đồng bộ của List riêng |
| Cho rằng downstream `counting()` phải là concurrent để `groupingByConcurrent` hoạt động | Collector ngoài có thể phối hợp cập nhật downstream | Dùng API chuẩn theo hợp đồng thay vì sửa chia sẻ dữ liệu |
| Gọi `collect` xong nghĩ Stream I/O đã đóng | Terminal operation không tự gọi `close` | `try-with-resources` tại nơi sở hữu nguồn |
| Chỉ kiểm tra kết quả tuần tự rồi khai báo `CONCURRENT` | Sai sót có thể chỉ xuất hiện trong parallel | Kiểm tra combiner, thử parallel, xem xét an toàn luồng và hợp đồng |

## 12. Câu hỏi tự kiểm tra

1. `IDENTITY_FINISH` nói về bước nào? **Finisher**: có thể dùng `A` trực tiếp làm `R`, không cần phép chuyển kiểu có ý nghĩa.
2. `IDENTITY_FINISH` có bảo đảm container thread-safe không? **Không**; đặc tính này không nói về concurrency.
3. `UNORDERED` có nghĩa là Java bắt buộc đảo ngẫu nhiên kết quả không? **Không**; chỉ không cam kết encounter order.
4. `CONCURRENT` có nghĩa là accumulator được phép gọi trên cùng `A` từ nhiều luồng không? **Có**, nên cập nhật trên `A` phải an toàn đồng thời.
5. Khi Stream parallel có encounter order, collector `CONCURRENT` nhưng không `UNORDERED` có thể tự do tích lũy chung không? **Không**, nếu làm vậy phá ràng buộc thứ tự; cần chiến lược tôn trọng encounter order.
6. Một collector `UNORDERED` nhưng không `CONCURRENT` có thể được chia sẻ một `ArrayList` để nhiều luồng thêm tự do không? **Không**, vì không hề có bảo đảm an toàn cập nhật đồng thời.
7. Vì sao `StringJoiner::toString` không đi với `IDENTITY_FINISH` khi `R` là `String`? **Vì** `A` và `R` khác kiểu, finisher phải thực sự chuyển đổi.
8. `groupingByConcurrent` có bảo đảm thứ tự giá trị trong từng nhóm không? **Không**, nó là unordered collector.
9. Nếu `Collector.of` chỉ nhận supplier, accumulator và combiner, đặc tính hoàn tất được khai báo là gì? **IDENTITY_FINISH**.
10. Có nên chọn `CONCURRENT + UNORDERED` để lấy top năm bản ghi **đầu tiên** theo thời gian không? **Không**, bởi yêu cầu đầu tiên cần giữ thứ tự và quy tắc chọn rõ ràng.

**Nguyên tắc áp dụng:** Khai báo đặc tính Collector là **cam kết về tính đúng đắn**, không phải mẹo để chạy nhanh. `IDENTITY_FINISH` chỉ hợp lệ khi bộ tích lũy cũng là kết quả; `UNORDERED` chỉ hợp lệ khi nghiệp vụ không cần encounter order; `CONCURRENT` chỉ hợp lệ khi accumulator thực sự có thể cập nhật cùng container từ nhiều luồng. Hãy chọn Collector có sẵn khi đáp ứng yêu cầu, tự xây Collector khi cần và chỉ tối ưu parallel sau khi đã chứng minh đúng hợp đồng.
