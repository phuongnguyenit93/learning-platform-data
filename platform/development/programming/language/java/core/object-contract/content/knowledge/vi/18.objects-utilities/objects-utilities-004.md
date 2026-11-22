# Objects.hash() cho nhiều giá trị và tình huống truyền mảng

## 1. Objects.hash() dùng để làm gì?

`java.util.Objects.hash(Object... values)` là phương thức tiện ích tính **một giá trị `int` từ nhiều đối số**. Nó thường xuất hiện khi một class override `hashCode()` và cần kết hợp các trường tham gia quan hệ bằng nhau:

```java
@Override
public int hashCode() {
    return Objects.hash(customerId, region, version);
}
```

Đoạn trên là phần thân phương thức minh họa bên trong một class có ba trường tương ứng, không phải tệp Java độc lập. Các đối số được xử lý theo đúng thứ tự; số lượng và giá trị của từng đối số ảnh hưởng đến hash được tính.

**Định nghĩa chính xác:** Javadoc Java 17 của `Objects.hash(Object... values)` quy định kết quả tương đương với `Arrays.hashCode(Object[])` áp dụng trên **mảng đối số thực sự được truyền cho tham số varargs**. Nghĩa là có thể hình dung:

```java
// Ý tưởng tương đương, không phải khai báo lại phương thức JDK:
static int hashMany(Object... values) {
    return java.util.Arrays.hashCode(values);
}
```

Điểm thường bị bỏ sót nằm ở dấu ba chấm `...`: trong Java, một lời gọi varargs có thể truyền **nhiều giá trị riêng lẻ** hoặc truyền **một mảng tương thích với kiểu tham số mảng**. Nếu đối số cuối cùng vốn là một mảng, compiler có thể coi nó là chính mảng varargs, thay vì một giá trị duy nhất bên trong mảng varargs.

Bài học cần phân biệt:

- `Objects.hash(a, b, c)`: kết hợp ba giá trị.
- `Objects.hash(a)`: tạo hash của **một danh sách có một phần tử**, không nhất thiết giống `a.hashCode()`.
- `Objects.hash((Object[]) array)`: khi `array` là `Object[]` hoặc mảng tham chiếu con như `String[]`, truyền chính nó làm mảng varargs.
- `Objects.hash((Object) array)`: ép compiler coi cả mảng là **một đối tượng duy nhất**, rồi dùng hash của chính đối tượng mảng đó.
- `Objects.hash(primitiveArray)`: mảng nguyên thủy như `int[]` không phải `Object[]`, nên là một phần tử `Object` trong varargs.

Đừng nhầm `Objects.hash` với thuật toán băm mật mã, mã định danh duy nhất, hoặc phương thức tự động so sánh sâu mọi cấu trúc mảng. Nó là tiện ích tính hash cho hợp đồng `Object.hashCode`, vốn cho phép va chạm.

## 2. Nhiều đối số: kết hợp theo thứ tự

`Objects.hash("A", 7)` được tính như `Arrays.hashCode(new Object[] {"A", Integer.valueOf(7)})`. Với công thức cho `Object[]`, bắt đầu từ `result = 1`, rồi theo từng phần tử thực hiện `result = 31 * result + elementHash`. Phần tử `null` đóng góp giá trị `0`; các phép toán `int` có thể tràn theo ngữ nghĩa Java.

Với `"A".hashCode() == 65` và `Integer.valueOf(7).hashCode() == 7`:

1. Sau `"A"`: `31 * 1 + 65 = 96`.
2. Sau `7`: `31 * 96 + 7 = 2983`.

Đổi thứ tự có thể đổi hash vì `Objects.hash("A", 7)` không có cùng mảng đối số với `Objects.hash(7, "A")`. Tuy vậy, không thể khẳng định mọi dãy đối số khác nhau luôn cho hash khác nhau: miền kết quả chỉ là `int` 32-bit và **hash collision được phép**.

### Ví dụ Java 17 chạy được

