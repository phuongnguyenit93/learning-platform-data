# UnaryOperator<T> và BinaryOperator<T> trong Java

## 1. Hai dạng phép toán giữ nguyên kiểu dữ liệu

Trong gói **java.util.function**, **UnaryOperator<T>** và **BinaryOperator<T>** biểu diễn các hàm mà kiểu đầu ra trùng với kiểu đầu vào. Chúng là các phiên bản chuyên biệt của **Function** và **BiFunction**, rất hữu ích khi cần mô tả **biến đổi một giá trị** hoặc **kết hợp hai giá trị cùng kiểu**.

- **UnaryOperator<T>**: nhận **một T**, trả **một T**. Có thể đọc là **T → T**. Ví dụ: chuẩn hóa chuỗi, cập nhật trạng thái bất biến, làm tròn một giá trị.
- **BinaryOperator<T>**: nhận **hai T**, trả **một T**. Có thể đọc là **(T, T) → T**. Ví dụ: cộng hai số, chọn giá trị lớn hơn, hợp nhất hai cấu hình cùng kiểu theo quy tắc rõ ràng.

Cả hai đều là **functional interface**, nên có thể tạo implementation bằng lambda hoặc method reference. Chúng không đòi hỏi phép toán phải là toán học; tên “operator” mô tả **hình dạng hàm**.

~~~text
UnaryOperator<T>:
      T ──────► [ operation ] ──────► T

BinaryOperator<T>:
      T ──┐
          ├──► [ operation ] ──────► T
      T ──┘
~~~

Ví dụ:

~~~java
UnaryOperator<String> trim = String::strip;
BinaryOperator<Integer> add = Integer::sum;
~~~

Đây là **đoạn minh họa**, giả định import **java.util.function.UnaryOperator** và **java.util.function.BinaryOperator**. **trim.apply("  Java  ")** cho kết quả **"Java"**; **add.apply(4, 6)** cho kết quả **10**.

Cần phân biệt: kiểu kết quả bằng kiểu tham số **không đồng nghĩa** đối tượng kết quả phải là cùng một instance. Một UnaryOperator có thể trả đối tượng mới, trả nguyên đối tượng cũ, hoặc thay đổi đối tượng mutable rồi trả về. Chữ ký Java không tự bảo đảm tính bất biến, pure function hay thread safety.

## 2. Quan hệ với Function và BiFunction

Khai báo cốt lõi của hai interface trong Java có thể hiểu như sau:

~~~java
@FunctionalInterface
public interface UnaryOperator<T> extends Function<T, T> {
    static <T> UnaryOperator<T> identity() { /* implementation */ }
}

@FunctionalInterface
public interface BinaryOperator<T> extends BiFunction<T, T, T> {
    static <T> BinaryOperator<T> minBy(Comparator<? super T> comparator)
        { /* implementation */ }

    static <T> BinaryOperator<T> maxBy(Comparator<? super T> comparator)
        { /* implementation */ }
}
~~~

Đoạn trên là **sơ đồ chữ ký API**, cố ý lược bỏ thân phương thức và import; **không phải tệp Java độc lập để biên dịch**. Hai interface thực tế được cung cấp sẵn bởi JDK.

So sánh:

| Interface | Chữ ký chức năng | Phương thức SAM | Khi nào dùng |
| --- | --- | --- | --- |
| **Function<T,R>** | T → R | **R apply(T)** | Có thể đổi kiểu khi biến đổi |
| **UnaryOperator<T>** | T → T | **T apply(T)** | Biến đổi nhưng giữ cùng kiểu |
| **BiFunction<T,U,R>** | (T,U) → R | **R apply(T,U)** | Hai tham số có thể khác kiểu |
| **BinaryOperator<T>** | (T,T) → T | **T apply(T,T)** | Kết hợp hai giá trị cùng kiểu |

**UnaryOperator<T> extends Function<T,T>** có nghĩa là một UnaryOperator vẫn dùng được ở chỗ yêu cầu **Function<T,T>**. Tương tự, **BinaryOperator<T> extends BiFunction<T,T,T>**. Chúng đều dùng tên phương thức **apply** thừa hưởng từ interface cha.

