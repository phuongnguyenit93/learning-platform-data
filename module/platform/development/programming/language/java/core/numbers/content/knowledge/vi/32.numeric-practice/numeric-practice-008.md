# Thực hành so sánh `HashSet` và `TreeSet` khi chứa `BigDecimal`

## 1. Vấn đề cần giải quyết

`HashSet` và `TreeSet` đều hiện thực giao diện `Set` trong Java, nhưng với `BigDecimal`, chúng **không nhất thiết giữ cùng số phần tử** khi nhận cùng danh sách đầu vào:

- `HashSet<BigDecimal>` nhận định trùng lặp theo `equals()` và `hashCode()`.
- `TreeSet<BigDecimal>` dùng thứ tự tự nhiên `compareTo()` hoặc `Comparator` đã truyền vào. Hai phần tử được xem là cùng một phần tử nếu phép so sánh trả **0**.

Điểm đặc biệt của `BigDecimal`: `equals()` kiểm tra **cả giá trị lẫn scale**, nhưng `compareTo()` chỉ so sánh **giá trị toán học**.

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

Hai số có giá trị bằng 1 nhưng scale lần lượt 1 và 2. Do đó `HashSet` xem chúng là hai phần tử khác, còn `TreeSet` mặc định xem chúng là một lớp tương đương. Sự khác biệt này tác động đến `add`, `size`, `contains`, `remove` và dữ liệu xuất ra.

**Mục tiêu:** tự chạy một chương trình Java 17+, dự đoán đầu ra trước khi chạy, giải thích từng dòng, sau đó chọn quy tắc trùng lặp phù hợp hợp đồng dữ liệu thay vì chọn collection theo thói quen.

## 2. Ôn lại `BigDecimal` và scale

Công thức biểu diễn của `BigDecimal`:

~~~text
value = unscaledValue × 10^(-scale)
~~~

| Dữ liệu đầu vào | Unscaled value | Scale | Giá trị toán học |
| --- | ---: | ---: | ---: |
| `"1"` | 1 | 0 | 1 |
| `"1.0"` | 10 | 1 | 1 |
| `"1.00"` | 100 | 2 | 1 |
| `"1.000"` | 1000 | 3 | 1 |
| `"1E+0"` | 1 | 0 | 1 |
| `"1000.00"` | 100000 | 2 | 1000 |

Tất cả các biểu diễn có giá trị 1 đều bằng nhau theo `compareTo`, nhưng chỉ các đối tượng có cùng giá trị và scale mới bằng nhau theo `equals`. `BigDecimal.hashCode()` cũng có tính đến scale để nhất quán với `equals`.

Vì vậy, khi cần bảo toàn số chữ số sau dấu thập phân như một phần của hợp đồng, **không được mặc định rằng “cùng giá trị” nghĩa là “cùng dữ liệu”**. Ngược lại, nếu chỉ cần tập các giá trị số học phân biệt, không nên vô tình giữ nhiều biểu diễn chỉ vì chúng khác scale.

Hãy dựng dữ liệu thực hành bằng `new BigDecimal("1.00")` thay vì qua `double`. Constructor nhận chuỗi giữ đúng giá trị thập phân và scale dự định; constructor nhận `double` có thể đưa vào sai số nhị phân cho nhiều số thập phân như 0.1.

## 3. `HashSet<BigDecimal>`: quy tắc bằng nhau có xét scale

Thí nghiệm:

~~~java
HashSet<BigDecimal> hash = new HashSet<>();
System.out.println(hash.add(new BigDecimal("1.0")));   // true
System.out.println(hash.add(new BigDecimal("1.00")));  // true
System.out.println(hash.add(new BigDecimal("1.000"))); // true
System.out.println(hash.size());                       // 3
~~~

Đây là đoạn mã minh họa đặt trong phương thức, cần import `java.math.BigDecimal` và `java.util.HashSet`.

Cả ba lời gọi `add` trả `true`, vì ba đối tượng không bằng nhau theo `BigDecimal.equals`. Số phần tử trong tập là 3 mặc dù có duy nhất một giá trị toán học là 1.

Hệ quả với truy vấn:

