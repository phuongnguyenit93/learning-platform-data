# Không thay đổi quy tắc chính xác chỉ để rút ngắn thời gian chạy

## 1. Vấn đề cốt lõi

Một phép tính số trong Java có thể chậm vì kiểu dữ liệu, số lần cấp phát đối tượng, thuật toán, cách truy cập bộ nhớ hoặc số lượng phép toán. Khi tối ưu, việc đổi từ `BigDecimal` sang `double`, giảm `MathContext.precision`, thay `long` bằng `int` hoặc đổi chỗ làm tròn thường giúp một đoạn code ngắn hơn và *có thể* nhanh hơn. Nhưng nếu ứng dụng trước và sau đưa ra các kết quả khác nhau đối với cùng đầu vào thì đó không còn là tối ưu tương đương: **hợp đồng tính toán đã thay đổi**.

Ví dụ ba dòng tiền dưới dạng chuỗi thập phân chính xác:

```text
0.005
0.005
0.005
```

Nếu hợp đồng yêu cầu **cộng chính xác tất cả dòng, rồi làm tròn tổng tới 2 chữ số thập phân bằng `HALF_UP`**, kết quả là `0.02`. Nếu một thay đổi “tối ưu” làm tròn **từng dòng** trước khi cộng, kết quả là `0.03`. Không thể gọi cả hai cách là tương đương vì chúng đáp ứng hai chính sách nghiệp vụ khác nhau.

**Mục tiêu bài học:** xác định hợp đồng chính xác của phép toán số; nhận diện thay đổi ngữ nghĩa khi tối ưu; ưu tiên những cải tiến giữ nguyên kết quả; đo hiệu năng đúng phương pháp; và kiểm chứng cả tính đúng đắn lẫn lợi ích hiệu năng trong Java 17+.

Bài thuộc chủ đề **Hiệu năng của Java core - numbers**. Trọng tâm là phép tính số trong một chương trình Java. Hợp đồng dữ liệu với cơ sở dữ liệu hoặc API là phần mở rộng cần đối chiếu khi quyết định quy tắc lưu/trao đổi.

## 2. “Đúng” nghĩa là gì: hợp đồng số học trước benchmark

Không có khái niệm “nhanh và đủ chính xác” mang tính phổ quát. Trước khi sửa code, cần trả lời rõ những yêu cầu dưới đây:

| Thuộc tính hợp đồng | Câu hỏi cần chốt | Ví dụ |
| --- | --- | --- |
| **Miền dữ liệu** | Âm, dương, 0, số rất lớn/rất nhỏ; có NaN/vô cực không? | Số lượng phải không âm, giới hạn trên xác định |
| **Kiểu và miền biểu diễn** | `int`, `long`, `BigInteger`, `double`, `BigDecimal`? | Tổng không được vượt miền `long` |
| **Độ chính xác** | Chính xác tuyệt đối, precision hữu hạn, hay sai số được định lượng? | Giá trị thập phân phải chính xác đến đơn vị 0.01 |
| **Điểm làm tròn** | Làm tròn mỗi đơn vị, mỗi dòng hay cuối phép tính? | `HALF_UP` một lần khi chốt tổng |
| **Chế độ làm tròn** | `HALF_EVEN`, `HALF_UP`, `DOWN`, `UNNECESSARY`...? | Từ chối dữ liệu có quá 2 chữ số có nghĩa sau dấu phẩy |
| **Scale/định dạng** | Cần giá trị hay cả biểu diễn (`1.0` khác `1.00`)? | Lưu tiền với `scale = 2` |
| **Tràn số/ngoại lệ** | Tràn được phép quay vòng, bão hòa hay phải ném lỗi? | `Math.addExact` từ chối tràn |
| **Thứ tự và tính tái lập** | Kết quả phải trùng từng bit hay chỉ trong ngưỡng sai số? | Cùng input tạo cùng output trên môi trường mục tiêu |
| **Giá trị đặc biệt** | Có chấp nhận `NaN`, `+0.0`, `-0.0`, `Infinity` không? | Thống kê không được âm thầm bỏ `NaN` |
| **Đơn vị/ngữ nghĩa** | Xu, đồng, mili giây, phần trăm, tỷ lệ hay số đếm? | Không tự đổi đơn vị khi đổi kiểu lưu |

Phải quyết định **sự tương đương** được kiểm thử bằng tiêu chí nào:

- **Đúng bằng về số học:** `BigDecimal.compareTo(other) == 0` khi không quan tâm scale.
- **Đúng cả biểu diễn:** `BigDecimal.equals(other)` khi scale cũng là một phần hợp đồng.
- **Đúng đến số chữ số quy định:** áp dụng rounding/scale tại ranh giới đã định, sau đó so sánh.
- **Sai số có giới hạn:** ví dụ công thức khoa học cho phép absolute error hoặc relative error dưới ngưỡng được mô tả cẩn thận; ngưỡng này phải được phê duyệt theo bài toán, không suy diễn từ thời gian chạy.
- **Đúng cả hành vi lỗi:** cùng input không hợp lệ phải tiếp tục bị từ chối; không được biến tràn hoặc chia không chính xác thành một kết quả giả.

