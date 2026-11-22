# Giới hạn khi tự xây dựng một lớp con `Number` trong Java

## 1. Vì sao `extends Number` chưa đủ để có một kiểu số hoàn chỉnh?

Trong Java, `java.lang.Number` là **lớp trừu tượng** (*abstract class*) đại diện chung cho những đối tượng có thể cung cấp giá trị ở dạng một số kiểu nguyên thủy. Các lớp quen thuộc như `Integer`, `Long`, `Float`, `Double`, `BigInteger` và `BigDecimal` đều thuộc họ `Number`.

Bạn có thể xây dựng một lớp riêng:

```java
final class CustomNumber extends Number {
    @Override public int intValue() { return 0; }
    @Override public long longValue() { return 0L; }
    @Override public float floatValue() { return 0.0f; }
    @Override public double doubleValue() { return 0.0; }
}
```

Lớp này **biên dịch được**, nhưng mới chỉ đáp ứng hợp đồng tối thiểu: nó cung cấp bốn cách chuyển đổi thành primitive. Nó chưa có phép cộng, phép nhân, quy tắc so sánh giá trị, kiểm tra miền, độ chính xác, đơn vị đo hay các bất biến mà một kiểu số thực tế cần.

Vì vậy, **kế thừa `Number` không biến lớp của bạn thành một kiểu primitive hoặc wrapper có đầy đủ cú pháp số học**. Trong Java, không có cơ chế nạp chồng toán tử `+`, `-`, `*`, `/` dành cho các đối tượng `Number` tự định nghĩa.

Bài học này tập trung vào **giới hạn và trách nhiệm thiết kế khi tự xây dựng một lớp con `Number`**, cách đáp ứng đúng API, những mất mát dữ liệu có thể xảy ra và khi nào nên chọn một thiết kế khác.

## 2. Hợp đồng tối thiểu của `Number`

`Number` là lớp trừu tượng, triển khai `java.io.Serializable`. Bốn phương thức **abstract** mà lớp con cụ thể phải triển khai là:

| Phương thức | Kiểu kết quả | Trách nhiệm |
|---|---|---|
| `intValue()` | `int` | Biểu diễn giá trị dưới dạng số nguyên 32 bit |
| `longValue()` | `long` | Biểu diễn giá trị dưới dạng số nguyên 64 bit |
| `floatValue()` | `float` | Biểu diễn giá trị dưới dạng số thực nhị phân 32 bit |
| `doubleValue()` | `double` | Biểu diễn giá trị dưới dạng số thực nhị phân 64 bit |

Ngoài ra, `Number` đã cung cấp hai phương thức cụ thể:

- `byteValue()`: về cơ bản chuyển `(byte) intValue()`.
- `shortValue()`: về cơ bản chuyển `(short) intValue()`.

Điều đó có nghĩa bạn **không bắt buộc override** `byteValue()` hoặc `shortValue()` để có một lớp con không trừu tượng. Tuy nhiên, mặc định của chúng có thể làm mất bit theo quy tắc thu hẹp số nguyên. Nếu mô hình dữ liệu cần cách xử lý khác, hãy cân nhắc thiết kế API tường minh và kiểm thử kỹ.

Ví dụ:

```java
Number n = Integer.valueOf(258);
System.out.println(n.intValue());   // 258
System.out.println(n.byteValue());  // 2
```

Số 258 khi chuyển thành `byte` chỉ giữ 8 bit thấp, cho 2. **Việc có phương thức `byteValue()` không chứng minh giá trị sẽ vừa miền `byte`.**

### Điều mà lớp `Number` không hứa hẹn

`Number` không cung cấp một hợp đồng chung về:

- Miền giá trị, độ chính xác hay đơn vị.
- Số nguyên hay số thập phân; hữu hạn hay có NaN/Infinity.
- Phép cộng, trừ, nhân, chia giữa hai đối tượng `Number`.
- Kiểu kết quả sau phép tính.
- Thứ tự so sánh tự nhiên hoặc quy tắc bằng nhau theo giá trị.
- Chuyển đổi **chính xác** sang primitive.
- An toàn luồng hoặc tính bất biến của lớp con.

Một lớp con có thể bổ sung những khả năng đó, nhưng **đó là hợp đồng do chính lớp con thiết kế**, không tự xuất hiện vì kế thừa `Number`.

## 3. Kế thừa `Number` không tạo toán tử số học

Hãy xem:

```java
Number a = Integer.valueOf(7);
Number b = Long.valueOf(5);

// Number c = a + b; // LỖI biên dịch
int c = a.intValue() + b.intValue(); // 12, nhưng có thể mất dữ liệu
```

