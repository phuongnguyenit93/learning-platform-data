# Record component, trường `private final` và accessor trong Java 17

Một `record` trong Java 17 giúp khai báo ngắn gọn một kiểu dữ liệu có **cấu trúc cố định**. Danh sách ở phần đầu khai báo `record` gọi là **record components**. Mỗi component liên hệ trực tiếp đến một **trường instance `private final`**, một **accessor công khai**, và một **tham số của canonical constructor**.

Ví dụ:

```java
record Person(String name, int age) {}
```

Từ dòng này, trình biên dịch Java 17 tự tạo những thành phần thiết yếu để lưu và truy cập hai giá trị `name`, `age`. Hiểu cơ chế đó giúp sử dụng `record` đúng, tránh nhầm với field công khai, getter JavaBeans và khái niệm bất biến dữ liệu.

> **Phiên bản:** Records đã là tính năng chính thức từ Java 16 (JEP 395); với **Java 17** không cần `--enable-preview`. Các ví dụ trong bài sử dụng cú pháp được hỗ trợ chính thức bởi Java 17.

## 1. Record component là gì?

**Record component** là một mục khai báo **kiểu dữ liệu và tên** trong phần header của `record`:

```java
record Book(String title, String author, int pages) {}
//          ^^^^^^^^^^^^  ^^^^^^^^^^^^^  ^^^^^^^^^
//           component 1   component 2     component 3
```

Ở đây có ba component:

| Component | Kiểu khai báo | Tên | Accessor tương ứng |
|---|---|---|---|
| `String title` | `String` | `title` | `title()` |
| `String author` | `String` | `author` | `author()` |
| `int pages` | `int` | `pages` | `pages()` |

Danh sách component mô tả **trạng thái cốt lõi** của mỗi đối tượng `Book`. Vị trí của mỗi component cũng quan trọng: thứ tự trong header là thứ tự tham số của **canonical constructor**.

Để tạo và sử dụng đối tượng:

```java
Book book = new Book("Effective Java", "Joshua Bloch", 416);

System.out.println(book.title());
System.out.println(book.author());
System.out.println(book.pages());
```

Kết quả:

```text
Effective Java
Joshua Bloch
416
```

Các lời gọi `title()`, `author()` và `pages()` hợp lệ mặc dù ta **không hề tự viết ba phương thức** đó. Trình biên dịch tạo accessor tương ứng với từng component.

### 1.1. Component không phải “biến public”

Một component trong header không khai báo field public. Java lưu trạng thái bên trong đối tượng qua các field có phạm vi `private` và tính chất `final`.

Ví dụ sau **không hợp lệ** nếu viết ở bên ngoài `Book`:

```java
// Sai: title là private field.
// System.out.println(book.title);

// Sai: không thể gán trực tiếp cho field.
// book.pages = 500;

// Đúng: gọi accessor công khai.
System.out.println(book.title());
```

Cụm từ *record component* mô tả **khai báo thành phần** ở header. Field tương ứng và accessor là những thành viên khác nhau được sinh ra từ khai báo đó.

### 1.2. Kiểu dữ liệu của component

Component có thể dùng kiểu nguyên thủy, kiểu tham chiếu, generic type và mảng:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

record Invoice(
        long id,
        BigDecimal amount,
        LocalDate issuedAt,
        List<String> tags,
        byte[] signature
) {}
```

Các component ở đây có kiểu khác nhau nhưng đều dẫn đến quy tắc **field private final + accessor cùng tên**. Với kiểu tham chiếu hoặc mảng, `final` chỉ cố định **tham chiếu được giữ trong field**, không tự làm nội dung đối tượng bất biến. Phần 6 phân tích chi tiết điều này.

## 2. Java tạo field, constructor và accessor như thế nào?

Xét khai báo:

```java
record Point(int x, int y) {}
```

Về mô hình, có thể hình dung các thành viên chính gần tương đương với:

```java
// Mã sau chỉ để minh họa các thành viên cốt lõi,
// KHÔNG phải bản mã nguồn chính xác mà javac tạo.
final class PointLike {
    private final int x;
    private final int y;

