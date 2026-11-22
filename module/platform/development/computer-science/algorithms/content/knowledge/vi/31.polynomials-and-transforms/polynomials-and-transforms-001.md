# Biểu diễn đa thức và đánh giá bằng sơ đồ Horner

## Tổng quan và mục tiêu

Trong nhóm **Đa thức và biến đổi**, một đa thức cần được biểu diễn đúng hệ số và số mũ trước khi chương trình có thể tính giá trị, đạo hàm hoặc phần dư. **Sơ đồ Horner** (*Horner's method*) là phương pháp đánh giá đa thức bằng chuỗi phép nhân và cộng lồng nhau, không cần tính từng lũy thừa riêng.

Với đa thức bậc n lưu bằng n+1 hệ số dense, Horner dùng **O(n) phép toán số học và O(1) bộ nhớ phụ**, một lựa chọn đơn giản, nhanh và dễ chứng minh. Kỹ thuật này còn dẫn đến **Horner mở rộng** tính đồng thời giá trị và đạo hàm, và **chia tổng hợp** cho một nhân tử dạng `x-r`.

Sau bài này, bạn cần biết:

1. Biểu diễn đa thức bằng hệ số dense theo thứ tự tăng hoặc giảm số mũ, và biểu diễn sparse theo cặp số mũ–hệ số.
2. Chuẩn hóa hệ số 0 ở bậc cao, phân biệt đa thức không và đa thức hằng.
3. Suy ra biểu thức Horner lồng nhau, mô phỏng từng bước và chứng minh bằng bất biến.
4. Đếm chính xác phép nhân/cộng; phân biệt O(n) phép toán với chi phí bit khi dùng `BigInteger`.
5. Cài đặt Java 17+ với hệ số bất biến, giá trị lớn, modulo và điều kiện đầu vào.
6. Tính `P(r)` và `P'(r)` trong một lượt Horner.
7. Chia tổng hợp cho `x-r`, tìm thương Q và phần dư `P(r)`, vận dụng định lý nhân tử.
8. Nhận biết sai số dấu phẩy động, overflow, sự khác nhau giữa đánh giá và tìm nghiệm.
9. Kiểm thử bằng phép tính trực tiếp, đạo hàm độc lập, phép chia dựng lại và ví dụ số học modulo.

---

## 1. Khái niệm đa thức và hệ số

Một đa thức một biến x với hệ số nguyên được viết:

\[
P(x)=a_0+a_1x+a_2x^2+\cdots+a_nx^n.
\]

Trong đó:

- `a_i` là **hệ số** của `x^i`.
- `i` là số mũ nguyên không âm.
- `a_0` là **hệ số tự do**; luôn có `P(0)=a_0`.
- Nếu `a_n\ne0`, n là **bậc** của đa thức và `a_n` là hệ số dẫn đầu.

Ví dụ xuyên suốt:

\[
\boxed{P(x)=2x^3-6x^2+2x-1}.
\]

Đa thức này có bậc 3, hệ số dẫn đầu 2 và hệ số tự do −1.

### 1.1. Đa thức hằng

`C(x)=7` có bậc 0 và `C(r)=7` với mọi r. Những hệ số 0 có thể được cho thêm ở bậc cao nhưng không làm bậc thực tăng.

### 1.2. Đa thức không

`Z(x)=0` là đa thức có tất cả hệ số bằng 0. Bậc của đa thức không thường được để **không xác định** hoặc theo quy ước lý thuyết là `-\infty`.

**Hợp đồng Java của bài:** lưu đa thức không bằng đúng mảng `[0]` và trả `degree()=-1` làm giá trị sentinel. Đây là **quy ước API**, không phải định nghĩa duy nhất của toán học.

### 1.3. Tính giá trị khác với biến đổi đa thức

- **Đánh giá P(r):** trả một số ứng với giá trị của đa thức tại r.
- **Lấy đạo hàm P'(x):** tạo một đa thức mới.
- **Đánh giá đạo hàm P'(r):** trả một số.
- **Chia P(x) cho x-r:** trả một đa thức thương và một số dư.

Các thao tác liên quan nhưng có kiểu kết quả khác nhau. Mã Java đặt chúng trong các phương thức riêng để tránh nhập nhằng.

---

## 2. Biểu diễn dense tăng dần hoặc giảm dần số mũ

Với:

\[
P(x)=2x^3-6x^2+2x-1,
\]

mảng **tăng dần số mũ** (*ascending coefficients*) là:

```text
index:            0   1   2   3
coefficient:     -1   2  -6   2
power of x:       0   1   2   3
```

Tức `coeff[i]` là hệ số của `x^i`.

Mảng **giảm dần số mũ** (*descending coefficients*) là:

```text
[2, -6, 2, -1]
```

vì phần tử đầu tiên là hệ số của `x^3`.

### 2.1. Vì sao hướng lưu đặc biệt quan trọng?

Mảng:

```text
[2, -6, 2, -1]
```

nếu hiểu theo giảm dần sẽ là:

\[
2x^3-6x^2+2x-1,
\]

nhưng nếu hiểu theo tăng dần lại là:

\[
2-6x+2x^2-x^3.
\]

Chương trình vẫn có thể chạy hoàn toàn hợp lệ nhưng trả **giá trị sai bài toán**. Vì thế thứ tự hệ số phải là một phần bắt buộc của API.

**Quy ước toàn bộ chương trình Java bên dưới: hệ số được nhập theo thứ tự tăng dần số mũ.** Thuật toán Horner sẽ duyệt ngược từ cuối mảng về chỉ số 0.

### 2.2. Bảo toàn các hệ số 0 nằm giữa

Cho:

\[
R(x)=x^2-1.
\]

Mảng tăng dần là:

```text
[-1, 0, 1]
```

Số 0 ở index 1 biểu thị hệ số của x bằng 0. Nếu xóa nó và lưu `[-1,1]` thì đa thức biến thành `x-1`, **khác** đa thức ban đầu.

### 2.3. Chuẩn hóa số 0 ở bậc cao

Nếu input tăng dần là:

```text
[7, 2, 0, 0]
```

thì đa thức thực tế chỉ là `7+2x`, bậc 1. Có thể xóa các số 0 ở **cuối mảng** khi không còn hệ số khác 0 ở bậc cao hơn:

```text
[7, 2, 0, 0] -> [7, 2]
[7, 0, 0]    -> [7]
[0, 0, 0]    -> [0]
```

Không xóa số 0 ở **giữa** các hệ số có ý nghĩa.

### 2.4. Biểu diễn sparse

Đa thức:

\[
S(x)=5x^{1\,000\,000}+2x^3-7
\]

chỉ có ba hệ số khác 0 nhưng bậc một triệu. Dense cần 1.000.001 ô, phần lớn đều bằng 0. Sparse chỉ lưu:

```text
(exponent, coefficient)
(0, -7)
(3,  2)
(1000000, 5)
```

Một `Map<Integer,BigInteger>` hoặc danh sách cặp đã sắp theo số mũ có thể tiết kiệm RAM.

- **Dense:** phù hợp khi các số mũ liên tiếp hoặc đa thức có nhiều hạng tử, dễ tính đạo hàm và Horner.
- **Sparse:** phù hợp khi bậc rất cao và số hạng khác 0 ít, cần giữ số mũ rõ ràng.

Horner cơ bản dưới đây dành cho dense. Với sparse, có thể dùng Horner theo **khoảng cách số mũ** kết hợp lũy thừa nhanh; không nên cấp phát một mảng khổng lồ chỉ để chứa rất nhiều số 0.

---

## 3. Từ tổng đa thức sang dạng Horner

Viết đa thức theo bậc giảm:

\[
P(x)=a_nx^n+a_{n-1}x^{n-1}+\cdots+a_1x+a_0.
\]

Nhóm nhân tử x từ các hạng tử có số mũ dương:

\[
P(x)=
x(a_nx^{n-1}+a_{n-1}x^{n-2}+\cdots+a_1)+a_0.
\]

Tiếp tục nhóm bên trong, ta được:

\[
\boxed{
P(x)=(\cdots((a_nx+a_{n-1})x+a_{n-2})x
+\cdots+a_1)x+a_0.
}
\]

Đây là **dạng lồng nhau** của Horner.

Với `P(x)=2x^3-6x^2+2x-1`:

\[
P(x)=((2x-6)x+2)x-1.
\]

### 3.1. Mô phỏng tại x=3

```text
Bắt đầu từ hệ số dẫn đầu: result = 2
Bước 1: result = 2*3 - 6 = 0
Bước 2: result = 0*3 + 2 = 2
Bước 3: result = 2*3 - 1 = 5
```

Vậy:

\[
\boxed{P(3)=5}.
\]

Kiểm chứng bằng tổng ban đầu:

\[
2\cdot3^3-6\cdot3^2+2\cdot3-1
=54-54+6-1=5.
\]

| Hệ số xét | Giá trị cũ | Nhân x=3 rồi cộng hệ số | Kết quả |
| ---: | ---: | --- | ---: |
| 2 | — | Khởi tạo | 2 |
| −6 | 2 | `2·3−6` | 0 |
| 2 | 0 | `0·3+2` | 2 |
| −1 | 2 | `2·3−1` | 5 |

### 3.2. Ví dụ có hệ số thiếu

Với:

\[
T(x)=3x^4-2x^3+5x-7,
\]

các hệ số giảm dần là:

```text
[3, -2, 0, 5, -7]
```

Dạng Horner chuẩn:

\[
\boxed{T(x)=((((3x-2)x+0)x+5)x-7)}.
\]

Bước cộng 0 **không được bỏ cả phép nhân x**, vì hệ số của `x^2` bằng 0 nhưng số mũ vẫn phải giảm đúng một cấp.

---

## 4. Giả mã Horner và hướng duyệt

### 4.1. Dữ liệu tăng dần số mũ

```text
HORNER_ASCENDING(a, x):
    result = 0

    for i from a.length-1 down to 0:
        result = result*x + a[i]

    return result
```

Mã dùng result=0 để xử lý mảng đã chuẩn hóa, kể cả đa thức không.

### 4.2. Dữ liệu giảm dần số mũ

```text
HORNER_DESCENDING(a, x):
    result = 0

    for i from 0 to a.length-1:
        result = result*x + a[i]

    return result
```

Hai cách chỉ khác hướng duyệt. Nếu API nhận mảng tăng dần mà bạn dùng phiên bản giảm dần, kết quả nhìn có vẻ hợp lý nhưng tương ứng với **một đa thức khác**.

### 4.3. Khởi tạo từ hệ số dẫn đầu

Với đa thức bậc n và hệ số a_n khác 0:

```text
result = a[n]

for i = n-1 down to 0:
    result = result*x + a[i]
```

Phiên bản này thực hiện **đúng n phép nhân và n phép cộng**, thay vì thêm bước vô hại `0*x+a_n` như phiên bản result=0.

### 4.4. Những điểm kiểm tra nhanh

- `x=0`: luôn `P(0)=a_0`.
- `x=1`: `P(1)=a_0+a_1+\cdots+a_n`.
- `x=-1`: `P(-1)=a_0-a_1+a_2-a_3+\cdots`.

Với P của ví dụ:

\[
P(0)=-1,\qquad P(1)=-3,\qquad P(-1)=-11.
\]

Đây là những test dễ kiểm tra mà không cần thuật toán khác phức tạp.

---

## 5. Chứng minh tính đúng bằng bất biến

Đặt:

\[
H_i(x)=a_i+a_{i+1}x+\cdots+a_nx^{n-i}.
\]

Các đa thức hậu tố hệ số thỏa:

\[
H_n(x)=a_n,\qquad
H_i(x)=a_i+xH_{i+1}(x).
\]

Xét phiên bản khởi tạo `result=a_n` và lần lượt xử lý `a_{n-1},...,a_0`.

**Bất biến:** sau khi xử lý a_i, giá trị result bằng `H_i(x)`.

**Cơ sở:** lúc đầu result=a_n=H_n(x).

**Bước quy nạp:** nếu trước bước i có `result=H_{i+1}(x)`, sau phép:

\[
result\leftarrow result\cdot x+a_i
\]

ta được:

\[
result=a_i+xH_{i+1}(x)=H_i(x).
\]

**Kết thúc:** sau bước i=0:

\[
result=H_0(x)=P(x).
\]

Do đó Horner tính đúng trong số học chính xác.

### 5.1. Số phép toán và độ phức tạp

Với bậc n:

- **n phép nhân** khi dùng phiên bản khởi tạo từ a_n.
- **n phép cộng**.
- **O(1)** biến phụ cho riêng phép đánh giá.

Nếu mỗi phép số học có chi phí O(1), thời gian:

\[
\boxed{T(n)=O(n)},\qquad
\boxed{S_{\mathrm{extra}}(n)=O(1)}.
\]

Mảng hệ số đầu vào vẫn tốn O(n) bộ nhớ, và không được tính nhầm thành “bộ nhớ phụ O(1) của thuật toán”.

### 5.2. Horner so với tính từng lũy thừa

Nếu tính riêng `x^i` từ đầu bằng i lần nhân cho từng i, tổng phép toán có thể O(n²).

Tuy nhiên, một cách tính trực tiếp có biến `power` duy trì `1,x,x²,...` cũng có thể đạt O(n) phép số học. Vì vậy **không được khẳng định mọi cách trực tiếp đều O(n²)**. Ưu thế của Horner là công thức rất gọn, dùng ít phép nhân và không cần lưu các lũy thừa.

### 5.3. BigInteger và chi phí bit

Với `BigInteger`, số chữ số của các giá trị trung gian có thể tăng khi n hoặc x lớn. Một phép nhân BigInteger **không phải O(1)** nếu tính theo số bit.

Do đó O(n) là cận **số bước số học** của Horner trong mô hình phép số học hằng số, không phải bảo đảm thời gian CPU O(n) trên mọi số nguyên khổng lồ.

---

## 6. Đánh giá với số âm và kết quả lớn

Với:

\[
P(x)=2x^3-6x^2+2x-1,
\]

tại x=−2:

\[
P(-2)=2(-8)-6(4)+2(-2)-1
=-16-24-4-1
=\boxed{-45}.
\]

Tại `x=10^9`:

\[
P(10^9)=2\cdot10^{27}-6\cdot10^{18}
+2\cdot10^9-1.
\]

Kết quả chính xác:

```text
1999999994000000001999999999
```

Giá trị này **vượt xa giới hạn long**. Nếu dùng `long` và nhân tràn trước khi tính xong, Java không tự ném ngoại lệ mà kết quả sẽ bị sai.

**BigInteger** biểu diễn số nguyên lớn chính xác, phù hợp khi đầu vào và kết quả cần bảo đảm không tràn. Nó đổi lại chi phí tính toán và bộ nhớ theo kích thước số.

---

## 7. Java 17+: chương trình hoàn chỉnh

Chương trình sử dụng lớp bất biến `Polynomial` và có các phép:

- Đánh giá bằng Horner.
- Đánh giá đồng thời `P(x)` và `P'(x)`.
- Tạo đa thức đạo hàm.
- Đánh giá modulo m.
- Chia tổng hợp cho `x-root` với thương và phần dư.
- Chuẩn hóa đa thức hằng/không.
- Kiểm tra giới hạn đầu vào.

**Tên tệp: `PolynomialHornerDemo.java`.** Tất cả hệ số nhập vào theo **thứ tự tăng số mũ**.

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;

public final class PolynomialHornerDemo {

    private static final BigInteger ZERO = BigInteger.ZERO;
    private static final BigInteger ONE = BigInteger.ONE;
    private static final BigInteger TWO = BigInteger.TWO;

    public record Evaluation(
            BigInteger value,
            BigInteger derivative) {
    }

    public record DivisionResult(
            Polynomial quotient,
            BigInteger remainder) {
    }

    public static final class Polynomial {
        // a[0] = constant; a[i] = coefficient of x^i.
        private final BigInteger[] a;

        private Polynomial(BigInteger[] input) {
            Objects.requireNonNull(input, "coefficients");

            if (input.length == 0) {
                a = new BigInteger[] { ZERO };
                return;
            }

            for (BigInteger coefficient : input) {
                Objects.requireNonNull(
                        coefficient, "coefficient");
            }

            int last = input.length - 1;

            while (last > 0
                    && input[last].signum() == 0) {
                last--;
            }

            a = Arrays.copyOf(input, last + 1);
        }

        public static Polynomial of(long... coefficients) {
            Objects.requireNonNull(
                    coefficients, "coefficients");

            BigInteger[] data =
                    new BigInteger[coefficients.length];

            for (int i = 0; i < coefficients.length; i++) {
                data[i] =
                        BigInteger.valueOf(coefficients[i]);
            }

            return new Polynomial(data);
        }

        public boolean isZero() {
            return a.length == 1
                    && a[0].signum() == 0;
        }

        // Zero polynomial convention: degree -1.
        public int degree() {
            return isZero() ? -1 : a.length - 1;
        }

        public String coefficientsAscending() {
            return Arrays.toString(a);
        }

        public BigInteger evaluate(BigInteger x) {
            Objects.requireNonNull(x, "x");

            BigInteger result = ZERO;

            for (int i = a.length - 1; i >= 0; i--) {
                result = result.multiply(x).add(a[i]);
            }

            return result;
        }

        // Calculate P(x) and P'(x) together.
        public Evaluation evaluateAndDerivative(
                BigInteger x) {

            Objects.requireNonNull(x, "x");

            BigInteger value = ZERO;
            BigInteger derivative = ZERO;

            for (int i = a.length - 1; i >= 0; i--) {
                // derivative must use OLD value.
                derivative = derivative.multiply(x)
                        .add(value);

                value = value.multiply(x).add(a[i]);
            }

            return new Evaluation(value, derivative);
        }

        public Polynomial derivative() {
            if (a.length == 1) {
                return new Polynomial(
                        new BigInteger[] { ZERO });
            }

            BigInteger[] d = new BigInteger[a.length - 1];

            for (int i = 1; i < a.length; i++) {
                d[i - 1] =
                        a[i].multiply(
                                BigInteger.valueOf(i));
            }

            return new Polynomial(d);
        }

        public BigInteger evaluateModulo(
                BigInteger x,
                BigInteger modulus) {

            Objects.requireNonNull(x, "x");
            Objects.requireNonNull(modulus, "modulus");

            if (modulus.compareTo(TWO) < 0) {
                throw new IllegalArgumentException(
                        "modulus must be >= 2");
            }

            BigInteger r = x.mod(modulus);
            BigInteger result = ZERO;

            for (int i = a.length - 1; i >= 0; i--) {
                result = result.multiply(r)
                        .add(a[i]).mod(modulus);
            }

            return result;
        }

        // P(x) = (x-root)*Q(x) + remainder.
        public DivisionResult divideByXMinus(
                BigInteger root) {

            Objects.requireNonNull(root, "root");

            int n = degree();

            if (n < 1) {
                throw new IllegalArgumentException(
                        "degree must be >= 1");
            }

            BigInteger[] q = new BigInteger[n];
            q[n - 1] = a[n];

            for (int i = n - 1; i >= 1; i--) {
                q[i - 1] = a[i]
                        .add(root.multiply(q[i]));
            }

            BigInteger remainder = a[0]
                    .add(root.multiply(q[0]));

            return new DivisionResult(
                    new Polynomial(q), remainder);
        }
    }

    public static void main(String[] args) {
        // P(x) = 2x^3 - 6x^2 + 2x - 1.
        Polynomial p = Polynomial.of(-1, 2, -6, 2);

        BigInteger three = BigInteger.valueOf(3);
        BigInteger minusTwo = BigInteger.valueOf(-2);

        System.out.println(
                "P coefficients asc: "
                        + p.coefficientsAscending());
        System.out.println("P degree: " + p.degree());
        System.out.println(
                "P(3) Horner: " + p.evaluate(three));

        Evaluation both = p.evaluateAndDerivative(three);

        System.out.println(
                "P(3) paired value: " + both.value());
        System.out.println(
                "P'(3) paired derivative: "
                        + both.derivative());
        System.out.println(
                "P' coefficients asc: "
                        + p.derivative().coefficientsAscending());

        System.out.println(
                "P(0): " + p.evaluate(ZERO));
        System.out.println(
                "P(-2): " + p.evaluate(minusTwo));
        System.out.println(
                "P(-2) mod 17: "
                        + p.evaluateModulo(
                                minusTwo,
                                BigInteger.valueOf(17)));
        System.out.println(
                "P(3) mod 17: "
                        + p.evaluateModulo(
                                three,
                                BigInteger.valueOf(17)));

        DivisionResult div = p.divideByXMinus(three);

        System.out.println(
                "P / (x-3) quotient asc: "
                        + div.quotient()
                                .coefficientsAscending());
        System.out.println(
                "P / (x-3) remainder: "
                        + div.remainder());

        // R(x) = x^2 - 1.
        Polynomial r = Polynomial.of(-1, 0, 1);
        DivisionResult rDiv = r.divideByXMinus(ONE);

        System.out.println(
                "R(1): " + r.evaluate(ONE));
        System.out.println(
                "R / (x-1) quotient asc: "
                        + rDiv.quotient()
                                .coefficientsAscending());
        System.out.println(
                "R / (x-1) remainder: "
                        + rDiv.remainder());

        // F(x) = (x-2)^2.
        Polynomial f = Polynomial.of(4, -4, 1);
        Evaluation fAtTwo = f.evaluateAndDerivative(TWO);

        System.out.println(
                "F(2), F'(2): "
                        + fAtTwo.value() + ", "
                        + fAtTwo.derivative());

        Polynomial constant = Polynomial.of(7, 0, 0);
        Polynomial zero = Polynomial.of(0, 0, 0);

        System.out.println(
                "Constant coefficients asc: "
                        + constant.coefficientsAscending());
        System.out.println(
                "Constant degree: " + constant.degree());
        System.out.println(
                "Constant(100): "
                        + constant.evaluate(
                                BigInteger.valueOf(100)));
        System.out.println(
                "Zero coefficients asc: "
                        + zero.coefficientsAscending());
        System.out.println(
                "Zero degree: " + zero.degree());
        System.out.println(
                "Zero(123): "
                        + zero.evaluate(
                                BigInteger.valueOf(123)));

        BigInteger billion = new BigInteger("1000000000");
        System.out.println(
                "P(1000000000): " + p.evaluate(billion));

        boolean constantDivisionRejected = false;
        try {
            constant.divideByXMinus(ONE);
        } catch (IllegalArgumentException ex) {
            constantDivisionRejected = true;
        }
        System.out.println(
                "Constant division rejected: "
                        + constantDivisionRejected);

        boolean invalidModulusRejected = false;
        try {
            p.evaluateModulo(ONE, ONE);
        } catch (IllegalArgumentException ex) {
            invalidModulusRejected = true;
        }
        System.out.println(
                "Modulus 1 rejected: "
                        + invalidModulusRejected);
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac PolynomialHornerDemo.java
java PolynomialHornerDemo
```

**Stdout kỳ vọng chính xác:**

```text
P coefficients asc: [-1, 2, -6, 2]
P degree: 3
P(3) Horner: 5
P(3) paired value: 5
P'(3) paired derivative: 20
P' coefficients asc: [2, -12, 6]
P(0): -1
P(-2): -45
P(-2) mod 17: 6
P(3) mod 17: 5
P / (x-3) quotient asc: [2, 0, 2]
P / (x-3) remainder: 5
R(1): 0
R / (x-1) quotient asc: [1, 1]
R / (x-1) remainder: 0
F(2), F'(2): 0, 0
Constant coefficients asc: [7]
Constant degree: 0
Constant(100): 7
Zero coefficients asc: [0]
Zero degree: -1
Zero(123): 0
P(1000000000): 1999999994000000001999999999
Constant division rejected: true
Modulus 1 rejected: true
```

### 7.1. Cách đọc cấu trúc dữ liệu Java

`Polynomial.of(-1,2,-6,2)` lưu `[-1,2,-6,2]` theo chiều tăng số mũ.

Constructor:

- Kiểm tra dữ liệu null.
- Nếu mảng rỗng, dùng biểu diễn chuẩn `[0]`.
- Loại trailing zeros ở **bậc cao**.
- Sao chép dữ liệu vào trường private để hạn chế thay đổi ngoài ý muốn.

Vì BigInteger bất biến, các phương thức tính toán không chỉnh sửa hệ số sau khi đối tượng đã tạo.

### 7.2. Vì sao method evaluate đúng cho đa thức không?

Mảng của đa thức không được chuẩn hóa thành `[0]`. Vòng Horner xử lý đúng một hệ số:

```text
result = 0
result = result*x + 0 = 0
```

Nó trả 0 với mọi x, còn `degree()` dùng riêng quy ước −1.

### 7.3. Vì sao dùng record cho kết quả?

`Evaluation` gom hai giá trị:

```text
value:       P(x)
derivative:  P'(x)
```

`DivisionResult` gom:

```text
quotient:  Q(x)
remainder: R
```

Các record có accessor tự sinh (ví dụ `both.value()`) và thuận tiện hơn việc trả một mảng không có ý nghĩa tên trường.

### 7.4. Hạn chế cố ý của chương trình

- API `Polynomial.of` nhận hệ số từ `long`, nhưng các phép tính về sau dùng `BigInteger`. Nếu đầu vào có hệ số **lớn hơn long ngay từ đầu**, cần cung cấp factory nhận `BigInteger[]` hoặc chuỗi số nguyên và kiểm tra đầu vào.
- `evaluateModulo` yêu cầu `modulus≥2`. Về mặt toán học `mod 1` có thể quy về 0, nhưng mã chọn hợp đồng rõ ràng cho bài tập.
- `divideByXMinus` yêu cầu bậc ít nhất 1. Trong toán học, có thể chia đa thức hằng cho `x-r` với thương 0 và dư bằng hằng; đây là **giới hạn API mẫu**, không phải cấm về mặt lý thuyết.
- Không xử lý số thực vì tập trung vào **số học nguyên chính xác**. Nếu dùng double/BigDecimal cần xem xét sai số và làm tròn.

---

## 8. Horner mở rộng tính P(r) và P'(r)

Đạo hàm của:

\[
P(x)=a_0+a_1x+\cdots+a_nx^n
\]

là:

\[
P'(x)=a_1+2a_2x+\cdots+na_nx^{n-1}.
\]

Ta có thể tạo mảng đạo hàm rồi chạy Horner lần nữa. Nhưng **Horner mở rộng** tính cả hai chỉ trong một vòng.

### 8.1. Suy ra công thức

Đặt:

\[
H_i(x)=a_i+xH_{i+1}(x).
\]

Lấy đạo hàm:

\[
H_i'(x)=H_{i+1}(x)+xH_{i+1}'(x).
\]

Tại x=r, giả sử ta đang giữ:

- `value=H_{i+1}(r)`.
- `derivative=H'_{i+1}(r)`.

Khi xử lý a_i:

\[
\boxed{
newDerivative=derivative\cdot r+value,
}
\]

\[
\boxed{
newValue=value\cdot r+a_i.
}
\]

**Phải tính newDerivative với value cũ.** Nếu cập nhật value trước, đạo hàm sẽ sử dụng `H_i` thay vì `H_{i+1}` và sai công thức tích.

### 8.2. Giả mã

```text
value = 0
derivative = 0

for i from n down to 0:
    derivative = derivative*r + value
    value = value*r + a[i]

return (value,derivative)
```

### 8.3. Bảng tại r=3

Với hệ số giảm dần xử lý `2,-6,2,-1`:

| Hệ số | value cũ | derivative cũ | derivative mới | value mới |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 0 | 0 | 0 | 2 |
| −6 | 2 | 0 | 2 | 0 |
| 2 | 0 | 2 | 6 | 2 |
| −1 | 2 | 6 | 20 | 5 |

Vậy:

\[
\boxed{P(3)=5,\qquad P'(3)=20.}
\]

Kiểm tra đạo hàm trực tiếp:

\[
P'(x)=6x^2-12x+2,
\]

\[
P'(3)=54-36+2=20.
\]

Tại x=−2:

\[
P'(-2)=6\cdot4-12(-2)+2=\boxed{50}.
\]

### 8.4. Đạo hàm đa thức hằng và không

Đạo hàm của một hằng số và của đa thức không đều là đa thức không. `derivative()` trả đối tượng `[0]` trong hai trường hợp ấy; Horner mở rộng trả derivative=0.

### 8.5. Đạo hàm hình thức modulo

Có thể lấy đạo hàm hệ số nguyên rồi xét modulo m. Tuy nhiên trong đặc trưng nguyên tố p, hệ số p trở thành 0 nên đạo hàm hình thức có thể khác trực giác trên số thực. Ví dụ `(x^p)'=p x^{p-1}\equiv0(mod p)`. Đừng áp mọi kết luận về bội nghiệm từ số thực vào modulo hợp số/nguyên tố mà không xét giả thiết.

---

## 9. Chia tổng hợp và định lý phần dư

Cho đa thức P bậc n≥1 và một số r. Ta có đẳng thức:

\[
\boxed{P(x)=(x-r)Q(x)+R},
\]

với Q có bậc n−1 và R là hằng số.

Thay x=r:

\[
P(r)=(r-r)Q(r)+R=R.
\]

Vậy **phần dư khi chia cho x-r bằng P(r)**.

### 9.1. Hệ số thương qua sơ đồ Horner

Đặt:

\[
b_n=a_n,
\]

và lần lượt:

\[
b_i=a_i+r b_{i+1}
\quad\text{với }i=n-1,\ldots,0.
\]

Khi đó:

\[
R=b_0,
\]

\[
Q(x)=b_1+b_2x+\cdots+b_nx^{n-1}.
\]

Nếu mảng a tăng dần, q cũng được lưu tăng dần:

```text
q[n-1] = a[n]
for i=n-1 down to 1:
    q[i-1] = a[i] + r*q[i]
remainder = a[0] + r*q[0]
```

### 9.2. Ví dụ chia P cho x−3

```text
3 |  2   -6    2   -1
  |       6    0    6
  +--------------------
     2    0    2    5
```

- Thương: `Q(x)=2x^2+2`.
- Mảng hệ số thương tăng dần: `[2,0,2]`.
- Dư: `R=5`.

Kiểm chứng:

\[
(x-3)(2x^2+2)+5
=2x^3-6x^2+2x-1=P(x).
\]

Phần dư khớp với `P(3)=5`.

### 9.3. Định lý nhân tử

\[
\boxed{P(r)=0\iff(x-r)\text{ là nhân tử của }P(x).}
\]

Ví dụ:

\[
R(x)=x^2-1=(x-1)(x+1).
\]

`R(1)=0` nên chia cho x−1 có dư 0, thương x+1 (mảng tăng dần `[1,1]`).

### 9.4. Nghiệm bội

\[
F(x)=(x-2)^2=x^2-4x+4.
\]

Ta có:

\[
F(2)=0,\quad F'(2)=0.
\]

Trên hệ số nguyên/thực, r=2 là nghiệm bội 2. Có thể kiểm tra bằng việc chia hai lần liên tiếp cho x−2, mỗi lần dư 0.

Trong đặc trưng p, đạo hàm hình thức có thể bằng 0 với đa thức như `x^p`; khi suy ra bội nghiệm cần chú ý đặc trưng của trường.

### 9.5. Vì sao API từ chối chia hằng số?

Phương thức `divideByXMinus` yêu cầu degree≥1 để giữ mảng hệ số thương có n phần tử. Về mặt toán học, chia hằng số cho x−r là hợp lệ với thương 0, dư bằng hằng đó. Việc từ chối ở đây chỉ là lựa chọn API cho ví dụ dạy chia tổng hợp bậc ít nhất 1.

---

## 10. Horner trong số học modulo

Cho môđun m≥2, ta cần:

\[
P(r)\bmod m.
\]

Vì đồng dư tương thích với cộng và nhân, có thể lấy dư **ở mỗi bước**:

```text
value = 0
r = normalize(r,m)

for i=n down to 0:
    value = normalize(value*r + a[i],m)

return value
```

### 10.1. Ví dụ x=−2, m=17

Giá trị nguyên:

\[
P(-2)=-45.
\]

Đại diện chuẩn:

\[
-45=(-3)\cdot17+6
\Longrightarrow
\boxed{P(-2)\bmod17=6}.
\]

Khi m=17 và r=3, `P(3)=5` nên `P(3) mod17=5`.

### 10.2. Hệ số âm và số âm trong Java

Với kiểu `long`, biểu thức `-45 % 17` trả số âm, không phải đại diện chuẩn 6. Một cách chuẩn hóa:

```java
long rem = ((value % m) + m) % m;
```

Tuy nhiên với m rất gần `Long.MAX_VALUE`, tổng `(value%m)+m` có nguy cơ tràn. `BigInteger.mod(m)` với m dương luôn trả đại diện không âm, nên mã dùng:

```java
value = value.multiply(reducedX)
        .add(coefficient).mod(modulus);
```

### 10.3. Không cần m nguyên tố

Horner modulo chỉ dùng cộng và nhân. Môđun 8, 12 hay 17 đều dùng được. Yêu cầu môđun nguyên tố thường xuất hiện trong các bài toán cần **nghịch đảo nhân**, không phải trong phép đánh giá Horner.

### 10.4. Vấn đề overflow

Lấy `%m` sau phép `value*x` **không cứu được tích đã tràn** trong long. Phải kiểm tra giới hạn trung gian hoặc dùng số học an toàn/BigInteger.

### 10.5. Phân biệt modulo với kết quả nguyên

`P(-2)=-45` là giá trị nguyên chính xác; `P(-2) mod17=6` là **đại diện của lớp đồng dư**. Không phải P ở x=−2 tự nhiên bằng 6 trong số học nguyên.

---

## 11. Bậc, nghiệm và môđun hợp số

Trong một trường, đa thức khác 0 bậc n có không quá n nghiệm phân biệt. Nhưng nếu xét modulo **hợp số**, cấu trúc hệ số có **ước của 0**, nên mệnh đề ấy không thể áp dụng tùy tiện.

Ví dụ:

\[
G(x)=x^2-1\pmod8.
\]

Các lớp dư:

```text
x=1: 1 - 1 = 0 mod8
x=3: 9 - 1 = 8 = 0 mod8
x=5: 25 - 1 = 24 = 0 mod8
x=7: 49 - 1 = 48 = 0 mod8
```

Vậy đa thức bậc 2 này có **4 nghiệm modulo 8**.

**Horner vẫn đúng**, vì nó chỉ dùng tính phân phối của cộng và nhân. Điều thay đổi là những kết luận về nghiệm và phân tích nhân tử trong vành có ước của 0.

---

## 12. Sai số số thực và độ ổn định

Khi dùng `double` thay BigInteger, các phép nhân/cộng có thể làm tròn. Horner thường nhanh và có tính chất sai số tốt so với nhiều cách đánh giá trực tiếp, nhưng **không bảo đảm mọi đáp án có sai số tương đối nhỏ**.

Ví dụ:

\[
G(x)=(x-1)^2=x^2-2x+1.
\]

Với x rất gần 1, giá trị thật rất nhỏ. Việc trừ những số gần bằng nhau có thể gây **triệt tiêu chữ số có nghĩa** (*catastrophic cancellation*).

Horner:

\[
G(x)=(x-2)x+1
\]

tiết kiệm phép nhân nhưng vẫn có thể bị ảnh hưởng bởi làm tròn; biểu diễn đã phân tích nhân tử `(x-1)(x-1)` có hành vi số học khác.

### 12.1. Chọn kiểu dữ liệu

- **BigInteger:** kết quả nguyên chính xác, không tràn theo giới hạn long; chi phí tăng theo số bit.
- **long:** nhanh nhưng chỉ đúng khi mọi giá trị trung gian nằm trong phạm vi.
- **double:** biểu diễn số thực gần đúng, không phù hợp để đòi kết quả nguyên lớn tuyệt đối chính xác.
- **BigDecimal:** số thập phân theo độ chính xác và quy tắc làm tròn được chọn; cần `MathContext` rõ ràng.

Không nên dùng số thực double để rồi làm tròn thành số nguyên khi bài đòi kết quả toán học nguyên chính xác.

### 12.2. Conditioning khác stability

- **Conditioning:** kết quả của bài toán có nhạy với thay đổi rất nhỏ ở input/hệ số không?
- **Stability:** thuật toán có kiểm soát tốt sai số tính toán hay không?

Horner thường là một thuật toán đánh giá tốt, nhưng nếu đa thức bị điều kiện kém tại điểm xét, ngay cả thuật toán tốt cũng có thể mất độ chính xác tương đối.

---

## 13. Đánh giá sparse bằng khoảng trống số mũ

Với:

\[
S(x)=5x^{1\,000\,000}+2x^3-7,
\]

danh sách hạng sắp giảm dần:

```text
(1000000,5), (3,2), (0,-7)
```

Ta viết:

\[
S(x)=(5x^{999\,997}+2)x^3-7.
\]

Nếu cần số hạng rất thưa, có thể dùng lũy thừa nhị phân cho khoảng cách số mũ thay vì lặp 1.000.000 bước Horner dense.

Giả mã:

```text
SPARSE_HORNER(termsDescending, x):
    if terms empty:
        return 0

    (prevExp, value) = first term

    for (exp, coefficient) in remaining terms:
        gap = prevExp - exp
        value = value * POW(x,gap) + coefficient
        prevExp = exp

    value = value * POW(x,prevExp)
    return value
```

Điều kiện: các số mũ không âm, được sắp giảm dần, và các hạng trùng số mũ đã được gộp.

**Không nhất thiết sparse luôn nhanh hơn.** Khi có nhiều hệ số khác 0 liên tiếp, dense Horner rất đơn giản và không phải tính nhiều lũy thừa riêng.

---

## 14. Biến đổi đa thức và công thức kiểm tra

### 14.1. Đạo hàm bằng mảng hệ số

Với:

\[
P(x)=\sum_{i=0}^n a_ix^i,
\]

\[
P'(x)=\sum_{i=1}^n i a_i x^{i-1}.
\]

Mảng tăng dần của đạo hàm:

```text
[a1, 2*a2, 3*a3, ..., n*an]
```

Ví dụ:

```text
P coefficients  = [-1, 2, -6, 2]
P' coefficients = [2, -12, 6]
```

### 14.2. Phép cộng

Hai đa thức dense `A(x),B(x)` có hệ số tổng tại bậc i bằng `a_i+b_i`, coi hệ số không tồn tại là 0. Sau cộng có thể cần chuẩn hóa nếu hệ số dẫn đầu bị triệt tiêu.

### 14.3. Phép nhân

Hệ số của `x^k` trong tích `A(x)B(x)`:

\[
c_k=\sum_{i+j=k}a_ib_j.
\]

Cách nhân dense ngây thơ O(nm) với hai đa thức bậc n,m. Nếu **chỉ cần giá trị của tích tại r**, không cần dựng cả tích:

\[
(A B)(r)=A(r)B(r).
\]

Chạy Horner cho A và B rồi nhân hai kết quả có thể rẻ hơn dựng mảng tích đầy đủ.

### 14.4. Đa thức ghép

Nếu `C(x)=A(B(x))`, để tính C(r):

1. Tính `y=B(r)`.
2. Dùng Horner tính `A(y)`.

Không cần dựng đa thức ghép C(x), vốn có thể có bậc rất lớn.

### 14.5. Các đẳng thức kiểm tra

Với mọi r:

\[
(A+B)(r)=A(r)+B(r),
\]

\[
(A B)(r)=A(r)B(r),
\]

\[
(A(B(x)))(r)=A(B(r)).
\]

Những đẳng thức này giúp xây các bài test thuộc tính khi mở rộng thành thư viện thao tác đa thức.

---

## 15. Khi nào nên dùng Horner?

**Một đa thức dense, một điểm:** Horner cơ bản là lựa chọn tốt.

**Một đa thức dense, cần cả P(r) và P'(r):** Horner mở rộng.

**Cần kiểm tra r có phải nghiệm:** tính `P(r)`. Nếu bằng 0, dùng định lý nhân tử; không nhất thiết phải chia toàn bộ.

**Cần thương khi chia cho x−r:** phép chia tổng hợp, dùng cùng ý tưởng Horner và lưu hệ số thương.

**Tính modulo:** lấy modulo trong mỗi bước, bảo đảm không dùng kiểu số bị tràn trước phép lấy dư.

**Một đa thức bậc rất cao nhưng cực ít hạng:** sparse với khoảng cách số mũ có thể hiệu quả hơn.

**Rất nhiều điểm đánh giá:** Horner riêng từng điểm tốn O(kn) phép số học với k điểm và bậc n. Một số thuật toán *multipoint evaluation* dùng cây tích/chia đa thức để giảm chi phí khi n,k rất lớn, nhưng khó triển khai hơn và có các giả thiết tính toán riêng.

---

## 16. Kiểm thử độc lập

### 16.1. Oracle không dùng dạng Horner

Một cách đánh giá trực tiếp bằng lũy thừa tích lũy:

```text
DIRECT_EVALUATE(a,x):
    result=0
    power=1

    for i=0..a.length-1:
        result += a[i]*power
        power *= x

    return result
```

Với số nguyên chính xác, kết quả này phải **bằng đúng** Horner cho mọi mảng hệ số và x. Cách tính khác thứ tự Horner, nên là oracle độc lập tốt.

### 16.2. Các test biên và giá trị

| Hệ số tăng dần | x | Giá trị |
| --- | ---: | ---: |
| `[-1,2,-6,2]` | 3 | 5 |
| `[-1,2,-6,2]` | −2 | −45 |
| `[-1,2,-6,2]` | 0 | −1 |
| `[-1,2,-6,2]` | 1 | −3 |
| `[-1,2,-6,2]` | −1 | −11 |
| `[-1,0,1]` | 1 | 0 |
| `[-1,0,1]` | −1 | 0 |
| `[7,0,0]` | 100 | 7 |
| `[0,0,0]` | 123 | 0 |
| `[4,-4,1]` | 2 | 0 |
| `[1,0,0,1]` | 2 | 9 |
| `[0,0,1]` | −3 | 9 |

### 16.3. Kiểm thử đạo hàm

Tạo đa thức đạo hàm bằng `derivative()` rồi đánh giá độc lập bằng `evaluate(x)`. So kết quả với `evaluateAndDerivative(x).derivative()`.

Ví dụ P:

```text
P'(3)  = 20
P'(-2) = 50
P'(0)  = 2
```

### 16.4. Kiểm thử chia tổng hợp

Nếu `(Q,R)=divideByXMinus(r)`, phải đúng:

\[
P(x)=(x-r)Q(x)+R.
\]

Đây là đẳng thức **về hệ số**, không chỉ tại một điểm. Có thể dựng lại mảng hệ số:

- Với q_i của Q, thêm q_i vào hệ số `x^{i+1}`.
- Trừ `r q_i` khỏi hệ số `x^i`.
- Cộng R vào hệ số tự do.

Mảng thu được phải bằng P đã chuẩn hóa. Ngoài ra `R==P(r)` phải đúng.

### 16.5. Kiểm thử modulo

So:

\[
evaluateModulo(x,m)
\]

với:

\[
evaluate(x)\bmod m
\]

trên BigInteger với `m≥2`. Kết quả phải giống nhau và trong `0..m−1`.

### 16.6. Sinh kiểm thử ngẫu nhiên

Với bậc 0..8 và hệ số trong −8..8:

1. Sinh mảng, gồm cả trailing zeros.
2. Xây đối tượng Polynomial và kiểm tra chuẩn hóa.
3. Chọn x từ −5 tới 5.
4. So Horner với DIRECT_EVALUATE.
5. So đạo hàm mở rộng với đạo hàm đánh giá độc lập.
6. Nếu degree≥1, chia cho x−r và dựng lại P.
7. Kiểm tra dư bằng P(r).
8. Với m từ 2 tới 19, kiểm tra Horner modulo và modulo của giá trị nguyên.

Bộ test này dễ phát hiện lỗi hệ số đảo thứ tự, cập nhật đạo hàm sai thứ tự, phép chia sai chỉ số và modulo âm.

---

## 17. Lỗi thường gặp

1. **Nhầm ascending và descending**, làm chương trình tính đa thức khác.
2. **Xóa hệ số 0 nằm giữa**, làm các số mũ giảm sai.
3. **Không chuẩn hóa hệ số 0 ở bậc cao** trước khi tính bậc.
4. **Không quy định rõ bậc của đa thức không**, khiến code xử lý mảng rỗng không thống nhất.
5. **Khởi tạo result từ a[0] rồi duyệt ngược**, cộng lặp hệ số tự do.
6. **Duyệt mảng tăng dần từ trái sang phải bằng Horner**, sai hướng.
7. **Bỏ bước nhân x khi hệ số bằng 0**, làm mất một cấp bậc.
8. **Không cộng hệ số ở mỗi bước**, kết quả chỉ là tích lũy lũy thừa.
9. **Dùng int/long khi kết quả có thể tràn**, sai im lặng.
10. **Nghĩ lấy modulo cuối cùng sẽ sửa overflow của tích**, sai.
11. **Dùng BigInteger.mod với m không dương**, vi phạm hợp đồng hàm.
12. **Nhầm kết quả nguyên P(r) với đại diện P(r) mod m**.
13. **Tính đạo hàm bằng value mới**, vi phạm công thức Horner mở rộng.
14. **Dịch mảng đạo hàm sai một index**, ví dụ hệ số `i a_i` phải đặt ở index i−1.
15. **Đưa luôn phần dư vào mảng thương**, làm thương sai bậc.
16. **Nhầm chia cho x−r với chia cho x+r**, sai dấu trong synthetic division.
17. **Chia đa thức hằng mà không xét quy ước API**, có thể tạo mảng thương rỗng và truy cập âm.
18. **Không kiểm tra `R=P(r)`** sau synthetic division.
19. **Tưởng P(r)=0 đủ kết luận r là nghiệm đơn**, có thể là nghiệm bội.
20. **Áp “bậc n tối đa n nghiệm” cho modulo hợp số**, không đúng tổng quát.
21. **Tuyên bố Horner luôn chính xác tuyệt đối với double**, bỏ sai số làm tròn.
22. **Tuyên bố Horner là thuật toán O(n) duy nhất**, quên cách tính power tích lũy.
23. **Nhầm O(n) phép số học với O(n) thời gian bit khi dùng BigInteger**.
24. **Lưu đa thức sparse cực thưa thành dense khổng lồ** mà không cân nhắc tài nguyên.
25. **Quên gộp hạng cùng số mũ trong sparse**, tính sai hệ số.
26. **Cho phép sửa mảng hệ số nội bộ**, phá bất biến bậc và dữ liệu.
27. **Không test x=0,1,−1**, bỏ các oracle đơn giản.
28. **Không test đa thức không/hằng**, bỏ lỗi nhánh rỗng.
29. **Không kiểm tra quotient bằng phép nhân dựng lại**, bỏ lỗi synthetic division.
30. **Nhầm đánh giá tại r với tìm tất cả nghiệm của P(x)=0**.

---

## 18. Bài tập tự kiểm tra

### Bài 1 — Hệ số và bậc
Cho `A(x)=4x^5-3x^2+7`. Viết mảng hệ số tăng dần và bậc.

### Bài 2 — Hai hướng biểu diễn
Mảng tăng dần `[-1,2,-6,2]` biểu diễn đa thức nào? Mảng giảm dần tương ứng?

### Bài 3 — Chuẩn hóa
`[7,0,0]` và `[0,0,0]` sau chuẩn hóa là gì? Bậc theo hợp đồng Java?

### Bài 4 — Horner
Tính `P(3)` với `P(x)=2x^3-6x^2+2x-1` theo Horner.

### Bài 5 — Dạng lồng nhau
Viết `T(x)=3x^4-2x^3+5x-7` thành Horner có đủ hạng hệ số 0.

### Bài 6 — Điểm x=0
Tại sao P(0) luôn là a0? Với P ví dụ, giá trị là bao nhiêu?

### Bài 7 — Điểm x=1
Tính P(1) bằng cách cộng các hệ số.

### Bài 8 — Điểm x=−1
Tính P(−1) bằng tổng luân phiên dấu.

### Bài 9 — Hệ số ở giữa
Tại sao `[-1,0,1]` không được rút thành `[-1,1]` trong dense?

### Bài 10 — Phép toán
Với bậc n, Horner khởi tạo từ a_n dùng bao nhiêu phép nhân/cộng?

### Bài 11 — Oracle
Viết cách đánh giá dùng biến `power` bắt đầu ở 1 thay vì dạng lồng Horner.

### Bài 12 — Số âm
Tính P(−2).

### Bài 13 — Giá trị lớn
Vì sao P(10^9) không vừa long? Kết quả chính xác trong bài?

### Bài 14 — Đạo hàm
Tìm P'(x) và tính P'(3).

### Bài 15 — Horner mở rộng
Viết quy tắc cập nhật value và derivative, giải thích việc dùng oldValue.

### Bài 16 — Đạo hàm ở điểm âm
Tính P'(−2).

### Bài 17 — Chia tổng hợp
Chia P cho x−3, cho thương và dư.

### Bài 18 — Định lý phần dư
Chứng minh dư khi chia cho x−r là P(r).

### Bài 19 — Định lý nhân tử
Cho R(x)=x²−1, tìm thương khi chia cho x−1.

### Bài 20 — Nghiệm bội
Cho F(x)=x²−4x+4, tính F(2),F'(2) và nhận xét.

### Bài 21 — Modulo
Tính P(−2) mod17.

### Bài 22 — Môđun hợp số
Horner có bắt buộc m nguyên tố khi đánh giá modulo không?

### Bài 23 — Sparse
Với `5x^{1000000}+2x^3-7`, nên lưu dense hay sparse?

### Bài 24 — Sai số
Horner dùng double có tuyệt đối chính xác cho mọi đa thức không?

### Bài 25 — Nhiều điểm
Cần đánh giá một đa thức bậc n ở k điểm. Horner riêng từng điểm tốn bao nhiêu phép toán?

### Bài 26 — Dựng lại đa thức
Nêu cách kiểm tra hệ số thương và dư bằng `(x-r)Q+R`.

### Bài 27 — Modulo 8
Giải thích tại sao `x²−1` có bốn nghiệm 1,3,5,7 modulo 8.

### Bài 28 — Số học Java
So sánh long, BigInteger, double khi đề cần kết quả **nguyên chính xác** rất lớn.

### Đáp án gợi ý

1. `[7,0,-3,0,0,4]`, bậc 5.
2. `2x³−6x²+2x−1`, mảng giảm dần `[2,-6,2,-1]`.
3. `[7]` bậc 0; `[0]` bậc −1 theo quy ước.
4. `((2·3−6)·3+2)·3−1=5`.
5. `((((3x−2)x+0)x+5)x−7)`.
6. Các hạng có x mũ dương đều thành 0; P(0)=−1.
7. `2−6+2−1=−3`.
8. `−2−6−2−1=−11`.
9. `[-1,0,1]` là x²−1, trong khi `[-1,1]` là x−1.
10. n phép nhân và n phép cộng sau khi khởi tạo từ a_n.
11. `power=1,result=0`; theo i từ 0 tới n, cộng `a_i*power` rồi `power*=x`.
12. −45.
13. `1999999994000000001999999999`, vượt giới hạn long.
14. `P'(x)=6x²−12x+2`, nên P'(3)=20.
15. `derivative=derivative*r+oldValue`; `value=oldValue*r+a_i`; đổi thứ tự sẽ sai đạo hàm.
16. 50.
17. Thương `2x²+2`, dư 5.
18. Trong `P(x)=(x-r)Q(x)+R`, thế x=r cho P(r)=R.
19. `R(x)=(x-1)(x+1)` nên thương x+1, dư 0.
20. F(2)=0 và F'(2)=0, là nghiệm bội 2 trên hệ số nguyên.
21. `−45 mod17=6`.
22. Không, cộng và nhân hợp lệ modulo mọi m dương.
23. Sparse do chỉ ba hệ số khác 0 và bậc quá lớn.
24. Không; double có sai số làm tròn và có thể mất chữ số khi triệt tiêu.
25. O(kn) phép số học.
26. Dựng lại `P=(x-r)Q+R` theo hệ số và kiểm tra R=P(r).
27. Với các x lẻ 1,3,5,7, `x²−1` chia hết cho 8; môđun hợp số có ước của 0 nên cận nghiệm theo bậc không áp trực tiếp.
28. BigInteger là lựa chọn cho số nguyên lớn chính xác; long chỉ đúng khi mọi trung gian không tràn; double chỉ gần đúng.

---

## Ghi nhớ

**Horner là cách đánh giá đa thức bằng nhân–cộng lồng nhau.** Với mảng hệ số tăng dần số mũ `[a0,a1,...,an]`, duyệt từ hệ số bậc cao về a0:

```text
result = 0
for i from n downTo 0:
    result = result*x + a[i]
```

Phương pháp tốn **O(n) phép số học** và **O(1) bộ nhớ phụ**. Horner mở rộng dùng đồng thời hai biến:

```text
derivative = derivative*x + OLD_value
value      = value*x + coefficient
```

để tính `P(x)` và `P'(x)`. Chia tổng hợp cho `x-r` cho phần dư **P(r)** và thương có thể khôi phục bằng các hệ số trung gian. Với môđun m, lấy phần dư trong từng bước Horner; với số nguyên lớn phải tránh overflow. Luôn kiểm tra quy ước **thứ tự hệ số**, chuẩn hóa số 0 ở bậc cao, phân biệt dense/sparse và xác minh bằng oracle độc lập.
