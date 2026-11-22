# BigDecimal: thứ tự tự nhiên không nhất quán với equals

Trong Java, `BigDecimal` có một đặc điểm dễ gây lỗi: **hai giá trị bằng nhau về mặt số học có thể được `compareTo()` xem là bằng nhau nhưng `equals()` lại xem là khác nhau**. Ví dụ `new BigDecimal("2.0")` và `new BigDecimal("2.00")` cùng mang giá trị số 2, song khác số chữ số sau dấu thập phân (`scale`). Sự khác biệt này ảnh hưởng trực tiếp đến sắp xếp, loại phần tử trùng, kiểm tra `contains()` và các thao tác khóa trong `Set`/`Map`.

Mục tiêu của bài:
- Giải thích chính xác khái niệm **natural ordering consistent with equals** của `Comparable` và lý do `BigDecimal` là ngoại lệ có chủ ý.
- Dự đoán kết quả `compareTo()`, `equals()`, `hashCode()` cùng tác động đối với `HashSet`, `TreeSet`, `HashMap` và `TreeMap`.
- Chọn quy tắc so sánh/chuẩn hóa phù hợp tùy việc ứng dụng xem **giá trị số** hay **biểu diễn kèm `scale`** là danh tính.
- Tránh mất dữ liệu về `scale` hoặc bị gộp khóa ngoài ý muốn.

## 1. “Thứ tự tự nhiên nhất quán với equals” nghĩa là gì?

Một lớp triển khai `Comparable<T>` có **thứ tự tự nhiên** do phương thức `compareTo(T other)` xác định. Theo hợp đồng của `Comparable`, `compareTo()` trả về số âm khi đối tượng đứng trước, số dương khi đứng sau và `0` khi hai đối tượng **tương đương theo thứ tự**. Đừng phụ thuộc độ lớn tuyệt đối của kết quả khi lớp khác có thể trả về những số nguyên khác ngoài -1, 0, 1.

Thứ tự tự nhiên được gọi là **nhất quán với `equals`** khi với *mọi* cặp `a`, `b` hợp lệ:

~~~text
(a.compareTo(b) == 0)  ==  a.equals(b)
~~~

Ở đây dấu `==` ngoài cùng diễn đạt sự bằng nhau giữa hai giá trị `boolean`: hai mệnh đề cần cùng đúng hoặc cùng sai.

Java khuyến nghị tính nhất quán này vì giao diện `Set`/`Map` nói về danh tính thông qua `equals()`, trong khi những cấu trúc có sắp xếp như `TreeSet`/`TreeMap` dựa trên **kết quả so sánh bằng 0**. Tuy nhiên, đây là khuyến nghị mạnh chứ không phải điều kiện bắt buộc để triển khai `Comparable`. Tài liệu API xác định rõ `BigDecimal` là một ngoại lệ, vì nó dùng một quy tắc cho **thứ tự số học** và quy tắc khác cho **bằng nhau theo biểu diễn**.

**Hai mệnh đề phải phân biệt:**

1. `a.compareTo(b) == 0`: cùng giá trị số, có thể khác `scale`.
2. `a.equals(b)`: cùng giá trị số **và** cùng `scale`.

Với `BigDecimal`, `equals()` bằng `true` thì `compareTo() == 0` cũng đúng; chiều ngược lại không nhất thiết đúng. Đây là **sự không nhất quán về quan hệ tương đương**, không phải là lỗi sắp thứ tự tăng/giảm hay việc `compareTo()` vi phạm tính bắc cầu.

## 2. Nguồn gốc: unscaled value và scale

`BigDecimal` biểu diễn một số thập phân bằng một số nguyên `unscaledValue` và `scale`:

~~~text
giá trị số = unscaledValue × 10^(-scale)
~~~

| Chuỗi khởi tạo | `unscaledValue()` | `scale()` | Giá trị số |
|---|---:|---:|---:|
| `"2"` | 2 | 0 | 2 |
| `"2.0"` | 20 | 1 | 2 |
| `"2.00"` | 200 | 2 | 2 |
| `"2E+0"` | 2 | 0 | 2 |
| `"0.00"` | 0 | 2 | 0 |
| `"0.000"` | 0 | 3 | 0 |

