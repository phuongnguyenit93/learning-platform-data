# So sánh `null` và lựa chọn hợp đồng API khi làm việc với `BigDecimal`

`BigDecimal` là kiểu tham chiếu, vì vậy một biến `BigDecimal` có thể là `null`. Khi viết API so sánh, cần trả lời hai câu hỏi độc lập: **hai số được so sánh theo giá trị số hay theo biểu diễn (bao gồm scale)?**, và **thiếu một hoặc hai giá trị phải được xử lý ra sao?**. Chính sách thiếu giá trị ảnh hưởng đến quy tắc nghiệp vụ, thao tác sắp xếp, tập hợp có thứ tự và kết quả trả về của API.

Bài này phân biệt ba hợp đồng: (1) từ chối `null`, (2) sắp xếp `null` theo một thứ tự rõ ràng, (3) trả kết quả “chưa xác định” khi thiếu toán hạng. Mục tiêu là chọn một hợp đồng phù hợp và thực thi nhất quán, không đánh đồng `null` với 0 hoặc với kết quả so sánh bằng nhau.

## 1. `null` không phải là số 0

```java
BigDecimal zero = BigDecimal.ZERO; // Có giá trị, chính xác bằng 0.
BigDecimal missing = null;         // Không có đối tượng BigDecimal.
```

Trong báo cáo tài chính, số dư `0` nghĩa là số dư đã được xác định và bằng 0; `null` có thể mang nghĩa chưa cung cấp, chưa tính hoặc không áp dụng. Tự thay `null` bằng `BigDecimal.ZERO` là một **quyết định nghiệp vụ**, không phải kỹ thuật sửa lỗi. Nó có thể làm sai so sánh ngưỡng hoặc biến “chưa biết” thành “bằng 0”.

Trước khi triển khai, hãy xác định nguồn dữ liệu có cho phép `null` và vì sao. Nếu một đối số luôn bắt buộc thì API nên từ chối thiếu dữ liệu. Nếu dữ liệu có thể thiếu, quyết định rõ phải xếp dòng thiếu ở đâu trong danh sách hay phải trả về trạng thái không thể kết luận.

## 2. Hành vi gốc của `BigDecimal` khi gặp `null`

`BigDecimal.compareTo(BigDecimal)` so sánh theo **giá trị số** và trả về một số âm, 0 hoặc dương. So sánh với `null` không được hỗ trợ:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.compareTo(b);    // 0: cùng giá trị số.
a.equals(b);       // false: scale 1 khác scale 2.
a.equals(null);    // false.
a.compareTo(null); // NullPointerException.
```

Nếu chính `a` là `null`, gọi `a.compareTo(b)` hoặc `a.equals(b)` đều ném `NullPointerException` vì không có đối tượng nhận lời gọi. Các phương thức `a.min(null)` và `a.max(null)` cũng không phải là lựa chọn null-safe.

`Objects.equals(left, right)` khác `compareTo`:

- `Objects.equals(null, null)` trả `true`.
- `Objects.equals(null, BigDecimal.ZERO)` trả `false`.
- `Objects.equals(new BigDecimal("1.0"), new BigDecimal("1.00"))` trả `false`, vì vẫn dùng `BigDecimal.equals`.
- `Objects.equals` chỉ giải quyết **kiểm tra bằng nhau theo `equals`**, không thay `BigDecimal.compareTo` hay tạo thứ tự số học.

`Objects.compare(left, right, comparator)` cũng không tự trở thành một comparator chấp nhận null. Nó trả 0 nếu hai tham chiếu là cùng một đối tượng (kể cả cả hai cùng null); nếu khác tham chiếu, nó gọi comparator được cung cấp. Với comparator không cho phép null, trường hợp chỉ một bên null vẫn ném ngoại lệ.

### `compareTo` và `equals`: hai quan hệ cần phân biệt

| Cặp `BigDecimal` | `compareTo == 0` | `equals` |
| --- | --- | --- |
| `"1.0"` / `"1.00"` | `true` | `false` |
| `"0"` / `"0.00"` | `true` | `false` |
| `"1.0"` / `"2.0"` | `false` | `false` |
| `"1.00"` / `"1.00"` | `true` | `true` |

`equals` và `hashCode` của `BigDecimal` xét cả giá trị và **scale**. Nếu cần kiểm tra “cùng số tiền” độc lập scale, `compareTo == 0` thường hợp lý. Nếu biểu diễn (`1.0` so với `1.00`) là một phần của dữ liệu, `equals` là lựa chọn phù hợp hơn.

## 3. Hợp đồng A: `null` là đầu vào không hợp lệ

Với ngưỡng bắt buộc, tổng tiền đã duyệt hoặc số tiền thanh toán đã ghi nhận, thường nên quy định **hai toán hạng đều khác null**. Thất bại tại điểm nhận tham số giúp lỗi được phát hiện rõ:

```java
import java.math.BigDecimal;
import java.util.Objects;

