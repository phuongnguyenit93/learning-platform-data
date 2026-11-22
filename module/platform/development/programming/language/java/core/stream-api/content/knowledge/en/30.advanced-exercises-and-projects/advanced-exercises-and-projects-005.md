# Sửa pipeline song song có lỗi trạng thái dùng chung

## 1. Bối cảnh bài tập: code chạy tuần tự đúng nhưng song song lại sai

Trong **Java Stream API**, chuyển `stream()` thành `parallelStream()` hoặc gọi `parallel()` có thể giúp chia một số công việc xử lý dữ liệu cho nhiều tác vụ. Tuy nhiên, một pipeline đang hoạt động đúng khi tuần tự **không tự động trở nên an toàn khi chạy song song**. Sai lầm thường gặp là lambda trong `forEach`, `filter` hoặc `map` cùng đọc và sửa một biến, một danh sách, một Map hoặc chính nguồn đang được duyệt.

Ví dụ phản diện:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add); // SAI: nhiều tác vụ cùng sửa một ArrayList.

System.out.println(shared.size());
// Không có bảo đảm bằng 10_000; thậm chí có thể phát sinh ngoại lệ.
```

`ArrayList.add` không hỗ trợ cập nhật đồng thời an toàn. Lỗi có thể biểu hiện bằng **mất phần tử**, kích thước sai, cấu trúc nội bộ không nhất quán hoặc ngoại lệ. Một lần chạy ra đúng 10.000 **không chứng minh code đúng**: lịch chạy của các tác vụ không cố định.

Cách sửa thường tốt nhất **không phải thêm khóa vào từng lời gọi `add`**, mà là để Stream tự quản lý phép thu thập:

```java
List<Integer> result = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();

System.out.println(result.size()); // 10000
System.out.println(result.get(0)); // 0
```

Với nguồn `IntStream.range` có encounter order, `toList()` giữ thứ tự đó, dù việc tính toán có thể diễn ra song song. `Stream.toList()` có từ Java 16 và trả về danh sách **không cho phép sửa cấu trúc**.

Bài học thuộc chương **Bài tập nâng cao và dự án** của module `JAVA_STREAM_API`. Trọng tâm không phải chỉ biết tên API, mà là **đọc pipeline lỗi, xác định trạng thái bị chia sẻ, lựa chọn phép toán thay thế, chứng minh tính đúng đắn và thiết kế kiểm thử có thể lặp lại**.

**Sau bài này, bạn có thể:**

1. Nhận diện data race, non-interference và stateful behavior trong pipeline song song.
2. Sửa cách thu thập `List`/`Set`, tính tổng/đếm, phân nhóm và loại trùng bằng các terminal operation phù hợp.
3. Phân biệt *thread-safe* với *đúng ngữ nghĩa nghiệp vụ*, nhất là khi liên quan đến encounter order.
4. Dùng `collect`, `reduce`, `groupingBy`, `toMap` hoặc `groupingByConcurrent` đúng hợp đồng.
5. Viết kiểm thử xác nhận kết quả, thay vì phụ thuộc số thread hoặc thứ tự thực thi tình cờ.

Ví dụ hoàn chỉnh trong bài dùng **Java 17+** (`record`, `List.of`, `Stream.toList()`). Những nguyên tắc về parallel Stream, stateless lambda và Collector có từ Java 8.

## 2. Mô hình thực thi: nguồn có thứ tự vẫn có thể chạy không theo thứ tự

`parallelStream()` diễn đạt ý định xử lý song song; Stream có thể **tách dữ liệu**, xử lý từng nhánh rồi kết hợp kết quả. Nó không cam kết số lượng thread, thứ tự chạy từng lambda hay việc mỗi phần tử sẽ được một thread riêng xử lý.

```text
                       List: [A, B, C, D]
                               |
                       parallelStream()
                         /           \
                    [A, B]           [C, D]
                      |                |
                  tác vụ 1         tác vụ 2
                      \                /
                       \              /
                         collect(...)
                               |
                       [A, B, C, D]
```

Sơ đồ trên chỉ là **một cách chia logic**. Thực tế framework có thể tách nhiều lần, và các nhánh có thể chạy theo lịch khác.

Điều cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Encounter order** | Thứ tự phần tử về mặt logic do nguồn và pipeline xác định. |
| **Execution order** | Thời điểm và thread thực thi từng callback. Không được dựa vào khi song song. |
| **Data race** | Nhiều thread truy cập cùng trạng thái mutable, có truy cập ghi, mà không có đồng bộ phù hợp. |
| **Non-interference** | Lambda không thay đổi nguồn dữ liệu đang được Stream duyệt. |
| **Stateless behavior** | Kết quả xử lý một phần tử không phụ thuộc trạng thái mutable thay đổi do xử lý phần tử khác. |
| **Mutable reduction** | `collect` tạo những vùng chứa kết quả riêng, tích lũy rồi kết hợp theo hợp đồng. |

Ví dụ nguồn ordered vẫn có kết quả có thứ tự:

```java
List<String> labels = List.of("A", "B", "C", "D");

