# `Objects.toString()` với giá trị mặc định khi `null`

## 1. Mục đích và hai overload

Trong Java, gọi `value.toString()` trên tham chiếu `null` sẽ ném `NullPointerException`. Lớp tiện ích `java.util.Objects` cung cấp hai phương thức tĩnh giúp lấy chuỗi biểu diễn của một đối tượng, kể cả khi đầu vào không có giá trị:

```java
public static String toString(Object o)
public static String toString(Object o, String nullDefault)
```

Đây là các chữ ký API để đọc, không phải chương trình độc lập.

Với overload **một tham số**, nếu `o` không null thì kết quả là `o.toString()`; nếu `o == null` thì kết quả là chuỗi gồm bốn ký tự `"null"`.

Với overload **hai tham số**, nếu `o` không null thì kết quả vẫn là `o.toString()`; nếu `o == null` thì kết quả là giá trị `nullDefault` mà người gọi truyền vào. Nhờ vậy có thể chọn nhãn dễ đọc như `"N/A"`, `"(chưa cung cấp)"` hoặc chuỗi rỗng cho giao diện.

```java
String department = null;
String label = java.util.Objects.toString(department, "(chưa có)");
System.out.println(label); // (chưa có)
```

Mảnh mã trên hợp lệ trong một phương thức, không phải tệp có `main` riêng. Nó không tự sửa dữ liệu gốc; chỉ tạo chuỗi trả về.

## 2. Nhánh lựa chọn: chỉ kiểm tra tham chiếu của đối tượng

Ngữ nghĩa của overload hai tham số có thể viết gần tương đương với biểu thức điều kiện:

```java
String result = o != null ? o.toString() : nullDefault;
```

Đây là mô tả logic, không ràng buộc JDK phải có mã nguồn nội bộ như vậy.

- **`o == null`:** trả `nullDefault`; không gọi phương thức nào trên `o`.
- **`o != null`:** gọi `o.toString()`. Nếu lớp thực tế override `toString()` thì nhận kết quả của override đó. Tham số mặc định không thay thế kết quả này.

Điều kiện dựa trên **tham chiếu**, không dựa trên nội dung chuỗi. Nếu `o` là `""`, `" "`, `"null"`, `0` hoặc một đối tượng có trạng thái được coi là rỗng theo nghiệp vụ, nó vẫn khác null.

| Lời gọi | Kết quả | Vì sao |
| --- | --- | --- |
| `Objects.toString(null, "N/A")` | `"N/A"` | Tham chiếu null |
| `Objects.toString(null, "")` | `""` | Giá trị mặc định được chọn |
| `Objects.toString(null, null)` | `null` | Được phép dùng mặc định null |
| `Objects.toString("Java", "N/A")` | `"Java"` | Đối tượng tồn tại |
| `Objects.toString("", "N/A")` | `""` | Chuỗi rỗng vẫn là một đối tượng |
| `Objects.toString("null", "N/A")` | `"null"` | Chuỗi chữ null không phải tham chiếu null |
| `Objects.toString(12, "N/A")` | `"12"` | Autoboxing sang Integer và dùng `toString()` |

**Điểm dễ bỏ sót:** dù `o` không null, một override `toString()` do người dùng viết có thể ném ngoại lệ hoặc thậm chí trả tham chiếu null. `Objects.toString(o, fallback)` không bắt ngoại lệ đó và không kiểm tra lại xem chuỗi do `o.toString()` trả về có null hay không. Vì vậy nó bảo vệ lời gọi khỏi **tham chiếu đầu vào null**, không chứng nhận chất lượng của triển khai `toString()`.

## 3. `"null"` và `null` là hai kết quả khác nhau

`Objects.toString(null)` trả chuỗi ký tự `"null"`, không phải tham chiếu null. Overload hai tham số có thể trả null nếu chính `nullDefault` là null.

```java
String a = java.util.Objects.toString(null);
String b = java.util.Objects.toString(null, null);
System.out.println(a == null); // false
System.out.println(b == null); // true
```

Đây là mảnh mã minh họa. Phân biệt hai kết quả là cần thiết trong xử lý giao diện, lưu cơ sở dữ liệu và kiểm thử: **chuỗi `"null"`** là dữ liệu gồm bốn ký tự, còn **`null`** là không có đối tượng `String`.

