# Collection.stream() và Collection.parallelStream() trong Java

## 1. Hai cách tạo Stream từ Collection

Từ Java 8, interface `java.util.Collection<E>` có hai phương thức mặc định quan trọng để chuyển một **nguồn Collection** thành pipeline Stream:

```java
Stream<E> stream()
Stream<E> parallelStream()
```

- `collection.stream()` trả một **sequential Stream**: pipeline được thiết lập để xử lý tuần tự khi terminal operation được gọi, trừ khi bạn chủ động thay đổi chế độ.
- `collection.parallelStream()` trả một **possibly parallel Stream**: pipeline được đặt ở chế độ song song và có thể chia công việc thành các phần để xử lý đồng thời khi có terminal operation.
- Cả hai **không sao chép Collection** thành một danh sách mới chỉ vì bạn gọi phương thức. Chúng tạo Stream có **Collection là nguồn**.
- Cả hai đều dùng mô hình **intermediate operations lazy** như `filter`, `map`, `sorted`, `distinct`; công việc duyệt dữ liệu thường bắt đầu khi gọi terminal như `collect`, `sum`, `reduce` hoặc `forEach`.
- Cả hai đều cho phép viết pipeline cùng kiểu. **Chế độ song song là chiến lược thực thi**, không phải một kiểu dữ liệu đầu ra khác, cũng không tự bảo đảm chương trình chạy nhanh hơn hoặc an toàn cho mọi side effect.

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> sequential = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .collect(Collectors.toList());

List<Integer> parallel = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .collect(Collectors.toList());

System.out.println(sequential); // [4, 16, 36]
System.out.println(parallel);   // [4, 16, 36]
```

`numbers` là một `List` có **encounter order** xác định; `filter` và `map` là những phép biến đổi thuần, còn collector `toList()` giữ encounter order khi stream có thứ tự. Vì vậy kết quả ở cả hai trường hợp là cùng một danh sách theo thứ tự. Tuy nhiên, khi chạy parallel, **thứ tự callback thực sự được gọi và thread thực hiện từng callback không được bảo đảm giống sequential**.

**Quy tắc nền tảng:** trước khi chọn `parallelStream()`, hãy chắc chắn code đã **đúng về kết quả, độc lập giữa các phần tử và không can thiệp nguồn**. Chỉ sau đó mới đo xem chế độ song song có giúp cải thiện hiệu năng thực tế không.

## 2. `Collection.stream()` nằm ở đâu trong Collection Framework?

`Collection<E>` là interface cha của các loại collection như `List<E>`, `Set<E>`, `Queue<E>`, `Deque<E>`. Những loại này có thể dùng `stream()`/`parallelStream()` nếu triển khai hỗ trợ đúng hợp đồng.

```java
List<String> list = Arrays.asList("Java", "Kotlin");
long listCount = list.stream().count(); // 2

java.util.Set<String> set =
        new java.util.LinkedHashSet<>(list);
long setCount = set.parallelStream().count(); // 2
```

Không nhầm **Collection** với **Map**:

```java
java.util.Map<String, Integer> points =
        new java.util.HashMap<>();

points.put("A", 10);
points.put("B", 20);

// Map không trực tiếp extends Collection:
// points.stream(); // KHÔNG BIÊN DỊCH

// Chọn view phù hợp:
long entries = points.entrySet().stream().count();
long keys = points.keySet().parallelStream().count();
long values = points.values().stream().count();
```

`Map.entrySet()`, `keySet()` và `values()` trả các Collection views của Map. Việc chọn view nói lên **bạn muốn duyệt entry, key hay value**, chứ không chỉ chọn xử lý tuần tự/song song.

### 2.1. Stream là *view xử lý*, không phải Collection mới

```java
List<String> names = new java.util.ArrayList<>(
        Arrays.asList("An", "Binh", "Chi"));

java.util.stream.Stream<String> stream = names.stream();
```

Lúc này `stream` không phải là một `List` thứ hai có sẵn ba phần tử. Nó mô tả nguồn và kế hoạch duyệt. Không gọi `stream.add(...)` như một Collection. Nếu cần kết quả được lưu trữ độc lập, dùng terminal:

```java
List<String> copy = names.stream()
        .collect(Collectors.toList());
```

`copy` là một List do collector tạo ra. Tuy nhiên, đây là **shallow copy** của các phần tử; các đối tượng phần tử mutable không tự được deep-copy.

### 2.2. Tên phương thức không quyết định kiểu phần tử cụ thể

`Collection<E>.stream()` trả `Stream<E>`. Ví dụ:

- `List<String>` → `Stream<String>`.
- `Set<Integer>` → `Stream<Integer>`.
- `Collection<Order>` → `Stream<Order>`.

Không thể cast một `Stream<Order>` thành `Stream<String>` để biến đổi dữ liệu. Muốn đổi kiểu phần tử, dùng `map` đúng hợp đồng:

```java
List<Integer> sizes = Arrays.asList("Java", "Go").stream()
        .map(String::length)
        .collect(Collectors.toList()); // [4, 2]
```

Nếu cần xử lý lượng lớn số nguyên, `mapToInt` và `IntStream` có thể tránh boxing trung gian trong những phép tính cụ thể.

## 3. Sequential Stream: mặc định dễ hiểu và dự đoán hơn

Với `stream()` trên `List` có encounter order, khi xử lý tuần tự, pipeline thường đi qua phần tử theo thứ tự của nguồn:

```java
List<String> items = Arrays.asList("a", "b", "c");

items.stream()
        .map(String::toUpperCase)
        .forEach(System.out::println);
