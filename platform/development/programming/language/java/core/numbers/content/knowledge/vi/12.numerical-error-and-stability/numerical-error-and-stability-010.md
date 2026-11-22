# Kiểm chứng thuật toán bằng dữ liệu biên và kết quả tham chiếu trong Java

## 1. Vì sao kết quả “trông hợp lý” chưa chứng minh thuật toán đúng?

Với thuật toán số học, một vài kết quả đúng trên dữ liệu thông thường không đủ chứng minh thuật toán đúng. Lỗi có thể chỉ xuất hiện khi **đầu vào chạm giới hạn kiểu**, hai số chênh lệch độ lớn rất lớn, dữ liệu có dấu âm, xuất hiện `NaN`/vô cực hoặc nhiều phép tính làm tròn liên tiếp.

Ví dụ:

```java
int a = 50_000;
int b = 50_000;

long wrong = a * b;          // -1794967296: phép nhân int tràn trước khi gán.
long right = (long) a * b;   // 2500000000: phép nhân long.
```

Một bài test chỉ dùng `a = 2, b = 3` không thể phát hiện lỗi trên. Thuật toán cộng số thực có thể tương tự: nhiều trường hợp nhỏ đúng, nhưng `1e16 + 1.0` ở kiểu `double` được làm tròn về `1e16`.

Để đánh giá tin cậy, cần kết hợp **hai nguồn chứng cứ**:

1. **Dữ liệu biên (*boundary and adversarial cases*):** cố tình tạo tình huống khó, sát giới hạn hay dễ bộc lộ lỗi.
2. **Kết quả tham chiếu (*reference result, test oracle*):** xác định kết quả kỳ vọng bằng một cách đủ độc lập, đủ chính xác và phù hợp với hợp đồng của thuật toán.

Bài này tập trung vào kiểm chứng các phép tính số trong Java Core: số nguyên cố định, số thực `float`/`double`, độ ổn định số học và chiến lược đối chiếu. Mục tiêu không chỉ viết `assert`, mà còn biết **đang khẳng định điều gì, căn cứ từ đâu và sai số nào được chấp nhận**.

## 2. Trước tiên phải định nghĩa “đúng” là gì

Một thuật toán có thể đúng theo nhiều hợp đồng khác nhau:

- **Số nguyên toán học:** cần kết quả chính xác không giới hạn về mặt ý nghĩa, có thể dùng `BigInteger` làm tham chiếu.
- **Số nguyên có độ rộng cố định:** chương trình có thể chủ đích dùng modulo `2^32`/`2^64`, hoặc phải báo lỗi khi tràn. Cần xác định kỳ vọng, không mặc định rằng mọi wraparound đều là bug.
- **Số thực IEEE 754:** chấp nhận sai số làm tròn theo một mô hình đã định nghĩa. Kiểm chứng phải xét độ lớn, độ chính xác và giá trị đặc biệt.
- **Thập phân chính xác:** ví dụ số tiền hoặc số đo được quy định chính xác đến một số chữ số, có thể cần `BigDecimal` và quy tắc `RoundingMode`.
- **Thuật toán xấp xỉ:** kết quả được chấp nhận nếu thỏa sai số tuyệt đối/tương đối, khoảng tin cậy hoặc giới hạn sai số riêng của miền ứng dụng.

Một phép toán `int` cho kết quả âm do tràn có thể **đúng theo số học modulo** nhưng **sai trong nghiệp vụ tính doanh thu**. Một kết quả `double` lệch vài ULP có thể **chấp nhận được** trong bài toán mô phỏng nhưng **không đạt yêu cầu** nếu hợp đồng phải chính xác đến đơn vị nhỏ nhất.

Vì vậy, trước khi tạo testcase, ghi rõ:

| Phần hợp đồng | Câu hỏi cần trả lời |
| --- | --- |
| Miền đầu vào | Cho phép số âm, zero, `NaN`, vô cực, giá trị ngoài miền không? |
| Miền đầu ra | Kết quả có phải hữu hạn, không âm, trong một khoảng hay đúng kiểu không? |
| Tràn và ngoại lệ | Tràn cần báo lỗi, bão hòa (*saturate*) hay modulo? Chia cho 0 xử lý ra sao? |
| Độ chính xác | Cần chính xác tuyệt đối, làm tròn đến chữ số nào hay giới hạn sai số nào? |
| Tính ổn định | Sai số có tăng quá lớn khi thay đổi nhẹ dữ liệu hoặc thứ tự tính không? |
| Điều kiện tiên quyết | Mảng rỗng, `null`, dữ liệu chưa sắp xếp có được phép không? |

