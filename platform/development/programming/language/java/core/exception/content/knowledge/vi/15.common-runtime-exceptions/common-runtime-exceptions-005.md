# ArithmeticException với phép toán số nguyên và các phép toán exact trong Java

`ArithmeticException` là một **unchecked exception** thuộc nhánh `RuntimeException`. Trong Java Core, nó đặc biệt quan trọng ở hai nhóm tình huống: **chia/lấy dư cho số nguyên với số chia bằng 0**, và **những phép toán yêu cầu kết quả chính xác nhưng vượt phạm vi của kiểu số nguyên**, chẳng hạn `Math.addExact`, `Math.multiplyExact` hay `Math.toIntExact`.

Điều dễ nhầm là **không phải mọi lỗi số học hay mọi trường hợp tràn số đều tự tạo `ArithmeticException`**. Các phép `+`, `-`, `*` thông thường trên `int` và `long` có thể tràn và cho kết quả quấn vòng (*wraparound*) mà không ném lỗi. Ngược lại, họ hàm `Math.*Exact` chủ động phát hiện tràn số và ném `ArithmeticException`. Phép chia số thực `double` cho `0.0` lại có hành vi khác phép chia số nguyên cho `0`.

Bài học thuộc Java Core – Exception, ngữ cảnh **Ngoại lệ runtime**, và tập trung vào ngữ nghĩa phép toán, dấu của thương/số dư, tràn số nguyên, `Math.*Exact`, các ngoại lệ số học liên quan và cách xử lý an toàn trong Java 17+.

## 1. Vị trí của `ArithmeticException` trong hệ thống exception

Phân cấp:

~~~text
java.lang.Object
    |
    +-- java.lang.Throwable
          |
          +-- java.lang.Exception
                |
                +-- java.lang.RuntimeException
                      |
                      +-- java.lang.ArithmeticException
~~~

Vì là subtype của `RuntimeException`:

- Java **không bắt buộc** phương thức khai báo `throws ArithmeticException`.
- Caller **không bị buộc** phải viết `catch (ArithmeticException e)`.
- Ngoại lệ vẫn có thể lan truyền và làm tác vụ thất bại nếu không được xử lý.
- Một `catch (ArithmeticException)` nhận nó; một `catch (RuntimeException)` hoặc `catch (Exception)` cũng nhận nếu có vị trí phù hợp.
- Nếu bắt nhiều nhánh, nên đặt handler **hẹp hơn trước** handler superclass để tránh handler không thể đạt tới.

Ví dụ:

~~~java
static int divide(int a, int b) {
    return a / b;
}
~~~

Phương thức trên biên dịch dù không khai báo `throws`. Nếu `b == 0`, thao tác `a / b` với `int` sẽ ném `ArithmeticException` khi thực thi.

Không dùng `Error` để mô tả phép chia cho 0 trong ứng dụng. `ArithmeticException` là một lỗi runtime thông thường trong ngữ nghĩa của phép toán Java, không phải bằng chứng JVM đã bị hỏng.

## 2. Phép chia nguyên `/` và phép lấy dư `%` khi số chia bằng 0

Với các toán hạng có kiểu số nguyên, cả **chia `/`** và **lấy dư `%`** đều không xác định khi mẫu số bằng `0`. Java phản ánh điều đó bằng `ArithmeticException`.

~~~java
int a = 10;
int zero = 0;

System.out.println(a / zero); // Ném ArithmeticException.
~~~

Đây là đoạn **cố ý gây lỗi runtime**, không phải ví dụ cần chạy nguyên văn mà không có handler.

Tương tự:

~~~java
int remainder = 10 % 0; // ArithmeticException khi thực thi.
~~~

Với `long`:

~~~java
long value = 10L;
long divisor = 0L;

long result = value / divisor; // ArithmeticException.
~~~

Với `byte` và `short`, Java thực hiện **binary numeric promotion** nên nhiều biểu thức được tính như phép toán `int`. Quy tắc chia/lấy dư cho 0 của phép toán nguyên vẫn áp dụng.

Ví dụ:

~~~java
byte left = 7;
byte right = 0;
int result = left / right; // ArithmeticException.
~~~

**Đừng nhầm:** `%` là phép lấy dư, không phải phép chia trả về thương. Dù kết quả cần lấy là số dư, mẫu số bằng 0 vẫn gây ngoại lệ.

### Điều gì được kiểm tra tại runtime?

Bản chất phép `/` hoặc `%` dùng toán hạng nguyên: nếu số chia bằng 0, phép toán không tạo một giá trị nguyên hợp lệ. Khi thao tác ấy được thực hiện, Java ném `ArithmeticException`.

Không nên xây kiểm thử phụ thuộc vào nguyên văn `getMessage()` như `"/ by zero"`: các biểu diễn thông điệp và môi trường có thể khác. Hãy kiểm tra **kiểu ngoại lệ**, điều kiện gây lỗi và dữ liệu cần thiết thay vì parse chuỗi.

## 3. Phép chia nguyên làm tròn về 0, không làm tròn xuống

Java chia hai số nguyên bằng cách **bỏ phần phân số và làm tròn về 0** (*truncate toward zero*):

~~~java
System.out.println(7 / 3);     // 2
System.out.println(-7 / 3);    // -2
System.out.println(7 / -3);    // -2
System.out.println(-7 / -3);   // 2
~~~

Ví dụ `-7 / 3` là `-2` chứ không phải `-3`. Điều này khác phép `Math.floorDiv(-7, 3)`, vốn trả `-3`.

Bảng đối chiếu:

| Biểu thức | Kết quả |
| --- | ---: |
| `7 / 3` | `2` |
| `-7 / 3` | `-2` |
| `7 / -3` | `-2` |
| `-7 / -3` | `2` |
| `Math.floorDiv(-7, 3)` | `-3` |
| `Math.floorDiv(7, -3)` | `-3` |

Không được dùng trực giác “chia số âm luôn làm tròn xuống” khi làm việc với toán tử `/` của số nguyên Java.

### Toán tử `%` có dấu của số bị chia

Trong phép dư nguyên Java, kết quả (nếu khác 0) có cùng dấu với **số bị chia**:

~~~java
System.out.println(7 % 3);     // 1
System.out.println(-7 % 3);    // -1
System.out.println(7 % -3);    // 1
System.out.println(-7 % -3);   // -1
~~~

Đây không phải phép modulo luôn cho số không âm. Nếu cần phép chia dạng *floor division* và số dư theo cùng quy ước, dùng `Math.floorDiv` và `Math.floorMod` khi phù hợp.

Với `a` và `b != 0`, quan hệ của phép chia/dư nguyên thông thường về mặt toán học là:

~~~text
a = (a / b) * b + (a % b)
~~~

Tuy nhiên khi biểu diễn bằng kiểu nguyên cố định, cần thận trọng với tràn số ở những biểu thức trung gian và **trường hợp đặc biệt MIN_VALUE / -1** được nêu ở phần sau.

## 4. `Math.floorDiv` và `Math.floorMod` khác `/` và `%` ở chỗ nào?

Java có các phương thức trong `Math`:

~~~java
Math.floorDiv(int x, int y)
Math.floorDiv(long x, long y)
Math.floorMod(int x, int y)
Math.floorMod(long x, long y)
~~~

Ngoài ra còn có overload phù hợp cho toán hạng `long` và `int` ở một số API. Mấu chốt:

- `/` làm tròn thương **về 0**.
- `floorDiv` chọn thương theo phép **floor** — hướng âm vô cực.
- `%` đi cùng phép chia làm tròn về 0.
- `floorMod` là số dư đi cùng `floorDiv`, nên khi khác 0, dấu thường theo **số chia**.

~~~java
System.out.println(-7 / 3);                 // -2
System.out.println(-7 % 3);                 // -1
System.out.println(Math.floorDiv(-7, 3));   // -3
System.out.println(Math.floorMod(-7, 3));   // 2
~~~

Bảng:

| Số bị chia | Số chia | `/` | `%` | `floorDiv` | `floorMod` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `3` | `2` | `1` | `2` | `1` |
| `-7` | `3` | `-2` | `-1` | `-3` | `2` |
| `7` | `-3` | `-2` | `1` | `-3` | `-2` |
| `-7` | `-3` | `2` | `-1` | `2` | `-1` |

**Quan trọng:** `Math.floorDiv(x, 0)` và `Math.floorMod(x, 0)` với số nguyên **vẫn ném `ArithmeticException`**. Chúng đổi quy tắc làm tròn/số dư chứ không làm phép chia cho 0 trở nên hợp lệ.

Cũng đừng nhầm `floorDiv` với “chia có kiểm tra tràn số”. Nó không phải hàm `Exact` để bảo đảm phát hiện mọi tràn số.

## 5. Trường hợp đặc biệt: `MIN_VALUE / -1` không ném `ArithmeticException`

Đây là một góc cạnh rất quan trọng của số nguyên có dấu.

`int` dùng 32 bit, có miền:

~~~text
Integer.MIN_VALUE = -2147483648
Integer.MAX_VALUE =  2147483647
~~~

Giá trị toán học của:

~~~text
-2147483648 / -1 = 2147483648
~~~

lớn hơn `Integer.MAX_VALUE`. **Nhưng toán tử chia nguyên Java không ném `ArithmeticException` trong trường hợp đặc biệt này.** Kết quả là `Integer.MIN_VALUE`.

~~~java
int result = Integer.MIN_VALUE / -1;
System.out.println(result);
// -2147483648
~~~

Điều tương tự đúng với `long`:

~~~java
long result = Long.MIN_VALUE / -1L;
System.out.println(result);
// -9223372036854775808
~~~

Đây là **hành vi được ngôn ngữ xác định**, không phải hành vi ngẫu nhiên của phần cứng.

### Tại sao người học hay đoán sai?

Họ suy luận rằng “phép chia cho ra giá trị ngoài miền int thì phải ném ArithmeticException”. Điều này **không đúng với toán tử `/` thông thường**: chỉ số chia bằng 0 gây ngoại lệ trực tiếp cho phép chia nguyên; riêng `MIN_VALUE / -1` có kết quả tràn được định nghĩa.

Với `Integer.MIN_VALUE % -1`, số dư là `0`.

~~~java
System.out.println(Integer.MIN_VALUE % -1); // 0
~~~

Nếu ứng dụng yêu cầu phát hiện chính xác mọi trường hợp overflow, **không thể chỉ dựa vào `ArithmeticException` của toán tử `/`**. Cần kiểm tra trường hợp đặc biệt trước phép chia:

~~~java
static int divideSafely(int a, int b) {
    if (b == 0) {
        throw new ArithmeticException("division by zero");
    }
    if (a == Integer.MIN_VALUE && b == -1) {
        throw new ArithmeticException("integer division overflow");
    }
    return a / b;
}
~~~

Đây là phương thức Java hợp lệ. Nó đưa ra một **hợp đồng ứng dụng có kiểm tra overflow** rõ ràng hơn toán tử `/` mặc định. Với `long`, cần thay bằng `Long.MIN_VALUE` và `-1L`.

Không nhầm phương thức ứng dụng này với một API `Math.divideExact` của Java 17: trong bài này không giả định JDK 17 cung cấp một overload như vậy. Hãy dùng kiểm tra đã nêu nếu cần đảm bảo trên Java 17.

## 6. Phép `+`, `-` và `*` trên `int`, `long` không tự báo overflow

Mặc định, phép toán số nguyên cố định của Java **không ném `ArithmeticException` vì tràn số** khi cộng, trừ hay nhân.

~~~java
int a = Integer.MAX_VALUE;
System.out.println(a + 1);
// -2147483648
~~~

~~~java
int b = Integer.MIN_VALUE;
System.out.println(b - 1);
// 2147483647
~~~

~~~java
int c = 50_000 * 50_000;
System.out.println(c);
// -1794967296
~~~

Giá trị toán học của `50_000 × 50_000` là `2_500_000_000`, lớn hơn `Integer.MAX_VALUE`. Với biểu diễn 32-bit, kết quả quấn vòng thành `-1794967296`.

Đối với `long`:

~~~java
long value = Long.MAX_VALUE;
System.out.println(value + 1L);
// -9223372036854775808
~~~

