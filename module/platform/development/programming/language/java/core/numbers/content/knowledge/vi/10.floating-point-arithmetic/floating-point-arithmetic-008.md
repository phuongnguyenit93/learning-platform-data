# Mất thông tin khi cộng số rất nhỏ vào số rất lớn trong Java

## 1. Hiện tượng: cộng một số khác 0 nhưng kết quả không đổi

Trong toán học, nếu `a` là số hữu hạn và `b > 0` thì `a + b > a`. Tuy nhiên, đối với `float` và `double` của Java, kết quả phép cộng phải được biểu diễn bằng một số lượng **bit có nghĩa hữu hạn**, nên phép cộng một số rất nhỏ vào một số rất lớn có thể **không làm thay đổi giá trị lưu**.

```java
double big = 1e16;
double small = 1.0;

System.out.println(big + small == big); // true
System.out.println((big + small) - big); // 0.0
```

Kết quả toán học của `10^16 + 1` là `10_000_000_000_000_001`. Nhưng một giá trị `double` gần `10^16` không thể biểu diễn chính xác mọi số nguyên liên tiếp. Khi làm tròn kết quả phép cộng về giá trị `double` gần nhất, `big + 1.0` trở thành **chính `big`**.

Hiện tượng này thường gọi là **absorption** (số hạng nhỏ bị “nuốt mất”), hoặc **loss of significance** khi xét việc đóng góp của số hạng nhỏ không còn thể hiện trong kết quả. Nó khác với tràn số nguyên (*integer overflow*) và cũng không cần tạo ra `Infinity`/`NaN`.

Điều cần nhớ ngay:

- `double` có miền độ lớn rất rộng nhưng **không có độ chính xác vô hạn**.
- Độ chính xác phụ thuộc **khoảng cách giữa những số có thể biểu diễn** quanh giá trị hiện tại, không chỉ giá trị tuyệt đối của số được cộng.
- Số hạng nhỏ vẫn là một số hợp lệ, khác `0`. Nó bị mất do **làm tròn kết quả phép toán**.
- Chuyển kết quả đã làm tròn sang kiểu khác hoặc định dạng in ra nhiều chữ số **không khôi phục** phần thông tin đã mất.

## 2. Vì sao số rất lớn lại có bước nhảy giữa các giá trị?

Một `double` thông thường tuân theo định dạng dấu phẩy động nhị phân 64 bit, với **53 bit chính xác của phần trị** (*significand*, kể cả bit dẫn đầu ngầm đối với số chuẩn hóa). `float` có **24 bit chính xác của phần trị**.

Với số chuẩn hóa trong khoảng `2^e <= |x| < 2^(e+1)`, khoảng cách giữa những giá trị nhị phân kề nhau trong cùng miền lũy thừa hai là:

```text
ULP(double) = 2^(e - 52)
ULP(float)  = 2^(e - 23)
```

Trong đó **ULP** (*unit in the last place*) là đơn vị ở vị trí bit có nghĩa thấp nhất tại độ lớn đang xét. Khoảng cách thay đổi theo số mũ; càng xa 0 thì những giá trị dấu phẩy động có thể biểu diễn càng thưa.

Ví dụ:

| Độ lớn của giá trị | Khoảng cách gần đó của `double` | Ý nghĩa |
| --- | ---: | --- |
| `1.0` | `2^-52`, khoảng `2.22e-16` ở phía trên | Có thể biểu diễn những thay đổi rất nhỏ gần 1 |
| `2^52` | `1.0` | Mọi số nguyên liên tiếp trong vùng này còn có thể phân biệt |
| `2^53` | `2.0` | Số nguyên kế tiếp `2^53+1` không còn biểu diễn riêng |
| `1e16` | `2.0` | Cộng `1.0` có thể làm tròn về chính số cũ |
| `2^54` | `4.0` | Phải thay đổi lớn hơn mới chắc chắn có giá trị khác |

Bảng xét các giá trị chuẩn hóa và bước nhảy về phía số lớn hơn tại các mốc; ở **ranh giới lũy thừa của hai**, khoảng cách về phía dưới có thể nhỏ hơn khoảng cách về phía trên. Không nên hiểu một ULP là hằng số duy nhất cho mọi giá trị `double`.

Java cung cấp API kiểm tra ngay:

```java
double x = 1e16;
System.out.println(Math.ulp(x));          // 2.0
System.out.println(Math.nextUp(x) - x);   // 2.0
```

