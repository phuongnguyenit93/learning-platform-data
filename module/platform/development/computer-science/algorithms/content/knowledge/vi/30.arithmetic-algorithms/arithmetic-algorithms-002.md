# Euclid mở rộng và nghiệm Bézout

> **Chủ đề:** Computer Science Algorithms → **Thuật toán số học** (*Number-Theoretic Algorithms*).  
> **Đầu ra cần nắm vững:** Từ hai số nguyên a, b, tìm `g = gcd(a,b)` **không âm** và hai hệ số nguyên x, y thỏa **đẳng thức Bézout** `a·x + b·y = g`. Hiểu vì sao thuật toán Euclid mở rộng tạo được x,y; xử lý a/b âm, số 0, tràn số; ứng dụng vào phương trình Diophantine tuyến tính, nghịch đảo modulo, đồng dư tuyến tính và CRT khi môđun không nguyên tố cùng nhau. Có chương trình Java 17 hoàn chỉnh và bộ kiểm chứng độc lập.

## 1. Euclid thường, Euclid mở rộng và đẳng thức Bézout

Thuật toán **Euclid thường** chỉ tìm **ước chung lớn nhất**:

`gcd(a,b)`.

Thuật toán **Euclid mở rộng** (*extended Euclidean algorithm*) còn tìm **hai số nguyên** x,y sao cho:

`a·x + b·y = gcd(a,b)`.

Đẳng thức trên được gọi là **đẳng thức Bézout**, và (x,y) là **một cặp hệ số Bézout**.

Ví dụ:

`240·(-9) + 46·47 = -2160 + 2162 = 2`.

Do `gcd(240,46)=2`, nên `x=-9`, `y=47` là một cặp hệ số Bézout.

**Quan trọng:** x,y **không nhất thiết dương**, và **không duy nhất**. Thuật toán trả về **một cặp nghiệm** theo trình tự chia Euclid đã chọn.

### 1.1. Quy ước về gcd

Trong bài học, `gcd(a,b)` luôn **không âm**.

- Nếu ít nhất một trong a,b khác 0 thì `gcd(a,b)>0`.
- `gcd(a,0)=|a|`.
- `gcd(0,b)=|b|`.
- Quy ước `gcd(0,0)=0`.

Khi `(a,b)=(0,0)`, phương trình Bézout có dạng `0·x+0·y=0` và **mọi cặp** (x,y) đều thỏa; chương trình chọn **(0,0)** làm kết quả chuẩn cho trường hợp này.

Khi a hoặc b âm, không được trả gcd âm chỉ vì phép chia trong ngôn ngữ lập trình dùng số âm.

### 1.2. “Mở rộng” không có nghĩa là đi tìm mọi x,y

Euclid mở rộng tính một bộ ba:

`(g,x,y)`.

Từ một cặp `(x0,y0)` mới có thể suy ra **toàn bộ các cặp hệ số Bézout**, nếu a,b không đồng thời bằng 0:

`x = x0 + (b/g)·t`

`y = y0 − (a/g)·t`,

với mọi `t∈ℤ`. Công thức tổng quát này sẽ được chứng minh sau.

## 2. Vì sao phép chia Euclid giữ nguyên gcd?

Với a,b **không âm** và b>0, tồn tại duy nhất thương q và số dư r sao cho:

`a = q·b + r`, với `0 ≤ r < b`.

Tương đương:

`r = a − q·b`.

Một số d chia hết cả a và b khi và chỉ khi d chia hết cả b và r:

- Nếu d|a, d|b thì d|(a−q·b)=r.
- Nếu d|b, d|r thì d|(q·b+r)=a.

Vì hai cặp có cùng tập ước chung:

`gcd(a,b) = gcd(b,r)`.

Lặp lại phép chia, số dư không âm **giảm nghiêm ngặt** khi khác 0, nên cuối cùng gặp số dư 0. **Số dư khác 0 cuối cùng là gcd**.

### 2.1. Ví dụ chuỗi chia với 240 và 46

```text
240 = 5 × 46 + 10
 46 = 4 × 10 +  6
 10 = 1 ×  6 +  4
  6 = 1 ×  4 +  2
  4 = 2 ×  2 +  0
```

Số dư khác 0 cuối cùng là 2:

`gcd(240,46)=2`.

| Lượt | a | b | q = a div b | r = a mod b |
|---:|---:|---:|---:|---:|
| 1 | 240 | 46 | 5 | 10 |
| 2 | 46 | 10 | 4 | 6 |
| 3 | 10 | 6 | 1 | 4 |
| 4 | 6 | 4 | 1 | 2 |
| 5 | 4 | 2 | 2 | 0 |

Thuật toán Euclid thường có thể dừng ở gcd=2. Nhưng nếu cần nghịch đảo modulo hoặc giải phương trình số nguyên, ta cần **x và y**.

## 3. Thế ngược để tìm hệ số Bézout

Ta sẽ đưa 2 về dạng tổ hợp tuyến tính của **hai số ban đầu** 240 và 46.

Từ chuỗi chia:

`2 = 6 − 1·4`.

Thay `4 = 10 − 1·6`:

`2 = 6 − (10−6) = 2·6 − 10`.

Thay `6 = 46 − 4·10`:

`2 = 2·(46−4·10) − 10 = 2·46 − 9·10`.

Thay `10 = 240 − 5·46`:

`2 = 2·46 − 9·(240−5·46)`.

Rút gọn:

`2 = (-9)·240 + 47·46`.

Vậy:

`g = 2`, `x = -9`, `y = 47`.

### 3.1. Ý tưởng thuật toán

Trong mỗi dòng chia Euclid, nếu đã biết cách viết **số dư kế tiếp** theo hai số ban đầu thì có thể tính ngược hệ số.

Euclid mở rộng tự động làm phép thế ngược đó bằng **truy hồi hệ số**, không cần lưu rồi thao tác lại toàn bộ các phương trình chia dưới dạng chuỗi.

### 3.2. Bất biến tổ hợp tuyến tính

Nếu tại một bước:

`a_current = s_a·A + t_a·B`

`b_current = s_b·A + t_b·B`,

với A,B là hai số ban đầu, thì r=`a_current − q·b_current` cũng là tổ hợp của A,B:

`r = (s_a − q·s_b)·A + (t_a − q·t_b)·B`.

Vì vậy mỗi số dư vẫn biểu diễn được bằng tổ hợp tuyến tính **với hệ số nguyên** của A và B. Khi một số dư chính là gcd, các hệ số tương ứng chính là nghiệm Bézout.

## 4. Euclid mở rộng dạng đệ quy

Giả sử a,b **không âm**. Nếu b=0, ta có:

`gcd(a,0)=a` và `a·1 + 0·0 = a`.

Trường hợp cơ sở:

`extended(a,0) = (a,1,0)`.

Nếu b>0, đặt:

`q = a div b`, `r = a mod b`.

Gọi đệ quy:

`extended(b,r) = (g,x1,y1)`.

Theo định nghĩa:

`b·x1 + r·y1 = g`.

Do `r=a−q·b`:

`b·x1 + (a−q·b)·y1 = g`.

Sắp xếp lại:

`a·y1 + b·(x1−q·y1) = g`.

Vậy kết quả cho (a,b) là:

`g = g`

`x = y1`

`y = x1 − q·y1`.

Đây là **công thức chuyển hệ số cốt lõi** của Euclid mở rộng.

### 4.1. Pseudocode

```text
extendedNonnegative(a, b):      // a >= 0, b >= 0
    if b == 0:
        return (g=a, x=1, y=0)

    q = a div b
    r = a mod b
    (g, x1, y1) = extendedNonnegative(b, r)

    return (g, x=y1, y=x1−q*y1)
```

**Không nhầm** `x=x1` và `y=y1`: khi đệ quy trở lên, hệ số đổi vai trò và y phải trừ thêm `q*y1`.

### 4.2. Kết quả của đệ quy phụ thuộc thứ tự số

Với (240,46), một kết quả là `(-9,47)`. Nếu đổi a,b thành (46,240), hệ số tương ứng là `(47,-9)`.

Không được so x,y theo một “đáp án chuẩn” duy nhất nếu thuật toán dùng thứ tự chia hoặc cách chuẩn hóa khác. Điều bắt buộc là:

`a*x+b*y = gcd(a,b)`

và gcd đúng, không âm.

## 5. Euclid mở rộng dạng lặp và hai cặp hệ số

Dạng lặp thường phù hợp khi muốn tránh đệ quy, dễ kiểm tra bất biến.

Khởi tạo với A,B không âm:

```text
oldR = A       r = B
oldS = 1       s = 0
oldT = 0       t = 1
```