Những kết quả này có thể gây lỗi nghiệp vụ rất khó phát hiện nếu dùng cho tiền, bộ đếm, thời hạn, dung lượng hoặc tính số phần tử.

**Đừng cho rằng Java tự bảo vệ bằng `ArithmeticException` khi một phép toán nguyên thông thường vượt miền kiểu.**

## 7. `Math.addExact`: cộng có kiểm tra overflow

`Math.addExact` có overload cho `int` và `long`:

~~~java
int x = Math.addExact(20, 22); // 42
~~~

Nếu kết quả toán học không nằm trong miền của kiểu trả về, nó ném `ArithmeticException`:

~~~java
int x = Math.addExact(Integer.MAX_VALUE, 1);
// Ném ArithmeticException.
~~~

Với `long`:

~~~java
long x = Math.addExact(Long.MAX_VALUE, 1L);
// Ném ArithmeticException.
~~~

So sánh:

| Phép toán | Khi không overflow | Khi overflow |
| --- | --- | --- |
| `a + b` | Trả tổng | Kết quả wraparound, không tự ném lỗi |
| `Math.addExact(a, b)` | Trả tổng | Ném `ArithmeticException` |

`addExact` thích hợp khi **số đếm không được phép quấn vòng**, ví dụ tổng số phần tử xử lý, số byte có kiểm soát hoặc các chỉ số có bất biến mạnh.

Với tiền tệ, chỉ dùng `Math.addExact` sau khi bạn đã xác định rõ **đơn vị lưu trữ**, giới hạn miền, tỷ giá, làm tròn và yêu cầu kế toán. `addExact` chỉ kiểm tra overflow của kiểu nguyên, không tự giải quyết precision/scale của tiền.

## 8. `Math.subtractExact`: trừ có kiểm tra overflow

~~~java
int remaining = Math.subtractExact(100, 35); // 65
~~~

Overflow:

~~~java
int value = Math.subtractExact(Integer.MIN_VALUE, 1);
// ArithmeticException.
~~~

So sánh:

~~~java
int wrapped = Integer.MIN_VALUE - 1;
System.out.println(wrapped);
// 2147483647
~~~

`Math.subtractExact` có cả overload `long` tương ứng.

**Cần chú ý dấu:** một phép trừ từ số âm nhỏ nhất trừ tiếp một số dương có thể vượt đáy miền kiểu. Các lỗi này thường không lộ ra qua kiểm tra `result < 0` đơn giản vì kết quả đã wrap sang số dương.

## 9. `Math.multiplyExact`: nhân có kiểm tra overflow

~~~java
int area = Math.multiplyExact(200, 300);
// 60000
~~~

Overflow:

~~~java
int huge = Math.multiplyExact(50_000, 50_000);
// ArithmeticException.
~~~

Với `long`:

~~~java
long tooLarge = Math.multiplyExact(Long.MAX_VALUE, 2L);
// ArithmeticException.
~~~

Đây là một công cụ hữu ích trong phép tính kích thước:

~~~java
static int requiredBytes(int elements, int bytesPerElement) {
    if (elements < 0 || bytesPerElement < 0) {
        throw new IllegalArgumentException("negative size");
    }
    return Math.multiplyExact(elements, bytesPerElement);
}
~~~

Phương thức này kiểm tra đầu vào không âm rồi dùng phép nhân exact để không âm thầm cho ra một kích thước sai. Lưu ý: `requiredBytes` vẫn chỉ mô tả phép nhân hai số nguyên; việc cấp phát bộ nhớ cần thêm kiểm tra thực tế về giới hạn mảng, bộ nhớ khả dụng và những quy tắc khác của API.

### Nhân trước khi ép sang long là lỗi phổ biến

Sai:

~~~java
int a = 50_000;
int b = 50_000;
long product = a * b;  // Overflow int trước, rồi mới widening.
~~~

Kết quả `product` là `-1794967296L` chứ không phải `2_500_000_000L`.

Nếu muốn tính trong miền `long`:

~~~java
long product = (long) a * b;
// 2500000000
~~~

Hoặc:

~~~java
long product = Math.multiplyExact((long) a, (long) b);
// 2500000000
~~~

Nếu phép toán cuối phải nằm trong `int`, dùng `Math.multiplyExact(a, b)` để **báo lỗi overflow**, không âm thầm nâng kiểu rồi cắt bớt.

## 10. `Math.incrementExact` và `Math.decrementExact`

Với phép tăng/giảm đúng một đơn vị:

~~~java
int next = Math.incrementExact(9);      // 10
int previous = Math.decrementExact(9);  // 8
~~~

Ở biên:

~~~java
Math.incrementExact(Integer.MAX_VALUE);
// ArithmeticException.

Math.decrementExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

Cả hai có overload cho `long`.

Ngược lại:

~~~java
int x = Integer.MAX_VALUE;
x++;  // Giá trị quấn vòng thành Integer.MIN_VALUE.
~~~

Đừng viết `x++` ở một bộ đếm có yêu cầu **không được phép overflow** rồi mong tự gặp `ArithmeticException`. Dùng `Math.incrementExact` và quyết định chính sách khi đạt giới hạn.

### Ví dụ một bộ đếm có hợp đồng

~~~java
static int countOneMore(int current) {
    if (current < 0) {
        throw new IllegalArgumentException("negative count");
    }
    return Math.incrementExact(current);
}
~~~

Phương thức này phân biệt hai kiểu vấn đề:

- Giá trị hiện tại âm vi phạm tiền điều kiện → `IllegalArgumentException`.
- Giá trị đã chạm `Integer.MAX_VALUE` → `ArithmeticException` từ phép tăng exact.

Trong ứng dụng, có thể bọc `ArithmeticException` thành một loại lỗi miền nếu caller cần thông điệp/ngữ cảnh riêng. Không đánh đồng nó với “mọi lỗi đếm đều do dữ liệu không hợp lệ”.

## 11. `Math.negateExact` và `Math.absExact`

Thông thường:

~~~java
int x = -12;
System.out.println(-x);             // 12
System.out.println(Math.abs(x));    // 12
~~~

