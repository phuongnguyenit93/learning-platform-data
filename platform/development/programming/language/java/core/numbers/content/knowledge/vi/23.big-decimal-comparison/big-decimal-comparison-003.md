# Ví dụ 2.0 và 2.00 theo từng cách so sánh `BigDecimal` trong Java

## 1. Vấn đề: bằng nhau về giá trị nhưng khác cách biểu diễn

Trong Java, hai đối tượng `BigDecimal` này đều mang giá trị số học bằng 2:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
```

Nhưng kết quả của từng cách so sánh **không giống nhau**:

```java
a == b;             // false: hai đối tượng khác tham chiếu
a.equals(b);        // false: BigDecimal xét cả giá trị và scale
a.compareTo(b);     // 0: cùng giá trị số học
a.compareTo(b) == 0; // true: bằng nhau theo thứ tự số học
```

Điều quan trọng là phải xác định từ đầu “bằng nhau” đang có ý nghĩa gì: **cùng đối tượng**, **cùng giá trị và cùng scale**, hay **cùng giá trị số học**. Đây là ba câu hỏi riêng, với các cách kiểm tra riêng.

Bài học này dùng `2.0` và `2.00` để quan sát trực tiếp từng kết quả, giải thích lý do và chỉ ra ảnh hưởng tới `HashSet`, `TreeSet`, bản đồ khóa và dữ liệu nghiệp vụ.

## 2. Vì sao `BigDecimal` phân biệt 2.0 và 2.00?

Một `BigDecimal` biểu diễn giá trị thập phân bằng cặp thông tin:

- **Unscaled value**: một số nguyên không giới hạn độ dài (`BigInteger`).
- **Scale**: số mũ thập phân có dấu, quyết định vị trí dấu phẩy.

Công thức:

```text
giá trị số học = unscaledValue × 10^(-scale)

2.0  = 20  × 10^(-1)
2.00 = 200 × 10^(-2)

=> Cùng giá trị số học là 2, nhưng có cặp (unscaledValue, scale) khác nhau.
```

Đọc giá trị thực tế:

| Thuộc tính | `new BigDecimal("2.0")` | `new BigDecimal("2.00")` |
|---|---:|---:|
| `toString()` | `2.0` | `2.00` |
| `unscaledValue()` | `20` | `200` |
| `scale()` | `1` | `2` |
| `precision()` | `2` | `3` |
| Giá trị số học | `2` | `2` |

`precision()` ở đây là số chữ số của phần unscaled (20 có 2 chữ số, 200 có 3 chữ số). `precision` và `scale` không phải cùng một khái niệm.

**Vai trò của chuỗi đầu vào:** `new BigDecimal("2.0")` giữ scale 1, còn `new BigDecimal("2.00")` giữ scale 2. Điều này hữu ích khi biểu diễn có ý nghĩa như độ chính xác đã được nhập, đơn vị đo hoặc số chữ số cần hiển thị.

## 3. Bốn cách so sánh: `==`, `equals`, `compareTo`, `compareTo == 0`

| Biểu thức | Kết quả với `a=2.0`, `b=2.00` | Đang kiểm tra điều gì? |
|---|---|---|
| `a == b` | `false` | Hai biến có trỏ **cùng một đối tượng** hay không |
| `a.equals(b)` | `false` | Giá trị số học **và scale** đều bằng nhau hay không |
| `a.compareTo(b)` | `0` | Quan hệ thứ tự giữa hai giá trị số học |
| `a.compareTo(b) == 0` | `true` | Hai giá trị có **bằng nhau về mặt số học** hay không |

### 3.1. Toán tử `==`: so sánh tham chiếu

Vì `BigDecimal` là đối tượng, `==` kiểm tra hai biến có cùng địa chỉ đối tượng theo nghĩa Java reference identity, không kiểm tra giá trị thập phân.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
BigDecimal c = a;

System.out.println(a == b); // false
System.out.println(a == c); // true
```

Đây là đoạn mã minh họa cần đặt trong phương thức (chẳng hạn `main`) để chạy. `==` có thể trả `true` khi hai biến giữ cùng tham chiếu, nhưng không đáp ứng nhu cầu so sánh số học.

### 3.2. `equals(Object)`: giá trị số học và scale phải khớp

