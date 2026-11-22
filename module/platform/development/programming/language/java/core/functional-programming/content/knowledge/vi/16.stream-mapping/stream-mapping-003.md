# Phân biệt map() tạo Stream lồng với flatMap() trong Java

## 1. Vấn đề cốt lõi: sau phép biến đổi còn bao nhiêu tầng dữ liệu?

Khi làm việc với `Stream` trong Java, hai phương thức `map()` và `flatMap()` đều nhận một hàm biến đổi phần tử. Điểm khác nhau quan trọng nhất là **hình dạng của kết quả**:

- **`map()`** biến đổi **mỗi phần tử đầu vào thành đúng một kết quả ánh xạ** (một đối tượng kết quả, dù đối tượng ấy có thể là collection hoặc một `Stream`). Phương thức **không tự xóa tầng lồng nhau**.
- **`flatMap()`** biến đổi mỗi phần tử thành **một `Stream` con** rồi **làm phẳng (*flatten*)** các phần tử của những stream con thành **một `Stream` kết quả duy nhất**. Một phần tử nguồn có thể tạo ra **0, 1 hoặc nhiều** phần tử đầu ra.

Tưởng tượng đầu vào có ba danh sách:

~~~text
[ ["java", "stream"], [], ["lambda"] ]
~~~

Với `map(List::stream)`, ta nhận **một stream gồm ba stream con**:

~~~text
Stream<Stream<String>>
  ├── Stream("java", "stream")
  ├── Stream()
  └── Stream("lambda")
~~~

Với `flatMap(List::stream)`, các phần tử được đưa ra một luồng chung:

~~~text
Stream<String>  →  "java", "stream", "lambda"
~~~

Điều quan trọng không phải `map` “sai” và `flatMap` “đúng”. **`map` đúng khi muốn giữ mỗi kết quả là một phần tử riêng** (chẳng hạn giữ từng nhóm). **`flatMap` đúng khi muốn nối các phần tử bên trong thành một luồng phẳng** để tiếp tục lọc, đếm, tìm, sắp xếp hoặc thu thập.

## 2. Chữ ký generic giúp phân biệt rất nhanh

Hai phương thức trên `Stream<T>` có chữ ký rút gọn:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);

<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

Đây là **chữ ký API minh họa**, không phải mã tự khai báo lại `Stream`.

Hãy nhìn kiểu **giá trị mà mapper trả về**:

| Tiêu chí | `map()` | `flatMap()` |
|---|---|---|
| Đầu vào nguồn | `Stream<T>` | `Stream<T>` |
| Mapper | `T → R` | `T → Stream<R>` (xét kiểu đơn giản) |
| Kết quả API | `Stream<R>` | `Stream<R>` |
| Một phần tử `T` tạo ra | Một `R` | 0, 1 hoặc nhiều `R` |
| Khi mapper trả `Stream<U>` | `R = Stream<U>`, thành `Stream<Stream<U>>` | Bóc phần tử `U` từ từng stream con, thành `Stream<U>` |
| Dùng khi | Đổi từng phần tử nhưng giữ mỗi phần tử kết quả như một đơn vị | Tách rồi nối, trải phẳng các nhóm hoặc nguồn con |
| Mapper ví dụ | `String::length` | `List::stream`, `Optional::stream` |

`flatMap` **không nhận trực tiếp `List<R>` làm kết quả mapper**. Khi xuất phát từ một danh sách bên trong, cần đổi nó thành stream qua `list.stream()`. Ví dụ đúng là `flatMap(List::stream)`; ví dụ `flatMap(group -> group)` không hợp lệ nếu `group` có kiểu `List<String>`.

### 2.1. Vì sao map có thể tạo Stream lồng?

Xét nguồn `Stream<List<String>>`. Với:

~~~java
Stream<Stream<String>> nested = groups.stream().map(List::stream);
~~~

- `T` của stream nguồn là `List<String>`.
- Mapper `List::stream` nhận một `List<String>` và trả `Stream<String>`.
- Theo hợp đồng `map`, một đối tượng `Stream<String>` vừa trả về sẽ trở thành **một phần tử `R`** của stream ngoài.
- Vậy `R` là `Stream<String>`, nên kết quả là `Stream<Stream<String>>`.

Trong khi đó:

~~~java
Stream<String> flat = groups.stream().flatMap(List::stream);
~~~

- Mapper vẫn tạo `Stream<String>`.
- Nhưng `flatMap` **tiêu thụ và làm phẳng** từng stream con, đưa các `String` vào luồng kết quả.
- Kết quả có kiểu `Stream<String>`, không còn tầng `Stream<...>` bên trong.