```java
import java.util.Arrays;
import java.util.Objects;

public class ObjectsHashBasics {
    public static void main(String[] args) {
        System.out.println(Objects.hash("A", 7));
        System.out.println(
                Objects.hash("A", 7)
                == Arrays.hashCode(new Object[] {"A", 7})
        );
        System.out.println(Objects.hash("A"));
        System.out.println("A".hashCode());
        System.out.println(Objects.hash());
    }
}
```

Lưu thành `ObjectsHashBasics.java` rồi chạy:

```bash
javac ObjectsHashBasics.java
java ObjectsHashBasics
```

Kết quả:

```text
2983
true
96
65
1
```

Giải thích: `Objects.hash("A")` không đơn thuần trả `"A".hashCode()`. Nó tính `Arrays.hashCode` trên mảng varargs có **một** phần tử `"A"`, nên kết quả là `31 + 65 = 96`. Không có đối số thì mảng varargs rỗng và kết quả là `1`.

Nếu chỉ muốn lấy hash của **một object riêng lẻ**, `Objects.hashCode(value)` thường rõ ý định hơn `Objects.hash(value)`. Phương thức `Objects.hashCode(Object)` trả `0` nếu giá trị là `null`, còn không thì trả `value.hashCode()`. Hai overload này không có cùng công thức chung.

## 3. Truyền Object[]: trải thành các phần tử hay coi cả mảng là một object?

Đây là tình huống dễ nhầm nhất của `Objects.hash`.

Cho:

```java
String[] codes = {"A", "B"};
```

`String[]` là một kiểu con của `Object[]`. Bởi vậy, khi gọi `Objects.hash(codes)`, compiler có thể chọn lời gọi varargs ở **dạng không đóng gói thêm mảng**, sử dụng chính `codes` làm mảng đối số. Trình biên dịch Java thường cảnh báo khi một lời gọi như vậy dễ gây nhầm về varargs.

Hãy dùng cast để nói rõ ý muốn:

- `Objects.hash((Object[]) codes)`: coi `codes` là **mảng varargs**; hash các phần tử `"A"` và `"B"`.
- `Objects.hash((Object) codes)`: coi **nguyên đối tượng mảng** là một đối số; mã băm dùng `codes.hashCode()`, tức hash theo identity của mảng.
- `Arrays.hashCode(codes)`: trực tiếp hash nội dung mảng tham chiếu một chiều; với hai chuỗi ví dụ sẽ tương ứng với trường hợp trải mảng.

Vì `String.hashCode` cho `"A"` là `65` và `"B"` là `66`, kết quả khi trải mảng sẽ là `31 * (31 + 65) + 66 = 3042`.

### Ví dụ chứng minh hai cách truyền khác nhau

```java
import java.util.Arrays;
import java.util.Objects;

public class ObjectArrayVarargsDemo {
    public static void main(String[] args) {
        String[] codes = {"A", "B"};

        int byElements = Objects.hash("A", "B");
        int byArrayAsVarargs = Objects.hash((Object[]) codes);
        int byOneArrayObject = Objects.hash((Object) codes);

        System.out.println(byElements);
        System.out.println(byArrayAsVarargs);
        System.out.println(byArrayAsVarargs == Arrays.hashCode(codes));
        System.out.println(
                byOneArrayObject == 31 + System.identityHashCode(codes)
        );
        System.out.println(
                byArrayAsVarargs == Objects.hash("A", "B")
        );
    }
}
```

Lưu `ObjectArrayVarargsDemo.java` rồi chạy:

```bash
javac ObjectArrayVarargsDemo.java
java ObjectArrayVarargsDemo
```

Đầu ra:

```text
3042
3042
true
true
true
```

Dòng thứ tư là `true` vì `codes` là mảng Java, `codes.hashCode()` có ngữ nghĩa identity hash như `System.identityHashCode(codes)`, và hash của **một** phần tử trong `Object[]` là `31 + elementHash` (với quy tắc tràn `int` thông thường).

