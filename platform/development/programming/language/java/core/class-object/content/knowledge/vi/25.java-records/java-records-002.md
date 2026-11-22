# Khai báo thành phần và các thành viên được sinh tự động của Java record

## 1. Record là gì và bài này tập trung vào điều gì?

Từ Java 16, `record` là một kiểu khai báo class chuyên mô hình hóa **một giá trị dữ liệu được mô tả bằng danh sách thành phần cố định** (*record components*). Java 17 đã hỗ trợ record như một tính năng chính thức và ổn định.

Ví dụ:

```java
record Student(String name, int age) {
}
```

Đây là khai báo một **record class** tên `Student` có đúng **hai record components**:

- `String name`: thành phần kiểu String tên `name`.
- `int age`: thành phần kiểu int tên `age`.

Từ một khai báo ngắn này, trình biên dịch tạo các thành viên có thể quan sát được như:

- Hai **instance fields** tương ứng: `private final String name` và `private final int age`.
- Hai **public accessor methods**: `String name()` và `int age()`.
- Một **canonical constructor** nhận các đối số theo thứ tự header: `Student(String name, int age)`.
- Implementations cho `equals(Object)`, `hashCode()` và `toString()`, trừ khi bạn tự khai báo những phương thức được phép thay thế.

Record vẫn là một **class**, có thể có methods, static fields, static methods và implement interfaces theo các quy tắc của nó. Nhưng nó không được dùng như một mutable class tùy ý: component fields là `final`, không cho khai báo instance fields bổ sung và không cho extends một class tự chọn.

> **Câu chốt:** Record header không chỉ là danh sách tham số constructor. Nó là **mô tả trạng thái dữ liệu cốt lõi của record**, làm cơ sở cho fields, accessors, canonical constructor và các phương thức value-oriented.

Bài này tập trung chính xác vào **khai báo record components và các thành viên được sinh tự động**, cách xem/định nghĩa lại chúng, các trường hợp có mutable components và những lỗi phổ biến. Các ví dụ ưu tiên Java 17+ và đều ghi rõ tệp, lệnh biên dịch, output khi là chương trình đầy đủ.

## 2. Chạy chương trình record đầu tiên

Tạo tệp **`RecordBasicsDemo.java`**:

```java
record Student(String name, int age) {
}

public class RecordBasicsDemo {
    public static void main(String[] args) {
        Student student = new Student("An", 20);

        System.out.println(student.name());
        System.out.println(student.age());
        System.out.println(student);
    }
}
```

Biên dịch và chạy:

```bash
javac RecordBasicsDemo.java
java RecordBasicsDemo
```

**Standard output:**

```text
An
20
Student[name=An, age=20]
```

### Đọc kết quả

1. `new Student("An", 20)` gọi canonical constructor có chữ ký phù hợp với record header.
2. `student.name()` gọi component accessor `name()`. Đây **không phải** `getName()` do compiler sinh.
3. `student.age()` gọi component accessor `age()`.
4. `System.out.println(student)` gọi `toString()` được record cung cấp, hiển thị tên record và các tên/giá trị components.

**Điều compiler không tự tạo:** `getName()`, `getAge()`, `setName(...)` hoặc `setAge(...)` kiểu JavaBean. Nếu bạn cần JavaBean naming cho thư viện cụ thể, đó là một yêu cầu tích hợp khác; record accessors mặc định luôn có tên **giống component**.

## 3. Đọc cú pháp record declaration

Một khai báo tổng quát có dạng:

```java
record RecordName(TypeA first, TypeB second) {
    // Các members được phép của record.
}
```

Đây là **mẫu minh họa**, `TypeA` và `TypeB` đại diện cho các kiểu hợp lệ phải được định nghĩa khi sử dụng.

Cấu trúc:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `record` | Từ khóa khai báo record class |
| `RecordName` | Tên type |
| `(...)` ngay sau tên | Record header |
| `TypeA first` | Record component thứ nhất |
| `TypeB second` | Record component thứ hai |
| `{ ... }` | Thân record class để thêm các thành viên hợp lệ |
| `;` sau khai báo | Không bắt buộc cho class/record declaration |

Các components có **thứ tự**, tên và kiểu xác định. Thứ tự này dùng cho tham số của canonical constructor và cho APIs quan sát cấu trúc record.

### Record có thể có không thành phần

```java
record Empty() {
}
```

Đây là khai báo hợp lệ. Nó mô tả một record không có component state; canonical constructor không tham số và các component accessors không tồn tại vì không có components.

**Nhưng hãy chọn theo domain:** Nếu chỉ cần một hằng không dữ liệu, singleton/enum có thể rõ ràng hơn. Record rỗng hợp lý khi một **giá trị kiểu cụ thể** cần tham gia API mà không mang component data.

## 4. Từ header sang fields: `private final` là điểm cốt lõi

Xét:

```java
record Point(int x, int y) {
}
```

Compiler tạo fields tương ứng với hai components có bản chất:

```java
private final int x;
private final int y;
```

Đây là **mảnh mô phỏng**, không phải yêu cầu viết lại hai fields trong record body. Trong khai báo record **không được khai báo instance fields bổ sung**.

### Ý nghĩa của hai modifiers

- `private`: code bên ngoài không truy cập trực tiếp `point.x` theo cơ chế field access thông thường; thay vào đó dùng `point.x()`.
- `final`: mỗi component field được gán trong quá trình xây dựng object và **không được gán lại sau khi đã khởi tạo**.

Tạo **`RecordFinalFieldsDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordFinalFieldsDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(5, 8);

        System.out.println(first.x() + "," + first.y());
        System.out.println(second.x() + "," + second.y());

        // first.x = 10; // Không hợp lệ: private final field.
        // first.x(10);  // Không có setter x(int).
    }
}
```

```bash
javac RecordFinalFieldsDemo.java
java RecordFinalFieldsDemo
```

```text
2,3
5,8
```

Cả hai instances có state riêng. Không thể sửa component `x` ở một Point đã tạo bằng assignment. Muốn một giá trị mới, tạo **record instance mới** từ những values mới.

**Không nhầm:** `final` trên reference field chỉ cố định reference, không nhất thiết làm object được tham chiếu bên trong bất biến. Phần sau có ví dụ mảng/danh sách.

## 5. Accessors: tên giống component, không có tiền tố `get`

Mỗi record component `foo` có một accessor method `foo()`. Ví dụ:

```java
record User(String username, boolean active) {
}
```

Compiler cung cấp:

```java
public String username();
public boolean active();
```

Hai dòng là **method signatures minh họa**, không phải declarations cần chép vào body.

Không tự sinh:

```java
// public String getUsername();
// public boolean isActive();
// public void setActive(boolean value);
```

### Ví dụ callable

Tạo **`RecordAccessorNamesDemo.java`**:

```java
record User(String username, boolean active) {
}

public class RecordAccessorNamesDemo {
    public static void main(String[] args) {
        User user = new User("an", true);

        System.out.println(user.username());
        System.out.println(user.active());

        // user.getUsername(); // Không được sinh.
        // user.isActive();    // Không được sinh.
    }
}
```

```bash
javac RecordAccessorNamesDemo.java
java RecordAccessorNamesDemo
```

```text
an
true
```

**Vì sao quan trọng?** Một số frameworks cũ nhận dạng properties thông qua JavaBeans getters. Record có API riêng, nên phải kiểm framework có hỗ trợ record/component introspection hay yêu cầu adapter/custom mapping.

## 6. Canonical constructor được sinh theo record header

Record:

```java
record Rectangle(int width, int height) {
}
```

có canonical constructor tương ứng các components:

