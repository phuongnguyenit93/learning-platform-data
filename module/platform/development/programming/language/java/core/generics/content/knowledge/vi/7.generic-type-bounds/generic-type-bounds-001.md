# Giới hạn trên `<T extends U>` và các thao tác được phép trên `T` trong Java

**Giới hạn trên** (*upper bound*) là ràng buộc một tham số kiểu generic phải là một kiểu phù hợp với một kiểu cha, một interface hoặc một type variable đã biết. Cú pháp thường gặp là `<T extends U>`, trong đó `T` là tham số kiểu được khai báo và `U` là giới hạn trên: **đối số kiểu truyền cho `T` phải là `U` hoặc subtype của `U`**.

Upper bound giải quyết vấn đề quan trọng: khi một thuật toán nhận dữ liệu thuộc nhiều lớp khác nhau, trình biên dịch cần biết **những phương thức nào chắc chắn có thể gọi trên `T`**. Nếu chỉ khai báo `<T>`, compiler không giả định `T` có `doubleValue()`, `compareTo()` hay một method nghiệp vụ bất kỳ. Nếu khai báo `<T extends Number>`, compiler biết `T` hỗ trợ những thành viên truy cập được của `Number`, chẳng hạn `doubleValue()`.

Bài này trình bày cú pháp, cơ chế kiểm tra lúc biên dịch, các thao tác hợp lệ và không hợp lệ, nhiều giới hạn, sự khác biệt giữa upper bound cho type parameter và wildcard `? extends U`, kiểu kết quả, type erasure, lỗi thường gặp và ví dụ Java 17+ chạy được.

## 1. Đọc cú pháp `<T extends U>` chính xác

Ví dụ đơn giản:

```java
static <T extends Number> double toDouble(T value) {
    return value.doubleValue();
}
```

Trong chữ ký:

1. `<T extends Number>` **khai báo** một type parameter mới tên `T`.
2. `Number` là **upper bound**: đối số kiểu thay cho `T` phải là `Number` hoặc lớp con phù hợp, như `Integer`, `Long`, `Double`, `BigDecimal`.
3. Kiểu trả về của phương thức là `double` cố định; không phải `T`.
4. Tham số `T value` chấp nhận giá trị theo `T` đã được compiler suy luận/chọn.
5. `doubleValue()` hợp lệ bởi đây là phương thức được khai báo trên `Number`.

Lời gọi minh họa:

```java
double a = toDouble(42);                       // T suy luận là Integer.
double b = toDouble(3.5);                      // T suy luận là Double.
double c = toDouble(new java.math.BigDecimal("2.25"));

// toDouble("42"); // Không biên dịch: String không extends Number.
```

`Number` ở đây là lớp trừu tượng trong Java, có các phương thức như `intValue()`, `longValue()`, `floatValue()`, `doubleValue()`. Sự tồn tại của method **không bảo đảm kết quả chuyển đổi không mất độ chính xác**: `longValue()` có thể làm mất phần thông tin và `doubleValue()` có thể làm tròn khi kiểu số gốc giữ độ chính xác cao hơn.

Cú pháp `<T extends U>` không có nghĩa `T` **bằng hẳn** `U`; `T` có thể là subtype của `U`. Từ khóa `extends` dùng cho cả upper bound là class, interface hoặc một type variable đã được khai báo phù hợp.

### `U` không nhất thiết là tên class

Một ràng buộc có thể tham chiếu type variable khác:

```java
static <U, T extends U> U upcast(T value) {
    return value;
}
```

Ở đây `U` được khai báo trước, nên `T extends U` hợp lệ. Phương thức trả `U` vì mọi `T` phù hợp có thể được xem như `U`. Đoạn minh họa này **không cần dùng trong mọi bài toán**; trên thực tế, các chữ ký đơn giản hơn thường dễ hiểu hơn nếu chỉ cần phép upcast thông thường.

### Upper bound có thể là interface

```java
static <T extends CharSequence> int lengthOf(T value) {
    return value.length();
}
```

`CharSequence` là interface. Dù vậy vẫn viết `extends`, không viết `implements` trong danh sách giới hạn type parameter. `String`, `StringBuilder`, `StringBuffer` là các kiểu thích hợp để sử dụng ở đây; kiểu `Integer` không đáp ứng ràng buộc `CharSequence`.

`T` có thể là một class/interface subtype phù hợp, nhưng **không thể là primitive**: `<T extends Number>` có thể dùng `Integer`, không dùng trực tiếp `int`. Java có boxing để hỗ trợ nhiều lời gọi với literal primitive, nhưng type argument thực vẫn là kiểu tham chiếu.

## 2. Vì sao không có bound thì compiler chỉ biết rất ít về `T`?