List<String> mapped = labels.parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(mapped); // [a, b, c, d]
```

**Không kết luận** rằng `map("A")` chạy trước `map("B")`. Điều được bảo đảm ở đây là danh sách kết quả phản ánh encounter order khi terminal operation thu thập.

## 3. Quy trình chẩn đoán pipeline có trạng thái dùng chung

Khi gặp bug chỉ xuất hiện với `parallelStream()`, kiểm tra lần lượt:

1. **Nguồn:** Có `ArrayList`, `HashMap`, mảng hoặc đối tượng mutable nào đang bị sửa trong lúc Stream duyệt không?
2. **Lambda:** `filter`, `map`, `peek` hay `forEach` có ghi vào biến được khai báo bên ngoài, gọi `add`/`put`/`increment` hoặc sửa trường đối tượng nguồn không?
3. **Kiểu kết quả mong muốn:** Cần List, Set, Map, số đếm, tổng, cực trị hay một hành động độc lập? Có terminal operation chuẩn thay thế tác dụng phụ không?
4. **Thứ tự:** Cần phần tử đầu tiên theo nguồn, thứ tự hiển thị hay chỉ cần tập kết quả không thứ tự?
5. **Khả năng kết hợp:** Nếu dùng `reduce`/`collect` tùy chỉnh, phép kết hợp có identity và tính kết hợp phù hợp không?
6. **Kiểm thử:** Có assert kết quả đúng **bất kể lịch thread** không, hay chỉ in log và nhìn một lần?

Một cách nhận diện nhanh là tìm các biến mutable **nằm ngoài** pipeline và được dùng bên trong:

```java
List<String> output = new ArrayList<>();
int[] total = {0};
Map<String, Integer> counts = new HashMap<>();

// Khi các biến trên được sửa trong lambda của parallel Stream,
// chúng là những vị trí cần rà soát đầu tiên.
```

Không phải mọi biến được lambda capture đều sai. Một đối tượng cấu hình **bất biến** được đọc chung là bình thường; nguy cơ nằm ở việc đọc/ghi trạng thái mutable phụ thuộc các phần tử hoặc sửa nguồn không đúng hợp đồng.

## 4. Lỗi số 1: dùng forEach để thêm vào ArrayList chia sẻ

### Pipeline sai

```java
List<String> ids = List.of("T01", "T02", "T03", "T04");
List<String> collected = new ArrayList<>();

ids.parallelStream()
        .map(String::toLowerCase)
        .forEach(collected::add); // SAI
```

Ở đây, nhiều lời gọi `ArrayList.add` có thể chồng chéo. Ngoài khả năng mất phần tử, `forEach` còn **không cam kết thứ tự hành động** với parallel Stream: ngay cả khi thay bằng Collection thread-safe, thứ tự các phần tử được thêm cũng có thể không phải `T01, T02, T03, T04`.

### Sửa tốt nhất khi cần một List kết quả

```java
List<String> safeList = ids.parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(safeList); // [t01, t02, t03, t04]
```

Nếu cần danh sách **chỉnh sửa được sau khi thu thập**, chỉ định container bằng collector:

```java
List<String> editableList = ids.parallelStream()
        .map(String::toLowerCase)
        .collect(Collectors.toCollection(ArrayList::new));

editableList.add("t05"); // Hợp lệ.
```

`Collectors.toList()` cũng thường dùng để thu thập, nhưng API không cam kết kiểu List cụ thể hoặc khả năng chỉnh sửa. `toCollection(ArrayList::new)` thể hiện rõ yêu cầu cần `ArrayList`.

### Nếu muốn tự viết collect ba tham số

```java
List<String> safeByThreeArgs = ids.parallelStream()
        .map(String::toLowerCase)
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(safeByThreeArgs);
// [t01, t02, t03, t04]
```

Mỗi lời gọi `supplier` tạo vùng chứa **độc lập**. `accumulator` thêm phần tử vào vùng chứa của nhánh; `combiner` gộp các vùng chứa với nhau theo hợp đồng. Vì vậy, việc `ArrayList` không thread-safe **không làm phép collect trên sai**: framework không cần gọi đồng thời accumulator trên cùng vùng chứa không-concurrent.

**Sai khi đưa lại cùng một List dùng chung vào supplier:**

```java
List<String> shared = new ArrayList<>();

List<String> broken = ids.parallelStream()
        .collect(
                () -> shared,    // SAI: không tạo container mới.
                List::add,
                List::addAll
        );
```

Supplier có thể được gọi nhiều lần. Nếu luôn trả về `shared`, các nhánh cùng ghi vào một List và combiner có thể còn gộp container với chính nó, khiến dữ liệu sai nghiêm trọng.

## 5. Lỗi số 2: cộng số bằng biến int hoặc mảng bên ngoài

### Pipeline sai

```java
int[] total = {0};

IntStream.rangeClosed(1, 1_000)
        .parallel()
        .forEach(n -> total[0] += n); // SAI: read-modify-write không nguyên tử.

System.out.println(total[0]);
// Không có bảo đảm bằng 500500.
```

Phép `total[0] += n` bao gồm đọc giá trị cũ, cộng và ghi lại. Hai thread có thể đọc cùng một giá trị rồi ghi đè kết quả của nhau (**lost update**).

### Cách sửa khi chỉ cần tổng

```java
long expected = IntStream.rangeClosed(1, 1_000)
        .parallel()
        .asLongStream()
        .sum();

System.out.println(expected); // 500500
```

Sử dụng `mapToLong`/`asLongStream` và `sum` giúp diễn đạt phép tính trực tiếp; không cần biến đếm hoặc lock. `long` giúp mở rộng phạm vi so với `int`, nhưng vẫn có thể tràn nếu tổng vượt phạm vi `long`.

Với tổng số tiền dạng thập phân, có thể dùng đối tượng giá trị bất biến `BigDecimal`:

```java
List<java.math.BigDecimal> amounts = List.of(
        new java.math.BigDecimal("12.50"),
        new java.math.BigDecimal("7.25")
);

