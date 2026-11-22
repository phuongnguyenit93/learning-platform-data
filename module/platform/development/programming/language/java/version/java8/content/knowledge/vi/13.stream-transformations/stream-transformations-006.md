# sorted và thứ tự tự nhiên hoặc Comparator — biến đổi Stream trong Java 8

## 1. Mục tiêu và ý nghĩa

Trong Java 8, `Stream.sorted()` và `Stream.sorted(Comparator)` là **intermediate operations** để sắp xếp các phần tử của một Stream. Chúng trả về một **Stream mới mô tả thứ tự sắp xếp**, chứ không phải phương thức sửa thứ tự trực tiếp của `List` nguồn. Việc sắp xếp được thực thi khi pipeline được tiêu thụ bởi một **terminal operation** như `collect`, `toArray`, `forEachOrdered`.

Hai cách sắp xếp cần phân biệt:

- **Thứ tự tự nhiên (natural ordering)**: `stream.sorted()`. Dùng cách so sánh do `Comparable` của phần tử quy định, ví dụ `Integer`, `Long`, `String`, `LocalDate`.
- **Thứ tự theo Comparator**: `stream.sorted(comparator)`. Lập quy tắc so sánh tùy mục đích, ví dụ tên A–Z, điểm giảm dần, phòng ban tăng dần rồi điểm giảm dần, hoặc cho phép phần tử `null`.

Ví dụ ngắn:

```java
List<Integer> numbers = Arrays.asList(7, 2, 10, 2);

List<Integer> ascending = numbers.stream()
        .sorted()
        .collect(Collectors.toList()); // [2, 2, 7, 10]

List<Integer> descending = numbers.stream()
        .sorted(Comparator.reverseOrder())
        .collect(Collectors.toList()); // [10, 7, 2, 2]
```

Đây là đoạn minh họa bên trong một method; cần import `java.util.Arrays`, `java.util.List`, `java.util.Comparator`, `java.util.stream.Collectors`. `numbers` **vẫn là** `[7, 2, 10, 2]`; hai `List` kết quả được tạo qua terminal `collect`.

Sau bài học, bạn có thể:

1. Chọn giữa `sorted()` và `sorted(Comparator)`.
2. Dùng `Comparable` và `Comparator` đúng loại đối tượng.
3. Viết nhiều tiêu chí bằng `comparing`, `comparingInt`, `thenComparing`, `reversed`.
4. Xử lý `null`, String phân biệt hoa thường và so sánh theo ngôn ngữ khi cần.
5. Giải thích **tính ổn định (stable sort)**, **encounter order**, stream có/không có thứ tự và parallel.
6. Hiểu `sorted` là **stateful intermediate operation**, có chi phí thời gian/bộ nhớ khác `filter` hoặc `map`.
7. Tránh comparator sai contract, tràn số khi so sánh, nhầm giữa `distinct` và sắp xếp, nhầm về việc Stream sửa nguồn.
8. Kiểm thử chương trình chạy độc lập và biết đọc chính xác stdout.

**Special Note:** chỉ sử dụng những kiến thức vẫn áp dụng trong Java hiện đại; các phương thức `Stream.sorted`, `Comparator` từ Java 8 vẫn được hỗ trợ, không có cơ sở coi chúng đã lỗi thời.

## 2. Hai overload của Stream.sorted

Với `java.util.stream.Stream<T>`:

```java
Stream<T> sorted()
Stream<T> sorted(Comparator<? super T> comparator)
```

Đây là **chữ ký API minh họa**, không phải hai phương thức bạn cần tự định nghĩa.

| Phương thức | Quy tắc so sánh | Yêu cầu |
| --- | --- | --- |
| `sorted()` | Natural order qua `Comparable` | Những phần tử phải so sánh được với nhau theo natural ordering |
| `sorted(comparator)` | Dùng `Comparator<? super T>` bạn cung cấp | Comparator phải hợp lệ, phù hợp kiểu dữ liệu, non-interfering và stateless theo contract Stream |

Cả hai:

- **Không phải terminal operation**: gọi `sorted(...)` chỉ tạo stage.
- **Là stateful intermediate operation**: để quyết định phần tử nhỏ nhất/đúng thứ tự, việc triển khai sắp xếp thường phải **xem và đệm nhiều hoặc toàn bộ phần tử đầu vào**.
- **Trả về Stream**, không phải List hoặc array. Muốn kết quả lưu được, dùng `collect`/`toArray` phù hợp.
- **Có quy tắc stability**: với **ordered streams**, sắp xếp ổn định; với **unordered streams**, không có bảo đảm ổn định.

Ví dụ:

```java
List<String> words = Arrays.asList("pear", "Apple", "banana");

List<String> natural = words.stream()
        .sorted()
        .collect(Collectors.toList());
// [Apple, banana, pear]
```

`String` implements `Comparable<String>`, nên `sorted()` có thể dùng trực tiếp. Natural order của String **không tự động là thứ tự từ điển tiếng Việt**, cũng không tự bỏ qua hoa/thường.

## 3. Natural ordering với Comparable

`Comparable<T>` cung cấp phương thức:

```java
int compareTo(T other);
```

Quy ước giá trị trả về:

- Giá trị **âm**: đối tượng hiện tại đứng **trước** `other`.
- Bằng **0**: hai giá trị ngang nhau theo quy tắc thứ tự.
- Giá trị **dương**: đối tượng hiện tại đứng **sau** `other`.

Không có yêu cầu kết quả phải **đúng -1 hoặc 1**; chương trình chỉ nên kiểm tra **dấu**.

Các kiểu thông dụng như `Integer`, `Long`, `String`, `BigDecimal`, `LocalDate` có natural ordering tương ứng. Nếu một class nghiệp vụ có một thứ tự "mặc định" rõ ràng, nó có thể implement `Comparable<ThatClass>` để sử dụng với `sorted()`.

