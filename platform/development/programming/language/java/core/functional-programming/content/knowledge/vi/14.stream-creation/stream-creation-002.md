# Tạo Stream với `Stream.of()`, `Stream.empty()` và `Stream.ofNullable()`

## 1. Mục tiêu

Trong Java, `java.util.stream.Stream<T>` biểu diễn một luồng phần tử để thực hiện các thao tác xử lý dữ liệu theo phong cách khai báo. Khi cần **tạo stream** từ vài giá trị, từ một nguồn không có phần tử hoặc từ một giá trị có thể bằng `null`, ba factory method thường gặp là:

- `Stream.of(...)`: tạo stream chứa **các phần tử được cung cấp**, kể cả một phần tử `null` nếu chọn đúng overload và truyền vào `null`.
- `Stream.empty()`: tạo stream **không có phần tử**.
- `Stream.ofNullable(value)`: tạo stream **có đúng một phần tử khi `value != null`**, hoặc **rỗng khi `value == null`**; được bổ sung từ **Java 9**.

Ba phương thức đều là **static factory method** trên interface `Stream`. Chúng tạo stream, nhưng không tự biến dữ liệu thành một collection hay chạy các thao tác trung gian như `map`, `filter` ngay khi thêm chúng vào pipeline.

Nắm đúng sự khác biệt này giúp tránh nhầm lẫn giữa **“không có phần tử”** với **“có một phần tử là null”**, xử lý optional input và hiểu chính xác mảng/varargs.

## 2. So sánh chữ ký API và số lượng phần tử

Các chữ ký cốt lõi (rút gọn để dễ đọc):

```java
static <T> Stream<T> of(T t)
static <T> Stream<T> of(T... values)
static <T> Stream<T> empty()
static <T> Stream<T> ofNullable(T t) // Java 9+
```

Đây là **chữ ký minh họa**, không phải một class Java có thể biên dịch độc lập.

| Lời gọi | Số phần tử | Ý nghĩa |
| --- | ---: | --- |
| `Stream.of("a")` | 1 | Một phần tử `"a"` |
| `Stream.of("a", "b")` | 2 | Hai phần tử theo thứ tự `a`, `b` |
| `Stream.of()` | 0 | Không có đối số varargs; stream rỗng |
| `Stream.empty()` | 0 | Stream rỗng, nói rõ ý định |
| `Stream.ofNullable("a")` | 1 | Có giá trị không-null |
| `Stream.ofNullable(null)` | 0 | Giá trị vắng mặt |
| `Stream.of((String) null)` | 1 | **Có một phần tử null** |
| `Stream.of("a", null)` | 2 | Hai phần tử, phần tử thứ hai là null |

Khi nói “stream rỗng”, tức là stream không chứa phần tử: `count() == 0`. Một stream chứa duy nhất phần tử `null` vẫn có kích thước một phần tử. **Null không phải là tín hiệu tự động làm Stream bỏ qua phần tử.**

Lưu ý `Stream.of()` không đối số và `Stream.empty()` đều tạo stream rỗng; `empty()` thường diễn đạt ý định rõ hơn khi dữ liệu đã được xác định là không có. Với generic phức tạp, có thể chỉ rõ kiểu bằng `Stream.<String>empty()` hoặc `Stream.<String>of()`.

## 3. `Stream.of()`: từ một hoặc nhiều phần tử

### 3.1. Một phần tử và nhiều phần tử

Dùng `Stream.of(value)` khi muốn một stream có một phần tử; dùng `Stream.of(a, b, c)` khi có sẵn vài phần tử:

```java
Stream<String> one = Stream.of("Java");
Stream<String> many = Stream.of("Java", "Kotlin", "Scala");
```

Đây là đoạn mã đặt trong phương thức với import `java.util.stream.Stream`. Khi gọi terminal operation như `toList()` hoặc `count()`, các phần tử này được xử lý theo thứ tự encounter order của stream tuần tự từ nguồn `of`.

Ví dụ Java 17+ hoàn chỉnh, lưu trong `StreamFactoryDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class StreamFactoryDemo {
    public static void main(String[] args) {
        List<String> names = Stream.of("An", "Binh", "Chi")
                .map(String::toUpperCase)
                .toList();

        System.out.println(names);
        System.out.println(Stream.of("x").count());
        System.out.println(Stream.of().count());
        System.out.println(Stream.empty().count());
        System.out.println(Stream.ofNullable("Java").count());
        System.out.println(Stream.ofNullable((String) null).count());
    }
}
```

