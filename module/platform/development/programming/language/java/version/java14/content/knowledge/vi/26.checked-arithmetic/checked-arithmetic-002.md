# Các bổ sung `decrementExact` của `StrictMath` trong Java 14

## 1. Vấn đề: trừ một đơn vị nhưng không phát hiện tràn số

Với số nguyên có dấu trong Java, biểu thức `value - 1` có thể cho kết quả không đúng về mặt toán học nếu giá trị đã ở **cận dưới** của kiểu dữ liệu. Ví dụ, `int` dùng 32 bit có dấu, chứa các giá trị từ `-2_147_483_648` đến `2_147_483_647`. Không tồn tại một giá trị `int` nào biểu diễn được:

```text
-2_147_483_648 - 1 = -2_147_483_649
```

Phép trừ số nguyên Java thông thường **không tự ném ngoại lệ** khi tràn; nó áp dụng số học có độ rộng cố định và kết quả có thể quay vòng (*wraparound*):

```java
int value = Integer.MIN_VALUE;
int wrapped = value - 1;
System.out.println(wrapped); // 2147483647
```

Đây là đoạn đặt trong một phương thức. Kết quả lớn nhất của `int` hoàn toàn trái với ý định “giảm thêm một đơn vị”.

**`StrictMath.decrementExact`** giải quyết đúng bài toán này: trả về `a - 1` nếu biểu diễn được trong kiểu `int` hoặc `long`; nếu không, **ném `ArithmeticException`** thay vì trả kết quả tràn.

**Mốc phiên bản:** Hai overload `StrictMath.decrementExact(int)` và `StrictMath.decrementExact(long)` được **bổ sung từ Java 14**. Chúng vẫn là API chuẩn được tài liệu Java SE hiện hành duy trì, không phải tính năng preview. Bài dùng Java 17+ để chạy ví dụ đầy đủ, đồng thời đã xác nhận ví dụ biên dịch được với `--release 14`.

**Ghi nhớ sớm:** Từ `Exact` trong tên phương thức nói về **kiểm tra tràn số nguyên**, không có nghĩa đây là phép giảm nguyên tử giữa nhiều luồng, một transaction hay quy tắc kiểm tra giá trị nghiệp vụ.

## 2. API được bổ sung là gì?

Hai phương thức tĩnh trong `java.lang.StrictMath`:

```java
public static int decrementExact(int a)
public static long decrementExact(long a)
```

Bảng hành vi:

| Overload | Đầu vào | Kết quả hợp lệ | Điều kiện ném ngoại lệ |
| --- | --- | --- | --- |
| `StrictMath.decrementExact(int a)` | Một `int` | `a - 1` dưới dạng `int` | `a == Integer.MIN_VALUE` |
| `StrictMath.decrementExact(long a)` | Một `long` | `a - 1` dưới dạng `long` | `a == Long.MIN_VALUE` |

Cả hai đều:

- Là **phương thức `static`**: gọi trực tiếp bằng tên lớp, không tạo `new StrictMath()`.
- Nhận **một đối số**, không phải hai đối số như `subtractExact(x, y)`.
- **Không sửa biến đối số**. Java truyền giá trị của biến kiểu nguyên thủy vào phương thức; giá trị giảm được **trả về**.
- Ném **`java.lang.ArithmeticException`** nếu trừ một tạo kết quả ngoài miền biểu diễn.
- Là API của **`java.base`**, không cần dependency ngoài hoặc `--enable-preview`.

### Kiểm tra bằng ví dụ ngắn

```java
int count = 5;
int next = StrictMath.decrementExact(count);

System.out.println(count); // 5
System.out.println(next);  // 4
```

Đây là hai biến riêng. `count` **vẫn bằng `5`** vì `decrementExact` trả về kết quả thay vì thay đổi đối số như toán tử `--`.

Nếu muốn cập nhật biến, phải gán lại:

```java
int remaining = 5;
remaining = StrictMath.decrementExact(remaining);
System.out.println(remaining); // 4
```

## 3. Vì sao chỉ tràn tại `MIN_VALUE`?

Với toán tử “trừ đúng một” và các kiểu số nguyên có dấu:

- Nếu `a > MIN_VALUE`, `a - 1` vẫn nằm trong miền biểu diễn.
- Nếu `a == MIN_VALUE`, `a - 1` thấp hơn cận dưới, không thể biểu diễn trong cùng kiểu.
- Giá trị ở `MAX_VALUE` không gây tràn khi **giảm** một.

Bảng một số biên:

| Biểu thức | Kết quả |
| --- | --- |
| `StrictMath.decrementExact(5)` | `4` |
| `StrictMath.decrementExact(1)` | `0` |
| `StrictMath.decrementExact(0)` | `-1` |
| `StrictMath.decrementExact(-5)` | `-6` |
| `StrictMath.decrementExact(Integer.MAX_VALUE)` | `2147483646` |
| `StrictMath.decrementExact(Integer.MIN_VALUE + 1)` | `Integer.MIN_VALUE` |
| `StrictMath.decrementExact(Integer.MIN_VALUE)` | Ném `ArithmeticException` |
| `StrictMath.decrementExact(10L)` | `9L` |
| `StrictMath.decrementExact(Long.MIN_VALUE + 1)` | `Long.MIN_VALUE` |
| `StrictMath.decrementExact(Long.MIN_VALUE)` | Ném `ArithmeticException` |

**Điểm dễ nhầm:** `decrementExact(0)` **không ném ngoại lệ**. Kết quả `-1` vẫn hợp lệ với `int` và `long`. Hàm kiểm tra **biên biểu diễn số nguyên**, không kiểm tra rằng “số lượng hàng tồn kho phải không âm” hay “số vé còn lại không thể âm”.

### Giá trị cực tiểu

```java
int minInt = Integer.MIN_VALUE;  // -2147483648
long minLong = Long.MIN_VALUE;   // -9223372036854775808L

// Hai lời gọi sau đều ném ArithmeticException:
StrictMath.decrementExact(minInt);
StrictMath.decrementExact(minLong);
```

Đây là **đoạn cố ý gây ngoại lệ** khi thực thi, không phải mã dùng để chạy nối tiếp mà không bắt lỗi. Không nên khẳng định văn bản của `ArithmeticException.getMessage()` luôn giống nhau ở mọi JVM; **loại ngoại lệ** mới là điều API cam kết.

## 4. So sánh `decrementExact` với `--`, `- 1` và `subtractExact`

| Cách viết | Có tự thay đổi biến? | Phát hiện tràn ở `MIN_VALUE`? | Ý nghĩa |
| --- | --- | --- | --- |
| `x - 1` | Không | Không | Tính `x - 1` theo số học `int`/`long` thông thường |
| `x--` | Có | Không | Trả giá trị cũ, sau đó giảm biến |
| `--x` | Có | Không | Giảm biến, rồi trả giá trị mới |
| `StrictMath.decrementExact(x)` | Không | **Có** | Trả giá trị giảm chính xác hoặc ném lỗi |
| `Math.decrementExact(x)` | Không | **Có** | Ngữ nghĩa nguyên tương đương |
| `StrictMath.subtractExact(x, 1)` | Không | **Có** | Trừ chính xác hai số theo overload phù hợp |

Ở đây `x` là biến kiểu `int` cho các ví dụ `- 1` và `subtractExact(x, 1)`, hoặc `long` khi đối số/overload thích hợp. Việc lựa chọn đúng kiểu rất quan trọng: số học `int` và `long` có các cận khác nhau.

### Hậu tố và tiền tố đều có thể wraparound

```java
int a = Integer.MIN_VALUE;
a--;
System.out.println(a); // 2147483647

int b = Integer.MIN_VALUE;
--b;
System.out.println(b); // 2147483647
```

Toán tử `--` làm thay đổi biến, còn `decrementExact` không. Nhưng quan trọng hơn, cả `a--` và `--b` đều **không kiểm tra overflow**. Dùng toán tử nào tùy ý định về giá trị trả về, không phải để phòng tràn.

### `decrementExact` tương đương trừ chính xác một đơn vị