**Test oracle phải xuất phát từ hợp đồng**, không phải từ kết quả đang được tạo ra bởi chính hàm cần kiểm thử.

## 3. Thiết kế bộ dữ liệu biên cho các phép tính số

Không chỉ kiểm tra `0` và `MAX_VALUE`. Với thuật toán số, cần kiểm tra **giá trị ngay bên dưới, tại và ngay bên trên các ngưỡng** cùng những tổ hợp dễ gây mất ổn định.

| Nhóm dữ liệu | Ví dụ đầu vào | Lỗi/rủi ro muốn phát hiện |
| --- | --- | --- |
| Zero và dấu | `0`, `-1`, `1`, `+0.0`, `-0.0` | Chia 0, quy tắc dấu, xử lý signed zero |
| Cận số nguyên | `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, giá trị sát cận | Tràn cộng/nhân, `Math.abs(MIN_VALUE)` |
| Cận `long` | `Long.MIN_VALUE`, `Long.MAX_VALUE` | Tràn 64 bit và cast hẹp |
| Giới hạn chính xác `float` | `2^24` và số nguyên kề | Mất khả năng phân biệt bước `1` |
| Giới hạn chính xác `double` | `2^53` và số nguyên kề | Làm tròn số nguyên lớn |
| Khác biệt độ lớn | `1e16 + 1.0` | Số hạng nhỏ bị nuốt |
| Triệt tiêu | `(1e16 + 1.0) - 1e16` | Mất thông tin trước khi trừ |
| Cực trị số thực | `Double.MAX_VALUE`, `Double.MIN_NORMAL`, `Double.MIN_VALUE` | Overflow, subnormal, underflow |
| Giá trị đặc biệt | `Double.NaN`, `Double.POSITIVE_INFINITY`, `-0.0` | So sánh, kiểm tra finite, hợp đồng giá trị |
| Dữ liệu tổ hợp | Mảng rỗng, một phần tử, nhiều số cùng dấu, số khác dấu xen kẽ | Sai chỉ số, trung bình sai, độ ổn định của phép tổng |
| Đầu vào không hợp lệ | Mẫu số 0, độ dài âm, số vượt miền | Ngoại lệ đúng loại, không nuốt lỗi |

Đối với mỗi ranh giới `B`, một mẫu cơ bản là thử **`B-1`, `B`, `B+1`**, nhưng phải tạo dữ liệu bằng kiểu **đủ rộng**; đừng để chính code tạo test bị tràn trước khi test chạy:

```java
long below = (long) Integer.MAX_VALUE - 1;
long at = Integer.MAX_VALUE;
long above = (long) Integer.MAX_VALUE + 1;
```

Đối với số thực, `x - 1`/`x + 1` không phải lúc nào cũng là hai giá trị kề nhau. Dùng `Math.nextDown(x)`, `Math.nextUp(x)`, `Math.ulp(x)` khi muốn kiểm tra ranh giới theo độ phân giải của `double`.

### Các testcase đối nghịch đặc biệt hữu ích

- `Integer.MAX_VALUE + 1` và `Long.MAX_VALUE + 1L`: quan sát tràn số nguyên.
- `Integer.MIN_VALUE / -1`: trường hợp chia nguyên đặc biệt; ở kiểu `int` kết quả là `Integer.MIN_VALUE` do thương toán học không nằm trong miền.
- `0 / 0` theo số nguyên: phải ném `ArithmeticException`; `0.0 / 0.0` theo số thực: là `NaN`.
- `1e16 + 1.0` và `1e16 + 2.0`: phân biệt thay đổi bị làm tròn và thay đổi giữ được.
- `Double.MIN_VALUE / 2.0`: phép toán nhỏ hơn số `double` dương nhỏ nhất, làm tròn thành `0.0`.
- `Double.MAX_VALUE * 2.0`: kết quả là `Infinity`.
- Hai số thực sát nhau quanh mốc cần so sánh: dùng `Math.nextUp` thay vì cộng một epsilon bất kỳ.

Đừng coi số lượng trường hợp càng nhiều là đủ. Một bộ dữ liệu nhỏ nhưng có lý do chọn từng trường hợp thường hiệu quả hơn hàng nghìn đầu vào ngẫu nhiên chỉ quanh giá trị trung bình.

## 4. Xây dựng kết quả tham chiếu đáng tin cậy

**Kết quả tham chiếu** phải được tạo bằng phương pháp có độ tin cậy cao hơn, đủ khác biệt so với code đang kiểm thử để không vô tình lặp lại cùng một lỗi.

### 4.1. `BigInteger` làm oracle cho số nguyên toán học

Nếu thuật toán tính toán các giá trị nguyên có thể vượt 32/64 bit, dùng `java.math.BigInteger`:

```java
import java.math.BigInteger;

