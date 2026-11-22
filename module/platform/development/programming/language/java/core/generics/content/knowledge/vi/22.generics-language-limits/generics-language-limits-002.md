# Không dùng primitive làm đối số kiểu trong Java Generics

## 1. Quy tắc cốt lõi và vấn đề thường gặp

Trong Java Generics, **đối số kiểu (*type argument*) phải là kiểu tham chiếu (*reference type*) thích hợp, không được là kiểu nguyên thủy (*primitive type*)**. Vì vậy, các khai báo này **không hợp lệ**:

```java
// CỐ Ý KHÔNG BIÊN DỊCH – minh họa các trường hợp sai:
List<int> numbers;
Set<boolean> flags;
Map<int, double> prices;
Optional<long> count;
```

`int`, `boolean`, `double`, `long` là các primitive types. Chúng không thể đứng trực tiếp trong dấu `<...>` với vai trò type argument của generic class/interface.

Thay vào đó, Java cung cấp các **wrapper classes** như `Integer`, `Boolean`, `Double`, `Long`:

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

class ValidDeclarations {
    List<Integer> numbers;
    Set<Boolean> flags;
    Map<Integer, Double> prices;
    Optional<Long> count;
}
```

Đoạn này là một class hợp lệ để minh họa khai báo; nó không có `main`.

Cần ghi nhớ ngay ba ý:

1. **`List<int>` sai**, **`List<Integer>` đúng**: `Integer` là một class, không phải primitive `int`.
2. **Autoboxing/unboxing** giúp viết code với `Integer` gần giống `int`, nhưng đây là các phép chuyển đổi thật, có hệ quả về `null`, so sánh và hiệu năng.
3. **Không phải mọi thứ chứa `int` đều bị cấm trong generic**: `int[]` là **kiểu mảng tham chiếu**, nên `List<int[]>` hoàn toàn hợp lệ.

Bài học này không chỉ yêu cầu nhớ tên wrapper: nó giúp chọn đúng loại lưu trữ và hiểu những lỗi tinh vi có thể phát sinh khi dùng Generics với dữ liệu số.

## 2. Các primitive types và wrapper classes tương ứng

Java có tám primitive types. Mỗi primitive có một wrapper class trong `java.lang`:

| Primitive | Wrapper | Ví dụ dùng làm type argument |
|---|---|---|
| `byte` | `Byte` | `List<Byte>` |
| `short` | `Short` | `List<Short>` |
| `int` | `Integer` | `List<Integer>` |
| `long` | `Long` | `List<Long>` |
| `float` | `Float` | `List<Float>` |
| `double` | `Double` | `List<Double>` |
| `char` | `Character` | `List<Character>` |
| `boolean` | `Boolean` | `List<Boolean>` |

Các wrapper này là **class tham chiếu** và có thể là type argument:

```java
java.util.List<Integer> ids = new java.util.ArrayList<>();
java.util.List<Character> letters = new java.util.ArrayList<>();
java.util.List<Boolean> enabled = new java.util.ArrayList<>();
```

Trong khi các dạng sau không hợp lệ:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
java.util.List<int> ids;
java.util.List<char> letters;
java.util.List<boolean> enabled;
```

Hai nhóm kiểu phục vụ những vai trò khác nhau:

- Primitive lưu và thực hiện phép toán với giá trị theo ngữ nghĩa primitive.
- Wrapper là đối tượng tham chiếu (hoặc `null`) có phương thức, tham gia hệ thống kế thừa class/interface và làm type argument hợp lệ.

Các wrapper không làm `int` trở thành subclass của `Object`. `Integer` mới là class kế thừa từ `Number` và gián tiếp từ `Object`.

## 3. Tại sao ngôn ngữ đặt ra giới hạn này?

Java Generics thông thường dựa trên **type erasure** (*xóa kiểu*) để duy trì một mô hình class/bytecode dùng chung cho nhiều type arguments. Một `ArrayList<String>` và một `ArrayList<Integer>` sử dụng cùng generic class ở runtime, thay vì JVM tự sinh một class chuyên biệt cho từng type argument.

Với:

```java
class Box<T> {
    T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Nếu type variable `T` không có bound tường minh, erasure của `T` là `Object`. Mã bytecode đại diện cho field và method có thể làm việc qua kiểu tham chiếu `Object`, sau đó compiler đặt các phép cast cần thiết tại nơi sử dụng kiểu cụ thể.

Primitive `int` **không phải reference type** và không thể được dùng như một instance của `Object` mà không chuyển sang wrapper. Do đó, một generic API được thiết kế theo type variables tham chiếu không cho phép trực tiếp đưa `int` vào `T`.

Nói cách khác, không thể suy luận rằng:

```java
Box<int> counter; // CỐ Ý KHÔNG HỢP LỆ.
```

sẽ tạo một `Box` lưu `int` nguyên thủy hiệu quả như một field kiểu `int`. Java Generics thông thường **không chuyên biệt hóa (*specialize*)** class `Box` cho primitive bằng cú pháp đó.

Thay vào đó:

```java
Box<Integer> counter = new Box<>(10);
```

được compiler chấp nhận: `10` được chuyển thành `Integer` nếu ngữ cảnh đòi wrapper.

**Giới hạn đang nói tới nằm ở vị trí *type argument*.** Nó không cấm bạn dùng primitive làm tham số phương thức bình thường, trường dữ liệu của class không generic, kiểu trả về, hay phần tử của mảng primitive.

## 4. Đối chiếu: primitive trong method hợp lệ, primitive trong `<...>` không hợp lệ

Hai tình huống này rất dễ bị nhầm:

```java
class Arithmetic {
    int doubleIt(int value) {
        return value * 2;
    }