```java
Rectangle(int width, int height)
```

Đây là **chữ ký khái niệm**; access level do quy tắc canonical constructor và record declaration quyết định.

Canonical constructor dùng để thiết lập state cho đúng mỗi component, theo đúng thứ tự header. Ví dụ:

```java
new Rectangle(4, 6);
```

truyền `width=4`, `height=6`.

Tạo **`RecordConstructorDemo.java`**:

```java
record Rectangle(int width, int height) {
}

public class RecordConstructorDemo {
    public static void main(String[] args) {
        Rectangle r = new Rectangle(4, 6);

        System.out.println(r.width());
        System.out.println(r.height());
        System.out.println(r.width() * r.height());
    }
}
```

```bash
javac RecordConstructorDemo.java
java RecordConstructorDemo
```

```text
4
6
24
```

**Nếu không khai báo constructor**, compiler tạo canonical constructor phù hợp với header. Nếu tự khai báo explicit canonical hoặc compact constructor, bạn chịu trách nhiệm đảm bảo invariants, nhưng quy tắc khởi tạo component fields vẫn được Java thực thi.

## 7. Generated `equals(Object)`: so giá trị các components

Một record được thiết kế để mang giá trị dữ liệu. Khi bạn không khai báo `equals`, compiler cung cấp cách so sánh dựa trên toàn bộ components của record type.

Tạo **`RecordEqualityDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordEqualityDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point c = new Point(2, 4);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.equals(null));
    }
}
```

```bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
```

```text
false
true
false
false
```

**Diễn giải:**

- `a == b` là false vì được tạo bằng hai lần `new` và là hai object references riêng.
- `a.equals(b)` true vì cùng record class và hai components x,y bằng nhau.
- `a.equals(c)` false vì y khác nhau.
- `a.equals(null)` false.

Đây là **equality theo component state**, không đồng nghĩa record fields được copy sâu. Cũng không có chuyện record instances equal buộc phải là cùng object.

### Cẩn thận về so sánh reference components

Với component là object, cách so sánh dựa trên loại giá trị component; ví dụ String có content equality, còn array dùng reference identity khi không tự custom logic. Không kết luận generated equals sẽ đệ quy so mọi object graph theo mong muốn nghiệp vụ.

## 8. `hashCode()` được tạo nhất quán với `equals()`

Compiler cung cấp `hashCode()` dựa trên components, theo contract: hai record instances equal phải có hashCode bằng nhau.

Tạo **`RecordHashCodeDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordHashCodeDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point c = new Point(2, 4);

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a.equals(c));
    }
}
```

```bash
javac RecordHashCodeDemo.java
java RecordHashCodeDemo
```

```text
true
true
false
```

**Không in một số hash cụ thể để coi là output chuẩn.** Hash code không phải khóa ID nghiệp vụ hay mã lưu trữ ổn định giữa mọi phiên bản/implementation. Hai object không equal vẫn có thể có hash collision.

### Record làm key của HashMap

Một record có components phù hợp và bất biến về logical value thường là ứng viên tốt cho map key. Nhưng nếu component tham chiếu một mutable object có ảnh hưởng tới equals/hashCode, việc mutate object ấy sau khi dùng làm key có thể làm hành vi lookup khó dự đoán.

**Rule thực tiễn:** Những components góp phần vào equality/hashCode nên có **ngữ nghĩa giá trị ổn định** khi record được dùng làm key.

## 9. `toString()` được sinh để hiển thị dạng có tên component

Record có `toString()` theo dạng:

```text
RecordName[component1=value1, component2=value2]
```

Đây là **mẫu output**, giá trị cụ thể do instance quyết định.

Tạo **`RecordToStringDemo.java`**:

```java
record Book(String title, int pages, boolean published) {
}

public class RecordToStringDemo {
    public static void main(String[] args) {
        Book book = new Book("Java", 300, true);

        System.out.println(book);
    }
}
```

```bash
javac RecordToStringDemo.java
java RecordToStringDemo
```

```text
Book[title=Java, pages=300, published=true]
```

`toString()` thuận tiện khi debug, nhưng không mặc định là **JSON**, không có escaping/serialization contract phù hợp mọi trường hợp và có thể để lộ component nhạy cảm nếu log không kiểm soát.

**Một điểm quan trọng:** Với array component, `toString()` có thể dùng biểu diễn object array mặc định chứ không nhất thiết in nội dung đẹp kiểu `[1, 2]`. Muốn output điều chỉnh, tự implement toString đúng contract ứng dụng.

## 10. Mối quan hệ giữa ba phương thức sinh tự động

| Phương thức | Vai trò | Nguồn ngữ nghĩa mặc định |
| --- | --- | --- |
| `equals(Object)` | So sánh value theo record components | Components và types |
| `hashCode()` | Hash nhất quán với equals | Components |
| `toString()` | Hiển thị tên record/components | Components và giá trị hiển thị |

Ba methods này phục vụ **các mục tiêu khác nhau**. Một record có thể override riêng chúng, nhưng nếu override equals/hashCode phải giữ general contracts của Object.

**Không suy rằng** toString giống nhau thì hai record equal, hoặc hashCode giống nhau thì equal. Nội dung display và hash collisions không phải chứng cứ đủ.

## 11. Tổng hợp generated members trên một record

Tạo **`RecordGeneratedSummaryDemo.java`**:

```java
record Employee(String id, int grade) {
}

public class RecordGeneratedSummaryDemo {
    public static void main(String[] args) {
        Employee first = new Employee("E-1", 3);
        Employee duplicate = new Employee("E-1", 3);

        System.out.println(first.id());
        System.out.println(first.grade());

        System.out.println(first.equals(duplicate));
        System.out.println(
                first.hashCode() == duplicate.hashCode());
        System.out.println(first.toString());
    }
}
```

```bash
javac RecordGeneratedSummaryDemo.java
java RecordGeneratedSummaryDemo
```

```text
E-1
3
true
true
Employee[id=E-1, grade=3]
```

Không có method body tự viết trong Employee nhưng đã có constructor, accessors và Object-related implementations để dùng.

**Sự tiết kiệm không chỉ là ít dòng:** Vì các methods đều được suy ra từ **cùng record header**, một component mới trở thành thành phần của canonical constructor, equality, hash và display theo quy tắc record. Điều đó giảm nguy cơ developer quên thêm field vào equals/hashCode so với một mutable data class viết tay.

## 12. Record component khác local variable hay getter đơn thuần

Xét:

```java
record Score(int points) {
    int doubled() {
        return points * 2;
    }
}
```

`points` là **record component**; compiler tạo một field tương ứng và accessor `points()`. Method `doubled()` là một **instance method bổ sung** do bạn khai báo, không phải record component.

Vì vậy:

- `Score.points()` không phải một static method.
- `score.points()` trả component state.
- `score.doubled()` tính một derived value.
- `doubled` không được tự thêm vào `equals/hashCode/toString` như một component mới.

**Ranh giới:** Chỉ những khai báo trong record header tạo thành record components. Methods trong body không biến thành components ngay cả khi trả về dữ liệu quan trọng.

## 13. Instance methods bổ sung là hợp lệ

Một record không chỉ là “dữ liệu trơ”. Bạn có thể viết methods tính giá trị dẫn xuất mà không lưu thêm state.

Tạo **`RecordDerivedMethodDemo.java`**:

```java
record Rectangle(int width, int height) {
    int area() {
        return Math.multiplyExact(width, height);
    }

    boolean isSquare() {
        return width == height;
    }
}

public class RecordDerivedMethodDemo {
    public static void main(String[] args) {
        Rectangle a = new Rectangle(3, 4);
        Rectangle b = new Rectangle(5, 5);

        System.out.println(a.area());
        System.out.println(a.isSquare());
        System.out.println(b.area());
        System.out.println(b.isSquare());
    }
}
```