Ví dụ trong class minh họa:

```java
final class Ticket implements Comparable<Ticket> {
    private final int priority;
    private final String id;

    Ticket(int priority, String id) {
        this.priority = priority;
        this.id = id;
    }

    @Override
    public int compareTo(Ticket other) {
        int byPriority = Integer.compare(this.priority, other.priority);
        return byPriority != 0 ? byPriority : this.id.compareTo(other.id);
    }
}
```

Đây là **khai báo class** có thể được dùng cùng `Ticket` trong project. So sánh theo `priority` tăng dần, nếu trùng mới so sánh `id`. Việc có tie-breaker giúp tạo thứ tự rõ ràng ngay cả khi nhiều ticket cùng độ ưu tiên. Nếu `id` có thể null, ví dụ cần thêm quy tắc null; đoạn trên giả định `id` không null.

### Khi nào sorted() có thể lỗi?

```java
Stream.of(new Object(), new Object())
        .sorted()
        .toArray();
```

Đây là snippet **cố ý gây lỗi**. `Object` không implement `Comparable`; với hai object đó, terminal `toArray` khiến việc so sánh xảy ra và có thể ném `ClassCastException`. Lỗi có thể xuất hiện **khi terminal operation được thực thi**, không nhất thiết lúc vừa gọi `sorted()`.

Một class `Comparable` được khai báo không hợp lệ hoặc hỗn hợp những kiểu không so sánh lẫn nhau cũng có thể gây lỗi. Ví dụ không nên tạo `Stream<Object>` gồm `Integer` và `String` rồi mong natural sort tự biết quy tắc chuyển đổi kiểu.

**Không dùng `sorted()` cho đối tượng nghiệp vụ không có natural order rõ ràng**; hãy đưa `Comparator` cụ thể vào pipeline.

## 4. Comparator: định nghĩa thứ tự ngay tại nơi sử dụng

`java.util.Comparator<T>` là functional interface:

```java
int compare(T left, T right);
```

Một Comparator có thể được khai báo bằng lambda, method reference, hoặc các factory methods hiện đại:

```java
Comparator<String> byLength =
        (a, b) -> Integer.compare(a.length(), b.length());

List<String> result = Stream.of("pear", "kiwi", "a", "banana")
        .sorted(byLength)
        .collect(Collectors.toList());
// [a, pear, kiwi, banana]
```

Với nguồn `Stream.of("pear", "kiwi", "a", "banana")`, `pear` và `kiwi` cùng độ dài 4; kết quả của một **ordered stream** bảo toàn thứ tự tương đối giữa chúng. Đây là ví dụ minh họa trong method với import `Comparator`, `List`, `Stream`, `Collectors`.

Cách dùng API factory ngắn gọn hơn:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
```

Không cần tạo class riêng chỉ để so sánh độ dài nếu dùng quy tắc này ở một chỗ.

**Ưu điểm:** cùng một loại đối tượng có thể được sắp xếp theo nhiều tiêu chí mà **không phải thay đổi class hoặc `compareTo` tự nhiên**.

## 5. Comparator.comparing, comparingInt, thenComparing, reversed

### 5.1. `comparing` — so sánh theo thuộc tính

Giả sử class `Employee` có getters `getName()`, `getTeam()`, `getScore()`:

```java
Comparator<Employee> byName =
        Comparator.comparing(Employee::getName);
```

Nếu `getName()` trả `String`, factory này dùng natural ordering của String cho thuộc tính. Nếu key có thể null, cần policy null riêng; `Comparator.comparing` không tự bảo đảm xử lý null.

### 5.2. `comparingInt`, `comparingLong`, `comparingDouble`

Khi thuộc tính là số primitive, có thể tránh boxing:

```java
Comparator<Employee> byScore =
        Comparator.comparingInt(Employee::getScore);
```

Tương tự, `comparingLong` và `comparingDouble` dành cho các key thuộc kiểu `long` và `double`. Cần nhớ `double` có những quy tắc đặc biệt với NaN và signed zero theo `Double.compare`; nếu dữ liệu khoa học cần policy riêng về giá trị đặc biệt, hãy định nghĩa rõ.

### 5.3. `reversed()` — đảo thứ tự

```java
Comparator<Employee> scoreDescending =
        Comparator.comparingInt(Employee::getScore).reversed();
```

Các nhân viên có điểm lớn hơn đứng trước.

**Cảnh báo về thứ tự thao tác `reversed`:**

```java
Comparator<Employee> wholeOrderReversed =
        Comparator.comparing(Employee::getTeam)
                .thenComparingInt(Employee::getScore)
                .reversed();
```

Đoạn này đảo **toàn bộ Comparator đã ghép**, tức vừa đảo team vừa đảo score. Nếu muốn **team tăng nhưng score giảm**, phải đảo chỉ **Comparator của score** rồi ghép vào:

```java
Comparator<Employee> teamAscScoreDesc =
        Comparator.comparing(Employee::getTeam)
                .thenComparing(
                        Comparator.comparingInt(Employee::getScore).reversed());
```

Thứ tự đặt `reversed` không chỉ khác về style, mà **khác kết quả**.

### 5.4. `thenComparing` — nhiều tiêu chí

```java
Comparator<Employee> order =
        Comparator.comparing(Employee::getTeam)
                .thenComparing(
                        Comparator.comparingInt(Employee::getScore).reversed())
                .thenComparing(Employee::getName);
