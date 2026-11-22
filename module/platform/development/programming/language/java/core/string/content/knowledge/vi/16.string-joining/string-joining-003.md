# Chính sách `null` của delimiter, tập phần tử và từng phần tử khi ghép chuỗi Java

## 1. Vì sao phải phân biệt ba loại `null`?

Khi ghép nhiều phần thành một chuỗi, Java cho phép dùng `String.join(...)` với **delimiter** (chuỗi phân cách) và một **tập phần tử** dưới dạng varargs hoặc `Iterable`. Có ba chỗ độc lập có thể mang giá trị `null`:

1. **Delimiter `null`:** chuỗi dùng để ngăn cách các phần tử không tồn tại.
2. **Tập phần tử `null`:** chính mảng varargs hoặc đối tượng `Iterable` không tồn tại.
3. **Một phần tử `null`:** tập phần tử có tồn tại nhưng một mục bên trong bằng `null`.

Ba trường hợp **không có cùng hành vi**. Theo API của Java 17:

| Vị trí `null` | Ví dụ | Kết quả |
| --- | --- | --- |
| Delimiter | `String.join(null, "A", "B")` | Ném `NullPointerException`. |
| Mảng varargs `elements` | `String.join(",", (CharSequence[]) null)` | Ném `NullPointerException`. |
| `Iterable elements` | `String.join(",", (Iterable<? extends CharSequence>) null)` | Ném `NullPointerException`. |
| Một phần tử trong varargs | `String.join(",", "A", null, "B")` | `"A,null,B"`. |
| Một phần tử trong `Iterable` | `String.join(",", Arrays.asList("A", null, "B"))` | `"A,null,B"`. |

**Quy tắc ngắn gọn:** `String.join` yêu cầu **delimiter và tập phần tử không được `null`**, nhưng nếu **một phần tử riêng lẻ** là `null`, nó sẽ được biểu diễn bằng chuỗi ký tự `"null"`.

Điều này rất quan trọng khi xuất dữ liệu, tạo log, xây dựng câu lệnh cấu hình, hoặc chuyển danh sách thành chuỗi. Chuỗi chữ `"null"` không nhất thiết có cùng ý nghĩa với giá trị `null` ban đầu của ứng dụng.

## 2. Hai overload của `String.join`

Từ Java 8, `String` có hai overload:

```java
public static String join(
        CharSequence delimiter,
        CharSequence... elements)

public static String join(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements)
```

### 2.1. Overload varargs

```java
String result = String.join(" | ", "Java", "Core", "String");
System.out.println(result); // Java | Core | String
```

`elements` được biểu diễn bằng một mảng `CharSequence[]` khi lời gọi được xử lý. Thông thường người lập trình không phải tự tạo mảng; chỉ cần liệt kê các đối số.

### 2.2. Overload `Iterable`

```java
import java.util.List;

List<String> words = List.of("Java", "Core", "String");
String result = String.join(" | ", words);

System.out.println(result); // Java | Core | String
```

Đây là một `Iterable` có ba phần tử. Hợp đồng xử lý `null` của các **phần tử** vẫn giống overload varargs: một mục bằng `null` được thêm dưới dạng chữ `"null"`.

Chú ý: `List.of(...)` **không chấp nhận phần tử `null`**. Nếu cần minh họa một `Iterable` thực sự chứa `null`, có thể dùng `Arrays.asList(...)` hoặc một collection cho phép `null`:

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("Java", null, "String");
System.out.println(String.join(" | ", words));
// Java | null | String
```

**Phân biệt rõ:** lỗi khi cố tạo `List.of("A", null)` là do **`List.of`**, không phải do `String.join`. `String.join` chấp nhận mục `null` nếu collection đã chứa nó.

## 3. Trường hợp thứ nhất: delimiter bằng `null`

Delimiter là nội dung được chèn **giữa các phần tử liên tiếp**, ví dụ `","`, `"; "` hoặc `" | "`. Nếu delimiter bằng `null`, `String.join` ném `NullPointerException`:

```java
String separator = null;