Một tối ưu chỉ được coi **giữ nguyên hợp đồng** khi đáp ứng toàn bộ thuộc tính có ý nghĩa. Benchmark không thể chứng minh một phép tính sai trở nên đúng.

## 3. Vì sao đổi `BigDecimal` sang `double` có thể phá hợp đồng?

`double` theo IEEE 754 là số dấu phẩy động nhị phân có độ chính xác hữu hạn. Nhiều phân số thập phân như `0.1` và `0.2` không biểu diễn chính xác dưới dạng nhị phân hữu hạn.

```java
import java.math.BigDecimal;

BigDecimal exact = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

BigDecimal viaDouble = BigDecimal.valueOf(0.1 + 0.2);

System.out.println(exact.toPlainString());     // 0.3
System.out.println(viaDouble.toPlainString()); // 0.30000000000000004
```

Đây là đoạn mã *nhúng*, cần đặt trong `main` hoặc phương thức khác. `BigDecimal.valueOf(double)` chuyển kết quả `double` đã có thành dạng thập phân theo `Double.toString`; nó **không khôi phục** giá trị chính xác của hai toán hạng thập phân gốc.

Nếu nghiệp vụ yêu cầu tổng thập phân chính xác, thay `BigDecimal` bằng `double` chỉ để giảm allocation là thay đổi sai. Nếu nghiệp vụ ngay từ đầu cho phép sai số nhị phân đã công bố, `double` có thể là lựa chọn hợp lệ; nhưng đó là **quyết định hợp đồng**, không phải tối ưu tùy tiện.

### 3.1. `MathContext.precision` không phải tham số “càng nhỏ càng nhanh càng tốt”

```java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal p6 = one.divide(
        three, new MathContext(6, RoundingMode.HALF_EVEN));
BigDecimal p12 = one.divide(
        three, new MathContext(12, RoundingMode.HALF_EVEN));

// p6  = 0.333333
// p12 = 0.333333333333
```

Giảm precision thay đổi số chữ số có nghĩa, có thể đổi kết quả ở các bước tính tiếp theo. Nếu bài toán đòi 12 chữ số có nghĩa, đổi sang 6 chỉ để tiết kiệm CPU **vi phạm hợp đồng**. `MathContext.UNLIMITED` có thể ném `ArithmeticException` khi phép chia không có biểu diễn thập phân hữu hạn, chẳng hạn `1 / 3`; không được tự trả 0 hoặc một xấp xỉ thiếu cơ sở để né ngoại lệ.

### 3.2. `setScale` không tương đương với `round(MathContext)`

- `setScale(2, HALF_EVEN)` quyết định **hai chữ số sau dấu thập phân**.
- `round(new MathContext(2, HALF_EVEN))` quyết định **hai chữ số có nghĩa**.

Với `123.45`, cách thứ nhất giữ `123.45` (đã có scale 2), cách thứ hai làm tròn thành xấp xỉ `120`. Không thay hai API cho nhau dù có thể giảm số phép toán.

### 3.3. Không lược bỏ `RoundingMode.UNNECESSARY`

```java
new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException vì cần bỏ chữ số có giá trị.
```

Nếu chính sách là **từ chối** số có quá nhiều chữ số thập phân có giá trị, đổi thành `setScale(2, HALF_UP)` là chấp nhận dữ liệu trước đây bị từ chối. Đây là thay đổi validation nghiệp vụ. Việc dữ liệu được xử lý “trơn tru hơn” không chứng minh kết quả đúng.

## 4. Vị trí làm tròn là một phần của hợp đồng

Dữ liệu: ba dòng `0.005`, `0.005`, `0.005`, rounding mode `HALF_UP`, scale đầu ra 2.

**Chính sách A — làm tròn tổng cuối:**

```java
BigDecimal total = new BigDecimal("0.005")
        .add(new BigDecimal("0.005"))
        .add(new BigDecimal("0.005"))
        .setScale(2, RoundingMode.HALF_UP);
// 0.02
```

**Chính sách B — làm tròn từng dòng trước khi cộng:**

```java
BigDecimal line = new BigDecimal("0.005")
        .setScale(2, RoundingMode.HALF_UP); // 0.01

BigDecimal total = line.add(line).add(line); // 0.03
```

Cả hai cách đều có thể có lý do nghiệp vụ. Nhưng chúng **không thay thế được cho nhau**. Đừng kéo `setScale()` vào trong vòng lặp, đưa ra ngoài vòng lặp hoặc đổi thời điểm kết toán nếu không xác nhận yêu cầu làm tròn.