Xét generic method không có bound:

```java
static <T> String describe(T value) {
    return String.valueOf(value);
}
```

`T` mặc định có giới hạn trên là `Object` nếu không bị ràng buộc khác. Compiler chỉ cho truy cập các thành viên hợp lệ đã được bảo đảm bởi kiểu đó, chẳng hạn các phương thức của `Object` được phép gọi trong ngữ cảnh tương ứng (`toString`, `equals`, `hashCode`, `getClass`, ...). `String.valueOf(value)` còn xử lý được trường hợp `null`.

**Không thể tự ý gọi method thuộc một subtype tùy ý:**

```java
// Không biên dịch:
// static <T> double broken(T value) {
//     return value.doubleValue();
// }
```

Compiler phải kiểm tra phương thức tổng quát ấy cho **mọi `T` hợp lệ**, từ `String` đến `LocalDate` hoặc một lớp nghiệp vụ. Không có hợp đồng nào yêu cầu mọi đối tượng đều có `doubleValue()`.

Nếu code viết `<T extends Number>`, các member của `Number` trở nên khả dụng:

```java
static <T extends Number> String describeNumber(T value) {
    return "double=" + value.doubleValue()
            + ", long=" + value.longValue();
}
```

Upper bound là **lời hứa về kiểu được compiler kiểm tra**, chứ không phải một phép chuyển runtime từ giá trị tùy ý thành `Number`. Caller truyền `String` sẽ bị từ chối theo đường gọi có kiểm tra generic type đầy đủ.

## 3. Những thao tác nào được phép trên `T extends U`?

Hãy hình dung bạn viết:

```java
static <T extends Number> double twice(T value) {
    return value.doubleValue() * 2.0;
}
```

Compiler biết `value` có ít nhất hợp đồng của `Number`; do đó có thể gọi `doubleValue()` và thực hiện phép toán số học trên **giá trị `double` trả về**.

| Thao tác | Với `T extends Number` | Vì sao |
| --- | --- | --- |
| `value.doubleValue()` | Hợp lệ | Method nằm trong `Number` |
| `value.intValue()` | Hợp lệ | Method nằm trong `Number` |
| `value.toString()` | Hợp lệ | Thừa hưởng/ghi đè method của `Object` |
| `Number n = value` | Hợp lệ | Mọi `T` phù hợp có thể được xem như `Number` |
| `Object o = value` | Hợp lệ | Mọi kiểu tham chiếu phù hợp là `Object` |
| `T copy = value` | Hợp lệ | Gán đúng kiểu `T` hiện có |
| `value.compareTo(other)` | Không được bảo đảm | `Number` không khai báo `compareTo` |
| `value.add(other)` | Không được bảo đảm | Không phải mọi `Number` có method `add` |
| `value + other` | Không hợp lệ cho `T` chỉ bound bởi `Number` | Java không định nghĩa toán tử số học trực tiếp cho type variable `T` như primitive |
| `new T()` | Không hợp lệ | Không thể khởi tạo type variable bằng constructor trực tiếp |
| `new T[10]` | Không hợp lệ | Java không cho tạo mảng component type không reifiable như type variable `T` |

Upper bound cũng **không** cho phép truy cập field/method `private` của `U` chỉ vì `T extends U`: kiểm soát truy cập Java vẫn áp dụng. Những method cụ thể của subclass `Integer` hoặc `BigDecimal` cũng không tự nhiên được gọi trên `T` nếu bound chỉ là `Number`.

### Không nhầm `T` với `U`

Với `<T extends Number>`, bạn có thể gán `T` cho `Number`, nhưng không thể tùy ý gán `Number` thành `T`:

```java
static <T extends Number> void example(T value) {
    Number number = value;       // Hợp lệ.
    // T wrong = number;         // Không biên dịch.
}
```

Lý do: `T` có thể là `Integer`, còn biến `number` có thể tham chiếu đến `Double`. Quan hệ subtype chỉ bảo đảm chiều **T → Number**, không bảo đảm chiều ngược.

Tương tự, không thể coi `<T extends Number>` là một phép `cast` cho mọi object. Nếu dữ liệu đến từ nguồn bên ngoài, vẫn phải xác thực kiểu và nội dung theo yêu cầu nghiệp vụ.

## 4. Upper bound ở cấp class và ở cấp method