static int compareRequired(BigDecimal left, BigDecimal right) {
    Objects.requireNonNull(left, "left must not be null");
    Objects.requireNonNull(right, "right must not be null");
    return Integer.signum(left.compareTo(right));
}
```

Đây là một phương thức minh họa; cần đặt trong class phù hợp. `Objects.requireNonNull` ném `NullPointerException` với thông báo chỉ rõ đối số vi phạm. `Integer.signum(...)` chuẩn hóa kết quả thành **-1, 0 hoặc 1**; nếu không chuẩn hóa, `compareTo` chỉ cam kết âm/0/dương, không nhất thiết là -1/0/1.

Có thể mô tả hợp đồng bằng Javadoc:

```java
/**
 * So sánh hai giá trị thập phân bắt buộc có dữ liệu.
 * @param left không được null
 * @param right không được null
 * @return -1 nếu left nhỏ hơn right, 0 nếu bằng nhau về số học,
 *         1 nếu left lớn hơn right
 * @throws NullPointerException nếu một trong hai đối số là null
 */
```

Mảnh Javadoc này chỉ minh họa nội dung tài liệu của phương thức phía trên. API cần xác nhận rằng **0 nghĩa là hai giá trị đã được so sánh và bằng nhau**, không có nghĩa là dữ liệu thiếu.

Khi thực thi các điều kiện so sánh, nên viết `left.compareTo(right) > 0` thay vì `left.compareTo(right) == 1`, vì hợp đồng của `Comparable` cam kết **dấu** kết quả.

**Không** xử lý `NullPointerException` bằng cách tự động trả 0: như vậy API biến một lỗi thành kết luận “bằng nhau”, dẫn đến các nhánh logic nghiệp vụ sai.

## 4. Hợp đồng B: `null` được xếp ở đầu hoặc cuối

Nếu một danh sách vẫn phải sắp xếp khi có ô số tiền thiếu, Java cung cấp `Comparator.nullsFirst` và `Comparator.nullsLast`. Chúng tạo thứ tự xác định cho `null` và các giá trị không null:

```java
import java.math.BigDecimal;
import java.util.Comparator;

Comparator<BigDecimal> nullsFirst =
        Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<BigDecimal> nullsLast =
        Comparator.nullsLast(Comparator.naturalOrder());
```

Trong `nullsFirst`, `null` đứng trước mọi giá trị không null; trong `nullsLast`, `null` đứng sau mọi giá trị không null. Hai `null` được coi là bằng nhau để **sắp xếp** (`compare(null, null) == 0`). Khi cả hai đều khác null, comparator dùng thứ tự tự nhiên của `BigDecimal`, tức `compareTo`.

| Hai giá trị | `nullsFirst` | `nullsLast` |
| --- | --- | --- |
| `null`, `null` | `0` | `0` |
| `null`, `BigDecimal.ZERO` | Âm | Dương |
| `BigDecimal.ZERO`, `null` | Dương | Âm |
| `1.0`, `1.00` | `0` | `0` |
| `2`, `1` | Dương | Dương |

Quy tắc cho `null` ở đầu/cuối chỉ là **quy ước thứ tự hiển thị**. Nó không có nghĩa số tiền “chưa biết” thực sự nhỏ hơn hoặc lớn hơn số tiền bất kỳ. Không dùng ngầm quy ước hiển thị như một quy tắc so sánh nghiệp vụ.

Ví dụ, đoạn mã sau đặt giá trị thiếu ở cuối:

```java
List<BigDecimal> values = new ArrayList<>(Arrays.asList(
        new BigDecimal("2.0"),
        null,
        new BigDecimal("1.00"),
        new BigDecimal("1.0"),
        null,
        BigDecimal.ZERO));

