# `toString()` để biểu diễn đối tượng khi quan sát chương trình trong Java

Trong Java, mỗi đối tượng đều có thể được **biểu diễn bằng văn bản** để người lập trình dễ quan sát trạng thái khi chạy chương trình, in ra console, kiểm tra trong debugger, ghi log hoặc đưa vào một thông báo chẩn đoán. Phương thức nền tảng cho việc đó là **`toString()`**, được khai báo trong lớp `java.lang.Object` và thường được **override** ở lớp của mình để tạo chuỗi có ý nghĩa.

Ví dụ thay vì quan sát:

```text
Student@5acf9800
```

ta thường muốn:

```text
Student{id=12, name='An', active=true}
```

Chuỗi thứ hai giúp hiểu object mà không cần mở từng field. Tuy nhiên, ví dụ `Student@5acf9800` chỉ là **dạng minh họa**, không phải giá trị hậu tố bảo đảm trên mọi lần chạy, mọi JVM hay mọi object.

Cách override thông dụng:

```java
@Override
public String toString() {
    return "Student{id=" + id
            + ", name='" + name + "'"
            + ", active=" + active + "}";
}
```

**Ghi nhớ từ đầu:**

- `toString()` tạo **biểu diễn dạng `String`** của một object; nó không thay đổi loại object.
- `Object.toString()` có implementation mặc định, nhưng phần lớn domain class nên cân nhắc một representation dễ đọc hơn.
- `System.out.println(object)` và nối chuỗi với object thường dẫn đến việc gọi `toString()` theo cơ chế chuyển thành chuỗi.
- Override đúng là **`public String toString()`, không có tham số**, nên sử dụng `@Override`.
- `toString()` không thay thế `equals()`, `hashCode()`, serialization hay định dạng API công khai.
- Một `toString()` tốt thường **ngắn, nhất quán, an toàn, ít side effects và không tiết lộ bí mật**.

Bài thuộc phần **lớp `Object`** trong Java Core, dùng **Java 17+**, đi từ contract cơ bản tới tình huống in/log thực tế: kế thừa, mảng, collection, record, enum, `null`, vòng tham chiếu, bảo mật, performance và các ví dụ có lệnh chạy cùng **stdout xác định**.

## 1. `toString()` được khai báo ở đâu?

Mọi class thông thường trong Java đều có quan hệ kế thừa đến `java.lang.Object` (trực tiếp hoặc gián tiếp). Vì vậy một object có thể dùng các method từ `Object`, bao gồm:

```java
public String toString()
```

Đây là **instance method**. Một class không override vẫn **kế thừa implementation** phù hợp.

Ví dụ:

```java
class User {
    private final int id;

    User(int id) {
        this.id = id;
    }
}
```

`User` không khai báo `toString()` nên lời gọi `new User(7).toString()` sử dụng implementation kế thừa từ `Object`.

**Không có nghĩa mọi object hiển thị một nội dung giống nhau.** Lớp runtime, `hashCode()`, override của các lớp thư viện và cách gọi API chuyển chuỗi đều có thể ảnh hưởng representation quan sát được.

### Tại sao gọi `toString()` mà không cần extends tường minh?

```java
class User {
}
```

về quan hệ superclass thông thường tương đương với:

```java
class User extends Object {
}
```

Nếu class extends một superclass khác, `toString()` có thể được kế thừa từ superclass đó hoặc từ `Object` ở xa hơn trong hierarchy, tùy method được override.

**Đừng nhầm `toString()` là hàm chỉ có ở `String`.** Nó là method thuộc contract của `Object` và rất nhiều class đã override riêng.

## 2. Biểu diễn mặc định của `Object.toString()`

Implementation của `Object.toString()` trả về một chuỗi tương đương với:

```java
getClass().getName() + "@"
        + Integer.toHexString(hashCode())
```

Trong đó:

- `getClass().getName()` là tên lớp runtime theo API `Class`, thường là tên fully qualified hoặc binary name thích hợp.
- `"@"` là ký tự phân tách.
- `Integer.toHexString(hashCode())` chuyển giá trị `int` từ method `hashCode()` sang biểu diễn hexadecimal không dấu.

Ví dụ dạng quan sát được của một class `Student` ở default package:

```text
Student@2f92e0f4
```

**Phần `2f92e0f4` chỉ là ví dụ.** Không được viết test khẳng định đúng chuỗi này khi gọi `Object.toString()`. Hậu tố thay đổi theo object, JVM và implementation của `hashCode()`.

### Hậu tố hexadecimal có phải địa chỉ bộ nhớ?

**Không nên suy ra như vậy.** Java không quy định rằng hậu tố đó là địa chỉ memory. Nó là **hexadecimal representation của giá trị `hashCode()`** được dùng bởi implementation mặc định của `Object.toString()`.

Nếu class override `hashCode()`, việc gọi `super.toString()` có thể dùng giá trị hash do override ấy trả về. Vì vậy càng không thể coi suffix là một memory address đáng tin.

### `Object.toString()` có phải khóa định danh toàn cục?

Không. Hai objects có thể có cùng hash code; `hashCode` không bảo đảm unique ID. Đừng lấy chuỗi default `Class@hex` làm database key, request ID hay identifier bất biến dài hạn.

Nếu cần phân biệt object theo nghiệp vụ, tạo **ID ổn định** hoặc value object thích hợp. Nếu cần identity diagnostic, có thể cân nhắc `System.identityHashCode` trong công cụ chẩn đoán, nhưng nó cũng **không bảo đảm duy nhất tuyệt đối**.

## 3. Chương trình đầu tiên: so sánh mặc định và override

Lưu thành **`ToStringFirstDemo.java`**:

```java
class PlainStudent {
    private final int id;

    PlainStudent(int id) {
        this.id = id;
    }
}

class Student {
    private final int id;
    private final String name;

    Student(int id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String toString() {
        return "Student{id=" + id
                + ", name='" + name + "'}";
    }
}

public class ToStringFirstDemo {
    public static void main(String[] args) {
        PlainStudent plain = new PlainStudent(12);
        Student student = new Student(12, "An");

        System.out.println(
                plain.toString().startsWith("PlainStudent@"));
        System.out.println(student.toString());
        System.out.println(student);
    }
}
```

Biên dịch và chạy JDK 17 trở lên:

```bash
javac -encoding UTF-8 ToStringFirstDemo.java
java ToStringFirstDemo
```

**Stdout xác định:**

```text
true
Student{id=12, name='An'}
Student{id=12, name='An'}
```

Giải thích:

1. `PlainStudent` không override, nên dùng `Object.toString()`; kiểm tra `startsWith` tránh phụ thuộc suffix hexadecimal.
2. `Student` override `toString()`, trả chuỗi được thiết kế.
3. `System.out.println(student)` có thể hiển thị representation của object mà không cần viết `student.toString()` tường minh.
4. `id` của cả hai objects chỉ xuất hiện trong chuỗi khi logic `toString()` thực sự đưa nó vào; `Object.toString()` mặc định **không tự duyệt fields**.

## 4. Cú pháp override đúng

Một override chuẩn:

```java
@Override
public String toString() {
    return "Some readable representation";
}
```

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Override` | Nhờ compiler kiểm tra đang override method hợp lệ |
| `public` | Giữ mức truy cập công khai của `Object.toString()` |
| `String` | Kiểu trả về của method |
| `toString` | Tên method đúng chính tả và chữ hoa/chữ thường |
| `()` | Không nhận tham số |
| `return ...` | Trả một chuỗi biểu diễn object |

**Hai lỗi phổ biến:**

```java
class Wrong {
    // String toString() { return "Wrong"; }
    // SAI: giảm visibility từ public của Object.toString().
}
```

```java
class OverloadInstead {
    public String toString(String prefix) {
        return prefix + "data";
    }
    // Đây là overload mới, KHÔNG override Object.toString().
}
```

Dùng `@Override` giúp phát hiện trường hợp viết nhầm `toString(String)` hoặc `tostring()` nếu tác giả tưởng đang override.

### Có cần `throws` không?

`Object.toString()` không khai báo checked exceptions. Một override không được mở rộng danh sách checked exceptions trái quy tắc overriding. Việc dựng chuỗi bình thường không cần khai báo `throws Exception`.

## 5. `toString()` là instance method có dynamic dispatch

`toString()` không phải static method. Nếu một subclass override, Java sẽ dùng **implementation phù hợp với runtime class của receiver**.

```java
Object object = new Student(12, "An");
System.out.println(object.toString());
```

Dù biến `object` có kiểu khai báo `Object`, runtime object là `Student` nên gọi override `Student.toString()`.

### Ví dụ qua ba kiểu tham chiếu

Lưu **`ToStringDispatchDemo.java`**:

```java
class Asset {
    private final String code;

    Asset(String code) {
        this.code = code;
    }

    protected String code() {
        return code;
    }