// Ném NullPointerException:
String value = String.join(separator, "A", "B");
```

Đặc điểm:
- `null` không được tự hiểu là chuỗi rỗng.
- `null` không được tự hiểu là dấu phẩy.
- Không nên dùng biểu diễn chữ `"null"` làm delimiter dự phòng nếu nghiệp vụ không quy định như vậy.
- **Delimiter rỗng `""` là hợp lệ** và khác delimiter `null`.

Ví dụ delimiter rỗng:

```java
System.out.println(String.join("", "A", "B", "C")); // ABC
```

### Chọn chính sách cho delimiter từ người dùng

Nếu việc thiếu delimiter là lỗi của đầu vào, nên **fail fast**:

```java
import java.util.Objects;

static String joinRequiredDelimiter(
        CharSequence delimiter,
        Iterable<? extends CharSequence> parts) {
    Objects.requireNonNull(delimiter, "delimiter");
    Objects.requireNonNull(parts, "parts");
    return String.join(delimiter, parts);
}
```

Đoạn trên là **phương thức hỗ trợ đặt trong lớp Java**, không phải file chạy độc lập. Khi delimiter hoặc tập phần tử là `null`, thông báo lỗi sẽ chỉ ra thành phần vi phạm hợp đồng.

Nếu sản phẩm thực sự muốn coi delimiter thiếu là “không có ký tự phân cách”, hãy chuẩn hóa **có chủ đích** trước:

```java
String effectiveDelimiter =
        delimiter == null ? "" : delimiter.toString();

String result = String.join(effectiveDelimiter, "A", "B");
```

Khi `delimiter == null`, kết quả là `"AB"`. Đây là **chính sách do ứng dụng chọn**, không phải hành vi mặc định của `String.join`.

## 4. Trường hợp thứ hai: toàn bộ tập phần tử bằng `null`

Tập phần tử có thể được truyền dưới dạng `CharSequence[]` hoặc `Iterable<? extends CharSequence>`. Nếu bản thân đối tượng tập hợp không tồn tại, `String.join` không có nguồn dữ liệu để duyệt và ném `NullPointerException`.

### 4.1. Mảng varargs `null`

```java
CharSequence[] parts = null;

// Ném NullPointerException:
String result = String.join(",", parts);
```

### 4.2. `Iterable` bằng `null`

```java
Iterable<String> parts = null;

// Ném NullPointerException:
String result = String.join(",", parts);
```

Nhưng **tập phần tử rỗng** hoàn toàn hợp lệ:

```java
System.out.println("[" + String.join(",") + "]"); // []
System.out.println("[" + String.join(",", java.util.List.<String>of()) + "]");
// []
```

Hai dòng trên in `[]` do chúng ta chủ động thêm dấu ngoặc vuông; kết quả của `String.join` thực tế là **chuỗi rỗng `""`**, không phải chuỗi `"[]"`.

| Đầu vào | Ví dụ | Kết quả |
| --- | --- | --- |
| Tập `null` | `(CharSequence[]) null` | `NullPointerException` |
| Tập có 0 phần tử | `new CharSequence[0]` | `""` |
| Tập có 1 phần tử rỗng | `new CharSequence[]{""}` | `""` |
| Tập có 1 phần tử `null` | `new CharSequence[]{null}` | `"null"` |

**Quan trọng:** tập rỗng và tập chỉ có một chuỗi rỗng cho cùng văn bản `""` sau khi join. Vì thế `String.join` **không phải một định dạng lưu trữ có khả năng khôi phục đầy đủ danh sách gốc** trong mọi tình huống.

### Chính sách cho tập `null`

Ba lựa chọn phổ biến:

- **Báo lỗi:** input bắt buộc phải có; dùng `Objects.requireNonNull(parts)`.
- **Coi như tập rỗng:** chỉ khi hợp đồng nghiệp vụ cho phép. Ví dụ chuyển `null` thành `List.of()` trước khi join.
- **Phân biệt “chưa có dữ liệu” và “danh sách rỗng”:** không biến cả hai thành `""` nếu ứng dụng cần giữ thông tin khác biệt. Có thể dùng kiểu dữ liệu hoặc trường trạng thái riêng.

Ví dụ coi danh sách `null` là rỗng một cách tường minh:

```java
static String joinOrEmpty(
        String delimiter,
        java.util.List<String> parts) {
    java.util.Objects.requireNonNull(delimiter, "delimiter");
    return String.join(
            delimiter,
            parts == null ? java.util.List.<String>of() : parts);
}
```

Hàm vẫn báo lỗi nếu delimiter `null`, nhưng cho phép không có `parts` và trả về chuỗi rỗng. Đó là **một thiết kế tùy chọn**; không nên áp dụng mặc định khi dữ liệu bắt buộc.

## 5. Trường hợp thứ ba: từng phần tử có thể bằng `null`

Khi một mục trong tập là `null`, `String.join` thêm **bốn ký tự** `n`, `u`, `l`, `l`:

```java
String result = String.join("|", "A", null, "B");
System.out.println(result); // A|null|B
```

Tương tự với `Iterable`:

```java
java.util.List<String> parts =
        java.util.Arrays.asList("A", null, "B");