    public PointLike(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() {
        return x;
    }

    public int y() {
        return y;
    }
}
```

Bảng liên hệ:

| Khi viết trong header | Trường được suy ra | Accessor được suy ra | Tham số constructor |
|---|---|---|---|
| `int x` | `private final int x` | `public int x()` | `int x` |
| `int y` | `private final int y` | `public int y()` | `int y` |

Ngoài những thành viên đó, record còn có cách triển khai phù hợp của `equals(Object)`, `hashCode()` và `toString()`; chúng sử dụng trạng thái của các component.

Một record là một class đặc biệt, kế thừa trực tiếp `java.lang.Record`, và được xem là **`final`** (không thể được class khác kế thừa). Vì vậy:

```java
record Point(int x, int y) {}

// Sai: Point là final.
// class ColorPoint extends Point {}
```

**Điều cần nhớ:** không phải compiler “dịch record thành một class thông thường có code y hệt” theo nghĩa chuẩn hóa mã nguồn; bảng và lớp `PointLike` chỉ là cách minh họa những thành viên mà lập trình viên có thể quan sát/sử dụng.

### 2.1. Quan sát thành viên qua công cụ `javap`

Nếu tạo tệp `Point.java`:

```java
public record Point(int x, int y) {}
```

Trong terminal dùng JDK 17:

```bash
javac --release 17 Point.java
javap -p Point
```

`javap -p` hiển thị cả thành viên `private`, nên có thể nhận ra kiểu dữ liệu, field và phương thức do compiler tạo. Kết quả có những dòng tương đương:

```text
public final class Point extends java.lang.Record {
  private final int x;
  private final int y;
  public Point(int, int);
  public final java.lang.String toString();
  public final int hashCode();
  public final boolean equals(java.lang.Object);
  public int x();
  public int y();
}
```

Đây là **kết quả dạng minh họa**, thứ tự hiển thị thành viên có thể khác theo trình biên dịch/công cụ. Thứ cần quan sát là field mang `private final` và accessor trả về đúng kiểu component.

## 3. Field `private final` của record

Với:

```java
record User(long id, String email) {}
```

Java thiết lập các trường lưu trữ:

```java
// Biểu diễn ý nghĩa, không viết thêm các dòng này trong User:
private final long id;
private final String email;
```

### 3.1. Vì sao là `private`?

`private` đóng quyền truy cập trực tiếp từ các class khác. Thông tin được đọc thông qua giao diện công khai là accessor:

```java
User user = new User(101L, "a@example.com");

System.out.println(user.id());    // 101
System.out.println(user.email()); // a@example.com
```

Cách này cho phép record **quy định rõ cách đọc giá trị** khi cần, chẳng hạn trả về bản sao của dữ liệu mutable trong một explicit accessor.

### 3.2. Vì sao là `final`?

`final` buộc field được gán đúng trong quá trình khởi tạo đối tượng và không được gán lại sau đó.

```java
record User(long id, String email) {
    void changeEmail(String newEmail) {
        // Sai: field là final.
        // this.email = newEmail;
    }
}
```

Từ bên ngoài cũng không thể:

```java
User user = new User(101L, "a@example.com");

// Sai: không tồn tại setter tự sinh.
// user.setEmail("b@example.com");

// Sai: field private final.
// user.email = "b@example.com";
```

Nếu cần giá trị khác, cách tự nhiên là **tạo một record mới**:

```java
User updated = new User(user.id(), "b@example.com");
```

Hai đối tượng có trạng thái riêng: `user` vẫn có email ban đầu, còn `updated` mang email mới.

### 3.3. Không tự khai báo lại instance field của component

Không cần và không được thêm field instance vào body của record để “định nghĩa lại” component:

```java
// Sai: record không cho phép tự khai báo instance field.
// record User(long id) {
//     private final long id;
// }
```

Một record cũng không cho phép khai báo thêm instance field khác ngoài các field suy ra từ record components:

```java
// Sai: extra là instance field khai báo thêm.
// record User(long id) {
//     private int extra;
// }
```

Nhưng record **có thể có static field**, phương thức thành viên, constructor phù hợp, và có thể triển khai interface:

```java
record Product(String name, long price) {
    static final String CURRENCY = "VND";

