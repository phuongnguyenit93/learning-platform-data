# Stateless lambda và tránh shared mutable state trong Parallel Streams

## 1. Bài toán: cùng một phép biến đổi nhưng nhiều luồng thực thi

Một `Stream` trong Java mô tả pipeline xử lý dữ liệu gồm **source → intermediate operations → terminal operation**. Chuyển sang `parallelStream()` hoặc gọi `parallel()` cho phép Java Stream framework chia công việc thành nhiều phần và có thể chạy các phần trên những thread khác nhau. Cú pháp lambda thường giữ nguyên, nhưng **điều kiện để phép xử lý đúng dưới concurrency** trở nên rất quan trọng.

Ví dụ, nhân đôi mỗi số là phép biến đổi độc lập:

```java
List<Integer> doubled = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();
```

Đoạn code là *mảnh minh họa*: biến `numbers` cần được định nghĩa trong chương trình của bạn. Mỗi kết quả chỉ phụ thuộc phần tử `n`, không đọc/ghi biến có thể thay đổi bên ngoài và không sửa nguồn. Vì vậy lambda `n -> n * 2` là **stateless** (không phụ thuộc trạng thái biến đổi giữa những lần gọi).

Ngược lại:

```java
List<Integer> output = new ArrayList<>();
numbers.parallelStream().forEach(n -> output.add(n * 2));
```

Đây là **phản ví dụ nguy hiểm**, không phải mẫu dùng trong ứng dụng. `ArrayList` bị nhiều thread sửa đồng thời; `add()` không đồng bộ hóa, có thể làm mất phần tử, sai kích thước, làm hỏng cấu trúc hoặc dẫn tới exception. Không được coi kết quả “chạy thử có vẻ đúng” là bằng chứng an toàn.

Bài này tập trung vào **Java Stream API và concurrency thuần Java**. Không cần Spring, scheduler của framework hay annotation bất đồng bộ.

### Kết quả học tập

Sau bài này, bạn cần giải thích được:

1. Stateless lambda khác stateful lambda và side effect như thế nào.
2. Vì sao nhiều callback cùng truy cập shared mutable state gây race và làm kết quả không xác định.
3. Cách thay `forEach + add` bằng `map`, `filter`, `sum`, `reduce`, `collect` hoặc concurrent collector.
4. Vì sao `ArrayList` vẫn có thể xuất hiện bên trong `collect` an toàn, dù không phải collection thread-safe.
5. Những ràng buộc về encounter order, stateful stream operations, thread safety và hiệu năng khi chuyển sang parallel stream.

## 2. Stateless lambda: đặc tính của hành vi, không phải loại cú pháp

Một behavioral parameter như `Predicate<T>`, `Function<T,R>`, `Consumer<T>` hoặc `BinaryOperator<T>` được xem là **stateless** khi kết quả/hành vi của một lần gọi không phụ thuộc trạng thái có thể thay đổi bởi các lần gọi khác trong pipeline (hoặc bởi thread bên ngoài).

Ví dụ tốt:

```java
final int threshold = 10;

var values = List.of(4, 11, 16, 3);
var selected = values.parallelStream()
        .filter(n -> n > threshold)
        .map(n -> n * n)
        .toList();
```

`threshold` cố định trong lúc pipeline chạy; predicate và mapper không tích lũy trạng thái, không sửa dữ liệu đầu vào. Đây là **mảnh mã minh họa** tự đủ về biến, cần đặt trong một phương thức và import `List`. Với nguồn `List` có thứ tự, `toList()` giữ encounter order, nên `selected` tương ứng `[121, 256]`; việc callback có chạy theo thứ tự 11 rồi 16 hay không là vấn đề khác.

Ví dụ stateful:

```java
AtomicInteger sequence = new AtomicInteger();

List<String> labelled = items.parallelStream()
        .map(item -> sequence.getAndIncrement() + ":" + item)
        .toList();
```

Đây là **phản ví dụ về stateful lambda**, dù `AtomicInteger` làm tăng bộ đếm một cách atomic. Thứ tự cấp phát số phụ thuộc lịch chạy và có thể thay đổi giữa các lần thực thi; `labelled` vẫn được trả theo encounter order của `items`, nhưng số thứ tự gắn với từng phần tử có thể lộn xộn. Nếu cần chỉ số ổn định, hãy biểu diễn chỉ số bằng dữ liệu đầu vào, ví dụ dùng `IntStream.range(0, items.size())` để ánh xạ `i` với `items.get(i)` khi nguồn là danh sách không bị sửa và việc truy cập theo chỉ số phù hợp.

