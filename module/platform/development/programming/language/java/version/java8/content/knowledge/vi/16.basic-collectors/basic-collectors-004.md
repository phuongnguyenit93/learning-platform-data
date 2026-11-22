# Collectors.joining: delimiter, prefix và suffix trong Java Stream

`Collectors.joining(...)` là một **collector kết thúc Stream**, gom các phần tử dạng chuỗi ký tự thành **một `String` duy nhất**. Tính năng này có từ Java 8 và vẫn là API thông dụng trong Java hiện nay. Bài học tập trung vào ba thành phần của chuỗi đầu ra:

- **`delimiter`**: dấu phân cách **giữa** hai phần tử liền kề.
- **`prefix`**: chuỗi đặt **một lần ở đầu** kết quả.
- **`suffix`**: chuỗi đặt **một lần ở cuối** kết quả.

Ví dụ, với ba phần tử `"An"`, `"Binh"` và `"Chi"`:

```text
Phần tử:        "An"    "Binh"    "Chi"
delimiter:      " | "
prefix/suffix:  "["  và  "]"
Kết quả:        [An | Binh | Chi]
```

Khi muốn hiển thị nhãn, đường dẫn, danh sách lựa chọn hoặc dữ liệu trong log, `joining` giúp loại bỏ nhu cầu tự xử lý “thêm dấu phân cách trước hay sau phần tử cuối”.

## 1. Ba overload của `Collectors.joining`

Các overload thuộc `java.util.stream.Collectors`, trả về một `Collector<CharSequence, ?, String>`:

| Cú pháp | Tác dụng | Ví dụ trên `["An", "Binh", "Chi"]` |
| --- | --- | --- |
| `Collectors.joining()` | Nối trực tiếp, không có dấu phân cách hay bao ngoài | `AnBinhChi` |
| `Collectors.joining(delimiter)` | Chèn dấu phân cách **chỉ giữa** các phần tử | Với `" | "` → `An | Binh | Chi` |
| `Collectors.joining(delimiter, prefix, suffix)` | Có dấu phân cách, thêm chuỗi đầu và cuối | Với `" | ", "[", "]"` → `[An | Binh | Chi]` |

Chữ ký đầy đủ của overload ba tham số:

```java
public static Collector<CharSequence, ?, String> joining(
        CharSequence delimiter,
        CharSequence prefix,
        CharSequence suffix)
```

`CharSequence` là kiểu giao diện mà `String` triển khai. `joining` không tự gọi `toString()` trên mọi loại object; nếu nguồn là số, enum hoặc đối tượng khác, cần chuyển từng phần tử thành chuỗi trước (`map`) hoặc dùng `Collectors.mapping` làm downstream collector.

Cách đọc biểu thức:

```java
String text = names.stream()
        .collect(Collectors.joining(", ", "[", "]"));
```

1. `names.stream()` cung cấp các tên theo thứ tự duyệt của nguồn.
2. `joining(", ", "[", "]")` tạo collector dùng `", "` làm delimiter, `"["` làm prefix, `"]"` làm suffix.
3. `collect(...)` là terminal operation thực thi pipeline và trả `String`.
4. Dấu phân cách không được thêm trước phần tử đầu hay sau phần tử cuối. Prefix/suffix không phải dấu phân cách.

### Hình dung công thức

Với các phần tử `x1, x2, ..., xn` và `n >= 1`:

```text
result = prefix + x1 + delimiter + x2 + ... + delimiter + xn + suffix
```

Với **0 phần tử**, kết quả của overload ba tham số là:

```text
result = prefix + suffix
```

Nếu dùng `joining()` hoặc `joining(delimiter)` trên nguồn rỗng thì kết quả là chuỗi rỗng `""`.

## 2. Ví dụ hoàn chỉnh: ba overload, một phần tử và nguồn rỗng

Tạo tệp `JoiningBasicsDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningBasicsDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi");

        System.out.println("plain = "
                + names.stream().collect(Collectors.joining()));
        System.out.println("delimiter = "
                + names.stream().collect(Collectors.joining(" | ")));
        System.out.println("wrapped = "
                + names.stream().collect(Collectors.joining(" | ", "[", "]")));

        System.out.println("single = "
                + Stream.of("An").collect(Collectors.joining(" | ", "[", "]")));
        System.out.println("empty = "
                + Stream.<String>empty()
                        .collect(Collectors.joining(" | ", "[", "]")));
        System.out.println("empty no wrap = <"
                + Stream.<String>empty()
                        .collect(Collectors.joining(" | ")) + ">");
    }
}
```

