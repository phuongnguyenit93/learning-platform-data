# Biến đổi phần tử bằng map và xử lý ánh xạ nhiều bước

## 1. Vị trí của map trong pipeline Java Stream

Trong **Java Stream API**, một pipeline thường gồm nguồn dữ liệu, những thao tác trung gian (*intermediate operations*) và một thao tác kết thúc (*terminal operation*). Ở chương **Lọc và biến đổi phần tử**, `filter` quyết định phần tử nào được giữ lại, còn `map` quyết định **mỗi phần tử được biểu diễn thành giá trị mới như thế nào**.

```text
Nguồn Stream<T>
      |
      v
  filter(...)        Chọn phần tử cần xử lý
      |
      v
   map(T -> R)       Biến đổi từng phần tử thành giá trị kiểu R
      |
      v
  Stream<R>
      |
      v
  toList()/collect() Thu kết quả
```

Ví dụ: lấy tên người dùng, bỏ khoảng trắng ở hai đầu, chuẩn hóa chữ thường rồi tạo mã định danh.

```java
import java.util.List;
import java.util.Locale;

List<String> names = List.of("  An  ", "  Bình ", " CHI  ");

List<String> usernames = names.stream()
        .map(String::strip)
        .map(name -> name.toLowerCase(Locale.ROOT))
        .map(name -> "user-" + name)
        .toList();

System.out.println(usernames);
// [user-an, user-bình, user-chi]
```

Ba lời gọi `map` lần lượt chuẩn hóa khoảng trắng, chuẩn hóa kiểu chữ và bổ sung tiền tố. Đó chính là **ánh xạ nhiều bước** (*multi-step mapping*): kết quả bước trước trở thành đầu vào của bước sau, trong cùng một pipeline.

**Kết quả cần đạt sau bài học:**

- Hiểu hợp đồng của `Stream.map`, tính lazy và việc thay đổi kiểu phần tử.
- Biết tổ chức chuỗi nhiều `map` để dễ đọc, tái sử dụng và kiểm soát lỗi.
- Kết hợp `filter`, `map`, `mapToInt` và `collect` trong xử lý dữ liệu thực tế.
- Phân biệt `map` với `flatMap`, tránh tác dụng phụ, lỗi `null` và trạng thái dùng chung.
- Chọn thứ tự xử lý phù hợp với dữ liệu, tính đúng đắn và chi phí tính toán.

Các ví dụ chính dùng **Java 17+** để sử dụng `record`, `String.strip` và `Stream.toList`. `Stream.map` có từ Java 8.

## 2. Hợp đồng của Stream.map

Chữ ký phương thức trong `Stream<T>`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Trong đó:

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử của Stream đầu vào. |
| `R` | Kiểu phần tử của Stream sau biến đổi; có thể giống hoặc khác `T`. |
| `mapper` | Hàm nhận một phần tử `T` và trả về một giá trị `R`. |
| `Stream<R>` | Stream mới mô tả phép biến đổi; chưa phải `List<R>`. |

`map` là **thao tác trung gian, stateless theo hợp đồng sử dụng, và thực thi lazy**. Khi mapper thực sự được gọi cho một phần tử, nó trả về **một** giá trị đầu ra cho phần tử đó. `map` tự nó không bỏ phần tử theo điều kiện và cũng không trải phẳng các collection con.

Ví dụ từ `String` sang `Integer`:

```java
List<String> words = List.of("Java", "Stream", "API");

List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();

System.out.println(lengths); // [4, 6, 3]
```

Sau `map(String::length)`, kiểu logic là `Stream<Integer>`. Từ đây, các thao tác phía sau làm việc với độ dài, chứ không còn trực tiếp nhận chuỗi ban đầu.

Lưu ý: `map` trong `Stream.map(...)` là **tên thao tác ánh xạ**; khác với cấu trúc dữ liệu `java.util.Map<K, V>`. Hai khái niệm cùng tên nhưng giữ vai trò riêng.

## 3. Ánh xạ một bước và nhiều bước

Một mapper có thể biểu diễn bằng lambda hoặc method reference:

```java
List<String> products = List.of("sách", "bút", "vở");

List<String> upper = products.stream()
        .map(value -> value.toUpperCase(Locale.ROOT))
        .toList();

// Tương đương khi muốn gọi toUpperCase() không có tham số:
List<String> upperDefault = products.stream()
        .map(String::toUpperCase)
        .toList();
```

