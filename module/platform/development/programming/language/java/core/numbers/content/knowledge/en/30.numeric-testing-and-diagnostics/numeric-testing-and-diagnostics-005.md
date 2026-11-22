# Kiểm tra phép so sánh với sai số phù hợp trong Java

Khi kiểm thử hoặc chẩn đoán các phép tính số, không phải lúc nào so sánh hai kết quả bằng dấu `==` hoặc `equals()` cũng phản ánh đúng yêu cầu. Với số dấu phẩy động nhị phân (`float`, `double`), kết quả toán học mong muốn có thể được biểu diễn bằng giá trị xấp xỉ. Ngược lại, cho phép một mức sai số quá rộng có thể làm **bài kiểm thử chấp nhận cả kết quả thực sự sai**.

Mục tiêu của bài này là chọn **tiêu chí bằng nhau phù hợp với loại số và yêu cầu đo lường/nghiệp vụ**, dùng sai số tuyệt đối, sai số tương đối hoặc kết hợp hai tiêu chí khi hợp lý, và kiểm tra các trường hợp đặc biệt như số gần 0, độ lớn khác nhau, `NaN`, vô cực, số có dấu âm 0 và `BigDecimal`.

**Nguyên tắc:** trước khi viết assertion, phải trả lời “Hai kết quả này cần bằng nhau về mặt nào và được phép sai lệch bao nhiêu?”. Không có một hằng số `epsilon` đúng cho mọi phép tính, mọi đơn vị và mọi miền giá trị.

## 1. Vì sao `double` thường không nên so sánh chính xác bằng `==`?

Kiểu `double` Java dùng biểu diễn nhị phân IEEE 754 với độ chính xác hữu hạn. Nhiều phân số thập phân đơn giản, như 0,1 hoặc 0,2, không có biểu diễn nhị phân hữu hạn chính xác. Khi lưu và tính toán, giá trị phải được làm tròn theo quy tắc số dấu phẩy động.

Ví dụ:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual);             // 0.30000000000000004
System.out.println(actual == expected); // false
```

`actual` và `expected` là hai giá trị `double` gần nhau, nhưng **khác bit**, vì vậy `==` trả `false`. Trong một bài kiểm thử tính gần đúng, ta có thể chấp nhận mức sai lệch rất nhỏ nếu yêu cầu cho phép.

Tuy nhiên, `==` **không sai trong mọi trường hợp**:

- Khi kiểm tra một giá trị được quy định phải chính xác, như số nguyên nhỏ được biểu diễn chính xác trong `double`, so sánh chính xác có thể hợp lý.
- Khi kiểm tra những giá trị đặc biệt hoặc trạng thái, có thể cần kiểm tra **chính xác** hoặc kiểm tra bit, chứ không dùng sai số.
- Khi yêu cầu nghiệp vụ đòi chính xác tuyệt đối, không thể chữa thiết kế sai kiểu dữ liệu bằng cách tùy tiện thêm epsilon.

Những sai khác trong số dấu phẩy động có thể đến từ biểu diễn đầu vào, trình tự phép tính, sự làm tròn ở từng bước, phép biến đổi đại số, hoặc các thuật toán xấp xỉ. Một “khoảng chấp nhận” chỉ hữu ích khi có **cơ sở xác định độ sai lệch hợp lệ**.

## 2. Sai số tuyệt đối: dùng khi đơn vị và độ lệch tối đa quan trọng

Đặt giá trị tham chiếu là `expected` và kết quả cần kiểm tra là `actual`:

```text
absoluteError = |actual - expected|

Chấp nhận khi:
|actual - expected| <= absoluteTolerance
```

Ví dụ, nếu phép đo được phép lệch tối đa 0,01 đơn vị, ta có thể kiểm tra:

```java
boolean acceptable =
        Math.abs(actual - expected) <= 0.01;