**Stateless không có nghĩa lambda không capture biến.** Capture một giá trị bất biến như `threshold` là bình thường. Capture tham chiếu đến một đối tượng mutable rồi đọc/ghi trạng thái liên tục có thể là stateful ngay cả khi biến tham chiếu là `final`.

```java
final List<Integer> sink = new ArrayList<>();
// 'sink' không được gán sang đối tượng khác, nhưng sink.add(...) vẫn sửa đối tượng.
```

Quy tắc Java bắt buộc local variable được lambda capture phải **final hoặc effectively final** chỉ ngăn gán lại biến cục bộ; nó **không tự biến đối tượng được tham chiếu thành immutable hay thread-safe**.

## 3. Shared mutable state và data race

**Shared mutable state** là trạng thái có thể thay đổi được chia sẻ giữa nhiều lần gọi callback hoặc nhiều thread, ví dụ một `ArrayList`, `HashMap`, `int[]`, bộ đếm, object chứa field có thể sửa, hoặc phần tử của source bị cập nhật.

Xét mã sau, với `numbers` là danh sách số nguyên:

```java
List<Integer> results = new ArrayList<>();

numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .forEach(results::add); // SAI nếu các thread cùng ghi ArrayList
```

Một `ArrayList` lưu các phần tử trong mảng nội bộ và duy trì `size`; những lần `add` đồng thời có thể cùng đọc và ghi vùng trạng thái đó. Không có quan hệ đồng bộ thích hợp, đây là **data race** theo mô hình bộ nhớ Java. Triệu chứng có thể thay đổi từ lần chạy này sang lần khác; không có con số thất thoát cố định để dùng làm output mẫu.

Hình dung hai lời gọi cùng thao tác với chỉ số `size`:

```text
Thread A: đọc size = 5  → ghi phần tử vào vị trí 5 → cập nhật size
Thread B: đọc size = 5  → ghi phần tử vào vị trí 5 → cập nhật size
                                      ↑
                              Có thể đè kết quả
```

Đây là sơ đồ mô hình hóa một khả năng interleaving, không phải trình tự nội bộ bắt buộc của mọi phiên bản `ArrayList`. Dùng collection không thread-safe để chia sẻ write giữa các callback khiến chương trình không có bảo đảm correctness.

Một `HashMap` cũng không trở nên thread-safe chỉ vì bạn gọi `parallelStream()`; thêm/sửa mục đồng thời phải có cơ chế đồng bộ hoặc collection concurrent phù hợp.

### Data race khác với kết quả sai do thứ tự không xác định

Ngay cả khi dùng `AtomicInteger` hoặc `Collections.synchronizedList(...)` để loại bỏ race đối với **một thao tác**, chương trình vẫn có thể có vấn đề:

- Số thứ tự/tính toán phụ thuộc ai chạy trước; đúng về atomicity nhưng không còn kết quả ổn định theo thứ tự logic.
- Nhiều thao tác riêng lẻ có thể đòi hỏi tính nguyên tử **cho cả chuỗi thao tác** (check-then-act); một lời gọi thread-safe không bảo đảm cả workflow là atomic.
- Mọi worker cùng tranh chấp một lock hoặc atomic counter làm giảm hiệu năng.
- Source vẫn có thể bị thay đổi đồng thời ngoài pipeline, làm vi phạm quy tắc non-interference.

Vì thế “dùng synchronized là xong” không phải phương án mặc định để viết pipeline.

## 4. Hai yêu cầu cốt lõi của Stream API: non-interference và statelessness

### Non-interference: đừng sửa nguồn khi stream đang xử lý

Trong phần lớn trường hợp, behavioral parameter không được thay đổi **nguồn dữ liệu không concurrent** đang được stream duyệt. Ví dụ sai:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));
source.parallelStream().forEach(source::remove);
```

Phản ví dụ này vi phạm non-interference: code sửa chính collection được stream dùng làm nguồn. Có thể gặp lỗi, bỏ sót phần tử hoặc hành vi không ổn định tùy tình huống. Nếu cần xóa phần tử, hãy làm ở một bước riêng sau khi pipeline kết thúc, hoặc tạo collection kết quả bằng `filter` rồi thay thế tham chiếu ở lớp quản lý dữ liệu.

Quy tắc có ngoại lệ khi nguồn được thiết kế cho modification đồng thời, ví dụ một số concurrent collection có spliterator `CONCURRENT`; nhưng loại nguồn đó có semantics duyệt riêng, không đồng nghĩa mọi sửa đổi đều tạo ảnh chụp nhất quán hoặc deterministic.

### Statelessness: cùng input không nên phụ thuộc lịch xử lý phần tử khác

Những phép `map`, `filter`, `flatMap` và predicate/mapping truyền vào chúng thường nên thuần theo từng phần tử. Một function stateless dễ kiểm thử trên từng đầu vào và dễ thực thi song song an toàn.

Ví dụ:

```java
int threshold = 100;
long count = orders.parallelStream()
        .filter(order -> order.total() >= threshold)
        .count();
