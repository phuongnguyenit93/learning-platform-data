# Vì sao phép toán dấu phẩy động không bảo đảm tính kết hợp của số thực toán học trong Java

> **Java core – numbers · Phép toán dấu phẩy động**  
> **Mục tiêu:** Hiểu chính xác vì sao các phép cộng/nhân trên `float` và `double` có thể cho kết quả khác nhau khi đổi ngoặc; phân biệt tính kết hợp của đại số với cách nhóm cú pháp và thứ tự đánh giá trong Java; biết cách thiết kế phép tính tổng ổn định hơn, kiểm thử và xử lý sai số.

## 1. Tính kết hợp trong toán học nói gì?

Với các số thực toán học và phép cộng, phép nhân chính xác, ta có:

\[
(a+b)+c=a+(b+c)
\]
\[
(a\times b)\times c=a\times(b\times c)
\]

Đây là **tính kết hợp** (*associativity*). Nó cho phép đổi ngoặc trong một chuỗi cộng hoặc nhân số thực mà không đổi giá trị cuối cùng.

Nhưng các giá trị `float` và `double` trong Java không phải tập số thực có độ chính xác vô hạn. Chúng lưu một **tập hữu hạn các mẫu bit** của chuẩn dấu phẩy động nhị phân IEEE 754. Sau nhiều phép toán, kết quả toán học phải **làm tròn** về một giá trị mà kiểu dữ liệu biểu diễn được.

Do đó các phép toán dấu phẩy động **không được bảo đảm có tính kết hợp như phép cộng và phép nhân trên tập số thực toán học**. Đây không phải lỗi Java hay lỗi CPU: việc tính trong miền có độ chính xác hữu hạn và làm tròn ở mỗi bước chính là nguồn gốc của sự khác biệt.

Điểm cần tránh: **phép trừ và phép chia trên số thực toán học vốn không có tính kết hợp**, nên các ví dụ `(a-b)-c` khác `a-(b-c)` không phải bằng chứng riêng về mất tính kết hợp do IEEE 754. Ta dùng **cộng** và **nhân** để minh họa hiện tượng đúng trọng tâm.

## 2. Mô hình đúng: cộng rồi làm tròn, không phải cộng số thực vô hạn

Đối với phép toán `op`, có thể hình dung:

\[
\mathrm{fl}(a\ \mathrm{op}\ b)
 = \mathrm{round}_{\mathrm{format}}(a\ \mathrm{op}\ b)
\]

Trong đó `fl` là kết quả được biểu diễn bằng `float` hoặc `double` sau khi phép toán được làm tròn. Với các phép cộng thông thường trên các giá trị hữu hạn, Java 17+ dùng ngữ nghĩa IEEE 754 xác định; chế độ làm tròn áp dụng cho các toán tử số học tiêu chuẩn là **làm tròn đến giá trị gần nhất, hòa thì chọn bit cuối chẵn** (*round to nearest, ties to even*).

Bởi vậy hai cách nhóm tính hai chuỗi làm tròn khác nhau:

\[
\mathrm{fl}\big(\mathrm{fl}(a+b)+c\big)
\]
\[
\mathrm{fl}\big(a+\mathrm{fl}(b+c)\big)
\]

Khi `fl(a+b)` hoặc `fl(b+c)` đã khác giá trị toán học chính xác, phép toán tiếp theo không thể tự khôi phục tất cả bit bị bỏ đi. Hai chuỗi có thể cho **hai kết quả cuối cùng khác nhau**, mặc dù cả hai biểu thức đều hợp lệ và tuân thủ Java.

### Độ chính xác hữu hạn

| Kiểu | Độ rộng | Bit chính xác hiệu dụng của số normal | Khoảng chữ số thập phân có nghĩa |
| --- | ---: | ---: | --- |
| `float` | 32 | 24 bit | Khoảng 6–9 |
| `double` | 64 | 53 bit | Khoảng 15–17 |

Các bit này không được phân bổ đồng đều trên trục số thực: khoảng cách giữa các giá trị biểu diễn được thường **lớn hơn khi độ lớn của số lớn hơn**. Từ đây nảy sinh hiện tượng một số nhỏ cộng vào số rất lớn có thể **không làm thay đổi** số lớn.

## 3. Phản ví dụ kinh điển: cùng ba số, đổi ngoặc đổi kết quả

Chọn:

```java
double a = 1.0e16;  // 10^16
double b = -1.0e16; // -10^16
double c = 1.0;
```

Trên số thực toán học:

