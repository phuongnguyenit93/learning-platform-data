# Cú pháp `class` và cấu trúc thân lớp trong Java

## 1. Khai báo một lớp có ý nghĩa gì?

Trong Java, từ khóa **`class`** bắt đầu một bản khai báo lớp (*class declaration*). Bản khai báo tạo tên cho một **kiểu tham chiếu** mới, đồng thời xác định những dữ liệu và hành vi mà các đối tượng của kiểu đó có thể có.

Khai báo tối giản:

```java
class Book {
}
```

`Book` đã là một kiểu hợp lệ dù thân lớp còn rỗng. Nếu mã nằm trong phạm vi truy cập cho phép, người lập trình có thể khai báo `Book book;` hoặc tạo một instance bằng `new Book()`. Trong trường hợp này, vì không khai báo constructor nào, trình biên dịch cung cấp constructor mặc định không tham số. Khai báo biến `Book book;` **chưa tạo đối tượng**.

Dấu ngoặc nhọn `{` và `}` là giới hạn của **thân lớp (class body)**. Các khai báo field, constructor, method, khối khởi tạo và kiểu lồng nhau có thể xuất hiện bên trong, theo quy tắc cú pháp Java.

## 2. Dạng tổng quát của khai báo `class`

Một khung cú pháp minh họa các thành phần tùy chọn:

```java
[annotations] [modifiers] class ClassName [<T, ...>]
        [extends Superclass]
        [implements InterfaceA, InterfaceB, ...]
        [permits SubclassA, SubclassB, ...] {
    // Các khai báo thành viên và khối khởi tạo
}
```

**Đây là ký pháp diễn giải cú pháp, không phải mã Java để biên dịch nguyên văn.** Dấu ngoặc vuông chỉ “có thể có hoặc không”; `...` biểu diễn danh sách. Không phải mọi tổ hợp đều hợp lệ.

| Phần | Vai trò và quy tắc chính |
| --- | --- |
| `class` | Từ khóa bắt buộc khi khai báo một lớp thông thường. |
| `ClassName` | Tên định danh hợp lệ, thường theo quy ước `UpperCamelCase`, ví dụ `BankAccount`. |
| `[annotations]` | Chú thích metadata (annotation) trên lớp nếu cần, ví dụ `@Deprecated`. |
| `[modifiers]` | Điều khiển mức truy cập và đặc tính lớp, như `public`, `abstract`, `final`, `sealed`. |
| `<T, ...>` | Tham số kiểu (*type parameters*) của lớp generic; ví dụ `class Box<T>`. |
| `extends Superclass` | Chỉ rõ lớp cha trực tiếp; lớp thông thường chỉ có thể `extends` **một lớp**. |
| `implements ...` | Chỉ rõ các interface được triển khai; có thể là nhiều interface, phân cách bằng dấu phẩy. |
| `permits ...` | Dùng trong khai báo lớp `sealed` khi cần liệt kê các lớp con được phép; chịu các điều kiện riêng của sealed types. |
| `{ ... }` | Thân lớp, chứa những khai báo và khối khởi tạo đúng cú pháp. |

Ví dụ hợp lệ:

```java
class Account {
}

public class PremiumAccount extends Account implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
}
```

Đoạn này minh họa *hình dạng khai báo*, không phải tệp chạy độc lập vì không có `main`. Nếu đặt trong tệp `PremiumAccount.java` và không thêm khai báo `package`, hai lớp top-level ở đây biên dịch được. `PremiumAccount` là lớp `public`; `Account` có quyền truy cập **package-private** vì không ghi modifier. `extends` đứng trước `implements` trong khai báo.

Nếu không ghi `extends`, lớp thông thường mặc nhiên kế thừa `java.lang.Object` (ngoại trừ chính lớp `Object`). Không thể viết nhiều lớp cha như `extends ParentA, ParentB`. Java có đa hình qua interface và kế thừa đơn giữa các lớp.

### Vị trí trong tệp mã nguồn

Một tệp `.java` thường có thứ tự:

```java
// package example.study;        // Nếu dùng package, đây là khai báo đầu tiên
// import java.util.Objects;      // Nếu cần import, đặt sau package

public class Demo {
    // Thân lớp
}
```

