# Euclid để tìm ước chung lớn nhất

## 1. Bài toán và định nghĩa

Cho hai số nguyên a và b, **ước chung lớn nhất** (ƯCLN, GCD — greatest common divisor) là số nguyên dương lớn nhất chia hết cả a lẫn b, miễn là ít nhất một số khác 0. Ký hiệu d | a nghĩa là a = d*k với k nguyên.

```text
Ước dương của 48: 1, 2, 3, 4, 6, 8, 12, 16, 24, 48
Ước dương của 18: 1, 2, 3, 6, 9, 18
Ước chung: 1, 2, 3, 6
gcd(48,18) = 6
```

Thử tất cả các ước phù hợp với số nhỏ, nhưng quá chậm với dữ liệu lớn. **Thuật toán Euclid** dùng phép chia có dư, giải bài toán với rất ít vòng lặp.

### 1.1. Dấu và số 0

GCD được trả về **không âm**. Đổi dấu không đổi các ước dương, nên gcd(a,b)=gcd(|a|,|b|). Ví dụ gcd(-54,24)=6.

Nếu a khác 0: gcd(a,0)=gcd(0,a)=|a|. Chẳng hạn gcd(0,-54)=54.

Riêng gcd(0,0) **không xác định** theo định nghĩa toán học là ước chung dương lớn nhất, vì mọi số dương đều chia 0. Nhiều thư viện lập trình quy ước gcd(0,0)=0 để tiện gộp GCD. **Mã trong bài này dùng quy ước đó**, không nói 0 là ước dương lớn nhất.

### 1.2. Nguyên tố cùng nhau

Hai số được gọi là nguyên tố cùng nhau (coprime) khi gcd(a,b)=1. Ví dụ gcd(8,15)=1 dù 8 và 15 đều là hợp số. Điều kiện này là quan hệ giữa hai số, không phải yêu cầu cả hai đều là số nguyên tố.

## 2. Định lý Euclid từ phép chia có dư

Với a không âm, b dương, tồn tại duy nhất thương q và dư r sao cho a=q*b+r và 0<=r<b.

```text
48 = 2 * 18 + 12
18 = 1 * 12 + 6
12 = 2 * 6  + 0
```

**Định lý trung tâm:** gcd(a,b)=gcd(b,a%b), với b>0 và a,b không âm.

### 2.1. Chứng minh tập ước chung được bảo toàn

Đặt r=a-q*b. Nếu d chia cả a và b, d cũng chia hiệu a-q*b, tức d chia r. Ngược lại, nếu d chia cả b và r, d chia tổng q*b+r=a. Vậy tập ước chung của cặp (a,b) bằng tập ước chung của cặp (b,r); hai cặp có GCD như nhau.

Đây là **bất biến**: mỗi vòng lặp thay cặp hiện tại bằng cặp nhỏ hơn mà không thay đổi GCD.

### 2.2. Chứng minh tính dừng

Khi b>0 và đầu vào đã không âm, r=a%b luôn thỏa 0<=r<b. Sau bước (a,b) -> (b,r), thành phần thứ hai giảm nghiêm ngặt trong tập số nguyên không âm. Không tồn tại dãy giảm vô hạn như thế, nên thuật toán kết thúc tại b=0; khi đó GCD chính là a.

Chứng minh tính đúng hoàn chỉnh gồm: **bất biến bảo toàn GCD**, **tính dừng** và **giá trị trả về đúng khi b=0**.

## 3. Euclid dạng lặp

```text
gcdNonnegative(a,b):
    while b != 0:
        r = a % b
        a = b
        b = r
    return a
```

Mô phỏng gcd(48,18):

| Vòng | a | b | r=a%b | Cặp mới |
|---:|---:|---:|---:|---|
| 1 | 48 | 18 | 12 | (18,12) |
| 2 | 18 | 12 | 6 | (12,6) |
| 3 | 12 | 6 | 0 | (6,0) |

Trả 6. Nếu a<b, thuật toán tự hoán vai trò trong vòng đầu: (18,48) -> (48,18). Nếu b=0 từ đầu, không chạy vòng nào và trả a.

### 3.1. Không được cập nhật sai thứ tự

```java
// Sai: mất giá trị a trước khi tính số dư
a = b;
b = a % b;

// Đúng: giữ a cũ trong phép chia dư
long r = a % b;
a = b;
b = r;
```

