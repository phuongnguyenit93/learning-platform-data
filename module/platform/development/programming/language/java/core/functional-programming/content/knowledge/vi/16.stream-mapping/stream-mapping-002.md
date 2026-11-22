# `flatMap()` và làm phẳng dữ liệu lồng nhau trong Java Stream

## 1. Vấn đề: một phần tử có thể chứa nhiều phần tử con

Trong Java, `Stream.map` biến đổi **mỗi phần tử đầu vào thành một giá trị đầu ra**. Nhưng dữ liệu thực tế thường có cấu trúc lồng nhau: một đơn hàng chứa nhiều dòng hàng, một phòng ban chứa nhiều nhân viên, một lớp có nhiều học viên, hoặc một tệp chứa nhiều dòng và mỗi dòng chứa nhiều từ.

Giả sử một danh sách chứa ba danh sách con:

```text
[[1, 2], [], [3, 4]]
```

Khi cần xử lý từng số `1, 2, 3, 4` như những phần tử của **một** luồng, `flatMap` giúp **chuyển mỗi phần tử cha thành một stream con rồi nối nội dung các stream con thành một stream kết quả**.

```text
Stream<List<Integer>>
   [1, 2] ----> Stream(1, 2) ---+
   [] --------> Stream() -------+----> Stream<Integer>: 1, 2, 3, 4
   [3, 4] ----> Stream(3, 4) ---+
```

Điểm chính cần ghi nhớ:

- `map(f)`: **một đầu vào → một đầu ra**. Nếu `f` trả `List<T>` hoặc `Stream<T>`, kết quả vẫn chứa những danh sách/stream con.
- `flatMap(f)`: **một đầu vào → không, một hoặc nhiều đầu ra** (mỗi đầu vào được ánh xạ thành một stream con). `flatMap` nối các phần tử của những stream con thành một luồng phẳng.
- `flatMap` không tự “đệ quy làm phẳng mọi cấp độ”. **Mỗi lần gọi** chỉ làm phẳng một tầng stream được mapper trả về.

Ví dụ thực tế: cần lấy tất cả mã sản phẩm xuất hiện trong đơn hàng, không cần danh sách mã sản phẩm lồng theo từng đơn.

## 2. Chữ ký kiểu và cách suy luận

Chữ ký quan trọng của `Stream<T>` là:

```java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
```

Đọc từ trong ra ngoài:

1. Nguồn có kiểu `Stream<T>`.
2. Mapper nhận một `T` và trả một `Stream<? extends R>`.
3. `flatMap` lấy các phần tử `R` bên trong các stream con và trả một `Stream<R>` duy nhất.

Ví dụ:

```java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> groups =
        List.of(List.of(1, 2), List.of(), List.of(3, 4));

Stream<List<Integer>> outer = groups.stream();

// map: mỗi List<Integer> thành một Stream<Integer>
Stream<Stream<Integer>> nested =
        outer.map(List::stream);

// Tạo một nguồn stream mới vì "outer" đã tham gia pipeline trước.
Stream<Integer> flat =
        groups.stream().flatMap(List::stream);

System.out.println(flat.toList()); // [1, 2, 3, 4]
```

Trong ví dụ này `List::stream` là method reference tương đương `list -> list.stream()`. Với `map`, kiểu kết quả là `Stream<Stream<Integer>>`; với `flatMap`, kiểu kết quả trực tiếp là `Stream<Integer>`.

**Lưu ý về sử dụng stream một lần:** một `Stream` không phải danh sách có thể dùng đi dùng lại. Sau khi bắt đầu xây pipeline bằng một intermediate operation, không nên dùng lại stream gốc ở nhánh khác. Khi cần hai phép biến đổi độc lập, gọi `groups.stream()` hai lần như trên.

### Công thức trực quan

```text
map:
T --f--> R
Stream<T> --map(f)--> Stream<R>

flatMap:
T --f--> Stream<R>
Stream<T> --flatMap(f)--> Stream<R>
```

Không có luật “`flatMap` luôn mạnh hơn `map`”. Chọn `map` khi một phần tử thực sự ứng với **một kết quả**; chọn `flatMap` khi một phần tử ứng với **một luồng các kết quả** và mục tiêu là duyệt chúng như cùng một luồng.

## 3. Ví dụ cơ bản: làm phẳng danh sách hai chiều

```java
List<List<String>> teams = List.of(
        List.of("Lan", "Minh"),
        List.of(),
        List.of("An", "Hoa")
);

List<String> members = teams.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(members);
// [Lan, Minh, An, Hoa]
```