Mặc dù mục đích thường gặp của overload hai tham số là bảo đảm một nhãn dễ đọc, API không bắt buộc fallback phải khác null. Muốn có chuỗi hiển thị khi đối tượng bị thiếu, hãy dùng một fallback không null như `"N/A"`. Với đầu vào khác null, tính hợp lệ của kết quả vẫn phụ thuộc `toString()` của đối tượng.

## 4. Ví dụ hoàn chỉnh trên Java 17+

Lưu chương trình sau vào `ObjectsToStringDemo.java`:

```java
import java.util.Objects;

public class ObjectsToStringDemo {
    static final class Ticket {
        private final int id;

        Ticket(int id) {
            this.id = id;
        }

        @Override
        public String toString() {
            return "Ticket#" + id;
        }
    }

    private static String buildFallback() {
        System.out.println("fallback evaluated");
        return "<computed>";
    }

    public static void main(String[] args) {
        Object missing = null;
        Object text = "Java";
        Object ticket = new Ticket(7);

        System.out.println("missing: "
                + Objects.toString(missing, "<unknown>"));
        System.out.println("non-null: "
                + Objects.toString(text, "<unknown>"));
        System.out.println("custom: "
                + Objects.toString(ticket, "<unknown>"));
        System.out.println("empty: ["
                + Objects.toString("", "<unknown>") + "]");

        System.out.println("one argument: ["
                + Objects.toString(null) + "]");
        System.out.println("two arguments null default: "
                + (Objects.toString(null, null) == null));

        System.out.println("not lazy: "
                + Objects.toString("ready", buildFallback()));
        System.out.println("lazy alternative: "
                + (text == null ? buildFallback() : text.toString()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ObjectsToStringDemo.java
java ObjectsToStringDemo
```

Kết quả chính xác:

```text
missing: <unknown>
non-null: Java
custom: Ticket#7
empty: []
one argument: [null]
two arguments null default: true
fallback evaluated
not lazy: ready
lazy alternative: Java
```

Giải thích:

1. `missing` là tham chiếu null nên được thay bằng `"<unknown>"`. `text` chứa đối tượng `String` nên nhận chính nội dung `"Java"`.
2. Với `ticket`, phương thức gọi `Ticket.toString()` do lớp tự định nghĩa, trả `"Ticket#7"`. `Objects` không tự lấy tên trường hoặc định dạng thông tin nghiệp vụ.
3. Chuỗi `""` khác null nên giữ nguyên; dấu ngoặc vuông trong output làm chuỗi rỗng dễ quan sát.
4. Kết quả overload một tham số là chữ `"null"`, còn khi fallback hai tham số là null thì biểu thức so tham chiếu với null trả `true`.
5. `buildFallback()` được thực thi **trước** lời gọi `Objects.toString("ready", ...)`, nên in `fallback evaluated` dù đối tượng đầu khác null.
6. Trong toán tử điều kiện `?:`, chỉ nhánh được chọn được thực hiện. Khi `text` khác null, `buildFallback()` không được gọi thêm; dòng cuối in `Java`.

## 5. Giá trị mặc định không được tính lười

Lời gọi `Objects.toString(value, fallbackExpression)` không phải cơ chế lazy fallback. **Java đánh giá các đối số trước khi thực hiện phương thức.** Vì vậy:

```java
String label = Objects.toString(value, expensiveFallback());
```

Đây là mảnh mã minh họa, giả định `value` và `expensiveFallback()` đã được khai báo. `expensiveFallback()` được gọi dù `value` có khác null. Nếu biểu thức mặc định phải truy cập cơ sở dữ liệu, làm I/O, tính toán lớn hoặc có tác dụng phụ, đây có thể là lỗi hiệu năng hay hành vi.

Khi chỉ muốn tạo giá trị mặc định nếu thực sự cần, dùng nhánh điều kiện:

```java
String label = value == null
        ? expensiveFallback()
        : value.toString();
```

Ở biểu thức này, chỉ một trong hai nhánh được tính. Nếu fallback đơn giản là literal `"N/A"` thì `Objects.toString(value, "N/A")` vẫn là cách viết rõ ràng và gọn nhất.

