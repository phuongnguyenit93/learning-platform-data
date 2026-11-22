# Trường kiểu nguyên thủy và trường kiểu tham chiếu trong Java

Một **field (trường dữ liệu)** là biến được khai báo trong thân class hoặc interface, dùng để biểu diễn trạng thái của một đối tượng hoặc trạng thái gắn với class. Trong Java, field có thể mang **kiểu nguyên thủy (*primitive type*)** hoặc **kiểu tham chiếu (*reference type*)**. Điểm khác biệt quyết định cách chúng hoạt động là: field nguyên thủy giữ **giá trị nguyên thủy**, còn field tham chiếu giữ **giá trị tham chiếu đến đối tượng** hoặc `null`.

Hiểu đúng hai nhóm field giúp dự đoán kết quả của phép gán, giải thích vì sao hai đối tượng có thể nhìn thấy một thay đổi chung, xử lý giá trị chưa được thiết lập và bảo vệ trạng thái nội bộ khi thiết kế class. Nội dung bên dưới dùng Java 17+.

## 1. Nhận diện hai nhóm field

Xét một class quản lý hồ sơ:

~~~java
class StudentProfile {
    int age;                 // primitive field: giá trị int
    double averageScore;     // primitive field: giá trị double
    boolean active;          // primitive field: giá trị boolean

    String fullName;         // reference field: tham chiếu String hoặc null
    int[] examScores;        // reference field: tham chiếu mảng hoặc null
    Address address;         // reference field: tham chiếu Address hoặc null
}

class Address {
    String city;
}
~~~

Đây là **đoạn minh họa khai báo lớp**, chưa có phương thức `main` để chạy trực tiếp.

| Tiêu chí | Primitive field | Reference field |
| --- | --- | --- |
| Ví dụ | `int age`, `boolean active` | `String name`, `Address address`, `int[] scores` |
| Giá trị được lưu | Giá trị của kiểu nguyên thủy | Giá trị tham chiếu hoặc `null` |
| Giá trị mặc định ở field | `0`, `false`, `'\u0000'`… tùy kiểu | `null` |
| Có thể gán `null` trực tiếp? | Không | Có, nếu không bị ràng buộc bởi cơ chế khác |
| Phép gán từ một field cùng kiểu | Sao chép giá trị primitive | Sao chép giá trị tham chiếu |
| Hai field có thể cùng chỉ đến một đối tượng? | Không có khái niệm đối tượng được trỏ tới | Có |
| Có thể gọi instance method qua giá trị field? | Không trực tiếp trên primitive | Có khi tham chiếu khác `null` và kiểu cho phép |
| So sánh bằng `==` | So sánh giá trị primitive theo quy tắc toán tử | So sánh hai tham chiếu có cùng chỉ đến một đối tượng hay không |

Lưu ý: **tham chiếu cũng là một giá trị được gán và sao chép**. Khi nói “field tham chiếu giữ địa chỉ”, đó chỉ là cách ví von phổ biến; đặc tả Java không buộc chương trình biết hay thao tác một địa chỉ bộ nhớ thô. Cách JVM biểu diễn tham chiếu là chi tiết triển khai.

## 2. Tám kiểu nguyên thủy

Java có đúng **tám primitive type**:

| Kiểu | Nhóm | Kích thước/miền giá trị theo ngôn ngữ | Ví dụ |
| --- | --- | --- | --- |
| `byte` | Số nguyên | Có dấu, 8 bit, từ -128 đến 127 | `byte level = 5;` |
| `short` | Số nguyên | Có dấu, 16 bit, từ -32768 đến 32767 | `short year = 2026;` |
| `int` | Số nguyên | Có dấu, 32 bit | `int quantity = 10;` |
| `long` | Số nguyên | Có dấu, 64 bit | `long distance = 9_000_000_000L;` |
| `float` | Dấu phẩy động | 32 bit, chuẩn IEEE 754 | `float ratio = 0.5f;` |
| `double` | Dấu phẩy động | 64 bit, chuẩn IEEE 754 | `double price = 19.5;` |
| `char` | Ký tự | Giá trị mã UTF-16 không dấu, 16 bit (0 đến 65535) | `char grade = 'A';` |
| `boolean` | Luận lý | `true` hoặc `false`; không quy định kích thước lưu trữ vật lý cố định | `boolean enabled = true;` |

