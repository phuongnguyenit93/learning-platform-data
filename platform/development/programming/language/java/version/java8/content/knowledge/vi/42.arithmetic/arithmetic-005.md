# Math.addExact, Math.subtractExact và Math.multiplyExact trong Java 8+

> **Chủ đề cha:** Số học. Ba phương thức `Math.addExact`, `Math.subtractExact` và `Math.multiplyExact` giúp phát hiện **tràn số nguyên** khi cộng, trừ, nhân trong miền `int` hoặc `long`. Nếu kết quả toán học còn biểu diễn được, phương thức trả giá trị chính xác; nếu không, nó ném `ArithmeticException` thay vì cuộn vòng (*wrap-around*) như toán tử số nguyên thông thường. Đây là các API có từ Java 8, vẫn còn được hỗ trợ trên JDK hiện đại.

## 1. Mục tiêu

Sau bài học, bạn có thể: nhận ra overflow/underflow của số nguyên có dấu; đọc đúng sáu chữ ký `int/long` của bộ ba method; biết cách kiểm tra phép nhân, phép cộng và phép trừ cả ở biên âm/dương; widen toán hạng **trước khi tính**, không cast sau overflow; kết hợp `Math.toIntExact` khi narrowing; xử lý ngoại lệ và validation của nghiệp vụ độc lập; dùng `BigInteger`/`BigDecimal` khi phạm vi hoặc biểu diễn số nguyên không đáp ứng; và hiểu vì sao checked arithmetic không tự bảo đảm transaction/atomic update khi nhiều thread chạy.

## 2. Vì sao tràn số nguy hiểm?

`int` là số nguyên có dấu 32-bit, từ `-2_147_483_648` đến `2_147_483_647`. `long` là số nguyên có dấu 64-bit, từ `-9_223_372_036_854_775_808L` đến `9_223_372_036_854_775_807L`. Kiểu số nguyên Java dùng biểu diễn two's complement, và phép `+`/`-`/`*` mặc định **không báo lỗi** nếu kết quả vượt miền.

```java
int positiveOverflow = Integer.MAX_VALUE + 1;
// -2147483648, thay vì 2147483648.

int negativeOverflow = Integer.MIN_VALUE - 1;
// 2147483647, thay vì -2147483649.

int productOverflow = 50_000 * 50_000;
// -1794967296, thay vì 2500000000.
```

Lỗi kiểu này có thể khiến tổng tiền thành âm, số lượng kho bị sai, offset file hoặc kích thước buffer tính sai, hoặc phép kiểm tra quota bị vượt qua. Không thể dựa vào kết quả “vẫn có kiểu int” để khẳng định dữ liệu hợp lệ.

**Hai phía đều quan trọng:** `Integer.MAX_VALUE+1` vượt phía dương; `Integer.MIN_VALUE-1` vượt phía âm (*underflow* theo cách gọi phổ biến). `Integer.MIN_VALUE * -1` cũng không vừa int vì trị dương 2.147.483.648 nằm ngoài miền.

## 3. API chuẩn từ Java 8

| Hàm | Overload int | Overload long | Khi tràn |
| --- | --- | --- | --- |
| `addExact` | `int addExact(int x,int y)` | `long addExact(long x,long y)` | `ArithmeticException` |
| `subtractExact` | `int subtractExact(int x,int y)` | `long subtractExact(long x,long y)` | `ArithmeticException` |
| `multiplyExact` | `int multiplyExact(int x,int y)` | `long multiplyExact(long x,long y)` | `ArithmeticException` |

Tất cả là static method của `java.lang.Math`, không cần tạo object/import riêng. Chúng không trả null, không tự động nâng `int` lên `long` khi int overflow, không bão hòa về `MAX_VALUE`, không tính trên `float/double`.

**Lưu ý phiên bản:** Java 9 bổ sung overload `multiplyExact(long,int)`. Để code chạy được trên **Java 8**, ví dụ trong bài dùng `multiplyExact(int,int)` hoặc `multiplyExact(long,long)`.

## 4. `Math.addExact`: cộng có kiểm tra

```java
int sum = Math.addExact(2_000_000_000, 100_000_000);
// 2100000000, vẫn vừa int.

long bigSum = Math.addExact(9_000_000_000L, 10_000L);
// 9000010000, vẫn vừa long.
```

