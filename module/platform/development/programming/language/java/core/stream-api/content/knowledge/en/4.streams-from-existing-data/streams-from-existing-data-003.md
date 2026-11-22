# Tạo Stream bằng Stream.of, Stream.empty và Stream.ofNullable

Trong Java Stream API, không nhất thiết phải bắt đầu pipeline từ `Collection.stream()`. Ba phương thức factory `Stream.of(...)`, `Stream.empty()` và `Stream.ofNullable(...)` giúp tạo stream ngay từ những giá trị đang có trong chương trình, từ một tập hằng số nhỏ hoặc từ một giá trị có thể vắng mặt.

Đây là bài trong chương **Tạo Stream từ dữ liệu có sẵn** của module **JAVA_STREAM_API**. Mục tiêu là biết chọn đúng phương thức tạo stream, hiểu chính xác số phần tử được tạo ra, xử lý `null` an toàn và kết nối nguồn này với pipeline khai báo `filter`, `map`, `reduce`, `collect` hoặc `flatMap`. Các vấn đề về tài nguyên, trạng thái và hiệu năng cũng được chỉ ra ở những chỗ liên quan trực tiếp.

## 1. Nhìn nhanh: ba phương thức khác nhau ở đâu?

| Phương thức | Đầu vào | Số phần tử trong stream | Khi nào nên dùng? |
|---|---|---|---|
| `Stream.of(value)` | Một giá trị thuộc kiểu `T` | Chính xác **1**, kể cả khi giá trị là `null` | Đưa một đối tượng cụ thể vào pipeline |
| `Stream.of(v1, v2, ...)` | Nhiều giá trị qua varargs | Bằng số đối số/phần tử mảng, có thể là **0** | Tạo stream từ vài giá trị có sẵn |
| `Stream.empty()` | Không cần đối số | Chính xác **0** | Diễn đạt nhánh không có phần tử |
| `Stream.ofNullable(value)` | Một giá trị có thể `null` | **0** nếu `null`, ngược lại **1** | Chuyển giá trị tùy chọn thành stream 0 hoặc 1 phần tử |

`Stream.of` và `Stream.empty` có từ Java 8; `Stream.ofNullable` có từ **Java 9**. Cả ba tạo stream tuần tự ban đầu. `Stream.toList()` được dùng trong một số ví dụ dưới đây và chỉ có từ **Java 16**; với Java 8–15 có thể thay bằng `collect(Collectors.toList())` trong những ví dụ không có yêu cầu riêng về tính bất biến của danh sách.

Để dùng các ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;
```

## 2. `Stream.of(...)`: từ một hoặc nhiều giá trị

### 2.1. Tạo stream từ các phần tử được liệt kê

```java
List<String> technologies = Stream.of("Java", "Kotlin", "Scala")
        .map(String::toUpperCase)
        .toList();

System.out.println(technologies); // [JAVA, KOTLIN, SCALA]
```

`Stream.of("Java", "Kotlin", "Scala")` tạo `Stream<String>` với ba phần tử theo thứ tự đã cung cấp. `map` là thao tác trung gian lazy: nó mô tả phép biến đổi; `toList()` là terminal operation kích hoạt pipeline và thu kết quả.

Với một phần tử:

```java
Stream<String> one = Stream.of("Java");
System.out.println(one.count()); // 1
```

Với không phần tử, lời gọi `Stream.of()` cũng tạo stream rỗng; nên chỉ rõ kiểu khi ngữ cảnh không đủ để suy luận:

```java
Stream<String> none = Stream.<String>of();
System.out.println(none.count()); // 0
```

Trong mã thể hiện ý định “không có dữ liệu”, `Stream.empty()` thường dễ đọc hơn `Stream.of()`.

### 2.2. `Stream.of` không tự loại `null`

`Stream.of` có thể chứa một phần tử `null`. Nó cũng có thể chứa `null` xen giữa những phần tử hợp lệ:

```java
long oneNull = Stream.of((String) null).count();
long threeValues = Stream.of("An", null, "Bình").count();

