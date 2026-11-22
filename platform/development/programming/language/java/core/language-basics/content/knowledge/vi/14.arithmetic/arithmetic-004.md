# Dấu của phần dư với toán hạng âm — Java 17+

Trong Java, toán tử **`%`** tính **phần dư của phép chia**, không phải phép toán modulo luôn cho kết quả không âm. Với hai số nguyên `a` và `b` (trong đó `b != 0`), Java chia số nguyên theo quy tắc **cắt phần thương về 0** (*truncation toward zero*), rồi tính phần dư:

~~~text
q = a / b      (thuong nguyen cat ve 0)
r = a % b
a = q * b + r  (dang thuc toan hoc)
~~~

**Quy tắc chính:** Phần dư nguyên khác 0 mang **cùng dấu với số bị chia `a`** (toán hạng trái), **không theo dấu số chia `b`** (toán hạng phải). Nếu chia hết, phần dư nguyên bằng `0`.

~~~java
System.out.println( 7 %  3); //  1
System.out.println(-7 %  3); // -1
System.out.println( 7 % -3); //  1
System.out.println(-7 % -3); // -1
~~~

Đừng nhầm `-7 % 3` với `Math.floorMod(-7, 3)`: chúng lần lượt là **`-1`** và **`2`**. Hai biểu thức dùng **quy tắc thương khác nhau**.

## 1. Bảng dấu của phần dư nguyên

| Số bị chia `a` | Số chia `b` | Thương nguyên `a / b` | Phần dư `a % b` | Kiểm tra |
| ---: | ---: | ---: | ---: | --- |
| 7 | 3 | 2 | 1 | `7 = 2 * 3 + 1` |
| −7 | 3 | −2 | −1 | `-7 = (-2) * 3 + (-1)` |
| 7 | −3 | −2 | 1 | `7 = (-2) * (-3) + 1` |
| −7 | −3 | 2 | −1 | `-7 = 2 * (-3) + (-1)` |
| −9 | 3 | −3 | 0 | Chia hết |
| 0 | −3 | 0 | 0 | Số bị chia bằng 0 |

Với số chia nguyên khác 0, độ lớn toán học của phần dư thỏa **`|r| < |b|`**; khi `r != 0` thì dấu của `r` là dấu của `a`. Lưu ý `Math.abs(Integer.MIN_VALUE)` vẫn có giá trị âm vì giới hạn biểu diễn `int`, nên không dùng `Math.abs` một cách mù quáng để kiểm chứng bất đẳng thức ở mọi biên.

### Vì sao `-7 % 3 == -1`?

Java lấy thương nguyên của `-7 / 3` là **`-2`**, không phải `-3`:

~~~text
-7 / 3 = -2       (cat ve 0)
-7 = (-2) * 3 + r
 r = -7 - (-6) = -1
~~~

Nếu thay thương bằng `floor(-7/3) = -3` thì phần dư tương ứng là 2. Đó là cách tiếp cận của **floor division / floor modulus**, không phải cách Java tính `%` nguyên.

## 2. Chương trình Java 17+ chạy được

Lưu file UTF-8 tên **`RemainderSignsDemo.java`**:

~~~java
public class RemainderSignsDemo {
    private static void show(int a, int b) {
        System.out.println(a + "/" + b + "=" + (a / b)
                + ",remainder=" + (a % b));
    }