```bash
javac RecordDerivedMethodDemo.java
java RecordDerivedMethodDemo
```

```text
12
false
25
true
```

Methods `area` và `isSquare` hoạt động trên components được lưu. Không cần field mới như `private int areaCache`; record cấm thêm instance field ngoài components.

`Math.multiplyExact` ném `ArithmeticException` khi integer multiplication overflow, tránh việc trả giá trị sai âm thầm nếu diện tích vượt `int`.

## 14. Record không tự validate dữ liệu chỉ vì là record

Generated canonical constructor **nhận và lưu arguments**, nhưng nó không tự biết nghiệp vụ của bạn yêu cầu gì.

Ví dụ:

```java
record Age(int value) {
}
```

Bạn vẫn có thể gọi `new Age(-5)` nếu không có validation.

Một cách rõ ràng là khai báo **compact canonical constructor** để thêm kiểm tra.

Tạo **`RecordValidationDemo.java`**:

```java
record Age(int value) {
    Age {
        if (value < 0 || value > 150) {
            throw new IllegalArgumentException(
                    "age out of range");
        }
    }
}

public class RecordValidationDemo {
    public static void main(String[] args) {
        Age valid = new Age(20);
        System.out.println(valid.value());

        try {
            new Age(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid age");
        }
    }
}
```

```bash
javac RecordValidationDemo.java
java RecordValidationDemo
```

```text
20
invalid age
```

**Compact constructor** `Age { ... }` không khai báo lại danh sách parameters; Java lấy canonical parameters từ header. Sau phần body, compiler đảm nhiệm việc gán component fields bằng values của parameters (có thể được chuẩn hóa trong body).

Không đánh đồng record với một hệ thống bean validation đầy đủ: domain invariants vẫn phải được lập trình hoặc cấu hình bằng giải pháp phù hợp.

## 15. Compact constructor có thể chuẩn hóa parameter

Một compact constructor có thể **gán lại parameter** trước khi Java lưu nó vào final component field, chẳng hạn trim String.

Tạo **`RecordNormalizationDemo.java`**:

```java
import java.util.Objects;

record Username(String value) {
    Username {
        value = Objects.requireNonNull(value).trim();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "username is blank");
        }
    }
}

public class RecordNormalizationDemo {
    public static void main(String[] args) {
        Username username = new Username("  An  ");

        System.out.println(username.value());
        System.out.println(username);
    }
}
```

```bash
javac RecordNormalizationDemo.java
java RecordNormalizationDemo
```

```text
An
Username[value=An]
```

Ở constructor body, `value` là **parameter** của canonical constructor, có thể được chuẩn hóa. Khi compact constructor body kết thúc bình thường, Java gán parameter value cuối cùng vào field final tương ứng.

**Không viết `this.value = value` bên trong compact constructor body**. Java cấm assignment trực tiếp tới component field trong compact constructor vì cơ chế gán được compiler thực hiện. Nếu cần explicit assignment control, xem explicit canonical constructor.

## 16. Explicit canonical constructor và yêu cầu gán đủ components

Bạn cũng có thể tự viết một constructor đầy đủ theo đúng kiểu, tên và thứ tự parameters của header.

Tạo **`ExplicitCanonicalRecordDemo.java`**:

```java
import java.util.Objects;

record Product(String sku, int quantity) {
    Product(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku).trim();

        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "negative quantity");
        }
        this.quantity = quantity;
    }
}

public class ExplicitCanonicalRecordDemo {
    public static void main(String[] args) {
        Product product = new Product(" A-1 ", 4);

        System.out.println(product.sku());
        System.out.println(product.quantity());
        System.out.println(product);
    }
}
```

```bash
javac ExplicitCanonicalRecordDemo.java
java ExplicitCanonicalRecordDemo
```

```text
A-1
4
Product[sku=A-1, quantity=4]
```

**Khác compact constructor:**

- `Product(String sku, int quantity)` khai báo đầy đủ canonical parameters.
- Bạn có trách nhiệm assign mỗi component field đúng một lần theo definite-assignment rules.
- `this.sku` và `this.quantity` được phép gán trong **explicit canonical constructor**.
- Cách này dài hơn, có ích khi phải kiểm soát logic khởi tạo chi tiết.
- Compact constructor thường gọn hơn khi chỉ validate/normalize parameters.

**Visibility:** Canonical constructor phải có mức truy cập phù hợp với record declaration; không thể cố ý thu hẹp quyền truy cập theo cách vi phạm quy tắc record. Với public record, dùng public canonical constructor.

## 17. So sánh hai dạng canonical constructor

| Đặc điểm | Compact constructor | Explicit canonical constructor |
| --- | --- | --- |
| Cú pháp | `RecordName { ... }` | `RecordName(Type a, Type b) { ... }` |
| Danh sách parameters | Lấy từ header | Viết đầy đủ khớp header |
| Cách lưu component fields | Compiler gán sau body | Body phải gán fields rõ ràng |
| Được chuẩn hóa parameters? | Có, trước implicit assignment | Có, qua logic explicit |
| Được `this.field = ...`? | Không với component field | Có nếu definite-assignment đúng |
| Phù hợp | Validation/normalization ngắn | Logic khởi tạo tường minh hơn |

Không khai báo **đồng thời cả compact canonical constructor và explicit canonical constructor** cho cùng record, vì chúng đại diện cùng một canonical constructor.

## 18. Constructor khác canonical phải ủy quyền qua `this(...)`

Record có thể có **overloaded constructors**, nhưng non-canonical constructor phải ủy quyền tới constructor khác của chính record, cuối cùng đi đến canonical constructor.

Tạo **`RecordOverloadedConstructorDemo.java`**:

```java
record Point(int x, int y) {
    Point(int both) {
        this(both, both);
    }

    Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException(
                    "negative coordinate");
        }
    }
}

public class RecordOverloadedConstructorDemo {
    public static void main(String[] args) {
        Point a = new Point(4);
        Point b = new Point(2, 3);

        System.out.println(a);
        System.out.println(b);
    }
}
```

```bash
javac RecordOverloadedConstructorDemo.java
java RecordOverloadedConstructorDemo
```

```text
Point[x=4, y=4]
Point[x=2, y=3]
```

`Point(int both)` gọi `this(both,both)`, sau đó canonical/compact constructor đảm bảo components được khởi tạo và validate.

**Không cho overloaded constructor tự ý gán lại component fields như một mutable class thường.** Mọi đường tạo record instance phải đi qua canonical initialization theo quy tắc record.

## 19. Override accessor: có thể, nhưng phải giữ đúng contract

Mặc định Java tạo `public Type componentName()`. Nếu bạn khai báo accessor tường minh, nó phải có **cùng tên component, return type phù hợp và không có parameters**, với access/public contract hợp lệ.

Một ví dụ hợp lệ: dùng accessor để trả snapshot của mảng mutable.

Tạo **`RecordCustomAccessorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Samples(int[] values) {
    Samples {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}

public class RecordCustomAccessorDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        Samples samples = new Samples(source);
        source[0] = 9;

        int[] returned = samples.values();
        returned[1] = 8;

        System.out.println(
                Arrays.toString(samples.values()));
        System.out.println(
                Arrays.toString(source));
    }
}
```

```bash
javac RecordCustomAccessorDemo.java
java RecordCustomAccessorDemo
```

```text
[1, 2]
[9, 2]
```

