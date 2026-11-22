# Quy tắc null, NaN, +0.0 và -0.0 khi so sánh mảng

## 1. Vì sao cần phân biệt các quy tắc so sánh?

Khi so sánh mảng trong Java, kết quả phụ thuộc vào API được chọn và kiểu dữ liệu bên trong mảng. Có ba lớp hành vi thường bị nhầm lẫn:

- **Tham chiếu mảng:** hai biến có cùng trỏ đến một object mảng hay không.
- **Nội dung mảng:** các phần tử tương ứng có bằng nhau theo quy tắc của kiểu phần tử hay không.
- **Giá trị số thực:** các giá trị `NaN`, `+0.0` và `-0.0` được xem là bằng nhau như thế nào.

`null` cũng có hai vị trí khác nhau: bản thân tham chiếu mảng có thể là null, và mảng kiểu tham chiếu như `Double[]` có thể chứa phần tử null. Mảng kiểu nguyên thủy như `double[]` không thể chứa null.

Để so sánh chính xác, cần chọn đúng giữa `Objects.equals`, `Objects.deepEquals`, `Arrays.equals`, `Arrays.deepEquals`, `Double.equals` và `Double.compare`.

## 2. Quy tắc null: tham chiếu mảng và phần tử mảng

### So sánh hai tham chiếu có thể null

`Objects.equals(a, b)` xử lý null trước:

- Cả hai tham chiếu null: trả về `true`.
- Chỉ một tham chiếu null: trả về `false`.
- Cả hai khác null: gọi `a.equals(b)`.

Với mảng, `equals` kế thừa từ `Object`, nên không so sánh nội dung. Hai mảng khác object vẫn không bằng nhau dù chứa cùng các phần tử.

```java
int[] first = {1, 2};
int[] second = {1, 2};

System.out.println(Objects.equals(null, null)); // true
System.out.println(Objects.equals(first, second)); // false
System.out.println(Objects.equals(first, first)); // true
```

Nếu muốn so sánh nội dung, hãy dùng `Arrays.equals` hoặc `Objects.deepEquals` tùy cấu trúc mảng.

### null ở cấp mảng với Arrays.equals

Các overload của `Arrays.equals` xử lý tham chiếu mảng null theo cùng nguyên tắc:

- Hai mảng null: `true`.
- Một mảng null, một mảng khác null: `false`.
- Hai mảng khác null: so sánh độ dài và các phần tử tương ứng.

Ví dụ:

```java
double[] missingA = null;
double[] missingB = null;
double[] empty = {};

System.out.println(Arrays.equals(missingA, missingB)); // true
System.out.println(Arrays.equals(missingA, empty));    // false
```

Mảng null khác với mảng rỗng. Mảng rỗng là một object có độ dài bằng 0; null không trỏ đến object mảng nào.

### null ở bên trong mảng kiểu tham chiếu

`Double[]` có thể chứa null, vì mỗi phần tử là một tham chiếu. Khi dùng `Arrays.equals` trên hai `Double[]`, hai phần tử null ở cùng vị trí được xem là bằng nhau; một phần tử null và một phần tử khác null không bằng nhau.

```java
Double[] first = {null, 1.0};
Double[] second = {null, 1.0};

System.out.println(Arrays.equals(first, second)); // true
```

Ngược lại, `double[]` chứa giá trị số nguyên thủy và không thể chứa null. Nếu dữ liệu có trạng thái “không có số”, phải chọn một cách biểu diễn phù hợp như `Double[]`, một kiểu dữ liệu miền riêng hoặc một giá trị sentinel được định nghĩa rõ ràng.

## 3. Objects.equals không so sánh nội dung mảng

`Objects.equals` là tiện ích so sánh null-safe cho object. Nó không tự biến so sánh mảng thành so sánh nội dung.

```java
String[] left = {"Java", "9"};
String[] right = {"Java", "9"};

System.out.println(Objects.equals(left, right)); // false
System.out.println(Objects.equals(left, left));  // true
```

Kết quả đầu là false vì `left` và `right` là hai object mảng khác nhau. Để so sánh một chiều nội dung, dùng `Arrays.equals(left, right)`. Với mảng lồng nhau, cần xem xét `Arrays.deepEquals` hoặc `Objects.deepEquals`.

## 4. Arrays.equals và deepEquals khác nhau thế nào?

### Arrays.equals: so sánh một cấp

`Arrays.equals` có overload cho mảng nguyên thủy và mảng object. Nó kiểm tra độ dài rồi so sánh các phần tử ở cùng vị trí.

