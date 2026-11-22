# Vì sao `BigDecimal.compareTo()` có thể bằng 0 khi `equals()` là `false`?

## 1. Hai câu hỏi khác nhau: bằng nhau về số học hay bằng nhau theo đối tượng?

`java.math.BigDecimal` lưu số thập phân với độ chính xác tùy ý. Đặc điểm quan trọng là mỗi `BigDecimal` gồm **giá trị nguyên không chia tỷ lệ** (`unscaledValue`) và **scale**. Giá trị toán học được tính bởi:

```text
value = unscaledValue × 10^(-scale)
```

Ví dụ:

| Biểu diễn | `unscaledValue()` | `scale()` | Giá trị toán học |
| --- | ---: | ---: | ---: |
| `new BigDecimal("2.0")` | 20 | 1 | 2 |
| `new BigDecimal("2.00")` | 200 | 2 | 2 |
| `new BigDecimal("2")` | 2 | 0 | 2 |
| `new BigDecimal("2E+1")` | 2 | -1 | 20 |

Vì vậy, hai `BigDecimal` có thể biểu thị **cùng một số** nhưng khác **scale**. Java cố ý dùng hai quy tắc khác nhau:

- **`a.compareTo(b) == 0`**: bằng nhau về **giá trị số học**; các số 2.0 và 2.00 được xem là ngang nhau.
- **`a.equals(b)`**: bằng nhau theo hợp đồng `BigDecimal.equals(Object)`; **cả giá trị số học và scale** phải bằng nhau.

Đây là hành vi được định nghĩa trong API `BigDecimal`, không phải lỗi làm tròn hay sai số dấu phẩy động. `BigDecimal` lưu chính xác các chữ số thập phân từ chuỗi đầu vào.

**Kết luận trực tiếp:** `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` là `true`, nhưng `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false`.

## 2. Chữ ký và hợp đồng của từng phương thức

```java
int compareTo(BigDecimal val)
boolean equals(Object obj)
int hashCode()
```

Các khai báo trên là **chữ ký minh họa**; đây không phải chương trình Java độc lập.

### `compareTo(BigDecimal)` so sánh thứ tự số học

Giá trị trả về là:

- **Âm** nếu số nhận lời gọi nhỏ hơn đối số.
- **0** nếu hai số ngang nhau về giá trị toán học.
- **Dương** nếu số nhận lời gọi lớn hơn đối số.

Không kiểm tra cụ thể `-1` hoặc `1`; API chỉ bảo đảm dấu của kết quả. Với `BigDecimal`, `compareTo` bỏ qua sự khác nhau không làm thay đổi giá trị số học, chẳng hạn các chữ số 0 ở cuối phần thập phân.

### `equals(Object)` đòi thêm scale bằng nhau

Đối với hai `BigDecimal`, `equals` xét cả **giá trị và scale**. Bởi vậy `2.0`, `2.00` và `2` là ba đại diện khác nhau theo `equals`, dù `compareTo` đều cho kết quả 0 giữa từng cặp.

`equals` cũng không coi một `BigDecimal` bằng một kiểu số khác như `Integer` hoặc `Double` dù chúng biểu thị cùng giá trị số học. `compareTo` là phương thức so sánh **với `BigDecimal`**, không phải công cụ so sánh tùy ý giữa các lớp `Number`.

### `hashCode()` phải tương thích với equals

Nếu `a.equals(b)` là `true`, chúng bắt buộc có cùng mã băm. Nhưng các `BigDecimal` **cùng giá trị số học mà khác scale** có thể có hash khác nhau. Vì `equals` đã coi chúng khác nhau, điều đó hoàn toàn hợp lệ.

Không được dùng `compareTo == 0` để tự kết luận hai đối tượng là cùng khóa trong `HashMap`, vì `HashMap` sử dụng hợp đồng `equals` và `hashCode`, không sử dụng thứ tự tự nhiên từ `compareTo`.

## 3. Ví dụ Java 17+: nhìn thấy rõ sự khác biệt

Tạo tệp `BigDecimalEqualityDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println(a.scale());
        System.out.println(b.scale());
        System.out.println(a.compareTo(b) == 0);
        System.out.println(a.equals(b));

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        System.out.println(hashSet.size());

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);
        System.out.println(treeSet.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "A");
        hashMap.put(b, "B");
        System.out.println(hashMap.size());
        System.out.println(hashMap.get(new BigDecimal("2.000")));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "A");
        treeMap.put(b, "B");
        System.out.println(treeMap.size());
        System.out.println(treeMap.get(new BigDecimal("2.000")));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
```