- Compact constructor **clone input array**, không giữ reference source.
- Accessor override **clone output array**, không lộ internal array.
- Component field thực sự vẫn là `private final int[] values`, nhưng content array mutable được bảo vệ bằng defensive copying ở hai ranh giới.
- `@Override` ở accessor dùng để chỉ method explicit thay accessor ngầm định; nếu compiler không chấp nhận override do sai signature, cần sửa method declaration.

**Cảnh báo thiết yếu:** Generated equals/hashCode đối với array component vẫn dựa trên array reference identity semantics, không tự so sâu contents. Phần sau phân tích riêng.

## 20. Record mặc định chỉ bất biến nông (*shallowly immutable*)

Record components là final fields, nhưng nếu component type là mutable object, bản thân object ấy vẫn có thể bị thay đổi.

Tạo **`RecordMutableArrayDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {
}

public class RecordMutableArrayDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        Numbers n = new Numbers(source);
        source[0] = 9;

        System.out.println(
                Arrays.toString(n.values()));

        n.values()[1] = 8;

        System.out.println(
                Arrays.toString(source));
    }
}
```

```bash
javac RecordMutableArrayDemo.java
java RecordMutableArrayDemo
```

```text
[9, 2]
[9, 8]
```

**Vì sao?**

- Final field `values` không được gán sang mảng khác sau construction.
- Nhưng generated constructor **không clone mảng**; nó giữ reference tới `source`.
- Generated accessor `values()` trả đúng internal array reference, không tạo copy.
- Thay `source[0]` hoặc `n.values()[1]` đều mutate **cùng array object**.

Do đó câu “record là immutable” chỉ chính xác nếu **component values thật sự immutable hoặc được phòng vệ và không có state mutable được lộ ra**. Đừng suy rằng mọi object graph reachable từ record đều bất biến.

## 21. Record với `List`: cấu trúc và phần tử cần kiểm riêng

Tạo **`RecordListAliasDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
}

public class RecordListAliasDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Team team = new Team(input);
        input.add("Binh");

        System.out.println(team.members());

        team.members().add("Chi");
        System.out.println(input);
    }
}
```

```bash
javac RecordListAliasDemo.java
java RecordListAliasDemo
```

```text
[An, Binh]
[An, Binh, Chi]
```

Generated constructor và accessor không deep-copy List.

### Cách xử lý khi chỉ chứa immutable elements

Tạo **`RecordImmutableListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}

public class RecordImmutableListDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Team team = new Team(input);
        input.add("Binh");

        System.out.println(team.members());

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutable list view");
        }
    }
}
```

```bash
javac RecordImmutableListDemo.java
java RecordImmutableListDemo
```

```text
[An]
immutable list view
```

`List.copyOf` tạo unmodifiable snapshot của mutable input list structure. Vì các elements là `String` immutable, thiết kế này có semantics immutable phù hợp cho danh sách thành viên trong ví dụ.

**Không khái quát quá mức:** Nếu `members` là `List<StringBuilder>`, `List.copyOf` không clone mỗi StringBuilder. Vẫn có thể mutate elements thông qua references khác. Phải xác định **độ sâu của immutable contract** theo loại components.

## 22. Generated `equals` với component mảng: giới hạn của member được sinh

Các methods do record sinh dựa trên **record components**, nhưng với reference tới array, equality không phải phép so từng phần tử. Hai mảng có nội dung giống nhau mà là hai object khác nhau vẫn không equal theo `Object.equals` của array:

~~~java
record Numbers(int[] values) {}

Numbers a = new Numbers(new int[]{1, 2});
Numbers b = new Numbers(new int[]{1, 2});
// a.equals(b) là false; java.util.Arrays.equals(a.values(), b.values()) là true.
~~~

Các phép tạo/gọi ở trên là **fragment đặt trong một method**, không phải Java file độc lập. Nếu cả hai record giữ đúng **cùng array reference**, generated equality có thể true, dù trạng thái mảng vẫn mutable.

Đây là ngoại lệ cần biết để không hiểu sai chữ **generated**. Bài **“equals(), hashCode(), toString() và ảnh hưởng của thành phần mảng”** là nơi kiểm chứng tất cả các trường hợp (array mới, shared reference, hash contract, two-dimensional arrays và Map/Set). `Arrays.equals` chỉ trả về giá trị boolean và **không** tự đổi behavior của `record.equals`; muốn content-based value semantics phải thiết kế override cả `equals` lẫn `hashCode` hoặc chọn representation bất biến khác.

## 23. Ví dụ record với custom content equality cho mảng

Tạo **`RecordArrayContentValueDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record IntVector(int[] values) {
    IntVector {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof IntVector vector
                    && Arrays.equals(values, vector.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "IntVector" + Arrays.toString(values);
    }
}

public class RecordArrayContentValueDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        IntVector a = new IntVector(input);
        IntVector b = new IntVector(new int[] {1, 2});

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        input[0] = 9;
        System.out.println(a);
        System.out.println(b);
    }
}
```

```bash
javac RecordArrayContentValueDemo.java
java RecordArrayContentValueDemo
```

```text
true
true
IntVector[1, 2]
IntVector[1, 2]
```

**Điểm thiết kế:**

- Compact constructor clone input để cắt alias.
- Accessor clone output để không lộ mutable internal state.
- `equals` và `hashCode` so theo contents.
- `toString` hiển thị contents theo policy ứng dụng.

Đây là trường hợp bạn **cố ý viết lại** generated methods vì representation cần logical value semantics khác với array reference equality.

**Giới hạn:** Nếu array có nested mutable elements hoặc giá trị mutable khác, phải xét deep copy/deep equals phù hợp. Ví dụ này chỉ là mảng `int[]`.

## 24. Có thể tự viết `equals`, `hashCode`, `toString`, nhưng phải nhất quán

Record cho phép bạn khai báo overrides của ba methods đặc biệt. Tuy nhiên, hãy cân nhắc:

- Vì sao mặc định không phù hợp?
- Bạn có định nghĩa equality dựa trên **tất cả dữ liệu cốt lõi** hay muốn một business identity khác?
- Nếu hai records equal, hashCode có chắc bằng nhau?
- Có mutable value nào khiến hashCode thay đổi sau khi dùng làm map key?
- `toString()` có vô tình làm rò credentials, tokens hoặc dữ liệu nhạy cảm?
- Các frameworks/serializers có mong chờ semantics header components không?

**Một hướng thay thế** là không dùng record khi class thật sự có **identity và lifecycle riêng**. Record thiên về transparent data carrier; nếu equality chỉ theo database ID còn các fields khác mutable, một entity class thông thường có thể diễn đạt đúng hơn.

## 25. Record có thể implement interface

Một record không được extends một user-defined class, nhưng có thể implement interfaces.

Tạo **`RecordInterfaceDemo.java`**:

```java
interface Named {
    String name();
}

record Person(String name, int age) implements Named {
}

public class RecordInterfaceDemo {
    static String display(Named value) {
        return "name=" + value.name();
    }

    public static void main(String[] args) {
        Person person = new Person("Lan", 25);

        System.out.println(display(person));
        System.out.println(person instanceof Named);
    }
}
```

```bash
javac RecordInterfaceDemo.java
java RecordInterfaceDemo
```

```text
name=Lan
true
```

Generated accessor `public String name()` của Person có signature tương thích với interface `Named.name()`. Vì vậy record có thể thỏa interface contract **ngay từ accessor tự sinh**, không cần code override thủ công.

Điều này hữu ích khi các APIs cần shared read-only views, nhưng mỗi record vẫn giữ bộ components của chính nó.

## 26. Record là class ngầm `final` và extends `java.lang.Record`