`compareTo()` nhìn vào **giá trị số**, nên coi `2`, `2.0` và `2.00` là tương đương. Ngược lại, `equals()` còn xét `scale`, do đó `2.0` khác `2.00` theo phương thức này. Một cách dễ nhớ: thêm số 0 cuối phần thập phân có thể giữ nguyên *giá trị* nhưng thay đổi *biểu diễn*.

Hai giá trị có cùng `scale` và cùng giá trị số thì có cùng `unscaledValue`, do đó `equals()` trả về `true`. Dấu cách trình bày từ chuỗi đầu vào cũng không trở thành thuộc tính riêng trong `BigDecimal`; hai chuỗi khác nhau có thể tạo ra đối tượng `equals()` bằng nhau nếu chúng cho đúng cùng cặp giá trị/số mũ.

## 3. So sánh rõ ba kiểu kiểm tra

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
System.out.println(a == b);              // false
~~~

Đây là *đoạn minh họa đặt bên trong phương thức* và cần `import java.math.BigDecimal;`. Chương trình đầy đủ chạy độc lập nằm ở mục 5.

| Cách kiểm tra | Tiêu chí | `2.0` so với `2.00` |
|---|---|---|
| `a.compareTo(b) == 0` | Bằng giá trị số | `true` |
| `a.equals(b)` | Bằng giá trị số và `scale` | `false` |
| `a == b` | Cùng tham chiếu đối tượng | `false` với hai lần `new` riêng |
| `a.compareTo(b) < 0` | Nhỏ hơn về giá trị số | `false` |
| `a.compareTo(b) > 0` | Lớn hơn về giá trị số | `false` |

**`hashCode()` đi theo `equals()`, không theo `compareTo()`.** Hai đối tượng có `equals() == true` bắt buộc cùng `hashCode()`. Hai đối tượng chỉ bằng giá trị số nhưng khác `scale` không được `BigDecimal` hứa có hash giống nhau; hàm băm của nó cũng xét `scale`. Vì thế, dữ liệu băm không tự xem `2.0` và `2.00` là một khóa.

Không dùng `a.hashCode() == b.hashCode()` làm phép thử bằng nhau: hash collision vẫn có thể xảy ra, và hash chỉ là công cụ chọn bucket, trong khi `equals()` xác nhận danh tính.

## 4. Vì sao điều này ảnh hưởng đến Set và Map?

Hai họ cấu trúc dữ liệu sử dụng quy tắc “trùng” khác nhau:

| Cấu trúc | Mặc định xác định trùng bằng | `2.0` và `2.00` cùng tồn tại? |
|---|---|---|
| `HashSet<BigDecimal>` | `hashCode()` kết hợp `equals()` | **Có**, hai phần tử |
| `TreeSet<BigDecimal>` | `compareTo() == 0` nếu không chỉ định comparator | **Không**, một phần tử |
| `HashMap<BigDecimal, V>` | `hashCode()` kết hợp `equals()` cho khóa | **Có**, hai khóa |
| `TreeMap<BigDecimal, V>` | `compareTo() == 0` nếu không chỉ định comparator | **Không**, lần `put` sau cập nhật value của khóa tương đương |

Các cấu trúc `TreeSet`/`TreeMap` có hành vi **xác định rõ theo hợp đồng sắp xếp**, dù việc dùng `BigDecimal` với thứ tự mặc định khiến quan hệ danh tính theo cây không tương thích với cách `Set`/`Map` thông thường diễn đạt thông qua `equals`.

Điều này có hai kiểu lỗi phổ biến:
- Hệ thống cần phân biệt `2.0` và `2.00`, nhưng chuyển từ `HashSet` sang `TreeSet` dẫn tới phần tử thứ hai không được thêm.
- Hệ thống dùng `TreeMap` để lưu dữ liệu theo đơn giá. Khóa `2.00` được xem là khóa tương đương với `2.0`, làm `put` sau **thay value cũ**, thay vì tạo một entry mới.

Bản thân việc sắp xếp theo `compareTo()` không “sai”; vấn đề xuất hiện khi nghiệp vụ ngầm coi **mỗi cách biểu diễn** là một danh tính riêng nhưng lại chọn collection gộp theo **giá trị số**.