`char` biểu diễn **một UTF-16 code unit**, không nhất thiết là một ký tự Unicode hoàn chỉnh mà người dùng nhìn thấy; một số ký tự Unicode cần hai code unit (*surrogate pair*). `boolean` không tự chuyển đổi sang `0`/`1` như một số ngôn ngữ khác.

Các kiểu nguyên thủy **không phải class**, không phải đối tượng Java và không có identity của object. Vì vậy:

~~~java
class Metrics {
    int count = 3;
    boolean ready = true;
    double total = 7.5;

    // count.length() // sai: int không có instance method
}
~~~

Đoạn trên minh họa kiểu field; dòng comment là biểu thức không hợp lệ nếu bỏ comment. Các field vẫn có thể dùng trong phép tính và biểu thức so sánh phù hợp với kiểu tương ứng.

### 2.1. Field nguyên thủy chứa giá trị của riêng mình

~~~java
class Score {
    int value;
}
~~~

Giả sử có hai đối tượng `Score first` và `Score second`: mỗi đối tượng mang **instance field `value` riêng**. Gán `first.value = 10` không tự thay đổi `second.value`. Nếu viết `second.value = first.value`, Java sao chép con số hiện tại; sau đó sửa một bên không ảnh hưởng bên còn lại.

Một đối tượng `Score` có thể được trỏ đến bởi nhiều biến tham chiếu khác nhau; lúc đó `first` và một biến alias của `first` cùng truy cập **một instance field**. Vì thế cần phân biệt **hai đối tượng khác nhau** với **hai biến cùng tham chiếu đến một đối tượng**.

## 3. Các kiểu tham chiếu phổ biến

Reference type bao gồm class type, interface type, array type và các kiểu liên quan được Java hỗ trợ. Trong khai báo field, bạn thường gặp:

~~~java
class Order {
    String orderCode;              // String là class
    Customer customer;             // class tự định nghĩa
    java.util.List<String> items;  // List là interface
    int[] quantities;              // array là đối tượng
    Object extra;                  // tham chiếu đến đối tượng phù hợp
}

class Customer {
    String name;
}
~~~

Đây là ví dụ khai báo, chưa phải chương trình độc lập. Dù mảng `int[]` chứa **các phần tử kiểu nguyên thủy**, chính **field `quantities`** vẫn là một **reference field**, vì mảng trong Java là một object. Ngược lại, mỗi phần tử `quantities[i]` là giá trị `int`.

Reference field không chứa nguyên cả object “bên trong field” theo mô hình ngôn ngữ. Nó chứa một giá trị tham chiếu; object được tham chiếu có thể có nhiều field riêng và có thể được nhiều tham chiếu cùng trỏ tới.

Ví dụ:

~~~java
class Department {
    String name;
}

class Employee {
    Department department;
}
~~~

Hai đối tượng `Employee` độc lập vẫn có thể cùng giữ giá trị tham chiếu tới **một** đối tượng `Department`. Thay đổi `department.name` qua một nhân viên có thể được thấy qua nhân viên kia, nếu cả hai trỏ đến cùng object.

### 3.1. String là reference type dù trông giống giá trị

`String` là **class**; `String name` là reference field. Một `String` object **bất biến** (*immutable*): không thể sửa nội dung đối tượng String đã tạo.

~~~java
class Greeting {
    String message = "Xin chào";
}
~~~

Sau `greeting.message = "Tạm biệt"`, field trỏ tới một giá trị String khác; object String ban đầu không bị sửa nội dung. Đây là khác biệt với một class mutable như `StringBuilder` hoặc một `Address` cho phép cập nhật field.

`String` có các tính chất tối ưu hóa như string pool, nhưng **không dùng `==` để kết luận hai chuỗi có cùng nội dung**; nên dùng `equals` khi so sánh nội dung.