java.math.BigDecimal amountTotal = amounts.parallelStream()
        .reduce(java.math.BigDecimal.ZERO, java.math.BigDecimal::add);

System.out.println(amountTotal); // 19.75
```

`BigDecimal.add` không sửa toán hạng và bảo đảm phép cộng chính xác theo các giá trị đầu vào ở ví dụ không dùng `MathContext`. Với phép reduction, cần một identity đúng và phép kết hợp phù hợp để kết quả không phụ thuộc cách chia nguồn.

### AtomicInteger có giải quyết tất cả không?

`AtomicInteger.addAndGet` bảo đảm cập nhật nguyên tử, vì vậy có thể ngăn lost update của một biến đếm. Nhưng điều đó **không** làm `filter` dựa vào biến đếm trở thành một phép lọc xác định, cũng không thay thế được nhu cầu bảo toàn thứ tự.

```java
AtomicInteger sequence = new AtomicInteger();

List<Integer> unstable = IntStream.rangeClosed(1, 10)
        .parallel()
        .filter(n -> sequence.incrementAndGet() <= 3)
        .boxed()
        .toList();

// Không bảo đảm unstable == [1, 2, 3].
```

Ở đây biến đếm an toàn ở mức nguyên tử nhưng **phần tử nào được xét trước** phụ thuộc lịch thực thi. Nếu yêu cầu lấy ba phần tử đầu tiên từ nguồn ordered, dùng:

```java
List<Integer> firstThree = IntStream.rangeClosed(1, 10)
        .parallel()
        .limit(3)
        .boxed()
        .toList();

System.out.println(firstThree); // [1, 2, 3]
```

`limit` trên ordered parallel Stream có thể tốn chi phí phối hợp, nhưng đúng với yêu cầu. Không đổi tính đúng đắn lấy tốc độ bằng một biến đếm dùng chung.

## 6. Lỗi số 3: đếm theo khóa bằng HashMap mutable

### Pipeline sai

```java
List<String> teams = List.of("A", "B", "A", "C", "B", "A");
Map<String, Integer> sharedCounts = new HashMap<>();

teams.parallelStream()
        .forEach(team -> sharedCounts.merge(team, 1, Integer::sum));
        // SAI: HashMap không an toàn khi nhiều thread cùng cập nhật.
```

`HashMap.merge` không biến `HashMap` thành concurrent Map. Các nhánh có thể làm mất lần cập nhật hoặc gây hành vi không đáng tin cậy.

### Sửa bằng groupingBy + counting

```java
Map<String, Long> counts = teams.parallelStream()
        .collect(Collectors.groupingBy(
                java.util.function.Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("A")); // 3
System.out.println(counts.get("B")); // 2
System.out.println(counts.get("C")); // 1
```

Collector tổ chức các phép tích lũy và kết hợp đúng với nguồn song song. `groupingBy` không cần trả về `ConcurrentMap` để có kết quả đúng. Với nguồn lớn và yêu cầu không quan tâm thứ tự, có thể cân nhắc `groupingByConcurrent`:

```java
ConcurrentMap<String, Long> concurrentCounts = teams.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                java.util.function.Function.identity(),
                Collectors.counting()
        ));

System.out.println(concurrentCounts.get("A")); // 3
```

`groupingByConcurrent` là collector **concurrent, unordered**. Nó thích hợp khi không cần encounter order của giá trị trong từng nhóm; hiệu năng thực tế vẫn phụ thuộc độ phân tán khóa, kích thước nguồn và chi phí contention.

### Sửa bằng toMap với hàm merge

```java
Map<String, Integer> countsWithMerge = teams.parallelStream()
        .collect(Collectors.toMap(
                java.util.function.Function.identity(),
                team -> 1,
                Integer::sum
        ));

System.out.println(countsWithMerge.get("A")); // 3
```

Hàm merge `Integer::sum` làm rõ cách kết hợp giá trị cho các khóa trùng nhau. Nếu dùng `Collectors.toMap` hai tham số mà có khóa trùng, collector sẽ ném `IllegalStateException`; đừng bỏ qua quyết định nghiệp vụ về dữ liệu trùng.

**Lưu ý:** `Map` kết quả từ các collector trên không mặc nhiên có thứ tự khóa xác định. Kiểm tra từng entry bằng `get` hoặc so sánh Map theo nội dung, không dựa vào chuỗi in ra của `HashMap`.

## 7. Lỗi số 4: loại trùng bằng HashSet chia sẻ trong filter

### Pipeline sai

```java
Set<String> seen = new HashSet<>();

List<String> unique = List.of("A", "B", "A", "C", "B")
        .parallelStream()
        .filter(seen::add) // SAI: stateful predicate và HashSet không thread-safe.
        .toList();
```

`filter(seen::add)` đọc và thay đổi trạng thái mutable bên ngoài. Ngoài nguy cơ data race, ngay cả khi thay bằng concurrent Set, điều kiện **giữ bản nào đầu tiên** cũng có thể không tương thích với lịch xử lý song song.

### Sửa bằng distinct

```java
List<String> uniqueOrdered = List.of("A", "B", "A", "C", "B")
        .parallelStream()
        .distinct()
        .toList();

