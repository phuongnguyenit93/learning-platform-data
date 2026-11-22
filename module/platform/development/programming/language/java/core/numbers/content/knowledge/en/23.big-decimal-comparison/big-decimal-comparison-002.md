# `BigDecimal.equals()` đồng thời xét giá trị và scale

Khi làm việc với `BigDecimal`, hai đối tượng có thể **bằng nhau về giá trị số học** nhưng `equals()` vẫn trả về `false`. Lý do: `BigDecimal.equals(Object)` xét **cả giá trị và `scale`**. Vì vậy `new BigDecimal("2.0")` không `equals()` với `new BigDecimal("2.00")`, dù hai số đều có giá trị 2.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));         // false
System.out.println(a.compareTo(b) == 0); // true
```

Việc phân biệt này ảnh hưởng trực tiếp đến điều kiện so sánh, `HashSet`/`TreeSet`, khóa `HashMap`/`TreeMap` và cách thiết kế `equals`/`hashCode` cho lớp nghiệp vụ.

## 1. Giá trị số học và scale là hai thuộc tính khác nhau

Một `BigDecimal` có dạng:

```text
giá trị = unscaledValue × 10^(-scale)
```

`unscaledValue` là hệ số nguyên, còn `scale` xác định vị trí dấu thập phân trong biểu diễn.

| Cách tạo | `unscaledValue()` | `scale()` | Giá trị số học |
|---|---:|---:|---:|
| `new BigDecimal("2")` | 2 | 0 | 2 |
| `new BigDecimal("2.0")` | 20 | 1 | 2 |
| `new BigDecimal("2.00")` | 200 | 2 | 2 |
| `new BigDecimal("2E+0")` | 2 | 0 | 2 |
| `new BigDecimal("1000")` | 1000 | 0 | 1000 |
| `new BigDecimal("1E+3")` | 1 | -3 | 1000 |

Quy tắc `equals()`:

- Đối số phải là một `BigDecimal`.
- Giá trị số học phải bằng nhau.
- **Scale phải bằng nhau**.

Hệ quả:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00")); // false
new BigDecimal("2.00").equals(new BigDecimal("2.00")); // true
new BigDecimal("2").equals(new BigDecimal("2E+0"));  // true
new BigDecimal("1000").equals(new BigDecimal("1E+3")); // false
```

Scale có thể âm, bằng 0 hoặc dương. Vì vậy, không nên định nghĩa scale đơn giản là “có bao nhiêu chữ số sau dấu thập phân trong chuỗi nhập”; mô hình `unscaledValue × 10^(-scale)` bao quát cả ký pháp khoa học.

**Ngay cả số 0 cũng có scale**: `new BigDecimal("0.00")` có scale 2; `BigDecimal.ZERO` có scale 0. Chúng cùng giá trị toán học 0 nhưng `equals()` trả `false`.

## 2. `equals()` và `compareTo()` trả lời hai câu hỏi khác nhau

- `a.equals(b)`: hai biểu diễn có **cùng giá trị và cùng scale** không?
- `a.compareTo(b)`: theo **giá trị số học**, `a` nhỏ hơn, bằng hay lớn hơn `b`?

`compareTo()` trả số âm, 0 hoặc số dương; **0** nghĩa là hai giá trị số học bằng nhau. Nó không yêu cầu scale trùng nhau.

| `a` | `b` | `a.equals(b)` | `a.compareTo(b)` |
|---|---|---|---:|
| `2.0` | `2.00` | `false` | 0 |
| `2.00` | `2.00` | `true` | 0 |
| `0.0` | `0` | `false` | 0 |
| `1000` | `1E+3` | `false` | 0 |
| `1.99` | `2.00` | `false` | Số âm |
| `2.01` | `2.00` | `false` | Số dương |

Cần so sánh theo **giá trị số học**:

```java
boolean sameNumericValue = a.compareTo(b) == 0;
boolean smaller = a.compareTo(b) < 0;
boolean greater = a.compareTo(b) > 0;
```

Đừng giả định `compareTo()` luôn trả chính xác `-1` hay `1`; hợp đồng `Comparable` chỉ đảm bảo dấu của kết quả.

Cần so sánh theo **cả giá trị và scale**, ví dụ kiểm tra biểu diễn có đúng số chữ số thập phân quy định:

```java
boolean sameRepresentationValue = a.equals(b);
```