## 4. Giá trị mặc định: hệ quả của hai nhóm kiểu

Khi một field chưa có initializer tường minh, Java gán **giá trị mặc định theo kiểu**, không theo mong muốn nghiệp vụ: các kiểu số nguyên là `0`, kiểu dấu phẩy động là `0.0`, `boolean` là `false`, `char` có mã 0; mọi **reference field** là `null`. Quy tắc áp dụng cho cả instance fields và static fields.

```java
class Profile {
    int visits;        // 0
    boolean enabled;   // false
    String nickname;   // null, không phải ""
    int[] points;      // null, chưa có array object
}
```

Đây là **khai báo minh họa**, không có `main`. Sự khác biệt cần nhớ trong bài này là **primitive nhận một giá trị primitive, còn reference có thể không trỏ object nào**. `nickname.length()` hoặc `points.length` sẽ lỗi nếu reference vẫn `null`. Biến cục bộ lại phải được compiler chứng minh đã gán trước khi đọc (*definite assignment*). Ngay cả khi hợp lệ về kiểu, những mặc định đó có thể không thỏa invariant nghiệp vụ; constructor cần thiết lập dữ liệu bắt buộc.

## 5. Phép gán: sao chép giá trị nguyên thủy và sao chép tham chiếu

Đây là phần quan trọng nhất trong thực hành. Cả hai phép gán đều **sao chép một giá trị**. Khác biệt là giá trị đó đại diện cho điều gì.

~~~java
int a = 10;
int b = a;       // b nhận bản sao giá trị 10
b = 99;          // không đổi a

Address first = new Address();
Address second = first; // sao chép tham chiếu, chưa tạo object Address mới
~~~

Đoạn này minh họa cơ chế. Nếu `first` và `second` cùng trỏ tới một `Address` mutable, sửa trạng thái của object qua `second` có thể nhìn thấy qua `first`. Nhưng **`second = new Address()` không làm `first` tự trỏ sang object mới**.

### 5.1. Ví dụ đầy đủ: hai field tham chiếu cùng trỏ đến một object

Tạo tệp **`FieldKindsDemo.java`**:

~~~java
public class FieldKindsDemo {
    static final class Location {
        String city;

        Location(String city) {
            this.city = city;
        }
    }

    static final class Member {
        int points;              // primitive field
        boolean verified;        // primitive field
        String nickname;         // reference field
        Location location;       // reference field

        Member(int points, Location location) {
            this.points = points;
            this.location = location;
        }
    }