    java.util.List<Integer> asList(int value) {
        return java.util.List.of(value);
    }
}
```

Class trên hợp lệ:

- `doubleIt` nhận và trả `int` trực tiếp, không có type argument nào.
- `asList` nhận `int` nhưng trả `List<Integer>`. Generic method `List.of` suy luận wrapper `Integer` trong ngữ cảnh phù hợp và boxing diễn ra ở bước truyền phần tử.

Ngược lại:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
class Broken<T extends int> { }
```

`T extends int` không hợp lệ vì `int` không phải reference type dùng được làm bound. Nếu cần giới hạn các wrapper số, có thể viết `<T extends Number>`:

```java
class NumericBox<T extends Number> {
    T value;
}
```

Sau đó `NumericBox<Integer>` và `NumericBox<Double>` hợp lệ; `NumericBox<int>` vẫn không hợp lệ.

## 5. Ví dụ Java 17 chạy được: `List<Integer>` thay `List<int>`

Tạo tệp **`WrapperListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WrapperListDemo {
    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();

        scores.add(8);
        scores.add(9);
        scores.add(10);

        int total = 0;

        for (int score : scores) {
            total += score;
        }

        System.out.println(scores);
        System.out.println(total);
        System.out.println(scores.get(0) + 2);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac WrapperListDemo.java
java WrapperListDemo
```

Stdout:

```text
[8, 9, 10]
27
10
```

Giải thích:

1. `scores` khai báo `List<Integer>`, **không** phải `List<int>`.
2. `scores.add(8)` hợp lệ nhờ **boxing**: một giá trị `int` được chuyển sang wrapper `Integer` ở nơi cần.
3. Vòng `for (int score : scores)` đọc mỗi `Integer` và **unbox** thành `int`.
4. `total` là `int`, nên các phép cộng dùng phép toán số nguyên thông thường.
5. `scores.get(0) + 2` yêu cầu giá trị số; `Integer` có thể được unbox để tính ra `10`.

Code này được kiểm tra generic ở compile time. Nếu thử `scores.add("text")`, compiler từ chối vì `String` không tương thích với `Integer`.

## 6. Autoboxing và unboxing hoạt động thế nào?

**Boxing conversion** chuyển một giá trị primitive sang kiểu wrapper tương ứng trong các ngữ cảnh mà Java cho phép.

**Unboxing conversion** chuyển một wrapper sang giá trị primitive tương ứng.

Ví dụ:

```java
Integer boxed = 42; // Boxing từ int sang Integer.
int primitive = boxed; // Unboxing từ Integer sang int.
```

Có thể xem biểu diễn minh họa gần tương đương:

```java
Integer boxed = Integer.valueOf(42);
int primitive = boxed.intValue();
```

Compiler có thể tạo lời gọi method hỗ trợ tương ứng và tối ưu hóa chúng theo ngữ cảnh. Ví dụ trên nhằm diễn giải ngữ nghĩa, **không phải cam kết chính xác mọi lệnh bytecode trong mọi bản JDK/JIT**.

### Chương trình quan sát chuyển đổi

Tạo **`BoxingConversionDemo.java`**:

```java
public class BoxingConversionDemo {
    public static void main(String[] args) {
        int original = 21;

        Integer boxed = original;
        int restored = boxed;

        Double pi = 3.5;
        double doubled = pi * 2;

        Boolean enabled = true;
        boolean active = enabled;

        System.out.println(boxed);
        System.out.println(restored);
        System.out.println(doubled);
        System.out.println(active);
    }
}
```

Lệnh:

```bash
javac BoxingConversionDemo.java
java BoxingConversionDemo
```

Stdout:

```text
21
21
7.0
true
```

Với `Double pi = 3.5`, compiler chọn wrapper `Double` từ literal `double`. Khi tính `pi * 2`, phép toán cần giá trị số primitive, nên có unboxing; kiểu kết quả là `double`.

Những chuyển đổi này giúp API Generic dễ dùng, nhưng **không miễn phí về mặt ngữ nghĩa**: wrapper có thể là `null`, có identity của reference và có thể có chi phí lưu trữ khác primitive.

## 7. `null` là nguy cơ đặc biệt khi unboxing

Primitive `int` không thể có giá trị `null`. `Integer` là reference type, nên có thể là `null`.

Ví dụ:

```java
Integer count = null;
// int total = count; // Có thể ném NullPointerException.
```

Đây không phải lỗi compiler; phép gán sang `int` có thể biên dịch thành công, rồi thất bại khi chạy nếu `count == null`.

Tạo tệp **`UnboxingNullDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class UnboxingNullDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>();
        values.add(10);
        values.add(null);

        System.out.println(values.size());
        System.out.println(values.get(0));

        try {
            int number = values.get(1);
            System.out.println(number);
        } catch (NullPointerException ex) {
            System.out.println("NullPointerException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac UnboxingNullDemo.java
java UnboxingNullDemo
```

Stdout:

```text
2
10
NullPointerException
```

`ArrayList<Integer>` có thể chứa `null`. Khi `values.get(1)` được dùng ở vị trí `int`, compiler thực hiện unboxing, và giá trị `null` không thể được giải tham chiếu để lấy primitive.