    String label() {
        return name() + ": " + price() + " " + CURRENCY;
    }
}
```

Việc dùng `name()` và `price()` trong phương thức do mình viết là rõ ràng và nhất quán với API của record.

## 4. Accessor của record: `name()` thay vì `getName()`

Với component `String name`, accessor mặc định là **`public String name()`**.

```java
record Employee(String name, int level) {}

Employee e = new Employee("Mai", 3);

String n = e.name();
int l = e.level();
```

Không có getter JavaBeans `getName()` hoặc `getLevel()` được sinh tự động.

| Thành phần | Cú pháp đúng của record | Không tự có |
|---|---|---|
| Component `name` | `employee.name()` | `employee.getName()` |
| Component `level` | `employee.level()` | `employee.getLevel()` |
| Component `active` kiểu `boolean` | `employee.active()` | `employee.isActive()` |

Ví dụ:

```java
record Feature(String name, boolean active) {}

Feature f = new Feature("Export", true);

System.out.println(f.name());
System.out.println(f.active());
```

Dù component kiểu `boolean`, accessor mặc định vẫn là **`active()`**.

### 4.1. Accessor có tham số không?

Accessor của component **không nhận tham số**:

```java
record Size(int width, int height) {}

Size size = new Size(800, 600);

System.out.println(size.width());  // 800
System.out.println(size.height()); // 600

// Sai: width() không có tham số.
// size.width(1024);
```

Accessor có **kiểu trả về giống hệt kiểu khai báo component**: `width()` trả `int`, `name()` trả `String`, `tags()` trả `List<String>` nếu component là `List<String> tags`.

### 4.2. Accessor được sinh có phạm vi `public`

Dù record không có từ khóa `public` (record là package-private), các accessor sinh ra vẫn mang modifier `public`. Khả năng truy cập được record từ package khác vẫn chịu chi phối bởi **phạm vi của chính kiểu record**.

Nếu muốn sử dụng kiểu record từ package khác, khai báo một top-level record `public` trong tệp có tên tương ứng:

```java
// File: com/example/model/Employee.java
package com.example.model;

public record Employee(String name, int level) {}
```

Khi đó client truy cập được `Employee` và `Employee.name()`/`Employee.level()` nếu có quyền truy cập package/module tương ứng.

### 4.3. Có thể tự viết accessor không?

Có. Trường hợp này gọi là **explicit accessor**. Nó phải khớp contract của component: là instance method `public`, không tham số, trả về đúng kiểu dữ liệu component, không khai báo type parameters hoặc `throws` clause.

Ví dụ:

```java
record Title(String text) {
    public String text() {
        return text;
    }
}
```

Dòng `return text;` bên trong body record truy cập field `private final` do Java tạo. Vì có explicit accessor hợp lệ, Java **không sinh thêm** accessor `text()` khác.

Đây là phương thức công khai do lập trình viên viết:

```java
Title title = new Title("Java 17");
System.out.println(title.text());
```

**Lưu ý về thiết kế:** một record được định hướng như một *transparent carrier* của các giá trị component. Accessor tùy biến nên duy trì ý nghĩa dữ liệu của component. Ví dụ accessor `price()` trả một giá bán khác với giá trị field thực tế có thể khiến người đọc bất ngờ vì `equals`/`hashCode` mặc định căn cứ vào trạng thái các component, không dựa vào cách tự biến đổi dữ liệu tùy ý của accessor. Nếu muốn chuẩn hóa giá trị, ưu tiên làm **trong constructor**.

## 5. Component và canonical constructor

Mỗi record có một **canonical constructor** với danh sách tham số tương ứng component theo **cùng thứ tự và kiểu**.

```java
record Person(String name, int age) {}

Person p = new Person("An", 20);
```

Ở đây constructor có hai tham số `(String name, int age)`. Lệnh sau không khớp thứ tự hoặc kiểu:

```java
// Sai: tham số đầu phải là String.
// Person wrong = new Person(20, "An");
```

### 5.1. Compact canonical constructor

Để kiểm tra và chuẩn hóa đầu vào, có thể viết **compact constructor** bằng cú pháp `public Person { ... }`. Trong compact constructor, Java tự gán các field component từ tham số tương ứng **sau khi body kết thúc bình thường**:

```java
import java.util.Objects;

public record Person(String name, int age) {
    public Person {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be non-negative");
        }
    }
}
```

Nếu gọi:

```java
Person p = new Person("  An  ", 20);
System.out.println(p.name()); // "An"
System.out.println(p.age());  // 20
```

Dòng `name = ...` ở compact constructor đang thay đổi **tham số đầu vào**, không gán lại field `private final`. Java dùng giá trị tham số đã được chuẩn hóa khi thực hiện phép gán field ngầm định ở cuối constructor.

Trong compact constructor, **không tự gán** `this.name = ...` hoặc `this.age = ...`; phép gán field do Java đảm nhiệm.

### 5.2. Explicit canonical constructor

Nếu cần viết toàn bộ canonical constructor, khai báo danh sách tham số khớp header và tự gán **tất cả** component fields:

```java
import java.util.Objects;