System.out.println(String.join("|", parts)); // A|null|B
```

Điều đó **không** tương đương với một trong các hành vi sau:
- Bỏ phần tử `null` → `"A|B"`.
- Thay phần tử `null` thành chuỗi rỗng → `"A||B"`.
- Ném ngoại lệ ngay khi gặp phần tử `null`.
- Chèn một giá trị nullable có thể khôi phục nguyên trạng sau khi split.

Nếu `"null"` cũng có thể là chuỗi hợp lệ do người dùng nhập, kết quả join **không cho phép phân biệt**:

```java
String a = String.join(",", "A", (CharSequence) null);
String b = String.join(",", "A", "null");

System.out.println(a);          // A,null
System.out.println(b);          // A,null
System.out.println(a.equals(b)); // true
```

**Đây là mất thông tin**, không phải bug của `String.join`. Khi hệ thống cần phân biệt giá trị vắng mặt và chuỗi văn bản `"null"`, hãy dùng một cách mã hóa có quy tắc riêng (ví dụ JSON với `null` đúng kiểu và chuỗi `"null"` được đặt trong dấu nháy), thay vì lấy kết quả join làm định dạng lưu trữ chính.

### Điểm chú ý về overload khi truyền literal `null`

Do `String.join` có cả overload varargs và `Iterable`, lời gọi dùng `null` không chỉ rõ kiểu như:

```java
// Không nên dùng vì dễ mơ hồ overload:
// String.join(",", null);
```

Có thể dẫn đến vấn đề lựa chọn overload hoặc diễn giải `null` là cả mảng/tập thay vì một phần tử. **Hãy khai báo hoặc ép kiểu rõ ý định**:

```java
System.out.println(String.join("|", (CharSequence) null));
// null  (một phần tử null được chuyển thành chữ "null")

// Ném NullPointerException: toàn bộ mảng varargs null.
// String.join("|", (CharSequence[]) null);

// Ném NullPointerException: toàn bộ Iterable null.
// String.join("|", (Iterable<? extends CharSequence>) null);
```

Điều khác biệt là **kiểu tại vị trí đối số** và overload Java chọn, không chỉ hình thức viết chữ `null`.

## 6. Phân biệt phần tử rỗng, phần tử `null` và phần tử có dấu phân cách

Xét delimiter `","`:

| Danh sách đầu vào | Kết quả `String.join(",", ...)` | Nhận xét |
| --- | --- | --- |
| `["A", "B"]` | `"A,B"` | Bình thường |
| `["A", null, "B"]` | `"A,null,B"` | Giá trị `null` trở thành chữ `"null"` |
| `["A", "", "B"]` | `"A,,B"` | Vị trí rỗng vẫn được giữ lại |
| `["A", "null", "B"]` | `"A,null,B"` | Không phân biệt được với phần tử `null` |
| `["A,B", "C"]` | `"A,B,C"` | Dữ liệu chứa delimiter, không tự escape |
| `[]` | `""` | Không có phần tử |
| `[""]` | `""` | Một phần tử rỗng, cùng kết quả với tập rỗng |

`String.join` **không phải một trình mã hóa CSV**. Nó không tự thêm dấu nháy cho giá trị chứa dấu phân cách, không escape dấu nháy, và cũng không tạo cách biểu diễn nullable có thể khôi phục an toàn. Nếu làm CSV, JSON, TSV hoặc dữ liệu trao đổi theo chuẩn cụ thể, hãy dùng bộ mã hóa đúng định dạng đó.

Ví dụ dấu phẩy nằm trong dữ liệu:

```java
System.out.println(String.join(",", "New York, NY", "USA"));
// New York, NY,USA
```

Không thể tách lại kết quả này thành chính xác hai phần ban đầu chỉ bằng `split(",")`. Chọn delimiter khác đôi khi giảm va chạm nhưng **không thay thế escape/quoting**.

## 7. Bốn chính sách phổ biến đối với phần tử `null`

Nếu nghiệp vụ có yêu cầu khác mặc định của `String.join`, bạn cần xử lý phần tử **trước khi ghép**.

Dùng một danh sách có `null` thật sự:

```java
java.util.List<String> parts =
        java.util.Arrays.asList("A", null, "B");
