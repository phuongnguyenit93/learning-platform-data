# Ví dụ BigDecimal có scale khác nhau trong tập hợp có thứ tự

## 1. Mục tiêu

`BigDecimal` đại diện cho số thập phân có độ chính xác tùy ý bằng hai yếu tố: **unscaled value** (một số nguyên) và **scale** (số chữ số thập phân theo phép biểu diễn). Hai đối tượng có cùng **giá trị số học** vẫn có thể khác scale. Đây là tình huống điển hình cho việc **quan hệ bằng nhau của `equals()` không đồng nhất với quan hệ tương đương của thứ tự `compareTo()`**.

Bài học giúp bạn:

- Hiểu `new BigDecimal("1.0")` và `new BigDecimal("1.00")` vì sao có `equals() == false` nhưng `compareTo() == 0`.
- Dự đoán chính xác khi đưa hai giá trị đó vào `HashSet`, `TreeSet`, `HashMap`, `TreeMap`.
- Hiểu tập hợp có thứ tự dùng `compareTo` hoặc `Comparator` để xét cả vị trí sắp xếp lẫn việc **một key đã tồn tại hay chưa**.
- Chọn chính sách phù hợp khi cần phân biệt scale hoặc khi cần coi các cách biểu diễn cùng trị số là một.
- Áp dụng `stripTrailingZeros()` hoặc comparator tường minh đúng mục đích; tránh làm mất thông tin scale có ý nghĩa nghiệp vụ.

## 2. BigDecimal gồm trị số và scale

Đối với `BigDecimal`, trị số được diễn đạt theo công thức:

```text
numeric value = unscaledValue × 10^(-scale)
```

Ví dụ:

| Cách tạo | Unscaled value | Scale | Trị số học |
| --- | ---: | ---: | ---: |
| `new BigDecimal("1.0")` | `10` | `1` | `1` |
| `new BigDecimal("1.00")` | `100` | `2` | `1` |
| `new BigDecimal("1")` | `1` | `0` | `1` |
| `new BigDecimal("1E+2")` | `1` | `-2` | `100` |
| `new BigDecimal("0.000")` | `0` | `3` | `0` |

Trong Java:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.unscaledValue()); // 10
System.out.println(a.scale());         // 1
System.out.println(b.unscaledValue()); // 100
System.out.println(b.scale());         // 2
```

Đây là đoạn minh họa cần `import java.math.BigDecimal;`. Phân biệt **scale** với **precision**: precision là số chữ số của unscaled value (không tính dấu), còn scale xác định vị trí dấu thập phân. `"1.00"` có precision 3, scale 2; `"1.0"` có precision 2, scale 1.

Scale có thể là thông tin đáng lưu giữ: biểu diễn độ chính xác đo lường, số chữ số được ghi nhận hay chính sách hiển thị tiền tệ. Vì vậy Java cung cấp cả cách so “bằng nhau về biểu diễn số thập phân” lẫn cách so “bằng nhau về trị số”.

## 3. `equals()` và `compareTo()` khác nhau thế nào?

### 3.1. `BigDecimal.equals(Object)` xét cả trị số và scale

Với hai `BigDecimal`, `equals()` trả `true` chỉ khi chúng có **cùng unscaled value và cùng scale**. Do đó:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.equals(b);                // false
a.hashCode() == b.hashCode(); // false trong ví dụ này
```

`hashCode()` của `BigDecimal` phù hợp với `equals()`: nếu hai giá trị `equals` bằng nhau, hash của chúng bắt buộc bằng nhau. Khi chỉ khác scale, hash **có thể** khác và trong ví dụ `1.0` với `1.00` quả thực khác. Đừng suy ra hash là định danh duy nhất vì collision vẫn có thể xảy ra.

### 3.2. `compareTo()` so giá trị số học

`BigDecimal.compareTo(BigDecimal)` thực hiện so sánh thứ tự theo **trị số**, không coi scale là yếu tố phân biệt khi trị số bằng nhau:

```java
a.compareTo(b);  // 0
```

Quy tắc:

- Giá trị âm: `a.compareTo(b) < 0` nghĩa là `a` nhỏ hơn `b`.
- Trả `0`: `a` và `b` có cùng trị số đối với phép so sánh này.
- Giá trị dương: `a.compareTo(b) > 0` nghĩa là `a` lớn hơn `b`.