```

Với nguồn List ở ví dụ, đầu ra theo thứ tự là:

```text
A
B
C
```

`forEach` trên sequential pipeline có thể dùng để minh họa hoạt động đơn giản. Nhưng với nguồn **không có encounter order**, ngay cả khi xử lý sequential bạn cũng không thể suy luận một thứ tự nghiệp vụ nếu collection không hứa cung cấp nó.

### 3.1. Không phải Set nào cũng giống List về thứ tự

- `ArrayList` và `LinkedList` có thứ tự phần tử theo List.
- `LinkedHashSet` duy trì thứ tự gặp/phần tử thêm vào theo hợp đồng của nó.
- `TreeSet` duy trì thứ tự sắp xếp theo comparator/natural ordering.
- `HashSet` **không bảo đảm encounter order** thích hợp cho logic yêu cầu thứ tự.
- Concurrent collections có thể có các đặc tính spliterator và quy tắc nhất quán khác nhau.

Nếu cần kết quả ổn định theo thứ tự, hãy **chọn collection có hợp đồng thứ tự**, dùng `sorted` với comparator thích hợp hoặc collector có kết quả theo thứ tự rõ ràng. Đừng phụ thuộc thứ tự quan sát tình cờ của `HashSet`.

### 3.2. Sequential không có nghĩa có thể can thiệp vào Collection

Đoạn sau là anti-pattern:

```java
List<Integer> source = new java.util.ArrayList<>(
        Arrays.asList(1, 2, 3, 4));

// KHÔNG NÊN: sửa nguồn từ callback đang duyệt.
// source.stream()
//       .peek(source::remove)
//       .collect(Collectors.toList());
```

Với nguồn Collection không concurrent, việc thay đổi nguồn trong khi terminal đang thực thi có thể gây lỗi hoặc kết quả sai. **Non-interference** áp dụng cho cả sequential và parallel, không chỉ khi nhiều thread.

## 4. Parallel Stream: khai báo chế độ song song, không khai báo thread

`parallelStream()` tạo Stream có **parallel execution mode**. Khi chạy terminal, implementation có thể chia dữ liệu thành nhiều phần, xử lý/ghép kết quả theo cơ chế phù hợp với `Spliterator` và operation trong pipeline.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

boolean parallelMode = numbers.parallelStream().isParallel();
// parallelMode == true

boolean sequentialMode = numbers.stream().isParallel();
// sequentialMode == false
```

`isParallel()` chỉ báo **chế độ đã chọn**. Nó **không đo** số thread đang thực tế xử lý, cũng không chứng minh pipeline có lợi về tốc độ.

### 4.1. Parallel không đồng nghĩa chạy bất đồng bộ

`parallelStream()` không phải API `CompletableFuture` và không mặc nhiên trả một background job để bạn nhận kết quả sau. Với terminal thông thường như `sum()` hoặc `collect()`, lời gọi vẫn hoàn thành trước khi trả giá trị cho caller:

```java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 15
```

JDK thường thực thi parallel stream bằng cơ chế fork/join phù hợp với runtime, có thể dùng thread của caller và các worker. Không nên xây logic phụ thuộc một số lượng thread cụ thể, tên worker, thứ tự lịch hoặc một thread pool chính xác trong mọi ngữ cảnh triển khai.

### 4.2. Parallel không đồng nghĩa phải có nhiều CPU đang hoạt động

Một stream ở chế độ parallel có thể xử lý một phần công việc theo cách rất gần tuần tự, đặc biệt với nguồn nhỏ, operation nhanh hoặc tài nguyên xử lý hạn chế. Không dùng `isParallel()` làm thước đo tốc độ.

### 4.3. Thực thi song song được phép khác thứ tự callback

```java
numbers.parallelStream()
        .map(n -> {
            System.out.println("mapping " + n);
            return n * 2;
        })
        .collect(Collectors.toList());
```

Đây là ví dụ để quan sát, **không có stdout xác định cho các dòng `mapping`**. Ngay cả khi danh sách kết quả vẫn theo encounter order, log có thể xuất hiện không theo thứ tự. Trong code thực tế, side effect trong `map`/`peek` thường không phải thiết kế phù hợp.

## 5. `stream()` và `parallelStream()` khác nhau chính xác ở đâu?

| Thuộc tính | `collection.stream()` | `collection.parallelStream()` |
| --- | --- | --- |
| Chế độ ban đầu | Sequential | Parallel |
| Kiểu kết quả | `Stream<E>` | `Stream<E>` |
| Nguồn | Cùng Collection | Cùng Collection |
| Intermediate operations | Lazy | Lazy |
| Khi nào đánh giá phần tử? | Khi có terminal phù hợp | Khi có terminal phù hợp |
| Có luôn giữ encounter order của kết quả? | Theo hợp đồng nguồn và operation | Theo hợp đồng nguồn và operation, dù callback chạy khác thứ tự |
| Thread thực thi callback | Thường cùng thread duyệt tuần tự | Có thể nhiều thread |
| Có tự làm Collection thread-safe? | Không | **Không** |
| Có tự deep-copy dữ liệu? | Không | Không |
| Có bảo đảm nhanh hơn? | Không đặt vấn đề | **Không** |
| Có thể gọi `filter/map/reduce/collect`? | Có | Có |
| Có thể chuyển chế độ sau khi tạo? | `parallel()` | `sequential()` |

Trọng tâm là **hai entry points cùng mô hình Stream**. Đổi cách tạo Stream không làm thay đổi ý nghĩa nghiệp vụ của `filter`, `map` hoặc `reduce`, nhưng nó có thể làm lộ những lỗi trong callback dùng shared mutable state.

## 6. Thay đổi chế độ bằng `parallel()` và `sequential()`

Bạn không bắt buộc chọn chế độ chỉ ở phương thức tạo Stream. `BaseStream` còn có:

```java
Stream<T> parallel()
Stream<T> sequential()
boolean isParallel()
```

Ví dụ:

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4);

boolean a = numbers.stream()
        .parallel()
        .isParallel(); // true

boolean b = numbers.parallelStream()
        .sequential()
        .isParallel(); // false

boolean c = numbers.stream()
        .parallel()
        .sequential()
        .isParallel(); // false
```

**Quy tắc quan trọng:** mode được dùng khi thực thi pipeline được quyết định theo cấu hình cuối cùng phù hợp; Java không cam kết pipeline chạy nửa đầu sequential, nửa sau parallel chỉ vì bạn viết `stream().map(...).parallel().filter(...)`.

Ví dụ:

```java
long sum = numbers.stream()
        .map(n -> n * 2)
        .parallel()
        .filter(n -> n > 4)
        .mapToLong(Integer::longValue)
        .sum();