System.out.println(oneNull);     // 1
System.out.println(threeValues); // 3
```

Ép kiểu `(String) null` ở đây rất có chủ ý: nó buộc gọi overload nhận **một đối tượng**, tránh sự mơ hồ với overload varargs khi viết `Stream.of(null)`. Nếu truyền một **mảng varargs tham chiếu `null`** như `Stream.of((String[]) null)`, lời gọi không tương đương một phần tử `null` và có thể ném `NullPointerException` khi tạo stream.

Việc stream cho phép chứa `null` **không** có nghĩa mọi thao tác phía sau đều chấp nhận nó:

```java
List<String> names = Stream.of("An", null, "Bình")
        .filter(Objects::nonNull)
        .map(String::toUpperCase)
        .toList();

System.out.println(names); // [AN, BÌNH]
```

Nếu bỏ `filter(Objects::nonNull)`, `String::toUpperCase` sẽ ném `NullPointerException` khi gặp phần tử `null`. Tương tự, `findFirst()` và `findAny()` có thể ném `NullPointerException` nếu phần tử chúng chọn là `null`. Hãy quyết định rõ việc có cho phép `null` tồn tại trong pipeline hay không.

### 2.3. Cẩn thận với overload varargs và mảng

Với mảng **đối tượng** `String[]`, `Stream.of(array)` có thể coi từng phần tử trong mảng là phần tử của stream thông qua overload varargs:

```java
String[] languages = {"Java", "Go", "Rust"};

List<String> values = Stream.of(languages).toList();
System.out.println(values); // [Java, Go, Rust]

// Ép sang Object để coi toàn bộ mảng là MỘT phần tử:
long wholeArray = Stream.of((Object) languages).count();
System.out.println(wholeArray); // 1
```

Với **mảng kiểu nguyên thủy** `int[]`, không có sự bung phần tử thành `Stream<Integer>`:

```java
int[] scores = {10, 20, 30};

Stream<int[]> arrays = Stream.of(scores);
System.out.println(arrays.count());        // 1: một mảng int[]
System.out.println(Arrays.stream(scores).sum()); // 60: IntStream
System.out.println(IntStream.of(scores).sum());   // 60: IntStream
```

`Stream.of(scores)` chứa đúng **một đối tượng mảng** `int[]`; `Arrays.stream(scores)` và `IntStream.of(scores)` mới tạo `IntStream` trên từng số nguyên. Với dữ liệu primitive lớn, ưu tiên `IntStream`, `LongStream`, `DoubleStream` khi phù hợp để tránh boxing không cần thiết.

Một nhầm lẫn tương tự xảy ra với `Collection`:

```java
List<String> tags = List.of("core", "stream");

System.out.println(Stream.of(tags).count()); // 1: một List<String>
System.out.println(tags.stream().count());   // 2: hai String
```

**Quy tắc:** muốn duyệt phần tử của `List` thì dùng `list.stream()`; muốn duyệt phần tử của một mảng thì `Arrays.stream(array)` thường diễn đạt rõ ý hơn; muốn đưa **cả** `List` hoặc mảng thành một giá trị duy nhất thì dùng `Stream.of(collection)` hoặc ép kiểu mảng phù hợp.

### 2.4. Dùng `Stream.of` trong pipeline khai báo

```java
int total = Stream.of(12, 7, 20, 5)
        .filter(n -> n >= 10)
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

System.out.println(total); // 64 = 24 + 40
```

`Stream.of(12, 7, 20, 5)` ở đây tạo `Stream<Integer>`. `filter` giữ hai phần tử, `map` nhân đôi, `reduce` tính tổng. Đây là kiểu pipeline xử lý dữ liệu khai báo: nói **cần làm gì** với nguồn, không cần tự viết vòng lặp để tích lũy từng phần tử.

## 3. `Stream.empty()`: thể hiện trường hợp không có dữ liệu

`Stream.empty()` trả về stream rỗng thuộc kiểu phần tử mà ngữ cảnh mong muốn:

```java
Stream<String> emptyNames = Stream.empty();
List<String> result = emptyNames.toList();