int a = 50_000;
int b = 50_000;

BigInteger expected = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));

System.out.println(expected); // 2500000000
```

Không làm phép nhân nguyên thủy **trước khi** đưa kết quả vào `BigInteger`:

```java
// Sai oracle: phép nhân int có thể tràn trước.
BigInteger wrongReference = BigInteger.valueOf(a * b);
```

Tương tự, muốn kiểm tra phép cộng `long` ở biên, dùng `BigInteger.valueOf(x).add(BigInteger.valueOf(y))`, không dùng `BigInteger.valueOf(x + y)`. Nếu hợp đồng cho phép modulo 32/64 bit, kết quả BigInteger phải được đối chiếu sau khi áp dụng **chính phép quy đổi modulo** mà hợp đồng yêu cầu.

Với hợp đồng “không được tràn”, thay vì so sánh kết quả đã wraparound, hãy xác nhận `Math.addExact`, `Math.multiplyExact` hoặc logic kiểm tra biên phát ra `ArithmeticException` đúng trường hợp.

### 4.2. `BigDecimal` làm oracle cho đầu vào thập phân

Giả sử hợp đồng đầu vào là **mười lần giá trị thập phân đúng `0.1`**:

```java
import java.math.BigDecimal;

BigDecimal reference = new BigDecimal("0.1")
        .multiply(BigDecimal.TEN);

System.out.println(reference.toPlainString()); // 1.0
```

Điểm quan trọng là **định nghĩa đầu vào**. Có hai cách làm tham chiếu khác nhau:

1. **Tham chiếu thập phân ý định:** `new BigDecimal("0.1")` biểu diễn đúng phân số thập phân `1/10`.
2. **Tham chiếu đúng mẫu bit `double` đã nhận:** `new BigDecimal(0.1)` biểu diễn chính xác giá trị **nhị phân xấp xỉ** đang lưu ở `double`. Nó khác `1/10` về mặt toán học.

Trong Java, `BigDecimal.valueOf(0.1)` dùng cách chuyển `double` thành chuỗi thập phân ngắn, thường cho `0.1`. Nhưng khi mục đích là tính **giá trị chính xác của mẫu bit `double`**, `new BigDecimal(x)` mới là lựa chọn phù hợp. Phải chọn oracle theo loại đầu vào thực tế, không dùng một cách xây dựng `BigDecimal` cho mọi bài toán.

Đối với các phép chia thập phân có khai triển vô hạn như `1/3`, hãy chọn `MathContext` hoặc `RoundingMode` và scale theo hợp đồng; nếu không, `BigDecimal.divide` có thể ném `ArithmeticException`. Oracle không được “chính xác vô hạn” nếu bài toán thực sự yêu cầu làm tròn đến hai chữ số: khi đó quy tắc làm tròn **là một phần kết quả mong đợi**.

### 4.3. Dùng một cài đặt độc lập hoặc bảng kết quả đã kiểm chứng

Với thuật toán có công thức phức tạp, tham chiếu có thể là:

- Một cách triển khai đơn giản, rõ ràng hơn nhưng chậm hơn (ví dụ `O(n^2)` cho kích thước test nhỏ).
- Giá trị tính ở độ chính xác cao hơn với mô hình số phù hợp.
- Bộ trường hợp chuẩn có giá trị đã được kiểm tra thủ công hoặc từ tài liệu đáng tin.
- Một phép tính độc lập từ thư viện/thuật toán khác, với **hợp đồng, miền giá trị và quy tắc làm tròn tương thích**.

**Không dùng chính kết quả của hàm đang test làm “expected”** rồi kiểm tra nó bằng một phép biến đổi tương đương. Hai triển khai chia sẻ cùng phép tính lỗi có thể cùng tạo một kết quả sai; tính độc lập của oracle là phần quan trọng của kiểm chứng.

## 5. So sánh actual với expected: kiểm tra chính xác hay gần đúng?

### Với số nguyên, kiểu liệt kê hoặc trạng thái

Nếu hợp đồng yêu cầu **chính xác**, so sánh trực tiếp:

```java
long actual = 2_500_000_000L;
long expected = 2_500_000_000L;