**Không có quy tắc tự chuyển ngược** từ một biến kiểu **Function<T,T>** thành UnaryOperator hoặc từ **BiFunction<T,T,T>** thành BinaryOperator. Dù cùng hình dạng, đó vẫn là các kiểu interface khác nhau; muốn có UnaryOperator, bạn cần lambda/method reference có **target type** tương ứng hoặc một adapter đúng nghĩa.

Chẳng hạn:

~~~java
Function<String, String> transform = String::strip;
UnaryOperator<String> operator = transform::apply;
~~~

Đoạn minh họa này hợp lệ khi import hai interface. Gán trực tiếp **UnaryOperator<String> operator = transform;** không biên dịch, vì biến **transform** có kiểu tĩnh **Function<String,String>**, không nhất thiết là một UnaryOperator.

## 3. UnaryOperator<T>: biến đổi một giá trị mà vẫn giữ kiểu

**UnaryOperator<T>** rất phù hợp khi một giá trị đi qua nhiều bước chuẩn hóa. Ví dụ một mã hàng từ đầu vào có thể cần bỏ khoảng trắng, đổi chữ hoa, rồi gắn tiền tố.

Cách dùng với lambda:

~~~java
UnaryOperator<String> normalize =
        value -> value.strip().toUpperCase(Locale.ROOT);
~~~

Đây là đoạn đặt trong phương thức có import **java.util.Locale** và **java.util.function.UnaryOperator**. Nó trả một String sau chuẩn hóa; String là immutable, nên dữ liệu nguồn không bị sửa tại chỗ.

**Method reference** giúp ngắn gọn khi phép biến đổi đã được đóng gói thành một phương thức phù hợp:

~~~java
UnaryOperator<String> removeEdgeSpace = String::strip;
UnaryOperator<String> unchanged = UnaryOperator.identity();
~~~

**identity()** tạo phép toán đồng nhất: **identity.apply(x)** trả lại **x** (cùng tham chiếu nếu x là object). Nó có ích làm giá trị mặc định cho một bước biến đổi tùy chọn hoặc đơn vị trung hòa trong phép ghép chức năng, nhưng **không sao chép đối tượng**.

### 3.1. Kết hợp với compose() và andThen()

Vì UnaryOperator kế thừa **Function<T,T>**, nó sử dụng được **compose** và **andThen**:

- **f.andThen(g)** nghĩa là áp dụng **f trước**, sau đó **g**: **g(f(x))**.
- **f.compose(g)** nghĩa là áp dụng **g trước**, sau đó **f**: **f(g(x))**.

**Chú ý về kiểu trả về:** chữ ký kế thừa của **Function.andThen** và **Function.compose** trả về **Function**. Vì vậy, ngay cả khi hai toán tử cùng kiểu T, không được mặc nhiên gán kết quả của **f.andThen(g)** cho một biến **UnaryOperator<T>**.

~~~java
UnaryOperator<String> strip = String::strip;
UnaryOperator<String> upper =
        s -> s.toUpperCase(Locale.ROOT);

Function<String, String> pipeline = strip.andThen(upper);
// Nếu thực sự cần biến có kiểu UnaryOperator<String>:
UnaryOperator<String> chained =
        s -> upper.apply(strip.apply(s));
~~~

Đây là đoạn minh họa trong ngữ cảnh có import **Function**, **UnaryOperator**, **Locale**. Với đầu vào **"  java  "**, hai biến **pipeline** và **chained** đều trả **"JAVA"**.

Phân biệt **Function<T,T>** với **UnaryOperator<T>** ở đây là vấn đề **hợp đồng kiểu tĩnh**, không phải việc xử lý có khác kết quả. Cũng cần xét thứ tự biến đổi: **strip → upper** có thể khác **upper → strip** trong những pipeline thực tế có nhiều quy tắc phụ thuộc lẫn nhau.

## 4. BinaryOperator<T>: kết hợp hai giá trị cùng kiểu

**BinaryOperator<T>** dùng được khi phép tính nhận hai giá trị **cùng kiểu T** và kết quả cũng là **T**.

~~~java
BinaryOperator<Integer> sum = Integer::sum;
BinaryOperator<String> join = (left, right) -> left + "-" + right;
BinaryOperator<Integer> larger = Integer::max;
~~~

Các đoạn minh họa cần import **java.util.function.BinaryOperator**. Chúng có cách dùng:

~~~text
sum.apply(7, 5)      → 12
join.apply("A", "B") → "A-B"
larger.apply(7, 5)  → 7
~~~

