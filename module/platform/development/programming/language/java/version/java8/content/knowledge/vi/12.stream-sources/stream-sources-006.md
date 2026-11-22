# Stream.concat và nối nguồn trong Java

## 1. Mục tiêu: nối các nguồn Stream mà không cần tạo danh sách trung gian

Khi xử lý dữ liệu bằng Java Stream API, ta thường có **hai nguồn** cần đưa vào cùng một pipeline: bản ghi cũ và mới, kết quả từ hai collection, hai nguồn file, hoặc hai nhóm sự kiện. Từ Java 8, `java.util.stream.Stream` có phương thức tĩnh:

```java
static <T> Stream<T> concat(
        Stream<? extends T> a,
        Stream<? extends T> b)
```

`Stream.concat(a, b)` tạo một **Stream mới được nối lười** (*lazily concatenated stream*). Về mặt thứ tự logic, các phần tử từ `a` xuất hiện **trước** các phần tử từ `b`. Nếu **cả hai** Stream đầu vào có encounter order, Stream kết quả cũng **có thứ tự**. Nếu **ít nhất một** đầu vào ở parallel mode, Stream kết quả ở parallel mode. Khi đóng Stream kết quả, các close handlers của **cả hai** đầu vào được kích hoạt.

Ví dụ cơ bản:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> before = Arrays.asList("A", "B");
List<String> after  = Arrays.asList("C", "D");

List<String> combined = Stream.concat(
        before.stream(),
        after.stream()
).collect(Collectors.toList());

System.out.println(combined); // [A, B, C, D]
```

`Stream.concat` chỉ xây **một Stream kết hợp**. Nó không tự nối hai `List` bằng cách thêm phần tử từ `after` vào `before`. Collection nguồn vẫn được giữ nguyên nếu callback của bạn không sửa chúng. Lệnh `collect` mới tạo List kết quả.

**Bốn điều cần nhớ ngay:**

1. **Nối, không merge/sort:** `concat` nối hai chuỗi phần tử, không sắp xếp, không loại trùng và không kiểm tra các phần tử có khóa giống nhau.
2. **Lazy traversal:** tạo Stream kết quả không đồng nghĩa xử lý toàn bộ phần tử ngay.
3. **Một lần tiêu thụ:** các Stream đầu vào đã gắn vào phép nối, không được cố dùng lại riêng biệt; Stream kết quả cũng không thể chạy hai terminal operations độc lập.
4. **Quản lý tài nguyên:** `concat` kết hợp các close handlers, nhưng gọi `count`/`collect` không tự đóng Stream; nếu một nguồn gắn với I/O, phải thiết kế `try-with-resources` thích hợp.

Đây là các quy tắc từ Java 8 vẫn còn hiệu lực trên Java SE hiện đại. Bài không cần dùng thư viện legacy.

## 2. Dễ hình dung: nguồn A, nguồn B, Stream nối

```text
Stream A: [a1, a2, a3]
                    \
                     \ 
                    Stream.concat(A, B)
                     /
                    /
Stream B: [b1, b2]

Kết quả logic có encounter order:
[a1, a2, a3, b1, b2]
```

Có hai lớp ý nghĩa cần tách biệt:

- **Thứ tự kết quả logic**: khi hai nguồn có encounter order, các phần tử của A đứng trước B trong sequence kết quả. Đây là ngữ nghĩa của `concat`.
- **Thứ tự callback chạy thực tế**: trong pipeline parallel, các callback trong `map`, `filter` hoặc `peek` có thể được lên lịch khác nhau. Ngay cả với nguồn ordered, `forEach` song song không bảo đảm thứ tự in log.

Do đó, `concat` không có nghĩa JVM sẽ luôn xử lý từng phần tử A xong mới bắt đầu mọi công việc liên quan B trong bất kỳ chế độ nào. **Thứ tự của các giá trị sau phép nối** khác với **thứ tự thực thi side effect trong các stage**.

### 2.1. Mô hình trên một nguồn rỗng

```java
List<String> result = Stream.concat(
        Stream.<String>empty(),
        Stream.of("X", "Y")
).collect(Collectors.toList());
// [X, Y]
```

Nối với Stream rỗng ở đầu không làm thay đổi sequence phần tử còn lại. Tương tự, nối với Stream rỗng ở cuối không thêm giá trị mới.

`Stream.empty()` là một **Stream hợp lệ không có phần tử**, khác với giá trị tham chiếu `null` cho một đối số đầu vào.

### 2.2. Nối không thêm một phần tử phân cách

```java
List<String> result = Stream.concat(
        Stream.of("A", "B"),
        Stream.of("C", "D")
).collect(Collectors.toList());
// [A, B, C, D], không có dấu phân cách.
```

Nếu cần chèn một marker giữa hai nguồn, bạn phải thể hiện nó như dữ liệu:

```java
Stream<String> withMarker = Stream.concat(
        Stream.concat(Stream.of("A", "B"), Stream.of("|")),
        Stream.of("C", "D")
);
```

Ví dụ trên nối ba nguồn nhỏ và hợp lệ. Với **nhiều** nguồn, không nên lặp `concat` thành cây quá sâu; xem giải pháp `flatMap` ở mục 11.

## 3. Chữ ký generic và phép suy luận kiểu

Chữ ký:

```java
static <T> Stream<T> concat(
        Stream<? extends T> a,
        Stream<? extends T> b)
```

cho phép hai nguồn có phần tử thuộc những kiểu con thích hợp của cùng một kiểu đích `T`.

### 3.1. Hai Stream cùng kiểu

```java
Stream<String> names = Stream.concat(
        Stream.of("An", "Binh"),
        Stream.of("Chi")
);
```

`T` được suy luận là `String`. Đây là trường hợp đơn giản nhất.

### 3.2. Hai Stream có kiểu phần tử khác nhau nhưng tương thích

```java
Stream<Number> numbers = Stream.<Number>concat(
        Stream.of(1, 2),
        Stream.of(3.5, 4.5)
);

double sum = numbers.mapToDouble(Number::doubleValue)
        .sum(); // 11.0
```

`Stream<Integer>` và `Stream<Double>` có thể cùng được xem qua `Stream<? extends Number>`. Biểu thức `Stream.<Number>concat(...)` sử dụng **type witness** để nói rõ kiểu phần tử kết quả là `Number`.

Đây không phải việc cast số nguyên sang số thực khi nối. Các đối tượng phần tử giữ kiểu của chúng, và `Number::doubleValue` mới chuyển cách đọc số để tính tổng.

### 3.3. Chú ý generic invariance

`Stream<Integer>` không phải subtype của `Stream<Number>` theo Java generics. Vì thế, chữ ký `? extends T` của `concat` rất hữu ích: nhận các nguồn là producer của subtype. Tuy nhiên, đầu ra `Stream<Number>` không tự cung cấp một phép biến đổi mọi phần tử thành đúng class `Number` ở runtime.

Nếu bạn thật sự cần kiểu dữ liệu đồng nhất về representation, hãy viết `map` thích hợp thay vì dùng unchecked cast.

### 3.4. Nối Stream khác với nối hai kiểu `Collection`

Ví dụ:

```java
List<String> left = Arrays.asList("a", "b");
List<String> right = Arrays.asList("c");

Stream<String> combined = Stream.concat(
        left.stream(), right.stream());
```

Phương thức `concat` nhận **Stream**, không nhận trực tiếp `Collection`:

```java
// KHÔNG BIÊN DỊCH:
// Stream.concat(left, right);
```

Nếu cần kết quả là một List, hãy gọi terminal `collect` hoặc `toList()` phù hợp với phiên bản. `Stream.toList()` có từ Java 16; ví dụ tương thích Java 8 trong bài dùng `Collectors.toList()`.

## 4. `concat` là lazy, nhưng cần hiểu đúng thời điểm nguồn bị ràng buộc

Javadoc hiện hành mô tả `concat` là **lazily concatenated stream**. Điều đó nói rằng các phần tử không bị duyệt, ánh xạ hoặc thu thập ngay khi `concat` được gọi.

```java
Stream<String> joined = Stream.concat(
        Stream.of("a", "b").map(s -> {
            System.out.println("left map " + s);
            return s.toUpperCase();
        }),
        Stream.of("c").map(s -> {
            System.out.println("right map " + s);
            return s.toUpperCase();
        })
);

