# Khai báo generic record và ràng buộc kiểu cho component

## 1. Vì sao record cần generic?

Một record thường biểu diễn một tập giá trị có cấu trúc xác định. Khi kiểu dữ liệu cần mang những giá trị thuộc nhiều kiểu khác nhau, ta có thể khai báo record generic để tái sử dụng cùng một cấu trúc mà vẫn giữ kiểm tra kiểu ở thời điểm biên dịch.

Ví dụ, một cặp giá trị có thể chứa hai kiểu khác nhau:

~~~java
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> result = new Pair<>("Created", 201);
System.out.println(result.left());  // Created
System.out.println(result.right()); // 201
~~~

**Pair<L, R>** khai báo hai tham số kiểu: **L** và **R**. Component **left** có kiểu **L**; component **right** có kiểu **R**. Khi tạo **Pair<String, Integer>**, compiler thay **L** bằng **String** và **R** bằng **Integer** trong ngữ cảnh sử dụng.

Generic record là tính năng ngôn ngữ ổn định, có thể dùng từ Java 16 trở lên. Nó kết hợp quy tắc record với hệ thống generic của Java: component vẫn có accessor, canonical constructor và ngữ nghĩa bình đẳng theo component; kiểu cụ thể được kiểm tra tại compile time.

Mục tiêu bài học:

- Khai báo tham số kiểu trên record header.
- Dùng type parameter làm kiểu của component.
- Khai báo nhiều tham số kiểu, generic lồng nhau và wildcard.
- Đặt giới hạn kiểu bằng extends, nhiều bound và recursive bound.
- Hiểu type inference, diamond operator và generic factory method.
- Nhận diện giới hạn do type erasure và tránh raw type.

## 2. Cú pháp khai báo generic record

Cú pháp tổng quát:

~~~java
record RecordName<T>(T value) {}
~~~

Danh sách tham số kiểu nằm **sau tên record và trước record header**. Các component được khai báo trong ngoặc tròn như record thông thường.

Ví dụ:

~~~java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Triple<A, B, C>(A first, B second, C third) {}
~~~

Một record có thể có một hoặc nhiều tham số kiểu. Mỗi tham số kiểu là một tên đại diện cho một kiểu cụ thể sẽ được cung cấp khi sử dụng record.

Tên tham số kiểu thường dùng một chữ cái viết hoa theo convention Java:

| Tên thường gặp | Ý nghĩa thường dùng |
| --- | --- |
| **T** | Type, một kiểu tổng quát. |
| **E** | Element, kiểu phần tử. |
| **K** | Key, kiểu khóa. |
| **V** | Value, kiểu giá trị. |
| **N** | Number, kiểu số hoặc kiểu có liên quan đến số. |
| **R** | Result hoặc kiểu kết quả. |
| **S**, **U** | Các tham số kiểu bổ sung. |

Đây chỉ là quy ước đặt tên. Có thể dùng tên mô tả như **Payload**, **Key** hoặc **ResultType** nếu giúp API dễ đọc hơn.

### Generic record với một component

~~~java
record ApiResponse<T>(T data) {}

ApiResponse<String> message =
    new ApiResponse<>("Saved");

ApiResponse<Integer> count =
    new ApiResponse<>(25);
~~~

Ở đây, cùng kiểu **ApiResponse** được sử dụng với hai kiểu component khác nhau. Với **ApiResponse<String>**, accessor **data()** có kiểu trả về **String**; với **ApiResponse<Integer>**, accessor **data()** có kiểu trả về **Integer**.

### Generic record với nhiều component

~~~java
record Entry<K, V>(K key, V value) {}

Entry<Long, String> entry =
    new Entry<>(100L, "Java");

Long id = entry.key();
String label = entry.value();
~~~

Mỗi component có thể sử dụng một tham số kiểu riêng. Kiểu được truyền vào khi tạo record phải phù hợp với tất cả vị trí sử dụng tương ứng.