```java
int a = 17;
System.out.println(
        StrictMath.decrementExact(a)
                == StrictMath.subtractExact(a, 1)
); // true
```

Nếu `a == Integer.MIN_VALUE`, cả hai đều ném `ArithmeticException`. Sự khác biệt chính là `decrementExact` mô tả **một phép giảm đơn vị**, trong khi `subtractExact` là phép trừ hai đối số tổng quát.

### `StrictMath` so với `Math`

`Math.decrementExact(int/long)` đã có trước Java 14, còn `StrictMath.decrementExact(int/long)` xuất hiện từ **Java 14**. Hai lớp đều cung cấp toán tử giảm số nguyên chính xác; đối với cùng một kiểu và đầu vào, **kết quả hoặc điều kiện tràn là giống nhau**.

`StrictMath` nổi tiếng vì các hàm số học dấu phẩy động có quy tắc tái lập nghiêm ngặt, nhưng ở đây ta đang nói về **trừ số nguyên và kiểm tra miền biểu diễn**, không phải khác biệt làm tròn số thực. Không cần chọn `StrictMath` chỉ vì nghĩ tên lớp sẽ “chính xác hơn” `Math` cho `decrementExact`; hãy ưu tiên tính nhất quán API và quy ước codebase.

## 5. Chương trình Java 17+ hoàn chỉnh: cả kết quả và trường hợp tràn

Lưu mã sau thành **`Main.java`**. Chương trình kiểm tra `int`, `long`, tính không thay đổi đối số, tràn tại cận dưới, phép trừ thông thường, ràng buộc nghiệp vụ và một ví dụ cập nhật nguyên tử riêng biệt.

