# `Stream.toList` và `mapMulti` từ Java 16

## 1. Mục tiêu và bối cảnh tương thích JDK

Trong module **`JAVA_STREAM_API`**, pipeline thường đi từ nguồn dữ liệu qua các thao tác lazy như `filter`, `map`, `flatMap` tới terminal operation như `collect`, `reduce`. Khi học các phiên bản JDK mới, cần biết một API **xuất hiện từ bản Java nào**, đồng thời hiểu sự khác biệt về hợp đồng trước khi thay thế mã cũ.

Hai bổ sung quan trọng ở **Java 16**:

- **`Stream.toList()`:** terminal operation thu nội dung stream vào một `List` **không cho phép sửa đổi**.
- **`Stream.mapMulti(...)`:** intermediate operation cho phép một phần tử đầu vào phát ra **0, 1 hoặc nhiều** phần tử đầu ra thông qua consumer, thay vì tạo stream con như `flatMap`.

Bài thuộc chương **Khả năng tương thích JDK** và kết nối kiến thức về biến đổi/thu thập dữ liệu, kiểu generic, primitive streams, collector, xử lý song song và giới hạn về hiệu năng, trạng thái và tài nguyên.

Sau bài, bạn có thể:

1. Phân biệt `Stream.toList()` với `Collectors.toList()`, `Collectors.toUnmodifiableList()` và `Collectors.toCollection(ArrayList::new)`.
2. Dự đoán tính không cho phép sửa, khả năng chứa `null` và encounter order của kết quả.
3. Dùng `mapMulti` để lọc/biến đổi/flatten dữ liệu bằng một callback phát 0..n phần tử.
4. Quyết định khi nào dùng `mapMulti`, `flatMap`, `mapMultiToInt` hoặc primitive `mapMulti`.
5. Xử lý generic type inference, đối tượng mutable, tài nguyên bên ngoài và parallel stream.
6. Viết phương án tương thích Java 8/11 và kiểm tra các khác biệt khi nâng cấp lên Java 16+.

## 2. Các cột mốc phiên bản

| API | Có từ | Ngữ nghĩa chính |
| --- | --- | --- |
| `Stream.collect(Collectors.toList())` | Java 8 | Thu về `List`, **không cam kết** kiểu triển khai hoặc mutability. |
| `Stream.flatMap(...)` | Java 8 | Ánh xạ phần tử thành `Stream` con rồi nối phẳng. |
| `Collectors.toCollection(ArrayList::new)` | Java 8 | Chọn rõ collection đích có thể sửa. |
| `Stream.ofNullable(...)` | Java 9 | Tạo 0 hoặc 1 phần tử tùy null. |
| `List.of(...)` | Java 9 | Tạo list không cho phép sửa, từ chối `null`. |
| `Collectors.toUnmodifiableList()` | Java 10 | Thu list không cho phép sửa, từ chối `null`. |
| `List.copyOf(...)` | Java 10 | Tạo list không cho phép sửa từ collection, từ chối `null`. |
| `Stream.toList()` | **Java 16** | Terminal operation trả list không cho phép sửa, **cho phép `null`**. |
| `Stream.mapMulti(...)` | **Java 16** | Phát 0..n phần tử từ mỗi đầu vào. |
| `Stream.mapMultiToInt/Long/Double(...)` | **Java 16** | Phát kết quả primitive mà không cần boxed stream. |
| `IntStream.mapMulti(...)` và tương đương `LongStream`, `DoubleStream` | **Java 16** | Phát nhiều kết quả primitive từ mỗi primitive đầu vào. |

Bảng phản ánh **API của thư viện chuẩn**. Một dự án đang chạy JDK mới nhưng biên dịch với `--release 8` hoặc `--release 11` vẫn không được dùng API chỉ có từ Java 16. Việc nâng mức JDK runtime và mức phát hành mã nguồn/bytecode cần được xem xét cùng nhau.

## 3. `Stream.toList()`: terminal operation với list không cho phép sửa

Chữ ký cơ bản:

```java
List<T> toList()
```

Ví dụ Java 16+:

```java
import java.util.Arrays;
import java.util.List;

public class ToListBasics {
    public static void main(String[] args) {
        List<String> source = Arrays.asList(
            "Java", "Go", "Kotlin", "Java"
        );

        List<String> result = source.stream()
            .filter(s -> s.length() >= 4)
            .map(String::toUpperCase)
            .toList();

        System.out.println(result);
        // [JAVA, KOTLIN, JAVA]
    }
}
```

`toList()` tiêu thụ stream, tạo list theo **encounter order nếu stream có thứ tự**. Nó không tự `distinct`, vì vậy hai lần `JAVA` vẫn tồn tại. Nếu nguồn có thứ tự và stream được xử lý song song, thứ tự nội dung list vẫn phản ánh encounter order, không phải thứ tự các thread hoàn thành.

Đặc điểm quan trọng nhất: **list trả về không cho phép sửa đổi**.

```java
import java.util.List;
import java.util.stream.Stream;

public class ToListUnmodifiable {
    public static void main(String[] args) {
        List<Integer> numbers = Stream.of(1, 2, 3).toList();

        System.out.println(numbers); // [1, 2, 3]

        try {
            numbers.add(4);
        } catch (UnsupportedOperationException expected) {
            System.out.println("Khong the them");
        }

        try {
            numbers.set(0, 10);
        } catch (UnsupportedOperationException expected) {
            System.out.println("Khong the set");
        }
    }
}
```

Kết quả:

```text
[1, 2, 3]
Khong the them
Khong the set
```

`add`, `remove`, `set`, `clear`, `sort` và những phép sửa khác không được hỗ trợ trên list kết quả. Nếu phần code sau cần thêm, xóa hay sắp xếp tại chỗ, **không nên thay `collect(Collectors.toList())` bằng `toList()` một cách cơ học**.

### 3.1. Không cam kết loại triển khai

`Stream.toList()` có kiểu trả về `List<T>`, không cam kết là `ArrayList` hay lớp cụ thể nào. Không viết code phụ thuộc vào tên lớp thực tế hoặc ép kiểu:

```java
// KHÔNG HỢP LỆ VỀ KIỂU TĨNH:
// ArrayList<String> values = Stream.of("A").toList();
```

Nếu thật sự cần `ArrayList`:

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> values = Stream.of("A", "B")
    .collect(Collectors.toCollection(ArrayList::new));