    public static void main(String[] args) {
        Location shared = new Location("Huế");

        Member first = new Member(10, shared);
        Member second = new Member(20, shared);

        int copiedPoints = first.points;
        copiedPoints = 99;

        System.out.println("copiedPoints = " + copiedPoints);
        System.out.println("first.points = " + first.points);

        Location copiedLocation = first.location;
        copiedLocation.city = "Đà Nẵng";

        System.out.println("first.city = " + first.location.city);
        System.out.println("second.city = " + second.location.city);

        copiedLocation = new Location("Hà Nội");

        System.out.println("first.city after reassignment = " + first.location.city);
        System.out.println("default verified = " + first.verified);
        System.out.println("nickname is null = " + (first.nickname == null));
        System.out.println("same location = " + (first.location == second.location));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 FieldKindsDemo.java
java FieldKindsDemo
~~~

**Stdout chính xác:**

~~~text
copiedPoints = 99
first.points = 10
first.city = Đà Nẵng
second.city = Đà Nẵng
first.city after reassignment = Đà Nẵng
default verified = false
nickname is null = true
same location = true
~~~

Giải thích từng bước:

1. `shared` tham chiếu đến một `Location("Huế")`. Constructor của `Member` sao chép **giá trị tham chiếu** này vào `first.location` và `second.location`; không tạo hai `Location`.
2. `copiedPoints = first.points` sao chép giá trị primitive `10`. Gán `copiedPoints = 99` chỉ sửa biến cục bộ; `first.points` vẫn bằng `10`.
3. `copiedLocation = first.location` tạo một alias cho cùng `Location`. `copiedLocation.city = "Đà Nẵng"` sửa field `city` **trên object dùng chung**, nên cả `first.location.city` lẫn `second.location.city` đều đổi theo.
4. `copiedLocation = new Location("Hà Nội")` chỉ thay giá trị của biến `copiedLocation`. Hai field `first.location` và `second.location` vẫn tham chiếu đến `Location` cũ tại Đà Nẵng.
5. `verified` chưa được gán nên mặc định `false`; `nickname` chưa được gán nên mặc định `null`. Hai field `location` đang tham chiếu cùng object nên `first.location == second.location` là `true`.

Một sơ đồ khái niệm ngay sau câu lệnh `copiedLocation.city = "Đà Nẵng"` và **trước** khi gán `copiedLocation = new Location(...)`:

~~~text
Member first                       Member second
+------------------+               +------------------+
| points = 10      |               | points = 20      |
| location --------+----+      +---+-------- location |
+------------------+    |      |   +------------------+
                        v      v
                    +-------------------+
                    | Location object   |
                    | city = "Đà Nẵng"  |
                    +-------------------+
                              ^
                              |
                       copiedLocation
~~~

Đây là **mô hình về quan hệ tham chiếu**, không phải sơ đồ địa chỉ vùng nhớ hoặc layout vật lý bắt buộc của JVM.

## 6. Gán tham chiếu không phải sao chép sâu đối tượng

Giả sử:

~~~java
class Basket {
    int[] quantities;
}
~~~

Nếu có hai `Basket` khác nhau nhưng cùng giữ tham chiếu đến **một mảng `int[]`**, thay đổi `first.quantities[0]` có thể quan sát qua `second.quantities[0]`. Phép `second.quantities = first.quantities` không tạo bản sao mảng.

Muốn có mảng khác với các phần tử primitive được sao chép, có thể dùng `clone()` của array hoặc `Arrays.copyOf(...)`:

~~~java
int[] source = {2, 4, 6};
int[] copied = source.clone();

copied[0] = 99;

System.out.println(source[0]); // 2
System.out.println(copied[0]); // 99
~~~

Đoạn này là fragment trong method (không có class `main` độc lập). Nó minh họa **mảng primitive**: mỗi phần tử là giá trị `int` nên sao chép mảng sẽ sao chép các số đó.

Nếu mảng chứa **reference**, như `Address[]`, thao tác `clone()` hoặc `Arrays.copyOf` chỉ tạo mảng mới và sao chép **các tham chiếu phần tử**. Hai mảng có thể tiếp tục trỏ đến cùng các `Address` mutable; đó là **shallow copy**, không phải deep copy. Muốn độc lập cả các đối tượng con cần sao chép theo cấu trúc dữ liệu và hợp đồng riêng của từng kiểu.

## 7. Trường tham chiếu có thể null; trường primitive thì không

`null` biểu thị **không có tham chiếu đến object**. Nó không phải là một object riêng, không có method, và không thể gán trực tiếp cho primitive:

~~~java
class Customer {
    int age;          // không thể gán age = null
    String name;      // có thể nhận null
}
~~~

Nếu viết `customer.name.length()` khi `name == null`, Java ném `NullPointerException` tại thời điểm chạy.

Một đoạn kiểm tra an toàn:

~~~java
if (customer.name != null) {
    System.out.println(customer.name.length());
}
~~~

Đoạn trên yêu cầu biến `customer` đã tham chiếu một `Customer` khác null. Nếu bản thân `customer == null`, cả biểu thức `customer.name` cũng gây `NullPointerException`. Khi dữ liệu bắt buộc có, có thể kiểm tra sớm trong constructor:

~~~java
import java.util.Objects;

class RegisteredCustomer {
    private final String id;

    RegisteredCustomer(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }
}
~~~

Đây là đoạn khai báo minh họa, không có `main`. `Objects.requireNonNull` ném `NullPointerException` khi `id` là null, giúp phát hiện thiếu dữ liệu ngay lúc tạo đối tượng. Với ràng buộc khác (ví dụ chuỗi không rỗng), cần kiểm tra thêm.

### 7.1. Wrapper class và auto-unboxing

Các primitive có lớp bao tương ứng: `Integer` cho `int`, `Long` cho `long`, `Double` cho `double`, `Boolean` cho `boolean`, v.v. **Field kiểu wrapper là reference field**, có thể mang `null`.

~~~java
class Registration {
    int attempts;       // mặc định 0
    Integer maxRetries; // mặc định null
}
~~~

`Integer value = 10;` sử dụng boxing tự động trong ngữ cảnh thích hợp. Còn:

~~~java
Integer boxed = null;
// int unboxed = boxed; // Nếu thực thi sẽ ném NullPointerException
~~~

Trình biên dịch chấp nhận phép gán `Integer` sang `int` thông qua **unboxing**, nhưng lúc chạy sẽ lỗi nếu tham chiếu là `null`. Vì vậy cần lựa chọn đúng giữa “`0` là giá trị có ý nghĩa” và “chưa có giá trị”.

Wrapper còn có overhead cấp phát/đại diện object tùy cách tối ưu và không có cùng ngữ nghĩa với primitive. Hạn chế dùng `Integer` chỉ để thay `int` nếu không cần khả năng null hoặc API đòi hỏi kiểu tham chiếu.

## 8. Toán tử == và equals: hai kiểu field dẫn đến hai câu hỏi khác nhau

### 8.1. Với primitive: so sánh giá trị

~~~java
int left = 42;
int right = 42;
System.out.println(left == right); // true
~~~

`==` trên các primitive số/`char`/`boolean` hợp lệ so sánh giá trị theo quy tắc của Java (có thể có numeric promotion). Với số dấu phẩy động, cần lưu ý `NaN == NaN` là `false` và sai số biểu diễn khiến so sánh `double` trực tiếp có thể không phù hợp khi kiểm tra kết quả tính toán gần đúng.

### 8.2. Với reference: == kiểm tra cùng object

~~~java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);       // false: hai object String khác nhau
System.out.println(a.equals(b));  // true: String.equals so sánh nội dung
~~~

Đây là fragment trong method. `new String("Java")` cố ý tạo hai object khác nhau để minh họa identity; **không** cần tạo String theo cách này trong ứng dụng bình thường. Đừng dựa vào việc `"Java" == "Java"` đôi lúc cho `true` do string interning để suy ra `==` so sánh nội dung String.

Với reference field, `Objects.equals(a, b)` hữu ích khi một bên có thể null: nó kiểm tra null rồi gọi `equals` phù hợp. Lưu ý `equals` của từng kiểu có hợp đồng riêng; không phải mọi class đều định nghĩa content equality, bởi `Object.equals` mặc định tương đương so sánh identity khi chưa override.

| Mục đích | Cách thực hiện điển hình |
| --- | --- |
| Hai `int` có cùng giá trị? | `x == y` |
| Hai reference có trỏ cùng object? | `left == right` |
| Hai `String` có cùng nội dung? | `left.equals(right)` nếu `left` non-null |
| Hai reference có cùng nội dung và có thể null? | `Objects.equals(left, right)` |
| Kiểm tra reference chưa trỏ tới object? | `value == null` |

## 9. final: không cho gán lại field, nhưng chưa chắc object bất biến

Modifier `final` có cùng nguyên tắc cơ bản ở cả hai nhóm field: sau khi được gán trong quá trình khởi tạo hợp lệ, field đó **không được gán lại**.

~~~java
class Example {
    final int id = 10;
    final String title = "Cơ bản";
    final int[] scores = {1, 2, 3};

