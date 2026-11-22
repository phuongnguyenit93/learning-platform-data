# Giới hạn tài nguyên của BigInteger dù không có độ rộng cố định như long

## 1. Mục tiêu: số nguyên chính xác tùy ý không có nghĩa là vô hạn tài nguyên

`java.math.BigInteger` là lớp biểu diễn **số nguyên có dấu với độ chính xác tùy ý** (*arbitrary-precision signed integer*). Khác với `long` cố định 64 bit, `BigInteger` có thể chứa số nguyên hàng trăm, hàng nghìn hoặc rất nhiều chữ số mà không bị **tràn số theo modulo 2⁶⁴** như toán tử primitive.

Nhưng “tùy ý” **không phải “vô hạn”**. Mỗi chương trình Java vẫn chạy trong một JVM hữu hạn RAM, heap, CPU, thời gian, tài nguyên thread và giới hạn cài đặt. Một phép toán trên `BigInteger` quá lớn có thể:

- Cần bộ nhớ cho đối tượng, mảng dữ liệu và các kết quả tạm.
- Mất nhiều thời gian CPU để cộng, nhân, chia, nâng lũy thừa hoặc chuyển đổi sang chuỗi.
- Thất bại do giới hạn kích thước dữ liệu của implementation, hoặc gây `OutOfMemoryError`.
- Chiếm tài nguyên chung khiến các yêu cầu khác của dịch vụ chậm hoặc bị từ chối.
- Tạo nguy cơ từ dữ liệu không đáng tin cậy, nhất là một chuỗi đầu vào dài bất thường hoặc một số mũ do người dùng quyết định.

Bài học giúp bạn phân biệt **giới hạn của kiểu dữ liệu** với **ngân sách tài nguyên của ứng dụng**, ước lượng độ lớn bằng `bitLength()`, bảo vệ các thao tác tăng trưởng nhanh và viết ví dụ Java 17+ an toàn.

## 2. long cố định 64 bit, còn BigInteger mở rộng theo giá trị

| Thuộc tính | `long` | `BigInteger` |
| --- | --- | --- |
| Dạng | Primitive 64-bit có dấu | Lớp đối tượng bất biến |
| Miền giá trị | `Long.MIN_VALUE` đến `Long.MAX_VALUE` | Không khóa ở độ rộng 64 bit; có giới hạn implementation và tài nguyên |
| Tràn khi cộng/nhân thông thường | Có thể wrap quanh modulo 2⁶⁴ | Không wrap theo miền `long` |
| Độ chính xác số nguyên | Chính xác trong miền `long` | Chính xác cho số nguyên mà JVM biểu diễn/tính được |
| Bộ nhớ mỗi giá trị | Kích thước primitive cố định | Phụ thuộc độ lớn, cấu trúc đối tượng và cài đặt |
| Độ dài kết quả | Tối đa 64 bit kiểu primitive | Có thể tăng theo phép toán |
| Khi không đủ khả năng xử lý | Overflow số học kiểu primitive | Có thể hết bộ nhớ, quá giới hạn implementation hoặc quá ngân sách ứng dụng |

Ví dụ so sánh:

~~~java
long primitive = Long.MAX_VALUE;
System.out.println(primitive + 1); // -9223372036854775808

BigInteger extended = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
System.out.println(extended);      // 9223372036854775808
~~~

Đây là đoạn minh họa trong phương thức có import `java.math.BigInteger`, không phải chương trình độc lập.

`BigInteger` không làm mất chữ số trong phép cộng trên. Tuy nhiên, giá trị kết quả cần được biểu diễn và lưu trên heap. Nếu tiếp tục tạo những kết quả quá lớn, ứng dụng vẫn có thể thất bại.

**Không dùng `double` như phương án “tránh tràn long” nếu cần số nguyên chính xác.** `double` có 53 bit precision có nghĩa, nên nhiều số nguyên lớn không thể biểu diễn chính xác; `BigInteger` phục vụ bài toán khác hẳn.

## 3. BigInteger lưu bao nhiêu dữ liệu?

Về mặt toán học, một số nguyên dương `n` cần khoảng:

\[
\text{bits}(n)=\lfloor\log_2(n)\rfloor+1,\qquad n>0
\]

bit để biểu diễn phần độ lớn dưới dạng nhị phân. Với số 0, quy ước độ dài độ lớn bằng 0 bit.

Java có sẵn:

~~~java
BigInteger n = BigInteger.ONE.shiftLeft(1000);

System.out.println(n.bitLength());         // 1001
System.out.println(n.toString().length()); // 302
~~~

`n = 2¹⁰⁰⁰` nên bit cao nhất ở vị trí 1000 (đánh số từ 0), dẫn tới **1001 bit**. Khi in thập phân, `2¹⁰⁰⁰` có **302 chữ số**.

### Ước lượng bộ nhớ thô theo bit

Một số có `b` bit độ lớn cần ít nhất khoảng `ceil(b / 8)` byte cho phần bit thô, trước các chi phí bổ sung:

\[
\text{rawMagnitudeBytes}\approx \left\lceil\frac{b}{8}\right\rceil.
\]

Nhưng **đây không phải kích thước heap thực của BigInteger**. Trên JVM còn có header đối tượng, trường tham chiếu, thông tin dấu, mảng/word, alignment và các đối tượng tạm. Thực tế còn phụ thuộc phiên bản JDK, architecture, GC và cách tính.

`BigInteger.toByteArray()` cũng **không phải công cụ đo heap**. API này tạo một mảng byte **two's-complement có dấu**, nên có thể phải giữ thêm bit/byte dấu và còn phát sinh bản sao.