```

Đây là **mảnh mã minh họa** với `orders` chứa loại phần tử có phương thức `total()`. Điều kiện là dữ liệu đơn hàng không bị sửa trong khi pipeline chạy. `count()` có thể thực hiện tối ưu hóa dựa trên đặc tính source và pipeline; đừng thêm side effect chỉ để “đếm số lần lambda được gọi” rồi kỳ vọng lần nào cũng bằng số phần tử.

## 5. Phân biệt stateful lambda với stateful intermediate operation

**Stateful lambda** phụ thuộc vào trạng thái mutable ở bên ngoài/các lần gọi khác. Nó làm các bước xử lý dễ phụ thuộc lịch chạy và khó đảm bảo tính đúng đắn.

**Stateful intermediate operation** là một thao tác chuẩn của Stream API có state nội bộ do thư viện quản lý, chẳng hạn `distinct()`, `sorted()`, `limit()`, `skip()`. Chúng **không bị cấm trong parallel stream**: implementation tự thực hiện đồng bộ/hợp nhất phù hợp với contract, dù có thể cần buffering, coordination hoặc giảm hiệu suất.

Ví dụ hợp lệ:

```java
List<Integer> unique = List.of(3, 1, 3, 2, 2)
        .parallelStream()
        .distinct()
        .sorted()
        .toList();
```

Kết quả là `[1, 2, 3]`. Đây là thao tác stateful do Stream API quản lý, khác với tự tạo `HashSet` dùng chung rồi gọi `forEach(set::add)` trong parallel pipeline.

**Đừng suy diễn** “parallel stream không được dùng `sorted` hay `distinct`”. Điều cần đo là chi phí thứ tự, buffering và nhu cầu kết quả, chứ không phải tự viết lại thuật toán stateful bằng side effect.

## 6. Cách đúng: biểu diễn phép xử lý bằng map/filter/reduction

Thay vì gom dữ liệu thủ công vào một collection chung, hãy để framework quản lý phân chia/hợp nhất:

| Mục tiêu | Phản ví dụ dùng side effect | Cách ưu tiên |
| --- | --- | --- |
| Tạo danh sách phần tử đã biến đổi | `forEach(result::add)` | `map(...).toList()` |
| Lọc phần tử | `forEach(n -> { if (...) result.add(n); })` | `filter(...).toList()` |
| Đếm phần tử thỏa điều kiện | `AtomicInteger.incrementAndGet()` | `filter(...).count()` |
| Cộng số | `AtomicLong.addAndGet()` | `mapToLong(...).sum()` |
| Lấy tổng hợp phần tử | Ghi vào biến chung trong `forEach` | `reduce` với phép kết hợp associative |
| Nhóm phần tử | `HashMap.computeIfAbsent(...).add(...)` dùng chung | `collect(groupingBy(...))` hoặc `groupingByConcurrent(...)` khi phù hợp |
| Tạo map có key trùng | `HashMap.put` không đồng bộ | `toMap(..., mergeFunction)` hoặc `toConcurrentMap(...)` |

**Terminal reduction** gồm `count()`, `sum()`, `min()`, `max()` và `reduce()`. Mỗi worker có thể tính phần của mình rồi framework ghép kết quả mà không yêu cầu application code duy trì một accumulator dùng chung.

### `reduce` cần identity và phép kết hợp đúng

```java
int total = numbers.parallelStream()
        .reduce(0, Integer::sum);
