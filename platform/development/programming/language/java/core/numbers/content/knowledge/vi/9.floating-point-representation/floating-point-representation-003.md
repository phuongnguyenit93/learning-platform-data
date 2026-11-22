# Precision nhị phân và số chữ số thập phân có thể tin cậy trong Java

Khi viết `double x = 0.1;`, nhiều người nghĩ máy tính đã lưu đúng **một phần mười**. Thực tế `float` và `double` của Java dùng biểu diễn dấu phẩy động **nhị phân**, nên đa số phân số thập phân như 0,1 không thể lưu chính xác. Giá trị được làm tròn tới một số nhị phân biểu diễn được gần nhất.

Một câu hỏi quan trọng hơn câu “`double` có bao nhiêu chữ số?” là: **số chữ số nào có thể tin cậy cho phép tính, và cần bao nhiêu chữ số thập phân để ghi ra rồi đọc lại đúng cùng giá trị bit?** Hai con số này khác nhau.

Bài học làm rõ *precision* (độ chính xác của phần trị), sai số làm tròn, khoảng cách giữa các số biểu diễn được (*ULP*), ý nghĩa của khoảng “6–9 chữ số” với `float`, “15–17 chữ số” với `double` và cách sử dụng các con số ấy khi lập trình Java 17+.

## 1. `float` và `double` lưu số bằng các bit như thế nào?

Java sử dụng biểu diễn dấu phẩy động nhị phân IEEE 754 cho hai kiểu:

| Đặc điểm | `float` | `double` |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ lưu trữ (*exponent field*) | 8 | 11 |
| Bit phần phân số lưu trữ (*fraction field*) | 23 | 52 |
| Độ chính xác phần trị (*significand precision*) cho số chuẩn hóa | **24 bit** | **53 bit** |
| Số chữ số thập phân có nghĩa thường có thể tin cậy | **khoảng 6–7** | **khoảng 15–16** |
| Số chữ số thập phân có nghĩa tối đa đủ để ghi mọi giá trị rồi đọc lại đúng bit | **9** | **17** |

Tại sao có 24 bit nhưng chỉ lưu 23 bit phân số? Với **số chuẩn hóa** (*normal number*), IEEE 754 có một bit 1 đầu tiên được **ngầm hiểu** trong phần trị nhị phân. Vì vậy `float` có độ chính xác 24 bit và `double` có 53 bit. Với **số dưới chuẩn** (*subnormal*) rất gần 0, bit 1 ngầm định không còn nữa; số bit có nghĩa thực tế có thể ít hơn.

Về ý tưởng, số chuẩn hóa có dạng:

```text
(-1)^sign × (1.fractionBits)_2 × 2^exponent
```

Số mũ cho phép biểu diễn số rất lớn hoặc rất nhỏ; **số bit phần trị** mới quyết định khoảng cách giữa hai giá trị liên tiếp và độ chi tiết có thể giữ lại. Đừng nhầm **range** (miền độ lớn) với **precision** (độ phân giải số).

Ví dụ `double` có thể có trị tuyệt đối đến khoảng `1.8 × 10^308` nhưng không thể phân biệt được mọi cặp số nguyên liên tiếp tại khoảng `10^16`.

## 2. Vì sao 0,1 thập phân không được lưu chính xác?

Hệ nhị phân biểu diễn chính xác các phân số có mẫu số là lũy thừa của 2 sau khi rút gọn:

- `0.5 = 1/2 = 0.1₂` được lưu chính xác.
- `0.25 = 1/4 = 0.01₂` được lưu chính xác.
- `0.125 = 1/8 = 0.001₂` được lưu chính xác.
- `0.1 = 1/10` có mẫu số chứa thừa số 5, nên khai triển nhị phân kéo dài vô hạn và không thể lưu đúng bằng hữu hạn bit.

Giá trị `double` gần `0.1` thực sự là:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Đây là giá trị thập phân **chính xác của số nhị phân được lưu**, không phải kết quả Java mặc định in ra cho literal. Với `System.out.println(0.1)`, Java thường in `0.1` vì chuỗi ngắn đó đủ để đọc ngược lại ra cùng giá trị `double`.