\[
(a+b)+c=(10^{16}-10^{16})+1=1
\]
\[
a+(b+c)=10^{16}+(-10^{16}+1)=1
\]

Trong `double` Java:

```java
double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);          // 1.0
System.out.println(right);         // 0.0
System.out.println(left == right); // false
```

**Vì sao vế trái ra 1.0?**

1. `a+b`: hai số có cùng độ lớn và trái dấu triệt tiêu nhau, tạo ra `0.0` chính xác.
2. Cộng tiếp `c=1.0`, được `1.0` chính xác.

**Vì sao vế phải ra 0.0?**

1. Trong `b+c`, ta thử cộng `1.0` vào `-10^16`.
2. Ở độ lớn quanh `10^16`, hai số `double` liên tiếp cách nhau **2.0**. Giá trị toán học `-10^16+1` nằm đúng giữa những giá trị có thể biểu diễn, và quy tắc *ties to even* làm tròn về `-10^16`.
3. Sau đó `a + b` trở thành `10^16 + (-10^16)`, cho `0.0`.

Có thể kiểm tra trực tiếp:

```java
System.out.println(Math.ulp(1.0e16)); // 2.0
System.out.println(-1.0e16 + 1.0 == -1.0e16); // true
```

`Math.ulp(x)` cho biết kích cỡ một đơn vị ở vị trí bit có nghĩa cuối (*unit in the last place*) quanh `x`. Ở đây độ lệch 1.0 nhỏ hơn khả năng phân giải cần để tạo ra một giá trị `double` mới quanh `10^16`.

| Phép tính | Giá trị trung gian sau làm tròn | Kết quả |
| --- | --- | --- |
| `(a+b)+c` | `a+b = 0.0` | **1.0** |
| `a+(b+c)` | `b+c = -1.0E16` | **0.0** |

**Kết luận từ phản ví dụ:** Java không bảo đảm `(a+b)+c == a+(b+c)` khi các biến là `float`/`double`. Chỉ một trường hợp hợp lệ trả khác nhau đã đủ bác bỏ giả thiết luôn có tính kết hợp.

## 4. Cách nhóm cú pháp khác thứ tự đánh giá toán hạng

Cần phân biệt ba vấn đề liên quan nhưng khác nhau:

- **Độ ưu tiên** (*precedence*): `*` gắn toán hạng chặt hơn `+`.
- **Tính kết hợp của cú pháp** (*syntactic associativity*): chuỗi `a+b+c` được nhóm theo bên trái, tức `(a+b)+c`.
- **Thứ tự đánh giá** (*evaluation order*): Java đánh giá các toán hạng theo quy tắc từ trái sang phải, bao gồm tác dụng phụ quan sát được của lời gọi phương thức.

Ví dụ:

```java
double a = 1.0e16, b = -1.0e16, c = 1.0;

double defaultGroup = a + b + c;    // (a + b) + c -> 1.0
double otherGroup   = a + (b + c);  // 0.0
```

Dấu ngoặc thứ hai **thay đổi cây phép tính**, do đó thay đổi chỗ thực hiện làm tròn. Nhưng ngoặc ở vế phải không có nghĩa Java tự ý gọi những hàm ở bên phải trước những hàm đứng bên trái.

Ví dụ:

```java
double result = first() + (second() + third());
```

Java vẫn đánh giá các toán hạng theo thứ tự: `first()`, rồi `second()`, rồi `third()` (nếu không có ngoại lệ ngắt quá trình). **Các kết quả đã nhận** được kết hợp theo dấu ngoặc: `second+third` trước, sau đó mới cộng với `first`.

Trong Java 17+, biểu thức dấu phẩy động có ngữ nghĩa **always-strict**. Compiler/JVM không được tùy tiện đổi `(a+b)+c` thành `a+(b+c)` nếu điều đó có thể đổi hành vi được Java quy định. Việc tối ưu phải bảo toàn ngữ nghĩa quan sát được; lập trình viên không được tự giả định hai cách nhóm bằng nhau để “tối ưu đại số”.

## 5. Vì sao bit thấp có thể biến mất: độ lớn, ULP và hấp thụ

Một số nguyên nhỏ có thể biểu diễn chính xác riêng lẻ, nhưng không đủ lớn để thay đổi một số `double` đã có độ lớn cao:

```java
double big = 1.0e16;
double small = 1.0;

System.out.println(big + small == big); // true
System.out.println(Math.ulp(big));      // 2.0
```

