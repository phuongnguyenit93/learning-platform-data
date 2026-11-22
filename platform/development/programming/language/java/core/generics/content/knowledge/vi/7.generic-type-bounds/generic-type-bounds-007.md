# Vì sao `<T extends Number>` không cung cấp toán tử số học trên `T`?

Một cách hiểu nhầm phổ biến khi học Java Generics là: nếu khai báo `<T extends Number>`, các biến kiểu `T` hẳn phải dùng được các toán tử số học `+`, `-`, `*` và `/` như số nguyên hoặc số thực. **Điều đó không đúng trong Java.**

`Number` là một **lớp trừu tượng** đại diện cho các kiểu số dưới dạng đối tượng. Giới hạn `T extends Number` cho phép compiler biết rằng một giá trị kiểu `T` có các phương thức của `Number`, chẳng hạn `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`. Nhưng giới hạn này **không biến `T` thành kiểu nguyên thủy**, không định nghĩa phép cộng cho mọi lớp con và không tạo toán tử tùy biến. Vì vậy biểu thức `a + b` với hai biến có kiểu `T extends Number` **không biên dịch**.

Bài học phân biệt kiểm tra kiểu generic với cơ chế toán tử số học của Java, giải thích vì sao unboxing không tự áp dụng cho `T`, cách chuyển đổi giá trị có chủ đích, và các phương án thiết kế API khi thật sự cần cộng/trừ/so sánh những số thuộc nhiều kiểu.

## 1. Đọc đúng ý nghĩa của `<T extends Number>`

Xét phương thức generic:

```java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
```

Đây là **phương thức minh họa** đặt bên trong một lớp Java. Ta có thể gọi phương thức với `Integer`, `Long`, `Double`, `BigDecimal`, `BigInteger` hoặc lớp con hợp lệ khác của `Number`. Lý do compiler chấp nhận `value.doubleValue()` là `Number` công bố phương thức đó.

Nhưng chữ ký:

```java
static <T extends Number> T add(T a, T b) {
    // return a + b; // LỖI BIÊN DỊCH
    throw new UnsupportedOperationException();
}
```

lại khác. Dòng `return a + b` bị chú thích vì toán tử cộng số học của Java không có cách áp dụng tổng quát lên hai **tham chiếu kiểu `T`**. Phần `throw` chỉ nhằm tạo thân phương thức hợp lệ để minh họa chữ ký; **không phải** một cách cài đặt phép cộng.

Cần phân biệt:

| Khái niệm | `<T extends Number>` có bảo đảm không? | Vì sao? |
|---|---|---|
| `T` là một kiểu tham chiếu thỏa `Number` | Có | Đây là **upper bound** của tham số kiểu. |
| `value.doubleValue()` gọi được | Có | Phương thức được khai báo trên `Number`. |
| `value.intValue()` gọi được | Có | Đây là phương thức của `Number`. |
| `a + b` với `T a, T b` | **Không** | Không có toán tử số học tổng quát trên các đối tượng `Number`. |
| `a.compareTo(b)` gọi được | **Không** chỉ từ bound này | `Number` không thực hiện `Comparable<Number>`. |
| Kết quả phép cộng tự có kiểu `T` | **Không** | Không có hợp đồng nào sinh một giá trị `T` mới. |
| Mọi phép chuyển sang `double` đều chính xác | **Không** | Chuyển đổi có thể làm tròn hoặc mất thông tin. |

**Upper bound là ràng buộc về các thành viên có thể sử dụng và quan hệ kiểu**, không phải lời hứa rằng mọi lớp con đều hỗ trợ cùng một toán tử với cùng quy tắc.

## 2. Java định nghĩa các toán tử số học cho những kiểu nào?

Các phép số học số nguyên/số thực như `+`, `-`, `*`, `/` chủ yếu hoạt động trên **kiểu số nguyên thủy** (`byte`, `short`, `char`, `int`, `long`, `float`, `double`) sau quy tắc chuyển đổi số nhị phân (*binary numeric promotion*). Java cũng hỗ trợ **unboxing** từ những lớp bao chuẩn tương ứng khi ngữ cảnh phép toán yêu cầu.

Ví dụ nằm trong một phương thức:

```java
int a = 4;
long b = 5L;
System.out.println(a + b); // 9, kết quả kiểu long

Integer x = 4;
Integer y = 5;
System.out.println(x + y); // 9: Integer tự unbox thành int
```

