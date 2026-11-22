# Đọc một pipeline Stream theo kiểu dữ liệu ở từng bước

Một pipeline trong Java Stream là chuỗi thao tác bắt đầu từ **nguồn dữ liệu**, đi qua **zero hoặc nhiều thao tác trung gian** (*intermediate operations*) và kết thúc bằng một **thao tác cuối** (*terminal operation*). Để hiểu đúng pipeline, đừng chỉ đọc tên phương thức; hãy hỏi ở từng bước: **kiểu đầu vào là gì, kiểu phần tử sau phép biến đổi là gì, và hiện tại còn đang giữ một Stream hay đã trả về kết quả?**

Ví dụ:

~~~java
List<String> names = orders.stream()
        .filter(order -> order.total() >= 100)
        .map(Order::customer)
        .distinct()
        .sorted()
        .toList();
~~~

Nếu `orders` là `List<Order>` và `Order.customer()` trả `String`, ta đọc theo sơ đồ:

~~~text
List<Order>
  .stream()                         → Stream<Order>
  .filter(Order -> boolean)          → Stream<Order>
  .map(Order -> String)              → Stream<String>
  .distinct()                        → Stream<String>
  .sorted()                          → Stream<String>
  .toList()                          → List<String>
~~~

Các dòng trên là **phân tích kiểu**, không phải các câu lệnh Java độc lập. Trong thực thi, `filter`, `map`, `distinct`, `sorted` là những thao tác trung gian tạo ra một pipeline để xử lý khi có terminal operation; chúng không có nghĩa mỗi bước đều phải tạo sẵn một danh sách mới.

## 1. Quy tắc đọc nhanh từ trái sang phải

Với mỗi mắt xích, ghi lại bốn thông tin:

1. **Receiver hiện tại:** đối tượng bên trái dấu chấm thuộc kiểu gì? Ví dụ `Stream<Order>`, `IntStream`, `Optional<Order>`, `List<Order>`.
2. **Kiểu đầu vào của lambda/method reference:** đối số của `filter` hoặc `map` thường là **một phần tử** thuộc kiểu hiện tại, không phải toàn bộ danh sách.
3. **Kiểu trả về của lambda:** `boolean`, `R`, `Stream<R>`, `int`... quyết định một số phép biến đổi.
4. **Kiểu kết quả của phương thức:** còn là một stream để nối tiếp, hay đã kết thúc thành `List`, `long`, `Optional`, `Map`...?

Có thể đánh dấu trực tiếp vào chữ ký API:

| Thao tác | Đầu vào điển hình | Kiểu kết quả | Thay đổi kiểu phần tử? |
| --- | --- | --- | --- |
| `Collection<T>.stream()` | Collection phần tử `T` | `Stream<T>` | Không |
| `Stream<T>.filter(Predicate<T>)` | `T -> boolean` | `Stream<T>` | Không |
| `Stream<T>.map(Function<T,R>)` | `T -> R` | `Stream<R>` | Có thể |
| `Stream<T>.flatMap(Function<T,Stream<R>>)` | `T -> Stream<R>` | `Stream<R>` | Có thể, đồng thời trải phẳng |
| `Stream<T>.mapToInt(ToIntFunction<T>)` | `T -> int` | `IntStream` | Chuyển sang primitive stream |
| `Stream<T>.distinct()` | Một `Stream<T>` | `Stream<T>` | Không |
| `Stream<T>.sorted()` | Một `Stream<T>` | `Stream<T>` | Không |
| `Stream<T>.sorted(Comparator<T>)` | Comparator so sánh `T` | `Stream<T>` | Không |
| `Stream<T>.limit(long)` | Một `Stream<T>` | `Stream<T>` | Không |
| `Stream<T>.toList()` | Một `Stream<T>` | `List<T>` | Kết thúc stream |
| `Stream<T>.count()` | Một `Stream<T>` | `long` | Kết thúc stream |
| `Stream<T>.findFirst()` | Một `Stream<T>` | `Optional<T>` | Kết thúc stream |