Chạy:

```bash
javac StreamFactoryDemo.java
java StreamFactoryDemo
```

Kết quả:

```text
[AN, BINH, CHI]
1
0
0
1
0
```

Giải thích:

- `Stream.of("An", "Binh", "Chi")` có ba phần tử; `map(String::toUpperCase)` biến đổi từng chuỗi; `toList()` thu kết quả.
- `Stream.of("x")` có đúng một phần tử.
- `Stream.of()` và `Stream.empty()` có 0 phần tử.
- `Stream.ofNullable("Java")` có một phần tử; `Stream.ofNullable((String) null)` rỗng.

Phương thức `Stream.toList()` được bổ sung ở **Java 16**, vì vậy các chương trình chạy độc lập ở đây yêu cầu **Java 17+** như đã nêu.

### 3.2. `Stream.of()` với null: chọn overload có chủ đích

Java có hai overload `of(T)` và `of(T...)`. Do đó gọi `Stream.of(null)` trần trụi có thể bị hiểu như **mảng varargs null** thay vì một giá trị phần tử null; cách chọn overload và cảnh báo compiler làm câu lệnh này dễ gây hiểu nhầm. Đừng dùng nó để biểu diễn giá trị có thể thiếu.

Muốn kiểm thử **một phần tử là null**, viết rõ:

```java
Stream<String> singleNull = Stream.of((String) null);
```

Muốn **không tạo phần tử** nếu giá trị là null:

```java
String maybeNull = null;
Stream<String> zeroOrOne = Stream.ofNullable(maybeNull);
```

Hai stream trên khác nhau về số phần tử. Nếu xử lý bằng `map(String::length)`, stream chứa null có thể ném `NullPointerException` khi chạy terminal operation, còn `ofNullable(null)` không gọi mapper vì không có phần tử.

Đừng nhầm `Stream.of((String) null)` với `Optional.of(null)`: `Optional.of(null)` ném `NullPointerException`; stream có thể chứa null ở nguồn, nhưng nhiều thao tác downstream không chịu được null. **Có thể chứa** không đồng nghĩa **nên chứa**.

## 4. `Stream.empty()`: biểu diễn không có phần tử

`Stream.empty()` thích hợp khi một nhánh xử lý không có gì để phát ra, chẳng hạn API phải trả `Stream<String>` nhưng không tìm thấy kết quả.

Ví dụ:

```java
static Stream<String> tagsFor(boolean enabled) {
    if (!enabled) {
        return Stream.empty();
    }
    return Stream.of("java", "stream");
}
```

Đây là **một phương thức bên trong class**, cần import `Stream`; khi `enabled == false`, kết quả có 0 phần tử. Chọn stream rỗng cho phép caller tiếp tục gọi `map`, `filter`, `flatMap` và terminal operation mà không cần nhận `null`.

Trường hợp quan trọng về kiểu generic:

```java
Stream<String> none = Stream.empty();
Stream<Integer> noNumbers = Stream.empty();
Stream<String> explicit = Stream.<String>empty();
```

Java thường suy luận `T` từ ngữ cảnh gán. Nếu suy luận gặp khó khăn trong một biểu thức ghép/phương thức overload phức tạp, dùng type witness `Stream.<String>empty()` làm rõ ý định.

**Không có phép toán tính toán phần tử nào** khi gọi `count()` trên stream rỗng; terminal operation như `forEach` không có phần tử để đưa vào Consumer. Không phải cứ dùng `empty()` là có một “đối tượng rỗng” ở vị trí phần tử thứ nhất.

### Khi cần nhánh thiếu dữ liệu không ném lỗi

Lưu `EmptyStreamDemo.java`:

```java
import java.util.stream.Stream;

public class EmptyStreamDemo {
    static Stream<String> permissions(boolean active) {
        return active
                ? Stream.of("READ", "WRITE")
                : Stream.empty();
    }

    public static void main(String[] args) {
        System.out.println(permissions(true).toList());
        System.out.println(permissions(false).toList());
        System.out.println(
                permissions(false).map(String::length).count());
    }
}
```

Chạy:

```bash
javac EmptyStreamDemo.java
java EmptyStreamDemo
```

Output:

```text
[READ, WRITE]
[]
0
```