Nếu phép tính vượt max/min:

```java
try {
    int failed = Math.addExact(Integer.MAX_VALUE, 1);
} catch (ArithmeticException ex) {
    System.out.println("integer overflow");
}
```

`Math.addExact(Integer.MIN_VALUE,-1)` cũng ném exception vì kết quả nhỏ hơn min. Không chỉ kiểm tra overflow dương: số âm cộng số âm có thể tràn về dương.

Khi tính một tổng qua nhiều bước, kiểm tra từng bước:

```java
int total = 0;
for (int item : values) {
    total = Math.addExact(total, item);
}
```

Đây là snippet giả định `values` là `int[]`. Có trường hợp **tổng cuối vẫn vừa int nhưng tổng trung gian không vừa**, ví dụ `MAX_VALUE,1,-1`: bước `MAX_VALUE+1` gây overflow dù tổng toán học cuối là MAX_VALUE. Nếu phải tính tổng cuối cùng độc lập thứ tự nhóm, dùng `long` nếu đủ, hoặc `BigInteger` nếu cần miền không giới hạn, rồi kiểm tra khả năng chuyển về kiểu đích.

## 5. `Math.subtractExact`: trừ có kiểm tra

```java
int remaining = Math.subtractExact(125, 35);
// 90.

int signed = Math.subtractExact(-2_000_000_000, 100_000_000);
// -2100000000.
```

`subtractExact(x,y)` nghĩa là `x-y`; **không hoán đổi** được thứ tự. Các ca lỗi:

```java
Math.subtractExact(Integer.MIN_VALUE, 1);    // Throws.
Math.subtractExact(Integer.MAX_VALUE, -1);   // Throws.
Math.subtractExact(Long.MIN_VALUE, 1L);       // Throws.
```

**Phân biệt overflow với lỗi nghiệp vụ:** `Math.subtractExact(10L,12L)` trả -2, hoàn toàn hợp lệ trong long; nhưng một tồn kho âm có thể bị cấm. Kiểm tra domain riêng:

```java
if (available < 0 || requested < 0 || requested > available) {
    throw new IllegalArgumentException("invalid stock request");
}
long left = Math.subtractExact(available, requested);
```

Snippet giả định `available/requested` là biến long. Đừng thay `x-y` bằng `x+(-y)` khi `y` có thể là `Integer.MIN_VALUE`: phép đổi dấu `-MIN_VALUE` tự nó có thể tràn. Dùng `subtractExact` trực tiếp, hoặc `Math.negateExact` khi thật sự cần đổi dấu.

## 6. `Math.multiplyExact`: nhân có kiểm tra

```java
int valid = Math.multiplyExact(30_000, 40_000);
// 1200000000.

long validLong = Math.multiplyExact(3_000_000_000L, 2L);
// 6000000000.
```

```java
Math.multiplyExact(50_000, 50_000);
// Throws ArithmeticException: tích toán học là 2500000000.

Math.multiplyExact(Long.MAX_VALUE, 2L);
// Throws: tích vượt long.
```

Tích của hai số âm cũng có thể tràn phía dương; `Integer.MIN_VALUE * -1` là ca biên rất dễ bỏ sót. Khi nhân với 0, kết quả luôn vừa trong int/long. Phép nhân Exact kiểm tra phạm vi **của overload** đang dùng.

### 6.1. Widen trước khi tính, không cast sau

```java
int units = 50_000;
int price = 50_000;

long wrong = (long) (units * price);
// -1794967296: int nhân tràn trước khi cast.

long right = (long) units * price;
// 2500000000, phép nhân đã diễn ra trong long.

long checked = Math.multiplyExact((long) units, (long) price);
// 2500000000 và phát hiện tràn nếu vượt long.
```

`long result = Math.multiplyExact(units,price)` với hai đối số int **vẫn chọn overload int**, dù biến nhận là long. Kiểu của **đối số tại lời gọi** quyết định overload, không phải kiểu của biến được gán.

### 6.2. Long không vô hạn

`Math.multiplyExact(long,long)` cũng ném `ArithmeticException` nếu tích vượt 64-bit. Trong bài toán cần số nguyên lớn hơn long, dùng `BigInteger.multiply` hoặc thay đổi thuật toán để kiểm soát giới hạn, thay vì chỉ widen từ int sang long rồi cho rằng không thể overflow.