    void update() {
        // id = 20;           // sai: không thể gán lại final field
        // title = "Nâng cao"; // sai: không thể gán lại final field
        scores[0] = 99;       // hợp lệ: sửa nội dung mảng
        // scores = new int[3]; // sai: không thể gán lại final field
    }
}
~~~

Đây là đoạn khai báo, không có `main`. `final int id` cố định giá trị primitive `10` cho một đối tượng. `final int[] scores` cố định **tham chiếu của field**, nhưng mảng được tham chiếu vẫn mutable. Với `String`, tham chiếu final không đổi và String bản thân cũng immutable nên không có cách sửa nội dung String đang trỏ tới qua API bình thường.

Các mức độ cần phân biệt:

1. **Không gán lại tham chiếu:** `final` field.
2. **Đối tượng không cho sửa trạng thái:** do thiết kế class; `String` là ví dụ.
3. **Đồ thị đối tượng bất biến sâu:** mọi thành phần có thể quan sát đều phải được kiểm soát; chỉ thêm `final` cho reference không đủ.

Ví dụ lớp bảo vệ mảng bằng defensive copy:

~~~java
class GradeBook {
    private final int[] grades;

    GradeBook(int[] grades) {
        this.grades = grades.clone();
    }

    int[] getGrades() {
        return grades.clone();
    }
}
~~~

Đây là đoạn khai báo minh họa, chưa có `main`. `clone()` tại constructor ngăn caller giữ tham chiếu tới **chính mảng nội bộ**; `clone()` trong getter ngăn caller sửa mảng nội bộ bằng tham chiếu được trả về. Với mảng `int[]`, sao chép một tầng là đủ để tách các giá trị nguyên thủy. Để code thực tế chặt chẽ, nên kiểm tra `grades != null` hoặc dùng `Objects.requireNonNull` trước khi clone.

## 10. Field nguyên thủy/tham chiếu độc lập với instance/static

Hai cách phân loại không loại trừ nhau:

- **Primitive / reference** mô tả **kiểu của giá trị mà field chứa**.
- **Instance / static** mô tả field thuộc **mỗi đối tượng** hay thuộc **class**.

Ví dụ:

~~~java
class RuntimeState {
    int currentLevel;                       // instance + primitive
    String currentUser;                     // instance + reference