Biên dịch và chạy bằng JDK 17+ (mã dùng các API đã có từ Java 8):

```bash
javac -encoding UTF-8 JoiningBasicsDemo.java
java JoiningBasicsDemo
```

Đầu ra chính xác:

```text
plain = AnBinhChi
delimiter = An | Binh | Chi
wrapped = [An | Binh | Chi]
single = [An]
empty = []
empty no wrap = <>
```

**Điểm cần thấy:** nguồn chỉ có một phần tử vẫn có prefix/suffix nhưng không có delimiter; nguồn rỗng vẫn có `"["` và `"]"` vì chúng thuộc về **toàn bộ kết quả**, không thuộc về từng phần tử. Hai ký tự `<>` ở dòng cuối do mã `System.out.println` dùng để hiển thị rõ chuỗi rỗng, không phải do collector tạo ra.

## 3. Cách xử lý trường hợp rỗng và chuỗi phần tử rỗng

Ba trường hợp tưởng giống nhau nhưng khác về số phần tử:

| Đầu vào | Gọi `joining(",", "[", "]")` | Kết quả |
| --- | --- | --- |
| Không có phần tử | `Stream.<String>empty()` | `[]` |
| Một phần tử là chuỗi rỗng `""` | `Stream.of("")` | `[]` |
| Hai phần tử đều là chuỗi rỗng | `Stream.of("", "")` | `[,]` |
| Ba phần tử: rỗng, rỗng, `"X"` | `Stream.of("", "", "X")` | `[,,X]` |
| Một phần tử `"A"` | `Stream.of("A")` | `[A]` |

**Lưu ý quan trọng:** kết quả hiển thị `[]` **không đủ để xác định Stream có rỗng hay có một phần tử chuỗi rỗng**. Sau khi đã tạo chuỗi, thông tin về số phần tử có thể bị mất. Nếu logic nghiệp vụ cần biết “không có dữ liệu”, hãy kiểm tra nguồn hoặc thu thập thêm trạng thái trước khi định dạng; đừng suy diễn từ kết quả `String`.

Với `joining("; ", "(", ")")`, đầu vào rỗng tạo `()`. Với `joining("; ")`, đầu vào rỗng tạo `""`. Delimiter không được viết vào kết quả nếu không tồn tại **hai phần tử** để ngăn cách.

## 4. Chuẩn hóa dữ liệu trước khi `joining`

`joining` chỉ **nối** các chuỗi đầu vào. Nó không tự xóa khoảng trắng, lọc chuỗi rỗng, loại `null`, sắp xếp, chuyển số thành chuỗi, hay thêm dấu ngoặc cho **mỗi** phần tử.

Đặt các thao tác `filter`, `map`, `sorted` trước `collect`:

```text
Nguồn → [lọc dữ liệu] → [chuyển thành CharSequence] → [sắp xếp khi cần] → collect(joining(...))
```

Ví dụ thực tế:
- Các ID kiểu `Integer`: `map(String::valueOf)` rồi `joining(",")`.
- Các tên nhập vào chứa khoảng trắng, giá trị rỗng và `null`: `filter(Objects::nonNull)`, `map(String::trim)`, `filter(s -> !s.isEmpty())` trước khi nối.
- Nếu muốn mỗi phần tử nằm trong dấu ngoặc riêng: `map(s -> "(" + s + ")")` rồi `joining(...)`. `prefix`/`suffix` chỉ bao **toàn chuỗi**.

Tạo tệp `JoiningDataDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningDataDemo {
    public static void main(String[] args) {
        List<Integer> ids = Arrays.asList(7, 12, 35);
        System.out.println("ids = "
                + ids.stream()
                        .map(String::valueOf)
                        .collect(Collectors.joining(",", "ids=", "")));

        List<String> raw = Arrays.asList("  red ", "", null, " blue ", "  ");
        String cleaned = raw.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.joining(", ", "<", ">"));
        System.out.println("cleaned = " + cleaned);

        String perItem = Stream.of("x", "y")
                .map(s -> "(" + s + ")")
                .collect(Collectors.joining(" + ", "begin=", "!"));
        System.out.println("per item = " + perItem);
    }
}
```