## 3. Dùng type parameter làm kiểu component

Type parameter có thể xuất hiện trực tiếp làm kiểu component:

~~~java
record Result<T>(boolean successful, T data, String message) {}

Result<String> textResult =
    new Result<>(true, "Completed", "Request succeeded");

Result<Long> idResult =
    new Result<>(true, 9001L, "Created");
~~~

Trong ví dụ này, **successful** và **message** có kiểu cố định; **data** thay đổi theo tham số kiểu **T**.

Có thể dùng type parameter nhiều lần trong header để thể hiện quan hệ kiểu giữa các component:

~~~java
record SameTypePair<T>(T first, T second) {}

SameTypePair<String> names =
    new SameTypePair<>("An", "Binh");
~~~

Hai component **first** và **second** phải cùng kiểu **T** trong một lần sử dụng. Nếu cần hai component độc lập về kiểu, khai báo hai tham số kiểu như **Pair<L, R>**.

Type argument của generic Java phải là kiểu tham chiếu; không thể dùng primitive trực tiếp làm type argument. Ví dụ **Pair<int, long>** không hợp lệ. Hãy dùng wrapper tương ứng như **Pair<Integer, Long>**. Nếu cần tối ưu primitive và tránh boxing, có thể khai báo component primitive riêng trong record không generic hoặc kết hợp component primitive với component generic.

### Component có kiểu generic lồng nhau

Component không chỉ nhận trực tiếp **T**; nó còn có thể là một kiểu generic sử dụng **T**:

~~~java
import java.util.List;
import java.util.Map;

record Page<T>(List<T> items, int total) {}
record Lookup<T>(Map<String, T> values) {}

Page<String> page =
    new Page<>(List.of("record", "stream"), 2);

Lookup<Long> lookup =
    new Lookup<>(Map.of("customer-1", 100L));
~~~

Accessor trả về đúng kiểu đã khai báo: **Page<String>.items()** có kiểu **List<String>**, còn **Lookup<Long>.values()** có kiểu **Map<String, Long>**.

Kiểu component cũng có thể chứa wildcard:

~~~java
import java.util.List;

record ReadOnlyBatch<T>(List<? extends T> values) {}
record Sink<T>(List<? super T> values) {}
~~~

- **List<? extends T>** cho phép đọc các phần tử như **T** hoặc một subtype của **T**.
- **List<? super T>** biểu diễn danh sách có kiểu phần tử là **T** hoặc một supertype của **T**; nó thường hữu ích cho vị trí nhận/ghi giá trị.

Wildcard nằm trong một kiểu tham số hóa. Không thể dùng wildcard như một kiểu độc lập cho component; khai báo **record Invalid(? value) {}** là sai cú pháp.

## 4. Truyền kiểu và suy luận kiểu khi tạo generic record

Khi tạo một instance generic record, có thể ghi rõ kiểu tham số:

~~~java
record Box<T>(T value) {}

Box<String> text = new Box<String>("Java");
Box<Integer> number = new Box<Integer>(16);
~~~

Nếu kiểu đích hoặc đối số cung cấp đủ thông tin, có thể dùng diamond operator **<>** để compiler suy luận kiểu:

~~~java
Box<String> text = new Box<>("Java");
Box<Integer> number = new Box<>(16);

var dateBox = new Box<>(java.time.LocalDate.now());
~~~

Với khai báo **Box<String> text**, compiler suy luận **T** là **String**. Với **var dateBox**, compiler suy luận kiểu biến từ biểu thức tạo đối tượng, nên kiểu của biến là **Box<LocalDate>**.

Có thể truyền kiểu tường minh ở một biểu thức khi muốn làm rõ ý định:

~~~java
var result = new Pair<String, Integer>("OK", 200);
~~~

Diamond operator không làm mất kiểm tra kiểu. Nếu kiểu đối số không tương thích với kiểu đích, compiler vẫn báo lỗi.

