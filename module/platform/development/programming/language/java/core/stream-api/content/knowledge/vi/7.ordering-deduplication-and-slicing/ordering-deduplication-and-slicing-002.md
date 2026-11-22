# Sắp xếp theo thứ tự tự nhiên bằng `sorted`

Java Stream API cho phép mô tả luồng xử lý dữ liệu bằng các thao tác khai báo như `filter`, `map`, `sorted` và `collect`. Khi cần đưa dữ liệu về **thứ tự tự nhiên** (natural order) mà không thay đổi tập dữ liệu gốc, ta dùng thao tác trung gian `sorted()` không đối số.

Bài này thuộc chương **Thứ tự, loại trùng và cắt lát** của module **JAVA_STREAM_API**. Trọng tâm là hợp đồng của `Stream.sorted()`, cách Java xác định thứ tự tự nhiên từ `Comparable`, ảnh hưởng của encounter order, hành vi với parallel stream, cùng các giới hạn về bộ nhớ và nguồn vô hạn. Phần cuối minh họa việc kết hợp sắp xếp với `filter`, `map`, `distinct`, `limit`, `reduce` và `collect`.

## 1. Bắt đầu với `sorted()`

```java
import java.util.List;

List<Integer> scores = List.of(8, 3, 10, 1, 3);

List<Integer> ascending = scores.stream()
        .sorted()
        .toList();

System.out.println(ascending); // [1, 3, 3, 8, 10]
System.out.println(scores);    // [8, 3, 10, 1, 3]
```

`sorted()` tạo một **stream mới có thứ tự tăng dần** theo thứ tự tự nhiên của phần tử. Danh sách `scores` gốc không bị sắp xếp tại chỗ. `toList()` là terminal operation lấy các phần tử đã được sắp xếp để tạo danh sách kết quả.

Trong `Stream<T>`, chữ ký của thao tác là:

```java
Stream<T> sorted();
```

Các điểm cần ghi nhớ:

- `sorted()` là **intermediate operation**: việc sắp xếp được thực hiện khi terminal operation thực sự yêu cầu dữ liệu; chỉ gọi `sorted()` chưa tạo ngay một danh sách kết quả.
- Đây là một thao tác **stateful**: muốn xuất ra phần tử nhỏ nhất một cách tổng quát, nó phải xem xét các phần tử đầu vào, và việc sắp xếp thường phải lưu trữ chúng.
- Thứ tự được xác định bởi **natural ordering** của từng phần tử thông qua `Comparable`.
- `sorted()` không loại phần tử trùng lặp. Muốn loại trùng cần thêm `distinct()`, nhưng tiêu chí loại trùng dùng `equals`, không phải `compareTo`.
- `sorted()` sắp xếp **tăng dần** theo thứ tự tự nhiên; muốn giảm dần hoặc tiêu chí riêng phải dùng `sorted(Comparator)`, nằm ngoài phạm vi chính của bài này.

## 2. Thứ tự tự nhiên đến từ `Comparable`

Phần tử của `Stream<T>` cần có khả năng so sánh với nhau theo `Comparable`. Giao diện `java.lang.Comparable<T>` quy định:

```java
public interface Comparable<T> {
    int compareTo(T other);
}
```

Kết quả của `a.compareTo(b)` được hiểu qua **dấu** của số trả về:

| Kết quả | Ý nghĩa |
|---|---|
| Âm | `a` đứng trước `b` |
| Bằng `0` | `a` và `b` bằng nhau **theo thứ tự sắp xếp** |
| Dương | `a` đứng sau `b` |

Không cần `compareTo` chỉ trả về `-1`, `0` hoặc `1`; bất kỳ số nguyên âm/dương nào cũng hợp lệ nếu bảo đảm hợp đồng so sánh. Không tự diễn giải trị tuyệt đối của kết quả thành khoảng cách giữa hai giá trị.

Các kiểu phổ biến đã có thứ tự tự nhiên:

