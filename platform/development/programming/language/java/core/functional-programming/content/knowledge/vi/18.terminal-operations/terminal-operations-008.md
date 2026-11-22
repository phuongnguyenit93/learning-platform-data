# Stream.toList(), collect() và reduce(): chọn thao tác kết thúc theo kiểu kết quả

## Mục tiêu bài học

Trong Java Stream API, **`toList()`, `collect()` và `reduce()` đều là terminal operation**: chúng kích hoạt quá trình xử lý pipeline để tạo ra một kết quả. Tuy nhiên, ba API không giống nhau:

- **`toList()`**: thu các phần tử của Stream thành một **`List<T>` không cho phép sửa**.
- **`collect()`**: **mutable reduction** hoặc sử dụng `Collector` để tạo ra loại kết quả mong muốn, như `List`, `Set`, `Map`, chuỗi đã nối, nhóm dữ liệu hoặc bản thống kê.
- **`reduce()`**: kết hợp nhiều phần tử thành một kết quả thông qua **phép gộp phù hợp với quy tắc kết hợp** (*associative reduction*), thường là tổng, tích, cực đại hoặc một giá trị tổng hợp bất biến.

Việc chọn đúng thao tác không chỉ quyết định câu lệnh ngắn hay dài. Nó quyết định **kiểu dữ liệu trả về, tính thay đổi được, cách xử lý Stream rỗng, tính đúng đắn khi chạy song song và chi phí lưu trữ**.

Sau bài học, bạn có thể đọc các chữ ký quan trọng, thiết kế một pipeline có kiểu kết quả rõ, áp dụng `Collectors` thông dụng, tránh lỗi `reduce` với accumulator mutable, và kiểm chứng chương trình Java 17 từ dữ liệu đầu vào đến stdout.

## 1. Terminal operation kết thúc một pipeline

Một pipeline Stream thường có ba phần:

```text
Nguồn dữ liệu
    → thao tác trung gian (map / filter / sorted / ...)
    → thao tác kết thúc (toList / collect / reduce / ...)
    → kết quả
```

Ví dụ:

```java
List<String> names = products.stream()
        .filter(p -> p.active())
        .map(p -> p.name())
        .toList();
```

Đây là **mã minh họa**, cần định nghĩa `products` và kiểu phần tử có phương thức `active()`, `name()` phù hợp. `filter` và `map` tạo phần mô tả pipeline; `toList` là thao tác kết thúc yêu cầu xử lý dữ liệu để tạo danh sách.

Sau khi dùng terminal operation, **không được tái sử dụng cùng Stream** như một nguồn mới:

```java
Stream<Integer> numbers = Stream.of(1, 2, 3);
List<Integer> list = numbers.toList();

// Không làm: numbers đã được tiêu thụ.
// long count = numbers.count();
```

Nếu nguồn là collection có thể duyệt lại, tạo Stream mới bằng `collection.stream()`. Nếu nguồn là I/O hoặc một Stream vô hạn, phải cân nhắc thiết kế riêng.

### Chọn đầu ra trước khi chọn phương thức

| Kết quả nghiệp vụ cần | Công cụ thường phù hợp |
| --- | --- |
| Một danh sách các phần tử và không cần thay đổi sau đó | `stream.toList()` |
| Danh sách có thể thêm/xóa phần tử sau khi thu | `collect(toCollection(ArrayList::new))` |
| Tập hợp không trùng phần tử | `collect(toSet())` hoặc `toCollection(...)` |
| Map theo khóa và giá trị | `collect(toMap(...))` |
| Map nhóm các phần tử theo tiêu chí | `collect(groupingBy(...))` |
| Một chuỗi nối từ nhiều chuỗi | `collect(joining(...))` hoặc cách reduce thích hợp |
| Tổng, tích, min, max, một giá trị gộp | `reduce(...)` hoặc primitive stream terminal như `sum()` |
| Nhiều thống kê theo số | `collect(summarizingInt(...))` hoặc `mapToInt(...).summaryStatistics()` |

Bảng là gợi ý lựa chọn, không phải yêu cầu phải dùng duy nhất một API. Một kết quả có thể được tạo bằng nhiều cách; ưu tiên **hợp đồng kiểu, ý nghĩa nghiệp vụ và tính đúng đắn**.

## 2. Stream.toList(): kết quả List không sửa được

### 2.1. Cú pháp và kiểu trả về

Từ Java 16, `Stream<T>` có terminal operation:

```java
List<T> toList()
```

Ví dụ:

```java
List<String> names = Stream.of("Lan", "An", "Mai")
        .toList();

System.out.println(names); // [Lan, An, Mai]
```

`toList()` thu các phần tử thành một `List<T>`, giữ **encounter order nếu Stream có encounter order**. Chẳng hạn nguồn `Stream.of("Lan","An","Mai")` có thứ tự, nên kết quả cũng theo thứ tự đó. Nếu nguồn unordered, đừng gán ý nghĩa nghiệp vụ cho một thứ tự không được bảo đảm.

**Điểm quan trọng:** danh sách từ `Stream.toList()` là **unmodifiable**. Thao tác như `add`, `remove`, `clear` hoặc `set` làm thay đổi danh sách sẽ ném `UnsupportedOperationException`:

```java
List<String> names = Stream.of("Lan", "An").toList();
names.add("Mai"); // UnsupportedOperationException
```

“Unmodifiable” nói về **cấu trúc của List**, không tự khiến các object phần tử trở thành bất biến. Nếu phần tử là một object mutable, code giữ tham chiếu tới object đó vẫn có thể thay đổi trạng thái bên trong object.