    @Override
    public String toString() {
        return "Asset[" + code + "]";
    }
}

class Vehicle extends Asset {
    Vehicle(String code) {
        super(code);
    }

    @Override
    public String toString() {
        return "Vehicle[" + code() + "]";
    }
}

public class ToStringDispatchDemo {
    public static void main(String[] args) {
        Asset base = new Asset("A");
        Asset vehicle = new Vehicle("V");
        Object view = vehicle;

        System.out.println(base);
        System.out.println(vehicle);
        System.out.println(view);
    }
}
```

```bash
javac -encoding UTF-8 ToStringDispatchDemo.java
java ToStringDispatchDemo
```

Stdout:

```text
Asset[A]
Vehicle[V]
Vehicle[V]
```

Hai biến `vehicle` và `view` có static types khác nhau, nhưng cùng tham chiếu tới object runtime `Vehicle`. Vì thế override `Vehicle.toString()` được chọn khi in cả hai.

### Nếu subclass không override?

Khi subclass không override, nó kế thừa implementation phù hợp gần nhất của superclass. Ví dụ `class Truck extends Vehicle { ... }` không khai báo `toString()` thì gọi method được kế thừa từ `Vehicle`. Điều này thường hợp lý nếu superclass representation vẫn đúng với subclass; nếu lớp con thêm thông tin quan trọng, cân nhắc override có chủ đích.

## 6. `System.out.println(object)` hoạt động ra sao?

`PrintStream.println` có nhiều overload:

```java
println(String value)
println(Object value)
println(int value)
println(char[] value)
...
```

Nếu đối số có kiểu tĩnh là một domain object như `Student`, overload `println(Object)` có thể được chọn. Nó chuyển object thành chuỗi theo semantics của API, thường thông qua `String.valueOf(object)`, rồi ghi nội dung kèm dấu xuống dòng.

Vì vậy:

```java
Student student = new Student(12, "An");

System.out.println(student);
System.out.println(student.toString());
```

thường cho cùng representation khi receiver khác null và `toString()` trả một String hợp lệ, nhưng **không phải mọi overload của `println` đều đồng nhất**. Trường hợp `char[]` là phản ví dụ đáng chú ý sẽ được giải thích phía sau.

### `print` khác `println`

`System.out.print(student)` chuyển object thành văn bản **không tự xuống dòng** sau nội dung.

`System.out.println(student)` chuyển object thành văn bản và **thêm kết thúc dòng** theo PrintStream.

Nếu ghi:

```java
System.out.print("Object: ");
System.out.println(student);
```

trong cùng luồng output, kết quả một dòng là `Object: Student{...}`.

## 7. Nối chuỗi: Java chuyển object thành văn bản

Khi một toán hạng của phép `+` là `String`, Java thực hiện nối chuỗi và chuyển toán hạng khác thành text theo quy tắc **string conversion**.

```java
Student student = new Student(12, "An");

String message = "Đang xử lý: " + student;
System.out.println(message);
```

Giả sử `Student.toString()` đã override như ví dụ đầu, message sẽ chứa representation của student.

**Lưu ý:** compiler/runtime có thể triển khai nối chuỗi bằng cơ chế tối ưu phù hợp (Java 17 thường sử dụng invokedynamic cho string concatenation). Không nên suy luận rằng mã nguồn `"x" + object` bắt buộc tạo và dùng đúng một `StringBuilder` ở cấp bytecode.

### Runnable: trực tiếp, nối chuỗi và `String.valueOf`

Lưu **`ToStringConversionDemo.java`**:

```java
record Point(int x, int y) {
}

public class ToStringConversionDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(point);
        System.out.println("Point = " + point);
        System.out.println(String.valueOf(point));
    }
}
```

```bash
javac -encoding UTF-8 ToStringConversionDemo.java
java ToStringConversionDemo
```

Stdout:

```text
Point[x=2, y=3]
Point = Point[x=2, y=3]
Point[x=2, y=3]
```

Record ở đây có `toString()` được compiler cung cấp, nên ba cách quan sát cùng dùng một representation xác định.

## 8. `String.valueOf(Object)` và `Objects.toString(Object)`

Khi một object có thể null, gọi trực tiếp:

```java
value.toString();
```

có thể gây `NullPointerException` nếu `value == null`.

`String.valueOf(Object)` cung cấp cơ chế chuyển một **tham chiếu object** thành chuỗi:

- Nếu tham chiếu null → trả chuỗi văn bản `"null"`.
- Nếu không null → dùng representation từ `toString()`.

`Objects.toString(Object)` cũng hỗ trợ null theo cách thông dụng:

```java
String left = String.valueOf((Object) null);
String right = java.util.Objects.toString(null);
```

Cả `left` và `right` đều là chuỗi `"null"`.

Có overload hữu ích:

```java
String label =
        java.util.Objects.toString(maybeNull, "<missing>");
```

Nếu `maybeNull` null, nhận `"<missing>"`; nếu khác null, dùng `maybeNull.toString()`.

### Ví dụ Java 17

Lưu **`NullSafeToStringDemo.java`**:

```java
import java.util.Objects;