**BinaryOperator<T> không đòi hỏi phép toán giao hoán hay kết hợp.** Với **Integer::sum**, về mặt toán học cộng số nguyên có tính giao hoán và kết hợp, nhưng với kiểu **int** còn tồn tại hành vi tràn số. Với **(a,b) -> a-b**, thứ tự tham số rất quan trọng; phép trừ không có tính kết hợp. Với **String** ghép văn bản, thứ tự cũng quan trọng dù phép nối có tính kết hợp khi xét nội dung String.

Nếu cần kết hợp **hai kiểu khác nhau** hoặc trả về **kiểu khác**, dùng **BiFunction<T,U,R>** phù hợp hơn. Chẳng hạn một **Order** và một mức thuế để tạo **Invoice** không thuộc dạng BinaryOperator<Order>, vì đầu ra không phải Order.

### 4.1. minBy() và maxBy()

**BinaryOperator.minBy(comparator)** trả về một toán tử chọn giá trị nhỏ hơn theo Comparator; **maxBy** chọn giá trị lớn hơn.

~~~java
BinaryOperator<Integer> min =
        BinaryOperator.minBy(Comparator.naturalOrder());
BinaryOperator<Integer> max =
        BinaryOperator.maxBy(Comparator.naturalOrder());
~~~

Đây là đoạn minh họa với import **java.util.Comparator** và **java.util.function.BinaryOperator**. **min.apply(8, 3)** cho **3**, **max.apply(8, 3)** cho **8**.

Với kiểu có nhiều thuộc tính, một Comparator có thể giúp định nghĩa rõ tiêu chí chọn; chẳng hạn chọn sản phẩm đắt nhất hoặc đơn hàng mới nhất. Nếu hai phần tử bằng nhau theo Comparator nhưng là hai object khác nhau, hợp đồng “min/max theo Comparator” không có nghĩa các object có cùng ý nghĩa nghiệp vụ. Nếu tie-breaker quan trọng, hãy đưa nó vào Comparator.

Nếu Comparator không nhất quán, thay đổi theo thời gian hoặc chịu tác động của trạng thái dùng chung, kết quả của việc chọn min/max có thể thiếu ổn định.

## 5. Chương trình Java 17 hoàn chỉnh: UnaryOperator và BinaryOperator

Tạo tệp **OperatorBasics.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.UnaryOperator;