Nhưng số nguyên có dấu có **một giá trị âm nhiều hơn số giá trị dương**. Không có số `int` dương tương ứng với độ lớn của `Integer.MIN_VALUE`.

Vì vậy:

~~~java
int a = -Integer.MIN_VALUE;
System.out.println(a);
// -2147483648
~~~

Và:

~~~java
System.out.println(Math.abs(Integer.MIN_VALUE));
// -2147483648
~~~

Đây là hành vi mặc định: `-MIN_VALUE` và `Math.abs(MIN_VALUE)` với số nguyên có thể wrap, **không tự ném ngoại lệ**.

Muốn kiểm tra:

~~~java
Math.negateExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

Từ Java 17, `Math.absExact` có thể dùng tương tự:

~~~java
Math.absExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

Với `long`, `Long.MIN_VALUE` là trường hợp biên tương ứng.

### Vì sao `Math.abs(value)` có thể nguy hiểm?

Một thuật toán tính chỉ số mảng hoặc hash bucket bằng:

~~~java
int index = Math.abs(hash) % capacity;
~~~

có thể trả kết quả âm nếu `hash == Integer.MIN_VALUE`, dù `capacity > 0`. Với bài toán chọn bucket có kích thước dương, có thể cân nhắc:

~~~java
int index = Math.floorMod(hash, capacity);
~~~

Khi `capacity > 0`, `floorMod` trả số dư trong miền từ `0` đến `capacity - 1`. Nếu `capacity == 0`, nó vẫn ném `ArithmeticException`; vì vậy cần kiểm tra bất biến `capacity > 0` trước.

## 12. `Math.toIntExact`: thu hẹp `long` thành `int` có kiểm tra

Ép kiểu `long` sang `int` thông thường **không báo lỗi khi mất bit cao**:

~~~java
long value = (long) Integer.MAX_VALUE + 1L;
int narrowed = (int) value;
System.out.println(narrowed);
// -2147483648
~~~

`Math.toIntExact(long)` kiểm tra xem giá trị `long` có thể biểu diễn dưới dạng `int` hay không.

~~~java
int ok = Math.toIntExact(42L); // 42
~~~

~~~java
int failed = Math.toIntExact(
        (long) Integer.MAX_VALUE + 1L);
// ArithmeticException.
~~~

Cách này đặc biệt có ích khi một API mới sử dụng `long`, còn hệ thống cũ nhận `int`; nếu không dùng exact conversion, việc cắt mất bit có thể dẫn tới chỉ số âm hoặc kích thước sai.

**Lưu ý:** `Math.toIntExact` không kiểm tra những điều kiện ứng dụng như “kết quả phải không âm” hay “không vượt kích thước mảng”; nó chỉ đảm bảo nằm trong miền `int`.

## 13. Tổng hợp phép số nguyên nào ném `ArithmeticException`?

| Biểu thức / API | Khi chia cho 0 | Khi overflow |
| --- | --- | --- |
| `int/long /` | Ném `ArithmeticException` | Riêng `MIN_VALUE / -1` không ném, trả MIN_VALUE |
| `int/long %` | Ném `ArithmeticException` | `MIN_VALUE % -1` trả 0 |
| `int/long +`, `-`, `*` | Không áp dụng | Wrap, không tự ném |
| `++`, `--` | Không áp dụng | Wrap, không tự ném |
| Unary `-` | Không áp dụng | `-MIN_VALUE` wrap |
| `Math.floorDiv`/`floorMod` | Ném `ArithmeticException` | Không bảo đảm kiểm tra tràn |
| `Math.addExact` | Không áp dụng | Ném `ArithmeticException` |
| `Math.subtractExact` | Không áp dụng | Ném `ArithmeticException` |
| `Math.multiplyExact` | Không áp dụng | Ném `ArithmeticException` |
| `Math.incrementExact`/`decrementExact` | Không áp dụng | Ném `ArithmeticException` |
| `Math.negateExact`/`absExact` | Không áp dụng | Ném `ArithmeticException` với MIN_VALUE |
| `Math.toIntExact` | Không áp dụng | Ném khi `long` ngoài miền `int` |

Không nên hiểu “exact” là mọi thuật toán bất kỳ đều có phiên bản mang tên `Exact` trong JDK 17. Các API trên có chức năng cụ thể; hãy kiểm tra tài liệu của JDK mục tiêu trước khi dùng một tên hàm chỉ vì có hậu tố giống nhau.

## 14. Số thực `float` và `double` chia cho 0 không giống số nguyên

`ArithmeticException` do mẫu số bằng `0` gắn với phép chia và phép `%` **kiểu số nguyên**. Với `float`/`double`, Java sử dụng các giá trị đặc biệt theo ngữ nghĩa IEEE 754, không tự ném lỗi chỉ vì chia cho `0.0`:

~~~java
System.out.println(1.0 / 0.0);                // Infinity
System.out.println(-1.0 / 0.0);               // -Infinity
System.out.println(0.0 / 0.0);                // NaN
System.out.println(Double.isNaN(1.0 % 0.0)); // true
~~~

Kiểu toán hạng quan trọng: `5 / 2` trả `2`, còn `5.0 / 2` trả `2.5`. `Double.isFinite(value)` giúp xác định kết quả hữu hạn trước khi đưa vào nghiệp vụ yêu cầu số thực hợp lệ.

**Không ép sang `double` chỉ để tránh ngoại lệ chia nguyên cho 0**: việc đó có thể âm thầm chuyển lỗi thành `Infinity`/`NaN` và làm sai tính toán phía sau. Bài về *phân biệt chia số thực cho 0 với chia số nguyên cho 0* phân tích sâu numeric promotion, dấu `-0.0`, phép `%` và kiểm thử các giá trị đặc biệt; trọng tâm bài hiện tại vẫn là phép số nguyên và `Math.*Exact`.

## 15. `BigInteger` và `BigDecimal` có liên quan gì?

`ArithmeticException` không chỉ do toán tử nguyên hoặc `Math.*Exact`. Một số API số học khác cũng sử dụng nó khi phép tính không hợp lệ hoặc không thể biểu diễn theo yêu cầu.

### `BigInteger`: không overflow theo miền int/long, vẫn không chia được cho 0

