# Collectors.joining trong xử lý Stream

`Collectors.joining` là collector dùng ở bước cuối của một `Stream` để **ghép các phần tử dạng văn bản thành một `String`**. Nó đặc biệt hữu ích khi dữ liệu phải đi qua các thao tác `filter`, `map` hoặc `sorted` trước khi kết hợp: thay vì tự duyệt, nối chuỗi và quản lý dấu phân cách, ta mô tả toàn bộ quá trình thành một pipeline.

Bài này tập trung vào việc ghép nhiều phần bằng `Collectors.joining`, cách kiểm soát dấu phân cách và phần bao ngoài, cũng như các tình huống dễ cho kết quả ngoài dự kiến.

## 1. Cách dùng cơ bản

Các phương thức `joining` nằm trong `java.util.stream.Collectors`. Ba overload được dùng nhiều nhất:

| Biểu thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `Collectors.joining()` | `"ABC"` | Ghép liên tiếp, không thêm dấu phân cách. |
| `Collectors.joining(", ")` | `"A, B, C"` | Chèn `", "` **giữa** hai phần tử liên tiếp. |
| `Collectors.joining(", ", "[", "]")` | `"[A, B, C]"` | Thêm dấu phân cách, đồng thời bao **toàn bộ kết quả** bằng tiền tố và hậu tố. |

Ví dụ với dữ liệu có thứ tự:

```java
List<String> parts = List.of("A", "B", "C");

String text = parts.stream()
        .collect(Collectors.joining(" - "));
// text = "A - B - C"
```

Đây là **đoạn minh họa**: để chạy độc lập cần đặt nó trong phương thức Java và import `java.util.List`, `java.util.stream.Collectors`. Chương trình hoàn chỉnh có ở mục 4.

Phần tử trong stream cần tương thích với `CharSequence` (thường là `String`). Vì vậy có thể thu thập trực tiếp `Stream<String>` hoặc `Stream<CharSequence>`; với `Stream<Integer>` hay stream đối tượng, cần chuyển thành chuỗi trước khi thu thập.

## 2. Hiểu đúng các tham số

### 2.1. `joining()`: nối sát nhau

`Stream.of("Ja", "va", " 17").collect(Collectors.joining())` tạo `"Java 17"`. Collector không tự thêm khoảng trắng, dấu phẩy hoặc ký tự xuống dòng.

### 2.2. `joining(delimiter)`: dấu ngăn cách ở giữa

Với `joining(" | ")`, dấu `" | "` xuất hiện giữa các phần tử, không tự xuất hiện ở đầu hoặc cuối. Dấu phân cách là **văn bản thông thường**, không phải biểu thức chính quy (regex); chẳng hạn `joining(".")` chèn dấu chấm thật, không có ý nghĩa “mọi ký tự” như dấu chấm trong regex.

Để ghép thành nhiều dòng, dùng `joining("\n")`. Kết quả chứa ký tự xuống dòng giữa các phần tử. Nếu một phần tử vốn đã chứa `\n`, ký tự đó vẫn được giữ; `joining` không tự chuẩn hóa nội dung.

### 2.3. `joining(delimiter, prefix, suffix)`: bao kết quả một lần

`Stream.of("x", "y").collect(Collectors.joining(", ", "(", ")"))` trả về `"(x, y)"`.

- `delimiter` được chèn **giữa** các phần tử.
- `prefix` được chèn **một lần trước toàn bộ** chuỗi.
- `suffix` được chèn **một lần sau toàn bộ** chuỗi.

Vì vậy `joining(", ", "[", "]")` tạo dạng danh sách `[a, b]`; nó không tạo `[a], [b]`. Nếu cần định dạng từng phần tử, hãy định dạng bằng `map` trước khi `collect`.

## 3. Cơ chế trong Stream pipeline

Hình dung pipeline sau:

```java
String result = Stream.of("  Mai ", "", " Nam ", "  Lan ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.joining(" / "));
// result = "Mai / Nam / Lan"
```

Diễn biến logic:

1. `Stream.of(...)` cung cấp các phần tử nguồn theo thứ tự đã khai báo.
2. `map(String::trim)` tạo dạng đã loại khoảng trắng hai đầu của **từng** chuỗi.
3. `filter(s -> !s.isEmpty())` bỏ phần tử rỗng sau khi trim.
4. `collect(Collectors.joining(" / "))` là **terminal operation**: stream được tiêu thụ, các chuỗi còn lại được ghép thành một kết quả.