Cả hai câu lệnh là **đoạn minh họa cần biến `groups` kiểu `List<List<String>>` và các imports `java.util.List`, `java.util.stream.Stream`**.

## 3. Hình dung phép map và flatMap bằng số lượng phần tử

Với dữ liệu đầu vào có ba nhóm:

~~~text
Nguồn:       ["a", "b"]       []         ["c", "d", "e"]
                │             │                │
map(stream):   Stream(2)    Stream(0)        Stream(3)
                └──────── Stream<Stream<String>> ────────┘
flatMap:         "a" "b"       (rỗng)           "c" "d" "e"
                └────────── Stream<String> ─────────────┘
~~~

Một nhận xét dễ nhớ: `map()` tạo **một kết quả ánh xạ cho mỗi phần tử nguồn khi phần tử được xử lý**, còn `flatMap()` có thể **làm biến mất một nhóm rỗng** hoặc **mở rộng một nhóm nhiều phần tử**. Câu này mô tả số phần tử *logic*, không bảo đảm bao nhiêu lần callback sẽ chạy trong một pipeline có short-circuit hoặc tối ưu hóa của Stream.

Nếu cần tiếp tục gọi `String::toUpperCase` trên từng từ, `flatMap` giúp code đơn giản hơn:

~~~java
List<String> upper = groups.stream()
        .flatMap(List::stream)
        .map(String::toUpperCase)
        .toList();
~~~

Kết quả là danh sách phẳng. Nếu giữ `map(List::stream)`, ta sẽ có `Stream<Stream<String>>` và `map(String::toUpperCase)` trên tầng ngoài **không hợp kiểu**: các phần tử tầng ngoài là `Stream<String>`, không phải `String`.

## 4. Chương trình Java 17 hoàn chỉnh: quan sát đúng hai kiểu kết quả