Ở ví dụ tiếp theo, dữ liệu đi qua **ba giai đoạn biến đổi**, mỗi giai đoạn có trách nhiệm cụ thể:

```java
List<String> rawCodes = List.of("  SP 01 ", "Sp 02", "  sp 03 ");

List<String> normalizedCodes = rawCodes.stream()
        .map(String::strip)                                // Bước 1: cắt đầu/cuối
        .map(code -> code.toUpperCase(Locale.ROOT))        // Bước 2: viết hoa
        .map(code -> code.replace(" ", "-"))                // Bước 3: đổi dấu cách
        .toList();

System.out.println(normalizedCodes); // [SP-01, SP-02, SP-03]
```

Việc chia nhiều `map` có ba lợi ích: đọc pipeline theo từng ý nghĩa, dễ thay đổi quy tắc riêng và dễ dùng lại hàm chuẩn hóa.

### Một mapper hợp nhất có được không?

Có thể viết:

```java
List<String> normalizedCodes = rawCodes.stream()
        .map(code -> code.strip()
                .toUpperCase(Locale.ROOT)
                .replace(" ", "-"))
        .toList();
```

Hai cách cho cùng kết quả với dữ liệu này. Dùng nhiều `map` khi các bước có ý nghĩa độc lập hoặc muốn xen `filter` để loại dữ liệu trước bước tốn kém; gộp lại nếu phép biến đổi ngắn và dễ hiểu.

**Không phải mỗi `map` tạo một danh sách trung gian.** Pipeline tuần tự thông thường kết hợp các bước và chuyển từng phần tử qua chúng trong lúc thao tác kết thúc thực thi. Danh sách kết quả chỉ được tạo ở `toList()`. Các thao tác có trạng thái như `sorted` có thể cần bộ đệm riêng.

## 4. Biến đổi kiểu qua nhiều giai đoạn

Ánh xạ nhiều bước không giới hạn trong `String -> String`. Với ứng dụng thực tế, dữ liệu có thể đi qua các kiểu khác nhau:

```text
Stream<String>          Stream<Integer>        Stream<String>
 ["12", "7", "30"] --map(Integer::parseInt)--> [12, 7, 30]
                              --map(n -> "Điểm: " + n)--> ["Điểm: 12", ...]
```

Mã Java tương ứng:

```java
List<String> scoreTexts = List.of("12", "7", "30");

List<String> labels = scoreTexts.stream()
        .map(Integer::parseInt)             // Stream<Integer>
        .map(score -> score * 2)            // Stream<Integer>
        .map(score -> "Điểm: " + score)      // Stream<String>
        .toList();

System.out.println(labels); // [Điểm: 24, Điểm: 14, Điểm: 60]
```

Kiểu sau mỗi bước được suy luận từ `Function` tương ứng. Trình biên dịch kiểm tra rằng bước sau có thể nhận giá trị được bước trước trả về.

Nếu cần lấy nhiều thuộc tính từ một đối tượng, nên ánh xạ trực tiếp sang một kiểu dữ liệu đích rõ ràng. Ví dụ:

```java
record Customer(String id, String fullName, int age) {}
record CustomerLabel(String id, String displayName) {}

List<Customer> customers = List.of(
        new Customer("C01", "  An ", 21),
        new Customer("C02", " Bình  ", 16),
        new Customer("C03", "Chi", 28)
);

List<CustomerLabel> adultLabels = customers.stream()
        .filter(customer -> customer.age() >= 18)
        .map(customer -> new CustomerLabel(
                customer.id(),
                customer.fullName().strip().toUpperCase(Locale.ROOT)
        ))
        .toList();

System.out.println(adultLabels);
// [CustomerLabel[id=C01, displayName=AN], CustomerLabel[id=C03, displayName=CHI]]
```

Ở đây `filter` loại khách dưới 18 tuổi; `map` biến một đối tượng nghiệp vụ thành DTO chỉ chứa thông tin cần trình bày. Đối tượng nguồn không bị sửa đổi.

## 5. Tách các bước phức tạp thành hàm riêng

Với chuỗi ánh xạ dài, các lambda lồng nhau khó kiểm tra. Có thể tạo hàm thuần (*pure function*) với tên phản ánh trách nhiệm:

```java
static String trimAndUppercase(String value) {
    return value.strip().toUpperCase(Locale.ROOT);
}

static String toSlug(String value) {
    return value.toLowerCase(Locale.ROOT).replace(" ", "-");
}

// Trong phương thức khác của cùng lớp:
List<String> slugs = List.of("  Java Stream ", "Lambda API ")
        .stream()
        .map(MyClass::trimAndUppercase)
        .map(MyClass::toSlug)
        .toList();

// [java-stream, lambda-api]
```

Trong đoạn minh họa, `MyClass` là tên lớp chứa hai hàm `static` và câu lệnh tạo `slugs`. Khi dùng trong dự án, thay bằng tên lớp thật; nếu các hàm ở cùng lớp, có thể gọi `MyClass::trimAndUppercase` hoặc dạng method reference thích hợp.

Hàm độc lập cho phép kiểm tra từng quy tắc chuẩn hóa trước khi nối chúng. Với logic nhiều nhánh, dùng tên hàm rõ ràng thường dễ bảo trì hơn một lambda dài.

Không nên chia tách máy móc mọi biểu thức nhỏ. Một `map(String::strip)` riêng đã đủ rõ; nhiều phương thức chỉ làm mã phức tạp hơn nếu không biểu đạt thêm ý nghĩa.

## 6. Kết hợp filter và map đúng thứ tự

`filter` giữ lại phần tử theo `Predicate<T>`, còn `map` biến nó thành `R`. Thứ tự hai thao tác ảnh hưởng tới **ngữ nghĩa** và **chi phí**.

Ví dụ chỉ cần xử lý đơn hàng đã thanh toán:

```java
record Order(String id, int quantity, boolean paid) {}

List<Order> orders = List.of(
        new Order("O01", 2, true),
        new Order("O02", 5, false),
        new Order("O03", 3, true)
);

List<String> paidLabels = orders.stream()
        .filter(Order::paid)                         // Chọn trước
        .map(order -> order.id() + ": " + order.quantity())
        .toList();

System.out.println(paidLabels); // [O01: 2, O03: 3]
```

Nếu việc tạo nhãn tốn kém và không cần xử lý đơn chưa thanh toán, lọc trước sẽ tránh biến đổi thừa.

Ngược lại, khi điều kiện lọc chỉ có nghĩa **sau** chuẩn hóa, cần `map` trước:

```java
List<String> values = List.of("  ", " An ", "  Bình  ");

List<String> nonEmptyNames = values.stream()
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .toList();

System.out.println(nonEmptyNames); // [An, Bình]
```

| Pipeline | Thực hiện khi nào | Điều cần lưu ý |
| --- | --- | --- |
| `filter(...).map(...)` | Điều kiện biết được từ phần tử gốc. | Thường giảm số lượt biến đổi. |
| `map(...).filter(...)` | Điều kiện cần giá trị đã được chuẩn hóa/biến đổi. | Mọi phần tử đi qua bước ánh xạ trước. |
| `map(...).filter(...).map(...)` | Cần chuẩn hóa, loại không hợp lệ, rồi tạo kiểu đầu ra. | Mỗi bước có mục đích riêng. |

Không tự động hoán đổi `filter` và `map`. Hai thứ tự có thể cho kết quả khác nhau; hãy căn cứ vào kiểu dữ liệu và điều kiện nghiệp vụ.

## 7. Từ kiểu đối tượng sang primitive stream

`map(String::length)` trả về `Stream<Integer>`, tức các số nguyên được boxed. Khi mục tiêu là tính tổng, trung bình hoặc thống kê số, dùng `mapToInt`, `mapToLong` hoặc `mapToDouble` thường phù hợp hơn.

```java
List<String> words = List.of("Java", "Stream", "API");

int totalLetters = words.stream()
        .mapToInt(String::length)
        .sum(); // 4 + 6 + 3 = 13

double averageLength = words.stream()
        .mapToInt(String::length)
        .average()
        .orElse(0.0);

System.out.println(totalLetters);   // 13
System.out.println(averageLength); // 4.333333333333333
```

Lúc này pipeline sau `mapToInt` có kiểu `IntStream`. Nó có các thao tác chuyên biệt như `sum`, `average`, `summaryStatistics` và `max`.

Có thể đổi tiếp kiểu dữ liệu:

```java
List<String> labels = words.stream()
        .mapToInt(String::length)       // IntStream
        .map(length -> length * 2)      // IntStream
        .mapToObj(length -> "x2=" + length)  // Stream<String>
        .toList();

System.out.println(labels); // [x2=8, x2=12, x2=6]
```

Nếu muốn trở về `Stream<Integer>`, dùng `boxed()`:

```java
List<Integer> lengths = words.stream()
        .mapToInt(String::length)
        .boxed()
        .toList();
```

`mapToLong` và `mapToDouble` cũng hỗ trợ kiểu primitive tương ứng. Chúng tránh boxing trong quá trình tính toán số nhưng không thay thế kiểm tra tràn số hoặc chọn kiểu số hợp lý theo nghiệp vụ.

## 8. map khác flatMap như thế nào?

Nếu mỗi phần tử đầu vào chứa **một danh sách con**, dùng `map` sẽ tạo Stream của các danh sách:

```java
List<List<String>> teams = List.of(
        List.of("An", "Bình"),
        List.of("Chi"),
        List.of("Dũng", "Hà")
);

List<List<String>> namesByTeam = teams.stream()
        .map(team -> team.stream().map(String::toUpperCase).toList())
        .toList();

// [[AN, BÌNH], [CHI], [DŨNG, HÀ]]
```

Khi cần **một dãy tên phẳng**, dùng `flatMap`:

```java
List<String> allNames = teams.stream()
        .flatMap(List::stream)
        .map(String::toUpperCase)
        .toList();

System.out.println(allNames); // [AN, BÌNH, CHI, DŨNG, HÀ]
```

| Thao tác | Phép biến đổi | Kết quả điển hình |
| --- | --- | --- |
| `map(f)` | Mỗi phần tử được ánh xạ thành **một giá trị** (có thể là collection hoặc Stream). | `Stream<List<String>>` nếu `f` tạo `List<String>`. |
| `flatMap(f)` | Mỗi phần tử được ánh xạ thành một Stream con, rồi trải phẳng các Stream con. | `Stream<String>` từ nhiều danh sách tên. |

Nếu chỉ cần chuẩn hóa một giá trị thành một giá trị khác, `map` là đủ. Khi một đầu vào có thể sinh **0, 1 hoặc nhiều phần tử** và cần đầu ra phẳng, hãy xét `flatMap` hoặc `mapMulti` (Java 16+). Không cần dùng `flatMap` cho bài toán biến đổi một-một đơn giản.

## 9. Giá trị null, lỗi chuyển đổi và Optional

### 9.1. map không tự loại bỏ null

`Stream.map` **có thể trả về `null`** và tiếp tục chứa phần tử `null` trong pipeline. Điều này khác với `Optional.map`, nơi kết quả ánh xạ `null` trở thành `Optional.empty()`.

```java
import java.util.Arrays;
import java.util.Objects;

List<String> raw = Arrays.asList(" An ", null, " Chi ");

List<String> clean = raw.stream()
        .filter(Objects::nonNull)
        .map(String::strip)
        .map(String::toUpperCase)
        .toList();

System.out.println(clean); // [AN, CHI]
```

Nếu bỏ `filter(Objects::nonNull)`, `String::strip` sẽ ném `NullPointerException` khi gặp phần tử `null`. Các factory `List.of(...)` không nhận phần tử `null`, nên ví dụ cố ý dùng `Arrays.asList`.

Khi một phép `map` có thể sinh `null`, vẫn cần quyết định bước tiếp theo phải làm gì:

```java
List<String> mapped = List.of("A", "X", "B").stream()
        .map(code -> code.equals("X") ? null : code.toLowerCase(Locale.ROOT))
        .filter(Objects::nonNull)
        .toList();

System.out.println(mapped); // [a, b]
```

Với mã nghiệp vụ, nên cân nhắc mô hình kết quả rõ ràng như `Optional` hoặc đối tượng biểu diễn trạng thái lỗi để tránh tạo `null` âm thầm.

### 9.2. Lỗi parse dừng pipeline

`Integer.parseInt` ném `NumberFormatException` nếu chuỗi không hợp lệ:

```java
List<String> amounts = List.of("10", "oops", "25");

// Sẽ lỗi tại phần tử "oops" khi thao tác kết thúc được thực thi.
List<Integer> parsed = amounts.stream()
        .map(Integer::parseInt)
        .toList();
```