Một record class được coi là final; bạn không thể viết một class khác `extends Person` nếu Person là record. Nó extends `java.lang.Record` theo cơ chế ngôn ngữ, không phải `Object` trực tiếp như một class thường.

Đoạn **cố ý sai**:

```java
record Person(String name) {
}

// class Employee extends Person { } // Không hợp lệ.
```

Một record cũng không thể tự chọn `extends OtherBaseClass`. Đây là chủ đích: một record có tập state components cố định và transparent; subclass mở rộng thêm instance state có thể làm mờ semantics đó.

**Có thể dùng polymorphism bằng interface:** Nhiều records `implements SharedInterface` nhưng không extends lẫn nhau.

## 27. Những gì được phép trong record body?

| Loại thành viên | Có thể khai báo? | Ghi chú |
| --- | --- | --- |
| Instance method | Có | Có thể tính derived value |
| Explicit accessor | Có | Phải đúng contract component accessor |
| Compact canonical constructor | Có | Validation/normalization |
| Explicit canonical constructor | Có | Khớp header/assign components |
| Overloaded constructor | Có | Phải delegate qua `this(...)` |
| Static field | Có | Ví dụ constant/config, thận trọng state mutable |
| Static method | Có | Factory/helper methods |
| Static initializer | Có | Theo rules tương ứng |
| Nested class/interface/enum | Có | Theo rules của member declarations |
| Instance field ngoài header | **Không** | Component fields là instance fields duy nhất |
| Instance initializer block | **Không** | Record hạn chế khởi tạo instance |
| Tự extends một class khác | **Không** | Superclass là `java.lang.Record` |
| Để một class extends record | **Không** | Record là final |
| Abstract record | **Không** | Record không khai báo abstract |

### Ví dụ kết hợp instance và static methods

Tạo **`RecordFactoryDemo.java`**:

```java
record Temperature(int celsius) {
    static Temperature freezing() {
        return new Temperature(0);
    }

    int fahrenheit() {
        return celsius * 9 / 5 + 32;
    }
}

public class RecordFactoryDemo {
    public static void main(String[] args) {
        Temperature a = Temperature.freezing();
        Temperature b = new Temperature(20);

        System.out.println(a.fahrenheit());
        System.out.println(b.fahrenheit());
    }
}
```

```bash
javac RecordFactoryDemo.java
java RecordFactoryDemo
```

```text
32
68
```

`freezing()` là **static factory** do tác giả khai báo, không phải generated member. `fahrenheit()` là instance method bổ sung. Component `celsius` vẫn final.

## 28. Không khai báo instance field hoặc instance initializer

Đây là **mã sai có chú thích**:

```java
record Bad(int x) {
    // int counter; // Không hợp lệ: instance field ngoài components.

    // { System.out.println("init"); }
    // Không hợp lệ: instance initializer block.
}
```

Nếu cần state dẫn xuất `doubleX`, có những hướng:

- Tính từ `x` trong method: `int doubleX() { return 2 * x; }`.
- Thêm một component mới vào header nếu dữ liệu thực sự là **một phần transparent state**. Nhưng phải cân nhắc equality/hash/constructor vì tất cả chịu tác động.
- Dùng một ordinary class nếu cần nhiều instance fields, cache mutable và vòng đời riêng.

**Không dùng static field như cách lách giới hạn:** Static state được chia sẻ toàn type, không phải state riêng từng record object.

## 29. Record component có thể là primitive, reference, generic type

Ví dụ:

```java
record Coordinate(double latitude, double longitude) {
}

record Pair<A, B>(A first, B second) {
}

record Response<T>(int status, T body) {
}
```

Đây là **các khai báo hợp lệ minh họa**.

- Primitive components như int/double được lưu trực tiếp dưới dạng component value.
- Reference components như String/List có thể là null trừ khi constructor validate.
- Generic type parameters cho phép record mô hình một pair/response có kiểu linh hoạt.
- Generated methods vẫn dựa trên **các components được khai báo**, không sinh ra một kiểu member field mới cho generic arguments.

### Ví dụ generic record chạy được

Tạo **`GenericRecordDemo.java`**:

```java
record Pair<A, B>(A first, B second) {
}

public class GenericRecordDemo {
    public static void main(String[] args) {
        Pair<String, Integer> pair =
                new Pair<>("item", 5);

        System.out.println(pair.first());
        System.out.println(pair.second());
        System.out.println(pair);
    }
}
```

```bash
javac GenericRecordDemo.java
java GenericRecordDemo
```

```text
item
5
Pair[first=item, second=5]
```

Generic type safety hoạt động theo Java generics; không phải một cơ chế deep copy hay validation tự động cho reference components.

## 30. Record có thể là nested type hoặc local record

Một record có thể được khai báo lồng trong class hoặc trong block (Java 17). Nested/member records và local records có tính **implicitly static**, nên không tự giữ enclosing instance hay capture local variable như một non-static inner class.

Tạo **`NestedAndLocalRecordDemo.java`**:

```java
public class NestedAndLocalRecordDemo {
    record Pair(int left, int right) {
    }

    static int sum(int base) {
        record Delta(int amount) {
        }

        Delta delta = new Delta(3);
        return base + delta.amount();
    }

    public static void main(String[] args) {
        Pair pair = new Pair(2, 4);

        System.out.println(pair.left() + pair.right());
        System.out.println(sum(10));
    }
}
```

```bash
javac NestedAndLocalRecordDemo.java
java NestedAndLocalRecordDemo
```

```text
6
13
```

`Delta` là local record chỉ có tên trong block `sum`. Nó không capture `base` vào fields ngầm; code truyền `3` vào component `amount` rõ ràng. `base` được dùng bởi enclosing method ở phép cộng bên ngoài local record.

**Lưu ý:** Đừng nhầm local record với local class không static có thể capture effectively-final local variables; hai loại có quy tắc khác nhau.

## 31. Record components và thứ tự khai báo có ý nghĩa

Thứ tự header là một phần của constructor API và cách quan sát record components.

```java
record Pair(int first, int second) {
}
```

`new Pair(1,2)` gán first=1, second=2. Nếu bạn đổi thứ tự hoặc tên components, source-level API và serialized schemas/tooling có thể bị ảnh hưởng.

### Về generated equality/toString

- Equality so các components theo semantics record.
- String representation hiển thị theo tên và thứ tự components.
- Canonical constructor nhận parameters theo thứ tự record header.
- `Class.getRecordComponents()` phản ánh thứ tự khai báo components.

**Không xem rename/reorder components là refactor hoàn toàn vô hại**, nhất là khi các hệ thống bên ngoài dùng JSON/database mapping hoặc reflect record metadata.

## 32. Quan sát components qua reflection thay vì suy từ fields

Java có API `Class.getRecordComponents()` và `Class.isRecord()` để biết một type có phải record và các components của nó.

Tạo **`RecordReflectionDemo.java`**:

```java
import java.lang.reflect.RecordComponent;

record Point(int x, int y) {
}

public class RecordReflectionDemo {
    public static void main(String[] args) {
        Class<Point> type = Point.class;

        System.out.println(type.isRecord());

        for (RecordComponent component :
                type.getRecordComponents()) {
            System.out.println(component.getName() + ":"
                    + component.getType().getSimpleName());
        }
    }
}
```

```bash
javac RecordReflectionDemo.java
java RecordReflectionDemo
```

```text
true
x:int
y:int
```

**Vì sao dùng API này?** Frameworks và tools có thể nhận diện record structure một cách chuẩn thay vì đoán rằng class có các private final fields hoặc JavaBean getters. Một ordinary class cũng có thể có private final fields, nhưng **không trở thành record** vì vậy.