record PointLabel(int x, int y, String label) {
    public PointLabel(int x, int y, String label) {
        this.x = x;
        this.y = y;
        this.label = Objects.requireNonNull(label).strip();
    }
}
```

Khác với compact constructor, explicit canonical constructor **tự chịu trách nhiệm khởi tạo** các final field.

Với record dành cho dữ liệu thông thường, compact constructor thường dễ viết và giảm nguy cơ bỏ sót field.

### 5.3. Constructor bổ sung phải điều hướng về canonical constructor

Một record có thể cung cấp constructor tiện ích, nhưng non-canonical constructor phải gọi constructor khác bằng `this(...)`:

```java
record Range(int start, int end) {
    Range(int end) {
        this(0, end);
    }

    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }
}
```

`new Range(10)` chuyển đến canonical constructor `Range(int start, int end)`, nơi mọi component được kiểm tra và khởi tạo.

## 6. `private final` chỉ bảo đảm bất biến nông

Đây là sai lầm hay gặp nhất khi làm việc với record: **field final không bảo đảm đối tượng được tham chiếu cũng bất biến**.

### 6.1. Ví dụ với component kiểu mảng

```java
record Scores(int[] values) {}

int[] input = {10, 20};
Scores scores = new Scores(input);

input[0] = 99; // Sửa trực tiếp nội dung mảng đã truyền vào.

System.out.println(scores.values()[0]); // 99
```

Nguyên nhân:

- Field `values` trong `Scores` là `private final int[] values`.
- `final` chỉ ngăn gán field sang **một mảng khác**.
- Nó không ngăn thay đổi các phần tử của **mảng hiện tại**.
- Accessor tự sinh `values()` trả về **chính tham chiếu mảng** được lưu trong record.

Người sử dụng còn có thể sửa thông qua accessor:

```java
scores.values()[1] = 77;
System.out.println(input[1]); // 77
```

Vì thế không thể mặc định rằng mọi record đều có trạng thái bất biến sâu.

### 6.2. Sao chép khi nhận và khi trả mảng

Nếu cần bảo vệ mảng khỏi sửa từ bên ngoài, sao chép đầu vào và đầu ra:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeScores(int[] values) {
    public SafeScores {
        values = Objects.requireNonNull(values, "values").clone();
    }

    public int[] values() {
        return values.clone();
    }

    public int sum() {
        return Arrays.stream(values).sum();
    }
}
```

Sử dụng:

```java
int[] input = {10, 20};
SafeScores scores = new SafeScores(input);

input[0] = 99;            // Không ảnh hưởng mảng nội bộ.
scores.values()[1] = 77;  // Chỉ sửa bản sao vừa nhận.

System.out.println(scores.sum()); // 30
```

Ở compact constructor, `values = values.clone()` thay thế **tham số**, rồi Java gán bản sao đó vào field cuối constructor. Explicit accessor `values()` cũng sao chép khi trả về.

**Điểm nâng cao cần biết:** record có component mảng vẫn có `equals`/`hashCode` mặc định theo cách so sánh của các component; với mảng, so sánh mặc định căn cứ vào **tham chiếu** chứ không tự động so từng phần tử. Hai bản sao mảng có phần tử giống nhau không nhất thiết khiến hai record bằng nhau. Nếu cần value equality theo nội dung mảng, phải tự thiết kế lại `equals`/`hashCode` một cách nhất quán hoặc dùng kiểu cấu trúc bất biến phù hợp hơn.