```

Đây là mảnh mã minh họa khi `numbers` chứa `Integer`. Với phép cộng số nguyên theo semantics Java, `0` là identity và phép cộng có tính kết hợp theo arithmetic modulo (2^{32}), dù tổng vượt ngưỡng có thể overflow. Khi nghiệp vụ không chấp nhận overflow, dùng `long`, `Math.addExact` hoặc `BigInteger` theo yêu cầu.

Trong parallel reduction, hàm kết hợp phải **associative**; nếu hoán vị nhóm thực thi mà kết quả thay đổi, chương trình có thể sai.

Phản ví dụ:

```java
int wrong = numbers.parallelStream().reduce(0, (a, b) -> a - b);
```

Phép trừ không associative: `(a-b)-c` khác `a-(b-c)`. Kết quả parallel có thể khác sequential. Đối với số thực dấu phẩy động, ngay cả phép cộng cũng không kết hợp hoàn toàn do làm tròn IEEE 754; chấp nhận sai khác số học và chọn thuật toán cộng ổn định khi cần độ chính xác cao.

### `reduce` không phải nơi sửa một container chia sẻ

Đừng cố dùng `reduce(new ArrayList<>(), ...)` rồi mutate danh sách identity/accumulator để bắt chước `collect`. Với phép `reduce`, accumulator phải phù hợp quy tắc non-interference, associativity và identity; mutating cùng identity object có thể dẫn tới cùng container bị dùng tại nhiều phân nhánh. **Mutable reduction** đã có API riêng là `collect`.

## 7. Ví dụ hoàn chỉnh 1: stateless lambda cho kết quả ổn định

Chạy với **Java 17+**. Lưu file `ParallelStreamStatelessDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelStreamStatelessDemo {
    public static void main(String[] args) {
        List<Integer> input = IntStream.rangeClosed(1, 12).boxed().toList();
        List<Integer> squares = input.parallelStream()
                .map(n -> n * n)
                .toList();
        int sumSquares = input.parallelStream()
                .mapToInt(n -> n * n)
                .sum();
        long evenCount = input.parallelStream()
                .filter(n -> n % 2 == 0)
                .count();

        System.out.println("size=" + squares.size());
        System.out.println("first=" + squares.get(0)
                + ", last=" + squares.get(squares.size() - 1));
        System.out.println("sumSquares=" + sumSquares);
        System.out.println("evenCount=" + evenCount);
    }
}
```

```bash
javac -encoding UTF-8 ParallelStreamStatelessDemo.java
java ParallelStreamStatelessDemo
```

```text
size=12
first=1, last=144
sumSquares=650
evenCount=6
```

Giải thích:

1. `IntStream.rangeClosed(1, 12)` tạo dữ liệu cố định; `toList()` tạo danh sách dùng làm source không bị mutate.
2. `map(n -> n * n)` chỉ dùng `n`. Framework có thể gọi mapper cho các phần tử trên nhiều thread; mapper không phải giữ tổng hoặc danh sách chung.
3. `Stream.toList()` giữ **encounter order** của ordered stream. Vì đầu vào là danh sách có thứ tự, `squares` có phần tử đầu bằng `1`, cuối bằng `144`, dù lịch xử lý nội bộ không có thứ tự xác định.
4. `mapToInt(...).sum()` ghép các phần tổng, cho `1² + 2² + ... + 12² = 650`; `filter(...).count()` cho `6` số chẵn.
5. `Stream.toList()` trả về danh sách **không cho phép sửa** trên Java 17+. Muốn một `ArrayList` riêng có thể mutate sau khi pipeline kết thúc, có thể tạo `new ArrayList<>(result)` ở bước sau.

Ở ví dụ này, lợi ích chính là **tính đúng và rõ ràng**. Với 12 phần tử và thao tác rất nhẹ, chạy song song thường không nhanh hơn chạy tuần tự; overhead chia việc có thể lớn hơn công việc thực tế.

## 8. Mutable reduction đúng cách: `collect` với container tạm độc lập

Một hiểu lầm phổ biến: “`ArrayList` không thread-safe, vì vậy `parallelStream().collect(...)` không thể dùng `ArrayList`”. Điều đó không đúng khi sử dụng collector/mutable reduction theo contract.

Với collector thông thường không có đặc tính `CONCURRENT`, Stream framework tạo ra **những accumulator độc lập** cho các nhánh, gọi accumulator trên mỗi container ở những nhánh thích hợp, rồi dùng combiner hợp nhất. Không có nghĩa tất cả worker cùng gọi `add` trên **một `ArrayList` chia sẻ**.

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 2)
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

Đây là **mảnh mã minh họa** cần import `List`, `ArrayList` và xác định `numbers`.

Ba hàm có vai trò rõ ràng:

- **Supplier `ArrayList::new`**: tạo container rỗng mới.
- **Accumulator `ArrayList::add`**: đưa phần tử vào container của nhánh hiện tại.
- **Combiner `ArrayList::addAll`**: ghép container kết quả từ hai nhánh.

Framework chịu trách nhiệm phối hợp các container. Đừng đưa **chính cùng một instance** dùng chung vào supplier:

```java
List<Integer> shared = new ArrayList<>();
// SAI: supplier trả về cùng một đối tượng cho mọi nhánh.
var bad = numbers.parallelStream()
        .collect(() -> shared, List::add, List::addAll);