Hiện tượng này thường gọi là **hấp thụ số hạng nhỏ** (*absorption*) trong phép cộng dấu phẩy động. Không phải số 1 “không tồn tại”; nó tồn tại, nhưng khi cộng với `10^16`, kết quả toán học rơi giữa các điểm có thể biểu diễn bằng 53 bit chính xác của `double`.

Mấu chốt là **độ chính xác tương đối**, không chỉ phạm vi lớn/nhỏ của kiểu:

- `double` có thể biểu diễn các số đến gần `1.8×10^308`.
- Điều đó không có nghĩa mọi số nguyên cách nhau 1 đều biểu diễn chính xác ở gần `10^308` hay `10^16`.
- Trong miền số nguyên của `double`, mọi số nguyên đến `2^53` đều có thể biểu diễn chính xác, nhưng ngoài đó **không còn bảo đảm** khoảng cách 1.

Ở kiểu `float`, hiệu ứng đến sớm hơn:

```java
float bigFloat = 100_000_000f;
float smallFloat = 1f;

System.out.println(bigFloat + smallFloat == bigFloat); // true
System.out.println(Math.ulp(bigFloat)); // 8.0
```

Vì `float` có 24 bit chính xác hiệu dụng, độ phân giải quanh một trăm triệu là **8.0**. Tăng 1.0 không đủ để chuyển sang giá trị khác.

**Không dùng** `Float.MIN_VALUE` hoặc `Double.MIN_VALUE` như “bước giữa hai số” trên toàn trục số. Hai hằng này chỉ là số dương subnormal nhỏ nhất; bước ULP quanh 1, quanh một triệu và quanh một giá trị rất lớn là khác nhau.

## 6. Sai số do triệt tiêu: mất thông tin trước khi trừ/cộng

*Cộng hai số gần bằng nhau nhưng trái dấu* có thể tạo ra **cancellation** (*triệt tiêu*). Việc triệt tiêu **không tự nó luôn gây sai số lớn**: nếu hai toán hạng được lưu chính xác và phép cộng là chính xác, kết quả vẫn có thể đúng. Vấn đề là khi các toán hạng **đã có sai số làm tròn**, phép trừ gần bằng nhau có thể làm sai số tương đối của kết quả tăng lên.

Xét biểu thức:

```java
double a = 1.0e16;
double b = 1.0;
double c = -1.0e16;

double computed = (a + b) + c;
System.out.println(computed); // 0.0
```

Giá trị toán học mong muốn là 1, nhưng `a+b` được làm tròn về `a` rồi cộng `c` nên ra 0. **Phép cộng cuối không sai trong bản thân đầu vào đã được làm tròn**; thông tin “+1” đã bị bỏ ở bước trước.

Một cách nhóm khác:

```java
double betterForThisCase = (a + c) + b;
System.out.println(betterForThisCase); // 1.0
```

Cho bộ dữ liệu này, cộng hai số lớn trái dấu trước làm kết quả nhỏ 0 rồi mới cộng 1, giữ lại phần nhỏ. Nhưng **không có một thứ tự nhóm chung tốt nhất cho mọi dữ liệu**; việc chọn thuật toán tổng phải xét miền giá trị, dấu, điều kiện số và yêu cầu tái lập.

## 7. Nhân cũng không có bảo đảm kết hợp: overflow trung gian

Tính kết hợp toán học cho phép:

\[
(a\times b)\times c=a\times(b\times c).
\]

Tuy nhiên, trong `double`:

```java
double a = 1.0e308;
double b = 2.0;
double c = 0.5;

System.out.println((a * b) * c); // Infinity
System.out.println(a * (b * c)); // 1.0E308
```

Phân tích:

1. Vế trái tính `a*b = 2×10^308`, vượt giá trị hữu hạn lớn nhất của `double`, nên sau làm tròn thành `+Infinity`. Nhân `Infinity*0.5` vẫn là `Infinity`.
2. Vế phải tính `b*c = 1.0` trước, rồi `a*1.0 = 1.0E308`, vẫn hữu hạn.

Dưới số thực toán học, hai vế đều bằng `10^308`. Với số dấu phẩy động có giới hạn exponent, **đổi ngoặc có thể quyết định có overflow trung gian hay không**.

Không nên suy ra rằng luôn phải nhân các toán hạng nhỏ trước; trong bài toán khác, phương án đó có thể gây **underflow**, tăng sai số hoặc thay đổi nhu cầu xử lý các giá trị đặc biệt.

## 8. Underflow trung gian cũng làm kết quả khác nhau

