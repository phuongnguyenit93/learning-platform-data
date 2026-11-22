# Đọc chữ ký map, flatMap và collect trong Stream của Java Generics

## 1. Tại sao cần biết đọc chữ ký generic thay vì chỉ nhớ ví dụ?

`java.util.stream.Stream<T>` mô tả một luồng xử lý các phần tử có kiểu **T**. Ba nhóm API thường xuất hiện cùng nhau:

- **`map`**: biến mỗi T thành một R; tạo một **Stream<R>**.
- **`flatMap`**: biến mỗi T thành một **Stream con**, rồi nối các stream con thành một **Stream<R>**.
- **`collect`**: **terminal operation** gom các phần tử hiện tại của stream vào một kết quả R thông qua một Collector hoặc ba hành vi xây dựng/gộp.

Điểm khó nằm ở các tham số kiểu `T`, `R`, `A` cùng wildcard bounds `? super` và `? extends`. Khi nắm cách đọc, ta có thể hiểu vì sao pipeline biên dịch được hoặc lỗi, compiler suy luận kiểu ở mỗi bước ra sao, và vì sao `map` không tương đương `flatMap`.

Một pipeline điển hình:

~~~java
List<String> names = orders.stream()
        .filter(order -> order.total() > 0)
        .map(Order::customer)
        .collect(Collectors.toList());
~~~

Đây là **mảnh minh họa** giả định đã định nghĩa record `Order` và biến `orders`; chương trình đầy đủ xuất hiện ở phần 9. Kiểu của dòng dữ liệu biến đổi theo từng bước:

~~~text
List<Order>
    .stream()                  Stream<Order>
    .filter(Predicate<Order>)  Stream<Order>
    .map(Function<Order,String>)
                               Stream<String>
    .collect(Collector<String,?,List<String>>)
                               List<String>
~~~

`map` và `flatMap` là **intermediate operations**, thường lazy; `collect` là **terminal operation**, yêu cầu pipeline tạo kết quả. Luồng đã sử dụng terminal operation không được dùng lại như một stream mới.

## 2. Đọc đúng chữ ký thật trong Java 17

Rút gọn từ `java.util.stream.Stream<T>`:

~~~java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper);

<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);

<R, A> R collect(
        Collector<? super T, A, R> collector);

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

Các chữ ký trên đã bỏ `public abstract` và thông tin khai báo bao quanh để dễ đọc; chúng không phải một class Java độc lập cần copy chạy. Đây là **hai overload khác nhau** của `collect`, cùng tên nhưng nhận loại đối số khác nhau.

Bảng giải mã ký hiệu:

| Ký hiệu | Vai trò | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu phần tử hiện tại của `Stream<T>` | `Order` với `Stream<Order>` |
| `R` trong `map/flatMap` | Kiểu phần tử của stream sau biến đổi | `String` trong `Stream<String>` |
| `R` trong `collect` | Kiểu **kết quả cuối** | `List<String>`, `Map<String,Integer>` |
| `A` | Kiểu tích lũy **trung gian** bên trong Collector | Một mutable container, có thể khác R |
| `Function<? super T, ? extends R>` | Mapper nhận được T và tạo một giá trị tương thích R | `Order::customer` |
| `Stream<? extends R>` | Một stream con với phần tử là R hoặc subtype của R | `List<Integer>.stream()` khi R phù hợp |
| `Collector<? super T,A,R>` | Collector tiêu thụ được các T và tạo R | `Collectors.toList()` |
| `Supplier<R>`, `BiConsumer<...>` | Ba hành vi cấp phát, tích lũy, gộp kết quả | `ArrayList::new`, `List::add`, `List::addAll` |

Chữ `<R>` đặt **trước kiểu trả về** khai báo type parameter của chính generic method. Nó không có nghĩa method trả về một object có class tên R. Compiler suy luận R bằng target context, kiểu của mapper và các generic constraints.

## 3. Quy tắc wildcard: ? super khi nhận vào, ? extends khi tạo ra

Trong chữ ký `Stream<T>.map`:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
~~~

`? super T` cho mapper **nhận** được giá trị `T` qua một supertype, còn `? extends R` cho mapper **trả** kết quả thuộc subtype thích hợp của `R`. Đây là PECS theo hướng input/output của callback, **không** có nghĩa `Stream<Integer>` là subtype của `Stream<Number>`.

Ví dụ trong ngữ cảnh có imports cần thiết:

~~~java
Stream<Integer> integers = Stream.of(1, 2, 3);
Function<Number, String> asText = Object::toString;
List<String> result = integers.map(asText).toList();
~~~

Function nhận `Number` vẫn xử lý được từng `Integer`. Khi tiếp tục đọc `flatMap` và `collect`, hãy giữ đúng hướng này nhưng **phân biệt thêm** mapper trả `Stream<? extends R>` và collector có kiểu tích lũy `A` khác kiểu trả cuối cùng `R`. Đó là trọng tâm riêng của bài Stream, không chỉ lặp lại quy tắc wildcard tổng quát.

## 4. map: một phần tử đầu vào tạo một phần tử đầu ra

Chữ ký:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
~~~

Với mỗi phần tử T mà pipeline cần xử lý, mapper tạo một phần tử kết quả kiểu R. Những phần tử ấy tạo nên một `Stream<R>`.

Ví dụ:

~~~java
List<String> languages = List.of("Java", "Go", "Kotlin");

List<Integer> lengths = languages.stream()
        .map(String::length)
        .toList();
~~~

Kết quả:

~~~text
[4, 2, 6]
~~~

Phân tích kiểu:

~~~text
Stream<String>
    map(String::length)           Function<String,Integer>
                                   (int được boxing thành Integer)
    ↓
Stream<Integer>
    toList()
    ↓
List<Integer>
~~~

`map` giữ lại quan hệ **mỗi phần tử nguồn được biến đổi bằng một lần áp dụng mapper khi phần tử đó được xử lý**; nhưng không nên kết luận mapper luôn được gọi đúng số phần tử nguồn trong mọi pipeline phức tạp. Stream có thể short-circuit hoặc tối ưu một số thao tác theo ngữ nghĩa API.

### 4.1. map khi mapper trả một collection

Ví dụ mỗi đơn hàng giữ một danh sách giá:

~~~java
record Order(String customer, List<Integer> prices) {}

List<Order> orders = List.of(
        new Order("Lan", List.of(20, 30)),
        new Order("An", List.of(10))
);