values.sort(Comparator.nullsLast(Comparator.naturalOrder()));
System.out.println(values);
```

Đoạn này cần các import `BigDecimal`, `List`, `ArrayList`, `Arrays`, `Comparator` và phải nằm trong một phương thức. Kết quả:

```text
[0, 1.00, 1.0, 2.0, null, null]
```

`List.sort` giữ thứ tự tương đối của các phần tử có kết quả comparator bằng 0, vì vậy `1.00` vẫn đứng trước `1.0`. Hai giá trị cùng số học không bị ép về cùng scale.

Khi muốn **giảm dần nhưng null vẫn ở cuối**, phải chọn thứ tự ngược cho các số rồi mới bọc chính sách null:

```java
Comparator<BigDecimal> descendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
```

`Comparator.nullsLast(Comparator.naturalOrder()).reversed()` đảo **toàn bộ** thứ tự, bao gồm vị trí của null; khi đó null sẽ lên đầu.

### `null` của phần tử khác `null` của thuộc tính

Giả sử có một bản ghi gồm mã hóa đơn và số tiền:

```java
record Invoice(String code, BigDecimal amount) {}

Comparator<Invoice> byNullableAmount =
        Comparator.comparing(
                Invoice::amount,
                Comparator.nullsLast(Comparator.naturalOrder()));
```

Comparator trên cho phép `amount()` là null, nhưng **không** cho phép chính `Invoice` là null, bởi method reference vẫn phải gọi `amount()` từ một đối tượng tồn tại. Nếu danh sách có cả phần tử null:

```java
Comparator<Invoice> nullableInvoices =
        Comparator.nullsLast(
                Comparator.comparing(
                        Invoice::amount,
                        Comparator.nullsLast(Comparator.naturalOrder())));
```

Ví dụ record và comparator này là các mảnh mã cần đặt vào chương trình đầy đủ. Hai lớp null được xử lý độc lập: null ở **phần tử** và null ở **trường amount**. Không nên bọc nhầm tầng rồi tưởng rằng mọi trường hợp null đều đã an toàn.

## 5. Hợp đồng C: thiếu giá trị thì **chưa thể kết luận**

Với câu hỏi nghiệp vụ như “giá hiện tại cao hơn mức giới hạn hay không?”, nếu một trong hai số chưa được cung cấp, câu trả lời hợp lý có thể là “chưa biết”, không phải “nhỏ hơn”, “bằng nhau” hoặc “lớn hơn”.

Một API trả về `int` so sánh thuần túy không có chỗ biểu diễn trạng thái thứ tư đó. Với Java, có thể sử dụng `OptionalInt`:

```java
import java.math.BigDecimal;
import java.util.OptionalInt;

static OptionalInt compareIfPresent(BigDecimal left, BigDecimal right) {
    if (left == null || right == null) {
        return OptionalInt.empty();
    }
    return OptionalInt.of(Integer.signum(left.compareTo(right)));
}
```

`OptionalInt.empty()` nghĩa là **không có kết quả so sánh**, còn `OptionalInt.of(0)` nghĩa là **đã có đủ hai giá trị và bằng nhau**. Đặc biệt không được chuyển `empty()` thành số 0 một cách vô điều kiện.

Bên gọi có thể xử lý:

```java
OptionalInt result = compareIfPresent(amount, limit);
if (result.isEmpty()) {
    // Chưa xác định: yêu cầu bổ sung dữ liệu hoặc hiển thị trạng thái riêng.
} else if (result.getAsInt() > 0) {
    // amount đã biết và lớn hơn limit.
} else {
    // amount đã biết và nhỏ hơn hoặc bằng limit.
}
```

`amount` và `limit` ở ví dụ này là các biến `BigDecimal` của ứng dụng, đoạn mã không chạy độc lập. Với API nghiệp vụ phức tạp, có thể dùng enum `LESS`, `EQUAL`, `GREATER`, `UNKNOWN`, nhưng phải giải thích `UNKNOWN` phát sinh vì điều kiện nào.

`Comparator` phải trả `int` và cung cấp thứ tự nhất quán cho các giá trị thuộc miền của nó. Vì thế **không** nhét chính sách “unknown” thành một giá trị số đặc biệt trong comparator. Nếu thực sự không muốn xếp hạng các mục thiếu dữ liệu, hãy tách hoặc lọc chúng theo chính sách nghiệp vụ; nếu vẫn muốn sắp xếp tất cả, dùng một chính sách `nullsFirst/Last` rõ ràng.

Dùng `Optional<BigDecimal>` làm giá trị trả về có thể giúp phân biệt có/không có giá trị. Tuy nhiên, khi dùng ở tham số hay trường của DTO, nên theo quy ước của dự án và tài liệu hóa hợp đồng. Không kết hợp tùy tiện `null`, `Optional.empty()` và số 0 như ba cách diễn đạt cùng một trạng thái.

## 6. Bằng nhau với giá trị có thể null: chọn đúng nghĩa

Có ba cách định nghĩa “bằng nhau” tùy mục đích:

**Cách 1 — `equals`, chấp nhận cả hai null là cùng trạng thái:**

```java
boolean sameObjects = Objects.equals(left, right);
```

Kết quả `true` cho `(null, null)`, nhưng `false` cho `(1.0, 1.00)` vì scale khác nhau.

**Cách 2 — bằng nhau về số học, chỉ khi cả hai có mặt:**

```java
boolean sameNumericValueIfPresent =
        left != null && right != null && left.compareTo(right) == 0;