### 6.3. Chụp bản sao an toàn hơn với `List.copyOf`

Một lựa chọn phổ biến trong Java 17 là chuyển `List` đầu vào thành một danh sách không sửa được:

```java
import java.util.List;
import java.util.Objects;

record Course(String title, List<String> lessons) {
    public Course {
        title = Objects.requireNonNull(title, "title").strip();
        lessons = List.copyOf(lessons);
    }
}
```

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("Introduction", "Records"));
Course course = new Course("Java 17", source);

source.add("Sealed classes");

System.out.println(course.lessons());
// [Introduction, Records]
```

Với record `Course`:

- `List.copyOf` tạo snapshot danh sách theo nội dung tại thời điểm xây dựng và trả danh sách **không hỗ trợ sửa đổi**.
- `course.lessons().add("Extra")` sẽ ném `UnsupportedOperationException`.
- Những thay đổi về cấu trúc của `source` sau khi tạo record không làm thay đổi danh sách được lưu.

**Giới hạn:** Nếu mỗi phần tử của list là một đối tượng mutable, `List.copyOf` không tự sao chép sâu các đối tượng đó. Với `List<String>`, phần tử `String` bất biến nên ví dụ đơn giản này là lựa chọn phù hợp. `List.copyOf` cũng không chấp nhận phần tử `null`.

## 7. Tự viết accessor có làm thay đổi `equals`, `hashCode` không?

Không nên giả định rằng thay accessor sẽ tự định nghĩa lại cách so sánh của record. Xét:

```java
record MaskedSecret(String value) {
    public String value() {
        return "***";
    }
}
```

`MaskedSecret` vẫn lưu field `value` bên trong. Accessor trả về chuỗi được che, nhưng `equals` và `hashCode` mặc định dựa trên **trạng thái của component được lưu**, không mặc định gọi accessor viết lại để lấy `"***"`.

Ví dụ:

```java
MaskedSecret first = new MaskedSecret("alpha");
MaskedSecret second = new MaskedSecret("beta");

System.out.println(first.value());           // ***
System.out.println(second.value());          // ***
System.out.println(first.equals(second));    // false
```

Điều này thể hiện vì sao accessor có hành vi khác hẳn dữ liệu gốc dễ gây bất ngờ. Ngoài ra, `toString()` mặc định có thể hiển thị các component lưu bên trong, nên **không dùng một accessor che dữ liệu làm biện pháp duy nhất để bảo vệ bí mật**; với dữ liệu nhạy cảm, cần cân nhắc cả cách lưu, log, `toString` và API của kiểu.

Nếu chỉ muốn chuẩn hóa chữ hoa/thường, khoảng trắng hay kiểm tra miền giá trị, constructor thường là nơi thích hợp hơn:

```java
import java.util.Locale;
import java.util.Objects;

record CountryCode(String value) {
    CountryCode {
        value = Objects.requireNonNull(value).strip().toUpperCase(Locale.ROOT);
    }
}
```

Giờ `new CountryCode(" vn ").value()` trả `"VN"` và giá trị đã chuẩn hóa cũng chính là trạng thái được lưu.

## 8. Component và interface: accessor có thể thực hiện hợp đồng sẵn có

Một record có thể `implements` interface. Nếu tên và chữ ký phương thức trùng accessor component, accessor được sinh ra đủ để thực hiện phương thức interface.

```java
interface Named {
    String name();
}

record Customer(String name, long id) implements Named {}

class Demo {
    public static void main(String[] args) {
        Named n = new Customer("An", 101L);
        System.out.println(n.name()); // An
    }
}
```

Không cần viết thêm phương thức `public String name()` vào `Customer`.

Ngược lại, nếu interface yêu cầu `getName()`:

```java
interface BeanNamed {
    String getName();
}
```

record với component `name` **không tự triển khai** `getName()`. Có thể viết phương thức chuyển tiếp khi cần tương tác với API đó:

```java
record Customer(String name) implements BeanNamed {
    public String getName() {
        return name();
    }
}
```

Đây là phương thức lập trình viên thêm thủ công. Compiler vẫn sinh accessor `name()` từ component.

Điểm này quan trọng khi tích hợp framework hoặc thư viện chỉ nhận kiểu getter truyền thống: cần xem thư viện có hỗ trợ Java records hay không, và API của nó mong đợi dạng phương thức nào.

## 9. Record component khác field và method như thế nào khi dùng Reflection?

Java 17 có API phản chiếu chuyên dụng cho record:

- `Class.isRecord()`: kiểm tra class có phải record không.
- `Class.getRecordComponents()`: lấy danh sách `RecordComponent` được khai báo trong header.
- `RecordComponent.getName()`, `getType()`, `getAccessor()`: xem tên, kiểu và phương thức accessor.

Ví dụ:

```java
import java.lang.reflect.RecordComponent;