## 7. Bảng kiểu và overload

| Cách gọi | Miền kiểm tra | Kết quả |
| --- | --- | --- |
| `Math.addExact(100,20)` | int | 120 kiểu int |
| `Math.addExact(100L,20L)` | long | 120L |
| `Math.multiplyExact(50000,50000)` | int | Throws |
| `Math.multiplyExact(50000L,50000L)` | long | 2500000000L |
| `long x=Math.addExact(Integer.MAX_VALUE,1)` | int | Throws trước khi gán |
| `long x=Math.addExact((long)Integer.MAX_VALUE,1L)` | long | 2147483648L |

`byte/short/char` thường được promote thành int khi tính toán; ba method Exact không có overload riêng cho các kiểu nhỏ ấy. Nếu kết quả phải thu hẹp về byte/short, cast có thể mất dữ liệu dù phép tính int trước đó đã checked.

### 7.1. `Math.toIntExact` khi thu hẹp

```java
long computed = Math.multiplyExact(50_000L, 50_000L);
// 2500000000: đúng trong long.

// int loss = (int)computed;        // Truncation, không tự ném.
// int value = Math.toIntExact(computed); // Throws.
```

`Math.toIntExact(long)` là API Java 8 kiểm tra giá trị long có vừa int không. Tổ hợp `multiplyExact(long,long)` + `toIntExact` cho phép tính ở miền rộng, rồi kiểm tra ranh giới khi thực sự cần int.

## 8. Bài toán nghiệp vụ: invoice và tồn kho

Dùng kiểu long chứa tiền theo **đơn vị nhỏ nhất** của đồng tiền khi mô hình nghiệp vụ cho phép. Cần kiểm tra phép nhân giá × số lượng **trước** khi cộng phí.

```java
static long totalCents(long unitPrice, long quantity, long shipping) {
    if (unitPrice < 0 || quantity < 0 || shipping < 0) {
        throw new IllegalArgumentException("negative input");
    }
    long subtotal = Math.multiplyExact(unitPrice, quantity);
    return Math.addExact(subtotal, shipping);
}
```

Đây là method snippet, chương trình hoàn chỉnh phía sau dùng tên `lineTotalCents`. Ví dụ `1_999 * 3 + 250 = 6_247` cents. Nếu số lượng cực lớn làm tích vượt long, program phải **báo lỗi**, không âm thầm trả hóa đơn âm.

Tương tự, `remainingStock` nên kiểm tra số lượng yêu cầu không vượt tồn kho rồi mới `Math.subtractExact`. Một phép trừ không overflow vẫn có thể tạo giá trị bị cấm về nghiệp vụ.

**Chú ý tiền tệ:** Không mặc định mọi currency có hai chữ số thập phân hay phép quy đổi/thuế đều chia hết. Với tiền thập phân, lãi/tỷ giá hay rounding, thường dùng `BigDecimal` cùng chính sách scale/rounding thích hợp.


## 9. ArithmeticException: phát hiện lỗi, không phải cách che lỗi

`ArithmeticException` là unchecked exception. Có thể để nó truyền ra caller hoặc bắt để chuyển sang một **mã lỗi nghiệp vụ ổn định**, chẳng hạn `NUMERIC_OVERFLOW`.

```java
try {
    long total = Math.addExact(subtotal, shipping);
    // Chỉ commit sau khi tính toán và validation thành công.
} catch (ArithmeticException overflow) {
    // Báo validation/business error; không chấp nhận giá trị wrap.
}
```

Snippet giả định `subtotal` và `shipping` là long. Không phân nhánh theo chuỗi `overflow.getMessage()` vì nội dung message không phải hợp đồng cố định của API. Không dùng `catch (Exception ex) { return 0; }` để nuốt mọi lỗi: giá 0 giả có thể làm hệ thống thanh toán/quota sai.

### 9.1. “Checked” không biến nhiều bước thành transaction

Giả sử program đã cập nhật subtotal vào object/DB rồi mới gọi `Math.addExact` để tính tổng. Nếu phép cộng thất bại, một phần dữ liệu có thể **đã được lưu**. `Math.*Exact` chỉ kiểm tra phép toán hiện tại, không rollback side effect.

