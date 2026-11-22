# Phân biệt equals với compareTo của BigDecimal

## 1. “Bằng nhau” có thể đang hỏi hai điều khác nhau

Xét hai số được tạo từ chuỗi:

```java
BigDecimal first = new BigDecimal("12.0");
BigDecimal second = new BigDecimal("12.00");
```

Về giá trị số, chúng cùng biểu diễn số 12. Nhưng số chữ số thập phân được giữ trong biểu diễn khác nhau:

| Đối tượng | unscaledValue() | scale() | Giá trị số |
| --- | ---: | ---: | --- |
| `first` | 120 | 1 | 120 × 10⁻¹ = 12 |
| `second` | 1200 | 2 | 1200 × 10⁻² = 12 |

`BigDecimal` biểu diễn một giá trị bằng phần số nguyên `unscaledValue` và `scale`. Do đó, có thể phân biệt hai câu hỏi:

- **Giá trị số có bằng nhau không?** Dùng `compareTo(...) == 0`.
- **Giá trị số và scale có cùng nhau không?** Dùng `equals(...)`.

Kết quả:

```java
first.equals(second);         // false
first.compareTo(second) == 0; // true
```

Đây là hành vi được quy định của `BigDecimal`, không phải một lỗi số dấu phẩy động và cũng không phải do một phương thức tự làm tròn.

Những đoạn mã ngắn trong bài đặt trong một phương thức và cần import lớp được dùng. Chương trình hoàn chỉnh ở phần sau tương thích Java 17+.

## 2. equals xét giá trị và scale

`equals(Object)` chỉ trả true khi đối tượng kia cũng là `BigDecimal`, có cùng giá trị số và cùng scale.

| Hai giá trị tạo từ chuỗi | equals | Lý do |
| --- | --- | --- |
| "12.0" và "12.0" | true | Giá trị và scale đều giống |
| "12.0" và "12.00" | false | Scale 1 khác scale 2 |
| "0012.0" và "12.0" | true | Số 0 đầu chuỗi không tạo ra khác biệt biểu diễn này |
| "1000" và "1E+3" | false | Scale 0 khác scale -3 |
| "0" và "0.00" | false | Scale 0 khác scale 2 |

`equals` không so sánh nguyên văn chuỗi đầu vào. Sau khi parse, `BigDecimal` không ghi nhớ việc người dùng đã thêm số 0 ở đầu, ký hiệu dấu cộng hay viết chữ E theo cách nào. Nó xét biểu diễn số đã lưu.

Vì vậy cũng không nên mô tả `equals` đơn thuần là “hai chuỗi nhìn giống nhau”. Chuỗi chỉ là một cách để tạo hoặc hiển thị đối tượng.

### Vì sao scale có thể đáng được giữ lại?

Scale là một phần quan sát được của `BigDecimal` và có thể ảnh hưởng đến phép toán khác. Ví dụ với overload `divide(divisor, roundingMode)`, kết quả dùng scale của số bị chia:

```java
BigDecimal a = new BigDecimal("12.0");
BigDecimal b = new BigDecimal("12.00");
BigDecimal seven = new BigDecimal("7");

System.out.println(a.divide(seven, RoundingMode.HALF_UP)); // 1.7
System.out.println(b.divide(seven, RoundingMode.HALF_UP)); // 1.71
```

Hai đối tượng bằng nhau về số chưa chắc thay thế được cho nhau trong mọi phép toán phụ thuộc scale.

Điều đó không có nghĩa scale luôn mang ý nghĩa nghiệp vụ. Ứng dụng phải quyết định liệu khác biệt ấy cần được giữ hay chỉ là do cách nhập dữ liệu.

