# String.join với mảng hoặc Iterable

## 1. Mục tiêu bài học

Khi có nhiều đoạn văn bản như tên cột, thẻ, đường dẫn logic hoặc các thành phần thông báo, ta thường muốn ghép chúng thành **một chuỗi** và chèn cùng một dấu phân cách giữa các phần tử. `String.join(...)` giải quyết đúng tình huống đó: nhận một `delimiter` và nhiều phần tử kiểu `CharSequence`, rồi trả về một `String` mới.

Sau bài này, bạn có thể:
- Chọn đúng overload `String.join` cho **mảng**, **danh sách/Iterable** hoặc các tham số rời.
- Dự đoán kết quả khi danh sách rỗng, có một phần tử, có `null` hoặc dấu phân cách rỗng.
- Biết khi nào cần xử lý dữ liệu trước khi ghép và khi nào chuyển sang `StringJoiner` hoặc `Collectors.joining`.

## 2. Hai overload cần biết

Từ Java 8, lớp `java.lang.String` cung cấp hai phương thức tĩnh:

```java
public static String join(CharSequence delimiter, CharSequence... elements);

public static String join(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements);
```

Trong đó:
- `delimiter` là chuỗi/dãy ký tự chèn **giữa hai phần tử liên tiếp**, không tự thêm vào đầu hoặc cuối.
- `elements` là các phần tử cần ghép, theo đúng thứ tự được truyền vào hoặc thứ tự mà `Iterable` duyệt qua.
- Giá trị trả về là `String` mới; thao tác không thay đổi mảng, collection hay bản thân các phần tử.
- `CharSequence` là giao diện mà `String`, `StringBuilder` và `StringBuffer` triển khai. Vì thế tham số không bắt buộc phải có kiểu chính xác là `String`.

| Dữ liệu đầu vào | Cách gọi | Overload được chọn |
| --- | --- | --- |
| Các phần tử rời | `String.join("-", "A", "B", "C")` | `CharSequence...` |
| `String[]` | `String.join("-", array)` | `CharSequence...`, truyền cả mảng |
| `List<String>` | `String.join("-", list)` | `Iterable<? extends CharSequence>` |
| `Set<String>` | `String.join("-", set)` | `Iterable<? extends CharSequence>` |
| `Iterable<StringBuilder>` | `String.join("-", items)` | `Iterable<? extends CharSequence>` |

**Phân biệt cú pháp:** dấu `...` trong khai báo Java là *varargs*; trong lời gọi, bạn có thể truyền các phần tử rời hoặc một mảng đối tượng tương thích. Với `List`, `Set` hay một `Iterable` tự tạo, Java dùng overload thứ hai.

## 3. Ví dụ hoàn chỉnh: mảng, Iterable và varargs