Không dựa vào độ lớn tuyệt đối của kết quả âm/dương; hợp đồng chỉ bảo đảm **dấu**. Với `BigDecimal`, quan hệ `compareTo() == 0` có thể rộng hơn `equals() == true`.

`BigDecimal` là ví dụ tiêu biểu cho **natural ordering inconsistent with equals**: hai phần tử có thể tương đương về thứ tự nhưng không bằng nhau theo `equals`.

### 3.3. Mối quan hệ chính xác

| Phép kiểm tra | `1.0` với `1.00` | Ý nghĩa |
| --- | --- | --- |
| `a == b` | `false` | Hai đối tượng được tạo riêng có danh tính khác nhau. |
| `a.equals(b)` | `false` | Unscaled value và scale không cùng bộ giá trị. |
| `a.compareTo(b) == 0` | `true` | Cùng trị số số học. |
| `a.scale() == b.scale()` | `false` | Một bên scale 1, bên kia scale 2. |
| `a.stripTrailingZeros().equals(b.stripTrailingZeros())` | `true` | Hai giá trị quy về cùng dạng chuẩn với ví dụ này. |

Lưu ý `Objects.equals(a,b)` vẫn gọi `a.equals(b)` khi cả hai không null; nó **không tự chuyển sang `compareTo()`**.

## 4. Tại sao `HashSet` và `TreeSet` cho kết quả khác?

### 4.1. HashSet dựa trên `equals` và `hashCode`

`HashSet` sử dụng hash để phân phối phần tử, và dùng quan hệ `equals` để phân biệt những khóa có thể trùng nhau. Với:

```java
Set<BigDecimal> hashed = new HashSet<>();
hashed.add(new BigDecimal("1.0"));
hashed.add(new BigDecimal("1.00"));
```

`hashed.size()` là **2** vì hai `BigDecimal` không `equals()` bằng nhau. Đây là hai phần tử khác nhau theo **quan hệ bằng nhau của `BigDecimal`**.

### 4.2. TreeSet dựa trên thứ tự `compareTo` hoặc `Comparator`

`TreeSet` là một `SortedSet`; nếu không cung cấp comparator, nó dùng **thứ tự tự nhiên** (natural ordering) của phần tử, ở đây là `BigDecimal.compareTo`.

```java
TreeSet<BigDecimal> sorted = new TreeSet<>();
boolean first = sorted.add(new BigDecimal("1.0"));
boolean second = sorted.add(new BigDecimal("1.00"));
```

Kết quả:

- `first` là `true`: phần tử đầu được thêm.
- `second` là `false`: đối tượng thứ hai có `compareTo(...) == 0` với phần tử sẵn có.
- `sorted.size()` là **1**: `TreeSet` coi hai giá trị là cùng một khóa thứ tự, dù `equals` trả `false`.
- `sorted.contains(new BigDecimal("1.000"))` là `true`: tìm kiếm cũng dựa trên quan hệ thứ tự.
- Nếu thêm `1.0` trước, phần tử được giữ lại có dạng `1.0` (scale 1); nếu thêm `1.00` trước thì phần tử được giữ lại có dạng `1.00` (scale 2). Điều này cần lưu ý nếu mã ứng dụng quan sát `scale()` của phần tử được lưu.

Quy tắc tổng quát của `TreeSet` là **comparator trả 0 ⇒ phần tử bị coi là trùng đối với cấu trúc cây**, không phụ thuộc việc `equals` của chúng trả gì.

### 4.3. Điều này có vi phạm hợp đồng `Set` không?

Hợp đồng tổng quát của `Set` định nghĩa trùng theo `equals`. Các tài liệu Java nêu rằng thứ tự dùng cho một sorted set **nên nhất quán với `equals`** nếu muốn sorted set tuân thủ đầy đủ hợp đồng chung của `Set`. Khi thứ tự không nhất quán như `BigDecimal`, `TreeSet` vẫn có hành vi được xác định bởi comparator, nhưng cách coi phần tử trùng **khác** với một `HashSet` chứa cùng giá trị.

Không kết luận rằng `TreeSet` bị lỗi hoặc `BigDecimal.compareTo` triển khai sai. Đó là kết quả của **hai định nghĩa tương đương khác nhau**. Người thiết kế phải chọn quan hệ bằng nhau cần áp dụng cho collection.