public class OperatorBasics {
    public static void main(String[] args) {
        UnaryOperator<String> normalize =
                s -> s.strip().toLowerCase(Locale.ROOT);

        UnaryOperator<String> addPrefix =
                s -> "item:" + s;

        Function<String, String> normalizeAndPrefix =
                normalize.andThen(addPrefix);

        UnaryOperator<String> unchanged =
                UnaryOperator.identity();

        BinaryOperator<Integer> total = Integer::sum;
        BinaryOperator<Integer> greatest =
                BinaryOperator.maxBy(Comparator.naturalOrder());

        List<Integer> numbers = List.of(3, 6, 9);

        System.out.println(normalize.apply("  JAVA  "));
        System.out.println(normalizeAndPrefix.apply("  JAVA  "));
        System.out.println(unchanged.apply("hello"));
        System.out.println(total.apply(7, 5));
        System.out.println(greatest.apply(7, 5));
        System.out.println(numbers.stream().reduce(0, total));
        System.out.println(numbers.stream()
                .reduce(greatest)
                .orElse(-1));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 OperatorBasics.java
java OperatorBasics
~~~

Stdout:

~~~text
java
item:java
hello
12
7
18
9
~~~

Giải thích:

1. **normalize** nhận String và trả String đã loại khoảng trắng hai đầu, chuyển thành chữ thường với **Locale.ROOT** để tránh phụ thuộc locale mặc định của môi trường.
2. **normalize.andThen(addPrefix)** tạo **Function<String,String>**; đầu vào **"  JAVA  "** đi qua **normalize** trước rồi nhận tiền tố **"item:"**.
3. **UnaryOperator.identity()** không sửa nội dung đầu vào.
4. **total** và **greatest** đều nhận hai Integer, trả một Integer; BinaryOperator mô tả được hai hành vi khác nhau cùng chữ ký.
5. **reduce(0, total)** cộng từ giá trị đầu **0** qua ba phần tử: **3 + 6 + 9 = 18**.
6. **reduce(greatest)** trả **Optional<Integer>** vì stream có thể rỗng; với dữ liệu này giá trị lớn nhất là **9**, còn **orElse(-1)** chỉ là fallback của ví dụ.

Các hoạt động trên dùng Integer, nên có **boxing/unboxing** khi chạy qua API object. Ở quy mô xử lý lớn hoặc trong tác vụ hiệu năng nhạy cảm, nên xem xét primitive streams và primitive operator.

## 6. Vì sao BinaryOperator thường xuất hiện với Stream.reduce()?

**Stream.reduce** gom nhiều phần tử thành một giá trị bằng cách áp dụng phép kết hợp lặp đi lặp lại. Chữ ký của hai overload phổ biến là:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator);
T reduce(T identity, BinaryOperator<T> accumulator);
~~~

Đây là **chữ ký API rút gọn để giải thích**, không phải mã độc lập. Các overload khác của reduce còn có dạng ba tham số cho việc gom kiểu kết quả khác kiểu phần tử.

### 6.1. reduce(operator): không có identity

~~~java
Optional<Integer> maybeTotal =
        List.of(2, 4, 6).stream().reduce(Integer::sum);
~~~

Nếu stream có phần tử, Java kết hợp chúng để trả một **Optional** chứa kết quả. Nếu stream rỗng, kết quả là **Optional.empty()**. Không tự giả định rằng “tổng của stream rỗng phải là 0” khi bạn gọi overload **không có identity**. Đây là **đoạn minh họa** cần import **List**, **Optional**.

### 6.2. reduce(identity, operator): có giá trị trung hòa

~~~java
int total = List.of(2, 4, 6).stream()
        .reduce(0, Integer::sum);
~~~

Ở đây **0** là identity của phép cộng: với mọi x, **0 + x = x** và **x + 0 = x**. Với stream rỗng, overload này trả về **0**.

Dùng giá trị identity sai sẽ làm kết quả sai. Ví dụ, muốn tìm số lớn nhất từ danh sách có số âm, **reduce(0, Integer::max)** sai nếu tất cả phần tử đều âm: **0** được đưa vào như một ứng viên không có trong dữ liệu. Có thể dùng **reduce(Integer.MIN_VALUE, Integer::max)** cho kiểu int khi ngữ cảnh cho phép, hoặc **reduce(Integer::max)** để giữ semantics “có thể không có phần tử” qua Optional.

### 6.3. Tính kết hợp và xử lý song song

Trong các phép reduce của Stream, accumulator cần **associative**: cách đặt ngoặc không làm thay đổi kết quả.

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

Ví dụ **Integer::sum** có tính kết hợp theo số học mô-đun của int, dù kết quả có thể overflow so với phép cộng số nguyên toán học. **Integer::max** có tính kết hợp. Ngược lại, **(a,b) -> a-b** không có tính kết hợp:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Nếu viết phép trừ làm accumulator, kết quả có thể phụ thuộc vào cách nhóm phép toán, đặc biệt trong **parallel stream**. Đừng dùng một phép toán không kết hợp với reduce rồi suy ra rằng các mức song song luôn cho kết quả như vòng lặp tuần tự.

Đối với **double**, ngay cả phép cộng cũng có thể cho số cuối khác một chút nếu thay đổi cách nhóm, do sai số dấu phẩy động. Nếu bài toán đòi hỏi độ chính xác hoặc thứ tự cộng xác định, hãy thiết kế phù hợp thay vì mặc định song song là tương đương từng bit.

Một BinaryOperator dùng cho reduce nên **không có side effect, không sửa shared mutable state**, và trong những pipeline song song phải đáp ứng hợp đồng associative cùng identity đúng nghĩa. Nếu kết quả được tính bằng cách sửa một object tích lũy, hãy xem lại cách dùng collector hoặc vòng lặp phù hợp.

## 7. Chương trình thực tế: tính giá trị đơn hàng với BigDecimal

Đặt bài toán: mỗi dòng hàng có **đơn giá theo đơn vị tiền nhỏ nhất** và số lượng. Tính tổng các dòng, áp dụng mức chiết khấu **10%**, sau đó cộng **phí giao hàng cố định 15.000**.

Ở đây:
- Một phép **BinaryOperator<BigDecimal>** làm nhiệm vụ **cộng hai khoản tiền** cùng kiểu.
- Các phép **UnaryOperator<BigDecimal>** lần lượt **giảm giá** và **cộng phí** từ một khoản tiền sang khoản tiền mới.
- Ta không cần một interface riêng cho từng phép biến đổi đơn giản nếu ý nghĩa đã thể hiện rõ qua tên biến/phương thức.

Tạo tệp **OrderAmountDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.function.BinaryOperator;
import java.util.function.UnaryOperator;

record CartLine(String sku, long unitPrice, int quantity) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be non-negative");
        }
    }

    long subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