~~~java
hash.contains(new BigDecimal("1.00"));   // true
hash.contains(new BigDecimal("1.0000")); // false
~~~

`1.0000` có scale 4, chưa được lưu trong set. Kết quả `false` không có nghĩa trong set không có số bằng 1 về toán học; nó chỉ có nghĩa không có đối tượng tương đương theo `equals`.

**Không dựa vào thứ tự duyệt hoặc `toString()` của `HashSet`.** `HashSet` không cam kết duy trì thứ tự chèn hay sắp xếp. Khi kiểm thử kết quả hãy dùng `size`, `contains`, các phép so sánh hoặc kiểm tra từng phần tử mà không dựa vào thứ tự ngẫu nhiên.

## 4. `TreeSet<BigDecimal>`: quy tắc bằng nhau theo comparator

`TreeSet` là `NavigableSet` duy trì thứ tự. Khi không truyền `Comparator`, kiểu `BigDecimal` dùng `compareTo` làm thứ tự tự nhiên:

~~~java
TreeSet<BigDecimal> tree = new TreeSet<>();
System.out.println(tree.add(new BigDecimal("1.0")));   // true
System.out.println(tree.add(new BigDecimal("1.00")));  // false
System.out.println(tree.add(new BigDecimal("1.000"))); // false
System.out.println(tree.size());                       // 1
System.out.println(tree);                              // [1.0]
~~~

Giữa ba số, phép `compareTo` trả 0. Chỉ phần tử được thêm đầu tiên (`1.0`) trở thành **đại diện đang lưu**. Các lần thêm số có cùng giá trị nhưng khác scale không thay thế đại diện cũ. `TreeSet` không tự gọi `setScale` hay `stripTrailingZeros`.

### 4.1. `contains` và `remove` có thể gây bất ngờ

~~~java
TreeSet<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("1.0"));

System.out.println(tree.contains(new BigDecimal("1.0000"))); // true
System.out.println(tree.remove(new BigDecimal("1.0000")));   // true
System.out.println(tree.isEmpty());                          // true
~~~

Lời gọi `contains` là `true` vì có phần tử so sánh bằng 0, **không phải vì set đã lưu đối tượng scale 4**. Tương tự, `remove` xóa đại diện `1.0` bằng cách tìm một khóa tương đương theo comparator.

Nếu `HashSet` chỉ chứa `1.0`, `remove(new BigDecimal("1.0000"))` lại trả `false`. Vì vậy không được coi hai kiểu `Set` là thay thế hoàn toàn về ngữ nghĩa trong bài toán này.

### 4.2. Đại diện giữ lại phụ thuộc thứ tự chèn

~~~java
TreeSet<BigDecimal> first = new TreeSet<>();
first.add(new BigDecimal("6.0"));
first.add(new BigDecimal("6.00"));

TreeSet<BigDecimal> second = new TreeSet<>();
second.add(new BigDecimal("6.00"));
second.add(new BigDecimal("6.0"));

System.out.println(first);  // [6.0]
System.out.println(second); // [6.00]
~~~

Hai tập đều chỉ có **một giá trị toán học phân biệt**, nhưng scale của đại diện được lưu khác nhau. Nếu API yêu cầu biểu diễn đúng scale, đừng dùng `TreeSet` mặc định làm bước “chuẩn hóa” bởi thứ tự chèn có thể quyết định chuỗi kết quả.

## 5. Bài thực hành chính: dự đoán kết quả cho cùng dữ liệu

Cho đầu vào:

~~~java
List<BigDecimal> data = List.of(
        new BigDecimal("2.0"),
        new BigDecimal("1.0"),
        new BigDecimal("1.00"),
        new BigDecimal("2.00"),
        new BigDecimal("1.000"));
~~~

Xét về **giá trị số học**, dữ liệu chỉ có hai giá trị 1 và 2. Xét về **cặp giá trị và scale**, có năm phần tử phân biệt.

| Phép kiểm tra | `HashSet` | `TreeSet` mặc định |
| --- | --- | --- |
| `size()` sau khi thêm năm phần tử | 5 | 2 |
| Có gom `1.0` và `1.00` thành một không? | Không | Có |
| `contains(1.0000)` | `false` | `true` |
| Đồng nhất phần tử | `equals/hashCode` | `compareTo == 0` |
| Duy trì thứ tự số tăng dần | Không bảo đảm | Có |
| Tự chuẩn hóa scale | Không | Không |