Ký hiệu `T` và `R` là **kiểu tham số** chứ không phải tên lớp cụ thể. Chẳng hạn, nếu nguồn có `T = Order` và `map` lấy tên khách hàng (`R = String`), từ thời điểm đó lambda tiếp theo nhận `String` thay cho `Order`.

## 2. Ví dụ độc lập: theo vết từng kiểu của pipeline

Tạo file `PipelineTypeTrace.java`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class PipelineTypeTrace {
    record Order(String customer, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 120),
                new Order("Bình", 70),
                new Order("Chi", 180),
                new Order("An", 150)
        );

        Stream<Order> source = orders.stream();
        Stream<Order> expensive = source.filter(o -> o.total() >= 100);
        Stream<String> customers = expensive.map(Order::customer);
        Stream<String> unique = customers.distinct();
        Stream<String> alphabetical = unique.sorted();

        List<String> result = alphabetical.toList();
        System.out.println(result);
    }
}
~~~

~~~bash
javac --release 17 PipelineTypeTrace.java
java PipelineTypeTrace
~~~

Kết quả:

~~~text
[An, Chi]
~~~

Giải thích từng bước:

- `orders.stream()`: đối tượng nguồn là `List<Order>`; kết quả là `Stream<Order>`.
- `filter(o -> o.total() >= 100)`: `o` là `Order`, biểu thức điều kiện trả `boolean`; kết quả vẫn là `Stream<Order>`.
- `map(Order::customer)`: hàm trích xuất nhận `Order`, trả `String`; kiểu chuyển thành `Stream<String>`.
- `distinct()`: loại phần tử trùng theo `equals()`, không đổi `String` thành kiểu khác.
- `sorted()`: sắp xếp `String` theo thứ tự tự nhiên, vẫn là `Stream<String>`.
- `toList()`: terminal operation thu kết quả thành `List<String>`. Danh sách trả về bởi `Stream.toList()` không cho phép chỉnh sửa qua các thao tác như `add`.

Các biến `Stream<...>` trong ví dụ chỉ để bộc lộ kiểu tĩnh của từng giai đoạn. Viết pipeline nối chuỗi là tương đương về ý nghĩa trong trường hợp này:

~~~java
// Đoạn minh họa dùng danh sách orders đã khai báo trong ví dụ trên.
List<String> result = orders.stream()
        .filter(o -> o.total() >= 100)
        .map(Order::customer)
        .distinct()
        .sorted()
        .toList();
~~~

Mỗi stream được dùng một lần để nối tiếp pipeline; sau khi terminal operation chạy, không tiếp tục sử dụng stream đã tiêu thụ. Nếu cần thực hiện truy vấn khác trên cùng dữ liệu, tạo một stream mới từ nguồn.

## 3. `filter` thay đổi tập phần tử, không thay đổi kiểu phần tử

Đọc `filter` như “giữ hay bỏ từng phần tử `T`”. `Predicate<T>` trả về `boolean`; phương thức `filter` trả về `Stream<T>`.

~~~java
Stream<String> words = Stream.of("Java", "", "API");
Stream<String> nonEmpty = words.filter(s -> !s.isEmpty());
~~~

Nếu một lambda lọc dùng trường `age` của đối tượng, những phần tử còn lại **vẫn là đối tượng đó**, không tự trở thành tuổi:

~~~java
// Ký hiệu: Stream<Person> persons
Stream<Person> adults = persons.filter(p -> p.age() >= 18);
// Không thể gán kết quả trực tiếp cho Stream<Integer>.
~~~

Muốn lấy tuổi, bước kế tiếp phải là `map(Person::age)` hoặc `mapToInt(Person::age)`. Điều này thường giải thích lỗi IDE kiểu “cannot find symbol”: sau một `map` chuyển kiểu, lambda tiếp theo không còn nhận đối tượng cũ.

## 4. `map`: mỗi `T` chuyển thành một `R`

`map` nhận `Function<? super T, ? extends R>` và trả `Stream<R>`. Phần tử đầu ra của `map` là **giá trị do lambda trả về**:

~~~java
// Stream<String> nguồn:
Stream<String> names = Stream.of("An", "Bình", "Chi");

// String -> Integer (boxing chiều dài):
Stream<Integer> lengths = names.map(String::length);
~~~

Với ví dụ này, `String.length()` trả `int`; generic `Stream<R>` chỉ nhận kiểu tham chiếu, nên `int` được boxing thành `Integer` và kết quả có kiểu `Stream<Integer>`.

Nếu gọi tiếp `map(n -> n * 2)`, lambda nhận một `Integer` (tự unbox khi tính toán) và pipeline vẫn là `Stream<Integer>`. Không thể gọi `String::toUpperCase` trên `Stream<Integer>`: kiểu phần tử đã chuyển.

**`map` không trải phẳng cấu trúc nhiều giá trị.** Nếu lambda trả `List<String>` thì kiểu kết quả là `Stream<List<String>>`; nếu trả `Stream<String>` thì kiểu là `Stream<Stream<String>>`. Mỗi phần tử gốc vẫn tương ứng với một giá trị kết quả của mapper (giá trị đó có thể là một collection/stream).

### Lỗi suy kiểu điển hình

~~~java
// Minh họa cố ý không biên dịch:
// Stream.of("abc", "d")
//       .map(String::length)         // Stream<Integer>
//       .filter(s -> s.startsWith("a")); // s ở đây là Integer!
~~~

Muốn lọc theo chuỗi, đặt `filter(s -> s.startsWith("a"))` **trước** `map(String::length)`. Muốn lọc chiều dài, viết `.filter(n -> n > 1)` **sau** `map`. Thứ tự biến đổi làm thay đổi cả kiểu tĩnh lẫn ý nghĩa nghiệp vụ.

## 5. `flatMap`: từ `T -> Stream<R>` thành một `Stream<R>`

Khi mỗi phần tử có **nhiều phần tử con**, `flatMap` là bước vừa biến đổi vừa trải phẳng một tầng. Ví dụ `List<List<String>>`:

~~~text
List<List<String>>
  .stream()                  → Stream<List<String>>
  .map(List::stream)         → Stream<Stream<String>>
  .flatMap(List::stream)     → Stream<String>  (nếu dùng thay map ở trên)
~~~

Hai dòng `map` và `flatMap` trong sơ đồ là **hai lựa chọn khác nhau tại cùng một điểm**, không phải hai lời gọi nối tiếp nhau.

File `FlatMapTypeDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class FlatMapTypeDemo {
    public static void main(String[] args) {
        List<List<String>> groups = List.of(
                List.of("An", "Bình"),
                List.of(),
                List.of("Chi")
        );

        Stream<List<String>> outer = groups.stream();
        Stream<String> flattened = outer.flatMap(List::stream);
        List<String> all = flattened.map(String::toUpperCase).toList();

        System.out.println(all);
    }
}
~~~

~~~bash
javac --release 17 FlatMapTypeDemo.java
java FlatMapTypeDemo
~~~

Kết quả:

~~~text
[AN, BÌNH, CHI]
~~~

Tại `flatMap(List::stream)`:

- Đầu vào của mapper là một `List<String>`.
- `List::stream` trả `Stream<String>` cho từng danh sách con.
- `flatMap` nối các luồng con thành một `Stream<String>`.
- Lambda trong `map(String::toUpperCase)` tiếp theo nhận **`String`**, không phải `List<String>`.

Với mapper trả null, hợp đồng của `Stream.flatMap` coi luồng con null như luồng rỗng; tuy vậy, trong code nên trả `Stream.empty()` rõ ràng khi muốn bỏ qua một nhánh, tránh phụ thuộc vào việc null có ý nghĩa gì ở từng API. `Optional.flatMap` có hợp đồng khác: mapper của `Optional` trả tham chiếu `Optional` null khi được gọi sẽ ném `NullPointerException`.

## 6. Chuyển từ `Stream<T>` sang primitive stream

Các phương thức `mapToInt`, `mapToLong`, `mapToDouble` làm **thay đổi cả họ stream**:

~~~text
Stream<String>
  .map(String::length)       → Stream<Integer>
  .mapToInt(String::length)  → IntStream
~~~

Hai dòng là **lựa chọn thay thế**, không được nối trực tiếp sau nhau trong sơ đồ.

File `PrimitivePipelineDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitivePipelineDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "Java", "abc");

        IntStream lengths = words.stream().mapToInt(String::length);
        int total = lengths.filter(n -> n >= 3).sum();
        System.out.println("total=" + total);

        List<Integer> boxed = words.stream()
                .mapToInt(String::length)
                .boxed()
                .toList();
        System.out.println("boxed=" + boxed);
    }
}
~~~