Lưu thành **`MapFlatMapDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class MapFlatMapDemo {
    public static void main(String[] args) {
        List<List<String>> groups = List.of(
                List.of("java", "stream"),
                List.of(),
                List.of("lambda")
        );

        Stream<Stream<String>> nested =
                groups.stream().map(List::stream);

        List<List<String>> nestedValues = nested
                .map(Stream::toList)
                .toList();

        List<String> flattened = groups.stream()
                .flatMap(List::stream)
                .toList();

        List<String> upper = groups.stream()
                .flatMap(List::stream)
                .map(String::toUpperCase)
                .toList();

        int totalLength = groups.stream()
                .flatMap(List::stream)
                .mapToInt(String::length)
                .sum();

        System.out.println("nested=" + nestedValues);
        System.out.println("flat=" + flattened);
        System.out.println("upper=" + upper);
        System.out.println("length=" + totalLength);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac MapFlatMapDemo.java
java MapFlatMapDemo
~~~

Stdout chính xác:

~~~text
nested=[[java, stream], [], [lambda]]
flat=[java, stream, lambda]
upper=[JAVA, STREAM, LAMBDA]
length=16
~~~

**Giải thích theo từng pipeline:**

1. `groups` gồm ba danh sách con; danh sách thứ hai rỗng.
2. `map(List::stream)` tạo một `Stream<Stream<String>>`. Để **in được giá trị** mà không dựa vào `toString()` của đối tượng `Stream`, chương trình chuyển mỗi stream con thành một `List<String>` bằng `map(Stream::toList)`. Danh sách kết quả vẫn **lồng nhau**, có cả danh sách rỗng.
3. `flatMap(List::stream)` trải các `String` từ ba danh sách con ra một luồng duy nhất, cho `[java, stream, lambda]`. Nhóm rỗng không đóng góp phần tử nào.
4. Sau `flatMap`, `map(String::toUpperCase)` tác động trực tiếp lên mỗi `String`; `List.toList()` thu thập kết quả.
5. `mapToInt(String::length).sum()` làm việc với `IntStream` để cộng độ dài các chuỗi: `4 + 6 + 6 = 16`.
6. Mỗi lần xử lý cần **một pipeline nguồn mới**. `nested` đã bị tiêu thụ bởi `toList()`; gọi terminal operation thứ hai trên nó không hợp lệ. Do đó các pipeline sau dùng `groups.stream()` mới.

Code sử dụng `Stream.toList()` được bổ sung từ Java 16, phù hợp JDK 17. Trong ví dụ này luồng tuần tự và các nguồn List có thứ tự nên kết quả được in theo thứ tự dễ dự đoán.

## 5. Dùng map khi cần giữ nhóm, flatMap khi cần gộp nhóm

Giả sử ứng dụng có mỗi phòng ban và danh sách nhân viên:

~~~java
record Department(String name, List<String> members) {}
~~~

Nếu muốn thống kê số nhân viên **theo phòng ban**, cách tự nhiên là **`map`** để mỗi phòng ban tạo ra một kết quả thống kê:

~~~java
List<String> counts = departments.stream()
        .map(d -> d.name() + ":" + d.members().size())
        .toList();
~~~

Kết quả có **một mục cho mỗi phòng ban**, vì yêu cầu muốn giữ thông tin về nhóm.

Nếu muốn có **một danh sách tên nhân viên của toàn tổ chức**:

~~~java
List<String> allMembers = departments.stream()
        .flatMap(d -> d.members().stream())
        .toList();
~~~

Đây là ví dụ thích hợp cho **`flatMap`**, vì mỗi phòng ban có số nhân viên thay đổi và ta muốn kết hợp tất cả thành một luồng tên.

Hai đoạn trên là **mã minh họa đặt trong ngữ cảnh đã khai báo `departments` kiểu `List<Department>`**; không có `main` để chạy độc lập.

### 5.1. Một bước flatMap có thể tiếp tục kết hợp map

Khi cần gắn nhãn phòng ban vào mỗi nhân viên:

~~~java
List<String> labeled = departments.stream()
        .flatMap(d -> d.members().stream()
                .map(member -> d.name() + "/" + member))
        .toList();
~~~

Bên trong mapper của `flatMap`, ta gọi `map` trên **stream con** để tạo ra chuỗi chứa thông tin phòng ban, rồi `flatMap` ghép các chuỗi ấy vào một nguồn duy nhất. **Map và flatMap không loại trừ nhau**: chúng thường được kết hợp để vừa giữ ngữ cảnh của phần tử cha vừa trả ra nhiều phần tử con.

Đây cũng là tình huống một lambda rõ ràng hơn `flatMap(Department::members)`: phương thức `members()` trả `List<String>`, không phải `Stream<String>`, và còn cần thêm tên phòng ban vào từng chuỗi.

## 6. Chương trình Java 17: từ đơn hàng đến dòng hàng hóa

Lưu thành **`OrderFlatMapDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderFlatMapDemo {
    record Line(String sku, int quantity) {}
    record Order(String code, List<Line> lines) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", List.of(
                        new Line("pen", 2),
                        new Line("book", 1))),
                new Order("B", List.of()),
                new Order("C", List.of(
                        new Line("pen", 3)))
        );

        List<String> labeled = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> order.code()
                                + "/" + line.sku()
                                + "=" + line.quantity()))
                .toList();

        Map<String, Integer> quantities = orders.stream()
                .flatMap(order -> order.lines().stream())
                .collect(Collectors.groupingBy(
                        Line::sku,
                        TreeMap::new,
                        Collectors.summingInt(Line::quantity)
                ));

        List<String> nonEmptyOrders = orders.stream()
                .filter(order -> !order.lines().isEmpty())
                .map(Order::code)
                .toList();

        System.out.println("labeled=" + labeled);
        System.out.println("quantities=" + quantities);
        System.out.println("orders=" + nonEmptyOrders);
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac OrderFlatMapDemo.java
java OrderFlatMapDemo
~~~

Stdout:

~~~text
labeled=[A/pen=2, A/book=1, C/pen=3]
quantities={book=1, pen=5}
orders=[A, C]
~~~

**Vì sao kết quả đúng?**

1. `orders` gồm ba đơn: `A` có hai dòng hàng, `B` có danh sách rỗng, `C` có một dòng hàng.
2. Trong `flatMap(order -> ...)`, mỗi đơn tạo một stream con của các `Line`. `map` bên trong chuyển dòng hàng thành chuỗi mang cả mã đơn và mã hàng. `flatMap` ghép lại thành ba chuỗi; đơn `B` không sinh dòng nào.
3. `flatMap(order -> order.lines().stream())` đưa các `Line` của tất cả đơn vào cùng một stream, rồi `groupingBy(Line::sku, TreeMap::new, summingInt(...))` gộp số lượng theo `sku`. `pen` có `2 + 3 = 5`; `book` có `1`. `TreeMap` bảo đảm thứ tự key khi in.
4. `filter(...).map(Order::code)` vẫn giữ **mỗi đơn hàng là một phần tử nguồn**, chỉ loại đơn có danh sách rỗng rồi lấy mã đơn. Không cần dùng `flatMap` vì yêu cầu này là “mỗi đơn → một mã”, không phải “mỗi đơn → nhiều dòng hàng”.
5. Việc làm phẳng có thể làm mất ranh giới nhóm. Nếu thông tin đơn hàng quan trọng, hãy giữ nó trong kết quả như chuỗi gắn nhãn, một record chứa cả `orderCode` và `Line`, hoặc một cấu trúc dữ liệu có quan hệ cha-con rõ.