Dòng đầu tiên bị comment vì `a + b` **không hợp lệ**. Toán tử `+` trên số yêu cầu các toán hạng có thể chuyển đổi theo quy tắc số học của ngôn ngữ. Một đối tượng có kiểu tĩnh `Number` **không được Java tự động unbox thành kiểu số nguyên thủy tùy ý**.

Để tính toán, phải gọi phương thức chuyển đổi phù hợp hoặc sử dụng API dành riêng cho kiểu thực:

```java
BigDecimal price = new BigDecimal("12.50");
BigDecimal fee = new BigDecimal("2.25");
BigDecimal total = price.add(fee); // 14.75
```

Đây là **đoạn minh họa**, cần đặt trong phạm vi có import `java.math.BigDecimal`. Các phương thức như `add`, `subtract` và `multiply` là **API của `BigDecimal`**, không phải của `Number`.

**Không viết một hàm cộng tổng quát nhận hai `Number` rồi mặc định gọi `doubleValue()` để “giải quyết mọi kiểu số”.** Phương án ấy có thể làm mất chính xác của `BigInteger`/`BigDecimal` và có thể biến giá trị quá lớn thành Infinity.

## 4. Đừng nhầm `Number` với các lớp wrapper được auto-unbox

Java có hỗ trợ **unboxing conversion** cho các wrapper tương ứng với primitive, chẳng hạn `Integer → int` và `Double → double`:

```java
Integer x = 7;
int y = x;        // hợp lệ: unboxing Integer -> int
int sum = x + 5;  // hợp lệ: unboxing rồi cộng
```

Nhưng với biến có **kiểu tĩnh là `Number`**:

```java
Number x = Integer.valueOf(7);

// int y = x;       // LỖI biên dịch: Number không auto-unbox thành int
// int sum = x + 5; // LỖI biên dịch
int y = x.intValue(); // hợp lệ: gọi API Number một cách tường minh
```

Dù ở thời điểm chạy đối tượng thực tế là `Integer`, trình biên dịch xét kiểu tĩnh `Number` của biến. Không có quy tắc “unbox tùy động” đối với mọi lớp con `Number`.

Với một lớp con riêng như `FixedCents extends Number`, Java cũng **không tự có chuyển đổi `FixedCents → long`**, kể cả khi lớp đã định nghĩa `longValue()`. Phải gọi phương thức rõ ràng.

Đây là giới hạn thiết kế căn bản: kế thừa `Number` giúp cung cấp một **giao diện chuyển đổi giá trị ở mức lớp**, không mở rộng cú pháp và hệ thống kiểu primitive của Java.

## 5. Phương thức chuyển đổi có thể làm mất phần lẻ, tràn hoặc mất chính xác

Các phương thức `intValue()`, `longValue()`, `floatValue()` và `doubleValue()` không phải những phiên bản luôn thành công và luôn chính xác. Chúng có thể trả về một giá trị được làm tròn, thu hẹp hoặc mất thông tin.

### Từ decimal sang số nguyên

```java
Number amount = new BigDecimal("12.99");

System.out.println(amount.intValue());  // 12
System.out.println(amount.longValue()); // 12
```

Phần lẻ bị loại khi chuyển sang số nguyên. Với số âm, cần chú ý quy tắc cắt về 0 của chuyển đổi kiểu số thực/nguyên trong nhiều trường hợp; riêng `BigDecimal` thực thi quy tắc chuyển đổi theo hợp đồng của API.

### Vượt miền `int`

```java
BigInteger big = new BigInteger("2147483648");

System.out.println(big.intValue()); // -2147483648
```

Giá trị 2_147_483_648 không vừa `int`; `BigInteger.intValue()` lấy các bit thấp, dẫn tới một giá trị có dấu khác với số gốc. Nếu cần yêu cầu chuyển **chính xác**, `BigInteger` có `intValueExact()`: nó ném `ArithmeticException` nếu không vừa miền.

### Mất độ chính xác khi chuyển sang `double`

Binary64 có khoảng 53 bit độ chính xác phần trị. Hai số nguyên lớn khác nhau có thể chuyển thành **cùng một giá trị `double`**:

```java
BigInteger a = new BigInteger("9007199254740992");
BigInteger b = new BigInteger("9007199254740993");

System.out.println(a.equals(b)); // false
System.out.println(a.doubleValue() == b.doubleValue()); // true
```