```java
import java.util.concurrent.atomic.AtomicInteger;

public class Main {
    static int takeOne(int available) {
        if (available <= 0) {
            throw new IllegalArgumentException("stock must be positive");
        }
        return StrictMath.decrementExact(available);
    }

    static void checkOverflow(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=NO_EXCEPTION");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        int before = 5;
        int after = StrictMath.decrementExact(before);
        System.out.println("INT_RESULT=" + after);
        System.out.println("INPUT_UNCHANGED=" + (before == 5));
        System.out.println("ZERO=" + StrictMath.decrementExact(0));
        System.out.println("NEGATIVE=" + StrictMath.decrementExact(-5));
        System.out.println("LONG=" + StrictMath.decrementExact(10L));
        System.out.println("LONG_NEAR_MIN=" +
                StrictMath.decrementExact(Long.MIN_VALUE + 1));
        System.out.println("SAME_AS_MATH=" +
                (StrictMath.decrementExact(17) == Math.decrementExact(17)));

        checkOverflow("INT_MIN",
                () -> StrictMath.decrementExact(Integer.MIN_VALUE));
        checkOverflow("LONG_MIN",
                () -> StrictMath.decrementExact(Long.MIN_VALUE));

        int wrapped = Integer.MIN_VALUE - 1;
        System.out.println("ORDINARY_WRAP=" +
                (wrapped == Integer.MAX_VALUE));
        System.out.println("STOCK_AFTER_ONE=" + takeOne(2));
        try {
            takeOne(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("STOCK_ZERO=" + ex.getMessage());
        }

        AtomicInteger remaining = new AtomicInteger(3);
        remaining.updateAndGet(StrictMath::decrementExact);
        System.out.println("ATOMIC_LEFT=" + remaining.get());
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác đã được kiểm chứng:**

```text
INT_RESULT=4
INPUT_UNCHANGED=true
ZERO=-1
NEGATIVE=-6
LONG=9
LONG_NEAR_MIN=-9223372036854775808
SAME_AS_MATH=true
INT_MIN=ArithmeticException
LONG_MIN=ArithmeticException
ORDINARY_WRAP=true
STOCK_AFTER_ONE=1
STOCK_ZERO=stock must be positive
ATOMIC_LEFT=2
```

### Giải thích kết quả theo từng nhóm

- `INT_RESULT=4`, `INPUT_UNCHANGED=true`: hàm trả về giá trị mới mà không sửa `before`.
- `ZERO=-1`: số `-1` hợp lệ nên không có lỗi; `NEGATIVE=-6` tương tự.
- `LONG=9`: literal `10L` chọn overload `long`.
- `LONG_NEAR_MIN=-9223372036854775808`: đầu vào `Long.MIN_VALUE + 1` vẫn có thể giảm đúng một để về `Long.MIN_VALUE`; lỗi chỉ xuất hiện nếu muốn giảm thêm lần nữa.
- `SAME_AS_MATH=true`: `StrictMath` và `Math` cho kết quả bằng nhau trên đầu vào hợp lệ.
- `INT_MIN=ArithmeticException`, `LONG_MIN=ArithmeticException`: hai hàm `checkOverflow` bắt đúng loại lỗi. Output **không phụ thuộc thông báo lỗi đặc thù JVM**.
- `ORDINARY_WRAP=true`: phép `Integer.MIN_VALUE - 1` truyền thống quay vòng về `Integer.MAX_VALUE` thay vì ném lỗi.
- `STOCK_AFTER_ONE=1`: hàm nghiệp vụ `takeOne` kiểm tra tồn kho rồi mới giảm.
- `STOCK_ZERO=stock must be positive`: lỗi nghiệp vụ khi số lượng không dương là **`IllegalArgumentException` do ứng dụng chủ động ném**, không phải overflow.
- `ATOMIC_LEFT=2`: việc giảm trong `AtomicInteger.updateAndGet` được điều phối bởi `AtomicInteger`, không phải bản thân `decrementExact`.

**Kiểm chứng phiên bản:** Chương trình cũng đã biên dịch thành công với `javac --release 14`. API `StrictMath.decrementExact` vì thế phù hợp chính xác với Java 14 và vẫn dùng tốt trên Java hiện đại. `record` và những cú pháp preview không cần thiết cho ví dụ này.

## 6. Kiểu `int`, `long` và overload resolution

Java chọn overload dựa trên **kiểu biểu thức** truyền vào, không dựa trên giá trị số học mà người lập trình kỳ vọng.

```java
int a = StrictMath.decrementExact(10);   // int -> int
long b = StrictMath.decrementExact(10L); // long -> long
long c = StrictMath.decrementExact(10);  // int result được widening sang long
```

Trong dòng `c`, phương thức `int` được chọn vì đối số literal `10` có kiểu `int`; sau đó kết quả mới được mở rộng thành `long`. Nếu bạn muốn kiểm tra cận của kiểu `long`, dùng input kiểu `long`:

```java
long count = Long.MIN_VALUE + 1;
long next = StrictMath.decrementExact(count); // Long.MIN_VALUE
```

### `byte`, `short` và `char`

Java có thể **widening primitive conversion** sang `int`:

```java
byte small = 10;
int result = StrictMath.decrementExact(small);
System.out.println(result); // 9
```

Nhưng kết quả của overload đó vẫn là **`int`**, không tự co lại thành `byte`. Câu lệnh sau không hợp lệ nếu không có phép chuyển kiểu tường minh:

```java
byte small = 10;
// byte next = StrictMath.decrementExact(small); // lỗi: int cannot be converted to byte
```

Nếu phải giới hạn kết quả trong miền `byte`, `short` hay kiểu dữ liệu ứng dụng có cận hẹp, cần kiểm tra miền riêng trước khi narrowing. **`decrementExact(int)` chỉ phát hiện tràn miền `int`**: nó không thể tự biết kết quả có hợp lệ với miền `byte`, bộ đếm 0–255 hay quy tắc nghiệp vụ không.

### Boxing và `null`

Đối với `Integer` hoặc `Long`, Java có thể **unbox** để gọi overload nguyên thủy:

```java
Integer boxed = 4;
int value = StrictMath.decrementExact(boxed);
System.out.println(value); // 3
```

Nhưng nếu `boxed == null`, việc unboxing ném `NullPointerException` **trước khi** `decrementExact` xử lý số học. Đây **không phải `ArithmeticException` do overflow**. Khi đọc mã với boxed values, phải phân biệt lỗi thiếu dữ liệu và lỗi vượt miền số nguyên.

## 7. Tràn số nguyên không phải số lượng âm

Với một bộ đếm tồn kho, `0 -> -1` có thể bị coi là lỗi dù **hoàn toàn không tràn `int`**.

**Cách dùng sai về quy tắc nghiệp vụ:**

```java
int stock = 0;
stock = StrictMath.decrementExact(stock);
// stock == -1: không overflow, nhưng có thể vi phạm quy tắc tồn kho.
```

**Cách thiết kế rõ ràng hơn:**

```java
static int takeOne(int stock) {
    if (stock <= 0) {
        throw new IllegalArgumentException("stock must be positive");
    }
    return StrictMath.decrementExact(stock);
}
```

Đây là **một phương thức trong lớp**, dùng như ví dụ đã chạy trong `Main.java`. Hợp đồng trả về số lượng mới, không thay đổi cơ sở dữ liệu, không trừ trực tiếp một field chung.

Hai loại kiểm tra cần độc lập:

1. **Kiểm tra miền biểu diễn:** `decrementExact` bảo đảm toán học `stock - 1` còn biểu diễn được trong kiểu.
2. **Kiểm tra miền nghiệp vụ:** `stock > 0`, `remaining >= 0`, có quyền giảm số lượng, đơn hàng còn hợp lệ… do mã nghiệp vụ hoặc tầng dữ liệu đảm bảo.

Một số nghiệp vụ **cho phép số âm**, ví dụ số dư nợ hoặc chênh lệch kho; vì thế không tự áp quy tắc “mọi đầu vào âm là lỗi” lên `StrictMath`. Chính sách số âm phụ thuộc miền bài toán.

### Tránh làm mất dữ liệu khi có ngoại lệ

Ví dụ:

```java
int previous = Integer.MIN_VALUE;
try {
    int next = StrictMath.decrementExact(previous);
    // Chỉ cập nhật state khi phép tính đã trả về thành công.
    previous = next;
} catch (ArithmeticException ex) {
    System.out.println("value cannot be decremented");
}
```

Nếu phép tính tràn, ngoại lệ được ném **trước phép gán `previous = next`**, nên biến vẫn giữ giá trị trước đó. Tuy nhiên với một hệ thống nhiều tài nguyên, việc *một phép tính* thành công không bảo đảm các cập nhật database/file liên quan đã thành công theo kiểu transaction; phải thiết kế transaction riêng nếu cần.

## 8. `decrementExact` không bảo đảm đồng bộ giữa các thread

Tên “exact” chỉ nói về **tràn số nguyên**. Xét:

```java
int counter = 10;