~~~java
BigInteger value = BigInteger.ONE.shiftLeft(1000);
System.out.println(value.toByteArray().length); // 126
~~~

Ví dụ trên có 126 byte, phù hợp với biểu diễn byte của số dương `2¹⁰⁰⁰`. Nó **không** có nghĩa đối tượng `BigInteger` chỉ chiếm 126 byte heap.

### Với số âm, cẩn trọng về bitLength()

`BigInteger.bitLength()` được mô tả bằng biểu diễn bù hai không kể bit dấu, nên không luôn giống bit length của **độ lớn tuyệt đối** đối với số âm. Nếu mục tiêu là kiểm soát kích thước toán hạng theo độ lớn, hãy dùng:

~~~java
int magnitudeBits = value.abs().bitLength();
~~~

`BigInteger.ZERO.bitLength()` là 0. `abs()` giữ nguyên ngữ nghĩa số nguyên chính xác; đừng ép về `long` để lấy giá trị tuyệt đối, vì như vậy có thể mất dữ liệu hoặc gặp `Long.MIN_VALUE`.

## 4. “Không cố định 64 bit” không đồng nghĩa “không có giới hạn implementation”

Hợp đồng `BigInteger` đảm bảo các phép toán số nguyên có độ chính xác tùy ý **trong miền mà implementation hỗ trợ**. Tài liệu API Java nêu các ràng buộc của kiểu và cảnh báo rằng những thao tác tạo kết quả vượt phạm vi được hỗ trợ có thể phát sinh `ArithmeticException`.

Ngoài phạm vi của implementation, còn có các giới hạn độc lập:

- **Kích thước mảng và đối tượng:** một mảng Java không có chiều dài vô hạn; độ lớn BigInteger phụ thuộc vào các cấu trúc dữ liệu trong bộ nhớ.
- **Giới hạn heap:** dù lý thuyết biểu diễn được, JVM có thể không còn vùng nhớ cấp phát.
- **Tài nguyên tạm thời:** phép nhân/chia/parse có thể cần nhiều bộ đệm hơn kích thước kết quả cuối.
- **CPU và thời gian:** ngay cả khi đủ RAM, tính toán hoặc chuyển đổi kết quả có thể lâu hơn giới hạn xử lý yêu cầu.
- **Giới hạn do ứng dụng đặt:** kích thước input, số chữ số output, số mũ, thời hạn request, quota tenant, ngân sách memory/CPU của container.

Không nên ghi trong tài liệu nghiệp vụ một con số **“BigInteger tối đa luôn là X bit”** như giới hạn thực tế phổ quát. Khả năng cụ thể có thể phụ thuộc phiên bản Java, implementation và môi trường vận hành; ứng dụng nên tự đặt ngân sách nhỏ hơn, có thể kiểm soát và kiểm thử được.

**Giới hạn kiểu dữ liệu** và **giới hạn an toàn của hệ thống** là hai việc khác nhau. Một máy có thể chứa số `BigInteger` với hàng triệu bit, nhưng việc cho phép từng yêu cầu web tạo số như vậy có thể vẫn không phù hợp.

## 5. Kích thước kết quả thay đổi theo phép toán

Điểm nguy hiểm không chỉ ở đầu vào; **kết quả trung gian có thể lớn lên rất nhanh**.

### Phép cộng và phép trừ

Khi cộng hai số có độ lớn tối đa khoảng `b` bit, kết quả có thể cần khoảng `b + 1` bit. Với dữ liệu tùy ý dấu, còn có những trường hợp triệt tiêu, nhưng không nên dựa vào điều đó để bỏ giới hạn.

~~~java
BigInteger a = BigInteger.ONE.shiftLeft(100);
BigInteger b = a;
BigInteger sum = a.add(b);

System.out.println(a.bitLength());   // 101
System.out.println(sum.bitLength()); // 102
~~~

### Phép nhân

Hai số dương có khoảng `m` và `n` bit tạo tích có không quá khoảng `m + n` bit, với độ lớn khác 0. Chẳng hạn bình phương một số có thể **gần gấp đôi số bit** cần thiết.

~~~java
BigInteger a = BigInteger.ONE.shiftLeft(1000);
BigInteger square = a.multiply(a);

System.out.println(a.bitLength());      // 1001
System.out.println(square.bitLength()); // 2001
~~~

Bên cạnh dung lượng kết quả còn có chi phí tính toán và các mảng trung gian. Implementation có thể sử dụng thuật toán nhân khác nhau theo kích thước; không nên khẳng định mọi phép nhân đều có một độ phức tạp cố định duy nhất trong mọi JDK.

### Nâng lũy thừa

`BigInteger.pow(int exponent)` có thể khiến kết quả tăng rất nhanh theo số mũ. Với `base > 1`:

\[
\text{bits}(base^e) \approx e\log_2(base)+1.
\]

~~~java
BigInteger power = BigInteger.TWO.pow(1000);
System.out.println(power.bitLength()); // 1001
~~~

Nếu số mũ do người dùng kiểm soát và bạn không kiểm tra ngân sách, một request nhỏ kiểu `"base=2&exponent=1000000000"` có thể yêu cầu lượng dữ liệu kết quả rất lớn. **Không chạy phép tính chỉ để “xem nó có vừa hay không”**; ước lượng kích thước trước.

### Bình phương lặp gây tăng trưởng đặc biệt nhanh

~~~java
BigInteger n = BigInteger.TWO;
for (int i = 0; i < 10; i++) {
    n = n.multiply(n);
}
System.out.println(n.bitLength()); // 1025
~~~

