# Phần cao của tích hai long bằng multiplyHigh

Một phép nhân hai giá trị `long` có thể tạo ra kết quả cần đến 128 bit, trong khi kiểu `long` chỉ lưu được 64 bit. Từ Java 9, `Math.multiplyHigh(long x, long y)` trả về **64 bit cao** của tích 128 bit khi hai toán hạng được hiểu là số nguyên có dấu.

Phần 64 bit thấp vẫn có thể lấy bằng phép nhân `x * y` thông thường. Kết hợp hai phần này cho ta biểu diễn 128 bit của tích trong hai biến `long`. API này hữu ích khi cần tính toán số nguyên độ rộng lớn hoặc xử lý phép nhân mà kết quả trung gian vượt phạm vi một `long`.

## 1. Vì sao cần phần cao của phép nhân?

Java `long` là số nguyên có dấu 64 bit, có miền giá trị từ `Long.MIN_VALUE` đến `Long.MAX_VALUE`. Khi nhân hai giá trị long, tích toán học có thể cần tối đa 128 bit.

Phép nhân long thông thường chỉ giữ lại 64 bit thấp của kết quả. Nếu tích vượt phạm vi long, Java không tự ném exception; các bit cao bị loại bỏ theo phép toán số nguyên hai bù.

Ví dụ:

~~~java
long low = Long.MAX_VALUE * 2;
System.out.println(low);
~~~

Kết quả là:

~~~text
-2
~~~

Giá trị toán học của tích là 18.446.744.073.709.551.614, nhưng phần 64 bit thấp khi diễn giải dưới dạng long có dấu là `-2`. Muốn biết phần cao đã bị bỏ đi là gì, cần một API tính phần cao của tích.

## 2. Math.multiplyHigh

Java 9 bổ sung phương thức:

~~~java
public static long multiplyHigh(long x, long y)
~~~

Phương thức trả về 64 bit có trọng số cao của tích 128 bit của hai toán hạng long có dấu. Có thể hình dung tích đầy đủ gồm hai nửa:

~~~text
128-bit product = [ high 64 bits ][ low 64 bits ]
~~~

Trong đó:

- `high = Math.multiplyHigh(x, y)` lấy 64 bit cao.
- `low = x * y` lấy 64 bit thấp.
- Cả hai giá trị đều được lưu trong biến long, nhưng mỗi biến đại diện cho một nửa bit của tích 128 bit.

`multiplyHigh` không trả về toàn bộ tích và cũng không tự phát hiện overflow bằng exception. Nó tính chính xác phần cao của tích theo ngữ nghĩa số nguyên có dấu.

## 3. Cách hiểu phần cao và phần thấp

Với hai toán hạng `x` và `y`, tích toán học có thể được biểu diễn bằng một số nguyên 128 bit có dấu theo dạng bù hai. Chia biểu diễn đó thành hai nửa 64 bit:

| Thành phần | Cách lấy | Ý nghĩa |
|---|---|---|
| Phần cao | `Math.multiplyHigh(x, y)` | 64 bit cao của tích 128 bit |
| Phần thấp | `x * y` | 64 bit thấp của tích, được giữ trong long |

Ví dụ:

- `3 * 5 = 15`: high là 0, low là 15.
- `Long.MAX_VALUE * 2`: high là 0, low được diễn giải thành -2.
- `-3 * 5 = -15`: high là -1, low là -15.
- `Long.MIN_VALUE * 2 = -2^64`: high là -1, low là 0.

Với tích âm, phần cao thường chứa các bit dấu mở rộng. Đây là kết quả đúng của biểu diễn 128 bit có dấu, không phải dấu hiệu tính toán sai.

## 4. Ví dụ minh họa bằng bảng

| x | y | high | low |
|---:|---:|---:|---:|
| 3 | 5 | 0 | 15 |
| `Long.MAX_VALUE` | 2 | 0 | -2 |
| -3 | 5 | -1 | -15 |
| `Long.MIN_VALUE` | 2 | -1 | 0 |
| `Long.MIN_VALUE` | `Long.MIN_VALUE` | 4611686018427387904 | 0 |

Trường hợp `Long.MAX_VALUE * 2` đáng chú ý: phần cao bằng 0 nhưng phần thấp âm. Điều này cho thấy chỉ nhìn phần cao hoặc chỉ nhìn phần thấp riêng lẻ không đủ để quyết định tích có nằm trong miền long có dấu hay không.