values.add("C"); // Hợp lệ.
```

### 3.2. List không sửa được không đồng nghĩa phần tử bất biến

`toList` không sao chép sâu các đối tượng trong stream:

```java
import java.util.List;
import java.util.stream.Stream;

public class MutableElement {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box box = new Box(1);
        List<Box> result = Stream.of(box).toList();

        box.value = 99;
        System.out.println(result.get(0).value); // 99

        // result.add(new Box(2)); // UnsupportedOperationException
    }
}
```

Chỉ **cấu trúc list qua interface List** không được phép sửa; trạng thái đối tượng bên trong vẫn có thể thay đổi nếu đối tượng mutable. Một snapshot sâu cần chiến lược sao chép riêng hoặc phần tử bất biến.

## 4. So sánh các kiểu thu thập `List`

| Phương án | Java tối thiểu | Mutability của list kết quả | Null | Loại cụ thể |
| --- | --- | --- | --- | --- |
| `collect(Collectors.toList())` | 8 | **Không cam kết** | Chấp nhận `null` | Không cam kết |
| `collect(Collectors.toCollection(ArrayList::new))` | 8 | Có thể sửa | Chấp nhận `null` | `ArrayList` |
| `collect(Collectors.toUnmodifiableList())` | 10 | Không cho sửa | Từ chối `null` | Không cam kết |
| `Stream.toList()` | 16 | **Không cho sửa** | **Chấp nhận `null`** | Không cam kết |
| `List.copyOf(collection)` | 10 | Không cho sửa | Từ chối `null` | Không cam kết |

**Điểm dễ nhầm:** `Collectors.toList()` không hứa sẽ trả `ArrayList` có thể sửa, dù một số triển khai hiện tại làm như vậy. Ngược lại, `Stream.toList()` **có cam kết** list không cho phép sửa.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CompareListCollectors {
    public static void main(String[] args) {
        List<String> unspecified = Stream.of("A", "B")
            .collect(Collectors.toList());

        ArrayList<String> mutable = Stream.of("A", "B")
            .collect(Collectors.toCollection(ArrayList::new));

        List<String> unmodifiable = Stream.of("A", "B")
            .toList();

        mutable.add("C"); // OK
        System.out.println(mutable); // [A, B, C]
        System.out.println(unspecified); // [A, B]
        System.out.println(unmodifiable); // [A, B]
    }
}
```

### 4.1. Khi cần tương thích Java 8

Trước Java 16, nếu cần một list không cho phép sửa **và vẫn chấp nhận null**, có thể dùng wrapper quanh một bản sao mới:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> result = Collections.unmodifiableList(
    Stream.of("A", null, "B")
        .collect(Collectors.toCollection(ArrayList::new))
);

System.out.println(result); // [A, null, B]
```

Đây là đoạn mã đặt bên trong một method có các import phù hợp. `Collections.unmodifiableList` trả một view không cho phép sửa, nên ví dụ cố ý tạo list mới **không lộ tham chiếu mutable** ra ngoài. Nó không làm bất biến các phần tử bên trong.

Nếu yêu cầu là list **có thể sửa**, dùng `toCollection(ArrayList::new)` ngay từ Java 8 thay vì `toList()`.

## 5. Khác biệt về `null`, định danh và thứ tự

### 5.1. `toList` nhận `null`

```java
import java.util.List;
import java.util.stream.Stream;

List<String> withNull = Stream.of("Java", null, "Go")
    .toList();

System.out.println(withNull); // [Java, null, Go]
System.out.println(withNull.size()); // 3
```

Trong khi đó, `Collectors.toUnmodifiableList()` và `List.of(...)` từ chối `null`:

```java
// Mỗi lời gọi dưới đây có thể ném NullPointerException.
// Stream.of("A", null)
//     .collect(Collectors.toUnmodifiableList());
// List.of("A", null);
```

Vì vậy, chuyển từ `toUnmodifiableList` sang `Stream.toList` **thay đổi quy tắc null**. Nếu muốn loại null:

```java
List<String> clean = Stream.of("Java", null, "Go")
    .filter(java.util.Objects::nonNull)
    .toList();

System.out.println(clean); // [Java, Go]
```

Nhưng **bỏ null** và **báo lỗi dữ liệu null** là hai yêu cầu nghiệp vụ khác nhau; không âm thầm lọc bỏ nếu null cần được kiểm tra hoặc ghi nhận.

### 5.2. Instance có thể là value-based

`Stream.toList()` có thể trả một **value-based instance**. Không dựa vào:

- `==` để kiểm tra danh tính list.
- `System.identityHashCode(list)` làm định danh nghiệp vụ.
- `synchronized(list)` dùng chính list trả về làm khóa đồng bộ hóa.

So sánh nội dung:

```java
List<Integer> first = Stream.of(1, 2).toList();
List<Integer> second = Stream.of(1, 2).toList();

System.out.println(first.equals(second)); // true
```

Không suy luận hợp đồng từ việc `first == second` có xảy ra ở một JDK cụ thể hay không.

### 5.3. `toList` không tự định nghĩa thứ tự mới

```java
List<Integer> sorted = Stream.of(4, 1, 3, 2)
    .sorted()
    .toList();

System.out.println(sorted); // [1, 2, 3, 4]
```

Nguồn `List` hoặc `IntStream.range` có encounter order; `sorted` có thể tạo thứ tự sắp xếp mới. Ngược lại, nguồn `HashSet` không bảo đảm thứ tự gặp và `unordered()` có thể bỏ ràng buộc đó. `toList()` giữ thứ tự nếu có, **không tự sắp xếp** hay khôi phục một thứ tự không tồn tại.

## 6. `toList()` kết thúc một pipeline lazy

```java
import java.util.Arrays;
import java.util.List;

List<String> source = Arrays.asList(
    "Kotlin", "Go", "Java", "Java"
);

List<String> result = source.stream()
    .filter(s -> s.length() >= 4)
    .map(String::toUpperCase)
    .sorted()
    .toList();

System.out.println(result);
// [JAVA, JAVA, KOTLIN]
```

`filter`, `map` và `sorted` vẫn là intermediate operations; chúng được đánh giá khi terminal `toList` cần kết quả. Nếu thêm `distinct()`:

```java
List<String> unique = source.stream()
    .filter(s -> s.length() >= 4)
    .map(String::toUpperCase)
    .distinct()
    .sorted()
    .toList();

