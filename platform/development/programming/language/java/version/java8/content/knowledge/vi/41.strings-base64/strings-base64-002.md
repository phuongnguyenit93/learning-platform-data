# StringJoiner, prefix, suffix và dữ liệu rỗng trong Java

**Chủ đề:** Java 8 → Chuỗi và Base64 → StringJoiner, prefix, suffix và dữ liệu rỗng.

**StringJoiner** (`java.util.StringJoiner`) là API xuất hiện từ **Java 8** và vẫn được hỗ trợ trong Java hiện đại. Nó dùng để ghép một chuỗi các phần tử văn bản bằng **delimiter** (dấu phân tách), có thể thêm **prefix** ở đầu và **suffix** ở cuối kết quả. Điểm quan trọng nhất của bài này không chỉ là cách đặt dấu phẩy mà còn là **phân biệt joiner chưa có phần tử, joiner đã thêm một chuỗi rỗng, joiner đã thêm null và joiner có giá trị rỗng tùy chỉnh qua setEmptyValue()**.

Cách tư duy cơ bản:

~~~text
new StringJoiner(", ", "[", "]")
                 │    │    │
             delimiter prefix suffix

chưa add()          -> "[]"
add("A")            -> "[A]"
add("B") tiếp theo  -> "[A, B]"

setEmptyValue("(none)") trước add():
chưa add()          -> "(none)"
sau add("A")        -> "[A]"
~~~

**Lưu ý quan trọng:** `StringJoiner` **không tự thoát ký tự đặc biệt** trong CSV, JSON, SQL hoặc HTML. Nó chỉ ghép đúng các đoạn ký tự bạn cung cấp. Khi đầu vào là dữ liệu không tin cậy hoặc có delimiter trong chính phần tử, cần xử lý escaping/serialization theo đúng định dạng đích.

Bài sử dụng **Java 17+** cho các chương trình chạy độc lập để thuận tiện kiểm thử. Các API chính `StringJoiner`, `String.join(...)` và `Collectors.joining(...)` đều có từ Java 8. Khi ví dụ sử dụng `List.of(...)`, cần Java 9+; các method như `String.isBlank()` yêu cầu Java 11+. Nội dung chỉ sử dụng kiến thức vẫn còn áp dụng hiện nay, không mặc định dùng các công nghệ đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Tạo `StringJoiner` với một delimiter hoặc với đủ delimiter, prefix và suffix.
2. Phân biệt **prefix**, **suffix** và **delimiter** theo vị trí chèn.
3. Giải thích kết quả `toString()` khi **chưa thêm bất kỳ phần tử nào**.
4. Sử dụng `setEmptyValue()` khi muốn thay thế cách hiển thị **joiner rỗng thật sự**.
5. Phân biệt `add("")`, `add(" ")`, `add(null)` và **không gọi add**.
6. Hiểu vì sao `add("")` khiến joiner hết trạng thái rỗng dù kết quả có thể trông giống trước.
7. Dùng `length()` và hiểu nó đếm đơn vị **UTF-16**, không phải số lượng phần tử hay glyph hiển thị.
8. Dùng `merge(StringJoiner)` với joiner khác delimiter, prefix, suffix hoặc trạng thái rỗng.
9. Biết `StringJoiner` sao chép nội dung `CharSequence` được truyền vào.
10. Chọn giữa `StringJoiner`, `String.join` và `Collectors.joining`.
11. Xử lý null, chuỗi rỗng và danh sách rỗng theo yêu cầu nghiệp vụ, thay vì nhầm chúng với nhau.
12. Tránh sai sót về escaping, sự thay đổi của đối tượng mutable và sử dụng chung giữa nhiều thread.
13. Viết test xác định với các trường hợp biên quan trọng của StringJoiner.

## 2. Các thành phần cấu tạo

Một `StringJoiner` có ba tham số cấu hình thường gặp:

| Thành phần | Vị trí | Ví dụ |
|---|---|---|
| **delimiter** | Giữa hai phần tử đã thêm | `", "` |
| **prefix** | Một lần trước phần nội dung | `"["` |
| **suffix** | Một lần sau phần nội dung | `"]"` |

Ví dụ:

~~~java
StringJoiner joiner =
        new StringJoiner(" | ", "<", ">");

joiner.add("Java");
joiner.add("Kotlin");

System.out.println(joiner);
~~~

Kết quả:

~~~text
<Java | Kotlin>
~~~

`prefix` **không lặp trước từng phần tử**. `suffix` **không lặp sau từng phần tử**. Delimiter chỉ nằm **giữa các phần tử**, không tự thêm ở đầu hoặc cuối.

Đối với ba phần tử `A`, `B`, `C`:

~~~text
prefix + A + delimiter + B + delimiter + C + suffix
~~~

Với một phần tử thì **không có delimiter**; với hai phần tử thì có một delimiter; với ba phần tử thì có hai delimiter.

**Không nhầm delimiter với ký tự phân tách của regex.** `StringJoiner` chèn nguyên văn chuỗi delimiter, không coi dấu `|`, `.`, `*`, `?` là pattern.

## 3. Hai constructor của StringJoiner

Java cung cấp hai constructor:

~~~java
new StringJoiner(CharSequence delimiter)
new StringJoiner(
        CharSequence delimiter,
        CharSequence prefix,
        CharSequence suffix)
~~~

### 3.1. Chỉ có delimiter

~~~java
StringJoiner simple = new StringJoiner(", ");
simple.add("red").add("green").add("blue");

System.out.println(simple.toString());
~~~

Stdout:

~~~text
red, green, blue
~~~

Không có prefix hoặc suffix được cấu hình; mặc định tương đương **chuỗi rỗng** cho hai thành phần này.

### 3.2. Có delimiter, prefix, suffix

~~~java
StringJoiner wrapped =
        new StringJoiner(", ", "[", "]");

wrapped.add("red").add("green").add("blue");

System.out.println(wrapped);
~~~

Stdout:

~~~text
[red, green, blue]
~~~

**Thứ tự constructor là `delimiter, prefix, suffix`.** Đây là lỗi phổ biến khi người đọc nghĩ tham số đầu tiên là prefix như một số API format khác.

### 3.3. Tham số có thể là CharSequence

`CharSequence` có thể là `String`, `StringBuilder` hoặc implementation khác. `StringJoiner` sao chép biểu diễn ký tự của delimiter/prefix/suffix khi khởi tạo. Những thay đổi sau đó trên các `StringBuilder` đầu vào **không sửa cấu hình đã lưu trong joiner**.

### 3.4. Tham số constructor không được null

`delimiter`, `prefix`, `suffix` truyền vào constructor tương ứng phải khác null. Nếu không, constructor ném **NullPointerException**.

**Phân biệt:** `add(null)` lại có hành vi riêng — nó **không ném NullPointerException**, mà thêm chữ `"null"` theo hợp đồng API.

## 4. Demo cơ bản: prefix, suffix, delimiter và chaining

Lưu thành **StringJoinerBasicsDemo.java**:

~~~java
import java.util.StringJoiner;