~~~java
java.math.BigInteger a =
        new java.math.BigInteger("999999999999999999999");

java.math.BigInteger b = a.multiply(a);
System.out.println(b.signum() > 0);
// true
~~~

`BigInteger` có độ chính xác nguyên theo nhu cầu thay vì bị giới hạn 32/64 bit, trong phạm vi tài nguyên bộ nhớ và giới hạn thực thi. Nhưng:

~~~java
java.math.BigInteger.TEN.divide(java.math.BigInteger.ZERO);
// ArithmeticException.
~~~

Không phải vì `BigInteger` lớn nên mọi phép toán đều hợp lệ.

### `BigDecimal`: phép chia chính xác có thể không có biểu diễn hữu hạn

~~~java
java.math.BigDecimal result =
        java.math.BigDecimal.ONE.divide(
                new java.math.BigDecimal("2"));

System.out.println(result); // 0.5
~~~

Nhưng:

~~~java
java.math.BigDecimal.ONE.divide(
        new java.math.BigDecimal("3"));
// ArithmeticException nếu yêu cầu kết quả chính xác
// mà thương có biểu diễn thập phân vô hạn.
~~~

Đây là trường hợp khác hẳn tràn số nguyên: `1 / 3` có khai triển thập phân không kết thúc. Dạng `BigDecimal.divide(BigDecimal)` không được cung cấp chiến lược làm tròn, nên nó ném `ArithmeticException` thay vì âm thầm tạo một số xấp xỉ.

Nếu hợp đồng chấp nhận làm tròn:

~~~java
java.math.BigDecimal rounded =
        java.math.BigDecimal.ONE.divide(
                new java.math.BigDecimal("3"),
                2,
                java.math.RoundingMode.HALF_UP);

System.out.println(rounded);
// 0.33
~~~

Cần quy định scale và rounding mode theo nghiệp vụ; không chọn `HALF_UP` vô điều kiện cho mọi bài toán tiền tệ. Chia cho `BigDecimal.ZERO` vẫn không hợp lệ.

## 16. Chương trình Java 17+ chạy độc lập

Tệp **`ArithmeticExactDemo.java`** dưới đây cho phép thấy rõ:

1. Phép chia/dư nguyên và quy tắc dấu.
2. Trường hợp `MIN_VALUE / -1` không ném lỗi.
3. Overflow mặc định của `+` và `*`.
4. Phép chia cho 0 ném `ArithmeticException`.
5. Các `Math.*Exact` ném ngoại lệ khi vượt miền.
6. Ép kiểu thu hẹp khác `Math.toIntExact`.
7. Số thực và BigDecimal có hành vi riêng.

