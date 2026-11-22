# Kiểm thử biên và tránh làm tràn trước khi gọi phương thức số học kiểm tra tràn

## 1. Vấn đề trọng tâm

Trong Java, các phép cộng, trừ, nhân trên số nguyên `int` và `long` **không tự ném ngoại lệ khi tràn**. Giá trị được tính theo số học nhị phân có độ rộng cố định và có thể quay vòng (*wraparound*). Vì vậy, một phép tính trông rất đơn giản có thể âm thầm tạo giá trị sai.

Các phương thức `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact`, `absExact` và `toIntExact` có thể phát hiện tràn **trong phạm vi thao tác do chính chúng thực hiện**, hoặc trong chuyển đổi từ `long` về `int`.

**Nhưng:** nếu một phép cộng/nhân đã xảy ra **trước khi đối số được truyền vào phương thức kiểm tra**, phương thức đó chỉ nhìn thấy **giá trị đã bị tràn**. Nó không thể khôi phục giá trị toán học ban đầu.

```java
int a = 50_000;
int b = 50_000;

long wrong = (long) (a * b);         // -1_794_967_296: int đã tràn
long right = (long) a * b;           //  2_500_000_000: nâng kiểu TRƯỚC khi nhân
long checked = Math.multiplyExact((long) a, b); // 2_500_000_000
```

Cả `wrong`, `right` và `checked` đều là `long`, nhưng chỉ hai biểu thức cuối tính đúng vì phép nhân diễn ra ở miền `long`. `Math.multiplyExact(a,b)` với **hai toán hạng kiểu `int`** sẽ ném `ArithmeticException`, vì kết quả 2,5 tỷ nằm ngoài miền `int`.

**Mục tiêu bài học:** thiết kế các phép tính **không tràn trước khi gọi phương thức**, kiểm tra các giá trị **ngay sát biên**, xây test có **oracle độc lập** như `BigInteger`, phát hiện lỗi tràn trung gian dù kết quả cuối vẫn vừa miền, và áp dụng cho kích thước bộ nhớ, chỉ số, offset, bộ đếm hay tổng số lượng.

**Bối cảnh phiên bản:** chủ đề thuộc module Java 14 nhưng phần lớn `Math.*Exact` đã có từ Java 8, `Math.multiplyFull(int,int)` từ Java 9 và `Math.absExact` hiện có trong Java 17+. Đây đều là kiến thức **vẫn áp dụng trên Java hiện đại**. Mã độc lập bên dưới được kiểm chứng bằng `javac --release 17`, không dùng API mới hơn Java 17 trong chương trình cần chạy.

## 2. Hiểu đúng giới hạn của `int` và `long`

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

Trong mã:

```java
int min = Integer.MIN_VALUE;
int max = Integer.MAX_VALUE;
long minLong = Long.MIN_VALUE;
long maxLong = Long.MAX_VALUE;
```

Các tình huống cần kiểm thử không chỉ là `MAX + 1` mà còn:

- `MIN - 1` và `MAX - (-1)` khi phép trừ.
- `MIN * (-1)` và `MAX * 2` khi nhân.
- `-MIN` và `Math.abs(MIN)` khi đổi dấu/trị tuyệt đối.
- `MAX++` và `MIN--` khi tăng/giảm.
- `MIN / -1`: phép chia số nguyên **có thể tràn dù mẫu khác 0**.
- `(a + b) / 2`, `n * (n + 1) / 2`, `row * width + col`: phép trung gian tràn trước khi chia/đổi kiểu/kiểm tra.
- `offset + length`: có thể quay về âm và vượt qua điều kiện kiểm tra phạm vi không an toàn.
- `long` tràn trong tính byte offset, timestamp delta, số lượng lớn hoặc tiền được lưu bằng đơn vị nguyên.

Theo Java Language Specification (JLS), số học `int`/`long` có quy tắc wraparound, không tự phát tín hiệu ngoại lệ overflow. Một phép tính đã quay vòng **không tự được sửa** chỉ vì sau đó gán vào kiểu rộng hơn.

Ví dụ:

```java
int x = Integer.MAX_VALUE;
int wrapped = x + 1;            // Integer.MIN_VALUE
long stillWrong = x + 1;        // Tràn ở int, SAU ĐÓ mới widening
long correct = (long) x + 1;    // 2_147_483_648
```

Đừng nhầm overflow của số nguyên với phép chia cho 0: `x / 0` ném `ArithmeticException`, nhưng `Integer.MIN_VALUE / -1` có kết quả quay vòng mà phép chia thường không ném.

## 3. Quy tắc then chốt: phép tính diễn ra **trước** lời gọi phương thức

Java đánh giá biểu thức đối số **trước khi** phương thức nhận được chúng. Hãy xem:

```java
int a = 50_000;
int b = 50_000;

// SAI: phép nhân int xảy ra trước Math.toIntExact.
int broken = Math.toIntExact(a * b);

// ĐÚNG: có một toán hạng long từ trước phép nhân.
int checkedNarrowing = Math.toIntExact((long) a * b);
```

**Diễn biến cụ thể:**

1. Trong `Math.toIntExact(a * b)`, toán hạng `a` và `b` đều là `int`; nhân cho một `int` bị tràn thành `-1_794_967_296`.
2. Vì `Math.toIntExact` nhận `long`, JVM chuyển **giá trị `int` đã sai** sang `long`.
3. Giá trị âm đó vẫn nằm trong miền `int`, nên `toIntExact` **không ném ngoại lệ**.
4. Ở biểu thức `Math.toIntExact((long) a * b)`, cast `(long)a` xảy ra **trước** nhân, kết quả `2_500_000_000L` đúng; `toIntExact` sau đó ném `ArithmeticException` vì không thể thu hẹp về `int`.

**Vì thế `toIntExact` chỉ kiểm tra phép chuyển `long → int`, không phải phép tính đã diễn ra ở nơi khác.**

Bảng so sánh:

| Biểu thức | Kiểu của phép nhân | Kết quả/hành vi |
| --- | --- | --- |
| `a * b` | `int` | Tràn im lặng |
| `(long)(a * b)` | `int` trước, rồi cast | Vẫn sai |
| `1L * a * b` | `long` từ phép nhân đầu | Đúng với ví dụ, còn phải coi chừng tràn `long` |
| `(long)a * b` | `long` | Đúng với ví dụ |
| `Math.multiplyExact(a,b)` | `int` | Ném nếu ngoài miền `int` |
| `Math.multiplyExact((long)a,b)` | `long` | Trả đúng nếu trong miền `long` |
| `Math.toIntExact((long)a*b)` | `long` rồi kiểm tra thu hẹp | Ném nếu kết quả ngoài miền `int` |
| `Math.toIntExact((long)(a*b))` | `int` đã tràn | **Không phát hiện** sai số đã xảy ra |

### 3.1. Cast sau phép tính là quá muộn

Một lỗi thường gặp khi sửa code:

```java
long total = (long) (count * unitSize);
```

Nếu cả hai đầu vào là `int` thì `count * unitSize` vẫn là `int`. Đúng hơn:

```java
long total = (long) count * unitSize;
```

Với giá trị thực sự có thể làm tràn `long`, dùng:

```java
long total = Math.multiplyExact((long) count, unitSize);
```

Kiểu đích của biến `total` không bắt buộc phép tính ở bên phải được thực hiện ở `long`; **numeric promotion của toán hạng tại chính phép toán** mới quyết định.

### 3.2. Đừng truyền **một biểu thức đã tính sai** cho `*Exact`

```java
// SAI: bên trong đối số thứ nhất đã là phép cộng int chưa được kiểm tra.
int corrupted = Math.addExact(a + b, -1);

// ĐÚNG: mọi bước cộng/trừ đều được kiểm tra.
int safe = Math.subtractExact(Math.addExact(a, b), 1);
```