```bash
javac -encoding UTF-8 JoiningDataDemo.java
java JoiningDataDemo
```

```text
ids = ids=7,12,35
cleaned = <red, blue>
per item = begin=(x) + (y)!
```

Giải thích:
- `map(String::valueOf)` biến các số thành `String`, đáp ứng loại phần tử mà `joining` nhận. Giá trị `ids=` là **prefix**; suffix ở đây là chuỗi rỗng.
- Dãy màu có `null`, khoảng trắng hoặc chuỗi rỗng đã được lọc trước khi nối; dấu `< >` bao **toàn kết quả**, không bao từng màu.
- `map(s -> "(" + s + ")")` định dạng từng phần tử; dấu `begin=` và `!` chỉ xuất hiện một lần.

Nếu cần chuẩn hóa chữ hoa/thường theo ngôn ngữ, hãy dùng quy tắc locale được xác định rõ (`toLowerCase(Locale.ROOT)` cho mã định danh không phụ thuộc ngôn ngữ, hoặc locale cụ thể cho dữ liệu ngôn ngữ tự nhiên). `joining` không xử lý việc này.

## 5. `null`: phân biệt phần tử, tham số và nguồn

### 5.1. Phần tử `null` không tự bị bỏ qua

Với các overload có delimiter, collector dùng `StringJoiner` để tích lũy phần tử. Theo hợp đồng `StringJoiner.add`, nếu phần tử được thêm là `null` thì nội dung `"null"` (bốn chữ cái) được chèn vào kết quả:

```java
String value = Stream.of("A", null, "B")
        .collect(Collectors.joining("|", "[", "]"));
// "[A|null|B]"
```

Đây **không phải JSON null** và không thể coi là dữ liệu đã được làm sạch. Nếu `null` là dữ liệu không hợp lệ, hãy lọc hoặc thay thế rõ ràng:

```java
String withoutNull = Stream.of("A", null, "B")
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|", "[", "]"));
// "[A|B]"

String withFallback = Stream.of("A", null, "B")
        .map(s -> s == null ? "(missing)" : s)
        .collect(Collectors.joining("|", "[", "]"));
// "[A|(missing)|B]"
```

Hai đoạn trên là mã minh họa nằm trong ngữ cảnh đã import `java.util.Objects`, `java.util.stream.Collectors` và `java.util.stream.Stream`. Chọn lọc hay hiển thị mặc định theo hợp đồng dữ liệu, không theo thói quen.

### 5.2. `delimiter`, `prefix`, `suffix` bằng `null` là lỗi

Ba tham số thuộc overload ba đối số phải khác `null`. Truyền `null` có thể làm `collect(...)` ném `NullPointerException` ngay cả với nguồn rỗng; muốn “không có” delimiter/prefix/suffix, hãy truyền `""` thay thế. Ví dụ:

```java
Stream.<String>empty()
        .collect(Collectors.joining(null, "[", "]"));
// NullPointerException
```

Đừng nhầm với phần tử `null`: phần tử `null` được chuyển thành chữ `"null"` theo `StringJoiner.add`, còn **tham số cấu hình `null` không hợp lệ**.

Nếu **biến nguồn** bằng `null` (chẳng hạn `List<String> source = null;`), `source.stream()` đã ném `NullPointerException` **trước** lúc collector được chạy. Hãy xử lý nguồn null theo chính sách ứng dụng thay vì mong `joining` tự biến nó thành Stream rỗng.

### 5.3. Ví dụ kiểm chứng ngoại lệ và thứ tự