~~~bash
javac --release 17 PrimitivePipelineDemo.java
java PrimitivePipelineDemo
~~~

Kết quả:

~~~text
total=7
boxed=[1, 4, 3]
~~~

Diễn giải:

1. `words.stream()` là `Stream<String>`.
2. `mapToInt(String::length)` trả `IntStream`, mỗi phần tử là số `int`.
3. `IntStream.filter(IntPredicate)` vẫn trả `IntStream`.
4. `IntStream.sum()` kết thúc pipeline, trả `int` (trong ví dụ 4 + 3 = 7).
5. `IntStream.boxed()` biến các giá trị thành `Stream<Integer>`; `toList()` sau đó trả `List<Integer>`.

Trên `IntStream`, các API đặc thù gồm `sum()`, `average()`, `summaryStatistics()`, `boxed()` và `mapToObj()`. Một số phép tương tự có ở `Stream<T>`, nhưng kiểu trả về khác. Ví dụ `IntStream.average()` trả `OptionalDouble`, không phải `double` trần vì một stream rỗng không có trung bình xác định.

Cũng cần nhớ `IntStream.mapToObj(n -> "length=" + n)` trả lại `Stream<String>` nếu lambda tạo chuỗi; khi đó terminal operation `toList()` lại trả `List<String>`.

## 7. Từ một stream sang `Optional`, rồi sang giá trị

Terminal operation thay đổi dạng kết quả. Ví dụ:

~~~text
Stream<Order>
  .filter(...)                      → Stream<Order>
  .findFirst()                      → Optional<Order>
  .map(Order::customer)             → Optional<String>
  .orElse("Không có")               → String
~~~

Phần `map` sau `findFirst()` là **`Optional.map`**, không còn là `Stream.map`; hai API cùng tên nhưng receiver khác, và Optional chỉ mang tối đa một giá trị.

File `OptionalAfterStreamDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;

public class OptionalAfterStreamDemo {
    record Order(String customer, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 50),
                new Order("Bình", 150)
        );

        Optional<Order> selected = orders.stream()
                .filter(o -> o.total() >= 100)
                .findFirst();

        Optional<String> customer = selected.map(Order::customer);
        String name = customer.orElse("Không có");

        System.out.println("selected=" + selected.isPresent());
        System.out.println("name=" + name);
    }
}
~~~

~~~bash
javac --release 17 OptionalAfterStreamDemo.java
java OptionalAfterStreamDemo
~~~

Kết quả:

~~~text
selected=true
name=Bình
~~~

Một lỗi phổ biến là viết `.findFirst().filter(...).toList()`: `Optional.filter` có tồn tại, nhưng `Optional` **không có `toList()`**. Hãy nhìn kiểu hiện tại trước khi gọi tiếp API.

Một số terminal operation cần nhớ:

| Terminal operation | Kiểu kết quả | Ghi chú |
| --- | --- | --- |
| `Stream<T>.toList()` | `List<T>` | Danh sách không chỉnh sửa được qua API. |
| `Stream<T>.toArray()` | `Object[]` | Không tự trở thành `T[]` tại runtime. |
| `Stream<T>.toArray(String[]::new)` | `String[]` | Khi phần tử có thể lưu vào mảng `String[]`. |
| `Stream<T>.count()` | `long` | Số phần tử. |
| `Stream<T>.anyMatch(predicate)` | `boolean` | Có thể dừng sớm. |
| `Stream<T>.findFirst()` | `Optional<T>` | Với một stream có thứ tự, chọn phần tử đầu theo encounter order. |
| `IntStream.sum()` | `int` | Tổng nguyên thủy, empty cho tổng 0. |
| `IntStream.average()` | `OptionalDouble` | Có thể empty. |
| `Stream<T>.collect(collector)` | Phụ thuộc `Collector` | Ví dụ `List<T>`, `Map<K,List<T>>`, `Long`... |

## 8. `collect` có thể đổi cấu trúc thành `Map`

Không phải mọi terminal operation đều cho ra list. Với `Collectors.groupingBy`, hãy đọc kiểu khóa từ hàm phân nhóm và kiểu phần tử từ stream **ngay trước collector**.

File `GroupingTypeDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingTypeDemo {
    record Item(String category, String name) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("book", "Java"),
                new Item("tool", "Git"),
                new Item("book", "Kotlin")
        );

        Map<String, List<String>> namesByCategory = items.stream()
                .collect(Collectors.groupingBy(
                        Item::category,
                        TreeMap::new,
                        Collectors.mapping(Item::name, Collectors.toList())
                ));

        System.out.println(namesByCategory);
    }
}
~~~