Vì vậy, **không dùng `doubleValue()` làm khóa so sánh giá trị chung cho mọi `Number`**. Nếu lớp của bạn cần kiểm tra chính xác, hãy cung cấp phương thức riêng như `toBigDecimal()` hoặc `longValueExact()` khi mô hình cho phép.

### Chính sách chuyển đổi cho lớp con

Khi tự viết `Number`, bạn cần quyết định và ghi rõ:

- Với giá trị có phần lẻ, `intValue()`/`longValue()` cắt phần lẻ, làm tròn hay từ chối?
- Khi số vượt miền `int` hoặc `long`, xử lý thế nào?
- `floatValue()`/`doubleValue()` có thể mất độ chính xác đến mức nào?
- Có hỗ trợ NaN/Infinity không? Nếu là tiền tệ decimal, thường **không nên** đưa các giá trị ấy vào miền nghiệp vụ.
- Có phương thức **chuyển chính xác và báo lỗi rõ ràng** bên cạnh các phương thức `Number` không?

Đừng dựa vào lời gọi chuyển kiểu để che giấu đơn vị hoặc làm mất dữ liệu ngoài ý muốn.

## 6. Chương trình kiểm chứng các giới hạn của `Number`

Tạo file `NumberLimitsDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberLimitsDemo {
    public static void main(String[] args) {
        Number wrapperAsNumber = Integer.valueOf(7);
        System.out.println("manual extraction: "
                + (wrapperAsNumber.intValue() + 5));

        Number decimalAsNumber = new BigDecimal("12.99");
        System.out.println("decimal to int: "
                + decimalAsNumber.intValue());

        BigInteger tooLarge = new BigInteger("2147483648");
        System.out.println("overflowing intValue: "
                + tooLarge.intValue());

        try {
            System.out.println(tooLarge.intValueExact());
        } catch (ArithmeticException e) {
            System.out.println("intValueExact: out of range");
        }

        BigInteger a = new BigInteger("9007199254740992");
        BigInteger b = new BigInteger("9007199254740993");
        System.out.println("big integers equal: " + a.equals(b));
        System.out.println("converted doubles equal: "
                + (a.doubleValue() == b.doubleValue()));

        Number n = Integer.valueOf(258);
        System.out.println("inherited byte conversion: "
                + n.byteValue());
    }
}
```

Chạy với Java 17+:

```bash
javac NumberLimitsDemo.java
java NumberLimitsDemo
```

Kết quả:

```text
manual extraction: 12
decimal to int: 12
overflowing intValue: -2147483648
intValueExact: out of range
big integers equal: false
converted doubles equal: true
inherited byte conversion: 2
```

Chương trình cho thấy `Number` là **API chuyển đổi**, còn giới hạn miền, độ chính xác và chính sách báo lỗi vẫn phụ thuộc **kiểu số thực tế**.

## 7. Thiết kế ví dụ: số tiền cố định hai chữ số thập phân

Giả sử mô hình muốn biểu diễn một giá trị tiền bằng **số xu nguyên**, và mọi phép toán cộng phải được kiểm soát tràn. Một lớp `FixedCents` tự định nghĩa có thể lưu một biến `long cents`.

Đây chỉ là **mô hình học tập cố định hai chữ số thập phân**, chưa đầy đủ yêu cầu sản phẩm tiền tệ thực tế. Nó **không lưu currency**, không có quy tắc đổi tiền và không tự xử lý thuế hay phương thức làm tròn tỷ giá.

Quy ước rõ ràng:

- Giá trị gốc `cents` là **đơn vị nhỏ nhất**, ví dụ 1234 nghĩa là 12.34 đơn vị tiền.
- `toBigDecimal()` trả giá trị decimal **chính xác** theo đơn vị tiền chính.
- `intValue()` và `longValue()` trả **số đơn vị tiền nguyên**, cắt phần lẻ về 0.
- `floatValue()`, `doubleValue()` trả một **xấp xỉ binary floating-point** của giá trị decimal.
- Phép cộng phải gọi `plus`, không thể dùng `+` giữa hai `FixedCents`.
- `Math.addExact` dùng để phát hiện tràn số xu.
- `equals`/`hashCode`/`compareTo` xét cùng đơn vị và cùng giá trị `cents`.

Việc định nghĩa các quy tắc này **không do `Number` cung cấp**. Nhà phát triển phải thiết kế và công bố chúng.

## 8. Lớp con `Number` có thể biên dịch, chạy và kiểm tra được

Tạo file `CustomNumberDemo.java` chứa **hai lớp**: lớp `public` dùng để chạy và lớp `FixedCents` lồng tĩnh.