Không phải mọi collection cho phép `null`:

- `new ArrayList<Integer>()` cho phép `null`.
- `List.of(1, null)` ném `NullPointerException` ngay khi tạo danh sách.
- `List.copyOf` từ chối `null` trong nguồn.

**Thực hành tốt:** Quyết định rõ `null` có phải giá trị hợp lệ trong hợp đồng dữ liệu hay không. Nếu không, kiểm tra hoặc dùng collection/factory có chính sách ngăn `null`. Nếu có, phải xử lý `null` trước unboxing.

## 8. Wrapper không phải primitive: so sánh bằng `==` và `equals`

Một khác biệt đáng chú ý là `Integer` là object tham chiếu.

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b));
```

Dòng in `true`, vì hai đối tượng biểu diễn cùng giá trị số.

Nhưng `a == b` trong trường hợp **cả hai biến đều là wrapper tham chiếu** có ý nghĩa kiểm tra **cùng object hay không**, không phải so sánh số học. Không nên dựa vào việc JVM cache hay không cache từng giá trị wrapper để đưa ra một kết luận phổ quát.

Đặc biệt, với `Integer` nằm trong khoảng nhỏ, Java có quy tắc và cách triển khai boxing/cache khiến một số phép `==` tình cờ trả `true`; ngoài khoảng đó, hành vi identity không nên dùng làm hợp đồng. Dùng `.equals(...)` hoặc so sánh primitive sau khi xử lý `null`.

Tệp **`WrapperEqualityDemo.java`**:

```java
import java.util.Objects;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer first = 1000;
        Integer second = 1000;

        System.out.println(first.equals(second));
        System.out.println(Objects.equals(first, second));
        System.out.println(first.intValue() == second.intValue());

        Integer absent = null;
        System.out.println(Objects.equals(absent, null));
    }
}
```

Biên dịch/chạy:

```bash
javac WrapperEqualityDemo.java
java WrapperEqualityDemo
```

Stdout:

```text
true
true
true
true
```

Ví dụ cố tình **không in `first == second`** để tránh khiến người học dựa vào wrapper identity. Nếu quan tâm giá trị, hãy dùng `.equals` hoặc `Objects.equals` khi có thể có `null`; nếu quan tâm giá trị nguyên thủy và đã chắc chắn không null, unbox rồi so sánh primitive.

Cũng nên tránh trộn `Integer` nullable vào biểu thức với literal `int` mà không cân nhắc unboxing. Ví dụ `Integer x = null; boolean zero = (x == 0);` có thể ném `NullPointerException`.

## 9. Type inference với primitive: compiler thường chọn wrapper

Một generic method khai báo tham số kiểu `T`:

```java
static <T> T identity(T value) {
    return value;
}
```

Khi gọi:

```java
Integer result = identity(123);
```

compiler không suy luận `T = int` như một primitive type argument bất hợp lệ. Trong ngữ cảnh thích hợp, nó sử dụng boxing và suy luận một reference type, ở đây là `Integer`.

Tạo tệp **`GenericInferencePrimitiveDemo.java`**:

```java
import java.util.List;

public class GenericInferencePrimitiveDemo {

    static <T> T identity(T value) {
        return value;
    }

    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    public static void main(String[] args) {
        Integer boxed = identity(7);
        int primitive = identity(7);

        List<Integer> numbers = singleton(9);

        System.out.println(boxed);
        System.out.println(primitive);
        System.out.println(numbers);

        System.out.println(numbers.get(0) + 1);
    }
}
```

Lệnh:

```bash
javac GenericInferencePrimitiveDemo.java
java GenericInferencePrimitiveDemo
```

Stdout:

```text
7
7
[9]
10
```

Diễn giải:

1. Generic method `<T> T identity(T value)` đòi `T` thuộc hệ kiểu tham chiếu.
2. Literal `7` là `int`, được boxing phù hợp với suy luận generic.
3. Kết quả có thể gán cho `Integer`; nếu gán cho `int`, unboxing cung cấp giá trị primitive.
4. `singleton(9)` suy luận `T = Integer`, tạo `List<Integer>`.

**Không có chuyện compiler âm thầm tạo `List<int>` rồi che nó đi.** Các type arguments được biểu diễn theo hệ thống kiểu tham chiếu.

## 10. `List.of`, `Arrays.asList` và bẫy mảng primitive

Khi muốn biến nhiều số nguyên thành `List<Integer>`, hãy cẩn thận nếu nguồn ban đầu là `int[]`.

Xét:

```java
int[] raw = {1, 2, 3};

