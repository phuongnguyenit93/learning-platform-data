# Dùng `Supplier`, `BiFunction` và `BinaryOperator` đúng vai trò

Trong **Java Stream API**, các phép toán `filter`, `map`, `reduce`, `collect` và các collector nhận **hàm hành vi** để mô tả cách xử lý dữ liệu. Pipeline được đánh giá *lazy*: phần lớn phép toán trung gian chỉ chạy khi có terminal operation. Ba functional interface thường xuất hiện khi tạo dữ liệu, tính toán với hai đầu vào và kết hợp kết quả là `Supplier`, `BiFunction` và `BinaryOperator`.

Chúng có thể được viết bằng lambda hoặc method reference, nhưng **không thay thế lẫn nhau tùy ý**. Chọn sai kiểu hàm có thể khiến chương trình không biên dịch, dùng sai ngữ nghĩa `reduce`/`collect`, hoặc trả kết quả không ổn định khi chạy song song.

## 1. Nhìn vào đầu vào và đầu ra để phân biệt

Các kiểu dưới đây thuộc gói `java.util.function`, có từ Java 8:

| Functional interface | Phương thức trừu tượng duy nhất | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `Supplier<T>` | `T get()` | Không nhận đối số; **cung cấp** một giá trị `T` khi được gọi. | `ArrayList::new`, `() -> "new"` |
| `BiFunction<T, U, R>` | `R apply(T t, U u)` | Nhận **hai giá trị**, có thể khác kiểu, trả một kết quả kiểu `R`. | `(name, n) -> name + n` |
| `BinaryOperator<T>` | `T apply(T left, T right)` | Nhận **hai giá trị cùng kiểu `T`**, trả kết quả cũng kiểu `T`. | `Integer::sum` |

`BinaryOperator<T>` **kế thừa** `BiFunction<T, T, T>`; nó là một trường hợp đặc biệt, dùng khi hành vi kết hợp hai giá trị cùng loại thành một giá trị cùng loại. Ngược lại, `BiFunction<String, Integer, Long>` không thể được xem là `BinaryOperator<?>`, vì các kiểu đầu vào và đầu ra không đồng nhất.

```java
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.function.Supplier;

Supplier<String> newLabel = () -> "pending";
BiFunction<String, Integer, String> appendIndex =
    (label, index) -> label + "-" + index;
BinaryOperator<Integer> add = Integer::sum;

System.out.println(newLabel.get());              // pending
System.out.println(appendIndex.apply("task", 7)); // task-7
System.out.println(add.apply(10, 20));            // 30
```

**Cách đọc nhanh:** không có tham số thì nghĩ tới `Supplier`; có hai tham số và cần một kết quả thì nghĩ tới `BiFunction`; nếu cả hai tham số và kết quả phải cùng kiểu, `BinaryOperator` diễn đạt ý định rõ hơn.

## 2. `Supplier<T>`: cung cấp giá trị hoặc tạo đối tượng khi cần

`Supplier<T>` có một phương thức `get()` và không nhận đối số. Nó thường làm **factory** tạo đối tượng mới, sinh phần tử cho stream, hoặc trì hoãn việc tính giá trị dự phòng.

### Tạo container mới cho mỗi lần yêu cầu

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

Supplier<List<String>> newList = ArrayList::new;

List<String> left = newList.get();
List<String> right = newList.get();
left.add("Java");

System.out.println(left);          // [Java]
System.out.println(right);         // []
System.out.println(left == right); // false
```

**Bản thân interface không bảo đảm mỗi lần `get()` trả về đối tượng mới.** Bảo đảm đó đến từ cách triển khai `ArrayList::new`. Với `collect`, `groupingBy` và collector tùy chỉnh cần container có thể thay đổi, supplier thường phải tạo **container độc lập** cho các nhánh tích lũy; dùng `() -> sharedList` dễ gây trộn dữ liệu và lỗi đồng thời.

### Sinh phần tử theo nhu cầu bằng `Stream.generate`

```java
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Supplier<String> makeId = () -> UUID.randomUUID().toString();

List<String> ids = Stream.generate(makeId)
    .limit(3)
    .collect(Collectors.toList());

