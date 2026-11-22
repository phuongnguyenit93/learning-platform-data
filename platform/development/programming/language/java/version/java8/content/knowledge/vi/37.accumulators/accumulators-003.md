# LongAccumulator, DoubleAccumulator và toán tử tích lũy trong Java

**`LongAccumulator`** và **`DoubleAccumulator`** là hai lớp trong package `java.util.concurrent.atomic`, được bổ sung từ **Java 8** và vẫn được sử dụng trong Java hiện nay. Cả hai giúp nhiều thread **cùng cập nhật một kết quả thống kê tổng hợp**, ví dụ giá trị lớn nhất, nhỏ nhất, tổng, phép OR cờ bit hoặc một phép kết hợp tùy biến, mà không phải khóa toàn bộ các lần cập nhật vào cùng một biến duy nhất.

Điểm quan trọng nhất của chủ đề không nằm ở tên class mà ở **toán tử tích lũy**: bạn cung cấp một hàm hai đối số (`LongBinaryOperator` hoặc `DoubleBinaryOperator`) cùng **phần tử đơn vị** (*identity*). Java có thể giữ nhiều vùng cập nhật nội bộ nhằm giảm tranh chấp, rồi áp dụng lại hàm khi tổng hợp. Do đó, tính đúng đắn phụ thuộc vào **hàm kết hợp, thứ tự cập nhật, identity và giới hạn quan sát đồng thời**.

Bài này giải thích: cách tạo `LongAccumulator`/`DoubleAccumulator`; các toán tử `max`, `min`, cộng, nhân, OR và GCD; đại số kết hợp/giao hoán/identity; cách hoạt động ở mức công khai của API; `accumulate`, `get`, `reset` và `getThenReset`; phép đo đa luồng; so sánh `LongAdder`, `DoubleAdder` và `AtomicLong`; sai số floating-point, NaN, signed zero, tràn số, cách kiểm thử và lỗi thường gặp. Nội dung ưu tiên kiến thức **còn áp dụng hiện nay**, không dựa vào API lỗi thời.

Các chương trình đầy đủ đều dùng **Java 17+**, phù hợp cả với API cốt lõi Java 8, có lệnh chạy và stdout được đối chiếu trên OpenJDK. Khi ví dụ chỉ là snippet minh họa trong phương thức, bài sẽ nói rõ.

## 1. Bài toán: nhiều thread cập nhật một thống kê

Giả sử một server có nhiều worker. Mỗi worker xử lý một phần dữ liệu và cần cập nhật:
- Số lượng request.
- Thời gian xử lý **lớn nhất** trong một cửa sổ quan sát.
- Điểm số **nhỏ nhất** từ nhiều tác vụ.
- Tổng bytes đã chuyển.
- Hợp các bit flag của nhiều kết quả.
- Giá trị thống kê theo một phép kết hợp có đặc tính toán học rõ.

Dùng một `long max` thông thường:

```java
if (sample > max) {
    max = sample;
}
```

Đây là **phản ví dụ đặt trong phương thức**. Nhiều thread đọc và ghi `max` đồng thời không có cơ chế đồng bộ sẽ gặp **data race** và có thể làm mất cập nhật. Biến `volatile long max` không tự sửa lỗi của chuỗi “đọc, so sánh, ghi”: `volatile` làm rõ visibility nhưng không biến phép cập nhật nhiều bước thành atomic.

Một giải pháp là `AtomicLong.accumulateAndGet(sample, Long::max)`, cho **một biến nguyên tử duy nhất**. Giải pháp khác là `LongAccumulator(Long::max, Long.MIN_VALUE)`, phù hợp khi có rất nhiều **updates** và ít **reads**, vì cấu trúc có thể chia vùng cập nhật theo mức tranh chấp.

`LongAccumulator` không phải thuốc thay thế mọi atomic; nó tối ưu **thống kê dùng để tổng hợp**, không có mục tiêu cung cấp một **giá trị cập nhật đơn lẻ tuyến tính hóa** để điều khiển đồng bộ tinh vi.

## 2. Hai lớp và toán tử tương ứng

| Lớp | Input | Toán tử | Identity | Lấy kết quả |
| --- | --- | --- | --- | --- |
| `LongAccumulator` | `long` | `LongBinaryOperator` (`long,long → long`) | `long` | `get(): long` |
| `DoubleAccumulator` | `double` | `DoubleBinaryOperator` (`double,double → double`) | `double` | `get(): double` |

Cú pháp cơ bản:

```java
LongAccumulator largest =
        new LongAccumulator(Long::max, Long.MIN_VALUE);

DoubleAccumulator highest =
        new DoubleAccumulator(
                Double::max, Double.NEGATIVE_INFINITY);
```

Đây là snippet sau khi import `java.util.concurrent.atomic.*`. Cả hai loại có ba thao tác cốt lõi:

```java
largest.accumulate(12L); // Đưa một quan sát vào bộ tích lũy.
long observed = largest.get(); // Tính giá trị tổng hợp hiện tại.
largest.reset();        // Trở về identity; chỉ nên làm khi ngừng cập nhật.
```

Không có `set(value)` dùng chung như ở `AtomicLong`, vì `Accumulator` **không phải một biến đơn được đọc/ghi nguyên tử** theo mô hình CAS. Muốn đổi toán tử/identity, thường tạo accumulator mới trong lifecycle tương ứng, không giả định có method thay operator sau khởi tạo.

## 3. `LongBinaryOperator` và `DoubleBinaryOperator` là functional interface

`LongBinaryOperator` nằm trong `java.util.function`, nhận hai `long` và trả một `long`:

```java
LongBinaryOperator sum = (a, b) -> a + b;
LongBinaryOperator max = Long::max;
LongBinaryOperator flags = (a, b) -> a | b;
```

`DoubleBinaryOperator` nhận/trả kiểu `double`:

```java
DoubleBinaryOperator sum = Double::sum;
DoubleBinaryOperator max = Double::max;
DoubleBinaryOperator min = Double::min;
```

Đây là snippet trong phương thức đã import `java.util.function.*`. Hai interface có phương thức trừu tượng `applyAsLong(long left, long right)` và `applyAsDouble(double left, double right)`. Có thể truyền lambda hoặc method reference trực tiếp vào constructor.

Một lớp `Accumulator` áp dụng toán tử với **giá trị đã lưu** là đối số thứ nhất và **giá trị mới đưa vào** là đối số thứ hai, ví dụ `f(existing, incoming)`. Nhưng thứ tự **kết hợp nhiều cập nhật giữa các thread** không bảo đảm cố định, nên **không dùng phép toán phụ thuộc thứ tự**.

Toán tử không phải callback “chạy đúng một lần cho mỗi lời gọi accumulate”. Dưới tranh chấp, cập nhật CAS thất bại có thể làm implementation **áp dụng lại hàm**. Vì thế **toán tử bắt buộc không có side effects**.

## 4. Identity là phần tử đơn vị, không phải chỉ là “giá trị khởi tạo”

Một identity `e` đúng cho phép tích lũy `f` phải thỏa ở cả hai phía:

```text
f(e, x) = x
f(x, e) = x
```

Ví dụ:

| Mục đích | Toán tử `f(a,b)` | Identity đúng |
| --- | --- | --- |
| Cộng `long` | `a + b` hoặc `Long::sum` | `0L` |
| Nhân `long` | `a * b` | `1L` |
| Lấy `max(long)` | `Long::max` | `Long.MIN_VALUE` |
| Lấy `min(long)` | `Long::min` | `Long.MAX_VALUE` |
| Hợp cờ bit (OR) | `a \| b` | `0L` |
| Giao cờ bit (AND) | `a & b` | `-1L`, tất cả bit 1 |
| XOR bit | `a ^ b` | `0L` |
| GCD trên số nguyên không âm | `gcd(a,b)` | `0L` |
| Cộng `double` | `Double::sum` | `0.0`, có lưu ý signed zero |
| Max `double` | `Double::max` | `Double.NEGATIVE_INFINITY` |
| Min `double` | `Double::min` | `Double.POSITIVE_INFINITY` |
| Nhân `double` | `a * b` | `1.0`, có lưu ý NaN/infinity/rounding |

