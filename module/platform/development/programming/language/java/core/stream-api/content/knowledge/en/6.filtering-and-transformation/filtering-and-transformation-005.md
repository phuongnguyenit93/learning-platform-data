# So sánh flatMap và mapMulti theo hợp đồng và cách dùng

> **Chương:** Lọc và biến đổi phần tử  
> **Module:** JAVA_STREAM_API  
> **Phạm vi:** Java Stream API hỗ trợ pipeline xử lý dữ liệu khai báo, lazy evaluation, các thao tác `filter`/`map` và tổng hợp bằng `reduce`/`collect`. Bài này tập trung vào hai thao tác trung gian *biến một phần tử đầu vào thành không, một hoặc nhiều phần tử đầu ra*: `flatMap` và `mapMulti`.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích đúng hợp đồng đầu vào/đầu ra và khác biệt giữa `map`, `flatMap` và `mapMulti`.
2. Viết hai pipeline cho cùng một bài toán, dùng `flatMap` hoặc `mapMulti`, và giải thích vì sao kết quả giống nhau.
3. Biết `flatMap` có từ Java 8, `mapMulti` và các biến thể liên quan được bổ sung ở Java 16.
4. Xử lý các trường hợp phát ra **0, 1 hoặc nhiều giá trị**, có điều kiện lọc, và dữ liệu lồng nhau.
5. Hiểu cách tạo và đóng Stream con, vòng đời của `Consumer` nhận kết quả, lazy evaluation và short-circuit.
6. Xử lý kiểu generic, primitive stream, encounter order, song song và các chi phí hiệu năng cần đo đạc.

Các ví dụ chính dùng Java 17+, vì `mapMulti` và `Stream.toList()` yêu cầu Java 16+. Với Java 8–15, dùng `flatMap` và `collect(Collectors.toList())` theo phiên bản JDK hiện có.

## 1. Vì sao cần flatMap hoặc mapMulti?

`map` biến mỗi phần tử đầu vào thành đúng **một** giá trị đầu ra. Nếu mỗi phần tử tự chứa một danh sách con, `map` thường tạo Stream của các danh sách thay vì Stream của từng phần tử bên trong.

~~~java
import java.util.List;

List<List<String>> groups = List.of(
        List.of("An", "Bình"),
        List.of("Chi"),
        List.of("Dũng", "Hà")
);

List<List<String>> nested = groups.stream()
        .map(group -> group) // Mỗi List con vẫn là một phần tử
        .toList();

System.out.println(nested);
// [[An, Bình], [Chi], [Dũng, Hà]]
~~~

Nếu cần một danh sách tên duy nhất theo thứ tự, chúng ta cần **mở rộng/flatten** dữ liệu.

~~~text
Nguồn:
    [ ["An", "Bình"], ["Chi"], ["Dũng", "Hà"] ]

map(List::stream):
    Stream<Stream<String>>      (vẫn còn cấu trúc lồng)

flatMap(List::stream):
    Stream<String>              "An", "Bình", "Chi", "Dũng", "Hà"

mapMulti((group, out) -> group.forEach(out)):
    Stream<String>              "An", "Bình", "Chi", "Dũng", "Hà"
~~~

Dễ ghi nhớ qua số lượng phần tử:

| Phép biến đổi | Một phần tử đầu vào tạo ra | Dạng hàm chủ đạo |
|---|---|---|
| `map` | Một phần tử | `T -> R` |
| `filter` | Giữ lại hoặc loại bỏ phần tử đầu vào | `T -> boolean` |
| `flatMap` | Không, một hoặc nhiều phần tử | `T -> Stream<R>` |
| `mapMulti` | Không, một hoặc nhiều phần tử | `(T, Consumer<R>) -> void` |

`flatMap` và `mapMulti` đều phù hợp cho bài toán **một thành nhiều**, nhưng cách mapper cung cấp kết quả là khác nhau.

## 2. Hợp đồng API: phần khác nhau quan trọng nhất

### 2.1. flatMap trả về một Stream con

Chữ ký rút gọn của `Stream<T>`:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper
);
~~~

Mỗi khi mapper được gọi với một phần tử `T`, nó cung cấp một **Stream con** chứa các phần tử kiểu `R`. Thư viện Stream đưa các phần tử từ những Stream con đó vào pipeline kết quả. Về mặt khái niệm:

~~~text
             mapper(T) trả về Stream<R>
 T1 ───────────────> [R1, R2]
 T2 ───────────────> []
 T3 ───────────────> [R3]
                         │
                    nối phẳng
                         ▼
                     R1, R2, R3
~~~

Các điểm trong hợp đồng:

- `flatMap` là **thao tác trung gian** (*intermediate operation*) và có tính lazy như các thao tác trung gian Stream thông thường.
- Mapper cần **non-interfering** (không can thiệp vào nguồn đang duyệt) và **stateless** (không phụ thuộc trạng thái thay đổi khi chạy).
- Mapper có thể trả `Stream.empty()` để phát ra **không phần tử**. Theo hợp đồng `flatMap`, nếu mapper trả `null`, kết quả được xem là một Stream rỗng; tuy vậy, dùng `Stream.empty()` thể hiện ý định rõ hơn.
- **Mỗi Stream con được đóng** sau khi các phần tử của nó được đưa vào pipeline kết quả theo hợp đồng `flatMap`. Điểm này quan trọng nếu Stream con giữ tài nguyên như tệp.
- Stream con có thể được xây từ collection, mảng, `Stream.of(...)`, nguồn sinh dữ liệu hoặc một nguồn I/O thích hợp.

### 2.2. mapMulti phát trực tiếp giá trị vào Consumer

Chữ ký rút gọn của `Stream<T>`:

~~~java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper
);
~~~

Khác với `flatMap`, mapper của `mapMulti` **không trả một Stream con**. Thư viện gọi mapper với:

