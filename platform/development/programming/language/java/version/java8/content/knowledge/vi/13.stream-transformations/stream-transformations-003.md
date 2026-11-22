# flatMap và làm phẳng kết quả nhiều phần tử trong Java Stream

**`flatMap`** là phép biến đổi Stream dùng khi **mỗi phần tử đầu vào có thể tạo ra 0, 1 hoặc nhiều phần tử đầu ra**. Thay vì tạo một Stream chứa các Stream con, `flatMap` **nối nội dung của các Stream con thành một Stream phẳng** để tiếp tục lọc, biến đổi và thu thập.

Ví dụ đơn giản:

~~~java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("Lan", "An"),
        Collections.<String>emptyList(),
        Arrays.asList("Binh", "Lan"));

List<String> names = groups.stream()
        .flatMap(Collection::stream)
        .collect(Collectors.toList());
// names = ["Lan", "An", "Binh", "Lan"]
~~~

Đoạn này là **mã minh họa đặt trong một phương thức**, cần import `java.util.*` và `java.util.stream.*`. `groups` có ba nhóm nhưng nhóm thứ hai rỗng: `flatMap` trả về **bốn tên**, không tạo thêm một phần tử rỗng tương ứng với nhóm thứ hai. Danh sách đầu vào không bị thay đổi.

Đây là kiến thức nền của nhóm **Biến đổi Stream** trong Java 8 và vẫn được dùng trong Java hiện đại. Bài này giải thích bản chất one-to-many, so sánh `map` với `flatMap`, đi từ nested collections tới dữ liệu đơn hàng, số nguyên, `Optional`, hiệu năng, xử lý lỗi/`null`, độ trễ, thứ tự và resource ownership. Ví dụ chạy đầy đủ **dùng API có từ Java 8**, đã biên dịch với `javac --release 8` trên JDK 17 và chạy kiểm chứng với Java 17. Các lựa chọn mới như `Optional.stream` (Java 9) và `mapMulti` (Java 16) được đánh dấu phiên bản.

## 1. Hình dung rõ `map` và `flatMap`

Giả sử đầu vào gồm ba danh sách:

~~~text
groups
  ├── ["Lan", "An"]
  ├── []
  └── ["Binh", "Lan"]
~~~

Với `map`, mỗi nhóm được biến đổi thành **một phần tử đầu ra**, phần tử ấy có thể tiếp tục là danh sách hoặc Stream:

~~~text
Stream<List<String>>
    --map(group -> group)-->
Stream<List<String>>
    [
      ["Lan", "An"],
      [],
      ["Binh", "Lan"]
    ]
~~~

Với `flatMap`, mỗi nhóm được ánh xạ sang một **Stream con**, rồi nội dung các Stream con được trải phẳng:

~~~text
Stream<List<String>>
    --flatMap(List::stream)-->
Stream<String>
    ["Lan", "An", "Binh", "Lan"]
~~~

Không có một quy tắc “`flatMap` bỏ mọi dấu ngoặc ở mọi độ sâu”. Nó chỉ làm phẳng **một lớp** Stream theo mapper được cung cấp.

### Bảng so sánh nhanh

| Tiêu chí | `map` | `flatMap` |
| --- | --- | --- |
| Loại biến đổi thường gặp | Một đầu vào → **một đầu ra** | Một đầu vào → **0, 1 hoặc nhiều đầu ra** |
| Mapper trả về | Một giá trị `R` | Một `Stream<? extends R>` |
| Kiểu kết quả | `Stream<R>` | `Stream<R>` |
| Nếu mapper trả `List<String>` | `Stream<List<String>>` | **Không đúng trực tiếp**: cần chuyển List sang Stream |
| Nếu mapper trả `Stream<String>` | `Stream<Stream<String>>` | `Stream<String>` sau khi flatten |
| Trường hợp đầu vào không tạo giá trị | Mapper có thể trả một giá trị như `null` | Trả `Stream.empty()` để đóng góp **0 phần tử** |
| Tính laziness | Intermediate operation lazy | Intermediate operation lazy |
| Callback phải non-interfering/stateless? | Có | Có |
| Ví dụ | Lấy tên từ mỗi user | Lấy mọi role từ nhiều user |

Phân biệt bằng **kiểu dữ liệu** giúp tránh nhầm: khi source là `Stream<List<String>>` và mục tiêu là `Stream<String>`, `flatMap(List::stream)` nói rõ ý định “mở từng danh sách con rồi nối các phần tử”.

## 2. Chữ ký và cách suy luận kiểu của `Stream.flatMap`

Trong `java.util.stream.Stream<T>`, phương thức có dạng:

~~~java
<R> Stream<R> flatMap(
    Function<? super T, ? extends Stream<? extends R>> mapper)
~~~

Đây là **chữ ký API**, không phải một method cần tự triển khai. Ý nghĩa:

1. Source là `Stream<T>`.
2. Mỗi đối tượng `T` được đưa vào `mapper`.
3. Mapper trả về một `Stream` của một kiểu phần tử tương thích `R`.
4. `flatMap` lấy **từng phần tử** từ các Stream con và tạo `Stream<R>` kết quả.

Với:

~~~java
Stream<List<String>> source = groups.stream();
Stream<String> flattened = source.flatMap(List::stream);
~~~

compiler biết `T = List<String>`, và `List::stream` trả `Stream<String>`, nên kiểu đầu ra `R = String`. Suy luận xảy ra **lúc biên dịch**, không dựa vào class runtime của từng phần tử.

### Lambda tương đương method reference

~~~java
.flatMap(list -> list.stream())
~~~

và:

~~~java
.flatMap(List::stream)
~~~

đều có cùng ý nghĩa với source có kiểu phù hợp. `Collection::stream` cũng thường dùng cho `List`, `Set` hoặc những implementation của `Collection`.

**Không có “flatMap trực tiếp với List”** trong Java Stream:

~~~java
// SAI KIỂU: mapper trả List, không trả Stream.
// groups.stream().flatMap(group -> group);

// ĐÚNG:
groups.stream().flatMap(group -> group.stream());
~~~

`flatMap` đòi một **stream-bearing mapping function**; khi có `List`, dùng `list.stream()`. Điều này rất khác với việc truyền collection thẳng vào một overload không có thật.

## 3. Mỗi phần tử có thể tạo 0, 1 hoặc N phần tử

Đây là đặc tính thiết kế cốt lõi của `flatMap`.

### 0 phần tử: bỏ qua một trường hợp

~~~java
List<Integer> values = Arrays.asList(0, 1, 3);
List<String> expanded = values.stream()
    .flatMap(n -> IntStream.rangeClosed(1, n)
            .mapToObj(i -> "x" + i))
    .collect(Collectors.toList());
// expanded = ["x1", "x1", "x2", "x3"]
~~~

`n = 0` tạo `IntStream.rangeClosed(1,0)` rỗng, đóng góp 0 phần tử. `n = 1` tạo một `x1`. `n = 3` tạo ba phần tử `x1, x2, x3`. Vì thế source có **ba số** nhưng kết quả có **bốn chuỗi**.

### 1 phần tử: không cần tạo nhiều phần tử

~~~java
Stream<String> one = Stream.of("value");
Stream<String> unchanged = one.flatMap(Stream::of);
~~~