```

Diễn giải từng tầng:

1. So sánh `team` tăng dần.
2. Nếu `team` bằng nhau, so sánh `score` **giảm dần**.
3. Nếu cả `team` và `score` bằng nhau, dùng `name` tăng dần.

`thenComparing` chỉ xem tiêu chí tiếp theo khi tiêu chí trước đó trả về **0**. Do đó chuỗi `thenComparing` là cách diễn đạt **thứ tự ưu tiên so sánh** minh bạch.

Nếu cần tie-breaker không có khả năng trùng nhau trong miền dữ liệu, có thể thêm `thenComparing(Employee::getId)` theo business contract. Nếu comparator trả 0 cho hai bản ghi khác nhau, `sorted` vẫn sắp xếp được, nhưng những API như `TreeSet` có semantics khác cần lưu ý (mục 12).

## 6. Thứ tự tự nhiên, đảo chiều và sorting theo chữ

### Số

```java
List<Integer> sorted = Stream.of(10, 2, -1, 2)
        .sorted()
        .collect(Collectors.toList());
// [-1, 2, 2, 10]
```

`Integer.compareTo` so sánh **giá trị số học**, không so sánh chữ số trong dạng String.

### String và chữ hoa/thường

```java
List<String> values = Arrays.asList("pear", "Apple", "banana");
List<String> natural = values.stream()
        .sorted()
        .collect(Collectors.toList());
// [Apple, banana, pear]
```

Natural ordering của String so sánh các giá trị theo quy tắc của `String.compareTo` (dựa trên thứ tự các ký tự UTF-16), vì vậy chữ hoa có thể đứng trước chữ thường. Nó **không** cung cấp collation tự nhiên theo văn hóa hoặc ngôn ngữ.

Bỏ qua khác biệt hoa/thường theo comparator có sẵn:

```java
List<String> names = Arrays.asList("bob", "Alice", "alice", "BOB", "carol");

List<String> sorted = names.stream()
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .collect(Collectors.toList());
// [Alice, alice, bob, BOB, carol]
```

`Alice` và `alice` so sánh ngang nhau theo `CASE_INSENSITIVE_ORDER`; `bob` và `BOB` cũng vậy. Vì nguồn là **List có encounter order**, stable sort giữ thứ tự tương đối trong từng nhóm được comparator xem là bằng nhau.

**Không đồng nghĩa với bỏ dấu hoặc collation tiếng Việt.** Nếu cần sắp xếp tên theo ngôn ngữ, hãy xem `java.text.Collator` cùng `Locale` thích hợp, kiểm thử cách xử lý dấu và hoa/thường với dữ liệu thật. Ví dụ:

```java
Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
List<String> ordered = names.stream()
        .sorted(collator)
        .collect(Collectors.toList());
```

Đây là snippet trong method với import `java.text.Collator`, `java.util.Locale` và các loại collection/stream tương ứng. Thứ tự cụ thể phụ thuộc collation rules/provider/runtime; **không bịa một stdout cố định cho tiếng Việt** khi chưa kiểm thử môi trường và cấu hình locale. `Collator` có thể cấu hình độ nhạy, và một instance cấu hình mutable không nên bị thay đổi trong lúc comparator đang được stream dùng.

## 7. Null trong sorted: lựa chọn chính sách rõ ràng

`sorted()` theo natural ordering thông thường **không hỗ trợ `null` như một phần tử có thể so sánh**; khi thực sự cần so sánh `null` với String/Integer, có thể ném `NullPointerException`.

Ví dụ phản ví dụ:

```java
Stream.of("a", null, "b")
        .sorted()
        .toArray(); // Lỗi với natural ordering khi so sánh null.
```

Đây là snippet **cố ý không hợp lệ về dữ liệu đầu vào**.

Nếu `null` là giá trị hợp lệ trong nghiệp vụ, hãy định nghĩa rõ null đứng đầu hay cuối:

```java
Comparator<String> nullLast =
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER);

List<String> result = Stream.of("pear", null, "apple", null, "banana")
        .sorted(nullLast)
        .collect(Collectors.toList());
// [apple, banana, pear, null, null]
```

`Comparator.nullsFirst(otherComparator)` làm `null` đứng đầu, `nullsLast` làm `null` đứng cuối, theo thứ tự của comparator bên trong cho các phần tử khác null.

### Nếu bản thân object không null nhưng key null

Ví dụ `Employee` luôn tồn tại, nhưng `employee.getTeam()` có thể trả null:

```java
Comparator<Employee> byTeamNullable =
        Comparator.comparing(
                Employee::getTeam,
                Comparator.nullsLast(Comparator.naturalOrder()));
```

Điều này xử lý **giá trị key `team` null**, không phải **một phần tử Employee null**. Nếu danh sách có thể chứa `null Employee`, phải bọc **comparator ngoài cùng** bằng `Comparator.nullsFirst(...)` hoặc `nullsLast(...)`.

### reversed() và null position

Nếu viết `Comparator.nullsLast(byName).reversed()`, bạn đảo **cả quy tắc null**, nên null có thể chuyển lên trước. Muốn giữ null cuối nhưng đảo thứ tự đối tượng không null, viết `Comparator.nullsLast(byName.reversed())`. Đây là khác biệt quan trọng khi nhiều tiêu chí và null policy kết hợp.

## 8. Stability và encounter order

Javadoc `Stream.sorted` quy định:

- Với **ordered stream**, `sorted()` hoặc `sorted(comparator)` là **stable**.
- Với **unordered stream**, **không có bảo đảm ổn định**.

**Stable sort** nghĩa là: nếu Comparator coi hai phần tử có thứ tự bằng nhau (`compare(a,b)==0`), thì trong **ordered stream**, chúng giữ nguyên thứ tự tương đối như ở nguồn.

Ví dụ một ordered stream từ `List`:

```java
List<Entry> entries = Arrays.asList(
        new Entry("x", 2),
        new Entry("a", 1),
        new Entry("y", 2),
        new Entry("b", 1),
        new Entry("z", 2));

List<String> sorted = entries.stream()
        .sorted(Comparator.comparingInt(e -> e.priority))
        .map(e -> e.id)
        .collect(Collectors.toList());