**Sai identity gây sai ngay cả khi chỉ có một thread.**

Ví dụ `new LongAccumulator(Long::max, 0L)` **không đúng** nếu mọi dữ liệu có thể âm: bộ tích lũy khởi tạo ở 0, nên `max(-9,-3,-7)` sẽ không xuống -3 mà bị chặn bởi 0. Dùng `Long.MIN_VALUE` cho miền `long` đầy đủ.

Tương tự, `new DoubleAccumulator(Double::max, 0.0)` sẽ cho kết quả 0 nếu mọi quan sát là số âm. Identity đúng của max trên domain mở rộng `double` là **negative infinity**.

**Identity không có nghĩa “chưa có dữ liệu” tách biệt.** Nếu giá trị thật có thể bằng identity (max nhận đúng `Long.MIN_VALUE`, min nhận `Double.POSITIVE_INFINITY`), chỉ nhìn `get()` không phân biệt “chưa có sample” với “đã có sample bằng identity”. Nếu nghiệp vụ cần phân biệt, theo dõi số lượng/flag riêng **và quy định tính nhất quán khi đọc cả hai**.

## 5. Tính kết hợp, giao hoán và thứ tự không xác định

Để nhiều thread cập nhật và Java có thể gom các nhánh theo nhiều thứ tự, toán tử nên thỏa:

**Kết hợp** (*associative*):

```text
f(f(a, b), c) = f(a, f(b, c))
```

**Giao hoán** (*commutative*):

```text
f(a, b) = f(b, a)
```

**Phần tử đơn vị** (*identity*) như mục trước.

Ví dụ tốt:
- `Long::max`, `Long::min`.
- `Long::sum` trên miền `long` với phép cộng modulo 2^64 theo semantics tràn của Java (nhưng giá trị tổng **không còn chính xác toán học** nếu overflow).
- Bitwise AND, OR, XOR với identity tương ứng.
- GCD cho các số nguyên không âm và một implementation phù hợp.
- Nhân `long` với identity 1 trên miền kết quả modulo 2^64; có thể overflow về mặt nghiệp vụ.

**Ví dụ không nên dùng:** `(a,b) -> a - b`. Phép trừ không giao hoán và không kết hợp; `0` không phải identity **hai phía**:

```text
5 - 0 = 5
0 - 5 = -5
(10 - 4) - 2 = 4
10 - (4 - 2) = 8
```

Không dùng nối chuỗi “giữ thứ tự cập nhật” bằng một phép fold phụ thuộc thứ tự (dù lớp này chỉ hỗ trợ long/double) để mô phỏng hàng đợi. Nếu ý nghĩa yêu cầu thứ tự **chính xác**, hãy dùng cơ chế xử lý có thứ tự với đồng bộ hóa phù hợp.

### Double là ngoại lệ toán học quan trọng

Phép cộng `double` trên máy **không kết hợp tuyệt đối** do rounding:
- `(a + b) + c` có thể khác `a + (b + c)`.
- `DoubleAccumulator` với phép cộng vẫn là API có thể dùng cho thống kê khi **chấp nhận sai số floating-point**.
- Nếu yêu cầu kết quả cộng **bit-for-bit ổn định ở mọi interleaving**, không nên dùng phép tổng hợp đa luồng floating point không thứ tự.
- JavaDoc khuyến cáo cân nhắc độ ổn định số học khi các giá trị khác nhau nhiều bậc độ lớn.

## 6. Nguyên tắc purity: toán tử phải không có side effects

Sai lầm lớn:

```java
AtomicInteger invocations = new AtomicInteger();

LongAccumulator bad = new LongAccumulator(
        (a, b) -> {
            invocations.incrementAndGet(); // KHÔNG NÊN.
            return Math.max(a, b);
        },
        Long.MIN_VALUE);
```

Đây là **phản ví dụ** đặt trong phương thức, có import `java.util.concurrent.atomic.*`. Dưới contention, JVM có thể thử lại một cập nhật và **gọi lại hàm**; `invocations` không phải số mẫu đã thêm và side effect có thể xảy ra nhiều lần cho cùng một lần `accumulate`.

Toán tử nên:
- **Deterministic** theo đối số với domain đã định nghĩa.
- Không mutate object/state được chia sẻ.
- Không log, ghi DB, gửi message hoặc tăng counter trong lambda.
- Không gọi I/O, sleep, block hay mở lock.
- Không phụ thuộc thời điểm hiện tại, random, ThreadLocal hoặc thứ tự thread.
- Tối giản, vì có thể được gọi thường xuyên trong hot path.

Mọi side effect cần đặt **bên ngoài** operator theo semantics của ứng dụng. Nếu một lần `accumulate` phải kéo theo giao dịch exactly-once, `Accumulator` không phải nền tảng kiểm soát side effect; cần transaction/queue/idempotency thích hợp.

## 7. Cách hoạt động: nhiều vùng cập nhật giảm contention

Ở mức API, mỗi đối tượng duy trì **một hoặc nhiều biến nội bộ** phục vụ cùng một kết quả tích lũy. Khi cập nhật từ nhiều thread tranh chấp, implementation có thể **mở rộng số vùng lưu** để phân tán va chạm. Đây là mô hình của họ `LongAdder`, `LongAccumulator`, `DoubleAdder`, `DoubleAccumulator`.

Mô tả khái niệm:

```text
      thread A ─────┐
      thread B ─────┼──> các vùng cập nhật riêng khi cần
      thread C ─────┤       [cell 0] [cell 1] [cell 2] ...
      thread D ─────┘                   │
                                      │ get()
       base value ────────────────────┼──> combine bằng operator
                                      │
                         kết quả thống kê hiện tại
```

Đây là **sơ đồ ý tưởng**, không phải hợp đồng bố cục memory hoặc số cell cụ thể. Không dựa vào chi tiết private implementation/`Unsafe`/offset bộ nhớ để viết ứng dụng. Những chi tiết nội bộ có thể thay đổi qua JDK mà không làm thay đổi API được hỗ trợ.

Ưu điểm kỳ vọng: khi nhiều thread cập nhật cùng một statistic nhưng hiếm khi đọc, độ tranh chấp có thể thấp hơn một `AtomicLong` duy nhất, **đổi lấy chi phí bộ nhớ và chi phí tổng hợp khi đọc**.

Không khẳng định luôn nhanh hơn:
- Ít contention, `AtomicLong` có thể tương đương hoặc thích hợp hơn.
- Nhiều `get()`/`reset()` liên tục làm giảm lợi thế.
- Toán tử rất nặng có thể trở thành điểm nóng.
- Thread count, core, JVM, CPU cache, NUMA, GC và input ảnh hưởng hiệu năng.
- Muốn tuyên bố tăng tốc cụ thể cần benchmark JMH và workload đại diện; đừng dùng một con số mặc định.

## 8. API chính thức của hai Accumulator

| Method | `LongAccumulator` | `DoubleAccumulator` | Ghi chú |
| --- | --- | --- | --- |
| Constructor | `(LongBinaryOperator, long identity)` | `(DoubleBinaryOperator, double identity)` | Hàm nên pure, associative/commutative |
| Đưa sample | `accumulate(long x)` | `accumulate(double x)` | Thread-safe update |
| Đọc | `get(): long` | `get(): double` | **Không phải atomic snapshot** nếu đang có cập nhật |
| Đặt lại | `reset(): void` | `reset(): void` | Trả về identity; **racy** nếu có updates |
| Đọc rồi đặt lại | `getThenReset()` | `getThenReset()` | Tương đương get + reset về hiệu ứng; **không atomic** |
| Thể hiện thành chuỗi | `toString()` | `toString()` | Dựa trên giá trị quan sát hiện tại |
| Lấy kiểu Number | `longValue()` | `doubleValue()` | Tương đương `get()` |
| Các conversion khác | `intValue()`, `floatValue()`, `doubleValue()` | `intValue()`, `longValue()`, `floatValue()` | Có narrowing/widening như primitive Java |