Đây là **snippet minh họa**; `a`/`b` phải là các biến `int` đã tồn tại. Trong công thức nhiều bước, **bất kỳ bước không an toàn nào cũng có thể làm hỏng dữ liệu trước khi tới hàm exact cuối cùng**.

Một cách đúng khác nếu phép toán phải dùng kiểu lớn là:

```java
long sum = Math.addExact((long) a, b);
long result = Math.subtractExact(sum, 1L);
```

Khi sau đó thật sự cần `int`, gọi `Math.toIntExact(result)` **sau khi đã tính đúng**.

### 3.3. Binary numeric promotion và thứ tự toán tử

Theo JLS `5.6, với các toán tử `+`, `-`, `*`, nếu cả hai toán hạng là `int`, phép tính được thực hiện ở `int`; nếu ít nhất một toán hạng là `long`, bên kia được nâng thành `long` trước phép tính.

```java
int x = 50_000, y = 50_000;

long wrong = x * y * 1L; // x * y đã tràn TRƯỚC khi nhân 1L
long right = 1L * x * y; // toán hạng đầu là long ngay từ phép đầu
```

Vì `*` kết hợp từ trái sang phải, đặt `1L` **ở cuối** không cứu được phép toán đầu. Tuy nhiên, đặt `1L` đầu cũng **không** kiểm tra tràn `long`; dùng `Math.multiplyExact(long,long)` nếu miền `long` có nguy cơ không đủ.

Ngoài ra, các phép dịch bit `<<` không dùng binary numeric promotion từ toán hạng bên phải: `1 << 31` vẫn là `int` âm, `1L << 31` là `long` dương. Nếu làm thuật toán đếm kích thước, không sử dụng shift không kiểm tra rồi tin rằng kết quả chắc chắn dương/hợp lệ.

## 4. Các công cụ exact phù hợp trong Java hiện đại

| Phương thức | Dạng thường gặp | Khi nào ném `ArithmeticException` |
| --- | --- | --- |
| `Math.addExact` | `int,int`; `long,long` | Tổng vượt miền kết quả |
| `Math.subtractExact` | `int,int`; `long,long` | Hiệu vượt miền kết quả |
| `Math.multiplyExact` | `int,int`; `long,long`; `long,int` | Tích vượt miền kết quả |
| `Math.incrementExact` | `int` hoặc `long` | Tăng 1 vượt `MAX_VALUE` |
| `Math.decrementExact` | `int` hoặc `long` | Giảm 1 dưới `MIN_VALUE` |
| `Math.negateExact` | `int` hoặc `long` | Phủ định `MIN_VALUE` |
| `Math.absExact` | `int` hoặc `long` | Trị tuyệt đối `MIN_VALUE` không biểu diễn được |
| `Math.toIntExact` | `long` → `int` | Đối số ngoài miền `int` |
| `Math.multiplyFull` | `int,int` → `long` | **Không ném vì tích của hai int luôn vừa long** |
| `BigInteger.*` + `intValueExact()/longValueExact()` | Số nguyên độ chính xác không giới hạn | Chỉ lỗi khi chuyển kết quả xuống miền đích quá nhỏ |

Các phương thức `Math.*Exact` chỉ xử lý overflow của phép tính được mô tả. Chúng không tự validate độ dài mảng, số lượng âm, input chưa parse, cú pháp file, quyền truy cập, hoặc một giới hạn nghiệp vụ nhỏ hơn `Integer.MAX_VALUE`.

### 4.1. `Math.multiplyFull(int,int)` là một lựa chọn đúng cho tích hai `int`

```java
int a = 50_000;
int b = 50_000;

long product = Math.multiplyFull(a, b); // 2_500_000_000
```

`multiplyFull` trả chính xác **long product** của hai số nguyên `int`; khác với `Math.multiplyExact(int,int)` vốn từ chối kết quả ngoài `int`. Nó không phải API tính tùy ý tích của **hai `long`** không tràn. Nếu cần kết quả vượt `long`, dùng `BigInteger` hoặc thiết kế phép toán khác.

### 4.2. `Math.abs(Integer.MIN_VALUE)` là một góc biên nguy hiểm

```java
int value = Integer.MIN_VALUE;
int wrong = Math.abs(value); // Vẫn âm: Integer.MIN_VALUE