System.out.println(result); // []
```

Nếu cần khai báo tường minh kiểu generic:

```java
Stream<String> empty = Stream.<String>empty();
System.out.println(empty.count()); // 0
```

Giá trị lớn nhất của `Stream.empty()` không phải tiết kiệm một dòng mã; đó là **giữ cùng kiểu trả về** `Stream<T>` cho mọi nhánh logic, giúp bên gọi ghép pipeline mà không phải xử lý `null`.

```java
static Stream<String> topicsFor(boolean enabled) {
    if (!enabled) {
        return Stream.empty();
    }
    return Stream.of("stream", "collector", "spliterator");
}

// Bên gọi:
List<String> topics = topicsFor(false)
        .map(String::toUpperCase)
        .toList();

System.out.println(topics); // []
```

Trong một phương thức trả về stream, trả về `null` sẽ buộc bên gọi kiểm tra hoặc gây lỗi nếu gọi tiếp `.map(...)`; trả về `Stream.empty()` cho phép pipeline tiếp tục một cách tự nhiên.

### 3.1. Terminal operation trên stream rỗng

| Terminal operation | Kết quả của stream rỗng | Diễn giải |
|---|---|---|
| `count()` | `0` | Không có phần tử |
| `toList()` | `[]` | Danh sách rỗng |
| `findFirst()` | `Optional.empty()` | Không có phần tử đầu tiên |
| `anyMatch(...)` | `false` | Không có phần tử nào thỏa |
| `allMatch(...)` | `true` | Không tồn tại phần tử phản ví dụ |
| `noneMatch(...)` | `true` | Không có phần tử nào thỏa |
| `reduce(identity, op)` | `identity` | Không có giá trị để gộp |

Mỗi dòng dưới đây tạo **một stream mới**; một stream không được tiêu thụ hai lần:

```java
System.out.println(Stream.<Integer>empty().count());           // 0
System.out.println(Stream.<Integer>empty().anyMatch(n -> n > 0)); // false
System.out.println(Stream.<Integer>empty().allMatch(n -> n > 0)); // true
System.out.println(Stream.<Integer>empty().reduce(10, Integer::sum)); // 10
```

`allMatch` trên tập rỗng trả `true` theo quy tắc logic *vacuous truth*. Đừng suy diễn rằng “đã tìm thấy một phần tử thỏa điều kiện” khi kiểm tra `allMatch` trả `true` trên nguồn rỗng.

### 3.2. Kết hợp với các stream khác

```java
Stream<String> base = Stream.of("Java", "Kotlin");
Stream<String> extra = Stream.empty();

List<String> all = Stream.concat(base, extra).toList();
System.out.println(all); // [Java, Kotlin]
```

Khi nghiệp vụ không phát sinh phần tử ở một nhánh, `Stream.empty()` đóng vai trò như “nhánh không đóng góp dữ liệu” mà vẫn tương thích với `Stream.concat` hoặc `flatMap`.

## 4. `Stream.ofNullable(value)`: một giá trị có thể vắng mặt

Java 9 bổ sung `Stream.ofNullable(T value)` với hợp đồng đơn giản:

- `value != null`: stream chứa chính xác **một** phần tử đó.
- `value == null`: stream rỗng, **không chứa** phần tử `null`.

```java
String nickname = null;

List<String> a = Stream.ofNullable(nickname).toList();
List<String> b = Stream.ofNullable("Java").toList();

System.out.println(a); // []
System.out.println(b); // [Java]
```

So sánh trực tiếp với `Stream.of`:

```java
String value = null;

System.out.println(Stream.of((String) value).count()); // 1
System.out.println(Stream.ofNullable(value).count());  // 0
```

Với `value = "X"`, cả hai đều tạo một phần tử `"X"`. **Khác biệt chỉ xuất hiện khi giá trị là `null`**, nhưng khác biệt đó rất quan trọng khi các terminal operation không hỗ trợ phần tử `null`.

### 4.1. Kết hợp `flatMap` để bỏ các thuộc tính thiếu

Giả sử mỗi bản ghi khách hàng có địa chỉ email tùy chọn:

```java
record Customer(String name, String email) {}