System.out.println(unique); // [JAVA, KOTLIN]
```

`toList` không tự loại trùng, grouping hay sắp xếp. Nó chỉ thu các phần tử ở cuối pipeline thành list không cho phép sửa.

Một `Stream` **chỉ được tiêu thụ một lần**. Khi cần các báo cáo khác nhau, tạo stream mới từ nguồn hoặc giữ dữ liệu trung gian nếu hợp lý. Điều đó không thay đổi khi chuyển từ `collect` sang `toList`.


## 7. `mapMulti`: một phần tử có thể phát 0, 1 hoặc nhiều kết quả

`mapMulti` là **intermediate operation** từ Java 16. Trên `Stream<T>`, chữ ký quan trọng là:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Ý nghĩa:

- `T`: kiểu phần tử đầu vào.
- `R`: kiểu phần tử đầu ra.
- `mapper` nhận phần tử đầu vào và một consumer để **phát kết quả**.
- Gọi `consumer.accept(value)` mỗi khi có kết quả cần đưa vào pipeline.
- Callback không gọi `accept` thì phát 0 kết quả; gọi một lần phát 1; gọi nhiều lần phát nhiều kết quả.

So sánh:

```text
map:
  T -> R                       1 đầu vào → đúng 1 đầu ra

flatMap:
  T -> Stream<R>               1 đầu vào → stream con với 0..n kết quả

mapMulti:
  (T, Consumer<R>) -> void     1 đầu vào → gọi accept() 0..n lần
```

### 7.1. Phát hai giá trị từ mỗi số

```java
import java.util.List;
import java.util.stream.Stream;

public class MapMultiBasics {
    public static void main(String[] args) {
        List<Integer> result = Stream.of(1, 2, 3)
            .<Integer>mapMulti((n, emit) -> {
                emit.accept(n);
                emit.accept(n * 10);
            })
            .toList();

        System.out.println(result);
        // [1, 10, 2, 20, 3, 30]
    }
}
```

`emit` là tên đặt cho consumer do pipeline cung cấp. `mapMulti` trả về **`Stream<R>`**, không trực tiếp tạo list; list chỉ được tạo khi terminal operation `toList()` chạy.

### 7.2. Phát 0 hoặc 1 kết quả

```java
List<Integer> evenTimesTen = Stream.of(1, 2, 3, 4)
    .<Integer>mapMulti((n, emit) -> {
        if (n % 2 == 0) {
            emit.accept(n * 10);
        }
    })
    .toList();

System.out.println(evenTimesTen); // [20, 40]
```

Tương đương về nội dung:

```java
List<Integer> alternative = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10)
    .toList();
```

Với phép lọc và ánh xạ đơn giản, `filter` kết hợp `map` thường **diễn đạt rõ ràng hơn**. `mapMulti` hữu ích hơn khi một đầu vào cần phát **nhiều kết quả** hoặc có logic điều kiện và vòng lặp riêng.

### 7.3. Một phần tử phát nhiều bản ghi

```java
List<Integer> repeated = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        for (int i = 0; i < n; i++) {
            emit.accept(n);
        }
    })
    .toList();

System.out.println(repeated); // [1, 2, 2, 3, 3, 3]
```

Trên ordered stream, thứ tự logic đầu ra phản ánh thứ tự nguồn và các lần phát bên trong callback. **Thứ tự kết quả** vẫn khác **thứ tự thực thi lambda** khi chạy song song.

## 8. `mapMulti` hay `flatMap`?

Yêu cầu: với mỗi `n` dương trong `[1, 2, 3]`, phát dãy `1..n`.

### 8.1. Cách `flatMap`

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

List<Integer> byFlatMap = Stream.of(1, 2, 3)
    .flatMap(n -> IntStream.rangeClosed(1, n).boxed())
    .toList();

System.out.println(byFlatMap); // [1, 1, 2, 1, 2, 3]
```

`flatMap` đã có từ Java 8, nhưng terminal `toList()` trong ví dụ cần Java 16+. Nếu mục tiêu là source code Java 8, dùng `collect(Collectors.toList())` thay cho terminal này.

### 8.2. Cách `mapMulti`

```java
List<Integer> byMapMulti = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        for (int i = 1; i <= n; i++) {
            emit.accept(i);
        }
    })
    .toList();

System.out.println(byMapMulti); // [1, 1, 2, 1, 2, 3]
```

Với `mapMulti`, callback không cần tạo `Stream` con tường minh. API đặc biệt hợp lý khi mỗi đầu vào phát một số lượng **nhỏ, có thể bằng 0**, hoặc cách mô tả logic bằng vòng lặp dễ đọc hơn.

### 8.3. Bảng so sánh

| Tiêu chí | `mapMulti` | `flatMap` |
| --- | --- | --- |
| Phiên bản đầu tiên | Java 16 | Java 8 |
| Mapper | Gọi `Consumer.accept` nhiều lần | Trả một `Stream` con |
| Số phần tử đầu ra | 0..n | 0..n |
| Có phải tạo stream con trong callback? | Không | Có |
| Khi dữ liệu đã là một stream con | Có thể kém tự nhiên hơn | Thường rất thuận tiện |
| Cần lặp/nhánh điều kiện để phát ít kết quả | Thường gọn | Có thể dài hơn |
| Quản lý stream con do mapper tạo | Không có stream con | `flatMap` đóng stream con sau khi tiêu thụ |
| Nhu cầu chạy Java 8/11 | Không dùng được | Dùng được |
| Luôn nhanh hơn? | Không có bảo đảm | Không có bảo đảm |

`mapMulti` có thể giảm overhead tạo nhiều stream con ngắn, **nhưng không có nghĩa luôn nhanh hơn `flatMap`**. Khi có stream con tự nhiên như `group.stream()`, `flatMap` vẫn có thể rõ ràng hơn.

## 9. Các mẫu `mapMulti` trong xử lý dữ liệu

### 9.1. Flatten các danh sách con

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

List<List<String>> groups = Arrays.asList(
    Arrays.asList("A", "B"),
    Collections.<String>emptyList(),
    Arrays.asList("C", "D")
);

List<String> flattened = groups.stream()
    .<String>mapMulti((group, emit) -> {
        for (String value : group) {
            emit.accept(value);
        }
    })
    .toList();