Hai lớp đều mở rộng `Number`. **Không dùng instance làm value object/key của Map hoặc Set cần equality theo giá trị**, vì chúng là object có trạng thái thay đổi liên tục; không định nghĩa `equals`/`hashCode` theo kết quả tính toán.

`getThenReset()` **không phải** thao tác `AtomicLong.getAndSet(identity)` có một điểm tuyến tính hóa. Sự khác biệt là then chốt khi đo thống kê theo cửa sổ.

## 9. `LongAccumulator`: toán tử max, min, OR, GCD và sum

**Max**: `new LongAccumulator(Long::max, Long.MIN_VALUE)`.

**Min**: `new LongAccumulator(Long::min, Long.MAX_VALUE)`.

**Bitwise OR**: `new LongAccumulator((a,b) -> a | b, 0L)`. Nó phù hợp khi nhiều worker cần báo “có xuất hiện loại lỗi nào” dưới dạng bit flag; OR kết hợp và giao hoán nên không yêu cầu thứ tự.

**GCD**: khi input là số nguyên không âm, Euclid GCD kết hợp/giao hoán và `gcd(0,x) = x`. Cẩn thận miền input và `Long.MIN_VALUE` nếu chuẩn hóa số âm vì `Math.abs(Long.MIN_VALUE)` vẫn âm do overflow.

**Sum**: `new LongAccumulator(Long::sum, 0L)`. Dùng đúng được nhưng nếu chỉ cần đếm/cộng, **`LongAdder` đơn giản hơn**, tránh phải truyền operator/identity mỗi lần tạo.

**Không dùng `Long::max` với identity 0 nếu dữ liệu cho phép số âm.** Nếu domain bảo đảm mọi giá trị không âm, 0 có thể là identity đối với `max` **trên domain đó**; tài liệu/chính sách domain phải rõ. Với dữ liệu `long` bất kỳ, `Long.MIN_VALUE` là lựa chọn bao quát.

## 10. Chương trình hoàn chỉnh: năm loại toán tử long

Tạo `LongOperatorsDemo.java`:

```java
import java.util.concurrent.atomic.LongAccumulator;

public class LongOperatorsDemo {
    static long gcd(long a, long b) {
        // Bài tập ví dụ chỉ nhận các số không âm.
        while (b != 0) {
            long r = a % b;
            a = b;
            b = r;
        }
        return a;
    }

    public static void main(String[] args) {
        LongAccumulator max =
                new LongAccumulator(
                        Long::max, Long.MIN_VALUE);
        System.out.println(
                "max starts at identity = " +
                        (max.get() == Long.MIN_VALUE));

        max.accumulate(-9);
        max.accumulate(-3);
        max.accumulate(-7);
        System.out.println(
                "max negative values = " + max.get());

        LongAccumulator min =
                new LongAccumulator(
                        Long::min, Long.MAX_VALUE);
        min.accumulate(8);
        min.accumulate(5);
        min.accumulate(12);
        System.out.println("min = " + min.get());

        LongAccumulator mask =
                new LongAccumulator(
                        (a, b) -> a | b, 0L);
        mask.accumulate(0b1010);
        mask.accumulate(0b0101);
        System.out.println("flags = " + mask.get());

        LongAccumulator gcdAcc =
                new LongAccumulator(
                        LongOperatorsDemo::gcd, 0L);
        gcdAcc.accumulate(24);
        gcdAcc.accumulate(36);
        gcdAcc.accumulate(60);
        System.out.println("gcd = " + gcdAcc.get());

        LongAccumulator sum =
                new LongAccumulator(Long::sum, 0L);
        sum.accumulate(7);
        sum.accumulate(-2);
        System.out.println("sum = " + sum.get());
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 LongOperatorsDemo.java
java LongOperatorsDemo
```

Kết quả cố định đã kiểm thử:

```text
max starts at identity = true
max negative values = -3
min = 5
flags = 15
gcd = 12
sum = 5
```

Giải thích:
- `max starts at identity = true`: trước sample nào, `get()` trả `Long.MIN_VALUE`.
- Ba sample đều âm, nhưng `max` vẫn chọn **-3**, không bị identity 0 chặn.
- OR các flag `1010` và `0101` tạo `1111`, tức **15**.
- `gcd(24,36,60) = 12`; operator được phép gộp theo thứ tự khác mà kết quả vẫn như nhau **trên domain không âm**.
- `sum = 5` vì 7 + (-2) = 5.

Ví dụ dùng **một thread** để minh họa toán tử và identity, chưa nhằm chứng minh throughput concurrency. Phần đa luồng ở các mục tiếp theo.

## 11. `DoubleAccumulator`: max/min/sum với số thực

Các công thức:

```java
DoubleAccumulator max =
        new DoubleAccumulator(
                Double::max, Double.NEGATIVE_INFINITY);

DoubleAccumulator min =
        new DoubleAccumulator(
                Double::min, Double.POSITIVE_INFINITY);

DoubleAccumulator sum =
        new DoubleAccumulator(
                Double::sum, 0.0);
```

Đây là đoạn minh họa trong phương thức có `import java.util.concurrent.atomic.DoubleAccumulator`.

**Chọn identity theo domain `double` mở rộng**:
- `Double.NEGATIVE_INFINITY` cho max, bao quát cả giá trị âm và âm vô cực.
- `Double.POSITIVE_INFINITY` cho min.
- `0.0` cho sum số học thường gặp, nhưng xét thêm **signed zero**, NaN và độ chính xác floating-point nếu yêu cầu bit-for-bit.
- `1.0` cho phép nhân, với caveat rounding và special floating values.

`Double::max` / `Double::min` có xử lý **NaN** và **signed zero** theo hợp đồng của Java:
- `Double.max(NaN, 1.0)` trả NaN.
- `Double.min(NaN, 1.0)` trả NaN.
- `Double.max(-0.0, +0.0)` trả **+0.0**.
- `Double.min(-0.0, +0.0)` trả **-0.0**.

Vì vậy **không bỏ qua NaN một cách tự động**: nếu bất kỳ sample là NaN, `DoubleAccumulator(Double::max, NEGATIVE_INFINITY)` có thể cho kết quả NaN. Nếu nghiệp vụ muốn bỏ qua dữ liệu không phải số hữu hạn, **lọc trước khi gọi `accumulate`**.

```java
if (Double.isFinite(sample)) {
    max.accumulate(sample);
} else {
    // Ghi nhận sample không hợp lệ ở metric riêng nếu cần.
}
```

Đây là snippet minh họa, `sample` và `max` thuộc phương thức của ứng dụng. `Double.isFinite` có từ Java 8. Cách lọc này loại cả `NaN` và `±Infinity`; **chỉ làm nếu domain không chấp nhận chúng**.

## 12. Chương trình hoàn chỉnh: DoubleAccumulator, NaN và signed zero

Tạo `DoubleOperatorsDemo.java`:

```java
import java.util.concurrent.atomic.DoubleAccumulator;

public class DoubleOperatorsDemo {
    public static void main(String[] args) {
        DoubleAccumulator max =
                new DoubleAccumulator(
                        Double::max, Double.NEGATIVE_INFINITY);
        System.out.println(
                "initial max = " + max.get());

        max.accumulate(-1.5);
        max.accumulate(3.25);
        max.accumulate(2.0);
        System.out.println("max = " + max.get());

        DoubleAccumulator min =
                new DoubleAccumulator(
                        Double::min, Double.POSITIVE_INFINITY);
        min.accumulate(-3.5);
        min.accumulate(1.25);
        System.out.println("min = " + min.get());

        DoubleAccumulator sum =
                new DoubleAccumulator(Double::sum, 0.0);
        sum.accumulate(0.25);
        sum.accumulate(1.5);
        sum.accumulate(2.25);
        System.out.println("sum = " + sum.get());

        DoubleAccumulator zeroMin =
                new DoubleAccumulator(
                        Double::min, Double.POSITIVE_INFINITY);
        zeroMin.accumulate(0.0);
        zeroMin.accumulate(-0.0);
        System.out.println(
                "min signed zero = " + zeroMin.get());

        DoubleAccumulator zeroMax =
                new DoubleAccumulator(
                        Double::max, Double.NEGATIVE_INFINITY);
        zeroMax.accumulate(-0.0);
        zeroMax.accumulate(0.0);
        System.out.println(
                "max signed zero = " + zeroMax.get());

        DoubleAccumulator nan =
                new DoubleAccumulator(
                        Double::max, Double.NEGATIVE_INFINITY);
        nan.accumulate(5.0);
        nan.accumulate(Double.NaN);
        System.out.println(
                "max contains NaN = " +
                        Double.isNaN(nan.get()));
    }
}
```

```bash
javac -encoding UTF-8 DoubleOperatorsDemo.java
java DoubleOperatorsDemo
```

```text
initial max = -Infinity
max = 3.25
min = -3.5
sum = 4.0
min signed zero = -0.0
max signed zero = 0.0
max contains NaN = true
```

Đoạn mã minh họa ba đặc tính quan trọng:
1. Identity `-Infinity` của max không phải kết quả “thống kê âm vô cực” từ một sample — đó là giá trị **khởi tạo khi chưa có sample**.
2. `Double::min/max` phân biệt dấu của zero theo API, và **NaN lan truyền** vào phép tổng hợp tương ứng.
3. Các số `0.25`, `1.5`, `2.25` biểu diễn chính xác trong nhị phân, nên ví dụ sum không bị sai khác rounding; **điều này không chứng minh mọi phép cộng double đều chính xác**.

## 13. `accumulate(x)` là cập nhật thread-safe, nhưng `get()` không là atomic snapshot

Đây là chỗ cần đọc rất sát JavaDoc.

`accumulate(x)` được thiết kế cho nhiều thread cùng gọi trên cùng một accumulator. Implementation xử lý tranh chấp nội bộ để các cập nhật được gộp theo toán tử. Tuy nhiên, **`get()` không phải một snapshot nguyên tử của toàn bộ các vùng**.

Nếu cập nhật **không diễn ra đồng thời** với `get()`:
- `get()` trả kết quả đầy đủ của những cập nhật đã hoàn tất.
- Bạn có thể kiểm tra kết quả cuối sau khi mọi task đã thực sự hoàn thành và được chờ bằng `Future.get()`/`join()` hoặc một cơ chế đồng bộ thích hợp.

Nếu có cập nhật **đồng thời**:
- `get()` có thể đọc lần lượt nhiều vùng ở những thời điểm khác nhau.
- Một số updates đến trong lúc tính có thể không xuất hiện trong kết quả đọc đó.
- Không có một ranh giới tức thời duy nhất được API hứa hẹn cho kết quả.
- Với operator không đáp ứng điều kiện đại số, kết quả càng khó diễn giải.
- `get()` **không cung cấp compare-and-set hoặc khóa để bảo vệ một invariant nhiều biến**.

**Thread-safe updates không đồng nghĩa atomic snapshot reads.** Điều này không phải bug, mà là đánh đổi thiết kế vì throughput thống kê.

## 14. Chương trình hoàn chỉnh: nhiều thread cập nhật và đọc khi quiescent

Tạo `ParallelAccumulatorsDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ParallelAccumulatorsDemo {
    public static void main(String[] args) throws Exception {
        int workers = 4;
        int iterations = 1_000;

        LongAccumulator count =
                new LongAccumulator(Long::sum, 0L);
        LongAccumulator min =
                new LongAccumulator(
                        Long::min, Long.MAX_VALUE);
        LongAccumulator max =
                new LongAccumulator(
                        Long::max, Long.MIN_VALUE);
        DoubleAccumulator sum =
                new DoubleAccumulator(Double::sum, 0.0);

        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> jobs = new ArrayList<>();

        try {
            for (int worker = 0; worker < workers; worker++) {
                final int base = worker * iterations;

                jobs.add(pool.submit(() -> {
                    try {
                        start.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    }

                    for (int i = 1; i <= iterations; i++) {
                        count.accumulate(1);
                        min.accumulate(base + i);
                        max.accumulate(base + i);
                        sum.accumulate(0.25);
                    }
                }));
            }

            start.countDown();

            for (Future<?> job : jobs) {
                job.get(); // Chờ toàn bộ worker kết thúc.
            }

            System.out.println("count = " + count.get());
            System.out.println("min = " + min.get());
            System.out.println("max = " + max.get());
            System.out.println("quarter sum = " + sum.get());
        } finally {
            start.countDown();
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 ParallelAccumulatorsDemo.java
java ParallelAccumulatorsDemo
```

```text
count = 4000
min = 1
max = 4000
quarter sum = 1000.0
```

Có bốn worker, mỗi worker cập nhật 1.000 lần. `count` nhận 4.000 lần số 1; `min` và `max` nhận các số từ 1 đến 4.000; `sum` nhận 4.000 lần 0.25, nên tổng chính xác là 1.000.0.

**Lý do kết quả stdout ổn định:** chương trình chỉ gọi `get()` **sau khi chờ `Future.get()` của mọi worker**. Nó không đọc dở trong lúc có updates. `0.25` biểu diễn chính xác bằng binary floating-point trong miền này; không suy điều tương tự cho số thực tùy ý.

`CountDownLatch` khởi động công việc cùng một thời điểm tương đối, nhưng **không kiểm soát thứ tự interleaving**. Operator phải chịu được việc không biết worker nào cập nhật trước.

## 15. `reset()`: quay lại identity, nhưng không an toàn giữa updates

`LongAccumulator.reset()` và `DoubleAccumulator.reset()` đặt các giá trị đang lưu về **identity** đã cung cấp lúc tạo:

```java
LongAccumulator max =
        new LongAccumulator(Long::max, Long.MIN_VALUE);

max.accumulate(10L);
max.reset();

long after = max.get(); // Long.MIN_VALUE khi không có cập nhật đồng thời.
```

Đây là đoạn minh họa trong phương thức.

**Cảnh báo được JavaDoc nêu rõ:** `reset()` là thao tác **intrinsically racy** khi có cập nhật đồng thời. Nó chỉ nên dùng khi biết **không có thread đang `accumulate`**. Trong lúc reset, các vùng lưu có thể bị đặt lại từng phần; updates đua với reset có thể không thuộc đúng “cửa sổ” mong muốn.

Do vậy, **không dùng `reset()` mỗi giây trong luồng scheduler độc lập khi các worker vẫn cập nhật liên tục**, rồi tự tin rằng mỗi điểm dữ liệu được tính đúng một lần vào đúng cửa sổ.

Nếu bạn cần phân tích metric theo cửa sổ không mất/không đếm trùng, hãy thiết kế protocol handoff, rotate accumulator hoặc dùng hệ thống metrics có snapshot semantics đúng, thay vì coi reset tự bảo vệ concurrency.

## 16. `getThenReset()`: đọc và reset không tạo một giao dịch nguyên tử

`getThenReset()` có hiệu ứng tương đương `get()` rồi `reset()`. Nhưng điều này **không đồng nghĩa một phép atomic read-and-clear** trên cả cấu trúc nhiều vùng.

Trong điều kiện **quiescent** — đã chờ toàn bộ updates hoàn tất:
- Nó trả giá trị tổng hợp của cửa sổ trước.
- Sau đó `get()` trả identity (cho đến khi có cập nhật mới).
- Dùng cho các đợt tính thống kê có ranh giới rõ và không cập nhật lúc snapshot.