System.out.println("pipeline built");

List<String> firstTwo =
        joined.limit(2).collect(Collectors.toList());
```

Trong pipeline **sequential, ordered** trên, hai phần tử từ nguồn trái đủ để thỏa `limit(2)`. Vì vậy nó có thể kết thúc mà không thực hiện mapper của nguồn phải; các callback trong stage `map` không chạy tại thời điểm chỉ tạo `joined`.

Tuy nhiên, có một chi tiết quan trọng hơn câu “lazy”:

> Theo `Stream.concat` Javadoc, phép nối **binds each input stream to its source**.

Nghĩa là `concat` thao tác lên cả hai Stream đầu vào để ràng buộc chúng với nguồn; những thay đổi sau đó ở nguồn của Stream đầu vào **có thể không được phản ánh** trong kết quả của phép nối. Không dùng sự lười của việc duyệt như một bảo đảm nguồn còn late-binding sau khi đã gọi `concat`.

### 4.1. Lazy element traversal không phải lazy object construction

```java
static String loadName() {
    System.out.println("load name");
    return "A";
}

Stream<String> joined = Stream.concat(
        Stream.of(loadName()),
        Stream.of("B")
);
```

Đây là một đoạn **minh họa trong một class có `loadName()`**. Java đánh giá biểu thức đối số trước khi gọi `Stream.of`. Do đó, `loadName()` có thể chạy **ngay trong lúc dựng nguồn**, trước bất kỳ terminal operation nào. `concat` không khiến các biểu thức đối số của lời gọi đã diễn ra trở nên lazy.

Nếu muốn tạo phần tử theo nhu cầu, bạn có thể dùng nguồn supplier như `Stream.generate`, nhưng phải hiểu nguồn tạo như vậy thường là **vô hạn** và cần giới hạn khi chỉ muốn một số lượng hữu hạn.

### 4.2. Đừng phụ thuộc vào việc sửa nguồn sau khi ghép

```java
List<String> left = new ArrayList<>(
        Arrays.asList("A"));

Stream<String> leftStream = left.stream();
Stream<String> joined = Stream.concat(
        leftStream, Stream.of("B"));

left.add("C"); // Không được dựa vào C xuất hiện trong joined.
```

Đoạn này minh họa **điều không nên dựa vào**; không tự chạy tiếp terminal rồi khẳng định đầu ra luôn là một danh sách cố định trên mọi nguồn/implementation. Theo hợp đồng `concat`, input stream có thể đã bị bind vào source tại lúc nối; thay đổi sau đó có thể không xuất hiện.

Giải pháp khi cần một bộ dữ liệu cố định: chuẩn bị **snapshot rõ ràng trước khi tạo Stream**, hoặc xây Stream **sau khi** hoàn tất thay đổi collection.

### 4.3. Nối không có nghĩa đã materialize

`Stream.concat(a,b)` tạo một Stream đại diện cho phép nối. Nó không tương đương với việc gọi:

```java
List<T> both = new ArrayList<>();
both.addAll(listA);
both.addAll(listB);
```

Đoạn trên là **mã giả Java theo generic `T`** trong ngữ cảnh các biến đã có; nó tạo một collection mới bằng cách sao chép references. `concat` trì hoãn tiêu thụ phần tử cho tới khi terminal cần kết quả, và có thể short-circuit mà không phải duyệt hết nguồn.

## 5. Encounter order: quy tắc A trước B

Theo API `Stream.concat`, Stream kết quả có thứ tự **nếu cả hai Stream đầu vào có thứ tự**.

Với `List`:

```java
List<String> first = Arrays.asList("A1", "A2");
List<String> second = Arrays.asList("B1", "B2");

List<String> result = Stream.concat(
        first.stream(), second.stream())
    .collect(Collectors.toList());

// [A1, A2, B1, B2]
```

Thứ tự nguồn được giữ theo hợp đồng. Vì `Collectors.toList()` giữ encounter order của ordered stream, giá trị cuối xác định.

### 5.1. Nếu một đầu vào unordered thì sao?

`HashSet` thường không có encounter order được bảo đảm:

```java
Set<String> set = new HashSet<>(
        Arrays.asList("X", "Y", "Z"));

Stream<String> left = set.stream();
Stream<String> right = Stream.of("A", "B");

Stream<String> combined = Stream.concat(left, right);
```

Vì không thể nói tất cả hai nguồn đều ordered, `combined` **không có bảo đảm ordered** của phép nối. Không dùng output quan sát được trong một lần chạy để khẳng định thứ tự X/Y/Z hoặc một quy tắc sắp xếp cố định.

Khi cần thứ tự ổn định, hãy sắp xếp hoặc chọn collection có encounter order trước:

```java
List<String> stable = Stream.concat(
        set.stream().sorted(),
        Stream.of("A", "B")
).collect(Collectors.toList());

// Nếu set có X, Y, Z: [X, Y, Z, A, B].
```

`sorted` áp đặt thứ tự trên nhánh trái. Nó có thể cần thu thập/buffer các phần tử bên trong nhánh trái, vì vậy không nhất thiết là cách tối ưu về hiệu năng; nhưng khi nghiệp vụ đòi hỏi thứ tự, cách làm này rõ nghĩa.

### 5.2. Parallel mode không xóa ngữ nghĩa encounter order

```java
List<String> result = Stream.concat(
        Stream.of("A", "B").parallel(),
        Stream.of("C", "D")
).collect(Collectors.toList());

// [A, B, C, D]
```

Stream kết quả ở parallel mode vì nhánh trái parallel. Nhưng **kết quả ordered** vẫn giữ A/B trước C/D khi collector tôn trọng encounter order. Điều không được bảo đảm là callback nào chạy trên thread nào, vào thời điểm nào.

## 6. Chế độ parallel của Stream sau khi nối

Javadoc ghi rõ:

> Stream kết quả là parallel nếu một trong hai Stream đầu vào là parallel.

Bảng quyết định:

| A | B | `Stream.concat(A,B).isParallel()` |
| --- | --- | --- |
| Sequential | Sequential | `false` |
| Parallel | Sequential | `true` |
| Sequential | Parallel | `true` |
| Parallel | Parallel | `true` |

Có thể quan sát:

```java
boolean sequential = Stream.concat(
        Stream.of(1), Stream.of(2)
).isParallel(); // false

boolean parallel = Stream.concat(
        Stream.of(1).parallel(), Stream.of(2)
).isParallel(); // true
```

**Chú ý:** trạng thái parallel là chế độ thực thi, không phải cam kết pipeline luôn dùng nhiều worker hoặc nhanh hơn. Với hai nguồn rất nhỏ, overhead của parallel có thể vượt xa lợi ích.

### 6.1. Đổi mode sau khi nối

```java
Stream<String> combined = Stream.concat(
        Stream.of("A").parallel(),
        Stream.of("B")
).sequential();

boolean mode = combined.isParallel(); // false
```

Bạn có thể đổi chế độ của **Stream kết quả** bằng `sequential()` hoặc `parallel()`. Tuy vậy, Javadoc `concat` nêu rõ những thay đổi mode sau đó trên Stream kết quả **không được bảo đảm lan truyền tới các input streams**.

Vì vậy, không dựa vào việc thay đổi mode của Stream kết quả để khẳng định mọi input stream riêng lẻ đã bị thay đổi mode. Đối với tính đúng của dữ liệu, hãy tập trung vào contract của pipeline cuối cùng và tránh shared mutable state.

### 6.2. `forEach` khác `forEachOrdered`

```java
Stream.concat(
        Stream.of("A", "B").parallel(),
        Stream.of("C", "D")
).forEach(System.out::println);
```

Với parallel Stream, `forEach` **không bảo đảm thứ tự in**. Không dùng đầu ra của đoạn này làm stdout mẫu cố định.

Nếu cần thứ tự:

```java
Stream.concat(
        Stream.of("A", "B").parallel(),
        Stream.of("C", "D")
).forEachOrdered(System.out::println);
```

Kết quả theo encounter order ở ví dụ này:

```text
A
B
C
D
```

`forEachOrdered` đưa ra hợp đồng thứ tự của các hành động terminal theo encounter order, **không** có nghĩa mọi intermediate callback trước đó đều được thực thi tuần tự hoặc cùng một thread.

## 7. Các terminal operations sau `concat`

Sau khi nối, bạn có thể dùng các intermediate và terminal operations thông thường của `Stream<T>`:

```java
List<String> names = Stream.concat(
        Stream.of("an", "binh"),
        Stream.of("chi", "duong")
)
.filter(s -> s.length() >= 3)
.map(s -> s.toUpperCase(Locale.ROOT))
.collect(Collectors.toList());