| Kiểu | Thứ tự tự nhiên |
|---|---|
| `Integer`, `Long`, `Double` | Theo giá trị số, với các quy tắc so sánh được kiểu đó định nghĩa |
| `String` | Theo so sánh từ điển trên các đơn vị mã UTF-16, phân biệt chữ hoa/thường |
| `LocalDate`, `LocalDateTime` | Theo thời điểm/ngày giờ được biểu diễn trong phạm vi kiểu |
| `BigDecimal` | Theo giá trị số, không nhất thiết theo `equals` |
| `Enum` | Theo thứ tự khai báo hằng enum |

### 2.1. Số nguyên: kết quả rõ ràng

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = Stream.of(12, -3, 7, 0, 12)
        .sorted()
        .toList();

System.out.println(numbers); // [-3, 0, 7, 12, 12]
```

Giá trị `12` xuất hiện hai lần nên được giữ cả hai. `sorted()` không làm thay đổi số lượng phần tử, không sửa giá trị và không gộp các phần tử bằng nhau.

### 2.2. Chuỗi: thứ tự tự nhiên không phải thứ tự từ điển theo ngôn ngữ

```java
List<String> words = Stream.of("banana", "Apple", "apple", "Banana")
        .sorted()
        .toList();

System.out.println(words);
// [Apple, Banana, apple, banana]
```

`String.compareTo` phân biệt chữ hoa và chữ thường; kết quả không nhất thiết là thứ tự từ điển mà người dùng mong đợi theo tiếng Việt hoặc một ngôn ngữ khác. Nếu cần sắp xếp theo quy tắc ngôn ngữ, dấu và chữ hoa/thường, phải chọn công cụ so sánh có ngữ cảnh, chẳng hạn `Collator`, và dùng overload `sorted(Comparator)`.

Một lỗi khác là dữ liệu số được lưu dưới dạng `String`:

```java
System.out.println(Stream.of("2", "10", "3").sorted().toList());
// [10, 2, 3] — so sánh chuỗi, không phải giá trị số

System.out.println(Stream.of("2", "10", "3")
        .map(Integer::parseInt)
        .sorted()
        .toList());
// [2, 3, 10] — so sánh số nguyên
```

Muốn sắp xếp số, nên chuyển sang kiểu số trước khi gọi `sorted()`; các chuỗi không hợp lệ phải được kiểm tra hoặc xử lý khi `parseInt` phát sinh `NumberFormatException`.

### 2.3. Thứ tự tự nhiên với ngày tháng

```java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Stream;

List<LocalDate> dates = Stream.of(
        LocalDate.of(2026, 12, 1),
        LocalDate.of(2026, 1, 15),
        LocalDate.of(2025, 12, 31)
).sorted().toList();

System.out.println(dates);
// [2025-12-31, 2026-01-15, 2026-12-01]
```

Với `LocalDate`, thứ tự tự nhiên có ý nghĩa theo trình tự ngày tháng. Không nên dùng chuỗi định dạng tùy ý như `"31/12/2025"` để sắp xếp thời gian, vì thứ tự ký tự có thể khác thứ tự thời gian.

## 3. Tạo thứ tự tự nhiên cho kiểu dữ liệu tự định nghĩa

Nếu một class có quy tắc thứ tự duy nhất, rõ ràng và ổn định, class đó có thể triển khai `Comparable<T>`. Chẳng hạn hệ thống xếp hạng nhiệm vụ theo mức ưu tiên tăng dần, rồi theo mã để phân định trường hợp bằng nhau:

```java
import java.util.List;

record Task(int priority, String code) implements Comparable<Task> {
    @Override
    public int compareTo(Task other) {
        int byPriority = Integer.compare(this.priority, other.priority);
        if (byPriority != 0) {
            return byPriority;
        }
        return this.code.compareTo(other.code);
    }
}