Khi updates **đang diễn ra**:
- Giá trị trả về không bảo đảm chứa đúng mọi update trước thời điểm reset.
- Ranh giới trước/sau cửa sổ không có một instant tuyến tính hóa chung.
- Một update có thể không rơi vào cửa sổ dự tính.
- Phép gọi này **không thay thế** `AtomicLong.getAndSet(...)`.

Một ví dụ lifecycle hợp lý: tạm ngừng producer, chờ tất cả worker hoàn tất đợt, gọi `getThenReset()` để thu thống kê đợt, sau đó mới bắt đầu đợt tiếp. Nếu producer không thể ngừng, cần protocol snapshot khác hoặc chấp nhận semantics xấp xỉ theo đặc tả của hệ thống metrics.

## 17. Chương trình hoàn chỉnh: getThenReset khi đã ngừng cập nhật

Tạo `QuiescentResetDemo.java`:

```java
import java.util.concurrent.atomic.*;

public class QuiescentResetDemo {
    public static void main(String[] args) {
        LongAccumulator product =
                new LongAccumulator(
                        (a, b) -> a * b, 1L);

        product.accumulate(2);
        product.accumulate(3);
        product.accumulate(4);

        System.out.println(
                "product before = " + product.get());
        System.out.println(
                "product then reset = " + product.getThenReset());
        System.out.println(
                "product identity after = " + product.get());

        product.accumulate(5);
        System.out.println(
                "product next = " + product.get());

        product.reset();
        System.out.println(
                "product reset identity = " + product.get());

        DoubleAccumulator doubleProduct =
                new DoubleAccumulator(
                        (a, b) -> a * b, 1.0);
        doubleProduct.accumulate(1.5);
        doubleProduct.accumulate(2.0);

        System.out.println(
                "double product before = " +
                        doubleProduct.get());
        System.out.println(
                "double then reset = " +
                        doubleProduct.getThenReset());
        System.out.println(
                "double identity after = " +
                        doubleProduct.get());
    }
}
```

```bash
javac -encoding UTF-8 QuiescentResetDemo.java
java QuiescentResetDemo
```

```text
product before = 24
product then reset = 24
product identity after = 1
product next = 5
product reset identity = 1
double product before = 3.0
double then reset = 3.0
double identity after = 1.0
```

Đối với phép nhân, **identity là 1** chứ không phải 0. Sau getThenReset, `get()` trả 1; thêm sample 5 cho kết quả 5. Sau khi gọi `reset()` lại trả 1.

Ví dụ **không có cập nhật đồng thời** ở thời điểm reset. Điều này là chủ đích để kết quả ổn định và đúng ngữ nghĩa JavaDoc. **Không dùng stdout này làm bằng chứng reset an toàn giữa concurrent producers**.

## 18. So với `LongAdder` và `DoubleAdder`

Nếu toán tử chỉ là **cộng**, Java cung cấp hai lớp đơn giản hơn:

| Nhu cầu | API thường thích hợp |
| --- | --- |
| Đếm/sum long với nhiều writers | `LongAdder` |
| Sum double với nhiều writers và chấp nhận floating error | `DoubleAdder` |
| Max/min/gcd/OR hoặc operator tùy biến trên long | `LongAccumulator` |
| Max/min hoặc operator tùy biến trên double | `DoubleAccumulator` |

Ví dụ:

```java
LongAdder count = new LongAdder();
count.increment();
count.add(5);
long value = count.sum();

DoubleAdder amount = new DoubleAdder();
amount.add(0.5);
amount.add(1.25);
double total = amount.sum();
```

Đây là snippet trong phương thức có import `java.util.concurrent.atomic.*`.

JavaDoc nêu `new LongAdder()` tương đương về chức năng sum với `new LongAccumulator((a,b) -> a+b, 0L)`. Tương tự, `DoubleAdder` tương đương về mục đích sum với `DoubleAccumulator((a,b) -> a+b, 0.0)`.

**Không có nghĩa hai lớp là cùng instance hoặc cho cùng thứ tự floating-point cộng**, vì order gộp có thể khác. Cả `sum()` của Adder lẫn `get()` của Accumulator **không là atomic snapshot khi có concurrent updates**.

Với một counter đơn giản, `LongAdder` thường dễ đọc hơn `LongAccumulator(Long::sum, 0L)`. Nhưng nếu cần min/max, Adder không nhận toán tử tùy biến.

## 19. So với `AtomicLong` và `AtomicReference`

`AtomicLong` biểu diễn **một giá trị long được đọc/cập nhật nguyên tử**, có:
- `get()`, `set()`.
- `compareAndSet(expect, update)`.
- `getAndIncrement()`, `addAndGet(delta)`.
- `getAndAccumulate(x, operator)` và `accumulateAndGet(x, operator)` (Java 8+).

Ví dụ:

```java
AtomicLong max = new AtomicLong(Long.MIN_VALUE);
long current = max.accumulateAndGet(5L, Long::max);
```

Đây là snippet trong phương thức. `accumulateAndGet` cập nhật **một vị trí nguyên tử** bằng operator và trả giá trị **mới**; `getAndAccumulate` trả giá trị **trước** khi cập nhật. Dưới contention, CAS có thể retry operator nên **operator cũng cần side-effect-free**.

`AtomicLong.get()` là một lần đọc giá trị nguyên tử đơn, không phải một phép duyệt nhiều vùng. `LongAccumulator.get()` lại **gộp các vùng lưu**, vì vậy không có cùng snapshot guarantee.

| Câu hỏi | `AtomicLong` | `LongAccumulator` |
| --- | --- | --- |
| Có một giá trị long đơn để CAS/điều khiển invariant? | **Có** | **Không** |
| Update max/sum từ nhiều threads? | Có | Có |
| Một lần `get` là atomic read của một biến? | **Có** | **Không phải snapshot nguyên tử** |
| Cạnh tranh cao nhiều writes, ít reads | Có thể trở thành điểm tranh chấp | Có thể hiệu quả hơn |
| Cần operator identity tùy chỉnh | Khởi tạo giá trị đơn | Constructor nhận identity |
| Cần result mỗi update | `accumulateAndGet` trả giá trị | `accumulate` trả void |
| Chi phí không gian | Một atomic value | Có thể nhiều vùng lưu |
| Cần `getAndSet` với điểm atomic | Có | `getThenReset` **không tương đương** |

Với nhiều biến cùng phải thỏa invariant (ví dụ `min <= max` trong cùng một snapshot, count và sum của cùng tập samples), **cả hai accumulator đọc riêng cũng không tạo transaction đa biến**. Dùng lock, immutable snapshot/publish, hoặc cách quản lý theo epoch nếu cần consistency mạnh.

## 20. Chương trình hoàn chỉnh: AtomicLong, Adder và Accumulator

Tạo `AtomicAndAdderDemo.java`:

```java
import java.util.concurrent.atomic.*;

public class AtomicAndAdderDemo {
    public static void main(String[] args) {
        AtomicLong atomicMax =
                new AtomicLong(Long.MIN_VALUE);

        System.out.println(
                "atomic updated max = " +
                        atomicMax.accumulateAndGet(
                                5L, Long::max));
        System.out.println(
                "atomic max after 3 = " +
                        atomicMax.accumulateAndGet(
                                3L, Long::max));

        LongAdder longAdder = new LongAdder();
        longAdder.increment();
        longAdder.add(4);
        System.out.println(
                "LongAdder sum = " + longAdder.sum());

        DoubleAdder doubleAdder = new DoubleAdder();
        doubleAdder.add(0.5);
        doubleAdder.add(1.25);
        System.out.println(
                "DoubleAdder sum = " + doubleAdder.sum());

        LongAccumulator custom =
                new LongAccumulator(
                        Long::max, Long.MIN_VALUE);
        custom.accumulate(5);
        custom.accumulate(3);
        System.out.println(
                "LongAccumulator max = " + custom.get());
        System.out.println(
                "LongAccumulator longValue = " +
                        custom.longValue());
    }
}
```