```java
System.out.println(0.1);       // 0.1 (định dạng ngắn có thể round-trip)
System.out.println(0.1 + 0.2); // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

Cả `0.1`, `0.2` và `0.3` đều đã được làm tròn về nhị phân, và phép cộng được làm tròn thêm. Vì thế kết quả cộng hai giá trị lưu gần `0.1` và `0.2` không nhất thiết bằng bit của giá trị lưu gần `0.3`.

Quan trọng: **sai số không có nghĩa JVM tính “sai chuẩn Java”**. Chính phép tính trên `double` tuân theo biểu diễn và quy tắc làm tròn được quy định; khác biệt xuất hiện khi đối chiếu với số học thập phân chính xác mà con người kỳ vọng.

## 3. Precision nhị phân: 24 bit và 53 bit phần trị

Độ chính xác phần trị `p` bit có nghĩa là, quanh một số chuẩn hóa, phần trị chứa khoảng `p` bit thông tin nhị phân. Đổi sang chữ số thập phân có nghĩa bằng phép ước lượng:

```text
float:  24 × log10(2) ≈ 7.2247 chữ số
double: 53 × log10(2) ≈ 15.9546 chữ số
```

Vì vậy thường nói **`float` có khoảng 7 chữ số có nghĩa**, **`double` có khoảng 15–16 chữ số có nghĩa**. Đây là hướng dẫn thực tế về độ chính xác tương đối của số chuẩn hóa, **không phải cam kết rằng mọi giá trị in ra có đúng 7 hoặc 16 chữ số đáng tin**.

Ví dụ:

```java
float f = 16_777_216f;
float changed = f + 1f;
// f và changed bằng nhau: tại 2^24, ULP phía trên là 2 nên +1 bị làm tròn trở lại
```

Ở độ lớn lớn hơn, đơn vị nhỏ không còn phân biệt được. Cần luôn xét **độ lớn của số**, **độ chênh cần đo** và **các phép toán đã diễn ra**, không chỉ đếm chữ số sau dấu phẩy.

## 4. Khác biệt giữa số chữ số đáng tin và số chữ số để round-trip

Hai hướng chuyển đổi dữ liệu là:

1. **Decimal → Binary → Decimal:** ta nhập một số thập phân có số chữ số có nghĩa nhất định, lưu bằng `float`/`double` rồi muốn diễn tả lại con số ban đầu với độ chính xác đã chọn.
2. **Binary → Decimal → Binary:** ta đã có một giá trị bit bất kỳ của `float`/`double`, ghi ra chuỗi thập phân, rồi muốn parse chuỗi trở lại **đúng giá trị bit ban đầu**.

Hai mục tiêu yêu cầu số chữ số khác nhau.

| Câu hỏi | `float` | `double` |
| --- | ---: | ---: |
| Số chữ số có nghĩa thập phân bảo thủ thường dùng khi cần giữ độ chính xác | **6** | **15** |
| Giới hạn chữ số dùng để **đảm bảo mọi giá trị hữu hạn** có thể round-trip dạng nhị phân → chuỗi đủ chính xác → nhị phân | **9** | **17** |
| Hướng dẫn gần đúng về độ chính xác có nghĩa trong bài tính | **6–7** | **15–16** |

**9 hoặc 17 không phải số chữ số “đều chính xác so với giá trị toán học ban đầu”.** Chúng là số chữ số thập phân có nghĩa đủ để **phân biệt các giá trị nhị phân** khi chuyển đổi văn bản với cách làm tròn phù hợp.

Ngược lại, **6 và 15** là những mốc bảo thủ để thảo luận việc duy trì các chữ số thập phân có nghĩa qua chuyển đổi; chúng không tuyên bố rằng chữ số thứ 7 hay 16 luôn sai. Từng giá trị như `0.5` có thể được biểu diễn chính xác, còn số như `0.1` không.

Trong Java, `Float.toString` và `Double.toString` chọn biểu diễn thập phân ngắn cần thiết theo quy tắc chuyển đổi của Java; khi cần lưu/đọc lại các giá trị, nên dùng các API ấy và `parseFloat`/`parseDouble` thay vì tự cắt cố định 6 hoặc 15 chữ số.

```java
double original = Math.PI;
String saved = Double.toString(original);
double restored = Double.parseDouble(saved);

boolean sameBits =
        Double.doubleToRawLongBits(original)
        == Double.doubleToRawLongBits(restored);
