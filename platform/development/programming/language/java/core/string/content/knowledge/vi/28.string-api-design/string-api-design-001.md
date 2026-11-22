# Chọn `String` hay `CharSequence` cho tham số API Java

## 1. Nguyên tắc: chọn theo hợp đồng mà phương thức cần

Java có hai cách quen thuộc để mô tả tham số văn bản: `String` là một lớp cụ thể, nội dung **bất biến**; `CharSequence` là một **interface** mô tả dãy ký tự có thể đọc. `String implements CharSequence`, nên bất kỳ đối tượng `String` nào cũng có thể truyền cho tham số `CharSequence`.

**Nên dùng `CharSequence`** khi phương thức chỉ cần duyệt, đếm hoặc phân tích các ký tự và có thể làm đúng với nhiều loại nguồn như `String`, `StringBuilder`, `StringBuffer`, `CharBuffer`. **Nên dùng `String`** khi phương thức thật sự cần một giá trị bất biến, API bên trong yêu cầu `String`, cần lưu trạng thái lâu dài hoặc dùng nhiều thao tác riêng của lớp `String`.

Ví dụ ý định hai API:

```java
// Chỉ đọc ký tự ngay trong lời gọi:
int countAsciiDigits(CharSequence text);

// Lưu lại nhãn ở dạng giá trị bất biến:
void setPermanentLabel(String label);
```

Đây là các chữ ký minh họa, không phải chương trình độc lập. Quyết định nằm ở **ngữ nghĩa sử dụng**, không đơn thuần là chọn kiểu tổng quát nhất. `CharSequence` không hứa bất biến, không tự mang lại an toàn đa luồng và cũng không mặc nhiên tránh việc sao chép dữ liệu.

## 2. So sánh đặc điểm quan trọng

| Tiêu chí | `String` | `CharSequence` |
| --- | --- | --- |
| Loại | Lớp `final` cụ thể. | Interface cho dãy ký tự. |
| Dữ liệu đầu vào | Giá trị `String` (hoặc `null` nếu API cho phép). | `String`, `StringBuilder`, `StringBuffer`, `CharBuffer`, triển khai riêng. |
| Bất biến | Nội dung đối tượng `String` không thay đổi. | **Không bảo đảm**: đối tượng thực tế có thể mutable. |
| Thao tác chung | `length()`, `charAt()`, `subSequence()`, `toString()`. | Các thao tác trên cùng, cùng `chars()`, `codePoints()` trong Java hiện đại. |
| Thao tác riêng của `String` | `strip()`, `startsWith()`, `substring()`, `replace()`, `split()`, ... | Không có trong hợp đồng của interface. |
| So sánh giá trị | `String.equals`/`hashCode` nhất quán theo nội dung với `String`. | Interface không áp đặt mọi triển khai `equals`/`hashCode` phải theo nội dung. |
| Lưu giá trị về sau | Phù hợp nhờ tính bất biến. | Phải xem xét biến đổi của nguồn, thường chụp `String` trước khi lưu. |
| Chi phí | Đã là `String`; không cần ép kiểu trước khi gọi API cần `String`. | Có thể đọc trực tiếp nhiều nguồn, nhưng đôi khi cần `toString()` và cấp phát. |

**Lưu ý:** Biến có kiểu `String` vẫn có thể được gán tham chiếu tới một `String` khác; chính **nội dung của từng đối tượng `String`** mới bất biến. Ngoài ra, tham số kiểu `CharSequence` không làm cho nguồn `StringBuilder` trở thành chỉ đọc đối với các phần mã khác vẫn giữ tham chiếu tới nó.

## 3. Ví dụ Java 17+ hoàn chỉnh

Tạo file `CharSequenceApiDemo.java`:

```java
import java.nio.CharBuffer;
import java.util.Locale;
import java.util.Objects;

public class CharSequenceApiDemo {
    // Phương thức chỉ cần đọc dãy ký tự theo interface.
    static int countAsciiDigits(CharSequence text) {
        Objects.requireNonNull(text, "text");
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch >= '0' && ch <= '9') {
                count++;
            }
        }
        return count;
    }

    // Chuyển sang String khi cần một giá trị ổn định để xử lý.
    static String normalizedCode(CharSequence text) {
        String stable = Objects.requireNonNull(text, "text").toString();
        return stable.strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String fixed = "A7B";
        StringBuilder builder = new StringBuilder("x2");
        CharBuffer buffer = CharBuffer.wrap("p45");

        System.out.println("String: " + countAsciiDigits(fixed));
        System.out.println("StringBuilder: " + countAsciiDigits(builder));
        System.out.println("CharBuffer: " + countAsciiDigits(buffer));

        String captured = normalizedCode(builder);
        builder.append("9");
        System.out.println("Captured: " + captured);
        System.out.println("Current: " + normalizedCode(builder));

        System.out.println("Content equals: "
                + "key".contentEquals(new StringBuilder("key")));
        System.out.println("Object equals: "
                + Objects.equals("key", new StringBuilder("key")));
    }
}
```