```

`parallel()` thay đổi chế độ pipeline, **không chèn một stage xử lý được dùng như hàng rào rõ ràng tách hai nhóm callback**. Nếu bạn muốn một giai đoạn bắt buộc tuần tự rồi một giai đoạn song song trên dữ liệu đã materialize, phải **tạo ranh giới rõ ràng bằng terminal operation + nguồn mới** và đánh giá chi phí bộ nhớ/vòng đời.

### 6.1. Không dùng lại cùng Stream sau terminal

```java
Stream<Integer> stream = numbers.stream();
long count = stream.count();

// KHÔNG HỢP LỆ theo mô hình single-use:
// stream.parallel().reduce(0, Integer::sum);
```

Cách đúng là tạo Stream mới:

```java
long count = numbers.stream().count();
int sum = numbers.parallelStream().reduce(0, Integer::sum);
```

Collection có thể dùng làm nguồn cho nhiều Stream mới khi phù hợp, nhưng **mỗi đối tượng Stream chỉ dùng một pipeline tiêu thụ**.

## 7. Encounter order và thứ tự của kết quả

**Encounter order** là thứ tự hợp đồng mà nguồn Stream cung cấp. Nó khác với **thứ tự thực thi callback**.

### 7.1. Parallel `collect(toList())` có thể giữ thứ tự nguồn

```java
List<Integer> input = Arrays.asList(5, 1, 4, 2, 3);

List<Integer> result = input.parallelStream()
        .map(n -> n * 10)
        .collect(Collectors.toList());

// result = [50, 10, 40, 20, 30]
```

`List` có encounter order; `map` giữ thứ tự logic; collector `toList()` của Java 8 tôn trọng encounter order của ordered stream. Nhưng việc mapper xử lý `5` trước hay sau `1` không phải thứ tự đã được bảo đảm.

### 7.2. `forEach` có thể phá vỡ thứ tự quan sát

```java
input.parallelStream()
        .forEach(System.out::println);
```

Đầu ra gồm các phần tử cần xử lý, nhưng **không bảo đảm thứ tự in**. Không viết expected stdout cố định cho đoạn này.

Nếu cần side effect theo encounter order:

```java
input.parallelStream()
        .forEachOrdered(n -> System.out.println("item=" + n));
```

Khi nguồn là `List` trên, thứ tự các dòng sẽ là:

```text
item=5
item=1
item=4
item=2
item=3
```

`forEachOrdered` bảo đảm hành động theo encounter order (nếu stream có thứ tự), nhưng **có thể làm giảm lợi ích song song**. Nó không biến mọi callback upstream thành chạy theo thứ tự hoặc cùng một thread.

### 7.3. `unordered()` cho phép bỏ ràng buộc thứ tự

Khi thứ tự **thực sự không quan trọng**, bạn có thể gọi:

```java
long unique = input.parallelStream()
        .unordered()
        .distinct()
        .count();
```

`unordered()` cho phép pipeline không cần duy trì encounter order ở các stage tiếp theo. Trong một số trường hợp, việc này có thể giảm chi phí của `distinct`, `limit` hoặc các operation nhạy với thứ tự. Nhưng `unordered()` **không tự thay đổi nội dung Collection**, không tự tạo hiệu năng tốt hơn trong mọi trường hợp, và có thể thay đổi ngữ nghĩa nếu bạn đang trông đợi `findFirst` hay một prefix cụ thể.

**Không dùng `unordered()` chỉ để “làm nhanh hơn” khi kết quả nghiệp vụ thực chất có thứ tự.**

### 7.4. `findFirst` so với `findAny`

```java
Optional<Integer> first = input.parallelStream()
        .filter(n -> n > 2)
        .findFirst(); // Optional[5]

Optional<Integer> any = input.parallelStream()
        .filter(n -> n > 2)
        .findAny();
```

`findFirst` phải trả phần tử phù hợp đầu theo encounter order của `input` — ở đây là 5. `findAny` cho phép trả **một phần tử phù hợp bất kỳ**, nên không kết luận đó là 5, 4 hay 3 ở mọi lần chạy.

Khi không yêu cầu phần tử đầu, `findAny` có thể tạo thêm cơ hội tối ưu cho parallel execution. Không dùng `findFirst` và `findAny` như các từ đồng nghĩa.

## 8. Vì sao parallel Stream có thể nhanh hơn?

Chia một phép tính độc lập thành các phần có thể làm giảm thời gian hoàn thành **nếu** lượng công việc đủ lớn, nguồn chia được hiệu quả, tài nguyên CPU có sẵn và chi phí phân chia/ghép nhỏ hơn lợi ích.

Có thể hình dung một phép tổng:

```text
Nguồn: [1, 2, 3, 4, 5, 6, 7, 8]

Phần A: [1, 2] -> tổng cục bộ 3
Phần B: [3, 4] -> tổng cục bộ 7
Phần C: [5, 6] -> tổng cục bộ 11
Phần D: [7, 8] -> tổng cục bộ 15