Kết quả:

```text
1
2
true
false
2
1
2
null
1
B
```

Diễn giải lần lượt:

1. `a.scale()` là 1; `b.scale()` là 2.
2. `a.compareTo(b) == 0` là `true` vì cả hai biểu thị số 2.
3. `a.equals(b)` là `false` vì scale khác nhau.
4. `HashSet` có **2 phần tử**: cấu trúc băm phân biệt chúng bằng hợp đồng `equals/hashCode`.
5. `TreeSet` có **1 phần tử**: với thứ tự tự nhiên, `compareTo == 0` được dùng để xác định các phần tử trùng nhau trong cây.
6. `HashMap` có **2 khóa**. Khóa `2.000` (scale 3) không `equals` với khóa scale 1 hay 2 đã thêm, nên `get` trả `null`.
7. `TreeMap` có **1 khóa theo thứ tự tự nhiên**: thêm `b` cập nhật giá trị `"B"` cho khóa tương đương với `a` theo `compareTo`. Tra cứu bằng `2.000` vẫn lấy `"B"`.

Đây là khác biệt quan trọng khi cùng một tập dữ liệu đi qua các cấu trúc collection khác nhau.

## 4. Vì sao HashSet và TreeSet có thể cho kết quả khác?

`HashSet` xác định một phần tử đã tồn tại hay chưa bằng cơ chế băm và equality (cùng tham chiếu hoặc `equals`). `HashMap` có cùng cơ sở nhận dạng **khóa**.

Ngược lại, `TreeSet` và `TreeMap` duy trì thứ tự bằng `Comparable.compareTo` hoặc `Comparator` được cung cấp. Chúng coi hai phần tử hoặc khóa là **tương đương trong thứ tự** khi phép so sánh trả 0.

Với `BigDecimal`:

```text
a = 2.0 (scale 1)         b = 2.00 (scale 2)
        |                          |
        +---- compareTo == 0 ------+     cùng giá trị số học
        |                          |
        +---- equals == false -----+     khác biểu diễn/scale

HashSet / HashMap: nhận hai khóa/phần tử khác nhau
TreeSet / TreeMap: nhận là cùng khóa/phần tử theo thứ tự tự nhiên
```

`BigDecimal` là ví dụ nổi bật về **natural ordering inconsistent with equals**: thứ tự tự nhiên của nó không nhất quán với `equals`. Thông thường, API `Comparable` khuyến nghị bảo đảm `compareTo(a, b) == 0` tương đương `a.equals(b)`, nhưng đây không phải điều bắt buộc mà mọi lớp `Comparable` đều thực hiện. Với `BigDecimal`, sự khác biệt được tài liệu Java công bố rõ.

Hệ quả: một `TreeSet<BigDecimal>` dùng natural ordering có thể không tuân thủ ngữ nghĩa bình đẳng tổng quát mà bạn kỳ vọng từ `Set`, bởi phần tử “trùng” được quyết định bằng `compareTo` thay vì `equals`. Mã sử dụng phải biết tiêu chí tương đương của collection.

Nếu yêu cầu là **mỗi giá trị số học chỉ xuất hiện một lần**, `TreeSet` với thứ tự tự nhiên có thể phù hợp. Nếu yêu cầu là **giữ phân biệt scale**, `HashSet` dùng `equals` mặc định có ý nghĩa khác; hoặc cần định nghĩa một comparator tương thích với `equals` nếu vẫn muốn duy trì thứ tự.

Ví dụ comparator phân biệt scale sau khi so sánh giá trị số học:

```java
Comparator<BigDecimal> byValueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
```

Đây là **đoạn mã minh họa**, cần `import java.math.BigDecimal;` và `import java.util.Comparator;`. Với các `BigDecimal` hữu hạn, comparator này trả 0 khi cả giá trị số học và scale bằng nhau, tương ứng với `BigDecimal.equals`. Khi dùng với `TreeSet<>(byValueThenScale)`, hai phần tử `2.0` và `2.00` được lưu riêng.

## 5. Tại sao việc giữ scale lại có ý nghĩa?

Scale không phải lúc nào cũng là chi tiết trình bày vô nghĩa. Nó có thể biểu thị độ chính xác hoặc quy ước về số chữ số thập phân:

- `2.0` và `2.00` là cùng một số, nhưng có thể đến từ hai phép đo hoặc hai quy tắc hiển thị khác nhau.
- Trong tính toán decimal, lựa chọn scale có thể ảnh hưởng đến **scale của kết quả**, cách chia số và nhu cầu làm tròn.
- Trong biểu diễn tiền tệ, dữ liệu có thể yêu cầu đúng hai chữ số thập phân; `2.00` phù hợp hơn `2` nếu định dạng lưu trữ yêu cầu scale 2.

Ví dụ, phép chia exact có thể bảo toàn sự khác nhau về scale:

```java
new BigDecimal("2.0").divide(new BigDecimal("3"),
                            2, RoundingMode.HALF_UP);
```

Đoạn minh họa trên cần `import java.math.BigDecimal;` và `import java.math.RoundingMode;`, trả giá trị toán học 0.67 với scale 2. Thông số scale và rounding mode được chỉ định rõ để tránh phụ thuộc ngầm vào độ chính xác đầu vào.

Lưu ý **scale không tự chứng minh ý nghĩa nghiệp vụ**. Nếu hệ thống coi 2.0 và 2.00 là cùng một giá trị, cần định nghĩa rõ quy tắc đó ở API hoặc tại ranh giới dữ liệu, không lấy `equals` mặc định làm tiêu chí khi nó không khớp.

## 6. Làm thế nào nếu muốn bình đẳng theo giá trị số học?

Trước khi dùng `BigDecimal` làm khóa hoặc phần tử tập hợp, hãy chọn rõ **quan hệ tương đương**. Hai biểu diễn `2.0` và `2.00` có cùng giá trị số học nhưng khác nhau theo `equals`. Có ba cách xử lý theo ba mục tiêu, không nên trộn lẫn:

### Cách A — Chỉ cần hỏi hai số có cùng giá trị hay không

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
boolean numericallyEqual = a.compareTo(b) == 0; // true
~~~

Đây là phép so trực tiếp, **không thay đổi** `equals` hay `hashCode`. Khi dùng hai số chưa chuẩn hóa làm khóa `HashMap`, chúng vẫn là hai khóa riêng. `compareTo(null)` ném `NullPointerException`; xử lý `null` trước theo quy định dữ liệu.

### Cách B — Muốn một khóa băm cho mỗi giá trị số học

Chuẩn hóa tại **cả thời điểm lưu lẫn truy vấn**, trước khi đưa số vào `HashMap` hoặc `HashSet`:

~~~java
BigDecimal first = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal second = new BigDecimal("2.00").stripTrailingZeros();
Set<BigDecimal> values = new HashSet<>();
values.add(first);
values.add(second);
System.out.println(values.size()); // 1
~~~

Đoạn này dùng các import `java.math.BigDecimal`, `java.util.Set` và `java.util.HashSet`; có thể đặt trong `main`. Cả hai giá trị chuẩn hóa đều có scale 0. Nếu tự viết một khóa mà `equals` dùng `compareTo == 0`, **`hashCode` cũng phải dựa trên đại diện đã chuẩn hóa**, không dùng trực tiếp `BigDecimal.hashCode` của giá trị có scale tùy ý.

Cần nhớ rằng `stripTrailingZeros()` có thể tạo **scale âm**: `1000.00` thành `1E+3`, và chuẩn hóa `0.000` thành số không scale 0. Do đó, phương án này **không phù hợp nếu scale ban đầu là dữ liệu nghiệp vụ cần giữ**.

### Cách C — Miền nghiệp vụ quy định scale cố định

Ví dụ ứng dụng quy định đúng hai chữ số thập phân:

~~~java
BigDecimal amount = new BigDecimal("2.0")
        .setScale(2, RoundingMode.UNNECESSARY); // 2.00
~~~

Cần import `java.math.RoundingMode`. Chế độ `UNNECESSARY` làm chương trình ném `ArithmeticException` nếu đầu vào như `2.001` không thể chuyển sang scale 2 mà không làm tròn. Nếu được phép làm tròn, phải chọn `RoundingMode` theo chính sách nghiệp vụ, không mặc định dùng `HALF_UP`.

**Lựa chọn nhanh:** so hai số riêng lẻ → `compareTo`; khử trùng theo giá trị trong hash collection → chuẩn hóa khóa nhất quán; cần giữ đúng độ chính xác/biểu diễn quy định → scale cố định và kiểm soát làm tròn. Bài 3 và 4 ở trên đã có chương trình hoàn chỉnh để kiểm chứng sự khác nhau giữa cấu trúc băm và cấu trúc sắp xếp.