Hai dòng đầu đang được comment để phần khung không phụ thuộc thư mục package. Nếu thực sự viết `package example.study;`, tệp phải được biên dịch/chạy theo đúng package và cấu trúc đường dẫn phù hợp. `import` giúp dùng tên kiểu ngắn ở mã nguồn, không khai báo kiểu mới.

Ở mức **top-level**, lớp có thể `public` hoặc không có modifier truy cập (package-private); không thể khai báo top-level class bằng `private` hoặc `protected`. Một tệp nguồn Java được phép chứa nhiều top-level class, nhưng tối đa **một top-level class `public`**, và tên tệp phải trùng tên lớp `public` đó. Ví dụ có `public class Demo` thì lưu tệp dưới tên `Demo.java`.

## 3. Thân lớp có những thành phần nào?

Phần nằm giữa `{` và `}` của lớp không phải một dãy lệnh chạy liên tiếp. Nó chủ yếu là các **khai báo thành viên**, cùng những **khối khởi tạo** hợp lệ.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Instance field | `private String title;` | Trạng thái riêng của mỗi instance. |
| Static field | `private static int count;` | Trạng thái thuộc lớp. |
| Constructor | `Book(String title) { ... }` | Khởi tạo một đối tượng; cùng tên lớp, không có kiểu trả về. |
| Instance method | `String getTitle() { ... }` | Hành vi được gọi trên đối tượng, có thể dùng `this`. |
| Static method | `static int count() { ... }` | Hành vi gắn với lớp, không có `this`. |
| Instance initializer | `{ /* lệnh */ }` | Khối khởi tạo instance, chạy trong quá trình tạo đối tượng. |
| Static initializer | `static { /* lệnh */ }` | Khối khởi tạo tĩnh, chạy khi lớp được khởi tạo. |
| Nested type | `static class Helper { }` | Kiểu được khai báo bên trong lớp khác. |
| Hằng thường dùng | `static final int MAX = 100;` | Field tĩnh không được gán lại sau khởi tạo. |

Ngoài nested class, thân lớp có thể khai báo nested interface, enum, record và annotation type khi ngữ cảnh cho phép. Một phương thức hoặc constructor có thể chứa các **câu lệnh thực thi**. Ngược lại, không thể đặt trực tiếp một câu lệnh độc lập như `System.out.println("Hello");` giữa các khai báo field/method của lớp.

Các field và method không bắt buộc xếp đúng thứ tự bảng. Bạn có thể khai báo method phía trên field mà nó sử dụng. Tuy vậy, **thứ tự giữa các field initializer và initializer block cùng loại rất quan trọng khi chạy**, sẽ được giải thích ở phần sau.

### Phân biệt field, tham số và biến cục bộ

```java
class Product {
    private String name;                 // Field: thuộc mỗi Product

    Product(String name) {                // name: tham số constructor
        this.name = name;                // this.name: field của instance
    }

    String format() {
        String prefix = "Product: ";      // Biến cục bộ của method
        return prefix + name;
    }
}
```

Field có giá trị mặc định nếu không được khởi tạo rõ ràng: tham chiếu có giá trị `null`, `int` có giá trị `0`, `boolean` có giá trị `false`. Biến cục bộ không thể được đọc trước khi chắc chắn đã được gán. `this` chỉ tới instance hiện tại trong ngữ cảnh instance, thường dùng khi field và tham số trùng tên. Field `private` chỉ cho phép mã trong phạm vi do Java quy định truy cập trực tiếp; các method của chính lớp vẫn đọc hoặc sửa được chúng.

## 4. Chương trình hoàn chỉnh nhìn thấy từng cấu phần hoạt động

Tạo tệp **`ClassSyntaxDemo.java`** sau; đây là ví dụ hoàn chỉnh dùng Java 17 trở lên.