List<Task> tasks = List.of(
        new Task(3, "C"),
        new Task(1, "B"),
        new Task(1, "A")
);

List<Task> ordered = tasks.stream().sorted().toList();
System.out.println(ordered);
// [Task[priority=1, code=A], Task[priority=1, code=B], Task[priority=3, code=C]]
```

`Integer.compare(a, b)` đáng tin cậy hơn `a - b` khi so sánh số nguyên, vì phép trừ có thể tràn số:

```java
// Tránh cách này: phép trừ có thể overflow.
// return this.priority - other.priority;

// Nên dùng:
return Integer.compare(this.priority, other.priority);
```

> Dòng `return` thứ hai ở trên là biểu thức minh họa để đặt trong thân `compareTo`, không phải một chương trình Java độc lập.

### 3.1. Hợp đồng của `compareTo`

Một thứ tự tự nhiên hợp lệ cần bảo đảm quan hệ so sánh nhất quán: nếu `a < b` và `b < c` thì `a < c`; kết quả phải có tính đối xứng về dấu; hai giá trị được coi bằng nhau theo so sánh phải có tương quan thứ tự nhất quán với các giá trị thứ ba.

Thông thường, nên cố gắng làm cho `compareTo(a, b) == 0` nhất quán với `a.equals(b)`. Java cho phép một số kiểu có natural order không nhất quán với `equals` (ví dụ `BigDecimal` với scale khác nhau), nhưng điều đó có thể gây bất ngờ khi kết hợp `sorted`, `distinct`, `TreeSet` hoặc `TreeMap`.

Ví dụ:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b)); // 0: bằng nhau theo giá trị số
System.out.println(a.equals(b));    // false: scale khác nhau
```

Khi không tồn tại một thứ tự tự nhiên phù hợp cho mọi ngữ cảnh, thay vì ép class phải triển khai `Comparable`, nên dùng `Comparator` tại vị trí cần sắp xếp.

## 4. `sorted()` là stateful nhưng vẫn thuộc pipeline lazy

Giống các intermediate operation khác, `sorted()` tạo một bước mô tả pipeline; công việc thực sự diễn ra khi terminal operation yêu cầu kết quả.

```java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(9, 4, 7)
        .sorted();

// Chưa có terminal operation nên chưa yêu cầu lấy danh sách đã sắp xếp.
System.out.println("Đã khai báo pipeline");

System.out.println(pipeline.toList()); // [4, 7, 9]
```

**Stateful** có nghĩa `sorted()` thường phải đọc hết nguồn hữu hạn và lưu các phần tử cần thiết để quyết định thứ tự; nó không thể đơn giản xuất từng phần tử ngay khi vừa nhận như `map` hoặc `filter` trong trường hợp tổng quát.

Minh họa việc sắp xếp cần quan sát các giá trị trước khi xuất chúng:

```java
List<Integer> result = Stream.of(4, 1, 3)
        .peek(n -> System.out.println("Nhận: " + n))
        .sorted()
        .peek(n -> System.out.println("Xuất: " + n))
        .toList();

System.out.println(result); // [1, 3, 4]
```

Trong pipeline tuần tự này, ta thường quan sát đủ ba dòng `Nhận` trước những dòng `Xuất`, nhưng **không dùng `peek` làm cơ chế nghiệp vụ**: Stream API cho phép tối ưu hóa loại bỏ một số bước khi chúng không ảnh hưởng kết quả. Ví dụ `count()` trên nguồn có kích thước biết trước có thể không cần thực thi `sorted()` hay các thao tác `peek` tương ứng.

Sau khi một terminal operation tiêu thụ stream, không thể sử dụng lại cùng đối tượng stream:

```java
Stream<Integer> values = Stream.of(3, 1, 2).sorted();
System.out.println(values.toList()); // [1, 2, 3]

// values.count(); // Không hợp lệ: stream đã được tiêu thụ.
```

Muốn tạo một cách nhìn sắp xếp khác, hãy tạo stream mới từ nguồn dữ liệu.