    static int activeUsers;                 // static + primitive
    static String applicationName = "Demo"; // static + reference
}
~~~

Đây là đoạn minh họa, không có `main`.

| Field | Primitive/reference | Instance/static |
| --- | --- | --- |
| `currentLevel` | Primitive `int` | Instance |
| `currentUser` | Reference `String` | Instance |
| `activeUsers` | Primitive `int` | Static |
| `applicationName` | Reference `String` | Static |

Nếu hai đối tượng `RuntimeState` khác nhau, `currentLevel` của chúng độc lập. Mọi instance của cùng class đã được nạp trong ngữ cảnh thông thường cùng nhìn vào static field `activeUsers`. Nếu một static reference field trỏ tới một mutable object dùng chung, mọi code có quyền truy cập qua nó có thể tác động cùng object.

**Static không tự động thread-safe**. Phép `activeUsers++` có thể mất cập nhật khi nhiều thread chạy đồng thời; nếu dữ liệu được chia sẻ giữa thread, cần thiết kế đồng bộ phù hợp (ví dụ `AtomicInteger` hoặc `synchronized`). Việc chọn primitive không loại bỏ nhu cầu kiểm soát tương tranh.

## 11. Constructor, đóng gói và bảo vệ dữ liệu

Nên cân nhắc khai báo field là `private` và dùng constructor để thiết lập trạng thái hợp lệ. Ví dụ một đơn hàng gồm số lượng `int` và mã sản phẩm `String`:

~~~java
import java.util.Objects;

class OrderLine {
    private final String productCode;
    private final int quantity;

    OrderLine(String productCode, int quantity) {
        Objects.requireNonNull(productCode, "productCode");

        if (productCode.isBlank()) {
            throw new IllegalArgumentException("productCode rỗng");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }

        this.productCode = productCode;
        this.quantity = quantity;
    }

    String getProductCode() {
        return productCode;
    }