1. Phần tử đầu vào `T`.
2. Một `Consumer<R>` do pipeline cung cấp, dùng để **phát** giá trị đầu ra.

Mapper gọi `downstream.accept(value)` **0, 1 hoặc nhiều lần**.

~~~text
             mapper(T, downstream)
 T1 ───────> downstream.accept(R1)
             downstream.accept(R2)

 T2 ───────> (không gọi accept)

 T3 ───────> downstream.accept(R3)
                           │
                           ▼
                        R1, R2, R3
~~~

Các điểm trong hợp đồng:

- `mapMulti` là **thao tác trung gian**, xử lý dữ liệu theo pipeline và không tạo một terminal operation mới.
- Mapper phải **non-interfering** và **stateless**, giống các hành vi được yêu cầu ở các pipeline Stream thông thường.
- Mapper nhận một `Consumer` dành cho **lần gọi đó**. Theo hợp đồng, `Consumer` được cấp **chỉ dùng trong phạm vi lời gọi mapper hiện tại**; không lưu giữ nó vào field, list, callback chạy sau hoặc thread khác.
- Mapper không dùng giá trị trả về để phát kết quả. **Mỗi lời gọi `accept`** đưa ra một giá trị ứng viên cho phần còn lại của pipeline.
- `mapMulti` không yêu cầu tạo `Stream` con ở phía người gọi, nên thuận tiện khi phát một số ít giá trị hoặc khi logic mở rộng dùng vòng lặp và điều kiện.

Về phiên bản, `Stream.mapMulti` được giới thiệu ở **Java 16**. `flatMap` có từ **Java 8**, vì vậy yêu cầu tương thích JDK là một tiêu chí lựa chọn rõ ràng.

### 2.3. Hai cú pháp, một kết quả

~~~java
import java.util.List;

List<List<String>> groups = List.of(
        List.of("An", "Bình"),
        List.of(),
        List.of("Chi", "Dũng")
);

List<String> withFlatMap = groups.stream()
        .flatMap(List::stream)
        .toList();

List<String> withMapMulti = groups.stream()
        .<String>mapMulti((group, downstream) -> {
            group.forEach(downstream);
        })
        .toList();

System.out.println(withFlatMap);  // [An, Bình, Chi, Dũng]
System.out.println(withMapMulti); // [An, Bình, Chi, Dũng]
~~~

Ở cách `flatMap`, mỗi `List` được biến thành một Stream con bằng `List::stream`. Ở cách `mapMulti`, từng phần tử trong danh sách con được truyền cho `downstream.accept(...)` (ẩn trong `forEach` của `List`).

Ký hiệu `.<String>mapMulti(...)` là **type witness**, giúp Java suy luận kiểu đầu ra `R` là `String`. Phần này sẽ được giải thích kỹ ở mục 7.

## 3. Khi nào dùng map, filter, flatMap hoặc mapMulti?

Không cần dùng `flatMap` hoặc `mapMulti` cho mọi biến đổi.

~~~java
import java.util.List;

List<String> names = List.of(" An ", "", " Bình ", " ");

List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();

System.out.println(cleaned); // [An, Bình]
~~~

Đây là cách rõ nhất để biến đổi từng tên và lọc tên rỗng. Có thể viết một `mapMulti` tương đương:

~~~java
import java.util.List;

List<String> names = List.of(" An ", "", " Bình ", " ");

List<String> cleaned = names.stream()
        .<String>mapMulti((rawName, out) -> {
            String name = rawName.trim();
            if (!name.isEmpty()) {
                out.accept(name);
            }
        })
        .toList();

System.out.println(cleaned); // [An, Bình]
~~~

Cách này phát **0 hoặc 1** phần tử trên mỗi đầu vào. Nó hữu ích khi nhiều điều kiện phụ thuộc nhau hoặc việc chuyển đổi có thể phát nhiều kết quả. Với trường hợp đơn giản ở trên, `map` + `filter` thường dễ đọc hơn.

Để hiểu sự khác biệt, đừng chỉ nhìn số dòng. Hãy hỏi: **mỗi phần tử có sinh ra một cấu trúc Stream con tự nhiên hay có logic phát nhiều giá trị từng bước?**

## 4. Ví dụ thực tế: chuyển một đơn hàng thành nhiều dòng sản phẩm

Giả sử mỗi đơn hàng chứa nhiều mặt hàng. Ta muốn lấy mã của các mặt hàng có số lượng lớn hơn 0, và bỏ các đơn hàng không có dòng hợp lệ.

Định nghĩa dữ liệu:

~~~java
import java.util.List;

record Item(String sku, int quantity) {}
record Order(String id, List<Item> items) {}

List<Order> orders = List.of(
        new Order("O-01", List.of(
                new Item("BOOK", 2),
                new Item("PEN", 0))),
        new Order("O-02", List.of(
                new Item("BAG", 1),
                new Item("PEN", 3))),
        new Order("O-03", List.of())
);
~~~

### 4.1. Giải pháp bằng flatMap

~~~java
import java.util.List;

List<String> skus = orders.stream()
        .flatMap(order -> order.items().stream()
                .filter(item -> item.quantity() > 0)
                .map(Item::sku))
        .toList();

System.out.println(skus); // [BOOK, BAG, PEN]
~~~

Mapper của `flatMap` tạo một pipeline Stream con từ các mặt hàng trong **mỗi** đơn hàng. Stream con được lọc và ánh xạ trước khi kết quả được nối phẳng.

### 4.2. Giải pháp bằng mapMulti

~~~java
import java.util.List;

List<String> skus = orders.stream()
        .<String>mapMulti((order, out) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    out.accept(item.sku());
                }
            }
        })
        .toList();

System.out.println(skus); // [BOOK, BAG, PEN]
~~~