Một hướng thiết kế đáng chú ý: `flatMap` rất phù hợp cho quan hệ **one-to-many**, nhưng nếu business logic cần tổng hợp **theo từng cha**, đừng làm phẳng quá sớm rồi phải cố dựng lại thông tin nhóm.

## 7. Biến tập hợp rỗng hoặc Optional rỗng thành 0 phần tử

### 7.1. Danh sách con rỗng

Với `groups.stream().flatMap(List::stream)`, một danh sách con rỗng tạo ra một stream con **không có phần tử**, nên không đóng góp gì vào kết quả. Không cần thêm `filter(list -> !list.isEmpty())` chỉ để tránh phần tử rỗng, trừ khi filter thể hiện một điều kiện nghiệp vụ khác.

### 7.2. Optional.stream() kết hợp flatMap

Từ **Java 9**, `Optional<T>` có phương thức `stream()`:

- Nếu Optional chứa giá trị, `stream()` tạo stream một phần tử.
- Nếu Optional rỗng, `stream()` tạo stream rỗng.

Vì vậy có thể đưa một `Stream<Optional<T>>` thành `Stream<T>` bằng:

~~~java
List<String> values = optionals.stream()
        .flatMap(Optional::stream)
        .toList();
~~~

Đây là đoạn minh họa, `optionals` phải có kiểu `List<Optional<String>>` hoặc kiểu tương thích. Dạng này diễn đạt rõ “lấy những giá trị có mặt, bỏ qua những Optional rỗng”. Nó không phải phép gọi `Optional.flatMap`; đây là **`Stream.flatMap` kết hợp `Optional.stream`**, hai API khác nhau.

### 7.3. Ví dụ Java hoàn chỉnh

Lưu thành **`OptionalFlattenDemo.java`**:

~~~java
import java.util.List;
import java.util.Optional;