Với yêu cầu **bỏ qua đầu vào không thể chuyển đổi**, có thể viết hàm hỗ trợ:

```java
static Optional<Integer> tryParseInt(String raw) {
    try {
        return Optional.of(Integer.parseInt(raw));
    } catch (NumberFormatException exception) {
        return Optional.empty();
    }
}

// Ví dụ trong cùng lớp:
List<Integer> parsed = List.of("10", "oops", "25").stream()
        .map(MyClass::tryParseInt)        // Stream<Optional<Integer>>
        .flatMap(Optional::stream)        // Chỉ giữ các Optional có giá trị
        .toList();

System.out.println(parsed); // [10, 25]
```

`MyClass` là tên lớp chứa hàm `tryParseInt`. `Optional::stream` có từ Java 9. Khi dữ liệu không hợp lệ là vấn đề cần báo cáo, không nên chỉ bỏ qua: hãy thu thập lỗi theo một cấu trúc kết quả riêng để truy vết và thông báo.

## 10. Tính lazy và tác dụng phụ của mapper

`map` không chạy ngay khi được khai báo:

```java
Stream<String> pipeline = List.of("a", "b", "c").stream()
        .map(value -> {
            System.out.println("map: " + value);
            return value.toUpperCase(Locale.ROOT);
        });

// Đến đây chưa có thao tác kết thúc, nên chưa thực hiện ánh xạ.
List<String> result = pipeline.toList();
// Bây giờ mới xử lý các phần tử và thu được [A, B, C].
```

Không nên đặt cập nhật dữ liệu quan trọng bên trong mapper. Stream có thể dừng sớm nhờ `findFirst`, `anyMatch`, `limit` hoặc bỏ qua một số thao tác trung gian khi kết quả có thể xác định mà không cần tính từng phần tử. Ví dụ, với nguồn `SIZED` và `count()`, một `map` không cần thiết có thể không được gọi.

```java
long count = List.of("a", "b", "c").stream()
        .map(value -> {
            System.out.println("Có thể không in: " + value);
            return value.toUpperCase(Locale.ROOT);
        })
        .count();

System.out.println(count); // 3
```

Nếu cần chuyển đổi dữ liệu, hãy **trả về giá trị mới** thay vì sửa collection nguồn:

```java
List<StringBuilder> builders = List.of(
        new StringBuilder("A"),
        new StringBuilder("B")
);

// Không nên: mapper sửa trạng thái các đối tượng nguồn.
List<StringBuilder> changed = builders.stream()
        .map(builder -> builder.append("-done"))
        .toList();

// Nên: tạo String đầu ra, không sửa StringBuilder gốc.
List<String> safe = builders.stream()
        .map(builder -> builder.toString() + "-done")
        .toList();
```

Đoạn `changed` là **minh họa phản ví dụ**, không chạy nó trước đoạn `safe` nếu muốn giữ nguyên giá trị nguồn. Mapper có tác dụng phụ gây khó dự đoán khi chạy song song, tái sử dụng dữ liệu hoặc kết hợp các bước khác.

### Ánh xạ song song

`parallelStream()` cho phép framework xử lý phần tử trên nhiều thread:

```java
List<Integer> squares = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * n)
        .toList();

System.out.println(squares); // [1, 4, 9, 16]
```

Với nguồn có *encounter order* như `List`, `toList` giữ thứ tự đó ngay cả khi mapper chạy song song. **Thứ tự gọi mapper giữa các thread không được bảo đảm.** Không dùng biến đếm chung, `ArrayList` dùng chung trong mapper hay logic phụ thuộc phần tử nào hoàn thành trước. Phép biến đổi nên không trạng thái, không can thiệp nguồn, không phụ thuộc thứ tự thực thi.

Đối với pipeline nhỏ và mapper rẻ, tạo thêm chi phí phân luồng có thể khiến `parallelStream` chậm hơn. Hãy đánh giá dựa vào khối lượng và phép biến đổi thực tế.

## 11. Ánh xạ trước khi collect hoặc grouping

`map` thường được dùng để chuẩn bị dữ liệu trước khi `collect`:

```java
List<String> products = List.of("  Bút ", " Sách", " Vở  ");

Set<String> normalized = products.stream()
        .map(String::strip)
        .map(name -> name.toUpperCase(Locale.ROOT))
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(normalized); // [BÚT, SÁCH, VỞ]
```