Với source Stream có phần tử kiểu `String`, `Stream::of` tạo Stream một phần tử cho mỗi String. Cách này **hợp lệ** nhưng thường **không cần thiết**. Nếu mỗi đầu vào luôn biến thành đúng một giá trị, `map` thể hiện ý định rõ và tránh lớp xử lý thêm.

### N phần tử: một nhóm có nhiều thành viên

~~~java
List<String> items = groups.stream()
    .flatMap(List::stream)
    .collect(Collectors.toList());
~~~

Nhóm `["Lan","An"]` đóng góp hai; nhóm rỗng không đóng góp gì; nhóm `["Binh","Lan"]` đóng góp hai. Không cần một vòng lặp lồng nhau hoặc một danh sách ngoài bị callback sửa.

### Không phải cứ trả nhiều phần tử mới dùng `flatMap`

Một mapper có thể trả **0 hoặc 1 phần tử** và vẫn dùng `flatMap` hợp lý khi mục tiêu là loại bỏ các giá trị vắng mặt:

~~~java
Stream<String> onlyPresent = inputs.stream()
    .flatMap(input -> input == null
        ? Stream.<String>empty()
        : Stream.of(input));
~~~

Ở đây `inputs` giả định là `Collection<String>` trong ngữ cảnh một phương thức. Code chuyển mỗi `null` thành 0 phần tử, mỗi String khác null thành 1 phần tử. Với Java 9+, có cách diễn đạt gọn hơn bằng `Stream.ofNullable`, nhưng trên **Java 8** việc dùng `Stream.empty()` là hợp lệ.

## 4. Làm phẳng List<List<T>> và các cấu trúc lồng nhau

Case điển hình:

~~~java
List<List<String>> matrix = Arrays.asList(
    Arrays.asList("a", "b"),
    Collections.<String>emptyList(),
    Arrays.asList("c"));

List<String> flat = matrix.stream()
    .flatMap(List::stream)
    .collect(Collectors.toList());
// flat = ["a", "b", "c"]
~~~

Đây là **đoạn minh họa**, cần imports Java Collections/Streams.

### So sánh kiểu kết quả thật

~~~java
List<Stream<String>> mapped = matrix.stream()
    .map(List::stream)
    .collect(Collectors.toList());

List<String> flattened = matrix.stream()
    .flatMap(List::stream)
    .collect(Collectors.toList());
~~~

`mapped` có các **Stream objects** trong List; mỗi Stream là nguồn single-use, dễ bị dùng sai nếu lưu lâu rồi cố consume lại. `flattened` là một List String đã materialize, thích hợp khi ứng dụng muốn làm việc trực tiếp với phần tử.

Lưu ý: trong ví dụ này, hai stream pipelines được **tạo độc lập từ `matrix.stream()`**. Không thể lấy **cùng một Stream instance** rồi gọi hai terminal operations: một stream chỉ được consume một lần.

### Làm phẳng hơn một cấp phải rõ ý định

Giả sử `List<List<List<String>>>`:

~~~java
List<List<List<String>>> nested = Arrays.asList(
    Arrays.asList(Arrays.asList("a", "b")),
    Arrays.asList(Collections.<String>emptyList(), Arrays.asList("c")));

List<String> flat = nested.stream()
    .flatMap(List::stream)
    .flatMap(List::stream)
    .collect(Collectors.toList());
// flat = ["a", "b", "c"]
~~~

`flatMap` đầu tiên chuyển `Stream<List<List<String>>>` thành `Stream<List<String>>`. `flatMap` thứ hai chuyển sang `Stream<String>`. Không nên nói `flatMap` “làm phẳng hoàn toàn mọi chiều sâu” nếu chỉ gọi một lần.

### Đọc dữ liệu lồng nhau có thể có nhóm `null`

~~~java
List<List<String>> groupsWithNull = Arrays.asList(
    Arrays.asList("a"), null, Arrays.asList("b"));

List<String> flattened = groupsWithNull.stream()
    .filter(Objects::nonNull)
    .flatMap(List::stream)
    .collect(Collectors.toList());
// ["a", "b"]
~~~

`List::stream` trên một nhóm `null` sẽ gây `NullPointerException`; giải pháp là xác định **hợp đồng dữ liệu** và lọc nhóm null trước khi dùng method reference.

Nếu null là dữ liệu lỗi, có thể hợp lý hơn **từ chối** với thông báo rõ thay vì âm thầm bỏ. Đừng để “flatMap xử lý null” trở thành thay thế cho validation.

## 5. Ví dụ nghiệp vụ: đơn hàng → nhiều dòng hàng

Đây là nơi `flatMap` phát huy rõ ràng: một đơn hàng có thể có **0 đến nhiều `Line`**. Ta muốn lấy **mọi dòng hàng của mọi đơn** để tính tổng, thống kê, lọc sản phẩm hoặc tạo report.

Mô hình:

~~~text
Order A
  ├─ book x2
  └─ pen x3
Order B
  └─ (không có dòng hàng)
Order C
  ├─ book x1
  └─ notebook x2
~~~

Một Stream của ba đơn hàng:

~~~java
Stream<Order> source = orders.stream();
~~~

Nếu gọi:

~~~java
Stream<List<Line>> nested = source.map(Order::lines);
~~~