Ở ví dụ thứ hai, compiler **biết chính xác** `x` và `y` có kiểu `Integer`, lớp bao chuẩn của `int`. Vì thế nó áp dụng unboxing và phép cộng số nguyên.

Ngược lại:

```java
Number first = Integer.valueOf(4);
Number second = Integer.valueOf(5);

// System.out.println(first + second); // SAI: Number + Number
```

Dù hai đối tượng runtime đều là `Integer`, **kiểu tĩnh** của hai biến là `Number`. Java không định nghĩa unboxing từ kiểu `Number` nói chung. Compiler không tìm class runtime của từng toán hạng rồi quyết định toán tử ở lúc chạy.

Điều tương tự xảy ra với tham số kiểu `T` bị giới hạn bởi `Number`: tuy `T` hẹp hơn hoặc bằng `Number` theo bound, compiler vẫn không biết một phép cộng thống nhất cho mọi `T` hợp lệ.

### Những trường hợp dễ nhầm

- `Integer + Integer`: hợp lệ nhờ unboxing.
- `Double + Integer`: hợp lệ nhờ unboxing và numeric promotion.
- `Number + Number`: **không hợp lệ**.
- `T + T` trong `<T extends Number>`: **không hợp lệ**.
- `BigDecimal + BigDecimal`: **không hợp lệ** vì `BigDecimal` là lớp đối tượng không được Java nạp chồng toán tử `+`; phải gọi `add`.
- `String + object`: hợp lệ với ý nghĩa **nối chuỗi**, không phải cộng số; không được dùng hiện tượng đó làm bằng chứng `Number` hỗ trợ toán tử.

Không có cơ chế **operator overloading do người dùng định nghĩa** cho `+` trên một class Java tùy ý.

## 3. Ví dụ Java 17: cùng một giá trị, khác kiểu tĩnh, khác phép toán hợp lệ

Lưu chương trình sau thành **`NumberBoundaryDemo.java`**:

```java
public class NumberBoundaryDemo {
    public static void main(String[] args) {
        Integer wrappedA = 4;
        Integer wrappedB = 5;
        System.out.println(wrappedA + wrappedB);

        Number first = wrappedA;
        Number second = wrappedB;

        // Không được viết: first + second
        System.out.println(first.intValue() + second.intValue());
        System.out.println(first.doubleValue() + second.doubleValue());

        Number decimal = Double.valueOf(2.9);
        System.out.println(decimal.intValue());
        System.out.println(decimal.doubleValue());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NumberBoundaryDemo.java
java NumberBoundaryDemo
```

Kết quả `stdout`:

```text
9
9
9.0
2
2.9
```

Ở đây ba điểm rất đáng chú ý:

1. `wrappedA + wrappedB` biên dịch vì cả hai có kiểu tĩnh `Integer`, cho phép unboxing.
2. `first + second` sẽ không biên dịch vì cả hai có kiểu tĩnh `Number`. Gọi `intValue()` hoặc `doubleValue()` trước phép toán là **một chuyển đổi do lập trình viên chọn**, khác hoàn toàn với cộng trực tiếp trên `Number`.
3. `decimal.intValue()` trả `2`, không phải `2.9`. Chuyển đổi sang `int` bỏ phần thập phân (với giá trị hữu hạn trong khoảng hợp lệ); vì thế **chuyển kiểu có thể mất dữ liệu**.

Chương trình chứng minh rằng bản thân đối tượng runtime chứa số chưa đủ để compiler cho phép toán tử. **Kiểu tĩnh và hợp đồng của phép toán mới là yếu tố quyết định.**

## 4. Vì sao Java không thể tự định nghĩa phép cộng cho mọi `Number`?

`Number` là một abstraction cho nhiều loại số với đặc tính khác nhau. Các lớp con phổ biến gồm:

- `Byte`, `Short`, `Integer`, `Long`: lớp bao các số nguyên thủy tương ứng.
- `Float`, `Double`: biểu diễn số thực dấu phẩy động nhị phân.
- `BigInteger`: số nguyên có độ lớn tùy ý, với phép cộng `add(BigInteger)`.
- `BigDecimal`: số thập phân có độ chính xác thập phân được kiểm soát, với `add(BigDecimal)`.
- Các lớp con khác có thể do thư viện hoặc ứng dụng định nghĩa, với ý nghĩa và giới hạn riêng.

Nếu một phương thức nhận `Number a` và `Number b`, cần trả lời:

- Nếu `a` là `Integer` nhưng `b` là `Double` thì kết quả phải là `Integer`, `Double`, `BigDecimal` hay kiểu khác?
- Nếu cả hai là `Long` và tổng vượt giới hạn `long`, API phải tràn số, báo lỗi, hay trả `BigInteger`?
- Nếu `a` là `BigDecimal("0.1")`, phép cộng có cần giữ **độ chính xác thập phân** không?
- Nếu `a` là một lớp con `Number` tùy chỉnh, làm thế nào tạo một thể hiện cùng lớp để giữ kiểu `T`?
- Nếu có giá trị `null`, API nên từ chối, bỏ qua hay thay bằng zero?

Java không tự chọn một câu trả lời cho tất cả các trường hợp đó. `Number` **không khai báo `add(Number)`**, cũng không có phương thức abstract hoặc toán tử đảm bảo “trả về một `T` tương ứng”.

Vì vậy, nếu chỉ biết `T extends Number`, bạn biết **cách chuyển giá trị thành một vài kiểu primitive**, chứ chưa biết **cách thực hiện số học đóng trên `T`**.

## 5. Cách 1: chuyển sang một kiểu primitive đích rõ ràng

Nếu nghiệp vụ chấp nhận xử lý trên `double`, có thể viết utility:

```java
static <T extends Number> double sumAsDouble(
        java.util.List<T> numbers) {
    double total = 0.0;
    for (T number : numbers) {
        total += number.doubleValue();
    }
    return total;
}
```

Đây là **phương thức minh họa trong một lớp**. Nó nhận một danh sách các đối tượng kiểu `T` và cộng giá trị đã chuyển thành `double`. Hàm **trả `double` chứ không trả `T`**. Nếu cố trả `T` từ kết quả `double`, compiler không có cách chuyển ngược an toàn, chung cho mọi lớp con của `Number`.

### Chương trình hoàn chỉnh

Lưu **`SumAsDoubleDemo.java`**:

```java
import java.util.List;

public class SumAsDoubleDemo {
    static <T extends Number> double sumAsDouble(List<T> values) {
        double total = 0.0;
        for (T value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static double sumNumbers(List<? extends Number> values) {
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(1.5, 2.25);

        System.out.println(sumAsDouble(integers));
        System.out.println(sumAsDouble(decimals));
        System.out.println(sumNumbers(List.of(1, 2.5, 3L)));
    }
}
```

Chạy bằng Java 17:

```bash
javac -encoding UTF-8 SumAsDoubleDemo.java
java SumAsDoubleDemo
```

`stdout`:

```text
6.0
3.75
6.5
```

Phân tích:

- Trong `sumAsDouble`, `<T extends Number>` giúp phần tử danh sách có kiểu `T` và cho phép gọi `doubleValue()`.
- Trong `sumNumbers`, không cần một tham số kiểu được **đặt tên**, vì thuật toán chỉ đọc phần tử dưới dạng `Number` rồi trả `double`. `List<? extends Number>` đủ để nhận `List<Integer>`, `List<Double>` và những danh sách số khác.
- Cả hai phiên bản đều thực hiện **tính toán trên `double`**, không thực hiện phép cộng trực tiếp trên `T`.
- `List.of(1, 2.5, 3L)` là một danh sách không sửa đổi được chứa các đối tượng số, được chấp nhận bởi tham số `List<? extends Number>`.

Nếu phương thức không cần giữ mối quan hệ kiểu giữa các tham số hoặc giá trị trả về, **wildcard đơn giản có thể dễ đọc hơn việc khai báo `<T>`**. Chỉ dùng một tên tham số kiểu khi nó thật sự diễn đạt một quan hệ cần được bảo toàn.

## 6. Cảnh báo: `doubleValue()` không phải chuyển đổi chính xác cho mọi kiểu

Mặc dù `doubleValue()` có sẵn trên `Number`, đây **không phải phép chuyển đổi bảo toàn dữ liệu cho mọi số**. `double` là kiểu dấu phẩy động nhị phân IEEE 754 với khoảng 53 bit chính xác cho phần trị, không thể biểu diễn chính xác mọi số nguyên lớn hoặc mọi phân số thập phân.

Ví dụ:

```java
long exact = 9_007_199_254_740_993L;
double converted = Long.valueOf(exact).doubleValue();

System.out.println(converted == 9_007_199_254_740_992.0);
```