Giải thích:

- Danh sách con đầu tiên phát `Lan`, `Minh`.
- Danh sách thứ hai trống, nên **không phát phần tử nào**.
- Danh sách cuối phát `An`, `Hoa`.
- Kết quả là danh sách phẳng có bốn phần tử, không có danh sách con rỗng trong kết quả.

Bản tương đương dùng lambda:

```java
List<String> members = teams.stream()
        .flatMap(team -> team.stream())
        .toList();
```

`List::stream` gọn và rõ khi mapper chỉ gọi `stream()`. Lambda thích hợp khi phải lọc, biến đổi hoặc giữ thêm dữ liệu ngữ cảnh trong stream con.

### `map` sẽ cho cấu trúc nào?

```java
List<List<String>> copiedGroups = teams.stream()
        .map(team -> team.stream().toList())
        .toList();

System.out.println(copiedGroups);
// [[Lan, Minh], [], [An, Hoa]]
```

Đây là `List<List<String>>` vì mỗi team vẫn tạo **một danh sách**. Nếu yêu cầu là hiển thị thành viên theo đội, cấu trúc lồng này là đúng; nếu yêu cầu là thống kê mọi thành viên, `flatMap` thường thuận tiện hơn.

## 4. Ví dụ Java 17 hoàn chỉnh: đơn hàng chứa các dòng sản phẩm

Bài toán: có nhiều đơn hàng, mỗi đơn có danh sách dòng hàng. Cần:

1. Hiểu sự khác nhau giữa dữ liệu vẫn lồng và dữ liệu đã làm phẳng.
2. Lấy tất cả dòng hàng qua `flatMap`.
3. Giữ **mã đơn cha** khi tạo danh sách chi tiết phẳng.
4. Tạo danh sách SKU duy nhất và tính tổng số lượng.
5. Trải phẳng danh sách số, các `Optional` và các từ trong nhiều dòng văn bản.

Tạo tệp **`FlatMapDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.stream.Stream;

public class FlatMapDemo {
    record Line(String sku, int quantity) {}

    record Order(String id, List<Line> lines) {
        Order {
            // Chụp bản sao cấu trúc danh sách; Line là record bất biến.
            lines = List.copyOf(lines);
        }
    }

    record OrderLine(String orderId, String sku, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", List.of(
                        new Line("BOOK", 2),
                        new Line("PEN", 3)
                )),
                new Order("A02", List.of()),
                new Order("A03", List.of(
                        new Line("BOOK", 1),
                        new Line("BAG", 1)
                ))
        );

        // map giữ một danh sách con trên mỗi Order.
        List<List<Line>> nested = orders.stream()
                .map(Order::lines)
                .toList();
        List<Integer> groupSizes = nested.stream()
                .map(List::size)
                .toList();
        System.out.println("Nested group sizes: " + groupSizes);

        // flatMap biến mỗi Order thành một Stream<Line>,
        // sau đó gộp tất cả dòng hàng thành một luồng.
        List<String> flatLabels = orders.stream()
                .flatMap(order -> order.lines().stream())
                .map(line -> line.sku() + "x" + line.quantity())
                .toList();
        System.out.println("Flat lines: " + flatLabels);

        // Giữ ngữ cảnh của đơn cha trước khi làm phẳng.
        List<OrderLine> details = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> new OrderLine(
                                order.id(),
                                line.sku(),
                                line.quantity())))
                .toList();

        List<String> withOrderId = details.stream()
                .map(d -> d.orderId() + ":" + d.sku()
                        + "x" + d.quantity())
                .toList();
        System.out.println("With order ID: " + withOrderId);

        // Kết hợp flatMap, map, distinct, sorted.
        List<String> uniqueSkus = orders.stream()
                .flatMap(order -> order.lines().stream())
                .map(Line::sku)
                .distinct()
                .sorted()
                .toList();
        System.out.println("Unique SKUs: " + uniqueSkus);

        int totalQuantity = orders.stream()
                .flatMap(order -> order.lines().stream())
                .mapToInt(Line::quantity)
                .sum();
        System.out.println("Total quantity: " + totalQuantity);

        // Danh sách các danh sách, có một danh sách con rỗng.
        List<List<Integer>> groups =
                List.of(List.of(1, 2), List.of(), List.of(3));
        List<Integer> flattened = groups.stream()
                .flatMap(List::stream)
                .toList();
        System.out.println("Nested numbers: " + flattened);

        // Optional.stream tạo 0 hoặc 1 phần tử.
        List<Optional<String>> maybeCodes = List.of(
                Optional.of("A"),
                Optional.empty(),
                Optional.of("B")
        );
        List<String> presentCodes = maybeCodes.stream()
                .flatMap(Optional::stream)
                .toList();
        System.out.println("Present codes: " + presentCodes);

        // Mỗi đoạn văn bản có nhiều từ; tách rồi làm phẳng.
        List<String> words = Stream.of("java,stream", "lambda,flatmap")
                .flatMap(line -> Arrays.stream(line.split(",")))
                .map(String::trim)
                .toList();
        System.out.println("Words: " + words);

        // Nếu mapper trả null Stream, Stream.flatMap xem là rỗng.
        List<String> nullMapped = Stream.of("x", "y")
                .flatMap(value -> value.equals("x")
                        ? null
                        : Stream.of(value.toUpperCase(Locale.ROOT)))
                .toList();
        System.out.println("Null stream result: " + nullMapped);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FlatMapDemo.java
java FlatMapDemo
```