Ở trường hợp rỗng, `map(String::length)` không cần xử lý bất kỳ giá trị nào. Lưu ý rằng theo đặc tả Stream, một implementation có thể bỏ qua một số thao tác trung gian nếu biết không ảnh hưởng đến terminal result (đặc biệt với `count()` trên nguồn có kích thước xác định), nên **không dùng side effect của `map` để kiểm chứng nó có chạy hay không**. Để kiểm tra công dụng thực tế, hãy đánh giá giá trị/đầu ra quan sát được theo hợp đồng pipeline.

## 5. `Stream.ofNullable()`: 0 hoặc 1 phần tử từ một giá trị

`Stream.ofNullable(T t)` được bổ sung ở Java 9, vì nhu cầu chuyển một giá trị có thể null thành stream xuất hiện thường xuyên, đặc biệt khi phối hợp với `flatMap`:

```text
value != null  → Stream.of(value)  → 1 phần tử
value == null  → Stream.empty()    → 0 phần tử
```

Tương đương về số phần tử và giá trị với cách biểu diễn có điều kiện:

```java
static <T> Stream<T> zeroOrOne(T value) {
    return value == null ? Stream.empty() : Stream.of(value);
}
```

Đây là một phương thức generic đầy đủ phần thân nhưng cần được đặt trong class và import `java.util.stream.Stream`. Trong Java 9+, thường chỉ cần gọi `Stream.ofNullable(value)` cho rõ ràng.

Khi có kết quả của một lookup có thể bằng null:

```java
String nickname = findNickname(); // Có thể trả null.
Stream<String> stream = Stream.ofNullable(nickname);
```

Đoạn này giả định `findNickname()` đã tồn tại. Nếu nickname không có, stream rỗng; nếu tồn tại, nó có một chuỗi. Không cần tạo một collection chỉ để chuyển nullable input vào pipeline.

### Ví dụ Java 17+ lọc null bằng `flatMap`

Tạo `NullableFlatMapDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class NullableFlatMapDemo {
    public static void main(String[] args) {
        List<String> raw = List.of("Java", "Stream", "API");

        List<Integer> lengths = raw.stream()
                .map(word -> word.equals("Stream") ? null : word)
                .flatMap(Stream::ofNullable)
                .map(String::length)
                .toList();

        System.out.println(lengths);
        System.out.println(lengths.size());
    }
}
```

Chạy:

```bash
javac NullableFlatMapDemo.java
java NullableFlatMapDemo
```

Output:

```text
[4, 3]
2
```

Lần lượt:

1. `raw.stream()` tạo stream từ ba phần tử của list.
2. `map` biến riêng `"Stream"` thành `null` để mô phỏng lookup không có kết quả.
3. `flatMap(Stream::ofNullable)` thay mỗi phần tử bằng stream 0 hoặc 1 phần tử: dữ liệu null phát ra **0**, dữ liệu có mặt phát ra **1**.
4. `map(String::length)` chỉ nhìn thấy `"Java"` và `"API"`, rồi chuyển thành `4` và `3`.

`flatMap` hữu ích bởi nó ghép (flatten) các stream nhỏ phát sinh từ từng phần tử thành một stream các kết quả. Nếu dùng `map(Stream::ofNullable)` thay vì `flatMap`, kết quả là stream chứa **các đối tượng `Stream<String>` bên trong**, khác hẳn stream `String` cần xử lý tiếp.

Trong trường hợp chỉ cần loại bỏ null ở một stream sẵn có, `filter(Objects::nonNull)` cũng là lựa chọn rõ ràng:

```java
Stream<String> values = Stream.of("A", null, "B");
Stream<String> nonNull = values.filter(java.util.Objects::nonNull);
```

Đây là đoạn khai báo trong phương thức. Với `ofNullable`, mỗi input nullable trở thành một stream nhỏ, thích hợp khi đang ở chuỗi `flatMap` hoặc muốn chuyển một nullable value đơn lẻ thành stream.

## 6. Điểm dễ nhầm: `Stream.of(array)` và cơ chế varargs

`Stream.of(T... values)` sử dụng varargs, vì vậy mảng tham chiếu có thể được truyền như danh sách các phần tử. Với mảng `String[]`:

```java
String[] names = {"An", "Binh"};
Stream<String> eachName = Stream.of(names);
```

Thông thường compiler chọn overload varargs dùng mảng `String[]` làm các phần tử, tạo stream của **hai chuỗi**.

Ngược lại, khi muốn stream có **một phần tử chính là đối tượng mảng**:

```java
String[] names = {"An", "Binh"};
Stream<Object> oneArray = Stream.of((Object) names);
```

