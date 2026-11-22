# `incrementExact`, `decrementExact`, `negateExact` và `toIntExact` trong Java

## 1. Vấn đề: số nguyên có giới hạn nhưng phép toán thường không báo tràn

Java có hai kiểu số nguyên nguyên thủy thường dùng cho phép đếm và các giá trị lớn: `int` (32 bit có dấu) và `long` (64 bit có dấu). Mỗi kiểu chỉ biểu diễn được một miền hữu hạn:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|
| `int` | `-2_147_483_648` | `2_147_483_647` |
| `long` | `-9_223_372_036_854_775_808L` | `9_223_372_036_854_775_807L` |

Giả sử bộ đếm kiểu `int` đã đạt `Integer.MAX_VALUE`. Lệnh `counter++` **không tự ném lỗi** mà đưa giá trị về `Integer.MIN_VALUE`. Tương tự, `Integer.MIN_VALUE - 1` trở thành `Integer.MAX_VALUE` và `-Integer.MIN_VALUE` lại cho `Integer.MIN_VALUE`. Đây là hệ quả của số học số nguyên cố định theo biểu diễn bù hai (*two's complement*).

Trong những bài toán cần **phát hiện tràn hoặc thu hẹp kiểu có mất dữ liệu**, Java cung cấp các phương thức trong `java.lang.Math`:

- `Math.incrementExact`: tăng một đơn vị, báo lỗi nếu tràn.
- `Math.decrementExact`: giảm một đơn vị, báo lỗi nếu tràn.
- `Math.negateExact`: lấy số đối, báo lỗi nếu số đối không biểu diễn được.
- `Math.toIntExact`: chuyển `long` sang `int`, báo lỗi nếu giá trị nằm ngoài miền `int`.

Cả bốn phương thức đều ném **`ArithmeticException`** khi không thể tạo kết quả chính xác trong kiểu trả về. Chúng không âm thầm cuốn vòng hay cắt bỏ các bit như các thao tác nguyên thông thường.

## 2. Bảng API và điều kiện thất bại

| Phương thức | Kiểu tham số và kết quả | Ý nghĩa | Trường hợp ném `ArithmeticException` |
|---|---|---|---|
| `Math.incrementExact(int)` | `int → int` | Tính `value + 1` | `value == Integer.MAX_VALUE` |
| `Math.incrementExact(long)` | `long → long` | Tính `value + 1` | `value == Long.MAX_VALUE` |
| `Math.decrementExact(int)` | `int → int` | Tính `value - 1` | `value == Integer.MIN_VALUE` |
| `Math.decrementExact(long)` | `long → long` | Tính `value - 1` | `value == Long.MIN_VALUE` |
| `Math.negateExact(int)` | `int → int` | Tính `-value` | `value == Integer.MIN_VALUE` |
| `Math.negateExact(long)` | `long → long` | Tính `-value` | `value == Long.MIN_VALUE` |
| `Math.toIntExact(long)` | `long → int` | Chuyển sang `int` mà không mất giá trị | `value < Integer.MIN_VALUE` hoặc `value > Integer.MAX_VALUE` |

**Điểm cần nhớ về overload:** ba phương thức đầu có cả phiên bản `int` lẫn `long`; `toIntExact` chỉ nhận `long` và trả `int`. Java chọn overload dựa trên **kiểu biểu thức**. Ví dụ, `Math.incrementExact(5)` trả `int` còn `Math.incrementExact(5L)` trả `long`.

Các phương thức này là `static` trong `Math`. Có thể gọi trực tiếp như `Math.incrementExact(n)` mà không tạo đối tượng. Chúng trả một **giá trị mới** và không tự thay đổi biến đã truyền.

## 3. `incrementExact` — tăng một đơn vị có kiểm tra

### Khi nào cần?

Một bộ đếm lượt giao dịch, mã phiên nội bộ, chỉ số logic hoặc tổng số lần xử lý có thể phải bảo đảm **không bao giờ âm vì tràn số**. Với toán tử `++`:

~~~java
int count = Integer.MAX_VALUE;
count++;
// count == Integer.MIN_VALUE
~~~

Đây là đoạn mã minh họa; kết quả theo số học `int` có độ rộng cố định. Toán tử `++` không báo overflow.

Đổi sang:

~~~java
int count = Integer.MAX_VALUE;
count = Math.incrementExact(count);
// Ném ArithmeticException, phép gán chưa hoàn thành.
~~~

Đoạn này cũng là minh họa và **cố ý ném lỗi khi chạy**. Khi toán hạng đã là `Integer.MAX_VALUE`, `Math.incrementExact(count)` ném `ArithmeticException` trước khi trả về; vì thế phép gán `count = ...` không hoàn thành và `count` vẫn giữ giá trị cũ.

Đối với `long` cũng vậy: `Math.incrementExact(Long.MAX_VALUE)` ném lỗi, trong khi `Long.MAX_VALUE + 1L` cho `Long.MIN_VALUE`.

Các giá trị **không phải cực đại** tăng bình thường, gồm `Math.incrementExact(-1) == 0`, `Math.incrementExact(0) == 1` và `Math.incrementExact(Integer.MAX_VALUE - 1) == Integer.MAX_VALUE`.

### Lưu ý với hậu tố toán tử

`count++` là biểu thức tăng biến và có sự khác nhau giữa tiền tố/hậu tố khi được dùng trong biểu thức lớn. `Math.incrementExact(count)` **không tương đương toàn bộ về mặt cú pháp/side effect**: nó chỉ trả giá trị tăng, không tự sửa `count`. Khi muốn cập nhật biến, phải gán `count = Math.incrementExact(count)`.

## 4. `decrementExact` — giảm một đơn vị có kiểm tra

`Math.decrementExact(value)` tính giá trị `value - 1` và kiểm tra miền của kiểu trả về. Nó phù hợp cho bộ đếm còn lại, số lượng chỗ, quota hoặc số dư đơn vị nguyên khi cần phát hiện **tràn số nguyên**.

~~~java
int remaining = Integer.MIN_VALUE;
remaining--;
// remaining == Integer.MAX_VALUE: đã tràn.

int safeRemaining = Math.decrementExact(Integer.MIN_VALUE);
// Ném ArithmeticException.
~~~

Đoạn code trên minh họa hai cách; dòng sau **cố ý ném lỗi**, không phải chương trình mẫu đầy đủ.

Ngược lại, `Math.decrementExact(0)` cho `-1` hoàn toàn hợp lệ. **`decrementExact` không kiểm tra điều kiện nghiệp vụ** “số lượng không được âm”; nó chỉ kiểm tra **miền kỹ thuật của kiểu số**. Nếu quy tắc ứng dụng là `remaining >= 0`, bạn vẫn phải kiểm tra điều kiện đó riêng.

Tương tự, `Math.decrementExact(Long.MIN_VALUE)` ném `ArithmeticException`, trong khi `Long.MIN_VALUE - 1L` trả `Long.MAX_VALUE`.

## 5. `negateExact` — lấy số đối có kiểm tra

Trong toán học, số đối của `x` là `-x`. Nhưng miền `int` và `long` **không đối xứng quanh 0**:

- `Integer.MIN_VALUE = -2_147_483_648`; số dương `2_147_483_648` không thể lưu bằng `int`.
- `Long.MIN_VALUE = -9_223_372_036_854_775_808L`; số dương `9_223_372_036_854_775_808` không thể lưu bằng `long`.

Vì vậy:

~~~java
int wrapped = -Integer.MIN_VALUE;
// wrapped == Integer.MIN_VALUE, không ném lỗi.

int checked = Math.negateExact(Integer.MIN_VALUE);
// Ném ArithmeticException.
~~~

Đây là minh họa, dòng `checked` **cố ý ném lỗi**.

Với mọi số `int` khác `Integer.MIN_VALUE`, `Math.negateExact` tạo số đối chính xác; ví dụ `Math.negateExact(-7) == 7`, `Math.negateExact(7) == -7` và `Math.negateExact(0) == 0`. `Math.negateExact(Long.MIN_VALUE)` cũng ném lỗi.

Nếu cần số đối của `Integer.MIN_VALUE` dưới dạng `long`, hãy **mở rộng trước khi đổi dấu**:

~~~java
long exactPositive = -(long) Integer.MIN_VALUE;  // 2147483648
~~~

Trong khi đó, `(long) (-Integer.MIN_VALUE)` chỉ chuyển thành `long` **sau** khi phép đổi dấu kiểu `int` đã tràn. Với `Long.MIN_VALUE`, không có kiểu nguyên thủy rộng hơn `long`; có thể dùng `BigInteger.valueOf(Long.MIN_VALUE).negate()` để có kết quả chính xác.

`Math.negateExact` cũng không phải hàm lấy trị tuyệt đối. Nó **đổi dấu** cả số dương lẫn số âm; nếu cần trị tuyệt đối với kiểm tra overflow, cần thiết kế phép toán riêng phù hợp API/JDK sử dụng. Chỉ dùng `Math.abs(Integer.MIN_VALUE)` sẽ không giải quyết được trường hợp biên.

## 6. `toIntExact` — thu hẹp `long` sang `int` mà không mất dữ liệu

Ép kiểu thường từ `long` sang `int` chỉ giữ 32 bit thấp; giá trị quá lớn hoặc quá nhỏ có thể biến thành một số hoàn toàn khác mà **không có exception**:

~~~java
long value = 2_147_483_648L;
int truncated = (int) value;
// truncated == -2147483648
~~~

Nếu ứng dụng cần bảo đảm giá trị khi chuyển kiểu vẫn **bằng chính số nguyên gốc**, dùng:

~~~java
long value = 2_147_483_648L;
int checked = Math.toIntExact(value);
// Ném ArithmeticException.
~~~

`Math.toIntExact(2_147_483_647L)` thành công với giá trị `2_147_483_647`; `Math.toIntExact(-2_147_483_648L)` cũng thành công với giá trị `-2_147_483_648`. Hai biên là **bao gồm**. Chỉ giá trị nằm **ngoài** khoảng `[Integer.MIN_VALUE, Integer.MAX_VALUE]` mới gây exception.

### So sánh `(int)` và `toIntExact`

| Giá trị `long` | Kết quả `(int) value` | Kết quả `Math.toIntExact(value)` |
|---:|---:|---|
| `42L` | `42` | `42` |
| `Integer.MAX_VALUE` | `2147483647` | `2147483647` |
| `2147483648L` | `-2147483648` | **`ArithmeticException`** |
| `Integer.MIN_VALUE` | `-2147483648` | `-2147483648` |
| `-2147483649L` | `2147483647` | **`ArithmeticException`** |

Bảng cho thấy **thu hẹp kiểu** khác **phép toán số học**: `toIntExact` không tính cộng/trừ; nó bảo đảm chuyển đổi không làm mất giá trị nguyên.

**Không có `Math.toIntExact(double)`**. Nếu bắt đầu từ `double`, bạn phải xử lý riêng điều kiện số hữu hạn, phần thập phân, miền giá trị và mất độ chính xác floating-point. `toIntExact` chỉ là hợp đồng giữa hai kiểu **số nguyên** `long` và `int`.

## 7. Ví dụ Java 17+ chạy độc lập: kết quả hợp lệ

Tạo tệp `MathExactBasics.java`:

~~~java
public class MathExactBasics {
    public static void main(String[] args) {
        System.out.println("incrementInt="
                + Math.incrementExact(41));
        System.out.println("decrementInt="
                + Math.decrementExact(-41));
        System.out.println("negateInt="
                + Math.negateExact(-41));
        System.out.println("incrementLong="
                + Math.incrementExact(2_147_483_647L));
        System.out.println("negateLong="
                + Math.negateExact(-2_147_483_648L));
        System.out.println("maxAsInt="
                + Math.toIntExact(2_147_483_647L));
        System.out.println("minAsInt="
                + Math.toIntExact(-2_147_483_648L));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac MathExactBasics.java
java MathExactBasics
~~~

Đầu ra:

~~~text
incrementInt=42
decrementInt=-42
negateInt=41
incrementLong=2147483648
negateLong=2147483648
maxAsInt=2147483647
minAsInt=-2147483648
~~~

Hai dòng `incrementLong` và `negateLong` chứng minh rằng **kiểu toán hạng quyết định miền kết quả**: với toán hạng `long`, số dương `2147483648` vẫn hợp lệ. Hai dòng chuyển về `int` nằm đúng biên và không gây lỗi.

## 8. Ví dụ Java 17+ chạy độc lập: kiểm tra các biên lỗi

Tạo tệp `MathExactFailures.java`:

~~~java
public class MathExactFailures {
    private static void check(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=OK");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=OVERFLOW");
        }
    }

    public static void main(String[] args) {
        check("incIntMax",
                () -> Math.incrementExact(Integer.MAX_VALUE));
        check("decIntMin",
                () -> Math.decrementExact(Integer.MIN_VALUE));
        check("negIntMin",
                () -> Math.negateExact(Integer.MIN_VALUE));

        check("incLongMax",
                () -> Math.incrementExact(Long.MAX_VALUE));
        check("decLongMin",
                () -> Math.decrementExact(Long.MIN_VALUE));
        check("negLongMin",
                () -> Math.negateExact(Long.MIN_VALUE));

        check("toIntTooLarge",
                () -> Math.toIntExact(2_147_483_648L));
        check("toIntTooSmall",
                () -> Math.toIntExact(-2_147_483_649L));
        check("toIntAtMin",
                () -> Math.toIntExact((long) Integer.MIN_VALUE));
    }
}
~~~

~~~bash
javac MathExactFailures.java
java MathExactFailures
~~~

Đầu ra:

~~~text
incIntMax=OVERFLOW
decIntMin=OVERFLOW
negIntMin=OVERFLOW
incLongMax=OVERFLOW
decLongMin=OVERFLOW
negLongMin=OVERFLOW
toIntTooLarge=OVERFLOW
toIntTooSmall=OVERFLOW
toIntAtMin=OK
~~~

Hàm `check` nhận một `Runnable` để thực thi lần lượt các phép toán; khi `ArithmeticException` xuất hiện, chương trình in `OVERFLOW` thay vì dựa vào **chuỗi thông điệp ngoại lệ** (vốn không nên được giả định là hợp đồng API cố định). Với Java, một lambda `() -> Math.incrementExact(value)` phù hợp `Runnable` vì lời gọi phương thức là một *statement expression* và giá trị trả về có thể bỏ qua.

Dòng cuối cũng xác nhận `toIntExact` chấp nhận **đúng biên âm**. Không phải cứ số âm là lỗi, cũng không phải mọi giá trị `long` đều nằm ngoài miền `int`.

## 9. Dùng trong mã ứng dụng: cập nhật và chuyển kiểu có kiểm soát

### 9.1. Cập nhật bộ đếm an toàn về miền số

Tạo tệp `CheckedCounterDemo.java`:

~~~java
public class CheckedCounterDemo {
    public static void main(String[] args) {
        int counter = Integer.MAX_VALUE;

        try {
            counter = Math.incrementExact(counter);
        } catch (ArithmeticException ex) {
            System.out.println("counter overflow");
        }

        System.out.println("counter=" + counter);

        long total = (long) Integer.MAX_VALUE;
        total = Math.incrementExact(total);
        System.out.println("total=" + total);

        try {
            int narrowed = Math.toIntExact(total);
            System.out.println("narrowed=" + narrowed);
        } catch (ArithmeticException ex) {
            System.out.println("cannot narrow to int");
        }
    }
}
~~~

~~~bash
javac CheckedCounterDemo.java
java CheckedCounterDemo
~~~

Đầu ra:

~~~text
counter overflow
counter=2147483647
total=2147483648
cannot narrow to int
~~~

Phép gán cho `counter` chỉ thực hiện sau khi `incrementExact` trả về thành công; vì phương thức ném lỗi, biến `counter` vẫn bằng `Integer.MAX_VALUE`. Ngược lại, phép tăng trên `long` thành công, nhưng kết quả vượt miền `int` nên `toIntExact` từ chối chuyển về `int`.

Mã trên minh họa **kiểm tra tràn số**, không tự bảo đảm các thuộc tính như giao dịch cơ sở dữ liệu hay cập nhật **nguyên tử giữa nhiều luồng**. Ví dụ, `counter = Math.incrementExact(counter)` là thao tác đọc–tính–ghi gồm nhiều bước; khi nhiều luồng cùng sửa một biến, cần cơ chế đồng bộ hoặc một API atomic phù hợp. Phép kiểm tra overflow và tính an toàn đồng thời là **hai yêu cầu khác nhau**.

### 9.2. Xử lý exception theo hợp đồng nghiệp vụ

Không nên luôn nuốt `ArithmeticException` và tiếp tục với giá trị mặc định không được xác định. Khi bộ đếm, lượng tồn kho hoặc dữ liệu giao tiếp có nguy cơ vượt miền, hãy quyết định rõ:

- **Từ chối thao tác:** thông báo giá trị không thể biểu diễn, giữ trạng thái cũ.
- **Chọn miền rộng hơn:** dùng `long` khi `int` không đủ và không có yêu cầu bắt buộc thu hẹp.
- **Dùng kiểu số nguyên độ lớn tùy ý:** `BigInteger` khi ngay cả `long` có thể không đủ.
- **Giữ hợp đồng kiểu `int` của API:** dùng `Math.toIntExact` ở biên chuyển đổi và xử lý lỗi có ngữ cảnh.

Cần tránh tự động “bão hòa” giá trị tại `MAX_VALUE` hoặc đặt lại thành 0 nếu nghiệp vụ không yêu cầu. Các phương thức `Exact` đưa ra tín hiệu lỗi để ứng dụng tự quyết định chính sách phù hợp.

### 9.3. Phép toán khác: khi nào cần `addExact` hoặc `multiplyExact`?

`incrementExact(x)` tương đương về ý nghĩa kiểm tra với `addExact(x, 1)`. `decrementExact(x)` tương đương với `subtractExact(x, 1)`. `negateExact(x)` tương đương về mục tiêu với việc lấy số đối có kiểm tra miền.

Nếu thao tác không phải ±1, hãy dùng phương thức phù hợp như `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` thay vì cố ghép nhiều phép `incrementExact`/`decrementExact`. Ví dụ, thêm 100 đơn vị: `Math.addExact(total, 100)` rõ ràng và chỉ kiểm tra một phép cộng.

Các phương thức trên kiểm tra **overflow kỹ thuật**, không thay thế validation nghiệp vụ: `Math.incrementExact(-3)` trả `-2` hợp lệ về kiểu nhưng có thể không hợp lệ nếu đối tượng phải chứa số lượng không âm.

## 10. Những hiểu lầm và lỗi phổ biến

| Nhầm lẫn | Sự thật và cách sửa |
|---|---|
| “`counter++` sẽ báo lỗi ở `MAX_VALUE`.” | `++` cuốn vòng âm thầm; dùng `Math.incrementExact(counter)` nếu cần phát hiện. |
| “`decrementExact(0)` phải báo lỗi.” | Nó trả `-1`; kiểm tra điều kiện không âm là chuyện của nghiệp vụ. |
| “`-Integer.MIN_VALUE` tạo số dương lớn nhất.” | Kết quả `int` vẫn là `Integer.MIN_VALUE`; `Math.negateExact` báo overflow. |
| “`toIntExact` làm tròn số.” | Nó chỉ chuyển `long` → `int` mà không mất giá trị; không nhận `double`. |
| “Ép `(int) longValue` sẽ ném lỗi nếu vượt miền.” | Cast nguyên thủy có thể cắt bit; dùng `Math.toIntExact`. |
| “`incrementExact` tự thay đổi biến đầu vào.” | Phương thức trả giá trị mới; phải gán hoặc dùng giá trị trả về. |
| “Các phương thức `Exact` tự giải quyết race condition.” | Chúng kiểm tra số học, không tự đồng bộ truy cập trạng thái giữa các luồng. |
| “Số vừa `long` thì chắc chắn vừa `int`.” | `long` có miền rộng hơn; dùng `toIntExact` khi cần bảo đảm thu hẹp. |
| “Chỉ cần bắt exception rồi tiếp tục bằng số 0.” | Chính sách xử lý overflow phải do yêu cầu nghiệp vụ quyết định. |

## 11. Checklist áp dụng vào dự án

1. **Chọn kiểu gốc:** `int` hay `long` có đủ miền giá trị kỳ vọng và các giá trị trung gian không?
2. **Tìm phép toán ở biên:** bộ đếm tăng/giảm, số đối, chuyển `long` → `int`; chọn đúng `incrementExact`, `decrementExact`, `negateExact`, `toIntExact`.
3. **Xác định khi có lỗi:** ném tiếp exception, chuyển thành lỗi có ngữ cảnh, từ chối thao tác hay đổi kiểu dữ liệu?
4. **Giữ trạng thái nhất quán:** gán kết quả sau khi phép kiểm tra hoàn tất; nếu có nhiều bước cập nhật, xem xét transaction/synchronization.
5. **Thử biên:** `MIN_VALUE`, `MIN_VALUE + 1`, `-1`, `0`, `1`, `MAX_VALUE - 1`, `MAX_VALUE` và hai giá trị `long` nằm ngay ngoài miền `int`.
6. **Kiểm tra điều kiện nghiệp vụ riêng:** số lượng không âm, hạn mức, định dạng dữ liệu và quyền cập nhật không được bảo đảm chỉ bằng phương thức `Exact`.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `Math.incrementExact(Integer.MAX_VALUE)` ném lỗi, còn `Integer.MAX_VALUE + 1` trả một số âm?
2. `Math.decrementExact(0)` trả bao nhiêu? Điều này có bảo đảm “tồn kho không âm” không?
3. Tại sao `Math.negateExact(Integer.MIN_VALUE)` ném lỗi, trong khi `Math.negateExact(Integer.MIN_VALUE + 1)` thành công?
4. Hai giá trị `2_147_483_647L` và `2_147_483_648L` có kết quả `Math.toIntExact` khác nhau thế nào?
5. Sự khác nhau giữa `(int) value` và `Math.toIntExact(value)` khi `value` là `long` vượt miền `int`?
6. Trong `counter = Math.incrementExact(counter)`, nếu phương thức ném ngoại lệ, giá trị của `counter` có bị gán mới không?
7. Vì sao mã trên vẫn cần đồng bộ nếu nhiều luồng cùng tăng `counter`?
8. Nếu tổng số giao dịch có thể vượt miền `long`, nên suy nghĩ đến kiểu nào thay vì cố tăng `long` mãi?

**Đáp án gợi ý:** (1) `incrementExact` kiểm tra overflow còn phép `+` thông thường không; (2) trả `-1`, phải kiểm tra quy tắc tồn kho riêng; (3) chỉ số nguyên nhỏ nhất không có số đối dương cùng miền, còn `MIN_VALUE + 1` có; (4) giá trị thứ nhất hợp lệ, thứ hai ném `ArithmeticException`; (5) cast có thể làm mất giá trị, `toIntExact` phát hiện; (6) không, gán chưa hoàn tất; (7) kiểm tra số học không bảo đảm tính nguyên tử của đọc–ghi; (8) cân nhắc `BigInteger`.

**Ghi nhớ:** `incrementExact`, `decrementExact` và `negateExact` giữ nguyên kiểu số nguyên nhưng **báo lỗi thay vì im lặng tràn**. `toIntExact` bảo đảm chuyển `long` sang `int` **không mất giá trị**. Dùng chúng tại các phép toán và biên chuyển đổi mà tính chính xác là yêu cầu của chương trình.