List<List<Integer>> nested = orders.stream()
        .map(Order::prices)
        .toList();
~~~

Kết quả:

~~~text
[[20, 30], [10]]
~~~

Đầu vào là `Stream<Order>`. `Order::prices` trả `List<Integer>`, nên `R = List<Integer>`; sau map, ta có `Stream<List<Integer>>`, **không phải Stream<Integer>**.

Đây là mấu chốt: **map không tự làm phẳng collection hoặc stream được mapper trả về**. Nếu mapper trả một List, mỗi phần tử kết quả của Stream vẫn là **một List**.

### 4.2. map và mapToInt

Nếu mapper trả một giá trị số nguyên primitive, `map` thường đưa tới `Stream<Integer>` vì type arguments generic không thể là primitive int:

~~~java
Stream<Integer> boxed = Stream.of("A", "BB")
        .map(String::length);
~~~

Trong khi:

~~~java
IntStream lengths = Stream.of("A", "BB")
        .mapToInt(String::length);

int sum = lengths.sum(); // 3
~~~

`mapToInt(ToIntFunction<? super T>)` trả `IntStream`, một primitive stream chuyên biệt. Không nên dùng `map(String::length)` rồi mong gọi trực tiếp mọi API primitive giống hệt IntStream.

## 5. flatMap: mỗi T tạo một stream con, sau đó làm phẳng một mức

Chữ ký:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

Khác với map, mapper của flatMap phải trả về một **Stream** (hoặc subtype phù hợp), không phải một R đơn lẻ.

Ví dụ:

~~~java
List<List<Integer>> batches = List.of(
        List.of(1, 2),
        List.of(3),
        List.of(4, 5)
);

List<Integer> numbers = batches.stream()
        .flatMap(List::stream)
        .toList();
~~~

Kết quả:

~~~text
[1, 2, 3, 4, 5]
~~~

Kiểu tại từng bước:

~~~text
Stream<List<Integer>>
    flatMap(List::stream)
        List<Integer> → Stream<Integer>
    ↓
Stream<Integer>
    toList()
    ↓
List<Integer>
~~~

`flatMap` có thể trả **0, 1 hoặc nhiều phần tử đầu ra cho một phần tử đầu vào**, tùy stream con. Điều này giúp dùng khi xử lý nhiều danh sách, chuỗi từ vựng, các bản ghi con hoặc kết quả tìm kiếm chứa nhiều items.

### 5.1. Không phải flatten đệ quy vô hạn

Nếu đầu vào là `Stream<List<List<String>>>`, chỉ gọi một lần `flatMap(List::stream)` sẽ tạo `Stream<List<String>>`. Muốn thành `Stream<String>` cần làm phẳng thêm một mức:

~~~java
List<List<List<String>>> levels = List.of(
        List.of(List.of("A", "B")),
        List.of(List.of("C"))
);

List<String> words = levels.stream()
        .flatMap(List::stream)
        .flatMap(List::stream)
        .toList();
~~~

Kết quả `[A, B, C]`. Hai lần flatMap xử lý hai mức cấu trúc lồng nhau; không có quy tắc tự động “làm phẳng bao nhiêu lớp cũng được”.

### 5.2. flatMap có thể loại phần tử bằng Stream.empty()

~~~java
List<String> source = List.of("A", "", "B");

List<String> nonBlank = source.stream()
        .flatMap(s -> s.isBlank()
                ? Stream.empty()
                : Stream.of(s))
        .toList();
~~~

Kết quả `[A, B]`. Với mỗi chuỗi trống, mapper trả stream rỗng nên không tạo phần tử đầu ra. Nếu bài toán đơn thuần là loại bỏ, `filter` thường dễ đọc hơn; ví dụ này giúp thấy khả năng một đầu vào tạo **0 phần tử** của flatMap.

### 5.3. Tại sao không trả trực tiếp List?

Sai kiểu:

~~~java
// orders.stream().flatMap(Order::prices);
// Không biên dịch: Order::prices trả List<Integer>, không phải Stream<Integer>.
~~~

Cách sửa:

~~~java
orders.stream().flatMap(order -> order.prices().stream());
~~~

`List.stream()` tạo Stream<Integer>, nên đáp ứng chữ ký Function nhận Order và trả Stream<? extends R>.

### 5.4. flatMap xử lý stream con thế nào?

Khi một mapped stream được sử dụng trong flatMap, Java sẽ xử lý phần tử của stream con và **đóng stream con sau khi sử dụng** theo hợp đồng API. Nếu mapper trả null stream, hợp đồng Stream.flatMap xử lý như một stream rỗng; tuy vậy trong code ứng dụng, trả rõ `Stream.empty()` giúp ý định sáng hơn và tránh phụ thuộc vào null.

Một stream không được tái sử dụng sau terminal operation; tương tự, đừng tái sử dụng một stream con đã bị tiêu thụ để map một phần tử khác. Với dữ liệu từ collection, gọi `list.stream()` mới mỗi lần là tự nhiên.

## 6. Bảng so sánh map và flatMap bằng kiểu

| Đầu vào | Mapper | API | Sau phép biến đổi |
| --- | --- | --- | --- |
| `Stream<String>` | `String::length` trả int/Integer | `map` | `Stream<Integer>` |
| `Stream<Order>` | `Order::customer` trả String | `map` | `Stream<String>` |
| `Stream<Order>` | `Order::prices` trả List<Integer> | `map` | `Stream<List<Integer>>` |
| `Stream<Order>` | `o -> o.prices().stream()` trả Stream<Integer> | `flatMap` | `Stream<Integer>` |
| `Stream<List<String>>` | `List::stream` trả Stream<String> | `flatMap` | `Stream<String>` |
| `Stream<String>` | `s -> Stream.of(s, s)` | `flatMap` | `Stream<String>` với hai kết quả cho mỗi đầu vào |

Câu hỏi chẩn đoán trước khi chọn API: “Mapper của mình trả **một R** hay trả **một Stream<R>**?” Nếu trả một kết quả, dùng map; nếu trả stream con và muốn gộp các phần tử của chúng, dùng flatMap.

Một phương thức trả Optional cũng có thể cung cấp stream con qua `Optional.stream()` (Java 9+):

~~~java
List<String> present = Stream.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B"))
        .flatMap(Optional::stream)
        .toList(); // [A, B]