Ghép: 3 + 7 + 11 + 15 = 36
```

Đây là sơ đồ **khái niệm**, không phải cam kết một implementation sẽ phân chia thành đúng bốn nhóm. Parallel Stream dùng `Spliterator` và các chiến lược scheduling của implementation để chia dữ liệu.

Các điều kiện thuận lợi thường gồm:

- Nguồn có nhiều phần tử, có thể phân chia tương đối đều.
- Mỗi phần tử có công việc tính toán **độc lập, không có tác dụng phụ** và đủ nặng để bù overhead.
- Terminal hỗ trợ phép **associative reduction** hoặc collector ghép kết quả an toàn.
- Không có quá nhiều stateful/ordered bottlenecks.
- Máy có tài nguyên CPU thực sự dành cho công việc, không bị tranh chấp nặng bởi tác vụ khác.
- Ứng dụng không bắt buộc thứ tự xử lý callback.

Tuy nhiên, **không có ngưỡng số lượng phần tử phổ quát** để quyết định dùng parallel. Một triệu phép cộng rất rẻ có thể khác hoàn toàn một nghìn phép tính nặng CPU; kích thước nguồn chỉ là một yếu tố.

### 8.1. Overhead nào khiến parallel chậm hơn?

- Chia tách công việc (`splitting`).
- Lên lịch các task và phối hợp worker.
- Kết hợp kết quả trung gian (`combining`).
- Buffer để giữ encounter order, nhất là với `sorted`, `distinct` hoặc ordered `limit`.
- Contention khi nhiều callback cùng khóa/chạm vào state dùng chung.
- Áp lực GC hoặc băng thông bộ nhớ khi materialize những kết quả trung gian.
- Khối lượng công việc thiếu cân bằng giữa các phần được chia.

Vì vậy, không tự động thay mọi `stream()` bằng `parallelStream()`.

## 9. Vai trò của `Spliterator` trong hiệu năng

Một Stream lấy nguồn từ Collection được điều khiển bởi `Spliterator` hoặc cơ chế tương ứng do implementation cung cấp. `Spliterator` mô tả cách tiến qua phần tử và khả năng **chia nguồn thành những phần độc lập**.

Những đặc tính có thể hỗ trợ tối ưu:

| `Spliterator` characteristic | Ý nghĩa khái quát |
| --- | --- |
| `SIZED` | Nguồn biết chính xác số lượng phần tử còn lại theo hợp đồng |
| `SUBSIZED` | Các phần được chia có thông tin kích thước thích hợp |
| `ORDERED` | Nguồn có encounter order |
| `DISTINCT` | Nguồn có các phần tử khác nhau theo hợp đồng |
| `SORTED` | Nguồn có thứ tự sắp xếp |
| `IMMUTABLE` | Nguồn phù hợp đặc tính bất biến trong khi duyệt |
| `CONCURRENT` | Nguồn hỗ trợ cơ chế concurrent modification theo hợp đồng |
| `NONNULL` | Nguồn khẳng định phần tử không null |

`ArrayList` thường thuận lợi để chia theo vùng chỉ số. Một số cấu trúc liên kết hoặc nguồn có Spliterator khó chia cân bằng có thể không đạt lợi ích parallel tương tự. Dù vậy, hiệu năng còn phụ thuộc thao tác tính toán, kích thước dữ liệu, bộ nhớ, implementation và môi trường CPU.

**Không dùng tên collection để kết luận tuyệt đối “parallel sẽ nhanh” hoặc “không thể parallel”.** Benchmark và đặc tính nguồn cụ thể mới quyết định.

### 9.1. `spliterator()` không phải cách xem “một bản sao dữ liệu”

```java
Spliterator<Integer> splitter = input.spliterator();
boolean sized = splitter.hasCharacteristics(Spliterator.SIZED);
```

Đoạn này cần import `java.util.Spliterator`. Spliterator là cơ chế duyệt/chia nguồn, không phải List sao chép. Với Collection mutable, không cố sửa nguồn trong lúc một spliterator đã bắt đầu duyệt nếu không có hợp đồng concurrency phù hợp.

### 9.2. Nguồn concurrent và non-concurrent khác nhau

`ConcurrentHashMap`/các concurrent collections có các hợp đồng chuyên biệt về tương tác đồng thời và visibility. Nhưng việc **nguồn là concurrent** không làm các callback sử dụng **biến ngoài không đồng bộ** trở nên thread-safe.

Ngược lại, `ArrayList.parallelStream()` vẫn có thể chạy an toàn khi **không sửa ArrayList trong lúc duyệt** và callback độc lập/stateless. Không cần chuyển mọi List thành một concurrent collection chỉ để gọi `parallelStream()`.

## 10. Rủi ro lớn nhất: side effects và shared mutable state

### 10.1. Anti-pattern: thêm vào cùng một ArrayList từ parallel forEach

```java
List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);
List<Integer> results = new ArrayList<>();

// KHÔNG NÊN:
// source.parallelStream()
//       .map(n -> n * 2)
//       .forEach(results::add);
```

`ArrayList` không hỗ trợ nhiều thread cùng cập nhật như vậy. Kết quả có thể mất phần tử, sai cấu trúc hoặc phát sinh lỗi. Ngay cả khi một lần chạy “đúng”, đó không phải bằng chứng code an toàn.

**Cách đúng khi muốn tạo danh sách kết quả:**

```java
List<Integer> results = source.parallelStream()
        .map(n -> n * 2)
        .collect(Collectors.toList());
```

Collector được thiết kế để tích lũy và ghép các kết quả phù hợp với mô hình Stream; bạn không cần tự điều phối một `ArrayList` dùng chung trong callback.

`Collectors.toList()` không hứa một implementation List cụ thể hoặc khả năng chỉnh sửa cụ thể theo hợp đồng API. Nếu thật sự yêu cầu một `ArrayList`, có thể dùng collector `toCollection(ArrayList::new)`:

```java
List<Integer> results = source.parallelStream()
        .map(n -> n * 2)
        .collect(Collectors.toCollection(ArrayList::new));
```

Collector có thể tạo các container cục bộ và ghép chúng đúng cách, thay vì cho các callback đồng thời truy cập cùng một biến `results` không đồng bộ.

### 10.2. Anti-pattern: mutable counter dùng chung

```java
int[] counter = {0};

// KHÔNG NÊN:
// source.parallelStream().forEach(n -> counter[0]++);
```

`counter[0]++` không phải thao tác atomic. Nếu nhiều worker chạy đồng thời, giá trị cuối có thể nhỏ hơn số phần tử. Với pipeline có thể tối ưu, một side effect đặt trong intermediate operation còn có thể bị bỏ qua.

**Cách đúng để đếm:**

```java
long count = source.parallelStream().count();
```

Muốn tính tổng:

```java
int sum = source.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
```

Hoặc dùng `reduce(0, Integer::sum)`. Đừng tạo một `AtomicInteger` chỉ để thay thế đơn giản cho `sum()` nếu mục tiêu là aggregate; atomics có thể thêm contention không cần thiết.

### 10.3. Thêm `synchronized` không biến thiết kế thành tốt

Bạn có thể khóa một List hoặc dùng concurrent collection cho side effects, nhưng contention có thể xóa lợi thế parallel; kết quả vẫn có thể không có thứ tự như nghiệp vụ muốn. **Tái cấu trúc thành phép tính không side effect + collector/reduction** thường rõ và hiệu quả hơn.

### 10.4. Thực thi không bảo đảm mọi callback được gọi

Một số phép tối ưu hóa có thể bỏ những stage không ảnh hưởng terminal result:

```java
long count = source.parallelStream()
        .peek(System.out::println)
        .count();