`getRecordComponents()` trả thông tin record components theo declaration order. Đối với class không phải record, API này trả null, nên code generic cần kiểm `isRecord()` hoặc xử lý null tương ứng.

## 33. Generated accessor có thể xem qua reflection

Một record component mô tả tên, kiểu và accessor method tương ứng. Phương thức `RecordComponent.getAccessor()` cho phép framework tìm accessor đúng contract.

Tạo **`RecordAccessorReflectionDemo.java`**:

```java
import java.lang.reflect.RecordComponent;

record User(String name, int age) {
}

public class RecordAccessorReflectionDemo {
    public static void main(String[] args) {
        for (RecordComponent component :
                User.class.getRecordComponents()) {
            System.out.println(component.getAccessor().getName());
        }
    }
}
```

```bash
javac RecordAccessorReflectionDemo.java
java RecordAccessorReflectionDemo
```

```text
name
age
```

**Điểm then chốt:** Accessor names là `name` và `age`, không phải `getName` hoặc `getAge`. Reflection metadata là một cách tiêu chuẩn để nhận biết record components.

**Không dùng reflection như biện pháp mặc định cho ứng dụng thường ngày** khi đã biết static type; gọi trực tiếp `user.name()` rõ hơn và type-safe hơn.

## 34. Đừng nhầm record với `java.lang.Record` object có thể dùng tùy ý

Mọi record class extends `java.lang.Record`, nhưng bạn không thể tự viết một ordinary class tùy ý `extends Record` để nó trở thành record.

**Khái niệm:**

- `record Person(...)` là cú pháp ngôn ngữ dành riêng cho record class.
- `java.lang.Record` là superclass đặc biệt của các record types.
- API `Class.isRecord()` phân biệt record class thực sự.
- Các generated members phụ thuộc vào **record declaration**, không chỉ vào superclass name.

Không nên dùng `java.lang.Record` làm kiểu dữ liệu chung cho domain nếu một interface rõ hơn thể hiện nhu cầu tốt hơn.

## 35. Record có thể override `toString()` để tránh lộ dữ liệu

Một record lưu thông tin nhạy cảm có thể cần display policy thận trọng. Generated toString thường nêu giá trị components, nên không phải mọi record nên được log trực tiếp.

Tạo **`RecordSafeDisplayDemo.java`**:

```java
record ApiCredential(String user, String token) {
    @Override
    public String toString() {
        return "ApiCredential[user=" + user
                + ", token=REDACTED]";
    }
}

public class RecordSafeDisplayDemo {
    public static void main(String[] args) {
        ApiCredential credential =
                new ApiCredential("service", "secret-value");

        System.out.println(credential);
        System.out.println(credential.user());
    }
}
```

```bash
javac RecordSafeDisplayDemo.java
java RecordSafeDisplayDemo
```

```text
ApiCredential[user=service, token=REDACTED]
service
```

**Giới hạn quan trọng:** Override toString **không bảo mật dữ liệu khỏi code có quyền truy cập accessor**: `credential.token()` vẫn trả token. Nếu data thật sự nhạy cảm, thiết kế quyền truy cập, lưu trữ và logging ở mức hệ thống; đừng dùng toString override làm biện pháp bảo mật duy nhất.

## 36. Null components: record không tự cấm null

Tạo **`RecordNullComponentDemo.java`**:

```java
record OptionalNote(String text) {
}

public class RecordNullComponentDemo {
    public static void main(String[] args) {
        OptionalNote note = new OptionalNote(null);

        System.out.println(note.text() == null);
        System.out.println(note);
    }
}
```

```bash
javac RecordNullComponentDemo.java
java RecordNullComponentDemo
```

```text
true
OptionalNote[text=null]
```

Record không cấm reference components bằng null chỉ vì fields final. Nếu domain yêu cầu non-null, dùng `Objects.requireNonNull` trong canonical/compact constructor.

**Đừng máy móc thay mọi nullable component bằng Optional**. Java Optional có mục tiêu thiết kế chủ yếu cho return values; đối với components/serialization, cần cân nhắc tool compatibility và domain semantics.

## 37. Khi thêm component mới, những gì tự đổi?

Giả sử ban đầu:

```java
record Customer(String name) {
}
```

Sau đó thay thành:

```java
record Customer(String name, int loyaltyPoints) {
}
```

Đây là **hai phiên bản minh họa thay thế nhau**, không khai báo đồng thời.

Khi thêm component:

- Canonical constructor đổi signature.
- Generated accessor `loyaltyPoints()` xuất hiện.
- Generated equals/hashCode/toString xét component mới.
- Call sites `new Customer(name)` cũ có thể không biên dịch, nếu không thêm overloaded constructor tương thích.
- Serializers, mappers, persisted schema, tests có thể cần cập nhật.
- Một change ở header có thể là **thay đổi API/schema**, không chỉ thêm field nội bộ.

### Giữ constructor cũ như overload

```java
record Customer(String name, int loyaltyPoints) {
    Customer(String name) {
        this(name, 0);
    }
}
```

Đây là khai báo hợp lệ. Overloaded constructor cũ ủy quyền qua `this(name,0)` tới canonical constructor.

**Lưu ý migration:** Giữ Java source call sites chưa chắc đủ cho tương thích với serialized dữ liệu cũ hoặc binary compatibility. Cần kiểm integration contract thật của ứng dụng.

## 38. Kết hợp record với pattern matching trong Java 17

Java 17 hỗ trợ pattern matching for `instanceof`, hữu ích khi code nhận một supertype rồi kiểm một record type.

Tạo **`RecordInstanceofDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordInstanceofDemo {
    static String describe(Object object) {
        if (object instanceof Point point) {
            return point.x() + "," + point.y();
        }
        return "not a point";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe("text"));
    }
}
```

```bash
javac RecordInstanceofDemo.java
java RecordInstanceofDemo
```

```text
2,3
not a point
```

Ở Java 17, đây là **type pattern cho instanceof**, không phải record deconstruction pattern.

**Phiên bản cần phân biệt:** Record patterns như `case Point(int x,int y)` không phải tính năng final của Java 17; chúng xuất hiện ở các phiên bản Java mới hơn. Nếu tài liệu hướng Java 17+, chỉ dùng các mẫu Java 17 biên dịch được, hoặc ghi rõ version khi giới thiệu tính năng mới.

## 39. Record component không phải mọi member của class

Một record có thể chứa:

- Components (header): tạo fields/accessors, tham gia value methods.
- Instance methods bổ sung: logic tính toán.
- Static fields/methods: logic/type-wide data.
- Constructors: khởi tạo/validate.
- Nested types: helpers.

Các **instance methods tính toán** không tự được kể vào equals/hashCode/toString. Các **static fields** cũng không thuộc component state và không quyết định equality của record object theo generated methods.

Ví dụ:

```java
record Invoice(int amount) {
    static final int TAX_PERCENT = 10;

    int total() {
        return amount + amount * TAX_PERCENT / 100;
    }
}
```

Đây là **khai báo minh họa**.

`amount` là component; `TAX_PERCENT` là static constant; `total()` là derived method. Generated equals so records theo amount, không theo một field `total` vì field ấy không tồn tại.

## 40. Khi nào chọn record thay class thường?

Record phù hợp nếu:

- Object chủ yếu là **giá trị dữ liệu**, không phải một entity với identity/lifecycle phức tạp.
- Bộ dữ liệu cốt lõi có thể khai báo rõ trong header.
- Component state không thay đổi sau construction.
- Value-like equals/hashCode/toString phù hợp với domain hoặc có thể override rõ.
- Có thể bảo vệ mutable components nếu muốn immutable sâu.
- Không cần extends class, instance fields bổ sung hoặc instance initializer.
- API mong chờ accessors theo component names.