System.out.println(ids.size()); // 3
```

`Stream.generate(supplier)` tạo một stream tuần tự, **không có thứ tự gặp phần tử được bảo đảm (unordered)** và có khả năng vô hạn; `limit(3)` tạo ranh giới hữu hạn cho trường hợp này. Khi pipeline chạy, stream gọi supplier để đáp ứng nhu cầu phần tử. Không giả định `get()` chỉ được gọi một lần cho toàn bộ stream, cũng không giả định thứ tự hoặc số lần gọi lambda khi chuyển pipeline sang song song. Nếu supplier lưu trạng thái có thể thay đổi, cần xét tính an toàn luồng và tính ổn định của kết quả.

### Chỉ tính giá trị dự phòng khi thật sự cần

```java
import java.util.Optional;
import java.util.function.Supplier;

Optional<String> cached = Optional.of("ready");

Supplier<String> fallback = () -> {
    System.out.println("Tạo giá trị dự phòng");
    return "default";
};

String result = cached.orElseGet(fallback);
System.out.println(result); // ready
// Không in "Tạo giá trị dự phòng" vì Optional đã có giá trị.
```

`orElseGet(Supplier<? extends T>)` chỉ gọi supplier khi `Optional` rỗng; trong khi biểu thức đối số của `orElse(value)` được tính trước khi gọi phương thức. Khi tạo giá trị dự phòng tốn công hoặc có tác động phụ, khác biệt này đáng chú ý. **Supplier không tự tạo ra lazy evaluation**: việc trì hoãn phụ thuộc API nhận supplier có quyết định gọi `get()` hay không.

## 3. `BiFunction<T, U, R>`: biến hai dữ liệu thành một kết quả

`BiFunction` nhận hai đối số có thể **khác kiểu** và trả một kết quả có kiểu riêng. Ví dụ, kết hợp tên sản phẩm với số lượng để sinh nhãn:

```java
import java.util.function.BiFunction;

BiFunction<String, Integer, String> formatOrder =
    (product, quantity) -> product + " x " + quantity;

System.out.println(formatOrder.apply("Notebook", 3));
// Notebook x 3
```

Ba type parameter có vai trò rõ ràng: `T` là kiểu đầu vào thứ nhất, `U` là kiểu đầu vào thứ hai, `R` là kiểu kết quả. Nếu kết quả phải chuyển tiếp qua một bước biến đổi, `BiFunction.andThen(Function<? super R, ? extends V>)` cho phép gắn thêm bước xử lý:

```java
import java.util.function.BiFunction;

BiFunction<String, Integer, String> format =
    (product, quantity) -> product + " x " + quantity;

BiFunction<String, Integer, String> loudFormat =
    format.andThen(String::toUpperCase);

System.out.println(loudFormat.apply("notebook", 3));
// NOTEBOOK X 3
```

### Áp dụng `BiFunction` trong pipeline

`Stream.map` nhận `Function<T, R>` **một tham số**, nên không thể truyền trực tiếp một `BiFunction` vào `map`. Nếu tham số thứ hai đến từ ngữ cảnh, có thể dùng lambda một tham số để gọi `apply`:

```java
import java.util.List;
import java.util.function.BiFunction;
import java.util.stream.Collectors;
import java.util.stream.Stream;

BiFunction<String, Integer, String> attachBatch =
    (name, batchNo) -> name + "@batch-" + batchNo;

int batchNo = 12;
List<String> labels = Stream.of("filter", "map", "reduce")
    .map(name -> attachBatch.apply(name, batchNo))
    .collect(Collectors.toList());

System.out.println(labels);
// [filter@batch-12, map@batch-12, reduce@batch-12]
```

Trong các API khác của Java, `Map.compute(key, remappingFunction)` nhận `BiFunction<? super K, ? super V, ? extends V>`: hàm xử lý cả khóa lẫn giá trị cũ. Cần đọc hợp đồng của API cụ thể; ví dụ giá trị `null` trả về từ remapping function của `Map.compute` có thể dẫn tới xóa mapping đang có.

## 4. `BinaryOperator<T>`: kết hợp hai giá trị cùng kiểu

`BinaryOperator<T>` chính là `BiFunction<T, T, T>` với tên biểu thị vai trò **kết hợp hai giá trị cùng loại**. Đó là kiểu được `reduce` sử dụng khi phần tử đầu vào và kết quả tích lũy cùng kiểu.

```java
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

BinaryOperator<Integer> add = Integer::sum;

int total = Stream.of(4, 6, 8).reduce(0, add);
Optional<Integer> maybeTotal = Stream.of(4, 6, 8).reduce(add);