public class StringJoinerBasicsDemo {
    public static void main(String[] args) {
        StringJoiner joiner =
                new StringJoiner(" | ", "[", "]");

        System.out.println("initial=" + joiner);
        System.out.println("initialLength=" + joiner.length());

        joiner.setEmptyValue("(none)");

        System.out.println("empty=" + joiner);
        System.out.println("emptyLength=" + joiner.length());

        joiner.add("Java").add("Kotlin");

        System.out.println("joined=" + joiner);
        System.out.println("joinedLength=" + joiner.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StringJoinerBasicsDemo.java
java StringJoinerBasicsDemo
~~~

**Stdout:**

~~~text
initial=[]
initialLength=2
empty=(none)
emptyLength=6
joined=[Java | Kotlin]
joinedLength=15
~~~

**Giải thích từng bước:**

1. Khi chưa gọi `add`, mặc định `toString()` trả `prefix + suffix`, ở đây là `"[]"`.
2. `length()` ban đầu là 2, bằng độ dài của `"[]"`.
3. `setEmptyValue("(none)")` thay thế **cách hiển thị khi chưa add**, không sửa prefix/suffix đã cấu hình.
4. Trước khi add, `toString()` và `length()` phản ánh `"(none)"`.
5. Sau khi thêm `Java` và `Kotlin`, `setEmptyValue` không còn được dùng để dựng chuỗi hiện tại.
6. Chuỗi `[Java | Kotlin]` có 15 đơn vị UTF-16: `[` (1), `Java` (4), ` | ` (3), `Kotlin` (6), `]` (1).
7. `add(...)` trả lại **chính joiner**, nên có thể nối lời gọi `.add("A").add("B")`.

Đây là chương trình đơn luồng, đầu ra không phụ thuộc lịch chạy thread hay dữ liệu bên ngoài.

## 5. Trạng thái rỗng của StringJoiner

**Rỗng theo định nghĩa của StringJoiner** không đồng nghĩa với **chuỗi kết quả không chứa ký tự**.

`StringJoiner` được coi là rỗng nếu:

- **Chưa gọi `add()`**.
- Và **chưa merge một StringJoiner có nội dung** vào nó.

Một joiner không có element có thể hiển thị `"[]"`, `"{}"`, `"(none)"` hoặc `""` tùy prefix/suffix và `setEmptyValue`. Nó vẫn là joiner rỗng theo trạng thái nội bộ.

### 5.1. Không có prefix/suffix

~~~java
new StringJoiner(",").toString()
~~~

Cho **chuỗi rỗng** `""` nếu chưa có phần tử.

### 5.2. Có prefix/suffix

~~~java
new StringJoiner(",", "{", "}").toString()
~~~

Cho `"{}"` nếu chưa có phần tử.

### 5.3. Có setEmptyValue

~~~java
new StringJoiner(",", "{", "}")
        .setEmptyValue("<empty>")
        .toString()
~~~

Cho `"<empty>"` nếu chưa có phần tử.

### 5.4. Một phần tử là chuỗi rỗng

~~~java
new StringJoiner(",", "{", "}")
        .setEmptyValue("<empty>")
        .add("")
        .toString()
~~~

Cho `"{}"`, **không phải** `"<empty>"`.

Điều này quan trọng: **Sau khi đã gọi `add("")`, joiner được coi là không còn rỗng**, ngay cả khi nội dung được thêm có độ dài 0.

### 5.5. Hai phần tử là chuỗi rỗng

~~~java
new StringJoiner(",", "{", "}")
        .add("")
        .add("")
        .toString()
~~~

Cho `"{,}"`. Delimiter xuất hiện **giữa hai phần tử** dù mỗi phần tử đều là chuỗi rỗng.

**Vì vậy không thể dùng `toString().isEmpty()` hoặc so sánh với `"{}"` để suy ra chắc chắn joiner đã được add hay chưa.** StringJoiner không cung cấp một method public `isEmpty()` cho trạng thái này; nếu nghiệp vụ cần số lượng phần tử, hãy theo dõi count riêng.

## 6. Bảng các trường hợp rỗng dễ nhầm

Giả sử bắt đầu bằng:

~~~java
StringJoiner j =
        new StringJoiner(",", "{", "}")
                .setEmptyValue("<empty>");
~~~

| Hành động | Chuỗi trả về | Joiner còn ở trạng thái rỗng? |
|---|---|---|
| Chưa add | `<empty>` | Có |
| `j.add("")` | `{}` | Không |
| Thêm `""` lần thứ hai | `{,}` | Không |
| Thêm `(CharSequence) null` | `{,,null}` | Không |
| `j.setEmptyValue("OTHER")` sau các add | Vẫn `{,,null}` | Không |
| Tạo joiner mới cùng cấu hình | `<empty>` | Có |

**Chuỗi rỗng `""`, chuỗi chứa một dấu cách `" "`, giá trị Java `null`, và việc không có phần tử là bốn tình huống khác nhau.** Đừng tự quy chúng về một dạng trước khi hiểu contract nghiệp vụ.

### 6.1. `add(" ")` khác `add("")`

`add(" ")` thêm một ký tự khoảng trắng. Với prefix `{}` sẽ hiển thị `{ }`, có độ dài 3. `add("")` hiển thị `{}` có độ dài 2, nhưng cả hai đều đánh dấu đã có phần tử.

### 6.2. `add(null)` khác `add("null")` về input, nhưng giống chuỗi kết quả

Theo API, `add(null)` thêm đúng các ký tự `"null"`. Khi đã ghép, không thể phân biệt một giá trị thực sự là chuỗi `"null"` với giá trị null đã được string hóa, nếu không giữ metadata ngoài joiner.

Nếu null có ý nghĩa “không có dữ liệu”, hãy chọn **chính sách null** trước khi add, ví dụ lọc bỏ hoặc chuyển thành marker rõ ràng.

## 7. Demo đầy đủ: không có element, chuỗi rỗng và null

Lưu thành **StringJoinerEmptyStateDemo.java**:

~~~java
import java.util.StringJoiner;

public class StringJoinerEmptyStateDemo {
    public static void main(String[] args) {
        StringJoiner j =
                new StringJoiner(",", "{", "}")
                        .setEmptyValue("<empty>");

        System.out.println("state0=" + j);

        j.add("");
        System.out.println("state1=" + j);

        j.add("");
        System.out.println("state2=" + j);

        j.add((CharSequence) null);
        System.out.println("state3=" + j);

        j.setEmptyValue("OTHER");
        System.out.println("afterSetEmptyValue=" + j);

        StringJoiner plain = new StringJoiner(",");
        System.out.println("plainLength=" + plain.length());

        plain.add("");
        System.out.println("plainAfterOneEmpty="
                + plain.toString().isEmpty());

        plain.add("");
        System.out.println("plainAfterTwoEmpty=" + plain);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StringJoinerEmptyStateDemo.java
java StringJoinerEmptyStateDemo
~~~

**Stdout:**

~~~text
state0=<empty>
state1={}
state2={,}
state3={,,null}
afterSetEmptyValue={,,null}
plainLength=0
plainAfterOneEmpty=true
plainAfterTwoEmpty=,
~~~

**Giải thích:**

- `state0` dùng `setEmptyValue` vì chưa có `add`.
- `state1` là kết quả của **một phần tử chuỗi rỗng**, nên không dùng emptyValue nữa.
- `state2` có hai phần tử, nên xuất hiện một dấu phẩy dù cả hai nội dung rỗng.
- `state3` có thêm chữ `"null"` theo hợp đồng `add(null)`.
- Gọi `setEmptyValue` sau khi đã add **không thay thế chuỗi hiện tại**.
- Với joiner không prefix/suffix, **trạng thái ban đầu** và **một element `""`** đều có thể tạo chuỗi `""`; nhưng sau khi add element thứ hai, delimiter xuất hiện.

**Lưu ý:** Ép kiểu `(CharSequence) null` không bắt buộc trong trường hợp này, nhưng giúp biểu đạt rõ overload `add(CharSequence)` và giá trị null được truyền vào.

## 8. setEmptyValue(): khi nào và vì sao?

Chữ ký:

~~~java
public StringJoiner setEmptyValue(CharSequence emptyValue)
~~~

**Ý nghĩa:** Cấu hình chuỗi thay thế khi **chưa có bất kỳ phần tử nào được thêm**, theo trạng thái rỗng của StringJoiner.

### 8.1. Dùng cho danh sách không có dữ liệu

Ví dụ ứng dụng muốn hiển thị:

- Có user: `[Lan, Mai]`.
- Không có user: `(không có người dùng)`.

Bạn có thể dùng:

~~~java
StringJoiner names =
        new StringJoiner(", ", "[", "]")
                .setEmptyValue("(không có người dùng)");
~~~

Chỉ gọi `names.add(name)` cho những mục thực sự được chấp nhận. Nếu list rỗng, kết quả là marker. Nếu có một name chuỗi rỗng, joiner **không còn rỗng**, do đó kết quả là `[]`, không phải marker.

### 8.2. Đặt emptyValue sau khi add?

Hợp đồng cho phép gọi `setEmptyValue(...)` ở nhiều thời điểm, nhưng **nó chỉ được sử dụng khi joiner đang rỗng**. Khi đã thêm phần tử, `setEmptyValue` không ảnh hưởng `toString()` hiện tại. StringJoiner không có method public reset/clear để quay lại trạng thái chưa add.

**Nếu muốn bắt đầu một nhóm dữ liệu mới, tạo StringJoiner mới.** Đừng dựa vào đổi emptyValue để xóa các phần tử trước đó.

### 8.3. emptyValue có thay prefix/suffix không?

**Có, nhưng chỉ cho output khi rỗng.** Khi chưa add, nó thay cho toàn chuỗi mặc định `prefix + suffix`; sau khi add, prefix và suffix cấu hình ban đầu vẫn dùng bình thường.

Ví dụ:

~~~text
prefix = "["
suffix = "]"
emptyValue = "EMPTY"

chưa add       => EMPTY
add("A")       => [A]
add("")        => []
~~~

**Không tự động cho output `"[EMPTY]"`**; `setEmptyValue` không chỉ chèn một element vào giữa prefix/suffix.

### 8.4. Null emptyValue

`setEmptyValue(null)` ném **NullPointerException**. Nếu muốn hiển thị bốn ký tự `"null"`, truyền literal `"null"` — nhưng nên cân nhắc marker rõ ràng hơn để tránh nhầm với dữ liệu hợp lệ.

## 9. null trong StringJoiner và String.join

`StringJoiner.add(CharSequence)` có hợp đồng đặc biệt: khi `newElement == null`, nó thêm **chuỗi `"null"`**.

Ví dụ:

~~~java
StringJoiner values = new StringJoiner(", ");
values.add("A").add(null).add("B");

System.out.println(values);
~~~

Kết quả:

~~~text
A, null, B
~~~

**`String.join` cũng có cách xử lý tương tự đối với phần tử null**: nó thêm `"null"`. Tuy nhiên, **delimiter** hoặc chính container varargs/Iterable được truyền vào `String.join` mà null sẽ dẫn tới lỗi `NullPointerException`, theo hợp đồng method.

### 9.1. Chính sách null trước khi ghép

Ba chính sách thường gặp:

1. **Giữ chỗ rõ ràng:** null → `"(missing)"`.
2. **Bỏ qua:** không add các phần tử null.
3. **Từ chối:** `Objects.requireNonNull(value)` hoặc validation nghiệp vụ.

**Đừng mặc định dùng `"null"` là một cách serialize dữ liệu an toàn**: nó không phân biệt được null Java và literal `"null"` trong dữ liệu.

### 9.2. Bỏ qua null khi stream có thể chứa null

~~~java
List<String> inputs =
        Arrays.asList("A", null, "B");

String result = inputs.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining(", "));

// result là "A, B".
~~~

Đây là đoạn minh họa cần import `List`, `Arrays`, `Objects`, `Collectors`.

**Quan trọng:** `List.of("A", null, "B")` ném `NullPointerException` ngay lúc tạo danh sách (Java 9+), nên khi cần fixture có null, dùng `Arrays.asList(...)` hoặc một collection phù hợp.

### 9.3. Chuỗi rỗng không phải null

`Objects::nonNull` **không lọc** `""`. Nếu nghiệp vụ muốn loại cả chuỗi rỗng, cần thêm predicate như `!s.isEmpty()`; nếu muốn loại khoảng trắng, có thể dùng `!s.isBlank()` trên Java 11+.

**Không tự trim/filter tất cả khoảng trắng nếu whitespace là dữ liệu có ý nghĩa**, ví dụ tên tệp, mã token hoặc một định dạng có khoảng trắng bắt buộc.

## 10. Demo đầy đủ: ba chính sách null

Lưu thành **StringJoinerNullPolicyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class StringJoinerNullPolicyDemo {
    public static void main(String[] args) {
        List<String> input =
                Arrays.asList("A", null, "", "B");

        StringJoiner literal =
                new StringJoiner("|", "[", "]");

        input.forEach(literal::add);

        System.out.println("literal=" + literal);

        String skipped = input.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.joining("|", "[", "]"));

        System.out.println("skipNull=" + skipped);

        String skipBlank = input.stream()
                .filter(Objects::nonNull)
                .filter(s -> !s.isBlank())
                .collect(Collectors.joining("|", "[", "]"));

        System.out.println("skipBlank=" + skipBlank);

        String withMarker = input.stream()
                .map(s -> s == null ? "(missing)" : s)
                .collect(Collectors.joining("|", "[", "]"));

        System.out.println("marker=" + withMarker);

        System.out.println("stringJoin="
                + String.join("|", input));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StringJoinerNullPolicyDemo.java
java StringJoinerNullPolicyDemo
~~~

**Stdout:**

~~~text
literal=[A|null||B]
skipNull=[A||B]
skipBlank=[A|B]
marker=[A|(missing)||B]
stringJoin=A|null||B
~~~

**Giải thích:**

- `literal`: giữ mọi element, null chuyển thành `"null"`, `""` tạo khoảng trống giữa hai delimiter.
- `skipNull`: bỏ null nhưng vẫn giữ phần tử chuỗi rỗng, tạo `||`.
- `skipBlank`: bỏ null và chuỗi blank (bao gồm `""`), chỉ còn `A|B`.
- `marker`: null được biểu diễn rõ.
- `String.join` không cho prefix/suffix, vẫn chuyển null element thành `"null"`.

**Nhận xét:** Không có lựa chọn nào đúng cho mọi ứng dụng. Định nghĩa null/empty policy ở tầng dữ liệu trước khi tạo chuỗi hiển thị.

## 11. merge(StringJoiner): ghép nội dung của một joiner khác

Chữ ký:

~~~java
public StringJoiner merge(StringJoiner other)
~~~

`merge(other)` đưa **nội dung** của `other` vào joiner hiện tại mà **không mang prefix/suffix của other** sang. Nếu `other` đang ở trạng thái rỗng theo định nghĩa của StringJoiner, merge **không thay đổi** joiner nhận.

Ví dụ:

~~~java
StringJoiner left =
        new StringJoiner(",", "[", "]");

StringJoiner right =
        new StringJoiner("|", "<", ">")
                .add("X").add("Y");

left.add("A").merge(right).add("B");

System.out.println(left);
System.out.println(right);
~~~

Kết quả:

~~~text
[A,X|Y,B]
<X|Y>
~~~

### 11.1. Khác delimiter có sao không?

**Có ảnh hưởng đến chuỗi bên trong phần được merge.** Theo hợp đồng `merge`, nếu delimiter của `other` khác, các phần tử của `other` được nối theo **delimiter của other**, và toàn bộ phần nội dung ấy được đưa vào joiner nhận như **một element**.

Vì thế `X|Y` xuất hiện nguyên vẹn trong một mục khi merge vào joiner dùng dấu `,`.

**merge không chuyển delimiter của từng mục trong other thành delimiter của receiver**. Nếu muốn tất cả phần tử có cùng delimiter, có thể lưu dữ liệu ở danh sách trước rồi tạo joiner mới có cấu hình thống nhất.

### 11.2. Prefix/suffix của source bị bỏ

Nếu `other` là `<X|Y>` nhưng kết quả receiver là `[A,X|Y,B]`, thì ký tự `<` và `>` của source không được chèn. Receiver vẫn dùng prefix `[` và suffix `]`.

### 11.3. Source có bị xóa sau merge không?

Không. `merge` không phải thao tác chuyển quyền sở hữu làm trống donor; donor vẫn giữ phần tử đã thêm. Trong ví dụ trên, `right.toString()` vẫn là `<X|Y>`.

### 11.4. merge với joiner rỗng

~~~java
StringJoiner receiver =
        new StringJoiner(",", "[", "]")
                .setEmptyValue("NONE");

StringJoiner empty =
        new StringJoiner("|", "<", ">")
                .setEmptyValue("DONOR-EMPTY");

receiver.merge(empty);

// receiver vẫn hiển thị "NONE".
~~~

`emptyValue` của donor **không được merge vào receiver**. Donor vẫn rỗng nên thao tác merge không thay đổi receiver.

### 11.5. merge với donor đã add chuỗi rỗng

~~~java
StringJoiner receiver =
        new StringJoiner(",", "[", "]")
                .setEmptyValue("NONE");

StringJoiner donor =
        new StringJoiner("|").add("");

receiver.merge(donor);

// receiver hiển thị "[]", không còn "NONE".
~~~

**Donor đã gọi `add("")`, nên không được coi là rỗng** dù nội dung ký tự của nó có độ dài 0. Merge donor này làm receiver không còn ở trạng thái rỗng. Đây là trường hợp biên rất dễ bỏ sót.

### 11.6. merge(null)

`merge(null)` ném **NullPointerException**. Nếu đầu vào có thể null, kiểm tra trước khi merge hoặc quy định một chính sách rõ ràng.

## 12. Demo đầy đủ: merge rỗng và khác delimiter

Lưu thành **StringJoinerMergeDemo.java**:

~~~java
import java.util.StringJoiner;

public class StringJoinerMergeDemo {
    public static void main(String[] args) {
        StringJoiner receiver =
                new StringJoiner(" / ", "[", "]")
                        .setEmptyValue("<none>");

        StringJoiner vacant =
                new StringJoiner("|", "{", "}")
                        .setEmptyValue("<other-empty>");

        receiver.merge(vacant);

        System.out.println("mergeVacant=" + receiver);

        StringJoiner donor =
                new StringJoiner("|", "<", ">")
                        .add("x").add("y");

        receiver.add("head").merge(donor).add("tail");

        System.out.println("mergeNonempty=" + receiver);
        System.out.println("donor=" + donor);

        StringJoiner emptySource =
                new StringJoiner(";").add("");

        StringJoiner target =
                new StringJoiner(",", "[", "]")
                        .setEmptyValue("NONE");

        target.merge(emptySource);

        System.out.println("mergeEmptyElement=" + target);
        System.out.println("mergeEmptyElementLength="
                + target.length());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StringJoinerMergeDemo.java
java StringJoinerMergeDemo
~~~

**Stdout:**

~~~text
mergeVacant=<none>
mergeNonempty=[head / x|y / tail]
donor=<x|y>
mergeEmptyElement=[]
mergeEmptyElementLength=2
~~~

**Giải thích:**

1. `vacant` chưa từng add nên `merge(vacant)` là no-op, bỏ qua cả giá trị `"<other-empty>"`.
2. Donor chứa `x|y` bên trong, còn receiver dùng dấu `" / "`.
3. Prefix/suffix `< >` của donor không xuất hiện trong receiver.
4. Donor vẫn giữ `<x|y>` sau khi merge.
5. `emptySource.add("")` khiến donor **không rỗng**. Merge nó khiến target từ trạng thái hiển thị `"NONE"` sang `"[]"`.
6. `length()` tính chiều dài của chuỗi thực tế `"[]"`, tức 2.

**Không suy từ chuỗi hiển thị `[]` rằng joiner chưa từng nhận dữ liệu.** Ở đây nó đã nhận một phần tử rỗng qua merge.

## 13. StringJoiner sao chép nội dung CharSequence

Các tham số constructor và `setEmptyValue` được sao chép thành biểu diễn ký tự. `add(CharSequence)` cũng thêm **bản sao nội dung** của phần tử tại thời điểm add, không giữ tham chiếu để sau này tự thay đổi theo `StringBuilder`.

Ví dụ:

~~~java
StringBuilder builder = new StringBuilder("A");

StringJoiner joiner = new StringJoiner(",");
joiner.add(builder);

builder.append("!");

System.out.println(joiner); // "A", không phải "A!".
~~~

### 13.1. Mutable delimiter/prefix/suffix

~~~java
StringBuilder delimiter = new StringBuilder("/");
StringBuilder prefix = new StringBuilder("<");
StringBuilder suffix = new StringBuilder(">");

StringJoiner joiner =
        new StringJoiner(delimiter, prefix, suffix);

delimiter.append("!");
prefix.append("!");
suffix.append("!");

joiner.add("A").add("B");

// joiner là "<A/B>", không phải "<!A/!B>!".
~~~

**Điều này không có nghĩa StringJoiner là immutable.** Joiner vẫn là đối tượng mutable: gọi `add`, `merge` hoặc `setEmptyValue` có thể thay đổi biểu diễn mà nó sẽ trả về. Chỉ có các **CharSequence đầu vào được sao chép**, tránh phụ thuộc vào sửa đổi sau đó của những đối tượng nguồn.

### 13.2. toString() không đóng băng joiner

~~~java
StringJoiner j = new StringJoiner(",", "[", "]");
j.add("A");

String snapshot = j.toString();

j.add("B");

// snapshot vẫn là "[A]"
// j.toString() là "[A,B]"
~~~

`toString()` trả một `String` bất biến tại thời điểm gọi. Joiner vẫn có thể được cập nhật và `toString()` tiếp theo trả kết quả khác.

## 14. Demo đầy đủ: bản sao CharSequence và trạng thái mutable

Lưu thành **StringJoinerCopyDemo.java**:

~~~java
import java.util.StringJoiner;

public class StringJoinerCopyDemo {
    public static void main(String[] args) {
        StringBuilder delimiter = new StringBuilder("/");
        StringBuilder prefix = new StringBuilder("<");
        StringBuilder suffix = new StringBuilder(">");

        StringJoiner joiner =
                new StringJoiner(delimiter, prefix, suffix);

        delimiter.append("!");
        prefix.append("!");
        suffix.append("!");

        StringBuilder element = new StringBuilder("A");

        joiner.add(element);
        element.append("!");

        joiner.add("B");

        System.out.println("copied=" + joiner);

        String firstString = joiner.toString();

        joiner.add("C");

        System.out.println("snapshot=" + firstString);
        System.out.println("current=" + joiner);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StringJoinerCopyDemo.java
java StringJoinerCopyDemo
~~~

**Stdout:**

~~~text
copied=<A/B>
snapshot=<A/B>
current=<A/B/C>
~~~

Đã thay đổi cả ba `StringBuilder` cấu hình và `StringBuilder` phần tử sau khi tạo/đăng ký. Joiner vẫn hiển thị các nội dung được sao chép tại thời điểm tương ứng. Nhưng joiner có thể tiếp tục `add("C")`, nên kết quả mới khác bản `String` đã lấy ra trước đó.

## 15. length() tính độ dài nào?

`StringJoiner.length()` trả `int` bằng độ dài biểu diễn chuỗi hiện tại, **tương đương `toString().length()`**.

Điều này bao gồm:

- `prefix` và `suffix` khi đã có element.
- Các delimiter được chèn giữa elements.
- Nội dung các elements.
- Hoặc `emptyValue` khi joiner chưa có element và đã cấu hình emptyValue.

**Không phải:** số phần tử được thêm, số từ, độ rộng hiển thị trên terminal, hoặc số ký tự Unicode theo cảm nhận người dùng.

### 15.1. Length khi rỗng

~~~java
StringJoiner j =
        new StringJoiner(",", "[", "]");

System.out.println(j.length()); // 2

j.setEmptyValue("EMPTY");

System.out.println(j.length()); // 5
~~~

### 15.2. Length khi add chuỗi rỗng

~~~java
StringJoiner j =
        new StringJoiner(",", "[", "]")
                .setEmptyValue("EMPTY");

j.add("");

System.out.println(j.length()); // 2
~~~

`EMPTY` không còn dùng sau khi add. Kết quả `"[]"` dài 2.

### 15.3. Length và Unicode supplementary characters

Java `String.length()` đo **UTF-16 code units**. Một Unicode supplementary character có thể chiếm hai `char` code units.

~~~java
StringJoiner j =
        new StringJoiner("/", "[", "]");
j.add("\uD83C\uDFAF");

String value = j.toString();

System.out.println("utf16=" + j.length());
System.out.println("codePoints="
        + value.codePointCount(0, value.length()));
~~~

Với chuỗi chứa dấu `[` + một emoji + dấu `]`, stdout:

~~~text
utf16=4
codePoints=3
~~~

**Cảnh báo:** Code points cũng không luôn đồng nghĩa số grapheme clusters mà mắt người thấy: emoji phức hợp có thể gồm nhiều code points. Nếu yêu cầu giới hạn độ rộng giao diện, cần phép đo phù hợp với sản phẩm hiển thị, không chỉ `StringJoiner.length()`.

### 15.4. Không dùng length() để đếm entries

Hai element rỗng với delimiter `","` có thể trả độ dài 1; một element `"A"` cũng có độ dài 1 khi không có wrapper. Từ `length()` không thể suy ra số lượng phần tử đã được add.

## 16. String.join, StringJoiner và Collectors.joining khác nhau thế nào?

Cả ba đều là API hiện hành và có từ Java 8, nhưng mức điều khiển khác nhau.

| Nhu cầu | `String.join` | `StringJoiner` | `Collectors.joining` |
|---|---|---|---|
| Ghép nhiều chuỗi bằng delimiter | Có | Có | Có |
| Prefix/suffix trực tiếp | Không | Có | Có, overload ba tham số |
| Custom emptyValue | Không | **Có** | Không có tham số emptyValue trong joining chuẩn |
| Thêm phần tử từng bước | Cần tập dữ liệu | **Có, add** | Qua Stream |
| Merge kết quả từ joiner khác | Không | **Có, merge** | Collector quản lý combiner |
| Trả kết quả trực tiếp | String | Mutable StringJoiner → toString | String |
| Dùng khi stream đã có sẵn | Có thể với Iterable | Có thể | **Rất phù hợp** |

### 16.1. String.join

~~~java
String result =
        String.join(", ", "A", "B", "C");

// "A, B, C"
~~~

Có overload nhận varargs `CharSequence...` và `Iterable<? extends CharSequence>`.

**String.join không có tham số prefix/suffix**. Muốn có wrapper, có thể dùng StringJoiner hoặc `Collectors.joining`.

### 16.2. StringJoiner

~~~java
StringJoiner result =
        new StringJoiner(", ", "[", "]")
                .add("A").add("B").add("C");

// result.toString() là "[A, B, C]".
~~~

Dùng khi **xây danh sách từng phần tử**, hoặc cần điều khiển đặc biệt cho rỗng qua `setEmptyValue`.

### 16.3. Collectors.joining

~~~java
String result = List.of("A", "B", "C")
        .stream()
        .collect(Collectors.joining(", ", "[", "]"));

// "[A, B, C]"
~~~

Đây là đoạn minh họa Java 17+, cần import `List` và `Collectors`.

Dùng khi dữ liệu đã nằm trong Stream pipeline và muốn một `String` kết quả. Với source có encounter order, collector ghép theo encounter order. Nếu source vốn unordered, không nên tự kỳ vọng thứ tự chuỗi ổn định mà không áp ordering rõ ràng.

### 16.4. Stream rỗng và prefix/suffix

~~~java
List.<String>of()
        .stream()
        .collect(Collectors.joining(", ", "[", "]"))
~~~

Cho `"[]"`. Standard `Collectors.joining` không có overload nhận `emptyValue`, nên nếu cần chuỗi rỗng đặc biệt, có thể xây một StringJoiner trực tiếp hoặc viết collector riêng đúng contract.

**Không viết `Collectors.joining(...).setEmptyValue(...)`**: kết quả của `Collectors.joining` là một `Collector`, không phải một `StringJoiner`.

## 17. Demo đầy đủ: String.join và Collectors.joining

Lưu thành **JoiningApisDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningApisDemo {
    public static void main(String[] args) {
        String direct =
                String.join("|", "A", "B", "C");

        System.out.println("stringJoin=" + direct);

        StringJoiner manual =
                new StringJoiner("|", "<", ">");

        manual.add("A").add("B").add("C");

        System.out.println("joiner=" + manual);

        String collected = List.of(
                "red", "green", "blue")
                .stream()
                .map(String::toUpperCase)
                .collect(Collectors.joining(
                        ", ", "<", ">"));

        System.out.println("collected=" + collected);

        String none = List.<String>of()
                .stream()
                .collect(Collectors.joining(
                        ",", "[", "]"));

        System.out.println("emptyCollected=" + none);

        String withEmptyElement = List.of("", "A")
                .stream()
                .collect(Collectors.joining(
                        ",", "[", "]"));

        System.out.println("emptyElement=" + withEmptyElement);

        String nullElement = String.join(
                "|", Arrays.asList("A", null, "B"));

        System.out.println("nullElement=" + nullElement);
    }
}
~~~

~~~bash
javac -encoding UTF-8 JoiningApisDemo.java
java JoiningApisDemo
~~~

**Stdout:**

~~~text
stringJoin=A|B|C
joiner=<A|B|C>
collected=<RED, GREEN, BLUE>
emptyCollected=[]
emptyElement=[,A]
nullElement=A|null|B
~~~

**Giải thích:**

- `String.join` ghép trực tiếp, không wrapper.
- StringJoiner thêm prefix/suffix `< >`.
- Stream map uppercase trước, sau đó collector joining.
- Stream không có element tạo `"[]"` khi có prefix/suffix.
- Stream có phần tử đầu tiên là `""` tạo `[,A]`, khác stream rỗng.
- Với null element, String.join dùng `"null"` như hợp đồng.

**Lưu ý biên dịch:** `List.of` có từ Java 9; chương trình chạy Java 17+. Với project chỉ dùng Java 8, thay bằng `Arrays.asList(...)` hoặc `Collections.emptyList()`.

## 18. Có nên dùng Collectors.joining với parallel stream?

`Collectors.joining` được thiết kế để làm collector trong Stream API, với combiner thích hợp cho các kết quả trung gian. Với **một nguồn có encounter order**, nó tạo kết quả theo thứ tự encounter của nguồn, kể cả khi pipeline được xử lý song song theo hợp đồng collector.

Ví dụ:

~~~java
List<String> parts =
        List.of("A", "B", "C", "D");

String result = parts.parallelStream()
        .collect(Collectors.joining(","));

// result là "A,B,C,D" với nguồn List có encounter order.
~~~

Điểm cần phân biệt:

- **Collector quản lý việc gộp các container trung gian** theo hợp đồng của nó.
- **Không có nghĩa bạn có thể tự chia sẻ một `StringJoiner` rồi gọi `add` từ nhiều threads không đồng bộ**.
- Nếu nguồn stream unordered hoặc có xử lý làm mất encounter order, không nên tuyên bố thứ tự kết quả không thay đổi.
- `parallel()` không mặc nhiên tăng tốc tác vụ nối chuỗi nhỏ; chi phí phân chia và gộp có thể cao hơn lợi ích.

**StringJoiner là đối tượng mutable; hãy xem nó như state dùng cục bộ cho một tác vụ hoặc được bảo vệ bằng đồng bộ nếu thực sự chia sẻ.**

## 19. Khi nào chọn StringJoiner thay StringBuilder?

**StringJoiner** tự quản lý delimiter giữa elements, prefix/suffix và emptyValue. Với một danh sách phần tử không quá phức tạp, nó giúp tránh logic:

~~~java
// Cách thủ công dễ có lỗi dấu phẩy đầu/cuối.
StringBuilder builder = new StringBuilder("[");

for (String value : values) {
    if (builder.length() > 1) {
        builder.append(",");
    }
    builder.append(value);
}

builder.append("]");
~~~

Đây là đoạn minh họa; `values` đã được khai báo.

Nếu prefix dài hơn 1, điều kiện `builder.length() > 1` là logic sai. Với StringJoiner, delimiter được xử lý dựa trên **số lần add**, không phải độ dài prefix.

**StringBuilder** vẫn là API hiện hành và rất phù hợp với logic format tùy biến phức tạp. Chọn nó khi cần chèn nhiều loại nội dung có điều kiện hoặc format không theo một delimiter thống nhất.

### 19.1. Không gọi toString lặp lại trong một vòng lớn

Một anti-pattern về hiệu năng:

~~~java
for (String item : items) {
    joiner.add(item);
    String partial = joiner.toString();
    // Thực hiện thao tác nặng với partial sau từng phần tử.
}
~~~

Nếu mỗi lần tạo String của toàn bộ nội dung hiện tại, tổng chi phí có thể tăng mạnh theo kích thước dữ liệu. Khi chỉ cần output cuối, add hết rồi gọi `toString()` một lần.

### 19.2. StringJoiner không stream dữ liệu ra tệp

Nó tích lũy ký tự trong bộ nhớ. Với dữ liệu khổng lồ, cân nhắc ghi theo từng phần vào `Writer`, response stream hoặc một API streaming thực sự, có escaping/encoding phù hợp. StringJoiner không cung cấp streaming output hay backpressure.

## 20. Ví dụ ứng dụng: hiển thị danh sách đẹp khi không có phần tử

Giả sử một trang cần:

- Danh sách nhân sự có phần tử: `[Lan; Mai; Nam]`.
- Không có phần tử: `(chưa có dữ liệu)`.
- Phần tử null: bỏ qua.
- Phần tử blank: bỏ qua **chỉ vì chính sách hiển thị ở ví dụ này**.

Lưu thành **FriendlyListDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.StringJoiner;

public class FriendlyListDemo {
    static String formatNames(List<String> names) {
        StringJoiner joiner =
                new StringJoiner("; ", "[", "]")
                        .setEmptyValue("(chưa có dữ liệu)");

        for (String name : names) {
            if (name != null && !name.isBlank()) {
                joiner.add(name);
            }
        }

        return joiner.toString();
    }

    public static void main(String[] args) {
        System.out.println("many="
                + formatNames(
                        List.of("Lan", "Mai", "Nam")));

        System.out.println("none="
                + formatNames(List.of()));

        System.out.println("filtered="
                + formatNames(Arrays.asList(
                        null, "", " ", "Lan")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FriendlyListDemo.java
java FriendlyListDemo
~~~

**Stdout:**

~~~text
many=[Lan; Mai; Nam]
none=(chưa có dữ liệu)
filtered=[Lan]
~~~

**Điều quan trọng:** Logic `name != null && !name.isBlank()` là một **quy tắc nghiệp vụ** được chọn trước khi add, không phải tính năng tự động của StringJoiner. Với dữ liệu có whitespace ý nghĩa, không nên lọc như vậy.

Nếu tất cả entries bị lọc bỏ, joiner vẫn chưa add và sử dụng `emptyValue`. Điều này giúp hiển thị một trạng thái rỗng rõ ràng cho người dùng.

## 21. Delimiter có trong dữ liệu: không có escaping tự động

Giả sử muốn CSV:

~~~text
name,comment
"Doe, Jane","hello"
~~~

Nếu viết:

~~~java
new StringJoiner(",")
        .add("Doe, Jane")
        .add("hello");
~~~

Kết quả là:

~~~text
Doe, Jane,hello
~~~

Chuỗi này **không bảo đảm là hai trường CSV hợp lệ**, vì bản thân trường đầu chứa dấu phẩy. StringJoiner chỉ chèn delimiter; nó không biết quy tắc CSV.

Tương tự:

- **JSON:** Không tự đặt dấu nháy hoặc escape backslash/quotes/control characters.
- **SQL:** Không tránh SQL injection; không dùng StringJoiner để tạo query từ dữ liệu không tin cậy. Dùng `PreparedStatement`/parameterized query.
- **HTML:** Không escape nội dung để chèn vào HTML an toàn.
- **URI:** Không tự URL-encode.
- **Tệp/Path:** Không thay thế `Path.resolve(...)` của NIO.

### 21.1. Ví dụ nhỏ về CSV quoting

Nếu buộc phải minh họa cách ghép các trường CSV đã được trích dẫn đúng, có thể dùng một hàm escape theo quy tắc double-quote cơ bản. Với dữ liệu ngoài thực tế, đặc biệt khi xuất cho spreadsheet, cần xét thêm **CSV formula injection** và đặc tả của công cụ đích.

Lưu thành **CsvJoinerDemo.java**:

~~~java
import java.util.Objects;
import java.util.StringJoiner;

public class CsvJoinerDemo {
    static String quoteCsv(String value) {
        Objects.requireNonNull(value);

        return "\""
                + value.replace("\"", "\"\"")
                + "\"";
    }

    public static void main(String[] args) {
        StringJoiner csv = new StringJoiner(",");

        csv.add(quoteCsv("Doe, Jane"))
                .add(quoteCsv("a\"b"))
                .add(quoteCsv("simple"));

        System.out.println(csv);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CsvJoinerDemo.java
java CsvJoinerDemo
~~~

**Stdout:**

~~~text
"Doe, Jane","a""b","simple"
~~~

**Giải thích:** QuoteCsv đặt dấu `"` quanh trường và nhân đôi dấu `"` bên trong theo quy tắc CSV double-quote cơ bản. StringJoiner chỉ đảm nhiệm nối các trường **đã escape** bằng dấu phẩy.

**Không coi helper ngắn này là thư viện CSV production đầy đủ**: cần chính sách cho null, newline, encoding, formula injection, nội dung không tin cậy và CSV dialect cụ thể. Với dữ liệu nghiêm túc, dùng thư viện CSV phù hợp, được duy trì và cấu hình đúng.

### 21.2. StringJoiner cũng không làm sạch dữ liệu

Nếu một element chứa prefix, suffix hoặc delimiter, các ký tự đó được giữ nguyên. Đó là hành vi đúng của một API nối chuỗi. Nếu yêu cầu định dạng phải phân tích cú pháp được, sử dụng escaping/serializer ở lớp tương ứng.

## 22. Các trường hợp null gây exception và không gây exception

| Lời gọi | Kết quả |
|---|---|
| `new StringJoiner(null)` | NullPointerException |
| `new StringJoiner(",", null, "]")` | NullPointerException |
| `new StringJoiner(",", "[", null)` | NullPointerException |
| `joiner.setEmptyValue(null)` | NullPointerException |
| `joiner.add(null)` | Thêm literal `"null"` |
| `joiner.merge(null)` | NullPointerException |
| `String.join(null, "A", "B")` | NullPointerException |
| `String.join(",", (CharSequence[]) null)` | NullPointerException |
| `String.join(",", "A", null)` | Thêm literal `"null"` |

**Không suy ra từ việc `add(null)` được phép rằng mọi API StringJoiner đều chấp nhận null.** Chỉ một số thao tác có semantics đặc biệt cho null element.

### 22.1. Unit test lỗi phải kiểm tra đúng method

Một test muốn chứng minh constructor null delimiter phải gọi constructor với tham số null, không gọi `add(null)`. Ngược lại, một test muốn chứng minh `add(null)` phải assert chuỗi chứa `"null"`, không assert NullPointerException.

## 23. Test các hợp đồng quan trọng bằng chương trình độc lập

Không cần thư viện ngoài để kiểm tra những kết quả xác định.

Lưu thành **StringJoinerContractTest.java**:

~~~java
import java.util.StringJoiner;

public class StringJoinerContractTest {
    static void check(String label, boolean valid) {
        if (!valid) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        StringJoiner a =
                new StringJoiner(",", "[", "]");

        check("default-empty",
                a.toString().equals("[]"));

        a.setEmptyValue("NONE");

        check("custom-empty",
                a.toString().equals("NONE"));

        check("custom-length",
                a.length() == 4);

        a.add("");

        check("added-empty-string",
                a.toString().equals("[]"));

        a.add("");

        check("two-empty-elements",
                a.toString().equals("[,]"));

        a.add(null);

        check("null-element",
                a.toString().equals("[,,null]"));

        StringJoiner donor =
                new StringJoiner("|", "<", ">")
                        .add("X").add("Y");

        StringJoiner receiver =
                new StringJoiner(",", "{", "}");

        receiver.merge(donor);

        check("merge-strips-donor-wrapper",
                receiver.toString().equals("{X|Y}"));

        check("merge-preserves-donor",
                donor.toString().equals("<X|Y>"));

        StringJoiner emptyDonor =
                new StringJoiner(";")
                        .setEmptyValue("EMPTY");

        receiver.merge(emptyDonor);

        check("merge-empty-no-op",
                receiver.toString().equals("{X|Y}"));

        check("length-equals-string-length",
                receiver.length()
                        == receiver.toString().length());

        check("string-join",
                String.join("|", "A", "B")
                        .equals("A|B"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StringJoinerContractTest.java
java StringJoinerContractTest
~~~

**Stdout:**

~~~text
PASS default-empty
PASS custom-empty
PASS custom-length
PASS added-empty-string
PASS two-empty-elements
PASS null-element
PASS merge-strips-donor-wrapper
PASS merge-preserves-donor
PASS merge-empty-no-op
PASS length-equals-string-length
PASS string-join
~~~

**Giải thích:** Các asserts kiểm tra sự khác nhau giữa empty state và empty element; custom emptyValue; null; merge; prefix/suffix và length. Không có các giả định về thread scheduling, locale hoặc filesystem.

**Mở rộng đề xuất:** Thêm test `merge` từ donor đã `add("")`; thêm test `setEmptyValue(null)` và `merge(null)` ném NullPointerException; thêm test copies của mutable CharSequence.

## 24. Những điều StringJoiner không tự làm

Không nên đánh đồng StringJoiner với một trình format hoặc parser đầy đủ.

- **Không sort:** thứ tự phần tử theo thứ tự gọi add (hoặc nội dung merge được nhận).
- **Không deduplicate:** thêm `"A"` hai lần vẫn có hai phần tử.
- **Không trim:** `" A "` giữ nguyên khoảng trắng.
- **Không skip null:** null chuyển thành `"null"`.
- **Không skip empty string:** `add("")` vẫn là thêm phần tử.
- **Không escape CSV/JSON/HTML/SQL.**
- **Không validate business IDs hoặc giá trị số.**
- **Không cung cấp public element count hoặc `isEmpty()`.**
- **Không cung cấp `remove`, `clear` hay `reset` cho các phần tử đã thêm.**
- **Không bảo đảm thread-safe cho shared concurrent mutation.**
- **Không xuất trực tiếp sang file/socket;** kết quả là String được xây trong bộ nhớ.
- **Không tự thêm ký tự xuống dòng** trừ khi delimiter/prefix/suffix/element chứa chúng.

Nếu muốn logic lọc, sắp xếp, format hoặc escaping, thực hiện **trước khi add** hoặc sử dụng một pipeline/serializer phù hợp.

## 25. Thiết kế format đầu ra: phân biệt “không dữ liệu” và “dữ liệu có giá trị rỗng”

Xem ba case:

~~~text
Case A: Không có record nào
Case B: Có một record, field name = ""
Case C: Có một record, field name = null
~~~

Nếu gọi:

~~~java
StringJoiner j =
        new StringJoiner(",", "[", "]")
                .setEmptyValue("NO_DATA");
~~~

thì:

| Input | Cách add | Output |
|---|---|---|
| A | Không gọi add | `NO_DATA` |
| B | `add("")` | `[]` |
| C | `add(null)` | `[null]` |

Một chuỗi hiển thị có thể **đánh mất sự khác biệt dữ liệu** nếu caller chỉ nhìn văn bản. Trong API domain, giữ **cấu trúc dữ liệu gốc** như `List`, `Optional` hoặc DTO nếu cần phân biệt đầy đủ. `StringJoiner` phù hợp với **presentation**, không phải giải pháp thay thế cho data model.

### 25.1. Vì sao không dùng chuỗi `"null"` để đánh dấu null nội bộ?

Dữ liệu hợp lệ có thể đúng là `"null"`, nên kết quả không thể phân biệt:

~~~java
joiner.add(null);
joiner.add("null");
~~~

Nếu cả hai đều chuyển thành cùng văn bản, phía nhận không còn biết cái nào là null Java. Muốn trao đổi dữ liệu, dùng serializer có type/escaping rõ ràng thay vì tự sáng tạo giao thức với StringJoiner.

## 26. Một vài nguyên tắc hiệu năng và bộ nhớ

StringJoiner hợp lý để xây các chuỗi ngắn/vừa trong một scope đơn luồng. Tuy nhiên:

1. **Mỗi phần tử đều được sao chép vào trạng thái nội bộ**, không tự giữ live CharSequence.
2. **toString() tạo biểu diễn String** của trạng thái hiện tại; gọi lặp trong vòng cập nhật lớn có thể làm nhiều công việc thừa.
3. **Tiếp tục add sau toString() vẫn hợp lệ**, vì joiner không bị đóng/finalize bởi toString.
4. **Không giữ toàn bộ dữ liệu không giới hạn** nếu output rất lớn và có thể gây áp lực bộ nhớ.
5. **Không tự chèn delimiter bằng tay khi dùng add**, vì StringJoiner đã tự làm.
6. **Không dùng `parallelStream().forEach(sharedJoiner::add)`** như một collector an toàn; dùng `Collectors.joining` hoặc cơ chế đồng bộ nếu thật sự cần.
7. **Không chọn StringJoiner để encode JSON/CSV** nếu định dạng đích có escaping phức tạp — serializer đúng thường đáng tin cậy hơn.
8. **Không xem length như byte length**; UTF-8 và UTF-16 có kích thước khác nhau.

Nếu cần đo hiệu năng giữa StringJoiner, StringBuilder và Collectors.joining, benchmark với workload thật bằng JMH. Không kết luận chỉ từ một vòng lặp rất ngắn vì JIT và allocation ảnh hưởng kết quả.

## 27. Sai lầm thường gặp

### Sai lầm 1 — Nhầm thứ tự constructor

**Sai:** nghĩ tham số đầu là prefix.

**Đúng:** `new StringJoiner(delimiter, prefix, suffix)`.

### Sai lầm 2 — Tưởng delimiter nằm ở cuối

`add("A").add("B")` với delimiter `","` cho `"A,B"`, không phải `"A,B,"`.

### Sai lầm 3 — Hiểu `setEmptyValue` là thêm một phần tử

Nó chỉ đổi chuỗi biểu diễn khi chưa có element; không làm joiner trở thành nonempty.

### Sai lầm 4 — Tưởng `add("")` không thay đổi trạng thái

Nó đánh dấu joiner đã có phần tử; custom emptyValue không còn áp dụng.

### Sai lầm 5 — Tưởng `add(null)` ném lỗi

`add(null)` chuyển thành `"null"`; nhưng constructor với null và `setEmptyValue(null)` lại ném NullPointerException.

### Sai lầm 6 — Dùng `length()` để đếm số element

Length là độ dài biểu diễn String theo UTF-16, có tính cả delimiter/prefix/suffix hoặc emptyValue.

### Sai lầm 7 — Tưởng `merge` giữ prefix/suffix của donor

Nó loại wrapper của donor và nhận nội dung.

### Sai lầm 8 — Tưởng donor rỗng có custom emptyValue sẽ được thêm vào

`merge(emptyDonor)` là no-op, không thêm emptyValue của donor.

### Sai lầm 9 — Tưởng donor có `add("")` vẫn rỗng

Nó đã có element theo trạng thái API. Merge nó có thể làm receiver mất trạng thái custom emptyValue dù chuỗi đóng góp không có ký tự.

### Sai lầm 10 — Tưởng hai joiner khác delimiter sẽ tự chuẩn hóa tất cả element

Nội dung donor dùng delimiter của chính donor được đưa vào receiver như một phần nội dung.

### Sai lầm 11 — Tưởng merge xóa donor

Donor vẫn giữ nội dung đã thêm.

### Sai lầm 12 — Tưởng `String.join` có prefix/suffix

Nó chỉ cung cấp delimiter; chọn StringJoiner hoặc Collectors.joining overload ba tham số nếu cần wrapper.

### Sai lầm 13 — Tưởng `Collectors.joining` có `setEmptyValue`

Collector không phải StringJoiner; overload chuẩn không cho custom emptyValue.

### Sai lầm 14 — Tưởng `String.join` tự bỏ phần tử null

Nó đưa ra `"null"`, cần tiền xử lý nếu muốn lọc.

### Sai lầm 15 — Dùng `List.of("A", null)` trong test

List.of không cho null, nên lỗi xảy ra trước khi gọi StringJoiner/String.join.

### Sai lầm 16 — Tưởng `StringJoiner` làm CSV/JSON escaping

Không; delimiter trong dữ liệu được giữ nguyên, cần escaping/serializer.

### Sai lầm 17 — Dùng StringJoiner để nối SQL query từ user input

Đừng đưa dữ liệu chưa parameterize vào SQL string; dùng PreparedStatement.

### Sai lầm 18 — Chia sẻ một joiner mutable và cập nhật từ nhiều threads không đồng bộ

Không có bảo đảm concurrent mutation an toàn. Dùng state cục bộ hoặc collector/framework phù hợp.

### Sai lầm 19 — Kết luận StringJoiner luôn nhanh hơn StringBuilder

Không được bảo đảm; hiệu năng phụ thuộc workload, complexity và allocation.

### Sai lầm 20 — Dùng `toString().isEmpty()` để suy ra chưa từng add

Một joiner có thể đã add("") mà chuỗi vẫn rỗng khi không có wrapper.

### Sai lầm 21 — Đếm ký tự hiển thị qua length()

Length là UTF-16 code units; một supplementary character có thể chiếm 2 units.

### Sai lầm 22 — Gọi `setEmptyValue` để reset joiner

Nó không xóa phần tử cũ. Muốn bắt đầu lại, tạo StringJoiner mới.

### Sai lầm 23 — Tự gọi `.add(",")` giữa các phần tử

Delimiter được chèn tự động; add một dấu phẩy chỉ thêm một element mang dấu phẩy, dẫn đến dấu thừa.

### Sai lầm 24 — Không quy định chính sách xử lý null/blank

Dữ liệu rỗng có thể có nghĩa khác nhau tùy domain. Chọn rule trước khi add, không âm thầm normalize.

## 28. Checklist sử dụng StringJoiner trong production

- [ ] Đã xác định delimiter/prefix/suffix và đúng thứ tự constructor.
- [ ] Khi không có element, output mong muốn là prefix+suffix hay custom emptyValue?
- [ ] Có phân biệt **không có phần tử** và **có một phần tử `""`** không?
- [ ] Đã định nghĩa null policy: hiển thị, bỏ, thay marker hay từ chối?
- [ ] Có cần bỏ whitespace-only hoặc giữ nguyên?
- [ ] Nếu merge, đã xác định delimiter của donor và hành vi với donor rỗng?
- [ ] Không trông chờ donor prefix/suffix xuất hiện sau merge.
- [ ] Không dùng length() như element count hoặc byte length.
- [ ] Không dựa vào cập nhật sau của StringBuilder nguồn để thay đổi joiner.
- [ ] Không chia sẻ một joiner mutable cho nhiều writers không đồng bộ.
- [ ] Nếu output là CSV/JSON/HTML/SQL, đã có encoder/serializer đúng định dạng?
- [ ] Nếu order quan trọng, đã xác định thứ tự add hoặc encounter order của stream?
- [ ] Không tự giả định collector trên unordered stream cho thứ tự cố định.
- [ ] Không materialize chuỗi quá lớn trong bộ nhớ nếu có giải pháp streaming.
- [ ] Test đầy đủ các case: zero element, one empty element, two empty elements, null element, different delimiters, empty merge, Unicode.
- [ ] Phân biệt Java 8 API gốc với tiện ích Java 9/11/16+ trong code.
- [ ] Khi hiển thị dữ liệu người dùng, không dùng StringJoiner thay escaping/security validation.

## 29. Bài tập thực hành

### Bài 1 — Prefix/suffix

Tạo `StringJoiner(" / ", "<", ">")`, add `A`, `B`, `C`. Dự đoán output và tổng `length()`.

### Bài 2 — Empty state

Tạo `StringJoiner(",", "[", "]").setEmptyValue("EMPTY")`. Gọi toString trước add, sau add(""), sau add("") lần thứ hai. Giải thích tại sao `"EMPTY"` biến mất từ lần add đầu tiên.

### Bài 3 — Null policy

Với `Arrays.asList("A", null, "", "B")`, hãy tạo hai kết quả: một giữ literal null và một bỏ cả null, blank. So sánh số delimiter.

### Bài 4 — Merge khác delimiter

Receiver dùng `,` và wrapper `[ ]`, donor dùng `|` và wrapper `< >`. Donor add `x`, `y`. Merge vào receiver đã add `A`. Dự đoán output của cả hai joiner sau merge.

### Bài 5 — Merge donor rỗng

Donor có `setEmptyValue("DONOR_EMPTY")` nhưng chưa add. Merge vào receiver có `setEmptyValue("NO_DATA")`. Receiver có thay đổi trạng thái không?

### Bài 6 — Merge donor có một empty element

Donor đã `add("")`, receiver chưa add và có custom emptyValue. Sau merge, receiver có còn hiển thị custom emptyValue không?

### Bài 7 — Count và length

Viết code thêm hai element rỗng với delimiter `","`. Tại sao length không bằng số elements? Muốn đếm elements chính xác, cần làm gì?

### Bài 8 — CharSequence mutable

Truyền StringBuilder làm delimiter và element, sau đó thay đổi StringBuilder. Chứng minh joiner vẫn chứa bản sao nội dung ban đầu.

### Bài 9 — So sánh ba API

Dùng `String.join`, `StringJoiner`, `Collectors.joining` để xuất `A|B|C`. Chọn cách phù hợp nếu dữ liệu sẵn trong Stream và cần `[A|B|C]`.

### Bài 10 — Không có dữ liệu trong UI

Viết hàm trả `(không có)` nếu list trống, và `[Lan; Mai]` nếu có dữ liệu. Nếu list chỉ chứa `" "` thì chính sách của bạn là gì?

### Bài 11 — Escaping CSV

Có input `Doe, Jane` và `a"b`. Tại sao `StringJoiner(",").add(...)` trực tiếp không đủ? Viết hàm CSV quoting phù hợp cho ví dụ cơ bản.

### Bài 12 — Unicode

Một element là Unicode supplementary character. Dự đoán sự khác nhau giữa `length()` và `codePointCount()` khi có prefix/suffix.

### Bài 13 — Tính thứ tự

Ghép stream từ `List.of("B","A","C")` bằng Collectors.joining. Nếu muốn alphabet, hãy thêm `.sorted()` trước collect. Điều gì xảy ra với unordered stream?

### Bài 14 — Thread safety

Giải thích vì sao không nên gọi `sharedJoiner.add` từ 20 threads cùng lúc. Đề xuất một collector hoặc một thiết kế sở hữu joiner theo từng task.

### Bài 15 — Reset

Sau khi add hai phần tử, bạn muốn dùng cùng cấu hình cho một danh sách mới. Có thể gọi `setEmptyValue` để xóa các phần tử cũ không? Cách đúng?

## 30. Câu hỏi ôn tập và đáp án

**1. Constructor ba tham số có thứ tự gì?** — `delimiter, prefix, suffix`.

**2. Khi chưa add, joiner có wrapper `[ ]` trả gì?** — `"[]"` nếu chưa setEmptyValue.

**3. Khi chưa add, joiner chỉ có delimiter trả gì?** — Chuỗi rỗng `""`.

**4. setEmptyValue làm gì?** — Đổi biểu diễn khi joiner đang rỗng theo trạng thái API.

**5. setEmptyValue có tự thêm một element không?** — Không.

**6. add("") có đánh dấu joiner không rỗng không?** — Có.

**7. add(null) thêm gì?** — Literal `"null"`.

**8. setEmptyValue(null) làm gì?** — Ném NullPointerException.

**9. merge(null) làm gì?** — Ném NullPointerException.

**10. merge donor rỗng có thêm emptyValue của donor không?** — Không, no-op.

**11. merge donor khác delimiter có giữ delimiter của donor trong nội dung không?** — Có.

**12. merge donor có giữ prefix/suffix của donor không?** — Không.

**13. merge có xóa donor không?** — Không.

**14. length đo gì?** — `toString().length()`, theo UTF-16 code units.

**15. length có cho số element đã add không?** — Không.

**16. CharSequence mutable thay đổi sau add có tự sửa joiner không?** — Không; nội dung đã được sao chép.

**17. toString có đóng băng joiner không?** — Không; joiner tiếp tục add được.

**18. String.join có wrapper prefix/suffix không?** — Không.

**19. Collectors.joining có thể nhận delimiter, prefix, suffix không?** — Có, overload ba tham số.

**20. Empty stream collect joining với prefix `[` suffix `]` cho gì?** — `"[]"`.

**21. Standard Collectors.joining có setEmptyValue trực tiếp không?** — Không.

**22. String.join trên null element xử lý thế nào?** — Thêm literal `"null"`.

**23. StringJoiner có tự escape CSV/JSON không?** — Không.

**24. Một joiner mutable có nên được nhiều thread add đồng thời không đồng bộ không?** — Không.

**25. Tại sao cần test empty element khác zero elements?** — Cả hai có thể hiển thị giống nhau nhưng khác trạng thái và ảnh hưởng delimiter/emptyValue.

**26. Delimiter có được xem như regex không?** — Không, chèn nguyên văn.

**27. Thứ tự add có được giữ trong kết quả không?** — Có đối với các lời gọi add tuần tự; Stream collector tuân theo encounter order khi nguồn có thứ tự.

**28. Nếu cần một chuỗi mới sau khi đã add, dùng setEmptyValue để reset được không?** — Không; tạo StringJoiner mới.

**29. StringBuilder nguồn biến đổi sau constructor có tự làm delimiter khác đi không?** — Không, StringJoiner sao chép các ký tự cấu hình.

**30. Null trong business domain có nên mặc định luôn thành text `"null"` không?** — Chỉ khi đó là chính sách mong muốn; thường cần lọc, marker hoặc validation rõ.

## 31. Tổng kết

**StringJoiner là lựa chọn hiện hành cho việc ghép nhiều đoạn ký tự theo delimiter, với prefix/suffix và cách xử lý đặc biệt cho trường hợp chưa có phần tử.** Tuy nhiên, các trường hợp **zero elements, empty string element, null element và custom emptyValue** có semantics khác nhau; không được gộp chung.

Những quy tắc cốt lõi:

- `new StringJoiner(delimiter, prefix, suffix)` — delimiter nằm **giữa**, wrapper nằm **ngoài**.
- Khi chưa add, mặc định `toString()` trả `prefix + suffix`, hoặc `""` nếu không có wrapper.
- `setEmptyValue(value)` thay cả biểu diễn khi **chưa có phần tử**, không chèn value thành element.
- `add("")` làm joiner **không còn rỗng**; `add(null)` thêm chữ `"null"`.
- `merge(other)` **bỏ prefix/suffix của other**, giữ nội dung bên trong; donor rỗng không ảnh hưởng receiver.
- Với donor khác delimiter, nội dung donor được nối theo delimiter riêng rồi đưa vào receiver.
- `length()` đo **UTF-16 character units của chuỗi biểu diễn**, không phải số phần tử hoặc độ rộng hiển thị.
- StringJoiner sao chép CharSequence khi nhận cấu hình và phần tử; `toString()` tạo String nhưng joiner vẫn mutable.
- Dùng `String.join` cho bài toán đơn giản không wrapper, `Collectors.joining` cho Stream pipeline, StringJoiner khi cần add tuần tự và custom emptyValue.
- Không dùng StringJoiner thay CSV/JSON/HTML/SQL escaping hay validation dữ liệu.
- Không chia sẻ joiner mutable giữa nhiều writers không có đồng bộ.
- Dùng unit tests cho empty/null/merge/copy/length; xác định null/blank policy trước khi tạo chuỗi.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — StringJoiner: constructors, add, merge, setEmptyValue, length và toString](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/StringJoiner.html)
- [Oracle Java SE 26 — String.join và Unicode String semantics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
- [Oracle Java SE 26 — Collectors.joining](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Stream và encounter order](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — CharSequence](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/CharSequence.html)
- [Oracle Java SE 26 — Objects và null validation](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html)