public class NullSafeToStringDemo {
    public static void main(String[] args) {
        Object absent = null;
        Object present = "Java";

        System.out.println(String.valueOf(absent));
        System.out.println(Objects.toString(absent));
        System.out.println(Objects.toString(absent, "(missing)"));
        System.out.println(Objects.toString(present, "(missing)"));
    }
}
```

```bash
javac -encoding UTF-8 NullSafeToStringDemo.java
java NullSafeToStringDemo
```

Stdout:

```text
null
null
(missing)
Java
```

**Đừng nhầm chuỗi `"null"` với giá trị tham chiếu `null`.** Chuỗi có bốn ký tự là dữ liệu hợp lệ; reference null không trỏ object String nào.

## 9. Cẩn thận với overload của `String.valueOf` và `println`

Java có nhiều overload, nên lời gọi nhìn giống nhau có thể xử lý khác nhau.

Ví dụ mảng ký tự:

```java
char[] chars = {'J', 'a', 'v', 'a'};
System.out.println(chars);
```

`println(char[])` in **các ký tự**, chứ không dùng default array `Object.toString()`.

`String.valueOf(chars)` chọn overload `String.valueOf(char[])` và tạo `"Java"`.

Ngược lại, nếu ép kiểu:

```java
Object value = chars;
System.out.println(value);
```

overload `println(Object)` được chọn; mảng không override `Object.toString()` để tự in các phần tử, nên thường quan sát representation kiểu `[C@...` với suffix không cố định.

### Ví dụ không phụ thuộc suffix

Lưu **`CharArrayOverloadDemo.java`**:

```java
public class CharArrayOverloadDemo {
    public static void main(String[] args) {
        char[] chars = {'J', 'a', 'v', 'a'};
        Object asObject = chars;

        System.out.println(chars);
        System.out.println(String.valueOf(chars));
        System.out.println(
                asObject.toString().startsWith("[C@"));
    }
}
```

```bash
javac -encoding UTF-8 CharArrayOverloadDemo.java
java CharArrayOverloadDemo
```

Stdout:

```text
Java
Java
true
```

Điểm rút ra: **overload resolution dùng kiểu tĩnh của biểu thức**, còn instance `toString()` của runtime object có thể tạo representation khác. Không được suy đoán kết quả chỉ từ tên method.

## 10. Vì sao nên override `toString()` cho domain object?

Một object `Order` có thể chứa mã đơn hàng, trạng thái và số dòng. Representation mặc định `Order@hex` không giúp người đang debug biết order nào gặp lỗi.

Một method phù hợp:

```java
@Override
public String toString() {
    return "Order{id='" + id + "', status=" + status
            + ", lineCount=" + lines.size() + "}";
}
```

giúp:
- Nhận diện object khi in console.
- Tìm đối tượng liên quan trong log.
- Quan sát nhanh trạng thái thông qua debugger hoặc thông báo lỗi.
- Viết mô tả hữu ích cho diagnostics.
- Giảm việc lặp lại nhiều câu lệnh `println(field)` ở nơi khác.

**Nhưng** representation tốt không đồng nghĩa đưa **mọi field** vào chuỗi. Một số fields có thể lớn, vòng tham chiếu, tốn chi phí truy cập, không ổn định hoặc mang dữ liệu nhạy cảm.

### Mục tiêu thực tế

Một `toString()` tốt thường trả lời:

> “Đối tượng này là gì và thông tin nào là đủ để người đọc hiểu/truy tìm nó, với chi phí và rủi ro chấp nhận được?”

Không nhất thiết trả lời:

> “Toàn bộ dữ liệu bên trong đối tượng là gì, không bỏ sót byte nào?”

## 11. Một `toString()` giàu thông tin nhưng vừa đủ

Ví dụ domain:

```java
final class Task {
    private final long id;
    private final String name;
    private final boolean completed;

    Task(long id, String name, boolean completed) {
        this.id = id;
        this.name = name;
        this.completed = completed;
    }

    @Override
    public String toString() {
        return "Task{id=" + id
                + ", name='" + name + "'"
                + ", completed=" + completed + "}";
    }
}
```

Representation:
- Có tên type `Task`.
- Chứa ID hữu ích để định vị.
- Có trạng thái `completed`.
- Không tiết lộ data không cần thiết.

### Runnable

Lưu **`ReadableObjectDemo.java`**:

```java
final class Task {
    private final long id;
    private final String name;
    private final boolean completed;

    Task(long id, String name, boolean completed) {
        this.id = id;
        this.name = name;
        this.completed = completed;
    }

    @Override
    public String toString() {
        return "Task{id=" + id
                + ", name='" + name + "'"
                + ", completed=" + completed + "}";
    }
}

public class ReadableObjectDemo {
    public static void main(String[] args) {
        Task first = new Task(101, "Java Core", false);
        Task second = new Task(102, "OOP", true);

        System.out.println(first);
        System.out.println("Kiểm tra: " + second);
    }
}
```

```bash
javac -encoding UTF-8 ReadableObjectDemo.java
java ReadableObjectDemo
```

Stdout:

```text
Task{id=101, name='Java Core', completed=false}
Kiểm tra: Task{id=102, name='OOP', completed=true}
```

**Thiết kế format không có một chuẩn bắt buộc cho mọi class.** Dấu ngoặc nhọn, dấu phẩy và dấu nháy đơn chỉ là quy ước do tác giả chọn. Điều quan trọng là representation rõ ràng, phù hợp domain và được bảo trì nhất quán.

## 12. Khi object chứa object khác

Ví dụ:

```java
class Address {
    private final String city;
}

class Customer {
    private final String name;
    private final Address address;
}
```

`Customer.toString()` có thể gọi `address.toString()` để biểu diễn nested object. Nhưng cần cân nhắc:
- `address` có null được không?
- `Address.toString()` có an toàn và ngắn không?
- Có vòng tham chiếu ngược `address.customer` không?
- Có lộ thông tin cá nhân khi in cả địa chỉ không?

Nếu không cần full nested representation, đôi khi chỉ in `address.city()` hoặc một ID là đủ.

### Ví dụ composition an toàn với nested immutable object

Lưu **`NestedToStringDemo.java`**:

```java
import java.util.Objects;

record City(String name) {
    City {
        Objects.requireNonNull(name);
    }

    @Override
    public String toString() {
        return name;
    }
}

final class Store {
    private final String code;
    private final City city;

    Store(String code, City city) {
        this.code = Objects.requireNonNull(code);
        this.city = Objects.requireNonNull(city);
    }

    @Override
    public String toString() {
        return "Store{code='" + code + "', city=" + city + "}";
    }
}

public class NestedToStringDemo {
    public static void main(String[] args) {
        Store store = new Store("S01", new City("Hà Nội"));

        System.out.println(store);
    }
}
```

```bash
javac -encoding UTF-8 NestedToStringDemo.java
java NestedToStringDemo
```

Stdout:

```text
Store{code='S01', city=Hà Nội}
```

`Store.toString()` gián tiếp dùng `City.toString()`. Record `City` trong ví dụ **tự override** để hiển thị chỉ tên thành phố; không dùng format record mặc định.

## 13. Record tự có `toString()`

Java 17 hỗ trợ **record**:

```java
record Point(int x, int y) {
}
```

Compiler cung cấp một `toString()` cho record nếu record không khai báo implementation riêng. Với hai primitive components, representation là dạng:

```text
Point[x=2, y=3]
```

Record tự khai báo các component fields và những methods tương ứng, đồng thời có implementations cho `equals()`, `hashCode()` và `toString()` phù hợp record semantics.

### Chương trình record runnable

Lưu **`RecordToStringDemo.java`**:

```java
record Point(int x, int y) {
}

record Course(String title, int lessons) {
}

public class RecordToStringDemo {
    public static void main(String[] args) {
        System.out.println(new Point(2, 3));
        System.out.println(new Course("Java", 12));
    }
}
```

```bash
javac -encoding UTF-8 RecordToStringDemo.java
java RecordToStringDemo
```

Stdout:

```text
Point[x=2, y=3]
Course[title=Java, lessons=12]
```

**Không cần tự override mọi record chỉ để in component names.** Representation mặc định có thể đủ cho diagnostics.

### Có thể override `toString()` trong record không?

Có:

```java
record Product(String sku, int price) {
    @Override
    public String toString() {
        return sku + " (" + price + ")";
    }
}
```

Tuy nhiên nếu custom format phục vụ **API bên ngoài**, hãy cân nhắc một method riêng như `toDisplayText()` thay vì phụ thuộc toàn bộ contract của hệ thống vào `toString()`.

## 14. Record chứa reference mutable không tự deep immutable

Ví dụ:

```java
record Snapshot(int[] values) {
}
```

Record `Snapshot` là final type, fields cho components là final, nhưng `int[]` vẫn mutable. Hơn nữa, representation mặc định có thể gọi string conversion của mảng và hiển thị dạng `[I@...` thay vì các phần tử.

### Một cách custom hiển thị

```java
import java.util.Arrays;

record Snapshot(int[] values) {
    @Override
    public String toString() {
        return "Snapshot{values="
                + Arrays.toString(values) + "}";
    }
}
```

Ví dụ trên giả định `values` không null hoặc đã có validation; `Arrays.toString((int[]) null)` vẫn có cách biểu diễn null theo API.

**Nhưng custom `toString()` không biến mảng thành bất biến.** Nếu cần immutable snapshot, phải kiểm soát mutable input/output, ví dụ defensive copying trong constructor/accessor hoặc dùng immutable representation.

## 15. Mảng thường không tự in nội dung bằng `Object.toString()`

Một mảng trong Java là object, nhưng kiểu mảng không tự override `toString()` để render từng phần tử theo cách bạn thường muốn.

Ví dụ:

```java
int[] values = {1, 2, 3};
System.out.println(values);
```

Thông thường sẽ cho chuỗi dạng:

```text
[I@... 
```

trong đó `[I` là descriptor cho mảng một chiều kiểu `int` và suffix không xác định trước. Dấu ba chấm ở đây chỉ thay hash suffix, **không phải ký tự mà chương trình bảo đảm in**.

Để in nội dung:

```java
System.out.println(java.util.Arrays.toString(values));
```

kết quả:

```text
[1, 2, 3]
```

**Không nên viết expected stdout cố định cho direct array `toString()`**, bởi hậu tố hash code có thể khác nhau.

## 16. `Arrays.toString`, `Arrays.deepToString` và mảng nhiều chiều

`java.util.Arrays` cung cấp các methods hiển thị arrays:

- `Arrays.toString(int[])`, `Arrays.toString(long[])`, ... cho mảng primitives một chiều.
- `Arrays.toString(Object[])` cho mảng references một chiều, biểu diễn từng phần tử (có thể gọi `toString()` của elements).
- `Arrays.deepToString(Object[])` cho mảng objects lồng nhau, hữu ích với mảng nhiều chiều như `int[][]`.
- Primitive array nhiều chiều như `int[][]` là **mảng của `int[]`**, nên `Arrays.toString(matrix)` không in sâu các int elements.

### Chương trình Java 17

Lưu **`ArrayToStringDemo.java`**:

```java
import java.util.Arrays;

public class ArrayToStringDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        String[] names = {"An", "Bình"};
        int[][] matrix = {{1, 2}, {3, 4}};

        System.out.println(Arrays.toString(numbers));
        System.out.println(Arrays.toString(names));
        System.out.println(Arrays.deepToString(matrix));
        System.out.println(
                numbers.toString().startsWith("[I@"));
    }
}
```

```bash
javac -encoding UTF-8 ArrayToStringDemo.java
java ArrayToStringDemo
```

**Stdout:**

```text
[1, 2, 3]
[An, Bình]
[[1, 2], [3, 4]]
true
```

**Quan trọng:** `Arrays.deepToString` xử lý nested reference arrays. Nó có cơ chế cho trường hợp reference-cycle thích hợp, nhưng output cho một graph phức tạp vẫn có thể lớn và không nên dùng làm serializer chuẩn.

## 17. Collection thường có representation đọc được

Các lớp như `ArrayList` và nhiều implementation của `Collection`/`Map` cung cấp `toString()` hữu ích:

```java
List<String> names = List.of("An", "Bình");
System.out.println(names);
```

Ví dụ output:

```text
[An, Bình]
```

Nhưng representation của collection thường **dựa vào representation của các phần tử**. Nếu element class không override `toString()`, bạn có thể thấy:

```text
[Student@..., Student@...]
```

thay vì thông tin tên/id mong muốn.

### Đừng phụ thuộc order không được bảo đảm

Một `HashSet` hoặc `HashMap` không có cam kết iteration order giống `List` hoặc `LinkedHashMap` theo hợp đồng tương ứng. Vì `toString()` của collection thường duyệt elements/entries, output order có thể thay đổi.

**Tránh viết unit test kỳ vọng `HashMap.toString()` có một thứ tự cụ thể** nếu hợp đồng không bảo đảm thứ tự. Khi cần output ổn định, dùng cấu trúc có ordering contract hoặc sắp xếp dữ liệu trước khi biểu diễn.

## 18. Ví dụ collection + record cho stdout ổn định

Lưu **`CollectionToStringDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

record Item(String code, int quantity) {
}

public class CollectionToStringDemo {
    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 2),
                new Item("B", 1));

        Map<String, Integer> quantities = new LinkedHashMap<>();
        quantities.put("A", 2);
        quantities.put("B", 1);

        System.out.println(items);
        System.out.println(quantities);
    }
}
```

```bash
javac -encoding UTF-8 CollectionToStringDemo.java
java CollectionToStringDemo
```

Stdout:

```text
[Item[code=A, quantity=2], Item[code=B, quantity=1]]
{A=2, B=1}
```

`List.of` giữ thứ tự elements theo danh sách truyền vào; `LinkedHashMap` trong ví dụ duy trì thứ tự chèn theo cấu hình mặc định.

Nếu `Item.toString()` bị override để trả một format khác, representation của `items` cũng thay đổi tương ứng. Vì vậy thay `toString()` của element class có thể ảnh hưởng output chẩn đoán ở rất nhiều nơi.

## 19. String, StringBuilder và các kiểu thư viện khác

`String` tự biểu diễn bằng chính nội dung chuỗi:

```java
String text = "Java";
System.out.println(text.toString()); // Java
```

`StringBuilder` có thể thay đổi nội dung và `toString()` trả chuỗi biểu diễn trạng thái ký tự tại thời điểm gọi:

```java
StringBuilder builder = new StringBuilder("Java");
builder.append(" 17");
System.out.println(builder.toString()); // Java 17
```

Điều này nhắc rằng `toString()` **không có một format bắt buộc cho mọi class**. Tùy loại đối tượng, representation phù hợp có thể là:
- Chỉ giá trị text (String).
- Các ký tự tích lũy (StringBuilder).
- Record components (record).
- Collection of elements (List/Map).
- ID/trạng thái nghiệp vụ (domain object).
- Text chẩn đoán tùy API (exceptions hoặc một số framework objects).

Đừng dựa vào `Object.toString()` mặc định để suy đoán format của **mọi JDK class**; mỗi class có thể đã override.

## 20. Enum: `name()` khác `toString()`

Một enum constant có **tên khai báo** được cung cấp bởi `name()`, còn `toString()` có thể được override để hiển thị văn bản thân thiện.

```java
enum Status {
    NEW,
    DONE
}
```

Mặc định `Status.NEW.toString()` thường trả `"NEW"` theo behavior `Enum.toString()`. Nhưng tác giả enum có thể override `toString()` theo representation khác.

### Ví dụ runnable

Lưu **`EnumToStringDemo.java`**:

```java
enum Status {
    NEW("Chưa xử lý"),
    DONE("Hoàn thành");