Chương trình bắt **chỉ `ArithmeticException`** trong các ca cố ý gây lỗi, không dùng `catch (Throwable)`.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class ArithmeticExactDemo {

    public static void main(String[] args) {
        System.out.println("== integer division ==");
        System.out.println("7 / 3=" + (7 / 3));
        System.out.println("-7 / 3=" + (-7 / 3));
        System.out.println("-7 % 3=" + (-7 % 3));
        System.out.println("floorDiv=" + Math.floorDiv(-7, 3));
        System.out.println("floorMod=" + Math.floorMod(-7, 3));
        System.out.println("int MIN / -1="
                + (Integer.MIN_VALUE / -1));
        System.out.println("long MIN / -1="
                + (Long.MIN_VALUE / -1L));

        System.out.println("== ordinary overflow ==");
        System.out.println("add wraps="
                + (Integer.MAX_VALUE + 1));
        System.out.println("multiply wraps="
                + (50_000 * 50_000));
        System.out.println("abs MIN="
                + Math.abs(Integer.MIN_VALUE));

        System.out.println("== division by zero ==");
        attempt("int / zero", () -> {
            int zero = 0;
            System.out.println(10 / zero);
        });
        attempt("int % zero", () -> {
            int zero = 0;
            System.out.println(10 % zero);
        });
        attempt("long / zero", () -> {
            long zero = 0L;
            System.out.println(10L / zero);
        });
        attempt("floorDiv zero", () -> Math.floorDiv(7, 0));

        System.out.println("== exact operations ==");
        System.out.println("addExact valid="
                + Math.addExact(20, 22));
        attempt("addExact", () ->
                Math.addExact(Integer.MAX_VALUE, 1));
        attempt("subtractExact", () ->
                Math.subtractExact(Integer.MIN_VALUE, 1));
        attempt("multiplyExact", () ->
                Math.multiplyExact(50_000, 50_000));
        attempt("long multiplyExact", () ->
                Math.multiplyExact(Long.MAX_VALUE, 2L));
        attempt("incrementExact", () ->
                Math.incrementExact(Integer.MAX_VALUE));
        attempt("decrementExact", () ->
                Math.decrementExact(Integer.MIN_VALUE));
        attempt("negateExact", () ->
                Math.negateExact(Integer.MIN_VALUE));
        attempt("absExact", () ->
                Math.absExact(Integer.MIN_VALUE));

        System.out.println("== long to int ==");
        long outsideInt = (long) Integer.MAX_VALUE + 1L;
        System.out.println("cast wraps=" + (int) outsideInt);
        System.out.println("toIntExact valid="
                + Math.toIntExact(42L));
        attempt("toIntExact", () ->
                Math.toIntExact(outsideInt));

        System.out.println("== floating point ==");
        System.out.println("double / zero=" + (1.0 / 0.0));
        System.out.println("double 0/0 NaN="
                + Double.isNaN(0.0 / 0.0));
        System.out.println("double % zero NaN="
                + Double.isNaN(1.0 % 0.0));

        System.out.println("== big numbers ==");
        attempt("BigInteger divide zero", () ->
                BigInteger.TEN.divide(BigInteger.ZERO));
        attempt("BigDecimal exact 1/3", () ->
                BigDecimal.ONE.divide(new BigDecimal("3")));
        System.out.println("BigDecimal rounded="
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"),
                        2,
                        RoundingMode.HALF_UP));
    }

    static void attempt(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + " => OK");
        } catch (ArithmeticException e) {
            System.out.println(
                    label + " => ArithmeticException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ArithmeticExactDemo.java
java ArithmeticExactDemo
~~~

**Stdout xác định cho Java 17+:**

~~~text
== integer division ==
7 / 3=2
-7 / 3=-2
-7 % 3=-1
floorDiv=-3
floorMod=2
int MIN / -1=-2147483648
long MIN / -1=-9223372036854775808
== ordinary overflow ==
add wraps=-2147483648
multiply wraps=-1794967296
abs MIN=-2147483648
== division by zero ==
int / zero => ArithmeticException
int % zero => ArithmeticException
long / zero => ArithmeticException
floorDiv zero => ArithmeticException
== exact operations ==
addExact valid=42
addExact => ArithmeticException
subtractExact => ArithmeticException
multiplyExact => ArithmeticException
long multiplyExact => ArithmeticException
incrementExact => ArithmeticException
decrementExact => ArithmeticException
negateExact => ArithmeticException
absExact => ArithmeticException
== long to int ==
cast wraps=-2147483648
toIntExact valid=42
toIntExact => ArithmeticException
== floating point ==
double / zero=Infinity
double 0/0 NaN=true
double % zero NaN=true
== big numbers ==
BigInteger divide zero => ArithmeticException
BigDecimal exact 1/3 => ArithmeticException
BigDecimal rounded=0.33
~~~

### Vì sao helper `attempt` chỉ bắt `ArithmeticException`?

`attempt(String, Runnable)` dùng một callback `Runnable`, và `Runnable.run()` không khai báo checked exception. Những thao tác trong các lambda trên là những thao tác có thể ném unchecked `ArithmeticException` nên chúng vẫn hợp lệ.

Helper in **tên loại ngoại lệ** thay vì `e.getMessage()`, nhằm giữ ví dụ độc lập với khác biệt câu chữ trong thông điệp runtime.

Không nên sửa thành `catch (Exception e)` rồi xem mọi lỗi được bắt là lỗi số học: một `NullPointerException`, `IllegalArgumentException` hoặc một lỗi của code callback khác cũng có thể nằm dưới `Exception` nhưng cần chính sách khác.

### Vì sao `Math.absExact` hoạt động trong Java 17?

`Math.absExact` được cung cấp trong những JDK hiện đại, bao gồm Java 17, và cho phép phát hiện trường hợp trị tuyệt đối của `Integer.MIN_VALUE`/`Long.MIN_VALUE` không thể biểu diễn bằng kiểu tương ứng.

Khác với `Math.abs`, nó ném `ArithmeticException` cho trường hợp biên đó. Do vậy ví dụ có cả `Math.abs(Integer.MIN_VALUE)` và `Math.absExact(Integer.MIN_VALUE)` để làm rõ sự khác biệt.

### Vì sao `BigDecimal.ONE.divide(new BigDecimal("3"))` có lỗi?

API này đòi kết quả chính xác, nhưng `1/3` không có biểu diễn thập phân hữu hạn. Cần chọn phép chia có scale/rounding mode hoặc `MathContext` phù hợp nếu ứng dụng chấp nhận kết quả làm tròn. Lỗi này **không phải overflow của kiểu `int`**.

## 17. Cách kiểm tra trước khi chia số nguyên

Nếu số chia đến từ input bên ngoài, có thể kiểm tra sớm:

~~~java
static int safeQuotient(int dividend, int divisor) {
    if (divisor == 0) {
        throw new IllegalArgumentException(
                "divisor must not be zero");
    }
    return dividend / divisor;
}
~~~

Hàm này chuyển từ một lỗi phép toán `ArithmeticException` thành một lỗi **tiền điều kiện `IllegalArgumentException`** có ngữ nghĩa rõ hơn khi mẫu số là đối số API.

Tuy nhiên `safeQuotient(Integer.MIN_VALUE, -1)` vẫn trả `Integer.MIN_VALUE`. Nếu cần **chính xác cả về tràn chia**, bổ sung kiểm tra trường hợp đó (như `divideSafely` ở phần 5).

### Nên precondition hay catch exception?

Không có một quy tắc duy nhất, nhưng thường:

- Nếu `divisor == 0` là **dữ liệu không hợp lệ có thể biết từ trước**, kiểm tra trước giúp báo lỗi đúng hợp đồng.
- Nếu bạn đang xây API thực hiện phép toán và chủ động muốn giữ ngữ nghĩa Java, có thể để `ArithmeticException` truyền ra.
- Nếu cần fallback nghiệp vụ, chỉ thực hiện khi fallback **được thiết kế và có ý nghĩa**.
- Nếu tính toán liên quan giao dịch hoặc cập nhật trạng thái, tránh vừa thay đổi dữ liệu vừa chỉ bắt lỗi cuối cùng mà không rollback/khôi phục đúng cách.

Không bắt lỗi rồi trả `0` tùy tiện, vì `0` có thể là một kết quả hợp lệ và việc che lỗi có thể dẫn đến mất tính chính xác của dữ liệu.

## 18. Thiết kế API phép toán exact với lỗi rõ ràng

Một helper kiểm tra số lượng trước khi cấp phát:

~~~java
static int checkedArrayLength(
        int records, int elementsPerRecord) {
    if (records < 0 || elementsPerRecord < 0) {
        throw new IllegalArgumentException("negative quantity");
    }
    int total = Math.multiplyExact(records, elementsPerRecord);
    if (total > 1_000_000) {
        throw new IllegalArgumentException(
                "too many elements");
    }
    return total;
}
~~~

Đây là phương thức Java hợp lệ. Nó có ba trường hợp:

1. Giá trị âm → lỗi tiền điều kiện `IllegalArgumentException`.
2. Phép nhân overflow → `ArithmeticException` từ `Math.multiplyExact`.
3. Kết quả đúng về số học nhưng vượt quota ứng dụng → `IllegalArgumentException` với message về giới hạn.

Đây là ví dụ quan trọng về phân biệt **độ đúng phép toán** với **hợp lệ theo quy tắc nghiệp vụ**. `Math.multiplyExact` không thể tự quyết định một request có vượt hạn mức tài nguyên của chương trình hay không.

### Bọc lỗi ở ranh giới nghiệp vụ khi có ích

~~~java
static int calculateRequiredSlots(
        int groups, int slotsPerGroup) {
    try {
        return Math.multiplyExact(groups, slotsPerGroup);
    } catch (ArithmeticException cause) {
        throw new IllegalArgumentException(
                "requested slot count is too large", cause);
    }
}
~~~

Mã này chuyển overflow thành một lỗi đầu vào tại ranh giới cụ thể và **giữ cause** để điều tra. Chỉ chọn cách bọc này khi overflow thực sự có ý nghĩa “request quá lớn” trong hợp đồng, không phải lỗi lập trình mà ứng dụng muốn phát hiện bằng một handler khác.

Nếu caller cần nhận trực tiếp `ArithmeticException`, cho nó lan truyền cũng có thể là lựa chọn phù hợp.

## 19. Những lỗi phổ biến khi dùng exact arithmetic

### 19.1. Nghĩ rằng `int` overflow luôn ném `ArithmeticException`

Sai. `Integer.MAX_VALUE + 1`, `Integer.MIN_VALUE - 1` và `50_000 * 50_000` mặc định wrap.

### 19.2. Nghĩ `MIN_VALUE / -1` ném overflow

Sai trong toán tử chia nguyên Java. Đây là trường hợp đặc biệt được xác định và trả MIN_VALUE. Nếu cần báo lỗi, tự kiểm tra điều kiện này trong Java 17.

### 19.3. Thấy `Math.floorDiv` rồi cho rằng nó phát hiện mọi overflow

Sai. `floorDiv` phục vụ quy tắc làm tròn xuống, không phải một họ API exact overflow checking.

### 19.4. Dùng `Math.abs` để đảm bảo số không âm

Sai khi input là `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`. Dùng `Math.absExact` khi cần phát hiện trường hợp không thể biểu diễn.

### 19.5. Nghĩ `Math.toIntExact` giống cast `(int)`

Sai. Cast có thể mất bit và trả giá trị khác hẳn; `toIntExact` ném `ArithmeticException` khi ngoài miền.

### 19.6. Ép sang long sau khi đã nhân int

Sai. `long total = a * b;` thực hiện nhân `int` trước nếu cả hai toán hạng là `int`. Ép một toán hạng **trước** phép nhân hoặc dùng `Math.multiplyExact` với kiểu mong muốn.

### 19.7. Dùng số thực để né chia cho 0

`double` chia cho `0.0` có thể cho `Infinity`/`NaN` chứ không ném. Điều đó không bảo đảm kết quả nghiệp vụ hợp lệ.

### 19.8. Dùng `%` như modulo luôn không âm

Sai với số bị chia âm. Dùng `Math.floorMod` với số chia dương nếu cần số dư không âm theo quy ước floor.

### 19.9. Cho rằng mọi `ArithmeticException` đều do chia cho 0

Sai. Exact arithmetic, thu hẹp kiểu, `BigInteger` và `BigDecimal` có thể gây `ArithmeticException` vì những điều kiện khác.

### 19.10. Bắt lỗi rồi trả 0 trong mọi tình huống

Có thể che lỗi dữ liệu, biến một phép tính không xác định thành kết quả dường như hợp lệ. Fallback phải thuộc hợp đồng.

### 19.11. Dùng message để xác định kiểu lỗi

Không nên viết `if (e.getMessage().equals("/ by zero"))`. Message không phải mã lỗi ổn định và có thể null. Nếu cần phân loại chính xác, kiểm tra precondition hoặc dùng loại lỗi miền/mã lỗi có cấu trúc.

### 19.12. Bắt `Exception` thay vì `ArithmeticException` mà không có lý do

Handler rộng có thể nuốt các lỗi không liên quan và làm việc chẩn đoán kém chính xác.

### 19.13. Quên kiểm tra số âm trước khi tính kích thước

`Math.multiplyExact(-2, 10)` trả `-20` vì phép toán **không overflow**. Nó không tự xác định số lượng âm là không hợp lệ. Phải kiểm tra invariant ứng dụng riêng.

### 19.14. Quên giới hạn tài nguyên dù phép nhân exact thành công

Một kết quả có thể nằm trong `int` nhưng vẫn quá lớn để cấp phát mảng hoặc xử lý an toàn. Exact chỉ bảo đảm miền số học, không bảo đảm bộ nhớ.

### 19.15. Nghĩ `BigInteger` hoặc `BigDecimal` không bao giờ ném lỗi số học

Sai. Chia cho 0 và phép chia `BigDecimal` không có kết quả thập phân hữu hạn khi thiếu rounding policy đều có thể ném `ArithmeticException`.

## 20. Các trường hợp biên cần có trong bài kiểm thử

Một bộ kiểm thử tốt nên có:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| `10 / 2` | Trả `5` |
| `10 / 0` | `ArithmeticException` |
| `10 % 0` | `ArithmeticException` |
| `10L / 0L` | `ArithmeticException` |
| `Integer.MIN_VALUE / -1` | Không throw, trả MIN_VALUE |
| `-7 / 3` | `-2`, truncate toward zero |
| `-7 % 3` | `-1` |
| `Math.floorDiv(-7,3)` | `-3` |
| `Math.floorMod(-7,3)` | `2` |
| `Integer.MAX_VALUE + 1` | Wrap thành MIN_VALUE |
| `Math.addExact(MAX,1)` | `ArithmeticException` |
| `Math.subtractExact(MIN,1)` | `ArithmeticException` |
| `Math.multiplyExact(50000,50000)` | `ArithmeticException` |
| `Math.negateExact(MIN)` | `ArithmeticException` |
| `Math.absExact(MIN)` | `ArithmeticException` |
| `Math.toIntExact(MAX+1L)` | `ArithmeticException` |
| `1.0 / 0.0` | `Infinity`, không ném ArithmeticException |
| `0.0 / 0.0` | `NaN` |
| `BigInteger.TEN.divide(ZERO)` | `ArithmeticException` |
| `BigDecimal.ONE.divide(3)` | `ArithmeticException` nếu cần kết quả chính xác vô hạn |
| `BigDecimal.ONE.divide(3,2,HALF_UP)` | `0.33` |

Khi viết unit test, kiểm tra exception **theo loại và điều kiện**, không bắt buộc cố định message của JDK. Chẳng hạn với JUnit 5:

~~~java
assertThrows(ArithmeticException.class,
        () -> Math.addExact(Integer.MAX_VALUE, 1));
~~~

Đây là **mảnh minh họa phụ thuộc thư viện JUnit 5**, không nằm trong chương trình `ArithmeticExactDemo.java` độc lập; chỉ sử dụng nếu dự án đã thiết lập JUnit.

## 21. Câu hỏi tự kiểm tra

1. `ArithmeticException` là checked hay unchecked? Nó kế thừa lớp nào?
2. Tại sao `int a = 10 / 0` có thể gây `ArithmeticException`?
3. `10 % 0` có hợp lệ không?
4. Phép chia `long` cho `0L` có giống chia `int` cho 0 không?
5. `7 / 3` và `-7 / 3` lần lượt trả gì?
6. Vì sao `-7 % 3` trả `-1`?
7. `Math.floorDiv(-7,3)` khác `-7/3` như thế nào?
8. `Math.floorMod(-7,3)` trả gì?
9. `Integer.MIN_VALUE / -1` ném lỗi hay trả một giá trị?
10. `Long.MIN_VALUE / -1L` có hành vi biên tương tự không?
11. Phép `Integer.MAX_VALUE + 1` mặc định có ném lỗi không?
12. `Math.addExact(Integer.MAX_VALUE,1)` có hành vi gì?
13. Khi nào `Math.subtractExact` ném lỗi?
14. Vì sao `50_000 * 50_000` cho giá trị `int` âm?
15. `Math.multiplyExact(50_000,50_000)` có trả cùng giá trị âm đó không?
16. `Math.incrementExact(Integer.MAX_VALUE)` làm gì?
17. Vì sao `-Integer.MIN_VALUE` không trả số nguyên dương theo toán học?
18. `Math.absExact(Integer.MIN_VALUE)` làm gì?
19. Nếu `long x = Integer.MAX_VALUE + 1L`, ép `(int)x` có báo lỗi không?
20. `Math.toIntExact(x)` khác cast ở điểm nào?
21. `1.0 / 0.0` có ném `ArithmeticException` không? Kết quả là gì?
22. `0.0 / 0.0` trả loại giá trị số thực đặc biệt nào?
23. `BigInteger` có còn ném `ArithmeticException` không? Nêu ví dụ.
24. Vì sao `BigDecimal.ONE.divide(new BigDecimal("3"))` có thể ném lỗi?
25. Khi thiết kế API chia số nguyên, nên kiểm tra `divisor == 0` trước khi tính không?
26. `Math.multiplyExact(-2,10)` có tự từ chối số lượng âm không?
27. Vì sao phép nhân exact thành công chưa bảo đảm cấp phát mảng an toàn?
28. Có nên mặc định `catch (ArithmeticException)` và trả `0` không?
29. `Math.floorDiv(x,0)` có khác toán tử nguyên `x/0` về lỗi không?
30. Khi kiểm thử, vì sao không nên phụ thuộc tuyệt đối vào `getMessage()` của `ArithmeticException`?

### Gợi ý đáp án

1. Unchecked, kế thừa `RuntimeException`.
2. Số chia bằng 0 trong phép chia nguyên là điều kiện không hợp lệ.
3. Không; ném `ArithmeticException`.
4. Có, với toán hạng nguyên.
5. `2` và `-2`.
6. Số dư theo toán tử `%` của Java mang dấu số bị chia.
7. `floorDiv` làm tròn xuống `-3`, còn `/` làm tròn về 0 thành `-2`.
8. `2`.
9. Trả `Integer.MIN_VALUE`, không ném.
10. Có; trả `Long.MIN_VALUE`.
11. Không; nó wrap.
12. Ném `ArithmeticException` vì overflow.
13. Khi hiệu vượt miền kiểu kết quả.
14. Tích toán học vượt `Integer.MAX_VALUE` nên wrap theo 32 bit.
15. Không; nó ném `ArithmeticException`.
16. Ném `ArithmeticException`.
17. Giá trị dương tương ứng vượt `Integer.MAX_VALUE`.
18. Ném `ArithmeticException`.
19. Không; cast có thể cắt bit cao.
20. `toIntExact` kiểm tra miền `int` và ném khi ngoài miền.
21. Không; kết quả `Infinity`.
22. `NaN`.
23. Có, ví dụ `BigInteger.TEN.divide(BigInteger.ZERO)`.
24. `1/3` không có biểu diễn thập phân hữu hạn khi yêu cầu phép chia chính xác không làm tròn.
25. Có thể, nếu muốn thông báo lỗi tiền điều kiện rõ ràng; còn hành vi phép toán Java tự ném nếu mẫu số 0.
26. Không; `-20` không overflow. Phải kiểm tra bất biến dữ liệu riêng.
27. Kết quả có thể vượt quota bộ nhớ hoặc ràng buộc API.
28. Không, chỉ khi fallback 0 được hợp đồng cho phép.
29. Cả hai ném `ArithmeticException` với số chia nguyên bằng 0.
30. Vì message không phải hợp đồng lỗi ổn định để xử lý máy; nên kiểm tra loại lỗi và điều kiện.

## 22. Ghi nhớ

**`ArithmeticException` trong Java Core chủ yếu xuất hiện khi chia/lấy dư số nguyên cho 0 và khi các API exact phát hiện phép toán không thể biểu diễn chính xác trong miền số nguyên.** Các toán tử `+`, `-`, `*`, `++`, `--` thông thường không tự báo overflow; `Integer.MIN_VALUE / -1` cũng không ném mà trả MIN_VALUE. Dùng `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact`, `absExact` và `toIntExact` khi cần phát hiện tràn số. Hiểu rõ khác biệt giữa `/`, `%`, `floorDiv` và `floorMod` với số âm, cùng hành vi `Infinity`/`NaN` của `float`/`double`. Khi thiết kế API, hãy kết hợp kiểm tra tiền điều kiện và bất biến nghiệp vụ; không bắt lỗi số học rồi trả một giá trị giả định nếu chưa có chính sách rõ ràng.