// Nếu nhiều thread cùng thực hiện mà không có cơ chế đồng bộ:
counter = StrictMath.decrementExact(counter);
```

Đây là mẫu minh họa, không phải phép thử đồng thời độc lập. Về mặt logic có ba bước **đọc → tính → ghi**. Hai thread có thể cùng đọc `10`, mỗi thread tính `9`, rồi đều ghi `9`: một lần giảm bị mất (*lost update*). `decrementExact` kiểm tra đúng mỗi phép tính, nhưng **không biến cả chuỗi thao tác thành nguyên tử**.

Để đồng bộ việc cập nhật một biến trong JVM, lựa chọn tùy thiết kế:

- Dùng `synchronized` hoặc `Lock` cùng một khóa khi thao tác thuộc critical section của ứng dụng.
- Dùng `AtomicInteger`/`AtomicLong` khi cần cập nhật kiểu nguyên thủy nguyên tử và phù hợp với yêu cầu thiết kế.
- Với bộ đếm lưu trong database, thiết kế giao dịch/khóa/optimistic concurrency phù hợp. `StrictMath` không tự bảo vệ trạng thái ở database.

**Ví dụ một bộ đếm nguyên tử:**

```java
java.util.concurrent.atomic.AtomicInteger remaining =
        new java.util.concurrent.atomic.AtomicInteger(3);