// [a, b, x, y, z]
```

Đây là snippet minh họa có class `Entry` gồm `String id` và `int priority` (được định nghĩa trong chương trình hoàn chỉnh ở mục 15). Các phần tử priority 1 là `a,b`, priority 2 là `x,y,z`. Comparator chỉ so sánh priority nhưng stable sort giữ thứ tự trong từng nhóm.

### Nếu source không có encounter order?

Một stream từ một số nguồn như `HashSet` có thể **không có encounter order xác định**. `sorted` vẫn định nghĩa thứ tự theo Comparator cho các phần tử khác nhau, nhưng **không bảo đảm** thứ tự các phần tử comparator xem là ngang nhau. Nếu cần kết quả hoàn toàn xác định:

1. Dùng một **nguồn có encounter order** phù hợp; hoặc
2. Thêm **tie-breaker** đủ để phân biệt các bản ghi theo business contract.

```java
Comparator<Entry> deterministic =
        Comparator.comparingInt((Entry e) -> e.priority)
                .thenComparing(e -> e.id);
```

### Parallel có làm mất stable sort?

Không thể nói "parallel stream luôn làm sorted không ổn định". Với **ordered stream**, `sorted` vẫn có bảo đảm stable **ngay cả khi pipeline chạy parallel**. Với **unordered stream**, không có bảo đảm ổn định dù chạy sequential hay parallel.

**Không nhầm thứ tự kết quả với thứ tự side effects:** `parallelStream().sorted(...).forEach(System.out::println)` không hứa thứ tự in. `forEach` không cam kết tôn trọng encounter order trong parallel. Muốn một trình tự đầu ra theo thứ tự, dùng `collect(Collectors.toList())` hoặc `forEachOrdered` khi phù hợp với yêu cầu.

## 9. sorted là stateful intermediate operation, không phải thao tác miễn phí

`filter` và `map` là **stateless intermediate operations**: chúng có thể xử lý từng phần tử mà không cần giữ toàn bộ đầu vào để quyết định phần tử kế tiếp. `sorted` thì khác: để biết phần tử nào nhỏ nhất, thông thường **phải quan sát toàn bộ dữ liệu đầu vào** (hoặc một tập đã được giới hạn trước).

Hệ quả:

- `sorted` thường có chi phí xấp xỉ **O(n log n)** cho n phần tử với các thuật toán sort so sánh và có thể cần **O(n)** bộ nhớ đệm. Con số thực tế phụ thuộc implementation, dữ liệu, comparator và parallelism.
- Nếu comparator tính toán đắt tiền (đọc file, truy vấn database, gọi API), sắp xếp trở nên rất chậm và có thể gây side effects khó đoán. Comparator nên **stateless, non-interfering**, không sửa nguồn stream.
- Với **nguồn vô hạn/không giới hạn**, `sorted()` rồi `limit(k)` thường **không thể tạo kết quả** vì sorting cần biết toàn bộ đầu vào. `limit(k)` **trước** `sorted()` giới hạn tập cần sắp xếp; thứ tự hai operations thay đổi ý nghĩa.

Ví dụ:

```java
List<Integer> firstFiveSorted = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .sorted(Comparator.reverseOrder())
        .collect(Collectors.toList());
// [5, 4, 3, 2, 1]
```

Đây là snippet trong method, không có nguồn vô hạn nào phải được duyệt hết: `limit(5)` đứng **trước** `sorted`.

### sorted rồi limit khác limit rồi sorted

Giả sử nguồn `[8,3,5,1,7]`:

```java
List<Integer> smallestTwo = Stream.of(8, 3, 5, 1, 7)
        .sorted()
        .limit(2)
        .collect(Collectors.toList());
// [1, 3]

List<Integer> firstTwoSorted = Stream.of(8, 3, 5, 1, 7)
        .limit(2)
        .sorted()
        .collect(Collectors.toList());
// [3, 8]
```

- `sorted().limit(2)`: lấy hai phần tử nhỏ nhất của **toàn bộ nguồn hữu hạn**.
- `limit(2).sorted()`: chỉ sắp xếp **hai phần tử đầu tiên** được nguồn phát ra.

Không thay đổi thứ tự các operations để "tối ưu" mà bỏ qua semantics nghiệp vụ.

### Lazy và tối ưu terminal

Vì `sorted` là intermediate, gọi `stream.sorted()` **chưa làm sắp xếp**. Thêm nữa, Stream implementation có thể tối ưu loại bỏ một stage **không cần thiết cho kết quả terminal**. Ví dụ `sorted().count()` không phải cách đáng tin để buộc Comparator được gọi hay để buộc tất cả side effects trong comparator/peek thực thi.

**Đừng viết comparator có nhiệm vụ ghi audit, đếm, cập nhật database** rồi dựa vào số lần `compare` được gọi: thuật toán sort không cam kết số lượt compare và các tối ưu có thể thay đổi việc thực thi.

## 10. Primitive streams: IntStream, LongStream, DoubleStream

Các primitive specializations của Stream trong Java 8 có:

```java
IntStream.sorted()
LongStream.sorted()
DoubleStream.sorted()
```

Chúng sắp xếp **natural numeric order** cho từng kiểu primitive và **không có overload nhận Comparator** giống `Stream<T>.sorted(comparator)`.

Ví dụ:

```java
int[] numbers = IntStream.of(9, 4, 2).sorted().toArray();
// [2, 4, 9]
```

Muốn sắp xếp `IntStream` theo thứ tự giảm dần bằng Comparator, có thể chuyển sang `Stream<Integer>`:

```java
List<Integer> reversed = IntStream.of(9, 4, 2)
        .boxed()
        .sorted(Comparator.reverseOrder())
        .collect(Collectors.toList());