```

Phản ví dụ này có thể gây race, gộp dữ liệu vào chính nó và sai semantics của phép collect. Supplier phải cung cấp container mới độc lập theo contract.

`Collectors.toList()` cũng là lựa chọn bình thường:

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 2)
        .collect(Collectors.toList());
```

`Collectors.toList()` **không bảo đảm** implementation type, mutability hay thread safety của collection được trả về; vì vậy không nên ép kiểu sang `ArrayList` hoặc mặc định collection sau đó có thể sửa. Nó vẫn được thiết kế để dùng an toàn trong quá trình parallel collect đúng contract. Nếu yêu cầu một loại collection cụ thể: `Collectors.toCollection(ArrayList::new)`.

## 9. Ví dụ hoàn chỉnh 2: gom nhóm đồng thời và gom vào accumulator cục bộ

Để đếm số từ xuất hiện, không nên dùng một `HashMap<String, Integer>` chung rồi `put`/tăng bộ đếm trong `forEach`. Java cung cấp concurrent collector cho trường hợp thích hợp.

Lưu file `ParallelCollectorDemo.java` (Java 17+):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelCollectorDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "java", "stream", "java", "parallel", "stream", "java");
        ConcurrentMap<String, Long> counts = words.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(), Collectors.counting()));

        System.out.println("java=" + counts.get("java"));
        System.out.println("stream=" + counts.get("stream"));
        System.out.println("parallel=" + counts.get("parallel"));

        List<Integer> doubled = IntStream.rangeClosed(1, 6)
                .boxed()
                .parallel()
                .map(n -> 2 * n)
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        System.out.println("doubled=" + doubled);
    }
}
```

```bash
javac -encoding UTF-8 ParallelCollectorDemo.java
java ParallelCollectorDemo
```

```text
java=3
stream=2
parallel=1
doubled=[2, 4, 6, 8, 10, 12]
```

Giải thích:

- `groupingByConcurrent` cho collector concurrent và unordered, cho phép phối hợp gom nhóm trong parallel pipeline. Kết quả là `ConcurrentMap`, hỗ trợ truy cập/concurrent update theo contract của implementation.
- `Collectors.counting()` được dùng làm downstream collector; thư viện chịu trách nhiệm phối hợp việc cập nhật giá trị cho từng key theo semantics collector, không yêu cầu bạn tự chia sẻ một `long[]` hoặc `HashMap` thường.
- Không in `counts` trực tiếp để dự đoán thứ tự key: map concurrent không cho thứ tự duyệt ổn định. In giá trị bằng những key cụ thể cho output deterministic.
- Trong phần `collect(ArrayList::new, ...)`, các `ArrayList` là những container tạm phục vụ reduction, kết quả cuối vẫn giữ encounter order cho nguồn ordered stream.
- `groupingByConcurrent` có thể tốt khi có dữ liệu đủ lớn và nhu cầu gom nhóm không phụ thuộc encounter order; không mặc định nhanh hơn `groupingBy` ở mọi trường hợp, nhất là khi số key nhỏ gây tranh chấp trên cùng nhóm.

Nếu cần bảo toàn encounter order trong từng nhóm, dùng collector phù hợp như `groupingBy` với nguồn ordered và downstream theo yêu cầu, sau đó đánh giá chi phí parallel. Bản thân `groupingByConcurrent` không bảo đảm thứ tự các phần tử trong nhóm.

## 10. `forEach`, `forEachOrdered`, `peek` và side effects

### `forEach` không giữ thứ tự gặp phần tử

```java
List.of(1, 2, 3, 4).parallelStream()
        .forEach(System.out::println);
```

Đây là đoạn chạy được khi đặt trong phương thức và import `List`. Các dòng có thể xuất hiện theo **bất kỳ thứ tự** nào; không nên viết expected stdout `1,2,3,4` cho chương trình này. Việc `PrintStream.println` có cơ chế đồng bộ nội bộ không khiến thứ tự logical của phần tử được khôi phục.

### `forEachOrdered` giữ encounter order của nguồn ordered

```java
List.of(1, 2, 3, 4).parallelStream()
        .forEachOrdered(System.out::println);