var fromArray = java.util.Arrays.asList(raw);
```

`Arrays.asList` là generic varargs method nhận **đối tượng** làm phần tử. `int[]` là một object mảng; các giá trị primitive **bên trong** mảng không được tự động boxing thành từng `Integer` nhờ truyền toàn bộ `int[]` vào varargs.

Kết quả của `Arrays.asList(raw)` là `List<int[]>` với **một phần tử**, chính là object mảng `raw`, chứ không phải `List<Integer>` có ba phần tử.

Tạo tệp **`PrimitiveArrayListTrapDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveArrayListTrapDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3};

        List<int[]> nested = Arrays.asList(raw);
        List<Integer> boxed = IntStream.of(raw)
                .boxed()
                .toList();

        System.out.println(nested.size());
        System.out.println(nested.get(0).length);
        System.out.println(boxed);
        System.out.println(boxed.size());
    }
}
```

Biên dịch/chạy:

```bash
javac PrimitiveArrayListTrapDemo.java
java PrimitiveArrayListTrapDemo
```

Stdout:

```text
1
3
[1, 2, 3]
3
```

Điểm cần nhớ:

- `int[]` là **reference type**, vì mảng là object; do đó `List<int[]>` hợp lệ.
- `Arrays.asList(raw)` đưa nguyên object `int[]` vào list.
- `IntStream.of(raw).boxed()` tạo stream wrapper `Integer` từ các giá trị `int`.
- `.toList()` (Java 16+) tạo một list không thể chỉnh sửa qua API chuẩn; không nên gọi `add` lên kết quả.

Nếu cần `ArrayList<Integer>` mutable, dùng `collect(Collectors.toCollection(ArrayList::new))` sau `.boxed()` hoặc tạo `new ArrayList<>(boxed)`.

## 11. Khi `List<int[]>` là thiết kế đúng

Giới hạn generic primitive không cấm dùng **mảng primitive như một phần tử tham chiếu**.

Ví dụ:

```java
java.util.List<int[]> rows = new java.util.ArrayList<>();
rows.add(new int[] {1, 2});
rows.add(new int[] {3, 4});
```

List trên có hai phần tử kiểu `int[]`, không phải bốn phần tử kiểu `Integer`. Nó phù hợp khi mỗi phần tử là một khối dữ liệu số nguyên, ví dụ một hàng ma trận hoặc một mẫu dữ liệu.

Ví dụ độc lập **`PrimitiveArrayElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PrimitiveArrayElementDemo {
    public static void main(String[] args) {
        List<int[]> rows = new ArrayList<>();

        rows.add(new int[] {1, 2});
        rows.add(new int[] {3, 4, 5});

        for (int[] row : rows) {
            int sum = 0;

            for (int value : row) {
                sum += value;
            }

            System.out.println(sum);
        }
    }
}
```

Lệnh:

```bash
javac PrimitiveArrayElementDemo.java
java PrimitiveArrayElementDemo
```

Stdout:

```text
3
12
```

Mỗi `row` là object mảng chứa primitive `int`. Vì `int[]` là reference type, nó có thể điền vào type argument của `List`. Các giá trị `int` bên trong vẫn nằm trong array primitive, không cần boxing từng phần tử ở lớp lưu trữ mảng.

Cần nhớ thêm rằng list **không sao chép sâu** các mảng được thêm vào. Nếu caller thay `rows.get(0)[0]`, nội dung mảng cũng thay đổi.

## 12. Giới hạn với nhiều kiểu generic khác nhau

Không chỉ `List` mới cấm primitive type arguments.

Các khai báo sau đều sai:

```java
// CỐ Ý KHÔNG HỢP LỆ:
java.util.Set<char> letters;
java.util.Map<int, String> namesById;
java.util.function.Supplier<double> supplier;
java.util.Optional<boolean> present;
```

Các phiên bản hợp lệ:

```java
java.util.Set<Character> letters;
java.util.Map<Integer, String> namesById;
java.util.function.Supplier<Double> supplier;
java.util.Optional<Boolean> present;
```

Tương tự với class tự viết:

```java
class Pair<A, B> {
    A left;
    B right;
}
```

Ta có thể dùng `Pair<Integer, Double>`, nhưng không được dùng `Pair<int, double>`.

Đây là **quy tắc của hệ thống type arguments**, không phải quy tắc riêng của Java Collections Framework.

Ngoài ra, generic method declaration:

```java
static <T> T first(T a, T b) {
    return a;
}
```

không thể được gọi bằng type witness primitive:

```java
// CỐ Ý KHÔNG HỢP LỆ:
Utils.<int>first(1, 2);
```

Nếu cần viết rõ type witness, dùng reference type như `<Integer>`, với điều kiện method được truy cập hợp lệ trong code thật.

## 13. Numeric wrappers và kiểu chung `Number`

Các wrapper số như `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` đều kế thừa từ `Number`, do đó có thể dùng một danh sách phần tử kiểu `Number` để chứa nhiều wrapper.

Tệp **`NumberCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NumberCollectionDemo {

    static double total(List<? extends Number> values) {
        double result = 0.0;

        for (Number number : values) {
            result += number.doubleValue();
        }

        return result;
    }

    public static void main(String[] args) {
        List<Number> mixed = new ArrayList<>();

        mixed.add(2);
        mixed.add(3.5);
        mixed.add(4L);

        System.out.println(mixed);
        System.out.println(total(mixed));
        System.out.println(total(List.of(1, 2, 3)));
    }
}
```

Biên dịch/chạy:

```bash
javac NumberCollectionDemo.java
java NumberCollectionDemo
```

Stdout:

```text
[2, 3.5, 4]
9.5
6.0
```

Các literal `2`, `3.5`, `4L` có thể được boxing thành `Integer`, `Double`, `Long`; tất cả phù hợp với `Number`.

Với `List<? extends Number>`, phương thức `total` chỉ cần **đọc** phần tử dưới dạng `Number`, nên nó có thể nhận `List<Integer>`, `List<Double>` hoặc `List<Number>`. Đây là ứng dụng PECS (*Producer Extends*) với wrapper numbers.

**Không nhầm `List<Integer>` với subtype của `List<Number>`.** Generic Java mặc định invariant:

```java
List<Integer> integers = List.of(1, 2);
// List<Number> numbers = integers; // CỐ Ý KHÔNG HỢP LỆ.
List<? extends Number> readable = integers; // Hợp lệ.
```

Biến `readable` có thể đọc `Number`, nhưng không thể tùy tiện thêm một `Double` vào danh sách vốn có thể là `List<Integer>`.

## 14. Bẫy conversion: không có mọi kiểu chuyển đổi trong một bước boxing

Một số người kỳ vọng một wrapper generic tự hỗ trợ tất cả các numeric widenings như primitive.

Ví dụ `Long` và `Integer` là **hai wrapper classes khác nhau**:

```java
java.util.List<Long> ids = new java.util.ArrayList<>();
ids.add(1L); // Hợp lệ.