// [9, 4, 2]
```

`boxed()` tạo wrapper objects, có chi phí boxing/memory. Với dữ liệu rất lớn, cân nhắc yêu cầu thực tế: sort tăng bằng primitive trước, rồi duyệt mảng ngược nếu chỉ cần trình tự giảm; đừng boxing mọi số nếu không cần.

**Lưu ý về `DoubleStream.sorted()`:** thứ tự được định nghĩa theo `Double.compare`, gồm các quy tắc riêng với `NaN`, `-0.0` và `+0.0`. Nếu domain yêu cầu xử lý NaN khác (chẳng hạn bỏ NaN trước khi sort), lọc hoặc mô tả policy rõ ràng thay vì kỳ vọng so sánh dấu phẩy động giống số thực toán học hoàn toàn.

## 11. sorted không sửa List nguồn; khác List.sort

So sánh hai cách sắp xếp:

```java
List<Integer> source = new ArrayList<>(Arrays.asList(3, 1, 2));

List<Integer> copySorted = source.stream()
        .sorted()
        .collect(Collectors.toList());
// source     = [3, 1, 2]
// copySorted = [1, 2, 3]

source.sort(Comparator.naturalOrder());
// source     = [1, 2, 3]
```

Đây là snippet trong method với các import phù hợp.

- `source.stream().sorted()` **không tự sắp xếp lại source**. `collect` tạo một collection kết quả khác.
- `source.sort(comparator)` là phương thức trên `List` để **sắp xếp chính List đó**, nếu List hỗ trợ operation.
- `Collections.sort(list)` và `Arrays.sort(array)` là các lựa chọn cho sorting cấu trúc lưu trữ cụ thể; đừng nhầm với semantics của Stream pipeline.

**Shallow semantics:** nếu Stream chứa các object mutable, `sorted().collect(toList())` thường tạo List mới nhưng **không deep copy các phần tử**. Hai List có thể tham chiếu cùng các object. Comparator không nên tự sửa object trong lúc so sánh vì có thể phá tính nhất quán của thứ tự.

**Không bảo đảm kiểu List cụ thể:** `Collectors.toList()` không cam kết một implementation/mutability cụ thể. Nếu cần `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`. `Stream.toList()` được giới thiệu từ **Java 16** và trả List unmodifiable; không dùng nó trong code cần biên dịch với Java 8.

## 12. Contract của Comparator: đúng dấu, nhất quán và không overflow

Comparator không chỉ là một lambda trả kết quả bất kỳ. Để sorting có ý nghĩa, các phép so sánh phải tuân thủ **contract**:

1. **Antisymmetry theo dấu:** dấu của `compare(a,b)` phải đối ngược dấu của `compare(b,a)`.
2. **Transitivity:** nếu a đứng trước b và b đứng trước c, thì a phải đứng trước c theo cùng thứ tự.
3. **Nhất quán khi comparator trả 0:** nếu `compare(a,b)==0`, hai phần tử phải có quan hệ so sánh nhất quán với phần tử khác.
4. **Không thay đổi tiêu chí trong một lần sort:** Comparator nên stateless, không phụ thuộc biến mutable thay đổi giữa các lần compare, không can thiệp source.

### Tránh tràn số khi so sánh

Không nên:

```java
Comparator<Employee> byScoreBad =
        (a, b) -> a.getScore() - b.getScore();
```

Nếu các score có thể gần `Integer.MIN_VALUE`/`MAX_VALUE`, hiệu có thể **overflow** và trả dấu sai. Chọn cách an toàn:

```java
Comparator<Employee> byScore =
        Comparator.comparingInt(Employee::getScore);

// Hoặc:
Comparator<Employee> byScoreExplicit =
        (a, b) -> Integer.compare(a.getScore(), b.getScore());
```

Với `long`, dùng `Long.compare` hoặc `comparingLong`; với `double`, dùng `Double.compare` hoặc `comparingDouble`.

### Comparator nhất quán với equals: khi nào quan trọng?

`Comparator.compare(a,b)==0` **không bắt buộc** nghĩa là `a.equals(b)`. Ví dụ nếu chỉ so sánh Employee theo score, hai nhân viên khác nhau có cùng score sẽ so sánh bằng nhau.

- **Stream.sorted** vẫn giữ được cả hai phần tử; nó **không tự xóa phần tử trùng thứ tự**.
- **Stream.distinct()** dựa trên `Object.equals`, không dùng comparator như quy tắc khử trùng.
- **TreeSet/TreeMap** dùng thứ tự Comparator làm tiêu chí phân biệt key; comparator coi hai key ngang nhau có thể dẫn đến hành vi khác với ý định nếu không nhất quán với `equals`.

Nếu business requirement là có thứ tự hoàn toàn xác định, thêm tie-breaker như một mã định danh phù hợp. Nếu business requirement là **khử trùng theo key**, cần một bước/grouping riêng với semantics được xác định, không kỳ vọng `sorted(comparator)` tự làm dedup.

### Comparator luôn trả 0 hoặc so sánh theo chu kỳ

Một Comparator sai có thể làm sorting cho kết quả khó đoán hoặc ném `IllegalArgumentException` ở một số implementation/đầu vào nếu vi phạm general contract. Đừng cố kiểm soát bằng việc "bắt exception rồi tiếp tục"; hãy sửa quy tắc so sánh.

**Kiểm thử tốt:** chọn ba giá trị a,b,c và xác nhận tính đối xứng theo dấu, tính bắc cầu và tie-breakers, bao gồm `null` và các cực trị số khi chúng hợp lệ với domain.

## 13. Top-k, distinct, ordering và hiệu năng

### Chọn k phần tử nhỏ nhất/lớn nhất

```java
List<Integer> smallest = numbers.stream()
        .sorted()
        .limit(3)
        .collect(Collectors.toList());