```

Đây là **đoạn minh họa** trong phạm vi các biến `actual` và `expected` là số `double` hữu hạn, cùng đơn vị, không quá lớn đến mức hiệu bị tràn. Trường hợp `NaN` hoặc vô cực cần được xử lý riêng nếu bài kiểm thử có thể gặp chúng.

### Lợi ích và giới hạn

Sai số tuyệt đối dễ diễn đạt theo đơn vị, chẳng hạn “không được lệch quá 0,001 giây” hoặc “không lệch quá 0,1 °C”, **nếu giới hạn đó thực sự được đặc tả**. Nó đặc biệt có ích gần **giá trị 0**.

Nhưng một ngưỡng cố định có thể quá lỏng với số rất nhỏ hoặc quá chặt với số rất lớn:

| Expected | Actual | Sai số tuyệt đối | Kết quả với tolerance = 0,001 |
|---:|---:|---:|---|
| 0 | 0,0005 | 0,0005 | Chấp nhận |
| 1000 | 1000,0005 | 0,0005 | Chấp nhận |
| 1.000.000.000 | 1.000.000.000,1 | Khoảng 0,1 | Từ chối |

Ví dụ cuối có sai lệch khoảng một phần mười tỷ theo tỷ lệ, nhưng bị từ chối bởi ngưỡng tuyệt đối 0,001. Điều này có thể đúng hoặc sai tùy yêu cầu: nếu sai số tuyệt đối phải nhỏ hơn 0,001 thì **phải từ chối**, bất kể số lớn đến đâu.

## 3. Sai số tương đối: đánh giá sai lệch theo độ lớn

Một tiêu chí khác là so sánh sai lệch với độ lớn của giá trị tham chiếu:

```text
relativeError = |actual - expected| / |expected|
```

Công thức này có vấn đề khi `expected = 0`, vì phép chia cho 0 không cho một sai số tương đối hữu ích. Nếu expected gần 0, tỷ lệ còn có thể phóng đại một sai lệch tuyệt đối rất nhỏ.

Trong trường hợp so sánh hai giá trị gần đúng một cách **đối xứng**, có thể dùng thước đo:

```text
scale = max(|expected|, |actual|)
relativeCondition: |actual - expected| <= relTol * scale
```

Nếu cả hai bằng 0, điều kiện bằng nhau chính xác đã được đáp ứng. Khi hai số rất gần 0 nhưng không bằng nhau, tiêu chí tương đối một mình thường quá khắt khe; lúc này cần cân nhắc ngưỡng tuyệt đối.

**Cần phân biệt:** “sai số tương đối so với expected” và “ngưỡng tương đối đối xứng theo max độ lớn” là hai định nghĩa khác nhau. Trong tài liệu kiểm thử, nên viết rõ công thức thay vì chỉ ghi “dùng epsilon tương đối”.

## 4. Kết hợp absolute tolerance và relative tolerance

Một phép kiểm tra tổng quát cho nhiều phép tính `double` hữu hạn là:

```text
diff = |actual - expected|
scale = max(|expected|, |actual|)