## 5. Encounter order, tính ổn định và kết quả song song

**Encounter order** là thứ tự logic mà các phần tử được gặp trong một stream có thứ tự; nó không có nghĩa nguồn đã tăng dần. Với `List.of(3, 1, 2)`, encounter order ban đầu là `3 → 1 → 2`. Sau `sorted()`, stream có encounter order tương ứng với thứ tự sắp xếp tự nhiên.

```java
List<Integer> ordered = List.of(3, 1, 2)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(ordered); // [1, 2, 3]
```

Trong ví dụ này, các phần tử có thể được xử lý trên nhiều thread, nhưng `toList()` vẫn trả danh sách theo thứ tự đã sắp xếp.

### 5.1. Khi nào `sorted()` ổn định?

Với **nguồn có encounter order**, `sorted()` là phép sắp xếp **ổn định** (*stable*): nếu hai phần tử so sánh bằng `0`, chúng giữ nguyên thứ tự tương đối ban đầu.

```java
import java.util.List;

record Player(int rank, String name) implements Comparable<Player> {
    @Override
    public int compareTo(Player other) {
        return Integer.compare(this.rank, other.rank);
    }
}

List<Player> players = List.of(
        new Player(2, "Lan"),
        new Player(1, "Minh"),
        new Player(2, "An")
);

System.out.println(players.stream().sorted().toList());
// [Player[rank=1, name=Minh], Player[rank=2, name=Lan], Player[rank=2, name=An]]
```

Hai người có `rank = 2` được xem là bằng nhau theo `compareTo`, nên `Lan` vẫn đứng trước `An`. Ví dụ này cố ý xây dựng thứ tự theo hạng và **không phân định** hai tên khi hạng bằng nhau; vì vậy natural order của kiểu `Player` không hoàn toàn nhất quán với `equals`. Nếu nghiệp vụ đòi thứ tự đầy đủ, hãy thêm tiêu chí phụ, ví dụ `name`.

Đối với **nguồn không có encounter order** như `HashSet.stream()`, `sorted()` vẫn sắp xếp các giá trị theo thứ tự tự nhiên, nhưng không có bảo đảm ổn định cho những phần tử so sánh bằng `0`. Nếu cần kết quả tái lập ngay cả khi khóa sắp xếp bằng nhau, nên định nghĩa thêm tiêu chí phân định thứ tự thay vì chỉ dựa vào vị trí xuất hiện.

### 5.2. `parallel()` không hủy kết quả sắp xếp

```java
List<Integer> result = List.of(5, 2, 4, 1, 3)
        .parallelStream()
        .sorted()
        .toList();

System.out.println(result); // [1, 2, 3, 4, 5]
```

`parallel()` thay đổi cách thực thi, không làm mất yêu cầu sắp xếp. Tuy vậy, terminal operation `forEach` **không bảo đảm thứ tự thực thi hành động** trong pipeline song song:

```java
List.of(5, 2, 4, 1, 3)
        .parallelStream()
        .sorted()
        .forEach(n -> System.out.print(n + " "));
// Không được suy ra thứ tự in cố định.

System.out.println();

List.of(5, 2, 4, 1, 3)
        .parallelStream()
        .sorted()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5
```

Nếu mục đích là lấy một danh sách đã sắp xếp, `toList()` hoặc `collect(Collectors.toList())` diễn đạt ý định rõ hơn việc ghi vào một danh sách ngoài qua `forEach`. Tự thêm phần tử vào `ArrayList` từ nhiều thread có nguy cơ race condition.

## 6. Vị trí `sorted()` trong pipeline quyết định ý nghĩa

Các thao tác `filter`, `map`, `sorted`, `distinct` và `limit` đều có thể kết hợp, nhưng đổi thứ tự các bước có thể đổi kết quả hoặc chi phí.

### 6.1. `filter` trước `sorted`