```java
class Device {
    // 1. Static field: dùng chung cho lớp Device.
    private static int createdCount;

    // 2. Instance fields: mỗi Device có giá trị riêng.
    private final String name;
    private boolean active; // Mặc định false.

    // 3. Static initializer: chạy khi lớp Device được khởi tạo.
    static {
        System.out.println("Device: static initializer");
    }

    // 4. Instance initializer: chạy khi tạo mỗi đối tượng Device.
    {
        System.out.println("Device: instance initializer");
    }

    // 5. Constructor: cùng tên Device, không có kiểu trả về.
    Device(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = name;
        createdCount++;
        System.out.println("Device: constructor " + name);
    }

    // 6. Instance method.
    void activate() {
        active = true;
    }

    String describe() {
        return name + " = " + (active ? "on" : "off");
    }

    // 7. Static method.
    static int getCreatedCount() {
        return createdCount;
    }

    // 8. Static nested class.
    static class Category {
        static String label() {
            return "general";
        }
    }
}

public class ClassSyntaxDemo {
    public static void main(String[] args) {
        System.out.println("Begin");

        Device first = new Device("Laptop");
        first.activate();
        Device second = new Device("Speaker");

        System.out.println(first.describe());
        System.out.println(second.describe());
        System.out.println(Device.getCreatedCount());
        System.out.println(Device.Category.label());
    }
}
```

Biên dịch, chạy trong thư mục có `ClassSyntaxDemo.java`:

```bash
javac ClassSyntaxDemo.java
java ClassSyntaxDemo
```

**Standard output chính xác:**

```text
Begin
Device: static initializer
Device: instance initializer
Device: constructor Laptop
Device: instance initializer
Device: constructor Speaker
Laptop = on
Speaker = off
2
general
```

Giải thích:

1. `ClassSyntaxDemo.main` in `Begin` trước khi sử dụng `Device`. Lệnh `new Device("Laptop")` kích hoạt khởi tạo lớp `Device` trong lần dùng chủ động này, nên `static initializer` chỉ in **một lần**.
2. Trước thân constructor cho từng đối tượng, các bộ khởi tạo instance trong lớp được thực hiện; vì vậy thông báo `instance initializer` xuất hiện **hai lần**.
3. Constructor nhận tham số, kiểm tra đầu vào, gán field `name`, tăng bộ đếm tĩnh và in tên thiết bị. `Device` không khai báo constructor không tham số, nên `new Device()` sẽ không biên dịch.
4. `active` là field instance kiểu `boolean`, mặc định `false`. Chỉ gọi `first.activate()` nên `first.describe()` in `on` còn `second.describe()` in `off`.
5. `createdCount` là field `static`, được cả hai lần tạo đối tượng cập nhật; `Device.getCreatedCount()` trả về `2`.
6. `Category` là một **static nested class** trong `Device`; `Device.Category.label()` cho thấy cú pháp tham chiếu kiểu lồng nhau và gọi static method của nó.
7. `Device` không `public` và nằm cùng tệp, cùng package với `ClassSyntaxDemo`; `ClassSyntaxDemo` mới là top-level class `public`, nên tên tệp đúng là `ClassSyntaxDemo.java`.

Lệnh `javac ClassSyntaxDemo.java` sẽ tạo các tệp `.class` tương ứng (ví dụ `Device.class`, `Device$Category.class` và `ClassSyntaxDemo.class`), nhưng một tệp nguồn vẫn chỉ có một top-level class `public`.

## 5. Quy tắc cú pháp của field

Field có dạng phổ biến:

```java
[modifiers] Type fieldName [= expression];
```

Đây là ký pháp minh họa; ví dụ thực tế:

```java
class InventoryItem {
    private String sku;
    private int stock = 0;
    public static final int MAX_STOCK = 1000;
}
```

- Mỗi khai báo field kết thúc bằng dấu **chấm phẩy `;`**.
- `private`, `protected`, `public` hoặc không có modifier quyết định khả năng truy cập; `static` xác định field thuộc lớp; `final` yêu cầu field được gán đúng quy tắc và không bị gán lại sau đó.
- `private final String sku;` hợp lệ nếu mọi constructor hoàn tất bình thường đều bảo đảm field `sku` đã được gán. Ví dụ trên `sku` không phải `final` nên mặc định `null`.
- Có thể khai báo nhiều biến cùng kiểu trong một dòng, ví dụ `int width, height;`, nhưng tách mỗi field thành một dòng thường dễ đọc và chú thích hơn.
- `var` chỉ dùng cho một số khai báo biến cục bộ có giá trị khởi tạo; **không dùng `var` làm kiểu field**. Ví dụ `private var stock = 1;` trong thân lớp là lỗi biên dịch.

