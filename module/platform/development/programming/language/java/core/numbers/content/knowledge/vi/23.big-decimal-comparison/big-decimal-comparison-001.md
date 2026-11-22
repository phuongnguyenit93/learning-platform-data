# BigDecimal.compareTo(): so sánh giá trị số trong Java

## 1. Vấn đề cần giải quyết

Trong Java, `BigDecimal` lưu giá trị thập phân có độ chính xác tùy ý bằng một **số nguyên không có scale** (`unscaledValue`) và một **scale** (số mũ thập phân âm). Giá trị toán học có thể hình dung là `unscaledValue × 10^(-scale)`. Cùng một số có thể mang những cách biểu diễn khác nhau:

- `new BigDecimal("2.0")`: giá trị số 2; unscaled value 20; scale 1.
- `new BigDecimal("2.00")`: giá trị số 2; unscaled value 200; scale 2.
- `new BigDecimal("2")`: giá trị số 2; unscaled value 2; scale 0.

Khi cần trả lời “giá trị nào lớn hơn?”, “có bằng nhau về **giá trị số** không?” hoặc “số này đã vượt ngưỡng chưa?”, dùng **`BigDecimal.compareTo(BigDecimal other)`**. Phương thức so sánh **giá trị số**, nên coi `2.0`, `2.00` và `2` ngang nhau về thứ tự, dù scale khác nhau.

Đây là điểm khác biệt quan trọng so với `equals(Object)`, vốn xét cả giá trị số lẫn scale. Chọn đúng phép so sánh giúp tránh lỗi khi dữ liệu đến từ những nguồn có định dạng thập phân không đồng nhất.

## 2. Cách đọc kết quả compareTo

Cú pháp:

~~~java
int result = left.compareTo(right);
~~~

Kết quả có ba nhóm ý nghĩa:

| Điều kiện | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `result < 0` | `left` nhỏ hơn `right` | `1.25` so với `1.30` |
| `result == 0` | Hai đối tượng có **cùng giá trị số** | `2.0` so với `2.00` |
| `result > 0` | `left` lớn hơn `right` | `9.5` so với `9.05` |

Hợp đồng của `Comparable.compareTo` yêu cầu kết quả **âm, 0 hoặc dương**; khi kiểm tra điều kiện, viết `< 0` hoặc `> 0`, không phụ thuộc vào việc phương thức trả chính xác `-1` hay `1`.

Hướng so sánh theo **trục số có dấu**:

- `-8.0 < -2.00` vì -8 nằm bên trái -2.
- `-0.001 < 0` dù giá trị tuyệt đối rất nhỏ.
- `0.000` và `0` bằng nhau về giá trị số.
- `10.00 > 9.999` dù số phía phải có nhiều chữ số thập phân hơn.

**Scale không quyết định số lớn hay nhỏ.** Không thể so sánh hai `BigDecimal` bằng cách lấy scale, độ dài chuỗi, số chữ số thập phân hay lexicographical ordering.

## 3. Ví dụ Java 17 chạy được