~~~bash
javac --release 17 GroupingTypeDemo.java
java GroupingTypeDemo
~~~

Kết quả:

~~~text
{book=[Java, Kotlin], tool=[Git]}
~~~

Ở đây:

~~~text
List<Item>
  .stream()                                          → Stream<Item>
  .collect(groupingBy(Item::category,
                      TreeMap::new,
                      mapping(Item::name, toList())))  → Map<String, List<String>>
~~~

`groupingBy` nhận khóa `String` từ `Item::category`; downstream `mapping` lấy `String name` và thu vào `List<String>`. `TreeMap::new` giúp thứ tự khóa trong kết quả được sắp theo thứ tự tự nhiên, nên stdout trong ví dụ là xác định. Nếu dùng `groupingBy(Item::category)` mặc định thì kết quả điển hình là `Map<String,List<Item>>`, và không nên phụ thuộc vào thứ tự duyệt khóa của map.

## 9. Thứ tự gọi phương thức và kiểu giúp phát hiện lỗi

Xem biểu thức:

~~~java
// Giả sử orders là List<Order> và Order.total() trả int.
orders.stream()
      .map(Order::customer)
      .filter(o -> o.total() > 100); // Sai kiểu ở lambda.
~~~

Sau `map(Order::customer)`, kiểu đã là `Stream<String>`: biến `o` trong `filter` là `String`, không còn là `Order`; không có phương thức `total()`.

Một cách đúng là lọc theo thuộc tính của `Order` **trước** khi chuyển sang tên:

~~~java
orders.stream()
      .filter(o -> o.total() > 100)
      .map(Order::customer)
      .toList();
~~~

Một cách đúng khác, nếu mục tiêu là lọc theo độ dài tên khách, là đổi predicate sau map:

~~~java
orders.stream()
      .map(Order::customer)
      .filter(name -> name.length() > 2)
      .toList();
~~~

Đây là hai yêu cầu nghiệp vụ khác nhau. IDE hoặc compiler có thể cảnh báo sai kiểu, nhưng chỉ việc đọc đường đi `Stream<Order> → Stream<String>` mới giúp xác nhận chỗ cần sửa.

## 10. Phân biệt kiểu phần tử và số phần tử

Hai câu hỏi cần tách riêng:

- **Kiểu phần tử** sau bước này là gì? Ví dụ `Stream<String>`.
- **Số phần tử** có thể thay đổi ra sao? Ví dụ `filter` có thể loại nhiều phần tử, `flatMap` có thể cho 0/nhiều phần tử từ một phần tử đầu vào, `distinct` có thể gộp trùng.

