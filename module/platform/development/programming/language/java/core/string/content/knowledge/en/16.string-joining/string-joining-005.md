# StringJoiner.add, merge và setEmptyValue trong Java

Khi cần ghép nhiều phần văn bản thành một chuỗi có dấu phân cách, Java cung cấp `java.util.StringJoiner`. Thay vì tự quản lý điều kiện “có phải phần tử cuối không?”, bạn cung cấp **delimiter** (dấu phân cách), và tùy chọn **prefix** (tiền tố) cùng **suffix** (hậu tố). Mỗi lần `add(...)`, joiner ghi nhận thêm một phần tử. `merge(...)` gộp nội dung của joiner khác, còn `setEmptyValue(...)` quy định cách biểu diễn joiner **chưa có phần tử**.

Ba phương thức có quan hệ chặt chẽ nhưng khác mục đích:

- `add(CharSequence)`: thêm **một phần tử**; có thể thêm chuỗi rỗng và giá trị `null` có quy tắc riêng.
- `merge(StringJoiner)`: thêm **nội dung bên trong** một joiner khác nếu joiner đó không rỗng, nhưng **không mang prefix/suffix của nguồn sang**.
- `setEmptyValue(CharSequence)`: đổi chuỗi hiển thị **chỉ khi chưa từng thêm phần tử**; không phải `clear()` và không xóa nội dung đã có.

Hiểu đúng thế nào là “rỗng” trong `StringJoiner` là điểm mấu chốt để không tạo ra dấu phân cách thừa, không nhập nhầm `"null"`, và không dùng sai `merge`.

## 1. Tạo một StringJoiner: delimiter, prefix, suffix

Lớp `StringJoiner` thuộc package `java.util`:

```java
import java.util.StringJoiner;

StringJoiner plain = new StringJoiner(", ");
StringJoiner decorated = new StringJoiner(", ", "[", "]");
```

Đây là đoạn mã minh họa để đặt trong một phương thức Java. Hai constructor thông dụng:

| Constructor | Ý nghĩa | Ví dụ kết quả sau khi thêm A, B |
|---|---|---|
| `new StringJoiner(delimiter)` | Chỉ có dấu phân cách, prefix/suffix rỗng | `A, B` |
| `new StringJoiner(delimiter, prefix, suffix)` | Dấu phân cách, tiền tố, hậu tố tùy chọn | `[A, B]` |

`delimiter` chỉ xuất hiện **giữa các phần tử**; không tự được thêm trước phần tử đầu tiên hoặc sau phần tử cuối cùng. `prefix` và `suffix` bao quanh **nội dung kết quả** khi joiner đã có phần tử. Nếu chưa thêm phần tử và chưa gọi `setEmptyValue`, `toString()` trả về `prefix + suffix` (với constructor một tham số, hai chuỗi này rỗng nên kết quả là `""`).

Ví dụ:

```text
new StringJoiner(", ")             chưa add gì → ""
new StringJoiner(", ", "[", "]")   chưa add gì → "[]"
new StringJoiner(" / ", "<", ">")  chưa add gì → "<>"
```

**Không nhầm prefix/suffix với phần tử.** Trong `new StringJoiner(",", "[", "]")`, các dấu ngoặc vuông chỉ là vỏ hiển thị của kết quả; chúng không được tính là hai phần tử của joiner. Đối số constructor `delimiter`, `prefix`, `suffix` đều phải khác `null`; truyền null dẫn đến `NullPointerException`.

### Ví dụ 1: ghép các phần và gọi chain

Lưu thành **`StringJoinerAddDemo.java`**:

```java
import java.util.StringJoiner;

public class StringJoinerAddDemo {
    public static void main(String[] args) {
        StringJoiner names = new StringJoiner(", ", "[", "]");

        System.out.println("initial: " + names);

        names.add("An").add("Binh").add("Chi");

        System.out.println("joined: " + names);
        System.out.println("length: " + names.length());
        System.out.println("content: " + names.toString());

        StringJoiner plain = new StringJoiner(" | ");
        plain.add("Java").add("Core");
        System.out.println("plain: " + plain);
    }
}
```

Biên dịch và chạy bằng JDK 17+ trong thư mục chứa tệp:

```bash
javac StringJoinerAddDemo.java
java StringJoinerAddDemo
```

**Stdout:**

```text
initial: []
joined: [An, Binh, Chi]
length: 15
content: [An, Binh, Chi]
plain: Java | Core
```