Với mảng nguyên thủy như `int[]`, `double[]`, phép so sánh dùng quy tắc dành cho kiểu phần tử đó. Với `Object[]`, các phần tử được so sánh bằng `equals`. Vì vậy, nếu phần tử lại là một mảng, phép so sánh ở cấp này vẫn chỉ kiểm tra tham chiếu của mảng con.

```java
Object[] first = {new int[] {1, 2}};
Object[] second = {new int[] {1, 2}};

System.out.println(Arrays.equals(first, second)); // false
```

Hai phần tử ở đây là hai object `int[]` riêng biệt; `equals` của mảng con không so sánh nội dung.

### Arrays.deepEquals: so sánh đệ quy các mảng lồng nhau

`Arrays.deepEquals(Object[] a, Object[] b)` so sánh nội dung đệ quy. Khi gặp phần tử là mảng, nó tiếp tục so sánh nội dung mảng con; nó cũng xử lý các mảng nguyên thủy nằm bên trong mảng object.

```java
Object[] first = {new int[] {1, 2}};
Object[] second = {new int[] {1, 2}};

System.out.println(Arrays.deepEquals(first, second)); // true
```

Lưu ý chữ ký của `Arrays.deepEquals` nhận `Object[]` ở cấp ngoài cùng. Với một mảng nguyên thủy đơn cấp như `double[]`, hãy dùng overload `Arrays.equals(double[], double[])`. Nếu muốn một API nhận hai object tổng quát và xử lý cả mảng nguyên thủy ở cấp gốc, có thể dùng `Objects.deepEquals(a, b)`.

### Objects.deepEquals: deep comparison qua hai object

`Objects.deepEquals(a, b)` xử lý null và so sánh sâu khi hai đối số là mảng. Với các object không phải mảng, nó hoạt động theo quy tắc `equals`. Do đó, phương thức này hữu ích khi kiểu tham chiếu ở thời điểm viết mã là `Object` và giá trị thực tế có thể là mảng.

```java
Object left = new double[] {1.0, 2.0};
Object right = new double[] {1.0, 2.0};

System.out.println(Objects.equals(left, right));     // false
System.out.println(Objects.deepEquals(left, right)); // true
```

Đối với hai mảng một chiều cùng kiểu, `Objects.deepEquals` có thể cho kết quả tương ứng với overload `Arrays.equals`. Với cấu trúc lồng nhau, dùng deep comparison để so sánh các cấp bên trong.

## 5. Quy tắc của NaN và signed zero trong phép so sánh số thực

Java dùng kiểu dấu phẩy động theo chuẩn IEEE 754. Điều này dẫn đến hai trường hợp đặc biệt:

- `NaN` (Not-a-Number) biểu diễn kết quả số không xác định như `0.0 / 0.0`. Theo phép so sánh số nguyên thủy, NaN không bằng bất kỳ giá trị nào, kể cả chính nó.
- `+0.0` và `-0.0` có cùng giá trị số khi dùng toán tử `==`, nhưng có biểu diễn bit khác nhau và có thể cho kết quả khác trong một số phép toán.

Các quy tắc cơ bản:

```java
double value = Double.NaN;

System.out.println(value == value); // false
System.out.println(+0.0d == -0.0d); // true
```

Không nên dùng riêng toán tử `==` để kiểm tra NaN. Hãy dùng `Double.isNaN(value)` hoặc `Double.isNaN` với giá trị primitive phù hợp.

## 6. Double.equals và Double.compare

Khi số thực được đóng gói trong `Double`, quy tắc so sánh thay đổi so với toán tử `==`.

### Double.equals

`Double.equals` dùng biểu diễn bit chuẩn hóa thông qua `Double.doubleToLongBits`:

- Mọi giá trị NaN được chuẩn hóa về cùng một biểu diễn và được xem là bằng nhau.
- `+0.0` và `-0.0` có biểu diễn bit khác nhau nên không bằng nhau.

```java
Double nanA = Double.NaN;
Double nanB = Double.longBitsToDouble(0x7ff8000000000001L);

System.out.println(nanA.equals(nanB)); // true
System.out.println(Double.valueOf(+0.0d).equals(-0.0d)); // false
```

Điều này cũng ảnh hưởng đến so sánh các phần tử trong `Double[]` bằng `Arrays.equals`, vì các phần tử object được so sánh bằng `equals`.

### Double.compare

`Double.compare(a, b)` cung cấp thứ tự tổng hợp cho hai giá trị double:

- Các NaN được xem là bằng nhau khi so sánh.
- NaN được xếp lớn hơn dương vô cực.
- `-0.0` được xếp nhỏ hơn `+0.0`.
- Với các giá trị thông thường, kết quả âm, 0 hoặc dương biểu thị thứ tự tương ứng.