    private final String label;

    Status(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}

public class EnumToStringDemo {
    public static void main(String[] args) {
        Status status = Status.DONE;

        System.out.println(status.name());
        System.out.println(status.toString());
        System.out.println(status);
    }
}
```

```bash
javac -encoding UTF-8 EnumToStringDemo.java
java EnumToStringDemo
```

Stdout:

```text
DONE
Hoàn thành
Hoàn thành
```

**Khi nào dùng `name()`?** Nếu cần tên khai báo chính thức của enum constant và chấp nhận ràng buộc khi đổi tên source, `name()` thể hiện rõ ý định hơn. Tuy nhiên **không nên dùng `name()` làm định dạng lưu trữ vĩnh viễn mà không thiết kế versioning** nếu enum names có thể thay trong tương lai.

**Khi nào dùng `toString()`?** Khi cần representation dễ đọc. Nhưng nếu text phụ thuộc ngôn ngữ người dùng, một method riêng như `displayName(Locale)` thường thích hợp hơn một `toString()` không nhận tham số.

## 21. Phân biệt `toString()` và serialization

Một lỗi kiến trúc thường gặp là dùng:

```java
String json = object.toString();
```

và tưởng biến `json` đã chứa JSON hợp lệ.

**Không đúng.** `toString()` không phải giao thức serialization chuẩn. Chuỗi tùy tác giả có thể:
- Không escape dấu nháy, dấu xuống dòng, ký tự điều khiển.
- Thiếu fields hoặc có fields phụ.
- Chứa thông tin thay đổi theo thời điểm/logging policy.
- Không thể parse ngược một cách đáng tin.
- Không có version schema.

Một representation:

```text
Customer{id=7, name='An'}
```

không phải JSON vì thiếu dấu nháy double chuẩn cho keys/strings và cú pháp JSON phù hợp.

Nếu cần JSON/XML/CSV hoặc protocol message:
- Dùng thư viện serializer thích hợp có hợp đồng rõ.
- Định nghĩa DTO/schema, escaping và versioning.
- Chọn timezone/locale/date format một cách tường minh.
- Không dùng `toString()` như dữ liệu hợp đồng mà các hệ thống khác phải parse.

### Display text cũng khác debug text

Một hóa đơn cho khách hàng cần ngôn ngữ, tiền tệ, bố cục và số liệu chính xác. Một `toString()` phục vụ debug có thể chỉ in `Invoice{id=..., total=...}`. Hai nhu cầu nên dùng **API riêng** nếu format có ý nghĩa nghiệp vụ.

## 22. `toString()`, `equals()` và `hashCode()` là ba hợp đồng khác nhau

`Object` cung cấp cả:

```java
public boolean equals(Object obj)
public int hashCode()
public String toString()
```

Đừng nhầm:

- `equals` xác định quan hệ **bằng nhau về mặt logic** theo contract.
- `hashCode` tạo giá trị hash phục vụ các cấu trúc như HashMap/HashSet, phải nhất quán với `equals`.
- `toString` tạo **mô tả bằng văn bản** để con người quan sát.

Hai objects có `toString()` giống nhau **không bắt buộc** được coi là bằng nhau bởi `equals`. Hai objects `equals` true cũng **không được Java yêu cầu** phải luôn có cùng `toString()`, dù thiết kế consistency có thể hữu ích.

### Đừng dùng `toString()` làm định danh trong equality

Sai về ý tưởng:

```java
@Override
public boolean equals(Object other) {
    return other != null
            && this.toString().equals(other.toString());
}
```

Cách này phụ thuộc format hiển thị, có thể sai type, thiếu state, lộ dependency trên fields không liên quan và dễ đệ quy. Hãy triển khai equality theo **business identity/value semantics**.

**Tương tự:** không nên triển khai `hashCode` bằng `toString().hashCode()` chỉ để khỏi suy nghĩ về fields; hai contracts có nhiệm vụ khác nhau.

## 23. Ví dụ: cùng biểu diễn, khác identity

Lưu **`ToStringIdentityDemo.java`**:

```java
final class Label {
    private final String value;

    Label(String value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return "Label[" + value + "]";
    }
}

public class ToStringIdentityDemo {
    public static void main(String[] args) {
        Label first = new Label("A");
        Label second = new Label("A");

        System.out.println(first.toString());
        System.out.println(second.toString());
        System.out.println(first == second);
        System.out.println(first.equals(second));
    }
}
```

```bash
javac -encoding UTF-8 ToStringIdentityDemo.java
java ToStringIdentityDemo
```

Stdout:

```text
Label[A]
Label[A]
false
false
```

`Label` **không override `equals()`** nên dùng identity-based equality của `Object`. Hai instances khác nhau nhưng `toString()` giống nhau do cùng `value`.

**Đừng lấy text presentation làm bằng chứng hai references cùng một object.**

## 24. Kế thừa: dùng `super.toString()` khi có ý nghĩa

Nếu superclass đã override `toString()` để hiển thị những thuộc tính chung, subclass có thể tái sử dụng representation ấy:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Person{name='" + name + "'}";
    }
}

class Employee extends Person {
    private final int level;

    Employee(String name, int level) {
        super(name);
        this.level = level;
    }

    @Override
    public String toString() {
        return "Employee{base=" + super.toString()
                + ", level=" + level + "}";
    }
}
```

`super.toString()` **chủ động gọi implementation superclass**, không phải dùng một cast để cố tắt virtual dispatch.

### Runnable

Lưu **`SuperToStringDemo.java`**:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Person{name='" + name + "'}";
    }
}

class Employee extends Person {
    private final int level;

    Employee(String name, int level) {
        super(name);
        this.level = level;
    }

    @Override
    public String toString() {
        return "Employee{base=" + super.toString()
                + ", level=" + level + "}";
    }
}