Không in `byOneArrayObject` thành một hằng số mong đợi: giá trị identity hash của mảng không được đặc tả cụ thể và có thể thay đổi giữa các lần chạy. Hai cách truyền có **ngữ nghĩa khác nhau**, dù trong trường hợp hiếm hoi vẫn có thể cho cùng số do va chạm hash.

Điều quan trọng không phải thuộc lòng một giá trị số mà là hiểu **cấu trúc mảng varargs compiler đã truyền cho phương thức**.

## 4. Mảng nguyên thủy: int[] không tự trải thành Object...

`int[]` là một object trong Java, nhưng **không phải** kiểu con của `Object[]`. Vì vậy lời gọi:

```java
int[] numbers = {1, 2};
int hash = Objects.hash(numbers);
```

được hiểu như băm **một đối số là chính mảng `numbers`**, không phải hai đối số `Integer.valueOf(1)` và `Integer.valueOf(2)`.

Mảng `int[]` không override `Object.hashCode` để hash nội dung, nên `Objects.hash(numbers)` dựa vào identity hash của mảng. Muốn hash **nội dung một chiều của mảng nguyên thủy**, hãy dùng:

`Arrays.hashCode(numbers)`

Ví dụ, `Arrays.hashCode(new int[]{1, 2})` là `994`, vì tính `31 * (31 * 1 + 1) + 2`.

### Ví dụ đối chiếu hai mục đích

```java
import java.util.Arrays;
import java.util.Objects;

public class PrimitiveArrayHashDemo {
    public static void main(String[] args) {
        int[] data = {1, 2};

        System.out.println(Arrays.hashCode(data));
        System.out.println(
                Objects.hash(data)
                == 31 + System.identityHashCode(data)
        );
        System.out.println(
                Objects.hash((Object) data)
                == Objects.hash(data)
        );
        System.out.println(Objects.hash(Arrays.hashCode(data)));
        System.out.println(Objects.hash(1, 2));
    }
}
```

Lưu `PrimitiveArrayHashDemo.java` rồi chạy:

```bash
javac PrimitiveArrayHashDemo.java
java PrimitiveArrayHashDemo
```

Kết quả:

```text
994
true
true
1025
994
```

Kết quả `1025` giải thích thêm một bẫy: `Objects.hash(Arrays.hashCode(data))` băm **một giá trị int đã được boxing**, nên tạo `31 + 994 = 1025`, thay vì trả nguyên `994`. Nó vẫn là một hàm hash có thể hợp lệ nếu được dùng nhất quán, nhưng không đồng nghĩa về công thức với `Arrays.hashCode(data)`.

Dòng cuối `Objects.hash(1, 2)` cũng cho `994`, do hai phần tử đóng góp hash lần lượt `1` và `2`. Đây là sự trùng nhau **theo đúng công thức áp dụng cho hai chuỗi phần tử số**, không chứng minh `Objects.hash(data)` tự trải `int[]`.

## 5. Null và lời gọi một đối số: cast rất quan trọng

Vì kiểu khai báo là `Object...`, một lời gọi với `null` có thể diễn giải ở hai cấp: **mảng varargs là `null`** hoặc **mảng varargs có một phần tử `null`**.

| Cách gọi | Mảng đối số mà Objects.hash nhận | Kết quả |
| --- | --- | --- |
| `Objects.hash()` | Mảng `Object[]` rỗng | `1` |
| `Objects.hash((Object) null)` | Mảng một phần tử `[null]` | `31` |
| `Objects.hash((Object[]) null)` | Chính mảng varargs là `null` | `0` |
| `Objects.hash("A")` | Mảng một phần tử `["A"]` | `96` |
| `Objects.hashCode(null)` | Một object `null` | `0` |

Kết quả `0` của trường hợp mảng varargs `null` đến từ `Arrays.hashCode((Object[]) null)`. Khi có một phần tử `null`, thuật toán bắt đầu từ `1` rồi tính `31 * 1 + 0 = 31`.