Tạo tệp `JoiningEdgeCasesDemo.java`:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningEdgeCasesDemo {
    public static void main(String[] args) {
        System.out.println("null element = "
                + Stream.of("A", null, "B")
                        .collect(Collectors.joining("|", "[", "]")));
        System.out.println("empty element = "
                + Stream.of("", "", "X")
                        .collect(Collectors.joining(",", "<", ">")));
        System.out.println("empty input = "
                + Stream.<String>empty()
                        .collect(Collectors.joining(",", "<", ">")));

        try {
            Stream.<String>empty()
                    .collect(Collectors.joining(null, "[", "]"));
        } catch (NullPointerException e) {
            System.out.println("null delimiter = NullPointerException");
        }

        String ordered = Stream.of("b", "a", "c")
                .sorted()
                .parallel()
                .collect(Collectors.joining(",", "{", "}"));
        System.out.println("sorted parallel = " + ordered);
    }
}
```

```bash
javac -encoding UTF-8 JoiningEdgeCasesDemo.java
java JoiningEdgeCasesDemo
```

```text
null element = [A|null|B]
empty element = <,,X>
empty input = <>
null delimiter = NullPointerException
sorted parallel = {a,b,c}
```

`empty element` có ba phần tử (hai chuỗi rỗng và `"X"`), vì vậy hai dấu phẩy vẫn xuất hiện. `empty input` có 0 phần tử nên chỉ có prefix `<` và suffix `>`. Ví dụ `sorted().parallel()` vẫn cho thứ tự `a,b,c` vì nguồn `Stream.of(...)` có thứ tự và `sorted()` xác định lại encounter order.

## 6. Thứ tự phần tử, Stream song song và collector lồng nhau

`Collectors.joining` nối theo **encounter order** của Stream **khi Stream có thứ tự**:

- `List.stream()` duyệt theo thứ tự danh sách; `Stream.of(...)` duyệt theo thứ tự tham số.
- `sorted()` tạo thứ tự sắp xếp trước khi nối. `distinct()` loại trùng lặp theo hợp đồng Stream mà không tự thêm dấu phân cách.
- Với Stream có thứ tự, `parallel()` không có nghĩa chuỗi kết quả bị đảo thứ tự: `joining` vẫn dùng encounter order. Chạy song song không bảo đảm nhanh hơn đối với dữ liệu nhỏ.
- Với nguồn không có thứ tự bảo đảm (ví dụ một `HashSet`), kết quả `joining` không có thứ tự có thể dự đoán giữa các môi trường/lần chạy. Nếu giao diện hoặc snapshot test cần ổn định, sắp xếp chủ đích: `source.stream().sorted().collect(Collectors.joining(", "))`.

`joining` còn có thể làm downstream collector khi nhóm dữ liệu. Ví dụ sau là **đoạn mã đặt trong phương thức** đã import `java.util.Map`, `java.util.TreeMap`, `java.util.stream.Stream`, `java.util.stream.Collectors`:

```java
Map<Character, String> byInitial = Stream.of("An", "Anh", "Binh")
        .collect(Collectors.groupingBy(
                s -> s.charAt(0),
                TreeMap::new,
                Collectors.joining(" / ")));

System.out.println(byInitial.get('A')); // An / Anh
System.out.println(byInitial.get('B')); // Binh
```

`groupingBy` chia thành nhóm; `joining` định dạng chuỗi của từng nhóm. `TreeMap` ở đây làm thứ tự khóa của Map có thể dự đoán; việc nối trong mỗi nhóm dựa vào encounter order của các giá trị tương ứng.

## 7. `Collectors.joining` khác `String.join` và `StringJoiner` như thế nào?

| API | Thích hợp khi | Ví dụ |
| --- | --- | --- |
| `Collectors.joining(", ", "[", "]")` | Đã có Stream/pipeline với `map`, `filter`, `sorted`; muốn chuỗi bao ngoài | `names.stream().collect(...)` |
| `String.join(", ", names)` | Đã có `Iterable<? extends CharSequence>` hoặc danh sách phần tử đơn giản; chỉ cần delimiter | `String.join(", ", names)` |
| `new StringJoiner(", ", "[", "]")` | Muốn thêm phần tử dần theo các nhánh logic ngoài pipeline Stream | `joiner.add("A").add("B").toString()` |

Cả ba API vẫn được hỗ trợ trong Java hiện đại. `String.join` không có overload nhận riêng `prefix` và `suffix`; có thể bao thêm bằng phép nối chuỗi, nhưng với một pipeline Stream thì overload ba đối số của `Collectors.joining` diễn đạt ý định rõ hơn.

Cơ chế của các overload có delimiter dựa vào `StringJoiner`: nó biết khi nào cần chèn delimiter giữa các phần tử; khi chưa có phần tử, giá trị mặc định là `prefix + suffix`. `StringJoiner` trực tiếp có phương thức `setEmptyValue(...)` cho nhu cầu hiển thị riêng khi rỗng, nhưng đây **không phải tham số** có sẵn của `Collectors.joining`. Nếu định dạng “rỗng” mang ý nghĩa nghiệp vụ riêng, hãy quyết định từ dữ liệu/đếm phần tử thay vì cố suy diễn từ chuỗi đã ghép.

Lựa chọn nên dựa vào cấu trúc dữ liệu và độ rõ ràng của code; tránh khẳng định `joining` luôn nhanh hơn mọi vòng lặp hoặc phép nối `StringBuilder` trong tất cả tình huống. Không dùng `parallel()` chỉ để tăng tốc một thao tác định dạng nhỏ.

## 8. Các lỗi thiết kế thường gặp

**Lỗi 1 — Dùng `Collectors.joining` trực tiếp với số hoặc object tùy ý.**

```java
List<Integer> ids = Arrays.asList(1, 2, 3);
// ids.stream().collect(Collectors.joining(",")); // Không biên dịch.