Biên dịch và chạy:

```bash
javac CharSequenceApiDemo.java
java CharSequenceApiDemo
```

Đầu ra:

```text
String: 1
StringBuilder: 1
CharBuffer: 2
Captured: X2
Current: X29
Content equals: true
Object equals: false
```

`countAsciiDigits` nhận ba kiểu văn bản và chỉ đọc `length()`, `charAt()`. `normalizedCode` chụp dữ liệu thành `String` trước khi gọi `strip()` và `toUpperCase(Locale.ROOT)`; chuỗi `captured` giữ nguyên `"X2"` dù bên gọi sửa `StringBuilder` thành `"x29"` sau đó. Đây là minh họa khác biệt giữa **nhận tham số rộng** và **giữ giá trị bất biến**.

## 4. Trường hợp `CharSequence` thích hợp hơn

Một phương thức **xử lý đồng bộ ngay trong lời gọi**, chỉ dùng `length()`, `charAt()` và `subSequence()` để đọc, thường có thể nhận `CharSequence`. API linh hoạt hơn cho người gọi đang giữ dữ liệu trong `StringBuilder` hoặc `CharBuffer`.

Chẳng hạn:

```java
static boolean containsAtSign(CharSequence input) {
    Objects.requireNonNull(input, "input");
    for (int i = 0; i < input.length(); i++) {
        if (input.charAt(i) == '@') {
            return true;
        }
    }
    return false;
}
```

Đây là một hàm **minh họa**, không phải file chạy độc lập, và kiểm tra dấu `@` không đồng nghĩa xác thực email. Kiểu `CharSequence` nói đúng điều thuật toán cần: đọc từng đơn vị ký tự.

Các API có sẵn của Java cũng thể hiện cách thiết kế này: `Pattern.matcher(CharSequence)` chấp nhận nguồn đầu vào trừu tượng để khớp regex; `Appendable.append(CharSequence)` chấp nhận dữ liệu văn bản tổng quát. Không nhất thiết mọi thao tác văn bản đều phải yêu cầu `String`.

**Giới hạn cần nói rõ:** Nếu `StringBuilder` bị một luồng khác sửa đồng thời lúc hàm gọi `length()` hoặc `charAt()`, kết quả có thể không nhất quán; thậm chí có thể gặp lỗi chỉ số nếu độ dài đổi. Interface này **không cung cấp** cơ chế đồng bộ. Hợp đồng của API cần yêu cầu caller không sửa trong khi đọc, đồng bộ phù hợp, hoặc snapshot thành `String`.

Việc nhận `CharSequence` cũng không tự động làm code hiệu quả hơn. Một `CharBuffer` có `position`/`limit` thay đổi vùng quan sát, các triển khai có chi phí đọc khác nhau, và thuật toán phụ thuộc `String` có thể phải gọi `toString()` về sau.

## 5. Trường hợp `String` thích hợp hơn

Nên chọn `String` nếu:

- **Lưu lâu dài:** lưu trường thành viên, cache, hàng đợi, job bất đồng bộ hoặc kết quả mà caller có thể giữ sau khi lời gọi kết thúc.
- **Giá trị phải ổn định:** validation, hashing và xử lý nghiệp vụ về sau phải dựa trên cùng nội dung đã nhận.
- **Dùng phương thức riêng `String`:** `strip()`, `replace()`, `split()`, `startsWith()` hoặc chuyển tiếp đến thư viện yêu cầu `String`.
- **So sánh hoặc lưu khóa theo nội dung:** `String.equals`, `hashCode` và tính bất biến của `String` giúp giá trị khóa có hành vi ổn định.
- **Hợp đồng public có chủ đích hẹp:** API chỉ hỗ trợ một giá trị text đã chuẩn hóa thành `String`, hoặc cần giữ tương thích phiên bản cũ.

Thậm chí có thể nhận `CharSequence` ở ranh giới công khai rồi chụp thành `String` ngay khi cần lưu:

```java
import java.util.Objects;

final class Label {
    private final String value;

    Label(CharSequence input) {
        this.value = Objects.requireNonNull(input, "input").toString();
    }

    String value() {
        return value;
    }
}
```