```

Với nguồn `List` có encounter order, output là `1`, `2`, `3`, `4` theo thứ tự. Stream API áp dụng ordering/synchronization cần thiết giữa các hành động `forEachOrdered`, có thể làm giảm lợi ích parallelism. Điều này không có nghĩa mọi callback trung gian chạy theo thứ tự, hoặc có thể sửa tùy ý một object bên ngoài ở các stage khác mà không cần đồng bộ.

Nếu mục tiêu chỉ là tạo danh sách đã biến đổi, `map(...).toList()` vẫn trực tiếp và rõ hơn.

### `peek` không phải công cụ thực hiện side effect nghiệp vụ

```java
AtomicInteger counter = new AtomicInteger();
long size = numbers.parallelStream()
        .peek(n -> counter.incrementAndGet())
        .count();
```

Đây là **phản ví dụ**: với một số source/pipeline, `count()` có thể suy ra kết quả không cần duyệt các phần tử, nên `peek` không nhất thiết được gọi cho từng phần tử. `AtomicInteger` tránh race trên counter nhưng không biến `peek` thành contract bảo đảm side effect. `peek` hữu ích cho chẩn đoán thận trọng, không phải phương thức chuẩn để tạo kết quả hay cập nhật trạng thái nghiệp vụ.

Trong nói chung, Java Stream có thể tối ưu hóa và bỏ qua evaluation của một số stage nếu không ảnh hưởng kết quả terminal theo contract. Do đó không xây logic sống còn dựa trên tác dụng phụ của `map`, `filter` hay `peek`.

## 11. Associativity, identity và thứ tự kết quả

Với parallel reduction, framework được phép chia dữ liệu thành các partition rồi kết hợp theo cây, nên phép gộp cần **associative** và có identity thích hợp.

Cho ví dụ phép nối chuỗi: nếu chỉ cần chuỗi tổng hợp cuối cùng, một `joining` collector có thể phối hợp nhiều buffer nội bộ. Nhưng nếu thuật toán muốn kết quả “phần tử trước” phụ thuộc việc worker nào hoàn tất trước, đó là phụ thuộc lịch chạy, không phải logic của stream.

Ba loại “thứ tự” cần phân biệt:

1. **Encounter order**: thứ tự logic của phần tử theo source, ví dụ `List.of("a","b","c")`.
2. **Execution order**: thứ tự callback thực tế chạy; với parallel stream có thể khác encounter order.
3. **Result order**: thứ tự đầu ra được terminal operation bảo đảm. `toList()` giữ encounter order nếu có, `forEach` không bảo đảm, `forEachOrdered` có, `groupingByConcurrent` không bảo đảm encounter order.

Đối với ordered stream, `findFirst()` cố tuân theo phần tử đầu tiên theo encounter order. `findAny()` cho phép chọn một phần tử bất kỳ để tăng cơ hội xử lý nhanh khi parallel; không dùng `findAny()` nếu nghiệp vụ đòi kết quả “đầu tiên”.

`unordered()` có thể mở ra một số tối ưu khi thuật toán không phụ thuộc thứ tự, nhưng chỉ được gọi khi đầu ra thật sự cho phép bỏ encounter order.

## 12. Vì sao thread-safe collection chưa chắc là thiết kế tốt nhất

Khi yêu cầu **có chủ đích** là ghi ra một tài nguyên chia sẻ ngoài stream (ví dụ telemetry hoặc sink không thể đổi API), cần synchronization và kiểm soát side effect phù hợp. Nhưng:

- `Collections.synchronizedList(new ArrayList<>())` đồng bộ hóa từng thao tác trên list; nó vẫn không bảo đảm thứ tự xử lý theo nguồn nếu dùng `parallel().forEach`.
- `ConcurrentLinkedQueue` cho phép append đồng thời nhưng không bảo đảm thứ tự queue chính là encounter order của source.
- `ConcurrentHashMap` hỗ trợ các phép cập nhật atomic như `merge` và `compute` theo contract; vẫn phải chọn hàm remapping đúng, không đưa mutable state không bảo vệ vào bên trong.
- `AtomicInteger`/`LongAdder` thích hợp cho một số bộ đếm cùng lúc nhưng có chi phí chia sẻ, và vẫn nên dùng `count()` nếu chỉ cần tổng số phần tử của một pipeline.

Nếu tác vụ phải gọi API external, cập nhật database hoặc ghi file, đó là side effect **ngoài mô hình collection**: an toàn thread của object Java chưa đủ để bảo đảm idempotency, thứ tự, transaction hay khả năng retry. Có thể chạy tuần tự hoặc tách side effect thành bước riêng sau phép tính thuần dữ liệu.

Các thao tác lặp lại `map` hoặc terminal trên cùng một source có thể chạy trên thread khác nhau; không dùng `ThreadLocal` như một map từ “phần tử dữ liệu” tới “bucket cố định” rồi mong kết quả có thứ tự nhất quán. Stream không cấp một thread duy nhất cố định cho mỗi phần tử.

## 13. Phần tử đầu vào mutable cũng có thể gây race

Giữ source `List` không thay đổi **chưa đủ** nếu các phần tử bên trong có field mutable.

Ví dụ dễ sai:

```java
customers.parallelStream()
        .forEach(customer -> customer.setPoints(customer.getPoints() + 1));