Và không bao giờ tính phép a%b khi b bằng 0, vì Java ném ArithmeticException cho phép chia/lấy dư số nguyên với 0.

### 3.2. Dạng đệ quy

```java
static long gcdRecursiveNonnegative(long a, long b) {
    if (b == 0) return a;
    return gcdRecursiveNonnegative(b, a % b);
}
```

Đây là đoạn minh họa **không độc lập**, giả định a,b là long không âm. Dạng đệ quy bám sát công thức toán học nhưng dùng thêm stack frame cho từng bước; dạng lặp dùng bộ nhớ phụ hằng số.

## 4. Vì sao dùng modulo thay vì trừ liên tiếp?

Với a>=b>0, ta cũng có gcd(a,b)=gcd(a-b,b). Nhưng phiên bản trừ số nhỏ khỏi số lớn liên tục có thể rất chậm. Ví dụ a=1_000_000_000, b=1 có thể cần gần một tỷ lần trừ; trong khi a%1=0 ở vòng đầu.

Biến thể trừ còn dễ bị lặp vô hạn nếu một đầu vào bằng 0 mà không có điều kiện xử lý. Phép chia có dư gộp nhiều phép trừ vào một phép toán.

## 5. Độ phức tạp và số Fibonacci

Với a,b cùng dương và M=min(a,b), Euclid thực hiện **O(log M) phép chia có dư**. Trực giác: với a>=b, nếu r=a%b lớn hơn b/2, thì số dư ở bước tiếp theo là b-r nhỏ hơn b/2; nếu r đã không lớn hơn b/2 thì đạt giảm đôi ngay. Như vậy tối đa hai bước làm số thứ hai giảm ít nhất một nửa.

Đầu vào là hai số Fibonacci liên tiếp thường làm Euclid cần nhiều bước:

```text
gcd(13,8):
13 % 8 = 5
 8 % 5 = 3
 5 % 3 = 2
 3 % 2 = 1
 2 % 1 = 0
```

Trong mô hình RAM với số máy có độ rộng cố định, mỗi phép chia dư được tính là O(1), thời gian là O(log M) và bộ nhớ bản lặp O(1). Nhưng với **BigInteger**, một phép chia trên số dài nhiều bit không phải O(1); số vòng logarithmic không đồng nghĩa tổng thời gian bit chỉ O(log M). Với a=0 hoặc b=0, thuật toán dừng ngay hay sau một vòng, không dùng log(0).

## 6. Số âm và bẫy Long.MIN_VALUE

Java long có miền [-2^63,2^63-1]. Giá trị nhỏ nhất Long.MIN_VALUE=-9223372036854775808; trị tuyệt đối của nó là 9223372036854775808, **không biểu diễn được bằng long dương**. Vì vậy Math.abs(Long.MIN_VALUE) vẫn là số âm.

```java
long x = Long.MIN_VALUE;
long y = Math.abs(x); // y vẫn là Long.MIN_VALUE!
```

Đặc biệt gcd(Long.MIN_VALUE,0) = 2^63, kết quả **thực sự vượt Long.MAX_VALUE**. Không thể hứa hàm long gcd(long,long) luôn trả chính xác GCD không âm cho mọi signed long.

Giải pháp: hoặc **hạn chế đầu vào không âm**, hoặc chuyển số nguyên sang BigInteger trước khi gọi abs(). Chương trình độc lập bên dưới cung cấp hai hàm: gcdLongNonnegative nhận long không âm; gcd(BigInteger,BigInteger) nhận giá trị có dấu và hỗ trợ biên Long.MIN_VALUE.

Toán tử Java % trên số âm là remainder có thể âm (ví dụ -7 % 3 == -1). Chứng minh giảm dần ở trên áp dụng cho hai số **không âm**; hàm BigInteger chuẩn hóa dấu trước vòng Euclid.

## 7. GCD nhiều số, BCNN và phân số

### 7.1. GCD một dãy

GCD có tính kết hợp: gcd(gcd(a,b),c)=gcd(a,gcd(b,c)). Vì gcd(0,x)=|x|, có thể gộp từ g=0:

```text
Dãy: [0,18,-24,30]
g=0
g=gcd(0,0)=0
g=gcd(0,18)=18
g=gcd(18,-24)=6
g=gcd(6,30)=6
```

GCD cả dãy bằng 6. Với mảng rỗng, chương trình trả 0 theo quy ước fold. Tính kết hợp cũng cho phép xây **segment tree GCD** để truy vấn đoạn.