acceptable = diff <= max(absTol, relTol * scale)
```

Giải thích:

- **`absTol`** là khoảng sai lệch tuyệt đối cho phép, hữu ích quanh 0.
- **`relTol`** cho phép sai lệch thay đổi theo độ lớn, hữu ích với những đại lượng rất lớn.
- Dùng `max` nghĩa là một trong hai giới hạn đủ để chấp nhận. Đây là chính sách dung sai **kết hợp theo OR**, không đồng nghĩa “phải đồng thời thỏa cả hai”.
- Nếu nghiệp vụ yêu cầu **cả** sai số tuyệt đối lẫn tương đối phải dưới ngưỡng, hãy kiểm tra **hai điều kiện AND** riêng. Không tùy ý dùng công thức `max` cho một hợp đồng nghiêm ngặt hơn.

Ví dụ giả định `absTol = 1e-12` và `relTol = 1e-9`:

| Expected | Actual | Đánh giá |
|---:|---:|---|
| `0.3` | `0.1 + 0.2` | Chấp nhận: sai số nhị phân rất nhỏ |
| `0.0` | `1e-13` | Chấp nhận: nằm trong ngưỡng tuyệt đối |
| `0.0` | `1e-8` | Từ chối: vượt ngưỡng tuyệt đối và tiêu chí tương đối |
| `1e9` | `1e9 + 0.1` | Chấp nhận: sai số nhỏ theo tỷ lệ |
| `1.0` | `1.1` | Từ chối: sai lệch quá lớn |

**Các ngưỡng trên chỉ phục vụ ví dụ minh họa**, không phải giá trị mặc định nên sao chép vào mọi dự án. Khi kiểm thử thuật toán khoa học, các ngưỡng có thể xuất phát từ phân tích sai số số học, chất lượng phương pháp xấp xỉ hoặc yêu cầu độ chính xác. Với phép đo vật lý, có thể phải xét độ phân giải thiết bị. Với dữ liệu tài chính/đếm/số định danh, phải dùng quy tắc khác.

### Một hàm so sánh gần bằng an toàn cho double

```java
static boolean nearlyEqual(
        double expected, double actual,
        double absTol, double relTol) {

    if (!Double.isFinite(absTol) || absTol < 0.0
            || !Double.isFinite(relTol)
            || relTol < 0.0 || relTol >= 1.0) {
        throw new IllegalArgumentException(
                "Invalid tolerance");
    }

    if (Double.isNaN(expected) || Double.isNaN(actual)) {
        return false;
    }

    if (expected == actual) {
        return true;
    }

    if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
        return false;
    }

    double difference = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(expected), Math.abs(actual));

    return difference <= Math.max(absTol, relTol * scale);
}
```

Đây là **một phương thức** có thể đặt trong lớp Java. Các quyết định thiết kế của nó cần được hiểu rõ:

1. Ngưỡng được yêu cầu hữu hạn, không âm; `relTol < 1` để ngăn một ngưỡng tương đối vô nghĩa có thể chấp nhận chênh lệch cực lớn. Đây là ràng buộc của **hàm minh họa**, không phải giới hạn chung của mọi API.
2. `NaN` luôn bị coi là không so sánh gần bằng, kể cả khi hai phía đều là `NaN`. Nếu bài test **mong đợi NaN**, hãy kiểm tra riêng bằng `Double.isNaN(...)`.
3. Hai giá trị vô cực cùng dấu được coi là bằng nhau tại nhánh `expected == actual`; một phía hữu hạn và phía còn lại vô cực, hoặc hai vô cực trái dấu, bị từ chối.
4. `+0.0` và `-0.0` được xem là bằng nhau về **giá trị số học**. Nếu bài kiểm tra đòi phân biệt dấu của 0, cần so sánh bit.
5. Với hai giá trị hữu hạn cực lớn trái dấu, phép trừ có thể ra vô cực do overflow. Hàm sẽ từ chối, phù hợp với chính sách tolerance hữu hạn và `relTol < 1` ở đây.
6. Hàm không tự suy ra absTol/relTol; người sử dụng phải cung cấp chúng dựa trên bài toán.

Không viết một hàm “gần bằng” mà ngầm cho phép `NaN` hoặc vô cực đi qua điều kiện sai số chỉ vì phép toán IEEE 754 trả về kết quả đặc biệt.

## 5. Những trường hợp biên đặc biệt

### 5.1. Gần 0 và dấu âm 0

Tỷ lệ `|actual - expected| / |expected|` không xác định hữu ích khi expected bằng 0. Vì vậy sai số tuyệt đối quan trọng để so sánh kết quả dự kiến gần 0:

```java
nearlyEqual(0.0, 1e-13, 1e-12, 1e-9); // true
nearlyEqual(0.0, 1e-8, 1e-12, 1e-9);  // false
```

Trong Java, `+0.0 == -0.0` là `true`. Nhưng bit dấu của hai giá trị khác nhau, và một số phép toán cho kết quả khác: `1.0 / +0.0` là `+Infinity`, còn `1.0 / -0.0` là `-Infinity`.

Nếu dấu của số 0 **là một phần hợp đồng**, cần kiểm tra bit:

```java
boolean sameBits = Double.doubleToRawLongBits(0.0)
        == Double.doubleToRawLongBits(-0.0); // false
