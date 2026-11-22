# Thu thập thành List bằng Collectors.toList

Trong Java Stream API, các phép toán trung gian như `filter`, `map`, `sorted` và `distinct` mô tả cách xử lý dữ liệu. Khi cần **lấy toàn bộ phần tử đầu ra của pipeline thành một `List`**, ta sử dụng phép toán kết thúc `collect(Collectors.toList())`.

Bài học thuộc chương **Thu thập thành Collection** của module **JAVA_STREAM_API**. Đây là bước chuyển từ pipeline lười sang kết quả có thể sử dụng tiếp: sau khi lọc, biến đổi hoặc sắp xếp dữ liệu, chúng ta cần thu thập các phần tử. Ngoài cú pháp, cần hiểu chính xác hợp đồng về **thứ tự, giá trị trùng, kiểu List, khả năng sửa đổi, chạy song song và chi phí bộ nhớ**. Những hiểu biết này cũng là nền tảng để học grouping, collector tùy chỉnh và các phép rút gọn khác.

## 1. Cú pháp và thời điểm thu thập

`Collectors.toList()` là phương thức tĩnh của `java.util.stream.Collectors`. Nó tạo một `Collector` dùng với terminal operation `Stream.collect(...)`:

```java
List<R> result = source.stream()
    .filter(/* điều kiện */)
    .map(/* biến đổi sang R */)
    .collect(Collectors.toList());
```

Chữ `R` chỉ kiểu phần tử sau các phép biến đổi; kết quả có kiểu `List<R>`. Chẳng hạn, nguồn `Stream<String>` có thể được ánh xạ thành `Stream<Integer>` rồi thu về `List<Integer>`.

### Ví dụ Java 8 hoàn chỉnh

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Collectors;