### 4.1. Khai báo trên generic class

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T extends Number` được khai báo **trên lớp**, nên constructor, field và instance methods cùng biết `T` phải phù hợp với `Number`. `NumericBox<Integer>` và `NumericBox<Double>` hợp lệ; `NumericBox<String>` không hợp lệ.

`T get()` trả đúng `T`, trong khi `double asDouble()` trả primitive `double`: hai method cung cấp hai kiểu hợp đồng khác nhau mà vẫn tận dụng chung upper bound.

### 4.2. Khai báo trên generic method

```java
class NumericTools {
    static <T extends Number> double square(T value) {
        double x = value.doubleValue();
        return x * x;
    }
}
```

Lớp `NumericTools` **không generic**; chỉ method `square` tự khai báo `<T extends Number>`. Mỗi lời gọi có thể dùng một subtype khác của `Number`.

### 4.3. Bound của lớp và bound của method độc lập

```java
class Holder<T extends Number> {
    private final T number;

    Holder(T number) {
        this.number = number;
    }

    <U extends CharSequence> String append(U suffix) {
        return number + ":" + suffix;
    }
}
```

`T` thuộc class và bound bởi `Number`; `U` thuộc method và bound bởi `CharSequence`. Hai type parameters có **phạm vi riêng**. Không nên khai báo một `<T>` mới ở method nếu mục tiêu là sử dụng chính `T` của lớp; việc dùng lại tên có thể che khuất type parameter ở lớp.

## 5. Ràng buộc bằng một interface nghiệp vụ

Không nhất thiết phải dùng `Number` hoặc interface có sẵn. Upper bound đặc biệt hữu ích khi thuật toán cần một **hợp đồng nghiệp vụ cụ thể**:

```java
interface HasId<ID> {
    ID id();
}

static <T extends HasId<String>> String extractId(T entity) {
    return entity.id();
}
```

Khi `T extends HasId<String>`, method biết `entity.id()` trả `String`, dù entity thực tế là `Product`, `Customer` hay một kiểu triển khai khác. Điều này cho phép tái sử dụng logic theo **khả năng được interface bảo đảm**, thay vì ép mọi entity kế thừa cùng một lớp nghiệp vụ.

Ví dụ:

```java
record Product(String id, String name) implements HasId<String> {}

String id = extractId(new Product("P-7", "Pen"));
```

Nếu một lớp chỉ implements `HasId<Long>`, nó không đáp ứng bound `HasId<String>` nói trên. Type arguments của interface generic vẫn quan trọng; không thể chỉ nhìn tên `HasId` rồi cho rằng mọi cách tham số hóa đều tương thích.

### Bound có thể gắn nhiều type variables

```java
interface HasId<ID> {
    ID id();
}