// Java 17+: ném ArithmeticException thay vì trả một số âm.
int checked = Math.absExact(value);
```

Đây là **snippet** minh họa; lệnh `absExact` sẽ ném và cần được xử lý ở ranh giới phù hợp. Giá trị `-Integer.MIN_VALUE` cũng quay về chính `Integer.MIN_VALUE`; thay vào đó `Math.negateExact` kiểm tra chính xác.

### 4.3. Chia `MIN_VALUE / -1` và Java 17

`Integer.MIN_VALUE / -1` hoặc `Long.MIN_VALUE / -1` là trường hợp đặc biệt: **kết quả toán học không vừa miền số**, nhưng toán tử `/` của Java trả về `MIN_VALUE` theo quy tắc số học số nguyên, không tự báo overflow.

Với Java 17, có thể kiểm tra trường hợp này trước khi chia:

```java
static int safeDivide(int a, int b) {
    if (b == 0) {
        throw new ArithmeticException("division by zero");
    }
    if (a == Integer.MIN_VALUE && b == -1) {
        throw new ArithmeticException("division overflow");
    }
    return a / b;
}
```

Đây là method có thể đặt trong một class. **Java 18+** có `Math.divideExact` và `Math.floorDivExact` để xử lý case overflow này, nhưng **không dùng chúng trong chương trình biên dịch `--release 17`** vì chúng không thuộc API Java 17. Đây là phân biệt **độ tương thích**, không phải khuyến nghị dùng API lỗi thời.

## 5. Chương trình runnable: thấy rõ tràn trước lời gọi và các biên nguy hiểm

**Tệp `CheckedArithmeticDemo.java` — Java 17+:**

```java
public class CheckedArithmeticDemo {
    static void expectOverflow(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=MISSED");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=OVERFLOW");
        }
    }

    static int safeDivide(int a, int b) {
        if (b == 0) {
            throw new ArithmeticException("division by zero");
        }
        if (a == Integer.MIN_VALUE && b == -1) {
            throw new ArithmeticException("division overflow");
        }
        return a / b;
    }

    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        System.out.println("plainIntProduct=" + (a * b));
        System.out.println("lateWidening=" + ((long) (a * b)));
        System.out.println("earlyWidening=" + ((long) a * b));

        expectOverflow("multiplyExactInt",
                () -> Math.multiplyExact(a, b));
        System.out.println("multiplyExactLong=" +
                Math.multiplyExact((long) a, b));
        System.out.println("multiplyFull=" + Math.multiplyFull(a, b));

        expectOverflow("toIntExactAfterWiden",
                () -> Math.toIntExact((long) a * b));
        System.out.println("toIntExactAfterOverflow=" +
                Math.toIntExact((long) (a * b)));

        expectOverflow("addExact",
                () -> Math.addExact(Integer.MAX_VALUE, 1));
        expectOverflow("subtractExact",
                () -> Math.subtractExact(Integer.MIN_VALUE, 1));
        expectOverflow("negateExact",
                () -> Math.negateExact(Integer.MIN_VALUE));
        expectOverflow("incrementExact",
                () -> Math.incrementExact(Integer.MAX_VALUE));
        expectOverflow("decrementExact",
                () -> Math.decrementExact(Integer.MIN_VALUE));
        expectOverflow("absExact",
                () -> Math.absExact(Integer.MIN_VALUE));

        int n = 65_535;
        System.out.println("triangleWrong=" + (n * (n + 1) / 2));
        System.out.println("triangleCorrect=" + ((long) n * (n + 1) / 2));
        expectOverflow("triangleExactIntermediate",
                () -> Math.multiplyExact(n, Math.addExact(n, 1)));
        System.out.println("triangleNextLong=" +
                ((long) (n + 1) * (n + 2) / 2));
        expectOverflow("triangleNextToIntExact",
                () -> Math.toIntExact((long) (n + 1) * (n + 2) / 2));

        int low = 2_000_000_000;
        int high = 2_100_000_000;
        System.out.println("midpointWrong=" + ((low + high) / 2));
        System.out.println("midpointSafe=" +
                (low + (high - low) / 2));

        System.out.println("divideMinByMinusOnePlain=" +
                (Integer.MIN_VALUE / -1));
        expectOverflow("divideMinByMinusOneChecked",
                () -> safeDivide(Integer.MIN_VALUE, -1));
        System.out.println("safeDivideNormal=" + safeDivide(10, 3));

        System.out.println("absMinPlain=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("longOverflowWrap=" + (Long.MAX_VALUE + 1L));
        expectOverflow("longAddExact",
                () -> Math.addExact(Long.MAX_VALUE, 1L));
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 CheckedArithmeticDemo.java
java CheckedArithmeticDemo
```

**Stdout chính xác đã kiểm chứng trên JDK 24 với target Java 17:**

```text
plainIntProduct=-1794967296
lateWidening=-1794967296
earlyWidening=2500000000
multiplyExactInt=OVERFLOW
multiplyExactLong=2500000000
multiplyFull=2500000000
toIntExactAfterWiden=OVERFLOW
toIntExactAfterOverflow=-1794967296
addExact=OVERFLOW
subtractExact=OVERFLOW
negateExact=OVERFLOW
incrementExact=OVERFLOW
decrementExact=OVERFLOW
absExact=OVERFLOW
triangleWrong=-32768
triangleCorrect=2147450880
triangleExactIntermediate=OVERFLOW
triangleNextLong=2147516416
triangleNextToIntExact=OVERFLOW
midpointWrong=-97483648
midpointSafe=2050000000
divideMinByMinusOnePlain=-2147483648
divideMinByMinusOneChecked=OVERFLOW
safeDivideNormal=3
absMinPlain=-2147483648
longOverflowWrap=-9223372036854775808
longAddExact=OVERFLOW
```

Giải thích các phát hiện quan trọng:

1. `50_000 * 50_000` bằng **2.500.000.000** về mặt toán học, nhưng vượt `Integer.MAX_VALUE`. Trong `int`, kết quả quay vòng thành `-1_794_967_296`.
2. `(long)(a*b)` không có cách nào lấy lại `2_500_000_000` vì overflow đã xảy ra.
3. `Math.multiplyExact(a,b)` ném chính xác vì đích là `int`; `Math.multiplyExact((long)a,b)` trả đúng kết quả `long`.
4. `Math.multiplyFull(a,b)` tính đúng long product cho hai `int`.
5. `toIntExactAfterOverflow` không báo lỗi: đây là bằng chứng rằng **chuyển đổi exact quá muộn không sửa được intermediate overflow**.
6. `Integer.MAX_VALUE+1`, `Integer.MIN_VALUE-1`, phủ định/trị tuyệt đối của `MIN_VALUE` và tăng/giảm qua biên đều bị các phương thức tương ứng phát hiện.
7. Công thức tam giác `n*(n+1)/2` có thể **tràn ở tử số ngay cả khi kết quả cuối vẫn vừa int**.
8. Phép tính midpoint bằng `(low+high)/2` bị tràn, trong khi công thức an toàn cho khoảng nonnegative đã cho trả đúng.
9. Chia `MIN_VALUE/-1` bằng toán tử thường quay vòng, vì vậy nếu cần kiểm tra overflow phải xử lý riêng trên Java 17.
10. `Long.MAX_VALUE+1L` cũng quay vòng về `Long.MIN_VALUE`. Dùng `Math.addExact(long,long)` khi cần kết quả chính xác hoặc ngoại lệ.

**Không có cờ compiler `--release 17` nào biến toán tử `+`/`*` thường thành checked arithmetic.** `--release` điều chỉnh language/API/bytecode target; bạn phải chọn **biểu thức hoặc phương thức an toàn**.

## 6. Tràn trung gian ngay cả khi kết quả cuối cùng vừa kiểu

Một lỗi khó phát hiện hơn “giá trị vượt int” là **bước trung gian vượt int, nhưng đáp số cuối cùng không vượt**. Vì đáp số cuối hợp lệ, các kiểm tra chỉ ở cuối có thể bỏ sót vấn đề.

### 6.1. Công thức số tam giác

Với `n = 65_535`:

\[
T(n) = \frac{n(n+1)}{2}
     = \frac{65\,535\times65\,536}{2}
     = 2\,147\,450\,880
\]

Đáp số **2.147.450.880** nằm trong `int`, nhưng tử số `65_535 * 65_536 = 4_294_901_760` lại vượt `Integer.MAX_VALUE`.

```java
int n = 65_535;

int broken = n * (n + 1) / 2; // -32_768: sai
long exact = (long) n * (n + 1) / 2; // 2_147_450_880
int checked = Math.toIntExact(exact); // hợp lệ vì đáp số vừa int
```

**Chú ý:** với `n` là int gần `MAX_VALUE`, cả biểu thức `n + 1` cũng có nguy cơ tràn trước khi dùng. Cách tính cẩn thận là nâng kiểu **trước cả bước cộng**:

```java
static long triangular(long n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be nonnegative");
    }
    long next = Math.addExact(n, 1L);
    long numerator = Math.multiplyExact(n, next);
    return numerator / 2L;
}
```

Tuy nhiên, với `n` kiểu `long` rất lớn, **tử số long có thể tràn dù kết quả chia hai vẫn vừa long**. Khi đó cần **rút gọn trước phép nhân**, với `n` không âm:

```java
static long triangularWithoutIntermediateOverflow(long n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be nonnegative");
    }
    long next = Math.addExact(n, 1L);
    long left = n;
    long right = next;
    if ((left & 1L) == 0L) {
        left /= 2L;
    } else {
        right /= 2L;
    }
    return Math.multiplyExact(left, right);
}
```

Cách này chia một thừa số chẵn cho 2 **trước khi nhân**, rồi dùng `multiplyExact` để kiểm tra kết quả cuối có vừa `long` hay không. Đây là ví dụ về **chọn lại thuật toán để không tạo intermediate quá lớn**, không chỉ nâng sang một kiểu khác.

Đối với `n` cực lớn đến mức `n+1` không nằm trong long, phương thức trên vẫn ném ở `addExact`, dù giá trị toán học của `T(n)` chắc chắn vượt long ở các trường hợp đó. Nếu bài toán cần kết quả hơn 64 bit, chuyển sang `BigInteger`.

### 6.2. Tính trung điểm

`(low + high) / 2` có thể tràn trong phép cộng. Nếu đã biết `0 <= low <= high` và `high - low` vừa int, dùng:

```java
int mid = low + (high - low) / 2;
```

Trong ví dụ `low=2_000_000_000`, `high=2_100_000_000`, đáp án `2_050_000_000`, còn công thức sai trả `-97_483_648`.

**Giới hạn của công thức `low + (high-low)/2`:** nếu các điểm có thể trải từ `Integer.MIN_VALUE` tới `Integer.MAX_VALUE`, `high-low` **cũng** có thể tràn `int`. Với đầu vào int bất kỳ, làm phép cộng ở `long`:

```java
int mid = Math.toIntExact(((long) low + high) / 2L);
```

Đoạn trên có **quy tắc làm tròn về 0** theo phép chia số nguyên Java. Nếu thuật toán yêu cầu floor cho cả số âm, sử dụng `Math.floorDiv((long) low + high, 2L)` rồi `Math.toIntExact`. Đừng tự đổi công thức khi kết quả âm mà chưa định nghĩa chính sách làm tròn.

### 6.3. Các biểu thức nhiều bước phải được kiểm tra từng bước

Giả sử tổng dung lượng là:

\[
\text{bytes} = \text{recordCount} \times \text{recordSize} + \text{headerSize}
\]

Mẫu an toàn:

```java
long payloadBytes = Math.multiplyExact(recordCount, recordSize);
long totalBytes = Math.addExact(payloadBytes, headerSize);
```

Trong snippet, các biến là `long` đã được validate. Nếu cả ba biến là `int` nhưng đáp số có thể vượt int, nâng ít nhất một toán hạng sang `long` **trước phép nhân đầu tiên**. Nếu thiết kế bắt buộc `int`, chỉ gọi `Math.toIntExact(totalBytes)` **sau** khi đã tính đúng tất cả bước.

## 7. Kiểm tra biên và tránh overflow trong điều kiện phạm vi

Lỗi tràn không chỉ xuất hiện trong tính tổng; nó còn tạo **lỗ hổng kiểm tra ranh giới**. Ví dụ logic đọc một đoạn dữ liệu:

```java
// SAI: offset + length có thể overflow thành số âm.
boolean accepted = offset + length <= total;
```

Khi `offset = Integer.MAX_VALUE-5`, `length=10` và `total=100`, phép cộng quay vòng thành số âm, khiến phép so sánh `<=100` thành **true**, mặc dù đoạn yêu cầu nằm rất xa ngoài bộ đệm.

Cách kiểm tra không cần cộng một số có thể tràn:

```java
static boolean validSlice(int offset, int length, int total) {
    return offset >= 0 && length >= 0 && total >= 0
            && offset <= total && length <= total - offset;
}
```

Vì Java dùng **short-circuit `&&`**, biểu thức `total - offset` chỉ được đánh giá **sau khi** đã kiểm tra `offset <= total` và cả hai không âm; do đó kết quả hiệu nằm trong khoảng `[0,total]` và không thể tràn với `int` hợp lệ.

**Đừng đổi máy móc thành `length <= total - offset` mà bỏ guard**: nếu offset âm/lớn hơn total, phép trừ hoặc ngữ nghĩa phạm vi có thể không hợp lệ. Nên validate **từng đại lượng và thứ tự kiểm tra**.

### 7.1. Tính kích thước ma trận/buffer

Mã thường gặp:

```java
int bytes = rows * columns; // Sai nếu tích vượt int.
```

Khi số phần tử dùng làm kích thước mảng Java, cần không âm và vừa miền `int`. Ví dụ:

```java
static int checkedElements(int rows, int columns) {
    if (rows < 0 || columns < 0) {
        throw new IllegalArgumentException("negative dimension");
    }
    long elements = Math.multiplyExact((long) rows, (long) columns);
    return Math.toIntExact(elements);
}
```

Đây là cách kiểm tra **giới hạn biểu diễn**; nó chưa khẳng định JVM thật sự có đủ RAM hoặc có thể tạo mảng gần `Integer.MAX_VALUE` phần tử. Một mảng thực còn có giới hạn triển khai, bộ nhớ, GC và `OutOfMemoryError`.

### 7.2. Tính byte offset

Một layout phổ biến có `row`, `stride` và `column`:

```java
static long checkedOffset(long row, long stride, long column) {
    if (row < 0 || stride < 0 || column < 0 || column >= stride) {
        throw new IllegalArgumentException("invalid coordinates");
    }
    long base = Math.multiplyExact(row, stride);
    return Math.addExact(base, column);
}
```

Kiểm tra tọa độ không âm và `column < stride` **trước** khi nhân/cộng. `Math.multiplyExact` và `Math.addExact` bảo đảm không tràn `long`. Nhưng phương thức không xác minh `row < rowCount` hoặc offset thật sự nằm trong file — ứng dụng phải kiểm tra **tổng số dòng và kích thước file** theo contract của mình.

**Lưu ý:** dữ liệu do client cung cấp phải được kiểm tra thêm theo giới hạn nghiệp vụ, không chỉ giới hạn JVM. Chẳng hạn một yêu cầu cấp 2 tỷ byte có thể vừa int về lý thuyết nhưng vượt quota ứng dụng.

## 8. Chương trình runnable: kiểm tra slice, kích thước và offset

**Tệp `SafeBoundsDemo.java` — Java 17+:**

```java
public class SafeBoundsDemo {
    static boolean validSlice(int offset, int length, int total) {
        return offset >= 0 && length >= 0 && total >= 0
                && offset <= total && length <= total - offset;
    }