```java
import java.math.BigDecimal;

public class CustomNumberDemo {

    static final class FixedCents extends Number
            implements Comparable<FixedCents> {

        private static final long serialVersionUID = 1L;
        private final long cents;

        FixedCents(long cents) {
            this.cents = cents;
        }

        BigDecimal toBigDecimal() {
            return BigDecimal.valueOf(cents, 2);
        }

        FixedCents plus(FixedCents other) {
            return new FixedCents(Math.addExact(cents, other.cents));
        }

        @Override
        public int intValue() {
            return (int) longValue();
        }

        @Override
        public long longValue() {
            return cents / 100L; // cắt phần lẻ về 0
        }

        @Override
        public float floatValue() {
            return toBigDecimal().floatValue();
        }

        @Override
        public double doubleValue() {
            return toBigDecimal().doubleValue();
        }

        @Override
        public int compareTo(FixedCents other) {
            return Long.compare(cents, other.cents);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof FixedCents that
                    && cents == that.cents;
        }

        @Override
        public int hashCode() {
            return Long.hashCode(cents);
        }

        @Override
        public String toString() {
            return toBigDecimal().toPlainString();
        }
    }

    public static void main(String[] args) {
        FixedCents price = new FixedCents(1234);
        FixedCents fee = new FixedCents(266);
        FixedCents total = price.plus(fee);

        Number generic = price;

        System.out.println("price: " + price);
        System.out.println("fee: " + fee);
        System.out.println("total: " + total);
        System.out.println("as long: " + generic.longValue());
        System.out.println("as double: " + generic.doubleValue());
        System.out.println("as byte: " + generic.byteValue());
        System.out.println("same cents: "
                + price.equals(new FixedCents(1234)));
        System.out.println("price > fee: "
                + (price.compareTo(fee) > 0));
    }
}
```

Biên dịch và chạy:

```bash
javac CustomNumberDemo.java
java CustomNumberDemo
```

Kết quả:

```text
price: 12.34
fee: 2.66
total: 15.00
as long: 12
as double: 12.34
as byte: 12
same cents: true
price > fee: true
```

### Vì sao cách triển khai này chỉ là một **lựa chọn chính sách**?

Một số quyết định được viết thành mã, không phải “nghĩa chuẩn duy nhất” của `Number`:

1. `longValue()` chọn trả **đơn vị chính nguyên**, không trả số xu. Nếu một ứng dụng khác mong `longValue()` trả 1234, hai hệ thống sẽ diễn giải sai nhau. Hợp đồng API phải mô tả rõ.
2. `intValue()` gọi `(int) longValue()`. Với số đơn vị chính vượt miền `int`, phép ép kiểu này **có thể mất bit**. Không dùng nó để kiểm tra tiền lớn.
3. `floatValue()` và `doubleValue()` được phép trả **xấp xỉ** — số thập phân `12.34` không nhất thiết có biểu diễn nhị phân chính xác.
4. `plus` dùng `Math.addExact` để từ chối tràn số `long` của cents. Nhưng lớp chưa có phép trừ, nhân với tỷ giá, ràng buộc currency hoặc xử lý làm tròn.
5. `equals` và `hashCode` cùng dựa vào `cents`. Đây là hành vi phải **tự override**: kế thừa `Number` không tự tạo bình đẳng theo giá trị.

Đặc biệt: `Number.byteValue()` của lớp ví dụ sẽ kế thừa cơ chế qua `intValue()`, rồi có thể thu hẹp tiếp về `byte`. Nếu `longValue()` có kết quả lớn hoặc âm, giá trị `byteValue()` cũng có thể khác giá trị toán học mong muốn.

## 9. Tại sao phải quan tâm `equals`, `hashCode` và `compareTo`?

`Number` không đảm bảo hai đối tượng khác nhau nhưng có “cùng giá trị” sẽ bằng nhau theo `equals`. Nếu không override, lớp con kế thừa hành vi so sánh đối tượng của `Object`.

Ví dụ hai đối tượng:

```java
FixedCents first = new FixedCents(1234);
FixedCents second = new FixedCents(1234);
```

Hai dòng trên là **minh họa** bên trong phạm vi lớp có thể truy cập `FixedCents`. Nếu `FixedCents` không tự triển khai `equals`, `first.equals(second)` có thể false mặc dù `cents` bằng nhau.

Khi dùng các cấu trúc như `HashSet` hoặc `HashMap`, cần đảm bảo:

- Nếu `a.equals(b)` true thì `a.hashCode() == b.hashCode()`.
- Giá trị sử dụng trong `equals` và `hashCode` phải được quản lý ổn định; **bất biến** là lựa chọn tốt cho value object.
- `compareTo` (nếu có) nên nhất quán với ý nghĩa thứ tự của mô hình và, khi có thể, với `equals`.
- Không so sánh giá trị tùy ý bằng `doubleValue()` của các `Number` không cùng miền/độ chính xác.

Ví dụ `new BigDecimal("2.0")` và `new BigDecimal("2.00")` có giá trị toán học bằng nhau theo `compareTo`, nhưng `equals` false vì khác scale. Điều đó cho thấy ngay cả **những lớp con `Number` của thư viện chuẩn cũng có chính sách bình đẳng riêng**.

### Có cần `Comparable<Number>` cho mọi kiểu số không?

Không. Một phép so sánh có ý nghĩa cần xét **cùng miền dữ liệu và cùng đơn vị**. Một đối tượng chứa mét không tự so sánh được với một đối tượng chứa tiền chỉ vì cả hai đều `extends Number`.

Trong ví dụ, `Comparable<FixedCents>` có chủ đích: chỉ so các giá trị cùng mô hình. Không định nghĩa thứ tự tổng quát cho mọi `Number` vì không tồn tại quy tắc thống nhất về NaN, độ chính xác, scale, đơn vị, Overflow và các kiểu số tùy biến.

## 10. Tính bất biến, serialize và an toàn luồng

`Number` triển khai `Serializable`, nên lớp con có liên hệ với Java Serialization. Tuy nhiên:

- Các trường dữ liệu của lớp con vẫn phải phù hợp cơ chế serialization nếu muốn serialize/deserialize thành công.
- Một lớp bất biến có thể cần thêm các bước bảo vệ bất biến khi deserialize nếu triển khai thực tế có logic phức tạp.
- `serialVersionUID` là một phần của quản lý tương thích serialization truyền thống; nó **không tự bảo đảm dữ liệu an toàn hoặc tương thích** giữa mọi phiên bản.
- Nếu không cần Java native serialization, không nên vì kế thừa `Number` mà mặc định dùng serialization đối tượng làm định dạng lưu trữ/giao tiếp bên ngoài.

Ví dụ `FixedCents` dùng `private final long cents` và chỉ tạo đối tượng mới khi tính toán. Cách tiếp cận **immutable value object** giúp tránh việc giá trị dùng làm khóa trong hash collection bị đổi sau khi thêm vào tập.

Nhưng kế thừa `Number` **không tự làm mọi lớp con trở nên immutable hoặc thread-safe**. Ví dụ một số kiểu liên quan đến trạng thái số như `AtomicInteger` cũng kế thừa `Number` nhưng có mục tiêu và cơ chế cập nhật khác.

Một lớp con mutable cần đặc biệt chú ý đồng bộ, quan sát trạng thái và hợp đồng `equals`/`hashCode` nếu đối tượng được chia sẻ giữa nhiều luồng.

## 11. Giới hạn của hệ thống kiểu và cú pháp Java

### 11.1. Một lớp chỉ được kế thừa một lớp cha trực tiếp

Java hỗ trợ **single inheritance** đối với class. Nếu bạn viết:

```java
class MyNumber extends Number {
    // ...
}
```

thì `MyNumber` không thể đồng thời `extends` một lớp cha khác. Bạn có thể triển khai nhiều interface, như `Comparable<MyNumber>`, nhưng không thể có hai superclass.

**Record** cũng không thể `extends Number` vì mọi record trực tiếp mở rộng `java.lang.Record`. Một record phù hợp hơn khi bạn cần value object đơn giản nhưng không cần quan hệ kiểu với `Number`.

Nếu mô hình cần đồng thời một superclass khác và các thao tác số, hãy cân nhắc **composition** (chứa `BigDecimal` hoặc `BigInteger` làm trường) và API tường minh thay vì cố kế thừa `Number`.

### 11.2. Java không cho tạo “primitive mới”

Một `Number` tự viết:

- Không có literal riêng như `123usd`.
- Không dùng trực tiếp toán tử số học primitive.
- Không được nhận bởi mọi overload yêu cầu `int`/`double` nếu không chuyển đổi.
- Không hỗ trợ unboxing tự động chỉ vì đã override `intValue()`.
- Không đổi quy tắc thăng cấp số học đã cố định của Java.

Đây là giới hạn ngôn ngữ, không phải do thiếu override một phương thức cụ thể.

### 11.3. Không thể dựa vào `instanceof Number` để suy ra mọi loại số đều so được