Hợp đồng của `equals`, `compareTo` và `hashCode` được mô tả trong [BigDecimal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

## 3. compareTo so sánh thứ tự theo giá trị số

`compareTo(BigDecimal)` bỏ qua khác biệt scale khi xác định thứ tự:

```java
BigDecimal value = new BigDecimal("12.00");
BigDecimal limit = new BigDecimal("12.0");

boolean sameValue = value.compareTo(limit) == 0;
boolean smaller = value.compareTo(limit) < 0;
boolean larger = value.compareTo(limit) > 0;
boolean atLeast = value.compareTo(limit) >= 0;
```

Trong ví dụ này, `sameValue` và `atLeast` là true; hai biến còn lại false.

Nên diễn đạt phép so sánh bằng dấu so với 0. Mẫu này cũng dùng được với các lớp `Comparable` khác mà không cần giả định giá trị âm/dương cụ thể.

Các ứng dụng thường cần so sánh số thay vì so sánh scale:

- Kiểm tra lượng còn lại có đủ cho một yêu cầu.
- Kiểm tra một số nằm trong khoảng.
- Kiểm tra kết quả tính có bằng giá trị mong đợi.
- So sánh một giá trị với 0.

### Kiểm tra số 0

```java
BigDecimal value = new BigDecimal("0.00");

boolean wrongForNumericZero = value.equals(BigDecimal.ZERO); // false
boolean numericZero = value.compareTo(BigDecimal.ZERO) == 0; // true
boolean zeroBySign = value.signum() == 0;                    // true
```

`wrongForNumericZero` không nói `equals` sai; nó cho thấy phương thức đó không trả lời đúng câu hỏi “giá trị số có phải 0 không?” khi scale không cố định.

### compareTo không phải so sánh gần đúng

`new BigDecimal("12.0001").compareTo(new BigDecimal("12"))` lớn hơn 0. Phương thức không tự bỏ qua một sai số nhỏ.

Nếu yêu cầu cho phép sai lệch trong một khoảng, hãy định nghĩa dung sai riêng, chẳng hạn kiểm tra `a.subtract(b).abs().compareTo(tolerance) <= 0`, với `tolerance` không âm. Đó là một quy tắc khác, không phải đặc điểm của `compareTo`.

Đặc biệt, quan hệ “cách nhau không quá dung sai” có thể không có tính bắc cầu. Không dùng nó tùy tiện để định nghĩa `equals` cho khóa trong collection.

## 4. ==, Objects.equals và null

### == kiểm tra cùng tham chiếu

```java
BigDecimal a = new BigDecimal("12.0");
BigDecimal b = new BigDecimal("12.0");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

Hai lần gọi constructor tạo hai đối tượng khác nhau. `==` không phải phép so sánh giá trị của `BigDecimal`. Một số hằng hoặc phương thức có thể tái sử dụng đối tượng; việc tình cờ nhận cùng tham chiếu không làm `==` trở thành cách kiểm tra giá trị đúng.

### Objects.equals không đổi quy tắc bằng nhau

`Objects.equals(a, b)` xử lý null thuận tiện nhưng vẫn gọi quy tắc `equals` của đối tượng:

```java
Objects.equals(new BigDecimal("12.0"), new BigDecimal("12.00")); // false
Objects.equals(null, null);                                    // true
```

Nó không chuyển sang so sánh số.

### Cần chọn ý nghĩa của null rõ ràng

`a.equals(null)` trả false khi `a` khác null. `a.compareTo(null)` ném `NullPointerException`; gọi bất kỳ phương thức nào trên tham chiếu null cũng lỗi.

Nếu ứng dụng muốn coi hai null là bằng nhau và null khác mọi số, có thể viết hàm sau:

```java
static boolean numericallyEqual(BigDecimal a, BigDecimal b) {
    return a == b || (a != null && b != null && a.compareTo(b) == 0);
}
```

Đây là lựa chọn chính sách của hàm. Trong nhiều phép tính, null thể hiện thiếu dữ liệu và nên bị từ chối thay vì coi như 0.

`BigDecimal.equals` cũng không tự chuyển đổi các kiểu khác: một `BigDecimal` có giá trị 12 không `equals` với `Long` hoặc `Double` có vẻ cùng giá trị. Hãy thống nhất kiểu dữ liệu trước khi so sánh, tránh chuyển qua `double` làm mất tính chính xác thập phân.

## 5. Ảnh hưởng đến HashSet, TreeSet và Map

`BigDecimal` có thứ tự tự nhiên không nhất quán với `equals`: có cặp `compareTo == 0` nhưng `equals == false`. Điều này thể hiện rõ khi đổi loại collection.

### HashSet và HashMap dùng equals cùng hashCode

Nếu thêm `12.0` và `12.00` vào `HashSet`, tập có hai phần tử. Nếu dùng chúng làm hai khóa trong `HashMap`, map có hai mục riêng.

`BigDecimal.hashCode()` được xây dựng phù hợp với `equals`, có xét scale. Hai đối tượng `equals` nhau phải có hash code bằng nhau; hai đối tượng chỉ bằng nhau theo số nhưng khác scale không bắt buộc có hash code bằng nhau.

Không nên kiểm tra sự bằng nhau bằng cách so sánh hash code. Va chạm hash có thể xảy ra; chiều ngược “cùng hash code thì equals” không đúng.

Ví dụ và hợp đồng tập hợp dựa trên bảng băm có tại [HashSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashSet.html).

### TreeSet và TreeMap dùng thứ tự so sánh

Với thứ tự tự nhiên của `BigDecimal`, `TreeSet` coi `12.0` và `12.00` là cùng một vị trí vì `compareTo` trả 0. Thêm cả hai chỉ tạo một phần tử. Tương tự, `TreeMap` coi chúng là cùng một khóa và lần put thứ hai thay giá trị gắn với khóa đó.

Đổi từ `HashMap` sang `TreeMap` chỉ để có sắp xếp có thể đồng thời đổi quy tắc nhận diện khóa. Đây là thay đổi hành vi, không chỉ là thay đổi thứ tự hiển thị.

`TreeSet` vẫn có hành vi xác định theo comparator, nhưng khi thứ tự không nhất quán với `equals`, nó không tuân theo đầy đủ hợp đồng chung của `Set`. Không nên trộn lẫn các tập dùng quy tắc khác nhau rồi giả định những phép bằng nhau giữa tập luôn có ý nghĩa như nhau. Xem cảnh báo trong [TreeSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Nếu cần giữ hai giá trị khác scale trong một cây có sắp xếp, có thể dùng comparator so sánh số trước rồi scale khi giá trị số hòa. Ngược lại, nếu ứng dụng muốn mọi biến thể scale là cùng khóa, nên thống nhất chính sách ngay tại ranh giới dữ liệu.

## 6. Chuẩn hóa khi scale không thuộc danh tính

### Bỏ số 0 cuối với stripTrailingZeros

```java
BigDecimal a = new BigDecimal("12.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("12.00").stripTrailingZeros();

System.out.println(a.equals(b)); // true
```

Phương thức không làm tròn giá trị số; nó bỏ các số 0 cuối biểu diễn. Số 0 được đưa về `BigDecimal.ZERO`.

Cần lưu ý scale có thể âm:

```java
BigDecimal normalized = new BigDecimal("1000.00").stripTrailingZeros();

System.out.println(normalized);                 // 1E+3
System.out.println(normalized.scale());         // -3
System.out.println(normalized.toPlainString()); // 1000
```

Ký hiệu số mũ không cho thấy giá trị bị sai. Đừng dùng độ dài chuỗi hoặc cách chuỗi trông như thế nào để quyết định số có bằng nhau không.

Với dữ liệu có scale cực hạn, `stripTrailingZeros` cũng có thể ném ngoại lệ khi scale vượt miền biểu diễn. Chính sách nhập dữ liệu vẫn cần giới hạn phù hợp.

### Chuẩn hóa cả lúc ghi và lúc tra khóa

```java
Map<BigDecimal, String> lookup = new HashMap<>();
lookup.put(new BigDecimal("12.0").stripTrailingZeros(), "matched");

String found = lookup.get(new BigDecimal("12.00").stripTrailingZeros());
```

`found` là `"matched"`. Chuẩn hóa chỉ khi put nhưng dùng khóa chưa chuẩn hóa lúc get vẫn có thể không tìm được.

Đây chỉ phù hợp khi ứng dụng đã quyết định scale không thuộc danh tính khóa. Nếu phải giữ biểu diễn gốc để hiển thị hoặc kiểm tra đầu vào, lưu nó riêng; đừng phá thông tin đó chỉ vì muốn tìm kiếm theo số.

### Scale cố định là một chính sách khác

Nếu hợp đồng yêu cầu đúng hai chữ số sau dấu chấm, có thể chuẩn hóa bằng:

```java
BigDecimal canonical = input.setScale(2, RoundingMode.UNNECESSARY);
```

Lúc đó 12.0 trở thành 12.00; 12.345 bị từ chối vì cần bỏ thông tin. Nếu dùng `HALF_UP` thay `UNNECESSARY`, 12.341 và 12.344 đều có thể thành 12.34: đó là làm tròn và gộp các giá trị số vốn khác nhau, không chỉ xóa khác biệt biểu diễn.

Nếu tạo lớp bao riêng và định nghĩa `equals` dựa trên giá trị số, phải định nghĩa `hashCode` tương ứng với cùng quy tắc. Không được dùng `compareTo == 0` trong `equals` rồi giữ hash code của `BigDecimal` chưa chuẩn hóa. Việc đó có thể khiến hai đối tượng bằng nhau rơi vào các nhóm hash khác nhau.

## 7. Chương trình hoàn chỉnh quan sát hành vi

Lưu thành `DecimalEqualityDemo.java`. Chương trình chỉ in kích thước collection và kết quả tra cứu; không phụ thuộc thứ tự duyệt của `HashSet` hay `HashMap`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class DecimalEqualityDemo {
    private static BigDecimal decimal(String value) {
        return new BigDecimal(value);
    }

    private static boolean numericallyEqual(BigDecimal a, BigDecimal b) {
        return a == b || (a != null && b != null && a.compareTo(b) == 0);
    }

    private static BigDecimal numericKey(BigDecimal value) {
        return Objects.requireNonNull(value, "value").stripTrailingZeros();
    }

    public static void main(String[] args) {
        BigDecimal a = decimal("12.0");
        BigDecimal b = decimal("12.00");

        System.out.println("a.scale=" + a.scale());
        System.out.println("b.scale=" + b.scale());
        System.out.println("reference=" + (a == decimal("12.0")));
        System.out.println("equals=" + a.equals(b));
        System.out.println("compareZero=" + (a.compareTo(b) == 0));
        System.out.println("objectsEquals=" + Objects.equals(a, b));
        System.out.println("a.equals.sameScale=" + a.equals(decimal("12.0")));

        BigDecimal zero = decimal("0.00");
        System.out.println("zero.equals=" + zero.equals(BigDecimal.ZERO));
        System.out.println("zero.numeric=" + (zero.compareTo(BigDecimal.ZERO) == 0));
        System.out.println("zero.signum=" + zero.signum());

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        System.out.println("hash.contains.b=" + hashSet.contains(b));
        hashSet.add(b);
        System.out.println("hash.size=" + hashSet.size());

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        System.out.println("tree.contains.b=" + treeSet.contains(b));
        treeSet.add(b);
        System.out.println("tree.size=" + treeSet.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");
        System.out.println("hashMap.size=" + hashMap.size());
        System.out.println("hashMap.a=" + hashMap.get(a));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");
        System.out.println("treeMap.size=" + treeMap.size());
        System.out.println("treeMap.a=" + treeMap.get(a));

        Map<BigDecimal, String> normalizedMap = new HashMap<>();
        normalizedMap.put(numericKey(a), "matched");
        System.out.println("normalized.lookup=" + normalizedMap.get(numericKey(b)));
        System.out.println("normalized.equals=" + numericKey(a).equals(numericKey(b)));
        System.out.println("normalized.sameHash="
                + (numericKey(a).hashCode() == numericKey(b).hashCode()));

        BigDecimal thousand = decimal("1000.00").stripTrailingZeros();
        System.out.println("stripped=" + thousand);
        System.out.println("stripped.scale=" + thousand.scale());
        System.out.println("stripped.plain=" + thousand.toPlainString());

        BigDecimal seven = decimal("7");
        System.out.println("a.divide7=" + a.divide(seven, RoundingMode.HALF_UP));
        System.out.println("b.divide7=" + b.divide(seven, RoundingMode.HALF_UP));

        System.out.println("fixedScale.equals="
                + a.setScale(2, RoundingMode.UNNECESSARY).equals(b));
        System.out.println("numeric.nulls=" + numericallyEqual(null, null));
        System.out.println("numeric.oneNull=" + numericallyEqual(a, null));
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 DecimalEqualityDemo.java
java DecimalEqualityDemo
```

Stdout:

```text
a.scale=1
b.scale=2
reference=false
equals=false
compareZero=true
objectsEquals=false
a.equals.sameScale=true
zero.equals=false
zero.numeric=true
zero.signum=0
hash.contains.b=false
hash.size=2
tree.contains.b=true
tree.size=1
hashMap.size=2
hashMap.a=first
treeMap.size=1
treeMap.a=second
normalized.lookup=matched
normalized.equals=true
normalized.sameHash=true
stripped=1E+3
stripped.scale=-3
stripped.plain=1000
a.divide7=1.7
b.divide7=1.71
fixedScale.equals=true
numeric.nulls=true
numeric.oneNull=false
```

Các cặp đầu ra cần đọc cùng nhau:

- `equals=false` và `compareZero=true` thể hiện hai quy tắc bằng nhau.
- `hash.size=2` và `tree.size=1` cho thấy loại collection ảnh hưởng việc nhận diện phần tử.
- `hashMap.a=first` và `treeMap.a=second` cho thấy lần put thứ hai có thay giá trị cũ hay không.
- `normalized.sameHash=true` kiểm tra kết quả của hai khóa đã chuẩn hóa; không khẳng định mọi cặp cùng hash đều bằng nhau.
- Hai kết quả chia khác nhau giải thích vì sao thông tin scale có thể quan sát được qua API khác.

## 8. Chọn cách so sánh và viết kiểm thử

| Câu hỏi của ứng dụng | Cách kiểm tra |
| --- | --- |
| Hai giá trị số có bằng nhau? | `a.compareTo(b) == 0` |
| Giá trị và scale có giống nhau? | `a.equals(b)` |
| Giá trị có phải 0? | `a.signum() == 0` |
| Có lớn hơn một giới hạn? | `a.compareTo(limit) > 0` |
| Hai biến có trỏ cùng đối tượng? | `a == b` |
| Hai tham chiếu có bằng nhau theo equals và xử lý null? | `Objects.equals(a, b)` |
| Tra khóa theo số, bỏ qua scale? | Chuẩn hóa nhất quán hoặc dùng kiểu khóa có hợp đồng bằng nhau tương ứng |

Nếu viết kiểm thử số học, đừng vô tình yêu cầu scale chỉ vì assertion mặc định gọi `equals`. Ngược lại, nếu đầu ra bắt buộc có scale 2, chỉ kiểm tra `compareTo == 0` sẽ bỏ sót lỗi biểu diễn.

Có thể tách hai điều kiện cho dễ đọc:

```java
boolean correctValue = actual.compareTo(expected) == 0;
boolean correctScale = actual.scale() == 2;
```

Khi một giá trị không khớp, kiểm tra cả `unscaledValue()`, `scale()` và nguồn tạo số. Không làm tròn hai bên chỉ để phép kiểm tra trả true nếu đặc tả chưa cho phép làm tròn.

Không chuyển cả hai sang `double` để bỏ qua scale. Cách đó có thể làm hai giá trị thập phân khác nhau bị coi là bằng nhau sau khi mất độ chính xác.

## 9. Thực hành

1. Dự đoán `equals` và `compareTo` của "7.50"/"7.500", "0.000"/"0", "100"/"1E+2" và "07.5"/"7.5".
2. Thêm ba số 7.5, 7.50 và 7.500 vào `HashSet` và `TreeSet`; giải thích kích thước từng tập.
3. Viết hàm kiểm tra một giá trị nằm trong đoạn đóng [min, max] theo giá trị số. Định nghĩa rõ chính sách null và trường hợp min lớn hơn max.
4. Dùng map khóa chuẩn hóa để put "1000.0" và tra bằng "1E+3". In scale của khóa chuẩn hóa để kiểm tra giả định rằng scale luôn không âm.
5. Tạo comparator so sánh giá trị số trước, rồi scale khi hòa; dùng nó trong `TreeSet` và so sánh với thứ tự tự nhiên.
6. Cho hợp đồng đầu ra đúng hai chữ số sau dấu chấm, viết kiểm tra riêng cho giá trị và scale. Thử actual="7.5", expected="7.50" để chứng minh vì sao cần cả hai điều kiện.

Gợi ý: ở câu 1, ba cặp đầu có `equals=false` nhưng `compareTo=0`; cặp cuối có cả `equals=true` và `compareTo=0`. Ở câu 2, `HashSet` có 3 phần tử, `TreeSet` theo thứ tự tự nhiên có 1. Kết quả cần được giải thích bằng hợp đồng so sánh, không bằng hình thức chuỗi.