    static int checkedElements(int rows, int columns) {
        if (rows < 0 || columns < 0) {
            throw new IllegalArgumentException("negative dimension");
        }
        long elements = Math.multiplyExact((long) rows, (long) columns);
        return Math.toIntExact(elements);
    }

    static long checkedOffset(long row, long stride, long column) {
        if (row < 0 || stride < 0 || column < 0 || column >= stride) {
            throw new IllegalArgumentException("invalid coordinates");
        }
        long base = Math.multiplyExact(row, stride);
        return Math.addExact(base, column);
    }

    public static void main(String[] args) {
        int offset = Integer.MAX_VALUE - 5;
        int length = 10;
        int total = 100;

        System.out.println("naiveRangeResult=" + (offset + length <= total));
        System.out.println("safeRangeResult=" + validSlice(offset, length, total));
        System.out.println("validRangeResult=" + validSlice(20, 5, 100));
        System.out.println("checkedElementCount=" +
                checkedElements(40_000, 50_000));

        try {
            checkedElements(60_000, 40_000);
            System.out.println("oversizeElementCount=MISSED");
        } catch (ArithmeticException ex) {
            System.out.println("oversizeElementCount=OVERFLOW");
        }

        System.out.println("checkedByteOffset=" +
                checkedOffset(4_000_000_000L, 8L, 7L));

        try {
            checkedOffset(Long.MAX_VALUE, 2L, 1L);
            System.out.println("offsetOverflow=MISSED");
        } catch (ArithmeticException ex) {
            System.out.println("offsetOverflow=OVERFLOW");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 SafeBoundsDemo.java
java SafeBoundsDemo
```

**Stdout đã kiểm chứng:**

```text
naiveRangeResult=true
safeRangeResult=false
validRangeResult=true
checkedElementCount=2000000000
oversizeElementCount=OVERFLOW
checkedByteOffset=32000000007
offsetOverflow=OVERFLOW
```

Phân tích:

- `naiveRangeResult=true` là **lỗi kiểm tra** vì `offset + length` đã tràn.
- `safeRangeResult=false` từ chối phạm vi không hợp lệ.
- `validRangeResult=true` cho trường hợp hợp lệ.
- `checkedElements(40_000,50_000)` trả `2_000_000_000`, vẫn vừa int.
- `checkedElements(60_000,40_000)` có tích `2_400_000_000L`: tích long đúng nhưng khi thu hẹp về int thì `toIntExact` ném.
- `checkedOffset(4_000_000_000L,8L,7L)` cho offset `32_000_000_007L`.
- `checkedOffset(Long.MAX_VALUE,2L,1L)` ném tại `multiplyExact` trước khi `addExact` chạy.

**Giới hạn phạm vi bài test:** chương trình không tạo một mảng 2 tỷ phần tử hay ghi file ở offset 32 tỷ. Nó chỉ kiểm tra **cách tính và guard**, không dùng RAM/đĩa khổng lồ để chứng minh.

## 9. Thiết kế test biên có hệ thống, không chỉ chọn một giá trị quá lớn

Một test `Integer.MAX_VALUE + 1` là cần nhưng **không đủ**. Hãy chọn dữ liệu sao cho vừa bao phủ **biên số học**, vừa bao phủ **biên hợp đồng nghiệp vụ**.

### 9.1. Danh sách đầu vào biên gợi ý

**Dành cho `int`:**

```text
Integer.MIN_VALUE
Integer.MIN_VALUE + 1
-65536
-46341
-1
0
1
2
46340
46341
65535
Integer.MAX_VALUE - 1
Integer.MAX_VALUE
```

Lý do các giá trị đặc biệt hữu ích:

- **`MIN`/`MAX` và hàng xóm:** bắt lỗi vượt mép, phủ định và tăng/giảm.
- **`-1`, `0`, `1`:** biên dấu, phần tử trung hòa, phép chia cho 0.
- **`46340` và `46341`:** bình phương `46340^2` còn vừa `int`, `46341^2` vượt giới hạn.
- **`65535` và `65536`:** các giá trị làm lộ overflow trong công thức số tam giác và biểu diễn 16-bit/32-bit.
- **Giá trị âm:** bảo đảm subtraction và signed multiplication được kiểm tra ở cả hai hướng.

**Dành cho `long`:** `Long.MIN_VALUE`, `MIN+1`, `-1`, `0`, `1`, `2`, `MAX-1`, `Long.MAX_VALUE`. Thêm các điểm lân cận biên theo domain, ví dụ giá trị gần một giới hạn byte offset hoặc đơn vị thời gian.

### 9.2. Bảng các phép cần kiểm thử

| Phép toán | Trường hợp hợp lệ sát biên | Trường hợp phải báo overflow |
| --- | --- | --- |
| `addExact(int,int)` | `MAX + 0`, `MIN + 0` | `MAX + 1`, `MIN + (-1)` |
| `subtractExact(int,int)` | `MIN - 0`, `MAX - 0` | `MIN - 1`, `MAX - (-1)` |
| `multiplyExact(int,int)` | `46340 * 46340` | `46341 * 46341`, `MIN * -1` |
| `negateExact(int)` | `-MAX` | `-MIN` |
| `absExact(int)` | `abs(-MAX)` | `abs(MIN)` |
| `incrementExact(int)` | `MAX-1` tăng 1 | `MAX` tăng 1 |
| `decrementExact(int)` | `MIN+1` giảm 1 | `MIN` giảm 1 |
| `toIntExact(long)` | `(long)MAX` | `(long)MAX+1`, `(long)MIN-1` |
| `safeDivide(int,int)` | `MIN / 1`, `10 / -2` | `MIN / -1`, mẫu `0` |
| `validSlice` | `offset=total,length=0` | offset âm, length âm, offset lớn hoặc phép cộng giả tràn |
| `checkedElements` | tích vừa int | tích lớn hơn int, kích thước âm |

Đối với `multiplyExact`, kết quả phải kiểm tra cả dấu: `(-46341)*46341` nằm dưới `Integer.MIN_VALUE`, còn `(-46340)*46340` nằm trong miền nếu không vượt giá trị âm. Với `long`, thêm `Long.MAX_VALUE*2` và `Long.MIN_VALUE*(-1)`.

### 9.3. Off-by-one là một phần quan trọng của kiểm thử biên

Giới hạn `n <= max` thường hỏng ở đúng `max+1`. Vì vậy hãy viết ít nhất các test:

- `max-1`, `max`, `max+1` nếu kiểu đủ chứa.
- `min-1`, `min`, `min+1` nếu có thể biểu diễn đầu vào ở kiểu rộng hơn.
- `length=0`, `length=1`, `length=remaining`, `length=remaining+1` trong slice.
- `row=0`, `row=height-1`, `row=height` cho row index.
- `column=0`, `column=stride-1`, `column=stride`.
- `n=65535`, `n=65536` cho công thức có nhân/trừ.

Nếu `max` đã là `Integer.MAX_VALUE`, **không viết `max + 1` bằng `int` để tạo input biên** vì bạn sẽ overflow **ngay trong test fixture**. Hãy tạo giá trị ở `long`: `((long) Integer.MAX_VALUE) + 1L`.

### 9.4. Test fixture không được tràn

Sai:

```java
long expected = 50_000 * 50_000; // expected đã sai!
```

Đúng:

```java
long expected = 50_000L * 50_000;
```

Tốt hơn nữa, dùng oracle `BigInteger.valueOf(50_000).multiply(...)` được tạo từ **các toán hạng gốc**, không tạo `BigInteger.valueOf(a*b)` từ kết quả đã tràn.

## 10. Oracle độc lập bằng `BigInteger` và property-style test

So sánh `Math.*Exact` với chính một biểu thức `int` tương tự là **kiểm tra sai bằng hai cách cùng lỗi**. Hãy dùng `BigInteger` làm **reference oracle**, vì phép cộng/trừ/nhân của nó không bị giới hạn ở 32/64 bit (dù tài nguyên máy vẫn hữu hạn).

Quy tắc kiểm thử:

1. Tạo toán hạng `x` và `y` kiểu `int`.
2. Tính kết quả toán học bằng `BigInteger.valueOf(x)` và `BigInteger.valueOf(y)`.
3. Nếu oracle nằm trong đoạn `[Integer.MIN_VALUE, Integer.MAX_VALUE]`, phương thức exact phải trả **đúng giá trị**.
4. Nếu oracle nằm ngoài đoạn đó, phương thức exact phải ném **`ArithmeticException`**.
5. Không so nội dung chuỗi exception message: đó không phải hợp đồng thông báo lỗi để dựa vào.
6. Lặp lại với `long` và giới hạn `Long.MIN_VALUE/Long.MAX_VALUE`.
7. Kết hợp **edge matrix** có chủ đích và **random có seed**. Random test không thay thế corner cases đã biết.

### 10.1. Chương trình kiểm thử đầy đủ, không cần JUnit

**Tệp `CheckedArithmeticTableTest.java` — Java 17+:**

```java
import java.math.BigInteger;
import java.util.Random;
import java.util.function.IntBinaryOperator;
import java.util.function.LongBinaryOperator;

public class CheckedArithmeticTableTest {
    static final BigInteger INT_MIN = BigInteger.valueOf(Integer.MIN_VALUE);
    static final BigInteger INT_MAX = BigInteger.valueOf(Integer.MAX_VALUE);
    static final BigInteger LONG_MIN = BigInteger.valueOf(Long.MIN_VALUE);
    static final BigInteger LONG_MAX = BigInteger.valueOf(Long.MAX_VALUE);
    static int intCases;
    static int longCases;

    static void checkInt(int x, int y, String name) {
        BigInteger a = BigInteger.valueOf(x);
        BigInteger b = BigInteger.valueOf(y);
        BigInteger oracle;
        IntBinaryOperator checked;
        switch (name) {
            case "add" -> {
                oracle = a.add(b);
                checked = Math::addExact;
            }
            case "subtract" -> {
                oracle = a.subtract(b);
                checked = Math::subtractExact;
            }
            case "multiply" -> {
                oracle = a.multiply(b);
                checked = Math::multiplyExact;
            }
            default -> throw new AssertionError("unknown operation");
        }

        boolean fits = oracle.compareTo(INT_MIN) >= 0
                && oracle.compareTo(INT_MAX) <= 0;
        try {
            int actual = checked.applyAsInt(x, y);
            if (!fits || actual != oracle.intValueExact()) {
                throw new AssertionError(name + " " + x + ", " + y);
            }
        } catch (ArithmeticException ex) {
            if (fits) {
                throw new AssertionError("unexpected overflow: " + name, ex);
            }
        }
        intCases++;
    }

    static void checkLong(long x, long y, String name) {
        BigInteger a = BigInteger.valueOf(x);
        BigInteger b = BigInteger.valueOf(y);
        BigInteger oracle;
        LongBinaryOperator checked;
        switch (name) {
            case "add" -> {
                oracle = a.add(b);
                checked = Math::addExact;
            }
            case "subtract" -> {
                oracle = a.subtract(b);
                checked = Math::subtractExact;
            }
            case "multiply" -> {
                oracle = a.multiply(b);
                checked = Math::multiplyExact;
            }
            default -> throw new AssertionError("unknown operation");
        }

        boolean fits = oracle.compareTo(LONG_MIN) >= 0
                && oracle.compareTo(LONG_MAX) <= 0;
        try {
            long actual = checked.applyAsLong(x, y);
            if (!fits || actual != oracle.longValueExact()) {
                throw new AssertionError(name + " " + x + ", " + y);
            }
        } catch (ArithmeticException ex) {
            if (fits) {
                throw new AssertionError("unexpected overflow: " + name, ex);
            }
        }
        longCases++;
    }

    public static void main(String[] args) {
        int[] boundaries = {
                Integer.MIN_VALUE, Integer.MIN_VALUE + 1, -65_536,
                -46_341, -1, 0, 1, 2, 46_340, 46_341, 65_535,
                Integer.MAX_VALUE - 1, Integer.MAX_VALUE
        };

        for (int x : boundaries) {
            for (int y : boundaries) {
                checkInt(x, y, "add");
                checkInt(x, y, "subtract");
                checkInt(x, y, "multiply");
            }
        }

        Random random = new Random(20261107L);
        for (int i = 0; i < 3_000; i++) {
            int x = random.nextInt();
            int y = random.nextInt();
            checkInt(x, y, "add");
            checkInt(x, y, "subtract");
            checkInt(x, y, "multiply");
        }

        long[] longBoundaries = {
                Long.MIN_VALUE, Long.MIN_VALUE + 1, -1L, 0L, 1L, 2L,
                Long.MAX_VALUE - 1, Long.MAX_VALUE
        };
        for (long x : longBoundaries) {
            for (long y : longBoundaries) {
                checkLong(x, y, "add");
                checkLong(x, y, "subtract");
                checkLong(x, y, "multiply");
            }
        }

        System.out.println("checkedIntCases=" + intCases);
        System.out.println("checkedLongCases=" + longCases);
        System.out.println("allMatchedBigInteger=true");
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 CheckedArithmeticTableTest.java
java CheckedArithmeticTableTest
```

**Stdout đã kiểm chứng chính xác:**

```text
checkedIntCases=9507
checkedLongCases=192
allMatchedBigInteger=true
```

Giải thích số lượng:

- 13 giá trị biên cho `int` → `13 × 13 × 3 = 507` trường hợp với ba phép toán.
- 3.000 cặp `int` ngẫu nhiên có seed cố định → `3.000 × 3 = 9.000` trường hợp.
- Tổng `507 + 9.000 = 9.507`.
- Tám giá trị biên `long` → `8 × 8 × 3 = 192`.
- Không một trường hợp nào bị kết luận sai so với oracle `BigInteger`.

**Điều bộ kiểm thử thật sự chứng minh:** trong những giá trị đã chọn, phép exact trả kết quả đúng khi còn trong miền và ném ngoại lệ khi vượt miền. Nó **không** chứng minh rằng công thức nghiệp vụ phức tạp của bạn không bị tràn ở bước khác, vì bài test chỉ kiểm tra các lời gọi exact riêng lẻ. Bài test nghiệp vụ vẫn phải đi qua **toàn bộ pipeline tính toán thật**, không chỉ gọi thư viện `Math`.

### 10.2. Property-based test và metamorphic properties

Nếu dùng JUnit 5 (Jupiter) hoặc một công cụ property-based testing hiện đại, bạn có thể chuyển cùng oracle thành parameterized tests/randomized tests; không cần sửa logic toán học. Những thuộc tính nên kiểm tra:

- Nếu oracle vừa miền, `Math.addExact(x,y)` = oracle; nếu không vừa, phải có `ArithmeticException`.
- `Math.addExact(x,0) == x` với mọi giá trị `x`.
- `Math.multiplyExact(x,1) == x`; `multiplyExact(x,0) == 0`.
- `Math.negateExact(Math.negateExact(x)) == x` **nếu `x != MIN_VALUE`**.
- `Math.toIntExact((long)x) == x` cho mọi `int x`.
- Phép tính index phải từ chối `row<0`, `col<0` hoặc vượt kích thước, không chỉ trả một `int` hợp lệ sau overflow.
- Với `validSlice`, kết quả true phải kéo theo `offset>=0`, `length>=0` và `offset+length <= total` **khi tính tổng bằng `long` để tránh overflow ngay trong phép kiểm tra**.

**Đừng viết property test chứa phép toán có cùng lỗi với mã production.** Ví dụ assertion `actual == (int)(a*b)` không phải reference phù hợp khi oracle cần phát hiện tràn.

### 10.3. Determinism và tái lập lỗi

`Random(20261107L)` cho cùng chuỗi số giả ngẫu nhiên ở cùng thuật toán Java trong bài. Khi một case thất bại:

- Ghi `seed`, hai toán hạng, operation, giá trị oracle và exception thực.
- Thu nhỏ dữ liệu về giá trị biên đơn giản hơn.
- Thêm cặp đó thành **regression test cố định**.
- Giữ test không phụ thuộc thứ tự luồng hoặc dữ liệu network.
- Với phép toán nhiều bước, log đầu vào và xác định **bước đầu tiên** sai hoặc overflow.

Không dùng `Random` làm nguồn dữ liệu bảo mật; nó ở đây chỉ phục vụ test tái lập.

## 11. Áp dụng cho mã ứng dụng thật

### 11.1. Kích thước mảng, network packet và độ dài file

Khi tính `headerBytes + itemCount * itemBytes`, hãy validate `itemCount` không âm, `itemBytes` dương, tổng không vượt quota và dùng `Math.multiplyExact`/`Math.addExact` ở kiểu `long`. Sau khi có tổng đúng mới `toIntExact` nếu API buộc `int`.

Nếu có yêu cầu như “không được vượt 16 MiB”, hãy kiểm tra **giới hạn nghiệp vụ 16 MiB** thay vì chỉ kiểm tra `Integer.MAX_VALUE`. Giá trị có thể đúng về số học nhưng vẫn nguy hiểm về bộ nhớ tài nguyên.

### 11.2. Tính offset/index

Không dùng `row * width + col` trong `int` khi `row` và `width` lớn. Nếu index thật sự cần nằm trong `int`:

```java
long offset = Math.addExact(
        Math.multiplyExact((long) row, width), col);
int index = Math.toIntExact(offset);
```

Sau đó còn phải kiểm tra `0 <= row < height` và `0 <= col < width` **theo đúng contract**, và bảo đảm mảng/buffer thực sự dài hơn `index`. Exact arithmetic chỉ bảo vệ **kết quả số học**, không thay thế bounds của object đang truy cập.

### 11.3. Tiền, đơn giá và số lượng

Nếu lưu tiền bằng **số cent nguyên**, `unitPriceCents * count` phải kiểm tra đúng đơn vị và tràn. Một nguồn tràn gây hậu quả tài chính:

```java
long totalCents = Math.multiplyExact(unitPriceCents, quantity);
```

Đây là **snippet** với hai biến `long` có dữ liệu đã validate. Nếu cần phần lẻ cent hoặc phép tính số thập phân theo quy tắc nghiệp vụ, dùng `BigDecimal` và một **rounding policy** rõ ràng; không dùng `double` rồi coi `Math.multiplyExact` là giải pháp.

### 11.4. Số lượng bộ đếm và thời gian

`counter++` và `counter += delta` không tự kiểm tra overflow. Với bộ đếm cần không vượt miền:

```java
counter = Math.incrementExact(counter);
counter = Math.addExact(counter, delta);
```

Khi nhiều thread cùng cập nhật, các thao tác vừa nêu **không tự tạo atomicity** cho biến chia sẻ; cần concurrency control thích hợp. Ngay cả một atomic counter `AtomicInteger.incrementAndGet` là atomic về đồng thời, nhưng **không tự bảo đảm checked arithmetic overflow** cho contract số học.

Với duration/timestamp, không lấy phép trừ `endNanos - startNanos` là luôn an toàn cho mọi range; cần hiểu nguồn clock, phạm vi giá trị, rollover semantics và contract đo thời gian. Đừng lấy thời gian hệ thống tuyệt đối làm số nanosecond `long` khi có thể vượt miền.

### 11.5. Xử lý ngoại lệ ở đâu?

`ArithmeticException` là **tín hiệu phép tính không biểu diễn được**, không tự định nghĩa HTTP status. Nếu dữ liệu đầu vào sai giới hạn được biết trước, validate và trả lỗi nghiệp vụ có ý nghĩa. Nếu overflow xảy ra ở invariant nội bộ (ví dụ tổng byte tính sai trong backend), đó có thể là **bug cần theo dõi**. Không catch một cách chung chung rồi âm thầm đổi overflow thành 0/giá trị âm.

Một đoạn xử lý hợp lý:

```java
try {
    long bytes = Math.multiplyExact(recordCount, recordSize);
    // Chỉ dùng bytes nếu phép tính hoàn tất không tràn.
} catch (ArithmeticException ex) {
    // Tùy contract: từ chối input hoặc báo lỗi tính toán.
    // Không dùng giá trị đã tràn để cấp phát hay chọn offset.
}
```

Đây là **snippet**, cần có biến đầu vào và phương thức xử lý lỗi phù hợp. Bắt `ArithmeticException` không thay thế việc validate input và quota, và không nên nuốt lỗi khiến code tiếp tục với dữ liệu không đáng tin.

## 12. Các lỗi thường gặp và cách sửa

### Lỗi 1 — Tràn trước `Math.toIntExact`

Sai: `Math.toIntExact(a*b)` khi cả hai là `int`. Đúng: `Math.toIntExact((long)a*b)` nếu tích có thể vượt int nhưng vừa long.

### Lỗi 2 — Cast sau phép nhân

Sai: `(long)(a*b)`. Đúng: `(long)a*b` hoặc `Math.multiplyExact((long)a,b)`.

### Lỗi 3 — Đặt `1L` ở cuối chuỗi nhân

Sai: `a*b*1L` vì `a*b` có thể tràn trước. Đúng: `1L*a*b` khi tích chắc chắn vừa long; nếu không chắc, dùng exact ở long.

### Lỗi 4 — Chỉ kiểm tra phép cuối cùng trong công thức

Sai: `Math.addExact(a*b,header)`. Đúng: `Math.addExact(Math.multiplyExact(a,b),header)` nếu tất cả là int, hoặc dùng long ngay từ đầu rồi kiểm tra.

### Lỗi 5 — Số tam giác có kết quả cuối vừa int nên tin trung gian cũng vừa

Sai: `n*(n+1)/2` với `n=65535`. Đúng: nâng kiểu trước khi tính hoặc chia một thừa số chẵn cho hai trước khi nhân.

### Lỗi 6 — Dùng `(low+high)/2` trên gần MAX

Sai: tổng có thể tràn. Đúng: công thức midpoint phù hợp với miền, hoặc cộng ở long trước.

### Lỗi 7 — Dùng `offset+length<=total` làm guard duy nhất

Sai: cộng có thể overflow thành âm. Đúng: validate không âm, `offset<=total` và `length<=total-offset`.

### Lỗi 8 — Quên MIN_VALUE âm

`Math.abs(MIN_VALUE)` hoặc `-MIN_VALUE` không cho số dương mong đợi. Dùng `Math.absExact`/`Math.negateExact` khi contract yêu cầu overflow detection.

### Lỗi 9 — Tin `x / -1` luôn an toàn

`MIN_VALUE / -1` overflow dù mẫu khác 0. Java 17 cần guard riêng; Java 18+ có `Math.divideExact`.

### Lỗi 10 — Dùng `BigInteger.valueOf(a*b)` làm oracle

Sai: BigInteger chỉ nhận kết quả đã wrap. Đúng: `BigInteger.valueOf(a).multiply(BigInteger.valueOf(b))`.

### Lỗi 11 — Chọn các case ngẫu nhiên nhưng bỏ MAX/MIN

Random có thể không bao giờ trúng `MIN*-1` hoặc `MAX+1`. Đúng: test có ma trận biên **cố định**, rồi thêm random.

### Lỗi 12 — Trong test tự tạo `Integer.MAX_VALUE + 1` bằng int

Input test đã wrap ngay trước lời gọi. Đúng: tạo bằng `(long) Integer.MAX_VALUE + 1L` hoặc `BigInteger`.

### Lỗi 13 — `int` vừa nhưng quota ứng dụng không vừa

`2_000_000_000` là int hợp lệ nhưng mảng lớn như vậy có thể không cấp được và vượt quota. Đúng: validate cả business limits, RAM/size policy và bounds thực.

### Lỗi 14 — Nghĩ `Math.multiplyFull` phát hiện overflow int bằng ngoại lệ

Không. Nó trả tích `long` của hai `int`. Nếu thật sự cần int, gọi `Math.toIntExact(Math.multiplyFull(a,b))`.

### Lỗi 15 — Dùng `Math.pow` với double rồi cast để tính tổng integer

`Math.pow` trả `double`, có nguy cơ mất độ chính xác và chuyển kiểu không phải checked integer arithmetic. Đúng: dùng toán học số nguyên `BigInteger` hoặc thuật toán kiểm tra phù hợp.

### Lỗi 16 — Sử dụng `++`/`+=` trong chỉ số hoặc bộ đếm nhạy cảm

Các toán tử không tự ném overflow; `+=` có thể kèm chuyển đổi kiểu hẹp. Đúng: dùng exact methods và validate output trước khi lưu.

### Lỗi 17 — Cho rằng `Math.*Exact` tự validate domain hoặc độ dài buffer

Các phương thức chỉ kiểm tra miền số học. Đúng: kết hợp range/domain validation với exact arithmetic.

### Lỗi 18 — Thử kết quả mong muốn bằng chính phép toán bị nghi ngờ

Sai: `assertEquals(a*b, actual)` khi `a*b` có thể tràn. Đúng: oracle `BigInteger`, hoặc giá trị `long` được tính đúng từ toán hạng gốc.

### Lỗi 19 — Dùng exception message làm hợp đồng

Không cần so thông điệp `"integer overflow"` hay `"long overflow"`. Đúng: test loại `ArithmeticException` và ngữ nghĩa thành công/thất bại.

### Lỗi 20 — Chạy test vài dòng rồi tuyên bố mọi công thức đều an toàn

Test của `Math` không chứng minh code khác không gây intermediate overflow. Đúng: kiểm thử **toàn bộ công thức nghiệp vụ**, các điểm cast, các biểu thức trước lời gọi và các bước sử dụng kết quả.

## 13. Checklist review và QA trước khi release

- [ ] Xác định kiểu và miền toán học cần thiết cho mọi biến trung gian.
- [ ] Không có phép nhân/cộng `int` dễ tràn trước khi truyền vào `Math.*Exact`.
- [ ] Cast hoặc `1L` được đặt **trước** phép có nguy cơ tràn, không ở cuối biểu thức.
- [ ] Nếu cần kiểm tra `long`, dùng `Math.multiplyExact`/`addExact` với kiểu `long` tương ứng.
- [ ] Nếu cần `int`, gọi `Math.toIntExact` **sau** khi kết quả được tính đúng.
- [ ] Test `Integer.MIN_VALUE`, `MAX_VALUE`, `Long.MIN_VALUE`, `MAX_VALUE` và các hàng xóm.
- [ ] Test các phép toán với `-1`, `0`, `1`, `2` và thay đổi dấu.
- [ ] Test các bình phương ngay dưới/vượt biên, ví dụ `46340`/`46341`.
- [ ] Test công thức nhiều bước có **intermediate overflow** dù final result vừa kiểu.
- [ ] Test `MIN_VALUE / -1`, phủ định và trị tuyệt đối.
- [ ] Không có `(a+b)/2` dễ overflow khi chỉ số gần MAX.
- [ ] Guard `offset/length` không dùng cộng dễ overflow trước khi so sánh.
- [ ] Validate số lượng, kích thước, quota, chỉ số và quyền truy cập riêng với overflow check.
- [ ] Có oracle độc lập `BigInteger` được tính từ các toán hạng gốc.
- [ ] Kết hợp edge-case matrix, tests xác định và random/property test có seed.
- [ ] Test kiểm tra cả **giá trị đúng** khi trong miền và **exception đúng** khi ngoài miền.
- [ ] Nếu tính nhiều bước, test đi qua code path thực, không chỉ test `Math` riêng lẻ.
- [ ] Test không tính expected bằng một phép toán int/long có nguy cơ tràn.
- [ ] Nếu dùng Java 17 target, không gọi API mới hơn Java 17 trong mã runnable.
- [ ] Giám sát lỗi và không dùng dữ liệu sai để cấp phát, thanh toán hoặc tính offset.

## 14. Bài tập thực hành

1. Cho `a=50_000`, `b=50_000`. Dự đoán kết quả của `a*b`, `(long)(a*b)` và `(long)a*b`; giải thích nơi overflow diễn ra.
2. So sánh `Math.toIntExact(a*b)` và `Math.toIntExact((long)a*b)`. Vì sao một cách **không ném** còn cách kia ném?
3. Viết `Math.multiplyExact(int,int)` và `Math.multiplyExact(long,long)` cho cùng hai toán hạng. Khi nào chúng có kết quả khác nhau?
4. Kiểm thử `Math.addExact(MAX,0)`, `Math.addExact(MAX,1)`, `Math.subtractExact(MIN,1)`.
5. So sánh `Math.multiplyExact(46340,46340)` với `Math.multiplyExact(46341,46341)`.
6. Tạo case `Math.negateExact(Integer.MIN_VALUE)` và `Math.absExact(Integer.MIN_VALUE)`, đối chiếu với toán tử `-` và `Math.abs` thường.
7. Vì sao `Integer.MIN_VALUE/-1` cần guard thêm ở Java 17?
8. Với `n=65_535`, tính toán đúng tổng `n(n+1)/2` và chứng minh kết quả cuối vừa int nhưng tử số vượt int.
9. Viết lại công thức `triangular(n)` để chia một thừa số chẵn cho 2 **trước khi multiplyExact`.
10. Với `low=2_000_000_000` và `high=2_100_000_000`, so sánh midpoint sai và đúng; sau đó thử khoảng `[Integer.MIN_VALUE,Integer.MAX_VALUE]`.
11. Viết một `validSlice` từ chối `offset=Integer.MAX_VALUE-5,length=10,total=100`.
12. Viết phép tính số phần tử `rows*columns` bằng `long`, sau đó thu hẹp về int có kiểm tra.
13. Viết `checkedOffset(row,stride,column)` với validation và mọi bước có thể tràn đều dùng `Math.*Exact`.
14. Xây oracle bằng `BigInteger` cho một cặp `int` tràn và một cặp không tràn; so cả giá trị/exception.
15. Dùng bảng `Integer.MIN/MAX`, `-1`, `0`, `1`, `46340`/`46341` và cặp ngẫu nhiên có seed để thiết kế test.
16. Viết test thất bại khi code nghiệp vụ sử dụng `Math.toIntExact((long)(a*b))` thay vì `Math.toIntExact((long)a*b)`.
17. Kiểm thử logic business quota cho tổng byte có giá trị trong int nhưng vượt giới hạn 16 MiB.
18. Tạo một trường hợp tràn ở `Long.MAX_VALUE+1L` và so với `Math.addExact(Long.MAX_VALUE,1L)`.
19. Phân biệt `Math.multiplyFull(int,int)` và `Math.multiplyExact(int,int)`.
20. Nếu chuyển sang `BigInteger` để tránh overflow, xác định lúc nào mới được gọi `intValueExact` hoặc `longValueExact`.

**Đáp án định hướng:** (1–2) int overflow xảy ra trước cast/method; (3) khác miền kết quả; (4–6) các biên phải được kiểm tra; (7) `MIN/-1` wraparound; (8) `2_147_450_880` là đáp số, tử số không vừa int; (9) chia trước nhân; (10) cộng bằng long khi miền rộng; (11) guard theo phép trừ đã kiểm tra; (12) `Math.toIntExact` sau phép nhân long đúng; (13) dùng `multiplyExact` rồi `addExact`; (14–15) oracle và ma trận; (16) test phải phát hiện vị trí cast sai; (17) quota khác giới hạn kiểu; (18) long cũng tràn; (19) một hàm mở rộng kết quả, một hàm phát hiện overflow ở int; (20) kiểm tra khi phải trả kiểu hữu hạn.

## 15. Tài liệu chính thức và vẫn áp dụng

- **Oracle Java SE 17 `Math` API:** `addExact`, `subtractExact`, `multiplyExact`, `multiplyFull`, `toIntExact`, `absExact` và các phương thức kiểm tra overflow còn sử dụng: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
- **Oracle Java SE 25 `Math` API:** cùng các phương thức trong JDK hiện đại; `divideExact`/`floorDivExact` chỉ xuất hiện từ Java 18: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html
- **Java Language Specification SE 25, `5.6 — Numeric Contexts:** promotion của toán hạng quyết định kiểu phép tính: https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.6
- **Java Language Specification SE 25, `15.17 — Multiplicative Operators:** số học nguyên, overflow và phép chia đặc biệt: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.17
- **Java Language Specification SE 25, `15.18.2 — Additive Operators:** kết quả khi cộng/trừ bị tràn: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.18.2
- **Java Language Specification SE 25, `15.12.4.2 — Evaluate Arguments:** đối số được tính trước khi lời gọi phương thức thực sự thực hiện: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.2
- **Oracle Java SE 17 `BigInteger` API:** số nguyên độ chính xác tùy ý, `intValueExact()` và `longValueExact()` làm oracle/thu hẹp an toàn: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html
- **SEI CERT Java Coding Standard — Numeric Types and Operations:** nguyên tắc kiểm soát promotion, overflow và validation đầu vào: https://wiki.sei.cmu.edu/confluence/display/java/Numeric+Types+and+Operations

**Ghi nhớ:** Không chỉ chọn phương thức có chữ `Exact`, mà còn phải **tránh mọi phép tính không kiểm tra xảy ra trước khi hàm nhận đối số**. Nếu có nguy cơ vượt `int`, nâng kiểu **trước phép toán** hoặc dùng `Math.multiplyFull`/`Math.*Exact` theo đúng overload. Nếu `long` cũng không đủ, tính bằng `BigInteger` từ **toán hạng gốc**. Kiểm thử biên phải bao phủ `MIN/MAX`, phép trung gian, công thức nhiều bước, chỉ số/length và các ngoại lệ; oracle độc lập là cách phát hiện lỗi mà một phép tính expected cũng có thể mắc phải.