public class SuperToStringDemo {
    public static void main(String[] args) {
        Person person = new Person("An");
        Person employee = new Employee("Bình", 3);

        System.out.println(person);
        System.out.println(employee);
    }
}
```

```bash
javac -encoding UTF-8 SuperToStringDemo.java
java SuperToStringDemo
```

Stdout:

```text
Person{name='An'}
Employee{base=Person{name='Bình'}, level=3}
```

Nếu `Person` chưa override, `super.toString()` có thể trả default `Class@hex` theo runtime receiver (tên class runtime), không phải tên type `Person` cố định. Đó chưa chắc là điều subclass mong muốn.

### Rủi ro thiết kế

Nếu superclass thay format `toString()`, format subclass phụ thuộc `super.toString()` cũng thay. Khi cần một format ổn định, cân nhắc xây representation từ getters hoặc một helper API có contract rõ thay vì parse hoặc nhúng trực tiếp text không ổn định.

## 25. Không gọi `toString()` từ constructor khi subclass chưa hoàn chỉnh

`toString()` là **instance method overridable** nếu không bị `final`. Gọi nó trong superclass constructor có thể dispatch đến override của subclass **trước khi subclass fields được khởi tạo tường minh**.

Ví dụ lỗi thiết kế:

```java
class Base {
    Base() {
        System.out.println(this);
    }
}

class Child extends Base {
    private String state = "READY";

    @Override
    public String toString() {
        return "Child{state=" + state + "}";
    }
}
```

`new Child()` có thể in `Child{state=null}` vì constructor `Base` chạy trước instance field initializer `state = "READY"` của Child.

### Ví dụ Java 17 xác định

Lưu **`ConstructorToStringPitfallDemo.java`**:

```java
class Base {
    Base() {
        System.out.println("Base sees: " + this);
    }
}

class Child extends Base {
    private String state = "READY";

    @Override
    public String toString() {
        return "Child{state=" + state + "}";
    }
}

public class ConstructorToStringPitfallDemo {
    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("After: " + child);
    }
}
```

```bash
javac -encoding UTF-8 ConstructorToStringPitfallDemo.java
java ConstructorToStringPitfallDemo
```

**Stdout:**

```text
Base sees: Child{state=null}
After: Child{state=READY}
```

**Khuyến nghị:** không làm lộ `this` quá sớm và không gọi overridable methods từ constructor nếu chúng có thể phụ thuộc subclass state. `toString()` là một trường hợp cụ thể, không phải ngoại lệ của quy tắc khởi tạo.

## 26. Đệ quy vô hạn nếu `toString()` lại in chính `this`

Đây là bẫy nguy hiểm:

```java
class Bad {
    @Override
    public String toString() {
        return "Bad: " + this;
    }
}
```

Lý do:
1. Có lời gọi `object.toString()`.
2. Bên trong `toString()`, biểu thức `"Bad: " + this` phải chuyển `this` thành chuỗi.
3. Để chuyển thành chuỗi, lại gọi `this.toString()`.
4. Quá trình lặp không có điểm dừng.

Kết quả thường là **`StackOverflowError`**, không phải representation hợp lệ.

Tương tự:

```java
@Override
public String toString() {
    System.out.println(this);
    return "Bad";
}
```

cũng tự kích hoạt `toString()` khi in `this`, dẫn tới recursion.

### Cách sửa

Hãy in **các fields hoặc values thực sự cần thiết**, không in toàn bộ `this` từ chính `toString()`:

```java
@Override
public String toString() {
    return "Good{id=" + id + "}";
}
```

Có thể dùng `getClass().getSimpleName()` để biểu diễn tên type, nhưng việc này không phải cách khắc phục vòng đệ quy giữa các objects tham chiếu nhau.

## 27. Vòng tham chiếu giữa hai objects

Một association hai chiều:

```text
Department ----> Employee
      ^              |
      |--------------|
```

Nếu:
- `Department.toString()` in toàn bộ danh sách Employees.
- `Employee.toString()` in Department.
- Department chứa Employee đang trỏ ngược lại cùng Department.

thì chuỗi gọi có thể là:

```text
Department.toString()
 -> Employee.toString()
     -> Department.toString()
         -> Employee.toString()
             -> ...
```

Đây là **object graph cycle**. Java GC có thể thu gom reference cycles không còn reachable, nhưng **không làm cho một `toString()` đệ quy tự dừng**.

### Cách thiết kế an toàn

1. Trong `Department.toString()` chỉ in `departmentId` và `employeeCount`.
2. Trong `Employee.toString()` in `employeeId` và `departmentId`, không in Department object đầy đủ.
3. Nếu thật sự cần render graph, dùng một utility riêng có **visited set theo identity**, giới hạn depth và số elements.
4. Không đưa logic duyệt graph phức tạp vào `toString()` mặc định của mọi entity.
5. Với entities/JPA, tránh vô tình trigger lazy associations chỉ để render log.

## 28. Chương trình an toàn với association hai chiều

Lưu **`CyclicReferenceSafeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Department {
    private final String code;
    private final List<Employee> employees = new ArrayList<>();

    Department(String code) {
        this.code = code;
    }

    void add(Employee employee) {
        employees.add(employee);
    }

    String code() {
        return code;
    }

    @Override
    public String toString() {
        return "Department{code='" + code
                + "', employeeCount=" + employees.size() + "}";
    }
}

final class Employee {
    private final String name;
    private final Department department;

    Employee(String name, Department department) {
        this.name = name;
        this.department = department;
    }

    @Override
    public String toString() {
        return "Employee{name='" + name
                + "', departmentCode='" + department.code() + "'}";
    }
}

public class CyclicReferenceSafeDemo {
    public static void main(String[] args) {
        Department dev = new Department("DEV");
        Employee an = new Employee("An", dev);
        dev.add(an);

        System.out.println(dev);
        System.out.println(an);
    }
}
```

```bash
javac -encoding UTF-8 CyclicReferenceSafeDemo.java
java CyclicReferenceSafeDemo
```

Stdout:

```text
Department{code='DEV', employeeCount=1}
Employee{name='An', departmentCode='DEV'}
```

Mỗi method chỉ in **metadata ngắn** của relation, không cố mở toàn bộ object graph. Thiết kế này tránh đệ quy ở `toString()` dù references tạo thành vòng.

## 29. Bảo mật: không lộ mật khẩu, token và dữ liệu cá nhân

`toString()` thường được gọi gián tiếp trong logging, exception messages, debug printouts và error monitoring. Nếu nó in những fields như:

- Password, password hash, recovery code.
- Access token, refresh token, API key.
- Secret connection strings, private keys.
- Thông tin cá nhân không cần thiết.
- Dữ liệu thanh toán hoặc nội dung confidential.

thì chỉ một lệnh `logger.info("{}", user)` (tùy framework) hoặc `System.out.println(user)` có thể làm lộ dữ liệu ra log.

**Quy tắc:** mặc định không đưa bí mật vào `toString()`. Hãy dùng representation redacted.

Ví dụ:

```java
@Override
public String toString() {
    return "Credentials{username='" + username
            + "', password=<redacted>}";
}
```

Ở đây password không được đọc và biến thành chuỗi; chỉ in literal `<redacted>`.

### Nếu dữ liệu cá nhân là chính ID?

Cũng cần xem quyền truy cập log, mục đích quan sát và chính sách dữ liệu. Không phải mọi ID hay email đều an toàn để in mọi nơi. Có thể chỉ in stable pseudonymous ID, phần thông tin đã che hoặc một correlation ID.

**Không nên dùng `toString()` làm nơi duy nhất xử lý an toàn log**; kiểm soát log levels, retention, quyền truy cập và redaction ở logging pipeline vẫn cần thiết.

## 30. Runnable: `toString()` có che thông tin nhạy cảm

Lưu **`SafeToStringDemo.java`**:

```java
final class Credentials {
    private final String username;
    private final String password;

    Credentials(String username, String password) {
        this.username = username;
        this.password = password;
    }

    @Override
    public String toString() {
        return "Credentials{username='" + username
                + "', password=<redacted>}";
    }
}