```bash
javac -encoding UTF-8 AtomicAndAdderDemo.java
java AtomicAndAdderDemo
```

```text
atomic updated max = 5
atomic max after 3 = 5
LongAdder sum = 5
DoubleAdder sum = 1.75
LongAccumulator max = 5
LongAccumulator longValue = 5
```

Khi không có concurrent updates, các API đều cho kết quả thống kê mong đợi. **Không suy ra rằng cùng stdout nghĩa semantics concurrency giống nhau**:
- `AtomicLong` có các phương thức atomic CAS trên **một giá trị**.
- `Adder` và `Accumulator` có thể phân tán update và gộp khi đọc.
- `get()` của accumulator tương đương `longValue()` hoặc `doubleValue()` đúng kiểu; phép đổi khác kiểu có thể mất precision.

## 21. `LongAccumulator` và nguy cơ tràn số long

Java `long` là signed 64-bit:
- `Long.MAX_VALUE = 9223372036854775807`.
- `Long.MIN_VALUE = -9223372036854775808`.

Phép `+`/`*` trên `long` mặc định **wrap quanh** khi overflow, không tự ném `ArithmeticException`. Ví dụ `Long.MAX_VALUE + 1` thành `Long.MIN_VALUE`.

```java
LongAccumulator sum =
        new LongAccumulator(Long::sum, 0L);

sum.accumulate(Long.MAX_VALUE);
sum.accumulate(1L);

// sum.get() == Long.MIN_VALUE vì overflow.
```

Đây là snippet minh họa. Với mục tiêu **đếm tổng bytes/tổng tiền/tổng số đơn vị chính xác toán học**, overflow có thể là lỗi nghiệp vụ nghiêm trọng dù update thread-safe.

Không tự kết luận “LongAccumulator là atomic nên tổng không tràn”. **Atomic/concurrent-safe và numeric-range-safe là hai thuộc tính độc lập**.

Nếu cần chặn overflow:
- Xác định upper bound rõ và giám sát trước khi vượt miền.
- Dùng cơ chế tổng hợp `BigInteger` trong thiết kế có đồng bộ/partition phù hợp nếu cần precision tùy ý.
- Có thể dùng `Math.addExact` ở nơi thực sự muốn lỗi khi overflow, nhưng đưa một operator **có thể ném** vào accumulator concurrent cần xét trạng thái update, exception/retry và failure policy; không phải lúc nào cũng là thiết kế thống kê tốt.
- Với số tiền, dùng đơn vị nguyên nhỏ nhất trong long **nếu đủ miền**, hoặc `BigDecimal`/hệ thống ledger có transaction; không dùng floating double tùy tiện để lưu tiền.

Lưu ý các phép như `Long::max/min` không có overflow phép cộng, nhưng logic chuyển đơn vị của sample **trước khi accumulate** vẫn có thể tràn nếu dùng toán học `long` không kiểm tra.

## 22. Sai số floating-point và tính kết hợp không tuyệt đối

Trong IEEE 754 double, phép cộng cần làm tròn sau mỗi bước. Ví dụ:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;  // 1.0
double right = a + (b + c); // 0.0
```

Cả hai kết quả đều xuất phát từ **cùng ba số**, nhưng do thứ tự gộp khác nhau và `1` nhỏ so với `10^16`, kết quả khác.

Điều này liên quan trực tiếp đến `DoubleAccumulator((x,y)->x+y, 0.0)`:
- Implementation có thể tích lũy các phần ở nhiều vùng.
- Thứ tự gộp giữa các vùng/threads không được bảo đảm.
- Kết quả cuối có thể khác tổng tuần tự một biến.
- Một algorithm nhạy với tính ổn định số học có thể cần kỹ thuật khác.

**Không dựa vào việc sum luôn giống y hệt một chuỗi `for` tuần tự**. Nếu cần kết quả reproducible, cân nhắc partition cố định, thứ tự reduction xác định hoặc thuật toán tổng ổn định, rồi đo tradeoff hiệu năng. Nếu cần chính xác tuyệt đối cho tài chính, dùng biểu diễn số thập phân chính xác/đơn vị nguyên phù hợp, không coi `DoubleAccumulator` là lời giải.

### NaN, Infinity và ±0.0

`DoubleAccumulator` cho phép tất cả giá trị `double`, bao gồm `NaN`, `Infinity` và hai dạng số 0. `Double::max/min` có semantics liên quan:
- NaN thường khiến kết quả min/max trở thành NaN.
- `-0.0` và `+0.0` có thể tạo output khác dấu với max/min.
- Cộng double có thể cho Infinity nếu vượt miền hữu hạn.
- Một số bài toán có thể muốn bỏ qua sample không hữu hạn (`Double.isFinite`), một số lại muốn đánh dấu lỗi dữ liệu; **đặt policy trước khi tích lũy**.

Không chỉ kiểm tra `sample != Double.NaN` — biểu thức đó **luôn true** theo semantics NaN. Dùng `Double.isNaN(sample)` hoặc `Double.isFinite(sample)` tùy mục tiêu.

## 23. Chương trình hoàn chỉnh: phép trừ sai, overflow và không kết hợp của double

Tạo `FloatingAndOverflowDemo.java`:

```java
import java.util.concurrent.atomic.LongAccumulator;

public class FloatingAndOverflowDemo {
    public static void main(String[] args) {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        System.out.println(
                "floating (a+b)+c = " + ((a + b) + c));
        System.out.println(
                "floating a+(b+c) = " + (a + (b + c)));

        LongAccumulator overflow =
                new LongAccumulator(Long::sum, 0L);
        overflow.accumulate(Long.MAX_VALUE);
        overflow.accumulate(1L);
        System.out.println(
                "long overflow sum = " + overflow.get());

        LongAccumulator bad =
                new LongAccumulator((x, y) -> x - y, 0L);
        bad.accumulate(5);
        bad.accumulate(3);

        System.out.println(
                "bad subtract fold = " + bad.get());
        System.out.println(
                "bad identity right = " + (5 - 0));
        System.out.println(
                "bad identity left = " + (0 - 5));
    }
}
```

```bash
javac -encoding UTF-8 FloatingAndOverflowDemo.java
java FloatingAndOverflowDemo
```

```text
floating (a+b)+c = 1.0
floating a+(b+c) = 0.0
long overflow sum = -9223372036854775808
bad subtract fold = -8
bad identity right = 5
bad identity left = -5
```

**`bad subtract fold = -8` không phải một cách làm được khuyến nghị.** Đây chỉ là kết quả của **một thread trong lần chạy mẫu**; phép trừ không phù hợp cho accumulator đa luồng. Bằng chứng quan trọng hơn là `5 - 0` khác `0 - 5`, chứng minh `0` **không là identity hai phía**, và phép trừ còn không kết hợp/giao hoán.

Phần đầu thể hiện rounding của floating-point; phần thứ hai thể hiện overflow `long`. Hai lỗi thuộc hai domain khác nhau: **thứ tự gom kết quả** và **miền số có giới hạn**.

## 24. Một bài toán metrics thực tế: thời gian request cao nhất

Bạn có thể thu maximum elapsed time ở đơn vị nanoseconds hoặc milliseconds:

```java
final LongAccumulator maxLatencyNanos =
        new LongAccumulator(
                Long::max, Long.MIN_VALUE);