**Stdout chính xác:**

```text
Nested group sizes: [2, 0, 2]
Flat lines: [BOOKx2, PENx3, BOOKx1, BAGx1]
With order ID: [A01:BOOKx2, A01:PENx3, A03:BOOKx1, A03:BAGx1]
Unique SKUs: [BAG, BOOK, PEN]
Total quantity: 7
Nested numbers: [1, 2, 3]
Present codes: [A, B]
Words: [java, stream, lambda, flatmap]
Null stream result: [Y]
```

Giải thích chi tiết:

- `groupSizes` là `[2,0,2]`: đơn A01 có 2 dòng, A02 không có dòng nào, A03 có 2 dòng. `map` vẫn giữ đúng ba nhóm.
- `flatLabels` có bốn dòng do A02 tạo một **stream con rỗng**, không tạo phần tử nào trong luồng phẳng.
- `details` giữ mã đơn bằng cách ánh xạ từng `Line` sang `OrderLine` **bên trong** hàm `flatMap`, khi biến `order` còn trong phạm vi lambda. Vì vậy biết được mỗi dòng hàng xuất phát từ A01 hay A03.
- `uniqueSkus` gom tất cả SKU, loại trùng rồi sắp xếp theo thứ tự tự nhiên: `BAG, BOOK, PEN`.
- Tổng số lượng là `2 + 3 + 1 + 1 = 7`. Việc tổng hợp dùng `mapToInt(...).sum()`, không sửa một bộ đếm dùng chung.
- `Optional.empty().stream()` không phát phần tử; hai Optional chứa A và B phát mỗi cái một phần tử.
- `Arrays.stream(line.split(","))` biến mỗi chuỗi đầu vào thành stream nhiều từ; `flatMap` nối hai stream từ thành một.
- `Stream.flatMap` **coi kết quả mapper bằng `null` là một stream rỗng**. Mã này chỉ minh họa contract, không khuyến nghị cố ý trả null trong thực tế.

Tất cả nguồn `List.of(...)` và `Stream.of(...)` có encounter order xác định trong chương trình tuần tự, nên `toList()` giữ thứ tự phần tử như stdout. `Stream.toList()` tạo danh sách không hỗ trợ sửa qua `add`/`remove` (Java 16+). Đừng hiểu điều đó là nó tự biến **từng phần tử bên trong** thành object bất biến.

## 5. Phân biệt `map` và `flatMap` bằng kiểu kết quả

Xét mỗi đơn hàng có các dòng sản phẩm:

```java
Stream<Order> source = orders.stream();
```

Với phương thức `Order.lines()` trả `List<Line>`:

| Biểu thức | Kiểu kết quả | Kết quả khái niệm |
| --- | --- | --- |
| `orders.stream().map(Order::lines)` | `Stream<List<Line>>` | Luồng **các danh sách con** |
| `orders.stream().map(o -> o.lines().stream())` | `Stream<Stream<Line>>` | Luồng **các stream con** |
| `orders.stream().flatMap(o -> o.lines().stream())` | `Stream<Line>` | Một luồng **tất cả dòng hàng** |
| `orders.stream().flatMap(o -> o.lines().stream()).map(Line::sku)` | `Stream<String>` | Một luồng **tất cả SKU** |