    int getQuantity() {
        return quantity;
    }
}
~~~

Đây là đoạn khai báo, chưa có `main`. `productCode` là reference field kiểu `String`; constructor kiểm tra null và nội dung rỗng. `quantity` là primitive field nên không thể null; constructor vẫn cần kiểm tra tính hợp lệ của giá trị `int`.

Với **mutable reference type** như `Date` hoặc `ArrayList`, chỉ giữ `private final` chưa đủ để bảo vệ invariant. Nếu caller đưa vào một object rồi sửa object đó, trạng thái nội bộ có thể bị ảnh hưởng. Có thể:

- Tạo bản sao phù hợp khi tiếp nhận đối tượng; với collection chứa immutable element, `List.copyOf(source)` có thể tạo danh sách không sửa được theo API và tách khỏi biến đổi cấu trúc của `source`.
- Tránh trả trực tiếp một mutable object nếu caller không nên chỉnh sửa; dùng getter trả bản sao hoặc một view không cho sửa khi đáp ứng yêu cầu.
- Với collection chứa các phần tử mutable, cần xem xét cả **bản thân phần tử**. `List.copyOf` không tự deep-copy mỗi object bên trong.

**Không cần sao chép vô điều kiện:** một object immutable như `String` có thể được chia sẻ an toàn về mặt thay đổi nội dung. Quyết định sao chép phụ thuộc việc đối tượng có mutable hay không, quy tắc sở hữu và yêu cầu hiệu năng.

## 12. Khi nào nên dùng primitive, khi nào dùng reference?

| Nhu cầu | Lựa chọn thường hợp lý | Cân nhắc |
| --- | --- | --- |
| Đếm sản phẩm, số lần thử, tuổi đã được xác nhận | `int` hoặc `long` | Giá trị 0 có ý nghĩa hay phải validate? |
| Bật/tắt một khả năng | `boolean` | Chỉ có true/false, không có “chưa biết” |
| Số đo thực | `double` | Biểu diễn nhị phân có sai số; không dùng tùy tiện cho tiền |
| Mã chữ đơn ở dạng UTF-16 code unit | `char` | Không đại diện mọi Unicode character đầy đủ |
| Tên, mã, thông báo | `String` | Có thể null; String immutable |
| Tập điểm số | `int[]` hoặc collection phù hợp | Field giữ tham chiếu; cần xem xét aliasing |
| Một đối tượng domain liên quan | Kiểu class/interface | Có thể chia sẻ object, cần xem xét tính mutable |
| Số nguyên có khả năng “chưa nhập” | `Integer` khi API yêu cầu null | Unboxing null có thể NPE; overhead boxing |
| Thuộc tính nhiều biến thể hoặc logic riêng | Class/record thiết kế phù hợp | Kiểm soát invariant thay vì thêm nhiều field rời |

Một số dữ liệu có tính quy tắc đặc thù: với tiền tệ có thể dùng `BigDecimal` (reference type) hoặc biểu diễn số đơn vị nhỏ nhất bằng `long` nếu bài toán cho phép và kiểm soát được tràn số. Không có loại field “đúng cho mọi trường hợp”; lựa chọn dựa trên miền giá trị, khả năng thiếu dữ liệu và hợp đồng của class.

## 13. Những nhầm lẫn phổ biến

1. **“Field String là primitive vì gán bằng literal.”** Sai: `String` luôn là class/reference type; cú pháp `"text"` chỉ giúp viết String literal.
2. **“Mảng `int[]` là primitive vì chứa int.”** Sai: mảng là object; field `int[]` mang tham chiếu tới mảng, từng phần tử mới là `int`.
3. **“Gán reference sẽ sao chép object.”** Sai: chỉ sao chép giá trị tham chiếu. Muốn tách mutable state phải tạo bản sao thích hợp.
4. **“Thay tham chiếu trong biến thứ hai làm biến thứ nhất đổi theo.”** Sai: gán `b = new X()` chỉ thay `b`; khác với thao tác `b.field = value` sửa object mà cả hai có thể cùng trỏ đến.
5. **“Trường int chưa gán sẽ là null.”** Sai: instance/static field kiểu `int` mặc định bằng 0. Biến cục bộ không được đọc trước khi gán.
6. **“Trường tham chiếu mặc định tạo object rỗng.”** Sai: mặc định `null`; field `String name;` không tự tạo String `""`, field `int[] values;` không tự tạo mảng độ dài 0.
7. **“`final Address` làm mọi field của Address bất biến.”** Sai: `final` ngăn gán lại tham chiếu field, không tự chặn sửa `Address.city`.
8. **“Hai String dùng `==` là so sánh nội dung.”** Sai: `==` trên reference hỏi có cùng object hay không; nội dung cần `equals` hoặc quy tắc tương ứng của class.
9. **“Java truyền object theo tham chiếu.”** Diễn đạt thiếu chính xác: Java **luôn truyền đối số theo giá trị**. Với reference type, giá trị được sao chép là tham chiếu; method có thể sửa object được tham chiếu nhưng không thay biến ở caller chỉ bằng cách gán lại tham số.
10. **“Primitive luôn ở stack, reference luôn ở heap.”** Sai nếu coi là quy định ngôn ngữ: instance field thuộc trạng thái của object, static field thuộc class, còn cách JVM/JIT bố trí hay tối ưu bộ nhớ là chi tiết triển khai.

### 13.1. Phép truyền đối số vẫn theo giá trị

Ví dụ minh họa (fragment bên trong class/method phù hợp):

~~~java
static void change(int number, StringBuilder text) {
    number = 100;           // chỉ đổi bản sao của số
    text.append("!");       // sửa object StringBuilder được chia sẻ
    text = new StringBuilder("Khác"); // chỉ gán lại tham số cục bộ
}
~~~

Nếu caller có `int n = 1` và `StringBuilder s = new StringBuilder("Hi")`, rồi gọi `change(n, s)`, sau lời gọi `n` vẫn là 1, còn `s.toString()` là `"Hi!"`. Việc gán `text = new ...` không khiến `s` trỏ sang object mới. Không có khái niệm “truyền tham số theo tham chiếu” cho một biến Java theo nghĩa cho phép method gán lại biến ở caller.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `String code;` và `int quantity;` là hai instance field chưa khởi tạo tường minh. Chúng có giá trị gì sau khi tạo đối tượng?

**Đáp án:** `code == null` và `quantity == 0`; đây là giá trị mặc định của reference và `int` field.

**Câu 2.** `int[] numbers` là field primitive hay reference? Phần tử `numbers[0]` thuộc loại gì sau khi mảng `new int[3]` đã được gán?

**Đáp án:** `numbers` là reference field trỏ tới array object; `numbers[0]` là phần tử primitive `int`, khởi tạo mặc định bằng 0.

**Câu 3.** `first.address = second.address`. Thay đổi `first.address.city` có thể ảnh hưởng `second.address.city` không?

**Đáp án:** Có, nếu cả hai field còn cùng trỏ tới một `Address` mutable và thao tác sửa được phép. Phép gán đã sao chép tham chiếu, không tạo bản sao đối tượng.

**Câu 4.** `final int[] values = {1, 2};`. Có thể thực thi `values[0] = 7` và `values = new int[]{3, 4}` không?

**Đáp án:** Có thể sửa phần tử `values[0]`, nhưng không được gán lại field `values` vì nó là `final`.

**Câu 5.** Vì sao `Integer retries = null; int x = retries;` lỗi lúc chạy dù biên dịch được?

**Đáp án:** Compiler thêm unboxing từ `Integer` sang `int`; unboxing một null reference gây `NullPointerException`.

**Câu 6.** Hai biến `String a` và `String b` có cùng nội dung chữ. `a == b` chắc chắn là `true` không?

**Đáp án:** Không. `==` kiểm tra cùng object. Nếu cần so sánh nội dung, dùng `a.equals(b)` khi `a` khác null, hoặc `Objects.equals(a, b)` nếu có thể null.

Để đọc một class có nhiều field, hãy trả lời theo thứ tự: **field mang giá trị nguyên thủy hay tham chiếu; giá trị mặc định có hợp lệ không; reference có thể null không; object được trỏ tới có mutable không; liệu hai field có thể alias cùng object không; có cần defensive copy hoặc validation không**. Trả lời được các câu hỏi đó là nền tảng để xây dựng trạng thái đối tượng Java dễ hiểu, an toàn và có thể kiểm chứng.