Ngược lại với overflow, kết quả trung gian quá gần 0 có thể bị làm tròn về 0 dù kết quả toán học cuối sau nhân các hệ số tiếp theo khác 0.

```java
double tiny = Double.MIN_VALUE;
double half = 0.5;
double two = 2.0;

System.out.println((tiny * half) * two); // 0.0
System.out.println(tiny * (half * two)); // 4.9E-324
```

`Double.MIN_VALUE` là số dương `double` nhỏ nhất khác 0, tương đương `2^-1074`. Giá trị toán học `tiny*0.5 = 2^-1075` nằm giữa 0 và giá trị dương nhỏ nhất có thể biểu diễn. Theo quy tắc làm tròn đến gần nhất, hòa thì chọn chẵn, nó làm tròn về `+0.0`. Nhân tiếp với 2 không thể phục hồi giá trị đã mất.

Vế phải tính `0.5*2.0=1.0` trước, nên `tiny*1.0` vẫn bằng `Double.MIN_VALUE`.

Đây là **underflow ở bước trung gian**, không phải lỗi cú pháp hay chương trình ném ngoại lệ. Phép toán dấu phẩy động với underflow/overflow thường tạo giá trị theo IEEE 754 thay vì ném `ArithmeticException` như chia nguyên cho 0.

## 9. Biểu diễn thập phân không chính xác là một nguyên nhân liên quan, nhưng không phải nguyên nhân duy nhất

`0.1` không có biểu diễn nhị phân hữu hạn. Khi gõ:

```java
double tenth = 0.1;
System.out.println(Double.toHexString(tenth));
// 0x1.999999999999ap-4
```

Java lưu **giá trị `double` gần 0.1**, không phải chính xác phân số toán học 1/10. Các phép toán tiếp theo dùng giá trị đã được lưu đó, rồi lại làm tròn trung gian.

Tuy nhiên, ví dụ phản chứng chính ở phần 3 **không cần** literal `0.1`: các giá trị `10^16`, `-10^16` và `1` đều có thể biểu diễn chính xác bằng `double`, nhưng **phép cộng trung gian** vẫn gây mất số hạng nhỏ. Vì vậy không đúng nếu kết luận rằng chỉ các số thập phân có biểu diễn nhị phân vô hạn mới bị ảnh hưởng.

Một ví dụ dễ thấy về làm tròn:

```java
System.out.println(0.1 + 0.2);        // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

Đây là ví dụ về sai số biểu diễn và cộng/làm tròn, **không tự nó chứng minh tính không kết hợp** vì không so sánh hai cách đặt ngoặc khác nhau.

## 10. Java 17+, strictfp, Math.fma và khả năng tái lập

Kể từ Java 17, JEP 306 khôi phục ngữ nghĩa dấu phẩy động **luôn nghiêm ngặt** (*always-strict floating-point semantics*); từ khóa `strictfp` không còn cần để yêu cầu cùng quy tắc chính xác đó cho các biểu thức số thực.

Điều này giúp hành vi phép toán ổn định theo đặc tả Java, nhưng **không làm phép cộng/nhân trở thành kết hợp**. “Kết quả tuân theo chuẩn và có thể dự đoán” hoàn toàn khác với “có thể đổi ngoặc tùy ý”.

### Fused multiply-add

`Math.fma(a, b, c)` tính tích chính xác lý tưởng `a*b` rồi cộng `c` trước khi làm tròn **một lần** về `float`/`double`; khác với biểu thức `a*b+c` thông thường, vốn có thể làm tròn sau phép nhân rồi sau phép cộng.

```java
double fused = Math.fma(a, b, c);
double separate = a * b + c;
```

Ở đây giá trị của các biến phụ thuộc ngữ cảnh đoạn code; đây là **minh họa API**, không phải chương trình độc lập. Dùng `fma` khi thuật toán được thiết kế để tận dụng phép nhân-cộng hợp nhất. **Nó không khiến mọi tổng hay mọi phép nhân tự động có tính kết hợp** và không thay thế việc kiểm soát overflow, underflow trong toàn thuật toán.

### Không tự cho phép trình biên dịch đổi ngoặc

Các phép biến đổi đại số như:

```java
// Không tự coi hai vế tương đương cho mọi float/double!
double left = (a + b) + c;
double right = a + (b + c);
```

không được áp dụng vô điều kiện. Một biểu thức có thể khác do sai số làm tròn, giá trị vô cực, `NaN` và số 0 có dấu. Khi cần cải thiện hiệu năng hoặc tính ổn định, đánh giá **kết quả tính được của dữ liệu thực**, không chỉ biến đổi đại số trên giấy.

## 11. Tổng nhiều số: thứ tự lặp và giảm song song có thể đổi kết quả

Trong chương trình tính tổng mảng, tổng từng phần (*partial sums*) có thể thay đổi theo:

- thứ tự duyệt phần tử;
- cách chia mảng thành các nhóm;
- cách kết hợp kết quả từ những luồng tính khác nhau;
- thuật toán cộng thường, ghép cặp hoặc cộng có bù sai số.

Dù dữ liệu đầu vào giống nhau, đổi cây cộng có thể đổi các bước làm tròn. Ví dụ:

```java
double[] values = {1.0e16, -1.0e16, 1.0};