```

So sánh bit có thể cũng phân biệt các mẫu biểu diễn `NaN`; hãy chỉ dùng khi yêu cầu thực sự gắn với biểu diễn IEEE 754.

### 5.2. NaN

`Double.NaN` thể hiện “Not a Number”. Theo phép so sánh nguyên thủy của IEEE 754:

```java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.isNaN(Double.NaN));   // true
```

Nếu mục đích kiểm thử là phát hiện thuật toán **đáng lẽ phải ra số hữu hạn**, một kết quả `NaN` phải bị từ chối. Nếu thuật toán **được đặc tả phải trả NaN** cho một đầu vào không hợp lệ, hãy viết assertion về `Double.isNaN(actual)`. Đừng xem khoảng sai số là công cụ kiểm tra `NaN`.

### 5.3. Vô cực và tràn số thực

`Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` là các giá trị đặc biệt. Hai số cùng vô cực có thể so sánh `==` bằng nhau, nhưng vô cực trừ chính nó tạo `NaN`; vì thế công thức chỉ dùng `Math.abs(expected - actual)` không đủ bao quát.

Nếu thuật toán phải trả số hữu hạn, kiểm tra `Double.isFinite(actual)` trước khi so sánh. Nếu vô cực là kết quả hợp lệ được đặc tả, kiểm tra chính xác trường hợp đó, tách biệt với tolerance.

### 5.4. ULP: khoảng cách giữa các giá trị floating-point lân cận

`Math.ulp(x)` trả kích thước một *unit in the last place* tại `x` theo độ lớn và biểu diễn floating-point. Ví dụ:

```java
System.out.println(Math.ulp(1.0)); // 2.220446049250313E-16
```

Trong kiểm thử thuật toán số, đôi khi người ta quy định sai lệch theo số ULP (ví dụ kết quả chỉ cách tham chiếu vài giá trị `double` có thể biểu diễn). Điều này có thể hữu ích khi cần đánh giá đặc tính làm tròn của một thuật toán cụ thể.

Tuy nhiên, **một khoảng ULP cố định cũng không phải ngưỡng nghiệp vụ chung**. Khoảng cách ULP thay đổi theo độ lớn, cần cẩn trọng gần 0, tại miền subnormal, qua 0, với hai số trái dấu và khi một phía là `NaN` hoặc vô cực. Không nên tùy tiện dùng `Math.ulp(expected)` làm epsilon mặc định để kiểm thử mọi phép tính.

## 6. Ví dụ Java 17+ hoàn chỉnh và có kết quả xác định

Lưu tệp `NumericToleranceDemo.java`:

```java
import java.math.BigDecimal;

public class NumericToleranceDemo {
    static boolean nearlyEqual(
            double expected, double actual,
            double absTol, double relTol) {

        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }
        if (Double.isNaN(expected) || Double.isNaN(actual)) {
            return false;
        }
        if (expected == actual) {
            return true;
        }
        if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
            return false;
        }
        double difference = Math.abs(actual - expected);
        double scale = Math.max(Math.abs(expected), Math.abs(actual));
        return difference <= Math.max(absTol, relTol * scale);
    }

    static boolean withinDecimalTolerance(
            BigDecimal expected,
            BigDecimal actual,
            BigDecimal tolerance) {
        if (tolerance.signum() < 0) {
            throw new IllegalArgumentException("Negative tolerance");
        }
        return actual.subtract(expected).abs()
                .compareTo(tolerance) <= 0;
    }

    public static void main(String[] args) {
        double absTol = 1e-12;
        double relTol = 1e-9;

        System.out.println("exact double: " + ((0.1 + 0.2) == 0.3));
        System.out.println("near double: "
                + nearlyEqual(0.3, 0.1 + 0.2, absTol, relTol));
        System.out.println("near zero pass: "
                + nearlyEqual(0.0, 1e-13, absTol, relTol));
        System.out.println("near zero fail: "
                + nearlyEqual(0.0, 1e-8, absTol, relTol));
        System.out.println("large magnitude: "
                + nearlyEqual(1e9, 1e9 + 0.1, absTol, relTol));
        System.out.println("far values: "
                + nearlyEqual(1.0, 1.1, absTol, relTol));

        System.out.println("NaN near NaN: "
                + nearlyEqual(Double.NaN, Double.NaN, absTol, relTol));
        System.out.println("same +infinity: "
                + nearlyEqual(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, absTol, relTol));
        System.out.println("opposite infinities: "
                + nearlyEqual(Double.POSITIVE_INFINITY,
                        Double.NEGATIVE_INFINITY, absTol, relTol));
        System.out.println("signed zero near: "
                + nearlyEqual(0.0, -0.0, absTol, relTol));
        System.out.println("signed zero same bits: "
                + (Double.doubleToRawLongBits(0.0)
                   == Double.doubleToRawLongBits(-0.0)));

        BigDecimal exactA = new BigDecimal("1.00");
        BigDecimal exactB = new BigDecimal("1.000");
        System.out.println("BigDecimal equals: "
                + exactA.equals(exactB));
        System.out.println("BigDecimal numeric equal: "
                + (exactA.compareTo(exactB) == 0));
        System.out.println("BigDecimal within 0.01: "
                + withinDecimalTolerance(exactA,
                        new BigDecimal("1.009"),
                        new BigDecimal("0.01")));
        System.out.println("BigDecimal outside 0.01: "
                + withinDecimalTolerance(exactA,
                        new BigDecimal("1.011"),
                        new BigDecimal("0.01")));
    }
}
```

Biên dịch, chạy với Java 17 trở lên:

```bash
javac NumericToleranceDemo.java
java NumericToleranceDemo
```

Kết quả:

```text
exact double: false
near double: true
near zero pass: true
near zero fail: false
large magnitude: true
far values: false
NaN near NaN: false
same +infinity: true
opposite infinities: false
signed zero near: true
signed zero same bits: false
BigDecimal equals: false
BigDecimal numeric equal: true
BigDecimal within 0.01: true
BigDecimal outside 0.01: false
```

Điểm quan trọng trong chương trình:

- Phép so sánh `0.1 + 0.2 == 0.3` thất bại về **bằng nhau chính xác**, nhưng thành công với ngưỡng thử nghiệm đã khai báo.
- Cùng một ngưỡng kết hợp vẫn phải từ chối `0` so với `1e-8` hoặc `1.0` so với `1.1`. Một tolerance quá rộng sẽ không có giá trị phát hiện lỗi.
- `NaN` không được chấp nhận như “gần một số”; vô cực cần quy tắc riêng.
- Trong `BigDecimal`, bằng nhau về giá trị số học và bằng nhau về biểu diễn có thể khác nhau do scale. Phép so sánh với một **khoảng sai số thập phân chính xác** không cần chuyển sang `double`.

## 7. BigDecimal: không dùng epsilon như phản xạ mặc định

`BigDecimal` biểu diễn giá trị thập phân theo `unscaledValue × 10^(-scale)`, phù hợp khi cần kiểm soát chính xác số học thập phân. Với hai `BigDecimal`, trước tiên xác định yêu cầu:

| Nhu cầu | Cách kiểm tra |
|---|---|
| Cùng giá trị số học, không quan tâm scale | `a.compareTo(b) == 0` |
| Cùng giá trị số học **và** cùng scale | `a.equals(b)` |
| Cho phép độ lệch thập phân được quy định | `a.subtract(b).abs().compareTo(tolerance) <= 0` |
| Kết quả phải đạt scale/mode nghiệp vụ cụ thể | Chuẩn hóa/làm tròn theo chính sách được phê duyệt rồi kiểm tra giá trị và scale tương ứng |

Ví dụ:

```java
BigDecimal expected = new BigDecimal("10.00");
BigDecimal actual = new BigDecimal("10.005");