// [BINH, CHI, DUONG]
```

Phép nối chỉ tạo nguồn logic gồm bốn phần tử; `filter` và `map` tiếp tục là intermediate lazy. `collect` mới yêu cầu dữ liệu.

### 7.1. `limit(n)`: có thể tránh duyệt nhánh B

```java
List<Integer> firstThree = Stream.concat(
        Stream.of(1, 2, 3, 4),
        Stream.of(100, 200)
)
.limit(3)
.collect(Collectors.toList());

// [1, 2, 3]
```

Trong pipeline sequential, ordered, chỉ cần lấy ba phần tử đầu bên trái. Nhánh bên phải không cần được duyệt để tạo kết quả này. Điều đó có thể tiết kiệm tài nguyên CPU khi nhánh phải có phép biến đổi đắt.

**Nhưng đừng kết luận nhánh phải không hề có chi phí khởi tạo.** `Stream.concat` đã nhận cả hai đối số Stream, nên biểu thức tạo nguồn bên phải và những tác vụ thiết lập có thể đã xảy ra khi dựng pipeline.

### 7.2. `skip(n)`: bỏ qua đầu nguồn trái rồi tới nguồn phải

```java
List<Integer> tail = Stream.concat(
        Stream.of(1, 2, 3),
        Stream.of(4, 5)
)
.skip(4)
.collect(Collectors.toList());

// [5]
```

Với hai ordered sources, `skip(4)` bỏ bốn phần tử đầu của sequence logic `[1,2,3,4,5]`; không bỏ riêng bốn phần tử từ từng nguồn.

### 7.3. `findFirst()`: ưu tiên A khi A có phần tử phù hợp

```java
Optional<String> first = Stream.concat(
        Stream.of("A", "B"),
        Stream.of("C", "D")
).findFirst();

// Optional[A].
```

Với nguồn có encounter order, `findFirst()` lấy phần tử đầu tiên của sequence nối. Nếu nhánh A rỗng, phần tử đầu nhánh B là ứng viên tiếp theo.

Khi thêm `filter`:

```java
Optional<String> firstLong = Stream.concat(
        Stream.of("A", "BB"),
        Stream.of("CCC")
).filter(s -> s.length() > 1)
 .findFirst();

// Optional[BB].
```

Đừng chuyển `findFirst` thành `findAny` nếu nghiệp vụ cần bảo đảm ưu tiên phần tử đầu theo thứ tự nối. `findAny` có thể trả phần tử phù hợp bất kỳ, đặc biệt khi parallel.

### 7.4. `count()`: đếm không đồng nghĩa gọi hết callback

```java
long count = Stream.concat(
        Stream.of(1, 2),
        Stream.of(3, 4, 5)
).count(); // 5
```

Javadoc `concat` nói việc bind source tạo cơ hội tối ưu khi biết kích thước chính xác của cả hai đầu vào. `count()` có thể dùng metadata thay vì duyệt từng phần tử ở một số pipeline. Do đó, không viết code nghiệp vụ phụ thuộc `peek` hoặc `map` chắc chắn sẽ chạy khi terminal chỉ cần số lượng.

```java
long n = Stream.concat(
        Stream.of("A", "B").peek(System.out::println),
        Stream.of("C")
).count();

// n == 3, nhưng không bảo đảm "A", "B" được in.
```

Các phép tối ưu loại bỏ việc gọi callback không ảnh hưởng kết quả là hành vi hợp lệ. `peek` chủ yếu hữu ích để quan sát khi debug, **không phải audit/logging bắt buộc**.

## 8. Nối nguồn có dữ liệu trùng và null

### 8.1. `concat` không loại trùng

```java
List<Integer> result = Stream.concat(
        Stream.of(1, 2, 2),
        Stream.of(2, 3)
).collect(Collectors.toList());

// [1, 2, 2, 2, 3]
```

Nếu nghiệp vụ muốn các giá trị duy nhất, đó là bước **riêng**:

```java
List<Integer> unique = Stream.concat(
        Stream.of(1, 2, 2),
        Stream.of(2, 3)
).distinct().collect(Collectors.toList());

// [1, 2, 3].
```

Trên ordered streams, `distinct()` giữ phần tử xuất hiện sớm nhất trong encounter order. Vì vậy duplicate từ B không thay thế bản được gặp trước từ A. Tuy nhiên, `distinct` có thể là stateful operation và cần bộ nhớ theo số giá trị đã thấy.

### 8.2. Phần tử null khác với tham số Stream null

Nguồn có thể chứa phần tử null:

```java
List<String> result = Stream.concat(
        Stream.of((String) null),
        Stream.of("ok")
).collect(Collectors.toList());

// [null, ok]
```

`concat` không tự lọc null và không kiểm tra các phần tử có hợp đồng non-null hay không. Nếu mapper phía sau gọi `s.length()` với `s == null`, kết quả có thể là `NullPointerException`.

Nếu ứng dụng không chấp nhận phần tử null, lọc rõ ràng:

```java
List<String> result = Stream.concat(
        Stream.of((String) null),
        Stream.of("ok")
).filter(Objects::nonNull)
 .collect(Collectors.toList());

// [ok].
```

Trái lại, **đối số Stream** của `concat` phải không null:

```java
// KHÔNG HỢP LỆ khi chạy: truyền một Stream null.
// Stream.concat(Stream.of("A"), null);
```

Trường hợp này ném `NullPointerException`, không được hiểu như nối với Stream rỗng. Nếu đầu vào có thể không tồn tại, hãy đưa ra chính sách chuyển thành `Stream.empty()` hoặc trả lỗi rõ ràng, thay vì ngầm bỏ qua.

## 9. Nối Stream không có nghĩa nối chuỗi ký tự

Tên “concat” xuất hiện trong cả `String.concat(String)` và `Stream.concat(Stream, Stream)` nhưng có kiểu/đầu ra khác nhau.

```java
String value = "A".concat("B"); // "AB"

Stream<String> values = Stream.concat(
        Stream.of("A"), Stream.of("B")
);
// Stream chứa hai phần tử "A" và "B".
```

Nếu muốn **một String** tạo từ nhiều phần tử, hãy dùng `Collectors.joining`:

```java
String joined = Stream.concat(
        Stream.of("A", "B"),
        Stream.of("C", "D")
).collect(Collectors.joining("-"));

// "A-B-C-D"
```

`Collectors.joining("-")` thêm dấu phân cách khi **chuyển Stream<String> thành String**, không phải ở bước `Stream.concat`. Vì vậy, đừng nhầm `concat` với `Collectors.joining` hay `StringBuilder.append`.

## 10. Nối hai primitive Stream

Java có ba biến thể primitive streams trong Stream API:

```java
IntStream.concat(IntStream a, IntStream b)
LongStream.concat(LongStream a, LongStream b)
DoubleStream.concat(DoubleStream a, DoubleStream b)
```

Chúng giữ dạng primitive để phù hợp với pipeline số học:

```java
int sum = IntStream.concat(
        IntStream.of(1, 2, 3),
        IntStream.of(4, 5)
).sum(); // 15

long longSum = LongStream.concat(
        LongStream.of(1L, 2L),
        LongStream.of(3L)
).sum(); // 6