`Math.ulp(x)` trả về kích thước ULP theo định nghĩa Java; `Math.nextUp(x)` trả về giá trị `double` kế tiếp lớn hơn `x`. Nhờ đó có thể nhìn thấy khoảng cách biểu diễn mà không phải tự đọc từng bit IEEE 754.

## 3. Cộng `1.0` vào `1e16`: phân tích từng bước

Ở gần `1e16`, các giá trị `double` kề nhau theo chiều tăng là:

```text
10000000000000000   (big)
10000000000000002   (Math.nextUp(big))
10000000000000004
...
```

Giá trị toán học `10000000000000001` nằm **đúng giữa** hai giá trị đầu tiên. Java dùng quy tắc làm tròn mặc định của phép toán dấu phẩy động: **gần nhất, trường hợp hòa chọn bit cuối chẵn** (*round to nearest, ties to even*). Trong ví dụ này, giá trị được chọn là `10000000000000000`, nên:

```java
double big = 1e16;

System.out.println(big + 1.0 == big); // true
System.out.println(big + 2.0 == big); // false
System.out.println(big + 2.0 - big);  // 2.0
```

Không phải cứ số hạng nhỏ hơn một ULP thì kết quả **luôn** bị bỏ qua. Kết quả phụ thuộc khoảng cách tới hai giá trị biểu diễn gần nhất và quy tắc làm tròn. Ví dụ, gần `big`, một số hạng có độ lớn **nhỏ hơn một nửa khoảng cách lên số kế tiếp** sẽ không đổi kết quả khi làm tròn gần nhất; còn trường hợp đúng giữa cần áp dụng quy tắc xử lý hòa.

Trong mô hình tính toán, trước phép cộng phần trị của hai số phải được **căn chỉnh số mũ**. Khi một số có số mũ lớn hơn hẳn số còn lại, các bit của số nhỏ bị dịch tương đối rất xa. Kết quả toán học có thể chứa những bit thấp không còn đủ chỗ trong 53 bit có nghĩa của `double`; quá trình làm tròn loại bỏ đóng góp đó. Đây là cách hiểu trực quan của hiện tượng absorption.

**Chú ý:** Cả `big` lẫn `1.0` trong ví dụ đều biểu diễn **chính xác** bằng `double`. Phần thông tin bị mất ở **kết quả phép cộng**, khác với trường hợp literal `0.1` đã cần xấp xỉ ngay khi được lưu.

## 4. `float` gặp hiện tượng này sớm hơn `double`

Vì phần trị của `float` chỉ có 24 bit chính xác, nó không phân biệt được mọi số nguyên liên tiếp khi độ lớn vượt `2^24`.

```java
float big = 16_777_216.0f; // 2^24
float small = 1.0f;

System.out.println(big + small == big); // true
System.out.println(Math.ulp(big));      // 2.0
```

Trong khi đó, `double` có 53 bit chính xác, nên cùng phép cộng với `16_777_216.0` và `1.0` vẫn giữ được kết quả chính xác:

```java
double big = 16_777_216.0;
System.out.println(big + 1.0); // 1.6777217E7
```

`1.6777217E7` là cách `Double.toString` in số `16777217.0` ở ký pháp khoa học trong ví dụ này. Việc chọn `double` thay `float` **giảm** nguy cơ mất số hạng nhỏ tại một độ lớn nhất định, nhưng không giải quyết bài toán vô hạn: ở độ lớn đủ cao, `double` cũng phải làm tròn.

| Kiểu | Số bit có nghĩa | Mốc mà phép cộng 1 có thể bị mất |
| --- | ---: | --- |
| `float` | 24 | `2^24 + 1` không có biểu diễn `float` riêng; `2^24f + 1f` làm tròn về `2^24f` |
| `double` | 53 | `2^53 + 1` không có biểu diễn `double` riêng; `2^53 + 1.0` làm tròn về `2^53` |

Vì vậy, câu hỏi quan trọng không chỉ là “số của tôi có nằm trong miền `float`/`double` không?” mà là **“ở độ lớn đó, kiểu đang dùng còn phân biệt được bước thay đổi mà tôi quan tâm không?”**

## 5. Mất số hạng nhỏ dẫn đến mất tính kết hợp của phép cộng

Trong toán học, phép cộng số thực có tính kết hợp:

```text
(a + b) + c = a + (b + c)
```

Đối với số học dấu phẩy động, kết quả trung gian được làm tròn, nên biểu thức có cách nhóm khác nhau có thể cho kết quả khác nhau:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double leftGrouped = (a + b) + c;
double rightGrouped = a + (b + c);