Đếm `length()`: `[` là 1, `An` là 2, `, ` là 2, `Binh` là 4, `, ` là 2, `Chi` là 3 và `]` là 1; tổng **15 code unit UTF-16**. `StringJoiner.length()` đo độ dài **chuỗi kết quả**, gồm prefix, các phần tử, delimiters và suffix, không phải số phần tử. API không có `size()` dành cho số phần tử.

`add(...)` trả về **chính joiner** để viết chuỗi lệnh fluent; nó không tạo một `StringJoiner` mới sau mỗi lần thêm.

## 2. `add(CharSequence)`: đúng một phần tử mỗi lần gọi

Chữ ký chính:

```java
public StringJoiner add(CharSequence newElement)
```

Ví dụ `joiner.add("red").add("green")` chứa hai phần tử. Khi tạo kết quả, joiner chèn đúng một delimiter giữa hai phần tử này. Một phần tử có thể là `String`, `StringBuilder` hoặc giá trị triển khai `CharSequence` khác. Với đầu vào có thể thay đổi, nên coi dữ liệu được **thêm theo nội dung tại thời điểm gọi**, không mong việc sửa đối tượng nguồn sau đó sẽ tự động cập nhật phần đã thêm.

### Chuỗi rỗng `""` vẫn là một phần tử

`joiner.add("")` **đánh dấu joiner đã có phần tử**, mặc dù ký tự hiển thị được thêm vào có độ dài 0. Nếu tiếp tục thêm phần tử khác, dấu phân cách xuất hiện ở giữa:

```java
StringJoiner j = new StringJoiner("|", "<", ">");
j.add("").add("A");
```

Kết quả `j.toString()` là `"<|A>"`, không phải `"<A>"`. Bởi vì phần tử thứ nhất là chuỗi rỗng, phần tử thứ hai là `"A"`, và delimiter `|` nằm giữa chúng.

Điều này dẫn đến khác biệt quan trọng:

- **Chưa gọi `add` lần nào:** joiner được coi là rỗng theo trạng thái nội bộ.
- **Đã gọi `add("")`:** joiner **không còn rỗng**, dù nếu không có prefix/suffix thì `toString()` vẫn có thể trông giống chuỗi rỗng.

Đừng dùng duy nhất `toString().isEmpty()` làm phép đo đáng tin cho “chưa có phần tử”; hai trạng thái không tương đương.

### Đối số null trở thành văn bản `"null"`

Theo hợp đồng `add(CharSequence)`, nếu `newElement == null` thì nó thêm bốn ký tự `n`, `u`, `l`, `l`. Nó **không** tự bỏ qua phần tử và cũng không tự ném `NullPointerException`.

**`StringJoinerEdgeDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerEdgeDemo {
    public static void main(String[] args) {
        StringJoiner first = new StringJoiner("|", "<", ">");
        System.out.println("empty: " + first);
        first.add("");
        System.out.println("after empty string: " + first);
        first.add("A");
        System.out.println("after A: " + first);

        StringJoiner second = new StringJoiner(",", "[", "]");
        second.add(null).add("");
        System.out.println("null and empty: " + second);
    }
}
```

```bash
javac StringJoinerEdgeDemo.java
java StringJoinerEdgeDemo
```

**Stdout:**

```text
empty: <>
after empty string: <>
after A: <|A>
null and empty: [null,]
```

Tình huống `add(null)` thường không phải điều mà nghiệp vụ mong muốn. Nếu muốn **bỏ qua phần tử null**, hãy lọc rõ ràng trước khi gọi:

```java
if (value != null) {
    joiner.add(value);
}
```

Nếu muốn thay null bằng nhãn khác, hãy chủ động dùng `Objects.toString(value, "(missing)")` hoặc quy tắc chuyển đổi thích hợp. Đừng dựa vào `StringJoiner` để suy đoán chính sách xử lý dữ liệu thiếu.

## 3. `setEmptyValue(...)`: trạng thái chưa có phần tử

Chữ ký:

```java
public StringJoiner setEmptyValue(CharSequence emptyValue)
```

Nếu chưa có phần tử, `setEmptyValue` thay chuỗi được trả về bởi `toString()` và giá trị được dùng cho `length()`. Đây là **toàn bộ giá trị hiển thị** cho trạng thái rỗng, **không tự bọc thêm prefix/suffix**.

Ví dụ một joiner có vỏ `[`, `]` mặc định hiển thị `[]`. Nếu gọi `setEmptyValue("(none)")`, chuỗi hiển thị thành `(none)`, **không phải** `[(none)]`.