Phép cộng `BigDecimal.add` **không truyền `MathContext`** là phép cộng chính xác trong miền biểu diễn và tài nguyên cho phép. Nếu mỗi bước `add` được truyền một `MathContext`, một phép cộng có thể làm tròn ở từng bước; đổi thứ tự/lược bớt context có thể thay đổi kết quả. Tương tự với `multiply`, `divide` và `pow` có context.

### 4.1. Rounding hai lần (*double rounding*)

Nếu một pipeline làm tròn tới precision trung gian rồi lại `setScale` để hiển thị, chữ số trung gian bị bỏ có thể khiến lần làm tròn cuối lệch so với làm tròn một lần trên giá trị toán học chính xác. Vì vậy, nếu muốn “precision phụ để tăng tốc”, hãy chứng minh ràng buộc sai số của toàn pipeline. Không có một số chữ số dự phòng cố định phù hợp mọi phép tính.

### 4.2. `stripTrailingZeros()` và biểu diễn cũng có thể là ngữ nghĩa

```java
BigDecimal left = new BigDecimal("1.0");
BigDecimal right = new BigDecimal("1.00");

System.out.println(left.compareTo(right) == 0); // true
System.out.println(left.equals(right));          // false
```

Chuẩn hóa bằng `stripTrailingZeros` có thể thích hợp cho khóa số học, nhưng đổi `scale` và kết quả của `equals`/`hashCode`; giá trị như `1000.00` có thể trở thành `1E+3` (scale âm). Đừng vô điều kiện loại số 0 cuối để giảm kích thước/chi phí khi ứng dụng cần bảo toàn đơn vị đo, văn bản đầu vào, kết quả JSON hoặc khóa phân biệt scale.

## 5. Không đánh đổi quy tắc tràn số lấy tốc độ

`int` và `long` là các số nguyên có phạm vi hữu hạn. Trong Java, phép cộng/nhân nguyên thông thường có thể tràn và quay vòng theo biểu diễn hai bù. Nếu hợp đồng **yêu cầu phát hiện tràn**, hãy dùng `Math.addExact`, `Math.multiplyExact`, `Math.subtractExact` theo kiểu phù hợp:

```java
long current = 5_000L;
long incoming = 7_525L;
long cents = Math.addExact(current, incoming);

BigDecimal amount = BigDecimal.valueOf(cents, 2);
System.out.println(amount.toPlainString()); // 125.25
```

Lưu **đơn vị nhỏ nhất** bằng `long` có thể là một thiết kế hiệu quả và chính xác cho miền có thang đo cố định (ví dụ xu), **nếu** đáp ứng các điều kiện:

1. Toàn bộ giá trị đầu vào có thể đổi **chính xác** sang đơn vị nhỏ nhất.
2. Chính sách rounding của hệ thống được áp dụng đúng ở ranh giới chuyển đổi.
3. Số nhỏ nhất/lớn nhất và mọi phép tính trung gian không vượt miền `long`.
4. Phép chia, tỷ lệ/thuế và phần dư được xử lý theo đúng hợp đồng, không âm thầm dùng chia nguyên.
5. Định dạng, lưu trữ và giao tiếp giữ nguyên đơn vị và `scale` mong muốn.

Ví dụ `BigDecimal.valueOf(cents, 2)` tạo giá trị thập phân theo đơn vị xu mà không đi qua `double`. Nếu hợp đồng cần số chữ số thập phân biến đổi hoặc giá trị vượt miền `long`, cách lưu đơn vị nhỏ nhất bằng `long` có thể **không phù hợp**.

### 5.1. Khi cần số nguyên vượt miền `long`

Dùng `BigInteger` cho phép tính chính xác không bị tràn theo kích thước cố định:

```java
import java.math.BigInteger;

BigInteger factorial = BigInteger.ONE;
for (int n = 2; n <= 21; n++) {
    factorial = factorial.multiply(BigInteger.valueOf(n));
}
System.out.println(factorial); // 51090942171709440000
```

`21!` vượt `Long.MAX_VALUE`. Thay `BigInteger` bằng `long` để nhanh hơn mà không có kiểm tra miền sẽ làm sai giá trị. Ngược lại, nếu toàn miền dữ liệu được chứng minh chắc chắn nằm trong `long`, có thể cân nhắc thiết kế `long` và dùng checked arithmetic, kiểm thử ranh giới và công bố bất biến đó.

**Atomicity không chữa tràn số:** `AtomicLong.incrementAndGet()` bảo vệ cập nhật concurrent nhưng vẫn có thể quay vòng nếu vượt phạm vi `long`. Khi số đếm tuyệt đối không được tràn, phải kết hợp quy tắc miền và cập nhật có điều kiện phù hợp.

## 6. Số dấu phẩy động, thứ tự cộng và tính tái lập