System.out.println(leftGrouped);  // 1.0
System.out.println(rightGrouped); // 0.0
```

Giải thích:

1. `(a + b) + c`: hai số lớn trái dấu `1e16` và `-1e16` triệt tiêu **chính xác** thành `0.0`, rồi cộng `1.0` cho `1.0`.
2. `a + (b + c)`: trước hết tính `-1e16 + 1.0`; số `1.0` quá nhỏ so với khoảng cách giữa các giá trị biểu diễn ở độ lớn đó, nên kết quả được làm tròn về `-1e16`. Sau đó cộng `a` cho `0.0`.

Hai kết quả khác nhau dù các toán hạng là cùng ba giá trị. Đây là lý do **thứ tự cộng và cách nhóm phép toán có thể ảnh hưởng đến kết quả** trong tính toán dấu phẩy động.

Trong những thuật toán thống kê, tổng số đo, mô phỏng và phép tính số học, đừng tự ý dùng các phép biến đổi đại số trên số thực máy như thể mọi phép cộng đều chính xác. Trình biên dịch Java tuân thủ những quy tắc đánh giá dấu phẩy động của ngôn ngữ; tuy nhiên, **doanh nghiệp/người viết thuật toán** vẫn phải lựa chọn công thức và thứ tự xử lý phù hợp với yêu cầu độ chính xác.

## 6. Cộng dồn nhiều số hạng nhỏ vào tổng rất lớn

Một ví dụ thực tế: ban đầu có tổng `1e16`, sau đó cộng `1.0` mười lần.

```java
double total = 1e16;

for (int i = 0; i < 10; i++) {
    total += 1.0;
}

System.out.println(total - 1e16); // 0.0
```

Toán học yêu cầu tổng tăng thêm `10`. Nhưng mỗi lần cộng `1.0`, phép cộng được làm tròn ngay về `1e16`, nên tổng **không tích lũy được bất kỳ đơn vị nào**.

Khác biệt quan trọng: nếu tạo tổng các phần nhỏ **trước khi** cộng vào số lớn, kết quả có thể được giữ:

```java
double big = 1e16;
double increments = 0.0;
for (int i = 0; i < 10; i++) {
    increments += 1.0;
}

System.out.println((big + increments) - big); // 10.0
```

Khi đó `increments` bằng `10.0`, lớn hơn nhiều so với bước biểu diễn `2.0` gần `big`, nên lần cộng cuối giữ được thông tin.

Nhưng **không có cách sắp xếp thứ tự cộng đơn giản nào đúng nhất cho mọi dữ liệu**. Ví dụ cộng các số âm/dương lớn có thể gây *catastrophic cancellation* (mất độ chính xác tương đối khi hai số gần bằng nhau bị trừ/triệt tiêu). Việc nhóm các số nhỏ trước chỉ là một kỹ thuật hữu ích trong những trường hợp xác định được cấu trúc dữ liệu.

## 7. Dùng thuật toán cộng có bù sai số: Kahan summation

Khi phải cộng nhiều giá trị dấu phẩy động, một kỹ thuật là **Kahan compensated summation**. Nó giữ thêm một biến bù để theo dõi phần nhỏ bị mất trong phép cộng trước và có cơ hội đưa phần đó vào các phép cộng tiếp theo.

```java
static double kahanAddOnTop(double start, double[] values) {
    double sum = start;
    double compensation = 0.0;

    for (double value : values) {
        double adjusted = value - compensation;
        double updated = sum + adjusted;
        compensation = (updated - sum) - adjusted;
        sum = updated;
    }

    return sum;
}
```

Đoạn này là phương thức minh họa cần đặt vào một lớp Java để chạy. Ba bước bên trong vòng lặp:

1. `adjusted = value - compensation` điều chỉnh giá trị sắp cộng bằng phần dư đã ghi nhận.
2. `updated = sum + adjusted` tạo tổng mới (vẫn có thể bị làm tròn).
3. `compensation = (updated - sum) - adjusted` ghi lại phần bị mất trong phép cộng vừa rồi để điều chỉnh về sau.

Ví dụ khi cộng mười số `1.0` vào `1e16`, thuật toán trên có thể giữ được mức tăng tổng cộng `10.0`, trong khi cộng ngây thơ từng lần cho mức tăng `0.0`.

**Giới hạn của Kahan:**

- Nó giúp giảm sai số tích lũy trong nhiều bài toán nhưng **không biến `double` thành số chính xác vô hạn**.
- Giá trị `sum` trả về vẫn là một `double`. Nếu kết quả toán học cuối cùng nằm giữa hai giá trị `double` mà không thể biểu diễn, hàm vẫn phải làm tròn.
- Với một phép cộng duy nhất `1e16 + 1.0`, biến bù có thể ghi nhận phần nhỏ cho **bước tiếp theo**, nhưng trả về mỗi `sum` vẫn không biểu diễn được `1e16 + 1`.
- Các thuật toán thay thế (Neumaier, pairwise summation, phép toán đa độ chính xác) phù hợp trong những bối cảnh khác nhau; cần đo chất lượng và chi phí theo dữ liệu thực.

Nếu một API đòi hỏi kết quả không sai một đơn vị, việc dùng một thuật toán dấu phẩy động ổn định hơn **chưa chắc** đáp ứng được hợp đồng. Khi đó cần chọn cách biểu diễn chính xác phù hợp với miền giá trị.

## 8. Khi nào dùng `Math.ulp`, `Math.nextUp` và ngưỡng sai số?

`Math.ulp(x)` đo **độ phân giải xấp xỉ tại độ lớn của `x`**, rất hữu ích để phát hiện một số hạng nhỏ có nguy cơ bị nuốt.

```java
double big = 1e16;
double step = Math.ulp(big);