### 7.2. BCNN (LCM)

Với ít nhất một số khác 0: gcd(a,b) * lcm(a,b) = |a*b|. Ta quy ước lcm(a,0)=0, kể cả lcm(0,0)=0.

Để giảm nguy cơ tràn, tính (|a| / gcd(a,b)) * |b| sau khi kiểm tra a,b khác 0, thay vì nhân a*b trước rồi mới chia. Nhưng ngay cả phép nhân cuối vẫn có thể tràn long: khi cần kết quả chính xác dùng BigInteger.

Ví dụ gcd(21,6)=3, lcm(21,6)=42, và 3*42=126=|21*6|.

### 7.3. Rút gọn phân số

Với phân số p/q, yêu cầu q khác 0, đặt g=gcd(p,q) và rút gọn về (p/g)/(q/g). Ví dụ -84/126=-2/3 do g=42. Có thể đổi dấu cả tử/mẫu để mẫu dương. Tuyệt đối không chia cho gcd(0,0)=0 để xử lý phân số 0/0; phân số ấy không hợp lệ.

## 8. Euclid mở rộng và hệ số Bézout

Euclid mở rộng tìm thêm hai hệ số x,y thỏa **a*x + b*y = gcd(a,b)**. Ví dụ 240*(-9) + 46*47 = 2 và (-54)*(-1) + 24*(-2) = 6.

Đặt A=|a|, B=|b|. Duy trì các bất biến:

```text
oldR = A*oldS + B*oldT
r    = A*s    + B*t

Khởi tạo:
oldR=A; r=B
oldS=1; s=0
oldT=0; t=1
```

Với thương q=oldR/r, tính **từ giá trị cũ**: nextR=oldR-q*r, nextS=oldS-q*s, nextT=oldT-q*t. Sau đó chuyển (oldR,r)=(r,nextR), (oldS,s)=(s,nextS), (oldT,t)=(t,nextT). Hai bất biến vẫn đúng vì tổ hợp tuyến tính được bảo toàn.

Khi r=0, oldR là GCD của A,B và oldS,oldT là hệ số. Để trả đẳng thức theo a,b có dấu, lấy x=oldS*sign(a), y=oldT*sign(b), quy ước sign(0)=0.

Với (a,b)=(0,0), bản mẫu trả g=0, x=y=0, thỏa 0=0. Không được cập nhật oldR trước khi tính nextR; nếu không, hệ số Bézout có thể sai dù GCD trông đúng.

## 9. Nghịch đảo modulo và đồng dư

Với modulus m>1, x là **nghịch đảo modulo** của a khi a*x ≡ 1 (mod m). Điều kiện cần và đủ: **gcd(a,m)=1**.

Nếu có nghịch đảo thì a*x+m*y=1 nên mọi ước chung phải chia 1. Nếu gcd=1 thì đẳng thức Bézout cho a*x+m*y=1 và lấy modulo m được nghịch đảo. Dùng x.mod(m) của BigInteger để trả kết quả không âm.

```text
inverse(3 mod 11) = 4       vì 3*4 = 12 ≡ 1 (mod 11)
inverse(-3 mod 11) = 7      vì -3*7 = -21 ≡ 1 (mod 11)
inverse(6 mod 9) = NONE    vì gcd(6,9)=3
```

Với đồng dư a*x ≡ b (mod m), m>0, đặt d=gcd(a,m). Phương trình có nghiệm nguyên nếu và chỉ nếu d chia b. Ví dụ 6*x ≡ 8 (mod 14) có d=2, tương đương 3*x ≡ 4 (mod 7), suy ra x ≡ 6 (mod 7), ứng với hai lớp 6,13 modulo 14.

Euclid là thuật toán về **tính chia hết trên số nguyên**: nó không tự tìm mọi thừa số nguyên tố, không áp dụng trực tiếp cho số thực sai số, và không thay một bộ giải phương trình tổng quát.


## 10. Chương trình Java 17+ hoàn chỉnh

Chương trình tự cài Euclid, Euclid mở rộng, GCD mảng, BCNN và nghịch đảo modulo; kiểm thử GCD bằng **duyệt ước số nhỏ** và **BigInteger.gcd của thư viện**. Tên tệp: `EuclidGcdDemo.java`.

