# Overload int, long và biên nhỏ nhất, lớn nhất trong số học kiểm tra tràn

## Mục tiêu

Trong Java, `int` và `long` là hai kiểu số nguyên có dấu, kích thước cố định. Nếu cộng, trừ, nhân hoặc đổi dấu làm kết quả toán học vượt phạm vi kiểu đích, toán tử số nguyên thông thường **không tự ném ngoại lệ tràn số**; giá trị bị tính theo quy tắc số học hai bù (two's complement), có thể chuyển từ dương lớn sang âm hoặc ngược lại. Điều này nguy hiểm với số lượng, chỉ số, độ dài, thời hạn và các phép tính tiền theo đơn vị nhỏ nhất.

Các hàm **checked arithmetic** của `java.lang.Math` và `java.lang.StrictMath` như `addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact` và `negateExact` trả về kết quả khi biểu diễn được, hoặc ném **`ArithmeticException`** nếu vượt phạm vi. **Chọn đúng overload `int` hay `long` là một phần của tính đúng đắn**: cùng phép nhân `50_000 × 50_000` có thể tràn `int` nhưng vẫn nằm trong `long`.

Sau bài này, bạn sẽ:

1. Biết biên chính xác `MIN_VALUE`, `MAX_VALUE` của `int` và `long`.
2. Phân biệt giá trị toán học với kết quả sau overflow của toán tử `+`, `-`, `*`, `++`, `--` và phép đổi dấu.
3. Nắm overload `int`, `long` của các phương thức `Math.*Exact`, đặc biệt `multiplyExact(long,int)`.
4. Hiểu **method overload resolution**, numeric promotion, hậu tố `L` và lý do **ép kiểu sau phép tính là quá muộn**.
5. Xử lý các điểm bất đối xứng: `MIN_VALUE` không có trị tuyệt đối hoặc số đối tương ứng trong cùng kiểu, còn `MAX_VALUE` không thể tăng thêm 1.
6. Đọc đúng behavior của `Math.absExact` (từ Java 15), `Math.toIntExact`, phép chia `MIN_VALUE / -1` và `Math.divideExact` (từ Java 18).
7. Chọn `Math.multiplyFull` hoặc `BigInteger` khi đích phải rộng hơn kết quả trả về của một overload `*Exact`.
8. Biên dịch/chạy ví dụ Java 17+ có kiểm tra cả kết quả đúng và các ngoại lệ ở biên.

**Ngữ cảnh Java 14:** Những phương thức `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact` và `toIntExact` đã tồn tại trước Java 14. Trong `StrictMath`, `incrementExact`, `decrementExact` và `negateExact` có mốc **Since: 14**, nhưng các hàm `StrictMath.addExact/subtractExact/multiplyExact` không phải mới toàn bộ ở Java 14. Các API này **vẫn hợp lệ trên Java hiện đại**. Bài tập chọn **Java 17** làm baseline, không dùng tính năng preview và không gọi nhầm API chỉ có từ JDK 18.

## 1. Phạm vi của int và long

Java dùng số nguyên có dấu theo biểu diễn two's complement:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất | Hằng số Java |
|---|---:|---:|---:|---|
| `int` | 32 | −2,147,483,648 | 2,147,483,647 | `Integer.MIN_VALUE` và `Integer.MAX_VALUE` |
| `long` | 64 | −9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 | `Long.MIN_VALUE` và `Long.MAX_VALUE` |

Với `n` bit, khoảng giá trị là:

~~~text
MIN = -(2^(n-1))
MAX =  (2^(n-1)) - 1
~~~

**Phạm vi bất đối xứng**: độ lớn của `MIN_VALUE` nhiều hơn `MAX_VALUE` đúng 1. Ví dụ:

~~~java
int min = Integer.MIN_VALUE;  // -2147483648
int max = Integer.MAX_VALUE;  //  2147483647
long bigMin = Long.MIN_VALUE;
long bigMax = Long.MAX_VALUE;
~~~

Điều này dẫn đến hai trường hợp dễ sai:

- `Math.negateExact(Integer.MIN_VALUE)` phải ném lỗi vì `+2_147_483_648` **không chứa được trong `int`**.
- `Math.absExact(Long.MIN_VALUE)` phải ném lỗi vì trị tuyệt đối `+9_223_372_036_854_775_808` **không chứa được trong `long`**.

Đừng gán `Integer.MIN_VALUE` nghĩa là “số âm nhỏ nhất về độ lớn”. Trong thuật ngữ thứ tự số nguyên, đó là **giá trị nhỏ nhất — âm nhất**.

### 1.1. Hậu tố L và literal có phân tách hàng nghìn

~~~java
int count = 2_000_000_000;
long quantity = 2_000_000_000L;
long max = Long.MAX_VALUE;
~~~

Dấu gạch dưới là cách viết literal cho dễ đọc, **không đổi giá trị**. Hậu tố `L` cho biết literal kiểu `long`; nên dùng chữ `L` hoa để tránh nhầm với số `1`.

Không tự ghi `9_223_372_036_854_775_808L` thành một giá trị dương `long`: nó vượt `Long.MAX_VALUE`. Hãy dùng `Long.MIN_VALUE` khi cần biên âm hoặc dùng `BigInteger` nếu muốn biểu diễn độ lớn ngoài `long`.

## 2. Toán tử thường không báo tràn

Xem:

~~~java
int max = Integer.MAX_VALUE;
int wrapped = max + 1;
System.out.println(wrapped);  // -2147483648
~~~

Khi phép cộng `int` tạo ra kết quả toán học ngoài phạm vi, Java không ném `ArithmeticException` cho **overflow**. Kết quả bị rút về 32 bit, được hiểu theo two's complement. Tương tự:

~~~java
int min = Integer.MIN_VALUE;
System.out.println(min - 1);  // 2147483647
System.out.println(-min);     // -2147483648
~~~

`-Integer.MIN_VALUE` vẫn là chính `Integer.MIN_VALUE`, không phải một số dương. Với `long`, `Long.MAX_VALUE + 1L` cũng quay về `Long.MIN_VALUE`.

Điều này khác với **chia số nguyên cho 0**, khi toán tử `/` và `%` ném `ArithmeticException`. Đừng vì đã quen ngoại lệ phép chia cho 0 mà cho rằng `+`, `-`, `*` sẽ tự kiểm tra overflow.

### 2.1. Biểu thức int vẫn là int dù được gán vào long

~~~java
int a = 50_000;
int b = 50_000;
long wrong = a * b;          // -1794967296 (int bị tràn trước)
long correct = (long) a * b; // 2500000000
~~~

Cả hai biến có kiểu `long` nhưng không đồng nghĩa:

1. `a * b` dùng hai toán hạng `int`, nên phép nhân được thực hiện theo **`int`** trước.
2. Khi kết quả `int` đã tràn, phép gán mới mở rộng giá trị sai đó sang `long`.
3. `(long) a * b` mở rộng **một toán hạng trước phép nhân**, nên toàn phép nhân dùng `long`.

Đây là **numeric promotion**, không phải một cơ chế checked arithmetic. Nếu kết quả cũng có thể vượt `long`, bạn vẫn cần `Math.multiplyExact(...)` hoặc `BigInteger`.

## 3. Các overload *Exact của Math

Những chữ ký chính trong `java.lang.Math`:

| Nhóm | Overload `int` | Overload `long` | Điều kiện lỗi |
|---|---|---|---|
| Cộng | `int addExact(int,int)` | `long addExact(long,long)` | Tổng vượt khoảng kiểu trả về |
| Trừ | `int subtractExact(int,int)` | `long subtractExact(long,long)` | Hiệu vượt khoảng kiểu trả về |
| Nhân | `int multiplyExact(int,int)` | `long multiplyExact(long,long)` | Tích vượt khoảng kiểu trả về |
| Nhân hỗn hợp | — | `long multiplyExact(long,int)` | Tích vượt `long` |
| Tăng 1 | `int incrementExact(int)` | `long incrementExact(long)` | Giá trị hiện tại là `MAX_VALUE` |
| Giảm 1 | `int decrementExact(int)` | `long decrementExact(long)` | Giá trị hiện tại là `MIN_VALUE` |
| Đổi dấu | `int negateExact(int)` | `long negateExact(long)` | Giá trị hiện tại là `MIN_VALUE` |
| Trị tuyệt đối | `int absExact(int)` | `long absExact(long)` | Đối số là `MIN_VALUE`; API từ JDK 15 |

Đổi từ `long` sang `int` có một phương thức riêng:

~~~java
int small = Math.toIntExact(1_000L);
~~~

`Math.toIntExact(long)` **không phải** overload của `addExact`; nó xác nhận một giá trị `long` nằm trong khoảng `int` rồi mới chuyển kiểu.

**Không có overload `addExact(int,long)` riêng** và không có `multiplyExact(int,long)` riêng. Lúc cần, Java sẽ chọn overload có thể nhận các tham số sau khi mở rộng primitive type theo quy tắc resolution.

### 3.1. Khi nào ngoại lệ xảy ra?

~~~java
Math.addExact(100, 200);                    // int 300
Math.addExact(100L, 200L);                  // long 300
Math.subtractExact(-10, 5);                // int -15
Math.multiplyExact(1_000L, 3);             // long 3000
Math.incrementExact(9);                    // int 10
Math.decrementExact(9L);                   // long 8
Math.negateExact(-9);                      // int 9
Math.toIntExact(2_147_483_647L);           // int MAX_VALUE
~~~

Các dòng trên là **đoạn minh họa**, đặt trong method nếu muốn chạy.

Nếu kết quả biểu diễn được, không có ngoại lệ. Nếu vượt biên, phương thức ném `ArithmeticException` **ngay tại phép tính**: nó không trả một giá trị sai rồi mới báo lỗi.

### 3.2. Những API không nên nhầm

- `Math.max(a,b)` và `Math.min(a,b)` chọn phần tử **lớn hơn/nhỏ hơn**; chúng **không kiểm tra tràn số**.
- `Integer.MAX_VALUE`/`Long.MIN_VALUE` là **hằng số biên**, không phải phương thức.
- `Math.multiplyFull(int,int)` trả về **`long`** chứa toàn bộ tích của hai `int`, vì tích của hai số 32 bit luôn vừa phạm vi `long`. Nó **không** ném lỗi tràn `int`, vì kiểu trả về rộng hơn.
- `Math.multiplyHigh(long,long)` cho phần 64 bit cao của một tích 128 bit, **không** thay thế `Math.multiplyExact` khi cần kết quả `long` không tràn.
- `BigInteger` xử lý số nguyên tùy ý độ lớn, phù hợp khi kết quả toán học có thể vượt cả `long`.
- `Math.divideExact` chỉ có từ **JDK 18**; không viết nó vào code yêu cầu biên dịch với `--release 17`.

## 4. Java chọn overload nào?

### 4.1. Hai int → overload int

~~~java
int result = Math.addExact(20, 30);     // addExact(int,int)
int product = Math.multiplyExact(6, 7); // multiplyExact(int,int)
~~~

Đối số là `int` nên overload `int,int` phù hợp nhất. **Kiểu biến nhận kết quả không tự quyết định chọn overload**:

~~~java
long stillIntComputation = Math.multiplyExact(50_000, 50_000);
~~~

Dòng trên **ném `ArithmeticException`**, dù đích có kiểu `long`, vì compiler chọn `multiplyExact(int,int)` **trước** khi gán.

### 4.2. Ít nhất một long → overload long

~~~java
long one = Math.addExact(20L, 30L);  // addExact(long,long)
long two = Math.addExact(20, 30L);   // int 20 mở rộng thành long
long three = Math.multiplyExact(3L, 7); // multiplyExact(long,int)
long four = Math.multiplyExact(3, 7L);  // multiplyExact(long,long)
~~~

Phân tích:

- `Math.addExact(20,30L)`: không có overload `(int,long)`; `20` được mở rộng thành `long` để dùng `addExact(long,long)`.
- `Math.multiplyExact(3L,7)`: có đúng overload `(long,int)`, được chọn.
- `Math.multiplyExact(3,7L)`: overload `(long,int)` **không thể nhận đối số thứ hai long bằng cách narrowing xuống int**; compiler chọn `(long,long)` và mở rộng `3`.
- `Math.multiplyExact(3,7)` chọn overload `(int,int)`, **trả int**.

Cả overload `(long,int)` và `(long,long)` đều trả `long`. Việc chọn overload dựa trên **kiểu của đối số tại compile time**, không dựa trên việc kết quả sau cùng “có thể nhỏ”.

### 4.3. Cast trước phép tính, không sau phép tính

~~~java
int a = 50_000;
int b = 50_000;

// Tràn int rồi mới cast: KHÔNG ĐÚNG.
long wrong1 = (long) (a * b);

// Checked int sẽ ném lỗi: đúng nếu nghiệp vụ đòi kết quả int.
long checkedIntFirst = Math.multiplyExact(a, b);

// Kiểm tra bằng long, không làm mất dữ liệu trung gian:
long safe = Math.multiplyExact((long) a, b);

// Cũng có thể dùng phương thức tạo tích int*int chính xác thành long:
long full = Math.multiplyFull(a, b);
~~~

`checkedIntFirst` là ví dụ **cố ý ném ArithmeticException** với các giá trị trên, nên không chạy nguyên khối nếu bạn muốn in `safe` ở các dòng sau. Trong ứng dụng thật, chọn một chính sách:

- **Cần đúng kiểu `int`:** dùng overload `int,int` và **chấp nhận ArithmeticException** khi tràn.
- **Cần kết quả vượt int nhưng nằm trong long:** mở rộng **trước** khi gọi exact operation hoặc dùng `multiplyFull`.
- **Có thể vượt cả long:** dùng `BigInteger` và kiểm tra giới hạn nghiệp vụ riêng.

### 4.4. byte, short, char và wrapper

`byte`, `short` và `char` thường được **widening** thành `int` khi gọi phương thức exact. Ví dụ:

~~~java
short a = 100;
short b = 200;
int total = Math.addExact(a, b); // int 300
~~~

Với wrapper như `Integer` hoặc `Long`, Java có thể **unbox** đối số khi chọn primitive overload. Nhưng nếu wrapper là `null`, thao tác unbox có thể ném **`NullPointerException`**, không phải `ArithmeticException`; kiểm tra null ở ranh giới dữ liệu.

Đừng dùng overload resolution như một hình thức validation: kiểu dữ liệu và miền giá trị nghiệp vụ vẫn cần được kiểm tra rõ.

## 5. Bảng biên nhỏ nhất/lớn nhất

| Phép tính | Kết quả mong đợi | Giải thích |
|---|---|---|
| `Math.addExact(Integer.MAX_VALUE, 0)` | `Integer.MAX_VALUE` | Vẫn trong phạm vi |
| `Math.addExact(Integer.MAX_VALUE, 1)` | `ArithmeticException` | Vượt biên dương int |
| `Math.subtractExact(Integer.MIN_VALUE, 1)` | `ArithmeticException` | Vượt biên âm int |
| `Math.incrementExact(Integer.MAX_VALUE)` | `ArithmeticException` | Không thể tăng MAX |
| `Math.decrementExact(Integer.MIN_VALUE)` | `ArithmeticException` | Không thể giảm MIN |
| `Math.negateExact(Integer.MIN_VALUE)` | `ArithmeticException` | Không có số đối dương trong int |
| `Math.multiplyExact(50_000, 50_000)` | `ArithmeticException` | Tích 2.5 tỷ vượt int MAX |
| `Math.multiplyExact(50_000L, 50_000)` | `2_500_000_000L` | Nằm trong long |
| `Math.addExact(Long.MAX_VALUE, 1L)` | `ArithmeticException` | Vượt biên dương long |
| `Math.subtractExact(Long.MIN_VALUE, 1L)` | `ArithmeticException` | Vượt biên âm long |
| `Math.multiplyExact(Long.MAX_VALUE, 2L)` | `ArithmeticException` | Vượt long |
| `Math.negateExact(Long.MIN_VALUE)` | `ArithmeticException` | Không có số đối trong long |
| `Math.absExact(Integer.MIN_VALUE)` | `ArithmeticException` | Trị tuyệt đối vượt int MAX |
| `Math.toIntExact(2_147_483_648L)` | `ArithmeticException` | long không thể thu hẹp về int |
| `Math.multiplyFull(50_000,50_000)` | `2_500_000_000L` | Chính xác với kiểu đích long |

**Tính chất quan trọng:** overflow phụ thuộc vào **phạm vi của kiểu trả về**. Cùng tích hai số `50_000` là giá trị hợp lệ nếu lưu dưới `long` nhưng không hợp lệ nếu yêu cầu `int`.

### 5.1. Tràn có thể xảy ra cả ở cực âm

Không chỉ kiểm tra `MAX_VALUE`. Với phép trừ:

~~~java
Math.subtractExact(Integer.MIN_VALUE, -1); // MIN_VALUE + 1, hợp lệ
Math.subtractExact(Integer.MIN_VALUE, 1);  // ArithmeticException
~~~

Với phép cộng âm:

~~~java
Math.addExact(Integer.MIN_VALUE, -1);   // ArithmeticException
Math.addExact(Integer.MIN_VALUE, 1);    // MIN_VALUE + 1, hợp lệ
~~~

Với phép nhân âm:

~~~java
Math.multiplyExact(Long.MIN_VALUE, -1L); // ArithmeticException
Math.multiplyExact(Long.MIN_VALUE, 1L);  // hợp lệ
~~~

Không có công thức “chỉ khi hai số dương mới tràn”. Mỗi phép toán phải kiểm tra cả miền âm và dương.

## 6. Trường hợp đặc biệt: MIN_VALUE, abs, negate và chia -1

### 6.1. Phép đổi dấu

~~~java
int x = Integer.MIN_VALUE;
System.out.println(-x);                   // -2147483648
Math.negateExact(x);                      // ArithmeticException
~~~

Vì `-x` theo số học `int` thông thường quay vòng, nó vẫn âm. `Math.negateExact(x)` chủ động từ chối kết quả không biểu diễn được.

### 6.2. Giá trị tuyệt đối

~~~java
int x = Integer.MIN_VALUE;
System.out.println(Math.abs(x));          // -2147483648
Math.absExact(x);                         // ArithmeticException
~~~

`Math.absExact(int)` và `Math.absExact(long)` đã có từ **JDK 15** và đang được hỗ trợ trên JDK 17+. Vì vậy ví dụ chính dùng Java 17 có thể gọi `absExact`, nhưng **không được mô tả nó là tính năng mới của Java 14**.

Nếu bạn buộc chạy đúng Java 14, có thể kiểm tra `x == Integer.MIN_VALUE` trước `Math.abs(x)`, hoặc chuyển sang miền rộng hơn khi phù hợp:

~~~java
long positiveMagnitude = Math.abs((long) Integer.MIN_VALUE);
// 2147483648L: int MIN được mở rộng sang long TRƯỚC khi abs.
~~~

Chuyển `Long.MIN_VALUE` sang kiểu primitive số nguyên rộng hơn `long` không có sẵn; muốn trị tuyệt đối dương chính xác, dùng `BigInteger.valueOf(Long.MIN_VALUE).abs()`.

### 6.3. Chia nguyên MIN_VALUE / -1

Đây là **trường hợp dễ nhầm** trong Java:

~~~java
int q1 = Integer.MIN_VALUE / -1; // Integer.MIN_VALUE, KHÔNG ném lỗi
long q2 = Long.MIN_VALUE / -1L;  // Long.MIN_VALUE, KHÔNG ném lỗi
~~~

Kết quả toán học dương vượt phạm vi tương ứng, nhưng toán tử chia nguyên của Java trả lại `MIN_VALUE` mà **không ném ngoại lệ** theo Java Language Specification. **Chia cho 0** thì vẫn ném `ArithmeticException`.

Từ **JDK 18**, `Math.divideExact(int,int)` và `Math.divideExact(long,long)` được bổ sung để phát hiện trường hợp `MIN_VALUE / -1` (và chia 0). Chúng **không tồn tại trong Java 17**, nên đừng đặt `Math.divideExact` vào code biên dịch bằng `--release 17`.

Nếu ứng dụng dùng Java 17, có thể tự kiểm tra:

~~~java
static long divideChecked(long a, long b) {
    if (b == 0 || (a == Long.MIN_VALUE && b == -1)) {
        throw new ArithmeticException("division not representable");
    }
    return a / b;
}
~~~

Đây là **method minh họa** (không phải chương trình độc lập). Khi dùng JDK 18+ thật, nên cân nhắc `Math.divideExact` cho cùng ý nghĩa. Đừng gọi `Math.floorDiv` như một cách tự động phát hiện overflow ở `MIN/-1`; cách chia làm tròn khác không tự thay thế exact division.

## 7. toIntExact và vì sao cast có thể đánh mất thông tin

Ví dụ:

~~~java
long total = 2_147_483_648L;

int wrong = (int) total;          // -2147483648
int right = Math.toIntExact(total); // ArithmeticException
~~~

`(int) total` thực hiện **narrowing primitive conversion**, giữ phần bit thấp và có thể đổi ý nghĩa giá trị. `Math.toIntExact` kiểm tra miền rồi mới trả `int`.

Ứng dụng phù hợp:

- Chuyển độ dài `long` sang kích thước `int` mà code/format cũ yêu cầu.
- Chuyển tổng số lượng `long` về giá trị UI có giới hạn.
- Chuyển byte count/offset khi một API chỉ hỗ trợ `int`.

**Quan trọng:** `Math.toIntExact` chỉ kiểm tra phạm vi **kiểu số**, không kiểm tra điều kiện nghiệp vụ như “số lượng phải không âm”, “đơn giá phải là số dương” hoặc “một đơn hàng tối đa 10.000 sản phẩm”. Các điều kiện này phải được validate riêng.

Với phép nhân hai `int`:

~~~java
int quantity = 50_000;
int price = 50_000;

long totalCents = Math.multiplyExact((long) quantity, price);
int limited = Math.toIntExact(totalCents); // Ném lỗi nếu cần int.
~~~

Cách viết này tách **tính đúng kết quả toán học ở long** khỏi **kiểm tra xem kết quả có thể chứa trong int** hay không.

## 8. Ví dụ Java 17 hoàn chỉnh đã kiểm chứng

Chương trình bên dưới in **biên**, **overload đúng**, **tràn dự kiến**, **phép toán thường bị wrap** và **phương án mở rộng**. Không cần thư viện ngoài JDK.

### 8.1. Tạo ExactOverloadBoundsDemo.java

~~~java
import java.math.BigInteger;

public final class ExactOverloadBoundsDemo {
    private static void expectOverflow(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=NO_EXCEPTION");
        } catch (ArithmeticException ex) {
            System.out.println(name + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        System.out.println("intRange=" + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("longRange=" + Long.MIN_VALUE + ".." + Long.MAX_VALUE);

        System.out.println("intLast=" + Math.addExact(Integer.MAX_VALUE, 0));
        System.out.println("longLast=" + Math.addExact(Long.MAX_VALUE, 0L));
        System.out.println("widenedAdd=" + Math.addExact((long) Integer.MAX_VALUE, 1L));
        System.out.println("mixedMultiply=" + Math.multiplyExact(3L, 2));
        System.out.println("intProductAsLong=" + Math.multiplyFull(50_000, 50_000));
        System.out.println("strict14=" + StrictMath.incrementExact(40L));

        expectOverflow("intMaxAdd", () -> Math.addExact(Integer.MAX_VALUE, 1));
        expectOverflow("intMinSubtract", () -> Math.subtractExact(Integer.MIN_VALUE, 1));
        expectOverflow("longMaxAdd", () -> Math.addExact(Long.MAX_VALUE, 1L));
        expectOverflow("longMinSubtract", () -> Math.subtractExact(Long.MIN_VALUE, 1L));
        expectOverflow("intMultiply", () -> Math.multiplyExact(50_000, 50_000));
        expectOverflow("longMultiply", () -> Math.multiplyExact(Long.MAX_VALUE, 2L));
        expectOverflow("incrementMax", () -> Math.incrementExact(Integer.MAX_VALUE));
        expectOverflow("decrementMin", () -> Math.decrementExact(Long.MIN_VALUE));
        expectOverflow("negateMin", () -> Math.negateExact(Integer.MIN_VALUE));
        expectOverflow("absMin", () -> Math.absExact(Integer.MIN_VALUE));
        expectOverflow("narrowLong", () -> Math.toIntExact(2_147_483_648L));

        System.out.println("plainWrap=" + (Integer.MAX_VALUE + 1));
        System.out.println("tooLateCast=" + (long) (50_000 * 50_000));
        System.out.println("safeLongProduct=" + Math.multiplyExact(50_000L, 50_000));
        System.out.println("plainDivideMin=" + (Long.MIN_VALUE / -1L));
        System.out.println("plainAbsMin=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("bigBeyondLong=" +
                BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
    }
}
~~~

Lệnh chạy với **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 ExactOverloadBoundsDemo.java
java ExactOverloadBoundsDemo
~~~

### 8.2. Đầu ra thực tế

~~~text
intRange=-2147483648..2147483647
longRange=-9223372036854775808..9223372036854775807
intLast=2147483647
longLast=9223372036854775807
widenedAdd=2147483648
mixedMultiply=6
intProductAsLong=2500000000
strict14=41
intMaxAdd=ArithmeticException
intMinSubtract=ArithmeticException
longMaxAdd=ArithmeticException
longMinSubtract=ArithmeticException
intMultiply=ArithmeticException
longMultiply=ArithmeticException
incrementMax=ArithmeticException
decrementMin=ArithmeticException
negateMin=ArithmeticException
absMin=ArithmeticException
narrowLong=ArithmeticException
plainWrap=-2147483648
tooLateCast=-1794967296
safeLongProduct=2500000000
plainDivideMin=-9223372036854775808
plainAbsMin=-2147483648
bigBeyondLong=9223372036854775808
~~~

**Kết quả này đã được biên dịch bằng `javac --release 17` và chạy thực tế.** Các nhánh `expectOverflow` cố tình bắt `ArithmeticException` để chương trình vẫn tiếp tục thử các phép tính tiếp theo. Trong code production, đừng bắt ngoại lệ rồi im lặng bỏ qua; chính sách lỗi và thông điệp phản hồi phụ thuộc nghiệp vụ.

### 8.3. Phân tích các dòng cần nhớ

- `intLast` và `longLast`: cộng 0 đúng tại biên dương vẫn hợp lệ.
- `widenedAdd=2147483648`: mở rộng `Integer.MAX_VALUE` sang long **trước khi cộng 1**; kết quả vượt int nhưng nằm trong long.
- `mixedMultiply=6`: `multiplyExact(long,int)` trả long, không tạo ngoại lệ.
- `intProductAsLong=2500000000`: `multiplyFull(int,int)` trả long chứa đầy đủ tích.
- Các dòng `=ArithmeticException`: phép toán exact phát hiện vượt biên của kiểu đích.
- `plainWrap=-2147483648`: cộng thông thường bị wrap từ `Integer.MAX_VALUE`.
- `tooLateCast=-1794967296`: ép `(long)` **sau** khi nhân int không cứu được giá trị.
- `safeLongProduct=2500000000`: mở rộng toán hạng trước khi nhân giúp chọn overload trả long.
- `plainDivideMin`: trường hợp `Long.MIN_VALUE / -1L` không ném lỗi dù quotient toán học vượt long.
- `plainAbsMin`: `Math.abs(Integer.MIN_VALUE)` vẫn trả một số âm.
- `bigBeyondLong=9223372036854775808`: `BigInteger` biểu diễn được giá trị dương lớn hơn `Long.MAX_VALUE`.

## 9. Math và StrictMath trong ngữ cảnh Java 14

Một số phương thức exact xuất hiện ở cả `Math` và `StrictMath`, với hợp đồng overflow tương đương cho **integer operations**. `StrictMath` thường gắn với yêu cầu tính toán số thực tái lập theo tiêu chuẩn, nhưng điều đó **không khiến nó “chính xác hơn” `Math` cho phép cộng/trừ/nhân số nguyên**.

Mốc phiên bản có ý nghĩa khi học module Java 14:

| API | Mốc có từ | Ý nghĩa |
|---|---|---|
| `Math.addExact`/`subtractExact`/`multiplyExact(int,int)`/`multiplyExact(long,long)` | Java 8 | Checked arithmetic đã có trước Java 14 |
| `Math.multiplyExact(long,int)` | Java 9 | Overload nhân kết hợp long và int |
| `Math.incrementExact`/`decrementExact`/`negateExact` | Java 8 | Kiểm tra tràn với tăng/giảm/đổi dấu |
| `StrictMath.incrementExact`/`decrementExact`/`negateExact` | **Java 14** | Bổ sung các phương thức tương ứng vào `StrictMath` |
| `Math.absExact(int/long)` | Java 15 | Phát hiện trường hợp trị tuyệt đối của MIN |
| `Math.divideExact(int/long)` | Java 18 | Phát hiện overflow khi chia MIN cho -1 và chia 0 |

Các mốc này giúp không viết tài liệu sai: **bài học thuộc “Java 14” không có nghĩa mọi hàm được nhắc đến đều lần đầu xuất hiện ở Java 14**. Với code baseline Java 17, `Math.absExact` dùng được; `Math.divideExact` chưa dùng được. Với JDK hiện hành mới hơn, cả hai vẫn được hỗ trợ.

**Chọn Math hay StrictMath?** Trong phần xử lý số nguyên kiểm tra tràn này, thông thường dùng `Math.*Exact`. Nếu một codebase đã dùng `StrictMath` nhất quán thì các exact methods tương ứng vẫn hợp lệ; việc lựa chọn này không thay đổi các giới hạn `int/long`.

## 10. Ứng dụng thực tế: số lượng, tiền và chỉ số

### 10.1. Tính tổng tiền theo đơn vị nhỏ nhất

Giả sử đơn giá và tổng giá lưu bằng **`long` số xu** để tránh sai số floating point. Số lượng là `int`:

~~~java
// Phương thức minh họa, không phải chương trình độc lập.
static long subtotalCents(long unitPriceCents, int quantity) {
    if (unitPriceCents < 0 || quantity < 0) {
        throw new IllegalArgumentException("negative amount");
    }
    return Math.multiplyExact(unitPriceCents, quantity);
}
~~~

Overload `multiplyExact(long,int)` phù hợp tự nhiên: một giá trị long, một int, kết quả long. Nếu tích vượt long, phương thức ném `ArithmeticException` thay vì âm thầm tạo tổng tiền âm.

**Tuy nhiên**, nếu nghiệp vụ còn chiết khấu, thuế, làm tròn hoặc tỷ lệ thập phân, cần quy tắc domain rõ ràng; `BigDecimal` có thể phù hợp hơn cho các phép tính decimal. Checked arithmetic chỉ kiểm tra **tràn kiểu**, không tự bảo đảm tính hợp lệ của một biểu thức tài chính.

### 10.2. Cộng dồn số lượng nhiều lần

~~~java
// Đoạn minh họa; quantities là int[].
long total = 0L;
for (int quantity : quantities) {
    if (quantity < 0) {
        throw new IllegalArgumentException("negative quantity");
    }
    total = Math.addExact(total, quantity);
}
~~~

Do `total` là long, Java chọn `addExact(long,long)`, mở rộng từng `quantity` từ int sang long. Tổng có thể vượt `Integer.MAX_VALUE` mà không tràn int. Nếu vượt cả long, lời gọi cuối sẽ báo `ArithmeticException`.

Nếu biến `total` là int, Java chọn `addExact(int,int)` và sẽ từ chối sớm hơn — đúng hay sai phụ thuộc yêu cầu nghiệp vụ.

### 10.3. Tính kích thước byte của buffer

~~~java
// Đoạn minh họa.
long items = 1_000_000L;
int bytesPerItem = 64;
long bytes = Math.multiplyExact(items, bytesPerItem);
~~~

Nếu API đích chỉ nhận `int` size, dùng `Math.toIntExact(bytes)` **sau** khi tính chính xác ở long. Nếu API hỗ trợ long offset, tránh thu hẹp vô cớ.

### 10.4. Chọn kiểu dữ liệu trước khi tính

Một quy trình tốt:

1. Xác định **miền tối đa** của mỗi tham số nghiệp vụ.
2. Ước lượng miền của **kết quả trung gian**, không chỉ kết quả cuối.
3. Nếu `int` không đủ, mở rộng toán hạng sang `long` **trước phép tính**.
4. Nếu `long` không đủ, dùng `BigInteger` hoặc thay đổi thuật toán.
5. Dùng checked arithmetic ở nơi tràn phải được phát hiện và xử lý.
6. Kiểm tra thêm điều kiện nghiệp vụ (không âm, không vượt quota, đúng precision).
7. Test ở **MIN, MIN+1, -1, 0, 1, MAX-1, MAX** và các điểm crossing của nhiều phép tính.

## 11. Các lỗi phổ biến

| Sai lầm | Hệ quả | Cách đúng |
|---|---|---|
| `long result = intA * intB;` rồi cho rằng an toàn | Tích tính theo int và có thể tràn trước khi gán | `(long)intA * intB` hoặc `Math.multiplyExact((long)intA,intB)` |
| `long result = Math.multiplyExact(intA,intB);` | Chọn overload int,int; có thể ném dù long chứa được | Mở rộng tham số trước, hoặc dùng `Math.multiplyFull` |
| `Math.addExact(1, 2L)` được nghĩ là trả int | Compiler chọn long,long | Xem kiểu đối số và overload |
| `Math.multiplyExact(1, 2L)` được nghĩ là long,int | long,int không thể nhận đối số thứ hai long | Chọn long,long |
| Dùng `Math.abs(Integer.MIN_VALUE)` để kiểm tra số không âm | Kết quả vẫn âm | Dùng `Math.absExact` (JDK 15+) hoặc kiểm tra MIN thủ công |
| Dùng `-Integer.MIN_VALUE` để lấy số dương | Tràn, vẫn trả MIN | `Math.negateExact` hoặc mở rộng sang long |
| Cho rằng `MIN_VALUE / -1` tự ném | Phép chia nguyên thường không ném overflow | Kiểm tra riêng trên JDK17; `Math.divideExact` từ JDK18 |
| Dùng `(int) longValue` để kiểm tra miền int | Cast cắt bit, có thể tạo kết quả sai | `Math.toIntExact(longValue)` |
| Dùng `Math.max/min` để “phát hiện” tràn | Hai hàm chỉ so sánh giá trị | Dùng exact arithmetic đúng phép |
| Dùng `Math.multiplyFull` rồi gán ngay thành int | Giá trị long có thể vượt int | `Math.toIntExact(Math.multiplyFull(a,b))` nếu cần int |
| Dùng `BigInteger` rồi không kiểm tra business limit | Không tràn primitive, nhưng kết quả có thể vô lý với nghiệp vụ | Validate max/min theo domain |
| Bắt `ArithmeticException` nhưng trả 0 âm thầm | Che dấu dữ liệu/thiết kế không hợp lệ | Propagate, ghi lỗi hoặc dùng chính sách chuyển đổi tường minh |
| Chỉ test `MAX_VALUE`, không test `MIN_VALUE` | Bỏ sót overflow âm, negate, abs và division | Test cả hai biên |
| Gọi `Math.divideExact` trong chương trình Java 17 | Không có API ở JDK 17 | Dùng guard riêng hoặc yêu cầu JDK 18+ |
| Giả định `StrictMath` mới có toàn bộ checked arithmetic ở Java14 | Sai mốc phiên bản | Phân biệt các method Since 8/9 với Since 14 |

## 12. Bài tập và lời giải

**Câu 1.** Overload nào được chọn?

~~~java
Math.addExact(1, 2);
Math.addExact(1, 2L);
Math.multiplyExact(3L, 4);
Math.multiplyExact(3, 4L);
~~~

**Đáp án:** Lần lượt `addExact(int,int)`, `addExact(long,long)`, `multiplyExact(long,int)` và `multiplyExact(long,long)`.

**Câu 2.** Vì sao đoạn sau vẫn có thể ném lỗi dù biến đích long?

~~~java
long p = Math.multiplyExact(50_000, 50_000);
~~~

**Đáp án:** Hai đối số đều int nên chọn overload trả int. Tích `2_500_000_000` vượt int MAX trước khi có phép gán vào long. Muốn nhận long, dùng `Math.multiplyExact(50_000L, 50_000)` hoặc `Math.multiplyFull(50_000,50_000)`.

**Câu 3.** Kết quả `Math.incrementExact(Integer.MAX_VALUE)` và `Math.decrementExact(Integer.MIN_VALUE)`?

**Đáp án:** Cả hai ném `ArithmeticException`; một phép vượt biên trên, một phép vượt biên dưới.

**Câu 4.** `Math.negateExact(Long.MIN_VALUE)` có thể trả `Long.MAX_VALUE + 1` không?

**Đáp án:** Không. `Long.MAX_VALUE+1` cũng không chứa trong long; negateExact phải ném lỗi. Muốn số đối toán học ngoài long, dùng `BigInteger.valueOf(Long.MIN_VALUE).negate()`.

**Câu 5.** `(long)(50_000 * 50_000)` có cùng giá trị với `(long)50_000 * 50_000` không?

**Đáp án:** Không. Biểu thức đầu nhân int trước rồi cast (đã tràn), biểu thức sau mở rộng trước khi nhân, cho `2_500_000_000L`.

**Câu 6.** `Long.MIN_VALUE / -1L` có tự ném overflow không? Java 17 có `Math.divideExact` không?

**Đáp án:** Toán tử chia thường trả lại `Long.MIN_VALUE`, **không ném** overflow; `Math.divideExact` chỉ có từ JDK18. Java17 phải kiểm tra riêng hoặc đổi thuật toán/kiểu kết quả.

**Câu 7.** Làm sao kiểm tra một `long` có chuyển thành `int` an toàn?

**Đáp án:** `Math.toIntExact(longValue)`. Nó ném ngoại lệ nếu nằm ngoài khoảng `Integer.MIN_VALUE..Integer.MAX_VALUE`.

**Câu 8.** Tại sao `Math.absExact(Integer.MIN_VALUE)` ném ngoại lệ, trong khi `Math.abs(Integer.MIN_VALUE)` không?

**Đáp án:** Trị tuyệt đối toán học của int MIN lớn hơn int MAX đúng 1. `absExact` kiểm tra tràn; `abs` thường trả chính MIN.

**Câu 9.** Có nên luôn dùng BigInteger để tránh mọi lỗi số học?

**Đáp án:** Không bắt buộc. Với miền dữ liệu đã giới hạn phù hợp, `int`/`long` và exact methods thường đơn giản, hiệu quả, diễn đạt đúng contract. `BigInteger` hữu ích khi kết quả có thể vượt long, nhưng vẫn cần validation domain.

**Câu 10.** Mốc Java 14 nào liên quan `StrictMath`, trong khi `Math.absExact` và `Math.divideExact` có từ mốc nào?

**Đáp án:** `StrictMath.incrementExact`, `decrementExact`, `negateExact` có Since Java14. `Math.absExact` từ Java15, `Math.divideExact` từ Java18.

## 13. Tài liệu tham khảo chính thức

- [Oracle Java SE 14 — StrictMath](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/lang/StrictMath.html): bảng các overload, mốc `Since: 14` cho `incrementExact`, `decrementExact`, `negateExact`.
- [Oracle Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact`, `multiplyExact`, `multiplyFull`, `toIntExact`, `absExact` và hợp đồng `ArithmeticException`.
- [Oracle Java SE 17 — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): các overload số nguyên trong `StrictMath`.
- [Oracle Java SE 25 — Math](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html): đối chiếu chữ ký hiện hành, bao gồm `divideExact` trên JDK mới.
- [Oracle Java SE 18 — Math](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/Math.html): mốc `Since: 18` của `divideExact`.
- [Java Language Specification 17 — `4.2.1 Integral Types and Values`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): khoảng int/long, two's complement.
- [Java Language Specification 17 — `5.6 Numeric Contexts`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): numeric promotion.
- [Java Language Specification 17 — `15.12 Method Invocation Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): cách chọn overload tại compile time.
- [Java Language Specification 17 — `15.17.2 Division Operator /`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): trường hợp `MIN_VALUE / -1` và chia cho 0.
- [Oracle Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): kết quả số nguyên vượt giới hạn primitive.

**Ghi nhớ:** Hãy **chọn kiểu và overload trước khi tính**, không hy vọng biến nhận kiểu `long` sẽ chữa kết quả `int` đã tràn. Dùng `Math.*Exact` để **phát hiện** overflow, `Math.toIntExact` khi thu hẹp, `Math.multiplyFull` cho tích int×int cần lưu long, và `BigInteger` nếu vượt long. Kiểm thử cả `MIN_VALUE` lẫn `MAX_VALUE`: một bên gây tràn khi giảm/đổi dấu/lấy trị tuyệt đối, bên kia gây tràn khi tăng. `ArithmeticException` là tín hiệu dữ liệu hoặc thiết kế cần được xử lý có chủ đích, không phải lý do âm thầm bỏ qua kết quả.