## 5. `TreeMap`: key mới có thể thay value của key cũ

`TreeMap` cũng dựa vào `compareTo` hoặc comparator để sắp xếp và xác định khóa tương đương:

```java
TreeMap<BigDecimal, String> map = new TreeMap<>();
map.put(new BigDecimal("1.0"), "first");
map.put(new BigDecimal("1.00"), "second");
```

Kết quả:

- `map.size() == 1`: hai key so sánh bằng 0.
- Giá trị của key tương đương được cập nhật thành `"second"`.
- Khi thêm theo đúng thứ tự trên, key giữ trong entry là `1.0` (scale 1), vì cập nhật giá trị không thay đối tượng key đã lưu.
- `map.get(new BigDecimal("1.000"))` trả `"second"`.

Ngược lại, `HashMap<BigDecimal, String>` với hai key này sẽ có **hai entry** khi dùng `equals/hashCode` của `BigDecimal`.

Tình huống thực tế: Nếu bạn lưu mức giá `1.0` và `1.00` như hai mốc riêng cần giữ cả precision/scale, `TreeMap` theo thứ tự tự nhiên có thể **gộp chúng thành một key**. Nếu bạn lưu các ngưỡng chỉ dựa trên trị số, việc gộp lại có thể chính là hành vi mong muốn.

## 6. Chương trình Java 17+ chạy được

Tạo tệp **`BigDecimalSortedSetDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalSortedSetDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("a scale: " + a.scale());
        System.out.println("b scale: " + b.scale());
        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo: " + a.compareTo(b));
        System.out.println("hash equals: "
                + (a.hashCode() == b.hashCode()));

        Set<BigDecimal> hashed = new HashSet<>();
        hashed.add(a);
        hashed.add(b);
        System.out.println("HashSet size: " + hashed.size());

        TreeSet<BigDecimal> sorted = new TreeSet<>();
        System.out.println("TreeSet add a: " + sorted.add(a));
        System.out.println("TreeSet add b: " + sorted.add(b));
        System.out.println("TreeSet size: " + sorted.size());
        System.out.println("TreeSet stored: "
                + sorted.first().toPlainString());
        System.out.println("TreeSet contains 1.000: "
                + sorted.contains(new BigDecimal("1.000")));

        TreeMap<BigDecimal, String> sortedMap = new TreeMap<>();
        sortedMap.put(a, "first");
        sortedMap.put(b, "second");
        System.out.println("TreeMap size: " + sortedMap.size());
        System.out.println("TreeMap key scale: "
                + sortedMap.firstKey().scale());
        System.out.println("TreeMap lookup 1.000: "
                + sortedMap.get(new BigDecimal("1.000")));

        Map<BigDecimal, String> hashedMap = new HashMap<>();
        hashedMap.put(a, "first");
        hashedMap.put(b, "second");
        System.out.println("HashMap size: " + hashedMap.size());

        BigDecimal cleanA = a.stripTrailingZeros();
        BigDecimal cleanB = b.stripTrailingZeros();
        System.out.println("canonical equals: "
                + cleanA.equals(cleanB));
        System.out.println("canonical hash equals: "
                + (cleanA.hashCode() == cleanB.hashCode()));

        Comparator<BigDecimal> byValueThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        TreeSet<BigDecimal> strict = new TreeSet<>(byValueThenScale);
        strict.add(a);
        strict.add(b);
        System.out.println("strict TreeSet size: " + strict.size());

        BigDecimal large = new BigDecimal("600.0")
                .stripTrailingZeros();
        System.out.println("600.0 canonical: " + large.toString());
        System.out.println("0.000 canonical: "
                + new BigDecimal("0.000")
                        .stripTrailingZeros().toString());
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalSortedSetDemo.java
java BigDecimalSortedSetDemo
```

Kết quả:

```text
a scale: 1
b scale: 2
equals: false
compareTo: 0
hash equals: false
HashSet size: 2
TreeSet add a: true
TreeSet add b: false
TreeSet size: 1
TreeSet stored: 1.0
TreeSet contains 1.000: true
TreeMap size: 1
TreeMap key scale: 1
TreeMap lookup 1.000: second
HashMap size: 2
canonical equals: true
canonical hash equals: true
strict TreeSet size: 2
600.0 canonical: 6E+2
0.000 canonical: 0
```