Java không yêu cầu `toList()` trả cụ thể `ArrayList`, cũng không hứa danh sách có serializable hay một identity ổn định thích hợp để đồng bộ. Không phụ thuộc tên lớp triển khai hoặc phép so sánh identity `==`.

### 2.2. Stream.toList() có chấp nhận null không?

`Stream.toList()` không áp đặt lệnh cấm phần tử null như `List.of(...)`. Ví dụ với Stream tham chiếu:

```java
List<String> values = Stream.of("A", null, "B").toList();
System.out.println(values); // [A, null, B]
```

Ví dụ trên hợp lệ trong Java 17. Tuy nhiên, **cho phép null không có nghĩa là nên đưa null vào kết quả nghiệp vụ**. Một pipeline chứa null có thể gây NPE ở `map(String::length)`, khi dereference hoặc khi truyền sang một API không cho phép null.

Nếu yêu cầu danh sách không chứa null, có thể lọc có chủ đích:

```java
List<String> safe = Stream.of("A", null, "B")
        .filter(Objects::nonNull)
        .toList(); // [A, B]
```

Đoạn này cần import `java.util.Objects`. Chỉ lọc nếu việc bỏ phần tử thiếu dữ liệu là chính sách hợp lệ; nếu null là lỗi dữ liệu, nên xác thực và báo lỗi thay vì âm thầm bỏ qua.

### 2.3. toList() không tự tạo snapshot sâu

Nếu nguồn là một `List<Person>` có object `Person` mutable, danh sách trả về có thể chứa **cùng các tham chiếu** đến object ấy. Bản thân List không cho `set` hay `add`, nhưng việc cập nhật `person.setName(...)` qua một tham chiếu đã có vẫn có thể thay đổi nội dung được quan sát khi đọc object. Nếu cần dữ liệu bất biến thật sự, hãy tạo value object bất biến hoặc sao chép có chủ đích.

### 2.4. Khi nào ưu tiên toList()?

Dùng `toList()` khi kết quả là danh sách để đọc, trả từ service, hiển thị UI hoặc truyền qua tầng khác mà không cần chỉnh sửa cấu trúc. Nó gọn, nêu rõ ý định và tránh kỳ vọng sai về tính mutable. Nếu caller có quyền sửa danh sách, hãy cung cấp loại collection có thể sửa theo hợp đồng thay vì để caller gặp exception bất ngờ.

## 3. collect(): tạo nhiều kiểu kết quả theo Collector

`collect()` có hai dạng chính trên `Stream<T>`. Dạng phổ biến dùng `Collector`:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

Trong đó:

- `T` là kiểu phần tử đầu vào.
- `A` là kiểu container **tích lũy trung gian** mà Collector dùng; không nhất thiết giống kết quả cuối.
- `R` là **kiểu kết quả** thu được.
- Một Collector mô tả cách tạo accumulator, thêm phần tử, kết hợp kết quả từng phần và tùy trường hợp biến container thành kết quả cuối.

`Collectors` trong `java.util.stream.Collectors` cung cấp nhiều factory tạo Collector chuẩn. Vì thế `collect` không nhất thiết chỉ cho danh sách.

### 3.1. Collectors.toList() và khác biệt với Stream.toList()

```java
List<String> names = Stream.of("A", "B")
        .collect(Collectors.toList());
```

Cần import `java.util.List`, `java.util.stream.Stream` và `java.util.stream.Collectors`. Kết quả có kiểu `List<String>`, nhưng **hợp đồng của `Collectors.toList()` không bảo đảm loại List cụ thể, tính mutable, serializable hay thread-safe**. Đừng giả định “`collect(toList())` chắc chắn là `ArrayList` có thể sửa” chỉ vì một JDK cụ thể đã trả như vậy.

So sánh:

| Cách viết | Hợp đồng danh sách |
| --- | --- |
| `stream.toList()` | `List<T>` **unmodifiable**, giữ encounter order nếu có |
| `stream.collect(Collectors.toList())` | `List<T>`, **không cam kết** khả năng sửa |
| `stream.collect(Collectors.toUnmodifiableList())` | `List<T>` unmodifiable, **không cho phần tử null** |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Đúng loại collection tạo ra, ví dụ `ArrayList<T>` có thể sửa |

Nếu chỉ đọc, `toList()` rất phù hợp. Nếu **bắt buộc mutable**, hãy yêu cầu rõ bằng `toCollection`:

```java
ArrayList<String> names = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));
names.add("C"); // hợp lệ
```

Ví dụ này cần import `java.util.ArrayList`. `toCollection` còn hữu ích nếu cần `LinkedHashSet` để loại trùng theo encounter order trong các tình huống cụ thể.

### 3.2. Collectors.toSet() và thứ tự phần tử

```java
Set<String> tags = Stream.of("java", "api", "java")
        .collect(Collectors.toSet()); // chứa "java" và "api"
```

`toSet()` loại trùng theo cách so sánh của Set; **không bảo đảm loại Set, tính mutable, hay thứ tự lặp**. Không nên in một Set mặc định rồi kiểm tra một thứ tự cụ thể trong bài test.

Nếu cần giữ encounter order của nguồn có thứ tự:

```java
LinkedHashSet<String> tags = Stream.of("java", "api", "java")
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

Với `LinkedHashSet`, kết quả lặp theo thứ tự phần tử xuất hiện lần đầu trong dữ liệu đã cung cấp. Đoạn này cần import `java.util.LinkedHashSet`.

### 3.3. Collectors.toMap(): kết quả Map

```java
Map<String, Integer> lengths = Stream.of("Java", "Go")
        .collect(Collectors.toMap(
                Function.identity(),
                String::length
        ));