~~~

Cách này làm phẳng Stream<Optional<String>> thành Stream<String>, bỏ qua các Optional rỗng.

## 7. collect là terminal operation và khác map/flatMap

`map`, `flatMap` chỉ biến đổi một `Stream<T>` thành stream khác; chúng không tự gom các phần tử vào danh sách hoặc map.

`collect` là một **terminal reduction**: dùng các phần tử của stream để tạo kết quả. Có **hai overload** chính trong `Stream<T>`:

~~~java
<R, A> R collect(Collector<? super T, A, R> collector);

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

Ở overload đầu, một **Collector** đóng gói logic tích lũy, kết hợp, hoàn thiện kết quả và characteristics. Overload thứ hai nhận trực tiếp **ba hành vi** dùng để tạo và gộp kết quả mutable.

Điểm thường bị đọc sai: **R của collect không nhất thiết là kiểu phần tử đầu vào**. Từ `Stream<Order>`, một collector có thể tạo:
- `List<Order>`;
- `Map<String,List<Order>>`;
- `Map<String,Integer>`;
- `Long`;
- `String`;
- một kiểu kết quả riêng của ứng dụng.

Hãy theo dõi **T của stream hiện tại** và **R được Collector tạo ra** thay vì suy ra R luôn là List<T>.

## 8. collect(Collector<? super T,A,R>): ý nghĩa của ba tham số kiểu

Chữ ký:

~~~java
<R, A> R collect(Collector<? super T, A, R> collector);
~~~

Giải mã:

- `T`: phần tử đang được xử lý trong stream.
- `? super T`: collector có thể tiêu thụ T **hoặc một supertype của T**.
- `A`: kiểu **container tích lũy trung gian** (*mutable accumulation type*) mà Collector quản lý. Người gọi nhiều khi không cần biết nó và API có thể biểu diễn bằng `?`.
- `R`: kiểu **kết quả cuối** mà `collect` trả về.

Ví dụ:

~~~java
List<String> names = Stream.of("Java", "Go")
        .collect(Collectors.toList());
~~~

`Collectors.toList()` có chữ ký rút gọn:

~~~java
<T> Collector<T, ?, List<T>> toList();
~~~

Dấu `?` ở vị trí A có nghĩa implementation che loại accumulator cụ thể; không phải Java không biết gì về dữ liệu. Kết quả R là `List<T>`, ở ví dụ này là `List<String>`.

### 8.1. A có thể khác R

Với collector có bước *finisher*, container tích lũy bên trong và kết quả công khai có thể thuộc các kiểu khác nhau. Không nên khẳng định `Collector<T,A,R>` luôn cần `A=R`.

Một collector có thể dùng một mutable builder như `StringBuilder` để tích lũy rồi trả một `String` sau khi hoàn tất. Cơ chế Collector gồm:
- supplier: tạo A;
- accumulator: nhận A và T để tích lũy;
- combiner: ghép hai A;
- finisher: chuyển A sang R;
- characteristics: mô tả các tính chất hỗ trợ tối ưu hoặc thực thi song song theo hợp đồng.

`Collectors.joining()` là một ví dụ dễ hình dung: gom các CharSequence để cho String kết quả mà không bắt caller quản lý builder.

### 8.2. Tại sao collector nhận ? super T?

Giống `map`, collector có thể tiêu thụ một supertype của stream element type. Khi API viết `Collector<? super T,A,R>`, nó tránh yêu cầu mọi collector phải khai báo đúng T tuyệt đối. Đây là một biểu hiện nữa của quy tắc **consumer super**.

Đừng suy luận dấu wildcard `?` trong `Collector<T,?,List<T>>` mang nghĩa “List đầu ra chứa Object”. Dấu hỏi đó đứng ở **A — accumulator nội bộ**, còn kết quả List vẫn giữ T.

## 9. Chương trình Java 17+ đầy đủ minh họa map, flatMap và collect

Lưu tệp **StreamSignaturesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamSignaturesDemo {
    record Order(String customer, List<Integer> prices) {
        int total() {
            return prices.stream()
                    .mapToInt(Integer::intValue)
                    .sum();
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("Lan", List.of(20, 30)),
                new Order("An", List.of(10)),
                new Order("Lan", List.of(5, 15))
        );

        List<String> labels = orders.stream()
                .map(o -> o.customer() + ":" + o.prices().size())
                .toList();
        System.out.println("map=" + labels);

        List<List<Integer>> nested = orders.stream()
                .map(Order::prices)
                .toList();
        System.out.println("nested=" + nested);

        List<Integer> flattened = orders.stream()
                .flatMap(o -> o.prices().stream())
                .toList();
        System.out.println("flatMap=" + flattened);

        // Overload collect(supplier, accumulator, combiner).
        List<String> threeArg = orders.stream()
                .map(Order::customer)
                .collect(ArrayList::new, List::add, List::addAll);
        System.out.println("collect3=" + threeArg);

        // Collector mapping: biến Order thành Integer bên trong collect.
        List<Integer> totals = orders.stream()
                .collect(Collectors.mapping(
                        Order::total, Collectors.toList()
                ));
        System.out.println("mapping=" + totals);

        // Collector flatMapping: làm phẳng phần tử trước downstream.
        List<Integer> withFlatMapping = orders.stream()
                .collect(Collectors.flatMapping(
                        o -> o.prices().stream(),
                        Collectors.toList()
                ));
        System.out.println("flatMapping=" + withFlatMapping);

        // TreeMap để thứ tự key trong output được xác định.
        Map<String, Integer> grouped = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::customer,
                        TreeMap::new,
                        Collectors.summingInt(Order::total)
                ));
        System.out.println("grouped=" + grouped);

        Map<String, Integer> merged = orders.stream()
                .collect(Collectors.toMap(
                        Order::customer,
                        Order::total,
                        Integer::sum,
                        TreeMap::new
                ));
        System.out.println("toMap=" + merged);

        try {
            // Trùng key "Lan" mà không cung cấp merge function.
            orders.stream().collect(Collectors.toMap(
                    Order::customer, Order::total
            ));
        } catch (IllegalStateException error) {
            System.out.println("duplicate=IllegalStateException");
        }

        Function<CharSequence, String> trim =
                s -> s.toString().trim();

        List<String> cleaned = Stream.of(" Lan ", " An ")
                .map(trim)
                .toList();
        System.out.println("wildcard=" + cleaned);

        try {
            labels.add("new");
        } catch (UnsupportedOperationException error) {
            System.out.println("toList=unmodifiable");
        }
    }
}
~~~