`map` và `filter` là intermediate operations; chúng chỉ thực sự được thực thi khi terminal operation được gọi. `joining` tự xử lý việc chèn delimiter và tích lũy thành một giá trị cuối, nên không cần nối thủ công bằng `reduce((a, b) -> a + ", " + b)`.

Sau khi `collect` chạy, stream đó không được dùng lại cho một terminal operation khác; muốn tính kết quả khác thì tạo stream mới từ nguồn. Danh sách nguồn không bị thay đổi bởi pipeline trên.

## 4. Chương trình Java 17+ chạy độc lập

Lưu đúng tên tệp `JoiningDemo.java` (sử dụng UTF-8):

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningDemo {
    record Member(String team, String name) {}

    public static void main(String[] args) {
        List<String> fruits = List.of("táo", "cam", "lê");

        System.out.println(fruits.stream()
                .collect(Collectors.joining()));
        System.out.println(fruits.stream()
                .collect(Collectors.joining(" | ")));
        System.out.println(fruits.stream()
                .collect(Collectors.joining(", ", "[", "]")));

        System.out.println(Stream.<String>empty()
                .collect(Collectors.joining(", ", "[", "]")));
        System.out.println(Stream.of("", "")
                .collect(Collectors.joining(",")));

        List<String> rawNames =
                Arrays.asList("  An  ", null, "", " Bình ", "  Chi ");

        String cleanNames = rawNames.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.joining(" / "));
        System.out.println(cleanNames);

        String numbers = Stream.of(10, 20, 30)
                .map(i -> Integer.toString(i))
                .collect(Collectors.joining(" + ", "(", ")"));
        System.out.println(numbers);

        List<Member> members = List.of(
                new Member("Backend", "An"),
                new Member("Frontend", "Bình"),
                new Member("Backend", "Chi")
        );

        Map<String, String> namesByTeam = members.stream()
                .collect(Collectors.groupingBy(
                        Member::team,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Member::name,
                                Collectors.joining(", ")
                        )
                ));

        namesByTeam.forEach((team, names) ->
                System.out.println(team + ": " + names));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 JoiningDemo.java
java JoiningDemo
```

Kết quả chuẩn (dòng thứ năm chỉ có **một dấu phẩy**):

```text
táocamlê
táo | cam | lê
[táo, cam, lê]
[]
,
An / Bình / Chi
(10 + 20 + 30)
Backend: An, Chi
Frontend: Bình
```

**Giải thích các trường hợp đáng chú ý:**

- Ba lệnh đầu khác nhau duy nhất ở overload của `joining`: nối sát nhau; thêm dấu ngăn cách; hoặc thêm cả cặp ngoặc vuông.
- Stream rỗng với `joining(", ", "[", "]")` vẫn trả về `"[]"`. Các dấu bao không bị bỏ đi chỉ vì không có phần tử.
- Stream có **hai chuỗi rỗng** không phải stream rỗng: giữa hai phần tử vẫn có một delimiter `","`.
- `Objects::nonNull` được đặt **trước** `String::trim` để không gọi phương thức trên tham chiếu `null`. Sau đó `filter` bỏ chuỗi rỗng.
- Các giá trị `Integer` được chuyển thành `String` bằng `map` trước khi đưa vào collector.
- `Collectors.mapping(Member::name, Collectors.joining(", "))` dùng `joining` như **downstream collector** của `groupingBy`. Từng nhóm có một chuỗi tên riêng; `LinkedHashMap` giữ thứ tự xuất hiện đầu tiên của các nhóm trong ví dụ tuần tự này.

## 5. Các trường hợp biên cần biết

| Đầu vào hoặc thao tác | Kết quả / hành vi cần nhớ |
| --- | --- |
| `Stream.<String>empty().collect(joining())` | Chuỗi rỗng `""`. |
| `Stream.<String>empty().collect(joining(",", "{", "}"))` | `"{}"`: prefix và suffix vẫn được thêm. |
| `Stream.of("a").collect(joining(","))` | `"a"`: không có delimiter vì chỉ một phần tử. |
| `Stream.of("", "").collect(joining("-"))` | `"-"`: hai phần tử rỗng có một delimiter ở giữa. |
| `Stream.of("a", "b").collect(joining(""))` | `"ab"`: delimiter rỗng tương tự nối sát. |
| `Stream.of("a", null, "b").collect(joining(","))` | `"a,null,b"`: `null` được biểu diễn bằng văn bản `"null"`. |
| `Stream.of("a", "b").collect(joining(",", "[", "]"))` | `"[a,b]"`, không có dấu phẩy ở cuối. |

Các biểu thức trong bảng dùng `Collectors.joining` theo dạng viết rút gọn `joining` để dễ nhìn. Khi viết mã thực tế, có thể gọi đầy đủ `Collectors.joining(...)` hoặc thêm `import static java.util.stream.Collectors.joining;`.

### 5.1. Xử lý `null` theo ý nghĩa nghiệp vụ

`Collectors.joining` không loại bỏ phần tử `null`. Khi phần tử null đi vào collector, văn bản `"null"` có thể xuất hiện trong kết quả. Chọn cách xử lý **trước** khi joining:

```java
// Bỏ giá trị null:
String a = Stream.of("An", null, "Bình")
        .filter(Objects::nonNull)
        .collect(Collectors.joining(", "));