Đây là **đoạn minh họa một lớp**, không phải chương trình `main` độc lập. Sau khi constructor nhận `StringBuilder`, đối tượng `Label` giữ một giá trị `String` ổn định, không thay đổi theo `StringBuilder` nguồn. Nếu chỉ muốn cho phép `String` ngay từ đầu, khai báo tham số `String` cũng là thiết kế hợp lệ.

Nếu vừa **kiểm tra dữ liệu rồi lưu**, nên chụp `String` trước, kiểm tra trên **chính bản đã chụp** và lưu đúng bản đó. Cách kiểm tra trực tiếp một `CharSequence` mutable rồi về sau chụp/lưu có thể khiến giá trị đã kiểm tra khác giá trị được dùng.

## 6. Quy tắc ownership khi dùng \`CharSequence\`

\`CharSequence\` cho phép API đọc nhiều loại nguồn, nhưng không biến \`StringBuilder\` thành bất biến. Nếu chỉ đọc ngay trong lời gọi, tài liệu hóa yêu cầu nguồn không bị thay đổi đồng thời. Nếu cần giữ giá trị cho cache, hàng đợi hoặc xử lý bất đồng bộ, hãy **snapshot một lần** khi nhận:

~~~java
final class Label {
    private final String value;

    Label(CharSequence source) {
        this.value = java.util.Objects.requireNonNull(source, "source")
                .toString();
    }

    String value() { return value; }
}
~~~

Bản \`String\` đã chụp không đổi sau khi bên gọi sửa nguồn. Tuy nhiên việc gọi \`toString()\` trong khi một nguồn mutable **đang bị sửa đồng thời** không mặc nhiên là snapshot nguyên tử; cần thỏa thuận chuyển giao quyền sở hữu hoặc đồng bộ hóa. \`subSequence()\` cũng có thể là view chia sẻ dữ liệu tùy triển khai. Khi API trả view, phải công bố vòng đời và cơ chế cập nhật.

## 7. So sánh nội dung cần ngữ nghĩa được chỉ định

\`String.equals(Object)\` so sánh nội dung với \`String\`, nhưng các implementation của \`CharSequence\` không có quy tắc \`equals/hashCode\` thống nhất. Khi chỉ muốn so sánh văn bản hiện tại:

~~~java
CharSequence candidate = new StringBuilder("key");
System.out.println("key".contentEquals(candidate)); // true
System.out.println("key".equals(candidate));        // false
~~~

Với khóa lưu dài hạn, dùng \`String\` snapshot và \`Map<String, ...>\` khi nghiệp vụ muốn equality theo văn bản. Không giả định \`HashMap<CharSequence, ...>\` sẽ gộp các kiểu nguồn cùng ký tự hoặc bảo đảm khóa ổn định. Phân tích chi tiết \`StringBuilder\`, \`StringBuffer\`, \`CharBuffer\` và \`subSequence\` thuộc bài chuyên sâu ngay sau bài chọn kiểu tham số.

## 8. Unicode và đơn vị đếm ký tự

`String` và `CharSequence` trong Java chủ yếu biểu diễn dãy **đơn vị mã UTF-16**:

- `length()` đếm số đơn vị UTF-16, không nhất thiết là số Unicode code point.
- `charAt(i)` trả một `char` 16-bit; code point nằm ngoài BMP có thể cần một **cặp surrogate** và chiếm hai vị trí.
- `codePoints()` có thể duyệt các code point, nhưng “ký tự” người dùng nhìn thấy (*grapheme cluster*) có thể gồm nhiều code point kết hợp.

Ví dụ Java trong một phương thức:

```java
String emoji = "😀";
System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
```

Nếu API cần đếm “10 ký tự người dùng nhìn thấy”, cả `String.length()` lẫn `CharSequence.length()` đều chưa đủ cho mọi Unicode; cần thuật toán hoặc thư viện phân đoạn grapheme phù hợp. Việc chọn `String` hay `CharSequence` không tự quyết định đơn vị đếm cho nghiệp vụ.

## 9. Tương thích khi sửa chữ ký API đã phát hành

Giả sử thư viện hiện có:

```java
public void submit(String text) {
    // Logic đang tồn tại.
}
```

Đổi thẳng thành `submit(CharSequence text)` có thể vẫn cho phép **mã nguồn gọi bằng `String`** biên dịch lại vì `String implements CharSequence`. Nhưng chữ ký ở mức **JVM bytecode descriptor** thay đổi: chương trình đã biên dịch trước đó tìm `submit(String)` có thể không chạy với phiên bản thư viện chỉ còn `submit(CharSequence)` và gặp `NoSuchMethodError`.

Để xem xét tương thích nhị phân, có thể giữ phương thức cũ và **thêm overload**:

```java
public void submit(String text) {
    // Giữ hành vi hiện có.
}