Biên dịch với JDK hỗ trợ Java 17:

~~~bash
javac --release 17 -Xlint:all StreamSignaturesDemo.java
java StreamSignaturesDemo
~~~

**Stdout đã được kiểm chứng:**

~~~text
map=[Lan:2, An:1, Lan:2]
nested=[[20, 30], [10], [5, 15]]
flatMap=[20, 30, 10, 5, 15]
collect3=[Lan, An, Lan]
mapping=[50, 10, 20]
flatMapping=[20, 30, 10, 5, 15]
grouped={An=10, Lan=70}
toMap={An=10, Lan=70}
duplicate=IllegalStateException
wildcard=[Lan, An]
toList=unmodifiable
~~~

### 9.1. Phân tích kiểu từng dòng kết quả

`map=[Lan:2, An:1, Lan:2]`: biến `Order` thành `String`; số phần tử giữ nguyên ở tình huống này.

`nested=[[20, 30], [10], [5, 15]]`: `Order::prices` trả `List<Integer>` nên `map` cho `Stream<List<Integer>>`; thu thành `List<List<Integer>>`.

`flatMap=[20, 30, 10, 5, 15]`: mapper `o -> o.prices().stream()` trả `Stream<Integer>`, nên `flatMap` nối các stream con thành `Stream<Integer>`.

`collect3=[Lan, An, Lan]`: sau `map(Order::customer)`, stream hiện tại chứa String; overload ba tham số tạo ArrayList<String>, thêm từng String rồi gộp các container khi cần.

`mapping=[50, 10, 20]`: mỗi Order được biến thành tổng tiền Integer bằng `Order::total` trong `Collectors.mapping`, sau đó downstream `toList` gom kết quả.

`flatMapping=[20, 30, 10, 5, 15]`: `Collectors.flatMapping` dùng stream con của từng order như bước chuẩn bị dữ liệu trước collector downstream.

`grouped={An=10, Lan=70}`: `groupingBy` phân nhóm theo customer, `summingInt` cộng tổng của các order cùng key, TreeMap sắp key theo thứ tự tự nhiên.

`toMap={An=10, Lan=70}`: `toMap` dùng customer làm key, total làm value và `Integer::sum` gộp các value khi trùng key; TreeMap giữ thứ tự key xác định.

`duplicate=IllegalStateException`: overload hai mapper của `toMap` không có merge function được cung cấp, nên dữ liệu có key "Lan" lặp gây ngoại lệ khi collect.

`wildcard=[Lan, An]`: `Function<CharSequence,String>` có thể được dùng làm mapper cho `Stream<String>` nhờ tham số `? super T` trong chữ ký map.

`toList=unmodifiable`: `Stream.toList()` từ Java 16 trả danh sách không cho phép sửa đổi; gọi add ném UnsupportedOperationException.

## 10. Overload collect(supplier, accumulator, combiner)

Chữ ký:

~~~java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

Ở overload này **không có A riêng**: kiểu container tích lũy được khai báo chính là R, cũng là kiểu kết quả trả về.

Đọc từng thành phần:
- `supplier`: tạo **container R mới** để tích lũy.
- `accumulator`: nhận container R và một phần tử T; thay đổi container để thêm dữ liệu.
- `combiner`: kết hợp hai container R; đặc biệt quan trọng khi engine cần gộp các kết quả từng nhánh của parallel stream.

Ví dụ:

~~~java
List<String> output = Stream.of("A", "B", "C")
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
~~~

Kiểu suy luận:
- Input `Stream<String>`: T = String.
- `ArrayList::new` cấp phát một ArrayList<String> có thể được nhìn dưới dạng List<String>.
- `List::add` chấp nhận container List<String> và phần tử String (giá trị trả boolean bị bỏ qua khi dùng làm BiConsumer).
- `List::addAll` kết hợp hai List<String>, thêm phần tử của container thứ hai vào container thứ nhất.
- Result R = `List<String>`.

**Điều kiện correctness:** combiner phải kết hợp đúng, và supplier/accumulator/combiner cần tuân thủ các ràng buộc của mutable reduction. Nếu combiner chỉ bỏ qua container thứ hai, kết quả có thể trông đúng ở tuần tự nhưng thiếu phần tử khi chạy parallel.

### 10.1. Vì sao không chỉ dùng một ArrayList global?

Sai lầm thường gặp:

~~~java
List<String> shared = new ArrayList<>();
// stream.parallel().forEach(shared::add); // Không an toàn.
~~~

`ArrayList` không thread-safe để nhiều thread cùng thay đổi qua `forEach` không đồng bộ. Trong overload collect ba tham số, framework có thể tạo các container riêng bằng supplier và dùng combiner để kết hợp; đây là cơ chế reduction được thiết kế cho môi trường parallel khi các ràng buộc về đồng nhất và liên kết được tuân thủ.

Không nên truyền một supplier luôn trả cùng một mutable global list, vì như vậy phá ý tưởng các container tích lũy độc lập.

### 10.2. Vì sao combiner không dùng để biến T sang R?

Trong chữ ký, `BiConsumer<R,R> combiner` nhận **hai container R**, không nhận phần tử T. Việc xử lý từng T thuộc `BiConsumer<R,? super T> accumulator`. Nếu cần biến đổi T thành R theo từng phần tử, dùng map trước hoặc xử lý trong accumulator có kiểm soát.

## 11. Collectors.toList và Stream.toList khác nhau

Hai cách thu về danh sách:

~~~java
List<String> a = Stream.of("A", "B")
        .collect(Collectors.toList());

List<String> b = Stream.of("A", "B")
        .toList();
~~~

Chúng có cùng **kiểu kết quả** `List<String>` và cùng phần tử trên stream có encounter order tương ứng, nhưng không có cùng mọi cam kết API.

- `Stream.toList()` có từ Java 16; trả **unmodifiable List**. Cố gắng thêm, xóa hoặc thay phần tử qua các thao tác sửa đổi sẽ ném UnsupportedOperationException.
- `Collectors.toList()` không bảo đảm cụ thể về kiểu implementation, mutability, serializability hoặc thread safety của List kết quả. Trên một số JDK có thể thấy ArrayList mutable, nhưng **không được xem đây là hợp đồng chuẩn**.
- `Collectors.toCollection(ArrayList::new)` dùng khi cần collection cụ thể là ArrayList do factory chỉ định.
- `Collectors.toUnmodifiableList()` cung cấp unmodifiable List qua collector; phương thức này không chấp nhận phần tử null theo hợp đồng.