`instanceof Number` chỉ kiểm tra quan hệ kiểu tham chiếu. Đối tượng có thể là `BigDecimal`, `BigInteger`, `Integer` hoặc bất kỳ kiểu số tùy biến có miền/đơn vị riêng.

```java
static String describe(Number value) {
    if (value == null) {
        return "missing";
    }
    return value.getClass().getSimpleName()
            + " -> " + value.doubleValue();
}
```

Đây là phương thức minh họa **không bảo toàn giá trị số chính xác**. Nó phù hợp cho log xấp xỉ khi có chủ đích, nhưng không phải hàm chuẩn hóa số an toàn cho tài chính hoặc so sánh giá trị lớn.

## 12. Thiết kế chuyển đổi **chính xác** bên cạnh các phương thức `Number`

Bốn phương thức abstract phục vụ **truy cập giá trị nguyên thủy**. Nếu miền số của bạn đòi hỏi không mất dữ liệu, nên cung cấp API bổ sung với tên biểu đạt chính sách:

```java
BigDecimal toBigDecimal()
long centsExact()
int intValueExact()
```

Đây là **các chữ ký gợi ý**, không phải đoạn chương trình độc lập. Ví dụ:

- `toBigDecimal()` giữ nguyên phần thập phân trong hệ decimal khi cấu trúc nội bộ cho phép.
- `centsExact()` trả số xu gốc và mô tả đơn vị ngay ở tên hàm.
- `intValueExact()` chỉ trả `int` nếu giá trị toán học không có phần lẻ và nằm trong miền `int`; nếu không thì ném ngoại lệ có kiểm soát.

Một triển khai đơn giản cho lớp `FixedCents` bên trên có thể sử dụng:

```java
int intValueExact() {
    return toBigDecimal().intValueExact();
}
```

Phương thức này phải được đặt **bên trong lớp `FixedCents`**. Nó yêu cầu số tiền theo đơn vị chính là số nguyên chính xác: 12.00 được phép, 12.34 bị từ chối. Nếu nhu cầu thật là trả số xu dạng `int`, cần API khác như `Math.toIntExact(cents)`, cũng với tên đơn vị rõ ràng.

Tương tự, khi nhận một `Number` bất kỳ từ API, không thể bảo đảm tự khôi phục giá trị decimal gốc từ `doubleValue()`. Nếu cần decimal chính xác, hãy yêu cầu đầu vào `BigDecimal` hoặc giao diện riêng cung cấp decimal ở ranh giới thiết kế.

## 13. Khi nào nên dùng composition thay vì `extends Number`?

Một lớp giá trị có ý nghĩa miền dữ liệu, ví dụ `Money`, `Percentage`, `Temperature`, `Distance`, thường cần:

- Đơn vị và ràng buộc đi kèm giá trị.
- Các phép toán có ý nghĩa và không có ý nghĩa (ví dụ tiền + tiền cùng currency, nhưng không cộng tiền với mét).
- Quy tắc làm tròn/kiểm tra riêng.
- Kiểm soát so sánh, chuyển đổi và serialize.

Một đối tượng `Money` **không nhất thiết cần kế thừa `Number`**. Dùng composition với `BigDecimal` và `Currency` thường thể hiện mô hình rõ ràng hơn:

```java
import java.math.BigDecimal;
import java.util.Currency;

record Money(BigDecimal amount, Currency currency) {
    Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException("missing money data");
        }
    }

    Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
```

Đây là **đoạn khai báo record minh họa**, không có phương thức `main`. Nó cho thấy cách giữ mô hình bằng **đơn vị và API riêng**; chưa xử lý scale, currency minor unit, làm tròn hay toàn bộ yêu cầu triển khai tài chính.

### Vì sao composition có thể an toàn hơn?

Nếu `Money extends Number`, một framework có thể tùy ý gọi `doubleValue()` và vô tình làm mất precision, currency hay scale. Một record/class không kế thừa `Number` sẽ **buộc bên gọi chọn phép chuyển đổi hoặc thao tác có đơn vị rõ ràng**.

Hãy chỉ `extends Number` khi thật sự cần hỗ trợ một API đa hình nhận `Number` và bạn **có thể định nghĩa cách chuyển sang bốn primitive** nhất quán, dễ hiểu, được tài liệu hóa. Nếu không có yêu cầu tương thích đó, composition thường có ít hành vi ngầm hơn.

## 14. Generic, collection và giới hạn của kiểu `Number`

Java generics hỗ trợ:

```java
java.util.List<Number> numbers = java.util.List.of(
        Integer.valueOf(1),
        Long.valueOf(2L),
        new BigDecimal("3.5"));
```

Một danh sách như trên có thể giữ các lớp số khác nhau, nhưng Java **không tự có phép cộng tổng quát chính xác** cho `List<Number>`. Nếu duyệt mỗi phần tử rồi cộng `doubleValue()`, ta đã chọn chính sách **tính xấp xỉ binary64**.

```java
double sum = 0.0;
for (Number n : numbers) {
    sum += n.doubleValue();
}
```

Đây là **đoạn mã minh họa**; nó có thể phù hợp với dữ liệu đo xấp xỉ, nhưng không giữ exact decimal cho mọi `Number`.

Nếu API chỉ nhận số nguyên nhỏ và ổn định, có thể hạn chế kiểu cụ thể như `List<Integer>`; nếu đòi decimal chính xác thì sử dụng `List<BigDecimal>` hoặc một abstraction miền dữ liệu phù hợp. **Ràng buộc kiểu đầu vào chặt hơn có thể cải thiện tính đúng đắn hơn là chấp nhận mọi `Number`.**

### Generic bound không tạo phép toán

```java
static <T extends Number> double approximate(T value) {
    return value.doubleValue();
}
```

Phương thức generic trên hợp lệ, nhưng vẫn **không thể viết `value + value`** mà mong toán tử hiểu đó là số. Một bound `T extends Number` chỉ bảo đảm truy cập được API `Number`; không thêm hỗ trợ số học primitive, độ chính xác hoặc thao tác giữa các giá trị `T`.

## 15. Nhầm lẫn phổ biến và cách tránh

| Ngộ nhận | Sự thật | Cách xử lý |
|---|---|---|
| `extends Number` thì dùng được `a + b` | Java không cho nạp chồng toán tử cho lớp số tùy biến | Cung cấp `add/plus` hoặc API miền dữ liệu |
| Cần override cả 6 phương thức chuyển đổi | Chỉ 4 phương thức là abstract; `byteValue/shortValue` đã có mặc định | Override thêm khi có hợp đồng phù hợp |
| `Number n` sẽ tự unbox như `Integer` | Kiểu tĩnh `Number` không có unboxing primitive chung | Gọi `intValue()`/API cụ thể |
| `intValue()` luôn chính xác | Có thể mất phần lẻ hoặc bit khi vượt miền | Dùng phương thức `...Exact()` nếu có |
| `doubleValue()` đủ để so mọi số | Số nguyên lớn/decimal có thể mất precision | So theo kiểu gốc và miền dữ liệu |
| Kế thừa `Number` tự định nghĩa `equals` giá trị | Không; hành vi mặc định đến từ `Object` | Thiết kế `equals/hashCode` nhất quán |
| `Number` có thứ tự so sánh tự nhiên | Không bắt buộc `Comparable` | Implement `Comparable<T>` khi có ý nghĩa |
| `Number` bảo đảm immutable | Không | Thiết kế `final`, trường `final` hoặc quản lý đồng bộ |
| `Number` tự kiểm tra overflow | Không | `Math.*Exact` hoặc API kiểm tra |
| `Number` bảo toàn đơn vị đo | Không có trường/unit chung | Đặt API và loại dữ liệu rõ đơn vị |
| Mọi `Number` có thể serialize an toàn ra mạng | Serializable không tương đương định dạng trao đổi an toàn | Dùng định dạng dữ liệu xác định, kiểm soát schema |
| `record` có thể `extends Number` | Record đã kế thừa `Record` | Dùng composition nếu muốn value record |
| `List<Number>` có `sum` chuẩn cho mọi số | Không có mô hình cộng/tính chính xác duy nhất | Chọn thuật toán, kiểu và quy tắc phù hợp |

## 16. Bài tập tự kiểm tra

**Câu 1.** Muốn tạo lớp `extends Number` cụ thể, cần override bốn phương thức nào?  
**Đáp án:** `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`.

**Câu 2.** Có bắt buộc override `byteValue()` và `shortValue()` không?  
**Đáp án:** Không. `Number` đã triển khai dựa trên `intValue()`, nhưng chuyển đổi có thể mất thông tin.

**Câu 3.** Nếu `Number n = Integer.valueOf(10);`, có viết `int x = n;` được không?  
**Đáp án:** Không. Biến có kiểu tĩnh `Number`; cần `int x = n.intValue();` hoặc thiết kế API sử dụng kiểu cụ thể.