Cast sang `Object` khiến đối số đơn được xem như một object chứa mảng, nên stream có **1 phần tử kiểu `Object`** trỏ tới mảng. Việc chọn kiểu đích và overload vì thế là rất quan trọng.

Đặc biệt với **mảng nguyên thủy**:

```java
int[] numbers = {1, 2, 3};
Stream<int[]> arrayAsElement = Stream.of(numbers);
```

Kiểu của stream là `Stream<int[]>`, chỉ có **một phần tử là mảng `int[]`**; không phải ba phần tử `Integer`. Java generics không nhận kiểu nguyên thủy như tham số kiểu, vì thế `T` ở đây là `int[]`. Để tạo stream số nguyên trực tiếp từ mảng nguyên thủy, dùng `Arrays.stream(numbers)` để nhận `IntStream`, hoặc dùng `IntStream.of(1, 2, 3)`. Những factory này thuộc họ primitive stream, khác `Stream<T>`.

### Ví dụ đầy đủ để quan sát số phần tử

Lưu `StreamArrayDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.Stream;

public class StreamArrayDemo {
    public static void main(String[] args) {
        String[] names = {"An", "Binh"};
        int[] numbers = {1, 2, 3};

        System.out.println(Stream.of(names).count());
        System.out.println(Stream.of((Object) names).count());
        System.out.println(Stream.of(numbers).count());
        System.out.println(Arrays.stream(numbers).sum());
        System.out.println(Stream.of("A", "B").toList());
    }
}
```

Chạy:

```bash
javac StreamArrayDemo.java
java StreamArrayDemo
```

Output:

```text
2
1
1
6
[A, B]
```

Khi có một mảng **tham chiếu** và muốn một stream từng phần tử, `Arrays.stream(referenceArray)` cũng diễn đạt ý định rõ và tránh nhầm overload. Đừng truyền **mảng tham chiếu null** vào overload varargs rồi kỳ vọng đây là “0 phần tử”: mảng null không phải mảng rỗng. Nếu muốn không có phần tử, dùng `Stream.empty()` hoặc xử lý nguồn null bằng nhánh tường minh. `Stream.ofNullable(array)` cần cân nhắc kiểu: nếu truyền cả mảng vào như một giá trị, bạn có thể tạo stream của **một mảng**, không phải stream của từng phần tử trong mảng.

## 7. Null, downstream operation và những lỗi dễ gặp

Một điểm cần ghi nhớ là các factory Stream có cách xử lý null khác nhau:

- `Stream.of((String) null)`: có một phần tử null.
- `Stream.of("A", null)`: có cả `"A"` và null.
- `Stream.empty()`: không có phần tử.
- `Stream.ofNullable(null)`: không có phần tử.
- `Stream.ofNullable("A")`: có một phần tử `"A"`.

Vì stream từ `of` có thể chứa null, các thao tác downstream như `map(String::length)` hay `String::toUpperCase` sẽ ném `NullPointerException` nếu thực sự gặp null. Một số thao tác khác cũng yêu cầu phần tử không-null; ví dụ `findFirst()`/`findAny()` tạo `Optional` và không thể chứa giá trị null làm phần tử được chọn. Không suy ra rằng mọi terminal operation xử lý null được chỉ vì nguồn Stream cho phép null.

Tạo `NullStreamDemo.java`:

```java
import java.util.stream.Stream;

public class NullStreamDemo {
    public static void main(String[] args) {
        Stream<String> oneNull = Stream.of((String) null);
        Stream<String> noElement = Stream.ofNullable((String) null);

        System.out.println(oneNull.count());
        System.out.println(noElement.count());

        System.out.println(
                Stream.of((String) null)
                        .map(value -> value == null ? 0 : value.length())
                        .toList());

        System.out.println(
                Stream.ofNullable((String) null)
                        .map(String::length)
                        .toList());
    }
}
```

Chạy:

```bash
javac NullStreamDemo.java
java NullStreamDemo
```

Output:

```text
1
0
[0]
[]
```

Vì mapper trong lời gọi thứ ba **có xử lý null**, kết quả là list chứa một phần tử số 0; ở lời gọi thứ tư, mapper không chạy vì stream rỗng. Đây là điểm khác bản chất với việc truyền null để phương thức tự bỏ qua.

Không dùng `Stream.ofNullable((String) null).findFirst().orElse(...)` để kết luận stream có phần tử null: nguồn đã rỗng nên không có phần tử để chọn. Ngược lại, `Stream.of((String) null).findFirst()` có thể ném `NullPointerException` vì `Optional` không chấp nhận phần tử null làm giá trị hiện diện.