System.out.println(uniqueOrdered); // [A, B, C]
```

Trên Stream có encounter order, `distinct` giữ **lần xuất hiện đầu tiên** của mỗi giá trị bằng nhau, và `toList` giữ thứ tự đó. Nếu nguồn unordered, không được kỳ vọng thứ tự hoặc một representative cụ thể khi các đối tượng khác tham chiếu nhưng `equals` xem là bằng nhau.

`distinct` là một thao tác trung gian **stateful** do thư viện quản lý, khác với việc lambda tự thao tác lên một `HashSet` dùng chung. Việc giữ encounter order trong parallel `distinct` có thể tốn bộ nhớ và chi phí phối hợp.

### Trùng theo khóa nghiệp vụ, không phải equals toàn đối tượng

`distinct` dùng `equals`/`hashCode` của phần tử. Nếu yêu cầu giữ một đơn hàng theo `id` nhưng đối tượng còn nhiều trường, không được coi `distinct()` trên toàn `Order` là tương đương loại trùng theo `id`.

```java
record Product(String sku, int version, String name) {}

List<Product> products = List.of(
        new Product("P01", 1, "Bút cũ"),
        new Product("P01", 2, "Bút mới"),
        new Product("P02", 1, "Vở")
);

Map<String, Product> latest = products.parallelStream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(
                        Comparator.comparingInt(Product::version)
                                .thenComparing(Product::name)
                )
        ));

System.out.println(latest.get("P01").version()); // 2
```

Hàm merge lựa chọn bản có version cao hơn, và dùng `name` để xử lý trường hợp bằng version. Quy tắc phải có **tie-break xác định** nếu dữ liệu có thể trùng cả các tiêu chí mà vẫn khác nhau về nội dung cần giữ. Nếu muốn giữ lần xuất hiện đầu tiên theo List, cần chọn một chiến lược có hợp đồng encounter order phù hợp thay vì suy luận từ thứ tự cập nhật Map trong parallel.

## 8. Lỗi số 5: sửa chính nguồn trong khi Stream đang duyệt

### Pipeline sai

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.parallelStream()
        .filter(n -> {
            if (n == 2) {
                source.add(99); // SAI: sửa collection nguồn.
            }
            return n > 0;
        })
        .toList();
```

Đây là vi phạm **non-interference**, không chỉ là vấn đề `ArrayList` thiếu thread-safety. Có thể gặp `ConcurrentModificationException`, dữ liệu khó dự đoán hoặc mất tính nhất quán.

### Sửa bằng pipeline chỉ đọc nguồn

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> selected = source.parallelStream()
        .filter(n -> n > 0)
        .toList();

List<Integer> updated = new ArrayList<>(source);
updated.add(99);

System.out.println(selected); // [1, 2, 3, 4]
System.out.println(updated);  // [1, 2, 3, 4, 99]
```

Trong phương án này, việc tạo dữ liệu kết quả và cập nhật cấu trúc là **hai giai đoạn tách biệt**. Nếu một thread khác vẫn đang sửa nguồn, chỉ tách hai giai đoạn trong cùng thread chưa đủ: ứng dụng phải có snapshot nhất quán hoặc cơ chế đồng bộ/sở hữu nguồn thích hợp.

`List.copyOf(source)` có thể tạo danh sách không sửa được để đọc ổn định hơn nếu nguồn được chụp ở thời điểm không có sửa đồng thời và không chứa `null`. Đây là **bản sao nông**, nên các đối tượng phần tử mutable vẫn có thể thay đổi từ nơi khác. Không coi `List.copyOf` tự giải quyết mọi race trong một hệ thống đang cập nhật dữ liệu.

## 9. Lỗi số 6: reduce với identity mutable

`reduce` phù hợp với phép kết hợp các **giá trị**, không phải công cụ để cập nhật một accumulator mutable được chia sẻ.

### Pipeline sai

```java
List<String> source = List.of("A", "B", "C");

List<String> incorrect = source.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item); // SAI: thay đổi identity mutable.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

`reduce` yêu cầu identity, accumulator và combiner tương thích theo hợp đồng reduction. Sửa trực tiếp identity mutable có thể làm nhiều nhánh dùng chung trạng thái và phá kết quả, đặc biệt khi song song.

### Sửa bằng collect

```java
List<String> correct = source.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );

System.out.println(correct); // [A, B, C]
```

`collect` ba tham số là **mutable reduction đúng mục đích**: supplier tạo container mới cho từng phần tích lũy, accumulator thay đổi container ấy, combiner gộp các phần theo một phép phù hợp.

Nếu chỉ muốn nối chuỗi, thay vì tự tích lũy `StringBuilder` qua `reduce`, dùng collector đã có:

```java
String joined = source.parallelStream()
        .collect(Collectors.joining(","));

System.out.println(joined); // A,B,C
```

Trên Stream có thứ tự, `joining` bảo toàn encounter order. Trên nguồn unordered, không suy đoán thứ tự ghép.

## 10. Thread-safe container có phải là cách sửa luôn đúng?

Không. **Thread-safe** chỉ giải quyết một số vấn đề truy cập đồng thời; nó **không tự bảo đảm thứ tự hoặc chính sách nghiệp vụ**.

