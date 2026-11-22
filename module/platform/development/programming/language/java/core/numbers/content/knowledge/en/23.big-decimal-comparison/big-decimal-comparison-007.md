# Chính sách chuẩn hóa `scale` của `BigDecimal` trước khi lưu hoặc so sánh

## 1. Vì sao cần một chính sách chuẩn hóa?

Trong Java, hai đối tượng `BigDecimal` có thể biểu diễn **cùng một giá trị toán học** nhưng có **`scale` khác nhau**:

```java
BigDecimal a = new BigDecimal("1.0");  // scale = 1
BigDecimal b = new BigDecimal("1.00"); // scale = 2

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

`compareTo` chỉ xét thứ tự/giá trị số, trong khi `equals` còn yêu cầu cùng `scale`. Sự khác biệt này có thể gây kết quả bất ngờ khi dùng `BigDecimal` làm khóa `HashMap`, phần tử `HashSet`, dữ liệu định danh, giá trị lưu trong cơ sở dữ liệu hoặc trường trong bản ghi được so sánh bằng `equals`.

**Mục tiêu của bài:** xây dựng chính sách nhất quán để quyết định *khi nào* chuẩn hóa `scale`, *chuẩn hóa bằng cách nào* và *ở ranh giới nào* (trước khi lưu, trước khi so sánh, khi tạo khóa, khi trao đổi dữ liệu), mà không làm mất thông tin hoặc âm thầm thay đổi giá trị.

Không có một cách chuẩn hóa phù hợp cho mọi miền nghiệp vụ. Ba mục tiêu thường gặp rất khác nhau:

1. **So sánh giá trị số:** `1.0` và `1.00` được coi bằng nhau; có thể dùng `compareTo` trực tiếp.
2. **Tạo dạng biểu diễn duy nhất cho định danh/khóa:** hai giá trị số bằng nhau cần nhận cùng dạng `BigDecimal`; cân nhắc `stripTrailingZeros`.
3. **Lưu theo số chữ số thập phân cố định:** ví dụ số tiền với 2 chữ số phần thập phân; cần `setScale(2, ...)` theo chính sách hợp lệ hoặc làm tròn.

Nhầm lẫn ba mục tiêu này thường gây ra lỗi dữ liệu hoặc logic khó nhận ra.

## 2. Hiểu đúng `scale`, `precision` và tính bằng nhau

`BigDecimal` lưu giá trị dưới dạng:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

| Chuỗi khởi tạo | `precision()` | `scale()` | Giá trị số |
| --- | ---: | ---: | ---: |
| `"1.0"` | 2 | 1 | 1 |
| `"1.00"` | 3 | 2 | 1 |
| `"12.30"` | 4 | 2 | 12.3 |
| `"0.0000"` | 1 | 4 | 0 |
| `"1000.00"` | 6 | 2 | 1000 |

**Precision** là số chữ số có nghĩa của cách biểu diễn, còn **scale** xác định vị trí dấu thập phân. `MathContext(6)` giới hạn chữ số có nghĩa của phép tính; nó không phải chính sách “6 chữ số sau dấu phẩy” để lưu dữ liệu. Để yêu cầu scale cố định, dùng `setScale`.

Những phương thức quan trọng:

- `a.compareTo(b) == 0`: bằng nhau về **giá trị số**, bỏ qua khác biệt do scale.
- `a.equals(b)`: bằng nhau cả về **giá trị số lẫn scale**.
- `a.hashCode()`: tương ứng với `equals`; vì vậy những số bằng nhau theo `compareTo` nhưng khác scale thường có hash code khác nhau.
- `a.stripTrailingZeros()`: loại bỏ các số 0 dư ở cuối cách biểu diễn, có thể tạo scale âm.
- `a.setScale(targetScale, roundingMode)`: tạo đối tượng có scale yêu cầu; có thể chỉ thêm số 0 hoặc cần bỏ bớt chữ số.
- `a.toPlainString()`: xuất chuỗi thập phân không dùng ký hiệu số mũ, không phải thao tác chuẩn hóa khóa.

`BigDecimal` bất biến: tất cả phương thức biến đổi trả về đối tượng mới hoặc giá trị mới. Cần sử dụng giá trị trả về; gọi `amount.setScale(2, ...)` mà không gán lại sẽ không thay đổi `amount`.

## 3. Chính sách A — Chỉ cần so sánh giá trị số

Nếu câu hỏi nghiệp vụ là “hai số này có cùng độ lớn không?”, **không cần chuẩn hóa trước khi so sánh**:

```java
BigDecimal supplied = new BigDecimal("10.500");
BigDecimal expected = new BigDecimal("10.5");