public class SafeToStringDemo {
    public static void main(String[] args) {
        Credentials credentials =
                new Credentials("an", "secret-123");

        System.out.println(credentials);
    }
}
```

```bash
javac -encoding UTF-8 SafeToStringDemo.java
java SafeToStringDemo
```

Stdout:

```text
Credentials{username='an', password=<redacted>}
```

Lưu ý: biến `password` trong chương trình minh họa vẫn tồn tại trong object; **redaction trong `toString()` không xóa dữ liệu khỏi bộ nhớ**. Nó chỉ giúp representation không tiết lộ giá trị ấy ở đường in cụ thể.

## 31. `toString()` nên tránh side effects

Một `toString()` dùng để quan sát trạng thái nên **không tự làm thay đổi trạng thái nghiệp vụ**.

Thiết kế nguy hiểm:

```java
@Override
public String toString() {
    counter++; // Side effect không mong muốn.
    return "Counter=" + counter;
}
```

Khi một debugger hoặc logger yêu cầu representation, object bị mutate. Kết quả có thể khác nhau chỉ vì **số lần quan sát**.

Những thao tác thường nên tránh bên trong `toString()`:
- Ghi database hoặc gửi HTTP request.
- Tạo transaction hoặc thay trạng thái nghiệp vụ.
- Đọc file/network tốn kém.
- Gọi lazy-loaded association khiến truy vấn không mong muốn.
- Xóa hoặc sửa collection.
- Ném unchecked exception vì field tạm thời null mà không có chính sách phù hợp.
- Dùng thời gian hiện tại/random nếu không có lý do hiển thị rõ ràng.

**Mục tiêu thường là operation quan sát nhẹ, nhanh và ít ngạc nhiên.** Java không cấm toString có side effects, nhưng về thiết kế đó thường là lựa chọn kém.

## 32. Chi phí performance khi render object

Một `toString()` được gọi trong hot path có thể tốn thời gian nếu:
- Duyệt hàng nghìn elements trong một collection.
- Dựng chuỗi rất lớn.
- Đi theo relation graph sâu.
- Format dates/currency mỗi lần.
- Truy vấn dữ liệu bên ngoài qua getter.
- Phát sinh allocations đáng kể.

Đối với collection lớn, representation nên giới hạn số phần tử và hiển thị count:

```java
@Override
public String toString() {
    return "Batch{count=" + items.size() + "}";
}
```

Nếu cần dump đầy đủ, đặt tên operation rõ như `toDebugDump()` và kiểm soát caller/log level.

### Logging có thể trì hoãn formatting

Nhiều logging libraries có cơ chế **parameterized logging** hoặc supplier/lazy message để tránh dựng chuỗi khi log level bị tắt. Nhưng chi tiết tùy API/framework; đừng khẳng định tất cả logging frameworks luôn tránh gọi `toString()` trong mọi trường hợp.

Đối chiếu:
- `logger.debug("Object: " + object)` dựng message string ở biểu thức Java trước khi logger quyết định sử dụng, trừ khi compiler/framework có cơ chế đặc thù không thay semantics đánh giá đối số.
- API hỗ trợ lazy supplier hoặc placeholders có thể trì hoãn công việc format theo contract riêng.

Trong bài Java Core này, `System.out.println` thực sự quan sát object ngay lúc dòng chạy, không có cơ chế log-level filtering.

## 33. Thread-safety: representation có thể quan sát state đang đổi

Nếu object có mutable fields và nhiều threads thay đổi cùng lúc, `toString()` có thể đọc được **một tổ hợp giá trị không nhất quán** nếu không có synchronization/visibility contract.

Ví dụ ý tưởng:

```java
class Pair {
    int left;
    int right;

    @Override
    public String toString() {
        return "Pair{" + left + ", " + right + "}";
    }
}
```

Nếu một thread cập nhật `left` và `right` không đồng bộ trong khi thread khác gọi `toString()`, representation có thể ghi nhận trạng thái trung gian. Chỉ việc thêm `final` vào **method** hay vào **tham chiếu tới Pair** không làm object thread-safe.

Các lựa chọn tùy hợp đồng:
- Thiết kế immutable value object.
- Đồng bộ read/write bằng cùng lock.
- Đọc từ một immutable snapshot đã được publish an toàn.
- Dùng cấu trúc concurrent phù hợp.
- Không hứa rằng log là snapshot nguyên tử nếu không có bảo đảm.

Đừng gọi nhiều getters có side effects khác nhau rồi ghép thành một representation được coi là atomic snapshot nếu thực tế không có cơ chế bảo đảm.

## 34. Null fields bên trong object

Bản thân receiver của `toString()` phải khác null mới gọi được instance method trực tiếp. Nhưng **các fields bên trong object có thể null**.

```java
class User {
    private String nickname;

    @Override
    public String toString() {
        return "User{nickname=" + nickname + "}";
    }
}
```

Nối chuỗi với `nickname == null` có thể tạo text `null` một cách an toàn về mặt cú pháp. Tuy nhiên:

```java
return nickname.toUpperCase();
```

sẽ gây `NullPointerException` nếu nickname null.

Cân nhắc:
- Nếu null là trạng thái hợp lệ, in `(unknown)` hoặc `null` rõ ràng.
- Nếu null không hợp lệ, validate trong constructor/operation thay vì để `toString()` làm nơi phát hiện trễ.
- Nếu dữ liệu chứa bí mật, tránh in ngay cả khi nó khác null.
- Không tạo chuỗi sai nghĩa như “nickname='null'” khi người đọc có thể hiểu đó là tên thực.

### Sử dụng `Objects.toString` để có text thay thế

```java
return "User{nickname="
        + java.util.Objects.toString(nickname, "(unset)")
        + "}";
```

Cách này giúp biểu diễn rõ trường nullable.

## 35. Runnable: field nullable

Lưu **`NullableFieldToStringDemo.java`**:

```java
import java.util.Objects;

final class User {
    private final int id;
    private final String nickname;

    User(int id, String nickname) {
        this.id = id;
        this.nickname = nickname;
    }

    @Override
    public String toString() {
        return "User{id=" + id + ", nickname="
                + Objects.toString(nickname, "(unset)")
                + "}";
    }
}

public class NullableFieldToStringDemo {
    public static void main(String[] args) {
        System.out.println(new User(1, "An"));
        System.out.println(new User(2, null));
    }
}
```

```bash
javac -encoding UTF-8 NullableFieldToStringDemo.java
java NullableFieldToStringDemo
```

Stdout:

```text
User{id=1, nickname=An}
User{id=2, nickname=(unset)}
```

## 36. Định dạng thời gian và số: tách vấn đề Locale/timezone

Nếu representation chứa numbers, dates, currency hoặc decimal:
- `Double.toString(value)` dùng format khác với display theo locale.
- `LocalDate` có representation ISO-like rõ ràng.
- `Instant` biểu diễn một mốc trên UTC timeline.
- `ZonedDateTime` và `OffsetDateTime` mang dữ liệu timezone/offset theo semantics của chính chúng.

Nếu API cần output ổn định cho tests/diagnostics, **chọn format rõ ràng**, ví dụ `Locale.ROOT` với `String.format` khi cần điều khiển số thập phân.

**Đừng gọi `toString()` của một đối tượng rồi xem đó là giao thức vĩnh viễn cho mọi bản Java/JDK/library.** Format library-specific có thể thay nếu API không hứa ổn định.

### Ví dụ decimal với Locale.ROOT

Lưu **`LocaleToStringDemo.java`**:

```java
import java.util.Locale;

record Measurement(double value, String unit) {
    @Override
    public String toString() {
        return String.format(Locale.ROOT,
                "Measurement{value=%.2f, unit=%s}",
                value, unit);
    }
}

public class LocaleToStringDemo {
    public static void main(String[] args) {
        Measurement measurement =
                new Measurement(12.5, "kg");

        System.out.println(measurement);
    }
}
```

```bash
javac -encoding UTF-8 LocaleToStringDemo.java
java LocaleToStringDemo
```

Stdout:

```text
Measurement{value=12.50, unit=kg}
```

Có `Locale.ROOT` để số thập phân có dấu chấm trong representation minh họa, không phụ thuộc default locale của môi trường.

## 37. `String.format("%s", object)` có luôn gọi `toString()`?

Với object thông thường không implement cơ chế format riêng, conversion `%s` thường biểu diễn object bằng `toString()`; nếu object null, hiển thị `null`.

Tuy nhiên API `java.util.Formatter` có một đường đặc biệt: nếu argument implement **`java.util.Formattable`**, conversion `%s` có thể gọi **`formatTo(...)`** thay vì đơn giản gọi `toString()`.

Vì vậy:

```java
String text = String.format("Value=%s", object);
```

không nên coi như cách viết tương đương tuyệt đối của `"Value=" + object` đối với **mọi loại object**.

Ngoài ra, `String.format` có quy tắc `Locale`, format flags, width, precision và có thể ném formatting exceptions nếu format string không hợp lệ. Dùng `toString()` cho debug representation thông thường; dùng formatter khi yêu cầu định dạng có chủ đích.

### Ví dụ với record

```java
record Point(int x, int y) {
}