Duy trì:

`oldR = oldS·A + oldT·B`

`r    = s·A + t·B`.

Ở mỗi lượt:

```text
q = oldR div r

(oldR, r) = (r, oldR−q*r)
(oldS, s) = (s, oldS−q*s)
(oldT, t) = (t, oldT−q*t)
```

Khi r=0:

`g = oldR`, `x = oldS`, `y = oldT`.

### 5.1. Tại sao bất biến đúng?

Ban đầu:

`oldR = A = 1·A+0·B`.

`r = B = 0·A+1·B`.

Sau một bước:

`newR = oldR−q*r`
`= (oldS−q*s)·A + (oldT−q*t)·B`.

Bằng cách cập nhật **cả hai cặp hệ số** đúng công thức, bất biến giữ nguyên. Khi r về 0, oldR là gcd theo Euclid và cũng có biểu diễn Bézout.

### 5.2. Bảng hệ số của ví dụ

Với A=240, B=46:

| Sau bước | oldR | r | oldS | oldT | s | t |
|---:|---:|---:|---:|---:|---:|---:|
| Ban đầu | 240 | 46 | 1 | 0 | 0 | 1 |
| q=5 | 46 | 10 | 0 | 1 | 1 | -5 |
| q=4 | 10 | 6 | 1 | -5 | -4 | 21 |
| q=1 | 6 | 4 | -4 | 21 | 5 | -26 |
| q=1 | 4 | 2 | 5 | -26 | -9 | 47 |
| q=2 | 2 | 0 | -9 | 47 | 23 | -120 |

Cuối cùng `oldR=2`, `oldS=-9`, `oldT=47`.

Kiểm từng dòng theo invariant, ví dụ dòng có `oldR=6`: `(-4)·240 + 21·46 = -960+966 = 6`.

### 5.3. Số âm: vì sao nên chuẩn hóa trước?

Phép chia có dư trên số âm khác nhau tùy ngôn ngữ. Trong Java, phép chia `long /` và remainder `%` với số âm không dùng chung quy ước số dư **không âm** như phép chia Euclid toán học.

Cách an toàn:

1. Chạy Euclid mở rộng trên `A=|a|`, `B=|b|`.
2. Thu `(g,xAbs,yAbs)` sao cho `|a|·xAbs+|b|·yAbs=g`.
3. Đổi lại hệ số:

   `x = sign(a)·xAbs`

   `y = sign(b)·yAbs`.

Với `sign(0)=0`, điều này vẫn hợp lệ cho trường hợp một số bằng 0. Trường hợp cả hai bằng 0 được xử lý riêng.

Ví dụ:

`(-240)·9 + 46·47 = -2160+2162=2`.

Do đó với a=-240,b=46, một kết quả là `(g=2,x=9,y=47)`.

**Lưu ý:** `Math.abs(Long.MIN_VALUE)` bị tràn vì `|−2^63|=2^63` không thể biểu diễn trong long có dấu. Dùng `BigInteger` tránh lỗi đó.

## 6. Java 17 — hai bản Euclid mở rộng có kiểm chứng

Chương trình này cài cả **đệ quy** và **lặp** trên `BigInteger`, thống nhất quy ước `(0,0)→(g=0,x=0,y=0)` và kiểm tra hai phương pháp trả cùng kết quả với cùng quy tắc chia.

Lưu thành **ExtendedEuclidBezoutDemo.java**:

```java
import java.math.BigInteger;

public class ExtendedEuclidBezoutDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;

    record Answer(BigInteger gcd, BigInteger x, BigInteger y) {
        boolean valid(BigInteger a, BigInteger b) {
            return a.multiply(x).add(b.multiply(y)).equals(gcd);
        }
    }

    static Answer recursiveNonnegative(BigInteger a, BigInteger b) {
        if (b.signum() == 0) {
            return new Answer(a, ONE, ZERO);
        }

        BigInteger[] qr = a.divideAndRemainder(b);
        BigInteger q = qr[0];
        BigInteger r = qr[1];
        Answer child = recursiveNonnegative(b, r);

        return new Answer(
                child.gcd(),
                child.y(),
                child.x().subtract(q.multiply(child.y())));
    }

    static Answer iterativeNonnegative(BigInteger a, BigInteger b) {
        BigInteger oldR = a, r = b;
        BigInteger oldS = ONE, s = ZERO;
        BigInteger oldT = ZERO, t = ONE;

        while (r.signum() != 0) {
            BigInteger q = oldR.divide(r);

            BigInteger nextR = oldR.subtract(q.multiply(r));
            BigInteger nextS = oldS.subtract(q.multiply(s));
            BigInteger nextT = oldT.subtract(q.multiply(t));

            oldR = r;
            r = nextR;
            oldS = s;
            s = nextS;
            oldT = t;
            t = nextT;
        }
        return new Answer(oldR, oldS, oldT);
    }

    static Answer extended(BigInteger a, BigInteger b,
                           boolean recursive) {
        if (a.signum() == 0 && b.signum() == 0) {
            return new Answer(ZERO, ZERO, ZERO);
        }

        BigInteger positiveA = a.abs();
        BigInteger positiveB = b.abs();
        Answer positive = recursive
                ? recursiveNonnegative(positiveA, positiveB)
                : iterativeNonnegative(positiveA, positiveB);

        BigInteger x = positive.x().multiply(
                BigInteger.valueOf(a.signum()));
        BigInteger y = positive.y().multiply(
                BigInteger.valueOf(b.signum()));
        return new Answer(positive.gcd(), x, y);
    }

    static void show(String as, String bs) {
        BigInteger a = new BigInteger(as);
        BigInteger b = new BigInteger(bs);

        Answer rec = extended(a, b, true);
        Answer iter = extended(a, b, false);
        if (!rec.equals(iter) || !rec.valid(a, b)
                || rec.gcd().signum() < 0
                || !rec.gcd().equals(a.gcd(b))) {
            throw new IllegalStateException(
                    "Mismatch between recursive and iterative EGCD");
        }

        System.out.println("(" + a + ", " + b + ") => gcd="
                + rec.gcd() + ", x=" + rec.x() + ", y=" + rec.y()
                + ", verified=" + rec.valid(a, b));
    }

    public static void main(String[] args) {
        show("240", "46");
        show("30", "18");
        show("99", "78");
        show("-240", "46");
        show("0", "-7");
        show("0", "0");

        // |Long.MIN_VALUE| vượt phạm vi long, nhưng BigInteger xử lý được.
        show("-9223372036854775808", "0");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ExtendedEuclidBezoutDemo.java
java ExtendedEuclidBezoutDemo
```

Stdout:

```text
(240, 46) => gcd=2, x=-9, y=47, verified=true
(30, 18) => gcd=6, x=-1, y=2, verified=true
(99, 78) => gcd=3, x=-11, y=14, verified=true
(-240, 46) => gcd=2, x=9, y=47, verified=true
(0, -7) => gcd=7, x=0, y=-1, verified=true
(0, 0) => gcd=0, x=0, y=0, verified=true
(-9223372036854775808, 0) => gcd=9223372036854775808, x=-1, y=0, verified=true
```

### 6.1. Tại sao đệ quy và lặp giống nhau trong chương trình?

Cả hai dùng **cùng phép chia Euclid trên số không âm**, cùng trường hợp cơ sở `(a,0)→(a,1,0)`. Một bản tính hệ số từ đáy truy hồi lên, một bản biến đổi hệ số ở từng vòng. Vì cùng quy tắc, trên các input kiểm thử chúng cho **cùng bộ ba**, không chỉ cùng gcd.

Đừng suy rằng mọi implementation EGCD phải trả cùng x,y: thay cách khởi tạo/chuẩn hóa hoặc dịch nghiệm bằng tham số t có thể cho cặp khác nhưng vẫn đúng.

### 6.2. Vì sao BigInteger rất quan trọng?

Công thức tính hệ số có phép nhân `q·y1` hoặc `q·s`. Nếu dùng `int`, `long`, các phép trung gian có thể tràn; ngay phép lấy giá trị tuyệt đối của `Long.MIN_VALUE` cũng tràn với `Math.abs(long)`.

`BigInteger` hỗ trợ:

- `abs()`, `signum()`.
- `divideAndRemainder()`.
- `multiply()`, `subtract()`, `add()`.
- `gcd()` để làm **oracle kiểm chứng** (không thay thế việc giải thích thuật toán).

Bản BigInteger không bị tràn theo miền số nguyên hữu hạn, nhưng vẫn cần đủ bộ nhớ và thời gian cho số rất lớn.

### 6.3. Không chép `long` vào `BigInteger` rồi cast ngược tùy tiện