Khi đã thêm một phần tử, `setEmptyValue` không còn ảnh hưởng đến kết quả hiển thị của joiner hiện tại. Kể cả phần tử đó là `""`, joiner vẫn được coi là đã có phần tử.

### Ví dụ 2: trước và sau khi thêm phần tử

**`StringJoinerEmptyValueDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerEmptyValueDemo {
    public static void main(String[] args) {
        StringJoiner tags = new StringJoiner(", ", "[", "]");

        System.out.println("default empty: " + tags);

        tags.setEmptyValue("(none)");
        System.out.println("custom empty: " + tags);
        System.out.println("empty length: " + tags.length());

        tags.add("");
        System.out.println("after add empty: " + tags);
        System.out.println("after add empty length: " + tags.length());

        tags.setEmptyValue("(changed)");
        System.out.println("after setting again: " + tags);

        tags.add("Java");
        System.out.println("after Java: " + tags);
    }
}
```

```bash
javac StringJoinerEmptyValueDemo.java
java StringJoinerEmptyValueDemo
```

**Stdout:**

```text
default empty: []
custom empty: (none)
empty length: 6
after add empty: []
after add empty length: 2
after setting again: []
after Java: [, Java]
```

Tại bước `add("")`, joiner chuyển từ “chưa có phần tử” sang “đã có một phần tử rỗng”. Kết quả `[]` trông giống trạng thái mặc định nhưng **không còn áp dụng emptyValue**, và độ dài của kết quả là 2. Sau khi thêm `"Java"`, delimiter `", "` nằm giữa hai phần tử, cho `"[, Java]"`.

`setEmptyValue(...)` trả về cùng joiner nên có thể chain với `add(...)`:

```java
String result = new StringJoiner(", ", "[", "]")
        .setEmptyValue("(none)")
        .add("A")
        .add("B")
        .toString(); // "[A, B]"
```

Đây là đoạn mã minh họa. Gọi `setEmptyValue(null)` là không hợp lệ và ném `NullPointerException`, khác với `add(null)`. Không có `StringJoiner.clear()` hay `reset()` để biến một joiner đã thêm phần tử quay lại trạng thái chưa thêm; hãy tạo joiner mới nếu cần một lần ghép mới.

### Khi nào đặt emptyValue?

- Danh sách bộ lọc chưa có điều kiện: `"(none)"` hoặc chuỗi rỗng theo chuẩn UI.
- Chuỗi hiển thị của tập phần tử: mặc định `"[]"` nếu có prefix/suffix là ngoặc vuông.
- Kết quả ghép dòng log không có phần tử: có thể dùng `"N/A"` nếu hợp đồng dữ liệu quy định rõ.

Điểm quyết định là **ý nghĩa của danh sách không có phần tử**. Không dùng `setEmptyValue` thay cho kiểm tra phần tử rỗng hoặc phần tử null.

## 4. `merge(StringJoiner)`: nội dung nguồn được ghép như một phần

Chữ ký:

```java
public StringJoiner merge(StringJoiner other)
```

`merge(other)` lấy **nội dung bên trong** joiner `other` để thêm vào joiner nhận lời gọi. Nó bỏ qua **prefix và suffix của nguồn**. Nếu `other` là joiner **chưa có phần tử**, lời gọi **không làm thay đổi nội dung** joiner nhận, dù `other.setEmptyValue(...)` có giá trị tùy chỉnh.

Nếu `other` đã có phần tử, phần văn bản ghép của các phần tử nguồn được thêm vào **như một phần tử tổng hợp duy nhất** của joiner đích. Vì vậy:

- Delimiter của **joiner nguồn** giữa những phần tử nguồn **được giữ nguyên trong nội dung nhập**.
- Delimiter của **joiner đích** được dùng để ngăn phần tổng hợp này với các phần đã có của đích.
- Prefix/suffix của **nguồn không được sao chép**.
- Prefix/suffix của **đích vẫn được dùng** khi dựng chuỗi kết quả.
- Lời gọi trả về **chính joiner đích**; có thể tiếp tục `add()` hoặc `merge()`.

Điểm dễ nhầm: `merge` **không** duyệt từng phần tử nguồn rồi thay mọi delimiter nguồn bằng delimiter đích. Với nguồn `"B+C"` và đích dùng `" | "`, nội dung nhập vẫn có dấu `+`.