Không có overload `Objects.toString(Object, Supplier<String>)` trong API này. Đừng suy luận cách hoạt động từ `Objects.requireNonNullElseGet`, vì đó là phương thức khác với mục đích và kiểu kết quả khác.

## 6. Phân biệt với `String.valueOf` và `Objects.requireNonNullElse`

| API | Hành vi với null | Mục đích |
| --- | --- | --- |
| `o.toString()` | Ném `NullPointerException` khi chính `o` là null | Lấy biểu diễn chuỗi trên đối tượng đã biết tồn tại |
| `Objects.toString(o)` | Trả chuỗi `"null"` | Biểu diễn đối tượng, chấp nhận chữ null |
| `Objects.toString(o, "N/A")` | Trả `"N/A"` | Tùy biến biểu diễn khi tham chiếu null |
| `String.valueOf((Object) o)` | Trả chuỗi `"null"` | Chuyển một tham chiếu Object sang chuỗi |
| `Objects.requireNonNullElse(o, fallback)` | Trả đối tượng fallback, yêu cầu fallback khác null | Chọn một đối tượng thay thế, không tự chuyển sang String |
| `Objects.requireNonNullElseGet(o, supplier)` | Dùng supplier khi `o` null | Chọn đối tượng thay thế theo cách lazy |

Chú ý `String.valueOf` có **nhiều overload**. Để mô tả overload nhận tham chiếu Object, dùng kiểu tĩnh rõ ràng `String.valueOf((Object) null)`; đừng suy ra hành vi của tất cả overload từ ví dụ `String.valueOf(null)` không ép kiểu, vì overload `char[]` có thể được chọn và gây ngoại lệ.

`Objects.requireNonNullElse` trả về đối tượng cùng kiểu có thể dùng thay giá trị bị thiếu, trong khi `Objects.toString` chủ động chuyển kết quả thành `String`. `Objects.requireNonNullElse` từ chối fallback null; `Objects.toString(o, null)` thì không.

Cũng đừng nhầm với `Objects.equals(a, b)`. Đó là phương thức so sánh hai giá trị; `Objects.toString` không xác lập danh tính hoặc sự bằng nhau. Hai đối tượng có cùng `toString()` vẫn có thể không bằng nhau theo `equals`.

## 7. Kết quả `toString()` phụ thuộc lớp của đối tượng

`Objects.toString` không phải trình tuần tự hóa JSON hay công cụ tự động diễn giải thuộc tính. Nó dùng `toString` mà lớp thực tế cung cấp.

- `String.toString()` trả về nội dung chuỗi.
- `Integer`, `Long`, `Boolean` và các wrapper khác trả dạng văn bản của giá trị.
- Record không tùy biến có `toString` được tự sinh để mô tả các thành phần; không nên xem định dạng này như giao thức lưu trữ bền vững.
- Lớp không override `Object.toString()` dùng biểu diễn mặc định dạng tên lớp và mã hex dựa trên hash code. Đây không phải ID nghiệp vụ ổn định.
- Mảng không tự chuyển thành danh sách phần tử khi gọi `Objects.toString(array, "N/A")`.

Nếu cần chuỗi các phần tử mảng, sử dụng tiện ích của `Arrays`:

```java
int[] data = {1, 2, 3};
String result = java.util.Arrays.toString(data); // "[1, 2, 3]"
```

Đây là một mảnh mã minh họa, chưa có `main` độc lập. Với mảng lồng nhau, cân nhắc `Arrays.deepToString`. Khi đối tượng chứa dữ liệu nhạy cảm hoặc cấu trúc lớn, không trực tiếp ghi toàn bộ `toString()` vào log nếu chưa kiểm soát nội dung.

Nếu muốn hiển thị tiền tệ, thời gian, số thập phân theo locale hoặc JSON, phải dùng formatter/serializer phù hợp. `Objects.toString` chỉ giải quyết lựa chọn biểu diễn chuỗi và trường hợp đối tượng null.

## 8. Không phải mọi giá trị “trống” đều là null

Trường hợp `""`, `"  "`, `"null"` hoặc `"unknown"` vẫn là đối tượng `String` bình thường. Do đó `Objects.toString(value, "N/A")` không thay thế chúng.