## 5. So sánh multiplyHigh với multiplyExact

Hai API giải quyết hai nhu cầu khác nhau:

| API | Kết quả | Khi tích vượt miền long |
|---|---|---|
| `Math.multiplyHigh(x, y)` | Trả 64 bit cao của tích 128 bit | Vẫn trả về phần cao, không ném lỗi overflow |
| `x * y` | Trả 64 bit thấp | Phần cao bị bỏ, kết quả có thể wrap |
| `Math.multiplyExact(x, y)` | Trả tích nếu biểu diễn được bằng long | Ném `ArithmeticException` |

Nếu mục tiêu là biết tích có biểu diễn được trong một long hay không, hãy dùng `Math.multiplyExact`:

~~~java
long product = Math.multiplyExact(x, y);
~~~

Nếu cần phần cao của tích để tiếp tục tính toán rộng hơn, dùng `Math.multiplyHigh`. Không thay `multiplyExact` bằng `multiplyHigh` khi yêu cầu nghiệp vụ là từ chối overflow.

Về mặt bit, tích có dấu biểu diễn được trong 64 bit khi phần cao bằng phần mở rộng dấu của phần thấp. Tuy nhiên, khi chỉ cần một tích long có kiểm tra overflow, `multiplyExact` diễn đạt ý định rõ ràng và tránh tự viết điều kiện bit.

## 6. Toán hạng âm và số âm nhỏ nhất

`Math.multiplyHigh` xử lý toán hạng âm theo ngữ nghĩa long có dấu. Không cần chuyển trị tuyệt đối trước khi gọi.

Một số trường hợp biên hữu ích:

- `-1 * 5 = -5`: high là -1, low là -5.
- `Long.MIN_VALUE * 2 = -2^64`: high là -1, low là 0.
- `Long.MIN_VALUE * Long.MIN_VALUE = 2^126`: high là (2^{62}), low là 0.

Không nên tự lấy `Math.abs(x)` và `Math.abs(y)` trước khi nhân. `Math.abs(Long.MIN_VALUE)` vẫn là `Long.MIN_VALUE` vì giá trị dương tương ứng không thể biểu diễn bằng long. Cách chuyển trị tuyệt đối như vậy sẽ làm sai các trường hợp biên.

## 7. Phân biệt phép nhân signed và unsigned

`Math.multiplyHigh` tính phần cao theo cách hiểu hai toán hạng là số nguyên có dấu. Nếu dữ liệu đang biểu diễn hai số nguyên không dấu 64 bit, phần cao của tích không dấu có thể khác.

Trên Java 18 trở lên có thêm:

~~~java
Math.unsignedMultiplyHigh(long x, long y)
~~~

Phương thức này trả về 64 bit cao của tích khi hai toán hạng được diễn giải như giá trị unsigned 64 bit. Đây là API riêng, không có trong Java 9 đến Java 17.

Chọn đúng phương thức theo cách dữ liệu được diễn giải:

- Số nguyên có dấu: `Math.multiplyHigh`, có từ Java 9.
- Số nguyên không dấu: `Math.unsignedMultiplyHigh`, có từ Java 18.

Không dùng `multiplyHigh` cho dữ liệu unsigned chỉ vì kiểu lưu trữ vẫn là long. Cùng một mẫu bit có thể đại diện cho giá trị signed và unsigned khác nhau.

## 8. Ví dụ chạy được với Java 17+

Tạo file **MultiplyHighDemo.java**:

~~~java
import java.math.BigInteger;

public class MultiplyHighDemo {
    static void showProduct(long x, long y) {
        long high = Math.multiplyHigh(x, y);
        long low = x * y;

        BigInteger exact = BigInteger.valueOf(x)
                .multiply(BigInteger.valueOf(y));

        long expectedHigh = exact.shiftRight(Long.SIZE).longValue();

        if (high != expectedHigh) {
            throw new AssertionError("Incorrect high half");
        }

        System.out.printf(
                "%d * %d => high=%d, low=%d%n",
                x, y, high, low
        );
    }