```java
import java.math.BigInteger;
import java.util.Objects;
import java.util.Random;

public final class EuclidGcdDemo {
    private EuclidGcdDemo() {}

    private static final BigInteger ZERO = BigInteger.ZERO;
    private static final BigInteger ONE = BigInteger.ONE;

    private static BigInteger bi(long x) {
        return BigInteger.valueOf(x);
    }

    public static long gcdLongNonnegative(long a, long b) {
        if (a < 0 || b < 0) {
            throw new IllegalArgumentException(
                "expected nonnegative long arguments"
            );
        }
        while (b != 0) {
            long r = a % b;
            a = b;
            b = r;
        }
        return a;
    }

    public static BigInteger gcd(
            BigInteger a, BigInteger b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        a = a.abs();
        b = b.abs();
        while (b.signum() != 0) {
            BigInteger r = a.remainder(b);
            a = b;
            b = r;
        }
        return a;
    }

    public static BigInteger gcdOf(long... values) {
        Objects.requireNonNull(values, "values");
        BigInteger result = ZERO;
        for (long x : values) result = gcd(result, bi(x));
        return result;
    }

    public static BigInteger lcm(
            BigInteger a, BigInteger b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        if (a.signum() == 0 || b.signum() == 0) return ZERO;
        return a.abs().divide(gcd(a, b)).multiply(b.abs());
    }

    public record Bezout(
            BigInteger g, BigInteger x, BigInteger y) {}

    public static Bezout extended(
            BigInteger a, BigInteger b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        BigInteger oldR = a.abs(), r = b.abs();
        BigInteger oldS = ONE, s = ZERO;
        BigInteger oldT = ZERO, t = ONE;

        while (r.signum() != 0) {
            BigInteger q = oldR.divide(r);
            BigInteger nextR = oldR.subtract(q.multiply(r));
            BigInteger nextS = oldS.subtract(q.multiply(s));
            BigInteger nextT = oldT.subtract(q.multiply(t));

            oldR = r; r = nextR;
            oldS = s; s = nextS;
            oldT = t; t = nextT;
        }

        BigInteger x = oldS.multiply(bi(a.signum()));
        BigInteger y = oldT.multiply(bi(b.signum()));
        return new Bezout(oldR, x, y);
    }

    public static BigInteger inverse(
            BigInteger a, BigInteger modulus) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(modulus, "modulus");
        if (modulus.compareTo(ONE) <= 0) {
            throw new IllegalArgumentException(
                "modulus must be greater than 1"
            );
        }
        Bezout z = extended(a, modulus);
        if (!z.g().equals(ONE)) {
            throw new ArithmeticException(
                "inverse does not exist"
            );
        }
        return z.x().mod(modulus);
    }

    // Oracle theo dinh nghia; chi goi voi |a|,|b| <= 1000.
    private static int bruteGcdSmall(int a, int b) {
        int x = Math.abs(a), y = Math.abs(b);
        if (x == 0) return y;
        if (y == 0) return x;
        int answer = 1;
        for (int d = 1; d <= Math.min(x, y); d++) {
            if (x % d == 0 && y % d == 0) answer = d;
        }
        return answer;
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        System.out.println(
            "gcdLong(48,18)="
            + gcdLongNonnegative(48, 18)
        );
        System.out.println(
            "gcd(48,18)=" + gcd(bi(48), bi(18))
        );

        System.out.println("Trace(48,18):");
        BigInteger a = bi(48), b = bi(18);
        while (b.signum() != 0) {
            BigInteger[] qr = a.divideAndRemainder(b);
            System.out.println(
                "  " + a + " = " + qr[0]
                + " * " + b + " + " + qr[1]
            );
            a = b; b = qr[1];
        }

        System.out.println(
            "gcd(-54,24)=" + gcd(bi(-54), bi(24))
        );
        System.out.println(
            "gcd(0,-54)=" + gcd(ZERO, bi(-54))
        );
        System.out.println(
            "gcd(0,0)=" + gcd(ZERO, ZERO)
        );
        System.out.println(
            "gcd(Long.MIN_VALUE,0)="
            + gcd(bi(Long.MIN_VALUE), ZERO)
        );
        System.out.println(
            "gcdOf[0,18,-24,30]="
            + gcdOf(0, 18, -24, 30)
        );
        System.out.println(
            "lcm(21,6)=" + lcm(bi(21), bi(6))
        );
        System.out.println(
            "lcm(0,7)=" + lcm(ZERO, bi(7))
        );

        Bezout z1 = extended(bi(240), bi(46));
        System.out.println(
            "Bezout(240,46): g=" + z1.g()
            + " x=" + z1.x() + " y=" + z1.y()
            + " check=" + bi(240).multiply(z1.x())
                .add(bi(46).multiply(z1.y()))
        );

        Bezout z2 = extended(bi(-54), bi(24));
        System.out.println(
            "Bezout(-54,24): g=" + z2.g()
            + " x=" + z2.x() + " y=" + z2.y()
            + " check=" + bi(-54).multiply(z2.x())
                .add(bi(24).multiply(z2.y()))
        );

        Bezout z0 = extended(ZERO, ZERO);
        System.out.println(
            "Bezout(0,0): g=" + z0.g()
            + " x=" + z0.x() + " y=" + z0.y()
        );

        System.out.println(
            "inverse(3 mod 11)="
            + inverse(bi(3), bi(11))
        );
        System.out.println(
            "inverse(-3 mod 11)="
            + inverse(bi(-3), bi(11))
        );
        try {
            inverse(bi(6), bi(9));
            throw new AssertionError("inverse must not exist");
        } catch (ArithmeticException expected) {
            System.out.println("inverse(6 mod 9)=NONE");
        }

        boolean rejected = false;
        try {
            gcdLongNonnegative(-3, 6);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Negative long rejected=" + rejected);

        Random random = new Random(392L);
        int small = 0, signed = 0, big = 0;
        int bezout = 0, lcmTests = 0;

        for (int i = 0; i < 3_000; i++) {
            int x = random.nextInt(2001) - 1000;
            int y = random.nextInt(2001) - 1000;
            check(gcd(bi(x), bi(y)).equals(
                bi(bruteGcdSmall(x, y))),
                "small GCD trial=" + i
            );
            small++;
        }

        for (int i = 0; i < 2_500; i++) {
            BigInteger x = bi(random.nextLong());
            BigInteger y = bi(random.nextLong());
            check(gcd(x, y).equals(x.gcd(y)),
                "signed GCD trial=" + i
            );
            signed++;
        }

        for (int i = 0; i < 1_500; i++) {
            BigInteger x = new BigInteger(256, random);
            BigInteger y = new BigInteger(256, random);
            if (random.nextBoolean()) x = x.negate();
            if (random.nextBoolean()) y = y.negate();
            check(gcd(x, y).equals(x.gcd(y)),
                "256-bit GCD trial=" + i
            );
            big++;
        }

        for (int i = 0; i < 2_000; i++) {
            BigInteger x = bi(
                random.nextInt(200001) - 100000
            );
            BigInteger y = bi(
                random.nextInt(200001) - 100000
            );
            Bezout z = extended(x, y);
            check(x.multiply(z.x())
                .add(y.multiply(z.y())).equals(z.g()),
                "Bezout identity trial=" + i
            );
            check(z.g().equals(x.gcd(y)),
                "Bezout gcd trial=" + i
            );
            bezout++;
        }

        for (int i = 0; i < 2_000; i++) {
            BigInteger x = bi(
                random.nextInt(200001) - 100000
            );
            BigInteger y = bi(
                random.nextInt(200001) - 100000
            );
            BigInteger g = gcd(x, y);
            BigInteger lc = lcm(x, y);
            check(g.multiply(lc).equals(
                x.multiply(y).abs()),
                "GCD-LCM trial=" + i
            );
            check(lc.signum() >= 0,
                "negative LCM trial=" + i
            );
            lcmTests++;
        }

        System.out.println("Random small GCD: " + small);
        System.out.println("Random signed long: " + signed);
        System.out.println("Random 256-bit: " + big);
        System.out.println("Random Bezout: " + bezout);
        System.out.println("Random GCD-LCM: " + lcmTests);
    }
}
```