record Address(String city, int zipCode) {}

class ReflectRecord {
    public static void main(String[] args) {
        Class<Address> type = Address.class;

        System.out.println(type.isRecord()); // true

        for (RecordComponent c : type.getRecordComponents()) {
            System.out.printf(
                    "component=%s, type=%s, accessor=%s%n",
                    c.getName(),
                    c.getType().getSimpleName(),
                    c.getAccessor().getName()
            );
        }
    }
}
```

Kết quả:

```text
true
component=city, type=String, accessor=city
component=zipCode, type=int, accessor=zipCode
```

**Phân biệt ba đối tượng phản chiếu:**

| API | Đại diện cho | Ví dụ |
|---|---|---|
| `RecordComponent` | Component khai báo trong header của record | `String city` |
| `Field` | Trường lưu dữ liệu trong class | `private final String city` |
| `Method` | Phương thức, gồm accessor | `public String city()` |

`RecordComponent` không phải `Field` và cũng không phải `Method`. Chúng liên hệ với nhau qua khai báo record, nhưng có API phản chiếu riêng.

Nếu `Class.getRecordComponents()` được gọi trên class không phải record, phương thức này trả về `null`; hãy dùng `isRecord()` khi xử lý class bất kỳ. Với record không có component, danh sách là mảng rỗng.

### 9.1. Annotation trên record component

Trong Java, annotation có thể nhắm riêng tới `RECORD_COMPONENT` hoặc tới field, method và parameter. Tùy `@Target`, một annotation viết ở component có thể xuất hiện ở những phần tử được sinh ra tương ứng theo quy tắc lan truyền annotation của Java 17.

Ví dụ annotation cho chính component:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.RECORD_COMPONENT)
@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}

record Customer(@Label("Mã khách hàng") String id) {}
```

Có thể truy vấn `Label` qua `Customer.class.getRecordComponents()[0]`. Vì annotation ở ví dụ trên chỉ nhắm `RECORD_COMPONENT`, không nên giả định nó tự xuất hiện ở `Field` hoặc `Method`; điều đó phụ thuộc `@Target` và quy tắc liên quan.

Đây là lý do một thư viện làm việc với record có thể xem component metadata thay vì chỉ tìm tên field hay getter.

## 10. Những gì record tự sinh và những gì không tự sinh

| Thành phần | Có tự sinh từ component? | Ghi chú |
|---|---|---|
| `private final` instance field | Có | Một field cho mỗi component |
| Accessor `componentName()` | Có | `public`, trả về kiểu component |
| Canonical constructor | Có nếu không tự khai báo | Tham số theo thứ tự component |
| `equals(Object)` | Có nếu không tự khai báo | Dựa trên trạng thái components |
| `hashCode()` | Có nếu không tự khai báo | Nhất quán với `equals` |
| `toString()` | Có nếu không tự khai báo | Biểu diễn tên record và components |
| `getName()`/`isActive()` JavaBeans | **Không** | Phải tự viết nếu thật sự cần |
| Setter `setName(...)` | **Không** | Field component là `final` |
| Defensive copy mảng/list mutable | **Không** | Phải thiết kế ở constructor/accessor |
| Kiểm tra `null`, miền giá trị | **Không** | Tự kiểm tra trong constructor nếu cần |
| Additional instance field | **Không được tự thêm** | Record chỉ giữ instance fields từ components |

Bảng trên phản ánh các quy tắc trong Java 17. Thư viện bổ sung hoặc cơ chế framework có thể tạo hành vi riêng, nhưng không thay đổi API cốt lõi của record.