`source` trong đoạn đầu chỉ minh họa kiểu; khi viết code thật, hãy bắt đầu pipeline mới từ `orders.stream()` cho mỗi phép biến đổi. Đừng cố dùng lại cùng đối tượng `Stream<Order>` đã gắn một pipeline.

### `flatMap` làm phẳng đến đâu?

Giả sử cấu trúc là:

```text
List<List<List<Integer>>>
[
  [[1, 2], [3]],
  [[4]]
]
```

Một lần `flatMap(List::stream)` biến `Stream<List<List<Integer>>>` thành `Stream<List<Integer>>`, **chưa** thành `Stream<Integer>`. Cần thêm một lần:

```java
List<List<List<Integer>>> threeLevels = List.of(
        List.of(List.of(1, 2), List.of(3)),
        List.of(List.of(4))
);

List<Integer> numbers = threeLevels.stream()
        .flatMap(List::stream)
        .flatMap(List::stream)
        .toList();

System.out.println(numbers); // [1, 2, 3, 4]
```

Đoạn này dùng `List` đã được import. Mỗi `flatMap` tương ứng **một cấp lồng nhau**. Không nên suy đoán rằng API duyệt đệ quy bất kỳ object phức tạp nào.

## 6. Chuyển một phần tử thành 0, 1 hoặc nhiều phần tử

Bản chất mạnh nhất của `flatMap` là mỗi phần tử đầu vào có thể sinh một số lượng kết quả **không cố định**:

```java
List<String> tokens = Stream.of("a,b", "", "c")
        .flatMap(text -> text.isEmpty()
                ? Stream.empty()
                : Arrays.stream(text.split(",")))
        .toList();

System.out.println(tokens); // [a, b, c]
```

- `"a,b"` tạo hai kết quả `a` và `b`.
- `""` tạo `Stream.empty()`, tức không tạo kết quả nào.
- `"c"` tạo một kết quả `c`.

Trong những bài toán trước đây cần nhiều vòng `for` lồng nhau và một `ArrayList` mutable để thêm phần tử, `flatMap` cho phép diễn đạt “lấy từng nhóm rồi trải phẳng” ngay trong pipeline.

### Tránh nhầm với `filter`

Nếu mỗi đầu vào chỉ cần quyết định **giữ hay bỏ chính nó**, `filter` rõ nghĩa hơn:

```java
List<Integer> positives = Stream.of(-2, 0, 3, 4)
        .filter(n -> n > 0)
        .toList();
// [3, 4]
```

Có thể dùng `flatMap(n -> n > 0 ? Stream.of(n) : Stream.empty())` nhưng thường dài hơn và khó đọc hơn. Chọn `flatMap` khi **thực sự có một luồng con cần nối** hoặc khi kết quả mapper là một số lượng phần tử biến thiên.

## 7. Giữ thông tin của phần tử cha khi làm phẳng

Một lỗi thiết kế thường gặp là sau khi làm phẳng các `Line`, người viết **không còn biết** dòng đó thuộc đơn hàng nào. Nếu yêu cầu nghiệp vụ cần mã đơn, không nên chỉ tạo `Stream<Line>` rồi cố tìm ngược thông tin cha.

Cách giải quyết là ánh xạ con sang một record mang ngữ cảnh **bên trong lambda của cha**:

```java
record OrderLine(String orderId, String sku, int quantity) {}

List<OrderLine> linesWithOrder = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> new OrderLine(
                        order.id(),
                        line.sku(),
                        line.quantity())))
        .toList();
```

Đây là đoạn minh họa đặt trong lớp có `Order`, `Line` và `orders` như ở ví dụ đầy đủ. Luồng biến đổi là:

```text
Order A01
  ├─ Line BOOK x2 ──> OrderLine(A01, BOOK, 2)
  └─ Line PEN  x3 ──> OrderLine(A01, PEN, 3)

Order A02 (không có Line) ──> không có kết quả

Order A03
  ├─ Line BOOK x1 ──> OrderLine(A03, BOOK, 1)
  └─ Line BAG  x1 ──> OrderLine(A03, BAG, 1)
```

Đây là một tình huống **kết hợp `flatMap` với `map`** rất hữu ích: `flatMap` đi vào từng nhóm, còn `map` chuyển mỗi phần tử con thành cấu trúc mới có đủ thông tin nghiệp vụ.

## 8. `Optional.stream()` và `Optional.flatMap()` là hai API khác nhau

### Làm phẳng nhiều Optional trong một Stream

Từ Java 9, `Optional<T>.stream()` trả:

- Một stream chứa **một phần tử** nếu Optional có giá trị.
- Một stream **rỗng** nếu Optional rỗng.