Việc gọi thẳng `Objects.hash(null)` không truyền tải rõ ý định, có thể gây cảnh báo compiler vì biểu thức `null` phù hợp với nhiều cách hiểu của varargs. Nên ép kiểu tường minh khi cần phân biệt hai trường hợp; trong mã ứng dụng, tránh thiết kế phụ thuộc vào sự mơ hồ này.

Hãy phân biệt `null` là **một trường trong object** với `null` là **toàn bộ mảng đối số**. Nếu class của bạn dùng `Objects.hash(name, nullableCode)`, giá trị `nullableCode == null` chỉ đóng góp 0 cho phần tử tương ứng; đó không phải mảng varargs `null`.

## 6. Object[] có mảng lồng: không tự so sánh hoặc hash sâu

Xét:

```java
Object[] nested = {new int[] {1, 2}};
```

`Objects.hash((Object[]) nested)` đi qua các **phần tử cấp ngoài**. Nhưng phần tử duy nhất lại là một `int[]`, mà `hashCode()` của nó theo identity. Nó **không tự đi sâu** để băm hai số `1` và `2`.

Vì thế:

- `Arrays.hashCode(nested)`: tính hash cấp ngoài theo hash của từng phần tử; mảng con đóng góp identity hash.
- `Arrays.deepHashCode(nested)`: áp dụng quy tắc băm sâu với các mảng lồng, trong ví dụ này dùng nội dung `{1, 2}`.
- `Objects.hash((Object) nested)`: coi **toàn bộ mảng ngoài** là một giá trị, rồi dùng identity hash của chính mảng ngoài.

Tương tự với equality:

- `Arrays.equals(nestedA, nestedB)` so sánh từng phần tử cấp ngoài bằng `equals`; hai mảng con khác tham chiếu không tự bằng nhau.
- `Arrays.deepEquals(nestedA, nestedB)` hỗ trợ so sánh sâu nội dung mảng con.

Để kiểm tra ổn định sự khác biệt về ngữ nghĩa, không nên khẳng định hai giá trị hash phải khác nhau; collision là hợp lệ. Thay vào đó, dùng các điều kiện có bảo đảm:

```java
import java.util.Arrays;
import java.util.Objects;

public class NestedArrayHashDemo {
    public static void main(String[] args) {
        Object[] left = {new int[] {1, 2}};
        Object[] right = {new int[] {1, 2}};

        System.out.println(Arrays.equals(left, right));
        System.out.println(Arrays.deepEquals(left, right));
        System.out.println(
                Objects.hash((Object[]) left)
                == Arrays.hashCode(left)
        );
        System.out.println(
                Arrays.deepHashCode(left) == Arrays.deepHashCode(right)
        );
    }
}
```

Lưu `NestedArrayHashDemo.java` và chạy:

```bash
javac NestedArrayHashDemo.java
java NestedArrayHashDemo
```

Kết quả:

```text
false
true
true
true
```

Hai cấu trúc có nội dung sâu giống nhau nhưng mảng con là hai đối tượng riêng. `Arrays.deepHashCode` cho kết quả bằng nhau với hai cấu trúc sâu bằng nhau. `Objects.hash` không tự chuyển thành `deepHashCode` chỉ vì phần tử bên trong là mảng.

## 7. Dùng Objects.hash() trong equals/hashCode đúng cách

Nguyên tắc căn bản của `Object` là:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

Nếu một class so sánh theo nhiều trường, `Objects.hash` là lựa chọn tiện khi mọi trường có `hashCode()` phù hợp với cách `equals` của chính trường đó. Ví dụ với `String`, `Integer` và các value object bất biến có hợp đồng equality/hash đúng, mã thường rất gọn:

```java
@Override
public int hashCode() {
    return Objects.hash(countryCode, customerId);
}
```

Đây là ví dụ phương thức trong class có hai trường, không phải chương trình độc lập.

Nhưng có bẫy quan trọng khi các trường là **mảng**. Nếu `equals` dùng `Arrays.equals(data, other.data)` để so **nội dung**, còn `hashCode` trả `Objects.hash(data)` với `data` là `byte[]`, mã băm sẽ dựa theo identity mảng, **không tương thích chắc chắn** với equality theo nội dung.