```

`peek` có thể không in gì nếu kích thước nguồn đã biết và `count()` được tính trực tiếp. Điều này **hợp lệ** theo Stream API. Không dùng `peek` làm cơ chế ghi log bắt buộc, audit, cập nhật database hoặc gửi thông báo nghiệp vụ.

**Quy tắc an toàn:** predicate/mapper nên **non-interfering** và hầu hết là **stateless**. Không xây correctness dựa vào thứ tự, số lần hoặc thread gọi từng callback trừ khi operation cụ thể có hợp đồng đó.

## 11. Reduction an toàn cho cả sequential và parallel

`reduce` rất hợp với những phép tổng hợp có toán tử **associative** và phần tử đơn vị phù hợp.

### 11.1. Ví dụ đúng: tổng các số nguyên

```java
int seqSum = Arrays.asList(1, 2, 3, 4)
        .stream()
        .reduce(0, Integer::sum);

int parSum = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum);

// seqSum = 10, parSum = 10.
```

Với phép cộng số nguyên trong phạm vi ví dụ, thứ tự nhóm các số không thay đổi kết quả. `0` là identity phù hợp.

### 11.2. Ví dụ sai: dùng phép trừ làm reduction kết hợp

```java
int questionable = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (left, right) -> left - right);
```

Phép trừ **không associative**: `(a - b) - c` thường không bằng `a - (b - c)`. Parallel reduction có thể nhóm các phần theo cách khác với sequential; **không nên kỳ vọng một đáp án cố định theo cách gộp tuần tự**. Thay cách tính theo nghiệp vụ; nếu muốn trừ tổng, hãy lấy tổng rồi đổi dấu:

```java
int negativeSum = -Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .mapToInt(Integer::intValue)
        .sum(); // -10
```

Ví dụ này minh họa tính cần thiết của associativity. Với số thực dấu phẩy động, kết quả cộng nhiều số còn có thể khác đôi chút khi nhóm thứ tự khác vì vấn đề làm tròn; cần xác định yêu cầu số học trước khi parallelize.

### 11.3. Reduce ba tham số đòi hỏi combiner phù hợp

```java
int totalLength = Arrays.asList("a", "bb", "ccc")
        .parallelStream()
        .reduce(
                0,
                (sum, text) -> sum + text.length(),
                Integer::sum
        );
// totalLength = 6
```

`accumulator` cộng độ dài phần tử vào kết quả cục bộ; `combiner` ghép các tổng cục bộ. Chúng phải nhất quán với identity và hành vi kết hợp. Không bỏ qua `combiner` hoặc dùng nó cho một nghiệp vụ khác với accumulator.

## 12. Collectors, grouping và concurrent reductions

### 12.1. `groupingBy` không cần map dùng chung thủ công

```java
List<String> words = Arrays.asList(
        "ant", "ape", "bear", "bee", "boat");

Map<Character, List<String>> grouped = words.parallelStream()
        .collect(Collectors.groupingBy(s -> s.charAt(0)));
```

`groupingBy` có thể tạo các kết quả trung gian và merge chúng khi thực thi parallel. Bạn không cần tạo `HashMap` dùng chung rồi thêm phần tử trong `forEach`. Thứ tự duyệt `Map` kết quả không được bảo đảm là thứ tự key đã gặp nếu Map implementation không hứa điều đó; hãy sắp key khi trình bày.

### 12.2. `groupingByConcurrent` khi ngữ nghĩa cho phép

```java
ConcurrentMap<Character, List<String>> grouped =
        words.parallelStream()
                .unordered()
                .collect(Collectors.groupingByConcurrent(
                        s -> s.charAt(0)));
```

Đoạn này cần import `java.util.concurrent.ConcurrentMap` hoặc tên đầy đủ. `groupingByConcurrent` cung cấp concurrent, unordered collector theo hợp đồng. Thứ tự phần tử trong danh sách của mỗi nhóm **không nên được giả định giống encounter order** khi pipeline hoạt động song song.

Chỉ dùng khi kết quả nghiệp vụ **không đòi hỏi thứ tự** và khi benchmark chứng minh lợi ích. Một collector concurrent không tự làm mọi tác vụ hiệu quả hơn; nó có thể gặp contention hoặc chi phí khác.

### 12.3. Không đồng nhất “parallel” với “collector chạy concurrently vào một container”

Một parallel stream có thể tích lũy vào nhiều result containers riêng rồi **combine** chúng, kể cả khi container như `ArrayList` không thread-safe. Vì vậy, `parallelStream().collect(Collectors.toList())` là một cách dùng hợp lệ; không cần `Collections.synchronizedList` trong callback.

Concurrent reduction vào một container chung có những điều kiện riêng liên quan `Collector.Characteristics.CONCURRENT` và encounter order. Chỉ chọn đúng collector là bạn đã ủy thác logic phối hợp cần thiết cho Stream API.

## 13. Lazy evaluation và thời điểm thay đổi Collection

`Collection.stream()` và `parallelStream()` thường là **lazy**: các intermediate operations không chạy khi được khai báo. Với những nguồn Collection chuẩn có spliterator phù hợp, thay đổi nguồn **trước khi bắt đầu terminal** có thể được phản ánh trong kết quả.

```java
List<String> source = new ArrayList<>(
        Arrays.asList("a", "b"));

Stream<String> stream = source.stream();

source.add("c"); // Thay đổi trước terminal.

List<String> result = stream.collect(Collectors.toList());
// Với ArrayList chuẩn: [a, b, c]
```

Đây là minh họa **late-binding** trên nguồn well-behaved, không phải lời hứa “stream đã chụp snapshot”. Nhưng cũng không được tổng quát rằng mọi custom Collection có binding giống `ArrayList`.

### 13.1. Sửa nguồn trong lúc terminal đang chạy là chuyện khác

```java
List<Integer> numbers = new ArrayList<>(
        Arrays.asList(1, 2, 3, 4));

