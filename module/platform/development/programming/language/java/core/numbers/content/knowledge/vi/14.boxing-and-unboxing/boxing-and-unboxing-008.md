# Objects.equals và xử lý wrapper có thể null trong Java

Trong Java, các kiểu wrapper như `Integer`, `Long`, `Double`, `Boolean` là **kiểu tham chiếu**, vì vậy biến wrapper có thể chứa `null`. Dù autoboxing/unboxing khiến nhiều biểu thức trông giống đang làm việc với primitive, **unboxing một tham chiếu null sẽ ném `NullPointerException`**. Mặt khác, gọi `a.equals(b)` cũng ném ngoại lệ nếu `a == null`.

`java.util.Objects.equals(a, b)` là công cụ tiêu chuẩn để so sánh hai đối tượng **mà không cần gọi `equals` trên một tham chiếu có thể null**. Tuy nhiên nó **không** tự chuyển `Integer` thành `Long`, **không** unbox để so sánh số học và **không** thay thế chính sách xử lý dữ liệu thiếu. Bài học trình bày cơ chế, các góc cạnh và cách viết code Java 17+ an toàn.

## 1. Wrapper nullable khác primitive như thế nào?

~~~java
int primitive = 0;          // Luôn có giá trị int
Integer wrapper = null;     // Có thể null
Integer boxed = 0;          // Autoboxing: int -> Integer
int unboxed = boxed;        // Unboxing: Integer -> int
~~~