System.out.println(flattened); // [A, B, C, D]
```

Mỗi nhóm được duyệt, phát 0..n phần tử. Nếu đã có `List<List<T>>`, `flatMap(List::stream)` cũng rất tự nhiên; lựa chọn nên dựa vào tính rõ ràng và yêu cầu hiệu năng đo được.

### 9.2. Tách từ và chuẩn hóa

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

List<String> lines = Arrays.asList(
    " Java   Stream ",
    "",
    "mapMulti flatMap"
);

List<String> words = lines.stream()
    .<String>mapMulti((line, emit) -> {
        for (String word : line.trim().split("\\s+")) {
            if (!word.isEmpty()) {
                emit.accept(word.toLowerCase(Locale.ROOT));
            }
        }
    })
    .toList();

System.out.println(words);
// [java, stream, mapmulti, flatmap]
```

`split` vẫn cấp phát mảng và chuỗi theo cách của nó. `mapMulti` chỉ tránh yêu cầu **tạo stream con tường minh**, không xóa mọi chi phí phân tích văn bản.

### 9.3. Chỉ lấy phần tử thuộc một kiểu

```java
import java.util.List;
import java.util.stream.Stream;

List<String> strings = Stream.<Object>of(
        "Java", 42, "Go", 7.5, "Kotlin")
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String) {
            emit.accept((String) value);
        }
    })
    .toList();

System.out.println(strings); // [Java, Go, Kotlin]
```

Cách khác là `filter(String.class::isInstance).map(String.class::cast)`. Khi chỉ có một phép lọc/ép kiểu đơn giản, cách sử dụng hai thao tác riêng có thể dễ đọc hơn.

### 9.4. Tạo nhãn từ bản ghi có danh sách con

Ví dụ Java 16+, có thể đặt toàn bộ đoạn dưới trong thân một phương thức của một lớp:

```java
class Order {
    final String id;
    final List<String> tags;

    Order(String id, List<String> tags) {
        this.id = id;
        this.tags = tags;
    }
}

List<Order> orders = Arrays.asList(
    new Order("D1", Arrays.asList("urgent", "paid")),
    new Order("D2", Arrays.asList("paid")),
    new Order("D3", Arrays.asList())
);

List<String> labels = orders.stream()
    .<String>mapMulti((order, emit) -> {
        for (String tag : order.tags) {
            emit.accept(order.id + ":" + tag);
        }
    })
    .toList();

System.out.println(labels);
// [D1:urgent, D1:paid, D2:paid]
```

Ví dụ giả định đã import `java.util.Arrays` và `java.util.List`. Các phần tử con được phát theo thứ tự trong `tags`. Nếu muốn loại trùng nhãn, có thể thêm `distinct` trước `toList`.

## 10. Generic type inference của `mapMulti`

Vì callback của `mapMulti` trả `void`, trình biên dịch đôi khi **khó suy ra kiểu đầu ra `R`** trong những lambda có nhiều nhánh hoặc chỉ phát dữ liệu khi thỏa điều kiện. Cách khắc phục là khai type witness:

```java
List<Integer> parsed = Stream.of("10", "X", "20")
    .<Integer>mapMulti((text, emit) -> {
        if (text.matches("\\d+")) {
            emit.accept(Integer.parseInt(text));
        }
    })
    .toList();

System.out.println(parsed); // [10, 20]
```

Cú pháp `.<Integer>mapMulti(...)` chỉ rõ `R = Integer`. Nó không làm thay đổi logic runtime.

```java
List<String> converted = Stream.of(10, 20)
    .<String>mapMulti((n, emit) -> {
        emit.accept("N=" + n);
    })
    .toList();

System.out.println(converted); // [N=10, N=20]
```

Ở đây kiểu đầu vào là `Integer`, còn đầu ra là `String`. Hai kiểu không nhất thiết giống nhau.

### 10.1. `Stream.toList()` không tự widen generic

```java
List<Number> numbers = Stream.<Number>of(1, 2.5)
    .toList();

System.out.println(numbers); // [1, 2.5]
```

Không gán trực tiếp `List<Integer>` cho `List<Number>`: Java generics là invariant. Ví dụ `Stream.of(1,2,3).toList()` tạo `List<Integer>`; khi muốn `List<Number>`, hãy cung cấp kiểu `Number` cho stream hoặc phép biến đổi tương ứng.

## 11. Các biến thể trả primitive stream

Trên `Stream<T>`, Java 16 có:

```java
IntStream mapMultiToInt(
    BiConsumer<? super T, ? super IntConsumer> mapper
);

LongStream mapMultiToLong(
    BiConsumer<? super T, ? super LongConsumer> mapper
);

DoubleStream mapMultiToDouble(
    BiConsumer<? super T, ? super DoubleConsumer> mapper
);
```

Những phương thức này giúp phát `int`, `long`, `double` trực tiếp, tránh boxing không cần thiết khi xử lý số.

Ví dụ:

```java
import java.util.stream.Stream;

public class MapMultiToIntExample {
    public static void main(String[] args) {
        int sum = Stream.of("10,20", "", "30")
            .mapMultiToInt((text, emit) -> {
                if (!text.isEmpty()) {
                    for (String token : text.split(",")) {
                        emit.accept(Integer.parseInt(token));
                    }
                }
            })
            .sum();

        System.out.println(sum); // 60
    }
}
```

### 11.1. Primitive stream cũng có `mapMulti`

`IntStream.mapMulti(IntMapMultiConsumer)` nhận số `int` và một `IntConsumer`:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class IntStreamMapMultiExample {
    public static void main(String[] args) {
        int[] values = IntStream.of(1, 2, 3, 4)
            .mapMulti((n, emit) -> {
                if (n % 2 == 0) {
                    emit.accept(n);
                    emit.accept(n * 10);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(values));
        // [2, 20, 4, 40]
    }
}
```

Tương tự có `LongStream.mapMulti(LongMapMultiConsumer)` và `DoubleStream.mapMulti(DoubleMapMultiConsumer)`.

| Phương thức | Nguồn | Kết quả |
| --- | --- | --- |
| `Stream.mapMulti` | `Stream<T>` | `Stream<R>` |
| `Stream.mapMultiToInt` | `Stream<T>` | `IntStream` |
| `Stream.mapMultiToLong` | `Stream<T>` | `LongStream` |
| `Stream.mapMultiToDouble` | `Stream<T>` | `DoubleStream` |
| `IntStream.mapMulti` | `IntStream` | `IntStream` |
| `LongStream.mapMulti` | `LongStream` | `LongStream` |
| `DoubleStream.mapMulti` | `DoubleStream` | `DoubleStream` |

Nếu đầu ra được dùng để tính tổng hoặc thống kê số, primitive stream có thể tránh overhead của `Integer`/`Long`/`Double`. Tuy vậy, tràn số nguyên và sai số dấu phẩy động vẫn cần được xử lý theo yêu cầu nghiệp vụ.


## 12. Vòng đời consumer, tính lazy và parallel stream

`mapMulti` không chạy ngay khi xây pipeline:

```java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n * 2);
    });