// "An, Bình"

// Thay giá trị null bằng nhãn chủ động:
String b = Stream.of("An", null, "Bình")
        .map(s -> s == null ? "(chưa có)" : s)
        .collect(Collectors.joining(", "));
// "An, (chưa có), Bình"
```

Đừng dùng `map(String::trim)` hoặc `map(Object::toString)` khi nguồn có thể có `null` mà chưa lọc hay xử lý null.

### 5.2. Phần tử rỗng, khoảng trắng và delimiter

`joining` không tự cắt khoảng trắng, loại chuỗi rỗng, bỏ trùng hay sắp xếp. Ví dụ dữ liệu `" An "` và `"Bình "` với `joining(", ")` vẫn giữ nguyên khoảng trắng trong phần tử. Khi muốn chuẩn hóa, thứ tự thường là **lọc null → chuẩn hóa bằng map → lọc rỗng → ghép**.

Nếu một phần tử có sẵn ký tự phân cách (ví dụ tên `"An, Bình"`), `joining(",")` vẫn giữ nguyên dấu phẩy trong tên. Nó không escape hay quote cho CSV. Khi xuất CSV/TSV hoặc định dạng yêu cầu escape, cần xử lý quy tắc định dạng riêng cho **từng giá trị** trước khi ghép; không thể mặc định đầu ra `joining(",")` là CSV hợp lệ.

### 5.3. Thứ tự phần tử

`joining` nối theo **encounter order**, nếu stream có thứ tự xác định. `List.stream()` và `Stream.of(...)` là những nguồn thường giữ thứ tự này. Nếu bắt đầu từ một nguồn không đảm bảo thứ tự (ví dụ `HashSet`), hoặc chủ động dùng `unordered()`, đừng giả định chuỗi được ghép theo thứ tự cụ thể.

Khi phải có thứ tự rõ ràng, hãy sử dụng nguồn có thứ tự hoặc gọi `sorted()` / `sorted(comparator)` thích hợp trước `collect`. Với stream song song từ nguồn có encounter order, `joining` vẫn thu kết quả theo encounter order, nhưng thường không mang lại lợi ích tốc độ trên tập dữ liệu nhỏ; không cần tự thay thế collector bằng một `StringBuilder` dùng chung giữa các thread.

## 6. Ghép dữ liệu sau `map` và trong collector khác

`joining` nhận những phần tử đã trở thành văn bản. Nhờ đó ta có thể kiểm soát cách hiển thị **từng** đối tượng trước khi thêm delimiter:

```java
record Product(String code, int quantity) {}

List<Product> products = List.of(
        new Product("P01", 2),
        new Product("P02", 5)
);

String summary = products.stream()
        .map(p -> p.code() + " x" + p.quantity())
        .collect(Collectors.joining("; ", "Đơn hàng: ", "."));