public class OrderAmountDemo {
    public static void main(String[] args) {
        List<CartLine> lines = List.of(
                new CartLine("BOOK", 50_000L, 2),
                new CartLine("PEN", 40_000L, 1)
        );

        BinaryOperator<BigDecimal> add = BigDecimal::add;

        UnaryOperator<BigDecimal> discount10 =
                amount -> amount.multiply(new BigDecimal("0.90"));
        UnaryOperator<BigDecimal> deliveryFee =
                amount -> amount.add(new BigDecimal("15000"));

        BigDecimal subtotal = lines.stream()
                .map(line -> BigDecimal.valueOf(line.subtotal()))
                .reduce(BigDecimal.ZERO, add);

        BigDecimal afterDiscount = discount10.apply(subtotal);
        BigDecimal finalAmount = deliveryFee.apply(afterDiscount);

        System.out.println("Subtotal: " + subtotal);
        System.out.println("Discounted: " + afterDiscount);
        System.out.println("Payable: " + finalAmount);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OrderAmountDemo.java
java OrderAmountDemo
~~~

Stdout:

~~~text
Subtotal: 140000
Discounted: 126000.00
Payable: 141000.00
~~~

Diễn giải số học:

- Dòng **BOOK**: **50.000 × 2 = 100.000**.
- Dòng **PEN**: **40.000 × 1 = 40.000**.
- **subtotal = 140.000**; giảm 10% bằng nhân **0.90** được **126.000,00**; cộng **15.000** cho kết quả **141.000,00**.
- **BigDecimal** giữ giá trị thập phân chính xác cho các phép tính được chỉ định. **new BigDecimal("0.90")** giữ scale 2, nên phép nhân và phép cộng thể hiện **.00** khi in bằng **toString()**.

Đây là **ví dụ học tập**, chưa thể hiện quy tắc thuế, giới hạn voucher, đơn vị tiền cụ thể hay cách làm tròn nếu có chia số. Trong hệ thống thanh toán, cần định nghĩa **đơn vị tiền, chính sách round, trình tự giảm giá và tính phí** một cách chính thức. **Math.multiplyExact** giúp phát hiện overflow ở phép nhân đơn giá với số lượng trước khi chuyển thành BigDecimal; trường hợp cần miền số lớn hơn long phải thay đổi thiết kế lưu trữ.

**Điểm chính về kiểu:** **discount10** là UnaryOperator<BigDecimal> bởi vì đầu vào và đầu ra đều là BigDecimal; **add** là BinaryOperator<BigDecimal> bởi vì hai khoản tiền cùng kiểu được hợp nhất thành một khoản tiền cùng kiểu.

## 8. Primitive specialization: tránh boxing khi phù hợp

**UnaryOperator<Integer>** và **BinaryOperator<Integer>** làm việc với kiểu tham chiếu **Integer**. Khi xử lý nhiều giá trị primitive **int**, Java có các phiên bản chuyên biệt:

| Kiểu chuyên biệt | Phương thức SAM | Ý nghĩa |
| --- | --- | --- |
| **IntUnaryOperator** | **int applyAsInt(int)** | int → int |
| **LongUnaryOperator** | **long applyAsLong(long)** | long → long |
| **DoubleUnaryOperator** | **double applyAsDouble(double)** | double → double |
| **IntBinaryOperator** | **int applyAsInt(int,int)** | (int,int) → int |
| **LongBinaryOperator** | **long applyAsLong(long,long)** | (long,long) → long |
| **DoubleBinaryOperator** | **double applyAsDouble(double,double)** | (double,double) → double |

Ví dụ trong phương thức đã import **java.util.function.IntUnaryOperator** và **java.util.function.IntBinaryOperator**:

~~~java
IntUnaryOperator twice = x -> x * 2;
IntBinaryOperator sum = Integer::sum;

System.out.println(twice.applyAsInt(6));  // 12
System.out.println(sum.applyAsInt(6, 7)); // 13
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. Với **IntStream**, ta có thể dùng trực tiếp **IntUnaryOperator** trong **map** và **IntBinaryOperator** trong **reduce**:

~~~java
int total = IntStream.of(1, 2, 3)
        .map(x -> x * 2)
        .reduce(0, Integer::sum);

System.out.println(total); // 12
~~~

Đoạn minh họa cần import **java.util.stream.IntStream**. Việc dùng primitive stream giúp giảm boxing trong phần xử lý dữ liệu primitive; tuy nhiên hiệu năng thực tế vẫn phụ thuộc thuật toán, JVM, dữ liệu và workload. Không nên chuyển sang primitive interface khi nghiệp vụ cần **BigDecimal** hoặc một object có cấu trúc để biểu diễn đúng miền dữ liệu.

## 9. Những điểm dễ nhầm khi kết hợp operator

### 9.1. Đừng dùng UnaryOperator khi có đổi kiểu

~~~java
Function<String, Integer> length = String::length;
~~~

Đoạn minh họa cần import **Function**. Phép này là **String → Integer**, vì thế không phải UnaryOperator<String>. Tương tự, phép chuyển **String → BigDecimal** cần Function<String,BigDecimal> hoặc kiểu nghiệp vụ chuyên biệt.

### 9.2. Đừng dùng BinaryOperator khi hai đầu vào khác kiểu

~~~java
BiFunction<String, Integer, String> repeat =
        String::repeat;
~~~

Đoạn minh họa cần import **BiFunction**; **String.repeat(int)** phù hợp kiểu **(String,Integer) → String** nhờ unboxing Integer sang int. Vì hai đầu vào không cùng kiểu, BinaryOperator<String> không thích hợp.

### 9.3. Không được đồng nhất “cùng kiểu” với “cùng object”

~~~java
UnaryOperator<StringBuilder> appendBang = b -> b.append("!");
~~~

Đây là đoạn minh họa cần import **UnaryOperator**. Nó thay đổi object **StringBuilder** được truyền vào; hàm không thuần và có thể gây tác động phụ nếu chia sẻ đối tượng. Nếu muốn chuyển đổi bất biến, hãy xác định kiểu dữ liệu thích hợp và tạo một giá trị mới.

### 9.4. Không dùng operator với null mà không có chính sách

**String::strip**, **Integer::sum**, **BigDecimal::add** đều có các tình huống không chấp nhận null; một null có thể gây **NullPointerException**. Kiểu **UnaryOperator<String>** không tự diễn đạt rằng đầu vào có được null hay không.

Với pipeline xử lý dữ liệu từ bên ngoài, xác định liệu null phải bị loại, được thay bằng mặc định hay được báo lỗi. Ví dụ **Stream.filter(Objects::nonNull)** có thể loại null trước thao tác áp dụng, nhưng chỉ đúng khi chính sách nghiệp vụ cho phép bỏ dữ liệu đó.

### 9.5. Không cho rằng mọi BinaryOperator đều dùng tốt với reduce

Một operator có thể hoàn toàn hợp lệ khi gọi trực tiếp nhưng không phù hợp với reduction song song. Để dùng reduce đáng tin cậy, phải xét tính kết hợp, identity, side effect và kiểu dữ liệu. Ví dụ phép trừ là BinaryOperator<Integer> hợp lệ nhưng **không associative**.

### 9.6. Không cho rằng Function.andThen trả lại UnaryOperator

Đây là bẫy kiểu tĩnh thường gặp. Kể cả khi cả hai thao tác là UnaryOperator<T>, **andThen** thừa hưởng từ **Function** trả **Function<T,T>**. Nếu cần chính xác UnaryOperator<T>, bọc bằng lambda:

~~~java
UnaryOperator<String> first = String::strip;
UnaryOperator<String> second = String::toUpperCase;

UnaryOperator<String> combined =
        value -> second.apply(first.apply(value));
~~~

Đây là đoạn minh họa có import **UnaryOperator**. Nếu việc chuyển chữ hoa cần ổn định giữa các locale, hãy dùng lambda gọi **toUpperCase(Locale.ROOT)** như các chương trình đầy đủ phía trên.

## 10. Khi nào nên chọn operator, Function hay interface nghiệp vụ riêng?

**Chọn UnaryOperator<T>** khi hành vi nhận một giá trị rồi trả cùng kiểu, ví dụ chuỗi chuẩn hóa, trạng thái bất biến được cập nhật, giá trị tiền được điều chỉnh.

**Chọn BinaryOperator<T>** khi hành vi kết hợp hai giá trị cùng kiểu thành một giá trị cùng kiểu, ví dụ cộng, min/max, hợp nhất hai cấu hình theo chính sách đã định nghĩa. Nếu dùng với reduce, hãy xác nhận đặc tính đại số phù hợp.

**Chọn Function<T,R>/BiFunction<T,U,R>** khi đầu vào hoặc đầu ra khác kiểu. Dùng kiểu tổng quát giúp biểu diễn đúng hợp đồng mà không ép mọi thứ về một loại dữ liệu.

**Tạo functional interface riêng** khi hành vi có tên nghiệp vụ quan trọng, cần tài liệu/ngoại lệ/quy tắc đặc thù và được dùng như một hợp đồng API. Một **UnaryOperator<T>** dùng trong hàm cục bộ là đủ cho phép chuẩn hóa; nhưng một hợp đồng công khai như **ExchangeRatePolicy.convert(amount)** có thể xứng đáng được biểu diễn bằng kiểu chuyên biệt nếu ngữ nghĩa, tiền tệ, nguồn tỷ giá và lỗi cần định nghĩa rõ.

Không có một lựa chọn “luôn tốt nhất”. Hãy ưu tiên **chữ ký đúng, ý nghĩa rõ và hành vi kiểm chứng được**.

## 11. Bài tập thực hành

1. Viết **UnaryOperator<String>** chuẩn hóa một mã khách hàng: bỏ khoảng trắng đầu/cuối, đổi sang chữ hoa bằng Locale.ROOT; thử với **"  ab-12  "**.
2. Viết **BinaryOperator<Integer>** chọn giá trị nhỏ nhất, so sánh kết quả của lambda **(a,b) -> Math.min(a,b)** với **BinaryOperator.minBy(Comparator.naturalOrder())**.
3. Tạo hai UnaryOperator<String> **first** và **second**, ghép bằng **andThen**. Kiểm tra kiểu của kết quả bằng cách gán cho **Function<String,String>**; giải thích vì sao không gán trực tiếp cho **UnaryOperator<String>**.
4. Cho danh sách **[-7, -3, -10]**, so sánh **reduce(0, Integer::max)** và **reduce(Integer::max)**. Giải thích vì sao kết quả đầu có thể sai ý nghĩa “max của dữ liệu”.
5. Viết **BinaryOperator<Integer>** cho phép trừ, rồi kiểm tra **(10 - 3) - 2** với **10 - (3 - 2)**. Rút ra điều kiện phải xét trước khi dùng operator trong parallel reduction.
6. Chuyển một phép tính dùng **UnaryOperator<Integer>** trên **Stream<Integer>** sang **IntUnaryOperator** và **IntStream**; phân biệt mục tiêu giảm boxing với tính đúng nghiệp vụ.
7. Mở rộng bài toán số tiền bằng chính sách làm tròn và thuế rõ ràng; đánh giá xem chuỗi UnaryOperator<BigDecimal> còn đủ diễn đạt hợp đồng hay cần kiểu nghiệp vụ riêng.

## 12. Ghi nhớ

**UnaryOperator<T>** là **Function<T,T>** với ý định “một giá trị vào, một giá trị cùng kiểu ra”. **BinaryOperator<T>** là **BiFunction<T,T,T>** với ý định “hai giá trị cùng kiểu vào, một giá trị cùng kiểu ra”. Cả hai dùng lambda, method reference và phương thức **apply**.

Điểm thực hành quan trọng nhất là **chọn đúng kiểu cho hợp đồng**, phân biệt kết hợp hàm với phép kết hợp giá trị, hiểu **identity/associativity** khi áp dụng BinaryOperator cho **Stream.reduce**, và kiểm soát null, side effect, tràn số cùng giới hạn hiệu năng. Khi cần xử lý primitive số lượng lớn, hãy cân nhắc các dạng **Int/Long/DoubleUnaryOperator** và **Int/Long/DoubleBinaryOperator**.