### Ví dụ 3: merge với delimiter và vỏ khác nhau

**`StringJoinerMergeDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerMergeDemo {
    public static void main(String[] args) {
        StringJoiner target =
                new StringJoiner(" | ", "<", ">").add("A");

        StringJoiner source =
                new StringJoiner("+", "[", "]").add("B").add("C");

        System.out.println("target before: " + target);
        System.out.println("source before: " + source);

        target.merge(source);
        System.out.println("target merged: " + target);
        System.out.println("source visible: " + source);

        target.add("D");
        System.out.println("target after D: " + target);
    }
}
```

```bash
javac StringJoinerMergeDemo.java
java StringJoinerMergeDemo
```

**Stdout:**

```text
target before: <A>
source before: [B+C]
target merged: <A | B+C>
source visible: [B+C]
target after D: <A | B+C | D>
```

Giải thích: nguồn có hai phần tử, biểu diễn nội bộ không có vỏ là `"B+C"`. Khi merge, joiner đích thêm **một phần tử tổng hợp** `"B+C"` sau `"A"`, dùng delimiter đích `" | "`, còn prefix/suffix nguồn `[`, `]` không xuất hiện trong đích. Sau `add("D")`, đích có thêm một phần tử độc lập nên thêm tiếp delimiter đích.

**Không suy luận số phần tử từ kết quả hiển thị:** dấu `+` trong `"B+C"` lúc này là một phần của **một nội dung được merge** vào đích, không phải dấu phân cách do đích quản lý giữa hai phần tử tách biệt. `StringJoiner` không có API công khai trả danh sách phần tử để phân tích lại cấu trúc ban đầu.

### Merge không phải phép nối hai chuỗi bao gồm cả vỏ

Giả sử:

```java
StringJoiner a = new StringJoiner(",", "{", "}").add("X");
StringJoiner b = new StringJoiner(";", "[", "]").add("Y");
a.merge(b);
```

Kết quả của `a.toString()` là `"{X,Y}"`, không phải `"{X,[Y]}"`. Nếu thật sự muốn giữ toàn bộ kết quả trang trí của nguồn như một **phần tử văn bản**, dùng `a.add(b.toString())`. Hai thao tác này có ý nghĩa khác nhau:

- `a.merge(b)`: nhập **nội dung bên trong** joiner nguồn.
- `a.add(b.toString())`: thêm **chuỗi hiển thị đầy đủ**, bao gồm prefix/suffix nguồn, làm một phần tử mới.

Cả hai là đoạn mã minh họa; hãy chọn theo cấu trúc đầu ra muốn tạo.

## 5. Merge joiner chưa có phần tử và joiner đã add("")

Trường hợp biên này thường gây kết quả bất ngờ. Theo hợp đồng của `merge`, “other empty” nghĩa là **chưa có phần tử nào được add**, không phải “toString() hiển thị chuỗi rỗng”. EmptyValue tùy chỉnh chỉ có nhiệm vụ hiển thị và **không trở thành nội dung để merge**.

Ví dụ:

- Source chưa add gì, `source.setEmptyValue("SOURCE_EMPTY")`: `target.merge(source)` không làm thay đổi target.
- Source đã gọi `source.add("")`: source **không còn empty**, và merge sẽ thêm một phần tử có nội dung rỗng vào target.
- Nếu target đang chưa có phần tử nhưng có `setEmptyValue(...)`, merge một phần tử rỗng cũng khiến target **không còn dùng emptyValue**.

### Ví dụ 4: sự khác nhau xuất hiện khi thêm phần tử tiếp theo

**`StringJoinerMergeEmptyDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerMergeEmptyDemo {
    public static void main(String[] args) {
        StringJoiner target = new StringJoiner(",", "{", "}")
                .setEmptyValue("TARGET_EMPTY");

        StringJoiner source = new StringJoiner(";", "[", "]")
                .setEmptyValue("SOURCE_EMPTY");

        System.out.println("target initially: " + target);
        System.out.println("source initially: " + source);

        target.merge(source);
        System.out.println("merge untouched: " + target);

        source.add("");
        System.out.println("source with empty member: " + source);
        target.merge(source);
        System.out.println("merge empty member: " + target);

        target.add("X");
        System.out.println("after X: " + target);
    }
}
```

```bash
javac StringJoinerMergeEmptyDemo.java
java StringJoinerMergeEmptyDemo
```

**Stdout:**