Vì vậy:

```java
List<Optional<Integer>> possible = List.of(
        Optional.of(10),
        Optional.empty(),
        Optional.of(20)
);

List<Integer> actual = possible.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(actual); // [10, 20]
```

Đây là cách rõ ràng để bỏ qua các Optional rỗng trong danh sách mà không phải gọi `get()`.

### `Optional.flatMap()` làm phẳng Optional lồng nhau

`Optional.flatMap` nhận một hàm trả về `Optional<U>`, không phải `Stream<U>`:

```java
record Account(String id, String email) {}

static Optional<String> safeEmail(Account account) {
    return Optional.ofNullable(account.email());
}

Optional<Account> account =
        Optional.of(new Account("A01", "a@example.com"));

Optional<String> email = account.flatMap(MyClass::safeEmail);
```

Đoạn này **minh họa chữ ký**, phải đặt trong một lớp có tên thích hợp và đổi `MyClass` thành tên lớp chứa `safeEmail`. Nếu viết `account.map(MyClass::safeEmail)`, kết quả có kiểu `Optional<Optional<String>>`, trong khi `flatMap` cho `Optional<String>`.

**Khác biệt cần nhớ:**

| API | Mapper trả | Kết quả |
| --- | --- | --- |
| `Stream<T>.flatMap(...)` | `Stream<R>` | `Stream<R>` |
| `Optional<T>.flatMap(...)` | `Optional<R>` | `Optional<R>` |
| `Stream<Optional<T>>.flatMap(Optional::stream)` | `Stream<T>` cho mỗi Optional | `Stream<T>` phẳng |

`Optional.flatMap` **không chấp nhận mapper trả tham chiếu `null`**: nếu mapper trả null thay vì một Optional thực, nó ném `NullPointerException`. Trong khi đó, `Stream.flatMap` có quy tắc khác cho **mapper trả `null` stream**, nêu ở phần kế tiếp. Đừng lẫn contract hai API chỉ vì cùng tên `flatMap`.

## 9. Xử lý danh sách rỗng, nguồn `null` và mapper trả `null`

### Danh sách con rỗng: cách dùng thông thường

```java
List<List<String>> groups = List.of(
        List.of("A"),
        List.of(),
        List.of("B")
);

System.out.println(groups.stream()
        .flatMap(List::stream)
        .toList()); // [A, B]
```

Danh sách con rỗng có một stream rỗng và không làm phát sinh exception.

### Một danh sách con bằng `null`: có thể ném NPE

`List.of(...)` không chấp nhận phần tử null, nhưng các collection mutable hoặc dữ liệu legacy có thể chứa null:

```java
List<List<String>> groups = new java.util.ArrayList<>();
groups.add(List.of("A"));
groups.add(null);

 // SAI ở runtime: khi gặp null, gọi null.stream() sẽ ném NPE.
 // groups.stream().flatMap(List::stream).toList();
```

Nếu null là dữ liệu được phép, nên chuẩn hóa ở ranh giới hoặc xử lý rõ:

```java
List<String> safe = groups.stream()
        .flatMap(group -> group == null
                ? Stream.<String>empty()
                : group.stream())
        .toList();

System.out.println(safe); // [A]
```

Đoạn này là minh họa theo danh sách `groups` ở trên. Nhưng không mặc định rằng mọi nhóm null là “nhóm rỗng”: nếu null thực sự biểu thị dữ liệu hỏng, nên báo lỗi/validate, không lặng lẽ loại bỏ.

### `Stream.flatMap` có contract riêng với mapper trả `null`

Theo API `Stream.flatMap`, nếu mapper trả `null` thay vì một stream, kết quả được xem là **stream rỗng**:

```java
List<String> result = Stream.of("a", "b")
        .flatMap(value -> value.equals("a")
                ? null
                : Stream.of(value))
        .toList();

System.out.println(result); // [b]
```

Đoạn này hợp lệ về contract nhưng **không nên cố ý trả null** chỉ để bỏ một phần tử. Viết `Stream.empty()` giúp chủ đích rõ ràng và tránh nhầm với `Optional.flatMap` (nơi mapper trả null sẽ ném NPE):

```java
.flatMap(value -> condition(value)
        ? Stream.of(value)
        : Stream.empty())
```

Dòng trên là **một phần của pipeline minh họa**, giả sử `condition(value)` đã tồn tại; không phải câu lệnh độc lập.