Ví dụ:

~~~java
List<String> mutable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

mutable.add("C"); // Hợp lệ với ArrayList.
~~~

Đừng chọn `Collectors.toList()` chỉ vì muốn sửa kết quả nếu API thực sự đòi một ArrayList mutable; hãy thể hiện yêu cầu bằng `toCollection`.

## 12. groupingBy: đọc classifier, mapFactory và downstream

Overload cơ bản của `Collectors.groupingBy` có thể được mô tả như sau:

~~~java
<T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
        Function<? super T, ? extends K> classifier);
~~~

Nó nhóm các phần tử T theo **khóa K** do classifier tạo, và trả Map<K,List<T>>.

Ví dụ:

~~~java
Map<Integer, List<String>> byLength = Stream.of("A", "BB", "C")
        .collect(Collectors.groupingBy(String::length));
~~~

Kiểu:
- T = String.
- K = Integer.
- classifier: String → Integer.
- R = Map<Integer,List<String>>.

Nếu cần một kết quả downstream không phải List<T>, dùng overload có Collector:

~~~java
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
        Function<? super T, ? extends K> classifier,
        Collector<? super T, A, D> downstream);
~~~

Ở đây `D` là kết quả của **mỗi nhóm**, có thể là Long, Integer, Set<String>, hoặc một cấu trúc khác. Vì thế toàn bộ kết quả là `Map<K,D>`.

Ví dụ đếm mỗi nhóm:

~~~java
Map<Integer, Long> counts = Stream.of("A", "BB", "C")
        .collect(Collectors.groupingBy(
                String::length,
                Collectors.counting()
        ));
~~~

Kết quả theo nội dung: key 1 có count 2, key 2 có count 1. Không dựa vào thứ tự in của HashMap ở ví dụ này.

Chương trình đầy đủ dùng overload ba đối số:

~~~java
Collectors.groupingBy(
        Order::customer,
        TreeMap::new,
        Collectors.summingInt(Order::total)
)
~~~

Ý nghĩa:
- classifier lấy customer:String → K = String;
- mapFactory tạo TreeMap<String,Integer>;
- downstream cộng total của từng nhóm → D = Integer;
- result `Map<String,Integer>` được in ổn định theo key TreeMap.

Điểm rất hay bị hiểu sai: `groupingBy(classifier, downstream)` không đòi downstream nhận **một List<T> đã nhóm sẵn**; collector downstream được dùng để tích lũy những phần tử T thuộc từng nhóm.

## 13. Collectors.mapping và Collectors.flatMapping không phải Stream.map/flatMap

Hai API khác nhau:

~~~java
orders.stream()
      .map(Order::total)
      .collect(Collectors.toList());
~~~

và:

~~~java
orders.stream()
      .collect(Collectors.mapping(
              Order::total,
              Collectors.toList()
      ));
~~~

đều có thể tạo danh sách các tổng của từng order. Nhưng:
- `Stream.map` biến **stream trung gian** từ Stream<Order> thành Stream<Integer>.
- `Collectors.mapping` là **adapter collector**: nó biến từng phần tử Order thành Integer khi collector downstream nhận dữ liệu.

Một chữ ký rút gọn:

~~~java
<T, U, A, R> Collector<T, ?, R> mapping(
        Function<? super T, ? extends U> mapper,
        Collector<? super U, A, R> downstream);
~~~

Mapper nhận T và tạo U; downstream thu U để trả R.

Tương tự:

~~~java
<T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream);
~~~

`Collectors.flatMapping` làm phẳng stream con **ngay trong quá trình collect**, hữu ích khi nó là một downstream collector của groupingBy hoặc partitioningBy.

Ví dụ muốn lấy set các số nguyên trong mỗi nhóm customer:

~~~java
Map<String, Set<Integer>> valuesByCustomer = orders.stream()
        .collect(Collectors.groupingBy(
                Order::customer,
                Collectors.flatMapping(
                        o -> o.prices().stream(),
                        Collectors.toSet()
                )
        ));
~~~

Phần này giả định import `java.util.Set` và kiểu Order của chương trình đầy đủ. Mỗi nhóm customer nhận các Order, flatMapping tạo Integer từ các list giá, và downstream `toSet` gom các Integer, không cần tạo Stream trung gian để làm phẳng toàn bộ rồi cố dựng lại mối quan hệ customer.

**Lưu ý:** đây là hai mức API khác nhau; đừng cố gọi `.flatMap(Collectors.flatMapping(...))` vì `Stream.flatMap` cần Function trả Stream, còn `Collectors.flatMapping` trả một Collector.

## 14. Collectors.toMap: hai mapper và bài toán trùng khóa

Overload cơ bản:

~~~java
<T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);
~~~

Tức là với mỗi phần tử T:
- keyMapper sinh K;
- valueMapper sinh U;
- kết quả gom thành Map<K,U>.

Ví dụ:

~~~java
Map<String, Integer> values = Stream.of("A", "BB")
        .collect(Collectors.toMap(
                word -> word,
                String::length
        ));
~~~

Đầu vào `Stream<String>`, khóa String, giá trị Integer. Nhưng nếu có **hai phần tử tạo cùng key**, overload này ném IllegalStateException.

Trong chương trình ở phần 9, customer "Lan" xuất hiện hai lần. Vì vậy:

~~~java
orders.stream().collect(Collectors.toMap(
        Order::customer, Order::total
));
~~~

bị IllegalStateException do trùng khóa.

Muốn quyết định cách gộp value khi trùng khóa:

~~~java
Map<String, Integer> merged = orders.stream()
        .collect(Collectors.toMap(
                Order::customer,
                Order::total,
                Integer::sum,
                TreeMap::new
        ));
~~~

Ở overload này:
- `BinaryOperator<U> mergeFunction` kết hợp **hai giá trị U** của cùng key, không kết hợp hai đối tượng Order.
- `Supplier<M> mapFactory` chọn loại Map cần tạo; TreeMap giúp thứ tự key xác định.
- Kết quả có `Lan = 50 + 20 = 70`, `An = 10`.