// true
```

Với chương trình thực tế, nếu có `NaN` mang payload đặc biệt, nhiều chi tiết bit không được bảo toàn qua văn bản; ví dụ ở trên dùng giá trị hữu hạn bình thường. `Double.toString` xuất `-0.0` riêng, nhưng đừng mở rộng nhận xét round-trip đơn giản này thành bảo đảm giữ mọi payload `NaN`.

## 5. ULP: khoảng cách giữa các giá trị biểu diễn được

**ULP** (*unit in the last place*) có thể hiểu thực dụng là độ lớn của một bước lưới số ở độ lớn đang xét. Với số chuẩn hóa thuộc vùng `[2^e, 2^(e+1))`, khoảng cách giữa các số cùng vùng xấp xỉ:

```text
ULP ≈ 2^(e - (p - 1))
p = 24 đối với float; p = 53 đối với double
```

Khi số lớn dần, **khoảng cách giữa các số biểu diễn được cũng tăng**. Vì vậy ta không thể nói `double` luôn chính xác đến “15 chữ số sau dấu chấm”: con số đáng quan tâm là **chữ số có nghĩa**, và độ phân giải tuyệt đối phụ thuộc vào độ lớn giá trị.

Java cung cấp `Math.ulp` và `Math.nextUp` để quan sát:

```java
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
System.out.println(Math.ulp(1.0));  // 2.220446049250313E-16
System.out.println(Math.nextUp(1.0)); // 1.0000000000000002
```

Tại chính `1.0`, `Math.ulp(1.0)` là khoảng từ 1.0 đến số `double` lớn hơn gần nhất. Về phía dưới 1.0, bước có thể nhỏ hơn do ranh giới giữa hai vùng số mũ.

### Số nguyên liên tiếp bắt đầu “dính” vào nhau ở đâu?

`float` có 24 bit phần trị, nên mọi số nguyên từ `-2^24` đến `2^24` đều biểu diễn chính xác; nhưng `2^24 + 1` không biểu diễn được dưới dạng `float`.

```java
int originalInt = 16_777_217; // 2^24 + 1
float roundedFloat = originalInt; // 16777216.0f
```

`double` có 53 bit phần trị, nên mọi số nguyên từ `-2^53` đến `2^53` đều biểu diễn chính xác; `2^53 + 1` không biểu diễn được dưới dạng `double`:

```java
long originalLong = 9_007_199_254_740_993L; // 2^53 + 1
double roundedDouble = originalLong; // 9.007199254740992E15
```

**Đây đều là widening hợp lệ của Java**, không cần cast và không ném exception, nhưng có mất một đơn vị giá trị. Nếu dữ liệu là ID, số lượng nguyên lớn, bộ đếm hoặc giá trị cần so sánh tuyệt đối, đừng tự ý chuyển `long` qua `double`.

## 6. Số thực có rất nhiều chữ số sau dấu phẩy không có nghĩa là tin cậy hết

Việc dùng một định dạng in rất dài, hoặc chuyển `double` thành biểu diễn thập phân chính xác của chính các bit đang lưu, có thể tạo ra hàng chục chữ số sau dấu chấm. Điều đó **không biến những chữ số ấy thành độ chính xác mới** so với con số người dùng đã định nhập.

```java
double x = 0.1;
System.out.println(Double.toString(x)); // 0.1
System.out.println(new java.math.BigDecimal(x));
// 0.1000000000000000055511151231257827021181583404541015625
```

`Double.toString(x)` hiển thị biểu diễn thập phân phù hợp để parse lại cùng giá trị binary; `new BigDecimal(x)` lấy **chính xác giá trị nhị phân đang có** rồi diễn tả thành thập phân, phơi bày sai khác.

Ngược lại:

```java
java.math.BigDecimal decimal =
        new java.math.BigDecimal("0.1");
java.math.BigDecimal fromValueOf =
        java.math.BigDecimal.valueOf(0.1);
