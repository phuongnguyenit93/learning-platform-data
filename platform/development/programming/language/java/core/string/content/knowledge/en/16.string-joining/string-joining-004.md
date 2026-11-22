# `StringJoiner` với `delimiter`, `prefix` và `suffix` trong Java

Khi cần ghép nhiều giá trị thành một chuỗi, ta thường muốn đặt **dấu phân cách ở giữa các phần tử** và đôi khi thêm **tiền tố**/**hậu tố** bao quanh toàn bộ kết quả. Ví dụ, từ các phần tử `"Lan"`, `"Mai"` và `"An"`, đầu ra mong muốn có thể là `"[Lan, Mai, An]"`.

`java.util.StringJoiner` được thiết kế đúng cho trường hợp này. Thay vì tự theo dõi «đã thêm phần tử đầu tiên chưa?» để chèn dấu phẩy, ta khai báo quy tắc ghép một lần rồi lần lượt gọi `add(...)`. Đặc biệt, ba khái niệm **delimiter**, **prefix** và **suffix** có ba vai trò hoàn toàn khác nhau:

- **`delimiter` (dấu phân cách):** xuất hiện **giữa** các phần tử, không tự xuất hiện ở đầu hay cuối danh sách.
- **`prefix` (tiền tố):** đứng **trước toàn bộ** nội dung các phần tử.
- **`suffix` (hậu tố):** đứng **sau toàn bộ** nội dung các phần tử.

Một `StringJoiner` là đối tượng *mutable* dùng để tích lũy nội dung; kết quả từ `toString()` là một `String` để dùng hoặc lưu lại.

## 1. Khởi tạo `StringJoiner`

Hai constructor thường dùng:

```java
StringJoiner joiner = new StringJoiner(", ");
StringJoiner wrapped = new StringJoiner(", ", "[", "]");
```

Constructor đầy đủ có chữ ký:

```java
StringJoiner(CharSequence delimiter, CharSequence prefix, CharSequence suffix)
```

Constructor chỉ nhận delimiter tương đương việc dùng tiền tố và hậu tố là chuỗi rỗng. Các tham số cấu hình này **không được `null`**: truyền `null` cho delimiter, prefix hoặc suffix khiến constructor ném `NullPointerException`.

Ví dụ:

```text
new StringJoiner(", ")         -> "A, B, C"
new StringJoiner(", ", "[", "]") -> "[A, B, C]"
new StringJoiner(" | ", "{", "}") -> "{A | B | C}"
```

Đây là hình dung kết quả **sau khi** gọi `add("A")`, `add("B")` và `add("C")` lên từng joiner tương ứng.

Không phải `StringJoiner` tự biết danh sách phần tử. Nó chỉ biết cách nối các chuỗi được bạn truyền lần lượt qua `add(...)`.

### Ví dụ 1: cấu hình một lần, thêm nhiều phần tử

Tạo tệp `StringJoinerBasicsDemo.java`:

```java
import java.util.StringJoiner;

public class StringJoinerBasicsDemo {
    public static void main(String[] args) {
        StringJoiner joiner = new StringJoiner(" | ", "{", "}");

        System.out.println(joiner);

        joiner.add("alpha")
              .add("beta")
              .add("gamma");

        System.out.println(joiner);
        System.out.println(joiner.length());
        System.out.println(joiner.toString().equals("{alpha | beta | gamma}"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StringJoinerBasicsDemo.java
java StringJoinerBasicsDemo
```

Kết quả:

```text
{}
{alpha | beta | gamma}
22
true
```

Khi chưa thêm phần tử nào, `toString()` trả `prefix + suffix`, ở đây là `{}`. Sau ba lần `add`, delimiter `" | "` chỉ xuất hiện **giữa** các phần tử; dấu `{` và `}` chỉ xuất hiện mỗi thứ một lần bao quanh toàn bộ nội dung.

`length()` trả số UTF-16 code unit của **biểu diễn kết quả hiện tại**, tương đương `toString().length()`. Nó không trả về số phần tử đã gọi `add`.

## 2. Diễn biến trước và sau mỗi lần `add`

Với cấu hình:

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
```

Các bước được hiểu như sau:

| Thời điểm | Nội dung của `joiner.toString()` |
| --- | --- |
| Chưa gọi `add` | `[]` |
| Sau `add("A")` | `[A]` |
| Sau `add("B")` | `[A, B]` |
| Sau `add("C")` | `[A, B, C]` |

**Dấu phân cách không xuất hiện trước phần tử đầu tiên hay tự đứng sau phần tử cuối.** Đây chính là lợi ích so với cách viết nối chuỗi dễ thừa hoặc thiếu dấu:

```java
StringBuilder builder = new StringBuilder("[");
for (String name : names) {
    builder.append(name).append(", ");
}
builder.append("]");
```

Đoạn trên chỉ là minh họa và giả định biến `names` đã tồn tại. Nếu danh sách có phần tử, nó có thể tạo dư `", "` trước dấu `]`. `StringJoiner` tự giải quyết việc đặt delimiter **giữa** các phần tử; bạn không cần xóa delimiter cuối hoặc quản lý biến cờ «đã có phần tử».

Để hiểu đúng, hãy tưởng tượng `StringJoiner` lưu nội dung các phần tử theo thứ tự thêm, rồi tạo ra chuỗi với delimiter và phần bao ngoài khi được yêu cầu. **Không nên phụ thuộc vào cấu trúc bộ nhớ nội bộ của JDK**; những gì chương trình dựa vào là hợp đồng API và kết quả `toString()`.

## 3. Phân biệt bộ bao ngoài với nội dung từng phần tử

`prefix` và `suffix` bao **toàn bộ chuỗi**. Chúng không bọc lần lượt từng giá trị được thêm bằng `add`. Bốn cấu hình dưới đây đều nhận cùng hai phần tử `"A"` rồi `"B"`:

| Delimiter | Prefix | Suffix | Kết quả |
| --- | --- | --- | --- |
| `", "` | `""` | `""` | `A, B` |
| `" / "` | `"["` | `"]"` | `[A / B]` |
| `":"` | `"user="` | `";"` | `user=A:B;` |
| `""` | `"<"` | `">"` | `<AB>` |

Nếu yêu cầu là `[A], [B]`, phải tạo phần tử đã được bọc, chẳng hạn `joiner.add("[" + item + "]")` với delimiter `", "`. Dùng prefix/suffix `"["` và `"]"` sẽ tạo `[A, B]`, biểu diễn một nhóm duy nhất.

**Các wrapper là văn bản nguyên dạng.** `StringJoiner` không kiểm tra cặp dấu ngoặc đúng cú pháp, không phân tích delimiter, không escape dấu phẩy hoặc quote bên trong phần tử. Bạn có thể tạo nhãn văn bản thông thường bằng prefix, nhưng nếu cần xuất CSV, JSON, SQL hoặc URL hợp lệ hãy dùng API hoặc bộ mã hóa đúng định dạng.

## 4. Trạng thái chưa có phần tử

Khi chưa gọi `add`, một joiner với prefix/suffix trả về `prefix + suffix`. Ví dụ `new StringJoiner(", ", "[", "]")` trả `"[]"` khi gọi `toString()` trước lần `add` đầu tiên. Có thể dùng `setEmptyValue(...)` để thay **toàn bộ** biểu diễn khi chưa có phần tử; giá trị đó không bị bọc thêm bởi prefix/suffix.

```java
StringJoiner names = new StringJoiner(" / ", "<", ">");
System.out.println(names); // <>

names.setEmptyValue("(none)");
System.out.println(names); // (none)

names.add("");
System.out.println(names); // <>

names.add("Mai");
System.out.println(names); // < / Mai>
```

`add("")` vẫn ghi nhận **một phần tử**. Dù không có ký tự trong phần tử đầu, sau lần `add` đó kết quả không còn sử dụng emptyValue; khi thêm `"Mai"`, delimiter xuất hiện ở ranh giới hai phần tử. Cần phân biệt “chưa có phần tử” với “đã có một phần tử rỗng”, nhất là khi biểu diễn trường dữ liệu theo vị trí.

Bài `StringJoiner.add, merge và setEmptyValue` phân tích sâu những thay đổi trạng thái, cách `merge` xử lý nguồn rỗng hoặc đã có `add("")`, và sự khác biệt giữa `merge(other)` với `add(other.toString())`. Trong bài này, hãy tập trung vào **hình dạng đầu ra** do delimiter, prefix và suffix xác định.

## 5. Chương trình hoàn chỉnh: ghép nhãn hiển thị

Lưu thành `JoinerEnvelopeDemo.java` và chạy bằng JDK 17 trở lên:

```java
import java.util.List;
import java.util.StringJoiner;

public class JoinerEnvelopeDemo {
    public static void main(String[] args) {
        StringJoiner filters = new StringJoiner(" ; ", "Filters: [", "]");
        System.out.println(filters);

        filters.add("status=OPEN").add("level=HIGH");
        System.out.println(filters);

        StringJoiner names = new StringJoiner(" / ", "<", ">");
        names.setEmptyValue("(none)");
        System.out.println(names);
        names.add("").add("Mai");
        System.out.println(names);

        List<String> tags = List.of("java", "core");
        StringJoiner decoratedTags = new StringJoiner(", ");
        for (String tag : tags) {
            decoratedTags.add("[" + tag + "]");
        }
        System.out.println(decoratedTags);
    }
}
```

```bash
javac -encoding UTF-8 JoinerEnvelopeDemo.java
java JoinerEnvelopeDemo
```

Kết quả:

```text
Filters: []
Filters: [status=OPEN ; level=HIGH]
(none)
< / Mai>
[java], [core]
```

`Filters: []` là biểu diễn của **joiner chưa có phần tử** với prefix/suffix có sẵn. Sau hai lần `add`, delimiter `" ; "` xuất hiện đúng một lần ở giữa. Dòng `< / Mai>` cho thấy delimiter có thể nằm gần đầu chuỗi khi **phần tử đầu là chuỗi rỗng**; phần bao ngoài vẫn chỉ được chèn một lần. Dòng cuối bọc từng tag trong phần tử truyền cho `add`, không dùng wrapper của toàn bộ joiner.

## 6. Giới hạn và cách chọn công cụ

- Constructor yêu cầu delimiter, prefix và suffix **khác `null`**, nhưng `""` hợp lệ. Đối số `add(null)` được biểu diễn bằng chữ `"null"`; muốn bỏ null thì phải lọc trước.
- `StringJoiner.length()` trả số code unit UTF-16 trong văn bản hiển thị, gồm wrapper và delimiter (hoặc emptyValue khi chưa có phần tử); đây không phải số phần tử hay số byte UTF-8.
- `StringJoiner` có thể thay đổi sau `add`, nhưng một `String` đã được trả từ `toString()` không thay đổi khi joiner nhận phần tử mới.
- Khi có mảng/`Iterable` hoàn chỉnh và chỉ cần delimiter, `String.join` ngắn hơn. Khi dữ liệu đã ở `Stream` với `map`/`filter`, dùng `Collectors.joining(delimiter, prefix, suffix)` thường hợp lý. Chọn `StringJoiner` khi cần thêm từng phần và kiểm soát wrapper theo tiến trình.

## 7. Tự kiểm tra

**Bài 1.** Cho:

```java
StringJoiner j = new StringJoiner("|", "(", ")");
j.add("A").add("B").add("C");
```

Kết quả `j.toString()` là `"(A|B|C)"`. Ba phần tử tạo hai delimiter; prefix và suffix chỉ xuất hiện một lần.

**Bài 2.** Với `new StringJoiner(":", "user=", ";")`, trước `add` kết quả là `"user=;"`, sau `add("A").add("B")` là `"user=A:B;"`. Prefix/suffix là văn bản tùy chọn, không nhất thiết là cặp dấu ngoặc.

**Bài 3.** Một joiner `new StringJoiner("-", "[", "]")` được đặt `setEmptyValue("EMPTY")`, rồi lần lượt gọi `add("")` và `add("X")`. Ba lần in trước và sau các lệnh cho:

```text
EMPTY
[]
[-X]
```

`add("")` khiến joiner không còn ở trạng thái chưa có phần tử; `-` được chèn trước phần tử `"X"` tiếp theo.

## 8. Ghi nhớ

`delimiter` nằm **giữa các phần tử**; `prefix` và `suffix` nằm **ngoài toàn bộ kết quả**. Khi chưa có phần tử, kết quả mặc định là prefix + suffix, trừ khi có `setEmptyValue`. Một phần tử `""` vẫn được tính là đã thêm; việc lọc, escape và xác thực nội dung là trách nhiệm riêng của ứng dụng.

Tài liệu tham khảo: [Oracle Java SE 17 — StringJoiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html).