Cách tốt là tính toàn bộ vào biến tạm, kiểm tra nghiệp vụ, sau đó mới commit dưới transaction/lock/immutable-state update thích hợp:

```java
long computedSubtotal = Math.multiplyExact(price, quantity);
long computedTotal = Math.addExact(computedSubtotal, shipping);
// Sau khi thành công: commit đồng bộ computedSubtotal/computedTotal.
```

Điều này không tự tạo một transaction: nếu cần atomicity giữa nhiều field hoặc bảng DB, phải dùng cơ chế giao dịch riêng.

### 9.2. Xử lý theo domain

- Giá/quantity đầu vào vượt giới hạn: từ chối yêu cầu và chỉ rõ trường dữ liệu, không sửa âm thầm.
- Invariant nội bộ đáng lẽ không bao giờ overflow: báo lỗi có ID sự kiện, theo dõi, dừng xử lý để điều tra.
- Kiểu số chưa đủ: chuyển từ int sang long hoặc `BigInteger` sau khi xem lại schema/API/storage.
- Thuật toán cố ý dùng modulo 32/64 bit (hash, bit mixing, một số giao thức): dùng wrap-around có **chủ đích**, không phải lúc nào cũng cần Exact.

## 10. Concurrency: Exact không bằng atomic update

`Math.*Exact` là static pure function, có thể gọi từ nhiều threads. Nhưng cấu trúc **đọc → tính → ghi** một field chia sẻ có thể bị race:

```java
// Sai khi nhiều thread cùng làm với count chung:
count = Math.addExact(count, 1);
```

Hai threads có thể đọc cùng giá trị cũ và ghi cùng kết quả mới (**lost update**), dù phép cộng từng thread không overflow. Muốn cộng atomically và báo overflow, Java 8 có:

```java
AtomicLong counter = new AtomicLong(0L);
long after = counter.updateAndGet(
        old -> Math.addExact(old, 1L));
```

`AtomicLong.updateAndGet` có thể gọi lại lambda khi CAS thất bại do contention, nên lambda phải **không có side effect** (không gửi email, ghi DB hay tăng counter khác bên trong). Khi tràn, method Exact ném exception trước khi biến atomic bị ghi thành giá trị đã overflow.

`AtomicLong.addAndGet`/`incrementAndGet` tự nó **atomically update**, nhưng arithmetic của chúng vẫn có thể wrap nếu vượt long. `LongAdder` tăng thông lượng cho nhiều thread nhưng không bảo đảm phát hiện overflow như `Math.addExact`. Phân biệt **atomicity, overflow checking, business transaction**.

## 11. Khi nào dùng BigInteger/BigDecimal?

### 11.1. BigInteger cho số nguyên vượt long

```java
BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
// 9223372036854775808: ngoài miền long.
```

`BigInteger` tính số nguyên với số chữ số lớn theo tài nguyên máy, không wrap ở 32/64 bit. Phù hợp khi phép nhân/tổng thật sự có thể vượt long, hoặc yêu cầu tính **tổng toán học cuối** chính xác dù trung gian lớn. Vẫn cần limit input và memory vì một BigInteger quá lớn có thể dùng nhiều RAM/CPU.

### 11.2. BigDecimal cho số thập phân cần độ chính xác

```java
BigDecimal price = new BigDecimal("9.99");
BigDecimal total = price.multiply(BigDecimal.valueOf(2L));
// 19.98.
```

`BigDecimal` phù hợp tiền, thuế, tỷ giá với chính sách scale và `RoundingMode`. Không dùng `new BigDecimal(0.1)` nếu bạn muốn chính xác decimal 0.1 (literal double đã có biểu diễn nhị phân không chính xác). Khởi tạo từ chuỗi hoặc `BigDecimal.valueOf(...)` với ý nghĩa dữ liệu rõ ràng.

`Math.addExact` không có overload cho `double`/`float`; nó không sửa được vấn đề `0.1+0.2 != 0.3` của floating-point. “Exact integer overflow checking” và “decimal financial precision” là hai nhu cầu khác nhau.

## 12. Stream và các phép cộng dồn

```java
int result = IntStream.of(10, 20, 30)
        .reduce(0, Math::addExact);
// 60.
```