// KHÔNG NÊN: sửa chính nguồn trong callback.
// numbers.parallelStream()
//        .forEach(numbers::remove);
```

Đây là **interference** trên non-concurrent Collection. Kết quả có thể sai hoặc phát sinh exception. Việc dùng `parallelStream` không tự biến nguồn thành concurrent.

### 13.2. Concurrent Collection có hợp đồng khác nhưng không miễn trừ mọi kiểm tra

Concurrent collections thường có cơ chế duyệt thích hợp khi có thay đổi đồng thời, nhưng **semantics phải được đọc theo từng implementation**. Có thể thấy dữ liệu trước hoặc sau một cập nhật đồng thời tùy loại collection; không vì “concurrent” mà một phép tổng trên dữ liệu đang bị sửa trở thành snapshot nhất quán.

Nếu yêu cầu một bộ dữ liệu cố định, hãy thiết kế **snapshot rõ ràng** hoặc đồng bộ hóa truy cập theo một hợp đồng cụ thể. Nếu chỉ cần throughput cao trên dữ liệu được phép biến đổi, có thể chọn concurrent collection phù hợp và kiểm thử kỹ.

### 13.3. `-parallel` không làm stream gắn với Collection an toàn trước cập nhật khác thread

Đừng chia sẻ một `ArrayList` mutable giữa các producer đang thêm/xóa và một pipeline `parallelStream()` đang duyệt nếu không có chính sách đồng bộ/tái cấu trúc dữ liệu phù hợp. **Dùng nhiều worker không chữa được race condition của nguồn.**

## 14. `parallelStream()` và xử lý blocking I/O

Một phép tính CPU-bound như biến đổi số học thuần có thể phù hợp với parallel stream sau khi đo hiệu năng. Ngược lại, **blocking I/O** hoặc việc gọi HTTP/database trong mỗi callback dễ tạo vấn đề:

- Phần việc có thời gian chờ không đều, khó chia cân bằng.
- Những worker dùng chung có thể bị chiếm khi chờ I/O.
- Cần giới hạn đồng thời, timeout, retry và chính sách backpressure rõ ràng.
- Khi có lỗi giữa nhiều phần việc, propagation/cancellation không tự biến thành mô hình orchestration đầy đủ.
- Side effects như ghi database không tự idempotent chỉ nhờ dùng Stream.

Ví dụ cần cân nhắc kỹ:

```java
// KHÔNG PHẢI LỰA CHỌN MẶC ĐỊNH TỐT CHO I/O:
// urls.parallelStream()
//     .map(url -> httpClient.fetch(url))
//     .collect(Collectors.toList());
```

Đoạn này mang tính khái niệm; `httpClient.fetch` là API giả định của ứng dụng, **không phải phương thức Java SE đã được định nghĩa**. Khi xử lý số lượng lớn request I/O, thường nên chọn cơ chế concurrency có **giới hạn tài nguyên và cancellation/timeout phù hợp** thay vì mặc nhiên dùng parallelStream.

Không cần áp dụng các API đã lỗi thời để xử lý song song. Mục tiêu là chọn cơ chế hiện đại có hợp đồng điều phối đúng với hệ thống, không phải thay mọi vòng lặp bằng một Stream.

## 15. Khi nào nên dùng `stream()`, khi nào cân nhắc `parallelStream()`?

**Ưu tiên `stream()`** khi:

- Dữ liệu ít hoặc công việc trên mỗi phần tử rất nhanh.
- Thứ tự xử lý có ý nghĩa, đặc biệt với side effects.
- Pipeline có nhiều stage stateful hoặc chi phí duy trì thứ tự cao.
- Workload có nhiều I/O/blocking hoặc phụ thuộc trạng thái dùng chung.
- Muốn code đơn giản, dễ debug và có latency ổn định.
- Chưa có đo đạc chứng minh parallel mang lại lợi ích.

**Cân nhắc `parallelStream()`** khi:

- Nguồn có nhiều phần tử và tách tốt.
- Công việc CPU-bound tương đối nặng, độc lập và có thể chia cân bằng.
- Callback stateless, non-interfering, thread-safe theo thiết kế.
- Reduction/collector có hợp đồng hỗ trợ ghép kết quả.
- Thứ tự không bị buộc chặt hoặc chi phí duy trì thứ tự chấp nhận được.
- Có CPU rảnh và benchmark thực tế cho thấy throughput/latency cải thiện.

**Không dùng parallel như giải pháp che lỗi:** nếu sequential cho kết quả đúng nhưng parallel cho kết quả ngẫu nhiên, thường cần sửa shared mutable state, associativity hoặc ngữ nghĩa thứ tự; không phải chỉ tăng số thread.

### 15.1. Benchmark đúng cách

So sánh thời gian trên **tập dữ liệu thực tế**, đo ít nhất:

1. Pipeline sequential và parallel có **cùng ngữ nghĩa kết quả**.
2. Dữ liệu có kích thước và phân bố đại diện.
3. Runtime được warm-up; JIT/GC và nhiễu môi trường được tính đến.
4. Có nhiều lần đo, thống kê trung vị/phân bố, không chọn một lần chạy ngẫu nhiên.
5. Xem cả latency, CPU utilization, allocation và tác động lên những request khác.
6. Không benchmark bằng `System.out.println` trong callback vì I/O và lock của console làm sai tương quan chi phí xử lý.
7. Với công việc phức tạp, cân nhắc công cụ benchmark chuyên dụng cho JVM như **JMH**, thay vì tự so hai giá trị `System.nanoTime()` trong một lần chạy.

JMH là công cụ benchmark phổ biến của hệ sinh thái OpenJDK, **không bắt buộc** để dùng Stream và không thay thế việc test correctness.

## 16. Chương trình Java hoàn chỉnh: so sánh sequential và parallel

Tạo tệp **`CollectionStreamModesDemo.java`**. Chương trình sử dụng API Java 8-compatible, biên dịch/chạy trên JDK 17+ và **chỉ in kết quả có thứ tự xác định**, không in tên thread hoặc thứ tự callback có thể khác nhau.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class CollectionStreamModesDemo {

    public static void main(String[] args) {
        List<Integer> numbers =
                Arrays.asList(5, 1, 4, 2, 3, 6);

        System.out.println("Sequential mode: "
                + numbers.stream().isParallel());
        System.out.println("Parallel mode: "
                + numbers.parallelStream().isParallel());

        List<Integer> sequential = numbers.stream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .collect(Collectors.toList());

        List<Integer> parallel = numbers.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .collect(Collectors.toList());

        System.out.println("Sequential result: " + sequential);
        System.out.println("Parallel result: " + parallel);
        System.out.println("Equal results: "
                + sequential.equals(parallel));

        int seqSum = numbers.stream()
                .reduce(0, Integer::sum);
        int parSum = numbers.parallelStream()
                .reduce(0, Integer::sum);
        System.out.println("Sequential sum: " + seqSum);
        System.out.println("Parallel sum: " + parSum);

        boolean finalSequential = numbers.stream()
                .parallel()
                .sequential()
                .isParallel();
        System.out.println("Final sequential: " + finalSequential);

        System.out.println("Ordered output:");
        numbers.parallelStream()
                .forEachOrdered(System.out::println);

        Optional<Integer> first = numbers.parallelStream()
                .filter(n -> n > 2)
                .findFirst();
        System.out.println("First > 2: " + first.get());

        List<String> words = Arrays.asList(
                "ant", "ape", "bear", "bee", "boat");

        Map<Character, Long> counts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        s -> s.charAt(0),
                        Collectors.counting()));

        System.out.println("Counts: " + new TreeMap<>(counts));

        LinkedHashSet<String> ordered = new LinkedHashSet<>();
        ordered.add("A");
        ordered.add("B");
        ordered.add("C");
        List<String> setResult = ordered.parallelStream()
                .collect(Collectors.toList());
        System.out.println("LinkedHashSet order: " + setResult);

        List<String> source = new ArrayList<>(
                Arrays.asList("x", "y"));
        java.util.stream.Stream<String> pending = source.stream();
        source.add("z");
        System.out.println("Late binding: "
                + pending.collect(Collectors.toList()));
    }
}
```