System.out.println(total);              // 18
System.out.println(maybeTotal.orElse(0)); // 18
```

`reduce(identity, BinaryOperator<T>)` trả về `T` và cần một giá trị khởi tạo phù hợp. `reduce(BinaryOperator<T>)` trả về `Optional<T>` vì stream có thể rỗng. Với phép cộng số nguyên, `0` là phần tử đơn vị; với phép nhân, `1` là phần tử đơn vị.

`BinaryOperator` còn cung cấp các phương thức tĩnh `minBy(comparator)` và `maxBy(comparator)` để tạo phép chọn phần tử nhỏ/lớn theo bộ so sánh:

```java
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

BinaryOperator<String> longest = BinaryOperator.maxBy(
    (a, b) -> Integer.compare(a.length(), b.length())
);

Optional<String> value = Stream.of("API", "Stream", "Java")
    .reduce(longest);

System.out.println(value.orElse("(empty)")); // Stream
```

Với bài toán chỉ tìm giá trị lớn nhất, `stream.max(comparator)` thường diễn đạt trực tiếp hơn; ví dụ `BinaryOperator.maxBy` giúp nhận diện rằng `reduce` kỳ vọng phép kết hợp cùng kiểu. Nếu bộ so sánh cho rằng hai giá trị bằng nhau, không nên dựa vào việc chọn bên trái hay bên phải để mã hóa yêu cầu nghiệp vụ riêng.

## 5. `reduce` ba tham số: `BiFunction` và `BinaryOperator` phối hợp thế nào?

Phiên bản tổng quát của `Stream.reduce` có chữ ký về mặt kiểu như sau:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Ở đây, phần tử của stream có kiểu `T`, còn kết quả tích lũy có kiểu `U` **có thể khác `T`**:

- `identity`: giá trị khởi tạo của kiểu kết quả `U`.
- `accumulator`: kết hợp **kết quả tạm `U`** và **một phần tử `T`** để tạo `U` mới; do đó dùng `BiFunction<U, T, U>`.
- `combiner`: kết hợp **hai kết quả tạm cùng kiểu `U`** để tạo `U`; do đó dùng `BinaryOperator<U>`.

Ví dụ tính tổng số ký tự trong stream các chuỗi:

```java
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

BiFunction<Integer, String, Integer> countChars =
    (total, word) -> total + word.length();

BinaryOperator<Integer> mergeTotals = Integer::sum;

int charCount = Stream.of("Java", "Stream", "API")
    .parallel()
    .reduce(0, countChars, mergeTotals);

System.out.println(charCount); // 13 (= 4 + 6 + 3)
```

Trong nhánh xử lý tuần tự, accumulator nhận tổng tạm và chuỗi tiếp theo. Khi thực thi song song, các nhánh có thể tính tổng riêng; combiner cộng những tổng đó. Dù một quá trình thực thi cụ thể có sử dụng bao nhiêu nhánh, kết quả đúng phải tuân thủ các hợp đồng của `reduce`.

### Các quy tắc để giảm đúng trong song song

1. **Combiner phải kết hợp được theo tính kết hợp (associativity):** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)` theo ngữ nghĩa phép toán. Phép cộng số nguyên phù hợp; phép trừ thường không phù hợp.
2. **Identity phải là phần tử đơn vị hai phía của combiner:** `combiner(identity, u) = combiner(u, identity) = u`.
3. **Accumulator phải tương thích với combiner:** `combiner(u, accumulator(identity, t)) = accumulator(u, t)` cho giá trị tích lũy `u` và phần tử `t`.
4. **Hàm hành vi phải không can thiệp nguồn và không dựa vào trạng thái có thể thay đổi bên ngoài:** không sửa collection đang làm nguồn, không cập nhật một bộ đếm dùng chung như cách tính kết quả chính.

Ví dụ sai thường gặp:

```java
import java.util.stream.Stream;

// KHÔNG DÙNG làm phép reduce đáng tin cậy khi chạy song song:
int result = Stream.of(10, 3, 2)
    .parallel()
    .reduce(0, (left, right) -> left - right);

// Phép trừ không có tính kết hợp; 0 cũng không là đơn vị hai phía.
// Không suy ra được một "tổng trừ tuần tự" ổn định từ phép reduce này.
```