// Chưa có terminal operation, chưa yêu cầu tiêu thụ nguồn.
List<Integer> values = pipeline.toList();

System.out.println(values); // [2, 4, 6]
```

Các yêu cầu tương tự mapper của Stream:

- **Non-interfering:** không sửa cấu trúc nguồn trong lúc duyệt.
- **Stateless:** không dùng bộ đếm hoặc list mutable bên ngoài để quyết định đầu ra theo thứ tự thread.
- **Consumer chỉ dùng trong callback:** không lưu lại `emit` để gọi sau, không chuyển cho thread khác rồi gọi sau khi mapper kết thúc.
- **Không phụ thuộc tác dụng phụ:** terminal operation hoặc short-circuit có thể không đánh giá mọi callback theo cách bạn dự đoán.

### 12.1. Sai: lưu consumer để phát kết quả về sau

```java
// KHÔNG NÊN:
// List<Consumer<Integer>> saved = new ArrayList<>();
//
// Stream.of(1, 2)
//     .<Integer>mapMulti((n, emit) -> saved.add(emit))
//     .toList();
//
// saved.forEach(consumer -> consumer.accept(100));
```

Consumer do `mapMulti` nhận được thuộc phạm vi xử lý của stream runtime; nó **không phải đối tượng có thể lưu giữ để phát kết quả sau này**. Dù callback không chạy song song, cách trên vẫn vi phạm ý nghĩa của API.

### 12.2. `limit` có thể short-circuit

```java
List<Integer> first = Stream.of(1, 2, 3, 4)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(n * 10);
    })
    .limit(3)
    .toList();

System.out.println(first); // [1, 10, 2]
```

`limit(3)` giữ ba phần tử đầu của **luồng đầu ra**, không phải ba phần tử đầu của nguồn. Không dựa vào việc mapper được gọi bao nhiêu lần hay có bao nhiêu lần `emit.accept` được xử lý nội bộ; cách buffering và short-circuit phụ thuộc pipeline/triển khai.

Một mapper sinh nhiều kết quả mỗi lần gọi có thể tiêu tốn tài nguyên ngay cả khi downstream chỉ cần ít kết quả. Việc chọn `mapMulti` thay `flatMap` phải dựa vào cả **quy mô đầu ra mỗi phần tử** và mục tiêu xử lý, không chỉ số dòng mã.

### 12.3. Parallel stream: thứ tự logic khác thứ tự chạy

```java
List<Integer> result = Stream.of(1, 2, 3, 4)
    .parallel()
    .<Integer>mapMulti((n, emit) -> {
        if (n % 2 == 0) {
            emit.accept(n);
            emit.accept(n * 10);
        }
    })
    .toList();

System.out.println(result); // [2, 20, 4, 40]
```

Trong ví dụ, mapper không lưu trạng thái bên ngoài. `toList` tôn trọng encounter order của nguồn ordered ngay cả khi callback thực thi ở nhiều thread. Nhưng viết:

```java
// KHÔNG NÊN:
// List<Integer> external = new ArrayList<>();
// Stream.of(1,2,3,4).parallel()
//     .<Integer>mapMulti((n, emit) -> {
//         external.add(n); // Tác dụng phụ không an toàn.
//         emit.accept(n);
//     }).toList();
```

có thể gây race condition hoặc làm logic sai lệch. Dùng collector/terminal operation thay vì cập nhật `ArrayList` chia sẻ.

### 12.4. Nguồn I/O vẫn cần đóng riêng

`mapMulti` không tự đóng một nguồn như `Files.lines`; `toList` cũng không tự giải phóng mọi tài nguyên của nguồn I/O. Ví dụ Java 16+:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> readWords(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines.<String>mapMulti((line, emit) -> {
            for (String word : line.split("\\s+")) {
                if (!word.isEmpty()) {
                    emit.accept(word);
                }
            }
        }).toList();
    }
}
```

Ở đây `try-with-resources` đóng `lines` khi hoàn thành hoặc gặp lỗi. Nếu callback tự mở tài nguyên khác, phải quản lý việc đóng tài nguyên đó trong đúng phạm vi sở hữu. `mapMulti` không phải công cụ thay thế cơ chế quản lý I/O.

## 13. Mối quan hệ với collector, grouping và Stream Gatherers

`mapMulti` xử lý **một phần tử đầu vào rồi phát 0..n phần tử**. Nó không phải một collector hoặc cơ chế phân nhóm:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<List<String>> groups = Arrays.asList(
    Arrays.asList("Java", "Go"),
    Arrays.asList("Java", "Kotlin")
);

Map<Integer, Long> counts = groups.stream()
    .<String>mapMulti((group, emit) -> {
        for (String value : group) {
            emit.accept(value);
        }
    })
    .collect(Collectors.groupingBy(
        String::length,
        Collectors.counting()
    ));

System.out.println(counts.get(4)); // 2 (Java, Java)
```

- `mapMulti` làm phẳng các nhóm thành stream chuỗi.
- `groupingBy` là collector cho terminal `collect`.
- `counting` tính số lượng mỗi nhóm.
- Không có `toList` ở pipeline này vì kết quả mong muốn là `Map<Integer, Long>`.

Tương tự, `mapMulti` không thay thế `reduce`; nếu muốn tổng hợp các số, hãy dùng `mapMultiToInt(...).sum()` hoặc downstream thích hợp.

Stream Gatherers là một nhóm API khác (ở các JDK mới hơn Java 16) dành cho những phép biến đổi có trạng thái hoặc cửa sổ phức tạp. Đừng xem `mapMulti` như một collector stateful hoặc một gatherer: callback `mapMulti` phải thỏa các quy tắc stateless/non-interfering của một intermediate operation.

## 14. Tương thích Java 8/11 và chiến lược nâng cấp

### 14.1. Đoạn Java 16 không biên dịch dưới `--release 11`

```java
List<String> names = Stream.of("Java", "Go").toList();