Cách chuẩn cho một mảng đơn:

```java
@Override
public int hashCode() {
    return Arrays.hashCode(data);
}
```

Khi kết hợp với các trường khác, có thể đưa **hash nội dung của mảng** vào `Objects.hash` như một giá trị:

```java
@Override
public int hashCode() {
    return Objects.hash(type, Arrays.hashCode(data));
}
```

Đây là một chiến lược hợp lệ vì hai đối tượng cùng `type` và cùng nội dung `data` thì `type.hashCode()` và `Arrays.hashCode(data)` tương ứng cũng bằng nhau. Nhưng kết quả số **không bắt buộc giống** `Arrays.hashCode(data)` một mình, và phân bố/collision của hash là vấn đề riêng.

### Ví dụ Java 17 hoàn chỉnh: value object có trường mảng

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MixedFieldsHashDemo {
    record AttachmentKey(String kind, byte[] bytes) {
        public AttachmentKey {
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(bytes, "bytes");
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || other instanceof AttachmentKey that
                    && kind.equals(that.kind)
                    && Arrays.equals(bytes, that.bytes);
        }

        @Override
        public int hashCode() {
            return Objects.hash(kind, Arrays.hashCode(bytes));
        }
    }

    public static void main(String[] args) {
        byte[] source = {10, 20};
        AttachmentKey a = new AttachmentKey("image", source);
        AttachmentKey b = new AttachmentKey("image", new byte[] {10, 20});

        Set<AttachmentKey> keys = new HashSet<>();
        keys.add(a);

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(keys.contains(b));

        source[0] = 99;
        System.out.println(a.bytes()[0]);

        byte[] copied = a.bytes();
        copied[1] = 77;
        System.out.println(a.bytes()[1]);

        System.out.println(a.equals(b));
    }
}
```

Lưu `MixedFieldsHashDemo.java` rồi chạy:

```bash
javac MixedFieldsHashDemo.java
java MixedFieldsHashDemo
```

Kết quả:

```text
true
true
true
10
20
true
```

Ở đây `equals` xét `kind` theo equality của chuỗi và `bytes` theo nội dung từng byte. `hashCode` sử dụng `Objects.hash(kind, Arrays.hashCode(bytes))` để kết hợp các giá trị phù hợp với cùng quy tắc.

Constructor copy mảng đầu vào, accessor trả bản sao, nên caller không dễ làm thay đổi mảng định nghĩa equality sau khi object được thêm vào `HashSet`. Với mảng nhiều chiều, sao chép mảng ngoài đơn thuần sẽ không bảo vệ các mảng con; cần thiết kế deep copy tương ứng.

**Lưu ý:** Generated `equals`/`hashCode` mặc định của một record chứa mảng không tự so sánh/hash theo nội dung mảng. Vì vậy ví dụ đã override cả hai phương thức. Chỉ override `equals` theo nội dung mà để `hashCode` theo identity có thể phá hợp đồng với `HashSet`/`HashMap`.

## 8. Đâu là cách chọn phương thức hash cho mảng?

| Mục đích | Công cụ thường phù hợp | Cần nhớ |
| --- | --- | --- |
| Băm nhiều giá trị độc lập | `Objects.hash(a, b, c)` | Varargs là một `Object[]` |
| Băm một object, có thể `null` | `Objects.hashCode(obj)` | Với `null` trả 0; với array vẫn là hash identity |
| Băm nội dung `int[]`, `byte[]` một chiều | `Arrays.hashCode(array)` | Không dùng `Objects.hash(array)` nếu muốn nội dung |
| Băm nội dung `String[]` một chiều | `Arrays.hashCode(array)` | `Objects.hash((Object[]) array)` có cùng kết quả nhưng dễ gây nhầm |
| Băm nội dung mảng lồng | `Arrays.deepHashCode(array)` | Ghép với `Arrays.deepEquals` theo đúng cấu trúc |
| Kết hợp String và mảng theo nội dung | `Objects.hash(name, Arrays.hashCode(array))` | Equality cũng phải xét name và nội dung array |
| Cố ý băm identity của một mảng | `System.identityHashCode(array)` hoặc hash theo identity theo thiết kế | Không coi đó là content hash hay ID duy nhất |

`Objects.hash` không tự bảo đảm mọi giá trị hash là duy nhất, không phải thuật toán bảo mật, cũng không cam kết một giá trị ổn định giữa mọi lần chạy cho mọi kiểu object. Với yêu cầu checksum hoặc lưu trữ lâu dài, nên đặc tả thuật toán và biểu diễn dữ liệu riêng.

## 9. Hiệu năng và khả năng đọc mã

`Objects.hash(a, b, c)` tiện và dễ bảo trì, nhất là với class có một vài trường. Nhưng vì varargs tạo hoặc sử dụng một mảng `Object[]` và các giá trị nguyên thủy có thể cần boxing, nó có thể tạo thêm chi phí phân bổ bộ nhớ và tính toán.

Với mã được gọi rất thường xuyên trong đường nóng (*hot path*), có thể cân nhắc:

```java
@Override
public int hashCode() {
    int result = Integer.hashCode(id);
    result = 31 * result + name.hashCode();
    return result;
}
```

Đoạn này là phương thức minh họa trong class có `int id` và `String name` khác `null`. Một thuật toán phối hợp thủ công cũng có thể đúng nếu giữ yêu cầu bằng nhau thì cùng hash; Java **không bắt buộc** dùng `Objects.hash` hay hệ số 31 trong mọi class.

Không nên tối ưu khi chưa đo đạc. Đối với bài học cơ bản, **đúng ngữ nghĩa equality**, xử lý `null` và hiểu varargs quan trọng hơn việc tiết kiệm một lời gọi tiện ích. Nếu hiệu năng thực tế là vấn đề, hãy đo bằng công cụ benchmark phù hợp với JIT, khởi động và tải ứng dụng.

## 10. Các lỗi thường gặp và cách sửa

**Lỗi 1 — hiểu `Objects.hash(array)` luôn là content hash.** Với `int[]`, lời gọi xử lý mảng như một object; với `String[]`, nó có thể dùng mảng làm danh sách varargs. Cách sửa là nêu mục đích bằng `Arrays.hashCode(array)` khi cần hash nội dung một chiều.

**Lỗi 2 — bỏ qua cast khi truyền Object[].** `Objects.hash((Object[]) array)` và `Objects.hash((Object) array)` có hai ngữ nghĩa khác nhau. Hãy viết cast tường minh hoặc gọi trực tiếp `Arrays.hashCode` cho dễ đọc.

**Lỗi 3 — tưởng `Objects.hash(x) == x.hashCode()`.** Với một `x` bình thường khác `null`, `Objects.hash(x)` băm mảng một phần tử, theo công thức `31 + x.hashCode()`; `Objects.hashCode(x)` mới trả nguyên hash của object.

**Lỗi 4 — dùng `Objects.hash(data)` khi `equals` so nội dung byte[].** Phải chọn hash nội dung tương thích, như `Arrays.hashCode(data)`, và xử lý bất biến của mảng khi làm khóa.

**Lỗi 5 — chỉ xét mảng ngoài khi dữ liệu lồng nhiều cấp.** `Arrays.hashCode(Object[])` và `Objects.hash((Object[]) outer)` không tự deep-hash các mảng con. Nếu equality sâu, dùng `Arrays.deepEquals` cùng `Arrays.deepHashCode` theo mô hình phù hợp.

**Lỗi 6 — hiểu hash trùng nghĩa là object bằng nhau.** Hai object khác nhau được phép có cùng mã băm. Hash giúp tổ chức/tra cứu; `equals` mới là quy tắc nhận diện giá trị bằng nhau.

**Lỗi 7 — sửa mảng sau khi dùng object làm hash key.** Nếu hash/equality dựa trên nội dung mảng, sửa phần tử trong lúc object thuộc `HashSet` có thể khiến tra cứu không còn đáng tin. Ưu tiên defensive copy và dữ liệu định nghĩa equality bất biến.

## 11. Câu hỏi tự luyện

**Câu 1.** `Objects.hash("A")` có bằng `"A".hashCode()` không?

**Đáp án:** Không. Với `"A"`, hai số là `96` và `65`. `Objects.hash` băm một mảng varargs có một phần tử.

**Câu 2.** `String[] codes = {"A", "B"};`. Khác nhau giữa `Objects.hash((Object[]) codes)` và `Objects.hash((Object) codes)` là gì?

**Đáp án:** Cách đầu truyền chính mảng làm danh sách đối số, hash nội dung các phần tử cấp một; cách sau xem cả mảng như một Object duy nhất và dùng identity hash của mảng.

**Câu 3.** `Objects.hash(new int[]{1, 2})` có buộc bằng `Arrays.hashCode(new int[]{1, 2})` không?

**Đáp án:** Không. Mảng nguyên thủy được xử lý như một object duy nhất trong varargs và dùng identity hash; `Arrays.hashCode(int[])` tính theo nội dung mảng.

**Câu 4.** Tại sao `Objects.hash(Arrays.hashCode(data))` có thể khác `Arrays.hashCode(data)`?

**Đáp án:** Vì băm **một giá trị int** còn thêm bước `31 + valueHash`. Với `data = {1, 2}`, kết quả tương ứng là `1025` và `994`.

**Câu 5.** Hai object có mảng khác tham chiếu nhưng cùng nội dung được `equals` xem là bằng nhau. `hashCode` nên chọn cách nào?

**Đáp án:** Phải tính hash từ cùng nội dung mà equality xét, ví dụ `Arrays.hashCode` cho mảng nguyên thủy một chiều, hoặc `Objects.hash(type, Arrays.hashCode(data))` nếu có thêm trường khác. Đồng thời kiểm soát việc mảng có thể thay đổi.

**Câu 6.** Với `Object[] outer = {new int[]{1, 2}};`, `Objects.hash((Object[]) outer)` có băm sâu hai số nguyên không?

**Đáp án:** Không. Phần tử cấp ngoài là mảng `int[]` và đóng góp identity hash. Nếu muốn băm sâu cấu trúc lồng, cân nhắc `Arrays.deepHashCode(outer)`.

**Câu 7.** Vì sao kết quả `Objects.hash((Object[]) null)` khác `Objects.hash((Object) null)`?

**Đáp án:** Trường hợp đầu truyền mảng varargs `null` và cho `0`; trường hợp sau tạo một mảng chứa đúng một phần tử `null` và cho `31`.

## 12. Ghi nhớ

1. `Objects.hash(Object... values)` tương đương `Arrays.hashCode` trên **mảng varargs thực tế**.
2. `Objects.hash(a, b)` băm hai phần tử theo thứ tự; `Objects.hash(a)` **không nhất thiết** bằng `Objects.hashCode(a)` hoặc `a.hashCode()`.
3. `Object[]` (ví dụ `String[]`) có thể được truyền **trực tiếp làm mảng varargs**; cast `(Object[])` và `(Object)` biểu đạt hai ý nghĩa khác nhau.
4. `int[]` và các mảng nguyên thủy **không phải** `Object[]`; `Objects.hash(primitiveArray)` băm identity của mảng, không băm phần tử.
5. Cần **content hash** thì dùng `Arrays.hashCode` (một chiều) hoặc `Arrays.deepHashCode` (lồng), đi cùng equality tương ứng.
6. Với class có nhiều trường gồm mảng, có thể kết hợp `Objects.hash(name, Arrays.hashCode(array))` nếu `equals` cũng xét name và nội dung mảng.
7. Bảo đảm hợp đồng `equals`/`hashCode` và tính ổn định của khóa quan trọng hơn hình thức viết hash ngắn hay dài.

Tài liệu chính thức: [`Objects.hash` / `Objects.hashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html), [`Arrays.hashCode` và `Arrays.deepHashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), [`Object.equals/hashCode` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).