List<Customer> customers = List.of(
        new Customer("An", "an@example.com"),
        new Customer("Bình", null),
        new Customer("Chi", "chi@example.com")
);

List<String> emails = customers.stream()
        .flatMap(customer -> Stream.ofNullable(customer.email()))
        .map(String::toLowerCase)
        .toList();

System.out.println(emails); // [an@example.com, chi@example.com]
```

Đối với từng khách hàng, `Stream.ofNullable(customer.email())` tạo stream có **0 hoặc 1 email**. `flatMap` nối các stream con thành một stream phẳng, nên email `null` không đi tiếp xuống `map`.

Cùng bài toán có thể viết:

```java
List<String> emails = customers.stream()
        .map(Customer::email)
        .filter(Objects::nonNull)
        .map(String::toLowerCase)
        .toList();
```

Hai cách đều hợp lý. `map(...).filter(Objects::nonNull)` thường đơn giản nhất khi chỉ loại `null` sau một phép lấy thuộc tính; `flatMap(...Stream.ofNullable(...))` hữu ích khi mô hình hóa **mỗi phần tử đầu vào đóng góp 0 hoặc 1 kết quả** hoặc khi cùng một pipeline đã cần `flatMap`.

### 4.2. Ghép nhiều nguồn dữ liệu có thể `null`

```java
String primaryCode = "JAVA";
String fallbackCode = null;

List<String> codes = Stream.of(primaryCode, fallbackCode)
        .flatMap(Stream::ofNullable)
        .map(String::toLowerCase)
        .toList();

System.out.println(codes); // [java]
```

Ở đây `Stream.of(...)` tạo hai phần tử, trong đó có một `null`; `flatMap(Stream::ofNullable)` biến từng phần tử thành stream 0 hoặc 1 phần tử để loại giá trị thiếu. Trong trường hợp chỉ muốn loại `null`, `filter(Objects::nonNull)` thường trực tiếp và dễ đọc hơn.

### 4.3. Phân biệt với `Optional.ofNullable`

```java
String token = null;

Optional<String> maybeToken = Optional.ofNullable(token);
Stream<String> tokenStream = Stream.ofNullable(token);
```

`Optional<T>` mô tả **một giá trị có thể vắng mặt** để trả về từ API hoặc biểu diễn kết quả phép tra cứu. `Stream<T>` mô tả **dãy 0 hoặc nhiều phần tử** để thực hiện pipeline. Nếu đã có `Optional<T>`, Java 9 cung cấp `optional.stream()` để lấy stream có 0 hoặc 1 phần tử:

```java
Optional<String> maybe = Optional.of("java");
List<String> list = maybe.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(list); // [JAVA]
```

Không cần tạo `Optional` trung gian chỉ để biến một giá trị nullable thành stream; `Stream.ofNullable(value)` diễn đạt trực tiếp hơn.

## 5. Chọn đúng factory trong tình huống thực tế

| Dữ liệu đang có / yêu cầu | Cách viết gợi ý | Lý do |
|---|---|---|
| Hai hằng số `"A"`, `"B"` | `Stream.of("A", "B")` | Hai phần tử xác định |
| Một đối tượng luôn có mặt | `Stream.of(object)` | Một phần tử |
| Một đối tượng có thể `null`, muốn bỏ nếu vắng | `Stream.ofNullable(object)` | Không tạo phần tử `null` |
| Nhánh không có kết quả | `Stream.empty()` | Bảo toàn kiểu `Stream<T>` |
| Một `List<T>` đã có | `list.stream()` | Duyệt các phần tử của list |
| Một `T[]` đã có | `Arrays.stream(array)` | Rõ ràng duyệt từng phần tử mảng |
| Một `int[]` đã có | `Arrays.stream(array)` hoặc `IntStream.of(array)` | Có `IntStream`, không phải `Stream<int[]>` |
| Một `Optional<T>` đã có | `optional.stream()` | Chuyển Optional thành stream 0 hoặc 1 phần tử |
| Nhiều thuộc tính nullable cần gom | `Stream.of(a, b).filter(Objects::nonNull)` | Loại `null` rõ ràng, đơn giản |

### Ví dụ nghiệp vụ: thu thập nhãn tùy chọn

```java
static Stream<String> labelsFor(String title, String category, boolean includeCategory) {
    Stream<String> titlePart = Stream.ofNullable(title);
    Stream<String> categoryPart = includeCategory
            ? Stream.ofNullable(category)
            : Stream.empty();

    return Stream.concat(titlePart, categoryPart)
            .map(String::trim)
            .filter(s -> !s.isEmpty());
}