System.out.printf("Point: %s%n", new Point(1, 2));
```

Với JDK 17 và record này, kết quả:

```text
Point: Point[x=1, y=2]
```

Dấu `%n` là newline theo platform; khi ghi stdout theo dòng ở tài liệu, nội dung mỗi dòng vẫn như trên.

## 38. Không dùng `toString()` để kiểm thử toàn bộ trạng thái

Unit test dạng:

```java
assertEquals("Order{id=7, status=NEW}", order.toString());
```

có thể phù hợp **nếu chính format của `toString()` là hành vi bạn cần kiểm chứng**.

Nhưng nếu test đang muốn xác nhận logic nghiệp vụ, việc so sánh representation có thể gây **false failures** khi chỉ thay format debug:
- Đổi khoảng trắng.
- Thêm một field chẩn đoán.
- Đổi thứ tự fields.
- Tên class/record thay đổi.
- Đổi locale hoặc cách escape.

Test tốt cho domain behavior nên gọi **accessors/methods nghiệp vụ** hoặc so sánh value objects theo contract phù hợp. Test `toString` riêng để đảm bảo representation dễ đọc và không lộ secrets.

### Dạng kiểm tra linh hoạt khi có giá trị không ổn định

Nếu implementation default chứa suffix hash:

```java
String text = new Object().toString();
System.out.println(text.startsWith("java.lang.Object@"));
```

Dòng này cho `true` trên implementation `Object.toString` chuẩn; không kiểm tra toàn bộ `hex`.

Với object custom, nếu representation không được cam kết ổn định tuyệt đối, có thể assert các phần mang ý nghĩa như `contains("id=7")` và absence of secrets, nhưng vẫn phải tránh quá nhiều tests bám vào format nội bộ.

## 39. Công cụ debugger có thể hiển thị object khác `toString()`

Trong IDE/debugger, object thường được trình bày theo nhiều cách:
- Cây fields, properties.
- Class name + identity.
- Custom object renderer.
- Kết quả `toString()` nếu cấu hình và môi trường cho phép.

**Không được mặc định IDE luôn gọi `toString()`** hoặc không gọi nó. Một số debugger có thể thực thi method để tạo display text, mang rủi ro side effects và chi phí. Cấu hình của từng IDE có thể khác nhau.

Đó là lý do `toString()` không nên:
- Gây thay đổi business state.
- Blocking I/O không cần thiết.
- Truy cập remote resource.
- Tạo nhiều objects hoặc duyệt graph cực lớn.
- Ném lỗi vì field chưa khởi tạo.

Nếu object nặng, có thể thiết kế một summary ngắn, còn dump chi tiết là API riêng có thể kiểm soát lúc gọi.

## 40. Phân biệt `toString()` và một mã định danh ổn định

Một object có thể cần nhiều cách trình bày:

```java
record UserId(long value) {
}
```

- **ID:** `value()` → con số dùng để định vị người dùng trong domain.
- **Debug representation:** `toString()` → ví dụ `UserId[value=12]`.
- **Display label:** `displayName()` hoặc dữ liệu profile → ví dụ tên thân thiện với UI.
- **Serialization:** JSON/protobuf/DTO fields → hợp đồng riêng với hệ thống khác.

Đừng dùng `user.toString()` làm foreign key, cache key lâu dài hoặc URL path segment trừ khi bạn **cố ý định nghĩa** một định dạng stable, escaped và versioned — và lúc đó một method chuyên biệt thường dễ duy trì hơn.

Một đối tượng mutable còn có thể thay representation theo state:

```java
class Counter {
    int count;