int newValue = remaining.updateAndGet(StrictMath::decrementExact);
System.out.println(newValue); // 2
```

Phương thức tham chiếu `StrictMath::decrementExact` được dùng như một `IntUnaryOperator` thuần. `AtomicInteger.updateAndGet` tổ chức phép cập nhật nguyên tử và có thể gọi lại hàm tính toán nếu xảy ra contention. Bởi vậy **không ghi log, gửi email hay thay đổi trạng thái ngoài trong hàm cập nhật**: side effect có thể lặp lại khi cần retry.

Cũng không quên kiểm tra **miền nghiệp vụ**. Nếu số lượng phải không âm, chỉ gọi `updateAndGet(StrictMath::decrementExact)` trên giá trị 0 sẽ cho -1, không bị `StrictMath` chặn.

### Kiểm tra nghiệp vụ nguyên tử với `AtomicInteger`

Một mẫu tùy chọn khi muốn giữ số lượng không âm:

```java
static int takeOneAtomically(
        java.util.concurrent.atomic.AtomicInteger stock) {
    return stock.updateAndGet(current -> {
        if (current <= 0) {
            throw new IllegalStateException("out of stock");
        }
        return StrictMath.decrementExact(current);
    });
}
```

Đây là **phương thức minh họa**, không chứa `main`. Nó dùng `updateAndGet` để phối hợp kiểm tra và cập nhật một `AtomicInteger`, thay vì làm `if (stock.get() > 0)` rồi `stock.set(...)` không nguyên tử. Khi thao tác liên quan nhiều trường, nhiều object hoặc hệ thống ngoài JVM, một `AtomicInteger` vẫn **không tự tạo transaction tổng thể**.

## 9. Không thay mọi phép trừ bằng `decrementExact`

`decrementExact` phù hợp khi phép toán **giảm đúng một đơn vị** và overflow là lỗi cần báo rõ. Các bài toán khác cần công cụ khác:

| Nhu cầu | API phù hợp | Lưu ý |
| --- | --- | --- |
| Cộng hai số nguyên và phát hiện tràn | `Math.addExact(a, b)` hoặc `StrictMath.addExact(a, b)` | Kiểm tra miền `int`/`long` |
| Trừ một số khác 1 và phát hiện tràn | `Math.subtractExact(a, b)` / `StrictMath.subtractExact(a, b)` | `decrementExact` chỉ trừ 1 |
| Tăng đúng một, kiểm tra cận trên | `Math.incrementExact(a)` / `StrictMath.incrementExact(a)` | Tràn tại `MAX_VALUE` |
| Đổi dấu, kiểm tra cận dưới | `Math.negateExact(a)` / `StrictMath.negateExact(a)` | `-MIN_VALUE` không thể biểu diễn cùng kiểu |
| Chuyển `long` về `int` có kiểm tra | `Math.toIntExact(longValue)` | Ném lỗi nếu ngoài miền `int` |
| Số nguyên có thể lớn hơn miền `long` | `java.math.BigInteger` | Sử dụng phép `subtract(BigInteger.ONE)` |
| Số thập phân/tiền tệ chính xác theo scale | `java.math.BigDecimal` (và chính sách rounding) | Không dùng `decrementExact` với `float`/`double` |

**Không có** overload `decrementExact(float)`, `decrementExact(double)` hay `decrementExact(BigInteger)` trong `StrictMath`. Chỉ dùng đúng hai kiểu nguyên thủy `int` và `long`; công cụ khác sẽ biểu diễn những miền số khác.

### Nếu cần giá trị nhỏ hơn `Long.MIN_VALUE`

`long` không đủ rộng, nên cần đổi kiểu biểu diễn *trước khi* thực hiện phép tính:

```java
java.math.BigInteger value =
        java.math.BigInteger.valueOf(Long.MIN_VALUE);
java.math.BigInteger next =
        value.subtract(java.math.BigInteger.ONE);