Sau 10 lần bình phương, `n = 2¹⁰²⁴`, có 1025 bit. Nếu tăng số lần bình phương thêm rất nhiều, số bit tăng theo **hàm mũ của số bước**. Vì vậy một vòng lặp trông ngắn cũng có thể tạo gánh nặng lớn nếu không có điểm dừng theo kích thước.

## 6. Không chỉ phép toán: parse và toString cũng tốn tài nguyên

Lấy BigInteger từ chuỗi:

~~~java
BigInteger n = new BigInteger("123456789012345678901234567890");
~~~

Cú pháp chuỗi nhỏ có vẻ vô hại. Nhưng với chuỗi có hàng triệu chữ số, chương trình cần đọc, kiểm tra định dạng, chuyển sang biểu diễn nhị phân, cấp phát bộ nhớ và xử lý lỗi. Nếu đầu vào không đáng tin, việc parse không giới hạn có thể là vấn đề **availability** của dịch vụ.

Tương tự, `n.toString()` phải sinh biểu diễn thập phân:

~~~java
String decimal = n.toString();
~~~

Một số có hàng triệu bit có thể tạo một chuỗi thập phân rất lớn. Việc ghi chuỗi đó ra log, gửi qua HTTP, chèn vào JSON hoặc lưu vào hệ thống khác tiêu tốn thêm bộ nhớ, CPU, băng thông và dung lượng lưu trữ.

### Ước lượng số chữ số thập phân

Số nguyên dương có `b` bit thường có khoảng:

\[
\text{decimalDigits}\approx b\log_{10}(2)\approx0{,}30103b.
\]

Đây là **ước lượng**, không phải một bộ kiểm tra độ dài chính xác cho mọi giá trị. Ví dụ `2¹⁰⁰⁰` có 1001 bit nhưng 302 chữ số thập phân.

Với dữ liệu cần giữ nguyên, không nên làm `toString()` của một BigInteger rất lớn chỉ để hỏi “nó có lớn không?”. `abs().bitLength()` cung cấp một tín hiệu kích thước rẻ hơn so với tạo toàn bộ chuỗi.

### Input cực dài có thể gây rủi ro trước khi constructor chạy

Nếu hệ thống đã tải toàn bộ body HTTP hoặc file vào một `String` khổng lồ rồi mới kiểm tra độ dài, bạn **đã cấp phát tài nguyên cho đầu vào**. Vì vậy nên giới hạn request body/field ngay tại ranh giới tiếp nhận, rồi mới kiểm tra chuỗi, parse và tính toán. Hàm parse có giới hạn ở tầng nghiệp vụ là lớp bảo vệ thứ hai, không phải thay thế toàn bộ kiểm soát ở gateway/server.

## 7. Một hàm parse có giới hạn số chữ số

Ví dụ yêu cầu hệ thống chỉ nhận số nguyên thập phân ASCII tối đa **40 chữ số**, không tính dấu `+` hoặc `-`. Đoạn code dưới đây không cần thư viện ngoài:

~~~java
static BigInteger parseLimitedDecimal(String text, int maxDigits) {
    if (text == null || maxDigits <= 0) {
        throw new IllegalArgumentException("Invalid input or limit");
    }

    int start = 0;
    if (!text.isEmpty()
            && (text.charAt(0) == '+' || text.charAt(0) == '-')) {
        start = 1;
    }

    int digits = text.length() - start;
    if (digits < 1 || digits > maxDigits) {
        throw new IllegalArgumentException("Too many or no digits");
    }

    for (int i = start; i < text.length(); i++) {
        char c = text.charAt(i);
        if (c < '0' || c > '9') {
            throw new IllegalArgumentException("ASCII decimal digits only");
        }
    }

    return new BigInteger(text);
}
~~~

Đây là **phương thức đặt trong thân lớp**, cần `import java.math.BigInteger;`, không phải một file chạy độc lập.

Lựa chọn kiểm tra ASCII có chủ đích: `BigInteger(String)` có thể nhận nhiều dạng chữ số mà `Character.digit` hỗ trợ, nhưng giao thức ví dụ này quy định **chỉ 0–9 ASCII**. Đừng cho phép một tập ký tự rồi vô tình mô tả nó là “chỉ số ASCII”.

Điểm tốt của hàm:

1. Kiểm tra `null`, số chữ số và độ dài **trước** khi tạo `BigInteger`.
2. Cho phép dấu đầu chuỗi nhưng không tính nó như chữ số.
3. Dùng vòng lặp đơn giản để kiểm tra định dạng; không cần parse rồi mới kiểm tra kích thước.
4. Tạo giá trị chính xác nếu đầu vào hợp lệ.
5. Báo lỗi tường minh khi vượt chính sách.

Nếu chuỗi đến từ người dùng, còn cần giới hạn **độ dài payload trước khi hình thành String** như đã trình bày ở trên. Giới hạn 40 chỉ là ví dụ, không phải ngưỡng bắt buộc của `BigInteger`.

## 8. Kiểm tra số bit trước phép nhân

Với hai số khác 0 có độ dài độ lớn lần lượt là `aBits` và `bBits`, tích có **không quá `aBits + bBits` bit**. Ta có thể dùng cận trên bảo thủ này để **từ chối sớm** phép nhân có nguy cơ vượt ngân sách.

~~~java
static BigInteger multiplyWithinBitBudget(
        BigInteger a, BigInteger b, int maxBits) {
    if (a == null || b == null || maxBits < 1) {
        throw new IllegalArgumentException("Invalid operands or budget");
    }
    if (a.signum() == 0 || b.signum() == 0) {
        return BigInteger.ZERO;
    }

    long upperBound = (long) a.abs().bitLength()
            + b.abs().bitLength();
    if (upperBound > maxBits) {
        throw new IllegalArgumentException("Result may exceed bit budget");
    }

    return a.multiply(b);
}
~~~