Tính **giao hoán** (`a ⊕ b = b ⊕ a`) không phải điều kiện bắt buộc cho mọi reduction. Ví dụ nối chuỗi có tính kết hợp nhưng không giao hoán; trên nguồn có encounter order và một phép reduction phù hợp, thứ tự vẫn là phần của ngữ nghĩa kết quả. Tuy nhiên, không nên dựa vào thứ tự thực thi các lambda hay hiệu ứng phụ giữa các nhánh song song.

## 6. Khi nào dùng `Supplier` trong `collect`, khi nào dùng `BinaryOperator`?

`reduce` thiên về tạo **giá trị tích lũy** qua phép kết hợp. `collect` là *mutable reduction*: tích lũy vào container có thể thay đổi, thường phù hợp để xây danh sách, nhóm dữ liệu (`groupingBy`) hoặc tạo collector tùy chỉnh.

### `Stream.collect` ba tham số dùng `BiConsumer`, không dùng `BinaryOperator`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Binh", "Chi")
    .parallel()
    .collect(
        ArrayList::new,                     // Supplier<List<String>>
        (list, name) -> list.add(name),     // BiConsumer<List<String>, String>
        (left, right) -> left.addAll(right) // BiConsumer<List<String>, List<String>>
    );

System.out.println(names); // [An, Binh, Chi] với nguồn có thứ tự
```

Trong overload này, `supplier` tạo container; `accumulator` thêm một phần tử; `combiner` **chuyển phần tử giữa hai container**. Hai hàm cuối có hợp đồng `BiConsumer`: chúng thực hiện thay đổi và **không trả kết quả** cho `collect`. Biểu thức `list.add` và `left.addAll` tình cờ trả `boolean`, nhưng lambda được dùng trong ngữ cảnh `void` của `BiConsumer`, nên giá trị ấy bị bỏ qua.

### `Collector.of` có combiner là `BinaryOperator<A>`

Khác với overload trên, `Collector.of` yêu cầu combiner nhận hai container kiểu `A` và **trả về container gộp** kiểu `A`. Đây là chỗ `Supplier` và `BinaryOperator` cùng xuất hiện:

```java
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

Collector<String, StringJoiner, String> joinWords = Collector.of(
    () -> new StringJoiner(" | "),             // Supplier<StringJoiner>
    (joiner, word) -> joiner.add(word),          // BiConsumer<StringJoiner, String>
    (left, right) -> left.merge(right),          // BinaryOperator<StringJoiner>
    StringJoiner::toString                      // Function<StringJoiner, String>
);

String text = Stream.of("filter", "map", "reduce")
    .parallel()
    .collect(joinWords);

System.out.println(text); // filter | map | reduce
```

`Supplier<StringJoiner>` phải tạo bộ tích lũy mới. Trong combiner, `left.merge(right)` thay đổi `left` rồi trả lại chính `left`, đáp ứng chữ ký `BinaryOperator<StringJoiner>`. Bộ tích lũy từ các nhánh phải độc lập; không dùng một `StringJoiner` chia sẻ làm kết quả của mọi lần gọi supplier. Nếu chỉ cần nối chuỗi, API chuẩn `Collectors.joining(" | ")` ngắn gọn hơn; ví dụ `Collector.of` minh họa cách viết collector tùy chỉnh.

### `Collectors.toMap` dùng `BinaryOperator` để xử lý khóa trùng

Khi biến stream thành map, hai phần tử có thể tạo cùng khóa. Overload `Collectors.toMap(keyMapper, valueMapper, mergeFunction)` cần một hàm **kết hợp hai giá trị cùng kiểu** cho khóa trùng:

```java
import java.util.Comparator;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Character, String> longestByInitial = Stream.of("An", "Anh", "Binh")
    .collect(Collectors.toMap(
        word -> word.charAt(0),
        word -> word,
        BinaryOperator.maxBy(Comparator.comparingInt(String::length))
    ));

