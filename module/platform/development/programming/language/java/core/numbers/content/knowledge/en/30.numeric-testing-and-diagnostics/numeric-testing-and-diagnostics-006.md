# Kiểm tra `BigDecimal` cả giá trị và scale khi hợp đồng yêu cầu

## 1. Vì sao kiểm thử `BigDecimal` phải xác định rõ hợp đồng?

Một `BigDecimal` chứa **giá trị thập phân** và **scale** (vị trí dấu thập phân). Hai đối tượng có thể cùng giá trị toán học nhưng khác scale:

~~~java
BigDecimal a = new BigDecimal("12.0");
BigDecimal b = new BigDecimal("12.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
System.out.println(a.scale());            // 1
System.out.println(b.scale());            // 2
~~~

Về số học, cả hai đều bằng 12. Tuy nhiên, `12.0` lưu unscaled value 120 và scale 1; `12.00` lưu unscaled value 1200 và scale 2. Hai cách biểu diễn này có thể mang ý nghĩa khác nhau đối với định dạng đầu ra, chính sách phần thập phân, hợp đồng dữ liệu hoặc kiểm thử.

**Quy tắc quan trọng:** Trước khi viết phép kiểm tra, phải hỏi hợp đồng yêu cầu gì:

1. Chỉ cần **giá trị toán học** bằng nhau?
2. Cần **giá trị và scale** bằng nhau?
3. Cần một **scale chuẩn cụ thể**, ví dụ đúng 2, dù nguồn có thể truyền scale khác?
4. Cần **biểu diễn văn bản** giống hệt, gồm chữ số 0 tận cùng, dấu cộng, ký pháp mũ hay định dạng locale?

Đây là các yêu cầu khác nhau. Không có một phép so sánh duy nhất phù hợp mọi trường hợp.

## 2. Hiểu rõ giá trị, scale và precision

Về cấu trúc:

~~~text
Giá trị = unscaledValue × 10^(-scale)
~~~

Ví dụ:

| Cách tạo | Giá trị toán học | Unscaled value | Scale | Precision |
| --- | --- | ---: | ---: | ---: |
| `new BigDecimal("12")` | 12 | 12 | 0 | 2 |
| `new BigDecimal("12.0")` | 12 | 120 | 1 | 3 |
| `new BigDecimal("12.00")` | 12 | 1200 | 2 | 4 |
| `new BigDecimal("0.000")` | 0 | 0 | 3 | 1 |
| `new BigDecimal("1E+3")` | 1000 | 1 | -3 | 1 |

**Scale** không phải precision:

- Scale có thể **dương, bằng 0 hoặc âm**. Scale âm biểu diễn bội của 10 mũ dương, chẳng hạn `1E+3` có scale -3.
- Precision là số chữ số thập phân trong giá trị nguyên không scale, bỏ dấu; với zero, precision là 1.
- Hai số bằng nhau về giá trị có thể có precision lẫn scale khác nhau.
- `BigDecimal` không giữ trọn văn bản gốc: các ký tự `+0012.00` và `12.00` tạo ra đối tượng có cùng giá trị và scale, dù chuỗi nguồn khác nhau.

Nếu kiểm thử yêu cầu giữ nguyên **từng ký tự** đầu vào, chỉ so sánh `BigDecimal` là chưa đủ. Cần giữ và kiểm tra cả văn bản hoặc một bản ghi biểu diễn riêng.

## 3. `compareTo()` kiểm tra giá trị toán học

Phương thức:

~~~java
int comparison = expected.compareTo(actual);
~~~

trả số âm, 0 hoặc số dương tùy giá trị của `expected` nhỏ hơn, bằng hoặc lớn hơn `actual`. Khi cần kiểm tra bằng nhau **chỉ về giá trị số học**, dùng:

~~~java
boolean sameNumericValue = expected.compareTo(actual) == 0;
~~~

Các cặp ví dụ:

| Giá trị thứ nhất | Giá trị thứ hai | `compareTo(...) == 0` |
| --- | --- | --- |
| `1.0` | `1.00` | `true` |
| `0` | `0.000` | `true` |
| `1000` | `1E+3` | `true` |
| `12.00` | `12.01` | `false` |
| `-2.50` | `-2.5` | `true` |

`compareTo` phù hợp khi hợp đồng chỉ yêu cầu **kết quả số học bằng nhau**, ví dụ tổng 10.0 và 10.00 là tương đương về giá trị.

**Không nên so sánh `BigDecimal` bằng cách đổi sang `double` rồi so sánh gần đúng** nếu chính xác thập phân là mục tiêu. Ép sang `double` có thể làm tròn hoặc tràn phạm vi và khiến hai giá trị khác nhau thành cùng một giá trị nhị phân.

Tuy nhiên, `compareTo` **cố ý bỏ qua sự khác nhau về scale**. Nó không chứng minh đầu ra đáp ứng yêu cầu “phải có đúng hai chữ số thập phân ở dạng `BigDecimal`”.

## 4. `equals()` kiểm tra cả giá trị và scale

`BigDecimal.equals(Object)` yêu cầu cả giá trị và scale giống nhau. Có thể dùng:

~~~java
BigDecimal expected = new BigDecimal("12.00");
BigDecimal actual = new BigDecimal("12.0");

System.out.println(expected.equals(actual)); // false
System.out.println(expected.compareTo(actual) == 0); // true
~~~

Nếu hai đối tượng là `BigDecimal` hợp lệ, `equals` bằng `true` khi **cùng giá trị và cùng scale**. Một cách diễn đạt tường minh tương đương:

~~~java
boolean sameValueAndScale =
        expected.compareTo(actual) == 0
        && expected.scale() == actual.scale();
~~~

Nếu `expected` và `actual` có thể `null`, cần có chính sách null riêng. `Objects.equals(expected, actual)` hỗ trợ so sánh null an toàn nhưng vẫn sử dụng ngữ nghĩa `BigDecimal.equals`; hai giá trị null cùng nhau sẽ được xem là bằng nhau, điều này có thể **không hợp lệ** nếu hợp đồng bắt buộc có giá trị.

### 4.1. `equals` không phải kiểm tra định dạng chuỗi

Hai chuỗi sau khác nhau về mặt ký tự:

~~~java
String rawA = "+0012.00";
String rawB = "12.00";
~~~

Nhưng `new BigDecimal(rawA).equals(new BigDecimal(rawB))` là `true`. Constructor đã chuyển chuỗi thành số và không giữ nguyên ký tự cộng hay các zero đứng đầu.

Vì vậy:

- **Chỉ giá trị:** kiểm tra `compareTo == 0`.
- **Giá trị và scale:** dùng `equals` hoặc hai assertion tường minh.
- **Chuỗi hiển thị/trao đổi:** kiểm tra `String` sau khi format/serialize theo hợp đồng, ngoài kiểm tra giá trị số khi cần.

## 5. Viết assertion rõ ràng trong kiểm thử

### 5.1. Kiểm thử chỉ yêu cầu giá trị

Nếu dùng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.math.BigDecimal;

BigDecimal expected = new BigDecimal("12.00");
BigDecimal actual = new BigDecimal("12.0");

assertEquals(0, expected.compareTo(actual));
~~~

Đây là **đoạn mã đặt bên trong phương thức test JUnit 5**, không phải chương trình chạy độc lập. Câu assertion nói rõ rằng **khác scale được phép**.

Nếu muốn thông báo thất bại mang ý nghĩa nghiệp vụ:

~~~java
assertEquals(0, expected.compareTo(actual),
        "Gia tri thap phan phai bang nhau");
~~~

### 5.2. Kiểm thử cần cả giá trị và scale

~~~java
BigDecimal expected = new BigDecimal("12.00");
BigDecimal actual = new BigDecimal("12.0");

assertEquals(0, expected.compareTo(actual), "Sai gia tri");
assertEquals(expected.scale(), actual.scale(), "Sai scale");
~~~

Đoạn này sẽ **thất bại ở assertion scale**: expected scale = 2, actual scale = 1. Chia hai assertion giúp chẩn đoán nhanh **giá trị sai** hay **chỉ sai cách biểu diễn scale**.

Nếu chỉ cần một assertion, `assertEquals(expected, actual)` của JUnit sử dụng `equals` nên cũng kiểm tra cả hai. Việc tách assertion có giá trị khi thông báo lỗi cần nhấn mạnh hai khía cạnh khác nhau.

Trong production, tránh dùng câu lệnh Java `assert condition;` làm cơ chế thực thi hợp đồng vì Java assertion mặc định có thể bị tắt nếu không chạy với `-ea`. Trong kiểm thử, dùng API assertions của framework; ở ranh giới dữ liệu production, dùng kiểm tra và exception tường minh.

### 5.3. Nếu yêu cầu scale cố định

Có hợp đồng không cần giữ scale giống một đối tượng expected, mà quy định **mọi kết quả phải có scale = 2**:

~~~java
BigDecimal actual = new BigDecimal("12.00");

assertEquals(0, actual.compareTo(new BigDecimal("12")));
assertEquals(2, actual.scale());
~~~

Đây là yêu cầu **giá trị bằng 12 và scale đúng 2**. Tách hai điều kiện là cách dễ thấy nhất để xác nhận hợp đồng.

Không thay assertion scale bằng `actual.toPlainString().endsWith("00")`: kiểm tra ký tự cuối không chứng minh đúng số chữ số sau dấu thập phân hoặc giá trị mong muốn.

## 6. Chuẩn hóa scale: `setScale` phải có chính sách rõ

Khi các nguồn vào có scale khác nhau nhưng contract quy định scale chuẩn, có thể chuẩn hóa ở **ranh giới nhập/xuất hoặc tầng domain**:

~~~java
BigDecimal raw = new BigDecimal("12.0");
BigDecimal canonical = raw.setScale(2, RoundingMode.UNNECESSARY);

System.out.println(canonical); // 12.00
System.out.println(canonical.scale()); // 2
~~~

`setScale(2, UNNECESSARY)` yêu cầu kết quả giữ nguyên giá trị khi chuyển sang scale 2. Các tình huống:

| Giá trị đầu vào | `setScale(2, UNNECESSARY)` | Lý do |
| --- | --- | --- |
| `12` | `12.00` | Thêm zero, không đổi giá trị |
| `12.0` | `12.00` | Thêm zero |
| `12.000` | `12.00` | Bỏ zero dư |
| `12.345` | `ArithmeticException` | Không thể bỏ chữ số 5 mà giữ đúng giá trị |
| `-0.000` | `0.00` | `BigDecimal` không bảo toàn zero âm theo IEEE 754 |

Nếu hợp đồng **cho phép làm tròn**, có thể chọn `HALF_UP` hoặc `HALF_EVEN`, chẳng hạn:

~~~java
BigDecimal rounded =
        new BigDecimal("12.345").setScale(2, RoundingMode.HALF_UP);
// 12.35
~~~

Lúc này giá trị đã thay đổi theo quy tắc được chọn. Hãy **kiểm tra giá trị sau làm tròn**, đồng thời kiểm tra scale. Không tự chuẩn hóa bằng `HALF_UP` chỉ để một bài test từ đỏ thành xanh, bởi hành động đó có thể che mất lỗi hợp đồng “không được làm tròn”.

### 6.1. Không sửa cả expected và actual bằng cùng cách rồi coi như xong

Một anti-pattern:

~~~java
// Che lỗi scale nếu hợp đồng đòi kết quả có scale = 2:
BigDecimal e = expected.stripTrailingZeros();
BigDecimal a = actual.stripTrailingZeros();
assertEquals(e, a);
~~~

Cách này bỏ khác biệt về scale trước khi kiểm tra. Nó phù hợp **chỉ khi** hợp đồng thực chất là so sánh giá trị, lúc đó hãy dùng `compareTo` để biểu đạt trực tiếp.

Ngược lại, nếu contract cho phép mọi biểu diễn đầu vào nhưng bắt buộc API xuất trả scale 2, hãy chuẩn hóa **ở đúng nơi sản xuất kết quả** rồi assert đầu ra có scale 2. Không nên để test tự sửa `actual` trước khi kiểm tra, vì có thể làm mất lỗi của code cần kiểm thử.

## 7. Cạm bẫy `stripTrailingZeros()`: scale có thể thành số âm

Phương thức `stripTrailingZeros()` loại bỏ số 0 tận cùng trong cách biểu diễn của `BigDecimal`, có thể làm scale giảm, kể cả sang **giá trị âm**:

~~~java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal stripped = x.stripTrailingZeros();

System.out.println(stripped);         // 1E+3
System.out.println(stripped.scale()); // -3
~~~

Giá trị vẫn bằng 1000, nhưng biểu diễn `1E+3` có scale -3. Nếu hợp đồng yêu cầu scale 2, việc gọi `stripTrailingZeros` làm đầu ra **vi phạm hợp đồng** dù giá trị số học không thay đổi.

Với zero:

~~~java
BigDecimal zero = new BigDecimal("0.000");
System.out.println(zero.scale()); // 3
System.out.println(zero.stripTrailingZeros().scale()); // 0
~~~

Zero sau `stripTrailingZeros()` được chuẩn hóa về `BigDecimal.ZERO` có scale 0. Khi kiểm thử hợp đồng “số không phải biểu diễn `0.00`”, cần cố ý tạo hoặc kiểm tra scale 2, ví dụ `BigDecimal.ZERO.setScale(2)`.

**Không xem `stripTrailingZeros` là cách chuẩn hóa scale về một scale cố định.** Nó là phép loại bỏ zero dư, có kết quả scale phụ thuộc vào giá trị cụ thể.

## 8. Những phép toán nào làm thay đổi scale?

Khi test các pipeline tính toán, không nên giả định scale đầu ra luôn trùng scale của một đầu vào. `BigDecimal` có các quy tắc preferred scale:

| Phép toán chính xác | Preferred scale điển hình |
| --- | --- |
| `a.add(b)`, `a.subtract(b)` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a.scale() + b.scale()` |
| `a.divide(b)` khi kết quả chính xác có biểu diễn thập phân hữu hạn | `a.scale() - b.scale()` là preferred scale; kết quả có thể cần scale lớn hơn |
| `a.setScale(target, mode)` | `target` khi thành công |
| `a.stripTrailingZeros()` | Có thể giảm, về 0 hoặc âm |

Ví dụ:

~~~java
BigDecimal first = new BigDecimal("1.20"); // scale 2
BigDecimal second = new BigDecimal("3.0"); // scale 1

System.out.println(first.add(second));      // 4.20, scale 2
System.out.println(first.multiply(second)); // 3.600, scale 3
~~~

Phép chia với `MathContext`, phép `round(context)`, hoặc thao tác có quy tắc làm tròn cụ thể có thể tạo scale khác các phép toán chính xác đơn giản. Vì vậy nếu API cam kết scale cụ thể, hãy kiểm tra scale **ở điểm trả kết quả**, không suy luận chỉ từ scale đầu vào.

**Precision cũng là khái niệm khác:** `new MathContext(3, HALF_UP)` giới hạn ba chữ số có nghĩa. Nó **không** tự bảo đảm scale 3 hoặc scale 2. Nếu cả precision và scale đều là điều kiện hợp đồng, phải kiểm tra cả hai theo chính sách có thứ tự rõ ràng.

## 9. Kết quả trong tập hợp và dữ liệu tra cứu

`BigDecimal.compareTo` và `BigDecimal.equals` có cách nhận định bằng nhau khác nhau. Điều này ảnh hưởng đến collection:

~~~java
BigDecimal a = new BigDecimal("12.0");
BigDecimal b = new BigDecimal("12.00");

Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
Set<BigDecimal> treeSet = new TreeSet<>(List.of(a, b));

System.out.println(hashSet.size()); // 2
System.out.println(treeSet.size()); // 1
~~~

Đây là đoạn mã minh họa với import `java.math.BigDecimal` và `java.util.*`.

- `HashSet` dựa trên `equals`/`hashCode`, nên giữ hai `BigDecimal` khác scale thành **hai phần tử**.
- `TreeSet` dùng thứ tự tự nhiên `compareTo` để xác định phần tử bằng nhau theo comparator, nên xem hai giá trị bằng nhau về số học là **một phần tử**.

Khi dùng `BigDecimal` làm khóa trong `HashMap` hoặc `TreeMap`, hãy chọn collection có ngữ nghĩa phù hợp: đối tượng khác scale là khóa khác hay không? Đừng giả định chuyển từ map dạng hash sang map có sắp thứ tự chỉ ảnh hưởng thứ tự duyệt.

Nếu muốn các giá trị có scale khác nhau là cùng một khóa, nên thiết kế quy tắc chuẩn hóa rõ ràng; nếu muốn khác biệt scale có ý nghĩa, giữ ngữ nghĩa `equals` và kiểm thử cấu trúc dữ liệu tương ứng.

## 10. Test dữ liệu qua API, JSON, database

### 10.1. API/JSON

Giả sử một API công bố:

~~~json
{
  "amount": "12.00",
  "currency": "USD"
}
~~~

Nếu `amount` là chuỗi chuẩn với **đúng hai chữ số sau dấu thập phân**, có thể cần hai lớp assertion:

1. Parse `"12.00"` thành `BigDecimal` và xác minh **giá trị**, **scale**.
2. Kiểm tra chuỗi trao đổi đúng pattern, ví dụ **đúng hai chữ số ở phần thập phân, dấu chấm, không phân nhóm**.

`BigDecimal.equals` không bảo đảm chuỗi gốc không có dấu `+` hay zero dẫn đầu. Dù cùng một giá trị và scale, `"+0012.00"` và `"12.00"` khác nhau về văn bản. Nếu hợp đồng yêu cầu biểu diễn canonical, nên kiểm tra thêm trường chuỗi.

Nếu hợp đồng chỉ yêu cầu **giá trị thập phân bằng nhau**, không nên tự áp assertion scale chặt hơn đặc tả. Một producer có thể serialize cùng giá trị dưới các dạng `12`, `12.0` hoặc `12.00` mà vẫn thỏa yêu cầu giá trị. JSON number và JSON string cũng có cách parse khác nhau tùy thư viện và consumer; hãy kiểm tra đúng kiểu dữ liệu contract quy định.

### 10.2. JDBC và cột `DECIMAL`/`NUMERIC`

Các cột số thập phân ở database thường có precision/scale được khai báo trong schema, ví dụ `DECIMAL(12,2)`. Nhưng **cách driver/database trả về `BigDecimal` có thể chịu ảnh hưởng schema và hệ quản trị cụ thể**. Không suy ra một scale Java cụ thể từ dữ liệu mẫu mà không kiểm chứng hệ thống thực.

Nếu hợp đồng yêu cầu số đã đọc về có scale 2, kiểm tra tại boundary JDBC/repository. Nếu yêu cầu chỉ là cùng giá trị toán học, tránh để test thất bại chỉ vì scale khác mà schema hoặc driver cho phép.

Không biến `BigDecimal` sang `double` làm trung gian khi so sánh kết quả database nếu độ chính xác thập phân là yêu cầu. Việc làm tròn nhị phân có thể che hoặc tạo sai lệch.

### 10.3. Định dạng hiển thị

`DecimalFormat` hoặc `NumberFormat` có thể in `12.0` thành `12.00` mà **không sửa `BigDecimal` đầu vào**. Nếu hợp đồng chỉ nói “UI phải hiển thị hai số sau dấu chấm”, nên test chuỗi format. Nếu hợp đồng nói “domain trả `BigDecimal` scale 2”, phải test `scale()`. Hai phép kiểm tra khác nhau.

## 11. Ví dụ Java 17+ chạy độc lập: hai loại hợp đồng

Tạo tệp **BigDecimalContractDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalContractDemo {
    private static void requireNumeric(
            BigDecimal expected, BigDecimal actual) {
        if (expected.compareTo(actual) != 0) {
            throw new AssertionError("Numeric value differs");
        }
    }

    private static void requireValueAndScale(
            BigDecimal expected, BigDecimal actual) {
        requireNumeric(expected, actual);
        if (expected.scale() != actual.scale()) {
            throw new AssertionError("Scale differs");
        }
    }

    private static boolean passes(Runnable assertion) {
        try {
            assertion.run();
            return true;
        } catch (AssertionError ex) {
            return false;
        }
    }

    public static void main(String[] args) {
        BigDecimal expected = new BigDecimal("12.00");
        BigDecimal actual = new BigDecimal("12.0");

        System.out.println("compareTo zero: "
                + (expected.compareTo(actual) == 0));
        System.out.println("equals: " + expected.equals(actual));
        System.out.println("numeric assertion: "
                + passes(() -> requireNumeric(expected, actual)));
        System.out.println("value and scale assertion: "
                + passes(() -> requireValueAndScale(expected, actual)));

        BigDecimal normalized =
                actual.setScale(2, RoundingMode.UNNECESSARY);
        System.out.println("normalized: " + normalized.toPlainString());
        System.out.println("normalized assertion: "
                + passes(() -> requireValueAndScale(expected, normalized)));

        System.out.println("HashSet size: "
                + new HashSet<>(List.of(expected, actual)).size());
        System.out.println("TreeSet size: "
                + new TreeSet<>(List.of(expected, actual)).size());

        BigDecimal stripped =
                new BigDecimal("1000.00").stripTrailingZeros();
        System.out.println("stripped: " + stripped
                + ", scale: " + stripped.scale());

        BigDecimal zero =
                new BigDecimal("0.000").stripTrailingZeros();
        System.out.println("zero stripped scale: " + zero.scale());

        try {
            new BigDecimal("12.345")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("strict scale: ArithmeticException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalContractDemo.java
java BigDecimalContractDemo
~~~

Đầu ra chính xác:

~~~text
compareTo zero: true
equals: false
numeric assertion: true
value and scale assertion: false
normalized: 12.00
normalized assertion: true
HashSet size: 2
TreeSet size: 1
stripped: 1E+3, scale: -3
zero stripped scale: 0
strict scale: ArithmeticException
~~~

Chương trình sử dụng `AssertionError` để mô phỏng một phép assertion chủ động; `passes` chỉ giúp in ra `true`/`false` mà không dừng toàn bộ demo. Trong kiểm thử thật, **đừng bao lỗi assertion bằng `passes` rồi bỏ qua kết quả**: để JUnit báo test failed với tên trường hợp và thông tin expected/actual.

## 12. Các trường hợp kiểm thử cần có

Nên lập bộ test dựa trên chính hợp đồng, gồm các nhóm sau:

| Trường hợp | Giá trị mẫu | Điều cần xác minh |
| --- | --- | --- |
| Bằng giá trị, khác scale | `12.0` vs `12.00` | Chọn `compareTo` hay `equals` đúng yêu cầu |
| Bằng 0, khác scale | `0` vs `0.000` | Zero vẫn có scale |
| Dạng lũy thừa | `1E+3` vs `1000.00` | `compareTo` bằng 0; scale khác |
| Chuyển sang scale lớn hơn | `12` thành `12.00` | Không mất giá trị |
| Giảm scale nhờ zero dư | `12.000` thành `12.00` | Chuyển chính xác |
| Giảm scale làm mất chữ số | `12.345` sang scale 2 | Exception khi `UNNECESSARY`, hoặc làm tròn nếu được phép |
| `stripTrailingZeros` | `1000.00` | Scale có thể âm |
| Tính toán tổng | `1.20 + 2.345` | Giá trị chính xác và preferred scale |
| Pipeline serialize/parse | `"12.00"` qua JSON/JDBC | Giá trị, scale, chuỗi theo contract riêng |
| Đầu vào null | `null` | Từ chối hay chấp nhận có chủ đích |
| Số âm, số lớn và số rất nhỏ | `-0.0010`, `1E+20` | Không suy diễn scale theo độ lớn |

Một bộ kiểm thử đủ mạnh có thể gồm **test numeric**, **test value-and-scale**, **test canonical string** và **test chuyển đổi scale không mất giá trị**, tùy contract. Không cần ép mọi use case đều phải so scale: điều đó có thể biến khác biệt biểu diễn vô hại thành lỗi giả.

## 13. Các hiểu lầm thường gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| Hai `BigDecimal` cùng số thì `equals` luôn `true` | `equals` xét cả scale |
| `compareTo == 0` chứng minh scale bằng nhau | Nó chỉ chứng minh cùng giá trị toán học |
| `setScale(2, UNNECESSARY)` luôn thành công | Nó thất bại nếu muốn giữ giá trị mà phải loại chữ số khác 0 |
| `stripTrailingZeros` chuẩn hóa thành scale 0 | Scale có thể âm, như `1000.00 -> 1E+3` |
| `precision == scale` | Precision và scale là hai khái niệm độc lập |
| Test hiển thị chuỗi `12.00` đủ chứng minh domain scale 2 | Formatter có thể tạo chuỗi đó từ domain scale 1 |
| `HashSet` và `TreeSet` xem các `BigDecimal` bằng nhau theo cách giống nhau | Hash dùng `equals`/`hashCode`; tree dùng `compareTo` |
| Chuyển sang `double` sẽ làm so sánh đơn giản hơn | Có thể mất độ chính xác và làm sai kết quả |
| Dữ liệu từ SQL `DECIMAL` luôn có scale Java đúng như ta đoán | Phải dựa vào contract, schema và hành vi driver thực tế |
| Assertion Java luôn được chạy khi triển khai | Câu lệnh `assert` có thể bị vô hiệu hóa nếu không bật assertions |

## 14. Tự kiểm tra

1. `new BigDecimal("1.00").equals(new BigDecimal("1.0"))` trả gì? **`false`**, vì scale lần lượt là 2 và 1.
2. Cặp trên có `compareTo == 0` không? **Có**, vì giá trị toán học bằng nhau.
3. Khi một DTO cam kết amount có đúng scale 2, chỉ dùng `compareTo` đã đủ chưa? **Chưa**; phải kiểm tra scale 2.
4. Vì sao `new BigDecimal("1000.00").stripTrailingZeros().scale()` là -3? **Vì dạng kết quả `1E+3` giữ nguyên giá trị với unscaled value 1 và scale -3**.
5. `new BigDecimal("12.340").setScale(2, UNNECESSARY)` có thành công không? **Có**, kết quả `12.34`, vì chỉ bỏ zero dư.
6. `new BigDecimal("12.345").setScale(2, UNNECESSARY)` có thành công không? **Không**, vì không thể giữ nguyên giá trị ở scale 2.
7. Khi nào `assertEquals(expected, actual)` hợp lý hơn `assertEquals(0, expected.compareTo(actual))`? **Khi hợp đồng yêu cầu cùng cả giá trị và scale**.
8. Nếu API yêu cầu giữ chính xác văn bản `"0012.00"`, kiểm tra `BigDecimal.equals` có đủ không? **Không**, phải kiểm tra chuỗi gốc hoặc chuỗi xuất đúng quy tắc biểu diễn.

**Ghi nhớ:** Đối với `BigDecimal`, **bằng nhau về số** (`compareTo == 0`) và **bằng nhau về số lẫn scale** (`equals`, hoặc hai phép kiểm tra rõ ràng) không đồng nghĩa. Hãy viết assertion theo hợp đồng dữ liệu; chỉ chuẩn hóa scale khi chính sách cho phép và đừng vô tình bỏ scale bằng `stripTrailingZeros` trước khi kiểm thử một yêu cầu cần giữ scale.