| Cách làm | Tránh được vấn đề nào? | Còn giới hạn gì? |
| --- | --- | --- |
| `Collections.synchronizedList(...)` | Đồng bộ các thao tác đơn lẻ trên List | Thứ tự `add` phụ thuộc lịch thread, không nhất thiết là encounter order |
| `ConcurrentLinkedQueue` | Hỗ trợ thêm/lấy phần tử đồng thời | Thứ tự tác vụ đưa phần tử vào không nhất thiết trùng thứ tự nguồn |
| `ConcurrentHashMap` | Các thao tác Map concurrent theo hợp đồng | Hàm cập nhật và phép kết hợp phải đúng ngữ nghĩa; không có thứ tự khóa |
| `AtomicInteger` / `LongAdder` | Cập nhật số đếm đồng thời | Không làm predicate phụ thuộc state trở thành xác định |
| `forEachOrdered` | Thực hiện terminal action theo encounter order nếu nguồn ordered | Có thể giảm song song; không thay thế phép collect hay bảo vệ trước những thread ngoài pipeline |
| `collect`/`reduce` chuẩn | Phân phối và kết hợp kết quả theo hợp đồng | Vẫn cần chọn phép tích lũy, kiểu kết quả và thứ tự phù hợp |

Ví dụ thực sự cần hành động concurrent độc lập:

```java
java.util.concurrent.ConcurrentLinkedQueue<String> queue =
        new java.util.concurrent.ConcurrentLinkedQueue<>();

List.of("A", "B", "C").parallelStream()
        .forEach(queue::add);

System.out.println(queue.size()); // 3
// Không cam kết iterator của queue sẽ trả A, B, C theo thứ tự nguồn.
```

Đây là thao tác `add` thread-safe; tuy nhiên, khi mục tiêu chỉ là **thu thập danh sách**, `toList()` hoặc `collect` vẫn diễn đạt yêu cầu rõ ràng hơn. Chỉ dùng queue/concurrent Map và tác dụng phụ khi có nhu cầu cụ thể về một nơi nhận dữ liệu đồng thời.

### forEachOrdered không sửa được tất cả

```java
List<String> printed = new ArrayList<>();

List.of("A", "B", "C").parallelStream()
        .forEachOrdered(printed::add);

System.out.println(printed); // [A, B, C]
```

Trong **một lời gọi `forEachOrdered`** trên nguồn ordered, các action được thực hiện theo encounter order và action trước *happens-before* action sau. Nhưng `map`/`filter` phía trước vẫn có thể thực thi song song; danh sách `printed` cũng không được bảo vệ trước một thread **khác** sửa đồng thời.

Vì vậy, dù ví dụ này cho kết quả đúng trong phạm vi đã nêu, **khuyến nghị thu thập bằng `toList`** khi đầu ra cần là List. `forEachOrdered` hữu ích hơn khi hành động cuối thật sự phải xảy ra theo thứ tự như ghi một chuỗi dòng ra một kênh.

## 11. Collector concurrent và cách chọn đúng mục tiêu

Một số collector có thể tích lũy đồng thời, nhưng có khác biệt giữa:

- **Nguồn chạy song song:** `parallelStream()`.
- **Collector có khả năng concurrent:** ví dụ `groupingByConcurrent` hoặc `toConcurrentMap`.
- **Kết quả cuối là ConcurrentMap:** khác với việc mọi Map được trả từ một parallel Stream đều là concurrent.

Ví dụ gộp tổng theo khóa với Map concurrent:

```java
record Event(String team, long points) {}

List<Event> events = List.of(
        new Event("A", 2),
        new Event("B", 3),
        new Event("A", 5)
);

ConcurrentMap<String, Long> totals = events.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Event::team,
                Event::points,
                Long::sum
        ));

System.out.println(totals.get("A")); // 7
System.out.println(totals.get("B")); // 3
```

Hàm merge `Long::sum` cho kết quả không phụ thuộc cách chia và thứ tự kết hợp **trong phạm vi số không tràn**. Ngược lại, những phép kết hợp như "lấy chuỗi của lần cập nhật cuối trên thread" phụ thuộc lịch chạy và không phải một quy tắc nghiệp vụ ổn định.

Với dữ liệu có encounter order nhưng yêu cầu **giữ lần xuất hiện đầu tiên**, việc chọn `toConcurrentMap` có thể không phù hợp nếu merge function dựa vào "đến trước" của các thread. Hãy nêu rõ tiêu chí so sánh của các bản ghi (timestamp, version, thứ tự nghiệp vụ) rồi dùng phép chọn có tính kết hợp và tie-break xác định, hoặc thực hiện xử lý ordered thích hợp.

## 12. Mọi side effect trong map hoặc peek đều đáng rà soát

Không chỉ `forEach` có thể làm dữ liệu không an toàn:

```java
AtomicInteger calls = new AtomicInteger();

long n = List.of(1, 2, 3, 4)
        .parallelStream()
        .peek(x -> calls.incrementAndGet())
        .count();

// Không được dùng calls.get() làm số đếm nghiệp vụ.
System.out.println(n); // 4
```

Một số terminal operation có thể tận dụng thông tin kích thước nguồn để trả kết quả mà **không phải thực thi các thao tác trung gian chỉ có tác dụng phụ**, khi điều đó không làm thay đổi giá trị kết quả. `peek` thích hợp để debug hạn chế, không phải đảm bảo việc gửi thông báo hoặc cập nhật dữ liệu một lần cho mọi phần tử.

