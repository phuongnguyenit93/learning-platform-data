# Dấu phân cách và phần tử rỗng khi ghép nhiều chuỗi trong Java

## 1. Vấn đề cần giải quyết

Khi ghép nhiều phần tử thành một chuỗi, thông thường ta đặt **dấu phân cách** (*delimiter/separator*) giữa hai phần tử liên tiếp. Nhưng điều gì xảy ra nếu một phần tử là chuỗi rỗng `""`, nằm ở đầu, giữa hoặc cuối danh sách? Nếu toàn bộ danh sách không có phần tử thì kết quả ra sao? Và có nên tự động bỏ các phần tử rỗng trước khi ghép?

Các câu hỏi này quan trọng trong việc tạo dòng dữ liệu, nối tham số, hiển thị danh sách, xây chuỗi log hoặc trao đổi thông tin với hệ thống khác. Một dấu phân cách thừa hoặc thiếu có thể làm thay đổi **số lượng và vị trí của trường dữ liệu**.

Xét ba chuỗi đầu vào:

```java
String a = "Java";
String b = "";
String c = "String";

String result = String.join("|", a, b, c);
System.out.println(result); // Java||String
```

Hai dấu `|` liền nhau **không phải lỗi**: chúng thể hiện rằng có **một phần tử rỗng ở giữa**. Nếu bỏ `b` trước khi ghép, kết quả `Java|String` mang cấu trúc khác.

Nguyên tắc nền tảng: **phần tử rỗng không đồng nghĩa với phần tử không tồn tại**.

## 2. `String.join` đặt dấu phân cách như thế nào?

Từ Java 8, `String.join` có hai overload phổ biến:

```java
String.join(CharSequence delimiter, CharSequence... elements);
String.join(CharSequence delimiter,
            Iterable<? extends CharSequence> elements);
```

Đây là **chữ ký API để tham khảo**, không phải khai báo chương trình độc lập. `delimiter` là chuỗi phân cách, còn `elements` là dãy phần tử theo thứ tự do bạn cung cấp hoặc thứ tự mà `Iterable` duyệt được.

Với `n` phần tử, nếu `n >= 1`, quy tắc ghép là:

```text
element[0] + delimiter + element[1] + ... + delimiter + element[n-1]
```

Nói cách khác, có **n − 1 lần chèn delimiter giữa các phần tử**, không tự chèn thêm ở đầu hay cuối. Khi `n = 0`, kết quả là chuỗi rỗng `""`.

```java
System.out.println(String.join(", ", "A", "B", "C")); // A, B, C
System.out.println(String.join(" / ", "A"));         // A
System.out.println(String.join(", ", new String[0]).isEmpty()); // true
```

**Lưu ý:** Dấu phân cách có thể là một hoặc nhiều ký tự, thậm chí chuỗi rỗng `""`. Dấu phân cách được sao chép dưới dạng văn bản **literal**; `String.join` không dùng biểu thức chính quy (*regex*) để hiểu delimiter.

### Bảng hành vi của phần tử rỗng

Trong bảng sau, dấu `<...>` chỉ để **nhìn thấy ranh giới kết quả**, không phải ký tự do `String.join` tự thêm.

| Các phần tử đầu vào | Delimiter | Kết quả nhìn trong dấu `<...>` | Ý nghĩa |
| --- | --- | --- | --- |
| Không có phần tử: `[]` | `","` | `<>` | Không có gì để ghép |
| Một phần tử: `["A"]` | `","` | `<A>` | Không cần dấu phân cách |
| Một phần tử rỗng: `[""]` | `","` | `<>` | Có phần tử, nhưng nội dung rỗng |
| Hai phần tử rỗng: `["", ""]` | `","` | `<,>` | Delimiter nằm giữa hai chuỗi rỗng |
| `["A", "", "B"]` | `","` | `<A,,B>` | Giữ phần tử rỗng ở giữa |
| `["", "A"]` | `","` | `<,A>` | Delimiter ở đầu **do phần tử đầu rỗng** |
| `["A", ""]` | `","` | `<A,>` | Delimiter ở cuối **do phần tử cuối rỗng** |
| `["", "A", ""]` | `","` | `<,A,>` | Giữ cả hai phần tử rỗng hai đầu |
| `["A", "", "B"]` | `""` | `<AB>` | Không có ký tự nào thể hiện ranh giới |