Với `float`/`double`, phép cộng không luôn kết hợp theo nghĩa toán học khi có làm tròn:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Biểu thức `b + c` làm mất `1.0` do độ lớn chênh lệch. Vì vậy thay một vòng lặp tuần tự bằng phép reduction song song, đổi thứ tự phần tử hoặc nhóm cặp hạng để “tăng throughput” **có thể đổi kết quả**, ngay cả khi không đổi kiểu `double`.

Những vấn đề cần xét trong hợp đồng:

- Có yêu cầu trùng bit giữa các lần chạy hay chỉ yêu cầu sai số trong ngưỡng đã phê duyệt?
- Cách cộng đã được định nghĩa theo thứ tự phần tử chưa?
- Có hỗ trợ `NaN`, `Infinity`, signed zero (`-0.0`/`+0.0`), overflow/underflow không?
- Có cần thuật toán ổn định hơn, ví dụ cộng bù (*compensated summation*) hay tổng đôi/cặp, để giảm sai số?
- Các phép biến đổi của compiler/JVM và thư viện số trong JDK mục tiêu có được đặc tả phù hợp không?

Kỹ thuật tăng độ ổn định số học có thể *cải thiện sai số*, nhưng nếu nó đổi output cũ thì vẫn phải kiểm chứng so với hợp đồng. Nếu hợp đồng yêu cầu kết quả từng bit giống thuật toán cũ, “chính xác hơn” vẫn có thể là thay đổi không tương thích.

Java 17 luôn sử dụng semantics floating-point chặt theo quy tắc ngôn ngữ (*always-strict floating-point semantics*); điều đó không biến `double` thành số thập phân chính xác và không khiến phép cộng trở nên kết hợp.

### 6.1. Với `BigDecimal`, thứ tự tính và context vẫn quan trọng

Cộng `BigDecimal` chính xác, không dùng `MathContext`, thường bảo toàn cùng một giá trị toán học bất kể cách nhóm phép cộng; tuy nhiên biểu diễn `scale` và việc tạo đối tượng vẫn có thể quan trọng với API. Khi áp dụng `MathContext` ở các bước trung gian, thứ tự tính có thể làm thay đổi các lần làm tròn. Vì vậy không hoán đổi phép toán, song song hóa hay vector hóa mà bỏ qua vị trí rounding đã quy định.

## 7. Các tối ưu nên xét trước khi giảm độ chính xác

Những cải tiến dưới đây thường bảo toàn quy tắc tính toán hơn, **nhưng vẫn cần kiểm chứng với hợp đồng cụ thể**.

### 7.1. Chọn thuật toán tốt hơn

Tránh tính lại cùng một giá trị không thay đổi; dùng precomputation/cache cho kết quả của hàm thuần túy nếu khóa cache chứa **mọi tham số ngữ nghĩa**: operands, rounding mode, precision, scale, đơn vị và phiên bản quy tắc. Với đầu vào nhiều số rất lớn, kiểm tra độ phức tạp thuật toán, giới hạn lặp và bộ nhớ thay vì cắt bớt chữ số.

Nếu một báo cáo cần min/max/count, `IntStream.summaryStatistics()` có thể duyệt một lượt thay vì dựng nhiều stream; nhưng phải giữ đúng cách xử lý rỗng và tràn tổng, không dựa vào giá trị khởi tạo min/max khi count bằng 0.

### 7.2. Loại việc cấp phát/chuyển đổi không cần thiết

**Tốt hơn cho dữ liệu đã đúng kiểu:**

```java
static BigDecimal sumAmounts(List<BigDecimal> values) {
    BigDecimal total = BigDecimal.ZERO;
    for (BigDecimal value : values) {
        total = total.add(value); // chính xác, không chuyển qua double
    }
    return total;
}
```

Hàm trên cần `import java.math.BigDecimal; import java.util.List;` và là một phương thức *nhúng*. `BigDecimal` bất biến nên các phép cộng có thể tạo đối tượng mới; không thể “sửa” đối tượng hiện có bằng `+=`.

Nếu đầu vào đến dưới dạng `String`, parse **một lần ở ranh giới** vào kiểu phù hợp; tránh liên tục đổi `BigDecimal -> String -> double -> BigDecimal` trong hot path. Có thể giữ constant/context dùng chung cho cùng một chính sách:

```java
static final MathContext MONEY_MC =
        new MathContext(18, RoundingMode.HALF_EVEN);
```

`MathContext` bất biến và có thể tái sử dụng khi quy tắc tính toán giống nhau. Tuy nhiên không thay precision hoặc rounding mode của constant chỉ để giảm chi phí.

### 7.3. Tách phép tính số khỏi định dạng và I/O

Nếu workload phải cộng một triệu giá trị, không gọi `toPlainString()`, formatter hoặc ghi log cho từng phép cộng trừ khi hợp đồng cần log từng bước. Thực hiện tính toán rồi định dạng tại **ranh giới xuất**. Nhưng nếu hợp đồng yêu cầu làm tròn/chuẩn hóa từng dòng, không được dời `setScale` sang cuối chỉ vì việc tạo đối tượng ít hơn.