System.out.println(step);               // 2.0
System.out.println(big + step == big);  // false
```

Tuy nhiên, không nên áp dụng mù quáng quy tắc **“cứ số nhỏ hơn ULP thì chắc chắn bằng 0”**. Một số hạng nằm giữa khoảng cách biểu diễn có thể được làm tròn theo hướng tăng/giảm; việc xử lý hòa cũng phụ thuộc bit cuối của phần trị. Kỹ thuật dùng ULP là để **đánh giá độ phân giải**, không phải thay cho phân tích sai số đầy đủ.

Khi so sánh hai kết quả số thực gần nhau, có thể cân nhắc ngưỡng tuyệt đối và tương đối:

```java
static boolean nearlyEqual(double a, double b,
                           double absTol, double relTol) {
    if (a == b) {
        return true; // Kể cả hai vô cực cùng dấu.
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false; // Bao gồm NaN và vô cực không cùng giá trị.
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(absTol, relTol * scale);
}
```

Đây là **một chính sách so sánh gần đúng**, không phải cách phục hồi giá trị đã mất. Ví dụ `big + 1.0 == big` là `true` ngay ở mức biểu diễn; `nearlyEqual` không thể biết rằng người dùng từng mong có thêm `1.0`.

Ngưỡng phải phù hợp **đơn vị đo, độ lớn dữ liệu và yêu cầu nghiệp vụ**. Công thức trên là minh họa đơn giản; dữ liệu cực lớn/cực nhỏ còn cần xét overflow/underflow trong tính ngưỡng, `NaN` và `Infinity`. Không dùng một epsilon tùy tiện cho tất cả ứng dụng.

## 9. Định dạng số và chuyển kiểu không khôi phục thông tin

Một số người thử in nhiều chữ số hơn:

```java
double big = 1e16;
double rounded = big + 1.0;
System.out.printf("%.0f%n", rounded); // 10000000000000000
```

Lệnh định dạng chỉ in giá trị **đã được tính và làm tròn**. Không có thông tin nào còn lại trong `rounded` để biết phép cộng ban đầu có số `1.0`.

Tương tự, gán kết quả sang `BigDecimal` **sau** phép tính cũng quá muộn:

```java
import java.math.BigDecimal;

double wrong = 1e16 + 1.0;
BigDecimal after = BigDecimal.valueOf(wrong);
System.out.println(after.toPlainString()); // 10000000000000000
```

`BigDecimal.valueOf(double)` dùng cách chuyển `double` đã có thành chuỗi rồi tạo đối tượng thập phân; nó không lưu được chữ số `1` vốn đã biến mất ở phép cộng `double`.

Muốn giữ giá trị thập phân chính xác, chuyển dữ liệu sang biểu diễn chính xác **trước phép toán**:

```java
BigDecimal big = new BigDecimal("10000000000000000");
BigDecimal one = BigDecimal.ONE;
BigDecimal exact = big.add(one);

System.out.println(exact); // 10000000000000001
```

`BigDecimal` giúp biểu diễn các số thập phân với độ chính xác tùy ý trong giới hạn tài nguyên; các phép chia có khai triển vô hạn vẫn có thể cần `MathContext`/`RoundingMode`. Nó phù hợp khi yêu cầu nghiệp vụ cần chính xác từng chữ số thập phân, nhưng không có nghĩa là nên thay mọi phép tính số học khoa học bằng `BigDecimal`.

### Dùng số nguyên khi bản chất dữ liệu là số đếm

Nếu đang đếm sản phẩm, số lượng giao dịch hoặc đơn vị tiền nhỏ nhất, cách lưu bằng `int`/`long` có thể phù hợp hơn số thực:

```java
long base = 10_000_000_000_000_000L;
long exact = base + 1L;
System.out.println(exact); // 10000000000000001
```

`long` có thể giữ chính xác số nguyên này vì nằm trong miền 64 bit; **nhưng `long` vẫn có nguy cơ tràn** nếu vượt giới hạn. Khi vượt cả `long`, dùng `BigInteger`. Phân biệt “kiểu nguyên chính xác trong miền” với “số thực nhị phân xấp xỉ ở độ lớn lớn” giúp chọn mô hình dữ liệu đúng.

## 10. Liên hệ với hiện tượng mất chính xác do trừ hai số gần nhau

**Absorption** và **catastrophic cancellation** đều liên quan độ chính xác dấu phẩy động, nhưng không phải một hiện tượng:

- **Absorption:** cộng một số hạng quá nhỏ vào một số rất lớn; phần đóng góp nhỏ không thể hiện trong kết quả làm tròn. Ví dụ `1e16 + 1.0 == 1e16`.
- **Cancellation:** lấy hiệu hai giá trị gần nhau; những chữ số có nghĩa chung triệt tiêu, và sai số đã tồn tại trong các toán hạng có thể chiếm tỷ lệ lớn trong hiệu. Ví dụ nếu hai số đã được làm tròn thành cùng mẫu bit, phép trừ cho `0.0` dù hiệu giữa hai giá trị lý tưởng khác 0.

Ví dụ:

```java
double a = 1e16 + 1.0; // Thành 1e16 ngay lúc cộng.
double b = 1e16;
System.out.println(a - b); // 0.0
```

Nếu `a` ban đầu được thiết kế để chứa giá trị toán học `1e16 + 1`, phần `1` đã mất **trước** khi thực hiện phép trừ. Thay công thức `a - b` hoặc ép kết quả sang `long` không hồi phục thông tin; phải chọn biểu diễn và thuật toán phù hợp từ bước tạo toán hạng.

## 11. Ví dụ Java 17+ độc lập và kết quả

Tạo tệp **`TinyPlusHugeDemo.java`**:

```java
import java.math.BigDecimal;

public class TinyPlusHugeDemo {
    public static void main(String[] args) {
        double big = 1e16;

        System.out.println("ULP at 1e16 = " + Math.ulp(big));
        System.out.println("next gap = " + (Math.nextUp(big) - big));
        System.out.println("big + 1 == big = " + (big + 1.0 == big));
        System.out.println("big + 2 == big = " + (big + 2.0 == big));

        float floatBig = 16_777_216f;
        System.out.println("float big + 1 == big = "
                + (floatBig + 1.0f == floatBig));

        double a = 1e16;
        double b = -1e16;
        double c = 1.0;
        System.out.println("(a+b)+c = " + ((a + b) + c));
        System.out.println("a+(b+c) = " + (a + (b + c)));

        double naive = big;
        double kahan = big;
        double compensation = 0.0;

        for (int i = 0; i < 10; i++) {
            naive += 1.0;

            double adjusted = 1.0 - compensation;
            double updated = kahan + adjusted;
            compensation = (updated - kahan) - adjusted;
            kahan = updated;
        }

        System.out.println("naive delta = " + (naive - big));
        System.out.println("Kahan delta = " + (kahan - big));

        BigDecimal exact = new BigDecimal("10000000000000000")
                .add(BigDecimal.ONE);
        System.out.println("BigDecimal exact = " + exact);

        long integerExact = 10_000_000_000_000_000L + 1L;
        System.out.println("long exact = " + integerExact);
    }
}
```

Biên dịch và chạy:

```bash
javac TinyPlusHugeDemo.java
java TinyPlusHugeDemo
```

Kết quả:

```text
ULP at 1e16 = 2.0
next gap = 2.0
big + 1 == big = true
big + 2 == big = false
float big + 1 == big = true
(a+b)+c = 1.0
a+(b+c) = 0.0
naive delta = 0.0
Kahan delta = 10.0
BigDecimal exact = 10000000000000001
long exact = 10000000000000001
```

Ví dụ chứng minh hai khía cạnh: giá trị `1.0` có thể **bị mất trong từng phép cộng `double`**, nhưng thuật toán tổng có bù có thể thu hồi các phần bị mất ở **các lần cộng sau**. Dữ liệu cần chính xác tuyệt đối từng đơn vị nên dùng số nguyên đủ rộng hoặc `BigDecimal`/`BigInteger` thay vì mong số thực nhị phân tự giải quyết mọi trường hợp.

## 12. Những hiểu lầm và lỗi phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| “Số nhỏ là `1.0` nên không thể tự biến thành 0.” | Số hạng không biến thành `0`; **kết quả cộng sau làm tròn** có thể trùng số lớn ban đầu. |
| “Chỉ khi phép toán tràn `Infinity` mới mất dữ liệu.” | Mất độ phân giải diễn ra với giá trị hoàn toàn hữu hạn như `1e16`. |
| “`double` giữ mọi số nguyên nếu chúng nhỏ hơn `Double.MAX_VALUE`.” | Miền độ lớn và số bit chính xác là hai khái niệm khác nhau. |
| “Cứ tăng từ `float` sang `double` là hết lỗi.” | `double` có độ phân giải tốt hơn nhưng vẫn hữu hạn. |
| “Cộng theo thứ tự nào cũng cho cùng kết quả.” | Phép cộng dấu phẩy động không đảm bảo tính kết hợp như số học thực lý tưởng. |
| “Kahan đảm bảo kết quả chính xác tuyệt đối.” | Nó giảm sai số cho nhiều dãy cộng, nhưng kết quả `double` vẫn phải làm tròn. |
| “Một epsilon cố định giải quyết mọi vấn đề.” | Ngưỡng gần đúng phụ thuộc độ lớn, đơn vị và tính đúng đắn nghiệp vụ. |
| “In ra thêm chữ số sẽ lấy lại được số nhỏ.” | Định dạng không khôi phục thông tin đã bị mất từ phép toán. |
| “Đổi sang `BigDecimal` sau phép cộng sẽ sửa được.” | Muốn tính thập phân chính xác, phải chuyển **trước** phép tính gây mất thông tin. |
| “Cứ dùng `long` thay số thực trong mọi trường hợp.” | `long` hữu hạn và chỉ biểu diễn số nguyên; số đo thực có thể cần thuật toán số ổn định. |

## 13. Cách chọn phương pháp xử lý

Trước khi cộng những giá trị rất chênh lệch, hãy đặt các câu hỏi:

1. **Độ lớn của tổng là bao nhiêu?** Ước lượng `Math.ulp(total)` ở những vùng thường gặp.
2. **Số hạng nhỏ nhất cần giữ là bao nhiêu?** Nếu nó nhỏ hơn khả năng phân giải gần tổng, phải xem xét cách tính khác.
3. **Có cộng nhiều số hạng không?** Nếu có, thứ tự cộng hoặc thuật toán Kahan/pairwise/Neumaier có thể giảm sai số tích lũy.
4. **Có các số lớn trái dấu dễ triệt tiêu nhau không?** Xem xét sai số tương đối và cấu trúc công thức, không chỉ tổng cuối.
5. **Yêu cầu là chính xác tuyệt đối hay chấp nhận sai số?** Số đếm chính xác có thể dùng `long`/`BigInteger`; thập phân chính xác dùng `BigDecimal` với quy tắc làm tròn phù hợp; mô phỏng/đo lường có thể dùng `double` cùng phân tích sai số.

**Kết luận:** Khi cộng số rất nhỏ vào số rất lớn, số hạng nhỏ có thể bị mất vì khoảng cách giữa các giá trị `float`/`double` có thể biểu diễn **tăng theo độ lớn của số**. Hiện tượng này làm tổng phụ thuộc thứ tự tính, gây mất đóng góp của số hạng nhỏ và có thể ảnh hưởng đến thống kê hoặc điều kiện so sánh. Hãy hiểu ULP, chọn thứ tự/thuật toán tổng phù hợp và sử dụng kiểu biểu diễn chính xác **trước khi tính** nếu bài toán không chấp nhận sai số.

**Tài liệu tham khảo:** [Java Language Specification §4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3), [JLS §15.4 — FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4), [Math.ulp API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#ulp(double)), [Math.nextUp API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#nextUp(double)), [BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
