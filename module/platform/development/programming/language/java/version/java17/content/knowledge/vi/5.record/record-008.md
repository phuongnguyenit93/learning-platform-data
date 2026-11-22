# Record có kiểu tổng quát và triển khai interface trong Java 17

**Chủ đề:** Java 17 → Record  
**Nội dung:** Khai báo record với tham số kiểu tổng quát (*generic record*), sử dụng ràng buộc kiểu (*type bounds*), và cho record triển khai một hoặc nhiều interface, kể cả generic interface.

Trong Java 17, **record** là một loại khai báo lớp dành cho các đối tượng chủ yếu dùng để mang dữ liệu. Một record có thể có **tham số kiểu** như `<T>` hoặc `<K, V>`, giống lớp Java thông thường, và có thể **`implements` interface** để tham gia các hợp đồng xử lý chung. Record là tính năng chính thức từ Java 16, vì vậy mọi ví dụ trong bài đều sử dụng cú pháp **ổn định trên Java 17**, không cần `--enable-preview` hay thư viện ngoài JDK.

## 1. Ôn nhanh: record tạo ra những gì?

Xét record đơn giản:

~~~java
record Book(String title, int pages) {
}
~~~

Khai báo này định nghĩa hai **record component** là `title` và `pages`. Trình biên dịch cung cấp các thành phần tương ứng:

- Các trường lưu dữ liệu tương ứng với component, có tính chất `private final`.
- Constructor chính (*canonical constructor*) nhận giá trị của các component theo thứ tự khai báo.
- Các phương thức truy cập `title()` và `pages()`. Record không tự tạo getter theo mẫu `getTitle()`.
- Các phương thức `equals(Object)`, `hashCode()`, `toString()` theo ngữ nghĩa dữ liệu của record, trừ khi được khai báo lại hợp lệ.

Ví dụ:

~~~java
Book book = new Book("Java 17", 320);
System.out.println(book.title()); // Java 17
System.out.println(book.pages()); // 320
System.out.println(book);         // Book[title=Java 17, pages=320]
~~~

Record **không cho phép một lớp khác kế thừa nó** vì record có tính chất `final` ngầm định. Bản thân record luôn kế thừa `java.lang.Record`, nên không thể tự `extends` một lớp cha khác. Tuy vậy, record **được phép triển khai interface** và có thể khai báo phương thức, constructor, trường `static` hoặc phương thức `static` như quy tắc Java cho phép.

## 2. Cú pháp generic record: `record Name<T>(...)`

Generic record đặt danh sách tham số kiểu **ngay sau tên record**:

~~~java
record Box<T>(T value) {
}

record Pair<K, V>(K key, V value) {
}
~~~

Trong đó:

| Thành phần | Vai trò |
| --- | --- |
| `record` | Khai báo một record. |
| `Box<T>` | `T` là tham số kiểu; giá trị cụ thể được xác định khi sử dụng. |
| `T value` | Component `value` có kiểu `T`. |
| `Pair<K, V>` | Record có hai tham số kiểu độc lập, thường dùng cho cặp khóa–giá trị. |
| `key()`, `value()` | Các accessor do record tạo ra, trả đúng kiểu đã khai báo của component theo thông tin kiểu lúc biên dịch. |

### 2.1. Ví dụ chạy được: một record dùng cho nhiều kiểu dữ liệu

Tạo tệp **`GenericRecordDemo.java`**:

~~~java
import java.util.Objects;

public class GenericRecordDemo {
    record Box<T>(T value) {
        Box {
            Objects.requireNonNull(value, "value");
        }
    }

    record Pair<K, V>(K key, V value) {
    }