String csv = ids.stream()
        .map(String::valueOf)
        .collect(Collectors.joining(","));
// "1,2,3"
```

Collector nhận phần tử thuộc `CharSequence`; `map` biến số thành chuỗi trước. Đoạn trên là minh họa trong phương thức đã import `Arrays`, `List`, `Collectors`.

**Lỗi 2 — Hiểu nhầm prefix/suffix áp dụng cho mỗi phần tử.**

```java
Stream.of("A", "B").collect(Collectors.joining(",", "(", ")"));
// "(A,B)" chứ không phải "(A),(B)"

Stream.of("A", "B")
        .map(s -> "(" + s + ")")
        .collect(Collectors.joining(","));
// "(A),(B)"
```

**Lỗi 3 — Mong có delimiter cuối chuỗi.** `joining(",")` tạo `"A,B"`, không tạo `"A,B,"`. Nếu một giao thức thực sự yêu cầu ký tự cuối, cần định dạng giao thức rõ ràng; không diễn giải suffix là “dấu phân cách lặp lại”.

**Lỗi 4 — Dùng `joining` để xuất CSV/JSON/XML tùy tiện.** `joining` chỉ thêm ký tự, **không escaping** dấu phẩy, dấu ngoặc kép, dấu xuống dòng hoặc ký tự đặc biệt của từng định dạng. Ví dụ, nối tên `"Nguyen, An"` và `"Binh"` bằng `","` cho chuỗi nhìn như ba cột CSV. Với dữ liệu CSV thực sự, dùng writer có khả năng quote/escape theo chuẩn. Với JSON/XML, dùng serializer chuyên dụng. Bao ngoài bằng `"["` và `"]"` **không** tự tạo JSON hợp lệ cho mọi phần tử.

**Lỗi 5 — Bỏ qua `null` hoặc chuỗi trắng.** `joining` không lọc `null`. `Stream.of("A", null).collect(joining(","))` dẫn đến văn bản `A,null`. Khi cần bỏ giá trị thiếu, dùng `filter(Objects::nonNull)`; khi cần loại chuỗi trắng, `map(String::trim)` rồi `filter(s -> !s.isEmpty())`, như ví dụ chạy được phía trên.

**Lỗi 6 — Tin rằng thứ tự của nguồn bất kỳ là cố định.** `HashSet` và các Stream bị đánh dấu `unordered()` không cam kết encounter order ổn định. Nếu đầu ra dùng trong log so sánh, test hoặc chữ ký dữ liệu, thêm `sorted()` với comparator thích hợp; sau đó mới `joining`.

**Lỗi 7 — Sử dụng lại cùng Stream đã kết thúc.**

```java
Stream<String> stream = Stream.of("A", "B");
String first = stream.collect(Collectors.joining(","));
// stream.collect(Collectors.joining("|")); // Sai: Stream đã bị tiêu thụ.
```

Khi nguồn là `List`, gọi `list.stream()` mỗi khi cần pipeline mới. Không gọi nhiều terminal operation trên cùng đối tượng Stream.

## 9. Quy trình lựa chọn tham số đúng nhu cầu

1. **Xác định phần tử đầu vào.** Nếu không phải `CharSequence`, dùng `map` để chuyển; nếu dữ liệu có `null`, quyết định lọc hay thay bằng nhãn.
2. **Xác định separator thực sự.** Dùng `", "` cho danh sách dễ đọc, `" | "` cho log, `"\n"` cho nhiều dòng. Delimiter chỉ nằm giữa hai phần tử.
3. **Xác định có cần bao toàn bộ kết quả.** Nếu có, dùng overload ba đối số và truyền `prefix`/`suffix`; nếu không, dùng overload một đối số; nếu không cần delimiter thì dùng overload không đối số.
4. **Xác định ý nghĩa của tập rỗng.** Overload ba đối số luôn cho `prefix + suffix` khi rỗng; nếu muốn thông điệp “không có dữ liệu”, xử lý trước hoặc giữ kèm metadata về số lượng.
5. **Xác định yêu cầu thứ tự và tính hợp lệ của định dạng.** Sắp xếp khi cần đầu ra ổn định; không dùng `joining` làm CSV/JSON/XML serializer.
6. **Đọc kết quả như một `String` đã định dạng.** Không dựa vào delimiter để khôi phục chắc chắn từng phần tử khi nội dung phần tử cũng có thể chứa delimiter.

## 10. Tự kiểm tra

**Câu 1.** `Stream.of("x", "y").collect(Collectors.joining("-", "{", "}"))` trả gì?  
**Đáp án:** `{x-y}`. Delimiter đứng giữa, prefix/suffix bao ngoài.

**Câu 2.** `Stream.<String>empty().collect(Collectors.joining(";", "(", ")"))` trả gì?  
**Đáp án:** `()`. Không có delimiter vì không có cặp phần tử.

**Câu 3.** `Stream.of("", "").collect(Collectors.joining(",", "[", "]"))` trả gì?  
**Đáp án:** `[,]`. Có hai phần tử chuỗi rỗng nên vẫn có một delimiter.

**Câu 4.** `Stream.of(10, 20).collect(Collectors.joining(","))` có hợp lệ không?  
**Đáp án:** Không biên dịch, vì Stream phần tử `Integer` không khớp collector nhận `CharSequence`. Dùng `map(String::valueOf)` trước `collect`.

**Câu 5.** `Collectors.joining(",", "[", "]")` có tự escape dấu phẩy nằm trong phần tử không?  
**Đáp án:** Không. Đây là nối chuỗi ký tự, không phải bộ mã hóa CSV/JSON.

**Câu 6.** Prefix có thay được việc `map(s -> "(" + s + ")")` để bọc mỗi phần tử không?  
**Đáp án:** Không. Prefix chỉ xuất hiện **một lần** ở đầu toàn bộ chuỗi.

## 11. Ghi nhớ

- Công thức: **`prefix + (các phần tử ghép bằng delimiter) + suffix`**.
- Không có phần tử: overload ba tham số trả **`prefix + suffix`**; có đúng một phần tử thì không có delimiter.
- `joining` là terminal collector cho dữ liệu dạng `CharSequence`; lọc/chuẩn hóa/chuyển kiểu trước `collect` khi cần.
- Phần tử `null` có thể thành chữ `"null"`; tham số `delimiter/prefix/suffix` bằng `null` gây lỗi. Hai trường hợp khác nhau.
- Nếu Stream có encounter order, kết quả nối giữ thứ tự đó; đầu vào không có thứ tự bảo đảm thì không suy ra được chuỗi ổn định.
- Chỉ dùng để định dạng chuỗi đơn giản; các định dạng trao đổi dữ liệu có quy tắc escape riêng cần bộ ghi/serializer phù hợp.

### Tài liệu Java API chính thức (vẫn áp dụng)

- [`Collectors.joining`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#joining(java.lang.CharSequence,java.lang.CharSequence,java.lang.CharSequence)): chữ ký, ba overload và encounter order.
- [`StringJoiner`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/StringJoiner.html): delimiter, prefix, suffix, `add(null)` và kết quả khi rỗng.
- [`String.join`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#join(java.lang.CharSequence,java.lang.Iterable)): phương án khi đầu vào đã là một `Iterable`.
- [`Stream.collect`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector)): terminal operation thu thập kết quả.