Nếu cần số đếm, lấy từ `count`. Nếu cần tạo giá trị mới, dùng `map` thuần. Nếu cần thực hiện I/O cho tất cả phần tử, hãy thiết kế hành động, tính idempotent, xử lý lỗi và concurrency theo yêu cầu của hệ thống, không giả định rằng thay bằng `parallelStream` tự xử lý được tất cả.

## 13. Ví dụ hoàn chỉnh: sửa báo cáo đơn hàng chạy song song

Bài toán: danh sách đơn bán hàng có mã, phòng phụ trách, số lượng và trạng thái hợp lệ. Cần tạo:

1. Danh sách **ID của đơn hợp lệ** theo thứ tự nguồn.
2. Tổng số lượng theo phòng.
3. Tổng số lượng của tất cả đơn hợp lệ.
4. Số đơn hợp lệ.
5. Danh sách ID theo từng phòng và kết quả concurrent tương đương về tổng.

### Mẫu lỗi cần tránh

```java
List<String> ids = new ArrayList<>();
Map<String, Long> byTeam = new HashMap<>();
long[] sum = {0L};

orders.parallelStream()
        .filter(Order::valid)
        .forEach(order -> {
            ids.add(order.id());                           // SAI
            byTeam.merge(order.team(), order.units(), Long::sum); // SAI
            sum[0] += order.units();                       // SAI
        });
```

Ba vùng chứa mutable `ids`, `byTeam`, `sum` đều bị cập nhật từ nhiều nhánh mà không có một phép giảm/thu thập đúng hợp đồng. Đổi sang `synchronizedList` **không sửa** hai biến còn lại và cũng không đảm bảo thứ tự của `ids`.

### Chương trình Java 17+ đã sửa

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ParallelStateRepairDemo {
    record Order(
            String id,
            String team,
            long units,
            boolean valid
    ) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("S01", "A", 3, true),
                new Order("S02", "B", 5, true),
                new Order("S03", "A", 100, false),
                new Order("S04", "A", 2, true),
                new Order("S05", "B", 4, true)
        );

        List<String> validIds = orders.parallelStream()
                .filter(Order::valid)
                .map(Order::id)
                .toList();

        Map<String, Long> totalsByTeam = orders.parallelStream()
                .filter(Order::valid)
                .collect(Collectors.groupingBy(
                        Order::team,
                        Collectors.summingLong(Order::units)
                ));

        long totalUnits = orders.parallelStream()
                .filter(Order::valid)
                .mapToLong(Order::units)
                .sum();

        long validCount = orders.parallelStream()
                .filter(Order::valid)
                .count();

        Map<String, List<String>> idsByTeam = orders.parallelStream()
                .filter(Order::valid)
                .collect(Collectors.groupingBy(
                        Order::team,
                        Collectors.mapping(
                                Order::id,
                                Collectors.toList()
                        )
                ));

        ConcurrentMap<String, Long> concurrentTotals = orders.parallelStream()
                .filter(Order::valid)
                .collect(Collectors.groupingByConcurrent(
                        Order::team,
                        Collectors.summingLong(Order::units)
                ));

        // Kiểm tra điều kiện đúng theo dữ liệu, không theo lịch chạy.
        List<String> expectedIds = List.of("S01", "S02", "S04", "S05");
        Map<String, Long> expectedTotals = Map.of("A", 5L, "B", 9L);

        if (!validIds.equals(expectedIds)) {
            throw new AssertionError("Sai thứ tự hoặc nội dung validIds");
        }
        if (!totalsByTeam.equals(expectedTotals)) {
            throw new AssertionError("Sai tổng theo team");
        }
        if (totalUnits != 14L || validCount != 4L) {
            throw new AssertionError("Sai tổng hoặc số đơn");
        }
        if (!idsByTeam.get("A").equals(List.of("S01", "S04"))
                || !idsByTeam.get("B").equals(List.of("S02", "S05"))) {
            throw new AssertionError("Sai danh sách ID theo team");
        }
        if (!concurrentTotals.equals(expectedTotals)) {
            throw new AssertionError("Sai concurrentTotals");
        }

        System.out.println("IDs: " + validIds);
        // IDs: [S01, S02, S04, S05]
        System.out.println("Team A: " + totalsByTeam.get("A")); // 5
        System.out.println("Team B: " + totalsByTeam.get("B")); // 9
        System.out.println("Total: " + totalUnits);           // 14
        System.out.println("Count: " + validCount);           // 4
        System.out.println("PASS");
    }
}
```

### Tại sao cách sửa đúng?

1. `Order` là `record` chỉ chứa `String`, số nguyên thủy và `boolean`; dữ liệu đầu vào trong ví dụ không bị sửa khi duyệt.
2. `filter(Order::valid)` và `map(Order::id)` không dùng trạng thái mutable bên ngoài.
3. `toList` trả danh sách ID giữ encounter order của nguồn `List`.
4. `groupingBy(..., summingLong(...))` tích lũy tổng theo từng khóa; không yêu cầu HashMap tự cập nhật song song từ `forEach`.
5. `mapToLong(...).sum()` và `count()` diễn đạt trực tiếp phép tổng và đếm.
6. `groupingBy(..., mapping(..., toList()))` thu thập danh sách ID theo từng nhóm, giữ thứ tự tương đối của các phần tử trong nhóm từ nguồn ordered.
7. `groupingByConcurrent` tạo `ConcurrentMap` tổng theo team; vì chỉ có phép cộng số nguyên, nội dung tổng hợp là tiêu chí so sánh hợp lý. Không dựa vào thứ tự lặp các khóa Map.
8. Mỗi phép thống kê dựng một Stream **mới từ `orders`**. Stream đã bị terminal operation tiêu thụ không được chạy lại.

Ví dụ ưu tiên **tính đúng đắn và rõ ràng**; với tập dữ liệu rất lớn, nếu cần nhiều KPI trong cùng một lượt duyệt, có thể thiết kế một collector tổng hợp có hợp đồng kết hợp phù hợp. Không tự chuyển sang cấu trúc dùng chung chỉ để tránh duyệt nguồn nhiều lần.

## 14. Kiểm thử pipeline song song cho đúng trọng tâm

Để kiểm thử một pipeline đã sửa, nên chia thành nhiều nhóm:

| Nhóm kiểm thử | Điều cần xác minh |
| --- | --- |
| **Đúng nội dung** | Mọi phần tử phù hợp đều xuất hiện đúng số lần; tổng và số đếm chính xác. |
| **Đúng thứ tự** | Nếu nghiệp vụ yêu cầu, kết quả ordered trùng encounter order, không phụ thuộc lịch chạy. |
| **Nguồn rỗng** | `count() == 0`, `sum() == 0`, `toList()` rỗng, `groupingBy` trả Map rỗng. |
| **Trùng khóa** | Merge hoặc downstream collector xử lý nhiều bản ghi cùng khóa theo đúng quy tắc. |
| **Dữ liệu thiếu** | Chính sách về `null`, khóa null, giá trị không hợp lệ được định nghĩa rõ. |
| **Tuần tự và song song** | So sánh kết quả bằng nhau về **ngữ nghĩa**, không so chuỗi in Map unordered. |
| **Dữ liệu lớn** | Chạy stress test để tăng khả năng phát hiện lỗi, nhưng không dùng một lần chạy thành công làm bằng chứng tuyệt đối. |
| **Hiệu năng** | Chạy benchmark đủ warm-up, tải thực tế, đo thời gian/bộ nhớ và so sánh với tuần tự. |

Ví dụ kiểm tra hai cách thực thi từ một nguồn ổn định:

```java
List<Integer> source = IntStream.range(0, 100_000)
        .boxed()
        .toList();

