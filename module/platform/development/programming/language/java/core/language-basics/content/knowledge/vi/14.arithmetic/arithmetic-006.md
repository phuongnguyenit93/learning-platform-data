# Tràn số nguyên không tự động ném ngoại lệ trong Java

> **Java core — language-basics / Số học**  
> **Môi trường:** JDK 17+; chỉ dùng thư viện chuẩn Java.  
> **Mục tiêu:** Nhận diện tràn số ở `int`/`long`, hiểu vì sao phép tính vẫn tiếp tục mà **không tự ném ngoại lệ**, và biết cách chọn `Math.*Exact`, chuyển kiểu đúng thời điểm hoặc `BigInteger` để không âm thầm mất kết quả.

## 1. Thế nào là tràn số nguyên?

`int` là kiểu nguyên **32 bit có dấu**, từ **-2.147.483.648** đến **2.147.483.647**. `long` là kiểu nguyên **64 bit có dấu**, từ **-9.223.372.036.854.775.808** đến **9.223.372.036.854.775.807**.

Một phép cộng, trừ hoặc nhân có kết quả toán học vượt miền biểu diễn sẽ **tràn số** (*integer overflow*).

~~~java
int max = Integer.MAX_VALUE; // 2147483647
int wrapped = max + 1;
System.out.println(wrapped); // -2147483648
~~~

Java **không tự động ném `ArithmeticException` khi cộng, trừ hoặc nhân tràn `int`/`long`**. Phần bit kết quả còn lại được diễn giải theo biểu diễn số nguyên có dấu, nên kết quả có thể đổi dấu hoặc khác xa giá trị toán học mong đợi.

- `int` sử dụng 32 bit; phép toán nguyên tràn có hiệu ứng quay vòng theo **modulo `2^32`**.
- `long` sử dụng 64 bit; tương tự theo **modulo `2^64`**.
- Điều này là hành vi **được Java quy định**, không phải hành vi ngẫu nhiên hoặc lỗi bộ nhớ.
- `float`/`double` dùng quy tắc số thực khác: có thể ra `Infinity`/`NaN`. Chúng không phải giải pháp giữ nguyên mọi giá trị nguyên.

**Kết luận:** Chương trình chạy thành công **không chứng minh phép tính đúng về mặt toán học**.

## 2. Các phép toán dễ tràn nhưng vẫn chạy

| Biểu thức | Giá trị toán học | Kết quả `int` thực tế |
| --- | ---: | ---: |
| `Integer.MAX_VALUE + 1` | 2147483648 | -2147483648 |
| `Integer.MIN_VALUE - 1` | -2147483649 | 2147483647 |
| `50_000 * 50_000` | 2500000000 | -1794967296 |
| `-Integer.MIN_VALUE` | 2147483648 | -2147483648 |
| `Integer.MIN_VALUE / -1` | 2147483648 | -2147483648 |

Phép `Integer.MIN_VALUE / -1` là **trường hợp đặc biệt**: phép chia nguyên này có kết quả toán học vượt `int`, Java vẫn trả `Integer.MIN_VALUE` mà **không ném ngoại lệ**. Phần dư `Integer.MIN_VALUE % -1` bằng **0**.

Tương tự với `long`:

~~~java
long max = Long.MAX_VALUE;
System.out.println(max + 1L); // -9223372036854775808
~~~

Thao tác tăng `++`, giảm `--` hoặc gán cộng `+=` cũng có thể tràn khi tính và lưu vào kiểu nguyên. Ví dụ `int n = Integer.MAX_VALUE; n++;` khiến `n` trở thành `Integer.MIN_VALUE`.

## 3. Chuyển sang `long`: phải làm **trước** phép tính

Một bẫy thường gặp:

~~~java
int max = Integer.MAX_VALUE;

long wrong = max + 1;        // -2147483648, rồi mới mở rộng sang long.
long right = (long) max + 1; // 2147483648, phép cộng thực hiện bằng long.
~~~

Trong `long wrong = max + 1`, hai toán hạng đều có kiểu `int` nên **cộng kiểu `int` trước**, tràn rồi mới gán sang `long`. Kiểu biến đích không cứu được phép toán đã xảy ra.

Ngay cả cast sau ngoặc cũng quá muộn:

~~~java
long wrongAgain = (long) (max + 1); // -2147483648
long rightAgain = ((long) max) + 1; // 2147483648
~~~