// Bên gọi:
List<String> labels = labelsFor(" Java Stream ", null, true).toList();
System.out.println(labels); // [Java Stream]
```

Hàm luôn trả về `Stream<String>`, kể cả khi không có nhãn. `Stream.ofNullable` xử lý giá trị thiếu; `Stream.empty` thể hiện nhánh không thêm nhãn; `Stream.concat` nối hai nguồn. `map` và `filter` vẫn lazy đến khi `toList()` tiêu thụ stream.

## 6. Các hợp đồng và giới hạn cần nhớ

### 6.1. Thứ tự phần tử và chế độ thực thi

`Stream.of("C", "A", "B")` tạo stream có **encounter order** `C → A → B`; nếu sử dụng terminal operation giữ thứ tự như `toList()`, kết quả vẫn là `[C, A, B]`. `parallel()` cho phép xử lý trên nhiều thread nhưng bản thân nó không loại bỏ encounter order:

```java
List<String> names = Stream.of("C", "A", "B")
        .parallel()
        .map(String::toLowerCase)
        .toList();

System.out.println(names); // [c, a, b]
```

`Stream.empty()` và `Stream.ofNullable(...)` có tối đa một phần tử, nên chạy song song trực tiếp trên chúng hầu như không đem lại lợi ích. Nếu dùng `forEach` song song, đừng mặc định hành động được thực thi theo thứ tự; khi cần bảo đảm thứ tự hành động trên một stream có thứ tự, dùng `forEachOrdered`.

### 6.2. Stream chỉ được tiêu thụ một lần

```java
Stream<String> stream = Stream.of("A", "B");
long size = stream.count();
System.out.println(size); // 2

// stream.toList(); // Sai: stream đã được tiêu thụ.
```

Sau terminal operation `count()`, không dùng lại cùng đối tượng `stream`. Tạo stream mới từ các giá trị nguồn nếu muốn chạy pipeline khác.

### 6.3. Tham số được tính trước khi stream bắt đầu chạy

Các thao tác trung gian `map` và `filter` thường lazy, nhưng **đối số truyền vào factory vẫn được Java tính ngay**:

```java
static String fetchValue() {
    System.out.println("fetchValue called");
    return "data";
}

Stream<String> stream = Stream.ofNullable(fetchValue());
// Đã in "fetchValue called" tại đây, trước terminal operation.