Khi gom nhóm cần giữ đối tượng ban đầu nhưng chỉ biến đổi giá trị **bên trong mỗi nhóm**, `Collectors.mapping` cũng hữu ích:

```java
record Student(String group, String name) {}

List<Student> students = List.of(
        new Student("A", " An "),
        new Student("B", " Chi "),
        new Student("A", " Bình ")
);

Map<String, List<String>> namesByGroup = students.stream()
        .collect(Collectors.groupingBy(
                Student::group,
                Collectors.mapping(
                        student -> student.name().strip(),
                        Collectors.toList()
                )
        ));

// A -> [An, Bình]; B -> [Chi]. Thứ tự khóa Map không được bảo đảm.
```

`Stream.map` biến đổi tất cả phần tử của luồng **trước** terminal operation; `Collectors.mapping` là một downstream collector biến đổi phần tử **trong quá trình thu thập** của collector khác, thường dùng kết hợp `groupingBy` hoặc `partitioningBy`.

Nếu cần một pipeline nhiều bước với những nhánh điều kiện, hãy ưu tiên diễn đạt rõ ý nghĩa nghiệp vụ. Những thao tác như `sorted`, `distinct` hay `collect` có yêu cầu trạng thái, thứ tự và bộ nhớ khác với `map`.

## 12. Ví dụ hoàn chỉnh: chuẩn hóa và trình bày đơn hàng

Một hệ thống nhận đơn hàng dạng thô: mã đơn, tên khách, số tiền dạng chuỗi và trạng thái thanh toán. Nhiệm vụ là chỉ lấy đơn đã thanh toán, chuẩn hóa thông tin, tạo đối tượng hiển thị rồi cộng tổng tiền theo khách.

Ví dụ có thể biên dịch và chạy với Java 17+:

```java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class MultiStepMappingDemo {
    record RawOrder(String id, String customer, String amountText, boolean paid) {}
    record CleanOrder(String id, String customer, BigDecimal amount) {}
    record OrderView(String id, String customer, BigDecimal amount) {}

    public static void main(String[] args) {
        List<RawOrder> rawOrders = List.of(
                new RawOrder("O-01", " An ", "120000", true),
                new RawOrder("O-02", "Bình", "50000", false),
                new RawOrder("O-03", " Chi ", "80000", true),
                new RawOrder("O-04", " an ", "30000", true)
        );

        List<OrderView> paidOrders = rawOrders.stream()
                .filter(RawOrder::paid)
                .map(raw -> new CleanOrder(
                        raw.id().strip(),
                        raw.customer().strip().toUpperCase(Locale.ROOT),
                        new BigDecimal(raw.amountText().strip())
                ))
                .filter(clean -> clean.amount().signum() > 0)
                .map(clean -> new OrderView(
                        clean.id(),
                        clean.customer(),
                        clean.amount()
                ))
                .toList();

        Map<String, BigDecimal> totalsByCustomer = paidOrders.stream()
                .collect(Collectors.toMap(
                        OrderView::customer,
                        OrderView::amount,
                        BigDecimal::add,
                        LinkedHashMap::new
                ));

        System.out.println(paidOrders);
        // [OrderView[id=O-01, customer=AN, amount=120000],
        //  OrderView[id=O-03, customer=CHI, amount=80000],
        //  OrderView[id=O-04, customer=AN, amount=30000]]

        System.out.println(totalsByCustomer);
        // {AN=150000, CHI=80000}
    }
}
```

Trong pipeline này:

1. `filter(RawOrder::paid)` loại đơn chưa thanh toán trước khi chuyển đổi.
2. `map(RawOrder -> CleanOrder)` chuẩn hóa chuỗi và đổi số tiền sang `BigDecimal`.
3. `filter(CleanOrder)` kiểm tra số tiền dương trên dữ liệu đã được parse.
4. `map(CleanOrder -> OrderView)` tạo dạng hiển thị với các trường cần dùng.
5. `toList()` là thao tác kết thúc; `Collectors.toMap` trên danh sách mới cộng tiền các khách trùng tên chuẩn hóa bằng `BigDecimal::add`.