double firstOrder = 0.0;
for (double value : values) {
    firstOrder += value;
}
// firstOrder = 1.0
```

Nếu đổi thứ tự thành `{1.0e16, 1.0, -1.0e16}`, phép cộng tuần tự cho `0.0`. Nếu một phép **parallel reduction** nhóm các phần tử theo cách khác, kết quả có thể khác. Điều này không có nghĩa mọi lần chạy song song đều khác nhau: một lịch gộp xác định có thể ổn định; vấn đề là **không được hứa thứ tự ghép mà API/thuật toán không cam kết**.

Trong phân tích dữ liệu, tài chính, tính điểm hay phép tổng trên nhiều máy, cần xác định mục tiêu:

1. **Gần đúng đủ tốt** theo dung sai nghiệp vụ.
2. **Tái lập bit-for-bit** theo một thuật toán và thứ tự cố định.
3. **Tổng đúng theo quy tắc số học cụ thể** (ví dụ số thập phân chính xác, phép tổng bù sai số, hoặc tích lũy độ chính xác cao).

Ba mục tiêu trên đòi hỏi chiến lược triển khai và kiểm thử khác nhau.

## 12. Giảm sai số khi cộng nhiều giá trị

### 12.1. Chọn thứ tự cộng phù hợp dữ liệu

Trong một số trường hợp, cộng các số nhỏ với nhau trước khi ghép với số lớn có thể giảm hấp thụ. Cộng hai số lớn trái dấu trước cũng có thể giữ lại số nhỏ, như phản ví dụ phần 6.

Tuy nhiên, **sắp xếp theo trị tuyệt đối không phải định lý bảo đảm kết quả tốt nhất cho mọi chuỗi số**, đặc biệt khi có nhiều giá trị khác dấu hoặc gần biên. Không thay đổi thứ tự theo cảm tính nếu hệ thống đòi kết quả tái lập theo quy trình cố định.

### 12.2. Pairwise summation

*Pairwise summation* cộng theo cây cân bằng thay vì cộng lần lượt vào một accumulator. Đối với nhiều tập dữ liệu, cách này có thể giảm sự tích lũy sai số và phù hợp phép tính song song.

Nhưng thay đổi cây tổng **thay đổi các bước làm tròn**, nên kết quả có thể khác tổng tuần tự. Khi đặt mục tiêu reproducibility, ghi rõ thuật toán giảm và thứ tự ghép.

### 12.3. Kahan và các thuật toán compensated summation

*Compensated summation* (chẳng hạn Kahan hoặc Neumaier) giữ thêm thông tin về phần sai số bị bỏ trong một số bước cộng. Nó có thể cải thiện độ chính xác đáng kể so với cộng tuần tự đơn giản.

Không nên khẳng định “Kahan trả lời đúng cho mọi bộ số”: ví dụ có số lớn trái dấu, triệt tiêu và số nhỏ ở giữa có thể đòi biến thể bù sai số khác; Kahan không bảo đảm mọi biểu thức đại số trở thành kết hợp.

Một minh họa thuật toán **Neumaier summation** bằng Java:

```java
static double neumaierSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double x : values) {
        double t = sum + x;
        if (Math.abs(sum) >= Math.abs(x)) {
            correction += (sum - t) + x;
        } else {
            correction += (x - t) + sum;
        }
        sum = t;
    }

    return sum + correction;
}
```

Đây là **phương thức minh họa** cần nằm trong một lớp Java. Với mảng `{1.0e16, 1.0, -1.0e16}`, thuật toán giữ số hạng nhỏ trong biến bù và trả `1.0`. Nó vẫn dùng `double`, không phải phép tính chính xác tùy ý cho mọi trường hợp, và vẫn cần kiểm thử với infinities, NaN, overflow và giới hạn tài nguyên.

### 12.4. Khi cần số thập phân chính xác, dùng BigDecimal có chủ đích

Đối với tính tiền, các giá trị thập phân có quy tắc làm tròn cụ thể, cân nhắc `BigDecimal` tạo từ **chuỗi**:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10000000000000000");
BigDecimal b = new BigDecimal("-10000000000000000");
BigDecimal c = new BigDecimal("1");

BigDecimal exact = a.add(b).add(c);
System.out.println(exact); // 1
```