Ví dụ:

```java
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
System.out.println(Double.compare(+0.0d, -0.0d));            // 1
System.out.println(Double.compare(-0.0d, +0.0d));            // -1
```

Quy tắc này hữu ích khi sắp xếp hoặc xây dựng comparator. Không nhầm `Double.compare(a, b) == 0` với toán tử `a == b`; hai cách có thể khác nhau với NaN và signed zero.

## 7. Arrays.equals với double[] và Double[]

Với `double[]`, `Arrays.equals` dùng quy tắc tương đương so sánh biểu diễn bit chuẩn hóa của từng giá trị double:

- Hai phần tử NaN được xem là bằng nhau, kể cả khi payload bit NaN ban đầu khác nhau.
- `+0.0` và `-0.0` được xem là khác nhau.

Với `Double[]`, `Arrays.equals` so sánh từng phần tử bằng `Double.equals`:

- Hai phần tử null cùng vị trí được xem là bằng nhau.
- Hai phần tử NaN được xem là bằng nhau.
- `+0.0` và `-0.0` được xem là khác nhau.

`Arrays.deepEquals` cũng áp dụng quy tắc phù hợp cho mảng primitive lồng trong mảng object. Vì vậy, deep comparison không biến signed zero thành cùng một giá trị; nó vẫn tuân theo quy tắc so sánh của kiểu phần tử.

## 8. Ví dụ chạy được: null, NaN và signed zero

Chương trình sau kiểm tra null ở cấp mảng, mảng object, mảng primitive, deep comparison, NaN có payload khác nhau và hai dạng zero có dấu.

```java
import java.util.Arrays;
import java.util.Objects;

public class ArrayNullNanRulesDemo {
    public static void main(String[] args) {
        double nanA =
                Double.longBitsToDouble(0x7ff8000000000001L);
        double nanB =
                Double.longBitsToDouble(0x7ff8000000000002L);
        double[] positiveZero = {+0.0d};
        double[] negativeZero = {-0.0d};
        double[] firstNaN = {nanA};
        double[] secondNaN = {nanB};

        System.out.println("Objects.equals null/null = "
                + Objects.equals(null, null));
        System.out.println("Objects.deepEquals null/null = "
                + Objects.deepEquals(null, null));
        System.out.println("Arrays.equals null/null = "
                + Arrays.equals((double[]) null, (double[]) null));
        System.out.println("Arrays.equals null/empty = "
                + Arrays.equals((double[]) null, new double[0]));
        System.out.println("Objects.equals distinct arrays = "
                + Objects.equals(positiveZero, new double[] {+0.0d}));
        System.out.println("Objects.deepEquals arrays = "
                + Objects.deepEquals(positiveZero, new double[] {+0.0d}));
        System.out.println("Arrays.equals +0/-0 = "
                + Arrays.equals(positiveZero, negativeZero));
        System.out.println("Arrays.equals NaN payloads = "
                + Arrays.equals(firstNaN, secondNaN));

        Double[] boxedNullsA = {null, nanA};
        Double[] boxedNullsB = {null, nanB};
        System.out.println("Double[] null and NaN elements = "
                + Arrays.equals(boxedNullsA, boxedNullsB));
        System.out.println("Double[] +0/-0 = "
                + Arrays.equals(
                        new Double[] {+0.0d},
                        new Double[] {-0.0d}));

        System.out.println("primitive NaN == NaN = " + (nanA == nanA));
        System.out.println("primitive +0 == -0 = " + (+0.0d == -0.0d));
        System.out.println("Double NaN equals = "
                + Double.valueOf(nanA).equals(Double.valueOf(nanB)));
        System.out.println("Double +0 equals -0 = "
                + Double.valueOf(+0.0d).equals(Double.valueOf(-0.0d)));
        System.out.println("Double.compare NaN payloads = "
                + Double.compare(nanA, nanB));
        System.out.println("Double.compare +0/-0 = "
                + Double.compare(+0.0d, -0.0d));

        Object[] nestedA = {new double[] {nanA, +0.0d}};
        Object[] nestedB = {new double[] {nanB, +0.0d}};
        Object[] nestedZero = {new double[] {nanB, -0.0d}};
        System.out.println("Arrays.deepEquals nested NaN = "
                + Arrays.deepEquals(nestedA, nestedB));
        System.out.println("Arrays.deepEquals nested signed zero = "
                + Arrays.deepEquals(nestedA, nestedZero));
        System.out.println("Double bits canonicalize NaN = "
                + (Double.doubleToLongBits(nanA)
                        == Double.doubleToLongBits(nanB)));
        System.out.println("Raw bits preserve NaN payload = "
                + (Double.doubleToRawLongBits(nanA)
                        != Double.doubleToRawLongBits(nanB)));
    }
}
```