kết quả là Stream gồm các **List<Line>`**, không phải Stream của `Line`. Để có các dòng hàng riêng lẻ:

~~~java
Stream<Line> flattened = orders.stream()
    .flatMap(order -> order.lines().stream());
~~~

Đây là các **fragment minh họa**; `Order`, `Line` và `orders` được định nghĩa đầy đủ ở phần 11. Lưu ý không reuse biến `source` sau khi một terminal operation đã consume nó.

### Vừa flatten vừa giữ thông tin đơn cha

Nếu chỉ flatten `Line`, kết quả `Line` có thể không mang mã đơn. Có thể xử lý khi mapper vẫn nhìn thấy `order`:

~~~java
List<String> labels = orders.stream()
    .flatMap(order -> order.lines().stream()
        .map(line -> order.id() + "/" + line.product()
                       + ":" + line.quantity()))
    .collect(Collectors.toList());
~~~

Kết quả với demo:

~~~text
[A/book:2, A/pen:3, C/book:1, C/notebook:2]
~~~

`order.id()` được capture bởi lambda bên trong. Điều đó hợp lệ khi dữ liệu đơn ổn định trong pipeline; không cần tạo mutable list bên ngoài.

Nếu kết quả cần dùng tiếp cho nghiệp vụ, thay vì ghép chuỗi `"A/book:2"`, hãy tạo **DTO/value object** chứa `orderId`, `productId` và `quantity`. Chuỗi có ích để in test, nhưng không phải định dạng domain model lý tưởng.

### Một số phép toán sau khi flatten

~~~java
List<String> productNames = orders.stream()
    .flatMap(order -> order.lines().stream())
    .map(Line::product)
    .distinct()
    .collect(Collectors.toList());
~~~

`distinct()` loại tên trùng theo `equals`. Với `List` nguồn có encounter order và Stream ordered, danh sách tên giữ thứ tự xuất hiện lần đầu: `book, pen, notebook`.

~~~java
Map<String, Long> occurrences = orders.stream()
    .flatMap(order -> order.lines().stream())
    .collect(Collectors.groupingBy(
        Line::product, Collectors.counting()));
~~~

Kết quả về mặt nội dung: `book` xuất hiện hai dòng hàng, `pen` một, `notebook` một. **Đếm dòng hàng khác tổng số lượng bán**: `Line("book",2)` vẫn chỉ là **một dòng**. Nếu muốn tổng quantity theo sản phẩm, thay downstream collector thành `Collectors.summingInt(Line::quantity)`.

### Vì sao không dùng `forEach` lồng nhau?

~~~java
List<Line> flattened = new ArrayList<>();
orders.forEach(order ->
    order.lines().forEach(flattened::add));
~~~

Cách trên có thể chạy tuần tự, nhưng tích lũy qua mutable list ngoài, buộc người đọc phải hiểu vòng lặp và side effect. `flatMap(...).collect(...)` diễn đạt phép biến đổi trực tiếp, dễ mở rộng khi muốn lọc và thống kê. Với `parallelStream`, dùng `ArrayList` bên ngoài các callback còn tạo race; `collect` phù hợp hơn.

## 6. `flatMapToInt`, `flatMapToLong` và `flatMapToDouble`

Ngoài `Stream.flatMap` tạo `Stream<R>`, Java cung cấp các biến thể tạo **primitive streams**:

| Method | Mapper trả về | Stream kết quả | Thường dùng |
| --- | --- | --- | --- |
| `flatMap(Function<T,Stream<R>>)` | `Stream<R>` | `Stream<R>` | Các object như Line, String, DTO |
| `flatMapToInt(Function<T,IntStream>)` | `IntStream` | `IntStream` | Số lượng, điểm, số nguyên |
| `flatMapToLong(Function<T,LongStream>)` | `LongStream` | `LongStream` | Số lượng lớn hoặc long |
| `flatMapToDouble(Function<T,DoubleStream>)` | `DoubleStream` | `DoubleStream` | Các số đo dạng double |

Chữ ký ở bảng được giản lược để dễ học; bản thực có generics wildcards phù hợp theo Javadoc.

Ví dụ tính tổng số lượng sản phẩm từ mọi đơn:

~~~java
int quantitySum = orders.stream()
    .flatMapToInt(order -> order.lines().stream()
            .mapToInt(Line::quantity))
    .sum();
// quantitySum = 8
~~~

`Order A` góp `2+3`, `Order B` góp `0` và `Order C` góp `1+2`; tổng bằng 8. `flatMapToInt` tránh boxing từng primitive int thành `Integer` như một pipeline `Stream<Integer>` không cần thiết.

### So với `flatMap(...).mapToInt(...)`

Cũng hợp lệ:

~~~java
int quantitySum = orders.stream()
    .flatMap(order -> order.lines().stream())
    .mapToInt(Line::quantity)
    .sum();
~~~

Hai dạng tính cùng kết quả. Dạng `flatMapToInt` nói rõ mapper tạo primitive stream ngay từ mỗi Order; dạng `flatMap` rồi `mapToInt` đôi khi dễ đọc hơn khi ta còn cần xử lý các `Line` như object trước khi biến thành số.

**Đừng mặc định `flatMapToInt` luôn nhanh hơn trong mọi workload**. Khác biệt phân bổ đối tượng, số lượng phần tử, fusion và JIT phụ thuộc pipeline cụ thể; chọn theo sự rõ ràng và benchmark khi tối ưu hóa có giá trị.

### Từ một primitive stream sang nhiều primitive values

`IntStream` tự có `flatMap(IntFunction<? extends IntStream>)`:

~~~java
int[] expanded = IntStream.of(1, 3)
    .flatMap(n -> IntStream.rangeClosed(1, n))
    .toArray();
// expanded = [1, 1, 2, 3]
~~~

Đây là một API **khác** với `Stream<T>.flatMapToInt`: receiver là `IntStream`, mapper sinh `IntStream`. Cần phân biệt theo **kiểu của Stream ở bên trái**.

## 7. `flatMap` để tách chuỗi thành các từ

Một tình huống phổ biến: mỗi dòng chứa nhiều từ.

~~~java
List<String> lines = Arrays.asList(
    "java stream",
    "",
    "flat map");

List<String> words = lines.stream()
    .filter(s -> !s.isEmpty())
    .flatMap(s -> Arrays.stream(s.split("\\s+")))
    .collect(Collectors.toList());
// ["java", "stream", "flat", "map"]
~~~

`String.split("\\s+")` trả một **mảng String[]**, nên phải dùng `Arrays.stream(...)` để tạo `Stream<String>` con. `filter` bỏ chuỗi rỗng trước để không tạo một token rỗng từ một dòng rỗng.

Dữ liệu thực cần chú ý:
- Dòng chỉ gồm whitespace không bằng `""`. Với Java 8 có thể `map(String::trim)` rồi `filter(s -> !s.isEmpty())` trước khi split.
- Regex `\\s+` có semantics theo Java regex; phạm vi Unicode whitespace cần được quyết định rõ nếu ứng dụng đa ngôn ngữ.
- Dòng có dấu câu, dấu gạch nối hoặc token chứa whitespace được quote không phải lúc nào cũng phân tách chính xác bằng `split("\\s+")`. Nếu đang parse định dạng có cấu trúc, dùng parser phù hợp.
- `String.split` tạo mảng tạm cho mỗi dòng; với file rất lớn, hãy đo hiệu năng và memory nếu thật sự là nút thắt.

Nếu muốn **đếm tần suất từ**:

~~~java
Map<String, Long> frequencies = lines.stream()
    .filter(s -> !s.isEmpty())
    .flatMap(s -> Arrays.stream(s.split("\\s+")))
    .collect(Collectors.groupingBy(
        Function.identity(), Collectors.counting()));
~~~

Cần import `java.util.function.Function`. `Function.identity()` lấy chính từ làm key. Mặc định `groupingBy` không cam kết loại Map/thứ tự key; nếu output cần ổn định, chỉ định map factory hoặc sort khi trình bày.

## 8. Tạo cặp kết hợp bằng `flatMap` lồng `map`

`flatMap` không chỉ mở collection con đã tồn tại; nó còn tạo quan hệ **one-to-many** bằng phép kết hợp.

~~~java
List<String> pairs = Arrays.asList("A", "B").stream()
    .flatMap(left -> Arrays.asList("1", "2").stream()
        .map(right -> left + right))
    .collect(Collectors.toList());
// ["A1", "A2", "B1", "B2"]
~~~

Với mỗi `left`, mapper tạo một Stream con từ danh sách `right`. Bên trong dùng `map` để tạo **một cặp String cho mỗi right**. Bên ngoài dùng `flatMap` để **nối tất cả cặp**.

Phân loại chức năng:
- **`map` bên trong:** `right -> left + right` là one-to-one.
- **`flatMap` bên ngoài:** một `left` cho ra hai `pairs`.

Nếu có `m` phần tử trái và `n` phần tử phải, kết quả có tới `m*n` phần tử. Một điểm nguy hiểm là **cartesian product phình dữ liệu rất nhanh**; đừng materialize hàng triệu/tỷ cặp vào List trừ khi đã thiết kế budget và giới hạn. Với nhu cầu filter một điều kiện, nên đặt predicate trong pipeline thích hợp hoặc dùng thuật toán join/index hiệu quả hơn.

### Giới hạn số lượng bằng `limit`

~~~java
List<String> firstThree = Arrays.asList("A", "B").stream()
    .flatMap(left -> Arrays.asList("1", "2").stream()
        .map(right -> left + right))
    .limit(3)
    .collect(Collectors.toList());
// ["A1", "A2", "B1"]
~~~

Với nguồn ordered và execution tuần tự, `limit(3)` chọn ba phần tử đầu trong encounter order. Nhưng **không** dựa vào callback chạy cho mọi cặp trước khi limit: `flatMap` là lazy và `limit` short-circuit, nên một số stream con/callback có thể chưa được tiêu thụ.

## 9. `flatMap` với `Optional`: giống ý tưởng nhưng khác API

`java.util.Optional<T>` cũng có `map` và `flatMap` từ Java 8. Ý tưởng “tránh lồng container” giống Stream, nhưng mapper của `Optional.flatMap` **trả Optional**, không phải Stream.

Giả sử:

~~~java
static Optional<String> lookupCode(String id) {
    if ("A".equals(id)) return Optional.of("customer-42");
    return Optional.empty();
}
~~~

Đây là method minh họa trong class; trong chương trình chạy hoàn chỉnh nó được định nghĩa y nguyên.

Khi dùng `map`:

~~~java
Optional<Optional<String>> nestedCode =
    Optional.of("A").map(FlatMapManyDemo::lookupCode);
// Optional[Optional[customer-42]]
~~~

Vì `lookupCode` đã trả `Optional<String>`, `Optional.map` bao nó lại thành một `Optional` bên ngoài.

Khi dùng `flatMap`:

~~~java
Optional<String> code =
    Optional.of("A").flatMap(FlatMapManyDemo::lookupCode);
// Optional[customer-42]
~~~

Nó **không tạo Optional lồng nhau**. Khi khóa `"Z"` không có dữ liệu:

~~~java
Optional<String> absent =
    Optional.of("Z").flatMap(FlatMapManyDemo::lookupCode);
// Optional.empty
~~~

**Khác biệt quan trọng về null:** `Optional.flatMap` ném `NullPointerException` nếu mapper trả về **`null`**. Mapper đúng phải trả `Optional.empty()` để biểu diễn không có kết quả. Trong khi đó, API **`Stream.flatMap`** có quy tắc riêng: nếu mapper của nó trả về **`null` như cả một Stream**, giá trị đó được coi tương đương một Stream rỗng (theo Javadoc). Không được dùng quy tắc của Stream để suy luận ngược cho Optional.

### Một lần làm phẳng trong Optional và một lần trong Stream

`Optional.flatMap` xử lý `Optional<Optional<T>>`, còn `Stream.flatMap` xử lý `Stream<Stream<T>>` hoặc `Stream<Collection<T>>` khi mapper mở collection thành stream. Đây là cùng một ý tưởng compositional nhưng **khác chữ ký và lifecycle**.

Nếu bạn có `List<Optional<String>>` và muốn lấy những giá trị thực:
- Java 9+: `optionals.stream().flatMap(Optional::stream)`.
- Java 8: dùng `optionals.stream().filter(Optional::isPresent).map(Optional::get)` khi đã lọc presence, hoặc dùng mapper tạo 0/1 Stream một cách tường minh. Đừng gọi `Optional::stream` trong code target Java 8, vì method này **được thêm từ Java 9**.

## 10. Null safety và cách thiết kế mapper

### 10.1. Null ở outer collection

~~~java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("ok"), null, Arrays.asList("done"));
List<String> names = groups.stream()
        .filter(Objects::nonNull)
        .flatMap(List::stream)
        .collect(Collectors.toList());
~~~

Lọc `Objects::nonNull` trước `flatMap` là cách loại bỏ **nhóm `null`** nếu đặc tả dữ liệu cho phép. Trong mô hình nghiệp vụ cần dữ liệu bắt buộc, nên validate và báo lỗi thay vì im lặng loại bỏ.

### 10.2. Null bên trong nhóm

~~~java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("a", null, "b"));

List<String> nonNullItems = groups.stream()
        .flatMap(List::stream)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
// ["a", "b"]
~~~

Lúc này nhóm không null, nhưng **phần tử bên trong** có thể null; cần filter **sau** flatten. Nếu method kế tiếp là `String::trim`, không lọc thì có thể ném `NullPointerException`.

### 10.3. Mapper trả null thay vì Stream

Theo contract `Stream.flatMap`, nếu mapper trả về `null` cho một phần tử, nó được xử lý như **Stream rỗng**. Tuy nhiên, cách này dễ khiến người đọc hiểu nhầm hoặc bỏ sót lỗi thiết kế:

~~~java
// HỢP LỆ theo Stream.flatMap, nhưng không nên dùng vì kém rõ:
Stream<String> result = source.flatMap(x -> condition(x) ? Stream.of(x) : null);
~~~

Đây là fragment minh họa, `source` và `condition` thuộc ứng dụng. Cách rõ hơn:

~~~java
Stream<String> result = source.flatMap(x ->
        condition(x) ? Stream.of(x) : Stream.<String>empty());
~~~

Hoặc nếu mục đích là **giữ hoặc loại bỏ đúng một phần tử**, `filter` diễn đạt trực tiếp hơn:

~~~java
Stream<String> result = source.filter(x -> condition(x));
~~~

Không mặc định biến mọi `filter` thành `flatMap`. Một API tốt diễn đạt rõ số lượng phần tử kỳ vọng: `filter` cho giữ/bỏ một phần tử hiện tại; `flatMap` cho sinh một tập phần tử mới.

### 10.4. Java 9+ có `Stream.ofNullable`

Từ Java 9:

~~~java
Stream<String> result = source.flatMap(Stream::ofNullable);
~~~

Với `Stream<String> source` có phần tử null, cách này chuyển mỗi null thành 0 phần tử, mỗi String khác null thành 1 phần tử. Nó không cần viết ternary với `Stream.empty()`. **Đừng gắn nhãn đây là API Java 8**; bản `FlatMapManyDemo` ở phần 11 không sử dụng nó.

## 11. Chương trình đầy đủ: nested lists, đơn hàng, nguyên thủy và Optional

Chương trình dưới đây chỉ dùng Java 8 APIs và có các assertions để không chỉ in kết quả mà còn **báo lỗi nếu dữ liệu sai**. Biên dịch được với `javac --release 8` trên JDK 17; khi chạy trên JDK 17, stdout đã được kiểm chứng. Những snippet cố ý sai ở các phần khác **không nằm trong file runnable**.

Lưu thành **FlatMapManyDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class FlatMapManyDemo {
    static final class Line {
        private final String product;
        private final int quantity;
        Line(String product, int quantity) {
            this.product = product;
            this.quantity = quantity;
        }
        String product() { return product; }
        int quantity() { return quantity; }
    }

    static final class Order {
        private final String id;
        private final List<Line> lines;
        Order(String id, List<Line> lines) {
            this.id = id;
            this.lines = lines;
        }
        String id() { return id; }
        List<Line> lines() { return lines; }
    }

    static Optional<String> lookupCode(String id) {
        if ("A".equals(id)) return Optional.of("customer-42");
        return Optional.empty();
    }

    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        List<List<String>> groups = Arrays.asList(
                Arrays.asList("Lan", "An"),
                Collections.<String>emptyList(),
                Arrays.asList("Binh", "Lan"));

        List<List<String>> nested = groups.stream()
                .map(group -> group)
                .collect(Collectors.toList());
        List<String> flattened = groups.stream()
                .flatMap(Collection::stream)
                .collect(Collectors.toList());
        List<String> distinct = groups.stream()
                .flatMap(Collection::stream)
                .distinct()
                .collect(Collectors.toList());

        List<Order> orders = Arrays.asList(
                new Order("A", Arrays.asList(
                        new Line("book", 2), new Line("pen", 3))),
                new Order("B", Collections.<Line>emptyList()),
                new Order("C", Arrays.asList(
                        new Line("book", 1), new Line("notebook", 2))));

        List<String> items = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> order.id() + "/" + line.product()
                                + ":" + line.quantity()))
                .collect(Collectors.toList());
        int quantitySum = orders.stream()
                .flatMapToInt(order -> order.lines().stream()
                        .mapToInt(Line::quantity))
                .sum();
        List<String> parallelItems = orders.parallelStream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> order.id() + "/" + line.product()))
                .collect(Collectors.toList());

        List<String> words = Arrays.asList("java stream", "", "flat map")
                .stream()
                .filter(s -> !s.isEmpty())
                .flatMap(s -> Arrays.stream(s.split("\\s+")))
                .collect(Collectors.toList());

        List<String> pairs = Arrays.asList("A", "B").stream()
                .flatMap(left -> Arrays.asList("1", "2").stream()
                        .map(right -> left + right))
                .collect(Collectors.toList());

        Optional<Optional<String>> nestedCode =
                Optional.of("A").map(FlatMapManyDemo::lookupCode);
        Optional<String> code =
                Optional.of("A").flatMap(FlatMapManyDemo::lookupCode);
        Optional<String> absent =
                Optional.of("Z").flatMap(FlatMapManyDemo::lookupCode);

        List<String> zeroOneMany = Arrays.asList(0, 1, 3).stream()
                .flatMap(n -> IntStream.rangeClosed(1, n)
                        .mapToObj(i -> "x" + i))
                .collect(Collectors.toList());

        check(flattened.equals(Arrays.asList("Lan", "An", "Binh", "Lan")),
                "flattened");
        check(items.size() == 4 && quantitySum == 8, "order items and sum");
        check(parallelItems.equals(Arrays.asList(
                "A/book", "A/pen", "C/book", "C/notebook")), "parallel order");
        check(code.equals(Optional.of("customer-42")), "optional code");
        check(!absent.isPresent(), "optional absent");
        check(zeroOneMany.equals(Arrays.asList("x1", "x1", "x2", "x3")),
                "zero one many");

        System.out.println("nested=" + nested);
        System.out.println("flat=" + flattened);
        System.out.println("distinct=" + distinct);
        System.out.println("items=" + items);
        System.out.println("quantitySum=" + quantitySum);
        System.out.println("parallelItems=" + parallelItems);
        System.out.println("words=" + words);
        System.out.println("pairs=" + pairs);
        System.out.println("optionalMap=" + nestedCode);
        System.out.println("optionalFlatMap=" + code);
        System.out.println("optionalAbsent=" + absent);
        System.out.println("zeroOneMany=" + zeroOneMany);
        System.out.println("checks=PASS");
    }
}
~~~

Lệnh build và chạy:

~~~bash
# Với JDK 17+ có hỗ trợ --release 8
javac --release 8 -encoding UTF-8 FlatMapManyDemo.java
java FlatMapManyDemo
~~~

Lệnh build chọn **Java 8 language/API baseline**, còn máy chạy là JDK 17 trong bài kiểm chứng. Một số phiên bản JDK mới có thể cảnh báo về việc target/source 8 đã cũ; **cảnh báo compiler option không làm sai semantics của Java 8 Stream API**, và JDK mục tiêu trong dự án thực phải được kiểm tra theo chính sách hỗ trợ tương ứng.

Stdout **đã kiểm chứng chính xác**:

~~~text
nested=[[Lan, An], [], [Binh, Lan]]
flat=[Lan, An, Binh, Lan]
distinct=[Lan, An, Binh]
items=[A/book:2, A/pen:3, C/book:1, C/notebook:2]
quantitySum=8
parallelItems=[A/book, A/pen, C/book, C/notebook]
words=[java, stream, flat, map]
pairs=[A1, A2, B1, B2]
optionalMap=Optional[Optional[customer-42]]
optionalFlatMap=Optional[customer-42]
optionalAbsent=Optional.empty
zeroOneMany=[x1, x1, x2, x3]
checks=PASS
~~~

### Cách đọc kết quả từ trên xuống

1. **`nested`**: `map(group -> group)` không làm phẳng; ba danh sách vẫn là ba phần tử. Nhóm rỗng vẫn có vị trí.
2. **`flat`**: `flatMap(Collection::stream)` lấy từng tên; số phần tử chuyển từ ba nhóm sang bốn tên.
3. **`distinct`**: sau flatten, `distinct` loại tên `Lan` lặp ở nhóm cuối; encounter order của source `List` được giữ trong kết quả.
4. **`items`**: Order A tạo hai phần tử, B tạo không phần tử, C tạo hai phần tử. Mỗi dòng vẫn có mã đơn do mapper bên trong capture biến `order`.
5. **`quantitySum=8`**: `flatMapToInt` nối các `IntStream` số lượng của từng đơn trước khi cộng, không cần một counter bên ngoài.
6. **`parallelItems`**: dù các callback có thể chạy trên nhiều thread, phép collect từ nguồn `List` ordered và pipeline ordered cho kết quả theo encounter order, không đồng nghĩa mapper chạy tuần tự.
7. **`words`**: một dòng có thể sinh nhiều từ; dòng rỗng bị bỏ trước khi split.
8. **`pairs`**: với hai vế trái và hai vế phải, kết quả là bốn cặp theo thứ tự nguồn trong demo.
9. **`optionalMap`**: `map` bọc kết quả đã là Optional thành Optional lồng.
10. **`optionalFlatMap`**: `flatMap` chỉ giữ một tầng Optional.
11. **`optionalAbsent`**: key không có dữ liệu tạo `Optional.empty`, không cần trả `null`.
12. **`zeroOneMany`**: nguồn 0/1/3 phát lần lượt 0/1/3 phần tử, làm rõ khả năng cardinality.
13. **`checks=PASS`**: các assertion trong main đều thành công; ví dụ này kiểm tra cả nội dung, số lượng và kết quả tổng trong những trường hợp quan trọng.

## 12. Thứ tự, laziness và parallel stream

### `flatMap` là intermediate operation lazy

~~~java
Stream<String> stream = groups.stream().flatMap(List::stream);
// Chưa có terminal operation thì pipeline chưa bị consume.
List<String> result = stream.collect(Collectors.toList());
~~~

Một Stream pipeline không tự động đọc tất cả phần tử khi vừa tạo. Với các thao tác downstream như `findFirst`, `limit`, `anyMatch`, chương trình có thể chỉ cần tiêu thụ một phần của các Stream con.

Ví dụ:

~~~java
Optional<String> first = groups.stream()
    .flatMap(List::stream)
    .filter(s -> s.startsWith("B"))
    .findFirst();
// Optional[Binh]
~~~

Tùy pipeline, source và optimization, các callback trung gian có thể không được gọi trên tất cả phần tử. **Không dùng mapper của `flatMap` như hook audit hay side effect phải chạy đúng một lần cho mọi phần tử**.

### Encounter order ≠ thứ tự chạy callback

Với nguồn `List` có encounter order và mapper tự tạo Stream con ordered từ List:

~~~java
List<String> result = groups.parallelStream()
    .flatMap(List::stream)
    .collect(Collectors.toList());
~~~

`Collectors.toList()` trên pipeline ordered trả các phần tử theo encounter order theo contract tương ứng. Tuy nhiên, các phép tạo/đọc Stream con có thể chạy khác thứ tự hoặc trên thread khác. Đừng dựa vào thứ tự các dòng log được in từ `map` hay `peek` trong pipeline parallel.

**Một chú ý về performance:** `flatMap` có thể tăng rất mạnh số phần tử; nếu mỗi đầu vào tạo 1.000 phần tử và source có 1 triệu phần tử, kết quả có thể lên tới 1 tỷ. `collect(toList())` trên dữ liệu ấy sẽ tốn bộ nhớ lớn, bất kể Stream có lazy. Thiết kế `limit`, aggregation, batching hoặc cấu trúc dữ liệu phù hợp trước khi materialize.

### Stateful/side-effectful mapper không phù hợp

Tránh:

~~~java
AtomicInteger seq = new AtomicInteger();
List<String> labeled = groups.parallelStream()
    .flatMap(group -> group.stream()
            .map(name -> seq.incrementAndGet() + ":" + name))
    .collect(Collectors.toList());
~~~

Đây là **anti-pattern minh họa**: việc cấp số dựa trên shared mutable counter có thể phụ thuộc lịch chạy parallel, không phản ánh index của nguồn. Dù `AtomicInteger` tránh mất phép tăng, nó không mang lại ý nghĩa ordering mong muốn. Nếu cần index của source, dùng index-based traversal với dữ liệu ổn định hoặc gắn index trước khi flatten.

## 13. Mapped streams được đóng thế nào?

Theo Javadoc của **`Stream.flatMap`**, mỗi Stream được mapper tạo ra sẽ được **đóng sau khi nội dung của nó đã được đặt vào Stream kết quả**. Điều này đặc biệt quan trọng khi Stream con giữ tài nguyên (file handles, network resources).

Ví dụ nâng cao:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> allLines = paths
        .filter(Files::isRegularFile)
        .flatMap(path -> {
            try {
                return Files.lines(path, StandardCharsets.UTF_8);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .collect(Collectors.toList());
}
~~~

Đây là **mã minh họa trong một phương thức** có biến `directory` (kiểu `Path`) và imports `java.io.*`, `java.nio.file.*`, `java.nio.charset.*`, `java.util.*`, `java.util.stream.*`.

- `Files.list(directory)` trả Stream<Path> **nắm resource thư mục**, vì vậy **outer stream phải nằm trong try-with-resources**.
- Mỗi `Files.lines(path, UTF_8)` trả Stream<String> từ file. `flatMap` có contract **đóng mapped stream** sau khi xử lý nội dung.
- `Files.lines` có thể ném checked `IOException` khi mở, nên lambda phải xử lý hoặc chuyển thành `UncheckedIOException`; lỗi đọc sau khi mở cũng có thể xuất hiện dưới dạng `UncheckedIOException`.
- `collect(toList())` vẫn lưu **mọi dòng** vào RAM; với nhiều file lớn, không phải lựa chọn tối ưu.
- `Files.list` có thể chứa symlink, special files hoặc danh mục ngoài phạm vi mong muốn; điều kiện `Files::isRegularFile` là một bước lọc cơ bản, không thay thế chính sách security/path traversal.
- Nếu có nhiều file và lỗi, cần quy định tính atomic/partial result rõ ràng, không bỏ lỗi rồi coi dữ liệu đầy đủ.

**Không suy ra** “flatMap đóng Stream con” nghĩa là mọi nguồn tài nguyên bên ngoài tự đóng. Stream **nguồn của toàn pipeline**, hoặc reader/socket được cấp từ bên ngoài, vẫn phải được quản lý theo ownership contract riêng.

### Hạn chế khi mapped stream không phải nguồn dữ liệu sạch

Mapped Stream có thể được tạo từ một resource của người khác đang sở hữu. Nếu việc đóng mapped Stream sẽ đóng tài nguyên ấy, cần xác định quyền sở hữu thật, tránh trả về Stream đóng reader/socket ngoài ý muốn. Với các nguồn như `List.stream()` thì không có external file handle để đóng, nên thường không có vấn đề tài nguyên.

Đừng tạo Stream con từ một Stream instance đã bị consume/đóng rồi đưa lại vào `flatMap`; Stream là **single-use**. Một mapper đúng cần tạo nguồn có thể tiêu thụ hợp lệ cho mỗi đầu vào.

## 14. `flatMap` có phải phép nối Stream trực tiếp không?

`Stream.concat(a, b)` cũng có thể nối hai Stream thành một Stream:

~~~java
Stream<String> left = Stream.of("a", "b");
Stream<String> right = Stream.of("c");
Stream<String> joined = Stream.concat(left, right);
~~~

Đây là cách nối **hai stream đã biết**, không cần tính nhiều Stream con từ từng phần tử đầu vào. Ngược lại:

~~~java
List<List<String>> groups = ...;
Stream<String> joined = groups.stream().flatMap(List::stream);
~~~

thích hợp khi có **một tập phần tử, mỗi phần tử sinh một Stream con**. `flatMap` là phép biến đổi dữ liệu theo mapper, không chỉ là một phép concat viết dài hơn.

Không nên lồng `Stream.concat` hàng chục nghìn lần trong một cấu trúc đệ quy để làm phẳng dữ liệu lớn; Javadoc lưu ý việc concat sâu có thể tạo call chain sâu và chi phí không mong muốn. Khi có collection các nguồn, `flatMap` thường tự nhiên hơn.

## 15. Java 9+ và Java 16+: những lựa chọn vẫn còn áp dụng

Bài tập trung Java 8, nhưng API mới hơn có thể viết gọn hơn và **không phải kiến thức lỗi thời**.

### 15.1. `Optional.stream()` — Java 9

~~~java
List<Optional<String>> optionals = Arrays.asList(
    Optional.of("a"), Optional.empty(), Optional.of("b"));

List<String> values = optionals.stream()
    .flatMap(Optional::stream)
    .collect(Collectors.toList());
// ["a", "b"]
~~~

`Optional.stream()` từ **Java 9** chuyển một Optional có giá trị thành Stream một phần tử, Optional rỗng thành Stream rỗng. Đây là pairing rất tự nhiên với `Stream.flatMap`. Nếu phải target Java 8, không dùng `Optional::stream`; code cùng mục đích có thể viết:

~~~java
List<String> values = optionals.stream()
    .filter(Optional::isPresent)
    .map(Optional::get)
    .collect(Collectors.toList());
~~~

`Optional.get()` trong đoạn Java 8 này được dùng **sau khi filter presence**; không gọi trực tiếp trên Optional có thể rỗng. Với code hiện đại, `Optional::stream` thường diễn đạt intent rõ hơn và tránh thao tác get.

### 15.2. `Stream.ofNullable()` — Java 9

~~~java
Stream<String> names = source.flatMap(Stream::ofNullable);
~~~

Nếu `source` có kiểu `Stream<String>` và có phần tử null, mỗi null tạo 0 phần tử và mỗi String khác null tạo 1 phần tử. Đây là phương pháp loại bỏ null bằng one-to-zero/one mapping, nhưng nếu chỉ cần lọc, `source.filter(Objects::nonNull)` cũng rất rõ ràng và chạy từ Java 8.

### 15.3. `Collectors.flatMapping()` — Java 9

`Collectors.flatMapping(mapper, downstream)` là **downstream collector**, không phải method intermediate trên Stream. Nó đặc biệt hữu ích khi **grouping** rồi muốn flatten dữ liệu **bên trong từng nhóm**.

Ví dụ khái niệm:

~~~java
Map<String, Set<String>> productsByCustomer = orders.stream()
    .collect(Collectors.groupingBy(
        Order::customerId,
        Collectors.flatMapping(
            order -> order.lines().stream().map(Line::product),
            Collectors.toSet())));
~~~

Đây là **minh họa cần một `Order` khác với runnable demo**: model nghiệp vụ ở đây phải có `customerId()`; không được gán đoạn này vào `FlatMapManyDemo.java` và mong compiler chấp nhận. Mục tiêu là chỉ ra collector **`flatMapping`** phục vụ aggregate theo nhóm. `Collectors.flatMapping` có từ Java 9; Java 8 có thể flatten trước hoặc xây collector thích hợp tùy bài toán.

### 15.4. `Stream.mapMulti()` — Java 16

Từ **Java 16**, `Stream.mapMulti` cho phép mapper phát **0 đến nhiều phần tử qua một Consumer** thay vì tạo một Stream con cho mỗi phần tử.

Ví dụ:

~~~java
List<String> names = groups.stream()
    .<String>mapMulti((group, downstream) ->
        group.forEach(downstream))
    .collect(Collectors.toList());
~~~

`mapMulti` cho cùng danh sách tên như `flatMap(Collection::stream)` trong ví dụ nhóm. Type witness `<String>` làm kiểu kết quả rõ hơn khi compiler không suy luận đủ từ lambda.

Một số trường hợp `mapMulti` hữu ích:
- Mỗi phần tử chỉ phát **rất ít đầu ra** (0/1/vài phần tử).
- Muốn tránh tạo nhiều Stream con ngắn hoặc cần điều khiển số giá trị phát vào `Consumer`.
- Có logic phát phần tử nhưng không có collection/stream con tự nhiên để gọi `stream()`.

**Không mặc định `mapMulti` luôn nhanh hơn** và cũng không dùng `mapMulti` trên code target Java 8/11. Với `List<List<T>>` đơn giản, `flatMap(List::stream)` vẫn rất dễ đọc, đúng hợp đồng và đủ tốt trong nhiều ứng dụng. Khi đầu vào thực sự là Stream<Resource> con cần lifecycle riêng, `flatMap` có semantics mapped-stream close, nên không thay `mapMulti` máy móc.

### 15.5. `Stream.toList()` — Java 16

Từ Java 16:

~~~java
List<String> names = groups.stream()
    .flatMap(List::stream)
    .toList();
~~~

`Stream.toList()` trả List **không sửa được**. `Collectors.toList()` từ Java 8 không cam kết chính xác loại List hay khả năng sửa của kết quả. Nếu cần list sửa được cụ thể, dùng:

~~~java
List<String> mutable = groups.stream()
    .flatMap(List::stream)
    .collect(Collectors.toCollection(ArrayList::new));
~~~

Chọn theo contract của ứng dụng, không chỉ theo độ ngắn câu lệnh.

## 16. Những lỗi phổ biến

| Sai lầm | Vì sao sai / dễ gây lỗi | Cách đúng |
| --- | --- | --- |
| Dùng `map(List::stream)` và mong nhận String | Tạo `Stream<Stream<String>>` | `flatMap(List::stream)` |
| Truyền List thẳng vào `flatMap(group -> group)` | Mapper phải trả Stream | `group -> group.stream()` |
| Không xét nhóm rỗng | Số phần tử kết quả không bằng số nhóm | Nghĩ theo cardinality **0/1/N** |
| Cho rằng `flatMap` flatten vô hạn cấp | Chỉ flatten một lớp theo mapper | Gọi thêm `flatMap` cho cấp tiếp theo |
| Gọi `List::stream` trên nhóm null | Gây `NullPointerException` | Validate, lọc null hoặc xử lý theo contract |
| Dùng `null` làm Stream con | `Stream.flatMap` xem như empty nhưng kém rõ | Trả `Stream.empty()` tường minh |
| Nghĩ `Optional.flatMap` cũng nhận mapper trả null | `Optional.flatMap` ném `NullPointerException` | Trả `Optional.empty()` |
| Gọi `Optional::stream` khi target Java 8 | API này có từ Java 9 | Java 8 dùng filter/map hoặc mapper tạo Stream |
| Dùng `Stream.ofNullable` trên Java 8 | API từ Java 9 | `filter(Objects::nonNull)` hoặc empty stream |
| Dùng `mapMulti` trên Java 8 | API từ Java 16 | `flatMap` |
| Đếm số dòng hàng thay tổng số lượng | Mỗi `Line` có thể có quantity lớn hơn 1 | `summingInt`/`flatMapToInt` |
| Bỏ thông tin cha rồi mới cần lại | `Line` không biết Order ID | Map trong mapper bên trong khi còn capture `order` |
| Dùng `flatMap` chỉ để thay `filter` | Làm code phức tạp cho trường hợp chỉ giữ/bỏ phần tử | `filter` |
| Tạo cartesian product rồi `collect(toList())` vô hạn | Dùng RAM khổng lồ | Giới hạn, aggregate, dùng join/index khác |
| Dùng external `ArrayList.add` trong parallel stream | Race/coupling | `collect` |
| Dùng `peek` để audit trong nested pipeline | Callback có thể không được thực thi như kỳ vọng | Tách audit/side effects rõ ràng |
| Nghĩ `parallel` làm kết quả không bao giờ giữ order | Encounter order khác execution order | Xem source/order và terminal operation |
| Nghĩ `collect(toList())` sẽ luôn cho ArrayList có thể sửa | Javadoc không cam kết | `toCollection(ArrayList::new)` |
| Nghĩ `Stream.toList()` có từ Java 8 | Có từ Java 16 | Java 8 dùng `collect(Collectors.toList())` |
| Dùng một Stream con đã consume nhiều lần | Stream là single-use | Tạo Stream mới cho mỗi lần tiêu thụ |
| Không quản lý resource stream gốc | Có thể rò rỉ Files.list/Files.lines | Try-with-resources cho nguồn có resource |
| Coi `flatMap` như parser CSV/JSON tự động | Chỉ nối element streams | Dùng parser đúng định dạng rồi flatten record |
| Dựa vào số lần mapper chạy để cập nhật external state | Optimization/short-circuit có thể thay số lần gọi | Mapper stateless; side effect ở nơi rõ contract |

## 17. Checklist khi chọn `flatMap` trong code review

1. **Mục tiêu cardinality là gì?** Một đầu vào có thể cho 0, 1 hay nhiều phần tử không?
2. **Kiểu source và kiểu kết quả là gì?** `Stream<List<T>>` có cần biến thành `Stream<T>` không?
3. **Mapper thật sự trả `Stream`?** Nếu trả Collection hay array, đã chuyển sang Stream đúng chưa?
4. **Có lớp lồng nào khác phải flatten tiếp không?** Chỉ gọi một lần sẽ giảm đúng một tầng theo mapper.
5. **Các nhóm/giá trị có thể null?** Xác định cách validate/filter thay vì tình cờ NPE.
6. **Có cần giữ metadata cha?** Nếu có, tạo DTO từ `order` và `line` khi mapper bên trong vẫn thấy cả hai.
7. **Có cần đếm số record hay tổng số lượng?** Phân biệt `count()` và `sum()/summingInt()`.
8. **Kết quả có thể lớn đến đâu?** Kiểm tra rủi ro fan-out/cartesian product và bộ nhớ khi collect.
9. **Có cần primitive specialization?** `flatMapToInt`/`ToLong`/`ToDouble` có phù hợp không?
10. **Có side effect trong mapper?** Cần bảo đảm non-interference/statelessness.
11. **Nguồn ordered và yêu cầu thứ tự?** Đừng lẫn encounter order với execution order.
12. **Pipeline có short-circuit?** Không dùng side effects như cam kết mọi phần tử đều được xử lý.
13. **Mapped Stream có giữ file/network resource?** Hiểu close semantics và ownership của outer stream.
14. **JDK target là bao nhiêu?** Java 8 có `flatMap`; Java 9 có `Optional.stream`/`ofNullable`; Java 16 có `mapMulti`/`Stream.toList`.
15. **Có thể dùng `filter` hoặc `map` rõ hơn?** Đừng dùng `flatMap` cho một tác vụ không thật sự one-to-many.
16. **Các assertions đã test nhóm rỗng, nhóm một phần tử và nhóm nhiều phần tử chưa?** Đây là các edge cases thiết yếu.
17. **Dữ liệu cạnh biên có thể bị thay đổi đồng thời?** Giữ nguồn ổn định, không sửa collection trong mapper.
18. **Kết quả cuối cần List/Set/Map hay chỉ một giá trị?** Chọn terminal operation theo contract thay vì collect tất cả vô điều kiện.

## 18. Bài tập thực hành

1. Với `List<List<Integer>>` gồm nhóm rỗng, nhóm một số và nhóm ba số, viết `flatMap(List::stream)` và assert đúng số phần tử.
2. Viết cả `map(List::stream)` và `flatMap(List::stream)` trên cùng dữ liệu, ghi rõ kiểu tĩnh của hai kết quả. Vì sao một cách tạo `Stream<Stream<T>>`?
3. Với ba đơn hàng, một đơn không có dòng, dùng `flatMap` lấy tất cả `Line` và tính tổng `quantity` bằng `mapToInt`.
4. Chỉ cần danh sách product ID không trùng: dùng `flatMap`, `map` và `distinct`. Kết quả trên nguồn List ordered có encounter order thế nào?
5. Giữ `orderId` khi flatten các line items bằng cách tạo một DTO có `orderId` và `lineId`.
6. Chuyển `List<String>` mỗi dòng có nhiều từ thành `Stream<String>` bằng `Arrays.stream(line.split(...))`. Xử lý dòng rỗng và whitespace.
7. Viết cartesian product từ `List<String> letters` và `List<Integer> numbers` bằng `flatMap` lồng `map`. Nếu hai list có 1.000 phần tử, kết quả lớn tới đâu?
8. Viết `Optional<String> findValue(String key)`; so sánh `Optional.map` và `Optional.flatMap` khi mapper đã trả Optional.
9. Giải thích vì sao `Optional.flatMap(x -> null)` không tương đương `Stream.flatMap(x -> null)`.
10. Tạo `List<List<String>>` chứa một nhóm null và một phần tử null bên trong nhóm khác; thiết kế hai bước kiểm tra null đúng vị trí.
11. Thay một pipeline `flatMap(...).mapToInt(...).sum()` bằng `flatMapToInt(...).sum()`. Cách nào có thể diễn đạt ý định rõ hơn?
12. Viết một pipeline có `limit(3)` sau `flatMap`; giải thích vì sao mapper không bắt buộc chạy với mọi source element.
13. Dùng `parallelStream` flatten một List có encounter order rồi collect vào List; phân biệt thứ tự kết quả và thứ tự callback.
14. Dùng Java 9+ thay code lọc `List<Optional<String>>` bằng `flatMap(Optional::stream)`. Vì sao không dùng cách này khi target Java 8?
15. Dùng Java 16+ thử `mapMulti` phát 0/n phần tử thay `flatMap`; đánh giá ưu điểm về readability trên dữ liệu mẫu.
16. Tạo một file text từ `Path` và dùng `flatMap(path -> Files.lines(path))` trong pipeline `Files.list` (có xử lý IOException). Ai phải đóng outer resource và ai đóng mapped streams?
17. Với `List<List<List<String>>>`, thực hiện hai `flatMap` liên tiếp và chứng minh kết quả không còn một lớp List nào trong Stream.
18. Đếm tần suất các từ trong nhiều câu bằng `flatMap` + `groupingBy` + `counting`. Nếu không cần mọi từ trong RAM, terminal reduction giúp gì?
19. Xây unit tests riêng cho trường hợp mapper trả **0, 1 và nhiều** phần tử. Vì sao test chỉ có nhóm chứa hai giá trị là chưa đầy đủ?
20. Giải thích vì sao `Collectors.toList()` không cam kết modifiability, còn `Stream.toList()` (Java 16+) có kết quả unmodifiable.

## 19. Tài liệu chính thức và hiện hành

- [Oracle Java SE 17 — `Stream.flatMap`, `flatMapToInt` và các overload](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — Stream API và mapped stream lifecycle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 17 — `Optional.map` và `Optional.flatMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 17 — `IntStream.flatMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html)
- [Oracle Java SE 17 — `Collectors`, `groupingBy` và `counting`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 17 — `Stream.mapMulti` (Java 16+)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer))
- [Oracle Java SE 17 — `Stream.ofNullable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#ofNullable(T))
- [Oracle Java SE 17 — `Optional.stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#stream())
- [Oracle Java SE 17 — Stream package: non-interference và statelessness](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)

**Kết luận:** `flatMap` dùng khi **mỗi phần tử có thể tạo 0, 1 hoặc nhiều phần tử**, và bạn muốn kết quả được **làm phẳng thành một Stream duy nhất**. Với nested collections, nó biến `Stream<List<T>>` thành `Stream<T>` khi mapper gọi `List::stream`; với đơn hàng, nó biến `Stream<Order>` thành `Stream<Line>`; với `Optional`, nó tránh Optional lồng nhau. Hãy ưu tiên mapper thuần/stateless, xử lý null đúng ngữ cảnh, hiểu close semantics của Stream con, kiểm soát số lượng đầu ra và chọn terminal operation hợp lý. Những quy tắc này vẫn là nền tảng vững chắc của Java Stream hiện nay.