    public static void main(String[] args) {
        Box<String> title = new Box<>("Java 17");
        Box<Integer> count = new Box<>(17);
        Pair<String, Integer> course = new Pair<>("Số bài", 8);

        String text = title.value();
        int number = count.value();

        System.out.println(text);
        System.out.println(number);
        System.out.println(course.key() + ": " + course.value());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17**:

~~~shell
javac --release 17 GenericRecordDemo.java
java GenericRecordDemo
~~~

Kết quả:

~~~text
Java 17
17
Số bài: 8
~~~

**Giải thích:**

1. `Box<String>` chứa `String`; `title.value()` có kiểu `String` tại thời điểm biên dịch.
2. `Box<Integer>` chứa `Integer`; lời gán `int number = count.value()` hoạt động nhờ **unboxing** từ `Integer` sang `int`.
3. `new Box<>(...)` dùng toán tử kim cương `<>` để Java suy luận đối số kiểu từ ngữ cảnh và tham số constructor.
4. `Pair<String, Integer>` có hai component với hai kiểu độc lập.
5. Khối `Box { ... }` là **compact canonical constructor**; nó kiểm tra tham số `value` trước khi Java tự gán tham số vào trường component tương ứng.

Không thể dùng kiểu nguyên thủy làm type argument, ví dụ `Box<int>` là cú pháp không hợp lệ. Hãy dùng kiểu bao như `Integer`, `Long` hoặc `Double`.

### 2.2. Khai báo phương thức generic trong record

Một record generic cũng có thể cung cấp phương thức tiện ích để tạo đối tượng:

~~~java
record Box<T>(T value) {
    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

Sử dụng:

~~~java
Box<String> a = Box.of("Hello");
Box<Integer> b = Box.of(42);
~~~

`T` là tham số kiểu của **bản thân record**; `U` là tham số kiểu độc lập của **phương thức static** `of`. Phương thức static không thể sử dụng trực tiếp `T` của một thể hiện record vì không có thể hiện nào gắn với lời gọi static.

## 3. Ràng buộc tham số kiểu của record

Cũng như generic class, generic record có thể giới hạn những kiểu được phép truyền vào:

~~~java
record Measurement<T extends Number>(T amount, String unit) {
}
~~~

`T extends Number` nói rằng `T` phải là `Number` hoặc một kiểu con hợp lệ của `Number`, ví dụ `Integer`, `Long`, `Double` hoặc `BigDecimal`.

~~~java
Measurement<Integer> steps = new Measurement<>(1200, "steps");
Measurement<Double> distance = new Measurement<>(2.5, "km");

double total = steps.amount().doubleValue();
System.out.println(total); // 1200.0
~~~

Ngược lại, `Measurement<String>` không hợp lệ vì `String` không phải subtype của `Number`. Kiểm tra này diễn ra **khi biên dịch**.

Một giới hạn tổng quát hơn thường được dùng cho dữ liệu có thể so sánh:

~~~java
record Ranked<T extends Comparable<? super T>>(T value) {
    int compareTo(Ranked<T> other) {
        return value.compareTo(other.value());
    }
}
~~~

Cú pháp `Comparable<? super T>` cho phép `T` được so sánh bởi một `Comparable` chấp nhận `T` hoặc một kiểu cha của nó. Điều này thường linh hoạt hơn `Comparable<T>` thuần túy. Ràng buộc kiểu giúp bảo đảm việc gọi `compareTo` hợp lệ ngay tại thời điểm biên dịch.

### 3.1. Generic không làm mất kiểm tra kiểu

Các khai báo sau là **khác kiểu generic**:

~~~java
Box<Integer> integerBox = new Box<>(10);
Box<Number> numberBox = new Box<>(10);
~~~

Mặc dù `Integer` là subtype của `Number`, **`Box<Integer>` không phải subtype của `Box<Number>`**. Generic Java có tính **bất biến theo type argument** (*invariance*).

Vì vậy, câu lệnh sau không hợp lệ:

~~~java
// Sai: Box<Integer> không thể gán vào Box<Number>.
// Box<Number> other = integerBox;
~~~

Nếu phương thức chỉ cần **đọc** số từ một Box, có thể dùng wildcard:

~~~java
static double readNumber(Box<? extends Number> box) {
    return box.value().doubleValue();
}
~~~

Phương thức chấp nhận `Box<Integer>`, `Box<Double>` và những Box có kiểu đối số kế thừa `Number`.

## 4. Record triển khai interface như thế nào?

Một record có thể viết `implements InterfaceName` sau danh sách component:

~~~java
interface Named {
    String name();
}

record User(String name, int age) implements Named {
}
~~~

Mặc dù record `User` không tự khai báo phương thức `name()` trong thân, **accessor `name()` được sinh từ component `String name` đã đáp ứng hợp đồng `Named.name()`**. Vì chữ ký và kiểu trả về tương thích, không cần viết lại phương thức chỉ để trả về component.

Một đối tượng `User` có thể được dùng thông qua kiểu interface:

~~~java
Named named = new User("Lan", 25);
System.out.println(named.name()); // Lan
~~~

Đây là **tính đa hình**: mã sử dụng quan tâm đối tượng đáp ứng `Named`, chứ không bắt buộc phải biết đó là `User` record.

### 4.1. Ví dụ hoàn chỉnh: record generic triển khai generic interface

Tạo tệp **`GenericInterfaceDemo.java`**:

~~~java
import java.util.Objects;

public class GenericInterfaceDemo {
    interface Identifiable<ID> {
        ID id();
    }

    record Entity<ID, T>(ID id, T payload)
            implements Identifiable<ID> {

        Entity {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(payload, "payload");
        }
    }

    static <ID> void printId(Identifiable<ID> item) {
        System.out.println("ID: " + item.id());
    }

    public static void main(String[] args) {
        Entity<Long, String> first = new Entity<>(1001L, "Khóa học Java");
        Entity<String, Integer> second = new Entity<>("LESSON-1", 25);

        printId(first);
        printId(second);

        System.out.println(first.payload());
        System.out.println(second.payload());
    }
}
~~~

Chạy:

~~~shell
javac --release 17 GenericInterfaceDemo.java
java GenericInterfaceDemo
~~~

Kết quả:

~~~text
ID: 1001
ID: LESSON-1
Khóa học Java
25
~~~

**Tách từng phần khai báo:**

~~~java
record Entity<ID, T>(ID id, T payload) implements Identifiable<ID>
~~~

- `ID`: kiểu của định danh, ví dụ `Long` hoặc `String`.
- `T`: kiểu nội dung, độc lập với kiểu định danh.
- `implements Identifiable<ID>`: cam kết record cung cấp phương thức `ID id()`.
- Component `ID id` khiến trình biên dịch tạo accessor `id()` tương thích; không cần tự viết lại.
- Phương thức `printId` nhận mọi đối tượng triển khai `Identifiable<ID>`, bao gồm cả record.

Đối với generic interface, các type argument phải tương thích. Ví dụ `Entity<Long, String>` triển khai `Identifiable<Long>`, không phải `Identifiable<String>`.

## 5. Khi accessor không khớp tên phương thức của interface

Record chỉ sinh accessor theo **đúng tên component**. Nếu interface yêu cầu tên phương thức khác, record phải tự cài đặt:

~~~java
interface DisplayName {
    String getDisplayName();
}

record Person(String name) implements DisplayName {
    @Override
    public String getDisplayName() {
        return name();
    }
}
~~~

Ở đây, component `name` tạo ra `name()`; nó **không tự tạo** `getDisplayName()`. Vì vậy, phương thức ghi đè `getDisplayName()` là cần thiết.

Nếu interface yêu cầu `String name()` thì record `Person(String name)` có thể đáp ứng trực tiếp. Ngược lại, nếu component là `Object name`, accessor trả về `Object` và không thể đáp ứng phương thức yêu cầu trả về `String`.

| Interface yêu cầu | Component của record | Kết quả |
| --- | --- | --- |
| `String name()` | `String name` | Accessor sinh tự động phù hợp. |
| `Number amount()` | `Integer amount` | Kiểu trả về covariant `Integer` có thể đáp ứng `Number`. |
| `String getName()` | `String name` | Cần tự viết `getName()`. |
| `String name()` | `Object name` | Accessor tự sinh không có kiểu trả về phù hợp. |

Các phương thức của interface có thể là `default`, `static` hoặc `private` theo quy tắc của interface Java. Khi record triển khai interface, nó có thể kế thừa phương thức `default` phù hợp hoặc tự ghi đè hành vi. Quy tắc override vẫn giống các lớp Java khác.

## 6. Record có thể triển khai nhiều interface

Record không kế thừa lớp cha tùy ý, nhưng có thể triển khai **nhiều interface**:

~~~java
interface HasValue<T> {
    T value();
}

interface Describable {
    String description();
}

record Product<T>(String code, T value)
        implements HasValue<T>, Describable {

    @Override
    public String description() {
        return code() + " = " + value();
    }
}
~~~

Sử dụng:

~~~java
Product<Integer> product = new Product<>("SKU-15", 150);

HasValue<Integer> valueView = product;
Describable descriptionView = product;

System.out.println(valueView.value());          // 150
System.out.println(descriptionView.description()); // SKU-15 = 150
~~~

**Điều gì được tạo tự động, điều gì phải tự viết?**

| Thành phần | Có sẵn nhờ record? | Ghi chú |
| --- | --- | --- |
| `code()` và `value()` | Có | Accessor của hai component. |
| `HasValue<T>.value()` | Được đáp ứng bởi `value()` | Không cần phương thức `value` thứ hai. |
| `Describable.description()` | Không | Phải tự viết nếu interface không cung cấp default implementation. |
| `equals`, `hashCode`, `toString` | Có | Sinh theo component. |
| `setValue(...)` | Không | Record không cung cấp setter và không cho gán lại component field. |

Cách thiết kế này hữu ích khi cần truyền cùng một đối tượng qua nhiều API: API đọc giá trị chỉ cần `HasValue<T>`, còn API hiển thị chỉ cần `Describable`.

## 7. Bổ sung hành vi và ràng buộc dữ liệu cho generic record

Record không chỉ là một dòng khai báo ngắn. Nó có thể chứa logic xác thực và phương thức nghiệp vụ, miễn là tuân thủ quy tắc của record.

Ví dụ **`ValidatedRecordDemo.java`**:

~~~java
import java.util.Objects;

public class ValidatedRecordDemo {
    interface HasCode {
        String code();
    }

    record CatalogItem<T>(String code, T details)
            implements HasCode {

        CatalogItem {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(details, "details");

            code = code.trim();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("Code must not be blank");
            }
        }

        String display() {
            return code() + ": " + details();
        }
    }

    public static void main(String[] args) {
        CatalogItem<Integer> item =
            new CatalogItem<>("  ITEM-9  ", 120);

        HasCode contract = item;
        System.out.println(contract.code());
        System.out.println(item.display());
    }
}
~~~

~~~shell
javac --release 17 ValidatedRecordDemo.java
java ValidatedRecordDemo
~~~

Kết quả:

~~~text
ITEM-9
ITEM-9: 120
~~~

Trong compact constructor `CatalogItem { ... }`, ta có thể kiểm tra và **gán lại tham số** `code` để chuẩn hóa dữ liệu trước khi trường component được khởi tạo ngầm. Không được gán trực tiếp vào trường component kiểu `this.code = ...` trong compact constructor. Với canonical constructor đầy đủ, việc gán trường tuân theo những quy tắc riêng của constructor đó.

`HasCode.code()` được đáp ứng từ accessor `code()` do record sinh. Phương thức `display()` do tác giả khai báo bổ sung hành vi hiển thị, không can thiệp vào khả năng sử dụng record qua interface.

## 8. Record generic, collection và tính bất biến nông

Một nhầm lẫn thường gặp là: “record có các trường `final` nên toàn bộ nội dung của nó bất biến”. Thực tế, record bảo đảm **không gán lại tham chiếu của component sau khi tạo**, nhưng **đối tượng được tham chiếu vẫn có thể thay đổi**.

Xét:

~~~java
import java.util.List;

record Group<T>(List<T> members) {
}
~~~

Nếu truyền một `ArrayList` có thể sửa vào `Group`, một phần mã khác có thể thay đổi danh sách đó; `Group.members()` cũng trả về cùng tham chiếu. Đây là **bất biến nông** (*shallow immutability*), không phải bất biến sâu.

Khi thiết kế record mang collection và muốn ngăn thay đổi cấu trúc collection thông qua tham chiếu bên ngoài, hãy sao chép phòng vệ:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

record Batch<T>(List<T> items) implements Iterable<T> {
    Batch {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
    }

    @Override
    public Iterator<T> iterator() {
        return items.iterator();
    }
}
~~~

Sử dụng:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
Batch<String> batch = new Batch<>(source);

source.add("C");
System.out.println(batch.items()); // [A, B]

for (String value : batch) {
    System.out.println(value);
}

// batch.items().add("D"); // Ném UnsupportedOperationException.
~~~

Giải thích hai cơ chế phối hợp:

1. `List.copyOf(...)` tạo ra một danh sách không thể sửa trực tiếp, với snapshot của phần tử tại thời điểm copy (hoặc có thể tận dụng danh sách không thể sửa đã có).
2. `Iterable<T>` cho phép `Batch<T>` được dùng trong vòng `for-each`; record phải tự viết `iterator()` vì tên này không phải accessor của component.

`List.copyOf` không chấp nhận phần tử `null`. Cần xác định chính sách dữ liệu từ đầu nếu đầu vào có thể chứa `null`.

**Giới hạn:** `List.copyOf` không sao chép sâu từng đối tượng `T`. Nếu `T` là kiểu có thể thay đổi, nội dung bên trong phần tử vẫn có thể thay đổi. Để đạt bất biến sâu, còn cần quy tắc phù hợp cho kiểu phần tử.

## 9. Generic record và type erasure

Java generics dùng cơ chế **type erasure**. Khi chạy, không có một class riêng cho `Box<String>` và một class khác cho `Box<Integer>`; cả hai đều dùng class `Box` tương ứng.

Ví dụ:

~~~java
Box<String> text = new Box<>("Java");
Box<Integer> number = new Box<>(17);

System.out.println(text.getClass() == number.getClass()); // true
~~~

Vì vậy, không thể kiểm tra đối số kiểu cụ thể `String` bằng một biểu thức `instanceof Box<String>`:

~~~java
Object value = new Box<>("Java");

// Sai: không thể kiểm tra đối số kiểu String theo cách này.
// if (value instanceof Box<String> box) { ... }
~~~

Tuy nhiên, có thể nhận diện loại record với wildcard:

~~~java
if (value instanceof Box<?> box) {
    System.out.println(box.value());
}
~~~

Đây là **pattern matching for `instanceof`**, đã chính thức và dùng được trong Java 17. Thao tác so khớp kiểm tra đối tượng là `Box`, không khôi phục được type argument cụ thể vốn đã bị xóa tại runtime.

**Tác động khi thiết kế:** Đừng dùng `T` như thể runtime luôn biết lớp cụ thể của nó. Nếu cần metadata về loại dữ liệu lúc chạy, hãy thiết kế rõ ràng, chẳng hạn truyền thêm `Class<T>` hoặc một bộ chuyển đổi có khả năng xử lý kiểu tương ứng.

## 10. Kết hợp generic record với sealed interface

Một ứng dụng có thể dùng generic interface để biểu diễn kết quả với dữ liệu kiểu `T`, đồng thời giới hạn trực tiếp các biến thể bằng `sealed`. Cả **record** và **sealed interface** đều là tính năng chính thức trong Java 17.

Tạo tệp **`ResultRecordDemo.java`**:

~~~java
public class ResultRecordDemo {
    sealed interface Result<T> permits Success, Failure {
    }

    record Success<T>(T value) implements Result<T> {
    }

    record Failure<T>(String reason) implements Result<T> {
    }

    static <T> String describe(Result<T> result) {
        if (result instanceof Success<?> success) {
            return "Thành công: " + success.value();
        }
        if (result instanceof Failure<?> failure) {
            return "Thất bại: " + failure.reason();
        }
        throw new IllegalStateException("Loại kết quả chưa được hỗ trợ");
    }

    public static void main(String[] args) {
        Result<String> first = new Success<>("Đã lưu");
        Result<String> second = new Failure<>("Không có quyền truy cập");

        System.out.println(describe(first));
        System.out.println(describe(second));
    }
}
~~~

~~~shell
javac --release 17 ResultRecordDemo.java
java ResultRecordDemo
~~~

Kết quả:

~~~text
Thành công: Đã lưu
Thất bại: Không có quyền truy cập
~~~

Trong ví dụ:

- `Result<T>` là generic sealed interface, chỉ cho phép hai kiểu con **trực tiếp** `Success` và `Failure`.
- `Success<T>` và `Failure<T>` là generic record trực tiếp `implements Result<T>`; record có tính chất `final` ngầm định, đáp ứng quy tắc của sealed hierarchy.
- `Failure<T>` vẫn có tham số kiểu `T` để một kết quả thất bại được dùng qua cùng hợp đồng `Result<T>`, dù component `reason` không cần mang kiểu `T`.
- Trong `instanceof`, dùng `Success<?>` và `Failure<?>` vì Java không thể kiểm tra đối số kiểu `T` cụ thể tại runtime.

Không dùng **pattern matching trong `switch`** ở đây: tính năng đó còn ở dạng preview trong Java 17. Các chuỗi `if`/`instanceof` trong ví dụ sử dụng cú pháp chính thức.

Mô hình này thích hợp khi muốn mô tả một tập kết quả có kiểm soát nhưng vẫn cho phép payload thành công có nhiều kiểu khác nhau.

## 11. Các lỗi thường gặp và cách tránh

### 11.1. Quên type argument hoặc dùng raw type

~~~java
record Box<T>(T value) {
}

// Raw type: biên dịch được trong một số ngữ cảnh,
// nhưng làm mất lợi ích kiểm tra kiểu và có thể tạo cảnh báo.
Box raw = new Box("text");

Box<String> typed = new Box<>("text"); // Nên dùng.
~~~

Trong mã mới, hãy khai báo type argument cụ thể hoặc dùng `var` khi kiểu được suy luận rõ ràng từ biểu thức. Tránh raw type vì có thể dẫn đến ép kiểu không an toàn.

### 11.2. Nhầm accessor với getter theo convention JavaBeans

~~~java
record Customer(String name) {
}

Customer customer = new Customer("Minh");
System.out.println(customer.name()); // Đúng

// customer.getName(); // Sai: record không tự tạo getName().
~~~

Nếu API của interface hoặc framework yêu cầu `getName()`, cần khai báo phương thức đó hoặc cấu hình bộ chuyển đổi phù hợp.

### 11.3. Cố gắng kế thừa record hoặc cho record kế thừa lớp thường

~~~java
record Point(int x, int y) {
}

// Sai: record là final, không thể extends Point.
// class ColoredPoint extends Point {}

// Sai: record đã kế thừa java.lang.Record.
// record SpecialPoint(int x, int y) extends Point {}
~~~

Để chia sẻ hành vi hoặc hợp đồng giữa nhiều record, sử dụng **interface**. Nếu cần hệ phân cấp lớp có trạng thái và logic kế thừa, hãy cân nhắc class thông thường.

### 11.4. Cho record triển khai interface nhưng chưa đáp ứng phương thức

~~~java
interface Printable {
    String print();
}

// Sai: component tên value chỉ tạo value(), không tạo print().
// record Note(String value) implements Printable {}

record Note(String value) implements Printable {
    @Override
    public String print() {
        return value();
    }
}
~~~

Record là class cụ thể nên phải đáp ứng những phương thức trừu tượng của interface bằng accessor tương thích, phương thức tự viết hoặc phương thức hiện thực được thừa kế theo quy tắc Java.

### 11.5. Tin rằng `final` đồng nghĩa dữ liệu bất biến sâu

~~~java
import java.util.List;

record Tasks(List<String> values) {
}
~~~

Danh sách có thể vẫn thay đổi nếu record giữ tham chiếu đến danh sách sửa được. Dùng sao chép phòng vệ và xác định cách xử lý phần tử thay đổi được khi thiết kế dữ liệu.

### 11.6. Sử dụng type erasure như thể có kiểm tra generic tại runtime

`new Box<>(42)` và `new Box<>("text")` cùng tạo đối tượng của lớp `Box`. Generic Java hỗ trợ kiểm tra kiểu lúc biên dịch; không nên dựa vào `instanceof Box<String>` để phân biệt payload. Dùng wildcard, kiểm tra giá trị cụ thể khi cần, hoặc một mô hình có metadata kiểu rõ ràng.

## 12. Khi nào nên kết hợp generic record và interface?

| Nhu cầu | Gợi ý thiết kế | Lợi ích |
| --- | --- | --- |
| Đóng gói một giá trị có kiểu tùy ý | `record Box<T>(T value)` | Giữ kiểu cụ thể, giảm ép kiểu thủ công. |
| Biểu diễn một cặp giá trị nhiều kiểu | `record Pair<K, V>(K key, V value)` | Nhỏ gọn, accessor rõ ràng. |
| Nhiều loại đối tượng đều có định danh | `interface Identifiable<ID>`; record `implements Identifiable<ID>` | Consumer làm việc qua hợp đồng định danh. |
| Nhiều loại dữ liệu cùng được mô tả hoặc hiển thị | Record `implements Describable` | Gắn hành vi rõ ràng cho đối tượng dữ liệu. |
| Danh sách phần tử được cung cấp theo interface | `record Batch<T>(List<T> items) implements Iterable<T>` | Sử dụng được `for-each`, đồng thời định nghĩa chính sách bảo vệ collection. |
| Kết quả xử lý có nhiều biến thể, payload đa dạng | `sealed interface Result<T>` và các generic record triển khai | Giới hạn nhóm kết quả, giữ kiểm tra kiểu cho payload. |

Một generic record phù hợp khi cấu trúc dữ liệu có ngữ nghĩa ổn định và phần lớn hành vi của đối tượng đến từ các component. Nếu đối tượng cần vòng đời thay đổi liên tục, trạng thái nội bộ riêng, logic kế thừa lớp phức tạp hoặc quy trình cập nhật bằng setter, class thông thường có thể phù hợp hơn.

## 13. Bài luyện tập áp dụng

**Yêu cầu:** Xây dựng kiểu `Response<T>` mang dữ liệu `T` và mã HTTP; kiểu này phải triển khai `HasStatus` để mã bên ngoài đọc được trạng thái. Khi khởi tạo, mã trạng thái cần nằm trong khoảng từ 100 đến 599; dữ liệu không được `null`.

**Gợi ý lời giải:**

~~~java
import java.util.Objects;

public class ResponseDemo {
    interface HasStatus {
        int status();
    }

    record Response<T>(int status, T body) implements HasStatus {
        Response {
            if (status < 100 || status > 599) {
                throw new IllegalArgumentException("Invalid HTTP status");
            }
            Objects.requireNonNull(body, "body");
        }
    }

    static void showStatus(HasStatus value) {
        System.out.println("HTTP " + value.status());
    }

    public static void main(String[] args) {
        Response<String> text = new Response<>(200, "OK");
        Response<Integer> number = new Response<>(201, 123);

        showStatus(text);
        showStatus(number);
        System.out.println(text.body());
    }
}
~~~

~~~shell
javac --release 17 ResponseDemo.java
java ResponseDemo
~~~

Kết quả:

~~~text
HTTP 200
HTTP 201
OK
~~~

**Hãy tự giải thích:** Vì sao không cần viết lại `status()`? Vì sao `Response<String>` và `Response<Integer>` cùng truyền được vào `showStatus(HasStatus)`? Điều gì sẽ xảy ra nếu tạo `new Response<>(700, "invalid")` hoặc truyền `null` làm `body`?

Đáp án nằm ở ba quy tắc đã học: accessor `status()` của record đáp ứng interface, cả hai đối tượng đều triển khai `HasStatus`, và compact constructor từ chối dữ liệu không hợp lệ.

## 14. Ghi nhớ và tài liệu tham khảo

- **Generic record** dùng cú pháp `record Name<T>(T component)`, hỗ trợ nhiều tham số kiểu và ràng buộc kiểu như generic class.
- Record có thể **`implements` một hoặc nhiều interface** (kể cả generic interface), nhưng không thể `extends` lớp tùy ý vì luôn kế thừa `java.lang.Record` và có tính chất `final`.
- Accessor tạo từ component có thể **đáp ứng trực tiếp** một phương thức của interface nếu tên và kiểu trả về tương thích; những phương thức khác phải được cung cấp theo hợp đồng interface.
- `record` cung cấp ngữ nghĩa dữ liệu và các trường component `final`, nhưng **không bảo đảm bất biến sâu** cho collection hay đối tượng mutable được tham chiếu.
- Generic Java có **type erasure**. Type argument được kiểm tra lúc biên dịch; `instanceof Box<?>` hợp lệ nhưng `instanceof Box<String>` không phải cách kiểm tra runtime hợp lệ.
- Toàn bộ ví dụ dùng các tính năng chính thức của **Java 17** và không yêu cầu preview/incubator.

**Nguồn chính thức:**

1. [JEP 395 — Records](https://openjdk.org/jeps/395): đặc tả định hướng và việc đưa records thành tính năng chính thức.
2. [Java Language Specification 17 — Record Classes (§8.10)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): cấu trúc, component, constructor, generic record và các ràng buộc của record.
3. [Java Language Specification 17 — Type Parameters (§4.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): tham số kiểu và type bounds.
4. [Java Language Specification 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): hợp đồng phương thức và quy tắc triển khai interface.
5. [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): lớp cha nền tảng của mọi record.

Khi kết hợp generic record và interface, hãy thiết kế **dữ liệu record mang**, **kiểu dữ liệu được ràng buộc**, và **hợp đồng mà record cam kết thực hiện** thành ba quyết định rõ ràng. Cách đó giúp mã Java 17 ngắn gọn, an toàn kiểu và dễ mở rộng qua interface mà không phụ thuộc vào kế thừa lớp.