Lưu mã nguồn trong `ArrayNullNanRulesDemo.java`, sau đó biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all ArrayNullNanRulesDemo.java
java ArrayNullNanRulesDemo
```

Kết quả:

```text
Objects.equals null/null = true
Objects.deepEquals null/null = true
Arrays.equals null/null = true
Arrays.equals null/empty = false
Objects.equals distinct arrays = false
Objects.deepEquals arrays = true
Arrays.equals +0/-0 = false
Arrays.equals NaN payloads = true
Double[] null and NaN elements = true
Double[] +0/-0 = false
primitive NaN == NaN = false
primitive +0 == -0 = true
Double NaN equals = true
Double +0 equals -0 = false
Double.compare NaN payloads = 0
Double.compare +0/-0 = 1
Arrays.deepEquals nested NaN = true
Arrays.deepEquals nested signed zero = false
Double bits canonicalize NaN = true
Raw bits preserve NaN payload = true
```

Ví dụ đã được biên dịch với `javac --release 17 -Xlint:all` và kết quả chạy khớp từng dòng. Hai giá trị NaN trong ví dụ có payload bit khác nhau; `doubleToLongBits` chuẩn hóa chúng, trong khi `doubleToRawLongBits` giữ lại payload gốc.

## 9. Khi cần so sánh bit chính xác

So sánh giá trị số và so sánh biểu diễn bit là hai yêu cầu khác nhau.

- `Double.doubleToLongBits(value)` chuẩn hóa mọi NaN về một biểu diễn NaN chuẩn.
- `Double.doubleToRawLongBits(value)` giữ nguyên bit NaN, bao gồm payload.
- `Double.isNaN(value)` kiểm tra giá trị có phải NaN hay không.
- `Double.isInfinite(value)` kiểm tra vô cực.
- `Double.isFinite(value)` kiểm tra giá trị hữu hạn.

Nếu mục tiêu là so sánh nội dung số theo hợp đồng Java, dùng `Arrays.equals`, `Double.equals` hoặc `Double.compare` đúng với yêu cầu. Chỉ dùng raw bits khi ứng dụng thực sự cần phân biệt payload NaN hoặc kiểm tra định dạng nhị phân.

Đừng tự thay phép so sánh chính xác bằng một ngưỡng sai số tùy ý. Nếu bài toán cần so sánh gần đúng, phải xác định tolerance theo đơn vị, thang đo, miền giá trị và cách xử lý riêng cho NaN/vô cực.

## 10. Chọn API đúng mục đích

| Mục đích | API |
|---|---|
| So sánh hai object có thể null bằng `equals` | `Objects.equals(a, b)` |
| So sánh sâu hai object có thể là mảng | `Objects.deepEquals(a, b)` |
| So sánh nội dung mảng một cấp | `Arrays.equals(a, b)` |
| So sánh đệ quy mảng lồng nhau | `Arrays.deepEquals(a, b)` |
| So sánh hai giá trị Double theo hợp đồng wrapper | `Double.equals` |
| Tạo thứ tự tổng hợp cho giá trị double | `Double.compare(a, b)` |
| Kiểm tra NaN | `Double.isNaN(value)` |
| So sánh bit NaN sau chuẩn hóa | `Double.doubleToLongBits(value)` |
| Giữ nguyên payload bit NaN | `Double.doubleToRawLongBits(value)` |

## 11. Checklist khi review

1. Đối số có thể là null ở cấp mảng không?
2. Cần so sánh tham chiếu hay nội dung mảng?
3. Mảng có lồng mảng hoặc chứa mảng primitive bên trong không?
4. Phần tử là primitive hay wrapper như `Double`?
5. Dữ liệu có thể chứa NaN hoặc cả `+0.0` và `-0.0` không?
6. Yêu cầu là so sánh theo giá trị số, theo `equals`, theo thứ tự `compare` hay theo raw bits?
7. Nếu dùng mảng làm key hoặc thành phần của cấu trúc dữ liệu, logic `equals` và `hashCode` có cùng quy tắc không?

Kết quả so sánh chỉ có ý nghĩa khi API được chọn khớp với hợp đồng dữ liệu. Với mảng, hãy tách riêng null, identity và nội dung; với số thực, hãy xác định rõ cách xử lý NaN và signed zero trước khi so sánh.