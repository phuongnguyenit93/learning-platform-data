# Giới hạn kiểu và nhiều ràng buộc với extends

Generics cho phép lớp, interface và phương thức trong Java 27 làm việc với nhiều kiểu dữ liệu mà vẫn được trình biên dịch kiểm tra kiểu. Tuy nhiên, một kiểu tổng quát như `T` không mặc nhiên có các phương thức đặc thù. **Giới hạn kiểu (type bound)** cho biết những kiểu thực tế nào được phép thay cho `T` và những khả năng nào mã generic được phép sử dụng.

Ví dụ, một thuật toán cần đối tượng vừa là `Number` vừa có khả năng so sánh có thể khai báo `<T extends Number & Comparable<T>>`. Đây là **nhiều ràng buộc (multiple bounds)**: kiểu thực tế phải thỏa mãn **tất cả** ràng buộc, không phải chỉ một trong số đó.

Bài thuộc chương **Generics và hệ thống kiểu** trong module **Java 27 và các kiến thức liên quan**. Các cú pháp, quy tắc và ví dụ dưới đây dựa trên Java Language Specification (JLS) của Java SE 27. Chúng là kiến thức ngôn ngữ hiện hành, không cần bật Preview và không dùng kỹ thuật legacy như raw types để lách kiểm tra kiểu.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt generic không giới hạn, generic có upper bound và generic có nhiều bound.
- Đọc và viết `<T extends SomeClass>`, `<T extends SomeInterface>` và `<T extends Base & InterfaceA & InterfaceB>`.
- Giải thích vì sao từ khóa `extends` được dùng cả với interface trong khai báo type parameter.
- Xác định khi nào một kiểu thực tế thỏa mãn toàn bộ các bound và khi nào trình biên dịch từ chối.
- Phân biệt `<T extends B>` với wildcard `? extends B` và `? super B`.
- Hiểu các giới hạn của type erasure, ý nghĩa của bound đầu tiên và sự khác nhau giữa kiểm tra lúc biên dịch với thông tin kiểu lúc chạy.
- Thiết kế API có ràng buộc đủ chặt để an toàn nhưng không khóa chặt các implementation hợp lệ.

## 2. Từ generic không giới hạn đến bounded type parameter

### 2.1. Generic không khai báo bound

Xét một lớp lưu một giá trị:

~~~java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Có thể tạo các phiên bản với kiểu tham chiếu khác nhau:

~~~java
Box<String> text = new Box<>("Java 27");
Box<Integer> count = new Box<>(42);

String name = text.get();
int number = count.get(); // unboxing Integer -> int
~~~

Vì `T` không có bound tường minh, upper bound ngầm định của nó là `Object`. Bên trong `Box<T>`, trình biên dịch chỉ bảo đảm những thao tác hợp lệ đối với mọi `T` thỏa mãn bound này, chẳng hạn các phương thức public của `Object`. Không thể tự gọi `value.doubleValue()`, vì không phải kiểu nào cũng có phương thức đó.

Ví dụ không hợp lệ:

~~~java
final class InvalidBox<T> {
    private final T value;

    InvalidBox(T value) {
        this.value = value;
    }

    // Không biên dịch: T không được bảo đảm là Number.
    // double asDouble() {
    //     return value.doubleValue();
    // }
}
~~~

Cách giải quyết là công bố đúng yêu cầu về kiểu, thay vì ép kiểu tùy tiện trong thân phương thức.

### 2.2. Một upper bound là class

~~~java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    double asDouble() {
        return value.doubleValue();
    }

    T get() {
        return value;
    }
}
~~~

`T extends Number` có nghĩa là kiểu thay thế cho `T` phải là `Number` hoặc subtype của `Number`. Vì `Number` công bố `doubleValue()`, phương thức trên hợp lệ về mặt kiểu.

~~~java
NumericBox<Integer> a = new NumericBox<>(42);
NumericBox<Double> b = new NumericBox<>(3.5);

// Không hợp lệ: String không extends Number.
// NumericBox<String> c = new NumericBox<>("42");
~~~

Bound giúp **kiểm tra sai kiểu tại thời điểm biên dịch** và mô tả rõ contract của API. Nó không bảo đảm phép chuyển sang `double` giữ nguyên mọi độ chính xác, bởi đó là tính chất của `Number.doubleValue()` và kiểu số cụ thể.

### 2.3. Một upper bound là interface

`extends` trong khai báo type parameter cũng được dùng khi bound là **interface**:

~~~java
static <T extends CharSequence> int lengthOf(T input) {
    return input.length();
}
~~~

Phương thức chấp nhận `String`, `StringBuilder` và những kiểu khác triển khai `CharSequence`:

~~~java
int a = lengthOf("Java");
int b = lengthOf(new StringBuilder("Generics"));
~~~

Cú pháp `<T implements CharSequence>` **không hợp lệ**. `implements` dùng trong khai báo một class triển khai interface; còn trong **type parameter bound**, Java dùng `extends` cho cả class và interface.

### 2.4. Upper bound không phải kiểu cụ thể duy nhất

`T extends Number` không nói rằng `T` phải đúng bằng `Number`. Nó cho phép một kiểu con như `Integer` hoặc `BigDecimal`. Kiểu thực tế vẫn được theo dõi bởi compiler:

~~~java
static <T extends Number> T identity(T input) {
    return input;
}

Integer first = identity(10);
java.math.BigDecimal second =
        identity(new java.math.BigDecimal("12.50"));
~~~

Generic method bảo toàn quan hệ giữa kiểu đối số và kiểu kết quả qua `T`; nếu chỉ trả về `Number`, caller có thể phải xử lý kiểu rộng hơn.

## 3. Multiple bounds: một kiểu phải thỏa mãn nhiều contract

### 3.1. Cú pháp chuẩn

Cú pháp tổng quát cho khai báo có nhiều bound là:

~~~java
class Repository<T extends BaseClass & InterfaceOne & InterfaceTwo> {
    // T có thể sử dụng các thành viên hợp lệ của cả ba bound.
}
~~~

Nếu không cần class bound, có thể bắt đầu bằng một interface:

~~~java
class Processor<T extends InterfaceOne & InterfaceTwo> {
}
~~~

Dấu `&` ở đây mô tả **intersection type**: một giá trị kiểu `T` phải thuộc đồng thời các kiểu đã liệt kê. Nó **không** biểu thị phép AND boolean thực thi lúc chạy và cũng không tạo một object mới kết hợp các kiểu.

Có thể dùng nhiều hơn hai bound nếu mỗi bound đều hợp lệ và không xung đột. `extends` chỉ viết **một lần**:

~~~java
// Hợp lệ về cú pháp nếu các kiểu được định nghĩa và tương thích:
// <T extends BaseClass & InterfaceOne & InterfaceTwo>

// Sai cú pháp:
// <T extends BaseClass extends InterfaceOne>
// <T extends BaseClass implements InterfaceOne>
~~~

### 3.2. Bound class phải đứng đầu

Nếu có một class bound, nó phải đứng ở vị trí **đầu tiên**; các bound phía sau dấu `&` phải là interface:

~~~java
import java.io.Serializable;

final class NumericHandler<
        T extends Number & Comparable<T> & Serializable> {
    private final T input;

    NumericHandler(T input) {
        this.input = input;
    }

    T get() {
        return input;
    }
}
~~~

`Number` là class, `Comparable<T>` và `Serializable` là interface. Đây là cách sắp xếp hợp lệ. Một kiểu như `Integer` đáp ứng cả ba yêu cầu.

Ví dụ sắp xếp sai:

~~~java
// Sai: Number là class nhưng không nằm đầu.
// class Invalid<T extends Comparable<T> & Number> { }

// Sai: có hai class bound.
// class Invalid<T extends Number & Thread> { }
~~~

Java không hỗ trợ đa kế thừa class. Multiple bounds không tạo ngoại lệ cho quy tắc đó.

### 3.3. Nhiều interface bound

Có thể yêu cầu một object có nhiều khả năng mà không buộc nó kế thừa từ một lớp cơ sở ứng dụng:

~~~java
interface Named {
    String name();
}

interface Validatable {
    boolean valid();
}

record UserCommand(String name, boolean valid)
        implements Named, Validatable {
}

static <T extends Named & Validatable> String acceptedName(T input) {
    if (!input.valid()) {
        throw new IllegalArgumentException("Invalid input");
    }

    return input.name();
}
~~~

`UserCommand` là record triển khai hai interface. Kiểu của `input` trong `acceptedName` được compiler hiểu là thỏa mãn **cả** `Named` và `Validatable`. Vì vậy, cả `input.name()` và `input.valid()` đều được phép.

~~~java
String name = acceptedName(new UserCommand("deploy", true));
~~~

Một implementation chỉ hỗ trợ `Named` nhưng không hỗ trợ `Validatable` sẽ không thể truyền vào `acceptedName`.

### 3.4. Bảng quy tắc multiple bounds