List<Integer> output = Stream.of(1, 2)
    .<Integer>mapMulti((n, emit) -> emit.accept(n * 10))
    .toList();
```

Cả `Stream.toList` và `mapMulti` đều được giới thiệu ở Java 16. Nếu dự án đặt `--release 8` hay `--release 11`, compiler không thấy những phương thức đó, cho dù máy đang dùng một JDK mới hơn để chạy compiler.

Một đoạn code được biên dịch cho Java 16 cũng phải được chạy trên môi trường tương thích với **class-file version** và API Java 16. Chỉ nâng compiler mà không kiểm tra runtime của hệ thống triển khai có thể làm ứng dụng thất bại khi khởi chạy.

### 14.2. Mẫu Java 8 tương đương về dữ liệu

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Java8Fallback {
    public static void main(String[] args) {
        List<String> names = Stream.of("Java", "Go")
            .collect(Collectors.toList());

        List<Integer> output = Arrays.asList(1, 2)
            .stream()
            .flatMap(n -> Stream.of(n, n * 10))
            .collect(Collectors.toList());

        System.out.println(names);  // [Java, Go]
        System.out.println(output); // [1, 10, 2, 20]
    }
}
```

Dữ liệu tương đương, **nhưng `Collectors.toList()` không cam kết unmodifiable**. Khi yêu cầu bắt buộc là list không cho phép sửa và chấp nhận null trên Java 8, hãy dùng wrapper `Collections.unmodifiableList` quanh list mới không bị lộ tham chiếu ngoài.

Nếu cần list có thể sửa rõ ràng, dùng `Collectors.toCollection(ArrayList::new)` từ Java 8. Nếu cần list **không cho phép sửa và không chấp nhận null**, Java 10 có `Collectors.toUnmodifiableList`; Java 8 cần kiểm tra null riêng và wrapper phù hợp.

### 14.3. Biên dịch mã Java 16+

Từ terminal của một máy **đã cài JDK hỗ trợ Java 16 trở lên**, với file `Jdk16StreamCheck.java` ở mục tiếp theo:

```text
javac --release 16 Jdk16StreamCheck.java
java Jdk16StreamCheck
```

Đây là hướng dẫn để tự chạy, **không phải kết quả biên dịch đã được xác minh trong bài này**. Trong dự án Gradle/Maven, hãy đảm bảo toolchain, target release và JDK runtime thực tế đều hỗ trợ API được sử dụng.

Khi ứng dụng cần chạy trên Java 11, không đặt `--release 16` rồi kỳ vọng bytecode chạy được dưới JDK 11. Thay vào đó, sử dụng các API tương thích hoặc nâng yêu cầu nền tảng của ứng dụng.

## 15. Chương trình kiểm chứng tổng hợp (Java 16+)

Tạo file `Jdk16StreamCheck.java` với nội dung dưới đây. Chương trình kiểm tra:

- `toList` giữ thứ tự và giá trị trùng.
- List kết quả không cho sửa.
- `toList` nhận null, `toUnmodifiableList` từ chối null.
- `mapMulti` phát 0..n phần tử.
- `mapMultiToInt` và `IntStream.mapMulti`.
- Kết quả ordered parallel stream.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class Jdk16StreamCheck {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> names = Stream.of("Java", "Go", "Java")
            .toList();

        check(names.equals(Arrays.asList("Java", "Go", "Java")),
            "toList sai thu tu hoac gia tri trung");

        boolean rejectedAdd = false;
        try {
            names.add("Rust");
        } catch (UnsupportedOperationException expected) {
            rejectedAdd = true;
        }
        check(rejectedAdd, "toList phai unmodifiable");

        List<String> nullable = Stream.of(
            "A", (String) null, "B").toList();

        check(nullable.size() == 3 && nullable.get(1) == null,
            "toList phai chap nhan null");

        boolean rejectedNull = false;
        try {
            Stream.of("A", (String) null)
                .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }
        check(rejectedNull, "toUnmodifiableList phai tu choi null");

        List<Integer> expanded = Stream.of(1, 2, 3)
            .<Integer>mapMulti((n, emit) -> {
                for (int i = 0; i < n; i++) {
                    emit.accept(n);
                }
            })
            .toList();

        check(expanded.equals(Arrays.asList(1, 2, 2, 3, 3, 3)),
            "mapMulti sai so phan tu");

        List<Integer> even = Stream.of(1, 2, 3, 4)
            .<Integer>mapMulti((n, emit) -> {
                if (n % 2 == 0) {
                    emit.accept(n * 10);
                }
            })
            .toList();

        check(even.equals(Arrays.asList(20, 40)),
            "mapMulti loc sai");

        int sum = Stream.of("1,2", "", "3")
            .mapMultiToInt((text, emit) -> {
                if (!text.isEmpty()) {
                    for (String token : text.split(",")) {
                        emit.accept(Integer.parseInt(token));
                    }
                }
            })
            .sum();

        check(sum == 6, "mapMultiToInt sai tong");

        int[] primitive = IntStream.of(1, 2, 3)
            .mapMulti((n, emit) -> {
                emit.accept(n);
                if (n % 2 == 0) {
                    emit.accept(n * 10);
                }
            })
            .toArray();

        check(Arrays.equals(
                primitive, new int[] {1, 2, 20, 3}),
            "IntStream.mapMulti sai");

        List<Integer> parallel = Stream.of(1, 2, 3, 4)
            .parallel()
            .<Integer>mapMulti((n, emit) -> {
                emit.accept(n);
                emit.accept(n * 10);
            })
            .toList();

        check(parallel.equals(Arrays.asList(
                1, 10, 2, 20, 3, 30, 4, 40)),
            "mapMulti song song sai encounter order");

        ArrayList<Integer> mutable = Stream.of(1, 2)
            .collect(Collectors.toCollection(ArrayList::new));
        mutable.add(3);

        check(mutable.equals(Arrays.asList(1, 2, 3)),
            "toCollection phai cho phep sua");

        System.out.println("PASS: Stream.toList va mapMulti");
    }
}
```

Khi biên dịch và chạy thành công trên Java 16+, chương trình in:

```text
PASS: Stream.toList va mapMulti
```

Mẫu này kiểm tra những hợp đồng được chọn, không phải benchmark hiệu năng hoặc phép chứng minh mọi callback tùy chỉnh đều đúng. Cần bổ sung kiểm thử dữ liệu biên, nguồn rỗng, null và giới hạn tài nguyên cho ứng dụng thực tế.

## 16. Những hiểu nhầm và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: toList()` | Đang biên dịch theo API trước Java 16 | Dùng `collect` tương thích hoặc nâng release. |
| `cannot find symbol: mapMulti(...)` | JDK API trước Java 16 | Dùng `flatMap` trên Java 8/11. |
| `list.add(...)` ném `UnsupportedOperationException` | `Stream.toList()` trả list không cho phép sửa | Dùng `toCollection(ArrayList::new)` nếu cần sửa. |
| Thay `Collectors.toList()` bằng `toList` rồi downstream bị lỗi | Hai cách không có cùng hợp đồng mutability | Rà soát các chỗ `add`, `remove`, `sort`, `set`. |
| Nghĩ `toList()` luôn trả `ArrayList` | Không cam kết loại implementation | Dùng interface `List` hoặc collection factory tường minh. |
| Nghĩ `toList()` không chấp nhận null | Nhầm với `List.of` / `toUnmodifiableList` | Xác định rõ chính sách null. |
| Dữ liệu null bị lọc mất không báo lỗi | Tự thêm `filter(Objects::nonNull)` | Chọn bỏ null hay báo lỗi theo nghiệp vụ. |
| So sánh hai list bằng `==` | Nhầm danh tính với nội dung, value-based instance | Dùng `equals` để kiểm tra giá trị. |
| Dùng `List<Number>` cho `Stream<Integer>.toList()` | Generic invariant | Khai `Stream.<Number>of(...)` hoặc biến đổi kiểu. |
| `mapMulti` có lỗi type inference | Compiler chưa suy ra `R` từ callback | Dùng `.<R>mapMulti(...)`. |
| `mapMulti` không phát giá trị nào | Mapper không gọi consumer | Kiểm tra các nhánh điều kiện và số lần `accept`. |
| `mapMulti` phát dữ liệu lặp ngoài ý muốn | Gọi consumer nhiều lần | Làm rõ quy tắc 0..n; dùng `distinct` khi cần. |
| Kỳ vọng `mapMulti` nhanh hơn mọi `flatMap` | Hiệu năng phụ thuộc dữ liệu và JDK | Benchmark trên workload đại diện. |
| Cố giữ consumer để gọi sau | Vi phạm vòng đời consumer | Chỉ phát kết quả bên trong callback. |
| List bị sửa sai khi dùng parallel | Lambda viết trạng thái dùng chung | Dùng hàm stateless và terminal collector. |
| Đếm sai số callback khi `limit`/`findFirst` | Short-circuit và tối ưu hóa không cam kết số lần gọi | Không dùng side effect làm logic bắt buộc. |
| Dùng `Stream.toList` để sắp xếp tại chỗ | List trả về unmodifiable | Dùng `sorted` trước hoặc thu list mutable. |
| Mất tài nguyên I/O dù có `toList` | Terminal operation không thay `close` nguồn | `try-with-resources` khi nguồn gắn với I/O. |
| Mã chạy trên JDK mới nhưng lỗi ở môi trường triển khai cũ | Runtime/release không tương thích | Kiểm tra toolchain và phiên bản chạy thực. |

## 17. Bài tập thực hành

### Bài 1 — List nào có thể sửa?

Xét:

```java
List<Integer> a = Stream.of(1, 2).toList();
List<Integer> b = Stream.of(1, 2)
    .collect(Collectors.toList());
ArrayList<Integer> c = Stream.of(1, 2)
    .collect(Collectors.toCollection(ArrayList::new));
```

Trong ba list, list nào **được cam kết** có thể sửa, list nào **được cam kết** không thể sửa, và list nào không có cam kết mutability?

### Bài 2 — `null`

Dự đoán kết quả:

```java
List<String> a = Stream.of("A", null, "B").toList();
List<String> b = Stream.of("A", null, "B")
    .collect(Collectors.toUnmodifiableList());
```

Bài nào thành công, bài nào ném lỗi? Giải thích phiên bản JDK tối thiểu.

### Bài 3 — Chuyển từ `flatMap` sang `mapMulti`

Dùng `mapMulti` để phát các giá trị trong `List<List<Integer>>` sau:

```java
List<List<Integer>> batches = Arrays.asList(
    Arrays.asList(1, 2),
    Arrays.asList(),
    Arrays.asList(3, 4)
);
```

Kết quả cần là `[1, 2, 3, 4]`. Viết thêm cách `flatMap` tương ứng và giải thích sự khác biệt về version.

### Bài 4 — Chọn `map`, `filter` hay `mapMulti`?

Cho `[1, 2, 3]`, mỗi số `n` phải tạo các kết quả `n` và `-n`. Viết bằng `mapMulti`. Nếu bài toán chỉ yêu cầu `n * 2`, API nào dễ đọc hơn?

### Bài 5 — Primitive stream

Cho các chuỗi `["5,10", "", "15"]`. Dùng `mapMultiToInt` để tính tổng. Vì sao cách này có thể tránh boxing so với `mapMulti` trả `Stream<Integer>`?

### Bài 6 — Generic inference

Viết `mapMulti` từ `Stream<Object>` chỉ giữ phần tử kiểu `String`. Dùng type witness để tạo `List<String>` và giải thích vì sao phải thống nhất kiểu `R`.

### Bài 7 — Java 11 vẫn cần list không cho sửa

Một dự án phải chạy Java 11, cần kết quả không cho phép sửa và **chấp nhận null**. Vì sao không dùng `Stream.toList` hoặc `Collectors.toUnmodifiableList`? Viết phương án dùng `Collections.unmodifiableList` với list riêng.

### Bài 8 — Thứ tự và short-circuit

```java
List<Integer> result = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(n * 10);
    })
    .limit(4)
    .toList();
```

Dự đoán nội dung list. Có thể khẳng định callback chỉ được gọi đúng hai lần ở mọi triển khai không?

## 18. Đáp án tham khảo