Đoạn này **không cần tạo một đối tượng Stream con cho từng đơn hàng trong mã mapper**. Logic điều kiện và phát phần tử được viết rõ bên trong lambda. Nếu một đơn hàng rỗng, mapper không gọi `out.accept`, do đó đơn hàng ấy đóng góp 0 kết quả.

Hai kết quả tương đương với giả định đầu vào như nhau và mapper không có tác dụng phụ. Cách chọn phụ thuộc vào tính tự nhiên của nguồn con, độ rõ ràng, tương thích JDK và đặc điểm hiệu năng khi chạy thực tế.

## 5. Các trường hợp 0, 1 và nhiều đầu ra

### 5.1. Không phát gì: biểu đạt lọc

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> source = List.of(3, 6, 9, 12);

List<Integer> viaFlatMap = source.stream()
        .flatMap(n -> n % 2 == 0 ? Stream.of(n) : Stream.empty())
        .toList();

List<Integer> viaMapMulti = source.stream()
        .<Integer>mapMulti((n, out) -> {
            if (n % 2 == 0) {
                out.accept(n);
            }
        })
        .toList();

System.out.println(viaFlatMap);  // [6, 12]
System.out.println(viaMapMulti); // [6, 12]
~~~

Với nghiệp vụ chỉ kiểm tra điều kiện, viết `source.stream().filter(n -> n % 2 == 0)` sẽ đơn giản hơn. Ví dụ này chỉ minh họa cách mapper **không phát** phần tử.

### 5.2. Phát đúng một phần tử: dạng chuyển đổi

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = List.of(1, 2, 3);

List<Integer> viaFlatMap = values.stream()
        .flatMap(n -> Stream.of(n * n))
        .toList();

List<Integer> viaMapMulti = values.stream()
        .<Integer>mapMulti((n, out) -> out.accept(n * n))
        .toList();

System.out.println(viaFlatMap);  // [1, 4, 9]
System.out.println(viaMapMulti); // [1, 4, 9]
~~~

Trong trường hợp **1 đầu vào → 1 đầu ra**, `map(n -> n * n)` rõ nghĩa hơn cả hai.

### 5.3. Phát nhiều phần tử: mở rộng

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> quantities = List.of(1, 3, 2);

// Mỗi số n được lặp lại n lần.
List<Integer> viaFlatMap = quantities.stream()
        .flatMap(n -> IntStream.range(0, n).mapToObj(i -> n))
        .toList();

List<Integer> viaMapMulti = quantities.stream()
        .<Integer>mapMulti((n, out) -> {
            for (int i = 0; i < n; i++) {
                out.accept(n);
            }
        })
        .toList();

System.out.println(viaFlatMap);  // [1, 3, 3, 3, 2, 2]
System.out.println(viaMapMulti); // [1, 3, 3, 3, 2, 2]
~~~

Với số lượng mở rộng nhỏ và vòng lặp đơn giản, `mapMulti` thường là lựa chọn gọn và trực tiếp. Với nguồn con đã sẵn dưới dạng Stream hoặc cần tổ hợp các thao tác trên nguồn con, `flatMap` thường thuận tiện hơn.

## 6. Dữ liệu lồng nhau, Optional và cấu trúc phân cấp

### 6.1. Flatten Optional

`Optional.stream()` (Java 9+) trả về Stream có 0 phần tử nếu `Optional.empty()`, hoặc 1 phần tử nếu có giá trị.

~~~java
import java.util.List;
import java.util.Optional;

List<Optional<Integer>> options = List.of(
        Optional.of(7),
        Optional.empty(),
        Optional.of(11)
);

List<Integer> withFlatMap = options.stream()
        .flatMap(Optional::stream)
        .toList();

List<Integer> withMapMulti = options.stream()
        .<Integer>mapMulti((option, out) -> option.ifPresent(out))
        .toList();

System.out.println(withFlatMap);  // [7, 11]
System.out.println(withMapMulti); // [7, 11]
~~~

Đây là một trường hợp đối chiếu rất rõ: ở `flatMap`, `Optional` cung cấp Stream con; ở `mapMulti`, `ifPresent` quyết định có gọi `accept` hay không.

### 6.2. Cấu trúc lồng nhiều cấp

Giả sử một danh mục có thể chứa danh mục con hoặc một mã sản phẩm. Muốn thu thập tất cả mã sản phẩm theo thứ tự duyệt trước sâu (*depth-first*).

~~~java
import java.util.List;
import java.util.function.Consumer;
import java.util.stream.Stream;

class TreeExample {
    static void emitLeaves(Object node, Consumer<String> out) {
        if (node instanceof String text) {
            out.accept(text);
        } else if (node instanceof List<?> children) {
            for (Object child : children) {
                emitLeaves(child, out);
            }
        }
    }

    public static void main(String[] args) {
        List<Object> source = List.of(
                "A",
                List.of("B", List.of("C", "D")),
                "E"
        );

        List<String> leaves = source.stream()
                .<String>mapMulti(TreeExample::emitLeaves)
                .toList();

        System.out.println(leaves); // [A, B, C, D, E]
    }
}
~~~

Hàm `emitLeaves` xử lý đệ quy: mỗi node có thể phát ra 0 hoặc nhiều chuỗi. Mẫu này phù hợp khi thuật toán mở rộng đã có phong cách **phát kết quả vào Consumer**.

Với `flatMap`, có thể viết một hàm tạo Stream đệ quy và `flatMap` trên các node con. Cách ấy hợp lý nếu muốn duy trì mô hình **mỗi node là một Stream kết quả**. Với cây cực sâu, cả hai cách đệ quy đều cần tính đến giới hạn stack; `mapMulti` không tự giải quyết vấn đề tràn stack.

## 7. Suy luận kiểu generic: vì sao mapMulti đôi khi cần type witness?