**Phân biệt:** `String.join(",", new String[0])` và `String.join(",", "")` đều trả về `""`. Chỉ nhìn chuỗi kết quả **không thể phân biệt danh sách rỗng với danh sách có đúng một phần tử rỗng**. Đây là hạn chế thông tin của cách mã hóa dạng nối đơn giản, không phải lỗi API.

## 3. Ba khái niệm khác nhau: không có phần tử, phần tử rỗng và `null`

Trong Java, ba trường hợp sau không giống nhau:

- **Không có phần tử:** danh sách/array dài 0; ví dụ `List.of()`.
- **Có một phần tử rỗng:** danh sách dài 1, chứa `""`. Đây là một giá trị `String` hợp lệ với `length() == 0`.
- **Có một phần tử `null`:** danh sách dài 1, chứa tham chiếu `null`; nó không phải đối tượng `String` và không phải chuỗi `"null"`.

Theo hợp đồng của `String.join`, nếu **một phần tử** là `null`, API sẽ thêm văn bản `"null"` vào kết quả:

```java
String joined = String.join("|", "A", null, "B");
System.out.println(joined); // A|null|B
```

Điều này tạo nên điểm cần cân nhắc: phần tử tham chiếu `null` và phần tử **literal `"null"`** sẽ cho cùng cách biểu diễn sau khi nối. Nếu dữ liệu cần phân biệt giá trị vắng mặt và chuỗi bốn ký tự `"null"`, bạn phải có **quy tắc biểu diễn riêng** (ví dụ định dạng dữ liệu có hỗ trợ giá trị null), không dựa vào `String.join`.

Bên cạnh đó:

```java
String.join(",", "A", null);                // "A,null"
String.join(",", "A", "");                  // "A,"
String.join(",", new String[0]);           // ""
String.join(",", new String[]{null});      // "null"
```

Các dòng trên là **biểu thức minh họa**. Tên `"null"` được viết ra khi **element null** xuất hiện; nhưng truyền **delimiter null** hoặc chính mảng/`Iterable` `elements == null` sẽ ném `NullPointerException`. Đừng nhầm “phần tử null được chuyển thành văn bản” với “mọi đối số null đều được chấp nhận”.

## 4. Dấu phân cách ở vị trí đầu/cuối có thể hoàn toàn đúng

Một tình huống phổ biến là muốn nối ba trường theo thứ tự, trong đó trường đầu hoặc cuối được phép rỗng:

```java
String first = "";
String middle = "java";
String last = "";

String line = String.join("|", first, middle, last);
System.out.println("<" + line + ">"); // <|java|>
```

Đầu dòng có `|` vì **trước trường `middle` còn một trường rỗng**. Cuối dòng có `|` vì **sau `middle` còn một trường rỗng**. Đây không phải “delimiter được chèn thừa”.

Nếu yêu cầu dữ liệu là giữ nguyên cả ba vị trí, việc tự ý xóa dấu đầu/cuối bằng `strip()` hoặc logic cắt ký tự có thể phá vỡ thông tin. `strip()` cũng không được thiết kế để loại bỏ delimiter; nó loại bỏ một số khoảng trắng đầu/cuối theo `Character.isWhitespace`.

Trái lại, trong trường hợp **hiển thị một danh sách tên** mà phần tử rỗng vốn là dữ liệu không có ý nghĩa, bạn có thể chọn loại chúng **trước khi gọi join**. Đây phải là một quyết định theo hợp đồng bài toán, không phải hành vi mặc định mà ta gán cho API.

## 5. Khi nào giữ phần tử rỗng, khi nào lọc bỏ?

Hãy định nghĩa rõ ràng mục tiêu dữ liệu:

| Mục tiêu | Chính sách đối với `""` | Ví dụ |
| --- | --- | --- |
| Dữ liệu dạng cột, mỗi vị trí ứng với một trường | **Giữ** phần tử rỗng | `["A", "", "B"]` → `A||B` |
| Tạo nhãn hiển thị từ các phần **tùy chọn** | Có thể bỏ `""` nếu phần bỏ trống không mang ý nghĩa | `["Lan", "", "Nguyen"]` → `Lan Nguyen` |
| Biểu diễn số ô trống trong bản ghi cố định | **Giữ** cả rỗng ở đầu và cuối | `["", "A", ""]` → `|A|` |
| Tạo đường dẫn, URL, câu lệnh giao thức | Theo **đặc tả tương ứng**, không tự lọc | Dấu phân cách có thể mang ngữ nghĩa |
| Log hoặc thông điệp để con người đọc | Quyết định rõ liệu muốn giữ trường hay chỉ giữ giá trị có nội dung | Không được gây nhầm mất trường |