double doubleSum = DoubleStream.concat(
        DoubleStream.of(1.5, 2.5),
        DoubleStream.of(3.0)
).sum(); // 7.0
```

Các API này có từ Java 8, vẫn được sử dụng. Chúng cũng có ngữ nghĩa nối lazy và các quy tắc ordered/parallel/close tương ứng theo tài liệu API.

### 10.1. Không dùng `Stream.concat` trực tiếp cho `IntStream`

`IntStream` không phải `Stream<Integer>`. Vì vậy:

```java
// KHÔNG BIÊN DỊCH:
// Stream.concat(IntStream.of(1), IntStream.of(2));
```

Nếu cả hai nguồn đều primitive, chọn `IntStream.concat`. Nếu cần đưa vào một pipeline object với `Stream<Integer>`, có thể gọi `boxed()`:

```java
Stream<Integer> boxed = Stream.concat(
        IntStream.of(1, 2).boxed(),
        IntStream.of(3, 4).boxed()
);
```

Boxing có chi phí biểu diễn riêng; ưu tiên primitive Stream khi mục tiêu là số học đơn giản.

### 10.2. Nguồn số lớn và tính kết hợp

`IntStream.concat` không tự chứng minh phép tính `reduce` của bạn an toàn để chạy song song. Nếu callback dùng shared mutable state hoặc phép reduction không associative, tính đúng vẫn có thể bị ảnh hưởng. Lời khuyên chung: dùng `sum`, `average`, `summaryStatistics` hoặc phép reduction có hợp đồng rõ khi phù hợp.

## 11. Nối nhiều hơn hai Stream: vì sao cần cân nhắc `flatMap`?

`Stream.concat` chỉ nhận **hai Stream**. Khi có ba Stream, bạn có thể lồng:

```java
Stream<String> a = Stream.of("A");
Stream<String> b = Stream.of("B");
Stream<String> c = Stream.of("C");

Stream<String> all =
        Stream.concat(Stream.concat(a, b), c);
```

Với ba nguồn nhỏ, code này ổn. Nhưng nếu viết vòng lặp nối một Stream mới với kết quả cũ **hàng nghìn/hàng chục nghìn lần**, cấu trúc có thể rất sâu. Javadoc `Stream.concat` cảnh báo **deep call chains** và thậm chí `StackOverflowError` khi truy cập phần tử trên một Stream được lồng `concat` quá sâu.

**Cách thường được khuyến nghị khi có nhiều nguồn:**

```java
Stream<String> all = Stream.of(
        Stream.of("A"),
        Stream.of("B"),
        Stream.of("C")
).flatMap(Function.identity());

List<String> result =
        all.collect(Collectors.toList());

// [A, B, C]
```

Đây là Java 8-compatible code. `Stream.of(s1, s2, s3)` tạo **Stream<Stream<String>>**, rồi `flatMap(Function.identity())` làm phẳng các Stream con thành một chuỗi phần tử.

Javadoc `concat` cũng nêu `Stream.of(s1,s2,s3,s4).flatMap(s -> s)` như phương án để nối nhiều nguồn **không lồng các lần `concat`**.

### 11.1. Không nhầm Stream các Stream với Stream phần tử

```java
Stream<Stream<String>> nested = Stream.of(
        Stream.of("A"),
        Stream.of("B")
);
```

`nested` chứa **hai đối tượng Stream**, không chứa trực tiếp hai giá trị `"A"`, `"B"`. Nếu collector `toList()` ngay, kết quả sẽ là List các Stream, không phải List<String>.

Đúng:

```java
List<String> values = Stream.of(
        Stream.of("A"),
        Stream.of("B")
).flatMap(Function.identity())
 .collect(Collectors.toList());

// [A, B].
```

### 11.2. Nguồn của bạn đã là `List<List<T>>` hoặc `List<Collection<T>>`?

Khi các nguồn nằm sẵn trong một collection, thường không cần tạo từng Stream bằng tay:

```java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("a", "b"),
        Arrays.asList("c"),
        Arrays.asList("d", "e")
);

List<String> flattened = groups.stream()
        .flatMap(List::stream)
        .collect(Collectors.toList());

// [a, b, c, d, e].
```

Lúc này `flatMap` là đúng mô hình: **mỗi List trong groups là một nguồn con**, và ta ghép phần tử của các nguồn đó theo thứ tự các nhóm. Với `groups` là List ordered và mỗi nhóm ordered, pipeline sequential cho kết quả có thứ tự rõ ràng.

### 11.3. Dùng `concat` hay `flatMap`?

| Tình huống | Cách phù hợp thường gặp |
| --- | --- |
| Có đúng hai Stream rõ ràng | `Stream.concat(a, b)` — đơn giản, trực tiếp |
| Có ba nguồn nhỏ, cố định | Lồng một vài `concat` hoặc `Stream.of(...).flatMap(...)` |
| Có rất nhiều nguồn Stream | `Stream.of(streams...).flatMap(Function.identity())` hoặc nguồn chứa streams |
| Có `List<List<T>>` | `groups.stream().flatMap(List::stream)` |
| Nối primitive streams | `IntStream/LongStream/DoubleStream.concat` hoặc `flatMapToInt` tương ứng |
| Muốn gộp bản ghi theo khóa, sort hoặc loại trùng | Chỉ `concat` không đủ; thêm operation phù hợp |
| Nguồn gắn với tài nguyên I/O | Thiết kế close/ownership rõ ràng trước khi chọn biểu thức |

Không có quy tắc “flatMap luôn nhanh hơn concat” hoặc ngược lại. Với đúng hai nguồn, `concat` ngắn gọn và có cơ hội tối ưu size. Với nhiều nguồn động, tránh cây lồng sâu thường là lý do kiến trúc quan trọng hơn microbenchmark.

## 12. Đóng Stream kết quả và cả hai nguồn

Đây là một trong những hành vi quan trọng của `concat` được ghi rõ trong Javadoc:

> Khi Stream kết quả được đóng, close handlers của **cả hai Stream đầu vào** được gọi.

Ví dụ:

```java
Stream<String> left = Stream.of("A")
        .onClose(() -> System.out.println("close left"));

Stream<String> right = Stream.of("B")
        .onClose(() -> System.out.println("close right"));

try (Stream<String> joined = Stream.concat(left, right)) {
    System.out.println(
            joined.collect(Collectors.joining(",")));
}
// Đóng joined sẽ kích hoạt handlers của left và right.
```

Đây là đoạn minh họa cơ chế đóng; nếu cần một stdout tuyệt đối ổn định, đừng phụ thuộc một thứ tự log close handlers không được bạn xác nhận bằng chính hợp đồng API. Ở chương trình chạy độc lập của bài, việc kiểm tra close được làm bằng cách thu thập các nhãn rồi sắp xếp trước khi in.

### 12.1. Terminal operation không tự đóng Stream

```java
Stream<String> left = Stream.of("A")
        .onClose(() -> System.out.println("closed"));

Stream<String> joined =
        Stream.concat(left, Stream.of("B"));

long count = joined.count(); // 2
// Handler "closed" không tự chạy chỉ vì count() hoàn tất.

joined.close(); // Đây mới là thao tác close.
```

`close()` khác với terminal operation như `count()` hay `collect()`. Việc đã đọc hết các phần tử không tự tương đương `close()`. Với các nguồn Collection/array thông thường, thường không cần close để giải phóng tài nguyên hệ thống; với file/socket/IO, phải có chính sách close rõ ràng.

### 12.2. `onClose` để đăng ký cleanup

`BaseStream.onClose(Runnable)` đăng ký một handler chạy khi Stream được đóng. Đây là API lifecycle, không phải một intermediate operation xử lý từng phần tử.

```java
Stream<String> s = Stream.of("A")
        .onClose(() -> releaseSomeResource());
```

`releaseSomeResource()` ở đây là phương thức **giả định của ứng dụng**, không thuộc Java SE; đoạn code chỉ minh họa ý nghĩa của `onClose`. Handler sẽ được gọi khi Stream được đóng, không phải mỗi lần một phần tử được duyệt.

Đừng dùng `onClose` để thay thế `map`/`forEach`, hoặc kỳ vọng nó tự chạy sau mỗi terminal.

### 12.3. Exception khi đóng nhiều nguồn

Một close handler có thể ném exception. API Stream định nghĩa việc các close handlers liên quan vẫn được xem xét; ngoại lệ đầu tiên có thể được ném và các ngoại lệ khác được thêm dưới dạng suppressed theo hợp đồng thích hợp. Không nuốt exception đóng tài nguyên một cách im lặng trong mã xử lý file.

Với I/O, `try-with-resources` giúp quản lý việc đóng ngay cả khi terminal operation ném lỗi trong lúc duyệt. Khi cần xử lý lỗi I/O và lỗi cleanup, xem cả suppressed exceptions để không mất thông tin chẩn đoán.

## 13. Nối hai nguồn file: quản lý tài nguyên đúng cách

Một tình huống phổ biến là nối các dòng từ hai file. `Files.lines(path)` trả `Stream<String>` gắn với tài nguyên I/O, nên phải đóng sau sử dụng.

Ví dụ method Java 8-compatible:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readBoth(Path first, Path second)
        throws IOException {

    try (Stream<String> a =
                 Files.lines(first, StandardCharsets.UTF_8);
         Stream<String> b =
                 Files.lines(second, StandardCharsets.UTF_8);
         Stream<String> combined = Stream.concat(a, b)) {

        return combined.collect(Collectors.toList());
    }
}
```