Java công bố rõ rằng **thứ tự tự nhiên của `BigDecimal` không nhất quán với `equals()`**: có những cặp mà `compareTo() == 0` nhưng `equals() == false`. Đây là hành vi thiết kế có chủ đích.

## 3. `equals()`, `hashCode()` và hệ quả đối với collection

Quy tắc chung của Java: nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`. `BigDecimal.hashCode()` xét cả scale, nên `2.0` và `2.00` có thể có hash code khác nhau. Không được kết luận ngược rằng hai hash code bằng nhau thì hai đối tượng chắc chắn `equals()`, vì có thể xảy ra va chạm hash.

Hai nhóm collection sử dụng tiêu chí khác nhau:

| Cấu trúc | Tiêu chí tương đương mặc định | `2.0` và `2.00` |
|---|---|---|
| `HashSet<BigDecimal>` | `equals()` / `hashCode()` | Hai phần tử |
| `HashMap<BigDecimal, V>` | `equals()` / `hashCode()` | Hai khóa |
| `TreeSet<BigDecimal>` | `compareTo() == 0` | Một phần tử |
| `TreeMap<BigDecimal, V>` | `compareTo() == 0` | Một khóa tương đương |

Ví dụ:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

Set<BigDecimal> hash = new HashSet<>(List.of(a, b));
Set<BigDecimal> tree = new TreeSet<>(List.of(a, b));

System.out.println(hash.size()); // 2
System.out.println(tree.size()); // 1
```

`HashSet` giữ cả hai vì `equals()` trả `false`. `TreeSet` sử dụng thứ tự tự nhiên nên `compareTo() == 0` làm hai giá trị trở thành một phần tử tương đương theo thứ tự sắp xếp.

Với `Map` cũng tương tự. Nếu `map.put(new BigDecimal("2.0"), "A")` trên một `HashMap`, gọi `map.get(new BigDecimal("2.00"))` không tìm được ánh xạ tương ứng. Trên `TreeMap` dùng thứ tự tự nhiên, `put` với khóa thứ hai sẽ thay giá trị gắn với khóa tương đương đầu tiên.

**Cạm bẫy quan trọng:** chuyển giữa `HashSet` và `TreeSet` hoặc `HashMap` và `TreeMap` có thể làm thay đổi số phần tử/khóa được xem là duy nhất khi kiểu khóa là `BigDecimal`.