```

### Chính sách A — Giữ mặc định: chữ `"null"`

```java
String output = String.join("|", parts);
System.out.println(output); // A|null|B
```

Phù hợp với một số log hoặc mục đích đọc thủ công, nơi bạn chấp nhận `null` chỉ là biểu diễn văn bản, không cần khôi phục kiểu dữ liệu ban đầu.

### Chính sách B — Bỏ các mục `null`

```java
import java.util.Objects;
import java.util.stream.Collectors;

String output = parts.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|"));

System.out.println(output); // A|B
```

**Tác động:** số vị trí trong chuỗi xuất ra giảm. Nếu các phần tử là cột dữ liệu cố định (ví dụ mã đơn hàng, ngày, người nhận), bỏ một mục có thể làm lệch vị trí của các cột sau.

### Chính sách C — Thay `null` bằng chuỗi rỗng

```java
import java.util.stream.Collectors;

String output = parts.stream()
        .map(x -> x == null ? "" : x)
        .collect(Collectors.joining("|"));

System.out.println(output); // A||B
```

Cách này giữ vị trí phần tử giữa hai delimiter, nhưng không phân biệt `null` với một chuỗi rỗng vốn tồn tại trong dữ liệu gốc.

### Chính sách D — Thay bằng placeholder có ý nghĩa

```java
import java.util.stream.Collectors;

String output = parts.stream()
        .map(x -> x == null ? "<missing>" : x)
        .collect(Collectors.joining("|"));

System.out.println(output); // A|<missing>|B
```

Placeholder chỉ thích hợp nếu hợp đồng nghiệp vụ xác định rõ nó, và nếu chuỗi `"<missing>"` có thể xuất hiện trong dữ liệu thật thì vẫn cần cơ chế escape/phân biệt.

### Chính sách E — Cấm phần tử `null` (fail fast)

```java
import java.util.Objects;
import java.util.stream.Collectors;

String output = parts.stream()
        .map(x -> Objects.requireNonNull(x, "part"))
        .collect(Collectors.joining("|"));