## 11. Các lỗi thường gặp

### 11.1. Dùng cú pháp truy cập field thay cho accessor

```java
record Point(int x, int y) {}

class Demo {
    public static void main(String[] args) {
        Point p = new Point(1, 2);

        // Sai: x là private field của Point.
        // System.out.println(p.x);

        System.out.println(p.x()); // Đúng
    }
}
```

### 11.2. Tưởng record có getter JavaBeans

```java
record Person(String name) {}

class Demo {
    public static void main(String[] args) {
        Person p = new Person("Lan");

        // Sai: getName không do record tự sinh.
        // System.out.println(p.getName());

        System.out.println(p.name()); // Đúng
    }
}
```

### 11.3. Cố gán lại field `final`

```java
record Counter(int value) {
    void increase() {
        // Sai: không gán lại được field.
        // this.value++;
    }

    Counter increased() {
        return new Counter(value() + 1);
    }
}
```

Thay vì sửa tại chỗ, phương thức `increased()` tạo record mới.

### 11.4. Accessor tự viết có sai chữ ký

```java
// Sai: accessor phải có cùng kiểu trả về với component.
// record Price(long cents) {
//     public int cents() {
//         return 0;
//     }
// }
```

Đúng:

```java
record Price(long cents) {
    public long cents() {
        return cents;
    }
}
```

Không thể dùng accessor mặc định `cents()` để đồng thời thay đổi kiểu dữ liệu public API từ `long` sang `int`; nếu cần chuyển đổi, viết **một phương thức khác tên**, ví dụ `intValueExact()` với xử lý tràn số phù hợp.

### 11.5. Thiếu `public` trên accessor tường minh

```java
// Sai: explicit accessor phải là public.
// record Person(String name) {
//     String name() {
//         return name;
//     }
// }
```

Đúng:

```java
record Person(String name) {
    public String name() {
        return name;
    }
}
```

### 11.6. Giữ reference mutable mà tưởng dữ liệu được khóa

```java
record Holder(StringBuilder data) {}

StringBuilder buffer = new StringBuilder("A");
Holder holder = new Holder(buffer);

buffer.append("B");

System.out.println(holder.data()); // AB
```

Field `data` vẫn trỏ đến cùng `StringBuilder`. `final` không chặn `append`. Nếu muốn trạng thái chuỗi bất biến, cách tốt hơn thường là component kiểu `String`, chuyển dữ liệu thành `String` ngay lúc tạo record.

### 11.7. Thay đổi component nhưng quên thứ tự canonical constructor

```java
record Position(int row, int column) {}

Position p = new Position(2, 5);
```

Hai tham số đều là `int` nên đảo nhầm `(5, 2)` **vẫn biên dịch được**, nhưng ý nghĩa dữ liệu sai. Khi component có cùng kiểu, nên dùng tên biến rõ nghĩa hoặc factory method nếu API phức tạp.

## 12. Ví dụ hoàn chỉnh: bản ghi người học Java 17

Tạo tệp `RecordDemo.java`:

```java
import java.util.List;
import java.util.Objects;

record Student(String id, String fullName, List<String> courses) {
    Student {
        id = Objects.requireNonNull(id, "id").strip();
        fullName = Objects.requireNonNull(fullName, "fullName").strip();
        courses = List.copyOf(courses);

        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (fullName.isBlank()) {
            throw new IllegalArgumentException("fullName must not be blank");
        }
    }

    int numberOfCourses() {
        return courses().size();
    }

    Student withFullName(String newFullName) {
        return new Student(id(), newFullName, courses());
    }
}

public class RecordDemo {
    public static void main(String[] args) {
        Student a = new Student(
                "  S001  ",
                "  Minh  ",
                List.of("Java 17", "SQL")
        );

        System.out.println(a.id());
        System.out.println(a.fullName());
        System.out.println(a.courses());
        System.out.println(a.numberOfCourses());

        Student b = a.withFullName("Minh Anh");

        System.out.println(a.fullName());
        System.out.println(b.fullName());
        System.out.println(a.equals(b));
        System.out.println(a);
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 RecordDemo.java
java RecordDemo
```

Đầu ra:

```text
S001
Minh
[Java 17, SQL]
2
Minh
Minh Anh
false
Student[id=S001, fullName=Minh, courses=[Java 17, SQL]]
```