List<Integer> sequential = source.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toList();

List<Integer> parallel = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toList();

System.out.println(sequential.equals(parallel)); // true
```

Nếu biến đổi có tính **không kết hợp** hoặc phụ thuộc thứ tự (ví dụ trừ dồn hoặc phép cộng dấu phẩy động với sai số), cần thêm kiểm tra cho chính sách nghiệp vụ. Trong parallel Stream, phép reduction phải có identity và combiner phù hợp; đối với `double`, thứ tự cộng có thể ảnh hưởng chữ số cuối. Đừng chỉ kiểm tra "không ném ngoại lệ".

## 15. Bài tập nâng cao: tự sửa ba pipeline lỗi

### Bài 1 — Danh sách đơn hợp lệ

Cho:

```java
record Item(String id, boolean active) {}

List<Item> items = List.of(
        new Item("I01", true),
        new Item("I02", false),
        new Item("I03", true),
        new Item("I04", true)
);
```

Đoạn mã cần sửa:

```java
List<String> sharedIds = new ArrayList<>();
items.parallelStream()
        .filter(Item::active)
        .forEach(item -> sharedIds.add(item.id()));
```

**Yêu cầu:** sửa để kết quả đúng `[I01, I03, I04]` theo thứ tự nguồn, không dùng lock hay mutable List capture bên ngoài.

**Lời giải:**

```java
List<String> safeIds = items.parallelStream()
        .filter(Item::active)
        .map(Item::id)
        .toList();

System.out.println(safeIds); // [I01, I03, I04]
```

### Bài 2 — Đếm theo trạng thái

Cho:

```java
record Job(String state, int points) {}

List<Job> jobs = List.of(
        new Job("OPEN", 2),
        new Job("CLOSED", 1),
        new Job("OPEN", 3),
        new Job("OPEN", 5)
);
```

Đoạn mã cần sửa:

```java
Map<String, Integer> counts = new HashMap<>();
jobs.parallelStream().forEach(job ->
        counts.merge(job.state(), 1, Integer::sum));
```

**Yêu cầu:** dùng collector để thu được `OPEN=3` và `CLOSED=1`, không dựa vào thứ tự key của Map.

**Lời giải:**

```java
Map<String, Long> safeCounts = jobs.parallelStream()
        .collect(Collectors.groupingBy(
                Job::state,
                Collectors.counting()
        ));

System.out.println(safeCounts.get("OPEN"));   // 3
System.out.println(safeCounts.get("CLOSED")); // 1
```

### Bài 3 — Tổng điểm và chọn bản ghi theo ID

Một developer viết:

```java
long[] sum = {0};
jobs.parallelStream().forEach(job -> sum[0] += job.points());
```

**Yêu cầu:** sửa bằng phép reduction nguyên thủy, đồng thời giải thích vì sao `AtomicLong` tuy giúp cập nhật nguyên tử nhưng chưa phải cách diễn đạt tốt nhất cho phép tính tổng.

**Lời giải:**

```java
long safeSum = jobs.parallelStream()
        .mapToLong(Job::points)
        .sum();