Trong `flatMap`, mapper **trả về một `Stream<R>`**, nên trình biên dịch thường có đủ thông tin để suy ra `R`. Trong `mapMulti`, mapper trả `void` và chỉ đưa giá trị vào một `Consumer<R>`; đôi khi Java suy ra `R` quá rộng, chẳng hạn `Object`.

### 7.1. Cách viết an toàn, dễ đọc

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> {
            if (n > 1) {
                out.accept(n * 10);
            }
        })
        .toList();

System.out.println(values); // [20, 30]
~~~

`.<Integer>mapMulti(...)` ghi rõ tham số kiểu `R`. Nếu thiếu type witness, trình biên dịch có thể suy luận `Stream<Object>`; việc gán kết quả `toList()` cho `List<Integer>` sẽ lỗi kiểu.

### 7.2. Một số cách khác

Có thể gán kết quả của `mapMulti` vào một biến có kiểu cụ thể trước khi gọi `toList()`:

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> stream = Stream.of(1, 2, 3)
        .mapMulti((n, out) -> out.accept(n));

List<Integer> values = stream.toList();
System.out.println(values); // [1, 2, 3]
~~~

Ngữ cảnh `Stream<Integer>` giúp trình biên dịch xác định `R`. Khi chuỗi phương thức dài, type witness ngay tại `mapMulti` thường dễ hiểu hơn.

Cũng có thể viết lambda với kiểu tham số tường minh theo functional interface thực tế, nhưng cần khai báo kiểu nhất quán. Thông thường, **type witness** ngắn gọn nhất và ít rủi ro hơn việc ép kiểu `(Integer) value` ở từng lời gọi `accept`.

### 7.3. Đừng nhầm với kiểu đầu vào

Trong pipeline:

~~~java
List<String> names = List.of("An", "Bình");

List<Integer> lengths = names.stream()
        .<Integer>mapMulti((name, out) -> out.accept(name.length()))
        .toList();
~~~

`T` là `String` từ nguồn, còn `R` là `Integer` được phát ra. Type witness ở `mapMulti` chỉ xác định kiểu **đầu ra**, không đổi kiểu đầu vào.

## 8. Các biến thể primitive: tránh boxing khi phù hợp

`Stream<T>` có các biến thể:

| API | Đầu ra | Khi phù hợp |
|---|---|---|
| `flatMap(Function<T, Stream<R>>)` | `Stream<R>` | Nguồn con là Stream đối tượng |
| `flatMapToInt` / `flatMapToLong` / `flatMapToDouble` | `IntStream` / `LongStream` / `DoubleStream` | Mapper trả nguồn con primitive stream |
| `mapMulti(BiConsumer<T, Consumer<R>>)` | `Stream<R>` | Phát đối tượng trực tiếp |
| `mapMultiToInt` / `mapMultiToLong` / `mapMultiToDouble` | Primitive stream tương ứng | Phát số nguyên/thực trực tiếp qua primitive consumer |

Các chữ ký trong bảng chỉ mang tính diễn giải: chữ ký thật có generic wildcard `? super` và `? extends`.

### 8.1. Tách và cộng các số trong chuỗi

~~~java
import java.util.Arrays;
import java.util.List;

List<String> lines = List.of("4,7", "3", "2, 6");

int viaFlatMap = lines.stream()
        .flatMapToInt(line -> Arrays.stream(line.split(","))
                .map(String::trim)
                .filter(part -> !part.isEmpty())
                .mapToInt(Integer::parseInt))
        .sum();

int viaMapMulti = lines.stream()
        .mapMultiToInt((line, out) -> {
            for (String part : line.split(",")) {
                String token = part.trim();
                if (!token.isEmpty()) {
                    out.accept(Integer.parseInt(token));
                }
            }
        })
        .sum();

System.out.println(viaFlatMap);  // 22
System.out.println(viaMapMulti); // 22
~~~

Đây là hai cách từ `Stream<String>` sinh ra `IntStream`, rồi dùng terminal operation `sum()`.

Dữ liệu giả định mọi token không rỗng là số nguyên hợp lệ; `Integer.parseInt` có thể ném `NumberFormatException` khi token sai hoặc vượt giới hạn `int`. Với dữ liệu bên ngoài, cần chính sách rõ: từ chối bản ghi, ghi nhận lỗi hoặc cho phép bỏ qua. Không nên âm thầm bỏ lỗi trừ khi đó là yêu cầu nghiệp vụ.

### 8.2. IntStream.mapMulti

Các primitive stream cũng có thao tác `mapMulti` riêng. Ví dụ `IntStream.mapMulti(IntStream.IntMapMultiConsumer)` phát nhiều giá trị kiểu `int`:

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] expanded = IntStream.of(1, 3, 2)
        .mapMulti((value, out) -> {
            for (int i = 0; i < value; i++) {
                out.accept(value);
            }
        })
        .toArray();

System.out.println(Arrays.toString(expanded));
// [1, 3, 3, 3, 2, 2]
~~~

Đây là `IntStream.mapMulti`, **khác với** `Stream<T>.mapMultiToInt`:

- `Stream<T>.mapMultiToInt`: nguồn chứa đối tượng `T`, kết quả là `IntStream`.
- `IntStream.mapMulti`: nguồn đã là `IntStream`, kết quả vẫn là `IntStream`.

Nếu xử lý khối lượng lớn giá trị số, tránh boxing/unboxing có thể có ích. Tuy vậy, đừng giả định một biến thể luôn nhanh hơn mà chưa đo trong bối cảnh thực tế.

## 9. Tài nguyên và vòng đời Stream con

Khác biệt về vòng đời là một lý do quan trọng để chọn API.

### 9.1. flatMap có hợp đồng đóng Stream con