public class OptionalFlattenDemo {
    public static void main(String[] args) {
        List<Optional<String>> optionals = List.of(
                Optional.of("alpha"),
                Optional.empty(),
                Optional.of("beta")
        );

        List<List<String>> nested = optionals.stream()
                .map(value -> value.stream().toList())
                .toList();

        List<String> flat = optionals.stream()
                .flatMap(Optional::stream)
                .toList();

        System.out.println("nested=" + nested);
        System.out.println("flat=" + flat);
        System.out.println("count=" + flat.size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OptionalFlattenDemo.java
java OptionalFlattenDemo
~~~

Stdout:

~~~text
nested=[[alpha], [], [beta]]
flat=[alpha, beta]
count=2
~~~

Trong `nested`, mỗi `Optional` vẫn tương ứng một **danh sách con**, kể cả danh sách rỗng. Trong `flat`, kết quả chỉ gồm hai giá trị thật. Chọn cách nào tùy nhu cầu **giữ vị trí/gắn với đối tượng gốc** hay **chỉ lấy các giá trị hiện diện**.

## 8. `flatMap` với chuỗi: tách một phần tử ra nhiều token

Một tình huống thường gặp là một dòng văn bản chứa nhiều từ. Nếu dùng:

~~~java
List<String[]> arrays = lines.stream()
        .map(line -> line.split("\\s+"))
        .toList();
~~~

Kết quả là `List<String[]>`, mỗi dòng ứng với một mảng riêng. Cách này đúng nếu muốn giữ từng dòng là một nhóm.

Nếu muốn một danh sách từ phẳng:

~~~java
List<String> words = lines.stream()
        .flatMap(line -> java.util.Arrays.stream(line.split("\\s+")))
        .toList();
~~~

Ở đây `Arrays.stream(String[])` biến mảng token của một dòng thành `Stream<String>`, rồi `flatMap` nối các token.

**Lưu ý input:** với dòng rỗng, chuỗi chỉ có khoảng trắng, dấu câu hoặc nhiều dạng whitespace, kết quả `split("\\s+")` có các trường hợp biên cần kiểm tra theo dữ liệu thực tế; nếu cần xử lý chính xác, nên `strip()` và bỏ phần tử trống một cách có chủ đích trước khi thu thập.

Một mẫu thích hợp với chuỗi được chuẩn hóa là:

~~~java
List<String> words = lines.stream()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .flatMap(line -> java.util.Arrays.stream(line.split("\\s+")))
        .toList();
~~~

Nếu input `lines` chứa `null`, `String::strip` sẽ ném `NullPointerException`. Hãy xác định chính sách dữ liệu trước khi chọn pipeline.

## 9. `flatMap` và null: hai trường hợp khác nhau

**Trường hợp 1 — chính mapper trả về `null` thay vì stream:** theo hợp đồng của `Stream.flatMap`, một mapped stream bằng `null` được **xử lý như stream rỗng**. Tuy nhiên, cố ý trả `null` làm mapper khó đọc và dễ che lỗi; nên trả `Stream.empty()` rõ ràng.

~~~java
// Hợp lệ về ý tưởng; trả Stream.empty() rõ hơn trả null.
Stream<String> result = names.stream()
        .flatMap(name -> name.isBlank()
                ? Stream.empty()
                : Stream.of(name));
~~~

**Trường hợp 2 — phần tử nguồn là `null` và mapper gọi phương thức trên nó:**

~~~java
// Có thể ném NullPointerException nếu list == null.
source.stream().flatMap(List::stream);
~~~

`flatMap` không tự bảo vệ `null` trong **phần tử đầu vào**. Nếu nguồn có thể chứa danh sách null, cần quy tắc xử lý:

~~~java
Stream<String> result = source.stream()
        .flatMap(group -> group == null
                ? Stream.empty()
                : group.stream());
~~~

Hai đoạn cuối là **mã minh họa**, cần các kiểu `Stream`, nguồn `names` hoặc `source` phù hợp. `List.of(...)` tự không chấp nhận phần tử null khi tạo danh sách, nhưng các nguồn khác vẫn có thể chứa `null`.

**Phân biệt thêm:** `map` có thể trả ra phần tử kết quả `null`; khi đó stream ngoài vẫn chứa **một phần tử null** tại vị trí tương ứng. `flatMap` nhận một mapped stream bằng null thì coi như stream con rỗng. Đây là sự khác nhau về hợp đồng của hai phép toán, không phải lý do khuyến khích viết mapper trả null.

## 10. Độ lười (laziness), short-circuit và số lần gọi mapper

`map` và `flatMap` là **intermediate operations**. Chúng thiết lập pipeline, thường chưa gọi mapper ngay tại lúc xây dựng. Công việc thực tế được thực hiện khi có **terminal operation** như `toList()`, `count()` hoặc `findFirst()`, nhưng trình biên dịch/JVM và Stream API có thể tối ưu một số pipeline, nên không được dựa vào số lần mapper chạy như một giao thức tác dụng phụ.

### 10.1. `map()` thường là phép chuyển một-một về mặt logic

~~~java
List<Integer> lengths = List.of("a", "bb", "ccc").stream()
        .map(String::length)
        .toList();
// [1, 2, 3]
~~~

Đây là phép chuyển giá trị theo từng phần tử. Nếu dùng `filter` sau đó, một số kết quả sẽ bị bỏ đi; nếu dùng short-circuit, pipeline có thể dừng sớm. Không nên suy ra rằng mọi mapper trong mọi pipeline đều luôn chạy chính xác một lần cho từng phần tử ban đầu.

### 10.2. `flatMap` có thể tạo nhiều phần tử, nhưng downstream dừng sớm

~~~java
Optional<String> first = List.of(
        List.of("a", "b"),
        List.of("c", "d")
).stream()
 .flatMap(List::stream)
 .findFirst();
~~~

Kết quả `first` là `Optional.of("a")` trong pipeline tuần tự có thứ tự trên. Vì terminal operation `findFirst()` có thể dừng sớm, downstream **không cần** tiêu thụ toàn bộ các stream con. Do đó, không nên đặt thao tác nghiệp vụ bắt buộc vào mapper rồi trông đợi tất cả nhóm đều được xử lý.

### 10.3. `flatMap` không đồng nghĩa chạy song song

`flatMap` chỉ thay đổi cấu trúc pipeline. Nó **không tự tạo thread**, không có nghĩa “thực hiện bất đồng bộ”, và không bảo đảm hiệu năng tốt hơn `map`. Sử dụng `parallel()` là một quyết định khác, có các yêu cầu riêng về thread safety và thứ tự.

### 10.4. Tác dụng phụ trong mapper gây khó dự đoán

~~~java
// Không nên dùng như một cam kết chính xác về số lần ghi audit:
stream.flatMap(item -> {
    audit(item);           // side effect
    return item.children().stream();
});
~~~

Nếu traversal bị short-circuit, `audit(item)` có thể không chạy cho mọi phần tử. Với các nguồn và terminal operation có khả năng tối ưu, không nên coi side effect của intermediate operation là logic bắt buộc. Tách việc ghi audit/transaction thành luồng nghiệp vụ riêng hoặc dùng thiết kế có kiểm soát rõ ràng.

## 11. Vòng đời stream con và quản lý tài nguyên

Theo API Java, khi `flatMap` nhận một mapped stream khác null, **mapped stream được đóng sau khi nội dung của nó được đưa vào kết quả**. Điều này hữu ích khi mapper tạo stream con có vòng đời riêng.

Tuy nhiên, **không** suy ra mọi tài nguyên ngoài đều tự được đóng chỉ vì gọi `flatMap`:

- Nguồn stream ngoài có thể gắn với file hoặc tài nguyên cần đóng riêng.
- Nếu dùng `Files.lines(path)` làm nguồn ngoài, phải cân nhắc `try-with-resources` để đóng stream đó.
- Mapper có thể mở tài nguyên theo cách không gắn vòng đời với stream con; việc đóng stream con không tự đóng những tài nguyên không được kết nối với nó.
- Với lỗi I/O checked exception, `Function.apply` của `flatMap` không khai báo `throws IOException`, nên không thể đưa lời gọi có checked exception ra ngoài lambda mà không xử lý.

Ví dụ minh họa vòng đời nguồn file:

~~~java
// Giả sử path là java.nio.file.Path hợp lệ.
try (Stream<String> lines = java.nio.file.Files.lines(path)) {
    List<String> words = lines
            .flatMap(line -> java.util.Arrays.stream(line.split("\\s+")))
            .toList();
}
~~~

Đây là **đoạn code minh họa**, phải đặt trong phương thức xử lý/khai báo `IOException` và import `Stream`, `List`. Điểm chính là `try-with-resources` cho **source stream chứa tài nguyên file**, không phải biến `flatMap` thành công cụ quản lý mọi resource tự động.

Trong thực tế, khi có dữ liệu lớn, còn phải cân nhắc việc `toList()` thu thập toàn bộ kết quả trong bộ nhớ. Chọn terminal operation streaming, batch processing hoặc giới hạn dữ liệu tùy yêu cầu.

## 12. So sánh với `mapMulti` và các biến thể primitive

Java có thêm những API liên quan, nhưng **không nên nhầm với bản chất `flatMap`**:

| API | Mục đích | Kết quả |
|---|---|---|
| `Stream.map` | Một phần tử → một object kết quả | `Stream<R>` |
| `Stream.flatMap` | Một phần tử → stream con → làm phẳng | `Stream<R>` |
| `Stream.flatMapToInt` | Một phần tử → `IntStream` con → làm phẳng | `IntStream` |
| `Stream.flatMapToLong` | Một phần tử → `LongStream` con → làm phẳng | `LongStream` |
| `Stream.flatMapToDouble` | Một phần tử → `DoubleStream` con → làm phẳng | `DoubleStream` |
| `Stream.mapMulti` (Java 16+) | Một phần tử có thể phát 0..n kết quả qua một consumer | `Stream<R>` |

Ví dụ làm phẳng các danh sách `int` lưu trong `List<List<Integer>>` mà cần kết quả primitive:

~~~java
int total = numbers.stream()
        .flatMapToInt(group -> group.stream()
                .mapToInt(Integer::intValue))
        .sum();
~~~

Ở đây mapper của `flatMapToInt` trả `IntStream` con, không phải `Stream<Integer>`. `sum()` làm việc với primitive `int`, tránh một số chi phí boxing của pipeline object. Đoạn này là minh họa, cần `numbers` kiểu `List<List<Integer>>`.

Một ví dụ `mapMulti` để phát nhiều kết quả:

~~~java
List<Integer> flat = groups.stream()
        .<Integer>mapMulti((group, downstream) -> {
            for (Integer value : group) {
                downstream.accept(value);
            }
        })
        .toList();
~~~

`mapMulti` có thể hữu ích khi việc tạo một stream con cho mỗi phần tử là không cần thiết hoặc khi số phần tử đầu ra mỗi nguồn ít; nhưng nó có phong cách callback đẩy phần tử và không mặc định là lựa chọn dễ đọc nhất. Với danh sách lồng nhau quen thuộc, `flatMap(List::stream)` thường biểu đạt ý định rõ hơn.

**Chọn API theo kiểu đầu ra:** nếu cần làm phẳng object, `flatMap`; nếu cần làm phẳng primitive, cân nhắc `flatMapToInt`; nếu cần điều khiển emit qua consumer và sử dụng Java 16+, xem `mapMulti`.

## 13. Các lỗi phổ biến và cách sửa

### Lỗi 1: Dùng map rồi tưởng stream đã phẳng

~~~java
// Kiểu là Stream<Stream<String>>, KHÔNG phải Stream<String>.
// Stream<String> wrong = groups.stream().map(List::stream);
~~~

Cách sửa khi muốn phần tử String:

~~~java
Stream<String> words = groups.stream().flatMap(List::stream);
~~~

Nếu muốn **giữ** các luồng con như các đơn vị riêng, `map` không hề sai; khi đó biến cần khai báo đúng kiểu `Stream<Stream<String>>` và quản lý cách tiêu thụ các stream con.

### Lỗi 2: Trả List trực tiếp từ mapper của flatMap

~~~java
// SAI: flatMap cần mapper trả Stream.
// groups.stream().flatMap(group -> group);
~~~

Đúng:

~~~java
groups.stream().flatMap(List::stream);
~~~

### Lỗi 3: Dùng flatMap trong bài toán một-một

~~~java
// Rườm rà khi chỉ muốn biến mỗi String thành chiều dài.
List<Integer> a = words.stream()
        .flatMap(word -> Stream.of(word.length()))
        .toList();

// Rõ ràng hơn:
List<Integer> b = words.stream().map(String::length).toList();
~~~

`flatMap` ở dòng đầu vẫn có thể hợp lệ nhưng tạo ra một tầng stream con không cần thiết. `map` thể hiện tốt hơn quan hệ một-một.

### Lỗi 4: Dùng flatMap quá sớm và làm mất thông tin cha

Nếu phải báo cáo theo đơn hàng, `orders.stream().flatMap(o -> o.lines().stream())` chỉ còn các dòng hàng; mã đơn có thể không còn sẵn trong từng `Line`. Cách sửa là giữ thông tin cha trong object kết quả hoặc thực hiện phép tổng hợp theo từng đơn **trước** khi làm phẳng.

### Lỗi 5: Không xử lý phần tử null

`groups.stream().flatMap(List::stream)` có thể ném `NullPointerException` nếu có group `null`. Khi dữ liệu cho phép null, dùng `filter(Objects::nonNull)` hoặc lambda trả `Stream.empty()` theo chính sách đã thống nhất.

### Lỗi 6: Tái sử dụng stream sau terminal operation

~~~java
Stream<String> stream = groups.stream().flatMap(List::stream);
long count = stream.count();
// stream.toList();  // SAI: stream đã được tiêu thụ.
~~~

Muốn thu thập tiếp, tạo pipeline mới từ nguồn thích hợp. Stream có vòng đời dùng một lần; không phải collection có thể tùy ý lặp lại.

### Lỗi 7: Tin rằng `flatMap` luôn cải thiện hiệu năng

`flatMap` có thể cần tạo hoặc quản lý nhiều stream con, còn `map` thường đơn giản hơn khi một-một. Với khối lượng lớn, benchmark thực tế và xem xét cách tổ chức dữ liệu; đừng thay đổi `map` thành `flatMap` chỉ vì tên trông “mạnh” hơn.

### Lỗi 8: Cho rằng flatMap tự xử lý EOF

`flatMap` làm phẳng stream con, **không** chuyển một source vô hạn thành source hữu hạn. Nếu từng stream con vô hạn, pipeline có thể không tiến tới nhóm tiếp theo hoặc không kết thúc. Cần điểm dừng rõ ràng và thiết kế nguồn phù hợp.

## 14. Checklist chọn đúng phép biến đổi

Trước khi viết pipeline, hãy hỏi:

1. **Nguồn gồm phần tử kiểu gì?** `Stream<String>`, `Stream<List<String>>` hay `Stream<Optional<String>>`?
2. **Một phần tử đầu vào cần tạo ra mấy giá trị đầu ra?** Một, không có hoặc nhiều?
3. **Có cần giữ ranh giới nhóm không?** Nếu có, `map` thường phù hợp; nếu cần gộp mọi phần tử con, `flatMap`.
4. **Mapper trả kiểu nào?** `R` hay `Stream<R>`? `flatMap` yêu cầu stream con.
5. **Kết quả cần là `Stream<R>` hay một primitive stream?** Xem `flatMapToInt` và các biến thể khi cần.
6. **Thông tin cha có cần giữ trong phần tử đã làm phẳng không?** Nếu cần, tạo record hoặc gắn dữ liệu cha trong mapper.
7. **Có các nhóm rỗng/null không?** Xác định chính sách cho chúng.
8. **Có short-circuit, parallelism hoặc nguồn tài nguyên không?** Không dựa vào thứ tự/ số lần side effect một cách mù quáng; đóng nguồn cần đóng.
9. **Có thể dùng `Optional::stream` không?** Khi nguồn là Optional và muốn bỏ qua mục rỗng, đây là lựa chọn ngắn gọn.
10. **Người đọc sẽ hiểu hình dạng kiểu sau từng bước chứ?** Khi khó đọc, đặt biến trung gian có kiểu tường minh để kiểm tra.

Một mẹo debug rất hiệu quả: tạm khai báo rõ kiểu trung gian, ví dụ `Stream<Stream<String>>` đối chiếu với `Stream<String>`. Compiler sẽ giúp lộ ra nơi thêm hoặc thiếu một tầng stream.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Với `List<List<Integer>>`, `groups.stream().map(List::stream)` có kiểu gì?

**Câu 2.** `groups.stream().flatMap(List::stream)` có kiểu gì? Một nhóm rỗng đóng góp bao nhiêu phần tử?

**Câu 3.** Tại sao `flatMap(group -> group)` không hợp lệ khi `group` là `List<String>`?

**Câu 4.** `map(String::length)` thích hợp hơn `flatMap(s -> Stream.of(s.length()))` ở điểm nào?

**Câu 5.** Với `Stream<Optional<String>>`, có thể dùng biểu thức nào để thu các giá trị hiện diện?

**Câu 6.** Nếu cần giữ mã đơn hàng khi làm phẳng các dòng hàng, nên làm gì?

**Câu 7.** Có thể tin rằng mapper của `flatMap` luôn được gọi một lần cho mọi phần tử nguồn trong pipeline có `findFirst()` không?

**Câu 8.** Nếu nguồn có `null` và mapper gọi `List::stream`, điều gì có thể xảy ra?

**Câu 9.** Khi cần một `IntStream` gồm toàn bộ số từ các stream con, nên xem API nào?

**Đáp án ngắn:**

1. `Stream<Stream<Integer>>`: mỗi phần tử của stream ngoài là một stream con.
2. `Stream<Integer>`; nhóm rỗng góp `0` phần tử.
3. Vì mapper của `flatMap` phải trả `Stream<? extends R>`, không phải `List<R>`.
4. `map` diễn đạt trực tiếp phép một-một và không tạo stream con không cần thiết.
5. `flatMap(Optional::stream)`, có từ Java 9.
6. Map mỗi `Line` cùng mã đơn thành record/DTO hoặc dữ liệu nhãn trước khi kết quả được làm phẳng.
7. Không; short-circuit có thể ngừng traversal sớm, còn Stream API cho phép những tối ưu hóa phù hợp.
8. `NullPointerException` nếu mapper dereference giá trị null.
9. `flatMapToInt` và mapper trả một `IntStream`.
  
## 16. Tài liệu chính thức

- [Java SE 17 API — Stream.map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#map(java.util.function.Function)): phép biến đổi từng phần tử sang một kết quả.
- [Java SE 17 API — Stream.flatMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#flatMap(java.util.function.Function)): làm phẳng stream con, hành vi với mapped stream bằng null và vòng đời stream con.
- [Java SE 17 API — Stream.mapMulti](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer)): phát nhiều kết quả theo kiểu callback.
- [Java SE 17 API — Optional.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#stream()): Optional có giá trị thành stream một phần tử, rỗng thành stream không phần tử.
- [Java SE 17 API — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): thu kết quả vào danh sách.

**Ghi nhớ:** `map()` giữ **mỗi kết quả ánh xạ là một phần tử**; nếu kết quả mapper là `Stream<U>`, kiểu ngoài sẽ là `Stream<Stream<U>>`. `flatMap()` dùng khi mapper trả **stream con** và ta muốn ghép tất cả phần tử con thành **một `Stream<U>` phẳng**. Chọn theo **kiểu dữ liệu và nhu cầu giữ nhóm hay trải phẳng**, không chỉ theo việc cú pháp nào ngắn hơn.