```

Cần import `Map`, `Function`, `Collectors`, `Stream`. Kết quả có ánh xạ `"Java" -> 4` và `"Go" -> 2`. **Không dùng thứ tự in của Map mặc định làm hợp đồng**, vì `toMap` không hứa Map kết quả có kiểu triển khai và thứ tự nào.

Nếu nhiều phần tử tạo **cùng khóa**, overload `toMap(keyMapper, valueMapper)` thông thường ném `IllegalStateException` do trùng khóa, thay vì âm thầm giữ một giá trị. Phải xác định chính sách giải quyết:

```java
Map<String, Integer> latest = Stream.of("aa", "ab")
        .collect(Collectors.toMap(
                s -> s.substring(0, 1),
                String::length,
                (oldValue, newValue) -> newValue
        )); // khóa "a" có giá trị 2
```

Nếu thứ tự nguồn ảnh hưởng chính sách first/last, cần hiểu encounter order và xử lý song song; callback nên tuân theo yêu cầu liên quan đến phép kết hợp. Nếu mục tiêu là lưu **mọi** giá trị theo khóa, `groupingBy` thường thích hợp hơn chỉ giữ một giá trị.

Có thể yêu cầu Map có thứ tự chèn:

```java
Map<String, Integer> counts = Stream.of("A", "BB")
        .collect(Collectors.toMap(
                Function.identity(),
                String::length,
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));
```

Ví dụ cần import `java.util.LinkedHashMap`. Đối số cuối là `mapFactory`, quyết định loại Map kết quả. Điều này hữu ích cho đầu ra dễ kiểm chứng và báo cáo cần thứ tự đã chọn.

### 3.4. Collectors.groupingBy(): nhóm dữ liệu

`groupingBy(classifier)` dùng để nhóm phần tử theo một khóa:

```java
Map<String, List<String>> groups = Stream.of(
                "java", "javascript", "go")
        .collect(Collectors.groupingBy(s -> s.substring(0, 1)));
```

Kết quả có nhóm `"j"` gồm `"java"` và `"javascript"`, nhóm `"g"` gồm `"go"`. Không dựa vào thứ tự in của Map mặc định. Có thể truyền Collector downstream để không lưu nguyên object mà chỉ lưu thuộc tính:

```java
Map<String, List<String>> groupedNames = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                LinkedHashMap::new,
                Collectors.mapping(
                        Product::name,
                        Collectors.toList()
                )
        ));
```

Đây là đoạn minh họa, lớp `Product` được định nghĩa đầy đủ ở chương trình chính. `groupingBy` chia theo category, `mapping` lấy tên sản phẩm, `toList` downstream gom tên. Bằng `LinkedHashMap::new`, Map kết quả có thứ tự chèn theo key ở ví dụ tuần tự; **không mặc định danh sách downstream có khả năng sửa được**.

Một số Collector downstream thông dụng:

- `counting()`: đếm số phần tử theo nhóm, kết quả `Long`.
- `summingInt(...)` hoặc `summingLong(...)`: tính tổng thuộc tính số theo nhóm.
- `mapping(mapper, downstream)`: biến phần tử rồi chuyển cho Collector bên trong.
- `collectingAndThen(downstream, finisher)`: áp dụng bước hoàn thiện sau khi thu thập.

### 3.5. Collectors.joining(): một chuỗi kết quả

```java
String text = Stream.of("Java", "Stream", "API")
        .collect(Collectors.joining(" | "));

System.out.println(text); // Java | Stream | API
```

`joining` chỉ dùng cho Stream phần tử `CharSequence` (như `String`); với Stream object khác, dùng `map` trước để lấy biểu diễn chuỗi. Đây là một Collector tạo kết quả `String`, không phải List.

## 4. collect() dạng ba tham số: mutable reduction

Ngoài dạng nhận Collector, `Stream<T>` còn có:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner)
```

Mục đích là tạo một **container mutable**, rồi lần lượt đưa phần tử vào và kết hợp các container từng phần. Ví dụ:

```java
ArrayList<String> result = Stream.of("A", "B", "C")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(result); // [A, B, C]
```

Đây là code minh họa hợp lệ trong phương thức có import `ArrayList` và `Stream`. `supplier` tạo ArrayList rỗng; `accumulator` thêm phần tử; `combiner` ghép dữ liệu từ container thứ hai vào container thứ nhất khi cần. Với Stream song song, các container từng phần có thể được kết hợp theo quy tắc của Collector. **Không tự tạo một ArrayList chung cho tất cả luồng rồi bỏ qua đồng bộ**.

Dạng ba tham số phù hợp khi có cách tích lũy mutable tự nhiên. Khi đã có một Collector chuẩn, `collect(Collectors.toCollection(...))` hoặc `groupingBy(...)` thường dễ đọc và ít lỗi hơn.

## 5. reduce(): gộp phần tử thành kết quả duy nhất

`reduce` dùng để **gộp các phần tử thông qua phép toán phù hợp với associative reduction**. Với phép gộp số:

```java
int sum = Stream.of(1, 2, 3)
        .reduce(0, Integer::sum); // 6
```

Ở đây:

- `0` là **identity** của phép cộng: `0 + x = x`.
- `Integer::sum` là phép kết hợp cho ra tổng hai phần tử.
- Phép cộng theo miền số nguyên Java (với quy tắc tràn số của `int`) có tính kết hợp theo phép toán modulo ở cấp biểu diễn `int`, nhưng **không bảo đảm tổng toán học không tràn**. Nếu giá trị có thể lớn, chọn kiểu số/cơ chế kiểm tra tràn phù hợp.

Không nhầm `reduce` với `collect`: `reduce` thường xây một **giá trị kết quả** từ các giá trị cũ, còn `collect` thường **thay đổi container** tích lũy. Dùng `reduce` để `add` vào một `ArrayList` rồi trả cùng danh sách là anti-pattern, đặc biệt trong Stream song song.