```

Hai giá trị null trả `false` vì chưa có hai số để so. Nếu muốn phân biệt “khác” và “chưa biết”, dùng kiểu trả kết quả ba trạng thái thay cho một boolean.

**Cách 3 — cùng trạng thái nullable hoặc cùng giá trị số:**

```java
boolean sameNullableAmount =
        left == right
                || (left != null && right != null && left.compareTo(right) == 0);
```

Ở đây hai bên đều null được xem là tương đương **theo hợp đồng dữ liệu nullable**. Điều đó không khẳng định hai số chưa biết bằng nhau về toán học.

| Cặp giá trị | `Objects.equals` | Bằng số học khi đủ dữ liệu | Tương đương nullable/số học |
| --- | --- | --- | --- |
| `null`, `null` | `true` | `false` | `true` |
| `null`, `0` | `false` | `false` | `false` |
| `1.0`, `1.00` | `false` | `true` | `true` |
| `1.0`, `2.0` | `false` | `false` | `false` |

Tên hàm nên nói rõ nghĩa, ví dụ `sameNumericValueIfPresent` hoặc `sameNullableAmount`, hơn là `isEqual` không có tài liệu đi kèm.

## 7. `TreeSet`, `TreeMap`, `HashSet` và vấn đề scale

Do `BigDecimal.compareTo` bỏ qua khác biệt scale khi hai số bằng nhau, thứ tự tự nhiên của nó **không nhất quán với `equals`**:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.compareTo(b) == 0; // true
a.equals(b);         // false
```

`HashSet` dùng `equals`/`hashCode`, nên hai đối tượng trên được coi là hai phần tử khác nhau. `TreeSet` và `TreeMap` dựa trên comparator (hoặc `compareTo` khi không cung cấp comparator), nên chúng xem hai giá trị có kết quả compare bằng 0 là **cùng khóa theo thứ tự**. Chỉ một phần tử/khóa đại diện được lưu.

`Comparator.nullsFirst/Last(Comparator.naturalOrder())` cho phép đặt `null` theo thứ tự được chọn nhưng **không thay đổi** tính không nhất quán giữa `BigDecimal.compareTo` và `BigDecimal.equals`.

Nếu cần phân biệt thêm scale trong tập hợp có thứ tự, có thể nối một tiêu chí phụ:

```java
Comparator<BigDecimal> numericThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);

Comparator<BigDecimal> nullableNumericThenScale =
        Comparator.nullsLast(numericThenScale);
```

Với những giá trị `BigDecimal` không null, comparator này so theo số học trước, rồi so scale. Hai `BigDecimal` cùng số học **và** cùng scale là bằng nhau theo `equals`, vì vậy thứ tự này phù hợp hơn khi scale mang ý nghĩa định danh. Tuy nhiên, nếu nghiệp vụ xem `1.0` và `1.00` là cùng một số tiền, phải chọn chính sách chuẩn hóa hoặc chấp nhận thứ tự tự nhiên xem chúng tương đương. Đừng đổi quy tắc chỉ để ép số lượng phần tử trong `HashSet` và `TreeSet` trùng nhau.