Tách allocation, serialization, log và truy cập DB khỏi vùng CPU nóng có thể có lợi mà không thay đổi kết quả số.

### 7.4. Dùng primitive đúng miền, với checked arithmetic

Nếu quy tắc dùng số nguyên và miền đã được chứng minh, `int`/`long` có thể tránh overhead của object. Tuy nhiên:

- `int` có miền nhỏ hơn `long`; chuyển `long` sang `int` có thể cắt dữ liệu.
- `long` là số nguyên, không biểu diễn phân số trực tiếp; dùng đơn vị cố định với factor đã thỏa hợp đồng.
- `Math.addExact`/`multiplyExact` giúp giữ quy tắc phát hiện tràn.
- Không dùng phép chia nguyên nếu trước đây nghiệp vụ cho phép phân số.
- Không giả định đổi sang kiểu primitive sẽ tự động nhanh hơn: đo thực tế.

### 7.5. Điều chỉnh lưu trữ/cấu trúc dữ liệu, không điều chỉnh toán học

Với tập dữ liệu lớn, cách truy cập tuần tự, dung lượng cache CPU, lựa chọn array/collection, số lần boxing, batch I/O và concurrency có thể quyết định hiệu năng. Chọn cấu trúc phù hợp vẫn phải bảo đảm thứ tự, null handling, duplicate handling và ngữ nghĩa của dữ liệu.

Ví dụ `Arrays.stream(intArray).sum()` dùng `int` và có thể tràn; nếu tổng yêu cầu `long`, phải mở rộng đúng cách (`mapToLong`) và kiểm tra tràn phù hợp. Không chọn API tiện tay chỉ vì cú pháp ngắn hơn.

## 8. Ví dụ Java 17+ hoàn chỉnh: nhìn thấy thay đổi hợp đồng

Tạo file **`ExactnessPerformanceDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class ExactnessPerformanceDemo {

    // Hợp đồng A: cộng chính xác, chỉ làm tròn khi chốt tổng.
    static BigDecimal roundAtTotal(List<String> values) {
        BigDecimal total = BigDecimal.ZERO;
        for (String text : values) {
            total = total.add(new BigDecimal(text));
        }
        return total.setScale(2, RoundingMode.HALF_UP);
    }

    // Hợp đồng B: làm tròn mỗi dòng trước khi cộng.
    static BigDecimal roundPerItem(List<String> values) {
        BigDecimal total = BigDecimal.ZERO;
        for (String text : values) {
            total = total.add(
                    new BigDecimal(text).setScale(2, RoundingMode.HALF_UP));
        }
        return total.setScale(2, RoundingMode.HALF_UP);
    }

    public static void main(String[] args) {
        List<String> amounts = List.of("0.005", "0.005", "0.005");

        System.out.println("round at total = "
                + roundAtTotal(amounts).toPlainString());
        System.out.println("round per item = "
                + roundPerItem(amounts).toPlainString());

        System.out.println("exact sum = "
                + new BigDecimal("0.1").add(new BigDecimal("0.2"))
                        .toPlainString());
        System.out.println("double sum = "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());

        long cents = Math.addExact(5_000L, 7_525L);
        System.out.println("checked minor units = "
                + BigDecimal.valueOf(cents, 2).toPlainString());

        try {
            new BigDecimal("1.234")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("strict scale = rejected");
        }

        BigDecimal first = new BigDecimal("1.0");
        BigDecimal second = new BigDecimal("1.00");
        System.out.println("numeric compare = "
                + (first.compareTo(second) == 0));
        System.out.println("structural equals = "
                + first.equals(second));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ExactnessPerformanceDemo.java
java ExactnessPerformanceDemo
```

Stdout xác định:

```text
round at total = 0.02
round per item = 0.03
exact sum = 0.3
double sum = 0.30000000000000004
checked minor units = 125.25
strict scale = rejected
numeric compare = true
structural equals = false
```

Điều chương trình chứng minh:

1. **Thời điểm rounding là ngữ nghĩa.** Hai hàm dùng cùng dữ liệu, scale và `HALF_UP`, nhưng mỗi hàm làm tròn tại ranh giới khác nhau nên kết quả khác nhau.
2. **Đổi sang `double` không bảo toàn thập phân.** Ngay cả ví dụ `0.1 + 0.2` đã có giá trị khác.
3. **Dùng `long` với đơn vị nhỏ nhất có thể đúng khi miền cố định.** `Math.addExact` làm rõ hợp đồng tràn, `BigDecimal.valueOf(cents, 2)` khôi phục biểu diễn hai chữ số thập phân mà không đi qua `double`.
4. **`UNNECESSARY` là một quy tắc từ chối.** Đổi nó sang rounding mode khác sẽ thay đổi dữ liệu được hệ thống chấp nhận.
5. **Giá trị số và biểu diễn là hai khái niệm.** `compareTo` coi `1.0` và `1.00` bằng nhau, `equals` thì không. Đừng loại bỏ scale để “tối ưu cache” nếu ứng dụng cần phân biệt chúng.