    @Override
    public String toString() {
        return "Counter=" + count;
    }
}
```

Vì text thay đổi khi `count` đổi, không phù hợp làm khóa định danh bất biến.

## 41. So sánh nhanh các cách quan sát object

| Cách dùng | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `obj.toString()` | Lấy representation của object | Receiver null → lỗi |
| `System.out.println(obj)` | In object ra console | Chọn overload theo kiểu tĩnh; với domain object thường dùng object conversion |
| `"obj=" + obj` | Nối representation vào chuỗi | Có thể gọi conversion ngay khi đánh giá biểu thức |
| `String.valueOf(obj)` | Chuyển object/null thành text | `null` → `"null"` với Object overload |
| `Objects.toString(obj, fallback)` | Null-safe text có fallback | Chọn fallback khi obj null |
| `Arrays.toString(array)` | In elements mảng một chiều | Khác default array toString |
| `Arrays.deepToString(objectArray)` | In nested object arrays | Hữu ích với `int[][]` và arrays lồng |
| `record.toString()` | In record components | Auto-generated trừ khi custom override |
| `enum.name()` | Tên hằng enum | Khác display `toString()` nếu enum override |
| `String.format("%s", obj)` | Text theo Formatter | `Formattable` có thể can thiệp conversion |
| `serializer.write(obj)` | Định dạng data protocol | Không tương đương `toString()` |
| IDE object inspector | Quan sát fields/runtime state | Có thể hoặc không dùng `toString()` |

## 42. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| In object ra `Class@hex` | Class dùng inherited `Object.toString()` | Override representation phù hợp |
| Test phụ thuộc hậu tố hex | Hash suffix không ổn định | Kiểm tra pattern hoặc custom text ổn định |
| Tưởng `@hex` là memory address | Default format dùng `hashCode()` | Không dùng làm địa chỉ/ID |
| Viết `String toString()` không public | Giảm access từ public method của Object | Dùng `public String toString()` |
| Viết `toString(String prefix)` | Overload, không override | Dùng `@Override` và signature đúng |
| Return `"X" + this` ngay trong `toString()` | Tự gọi lại chính method | In fields cụ thể |
| In nested objects hai chiều vô hạn | Cycle của object graph | Chỉ in IDs/count hoặc graph renderer riêng |
| Array in `[I@...` | Mảng dùng inherited Object representation | `Arrays.toString` |
| Mảng hai chiều không in từng số | `Arrays.toString` không deep render | `Arrays.deepToString` |
| `char[]` in trực tiếp khác `Object` view | `println(char[])` overload | Xác định static type/call overload |
| List elements in `Class@hex` | Element class chưa override `toString()` | Override element hoặc map sang label |
| HashMap text thứ tự lúc khác | Collection không cam kết iteration order | Dùng ordered structure/sort trước |
| Log vô tình lộ password/token | `toString()` in sensitive field | Redact/omit và cấu hình log an toàn |
| Cứ log object là tải database | `toString()` đụng lazy association/getter | Chỉ in local summary và ID |
| Debugger làm object biến đổi | Side effect trong `toString()` | Pure-ish representation |
| `null.toString()` lỗi | Không có receiver object | `String.valueOf`/`Objects.toString` hoặc validate |
| `Record[array=...@hex]` | Component là mutable array | Custom `Arrays.toString`, cân nhắc copy |
| Dùng `toString` làm JSON | Không bảo đảm escaping/schema | Serializer/DTO riêng |
| Dùng `toString` làm `equals` | Text không phải equality contract | Compare fields/IDs theo logic |
| In object trong superclass constructor thấy field null | Virtual dispatch trước subclass initializer | Tránh gọi overridable methods khi construct |
| ToString trả output quá dài | Duyệt collection/graph không giới hạn | Summary, bounded elements/depth |
| Output thay theo Locale | Formatting dựa default Locale | Chọn Locale/formatter rõ |
| Gọi `%s` luôn giống `+` | Formatter có `Formattable` path | Biết API format đang dùng |

## 43. Bài tập 1 — Kết quả của `Object.toString()`

```java
class A {
}

A value = new A();
System.out.println(value);
```

**Hỏi:** có thể biết chính xác dòng stdout không?

**Đáp án:** Không thể suy ra toàn bộ suffix hexadecimal một cách portable. Theo representation mặc định, thường có dạng `A@...`. Đây không phải lý do để tự bịa một chuỗi hash cụ thể.

## 44. Bài tập 2 — Override đúng chữ ký

```java
class A {
    public String toString(int detail) {
        return "A:" + detail;
    }
}
```

**Hỏi:** `System.out.println(new A())` có dùng `toString(int)` không?

**Đáp án:** Không. Đây chỉ là overload khác tham số. `println` không tự gọi `toString(1)`; nó dùng representation của object theo `toString()` không đối số. Muốn custom phải khai báo `@Override public String toString()`.

## 45. Bài tập 3 — Dynamic dispatch

```java
class Parent {
    @Override
    public String toString() {
        return "P";
    }
}

class Child extends Parent {
    @Override
    public String toString() {
        return "C";
    }
}

Parent value = new Child();
System.out.println(value);
```

**Đáp án:** `C`. Runtime object là Child, method được override nên dispatch tới Child implementation.

## 46. Bài tập 4 — Null-safe chuyển chuỗi

```java
Object value = null;
System.out.println(String.valueOf(value));
System.out.println(java.util.Objects.toString(value, "none"));
```

**Stdout:**

```text
null
none
```

`String.valueOf(Object)` trả literal `"null"` với null; `Objects.toString` overload có fallback trả `"none"`.

## 47. Bài tập 5 — Mảng primitive

```java
int[] data = {4, 5};
System.out.println(java.util.Arrays.toString(data));
```

**Đáp án:**

```text
[4, 5]
```

Direct `System.out.println(data)` không bảo đảm chuỗi này; vì overload nhận array này là Object và array không tự render các elements như `Arrays.toString`.

## 48. Bài tập 6 — Mảng ký tự

```java
char[] text = {'O', 'K'};
System.out.println(text);
```

**Đáp án:**

```text
OK
```

Java chọn `println(char[])`. Nếu muốn quan sát giá trị như object, nên phân biệt `Object asObject = text` và gọi phù hợp; đừng suy ra mọi arrays in giống nhau.

## 49. Bài tập 7 — Record

```java
record Point(int x, int y) {
}

System.out.println(new Point(1, 2));
```

**Đáp án:**

```text
Point[x=1, y=2]
```

Record sinh `toString()` representation của components khi chưa custom override.

## 50. Bài tập 8 — Enum

```java
enum Level {
    HIGH;

    @Override
    public String toString() {
        return "high-priority";
    }
}

System.out.println(Level.HIGH.name());
System.out.println(Level.HIGH.toString());
```

**Stdout:**

```text
HIGH
high-priority
```

`name()` vẫn trả tên hằng enum, `toString()` có thể custom cho hiển thị.

## 51. Bài tập 9 — In trong constructor cha

```java
class Parent {
    Parent() {
        System.out.println(this);
    }
}

class Child extends Parent {
    String value = "ready";

    @Override
    public String toString() {
        return String.valueOf(value);
    }
}

new Child();
```

**Đáp án:** `null`. `Parent` constructor gọi `toString()` override ở Child trước khi field initializer `value = "ready"` chạy.

## 52. Bài tập 10 — Chuỗi `"X" + this`

```java
class Bad {
    @Override
    public String toString() {
        return "Bad" + this;
    }
}
```

**Đáp án:** Method tự gọi lại chính nó qua string conversion, thường gây `StackOverflowError`. Sửa bằng biểu diễn fields cụ thể, ví dụ `"Bad{id=" + id + "}"`.

## 53. Bài tập 11 — Collection ổn định thứ tự

```java
java.util.List<String> names =
        java.util.List.of("An", "Bình");
System.out.println(names);
```

**Đáp án:**

```text
[An, Bình]
```

`List` iteration order ở ví dụ xác định, và `String` elements hiển thị chính text của chúng.

## 54. Bài tập 12 — Hai chuỗi giống nhau có nghĩa objects bằng nhau?

```java
class User {
    @Override
    public String toString() {
        return "User";
    }
}

User a = new User();
User b = new User();

System.out.println(a.toString().equals(b.toString()));
System.out.println(a.equals(b));
```

**Stdout:**

```text
true
false
```

Hai representations bằng nhau, nhưng `equals` vẫn theo identity của `Object` vì class không override `equals`.

## 55. Bài tập 13 — Nên in gì từ Order có hàng nghìn OrderLines?

**Đề:** Order có 50.000 lines và nhiều liên kết hai chiều. Có nên `return "Order{" + lines + "}"` không?

**Đáp án:** Thường không. Nó có thể tạo text rất lớn, tốn chi phí, gây recursion nếu lines trỏ về Order và lộ dữ liệu không cần thiết. Nên in một summary như `Order{id=..., lineCount=50000, status=...}`; tạo dump riêng có giới hạn độ sâu/số phần tử nếu thực sự cần.

## 56. Bài tập 14 — An toàn thông tin

**Đề:** `Credentials` có fields username, password và accessToken. Thiết kế `toString()` nào phù hợp?

**Đáp án:** In thông tin tối thiểu không nhạy cảm như username nếu policy cho phép; biểu diễn password/token bằng `<redacted>` hoặc bỏ hẳn. Không dùng `getPassword()`/`getToken()` để đưa secret vào chuỗi. Bảo vệ log pipeline vẫn cần ngoài `toString()`.

## 57. Bài tập 15 — Superclass representation

```java
class Base {
    @Override
    public String toString() {
        return "Base";
    }
}

class Child extends Base {
    @Override
    public String toString() {
        return "Child(" + super.toString() + ")";
    }
}

System.out.println(new Child());
```

**Đáp án:**

```text
Child(Base)
```

`super.toString()` gọi implementation superclass theo cách đặc biệt; nếu thay bằng `((Base) this).toString()`, vẫn có dynamic dispatch tới Child và có nguy cơ recursion.

## 58. Bài tập 16 — Dùng cho JSON?

**Đề:** `record Customer(String name, int age)` in `Customer[name=An, age=20]`. Có thể gửi nguyên `toString()` làm JSON API response không?

**Đáp án:** Không. Đây là debug representation, không phải JSON schema. Dùng JSON serializer/DTO hợp lệ, escaping và versioning contract.

## 59. Bài tập 17 — `toString()` và mutable field

```java
class Counter {
    int value;

    @Override
    public String toString() {
        return "Counter=" + value;
    }
}

Counter counter = new Counter();
System.out.println(counter);
counter.value = 3;
System.out.println(counter);
```

**Stdout:**

```text
Counter=0
Counter=3
```

`toString()` trả text theo **trạng thái object tại lúc gọi**. Nó không chụp một snapshot bất biến vĩnh viễn ngay khi object được tạo.

## 60. Bài tập 18 — Field null và fallback

```java
String nickname = null;
System.out.println(
        java.util.Objects.toString(nickname, "unknown"));
```

**Đáp án:** `unknown`. Khi tham chiếu null, overload có fallback trả chuỗi thay thế, không gây `NullPointerException`.

## 61. Checklist triển khai `toString()`

1. Đã khai báo đúng **`@Override public String toString()`** chưa?
2. Kết quả có giúp xác định **loại object và trạng thái hữu ích** không?
3. Có đang dùng `Object.toString()` mặc định với hash suffix mà người đọc không cần không?
4. Có vô tình coi hash suffix là **địa chỉ memory/unique ID** không?
5. Có trường **password, token, secret, PII** cần bỏ hoặc redact không?
6. Representation có ngắn và dễ đọc ngay khi object chứa collections lớn không?
7. Có in toàn bộ object graph/lazy-loaded relations gây side effects hoặc recursion không?
8. Có vô tình nối **`this` trong chính `toString()`** không?
9. Nếu class có bidirectional associations, đã hạn chế references đệ quy chưa?
10. Method có thực hiện I/O, database query, thay mutable state hoặc blocking operation không?
11. Nếu object dùng trong nhiều threads, representation có thể thấy state trung gian không?
12. Có fields nullable cần `Objects.toString`/fallback không?
13. Có array cần `Arrays.toString` hoặc `Arrays.deepToString` không?
14. Có record auto-generated representation đủ dùng, hay thật sự cần override?
15. Với enum, có phân biệt `name()` và `toString()` không?
16. Có phụ thuộc iteration order của `HashMap`/`HashSet` không được bảo đảm không?
17. Nếu nối chuỗi hay gọi `println`, đã phân biệt overload đặc biệt như `char[]` chưa?
18. Nếu dùng `String.format`, đã xét Locale/`Formattable` khi cần chưa?
19. Nếu kế thừa, `super.toString()` có representation ổn định và hữu ích không?
20. Có gọi `toString()` từ constructor superclass khi subclass chưa init xong không?
21. Có đang dùng `toString()` làm JSON, storage key, equality check hoặc UI display contract một cách không chủ ý không?
22. Nếu cần output cho người dùng cuối, có nên có **formatter/display method riêng** không?
23. Tests có kiểm tra **đúng behavior cần thiết** thay vì phụ thuộc chuỗi chẩn đoán bất ổn không?
24. Có chương trình Java 17 runnable, đúng public class/file name và stdout ổn định không?

## Ghi nhớ

- **`toString()` của `java.lang.Object`** là nền tảng để có biểu diễn văn bản của object; class có thể **override** để in các fields có ý nghĩa.
- **Default `Object.toString()`** có dạng class name + `@` + hex của `hashCode()`; hậu tố không phải memory address hay unique identifier đáng tin.
- **`System.out.println(object)`, nối chuỗi và `String.valueOf(Object)`** thường dùng representation của `toString()`; lưu ý overload đặc biệt như `char[]`.
- **Mảng dùng `Arrays.toString` / `Arrays.deepToString`** nếu muốn hiển thị các phần tử; record có `toString()` được sinh theo components; enum có thể override representation hiển thị.
- **`toString()` là instance method có polymorphic dispatch**, nên biến khai báo kiểu `Object` vẫn có thể gọi override của runtime subclass.
- **`toString()` không phải serialization, equality hoặc định danh ổn định**. Những hợp đồng đó cần API riêng.
- Tránh **đệ quy tự gọi `this`**, vòng tham chiếu giữa objects, I/O nặng, mutation trong method và việc in dữ liệu nhạy cảm.
- Khi debugging/logging, ưu tiên một representation **ngắn gọn, có ID/trạng thái phù hợp, an toàn và có chi phí có thể dự đoán**.