    public static void main(String[] args) {
        showProduct(3, 5);
        showProduct(Long.MAX_VALUE, 2);
        showProduct(-3, 5);
        showProduct(Long.MIN_VALUE, 2);
        showProduct(Long.MIN_VALUE, Long.MIN_VALUE);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MultiplyHighDemo.java
java MultiplyHighDemo
~~~

Kết quả stdout:

~~~text
3 * 5 => high=0, low=15
9223372036854775807 * 2 => high=0, low=-2
-3 * 5 => high=-1, low=-15
-9223372036854775808 * 2 => high=-1, low=0
-9223372036854775808 * -9223372036854775808 => high=4611686018427387904, low=0
~~~

Trong ví dụ, `BigInteger` được dùng làm phép tính tham chiếu có độ rộng tùy ý để kiểm tra phần cao. `shiftRight(64)` lấy phần cao theo biểu diễn số nguyên có dấu. Phép nhân long thông thường cung cấp phần thấp.

Ví dụ có thể biên dịch với Java 9 vì `Math.multiplyHigh` được bổ sung từ phiên bản này và `BigInteger` đã có từ các phiên bản Java trước đó. Mã ví dụ cũng chạy được trên Java 17+.

## 9. Dùng khi nào?

`Math.multiplyHigh` hữu ích khi thuật toán cần phần cao của tích hai số 64 bit, chẳng hạn:

- Xây dựng phép toán số nguyên rộng hơn 64 bit.
- Tính toán các bước trung gian trong thuật toán số học độ rộng lớn.
- Thực hiện phép nhân có tách high/low để dùng trong thuật toán hash, số học modular hoặc xử lý bit.
- Cài đặt thuật toán cần phần cao của tích mà không tự viết chuỗi phép nhân và dịch bit phức tạp.

API này không thay thế thư viện số học tùy ý như `BigInteger` khi cần biểu diễn toàn bộ số rất lớn, cộng trừ nhiều phép toán rộng hoặc chia số 128 bit. Nó chỉ cung cấp trực tiếp một nửa cao của tích hai long.

Nếu chỉ cần nhân và yêu cầu overflow phải báo lỗi, dùng `Math.multiplyExact`. Nếu cần toàn bộ tích lớn hơn 64 bit và nhiều phép toán tiếp theo, cân nhắc `BigInteger` hoặc một kiểu số rộng tự xây dựng có kiểm thử.

## 10. Lỗi thường gặp

**Nghĩ multiplyHigh trả về toàn bộ tích**

Phương thức chỉ trả 64 bit cao. Lấy phần thấp bằng `x * y` nếu cần ghép biểu diễn 128 bit.

**Nhầm high với phần dư hoặc kết quả chia**

High là nửa bit có trọng số cao của tích 128 bit. Nó không phải phần dư, không phải thương và cũng không phải phép chia cho một hằng số.

**Dùng multiplyHigh để kiểm tra overflow**

Phương thức không ném `ArithmeticException` khi tích vượt miền long. Dùng `Math.multiplyExact` nếu cần phép nhân có kiểm tra overflow.

**Quên rằng phép nhân long thông thường wrap**

`x * y` giữ 64 bit thấp. Khi tích không biểu diễn được trong long, kết quả có thể âm hoặc khác tích toán học.

**Dùng multiplyHigh cho số unsigned**

`multiplyHigh` diễn giải toán hạng là signed. Dùng `unsignedMultiplyHigh` trên Java 18+ nếu cần phần cao của tích unsigned.

**Tự lấy trị tuyệt đối để tránh số âm**

`Long.MIN_VALUE` không có trị tuyệt đối dương biểu diễn được bằng long. Hãy dùng phép toán có ngữ nghĩa signed đúng thay vì đổi dấu thủ công.

## 11. Checklist sử dụng

- Xác định dữ liệu là signed hay unsigned.
- Dùng `Math.multiplyHigh` cho phần cao của tích signed 64-bit; API có từ Java 9.
- Lấy phần thấp bằng phép nhân long thông thường nếu cần ghép đủ hai nửa.
- Dùng `Math.multiplyExact` nếu cần phát hiện tích không biểu diễn được bằng long.
- Dùng `Math.unsignedMultiplyHigh` chỉ khi chạy Java 18+ và dữ liệu là unsigned.
- Kiểm thử với số dương lớn, số âm, `Long.MIN_VALUE` và `Long.MAX_VALUE`.
- Dùng `BigInteger` làm phép tính tham chiếu khi kiểm chứng thuật toán 128-bit.

`Math.multiplyHigh` giúp lấy chính xác phần cao của tích hai long theo ngữ nghĩa số nguyên có dấu. Kết hợp với phần thấp, nó cung cấp nền tảng cho các phép tính cần xem xét tích rộng 128 bit mà không nhầm lẫn với phép nhân long có kiểm tra overflow.