boolean sameNumericValue = supplied.compareTo(expected) == 0; // true
boolean greater = supplied.compareTo(expected) > 0;            // false
```

Dùng `compareTo` để so sánh `>`, `<`, `>=`, `<=` hoặc bằng nhau về số học. Không dùng `equals` khi scale không có ý nghĩa nghiệp vụ.

Không được làm tròn/ép scale chỉ để “giúp so sánh” nếu cần so sánh giá trị gốc:

```java
BigDecimal x = new BigDecimal("1.004");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y) == 0); // false
```

Nếu cả hai được làm tròn về 2 chữ số thập phân với `HALF_EVEN`, chúng đều thành `1.00`. Khi ấy so sánh sau làm tròn là một **quyết định nghiệp vụ khác**, vì đã cố ý loại bỏ sự khác nhau ở phần nghìn. Phải xác định rõ đang so sánh giá trị gốc hay giá trị sau lượng tử hóa.

### Vì sao `HashSet` và `TreeSet` có thể cho kết quả khác?

`HashSet` và `HashMap` sử dụng `equals`/`hashCode` của phần tử hoặc khóa; vì thế `new BigDecimal("1.0")` và `new BigDecimal("1.00")` được coi là hai khóa khác nhau. `TreeSet` với thứ tự tự nhiên sử dụng `compareTo`; vì thế hai giá trị này được coi là cùng vị trí sắp xếp và một trong hai không được thêm vào. Đây là đặc điểm quan trọng của `BigDecimal`: thứ tự tự nhiên **không nhất quán với `equals`**.

Không thay `HashSet` bằng `TreeSet` chỉ để né chuẩn hóa. Hãy định nghĩa trước quy tắc bằng nhau của bộ dữ liệu rồi chọn cách triển khai phù hợp.

## 4. Chính sách B — Chuẩn hóa theo giá trị số để dùng làm khóa

Khi hệ thống muốn `1`, `1.0` và `1.00` là **cùng một khóa**, có thể đưa mọi giá trị về dạng chuẩn bằng `stripTrailingZeros()`:

```java
BigDecimal a = new BigDecimal("1.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("1.00").stripTrailingZeros();

System.out.println(a.equals(b)); // true
```

Hàm chuẩn hóa sau hỗ trợ giá trị `0` nhất quán và từ chối `null` một cách rõ ràng:

```java
import java.math.BigDecimal;
import java.util.Objects;

public static BigDecimal numericKey(BigDecimal input) {
    BigDecimal normalized =
            Objects.requireNonNull(input, "input").stripTrailingZeros();
    return normalized.signum() == 0 ? BigDecimal.ZERO : normalized;
}
```

Đây là **một phương thức minh họa**, đặt trong lớp Java hoặc dùng phương thức cùng tên trong chương trình hoàn chỉnh ở mục 7.

Hai lưu ý khi áp dụng:

**1. `stripTrailingZeros()` có thể tạo scale âm.**

```java
BigDecimal canonical = new BigDecimal("1000.00").stripTrailingZeros();

System.out.println(canonical.toString());      // 1E+3
System.out.println(canonical.toPlainString()); // 1000
System.out.println(canonical.scale());         // -3
```

Scale âm hợp lệ, không biểu thị sai số. Đừng giả định dạng chuẩn hóa sẽ luôn có `scale >= 0`. Nếu cần chữ số thập phân cố định, hãy dùng chính sách C ở mục tiếp theo.

**2. Chuỗi hiển thị và khóa `BigDecimal` không hoàn toàn là cùng một hợp đồng.**

`canonical.toPlainString()` từ ví dụ trên xuất `"1000"`. Tạo lại `new BigDecimal("1000")` sẽ có `scale == 0`; nó *bằng về số học* nhưng không `equals` với giá trị chuẩn có scale `-3`. Vì thế, nếu đọc khóa từ chuỗi hoặc hệ thống khác, **chuẩn hóa lại cả hai phía** khi cần so sánh bằng `equals`/làm khóa hash. Không coi `toPlainString` là phép round-trip bảo toàn scale.

Chính sách `numericKey` phù hợp cho khóa tra cứu, khử trùng lặp và nhóm dữ liệu theo **giá trị số**. Phải áp dụng nhất quán ở cả lúc chèn, lúc tìm và lúc khôi phục dữ liệu từ kho lưu trữ. Không chỉ chuẩn hóa một nhánh dữ liệu.

## 5. Chính sách C — Ép `scale` cố định trước khi lưu

Nhiều mô hình lưu trữ có ràng buộc số chữ số phần thập phân, chẳng hạn một cột SQL `DECIMAL(18,2)` hoặc loại giá trị tiền tệ với hai chữ số thập phân. Lúc này, chính sách có thể là:

- Giá trị hợp lệ phải **biểu diễn chính xác** ở scale đích, nếu không thì từ chối.
- Hoặc giá trị được phép **làm tròn** theo quy tắc nghiệp vụ đã công bố, rồi lưu scale đích.

### 5.1. Chính sách nghiêm ngặt: không cho phép mất thông tin

```java
BigDecimal amount = new BigDecimal("12.3");
BigDecimal storage = amount.setScale(2, RoundingMode.UNNECESSARY);
// 12.30
```

`UNNECESSARY` yêu cầu không cần bỏ chữ số có giá trị. `12.3` trở thành `12.30`, và `12.3400` trở thành `12.34` mà vẫn chính xác. Nhưng `12.345` không thể lưu chính xác ở scale 2 nên ném `ArithmeticException`.

Dùng cách này khi đầu vào bắt buộc tuân thủ hợp đồng, ví dụ giá sản phẩm chỉ nhận đơn vị nhỏ nhất là xu. Nếu dữ liệu đầu vào có độ chi tiết vượt quá quy định, một lỗi xác thực minh bạch tốt hơn việc cắt hoặc tự làm tròn.

### 5.2. Chính sách cho phép làm tròn

```java
BigDecimal raw = new BigDecimal("2.345");
BigDecimal stored = raw.setScale(2, RoundingMode.HALF_EVEN);
// 2.34
```

Với `HALF_EVEN`, điểm giữa được làm tròn về chữ số cuối chẵn:

| Giá trị | `setScale(2, HALF_EVEN)` |
| --- | --- |
| `2.345` | `2.34` |
| `2.355` | `2.36` |
| `12.3` | `12.30` |

Chọn `RoundingMode` theo quy tắc nghiệp vụ, pháp lý hoặc hợp đồng trao đổi dữ liệu: `HALF_EVEN` không phải mặc định đúng cho mọi loại tiền tệ/giao dịch. Chẳng hạn `DOWN` cắt phần dư về phía 0, khác với `FLOOR` đối với số âm. Không được dùng `setScale(2)` thiếu chế độ làm tròn nếu đầu vào có thể cần làm tròn: overload đó có thể ném `ArithmeticException`.

**Nguyên tắc:** phân biệt rõ “kiểm tra dữ liệu có scale hợp lệ” với “cho phép biến đổi giá trị về scale hợp lệ”. Hai đường đi này phải có tên hàm và cách xử lý lỗi tách bạch.

## 6. Đặt quy tắc ở đúng ranh giới hệ thống

### 6.1. Trước khi ghi cơ sở dữ liệu

Giả sử cột `amount DECIMAL(18,2)` có tổng cộng tối đa 18 chữ số thập phân, trong đó 2 chữ số phần thập phân. Nó cho phép tối đa 16 chữ số phần nguyên. Một quy trình lưu an toàn nên:

1. Xác định scale và quy tắc làm tròn của miền dữ liệu.
2. Kiểm tra đầu vào/null, trường hợp vượt miền giá trị và các quy tắc nghiệp vụ khác.
3. Áp dụng `setScale(2, UNNECESSARY)` nếu cần bảo toàn chính xác, hoặc `setScale(2, selectedMode)` nếu được phép làm tròn.
4. Kiểm tra giá trị chuẩn hóa có phù hợp `precision` và phạm vi của cột hay không.
5. Ghi qua JDBC/ORM với kiểu số thập phân phù hợp; đọc lại và kiểm tra nếu hợp đồng đòi tương đương chính xác.

Ví dụ ánh xạ ORM `@Column(precision = 18, scale = 2)` chỉ mô tả cột dự kiến; hành vi làm tròn, ép kiểu hoặc từ chối của cơ sở dữ liệu và trình điều khiển có thể khác nhau. **Không dựa vào database để âm thầm chọn chính sách làm tròn thay cho ứng dụng.** Đặc biệt, scale của đối tượng `BigDecimal` sau khi đọc qua JDBC có thể phản ánh kiểu cột/driver, không nhất thiết giữ nguyên cách biểu diễn trong đầu vào ban đầu.

Với các số đo, kết quả khoa học hoặc tỷ lệ có precision biến đổi, việc áp đặt scale 2 sẽ làm mất dữ liệu. Chọn schema, scale và quy tắc lưu phù hợp từng loại giá trị.

### 6.2. Trước khi tạo khóa `Map`, `Set`, cache hoặc nhóm dữ liệu

Nếu định danh dựa trên giá trị số:

```java
Map<BigDecimal, String> labels = new HashMap<>();
labels.put(numericKey(new BigDecimal("5.0")), "five");

String found = labels.get(numericKey(new BigDecimal("5.00")));
// "five"
```

Mã nhúng này cần `import java.util.Map; import java.util.HashMap;` và phương thức `numericKey` đã định nghĩa. Nên tập trung bước chuẩn hóa ở constructor, factory, value object hoặc lớp truy cập dữ liệu để mọi nơi chèn và truy vấn đều tuân thủ cùng hợp đồng.

Nếu scale có ý nghĩa nghiệp vụ — ví dụ số đo `"1.0"` có độ phân giải khác `"1.00"` — **đừng chuẩn hóa mất scale** khi thiết kế định danh, nhật ký kiểm toán hoặc kiểm tra tính bằng nhau.

### 6.3. Trước khi so sánh đối tượng chứa `BigDecimal`

Một `record`, đối tượng value hoặc DTO tự sinh `equals` có thể kế thừa hành vi `BigDecimal.equals`. Vì vậy:

- Nếu scale là một phần bản sắc dữ liệu, giữ nguyên `BigDecimal` và dùng `equals` bình thường.
- Nếu chỉ giá trị số quyết định tính bằng nhau, chuẩn hóa tại lúc xây dựng đối tượng rồi giữ bất biến; nếu tự định nghĩa `equals`, phải định nghĩa `hashCode` tương ứng.
- Với so sánh một lần theo giá trị, dùng `compareTo` trực tiếp, không cần sửa dữ liệu đang lưu.

Không triển khai `equals` dựa trên `compareTo` nhưng giữ `hashCode` mặc định của `BigDecimal`; điều đó vi phạm hợp đồng các đối tượng bằng nhau phải có cùng hash code.

### 6.4. Khi trao đổi JSON hoặc chuỗi

Nếu hệ thống yêu cầu biểu diễn văn bản **đúng hai chữ số phần thập phân**, hãy dùng `setScale(2, ...)` rồi `toPlainString()` trong bước xuất. Nếu hệ thống yêu cầu **dạng số thập phân chuẩn theo giá trị**, có thể xuất `numericKey(value).toPlainString()` và buộc phía nhận áp dụng lại quy tắc chuẩn hóa.

JSON cho phép biểu diễn số theo nhiều chuỗi chữ số; serializer, parser và ngôn ngữ tiêu thụ có thể xử lý scale khác nhau hoặc chuyển về kiểu dấu chấm động. Nếu phải giữ nguyên số 0 cuối hoặc chuỗi gốc để ký số/kiểm toán, hãy xác định rõ schema và encoding (có thể dùng chuỗi JSON nếu giao thức cho phép) thay vì dựa vào hành vi ngầm của thư viện.

## 7. Ví dụ Java 17+ hoàn chỉnh

Lưu file **`BigDecimalScalePolicyDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;

public class BigDecimalScalePolicyDemo {
    private static final int MONEY_SCALE = 2;

    // Chính sách khóa: cùng giá trị số -> cùng BigDecimal chuẩn hóa.
    static BigDecimal numericKey(BigDecimal input) {
        BigDecimal normalized =
                Objects.requireNonNull(input, "input").stripTrailingZeros();
        return normalized.signum() == 0 ? BigDecimal.ZERO : normalized;
    }

    // Chính sách lưu nghiêm ngặt: từ chối mọi giá trị cần làm tròn.
    static BigDecimal strictAmount(BigDecimal input) {
        return Objects.requireNonNull(input, "input")
                .setScale(MONEY_SCALE, RoundingMode.UNNECESSARY);
    }

    // Chính sách lưu cho phép làm tròn (chỉ là ví dụ nghiệp vụ).
    static BigDecimal roundedAmount(BigDecimal input) {
        return Objects.requireNonNull(input, "input")
                .setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("numeric equals: " + (a.compareTo(b) == 0));
        System.out.println("object equals: " + a.equals(b));
        System.out.println("raw set size: "
                + new HashSet<>(List.of(a, b)).size());
        System.out.println("canonical set size: "
                + new HashSet<>(List.of(numericKey(a), numericKey(b))).size());

        BigDecimal thousand = numericKey(new BigDecimal("1000.00"));
        System.out.println("canonical text: " + thousand.toPlainString());
        System.out.println("canonical scale: " + thousand.scale());
        System.out.println("zero scale: "
                + numericKey(new BigDecimal("0.0000")).scale());

        System.out.println("strict amount: "
                + strictAmount(new BigDecimal("12.3")).toPlainString());

        try {
            strictAmount(new BigDecimal("12.345"));
        } catch (ArithmeticException ex) {
            System.out.println("reject excessive decimals");
        }

        System.out.println("round 2.345: "
                + roundedAmount(new BigDecimal("2.345")).toPlainString());
        System.out.println("round 2.355: "
                + roundedAmount(new BigDecimal("2.355")).toPlainString());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac BigDecimalScalePolicyDemo.java
java BigDecimalScalePolicyDemo
```

Đầu ra:

```text
numeric equals: true
object equals: false
raw set size: 2
canonical set size: 1
canonical text: 1000
canonical scale: -3
zero scale: 0
strict amount: 12.30
reject excessive decimals
round 2.345: 2.34
round 2.355: 2.36
```

Trong chương trình, `numericKey` chuẩn hóa biểu diễn để có hành vi `equals`/hash ổn định theo giá trị số, trong khi `strictAmount` và `roundedAmount` thực thi **hai chính sách lưu khác nhau**. `toPlainString` quyết định biểu diễn văn bản; `setScale` quyết định scale, và có thể quyết định việc làm tròn. Ba trách nhiệm này không được đánh đồng.

## 8. Những trường hợp biên phải kiểm thử

**Giá trị 0 và dấu âm:** `new BigDecimal("0.0000").stripTrailingZeros()` thành giá trị `BigDecimal.ZERO` với scale 0. Nếu hệ thống phải giữ đầu vào nguyên văn (ví dụ dấu `-0.00` trong một thông điệp ban đầu), cần lưu thêm văn bản gốc riêng; chuẩn hóa số học không bảo tồn tất cả chi tiết văn bản.

**Scale âm:** `1000.00` sau `stripTrailingZeros` có thể thành `1E+3`, scale `-3`. Đây là số hợp lệ; chấp nhận khi dùng làm khóa chuẩn, hoặc dùng chính sách scale cố định nếu kho lưu không hỗ trợ ý nghĩa biểu diễn đó.

**Scale cao nhưng chỉ có số 0:** `new BigDecimal("1.2300").setScale(2, UNNECESSARY)` thành `1.23` mà không mất giá trị. Đếm số ký tự phần thập phân của văn bản nguồn để từ chối tất cả trường hợp quá hai chữ số sẽ khác chính sách “không mất thông tin” này; hãy chọn rõ một trong hai.

**Giá trị sát ngưỡng làm tròn:** kiểm thử các giá trị như `2.345`, `2.355`, số âm và các giá trị rất nhỏ. Không dùng cùng một mode theo thói quen cho mọi miền. Đảm bảo so sánh trước hoặc sau làm tròn đúng theo hợp đồng.

**Đọc/ghi nhiều hệ thống:** canonicalize tại cùng ranh giới trên cả đường nhập và đường truy vấn; xem xét trường hợp SQL `DECIMAL`, JSON, serializer, cache và khóa phân tán có chính sách khác nhau.

**Bộ sưu tập:** kiểm thử chèn/truy vấn `HashMap`, `HashSet`, `TreeSet` với `1`, `1.0`, `1.00` để kiểm chứng quy tắc bằng nhau mong muốn.

**Input `double`:** tránh `new BigDecimal(0.1)` khi mục tiêu là giá trị thập phân chính xác `0.1`; chuyển đổi từ `double` có thể đã mang sai số trước khi bất kỳ chuẩn hóa scale nào diễn ra.

**Null/ngoại lệ:** quyết định liệu `null` có hợp lệ hay không. Các hàm ví dụ dùng `Objects.requireNonNull` để báo lỗi rõ ràng. Với `RoundingMode.UNNECESSARY`, `ArithmeticException` là tín hiệu đầu vào không thỏa hợp đồng; xử lý thành lỗi xác thực, không tự thay bằng 0 hoặc âm thầm làm tròn.

## 9. Bảng quyết định chính sách

| Nhu cầu | Cách làm | Lưu ý |
| --- | --- | --- |
| So sánh giá trị số, không quan tâm scale | `a.compareTo(b) == 0` | Không cần biến đổi đầu vào |
| So sánh cả giá trị và scale | `a.equals(b)` | `1.0` khác `1.00` |
| Khóa hash đồng nhất theo giá trị số | `numericKey(a)` trước khi chèn/tìm | Chuẩn hóa mọi phía; có thể tạo scale âm |
| Lưu đúng scale 2, không mất dữ liệu | `a.setScale(2, UNNECESSARY)` | Ném ngoại lệ nếu cần làm tròn |
| Lưu đúng scale 2, cho phép làm tròn | `a.setScale(2, selectedMode)` | Mode phải theo hợp đồng nghiệp vụ |
| Chuỗi số học chuẩn không có ký hiệu mũ | `numericKey(a).toPlainString()` | Khi parse lại, chuẩn hóa nếu dùng làm khóa |
| Lưu nguyên độ phân giải/biểu diễn đầu vào | Giữ `BigDecimal` và/hoặc chuỗi gốc | Không loại 0 cuối vô điều kiện |

## 10. Bài tập tự kiểm tra

1. Vì sao `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false`, nhưng `compareTo` cho `0`? Điều gì xảy ra khi đưa hai giá trị vào `HashSet`?
2. Viết hàm tạo khóa của một bộ đếm theo giá trị số để `1000`, `1000.0`, `1E+3` trùng khóa. Kiểm tra scale của giá trị chuẩn.
3. Thiết kế API lưu số tiền `DECIMAL(18,2)` có hai đường đi rõ ràng: (a) chỉ cho phép giá trị chính xác; (b) chấp nhận làm tròn theo quy tắc đã định. Đầu vào `12.345` có kết quả gì với mỗi đường?
4. Hệ thống đo lường cần phân biệt độ phân giải giữa `1.0` và `1.00`. Có nên gọi `stripTrailingZeros` ngay khi đọc dữ liệu không? Vì sao?
5. Tại sao `numericKey(x).toPlainString()` không tự bảo đảm rằng `new BigDecimal(resultString).equals(numericKey(x))` cho mọi số nguyên có nhiều số 0 ở cuối?

Gợi ý: (1) `equals` so cả scale; `HashSet` giữ 2 phần tử nếu chưa chuẩn hóa. (2) áp dụng `stripTrailingZeros` nhất quán cho mọi khóa; số nguyên 1000 có thể có scale `-3`. (3) đường nghiêm ngặt từ chối; đường làm tròn chọn kết quả theo mode, ví dụ `HALF_EVEN` thành `12.34`. (4) không, vì scale chứa ý nghĩa đo lường. (5) `toPlainString` không ghi lại scale âm, nên cần chuẩn hóa lại giá trị sau parse nếu dùng `BigDecimal.equals`.

**Kết luận thực hành:** đặt tên và ghi rõ chính sách tại ranh giới. So sánh số học dùng `compareTo`; khóa đồng nhất số học có thể dùng `stripTrailingZeros`; lưu có scale cố định dùng `setScale` với quy tắc mất dữ liệu minh bạch. Chỉ chuẩn hóa khi biết chắc scale không chứa thông tin có ý nghĩa trong miền đang xử lý.

Tài liệu đối chiếu: [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), đặc biệt `compareTo`, `equals`, `hashCode`, `stripTrailingZeros`, `setScale` và `toPlainString`.
