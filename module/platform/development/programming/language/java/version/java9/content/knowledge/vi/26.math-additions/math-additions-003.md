# Tích đầy đủ của hai int bằng Math.multiplyFull

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao phép nhân hai giá trị \`int\` có thể tràn trước khi gán vào biến \`long\`.
- Dùng \`Math.multiplyFull(int, int)\` để nhận tích chính xác của hai số nguyên 32-bit.
- Phân biệt \`multiplyFull\`, ép kiểu trước phép nhân và \`multiplyExact\`.
- Xác định khi nào cần \`long\` và khi nào phải dùng \`BigInteger\`.
- Kiểm thử các giá trị biên âm, dương và trường hợp kết quả vượt phạm vi \`int\`.

## 1. Vấn đề: tích có thể lớn hơn phạm vi int

Java \`int\` là số nguyên có dấu 32-bit, với phạm vi:

\`Integer.MIN_VALUE = -2^31\` đến \`Integer.MAX_VALUE = 2^31 - 1\`.

Phép nhân hai \`int\` vẫn được thực hiện bằng kiểu \`int\`. Nếu kết quả toán học nằm ngoài phạm vi này, giá trị bị tràn theo quy tắc số nguyên của Java; phép nhân không tự ném \`ArithmeticException\`.

Ví dụ:

~~~java
int a = 50_000;
int b = 50_000;

int product = a * b;
System.out.println(product);
~~~

Tích toán học là 2.500.000.000, lớn hơn \`Integer.MAX_VALUE\` (2.147.483.647). Vì vậy, biến \`product\` nhận giá trị đã tràn:

~~~text
-1794967296
~~~

Một lỗi thường gặp là gán kết quả đó vào \`long\`:

~~~java
long product = a * b; // Vẫn tràn
~~~

Hai toán hạng vẫn là \`int\`, nên phép nhân diễn ra ở kiểu \`int\` trước. Chỉ sau khi kết quả tràn được tạo ra, Java mới mở rộng giá trị đó thành \`long\`. Việc đổi kiểu ở biến nhận không thể khôi phục những bit đã mất.

Nếu muốn dùng phép nhân thông thường, phải mở rộng ít nhất một toán hạng trước phép nhân:

~~~java
long product = (long) a * b;
~~~

Lúc này phép nhân được thực hiện bằng \`long\`, nên tích của hai \`int\` được giữ chính xác.

## 2. Math.multiplyFull từ Java 9

Java 9 bổ sung \`Math.multiplyFull(int x, int y)\`. Method nhận hai toán hạng \`int\` và trả về tích đầy đủ dưới dạng \`long\`:

~~~java
long product = Math.multiplyFull(a, b);
~~~

Với hai giá trị \`int\` bất kỳ, tích toán học luôn nằm trong phạm vi \`long\`:

- Độ lớn lớn nhất của một toán hạng là \(2^{31}\).
- Độ lớn lớn nhất của tích không vượt quá \(2^{31} \times 2^{31} = 2^{62}\).
- \`long\` có phạm vi từ \(-2^{63}\) đến \(2^{63}-1\), nên chứa được mọi tích của hai \`int\`.

Do đó, \`Math.multiplyFull(int, int)\` có thể trả về chính xác tích của mọi cặp \`int\`, kể cả khi kết quả không thể biểu diễn bằng \`int\`. Với overload này, không cần xử lý overflow của tích bằng cách bắt exception.

Ví dụ:

~~~java
int a = 50_000;
int b = 50_000;

long product = Math.multiplyFull(a, b);
System.out.println(product);
~~~

Output:

~~~text
2500000000
~~~

Kết quả được trả về trực tiếp ở kiểu \`long\`, không trải qua bước nhân kiểu \`int\`.

## 3. So sánh ba cách nhân

| Cách viết | Kiểu thực hiện phép nhân | Hành vi khi tích vượt int |
|---|---|---|
| \`long p = a * b;\` | \`int\` | Tràn trước khi mở rộng |
| \`long p = (long) a * b;\` | \`long\` | Giữ chính xác tích của hai int |
| \`long p = Math.multiplyFull(a, b);\` | API trả tích đầy đủ kiểu \`long\` | Giữ chính xác tích của hai int |

Ép kiểu trước phép nhân và \`multiplyFull\` đều có thể cho kết quả chính xác. \`multiplyFull\` diễn đạt rõ ý định lấy tích đầy đủ của hai \`int\`, đặc biệt hữu ích khi đọc code số học hoặc khi muốn dùng API được thiết kế riêng cho trường hợp này.

Lưu ý: ép kiểu phải xảy ra trước phép nhân. Các cách sau đều quá muộn:

~~~java
long p1 = (long) (a * b); // a * b đã tính ở int
long p2 = 1L * (a * b);   // Biểu thức trong ngoặc đã tràn
~~~

## 4. Khác với Math.multiplyExact

\`Math.multiplyExact\` giải quyết một yêu cầu khác: thực hiện phép nhân và báo lỗi nếu kết quả không thể biểu diễn bằng kiểu trả về.

Với hai toán hạng \`int\`:

~~~java
int safe = Math.multiplyExact(1_000, 2_000);
// safe == 2_000_000

int overflow = Math.multiplyExact(50_000, 50_000);
// Ném ArithmeticException
~~~

So sánh:

- **\`Math.multiplyFull(int, int)\`:** trả tích chính xác dưới dạng \`long\`, kể cả khi tích vượt phạm vi \`int\`.
- **\`Math.multiplyExact(int, int)\`:** trả \`int\`; nếu tích không vừa \`int\`, ném \`ArithmeticException\`.
- **\`(long) a * b\`:** thực hiện phép nhân ở kiểu \`long\`, phù hợp khi chỉ cần mở rộng hai toán hạng trước khi nhân.

Chọn theo hợp đồng của chương trình. Nếu kết quả cần giữ toàn bộ tích hai \`int\`, dùng \`multiplyFull\` hoặc mở rộng toán hạng trước phép nhân. Nếu kết quả bắt buộc phải vừa \`int\` và overflow phải được phát hiện, dùng \`multiplyExact\`.

## 5. Ví dụ hoàn chỉnh có thể chạy

Tạo file **MultiplyFullDemo.java**:

~~~java
public class MultiplyFullDemo {

    private static long fullProduct(int left, int right) {
        long actual = Math.multiplyFull(left, right);
        long widenedMultiplication = (long) left * right;

        if (actual != widenedMultiplication) {
            throw new AssertionError("Unexpected full product");
        }
        return actual;
    }

    private static void printProduct(int left, int right) {
        System.out.println(
                left + " * " + right + " = "
                        + fullProduct(left, right));
    }

    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        int intProduct = a * b;
        long widenedTooLate = a * b;
        long fullProduct = Math.multiplyFull(a, b);
        long widenedBeforeMultiply = (long) a * b;

        System.out.println("int multiplication = " + intProduct);
        System.out.println("widened after multiply = " + widenedTooLate);
        System.out.println("multiplyFull = " + fullProduct);
        System.out.println("cast before multiply = " + widenedBeforeMultiply);

        try {
            Math.multiplyExact(a, b);
            throw new AssertionError("Expected int overflow");
        } catch (ArithmeticException expected) {
            System.out.println("multiplyExact(int, int) = overflow detected");
        }

        printProduct(Integer.MAX_VALUE, Integer.MAX_VALUE);
        printProduct(Integer.MIN_VALUE, Integer.MIN_VALUE);
        printProduct(Integer.MIN_VALUE, Integer.MAX_VALUE);
        printProduct(-50_000, 50_000);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all -d out MultiplyFullDemo.java
java -cp out MultiplyFullDemo
~~~

Output chính xác:

~~~text
int multiplication = -1794967296
widened after multiply = -1794967296
multiplyFull = 2500000000
cast before multiply = 2500000000
multiplyExact(int, int) = overflow detected
2147483647 * 2147483647 = 4611686014132420609
-2147483648 * -2147483648 = 4611686018427387904
-2147483648 * 2147483647 = -4611686016279904256
-50000 * 50000 = -2500000000
~~~

Method \`fullProduct\` cũng đối chiếu kết quả \`multiplyFull\` với phép nhân sau khi mở rộng toán hạng. Các cặp biên giúp xác nhận cả tích dương lớn nhất, tích của hai giá trị âm nhỏ nhất và tích âm có độ lớn lớn.

## 6. Khi nào cần BigInteger?

\`multiplyFull(int, int)\` trả về \`long\`, vì tích của hai \`int\` luôn vừa \`long\`. Điều này không đúng với hai toán hạng \`long\` bất kỳ: tích của chúng có thể vượt phạm vi 64-bit.

Nếu nghiệp vụ cần giữ tích chính xác của các số nguyên có độ lớn tùy ý, dùng \`BigInteger\`:

~~~java
import java.math.BigInteger;

BigInteger left = new BigInteger("9000000000000000000");
BigInteger right = new BigInteger("9000000000000000000");

BigInteger product = left.multiply(right);
System.out.println(product);
~~~

Không thay \`multiplyFull(int, int)\` bằng \`BigInteger\` nếu miền dữ liệu đã được bảo đảm là hai \`int\` và \`long\` đáp ứng yêu cầu. Chọn kiểu kết quả theo giới hạn dữ liệu và hợp đồng cần có.

## 7. Lỗi thường gặp

### Chỉ đổi kiểu biến nhận sang long

\`long result = x * y\` vẫn nhân ở kiểu \`int\`. Hãy ép kiểu ít nhất một toán hạng trước phép nhân hoặc gọi \`Math.multiplyFull\`.

### Ép kiểu sau khi nhân

\`(long) (x * y)\` không sửa được overflow đã xảy ra. Vị trí ép kiểu phải nằm trên một toán hạng trước toán tử \`*\`.

### Nhầm multiplyFull với multiplyExact

\`multiplyFull\` trả kết quả đầy đủ ở kiểu rộng hơn. \`multiplyExact\` kiểm tra kết quả có vừa kiểu trả về hay không và ném exception nếu không vừa.

### Cho rằng mọi phép nhân số nguyên đều ném exception khi overflow

Phép nhân toán tử \`*\` của kiểu nguyên không tự ném exception khi tràn. Cần dùng API \`multiplyExact\` nếu muốn phát hiện trường hợp đó.

### Nghĩ multiplyFull hỗ trợ mọi cặp long

Bài học này dùng overload nhận hai \`int\`. Tích của hai \`long\` bất kỳ không được bảo đảm vừa \`long\`; nếu cần độ chính xác tùy ý, dùng \`BigInteger\`.

### Không kiểm thử giá trị biên

Ví dụ với các số nhỏ thường không làm lộ overflow. Hãy kiểm tra \`Integer.MAX_VALUE\`, \`Integer.MIN_VALUE\`, số âm và tích vượt \`int\`.

## 8. Checklist

- [ ] Đã xác định kiểu của cả hai toán hạng trước phép nhân.
- [ ] Không gán \`int * int\` vào \`long\` với kỳ vọng tự tránh overflow.
- [ ] Đã dùng \`Math.multiplyFull(int, int)\` khi cần tích đầy đủ kiểu \`long\`.
- [ ] Đã phân biệt \`multiplyFull\` với \`multiplyExact\`.
- [ ] Đã ép kiểu toán hạng trước phép nhân nếu dùng cách nhân thông thường ở \`long\`.
- [ ] Đã dùng \`BigInteger\` khi miền dữ liệu vượt khả năng biểu diễn của \`long\`.
- [ ] Đã kiểm thử số dương lớn, số âm và các giá trị biên của \`int\`.
- [ ] Đã biên dịch ví dụ bằng mức Java phù hợp.