Đây là **đoạn mã trong một phương thức**; kết quả là `true` vì hai số nguyên liên tiếp ở vùng giá trị đó có thể bị làm tròn về cùng một giá trị `double`. Như vậy chuyển từ `long` lớn sang `double` có thể làm mất đơn vị cuối.

Một chương trình độc lập để minh họa:

Lưu tệp **`PrecisionDemo.java`**:

```java
import java.math.BigDecimal;

public class PrecisionDemo {
    public static void main(String[] args) {
        Number large = 9_007_199_254_740_993L;
        double approximate = large.doubleValue();

        System.out.println(
                approximate == 9_007_199_254_740_992.0);
        System.out.println(new BigDecimal("0.1")
                .add(new BigDecimal("0.2")));
        System.out.println(0.1 + 0.2);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PrecisionDemo.java
java PrecisionDemo
```

`stdout`:

```text
true
0.3
0.30000000000000004
```

**Cách chọn kiểu tính toán** phụ thuộc nghiệp vụ:

- Dữ liệu đo đạc hoặc mô phỏng chấp nhận sai số: `double` có thể phù hợp.
- Tiền tệ hoặc giá trị đòi độ chính xác thập phân: thường dùng `BigDecimal` với chính sách scale/rounding minh bạch.
- Số nguyên rất lớn cần chính xác: cân nhắc `BigInteger`.
- Số nguyên cố định: `int`/`long` có giới hạn; cân nhắc kiểm tra tràn bằng `Math.addExact` và các hàm liên quan.

Đừng đưa `doubleValue()` vào mọi generic utility chỉ để khiến phép `+` biên dịch; bạn đang **quyết định một mô hình số học mới**, không chỉ làm “cú pháp tương đương”.

## 7. Cách 2: gọi phép toán cụ thể của lớp số

Khi biết kiểu đầu vào, hãy ưu tiên API số học chuyên biệt của kiểu ấy thay vì cố viết `T + T`. Ví dụ:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

// Đoạn minh họa trong thân phương thức:
BigDecimal money = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

BigInteger big = new BigInteger("99999999999999999999")
        .add(BigInteger.ONE);