### 5.1. reduce(identity, accumulator) trả T

Chữ ký:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

Ví dụ:

```java
int count = Stream.of(2, 3, 1)
        .reduce(0, Integer::sum); // 6
```

Với nguồn rỗng, kết quả là `identity` — ví dụ tổng của Stream rỗng với identity `0` là `0`. Cần lựa chọn identity **trung hòa** cho phép gộp:

- Tổng: `0`.
- Tích: `1`.
- Ghép chuỗi: `""` nếu phép gộp là nối chuỗi phù hợp.
- Không tự chọn một identity tùy tiện chỉ để tránh xử lý trường hợp rỗng.

Nếu identity sai, kết quả của parallel reduction có thể sai ngay cả khi đoạn tuần tự có vẻ đúng.

### 5.2. reduce(accumulator) trả Optional<T>

Chữ ký:

```java
Optional<T> reduce(BinaryOperator<T> accumulator)
```

Không có identity, vì vậy nếu Stream rỗng, kết quả là `Optional.empty()`:

```java
Optional<Integer> maximum = Stream.of(4, 8, 3)
        .reduce(Integer::max); // Optional[8]

boolean empty = Stream.<Integer>empty()
        .reduce(Integer::max)
        .isEmpty(); // true
```

Đây là lựa chọn tự nhiên khi **không có một identity có ý nghĩa** cho trường hợp không có phần tử. Ví dụ, “max của danh sách chưa có giá trị” khác với “max bằng 0”. Với phép tổng, có thể dùng identity `0` nếu hợp đồng thống kê mong muốn tổng rỗng là 0.

**Lưu ý với `null`:** `reduce(BinaryOperator<T>)` không phù hợp để dùng `null` như kết quả reduction có ý nghĩa; một kết quả `null` từ phép gộp có thể gây `NullPointerException`. Khi xử lý dữ liệu có null, làm rõ policy ngay từ nguồn hoặc dùng một cấu trúc biểu diễn vắng mặt phù hợp.

### 5.3. reduce(identity, accumulator, combiner) trả U

Chữ ký:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
```

Dạng này cho phép kiểu kết quả `U` **khác kiểu phần tử `T`**. Ví dụ với `Product`:

```java
long revenue = products.stream().reduce(
        0L,
        (total, p) -> total + p.units() * p.unitPriceCents(),
        Long::sum
);
```

Nếu `products` là `Stream<Product>`, `U = Long` và `T = Product`. Identity là `0L`; accumulator nhận tổng đã có và một Product rồi trả **tổng mới**; combiner gộp hai tổng từng phần. Mục tiêu là lấy một giá trị `long`, không xây List.

Trong trường hợp tổng số primitive, cách đơn giản hơn và thường hiệu quả hơn là:

```java
long revenue = products.stream()
        .mapToLong(p -> p.units() * p.unitPriceCents())
        .sum();
```

Đây là hai cách **riêng** để tính cùng dữ liệu. `mapToLong().sum()` thường ngắn, tránh wrapper trung gian của reduce generic và dễ diễn đạt mục đích; ví dụ `reduce` ba tham số giúp hiểu khi nào cần đổi kiểu kết quả.

## 6. Vì sao reduce cần tính kết hợp và identity đúng?

Để Stream có thể chia công việc giữa nhiều phần dữ liệu, `reduce` yêu cầu **accumulator kết hợp được** và identity trung hòa phù hợp.

Với các phần tử `a,b,c`, cách nhóm `(a ⊕ b) ⊕ c` và `a ⊕ (b ⊕ c)` phải cho kết quả tương đương, trong phạm vi phép toán được chọn. Phép cộng số nguyên, phép nhân số nguyên và nối chuỗi theo thứ tự đều có tính kết hợp theo ngữ nghĩa phù hợp; phép trừ không có tính chất đó:

```java
int result = Stream.of(10, 3, 2)
        .reduce(0, (a, b) -> a - b);
```

Đoạn trên có thể biên dịch, nhưng dùng phép trừ làm accumulator cho parallel reduction **không thỏa điều kiện kết hợp**, nên không nên coi kết quả của pipeline song song là giá trị nghiệp vụ đáng tin. Thay bằng phép gộp associative hoặc một thiết kế khác diễn đạt rõ cách tính.

### 6.1. Không dùng identity sai

```java
int total = Stream.of(1, 2, 3)
        .reduce(10, Integer::sum);