Đây là **một method minh họa trong một lớp**, không phải file chạy độc lập. Các nguồn `a` và `b` được quản lý bằng `try-with-resources`, và `combined` cũng đóng trong cùng scope. Khi gọi `combined.close()`, các close handlers của hai input streams được gọi; việc đóng lại trực tiếp `b`/`a` theo `try-with-resources` là idempotent theo hợp đồng `BaseStream.close()`.

Việc khai báo nguồn trong danh sách resource bảo đảm nếu **mở file thứ hai thất bại**, resource đầu tiên đã mở vẫn được đóng theo quy tắc `try-with-resources`. Đây là lý do an toàn hơn so với tạo hai `Files.lines` bên trong biểu thức `Stream.concat(...)` mà không quản lý tình huống khởi tạo một nửa:

```java
// Không khuyến nghị khi cả hai factory mở tài nguyên:
// Stream<String> both = Stream.concat(
//         Files.lines(first), Files.lines(second));
```

Nếu `Files.lines(second)` ném exception sau khi nguồn thứ nhất đã mở, bạn có thể không có biến sở hữu nguồn thứ nhất để cleanup đúng cách. Hãy dùng scope resource rõ ràng như ví dụ trước.

### 13.1. `concat` không đồng nghĩa đọc hết file đầu rồi mới mở file sau

`Files.lines` có thể mở tài nguyên khi factory được gọi; cả hai factory `a` và `b` được thực hiện **trước** khi `concat` và terminal duyệt các dòng. Điều bảo đảm là **sequence logic** của phần tử đầu ra khi hai nguồn ordered: dòng từ file A trước dòng từ file B.

Nếu cần “đọc file A, đóng A hoàn toàn rồi **mới mở** file B”, hãy thiết kế logic nguồn tuần tự khác, không mặc định `Stream.concat(Files.lines(a),Files.lines(b))` có trình tự mở/đóng như vậy.

### 13.2. Dừng sớm không miễn trừ trách nhiệm close

```java
try (Stream<String> a = Files.lines(first);
     Stream<String> b = Files.lines(second);
     Stream<String> both = Stream.concat(a, b)) {

    Optional<String> match = both.filter(s -> s.contains("ERROR"))
            .findFirst();
}
```

Đoạn này minh họa trong một method có `Path first, second` và xử lý `IOException` phù hợp. `findFirst()` có thể kết thúc trước khi đọc hết hai file, nhưng cả hai nguồn đã mở vẫn cần đóng.

Lưu ý kiểu ký tự: nếu không truyền `StandardCharsets.UTF_8`, overload `Files.lines(Path)` hiện đại dùng UTF-8 theo API. Khi hệ thống có encoding khác, chỉ định charset đúng hợp đồng dữ liệu.

## 14. Nối nhiều nguồn có thứ tự: ví dụ ứng dụng nghiệp vụ

### 14.1. Dữ liệu lịch sử trước dữ liệu hiện tại

```java
List<String> history = Arrays.asList("H1", "H2");
List<String> live = Arrays.asList("L1", "L2");

List<String> events = Stream.concat(
        history.stream(),
        live.stream()
).collect(Collectors.toList());

// [H1, H2, L1, L2]
```

Đây là *append semantics*: sự kiện lịch sử được xếp trước sự kiện hiện tại. Nhưng nó không tự kiểm tra timestamp. Nếu `live` chứa sự kiện timestamp cũ hơn `history`, `concat` vẫn nối theo thứ tự nguồn, **không tự merge theo thời gian**.

Nếu yêu cầu một timeline toàn cục theo timestamp, bạn phải sắp xếp hoặc dùng thuật toán merge có comparator. Việc đó có chi phí và ngữ nghĩa khác.

### 14.2. Kết hợp dữ liệu dự phòng

```java
Stream<String> preferred = Stream.of("A", "B");
Stream<String> fallback = Stream.of("C");

List<String> results = Stream.concat(
        preferred, fallback)
        .collect(Collectors.toList());

// [A, B, C].
```

**Không nhầm với failover:** `concat` nối **cả hai nguồn**, không có nghĩa chỉ chạy fallback nếu preferred không có kết quả. Nếu nghiệp vụ thật sự cần “nếu A rỗng thì dùng B”, bạn cần kiểm tra điều kiện và thiết kế fallback có khả năng trì hoãn mở B khi không cần.

Có thể kết hợp `findFirst` với nguồn phụ trong một số tình huống để tránh duyệt hết B, nhưng **không bảo đảm B không được khởi tạo**, vì cả hai Stream đều được xây trước khi gọi `concat`.

### 14.3. Nối các kết quả phân trang

```java
List<String> page1 = Arrays.asList("P1-A", "P1-B");
List<String> page2 = Arrays.asList("P2-A", "P2-B");

List<String> all = Stream.concat(
        page1.stream(),
        page2.stream()
).collect(Collectors.toList());
```

Đối với một số lượng trang nhỏ và đã có trong bộ nhớ, `concat` phù hợp. Đối với **rất nhiều trang hoặc trang cần tải theo mạng**, nên thiết kế nguồn lazily loading/backpressure và giới hạn truy cập riêng; đừng tạo một cây `concat` sâu hoặc mở tất cả request trước khi xử lý.

### 14.4. Nối nguồn nhưng muốn loại trùng theo khóa

`distinct()` dùng `equals`/`hashCode` của phần tử. Nếu dữ liệu là record nghiệp vụ mà “trùng” được xác định bởi `id`, cần chiến lược đúng theo khóa. Không có tham số kiểu `distinctByKey` trong Stream API Java 8. Bạn có thể:

- Định nghĩa `equals`/`hashCode` của value object theo đúng identity nghiệp vụ nếu phù hợp.
- Dùng một collector tạo `Map<Id,Record>` với merge policy rõ ràng.
- Dùng bước nhóm hoặc giải quyết xung đột theo id tường minh.

Đừng sửa `equals` của một domain entity chỉ để một đoạn `concat(...).distinct()` có kết quả mong muốn khi điều đó mâu thuẫn với ngữ nghĩa toàn hệ thống.

## 15. Thời điểm tiêu thụ và lỗi reuse Stream

Một Stream không phải Collection tái duyệt được. Sau khi đưa input stream vào `Stream.concat(a,b)`, các input streams đã tham gia vào một pipeline mới, vì vậy không được dùng chúng lại như hai nguồn độc lập.

```java
Stream<String> a = Stream.of("A", "B");
Stream<String> b = Stream.of("C");

Stream<String> combined = Stream.concat(a, b);
long count = combined.count(); // 3

// KHÔNG HỢP LỆ theo nguyên tắc single-use:
// long again = a.count();
// long twice = combined.count();
```

Một implementation thường phát hiện reuse và ném `IllegalStateException`, nhưng API không hứa mọi dạng reuse sai đều được phát hiện theo một cách nhất quán. Không dùng thành công tình cờ của một lời gọi lại làm bằng chứng code đúng.

Nếu muốn hai phép tính độc lập từ hai Collections, hãy **tạo Stream mới mỗi lần**:

```java
List<String> a = Arrays.asList("A", "B");
List<String> b = Arrays.asList("C");

long count = Stream.concat(a.stream(), b.stream()).count();

List<String> copy = Stream.concat(a.stream(), b.stream())
        .collect(Collectors.toList());
```

Ở đây `a.stream()` và `b.stream()` được gọi lại, tạo **Stream mới** từ collection nguồn (khi collection còn ở trạng thái phù hợp).

## 16. Stream vô hạn khi nối: một bẫy logic

Một nguồn Stream có thể vô hạn, ví dụ `Stream.iterate` hoặc `Stream.generate`. Với nối logic A trước B, nếu A vô hạn và không bị giới hạn, những phép duyệt ordered sequential thông thường sẽ không bao giờ đi đến phần tử B:

```java
Stream<Long> infinite = Stream.iterate(0L, n -> n + 1);
Stream<Long> finite = Stream.of(100L, 200L);

// KHÔNG CHẠY collect() không giới hạn trên dòng sau:
// Stream.concat(infinite, finite)
//       .collect(Collectors.toList());
```

Vì đầu vào A không bao giờ kết thúc, terminal muốn thu mọi phần tử sẽ không thể hoàn tất bình thường.

### 16.1. Giới hạn riêng nhánh A trước khi nối

```java
List<Long> values = Stream.concat(
        Stream.iterate(0L, n -> n + 1).limit(3),
        Stream.of(100L, 200L)
).collect(Collectors.toList());

// [0, 1, 2, 100, 200].
```

`limit(3)` trong **nhánh A** làm A hữu hạn, vì vậy Stream kết quả có thể đi tới B.

### 16.2. `limit` sau concat khác `limit` trên nhánh A

```java
List<Long> first = Stream.concat(
        Stream.iterate(0L, n -> n + 1),
        Stream.of(100L)
).limit(3).collect(Collectors.toList());

// [0, 1, 2].
```

Ở đây `limit(3)` áp dụng lên **Stream kết quả**, vì vậy chỉ có ba phần tử đầu A, B không xuất hiện. Cả hai ví dụ kết thúc, nhưng ý nghĩa nghiệp vụ khác nhau.

Cần xác định bạn muốn **lấy N phần tử của toàn bộ nguồn nối** hay **lấy N phần tử từ một nguồn rồi tiếp tục nguồn sau**. Không hoán đổi vị trí `limit` tùy tiện.

## 17. `concat`, `flatMap`, `reduce` và `collect` khác nhau thế nào?

| Công cụ | Hình dung | Khi nên dùng |
| --- | --- | --- |
| `Stream.concat(a,b)` | Nối hai Stream thành một sequence | Có đúng hai Stream, muốn giữ thứ tự logic A rồi B |
| `Stream.of(s1,s2,...).flatMap(identity)` | Làm phẳng Stream các Stream | Nhiều nguồn, tránh nối sâu |
| `groups.stream().flatMap(Collection::stream)` | Làm phẳng Collection của các Collection | Nguồn nhiều nhóm đã lưu trong Collection |
| `collect(Collectors.toList())` | Đưa Stream vào List kết quả | Cần lưu trữ kết quả |
| `collect(Collectors.joining(...))` | Nối các chuỗi phần tử thành một String | Đầu ra là một chuỗi văn bản |
| `reduce(...)` | Gộp nhiều phần tử thành một giá trị bằng phép kết hợp | Tổng, tích, các phép aggregate phù hợp |
| `sorted(comparator)` | Sắp xếp phần tử | Cần thứ tự theo khóa/comparator |
| `distinct()` | Bỏ các phần tử trùng theo equality | Cần unique elements |
| `flatMap` có mapper sinh Stream mới | Một phần tử nguồn có thể tạo nhiều phần tử đầu ra | Quan hệ một-nhiều |

Một nhầm lẫn phổ biến là dùng `concat` khi thực chất cần **join** hai tập dữ liệu theo khóa. `concat` chỉ xếp các phần tử thành một chuỗi; không ghép cặp, không tra cứu theo key và không hợp nhất các trường.

## 18. Những lỗi thường gặp và cách sửa

### Lỗi 1: Tưởng `concat` tạo List mới ngay

`Stream.concat` trả `Stream<T>`, không phải `List<T>`. Khi cần danh sách, dùng terminal `collect(Collectors.toList())` hoặc `toList()` trên JDK hỗ trợ.

### Lỗi 2: Nghĩ `concat` tự loại trùng hoặc sắp xếp

Nó nối hai sequences. Nếu muốn unique/sorted, phải thêm `distinct` hoặc `sorted` đúng ngữ nghĩa. Việc thêm stage có thể tăng chi phí và làm mất ưu điểm duyệt lười.

### Lỗi 3: Dùng `Stream.of(a,b)` với hai Stream rồi quên `flatMap`

`Stream.of(a,b)` tạo `Stream<Stream<T>>`, không phải `Stream<T>`. Dùng `Stream.concat(a,b)` hoặc `Stream.of(a,b).flatMap(Function.identity())`.

### Lỗi 4: Nối hàng nghìn Stream bằng một chuỗi `concat` lồng sâu

Javadoc cảnh báo call chains sâu và nguy cơ `StackOverflowError`. Với rất nhiều nguồn, dùng Stream các Stream + `flatMap` hoặc thiết kế nguồn phù hợp để tránh cấu trúc lồng sâu.

### Lỗi 5: Đổi nguồn sau `concat` rồi đòi kết quả luôn cập nhật

`concat` binds input streams to sources. Không dựa vào sửa collection sau khi nối như một cách cập nhật Stream kết quả; chuẩn bị dữ liệu rồi tạo pipeline, hoặc thiết kế nguồn có hợp đồng cập nhật rõ.

### Lỗi 6: Cho rằng `concat` luôn sequential

Nếu **một** đầu vào parallel, kết quả parallel. Kiểm tra `isParallel()` khi quan trọng; đổi mode của Stream kết quả nếu cần. Không dùng mode như bằng chứng số thread.

### Lỗi 7: Tin rằng parallel `forEach` giữ thứ tự A trước B trong log

Với parallel execution, `forEach` không giữ encounter order. Dùng `forEachOrdered` nếu side effect cần thứ tự; hoặc tập trung kết quả qua ordered collector.

### Lỗi 8: Chỉ có một input stream null nên coi như rỗng

`null` không phải `Stream.empty()`. Không truyền null cho `concat`; quyết định rõ chính sách khi không có nguồn.

### Lỗi 9: Dùng lại Stream đầu vào hoặc Stream đã nối

Stream single-use. Sau khi dựng phép nối, không tiếp tục tiêu thụ hai Stream đầu vào như các pipeline riêng. Tạo Stream mới khi cần một lần tính khác.

### Lỗi 10: Tưởng terminal tự gọi `close()`

`count`, `collect`, `findFirst` không tự thay thế `close`. Khi nguồn gắn với file/socket/I/O, dùng `try-with-resources` và quản lý nguồn ngay cả khi short-circuit.

### Lỗi 11: Đóng Stream kết quả rồi vẫn cần dùng đầu vào

Đóng Stream kết quả sẽ gọi close handlers của cả hai input streams. Không chia sẻ input stream có tài nguyên giữa nhiều chủ sở hữu mà không xác định rõ lifecycle.

### Lỗi 12: Dùng `concat` cho nguồn vô hạn A nhưng muốn đi tới B

Nếu A vô hạn, phép duyệt ordered sequential không có điểm chuyển sang B khi không cắt A. Đặt `limit` vào nhánh A theo ý nghĩa nghiệp vụ.

### Lỗi 13: Cho rằng `peek` sẽ luôn chạy đủ trong `concat(...).count()`

`count` có thể dùng metadata kích thước để tối ưu. Side effects trong intermediate stages không phải hợp đồng kiểm toán/logging.

### Lỗi 14: Đọc file B “chỉ khi cần” nhưng tạo `Files.lines(B)` ngay

`Files.lines` có thể mở resource khi factory được gọi, mặc dù dữ liệu chưa được duyệt. `concat` nhận cả hai Stream đã được tạo. Nếu mục tiêu là trì hoãn **mở** B, thiết kế resource supplier/lazy source rõ ràng thay vì chỉ trông đợi terminal short-circuit.

### Lỗi 15: Chuyển `IntStream` trực tiếp vào `Stream.concat`

Primitive streams dùng `IntStream.concat`, `LongStream.concat` hoặc `DoubleStream.concat`. Nếu cần object Stream, có thể `boxed()`.

## 19. Chương trình Java hoàn chỉnh: nối nguồn, ngữ nghĩa và lifecycle