Với đúng thứ tự dữ liệu trên, `TreeSet.toString()` cho `[1.0, 2.0]`. Điều này do hai đại diện `1.0` và `2.0` được gặp trước các biểu diễn khác của chúng; không phải vì `TreeSet` cố tình chọn biểu diễn ngắn nhất.

## 6. Chương trình Java 17+ chạy độc lập

Tạo tệp **BigDecimalSetsLab.java**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class BigDecimalSetsLab {
    private static final Comparator<BigDecimal> VALUE_THEN_SCALE =
            (a, b) -> {
                int byValue = a.compareTo(b);
                return byValue != 0
                        ? byValue
                        : Integer.compare(a.scale(), b.scale());
            };

    public static void main(String[] args) {
        List<BigDecimal> data = List.of(
                new BigDecimal("2.0"),
                new BigDecimal("1.0"),
                new BigDecimal("1.00"),
                new BigDecimal("2.00"),
                new BigDecimal("1.000"));

        HashSet<BigDecimal> hash = new HashSet<>(data);
        TreeSet<BigDecimal> tree = new TreeSet<>(data);

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal oneHundredths = new BigDecimal("1.00");
        BigDecimal lookup = new BigDecimal("1.0000");

        System.out.println("equals 1.0 / 1.00: "
                + one.equals(oneHundredths));
        System.out.println("compareTo 1.0 / 1.00: "
                + one.compareTo(oneHundredths));

        System.out.println("hash size: " + hash.size());
        System.out.println("tree size: " + tree.size());
        System.out.println("tree values: " + tree);

        System.out.println("hash contains 1.0000: "
                + hash.contains(lookup));
        System.out.println("tree contains 1.0000: "
                + tree.contains(lookup));

        TreeSet<BigDecimal> scaleAware =
                new TreeSet<>(VALUE_THEN_SCALE);
        scaleAware.addAll(data);
        System.out.println("scale-aware tree size: "
                + scaleAware.size());
        System.out.println("scale-aware tree values: "
                + scaleAware);

        HashSet<BigDecimal> normalized = data.stream()
                .map(BigDecimal::stripTrailingZeros)
                .collect(Collectors.toCollection(HashSet::new));
        System.out.println("normalized hash size: "
                + normalized.size());

        System.out.println("1000.00 stripped: "
                + new BigDecimal("1000.00")
                        .stripTrailingZeros());

        System.out.println("tree remove 1.0000: "
                + tree.remove(lookup));
        System.out.println("tree after remove: " + tree);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac BigDecimalSetsLab.java
java BigDecimalSetsLab
~~~

Kết quả:

~~~text
equals 1.0 / 1.00: false
compareTo 1.0 / 1.00: 0
hash size: 5
tree size: 2
tree values: [1.0, 2.0]
hash contains 1.0000: false
tree contains 1.0000: true
scale-aware tree size: 5
scale-aware tree values: [1.0, 1.00, 1.000, 2.0, 2.00]
normalized hash size: 2
1000.00 stripped: 1E+3
tree remove 1.0000: true
tree after remove: [2.0]
~~~

Các dòng trên không in trực tiếp `HashSet`, bởi thứ tự phần tử của hash set không được bảo đảm. `TreeSet` mặc định sắp theo giá trị toán học, trong khi `scaleAware` sử dụng comparator riêng để phân biệt các biểu diễn có cùng giá trị nhưng khác scale.

## 7. Làm rõ `add`, `contains`, `remove` và tập hợp tương đương

Trong `HashSet`, việc thêm `BigDecimal("7.00")` sau `BigDecimal("7.0")` làm tăng số phần tử vì `equals` là `false`. Trong `TreeSet` mặc định, việc thêm tương tự không làm tăng số phần tử vì `compareTo == 0`.

~~~java
HashSet<BigDecimal> hash = new HashSet<>();
hash.add(new BigDecimal("7.0"));
System.out.println(hash.add(new BigDecimal("7.00"))); // true

TreeSet<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("7.0"));
System.out.println(tree.add(new BigDecimal("7.00"))); // false
~~~

`Set.add` trả `true` khi tập hợp thay đổi, `false` nếu phần tử được nhận định đã tồn tại. Với `TreeSet` trên, `false` **không thay đại diện `7.0` bằng `7.00`**.

`TreeSet` giữ thứ tự tăng dần theo comparator và hỗ trợ các phép `first()`, `last()`, `ceiling()`, `floor()`, `subSet()`. `HashSet` tập trung vào tra cứu theo hash, không bảo đảm thứ tự. Nhưng vấn đề chính khi dùng `BigDecimal` không đơn thuần là hiệu năng/sắp xếp mà là **định nghĩa “trùng nhau”**.

## 8. Nếu cần sắp xếp mà vẫn phân biệt scale

`TreeSet<BigDecimal>` tự nhiên coi `1.0` và `1.00` là một. Khi hợp đồng yêu cầu **hai đối tượng khác nhau theo `BigDecimal.equals` vẫn phải là hai phần tử**, hãy dùng comparator phân biệt scale khi giá trị bằng nhau:

~~~java
Comparator<BigDecimal> valueThenScale = (a, b) -> {
    int byValue = a.compareTo(b);
    return byValue != 0 ? byValue
            : Integer.compare(a.scale(), b.scale());
};

TreeSet<BigDecimal> scaleAware = new TreeSet<>(valueThenScale);
scaleAware.add(new BigDecimal("1.0"));
scaleAware.add(new BigDecimal("1.00"));
System.out.println(scaleAware.size()); // 2
~~~

Comparator sắp theo **giá trị toán học** trước; nếu giá trị bằng nhau, scale quyết định thứ tự. Với `BigDecimal` hợp lệ, comparator trả 0 chính xác khi `equals` trả `true`, nên quan hệ bằng nhau của set nhất quán với `equals`.

Đừng dùng `a.toString().compareTo(b.toString())` làm comparator số chỉ vì dễ viết: so sánh từ điển của chuỗi có thể cho thứ tự khác thứ tự toán học (nhất là số âm, độ dài phần nguyên và ký pháp mũ).

Nếu không cần sắp xếp nhưng cần giữ **thứ tự chèn**, `LinkedHashSet` có thể thích hợp. Nó vẫn dùng `equals`/`hashCode` để nhận định trùng lặp, tương tự `HashSet`. Thứ tự và quan hệ bằng nhau là hai quyết định riêng biệt.

## 9. Nếu muốn khử trùng lặp theo giá trị số học

Nếu chỉ cần các giá trị toán học phân biệt, `TreeSet` mặc định có thể phù hợp. Tuy nhiên, nếu dùng `HashSet` để tra cứu theo hash mà muốn gom các `BigDecimal` khác scale, có thể **chuẩn hóa các khóa một cách tường minh**:

~~~java
HashSet<BigDecimal> canonical = new HashSet<>();

canonical.add(new BigDecimal("1.0").stripTrailingZeros());
canonical.add(new BigDecimal("1.00").stripTrailingZeros());

System.out.println(canonical.size()); // 1
~~~

`stripTrailingZeros()` giữ nguyên **giá trị toán học** nhưng có thể thay đổi scale. Ví dụ:

~~~java
BigDecimal raw = new BigDecimal("1000.00");
BigDecimal compact = raw.stripTrailingZeros();

System.out.println(compact);         // 1E+3
System.out.println(compact.scale()); // -3
~~~

Điểm cần nhớ: chuẩn hóa theo cách này có thể tạo scale âm; **không thích hợp khi đầu ra bắt buộc giữ scale cố định**.

Nếu hợp đồng yêu cầu mọi khóa có đúng scale 2 và không được làm tròn, có thể chuẩn hóa bằng:

~~~java
BigDecimal key = raw.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
~~~

Đây là **đoạn minh họa với biến `raw` kiểu `BigDecimal`**. `1.0`, `1.00` đều trở thành `1.00` và sẽ là cùng khóa hash. `1.234` không thể đổi chính xác thành scale 2, nên ném `ArithmeticException`. Nếu nghiệp vụ cho phép làm tròn, hãy chọn rounding mode một cách có chủ đích: làm tròn có thể khiến **hai giá trị ban đầu khác nhau** nhập thành một khóa.

## 10. `Set` contract và tác động đến API

`BigDecimal` là trường hợp nổi tiếng mà thứ tự tự nhiên **không nhất quán với `equals`**. Điều này được tài liệu Java nêu rõ.

Một API chỉ khai báo nhận `Set<BigDecimal>` nhưng tự giả định `contains` luôn có ý nghĩa theo `BigDecimal.equals` có thể hoạt động khác khi người gọi truyền `HashSet` hoặc `TreeSet`. Với `TreeSet`, tập dùng comparator để xác định phần tử tương đương; về mặt `Set` contract tổng quát dựa trên `equals`, kết quả có thể gây bất ngờ.

Ví dụ nếu một set chứa `1.0`:

~~~java
boolean present = set.contains(new BigDecimal("1.00"));
~~~

Nếu `set` là `HashSet`, kết quả `false`. Nếu là `TreeSet` tự nhiên, kết quả `true`. Vì vậy cần mô tả rõ quan hệ tương đương trong API, nhất là khi dữ liệu được dùng cho khử trùng lặp, phát hiện bản ghi lặp, lookup hoặc kiểm thử.

Tương tự, `HashMap<BigDecimal, V>` dùng `equals`/`hashCode` cho khóa, còn `TreeMap<BigDecimal, V>` dùng comparator. Khi đổi cấu trúc map, số khóa hoặc hành vi `get`/`put` có thể thay đổi. Không đổi giữa map hash và map tree nếu chưa xem xét ngữ nghĩa của `BigDecimal`.

## 11. Bài tập tự giải và đáp án

### Bài 1 — Dự đoán số phần tử

~~~java
List<BigDecimal> input = List.of(
        new BigDecimal("3"),
        new BigDecimal("3.0"),
        new BigDecimal("3.00"),
        new BigDecimal("4.0"),
        new BigDecimal("4.00"));

System.out.println(new HashSet<>(input).size());
System.out.println(new TreeSet<>(input).size());
~~~

**Đáp án:** `5` rồi `2`. Tập hash phân biệt cả giá trị/scale; tập tree tự nhiên chỉ phân biệt hai giá trị 3 và 4.

### Bài 2 — Tìm theo giá trị hay theo scale

~~~java
Set<BigDecimal> hash = new HashSet<>();
Set<BigDecimal> tree = new TreeSet<>();
hash.add(new BigDecimal("0.50"));
tree.add(new BigDecimal("0.50"));

System.out.println(hash.contains(new BigDecimal("0.5")));
System.out.println(tree.contains(new BigDecimal("0.5")));
~~~

**Đáp án:** `false` rồi `true`, vì scale 2 khác scale 1 nhưng `compareTo == 0`.

### Bài 3 — Thứ tự chèn ảnh hưởng đại diện thế nào?

~~~java
TreeSet<BigDecimal> one = new TreeSet<>();
one.add(new BigDecimal("6.0"));
one.add(new BigDecimal("6.00"));

TreeSet<BigDecimal> two = new TreeSet<>();
two.add(new BigDecimal("6.00"));
two.add(new BigDecimal("6.0"));

System.out.println(one); // [6.0]
System.out.println(two); // [6.00]
~~~

**Giải thích:** mỗi tập giữ đại diện được chèn trước. Hai tập có cùng một giá trị số học nhưng khác cách biểu diễn của phần tử.

### Bài 4 — Giữ cả ba scale mà vẫn có thứ tự

Yêu cầu: với `6.0`, `6.00`, `6.000`, một sorted set cần giữ đủ **3** phần tử. Hãy dùng comparator `valueThenScale` trong phần 8. Chỉ dùng `compareTo` thì còn một phần tử.

### Bài 5 — Chọn cấu trúc cho dữ liệu đơn giá

Một hệ thống coi `15.0` và `15.00` là **cùng đơn giá**, nhưng phải xuất kết quả ở **scale 2**. Không nên chỉ dùng `TreeSet` mặc định rồi in phần tử được giữ: đại diện có thể là `15.0`. Hãy chuẩn hóa đầu vào bằng `setScale(2, UNNECESSARY)` khi phù hợp, sau đó dùng set theo nhu cầu thứ tự/tra cứu. Nếu đầu vào có hơn hai chữ số khác 0 ở phần thập phân, xử lý lỗi hoặc chính sách rounding đã định nghĩa.

## 12. Kiểm thử trong Java

Với JUnit 5, các assertion minh họa sau cần đặt trong phương thức test và import `org.junit.jupiter.api.Assertions.*`:

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

assertNotEquals(a, b);
assertEquals(0, a.compareTo(b));
assertEquals(2, new HashSet<>(List.of(a, b)).size());
assertEquals(1, new TreeSet<>(List.of(a, b)).size());
~~~

Chú ý `assertEquals(a, b)` sử dụng `equals` nên sẽ thất bại. Nếu contract chỉ xét giá trị số học, hãy kiểm tra `compareTo == 0` thay vì một assertion `equals` không tương ứng yêu cầu.

Các trường hợp nên kiểm thử thêm:

| Đầu vào | Điều muốn xác minh |
| --- | --- |
| `1.0`, `1.00`, `1.000` | Trùng theo giá trị hay giá trị+scale |
| `0`, `0.00` | Zero vẫn có scale trong `BigDecimal` |
| `-2.0`, `-2.00` | Quy tắc không phụ thuộc dấu |
| `1000.00`, `1E+3` | `stripTrailingZeros` có thể tạo scale âm |
| `1.01`, `1.010`, `1.02` | Không gom các giá trị thật sự khác nhau |
| `1.234` chuẩn hóa scale 2 | `UNNECESSARY` báo lỗi nếu làm tròn mới được |
| Chèn phần tử theo thứ tự đảo ngược | `TreeSet` có thể giữ đại diện khác |
| `HashSet` được duyệt nhiều lần | Không assert thứ tự không được bảo đảm |

Nếu `TreeSet` chứa kết quả đúng về số lượng nhưng cần xuất biểu diễn scale 2, hãy thêm assertion `scale() == 2` cho từng phần tử. **Đúng số lượng không chứng minh đúng biểu diễn dữ liệu.**

## 13. Các lỗi thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| Hai `BigDecimal` bằng nhau về số thì hash set chỉ giữ một | `HashSet` dựa vào `equals`, còn xét scale |
| `TreeSet` dùng `equals` để phát hiện trùng | `TreeSet` dùng comparator và coi `compare(...) == 0` là tương đương |
| `TreeSet` chỉ thêm khả năng sắp xếp cho `HashSet` | Với `BigDecimal`, nó còn đổi cả quy tắc đồng nhất |
| `TreeSet.contains(1.000)` chứng minh đúng đối tượng scale 3 đã được lưu | Nó chỉ chứng minh có đại diện cùng giá trị theo comparator |
| Thêm `1.00` sau `1.0` vào tree set sẽ thay đại diện | `add` trả `false` và giữ đại diện cũ |
| `HashSet` in phần tử theo thứ tự chèn | Không có cam kết về thứ tự duyệt |
| `stripTrailingZeros` luôn đưa scale về 0 | Có thể tạo scale âm, như `1E+3` |
| Comparator chuỗi `toString` tương đương so sánh số | Thứ tự chữ cái và số học có thể khác |
| Chuyển sang `double` trước khi khử trùng lặp sẽ chính xác hơn | Chuyển nhị phân có thể làm tròn và nhập nhằng các giá trị khác nhau |
| Chọn `HashSet` hay `TreeSet` là chuyện hiệu năng thuần túy | Nó có thể thay đổi cả kết quả và hợp đồng dữ liệu |

**Kết luận:** Hãy xác định rõ “trùng” nghĩa là **cùng giá trị số học** hay **cùng giá trị và scale**. `HashSet<BigDecimal>` mặc định phù hợp với quan hệ `equals`; `TreeSet<BigDecimal>` mặc định phù hợp với quan hệ `compareTo == 0`. Nếu cần một quan hệ khác, chuẩn hóa dữ liệu hoặc cung cấp comparator tường minh, rồi kiểm thử cả `size`, `contains`, `remove`, thứ tự và scale của đầu ra.