void onRequestFinished(long startedNanos) {
    long elapsed = System.nanoTime() - startedNanos;
    maxLatencyNanos.accumulate(elapsed);
}
```

Đây là snippet **thuộc một class service**, không phải class chạy độc lập. `System.nanoTime()` dùng để **đo elapsed time** trong JVM bằng hiệu tick, không dùng raw nano tick làm epoch timestamp. Trong mô hình domain request latency, thông thường elapsed >= 0 trong khoảng đo hợp lệ; bạn có thể chọn identity 0 nếu đã xác nhận mọi sample không âm, nhưng `Long.MIN_VALUE` mô tả max trên full long domain.

Tại thời điểm tạo dashboard:

```java
long observedMax = maxLatencyNanos.get();
```

Nếu nhiều request vẫn đang hoàn thành cùng lúc, `get()` là **thống kê quan sát được**, không phải snapshot nguyên tử chứa chính xác mọi request trước một ranh giới UTC. Với một thống kê “max quan sát gần đây” được cập nhật dày, mức nhất quán này có thể chấp nhận được.

Nếu cần **p99 latency**, max không đủ. Accumulator chỉ tính một đại lượng tổng hợp; muốn percentile cần histogram/quantile estimator hoặc phân phối mẫu phù hợp, không tính p99 bằng `get()` của max. Nếu dashboard cần count, sum và max, có thể dùng nhiều bộ tích lũy, nhưng ba số **không được đọc từ cùng một snapshot nguyên tử** khi các request đang cập nhật.

## 25. Thiết kế đọc/đặt lại thống kê theo cửa sổ

Bối cảnh hay gặp: “mỗi phút công bố thống kê rồi reset”. Nếu producer liên tục viết trong lúc scheduler gọi `getThenReset()`, có nguy cơ một sample không được gán vào cửa sổ nào theo đúng ranh giới mong muốn.

Một số chiến lược đúng ngữ nghĩa hơn, tùy yêu cầu:
1. **Ngừng cập nhật / quiescent point**: chờ toàn bộ producers của kỳ trước hoàn tất rồi mới gọi `getThenReset`, sau đó mở kỳ mới. Đây là tình huống JavaDoc hỗ trợ tốt.
2. **Đổi epoch/đối tượng accumulator**: công bố accumulator mới để writers mới hướng về đó; phải có protocol bảo đảm những writer đã lấy tham chiếu epoch cũ **thực sự hoàn tất** trước khi đọc/reset epoch cũ.
3. **Dùng khóa/transaction hoặc snapshot dữ liệu**: nếu cần đồng thời count/sum/max nhất quán, bảo vệ thao tác công bố bằng cơ chế có điểm đồng bộ hóa.
4. **Chấp nhận approximate metric**: nhiều hệ thống quan sát vận hành không cần số chính xác từng request tại mỗi tick, nhưng phải ghi rõ độ chính xác kỳ vọng và không dùng số đó cho ledger/billing.
5. **Dùng thư viện metrics chuyên dụng**: nếu cần sliding window, histogram, tag, retention và exporter, chọn hệ thống có semantics rõ thay vì tự xây tất cả bằng một accumulator.

**Chỉ thay field volatile** từ accumulator cũ sang mới chưa đủ đảm bảo quiescence: một writer có thể đã giữ tham chiếu cũ trước khi swap và vẫn cập nhật sau khi scheduler bắt đầu đọc/reset. Để đảm bảo không mất/đếm trùng phải có protocol handoff đầy đủ.

Tương tự, `getThenReset` không phải nút “lấy số tiền trong phút và xóa giao dịch” cho ứng dụng tài chính; tính đúng đắn kinh doanh cần mô hình transaction riêng.

## 26. Các câu hỏi phải tự trả lời trước khi chọn Accumulator

| Câu hỏi | Hướng quyết định |
| --- | --- |
| Toán tử có tính kết hợp và giao hoán trên **domain đầu vào thực tế** không? | Nếu không, không dùng striped accumulator |
| Identity có hợp lệ **hai phía** không? | Nếu sai, kết quả có thể sai cả khi một thread |
| Operator có side effect không? | Nếu có, tách side effect ra khỏi operator |
| Các update rất nhiều, đọc ít? | Accumulator/Adder có thể hợp lý |
| Cần đọc snapshot nguyên tử ở từng thời điểm? | `AtomicLong` hoặc đồng bộ hóa khác |
| Chỉ cần counter/sum? | Ưu tiên `LongAdder`/`DoubleAdder` |
| Cần max/min hoặc operator riêng? | `LongAccumulator`/`DoubleAccumulator` |
| Cần độ chính xác floating-point tuyệt đối? | Tránh reduction double không thứ tự |
| Có thể overflow long? | Kiểm tra miền số/chọn biểu diễn chính xác hơn |
| Có dùng NaN/Infinity/-0.0 không? | Xác định policy và kiểm thử |
| Có reset trong lúc producer chạy không? | Cần quiescence hoặc snapshot protocol |
| Có nhiều aggregate phải nhất quán cùng nhau? | Cần cơ chế snapshot chung, không đọc rời rạc |
| Kết quả empty state có phải phân biệt với identity không? | Cần count/flag riêng với consistency rõ |
| Cần benchmark throughput? | Dùng JMH/load test và theo dõi CPU/memory/latency |

Đây là checklist thực hành quan trọng hơn việc thuộc tên mỗi method. API là công cụ giúp **thống kê đa luồng**; tính đúng đắn do **toán tử, domain và lifecycle** quyết định.

## 27. Những lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai? | Cách tốt hơn |
| --- | --- | --- |
| `new LongAccumulator(Long::max, 0L)` với dữ liệu âm | Identity 0 làm sai max | Dùng `Long.MIN_VALUE` |
| `new DoubleAccumulator(Double::max, 0.0)` với dữ liệu âm | Không nhận max âm | Dùng `Double.NEGATIVE_INFINITY` |
| Dùng `(a,b)->a-b` | Không kết hợp/giao hoán, identity sai | Chọn toán tử có luật đại số phù hợp |
| Dùng lambda update counter/log/DB trong operator | Có thể được gọi lại khi tranh chấp | Operator pure |
| Mong `accumulate` trả giá trị sau update | Method trả `void` | Cần immediate update result thì cân nhắc `AtomicLong.accumulateAndGet` |
| Dùng `get()` làm số liệu chốt atomic giữa concurrent updates | Không atomic snapshot | Chờ quiescence hoặc snapshot protocol |
| Dùng `reset()` trong lúc producer chạy | Reset có race | Quiescent epoch/handoff |
| Dùng `getThenReset()` như `getAndSet` | Không atomic read-clear | Dùng atomic/lock nếu cần linearization |
| Đọc count và sum từ hai accumulator rồi coi là một transaction | Hai lần đọc có thể ở thời điểm khác | Snapshot chung |
| Dùng `LongAccumulator` cho phép cộng đơn giản mà bỏ qua `LongAdder` | Thêm độ phức tạp không cần | LongAdder cho counts/sums |
| Dùng `DoubleAccumulator` cộng tiền | Floating point có rounding và order khác nhau | Biểu diễn chính xác phù hợp domain |
| Cho rằng `double` sum kết quả luôn giống tuần tự | Non-associative do rounding | Chấp nhận tolerance hoặc thuật toán ổn định |
| Dùng `Double::max` rồi nghĩ tự bỏ qua NaN | NaN có thể lan truyền | Lọc sample theo policy |
| Không xét `-0.0` vs `+0.0` | Max/min có semantics signed zero | Test theo domain |
| Để identity tượng trưng “chưa có dữ liệu” khi sample bằng identity hợp lệ | Không phân biệt được empty | Theo dõi count/flag riêng |
| Bỏ qua overflow khi cộng `long` | Wrap sang số âm | Miền số/an toàn tính toán |
| Dùng `Math.abs(Long.MIN_VALUE)` để chuẩn hóa mọi số âm | Không biểu diễn được trị tuyệt đối trong long | Domain không âm hoặc BigInteger |
| Coi `LongAccumulator` luôn nhanh hơn `AtomicLong` | Chi phí thêm vùng và đọc | Benchmark workload thật |
| Cố xem private cells bằng reflection/Unsafe | Chi tiết nội bộ không phải API | Dựa vào API chính thức |
| Dùng instance mutable làm Map key theo giá trị | Không có equality theo thống kê | Lưu snapshot `long`/`double` vào key khi phù hợp |
| Lẫn nanoseconds tick `System.nanoTime` với epoch millis | Hai loại thời gian khác nhau | Chỉ tính hiệu để đo elapsed |
| Đòi số chính xác tuyệt đối giữa lúc update liên tục | Hợp đồng không cung cấp snapshot | Thiết kế đồng bộ/epoch |

Một thống kê có thể **thread-safe khi cập nhật** nhưng **không đúng nghiệp vụ** vì overflow, identity sai, thứ tự floating-point hoặc reset sai thời điểm. Luôn kiểm tra cả hai chiều.

## 28. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** `LongAccumulator` nhận toán tử kiểu gì?  
**Đáp án:** `LongBinaryOperator`, nhận hai `long` và trả một `long`, cùng identity kiểu long.

**Câu 2.** `DoubleAccumulator` khác LongAccumulator ở điều gì cốt lõi?  
**Đáp án:** Đầu vào, kết quả, operator, identity dùng `double`; do đó có NaN, Infinity, signed zero và sai số floating-point.

**Câu 3.** Identity đúng cho `Long::max` trên mọi `long` là gì?  
**Đáp án:** `Long.MIN_VALUE`, không phải 0 nếu có số âm.

**Câu 4.** Identity đúng cho `Double::min` trên domain double mở rộng là gì?  
**Đáp án:** `Double.POSITIVE_INFINITY`.

**Câu 5.** Vì sao toán tử nên không có side effects?  
**Đáp án:** Trong contention, các phép thử cập nhật có thể thất bại và operator được áp dụng lại, khiến side effect bị lặp.

**Câu 6.** `get()` trong khi nhiều worker đang update có phải một atomic snapshot không?  
**Đáp án:** Không. Nó có thể không bao gồm các update đồng thời trong lúc tính.

**Câu 7.** `reset()` có an toàn trong lúc nhiều worker đang `accumulate` không?  
**Đáp án:** Không. JavaDoc cảnh báo racy; chỉ dùng khi biết không còn concurrent updates.

**Câu 8.** `getThenReset()` có giống `AtomicLong.getAndSet(identity)` không?  
**Đáp án:** Không. Nó có hiệu ứng get rồi reset và không bảo đảm atomic read-clear giữa concurrent updates.

**Câu 9.** Khi chỉ cần đếm request, nên dùng `LongAdder` hay `LongAccumulator`?  
**Đáp án:** `LongAdder` thường rõ và tiện hơn; LongAccumulator phù hợp khi cần toán tử tùy biến.

**Câu 10.** Khi cần biết giá trị sau một cập nhật max **nguyên tử** ngay lập tức, nên cân nhắc gì?  
**Đáp án:** `AtomicLong.accumulateAndGet(value, Long::max)`, trả kết quả mới của một atomic value.

**Câu 11.** `LongAccumulator` với `Long::sum` có tự ngăn overflow không?  
**Đáp án:** Không. Phép cộng long của Java có thể wrap; cần domain/biểu diễn đúng.

**Câu 12.** Vì sao `DoubleAccumulator` tính tổng với cùng input có thể khác tuần tự?  
**Đáp án:** Thứ tự kết hợp giữa các thread/cell không bảo đảm, trong khi phép cộng floating-point không kết hợp tuyệt đối.

**Câu 13.** `Double::max` có mặc định bỏ qua NaN không?  
**Đáp án:** Không. Sample NaN có thể làm kết quả trở thành NaN; chính sách lọc phải thực hiện trước.

**Câu 14.** Tại sao `-0.0` và `+0.0` cần quan tâm?  
**Đáp án:** `Double.min/max` phân biệt dấu của zero; output có thể khác theo toán tử.

**Câu 15.** Muốn gộp các flag lỗi từ nhiều worker mà không phụ thuộc thứ tự, dùng phép gì?  
**Đáp án:** Bitwise OR `(a,b)->a|b` với identity `0L` nếu flags được biểu diễn bằng bit trong long.

**Câu 16.** Vì sao toán tử trừ không phù hợp?  
**Đáp án:** Nó không giao hoán, không kết hợp và 0 không là identity hai phía.

**Câu 17.** `LongAccumulator` có trả biết chắc chưa hề có sample khi `get()==Long.MIN_VALUE` với operator max không?  
**Đáp án:** Không, vì một sample thật có thể bằng chính Long.MIN_VALUE.

**Câu 18.** Tại sao chỉ thay biến chứa tham chiếu accumulator cũ sang mới chưa đủ để snapshot cửa sổ?  
**Đáp án:** Một worker đã giữ tham chiếu cũ có thể vẫn update sau khi biến được thay; cần handoff/quiescence protocol.

**Câu 19.** `AtomicLong.get()` và `LongAccumulator.get()` có giống nhau về snapshot không?  
**Đáp án:** Không. AtomicLong đọc một atomic value; LongAccumulator tổng hợp nhiều vùng và không atomic snapshot khi concurrent updates.

**Câu 20.** Có nên sử dụng Accumulator thay cho ledger hay transaction database?  
**Đáp án:** Không. Nó phù hợp thống kê cập nhật nhiều, không thay thế transaction/consistency của dữ liệu kinh doanh.

## 29. Tổng kết

- **`LongAccumulator` và `DoubleAccumulator`** thuộc `java.util.concurrent.atomic`, đã có từ Java 8 và vẫn phù hợp cho thống kê **nhiều cập nhật, ít lần đọc**.
- **Operator và identity quyết định tính đúng đắn**: ưu tiên hàm không side effects, associative và commutative trên domain, identity đúng hai phía.
- **`accumulate(x)` là thao tác cập nhật thread-safe; `get()` không phải atomic snapshot** nếu có cập nhật đồng thời.
- **`reset()` và `getThenReset()` có race**; chỉ dùng ở quiescent point hoặc khi đã có protocol đồng bộ hóa bảo đảm.
- **`LongAdder`/`DoubleAdder`** phù hợp đếm và cộng đơn giản; **`AtomicLong`** phù hợp khi cần atomic read/CAS và tính linearizable của một giá trị.
- **Double** phải kiểm soát NaN, Infinity, signed zero và sai số do thứ tự cộng; **long** cần kiểm soát overflow nếu nghiệp vụ yêu cầu tổng chính xác.
- Có thể dùng accumulator cho **max/min/bit flags/GCD** khi phép toán phù hợp; không dùng phép trừ hoặc logic phụ thuộc thứ tự.
- Cần **ownership, quiescence và snapshot consistency** khi gom số liệu từ nhiều accumulator hoặc tính báo cáo theo cửa sổ.
- Đo đúng hiệu năng bằng workload thực/JMH; không giả định accumulator luôn nhanh hơn mọi atomic trong mọi điều kiện.

### Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — `LongAccumulator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html): hợp đồng operator, identity, `accumulate`, `get`, `reset`, `getThenReset`.
- [Oracle Java SE 26 — `DoubleAccumulator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html): độ ổn định số học, order không xác định và giới hạn snapshot.
- [Oracle Java SE 26 — `LongAdder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html), [`DoubleAdder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html): các phép cộng chuyên dụng.
- [Oracle Java SE 26 — `AtomicLong`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): `accumulateAndGet`, `getAndAccumulate` và atomic CAS.
- [Oracle Java SE 26 — `LongBinaryOperator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/LongBinaryOperator.html), [`DoubleBinaryOperator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/DoubleBinaryOperator.html): toán tử primitive hai đối số.
- [Oracle Java SE 26 — `Double`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Double.html): NaN, signed zero và floating-point comparison.
- [Oracle Java SE 26 — `Executors`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html), [`CountDownLatch`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): công cụ chạy và kiểm thử cập nhật đa luồng.