System.out.println(safeSum); // 11
```

`AtomicLong.addAndGet` có thể tránh mất cập nhật, nhưng buộc các tác vụ truy cập một biến dùng chung, làm tăng sự phối hợp và khiến pipeline kém khai báo. `mapToLong(...).sum()` dùng phép tổng hợp chuẩn, không cần bên ngoài giữ trạng thái.

**Mở rộng:** Nếu muốn lấy một `Job` đại diện cho từng trạng thái, cần chỉ rõ tiêu chí chọn: điểm lớn nhất, thời gian mới nhất, hay thứ tự nguồn. Khi dùng `toMap` trên parallel Stream, phải cung cấp merge function có quy tắc kết hợp phù hợp, thay vì chọn đại "bản nào đến trước" theo lịch thread.

## 16. Bài tập tự kiểm tra: tình huống nào vẫn sai dù đã đồng bộ?

Xét:

```java
List<Integer> synchronizedOutput =
        java.util.Collections.synchronizedList(new ArrayList<>());

IntStream.range(1, 6)
        .parallel()
        .forEach(synchronizedOutput::add);

System.out.println(synchronizedOutput);
```

Lệnh thêm phần tử được đồng bộ, nhưng **thứ tự thêm không được bảo đảm** là `[1, 2, 3, 4, 5]`. Nếu yêu cầu chỉ cần một danh sách chứa đủ năm số bất kể thứ tự, code có thể chấp nhận được về an toàn khi nhiều tác vụ thêm riêng lẻ. Nếu yêu cầu List theo thứ tự nguồn, dùng `IntStream.range(1, 6).parallel().boxed().toList()`.

Một tình huống khác:

```java
AtomicInteger seenCount = new AtomicInteger();

List<String> firstTwo = List.of("A", "B", "C", "D")
        .parallelStream()
        .filter(x -> seenCount.incrementAndGet() <= 2)
        .toList();
```

Mặc dù biến đếm atomic, `firstTwo` **không bảo đảm bằng `[A, B]`**. Nếu cần hai phần tử đầu theo List, dùng `limit(2)`; nếu cần hai phần tử có điều kiện sắp xếp riêng, định nghĩa tiêu chí rồi dùng thao tác phù hợp.

**Câu hỏi tự giải thích:** Tại sao `Collectors.groupingBy(..., toList())` vẫn có thể đúng trong parallel Stream dù các List tích lũy thông thường không thread-safe? Vì collector có quyền tạo **các vùng chứa riêng và gộp kết quả theo hợp đồng**, chứ không yêu cầu tất cả thread gọi `add` trên cùng một List do người dùng capture.

## 17. Checklist bàn giao pipeline song song đã sửa

1. **Không sửa nguồn:** không gọi `add`/`remove`/`put` lên collection đang được Stream duyệt.
2. **Lambda rõ trạng thái:** `filter`/`map` không dựa vào biến đếm hoặc List/Map mutable dùng chung.
3. **Đúng terminal operation:** List → `toList`/`collect`; tổng → `sum`/`reduce`; nhóm → `groupingBy`; tồn tại → `anyMatch`; loại trùng → `distinct`.
4. **Supplier độc lập:** với `collect` tùy chỉnh, mỗi lần supplier phải tạo vùng chứa mới; không trả về cùng object global.
5. **Combiner đúng luật:** không bỏ mất kết quả từng phần; giữ identity, associativity và khả năng tương thích accumulator.
6. **Thứ tự rõ ràng:** xác định encounter order, không dùng `forEach` để bảo đảm thứ tự hay suy ra thứ tự thread.
7. **Khóa Map hợp lệ:** chính sách trùng khóa và merge function đã xác định; khóa không bị sửa trong lúc nằm trong Map.
8. **Số học đúng phạm vi:** kiểm tra overflow và sai số làm tròn; không dùng kiểu số nhỏ hơn yêu cầu.
9. **Nguồn ổn định:** snapshot hoặc đồng bộ nguồn khi nhiều thành phần có thể cập nhật đồng thời; nhớ snapshot nông không khóa các đối tượng phần tử mutable.
10. **Kiểm thử kết quả:** assert tổng, số lượng, nội dung, thứ tự nếu cần; thử dữ liệu rỗng, dữ liệu lặp, nhiều khóa và nhiều kích thước.
11. **Đo hiệu năng:** so sánh `stream()` và `parallelStream()` trên tải thật; không giả định parallel luôn nhanh.
12. **Tài nguyên:** với Stream từ tệp/kết nối, đóng nguồn bằng `try-with-resources`; tránh biến song song thành công cụ tạo I/O blocking không giới hạn.

## Ghi nhớ

Lỗi trạng thái dùng chung trong parallel Stream thường bắt đầu từ những biểu thức có vẻ vô hại như `forEach(sharedList::add)`, `sharedCount++`, `filter(sharedSet::add)` hoặc `map` sửa chính nguồn. Khi chạy song song, chúng có thể gây data race, sai thứ tự, mất dữ liệu hoặc vi phạm hợp đồng **stateless** và **non-interfering**.

Hướng sửa ưu tiên là **chuyển tác dụng phụ thành kết quả**: dùng `toList`/`collect` cho Collection, `sum`/`count`/`reduce` cho số liệu, `groupingBy`/`toMap` cho nhóm và `distinct` cho loại trùng. Container thread-safe chỉ giải quyết một phần concurrency; nó không tự tạo encounter order hay một quy tắc nghiệp vụ ổn định. Hãy kiểm thử tính đúng đắn trước, sau đó mới đánh giá lợi ích của chạy song song.