## 8. Thời điểm đánh giá, pipeline và tính lazy

Các phương thức `Stream.of`, `Stream.empty` và `Stream.ofNullable` **tạo nguồn stream**. Các phép biến đổi trung gian, như `map` hay `filter`, nói chung được thực hiện khi terminal operation yêu cầu dữ liệu. Điều này không có nghĩa mọi biểu thức đối số đưa vào factory được hoãn lại.

Ví dụ:

```java
Stream<String> stream = Stream.of(loadName());
```

Giả sử `loadName()` là một phương thức trả `String`. Java đánh giá đối số `loadName()` **ngay lúc gọi `Stream.of`**, sau đó mới tạo stream có một phần tử là giá trị đã tính. Việc gắn `map` sau đó mới là phần pipeline có thể được đánh giá lười.

Để hoãn việc **tạo stream/giá trị nguồn** tới thời điểm thật sự cần, có thể lưu một `Supplier<Stream<String>>`:

```java
Supplier<Stream<String>> supplier =
        () -> Stream.of(loadName());
```

Đây là đoạn mã nằm trong phương thức có import `Supplier` và `Stream`; lời gọi `loadName()` nằm trong thân lambda nên chỉ thực hiện khi gọi `supplier.get()`. Khi cần một nguồn có thể tạo lại, gọi `supplier.get()` để nhận **stream mới** mỗi lần, thay vì cố dùng lại một stream đã tiêu thụ.

Stream không phải collection có thể duyệt lại tùy ý: sau một terminal operation, không dùng lại cùng stream cho terminal operation thứ hai. Ví dụ `Stream<String> s = Stream.of("A"); s.count(); s.toList();` là cách dùng sai; lời gọi sau có thể ném `IllegalStateException` vì stream đã bị thao tác/đóng.

Khi dùng `Stream.of("A", "B")` trên stream tuần tự, nguồn có encounter order tương ứng thứ tự đối số. Với parallel pipeline, phải xét hợp đồng về thứ tự của từng thao tác terminal; đừng dựa vào trình tự side effect của `forEach` để suy diễn thứ tự dữ liệu trong stream song song.

## 9. Chọn factory theo ý định nghiệp vụ

| Tình huống | Cách tạo phù hợp | Lý do |
| --- | --- | --- |
| Có một giá trị chắc chắn không-null | `Stream.of(value)` | Một phần tử rõ ràng |
| Có nhiều giá trị riêng lẻ | `Stream.of(a, b, c)` | Đơn giản với dữ liệu nhỏ |
| Không có phần tử để phát ra | `Stream.empty()` | Truyền ý định rỗng rõ nhất |
| Có một đối tượng có thể null | `Stream.ofNullable(value)` | Null thành 0 phần tử, khác null thành 1 |
| Có mảng tham chiếu cần duyệt từng phần tử | `Arrays.stream(values)` hoặc `Stream.of(values)` | Có stream từng phần tử, lưu ý mảng không được null |
| Có mảng nguyên thủy `int[]` | `Arrays.stream(intArray)` | Nhận `IntStream` từng số nguyên |
| Muốn stream chứa chính một mảng như một phần tử | `Stream.of((Object) values)` | Nêu rõ kiểu phần tử là mảng ở dạng Object |
| Muốn loại bỏ các phần tử null trong stream hiện có | `filter(Objects::nonNull)` | Loại null ở pipeline |
| Muốn ánh xạ từng input thành zero-or-one output | `flatMap(x -> Stream.ofNullable(...))` | Ghép các stream 0 hoặc 1 phần tử |

Trong API, nếu phương thức trả stream và một trường hợp thực sự không có dữ liệu, ưu tiên trả `Stream.empty()` thay vì `null`. Caller nhờ đó luôn có thể kết hợp và sử dụng API Stream một cách nhất quán.

Lưu ý `List.of(...)` không chấp nhận phần tử null, trong khi một stream tạo với `Stream.of("A", null)` có thể chứa null. Việc đổi qua lại giữa collection và stream cần xét riêng hợp đồng null của mỗi API, đặc biệt khi dùng collectors hoặc chuyển về collection.

## 10. Những hiểu nhầm phổ biến