Lưu mã trong tệp UTF-8 có tên `EuclidGcdDemo.java` và chạy JDK 17+:

```bash
javac -encoding UTF-8 EuclidGcdDemo.java
java EuclidGcdDemo
```

**Đầu ra chuẩn:**

```text
gcdLong(48,18)=6
gcd(48,18)=6
Trace(48,18):
  48 = 2 * 18 + 12
  18 = 1 * 12 + 6
  12 = 2 * 6 + 0
gcd(-54,24)=6
gcd(0,-54)=54
gcd(0,0)=0
gcd(Long.MIN_VALUE,0)=9223372036854775808
gcdOf[0,18,-24,30]=6
lcm(21,6)=42
lcm(0,7)=0
Bezout(240,46): g=2 x=-9 y=47 check=2
Bezout(-54,24): g=6 x=-1 y=-2 check=6
Bezout(0,0): g=0 x=0 y=0
inverse(3 mod 11)=4
inverse(-3 mod 11)=7
inverse(6 mod 9)=NONE
Negative long rejected=true
Random small GCD: 3000
Random signed long: 2500
Random 256-bit: 1500
Random Bezout: 2000
Random GCD-LCM: 2000
```


## 11. Kiểm thử độc lập và tính đúng của chương trình

**Oracle 1 — chia thử ước dương:** với đầu vào nhỏ, kiểm tra từng ước từ 1 đến min(|a|,|b|), chọn ước chung lớn nhất. Đây là cách dựa trên định nghĩa, không dùng recurrence Euclid; phù hợp để phát hiện lỗi cập nhật cặp số.