Đây là bằng chứng về **tính đúng đắn**, không phải benchmark: không có kết luận nào về thời gian nhanh/chậm chỉ từ stdout của chương trình này.

## 9. Benchmark có ý nghĩa sau khi đã khóa hợp đồng

Quy trình tối ưu nên chạy theo thứ tự:

1. **Viết đặc tả đầu ra và xử lý lỗi:** kiểu, miền giá trị, scale, precision, rounding mode, thời điểm rounding, overflow và ngoại lệ.
2. **Tạo tập dữ liệu đối chiếu:** các giá trị bình thường và trường hợp biên. Giữ giá trị kỳ vọng được tính độc lập khi có thể.
3. **Đo baseline:** ghi môi trường JDK, CPU, dung lượng heap, input size, mức tải đồng thời, throughput/latency/GC.
4. **Tối ưu một yếu tố rõ ràng:** thuật toán, allocation, định dạng, cấu trúc dữ liệu, chi phí đồng bộ hoặc I/O.
5. **Chạy kiểm thử hợp đồng trước:** đối chiếu kết quả, lỗi, scale, precision và điều kiện biên.
6. **Đo lại theo cùng workload:** đánh giá trung vị, phân bố và độ nhiễu; chỉ giữ tối ưu khi có lợi ích đủ rõ và tính đúng đắn được bảo toàn.
7. **Ghi lại quyết định:** vì sao thay đổi an toàn, giới hạn miền áp dụng và điều kiện phải benchmark lại.

### 9.1. Vì sao không đo một lần với `System.nanoTime()`?

JVM có JIT compilation, class loading, warmup, GC và tối ưu code dựa trên profiling. Benchmark một lần thường đo lẫn quá trình khởi động và các yếu tố không liên quan. Compiler cũng có thể loại bỏ phép tính không ảnh hưởng đầu ra (*dead-code elimination*); đo một vòng lặp như vậy có thể khiến phương pháp sai trông “cực nhanh”.

Trong Java, JMH là thư viện benchmark vi mô thường được dùng để kiểm soát warmup, nhiều lần đo, fork JVM, tải song song và việc tiêu thụ kết quả thông qua `Blackhole`. Nhưng ngay cả JMH chỉ trả lời **hiệu năng của workload được đo**, không chứng minh tính tương đương số học.

### 9.2. Tách chi phí benchmark và chi phí sản phẩm

Ví dụ so sánh `BigDecimal` với một thuật toán long minor-units cần:

- Chuẩn bị dữ liệu **ngoài đoạn đo** nếu chỉ benchmark phép cộng; hoặc đo cả parse/format nếu đó là một phần đường xử lý thực tế.
- Dùng cùng input và quy tắc đơn vị, xác định overflow handling nhất quán.
- Đánh giá chính sách làm tròn trên các đầu vào không phải bội của đơn vị nhỏ nhất.
- Bảo đảm vòng đo tiêu thụ kết quả, không để JVM loại công việc.
- Thử với kích thước dữ liệu vừa, lớn và giá trị ở ranh giới.
- Đo GC/allocation nếu lý do tối ưu là giảm đối tượng, và đo tail latency nếu hệ thống nhạy với độ trễ.

Không được chỉ đo phương pháp mới trên các số “đẹp”, còn phương pháp cũ trên số cần làm tròn nhiều chữ số; workload khác nhau không chứng minh phương pháp mới vượt trội.

## 10. Kiểm thử hồi quy: phải so cái gì?

Tạo test ở đúng ranh giới mà nghiệp vụ có thể quan sát.

**Các case thập phân nên có:**

| Input/đặc điểm | Mục tiêu |
| --- | --- |
| `"0.1" + "0.2"` | Phát hiện chuyển đổi qua `double` |
| `0.005` lặp 3 lần | Phát hiện đổi điểm rounding |
| `"1.0"` và `"1.00"` | Phân biệt giá trị số với scale |
| `1.234` với scale 2 + `UNNECESSARY` | Giữ hành vi từ chối |
| `Long.MAX_VALUE + 1` với `Math.addExact` | Kiểm tra overflow bị từ chối |
| Số âm và điểm giữa như `-2.345`, `2.345`, `2.355` | Kiểm tra rounding mode |
| Giá trị rất nhỏ và rất lớn | Kiểm tra precision/scale/exponent và miền kiểu |
| Phép chia không kết thúc như `1/3` | Kiểm tra MathContext và ngoại lệ |
| `NaN`, ±infinity, `-0.0` nếu dùng `double` | Kiểm tra quy tắc cho giá trị đặc biệt |