```

Đây là mảnh mã minh họa; `Customer` cần được định nghĩa. Nếu mỗi phần tử thực sự là **một đối tượng khác nhau** và không được truy cập đồng thời từ bên ngoài, việc sửa mỗi đối tượng có thể không tạo race giữa các phần tử của stream, nhưng vẫn tạo side effect khó kiểm soát. Nếu list chứa **nhiều tham chiếu cùng trỏ đến một `Customer`**, hoặc có thread khác đang sửa các object ấy, nhiều callback có thể đọc/ghi cùng state và mất cập nhật.

Cách dễ lập luận hơn là tạo giá trị mới bất biến:

```java
record Customer(String id, int points) {}

List<Customer> updated = customers.parallelStream()
        .map(c -> new Customer(c.id(), c.points() + 1))
        .toList();
```

Đây là **mảnh minh họa** cần có `customers` và `List` phù hợp trong ngữ cảnh. `record` ở đây chứa `String` và `int` không biến đổi; với record chứa `List` hoặc object mutable, chỉ dùng `record` **không tự tạo deep immutability**.

Nếu source hoặc đồ thị object bị sửa đồng thời trong quá trình stream, cần snapshot an toàn, immutable data hoặc hợp đồng concurrency rõ ràng; đọc dữ liệu bằng một `List.copyOf(source)` chỉ sao chép cấu trúc list, không clone các object bên trong.

## 14. Khi nào nên dùng parallel stream?

Parallel stream hữu ích nhất khi phần tử đủ nhiều, mỗi phần tử có công việc CPU đáng kể, phép toán độc lập, reduction có thể kết hợp hiệu quả, và việc chia việc/hợp nhất rẻ hơn thời gian tiết kiệm được. Nó không phải “bật một cờ rồi ứng dụng tự nhanh”.

Các yếu tố ảnh hưởng:

- **Khối lượng và độ phức tạp**: vài chục phép cộng nhỏ có overhead lớn so với stream tuần tự.
- **Spliterator/source**: `ArrayList` và mảng thường dễ chia, còn một số nguồn khó split hoặc mất nhiều công chuyển đổi.
- **Thứ tự**: `sorted`, `limit`, `findFirst` trên ordered stream có thể cần coordination.
- **Collector**: chi phí tạo nhiều container/merge có thể cao; concurrent collector có thể tranh chấp khi số key ít.
- **Tài nguyên dùng chung**: common `ForkJoinPool` được stream framework sử dụng trong tình huống thông thường, có thể chịu ảnh hưởng của công việc song song khác trong cùng JVM; không nên giả định pool luôn trống hoặc có số thread cố định theo máy.
- **I/O blocking**: `parallelStream()` không phải bộ điều phối mặc định tốt cho hàng loạt request blocking; cần quản lý concurrency và deadline riêng, cân nhắc executor phù hợp với đặc tính workload.

Nếu cần so sánh hiệu năng, đo workload đại diện ở cả chế độ sequential/parallel, khởi động JVM đủ lâu, chọn input đủ lớn, kiểm tra GC/CPU, và dùng công cụ benchmark phù hợp như JMH. **Luôn chứng minh correctness trước khi đo tốc độ.**

## 15. Checklist rà soát một parallel pipeline

Khi đọc một pipeline, có thể lần lượt hỏi:

1. **Source có bị sửa đồng thời không?** Nếu có, có phải concurrent source được thiết kế cho điều đó và semantics có đáp ứng nghiệp vụ không?
2. **Lambda có đọc/ghi state bên ngoài thay đổi theo thời gian không?** Nếu có, có thể biến state đó thành input hoặc cấu trúc kết quả hay không?
3. **Có dùng `forEach` chỉ để thêm vào collection chung không?** Thường thay bằng `map/filter/collect`.
4. **Reduction có identity và hàm kết hợp associative không?** Nếu không, kết quả có thể thay đổi theo cách partition.
5. **Có giả định callback chạy theo thứ tự nguồn hoặc trên thread nhất định không?** Parallel stream không hứa điều đó.
6. **Có dùng atomic/synchronized để che một phép tính vốn có thể reduce không?** Ưu tiên phép reduction trực tiếp và so sánh hiệu năng.
7. **Có phụ thuộc side effect của `peek`/intermediate operation không?** Stream được phép tối ưu hóa, nên logic đó không đáng tin.
8. **Đầu ra cần order, mutability, thread safety như thế nào?** Chọn `toList`, `toCollection`, `groupingBy`, `groupingByConcurrent` đúng contract.
9. **Kết quả đã được kiểm tra với dữ liệu trùng key, rỗng, lớn, và chạy lặp nhiều lần chưa?** Lỗi race đôi khi chỉ xuất hiện dưới tải thực.
10. **Parallel có thật sự đem lại lợi ích cho workload này không?** Nếu không, một stream tuần tự với lambda stateless vẫn là lựa chọn rất tốt.

## 16. Bài tập nhỏ và đáp án

**Bài 1.** Mã sau có đúng với parallel stream không?

```java
List<String> out = new ArrayList<>();
input.parallelStream().map(String::trim).forEach(out::add);
```

**Đáp án:** Không an toàn vì nhiều thread cùng sửa `ArrayList`. Dùng `List<String> out = input.parallelStream().map(String::trim).toList();`; chỉ tạo mutable copy sau đó nếu thật sự cần.

**Bài 2.** Thay `ArrayList` bằng `Collections.synchronizedList` thì kết quả có giữ thứ tự đầu vào không?

**Đáp án:** Không. Nó bảo vệ từng `add()` nhưng `forEach` trên parallel stream không bảo đảm encounter order. Nếu cần thứ tự input, dùng ordered source và `toList()` hoặc collector phù hợp.

**Bài 3.** `map(n -> atomicCounter.getAndIncrement())` có stateless chỉ vì dùng atomic không?

**Đáp án:** Không. Nó không có data race trên counter nhưng giá trị map phụ thuộc thứ tự thực thi các lần gọi, tức là phụ thuộc state dùng chung.

**Bài 4.** `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` có phải đồng thời gọi `add` lên một `ArrayList` duy nhất không?

**Đáp án:** Không. Các nhánh có container tích lũy riêng theo contract, framework gọi combiner để hợp nhất; supplier phải trả container mới.

**Bài 5.** `distinct()` là stateful operation; có cần cấm trong parallel stream không?

**Đáp án:** Không. Đây là operation của thư viện được thiết kế để dùng với stream, có thể mất chi phí coordination. Nó khác một lambda tự đọc/ghi shared `HashSet`.

**Bài 6.** `parallelStream().forEachOrdered(...)` có làm mọi `map` trước đó chạy tuần tự không?

**Đáp án:** Không. Terminal operation này giữ thứ tự gọi action theo encounter order khi source ordered, nhưng các stage phía trước vẫn có thể được thực hiện song song.

## 17. Tổng kết khái niệm

**Stateless lambda** phụ thuộc vào input của chính lần gọi và ngữ cảnh bất biến; **non-interference** tránh sửa source trong khi stream đang xử lý; **reduction/collector** giao quyền phối hợp kết quả cho Stream framework. Ba nguyên tắc này giúp một pipeline vẫn đúng khi chuyển từ `stream()` sang `parallelStream()`.

Khi thấy một `forEach` ghi vào `ArrayList`/`HashMap` hay bộ đếm chung, hãy xác định mục tiêu thực sự là tạo danh sách, lọc, đếm, tính tổng hay nhóm dữ liệu. Biểu diễn đúng mục tiêu bằng `map`, `filter`, `count`, `sum`, `reduce`, `collect` hoặc concurrent collector phù hợp sẽ vừa dễ kiểm tra hơn vừa cho framework cơ hội tối ưu.

### Tài liệu tham khảo

- [Java SE 17 – java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): non-interference, stateless behavioral parameters, side effects, reduction.
- [Java SE 17 – Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `parallel`, `map`, `forEach`, `forEachOrdered`, `collect`, `toList`.
- [Java SE 17 – Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `toList`, `groupingBy`, `groupingByConcurrent`, `toConcurrentMap`.
- [Java SE 17 – ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): lưu ý đồng bộ hóa khi nhiều thread sửa danh sách.