**Oracle 2 — BigInteger.gcd của thư viện:** với signed long và số 256-bit, so kết quả hàm tự cài với thư viện chuẩn. Không thể chia thử tới căn của những số có hàng trăm bit trong thời gian hợp lý.

**Oracle 3 — đẳng thức Bézout:** với mỗi kết quả (g,x,y), kiểm a*x+b*y=g và g khớp GCD oracle. Chỉ so g là chưa đủ để phát hiện lỗi hệ số.

**Oracle 4 — hệ thức GCD–LCM:** kiểm gcd(a,b)*lcm(a,b)=|a*b| và lcm>=0, kể cả khi một số bằng 0.

Chương trình dùng seed Random(392L), kiểm 3.000 cặp nhỏ, 2.500 cặp signed long, 1.500 cặp BigInteger 256-bit, 2.000 cặp Bézout và 2.000 cặp GCD–LCM. Những kiểm thử hữu hạn tăng độ tin cậy về implementation, nhưng **không thay thế chứng minh toán học** ở phần 2.

### 11.1. Những ca biên cần tự thử

```text
gcd(48,18)=6
gcd(18,48)=6
gcd(13,13)=13
gcd(-54,24)=6
gcd(-8,-12)=4
gcd(0,-54)=54
gcd(0,0)=0 (quy ước)
gcd(8,15)=1
gcd(Long.MIN_VALUE,0)=9223372036854775808
gcdOf([0,18,-24,30])=6
lcm(21,6)=42
lcm(0,7)=0
inverse(3 mod 11)=4
inverse(6 mod 9)=NONE
```

## 12. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Trả số dư 0 thay vì số chia cuối | GCD dương bị báo 0 | Khi b=0 trả a |
| Gán a=b rồi mới tính a%b | Mất giá trị a cũ | Lưu r trước |
| Tính a%b với b=0 | Chia cho 0 | Vòng while(b!=0) |
| Không xử lý số âm | GCD có thể mang dấu sai | Chuẩn hóa trị tuyệt đối an toàn |
| Math.abs(Long.MIN_VALUE) | Vẫn là số âm | BigInteger hoặc hợp đồng không âm |
| Hàm long nhận mọi signed long và hứa trả GCD không âm | Không chứa được 2^63 | Trả BigInteger |
| Không nêu gcd(0,0) | Mơ hồ về kết quả | Quy ước rõ theo API |
| Trừ liên tiếp cho số lớn | Quá nhiều vòng | Dùng modulo |
| Nhân a*b trước khi chia GCD để tính LCM | Tràn long | Chia trước hoặc BigInteger |
| LCM có số 0 nhưng vẫn chia cho GCD | Có thể chia 0 | Xử lý số 0 trước |
| Nhầm coprime với cả hai số nguyên tố | Kết luận sai | Chỉ kiểm tra GCD=1 |
| Ghi đè biến trong Euclid mở rộng | Hệ số Bézout sai | nextR/nextS/nextT trước khi gán |
| Quên dấu a,b khi lấy hệ số | a*x+b*y không bằng g | Chỉnh bằng signum |
| Tìm inverse khi GCD>1 | Trả nghịch đảo không tồn tại | Kiểm tra gcd(a,m)=1 |
| Gọi BigInteger.mod với modulus<=0 | Lỗi API | Yêu cầu modulus dương; bài này >1 |
| Nêu O(log M) như bit complexity BigInteger | Đánh giá thấp chi phí | Phân biệt số vòng và phép chia lớn |
| Chỉ kiểm thử gcd(48,18) | Bỏ lỗi số 0, âm, biên | Dùng oracle độc lập và các ca biên |