System.out.println(next); // -9223372036854775809
```

Ví dụ này đặt trong một phương thức. `BigInteger` có độ chính xác số nguyên tùy ý theo giới hạn bộ nhớ ứng dụng, **không** phải cơ chế “bỏ qua `ArithmeticException` rồi vẫn lưu kết quả vào `long`”. Nếu dữ liệu cần lưu trong schema kiểu 64-bit, hãy xử lý yêu cầu miền ở schema trước.

## 10. Kiểm thử `decrementExact` nên tập trung vào đâu?

Một bộ kiểm thử hữu ích có thể chia thành ba nhóm:

**Nhóm 1 – giá trị thông thường:**

```java
assert StrictMath.decrementExact(5) == 4;
assert StrictMath.decrementExact(0) == -1;
assert StrictMath.decrementExact(-10) == -11;
assert StrictMath.decrementExact(100L) == 99L;
```

Những dòng này minh họa Java `assert` trong một phương thức. `assert` **có thể bị tắt mặc định**; chạy chương trình với `java -ea ...` nếu dùng assertion thuần Java làm bài kiểm thử.

**Nhóm 2 – cận hợp lệ:**

```java
assert StrictMath.decrementExact(Integer.MIN_VALUE + 1)
        == Integer.MIN_VALUE;
assert StrictMath.decrementExact(Long.MIN_VALUE + 1)
        == Long.MIN_VALUE;
```

Giá trị `MIN_VALUE + 1` là trường hợp hợp lệ sát biên; không được bắt ngoại lệ ở đó.

**Nhóm 3 – cận lỗi:** dùng JUnit hoặc bắt `ArithmeticException` rõ ràng. Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class ExactMathTest {
    @Test
    void intMinimumOverflows() {
        assertThrows(ArithmeticException.class,
                () -> StrictMath.decrementExact(Integer.MIN_VALUE));
    }

    @Test
    void longMinimumOverflows() {
        assertThrows(ArithmeticException.class,
                () -> StrictMath.decrementExact(Long.MIN_VALUE));
    }
}
```

Đây là **lớp kiểm thử cần dependency JUnit Jupiter**, không phải chương trình Java SE độc lập. Hai ca đều kiểm tra **loại ngoại lệ**, không dựa vào chuỗi `getMessage()`.

**Không chỉ thử `5 -> 4` rồi kết luận đã dùng phép toán an toàn.** Giá trị chính tạo sự khác biệt giữa `decrementExact` và `- 1` nằm ở **`MIN_VALUE`**.

## 11. Lỗi thường gặp

| Lỗi/nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Coi `decrementExact(0)` là overflow | `-1` hợp lệ trong `int`/`long` | Tách kiểm tra nghiệp vụ không âm |
| Quên gán lại giá trị trả về | `decrementExact` không tự sửa biến | `count = StrictMath.decrementExact(count)` |
| Dùng `x--` để thay thế kiểm tra tràn | `--` vẫn wraparound | Dùng exact arithmetic nếu overflow là lỗi |
| Chỉ chặn `Integer.MAX_VALUE` khi giảm | Tràn khi giảm ở **`MIN_VALUE`**, không phải MAX | Kiểm tra đúng cận dưới |
| Nghĩ `StrictMath` khác `Math` về tràn số nguyên | Hai overload decrement exact có cùng điều kiện tràn | Chọn API theo style và tương thích |
| Truyền `10` rồi nghĩ overload `long` do biến nhận là `long` | Kiểu đối số xác định overload | Dùng `10L`/biến `long` khi muốn overload long |
| Nghĩ kết quả từ `byte` vẫn là `byte` | Widening sang `int` và trả về `int` | Khai báo biến nhận đúng kiểu, xử lý narrowing cẩn thận |
| Nhầm `NullPointerException` unboxing với `ArithmeticException` overflow | Hai nguyên nhân riêng | Kiểm tra nullable inputs trước |
| Nghĩ exact có nghĩa nguyên tử giữa thread | Read–modify–write vẫn có thể lost update | `AtomicInteger`, lock hoặc transaction |
| Đặt side effect trong `AtomicInteger.updateAndGet` | Hàm có thể chạy lại khi CAS retry | Giữ hàm cập nhật thuần |
| Dùng `decrementExact` cho `double`/tiền tệ | Không có overload đó; quy tắc số học khác | `BigDecimal` hoặc thiết kế miền số thích hợp |
| Bắt `ArithmeticException` rồi bỏ qua, dùng giá trị cũ không báo gì | Che giấu lỗi tràn cần xử lý | Báo rõ hợp đồng và chính sách lỗi |
| Suy luận API StrictMath này chỉ dùng ở Java 14 | API được thêm ở Java 14 và tiếp tục tồn tại | Dùng trên Java 17/21+ bình thường |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `StrictMath.decrementExact(Integer.MIN_VALUE + 1)` cho kết quả gì?