    public static void main(String[] args) {
        System.out.println("== integer signs ==");
        show(7, 3);
        show(-7, 3);
        show(7, -3);
        show(-7, -3);
        show(-9, 3);
        show(0, -3);

        int dividend = -7;
        int divisor = 3;
        int quotient = dividend / divisor;
        int remainder = dividend % divisor;
        System.out.println("recombined="
                + (quotient * divisor + remainder));

        System.out.println("== floor modulus ==");
        System.out.println("remainderNeg=" + (-7 % 3));
        System.out.println("floorModNeg=" + Math.floorMod(-7, 3));
        System.out.println("floorModPosNeg=" + Math.floorMod(7, -3));
        System.out.println("floorModNegNeg=" + Math.floorMod(-7, -3));

        int slots = 3;
        int rawIndex = -7 % slots;
        int safeIndex = Math.floorMod(-7, slots);
        System.out.println("rawIndex=" + rawIndex);
        System.out.println("safeIndex=" + safeIndex);

        System.out.println("== edge cases ==");
        System.out.println("longRemainder=" + (-7L % 3L));
        System.out.println("minByMinusOne="
                + (Integer.MIN_VALUE % -1));

        try {
            int invalid = 7 % 0;
            System.out.println("unexpected=" + invalid);
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }

        System.out.println("== floating-point ==");
        System.out.println("doubleNeg=" + (-7.5 % 3.0));
        System.out.println("doubleNegDivisor=" + (7.5 % -3.0));
        System.out.println("negativeZero=" + (-0.0 % 3.0));
        System.out.println("floatingZeroIsNaN="
                + Double.isNaN(7.0 % 0.0));
        System.out.println("infiniteDividendIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY % 3.0));
        System.out.println("infiniteDivisor="
                + (-7.5 % Double.POSITIVE_INFINITY));
    }
}
~~~

Với **JDK 17 trở lên**, mở PowerShell hoặc Bash trong thư mục chứa tệp và chạy:

~~~bash
java -version
javac -version
javac -encoding UTF-8 RemainderSignsDemo.java
java RemainderSignsDemo
~~~

**Expected output chính xác** từ lệnh `java RemainderSignsDemo` (không tính đầu ra phiên bản JDK):

~~~text
== integer signs ==
7/3=2,remainder=1
-7/3=-2,remainder=-1
7/-3=-2,remainder=1
-7/-3=2,remainder=-1
-9/3=-3,remainder=0
0/-3=0,remainder=0
recombined=-7
== floor modulus ==
remainderNeg=-1
floorModNeg=2
floorModPosNeg=-2
floorModNegNeg=-1
rawIndex=-1
safeIndex=2
== edge cases ==
longRemainder=-1
minByMinusOne=0
integerZero=ArithmeticException
== floating-point ==
doubleNeg=-1.5
doubleNegDivisor=1.5
negativeZero=-0.0
floatingZeroIsNaN=true
infiniteDividendIsNaN=true
infiniteDivisor=-7.5
~~~

## 3. Toán hạng âm nằm ở đâu?

Với biểu thức `a % b`:

- `a`: **số bị chia** (*dividend*), nằm **bên trái** dấu `%`.
- `b`: **số chia** (*divisor*), nằm **bên phải** dấu `%`.
- Dấu của phần dư nguyên khác 0 tuân theo **`a`**, dù `b` dương hay âm.

Ví dụ cùng số bị chia `7`:

~~~java
int a = 7;
System.out.println(a % 3);  // 1.
System.out.println(a % -3); // 1.
~~~

Đổi dấu **số chia** làm thay đổi thương nhưng **không đảo dấu phần dư**. Ngược lại, đổi dấu số bị chia từ 7 sang −7 làm phần dư đổi dấu khi khác 0:

~~~java
System.out.println(-7 % 3);  // -1.
System.out.println(-7 % -3); // -1.
~~~

Không được kết luận rằng `%` “luôn trả số dương trong miền 0 đến `b-1`”. Điều đó chỉ đúng trong một số điều kiện (ví dụ `a >= 0` và `b > 0`), chứ **không đúng khi `a` âm**.

## 4. Khác nhau giữa `%` và `Math.floorMod()`

Java cung cấp `Math.floorMod` để tính phần dư tương ứng với **thương làm tròn xuống âm vô cực** (*floor division*). Với số nguyên:

~~~text
%:            a = (a / b) * b + (a % b)         (thuong cat ve 0)
floorMod:     a = floorDiv(a,b) * b + floorMod(a,b)
~~~

| Biểu thức | Kết quả `%` | Kết quả `Math.floorMod` |
| --- | ---: | ---: |
| `-7` và `3` | −1 | 2 |
| `7` và `-3` | 1 | −2 |
| `-7` và `-3` | −1 | −1 |
| `7` và `3` | 1 | 1 |

Với **số chia dương**, `Math.floorMod(a, b)` có kết quả trong khoảng từ **0 đến `b - 1`**, nên hữu ích khi cần chuẩn hóa chỉ số vòng, số thứ tự tuần hoàn hoặc nhóm theo một số lượng ô cố định.

~~~java
int slotCount = 3;
int raw = -7 % slotCount;              // -1: chi so am.
int index = Math.floorMod(-7, slotCount); // 2: trong 0..2.
~~~

Nếu `b` âm, `Math.floorMod(a, b)` cho kết quả **bằng 0 hoặc mang dấu của số chia** (có thể âm). Vì vậy khi dùng `floorMod` để tạo chỉ số mảng, cần bảo đảm **modulus dương**.

**Không nên tự viết `(a % n + n) % n` như công thức vạn năng**, bởi phép cộng trung gian có thể tràn `int` khi `n` lớn. `Math.floorMod(a, n)` thể hiện đúng ý đồ hơn cho `n > 0`. Nếu `n == 0`, `floorMod` nguyên cũng ném `ArithmeticException`.

## 5. Lưu ý biên của `int` và `long`

Các phép `%` giữa `int` và `long` được thực hiện với các toán hạng số nguyên sau khi Java áp dụng quy tắc nâng kiểu số thích hợp. Kết quả có kiểu số nguyên tương ứng:

~~~java
int i = -7 % 3;     // int -1.
long j = -7L % 3L;  // long -1.
~~~

Một tình huống biên dễ gây ngạc nhiên:

~~~java
int rem = Integer.MIN_VALUE % -1; // 0.
~~~

Về toán học, `Integer.MIN_VALUE` chia hết cho −1, nên phần dư bằng 0. Phép chia `Integer.MIN_VALUE / -1` riêng rẽ tạo thương không biểu diễn được trong `int` (Java xử lý tràn theo ngữ nghĩa số nguyên), nhưng **toán tử `%` vẫn trả 0 và không ném ngoại lệ**.

**Cảnh báo chia cho 0:**

~~~java
// int bad = 7 % 0; // Runtime ArithmeticException.
int divisor = 3;
if (divisor != 0) {
    System.out.println(7 % divisor); // 1.
}
~~~

Với `%` nguyên, số chia **bằng 0** ném `ArithmeticException`. Số chia âm **không** ném ngoại lệ chỉ vì dấu âm.

## 6. `%` cho `float` và `double` có khác không?

Có. Toán tử `%` cũng dùng được với kiểu số thực. Nó vẫn tuân theo logic phần dư dựa trên **thương cắt về 0**, **không phải** phép `Math.IEEEremainder` (dùng quy tắc khác cho thương). Khi các toán hạng hữu hạn và số chia khác 0, phần dư khác 0 thường mang dấu số bị chia.

~~~java
System.out.println(-7.5 % 3.0);  // -1.5.
System.out.println(7.5 % -3.0);  //  1.5.
~~~

Nhưng số thực IEEE 754 có những trường hợp đặc biệt:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `-7.5 % 3.0` | `-1.5` | Phần dư mang dấu số bị chia |
| `7.5 % -3.0` | `1.5` | Dấu số chia không quyết định dấu phần dư |
| `-0.0 % 3.0` | `-0.0` | Số thực phân biệt âm không và dương không |
| `7.0 % 0.0` | `NaN` | **Không** ném `ArithmeticException` như số nguyên |
| `Double.POSITIVE_INFINITY % 3.0` | `NaN` | Số bị chia vô cực |
| `-7.5 % Double.POSITIVE_INFINITY` | `-7.5` | Số chia vô cực, số bị chia hữu hạn |

Đừng nhầm `-0.0` (giá trị số thực có bit dấu) với `0` của kiểu `int`: phần dư nguyên không có trạng thái “âm không”.

Khi logic chương trình cần kiểm soát số thực không hợp lệ, cân nhắc `Double.isFinite(...)`, `Double.isNaN(...)` và yêu cầu làm tròn/độ chính xác của bài toán. Không dùng quy tắc “chắc chắn ném exception khi modulo 0” chung cho cả số nguyên và số thực.

## 7. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`-7 % 3` bằng 2.” | Trong Java, kết quả là **−1** |
| “Phần dư theo dấu của số chia.” | Phần dư **nguyên khác 0 theo dấu số bị chia** |
| “`7 % -3` phải âm.” | Kết quả là **1** |
| “`%` luôn trả chỉ số không âm.” | Không, nếu số bị chia âm |
| “`%` và `Math.floorMod` luôn giống nhau.” | Khác nhau khi dấu và cách lấy thương làm phần dư khác |
| “Số chia âm gây `ArithmeticException`.” | Chỉ chia cho **0** mới gây lỗi số học này với số nguyên |
| “`double % 0.0` cũng ném `ArithmeticException`.” | Kết quả là `NaN` |
| “Dấu âm của số 0 không đáng phân biệt với `double`.” | Có thể nhận được `-0.0` như phần dư số thực |
| “`Math.abs` luôn trả số không âm cho mọi `int`.” | `Math.abs(Integer.MIN_VALUE)` vẫn âm do tràn |

## 8. Bài tập tự kiểm tra

1. `-10 % 3` bằng bao nhiêu?  
   *Đáp án:* **−1** vì `-10 / 3` cho thương nguyên −3 và `-10 - (-3)*3 = -1`.
2. `10 % -3` bằng bao nhiêu?  
   *Đáp án:* **1**: số bị chia dương.
3. `-10 % -3` bằng bao nhiêu?  
   *Đáp án:* **−1**: số bị chia âm.
4. `-12 % 4` bằng bao nhiêu?  
   *Đáp án:* **0** vì chia hết.
5. `Math.floorMod(-10, 3)` và `-10 % 3` khác nhau thế nào?  
   *Đáp án:* **2** so với **−1**; `floorMod` với số chia dương giúp chuẩn hóa phần dư không âm.
6. `int index = -1 % 5;` có phù hợp để truy cập mảng năm phần tử không?  
   *Đáp án:* Không; `index == -1` là chỉ số âm. Dùng `Math.floorMod(-1, 5) == 4` nếu cần vòng chỉ số.
7. `7.0 % 0.0` có ném `ArithmeticException` không?  
   *Đáp án:* Không; kết quả số thực là `NaN`, khác `7 % 0` nguyên.
8. `Integer.MIN_VALUE % -1` trả gì?  
   *Đáp án:* **0**, vì số bị chia chia hết cho −1.

## Checklist

- [ ] Phân biệt **số bị chia bên trái** và **số chia bên phải** dấu `%`.
- [ ] Nhớ `/` nguyên cắt thương về 0, nên phần dư nguyên khác 0 theo **dấu số bị chia**.
- [ ] Dùng bảng dấu để kiểm tra bốn trường hợp dương/âm của hai toán hạng.
- [ ] Không lấy `%` trực tiếp làm chỉ số không âm nếu dữ liệu có thể âm.
- [ ] Với `n > 0`, cân nhắc `Math.floorMod(a, n)` để có phần dư từ 0 đến `n - 1`.
- [ ] Kiểm tra số chia bằng 0 trước `%` nguyên.
- [ ] Phân biệt `%` số thực với số nguyên, nhất là `NaN`, vô cực và `-0.0`.
- [ ] Không suy ra rằng việc đổi dấu số chia sẽ tự đổi dấu phần dư.

**Kết luận:** Trong Java, `%` là **remainder theo thương cắt về 0**. Với số nguyên, **dấu phần dư khác 0 đi theo toán hạng trái**. Khi cần modulo không âm để tính chỉ số vòng, dùng `Math.floorMod(a, n)` với **`n > 0`** thay vì giả định `a % n` luôn không âm.