Với `a=Long.MIN_VALUE,b=0`, gcd bằng **9223372036854775808**, vượt `Long.MAX_VALUE`. Nếu ép về long, mất giá trị đúng. Chỉ chuyển về long bằng `longValueExact()` khi đã chứng minh giá trị nằm trong miền.

### 6.4. Quy tắc `%` với số âm

Trong cách cài này, phần đệ quy chỉ nhận `a.abs(), b.abs()` không âm; vì vậy `divideAndRemainder` tạo phần dư không âm. Khi cần tính modulo số âm ở ứng dụng, dùng `BigInteger.mod(m)` với `m>0` để chuẩn hóa số dư trong `[0,m)`.

## 7. Chứng minh đẳng thức Bézout tồn tại

Định lý Bézout nói rằng, với hai số nguyên a,b không đồng thời bằng 0, tồn tại x,y∈ℤ sao cho:

`a·x+b·y=gcd(a,b)`.

### 7.1. Chứng minh bằng Euclid mở rộng

Làm việc trước với A=|a|, B=|b|.

- Ở bước cơ sở b=0, `(g,x,y)=(a,1,0)` đúng.
- Giả sử lời giải đệ quy cho `(b,r)` thỏa `b·x1+r·y1=g`.
- Thay `r=a−q·b` và chọn `x=y1`, `y=x1−q·y1`, ta được `a·x+b·y=g`.

Quy nạp ngược theo số bước của Euclid cho hệ số nguyên ở cặp ban đầu. Đổi dấu hệ số theo dấu của a,b giữ nguyên đẳng thức.

Đồng thời Euclid bảo toàn gcd, nên g đúng là gcd của cặp ban đầu.

### 7.2. Gcd là tổ hợp tuyến tính dương nhỏ nhất

Với a,b không đồng thời bằng 0, xét tập:

`S = {a·x+b·y > 0 : x,y∈ℤ}`.

Đẳng thức Bézout cho thấy `g=gcd(a,b)` thuộc S. Mọi tổ hợp `a·x+b·y` đều chia hết cho g vì g chia hết a,b. Do đó mọi phần tử dương của S ít nhất bằng g.

Vậy **g là số nguyên dương nhỏ nhất có thể biểu diễn thành tổ hợp tuyến tính của a,b**.

Một hệ quả quan trọng: phương trình `a·x+b·y=c` có nghiệm nguyên **khi và chỉ khi** `g|c` (nếu a,b không đồng thời 0).

### 7.3. Không suy ra một cặp hệ số duy nhất

Nếu `(x0,y0)` thỏa Bézout và g>0, mọi cặp:

`x=x0+(b/g)·t`,
`y=y0−(a/g)·t`

cũng thỏa:

`a·x+b·y = a·x0+b·y0 + t·(a·b/g−b·a/g) = g`.

Ví dụ với a=240,b=46:

`x=-9+23t`, `y=47−120t`.

- t=0: `(-9,47)`.
- t=1: `(14,-73)`.

Kiểm: `240·14+46·(-73)=3360−3358=2`.

### 7.4. Vì sao đây là tất cả nghiệm?

Giả sử một cặp (x,y) khác cũng cho g. Lấy hiệu với cặp gốc:

`a·(x−x0)+b·(y−y0)=0`.

Chia cho g:

`(a/g)·Δx = −(b/g)·Δy`.

Do `gcd(a/g,b/g)=1`, tính nguyên tố cùng nhau suy ra `b/g` chia hết Δx và `a/g` chia hết Δy với tham số t tương ứng. Thu được chính xác:

`Δx=(b/g)t`, `Δy=−(a/g)t`.

Lập luận này cũng đúng khi đúng một trong a,b bằng 0 (với quy ước chia g>0); nếu cả hai bằng 0 thì nghiệm phải xét riêng.

## 8. Phương trình Diophantine tuyến tính

**Phương trình Diophantine tuyến tính hai biến**:

`a·x+b·y=c`, với a,b,c nguyên và yêu cầu x,y **nguyên**.

Nếu `(a,b)≠(0,0)`, đặt `g=gcd(a,b)>0`.

**Điều kiện có nghiệm:** `c` chia hết cho g.

### 8.1. Chứng minh điều kiện cần

Nếu `a·x+b·y=c`, do g chia cả a và b nên g chia tổng bên trái. Vậy `g|c`.

### 8.2. Chứng minh điều kiện đủ

Nếu `c=g·k`, từ Bézout có `a·u+b·v=g`. Nhân k:

`a·(u·k)+b·(v·k)=c`.

Vậy một nghiệm riêng:

`x0=u·(c/g)`, `y0=v·(c/g)`.

### 8.3. Toàn bộ nghiệm

Khi g|c:

`x = x0 + (b/g)·t`

`y = y0 − (a/g)·t`

với **mọi t∈ℤ**.

Mọi nghiệm đều có dạng này theo lập luận lấy hiệu hai nghiệm.

### 8.4. Ví dụ 30x+18y=6

Ta có:

`gcd(30,18)=6`, Bézout: `30·(-1)+18·2=6`.

Nghiệm riêng:

`(x0,y0)=(-1,2)`.

Tất cả nghiệm:

`x=-1+3t`, `y=2−5t`.

Với t=1, được `(x,y)=(2,-3)`:

`30·2+18·(-3)=60−54=6`.

Với t=0, cặp (-1,2) cũng thỏa.

### 8.5. Ví dụ vô nghiệm

`30x+18y=5`.

Vì gcd=6 **không chia hết 5**, không có nghiệm nguyên, dù có vô số nghiệm thực.

**Không nhầm:** phương trình hai biến thực có thể có nghiệm dù Diophantine nguyên vô nghiệm.

### 8.6. Trường hợp cả a và b bằng 0

`0·x+0·y=c`.

- Nếu c=0: **mọi cặp số nguyên (x,y)** là nghiệm.
- Nếu c≠0: **không có nghiệm**.

Không áp công thức `c/g` khi g=0; sẽ chia cho 0.

### 8.7. Thêm ràng buộc x,y≥0

Nghiệm Diophantine nguyên chưa chắc có nghiệm **không âm**.

Trong ví dụ `30x+18y=6`, thay `x=-1+3t`, `y=2−5t`:

- x≥0 ⇒ t≥1.
- y≥0 ⇒ t≤0.

Hai điều kiện mâu thuẫn, nên **không có nghiệm không âm**, dù có vô số nghiệm nguyên.

Với `30x+18y=60`:

- Nghiệm riêng từ Bézout nhân 10: `(-10,20)`.
- `x=-10+3t`, `y=20−5t`.
- x≥0 ⇒ t≥4; y≥0 ⇒ t≤4.

Chỉ t=4, cho `(x,y)=(2,0)`.

Khi gặp giới hạn như `0≤x≤X`, `0≤y≤Y`, hãy chuyển từng bất đẳng thức về khoảng cho t, chú ý **đảo chiều khi chia số âm**, và dùng `floorDiv/ceilDiv` đúng với số âm. Không chọn nghiệm tùy tiện rồi tin nó thỏa giới hạn.

## 9. Java 17 — giải Diophantine và tham số hóa

Chương trình này độc lập, sử dụng Euclid mở rộng BigInteger và phân biệt ba trạng thái: **vô nghiệm**, **mọi cặp đều nghiệm**, **họ nghiệm một tham số**.

Lưu thành **BezoutDiophantineDemo.java**:

```java
import java.math.BigInteger;

public class BezoutDiophantineDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;

    record Egcd(BigInteger g, BigInteger x, BigInteger y) {}

    static Egcd nonnegative(BigInteger a, BigInteger b) {
        if (b.signum() == 0) return new Egcd(a, ONE, ZERO);
        BigInteger[] qr = a.divideAndRemainder(b);
        Egcd sub = nonnegative(b, qr[1]);
        return new Egcd(
                sub.g(), sub.y(),
                sub.x().subtract(qr[0].multiply(sub.y())));
    }

    static Egcd extended(BigInteger a, BigInteger b) {
        if (a.signum() == 0 && b.signum() == 0) {
            return new Egcd(ZERO, ZERO, ZERO);
        }
        Egcd r = nonnegative(a.abs(), b.abs());
        return new Egcd(
                r.g(),
                r.x().multiply(BigInteger.valueOf(a.signum())),
                r.y().multiply(BigInteger.valueOf(b.signum())));
    }

    record Solution(String type, BigInteger g,
                    BigInteger x0, BigInteger y0,
                    BigInteger dx, BigInteger dy) {
        BigInteger x(BigInteger t) {
            return x0.add(dx.multiply(t));
        }

        BigInteger y(BigInteger t) {
            return y0.add(dy.multiply(t));
        }
    }

    static Solution solve(BigInteger a, BigInteger b, BigInteger c) {
        Egcd r = extended(a, b);
        if (r.g().signum() == 0) {
            return new Solution(c.signum() == 0 ? "ALL" : "NONE",
                    ZERO, ZERO, ZERO, ZERO, ZERO);
        }
        if (!c.remainder(r.g()).equals(ZERO)) {
            return new Solution("NONE", r.g(),
                    ZERO, ZERO, ZERO, ZERO);
        }

        BigInteger factor = c.divide(r.g());
        return new Solution(
                "PARAMETRIC", r.g(),
                r.x().multiply(factor),
                r.y().multiply(factor),
                b.divide(r.g()),
                a.divide(r.g()).negate());
    }

    static void print(String as, String bs, String cs) {
        BigInteger a = new BigInteger(as);
        BigInteger b = new BigInteger(bs);
        BigInteger c = new BigInteger(cs);
        Solution sol = solve(a, b, c);

        String prefix = a + "x + " + b + "y = " + c + ": ";
        if (sol.type().equals("NONE")) {
            System.out.println(prefix + "no integer solution");
            return;
        }
        if (sol.type().equals("ALL")) {
            System.out.println(prefix + "all integer pairs");
            return;
        }

        System.out.println(prefix + "gcd=" + sol.g()
                + ", base=(" + sol.x0() + "," + sol.y0() + ")"
                + ", step=(" + sol.dx() + "," + sol.dy() + ")");

        if (!a.multiply(sol.x0()).add(
                b.multiply(sol.y0())).equals(c)) {
            throw new IllegalStateException("Bad base solution");
        }
    }

    public static void main(String[] args) {
        print("30", "18", "6");
        Solution one = solve(
                new BigInteger("30"),
                new BigInteger("18"),
                new BigInteger("6"));
        BigInteger t = ONE;
        BigInteger x = one.x(t), y = one.y(t);
        System.out.println("t=1: (" + x + "," + y
                + "), verified="
                + new BigInteger("30").multiply(x).add(
                        new BigInteger("18").multiply(y))
                        .equals(new BigInteger("6")));

        print("30", "18", "5");
        print("30", "18", "60");

        Solution sixty = solve(
                new BigInteger("30"), new BigInteger("18"),
                new BigInteger("60"));
        BigInteger four = new BigInteger("4");
        System.out.println("c=60, t=4: ("
                + sixty.x(four) + "," + sixty.y(four)
                + "), nonnegative="
                + (sixty.x(four).signum() >= 0
                   && sixty.y(four).signum() >= 0));

        print("0", "0", "0");
        print("0", "0", "7");
        print("0", "-7", "14");
        print("-15", "25", "5");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BezoutDiophantineDemo.java
java BezoutDiophantineDemo
```

Stdout:

```text
30x + 18y = 6: gcd=6, base=(-1,2), step=(3,-5)
t=1: (2,-3), verified=true
30x + 18y = 5: no integer solution
30x + 18y = 60: gcd=6, base=(-10,20), step=(3,-5)
c=60, t=4: (2,0), nonnegative=true
0x + 0y = 0: all integer pairs
0x + 0y = 7: no integer solution
0x + -7y = 14: gcd=7, base=(0,-2), step=(-1,0)
-15x + 25y = 5: gcd=5, base=(-2,-1), step=(5,3)
```

### 9.1. Tại sao bước dx,dy có thể âm hoặc 0?

Theo công thức:

`dx=b/g`, `dy=−a/g`.

Nếu b âm, dx âm. Nếu a=0, dy=0: y cố định và x tự do theo một bước ±1 nếu |b|=g. Ví dụ `0x−7y=14` có y=-2, x tùy ý; chương trình cho `x=0−t`, `y=-2`.

### 9.2. Nghiệm riêng không nhất thiết nhỏ nhất

`x0,y0` do Euclid trả có thể có giá trị âm hoặc trị tuyệt đối lớn; nó chỉ là một **nghiệm riêng**. Muốn nghiệm x,y không âm, nhỏ nhất theo tổng, hoặc tối thiểu |x|, cần **chọn t** theo ràng buộc/mục tiêu phụ.

### 9.3. Lỗi chia modulo với c âm

Điều kiện g|c kiểm bằng `c.remainder(g).equals(ZERO)` với g>0; dấu của c không ảnh hưởng tính chia hết. Còn **chuẩn hóa số dư modulo** trong một lớp đồng dư dùng `c.mod(m)` với m>0.

## 10. Nghịch đảo modulo từ hệ số Bézout

Cho số nguyên a và môđun `m≥2`. **Nghịch đảo nhân modulo m** của a là số nguyên r thỏa:

`a·r ≡ 1 (mod m)`.

Một nghịch đảo tồn tại **khi và chỉ khi**:

`gcd(a,m)=1`.

### 10.1. Vì sao điều kiện gcd=1 là cần?

Nếu a·r≡1 mod m, có số nguyên q sao cho:

`a·r−m·q=1`.

Tức 1 là một tổ hợp nguyên của a và m. Bất kỳ ước chung nào của a,m đều phải chia 1, nên gcd(a,m)=1.

### 10.2. Vì sao điều kiện gcd=1 là đủ?

Euclid mở rộng cho:

`a·x + m·y = 1`.

Lấy modulo m:

`a·x ≡ 1 (mod m)`.

Vậy x là một nghịch đảo. Có thể chuẩn hóa:

`inverse = x mod m`

để nhận đại diện chuẩn trong `[0,m)`.

### 10.3. Ví dụ 3 modulo 11

Euclid mở rộng:

`11 = 3·3 + 2`.

`3 = 1·2 + 1`.

Thế ngược:

`1 = 3 − (11−3·3) = 4·3 − 1·11`.

Vậy nghịch đảo của 3 modulo 11 là **4**, vì:

`3·4 = 12 ≡ 1 (mod 11)`.

### 10.4. Ví dụ a âm

Nghịch đảo của -3 mod11 là **7**:

`(-3)·7 = -21 ≡ 1 (mod 11)`,

vì -21+22=1.

Trong Java, chuẩn hóa bằng `BigInteger.mod(BigInteger.valueOf(11))` giúp số dư **không âm**.

### 10.5. Ví dụ không có nghịch đảo

6 modulo 9 không có nghịch đảo vì `gcd(6,9)=3>1`. Không được dùng lũy thừa `6^(m−2)` theo định lý Fermat nếu m không nguyên tố và cũng không thỏa các giả thiết thích hợp.

### 10.6. Môđun bằng 1

Nghịch đảo trong môđun1 không được định nghĩa theo quy ước thông dụng cho nhóm các phần tử khả nghịch với 1 khác 0; chương trình `inverseOrNull` yêu cầu **m≥2**. Phương trình đồng dư modulo1 lại có cách hiểu riêng là mọi số nguyên đồng dư với 0 — sẽ xử lý ở phần tiếp.

## 11. Đồng dư tuyến tính a·x ≡ b (mod m)

Cho m>0, tìm mọi số nguyên x sao cho:

`a·x ≡ b (mod m)`.

Tương đương tồn tại y nguyên:

`a·x − m·y = b`.

Đặt `g=gcd(a,m)` (luôn >0 vì m>0).

**Có nghiệm khi và chỉ khi g chia hết b.**

### 11.1. Khử ước chung

Nếu g|b, chia cả a,b,m cho g:

`a' = a/g`, `b'=b/g`, `m'=m/g`.

Khi ấy:

`a'·x ≡ b' (mod m')`.

Vì `gcd(a',m')=1`, nếu `m'≥2`, tồn tại nghịch đảo của a' modulo m' và:

`x0 ≡ b'·(a')^(-1) (mod m')`.

Tất cả nghiệm nguyên:

`x=x0+m'·t`, với t∈ℤ.

### 11.2. Số lớp nghiệm modulo m

Trong khoảng đại diện `[0,m)`, nếu g|b có **đúng g lớp nghiệm**:

`x0, x0+m', ..., x0+(g−1)m'`.

Nếu g không chia b, số nghiệm bằng 0.

### 11.3. Ví dụ 6x ≡ 9 (mod 15)

Ta có `gcd(6,15)=3`, 9 chia hết3 nên có nghiệm.

Chia 3:

`2x ≡ 3 (mod 5)`.

Nghịch đảo của 2 modulo5 là3, nên:

`x ≡ 3·3 ≡ 4 (mod 5)`.

Các lớp nghiệm modulo15 là:

`x ∈ {4,9,14}`.

Kiểm:

`6·4=24≡9 mod15`,
`6·9=54≡9 mod15`,
`6·14=84≡9 mod15`.