`IntStream.sum()` thông thường có thể wrap khi tổng int vượt miền. `reduce(0,Math::addExact)` kiểm tra ở **từng phép cộng**, nhưng có thể throw khi **tổng trung gian** vượt int dù tổng toán học cuối vẫn trong miền, ví dụ `MAX_VALUE + 1 - 1`. Với parallel reduction, nhóm các phần có thể khác và không nên dựa vào thứ tự để quyết định khi nào có overflow.

Muốn tính tổng cuối đủ lớn, dùng long nếu chứng minh được range, hoặc BigInteger cho yêu cầu không phụ thuộc trung gian:

```java
BigInteger[] numbers = {
    BigInteger.valueOf(Integer.MAX_VALUE),
    BigInteger.ONE,
    BigInteger.ONE.negate()
};
BigInteger exactSum = Arrays.stream(numbers)
        .reduce(BigInteger.ZERO, BigInteger::add);
// 2147483647, không overflow trung gian.
```

Ví dụ dùng `java.util.Arrays` và `java.math.BigInteger`. Lưu ý `LongStream.sum()` vẫn có thể overflow long; widen từ int sang long chỉ giải quyết phạm vi int, không biến tổng thành vô hạn.

## 13. Các hàm Exact liên quan

Java 8 còn có:

| Method | Chức năng | Ca tràn |
| --- | --- | --- |
| `incrementExact(int/long)` | Cộng 1 | MAX_VALUE+1 |
| `decrementExact(int/long)` | Trừ 1 | MIN_VALUE-1 |
| `negateExact(int/long)` | Đổi dấu | MIN_VALUE không có giá trị dương cùng kiểu |
| `toIntExact(long)` | Thu long về int | Long nằm ngoài int |
| `addExact`/`subtractExact`/`multiplyExact` | Phép cộng/trừ/nhân | Kết quả vượt miền kiểu |

```java
int x = Math.incrementExact(41);       // 42.
int y = Math.decrementExact(41);       // 40.
int z = Math.negateExact(-5);          // 5.
int n = Math.toIntExact(123L);         // 123.
```

`Math.divideExact` là API có trên JDK mới hơn (từ Java 18), **không có trong Java 8**. Với phép chia int/long Java 8, cần xử lý divide-by-zero và ca `MIN_VALUE / -1` riêng nếu yêu cầu báo overflow.

## 14. Hiệu năng và khi nào nên dùng

Ưu tiên `Math.*Exact` tại những phép tính có **rủi ro overflow gây sai nghiệp vụ**. Không cần tự viết bit-twiddling check dễ sai khi JDK đã có method chuẩn; JVM có thể tối ưu các method này. Tuy nhiên không hứa overhead luôn bằng zero hay không đáng kể: tốc độ phụ thuộc số lần throw, JIT, CPU và workload. Đo bằng JMH nếu performance là yếu tố quyết định.

Không biến overflow thành đường đi bình thường trong vòng lặp có tần suất cao: ném/catching exception liên tục không phải phép toán saturating hoặc modulo hiệu quả. Nếu muốn saturation, phải có một policy rõ ràng và kiểm thử riêng, không coi Exact tự làm điều đó.

## 15. Checklist review và test biên

| Kiểm tra | Câu hỏi |
| --- | --- |
| Giới hạn loại dữ liệu | Int/long có đủ cho miền thực tế và trung gian không? |
| Phép cộng | MAX+1, MIN-1, hai số âm cộng nhau đã test? |
| Phép trừ | MIN-1, MAX-(-1), thứ tự x-y đã đúng? |
| Phép nhân | 50000*50000 int, Long.MAX*2 và MIN*(-1) đã test? |
| Promotion | Toán hạng đã widen **trước** khi tính? |
| Cast | Thu long về int có dùng `toIntExact`? |
| Domain | Không âm/không vượt tồn được validate riêng? |
| Side effect | Tất cả tính toán xong mới commit? |
| Concurrency | Atomic update/lock/transaction có đúng? |
| Fallback | Overflow có được báo lỗi thay vì trả 0 tùy tiện? |
| Stream | Tổng trung gian có thể vượt mặc dù tổng cuối hợp lệ? |
| Tài chính | Decimal scale, minor units và rounding policy rõ? |

## 16. Ví dụ Java 8 đầy đủ và tự kiểm chứng