Nếu dữ liệu lớn và parallel, merge function nên phù hợp các yêu cầu associativity và không gây các side effects khiến kết quả thiếu nhất quán. Chọn merge policy thể hiện nghiệp vụ: lấy đầu, lấy cuối, cộng, max, min, hoặc báo lỗi — không tùy tiện ghép string nếu thứ tự không được bảo đảm.

### 14.1. groupingBy so với toMap

`groupingBy` thường hợp khi muốn **nhóm nhiều phần tử theo khóa** và dùng downstream reductions. `toMap` thường hợp khi muốn **một giá trị U cho mỗi khóa K** và có chính sách rõ ràng khi trùng khóa.

Cả hai có thể tạo Map<String,Integer> tính tổng như chương trình demo, nhưng cấu trúc code khác:
- groupingBy + summingInt mô tả “nhóm rồi cộng mỗi nhóm”.
- toMap + Integer::sum mô tả “đưa từng key/value vào map và merge giá trị trùng key”.

Không có một cách luôn tốt hơn; hãy chọn cách diễn đạt đúng mục đích và ràng buộc về key, null, ordering, parallelism.

## 15. Biến kiểu trong một pipeline thay đổi sau mỗi phép map/flatMap

Xét:

~~~java
Stream<Order> first = orders.stream();

Stream<String> second = first.map(Order::customer);
~~~

Sau phép map, stream mới chứa String. Nếu muốn `map(Order::total)` trên stream `second`, compiler sẽ từ chối vì mapper đó cần Order chứ không phải String.

**Đừng tái sử dụng `first` sau intermediate/terminal chain** như thể mọi stream có thể chạy nhiều lần. Java streams là các pipeline tiêu thụ một lần; cách viết trên chỉ giúp nhìn kiểu. Trong code thật nên tạo pipeline mới từ collection nguồn cho một terminal operation mới.

Một ví dụ chuỗi đúng kiểu:

~~~java
List<Integer> lengths = orders.stream()
        .map(Order::customer)  // Stream<String>
        .map(String::length)   // Stream<Integer>
        .toList();             // List<Integer>
~~~

Cách đọc lỗi kiểu:
1. Ghi T của stream trước phép biến đổi.
2. Xem mapper nhận gì, trả gì.
3. Suy ra R và kiểu stream sau biến đổi.
4. Đối chiếu kiểu R đó với phép tiếp theo.
5. Ở collect, xem collector tiêu thụ kiểu nào và trả kiểu R tổng kết nào.

Compiler đôi lúc đưa lỗi dài về inference variable hoặc incompatible bounds; việc đặt biến trung gian với kiểu tường minh có thể giúp xác định bước nào sai.

## 16. Compiler inference và type witness khi generics trở nên khó đọc

Ví dụ từ `Stream.of`:

~~~java
Stream<String> names = Stream.of("A", "B");
List<Integer> sizes = names.map(String::length).toList();
~~~

Compiler suy luận T=String từ các literal và R=Integer từ mapper. Đa số code không cần tự viết type witness.

Nhưng với các mapper trả generic collection, những bước suy luận phức tạp có thể khiến compiler suy ra một supertype rộng hoặc báo lỗi nếu hai nhánh lambda không thống nhất:

~~~java
// Nếu muốn mọi phần tử đầu ra có kiểu CharSequence:
List<CharSequence> output = Stream.of("A", "B")
        .<CharSequence>map(s -> s)
        .toList();
~~~

`.<CharSequence>map(...)` chỉ rõ type argument R của generic method map. Đây là **explicit type witness**; dùng khi cần kiểm soát kiểu đầu ra hoặc hỗ trợ compiler trong tình huống khó suy luận.

Tuy nhiên, không dùng type witness để che một mapper sai thật. Ví dụ `flatMap` vẫn cần function trả Stream; khai báo R không thể biến một List tự động thành Stream.

Một lời nhắc khác: `var` chỉ yêu cầu compiler suy ra kiểu biểu thức, không biến một type thành raw. Nếu viết:

~~~java
var nested = orders.stream().map(Order::prices).toList();
~~~

kiểu được suy luận tương ứng `List<List<Integer>>` trong ví dụ; nó **không tự làm phẳng** chỉ vì không ghi kiểu tường minh.

## 17. Laziness, terminal operation và không được dùng lại Stream

`map` và `flatMap` thường không chạy mapper ngay khi khai báo pipeline:

~~~java
Stream<String> pipeline = Stream.of("A", "B")
        .map(s -> {
            System.out.println("mapped=" + s);
            return s.toLowerCase();
        });
~~~

Khi chỉ tạo `pipeline`, không có yêu cầu tính toàn bộ kết quả. Khi gọi:

~~~java
List<String> result = pipeline.toList();
~~~

pipeline được thực thi để tạo danh sách. Đừng bắt đầu một terminal operation thứ hai trên `pipeline` sau khi đã tiêu thụ nó.

Cần phân biệt:
- **Intermediate:** `map`, `flatMap`, `filter`, `peek`, `sorted`...
- **Terminal:** `collect`, `toList`, `forEach`, `count`, `reduce`, `findFirst`...

Các thao tác có thể được stream engine fuse hoặc tối ưu; đừng dựa vào side effects của mapper để đếm số lần xử lý trong mọi pipeline. Đặc biệt với short-circuit operations, có thể không cần chạy mapper trên mọi phần tử.

### flatMap và tài nguyên stream con

Nếu một mapper trả stream được xây từ nguồn tài nguyên cần đóng, cần hiểu trách nhiệm đóng tài nguyên của stream cha và mapped streams. `flatMap` đóng từng mapped stream sau khi sử dụng, nhưng quản lý nguồn như file lines, IO hoặc connection vẫn đòi thiết kế đúng và xử lý lỗi theo API nguồn. Không nên mở tài nguyên rồi giả định mọi pipeline chưa terminal sẽ tự giải phóng chúng đúng lúc.

## 18. Parallel Stream và Collector: đọc chữ ký chưa đủ cho correctness

Với `parallelStream`, collector có thể thực hiện accumulation theo nhiều nhánh và combine kết quả. Các ràng buộc quan trọng:

- Mapper/flatMapper nên **non-interfering**: không thay đổi nguồn stream trong khi xử lý.
- Lambda có state chia sẻ phải được đồng bộ phù hợp; nếu không, kết quả có thể race hoặc sai.
- `collect(supplier,accumulator,combiner)` đòi hành vi phù hợp với **identity/associativity** của mutable reduction.
- `groupingBy` thường không phải concurrent collector; khi cần shared concurrent accumulation, cân nhắc API như `groupingByConcurrent` với đúng đặc tính và yêu cầu thứ tự.
- Không kết luận rằng một Collector trả ArrayList nghĩa là framework cho nhiều thread đồng thời ghi vào **cùng một ArrayList không đồng bộ**. Reduction có thể dùng container riêng và kết hợp, theo hợp đồng collector.

Ví dụ thiết kế sai:

~~~java
List<String> global = new ArrayList<>();

// Dùng như sau là ý tưởng không an toàn cho parallel stream:
// orders.parallelStream().map(Order::customer).forEach(global::add);
~~~

Thay bằng terminal collection phù hợp:

~~~java
List<String> customers = orders.parallelStream()
        .map(Order::customer)
        .toList();
~~~

Khi cần thứ tự, xem rõ encounter order và semantics của collector. `TreeMap` trong chương trình demo chọn thứ tự key được xác định, không có nghĩa mọi stream parallel sẽ có thứ tự mọi side effect được bảo đảm.

## 19. Null và duplicate trong các Collector phổ biến

**Với `toMap`:** trong code mới, nên coi null keys/values là vấn đề cần hợp đồng rõ. Các collector/map implementation cụ thể có giới hạn riêng; tránh dựa vào việc một overload chấp nhận null trên một bản JDK rồi coi đó là API chung. Đặc biệt, các bản Java chuẩn có thể từ chối null values trong `Collectors.toMap` với NullPointerException.

**Với `groupingBy`:** classifier trả null key có thể bị implementation chuẩn của groupingBy từ chối; tốt hơn hãy chuẩn hóa key sang một giá trị cụ thể được nghiệp vụ chấp nhận.

**Với `toUnmodifiableList`:** phần tử null bị từ chối. `Stream.toList()` có hợp đồng List không cho sửa đổi; đừng nhầm điều đó với một validator nội dung tổng quát.

**Với duplicate keys:** `toMap(keyMapper,valueMapper)` không tự quyết định cộng hoặc lấy value đầu/last. Nó ném IllegalStateException cho duplicate, nên nếu key có thể lặp phải chọn overload có mergeFunction hoặc dùng groupingBy.

**Với `Collectors.toList`:** không hứa List kết quả mutable hay có lớp triển khai cụ thể. Cần ArrayList mutable thì dùng `toCollection(ArrayList::new)`.

Chính sách cụ thể cho null, duplicates, ordering và mutability là một phần của **thiết kế API**, không phải chuyện có thể giải quyết chỉ bằng generic type arguments.

## 20. Lỗi thường gặp khi đọc ba chữ ký

### 20.1. Dùng map nhưng tưởng trả stream phẳng

~~~java
Stream<List<Integer>> nested = orders.stream().map(Order::prices);

// Stream<Integer> wrong = orders.stream().map(Order::prices);
// Không biên dịch: mỗi mapper trả List<Integer>.
~~~

Sửa bằng `flatMap(o -> o.prices().stream())`.

### 20.2. Dùng flatMap với mapper chỉ trả List

~~~java
// orders.stream().flatMap(Order::prices); // Không hợp lệ.
~~~

Cần trả `Stream<? extends R>`. Sửa bằng `o -> o.prices().stream()`.

### 20.3. Coi A trong Collector<T,A,R> là kiểu output

`A` là loại container tích lũy trung gian, `R` mới là kiểu kết quả. `Collector<T,?,List<T>>` có dấu `?` ở A không làm đầu ra trở thành List<?>.

### 20.4. Coi R của map và R của collect là một biến cố định

Chúng là các type parameters **riêng trong mỗi generic method invocation**. `map` có thể cho `Stream<Integer>`; sau đó `collect` có thể trả `Map<String,Long>` hoặc `List<Integer>` tùy collector và pipeline. Không có một R chung tồn tại xuyên tất cả methods.

### 20.5. Dùng BiConsumer trong collect rồi mong có return value

Trong overload ba tham số, accumulator/combiner là **BiConsumer** và có return type void. Các method references `List::add`, `List::addAll` vốn trả boolean vẫn có thể dùng theo target void-compatible trong ngữ cảnh này; giá trị boolean bị bỏ qua. Logic phải sửa container, không phải trả container khác rồi mong framework tự dùng giá trị trả về.

### 20.6. Thiếu combiner đúng cho parallel stream

Một combiner rỗng có thể trông không sai khi code chạy tuần tự nhưng cho kết quả sai ở parallel stream. Chọn những phép gộp thỏa luật kết hợp và identity, hoặc dùng collector chuẩn.

### 20.7. Dùng toMap với key trùng

~~~java
// orders.stream().collect(Collectors.toMap(
//         Order::customer, Order::total));
// Có thể ném IllegalStateException khi customer lặp.
~~~

Chọn mergeFunction rõ ràng như `Integer::sum` hoặc groupingBy.

### 20.8. Mặc định Collectors.toList trả ArrayList mutable

Đây không phải bảo đảm của API. Dùng `toCollection(ArrayList::new)` khi cần loại collection cụ thể.

### 20.9. Tái dùng stream sau terminal operation

~~~java
Stream<String> names = Stream.of("A", "B");
names.collect(Collectors.toList());
// names.count(); // Không dùng lại stream đã tiêu thụ.
~~~

Tạo stream mới từ nguồn khi cần phép xử lý tiếp theo.

### 20.10. Quên primitive streams

`mapToInt`, `flatMapToInt`, `mapToLong`... khác chữ ký với `map/flatMap` thông thường. Nếu mục tiêu là phép cộng số nguyên, primitive streams có thể đơn giản và tránh boxing; nhưng không phải cách chọn mặc định cho mọi loại dữ liệu.

## 21. Quy trình tự đọc một pipeline phức tạp

Khi nhìn thấy một chuỗi `stream().filter(...).flatMap(...).map(...).collect(...)`, thực hiện theo thứ tự:

1. **Ghi T ban đầu**: chẳng hạn `Stream<Order>`.
2. **Đọc filter**: Predicate nhận được Order, stream vẫn là Stream<Order>.
3. **Đọc flatMap**: function nhận Order và trả Stream<Integer>; sau đó stream là Stream<Integer>.
4. **Đọc map**: nếu mapping Integer → String, stream là Stream<String>.
5. **Đọc collect**: collector nhận được String và trả R, ví dụ List<String> hoặc Map<String,Long>.
6. **Chú ý wildcards**: mapper có thể nhận supertype; đầu ra là subtype của R; đừng thay nó bằng cast/raw type.
7. **Nếu gặp lỗi compiler**: đặt biến intermediate có kiểu tường minh để cô lập bước inference gây lỗi.
8. **Nếu collector phức tạp**: ghi T, A, R ở mỗi collector và downstream; A thường bị ẩn bằng `?`.
9. **Kiểm tra tính đúng đắn khác type safety**: null, duplicate keys, ordering, parallel, side effects, mutability.
10. **Xác nhận bằng javac** với source release dự án. Một ví dụ Java 17 có thể dùng `Stream.toList()`, nhưng dự án Java 8 cần `collect(Collectors.toList())` hoặc cách phù hợp khác.

Đọc chữ ký method là bước đầu; hiểu hợp đồng của terminal operation và collector mới giúp biết **kết quả thực sự được tạo ra như thế nào**.

## 22. Câu hỏi tự kiểm tra

**1.** Với `Stream<String>` và `map(String::length)`, stream sau map có kiểu gì?

**Đáp án:** `Stream<Integer>`, vì `String.length()` trả int và được boxing thành Integer khi cần generic type argument R.

**2.** Vì sao `map(Order::prices)` cho `Stream<List<Integer>>`?

**Đáp án:** `Order::prices` trả đúng một List<Integer> cho mỗi Order, nên R là List<Integer>. map không tự lấy phần tử bên trong List.

**3.** Đổi kết quả đó thành `Stream<Integer>` bằng cách nào?

**Đáp án:** `flatMap(o -> o.prices().stream())`; mapper phải trả Stream<Integer>.

**4.** Chữ ký `Function<? super T, ? extends R>` cho phép điều gì?

**Đáp án:** Function nhận T hoặc supertype của T, và trả R hoặc subtype của R; thể hiện PECS cho đầu vào/đầu ra.

**5.** `flatMap` có nhất thiết trả đúng một kết quả cho mỗi T không?

**Đáp án:** Không. Stream con có thể rỗng, một phần tử hoặc nhiều phần tử, tạo 0..n kết quả.

**6.** `A` trong `Collector<? super T,A,R>` là gì?

**Đáp án:** Kiểu container tích lũy trung gian; không nhất thiết trùng R, là kiểu trả ra sau khi collector hoàn tất.

**7.** `collect(ArrayList::new,List::add,List::addAll)` dùng hai BiConsumer cho việc gì?

**Đáp án:** Accumulator thêm từng T vào container R; combiner ghép hai container R, cần thiết khi framework gộp kết quả.

**8.** Từ Stream<Order>, dùng `Collectors.groupingBy(Order::customer)` thì R là gì?

**Đáp án:** `Map<String,List<Order>>`, bởi classifier trả String và downstream mặc định nhóm các Order vào List<Order>.

**9.** Khi dùng `groupingBy(Order::customer, Collectors.summingInt(Order::total))`, kiểu value của Map là gì?

**Đáp án:** Integer, nên kết quả là Map<String,Integer> về mặt generic type.

**10.** Vì sao `Collectors.toMap(Order::customer,Order::total)` có thể ném IllegalStateException?

**Đáp án:** Hai order có cùng customer tạo duplicate key; overload hai mapper không có merge policy do caller cung cấp.

**11.** Muốn tổng giá trị cho từng customer bằng toMap, thêm gì?

**Đáp án:** MergeFunction như `Integer::sum`; có thể thêm mapFactory `TreeMap::new` để thứ tự key xác định.

**12.** `Collectors.mapping` khác `Stream.map` ở đâu?

**Đáp án:** Stream.map biến một Stream trung gian; Collectors.mapping là adapter Collector biến từng T thành U trước khi downstream accumulator nhận dữ liệu.

**13.** `Stream.toList()` khác `collect(Collectors.toList())` ra sao?

**Đáp án:** `Stream.toList()` bảo đảm List kết quả không cho sửa đổi (Java 16+), còn `Collectors.toList()` không cam kết cụ thể mutability hoặc implementation type.

**14.** Vì sao không nên gọi `forEach(sharedArrayList::add)` trên parallel stream?

**Đáp án:** Shared ArrayList không thread-safe cho concurrent additions; nên dùng collection terminal phù hợp và không có interfering side effects.

**15.** Compiler báo incompatible bounds trong một pipeline; cách kiểm tra đầu tiên nên là gì?

**Đáp án:** Ghi lại kiểu T trước mỗi intermediate operation, kiểu R do mapper trả, sau đó đối chiếu collector tiêu thụ kiểu nào. Dùng intermediate variables rõ kiểu để tìm đúng bước.

## 23. Ghi nhớ

Ba API làm việc ở **ba mức khác nhau**:

~~~text
Stream<T>
    ├─ map(Function<T,R>)                 → Stream<R>
    ├─ flatMap(Function<T,Stream<R>>)     → Stream<R>, nối các stream con
    └─ collect(Collector<T,A,R>)          → R, kết thúc pipeline
~~~

Những chữ ký ở sơ đồ đã lược bỏ wildcard để dễ nhớ; **chữ ký thực** dùng `? super` cho đầu vào tiêu thụ và `? extends` cho đầu ra được tạo.

- `map`: **một T → một R** theo mapping, không tự flatten.
- `flatMap`: **một T → Stream<R> → 0..n R**, làm phẳng một mức.
- `collect`: **Stream<T> → R**, dùng Collector hoặc supplier/accumulator/combiner; A là container trung gian khi dùng Collector.
- `groupingBy`, `mapping`, `flatMapping`, `toMap` là **collector factories/adapters**, không phải phương thức cùng loại với Stream.map/flatMap.
- **Type safety không thay thế behavioral correctness**: cần chú ý duplicate keys, null, ordering, mutability, short-circuit, parallel reduction và nguồn side effects.

Cách học hữu ích nhất là **đọc loại phần tử T tại mỗi bước**, theo dõi R của mapper, rồi đọc kết quả R của collector. Khi làm được điều này, các chữ ký generics dài trở thành sơ đồ luồng dữ liệu rõ ràng thay vì một chuỗi ký tự khó nhớ.