public class CollectToListDemo {
    public static void main(String[] args) {
        List<String> rawNames = Arrays.asList(
            "  an  ", null, "Binh", "An", "Binh", " Chi "
        );

        List<String> names = rawNames.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(name -> name.length() >= 3)
            .map(name -> name.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println(names);    // [BINH, BINH, CHI]
        System.out.println(rawNames); // Nguồn vẫn chứa các giá trị ban đầu.
    }
}
```

Diễn giải từng bước:

1. `rawNames.stream()` tạo một Stream có thứ tự theo `List` nguồn.
2. `filter(Objects::nonNull)` bỏ giá trị `null` để `String::trim` không gây `NullPointerException`.
3. `map(String::trim)` bỏ khoảng trắng đầu/cuối; `filter` chỉ giữ tên dài ít nhất ba ký tự.
4. `map(...toUpperCase...)` tạo chuỗi viết hoa, sử dụng `Locale.ROOT` để tránh phụ thuộc locale mặc định.
5. `collect(Collectors.toList())` yêu cầu pipeline thực thi và thu các phần tử còn lại vào một `List<String>`.

**`collect` là phép toán kết thúc.** Trước khi gọi nó, `filter` và `map` thông thường chưa duyệt toàn bộ nguồn: các bước trung gian được đánh giá lười. Sau khi hoàn tất, `names` là một List chứa kết quả đã thu thập, có thể được truyền sang phương thức khác hoặc đọc nhiều lần như một Collection.

Ví dụ trên không cần tạo List tạm giữa các bước `filter` và `map`. Stream xử lý phần tử qua pipeline theo nhu cầu của terminal operation.

## 2. Kết quả giữ những phần tử nào?

`Collectors.toList()` thu thập **mọi phần tử được pipeline chuyển tới nó**. Bản thân collector không lọc, loại trùng hoặc sắp xếp. Những việc đó do các phép toán trung gian quyết định.

```java
List<String> input = Arrays.asList("B", "A", "B", "C", "A");

List<String> keepAll = input.stream()
    .collect(Collectors.toList());
// [B, A, B, C, A]

List<String> unique = input.stream()
    .distinct()
    .collect(Collectors.toList());
// [B, A, C]

List<String> sorted = input.stream()
    .sorted()
    .collect(Collectors.toList());
// [A, A, B, B, C]

List<String> firstTwoUniqueSorted = input.stream()
    .distinct()
    .sorted()
    .limit(2)
    .collect(Collectors.toList());
// [A, B]
```

Với `Stream` có encounter order, `distinct()` giữ lần xuất hiện đầu tiên của từng giá trị. `sorted()` tạo thứ tự sắp xếp, còn `limit(2)` giới hạn số phần tử tiếp tục được chuyển đến collector.

Nếu chỉ cần kiểm tra **có một phần tử phù hợp hay không**, `anyMatch(predicate)` thường đúng mục đích và có khả năng dừng sớm hơn việc thu toàn bộ List. Nếu chỉ cần **số lượng**, dùng `count()` để tránh tạo List không cần thiết.

### List có thể chứa phần tử lặp và null

`List` cho phép giá trị lặp. `Collectors.toList()` cũng không có bước tự động loại `null`:

```java
List<String> withNull = Stream.of("A", null, "B")
    .collect(Collectors.toList());

System.out.println(withNull); // [A, null, B]
```

Tuy nhiên, một phép toán trung gian như `map(String::length)` sẽ ném lỗi khi gặp `null`. Vì vậy, hãy xác định chính sách xử lý dữ liệu null trước các phép biến đổi có thể không chấp nhận null.

`distinct()` sử dụng ngữ nghĩa bằng nhau của phần tử (thông thường là `equals`); với kiểu đối tượng tự định nghĩa, việc triển khai `equals`/`hashCode` có thể ảnh hưởng kết quả loại trùng.

## 3. Encounter order và thứ tự phần tử trong List

Điểm quan trọng của `toList` là **giữ encounter order nếu Stream có thứ tự**. Encounter order là thứ tự phần tử do nguồn hoặc một phép toán trong pipeline xác định.

| Nguồn hoặc pipeline | Có encounter order không? | Hệ quả khi dùng `Collectors.toList()` |
| --- | --- | --- |
| `ArrayList.stream()` | Có, theo thứ tự List | List kết quả giữ thứ tự sau các bước pipeline |
| `LinkedHashSet.stream()` | Có, theo thứ tự chèn | Giữ thứ tự chèn của các phần tử còn lại |
| `TreeSet.stream()` | Có, theo thứ tự sắp xếp | Giữ thứ tự của Set |
| `HashSet.stream()` | Không bảo đảm | Không được giả định thứ tự List kết quả cố định |
| `stream.sorted()` | Có thứ tự sắp xếp xác định | List kết quả phản ánh thứ tự đã sắp xếp |
| `stream.unordered()` | Bỏ ràng buộc encounter order | Không được dựa vào thứ tự phần tử cụ thể |

Ví dụ thu thập từ `HashSet`:

```java
Set<Integer> values = new HashSet<>(
    Arrays.asList(30, 10, 20)
);

List<Integer> withoutOrderGuarantee = values.stream()
    .collect(Collectors.toList());
// Không giả định danh sách là [10, 20, 30].

List<Integer> stableOrder = values.stream()
    .sorted()
    .collect(Collectors.toList());
// [10, 20, 30]
```

**Collector không tự tạo thứ tự nghiệp vụ.** Nếu muốn hiển thị danh sách người dùng theo ngày đăng ký, cần sắp xếp theo ngày đăng ký, và nếu có thể trùng ngày thì bổ sung một khóa phân biệt như ID. Việc thu thành List chỉ bảo toàn thứ tự được pipeline cung cấp.

## 4. Hợp đồng không bảo đảm List cụ thể hoặc có thể sửa đổi

Một sai lầm phổ biến là cho rằng `Collectors.toList()` **luôn trả về `ArrayList` có thể `add`/`remove`**. Đó không phải hợp đồng API.

Theo hợp đồng `Collectors.toList()`, **không có bảo đảm** về:

- Lớp triển khai List cụ thể, ví dụ `ArrayList` hay một lớp khác.
- Khả năng sửa đổi (mutability) sau khi thu thập.
- Khả năng tuần tự hóa (serializability).
- Tính an toàn luồng (thread safety) của List trả về.

Trên các JDK thông dụng, kết quả thực tế có thể là `ArrayList` sửa đổi được, nhưng mã ứng dụng **không nên phụ thuộc** vào chi tiết triển khai này:

```java
List<String> result = Stream.of("A", "B")
    .collect(Collectors.toList());

// Không viết logic bắt buộc thao tác sau phải được hỗ trợ:
// result.add("C");
```

Nếu muốn **chắc chắn nhận một `ArrayList` có thể thay đổi**, chỉ rõ loại Collection cần tạo bằng `Collectors.toCollection`:

```java
ArrayList<String> mutable = Stream.of("A", "B")
    .collect(Collectors.toCollection(ArrayList::new));

mutable.add("C");
System.out.println(mutable); // [A, B, C]
```

Việc chỉ định `ArrayList::new` giúp mục đích của code rõ ràng và bám hợp đồng của lớp List cụ thể. Ngược lại, nếu chỉ cần đọc danh sách, có thể giữ kiểu biến là `List<T>` và không giả định kết quả có thể sửa.

## 5. Phân biệt ba cách thu thập List thường gặp

Từ các phiên bản Java khác nhau, có nhiều API cùng trả về `List` nhưng hợp đồng không giống nhau.

| Cách viết | Phiên bản có từ | Có thể sửa danh sách? | Giá trị `null` |
| --- | --- | --- | --- |
| `stream.collect(Collectors.toList())` | Java 8 | **Không được bảo đảm** | Có thể thu các phần tử `null` |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Java 8 | Có, vì trả về `ArrayList` | `ArrayList` chấp nhận `null` |
| `stream.collect(Collectors.toUnmodifiableList())` | Java 10 | Không | Không chấp nhận `null`; có thể ném `NullPointerException` |
| `stream.toList()` | Java 16 | Không | Có thể chứa `null` |

Mỗi lựa chọn đều có tình huống phù hợp:

```java
List<String> names = Stream.of("An", "Binh", "Chi")
    .collect(Collectors.toList()); // Java 8+

ArrayList<String> editable = Stream.of("An", "Binh", "Chi")
    .collect(Collectors.toCollection(ArrayList::new)); // Java 8+

List<String> immutableView = Stream.of("An", "Binh", "Chi")
    .collect(Collectors.toUnmodifiableList()); // Java 10+

List<String> unmodifiable = Stream.of("An", "Binh", "Chi")
    .toList(); // Java 16+
```

Ở ví dụ này, `immutableView` và `unmodifiable` đều không cho phép `add`, `remove` hoặc `set`, nhưng chúng là những **List kết quả**, không phải một cách đóng băng sâu nội dung của từng đối tượng phần tử.

### Đặc biệt: Collectors.toList và Stream.toList không tương đương

`Collectors.toList()` là một **Collector** truyền vào `collect(...)`. `Stream.toList()` là một **terminal operation trực tiếp trên Stream**, được thêm từ Java 16. Dù đều trả về `List`, sự khác biệt về mutability là một phần của hợp đồng:

```java
// Java 16+:
List<String> result = Stream.of("A", "B").toList();

// Luôn ném UnsupportedOperationException:
// result.add("C");
```

Không tự động đổi `collect(Collectors.toList())` thành `toList()` trong code cũ nếu đoạn code còn sửa danh sách kết quả; đồng thời code Java 8 không biên dịch được lời gọi `Stream.toList()`.

`Collectors.toUnmodifiableList()` và `Stream.toList()` cũng khác nhau về xử lý `null`. Ví dụ `Stream.of("A", null).toList()` có thể chứa `null`, còn `collect(Collectors.toUnmodifiableList())` từ chối `null`.

## 6. Kết quả List là một tập hợp tham chiếu, không phải bản sao sâu

Khi Stream chứa đối tượng có thể thay đổi, `Collectors.toList()` tạo một List chứa **các tham chiếu tới phần tử được pipeline phát ra**. Nếu không dùng `map` để tạo đối tượng mới, không có quá trình sao chép sâu từng phần tử.

```java
List<StringBuilder> source = Arrays.asList(
    new StringBuilder("A"),
    new StringBuilder("B")
);

List<StringBuilder> result = source.stream()
    .collect(Collectors.toList());

source.get(0).append("!");
System.out.println(result.get(0)); // A!
```

List kết quả và List nguồn là hai cấu trúc chứa phần tử, nhưng cả hai đang tham chiếu đến cùng đối tượng `StringBuilder` đầu tiên. Để có bản sao độc lập của phần tử, cần chủ động ánh xạ sang đối tượng mới:

```java
List<StringBuilder> copies = source.stream()
    .map(item -> new StringBuilder(item.toString()))
    .collect(Collectors.toList());
```

Nếu mục đích chỉ là thu chuỗi bất biến `String`, việc chia sẻ tham chiếu thông thường không gây vấn đề thay đổi nội dung chuỗi.

Một điểm khác: `Stream` **không tự chụp snapshot của Collection tại lúc gọi `stream()`**. Với Collection không hỗ trợ thay đổi đồng thời, sửa cấu trúc nguồn trong lúc pipeline tiêu thụ có thể gây `ConcurrentModificationException` hoặc hành vi không được bảo đảm. Đừng cập nhật nguồn bên trong `filter` hay `forEach` rồi mong `collect` xử lý an toàn.

## 7. Thu thập trong parallel stream

`collect(Collectors.toList())` sử dụng cơ chế **mutable reduction**. Về mặt khái niệm, một Collector có các thành phần: `supplier` tạo container, `accumulator` thêm phần tử, `combiner` gộp các container từng phần và `finisher` hoàn thiện kết quả.

Khi chạy song song, Stream có thể chia dữ liệu thành các nhánh, tích lũy vào **container từng phần** rồi gộp chúng. Bạn không phải tự giữ một `ArrayList` chung để nhiều luồng cùng `add`.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> squares = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(squares); // [4, 16, 36]
```

Vì `numbers` có encounter order và phép thu thập tôn trọng thứ tự ấy, List kết quả vẫn là `[4, 16, 36]`. Điều đó **không có nghĩa** các lời gọi `filter`/`map` đã chạy lần lượt theo thứ tự `1, 2, 3, 4, 5, 6`.

Đối chiếu với kiểu viết nguy hiểm:

```java
List<Integer> unsafe = new ArrayList<>();

// Không sử dụng: nhiều luồng cùng thay đổi một ArrayList.
// numbers.parallelStream().forEach(n -> unsafe.add(n * n));

List<Integer> safe = numbers.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

Trong ví dụ sai, `ArrayList` có thể bị ghi đồng thời dẫn đến kết quả thiếu/sai hoặc ngoại lệ. Trong ví dụ đúng, hệ thống thu thập gộp các kết quả theo hợp đồng Collector.

**Phân biệt:** quá trình `collect` từ một parallel stream có thể an toàn nhờ cách tổ chức các container, nhưng **List sau khi trả về không mặc nhiên an toàn cho nhiều luồng cùng sửa**. Nếu thật sự cần đồng bộ khi sử dụng kết quả, hãy thiết kế lớp bảo vệ phù hợp với ứng dụng.

`Collectors.toList()` không phải concurrent collector. Với nguồn có thứ tự, việc giữ encounter order còn có chi phí kết hợp và bảo toàn vị trí. Do đó, `parallelStream()` không hứa thu List nhanh hơn: hãy đo trên khối lượng và phép biến đổi thực tế.

## 8. Tính lười, bộ nhớ và nguồn vô hạn

`Collectors.toList()` cần có khả năng thu **tất cả phần tử của pipeline đầu ra** trước khi trả List. Với một nguồn vô hạn mà không có điều kiện dừng, terminal này không thể hoàn tất theo cách đánh giá thông thường:

```java
// KHÔNG chạy: nguồn không có giới hạn.
// List<Integer> infinite = Stream.iterate(1, n -> n + 1)
//     .collect(Collectors.toList());
```

Hãy giới hạn nguồn bằng các phép toán trung gian phù hợp:

```java
List<Integer> firstFiveEven = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(5)
    .collect(Collectors.toList());

System.out.println(firstFiveEven); // [2, 4, 6, 8, 10]
```

`limit(5)` giới hạn **số phần tử đã vượt qua bộ lọc**. Nếu bộ lọc không bao giờ cho phần tử đi tiếp, `limit` phía sau cũng không giúp hoàn tất. Từ Java 9, `takeWhile` có thể đặt điều kiện dừng theo đoạn đầu liên tiếp của một nguồn có encounter order.

Về bộ nhớ, List phải giữ các phần tử đã thu thập: mức sử dụng bộ nhớ tăng theo số phần tử đầu ra, chưa kể các đối tượng phần tử và dữ liệu tạm của pipeline. Với dữ liệu lớn, cần cân nhắc:

- Có thật sự cần giữ **toàn bộ** phần tử trong RAM không? Nếu chỉ cần đếm, dùng `count`; nếu cần tổng, dùng `sum`/`reduce`.
- Có thể lọc, giới hạn hoặc chọn những trường cần thiết bằng `map` **trước** khi thu thập không?
- Nếu nguồn dữ liệu tới từ cơ sở dữ liệu hoặc dịch vụ, có nên phân trang/tải theo lô tại nguồn không?
- Khi cần ghi ra một đích ở bên ngoài, có thể xử lý theo lô với quản lý tài nguyên và lỗi rõ ràng thay vì gom tất cả vào một List lớn không?

Một Stream gắn với tài nguyên ngoài như `Files.lines(path)` cần được đóng bằng `try-with-resources`. Việc `collect` hoàn tất **không tự động đóng** mọi nguồn tài nguyên:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> nonBlank = lines
        .filter(s -> !s.trim().isEmpty())
        .collect(Collectors.toList());
    // Dùng nonBlank khi cần.
}
```

Đây là ví dụ sử dụng `path` kiểu `Path` và các import `Files`, `Stream`, `List`, `Collectors` phù hợp. `Files.lines` có thể ném `IOException` nên mã gọi phải xử lý hoặc khai báo ngoại lệ.

## 9. Kết hợp với các Collector khác khi bài toán thay đổi

`Collectors.toList()` phù hợp với yêu cầu “cho tôi một danh sách các phần tử sau pipeline”. Khi yêu cầu đầu ra thay đổi, chọn Collector khác có thể chính xác và hiệu quả hơn.

| Yêu cầu đầu ra | Gợi ý |
| --- | --- |
| Danh sách các phần tử | `collect(Collectors.toList())` |
| Danh sách với lớp triển khai xác định | `collect(Collectors.toCollection(ArrayList::new))` |
| Tập giá trị duy nhất | `collect(Collectors.toSet())`; không giả định thứ tự |
| List theo từng nhóm khóa | `collect(Collectors.groupingBy(keyFn))` |
| Nối chuỗi bằng dấu phân cách | `collect(Collectors.joining(", "))` |
| Đếm số phần tử | `count()` hoặc `Collectors.counting()` khi lồng Collector |

Ví dụ lấy **các List được nhóm theo chữ cái đầu**:

```java
List<String> words = Arrays.asList("apple", "ant", "banana", "boat");

Map<Character, List<String>> byInitial = words.stream()
    .collect(Collectors.groupingBy(word -> word.charAt(0)));

// Khóa 'a' ứng với [apple, ant]; khóa 'b' ứng với [banana, boat].
// Không phụ thuộc thứ tự duyệt các khóa của Map kết quả.
```

`groupingBy` mặc định thu các phần tử trong từng nhóm vào List. Khi muốn chỉ định rõ downstream collector:

```java
Map<Character, List<String>> explicit = words.stream()
    .collect(Collectors.groupingBy(
        word -> word.charAt(0),
        Collectors.toList()
    ));
```

Đây là ví dụ cho thấy `Collectors.toList()` còn có thể được dùng **bên trong một Collector phức hợp**. Từ mục tiêu thu List cơ bản, người học có thể phát triển sang grouping, partitioning và collector tùy chỉnh.

## 10. Các lỗi thường gặp

| Cách hiểu hoặc cách viết sai | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Collectors.toList()` và mặc định kết quả là `ArrayList` | Phụ thuộc chi tiết triển khai | Khi cần `ArrayList`, dùng `toCollection(ArrayList::new)` |
| Coi `Collectors.toList()` và `Stream.toList()` là giống nhau | Khác hợp đồng sửa đổi List và yêu cầu phiên bản Java | Xem rõ phiên bản Java và loại List cần |
| Thu List rồi gọi `size()` chỉ để đếm | Tạo List không cần thiết | Dùng terminal `count()` |
| Thu List từ `HashSet` rồi dựa vào thứ tự | Không có cam kết encounter order | Sắp xếp trước hoặc dùng nguồn có thứ tự |
| Muốn loại trùng nhưng chỉ gọi `toList()` | Giá trị lặp vẫn được giữ | Thêm `distinct()` trước terminal |
| Nguồn chứa null rồi gọi `String::trim` | Có thể ném `NullPointerException` | `filter(Objects::nonNull)` trước phép biến đổi |
| Dùng `forEach(list::add)` lên List ngoài trong `parallelStream()` | Trạng thái chia sẻ có thể bị race condition | Dùng `collect(Collectors.toList())` |
| Tưởng List kết quả sao chép sâu đối tượng | Thay đổi phần tử mutable được thấy qua nhiều tham chiếu | Tạo bản sao phần tử bằng `map` khi cần |
| Thu tất cả từ Stream vô hạn | Không kết thúc hoặc cạn tài nguyên | Đặt giới hạn có thể đạt, ví dụ `limit(n)` |
| Dùng lại một Stream sau `collect` | Stream đã bị tiêu thụ | Tạo Stream mới từ nguồn cho truy vấn tiếp theo |

## 11. Bài tập có đáp án

### Bài 1 — Lọc và thu đúng thứ tự

Cho một danh sách điểm `[5, 9, 7, 9, 3]`, lấy tất cả điểm từ `7` trở lên, giữ nguyên thứ tự và giá trị trùng.

```java
List<Integer> points = Arrays.asList(5, 9, 7, 9, 3);

List<Integer> selected = points.stream()
    .filter(score -> score >= 7)
    .collect(Collectors.toList());
// [9, 7, 9]
```

**Đáp án:** `[9, 7, 9]`. `Collectors.toList()` không tự loại phần tử lặp và giữ encounter order của List.

### Bài 2 — Chuyển kiểu phần tử trước khi thu

Cho `["An", "Binh", "Chi"]`, tạo `List<Integer>` chứa độ dài mỗi tên.

```java
List<Integer> lengths = Arrays.asList("An", "Binh", "Chi")
    .stream()
    .map(String::length)
    .collect(Collectors.toList());
// [2, 4, 3]
```

**Đáp án:** `map` chuyển `Stream<String>` thành `Stream<Integer>`, vì vậy kết quả của `collect(Collectors.toList())` là `List<Integer>`.

### Bài 3 — Cần danh sách có thể add

Đoạn code sau có bảo đảm hoạt động trên mọi triển khai tuân thủ Java API không?

```java
List<String> names = Stream.of("A", "B")
    .collect(Collectors.toList());
// names.add("C"); // Không được API bảo đảm.
```

**Đáp án:** Không. Nếu cần thêm phần tử sau khi thu, hãy chỉ rõ `ArrayList`:

```java
ArrayList<String> names = Stream.of("A", "B")
    .collect(Collectors.toCollection(ArrayList::new));
names.add("C");
```

### Bài 4 — Song song có làm thay đổi thứ tự kết quả?

```java
List<Integer> input = Arrays.asList(1, 2, 3, 4, 5);

List<Integer> values = input.parallelStream()
    .filter(n -> n % 2 != 0)
    .map(n -> n * 10)
    .collect(Collectors.toList());
```

**Đáp án:** `[10, 30, 50]`. Với nguồn List có thứ tự, collector giữ encounter order của các phần tử đầu ra; thứ tự **thực thi** lambda vẫn có thể khác.

### Bài 5 — Chọn terminal theo yêu cầu

Cho `List<String> words` lớn, chỉ cần biết có tên nào rỗng sau `trim` không. Có nên gọi `collect(Collectors.toList())`?

```java
boolean hasBlank = words.stream()
    .anyMatch(word -> word.trim().isEmpty());
```

**Đáp án:** Nên dùng `anyMatch` vì kết quả cần là `boolean`; terminal này có thể dừng sớm khi gặp chuỗi rỗng đầu tiên. Nếu dữ liệu có thể chứa `null`, cần xác định quy tắc xử lý null riêng, chẳng hạn `word == null || word.trim().isEmpty()`.

### Bài 6 — List rỗng

```java
List<Integer> empty = Stream.of(1, 3, 5)
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList());
```

**Đáp án:** `empty` là một List rỗng, không phải `null`. `collect(Collectors.toList())` thu thành List dù không có phần tử nào đi qua pipeline.

## Ghi nhớ

Trong **JAVA_STREAM_API**, `collect(Collectors.toList())` là cách thông dụng từ Java 8 để biến các phần tử còn lại của Stream thành `List`. Nó là **terminal operation**, giữ các giá trị trùng và tôn trọng encounter order của nguồn có thứ tự, nhưng **không cam kết** lớp triển khai hay khả năng sửa đổi của List được trả về. Nếu cần `ArrayList` có thể chỉnh sửa, dùng `Collectors.toCollection(ArrayList::new)`; nếu cần List không thể sửa đổi, cân nhắc `Stream.toList()` (Java 16+) hoặc `Collectors.toUnmodifiableList()` (Java 10+) với chính sách null phù hợp. Khi thu thập song song, hãy để Collector quản lý các kết quả từng phần; khi dữ liệu lớn hoặc vô hạn, phải tính đến bộ nhớ và điểm dừng của pipeline.