Các ý chính trong ví dụ:

1. Header của `Student` khai báo ba component `id`, `fullName` và `courses`.
2. Compiler sinh các field tương ứng `private final` và các accessor `id()`, `fullName()`, `courses()`.
3. Compact constructor kiểm tra đầu vào, chuẩn hóa chuỗi và chụp bản sao danh sách bằng `List.copyOf`.
4. Phương thức `numberOfCourses()` bổ sung hành vi nhưng không làm thay đổi số lượng component.
5. `withFullName(...)` trả về **record mới**, nên `a` không đổi.
6. `equals` và `toString` mặc định căn cứ các giá trị component sau khi constructor đã chuẩn hóa.

## 13. Bài tập tự luyện

### Bài 1 — Xác định accessor và field

Cho:

```java
record Ticket(long number, String owner, boolean used) {}
```

Hãy cho biết:

- Có bao nhiêu component?
- Tên và kiểu của ba field được compiler sinh?
- Cần gọi phương thức nào để đọc trạng thái `used`?
- `ticket.isUsed()` có được sinh tự động không?

**Đáp án:** ba component; field lần lượt có kiểu `private final long number`, `private final String owner`, `private final boolean used`; truy cập qua `ticket.used()`; không có `isUsed()` mặc định.

### Bài 2 — Chọn cách cập nhật đúng

Cho:

```java
record Temperature(double celsius) {}

Temperature t1 = new Temperature(24.5);
```

Muốn tạo nhiệt độ mới bằng 25 độ C, viết:

```java
Temperature t2 = new Temperature(25.0);
```

Không sửa field của `t1`. Nếu cần một phương thức tiện ích, có thể thêm:

```java
record Temperature(double celsius) {
    Temperature withCelsius(double value) {
        return new Temperature(value);
    }
}
```

### Bài 3 — Tại sao `final` vẫn thay đổi được dữ liệu?

Cho:

```java
record Tags(String[] values) {}

String[] data = {"a", "b"};
Tags tags = new Tags(data);
data[0] = "x";
```

**Đáp án:** record giữ tham chiếu `final` đến mảng `data` nhưng không sao chép mảng và không ngăn thay đổi phần tử. `tags.values()[0]` sẽ là `"x"`. Muốn ngăn sửa từ bên ngoài thì sao chép dữ liệu tại constructor và tại accessor, hoặc dùng kiểu danh sách bất biến phù hợp.

### Bài 4 — Viết compact constructor

Mục tiêu: record `Age(int years)` từ chối giá trị âm.

```java
record Age(int years) {
    Age {
        if (years < 0) {
            throw new IllegalArgumentException("years < 0");
        }
    }
}
```

Không cần tự viết `this.years = years`. Phép gán cho field `private final` diễn ra ngầm định sau khi body compact constructor kết thúc bình thường.

## 14. Cách ghi nhớ

Khi đọc `record R(Type component)`, hãy liên hệ ba thành phần cốt lõi:

```text
record R(Type component) {}
        │
        ├── component trong record header
        │
        ├── private final Type component;   (field lưu giá trị)
        │
        ├── public Type component();        (accessor đọc giá trị)
        │
        └── R(Type component)               (canonical constructor)
```

- **Component** là khai báo cấu trúc dữ liệu.
- **`private final` field** giữ trạng thái một lần sau khởi tạo và không cho gán lại tham chiếu/giá trị.
- **Accessor `component()`** là phương thức công khai để lấy giá trị; không có getter JavaBeans mặc định.
- **`final` không đồng nghĩa với bất biến sâu**. Với mảng, list hoặc object mutable, phải quyết định rõ có cần defensive copy hay không.
- **Constructor** là nơi phù hợp để kiểm tra và chuẩn hóa dữ liệu trước khi được lưu.

## Tài liệu tham khảo chính thức

- [JEP 395 — Records: tính năng chính thức từ Java 16](https://openjdk.org/jeps/395)
- [Java Language Specification 17, `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10)
- [JLS 17, `8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1)
- [JLS 17, `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3)
- [JLS 17, `8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4)
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)
- [Java SE 17 API — `java.lang.reflect.RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html)