Ví dụ giả định đầu vào hợp lệ và không có trường `null`. Trong ứng dụng thực tế, validate các trường và xử lý lỗi parse trước khi tạo `BigDecimal`; chọn chính sách gộp tên khách theo định danh bền vững (ví dụ customer ID) nếu tên không đủ để phân biệt khách.

## 13. Sai lầm thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `map` xong nhưng kiểu dữ liệu không phù hợp bước sau | Không theo dõi `Stream<T> -> Stream<R>` | Xác định kiểu sau từng phép ánh xạ. |
| `map` cho ra `Stream<List<T>>` thay vì danh sách phần tử phẳng | Cần trải nhiều phần tử từ mỗi đầu vào | Cân nhắc `flatMap`. |
| `NullPointerException` trong method reference | Nguồn có `null` hoặc bước trước sinh `null` | Lọc/kiểm tra `null` và quy định dữ liệu thiếu. |
| `NumberFormatException` từ parse | Đầu vào sai định dạng | Validate, tách kết quả thành công/thất bại hoặc dùng `Optional` có chủ đích. |
| Dữ liệu nguồn bị thay đổi sau pipeline | Mapper sửa đối tượng/collection đang duyệt | Tạo đối tượng kết quả độc lập, không viết vào nguồn. |
| Số lần log trong mapper không như mong đợi | Pipeline lazy, dừng sớm hoặc tối ưu bỏ bước | Không dùng mapper làm cơ chế tác dụng phụ bắt buộc. |
| Sai thứ tự hoặc sai số khi chạy song song | Mapper dựa vào trạng thái ngoài, biến đếm dùng chung | Viết hàm ánh xạ không trạng thái; dùng collector phù hợp. |
| Pipeline khó đọc | Quá nhiều biểu thức lồng nhau, quy tắc trộn lẫn | Đặt tên bước và tách hàm chuyển đổi có ý nghĩa. |

## 14. Bài tập và lời giải tham khảo

Cho danh sách dữ liệu thô:

```java
List<String> prices = List.of(" 100 ", " 250 ", " 75 ", " 300 ");
```

**Yêu cầu:** Chuẩn hóa khoảng trắng, chuyển thành số nguyên, chỉ giữ giá trị từ 100 trở lên, tăng thuế minh họa 10% và tạo các nhãn `"Giá sau thuế: ..."`. Giả sử mọi chuỗi đều chứa số nguyên hợp lệ.

Lời giải:

```java
List<String> labels = prices.stream()
        .map(String::strip)                       // Stream<String>
        .map(Integer::parseInt)                   // Stream<Integer>
        .filter(price -> price >= 100)            // Giữ 100, 250, 300
        .map(price -> price * 110 / 100)          // Tính minh họa trên số nguyên
        .map(price -> "Giá sau thuế: " + price)    // Stream<String>
        .toList();

System.out.println(labels);
// [Giá sau thuế: 110, Giá sau thuế: 275, Giá sau thuế: 330]
```

**Tự mở rộng:** Nếu `prices` có giá trị `"không rõ"`, điều gì xảy ra ở `Integer::parseInt`? Hãy sử dụng `Optional<Integer>` và `flatMap(Optional::stream)` như mục 9 để xử lý dữ liệu không hợp lệ theo chính sách phù hợp.

Lưu ý phép `price * 110 / 100` chỉ để minh họa biến đổi nhiều bước với số nguyên: nó có thể bị tràn số và làm tròn xuống. Với số tiền thật, hãy sử dụng `BigDecimal` và quy tắc làm tròn được nghiệp vụ quy định.

## Ghi nhớ

`map` chuyển mỗi phần tử của Stream sang một giá trị mới, có thể thay đổi kiểu dữ liệu. Nối nhiều `map` giúp mô tả rõ từng giai đoạn chuẩn hóa, parse và tạo đối tượng đầu ra; `filter` được đặt theo điều kiện có nghĩa trước hoặc sau bước ánh xạ tương ứng. Pipeline vẫn lazy và không tự tạo một danh sách ở từng `map`. Khi một phần tử cần sinh nhiều phần tử phẳng, dùng `flatMap`; khi xử lý số, cân nhắc `mapToInt` và các primitive stream. Hãy giữ mapper không trạng thái, tránh sửa nguồn, xử lý `null`/lỗi chuyển đổi rõ ràng và chỉ dùng song song khi có lợi ích được kiểm chứng.