Hợp đồng `BigDecimal.equals` yêu cầu hai `BigDecimal` cùng giá trị số học **và cùng scale**. Do đó:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00"));  // false
new BigDecimal("2.0").equals(new BigDecimal("2.0"));   // true
new BigDecimal("2.00").equals(new BigDecimal("2.00")); // true
```

Không nên diễn giải `false` ở ví dụ đầu thành “2.0 khác 2.00 về độ lớn”. Hai đối tượng khác nhau theo **tiêu chuẩn `equals`** vì scale khác nhau. Hợp đồng `hashCode()` cũng tương ứng với `equals`, nên các biểu diễn khác scale thường có mã băm khác nhau; không dùng mã băm để kết luận hai số có bằng nhau về số học hay không.

### 3.3. `compareTo(BigDecimal)`: so sánh theo giá trị số học

`compareTo` trả về:

- Một số **âm** nếu đối tượng bên trái nhỏ hơn bên phải.
- **0** nếu hai giá trị số học bằng nhau.
- Một số **dương** nếu đối tượng bên trái lớn hơn bên phải.

Ví dụ:

```java
new BigDecimal("2.0").compareTo(new BigDecimal("2.00")); // 0
new BigDecimal("1.9").compareTo(new BigDecimal("2.00")); // âm
new BigDecimal("2.1").compareTo(new BigDecimal("2.00")); // dương
```

**Không dựa vào kết quả phải chính xác bằng `-1` hoặc `1`**: hợp đồng chỉ cam kết dấu của kết quả. Viết `a.compareTo(b) < 0`, `> 0`, `== 0` tương ứng với nhỏ hơn, lớn hơn và bằng nhau.

### 3.4. So sánh `compareTo(b) == 0`: kiểm tra bằng nhau về số học

Đây là lựa chọn thông dụng khi quy tắc nghiệp vụ chỉ quan tâm số lượng hoặc độ lớn:

```java
boolean sameNumericValue = a.compareTo(b) == 0; // true
```

`compareTo` vốn là phép so sánh thứ tự; thêm `== 0` mới thu được biểu thức boolean. Đừng viết `a.compareTo(b).equals(0)`: kết quả `compareTo` là `int` nguyên thủy và không có phương thức `equals`.

## 4. Ví dụ Java hoàn chỉnh: in từng kết quả

**Tệp `BigDecimalComparisonDemo.java`** — chạy với Java 17+:

```java
import java.math.BigDecimal;