Lưu thành **`ExactArithmeticDemo.java`**. Chương trình dùng int/long checked arithmetic, so sánh với wrap của toán tử thường, kiểm tra cast trước/sau, dùng `toIntExact`, mô phỏng invoice tính bằng cents, tồn kho, BigInteger và BigDecimal. Helper `checkedInt`/`checkedLong` chỉ chuyển exception thành chữ `OVERFLOW` **để kiểm thử stdout dễ dàng**; không phải chính sách production cho tiền.



```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.function.IntSupplier;
import java.util.function.LongSupplier;

public class ExactArithmeticDemo {
    private static String checkedInt(IntSupplier operation) {
        try {
            return Integer.toString(operation.getAsInt());
        } catch (ArithmeticException ex) {
            return "OVERFLOW";
        }
    }
    private static String checkedLong(LongSupplier operation) {
        try {
            return Long.toString(operation.getAsLong());
        } catch (ArithmeticException ex) {
            return "OVERFLOW";
        }
    }
    private static long lineTotalCents(long unitPriceCents,
                                       long quantity,
                                       long shippingCents) {
        if (unitPriceCents < 0 || quantity < 0 || shippingCents < 0) {
            throw new IllegalArgumentException("negative money or quantity");
        }
        long products = Math.multiplyExact(unitPriceCents, quantity);
        return Math.addExact(products, shippingCents);
    }
    private static long remainingStock(long available, long requested) {
        if (available < 0 || requested < 0 || requested > available) {
            throw new IllegalArgumentException("invalid stock request");
        }
        return Math.subtractExact(available, requested);
    }
    public static void main(String[] args) {
        int add = Math.addExact(2_000_000_000, 100_000_000);
        int subtract = Math.subtractExact(-2_000_000_000, 100_000_000);
        int multiply = Math.multiplyExact(30_000, 40_000);
        long multiplyLong = Math.multiplyExact(3_000_000_000L, 2L);
        long addLong = Math.addExact(9_000_000_000L, 10_000L);
        int rawAdd = Integer.MAX_VALUE + 1;
        int rawSubtract = Integer.MIN_VALUE - 1;
        int rawMultiply = 50_000 * 50_000;
        long wrongWiden = (long) (50_000 * 50_000);
        long correctWiden = Math.multiplyExact((long) 50_000, 50_000L);
        String addFailure = checkedInt(
                () -> Math.addExact(Integer.MAX_VALUE, 1));
        String subtractFailure = checkedInt(
                () -> Math.subtractExact(Integer.MIN_VALUE, 1));
        String multiplyFailure = checkedInt(
                () -> Math.multiplyExact(50_000, 50_000));
        String narrowFailure = checkedInt(
                () -> Math.toIntExact(correctWiden));
        String longAddFailure = checkedLong(
                () -> Math.addExact(Long.MAX_VALUE, 1L));
        String longSubtractFailure = checkedLong(
                () -> Math.subtractExact(Long.MIN_VALUE, 1L));
        String longMultiplyFailure = checkedLong(
                () -> Math.multiplyExact(Long.MAX_VALUE, 2L));
        long cents = lineTotalCents(1_999L, 3L, 250L);
        long stock = remainingStock(14L, 8L);
        String invoiceOverflow = checkedLong(
                () -> lineTotalCents(Long.MAX_VALUE, 2L, 0L));
        BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        BigDecimal decimal = new BigDecimal("9.99")
                .multiply(BigDecimal.valueOf(2L));

        System.out.println("add int: " + add);
        System.out.println("subtract int: " + subtract);
        System.out.println("multiply int: " + multiply);
        System.out.println("multiply long: " + multiplyLong);
        System.out.println("add long: " + addLong);
        System.out.println("unchecked max+1: " + rawAdd);
        System.out.println("addExact max+1: " + addFailure);
        System.out.println("unchecked min-1: " + rawSubtract);
        System.out.println("subtractExact min-1: " + subtractFailure);
        System.out.println("unchecked 50000*50000: " + rawMultiply);
        System.out.println("multiplyExact overflow: " + multiplyFailure);
        System.out.println("cast after multiply: " + wrongWiden);
        System.out.println("widen before multiply: " + correctWiden);
        System.out.println("toIntExact overflow: " + narrowFailure);
        System.out.println("long add overflow: " + longAddFailure);
        System.out.println("long subtract overflow: " + longSubtractFailure);
        System.out.println("long multiply overflow: " + longMultiplyFailure);
        System.out.println("invoice cents: " + cents);
        System.out.println("remaining stock: " + stock);
        System.out.println("invoice overflow: " + invoiceOverflow);
        System.out.println("BigInteger result: " + huge);
        System.out.println("BigDecimal result: " + decimal);

        if (add != 2_100_000_000 || subtract != -2_100_000_000
                || multiply != 1_200_000_000
                || multiplyLong != 6_000_000_000L
                || addLong != 9_000_010_000L
                || rawAdd != Integer.MIN_VALUE
                || rawSubtract != Integer.MAX_VALUE
                || rawMultiply != -1_794_967_296
                || wrongWiden != -1_794_967_296L
                || correctWiden != 2_500_000_000L
                || !addFailure.equals("OVERFLOW")
                || !subtractFailure.equals("OVERFLOW")
                || !multiplyFailure.equals("OVERFLOW")
                || !narrowFailure.equals("OVERFLOW")
                || !longAddFailure.equals("OVERFLOW")
                || !longSubtractFailure.equals("OVERFLOW")
                || !longMultiplyFailure.equals("OVERFLOW")
                || cents != 6_247L || stock != 6L
                || !invoiceOverflow.equals("OVERFLOW")
                || !huge.toString().equals("9223372036854775808")
                || !decimal.toPlainString().equals("19.98")) {
            throw new AssertionError("Exact math mismatch");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch với JDK 17+ ở mức Java 8, hoặc dùng compiler JDK 8:

```bash
javac --release 8 ExactArithmeticDemo.java
java ExactArithmeticDemo
```

**Stdout đã kiểm thử trên OpenJDK 24:**


```text
add int: 2100000000
subtract int: -2100000000
multiply int: 1200000000
multiply long: 6000000000
add long: 9000010000
unchecked max+1: -2147483648
addExact max+1: OVERFLOW
unchecked min-1: 2147483647
subtractExact min-1: OVERFLOW
unchecked 50000*50000: -1794967296
multiplyExact overflow: OVERFLOW
cast after multiply: -1794967296
widen before multiply: 2500000000
toIntExact overflow: OVERFLOW
long add overflow: OVERFLOW
long subtract overflow: OVERFLOW
long multiply overflow: OVERFLOW
invoice cents: 6247
remaining stock: 6
invoice overflow: OVERFLOW
BigInteger result: 9223372036854775808
BigDecimal result: 19.98
Checks passed.
```

### 16.1. Giải thích kết quả

Các dòng `add int`/`subtract int`/`multiply int`/`multiply long` cho thấy các phép hợp lệ. Hai dòng `unchecked` với MAX+1/MIN-1 cho thấy wrap xảy ra ở hai đầu miền int; các lời gọi `addExact/subtractExact` tương ứng ném exception và helper hiển thị `OVERFLOW`.

`50000*50000` bằng 2.500.000.000 theo toán học, không vừa int. Vì thế `unchecked 50000*50000` và `cast after multiply` cùng ra -1.794.967.296. `widen before multiply` trả 2.500.000.000 đúng trong long. `toIntExact` tiếp tục từ chối thu về int. Ba phép checked long cũng phát hiện overflow khi long không đủ.

`invoice cents` là 1999 × 3 + 250 = 6247; `remaining stock` là 14 − 8 = 6. Invoice cực lớn báo `OVERFLOW` mà không dùng giá trị sai. `BigInteger result` lớn hơn `Long.MAX_VALUE` một đơn vị. `BigDecimal result` là 19.98. `Checks passed` xác nhận mọi assert bằng code, không phụ thuộc `-ea`.

## 17. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi toán tử `+ - *` tự ném khi vượt int/long | Số bị wrap âm thầm | Dùng `Math.*Exact` khi cần |
| Coi biến nhận long khiến phép nhân int tự wide | Overload int vẫn được chọn | Cast toán hạng trước khi tính |
| Viết `(long)(a*b)` | Overflow đã diễn ra trước cast | `(long)a*b`/`multiplyExact(long,long)` |
| Cast long về int khi không kiểm tra | Mất dữ liệu | `Math.toIntExact` |
| Chỉ test overflow phía dương | Lọt ca MIN_VALUE | Test cả phía âm và dương |
| Tính `-Integer.MIN_VALUE` bằng toán tử thường | Wrap thành chính MIN_VALUE | `negateExact` |
| Coi `subtractExact` tự kiểm tra tồn kho âm | -2 vẫn nằm trong long | Domain validation riêng |
| Ghi subtotal vào DB rồi phép cộng total lỗi | Ghi dở dang | Tính/validate trước, transaction sau |
| Catch ArithmeticException và trả 0 tùy tiện | Che lỗi dữ liệu | Error code rõ ràng |
| Dùng `Math.addExact` để update shared count nhưng không atomic | Lost update | `AtomicLong.updateAndGet` hoặc synchronization |
| Dùng `AtomicLong.addAndGet` tưởng có overflow check | Atomicity không bao gồm check | CAS update với `Math.addExact` |
| Tổng trung gian tràn dù tổng cuối hợp lệ | Checked reduce có thể throw sớm | Miền rộng/BigInteger |
| Chọn long cho số cần hơn 64-bit | Long vẫn tràn | `BigInteger` |
| Dùng double cho tiền rồi nghĩ Exact giải quyết sai số | API không hỗ trợ float/double | `BigDecimal`/minor units |
| So sánh nội dung `ex.getMessage()` | Không phải hợp đồng cố định | Sử dụng error code của app |

## 18. Bài tập và đáp án

**1.** `Math.addExact(Integer.MAX_VALUE,0)` và `Math.addExact(Integer.MAX_VALUE,1)`? — Lần đầu trả MAX_VALUE, lần sau ném ArithmeticException.

**2.** `Math.subtractExact(Integer.MIN_VALUE,0)` có lỗi? — Không. Trừ 1 mới vượt miền âm.

**3.** `Math.multiplyExact(1000,2000)` trả gì? — 2.000.000 kiểu int.

**4.** `Math.multiplyExact(50000,50000)` có trả int âm không? — Không, nó ném exception; toán tử nhân unchecked mới wrap.

**5.** Vì sao `(long)(50000*50000)` ra số âm? — Nhân int trước, cast long sau. Widen một toán hạng trước.

**6.** Hai đối số là int nhưng biến nhận long, `Math.addExact` dùng overload gì? — `int,int`.

**7.** Sau phép nhân checked trong long, muốn trả int thì sao? — `Math.toIntExact` trước khi gán, có thể ném nếu không vừa int.

**8.** `Math.subtractExact(10L,12L)` có chặn tồn âm? — Không, nó trả -2L; validation nghiệp vụ là bước riêng.

**9.** Có thể giữ tích hơn 64-bit không? — Dùng `BigInteger.multiply`.

**10.** Tính chính xác khoản thập phân 9.99 nhân 2? — `new BigDecimal("9.99").multiply(BigDecimal.valueOf(2))`.

**11.** Dùng Math.addExact trong nhiều threads có tránh lost update không? — Không; cần AtomicLong/CAS, lock hoặc transaction phù hợp.

**12.** `Math.divideExact` có biên dịch được với `--release 8` không? — Không; API này có trên JDK mới hơn.

## 19. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Math](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): overload, `ArithmeticException`, miền số nguyên và các API Exact.
- [Oracle Java SE 8 — Math](https://docs.oracle.com/javase/8/docs/api/java/lang/Math.html): xác nhận `addExact`/`subtractExact`/`multiplyExact` từ Java 8.
- [Oracle Java SE 26 — BigInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html): số nguyên lớn không bị giới hạn 32/64-bit.
- [Oracle Java SE 26 — BigDecimal](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, scale và rounding.
- [Oracle Java SE 26 — AtomicLong](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic update và `updateAndGet`.
- [JLS — Operators and Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html): quy tắc arithmetic trên kiểu nguyên.

**Tóm tắt:** `Math.addExact`, `subtractExact` và `multiplyExact` là cách chuẩn phát hiện **integer overflow** mà toán tử thường có thể che giấu. Chọn đúng overload theo **kiểu đối số**, widen **trước** phép tính, thu hẹp bằng `toIntExact`, kết hợp validation/transaction theo miền nghiệp vụ, và chuyển sang `BigInteger`/`BigDecimal` khi kiểu số hữu hạn không đủ. “Exact” không tự tạo phép toán atomic đa luồng hay giúp số thực không sai số.