Nếu quy tắc nghiệp vụ muốn coi cả chuỗi trắng là không có thông tin, phải ghi điều kiện rõ ràng:

```java
String display = input == null || input.isBlank()
        ? "(không có nội dung)"
        : input;
```

Đây là mảnh mã minh họa, giả định `input` có kiểu `String`. `String.isBlank()` (Java 11+) xem chuỗi rỗng hoặc chỉ gồm ký tự whitespace là blank, **khác** điều kiện null.

Điều này đặc biệt quan trọng với biểu mẫu, thông tin nhập từ file và dữ liệu từ API: `null` có thể nghĩa là vắng mặt, còn `""` có thể nghĩa là một giá trị trống có chủ ý. Không tự hợp nhất các trường hợp khi hợp đồng nghiệp vụ cần phân biệt.

## 9. Tình huống sử dụng

**Giao diện người dùng:** hiển thị trường tùy chọn bằng nhãn mặc định. Ví dụ `Objects.toString(profile.getNickname(), "(chưa đặt)")` phù hợp khi nickname có thể null và `toString()` của giá trị đã đúng định dạng hiển thị.

**Báo cáo:** điền `"N/A"` cho trường không có dữ liệu nhưng để nguyên số, chuỗi hoặc mã đã có. Nếu báo cáo yêu cầu số hoặc ngày tháng theo định dạng địa phương, cần thêm formatter chuyên dụng.

**Logging và thông báo gỡ lỗi:** lựa chọn cách in một đối tượng vắng mặt mà không gây `NullPointerException`. Tuy vậy, logging cần cân nhắc dữ liệu riêng tư, chi phí `toString` và định dạng đối tượng.

**Khóa và giá trị có cấu trúc:** không sử dụng `toString` như định nghĩa danh tính, định dạng serialization hoặc phép so sánh, vì nhiều lớp tùy chỉnh `toString` chỉ để gỡ lỗi. Nếu chỉ cần mã sản phẩm, lấy đúng trường mã rồi xử lý null theo ngữ nghĩa của trường.

## 10. Lỗi thường gặp và checklist

1. **Nhầm `"null"` với null:** overload một tham số trả chuỗi `"null"`; overload hai tham số có thể trả chính null.
2. **Tin rằng chuỗi rỗng kích hoạt fallback:** `Objects.toString("", "N/A")` trả `""`. Muốn xử lý blank cần điều kiện bổ sung.
3. **Cho rằng fallback lazy:** mọi biểu thức đối số được tính trước khi gọi hàm; dùng `?:` nếu phải trì hoãn fallback đắt đỏ.
4. **Cho rằng fallback sửa được `toString` lỗi:** khi `o` khác null, phương thức vẫn gọi `o.toString()`; ngoại lệ ở đó không được tự bắt.
5. **Cho rằng tham số mặc định bắt buộc khác null:** `Objects.toString(null, null)` trả tham chiếu null.
6. **Dùng `toString` như danh tính:** cùng chuỗi hiển thị không có nghĩa hai đối tượng bằng nhau; dùng `equals` theo hợp đồng.
7. **Mặc định mảng được in theo phần tử:** dùng `Arrays.toString` hay `Arrays.deepToString` khi cần nội dung dễ đọc.
8. **Không tính đến ngữ nghĩa dữ liệu:** chọn nhãn fallback phù hợp cho từng giao diện, báo cáo hoặc API; phân biệt null với chuỗi rỗng.
9. **Không kiểm thử các giá trị biên:** thử null, chuỗi rỗng, non-null, fallback null, đối tượng có `toString` riêng và fallback có tác dụng phụ.

**Kết luận:** `Objects.toString(o, nullDefault)` gọi `toString()` khi `o` tồn tại; **chỉ khi chính tham chiếu `o` là null**, nó mới trả `nullDefault`. Giá trị mặc định do người gọi lựa chọn có thể là chuỗi bất kỳ hoặc null, và biểu thức tạo ra nó được tính trước lời gọi. Dùng phương thức này khi cần nhãn văn bản an toàn cho dữ liệu có thể thiếu, đồng thời giữ rõ ràng ranh giới giữa null, chuỗi rỗng và biểu diễn thực của đối tượng.