| Thao tác trung gian | Kiểu | Ảnh hưởng thường gặp đến lượng phần tử |
| --- | --- | --- |
| `filter` | `Stream<T> → Stream<T>` | Giữ hoặc bỏ từng phần tử. |
| `map` | `Stream<T> → Stream<R>` | Một phần tử đầu vào cho một phần tử đầu ra, kể cả nếu mapper tạo ra một collection. |
| `flatMap` | `Stream<T> → Stream<R>` | Một phần tử đầu vào có thể cho 0, 1, hoặc nhiều phần tử đầu ra. |
| `distinct` | `Stream<T> → Stream<T>` | Loại trùng theo `equals` trên kết quả hiện tại. |
| `limit(n)` | `Stream<T> → Stream<T>` | Giới hạn số phần tử tối đa là `n`. |
| `sorted` | `Stream<T> → Stream<T>` | Sắp thứ tự, không tự đổi kiểu phần tử. |

Ví dụ `Stream<List<String>>` gồm ba phần tử (ba danh sách) không có nghĩa `Stream<String>` sau `flatMap` có ba phần tử; kết quả có thể có tổng số chuỗi trong tất cả danh sách con.

Đặc biệt, `distinct()` đặt trước `map` khác `distinct()` đặt sau `map`: trước map nó so sánh đối tượng nguồn, sau map nó so sánh giá trị đã chuyển đổi. Cả hai có thể đúng, nhưng không thay thế tùy tiện.

## 11. Pipeline lazy: kiểu tĩnh có ngay, xử lý dữ liệu có thể diễn ra sau

Một pipeline có thể được khai báo mà chưa tiêu thụ dữ liệu:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        Stream<String> pipeline = List.of("a", "bb", "ccc").stream()
                .filter(s -> {
                    System.out.println("filter=" + s);
                    return s.length() >= 2;
                })
                .map(s -> {
                    System.out.println("map=" + s);
                    return s.toUpperCase();
                });

        System.out.println("ready");
        List<String> result = pipeline.toList();
        System.out.println("result=" + result);
    }
}
~~~

~~~bash
javac --release 17 LazyPipelineDemo.java
java LazyPipelineDemo
~~~

Kết quả cho stream tuần tự trong ví dụ:

~~~text
ready
filter=a
filter=bb
map=bb
filter=ccc
map=ccc
result=[BB, CCC]
~~~

Dù `filter` và `map` đã được khai báo, hoạt động của chúng chỉ được thực hiện khi terminal operation `toList()` tiêu thụ stream. Cách thực thi pipeline có thể *fuse* các thao tác trên từng phần tử; đừng hình dung luôn tạo một danh sách trung gian cho tất cả kết quả `filter` rồi mới chạy tất cả `map`.

**Không nên dựa vào side effect** trong `map`, `filter` hay `peek` để thực hiện nghiệp vụ. Một số terminal operation và tối ưu hóa có thể không cần chạy tất cả các lambda; pipeline song song cũng có thứ tự thực thi khác. Ví dụ logging ở trên chủ yếu để minh họa sự trì hoãn trong trường hợp cụ thể. Chọn terminal operation để thu kết quả; đừng coi việc lambda được gọi bao nhiêu lần là một hợp đồng dùng thay cho xử lý chính.

## 12. Khi kiểu gặp lỗi generic, hãy khai báo các bước trung gian để dò

Với pipeline dài, phương pháp kiểm tra hữu ích là tách tạm thành biến có kiểu rõ ràng:

~~~java
// Minh họa trong phương thức đã có List<String> source.
Stream<String> words = source.stream();
Stream<Integer> lengths = words.map(String::length);
Stream<Integer> large = lengths.filter(n -> n >= 3);
List<Integer> output = large.toList();
~~~

Nếu đoạn trên không biên dịch, compiler sẽ khoanh vùng chỗ kiểu kết quả không đáp ứng kiểu biến. Sau khi hiểu và sửa, có thể ghép lại thành một chuỗi. Khi viết helper generic, cũng nên giữ kiểu kết quả của `map`, `flatMap` và terminal rõ ràng, tránh ép kiểu cưỡng bức để che lỗi suy luận.

Trong IDE, có thể dùng “quick documentation”, hiển thị type của biểu thức hoặc trích xuất biến local. Khi đánh giá lambda:

- `filter(x -> ...)` phải trả `boolean`.
- `map(x -> ...)` có thể trả nhiều kiểu `R`, kể cả `List<R>` hoặc `Optional<R>`, nhưng **không tự flatten**.
- `flatMap(x -> ...)` của `Stream` cần mapper trả một `Stream<R>`.
- `mapToInt(x -> ...)` cần giá trị `int`, không phải `OptionalInt`.
- `findFirst()`, `count()`, `toList()`, `collect(...)` kết thúc pipeline; sau đó receiver không còn là stream.

## 13. Các lỗi thường gặp khi đọc Stream pipeline

1. **Đọc `filter` như `map`:** lọc theo thuộc tính không biến phần tử thành thuộc tính.
2. **Quên `map` đã đổi kiểu:** gọi lại method của lớp nguồn trên phần tử đã chuyển thành `String` hoặc `Integer`.
3. **Nhầm `Stream<List<T>>` với `Stream<T>`:** `map(List::stream)` tạo stream lồng nhau; `flatMap(List::stream)` mới trải phẳng.
4. **Nhầm primitive stream với `Stream<Integer>`:** `mapToInt` trả `IntStream`, `map` với hàm trả `int` sẽ boxing thành `Stream<Integer>`.
5. **Quên terminal operation đổi đối tượng receiver:** sau `findFirst` là `Optional<T>`; sau `toList` là `List<T>`; không còn đang nối tiếp `Stream<T>`.
6. **Tưởng mỗi intermediate operation lập tức chạy:** chúng thường lazy, pipeline được tiêu thụ bởi terminal operation.
7. **Đánh đồng kiểu phần tử và cardinality:** `filter`, `flatMap`, `distinct` có thể làm thay đổi số phần tử mà không nhất thiết đổi kiểu.
8. **Giả định dữ liệu mutable sẽ luôn an toàn:** tránh sửa collection nguồn trong khi pipeline đang xử lý và tránh side effect lên trạng thái chia sẻ khi chạy song song.
9. **Tưởng `toArray()` tự trả `T[]`:** overload không tham số của object stream trả `Object[]`; dùng generator như `String[]::new` khi cần mảng cụ thể.
10. **Dựa vào thứ tự của nguồn unordered:** dùng nguồn có thứ tự và API bảo toàn encounter order nếu kết quả cần tính thứ tự; không xem mọi loại `Set` hoặc `Map` là có thứ tự xác định.

## 14. Bài tập tự đọc pipeline

Hãy dự đoán **kiểu sau mỗi bước** trước khi chạy đoạn sau:

~~~java
List<String> results = java.util.stream.Stream.of("Java", "SQL", "Go")
        .filter(s -> s.length() >= 3)
        .map(String::length)
        .map(n -> "len=" + n)
        .sorted()
        .toList();
~~~

Đáp án:

~~~text
Stream.of(...)                   → Stream<String>
filter(String -> boolean)        → Stream<String>
map(String -> Integer)           → Stream<Integer>
map(Integer -> String)           → Stream<String>
sorted()                         → Stream<String>
toList()                         → List<String>
Giá trị cuối                     → [len=3, len=4]
~~~

Đây là sắp xếp **chuỗi** `"len=3"`, `"len=4"`. Nếu muốn sắp theo giá trị số trước khi định dạng, hãy đổi thứ tự thao tác thành `.map(String::length).sorted().map(n -> "len=" + n)`. Việc dịch chuyển `sorted` có thể làm thay đổi ý nghĩa nếu cách biểu diễn chuỗi không bảo toàn thứ tự số học, chẳng hạn `"len=10"` so với `"len=2"`.

**Ghi nhớ:** Khi đọc pipeline, luôn viết chuỗi kiểu **`Nguồn → Stream<T> → Stream<R> / IntStream → terminal result`**. Chỉ cần xác định kiểu receiver, input/output của lambda và kiểu phương thức trả về ở từng dấu chấm, bạn sẽ tránh được phần lớn lỗi về generic, lambda, boxing, `flatMap` và cách dùng API sau terminal operation.