Ví dụ lọc **chỉ chuỗi rỗng**:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> parts = List.of("Lan", "", "Nguyen");

String keepAll = String.join(" ", parts);
String skipEmpty = parts.stream()
        .filter(s -> !s.isEmpty())
        .collect(Collectors.joining(" "));

System.out.println("<" + keepAll + ">");  // <Lan  Nguyen>
System.out.println("<" + skipEmpty + ">"); // <Lan Nguyen>
```

Đây là **đoạn minh họa**; khi dùng `List.of`, phần tử không được là `null`. Lọc bằng `!s.isEmpty()` chỉ loại `""`, **không** loại chuỗi `" "` hoặc `"\t"`. Nếu yêu cầu là bỏ những phần tử toàn khoảng trắng, có thể xem xét `!s.isBlank()` (Java 11+), nhưng `isBlank` và `isEmpty` có ngữ nghĩa khác nhau và không nên tráo đổi tùy tiện.

### Với `null`: xác định chính sách rõ ràng

Nếu `null` nghĩa là “không có phần cần hiển thị”, có thể chủ động bỏ chúng:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> items = Arrays.asList("A", null, "", "B");
String joined = items.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|"));

System.out.println(joined); // A||B
```

Ở đây lọc `null` nhưng **giữ** phần tử rỗng, nên vẫn có hai delimiter liên tiếp. Nếu cũng muốn bỏ rỗng, phải thêm chính sách lọc thích hợp **sau khi** đã loại `null` để tránh `NullPointerException`.

Việc bỏ `null` thích hợp với một số danh sách hiển thị, nhưng có thể **không đúng** với bản ghi có số trường cố định; đối với trường bắt buộc, nên **báo lỗi hoặc dùng format có null riêng**.

## 6. `StringJoiner`: kiểm soát delimiter, prefix, suffix và giá trị khi chưa có phần tử

`java.util.StringJoiner` là công cụ mutable phục vụ **tích lũy** các phần tử, chèn delimiter giữa chúng và (nếu cần) thêm tiền tố/hậu tố.

```java
import java.util.StringJoiner;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("A").add("").add("B");
System.out.println(joiner); // [A, , B]
```

`StringJoiner.add("")` vẫn được tính là **đã thêm một phần tử**. Nó không bỏ qua chuỗi rỗng. Tương tự, `add(null)` thêm chữ `"null"`.

### Chưa thêm gì khác với đã thêm `""`

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");

System.out.println(joiner); // []
joiner.setEmptyValue("[none]");
System.out.println(joiner); // [none]

joiner.add("");
System.out.println(joiner); // []
joiner.add("B");
System.out.println(joiner); // [, B]
```

Trước `add(...)`, `StringJoiner` chưa có phần tử và dùng `prefix + suffix`, hoặc **empty value** do `setEmptyValue(...)` đặt ra. Sau `add("")`, nó **không còn được xem là empty** dù nội dung phần tử là `""`: nó trở lại biểu diễn thông thường là `prefix + "" + suffix`, ở đây là `[]`. Khi thêm `B`, delimiter xuất hiện giữa phần tử rỗng và `B`.

**Lưu ý:** Nếu chưa có phần tử, `new StringJoiner(",")` không prefix/suffix trả về `""`. Nếu muốn hiển thị khác giữa danh sách không có phần tử và danh sách có phần tử rỗng, dùng cơ chế `setEmptyValue` hoặc lưu riêng **số lượng phần tử**, nhưng không thể mong chuỗi kết quả của `String.join` tự giữ metadata đó.

`StringJoiner` hữu ích khi số phần tử chưa biết trước hoặc thêm dần trong vòng lặp. Với danh sách có sẵn, `String.join` thường đơn giản hơn.

## 7. `Collectors.joining`: ghép từ Stream mà vẫn giữ phần tử rỗng

Đối với `Stream<String>`, Java cung cấp các collector:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String result = Stream.of("A", "", "B")
        .collect(Collectors.joining("|"));

System.out.println(result); // A||B
```