Một `TreeSet` được khởi tạo với comparator cho phép null có thể chứa một phần tử null và sắp xếp nó theo chính sách; `TreeSet` dùng thứ tự tự nhiên không hỗ trợ điều đó. Trong dữ liệu thực tế, cần tài liệu hóa cả **quy tắc null** lẫn **quy tắc xem hai giá trị là trùng**.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau thành **`BigDecimalNullComparisonDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalNullComparisonDemo {
    static int compareRequired(BigDecimal left, BigDecimal right) {
        Objects.requireNonNull(left, "left must not be null");
        Objects.requireNonNull(right, "right must not be null");
        return Integer.signum(left.compareTo(right));
    }

    static OptionalInt compareIfPresent(BigDecimal left, BigDecimal right) {
        if (left == null || right == null) {
            return OptionalInt.empty();
        }
        return OptionalInt.of(Integer.signum(left.compareTo(right)));
    }

    static boolean sameNumericValueIfPresent(BigDecimal left, BigDecimal right) {
        return left != null && right != null && left.compareTo(right) == 0;
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("equals = " + a.equals(b));
        System.out.println("Objects.equals(null, null) = " + Objects.equals(null, null));
        System.out.println("sameNumericValueIfPresent = " + sameNumericValueIfPresent(a, b));

        System.out.println("compareRequired = " + compareRequired(a, b));
        System.out.println("compareIfPresent(null, b).isEmpty = "
                + compareIfPresent(null, b).isEmpty());
        try {
            compareRequired(null, b);
        } catch (NullPointerException ex) {
            System.out.println("compareRequired(null, b) = rejected");
        }

        Comparator<BigDecimal> nullsFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        Comparator<BigDecimal> nullsLast =
                Comparator.nullsLast(Comparator.naturalOrder());
        System.out.println("nullsFirst(null, 0) = "
                + Integer.signum(nullsFirst.compare(null, BigDecimal.ZERO)));
        System.out.println("nullsLast(null, 0) = "
                + Integer.signum(nullsLast.compare(null, BigDecimal.ZERO)));

        List<BigDecimal> values = new ArrayList<>(Arrays.asList(
                new BigDecimal("2.0"), null, b, a, null, BigDecimal.ZERO));
        values.sort(nullsLast);
        System.out.println("sorted = " + values);

        Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
        Set<BigDecimal> naturalTreeSet = new TreeSet<>(List.of(a, b));
        Comparator<BigDecimal> numericThenScale =
                Comparator.<BigDecimal>naturalOrder().thenComparingInt(BigDecimal::scale);
        Set<BigDecimal> scaleAwareTreeSet = new TreeSet<>(numericThenScale);
        scaleAwareTreeSet.addAll(List.of(a, b));
        System.out.println("set sizes = " + hashSet.size() + "/"
                + naturalTreeSet.size() + "/" + scaleAwareTreeSet.size());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BigDecimalNullComparisonDemo.java
java BigDecimalNullComparisonDemo
```

Stdout đã xác minh trên Java 21; mã tương thích Java 17:

```text
compareTo = 0
equals = false
Objects.equals(null, null) = true
sameNumericValueIfPresent = true
compareRequired = 0
compareIfPresent(null, b).isEmpty = true
compareRequired(null, b) = rejected
nullsFirst(null, 0) = -1
nullsLast(null, 0) = 1
sorted = [0, 1.00, 1.0, 2.0, null, null]
set sizes = 2/1/2
```

Dòng cuối lần lượt là kích thước `HashSet`, `TreeSet` theo thứ tự tự nhiên và `TreeSet` xét thêm scale. Khi so sánh kết quả, cần phân biệt **cùng giá trị số**, **cùng biểu diễn gồm scale**, và **hai vị trí đứng cạnh nhau trong một danh sách đã sắp xếp**.

## 9. Chọn hợp đồng theo tình huống