Khi `flatMap` nhận một Stream con từ mapper, Stream API có trách nhiệm đóng Stream con đó theo hợp đồng của `flatMap` khi xử lý nội dung Stream con.

Ví dụ: gộp nhiều tệp văn bản vào một pipeline:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

List<Path> paths = List.of(
        Path.of("application-1.log"),
        Path.of("application-2.log")
);

try (Stream<String> allLines = paths.stream()
        .flatMap(path -> {
            try {
                return Files.lines(path, StandardCharsets.UTF_8);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })) {

    long errors = allLines
            .filter(line -> line.contains("ERROR"))
            .count();

    System.out.println("Số dòng ERROR: " + errors);
} catch (UncheckedIOException ex) {
    System.err.println("Đọc log thất bại: " + ex.getMessage());
}
~~~

Lưu ý:

1. `Files.lines` trả về Stream lấy dữ liệu từ tệp và giữ tài nguyên cần đóng.
2. `flatMap` nối phẳng các Stream con và chịu trách nhiệm đóng chúng theo hợp đồng.
3. `try-with-resources` đóng **Stream kết quả** khi rời phạm vi sử dụng, đặc biệt cần thiết nếu bản thân pipeline còn sở hữu tài nguyên hoặc có close handler.
4. `IOException` khi mở tệp được chuyển thành `UncheckedIOException` để truyền qua lambda; lỗi I/O khi đang tiêu thụ Stream cũng có thể phát sinh dưới dạng `UncheckedIOException`.
5. Dù `count()` là terminal operation, **đừng mặc định terminal operation tự đóng toàn bộ Stream**. Chủ động quản lý vòng đời đối với Stream có nguồn I/O.

Không nên lấy ví dụ này làm lý do để mở nhiều tệp tùy ý đồng thời: với pipeline tuần tự, Stream con có thể được mở và xử lý lần lượt; với pipeline song song, cách sử dụng tài nguyên cần được xem xét theo thực tế.

### 9.2. mapMulti không có Stream con để tự động đóng

`mapMulti` chỉ cấp một `Consumer` để phát giá trị. Nếu bạn tự mở `Reader`, kết nối hoặc `Stream` I/O bên trong mapper, **chính mã mapper phải quản lý tài nguyên đó**; không có một Stream con được trả về để `mapMulti` tự áp dụng hợp đồng đóng của `flatMap`.

Mã minh họa — **chỉ** thích hợp khi cố ý đọc hết nguồn con trong từng lần gọi mapper:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

List<Path> files = List.of(Path.of("application-1.log"));

List<String> nonBlankLines = files.stream()
        .<String>mapMulti((path, out) -> {
            try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (!line.isBlank()) {
                        out.accept(line);
                    }
                }
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .toList();
~~~

Ở đây `try-with-resources` đóng `reader`, nhưng vòng đọc thủ công trong mapper có thể tiếp tục đọc hết tệp ngay cả khi downstream đã đủ kết quả để dừng sớm. Nếu cần pipeline xử lý dòng theo nhu cầu với `limit` hoặc `findFirst`, **`flatMap` trả Stream con từ `Files.lines` thường tự nhiên hơn**. Vấn đề này dẫn đến khác biệt tiếp theo.

## 10. Lazy evaluation và short-circuit: điều gì không được đảm bảo?

Cả `flatMap` và `mapMulti` đều lazy ở cấp **thao tác trung gian**: gọi chúng để xây pipeline chưa tự động xử lý hết nguồn. Khi một terminal operation như `toList`, `count`, `findFirst` hoặc `anyMatch` bắt đầu, thư viện mới tiêu thụ pipeline theo nhu cầu và những tối ưu hợp lệ.

Với `flatMap`, mapper cung cấp một Stream con có khả năng duyệt từng phần tử. Một pipeline có `limit(2)` có thể không cần lấy hết mọi phần tử của Stream con.

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

List<String> firstTwo = Stream.of("x")
        .flatMap(prefix ->
                IntStream.range(0, 1_000)
                        .mapToObj(i -> prefix + i))
        .limit(2)
        .toList();

System.out.println(firstTwo); // [x0, x1]
~~~

Với `mapMulti`, mã mapper nhận một `Consumer` có phương thức `accept` nhưng **không có một tín hiệu dừng chuẩn** để mapper hỏi downstream rằng đã cần thêm phần tử hay chưa.

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> firstTwo = Stream.of("x")
        .<String>mapMulti((prefix, out) -> {
            for (int i = 0; i < 1_000; i++) {
                out.accept(prefix + i);
            }
        })
        .limit(2)
        .toList();

System.out.println(firstTwo); // [x0, x1]
~~~

Kết quả cuối cùng vẫn có hai phần tử, nhưng **đừng suy ra mapper chỉ chạy hai lượt vòng lặp**: mapper có thể phát nhiều hơn số giá trị downstream tiêu thụ, và triển khai mặc định của `mapMulti` có thể phải đệm kết quả nội bộ.

Hệ quả khi thiết kế:

- Với phần mở rộng **hữu hạn, nhỏ**, `mapMulti` rất phù hợp.
- Với nguồn con **rất lớn, tính dần hoặc vô hạn**, `flatMap` với Stream con lazy thường dễ tận dụng short-circuit hơn.
- Đừng đặt vòng lặp vô hạn trong mapper `mapMulti` rồi kỳ vọng `limit` tự ngắt vòng lặp bên trong; mapper không có API cancellation cho `Consumer`.
- Không viết logic nghiệp vụ phụ thuộc vào số lần một lambda trung gian đã được gọi: Stream API được phép tối ưu việc thực thi khi vẫn giữ kết quả được quy định.

## 11. Thứ tự phần tử, song song và side effect

### 11.1. Encounter order

Nếu nguồn có **encounter order** (chẳng hạn `List.stream()`) và pipeline không bỏ thứ tự bằng `unordered()`, cả `flatMap` và `mapMulti` đều hướng tới kết quả theo thứ tự gặp phần tử, cùng thứ tự phát bên trong mỗi đầu vào.

~~~java
import java.util.List;

List<String> rows = List.of("A,B", "C,D");

List<String> tokens = rows.stream()
        .<String>mapMulti((row, out) -> {
            for (String token : row.split(",")) {
                out.accept(token);
            }
        })
        .toList();

System.out.println(tokens); // [A, B, C, D]
~~~

Không phải nguồn nào cũng có encounter order: ví dụ một `HashSet` không đảm bảo thứ tự duyệt cụ thể. `forEach` trên Stream song song cũng không bảo đảm thứ tự thực thi; nếu thật sự cần thứ tự đầu ra khi thực hiện side effect, xem xét `forEachOrdered` và tác động hiệu năng tương ứng.

### 11.2. Parallel stream không thay đổi hợp đồng hàm hành vi

~~~java
import java.util.List;

List<List<Integer>> groups = List.of(
        List.of(1, 2),
        List.of(3),
        List.of(4, 5)
);

List<Integer> result = groups.parallelStream()
        .<Integer>mapMulti((group, out) -> {
            for (int number : group) {
                out.accept(number * 10);
            }
        })
        .toList();

System.out.println(result); // [10, 20, 30, 40, 50]
~~~

Đây là biến đổi độc lập của từng nhóm. Pipeline có nguồn có thứ tự và `toList()` giữ thứ tự gặp phần tử. Tuy nhiên, thứ tự **chạy** lambda trên các thread có thể khác thứ tự **kết quả**.

Một lỗi thường gặp là đẩy kết quả vào collection dùng chung:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

// Không nên: nhiều thread có thể sửa ArrayList cùng lúc.
// groups.parallelStream().forEach(group -> shared.addAll(group));
~~~

`ArrayList` thông thường không thread-safe. Thay bằng `flatMap` hoặc `mapMulti` để tạo pipeline kết quả, sau đó dùng `toList` hay collector thích hợp.

Đừng lưu `out` trong `mapMulti` để gọi trong một thread khác:

~~~java
// Sai với hợp đồng mapMulti:
// Stream.of(1, 2).<Integer>mapMulti((n, out) -> {
//     new Thread(() -> out.accept(n)).start();
// });
~~~

Consumer do `mapMulti` cung cấp chỉ được dùng **trong chính lời gọi mapper**, không được đưa vào công việc bất đồng bộ chạy sau khi mapper trả về.

### 11.3. Đếm và tổng hợp bằng terminal operation

~~~java
import java.util.List;

List<List<Integer>> groups = List.of(
        List.of(2, 4),
        List.of(1, 3, 5)
);

int sum = groups.stream()
        .flatMap(List::stream)
        .mapToInt(Integer::intValue)
        .sum();

long count = groups.stream()
        .<Integer>mapMulti((group, out) -> group.forEach(out))
        .count();

System.out.println(sum);   // 15
System.out.println(count); // 5
~~~

Bài toán tổng hợp nên để `sum`, `count`, `reduce` hoặc `collect` thực hiện thay vì sửa một biến cộng dồn dùng chung từ bên trong mapper. Điều này đặc biệt quan trọng với parallel stream và những pipeline có short-circuit.

## 12. Hiệu năng: mapMulti có luôn nhanh hơn flatMap không?

**Không có bảo đảm chung** rằng `mapMulti` luôn nhanh hơn `flatMap`. Tài liệu API mô tả `mapMulti` là phương án thay thế hữu ích khi mỗi đầu vào sinh ra **một số ít** phần tử, nhằm tránh việc tạo một Stream mới trong mapper cho mỗi đầu vào và thuận tiện cho các thuật toán phát kết quả.

Nhưng cần phân biệt **ý định API** và **cách triển khai**:

- `flatMap` diễn đạt trực tiếp việc xử lý các Stream con, có chi phí xây và quản lý chúng tùy pipeline và tối ưu của JDK.
- `mapMulti` không buộc mã mapper tạo Stream con, nhưng **hợp đồng không cam kết không cấp phát bộ nhớ hoặc không dùng buffer**. Triển khai mặc định được mô tả trong Javadoc có thể gom các giá trị phát ra vào bộ đệm nội bộ rồi thực hiện `flatMap`.
- Tính lazy ở cấp pipeline **không bảo đảm** mỗi phép mở rộng sinh kết quả tức thì mà không lưu đệm.
- Khi sinh rất nhiều đầu ra từ một phần tử, chi phí lưu đệm/bộ nhớ và khả năng dừng sớm có thể quan trọng hơn việc tránh tạo Stream con.
- Khi dùng primitive stream, boxing/unboxing, phép phân tích chuỗi, cấp phát object hoặc thao tác I/O có thể chi phối tổng thời gian hơn sự khác nhau giữa `flatMap` và `mapMulti`.
- Khi chạy song song, hiệu quả còn phụ thuộc nguồn có chia nhỏ tốt không (liên quan `Spliterator`), chi phí phối hợp thread, tính kết hợp của phép tổng hợp và việc truy cập tài nguyên.

| Dạng công việc | Điều cần quan sát khi đo |
|---|---|
| Nhiều đầu vào, mỗi đầu vào sinh 0–2 phần tử | Chi phí tạo Stream con, cấp phát, GC |
| Nhiều đầu vào, mỗi đầu vào sinh hàng nghìn phần tử | Bộ nhớ đệm, khả năng tiêu thụ dần |
| Có `limit` hoặc `findFirst` | Có thể dừng bao nhiêu công việc ở nguồn con? |
| Xử lý số lượng lớn `int` hoặc `long` | Primitive stream và boxing/unboxing |
| Đọc file hoặc dữ liệu mạng | I/O, số tài nguyên đang mở, đóng tài nguyên |
| `parallel()` / `parallelStream()` | Kích thước bài toán, phân chia `Spliterator`, thứ tự, overhead |

Nếu cần kết luận hiệu năng cho ứng dụng, đo với dữ liệu và JDK thực tế, có warm-up/JMH phù hợp, kiểm soát đầu ra để tránh tối ưu loại bỏ công việc và theo dõi cấp phát hoặc GC. **Chọn API trước hết theo hợp đồng và tính rõ ràng**, sau đó mới tối ưu dựa trên số liệu.

## 13. Các lỗi hay gặp và cách sửa

### Lỗi 1: tưởng map tạo các phần tử phẳng

~~~java
import java.util.List;

List<List<Integer>> groups = List.of(List.of(1, 2), List.of(3));

var nested = groups.stream()
        .map(List::stream)
        .toList(); // List<Stream<Integer>>, chưa phải List<Integer>
~~~

Sửa bằng `flatMap(List::stream)` hoặc `.<Integer>mapMulti((group, out) -> group.forEach(out))`.

### Lỗi 2: cố trả Stream từ mapper của mapMulti

~~~java
// Sai về chữ ký: mapMulti yêu cầu BiConsumer, hàm trả void.
// groups.stream().mapMulti(group -> group.stream());
~~~

`mapMulti` nhận **hai tham số** trong lambda: phần tử đầu vào và `Consumer` đầu ra. Nếu cần trả Stream con, dùng `flatMap`.

### Lỗi 3: không chốt kiểu đầu ra khi suy luận generic không đủ

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> result = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> out.accept(n))
        .toList();
~~~

Type witness `<Integer>` xác định kiểu `R` của `mapMulti` và tránh lỗi `List<Object>` ở một số bối cảnh suy luận kiểu.

### Lỗi 4: giữ lại downstream Consumer

~~~java
// Sai hợp đồng:
// Consumer<Integer>[] holder = ...
// stream.<Integer>mapMulti((n, out) -> holder[0] = out);
// holder[0].accept(10); // Sử dụng ngoài lời gọi mapper
~~~

Sửa bằng cách gọi `accept` **ngay trong mapper**, hoặc chọn cơ chế bất đồng bộ khác có hợp đồng vòng đời riêng. Không coi Consumer này như một callback dùng về sau.

### Lỗi 5: tưởng mapMulti tự đóng thứ đã mở trong mapper

Nếu mapper tự mở `Reader` hoặc một Stream con rồi không đóng, `mapMulti` không thể tự biết cần giải phóng gì. Dùng `try-with-resources` trong mapper, hoặc chuyển sang `flatMap` khi muốn trả về Stream con và sử dụng hợp đồng đóng của nó.

### Lỗi 6: phụ thuộc vào side effect của mapper

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger calls = new AtomicInteger();

long count = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> {
            calls.incrementAndGet(); // Không dùng để xác định nghiệp vụ
            out.accept(n);
        })
        .count();