Điều này là một **giới hạn bảo thủ**, không phải phép tiên đoán số bit chính xác của tích. Một tích thực tế có thể nằm trong ngân sách ngay cả khi `upperBound` lớn hơn ngưỡng: khi đó hàm **cố ý từ chối** để tránh rủi ro. Nếu nghiệp vụ không chấp nhận false rejection, hãy áp dụng phân tích phù hợp hơn hoặc dùng ngân sách lớn hơn.

Vì `bitLength()` trả `int`, phép cộng hai độ dài được chuyển sang `long` trước để tránh tràn số nguyên ở phép cộng cận. Đừng ước lượng bằng `a.toString().length()` và `b.toString().length()` khi input có thể cực lớn: tạo chuỗi cũng là công việc tốn tài nguyên.

Một cận trên không thay thế memory limit thật. Phép nhân nhỏ hơn ngân sách bit vẫn có thể cần **mảng trung gian**, gặp thiếu heap hoặc ảnh hưởng CPU.

## 9. Kiểm tra số mũ trước khi gọi pow

`BigInteger.pow(int exponent)` yêu cầu số mũ nguyên không âm. Nếu `exponent < 0`, API ném `ArithmeticException`. Nếu số mũ rất lớn, kết quả có thể cần số bit khổng lồ.

Với `base` khác 0 và số mũ dương, cận trên đơn giản là:

\[
\text{resultBits}\le \text{abs(base).bitLength()}\times exponent.
\]

Ta dùng `long` để tính tích của hai tham số kích thước:

~~~java
static BigInteger powWithinBitBudget(
        BigInteger base, int exponent, int maxBits) {
    if (base == null || exponent < 0 || maxBits < 1) {
        throw new IllegalArgumentException("Invalid power parameters");
    }
    if (exponent == 0) {
        return BigInteger.ONE;
    }
    if (base.signum() == 0) {
        return BigInteger.ZERO;
    }

    long upperBound = (long) base.abs().bitLength() * exponent;
    if (upperBound > maxBits) {
        throw new IllegalArgumentException("Power may exceed bit budget");
    }
    return base.pow(exponent);
}
~~~

Đây cũng là một **cận bảo thủ**. Ví dụ `base = 1` hoặc `base = -1` thì kết quả luôn có độ lớn 1 với mọi số mũ, nhưng phép ước lượng trên vẫn có thể từ chối khi exponent quá lớn. Nếu cần xử lý tối ưu, có thể đặc biệt hóa các base `0`, `1` và `-1`.

**Lưu ý `0^0` trong Java API:** `BigInteger.pow(0)` trả `BigInteger.ONE` (kể cả khi base là 0); code trên cũng tuân theo hành vi đó. Nếu một mô hình toán học/ứng dụng muốn coi `0^0` là không hợp lệ, phải áp dụng kiểm tra nghiệp vụ riêng.

Không phải lúc nào cũng phù hợp trả về một BigInteger khổng lồ từ lũy thừa. Nếu bạn chỉ cần `base^exponent mod modulus`, hãy dùng phép toán modulo chuyên dụng, được nói ở phần tiếp theo.

## 10. Ví dụ Java 17+ hoàn chỉnh và kiểm soát được tài nguyên

Lưu thành file `BigIntegerResourceDemo.java`:

~~~java
import java.math.BigInteger;

public class BigIntegerResourceDemo {
    private static final int MAX_DIGITS = 40;
    private static final int MAX_RESULT_BITS = 2048;