BigDecimal tolerance = new BigDecimal("0.01");

boolean within = actual.subtract(expected).abs()
        .compareTo(tolerance) <= 0; // true
```

Phương pháp này **không dùng `doubleValue()`**, nên không thêm sai số do chuyển sang nhị phân. Nhưng cho phép lệch 0,01 vẫn là một **quyết định kiểm thử/nghiệp vụ**, không phải thuộc tính mặc định của `BigDecimal`.

Ví dụ khác, nếu yêu cầu là “phải tính chính xác 10,00 theo scale 2”, việc chấp nhận `10.005` vì “không lệch quá 0,01” sẽ che giấu một kết quả sai. Khi kiểm thử tổng tiền, giao dịch hoặc tính thuế, phải lấy chính sách chính thức về độ chính xác, scale, thứ tự làm tròn và thời điểm làm tròn làm chuẩn.

### Không tự gán epsilon theo scale

`new BigDecimal("1.00")` có scale 2, nhưng điều đó không có nghĩa sai số tối đa cho phép là `0.01` hay `0.005`. Giá trị có scale 2 có thể đã được làm tròn, có thể được nhập nguyên văn, hoặc có thể chỉ là định dạng lưu trữ.

Tương tự, cơ sở dữ liệu `DECIMAL(p, s)` hoặc một API nhận `BigDecimal` **không tự cho biết** giá trị nào được chấp nhận sai lệch. Tolerance cần có nguồn từ đặc tả, phương pháp đo, phân tích sai số hoặc yêu cầu nghiệp vụ.

## 8. Kiểm thử bằng assertion: đừng để ngưỡng che giấu lỗi

Trong JUnit Jupiter, ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

// Ví dụ bên trong một @Test
assertEquals(0.3, 0.1 + 0.2, 1e-12);
```