Tạo tệp `JoinDemo.java` với mã sau (Java 17+):

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class JoinDemo {
    public static void main(String[] args) {
        String[] words = {"Java", "Core", "String"};
        List<String> colors = List.of("đỏ", "xanh", "vàng");
        Set<String> ordered = new LinkedHashSet<>(List.of("A", "B", "C"));

        System.out.println("array: " + String.join(" / ", words));
        System.out.println("list: " + String.join(", ", colors));
        System.out.println("set: " + String.join(" -> ", ordered));
        System.out.println("varargs: " +
                String.join(".", "java", "lang", "String"));
        System.out.println("empty: [" +
                String.join(", ", new String[0]) + "]");
        System.out.println("one: " +
                String.join(" | ", new String[]{"solo"}));
        System.out.println("null item: " +
                String.join(", ", Arrays.asList("A", null, "C")));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 JoinDemo.java
java JoinDemo
```

Kết quả chuẩn:

```text
array: Java / Core / String
list: đỏ, xanh, vàng
set: A -> B -> C
varargs: java.lang.String
empty: []
one: solo
null item: A, null, C
```

Các điểm cần quan sát:
1. Mảng `words` có ba phần tử nên dấu ` / ` xuất hiện **hai lần**.
2. `colors` là `List<String>`, được xử lý thông qua `Iterable` mà không cần chuyển thành mảng.
3. `LinkedHashSet` giữ thứ tự chèn `A, B, C` nên kết quả trên có thứ tự xác định; `HashSet` nói chung không hứa hẹn cùng thứ tự đó.
4. Lời gọi `String.join(".", "java", "lang", "String")` sử dụng varargs trực tiếp.
5. Mảng rỗng trả chuỗi rỗng; ký hiệu `[]` xuất hiện chỉ vì ta tự ghép vào lệnh `println` để dễ quan sát.
6. Phần tử `null` trong danh sách được chuyển thành văn bản `"null"`; đây không phải thao tác bỏ qua phần tử.

## 4. Cơ chế ghép và quy tắc kết quả

Xét lời gọi:

```java
String result = String.join(" | ", "A", "B", "C");
```

Ta có thể hình dung quá trình là `A` + `" | "` + `B` + `" | "` + `C`, tạo `"A | B | C"`. Dấu phân cách được chèn **n − 1 lần** khi có `n >= 1` phần tử. `String.join` sử dụng cơ chế ghép nội bộ của thư viện Java, nên ta không cần tự nối lặp `result += ...`.

| Trường hợp | Ví dụ | Giá trị trả về |
| --- | --- | --- |
| Không phần tử | `String.join(",", new String[0])` | `""` |
| Một phần tử | `String.join(",", "A")` | `"A"` |
| Nhiều phần tử | `String.join(",", "A", "B")` | `"A,B"` |
| Dấu phân cách rỗng | `String.join("", "A", "B")` | `"AB"` |
| Dấu phân cách nhiều ký tự | `String.join(" -> ", "A", "B")` | `"A -> B"` |
| Phần tử rỗng | `String.join(",", "A", "", "B")` | `"A,,B"` |
| Phần tử `null` | `String.join(",", "A", (CharSequence) null)` | `"A,null"` |

**Lưu ý:** `String.join` **không** tự cắt khoảng trắng, lọc phần tử rỗng, loại trùng, sắp xếp hoặc escape ký tự phân cách bên trong từng phần tử. Ví dụ, `String.join(",", "a,b", "c")` trả `"a,b,c"`, không giữ lại thông tin nhóm ban đầu khi tách bằng dấu phẩy đơn thuần.

### Phân biệt `null` ở từng vị trí

- `delimiter == null`: ném `NullPointerException`.
- Cả mảng `elements` hoặc cả `Iterable` là `null`: ném `NullPointerException`.
- **Một phần tử bên trong** mảng/`Iterable` là `null`: giá trị đó được thể hiện bằng chuỗi ký tự `"null"` trong kết quả.

Ví dụ phân biệt hai tình huống khác nhau:

```java
String[] values = {"A", null, "C"};
System.out.println(String.join("-", values)); // A-null-C

String[] missingArray = null;
// String.join("-", missingArray); // NullPointerException
```

Đừng nhầm ngoại lệ xảy ra **trước lúc join** với hành vi của `join`: `List.of("A", null)` tự ném `NullPointerException` vì `List.of` không cho phép phần tử `null`. Nếu muốn kiểm thử một danh sách chứa `null`, có thể dùng `Arrays.asList("A", null)`.

## 5. Khi làm việc với mảng

`String[]` là lựa chọn trực tiếp nhất:

```java
String[] paths = {"api", "v1", "users"};
String route = String.join("/", paths); // "api/v1/users"
```

`String.join` không tự chuẩn hóa đường dẫn hay thêm dấu `/` ở đầu. Nếu cần một đường dẫn hệ thống thực sự, hãy cân nhắc API đường dẫn như `Path` thay vì xây đường dẫn hệ điều hành bằng phép ghép chuỗi.

Mảng kiểu nguyên thủy, chẳng hạn `int[]`, **không** tương thích với `CharSequence...`. Ví dụ `String.join(",", new int[]{1, 2})` không biên dịch. Muốn ghép số, cần chuyển số thành chuỗi:

```java
import java.util.stream.Collectors;
import java.util.stream.IntStream;

String ids = IntStream.of(7, 12, 30)
        .mapToObj(String::valueOf)
        .collect(Collectors.joining("-"));

System.out.println(ids); // 7-12-30
```

Ví dụ này là **đoạn mã đặt trong một phương thức hoặc chương trình có sẵn**; muốn chạy độc lập, hãy đặt các câu lệnh vào `main` và thêm những import được hiển thị.

## 6. Khi làm việc với Iterable

`Iterable<? extends CharSequence>` cho phép dùng `List<String>`, `Set<String>` và các collection/đối tượng có khả năng duyệt khác. Không cần gọi `toArray()` chỉ để ghép phần tử.

```java
import java.util.List;

List<String> roles = List.of("reader", "editor", "admin");
String description = String.join(" | ", roles);
// "reader | editor | admin"
```

Với `List`, thứ tự danh sách là thứ tự ghép. Với `Set`, thứ tự phụ thuộc vào loại set:
- `LinkedHashSet` giữ thứ tự chèn.
- `TreeSet` duyệt theo thứ tự sắp xếp của nó.
- `HashSet` không bảo đảm thứ tự duyệt; không dùng khi đầu ra bắt buộc ổn định.

Một đối tượng chỉ khai báo kiểu `Iterable<String>` vẫn truyền thẳng được cho `String.join`, vì overload thứ hai yêu cầu `Iterable<? extends CharSequence>`. Các phần tử được duyệt để tạo kết quả; `String.join` không đòi danh sách phải hỗ trợ truy cập theo chỉ số.

### Iterable chứa CharSequence khác String

```java
import java.util.List;

List<StringBuilder> builders = List.of(
        new StringBuilder("first"),
        new StringBuilder("second")
);

String joined = String.join(" + ", builders);
// "first + second"
```

Ở thời điểm ghép, nội dung mỗi `StringBuilder` được biểu diễn thành chuỗi. Chuỗi `joined` đã tạo ra sẽ không tự thay đổi nếu sau đó bạn sửa những `StringBuilder` nguồn.

## 7. Làm sạch dữ liệu trước khi join

Trong dữ liệu thực tế, bạn có thể cần bỏ `null`, trim khoảng trắng và loại mục rỗng. `String.join` không có tham số bật các hành vi này; hãy xử lý nguồn trước:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> raw = Arrays.asList("  Java  ", "", null, "  Core ");
List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(value -> !value.isEmpty())
        .toList();

System.out.println(String.join(", ", cleaned)); // Java, Core
```

Đây là đoạn mã minh họa dành cho `main` hoặc một phương thức thích hợp; `Stream.toList()` có từ Java 16, nên chạy được với Java 17+. Không nên mặc định loại phần tử rỗng hoặc `null` trong mọi bài toán: đôi khi vị trí trống trong dữ liệu có ý nghĩa và cần được giữ lại.

Nếu cần kiểm soát phân cách theo từng điều kiện, escape định dạng hoặc chuẩn hóa văn bản theo quy tắc nghiệp vụ, hãy xử lý rõ ràng trước khi gọi `join`.

## 8. Chọn String.join, StringJoiner hay Collectors.joining

| Công cụ | Tình huống phù hợp | Đặc điểm |
| --- | --- | --- |
| `String.join` | Đã có mảng, `Iterable` hoặc vài chuỗi rời | Ngắn gọn; chỉ chọn delimiter và các phần tử |
| `StringJoiner` | Thêm dần các phần tử; muốn prefix/suffix | Có `add`, delimiter, prefix, suffix |
| `Collectors.joining` | Đang xử lý `Stream<String>` | Kết hợp tự nhiên với `filter`, `map`; có overload prefix/suffix |

Ví dụ khi cần dấu ngoặc bao quanh:

```java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("A").add("B");
System.out.println(joiner); // [A, B]

String collected = List.of("A", "B").stream()
        .collect(Collectors.joining(", ", "[", "]"));
System.out.println(collected); // [A, B]
```

`String.join` chỉ chèn dấu phân cách; `String.join(", ", items)` tự nó không sinh tiền tố `[` hoặc hậu tố `]`. Cũng không cần chuyển `List` thành `Stream` chỉ để gọi `Collectors.joining` khi `String.join` đã giải quyết đủ yêu cầu.

## 9. Sai lầm thường gặp và cách tránh

1. **Dùng nhầm kiểu phần tử.** `String.join(",", List.of(1, 2))` không tương thích vì `Integer` không triển khai `CharSequence`. Chuyển phần tử sang `String` trước.
2. **Cho rằng `null` bị bỏ qua.** Phần tử `null` trở thành chữ `"null"`; nếu không muốn vậy, lọc trước.
3. **Cho rằng `String.join` tự bỏ khoảng trắng.** `" A "` vẫn chứa hai khoảng trắng; trim riêng khi cần.
4. **Cho rằng mọi `Set` đều có thứ tự ổn định.** Chọn cấu trúc bảo toàn thứ tự hoặc sắp xếp chủ động nếu kết quả cần tái lập.
5. **Nhầm dấu phân cách thành biểu thức chính quy.** `String.join` chèn delimiter nguyên văn, không diễn giải `.`, `|` hoặc `*` như regex.
6. **Dùng join để xuất CSV hoàn chỉnh.** Giá trị có dấu phẩy, dấu nháy kép hoặc xuống dòng cần quy tắc CSV; `String.join(",", fields)` không tự quote/escape.
7. **Nối chuỗi lặp bằng `+=` để thay join.** Với một collection có sẵn, `String.join` thể hiện mục đích rõ ràng và tránh tự quản lý dấu phân cách đầu/cuối.
8. **Truyền `null` không rõ kiểu cho overload.** Các overload đều nhận kiểu tham chiếu; hãy khai báo dữ liệu có kiểu rõ ràng, kiểm tra `null` trước khi gọi.

## 10. Bài tự luyện

**Bài 1.** Có `String[] tags = {"java", "core", "api"};`. Tạo chuỗi `"java | core | api"` mà không dùng vòng lặp.

```java
String[] tags = {"java", "core", "api"};
String result = String.join(" | ", tags);
```

**Bài 2.** Có `List<String> letters = List.of("x", "y", "z");`. Dự đoán kết quả của `String.join("", letters)` và `String.join("/", List.<String>of())`.

Đáp án: `"xyz"` và `""`. Dấu phân cách rỗng không tạo ký tự giữa các phần tử; iterable rỗng cho chuỗi rỗng.

**Bài 3.** Với `Arrays.asList("A", "", null, "B")` và delimiter `"-"`, dự đoán kết quả nếu không lọc dữ liệu.

Đáp án: `"A--null-B"`. Phần tử rỗng vẫn chiếm một vị trí, còn `null` được chuyển thành chữ `"null"`.

**Bài 4.** Muốn xuất nhiều trường có thể chứa dấu phẩy và xuống dòng theo định dạng CSV chuẩn, có nên chỉ dùng `String.join(",", fields)`?

Đáp án: Không đủ. Cần cơ chế quote/escape CSV phù hợp (hoặc thư viện CSV) trước khi phát hành dữ liệu; `String.join` chỉ thực hiện ghép ký tự.

## 11. Ghi nhớ

- **Mảng `String[]` hoặc `CharSequence[]`:** dùng overload varargs, ví dụ `String.join(", ", array)`.
- **`List<String>`, `Set<String>` hay `Iterable<? extends CharSequence>`:** truyền trực tiếp, ví dụ `String.join(", ", list)`.
- **Không phần tử:** nhận `""`. **Phần tử `null`:** nhận chữ `"null"`. **Delimiter hoặc nguồn `null`:** `NullPointerException`.
- **Thứ tự:** theo mảng hoặc thứ tự duyệt của `Iterable`; không tự sắp xếp.
- **Chuẩn hóa, lọc, thêm prefix/suffix hay xuất định dạng có escape:** cần bước xử lý khác hoặc công cụ phù hợp.

Tài liệu API tham khảo: [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — StringJoiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html), [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