Nếu hợp đồng yêu cầu đúng đến xu, so sánh **giá trị và scale đã chuẩn hóa theo hợp đồng**, không lấy `doubleValue()` của hai `BigDecimal` rồi dùng `==`. Nếu hợp đồng yêu cầu giữ biểu diễn, kiểm tra `equals`, `scale()` hoặc chuỗi xuất. Nếu hợp đồng cho phép sai số, định nghĩa sai số tuyệt đối/tương đối phù hợp cả gần 0, cực lớn, `NaN` và vô cực.

Có thể áp dụng **differential testing**: chạy bản baseline và bản tối ưu trên cùng tập dữ liệu, so kết quả theo đúng quan hệ tương đương đã đặc tả. Đây là cách phát hiện hồi quy, nhưng một baseline có bug không tự trở thành tiêu chuẩn đúng; khi có nghi ngờ, đối chiếu yêu cầu nghiệp vụ hoặc oracle độc lập.

### 10.1. Test tính đúng và test hiệu năng có nhiệm vụ khác nhau

- Unit/property test: xác nhận tính đúng, phạm vi dữ liệu, ngoại lệ, rounding.
- Benchmark: xác nhận thời gian/tài nguyên, mức dao động, khả năng mở rộng.
- Integration test: xác nhận kiểu dữ liệu, database scale, serialization và toàn pipeline.
- Kiểm thử concurrency: xác nhận trạng thái chia sẻ và thứ tự xử lý không làm mất hoặc thay đổi dữ liệu theo hợp đồng.

Một benchmark chạy nhanh và không ném exception vẫn có thể xuất ra số sai. Một unit test chạy đúng trên vài đầu vào vẫn không chứng minh hiệu năng trong môi trường production.

## 11. Ra quyết định khi tối ưu khiến kết quả khác đi

Có những trường hợp lợi ích thời gian rất lớn khiến doanh nghiệp muốn chấp nhận độ chính xác thấp hơn. Điều này có thể hợp lệ **chỉ khi có thay đổi hợp đồng rõ ràng**, ví dụ thay yêu cầu “tính chính xác tuyệt đối” bằng “sai số tương đối dưới ngưỡng X trên miền Y”, với phương pháp đánh giá và tình huống không đáp ứng đã thống nhất.

Khi đề xuất như vậy, cần ghi rõ:

1. **Trước:** quy tắc đầu vào, output và lỗi hiện tại.
2. **Sau:** kiểu/precision/rounding/sai số mới, những đầu vào thay đổi kết quả.
3. **Ảnh hưởng:** tiền, thuế, giới hạn quota, quyết định so sánh, downstream API, định dạng và audit.
4. **Mức độ chấp nhận:** ai có quyền phê duyệt việc đổi hợp đồng; quy trình migration/backfill nếu dữ liệu đã lưu.
5. **Bằng chứng:** test đối chiếu, phân tích sai số và benchmark trên workload thực.
6. **Phương án phục hồi:** cờ cấu hình, version API hoặc rollback nếu cần.

Nếu chưa có yêu cầu hoặc phê duyệt thay đổi hợp đồng, giữ nguyên tiêu chuẩn cũ và tìm những tối ưu an toàn hơn. Không âm thầm đánh đổi tính chính xác để đạt một ngưỡng throughput hoặc giảm vài mili giây.

## 12. Những sai lầm thường gặp

| Sai lầm khi tối ưu | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Thay `BigDecimal` bằng `double` không đối chiếu yêu cầu | Khác giá trị thập phân, rounding/overflow/NaN | Xác nhận sai số cho phép trước; giữ BigDecimal nếu cần chính xác |
| Hạ `MathContext` để làm nhanh | Mất chữ số có nghĩa ở phép tính hiện tại và bước sau | Giữ precision theo hợp đồng; tối ưu chi phí khác |
| Di chuyển `setScale` từ cuối sang trong vòng lặp | Đổi vị trí rounding, sai tổng | Giữ nguyên ranh giới làm tròn |
| Đổi `HALF_EVEN` sang `HALF_UP` tùy tiện | Khác kết quả tại điểm giữa | Rounding mode theo nghiệp vụ |
| Bỏ `UNNECESSARY` | Chấp nhận input trước đây phải từ chối | Bảo toàn validation |
| Đổi `BigInteger` sang `long` không xét miền | Tràn số | Chỉ đổi khi chứng minh miền, dùng checked arithmetic |
| Dùng `int` cho tổng lớn vì ít tốn bộ nhớ | Tràn miền `int` | Tính đúng kích thước miền từ input và tổng |
| Đưa reduction `double` sang song song rồi đòi output trùng bit | Thứ tự cộng khác, kết quả khác | Đặc tả thứ tự hoặc dung sai hợp lệ |
| `stripTrailingZeros` mọi nơi | Mất scale/biểu diễn cần thiết | Chuẩn hóa chỉ ở ranh giới có hợp đồng tương ứng |
| `BigDecimal.valueOf(doubleSum)` để “sửa” sai số double | Chỉ chuyển sai số đã có sang dạng thập phân | Tính trực tiếp từ dữ liệu decimal chính xác |
| Chỉ benchmark mà không test số | Tối ưu sai có thể nhanh hơn | Đặt correctness gate trước performance gate |
| Đo một lượt bằng `nanoTime()` | Dễ nhiễu bởi JIT/GC/OS | Benchmark có warmup, fork, nhiều mẫu và workload thích hợp |
| Benchmark cả parse bản cũ nhưng bỏ parse ở bản mới | So sánh không công bằng | Đo cùng ranh giới xử lý và cùng input |
| Dựa vào kết quả đầu ra trên vài số “đẹp” | Không thấy lỗi ở ranh giới | Test số âm, zero, large, tiny, ties, overflow, precision |