// ids.add(1); // Không hợp lệ: int không tự boxing thành Long.
```

Với lời gọi `ids.add(1)`, compiler không tự động thực hiện chuỗi “`int` -> `long` -> `Long`” chỉ vì đích là `Long`; Java không cung cấp mọi kết hợp widening-then-boxing như một conversion mặc định tại lời gọi này.

Sửa bằng:

```java
ids.add(1L);
ids.add(Long.valueOf(1));
```

Đối với hàm nhận `Number`, boxing một `int` thành `Integer` rồi widening reference sang `Number` là một trường hợp được phép:

```java
java.util.List<Number> numbers = new java.util.ArrayList<>();
numbers.add(1); // Integer là Number.
```

Khi gặp lỗi compiler với wrapper, hãy phân biệt **primitive widening**, **boxing**, **reference widening**, và các tổ hợp conversion được JLS thực sự cho phép. Đừng giả định mọi cú pháp nhìn giống numeric conversion đều hợp lệ.

## 15. Wrapper có ảnh hưởng hiệu năng và bộ nhớ không?

Khi cần lưu hàng triệu giá trị số:

- `int[]` lưu primitive `int` trong một object mảng.
- `List<Integer>` lưu các **reference** tới wrapper objects thông qua một implementation thích hợp, điển hình là `ArrayList` có mảng nội bộ chứa references.
- Boxing có thể tạo object wrapper hoặc tận dụng object được cache theo quy tắc/triển khai; không nên tự suy ra số lượng cấp phát tuyệt đối từ một đoạn code.
- Unboxing có thể thêm thao tác chuyển đổi, và nếu dữ liệu có `null` sẽ phát sinh `NullPointerException`.
- Trong các vòng lặp tính toán lớn, chi phí nhớ/cache/GC/boxing có thể ảnh hưởng đáng kể; nhưng các tối ưu hóa của JIT có thể khiến thực tế phụ thuộc workload.

Vì vậy `List<Integer>` không nhất thiết là cách tốt nhất để lưu một lượng lớn primitive `int` nếu mục tiêu là hiệu năng/mật độ dữ liệu. Nhưng nó thường là lựa chọn phù hợp khi cần các API Collections chuẩn: thay đổi kích thước, `contains`, `Map`, tương tác với code generic, v.v.

**Không kết luận “List luôn chậm”** chỉ từ việc có boxing. Muốn tối ưu một đường xử lý số, hãy dùng benchmark đáng tin như JMH trên workload đại diện.

## 16. Khi cần xử lý primitive hàng loạt, dùng `IntStream`, `LongStream`, `DoubleStream`

Java Stream API có các phiên bản **chuyên cho primitive**:

- `IntStream` xử lý `int`.
- `LongStream` xử lý `long`.
- `DoubleStream` xử lý `double`.

Chúng giúp thực hiện nhiều thao tác số học mà không cần trình bày dữ liệu theo `Stream<Integer>` hoặc `List<Integer>` ở mọi bước.

Tạo tệp **`PrimitiveStreamDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveStreamDemo {
    public static void main(String[] args) {
        int total = IntStream.rangeClosed(1, 4).sum();
        double average = IntStream.of(2, 4, 6)
                .average()
                .orElse(0.0);

        List<Integer> boxed =
                IntStream.of(3, 5, 7)
                        .boxed()
                        .toList();

        System.out.println(total);
        System.out.println(average);
        System.out.println(boxed);
    }
}
```

Biên dịch/chạy:

```bash
javac PrimitiveStreamDemo.java
java PrimitiveStreamDemo
```

Stdout:

```text
10
4.0
[3, 5, 7]
```

`IntStream.sum()` trả `int`, còn `average()` trả `OptionalDouble` vì trung bình có thể vắng mặt khi stream rỗng.

`.boxed()` chuyển dòng primitive `int` thành `Stream<Integer>`; `.toList()` tạo danh sách wrapper không sửa được qua API chuẩn trong Java 17. Nếu cần tiếp tục xử lý primitive, nên giữ primitive stream đến khi thật sự cần chuyển sang object API.

**Không có `Stream<int>`**. Cú pháp đúng là `IntStream`, hoặc `Stream<Integer>` khi muốn làm việc với wrappers.

## 17. Primitive-specialized Optional và functional interfaces

Giới hạn type arguments cũng giải thích vì sao Java cung cấp nhiều API chuyên biệt cho primitive.

Ví dụ:

| Mục tiêu | Generic reference API | Primitive-specialized API |
|---|---|---|
| Giá trị số nguyên có thể vắng mặt | `Optional<Integer>` | `OptionalInt` |
| Giá trị số thực double có thể vắng mặt | `Optional<Double>` | `OptionalDouble` |
| Giá trị long có thể vắng mặt | `Optional<Long>` | `OptionalLong` |
| Hàm trả `int` không tham số | `Supplier<Integer>` | `IntSupplier` |
| Hàm nhận `int` | `Consumer<Integer>` | `IntConsumer` |
| Predicate nhận `int` | `Predicate<Integer>` | `IntPredicate` |
| Ánh xạ `int` sang `int` | `Function<Integer,Integer>` | `IntUnaryOperator` |
| Hàm nhận `int`, trả object `R` | `Function<Integer,R>` | `IntFunction<R>` |
| Hàm nhận object `T`, trả `int` | `Function<T,Integer>` | `ToIntFunction<T>` |

Các kiểu chuyên biệt mô tả primitive ngay trong chữ ký API và có thể tránh boxing/unboxing trong một số thao tác.

Tệp **`PrimitiveFunctionalDemo.java`**:

```java
import java.util.OptionalInt;
import java.util.function.IntPredicate;
import java.util.function.IntUnaryOperator;