**Đối với phép nhân**, hãy chuyển toán hạng trước phép nhân:

~~~java
int a = 50_000, b = 50_000;
long wrongProduct = a * b;         // -1794967296
long rightProduct = (long) a * b; // 2500000000
~~~

**Giới hạn:** `long` cũng có thể tràn. Việc chuyển `int` sang `long` chỉ giải quyết được khi kết quả **nằm trong miền `long`**; không có kiểu primitive nguyên nào của Java tự mở rộng vô hạn.

## 4. Muốn phát hiện tràn: dùng các phép toán `Math.*Exact`

Java có các API **kiểm tra tràn** chủ động. Khi kết quả không nằm trong miền kiểu số nguyên được yêu cầu, chúng ném **`ArithmeticException`**:

| Phương thức | Vai trò |
| --- | --- |
| `Math.addExact(a, b)` | Cộng, phát hiện tràn |
| `Math.subtractExact(a, b)` | Trừ, phát hiện tràn |
| `Math.multiplyExact(a, b)` | Nhân, phát hiện tràn |
| `Math.incrementExact(a)` | Tăng 1, phát hiện tràn |
| `Math.decrementExact(a)` | Giảm 1, phát hiện tràn |
| `Math.negateExact(a)` | Đổi dấu, phát hiện trường hợp giá trị nhỏ nhất |
| `Math.toIntExact(value)` | Chuyển `long` sang `int`, kiểm tra ngoài miền |

Ví dụ:

~~~java
int a = Integer.MAX_VALUE;

try {
    int sum = Math.addExact(a, 1);
    System.out.println(sum);
} catch (ArithmeticException ex) {
    System.out.println("overflow detected");
}
~~~

Khi hệ thống yêu cầu **không được sai một đơn vị**, dùng API checked arithmetic có ý nghĩa hơn tự ngầm chấp nhận phép tính quay vòng. Đừng dùng `Math.addExact` trên một kết quả **đã tràn trước đó** rồi hy vọng nó có thể khôi phục giá trị gốc: phải gọi hàm kiểm tra **ngay tại phép tính có nguy cơ tràn**.

## 5. Chia cho 0 là ngoại lệ khác

Đừng nhầm **tràn số** với **chia nguyên cho 0**:

~~~java
int a = 10;
int zero = 0;
// a / zero; // ArithmeticException tại runtime.
// a % zero; // ArithmeticException tại runtime.
~~~

- `int`/`long` chia hoặc lấy phần dư cho **0** → `ArithmeticException`.
- `int`/`long` cộng, trừ, nhân bị tràn → **không tự ném**.
- `Integer.MIN_VALUE / -1` → **tràn theo quy tắc đặc biệt nhưng không ném**.
- `Math.addExact`/`multiplyExact`/`negateExact`... → **có ném** nếu không thể biểu diễn chính xác.

Nếu mẫu số có thể bằng 0, cần kiểm tra đầu vào. Việc chọn API `Exact` không thay thế guard chia cho 0.

## 6. Chương trình Java 17+ chạy độc lập

Tạo file **IntegerOverflowDemo.java**:

~~~java
import java.math.BigInteger;

public final class IntegerOverflowDemo {
    private static void checked(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=ok");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int min = Integer.MIN_VALUE;
        long maxLong = Long.MAX_VALUE;

        System.out.println("addWrap=" + (max + 1));
        System.out.println("subtractWrap=" + (min - 1));
        System.out.println("multiplyWrap=" + (50_000 * 50_000));
        System.out.println("longWrap=" + (maxLong + 1L));

        long lateWiden = max + 1;
        long earlyWiden = (long) max + 1;
        System.out.println("lateWiden=" + lateWiden);
        System.out.println("earlyWiden=" + earlyWiden);

        System.out.println("negateMinimum=" + (-min));
        System.out.println("minDivNegOne=" + (min / -1));
        System.out.println("minRemNegOne=" + (min % -1));

        checked("addExact", () -> Math.addExact(max, 1));
        checked("subtractExact", () -> Math.subtractExact(min, 1));
        checked("multiplyExact", () -> Math.multiplyExact(50_000, 50_000));
        checked("negateExact", () -> Math.negateExact(min));
        checked("toIntExact", () -> Math.toIntExact(2_147_483_648L));

        int zero = 0;
        checked("divideZero", () -> {
            int result = max / zero;
            System.out.println(result);
        });

        BigInteger exact = BigInteger.valueOf(maxLong).add(BigInteger.ONE);
        System.out.println("bigInteger=" + exact);
    }
}
~~~