```

`BigDecimal.add(...)` và `BigInteger.add(...)` là các phương thức do các lớp cụ thể định nghĩa. Chúng **không** được khai báo bởi `Number`, nên một biểu thức kiểu `T extends Number` không thể gọi `a.add(b)` nếu không có bound khác thực sự cung cấp hợp đồng phương thức phù hợp.

Một ví dụ Java 17 hoàn chỉnh:

Lưu **`ConcreteArithmeticDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class ConcreteArithmeticDemo {
    public static void main(String[] args) {
        BigDecimal money = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        BigInteger huge = new BigInteger("99999999999999999999")
                .add(BigInteger.ONE);

        int safe = Math.addExact(20, 22);
        System.out.println(money);
        System.out.println(huge);
        System.out.println(safe);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConcreteArithmeticDemo.java
java ConcreteArithmeticDemo
```

`stdout`:

```text
0.3
100000000000000000000
42
```

Lưu ý tạo `BigDecimal` từ **chuỗi thập phân** như `"0.1"` để chỉ rõ giá trị mong muốn; viết `new BigDecimal(0.1)` thường mang theo xấp xỉ nhị phân của literal `double`. `BigDecimal.valueOf(0.1)` có hành vi phù hợp hơn cho nhiều tình huống, nhưng khi giá trị tài chính xuất phát từ văn bản thập phân thì constructor nhận chuỗi thường biểu đạt ý định rõ nhất.

## 8. Cách 3: truyền phép cộng từ bên ngoài bằng `BinaryOperator<T>`

Nếu thật sự muốn một thuật toán tổng quát **trả về đúng kiểu `T`**, thuật toán phải được cung cấp một cách cộng hai giá trị `T` thành một giá trị `T`. Trong Java, có thể biểu diễn khả năng này bằng một **strategy** hoặc hàm `BinaryOperator<T>`.

Chữ ký:

```java
static <T extends Number> T sum(
        java.util.List<T> values,
        T zero,
        java.util.function.BinaryOperator<T> add) {
    T result = zero;
    for (T value : values) {
        result = add.apply(result, value);
    }
    return result;
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp. Thuật toán không viết `result + value`. Nó gọi `add.apply(result, value)` và để người gọi quyết định số học ứng với loại `T`.

### Chương trình hoàn chỉnh: cùng thuật toán cho `Integer` và `BigDecimal`

Lưu **`NumericStrategyDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.function.BinaryOperator;

public class NumericStrategyDemo {
    static <T extends Number> T sum(
            List<T> values,
            T zero,
            BinaryOperator<T> addition) {
        T result = zero;
        for (T value : values) {
            result = addition.apply(result, value);
        }
        return result;
    }

    public static void main(String[] args) {
        Integer integerTotal = sum(
                List.of(1, 2, 3),
                0,
                Integer::sum);

        BigDecimal decimalTotal = sum(
                List.of(
                    new BigDecimal("0.1"),
                    new BigDecimal("0.2")
                ),
                BigDecimal.ZERO,
                BigDecimal::add);

        System.out.println(integerTotal);
        System.out.println(decimalTotal);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NumericStrategyDemo.java
java NumericStrategyDemo
```

`stdout`:

```text
6
0.3
```

Ở lời gọi thứ nhất, `T` được suy luận là `Integer` và người gọi truyền `Integer::sum`. Ở lời gọi thứ hai, `T` được suy luận là `BigDecimal` và phép cộng được truyền bằng `BigDecimal::add`.

**Vì sao cách này khả thi?** Java không cần biết cách cộng một `T` bất kỳ; nó chỉ cần đảm bảo hàm `BinaryOperator<T>` nhận hai giá trị `T` và trả về một giá trị `T`. Người gọi tự cung cấp định nghĩa phép cộng của kiểu cụ thể.

Một số lưu ý thiết kế:

- `zero` phải là giá trị khởi tạo phù hợp với phép cộng đã chọn; compiler kiểm tra **kiểu**, chứ không chứng minh đây là phần tử trung hòa toán học.
- `Integer::sum` dùng phép cộng kiểu `int`, nên **vẫn có thể tràn số**. Nếu yêu cầu phát hiện tràn, có thể dùng `Math::addExact` trong ngữ cảnh `Integer`.
- `addition` có thể do người dùng viết sai, ném ngoại lệ hoặc có tác dụng phụ. Kiểm tra nghiệp vụ vẫn cần thiết.
- Nếu danh sách chứa `null`, toán tử như `Integer::sum` có thể ném `NullPointerException` khi unboxing.
- Ràng buộc `T extends Number` không cần thiết về mặt cú pháp nếu utility chỉ thực hiện `addition.apply` mà không dùng thành viên `Number`. Có thể chọn `<T>` thuần túy nếu muốn thuật toán áp dụng cho các kiểu có phép kết hợp khác, chẳng hạn nối chuỗi.

**Điểm quan trọng:** `BinaryOperator<T>` là một giải pháp cung cấp **hợp đồng phép toán** từ bên ngoài. Nó không làm Java “tự hỗ trợ toán tử `+` trên `T`”.

## 9. Cách 4: thiết kế interface cung cấp phép cộng

Nếu ứng dụng sở hữu các lớp số custom hoặc domain riêng, có thể định nghĩa interface biểu thị khả năng cộng. Giới hạn generic sẽ dựa trên **hợp đồng thực sự có phương thức phép cộng**, không dựa vào `Number`.

Ví dụ một kiểu lượng nguyên:

```java
interface Addable<T> {
    T add(T other);
}
```

Đây là một interface generic; có thể có một lớp domain `Quantity` triển khai nó và định nghĩa `add`. Nếu muốn dùng tất cả phương thức của `Number` **và** khả năng cộng, khai báo kiểu ràng buộc kép:

```java
static <T extends Number & Addable<T>> T add(T a, T b) {
    return a.add(b);
}
```

Đây là **phương thức minh họa**, cần đặt trong lớp. `Number` là bound dạng lớp nên đứng đầu; `Addable<T>` là interface bound theo sau dấu `&`. Lúc này compiler chấp nhận `a.add(b)` **do interface `Addable<T>` khai báo phương thức `add`**, không phải vì `Number` cung cấp phép cộng.

### Ví dụ chạy được với `Quantity extends Number`

Lưu **`AddableNumberDemo.java`**:

```java
public class AddableNumberDemo {
    interface Addable<T> {
        T add(T other);
    }

    static final class Quantity extends Number
            implements Addable<Quantity> {
        private final int value;

        Quantity(int value) {
            this.value = value;
        }

        @Override
        public Quantity add(Quantity other) {
            return new Quantity(Math.addExact(value, other.value));
        }

        @Override
        public int intValue() {
            return value;
        }

        @Override
        public long longValue() {
            return value;
        }

        @Override
        public float floatValue() {
            return value;
        }

        @Override
        public double doubleValue() {
            return value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    static <T extends Number & Addable<T>> T plus(T a, T b) {
        return a.add(b);
    }

    public static void main(String[] args) {
        Quantity a = new Quantity(20);
        Quantity b = new Quantity(22);
        System.out.println(plus(a, b));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AddableNumberDemo.java
java AddableNumberDemo
```

`stdout`:

```text
42
```

Tại sao `plus(a,b)` biên dịch? `Quantity` **kế thừa `Number` và triển khai `Addable<Quantity>`**, nên thỏa đồng thời hai giới hạn. `Math.addExact` giúp phương thức `Quantity.add` ném `ArithmeticException` thay vì âm thầm tràn số khi cộng hai `int` vượt phạm vi.

Không nên ép những lớp JDK như `Integer` hoặc `BigDecimal` vào interface `Addable<T>` do mình định nghĩa: chúng không tự nhiên triển khai interface này, và ta cũng không thể sửa mã nguồn của chúng. Với lớp số sẵn có, cách **truyền `BinaryOperator<T>`** ở phần trước thường thuận tiện hơn.

## 10. Toán tử so sánh cũng cần xem xét riêng

`T extends Number` không đủ để gọi `compareTo`:

```java
static <T extends Number> boolean greater(T a, T b) {
    // return a.compareTo(b) > 0; // Sai: Number không khai báo compareTo
    return a.doubleValue() > b.doubleValue();
}
```

Phương thức trên là **mã minh họa có thân hợp lệ** nhưng so sánh sau chuyển đổi `double`, nên có thể bị mất chính xác. Nó không đồng nghĩa so sánh chính xác cho mọi loại `Number`.

Nếu cần thứ tự tự nhiên do đối tượng định nghĩa, thêm bound `Comparable`:

```java
static <T extends Number & Comparable<? super T>> T maximum(
        T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đoạn này là phương thức đặt trong một lớp. Compiler cho phép `compareTo` vì `Comparable<? super T>` cung cấp hợp đồng so sánh; `Number` vẫn chỉ cung cấp khả năng chuyển đổi số.

Một chương trình Java 17 đầy đủ:

Lưu **`NumberComparableDemo.java`**:

```java
public class NumberComparableDemo {
    static <T extends Number & Comparable<? super T>>
    T maximum(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        System.out.println(maximum(5, 9));
        System.out.println(maximum(2.5, 1.25));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NumberComparableDemo.java
java NumberComparableDemo
```

`stdout`:

```text
9
2.5
```

Cú pháp `<T extends Number & Comparable<? super T>>` thuộc nhóm **multiple bounds**. Nếu có class bound, nó phải đứng đầu; tiếp theo là các interface.

Một điểm khác: các wrapper như `Integer` và `Double` có `compareTo` nhưng không tự cho phép so sánh chéo bằng một `Comparable<Number>` chung. Đừng giả định `maximum(5, 2.5)` có một kiểu `T` phù hợp chỉ vì cả hai đều là số.

## 11. Số nguyên bị tràn: một phép cộng “hợp lệ” vẫn có thể sai nghiệp vụ

Ngay cả khi kiểu đã được chốt là `Integer`, toán tử cộng hoặc `Integer.sum` sử dụng phép cộng `int` thông thường. Java không tự động báo lỗi khi `int` tràn trong phép cộng thường.

Tạo **`OverflowDemo.java`**:

```java
public class OverflowDemo {
    public static void main(String[] args) {
        int ordinary = Integer.MAX_VALUE + 1;
        System.out.println(ordinary);

        try {
            int checked = Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println(checked);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 OverflowDemo.java
java OverflowDemo
```

`stdout`:

```text
-2147483648
overflow detected
```

Bài toán tổng quát không chỉ là làm phép cộng biên dịch, mà còn phải **định nghĩa chính sách số học**: chấp nhận tràn, từ chối tràn hay sử dụng kiểu có miền giá trị lớn hơn. `T extends Number` không giải quyết chính sách này.

Với số thập phân, cũng phải phân biệt lỗi làm tròn nhị phân của `double` với quy tắc scale/rounding của `BigDecimal`. Chẳng hạn `BigDecimal.divide` có thể ném `ArithmeticException` khi thương thập phân vô hạn nếu không chỉ định cách làm tròn phù hợp.

## 12. Khi nào không cần `<T extends Number>`?

Một generic bound chỉ có ích nếu nó thể hiện quan hệ kiểu mà API cần kiểm tra. Ví dụ:

```java
static double sum(List<? extends Number> values) {
    double total = 0.0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

Đây là **phương thức minh họa** cần import `java.util.List` và đặt trong lớp. Nếu không có mối liên hệ kiểu cần giữ giữa đầu vào, đầu ra hoặc nhiều tham số, `List<? extends Number>` đủ rõ: danh sách là nguồn cung cấp các giá trị `Number`, còn thuật toán chuyển sang `double`.

Ngược lại, muốn **giữ kiểu `T` từ đầu vào đến kết quả**:

```java
static <T extends Number> T reduce(
        List<T> values,
        T zero,
        java.util.function.BinaryOperator<T> op) {
    T result = zero;
    for (T value : values) {
        result = op.apply(result, value);
    }
    return result;
}
```

Ở đây tham số kiểu `T` quan trọng vì liên kết kiểu phần tử, giá trị khởi tạo, toán tử và kết quả. Tuy nhiên, bound `extends Number` vẫn có thể không cần nếu phép toán chỉ dùng `op.apply`. Nếu muốn hàm xử lý tổng quát mọi giá trị có phép kết hợp, chữ ký `<T> T reduce(...)` còn linh hoạt hơn.

Nguyên tắc lựa chọn:

- **Chỉ cần đọc số để chuyển thành primitive:** nhận `Number` hoặc `? extends Number` là đủ.
- **Cần kết quả cụ thể `double` hoặc `long`:** khai báo rõ kiểu kết quả; ghi chú độ chính xác và overflow.
- **Cần giữ `T`:** truyền phép toán như `BinaryOperator<T>`, hoặc ràng buộc bằng interface mang phép toán thực sự.
- **Cần số thập phân chính xác:** chọn `BigDecimal` làm hợp đồng đầu vào/đầu ra và sử dụng API của nó, thay vì generic hóa quá mức.
- **Cần so sánh:** yêu cầu `Comparable<? super T>` hoặc nhận một `Comparator<? super T>` thích hợp.

## 13. Các lỗi biên dịch hoặc thiết kế thường gặp

| Viết sai hoặc suy luận sai | Vấn đề thực sự | Cách xử lý |
|---|---|---|
| `static <T extends Number> T add(T a,T b) { return a+b; }` | Toán tử `+` không hoạt động với `T`. | Chọn một kiểu số cụ thể, hoặc truyền phép cộng. |
| `Number a=1, b=2; a+b` | `Number` không được Java tự unbox. | Chuyển đổi tường minh và chấp nhận quy tắc số học đã chọn. |
| `T total = 0;` | Literal nguyên thủy `0` không tự có kiểu `T` bất kỳ. | Nhận `T zero` từ caller hoặc factory phù hợp. |
| `return (T) Double.valueOf(a.doubleValue()+b.doubleValue());` | Ép kiểu không an toàn; kết quả không nhất thiết thuộc kiểu `T` yêu cầu. | Trả `double` hoặc dùng toán tử được truyền vào trả `T`. |
| `a.add(b)` với `T extends Number` | `Number` không khai báo `add`. | Dùng `BigDecimal` cụ thể hoặc bound có `Addable<T>`. |
| `a.compareTo(b)` với `T extends Number` | `Number` không khai báo `compareTo`. | Thêm bound `Comparable<? super T>` hoặc nhận `Comparator`. |
| Lấy `doubleValue()` rồi cho rằng không đổi dữ liệu | Mất chính xác với số lớn hoặc phần thập phân. | Kiểm tra yêu cầu, dùng `BigDecimal`/`BigInteger` khi thích hợp. |
| Dùng `Integer::sum` và nghĩ không tràn | Phép cộng `int` có thể overflow. | `Math::addExact`, kiểu lớn hơn hoặc chính sách tràn phù hợp. |
| Viết generic cho phép cộng tiền rồi tự chuyển qua `double` | Có thể làm sai giá trị tiền tệ. | Thiết kế API nhận/trả `BigDecimal` với thang đo và quy tắc làm tròn rõ. |
| Dùng toán tử `+` trên lớp `BigDecimal` | Java không nạp chồng toán tử số học cho class. | `a.add(b)`. |
| Cho rằng compiler quyết định phép `+` theo class runtime | Java kiểm tra toán tử qua kiểu tĩnh và quy tắc unboxing/numeric promotion. | Thiết kế chữ ký số học rõ ở compile time. |

Các ví dụ lỗi được dùng để **nhận diện lỗi**, không phải mã Java để chạy nguyên trạng.

## 14. Quy trình thiết kế utility số học generic

Khi cần viết một hàm xử lý nhiều loại số, hãy xác định lần lượt:

1. **Đầu vào là những kiểu số nào?** Chỉ `Integer` và `Long`, hay cả `BigDecimal`, `BigInteger`, `Double` và các lớp con `Number` khác?
2. **Kết quả phải có kiểu gì?** `double`, `BigDecimal`, hay giữ nguyên kiểu `T`? Đây là quyết định API quan trọng nhất.
3. **Độ chính xác được phép mất bao nhiêu?** Tính tiền, số đếm rất lớn và phép đo gần đúng không nên dùng cùng chính sách.
4. **Số học có bị tràn không?** Nếu dùng `int`/`long`, xem xét `Math.addExact` hoặc chuyển kiểu theo nghiệp vụ.
5. **Phép toán lấy từ đâu?** Nếu dùng `T extends Number`, chỉ có các phương thức chuyển đổi của `Number`. Nếu muốn cộng trả `T`, phải có toán tử/strategy bổ sung.
6. **Có cần giữ quan hệ kiểu bằng tham số `T` không?** Nếu chỉ đọc và đổi thành `double`, wildcard `? extends Number` có thể đơn giản hơn.
7. **Giá trị `null`, danh sách rỗng và ngoại lệ xử lý thế nào?** Các điều kiện runtime cần được mô tả riêng.
8. **Có cần kiểm tra cảnh báo compiler không?** Tránh raw type, unchecked cast hoặc ép kiểu vòng vo nhằm che lỗi `T + T`.
9. **Thử dữ liệu biên**: số âm, số rất lớn, số thập phân, danh sách rỗng, tràn số và các giá trị không được phép.

## 15. Tự kiểm tra

**Câu 1.** Vì sao `Integer a=1, b=2; a+b` biên dịch nhưng `Number a=1, b=2; a+b` không biên dịch, dù đối tượng runtime có thể cùng là `Integer`?

**Câu 2.** Với `<T extends Number>`, compiler bảo đảm có những phương thức chuyển đổi nào? Nó có bảo đảm `add(T)` hay `compareTo(T)` không?

**Câu 3.** Nếu viết `double total = a.doubleValue() + b.doubleValue()`, điều gì đã thay đổi về hợp đồng kết quả? Tại sao điều đó có thể gây lỗi khi xử lý tiền hoặc số nguyên lớn?

**Câu 4.** Làm thế nào viết một hàm cộng hai `T` và trả đúng `T` mà không ép kiểu không kiểm tra, khi các lớp như `Integer` và `BigDecimal` không chia sẻ `add` chung?

**Câu 5.** Phân biệt `<T extends Number>` và `<T extends Number & Addable<T>>` khi viết `a.add(b)`.

**Câu 6.** `<T extends Number & Comparable<? super T>>` giúp làm gì mà `<T extends Number>` không giúp được?

**Gợi ý đáp án:** (1) `Integer` là lớp bao được Java unbox, còn `Number` không nằm trong nhóm kiểu có chuyển đổi unboxing trực tiếp. (2) Những phương thức như `intValue()` và `doubleValue()`; `Number` không khai báo `add` hoặc `compareTo`. (3) Phép toán chuyển thành `double`, không trả `T` và có thể mất chính xác. (4) Truyền `BinaryOperator<T>`, hoặc dùng một interface số học do ứng dụng định nghĩa. (5) Bound thứ hai bổ sung hợp đồng `Addable<T>` có `add`. (6) Bound `Comparable` bảo đảm lời gọi `compareTo` hợp lệ để so sánh thứ tự tự nhiên.

**Ghi nhớ:** **`<T extends Number>` không có nghĩa `T` có toán tử số học.** Java chỉ cho gọi những thành viên được các bounds bảo đảm, trong khi toán tử `+`, `-`, `*`, `/` phụ thuộc các kiểu số nguyên thủy và quy tắc unboxing cụ thể. Muốn xử lý nhiều kiểu số, hãy **chọn rõ kiểu kết quả và chính sách chính xác**, hoặc **cung cấp một hợp đồng phép toán** thông qua interface hay strategy như `BinaryOperator<T>`. Tránh cast không kiểm tra để giả lập một phép cộng tổng quát mà Java Generics không thực sự bảo đảm.