## 5. Chương trình Java 17+ chạy độc lập

Tạo tệp `BigDecimalOrderDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalOrderDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("compareTo: " + a.compareTo(b));
        System.out.println("equals: " + a.equals(b));
        System.out.println("same scale: " + (a.scale() == b.scale()));

        HashSet<BigDecimal> hashSet = new HashSet<>();
        System.out.println("hash add a: " + hashSet.add(a));
        System.out.println("hash add b: " + hashSet.add(b));
        System.out.println("hash size: " + hashSet.size());

        TreeSet<BigDecimal> treeSet = new TreeSet<>();
        System.out.println("tree add a: " + treeSet.add(a));
        System.out.println("tree add b: " + treeSet.add(b));
        System.out.println("tree size: " + treeSet.size());
        System.out.println("tree contains b: " + treeSet.contains(b));

        HashMap<BigDecimal, String> hashMap = new HashMap<>();
        System.out.println("hash first put: " + hashMap.put(a, "first"));
        System.out.println("hash second put: " + hashMap.put(b, "second"));
        System.out.println("hash map size: " + hashMap.size());
        System.out.println("hash get a: " + hashMap.get(a));

        TreeMap<BigDecimal, String> treeMap = new TreeMap<>();
        System.out.println("tree first put: " + treeMap.put(a, "first"));
        System.out.println("tree second put: " + treeMap.put(b, "second"));
        System.out.println("tree map size: " + treeMap.size());
        System.out.println("tree get a: " + treeMap.get(a));
        System.out.println("tree first key: " + treeMap.firstKey());

        Comparator<BigDecimal> valueThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        TreeSet<BigDecimal> representationSet = new TreeSet<>(valueThenScale);
        representationSet.add(a);
        representationSet.add(b);
        System.out.println("representation size: " + representationSet.size());
        System.out.println("representation contents: " + representationSet);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalOrderDemo.java
java BigDecimalOrderDemo
~~~

Kết quả:

~~~text
compareTo: 0
equals: false
same scale: false
hash add a: true
hash add b: true
hash size: 2
tree add a: true
tree add b: false
tree size: 1
tree contains b: true
hash first put: null
hash second put: null
hash map size: 2
hash get a: first
tree first put: null
tree second put: first
tree map size: 1
tree get a: second
tree first key: 2.0
representation size: 2
representation contents: [2.0, 2.00]
~~~

Giải thích kết quả:

1. `compareTo: 0` không kéo theo `equals: true` vì `a.scale() == 1` trong khi `b.scale() == 2`.
2. `HashSet` thêm được cả hai. `TreeSet` thêm `a` trước, rồi từ chối `b` vì `compareTo() == 0`; `treeSet.contains(b)` vẫn trả `true`. Điều này không có nghĩa phần tử `b` đã được lưu nguyên dạng trong cây.
3. `HashMap.put(a, "first")` và `put(b, "second")` tạo hai khóa riêng. `TreeMap.put(b, "second")` cập nhật entry theo thứ tự so sánh nên trả lại `"first"` và kích thước vẫn bằng 1.
4. Khi `TreeMap` có khóa tương đương theo comparator, lần ghi thứ hai thay giá trị của entry đang có; trong ví dụ `firstKey()` vẫn in `2.0`, là đối tượng khóa được chèn đầu tiên.
5. Comparator tự định nghĩa `valueThenScale` sắp theo giá trị số **rồi so tiếp `scale` nếu giá trị bằng nhau**, vì vậy xem `a` và `b` là khác và giữ cả hai trong `TreeSet`.

Chương trình chỉ in kích thước và kết quả kiểm tra đối với `HashSet`/`HashMap`, tránh giả định thứ tự duyệt của hash collection là cố định. Ví dụ này không sử dụng `double` để khởi tạo dữ liệu đầu vào.

## 6. Sorted collections dùng “bằng nhau theo comparator”

Trong `TreeSet`, `add()`, `contains()` và `remove()` xác định đối tượng tương đương thông qua `compareTo() == 0` khi dùng thứ tự tự nhiên. Trong `TreeMap`, `put()`, `get()`, `containsKey()` và `remove()` cũng dùng tương đương theo comparator cho khóa. Một `Comparator` tùy chỉnh sẽ thay cho `compareTo()` trong những quyết định đó.

Hãy xem kỹ hai thao tác này:

~~~java
TreeSet<BigDecimal> prices = new TreeSet<>();
prices.add(new BigDecimal("8.0"));

boolean found = prices.contains(new BigDecimal("8.00")); // true
boolean added = prices.add(new BigDecimal("8.00"));      // false
~~~

Kết quả `found == true` chỉ nói rằng trong tập có một phần tử **bằng theo thứ tự** với `8.00`, không chứng minh đối tượng `8.00` theo đúng `scale` đã được lưu. Nếu tiếp tục `prices.remove(new BigDecimal("8.000"))`, thao tác có thể xóa phần tử `8.0` dù `equals()` giữa chúng là `false`.

Với `TreeMap`, rủi ro tương tự đặc biệt quan trọng nếu khóa đại diện cho **một mục nghiệp vụ phải phân biệt theo quy cách ghi**: lần ghi thứ hai có thể thay payload của khóa đầu. Quy tắc so sánh phải được chọn rõ trước khi tạo collection.

## 7. Sắp xếp List, tìm kiếm và min/max

`Collections.sort(list)`, `List.sort(null)` và `Arrays.sort(array)` sử dụng thứ tự tự nhiên của `BigDecimal` khi không cung cấp comparator. Điều này có nghĩa chúng sắp **theo giá trị số**. Những đối tượng bằng nhau theo `compareTo` không bị bắt buộc trở thành cùng một đối tượng hoặc bị loại khỏi `List`. `List` giữ đủ số phần tử.

Nếu dùng `Collections.binarySearch(sortedList, target)` theo thứ tự tự nhiên, kết quả có thể trỏ vào phần tử bằng **giá trị số** nhưng khác `scale` so với `target`. Nếu có nhiều phần tử được xem là tương đương theo comparator, API không hứa trả lại một phần tử cụ thể trong số đó. Muốn tìm **đúng biểu diễn**, phải dùng một tiêu chí có xét `scale` hoặc duyệt kiểm tra bằng `equals()`.

Tương tự, `min()` và `max()` của `BigDecimal` chọn theo `compareTo()`. Nếu giá trị so sánh bằng 0, chúng trả về chính đối tượng nhận lệnh (`this`), vì vậy `min`/`max` không tự chuẩn hóa `scale`:

~~~java
BigDecimal one = new BigDecimal("2.0");
BigDecimal two = new BigDecimal("2.00");

System.out.println(one.min(two)); // 2.0
System.out.println(two.min(one)); // 2.00
~~~

Đây không phải lỗi trong thuật toán min/max; hai đối tượng bằng nhau theo thứ tự số học, và biểu diễn được chọn là một phần của hợp đồng phương thức.

## 8. Chiến lược A: danh tính dựa trên giá trị số

Nếu nghiệp vụ nói rằng `2.0`, `2.00` và `2.000` phải là **cùng một giá trị** để lọc trùng, tổng hợp hoặc tra cứu, có thể **chuẩn hóa trước khi sử dụng làm khóa**. Một cách phổ biến là `stripTrailingZeros()`:

~~~java
BigDecimal a = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("2.00").stripTrailingZeros();

System.out.println(a);            // 2
System.out.println(b);            // 2
System.out.println(a.equals(b));  // true
~~~

Khi chuẩn hóa hai phía theo cùng quy tắc, `HashSet`/`HashMap` có thể thực hiện danh tính số học nhất quán với `TreeSet`/`TreeMap` cho những giá trị đã chuẩn hóa. Cần thực hiện chuẩn hóa **ngay tại biên nhận dữ liệu hoặc trước mọi lần `put`, `get`, `contains` và `remove`**. Chuẩn hóa chỉ lúc chèn mà không chuẩn hóa lúc tra cứu sẽ tiếp tục sinh ra hành vi khó hiểu.

Ví dụ quy tắc chuẩn hóa:

~~~java
private static BigDecimal numericKey(BigDecimal value) {
    return value.stripTrailingZeros();
}
~~~

Đoạn trên cần đặt bên trong một lớp Java. `stripTrailingZeros()` giữ **giá trị số**, nhưng có thể đổi cách hiển thị và `scale`. Chẳng hạn `new BigDecimal("1000.00").stripTrailingZeros()` có thể hiển thị `1E+3` với `scale = -3`; mọi giá trị 0 sau chuẩn hóa có kết quả tương đương `BigDecimal.ZERO` (`scale = 0`).

**Giới hạn quan trọng:** Không áp dụng chuẩn hóa nếu `scale` biểu đạt số chữ số thập phân theo hợp đồng, độ phân giải phép đo, hoặc quy tắc số chữ số tiền tệ cần được giữ nguyên. Khi đó `2.0` và `2.00` có thể cần được phân biệt.

## 9. Chiến lược B: danh tính gồm giá trị số và scale

Khi bắt buộc phải giữ cả hai biểu diễn trong một sorted collection, dùng comparator sắp theo **giá trị số rồi tới `scale`**:

~~~java
Comparator<BigDecimal> valueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);

TreeSet<BigDecimal> values = new TreeSet<>(valueThenScale);
values.add(new BigDecimal("2.0"));
values.add(new BigDecimal("2.00"));

System.out.println(values.size()); // 2
~~~

Phép so sánh này nhất quán với `BigDecimal.equals()`:

- Nếu giá trị số khác nhau, comparator phân biệt.
- Nếu giá trị số bằng nhau nhưng `scale` khác nhau, bước `thenComparingInt` phân biệt.
- Nếu giá trị số và `scale` đều bằng nhau, hai đối tượng `BigDecimal` cũng bằng nhau theo `equals()`, nên comparator trả 0.

**Không** dùng `Comparator.comparing(BigDecimal::stripTrailingZeros)` nếu mục tiêu là giữ riêng từng `scale`: cách đó vẫn gộp những giá trị số bằng nhau. Cũng không so sánh chỉ bằng `scale`, vì hai giá trị số khác nhau nhưng có cùng `scale` sẽ bị coi là trùng. Thứ tự “giá trị trước, `scale` sau” là điều kiện quyết định trong chiến lược này.

Lưu ý comparator này phù hợp với đúng ngữ nghĩa `BigDecimal.equals()`, không phải mọi yêu cầu nghiệp vụ. Ví dụ một hệ thống có định danh giao dịch thì hai số `2.00` đến từ **hai giao dịch khác nhau** vẫn phải giữ cả hai; tập hợp các `BigDecimal` không thể mang đầy đủ định danh giao dịch. Khi đó nên lưu thực thể hoặc khóa có định danh riêng.

## 10. Chiến lược C: quy định scale cố định theo nghiệp vụ

Nếu toàn hệ thống yêu cầu **hai chữ số thập phân**, hãy chuẩn hóa về `scale = 2` ngay khi xác nhận đầu vào. Khi đó `2`, `2.0`, `2.00` có thể trở thành cùng `BigDecimal("2.00")`, nếu việc chuyển đổi không làm mất dữ liệu.

~~~java
BigDecimal first = new BigDecimal("2.0").setScale(2);
BigDecimal second = new BigDecimal("2.00").setScale(2);
System.out.println(first.equals(second)); // true
~~~

`setScale(2)` **không phải** phép nhân với 100; nó yêu cầu biểu diễn giá trị ở hai vị trí thập phân. Nếu cần bỏ chữ số khác 0, phiên bản không truyền rounding mode ném `ArithmeticException`:

~~~java
// Ném ArithmeticException vì 2.005 không biểu diễn chính xác với scale 2:
new BigDecimal("2.005").setScale(2);
~~~

Nếu nghiệp vụ cho phép làm tròn, hãy chỉ định rõ quy tắc, ví dụ `setScale(2, RoundingMode.HALF_EVEN)`. Làm tròn có thể thay đổi **giá trị số**, vì vậy không thể mặc nhiên coi việc chuẩn hóa `scale` là thao tác vô hại.

Có thể phối hợp chiến lược: dùng số đã chuẩn hóa để tính tiền, nhưng giữ chuỗi đầu vào hoặc metadata riêng khi cần kiểm toán độ chính xác mà người dùng khai báo. Không dùng một đối tượng `BigDecimal` duy nhất để giải quyết đồng thời hai định nghĩa danh tính mâu thuẫn nhau.

## 11. Vì sao scale đôi khi thực sự quan trọng?

`BigDecimal.equals()` phân biệt biểu diễn không chỉ vì “số 0 thừa”. Một số phép toán cung cấp kết quả phụ thuộc vào `scale` của toán hạng. JavaDoc đưa ra ví dụ hai phiên bản của số 2 khi dùng overload phép chia với `RoundingMode`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal divisor = new BigDecimal("3");

System.out.println(
        new BigDecimal("2.0").divide(divisor, RoundingMode.HALF_UP)
); // 0.7

System.out.println(
        new BigDecimal("2.00").divide(divisor, RoundingMode.HALF_UP)
); // 0.67
~~~

Overload `divide(BigDecimal, RoundingMode)` dùng `scale` của **số bị chia** làm `scale` kết quả, rồi làm tròn theo `RoundingMode`. Hai số cùng giá trị 2 nhưng có `scale` khác dẫn đến số chữ số giữ lại khác nhau. Đoạn trên đặt trong phương thức Java; nó minh họa một lý do thực tế phải hiểu `scale` trước khi chuẩn hóa.

Đối với phép chia cần quy định precision theo `MathContext`, hoặc `scale` kết quả bằng `divide(divisor, requestedScale, roundingMode)`, hãy chọn overload phù hợp một cách có ý thức. Không suy rằng `compareTo() == 0` cho phép hoán đổi mọi đối tượng mà không đổi kết quả biểu diễn trong toàn bộ API số học.

## 12. Những lỗi phổ biến cần tránh

1. **Dùng `equals()` để so sánh số tiền theo độ lớn hoặc bằng giá trị:** với `BigDecimal`, `amount.compareTo(other) == 0` diễn đạt bằng số học. Muốn kiểm tra nhỏ/lớn thì dùng `< 0` hoặc `> 0` trên kết quả `compareTo()`.
2. **Dùng `HashSet` rồi chuyển sang `TreeSet` mà không đánh giá lại danh tính:** cùng dữ liệu đầu vào có thể cho kích thước và kết quả `contains()` khác nhau.
3. **Dùng `TreeMap` để lưu hai khóa chỉ khác `scale`:** lần `put` sau sẽ cập nhật value thay vì tăng kích thước map.
4. **Cho rằng `TreeSet.contains(x)` đồng nghĩa có phần tử `equals(x)`:** `contains()` của cây áp dụng quy tắc so sánh; với `BigDecimal` mặc định, hai quy tắc có thể bất đồng.
5. **So sánh `BigDecimal` bằng `==`:** toán tử này so sánh tham chiếu trong Java, không phải bằng nhau về giá trị số hoặc `scale`.
6. **Chỉ dựa vào `hashCode()`:** hash bằng nhau không bảo đảm `equals()` bằng nhau; nếu muốn danh tính số học trong hash collection, chuẩn hóa khóa theo quy ước.
7. **Tưởng `stripTrailingZeros()` chỉ là thay đổi hiển thị:** kết quả có thể có `scale` âm, và `equals()` của kết quả với đối tượng ban đầu có thể khác.
8. **Dùng `new BigDecimal(0.1)` để lập ví dụ hoặc khóa:** constructor từ `double` đưa vào giá trị nhị phân thực sự của `double`, thường không bằng đúng thập phân được viết. Dùng chuỗi như `"0.1"` hoặc `BigDecimal.valueOf(0.1)` khi dữ liệu gốc là giá trị thập phân quen thuộc.
9. **Đọc quy tắc comparator bằng mắt nhưng quên tra cứu:** với `TreeMap`/`TreeSet` tùy chỉnh, cùng comparator phải được áp dụng cho toàn bộ vòng đời collection; dữ liệu dùng qua nhiều collection cần chính sách tương đương rõ ràng.
10. **Tưởng thêm comparator luôn bảo toàn mọi bản ghi:** nếu hai bản ghi có cùng số và cùng `scale` nhưng là hai thực thể khác nhau, comparator ở mục 9 vẫn coi chúng tương đương. Hãy dùng khóa danh tính thực thể phù hợp.

## 13. Bài tập kiểm tra hiểu biết

### Bài 1: dự đoán số lượng

~~~java
BigDecimal x = new BigDecimal("0.0");
BigDecimal y = new BigDecimal("0.00");

HashSet<BigDecimal> h = new HashSet<>();
TreeSet<BigDecimal> t = new TreeSet<>();
h.add(x);
h.add(y);
t.add(x);
t.add(y);
~~~

**Đáp án:** `h.size() == 2`, `t.size() == 1`. `x.compareTo(y) == 0` nhưng `x.equals(y) == false`. Nếu gọi `stripTrailingZeros()` trên cả `x` và `y` **trước khi thêm**, cả hai cùng trở thành dạng zero chuẩn và `HashSet` chỉ còn một phần tử.

### Bài 2: Map nào ghi đè?

~~~java
BigDecimal first = new BigDecimal("10.0");
BigDecimal second = new BigDecimal("10.00");

TreeMap<BigDecimal, String> map = new TreeMap<>();
map.put(first, "A");
String old = map.put(second, "B");
~~~

**Đáp án:** `old` là `"A"`, `map.size() == 1`, `map.get(first)` là `"B"` và `map.get(second)` cũng là `"B"`. Nếu dùng `HashMap` thay thế và giữ nguyên các khóa, kích thước là 2 vì chúng khác `equals()`.

### Bài 3: comparator nhất quán?

Xét ba cách tạo comparator:

~~~java
Comparator<BigDecimal> c1 = Comparator.naturalOrder();
Comparator<BigDecimal> c2 =
        Comparator.comparing(BigDecimal::stripTrailingZeros);
Comparator<BigDecimal> c3 =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
~~~

**Đáp án:** `c1` và `c2` cùng xem `2.0` và `2.00` là tương đương; chúng **không nhất quán với `BigDecimal.equals()`**. `c3` vừa sắp theo giá trị số vừa phân biệt `scale`, do đó nhất quán với `equals()` trên các đối tượng `BigDecimal`.

### Bài 4: chọn thiết kế

Một hệ thống nhận giá `12.0` và `12.00` từ hai tệp khác nhau. Yêu cầu (A) là đếm số **giá trị số duy nhất**, còn yêu cầu (B) là đếm số **biểu diễn số học phân biệt theo `scale`**.

**Đáp án định hướng:** (A) chuẩn hóa bằng `stripTrailingZeros()` rồi dùng `HashSet`, hoặc dùng `TreeSet` theo thứ tự tự nhiên nếu chỉ cần tập giá trị số. (B) dùng `HashSet` với `equals()` mặc định, hoặc `TreeSet` với comparator giá trị rồi `scale`. Nếu còn cần phân biệt **từng dòng nhập**, phải dùng ID của dòng thay vì chỉ dùng `BigDecimal`.

## 14. Ghi nhớ và tài liệu chính thức

- `compareTo()` của `BigDecimal` là **so sánh số học**; `equals()` kiểm tra **giá trị và `scale`**.
- “Thứ tự tự nhiên không nhất quán với `equals`” nghĩa là có các cặp mà `compareTo() == 0` nhưng `equals() == false`. Điều này có thể khiến các tập/bản đồ có sắp xếp và có băm không đồng thuận về phần tử/khóa trùng nhau.
- **Giá trị số**, **biểu diễn kèm `scale`** và **danh tính của bản ghi nghiệp vụ** là ba khái niệm khác nhau. Hãy chọn một quy tắc cụ thể và áp dụng nhất quán lúc lưu cũng như lúc truy xuất.

Tài liệu tham khảo (Java SE 17/21):
- [`BigDecimal` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): mục `compareTo`, `equals`, `hashCode`, `divide` và `stripTrailingZeros`.
- [`Comparable` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html): định nghĩa natural ordering nhất quán với `equals` và mô tả trường hợp `BigDecimal`.
- [`Comparator` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html): tính nhất quán giữa comparator và `equals` đối với sorted collections.