static <ID, T extends HasId<ID>> ID idOf(T entity) {
    return entity.id();
}
```

`ID` được khai báo trước `T`, và bound `T extends HasId<ID>` mô tả quan hệ giữa hai type parameters. Khi truyền một entity triển khai `HasId<Long>`, compiler có thể dùng quan hệ đó để xác định kiểu kết quả phù hợp với `Long`.

Đây là ví dụ một bound **có ích cho hợp đồng kiểu**, không chỉ giúp gọi method: nó kết nối loại entity với kiểu ID của chính entity ấy.

## 6. Nhận diện nhiều giới hạn trước khi đi sâu

Một type parameter có thể cần **đồng thời** hai khả năng độc lập, chẳng hạn tính toán như `Number` và so sánh như `Comparable<T>`. Khi đó Java cho phép:

```java
class NumericHolder<T extends Number & Comparable<T>> {
    private final T value;
    NumericHolder(T value) { this.value = value; }
    double asDouble() { return value.doubleValue(); }
    boolean isGreaterThan(T other) {
        return value.compareTo(other) > 0;
    }
}
```

`Integer` phù hợp cả hai bounds, nhưng `Number` **không** tự triển khai `Comparable<Number>`. Dấu `&` yêu cầu thỏa **tất cả** điều kiện, khác dấu phẩy phân tách nhiều type parameters. Nếu có class bound, class đứng đầu và các bounds sau là interfaces; không thể đặt hai class bounds.

Ví dụ này chỉ giới thiệu lý do cần multiple bounds; trọng tâm của bài hiện tại vẫn là **upper bound cấp quyền gọi phương thức nào trên `T`**. Các chương trình có nhiều interfaces, điều kiện tương thích và ảnh hưởng tới erasure được khai triển riêng ở các tình huống phức tạp hơn.

## 7. `Comparable<? super T>` và thuật toán chọn phần tử lớn nhất

Một yêu cầu hay gặp là **chọn phần tử lớn nhất** từ danh sách mà không ép kiểu về `Object`. Để gọi `compareTo` trên `T`, cần bound thích hợp:

```java
static <T extends Comparable<? super T>> T max(
        java.util.List<T> values) {

    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty");
    }

    T best = values.get(0);
    for (T value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

`Comparable<? super T>` có nghĩa `T` triển khai khả năng so sánh với `T` **hoặc với một supertype của `T`**. Khi gọi `value.compareTo(best)`, compiler biết `best` kiểu `T` có thể được truyền vào hợp đồng so sánh.

Tại sao không chỉ viết `T extends Comparable<T>`? Bản thân cách viết ấy vẫn hợp lệ cho nhiều kiểu, nhưng **hẹp hơn**. Có những lớp con kế thừa `Comparable<Parent>` từ kiểu cha: chúng có thể so sánh các đối tượng lớp con thông qua hợp đồng `Comparable<Parent>` dù không implements trực tiếp `Comparable<Child>`. Bound `Comparable<? super T>` chấp nhận các trường hợp như vậy.

Ví dụ:

```java
String longestLexicographically =
        max(java.util.List.of("Go", "Java", "C"));

Integer maxScore = max(java.util.List.of(4, 9, 6));
```

`String` và `Integer` đều đáp ứng bound, nhưng chúng có quy tắc so sánh riêng. **`max` dựa vào thứ tự `compareTo`**, không dựa vào độ dài chuỗi: `"Java"` lớn hơn `"Go"` trong so sánh từ điển ở ví dụ. Không nhầm chữ `max` với “chuỗi dài nhất”.

Với `T extends Number`, compiler **không** cho gọi `compareTo()` vì `Number` không có phương thức ấy. Hãy chọn bound dựa trên thao tác thuật toán thực sự cần.

## 8. Chương trình Java 17+ hoàn chỉnh: từng bound mở khóa thao tác gì?

Lưu toàn bộ mã dưới đây vào **`Main.java`**. Ví dụ sử dụng:

- `T extends Number` để gọi `doubleValue()`;
- `T extends Comparable<? super T>` để gọi `compareTo`;
- `T extends Identified<String> & Named` để gọi đồng thời `id()` và `name()`;
- `T extends Number & Comparable<T>` để dùng cả phép chuyển số và phép so sánh.

```java
import java.util.ArrayList;
import java.util.List;

public class Main {
    interface Identified<ID> {
        ID id();
    }

    interface Named {
        String name();
    }

    record Product(String id, String name)
            implements Identified<String>, Named {}

    static <T extends Number> double sum(List<T> values) {
        double total = 0;
        for (T value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static <T extends Comparable<? super T>> T max(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
        T best = values.get(0);
        for (T value : values) {
            if (value.compareTo(best) > 0) {
                best = value;
            }
        }
        return best;
    }

    static <T extends Identified<String> & Named>
    String describe(T entity) {
        return entity.id() + "/" + entity.name();
    }

    static final class PositiveBox<T extends Number & Comparable<T>> {
        private final T value;

        PositiveBox(T value) {
            this.value = value;
        }

        boolean greaterThan(T other) {
            return value.compareTo(other) > 0;
        }

        double twice() {
            return value.doubleValue() * 2;
        }
    }

    static <T extends Number> List<T> aboveThreshold(
            List<T> values, double threshold) {

        List<T> result = new ArrayList<>();
        for (T value : values) {
            if (value.doubleValue() > threshold) {
                result.add(value);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("sum integers: " + sum(List.of(1, 2, 3, 4)));
        System.out.println("sum decimals: " + sum(List.of(1.5, 2.25)));

        System.out.println("max string: " + max(List.of("Go", "Java", "C")));
        System.out.println("max integer: " + max(List.of(4, 9, 6)));

        System.out.println("product: "
                + describe(new Product("P-7", "Pen")));

        PositiveBox<Integer> box = new PositiveBox<>(7);
        System.out.println("larger: " + box.greaterThan(5));
        System.out.println("double: " + box.twice());

        System.out.println("above: "
                + aboveThreshold(List.of(1, 4, 6), 3.0));

        // sum(List.of("A", "B")); // Không biên dịch: String không extends Number.
        // PositiveBox<Number> wrong; // Không thỏa Comparable<Number>.
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout:**

```text
sum integers: 10.0
sum decimals: 3.75
max string: Java
max integer: 9
product: P-7/Pen
larger: true
double: 14.0
above: [4, 6]
```

### Giải thích kết quả và cơ chế type checking

1. `sum(List.of(1,2,3,4))`: compiler suy luận `T` phù hợp với `Integer`; method chỉ gọi `doubleValue()` mà `Number` bảo đảm. Vì dùng `double` làm biến cộng dồn, kết quả hiển thị `10.0`.
2. `sum(List.of(1.5,2.25))`: type argument phù hợp với `Double`; dùng chung implementation, kết quả `3.75`.
3. `max(List.of("Go","Java","C"))`: `String` đáp ứng `Comparable<String>`, nên gọi `compareTo` hợp lệ; `"Java"` đứng lớn nhất theo thứ tự từ điển.
4. `max(List.of(4,9,6))`: `Integer` cũng đáp ứng bound, kết quả `9`.
5. `describe(Product)`: record `Product` triển khai cả `Identified<String>` và `Named`, nên cả hai method được gọi an toàn.
6. `PositiveBox<Integer>`: `Integer` vừa kế thừa `Number`, vừa triển khai `Comparable<Integer>`. `greaterThan(5)` sử dụng `compareTo` và `twice()` dùng `doubleValue()`.
7. `aboveThreshold` trả `List<T>`, **giữ lại kiểu phần tử** của danh sách đầu vào. Với `List<Integer>`, kết quả vẫn có kiểu `List<Integer>`; method chỉ so sánh bằng giá trị `double` suy ra từ từng phần tử.

**Giới hạn của ví dụ:** `sum` tính tổng qua `doubleValue()`, nên không dành cho phép tính tài chính cần độ chính xác thập phân tuyệt đối. Với `BigDecimal`, hãy dùng phép tính theo chính kiểu `BigDecimal` hoặc một abstraction phù hợp. `max` yêu cầu danh sách không rỗng và các phần tử có thể so sánh được; chương trình ném `IllegalArgumentException` trên danh sách rỗng, còn các giá trị `null` có thể gây lỗi khi truy cập method. Upper bound **không** tự loại trừ `null`.

## 9. Bound không có nghĩa là mọi thao tác số học đều hợp lệ

Một chỗ dễ nhầm là chữ `Number` trong bound. Ví dụ:

```java
static <T extends Number> double add(T a, T b) {
    return a.doubleValue() + b.doubleValue();
}
```

Cách này hợp lệ vì phép cộng được thực hiện giữa **hai `double` primitive**, sau khi gọi method mà `Number` cung cấp.

Ngược lại:

```java
// Không biên dịch:
// static <T extends Number> T add(T a, T b) {
//     return a + b;
// }
```

Java không có toán tử `+` tổng quát cho mọi subtype `Number`, và không thể bảo đảm kết quả là cùng subtype `T`. Nếu `T = Integer`, biểu thức cộng có thể cần xử lý tràn số; nếu `T = BigDecimal`, việc cộng phải qua `add(...)`; nếu `T = AtomicInteger`, hành vi cũng khác. Một upper bound như `Number` không phát minh ra phép cộng chung cho mọi số.

**Chọn abstraction đúng:**

- Khi chỉ cần thống kê/hiển thị gần đúng, chuyển qua `doubleValue()` có thể phù hợp nếu chấp nhận giới hạn độ chính xác.
- Khi cần toán học chính xác trên `BigDecimal`, dùng API cụ thể `BigDecimal.add`, `multiply` và quy tắc rounding.
- Khi cần thuật toán tùy biến giữa nhiều kiểu số, cân nhắc truyền vào một hàm cộng/strategy có chữ ký rõ ràng thay vì ép kiểu không kiểm chứng.

## 10. Upper bound khác với wildcard `? extends U`

Hai cú pháp gần giống nhau nhưng được dùng cho **hai mục đích**:

```java
<T extends Number>           // Khai báo một type variable tên T có upper bound.
List<? extends Number>       // Dùng wildcard trong một parameterized type.
```

### 10.1. Type parameter được đặt tên và dùng lại

```java
static <T extends Number> T first(List<T> numbers) {
    return numbers.get(0);
}
```

`T` xuất hiện ở **cả tham số đầu vào và kiểu trả về**. Caller truyền `List<Integer>` thì kết quả được kiểm tra theo `Integer`, không chỉ theo `Number`.

### 10.2. Wildcard chỉ biểu diễn một kiểu chưa biết tại vị trí đó

```java
static double sumWildcard(List<? extends Number> numbers) {
    double total = 0;
    for (Number value : numbers) {
        total += value.doubleValue();
    }
    return total;
}
```

Method nhận `List<Integer>`, `List<Double>` và các danh sách subtype `Number` phù hợp. Nó chỉ cần đọc từng `Number`, **không cần đặt tên cho kiểu phần tử** hoặc trả lại một `T` cụ thể.

### Bảng so sánh

| Điểm so sánh | `<T extends Number>` | `? extends Number` |
| --- | --- | --- |
| Vai trò | Khai báo type parameter có tên | Chỉ định wildcard khi sử dụng generic type |
| Có tên `T` để dùng lại trong nhiều vị trí? | Có | Không |
| Khi hợp lý | Liên kết kiểu input và output, nhiều tham số cùng kiểu, thuật toán phải giữ `T` | Chỉ đọc từ cấu trúc gồm số thuộc một subtype bất kỳ |
| Dùng ở khai báo phương thức | `static <T extends Number> ...` | Không dùng wildcard làm type parameter khai báo |
| Dùng trong `List` | `List<T>` sau khi đã khai báo `T` | `List<? extends Number>` |
| Tự cho phép thêm `Number` tùy ý vào danh sách? | Phải xét đúng `T` và loại danh sách | Không, vì kiểu phần tử cụ thể chưa biết |

Ví dụ:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> numbers = integers;

// numbers.add(3.14); // Không biên dịch.
// numbers.add(10);   // Cũng không biên dịch.
```

Vì `numbers` thực ra có thể tham chiếu `List<Integer>`, compiler phải ngăn việc thêm một `Double` hay một `Number` tùy ý. Có thể thêm `null` qua những thao tác phù hợp, nhưng điều đó không có ích khi mục đích là thêm số hợp lệ.

### Upper bound không làm generic container hiệp biến

```java
List<Integer> integers = new ArrayList<>();

// Không biên dịch:
// List<Number> allNumbers = integers;

List<? extends Number> readNumbers = integers; // Hợp lệ.
```

`Integer extends Number` không biến `List<Integer>` thành subtype của `List<Number>`: generic types Java mặc định **bất biến**. Upper bound trên `T` và wildcard `? extends Number` giúp viết API linh hoạt theo những cách khác nhau, nhưng không thay đổi quy tắc ấy.

## 11. Bounds và quan hệ kế thừa giữa các generic classes

Một class con có thể **giữ hoặc thu hẹp** giới hạn của type parameter khi truyền nó cho superclass:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class NumberBox<N extends Number> extends Box<N> {
    NumberBox(N value) {
        super(value);
    }

    double asDouble() {
        return get().doubleValue();
    }
}
```

`Box<T>` chấp nhận mọi reference type, còn `NumberBox<N>` chỉ chấp nhận subtype của `Number`. `NumberBox<Integer>` hợp lệ, `NumberBox<String>` không hợp lệ.

Ngược lại, nếu superclass đã có ràng buộc:

```java
class NumericStore<T extends Number> {}

// Không biên dịch:
// class BadStore<T> extends NumericStore<T> {}
```

Compiler chưa thể bảo đảm một `T` hoàn toàn tự do thỏa `T extends Number` mà `NumericStore` yêu cầu. Sửa bằng cách giữ bound:

```java
class GoodStore<T extends Number> extends NumericStore<T> {}
```

Hoặc truyền trực tiếp một subtype cụ thể hợp lệ:

```java
class IntegerStore extends NumericStore<Integer> {}
```

Bounds của superclass/interface là một phần của hợp đồng: subclass muốn truyền type argument phải đáp ứng ràng buộc mà kiểu cha yêu cầu.

## 12. Bounds và type erasure ở runtime

Java generics chủ yếu được triển khai bằng **type erasure**: compiler kiểm tra kiểu ở compile time, sau đó xóa phần lớn type arguments và type variables trong bytecode. Với `T extends Number`, kiểu bị xóa của `T` thường là **bound ngoài cùng bên trái** `Number`, thay vì `Object` như type parameter không bị bound.

Trong:

```java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
```

code biên dịch có thể gọi `Number.doubleValue()` vì erasure của type variable phù hợp với `Number`. Khi có nhiều bounds, compiler có thể chèn cast và bridge methods nếu cần để duy trì hành vi đa hình.

Điều này **không** tạo một runtime class riêng cho mỗi `T`, và cũng không khiến kiểm tra sau hợp lệ:

```java
// Không biên dịch:
// if (object instanceof List<Integer>) { ... }

// Không biên dịch:
// T item = new T();

// Không biên dịch:
// T[] items = new T[10];
```

Nếu cần tạo một đối tượng kiểu `T`, một cách an toàn hơn là nhận **factory** có kiểu `Supplier<T>` hoặc constructor/factory được truyền vào:

```java
static <T extends Number> T fromFactory(
        java.util.function.Supplier<T> supplier) {
    return supplier.get();
}
```

Caller có thể truyền `() -> Integer.valueOf(5)`; đó là đối tượng thực được tạo bởi factory, không phải `new T()` do compiler suy đoán constructor của mọi subclass.

Nếu cần kiểm tra kiểu runtime cho một giá trị riêng lẻ, có thể truyền `Class<T>` vào phương thức và dùng `Class.cast` hoặc phương thức kiểm tra tương ứng. Tuy nhiên, `Class<List<Integer>>` không biểu diễn đầy đủ kiểu generic lồng ở runtime theo cách `List<Integer>.class`; việc validate cấu trúc phức tạp có thể cần type reference/schema hoặc kiểm tra từng phần tử.

## 13. Những hiểu nhầm và lỗi phổ biến

**Lỗi 1 — dùng `implements` trong bound:** không viết `<T implements Runnable>`. Type parameter bound luôn dùng `extends`, dù `Runnable` là interface.

**Lỗi 2 — tưởng `T extends Number` chỉ nhận đúng `Number`:** bound cho phép cả `Number` và subtype phù hợp. `Integer`, `Long`, `Double`, `BigDecimal` đều là các ví dụ hợp lệ.

**Lỗi 3 — gọi method không tồn tại trong bound:** `value.compareTo(other)` không được bảo đảm với `T extends Number`. Cần giới hạn có `Comparable` phù hợp hoặc sử dụng strategy.

**Lỗi 4 — dùng toán tử số học trực tiếp trên `T`:** phép `a + b` không hợp lệ cho hai biến chỉ có kiểu `T extends Number`. Chuyển sang thao tác mà bound bảo đảm hoặc dùng abstraction cụ thể.

**Lỗi 5 — đặt nhiều class bounds hoặc sai thứ tự:**

```java
// Sai:
// <T extends Runnable & Number>
// <T extends Number & java.util.AbstractList<T>>
```

Nếu có class, nó phải đầu tiên; các bound sau là interface. Không có hai superclass riêng cho một type parameter.

**Lỗi 6 — quên rằng bound phải thỏa ở lớp con:** nếu `Parent<T extends Number>` thì `Child<T> extends Parent<T>` không hợp lệ khi `T` chưa có bound phù hợp.

**Lỗi 7 — cho rằng upper bound loại bỏ `null`:** các reference type phù hợp vẫn có thể có giá trị `null`. Gọi `doubleValue()` trên `null` vẫn ném `NullPointerException`; validation và kiểu generic là hai vấn đề riêng.

**Lỗi 8 — nhầm type parameter với wildcard:** `<T extends Number>` tạo một tên kiểu có thể dùng lại; `? extends Number` là kiểu không biết chính xác tại một vị trí. Chọn dựa trên nhu cầu liên kết input/output.

**Lỗi 9 — hiểu `T extends Number` là mọi số đều so sánh được cùng cách:** `Number` không khai báo `compareTo`; `BigDecimal` và `Double` còn có ngữ nghĩa số học khác nhau. Không suy luận tính chất không có trong bound.

**Lỗi 10 — dùng cast không kiểm chứng để vượt bound:** `(T) arbitraryObject` không biến object thật thành `T`, có thể sinh unchecked warning và lỗi runtime. Hãy thiết kế hợp đồng cụ thể hoặc validate ở ranh giới.

**Lỗi 11 — hy vọng `T` tự có constructor mặc định:** ngay cả khi có upper bound, `new T()` vẫn không hợp lệ. Dùng factory/supplier hoặc truyền object đã tạo.

**Lỗi 12 — dùng `T` làm primitive type argument:** `List<int>` và `<T extends int>` không hợp lệ. Dùng wrapper/reference type phù hợp hoặc cấu trúc primitive nếu cần hiệu năng.

**Lỗi 13 — nhầm thứ tự trong nhiều bounds:** khi class bound xuất hiện, nó phải đứng đầu; `T extends Comparable<T> & Number` không hợp lệ vì `Number` là class nằm sau interface.

**Lỗi 14 — quên giới hạn độ chính xác của phép chuyển số:** `doubleValue()` hợp lệ về kiểu nhưng không bảo đảm bảo toàn toàn bộ chữ số của `BigDecimal` hay mọi `long`. Đối chiếu yêu cầu nghiệp vụ trước khi dùng thuật toán tổng quát qua `double`.

## 14. Quy trình chọn upper bound phù hợp

Trước khi khai báo `<T extends U>`, hãy đi từ **thao tác thực sự cần**:

1. **Liệt kê method cần gọi**: `doubleValue()`, `length()`, `compareTo()`, `id()` hay `name()`?
2. **Tìm hợp đồng chung nhỏ nhất phù hợp**: `Number`, `CharSequence`, `Comparable<? super T>` hay một interface nghiệp vụ tự định nghĩa?
3. **Kiểm tra mọi type argument dự kiến** có đáp ứng bound không; một loại class cụ thể không nhất thiết đại diện cho tất cả các subtype.
4. **Xác định đầu ra có cần giữ `T` không**: trả `T`, `List<T>` hay chỉ cần kiểu cố định như `double` hoặc `String`?
5. **Cân nhắc wildcard** nếu method chỉ đọc từ một cấu trúc generic và không cần đặt tên kiểu để liên kết nhiều vị trí.
6. **Xem xét null, dữ liệu rỗng và độ chính xác**: bound chỉ nói về khả năng của type, không bảo đảm các ràng buộc giá trị.
7. **Giữ signature đơn giản nhất đáp ứng hợp đồng**: mỗi bound nên có lý do rõ ràng, tránh thêm ràng buộc không dùng đến.

| Nhu cầu | Upper bound thường phù hợp |
| --- | --- |
| Truy cập `doubleValue()` hoặc `longValue()` | `<T extends Number>` |
| Đọc chiều dài chuỗi/ký tự | `<T extends CharSequence>` |
| So sánh phần tử cùng kiểu hoặc kiểu cha tương thích | `<T extends Comparable<? super T>>` |
| Cần vừa đặc điểm `Number`, vừa `compareTo` | `<T extends Number & Comparable<T>>` khi phù hợp với các type arguments thực tế |
| Cần ID theo kiểu cụ thể | `<T extends HasId<String>>` |
| Cần vừa có ID, vừa có tên | `<T extends Identified<String> & Named>` |
| Chỉ duyệt danh sách số để đọc | `List<? extends Number>` có thể đủ, không cần một `T` có tên |

## 15. Bài tập tự kiểm tra

**Câu 1.** Vì sao `static <T> double doubleValue(T value)` không thể gọi trực tiếp `value.doubleValue()`?

**Đáp án:** `T` không có upper bound diễn đạt khả năng ấy. Nếu compiler cho phép, method có thể được gọi với `String` hoặc bất kỳ reference type không có `doubleValue()`. Thêm `T extends Number` khi mục đích thật sự là làm việc với `Number`.

**Câu 2.** Với `static <T extends Number> double twice(T value)`, `twice(4)` có hợp lệ không?

**Đáp án:** Có. Literal `int` được boxing tương thích với `Integer` trong quá trình suy luận/gọi method generic. `Integer` là subtype của `Number`.

**Câu 3.** Một method có `T extends Number` được gọi `compareTo()` trên `T` không?

**Đáp án:** Không. `Number` không khai báo `compareTo`. Nếu cần so sánh, ràng buộc `Comparable<? super T>` hoặc các multiple bounds thích hợp.

**Câu 4.** `<T extends Identified<String> & Named>` yêu cầu `T` thỏa mấy hợp đồng?

**Đáp án:** Cả hai: `Identified<String>` và `Named`. Dấu `&` thể hiện giao của các giới hạn; class được chọn phải đáp ứng tất cả.

**Câu 5.** `List<Integer>` có gán trực tiếp cho `List<Number>` không? Có thể gán cho `List<? extends Number>` không?

**Đáp án:** Không gán trực tiếp cho `List<Number>` vì generic type bất biến. Có thể gán cho `List<? extends Number>` để đọc giá trị theo một subtype chưa biết; không được thêm một `Number` tùy ý qua tham chiếu wildcard.

**Câu 6.** Tại sao không thể viết `new T()` trong phương thức `<T extends Number>`?

**Đáp án:** Upper bound không bảo đảm mọi subtype của `Number` đều có một constructor không tham số hợp lệ, và erasure không giữ đối số kiểu để khởi tạo trực tiếp. Dùng factory hoặc đối tượng được truyền vào.

**Câu 7.** Nếu lớp cha là `class NumericStore<T extends Number>`, dòng `class Child<T> extends NumericStore<T>` hợp lệ không?

**Đáp án:** Không, vì `T` của `Child` chưa bị ràng buộc. Cần `class Child<T extends Number> extends NumericStore<T>` hoặc chọn type argument cụ thể đáp ứng `Number`.

**Câu 8.** `max(List<String>)` trong ví dụ dựa vào độ dài chuỗi hay `compareTo`?

**Đáp án:** Dựa vào `compareTo`, tức thứ tự so sánh tự nhiên của `String` theo hợp đồng Java, không phải độ dài. Tên hàm không tự suy ra tiêu chí nghiệp vụ.

## Tổng kết

Cú pháp `<T extends U>` đặt một **upper bound** lên type parameter `T`, qua đó cho phép trình biên dịch kiểm tra và cho sử dụng những thao tác được bảo đảm bởi `U`. Bound có thể là class, interface, type variable hoặc nhiều giới hạn kết hợp bằng `&`. Một method với `T extends Number` được gọi `doubleValue()` nhưng **không** tự được gọi `compareTo()` hay sử dụng toán tử số học trực tiếp trên `T`; muốn thêm khả năng cần thêm bound hoặc thiết kế abstraction phù hợp. Khi cần liên hệ chính xác kiểu đầu vào và đầu ra, type parameter có tên hữu ích hơn wildcard; khi chỉ đọc dữ liệu, `? extends U` có thể đơn giản hơn. Upper bound chủ yếu bảo đảm **kiểu lúc biên dịch**, không thay thế kiểm tra `null`, độ chính xác số học, dữ liệu runtime hoặc quy tắc nghiệp vụ.