## 10. `flatMap` là phép biến đổi lười, nhưng stream con vẫn cần được đóng đúng

`flatMap` là **intermediate operation** của Stream. Nó mô tả phép biến đổi nhưng không nhất thiết tính toàn bộ kết quả ngay khi tạo pipeline. Khi terminal operation yêu cầu các phần tử, mapper được gọi để tạo từng stream con và các phần tử của chúng được chuyển tiếp.

```java
Stream<String> words = Stream.of("A B", "C")
        .flatMap(line -> Arrays.stream(line.split(" ")));

List<String> collected = words.toList(); // [A, B, C]
```

`Stream.flatMap` còn có hợp đồng quan trọng: **mỗi stream con được mapper tạo ra sẽ được đóng sau khi nội dung của nó đã được đưa vào luồng kết quả**. Điều này giúp quản lý vòng đời stream con; tuy nhiên việc **mở nguồn tài nguyên** như file hoặc connection trong mapper vẫn cần thiết kế rất cẩn thận.

Ví dụ ý tưởng khi mỗi nguồn là một tệp:

```java
// Minh họa ý tưởng, không phải chương trình độc lập.
// paths.stream().flatMap(path -> {
//     try {
//         return Files.lines(path); // Mở tài nguyên file.
//     } catch (IOException ex) {
//         throw new UncheckedIOException(ex);
//     }
// });
```

`Files.lines` có thể ném checked `IOException` tại thời điểm mở; stream đọc file có thể ném `UncheckedIOException` khi đang tiêu thụ. Không giả định chỉ vì `flatMap` tự đóng stream con sau xử lý bình thường mà toàn bộ pipeline trở thành không có rủi ro tài nguyên, nhất là khi caller không đóng nguồn hoặc gặp ngoại lệ/điểm dừng bất ngờ.

Trong hệ thống cần xử lý nhiều file, có thể dùng `try-with-resources` hoặc thiết kế ranh giới sở hữu nguồn rõ ràng, và xử lý mở/đóng lỗi theo contract. Nếu chỉ cần đọc từng tệp và gom kết quả, đôi khi vòng lặp ngoài kết hợp `try-with-resources` dễ kiểm toán hơn `flatMap` mở tài nguyên ẩn trong mapper.

### Short-circuit và side effect

`findFirst`, `limit`, `anyMatch` có thể không cần duyệt mọi phần tử hoặc mọi stream con. Không đặt side effect quan trọng vào mapper với giả định nó **luôn được gọi đúng một lần cho mọi phần tử cha**. Cách dùng dễ kiểm thử hơn là mapper chỉ sinh dữ liệu, còn cập nhật database/gửi email được thực hiện ở một ranh giới riêng.

## 11. Thứ tự và parallel stream

Với nguồn có encounter order (ví dụ `List`), `flatMap` sẽ bảo toàn thứ tự tương ứng: duyệt từng nhóm theo thứ tự nguồn và phần tử trong từng stream con theo thứ tự của stream đó khi kết quả được thu thập theo encounter order.

```java
List<String> result = List.of(
        List.of("A", "B"),
        List.of("C", "D")
).stream()
 .flatMap(List::stream)
 .toList();

System.out.println(result); // [A, B, C, D]
```

Nếu chuyển sang `parallel()`, `toList()` vẫn biểu diễn encounter order của stream có thứ tự. Nhưng **thời điểm và thứ tự thực thi** của các lambda/mapper giữa nhiều thread không phải là thứ tự tuyến tính có thể dùng để điều khiển side effect.

Không làm như sau với collection dùng chung:

```java
// Phản ví dụ nguy hiểm với parallel stream.
List<String> output = new java.util.ArrayList<>();
// groups.parallelStream()
//       .flatMap(List::stream)
//       .forEach(output::add);
```

`ArrayList` không bảo đảm an toàn khi nhiều thread cùng thêm phần tử. Dùng terminal collector phù hợp như `toList` hoặc `collect(...)` để Stream quản lý kết quả, thay vì tự mutate một accumulator chung trong `forEach`.

**Tính hiệu năng:** `flatMap` có thể tránh việc tự xây một danh sách con trung gian ở từng bước nếu mapper tạo stream trực tiếp. Nhưng nó không có nghĩa “luôn nhanh nhất”; chi phí stream con, phân bổ object, boxing, kích thước dữ liệu và đặc điểm song song đều quan trọng. Với yêu cầu hiệu năng, đo benchmark đúng bối cảnh.