Các dạng thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `Collectors.joining()` | Ghép trực tiếp, không có delimiter |
| `Collectors.joining(delimiter)` | Chèn delimiter giữa các phần tử |
| `Collectors.joining(delimiter, prefix, suffix)` | Chèn delimiter và thêm prefix/suffix cho kết quả |

Một stream **không có phần tử** với `Collectors.joining("|")` cho `""`; stream có **một phần tử `""`** cũng cho `""`. Với collector có prefix/suffix, biểu diễn rỗng theo `StringJoiner`: ví dụ `Collectors.joining(", ", "[", "]")` trên stream rỗng trả về `"[]"`.

Nếu cần bỏ phần tử rỗng, **lọc trước khi collect**:

```java
String display = Stream.of("A", "", "B")
        .filter(s -> !s.isEmpty())
        .collect(Collectors.joining("|"));

System.out.println(display); // A|B
```

Trước khi dùng pipeline với các phần tử có thể `null`, hãy xác định chính sách và bổ sung `filter(Objects::nonNull)` khi phù hợp. `Collectors.joining` không tự mang ý nghĩa “lọc giá trị thiếu”; thông thường, `null` được biểu diễn như chữ `"null"` khi đi qua `StringJoiner`.

## 8. Chương trình Java 17 hoàn chỉnh

Lưu nội dung sau vào tệp `JoinEmptyDemo.java`. Các dấu `<...>` được in ra **chỉ để nhìn rõ** khi chuỗi bắt đầu/kết thúc bằng delimiter hoặc hoàn toàn rỗng.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.StringJoiner;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoinEmptyDemo {
    public static void main(String[] args) {
        String[] fields = {"", "java", "", "core", ""};
        String joined = String.join("|", fields);
        String[] restored = joined.split(Pattern.quote("|"), -1);
        String[] defaultSplit = joined.split(Pattern.quote("|"));

        System.out.println("joined=<" + joined + ">");
        System.out.println("restored count=" + restored.length);
        System.out.println("restored same=" + Arrays.equals(fields, restored));
        System.out.println("first empty=" + restored[0].isEmpty());
        System.out.println("middle empty=" + restored[2].isEmpty());
        System.out.println("last empty=" + restored[4].isEmpty());
        System.out.println("default split count=" + defaultSplit.length);

        System.out.println("empty collection=<"
                + String.join(",", Collections.<String>emptyList()) + ">");
        System.out.println("one empty=<" + String.join(",", "") + ">");
        System.out.println("two empty=<" + String.join(",", "", "") + ">");
        System.out.println("empty separator=<"
                + String.join("", "A", "", "B") + ">");
        System.out.println("null item=<"
                + String.join("|", "A", null, "B") + ">");

        StringJoiner sj = new StringJoiner(", ", "[", "]");
        System.out.println("joiner no elements=" + sj);
        sj.setEmptyValue("[none]");
        System.out.println("joiner custom empty=" + sj);
        sj.add("");
        System.out.println("joiner one empty=" + sj);
        sj.add("B");
        System.out.println("joiner two elements=" + sj);

        String collected = Stream.of("a", "", "b")
                .collect(Collectors.joining("|"));
        System.out.println("stream=<" + collected + ">");
    }
}
```

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac JoinEmptyDemo.java
java JoinEmptyDemo
```

Kết quả đã kiểm tra với Java 21 (đồng thời tương thích Java 17):

```text
joined=<|java||core|>
restored count=5
restored same=true
first empty=true
middle empty=true
last empty=true
default split count=4
empty collection=<>
one empty=<>
two empty=<,>
empty separator=<AB>
null item=<A|null|B>
joiner no elements=[]
joiner custom empty=[none]
joiner one empty=[]
joiner two elements=[, B]
stream=<a||b>
```

**Cách đọc kết quả:**

- `joined=<|java||core|>` chứng minh phần tử rỗng ở đầu, giữa và cuối được giữ.
- `restored count=5` và `restored same=true` chứng minh ở **trường hợp dữ liệu này** dùng `split(..., -1)` khôi phục đủ năm phần tử.
- `default split count=4` cho thấy `split(regex)` không giữ phần tử rỗng **cuối** theo mặc định.
- `empty collection=<>` và `one empty=<>` cho ra cùng chuỗi; số lượng phần tử ban đầu đã không còn nhận biết được.
- `joiner custom empty=[none]` nhưng sau `add("")` trở thành `[]` vì joiner đã có một phần tử dù rỗng.