Các wrapper `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `Character` và `Boolean` là các lớp tham chiếu. Chúng có thể đại diện cho **giá trị cụ thể** hoặc **không có đối tượng** (`null`). `null` không đồng nghĩa với số 0, `false` hoặc NaN.

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Primitive `int` | `0` | Có giá trị số nguyên 0 |
| Wrapper `Integer` | `Integer.valueOf(0)` | Có object chứa giá trị 0 |
| Wrapper `Integer` | `null` | Không có object để lấy giá trị |
| Primitive `double` | `Double.NaN` | Có một giá trị `double` đặc biệt; **không phải null** |

Một wrapper null có thể xuất hiện từ trường dữ liệu tùy chọn, một ô thiếu trong dữ liệu ngoài, giá trị trả về của API hoặc phần tử trong collection. Nếu yêu cầu nghiệp vụ phân biệt “không biết” và “bằng 0”, dùng wrapper nullable có thể phù hợp; nếu trường luôn bắt buộc, primitive hoặc validation không-null thường giúp loại bỏ một trạng thái lỗi.

## 2. Ba cách so sánh và mức an toàn khi null

### Cách 1 — `a.equals(b)`

~~~java
Integer a = null;
Integer b = 5;

// a.equals(b); // NullPointerException: a là null
~~~

Khi `a` không null, lời gọi `a.equals(b)` trả về boolean theo hợp đồng equality của object. Nhưng nếu `a` có thể null, bạn phải kiểm tra trước.

### Cách 2 — `Objects.equals(a, b)`

~~~java
import java.util.Objects;

Integer a = null;
Integer b = 5;

boolean first = Objects.equals(a, b);      // false
boolean second = Objects.equals(a, null);  // true
boolean third = Objects.equals(null, null); // true
~~~

`Objects.equals` định nghĩa logic tương đương:

~~~java
static boolean equivalentToObjectsEquals(Object a, Object b) {
    return a == b || (a != null && a.equals(b));
}
~~~

Đây là **phương thức minh họa**, không phải định nghĩa thay thế của thư viện Java. Các nhánh có ý nghĩa:

- Hai đối số cùng null → `true`, vì cùng tham chiếu null.
- Một null, một khác null → `false`.
- Hai đối tượng cùng tham chiếu → `true`.
- Hai object khác tham chiếu và `a` khác null → gọi `a.equals(b)`.

Cụm “null-safe” nghĩa là công cụ **không gọi một phương thức instance trên đối số đầu tiên đang null**. Nó không có nghĩa có thể che mọi lỗi trong custom `equals` do lập trình viên tự viết, hoặc biến dữ liệu null thành một giá trị số.

### Cách 3 — toán tử `==`

`==` có **hai ngữ nghĩa** tùy kiểu tĩnh của toán hạng:

~~~java
Integer x = Integer.valueOf(5);
Integer y = Integer.valueOf(5);
int five = 5;

boolean numberComparison = (x == five);  // true, unbox x
boolean referenceComparison = (x == y);  // kiểm tra cùng tham chiếu
~~~

Ở phép `x == five`, Java unbox `Integer` thành `int` rồi so sánh primitive; nếu `x` null có thể ném `NullPointerException`. Ở `x == y` khi **cả hai toán hạng là các tham chiếu `Integer`**, Java so sánh tham chiếu object. Kết quả có thể phụ thuộc cơ chế cache đối tượng; không dùng `==` để biểu thị value equality giữa wrapper. Ngoại lệ đáng nhớ: `x == null` là phép so sánh tham chiếu, **không unbox `x`** và an toàn.

## 3. `Objects.equals` không tự unbox hoặc nâng kiểu

Các wrapper số triển khai `equals` theo lớp cụ thể. Vì vậy:

~~~java
Integer count = Integer.valueOf(10);
Long total = Long.valueOf(10L);

boolean sameInteger = Objects.equals(count, Integer.valueOf(10)); // true
boolean differentWrappers = Objects.equals(count, total);         // false
boolean literalsWithDifferentTypes = Objects.equals(10, 10L);     // false
~~~

Ở dòng cuối, Java boxing đối số `10` thành `Integer` và `10L` thành `Long` khi truyền cho phương thức nhận `Object`; `Objects.equals` không thực hiện phép số học `10 == 10L`.

So sánh nhanh:

| Biểu thức | Kết quả | Tại sao? |
| --- | --- | --- |
| `Objects.equals(null, null)` | `true` | Cả hai tham chiếu null |
| `Objects.equals(null, 10)` | `false` | Chỉ một bên null |
| `Objects.equals(10, 10)` | `true` | Cùng wrapper `Integer`, cùng giá trị |
| `Objects.equals(10, 10L)` | `false` | `Integer` khác `Long` |
| `10 == 10L` | `true` | Primitive numeric promotion |
| `Objects.equals(Double.NaN, Double.NaN)` | `true` | `Double.equals` xem hai NaN bằng nhau |
| `Objects.equals(+0.0, -0.0)` | `false` | `Double.equals` phân biệt zero có dấu |

**Không nên dùng `Objects.equals` để so sánh trị số giữa nhiều wrapper khác kiểu.** Nếu cần coi `Integer(10)` và `Long(10)` như cùng một số, phải định nghĩa miền số và quy tắc chuyển kiểu. Ví dụ, khi chắc chắn hai đối số là wrapper số nguyên trong phạm vi `long` và không null, có thể dùng `a.longValue() == b.longValue()`. Không chuyển bừa mọi `Number` sang `doubleValue()`: số nguyên lớn có thể mất độ chính xác.

## 4. Unboxing null: lỗi không biến mất nhờ autoboxing

Ví dụ này **cố ý gây lỗi khi chạy** nếu bỏ comment:

~~~java
Integer count = null;

// int primitive = count;   // NullPointerException: unboxing
// int next = count + 1;    // NullPointerException: toán tử + phải unbox
// boolean positive = count > 0; // NullPointerException
// boolean zero = (count == 0);  // NullPointerException
~~~

Dù `count` có kiểu wrapper, toán tử số học hoặc so sánh với primitive cần lấy giá trị `int` từ object. Khi object là null, unboxing không thể thực hiện.

Ngược lại:

~~~java
Integer count = null;
boolean isAbsent = (count == null); // true, không unbox
boolean same = Objects.equals(count, null); // true, không unbox
~~~

Sự khác biệt giữa `count == null` và `count == 0` rất quan trọng. Câu đầu kiểm tra tình trạng có object hay không; câu sau cố lấy giá trị số từ wrapper.

Đối với `Boolean` cũng vậy:

~~~java
Boolean enabled = null;
// if (enabled) { } // NullPointerException do unboxing Boolean
if (Boolean.TRUE.equals(enabled)) {
    // Chạy chỉ khi enabled là Boolean.TRUE
}
~~~

`Boolean.TRUE.equals(enabled)` an toàn vì hằng `Boolean.TRUE` chắc chắn không null. Nó coi cả null lẫn false là “không bật”, **chỉ phù hợp nếu nghiệp vụ chấp nhận cách gộp này**. Nếu null nghĩa là “chưa xác định”, đừng tự biến nó thành false mà không định nghĩa chính sách.

## 5. Dùng short-circuit `&&` và `||` để kiểm tra trước khi unbox

Trong các điều kiện, Java đánh giá `&&` và `||` từ trái sang phải và chỉ đánh giá vế phải khi cần. Ta có thể dùng tính chất này để tránh unboxing null:

~~~java
Integer count = null;

boolean positive = count != null && count > 0; // false
boolean missingOrPositive = count == null || count > 0; // true
~~~

- Với `&&`, nếu `count != null` đã false thì vế `count > 0` không được chạy.
- Với `||`, nếu `count == null` đã true thì vế `count > 0` không được chạy.

**Thứ tự điều kiện không được đảo tùy tiện:**

~~~java
// count > 0 && count != null  // Sai: có thể unbox null trước
// count > 0 || count == null  // Sai: có thể unbox null trước
~~~

Với toán tử boolean không-short-circuit `&` hoặc `|`, cả hai vế được đánh giá (khi dùng boolean), nên **không** áp dụng mẹo null guard như trên. Đây là vấn đề quan trọng khi refactor điều kiện hoặc xây biểu thức filter.

Một phương thức kiểm tra giá trị dương nullable có thể viết rõ ràng:

~~~java
static boolean isPositive(Integer value) {
    return value != null && value > 0;
}
~~~

Phương thức này chủ ý trả `false` nếu không có giá trị; đó là một **quy ước nghiệp vụ** cần được thể hiện rõ trong tên hàm và tài liệu.

## 6. Chọn mặc định hay từ chối null?

`Objects.equals` phục vụ **so sánh**, không trả giá trị thay thế. Khi ứng dụng cần dùng primitive, phải ra quyết định cụ thể với null.

### Cách A — trả về giá trị mặc định

~~~java
Integer optionalCount = null;
int safeCount = java.util.Objects.requireNonNullElse(optionalCount, 0);
// safeCount = 0
~~~

`Objects.requireNonNullElse(value, defaultValue)` trả giá trị đầu nếu khác null; nếu không thì trả default. **Default cũng bắt buộc khác null**, nếu cả hai đều null sẽ ném `NullPointerException`. Đối với wrapper, phương thức này trả về **wrapper**; trong ví dụ, gán vào `int` diễn ra unboxing sau khi đã có default không null.

Với biểu thức tạo default tốn tài nguyên, có `Objects.requireNonNullElseGet(value, supplier)`; supplier được gọi khi giá trị ban đầu null và phải trả giá trị không null. Nếu đối số đầu đã có giá trị, supplier không bị gọi.

Một lựa chọn tương tự là:

~~~java
int safeCount = optionalCount == null ? 0 : optionalCount;
~~~

Toán tử điều kiện ở đây chọn giá trị primitive an toàn sau khi kiểm tra null. Tuy nhiên **đừng** mặc định mọi null đều là 0: tổng đơn hàng chưa được nhập, tuổi chưa biết và số lượng chính xác bằng 0 thường là các trạng thái khác nhau.

### Cách B — báo lỗi ngay tại ranh giới

~~~java
static int requireCount(Integer value) {
    return java.util.Objects.requireNonNull(value, "count is required");
}
~~~

Hàm này ném `NullPointerException` với thông báo khi null và unbox sau khi đã xác nhận có object. Nếu null đại diện cho **đầu vào không hợp lệ**, bạn có thể chọn `IllegalArgumentException` hoặc một kiểu lỗi nghiệp vụ khác theo quy ước API.

### Cách C — giữ rõ trạng thái thiếu

Nếu thiếu dữ liệu là hợp lệ, bạn có thể giữ `Integer` nullable, dùng `Optional<Integer>` ở một số API trả về, hoặc mô hình hóa trạng thái riêng. Hãy xác định quy tắc downstream: tính toán phải dừng, bỏ qua phần tử thiếu, hay trả về kết quả “chưa đủ dữ liệu”? Đừng chọn một giá trị giả như `-1` hoặc 0 nếu nó cũng có thể là giá trị thật.

## 7. So sánh nullable ở các vị trí thực tế

### DTO và đối tượng nghiệp vụ

Giả sử hai request có trường `Integer quantity` cho phép null. Nếu cần kiểm tra xem trường có thay đổi so với bản cũ hay không:

~~~java
static boolean quantityChanged(Integer oldQuantity, Integer newQuantity) {
    return !java.util.Objects.equals(oldQuantity, newQuantity);
}
~~~

Khi cả hai đều null, hàm trả false (không thay đổi); khi chỉ một bên null, hàm trả true; khi hai bên có cùng `Integer`, trả false. Điều này khác với chính sách “null nghĩa là 0”: nếu nghiệp vụ coi null và 0 là giống nhau, phải chuẩn hóa **một cách công khai** trước khi so sánh.

### Collection và tìm kiếm

~~~java
java.util.List<Integer> values = java.util.Arrays.asList(1, null, 3);
boolean hasMissing = values.contains(null); // true
boolean hasThree = values.contains(3);      // true
~~~

Các collection sử dụng equality theo hợp đồng của phần tử; `List.contains` theo `equals`, nên có thể xử lý null nếu triển khai collection cho phép. Tuy nhiên, với `HashMap`/`HashSet` và wrapper làm khóa, đừng gộp `Integer(3)` với `Long(3)`; `Objects.equals` không hề xóa ranh giới kiểu này.

### Sắp xếp danh sách có null

~~~java
java.util.List<Integer> values =
        new java.util.ArrayList<>(java.util.Arrays.asList(3, null, 1));
values.sort(java.util.Comparator.nullsFirst(Integer::compare));
// [null, 1, 3]
~~~

`Integer::compare` so sánh các giá trị không null; `Comparator.nullsFirst` xử lý null trước khi chuyển cho comparator nội bộ. Có thể dùng `nullsLast` nếu muốn xếp giá trị thiếu cuối danh sách.

**Đừng dùng `Integer::compare` trực tiếp cho danh sách có null** khi chưa có lớp xử lý: unboxing đối số null có thể ném `NullPointerException` trong quá trình sort.

## 8. `Objects.equals` và mảng, đối tượng cấu trúc phức tạp

Hai mảng khác tham chiếu nhưng có cùng phần tử không được xem bằng nhau bằng `Objects.equals`:

~~~java
Integer[] a = {1, null};
Integer[] b = {1, null};

boolean shallow = java.util.Objects.equals(a, b);     // false
boolean deep = java.util.Objects.deepEquals(a, b);    // true
~~~

Mảng Java không override `Object.equals` theo nội dung; `Objects.equals` do đó so sánh cùng tham chiếu. `Objects.deepEquals` nhận biết mảng và so sánh phần tử (kể cả mảng lồng nhau) một cách thích hợp; hoặc dùng `Arrays.equals`/`Arrays.deepEquals` theo dạng dữ liệu. Không cho rằng tên phương thức “Objects” tự động so sánh sâu mọi object: đối với class tự định nghĩa, logic equality vẫn phụ thuộc triển khai `equals`.

Cẩn trọng khi viết class có field wrapper nullable: nếu dùng `equals` tự viết, `hashCode` nên sử dụng chính những field phù hợp, chẳng hạn `Objects.hash(fieldA, fieldB)`, để tuân theo hợp đồng “hai object bằng nhau phải có hash code bằng nhau”. Với Java `record`, equality sinh tự động cho component theo quy tắc của ngôn ngữ; vẫn cần hiểu ý nghĩa của giá trị null và kiểu của component.

## 9. Ví dụ Java 17+ hoàn chỉnh có thể chạy

Lưu tệp `NullableWrapperDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class NullableWrapperDemo {
    public static void main(String[] args) {
        Integer missing = null;
        Integer ten = 10;
        Integer tenAgain = Integer.valueOf(10);
        Long tenLong = 10L;

        System.out.println("missing == null: " + (missing == null));
        System.out.println("equals(null,null): "
                + Objects.equals(null, null));
        System.out.println("equals(missing,ten): "
                + Objects.equals(missing, ten));
        System.out.println("equals(ten,missing): "
                + Objects.equals(ten, missing));
        System.out.println("equals(ten,tenAgain): "
                + Objects.equals(ten, tenAgain));
        System.out.println("equals(ten,tenLong): "
                + Objects.equals(ten, tenLong));
        System.out.println("equals(10,10L): "
                + Objects.equals(10, 10L));
        System.out.println("ten == 10: " + (ten == 10));
        System.out.println("safe AND: "
                + (missing != null && missing > 0));
        System.out.println("safe OR: "
                + (missing == null || missing > 0));

        try {
            int primitive = missing;
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("unbox null: NullPointerException");
        }

        System.out.println("default zero: "
                + Objects.requireNonNullElse(missing, 0));

        List<Integer> list =
                new ArrayList<>(Arrays.asList(3, null, 1));
        list.sort(Comparator.nullsFirst(Integer::compare));
        System.out.println("sorted null first: " + list);

        Integer[] a = {1, null};
        Integer[] b = {1, null};
        System.out.println("arrays equals: " + Objects.equals(a, b));
        System.out.println("arrays deepEquals: "
                + Objects.deepEquals(a, b));

        System.out.println("Double NaN equals: "
                + Objects.equals(Double.NaN, Double.NaN));
        System.out.println("signed zero equals: "
                + Objects.equals(+0.0, -0.0));
        System.out.println("BigDecimal scale equals: "
                + Objects.equals(
                        new BigDecimal("1.0"),
                        new BigDecimal("1.00")));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac NullableWrapperDemo.java
java NullableWrapperDemo
~~~

Kết quả stdout:

~~~text
missing == null: true
equals(null,null): true
equals(missing,ten): false
equals(ten,missing): false
equals(ten,tenAgain): true
equals(ten,tenLong): false
equals(10,10L): false
ten == 10: true
safe AND: false
safe OR: true
unbox null: NullPointerException
default zero: 0
sorted null first: [null, 1, 3]
arrays equals: false
arrays deepEquals: true
Double NaN equals: true
signed zero equals: false
BigDecimal scale equals: false
~~~

Chương trình xác nhận được cả đường đi có và không có null, wrapper khác kiểu, unboxing an toàn/không an toàn, thứ tự sắp xếp null và sự khác nhau giữa equality sâu/nông. Lưu ý `try/catch` ở đây chỉ dùng để minh họa ngoại lệ do unboxing null; **không nên dùng bắt ngoại lệ thay kiểm tra null** như một luồng xử lý thường ngày.

## 10. Những giới hạn cần nhớ của `Objects.equals`

- **Không tự biến null thành số 0:** `Objects.equals(null, 0)` là `false`; null vẫn là trạng thái vắng mặt.
- **Không nâng kiểu wrapper khi equality:** `Objects.equals(10, 10L)` là `false` vì `Integer` khác `Long`.
- **Không tự so sánh mảng theo phần tử:** dùng `Arrays.equals`, `Arrays.deepEquals` hoặc `Objects.deepEquals`.
- **Không xử lý null bên trong logic khác:** `Objects.equals(a, b)` không làm cho `a + 1` an toàn nếu `a == null`.
- **Không giải quyết số thực theo tolerance:** `Objects.equals(0.1 + 0.2, 0.3)` trả `false`; định nghĩa riêng tolerance nếu bài toán yêu cầu.
- **Không sửa hợp đồng `BigDecimal.equals`:** `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có giá trị toán học bằng nhau theo `compareTo == 0` nhưng `equals` trả `false` vì khác scale.
- **Không đồng nhất Boolean null với false:** `Objects.equals(null, Boolean.FALSE)` trả `false`; nếu dùng `Boolean.TRUE.equals(value)` thì bạn đang chủ động diễn giải null giống “không bật” cho mục đích kiểm tra.

Một số lỗi phổ biến là dùng `if (wrapper == 0)` trước khi kiểm tra null, viết `wrapper.equals(other)` dù wrapper nullable, dựa vào `==` để so giá trị của hai wrapper, hoặc ép các giá trị null về mặc định tại quá nhiều lớp hệ thống làm mất dấu nguồn dữ liệu thiếu.

## 11. Cách lựa chọn khi xây dựng API

| Yêu cầu | Cách xử lý | Điểm cần chú ý |
| --- | --- | --- |
| So sánh hai wrapper nullable theo object equality | `Objects.equals(a, b)` | Hai null bằng nhau; các wrapper khác kiểu không tự bằng nhau |
| Kiểm tra wrapper null | `value == null` hoặc `value != null` | Không unbox |
| Dùng wrapper trong phép toán | Null guard rồi unbox | Thông báo lỗi/mặc định theo hợp đồng |
| Dùng Boolean nullable trong điều kiện | `Boolean.TRUE.equals(flag)` hoặc ba nhánh | Phân biệt false với không xác định nếu cần |
| Có giá trị mặc định hợp lệ | `Objects.requireNonNullElse(value, defaultValue)` | Default phải khác null; không che dữ liệu thiếu ngoài ý muốn |
| Bắt buộc có giá trị | `Objects.requireNonNull(value, message)` | Fail fast tại ranh giới |
| Sắp xếp list có null | `Comparator.nullsFirst/nullsLast` | Comparator bên trong chỉ xử lý non-null |
| Equality mảng | `Arrays.equals` hoặc `Objects.deepEquals` | Chọn đúng mức nông/sâu |
| So sánh số học khác wrapper type | Chuẩn hóa theo miền số đã xác định | Tránh ép mọi `Number` về `double` gây mất chính xác |

## 12. Tự luyện và đáp án

**Câu 1.** Với `Integer x = null`, kết quả của `Objects.equals(x, null)` và `x == 0` là gì?

**Đáp án:** `Objects.equals(x, null)` là `true`; `x == 0` cố unbox null và ném `NullPointerException`.

**Câu 2.** `Objects.equals(Integer.valueOf(3), Long.valueOf(3L))` trả gì? Còn `3 == 3L`?

**Đáp án:** Lời gọi đầu trả `false` do khác wrapper; phép so sánh primitive trả `true` sau numeric promotion.

**Câu 3.** Với `Boolean approved = null`, viết một điều kiện không ném NPE và chỉ nhận đúng true.

**Đáp án:** `Boolean.TRUE.equals(approved)`. Nếu null cần phân biệt với false, bổ sung nhánh xử lý riêng.

**Câu 4.** Tại sao `count != null && count > 0` an toàn hơn `count > 0 && count != null`?

**Đáp án:** `&&` đánh giá từ trái sang phải và short-circuit. Biểu thức đầu kiểm tra null trước; biểu thức sau đã unbox trước khi kiểm tra.

**Câu 5.** Hai mảng `Integer[]` mới tạo với cùng phần tử có nhất thiết `Objects.equals` là true không?

**Đáp án:** Không. `Objects.equals` dùng equality tham chiếu của mảng; dùng `Arrays.equals` hoặc `Objects.deepEquals` để so sánh phần tử.

**Câu 6.** Nếu null phải được coi là một giá trị “chưa cung cấp”, có nên thay nó bằng 0 chỉ để tránh NPE không?

**Đáp án:** Không nên, trừ khi đặc tả nghiệp vụ quy định rõ null tương đương 0. Có thể giữ nullable/`Optional` hoặc từ chối input không hợp lệ để bảo toàn ý nghĩa dữ liệu.

## Tài liệu tham khảo

- [Java SE 21 — Objects.equals và deepEquals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html).
- [Java SE 21 — Integer.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#equals(java.lang.Object)).
- [Java SE 21 — Boolean](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Boolean.html).
- [Java SE 21 — Comparator.nullsFirst](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).
- [Java Language Specification `5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8).