```

Cả hai ở ví dụ trên biểu diễn giá trị thập phân `0.1` theo dạng decimal; `BigDecimal.valueOf(double)` dựa trên chuỗi mà `Double.toString` tạo ra, **không** làm lộ toàn bộ phân số nhị phân như constructor `new BigDecimal(double)`.

Nếu dữ liệu được nhập dưới dạng thập phân và phải giữ chính xác số thập phân đó, tạo `BigDecimal` từ **chuỗi** hoặc từ số nguyên cùng *scale* là cách rõ ràng hơn việc đi vòng qua `double`.

## 7. Sai số tích lũy và hiện tượng triệt tiêu chữ số có nghĩa

Sai số không chỉ xuất hiện khi tạo literal: mỗi phép cộng, trừ, nhân, chia số thực có thể làm tròn. Nhiều phép toán liên tiếp có thể tích lũy sai lệch:

```java
double sum = 0.0;
for (int i = 0; i < 10; i++) {
    sum += 0.1;
}
System.out.println(sum); // 0.9999999999999999
```

Tổng toán học là 1, nhưng từng lần cộng và lưu kết quả đều có thể làm tròn. **10 phép toán không bảo đảm sai số gấp đúng 10 lần**: sai số có thể bù trừ hoặc tăng tùy dữ liệu và thứ tự tính.

Một hiện tượng đáng chú ý là **cancellation** (mất chữ số có nghĩa khi trừ hai số gần nhau):

```java
double large = 1e16;
double tinyAddition = (large + 1.0) - large;
System.out.println(tinyAddition); // 0.0, không phải 1.0
```

Tại khoảng `1e16`, bước lưới của `double` lớn hơn 1, nên phép `large + 1.0` đã làm tròn thành `large`. Phép trừ phía sau không thể phục hồi phần đã mất.

Còn với một phép trừ hai số lớn gần bằng nhau, sai số đã có trong từng toán hạng cũng có thể lộ rõ ở kết quả nhỏ. Đây là lý do các bài toán số cần xem xét **độ ổn định số học (*numerical stability*)** ngoài việc chọn `float` hay `double`.

## 8. So sánh hai số `double`: khi nào dùng `==`?

`==` là phép so sánh chính xác theo ngữ nghĩa dấu phẩy động, không áp dụng “ngưỡng gần bằng” tự động:

```java
System.out.println(0.1 + 0.2 == 0.3); // false
```

Nếu hai phép tính độc lập phải tạo **đúng một giá trị bit**, `==` có thể phù hợp. Nhưng nếu mục tiêu là “hai kết quả số học đủ gần”, có thể dùng ngưỡng sai số được thiết kế theo miền dữ liệu.

Một hàm so sánh cho **hai giá trị hữu hạn**:

```java
static boolean approximatelyEqual(double a, double b,
                                  double absTol, double relTol) {
    double diff = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return diff <= Math.max(absTol, relTol * scale);
}
```

Method này là **đoạn minh họa bên trong class**, giả định `a`, `b` hữu hạn và `absTol`/`relTol` không âm; ứng dụng cần xử lý thêm `NaN`, vô cực, và tình huống trung gian bị tràn khi trừ hoặc tính ngưỡng. Không có một ngưỡng cố định tốt cho mọi ứng dụng.

Ví dụ ngưỡng tương đối thường hợp lý với số lớn, còn ngưỡng tuyệt đối có thể hữu ích gần 0. Với các bài toán tiền tệ, lựa chọn thường không phải “`double` + epsilon”, mà là **`BigDecimal`** hoặc số nguyên đơn vị nhỏ nhất kèm kiểm tra tràn.

### Các giá trị đặc biệt

- `Double.NaN == Double.NaN` cho `false`; `Double.isNaN` dùng kiểm tra NaN.
- `Double.POSITIVE_INFINITY`/`NEGATIVE_INFINITY` cần được xử lý theo miền dữ liệu; phép tính có vô cực không có cùng ý nghĩa với phép đo hữu hạn.
- `0.0 == -0.0` cho `true`, nhưng biểu diễn bit và một số phép toán có thể phân biệt dấu của zero.
- `Double.compare` cung cấp cách so sánh thứ tự theo quy tắc Java, khác với ngữ nghĩa so sánh số học thông thường ở NaN và zero có dấu.

Đối với khóa map, sort, serialization hoặc kiểm tra bit chính xác, cần chọn quy tắc so sánh phù hợp, không tự thay tất cả `==` bằng một công thức epsilon.

## 9. `float` so với `double`: chọn kiểu theo độ chính xác thực sự

`double` thường là lựa chọn mặc định cho tính toán số thực trong Java. Literal `0.1` có kiểu `double`, literal `0.1f` có kiểu `float`:

```java
double d = 0.1;
float f = 0.1f;
// float invalid = 0.1; // lỗi: double literal không tự narrowing sang float
```

`double` có độ chính xác phần trị cao hơn, nhưng vẫn **không đại diện cho số học thập phân chính xác**.

Với đồ họa, dữ liệu sensor, học máy hoặc tập hợp lớn mà nhu cầu precision cho phép, `float` có thể hợp lý về bộ nhớ và băng thông. Với mô phỏng/tính toán cần độ chính xác tương đối cao hơn, `double` thường phù hợp. Đối với giá tiền, lãi, thuế hoặc phép tính tài chính phải đúng quy tắc thập phân, dùng `BigDecimal` với `RoundingMode` phù hợp thay vì dựa trên độ chính xác của `double`.

**Đừng dùng “số chữ số in ra” làm thước đo duy nhất.** Cần xác định sai số tuyệt đối, sai số tương đối, giá trị lớn/nhỏ nhất, điều kiện tính toán, và cách người dùng sẽ sử dụng kết quả.

## 10. Chương trình Java 17+ hoàn chỉnh và output có thể kiểm chứng

Lưu nội dung sau thành **`BinaryPrecisionDemo.java`**:

```java
import java.math.BigDecimal;