## 4. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `BigDecimalEqualsDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalEqualsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("a.scale() = " + a.scale());
        System.out.println("b.scale() = " + b.scale());
        System.out.println("a.equals(b) = " + a.equals(b));
        System.out.println("a.compareTo(b) = " + a.compareTo(b));
        System.out.println("numeric equality = " + (a.compareTo(b) == 0));

        Set<BigDecimal> hash = new HashSet<>(List.of(a, b));
        Set<BigDecimal> tree = new TreeSet<>(List.of(a, b));
        System.out.println("HashSet size = " + hash.size());
        System.out.println("TreeSet size = " + tree.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        System.out.println("HashMap get b = " + hashMap.get(b));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");
        System.out.println("TreeMap size = " + treeMap.size());
        System.out.println("TreeMap get a = " + treeMap.get(a));

        BigDecimal normalizedA = a.stripTrailingZeros();
        BigDecimal normalizedB = b.stripTrailingZeros();
        System.out.println("normalized equals = "
                + normalizedA.equals(normalizedB));

        BigDecimal fixedScale = a.setScale(2);
        System.out.println("setScale(2) equals b = "
                + fixedScale.equals(b));

        BigDecimal normalizedZero =
                new BigDecimal("0.00").stripTrailingZeros();
        System.out.println("normalized zero = " + normalizedZero
                + ", scale=" + normalizedZero.scale());

        BigDecimal normalizedThousand =
                new BigDecimal("1000.00").stripTrailingZeros();
        System.out.println("normalized thousand = " + normalizedThousand
                + ", scale=" + normalizedThousand.scale());
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalEqualsDemo.java
java BigDecimalEqualsDemo
```

Stdout chính xác:

```text
a.scale() = 1
b.scale() = 2
a.equals(b) = false
a.compareTo(b) = 0
numeric equality = true
HashSet size = 2
TreeSet size = 1
HashMap get b = null
TreeMap size = 1
TreeMap get a = second
normalized equals = true
setScale(2) equals b = true
normalized zero = 0, scale=0
normalized thousand = 1E+3, scale=-3
```

Phần `TreeMap` chỉ giữ một khóa tương đương theo `compareTo`; lần `put(b, "second")` cập nhật giá trị từ `"first"` thành `"second"`. Trong khi đó, `HashMap.get(b)` trả `null` vì khóa ban đầu `a` có scale khác `b`.

Phần `stripTrailingZeros()` cho thấy khi loại các số 0 ở cuối hệ số, `2.0` và `2.00` về cùng biểu diễn `2`. `setScale(2)` lại đổi `2.0` thành `2.00` mà không phải làm tròn.

## 5. Chọn cách so sánh theo quy tắc nghiệp vụ

### Trường hợp A: chỉ quan tâm giá trị số học

Ví dụ, hai tổng tiền có cùng giá trị dù một nguồn trả `125.0` còn nguồn khác trả `125.00`:

```java
BigDecimal fromA = new BigDecimal("125.0");
BigDecimal fromB = new BigDecimal("125.00");

boolean sameAmount = fromA.compareTo(fromB) == 0; // true
```

Nếu chỉ cần kiểm tra bằng nhau tại một thời điểm, `compareTo() == 0` rõ ý nghĩa và không cần thay đổi dữ liệu.

### Trường hợp B: cần dùng khóa cho `HashMap` hoặc phần tử `HashSet`

Nếu muốn `125`, `125.0`, `125.00` cùng một khóa thì phải **chuẩn hóa khi đưa vào và khi tra cứu**. Một cách là `stripTrailingZeros()`:

```java
Map<BigDecimal, String> lookup = new HashMap<>();

BigDecimal entered = new BigDecimal("125.00");
lookup.put(entered.stripTrailingZeros(), "matched");

BigDecimal query = new BigDecimal("125.0");
String found = lookup.get(query.stripTrailingZeros());
// found = "matched"
```

`stripTrailingZeros()` giữ nguyên giá trị toán học nhưng chuẩn hóa biểu diễn:

- `2.0` và `2.00` đều thành `2`.
- Số 0 ở bất kỳ scale nào trở thành `BigDecimal.ZERO`, scale 0.
- `1000.00` có thể trở thành `1E+3`, scale -3. Scale âm là hợp lệ, và cách hiển thị có thể đổi sang ký pháp khoa học.

`stripTrailingZeros()` không sửa đối tượng gốc vì `BigDecimal` là kiểu bất biến; hãy dùng giá trị trả về.

### Trường hợp C: cần chuẩn hóa đúng scale theo miền nghiệp vụ

Nếu quy ước số tiền phải có **scale 2**, bạn có thể chuẩn hóa về scale 2:

```java
BigDecimal a = new BigDecimal("125.0").setScale(2);
BigDecimal b = new BigDecimal("125.00").setScale(2);
System.out.println(a.equals(b)); // true
```

Việc **tăng** scale bằng cách thêm các số 0 ở cuối không đổi giá trị. Nhưng **giảm** scale không phải lúc nào cũng chính xác:

```java
new BigDecimal("125.000").setScale(2); // 125.00: chính xác
new BigDecimal("125.001").setScale(2); // ArithmeticException
```

Để cho phép mất phần chữ số dư, cần có quy tắc làm tròn rõ ràng, ví dụ `setScale(2, RoundingMode.HALF_UP)`. Không tự làm tròn nếu mục tiêu là đánh giá liệu **hai số gốc** có bằng nhau hay không: sau làm tròn, hai số khác nhau có thể thành cùng một số.

### Trường hợp D: ứng dụng cần bảo toàn scale

Trong dữ liệu đo lường, hợp đồng hoặc định dạng nhập, `1.0` và `1.00` đôi khi có nghĩa biểu diễn khác nhau. Nếu quy tắc nghiệp vụ yêu cầu phân biệt chúng, dùng `equals()` và không chuẩn hóa xóa phần scale. Quyết định này phải nhất quán trong so sánh, lưu trữ và lập chỉ mục.

## 6. Khi `BigDecimal` là trường trong `equals()`/`hashCode()` của lớp khác

Một lỗi tinh vi: lớp nghiệp vụ dùng `amount.compareTo(other.amount) == 0` trong `equals()`, nhưng lại lấy `amount.hashCode()` chưa chuẩn hóa trong `hashCode()`. Khi `2.0` và `2.00` được coi là bằng nhau theo `equals()` mà có hash code khác nhau, lớp đó vi phạm hợp đồng hash của Java. `HashMap` và `HashSet` có thể xử lý sai kỳ vọng.

Cách đơn giản là **chuẩn hóa một lần lúc tạo khóa**, sau đó để `equals()` và `hashCode()` tự động dùng cùng biểu diễn chuẩn:

```java
import java.math.BigDecimal;

public record AmountKey(BigDecimal value) {
    public AmountKey {
        value = value.stripTrailingZeros();
    }
}
```

Đây là ví dụ độc lập về kiểu `record` trong Java 17. Với `value` khác `null`, hai khóa `new AmountKey(new BigDecimal("2.0"))` và `new AmountKey(new BigDecimal("2.00"))` có cùng trạng thái chuẩn hóa; `record` tự sinh `equals()` và `hashCode()` nhất quán. Nếu cần nhận `null`, lớp phải quy định và xử lý trường hợp đó riêng.

Nếu ứng dụng cần phân biệt scale thì không dùng cách chuẩn hóa này: nên giữ giá trị và scale như dữ liệu gốc trong phép so sánh.

## 7. Lỗi thường gặp và cách tránh

1. **Dùng `==` với hai đối tượng `BigDecimal`.** `==` so sánh tham chiếu, không phải giá trị. Dùng `equals()` hoặc `compareTo()` theo mục đích.
2. **Nhầm `equals()` với `compareTo() == 0`.** Một bên xét cả scale; một bên chỉ xét giá trị số học.
3. **Dùng `HashMap` với scale nhập vào không nhất quán.** Khóa lưu là `5.00` nhưng tra là `5.0` có thể không tìm được. Chuẩn hóa cả hai đầu nếu chỉ quan tâm giá trị.
4. **Đổi `HashSet` thành `TreeSet` rồi tưởng dữ liệu bị mất ngẫu nhiên.** Số phần tử khác nhau xuất phát từ cơ chế tương đương của hai collection.
5. **Giả định `stripTrailingZeros()` giữ nguyên scale hoặc `toString()`.** Giá trị không đổi, nhưng `1000.00` có thể thành `1E+3` với scale -3.
6. **Gọi `setScale` mà không xử lý trường hợp cần làm tròn.** Nếu cần giảm scale và phải bỏ chữ số khác 0, quá trình sẽ ném `ArithmeticException` nếu không có chế độ làm tròn.
7. **Chuyển sang `doubleValue()` để so sánh.** `double` có thể mất chính xác; hãy giữ phép so sánh trong miền `BigDecimal`.
8. **Tưởng mọi cách tạo số 2 đều có scale giống nhau.** `BigDecimal.valueOf(2.0)` có scale 1, còn `BigDecimal.valueOf(2L)` có scale 0.
9. **Quên trường hợp `null`.** `a.compareTo(b)` đòi các đối số hợp lệ. `Objects.equals(a, b)` xử lý `null` nhưng vẫn dùng semantics `equals()`, nên vẫn xét scale khi cả hai là `BigDecimal`.

## 8. Tự kiểm tra

**1.** `new BigDecimal("0.00").equals(BigDecimal.ZERO)` trả gì?  
**Đáp án:** `false`, vì scale 2 khác scale 0. Tuy vậy `compareTo() == 0`.

**2.** `new BigDecimal("1E+3").equals(new BigDecimal("1000"))` trả gì?  
**Đáp án:** `false`, vì scale -3 khác scale 0, dù cả hai cùng giá trị 1000.

**3.** Thêm `"1"`, `"1.0"`, `"1.00"` vào `HashSet<BigDecimal>` và `TreeSet<BigDecimal>` mặc định thì kích thước là bao nhiêu?  
**Đáp án:** `HashSet` là 3, `TreeSet` là 1.

**4.** Vì sao không nên để lớp nghiệp vụ dùng `compareTo() == 0` làm `equals()` nhưng dùng `BigDecimal.hashCode()` gốc?  
**Đáp án:** Các số khác scale có thể `equals() == true` nhưng hash code khác nhau, vi phạm hợp đồng của Java.

**5.** Khi cần phân biệt người dùng nhập `"2.0"` và `"2.00"`, nên dùng gì?  
**Đáp án:** `equals()` vì scale là một phần của yêu cầu so sánh.

**Ghi nhớ:** `BigDecimal.equals()` yêu cầu **cùng giá trị số học và cùng scale**. `BigDecimal.compareTo() == 0` chỉ yêu cầu **cùng giá trị số học**. Chọn tiêu chí theo mục đích trước khi so sánh hoặc chọn loại `Set`/`Map`.