Mở terminal tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 IntegerOverflowDemo.java
java IntegerOverflowDemo
~~~

**Expected output chính xác:**

~~~text
addWrap=-2147483648
subtractWrap=2147483647
multiplyWrap=-1794967296
longWrap=-9223372036854775808
lateWiden=-2147483648
earlyWiden=2147483648
negateMinimum=-2147483648
minDivNegOne=-2147483648
minRemNegOne=0
addExact=ArithmeticException
subtractExact=ArithmeticException
multiplyExact=ArithmeticException
negateExact=ArithmeticException
toIntExact=ArithmeticException
divideZero=ArithmeticException
bigInteger=9223372036854775808
~~~

Các dòng `addWrap`, `subtractWrap`, `multiplyWrap`, `longWrap` và `minDivNegOne` **không có exception**, mặc dù giá trị toán học không vừa kiểu đích. Các dòng `...Exact=ArithmeticException` cho thấy ngoại lệ chỉ xuất hiện khi chủ động dùng phép tính có kiểm tra. `divideZero` là lỗi **chia nguyên cho 0**, độc lập với tràn số.

## 7. Khi kết quả vượt cả `long`: dùng `BigInteger`

`BigInteger` trong `java.math` lưu số nguyên với độ lớn không bị giới hạn bởi 32/64 bit primitive (trong thực tế còn giới hạn bộ nhớ):

~~~java
BigInteger x = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger y = x.add(BigInteger.ONE);
System.out.println(y); // 9223372036854775808
~~~

Các phép tính với `BigInteger` dùng method như `add`, `subtract`, `multiply`. Nó **không** hỗ trợ viết `x + y` như primitive.

Nếu vẫn cần xuất `int`/`long`, kiểm tra miền hoặc dùng các phép chuyển đổi chính xác như `intValueExact()`/`longValueExact()` để **không âm thầm mất số**. Chuyển `BigInteger` sang primitive bằng `intValue()` đơn thuần có thể cắt mất các bit quan trọng.

## 8. Thực hành an toàn và bài tập

| Yêu cầu | Lựa chọn |
| --- | --- |
| Đếm, tính tổng nhỏ chắc chắn vừa `int` | Dùng `int` và kiểm soát miền dữ liệu |
| Kết quả có thể vượt `int` nhưng vừa `long` | Chuyển một toán hạng sang `long` **trước khi tính** |
| Không được phép tràn âm thầm | `Math.addExact`, `subtractExact`, `multiplyExact`, ... |
| Có thể vượt cả `long` | `BigInteger`, cùng xử lý giới hạn tài nguyên |
| Chuyển `long` về `int` mà phải giữ nguyên giá trị | `Math.toIntExact` |
| Chia cho mẫu số có thể bằng 0 | Guard đầu vào trước `/` hoặc `%` |

**Bài 1.** Tính `Integer.MAX_VALUE + 1` và `Integer.MIN_VALUE - 1` trong Java. Vì sao chương trình không dừng?

**Bài 2.** So sánh `long x = 50_000 * 50_000;` với `long y = 50_000L * 50_000;`. Phép nào tràn? Khi nào Java quyết định kiểu phép nhân?

**Bài 3.** Viết `Math.multiplyExact(50_000, 50_000)` trong `try/catch`. Giải thích khác biệt với toán tử `*`.

**Bài 4.** Dự đoán `Integer.MIN_VALUE / -1` và `Integer.MIN_VALUE % -1`. Tại sao đây không giống trường hợp chia cho 0?

**Bài 5.** Tính `Long.MAX_VALUE + 1` bằng `BigInteger` mà không mất giá trị nguyên ban đầu.

### Ghi nhớ

**Java không tự động ném ngoại lệ khi các phép toán nguyên `int`/`long` thông thường bị tràn.** Giá trị có thể quay vòng theo giới hạn bit và làm sai dữ liệu mà chương trình vẫn chạy. Nếu cần kết quả chính xác, hãy **mở rộng toán hạng trước khi tính** (khi `long` đủ miền), dùng **`Math.*Exact`** để phát hiện tràn, hoặc **`BigInteger`** khi vượt miền `long`. Chia nguyên cho 0 là một lỗi riêng: nó **ném `ArithmeticException`**.