```java
List<Integer> even = Stream.of(9, 2, 6, 3, 4)
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();

System.out.println(even); // [2, 4, 6]
```

Nếu phép lọc độc lập với thứ tự, lọc trước sắp xếp thường có lợi vì giảm số phần tử cần sắp xếp. Ví dụ `sorted().filter(...)` cũng cho kết quả `[2, 4, 6]` ở đây, nhưng có thể phải sắp xếp nhiều phần tử hơn.

### 6.2. `map` trước hay sau `sorted`?

```java
List<Integer> byOriginal = Stream.of(-5, 2, -1)
        .sorted()
        .map(Math::abs)
        .toList();
System.out.println(byOriginal); // [5, 1, 2]

List<Integer> byAbsolute = Stream.of(-5, 2, -1)
        .map(Math::abs)
        .sorted()
        .toList();
System.out.println(byAbsolute); // [1, 2, 5]
```

Sắp xếp **trước** `map` nghĩa là xếp theo giá trị ban đầu; sắp xếp **sau** `map` nghĩa là xếp theo giá trị đã biến đổi. Hai pipeline chỉ tương đương khi phép biến đổi bảo toàn thứ tự cần so sánh.

### 6.3. `sorted().limit(n)` và `limit(n).sorted()`

```java
List<Integer> firstThreeSmallest = Stream.of(8, 3, 7, 2, 9, 1)
        .sorted()
        .limit(3)
        .toList();
System.out.println(firstThreeSmallest); // [1, 2, 3]

List<Integer> sortFirstThreeSeen = Stream.of(8, 3, 7, 2, 9, 1)
        .limit(3)
        .sorted()
        .toList();
System.out.println(sortFirstThreeSeen); // [3, 7, 8]
```

Pipeline thứ nhất trả ba giá trị nhỏ nhất của **toàn bộ nguồn**. Pipeline thứ hai chỉ lấy ba giá trị **đầu tiên theo encounter order**, rồi sắp xếp ba giá trị đó. Thứ tự các bước mang ý nghĩa nghiệp vụ khác nhau.

Đối với nguồn **vô hạn** như `Stream.generate(...)`, đặt `sorted()` trước `limit()` thông thường khiến chương trình không thể hoàn tất vì `sorted()` cần toàn bộ đầu vào. Ngược lại:

```java
import java.util.concurrent.ThreadLocalRandom;

List<Integer> sample = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(100)
).limit(10).sorted().toList();

System.out.println(sample); // 10 số ngẫu nhiên đã được xếp tăng dần
```

Ở đây `limit(10)` tạo nguồn hữu hạn cho `sorted()`. Nếu phải tìm N phần tử nhỏ nhất từ một nguồn hữu hạn rất lớn, việc `sorted().limit(N)` có thể tốn nhiều bộ nhớ; có thể cân nhắc thuật toán top-N chuyên biệt.

### 6.4. Sắp xếp và loại trùng

```java
List<Integer> unique = Stream.of(4, 2, 4, 1, 2)
        .distinct()
        .sorted()
        .toList();

System.out.println(unique); // [1, 2, 4]
```

`distinct()` xét phần tử trùng nhau theo `Object.equals`; `sorted()` xét thứ tự tự nhiên theo `Comparable.compareTo`. Hai quy tắc **không đồng nhất**:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> values = List.of(
        new BigDecimal("1.0"),
        new BigDecimal("1.00")
);

System.out.println(values.stream().sorted().distinct().count()); // 2
```

Hai `BigDecimal` đều có cùng giá trị số theo `compareTo`, nhưng `equals` khác nhau do scale; vì vậy `distinct()` giữ cả hai. Sắp xếp không thay đổi quy tắc loại trùng.

### 6.5. Chọn `min`/`max` khi chỉ cần một giá trị cực trị

```java
List<Integer> temperatures = List.of(30, 25, 28, 24);

int minimum = temperatures.stream()
        .min(Integer::compareTo)
        .orElseThrow();