Các phép cộng `BigDecimal` không dùng `MathContext` giới hạn độ chính xác được thực hiện chính xác theo số thập phân của các toán hạng (giả sử đủ tài nguyên). Nếu áp dụng `MathContext` với độ chính xác giới hạn hoặc làm tròn từng bước, **thứ tự ghép vẫn có thể ảnh hưởng kết quả**. `BigDecimal` không tự chữa một dữ liệu `double` đã làm tròn trước đó; `new BigDecimal("0.1")` biểu diễn 0.1 thập phân chính xác, còn `new BigDecimal(0.1)` phản ánh giá trị nhị phân của `double 0.1`.

## 13. Cẩn trọng khi kiểm thử so sánh gần bằng

Vì `double` có sai số, nhiều thuật toán không nên so sánh kết quả gần đúng với `==` nếu chúng được tạo qua các chuỗi phép tính khác nhau. Nhưng **không có một epsilon cố định phù hợp mọi bài toán**.

Một phép kiểm tra bằng dung sai tuyệt đối + tương đối có dạng:

```java
static boolean nearlyEqual(double a, double b,
                           double absTolerance, double relTolerance) {
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true; // kể cả hai vô cực cùng dấu hoặc +0.0 == -0.0
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double diff = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return diff <= Math.max(absTolerance, relTolerance * scale);
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp. Các ngưỡng dung sai phải **không âm, hữu hạn và phù hợp bài toán**; trong code nghiệp vụ phải validate chúng. Công thức này là mẫu kiểm tra cơ bản, không phải giải pháp tổng quát cho mọi miền độ lớn vì chính phép trừ/trị tuyệt đối/nhân dung sai cũng có thể chịu ảnh hưởng của tràn, underflow và làm tròn.

Trong kiểm thử, phân biệt:

- **Tính đúng theo bit**: yêu cầu kết quả đúng chính xác như đặc tả thuật toán/quy trình tính, kể cả dấu số 0 khi có ý nghĩa.
- **Tính gần đúng số học**: sai khác có thể chấp nhận trong dung sai được chọn.
- **Tính đúng nghiệp vụ**: chẳng hạn số tiền cần làm tròn thập phân theo quy tắc cố định, tốt hơn là thiết kế với `BigDecimal` ngay từ đầu.

Không dùng `Double.MIN_VALUE` làm epsilon chung: đó là số dương subnormal nhỏ nhất, không phản ánh sai số gần 1, 100 hay `10^16`.

## 14. Chương trình Java 17+ chạy độc lập

Tạo tệp **`FloatingPointAssociativityDemo.java`**:

```java
import java.math.BigDecimal;