Giải thích các điểm chính:

1. `a` và `b` biểu diễn cùng trị số nhưng có scale 1 và 2 nên `equals()` là `false`, `compareTo()` là 0.
2. `HashSet` và `HashMap` giữ hai mục phân biệt vì dựa trên equality của `BigDecimal`.
3. `TreeSet` mặc định thêm `a` thành công, từ chối `b` vì natural ordering coi hai giá trị tương đương; nó còn `contains` giá trị `1.000`.
4. `TreeMap` giữ key đầu tiên với scale 1 và cập nhật value của key tương đương thành `"second"`.
5. Hai bản chuẩn hóa qua `stripTrailingZeros()` có cùng `equals` và hash.
6. Comparator tùy chỉnh `byValueThenScale` tách thêm các key có cùng trị số nhưng khác scale, nên `strict` có hai phần tử.
7. `stripTrailingZeros()` có thể trả số dạng lũy thừa 10 như `6E+2`; số 0 thường được chuẩn hóa thành `0`. Đây là thay đổi **biểu diễn**, dù trị số không đổi.

Kết quả trên không in trực tiếp thứ tự băm hay con số hash không cần thiết; ví dụ chỉ kiểm tra quan hệ hash có bằng nhau hay không.

## 7. Muốn TreeSet phân biệt scale thì dùng comparator nào?

Nếu nghiệp vụ yêu cầu xem `1.0` và `1.00` là **hai giá trị khác nhau**, comparator của tập hợp có thứ tự phải trả khác 0 khi scale khác nhau:

```java
Comparator<BigDecimal> byValueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);

TreeSet<BigDecimal> values = new TreeSet<>(byValueThenScale);
values.add(new BigDecimal("1.0"));
values.add(new BigDecimal("1.00"));
// size() == 2
```

Đầu tiên comparator so trị số, sau đó nếu cùng trị số thì so scale. Với `BigDecimal`, cùng trị số **và** cùng scale tương đương với `equals()` bằng nhau, do vậy comparator này **nhất quán với equals** trong miền các đối tượng `BigDecimal`.

Lợi ích: vừa có thứ tự số học để duyệt, vừa bảo toàn cách phân biệt scale của `BigDecimal.equals()`. Hạn chế: hai biểu diễn cùng trị số sẽ chiếm hai vị trí khác nhau; điều này đúng hoặc sai tùy bài toán. Comparator không làm thay đổi `BigDecimal.equals()` bên ngoài `TreeSet`.

**Cảnh báo:** không dùng `Comparator.comparing(BigDecimal::scale)` đơn lẻ nếu bạn cần phân biệt mọi giá trị. Hai số `1.00` và `2.00` có scale 2 nhưng trị số khác nhau; chỉ so scale sẽ coi chúng là trùng và đánh mất một phần tử.

## 8. Muốn coi cùng trị số là cùng key ở mọi collection?

Đôi khi nghiệp vụ xác định `1.0`, `1.00` và `1` là một. Khi đó bạn có thể chuẩn hóa trước khi lưu:

```java
static BigDecimal canonical(BigDecimal input) {
    return java.util.Objects.requireNonNull(
            input, "input").stripTrailingZeros();
}
```

Đây là phương thức minh họa đặt trong một lớp Java. Từ đó:

```java
Set<BigDecimal> numericKeys = new HashSet<>();
numericKeys.add(canonical(new BigDecimal("1.0")));
numericKeys.add(canonical(new BigDecimal("1.00")));
// size() == 1
```

Các key đã chuẩn hóa có `equals()`/`hashCode()` phù hợp với quan hệ “cùng trị số” đã chọn; `HashSet` và `TreeSet` (dùng natural ordering) giờ thống nhất hơn về nhóm key.

Tuy nhiên, quy tắc này **xóa mất khác biệt scale**. Nếu `1.00` mang thông tin đo lường, hiển thị hoặc định dạng hóa đơn thì không được âm thầm bỏ nó. Có thể giữ nguyên giá trị gốc ở một trường riêng để hiển thị và dùng canonical key cho việc tìm kiếm, miễn là phân tách rõ hai vai trò.

Một hướng khác là dùng value object định nghĩa equality theo trị số:

```java
record NumericKey(BigDecimal canonicalValue) {
    public NumericKey {
        canonicalValue = java.util.Objects.requireNonNull(
                canonicalValue, "canonicalValue")
                .stripTrailingZeros();
    }
}
```

Với record này, field được chuẩn hóa ngay khi khởi tạo, nên record sinh `equals`/`hashCode` dựa trên canonical value. Nếu cần sắp xếp `NumericKey`, phải cung cấp comparator phù hợp hoặc triển khai `Comparable`; việc nó là record **không tự khiến nó có natural ordering**.

### Lưu ý về `stripTrailingZeros()`

- `new BigDecimal("600.0").stripTrailingZeros()` có thể là `6E+2` với scale âm; nếu cần in dạng thập phân không dùng ký pháp khoa học thì dùng `toPlainString()` hoặc định dạng theo yêu cầu.
- `BigDecimal.ZERO` có scale 0; chuẩn hóa một giá trị 0 như `new BigDecimal("0.000")` bằng `stripTrailingZeros()` có thể cho zero với scale 0.
- Nếu cần scale cố định như 2 chữ số cho tiền tệ, cân nhắc `setScale(2, ...)` với chính sách làm tròn rõ ràng. Thao tác này không tương đương “bỏ số 0 vô nghĩa” trong mọi trường hợp.
- Tránh tự `new BigDecimal(0.1)` từ `double` khi cần đúng biểu diễn thập phân `0.1`; nó phản ánh giá trị nhị phân của `double`. Ưu tiên chuỗi thập phân hoặc `BigDecimal.valueOf(0.1)` khi phù hợp.
- Với tiền, currency cũng thuộc danh tính của giá trị nghiệp vụ: `1.00 USD` không giống `1.00 EUR` chỉ vì cùng `BigDecimal`.

## 9. Áp dụng vào bài toán cụ thể

### Tình huống A: danh sách ngưỡng số học

Bạn dùng `TreeSet<BigDecimal>` để lưu các ngưỡng so sánh. Cùng trị số `1.0` và `1.00` chỉ đại diện cho **một ngưỡng**, vì vậy natural ordering của `BigDecimal` là phù hợp. Dù vậy hãy nhớ khi lấy phần tử, scale có thể phản ánh **giá trị nào được chèn trước** chứ không phải một biểu diễn chuẩn duy nhất.

### Tình huống B: dữ liệu đo lường có ý nghĩa về độ chính xác

Bạn cần giữ `1.0` (một chữ số sau dấu thập phân) khác `1.00` (hai chữ số). Nếu cả hai đều phải nằm trong tập hợp có thứ tự, dùng comparator so **trị số trước, scale sau** để không mất một bản ghi.

### Tình huống C: khóa cache thống nhất trên HashMap và TreeMap

Nếu cùng trị số phải tra cứu như cùng key trong cả `HashMap` và `TreeMap`, chuẩn hóa dữ liệu ở **biên nhập** trước khi tạo key. Đảm bảo cả ghi và đọc dùng cùng quy tắc. Không trộn khóa chuẩn hóa và khóa gốc tùy nơi vì dễ tạo hành vi khó dự đoán.

### Tình huống D: kiểm thử và phát hiện lỗi

Dùng test có tối thiểu các giá trị `1`, `1.0`, `1.00`, `2.00`, `0.000` và một số có scale âm. Thử thêm, chứa, xóa, tìm map key; xác minh **đối tượng key được giữ lại** và **value sau khi put trùng**. Nếu dùng comparator custom, kiểm tra phản xạ, đối xứng về dấu, tính bắc cầu và nhất quán với yêu cầu equality.

## 10. Lỗi phổ biến