~~~

Trong pipeline cụ thể này, `count` trả về `3` và mapper thực tế cần phát các giá trị để xác định số phần tử đầu ra. Tuy nhiên, biến `calls` là một **side effect** không cần thiết: nếu đổi pipeline sang thao tác dừng sớm hoặc xử lý song song, số lần và thứ tự các lời gọi có thể khác giả định của người viết. Các pipeline khác cũng có thể được Stream API tối ưu mà không chạy một số hàm trung gian. Hãy dùng **kết quả terminal operation**, ở đây là `count`, thay cho bộ đếm tác dụng phụ trong logic nghiệp vụ.

### Lỗi 7: dùng mapMulti cho nguồn con vô hạn và kỳ vọng limit ngắt mapper

~~~java
// Nguy hiểm: vòng lặp này không có điểm dừng tự nhiên.
// Stream.of("x").<String>mapMulti((x, out) -> {
//     for (;;) {
//         out.accept(x);
//     }
// }).limit(1).toList();
~~~

`limit(1)` thuộc **downstream**, không phải một tín hiệu dừng được truyền ngược thành boolean cho vòng lặp trong mapper. Nếu nguồn con là vô hạn hoặc rất lớn, ưu tiên mô hình nguồn Stream lazy như `flatMap` với Stream con phù hợp và một terminal operation có dừng.