| Khai báo | Kết luận | Lý do |
|---|---|---|
| `<T extends Number>` | Hợp lệ | Một class upper bound |
| `<T extends CharSequence>` | Hợp lệ | Một interface upper bound |
| `<T extends Number & Comparable<T>>` | Hợp lệ | Class trước, interface sau |
| `<T extends Named & Validatable>` | Hợp lệ | Hai interface |
| `<T extends Runnable & AutoCloseable>` | Hợp lệ | Hai interface, không có class bound |
| `<T extends Comparable<T> & Number>` | Không hợp lệ | Class `Number` đứng sau dấu `&` |
| `<T extends Number & Thread>` | Không hợp lệ | Bound bổ sung không được là class |
| `<T implements Runnable>` | Không hợp lệ | Type parameter bound dùng `extends` |
| `<T extends Comparable<String> & Comparable<Integer>>` | Không hợp lệ | Hai bound có cùng erasure và tham số hóa không tương thích |

Quy tắc còn yêu cầu erasure của từng bound phải khác nhau; một type variable không được đồng thời là subtype của hai cách tham số hóa không tương thích của cùng một generic interface.

### 3.5. Một class bound vẫn không cho phép tất cả subtype

Trong khai báo:

~~~java
static <T extends Number & Comparable<T>> T larger(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
~~~

`Number` tự nó **không** triển khai `Comparable<Number>`. Bởi vậy, giá trị có kiểu khai báo là `Number` không tự thỏa mãn bound `Comparable<T>`.

~~~java
Integer a = larger(10, 20); // hợp lệ
Double b = larger(1.5, 3.0); // hợp lệ

Number left = Integer.valueOf(10);
Number right = Integer.valueOf(20);

// Không hợp lệ với khai báo trên: Number không đáp ứng Comparable<Number>.
// Number wrong = larger(left, right);
~~~

Hãy chú ý đến **kiểu tĩnh tại vị trí gọi**. Dù object thực tế có thể là `Integer`, một biến được khai báo `Number` không cho compiler quyền giả định nó triển khai `Comparable<Number>`.

## 4. Khai báo bound trên class, interface và method

### 4.1. Generic class

Một bound có thể ràng buộc tất cả đối tượng được tạo từ generic class:

~~~java
final class NumberPair<T extends Number & Comparable<T>> {
    private final T first;
    private final T second;

    NumberPair(T first, T second) {
        this.first = java.util.Objects.requireNonNull(first);
        this.second = java.util.Objects.requireNonNull(second);
    }

    T larger() {
        return first.compareTo(second) >= 0 ? first : second;
    }

    double sumAsDouble() {
        return first.doubleValue() + second.doubleValue();
    }
}
~~~

Trong cả class, `T` có thể dùng các phương thức của `Number` và `Comparable<T>`. Ví dụ:

~~~java
NumberPair<Integer> numbers = new NumberPair<>(12, 35);
System.out.println(numbers.larger());      // 35
System.out.println(numbers.sumAsDouble()); // 47.0
~~~

Dùng `doubleValue()` ở đây là minh họa cách truy cập thành viên của bound, không phải hướng dẫn dùng double để tính tiền hoặc xử lý số nguyên lớn cần độ chính xác tuyệt đối.

### 4.2. Generic interface

Interface cũng có type parameter với bound:

~~~java
interface Metric<T extends Number & Comparable<T>> {
    T measure();
}
~~~

Implementation phải chọn một kiểu hợp lệ:

~~~java
final class TemperatureMetric implements Metric<Double> {
    @Override
    public Double measure() {
        return 36.5;
    }
}
~~~

Không phải interface `Metric` mở rộng từ `Number`; **kiểu tham số T** mới phải đáp ứng các bound đã khai báo.

### 4.3. Generic method

Generic method khai báo type parameter riêng **trước kiểu trả về**:

~~~java
static <T extends Number & Comparable<T>> T max(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

`<T extends ...>` trước `T max` là phần khai báo type parameter. Nó khác với phần tham số thông thường `(T left, T right)`.

Phương thức có thể nằm trong class không generic. Compiler thường suy ra `T` từ các đối số nên caller không cần viết type argument tường minh:

~~~java
Integer a = max(100, 200);
java.math.BigDecimal b = max(
        new java.math.BigDecimal("19.95"),
        new java.math.BigDecimal("21.50")
);
~~~

Có thể chỉ định kiểu tường minh nếu thật sự cần:

~~~java
Integer value = BoundsDemo.<Integer>max(1, 2);
~~~

Ở đây `BoundsDemo` là tên class chứa method `max`; lời gọi tường minh `<Integer>` cho biết type argument của generic method. Phần lớn trường hợp nên để compiler suy luận nếu kết quả rõ ràng.

### 4.4. Nhiều type parameter khác với nhiều bound

Các dấu phẩy `,` phân tách **các biến kiểu khác nhau**; dấu `&` bổ sung **nhiều bound cho cùng một biến kiểu**:

~~~java
static <K extends Comparable<K>, V extends java.io.Serializable>
void store(K key, V value) {
    System.out.println(key + " -> " + value);
}
~~~

Phương thức trên khai báo hai type parameter riêng `K` và `V`. Nó **không** yêu cầu `K` phải triển khai `Serializable` hoặc `V` phải triển khai `Comparable<V>`.

Ngược lại:

~~~java
static <T extends Comparable<T> & java.io.Serializable>
void storeOne(T item) {
    System.out.println(item);
}
~~~

Chỉ có một `T` và chính kiểu `T` phải thỏa mãn cả hai interface.

### 4.5. Một type variable có thể bị bound bởi type variable khác

Khai báo sau hợp lệ vì `U` có bound là type variable `T`:

~~~java
static <T, U extends T> T upcast(U value) {
    return value;
}
~~~

`U` phải là subtype của `T`. Nếu dùng type variable làm bound trực tiếp, ngữ pháp của Java không cho thêm các bound `&` ở sau type variable đó theo cách giống class/interface. Các quan hệ phức tạp nên được mô tả bằng các interface hoặc tham số kiểu phù hợp thay vì cố lách quy tắc cú pháp.

## 5. Ví dụ tự chứa: sử dụng một và nhiều ràng buộc

Đoạn mã dưới đây có thể lưu thành `BoundsDemo.java`. Nó minh họa ba trường hợp: bound một class, bound class cộng interface, và bound nhiều interface. Ví dụ dùng những tính năng ổn định của Java 27, không cần Preview.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public final class BoundsDemo {

    interface Named {
        String name();
    }

    interface Validatable {
        boolean valid();
    }

    record Job(String name, int priority)
            implements Named, Validatable {

        Job {
            Objects.requireNonNull(name, "name");
        }

        @Override
        public boolean valid() {
            return !name.isBlank() && priority >= 0;
        }
    }

    static <T extends Named & Validatable> void submit(T job) {
        if (!job.valid()) {
            throw new IllegalArgumentException("Invalid job");
        }
        System.out.println("Submitted: " + job.name());
    }

    static <T extends Number & Comparable<T>> T max(T a, T b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        return a.compareTo(b) >= 0 ? a : b;
    }

    static double sum(List<? extends Number> numbers) {
        double result = 0;

        for (Number number : numbers) {
            result += number.doubleValue();
        }

        return result;
    }

    public static void main(String[] args) {
        submit(new Job("index-catalog", 3));

        Integer highestCount = max(15, 8);
        BigDecimal highestPrice = max(
                new BigDecimal("10.25"),
                new BigDecimal("10.40")
        );

        System.out.println(highestCount); // 15
        System.out.println(highestPrice); // 10.40
        System.out.println(sum(List.of(1, 2, 3))); // 6.0
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BoundsDemo.java
java BoundsDemo
~~~

Giải thích các ràng buộc:

- `submit` yêu cầu một kiểu vừa `Named` vừa `Validatable`. Vì `Job` implements cả hai, lời gọi hợp lệ.
- `max` yêu cầu một subtype của `Number` có khả năng `Comparable<T>` để so sánh hai giá trị cùng kiểu tĩnh.
- `sum` không cần trả lại cùng kiểu `T` hoặc bảo toàn mối liên hệ giữa các tham số. Vì vậy, sử dụng wildcard `List<? extends Number>` là đủ, giúp nhận `List<Integer>`, `List<Double>` và các list với kiểu phần tử phù hợp.

Lưu ý: kết quả của `sum` là `double` và có thể gặp sai số làm tròn. Nếu tính toán số tiền hoặc số nguyên lớn cần tính chính xác, hãy dùng miền giá trị và thuật toán phù hợp, chẳng hạn `BigDecimal` với quy tắc làm tròn tường minh.

## 6. Intersection type: ý nghĩa của dấu &

### 6.1. T đáp ứng tất cả bound

Với `<T extends Base & First & Second>`, compiler xem `T` như một subtype đáp ứng đồng thời:

~~~text
           Base       First       Second
             \          |          /
              \         |         /
                T: đáp ứng cả ba
~~~

Mỗi bound bổ sung những thành viên có thể truy cập trong phạm vi visibility của Java. Điều đó không có nghĩa trình biên dịch bỏ qua những ràng buộc về override, trả về, erasure hoặc tính hợp lệ của các interface.

Ví dụ:

~~~java
interface HasId {
    long id();
}

interface HasLabel {
    String label();
}

static <T extends HasId & HasLabel> String summary(T item) {
    return item.id() + " - " + item.label();
}
~~~

Phương thức `summary` truy cập hợp lệ cả `id()` lẫn `label()` vì chúng thuộc giao diện của intersection type tương ứng.

### 6.2. Không phải phép OR và không phải union type

`<T extends A & B>` **không** có nghĩa là “A hoặc B”. Nếu caller có một đối tượng chỉ implements `A` hoặc chỉ implements `B`, kiểu đó không hợp lệ cho `T`.

Java không dùng dấu `|` để khai báo union của type argument theo cách này. Trong Java, ký hiệu `|` xuất hiện ở những ngữ cảnh khác, chẳng hạn multi-catch, nhưng không thay thế cho intersection bounds trong generic.

### 6.3. Bound phải tương thích nhau

Các bound không thể có những yêu cầu kiểu mâu thuẫn làm intersection không hợp lệ. Chẳng hạn, hai cách tham số hóa của cùng một generic interface với type argument khác nhau không thể đồng thời làm bound cho một biến kiểu.

~~~java
// Không hợp lệ vì erasure của cả hai bound đều là Comparable:
// class Broken<T extends Comparable<String> & Comparable<Integer>> { }
~~~

Nếu hai interface khai báo phương thức trùng chữ ký nhưng có kiểu trả về không tương thích, intersection cũng có thể bị compiler từ chối. Đây là kiểm tra kiểu tại thời điểm biên dịch, không phải exception chỉ xảy ra khi chương trình chạy.

### 6.4. Intersection types còn xuất hiện ở đâu?

Ngoài type parameter bounds, intersection type còn có thể xuất hiện trong cast, type inference và capture conversion theo JLS. Ví dụ cú pháp cast:

~~~java
interface CloseableTask extends Runnable, AutoCloseable {
}

// Ví dụ khác về intersection cast nếu object thực sự
// đáp ứng cả hai interface:
// Runnable r = (Runnable & AutoCloseable) someObject;
~~~

Một cast tới intersection type vẫn chịu kiểm tra kiểu lúc chạy khi phù hợp. Nó không biến một object vốn không implements interface thành object đáp ứng interface ấy. Phần trọng tâm của bài này là **intersection trong khai báo type parameter**, không phải dùng cast để né thiết kế contract.

## 7. So sánh bounded type parameter và bounded wildcard

### 7.1. Type parameter được đặt tên

~~~java
static <T extends Number> T firstOf(T a, T b) {
    return a;
}
~~~

`T` có tên và có thể xuất hiện nhiều lần trong chữ ký, tạo liên hệ kiểu giữa đối số và kết quả.

Trong một generic method, dùng type parameter có tên khi cần mô tả quan hệ kiểu mà wildcard đơn giản không thể biểu diễn rõ, chẳng hạn “tham số và kết quả có cùng `T`”.

### 7.2. Upper-bounded wildcard

~~~java
static double total(List<? extends Number> values) {
    double result = 0.0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
~~~

`? extends Number` biểu thị một **kiểu tham số chưa biết** nhưng bị chặn trên bởi `Number`. Phương thức có thể nhận các `List<Integer>`, `List<Double>` hay `List<? extends Number>` tương thích.

Vì chưa biết kiểu phần tử chính xác, không thể tùy ý thêm một `Integer` hoặc `Double` vào `values`. Đọc phần tử như `Number` thì hợp lệ. Quy tắc này thường được nhắc bằng hướng dẫn **producer extends**.

~~~java
List<Integer> integers = List.of(1, 2, 3);
System.out.println(total(integers)); // 6.0
~~~

### 7.3. Lower-bounded wildcard

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(0);
    target.add(1);
}
~~~

`? super Integer` cho phép `List<Integer>`, `List<Number>` và `List<Object>`, vì chúng có thể nhận các giá trị kiểu `Integer`. Khi đọc trực tiếp một phần tử từ `target`, kiểu an toàn chung là `Object`.

Đây là phần **consumer super** của hướng dẫn **PECS (Producer Extends, Consumer Super)**. PECS là quy tắc thiết kế API theo chiều dữ liệu, không thay thế cho các quy tắc loại kiểu trong JLS.

### 7.4. Wildcard không dùng cú pháp multiple bounds

Một type parameter có tên hỗ trợ nhiều ràng buộc:

~~~java
static <T extends Named & Validatable> void process(T value) {
    // ...
}
~~~

Nhưng wildcard thông thường trong type argument chỉ có một upper bound hoặc một lower bound trong cú pháp:

~~~java
List<? extends Number> numbers;
List<? super Integer> targets;

// Không hợp lệ:
// List<? extends Number & Comparable<?>> values;
~~~

Khi cần nhiều khả năng cho một giá trị đầu vào, hãy cân nhắc khai báo type parameter có tên với multiple bounds hoặc công bố một interface kết hợp các khả năng cần thiết.

### 7.5. Generics là bất biến theo type argument

Quan hệ subtype của kiểu phần tử không làm generic parameterized type tự động trở thành subtype tương ứng:

~~~java
List<Integer> ints = List.of(1, 2, 3);

// Không hợp lệ:
// List<Number> nums = ints;

List<? extends Number> nums = ints; // hợp lệ
~~~

Ngay cả khi `Integer extends Number`, `List<Integer>` không phải `List<Number>`. Wildcard hỗ trợ việc chấp nhận một họ kiểu tham số một cách có kiểm soát, thay vì làm cho tất cả generic trở nên hiệp biến.

## 8. Type erasure và bound đầu tiên

### 8.1. Bound hoạt động mạnh ở thời điểm biên dịch

Java generics dùng **type erasure**. Trình biên dịch kiểm tra ràng buộc kiểu trong mã nguồn, sau đó ánh xạ type variable sang kiểu erasure phù hợp khi tạo bytecode.

Quy tắc quan trọng trong JLS §4.6:

> Erasure của type variable là erasure của **bound đứng đầu** (leftmost bound).

Ví dụ:

~~~java
class NumericStore<T extends Number & Comparable<T>> {
    T value;
}
~~~

Erasure của `T` ở đây là `Number`. Điều đó **không** có nghĩa compiler bỏ qua `Comparable<T>` khi kiểm tra mã nguồn. Compiler vẫn bảo đảm việc sử dụng các thành viên của bound bổ sung là hợp lệ, và bytecode có thể cần cast thích hợp khi truy cập interface đó.

Nếu không khai báo bound, erasure của `T` mặc định là `Object`.

### 8.2. Đổi thứ tự interface có thể thay đổi erasure

Nếu các bound đều là interface và hợp lệ, interface đứng đầu quyết định erasure:

~~~java
interface Readable {
    String read();
}

interface Trackable {
    long version();
}

class First<T extends Readable & Trackable> {
    T value;
}

class Second<T extends Trackable & Readable> {
    T value;
}
~~~

Cả hai yêu cầu cùng tập khả năng ở mức kiểu Java, nhưng erasure của `T` trong `First` là `Readable`, còn trong `Second` là `Trackable`.

Vì vậy, thứ tự bound không chỉ là vấn đề trình bày: trong API đã phát hành, thay đổi bound đầu tiên có thể ảnh hưởng mô tả bytecode, binary compatibility hoặc cách công cụ phản chiếu nhìn thấy kiểu đã khai báo. Không tự ý đảo thứ tự bound công khai chỉ vì thấy chúng tương đương về ý nghĩa source-level.

### 8.3. Runtime không biết type argument cụ thể của mỗi object generic

~~~java
NumericBox<Integer> a = new NumericBox<>(1);
NumericBox<Double> b = new NumericBox<>(2.5);

System.out.println(a.getClass() == b.getClass()); // true
~~~

Hai object cùng được tạo từ một generic class và chia sẻ cùng runtime class. Không thể dựa vào runtime class của `NumericBox<T>` để xác định chắc chắn một object được tạo từ `NumericBox<Integer>` hay `NumericBox<Double>`.

Các khai báo generic và bound có thể vẫn được giữ trong metadata `Signature` và đọc qua reflection, nhưng điều đó **không** đồng nghĩa mỗi object lưu một type argument được reify.

Vì `T` không là reifiable type trong trường hợp thông thường, các thao tác sau bị hạn chế:

~~~java
class GenericOps<T extends Number> {
    // Không hợp lệ:
    // T instance = new T();
    // T[] items = new T[10];
    // boolean isT(Object value) { return value instanceof T; }
}
~~~

Khi cần tạo đối tượng theo kiểu cụ thể, thường truyền factory, constructor reference, `Class<T>` hoặc một collaborator phù hợp, thay vì mong runtime tự tạo `T`.

### 8.4. Bound không tự bảo đảm các thuộc tính ngoài kiểu

`T extends Comparable<T>` đảm bảo có thể gọi `compareTo` theo chữ ký đã khai báo; nó không đảm bảo phép so sánh nhất quán với `equals`, không bảo đảm dữ liệu bất biến và không chứng minh thuật toán không có lỗi.

Tương tự, `T extends AutoCloseable` cho phép gọi `close()` theo contract của interface, nhưng không đảm bảo thao tác luôn thành công hoặc không ném checked exception. Các bound là **ràng buộc kiểu**, không phải lời hứa thay thế kiểm thử hành vi.

## 9. Ràng buộc đệ quy và Comparable<? super T>

### 9.1. Self-referential bound

Java cho phép một type parameter xuất hiện trong chính bound của nó, nếu khai báo hợp lệ và không tạo vòng phụ thuộc type variable bị cấm:

~~~java
interface Mergeable<T extends Mergeable<T>> {
    T merge(T other);
}

record Score(int points) implements Mergeable<Score> {
    @Override
    public Score merge(Score other) {
        return new Score(this.points + other.points);
    }
}
~~~

Đây là một dạng **F-bounded polymorphism**. Nó diễn đạt quan hệ giữa kiểu đang triển khai và kiểu của đối số/kết quả trong contract:

~~~java
Score result = new Score(10).merge(new Score(5));
System.out.println(result.points()); // 15
~~~

Ràng buộc này hữu ích cho API tự tham chiếu, operation trả về kiểu cụ thể và một số mô hình builder. Nhưng nó không phải phép kiểm tra runtime rằng type argument luôn trùng chính xác với class concrete. Người thiết kế vẫn cần xem xét mô hình subtype và contract.

### 9.2. Vì sao hay dùng Comparable<? super T>?

Khai báo:

~~~java
static <T extends Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

hoạt động khi `T` triển khai `Comparable<T>`. Nhưng đôi khi một subtype chỉ kế thừa khả năng so sánh với **supertype** của nó.

Ví dụ:

~~~java
class BaseValue implements Comparable<BaseValue> {
    private final int rank;

    BaseValue(int rank) {
        this.rank = rank;
    }

    @Override
    public int compareTo(BaseValue other) {
        return Integer.compare(rank, other.rank);
    }
}

final class DetailedValue extends BaseValue {
    DetailedValue(int rank) {
        super(rank);
    }
}
~~~

`DetailedValue` kế thừa việc so sánh theo `BaseValue`, nên nó là `Comparable<BaseValue>` chứ không mặc nhiên là `Comparable<DetailedValue>`.

Một cách diễn đạt linh hoạt hơn là:

~~~java
static <T extends Comparable<? super T>> T greaterOf(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

`? super T` cho phép khả năng so sánh được khai báo trên `T` hoặc một supertype thích hợp của `T`:

~~~java
DetailedValue high = greaterOf(
        new DetailedValue(10),
        new DetailedValue(20)
);
~~~

Đây là một ứng dụng thiết thực của wildcard lower bound **bên trong** interface `Comparable`, kết hợp với upper bound của type parameter `T`. Cú pháp `<T extends Comparable<? super T>>` là hợp lệ và hiện hành.

### 9.3. Kết hợp class bound với Comparable<? super T>

Nếu vừa cần các phương thức của `Number` vừa cần khả năng so sánh với `T` hoặc supertype thích hợp:

~~~java
static <T extends Number & Comparable<? super T>>
T greaterNumber(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
~~~

Đây vẫn là multiple bounds: class `Number` trước, interface `Comparable<? super T>` sau. Nó vừa diễn đạt khả năng sử dụng API số, vừa không yêu cầu interface so sánh phải được tham số hóa đúng bằng `T`.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi hoặc hiểu lầm | Giải thích đúng / hướng sửa |
|---|---|
| `<T extends X>` chỉ hợp lệ nếu X là class | X có thể là class hoặc interface |
| Dùng `<T implements Runnable>` | Type parameter bound phải dùng `extends` |
| Xem `A & B` là “A hoặc B” | Đây là intersection: phải đáp ứng cả A **và** B |
| Đặt class sau `&` | Nếu có class bound, class phải đứng đầu |
| Dùng hai class bound | Java không cho phép multiple class bounds |
| Dùng `<T extends Number>` rồi gọi `compareTo` | `Number` không cam kết `Comparable`; thêm bound phù hợp |
| Cho rằng `Number` thỏa mãn `Comparable<Number>` | `Number` không triển khai contract này; kiểm tra kiểu tĩnh của đối số |
| Dùng `List<Number>` để nhận `List<Integer>` | Generic invariant; có thể dùng `List<? extends Number>` khi chỉ cần đọc Number |
| Viết `? extends A & B` | Wildcard thông thường không có cú pháp multiple bounds; dùng type parameter có tên |
| Cho rằng mọi bound đều được giữ nguyên như runtime type arguments | Type erasure xóa type arguments; bound đầu quyết định erasure của type variable |
| Đảo thứ tự interface bounds trong public API tùy ý | Bound đầu quyết định erasure, có thể tác động tương thích nhị phân |
| Dùng raw type hoặc unchecked cast để bỏ lỗi bound | Thường làm mất kiểm tra kiểu; sửa mô hình kiểu/API thay vì che cảnh báo |
| Dùng `Comparable<T>` ở mọi nơi dù so sánh dựa trên supertype | Xem xét `Comparable<? super T>` khi contract cần tính linh hoạt đó |
| Tưởng bound đảm bảo object bất biến hoặc thuật toán đúng | Bound kiểm soát khả năng kiểu ở compile time, không chứng minh bất biến nghiệp vụ |

## 11. Nguyên tắc thiết kế API có bounds

Bound nên diễn tả **năng lực thực sự cần thiết**, không phải toàn bộ loại đối tượng mà tác giả có thể nghĩ tới.

- Dùng `<T extends Number>` khi thân phương thức thực sự cần API `Number`.
- Dùng `<T extends Named & Validatable>` khi thuật toán cần cả khả năng đặt tên và xác thực; không tạo một base class cứng chỉ để gom hai hành vi độc lập.
- Dùng `<T extends Number & Comparable<? super T>>` khi thực sự cần vừa đọc giá trị số vừa so sánh các giá trị.
- Nếu một type parameter chỉ xuất hiện ở một vị trí và không diễn đạt quan hệ giữa đối số và kiểu kết quả, wildcard phù hợp có thể làm API đơn giản hơn.
- Không mở rộng số lượng bound chỉ để phòng ngừa tương lai; bound bổ sung khiến các implementation hợp lệ khác không thể gọi API.
- Với API public, xem thứ tự bound và tương thích nhị phân là một phần của hợp đồng phát hành.
- Khi thao tác với collection, quyết định collection là **nguồn đọc** hay **đích nhận giá trị** trước khi chọn `? extends` hoặc `? super`.
- Không sử dụng raw types, unchecked casts hoặc reflection để vượt qua thiết kế ràng buộc nếu có thể sửa contract đúng đắn.

Một API tốt tránh cả hai cực đoan: **quá rộng** khiến compiler không thể giúp phát hiện lỗi và **quá hẹp** khiến người gọi phải đổi kiểu hoặc cast không cần thiết.

## 12. Câu hỏi tự kiểm tra

1. Sự khác nhau giữa `class Box<T>` và `class Box<T extends Number>` là gì?
2. Vì sao `<T extends Runnable>` hợp lệ dù `Runnable` là interface?
3. Trong `<T extends Number & Comparable<T>>`, tại sao `Number` phải đứng đầu?
4. `<T extends Named & Validatable>` chấp nhận object chỉ implements `Named` không? Vì sao?
5. Khi nào `List<? extends Number>` phù hợp hơn `List<Number>`?
6. Vì sao `? extends Number & Comparable<?>` không phải cú pháp wildcard hợp lệ?
7. Erasure của `T` là gì nếu `T extends Readable & Trackable`?
8. Hai kiểu tham số hóa `NumericBox<Integer>` và `NumericBox<Double>` có phải hai runtime class khác nhau không?
9. `Comparable<? super T>` giải quyết tình huống nào mà `Comparable<T>` có thể hạn chế quá mức?
10. Trong phương thức dùng `<T extends Number>`, vì sao gọi `T.compareTo()` không được bảo đảm hợp lệ?
11. Khi nào nên dùng nhiều type parameter ngăn cách bằng dấu phẩy thay vì một type parameter với nhiều bound?
12. Trước khi đổi thứ tự các bounds trong public generic API, cần kiểm tra điều gì?

## 13. Tài liệu chính thức cho Java SE 27

- [JLS Java SE 27 — §4.4 Type Variables](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.4): cú pháp `TypeBound`, nhiều bound, thứ tự class/interface và các giới hạn tương thích.
- [JLS Java SE 27 — §4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.5.1): wildcard `? extends`, `? super` và phương pháp diễn đạt quan hệ kiểu.
- [JLS Java SE 27 — §4.6 Type Erasure](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.6): erasure của type variable lấy từ leftmost bound.
- [JLS Java SE 27 — §4.9 Intersection Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.9): ý nghĩa intersection type và các thành viên có thể truy cập.
- [JLS Java SE 27 — §8.1.2 Generic Classes and Type Parameters](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.1.2): type parameter trong khai báo class.
- [JLS Java SE 27 — §8.4.4 Generic Methods](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.4): khai báo type parameter cấp phương thức.
- [Java SE 27 API — Comparable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Comparable.html): hợp đồng `Comparable<T>` và quy tắc so sánh.
- [Java SE 27 API — Number](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Number.html): các phương thức của upper bound `Number`.