## 12. `flatMapToInt`, `flatMapToLong`, `flatMapToDouble`

Nếu kết quả cuối là số nguyên thủy, Java có các overload chuyên biệt:

```java
int total = List.of(
        List.of(1, 2),
        List.of(3, 4)
).stream()
 .flatMapToInt(group -> group.stream()
         .mapToInt(Integer::intValue))
 .sum();

System.out.println(total); // 10
```

`flatMapToInt` nhận mapper trả `IntStream`, không trả `Stream<Integer>`. Dạng này hữu ích nếu cần tổng hợp `sum`, `average` hoặc tránh boxing/unboxing không cần thiết trong đường xử lý.

Trong ví dụ đơn hàng, cách sau cũng hợp lý:

```java
int totalQuantity = orders.stream()
        .flatMapToInt(order -> order.lines().stream()
                .mapToInt(Line::quantity))
        .sum();
```

Giả định `orders` và `Line` như ví dụ hoàn chỉnh, kết quả `7`. Hai lựa chọn `flatMap(...).mapToInt(...)` và `flatMapToInt(...)` có cùng mục tiêu nhưng khác kiểu stream con mà mapper trả. Chọn cách dễ đọc và có bằng chứng hiệu năng khi cần tối ưu.

## 13. Khi nào nên dùng `mapMulti` thay cho `flatMap`?

Từ Java 16, `Stream.mapMulti` cho phép mỗi đầu vào **đẩy 0 hoặc nhiều phần tử** trực tiếp tới một consumer, không nhất thiết phải dựng đối tượng stream con:

```java
List<Integer> flattened = Stream.of(
        List.of(1, 2),
        List.<Integer>of(),
        List.of(3)
).<Integer>mapMulti((group, downstream) ->
        group.forEach(downstream))
 .toList();

System.out.println(flattened); // [1, 2, 3]
```

`mapMulti` có thể hợp lý khi mỗi phần tử đầu vào thường sinh rất ít kết quả hoặc khi tránh tạo nhiều stream nhỏ là hữu ích. Tuy nhiên `flatMap` thường trực quan hơn đối với dữ liệu đã có sẵn dưới dạng `Collection`/`Stream` và người học mới.

`mapMulti` không phải một dạng khác của `Function<T,Stream<R>>`: callback của nó nhận phần tử và consumer để phát kết quả. Nếu không có yêu cầu hiệu năng/kiểu phức tạp, `flatMap(List::stream)` là cách dễ hiểu và dễ duy trì.

## 14. Lỗi phổ biến khi dùng `flatMap`

| Tình huống | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `map(List::stream)` rồi cố gọi `Line::sku` | Kiểu lúc đó là `Stream<Stream<Line>>`, không phải `Stream<Line>` | Dùng `flatMap(List::stream)` |
| Dùng `flatMap(line -> line.sku())` | Mapper trả `String`, không phải `Stream<R>` | Nếu một kết quả, dùng `map(Line::sku)` |
| Lấy dòng hàng nhưng mất mã đơn | Làm phẳng trước khi gắn context cha | Dùng `flatMap(order -> order.lines().stream().map(...))` |
| Một nhóm rỗng nhưng chờ một placeholder | `flatMap` phát 0 phần tử từ stream con rỗng | Nếu cần placeholder, tạo nó rõ ràng |
| Có danh sách con `null` | Gọi `null.stream()` ném NPE | Validate hoặc trả `Stream.empty()` nếu null hợp lệ |
| Mapper trả `null` Optional và nghĩ cũng như `Stream.flatMap` | API `Optional.flatMap` yêu cầu Optional không null | Trả `Optional.empty()` |
| Dùng `Optional.get()` để loại empty | `get()` ném khi empty | `flatMap(Optional::stream)` |
| Nghĩ `flatMap` làm phẳng mọi cấp | Mỗi call xử lý một cấp stream | Ghép nhiều `flatMap` theo kiểu dữ liệu |
| Tự thêm vào `ArrayList` từ parallel `forEach` | Race và thứ tự không bảo đảm | `toList` hoặc collector phù hợp |
| Mapper có side effect bắt buộc chạy cho mọi phần tử | Stream lazy/short-circuit | Tách side effect ra và thiết kế rõ số lần |
| Tạo stream con giữ tài nguyên mà không hiểu vòng đời | Có thể gây lỗi I/O/đóng tài nguyên khó kiểm soát | Xác định owner, đóng nguồn đúng contract |
| Dùng `flatMap` khi chỉ cần biến đổi 1→1 | Code không rõ ý định, thêm stream trung gian | Dùng `map` |