List<Integer> largest = numbers.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .collect(Collectors.toList());
```

Đây là snippets trong method có `numbers` là collection hữu hạn. Các cách này dễ đọc nhưng để sắp xếp toàn bộ n phần tử thường cần chi phí sort đáng kể.

Nếu chỉ cần **một** phần tử lớn nhất/nhỏ nhất, `max(comparator)` hoặc `min(comparator)` là terminal reduction phù hợp hơn so với sort toàn bộ rồi lấy phần tử đầu:

```java
Optional<Employee> top = employees.stream()
        .max(Comparator.comparingInt(Employee::getScore));
```

`max` trả `Optional` vì stream có thể rỗng. Khi nhiều phần tử cùng maximum, đừng đưa ra bảo đảm tùy tiện về phần tử được chọn nếu tie-breaker không xác định rõ nhu cầu.

Nếu tập dữ liệu cực lớn mà chỉ cần top-k rất nhỏ, cân nhắc thuật toán bounded heap/priority queue với độ phức tạp thích hợp, nhưng **đừng tối ưu sớm** khi tập dữ liệu nhỏ và pipeline dễ đọc là mục tiêu.

### sorted() rồi distinct() không đồng nghĩa sort khử trùng

```java
List<Integer> result = Stream.of(3, 1, 3, 2)
        .sorted()
        .distinct()
        .collect(Collectors.toList());
// [1, 2, 3]
```

`distinct` loại giá trị trùng theo `equals`; `sorted` chỉ xác định thứ tự, không tự xóa bản ghi. Đảo thứ tự `distinct`/`sorted` trên số có thể giữ kết quả cuối như nhau trong ví dụ, nhưng với object, order/identity và hiệu năng có thể khác theo pipeline; phải xem contract từng operation.

### sorted và các source vô hạn

Không viết `Stream.generate(...).sorted().limit(5)` rồi mong sort biết "năm số đầu". Sort cần đầu vào hữu hạn để biết thứ tự tổng thể. Nếu muốn sort một **mẫu gồm năm phần tử**, đặt `limit(5).sorted()` — và phải hiểu đây là **năm phần tử được lấy trước**, không phải năm phần tử nhỏ nhất của một nguồn vô hạn bất định.

## 14. Những lỗi thực tế và cách sửa

| Nhầm lẫn hoặc lỗi | Hướng xử lý đúng |
| --- | --- |
| Dùng `sorted()` cho class không có `Comparable` | Cung cấp `Comparator` hoặc natural order hợp lệ |
| Nghĩ `sorted()` sửa luôn `List` nguồn | Dùng `List.sort` nếu muốn sort in-place; dùng Stream.sorted cho pipeline |
| Nghĩ `sorted` đã chạy trước terminal | Intermediate operations lazy; cần terminal để quan sát kết quả |
| Dùng `Comparator.comparing(Employee::getScore)` rồi tin không có boxing | Nếu key là primitive, chọn `comparingInt` |
| Dùng `a.score - b.score` | Có thể overflow; dùng `Integer.compare` |
| Đặt `reversed()` cuối chuỗi nhiều tiêu chí mà chỉ muốn đảo một key | Đảo comparator của key đó **trước** khi `thenComparing` |
| Quên `null` trong phần tử hoặc key | Dùng `nullsFirst/nullsLast` đúng cấp, hoặc lọc/validate |
| Mong natural order String giống từ điển tiếng Việt | Cân nhắc `Collator` với `Locale` cụ thể |
| Mong `CASE_INSENSITIVE_ORDER` phân biệt strings chỉ khác case | Nó có thể coi các string khác nhau ngang thứ tự; thêm tie-breaker nếu cần |
| Tưởng Stream.sorted luôn stable với mọi nguồn | Stable khi **ordered**; unordered không có bảo đảm stability |
| Nghĩ parallel `forEach` vẫn in đúng thứ tự đã sort | Dùng `forEachOrdered` hoặc `collect` |
| Dùng `sorted().limit(k)` trên nguồn vô hạn | Không kết thúc; giới hạn đầu vào trước sort nếu ý định là sort một mẫu |
| Dùng `sorted().count()` để kích hoạt side effects trong comparator | Không đảm bảo; đừng đưa side effects vào comparator |
| Muốn top-1 nhưng sort toàn bộ | `min` hoặc `max` thường phù hợp hơn |
| Mong `sorted(comparator)` xóa duplicate | Dùng `distinct` hoặc grouping theo key được xác định |
| Dùng Comparator không bắc cầu | Vi phạm contract; sửa logic, viết test |
| Dùng `IntStream.sorted(Comparator)` | Primitive streams không có overload đó; chuyển `boxed()` hoặc cách khác |
| Nghĩ `Collectors.toList()` luôn là mutable ArrayList | Không cam kết; dùng `toCollection(ArrayList::new)` nếu cần |

## 15. Chương trình Java hoàn chỉnh, có kết quả kiểm thử

Tạo file **`StreamSortedDemo.java`**. Chương trình xác minh natural order, reverse order, String, Comparator nhiều tiêu chí, stable sorting, null policy, primitive stream và lỗi khi dữ liệu không so sánh được.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamSortedDemo {
    static final class Employee {
        final String name;
        final String team;
        final int score;

        Employee(String name, String team, int score) {
            this.name = name;
            this.team = team;
            this.score = score;
        }

        String getName() { return name; }
        String getTeam() { return team; }
        int getScore() { return score; }

        @Override public String toString() {
            return name + "(" + team + "," + score + ")";
        }
    }

    static final class Entry {
        final String id;
        final int priority;
        Entry(String id, int priority) {
            this.id = id;
            this.priority = priority;
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(3, 1, 10, 2, 2);
        System.out.println("natural=" + numbers.stream().sorted()
                .collect(Collectors.toList()));
        System.out.println("descending=" + numbers.stream()
                .sorted(Comparator.reverseOrder()).collect(Collectors.toList()));
        System.out.println("source=" + numbers);

        List<String> words = Arrays.asList("pear", "Apple", "banana");
        System.out.println("wordNatural=" + words.stream().sorted()
                .collect(Collectors.toList()));

        List<String> mixed = Arrays.asList("bob", "Alice", "alice", "BOB", "carol");
        System.out.println("caseInsensitive=" + mixed.stream()
                .sorted(String.CASE_INSENSITIVE_ORDER)
                .collect(Collectors.toList()));

        List<Employee> employees = Arrays.asList(
                new Employee("Mai", "Dev", 90),
                new Employee("An", "QA", 90),
                new Employee("Binh", "Dev", 70),
                new Employee("Lan", "Dev", 90),
                new Employee("Chi", "QA", 70),
                new Employee("Hoa", "QA", 90));

        Comparator<Employee> byTeamScoreName =
                Comparator.comparing(Employee::getTeam)
                        .thenComparing(Comparator.comparingInt(Employee::getScore)
                                .reversed())
                        .thenComparing(Employee::getName);

        System.out.println("employees=" + employees.stream()
                .sorted(byTeamScoreName).collect(Collectors.toList()));

        List<Entry> entries = Arrays.asList(
                new Entry("x", 2), new Entry("a", 1),
                new Entry("y", 2), new Entry("b", 1),
                new Entry("z", 2));
        System.out.println("stable=" + entries.stream()
                .sorted(Comparator.comparingInt(e -> e.priority))
                .map(e -> e.id).collect(Collectors.toList()));

        List<String> nullable = Arrays.asList("pear", null, "apple", null, "banana");
        System.out.println("nullsLast=" + nullable.stream()
                .sorted(Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER))
                .collect(Collectors.toList()));

        System.out.println("primitive=" + Arrays.toString(
                IntStream.of(9, 4, 2).sorted().toArray()));

        try {
            Stream.of(new Object(), new Object()).sorted().toArray();
        } catch (ClassCastException expected) {
            System.out.println("nonComparable=rejected");
        }

        try {
            Stream.of("a", null, "b").sorted().toArray();
        } catch (NullPointerException expected) {
            System.out.println("naturalNull=rejected");
        }
    }
}
```