| Sai lầm | Điều xảy ra | Cách phòng tránh |
| --- | --- | --- |
| Nghĩ `BigDecimal.equals()` chỉ xét trị số | `1.0` và `1.00` bị xem là khác | Nhớ `equals` xét cả unscaled value và scale. |
| Nghĩ `TreeSet` xác định trùng bằng `equals()` | `TreeSet` bất ngờ giảm kích thước | Kiểm tra `compareTo`/`Comparator` vì so 0 được xem là trùng. |
| Dùng `TreeMap` và mong giữ hai key khác scale | Lệnh `put` sau cập nhật entry của key tương đương | Dùng comparator phân biệt scale nếu nghiệp vụ cần. |
| Nhìn `HashSet.size()` rồi suy ra `TreeSet.size()` giống hệt | Hai tập dùng quan hệ tương đương khác nhau | Xác định quy tắc equality dự kiến trước khi chọn cấu trúc. |
| Chỉ sắp theo scale | Các trị số khác nhưng cùng scale bị coi là trùng | Sắp theo trị số rồi dùng scale phá hòa. |
| Chuẩn hóa bằng `stripTrailingZeros` nhưng vẫn cần lưu scale gốc | Mất thông tin biểu diễn ban đầu | Giữ giá trị gốc riêng cho hiển thị/kiểm toán. |
| So `hashCode` để kết luận hai số bằng nhau | Hash collision có thể xảy ra | Dùng `equals` hoặc `compareTo` tùy ngữ nghĩa, không dùng hash như tiêu chí equality. |
| Tạo `BigDecimal` từ `double` tùy tiện | Giá trị thập phân có thể khác điều mong đợi | Dùng chuỗi chính xác hoặc `valueOf` theo mục đích. |
| Dùng `setScale` với chính sách làm tròn ngầm | Có thể làm mất thông tin số học hoặc gây `ArithmeticException` khi cần làm tròn | Nêu rõ scale và `RoundingMode` khi áp dụng. |

## 11. Checklist khi chọn SortedSet/SortedMap cho BigDecimal

1. Xác định **trùng nhau theo trị số** hay **trùng nhau theo trị số và scale**.
2. Kiểm tra nguồn dữ liệu có thể gửi các biểu diễn như `1.0`, `1.00`, `1E+0` hay không.
3. Nếu dùng natural ordering, hiểu `compareTo() == 0` quyết định trùng ở `TreeSet`/`TreeMap`.
4. Nếu cần nhất quán với `BigDecimal.equals()`, dùng comparator theo trị số rồi theo scale.
5. Nếu cần equality theo trị số trên cả các collection hash, dùng canonical key được chuẩn hóa nhất quán.
6. Không dùng hash hoặc ordinal hay định dạng hiển thị để thay cho quy tắc so sánh.
7. Tạo test cho thao tác `add`, `contains`, `put`, `get`, `remove` và quy tắc chèn trùng.
8. Giữ nguyên scale khi nó mang ý nghĩa nghiệp vụ; chỉ chuẩn hóa khi được phép.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả gì? `compareTo` thì sao?

**Đáp án:** `equals` trả `false` vì khác scale; `compareTo` trả `0` vì cùng trị số.

**Câu 2.** Thêm hai số đó vào `HashSet` và `TreeSet` mặc định sẽ có kích thước bao nhiêu?

**Đáp án:** `HashSet` có 2; `TreeSet` có 1.

**Câu 3.** Vì sao `TreeMap.put(1.00, value2)` có thể thay value đang gắn với key `1.0`?

**Đáp án:** Vì `TreeMap` nhận diện key tương đương qua so sánh thứ tự. `1.0.compareTo(1.00) == 0`.

**Câu 4.** Cần giữ hai giá trị cùng trị số khác scale trong `TreeSet`; chọn comparator nào?

**Đáp án:** So trị số theo natural order, sau đó so scale bằng `thenComparingInt(BigDecimal::scale)`.

**Câu 5.** Khi nào dùng `stripTrailingZeros` cho key?

**Đáp án:** Khi nghiệp vụ muốn những biểu diễn cùng trị số là cùng key, và chấp nhận bỏ khác biệt scale. Phải chuẩn hóa thống nhất khi ghi và tra cứu.

**Câu 6.** `BigDecimal` có bị lỗi vì `compareTo` không nhất quán với `equals` không?

**Đáp án:** Không. Đây là hai quan hệ được tài liệu API xác định. Lập trình viên cần hiểu rằng collection sắp xếp sử dụng comparator làm cơ sở tương đương và chọn cấu trúc/phép so phù hợp.

**Ghi nhớ:** `BigDecimal.equals()` xét **trị số và scale**, còn `BigDecimal.compareTo()` xét **trị số**. Vì `TreeSet`/`TreeMap` coi kết quả so sánh **0** là cùng phần tử/key, `1.0` và `1.00` chỉ chiếm một vị trí với natural ordering.