Ordinary class thường phù hợp hơn nếu:

- Object có **mutable lifecycle** với setters/state transitions.
- Cần thêm instance fields/caches ngoài bộ dữ liệu được công khai.
- Cần inheritance từ một class cụ thể.
- Equality dựa trên business ID và có phức tạp entity semantics.
- Frameworks hiện hành bắt buộc no-arg constructors/proxy/subclass behaviors không tương thích record.
- Muốn encapsulate state nội bộ hoàn toàn khác với transparent component API.

**Không phải mọi DTO bắt buộc là record**, và record không tự bảo đảm deep immutability hoặc validation.

## 41. Bảng đối chiếu record và class viết tay

| Đặc điểm | Record | Ordinary class |
| --- | --- | --- |
| Khai báo data components | Trong header | Fields/constructors tùy thiết kế |
| Instance fields tương ứng | `private final` tự sinh | Tự khai báo |
| Getter/accessor | `componentName()` tự sinh | Tùy chọn `get...` |
| Canonical constructor | Tự sinh nếu không định nghĩa | Không có cơ chế canonical theo header |
| `equals/hashCode/toString` | Tự sinh theo components | Kế thừa Object nếu không override |
| Mutating setters | Không được sinh | Có thể viết |
| Instance fields bổ sung | Không | Có |
| Extends user-defined class | Không | Có, nếu class cho phép |
| Implement interfaces | Có | Có |
| Instance initialization block | Không | Có |
| Static members | Có | Có |
| Component references mutable | Có thể | Có thể |
| Deep immutability tự động | Không | Không |

Cả hai đều là Java reference types khi tạo object, và cả hai đều cần thiết kế rõ invariants, null policy, resource ownership và thread safety nếu domain yêu cầu.

## 42. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Record tự tạo `getName()`” | Accessor tên trùng component | Gọi `name()` |
| “Record tự tạo setter” | Components là final | Tạo record instance mới |
| “Component là public field” | Field được sinh là private final | Dùng accessor |
| “Có final field nên immutable sâu” | Reference có thể trỏ object mutable | Defensive copies/immutable components |
| “Constructor tự kiểm null/range” | Generated canonical chỉ lưu values | Validate tường minh |
| “Compact constructor phải gán `this.x`” | Assignment được compiler thêm sau body | Validate/normalize parameter |
| “Có thể thêm instance field vào record” | Java cấm | Đưa vào header hoặc đổi ordinary class |
| “Record có instance initializer” | Java cấm | Dùng canonical constructor |
| “Thêm component không đổi equals” | Generated equals xét components | Review value semantics |
| “Generated equals so sâu mảng” | Array equality là identity-based | Custom Arrays equals/hash hoặc đổi representation |
| “Hash giống nhau nghĩa equal” | Hash collision có thể xảy ra | Dùng equals |
| “`toString` dùng được làm JSON ổn định” | Không phải serialization format | Serializer riêng |
| “Record không thể có methods” | Cho phép instance/static methods | Khai báo methods theo rules |
| “Record extends mọi class được” | Superclass là java.lang.Record | Dùng interfaces/composition |
| “Local record capture biến outer method” | Local record implicitly static | Truyền data qua components |
| “Record constructor khác canonical tự gán fields” | Non-canonical phải delegate `this(...)` | Ủy quyền constructor |
| “Tự override equals mà quên hashCode” | Phá general contract | Override cặp tương ứng |
| “Record toString luôn an toàn để log” | Có thể lộ component values | Safe display/log policy |
| “Record là immutable nên thread-safe” | Mutable nested objects có thể race | Thiết kế ownership/synchronization |
| “Generated accessor lúc nào cũng clone array” | Trả internal reference mặc định | Tự override defensive accessor |
| “Reflect fields là cách chuẩn hiểu components” | Ordinary fields không phải record metadata | `getRecordComponents()` |
| “Java 17 hỗ trợ record deconstruction pattern final” | Không phải final ở Java 17 | Dùng accessors/instanceof type pattern |
| “Record phù hợp mọi entity DB” | Entity identity/proxies/lifecycle có thể khác | Chọn class nếu cần |

## 43. Một bộ self-test kiểm các members mặc định

Tạo **`RecordGeneratedSelfTest.java`**:

```java
record Item(String code, int count) {
}

public class RecordGeneratedSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Item first = new Item("A", 2);
        Item same = new Item("A", 2);
        Item other = new Item("A", 3);

        check(first.code().equals("A"), "accessor code");
        check(first.count() == 2, "accessor count");

        check(first != same, "different instances");
        check(first.equals(same), "value equals");
        check(!first.equals(other), "unequal value");

        check(first.hashCode() == same.hashCode(),
                "hash contract");
        check(first.toString().equals(
                "Item[code=A, count=2]"), "toString");

        check(Item.class.isRecord(), "isRecord");
        check(Item.class.getRecordComponents().length == 2,
                "component count");

        System.out.println("record generated members PASS");
    }
}
```

```bash
javac RecordGeneratedSelfTest.java
java RecordGeneratedSelfTest
```

```text
record generated members PASS
```

Các checks chủ động ném `AssertionError` khi sai, không cần bật JVM `-ea`.

**Giới hạn test:** Nó không đo hiệu suất, không chứng minh mọi loại component có value semantics hoàn hảo. Khi records chứa arrays, lists hoặc custom reference objects, cần thêm tests về copying, equality và null/invariant contracts.

## 44. Thực hành: thiết kế một record có validation và derived method

**Yêu cầu:** Tạo `Product(String code, int price)`, cấm code rỗng và price âm, chuẩn hóa code bằng `trim()`, cho phép tính giá sau giảm cố định 10 đơn vị nhưng không âm.

### Lời giải tham khảo

Tạo **`RecordProductExercise.java`**:

```java
import java.util.Objects;

record Product(String code, int price) {
    Product {
        code = Objects.requireNonNull(code).trim();
        if (code.isEmpty()) {
            throw new IllegalArgumentException("empty code");
        }
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }
    }

    int discountedPrice() {
        return Math.max(0, price - 10);
    }
}

public class RecordProductExercise {
    public static void main(String[] args) {
        Product product = new Product(" A1 ", 35);

        System.out.println(product);
        System.out.println(product.discountedPrice());

        try {
            new Product("", 10);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid product");
        }
    }
}
```

```bash
javac RecordProductExercise.java
java RecordProductExercise
```

```text
Product[code=A1, price=35]
25
invalid product
```

**Nhận xét:** Canonical constructor bảo vệ invariants; record components lưu state; derived method tính kết quả không lưu field mới. Đây là thiết kế value carrier gọn và đúng mục tiêu record.

## 45. Thực hành: tìm lỗi trong khai báo và sửa

Đoạn mã sau **cố ý sai**, không biên dịch:

```java
record InvalidPerson(String name, int age) {
    private int counter; // Sai: thêm instance field.

    InvalidPerson {
        this.name = name.trim(); // Sai trong compact constructor.
    }

    void setAge(int age) {
        this.age = age; // Sai: final component field.
    }
}
```

**Những lỗi riêng biệt:**

1. `counter` là instance field ngoài record components, bị cấm.
2. Trong compact constructor, không gán trực tiếp component field `this.name`.
3. `age` là private final field, không thể sửa trong setter sau construction.

### Bản sửa hợp lệ