**Câu 4.** Lớp `FixedCents extends Number` có tự dùng `price + fee` được không?  
**Đáp án:** Không. Phải định nghĩa rồi gọi phương thức `price.plus(fee)` hoặc API khác.

**Câu 5.** `new BigInteger("2147483648").intValue()` bằng bao nhiêu?  
**Đáp án:** -2_147_483_648 do mất bit cao theo quy tắc chuyển hẹp của `BigInteger`. Muốn từ chối số ngoài miền dùng `intValueExact()`.

**Câu 6.** Tại sao hai `BigInteger` hơn nhau 1 có thể trông bằng nhau sau `doubleValue()`?  
**Đáp án:** Vì binary64 có giới hạn độ chính xác phần trị; các giá trị lớn có thể làm tròn vào cùng một `double`.

**Câu 7.** Nếu hai đối tượng `FixedCents` có cùng `cents`, cần những phương thức nào để `HashSet` coi chúng bằng nhau?  
**Đáp án:** `equals` và `hashCode` được triển khai nhất quán.

**Câu 8.** Có nên để `longValue()` của kiểu tiền trả số xu hay số đơn vị chính?  
**Đáp án:** Không có đáp án chung. Phải định nghĩa chính sách rõ; tốt nhất cung cấp API có tên đơn vị, như `centsExact()`, để tránh nhập nhằng.

**Câu 9.** Nếu lớp muốn so thứ tự các số cùng loại, `Number` có đủ không?  
**Đáp án:** Không. Có thể triển khai `Comparable<MyNumber>` hoặc phương thức so sánh riêng.

**Câu 10.** Vì sao `Money` có thể nên là record/class chứa `BigDecimal` thay vì `extends Number`?  
**Đáp án:** Vì nó cần bảo vệ đơn vị, quy tắc chuyển tiền và tính toán miền dữ liệu; kế thừa `Number` có thể khuyến khích chuyển đổi primitive làm mất thông tin.

**Câu 11.** `class MyNumber extends Number` có thể còn `extends BaseEntity` không?  
**Đáp án:** Không, Java chỉ hỗ trợ một superclass trực tiếp. Có thể triển khai thêm các interface hoặc dùng composition.

**Câu 12.** `T extends Number` có cho phép `a + b` với hai biến `T` không?  
**Đáp án:** Không. Generic bound chỉ bảo đảm các phương thức của `Number`, không tạo toán tử cộng.

## 17. Checklist trước khi quyết định tự tạo lớp con `Number`

1. **Lý do kế thừa:** có framework/API thực sự yêu cầu kiểu `Number` không? Nếu không, composition có rõ nghĩa hơn không?
2. **Mô hình dữ liệu:** số nguyên, decimal, tỷ lệ, giá trị đo hay số kèm đơn vị? Miền cho phép là gì?
3. **Bốn phương thức bắt buộc:** mỗi phương thức sẽ trả giá trị nào khi phần lẻ, vượt miền hoặc mất độ chính xác?
4. **API chính xác:** có cần `toBigDecimal()`, `longValueExact()`, `centsExact()`, hoặc phương thức báo lỗi thay vì làm mất bit?
5. **Phép toán:** cộng, trừ, nhân, chia, làm tròn, chia cho 0 và tràn số xử lý thế nào?
6. **So sánh:** `equals/hashCode` và `compareTo` xét những trường/đơn vị nào? Có tương thích với các collection không?
7. **Đối tượng:** immutable hay mutable? Nếu mutable, đồng bộ và tính ổn định của hash key được bảo đảm ra sao?
8. **Ranh giới hệ thống:** có cần serialize, lưu database, JSON, logging? Có cách biểu diễn rõ ràng ngoài primitive không?
9. **Kiểm thử:** bao phủ số âm, số 0, cực trị, phần lẻ, giá trị ngoài miền, lỗi chuyển kiểu và các bất biến.
10. **Tài liệu hợp đồng:** người gọi có biết chính xác cách hiểu các kết quả `intValue/longValue/floatValue/doubleValue` không?

**Kết luận:** `Number` là **lớp nền cho việc lấy biểu diễn primitive của một giá trị số**, không phải một giao diện toán học đầy đủ. Muốn tự xây dựng lớp con an toàn, bạn phải tự thiết kế miền dữ liệu, phép toán, kiểm tra mất mát, so sánh và quy tắc chuyển đổi. Với kiểu có đơn vị hoặc độ chính xác nghiệp vụ quan trọng, **composition và API tường minh** thường là lựa chọn dễ bảo vệ tính đúng đắn hơn.

Tài liệu API chính thức: [Java SE 17 — Number](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html), [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).