## 14. Bảng quyết định chọn API

| Nhu cầu | Ưu tiên tham khảo | Lý do |
|---|---|---|
| Một đầu vào → đúng một kết quả | `map` | Ngắn gọn, khớp hợp đồng |
| Chỉ giữ/bỏ phần tử | `filter` | Thể hiện trực tiếp predicate |
| Flatten `List<List<T>>` hoặc `Stream<Stream<T>>` | `flatMap` | Nguồn con đã có dạng Stream tự nhiên |
| Mỗi phần tử phát 0–vài giá trị qua vòng lặp/điều kiện | `mapMulti` (Java 16+) | Mã mapper phát giá trị trực tiếp, không cần tạo Stream con |
| Có `Optional<T>` | `flatMap(Optional::stream)` hoặc `mapMulti(...ifPresent...)` | Hai cách đều biểu đạt 0/1 giá trị |
| Nguồn con cần xử lý lazy/short-circuit hiệu quả | Thường ưu tiên `flatMap` | Stream con cho phép duyệt dần; xem xét tài nguyên |
| Stream con gắn I/O | Thường ưu tiên `flatMap` và quản lý cả vòng đời bên ngoài | Hợp đồng `flatMap` có đóng Stream con |
| Đầu ra số nguyên/thực primitive | `flatMapToInt`, `mapMultiToInt`, `IntStream.mapMulti`... | Tránh boxing khi có ích |
| Cần chạy trên Java 8–15 | `flatMap` | `mapMulti` chưa có trong các JDK này |
| Dự kiến chạy song song | API nào rõ nghĩa và hàm stateless/non-interfering | Tránh chia sẻ trạng thái, đo hiệu năng thực tế |