```

Ở danh sách `["A", null, "B"]`, đoạn này ném `NullPointerException` với thông báo `"part"`. Cách xử lý phù hợp khi **mỗi phần tử bắt buộc có dữ liệu** và bạn muốn phát hiện lỗi tại ranh giới nghiệp vụ, thay vì âm thầm tạo văn bản `"null"`.

**Không có chính sách nào tốt nhất trong mọi tình huống.** Hãy quyết định rõ có cần giữ số lượng phần tử, vị trí cột, thông tin `null`, hoặc khả năng phục hồi giá trị gốc hay không.

## 8. Chương trình Java 17+ chạy độc lập

Lưu nội dung sau vào file `JoinNullPolicyDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class JoinNullPolicyDemo {
    private static void showResult(String label, Supplier<String> action) {
        try {
            System.out.println(label + " = " + action.get());
        } catch (NullPointerException ex) {
            System.out.println(label + " = NullPointerException");
        }
    }

    public static void main(String[] args) {
        List<String> parts = Arrays.asList("A", null, "B");

        System.out.println("varargs = ["
                + String.join("|", "A", null, "B") + "]");
        System.out.println("iterable = ["
                + String.join("|", parts) + "]");
        System.out.println("single null = ["
                + String.join("|", (CharSequence) null) + "]");
        System.out.println("empty varargs = ["
                + String.join("|") + "]");
        System.out.println("empty iterable = ["
                + String.join("|", List.<String>of()) + "]");
        System.out.println("empty member = ["
                + String.join("|", "A", "", "B") + "]");

        showResult("null delimiter",
                () -> String.join((CharSequence) null, "A", "B"));
        showResult("null array",
                () -> String.join("|", (CharSequence[]) null));
        showResult("null iterable",
                () -> String.join("|",
                        (Iterable<? extends CharSequence>) null));

        System.out.println("joiner = ["
                + new StringJoiner("|").add(null).add("B") + "]");

        String skip = parts.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.joining("|"));
        System.out.println("skip null = [" + skip + "]");

        String asEmpty = parts.stream()
                .map(x -> x == null ? "" : x)
                .collect(Collectors.joining("|"));
        System.out.println("null as empty = [" + asEmpty + "]");

        String placeholder = parts.stream()
                .map(x -> x == null ? "<missing>" : x)
                .collect(Collectors.joining("|"));
        System.out.println("placeholder = [" + placeholder + "]");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 JoinNullPolicyDemo.java
java JoinNullPolicyDemo
```

Đầu ra:

```text
varargs = [A|null|B]
iterable = [A|null|B]
single null = [null]
empty varargs = []
empty iterable = []
empty member = [A||B]
null delimiter = NullPointerException
null array = NullPointerException
null iterable = NullPointerException
joiner = [null|B]
skip null = [A|B]
null as empty = [A||B]
placeholder = [A|<missing>|B]
```

**Giải thích kết quả:**
- Varargs và `Iterable` cùng chèn chữ `"null"` cho một phần tử `null`.
- Một `null` được ép kiểu `CharSequence` là **một phần tử**, nên nhận `"null"`.
- Tập rỗng tạo chuỗi rỗng, nhưng phần tử rỗng ở giữa vẫn giữ hai delimiter.
- Delimiter, mảng varargs, hoặc đối tượng `Iterable` đều không được bằng `null`.
- `StringJoiner.add(null)` cũng thêm văn bản `"null"`.
- Các chính sách `skip`, `asEmpty` và `placeholder` biến đổi danh sách theo cách khác nhau **trước khi nối**.

Chương trình chủ động bắt `NullPointerException` ở từng thí nghiệm để chứng minh hành vi, chứ không khuyến khích dùng `try/catch` thay thế xác thực đầu vào trong mọi chương trình thực tế.

## 9. `StringJoiner` và `Collectors.joining` liên quan thế nào?

`StringJoiner` là công cụ bổ sung hữu ích nếu cần thêm phần tử dần dần hoặc muốn prefix/suffix:

```java
import java.util.StringJoiner;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("A");
joiner.add(null);
joiner.add("B");

System.out.println(joiner.toString()); // [A, null, B]
```

Với `StringJoiner`:
- Delimiter truyền vào constructor không được `null`; nếu `null` thì ném `NullPointerException`.
- `add((CharSequence) null)` chèn văn bản `"null"`.
- Constructor ba tham số còn yêu cầu `prefix` và `suffix` không `null`.
- Nếu chưa thêm phần tử, biểu diễn mặc định gồm `prefix + suffix`; có thể cấu hình `setEmptyValue` nếu cần.

Ví dụ phân biệt rỗng và một phần tử rỗng:

```java
StringJoiner empty = new StringJoiner(",", "[", "]");
System.out.println(empty); // []

StringJoiner oneBlank = new StringJoiner(",", "[", "]");
oneBlank.add("");
System.out.println(oneBlank); // []
```

Dù biểu diễn ngoài giống nhau, trạng thái “đã thêm một phần tử” khác nhau. Khi cần khả năng khôi phục chính xác cấu trúc dữ liệu, không nên xem `StringJoiner` hay `String.join` là một bộ mã hóa cấu trúc.

`Collectors.joining(delimiter)` thường được dùng sau `stream()`. Nó giúp ứng dụng **lọc**, **ánh xạ** hoặc **kiểm tra** đầu vào trước khi nối:

```java
String result = parts.stream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.joining(","));
```

Nếu `parts` bằng `null` thì gọi `parts.stream()` đã gây `NullPointerException` trước khi `Collectors.joining` có cơ hội xử lý. Nếu bạn cần coi danh sách `null` là rỗng, việc lựa chọn đó phải diễn ra **trước lệnh `stream()`**.

Không nên suy luận rằng chỉ vì dùng Stream thì các quy tắc về `null` tự thay đổi theo ý muốn. Chính sách rõ ràng nhất là áp dụng `filter`/`map`/validation tường minh theo hợp đồng ứng dụng.

## 10. Thiết kế API có chính sách `null` rõ ràng

Một thiết kế ghép chuỗi bền vững thường xác định trước ba câu hỏi:

**(A) Delimiter có bắt buộc không?** Nếu có, yêu cầu không `null`. Nếu không, quyết định giá trị mặc định rõ ràng, chẳng hạn `""` hoặc `", "`.

**(B) Tập phần tử có bắt buộc không?** Phân biệt *thiếu danh sách* (`null`), *có danh sách nhưng rỗng*, và *có phần tử rỗng* nếu nghiệp vụ cần sự khác nhau.

**(C) `null` ở từng phần tử có ý nghĩa gì?** Phải chọn: lỗi đầu vào, bỏ mục, giữ vị trí với chuỗi rỗng, placeholder, hay biểu diễn kiểu dữ liệu có thể khôi phục.

Ví dụ API **cấm `null` ở mọi cấp**, thích hợp cho trường cấu hình cần dữ liệu đầy đủ:

```java
static String strictJoin(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements) {
    java.util.Objects.requireNonNull(delimiter, "delimiter");
    java.util.Objects.requireNonNull(elements, "elements");

    java.util.StringJoiner joiner =
            new java.util.StringJoiner(delimiter);

    for (CharSequence element : elements) {
        joiner.add(java.util.Objects.requireNonNull(
                element, "element"));
    }
    return joiner.toString();
}
```

Đây là **phương thức hỗ trợ**, cần đặt bên trong một lớp Java. Phương thức khác với `String.join` mặc định: nó **báo lỗi** nếu có phần tử `null`, thay vì chuyển thành chữ `"null"`.

Một lựa chọn khác là **bỏ `null`**:

```java
static String skipNulls(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements) {
    java.util.Objects.requireNonNull(delimiter, "delimiter");
    java.util.Objects.requireNonNull(elements, "elements");

    java.util.StringJoiner joiner =
            new java.util.StringJoiner(delimiter);
    for (CharSequence element : elements) {
        if (element != null) {
            joiner.add(element);
        }
    }
    return joiner.toString();
}
```

Ví dụ đầu vào `["A", null, "B"]` tạo `"A,B"` khi delimiter là `","`. Nếu có các trường dữ liệu theo vị trí cố định, **cân nhắc hậu quả bỏ cột** trước khi chọn chính sách này.

## 11. Lưu ý khi xử lý dữ liệu ngoài ứng dụng

Các bài toán thường gặp:

| Tình huống | Chính sách nên cân nhắc | Vì sao? |
| --- | --- | --- |
| Tạo log chỉ để đọc | Placeholder cho `null` hoặc giữ mặc định `"null"`, nếu được chấp nhận | Dễ nhìn nhưng không bảo đảm khôi phục kiểu dữ liệu. |
| Ghép nhãn người dùng | Có thể lọc `null` hoặc thay bằng văn bản phù hợp | Tránh xuất chữ `"null"` khó hiểu cho người dùng. |
| Dữ liệu cột theo vị trí | Không âm thầm bỏ `null` | Bỏ một mục sẽ làm thay đổi vị trí các cột. |
| Cấu hình mà mọi phần bắt buộc | Fail fast khi thiếu delimiter/tập/phần tử | Phát hiện thiếu dữ liệu sớm. |
| Xuất CSV/JSON | Dùng bộ mã hóa định dạng phù hợp | Cần xử lý escape, ký tự phân cách, dấu nháy và `null` đúng kiểu. |
| Chuỗi cần phân tích ngược về danh sách | Dùng schema/encoding có thể khôi phục | `String.join` không giữ đủ thông tin để đảo ngược mọi trường hợp. |

Một chuỗi như `"A,null,B"` không cho biết phần tử giữa vốn là Java `null` hay chuỗi `"null"`. Tương tự, `"A,,B"` có thể chứa một phần tử rỗng, nhưng nếu delimiter nằm trong dữ liệu thật, việc phân tách bằng `split` cũng không tự bảo đảm dựng lại đúng danh sách ban đầu.

Nếu đầu ra được dùng để xây dựng SQL, câu lệnh shell, CSV hoặc đường dẫn, **đừng xem nối chuỗi là cơ chế escape hoặc bảo vệ injection**. Hãy dùng API có tham số hoặc bộ mã hóa chuyên dụng theo ngữ cảnh.

## 12. Bài tập tự kiểm tra

### Bài 1 — Ba loại `null`

```java
String.join(",", (CharSequence) null);
String.join(",", (CharSequence[]) null);
String.join(",", (Iterable<? extends CharSequence>) null);
```

**Đáp án:** Lời gọi thứ nhất tạo chuỗi `"null"`; lời gọi thứ hai và thứ ba ném `NullPointerException`. Ép kiểu thể hiện **một phần tử** khác **toàn bộ tập phần tử**.

### Bài 2 — Delimiter rỗng so với `null`

```java
System.out.println(String.join("", "A", "B"));
// String.join(null, "A", "B");
```

**Đáp án:** Dòng đầu in `AB`. Dòng bị chú thích nếu chạy sẽ ném `NullPointerException` vì delimiter `null` không hợp lệ.

### Bài 3 — `List.of` và `Arrays.asList`

```java
java.util.List<String> a =
        java.util.Arrays.asList("A", null, "B");