## 13. Bài tập tự luyện có đáp án

**Bài 1.** Tính gcd(48,18). *Đáp án:* số dư 12,6,0 nên GCD bằng 6.

**Bài 2.** Tính gcd(18,48). *Đáp án:* 6; bước đầu đưa cặp thành (48,18).

**Bài 3.** Tính gcd(-54,24). *Đáp án:* 6.

**Bài 4.** Tính gcd(0,-54). *Đáp án:* 54.

**Bài 5.** gcd(0,0) trong bài này là gì? *Đáp án:* 0 theo quy ước lập trình; định nghĩa ước chung dương lớn nhất không áp dụng.

**Bài 6.** Tại sao gcd(a,b)=gcd(b,a%b)? *Đáp án:* từ a=q*b+r, hai cặp có cùng tập ước chung.

**Bài 7.** Tại sao Euclid dừng? *Đáp án:* số dư mới không âm và nhỏ hơn số chia trước.

**Bài 8.** Mã a=b;b=a%b sai ở đâu? *Đáp án:* mất giá trị a cũ, cần lưu r trước.

**Bài 9.** GCD của 13 và 8? *Đáp án:* 1, với dãy dư 5,3,2,1,0.

**Bài 10.** Vì sao Fibonacci liên tiếp có thể cần nhiều bước? *Đáp án:* dãy dư giảm qua các số Fibonacci trước đó.

**Bài 11.** GCD của [0,18,-24,30]? *Đáp án:* 6.

**Bài 12.** 8 và 15 có nguyên tố cùng nhau không? *Đáp án:* có, GCD bằng 1.

**Bài 13.** lcm(21,6)? *Đáp án:* 42.

**Bài 14.** lcm(0,7) theo quy ước? *Đáp án:* 0.

**Bài 15.** GCD của (Long.MIN_VALUE,0) có vừa long không? *Đáp án:* không, kết quả là 2^63.

**Bài 16.** Kiểm tra 240*(-9)+46*47. *Đáp án:* 2, bằng GCD.

**Bài 17.** Hệ số Bézout cho (-54,24)? *Đáp án:* x=-1,y=-2.

**Bài 18.** Inverse 3 modulo 11? *Đáp án:* 4.

**Bài 19.** Inverse -3 modulo 11? *Đáp án:* 7.

**Bài 20.** Tại sao inverse 6 modulo 9 không tồn tại? *Đáp án:* GCD bằng 3.

**Bài 21.** Rút gọn -84/126. *Đáp án:* -2/3.

**Bài 22.** Giải 6*x ≡ 8 (mod 14). *Đáp án:* x ≡ 6 (mod 7), cho các lớp 6,13 modulo 14.

**Bài 23.** 6*x ≡ 5 (mod 14) có nghiệm không? *Đáp án:* không, vì gcd(6,14)=2 không chia 5.

**Bài 24.** Vì sao chia thử là oracle tốt? *Đáp án:* nó dùng định nghĩa ước chung, không tái sử dụng chính thuật toán Euclid.

## 14. Checklist và ghi nhớ

Trước khi nộp, kiểm tra điều kiện b!=0 trước modulo; lưu r trước khi đổi a,b; chuẩn hóa âm an toàn; nêu chính sách gcd(0,0); xử lý Long.MIN_VALUE; chứng minh bất biến và tính dừng; phân biệt số phép chia với chi phí bit; xử lý LCM có 0; kiểm tra hệ số Bézout và điều kiện tồn tại nghịch đảo; đối chiếu đầu vào nhỏ bằng oracle độc lập.

**Cốt lõi:** gcd(a,b)=gcd(b,a%b) với b>0 và a,b không âm. Mỗi số dư nhỏ hơn số chia, nên thuật toán dừng. Khi b=0, trả a.

```text
while b != 0:
    r = a % b
    a = b
    b = r
return a
```

Euclid là ví dụ kinh điển của kỹ thuật **biến đổi bài toán nhưng giữ nguyên đáp án**, sau đó dùng một đại lượng giảm nghiêm ngặt để chứng minh kết thúc.