// "Đơn hàng: P01 x2; P02 x5."
```

Đây là đoạn minh họa đặt trong ngữ cảnh có `List` và `Collectors` đã import. `map` tạo một chuỗi biểu diễn cho mỗi `Product`; prefix `"Đơn hàng: "` và suffix `"."` bao cả chuỗi kết quả, không áp dụng riêng cho từng sản phẩm.

Trong `groupingBy`, collector phía sau có thể là `Collectors.mapping(..., Collectors.joining(...))`, như chương trình ở mục 4. Ý tưởng là: **gom nhóm đối tượng → lấy thuộc tính cần hiển thị trong mỗi nhóm → nối thuộc tính trong nhóm**. Điều này khác với gọi `joining` một lần trên toàn bộ stream, vốn chỉ tạo một `String` chung.

## 7. Chọn giữa `Collectors.joining` và cách ghép khác

| Công cụ | Dùng khi nào |
| --- | --- |
| `stream.collect(Collectors.joining(...))` | Đã có pipeline `Stream` với `filter`/`map`/`sorted`; cần một chuỗi tổng hợp cuối. |
| `String.join(delimiter, elements)` | Đã có các chuỗi trong `Iterable` hoặc các đối số chuỗi; không cần pipeline stream. |
| `StringJoiner` | Muốn thêm phần tử từng bước thủ công, nhưng vẫn cần delimiter, prefix và suffix. |
| `StringBuilder` | Có luồng xử lý hoặc bố cục nối chuỗi tùy biến, nhiều điều kiện chèn nội dung, hoặc cần điều khiển từng thao tác append. |

Cả `String.join` và `Collectors.joining` đều hỗ trợ delimiter, nhưng `String.join` không nhận sẵn chuỗi thao tác `filter`/`map` trong một terminal collector. So với tự `reduce` chuỗi bằng phép cộng, `Collectors.joining` diễn đạt trực tiếp mục tiêu ghép văn bản và sử dụng bộ tích lũy phù hợp.

Kết quả của `joining` luôn là một `String` mới về mặt giá trị logic; không sửa các `String` nguồn. Việc thu toàn bộ stream thành một chuỗi cần giữ nội dung kết quả trong bộ nhớ. Nếu dữ liệu khổng lồ và yêu cầu ghi liên tục ra tệp/socket, cân nhắc ghi tuần tự vào `Writer`/`BufferedWriter` thay vì tích lũy toàn bộ văn bản vào một `String`.

## 8. Các lỗi thường gặp và cách sửa

**Lỗi 1 — Ghép stream số nguyên trực tiếp**

```java
// Không biên dịch: joining cần phần tử phù hợp CharSequence.
// Stream.of(1, 2, 3).collect(Collectors.joining(", "));

// Đúng:
String result = Stream.of(1, 2, 3)
        .map(String::valueOf)
        .collect(Collectors.joining(", "));
// "1, 2, 3"
```

**Lỗi 2 — Mong prefix/suffix bao từng phần tử**

`joining(", ", "[", "]")` ghép thành `"[a, b]"`. Nếu muốn `"[a], [b]"`, hãy dùng:

```java
String result = Stream.of("a", "b")
        .map(s -> "[" + s + "]")
        .collect(Collectors.joining(", "));
// "[a], [b]"
```

**Lỗi 3 — Có dấu phân cách dư vì dữ liệu đầu vào rỗng**

Với `Stream.of("a", "", "b")`, `joining(",")` cho `"a,,b"`, bởi phần tử rỗng vẫn được tính. Lọc bằng `filter(s -> !s.isEmpty())` nếu nghiệp vụ muốn bỏ nó; với chuỗi toàn khoảng trắng, có thể cần `trim` hoặc `strip` trước khi lọc.

**Lỗi 4 — Kết quả thay đổi thứ tự giữa các lần chạy**

Kiểm tra thứ tự của nguồn; một `HashSet` không bảo đảm encounter order. Nếu cần kết quả lặp lại có thứ tự, dùng `List` hoặc sắp xếp rõ ràng trước khi joining.

**Lỗi 5 — Xem delimiter là cú pháp định dạng dữ liệu**

`joining` chỉ chèn văn bản, không tự escape dấu ngoặc kép, dấu phẩy, xuống dòng trong một giá trị hay chống SQL injection. Khi tạo CSV, JSON, SQL hoặc HTML, dùng cách mã hóa/thư viện phù hợp với định dạng đầu ra; đặc biệt không dựng câu lệnh SQL chứa dữ liệu người dùng bằng `joining`.

## 9. Tự kiểm tra hiểu bài

Giả sử:

```java
List<String> words = List.of(" java ", "", "stream", " java ");
String output = words.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .distinct()
        .collect(Collectors.joining(" + ", "<", ">"));
```

`output` bằng `"<java + stream>"`: `trim` loại khoảng trắng ngoài, `filter` bỏ chuỗi rỗng, `distinct` giữ lần xuất hiện đầu tiên của mỗi chuỗi theo encounter order, sau đó `joining` chèn dấu `" + "` và bao toàn bộ bằng `<`, `>`.

Khi đọc một pipeline `Collectors.joining`, hãy lần lượt xác định **các phần tử còn lại sau thao tác trung gian**, **thứ tự của chúng**, **delimiter**, rồi **prefix/suffix**. Bốn yếu tố này quyết định phần lớn kết quả ghép chuỗi.