```java
record Person(String name, int age) {
    Person {
        name = name.trim();

        if (age < 0) {
            throw new IllegalArgumentException("negative age");
        }
    }

    Person withAge(int newAge) {
        return new Person(name, newAge);
    }
}
```

Đây là **một record declaration minh họa**.

`withAge` không mutate object hiện tại mà tạo một Person instance mới. Dù cú pháp dài hơn setter, semantics value-like của record vẫn rõ ràng.

## 46. Câu hỏi ôn tập và đáp án

**Câu 1.** `record Point(int x, int y)` khai báo bao nhiêu components?

*Đáp án:* Hai: `x` kiểu int và `y` kiểu int.

**Câu 2.** Compiler sinh fields với modifiers gì?

*Đáp án:* Các component fields tương ứng có `private final`.

**Câu 3.** Compiler sinh `getX()` hay `x()`?

*Đáp án:* `x()`, accessor tên trùng component.

**Câu 4.** Generated canonical constructor có parameters theo thứ tự nào?

*Đáp án:* Đúng theo thứ tự record header.

**Câu 5.** Có thể gọi `new Point(2,3)` khi không tự khai báo constructor không?

*Đáp án:* Có; canonical constructor được sinh tự động.

**Câu 6.** Có thể gán `point.x = 5` sau construction không?

*Đáp án:* Không; field private final.

**Câu 7.** Vì sao hai records `new Point(1,2)` có thể equals true nhưng `==` false?

*Đáp án:* Hai instances khác identity nhưng có cùng component values.

**Câu 8.** Generated hashCode có bắt buộc bằng nhau cho records equal không?

*Đáp án:* Có, theo equals/hashCode contract.

**Câu 9.** HashCode bằng nhau có chứng minh records equal không?

*Đáp án:* Không; collisions hợp lệ.

**Câu 10.** Generated `toString()` thường hiển thị gì?

*Đáp án:* Tên record và tên/giá trị từng component.

**Câu 11.** Record có component `int[]` tự bất biến sâu chưa?

*Đáp án:* Chưa. Final field vẫn có thể trỏ mảng mutable.

**Câu 12.** Generated accessor mảng có clone nội dung không?

*Đáp án:* Không mặc định; trả reference component.

**Câu 13.** `List.copyOf` trong compact constructor giúp gì?

*Đáp án:* Chụp unmodifiable snapshot cấu trúc list khi input mutable, nhưng không deep-copy mutable elements.

**Câu 14.** Generated equals cho array component có so `Arrays.equals` không?

*Đáp án:* Không; default array equals có identity semantics.

**Câu 15.** Khi custom equals cho mảng theo contents, còn cần gì?

*Đáp án:* Custom hashCode tương ứng, và nên bảo vệ mutable state.

**Câu 16.** Compact constructor có phải tự gán `this.component` không?

*Đáp án:* Không; compiler gán fields khi body hoàn tất.

**Câu 17.** Explicit canonical constructor khác compact thế nào?

*Đáp án:* Viết đủ parameters và tự assign final component fields theo rules.

**Câu 18.** Overloaded constructor phải làm gì?

*Đáp án:* Delegate bằng `this(...)` đến constructor khác, cuối cùng tới canonical.

**Câu 19.** Record có được thêm instance field không nằm trong header không?

*Đáp án:* Không.

**Câu 20.** Record có được khai báo static method không?

*Đáp án:* Có.

**Câu 21.** Record có được extends một user-defined class không?

*Đáp án:* Không; record extends `java.lang.Record` theo ngôn ngữ và là final.

**Câu 22.** Record có implements interface không?

*Đáp án:* Có.

**Câu 23.** Local record có tự capture local variable của method không?

*Đáp án:* Không, local record implicitly static; truyền values vào components.

**Câu 24.** API nào cho biết một Class là record?

*Đáp án:* `Class.isRecord()`.

**Câu 25.** API nào lấy danh sách record components?

*Đáp án:* `Class.getRecordComponents()`.

**Câu 26.** Một record component có thể là generic type parameter không?

*Đáp án:* Có, ví dụ `record Box<T>(T value)`.

**Câu 27.** Khi thêm component mới, những generated members nào thay đổi?

*Đáp án:* Canonical constructor, accessor/field mới, equals/hashCode/toString và metadata liên quan.

**Câu 28.** Java 17 có record deconstruction pattern final chưa?

*Đáp án:* Chưa; dùng component accessors và instanceof type patterns.

**Câu 29.** Record có bảo đảm `null` không xuất hiện ở reference component không?

*Đáp án:* Không; validate explicit nếu domain cấm null.

**Câu 30.** Trường hợp nào nên chọn ordinary class thay vì record?

*Đáp án:* Khi cần mutable lifecycle, instance fields bổ sung, inheritance hoặc entity identity semantics không phù hợp transparent value carrier.

## 47. Checklist review khai báo record và generated members

- [ ] Record header có mô tả chính xác các **components cốt lõi**?
- [ ] Tên và thứ tự components phản ánh API mong muốn?
- [ ] Đã hiểu component field là `private final`?
- [ ] Không cố thêm instance fields/instance initializers vào record?
- [ ] Gọi accessors `componentName()`, không tự giả định getters JavaBean?
- [ ] Có validation cho null, blank, range và invariants khi cần?
- [ ] Nếu dùng compact constructor, chỉ normalize parameters và để compiler gán component fields?
- [ ] Nếu dùng explicit canonical constructor, đã assign đủ fields đúng một lần?
- [ ] Overloaded constructors có delegate `this(...)` hợp lệ?
- [ ] Có hiểu generated equals/hashCode/toString theo components?
- [ ] Nếu custom equals, custom hashCode có giữ contract?
- [ ] Có array hoặc mutable List/Map components cần defensive copying?
- [ ] Nếu override accessor cho mutable component, có bảo vệ cả input và output?
- [ ] Có tests về equality/aliasing cho reference components?
- [ ] `toString()` có thể lộ thông tin nhạy cảm không?
- [ ] Không dùng hashCode/toString làm business ID/serializer mặc định?
- [ ] Có methods dẫn xuất mà không cần thêm instance state?
- [ ] Có dùng static factory/helper khi giúp API rõ ràng?
- [ ] Nếu implement interface, accessor có signature hợp lệ?
- [ ] Không dự kiến extends record hoặc cho record extends ordinary class?
- [ ] Local/nested record có dùng đúng quy tắc implicitly static?
- [ ] Nếu dùng reflection, có dựa vào `isRecord/getRecordComponents`?
- [ ] Nếu đổi record header, đã review callers/serialization/mapping/tests?
- [ ] Code nhắm Java 17 có tránh record patterns chưa được final ở phiên bản này?
- [ ] Mỗi ví dụ runnable có đúng tên file/public class, lệnh `javac`/`java` và stdout?

---

**Ghi nhớ cuối bài:** Từ một khai báo ngắn `record Person(String name, int age) { }`, Java tự cung cấp **private final component fields**, **public accessors `name()`/`age()`**, một **canonical constructor**, và các implementations `equals`, `hashCode`, `toString` dựa trên components. Đây là cơ chế tạo **transparent data carrier** có value-like semantics, không phải chỉ viết tắt của JavaBean. Khi cần validation hoặc chuẩn hóa, dùng **compact/explicit canonical constructor**; khi cần giá trị dẫn xuất, thêm methods. Khi components chứa arrays, lists hoặc objects mutable, **không được suy rằng record bất biến sâu hay generated equals so sâu nội dung**: phải xác định defensive-copy và equality contracts cho domain. Dùng record khi dữ liệu cốt lõi có bộ components rõ, ổn định và không cần mutable entity lifecycle; dùng ordinary class khi những giới hạn của record không phù hợp.