Biên dịch và chạy:

```bash
javac CollectionStreamModesDemo.java
java CollectionStreamModesDemo
```

**Stdout dự kiến theo hợp đồng các Collection/Stream được dùng:**

```text
Sequential mode: false
Parallel mode: true
Sequential result: [16, 4, 36]
Parallel result: [16, 4, 36]
Equal results: true
Sequential sum: 21
Parallel sum: 21
Final sequential: false
Ordered output:
5
1
4
2
3
6
First > 2: 5
Counts: {a=2, b=3}
LinkedHashSet order: [A, B, C]
Late binding: [x, y, z]
```

**Giải thích:**

1. `numbers.stream()` đặt mode sequential; `numbers.parallelStream()` đặt mode parallel. `isParallel()` quan sát mode, không đo số worker.
2. Các phần tử chẵn trong List nguồn `[5,1,4,2,3,6]` là `4,2,6`. Sau `map(n -> n*n)`, cả hai pipeline tạo `[16,4,36]` theo encounter order.
3. `reduce(0,Integer::sum)` cho cùng tổng 21 nhờ identity/associative operation phù hợp.
4. `stream().parallel().sequential()` có mode cuối là sequential, nên `isParallel()` trả false.
5. `forEachOrdered` in 5,1,4,2,3,6 theo encounter order của List dù pipeline ở mode parallel. **Không suy ra callback trước đó đã được chạy cùng thứ tự**.
6. `findFirst` sau bộ lọc `n > 2` trả 5 vì 5 là phần tử đầu tiên đạt điều kiện trong List.
7. `groupingBy`/`counting` đếm hai từ bắt đầu bằng a và ba từ bắt đầu bằng b; bọc Map kết quả bằng `TreeMap` khi in để có thứ tự key xác định.
8. `LinkedHashSet` có encounter order theo thứ tự thêm A,B,C; collector `toList` của ordered stream giữ thứ tự đó.
9. `ArrayList` nguồn được thêm `"z"` trước terminal, và pipeline lấy các phần tử của Collection hiện tại theo quy tắc late-binding phù hợp, nên có `[x,y,z]`.

Chương trình cố ý **không in** thread ID, thứ tự `parallel forEach`, kết quả `findAny` hoặc thời gian thực thi, vì các giá trị đó không có một stdout bắt buộc cố định.

## 17. Một số tình huống ứng dụng

### 17.1. Tạo báo cáo tổng hợp đơn giản

```java
List<Integer> prices = Arrays.asList(10, 20, 30);
int total = prices.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 60
```

Cách sequential đủ rõ và thường phù hợp với dữ liệu nhỏ.

### 17.2. Tính toán số học trên số lượng lớn phần tử

```java
long energy = largeNumbers.parallelStream()
        .mapToLong(n -> (long) n * n)
        .sum();
```

Ví dụ này là **đoạn minh họa trong ngữ cảnh `largeNumbers` là `Collection<Integer>` phù hợp**, không phải file chạy độc lập. Nếu cần tránh tràn số, phải kiểm tra phạm vi dữ liệu và dùng kiểu/thuật toán số học tương ứng; `long` không bảo đảm không overflow với mọi đầu vào. Chọn parallel chỉ sau khi benchmark.

### 17.3. Xử lý nghiệp vụ cần thứ tự

```java
List<String> steps = Arrays.asList(
        "validate", "reserve", "charge");

// Nếu mỗi bước có side effect bắt buộc theo thứ tự,
// đừng dùng parallelStream().forEach(...).
for (String step : steps) {
    // Thực hiện bước nghiệp vụ có kiểm soát.
}
```

Một quy trình phụ thuộc trạng thái trước–sau thường phù hợp với sequential code rõ ràng hơn là cố parallelize và hy vọng giữ thứ tự.

### 17.4. Dữ liệu từ Map

```java
Map<String, Integer> quantities = new java.util.HashMap<>();
quantities.put("book", 2);
quantities.put("pen", 3);

int total = quantities.entrySet().stream()
        .mapToInt(entry -> entry.getValue())
        .sum(); // 5
```

Dùng `entrySet()` khi cần cả key và value; `values()` nếu chỉ cần giá trị. Không gọi `Map.stream()` vì `Map` không triển khai `Collection`.