System.out.println(minimum); // 24
```

Nếu chỉ cần phần tử nhỏ nhất, `min` trực tiếp biểu đạt mục tiêu và có thể tránh chi phí sắp xếp toàn bộ:

```java
// Đúng nhưng thường không cần thiết nếu chỉ lấy một giá trị:
int alsoMinimum = temperatures.stream()
        .sorted()
        .findFirst()
        .orElseThrow();
```

`min` và `max` trả về `Optional<T>` vì stream có thể rỗng. Với số nguyên primitive, có `IntStream.min()`/`max()` và `OptionalInt`.

## 7. `sorted()` với stream kiểu nguyên thủy

`IntStream`, `LongStream` và `DoubleStream` cũng có `sorted()` không đối số, nên có thể sắp xếp trực tiếp mà không cần boxing sang `Integer`, `Long` hoặc `Double`.

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] sortedNumbers = IntStream.of(6, 1, 4, 2)
        .sorted()
        .toArray();

System.out.println(Arrays.toString(sortedNumbers)); // [1, 2, 4, 6]
```

```java
double[] measurements = {2.5, -1.0, 3.0};

System.out.println(Arrays.toString(
        Arrays.stream(measurements).sorted().toArray()
)); // [-1.0, 2.5, 3.0]
```

Với `DoubleStream`, các quy tắc sắp xếp liên quan đến `NaN`, `-0.0` và `+0.0` tuân theo `Double.compare`; đừng áp dụng máy móc trực giác so sánh số thực thông thường cho những giá trị đặc biệt này.

## 8. Trường hợp lỗi: không so sánh được, `null` và thứ tự không xác định

### 8.1. Phần tử không triển khai `Comparable`

```java
record Note(String text) {}

// Không có natural ordering; khi thực sự so sánh các Note, có thể gây
// ClassCastException trong lúc terminal operation tiêu thụ pipeline.
// Stream.of(new Note("B"), new Note("A")).sorted().toList();
```

Overload `sorted()` không có ràng buộc generic ngay trong chữ ký bắt kiểu `T` phải triển khai `Comparable`, nên lỗi có thể chỉ phát sinh **lúc chạy**, khi phép so sánh thực sự cần thực hiện. Với kiểu dữ liệu không có natural ordering, dùng `sorted(Comparator)` hoặc thiết kế `Comparable` thích hợp.

Nếu các phần tử có kiểu không thể so sánh lẫn nhau, ví dụ tập trộn `Integer` và `String` trong `Stream<Object>`, ta cũng có thể gặp `ClassCastException`.

### 8.2. `null` trong nguồn

```java
import java.util.Objects;

List<String> safe = Stream.of("b", null, "a")
        .filter(Objects::nonNull)
        .sorted()
        .toList();

System.out.println(safe); // [a, b]
```

Natural ordering của các kiểu như `String` không xác định `null` là phần tử đứng đầu hay cuối. Nếu cần so sánh `null` với giá trị thật, `sorted()` có thể ném `NullPointerException` khi so sánh. Lọc `null` trước khi sắp xếp hoặc dùng `Comparator.nullsFirst(...)`/`Comparator.nullsLast(...)` ở overload có comparator để xác định chính sách rõ ràng.

### 8.3. Phần tử có khóa sắp xếp thay đổi trong quá trình chạy

Kết quả có thể khó dự đoán khi đối tượng thay đổi trường dùng trong `compareTo` trong lúc pipeline đang sắp xếp. Vì vậy, tránh tác động lên dữ liệu nguồn trong các lambda, tránh sửa khóa sắp xếp từ thread khác; cân nhắc ánh xạ thành dữ liệu bất biến trước khi sắp xếp.

## 9. Chi phí bộ nhớ, độ phức tạp và nguồn vô hạn