public class FloatingPointAssociativityDemo {
    private static double neumaierSum(double[] values) {
        double sum = 0.0;
        double correction = 0.0;

        for (double x : values) {
            double t = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            sum = t;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        System.out.println("(a+b)+c = " + ((a + b) + c));
        System.out.println("a+(b+c) = " + (a + (b + c)));
        System.out.println("same = " + (((a + b) + c) == (a + (b + c))));
        System.out.println("ulp(1e16) = " + Math.ulp(a));
        System.out.println("-1e16 + 1 == -1e16 = " + (b + c == b));

        double big = 1.0e308;
        System.out.println("multiply left = " + ((big * 2.0) * 0.5));
        System.out.println("multiply right = " + (big * (2.0 * 0.5)));

        double min = Double.MIN_VALUE;
        System.out.println("underflow left = " + ((min * 0.5) * 2.0));
        System.out.println("underflow right = " + (min * (0.5 * 2.0)));

        double[] values = {1.0e16, 1.0, -1.0e16};
        double naive = 0.0;
        for (double x : values) {
            naive += x;
        }
        System.out.println("naive sum = " + naive);
        System.out.println("compensated sum = " + neumaierSum(values));

        BigDecimal decimal = new BigDecimal("10000000000000000")
                .add(new BigDecimal("-10000000000000000"))
                .add(new BigDecimal("1"));
        System.out.println("decimal exact = " + decimal);
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp:

```bash
javac FloatingPointAssociativityDemo.java
java FloatingPointAssociativityDemo
```

**Đầu ra chuẩn với Java 17+:**

```text
(a+b)+c = 1.0
a+(b+c) = 0.0
same = false
ulp(1e16) = 2.0
-1e16 + 1 == -1e16 = true
multiply left = Infinity
multiply right = 1.0E308
underflow left = 0.0
underflow right = 4.9E-324
naive sum = 0.0
compensated sum = 1.0
decimal exact = 1
```

**Đọc kết quả:**

1. Vế trái của phép cộng làm triệt tiêu hai số lớn trước, giữ lại 1; vế phải làm tròn mất số hạng +1 trước khi triệt tiêu.
2. `Math.ulp(1e16)` bằng 2.0 giải thích vì sao cộng 1.0 vào số có độ lớn `10^16` không thay đổi kết quả.
3. Trong phép nhân, overflow trung gian biến vế trái thành Infinity dù vế phải còn hữu hạn.
4. Trong ví dụ underflow, nhân với 0.5 trước làm mất `Double.MIN_VALUE`, trong khi nhân các hệ số 0.5 và 2.0 trước bảo toàn nó.
5. Tổng tuần tự của mảng `{1e16,1,-1e16}` mất số 1; tổng có bù theo Neumaier giữ lại trong trường hợp này. `BigDecimal` với đầu vào thập phân được định nghĩa chính xác cũng cho 1.

## 15. Sai lầm phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Cộng và nhân trên `double` cũng luôn kết hợp vì toán học nói vậy” | Các phép toán `double` có làm tròn trung gian nên không bảo đảm tính kết hợp |
| “Chỉ số thập phân như 0.1 mới gây sai số” | Ngay các số `1e16` và `1.0` có thể lưu chính xác vẫn gặp hấp thụ khi cộng |
| “Dấu ngoặc chỉ để dễ đọc” | Với `float`/`double`, đổi ngoặc có thể đổi giá trị cuối |
| “Associativity cú pháp bằng tính kết hợp toán học” | `a+b+c` nhóm trái theo cú pháp; điều này không bảo đảm `a+(b+c)` cùng kết quả |
| “Phép `*` ưu tiên cao nên hàm tạo toán hạng phải chạy trước hàm bên trái” | Ưu tiên là cách nhóm; Java quy định thứ tự đánh giá toán hạng riêng |
| “`double` có miền lớn nên mọi số nguyên đều cách nhau 1” | Khoảng cách ULP tăng theo độ lớn; quanh `1e16` khoảng cách là 2 |
| “Overflow luôn ném exception như chia nguyên cho 0” | IEEE 754 có thể trả ±Infinity; underflow có thể trả subnormal hoặc ±0 |
| “`Math.fma` khiến tất cả phép tính thành chính xác vô hạn” | FMA chỉ làm tròn một lần cho phép nhân-cộng riêng, không loại bỏ mọi sai số |
| “Kahan/Neumaier luôn cho đáp án toán học chính xác” | Chúng giảm sai số nhiều trường hợp nhưng không phải số học chính xác vô hạn |
| “BigDecimal luôn kết hợp dù giới hạn precision” | Khi làm tròn từng bước bằng `MathContext`, các cách nhóm có thể khác |
| “`Double.MIN_VALUE` dùng làm epsilon cho mọi so sánh” | Đây là subnormal nhỏ nhất, không phải ngưỡng sai số chung |
| “Parallel sum luôn cho đúng cùng bit như sequential sum” | Nhóm phép cộng khác có thể cho kết quả khác, trừ khi thuật toán cam kết quy tắc gộp phù hợp |

## 16. Bài tập tự kiểm tra và lời giải

**Bài 1.** Với `a=1e16`, `b=-1e16`, `c=1.0` kiểu `double`, tính `(a+b)+c` và `a+(b+c)`.  
**Đáp án:** `1.0` và `0.0`. `b+c` được làm tròn về `b` do khoảng cách hai `double` kề nhau quanh `1e16` là 2.

**Bài 2.** Vì sao `double x=1e16; x+1.0 == x` cho `true`?  
**Đáp án:** `Math.ulp(1e16) == 2.0`, cộng thêm 1 rơi đúng điểm giữa hai số biểu diễn được và làm tròn về `x` theo ties-to-even.

**Bài 3.** `(1e308*2.0)*0.5` và `1e308*(2.0*0.5)` in gì?  
**Đáp án:** `Infinity` và `1.0E308`. Vế trái overflow trung gian, vế phải nhân 2 với 0.5 trước tạo 1.

**Bài 4.** `(Double.MIN_VALUE*0.5)*2` có giữ được `Double.MIN_VALUE` không?  
**Đáp án:** Không, ra `0.0` do underflow ở phép nhân đầu. `Double.MIN_VALUE*(0.5*2)` vẫn bằng `Double.MIN_VALUE`.

**Bài 5.** Vì sao `0.1+0.2 == 0.3` cho `false` chưa tự chứng minh mất tính kết hợp?  
**Đáp án:** Vì đó là một phép cộng và một phép so sánh, chưa so sánh hai cách nhóm **cùng ba số hạng**. Nó minh họa sai số biểu diễn/làm tròn.

**Bài 6.** `a+b+c` trên Java được nhóm như thế nào? Nó có tự động tương đương `a+(b+c)` không?  
**Đáp án:** Nhóm `(a+b)+c` theo kết hợp cú pháp trái. Với dấu phẩy động, **không bảo đảm** cho cùng giá trị với nhóm phải.

**Bài 7.** Nếu thứ tự cộng mảng ảnh hưởng kết quả, cần làm gì để một báo cáo có thể tái lập?  
**Đáp án:** Quy định thuật toán cộng, thứ tự đầu vào/cách phân nhóm và quy tắc kiểm thử; khi cần độ chính xác tốt hơn có thể dùng tổng có bù hoặc phương pháp phù hợp miền nghiệp vụ. Nếu cần số thập phân chính xác, cân nhắc `BigDecimal` có quy tắc precision/rounding rõ ràng.

**Bài 8.** Dùng `BigDecimal` có bảo đảm nhóm nào cũng giống nhau không?  
**Đáp án:** Với các toán hạng thập phân chính xác và các phép cộng không làm tròn theo precision giới hạn, tính kết hợp của cộng được bảo toàn (khi phép tính hoàn tất). Nhưng đặt `MathContext` giới hạn độ chính xác và làm tròn ở từng bước có thể làm kết quả phụ thuộc thứ tự.

## 17. Checklist khi thiết kế phép tính dấu phẩy động

1. **Ghi rõ kiểu:** `float` hay `double`? Có chuyển kiểu, literal hậu tố `f`, hoặc chuyển dữ liệu từ decimal không?
2. **Xem cách nhóm:** `(a+b)+c` khác `a+(b+c)` không chỉ trên giấy mà có thể khác kết quả runtime.
3. **Xác định tỷ lệ độ lớn:** có cộng giá trị cực nhỏ vào accumulator lớn? Dùng `Math.ulp` để đánh giá độ phân giải quanh giá trị thực tế.
4. **Theo dõi overflow/underflow:** kết quả trung gian có thể thành vô cực hoặc 0 trước khi các hệ số khác được nhân vào.
5. **Chú ý dấu và special values:** `NaN`, ±Infinity, ±0.0 có các quy tắc riêng; kiểm tra `isFinite`/`isNaN` khi cần.
6. **Đừng đổi ngoặc vô điều kiện:** compiler cũng không được biến đổi làm sai ngữ nghĩa Java; phép biến đổi đại số cần chứng minh an toàn với miền dữ liệu.
7. **Chọn thuật toán tổng:** tuần tự, pairwise, compensated hoặc phương thức đáp ứng yêu cầu bit-level reproducibility.
8. **Định rõ sai số chấp nhận:** kiểm thử dung sai theo đơn vị và độ lớn nghiệp vụ; không dùng `MIN_VALUE` như epsilon dùng chung.
9. **Dùng BigDecimal khi phù hợp:** nhất là dữ liệu tiền/decimal có quy tắc làm tròn; tạo giá trị từ chuỗi và hiểu ảnh hưởng của `MathContext`.
10. **Kiểm tra bằng ví dụ phản chứng:** dùng `1e16`, `-1e16`, `1.0`, trường hợp overflow/underflow để chứng minh trực tiếp khi cần giải thích code.

**Ghi nhớ:** Số thực toán học có phép cộng và phép nhân kết hợp, nhưng `float`/`double` thực hiện **phép toán rồi làm tròn ở từng bước**. Đổi ngoặc làm đổi vị trí làm tròn, nên kết quả có thể đổi. Lập trình Java đúng cần tôn trọng **cách nhóm**, **thứ tự đánh giá**, **giới hạn biểu diễn** và **thuật toán tổng** thay vì giả định mọi biến đổi đại số đều giữ nguyên kết quả.