System.out.println(stream.map(String::toUpperCase).toList()); // [DATA]
```

Không dùng `Stream.of(fetchValue())` hay `Stream.ofNullable(fetchValue())` để trì hoãn việc gọi `fetchValue()`. Hai phương thức chỉ đóng gói **giá trị đã được tính** vào stream. Nếu cần phát sinh dữ liệu theo nhu cầu, phải chọn một nguồn lazy thích hợp (chẳng hạn `Stream.generate(supplier)` với giới hạn số phần tử rõ ràng).

### 6.4. Trạng thái dùng chung, tài nguyên và hiệu năng

- Không dùng `map` hoặc `peek` để tùy tiện cập nhật biến dùng chung, nhất là khi dùng `parallel()`. Ưu tiên phép biến đổi không side effect và terminal operation `collect`, `reduce` phù hợp.
- Ba factory này tạo stream từ dữ liệu đã có, không tự mở tài nguyên cần đóng như file hay kết nối. Với các nguồn mở tài nguyên khác, ví dụ `Files.lines(path)`, cần `try-with-resources` để đóng stream.
- `Stream.of` thuận tiện cho một tập giá trị nhỏ; nếu đã có `List` hoặc mảng lớn, dùng trực tiếp nguồn thích hợp. Tạo nhiều stream một phần tử rồi nối lồng quá sâu có thể gây chi phí không cần thiết; chọn cấu trúc pipeline rõ ràng và đo hiệu năng với dữ liệu thực tế.
- `Stream.toList()` trả danh sách không thể chỉnh sửa, trong khi `Collectors.toList()` không cam kết khả năng chỉnh sửa hay kiểu danh sách cụ thể. Nếu cần một `ArrayList` có thể thay đổi, dùng `collect(Collectors.toCollection(ArrayList::new))` và import `java.util.ArrayList`.

## 7. Ví dụ tổng hợp có thể chạy (Java 17+)

Chương trình sau kiểm tra trường hợp nhiều phần tử, stream rỗng, giá trị nullable, mảng nguyên thủy và ghép thuộc tính:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class StreamFactoriesDemo {
    record User(String name, String nickname) {}

    public static void main(String[] args) {
        // 1. Nhiều giá trị có sẵn.
        System.out.println(Stream.of("A", "B", "C").toList());
        // [A, B, C]

        // 2. Không có phần tử.
        System.out.println(Stream.<String>empty().count());
        // 0

        // 3. Một đối tượng có thể null.
        String nickname = null;
        System.out.println(Stream.ofNullable(nickname).toList());
        // []
        System.out.println(Stream.ofNullable("dev").toList());
        // [dev]

        // 4. Một phần tử null khác stream rỗng.
        System.out.println(Stream.of((String) null).count());
        // 1

        // 5. Mảng primitive không được bung bởi Stream.of().
        int[] nums = {1, 2, 3};
        System.out.println(Stream.of(nums).count());
        // 1
        System.out.println(Arrays.stream(nums).sum());
        // 6

        // 6. Thu thập các giá trị nullable.
        List<User> users = List.of(
                new User("An", "anna"),
                new User("Bình", null),
                new User("Chi", "chichi")
        );
        List<String> nicknames = users.stream()
                .flatMap(user -> Stream.ofNullable(user.nickname()))
                .map(String::toUpperCase)
                .toList();
        System.out.println(nicknames);
        // [ANNA, CHICHI]
    }
}
```

## 8. Tự kiểm tra

1. **`Stream.of((String) null).count()` trả gì?** Trả `1` vì `null` là một phần tử của stream.
2. **`Stream.ofNullable(null)` khác gì `Stream.empty()`?** Cả hai đều rỗng trong trường hợp này; `ofNullable` còn có khả năng tạo một phần tử khi đầu vào không `null`.
3. **`Stream.of(List.of(1, 2, 3)).count()` trả bao nhiêu?** Trả `1`, vì phần tử duy nhất là cả `List`. Muốn ba số, dùng `List.of(1, 2, 3).stream()`.
4. **`Stream.of(new int[]{1, 2, 3}).count()` trả bao nhiêu?** Trả `1`; muốn stream gồm ba số nguyên, dùng `IntStream.of(1, 2, 3)` hoặc `Arrays.stream(array)`.
5. **Vì sao `Stream.ofNullable(fetchValue())` không trì hoãn `fetchValue()`?** Vì Java tính đối số của phương thức trước khi gọi phương thức đó; tính lazy áp dụng cho các bước pipeline phía sau.
6. **Muốn mỗi khách hàng đóng góp tối đa một email, bỏ qua `null`, dùng gì?** `customers.stream().flatMap(c -> Stream.ofNullable(c.email()))` hoặc `map(...).filter(Objects::nonNull)`.

Hãy chọn `Stream.of` khi có các giá trị cụ thể, `Stream.empty` khi một nhánh không đóng góp phần tử, và `Stream.ofNullable` khi một giá trị đơn lẻ có thể vắng mặt. Sự lựa chọn này quyết định ngay từ nguồn việc pipeline tiếp theo nhìn thấy **0, 1 hay nhiều phần tử**, đặc biệt là có hay không có phần tử `null`.