## 7. Lỗi thường gặp khi làm việc với BigDecimal

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `equals` để hỏi “hai số có cùng giá trị toán học?” | `equals` còn so scale | Dùng `compareTo(...) == 0` |
| Dùng `compareTo == 0` rồi giả định `HashSet` sẽ gộp phần tử | HashSet dựa vào `equals/hashCode` | Chuẩn hóa trước khi thêm hoặc chọn collection/phép so sánh phù hợp |
| Xem `compareTo == 0` là dấu hiệu `hashCode` phải bằng nhau | Hợp đồng hash chỉ yêu cầu giống nhau nếu `equals == true` | Hiểu đúng hai điều kiện bình đẳng khác nhau |
| Dùng `==` so sánh hai đối tượng `BigDecimal` | `==` kiểm tra cùng tham chiếu | Chọn `equals` hoặc `compareTo` theo mục đích |
| Tạo decimal từ `new BigDecimal(0.1)` và kỳ vọng đúng 0.1 | `0.1` dạng `double` là xấp xỉ nhị phân | Ưu tiên `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` |
| Gọi `stripTrailingZeros` rồi kỳ vọng `toString()` giữ nguyên dạng decimal | Có thể chuyển sang ký pháp khoa học, scale âm | Dùng `toPlainString` để hiển thị số không có mũ khi thích hợp |
| Đổi tiêu chí equality giữa các phần của hệ thống | Khóa tra cứu và kết quả tập hợp khác nhau | Ghi rõ chính sách scale, làm tròn và chuẩn hóa tại ranh giới |

Lưu ý `BigDecimal` bất biến: `setScale` và `stripTrailingZeros` trả về kết quả `BigDecimal`, không sửa đối tượng ban đầu. Nếu muốn dùng kết quả chuẩn hóa, phải gán lại biến hoặc lưu giá trị trả về.

## 8. Checklist trước khi dùng BigDecimal làm khóa hoặc phần tử set

1. Xác định tiêu chí “trùng”: **cùng giá trị số học** hay **cùng giá trị và scale**?
2. Nếu chỉ cần so sánh hai số theo nghiệp vụ, dùng `compareTo` và kiểm tra **kết quả bằng 0**.
3. Nếu dùng `HashMap<BigDecimal, ...>` hoặc `HashSet<BigDecimal>`, nhớ rằng scale là một phần của equality; chuẩn hóa đầu vào nếu mục đích là gộp theo số học.
4. Nếu dùng `TreeMap`/`TreeSet`, hiểu comparator hoặc natural ordering quyết định khi nào hai khóa/phần tử là tương đương. Nếu cần phân biệt scale, hãy bổ sung tiêu chí scale vào comparator.
5. Với dữ liệu có quy tắc thập phân cố định, quy định scale và rounding mode một cách tường minh, nhất là trước khi lưu và tra cứu khóa.
6. Khi chuẩn hóa bằng `stripTrailingZeros`, kiểm tra trường hợp **0** và các số có nhiều số 0 ở cuối như `1000.00`, vì kết quả có thể có scale âm.
7. Viết kiểm thử cả `2.0`, `2.00`, `2`, `0.000` và trường hợp bắt buộc làm tròn. Kiểm thử khác biệt giữa `HashSet` và `TreeSet` nếu hệ thống sử dụng cả hai.

**Tự kiểm tra:**

- `new BigDecimal("5.0").compareTo(new BigDecimal("5.00"))` trả gì? **0**.
- `new BigDecimal("5.0").equals(new BigDecimal("5.00"))` trả gì? **`false`**, do scale 1 và 2.
- Thêm hai đối tượng ấy vào `HashSet` thì có bao nhiêu phần tử? **2**.
- Thêm chúng vào `TreeSet` dùng thứ tự tự nhiên thì có bao nhiêu phần tử? **1**.
- Làm sao để chúng bằng nhau theo `equals` khi dùng làm khóa hash theo giá trị số học? **Chuẩn hóa cùng một quy tắc**, ví dụ dùng `stripTrailingZeros()` trước khi thêm và tra cứu.

**Ghi nhớ:** Với `BigDecimal`, **`compareTo == 0` nói về giá trị số học**, còn **`equals == true` nói về giá trị số học cùng scale**. Sự khác biệt này quyết định cách `HashMap`, `HashSet`, `TreeMap` và `TreeSet` nhận diện giá trị trùng nhau; chọn tiêu chí nhất quán với nhu cầu của ứng dụng.