    static BigInteger parseLimitedDecimal(String text) {
        if (text == null) {
            throw new IllegalArgumentException("Missing number");
        }
        int start = 0;
        if (!text.isEmpty()
                && (text.charAt(0) == '+' || text.charAt(0) == '-')) {
            start = 1;
        }
        int digits = text.length() - start;
        if (digits < 1 || digits > MAX_DIGITS) {
            throw new IllegalArgumentException("Invalid digit count");
        }
        for (int i = start; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c < '0' || c > '9') {
                throw new IllegalArgumentException("Not ASCII decimal");
            }
        }
        return new BigInteger(text);
    }

    static BigInteger multiplyBounded(BigInteger a, BigInteger b) {
        if (a == null || b == null) {
            throw new IllegalArgumentException("Missing operand");
        }
        if (a.signum() == 0 || b.signum() == 0) {
            return BigInteger.ZERO;
        }
        long upperBound = (long) a.abs().bitLength()
                + b.abs().bitLength();
        if (upperBound > MAX_RESULT_BITS) {
            throw new IllegalArgumentException("Product too large");
        }
        return a.multiply(b);
    }

    static BigInteger powBounded(BigInteger base, int exponent) {
        if (base == null || exponent < 0) {
            throw new IllegalArgumentException("Invalid exponent");
        }
        if (exponent == 0) {
            return BigInteger.ONE;
        }
        if (base.signum() == 0) {
            return BigInteger.ZERO;
        }
        long upperBound = (long) base.abs().bitLength() * exponent;
        if (upperBound > MAX_RESULT_BITS) {
            throw new IllegalArgumentException("Power too large");
        }
        return base.pow(exponent);
    }

    public static void main(String[] args) {
        BigInteger powerOfTwo = BigInteger.ONE.shiftLeft(1000);
        System.out.println("bits=" + powerOfTwo.bitLength());
        System.out.println("decimal digits=" + powerOfTwo.toString().length());
        System.out.println("byte array length=" +
                powerOfTwo.toByteArray().length);

        BigInteger parsed = parseLimitedDecimal("12345678901234567890");
        System.out.println("parsed=" + parsed);
        try {
            parsed.longValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("longValueExact=rejected");
        }

        System.out.println("square=" +
                multiplyBounded(BigInteger.valueOf(1234),
                        BigInteger.valueOf(1234)));
        System.out.println("two^10=" + powBounded(BigInteger.TWO, 10));
        System.out.println("zero bits=" + BigInteger.ZERO.bitLength());

        try {
            powBounded(BigInteger.TWO, 2000);
        } catch (IllegalArgumentException ex) {
            System.out.println("oversized power=rejected");
        }
        try {
            parseLimitedDecimal("1".repeat(41));
        } catch (IllegalArgumentException ex) {
            System.out.println("too many digits=rejected");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 BigIntegerResourceDemo.java
java BigIntegerResourceDemo
~~~

Stdout:

~~~text
bits=1001
decimal digits=302
byte array length=126
parsed=12345678901234567890
longValueExact=rejected
square=1522756
two^10=1024
zero bits=0
oversized power=rejected
too many digits=rejected
~~~

Giải thích:

- Số `2^1000` chỉ lớn hơn một chút so với 1000 bit và vẫn rất an toàn để minh họa; không cần tạo một số có hàng triệu chữ số.
- Chuyển `BigInteger` có giá trị lớn hơn `Long.MAX_VALUE` bằng `longValueExact()` phát sinh `ArithmeticException`. Cách này giúp phát hiện vượt miền thay vì âm thầm mất bit như `longValue()`.
- Phép nhân nhỏ `1234 × 1234` cho kết quả chính xác `1522756`.
- `2^10` trả `1024`, nằm trong ngân sách 2048 bit.
- `2^2000` **không được tính** trong hàm `powBounded`: cận trên bảo thủ đã vượt ngân sách và ném lỗi trước khi tạo số lớn.
- Chuỗi 41 chữ số bị từ chối **trước khi khởi tạo BigInteger**.

Mục đích của ví dụ là thể hiện **kiểm soát tài nguyên bằng chính sách ứng dụng**, không đo benchmark CPU hoặc heap. Các ngân sách 40 chữ số/2048 bit chỉ là cấu hình minh họa; sản phẩm thực phải chọn giới hạn từ yêu cầu nghiệp vụ và thử nghiệm tải.

## 11. Dùng modPow thay vì tạo lũy thừa khổng lồ rồi lấy mod

Nhiều bài toán chỉ cần:

\[
a^e\bmod m
\]

với `m > 0`. Không cần tính giá trị `a^e` đầy đủ rồi mới lấy số dư. `BigInteger.modPow(BigInteger exponent, BigInteger modulus)` thực hiện phép nâng lũy thừa modulo trực tiếp.

~~~java
BigInteger base = BigInteger.valueOf(7);
BigInteger exponent = BigInteger.valueOf(100);
BigInteger modulus = BigInteger.valueOf(13);

BigInteger modular = base.modPow(exponent, modulus);
System.out.println(modular); // 9
~~~

Trong ví dụ trên, `7^100 mod 13 = 9`. Phương thức `modPow` giúp tránh phải giữ **toàn bộ `7^100`** trong kết quả trung gian chỉ để lấy số dư.

Nhưng **modPow không miễn phí**: số mũ lớn, modulus lớn hoặc số lượng phép gọi nhiều vẫn cần CPU và tài nguyên. Với dữ liệu không đáng tin, vẫn phải giới hạn độ dài của base, exponent, modulus, yêu cầu modulus dương và thời hạn xử lý.

`BigInteger.modPow` còn có các quy tắc riêng cho số mũ âm (liên quan nghịch đảo modulo khi tồn tại); nếu nghiệp vụ chỉ cần lũy thừa modulo thông thường, hãy **từ chối số mũ âm từ đầu** để hợp đồng đơn giản và dễ dự đoán.

## 12. Không tạo chuỗi khổng lồ chỉ để kiểm tra hay log

Ví dụ log nguy hiểm:

~~~java
// Không nên làm với BigInteger chưa bị giới hạn kích thước:
logger.info("Computed result: " + hugeBigInteger);
~~~

Việc ghép chuỗi sẽ gọi `toString()` của BigInteger trước khi hoặc trong lúc tạo thông điệp, có thể khiến ứng dụng tạo một chuỗi thập phân khổng lồ. Ngay cả việc dùng logging placeholder cũng cần xem logging framework có thực sự trì hoãn format, và có giới hạn độ lớn trước khi format hay không.

Thay vì log toàn bộ, nếu chính sách cho phép, có thể ghi thông tin **về kích thước**:

~~~java
BigInteger value = BigInteger.ONE.shiftLeft(1000);
System.out.println("sign=" + value.signum()
        + ", bits=" + value.abs().bitLength());
// sign=1, bits=1001
~~~

Khi phục vụ API, cần giới hạn **cả input lẫn output**. Một chuỗi số rất dài được phép tính xong vẫn có thể vượt giới hạn của response, cache, broker, database hoặc giao thức nhận dữ liệu tiếp theo.

Nếu yêu cầu phải xuất đầy đủ một kết quả cực lớn, nên có cơ chế xử lý theo lô hoặc lưu vào tài nguyên phù hợp, và đánh giá cả chi phí tạo biểu diễn decimal. Không giả định rằng vì tính toán hoàn tất thì bước serialize sẽ luôn an toàn.

## 13. Chi phí của các phép toán khác

| Phép toán | Dạng chi phí cần lưu ý |
| --- | --- |
| `add` / `subtract` | Xử lý các phần tử biểu diễn số; tạo kết quả thích hợp |
| `multiply` / `square` | Kích thước kết quả tăng, phép nhân dùng CPU và bộ nhớ tạm |
| `divide` / `remainder` | Thuật toán chia số nhiều bit; chi phí phụ thuộc độ lớn của cả hai toán hạng |
| `pow` | Độ dài kết quả có thể tăng theo số mũ |
| `shiftLeft` | Có thể mở rộng số bit theo số lượng vị trí dịch |
| `toString` | Tạo chuỗi decimal; CPU/bộ nhớ cho chuyển đổi và kết quả |
| `new BigInteger(String)` | Chi phí phân tích chuỗi và chuyển biểu diễn |
| `gcd` | Chi phí tăng với kích thước toán hạng |
| `modPow` | Giảm nhu cầu tạo lũy thừa đầy đủ, nhưng vẫn tốn tài nguyên |
| `isProbablePrime` / `nextProbablePrime` | Các phép kiểm tra/tìm số nguyên tố có thể tốn nhiều CPU với input lớn |

Không nên gán một con số thời gian hoặc độ phức tạp duy nhất cho mọi hoạt động BigInteger trong mọi JVM; JDK có thể lựa chọn thuật toán khác nhau theo độ dài và cấu trúc đầu vào. Điều quan trọng là **đo trên dữ liệu và runtime thực tế** đồng thời đặt giới hạn an toàn từ cấp thiết kế.

Một cảnh báo khác: phép chia cho `BigInteger.ZERO` ném `ArithmeticException` do **điều kiện toán học không hợp lệ**, chứ không phải lỗi thiếu tài nguyên. Hãy phân biệt lỗi dữ liệu, lỗi cận tài nguyên và lỗi hạ tầng khi ghi log hoặc trả phản hồi API.

## 14. Tăng trưởng không thể chặn chỉ bằng điều kiện “đầu vào nhỏ”

Một API nhận hai số nguyên mỗi số tối đa 100 chữ số có vẻ an toàn cho phép cộng. Nhưng nếu người dùng cung cấp thêm:

- `repeatCount` rất lớn để nhân hoặc cộng lặp.
- `exponent` để gọi `pow`.
- `shiftDistance` để gọi `shiftLeft`.
- Số lần thực hiện thuật toán tìm số nguyên tố.
- Số lượng bước thử hoặc số lượng yêu cầu đồng thời.

thì kết quả và CPU có thể vượt ngân sách dù **mỗi toán hạng đầu vào nhỏ**.

Ví dụ vòng lặp:

~~~java
BigInteger value = BigInteger.TWO;
for (int step = 0; step < 10; step++) {
    value = value.multiply(value);
}
System.out.println(value.bitLength()); // 1025
~~~

Tăng số bước lên vài lần nữa sẽ làm kích thước tăng đột ngột. Bảo vệ tốt là định nghĩa **cận tổng chi phí** theo thuật toán, không chỉ giới hạn ký tự của một input.

Nếu hệ thống cho phép biểu thức toán học do người dùng gửi vào, cần hạn chế cả độ sâu biểu thức, số phép toán, số mũ, kích thước kết quả trung gian và tần suất gọi. Nếu chương trình chỉ kiểm tra output sau khi phép tính hoàn tất, việc bảo vệ tài nguyên đã quá muộn.

## 15. Tại sao catch OutOfMemoryError không phải giải pháp?

`OutOfMemoryError` là một `Error`, không phải một `Exception` nghiệp vụ thông thường. Khi heap cạn hoặc JVM không thể cấp phát đối tượng cần thiết, hệ thống có thể đã ở trạng thái rất hạn chế về tài nguyên.

Không nên viết kiểu:

~~~java
// Mẫu không nên dùng để "xử lý" số quá lớn trong nghiệp vụ:
//
// try {
//     return veryLargeComputation();
// } catch (OutOfMemoryError error) {
//     return BigInteger.ZERO;
// }
~~~

Việc trả zero sẽ che giấu lỗi và tạo dữ liệu sai. Hơn nữa, việc bắt `OutOfMemoryError` **không đảm bảo** chương trình còn đủ bộ nhớ để chạy logic phục hồi an toàn; thông thường cần cơ chế quản lý tài nguyên và khôi phục dịch vụ ở tầng cao hơn.

Giải pháp tốt hơn là:

1. Giới hạn kích thước payload **trước khi** tạo chuỗi/đối tượng lớn.
2. Kiểm tra số bit/digit và các tham số tạo tăng trưởng trước phép tính.
3. Dùng phép toán phù hợp, như `modPow` nếu chỉ cần số dư modulo.
4. Đặt timeout, giới hạn song song và quota tại tầng job/request.
5. Dùng bộ đo/giám sát thích hợp cho heap, GC, CPU, latency và mức tải.
6. Thử tải với dữ liệu sát biên ngân sách, kiểm tra hành vi khi vượt ngưỡng.

## 16. Timeouts và heap size: không phải bảo đảm đủ cho mọi BigInteger

Cấu hình JVM như `-Xmx` đặt **giới hạn tối đa của heap**, nhưng không chỉ định một BigInteger được phép chiếm bao nhiêu. Heap còn dùng cho object khác, thread, request, cache và mảng tạm. Tăng `-Xmx` có thể giúp một workload chạy được, nhưng cũng có thể dẫn tới thời gian GC dài, áp lực bộ nhớ của máy chủ hoặc chi phí vận hành lớn.

Ví dụ lệnh:

~~~bash
java -Xmx256m MyBigIntegerApp
~~~

Đây là **lệnh minh họa**; `MyBigIntegerApp` không phải một lớp được tạo trong bài. Nó chỉ giới hạn heap theo cấu hình JVM, không tự động cho phép mọi phép tính BigInteger an toàn trong giới hạn đó.

**Timeout** cũng có nhiều tầng: HTTP timeout, queue deadline, cancellation của job và giới hạn CPU của container. Không mặc định rằng gọi `Thread.interrupt()` sẽ dừng tức thì mọi phương thức BigInteger đang tính. Với workload không tin cậy hoặc tính toán dài, cân nhắc cô lập job trong tiến trình/worker riêng để có cơ chế thực thi, giới hạn và hủy phù hợp với hệ thống.

## 17. Thiết kế ngân sách tài nguyên theo nghiệp vụ

Một phương án thực tế là **xác định ngân sách được phép trước khi xây API**:

| Tham số | Ví dụ giới hạn | Mục đích |
| --- | --- | --- |
| Số chữ số thập phân đầu vào | 1–1000 | Ngăn chuỗi quá dài |
| Số bit đầu vào | ≤ 4096 | Giới hạn độ lớn toán hạng |
| Số bit kết quả ước lượng | ≤ 8192 | Ngăn tăng trưởng ngoài dự kiến |
| Exponent | 0–10000, có thể thấp hơn | Kiểm soát `pow`/lặp |
| Số phép toán trong request | Theo workload | Chặn biểu thức dài bất thường |
| Kích thước response | Theo hợp đồng API | Tránh serialize/log kết quả quá dài |
| Thời hạn/CPU quota | Theo loại job | Bảo vệ thời gian đáp ứng |
| Số job đồng thời | Theo khả năng máy | Tránh cùng lúc cấp phát lớn |

**Các số trong bảng là ví dụ thiết kế, không phải khuyến nghị mặc định hoặc giới hạn của Java.** Không thể chọn riêng một “bit budget” rồi kết luận dịch vụ chắc chắn an toàn: độ phức tạp thuật toán và số request đồng thời quyết định đáng kể chi phí thực tế.

Nếu mỗi phép tính khác nhau có mức rủi ro khác nhau, nên đặt các giới hạn khác nhau cho parse, cộng, nhân, lũy thừa, primality test và serialize. Khi có dữ liệu người dùng, cần kiểm soát **trước** từng bước có thể làm chi phí tăng, kể cả khi những bước trước đã vượt qua validation.

## 18. Khi nào dùng BigInteger, khi nào giữ long?

Dùng `long` nếu:

- Miền dữ liệu được quy định rõ và luôn nằm trong 64 bit.
- Cần số lượng lớn phép toán nguyên primitive với chi phí/biểu diễn đơn giản.
- Có thể kiểm tra overflow tường minh bằng `Math.addExact`, `Math.multiplyExact` và các quy tắc giới hạn số.

Dùng `BigInteger` nếu:

- Giá trị nguyên hợp lệ vượt miền `long`.
- Cần tính toán số nguyên chính xác với số bit biến thiên.
- Bài toán dùng các phép toán số nguyên lớn như số học modulo, tính toán tổ hợp hoặc các thuật toán đặc thù.
- Bạn đã thiết kế chính sách hạn chế tài nguyên và cách báo lỗi cho trường hợp không thể xử lý.

Một lựa chọn cân bằng: dùng `long` với `Math.addExact`/`multiplyExact` để phát hiện overflow, rồi **chuyển sang BigInteger có chủ đích** khi bài toán cho phép số lớn. Đừng làm một phép toán đã overflow bằng `long` rồi mới chuyển **kết quả sai** sang `BigInteger`; phải chuyển toán hạng trước khi tính hoặc xử lý nhánh overflow riêng.

~~~java
long a = Long.MAX_VALUE;
long b = 1;

BigInteger sum = BigInteger.valueOf(a)
        .add(BigInteger.valueOf(b));
System.out.println(sum); // 9223372036854775808
~~~

## 19. Sai lầm thường gặp

| Sai lầm | Tại sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| “BigInteger là vô hạn” | Heap, CPU, array và implementation vẫn hữu hạn | Dùng ngân sách tài nguyên |
| “Không overflow long thì không thể có lỗi” | Vẫn có thể `OutOfMemoryError` hoặc giới hạn implementation | Giới hạn input/output và thao tác |
| Đọc String có hàng triệu chữ số rồi mới kiểm tra | Payload đã tiêu tốn RAM trước khi validation | Chặn kích thước ở tầng nhận dữ liệu |
| Chỉ giới hạn bitLength toán hạng ban đầu | `pow`, `multiply` hoặc `shiftLeft` làm kết quả lớn nhanh | Ước lượng kích thước trước từng phép |
| Gọi `pow` với exponent do người dùng nhập trực tiếp | Có thể tạo kết quả rất lớn | Kiểm tra exponent và result bit budget |
| Dùng `base.pow(e).mod(m)` khi chỉ cần modulo | Tạo lũy thừa đầy đủ không cần thiết | `base.modPow(e, m)` khi phù hợp |
| `toString()` để kiểm tra kích thước mọi số | Tạo chuỗi decimal có thể rất lớn | `abs().bitLength()` và cận chi phí |
| Dùng `toByteArray().length` như heap size | Mảng two's-complement không tính object/intermediate | Xem là encoding, không phải đo RAM |
| Ép `BigInteger.longValue()` trước thao tác | Có thể mất bit cao | Giữ BigInteger hoặc `longValueExact()` |
| Bắt `OutOfMemoryError` rồi trả 0 | Che giấu lỗi; không bảo đảm phục hồi | Ngăn lỗi trước; xử lý ở tầng vận hành |
| Tăng `-Xmx` là hết mọi vấn đề | CPU/GC/concurrency và giới hạn output vẫn còn | Đo workload và đặt quota |
| Cho rằng đo `Runtime.freeMemory()` là cận an toàn để tính | Không phản ánh đầy đủ cấp phát trung gian, GC và tải đồng thời | Dùng giới hạn thiết kế và giám sát thực tế |
| Chỉ giới hạn ký tự đầu vào, bỏ số request | Tải đồng thời có thể gây cạn tài nguyên | Giới hạn concurrency/rate |
| Lấy timing từ một lần chạy nhỏ rồi suy cho mọi số | Thuật toán có thể đổi theo kích thước | Benchmark nhiều dải dữ liệu |
| Xem mọi `ArithmeticException` đều là lỗi chia 0 | Có thể có overflow giới hạn implementation, chuyển đổi exact, exponent âm... | Phân biệt theo API và ngữ cảnh |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` đúng, nhưng vẫn không chứng minh BigInteger “vô hạn”?

**Đáp án:** BigInteger không có độ rộng 64 bit như long, nên biểu diễn được số vượt Long.MAX_VALUE. Tuy nhiên nó vẫn dùng heap và thuật toán trên một JVM hữu hạn, có giới hạn implementation và tài nguyên.

**Câu 2.** Số `2^1000` cần bao nhiêu bit để biểu diễn độ lớn và có bao nhiêu chữ số decimal?

**Đáp án:** 1001 bit và 302 chữ số thập phân. `BigInteger.ONE.shiftLeft(1000)` là ví dụ kiểm tra.

**Câu 3.** Vì sao `toByteArray().length` không phải kích thước heap của một BigInteger?

**Đáp án:** Nó là độ dài **một mảng mới chứa biểu diễn two's-complement có dấu**, có thể thêm bit/byte dấu và không tính header, mảng nội bộ hay các bộ đệm khác.

**Câu 4.** Nếu input chỉ 3 chữ số là `"999"` nhưng exponent bằng 1 tỷ, có thể coi an toàn không?

**Đáp án:** Không. `999^1000000000` có kích thước kết quả khổng lồ. Cần kiểm tra exponent và cận số bit kết quả trước khi tính.

**Câu 5.** Khi chỉ cần `7^100 mod 13`, nên dùng `pow(100).mod(13)` hay `modPow(100,13)`?

**Đáp án:** `modPow` phù hợp hơn vì tính số dư modulo trực tiếp mà không bắt buộc tạo lũy thừa đầy đủ.

**Câu 6.** Vì sao không nên catch `OutOfMemoryError` rồi trả về `BigInteger.ZERO`?

**Đáp án:** Cạn bộ nhớ không phải kết quả số học 0; cách đó che giấu lỗi và có thể không giúp JVM khôi phục. Phải thiết kế giới hạn tài nguyên trước.

**Câu 7.** `BigInteger.bitLength()` và `new BigInteger(text).toString().length()` có cùng chi phí và đơn vị không?

**Đáp án:** Không. `bitLength()` trả số bit theo biểu diễn số, còn `toString()` tạo văn bản thập phân rồi `length()` đếm UTF-16 code units của văn bản. Việc chuyển số rất lớn sang chuỗi có thể tốn tài nguyên đáng kể.

**Câu 8.** Nếu result bit budget là 2048, phép nhân có cận `aBits+bBits=2050` nhưng tích thực tế có thể chỉ 2049 bit, có nên gọi hàm kiểm tra bảo thủ là “sai” không?

**Đáp án:** Không; hàm được thiết kế **bảo thủ** và cố ý có thể từ chối trường hợp thực tế vẫn vừa ngân sách. Nếu cần tối ưu tỷ lệ chấp nhận, phải thiết kế cách ước lượng/kiểm tra chính xác hơn và chấp nhận chi phí tương ứng.

## 21. Ghi nhớ và tài liệu tham khảo

- **`BigInteger` không bị giới hạn ở 64 bit**, nhưng không có tài nguyên vô hạn. Giới hạn thực tế do **implementation, heap, CPU, các đối tượng tạm và chính sách ứng dụng** quyết định.
- Số bit có thể quan sát bằng `abs().bitLength()`; **đừng dùng `toByteArray()` như công cụ đo heap**.
- **Input nhỏ có thể tạo output rất lớn** qua nhân, bình phương lặp, dịch trái và `pow`.
- Đặt giới hạn **trước khi parse, trước phép toán nặng và trước serialize/log**. Cận trên độ lớn có thể bảo thủ, cần tài liệu rõ.
- Khi chỉ cần lũy thừa modulo, ưu tiên `modPow` thay cho tính đầy đủ `pow` rồi lấy `mod`.
- `OutOfMemoryError` không phải cách báo “kết quả bằng 0”; phòng tránh bằng quota, validation, timeout và cô lập tải thích hợp.
- Dùng `long` khi miền cố định đủ; dùng `BigInteger` khi thật sự cần số nguyên lớn chính xác và đã chấp nhận chi phí.

Tham khảo chính thức (Java 17):

- [BigInteger — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): giới hạn miền được hỗ trợ, `bitLength`, `multiply`, `pow`, `modPow`, `toByteArray`, `longValueExact`.
- [Math — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact` và `multiplyExact` khi cần phát hiện overflow primitive.
- [OutOfMemoryError — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html): lỗi cấp phát khi JVM không thể cung cấp đối tượng cần thiết.
- [Java launcher options — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn heap `-Xmx` và các cấu hình khởi động JVM.