Khi trả lời câu hỏi “`mapMulti` có thay thế hoàn toàn `flatMap` không?”, đáp án là **không**. Cả hai có thể biểu đạt cùng một kiểu biến đổi 0–N ở cấp giá trị, nhưng `flatMap` có mô hình **trả Stream con**, vòng đời Stream con và khả năng duyệt dần tự nhiên; `mapMulti` có mô hình **phát giá trị trong lúc mapper được gọi**, phù hợp với mở rộng trực tiếp hữu hạn và nhỏ.

## 15. Bài tập củng cố (kèm đáp án)

### Bài 1. Dự đoán kết quả

~~~java
import java.util.List;

List<List<Integer>> batches = List.of(
        List.of(1, 2),
        List.of(),
        List.of(3)
);

List<Integer> result = batches.stream()
        .<Integer>mapMulti((batch, out) -> batch.forEach(out))
        .toList();

System.out.println(result);
~~~

**Đáp án:** `[1, 2, 3]`. Batch rỗng không gọi `accept`; các batch còn lại phát phần tử theo thứ tự.

### Bài 2. Đổi flatMap thành mapMulti

Đoạn ban đầu:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> source = List.of("A", "BC", "D");

List<Character> letters = source.stream()
        .flatMap(s -> s.chars().mapToObj(c -> (char) c))
        .toList();
~~~

**Đáp án tham khảo:**

~~~java
List<Character> letters = source.stream()
        .<Character>mapMulti((s, out) -> {
            for (int i = 0; i < s.length(); i++) {
                out.accept(s.charAt(i));
            }
        })
        .toList();

System.out.println(letters); // [A, B, C, D]
~~~

Ở ví dụ này, mọi ký tự nằm trong BMP/ASCII nên `charAt` cho kết quả mong đợi. Với Unicode ngoài BMP, `char` có thể chỉ chứa một nửa surrogate pair; nếu cần code point, dùng `String.codePoints()` và làm việc với `int`.

### Bài 3. Khi nào dùng flatMap tự nhiên hơn?

**Đề:** Bạn có `List<Path>`, mỗi tệp có thể chứa hàng triệu dòng, và chỉ cần 10 dòng đầu tiên khớp điều kiện. Bạn sẽ ưu tiên API nào?

**Đáp án:** Thường ưu tiên `flatMap(path -> Files.lines(path))` kết hợp `filter` và `limit(10)`, xử lý ngoại lệ và vòng đời I/O đúng cách. Vì các Stream con cung cấp dòng một cách lazy, pipeline có cơ hội dừng sớm. Tránh viết `mapMulti` dùng vòng `while(reader.readLine())` quét hết từng tệp khi downstream chỉ cần vài dòng.

### Bài 4. Giải thích type witness

~~~java
List<Integer> result = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> {
            if (n > 1) out.accept(n);
        })
        .toList();
~~~

**Đáp án:** `<Integer>` cố định kiểu đầu ra `R` của `mapMulti`. Vì mapper không trả `Stream<R>` mà phát qua `Consumer<R>`, trình biên dịch đôi khi cần thêm ngữ cảnh để suy luận `R`.

### Bài 5. Phát nhiều phần tử mà không cần Stream con

**Đề:** Từ `List.of("x:1", "y:2", "z:3")`, lấy phần giá trị phía sau dấu hai chấm dưới dạng `List<String>` bằng `mapMulti`.

**Đáp án tham khảo:**

~~~java
import java.util.List;

List<String> source = List.of("x:1", "y:2", "z:3");

List<String> values = source.stream()
        .<String>mapMulti((record, out) -> {
            int separator = record.indexOf(':');
            if (separator >= 0 && separator + 1 < record.length()) {
                out.accept(record.substring(separator + 1));
            }
        })
        .toList();

System.out.println(values); // [1, 2, 3]
~~~

Đây là ví dụ **0 hoặc 1 kết quả**. Trong mã sản xuất, nếu đầu vào bảo đảm đúng định dạng và chỉ có một giá trị, `map` kết hợp validation cũng có thể rõ ràng hơn.

### Bài 6. Nhận diện rủi ro với parallel stream

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

List<List<Integer>> batches = List.of(
        List.of(1, 2),
        List.of(3, 4)
);

// Không nên:
// batches.parallelStream()
//         .forEach(batch -> shared.addAll(batch));
~~~

**Đáp án:** Việc ghi vào `ArrayList` chia sẻ từ các thread là không an toàn, có thể làm mất dữ liệu hoặc gây lỗi. Thay bằng:

~~~java
List<Integer> result = batches.parallelStream()
        .flatMap(List::stream)
        .toList();

System.out.println(result); // [1, 2, 3, 4]
~~~

Bởi nguồn có encounter order và `toList()` giữ thứ tự, kết quả được sắp theo thứ tự gặp phần tử mặc dù việc xử lý có thể diễn ra song song.

---

**Ghi nhớ:** `flatMap` yêu cầu mapper trả về **một Stream con cho mỗi phần tử đầu vào**; `mapMulti` yêu cầu mapper **phát trực tiếp 0–N giá trị vào Consumer trong phạm vi lời gọi**. Dùng `flatMap` khi nguồn con tự nhiên là Stream, cần khai thác xử lý lazy hoặc có tài nguyên phải đóng; cân nhắc `mapMulti` khi phần tử chỉ sinh ít giá trị bằng điều kiện và vòng lặp, trên Java 16+. Với cả hai, giữ mapper stateless/non-interfering, xác định rõ kiểu đầu ra và đo hiệu năng trước khi tối ưu.