## 15. Bài tập thực hành

1. Với `List.of(List.of("A","B"), List.of(), List.of("C"))`, viết biểu thức trả `["A","B","C"]` bằng `flatMap(List::stream)`. Giải thích vì sao nhóm rỗng không xuất hiện.
2. Với `orders` trong `FlatMapDemo`, sử dụng `map(Order::lines)`, kiểm tra kiểu trả về và số phần tử **ở cấp ngoài**. Sau đó đổi sang `flatMap(o -> o.lines().stream())` và nêu số dòng hàng được phát.
3. Tạo danh sách `OrderLine(orderId, sku, quantity)` giữ ngữ cảnh mã đơn. Vì sao không nên chờ tới sau khi `flatMap` mới đi tìm lại Order?
4. Viết `flatMap` tách danh sách chuỗi `["a,b", "", "c,d"]` thành `["a","b","c","d"]`. Xử lý chuỗi rỗng bằng `Stream.empty()`.
5. Với `List<Optional<Integer>>` gồm `Optional.of(1)`, `Optional.empty()`, `Optional.of(3)`, dùng `flatMap(Optional::stream)` rồi `mapToInt(Integer::intValue).sum()`. **Kết quả:** 4.
6. Dự đoán `Stream.of("a","b").flatMap(s -> s.equals("a") ? null : Stream.of(s)).toList()`. Giải thích vì sao kết quả là `[b]` và lý do nên dùng `Stream.empty()` thay vì null trong code mới.
7. Tạo nguồn `List<List<List<Integer>>>`. Viết hai lần `flatMap(List::stream)` để ra `List<Integer>` và giải thích các kiểu trung gian.
8. Sửa chương trình cố gắng `group.stream()` khi `group == null`. Khi nào coi null là rỗng được phép, khi nào phải fail-fast?
9. Viết phiên bản `flatMapToInt` để tính tổng số lượng của tất cả dòng hàng trong đơn. So sánh với `flatMap(...).mapToInt(...)`.
10. Từ danh sách đoạn văn bản, viết pipeline tách từ, chuẩn hóa chữ thường bằng `Locale.ROOT`, lọc từ rỗng, `distinct` và `sorted`. Dự đoán kiểu ở mỗi bước.
11. Nêu một tình huống `flatMap` không thích hợp dù dữ liệu có danh sách con: ví dụ cần hiển thị các dòng hàng **theo từng đơn**. Nên giữ `List<List<Line>>` hoặc model nhóm như thế nào?
12. So sánh `flatMap` và `mapMulti` khi dữ liệu đầu vào rất lớn nhưng mỗi phần tử tạo một hoặc hai kết quả; đề xuất thử nghiệm benchmark thực tế trước khi chọn theo hiệu năng.

## 16. Checklist trước khi triển khai

- Mapper cần trả **một giá trị** hay **một stream các giá trị**?
- Kiểu đầu ra thật sự mong muốn là `Stream<R>` hay `Stream<Stream<R>>`?
- Có cần giữ **ngữ cảnh phần tử cha** trước khi làm phẳng không?
- Nhóm có thể **rỗng** hoặc tham chiếu **null** không, và quy tắc nghiệp vụ là gì?
- Có sử dụng `Optional` không: `Optional::stream` hay `Optional.flatMap` mới đúng mục tiêu?
- Stream con có tài nguyên I/O nào cần đóng và xử lý lỗi không?
- Pipeline có side effect hoặc hoạt động song song không; có cần tránh mutable shared state không?
- Có nhầm `filter` (giữ/bỏ) với `flatMap` (sinh 0..n phần tử), hoặc `map` (một đầu ra) không?
- Có kiểm tra **thứ tự kết quả**, bản ghi trùng, danh sách rỗng và số lượng sau khi trải phẳng không?

**Ghi nhớ:** `map` giữ cấu trúc một-phần-tử-sang-một-phần-tử; `flatMap` nhận một stream cho mỗi đầu vào rồi **nối các phần tử con thành một stream phẳng**. Đây là công cụ trung tâm để xử lý collection lồng nhau, đơn hàng nhiều dòng, tách từ và kết hợp `Optional.stream()`. Dùng đúng chữ ký, xử lý nhóm rỗng/null theo hợp đồng và giữ ngữ cảnh cha trước khi làm phẳng sẽ giúp pipeline rõ ràng, dễ kiểm thử và ít lỗi.