1. **“`Stream.of(null)` chắc chắn cho stream chứa một null.”** Không nên viết mơ hồ do overload varargs. Muốn một phần tử null, viết `Stream.of((String) null)`; muốn bỏ qua null, dùng `Stream.ofNullable(value)`.
2. **“`Stream.empty()` chứa một phần tử rỗng.”** Sai: số phần tử bằng 0, không có giá trị placeholder.
3. **“`Stream.ofNullable(null)` cho stream có một null.”** Sai: kết quả rỗng.
4. **“Một phần tử null và không có phần tử là như nhau.”** Sai: `count()` khác nhau; mapper, predicate và terminal operation cũng có thể khác.
5. **“`Stream.of(array)` luôn chứa chính một mảng.”** Không đúng với mảng tham chiếu khi áp dụng overload varargs thông thường; còn mảng nguyên thủy như `int[]` thường là một phần tử `int[]`.
6. **“`Stream.of(intArray)` cho `IntStream`.”** Sai: muốn stream primitive từng số nguyên, dùng `Arrays.stream(intArray)` hoặc `IntStream.of(...)`.
7. **“`ofNullable` hoạt động trên mọi Java 8.”** Sai: cần Java 9+; Java 8 thường dùng biểu thức điều kiện trả `Stream.empty()` hoặc `Stream.of(value)`.
8. **“Tạo Stream xong có thể gọi nhiều terminal operation.”** Sai: một stream chỉ sử dụng cho một chuỗi thao tác có terminal; tạo stream mới khi muốn xử lý lại.
9. **“Thao tác trên stream luôn lazy kể cả khi gọi phương thức để tạo giá trị đầu vào.”** Sai: biểu thức đối số của `Stream.of(load())` được đánh giá trước lúc lời gọi `of` thực hiện.
10. **“Factory không có null trong đầu vào nên các phép biến đổi đều an toàn.”** Dữ liệu có thể sinh ra null trong `map`/`flatMap` hoặc từ các thành phần khác của pipeline. Mỗi stage cần hợp đồng rõ.
11. **“`map(Stream::ofNullable)` làm phẳng dữ liệu.”** Sai: `map` tạo phần tử là các stream con; `flatMap(Stream::ofNullable)` mới làm phẳng.
12. **“`Stream.empty()` chỉ dành cho String.”** Sai: đây là factory generic, hoạt động với bất kỳ kiểu phần tử tham chiếu nào.

## 11. Bài tập tự kiểm tra

Hãy dự đoán số lượng phần tử và giá trị kết quả trong Java 17:

```java
String value = null;

long a = Stream.of((String) null).count();
long b = Stream.ofNullable(value).count();
long c = Stream.<String>empty().count();
long d = Stream.of("A", "B").count();

List<String> words = Stream.of("A", null, "B")
        .flatMap(Stream::ofNullable)
        .toList();
```

Đoạn mã trên đặt trong phương thức và cần import `java.util.stream.Stream` cùng `java.util.List`.

**Đáp án:** `a = 1`; `b = 0`; `c = 0`; `d = 2`; `words = ["A", "B"]`. Vì `Stream.of((String) null)` chứa một phần tử null nên `count()` bằng 1; `ofNullable(null)` và `empty()` không chứa gì; `flatMap(Stream::ofNullable)` loại bỏ nhánh null trong khi giữ các giá trị còn lại.

Bài tập mở rộng: với `String[] names = {"Lan", "Mai"}`, so sánh `Stream.of(names).count()` với `Stream.of((Object) names).count()`. Kết quả tương ứng là **2** và **1**. Nếu thay bằng `int[] nums = {1, 2}`, `Stream.of(nums).count()` bằng **1**, còn `Arrays.stream(nums).count()` bằng **2**.

## 12. Ghi nhớ

Khi tạo stream, hãy hỏi: **Nguồn có bao nhiêu phần tử, và null có nên được xem như một phần tử hay như sự vắng mặt?**

- **`of(values...)`** — các giá trị cung cấp là phần tử; thận trọng với null và overload mảng.
- **`empty()`** — không có phần tử, không cần thêm sentinel.
- **`ofNullable(value)`** — **0 hoặc 1** phần tử; null tương đương không có phần tử.

Kiểm tra thêm kiểu phần tử của stream: `Stream<String>` khác `Stream<String[]>` và `IntStream`. Sau khi chọn đúng factory, downstream pipeline mới có cơ hội thực hiện đúng các thao tác trên phần tử mong muốn.

**Tài liệu tham khảo:** Java SE `java.util.stream.Stream` (factory `of`, `empty`, `ofNullable`), `java.util.Arrays.stream`, `java.util.stream.IntStream`; Java Language Specification về overload resolution, varargs và thứ tự đánh giá lời gọi phương thức.