Nếu phương trình là `6x≡8 mod15`, vì 3 không chia8 nên **vô nghiệm**.

### 11.4. Trường hợp a=0

`0·x≡b mod m` có nghiệm khi và chỉ khi `b≡0 mod m`.

Nếu đúng, **mọi số nguyên x** đều là nghiệm. Khi đó g=m, m'=1, biểu diễn thống nhất:

`x≡0 (mod 1)`.

Không được gọi thuật toán nghịch đảo modulo1 trong trường hợp này; trực tiếp chọn x0=0.

## 12. Java 17 — nghịch đảo và đồng dư tổng quát

Chương trình độc lập này dùng `BigInteger` để tránh overflow, hỗ trợ a,b âm, m dương và in số lớp nghiệm theo modulo gốc.

Lưu thành **BezoutModularInverseDemo.java**:

```java
import java.math.BigInteger;

public class BezoutModularInverseDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;

    record Egcd(BigInteger g, BigInteger x, BigInteger y) {}

    static Egcd nonnegative(BigInteger a, BigInteger b) {
        if (b.signum() == 0) return new Egcd(a, ONE, ZERO);
        BigInteger[] qr = a.divideAndRemainder(b);
        Egcd child = nonnegative(b, qr[1]);
        return new Egcd(
                child.g(), child.y(),
                child.x().subtract(qr[0].multiply(child.y())));
    }

    static Egcd extended(BigInteger a, BigInteger b) {
        if (a.signum() == 0 && b.signum() == 0) {
            return new Egcd(ZERO, ZERO, ZERO);
        }
        Egcd r = nonnegative(a.abs(), b.abs());
        return new Egcd(
                r.g(),
                r.x().multiply(BigInteger.valueOf(a.signum())),
                r.y().multiply(BigInteger.valueOf(b.signum())));
    }

    // null nếu không có nghịch đảo; yêu cầu m >= 2.
    static BigInteger inverseOrNull(BigInteger a, BigInteger m) {
        if (m.compareTo(ONE) <= 0) {
            throw new IllegalArgumentException("Modulus must be >= 2");
        }
        Egcd r = extended(a, m);
        return r.g().equals(ONE) ? r.x().mod(m) : null;
    }

    record Congruence(boolean solvable, BigInteger residue,
                      BigInteger period, BigInteger classesModM) {}

    static Congruence solveLinear(
            BigInteger a, BigInteger b, BigInteger m) {
        if (m.signum() <= 0) {
            throw new IllegalArgumentException("Modulus must be positive");
        }
        Egcd r = extended(a, m);
        BigInteger g = r.g();

        if (!b.mod(g).equals(ZERO)) {
            return new Congruence(false, ZERO, ZERO, ZERO);
        }

        BigInteger period = m.divide(g);
        BigInteger residue;
        if (period.equals(ONE)) {
            // Đồng dư modulo 1: mọi số nguyên x đều hợp lệ.
            residue = ZERO;
        } else {
            BigInteger reducedA = a.divide(g);
            BigInteger reducedB = b.divide(g);
            BigInteger inverse = inverseOrNull(reducedA, period);
            if (inverse == null) {
                throw new IllegalStateException(
                        "Reduced a must be invertible");
            }
            residue = inverse.multiply(reducedB).mod(period);
        }
        return new Congruence(true, residue, period, g);
    }

    static void showInverse(String as, String ms) {
        BigInteger a = new BigInteger(as);
        BigInteger m = new BigInteger(ms);
        BigInteger inv = inverseOrNull(a, m);
        System.out.println("inverse(" + a + " mod " + m + ") = "
                + (inv == null ? "none" : inv));
        if (inv != null
                && !a.multiply(inv).mod(m).equals(ONE)) {
            throw new IllegalStateException("Bad inverse");
        }
    }

    static void showCongruence(String as, String bs, String ms) {
        BigInteger a = new BigInteger(as);
        BigInteger b = new BigInteger(bs);
        BigInteger m = new BigInteger(ms);
        Congruence c = solveLinear(a, b, m);

        String head = a + "x ≡ " + b + " (mod " + m + "): ";
        if (!c.solvable()) {
            System.out.println(head + "no solution");
            return;
        }

        if (!a.multiply(c.residue()).subtract(b)
                .mod(m).equals(ZERO)) {
            throw new IllegalStateException("Bad residue");
        }
        System.out.println(head + "x ≡ " + c.residue()
                + " (mod " + c.period() + ")"
                + "; classes modulo " + m + " = "
                + c.classesModM());
    }

    public static void main(String[] args) {
        showInverse("3", "11");
        showInverse("-3", "11");
        showInverse("10", "17");
        showInverse("6", "9");

        showCongruence("6", "9", "15");
        showCongruence("6", "8", "15");
        showCongruence("0", "0", "7");
        showCongruence("0", "3", "7");
        showCongruence("-4", "8", "12");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BezoutModularInverseDemo.java
java BezoutModularInverseDemo
```

Stdout:

```text
inverse(3 mod 11) = 4
inverse(-3 mod 11) = 7
inverse(10 mod 17) = 12
inverse(6 mod 9) = none
6x ≡ 9 (mod 15): x ≡ 4 (mod 5); classes modulo 15 = 3
6x ≡ 8 (mod 15): no solution
0x ≡ 0 (mod 7): x ≡ 0 (mod 1); classes modulo 7 = 7
0x ≡ 3 (mod 7): no solution
-4x ≡ 8 (mod 12): x ≡ 1 (mod 3); classes modulo 12 = 4
```

### 12.1. Nghịch đảo phải dùng modulo dương

Java `BigInteger.mod(m)` yêu cầu m>0. Trong `solveLinear`, g=gcd(a,m)>0 vì m>0. Trong `inverseOrNull`, m≥2, nên chuẩn hóa `r.x().mod(m)` luôn nhận đại diện `[0,m)`.

### 12.2. Không dùng một nghiệm đại diện để suy hết lớp nghiệm

Trong `6x≡9 mod15`, `residue=4`, `period=5` nghĩa là:

`x=4+5t`.

Có **3 đại diện** trong modulo15: 4,9,14. In mỗi residue4 mà quên period5 có thể làm người dùng tưởng chỉ có một lớp nghiệm modulo15.

### 12.3. Vì sao không lấy `inverse(a,m)` khi gcd>1?

Không tồn tại số x sao cho `a·x≡1 modm` nếu gcd(a,m)>1. Với đồng dư có vế phải b, ta phải **chia cả a,b,m cho gcd** trước; chỉ sau đó a' mới có nghịch đảo modulo m'.

## 13. CRT không yêu cầu hai môđun nguyên tố cùng nhau

Định lý số dư Trung Hoa (*Chinese Remainder Theorem*, CRT) thường được dạy trong trường hợp các môđun nguyên tố cùng nhau. Với Euclid mở rộng, ta còn có thể hợp nhất **hai đồng dư bất kỳ có môđun dương**:

`x ≡ r1 (mod m1)`,

`x ≡ r2 (mod m2)`.

Đặt `g=gcd(m1,m2)`.

**Điều kiện có nghiệm:**

`g | (r2−r1)`.

Tức **hai residue phải tương thích modulo gcd**.

### 13.1. Suy ra từ Bézout

Viết `x=r1+m1·t`. Thay vào đồng dư thứ hai:

`m1·t ≡ r2−r1 (mod m2)`.

Đây chính là bài đồng dư tuyến tính của phần trước.

Nếu g không chia `r2−r1` ⇒ vô nghiệm.

Nếu g chia, đặt:

`m1'=m1/g`, `m2'=m2/g`, `d=(r2−r1)/g`.

Khi ấy:

`m1'·t ≡ d (mod m2')`.