Tạo file **`ConcatSourcesDemo.java`**. Chương trình chỉ dùng API có từ Java 8, biên dịch/chạy với JDK 17+ và **không phụ thuộc scheduling của parallel workers** để xác định stdout.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ConcatSourcesDemo {

    public static void main(String[] args) {
        List<String> first = Arrays.asList("A", "B");
        List<String> second = Arrays.asList("C", "D");

        List<String> basic = Stream.concat(
                first.stream(), second.stream())
                .collect(Collectors.toList());
        System.out.println("Basic: " + basic);

        boolean parallel = Stream.concat(
                first.stream().parallel(), second.stream())
                .isParallel();
        System.out.println("Parallel mode: " + parallel);

        List<String> ordered = Stream.concat(
                first.parallelStream(), second.stream())
                .collect(Collectors.toList());
        System.out.println("Parallel ordered: " + ordered);

        System.out.println("Pipeline creation:");
        Stream<String> lazy = Stream.concat(
                Stream.of("a", "b").map(s -> {
                    System.out.println("left map " + s);
                    return s.toUpperCase(Locale.ROOT);
                }),
                Stream.of("c").map(s -> {
                    System.out.println("right map " + s);
                    return s.toUpperCase(Locale.ROOT);
                })
        );
        System.out.println("Before terminal:");
        List<String> two = lazy.limit(2)
                .collect(Collectors.toList());
        System.out.println("First two: " + two);

        List<Integer> unique = Stream.concat(
                Stream.of(1, 2, 2),
                Stream.of(2, 3))
                .distinct()
                .collect(Collectors.toList());
        System.out.println("Unique: " + unique);

        List<String> many = Stream.of(
                Stream.of("L"),
                Stream.of("M"),
                Stream.of("R"))
                .flatMap(Function.identity())
                .collect(Collectors.toList());
        System.out.println("Many sources: " + many);

        int primitiveSum = IntStream.concat(
                IntStream.of(1, 2),
                IntStream.of(3, 4))
                .sum();
        System.out.println("Primitive sum: " + primitiveSum);

        Optional<String> firstValue = Stream.concat(
                Stream.of("X", "Y"),
                Stream.of("Z")).findFirst();
        System.out.println("First value: " + firstValue.get());

        List<String> events = new ArrayList<>();
        Stream<String> left = Stream.of("left")
                .onClose(() -> events.add("left"));
        Stream<String> right = Stream.of("right")
                .onClose(() -> events.add("right"));

        try (Stream<String> combined =
                     Stream.concat(left, right)) {
            long count = combined.count();
            System.out.println("Before close events: "
                    + events.size());
            System.out.println("Close demo count: " + count);
        }

        Collections.sort(events);
        System.out.println("Close events: " + events);

        long count = Stream.concat(
                Stream.of("A", "B"),
                Stream.of("C")).count();
        System.out.println("Count: " + count);
    }
}
```

Biên dịch/chạy:

```bash
javac ConcatSourcesDemo.java
java ConcatSourcesDemo
```

**Stdout của chương trình:**

```text
Basic: [A, B, C, D]
Parallel mode: true
Parallel ordered: [A, B, C, D]
Pipeline creation:
Before terminal:
left map a
left map b
First two: [A, B]
Unique: [1, 2, 3]
Many sources: [L, M, R]
Primitive sum: 10
First value: X
Before close events: 0
Close demo count: 2
Close events: [left, right]
Count: 3
```

### Giải thích chương trình

1. **Basic**: nối hai ordered List sources thành `[A,B,C,D]`.
2. **Parallel mode**: input trái ở parallel mode nên Stream kết quả có `isParallel() == true`.
3. **Parallel ordered**: kết quả collector vẫn giữ encounter order của hai List; không ghi log từ callback của parallel pipeline.
4. **Pipeline creation**: chỉ tạo `Stream.concat` và đăng ký mapper; không có log `left map` hoặc `right map` trước dòng `Before terminal`.
5. **Short-circuit**: `limit(2)` trên Stream ordered sequential chỉ cần hai phần tử từ nhánh trái; mapper nhánh phải không tham gia lấy phần tử kết quả.
6. **Unique**: `distinct` sau nối bỏ duplicate và giữ lần xuất hiện đầu trên ordered stream.
7. **Many sources**: `Stream.of(streams...).flatMap(Function.identity())` làm phẳng ba nguồn theo thứ tự L, M, R mà không cần cây `concat` lồng.
8. **Primitive sum**: `IntStream.concat` giữ primitive pipeline, tổng 1+2+3+4 = 10.
9. **First value**: `findFirst` lấy X từ đầu nguồn trái trong sequence ordered.
10. **Lifecycle**: `count()` hoàn tất nhưng chưa kích hoạt close handlers; `events.size() == 0` trước khi kết thúc `try-with-resources`.
11. **Close both**: khi kết thúc `try`, `combined.close()` gọi close handlers của cả left/right. Ta sắp xếp các nhãn trước khi in để **không đưa ra giả định về thứ tự thực hiện handler** khi mục tiêu test chỉ là kiểm tra cả hai được gọi.
12. **Count**: `count()` trên nguồn khác trả 3; chương trình không dựa vào callback side effect được gọi.

**Lưu ý QA:** ví dụ không cố in thứ tự `parallel forEach`, tên thread hay thông số thời gian, vì các giá trị đó không được Java Stream API cam kết cố định. Các ví dụ lỗi biên dịch và nguồn vô hạn ở mục khác đã được tách riêng và không nằm trong file chạy này.

## 20. Kiểm thử khi dùng `concat` trong production

### 20.1. Kiểm thử thứ tự và giá trị

Đặt test cho các ca:

- A có phần tử, B có phần tử.
- A rỗng, B có phần tử.
- A có phần tử, B rỗng.
- Cả hai rỗng.
- Trùng phần tử giữa A và B.
- Một nguồn có null nếu hợp đồng cho phép.
- Hai nguồn có encounter order và một nguồn unordered.
- Nguồn có nhiều phần tử và pipeline có short-circuit.

Chỉ kiểm tra thứ tự khi **nguồn và operation đều hứa encounter order**. Nếu nguồn là `HashSet` không ordered, test so sánh tập hợp hoặc sắp xếp đầu ra trước khi so sánh.

### 20.2. Kiểm thử mode nhưng không test số thread

Nếu nghiệp vụ cần xác minh mode:

```java
boolean p = Stream.concat(
        Stream.of(1).parallel(), Stream.of(2)
).isParallel(); // true
```

Không assert “đúng 4 worker” hay “mapper chạy trên ForkJoinPool nào”, vì đó không phải hợp đồng ổn định của phép nối.

### 20.3. Kiểm thử close ở cả hai nguồn

Dùng `onClose` hoặc fake closeable resources để assert khi **Stream kết quả được đóng**, cleanup của cả hai nguồn đã xảy ra. Test lỗi trong terminal và lỗi đóng nguồn riêng biệt. Không chỉ test terminal success rồi nghĩ rằng mọi tài nguyên đều đã được cleanup.

### 20.4. Kiểm thử không reuse

Nếu API trả một Stream kết quả cho caller, hãy ghi rõ **caller sở hữu và tiêu thụ/đóng Stream**. Đừng đồng thời chia sẻ hai input streams ra bên ngoài để những phần khác của ứng dụng tiêu thụ lần nữa. Nếu cần reuse dữ liệu, truyền Collections, arrays, hoặc một `Supplier<Stream<T>>` có khả năng tạo nguồn mới theo hợp đồng.

### 20.5. Kiểm thử số nguồn và khả năng mở rộng

Với đúng hai nguồn nhỏ, `concat` đơn giản. Với hàng nghìn nguồn, test độ sâu cấu trúc, thời gian mở resources, mức bộ nhớ và khả năng hủy/đóng. Tránh viết code:

```java
Stream<T> result = Stream.empty();
for (Stream<T> next : sources) {
    result = Stream.concat(result, next);
}
```

Đây là **mã minh họa generic trong ngữ cảnh `sources` có sẵn**, không phải file chạy độc lập. Nó tạo một chain nối ngày càng sâu. Nếu danh sách nguồn lớn, ưu tiên một luồng nguồn cấp streams rồi `flatMap` hoặc thiết kế custom Spliterator thích hợp khi có yêu cầu cao.

## 21. Bảng quyết định nhanh

| Nhu cầu | Giải pháp khuyến nghị | Cảnh báo |
| --- | --- | --- |
| Nối A rồi B, cả hai là Stream | `Stream.concat(a,b)` | Input streams single-use |
| Nối hai List mà cần một List kết quả | `Stream.concat(a.stream(),b.stream()).collect(toList())` | Không tự deep-copy phần tử |
| Nối số nguyên primitive | `IntStream.concat(a,b)` | Đừng boxing không cần thiết |
| Nối rất nhiều Stream | `Stream.of(...).flatMap(identity)` | Quản lý nguồn/lifecycle rõ ràng |
| Nối nhiều Collections đã ở trong List | `groups.stream().flatMap(Collection::stream)` | Không giả định các groups unordered có order |
| Muốn unique | `concat(...).distinct()` | Equality, stateful/buffering |
| Muốn sorted global | `concat(...).sorted(comparator)` | Cần so sánh toàn bộ các phần tử liên quan |
| Muốn chỉ N phần tử của toàn sequence | `concat(a,b).limit(n)` | Có thể chỉ duyệt A |
| Muốn N phần tử A rồi tiếp B | `concat(a.limit(n),b)` | Khác ngữ nghĩa limit sau concat |
| Muốn một chuỗi văn bản | `concat(...).collect(joining(delimiter))` | Dấu nối do collector |
| Muốn xử lý song song | Dùng input parallel hoặc `parallel()` trên kết quả khi phù hợp | Không cam kết nhanh hơn hoặc callback order |
| Hai nguồn file | `Files.lines` + `try-with-resources` + `concat` | Mở/đóng resource an toàn, kể cả khi lỗi |
| Muốn fallback nếu A rỗng | Thiết kế điều kiện fallback riêng | `concat` luôn có cả hai nguồn logic |
| Muốn merge theo timestamp/key | Thuật toán merge/sort/group tương ứng | `concat` không join theo key |

## 22. Checklist trước khi đưa code nối Stream vào hệ thống

1. Có **đúng hai Stream** hay nhiều nguồn động? Với nhiều nguồn, cân nhắc `flatMap`.
2. Các nguồn có **encounter order** không? Nếu có, bạn có cần giữ thứ tự A rồi B không?
3. Các đầu vào là Stream objects đã được tiêu thụ trước đó chưa? Không reuse.
4. Đã chọn đúng **kiểu phần tử generic** chưa? Nếu là primitive, cân nhắc `IntStream/LongStream/DoubleStream.concat`.
5. Có thể có **null Stream argument** không? Xử lý rõ bằng policy; không tự coi null là empty.
6. Có thể có **null element** không? Các downstream operations đã xử lý đúng chưa?
7. Có cần **distinct/sorted/join theo key** không? `concat` không thực hiện những việc đó.
8. Có nguồn vô hạn không? Nếu có, khi nào pipeline có thể đến phần tử của nguồn B?
9. Có đặt `limit` ở đúng chỗ theo nghiệp vụ: trước hay sau phép nối?
10. Có hiểu rằng `concat` **binds inputs to sources** và source mutation sau đó có thể không phản ánh trong kết quả?
11. Có dùng nguồn I/O không? Nếu có, resource được mở/đóng an toàn kể cả khi mở nguồn B hoặc terminal ném exception?
12. Có xác định quyền sở hữu Stream sau khi nối không? Ai sẽ consume và close?
13. Có cần parallel mode không? Có tránh side effects không đồng bộ, không can thiệp nguồn không?
14. Có đang test stdout không ổn định do parallel callback, thread scheduling hoặc close order không?
15. Có tối ưu đếm kích thước không? Đừng dựa vào `peek` chắc chắn được gọi khi `count`.
16. Có tạo cây `concat` quá sâu không? Tránh nguy cơ `StackOverflowError` được cảnh báo trong Javadoc.
17. Nếu nguồn là Collection mutable, có chuẩn bị dữ liệu trước khi nối hoặc snapshot đúng cách không?
18. Có kiểm thử nguồn rỗng, chỉ một nguồn có dữ liệu, trùng dữ liệu, short-circuit và lỗi resource chưa?
19. Có yêu cầu Java source level nào? `Stream.concat`, primitive `concat`, `flatMap` và `Collectors.toList` đều có từ Java 8; `Stream.toList` là Java 16+.
20. Có thể trình bày một ví dụ dễ hiểu hơn bằng vòng lặp hoặc List copy không? Đừng dùng Stream chỉ để tạo cú pháp phức tạp khi mô hình dữ liệu đơn giản.

## 23. Tự kiểm tra kiến thức

1. `Stream.concat(a,b)` trả `List<T>` hay `Stream<T>`?
2. Khi nào các phần tử ở B xuất hiện sau A trong encounter order?
3. Nếu A sequential nhưng B parallel, `concat(a,b).isParallel()` trả gì?
4. Vì sao `concat(a,b)` lazy nhưng việc sửa collection nguồn **sau khi gọi concat** có thể không phản ánh trong kết quả?
5. `Stream.concat(Stream.empty(), Stream.of("A"))` khác gì `Stream.concat(null, Stream.of("A"))`?
6. `Stream.concat(Stream.of("A"),Stream.of("B")).count()` có bắt buộc gọi mọi callback `peek` không?
7. `Stream.of(streamA,streamB)` chứa những kiểu phần tử gì? Cần thêm operation nào để lấy `Stream<T>`?
8. Vì sao lặp `result=Stream.concat(result,next)` hàng nghìn lần có thể nguy hiểm?
9. `IntStream.of(1,2)` có truyền trực tiếp được vào `Stream.concat` không?
10. Nếu A là một Stream vô hạn và không bị giới hạn, `concat(A,B).collect(toList())` có thể hoàn tất bình thường không?
11. Sự khác nhau giữa `concat(A.limit(3), B)` và `concat(A,B).limit(3)` là gì?
12. Nếu hai input streams có `onClose` handlers, đóng Stream nối sẽ ảnh hưởng những handler nào?
13. Gọi `collect` có tự đóng Stream gắn với file không?
14. Nếu mở file A thành công nhưng mở file B thất bại, `try-with-resources` nên được bố trí thế nào để không rò tài nguyên A?
15. Vì sao kết quả ordered `collect(toList())` có thể đúng thứ tự dù callback chạy song song khác thứ tự?
16. `concat` tự loại trùng phần tử giữa hai nguồn không?
17. Muốn gộp hai tập bản ghi theo timestamp, chỉ `concat` có đủ không?
18. Vì sao không nên phụ thuộc `findAny` để lấy phần tử ưu tiên của nguồn A?
19. Hai Stream đã được đưa vào `concat` có nên tiếp tục được consume riêng không?
20. Khi nào nên chọn `flatMap` thay vì `concat`?

**Kết luận:** `Stream.concat(a,b)` là công cụ chuẩn và trực tiếp để **nối hai Stream** thành một sequence lazy trong Java. Nó giữ ngữ nghĩa A rồi B khi các nguồn có encounter order, đưa Stream kết quả vào parallel mode nếu một đầu vào parallel, và truyền trách nhiệm close tới cả hai nguồn. Nhưng `concat` cũng **binds inputs to sources**, chỉ nhận hai Stream, không tự loại trùng/sort/merge theo khóa và không biến nguồn I/O thành tài nguyên tự đóng sau terminal. Với hai nguồn rõ ràng, dùng `concat`; với nhiều nguồn, cân nhắc `Stream.of(streams...).flatMap(Function.identity())`; với nguồn có tài nguyên, luôn thiết kế ownership/close có thể kiểm chứng.

## Tài liệu tham khảo chuẩn

- Java SE 25 API, **`java.util.stream.Stream.concat`** (lazy concatenation, ordered/parallel, close propagation, binding input sources, deep-concat warning): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#concat(java.util.stream.Stream,java.util.stream.Stream)
- Java SE 25 API, **`java.util.stream.Stream`** (intermediate/terminal, `flatMap`, `count`, `collect`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Java SE 25 API, **`IntStream.concat`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html#concat(java.util.stream.IntStream,java.util.stream.IntStream)
- Java SE 25 API, **`LongStream.concat`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/LongStream.html#concat(java.util.stream.LongStream,java.util.stream.LongStream)
- Java SE 25 API, **`DoubleStream.concat`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/DoubleStream.html#concat(java.util.stream.DoubleStream,java.util.stream.DoubleStream)
- Java SE 25 API, **`java.util.stream.BaseStream`** (single-use, close, onClose): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html
- Java SE 25 API, **`Files.lines`** (tài nguyên I/O, UTF-8, close): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)
- Java SE 25, **`java.util.stream` package summary** (pipeline, ordering, parallel, stateless callbacks): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