Chạy trên **JDK 17+** (code sử dụng những API đã có từ Java 8):

```bash
javac StreamSortedDemo.java
java StreamSortedDemo
```

**Stdout chính xác của chương trình trên OpenJDK 24:**

```text
natural=[1, 2, 2, 3, 10]
descending=[10, 3, 2, 2, 1]
source=[3, 1, 10, 2, 2]
wordNatural=[Apple, banana, pear]
caseInsensitive=[Alice, alice, bob, BOB, carol]
employees=[Lan(Dev,90), Mai(Dev,90), Binh(Dev,70), An(QA,90), Hoa(QA,90), Chi(QA,70)]
stable=[a, b, x, y, z]
nullsLast=[apple, banana, pear, null, null]
primitive=[2, 4, 9]
nonComparable=rejected
naturalNull=rejected
```

### Phân tích đầu ra

1. **`natural=[1,2,2,3,10]`**: Integer có natural order tăng dần; phần tử trùng vẫn được giữ lại.
2. **`descending=[10,3,2,2,1]`**: `Comparator.reverseOrder()` đảo thứ tự tự nhiên.
3. **`source=[3,1,10,2,2]`**: hai pipeline sorted/collect **không chỉnh sửa List nguồn**.
4. **`wordNatural=[Apple,banana,pear]`**: String natural order phân biệt hoa/thường theo quy tắc `String.compareTo`.
5. **`caseInsensitive=[Alice,alice,bob,BOB,carol]`**: bỏ qua hoa/thường khi so sánh; vì nguồn ordered và sort stable nên giữ thứ tự trong từng nhóm ngang nhau.
6. **`employees=...`**: nhóm Dev đứng trước QA; trong nhóm score 90 đứng trước 70; khi score trùng thì sắp tên tăng dần.
7. **`stable=[a,b,x,y,z]`**: Entry chỉ so sánh priority nhưng giữ encounter order trong nhóm bằng nhau.
8. **`nullsLast=[apple,banana,pear,null,null]`**: Comparator null policy đưa null xuống cuối và sắp phần tử không null không phân biệt hoa/thường.
9. **`primitive=[2,4,9]`**: `IntStream.sorted()` sắp xếp natural order mà không boxing.
10. **`nonComparable=rejected`**: natural sort trên những Object không Comparable ném `ClassCastException`.
11. **`naturalNull=rejected`**: natural sort gặp null khi so sánh gây `NullPointerException`.

Hai ví dụ lỗi cuối được **bắt ngoại lệ có chủ đích**, nên chương trình vẫn chạy thành công. Không dùng exception như cơ chế xử lý một thứ tự so sánh sai trong production; hãy validate đầu vào và chọn Comparator đúng.

## 16. Bài tập tự kiểm tra có đáp án

**Câu 1.** `sorted()` dùng quy tắc nào?  
**Đáp án:** Natural ordering từ `Comparable` của phần tử.

**Câu 2.** `sorted(Comparator.comparingInt(User::getAge))` làm gì?  
Sắp xếp theo `age` tăng dần mà không cần implement `Comparable<User>` (giả sử `User` có `getAge(): int`).

**Câu 3.** `sorted` có sửa thứ tự `List` nguồn?  
**Không.** `List.sort` là cách sắp xếp chính List nếu đó là mục tiêu.

**Câu 4.** Vì sao `Stream.of(1,2,3).sorted()` chưa chạy sort ngay?  
Vì sorted là **intermediate operation lazy**; terminal mới đòi kết quả.

**Câu 5.** Có thể dùng `sorted()` trên một object không Comparable không?  
Không an toàn; lúc cần so sánh sẽ gây `ClassCastException`. Dùng Comparator.