```text
target initially: TARGET_EMPTY
source initially: SOURCE_EMPTY
merge untouched: TARGET_EMPTY
source with empty member: []
merge empty member: {}
after X: {,X}
```

Dòng cuối `"{,X}"` chứng minh target đã có **một phần tử rỗng được merge**, dù nhìn tại bước `"{}"` rất giống trạng thái chưa có phần tử. Đừng kiểm tra “đã có phần tử chưa?” bằng cách so `toString()` với prefix+suffix; cùng một văn bản hiển thị có thể tương ứng với hai trạng thái logic khác nhau.

## 6. Dùng `add` hay `merge`, và sự khác biệt về ý định

| Nhu cầu | Lựa chọn | Vì sao |
|---|---|---|
| Thêm một giá trị đơn lẻ `"A"` | `add("A")` | Ghi nhận đúng một phần tử |
| Thêm một phần tử có thể chứa dấu phân cách | `add(value)` | Không tách value thành nhiều phần |
| Nhập phần nội dung đã được ghép từ một joiner khác | `merge(other)` | Giữ delimiter bên trong source và bỏ vỏ source |
| Muốn lấy nguyên đầu ra nguồn gồm cả prefix/suffix | `add(other.toString())` | Xem toàn bộ chuỗi nguồn là một phần tử |
| Muốn chuyển từng phần tử riêng từ một tập dữ liệu | Lặp `add(value)` trên chính dữ liệu đầu vào | Không dựa vào văn bản ghép đã mất cấu trúc phần tử |
| Muốn biểu diễn danh sách chưa có phần tử | `setEmptyValue(text)` | Chỉ thay cách hiển thị trạng thái rỗng |
| Muốn bỏ qua phần tử null | Tự lọc trước `add` | `add(null)` mặc định thêm chuỗi `"null"` |
| Muốn thoát khỏi joiner cũ và bắt đầu từ đầu | Tạo `new StringJoiner(...)` | Không có phương thức `clear()` |

Một ví dụ có ích là gom nhiều nhóm giá trị. Nếu các nhóm dùng **cùng delimiter**, merge thường tạo đầu ra dễ đọc như cộng các danh sách. Nếu các nhóm dùng **delimiter khác nhau**, biểu diễn nguồn được giữ trong phần đã merge, nên phải cân nhắc dữ liệu đầu ra có còn đúng hợp đồng hay không.

## 7. Ví dụ tổng hợp: ghép nhiều nhóm dữ liệu

Giả sử một chương trình tạo dòng báo cáo gồm các nhóm từ khóa. Mỗi nhóm dùng delimiter `", "`, báo cáo tổng dùng delimiter `" / "`. Khi merge nhóm, văn bản ghép của từng nhóm trở thành một phần tử của báo cáo tổng.

**`StringJoinerReportDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerReportDemo {
    public static void main(String[] args) {
        StringJoiner basics = new StringJoiner(", ")
                .add("String")
                .add("StringBuilder");

        StringJoiner collections = new StringJoiner(", ")
                .add("List")
                .add("Map");

        StringJoiner result = new StringJoiner(" / ", "Topics: ", ".")
                .setEmptyValue("No topics");

        result.merge(basics);
        result.merge(collections);

        System.out.println("result: " + result);
        System.out.println("basics: " + basics);
        System.out.println("collections: " + collections);

        StringJoiner empty = new StringJoiner(", ")
                .setEmptyValue("Nothing here");

        StringJoiner otherReport = new StringJoiner(" / ", "Topics: ", ".")
                .setEmptyValue("No topics");
        otherReport.merge(empty);

        System.out.println("empty report: " + otherReport);
    }
}
```

```bash
javac StringJoinerReportDemo.java
java StringJoinerReportDemo
```

**Stdout:**

```text
result: Topics: String, StringBuilder / List, Map.
basics: String, StringBuilder
collections: List, Map
empty report: No topics
```

Dấu `, ` nằm **bên trong** mỗi nhóm và ` / ` ngăn **các nhóm** trong báo cáo. Prefix `"Topics: "` và suffix `"."` là của joiner `result`, không phải của hai joiner nguồn. `empty` có `setEmptyValue("Nothing here")` nhưng chưa có phần tử, nên merge không đưa `"Nothing here"` vào báo cáo và báo cáo vẫn dùng emptyValue riêng là `"No topics"`.

Ví dụ cho thấy `merge` có thể dùng để ghép những **đoạn đã nối**, nhưng không thay cho mô hình dữ liệu phân nhóm khi bạn còn cần truy vấn lại từng phần tử riêng lẻ.