## 9. Ghép rồi tách lại: vì sao phần tử rỗng dễ bị mất?

Nếu bạn dùng delimiter để **mã hóa nhiều trường**, việc giải mã bằng `String.split` phải được hiểu rõ.

```java
String text = "A,,B,";
String[] withoutLimit = text.split(",");
String[] keepTrailing = text.split(",", -1);

System.out.println(withoutLimit.length); // 3
System.out.println(keepTrailing.length); // 4
```

`split(regex)` tương đương `split(regex, 0)`: Java loại bỏ **các phần tử rỗng ở cuối** của mảng kết quả. `split(regex, -1)` giữ các phần tử rỗng ở cuối, vì `limit` âm cho phép áp dụng mẫu không giới hạn và không loại bỏ phần tử rỗng kết thúc.

Ở giữa chuỗi, phần tử rỗng vẫn có thể giữ lại:

```java
String[] middle = "A,,B".split(",", -1);
// Nội dung logic: ["A", "", "B"]
```

### Delimiter của `join` là văn bản; delimiter của `split` là regex

Đây là khác biệt đặc biệt quan trọng:

```java
String joined = String.join("|", "A", "", "B"); // A||B
String[] parts = joined.split(
        java.util.regex.Pattern.quote("|"), -1);
```

`String.join("|", ...)` coi `|` là delimiter nguyên văn. Nhưng `split("|")` không hiểu `|` theo nghĩa đó: trong regex, `|` là toán tử lựa chọn (*alternation*). Dùng `Pattern.quote("|")` hoặc biểu thức regex escape phù hợp để tách **đúng delimiter literal**. Nếu delimiter là dữ liệu cấu hình động như `".", "|", "||"`, `Pattern.quote(delimiter)` thường giúp tránh lỗi do ký tự đặc biệt regex.

### `split(..., -1)` vẫn không bảo đảm hoàn nguyên mọi đầu vào

Ngay cả khi đã giữ phần tử rỗng cuối, `join` + `split` **không phải phép mã hóa hoàn nguyên tổng quát**:

1. **Danh sách rỗng và danh sách có một chuỗi rỗng cùng ra `""`.** Tách `""` theo delimiter không rỗng với `limit=-1` cho một chuỗi rỗng, không thể biết ban đầu có 0 hay 1 phần tử.
2. **Phần tử tự chứa delimiter sẽ gây nhập nhằng.** Ví dụ `["A,B", "C"]` và `["A", "B", "C"]` đều ghép với dấu `,` thành `"A,B,C"`.
3. **`null` và literal `"null"` mất sự khác biệt** vì `String.join` chuyển cả hai thành chữ `"null"`.
4. **Delimiter rỗng `""` không giữ ranh giới.** `["AB"]` và `["A", "B"]` đều có thể trở thành `"AB"` nếu nối bằng delimiter rỗng.

Do đó `String.join` rất tốt cho **biểu diễn đơn giản**, nhưng không phải serializer mang đủ thông tin trường, escaping, null và ranh giới.

## 10. Không tự dùng `String.join` như CSV/TSV serializer tổng quát

CSV có những quy tắc riêng liên quan đến delimiter, dấu ngoặc kép, escape, dòng mới và chính sách đối với các trường rỗng. Nếu trường dữ liệu chứa dấu phẩy, ngoặc kép hoặc ký tự xuống dòng, chỉ `String.join(",", fields)` **không đủ** để xuất CSV đúng trong mọi trường hợp.

Ví dụ:

```java
String[] fields = {"Nguyen, Lan", "Java"};
System.out.println(String.join(",", fields));
// Nguyen, Lan,Java
```

Nếu chỉ `split(",")` sau đó, kết quả sẽ có **ba đoạn** thay vì hai trường ban đầu. Với CSV đúng chuẩn, trường có dấu phẩy thường phải được quote, và dấu quote bên trong trường cũng phải được escape theo định dạng tương ứng. Nên dùng thư viện/parser CSV thích hợp khi dữ liệu cần lưu trữ hoặc truyền hệ thống. Các định dạng như JSON cũng có quy tắc rõ về mảng rỗng, `null`, chuỗi rỗng và escaping.

**Lựa chọn thực tế:**