**Đáp án:** `Integer.MIN_VALUE`, **không** ném ngoại lệ. Giá trị đầu vào cao hơn cận dưới đúng một đơn vị.

**Câu 2.** `StrictMath.decrementExact(0L)` ném lỗi hay trả giá trị?

**Đáp án:** Trả `-1L`. Không có overflow. Nếu số lượng bắt buộc không âm, phải thêm kiểm tra nghiệp vụ.

**Câu 3.** Vì sao `int next = x--;` không thể thay `int next = StrictMath.decrementExact(x);`?

**Đáp án:** `x--` trả giá trị **cũ**, đồng thời thay đổi `x` và không phát hiện tràn; `decrementExact(x)` trả kết quả đã giảm mà không sửa `x`, và ném lỗi khi giảm vượt cận dưới.

**Câu 4.** Khi `x` là `long`, có nên dùng `StrictMath.decrementExact(x)`?

**Đáp án:** Có. Java chọn overload `long`, kiểm tra cận `Long.MIN_VALUE`.

**Câu 5.** Hai thread đồng thời thực hiện `count = StrictMath.decrementExact(count)`. Có tránh được lost update không?

**Đáp án:** Không. Hàm kiểm tra tràn của một phép tính, không đồng bộ hóa chuỗi đọc–tính–ghi. Cần lock/atomic update thích hợp nếu chia sẻ dữ liệu.

**Câu 6.** `StrictMath.decrementExact(Integer.MIN_VALUE)` có trả `Integer.MAX_VALUE` như `Integer.MIN_VALUE - 1` không?

**Đáp án:** Không. Nó ném `ArithmeticException` thay vì wraparound.

**Câu 7.** Khi xử lý số nguyên lớn hơn miền `long`, có cách nào tránh tràn mà vẫn giữ đúng kết quả toán học?

**Đáp án:** Chuyển sang kiểu có miền biểu diễn phù hợp, ví dụ `BigInteger`. `decrementExact(long)` chỉ cho kết quả khi nó còn nằm trong miền `long`.

## 13. Tóm tắt áp dụng

- **API mới ở Java 14:** `StrictMath.decrementExact(int)` và `StrictMath.decrementExact(long)`; hiện vẫn sử dụng trên JDK hiện đại.
- **Hành vi:** trả `a - 1` nếu biểu diễn được; ném `ArithmeticException` khi `a == MIN_VALUE`.
- **Không có side effect trên biến đối số:** muốn thay đổi state thì gán lại kết quả hoặc dùng cơ chế cập nhật thích hợp.
- **Không thay kiểm tra nghiệp vụ:** `0 -> -1` hợp lệ về số học, có thể không hợp lệ trong ứng dụng.
- **Không thay đồng bộ:** nếu nhiều thread cùng giảm một biến, dùng `AtomicInteger`/`AtomicLong` hoặc khóa/giao dịch đúng phạm vi.
- **Không dành cho số thực hoặc BigInteger:** dùng API tính toán đúng kiểu và miền giá trị.

**Quy tắc thực hành:** khi giảm bộ đếm số nguyên mà wraparound là điều không thể chấp nhận, chọn `decrementExact` và xử lý `ArithmeticException`; đồng thời thêm validation nghiệp vụ và đồng bộ nếu tình huống yêu cầu. Một phép toán số học chính xác là **một phần** của mã an toàn, không phải toàn bộ hợp đồng trạng thái ứng dụng.

### Tham khảo chính thức

- [Oracle Java SE 14 — StrictMath (hai overload decrementExact, Since: 14)](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/lang/StrictMath.html).
- [Oracle Java SE 21 — StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html).
- [Oracle Java SE 21 — Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html).
- [Oracle Java SE 21 — AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).
- [Java Language Specification — Numeric Promotions, Arithmetic Operators and Overflow](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html).