```

Đây là ví dụ **identity không trung hòa**. Khi chạy tuần tự, giá trị bằng `16`; nhưng `10` không phải identity của phép cộng, và khi phân chia/ghép song song nó có thể được áp dụng ở nhiều nhánh, tạo kết quả không tương đương. Đúng là `reduce(0, Integer::sum)` nếu muốn tính tổng.

### 6.2. Combiner phải tương thích accumulator

Với `reduce` ba tham số, `combiner` không phải một hàm tùy tiện. Nó phải kết hợp đúng hai kết quả trung gian và tương thích với cách `accumulator` đưa từng phần tử vào trạng thái tổng hợp.

Với bài toán doanh thu:

- Identity `0L` là trung hòa.
- Accumulator thêm giá trị tiền của một Product vào tổng.
- Combiner `Long::sum` ghép hai tổng.
  
Ba thành phần cùng diễn đạt phép cộng, nên phù hợp với xử lý song song của ví dụ. Nếu accumulator tính tổng nhưng combiner lại nhân hai tổng, kết quả sẽ sai khi pipeline được chia thành nhiều phần.

### 6.3. Tránh state mutable trong reduce

Cách sau là một anti-pattern:

```java
// Không dùng để xây List trong Stream song song:
List<String> wrong = names.stream().reduce(
        new ArrayList<String>(),
        (list, name) -> {
            list.add(name);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

Đây là **đoạn minh họa không nên sử dụng**, giả định `names` có sẵn và các import phù hợp. Nó đột biến accumulator thay vì tạo một kết quả mới. Với reduce, identity có thể được chia sẻ qua nhánh xử lý; sửa đổi object dùng làm identity vi phạm giả định cần thiết cho reduction an toàn và có thể gây kết quả sai hoặc tranh chấp dữ liệu.

Để tạo danh sách, dùng `toList()` hoặc `collect(toCollection(...))`; không cố thay Collector bằng reduce mutable.

## 7. Đặt ba cách cạnh nhau trên cùng dữ liệu

Giả sử dữ liệu sản phẩm:

```java
record Product(String name, String category, int units,
               long unitPriceCents) {}

List<Product> products = List.of(
        new Product("Book", "office", 2, 1250),
        new Product("Pen", "office", 3, 200),
        new Product("Tea", "food", 1, 700)
);
```

Đây là phần dữ liệu của chương trình đầy đủ bên dưới.

### 7.1. Cần danh sách tên không sửa được

```java
List<String> names = products.stream()
        .map(Product::name)
        .toList(); // [Book, Pen, Tea]
```

Dùng `toList()` vì chỉ cần danh sách đọc.

### 7.2. Cần danh sách để cập nhật tiếp

```java
ArrayList<String> editable = products.stream()
        .map(Product::name)
        .collect(Collectors.toCollection(ArrayList::new));

editable.add("Extra"); // hợp lệ
```

Dùng `toCollection(ArrayList::new)` để hợp đồng mutable rõ ràng.

### 7.3. Cần Map nhóm tên theo danh mục

```java
Map<String, List<String>> groups = products.stream().collect(
        Collectors.groupingBy(
                Product::category,
                LinkedHashMap::new,
                Collectors.mapping(Product::name, Collectors.toList())
        )
);
```

Kết quả theo thứ tự chèn của ví dụ là `{office=[Book, Pen], food=[Tea]}`. Dùng Collector vì cần **Map chứa List** chứ không phải một giá trị duy nhất.

### 7.4. Cần doanh thu tổng cộng

```java
long revenue = products.stream().reduce(
        0L,
        (sum, p) -> sum + p.units() * p.unitPriceCents(),
        Long::sum
); // 3800
```

Dùng `reduce` vì chỉ cần một giá trị số gộp. Cũng có thể dùng `mapToLong(...).sum()` để thể hiện mục tiêu rõ hơn, tránh boxing khi phù hợp.

## 8. Chương trình Java 17 hoàn chỉnh

Ví dụ dưới đây được thiết kế để kiểm chứng **ba loại đầu ra**, gồm List unmodifiable, ArrayList có thể sửa, Map có thứ tự, các phép reduce và trường hợp Stream rỗng/null.

Tạo tệp **`StreamTerminalResultsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamTerminalResultsDemo {
    record Product(String name, String category,
                   int units, long unitPriceCents) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Book", "office", 2, 1250),
                new Product("Pen", "office", 3, 200),
                new Product("Tea", "food", 1, 700)
        );

        List<String> names = products.stream()
                .map(Product::name).toList();
        System.out.println("toList: " + names);
        try {
            names.add("Extra");
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList mutable: false");
        }

        ArrayList<String> editable = products.stream()
                .map(Product::name)
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("Extra");
        System.out.println("Mutable: " + editable);

        Map<String, List<String>> grouped = products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Product::name, Collectors.toList())
                ));
        System.out.println("Grouped: " + grouped);

        Map<String, Integer> unitsByName = products.stream().collect(
                Collectors.toMap(
                        Product::name,
                        Product::units,
                        (oldValue, newValue) -> oldValue,
                        LinkedHashMap::new
                ));
        System.out.println("Map: " + unitsByName);

        int unitCount = products.stream()
                .map(Product::units)
                .reduce(0, Integer::sum);
        long revenue = products.stream().reduce(
                0L,
                (total, p) -> total + p.units() * p.unitPriceCents(),
                Long::sum);
        System.out.println("Units reduce: " + unitCount);
        System.out.println("Revenue reduce: " + revenue);
        System.out.println("Max price: " + products.stream()
                .map(Product::unitPriceCents)
                .reduce(Long::max).orElseThrow());

        System.out.println("Joined: " + products.stream()
                .map(Product::name)
                .collect(Collectors.joining(", ")));

        System.out.println("Parallel units: " + products.parallelStream()
                .map(Product::units)
                .reduce(0, Integer::sum));

        System.out.println("Empty reduce: "
                + Stream.<Integer>empty()
                        .reduce(Integer::sum).isEmpty());

        System.out.println("Null in toList: "
                + Stream.of("A", null, "B").toList());
    }
}
```

Biên dịch/chạy với JDK 17 hoặc mới hơn:

```bash
javac StreamTerminalResultsDemo.java
java StreamTerminalResultsDemo
```

**Stdout chính xác:**

```text
toList: [Book, Pen, Tea]
toList mutable: false
Mutable: [Book, Pen, Tea, Extra]
Grouped: {office=[Book, Pen], food=[Tea]}
Map: {Book=2, Pen=3, Tea=1}
Units reduce: 6
Revenue reduce: 3800
Max price: 1250
Joined: Book, Pen, Tea
Parallel units: 6
Empty reduce: true
Null in toList: [A, null, B]
```

### Phân tích kết quả

1. `products.stream().map(Product::name).toList()` trả `[Book, Pen, Tea]`. Phép thêm `"Extra"` ném `UnsupportedOperationException` và được bắt; bởi vậy in `toList mutable: false`.
2. `Collectors.toCollection(ArrayList::new)` tạo một `ArrayList` mới. Gọi `editable.add("Extra")` hợp lệ, nên danh sách có bốn chuỗi.
3. `groupingBy` chia theo `category`. `LinkedHashMap` giữ nhóm theo thứ tự xuất hiện đầu tiên: `office` trước `food`. Downstream `mapping` lấy tên sản phẩm và thu danh sách cho mỗi nhóm.
4. `toMap` tạo Map từ tên đến số lượng. Tên trong mẫu không trùng; merge function `(old,new) -> old` chỉ thể hiện chính sách dự phòng khi có khóa trùng. `LinkedHashMap` giúp đầu ra Map có thứ tự xác định.
5. Tổng số lượng là `2+3+1=6`. Doanh thu là `2*1250 + 3*200 + 1*700 = 3800` xu.
6. `reduce(Long::max)` trả một `Optional<Long>` có giá trị cực đại `1250`, sau đó `orElseThrow()` lấy giá trị đó.
7. `joining(", ")` tạo một chuỗi duy nhất `Book, Pen, Tea`.
8. `parallelStream().reduce(0,Integer::sum)` vẫn tính tổng `6` vì identity và phép kết hợp phù hợp cho bài toán này; **không suy ra mọi lambda reduce đều an toàn song song**.
9. `Stream.empty().reduce(Integer::sum)` không có identity nên cho Optional rỗng; `isEmpty()` là `true`.
10. `Stream.toList()` chấp nhận phần tử null như ví dụ và hiển thị `[A, null, B]`.

Mã ví dụ chỉ dùng API có trong Java 17, không cần mạng hay file đầu vào. Kết quả đã được biên dịch theo mức `--release 17` và chạy với các giá trị cố định.

## 9. Những khác biệt quan trọng về kiểu và trạng thái rỗng

| Tiêu chí | `toList()` | `collect(...)` | `reduce(...)` |
| --- | --- | --- | --- |
| Kiểu kết quả | `List<T>` | Phụ thuộc Collector, có thể `R` bất kỳ hợp lệ | `T`, `Optional<T>` hoặc `U` |
| Mục đích chính | Gom phần tử thành danh sách | Kết quả cấu trúc hoặc mutable reduction | Gộp thành một giá trị |
| Tính sửa được | List không sửa được | Phụ thuộc Collector và hợp đồng cụ thể | Thường dùng kết quả bất biến/giá trị |
| Với Stream rỗng | Danh sách rỗng | Phụ thuộc Collector: List rỗng, Map rỗng, counting=0... | Có identity → identity; không identity → Optional.empty |
| Dạng dùng phổ biến | `.toList()` | `.collect(groupingBy(...))` | `.reduce(0,Integer::sum)` |
| Cần bộ kết hợp khi song song | Do triển khai Stream lo | Collector/combiner theo hợp đồng | Hàm kết hợp và identity phải đúng |
| Dùng để xây danh sách mutable | Không | `toCollection(ArrayList::new)` | Không nên dùng reduce mutable |

Nếu yêu cầu nghiệp vụ cần phân biệt giữa “không có dữ liệu” và “kết quả tổng bằng 0”, `reduce(0,Integer::sum)` không tự biểu đạt sự vắng mặt. Dùng `reduce(Integer::sum)` để nhận Optional, hoặc tính thêm `count`/thống kê phù hợp.

Nếu không cần duy trì toàn bộ phần tử trong bộ nhớ, tính tổng bằng `reduce` hoặc primitive `sum()` có thể tiết kiệm bộ nhớ so với `toList()` rồi mới duyệt tính tổng. Nhưng nếu cần hiển thị và xử lý lại cùng dữ liệu, có thể chấp nhận lưu danh sách để tránh đọc lại nguồn I/O đắt đỏ.

## 10. Hiệu năng, lazy evaluation và tính kết hợp

### 10.1. Terminal operation kích hoạt việc duyệt

`map` và `filter` là intermediate operations. Chúng tạo pipeline, thường chỉ chạy body trên phần tử khi terminal operation cần dữ liệu:

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> {
            System.out.println("map " + n);
            return n * 2;
        });

// Lúc này thường chưa có "map ..." nào được in.
List<Integer> values = pipeline.toList();
```

Với nguồn hữu hạn có thứ tự và `toList()`, pipeline cần tạo các phần tử danh sách. Nhưng nói chung, **không đặt side effect quan trọng trong mapper**, bởi Stream có thể dùng short-circuit hoặc tối ưu hóa làm thay đổi số lần một số callback được thực thi. `toList`, `collect` và `reduce` không biến side effect bên ngoài thành một giao dịch.

### 10.2. reduce: hiệu năng và boxing

`Stream<Integer>.reduce(0,Integer::sum)` xử lý wrapper `Integer`. Nếu nguồn là giá trị số primitive hoặc chuyển được sang primitive, `IntStream.sum()` thường ngắn và có thể giảm boxing:

```java
int sum = products.stream()
        .mapToInt(Product::units)
        .sum();
```

Với `mapToLong`/`mapToDouble` có các phương thức `sum()` tương ứng. Tối ưu hiệu năng thực tế còn tùy JIT, nguồn dữ liệu, kích cỡ Stream và chi phí tính toán; đừng kết luận một phiên bản luôn nhanh hơn khi chưa đo.

### 10.3. Parallel reduction không đồng nghĩa “cộng nhanh hơn”

Để reduction song song đúng, accumulator cần associative, identity phải trung hòa; dạng ba tham số còn cần combiner tương thích. Phép ghép cấu trúc phức tạp có thể đòi hỏi đồng bộ hoặc cơ chế Collector riêng. Một Stream nhỏ thường không đáng chi phí điều phối thread.

Với `collect`, Collector chuẩn thường được thiết kế theo contract phù hợp; tuy nhiên, **giá trị object mutable bên trong Map/List kết quả** không tự nhiên thread-safe khi được dùng sau khi collect. Đừng suy luận rằng chạy `parallelStream()` làm mọi container hoặc object thu được an toàn với nhiều thread.

### 10.4. Infinite Stream và bộ nhớ

`Stream.generate(...)` có thể tạo nguồn vô hạn. Gọi `toList()` trên nguồn vô hạn không có điều kiện dừng sẽ không tạo được danh sách hữu hạn thông thường; có thể không bao giờ kết thúc hoặc hết bộ nhớ. Hãy dùng `limit`, nguồn hữu hạn hoặc thuật toán terminal phù hợp.

`reduce` cũng không thể “giải quyết” tất cả Stream vô hạn; phần lớn phép reduction cần xử lý toàn bộ dữ liệu để có kết quả. Chọn nguồn và điều kiện dừng đúng trước khi quan tâm tới loại terminal.

## 11. Quy tắc null, trùng khóa và lỗi callback

### 11.1. Phần tử null

- `Stream.toList()` có thể chứa null; không tự lọc bỏ phần tử.
- `Collectors.toUnmodifiableList()` **từ chối phần tử null**.
- `Collectors.toMap(...)` không phải nơi để phụ thuộc vào việc mapper trả null như một giá trị hợp lệ; hãy chuẩn hóa/chọn hợp đồng Map rõ ràng.
- `reduce` cần phép kết hợp phù hợp; nếu callback tạo kết quả null hoặc dereference một phần tử null, có thể gây lỗi.

Nếu dữ liệu có thể null, quyết định có lọc, thay thế, biểu diễn bằng Optional hay báo lỗi. Đừng chỉ chọn Collector nào “tình cờ” bỏ qua null.

### 11.2. Khóa trùng với toMap

`Collectors.toMap(keyMapper,valueMapper)` không tự giải quyết trùng khóa. Khi hai phần tử ánh xạ tới cùng một khóa, thường ném `IllegalStateException`, ngay cả khi hai giá trị bằng nhau.

Có thể chọn hàm merge rõ ràng:

```java
Map<String, Integer> totalByCategory = products.stream()
        .collect(Collectors.toMap(
                Product::category,
                Product::units,
                Integer::sum
        ));
```

Kết quả theo nội dung gồm `office -> 5` và `food -> 1`. Nếu cần lưu mọi Product theo category, `groupingBy` phù hợp hơn vì không làm mất từng item.

### 11.3. Checked exception trong callback

`Function`, `BinaryOperator`, `BiConsumer` và các functional interface chuẩn trong Stream không tự khai báo checked exception như `IOException` cho phương thức hàm. Lambda trong `map`, `reduce` hoặc Collector không thể để checked exception thoát ra mà không xử lý theo hợp đồng.

Ví dụ khi mapper đọc file, nên tách I/O khỏi phép biến đổi thuần hoặc có chính sách bắt/chuyển ngoại lệ minh bạch. Không dùng một `catch (Exception) { return null; }` tùy tiện để ép pipeline hoàn thành, vì điều đó làm sai kết quả và che mất lỗi hệ thống.

### 11.4. Không thay đổi chính nguồn đang duyệt

Với collection thông thường, vừa duyệt Stream từ collection vừa sửa collection đó bằng side effect của pipeline có thể phá giả định của nguồn, gây lỗi hoặc kết quả không xác định. Để tạo đầu ra mới, dùng `toList()` hoặc `collect` thay vì thay đổi cùng nguồn bên trong `map` hay `reduce`.

## 12. Các lỗi thường gặp và cách sửa

1. **Tưởng `toList()` trả ArrayList mutable:** nó trả List unmodifiable. Muốn sửa dùng `collect(toCollection(ArrayList::new))`.
2. **Tưởng `Collectors.toList()` cam kết mutable:** không có bảo đảm; đừng dựa vào một JDK tình cờ trả ArrayList.
3. **Tưởng `toUnmodifiableList()` và `toList()` đồng nhất về null:** `toUnmodifiableList()` không nhận null, còn `Stream.toList()` có thể chứa null.
4. **Dùng `toMap` mà không xử lý khóa trùng:** cần hàm merge hoặc `groupingBy`.
5. **Dùng `reduce` để xây List rồi gọi `add` trên identity:** sai mô hình mutable reduction; dùng `collect`.
6. **Chọn identity sai trong `reduce`:** ví dụ dùng `10` khi tính tổng với `Integer::sum` sẽ sai, nhất là khi parallel.
7. **Dùng phép gộp không associative trong reduce song song:** phép trừ hoặc các phép toán phụ thuộc thứ tự gộp có thể cho kết quả không đúng kỳ vọng.
8. **Combiner không đồng nhất với accumulator:** dạng reduce ba tham số sẽ sai khi phân chia/ghép nhánh.
9. **Quên Optional khi reduce không có identity:** `reduce(BinaryOperator)` trả Optional, rỗng nếu không có phần tử.
10. **Tái dùng cùng Stream:** sau terminal operation, tạo Stream khác từ nguồn có thể tạo lại.
11. **Dùng List để tính tổng không cần lưu phần tử:** có thể dùng `mapToLong().sum()`, `reduce` hoặc statistics để tránh lưu trung gian.
12. **Giả định output Set/Map theo thứ tự cố định:** chọn `LinkedHashSet`/`LinkedHashMap` khi thứ tự là một phần hợp đồng.
13. **Bỏ qua null ở mapper:** `String::length` trên null gây NPE; xác định chính sách thiếu dữ liệu trước khi xử lý.
14. **Nghĩ parallelStream bảo đảm nhanh hơn:** overhead có thể lớn, callback và quy tắc kết hợp phải đúng.
15. **Dùng terminal trên Stream vô hạn mà không giới hạn:** có thể không kết thúc hoặc hết tài nguyên.
16. **Lẫn kết quả thống kê với kết quả collection:** `Collectors.summarizingInt` tạo summary object; `toList` tạo danh sách phần tử, hai mục tiêu khác nhau.

## 13. Bài tập tự luyện

**Bài 1.** Với `Stream.of("a","bb","ccc")`, viết pipeline tạo `List<Integer>` độ dài chuỗi. Nên dùng `toList()` hay `collect()` nếu danh sách chỉ để đọc?

**Bài 2.** Tạo danh sách tên từ `List<Product>` bằng `collect(Collectors.toCollection(ArrayList::new))`, sau đó thêm `"New"`. Vì sao cùng thao tác không được phép với `Stream.toList()`?

**Bài 3.** Từ `Stream.of("java","api","java")`, tạo `Set<String>` không trùng phần tử. Nếu cần giữ thứ tự xuất hiện đầu tiên, dùng Collector nào?

**Bài 4.** Từ `List<Product>` với category và units, tính Map tổng units theo category. Nên dùng `toMap(..., Integer::sum)` hay `groupingBy(..., summingInt(...))`? Giải thích vì sao cả hai có thể phù hợp.

**Bài 5.** Từ danh sách sản phẩm, nhóm tên theo category thành `Map<String,List<String>>`. Vì sao `toList()` không tạo được cấu trúc này trực tiếp?

**Bài 6.** Dùng `reduce(0,Integer::sum)` để tính tổng `[1,2,3]`. Kết quả trên Stream rỗng là gì? Nếu không có identity, kiểu trả về là gì?

**Bài 7.** Nêu hai yêu cầu quan trọng của identity và accumulator khi dùng `parallelStream().reduce(...)`. Vì sao phép trừ thường không phù hợp?

**Bài 8.** Với `Stream.of("Book","Pen","Tea")`, tạo chuỗi `"Book, Pen, Tea"` dùng Collector. So sánh với reduce nối chuỗi.

**Bài 9.** Tại sao `Stream.of("A",null,"B").toList()` hợp lệ mà một pipeline `collect(Collectors.toUnmodifiableList())` trên nguồn tương tự sẽ thất bại?

**Bài 10.** Viết một `reduce` ba tham số tính doanh thu kiểu `long` từ `Stream<Product>` có `units` và `unitPriceCents`. Chọn identity, accumulator và combiner phù hợp.

**Bài 11.** Vì sao không nên dùng `reduce(new ArrayList<>(), (list,x) -> {list.add(x); return list;}, ...)` để thu các phần tử từ parallel stream?

**Bài 12.** Nếu muốn trả một báo cáo gồm count/min/max/sum/average cho `units`, nên xét `mapToInt(...).summaryStatistics()` hay gọi nhiều terminal operation trên cùng Stream?

### Gợi ý đáp án

1. `Stream.of("a","bb","ccc").map(String::length).toList()` trả `[1,2,3]`; dùng `toList()` nếu không cần sửa.
2. `toCollection(ArrayList::new)` trả ArrayList có thể sửa; `toList()` là unmodifiable.
3. `collect(toSet())` loại trùng nhưng không hứa thứ tự; `collect(toCollection(LinkedHashSet::new))` giữ thứ tự chèn.
4. `toMap(Product::category, Product::units, Integer::sum)` hoặc `groupingBy(Product::category, summingInt(Product::units))` đều diễn đạt tổng theo nhóm; chọn dạng dễ đọc và hợp đồng kiểu đúng.
5. `toList()` chỉ gom phần tử thành một List; `groupingBy` tạo Map và danh sách trong từng nhóm.
6. Có identity `0` → kết quả `0`; không identity → `Optional<Integer>` rỗng.
7. Identity phải trung hòa, accumulator associative; combiner dạng ba tham số phải tương thích. Phép trừ không associative.
8. `stream.collect(Collectors.joining(", "))` dễ đọc; giảm chuỗi bằng reduce có thể tạo nhiều object tạm và thường không rõ ý định bằng joining.
9. `Stream.toList()` cho phép phần tử null; `Collectors.toUnmodifiableList()` từ chối null.
10. `reduce(0L, (total,p) -> total + p.units()*p.unitPriceCents(), Long::sum)`, với phép nhân và miền giá trị long phù hợp.
11. Sửa đổi identity mutable trái với hợp đồng reduction, có thể dùng chung và tạo tranh chấp/nhân bản sai; dùng `collect`.
12. `summaryStatistics()` thu nhiều chỉ số bằng một terminal operation; Stream không được chạy terminal lần hai.

## 14. Tổng kết

Ba terminal operation cùng kích hoạt pipeline nhưng trả lời ba câu hỏi khác nhau:

- **`toList()`:** “Tôi cần toàn bộ các phần tử dưới dạng List để đọc.”
- **`collect()`:** “Tôi cần một cấu trúc/kết quả được tạo theo quy tắc cụ thể: List mutable, Set, Map, nhóm, chuỗi, thống kê…”
- **`reduce()`:** “Tôi cần gộp các phần tử thành **một giá trị** dựa trên identity và phép kết hợp đúng.”

Hãy quyết định **kiểu kết quả và tính sửa được**, sau đó xem xét **nguồn rỗng, null, trùng khóa, tính kết hợp khi song song và tài nguyên**. Cú pháp Stream ngắn chỉ thực sự tốt khi nó thể hiện chính xác hợp đồng xử lý dữ liệu của ứng dụng.