- **Nhóm nhãn hiển thị:** `String.join`, có thể lọc phần tử rỗng theo nhu cầu hiển thị.
- **Ghép nội dung log đơn giản:** `StringJoiner` hoặc `Collectors.joining`; bảo đảm không mất trường quan trọng khi debug.
- **Dòng bản ghi cố định và delimiter không xuất hiện trong trường:** giữ đủ số trường, dùng delimiter literal, `split(Pattern.quote(delimiter), -1)` khi tách; vẫn phải xử lý trường hợp danh sách 0/1 rỗng.
- **Dữ liệu cấu trúc tổng quát:** định dạng/serializer có escaping, null và độ dài trường rõ ràng.

## 11. Lỗi thường gặp

1. **Tưởng `String.join` tự bỏ `""`.** Không: mỗi phần tử rỗng vẫn chiếm một vị trí và làm xuất hiện delimiter theo số lượng phần tử.
2. **Tưởng delimiter ở đầu/cuối là do join thêm sai.** Nếu phần tử đầu/cuối rỗng, delimiter có thể xuất hiện ở biên kết quả một cách hoàn toàn đúng.
3. **Không phân biệt danh sách rỗng và một phần tử rỗng.** Hai trường hợp đều có thể mã hóa thành `""`, nhưng một bên có 0 phần tử, bên kia có 1 phần tử.
4. **Nhầm phần tử `null` với delimiter `null`.** Phần tử null được chuyển thành chữ `"null"`; delimiter null hoặc tập phần tử null ném `NullPointerException`.
5. **Gọi `split(",")` rồi mất các trường rỗng cuối.** Nếu cần giữ chúng, dùng `split(",", -1)`.
6. **Dùng `split("|")` để tách dấu `|` literal.** `split` nhận regex; hãy dùng `Pattern.quote("|")`.
7. **Lọc rỗng trong dữ liệu có vị trí cột cố định.** Việc lọc khiến các giá trị sau bị dịch cột; không được đánh đổi cấu trúc chỉ để chuỗi nhìn gọn hơn.
8. **Đánh đồng `isEmpty()` với `isBlank()`.** `""` rỗng; `" "` không rỗng nhưng có thể blank. Chính sách loại bỏ của chúng khác nhau.
9. **Dùng `join` rồi `split` như cơ chế mã hóa không mất mát.** Dữ liệu có delimiter, null hoặc danh sách 0/1 rỗng làm đảo chiều không còn đáng tin.
10. **Tự tạo CSV bằng cách nối dấu phẩy mà không escape.** CSV/TSV hay giao thức dữ liệu có thể yêu cầu quote, escape và quy tắc về dòng mới; hãy dùng công cụ đúng định dạng.

## 12. Bài tập tự kiểm tra

Hãy tính hai chuỗi sau mà **không chạy code**:

```java
String first = String.join("-", "", "A", "", "B", "");
String second = String.join("-", "A", "B");
```

Đáp án:

```text
first  = -A--B-
second = A-B
```

Có năm phần tử trong `first` nên có **bốn dấu `-` phân cách**, kể cả khi các phần tử ngoài cùng rỗng. `second` có hai phần tử nên chỉ có một dấu phân cách.

Tiếp theo, với `String value = "A||B|"`, hỏi:

- `value.split(java.util.regex.Pattern.quote("|"))` có **3** phần tử (`"A"`, `""`, `"B"`) vì phần tử rỗng cuối bị bỏ.
- `value.split(java.util.regex.Pattern.quote("|"), -1)` có **4** phần tử, gồm phần tử rỗng cuối.
- Không thể biết chỉ từ một chuỗi `"A||B|"` liệu dữ liệu ban đầu đã được tạo bằng một cách mã hóa với escaping hay không; muốn đảm bảo tái tạo toàn bộ đầu vào cần một hợp đồng biểu diễn phù hợp.

**Ghi nhớ:** `String.join` chèn dấu phân cách **giữa các phần tử**, không mặc định bỏ chuỗi rỗng. Hãy quyết định rõ chính sách giữ/lọc `""` và `null` trước khi ghép; nếu muốn tách lại, nhớ regex của `split` và `limit=-1`, nhưng đừng xem nối chuỗi đơn giản là một định dạng dữ liệu hoàn nguyên.

### Tài liệu API Java 17

- [`String.join` và `String.split` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`StringJoiner` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [`Pattern.quote` và giới hạn của `split` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