Đây là ví dụ **phụ thuộc JUnit Jupiter** và không phải một chương trình Java độc lập chỉ với JDK. Tham số `delta` trong overload so sánh số thực là ngưỡng dung sai **tuyệt đối** cho sai lệch số học, có xử lý các giá trị đặc biệt theo hợp đồng của API. Nó không triển khai công thức **kết hợp tuyệt đối và tương đối** ở phần 4.

Nếu yêu cầu là tolerance hỗn hợp, có thể dùng helper riêng đã được kiểm thử:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

// Ví dụ bên trong một @Test
assertTrue(nearlyEqual(expected, actual, absTol, relTol));
```

Khi một assertion thất bại, chẩn đoán nên hiển thị **expected, actual, sai số tuyệt đối, ngưỡng được áp dụng và đơn vị** nếu có. Điều này giúp phân biệt lỗi logic, sai số tính toán chấp nhận được và trường hợp tolerance bị cấu hình không phù hợp.

Một số lưu ý:

- Không dùng `assertEquals(expected, actual, 0.0)` như thể nó tự động xử lý mọi sai số floating-point; khi yêu cầu chính xác, ghi rõ đó là chủ ý.
- Không đặt `delta` quá lớn chỉ để “bài test chuyển xanh”. Tolerance là một phần của **đặc tả**, không phải công cụ né lỗi.
- Không trộn lẫn kiểm tra xấp xỉ với so sánh kiểu nguyên hoặc các mã nhận dạng: ID, số lần lặp và chỉ số mảng thường đòi **bằng nhau chính xác**.
- Không mặc định cùng một tolerance phù hợp cho số giây, độ dài, phần trăm, tiền tệ hoặc xác suất. **Đơn vị và thang đo** quyết định ý nghĩa ngưỡng.

## 9. Chọn ngưỡng sai số dựa trên yêu cầu nào?

Độ dung sai nên xuất phát từ một hoặc nhiều căn cứ sau:

1. **Sai số cho phép trong hợp đồng nghiệp vụ hoặc tiêu chuẩn đo:** ví dụ giá trị đo có độ phân giải và sai số thiết bị đã được công bố.
2. **Phân tích sai số thuật toán:** số phép tính, độ ổn định số, mất mát do triệt tiêu khi trừ, độ điều kiện của bài toán và sai số làm tròn tích lũy.
3. **Phạm vi dữ liệu và đơn vị:** expected gần 0, rất lớn, dương/âm hay trải qua nhiều bậc độ lớn.
4. **Chuẩn tham chiếu và độ chính xác của expected:** kết quả “đúng” có phải là giá trị toán học chính xác, nghiệm gần đúng độ chính xác cao, hay số đo thực nghiệm cũng chứa sai số?
5. **Hành vi đặc biệt:** có chấp nhận `NaN`, `Infinity`, `-0.0` hoặc overflow/underflow hay không?
6. **Mục đích phép thử:** xác nhận một bất biến chính xác, đối chiếu thuật toán gần đúng, kiểm thử regression qua nền tảng, hay xác nhận sai số theo quy định.

**Phân biệt độ chính xác máy và sai số nghiệp vụ:** `Math.ulp(1.0)` là đặc tính số thực nhị phân gần 1, không phải mức sai số cho phép của một kết quả đo đạc hoặc của hệ thống kế toán. Một phép tính kém ổn định có thể tích lũy sai lệch lớn hơn nhiều ULP; ngược lại, một nghiệp vụ có thể cấm bất cứ lệch số nào dù mức lệch rất nhỏ.

Nếu không có hợp đồng sai số rõ ràng, kiểm thử nên ghi nhận khoảng sai số dự kiến và **xác minh với người sở hữu phép tính**, không gán hằng số mặc định thiếu căn cứ.

## 10. Những lỗi thường gặp

1. **Chọn một `epsilon = 1e-6` cho mọi số.** Ngưỡng đó có thể vô nghĩa khi đơn vị, miền giá trị hoặc yêu cầu thay đổi.
2. **Dùng duy nhất sai số tương đối gần 0.** Mẫu số bằng 0 hoặc rất nhỏ làm tỷ lệ không hữu ích. Thêm sai số tuyệt đối khi phù hợp.
3. **Dùng duy nhất sai số tuyệt đối cho miền nhiều bậc độ lớn.** Có thể từ chối một giá trị có sai số tương đối cực nhỏ hoặc chấp nhận sai lệch tương đối lớn với số nhỏ; chỉ kết luận theo yêu cầu.
4. **Xem mọi `NaN` là bằng nhau trong helper so sánh xấp xỉ.** Một hàm tính sai ra `NaN` có thể bị bỏ qua. Kiểm tra NaN riêng khi đó là kết quả được đặc tả.
5. **Bỏ qua infinity và số 0 âm.** Những giá trị này có ngữ nghĩa IEEE 754 đặc biệt; cần chính sách rõ ràng.
6. **Chuyển `BigDecimal` sang `double` để so sánh với epsilon.** Làm vậy bỏ mất lợi thế tính toán thập phân chính xác.
7. **Dùng `BigDecimal.equals()` khi chỉ cần cùng giá trị số học.** `1.0` và `1.00` không `equals()`, nhưng `compareTo()==0`.
8. **Dùng tolerance che phủ lỗi nghiệp vụ về làm tròn.** Một hóa đơn phải đúng 2 chữ số theo quy tắc đã duyệt không nên được chấp nhận chỉ vì số sai vẫn gần kết quả.
9. **Không thử giá trị ranh giới ngay quanh tolerance.** Cần kiểm tra trường hợp bằng ngưỡng, nhỏ hơn rất ít, lớn hơn rất ít, số âm và gần 0; hiểu rằng chính tolerance có thể không được biểu diễn thập phân chính xác trong `double`.
10. **Dựa vào việc một lần chạy trùng kết quả để kết luận thuật toán chính xác.** Các phép tính số có thể thay đổi theo đầu vào và thứ tự toán học; hãy kiểm tra nhiều miền đại diện và bất biến quan trọng.

## 11. Tự kiểm tra

**Câu 1.** Tại sao `0.1 + 0.2 == 0.3` có thể là `false` trong Java?  
**Đáp án:** `double` biểu diễn nhị phân hữu hạn; 0,1 và 0,2 không thể lưu chính xác, dẫn tới sai khác giữa kết quả cộng và biểu diễn gần đúng của 0,3.

**Câu 2.** Khi expected bằng 0, có nên chia sai số tuyệt đối cho `|expected|` để tính sai số tương đối không?  
**Đáp án:** Không; mẫu số bằng 0. Dùng một tiêu chí sai số tuyệt đối được xác định theo bài toán, hoặc chính sách phù hợp khác.

**Câu 3.** Với `absTol = 1e-12` và `relTol = 1e-9`, kiểm tra `expected = 0`, `actual = 1e-8` có qua không?  
**Đáp án:** Không; sai lệch `1e-8` vượt cả ngưỡng tuyệt đối `1e-12` và giới hạn tương đối dựa trên độ lớn của cặp giá trị.

**Câu 4.** Trong helper ở trên, hai giá trị `NaN` có được coi là gần bằng nhau không?  
**Đáp án:** Không. Nếu NaN là kết quả được kỳ vọng, dùng `Double.isNaN(actual)`.

**Câu 5.** `BigDecimal("1.0")` và `BigDecimal("1.00")` nên kiểm tra thế nào nếu chỉ cần cùng giá trị số học?  
**Đáp án:** `a.compareTo(b) == 0`. `equals()` còn xét cả scale.

**Câu 6.** Khi kiểm thử giá trị tiền tệ phải chính xác đến hai chữ số theo quy tắc đã phê duyệt, có nên dùng một epsilon tùy ý không?  
**Đáp án:** Không. Tính toán và làm tròn theo chính sách chính thức rồi kiểm tra giá trị (và scale nếu hợp đồng yêu cầu) bằng `BigDecimal`.

**Câu 7.** `Math.ulp(1.0)` có phải “epsilon chuẩn cho mọi thuật toán” không?  
**Đáp án:** Không; ULP thay đổi theo miền giá trị và không phản ánh mặc định sai số đo, sai số thuật toán hay mức lệch mà nghiệp vụ chấp nhận.

**Ghi nhớ:** Hãy so sánh **chính xác** khi hợp đồng yêu cầu chính xác; dùng **sai số tuyệt đối** theo đơn vị khi sai lệch cố định quan trọng; dùng **sai số tương đối** khi sai lệch theo độ lớn quan trọng; dùng **kết hợp có kiểm soát** cho miền rộng và gần 0. Mọi ngưỡng phải có lý do kiểm thử, không được suy ra tùy tiện chỉ từ kiểu số.