**Câu 6.** Muốn team A–Z, score giảm, name A–Z, đặt `reversed` ở đâu?  
Đảo **Comparator score** trước khi ghép với `thenComparing`, không đảo cả chuỗi cuối cùng.

**Câu 7.** `Comparator.comparingInt` khác `Comparator.comparing` ở điểm gì?  
Trích xuất **int primitive key**, tránh boxing wrapper trong phép so sánh key.

**Câu 8.** `sorted(Comparator.nullsLast(...))` dùng khi nào?  
Khi phần tử có thể null và business policy muốn null đứng cuối.

**Câu 9.** Một field key có thể null, nhưng object không null, xử lý thế nào?  
`Comparator.comparing(getter, Comparator.nullsLast(keyComparator))`.

**Câu 10.** Hai phần tử khác nhau mà Comparator trả 0 sẽ mất một phần tử sau `sorted`?  
**Không.** `sorted` không deduplicate; ordered stable sort còn giữ encounter order giữa chúng.

**Câu 11.** Tính ổn định của sorted được bảo đảm với stream nào?  
**Ordered streams**. Unordered streams không có stability guarantee.

**Câu 12.** `parallelStream().sorted().forEach(print)` có in đúng thứ tự sort?  
**Không bảo đảm** vì parallel `forEach` không giữ encounter order. Dùng `forEachOrdered` hoặc materialize kết quả.

**Câu 13.** `Stream.generate(...).sorted().limit(3)` có dễ hoàn tất?  
**Không.** Sorting nguồn vô hạn đòi biết toàn bộ đầu vào. Nếu muốn sort ba mẫu đầu, đặt `limit(3)` trước `sorted()`.

**Câu 14.** `IntStream.sorted(Comparator.reverseOrder())` có hợp lệ?  
**Không.** Primitive stream chỉ có `sorted()` tự nhiên; có thể `boxed()` trước.

**Câu 15.** Có nên so sánh `int` bằng phép trừ `a-b`?  
**Không nên**, có nguy cơ overflow. Dùng `Integer.compare` hoặc `comparingInt`.

**Câu 16.** `sorted(comparator)` và `distinct()` có cùng tiêu chí bằng nhau không?  
**Không.** `distinct` dùng `equals`; comparator dùng `compare`.

**Câu 17.** Comparator trả 0 cho hai key khác nhau có thể ảnh hưởng `TreeSet` không?  
**Có.** TreeSet dựa trên comparator để xác định phần tử cùng thứ tự; phải xác định consistency with equals nếu dùng cấu trúc sorted set/map.

**Câu 18.** Nếu chỉ tìm một nhân viên điểm cao nhất, có nhất thiết sort toàn bộ?  
**Không.** Dùng `max(Comparator.comparingInt(Employee::getScore))` và xử lý `Optional`.

## 17. Checklist áp dụng trong dự án

- [ ] Dữ liệu có **natural ordering** đáng tin không, hay cần Comparator?
- [ ] Có giá trị null ở **phần tử** hoặc **key** không? Chính sách null là gì?
- [ ] Thứ tự mỗi tiêu chí là tăng hay giảm? `reversed()` đã đặt **đúng cấp** chưa?
- [ ] Nếu comparator có kết quả bằng nhau, cần giữ encounter order hay thêm tie-breaker?
- [ ] Source có encounter order không? Có dùng `unordered()` hoặc parallel `forEach` không?
- [ ] Comparator có tuân thủ **antisymmetry, transitivity, consistency**, không có side effects và không sửa source không?
- [ ] Có phép trừ `int/long` trong comparator dễ overflow không?
- [ ] Có yêu cầu sorting theo locale chứ không phải String natural order không?
- [ ] Stream hữu hạn chưa? `limit` đứng trước/sau sorted có đúng ý định không?
- [ ] Đã đánh giá chi phí sort/buffering nếu dữ liệu lớn chưa?
- [ ] Có đang kỳ vọng sorted tự sửa List hoặc tự xóa duplicate không?
- [ ] Nếu target Java 8, có dùng API chỉ xuất hiện từ Java 16+ như `Stream.toList()` không?
- [ ] Có unit test cho null, tie-breaker, dữ liệu trùng, cực trị số và ordered/parallel khi phù hợp không?

## 18. Tổng kết và nguồn chính thức

**`Stream.sorted()`** sắp xếp theo **thứ tự tự nhiên** từ `Comparable`; **`Stream.sorted(Comparator)`** áp dụng thứ tự do ứng dụng định nghĩa. Các factory như `Comparator.comparing`, `comparingInt`, `thenComparing`, `reversed`, `nullsFirst`, `nullsLast` giúp xây comparator rõ ràng mà vẫn bảo toàn ý nghĩa nhiều tiêu chí.

`sorted` là một **stateful intermediate operation** và có thể cần buffer toàn bộ nguồn hữu hạn. Với **ordered streams**, sắp xếp ổn định; với unordered streams không có bảo đảm stability. Stream.sorted không sửa List nguồn, không khử trùng, không tự điều khiển thứ tự side effects của parallel `forEach`.

**Kiến thức trong bài vẫn đang áp dụng trong Java hiện đại.** Khi chọn giải pháp, ưu tiên đúng semantics, tính ổn định, chi phí và khả năng đọc code hơn việc cố dùng Stream ở mọi nơi.

Tài liệu chính thức:

- [Oracle Java SE — Stream.sorted() và sorted(Comparator)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#sorted()).
- [Oracle Java SE — Comparator API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).
- [Oracle Java SE — Comparable API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html).
- [Oracle Java SE — java.util.stream package summary](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html).
- [Oracle Java SE — List.sort](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).
- [Oracle Java SE — IntStream.sorted](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html#sorted()).