Lưu đoạn sau thành tệp `BigDecimalCompareDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalCompareDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("equals = " + a.equals(b));
        System.out.println("scales = " + a.scale() + ", " + b.scale());

        BigDecimal negative = new BigDecimal("-1.25");
        System.out.println("negative < zero = "
                + (negative.compareTo(BigDecimal.ZERO) < 0));
        System.out.println("3.50 > 3.05 = "
                + (new BigDecimal("3.50")
                        .compareTo(new BigDecimal("3.05")) > 0));
        System.out.println("1.20 < 1.3 = "
                + (new BigDecimal("1.20")
                        .compareTo(new BigDecimal("1.3")) < 0));

        List<BigDecimal> values = new ArrayList<>(List.of(
                new BigDecimal("10.0"),
                new BigDecimal("2.00"),
                new BigDecimal("-1.2"),
                new BigDecimal("2.0")
        ));
        values.sort(BigDecimal::compareTo);
        System.out.println("sorted = " + values);

        Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
        Set<BigDecimal> treeSet = new TreeSet<>(List.of(a, b));
        System.out.println("HashSet size = " + hashSet.size());
        System.out.println("TreeSet size = " + treeSet.size());

        BigDecimal representedZero = new BigDecimal("0.000");
        System.out.println("numeric zero = "
                + (representedZero.compareTo(BigDecimal.ZERO) == 0));
        System.out.println("normalized b = "
                + b.stripTrailingZeros().toPlainString());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac BigDecimalCompareDemo.java
java BigDecimalCompareDemo
~~~

Kết quả:

~~~text
compareTo = 0
equals = false
scales = 1, 2
negative < zero = true
3.50 > 3.05 = true
1.20 < 1.3 = true
sorted = [-1.2, 2.00, 2.0, 10.0]
HashSet size = 2
TreeSet size = 1
numeric zero = true
normalized b = 2
~~~

Giải thích theo từng nhóm:

1. `a.compareTo(b) == 0`: `2.0` và `2.00` có cùng **giá trị số**.
2. `a.equals(b) == false`: hai đối tượng biểu diễn cùng số 2 nhưng có scale lần lượt là 1 và 2.
3. Các so sánh âm/dương dùng `< 0` hoặc `> 0`, không cần đổi sang `double`.
4. `values.sort(BigDecimal::compareTo)` sắp xếp tăng theo số. Hai phần tử `2.00` và `2.0` có thứ tự bằng nhau theo comparator; `List.sort` ổn định nên giữ thứ tự tương đối ban đầu của chúng.
5. `HashSet` coi `2.0` và `2.00` là hai phần tử khác nhau dựa trên `equals` và `hashCode`; `TreeSet` dùng thứ tự tự nhiên do `compareTo` và coi chúng trùng nhau.
6. `stripTrailingZeros()` đưa `2.00` về biểu diễn không có số 0 thừa; `toPlainString()` in thành `2`. Thao tác này không sửa `b` vì `BigDecimal` là immutable.

## 4. compareTo và equals: khác nhau ở đâu?

Hai phương thức giải quyết hai câu hỏi khác nhau:

| Phương thức | Câu hỏi | `2.0` và `2.00` |
| --- | --- | --- |
| `compareTo` | Hai số lớn, nhỏ hay **bằng nhau về mặt số học**? | `compareTo(...) == 0` |
| `equals` | Hai `BigDecimal` có cùng giá trị và cùng **scale** không? | `equals(...) == false` |
| `hashCode` | Mã băm tuân theo quy ước bằng nhau của `equals`? | Có thể khác; không dùng mã băm để so sánh số |

Với `BigDecimal`, `equals` chỉ trả true nếu số được biểu diễn có giá trị bằng nhau **và scale bằng nhau**; `compareTo` không yêu cầu cùng scale. Điều này được Java ghi rõ: natural ordering của `BigDecimal` **không nhất quán với `equals`** (`inconsistent with equals`).

~~~java
BigDecimal priceA = new BigDecimal("19.9");
BigDecimal priceB = new BigDecimal("19.90");

boolean sameNumericValue = priceA.compareTo(priceB) == 0; // true
boolean sameRepresentation = priceA.equals(priceB);         // false
~~~

Đừng thay `compareTo` bằng `equals` chỉ vì đang cần kiểm tra hai **số** có bằng nhau hay không. Ngược lại, khi yêu cầu của chương trình coi scale là một phần quan trọng của thông tin (ví dụ kiểm tra đối tượng có đúng biểu diễn cần lưu hay không), `equals` có thể là lựa chọn chủ ý.

### Một trường hợp dễ ngạc nhiên khi thao tác

Cùng một số có thể cho kết quả `divideToIntegralValue` hay các phép toán dựa vào biểu diễn với scale đầu ra khác nhau tùy scale toán hạng. Thế nên “`compareTo == 0`” **không đảm bảo mọi thao tác trên hai đối tượng sẽ tạo ra kết quả có cùng scale**. Không suy diễn từ bằng nhau về giá trị số thành đồng nhất về biểu diễn.

## 5. So sánh với 0, ngưỡng và khoảng

`BigDecimal.ZERO` là hằng số biểu diễn số 0; so sánh với nó rõ ràng và tránh tạo đối tượng không cần thiết.

~~~java
BigDecimal balance = new BigDecimal("-0.01");

boolean isNegative = balance.compareTo(BigDecimal.ZERO) < 0;
boolean isZero = balance.compareTo(BigDecimal.ZERO) == 0;
boolean isPositive = balance.compareTo(BigDecimal.ZERO) > 0;
~~~

Các phép so sánh thường gặp:

| Yêu cầu | Biểu thức |
| --- | --- |
| `x < y` | `x.compareTo(y) < 0` |
| `x <= y` | `x.compareTo(y) <= 0` |
| `x == y` theo giá trị số | `x.compareTo(y) == 0` |
| `x >= y` | `x.compareTo(y) >= 0` |
| `x > y` | `x.compareTo(y) > 0` |
| `x != y` theo giá trị số | `x.compareTo(y) != 0` |

Ví dụ chấp nhận đơn hàng nếu số tiền đạt tối thiểu `100.00`:

~~~java
BigDecimal amount = new BigDecimal("100.0");
BigDecimal minimum = new BigDecimal("100.00");

if (amount.compareTo(minimum) >= 0) {
    System.out.println("Đạt ngưỡng");
}
~~~

Kết quả là `Đạt ngưỡng` vì giá trị số bằng nhau, dù scale khác nhau. Nếu cần kiểm tra khoảng đóng `[min, max]`, dùng:

~~~java
boolean inRange = value.compareTo(min) >= 0
        && value.compareTo(max) <= 0;
~~~

Đây là các **mảnh code minh họa**, với biến `value`, `min`, `max` được giả định đã là `BigDecimal` không null và khoảng `min <= max`. Để thực sự chạy, đặt các mảnh này vào phương thức hoặc chương trình khai báo đủ biến.

## 6. Sắp xếp và collection: hậu quả của sự khác biệt

`BigDecimal` triển khai `Comparable<BigDecimal>`, vì thế Java dùng `compareTo` làm **thứ tự tự nhiên**:

~~~java
List<BigDecimal> values = new ArrayList<>(List.of(
        new BigDecimal("9.00"),
        new BigDecimal("1.1"),
        new BigDecimal("1.10")
));
values.sort(BigDecimal::compareTo);
~~~

Kết quả được sắp tăng theo giá trị số: `[1.1, 1.10, 9.00]`. Hai giá trị `1.1` và `1.10` có `compareTo == 0` nên không có thứ tự số học khác nhau; một sort ổn định giữ thứ tự của chúng như trước khi sắp.

Tuy nhiên, **collection nào quyết định “trùng” theo cách nào** rất quan trọng:

- `HashSet<BigDecimal>` và `HashMap<BigDecimal, ...>` dựa vào `equals` và `hashCode` của khóa. `new BigDecimal("2.0")` khác `new BigDecimal("2.00")` theo tiêu chí này, nên hai khóa có thể cùng tồn tại.
- `TreeSet<BigDecimal>` và `TreeMap<BigDecimal, ...>` theo thứ tự tự nhiên dùng `compareTo` (hoặc comparator được cung cấp) để nhận diện hai khóa có cùng vị trí so sánh. `2.0` và `2.00` được xem là cùng một khóa, vì `compareTo == 0`.
- Nếu `TreeMap` được đưa khóa `2.00` sau khi đã chứa `2.0`, giá trị được ghi vào mục khóa có sẵn theo tiêu chí comparator; đừng mong tự động giữ hai mục độc lập.
- `Stream.distinct()` dùng `equals`, nên riêng thao tác này vẫn có thể giữ cả hai cách biểu diễn `2.0` và `2.00`. Sắp xếp bằng `compareTo` trước đó không tự đổi quy tắc `distinct()`.

Nếu nghiệp vụ coi các số thập phân cùng giá trị là cùng một danh tính, hãy xác định cách **chuẩn hóa** khóa trước khi dùng collection theo `equals`, hoặc chọn `TreeMap`/`TreeSet` theo comparator phù hợp. Tránh trộn lẫn nhiều quy tắc định danh mà không mô tả rõ.

### Chuẩn hóa số 0 cuối

`stripTrailingZeros()` trả về một `BigDecimal` tương đương về số học với các chữ số 0 cuối trong phần unscaled value đã được lược bỏ:

~~~java
BigDecimal first = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal second = new BigDecimal("2.00").stripTrailingZeros();

System.out.println(first.equals(second)); // true
~~~

Lưu ý:

- Chuẩn hóa không mất **giá trị số**, nhưng có thể làm đổi **scale** và dạng hiển thị.
- Ví dụ `new BigDecimal("600.0").stripTrailingZeros()` có thể biểu diễn thành `6E+2` với scale âm, thay vì chuỗi `600.0`. `toPlainString()` dùng khi cần cách in không có số mũ.
- `stripTrailingZeros()` của giá trị số 0 trả về biểu diễn zero chuẩn, có thể làm mất scale ban đầu của `0.000`.
- Nếu scale cố định là điều kiện nghiệp vụ hoặc hợp đồng dữ liệu, không tự chuẩn hóa mọi số mà chưa đánh giá tác động. Khi dữ liệu bắt buộc có scale 2, `setScale(2)` chỉ thành công không cần rounding mode nếu có thể đạt scale 2 mà **không làm tròn**; các giá trị khác có thể cần quy tắc làm tròn rõ ràng.

## 7. Dữ liệu đầu vào và tính chính xác

Hãy tạo `BigDecimal` từ dữ liệu thập phân chính xác như chuỗi JSON hoặc chuỗi nhập vào:

~~~java
BigDecimal expected = new BigDecimal("0.3");
BigDecimal actual = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

System.out.println(actual.compareTo(expected) == 0); // true
~~~

Nếu thay bằng `double` trước, các giá trị thập phân như `0.1` và `0.2` thường không biểu diễn chính xác được ở nhị phân dấu phẩy động. `BigDecimal.valueOf(double)` chuyển từ chuỗi thập phân chuẩn của giá trị `double`, hữu ích khi đầu vào đã ở dạng đó; nhưng không thể khôi phục độ chính xác đã mất do tính toán trước đó trong `double`.

Không nên dùng:

~~~java
double x = 0.1 + 0.2;
double y = 0.3;
boolean equal = (x == y); // Thường là false do biểu diễn nhị phân.
~~~

Trường hợp này minh họa riêng cho `double`. Với `BigDecimal` xây từ chuỗi và phép cộng chính xác không có `MathContext`, phép so sánh số học cho kết quả đúng như ví dụ ở trên.

Về nguyên tắc, `compareTo` **không làm tròn** hai số để so sánh và không yêu cầu hai bên có cùng scale. Nếu muốn so sánh các số *sau* khi đã được làm tròn theo quy tắc nghiệp vụ, phải làm tròn từng giá trị trước, rồi gọi `compareTo`; đó là một yêu cầu khác với so sánh giá trị gốc.

## 8. Các lưu ý khi thiết kế API

### Null không phải giá trị số

`BigDecimal` là lớp tham chiếu. Nếu đối tượng gọi phương thức là `null`, biểu thức `amount.compareTo(other)` gây `NullPointerException`; truyền `null` làm đối số so sánh cũng gây `NullPointerException`. Xử lý null theo hợp đồng dữ liệu trước khi so sánh:

~~~java
if (amount == null || minimum == null) {
    throw new IllegalArgumentException("Thiếu giá trị tiền");
}
boolean accepted = amount.compareTo(minimum) >= 0;
~~~

Đoạn trên là ví dụ kiểm tra đầu vào, với `amount` và `minimum` được cung cấp từ nơi khác.

### BigDecimal là immutable

`compareTo` chỉ **quan sát thứ tự** giữa hai giá trị, không sửa `BigDecimal` nào. Các phương thức như `stripTrailingZeros`, `setScale`, `add` cũng trả đối tượng kết quả mới (hoặc đối tượng có thể tái dùng) mà không thay đổi giá trị của đối tượng nhận.

### Không dùng toán tử < hoặc >

Toán tử `<`, `>`, `<=`, `>=` hoạt động trên kiểu số nguyên thủy và các phép chuyển kiểu thích hợp; chúng **không** được overload cho `BigDecimal`. Viết `a > b` với hai tham chiếu `BigDecimal` là lỗi biên dịch. Dùng `a.compareTo(b) > 0`.

### Không lấy chênh lệch rồi chuyển sang int để so sánh

Biểu thức kiểu `a.subtract(b).intValue()` có thể trả 0 dù hai số không bằng nhau hoặc làm mất thông tin do cắt phần thập phân/vượt khoảng kiểu int. `compareTo` diễn đạt trực tiếp mục đích, tránh phép tính trung gian không cần thiết.

### Thứ tự có tính bắc cầu

Nếu `a.compareTo(b) < 0` và `b.compareTo(c) < 0` thì `a.compareTo(c) < 0`. Đây là phần thiết yếu của hợp đồng so sánh, cho phép dùng với sắp xếp và cấu trúc dữ liệu có thứ tự. Khi viết comparator riêng để thay thế, hãy giữ tính đối xứng về dấu và bắc cầu; tránh comparator dựa trên `doubleValue()` nếu điều đó làm mất phân biệt giữa hai giá trị `BigDecimal` rất gần hoặc rất lớn.

## 9. Lỗi phổ biến và cách sửa

**Lỗi: dùng `equals` cho hai số nhập với scale không đồng nhất.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false. Nếu chỉ muốn biết hai số bằng nhau, dùng `compareTo(...) == 0`.

**Lỗi: so sánh qua `toString()`.** `"10.0".compareTo("2.0") < 0` do so chuỗi theo ký tự, dù 10.0 lớn hơn 2.0. Luôn dùng `BigDecimal.compareTo` cho thứ tự số học.

**Lỗi: tưởng `compareTo == 0` có nghĩa là `equals == true`.** Đây là nguyên nhân kết quả khác nhau giữa `HashSet` và `TreeSet`. Hãy chọn tiêu chí định danh, tập hợp và chuẩn hóa cho nhất quán.

**Lỗi: viết `compareTo(...) == 1`.** Tốt nhất so `> 0` hoặc `< 0` theo hợp đồng của `Comparable`; điều này cũng đúng với comparator tùy chỉnh.

**Lỗi: đổi sang `double` hoặc `long` để so sánh.** Việc chuyển kiểu có thể gây mất độ chính xác, cắt phần thập phân hoặc vượt phạm vi. `BigDecimal.compareTo` giữ nguyên miền số thập phân có độ chính xác tùy ý.

**Lỗi: mặc định null bằng 0.** Null là trạng thái không có dữ liệu, khác với `BigDecimal.ZERO`. Chỉ chuyển null thành 0 nếu đặc tả ứng dụng cho phép.

**Lỗi: sắp xếp rồi dùng `distinct()` để gộp các số bằng nhau.** `distinct()` vẫn dựa trên `equals`; `2.0` và `2.00` có thể cùng tồn tại sau thao tác đó.

## 10. Câu hỏi tự kiểm tra

Trước khi chạy thử, hãy xác định dấu của `left.compareTo(right)`:

| left | right | Dấu của kết quả | `left.equals(right)` |
| --- | --- | --- | --- |
| `3.0` | `3.00` | `0` | `false` |
| `-3.00` | `-2.99` | `< 0` | `false` |
| `0.000` | `0` | `0` | `false` |
| `0.100` | `0.10` | `0` | `false` |
| `100.01` | `100.001` | `> 0` | `false` |
| `7.00` | `7.00` | `0` | `true` |

Để thực hành, tự viết biểu thức xác định “âm”, “dương”, “bằng 0”, “ít nhất bằng ngưỡng” và thử nhập các chuỗi có khác biệt ở số 0 cuối. Sau đó đưa hai số `2.0`, `2.00` vào `HashSet` và `TreeSet` để tự quan sát khác biệt.

**Ghi nhớ:** `BigDecimal.compareTo` là phép so sánh **theo giá trị số**; kết quả âm/0/dương biểu thị nhỏ hơn/bằng/lớn hơn. Khi cần bằng nhau về số học, dùng `compareTo(other) == 0`. `equals` còn quan tâm đến scale, vì vậy lựa chọn giữa hai phương thức ảnh hưởng trực tiếp đến collection, khóa và logic ứng dụng.