public void submit(CharSequence text) {
    submit(Objects.requireNonNull(text, "text").toString());
}
```

Đây là đoạn minh họa trong lớp với `import java.util.Objects;`. Khi có cả hai overload, lời gọi bằng biến có kiểu biên dịch `String` chọn overload `String` do cụ thể hơn. Các overload khác có thể gây mơ hồ hoặc đổi cách phân giải lời gọi; cần thử API từ góc nhìn caller. Thêm overload cũng tăng việc phải duy trì nhất quán hành vi. Nếu API cũ vốn đáp ứng nhu cầu, giữ `String` có thể đơn giản hơn.

## 10. Xử lý `null`, hiệu năng và hợp đồng API

**Chính sách `null`:** cả `String` lẫn `CharSequence` là kiểu tham chiếu, nên đều có thể nhận `null`. Chọn rõ trường hợp hợp lệ/không hợp lệ và biểu diễn bằng tài liệu, annotation phù hợp hoặc `Objects.requireNonNull(text, "text")` nếu yêu cầu bắt buộc.

**Không giả định `toString()` miễn phí:** Với `String`, `toString()` trả chính đối tượng; với `StringBuilder` và các nguồn khác, nó có thể tạo/copy chuỗi mới. Nếu chỉ duyệt ký tự ngắn hạn và nguồn không đổi trong lúc gọi, đọc `CharSequence` trực tiếp có thể tránh chuyển đổi không cần thiết. Nếu tính ổn định quan trọng, tạo snapshot là chi phí có chủ đích.

**Không lưu nguyên tham chiếu mutable khi xử lý bất đồng bộ:** Trước khi đưa dữ liệu vào thread/task/queue cần xác định ai sở hữu nguồn và khi nào nguồn có thể bị sửa. Chụp `String` tại ranh giới nếu cần giữ đúng nội dung đã nhận. Đừng dựa vào việc kiểu tham số `CharSequence` có vẻ chỉ đọc để suy ra thread-safe.

**Không ràng buộc mọi API vào interface bằng mọi giá:** Một thư viện nên chọn kiểu tham số phản ánh đúng mô hình dữ liệu. Nếu mọi bước của phương thức đều cần `String` và caller đã có `String`, tham số `String` là lựa chọn rõ nghĩa; nếu thuật toán chỉ cần duyệt ký tự của nhiều nguồn, `CharSequence` là lựa chọn tự nhiên.

Một checklist quyết định:

| Câu hỏi | Gợi ý |
| --- | --- |
| Chỉ đọc ký tự ngay trong phương thức, không giữ nguồn? | Xem xét `CharSequence`. |
| Cần nhận trực tiếp `StringBuilder`, `CharBuffer`? | `CharSequence` đem lại tính linh hoạt. |
| Cần lưu và sử dụng sau? | Dùng `String` hoặc nhận `CharSequence` rồi snapshot. |
| Cần phương thức chỉ `String` mới có? | Chọn `String` hoặc chuyển đổi ở ranh giới rõ ràng. |
| Cần khóa theo nội dung? | `String` có equality/hash và tính bất biến phù hợp. |
| Thay chữ ký public của thư viện? | Xem xét source/binary compatibility trước. |

## 11. Câu hỏi thực hành

1. Vì sao `countAsciiDigits(CharSequence)` nhận được `StringBuilder` mà không cần caller đổi thành `String`? Trong trường hợp nào vẫn phải lưu ý thay đổi đồng thời nguồn?
2. Sau khi `normalizedCode(builder)` trả `"X2"`, vì sao `builder.append("9")` không sửa `captured`?
3. Vì sao `String.contentEquals(CharSequence)` có thể cho kết quả khác `String.equals(Object)` với `StringBuilder`?
4. Khi tạo job bất đồng bộ nhận `CharSequence`, khi nào nên chụp `String` để job xử lý đúng dữ liệu tại thời điểm enqueue?
5. Nếu đổi `submit(String)` thành `submit(CharSequence)`, vì sao một ứng dụng đã compile với phiên bản cũ có thể lỗi mặc dù lời gọi trong mã nguồn vẫn hợp lệ?
6. Vì sao `length()` không luôn bằng số Unicode code point hoặc số ký tự người dùng nhìn thấy?

**Kết luận:** Dùng `CharSequence` khi hợp đồng chỉ cần **đọc dãy ký tự** và có lợi khi hỗ trợ nhiều nguồn văn bản. Dùng `String` khi cần **giá trị bất biến, so sánh/lưu trữ ổn định hoặc các API chuyên biệt**. Khi nhận `CharSequence` mà cần giữ lâu, hãy chụp một `String` tại ranh giới phù hợp và xử lý quyền sở hữu, đồng bộ nguồn cho đúng.