`sorted()` là một thao tác stateful; trong trường hợp tổng quát, phép sắp xếp N phần tử thường có chi phí thời gian khoảng **O(N log N)** và cần bộ nhớ đệm tương ứng để quản lý dữ liệu. Chi phí thực tế phụ thuộc triển khai, kiểu nguồn, đặc điểm dữ liệu và chế độ tuần tự/song song.

Một số lưu ý thực hành:

1. **Nguồn hữu hạn lớn:** thu nhỏ đầu vào bằng `filter` trước `sorted` nếu không thay đổi ngữ nghĩa; tránh sắp xếp toàn bộ chỉ để lấy cực trị đơn lẻ.
2. **Nguồn không giới hạn:** `Stream.generate(...).sorted().limit(5)` không thể sắp xếp xong nguồn vô hạn; dùng `limit(5).sorted()` nếu mục tiêu là sắp xếp một mẫu hữu hạn.
3. **Chạy song song:** `parallelStream().sorted()` có thể được xử lý song song, nhưng cần phối hợp và lưu các phần tử; overhead có thể khiến tập nhỏ chậm hơn chạy tuần tự. Đo hiệu năng thay vì mặc định có lợi.
4. **Side effect:** không dùng `peek`, `map` hoặc `compareTo` để ghi vào trạng thái chung khi sort, vì thứ tự/lần gọi không nên trở thành yêu cầu nghiệp vụ.
5. **Tài nguyên:** `sorted()` không tự mở tệp; nhưng nếu nguồn lấy từ `Files.lines(path)`, stream nguồn giữ tài nguyên và cần `try-with-resources`. Sắp xếp dữ liệu tệp quá lớn có thể yêu cầu giải pháp sắp xếp ngoài bộ nhớ.

Với dữ liệu đã ở trong một `List` và cần sắp xếp **trực tiếp tại chỗ**, `List.sort` có thể thích hợp hơn vì không cần dựng thêm danh sách kết quả. Nhưng nếu muốn giữ nguyên dữ liệu nguồn, `list.stream().sorted().toList()` thể hiện rõ ý định.

## 10. Ví dụ tổng hợp có thể chạy (Java 17+)