Do `gcd(m1',m2')=1`, dùng Euclid mở rộng tìm nghịch đảo của m1' modulo m2' (khi m2'>1), rồi:

`t0 ≡ d·inverse(m1',m2') (mod m2')`.

Sau đó:

`x0=r1+m1·t0`.

Tất cả nghiệm:

`x ≡ x0 (mod lcm(m1,m2))`

với:

`lcm(m1,m2)=m1·(m2/g)`.

Nếu m2'=1, đồng dư rút gọn modulo1 hiển nhiên đúng, chọn t0=0.

### 13.2. Ví dụ tương thích

`x≡2 mod6`, `x≡5 mod9`.

gcd(6,9)=3 và (5−2)=3 chia hết3. Nghiệm:

`x≡14 mod18`,

vì 14 mod6=2, 14 mod9=5; lcm(6,9)=18.

### 13.3. Ví dụ không tương thích

`x≡2 mod6`, `x≡4 mod9`.

gcd=3 nhưng 4−2=2 không chia hết3 ⇒ **không có x** thỏa cả hai.

### 13.4. Residue âm

`x≡−1 mod8`, `x≡5 mod6` có nghiệm:

`x≡23 mod24`.

Vì −1 mod8 tương đương7 mod8, và 23 mod8=7, 23 mod6=5.

Luôn chuẩn hóa residue trong `[0,modulus)` trước khi trả.

## 14. Java 17 — hợp nhất hai lớp đồng dư bằng Bézout

Chương trình độc lập dưới sử dụng Euclid mở rộng cho m1,m2 và tránh giả định hai môđun nguyên tố cùng nhau.

Lưu thành **BezoutGeneralizedCrtDemo.java**:

```java
import java.math.BigInteger;

public class BezoutGeneralizedCrtDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;

    record Egcd(BigInteger g, BigInteger x, BigInteger y) {}
    record Congruence(BigInteger residue, BigInteger modulus) {}

    static Egcd extendedNonnegative(BigInteger a, BigInteger b) {
        if (b.equals(ZERO)) return new Egcd(a, ONE, ZERO);
        BigInteger[] qr = a.divideAndRemainder(b);
        Egcd child = extendedNonnegative(b, qr[1]);
        return new Egcd(child.g(), child.y(),
                child.x().subtract(qr[0].multiply(child.y())));
    }

    static Congruence canonical(BigInteger r, BigInteger m) {
        if (m.signum() <= 0) {
            throw new IllegalArgumentException("Modulus must be positive");
        }
        return new Congruence(r.mod(m), m);
    }

    static Congruence merge(Congruence c1, Congruence c2) {
        Congruence a = canonical(c1.residue(), c1.modulus());
        Congruence b = canonical(c2.residue(), c2.modulus());

        BigInteger m1 = a.modulus(), m2 = b.modulus();
        Egcd eg = extendedNonnegative(m1, m2);
        BigInteger g = eg.g();
        BigInteger diff = b.residue().subtract(a.residue());

        if (!diff.mod(g).equals(ZERO)) {
            return null; // Hai đồng dư mâu thuẫn modulo gcd.
        }

        BigInteger reducedM2 = m2.divide(g);
        BigInteger t;
        if (reducedM2.equals(ONE)) {
            t = ZERO;
        } else {
            // eg.x*m1 + eg.y*m2 = g.
            // => eg.x là nghịch đảo của m1/g modulo m2/g.
            t = eg.x().multiply(diff.divide(g)).mod(reducedM2);
        }

        BigInteger lcm = m1.multiply(reducedM2);
        BigInteger x0 = a.residue().add(m1.multiply(t)).mod(lcm);
        return new Congruence(x0, lcm);
    }

    static void show(String label, String r1, String m1,
                     String r2, String m2) {
        Congruence first = canonical(
                new BigInteger(r1), new BigInteger(m1));
        Congruence second = canonical(
                new BigInteger(r2), new BigInteger(m2));
        Congruence result = merge(first, second);

        if (result == null) {
            System.out.println(label + ": no solution");
            return;
        }

        if (!result.residue().mod(first.modulus())
                    .equals(first.residue())
                || !result.residue().mod(second.modulus())
                    .equals(second.residue())) {
            throw new IllegalStateException("CRT result invalid");
        }

        System.out.println(label + ": x ≡ "
                + result.residue() + " (mod " + result.modulus() + ")");
    }

    public static void main(String[] args) {
        show("Compatible", "2", "6", "5", "9");
        show("Contradictory", "2", "6", "4", "9");
        show("Negative residue", "-1", "8", "5", "6");
        show("Nested moduli", "14", "18", "2", "4");
        show("Zero residues", "0", "4", "0", "6");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BezoutGeneralizedCrtDemo.java
java BezoutGeneralizedCrtDemo
```

Stdout:

```text
Compatible: x ≡ 14 (mod 18)
Contradictory: no solution
Negative residue: x ≡ 23 (mod 24)
Nested moduli: x ≡ 14 (mod 36)
Zero residues: x ≡ 0 (mod 12)
```

### 14.1. Vì sao dùng hệ số eg.x của `m1,m2`?

Extended Euclid trên (m1,m2) cho:

`eg.x·m1 + eg.y·m2 = g`.

Chia cho g:

`eg.x·(m1/g) + eg.y·(m2/g) = 1`.

Nên `eg.x` là nghịch đảo của `m1/g` modulo `m2/g`, khi môđun rút gọn >1. Điều này tránh chạy EGCD thêm một lần trong merge.

### 14.2. Vì sao môđun đáp án là lcm?

Nếu x0 thỏa cả hai đồng dư, x0+k·m1 vẫn thỏa đồng dư thứ nhất, nhưng để đồng thời thỏa đồng dư thứ hai, lượng thay đổi phải là bội chung của m1,m2. Chu kỳ dương nhỏ nhất là **lcm(m1,m2)**.

### 14.3. Hợp nhiều đồng dư

Để ghép `x≡r_i mod m_i` cho nhiều i, bắt đầu từ một lớp đồng dư hợp lệ, rồi lần lượt gọi `merge`. Nếu một lần trả `null`, cả hệ **vô nghiệm**. Nếu mọi bước thành công, lớp cuối biểu diễn mọi nghiệm theo modulo lcm của toàn bộ môđun.

Không được lạm dụng CRT coprime khi môđun có gcd>1; trường hợp tương thích vẫn có nghiệm, nhưng chu kỳ là lcm chứ không phải tích máy móc.

## 15. Độ phức tạp và rủi ro số lớn

### 15.1. Số vòng chia

Trong Euclid thường và mở rộng, mỗi bước thay `(a,b)` bằng `(b,a mod b)`, phần dư giảm. Với a,b không âm và b>0, số phép chia là:

**`O(log min(a,b))`** theo số vòng lặp (trường hợp xấu gắn với các số Fibonacci liên tiếp).

Khi một số bằng 0, kết quả gcd và hệ số được xử lý ngay theo quy ước.

### 15.2. Độ phức tạp bit

Khi a,b là `BigInteger` nhiều chữ số, **một phép chia/nhân không có chi phí O(1)**. Số vòng Euclid vẫn log theo độ lớn số, nhưng chi phí theo bit còn tùy thuật toán số học đa độ chính xác của thư viện.

Nói “Euclid mở rộng O(log min(a,b))” là cách nói về **số vòng chia**, không phải luôn là thời gian thực theo mọi biểu diễn số.

### 15.3. Bộ nhớ

Bản lặp giữ một số hằng các biến số lớn ⇒ **O(1) đối tượng trạng thái** nếu bỏ qua kích thước bit của số nguyên.

Bản đệ quy thêm stack với chiều sâu bằng số bước chia ⇒ O(log min(a,b)) frame trong trường hợp số dương.

Độ lớn bit của các hệ số cũng đáng kể. Với dữ liệu gần giới hạn long, các tích trung gian dùng `q*coefficient` có thể overflow nếu cố dùng `long`.

### 15.4. Mối liên hệ với Fibonacci

Các cặp Fibonacci liên tiếp tạo chuỗi Euclid có nhiều phép chia với thương q=1, ví dụ:

`gcd(89,55)`, `gcd(144,89)`.

Chúng thường được dùng để stress test số vòng Euclid, nhưng vẫn có số vòng theo log của kích thước input.

## 16. Các lỗi triển khai thường gặp

### Lỗi 1 — Chỉ trả gcd mà không trả x,y

Đề yêu cầu **nghiệm Bézout**, không chỉ cần số ước chung lớn nhất. Phải trả `(g,x,y)` và kiểm `a*x+b*y=g`.

### Lỗi 2 — Nhầm hệ số khi quay lui đệ quy

Đúng: nếu lời gọi `(b,r)` trả `(g,x1,y1)`, thì lời gọi `(a,b)` trả `x=y1`, `y=x1−q*y1`. Không giữ nguyên x1,y1.

### Lỗi 3 — Không xử lý `(0,0)`

`gcd(0,0)=0` theo quy ước; mọi x,y thỏa Bézout. Không được chia cho gcd=0 khi suy nghiệm tổng quát hay giải Diophantine.

### Lỗi 4 — `Math.abs(Long.MIN_VALUE)` tràn

Giá trị dương đối ứng không biểu diễn trong long. Dùng BigInteger hoặc một biểu diễn unsigned có chứng minh riêng.

### Lỗi 5 — Áp quy tắc số dư dương cho `%` với a âm

Java remainder với số âm có thể âm. Chạy Euclid trên trị tuyệt đối rồi đổi dấu hệ số, hoặc dùng một phép chia Euclid nhất quán được chứng minh.

### Lỗi 6 — Trả gcd âm

Gcd chuẩn phải không âm. Với a=-240,b46, g=2, không phải -2.

### Lỗi 7 — In x,y như thể duy nhất

Tất cả nghiệm Bézout có tham số t; cặp thuật toán chọn chỉ là một cặp đại diện.

### Lỗi 8 — Thiếu kiểm chứng bất biến

Một cặp x,y “trông hợp lý” có thể sai. Luôn kiểm `a*x+b*y=gcd(a,b)`, và g là ước chung lớn nhất.

### Lỗi 9 — Dùng modulo nghịch đảo khi gcd(a,m)>1

Khi gcd>1, nghịch đảo không tồn tại. Không dùng một hệ số x từ EGCD khi g>1 và gọi nó là nghịch đảo của a.

### Lỗi 10 — Không chuẩn hóa inverse vào `[0,m)`

Hệ số x có thể âm; dùng `x.mod(m)` với m>0 để trả residue chuẩn.

### Lỗi 11 — Cho m=0 trong modulo

Modulo 0 không được định nghĩa. Đối với nghịch đảo cần m≥2; đối với congruence/CRT cần m>0 trong mô hình này.

### Lỗi 12 — Bỏ qua m'=1 sau khi chia gcd

Đồng dư modulo1 thỏa với mọi x, không cần gọi inverse modulo1. Chọn residue0, period1.

### Lỗi 13 — Đếm sai số nghiệm modulo m

`a·x≡b modm` có **g=gcd(a,m)** đại diện modulo m nếu g|b, chứ không phải luôn một.

### Lỗi 14 — Diophantine có nghiệm nhưng gọi vô nghiệm vì x0 âm

Nghiệm Bézout cho phép x,y **âm**. Nếu đề đòi nghiệm không âm, phải chọn t theo bất đẳng thức, không loại nghiệm nguyên tổng quát ngay.

### Lỗi 15 — Quên nhân c/g

Từ `a*u+b*v=g`, nghiệm cho `a*x+b*y=c` là `(u*c/g,v*c/g)`, không phải luôn `(u,v)`.

### Lỗi 16 — Công thức tham số sai dấu

Đúng: `dx=b/g`, `dy=−a/g`. Nếu cùng dùng dấu cộng `a/g`, tổng a*x+b*y sẽ thay đổi theo t.

### Lỗi 17 — Kiểm `g|c` khi g=0

Trường hợp a=b=0 phải xét riêng trước; không gọi phép chia hay remainder với g=0.

### Lỗi 18 — CRT mặc định môđun nguyên tố cùng nhau

Với m1,m2 không coprime, có nghiệm nếu gcd chia hiệu residue. Chẳng hạn 2 mod6 và 5 mod9 có nghiệm14 mod18.

### Lỗi 19 — CRT nhân m1*m2 làm chu kỳ dù gcd>1

Chu kỳ đúng là `lcm(m1,m2)`, không phải luôn `m1*m2`. Ví dụ trên lcm=18, tích=54.

### Lỗi 20 — Không chuẩn hóa residue âm

`x≡−1 mod8` tương đương `x≡7 mod8`; kết quả CRT chuẩn thường trả `[0,lcm)`.

### Lỗi 21 — Chỉ kiểm CRT theo một môđun

Một nghiệm hệ phải thỏa **cả hai** đồng dư. Test `x.mod(m1)==r1` và `x.mod(m2)==r2`.

### Lỗi 22 — Số lượng nghiệm modulo khác nghiệm nguyên

Đồng dư có vô số nghiệm nguyên theo `x=x0+period*t`, nhưng hữu hạn **đại diện trong `[0,m)`**. Nói rõ đang đếm theo modulo nào.

### Lỗi 23 — Tràn `q*coefficient` trong lặp

Cập nhật `oldS−q*s` có phép nhân; kiểu int/long không đủ cho mọi input. Dùng BigInteger hoặc chứng minh miền.

### Lỗi 24 — Nhầm BigInteger.remainder và BigInteger.mod

`remainder` nhận dấu theo số bị chia; `mod(m)` với m>0 trả residue không âm. Dùng đúng mục đích: kiểm chia hết hay chuẩn hóa modulo.

### Lỗi 25 — Dùng `BigInteger.divide()` với ước chia 0

Phải xử lý gcd=0, m=0 riêng. `BigInteger` không tự giúp thuật toán giải đúng mọi trường hợp không hợp lệ.

### Lỗi 26 — Chọn nghiệm thỏa `x>=0` mà quên `y>=0`

Ràng buộc trên t phải lấy **giao tất cả các khoảng**. Với 30x+18y=6, x>=0 đòi t>=1 nhưng y>=0 đòi t<=0 ⇒ không có nghiệm không âm.

### Lỗi 27 — Nhầm phép chia làm tròn trong điều kiện biên

Để giải `dx*t ≥ c` khi dx âm, phải đổi chiều, dùng floor/ceil division đúng với số âm. Trong Java BigInteger.divide làm tròn về 0, không tự động là floor cho mọi số.

### Lỗi 28 — Ép BigInteger về long không kiểm

`longValue()` có thể mất bit. Nếu cần chuyển, dùng `longValueExact()` và xử lý lỗi khi vượt miền.

### Lỗi 29 — Dùng Euclid mở rộng trên số thực

Chứng minh phụ thuộc phép chia có dư và tính chia hết trong **số nguyên**. Không thay a,b bằng floating point rồi kỳ vọng cùng kết quả.

### Lỗi 30 — Không kiểm nghiệm thay vào phương trình gốc

Sau khi tính nghiệm, nhất là trong CRT và Diophantine, thay lại và đối chiếu chính xác là QA quan trọng để phát hiện lỗi dấu hoặc modulo.

## 17. Kiểm thử, kiểm chứng và trường hợp biên

| Đầu vào | Kỳ vọng |
|---|---|
| EGCD(240,46) | g2, x-9,y47 |
| EGCD(30,18) | g6, x-1,y2 |
| EGCD(99,78) | g3, x-11,y14 |
| EGCD(-240,46) | g2, x9,y47 |
| EGCD(0,-7) | g7, x0,y-1 |
| EGCD(0,0) | g0, cặp chuẩn (0,0) |
| EGCD(Long.MIN_VALUE,0) | g=9223372036854775808, không overflow |
| `30x+18y=6` | Cơ sở(-1,2), bước(3,-5) |
| `30x+18y=5` | Vô nghiệm nguyên |
| `30x+18y=60`, x,y≥0 | Nghiệm duy nhất (2,0) |
| `0x+0y=0` | Mọi cặp nguyên |
| `0x+0y=7` | Vô nghiệm |
| `inv(3 mod11)` | 4 |
| `inv(-3 mod11)` | 7 |
| `inv(6 mod9)` | Không có |
| `6x≡9 mod15` | x≡4 mod5, ba residue mod15 |
| `6x≡8 mod15` | Vô nghiệm |
| `0x≡0 mod7` | Mọi x |
| `x≡2 mod6`, `x≡5 mod9` | x≡14 mod18 |
| `x≡2 mod6`, `x≡4 mod9` | Vô nghiệm |
| `x≡−1 mod8`, `x≡5 mod6` | x≡23 mod24 |
| `x≡14 mod18`, `x≡2 mod4` | x≡14 mod36 |

### 17.1. Randomized differential testing

Một bộ test mạnh dùng các cách tính **độc lập**:

1. Sinh a,b nguyên có thể âm hoặc bằng0; chạy Euclid mở rộng cả đệ quy và lặp.
2. So gcd với `BigInteger.gcd` hoặc phép chia Euclid thường độc lập.
3. Kiểm `a*x+b*y=g`, g≥0, và g chia a,b khi g>0.
4. Với Diophantine, sinh c và kiểm điều kiện `g|c` (trừ cả a,b=0).
5. Khi có nghiệm, chọn nhiều t âm/dương, kiểm thay `x0+dx*t`, `y0+dy*t` vào phương trình.
6. Với modulus m nhỏ, kiểm inverse bằng cách **duyệt hết residue `[0,m)`** để xác định có nghiệm hay không; nếu có, inverse nhân a phải bằng1 modm.
7. Với đồng dư tuyến tính, duyệt x=0..m−1 và so danh sách với các lớp từ phương pháp khử gcd.
8. Với CRT, duyệt x=0..lcm−1 để xác định các residue thật thỏa cả hai; so với `merge`.
9. Với số lớn như `Long.MIN_VALUE`, tránh ép về long và so bằng BigInteger.
10. Kiểm cả trường hợp âm, zero, modulus1 ở đồng dư, modulus không coprime, và phương trình vô nghiệm.

**Đừng chỉ so kết quả x,y với một cặp x,y cụ thể khi đổi cách cài**: khác cặp vẫn có thể đúng nếu giữ đẳng thức Bézout. So invariant và nghiệm thay vào mới là tiêu chuẩn cốt lõi.

## 18. Bài tập có lời giải

### Bài 1 — Gcd bằng Euclid

Tính gcd(240,46).

**Đáp án:** 2, theo chuỗi chia ở phần 2.

### Bài 2 — Bézout

Tìm x,y sao cho 240x+46y=2.

**Đáp án:** x=-9,y=47.

### Bài 3 — Kiểm nghiệm

`240·14+46·(-73)` bằng bao nhiêu?

**Đáp án:** 2. Đây là nghiệm Bézout khác nghiệm (-9,47), ứng với t=1.

### Bài 4 — Công thức đệ quy

Nếu extended(b,r) trả `(g,x1,y1)`, extended(a,b) trả hệ số nào?

**Đáp án:** `x=y1`, `y=x1−q*y1`, với `q=a div b`.

### Bài 5 — Bất biến lặp

Các biến oldS,oldT biểu diễn điều gì?

**Đáp án:** `oldR=oldS·A+oldT·B` với A,B là input không âm ban đầu.

### Bài 6 — Zero case

`extended(0,0)` có gcd bao nhiêu theo quy ước?

**Đáp án:** gcd=0; một cặp chuẩn là x=0,y=0, mọi cặp đều thỏa 0=0.

### Bài 7 — Số âm

Một cặp Bézout cho (-240,46)?

**Đáp án:** g2,x9,y47.

### Bài 8 — Long.MIN_VALUE

Vì sao không dùng Math.abs(long) với Long.MIN_VALUE?

**Đáp án:** |−2^63|=2^63 vượt `Long.MAX_VALUE`, nên `Math.abs` trả giá trị âm do overflow.

### Bài 9 — Diophantine điều kiện

`30x+18y=5` có nghiệm nguyên không?

**Đáp án:** không, vì gcd6 không chia hết5.

### Bài 10 — Diophantine cơ sở

`30x+18y=6` có nghiệm riêng nào?

**Đáp án:** (-1,2).

### Bài 11 — Toàn bộ nghiệm

Viết nghiệm tổng quát của `30x+18y=6`.

**Đáp án:** `x=-1+3t`, `y=2−5t`, t nguyên.

### Bài 12 — Nghiệm không âm

Có nghiệm x,y≥0 của `30x+18y=6` không?

**Đáp án:** không, vì t≥1 và t≤0 mâu thuẫn.

### Bài 13 — C=60

Nghiệm không âm của `30x+18y=60`?

**Đáp án:** (2,0) là nghiệm không âm duy nhất.

### Bài 14 — Điều kiện nghịch đảo

a có nghịch đảo mod m≥2 khi nào?

**Đáp án:** `gcd(a,m)=1`.

### Bài 15 — Inverse(3,11)

Nghịch đảo của 3 modulo11?

**Đáp án:** 4, vì 3·4≡1 mod11.

### Bài 16 — Inverse(-3,11)

Nghịch đảo của -3 modulo11?

**Đáp án:** 7, vì -3·7=-21≡1 mod11.

### Bài 17 — Không nghịch đảo

6 có nghịch đảo modulo9 không?

**Đáp án:** không, gcd(6,9)=3.

### Bài 18 — Đồng dư tuyến tính

Giải 6x≡9 mod15.

**Đáp án:** x≡4 mod5, đại diện modulo15 là 4,9,14.

### Bài 19 — Đồng dư vô nghiệm

6x≡8 mod15 có nghiệm không?

**Đáp án:** không, vì gcd3 không chia8.

### Bài 20 — Đồng dư a=0

0x≡0 mod7 có nghiệm nào?

**Đáp án:** mọi x nguyên; biểu diễn x≡0 mod1.

### Bài 21 — CRT tương thích

Giải x≡2 mod6, x≡5 mod9.

**Đáp án:** x≡14 mod18.

### Bài 22 — CRT mâu thuẫn

x≡2 mod6, x≡4 mod9 có nghiệm không?

**Đáp án:** không, vì gcd3 không chia hiệu2.

### Bài 23 — CRT residue âm

x≡−1 mod8, x≡5 mod6?

**Đáp án:** x≡23 mod24.

### Bài 24 — Chu kỳ CRT

Tại sao chu kỳ của hệ hai đồng dư là lcm(m1,m2) chứ không luôn là tích?

**Đáp án:** hai nghiệm cùng thỏa phải chênh nhau một bội chung của cả m1,m2; bội chung dương nhỏ nhất là lcm. Nếu gcd>1 thì tích lớn hơn lcm.

### Bài 25 — Điều kiện riêng x,y≥0

Một nghiệm Diophantine có x<0 có chứng minh bài toán x,y≥0 vô nghiệm không?

**Đáp án:** không. Cần xét **mọi t nguyên** trong họ nghiệm và kiểm giao các ràng buộc.

### Bài 26 — Tính duy nhất của Bézout

Hệ số x,y trong ax+by=g có nhất thiết duy nhất?

**Đáp án:** không, có họ nghiệm theo tham số t nếu a,b không đồng thời 0.

### Bài 27 — Số vòng chia

Số vòng Euclid mở rộng tăng theo gì?

**Đáp án:** O(log min(|a|,|b|)) phép chia khi cả hai khác0, nhưng chi phí bit của BigInteger phải tính riêng.

### Bài 28 — Kiểm modulo

Khi muốn residue không âm của x mod m trong Java BigInteger với m>0, dùng gì?

**Đáp án:** `x.mod(m)`; không đánh đồng với `remainder` trên số âm.

## 19. Checklist trước khi nộp

1. Gcd có được chuẩn hóa không âm?
2. Có xử lý `(0,0)` riêng trước khi chia cho g?
3. Khi một trong a,b bằng0, hệ số dấu có đúng?
4. Có dùng số học chính xác cho input có thể vượt long?
5. Công thức đệ quy có đúng `x=y1`, `y=x1−q*y1`?
6. Bản lặp có cập nhật oldR/r, oldS/s và oldT/t cùng q?
7. Các phép `q*coefficient` có được bảo vệ khỏi overflow?
8. Với số âm, có dùng phép chia/số dư nhất quán và đổi dấu hệ số?
9. Có kiểm `a*x+b*y=gcd(a,b)` bằng chính số nguyên lớn?
10. Có biết các hệ số Bézout không duy nhất?
11. Phương trình ax+by=c có kiểm `g|c`?
12. Khi g=0, có xét c=0 và c≠0 riêng?
13. Khi có nghiệm, có nhân x,y gốc với c/g?
14. Bước tổng quát có đúng `(b/g,−a/g)`?
15. Nếu x,y có ràng buộc, có giải khoảng t thay vì chọn nghiệm tùy ý?
16. Modulus của inverse có ≥2 và gcd(a,m)=1?
17. Inverse được chuẩn hóa trong `[0,m)`?
18. Đồng dư tuyến tính có khử gcd trước khi lấy inverse?
19. Có xử lý m'=1 (tất cả x) riêng?
20. Có phân biệt nghiệm nguyên vô hạn với số residue modulo m?
21. CRT có kiểm gcd chia hiệu hai residue?
22. Modulus CRT là lcm, không là tích khi hai môđun có ước chung?
23. Các residue âm có chuẩn hóa bằng mod dương?
24. Có kiểm nghiệm CRT thỏa **tất cả** đồng dư?
25. Có thử c âm, a/b âm, zero, modulus1, trường hợp vô nghiệm?
26. Có đối chiếu recursive/iterative cùng với gcd độc lập?
27. Có brute-force residue nhỏ cho modular inverse, linear congruence và CRT?
28. Có chú ý BigInteger.divide/remainder khác floor-mod với input âm?
29. Nếu cần hiệu năng, có phân biệt số vòng chia với chi phí phép toán BigInteger?
30. Có dùng `longValueExact()` nếu phải chuyển nghiệm về long?

**Ghi nhớ:** Euclid mở rộng không chỉ trả `gcd(a,b)`, mà trả **một chứng chỉ Bézout** `a*x+b*y=g`. Nhờ đẳng thức ấy, ta giải được `ax+by=c` khi và chỉ khi `g|c`, tìm nghịch đảo modulo m khi và chỉ khi gcd(a,m)=1, giải đồng dư tuyến tính và hợp nhất các đồng dư CRT kể cả khi môđun có ước chung. Luôn chuẩn hóa gcd không âm, xét riêng `(0,0)`, dùng số học chính xác và **kiểm lại đẳng thức gốc**.