public class BigDecimalComparisonDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal sameReference = a;

        System.out.println("a=" + a + ", scale=" + a.scale()
                + ", precision=" + a.precision()
                + ", unscaled=" + a.unscaledValue());
        System.out.println("b=" + b + ", scale=" + b.scale()
                + ", precision=" + b.precision()
                + ", unscaled=" + b.unscaledValue());

        System.out.println("a == b: " + (a == b));
        System.out.println("a == sameReference: " + (a == sameReference));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.compareTo(b): " + a.compareTo(b));
        System.out.println("a.compareTo(b) == 0: "
                + (a.compareTo(b) == 0));
        System.out.println("a.stripTrailingZeros().equals(b.stripTrailingZeros()): "
                + a.stripTrailingZeros().equals(b.stripTrailingZeros()));
        System.out.println("a.setScale(2).equals(b): "
                + a.setScale(2).equals(b));
    }
}
```

Lệnh chạy:

```bash
javac BigDecimalComparisonDemo.java
java BigDecimalComparisonDemo
```

Kết quả chính xác:

```text
a=2.0, scale=1, precision=2, unscaled=20
b=2.00, scale=2, precision=3, unscaled=200
a == b: false
a == sameReference: true
a.equals(b): false
a.compareTo(b): 0
a.compareTo(b) == 0: true
a.stripTrailingZeros().equals(b.stripTrailingZeros()): true
a.setScale(2).equals(b): true
```

Có hai cách khác nhau khiến `equals` trả về `true` trong những dòng cuối: bỏ các số 0 không cần thiết bằng `stripTrailingZeros()`, hoặc thống nhất hai số về **cùng scale 2**. Chúng đều trả về đối tượng `BigDecimal` mới hoặc kết quả đã điều chỉnh; đối tượng đầu vào không bị sửa vì `BigDecimal` là immutable.

## 5. Đối chiếu hệ quả của bốn phép so sánh trong collection

Với `2.0` và `2.00`, `equals` trả false nhưng `compareTo` trả 0. Cấu trúc băm dựa trên **equals/hashCode**; cấu trúc cây theo thứ tự tự nhiên dựa trên **compareTo**:

| Collection | Kết quả khi thêm 2.0 rồi 2.00 | Lý do |
| --- | --- | --- |
| `HashSet` | Hai phần tử | Khác equals |
| `HashMap` | Hai khóa | Khác equals/hashCode |
| `TreeSet` | Một phần tử | compareTo == 0 |
| `TreeMap` | Một khóa, value lần sau ghi đè | compareTo == 0 |

```java
Set<BigDecimal> hash = new HashSet<>();
hash.add(new BigDecimal("2.0"));
hash.add(new BigDecimal("2.00"));
Set<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("2.0"));
tree.add(new BigDecimal("2.00"));
// hash.size() == 2, tree.size() == 1
```

Đoạn mã nằm trong phương thức, cần import `BigDecimal`, `Set`, `HashSet`, `TreeSet`. Bài **hashCode và hệ quả trong HashSet hoặc HashMap** phân tích tra cứu khóa; bài **Hệ quả khi dùng TreeSet hoặc TreeMap** phân tích `contains`, `remove`, `put`, `get` và comparator. Ví dụ hiện tại chỉ minh họa sự khác biệt của **chính cặp 2.0 và 2.00**.

## 6. Chuẩn hóa có thể làm phép equals đổi kết quả

Nếu chỉ hỏi hai số có cùng giá trị không, dùng `a.compareTo(b) == 0` trực tiếp. Khi cần tạo khóa đồng nhất theo giá trị, có thể dùng `stripTrailingZeros()` cho cả hai phía:

```java
BigDecimal a = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("2.00").stripTrailingZeros();
// a.equals(b) == true
```

Tuy nhiên `stripTrailingZeros()` có thể biến `1000.00` thành `1E+3` (scale âm) hoặc xóa scale của zero. Một chính sách **scale cố định** như `setScale(2, RoundingMode.UNNECESSARY)` giữ đủ hai chữ số nhưng từ chối `2.001` vì cần làm tròn. Chuẩn hóa là quyết định nghiệp vụ riêng cho khóa/lưu trữ; không cần làm chỉ để so sánh số học. Bài **Chính sách chuẩn hóa scale trước khi lưu hoặc so sánh** đi sâu vào quy tắc chọn ranh giới và xử lý rounding.
## 7. Bẫy khi khởi tạo: `2.0` và `2.00` dưới dạng `double`

Đoạn dưới tạo ra **hai giá trị literal `double` giống nhau**:

```java
double x = 2.0;
double y = 2.00;
System.out.println(x == y); // true
```

Kiểu `double` không ghi nhớ người viết đã thêm bao nhiêu số 0 sau dấu phẩy. Vì vậy:

| Cách tạo đối tượng | Biểu diễn `BigDecimal` | Scale |
|---|---|---:|
| `new BigDecimal("2.0")` | `2.0` | 1 |
| `new BigDecimal("2.00")` | `2.00` | 2 |
| `BigDecimal.valueOf(2.00)` | `2.0` | 1 |
| `new BigDecimal(2.00)` | `2` | 0 |
| `BigDecimal.valueOf(2L)` | `2` | 0 |

`BigDecimal.valueOf(double)` dùng biểu diễn thập phân chuẩn từ `Double.toString(double)`. Với đúng giá trị 2.0, chuỗi đó là `"2.0"`. Constructor `BigDecimal(double)` chuyển chính xác giá trị nhị phân nhận được thành một `BigDecimal`; 2 là số nguyên biểu diễn chính xác, nên kết quả có scale 0 trong ví dụ này.

**Không áp dụng kết luận “constructor từ double là chính xác theo hệ thập phân” cho mọi số.** Ví dụ `0.1` không có biểu diễn nhị phân hữu hạn; `new BigDecimal(0.1)` sẽ bộc lộ phần sai khác rất dài so với giá trị thập phân `0.1` mà người dùng thường mong đợi. Để bảo toàn dạng chữ số ban đầu, nhận đầu vào dạng `String` và truyền vào constructor `BigDecimal(String)`.

## 8. Phép toán có thể làm thay đổi scale và kết quả `equals`

Scale không chỉ ảnh hưởng cách so sánh, mà còn có thể đi theo kết quả số học:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.add(b));      // 4.00
System.out.println(a.multiply(b)); // 4.000
```

Với phép cộng, scale của kết quả không làm tròn chính xác thường là `max(scale(a), scale(b))`; ở đây `max(1, 2) = 2`. Với phép nhân chính xác, scale kết quả thường là tổng hai scale; ở đây `1 + 2 = 3`.

Hệ quả: hai chuỗi thao tác có thể tạo ra những `BigDecimal` cùng giá trị số học nhưng scale khác, nên `equals` khác `compareTo == 0`. Khi kiểm tra giá trị tính toán trong bài toán tài chính, đo lường hoặc test, hãy xác định tiêu chí so sánh độc lập với hình thức trình bày.

## 9. Chọn phép so sánh đúng theo mục đích