public class PrimitiveFunctionalDemo {
    public static void main(String[] args) {
        IntUnaryOperator twice = n -> n * 2;
        IntPredicate positive = n -> n > 0;

        OptionalInt result = OptionalInt.of(twice.applyAsInt(6));

        System.out.println(result.getAsInt());
        System.out.println(positive.test(10));
        System.out.println(positive.test(-1));
    }
}
```

Biên dịch/chạy:

```bash
javac PrimitiveFunctionalDemo.java
java PrimitiveFunctionalDemo
```

Stdout:

```text
12
true
false
```

`IntUnaryOperator` và `IntPredicate` nhận/trả primitive `int` theo chữ ký; chúng **không** phải generic interface được tham số hóa bằng `<int>`.

`OptionalInt` không cần type argument; nó đã được thiết kế chuyên biệt cho `int`. Nếu cần giá trị vắng mặt, `OptionalInt.empty()` biểu diễn điều đó mà không dùng `null` như một giá trị `int`.

## 18. Khi nào nên chọn `Integer[]`, `int[]` và `List<Integer>`?

Cả ba đều hợp lệ, nhưng ý nghĩa khác nhau.

| Loại | Phần tử | Kích thước | `null` ở cấp phần tử | Hợp đồng chính |
|---|---|---|---|---|
| `int[]` | Primitive `int` | Cố định | Không thể | Mảng primitive, runtime biết component `int` |
| `Integer[]` | Reference `Integer` | Cố định | Có thể | Mảng reference wrapper |
| `List<Integer>` | Reference `Integer` | Tùy implementation | Tùy implementation | Collection generic, nhiều tiện ích |
| `List<int[]>` | Reference tới object `int[]` | Tùy implementation | Tùy implementation | Mỗi phần tử là một mảng primitive |
| `IntStream` | Dòng giá trị `int` | Không biểu diễn trực tiếp số slot có thể sửa | Không có phần tử null | Pipeline thao tác số nguyên |

**Cần số slot cố định và lưu primitive trực tiếp?** `int[]` thường là lựa chọn tự nhiên.

**Cần nhiều tiện ích Collections, thay đổi số phần tử, làm key/value hoặc dữ liệu generic?** `List<Integer>` hoặc các container wrapper phù hợp.

**Cần các dãy primitive theo từng nhóm?** `List<int[]>` có thể đúng, nhưng phải cân nhắc mutation của mảng con.

**Cần pipeline tính toán?** `IntStream` giúp mô tả thao tác số mà không phải chuyển tất cả giá trị sang wrappers.

`Integer[]` khác `int[]` ở runtime component type, ngữ nghĩa null và nơi áp dụng boxing/unboxing.

## 19. Ví dụ xử lý dữ liệu: chọn primitive array hoặc generic list

Tệp **`PrimitiveVsWrapperStorageDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PrimitiveVsWrapperStorageDemo {

    static int sumArray(int[] values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    static int sumList(List<Integer> values) {
        int sum = 0;
        for (Integer value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] primitive = {4, 5, 6};
        List<Integer> wrappers =
                new ArrayList<>(List.of(4, 5, 6));

        System.out.println(Arrays.toString(primitive));
        System.out.println(wrappers);
        System.out.println(sumArray(primitive));
        System.out.println(sumList(wrappers));

        wrappers.add(7);
        System.out.println(wrappers.size());
    }
}
```

Lệnh:

```bash
javac PrimitiveVsWrapperStorageDemo.java
java PrimitiveVsWrapperStorageDemo
```

Stdout:

```text
[4, 5, 6]
[4, 5, 6]
15
15
4
```

Ví dụ này không định đo tốc độ. Nó chỉ cho thấy:

- `sumArray` đọc primitive trực tiếp.
- `sumList` unbox `Integer` mỗi lần đưa vào phép cộng, và cần có chính sách rõ với `null`.
- `ArrayList` có thể thêm phần tử, còn kích thước mảng `int[]` được cố định khi tạo.

Nếu phần tử `null` xuất hiện trong `wrappers`, `sumList` có thể ném `NullPointerException`. Ngữ nghĩa này quan trọng hơn việc hai ví dụ đều in tổng `15` với dữ liệu hợp lệ.

## 20. Không được nhầm wrapper và class runtime của primitive

`Integer.class` là class token cho wrapper reference type `Integer`. Primitive type `int` có class literal hợp lệ là `int.class`, nhưng điều đó **không** khiến `int` trở thành reference type dùng được cho Generics.

Một class token có thể đại diện cho primitive type nhằm phục vụ reflection, trong khi generic type arguments vẫn chịu điều kiện là kiểu tham chiếu.

Ví dụ:

```java
System.out.println(int.class.isPrimitive());
System.out.println(Integer.class.isPrimitive());
```

Nếu đặt trong method Java, hai dòng trên lần lượt in:

```text
true
false
```

**Điểm cần nhớ:** Khả năng runtime/reflection có đối tượng `Class` đại diện cho primitive không thay đổi cú pháp `List<int>` thành hợp lệ.

Khi viết một API cần runtime class token:

```java
static <T> T checkedCast(Object value, Class<T> type) {
    return type.cast(value);
}
```

`T` vẫn là type variable generic tham chiếu. `Class<T>` không phải một cơ chế cho phép khai báo `T = int` bằng type argument primitive. Nếu API cần xử lý `int` trực tiếp, nên dùng primitive-specific signature hoặc wrapper `Integer` theo thiết kế.

## 21. Những lỗi phổ biến

**Lỗi 1 — “`List<int>` viết ngắn hơn `List<Integer>`.”** Không phải cú pháp hợp lệ. Type argument phải là reference type phù hợp.

**Lỗi 2 — “`int` kế thừa `Number`.”** Sai. `Integer` là subclass của `Number`; primitive `int` không phải class.

**Lỗi 3 — “`List<Integer>` lưu `int` trực tiếp như `int[]`.”** Không. Collection generic làm việc với wrappers ở lớp API, trong khi mảng primitive có component `int`.

**Lỗi 4 — “Boxing và unboxing hoàn toàn miễn phí.”** Không thể khẳng định. Có thể có chi phí object/conversion, tùy code và tối ưu hóa runtime.

**Lỗi 5 — “`Integer` không thể `null` vì biểu diễn `int`.”** Sai. Wrapper là reference và có thể `null`.

**Lỗi 6 — “Có thể dùng `==` an toàn để so giá trị hai `Integer`.”** Nếu cả hai toán hạng là references, `==` thường kiểm tra identity, không phải numeric equality. Dùng `.equals` hoặc primitive sau khi kiểm tra null.

**Lỗi 7 — “`List<Integer>` là `List<Number>` vì `Integer` là `Number`.”** Sai. Generic Java invariant; dùng wildcard phù hợp nếu API chỉ cần đọc kiểu cha.

**Lỗi 8 — “`Arrays.asList(int[])` trả list các `Integer`.”** Sai. `int[]` được coi là một phần tử reference, nên thường cho `List<int[]>` một phần tử.

**Lỗi 9 — “`List<int[]>` cũng bị cấm vì có chữ `int`.”** Sai. `int[]` là **array reference type**, hợp lệ làm type argument.

**Lỗi 10 — “`List<Long>` tự nhận literal `1` vì số nào cũng ép được.”** Không. Một `int` không tự chuyển qua mọi chuỗi widening-plus-boxing thành `Long`; dùng `1L` khi muốn `Long`.

**Lỗi 11 — “`Optional<int>` hợp lệ vì `Optional` dành cho giá trị có thể vắng mặt.”** Sai. Có `OptionalInt` chuyên biệt hoặc `Optional<Integer>`.

**Lỗi 12 — “`Stream<int>` giúp tránh boxing.”** Không hợp lệ. Dùng `IntStream`, không phải parameterized `Stream<int>`.

**Lỗi 13 — “Generics bị xóa nghĩa là compiler không kiểm tra được wrapper.”** Sai. `List<Integer>` có compile-time type checking mạnh; vấn đề riêng là primitive type arguments không được hỗ trợ.

**Lỗi 14 — “Primitive không được dùng ở bất kỳ vị trí nào trong generic class.”** Sai. Một generic class vẫn có thể khai báo `int count`, nhận tham số `double rate`, hoặc dùng `int[]`; điều bị giới hạn ở đây là primitive làm *type argument* hoặc type-variable bound không hợp lệ.

## 22. Bài tập tự kiểm tra có đáp án

**Câu 1.** Trong các khai báo sau, dòng nào hợp lệ?

```java
List<int> a;          // A
List<Integer> b;      // B
List<int[]> c;        // C
```

**Đáp án:** B và C hợp lệ. A không hợp lệ. Ví dụ cần import `java.util.List` và đặt trong class/method.

**Câu 2.** `Integer x = 5; int y = x;` thực hiện những chuyển đổi gì?

**Đáp án:** Boxing `int` thành `Integer` ở phép gán đầu và unboxing `Integer` thành `int` ở phép gán sau.

**Câu 3.** `Integer x = null; int y = x;` lỗi ở giai đoạn nào?

**Đáp án:** Có thể biên dịch, nhưng ném `NullPointerException` khi unboxing tại runtime.

**Câu 4.** `List<Integer>` có tự động gán cho `List<Number>` không?

**Đáp án:** Không; Java Generics invariant. Nếu chỉ đọc số, có thể dùng `List<? extends Number>`.

**Câu 5.** `Arrays.asList(new int[] {1,2,3}).size()` là bao nhiêu?

**Đáp án:** `1`, vì một mảng `int[]` được xem như một object phần tử của generic varargs.

**Câu 6.** Cần `List<Integer>` từ một `int[]`, có thể dùng gì trên Java 17?

**Đáp án:** `Arrays.stream(source).boxed().toList()` hoặc `IntStream.of(source).boxed().toList()`.

**Câu 7.** `List<Long> ids = new ArrayList<>(); ids.add(1);` hợp lệ không?

**Đáp án:** Không. Literal `1` có kiểu `int`; dùng `1L` hoặc `Long.valueOf(1)`.

**Câu 8.** `List<int[]>` lưu mỗi giá trị như thế nào?

**Đáp án:** Mỗi **phần tử của List** là một object mảng `int[]`, và các `int` nằm bên trong từng mảng ấy.

**Câu 9.** Nếu cần tổng các số nguyên lớn, tại sao nên cân nhắc `int[]` hoặc `IntStream`?

**Đáp án:** Vì chúng hỗ trợ thao tác primitive trực tiếp, có thể tránh một phần chi phí boxing/unboxing. Cần đo thực tế trước khi kết luận hiệu năng.

**Câu 10.** Vì sao `Integer.class` hoặc `int.class` không làm `List<int>` hợp lệ?

**Đáp án:** Reflection class tokens không thay đổi quy tắc type argument của ngôn ngữ; `int` vẫn là primitive type.

**Câu 11.** Cần optional value kiểu primitive `int`, có các lựa chọn nào?

**Đáp án:** `OptionalInt` cho API chuyên primitive hoặc `Optional<Integer>` khi cần generic wrapper API.

**Câu 12.** Có nên so sánh hai wrapper bằng `==` khi nghiệp vụ cần giá trị số?

**Đáp án:** Không nên. Dùng `Objects.equals(a,b)` để xử lý nullable references hoặc kiểm tra null rồi so sánh primitive.

## 23. Checklist thiết kế API liên quan primitive

Khi thiết kế một class/method Generic, hãy xét:

1. **Type argument có phải primitive không?** Nếu có, thay bằng wrapper hoặc chọn API chuyên primitive.
2. **Có cần tập hợp kích thước động không?** `List<Integer>`, `Set<Long>`, `Map<Integer,Double>` có thể phù hợp.
3. **Có cần dữ liệu primitive dày đặc hoặc thao tác số học nhiều không?** Xem xét `int[]`, `double[]`, `IntStream`, `DoubleStream`.
4. **Có thể nhận `null` không?** Nếu wrapper nullable, thiết kế chính sách trước khi unbox.
5. **Có đang so sánh wrapper bằng `==` không?** Nếu mục tiêu là value equality, sửa thành `.equals` hoặc `Objects.equals`.
6. **Có chuyển `int[]` sang `List<Integer>` không?** Đừng dùng nhầm `Arrays.asList(int[])`; cần boxing từng phần tử.
7. **Có đang giả định `List<Integer>` là `List<Number>` không?** Sử dụng variance/wildcards phù hợp.
8. **Có cần loại bỏ giá trị vắng mặt mà không dùng wrapper `null`?** Dùng `OptionalInt` hoặc một hợp đồng return primitive phù hợp.
9. **Có dùng type witness primitive như `<int>` không?** Sửa thành wrapper type hoặc để compiler boxing/infer hợp lệ.
10. **Có cần tương thích API bên ngoài không?** Nếu API nhận primitive array, đừng ép dùng generic collection chỉ vì đang học Generics.

Thiết kế rõ ràng thường tốt hơn việc ẩn boxing và casts sau các abstraction phức tạp. Mọi lựa chọn nên dựa trên semantics của dữ liệu và hình thức API cần hỗ trợ.

## 24. Tổng kết và tài liệu chuẩn

**Java Generics không cho primitive types như `int`, `double`, `boolean` làm type arguments.** Muốn dùng API generic, chọn wrapper class tương ứng: `Integer`, `Double`, `Boolean`, v.v. Java có autoboxing/unboxing để kết nối primitive và wrapper trong code thường ngày, nhưng các chuyển đổi này có hệ quả về `null`, equality và có thể cả hiệu năng.

Đừng nhầm lẫn giữa **primitive type** và **array of primitive**: `int` không phải reference type, còn `int[]` là object mảng tham chiếu, nên `List<int[]>` hợp lệ. Với nhiều giá trị primitive, cân nhắc `int[]`, `IntStream`, `OptionalInt` hoặc các primitive-specialized functional interfaces thay vì bắt buộc chuyển mọi thứ thành `List<Integer>`.

Chọn cấu trúc phù hợp với bài toán:

- Dùng `List<Integer>` cho Collection API khi cần generic reference elements.
- Dùng `int[]` khi cần lưu primitive có độ dài cố định.
- Dùng `IntStream` khi pipeline phép toán có ích.
- Dùng `OptionalInt` khi cần một giá trị `int` có thể vắng mặt.
- Dùng wrapper/reference generics khi cần API tổng quát và an toàn kiểu ở compile time.

Tài liệu đáng tin cậy để đối chiếu:

- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): quy tắc type arguments.
- [Java Language Specification §4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference type so với primitive type.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure của type variables và parameterized types.
- [Java Language Specification §5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7): chuyển primitive sang wrapper.
- [Java Language Specification §5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): chuyển wrapper sang primitive và tình huống `null`.
- [Java SE 17 `java.lang.Integer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): wrapper `Integer` và các API liên quan.
- [Java SE 17 `java.util.stream.IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): stream chuyên primitive int.
- [Java SE 17 `java.util.OptionalInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html): optional cho primitive `int`.