System.out.println(longestByInitial.get('A')); // Anh
System.out.println(longestByInitial.get('B')); // Binh
```

Nếu không truyền merge function và xuất hiện khóa trùng, `Collectors.toMap` trong overload hai tham số sẽ ném `IllegalStateException`. Trường hợp `groupingBy` lại có ngữ nghĩa **gom nhiều phần tử vào một nhóm**; chọn `groupingBy` khi cần lưu tất cả giá trị theo khóa, và `toMap` với merge function khi cần một giá trị tổng hợp cho mỗi khóa.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| Truyền `BiFunction` vào `Stream.map` | Không khớp chữ ký `Function<T, R>`. | Bọc trong `name -> biFunction.apply(name, context)` nếu có đối số thứ hai. |
| Cho rằng `Supplier` luôn sinh đối tượng mới | Dùng chung container giữa các nhánh `collect`, sinh lỗi khi song song. | Dùng factory như `ArrayList::new`; kiểm tra tính độc lập của kết quả `get()`. |
| Dùng phép trừ làm `BinaryOperator` cho `reduce` song song | Không thỏa tính kết hợp và/hoặc phần tử đơn vị. | Dùng phép kết hợp phù hợp, ví dụ `Integer::sum`. |
| Dùng `reduce` với identity là một `ArrayList` có thể thay đổi rồi `add` trực tiếp vào đó | Identity có thể được dùng ở nhiều nhánh; làm hỏng hợp đồng reduction, đặc biệt trong song song. | Dùng `collect` với supplier tạo container riêng. |
| Nghĩ `collect(supplier, accumulator, combiner)` cần combiner trả container | Nhầm với `Collector.of`; sai kiểu hoặc sai ý định. | Overload `Stream.collect` dùng `BiConsumer`; `Collector.of` dùng `BinaryOperator` làm combiner. |
| Nghĩ mọi lambda đều chắc chắn được gọi cho mọi phần tử | Short-circuiting, tối ưu hóa, song song làm số lần và thứ tự gọi khác kỳ vọng. | Không dùng hiệu ứng phụ làm cơ chế ghi nhận bắt buộc; dùng kết quả terminal operation. |

Các kiểu primitive chuyên dụng còn giúp hạn chế boxing: `IntSupplier` (cho `IntStream.generate`), `IntBinaryOperator` (cho `IntStream.reduce`), `LongBinaryOperator`, `DoubleBinaryOperator`. Chẳng hạn `IntStream.of(1, 2, 3).reduce(0, Integer::sum)` nhận phép toán phù hợp với `IntBinaryOperator`, không yêu cầu `BinaryOperator<Integer>`. Chỉ dùng wrapper `Integer` khi pipeline thực sự cần đối tượng hoặc generic API.

## 8. Quy trình chọn đúng hàm hành vi

Khi viết một pipeline Java Stream API, hãy đặt ba câu hỏi:

1. **Có cần dữ liệu đầu vào không?** Nếu chỉ cung cấp một giá trị, tạo đối tượng hoặc trì hoãn fallback, dùng `Supplier<T>`; với `Stream.generate`, nhớ giới hạn nguồn khi cần kết thúc.
2. **Cần ghép hai dữ liệu thành một kết quả có kiểu khác không?** Dùng `BiFunction<T, U, R>`; ví dụ accumulator của `reduce` ba tham số thường nhận kết quả tạm kiểu `U` và phần tử kiểu `T`.
3. **Có đang gộp hai kết quả cùng kiểu không?** Dùng `BinaryOperator<T>` cho `reduce`, combiner của `reduce` ba tham số, combiner của `Collector.of`, hoặc merge function của `toMap`. Đảm bảo các quy tắc kết hợp và identity nếu API có reduction song song.

Một phép toán có kiểu đúng **chưa đủ** để pipeline đúng: hàm hành vi phải hợp với hợp đồng của API đang gọi. Với luồng song song, cần đặc biệt chú ý tính kết hợp, trạng thái chia sẻ, encounter order và chi phí gộp kết quả. Với luồng gắn tài nguyên như `Files.lines`, cần đóng stream bằng `try-with-resources`; việc `Supplier`, `BiFunction` hay `BinaryOperator` trả kết quả không tự quản lý vòng đời tài nguyên.

**Tự kiểm tra:** Muốn tính tổng độ dài của các chuỗi, vì sao `reduce(0, (total, word) -> total + word.length(), Integer::sum)` cần cả `BiFunction<Integer, String, Integer>` và `BinaryOperator<Integer>`? Muốn thu thập từng chuỗi vào danh sách có thể thay đổi, vì sao `collect(ArrayList::new, ..., ...)` là lựa chọn thích hợp hơn `reduce` với một `ArrayList` làm identity? Trả lời được hai câu hỏi này là đã phân biệt được vai trò của ba functional interface trong phần lớn pipeline thông dụng.