if (actual != expected) {
    throw new AssertionError("Wrong integer result");
}
```

Đối với `BigInteger`/`BigDecimal`, dùng API so sánh phù hợp:

- `BigInteger.equals` kiểm tra bằng nhau theo giá trị số nguyên.
- `BigDecimal.compareTo` so sánh giá trị toán học; `BigDecimal.equals` còn yêu cầu **cùng scale**. Ví dụ `1.0` và `1.00` có `compareTo == 0` nhưng `equals == false`.

### Với `float`/`double`, sai số tuyệt đối và tương đối

So sánh `actual == expected` có thể không phù hợp nếu kết quả trải qua những bước làm tròn khác nhau. Một chính sách thường gặp là:

```text
|actual - expected| <= max(absTol, relTol * max(|actual|, |expected|))
```

Ở đây:

- `absTol` là **ngưỡng sai số tuyệt đối**, hữu ích gần zero.
- `relTol` là **ngưỡng sai số tương đối**, hữu ích khi độ lớn thay đổi.
- Cả hai ngưỡng phải bắt nguồn từ yêu cầu mô hình, đơn vị đo và độ chính xác cần đạt.

Ví dụ Java:

```java
static boolean nearlyEqual(double actual, double expected,
                           double absTol, double relTol) {
    if (!(Double.isFinite(actual) && Double.isFinite(expected))) {
        return false;
    }
    if (!(Double.isFinite(absTol) && Double.isFinite(relTol))
            || absTol < 0.0 || relTol < 0.0) {
        throw new IllegalArgumentException("Invalid tolerances");
    }

    double diff = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(actual), Math.abs(expected));
    return diff <= Math.max(absTol, relTol * scale);
}
```

Đây là **hàm minh họa cho phép so sánh hữu hạn trong miền số bình thường**, không phải bộ so sánh tổng quát hoàn hảo. Phép trừ `actual - expected` có thể tràn thành vô cực với hai giá trị hữu hạn trái dấu cực lớn; phép nhân `relTol * scale` cũng có thể gặp các tình huống đặc biệt. Với tính toán đòi hỏi độ tin cậy cao, hãy chọn và kiểm chứng cách tính sai số tương ứng miền dữ liệu.

**Không tự động dùng `1e-6` hoặc `1e-12` cho mọi thuật toán**. Ngưỡng quá chặt có thể đánh rớt kết quả hợp lệ; ngưỡng quá lỏng có thể bỏ sót lỗi nghiêm trọng. Gắn ngưỡng với độ phân giải đo, độ lớn kết quả, số phép tính và sai số mà bài toán cho phép.

### NaN, vô cực và signed zero cần testcase riêng

```java
System.out.println(Double.isNaN(0.0 / 0.0));         // true
System.out.println(Double.isInfinite(1.0 / 0.0));    // true
System.out.println(+0.0 == -0.0);                   // true
System.out.println(Double.compare(+0.0, -0.0) == 0); // false
```

- `NaN` không bằng chính nó qua toán tử nguyên thủy `==`, nhưng `Double.equals` xem các NaN cùng kiểu bằng nhau. Nếu hợp đồng **cấm NaN**, hãy kiểm tra `Double.isFinite` thay vì so sánh gần đúng.
- `Infinity` có thể là kết quả đúng của phép chia số thực cho zero theo IEEE 754, hoặc là dấu hiệu đầu vào/lỗi số học không chấp nhận được theo nghiệp vụ.
- `+0.0` và `-0.0` bằng nhau theo `==` nhưng khác bit dấu. Nếu dấu zero là một phần hợp đồng (ví dụ quan sát qua phép nghịch đảo), kiểm tra `Double.doubleToRawLongBits` hoặc `Double.compare` có chủ đích.

Trong kiểm thử, không được “chữa” `NaN` bằng cách đặt `tolerance` lớn: phải định nghĩa nó là hợp lệ hay lỗi riêng biệt.

## 6. Kiểm thử thuộc tính và quan hệ biến đổi (*property/metamorphic testing*)

Không phải phép tính nào cũng có oracle độc lập dễ xây dựng. Có thể kiểm tra những **bất biến đã chứng minh được trong miền hợp lệ**, thay vì chỉ đối chiếu một con số mẫu.

Ví dụ cho số nguyên và mảng:

- Nếu một hàm đếm số phần tử, `count(empty) == 0` và thêm một phần tử tăng kết quả đúng `1`, miễn không vượt miền kiểu.
- Nếu thuật toán tìm giá trị nhỏ nhất của tập không rỗng, kết quả phải là một phần tử trong tập và không lớn hơn bất kỳ phần tử nào.
- Nếu một phép mã hóa rồi giải mã được thiết kế không mất dữ liệu, kiểm tra `decode(encode(x)).equals(x)` cho mọi `x` hợp lệ.
- Đối với thuật toán tổng, nếu **tính theo số nguyên chính xác không tràn**, đổi thứ tự phần tử không làm thay đổi tổng.
- Với thuật toán số thực, việc đổi thứ tự cộng có thể làm thay đổi kết quả vì phép cộng dấu phẩy động **không kết hợp**; chỉ kiểm tra một bất biến gần đúng khi đã xác lập mức sai số hợp lý.

**Không áp dụng bất biến toán học lý tưởng một cách máy móc cho số thực máy.** Ví dụ `(a+b)+c == a+(b+c)` không phải một thuộc tính đúng chung của phép cộng `double`. `x - x == 0` cũng cần điều kiện `x` hữu hạn; với `Infinity` thì phép trừ cho `NaN`.

Một số quan hệ biến đổi hữu ích khi đã chứng minh miền áp dụng:

1. **Thêm zero:** `sum(values plus 0)` không nên thay đổi giá trị toán học; nhưng với dữ liệu có signed zero, cách biểu diễn dấu có thể thay đổi theo thứ tự/cách cộng.
2. **Đối chiếu công thức độc lập:** với `long` không tràn và `divisor != 0` (trừ trường hợp đặc biệt `MIN_VALUE / -1` khi xét theo số học toán học), quan hệ `dividend = divisor * quotient + remainder` giúp đối chiếu chia và lấy dư.
3. **Kiểm tra miền kết quả:** tỷ lệ xác suất hợp lệ phải nằm trong `0..1` nếu hợp đồng quy định; tuy nhiên giá trị dấu phẩy động sát biên có thể cần ngưỡng hoặc chiến lược chặn được đặc tả.
4. **Kiểm tra tính đơn điệu:** một hàm được chứng minh tăng theo đầu vào trong miền xác định không được giảm bất thường, trừ trường hợp độ chính xác hoặc overflow mà hợp đồng xử lý riêng.

Các bất biến tốt phải có **điều kiện tiên quyết rõ ràng**. Test không đạt có thể chỉ ra lỗi thuật toán, nhưng cũng có thể chỉ ra rằng bất biến bạn viết không đúng trong mô hình số học thực tế.

## 7. Kiểm thử độ ổn định số học: điều kiện và thuật toán

Một thuật toán có thể đúng về công thức toán học nhưng **không ổn định về cách tính** trong dấu phẩy động.

Ví dụ tính `a + b + c` với các số rất khác độ lớn:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Cả ba toán hạng đều là giá trị `double` hợp lệ. Sự khác nhau đến từ **làm tròn các biểu thức trung gian**. Trước khi tối ưu hoặc thay đổi thứ tự phép cộng, kiểm tra:

- Thứ tự tính có làm thay đổi kết quả vượt mức sai số được chấp nhận không?
- Có số lớn trái dấu dễ triệt tiêu và làm lộ sai số tương đối không?
- Có nhiều số hạng nhỏ bị “nuốt” khi cộng vào tổng quá lớn không?
- Bài toán có điều kiện kém (*ill-conditioned*), khiến nhiễu rất nhỏ ở input dẫn tới thay đổi lớn ở output, dù thuật toán đã ổn định hay không?

**Conditioning** mô tả độ nhạy của **bài toán toán học** với biến đổi đầu vào. **Numerical stability** mô tả thuật toán triển khai có khuếch đại sai số tính toán quá mức hay không. Hai khái niệm liên quan nhưng không đồng nghĩa: nếu bản thân bài toán rất nhạy, một thuật toán tốt vẫn khó cho kết quả tuyệt đối chính xác với dữ liệu đầu vào bị nhiễu.

Ví dụ cụ thể của tình huống “số nhỏ bị nuốt”:

```java
double naive = 1e16;
for (int i = 0; i < 10; i++) {
    naive += 1.0;
}
System.out.println(naive - 1e16); // 0.0
```

Tổng toán học đáng lẽ tăng `10.0`. Các cách thay thế như **cộng nhóm những số hạng nhỏ trước**, pairwise summation, Kahan/Neumaier compensated summation có thể giảm sai số cho nhiều bộ dữ liệu, nhưng không bảo đảm kết quả tuyệt đối chính xác trong mọi trường hợp.

Cần thiết kế testcase riêng để **chứng minh tính hữu ích của một kỹ thuật ổn định** đối với dữ liệu đặc trưng, sau đó đối chiếu với oracle có độ chính xác cao hơn.

## 8. Test theo ranh giới, phân hoạch tương đương và dữ liệu ngẫu nhiên có tái lập

Một bộ test có giá trị thường kết hợp ba lớp:

### Dữ liệu biên có chủ đích

Dùng một bảng nhỏ ghi rõ input, oracle và lý do:

| ID | Input | Kết quả kỳ vọng | Mục đích |
| --- | --- | --- | --- |
| INT-01 | `Integer.MAX_VALUE + 1` theo phép cộng `int` | `Integer.MIN_VALUE` nếu hợp đồng wraparound | Kiểm tra dấu/tràn |
| INT-02 | `Math.addExact(Integer.MAX_VALUE, 1)` | `ArithmeticException` | Kiểm tra báo tràn |
| DEC-01 | Mười giá trị thập phân `"0.1"` | `BigDecimal("1.0")` | Oracle thập phân chính xác |
| FP-01 | `1e16 + 1.0` | Cùng mẫu `double` với `1e16` | Độ phân giải/ULP |
| FP-02 | `Double.MIN_VALUE / 2.0` | `0.0` | Underflow |
| FP-03 | `Double.MAX_VALUE * 2.0` | `+Infinity` | Overflow số thực |
| FP-04 | `0.0 / 0.0` | `NaN` | Giá trị đặc biệt |
| FP-05 | So sánh `+0.0` với `-0.0` | `==` cho true, so bit cho false | Signed zero |

### Phân hoạch tương đương

Chia miền đầu vào thành nhóm có ý nghĩa: số âm/dương, zero, khoảng nhỏ/lớn, hữu hạn/không hữu hạn, có/không có nguy cơ tràn, dữ liệu đúng/sai miền. Trong mỗi nhóm lấy một số đại diện, sau đó bổ sung các giá trị sát biên. Việc phân hoạch giúp tránh chỉ test các số dương nhỏ dễ tính.

### Randomized/property-based testing

Sinh thêm dữ liệu có **seed cố định** để tái lập:

```java
java.util.Random random = new java.util.Random(2026L);
for (int i = 0; i < 1_000; i++) {
    int x = random.nextInt();
    int y = random.nextInt();
    // Đối chiếu thuật toán bằng oracle độc lập phù hợp.
}
```

Nếu một lần kiểm thử ngẫu nhiên thất bại, lưu **seed, input chính xác, thứ tự sinh, môi trường và thông tin lỗi** để tái tạo. Đừng chỉ lưu “1000 testcase đều pass”. Ngoài random đều trên một miền, nên phát sinh có chủ đích các số biên vì xác suất ngẫu nhiên “trúng” giá trị như `Integer.MIN_VALUE` hoặc đúng ranh giới ULP rất nhỏ.

Với test đặc biệt của `double`, có thể sinh các mẫu bit bằng `Double.longBitsToDouble(random.nextLong())`, nhưng cần phân nhóm đầu vào hữu hạn/`NaN`/vô cực và xử lý theo hợp đồng thay vì ép tất cả vào một phép so sánh xấp xỉ.

## 9. Những lỗi ngay trong code kiểm thử

**Kiểm thử cũng có thể sai.** Những bẫy phổ biến:

1. **Oracle bị tràn cùng kiểu:** `BigInteger.valueOf(a * b)` nhận kết quả `int` đã tràn. Chuyển từng toán hạng trước khi nhân.
2. **Oracle cùng thuật toán với code test:** nếu cùng sai công thức, kết quả trùng nhau không phát hiện được bug.
3. **So sánh `double` bằng `==` ở mọi trường hợp:** lỗi làm tròn vô hại bị coi là thất bại; ngược lại, phép so sánh gần đúng quá rộng có thể che bug.
4. **Chỉ test dữ liệu ngẫu nhiên bình thường:** bỏ sót ngưỡng `MAX_VALUE`, ranh giới bit chính xác, zero và giá trị đặc biệt.
5. **Không xét NaN:** trong so sánh điều kiện, `NaN` có thể khiến cả `>`, `<` và `==` đều false, làm đoạn assert thủ công bị lọt điều kiện.
6. **Nhầm `Double.MIN_VALUE` với số âm nhỏ nhất:** nó là **số dương subnormal nhỏ nhất lớn hơn 0**, không phải giá trị âm lớn về độ lớn; số âm có trị tuyệt đối lớn nhất là `-Double.MAX_VALUE`.
7. **Đổi `double` đã lỗi sang `BigDecimal` rồi kỳ vọng sửa dữ liệu:** một khi làm tròn/mất thông tin đã xảy ra, phép chuyển kiểu không khôi phục nó.
8. **Dùng một epsilon cho mọi quy mô:** mất cân đối giữa kết quả gần zero và kết quả rất lớn.
9. **Không kiểm thử ngoại lệ:** đối với phép chia cho 0 hoặc overflow được thiết kế để báo lỗi, chính loại ngoại lệ là expected result.
10. **Dựa vào thời gian chạy hoặc thứ tự lặp collection không được đảm bảo:** các yếu tố này không nên là oracle cho giá trị số học nếu hợp đồng không quy định.
11. **Chỉ test kết quả cuối mà bỏ qua bất biến:** thuật toán có thể cho đúng một số đầu vào nhưng vi phạm miền kết quả hoặc tính đơn điệu.
12. **Sử dụng `assert` Java nhưng không bật nó khi chạy:** câu lệnh `assert` bị tắt theo mặc định trong nhiều môi trường; cần `java -ea` hoặc một framework kiểm thử phù hợp. `throw new AssertionError(...)` không phụ thuộc cờ `-ea`.

## 10. Ví dụ Java 17+ chạy độc lập, có oracle và dữ liệu biên

Tạo tệp **`NumericalBoundaryReferenceDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumericalBoundaryReferenceDemo {
    static boolean nearlyEqual(double actual, double expected,
                               double absTol, double relTol) {
        if (!Double.isFinite(actual) || !Double.isFinite(expected)) {
            return false;
        }
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0.0 || relTol < 0.0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }

        double diff = Math.abs(actual - expected);
        double scale = Math.max(Math.abs(actual), Math.abs(expected));
        return diff <= Math.max(absTol, relTol * scale);
    }

    public static void main(String[] args) {
        double sum = 0.0;
        for (int i = 0; i < 10; i++) {
            sum += 0.1;
        }

        BigDecimal decimalReference =
                new BigDecimal("0.1").multiply(BigDecimal.TEN);

        System.out.println("double sum = " + sum);
        System.out.println("decimal reference = "
                + decimalReference.toPlainString());
        System.out.println("strict comparison = "
                + (sum == decimalReference.doubleValue()));
        System.out.println("tolerant comparison = "
                + nearlyEqual(sum, decimalReference.doubleValue(),
                              1e-12, 1e-12));

        int max = Integer.MAX_VALUE;
        System.out.println("int wrap = "
                + (max + 1 == Integer.MIN_VALUE));
        BigInteger exactInteger = BigInteger.valueOf(max)
                .add(BigInteger.ONE);
        System.out.println("BigInteger reference = " + exactInteger);

        try {
            Math.addExact(max, 1);
            System.out.println("unexpected: no overflow");
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow detected");
        }

        double huge = 1e16;
        System.out.println("small increment lost = "
                + (huge + 1.0 == huge));
        System.out.println("ULP at 1e16 = " + Math.ulp(huge));
        System.out.println("BigDecimal exact increment = "
                + new BigDecimal("10000000000000000")
                    .add(BigDecimal.ONE).toPlainString());

        System.out.println("underflow to zero = "
                + (Double.MIN_VALUE / 2.0 == 0.0));
        System.out.println("overflow to infinity = "
                + Double.isInfinite(Double.MAX_VALUE * 2.0));
        System.out.println("NaN detected = "
                + Double.isNaN(0.0 / 0.0));
        System.out.println("signed zero primitive equal = "
                + (+0.0 == -0.0));
        System.out.println("signed zero raw bits equal = "
                + (Double.doubleToRawLongBits(+0.0)
                == Double.doubleToRawLongBits(-0.0)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac NumericalBoundaryReferenceDemo.java
java NumericalBoundaryReferenceDemo
```

Kết quả dự kiến:

```text
double sum = 0.9999999999999999
decimal reference = 1.0
strict comparison = false
tolerant comparison = true
int wrap = true
BigInteger reference = 2147483648
checked overflow detected
small increment lost = true
ULP at 1e16 = 2.0
BigDecimal exact increment = 10000000000000001
underflow to zero = true
overflow to infinity = true
NaN detected = true
signed zero primitive equal = true
signed zero raw bits equal = false
```

Các nhóm testcase minh họa **những hợp đồng khác nhau**: `BigInteger` và `BigDecimal` làm tham chiếu chính xác, `Math.addExact` xác nhận hành vi báo tràn, kiểm tra gần đúng cho phép cộng `double`, và kiểm tra riêng các giá trị đặc biệt.

**Lưu ý về kiểm chứng:** đầu ra trên được trình bày để đối chiếu có chủ đích. Trong dự án thật, nên chuyển các trường hợp thành các phép assert có tên, chạy tự động theo CI và báo rõ input/expected/actual mỗi khi sai. Khi thay đổi thuật toán để cải thiện ổn định số học, giữ lại các trường hợp biên làm **regression tests** để ngăn lỗi quay lại.

## 11. Checklist kiểm chứng trước khi chấp nhận một thuật toán số

1. **Hợp đồng:** viết rõ miền đầu vào, cách làm tròn, kiểu dữ liệu, ngoại lệ và sai số cho phép.
2. **Oracle:** chọn giá trị tham chiếu độc lập và đúng mô hình đầu vào; tránh overflow trong quá trình tạo expected.
3. **Miền biên:** có zero, giá trị âm, cực trị kiểu, ngay quanh ngưỡng và các tổ hợp lớn–nhỏ/trái dấu.
4. **Số thực đặc biệt:** quyết định hành vi với `NaN`, vô cực, signed zero, subnormal, overflow và underflow.
5. **Cách so sánh:** dùng equality chính xác khi cần; dùng ngưỡng tuyệt đối/tương đối/ULP có căn cứ khi chấp nhận sai số.
6. **Tính ổn định:** test những dữ liệu dễ gây triệt tiêu, mất số hạng nhỏ, tích lũy sai số hoặc độ nhạy cao.
7. **Thuộc tính:** kiểm tra bất biến và quan hệ biến đổi đúng trong **miền thực thi Java**, không ngầm giả định mọi định luật đại số số thực vẫn đúng.
8. **Tái lập:** ghi seed, input và môi trường khi test ngẫu nhiên; lưu regression cases sau khi sửa lỗi.
9. **Tự động hóa:** dùng JUnit hoặc cơ chế kiểm tra rõ ràng; chạy lại cùng bộ test trong pipeline khi chỉnh code.
10. **Giải thích lỗi:** mỗi lần test thất bại nên cho biết sai lệch giá trị, ngưỡng, quy tắc và ý nghĩa nghiệp vụ, không chỉ báo “expected != actual”.

**Kết luận:** Kiểm chứng thuật toán số không thể chỉ dựa vào vài ví dụ “đẹp”. Hãy phối hợp **dữ liệu biên được chọn có chủ đích**, **kết quả tham chiếu đủ độc lập/chính xác** và **quy tắc so sánh tương ứng với hợp đồng**. Trong Java, `BigInteger`/`BigDecimal`, `Math.*Exact`, `Math.ulp` và các phép kiểm tra `isFinite`/`isNaN` giúp phát hiện những lỗi chỉ xuất hiện tại ranh giới độ rộng kiểu và độ chính xác dấu phẩy động.

**Tài liệu tham khảo:** [Java Language Specification §4.2 — Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2), [JLS §15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17), [Math API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html), [BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html), [BigInteger API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html).