`final` đối với biến tham chiếu không làm đối tượng được tham chiếu trở thành bất biến. Ví dụ field `final List<String> names` không được gán sang list khác sau khi đã khởi tạo, nhưng nội dung list đó vẫn có thể thay đổi nếu list hỗ trợ thao tác sửa.

## 6. Quy tắc cú pháp của constructor

Constructor có dạng:

```java
[access_modifier] ClassName(ParameterType parameter, ...) {
    // Khởi tạo đối tượng và bảo đảm các điều kiện hợp lệ
}
```

Không ghi kiểu trả về, kể cả `void`. Tên phải đúng **tên lớp**, và một lớp có thể khai báo nhiều constructor khác nhau theo danh sách tham số (*constructor overloading*).

Ví dụ:

```java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1);
    }

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    int area() {
        return width * height;
    }
}
```

Đây là đoạn khai báo lớp có thể biên dịch nhưng không có `main` riêng để chạy trực tiếp. `Rectangle()` gọi `this(1, 1)` nhằm tái sử dụng constructor có hai tham số. Với Java 17, lời gọi constructor khác bằng `this(...)` hoặc constructor cha bằng `super(...)` phải là câu lệnh đầu tiên trong constructor nếu được viết rõ ràng, và không được dùng cả hai trong cùng một constructor. Nếu không có lời gọi nào được viết, compiler thường chèn lời gọi `super()` thích hợp; do đó lớp cha cần có constructor phù hợp.

Phân biệt:

```java
class Example {
    Example() { }        // Constructor hợp lệ.
    void Example() { }   // Method tên "Example", KHÔNG phải constructor.
}
```

Nếu lớp **không khai báo constructor nào**, compiler sẽ tạo constructor mặc định không tham số; khi **đã tự khai báo ít nhất một constructor**, compiler không tạo thêm constructor mặc định. Không thể khai báo constructor là `static`, `final` hoặc `abstract`.

## 7. Quy tắc cú pháp của method

Method thông thường gồm modifier tùy chọn, **kiểu trả về**, tên, danh sách tham số, và thân trong ngoặc nhọn:

```java
[modifiers] ReturnType methodName(ParameterType parameter, ...) {
    // Các câu lệnh
}
```

Ví dụ:

```java
class Temperature {
    private double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    double fahrenheit() {
        return celsius * 9 / 5 + 32;
    }

    void setCelsius(double newValue) {
        celsius = newValue;
    }

    static String unit() {
        return "Celsius";
    }
}
```

`fahrenheit()` trả về `double` và phải trả một giá trị trên các luồng thực thi bình thường của method. `setCelsius(...)` có kiểu trả về `void` nên không trả giá trị; `unit()` là static method có thể gọi bằng `Temperature.unit()` mà không tạo instance.

Trong một static method không tồn tại biến `this`; muốn truy cập field `celsius` của một đối tượng, phải có một tham chiếu cụ thể tới `Temperature`. Một instance method có thể truy cập cả instance member và static member được phép.

Method `abstract` và một số khai báo method trong interface có thể **không có thân**, khi đó kết thúc bằng `;`. Ví dụ:

```java
abstract class Task {
    abstract void execute(); // Không có thân vì là abstract method.

    void log() {              // Concrete method có thân.
        System.out.println("Task");
    }
}
```

Một lớp có abstract method phải khai báo `abstract`. Không thể tạo instance trực tiếp bằng `new Task()`. Lớp con không abstract phải triển khai những abstract method còn thiếu.

Lưu ý về dấu câu: **field declaration** kết thúc bằng `;`; một method/constructor **có thân** kết thúc bằng `}` và không cần thêm `;`; các statement bên trong thân method thường có `;` theo cú pháp từng loại statement. Thân lớp không phải nơi đặt các statement tùy ý.

## 8. Thứ tự khởi tạo: `static`, instance initializer và constructor

Cấu trúc khai báo trông giống nhau nhưng thời điểm thực thi khác nhau:

1. **Khi lớp được khởi tạo**, các static field initializer và `static { ... }` của lớp được xử lý theo thứ tự văn bản trong điều kiện khởi tạo thích hợp. Khởi tạo lớp không đồng nghĩa với chỉ mới nạp tệp `.class`. Bộ khởi tạo tĩnh không chạy lại cho mỗi instance.
2. **Khi tạo một instance**, JVM thực hiện cấp phát và thiết lập các giá trị field mặc định trước; sau bước constructor của lớp cha, các instance field initializer cùng instance initializer block của lớp hiện tại được thực hiện theo thứ tự văn bản, trước phần thân constructor của lớp hiện tại.
3. **Constructor body** hoàn thành việc thiết lập đối tượng. Với constructor chaining qua `this(...)`, việc khởi tạo instance của lớp không bị lặp lại cho mỗi constructor trong chuỗi.

Ví dụ riêng về thứ tự trong **cùng một lớp**, có thể đặt trong `InitOrderDemo.java`:

```java
class Counter {
    static int multiplier = 2;

    static {
        multiplier += 1;
    }

    private int value = 10;

    {
        value += multiplier;
    }

    Counter() {
        value *= 2;
    }

    int value() {
        return value;
    }
}

public class InitOrderDemo {
    public static void main(String[] args) {
        System.out.println(new Counter().value());
        System.out.println(new Counter().value());
    }
}
```

```bash
javac InitOrderDemo.java
java InitOrderDemo
```

```text
26
26
```

Lý do: `multiplier` bắt đầu bằng `2` rồi tăng lên `3` khi lớp được khởi tạo; mỗi instance nhận `value = 10`, khối instance cộng `3` thành `13`, constructor nhân hai thành `26`. Static initialization không lặp khi tạo instance thứ hai.

**Không nên lạm dụng initializer block** chỉ để làm điều constructor có thể thể hiện rõ ràng hơn. Ví dụ dùng initializer block nhằm hiểu cấu trúc lớp; trong ứng dụng thường ưu tiên khởi tạo field đơn giản tại nơi khai báo và kiểm tra trạng thái trong constructor.

Một số chi tiết nâng cao nằm ngoài luồng cơ bản: tham chiếu đến static constant dạng *compile-time constant* có thể không làm chạy static initializer; khởi tạo và kế thừa tương tác theo quy tắc chặt chẽ; các initializer không được tùy tiện đọc field instance chưa được khởi tạo tại vị trí chưa hợp lệ. Khi học thứ tự thực thi, hãy dựa trên đúng mã và quy tắc khởi tạo chứ không suy ra từ việc JVM đã “load” lớp.

## 9. Quyền truy cập và modifier dùng ở đâu?

Không phải modifier nào cũng hợp lệ trong mọi ngữ cảnh:

| Vị trí | Modifier/đặc điểm thông dụng | Ghi chú |
| --- | --- | --- |
| Top-level class | `public` hoặc package-private; `abstract`, `final`, `sealed` theo quy tắc | Không khai báo top-level class `private`, `protected` hoặc `static`. |
| Member class (lớp lồng trong lớp) | Có thể `public`, `protected`, `private` hoặc package-private; có thể `static` | Có phạm vi truy cập của thành viên; static nested class không cần instance của lớp bao. |
| Instance field | Access modifier, `final`, `transient`, `volatile` tùy trường hợp | Không đồng thời khai báo field `final` và `volatile`. |
| Static field | Access modifier và `static`, thường phối hợp `final` cho hằng | Cần phân biệt trạng thái chung và riêng. |
| Constructor | `public`, `protected`, `private` hoặc package-private | Không có kiểu trả về; không `static`, `final`, `abstract`. |
| Method | Access modifier, `static`, `final`, `abstract`, `synchronized`, ... | Các kết hợp có ràng buộc; chẳng hạn abstract method không thể đồng thời `final`. |

`abstract` nghĩa là lớp có thể chưa có đầy đủ triển khai; `final` ngăn lớp bị kế thừa. Vì vậy `abstract final class X` không hợp lệ. `sealed` là cách Java 17 kiểm soát lớp con được phép; các lớp con trực tiếp phải khai báo trạng thái thích hợp như `final`, `sealed` hoặc `non-sealed` và đáp ứng những điều kiện khác của sealed hierarchy. Ví dụ:

```java
sealed class Shape permits Circle, Square {
}

final class Circle extends Shape {
}

non-sealed class Square extends Shape {
}
```

Đoạn trên là khai báo kiểu hợp lệ với Java 17, không có `main`. `Square` cho phép mở rộng tiếp, trong khi `Circle` chấm dứt nhánh kế thừa. Không cần dùng sealed class cho mọi mô hình dữ liệu; ví dụ chỉ làm rõ `permits` và `non-sealed` trong ngữ pháp lớp.

Một class top-level không có modifier truy cập là **package-private**: mã từ cùng package có thể tham chiếu tới nó nếu các điều kiện truy cập khác cho phép. Một thành viên `private` chỉ được truy cập theo quy tắc phạm vi private của Java; “cùng tệp nguồn” không tự đồng nghĩa với “được truy cập private”. Lựa chọn modifier là một phần API của lớp.

## 10. Kiểu lồng nhau nằm trong thân lớp

`class` không chỉ có thể xuất hiện ở đầu tệp: nó còn có thể nằm bên trong một lớp khác hoặc trong ngữ cảnh khai báo kiểu cục bộ theo quy tắc Java.

```java
class Outer {
    private int base = 10;

    class Inner {
        int addToBase(int n) {
            return base + n;
        }
    }

    static class Nested {
        static int doubleValue(int n) {
            return n * 2;
        }
    }
}

public class NestedDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        System.out.println(inner.addToBase(5));
        System.out.println(Outer.Nested.doubleValue(5));
    }
}
```

Lưu thành `NestedDemo.java` rồi chạy:

```bash
javac NestedDemo.java
java NestedDemo
```

```text
15
10
```

`Inner` là **non-static member class** (*inner class*), mỗi instance của nó gắn với một instance `Outer`. Vì vậy mã dùng `outer.new Inner()`; inner class có thể truy cập `base` của đối tượng `Outer` bao quanh. `Nested` là **static nested class** nên dùng tên kiểu `Outer.Nested`, không cần instance `Outer`. `static` ở đây mô tả loại lớp lồng nhau, không làm lớp thành một hàm độc lập.

Lớp cục bộ (*local class*) có thể khai báo trong block như bên trong method; lớp vô danh (*anonymous class*) có cú pháp biểu thức riêng. Đây là các hình thức khác của tổ chức kiểu trong Java, còn cấu trúc top-level và member class là đủ để nắm ý nghĩa cơ bản của thân lớp.

## 11. Cách đọc và rà soát một khai báo lớp

Khi thấy một lớp lạ, có thể rà theo trình tự:

1. **Đọc dòng khai báo:** tên kiểu là gì; mức truy cập nào; có `abstract`/`final`/`sealed`, tham số generic, `extends` hoặc `implements` không?
2. **Xác định state:** field nào thuộc instance, field nào `static`? Field nào `final`? Field nào được khởi tạo ngay khi khai báo?
3. **Tìm constructor:** nhận tham số gì, kiểm tra dữ liệu nào, có gọi `this(...)`/`super(...)` không? Có hay không có constructor không tham số?
4. **Tìm API method:** loại giá trị trả về, quyền truy cập, side effect và sự khác biệt giữa instance/static method.
5. **Tìm initializer và nested types:** khối nào chạy một lần khi khởi tạo lớp, khối nào chạy với từng instance, có kiểu lồng nhau cần hiểu thêm không?

Tên lớp, field và method theo thông lệ Java thường dùng `UpperCamelCase` cho kiểu (`OrderItem`), `lowerCamelCase` cho biến/method (`itemCount`, `calculateTotal`), và `UPPER_SNAKE_CASE` cho hằng (`MAX_RETRIES`). Đây là quy ước dễ đọc, không phải yêu cầu cú pháp bắt buộc.

## 12. Các lỗi thường gặp khi viết `class`