| Tình huống | Hợp đồng khuyên dùng | Lý do |
| --- | --- | --- |
| Hai số tiền bắt buộc trước khi thanh toán | `Objects.requireNonNull` rồi `compareTo` | Thiếu dữ liệu phải bị từ chối |
| Sắp xếp danh sách có thể thiếu giá | `Comparator.nullsLast(Comparator.naturalOrder())` | Hiển thị được mọi dòng, giá thiếu ở cuối |
| Xếp mức thiếu lên đầu danh sách cần bổ sung | `Comparator.nullsFirst(...)` | Lộ rõ dữ liệu cần hoàn thiện |
| Quyết định một giá có vượt ngưỡng hay không, nhưng ngưỡng chưa có | `OptionalInt` hoặc enum có `UNKNOWN` | Không gán kết luận sai khi chưa đủ dữ liệu |
| So khớp giá trị thập phân không quan tâm số chữ số sau dấu phẩy | Hai bên khác null và `compareTo(...) == 0` | `equals` có xét scale |
| So khớp dữ liệu khi cả hai cùng null được xem là cùng trạng thái | Kiểm tra `left == right` trước rồi `compareTo` nếu đủ dữ liệu | Quy tắc nullable được diễn đạt rõ |
| Khóa phải phân biệt `1.0` và `1.00` | `equals`/`hashCode` hoặc comparator xét thêm scale | Giữ phân biệt biểu diễn |
| Khóa chỉ phân biệt giá trị số | Tập hợp có thứ tự theo `compareTo` hoặc chuẩn hóa được xác định trước | Tránh bất nhất định danh |

Nếu API có nhiều người gọi, nên mô tả trong Javadoc: đối số nào nullable; `null` nghĩa là gì; trả kết quả gì khi thiếu; so theo số học hay so theo scale; nếu dùng comparator thì null đứng ở đâu; nếu dùng làm khóa thì các giá trị nào được coi là trùng. Tránh tên `isEqual` hoặc `compare` quá chung khi có nhiều quy tắc null cùng tồn tại.

## 10. Lỗi phổ biến và bộ trường hợp kiểm tra

Các lỗi dễ xuất hiện:

1. Gọi `left.compareTo(right)` trong khi không chắc cả hai khác null.
2. Dùng `Objects.equals` để kiểm tra hai `BigDecimal` bằng nhau về số học, quên `scale`.
3. Coi `null` là 0 bằng cách `Objects.requireNonNullElse(value, BigDecimal.ZERO)` mà không có quy tắc nghiệp vụ.
4. Trả `0` khi một bên thiếu, làm sai ý nghĩa “đã so sánh và bằng nhau”.
5. Dùng `Comparator.nullsLast` trong điều kiện nghiệp vụ thay vì chỉ dùng để sắp xếp.
6. Bọc comparator của thuộc tính nullable, nhưng quên chính đối tượng chứa thuộc tính cũng có thể null.
7. Dùng `.reversed()` trên comparator null-last rồi ngạc nhiên vì null xuất hiện đầu.
8. Cho rằng `TreeSet` sẽ giữ hai `BigDecimal` có `equals == false` dù `compareTo == 0`.
9. Chuyển sang `double` trước khi so, có nguy cơ mất độ chính xác.
10. Chỉ test cặp giá trị thường, không test `null` và scale khác nhau.

Bộ tình huống tối thiểu cho một API nullable gồm `(null, null)`, `(null, 0)`, `(0, null)`, `(0, 0)`, `(1.0, 1.00)`, `(-1, 0)`, `(1, 2)`, `(2, 1)`. Với comparator, kiểm tra thêm chiều đối xứng, tính bắc cầu và kết quả khi dùng làm thứ tự của `TreeSet`/`TreeMap`.

Tóm lại, **`null` là trạng thái thiếu dữ liệu, `compareTo` là quan hệ thứ tự theo số học, còn `equals` xét cả scale**. Ba vấn đề ấy cần được quyết định riêng trong hợp đồng API. API từ chối dữ liệu thiếu, API sắp xếp có quy tắc null và API cho phép kết quả “chưa xác định” giải quyết những nhu cầu khác nhau.

Tài liệu Java SE 21 để đối chiếu:

- [`BigDecimal`: `compareTo`, `equals`, `min`, `max`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Comparable`: hợp đồng thứ tự và tính nhất quán với `equals`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html)
- [`Comparator`: `nullsFirst`, `nullsLast`, `comparing`, `reversed`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html)
- [`Objects`: `requireNonNull`, `equals`, `compare`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html)