## 18. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`parallelStream()` luôn nhanh hơn” | Splitting/scheduling/combining có overhead | Benchmark workload thật |
| “Parallel luôn dùng đúng N thread” | Implementation/scheduler không hứa số thread | Không phụ thuộc thread count |
| “Parallel là async” | Terminal thường hoàn tất trước khi trả kết quả | Dùng API async khi cần orchestration async |
| “Parallel làm List thread-safe” | Nguồn/callback vẫn phải non-interfering | Không sửa List trong traversal |
| “Dùng `ArrayList.add` trong parallel forEach là ổn” | Có data race | Dùng `collect` |
| “Map có `stream()` trực tiếp” | Map không extends Collection | Dùng `entrySet`/`keySet`/`values` |
| “Ordered result tức mapper gọi theo thứ tự” | Encounter order khác execution order | Không phụ thuộc callback scheduling |
| “`forEach` giữ thứ tự trên parallel List” | `forEach` không hứa encounter order | Dùng `forEachOrdered` khi cần side effects có thứ tự |
| “`unordered()` luôn tối ưu được” | Phụ thuộc pipeline và nguồn | Chỉ bỏ order khi nghiệp vụ cho phép |
| “`findAny` là phần tử đầu” | Có thể chọn bất kỳ phần tử phù hợp | Dùng `findFirst` nếu cần đầu |
| “`reduce` nào cũng parallel được” | Toán tử phải associative và identity đúng | Kiểm tra hợp đồng reduction |
| “`count()` buộc chạy `peek`” | Có thể bỏ qua xử lý phần tử | Không dùng `peek` làm logic bắt buộc |
| “Stream là collection copy” | Stream chỉ biểu diễn pipeline | Dùng terminal để materialize |
| “Một Stream có thể chạy terminal nhiều lần” | Stream single-use | Tạo Stream mới từ Collection |
| “`HashSet` giữ thứ tự như List” | HashSet không cam kết order | Chọn ordered source/sort nếu cần |
| “Collector `toList()` luôn là ArrayList mutable” | Không có bảo đảm implementation cụ thể | Dùng `toCollection(ArrayList::new)` khi cần |
| “Concurrency của source bảo vệ counter ngoài” | Thread safety của collection và callback khác nhau | Tránh shared mutable state |
| “`stream()` luôn chụp snapshot” | Source có thể late-binding | Copy dữ liệu rõ ràng khi cần snapshot |
| “Dữ liệu ít cũng nên parallel” | Overhead có thể lớn hơn work | Ưu tiên sequential |
| “Parallel phù hợp mặc định cho HTTP/database” | Blocking và tài nguyên chung cần điều phối | Dùng concurrency có giới hạn/phù hợp |

## 19. Checklist trước khi chọn chế độ xử lý

1. Nguồn có thực sự là `Collection<E>` chưa? Với `Map` đã chọn đúng view?
2. Collection có encounter order theo hợp đồng không? Thứ tự đó có quan trọng đối với kết quả?
3. Pipeline chỉ chứa callbacks stateless/non-interfering chưa?
4. Có shared mutable state hoặc thay đổi nguồn khi duyệt không? Nếu có, sửa thiết kế trước.
5. Terminal có phép tổng hợp associative/identity đúng để parallelize không?
6. Có cần short-circuit/ordered `limit`/`distinct`/`sorted` không? Chi phí parallel có thể lớn?
7. Nguồn có thể chia thành các phần tương đối cân bằng nhờ `Spliterator` không?
8. Công việc trên từng phần tử đủ nhiều để bù chi phí chia và ghép chưa?
9. Có đủ CPU rảnh và không ảnh hưởng workload song song khác không?
10. Có cần một **async job**, timeout, retry hoặc giới hạn I/O không? Parallel Stream không thay thế API orchestration.
11. Có đang dựa vào thứ tự `forEach` hoặc `findAny` không? Nếu có, xác định yêu cầu order rõ.
12. Có đang dùng `peek`/side effect để ghi dữ liệu nghiệp vụ không? Thay bằng collector/reduction.
13. Có dùng đúng phiên bản Java không? `Collection.stream/parallelStream` có từ Java 8; `Stream.toList()` là Java 16+, nên ví dụ tương thích Java 8 sử dụng `Collectors.toList()`.
14. Đã test sequential và parallel cho **cùng kết quả** trên các ca đầu vào phù hợp chưa?
15. Đã benchmark có warm-up, nhiều lần đo và kích thước đại diện chưa?
16. Có tạo Stream mới cho mỗi lượt duyệt thay vì reuse Stream đã tiêu thụ chưa?
17. Nếu nguồn mutable, các thay đổi xảy ra trước hay **trong** terminal? Chính sách nhất quán của nguồn đã rõ chưa?

**Kết luận:** `Collection.stream()` là điểm bắt đầu mặc định cho một pipeline **sequential**, dễ hiểu và đủ hiệu quả trong nhiều tình huống. `Collection.parallelStream()` dùng cùng mô hình pipeline nhưng yêu cầu **parallel execution mode** để có thể khai thác việc chia công việc. Chúng không copy nguồn, không tự đồng bộ hóa dữ liệu, không sửa lỗi shared state và không hứa hiệu năng cao hơn. Viết đúng nghĩa phép tính trước, giữ callbacks thuần/non-interfering, hiểu encounter order và kiểm thử/benchmark — đó mới là cách sử dụng Stream từ Collection an toàn và hiệu quả trên Java hiện đại.

## Tài liệu chuẩn

- Java SE 25 API, **`java.util.Collection`** — định nghĩa `stream()` và `parallelStream()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html
- Java SE 25, **`java.util.stream` package summary** — mô hình pipeline, mode sequential/parallel, nguồn, non-interference, side effects, reduction: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- Java SE 25 API, **`Stream`** — các intermediate/terminal operations và thứ tự: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Java SE 25 API, **`BaseStream`** — `isParallel()`, `parallel()`, `sequential()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html
- Java SE 25 API, **`Spliterator`** — đặc tính nguồn và khả năng phân chia: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html
- OpenJDK, **JMH — Java Microbenchmark Harness** (khi cần benchmark chuyên dụng): https://openjdk.org/projects/code-tools/jmh/