// java.util.List<String> b = java.util.List.of("A", null, "B");
```

**Đáp án:** `Arrays.asList` tạo danh sách chứa phần tử `null`; `List.of` không cho phép phần tử `null` và sẽ ném `NullPointerException` khi khởi tạo. Đây là hợp đồng của collection factory, không phải của `String.join`.

### Bài 4 — Bỏ phần tử hay giữ vị trí?

Đầu vào theo cột `["id-1", null, "ACTIVE"]`. Nếu bỏ `null` trước khi join bằng `";"`, đầu ra là gì, và rủi ro gì?

**Đáp án:** `"id-1;ACTIVE"`. Vị trí “cột thứ hai” biến mất, có thể khiến bên nhận gán nhầm `ACTIVE` vào cột khác. Nếu định dạng cần giữ số cột, hãy dùng schema và encoding có quy tắc rõ ràng; không tự bỏ mục.

### Bài 5 — Chuỗi `"null"` có phân biệt được Java `null` không?

```java
String a = String.join(",", "A", (CharSequence) null);
String b = String.join(",", "A", "null");
System.out.println(a.equals(b));
```

**Đáp án:** `true`. Kết quả văn bản giống nhau. `String.join` không bảo toàn kiểu nullable gốc.

### Bài 6 — Chọn chính sách cho UI

Một ứng dụng ghép tên hiển thị từ các mục do người dùng nhập. Nếu thiếu một mục, có nên mặc định hiển thị chữ `"null"` không?

**Đáp án:** Không nên tự động mặc định. Xác định yêu cầu giao diện: bỏ mục bị thiếu, dùng placeholder dễ hiểu hoặc báo lỗi. Nếu ứng dụng cần lưu và khôi phục dữ liệu gốc, lưu một cấu trúc có thông tin nullable thay vì dựa vào chuỗi join.

## 13. Tóm tắt

- `String.join` có hai overload chính: **varargs `CharSequence...`** và **`Iterable<? extends CharSequence>`**.
- **Delimiter `null` → `NullPointerException`.**
- **Cả mảng varargs hoặc đối tượng `Iterable` bằng `null` → `NullPointerException`.**
- **Một phần tử riêng lẻ bằng `null` → thêm chữ `"null"`**, không bỏ phần tử và không tự ném lỗi.
- **Tập rỗng → chuỗi rỗng**; phần tử rỗng vẫn tham gia ghép và có thể tạo hai delimiter liên tiếp.
- `StringJoiner.add(null)` cũng nối chữ `"null"`; `Collectors.joining` cho phép áp dụng chính sách `filter`/`map` tường minh trước khi ghép.
- Phân biệt `null` và chuỗi `"null"`, cũng như giá trị chứa delimiter, nếu cần khôi phục dữ liệu.
- Hãy định nghĩa chính sách `null` riêng cho **delimiter**, **tập phần tử**, và **từng phần tử** theo hợp đồng nghiệp vụ, thay vì chỉ dựa vào kết quả mặc định.

## Tài liệu tham khảo

- [Java SE 17 — `String.join(CharSequence, CharSequence...)` và `String.join(CharSequence, Iterable)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `StringJoiner`: constructor và `add(CharSequence)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [Java SE 17 — `Collectors.joining`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 17 — `List.of` và `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)