public class BinaryPrecisionDemo {
    public static void main(String[] args) {
        System.out.println("floatBits=" + Float.SIZE);
        System.out.println("doubleBits=" + Double.SIZE);

        System.out.println("exactHalf=" + (0.5 + 0.25));
        System.out.println("decimalSum=" + (0.1 + 0.2));
        System.out.println("decimalEqual=" + (0.1 + 0.2 == 0.3));

        System.out.println("floatUlpOne=" + Math.ulp(1.0f));
        System.out.println("doubleUlpOne=" + Math.ulp(1.0));
        System.out.println("nextDouble=" + Math.nextUp(1.0));

        int bigInt = 16_777_217;
        float roundedFloat = bigInt;
        System.out.println("intViaFloat=" + (int) roundedFloat);

        long bigLong = 9_007_199_254_740_993L;
        double roundedDouble = bigLong;
        System.out.println("longViaDouble=" + (long) roundedDouble);
        System.out.println("longEqualsDouble=" + (bigLong == roundedDouble));

        double d = 0.1;
        System.out.println("shortDecimal=" + Double.toString(d));
        System.out.println("binaryAsDecimal=" + new BigDecimal(d));
        System.out.println("decimalFromString=" + new BigDecimal("0.1"));
        System.out.println("decimalValueOf=" + BigDecimal.valueOf(d));

        String encoded = Double.toString(Math.PI);
        double recovered = Double.parseDouble(encoded);
        System.out.println("roundTrip=" +
                (Double.doubleToRawLongBits(recovered) ==
                 Double.doubleToRawLongBits(Math.PI)));

        double tenTimes = 0.0;
        for (int i = 0; i < 10; i++) {
            tenTimes += 0.1;
        }
        System.out.println("tenTimes=" + tenTimes);
        System.out.println("lostUnit=" + ((1e16 + 1.0) - 1e16));

        System.out.println("nanSelfEqual=" + (Double.NaN == Double.NaN));
        System.out.println("signedZeroEqual=" + (0.0 == -0.0));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BinaryPrecisionDemo.java
java BinaryPrecisionDemo
```

Đầu ra:

```text
floatBits=32
doubleBits=64
exactHalf=0.75
decimalSum=0.30000000000000004
decimalEqual=false
floatUlpOne=1.1920929E-7
doubleUlpOne=2.220446049250313E-16
nextDouble=1.0000000000000002
intViaFloat=16777216
longViaDouble=9007199254740992
longEqualsDouble=true
shortDecimal=0.1
binaryAsDecimal=0.1000000000000000055511151231257827021181583404541015625
decimalFromString=0.1
decimalValueOf=0.1
roundTrip=true
tenTimes=0.9999999999999999
lostUnit=0.0
nanSelfEqual=false
signedZeroEqual=true
```

Điểm bất ngờ là `longEqualsDouble=true`: trong phép so sánh `long == double`, `long` được widening sang `double` và làm tròn, nên so sánh có thể cho `true` dù `long` ban đầu không được giữ nguyên khi chuyển đổi. Không nên dùng so sánh giữa `long` lớn và `double` để xác minh ID bằng nhau.

## 11. Các lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`double` có 15 chữ số sau dấu phẩy.” | Nó có **53 bit phần trị**, tương đương khoảng 15–16 **chữ số thập phân có nghĩa** cho số chuẩn hóa; không cố định theo số chữ số sau dấu phẩy. |
| “9 chữ số với `float`, 17 chữ số với `double` đều là chữ số toán học chính xác.” | 9/17 là giới hạn cho **round-trip nhị phân → chuỗi đủ chính xác → nhị phân**, không phải độ chính xác của phép đo ban đầu. |
| “Nếu Java in `0.1` thì đã lưu chính xác 0,1.” | `Double.toString` in biểu diễn ngắn đủ khôi phục cùng giá trị nhị phân, chứ không in toàn bộ số thập phân chính xác của bit lưu. |
| “`float` không thể giữ được số nguyên lớn vì tối đa chỉ ~3,4 × 10^38.” | `float` có miền **độ lớn** rộng, nhưng precision 24 bit nên nhiều số nguyên liên tiếp gần 2^24 không phân biệt được. |
| “Nâng `long` lên `double` là luôn chính xác vì 64 bit.” | `double` dùng 53 bit precision, nên `long` lớn có thể bị làm tròn. |
| “`==` luôn dùng tốt sau các phép cộng số thực.” | Có thể khác do làm tròn; chọn cách so sánh dựa trên yêu cầu của bài toán. |
| “Cộng mười lần 0,1 chắc chắn ra 1,0.” | Mỗi phép cộng có thể làm tròn, thứ tự tính ảnh hưởng đến sai số. |
| “Thêm chữ số khi in ra sẽ tăng độ chính xác lưu trữ.” | Định dạng chỉ thay đổi chuỗi hiển thị; không bổ sung bit thông tin đã mất. |
| “`BigDecimal.valueOf(0.1)` giống hoàn toàn `new BigDecimal(0.1)`.” | `valueOf` dùng biểu diễn chuỗi chuẩn của `double`; constructor `double` diễn tả chính xác giá trị nhị phân đã lưu. |
| “Có thể chọn epsilon 1e-9 cho mọi phép so sánh.” | Sai số hợp lý phụ thuộc thang đo, miền dữ liệu, sai số phép đo và thuật toán; cần chính sách cụ thể. |

### Checklist thực hành

1. **Chọn kiểu theo độ chính xác, không chỉ theo độ lớn.** `float` 24 bit, `double` 53 bit significand; cần thập phân chính xác thì cân nhắc `BigDecimal`.
2. **Phân biệt precision và round-trip:** khoảng 6–7/15–16 chữ số có nghĩa là hướng dẫn độ chính xác; 9/17 chữ số đủ để lưu chuỗi round-trip của mọi giá trị hữu hạn tương ứng.
3. **Đừng đếm chữ số sau dấu chấm:** sai số tuyệt đối và khoảng cách ULP thay đổi theo độ lớn.
4. **Kiểm tra phép cộng/trừ/multiplication nhiều bước:** sai số có thể tích lũy hoặc khuếch đại do mất chữ số có nghĩa; xem tính ổn định của thuật toán.
5. **Không mặc định dùng `==` cho kết quả số học gần đúng:** xác định miền dữ liệu, ngưỡng và cách xử lý NaN/vô cực phù hợp.
6. **Khi lưu và phục hồi bit số thực:** dùng `Float.toString`/`Double.toString` và parse tương ứng; khi cần giá trị decimal toán học chính xác, đừng đi vòng qua `double`.

**Ghi nhớ:** `float` và `double` lưu một lưới giá trị **nhị phân hữu hạn**. Quy tắc 6–9 hoặc 15–17 chữ số chỉ có nghĩa khi nói rõ mục tiêu: **độ chính xác của phép tính** hay **độ dài chuỗi cần để round-trip giá trị đang lưu**. Hiểu khác biệt này giúp tránh nhầm các chữ số hiển thị với độ tin cậy thực sự của dữ liệu.