## 8. Các trường hợp biên quan trọng khác

### 8.1. Delimiter, prefix, suffix và emptyValue có thể là chuỗi rỗng

`new StringJoiner("")` là hợp lệ: thêm `"A"` rồi `"B"` tạo `"AB"`, không có ký tự phân cách. `new StringJoiner(",", "", "")` cũng hợp lệ. `setEmptyValue("")` là hợp lệ và thường được dùng khi giao diện muốn không hiển thị gì với danh sách trống.

Điểm khác biệt là **chuỗi rỗng `""`** và **`null`**: constructor bắt buộc delimiter/prefix/suffix khác null; `setEmptyValue(null)` ném `NullPointerException`, trong khi `add(null)` thêm chữ `"null"`. `merge(null)` cũng không hợp lệ.

### 8.2. Phần tử có sẵn delimiter không được escape

Nếu delimiter là `", "` và phần tử là `"An, Binh"`, joiner coi `"An, Binh"` là **một phần tử**, không phân tách hay escape nội dung đó:

```java
StringJoiner j = new StringJoiner(", ", "[", "]");
j.add("An, Binh").add("Chi");
// toString(): "[An, Binh, Chi]"
```

Trong ví dụ, không thể suy ra từ đầu ra rằng joiner có **hai** hay **ba** phần tử. `StringJoiner` **không phải** thư viện tạo CSV chuẩn: nó không tự đặt dấu nháy kép, escape dấu phân cách, dấu nháy hoặc newline. Nếu cần dữ liệu có thể parse ngược không nhập nhằng, hãy có định dạng và bộ escape/parse tương ứng.

### 8.3. Prefix và suffix không nhất thiết là cặp dấu ngoặc

`new StringJoiner(":", "id=", ";")` có thể tạo `"id=A:B;"` sau khi thêm `"A"` và `"B"`. Joiner không kiểm tra ngữ nghĩa của các chuỗi trang trí; bạn tự quyết định xem định dạng có hợp lệ với giao thức hay không.

### 8.4. `toString()` là chuỗi bất biến tại thời điểm gọi

`StringJoiner` mutable. Sau `String snapshot = joiner.toString();`, việc tiếp tục `add(...)` sẽ thay đổi joiner, **không thay đổi** đối tượng `String` snapshot đã nhận. Vì thế nên lưu snapshot nếu muốn ghi log hoặc truyền sang API cần một giá trị cố định; tránh trông chờ `snapshot` cập nhật theo joiner.

### 8.5. `length()` là số code unit UTF-16, không phải số phần tử

`StringJoiner.length()` trả độ dài của chuỗi hiển thị trong trạng thái hiện tại. Nếu joiner còn rỗng và có emptyValue, nó dùng **độ dài emptyValue**. Khi đã có phần tử, nó tính theo prefix, nội dung, delimiters và suffix.

Ví dụ emoji 😊 là một Unicode code point ngoài BMP, dài **hai code unit UTF-16**:

**`StringJoinerUnicodeDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerUnicodeDemo {
    public static void main(String[] args) {
        String smile = "\uD83D\uDE0A";
        StringJoiner j = new StringJoiner("|", "(", ")")
                .add(smile)
                .add("A");

        String text = j.toString();
        System.out.println("units: " + j.length());
        System.out.println("code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("contains smile: " + text.contains(smile));
    }
}
```

```bash
javac StringJoinerUnicodeDemo.java
java StringJoinerUnicodeDemo
```

**Stdout:**

```text
units: 6
code points: 5
contains smile: true
```

`(`, `|`, `A`, `)` mỗi ký tự chiếm một code unit, emoji chiếm hai: tổng 6 code unit nhưng 5 code point. `StringJoiner` ghép dãy ký tự, **không tự đếm grapheme cluster** hay chuẩn hóa Unicode.

### 8.6. Chia sẻ joiner giữa nhiều luồng

`StringJoiner` là đối tượng có thể thay đổi, **không cung cấp bảo đảm đồng bộ hóa nội bộ** như một container thread-safe. Nếu nhiều luồng cùng `add`/`merge` trên **cùng instance**, phải quản lý chia sẻ và đồng bộ hóa hoặc cho mỗi luồng dùng joiner riêng rồi kết hợp kết quả theo cơ chế kiểm soát. `merge` cũng không biến nhiều thao tác nghiệp vụ thành một giao dịch đồng bộ.