| Tình huống | Ví dụ sai / cách sửa |
| --- | --- |
| Quên dấu ngoặc bao thân lớp | `class User` thiếu `{ ... }` là lỗi cú pháp. |
| Viết statement tự do ngay trong class body | `class A { System.out.println("Hi"); }` không hợp lệ; đặt lệnh trong method, constructor hoặc initializer block. |
| Viết `private class A` tại top-level | `private` chỉ áp dụng cho những ngữ cảnh phù hợp như member class, không phải top-level class. |
| Đặt file sai tên lớp `public` | `public class Report` phải ở tệp `Report.java`. |
| Đặt hai top-level class `public` trong cùng một tệp | Tách chúng thành các tệp tương ứng, hoặc thay đổi thiết kế/mức truy cập theo nhu cầu. |
| Nhầm method với constructor | `void User() { }` là method, không phải constructor `User() { }`. |
| Tưởng compiler luôn tạo constructor không tham số | Nếu có `User(String name)` mà không khai báo `User()`, `new User()` là lỗi biên dịch. |
| Gọi field instance trực tiếp từ static method | Cần tạo/lấy tham chiếu đối tượng rồi truy cập theo quyền; static method không có `this`. |
| Dùng `var` làm kiểu field | `class A { var x = 1; }` không biên dịch; khai báo kiểu cụ thể như `int x = 1;`. |
| Nghĩ mọi `{ ... }` trong lớp là method | Khối `static { ... }` và khối `{ ... }` độc lập trong class body là initializer; method cần chữ ký khai báo. |
| Viết nhiều lớp cha ở `extends` | Java class chỉ có một superclass trực tiếp; dùng `implements` cho nhiều interface. |
| Nghĩ thứ tự initializer không ảnh hưởng kết quả | Các field initializer và khối khởi tạo cùng loại được xử lý theo thứ tự khai báo khi khởi tạo; nên kiểm tra trước khi hoán đổi. |

Các đoạn “ví dụ sai” trong bảng được cung cấp để nhận diện lỗi và **không dùng để biên dịch nguyên văn**.

## 13. Bài tập tự kiểm tra

**Bài 1 — Nhận diện cấu trúc.** Trong `Device` ở ví dụ chính, hãy liệt kê: một static field, hai instance field, constructor, static initializer, instance initializer, một instance method, một static method và một nested type.

*Gợi ý đáp án:* `createdCount`; `name` và `active`; `Device(String name)`; `static { ... }`; `{ ... }`; `activate()` hoặc `describe()`; `getCreatedCount()`; `Category`.

**Bài 2 — Kiểm tra thứ tự.** Nếu trong `main` gọi thêm `new Device("Tablet")` rồi `System.out.println(Device.getCreatedCount());`, bộ khởi tạo nào chạy và in gì?

*Đáp án:* Static initializer **không chạy lại**; instance initializer in một dòng, constructor in `Device: constructor Tablet`, rồi số lượng được in là `3`.

**Bài 3 — Tự thiết kế lớp.** Viết lớp `Wallet` với `private int balance`, constructor nhận số dư khởi tạo không âm, method `deposit(int amount)` chỉ chấp nhận số dương và method `getBalance()` trả về số dư. Đặt tên tệp hợp lệ nếu lớp top-level được khai báo `public`. Tự xác định đâu là field, constructor, method và vị trí dấu `;`/`{}`.

**Bài 4 — Phân biệt khung khai báo.** Giải thích tại sao `class A { }` là hợp lệ, `private class A { }` tại top-level là lỗi, và `class A { private class B { } }` lại có thể hợp lệ.

*Đáp án:* Một class top-level có thể không có member; modifier `private` không dùng cho top-level type; nhưng `B` là **member class** của `A` nên có thể `private`.

**Bài 5 — Chẩn đoán.** Lớp `class X { X(int n) { } }` có tạo được bằng `new X()` không? Muốn hỗ trợ cú pháp đó, phải thay đổi gì?

*Đáp án:* Không; cần thêm constructor `X()` (ví dụ gọi `this(0);`), hoặc truyền đối số `new X(5)` đúng chữ ký hiện có.

---

**Ghi nhớ:** Dòng `class Name ... { ... }` khai báo một **kiểu**; phần header quy định tên, phạm vi và quan hệ kiểu, còn **thân lớp** chứa field, constructor, method, initializer và kiểu lồng nhau. Phân biệt đúng vị trí khai báo, quy tắc dấu `;`/ngoặc, thành viên `static` với instance và thứ tự khởi tạo sẽ giúp đọc và viết lớp Java chính xác hơn.