| Mục tiêu | Cách nên dùng | Lý do |
|---|---|---|
| Kiểm tra hai biến có trỏ cùng object | `a == b` | Chỉ kiểm tra danh tính tham chiếu |
| Kiểm tra giá trị **và scale** giống nhau | `a.equals(b)` | Xét đúng hợp đồng `BigDecimal.equals` |
| Kiểm tra hai giá trị số học bằng nhau | `a.compareTo(b) == 0` | Bỏ qua khác biệt về trailing zero/scale |
| Kiểm tra nhỏ hơn/lớn hơn | `a.compareTo(b) < 0` hoặc `> 0` | Thứ tự số học |
| Muốn `HashSet`/khóa `HashMap` gộp các dạng số học tương đương | Chuẩn hóa khóa theo một quy ước thống nhất | `HashSet` và `HashMap` dùng `equals`/`hashCode` |
| Muốn lưu cả `2.0` và `2.00` trong tập có thứ tự | `TreeSet` với comparator xét thêm scale | Thứ tự tự nhiên chỉ xét giá trị số học |
| Muốn giữ đúng 2 chữ số để hiển thị/ghi sổ | `setScale(2, mode)` theo chính sách | Scale là một phần của định dạng và hợp đồng nghiệp vụ |

**Vấn đề null:** `a.equals(b)` và `a.compareTo(b)` sẽ lỗi nếu `a == null`. Nếu `null` được phép, kiểm tra trước; đừng mặc định `null` tương đương số 0. `Objects.equals(a,b)` xử lý null an toàn nhưng vẫn dùng hợp đồng `equals`, tức vẫn cho `false` với `2.0` và `2.00`.

**Vấn đề test:** Với `assertEquals(expected, actual)` (ví dụ JUnit), framework thường dựa trên `equals`, nên một đối tượng mong đợi `2.00` có thể không bằng kết quả thực tế `2.0`. Nếu test yêu cầu bằng nhau về số học, hãy kiểm tra `expected.compareTo(actual) == 0` theo cách assertion phù hợp. Chỉ dùng `equals` khi scale thực sự là yêu cầu cần kiểm tra.

## 10. Bài tập và lời giải

1. **Cho `a = 2.0`, `b = 2.00` (đều khởi tạo từ chuỗi). `a.equals(b)` và `a.compareTo(b) == 0` trả gì?**  
   Đáp án: `false` và `true`. Scale khác nhau nhưng giá trị số học bằng nhau.
2. **Tạo `c = new BigDecimal("2.0")`. `a.equals(c)` và `a == c` trả gì?**  
   Đáp án: `true` và `false` nếu `a`, `c` được tạo bằng hai lệnh `new` riêng biệt: cùng value/scale nhưng khác object.
3. **`HashSet` lần lượt thêm `2.0` rồi `2.00` có bao nhiêu phần tử? `TreeSet` thứ tự tự nhiên thì sao?**  
   Đáp án: `HashSet` có 2; `TreeSet` có 1. Hai tập dùng tiêu chuẩn xác định trùng khác nhau.
4. **`new BigDecimal("2.00").stripTrailingZeros().scale()` bằng mấy?**  
   Đáp án: `0`, vì biểu diễn chuẩn hóa là `2`.
5. **Sau `new BigDecimal("2.0").setScale(2)`, `equals(new BigDecimal("2.00"))` là gì?**  
   Đáp án: `true`: cả giá trị và scale đều trùng.
6. **Tại sao `BigDecimal.valueOf(2.00)` không giữ lại 2 chữ số thập phân?**  
   Đáp án: `2.00` đã được chuyển thành `double` và mất thông tin về cách viết; `Double.toString` biểu diễn nó là `"2.0"`.

## 11. Ghi nhớ

`2.0` và `2.00` là **cùng giá trị số học** nhưng là **hai biểu diễn `BigDecimal` có scale khác nhau** khi tạo từ chuỗi. Hãy chọn tiêu chí theo ý định:

- Dùng `compareTo() == 0` cho **bằng nhau về số học**.
- Dùng `equals()` khi **scale cũng là một phần của tính bằng nhau**.
- Dùng `==` chỉ khi thật sự cần hỏi **có cùng tham chiếu đối tượng hay không**.
- Với collections, nhớ `HashSet`/`HashMap` theo `equals` còn `TreeSet`/`TreeMap` thứ tự tự nhiên theo `compareTo`.
- Chuẩn hóa `stripTrailingZeros` hoặc `setScale` chỉ khi quy tắc dữ liệu cho phép thay đổi cách biểu diễn.

Tài liệu chính thức:

- [Java 21 — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java 21 — `Comparable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html)
- [Java 21 — `TreeSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html)