## 13. Bài tập áp dụng

1. Đội phát triển muốn thay mọi `BigDecimal` trong hệ thống tính thuế bằng `double` vì benchmark nhanh hơn. Bạn cần hỏi và kiểm chứng những điều gì trước khi chấp nhận?
2. Có 1.000 dòng dữ liệu, mỗi dòng `0.005` đơn vị. Tính tổng theo chính sách “round từng dòng bằng HALF_UP” và “round một lần ở tổng”. Hai kết quả khác nhau thế nào? Chính sách nào đúng nếu hóa đơn được quy định là tổng của các dòng đã làm tròn?
3. Một hàm `sum` đang dùng `Math.addExact` để từ chối overflow. Đổi sang phép cộng `+` thông thường có giữ hợp đồng không? Hãy lập case biên.
4. Một chỉ số số thực được tổng hợp bằng `double`; bản mới dùng `parallelStream()` cho phép cộng. Vì sao khác biệt chữ số cuối không phải lúc nào cũng là bug, nhưng cũng không thể tự bỏ qua?
5. Bạn có thể dùng `long` đếm xu thay `BigDecimal` trong hệ thống giá tiền khi nào? Hãy liệt kê quy tắc chuyển đổi, overflow và rounding.
6. Nếu dữ liệu `"1.0"` và `"1.00"` dùng làm khóa `HashMap`, liệu thay bằng `stripTrailingZeros()` trong đường xử lý mới có thể ảnh hưởng kết quả tra cứu không?
7. Lên kế hoạch benchmark cho một hàm xử lý 10 triệu giá trị, phân biệt chi phí parse, arithmetic, logging và serialization; đề xuất test hợp đồng trước khi đo.

**Gợi ý:** (1) xác định rounding, scale, đơn vị, sai số, miền, serializing và đầu vào biên; không dựa duy nhất vào benchmark. (2) từng dòng thành `0.01` nên tổng `10.00`; làm tròn tổng `5.000` thành `5.00`. Nếu hóa đơn quy định cộng các dòng đã làm tròn, đáp án đúng là `10.00`. (3) không giữ hợp đồng: `Long.MAX_VALUE + 1` có thể quay vòng với `+`, nhưng `addExact` ném `ArithmeticException`. (4) phép cộng `double` không kết hợp, chỉ chấp nhận khác biệt nếu hợp đồng sai số/tái lập cho phép. (5) scale cố định, miền đủ, conversion chính xác, checked arithmetic và quy tắc làm tròn minh bạch. (6) có thể vì `equals/hashCode` xem scale như một phần của identity. (7) đo cùng pipeline, có warmup/fork; so correctness với oracle trước.

## 14. Ghi nhớ cho quyết định hiệu năng

Một tối ưu số học thành công phải có **hai bằng chứng độc lập**: (1) kết quả, lỗi và biểu diễn đáp ứng hợp đồng đã định; (2) thời gian hoặc tài nguyên thực sự được cải thiện trong workload đại diện. Những thay đổi như giảm precision, đổi kiểu số, đổi điểm rounding hay bỏ overflow check có thể làm thay đổi bài toán; không thực hiện chỉ để giảm thời gian.

Ưu tiên cải thiện thuật toán, tránh chuyển đổi thừa, cô lập format/I/O, lựa chọn cấu trúc dữ liệu phù hợp, cache kết quả thuần túy với khóa đầy đủ, và benchmark có kiểm soát. Khi cần đánh đổi độ chính xác, định nghĩa đó là **thay đổi hợp đồng có chủ đích**, với phạm vi áp dụng, sai số, test và phê duyệt rõ ràng.

Tài liệu Java 17 tham khảo:
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [`MathContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html), [`RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html).
- [`BigInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [`Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html), [`Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- [Java Language Specification §15, §17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html) cho quy tắc biểu thức số và thực thi Java.