**Bài 1:** `a` **không cho phép sửa** theo hợp đồng `Stream.toList`. `b` **không cam kết** có thể sửa hoặc không (`Collectors.toList`); không dựa vào quan sát ở một JDK cụ thể. `c` là `ArrayList` và có thể sửa.

**Bài 2:** `a` tạo `[A, null, B]` thành công trên Java 16+. `b` ném `NullPointerException` vì `Collectors.toUnmodifiableList` từ Java 10 từ chối null.

**Bài 3:**

```java
List<Integer> withMapMulti = batches.stream()
    .<Integer>mapMulti((batch, emit) -> {
        for (Integer n : batch) {
            emit.accept(n);
        }
    })
    .toList();

List<Integer> withFlatMap = batches.stream()
    .flatMap(List::stream)
    .toList();
```

Cả hai cho `[1, 2, 3, 4]` trên Java 16+. Nếu cần Java 8, `flatMap` có sẵn nhưng terminal phải đổi sang `collect(Collectors.toList())`.

**Bài 4:**

```java
List<Integer> output = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(-n);
    })
    .toList();

System.out.println(output); // [1, -1, 2, -2, 3, -3]
```

Nếu chỉ cần nhân đôi, `map(n -> n * 2)` đơn giản hơn và nêu rõ quan hệ một–một.

**Bài 5:**

```java
int sum = Stream.of("5,10", "", "15")
    .mapMultiToInt((text, emit) -> {
        if (!text.isEmpty()) {
            for (String token : text.split(",")) {
                emit.accept(Integer.parseInt(token));
            }
        }
    })
    .sum();

System.out.println(sum); // 30
```

Đầu ra là `IntStream` nên không cần tạo `Integer` boxed cho từng số qua `Stream<Integer>`.

**Bài 6:**

```java
List<String> strings = Stream.<Object>of(
        "Java", 42, "Go", true)
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String) {
            emit.accept((String) value);
        }
    })
    .toList();
```

Type witness `<String>` xác định kiểu đầu ra `R`; phần tử không phải `String` không được phát.

**Bài 7:**

```java
List<String> list = java.util.Collections.unmodifiableList(
    Stream.of("A", null, "B")
        .collect(Collectors.toCollection(
            java.util.ArrayList::new))
);
```

`Stream.toList` chỉ có từ Java 16; `toUnmodifiableList` có từ Java 10 nhưng từ chối null. Wrapper trên một list mới không bị lộ tham chiếu mutable đáp ứng yêu cầu cấu trúc của ví dụ, nhưng không làm bất biến các đối tượng bên trong.

**Bài 8:** `result = [1, 10, 2, 20]`. `limit(4)` giới hạn đầu ra, không tạo hợp đồng rằng callback được gọi đúng hai lần ở mọi cách triển khai. Không sử dụng side effect để đếm số lần callback bắt buộc phải chạy.

## 19. Checklist nâng cấp từ Java 8/11 sang Java 16+

Trước khi thay mã cũ, kiểm tra:

- [ ] JDK để biên dịch và môi trường chạy đều hỗ trợ Java 16+ nếu dùng `toList`/`mapMulti`.
- [ ] Mức `--release` hoặc toolchain của dự án không còn thấp hơn Java 16.
- [ ] Mã downstream có gọi `add`, `remove`, `sort`, `set` trên list kết quả hay không.
- [ ] Ứng dụng có yêu cầu loại list cụ thể (ví dụ `ArrayList`) hoặc có cần list có thể sửa không.
- [ ] Chính sách về `null` đã rõ: chấp nhận, bỏ qua hay báo lỗi.
- [ ] Có phụ thuộc danh tính list trả về hoặc dùng list như khóa đồng bộ hóa không.
- [ ] Kiểu generic `R` của `mapMulti` được suy ra đúng; thêm type witness nếu cần.
- [ ] Callback `mapMulti` chỉ phát dữ liệu trong lúc mapper chạy và không giữ consumer để gọi sau.
- [ ] Callback stateless và non-interfering, không cập nhật cấu trúc dùng chung khi parallel.
- [ ] `mapMulti` có phát nhiều kết quả đến mức gây vấn đề bộ nhớ hoặc short-circuit không.
- [ ] Đã cân nhắc primitive variants để tránh boxing khi làm việc với số.
- [ ] Nếu mã đang dùng `flatMap`, có lợi ích rõ ràng khi đổi hay chỉ tăng độ phức tạp.
- [ ] Stream nguồn gắn với I/O vẫn được đóng bằng `try-with-resources`.
- [ ] Đã thử nguồn rỗng, một phần tử, null, nhiều kết quả, dữ liệu trùng, ordered parallel và short-circuit.
- [ ] Nếu hiệu năng quan trọng, đã benchmark trên workload đại diện thay vì suy đoán.

## 20. Tổng kết

`Stream.toList()` và `Stream.mapMulti(...)` đều là bổ sung từ **Java 16**, nhưng đảm nhiệm hai vai trò khác nhau:

```java
// Terminal operation: thu một list không cho phép sửa.
List<String> values = Stream.of("A", "B").toList();

// Intermediate operation: mỗi đầu vào phát 0..n kết quả.
List<Integer> expanded = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(n * 10);
    })
    .toList();
```

- **`toList`:** giữ encounter order nếu nguồn ordered, cho phép null, không cho phép sửa list, không cam kết loại triển khai hoặc danh tính.
- **`Collectors.toList`:** tương thích Java 8 nhưng **không cam kết** khả năng sửa và kiểu list.
- **`Collectors.toUnmodifiableList`:** có từ Java 10, không cho sửa và **từ chối null**.
- **`mapMulti`:** phát 0..n phần tử thông qua consumer, có thể diễn đạt vòng lặp/điều kiện rõ hơn `flatMap` trong một số bài toán.
- **Primitive variants:** `mapMultiToInt/Long/Double` và primitive `mapMulti` từ Java 16 tránh boxing không cần thiết.
- **Tương thích và hiệu năng:** chọn API theo hợp đồng, mức JDK, dữ liệu và kiểm thử; không thay mã cơ học và không giả định `mapMulti` luôn nhanh hơn `flatMap`.

Hiểu kỹ hai bổ sung này giúp bạn nâng cấp Java Stream API một cách an toàn: viết pipeline rõ ràng, bảo đảm ngữ nghĩa đầu ra và kiểm soát tương thích JDK trước khi tối ưu hóa hay đưa chương trình vào môi trường thực tế.