## 9. Lựa chọn giữa StringJoiner, String.join, Collectors.joining và StringBuilder

Các công cụ này liên quan nhưng khác cấp độ điều khiển:

| Công cụ | Ví dụ | Phù hợp khi |
|---|---|---|
| `StringJoiner` | `new StringJoiner(", ", "[", "]").add("A").add("B")` | Muốn thêm dần, đặt prefix/suffix, merge các kết quả ghép và tùy chỉnh emptyValue |
| `String.join(...)` | `String.join(", ", "A", "B")` | Có sẵn các phần tử, muốn ghép nhanh bằng delimiter |
| `Collectors.joining(...)` | `stream.collect(Collectors.joining(", ", "[", "]"))` | Ghép các `CharSequence` trong pipeline Stream |
| `StringBuilder` | `builder.append(...)` | Cần tự kiểm soát toàn bộ trình tự dựng/chỉnh sửa chuỗi, không chỉ ghép phần tử bằng delimiter |

`String.join` không có API thêm dần `add` hoặc `merge` trên chính một đối tượng `StringJoiner` của bạn; `Collectors.joining` cung cấp kết quả cuối thông qua collector, đặc biệt phù hợp với Stream. Nếu cần một biểu diễn rỗng riêng, `StringJoiner.setEmptyValue` tiện lợi, còn với `String.join` hoặc collector có thể phải xử lý quy tắc rỗng ở tầng bao ngoài.

**Ví dụ `JoiningAlternativesDemo.java`:**

```java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class JoiningAlternativesDemo {
    public static void main(String[] args) {
        List<String> values = List.of("A", "B", "C");

        StringJoiner joiner = new StringJoiner(";", "<", ">");
        values.forEach(joiner::add);

        String direct = String.join(";", values);
        String collected = values.stream()
                .collect(Collectors.joining(";", "<", ">"));

        System.out.println("joiner: " + joiner);
        System.out.println("String.join: " + direct);
        System.out.println("collector: " + collected);
    }
}
```

```bash
javac JoiningAlternativesDemo.java
java JoiningAlternativesDemo
```

**Stdout:**

```text
joiner: <A;B;C>
String.join: A;B;C
collector: <A;B;C>
```

Chọn công cụ theo yêu cầu thực tế; không nhất thiết bọc một `StringJoiner` trong mọi thao tác nối hai ba phần tử. `StringBuilder` hữu ích nếu cần xen lẫn logic cấu trúc, escape, format và thao tác chỉnh sửa phức tạp hơn.

## 10. Hiệu năng và dữ liệu đầu vào

`StringJoiner` giúp tránh quản lý thủ công dấu phân cách, giảm lỗi logic khi danh sách có 0, 1 hay nhiều phần tử. Nhưng đừng coi nó là giải pháp tự động tối ưu mọi bài toán. Khi lượng dữ liệu rất lớn, hãy đo với workload đại diện; định dạng có thể cần serializer hay writer streaming thay vì gom tất cả thành một chuỗi trong bộ nhớ.

Các lưu ý:

1. **Đừng ghép thủ công bằng `String += item + delimiter` trong vòng lặp dài** khi có thể dùng `StringJoiner` hoặc một builder phù hợp. Ghép nối kiểu này dễ tạo logic xóa delimiter cuối hoặc phụ thuộc tối ưu hóa của JVM.
2. **Chọn chiến lược null rõ ràng** trước khi gọi `add`, đặc biệt khi dữ liệu đến từ CSDL, file, HTTP hoặc người dùng.
3. **Đừng dựa vào thứ tự từ một collection không có thứ tự xác định.** `StringJoiner` giữ thứ tự bạn gọi `add`; nó không tự sắp xếp nguồn.
4. **Nếu merge nhiều nhóm**, delimiter trong các nhóm được giữ nguyên. Cần thống nhất cấu trúc nếu đầu ra dùng trong giao thức máy đọc.
5. **Lưu ý độ dài UTF-16**: giới hạn kích thước byte của tệp hoặc mạng phải đo trên chuỗi đã mã hóa theo charset, không dùng `length()` làm số byte.
6. **Không dùng `setEmptyValue` làm cơ chế reset.** Nếu muốn tạo một bản ghi mới, khởi tạo joiner mới.
7. **Không ghép văn bản không đáng tin vào cú pháp đặc biệt mà không escape.** `StringJoiner` chỉ nối, không chống injection hay bảo đảm định dạng JSON/CSV/SQL hợp lệ.