### Generic invariant và chuyển đổi kiểu

Generic trong Java là invariant. Ví dụ **Box<Integer>** không phải subtype của **Box<Number>**, dù **Integer** là subtype của **Number**.

~~~java
record Box<T>(T value) {}

Box<Integer> integerBox = new Box<>(10);

// Không hợp lệ: Box<Integer> không phải Box<Number>.
// Box<Number> numberBox = integerBox;
~~~

Nếu muốn nhận nhiều kiểu con, có thể dùng wildcard ở vị trí tham số:

~~~java
static void printNumber(Box<? extends Number> box) {
    Number value = box.value();
    System.out.println(value);
}
~~~

**Box<? extends Number>** có thể nhận **Box<Integer>**, **Box<Double>** và các Box có **T** là subtype của **Number**. Wildcard này thuộc kiểu tham số của biến/phương thức; nó không thay đổi khai báo generic record gốc.

## 5. Ràng buộc kiểu với extends

Không phải component generic nào cũng nên nhận mọi kiểu. Có thể giới hạn type parameter bằng **extends** để yêu cầu kiểu truyền vào phải thỏa mãn một hợp đồng.

Ví dụ chỉ nhận kiểu con của **Number**:

~~~java
record NumericValue<T extends Number>(T value) {}

NumericValue<Integer> integer = new NumericValue<>(42);
NumericValue<Double> decimal = new NumericValue<>(3.14);

// Không hợp lệ: String không extends Number.
// NumericValue<String> text = new NumericValue<>("42");
~~~

**T extends Number** cho phép **Number** và các subtype của **Number**, như **Integer**, **Long**, **Double** và **BigDecimal**. Nó không cho phép **String**.

Sau khi có bound, code có thể gọi những phương thức được khai báo trong bound:

~~~java
record NumericValue<T extends Number>(T value) {
    double asDouble() {
        return value.doubleValue();
    }
}
~~~

Compiler biết mọi **T** đều là **Number** hoặc subtype nên lời gọi **doubleValue()** hợp lệ.

Lưu ý: bound kiểm tra quan hệ kiểu lúc biên dịch. Nó không tự kiểm tra giá trị nghiệp vụ, chẳng hạn số âm, null hoặc giới hạn độ lớn. Những điều kiện đó cần được xác thực trong constructor.

## 6. Nhiều type bounds và intersection type

Một type parameter có thể bị giới hạn bởi nhiều bound. Cú pháp dùng dấu **&**:

~~~java
record SortedValue<T extends Number & Comparable<T>>(T value) {}
~~~

Trong ví dụ này, **T** phải vừa là subtype của **Number**, vừa triển khai **Comparable<T>**. Nhờ vậy, có thể gọi cả phương thức của **Number** và **Comparable<T>**:

~~~java
record SortedValue<T extends Number & Comparable<T>>(T value) {
    boolean isGreaterThan(T other) {
        return value.compareTo(other) > 0;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
~~~

Khi có nhiều bound:

- Nếu có class bound, nó phải đứng đầu.
- Các interface bound đứng sau, phân cách bằng **&**.
- Một kiểu truyền vào phải thỏa mãn tất cả bound.

Ví dụ với class và hai interface:

~~~java
record AuditedNumber<T extends Number
        & Comparable<T>
        & java.io.Serializable>(T value) {}
~~~

Trong khai báo trên, **Number** là class bound, còn **Comparable<T>** và **Serializable** là interface bound. Thứ tự class trước interface là quy tắc của cú pháp bound.

Không thể viết hai class bound độc lập trong cùng một danh sách bound. Java chỉ cho phép một class cha trực tiếp; các hợp đồng bổ sung nên được thể hiện bằng interface.

## 7. Recursive bound: giới hạn tham chiếu chính type parameter

Một kiểu bound phổ biến khác là *recursive type bound*, trong đó type parameter xuất hiện bên trong bound của chính nó:

~~~java
record ComparableValue<T extends Comparable<T>>(T value) {}
~~~

Điều này yêu cầu **T** có thể so sánh với một giá trị cùng kiểu **T**. Ví dụ:

~~~java
ComparableValue<String> text = new ComparableValue<>("Java");
ComparableValue<Integer> number = new ComparableValue<>(16);
~~~

**String** và **Integer** đều triển khai **Comparable** với kiểu tham số tương ứng.

Có thể dùng bound này để viết hành vi so sánh:

~~~java
record OrderedPair<T extends Comparable<T>>(T first, T second) {
    boolean isOrdered() {
        return first.compareTo(second) <= 0;
    }
}
~~~

Recursive bound thường xuất hiện trong API tổng quát cần so sánh, sắp xếp hoặc kết hợp giá trị cùng kiểu. Không nên thêm bound chỉ vì có thể; bound cần phản ánh hợp đồng mà logic của record thật sự sử dụng.

## 8. Generic record triển khai generic interface

Record generic có thể triển khai interface generic giống class thông thường.

~~~java
interface ValueProvider<T> {
    T value();
}

record ConstantValue<T>(T value) implements ValueProvider<T> {}
~~~

Accessor **value()** do record cung cấp đáp ứng phương thức **value()** của **ValueProvider<T>**. Không cần viết lại phương thức nếu chữ ký đã khớp.

Có thể cố định kiểu khi triển khai interface:

~~~java
interface Identifier {
    String id();
}

record CustomerId(String id) implements Identifier {}
~~~

Hoặc triển khai interface với một tham số kiểu khác:

~~~java
interface Mapper<S, R> {
    R map(S source);
}

record MappingRule<S, R>(String name) implements Mapper<S, R> {
    @Override
    public R map(S source) {
        throw new UnsupportedOperationException("Implement mapping policy");
    }
}
~~~

Trong ví dụ cuối, **MappingRule<S, R>** giữ hai tham số kiểu cho hợp đồng mapper. Phương thức **map** phải được triển khai vì record không tự suy ra hành vi chuyển đổi chỉ từ component.

## 9. Constructor và static method trong generic record

Canonical constructor của generic record sử dụng chính các type parameter của record. Không khai báo lại một bộ type parameter khác cho canonical constructor.

~~~java
import java.util.Objects;

record NonNullBox<T>(T value) {
    NonNullBox {
        value = Objects.requireNonNull(value, "value");
    }
}
~~~

Compact canonical constructor nhận giá trị **T** và có thể xác thực hoặc chuẩn hóa dữ liệu. Nếu viết canonical constructor đầy đủ, tham số phải tương ứng với component và field phải được gán theo quy tắc record.

Có thể khai báo constructor phụ, miễn constructor đó ủy quyền đến constructor khác của cùng record bằng **this(...)**:

~~~java
record Result<T>(T value, boolean successful) {
    Result(T value) {
        this(value, true);
    }
}
~~~

Một static method không thể dùng trực tiếp type parameter **T** của instance generic record vì static context không gắn với một lần tham số hóa cụ thể. Nếu static method cần kiểu tổng quát, khai báo type parameter riêng:

~~~java
record Box<T>(T value) {
    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}

Box<String> text = Box.of("Java");
Box<Long> id = Box.of(100L);
~~~

**U** là type parameter của phương thức static; nó độc lập với **T** của record. Cách viết này tạo factory method tổng quát, vẫn suy luận được kiểu khi gọi.

## 10. Type erasure và giới hạn ở runtime

Java triển khai generic bằng *type erasure*. Phần lớn thông tin type parameter được dùng để kiểm tra kiểu lúc biên dịch và bị xóa/biến đổi theo quy tắc erasure trong bytecode. Vì vậy, không thể kiểm tra trực tiếp kiểu tham số hóa cụ thể bằng **instanceof** như thể mỗi lần tham số hóa là một class runtime riêng.

Ví dụ:

~~~java
record Box<T>(T value) {}

Object value = new Box<String>("Java");

if (value instanceof Box<?> box) {
    System.out.println(box.value());
}
~~~

**Box<?>** là kiểu reifiable phù hợp cho kiểm tra runtime: ta biết object là một **Box**, nhưng không khẳng định được type argument là **String**.

Kiểm tra sau không hợp lệ:

~~~java
// Không hợp lệ: không thể kiểm tra parameterized type cụ thể sau erasure.
// if (value instanceof Box<String> box) { }
~~~

Nếu ứng dụng cần biết kiểu dữ liệu cụ thể ở runtime, hãy truyền thêm **Class<T>**, metadata hoặc dùng một schema rõ ràng. Không giả định type parameter vẫn tồn tại như một class riêng cho mỗi cách tham số hóa.

### Tránh raw type

Không dùng generic record dưới dạng raw type nếu có thể tránh:

~~~java
record Box<T>(T value) {}

Box raw = new Box("Java"); // Raw type: mất kiểm tra kiểu.
Box<String> typed = new Box<>("Java");
~~~

Raw type bỏ qua lợi ích kiểm tra kiểu của generic, thường tạo compiler warning và có thể dẫn đến **ClassCastException** ở nơi sử dụng. Hãy khai báo tham số kiểu cụ thể hoặc wildcard khi chưa biết kiểu chính xác:

- **Box<String>** khi biết component là String.
- **Box<?>** khi chỉ cần nhận bất kỳ Box nào và không cần ghi giá trị theo một kiểu cụ thể.
- **Box<? extends Number>** khi cần đọc các giá trị có kiểu con của Number.

## 11. Ví dụ hoàn chỉnh: kết quả API generic có giới hạn kiểu

Ví dụ sau kết hợp generic record, bound, compact constructor và factory method. Lưu vào tệp **Demo.java**:

~~~java
import java.util.Objects;

public class Demo {
    record ApiResult<T>(T data, String message, boolean successful) {
        ApiResult {
            message = Objects.requireNonNull(message, "message").strip();
            if (successful && data == null) {
                throw new IllegalArgumentException(
                    "Successful result requires data"
                );
            }
        }

        static <U> ApiResult<U> success(U data) {
            return new ApiResult<>(Objects.requireNonNull(data), "OK", true);
        }

        static <U> ApiResult<U> failure(String message) {
            return new ApiResult<>(null, message, false);
        }
    }

    record Metric<T extends Number & Comparable<T>>(String name, T value) {
        Metric {
            name = Objects.requireNonNull(name, "name").strip();
            Objects.requireNonNull(value, "value");
            if (name.isEmpty()) {
                throw new IllegalArgumentException("name is required");
            }
        }

        double asDouble() {
            return value.doubleValue();
        }

        boolean exceeds(T threshold) {
            return value.compareTo(threshold) > 0;
        }
    }

    public static void main(String[] args) {
        ApiResult<String> saved = ApiResult.success("customer-100");
        ApiResult<String> failed = ApiResult.failure("Customer not found");

        System.out.println(saved.data());        // customer-100
        System.out.println(saved.message());     // OK
        System.out.println(failed.successful()); // false

        Metric<Integer> activeUsers = new Metric<>("active-users", 120);
        System.out.println(activeUsers.asDouble()); // 120.0
        System.out.println(activeUsers.exceeds(100)); // true
    }
}
~~~

Biên dịch và chạy bằng JDK 16 trở lên:

~~~bash
javac --release 16 Demo.java
java Demo
~~~

Điểm cần quan sát:

1. **ApiResult<T>** tái sử dụng một cấu trúc kết quả cho nhiều kiểu dữ liệu.
2. Static factory method **<U>** khai báo type parameter riêng, không sử dụng trực tiếp **T** của instance.
3. **Metric<T extends Number & Comparable<T>>** yêu cầu kiểu vừa là Number vừa so sánh được với cùng kiểu.
4. Compact constructor xác thực giá trị và chuẩn hóa tên metric; bound không thay thế việc kiểm tra dữ liệu nghiệp vụ.
5. Accessor của mỗi component giữ kiểu cụ thể: **ApiResult<String>.data()** là **String**, **Metric<Integer>.value()** là **Integer**.

## 12. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Viết **record Box<T value> {}** | Thiếu dấu ngoặc header và cú pháp component. | Viết **record Box<T>(T value) {}**. |
| Đặt type parameter sau record header | Sai vị trí khai báo tham số kiểu. | Đặt **<T>** sau tên record, trước **(...)**. |
| Truyền String vào **NumericValue<T extends Number>** | String không thỏa mãn bound Number. | Chọn kiểu con của Number hoặc bỏ bound nếu nghiệp vụ cho phép. |
| Gán **Box<Integer>** cho **Box<Number>** | Generic invariant. | Dùng wildcard phù hợp như **Box<? extends Number>**. |
| Dùng **instanceof Box<String>** | Type argument không reifiable sau erasure. | Dùng **instanceof Box<?>** và metadata nếu cần kiểm tra sâu hơn. |
| Dùng raw type **Box** | Bỏ qua kiểm tra kiểu generic. | Dùng **Box<T>**, **Box<?>** hoặc kiểu tham số hóa cụ thể. |
| Dùng **T** trong static method mà không khai báo type parameter | Static context không có **T** của instance. | Khai báo method generic, ví dụ **static <U> Box<U> of(U value)**. |
| Nghĩ bound tự xác thực dữ liệu runtime | Bound chỉ kiểm tra quan hệ kiểu lúc biên dịch. | Dùng constructor để kiểm tra null, khoảng giá trị và invariant nghiệp vụ. |

## 13. Bài tập thực hành

1. Khai báo **record Pair<L, R>(L left, R right)**. Tạo **Pair<String, Long>** và đọc hai component.
2. Viết **record Box<T>(T value)** có static factory method **of(U value)** với type parameter riêng của phương thức.
3. Khai báo **record NumericBox<T extends Number>(T value)** và viết phương thức trả về **doubleValue()**.
4. Mở rộng bound thành **T extends Number & Comparable<T>**. Giải thích vì sao **Integer** hợp lệ và **String** không hợp lệ.
5. Khai báo **record Page<T>(List<T> items, int total)**. Tạo một page chứa String và một page chứa Integer.
6. Viết phương thức nhận **Box<? extends Number>** và đọc component như **Number**.
7. Giải thích vì sao **instanceof Box<?>** hợp lệ nhưng **instanceof Box<String>** không hợp lệ.
8. Thêm compact constructor cho một generic record để từ chối component null và giải thích vì sao bound không thay thế kiểm tra này.

## Ghi nhớ

Generic record đặt type parameter sau tên record và trước record header, ví dụ **record Box<T>(T value) {}**. Component có thể dùng trực tiếp **T**, nhiều type parameter, kiểu generic lồng nhau hoặc wildcard trong một kiểu tham số hóa. Dùng **extends** để giới hạn kiểu; nhiều bound dùng **&**, với class bound đứng trước interface bounds; recursive bound phù hợp khi cần một kiểu so sánh được với chính nó. Diamond operator hỗ trợ suy luận kiểu, còn static factory method cần khai báo type parameter riêng. Generic vẫn chịu type erasure: dùng **Box<?>** khi kiểm tra record tổng quát ở runtime, tránh raw type và không giả định có thể kiểm tra **Box<String>** bằng **instanceof**. Các quy tắc này là phần ổn định của Java generic và record, tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Type Parameters, mục 4.4](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.4)
- [Java Language Specification – Type Erasure, mục 4.6](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.6)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