Chương trình độc lập sau chứng minh rằng sắp xếp tự nhiên không sửa nguồn, kết hợp được với `filter` và `distinct`, và vẫn tạo kết quả có thứ tự khi dùng parallel stream.

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public class NaturalSortedDemo {
    record Job(int priority, String id) implements Comparable<Job> {
        @Override
        public int compareTo(Job other) {
            int result = Integer.compare(priority, other.priority);
            return result != 0 ? result : id.compareTo(other.id);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(7, 3, 1, 7, 5);

        List<Integer> result = source.stream()
                .filter(n -> n >= 3)
                .distinct()
                .sorted()
                .toList();

        System.out.println(result); // [3, 5, 7]
        System.out.println(source); // [7, 3, 1, 7, 5]

        List<Job> jobs = List.of(
                new Job(2, "task-C"),
                new Job(1, "task-B"),
                new Job(1, "task-A")
        );

        System.out.println(jobs.parallelStream().sorted().toList());
        // [Job[priority=1, id=task-A], Job[priority=1, id=task-B],
        //  Job[priority=2, id=task-C]]

        System.out.println(Stream.of("Z", null, "A")
                .filter(Objects::nonNull)
                .sorted()
                .toList()); // [A, Z]

        System.out.println(Stream.of(9, 4, 1, 7)
                .sorted()
                .limit(2)
                .toList()); // [1, 4]
    }
}
```

Để chạy từ Java 16 trở lên có thể dùng `Stream.toList()`; trên Java 8–15, thay các đoạn `.toList()` bằng `.collect(Collectors.toList())` và không dùng `record` nếu phiên bản Java chưa hỗ trợ. `Stream.toList()` trả danh sách không thể chỉnh sửa, trong khi `Collectors.toList()` không cam kết kiểu hay tính thay đổi được của danh sách trả về.

## 11. Các sai lầm thường gặp

| Suy luận/cách viết | Vấn đề | Cách làm phù hợp |
|---|---|---|
| `list.stream().sorted()` làm thay đổi `list` | Stream tạo pipeline, không sắp xếp lại list gốc | Gọi terminal operation để lấy kết quả; nếu muốn sửa gốc dùng `list.sort` |
| `sorted()` tự loại phần tử trùng | Thao tác sort không loại trùng | Dùng `distinct()` khi cần, chú ý tiêu chí `equals` |
| `sorted()` luôn sắp xếp mọi `String` đúng thứ tự tiếng Việt | `String.compareTo` không theo quy tắc địa phương | Dùng `Collator`/comparator thích hợp |
| `sorted().limit(3)` giống `limit(3).sorted()` | Một bên xét toàn bộ, một bên xét ba phần tử đầu | Chọn theo ý nghĩa nghiệp vụ |
| `sorted()` chạy được với đối tượng bất kỳ | Phần tử có thể không `Comparable` | Định nghĩa natural order hoặc truyền comparator |
| Sắp xếp giá trị `null` mà không định chính sách | So sánh có thể ném `NullPointerException` | Lọc null hoặc chọn comparator xử lý null |
| `parallelStream().sorted().forEach(...)` luôn in tăng dần | `forEach` không bảo đảm thứ tự hành động | Dùng `forEachOrdered` hoặc `toList` |
| `sorted().limit(5)` luôn hoàn tất trên stream vô hạn | `sorted` cần toàn bộ nguồn | Giới hạn nguồn hữu hạn trước sort |
| Chỉ cần nhỏ nhất vẫn sort toàn bộ | Có thể tốn thời gian và bộ nhớ | Dùng `min(Comparator)` hoặc `IntStream.min()` |

## 12. Tự kiểm tra

1. **`Stream.of(4, 1, 4, 2).sorted().toList()` cho kết quả nào?** `[1, 2, 4, 4]` vì sort tăng dần và không loại trùng.
2. **`Stream.of("2", "10", "3").sorted().toList()` cho kết quả nào?** `[10, 2, 3]` vì `String.compareTo` không so sánh giá trị số.
3. **Khác nhau giữa `sorted().limit(2)` và `limit(2).sorted()` với `[9, 3, 1]`?** Kết quả lần lượt `[1, 3]` và `[3, 9]`.
4. **`sorted()` có làm thay đổi `List` nguồn không?** Không. Nó tạo một bước trong stream; phần tử nguồn không được sắp xếp tại chỗ.
5. **Vì sao gọi `sorted()` với object không `Comparable` có thể lỗi ở runtime?** Vì `Stream<T>.sorted()` không yêu cầu ràng buộc generic ở thời điểm biên dịch; runtime phải thực hiện phép so sánh tự nhiên.
6. **Một nguồn `HashSet` không có encounter order có thể dùng `sorted()` không?** Có, với phần tử so sánh được; thứ tự theo natural order được thiết lập, nhưng không cam kết ổn định giữa các phần tử có `compareTo == 0`.
7. **`parallelStream().sorted().toList()` có bảo đảm kết quả tăng dần không?** Có, nếu các phần tử có natural ordering hợp lệ và pipeline tiêu thụ thành công.
8. **Muốn tìm số nhỏ nhất, nên dùng `sorted().findFirst()` hay `min()`?** Thông thường dùng `min()` vì truyền đạt mục tiêu trực tiếp và không cần sắp xếp toàn bộ dãy.

**Quy tắc áp dụng:** dùng `sorted()` khi phần tử có **thứ tự tự nhiên xác định** và mục tiêu là thứ tự tăng dần; dùng `sorted(Comparator)` khi cần quy tắc khác. Xem xét kỹ vị trí đặt `sorted` so với `filter`, `map`, `distinct` và `limit` vì nó quyết định cả **ý nghĩa kết quả** lẫn **chi phí xử lý**.