## 11. Các lỗi thường gặp

| Hiểu nhầm | Hậu quả | Cách sửa |
|---|---|---|
| `add(null)` bỏ qua phần tử | Đầu ra chứa chữ `"null"` | Lọc null hoặc thay bằng nhãn theo hợp đồng |
| `add("")` tương đương chưa add | Delimiter xuất hiện khi thêm phần sau; emptyValue không còn hiệu lực | Phân biệt phần tử rỗng và danh sách rỗng |
| `setEmptyValue("(none)")` vẫn thêm prefix/suffix | Hiển thị khác dự kiến | EmptyValue là toàn bộ kết quả khi chưa add |
| `setEmptyValue` xóa hết phần đã thêm | Nội dung thực tế không đổi | Tạo joiner mới để reset |
| `merge` chép cả prefix/suffix nguồn | Có thể chèn hoặc bỏ vỏ không mong muốn | Dùng `merge` cho nội dung; `add(other.toString())` cho cả vỏ |
| `merge` thay delimiter nguồn bằng delimiter đích | Kết quả có các dấu phân cách khác nhau | Hiểu source body được thêm như một phần tổng hợp |
| Merge joiner rỗng nhưng có emptyValue sẽ ghép emptyValue | Đầu ra không có nhãn nguồn | EmptyValue không phải một phần tử |
| `length()` là số phần tử | Đếm sai, nhất là với prefix/emoji | `length()` là độ dài chuỗi kết quả theo UTF-16 |
| Dấu phân cách bên trong một phần tử tự được escape | CSV/log không parse lại chính xác | Tự escape hoặc dùng serializer thích hợp |
| Dùng `toString()` làm tham chiếu sống tới joiner | Snapshot không tự cập nhật | Gọi lại khi cần giá trị mới |
| Coi StringJoiner là thread-safe | Race khi cùng chỉnh sửa instance | Quản lý quyền sở hữu hoặc đồng bộ ngoài |
| Chuyển đầu vào null cho `setEmptyValue`/`merge` | Gặp `NullPointerException` | Xác thực các đối số cần khác null |

## 12. Tự kiểm tra kiến thức

Hãy đoán kết quả chương trình sau trước khi chạy:

**`StringJoinerSelfCheck.java`**

```java
import java.util.StringJoiner;

public class StringJoinerSelfCheck {
    public static void main(String[] args) {
        StringJoiner left = new StringJoiner("|", "[", "]")
                .setEmptyValue("EMPTY");

        StringJoiner right = new StringJoiner("-", "{", "}")
                .setEmptyValue("NO ITEMS");

        System.out.println(left);
        left.merge(right);
        System.out.println(left);

        right.add("A").add("B");
        left.merge(right);
        System.out.println(left);

        left.add("");
        System.out.println(left);

        left.setEmptyValue("CHANGED");
        System.out.println(left);

        System.out.println(right);
    }
}
```

```bash
javac StringJoinerSelfCheck.java
java StringJoinerSelfCheck
```

**Stdout:**

```text
EMPTY
EMPTY
[A-B]
[A-B|]
[A-B|]
{A-B}
```

Giải thích:

1. `left` chưa từng add nên `toString()` là `"EMPTY"`, bỏ qua vỏ `[` và `]` ở trạng thái rỗng tùy chỉnh.
2. `right` chưa add nên `left.merge(right)` không thêm gì; `left` vẫn rỗng.
3. Sau `right.add("A").add("B")`, nội dung của `right` bên trong vỏ là `"A-B"`. `left.merge(right)` nhập phần đó thành một phần tử, hiển thị `"[A-B]"`.
4. `left.add("")` thêm phần tử thứ hai rỗng, nên thêm delimiter đích `|` vào chuỗi kết quả: `"[A-B|]"`.
5. `setEmptyValue("CHANGED")` không tác động vì `left` đã có phần tử.
6. `right` vẫn hiển thị nội dung `"{A-B}"`; nó không mất các phần tử chỉ vì được merge vào `left`.

**Ghi nhớ:** `add` thêm một phần tử; `merge` nhập **nội dung của joiner khác** (không gồm vỏ nguồn), và `setEmptyValue` chỉ định **chuỗi hiển thị khi chưa có phần tử**. Đặt chính sách rõ cho null, chuỗi rỗng, delimiter trong dữ liệu và danh sách chưa có phần tử sẽ giúp việc ghép nhiều phần bằng `StringJoiner` đúng và dễ bảo trì.
