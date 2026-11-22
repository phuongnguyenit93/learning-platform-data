# Các từ khóa bổ nghĩa cho lớp và tổ hợp không hợp lệ trong Java

**Class modifier** là từ khóa đặt trong phần khai báo lớp để xác định **khả năng truy cập**, **khả năng kế thừa**, **khả năng tạo thể hiện** hoặc đặc điểm khai báo của lớp. Cùng một từ khóa có thể hợp lệ ở **lớp cấp cao nhất** (top-level class), **lớp thành viên/lồng nhau** (member/nested class) hay chỉ ở vị trí khác. Một số modifier riêng lẻ hợp lệ nhưng **không được kết hợp** vì ý nghĩa mâu thuẫn nhau.

Ví dụ:

```java
public abstract class Animal {
    public abstract void sound();
}
```

Trong `public abstract class Animal`, `public` cho biết phạm vi truy cập; `abstract` cho biết lớp chưa thể được tạo trực tiếp bằng `new Animal()` và có thể chứa phương thức trừu tượng.

Trái lại, khai báo `abstract final class Animal { }` **không hợp lệ**: `abstract` cho phép một lớp con hoàn thiện phần còn thiếu, trong khi `final` cấm kế thừa. Mục tiêu của bài này là xác định **modifier nào dùng được ở đâu, kết hợp nào có nghĩa, và trường hợp nào bị `javac` từ chối**.

## 1. Cú pháp và ba câu hỏi cần phân biệt

Cú pháp khái quát của lớp thông thường:

```java
[annotations] [modifiers] class ClassName
        [extends Superclass]
        [implements Interface1, Interface2] {
    // thành phần lớp
}
```

Đây là **sơ đồ cú pháp**, không phải mã Java để biên dịch nguyên xi. Dấu ngoặc vuông biểu thị thành phần tùy chọn.

Khi thấy một modifier, hãy kiểm tra:

1. **Vị trí khai báo:** Đây là top-level class, member class, hay local class nằm trong phương thức/khối lệnh?
2. **Thuộc tính được bổ nghĩa:** Modifier tác động đến **bản thân lớp**, hay đang đứng trước **method**, **field**, **constructor**? Cùng từ `final` nhưng tác dụng khác nhau tùy vị trí.
3. **Sự tương thích:** Một modifier có xung đột với modifier khác, cấu trúc `extends`/`implements`, hoặc quy tắc `sealed` hay không?

Không có từ khóa `default` để biểu thị “phạm vi truy cập mặc định” của lớp. **Không ghi access modifier** mới là cách khai báo lớp package-private trong ngữ cảnh cho phép.

## 2. Modifier của lớp cấp cao nhất

Lớp cấp cao nhất là lớp khai báo trực tiếp trong tệp nguồn, **không nằm trong thân một kiểu khác**.

| Modifier | Hợp lệ cho top-level class? | Ý nghĩa chính |
| --- | --- | --- |
| `public` | **Có** | Kiểu có thể được truy cập từ package khác nếu đáp ứng thêm các điều kiện về module, classpath và thành phần cần dùng |
| Không ghi access modifier | **Có** | Lớp có quyền truy cập **package-private** |
| `abstract` | **Có** | Không được khởi tạo trực tiếp; có thể chứa phương thức trừu tượng |
| `final` | **Có** | Không được tạo lớp con |
| `sealed` | **Có** (Java 17+) | Giới hạn các lớp được trực tiếp kế thừa lớp này |
| `non-sealed` | **Có điều kiện** (Java 17+) | Bỏ giới hạn kế thừa của một lớp con trực tiếp thuộc hệ phân cấp có siêu kiểu `sealed` |
| `strictfp` | **Có**, nhưng không còn ý nghĩa thực tế từ Java 17 | Modifier lịch sử liên quan phép toán dấu phẩy động |
| `private` | **Không** | Không áp dụng cho top-level class |
| `protected` | **Không** | Không áp dụng cho top-level class |
| `static` | **Không** | Chỉ dùng với lớp thành viên lồng nhau trong ngữ cảnh tương ứng |

**Ghi chú:** `sealed` và `non-sealed` là các từ hạn định được sử dụng theo ngữ cảnh (*contextual keywords/modifiers*) từ Java 17; trong khai báo lớp chúng hoạt động như modifier. `@Deprecated` và các annotation không phải access modifier, dù có thể xuất hiện trước `class`.

Ví dụ hợp lệ ở cấp tệp nguồn:

```java
public class Application { }

abstract class AbstractTask { }

final class Utility { }

class PackageHelper { }
```

Đây là đoạn minh họa các khai báo, không có phương thức `main`. Nếu đặt chung trong một tệp, hãy đặt tên tệp là **`Application.java`** vì `Application` là kiểu top-level `public`. Các lớp còn lại đều package-private.

Quy tắc **tối đa một kiểu top-level `public` trong tệp `.java`** áp dụng trong cách tổ chức và biên dịch bằng `javac` thông thường. Nếu có kiểu `public`, tên tệp phải trùng tên kiểu đó (phân biệt hoa/thường). Quy tắc đặt tên tệp là ràng buộc của **đơn vị biên dịch**, tách biệt với việc hai modifier trên **cùng một lớp** có hợp lệ hay không.

## 3. `public` và package-private: phạm vi truy cập của lớp

### 3.1. Top-level `public`

```java
package school;

public class Student {
    public String name() {
        return "An";
    }
}
```

Lưu trong `src/school/Student.java`. Lớp có thể được mã ở package khác tham chiếu nếu được nạp và có thể truy cập theo cấu hình module/classpath. Phương thức `name()` cũng được khai báo `public` để mã ngoài package gọi được.

`public` **không có nghĩa mọi thành phần bên trong lớp đều tự động là `public`**. Chẳng hạn, constructor `Student()` viết tường minh không có modifier sẽ là package-private; còn trong ví dụ trên, vì không khai báo constructor nào nên Java cung cấp constructor mặc định có cùng mức truy cập với lớp `public`.

### 3.2. Top-level package-private

```java
package school;

class StudentFormatter {
    static String upper(String text) {
        return text.toUpperCase();
    }
}
```

Lưu trong `src/school/StudentFormatter.java`. Không viết `public` hay một access modifier nào trước `class` khiến `StudentFormatter` chỉ được truy cập bằng mã thuộc package `school`. Đặt `import school.StudentFormatter;` từ package khác **không mở rộng** quyền truy cập đó.

Hai lớp trong **hai tệp nguồn khác nhau** nhưng cùng khai báo `package school;` vẫn có thể truy cập kiểu package-private của nhau. Ngược lại, chỉ đặt hai tệp cùng một thư mục mà khai báo package khác nhau không làm chúng trở thành cùng package.

### 3.3. Vì sao `private class` và `protected class` sai ở cấp tệp?

```java
private class Hidden { }        // SAI nếu khai báo top-level
protected class Inherited { }   // SAI nếu khai báo top-level
```

`private` và `protected` không phải modifier được phép trên top-level class. Muốn giấu chi tiết khỏi package khác, thường dùng **package-private**. Muốn một kiểu thực sự là thành phần `private` của một lớp khác, có thể khai báo **private nested class** (xem mục 7).

Không viết:

```java
default class Helper { }       // SAI: default không là access modifier của class
```

“Default access” là tên gọi không chính thức của việc **bỏ access modifier**, không phải lệnh thêm từ khóa `default`.

## 4. `abstract`: lớp chưa thể khởi tạo trực tiếp

Một **abstract class** được khai báo bằng `abstract` và **không được tạo thể hiện trực tiếp**. Nó có thể chứa cả phương thức đã có phần thân, phương thức trừu tượng, field, constructor và các thành phần khác được Java cho phép.

Ví dụ:

```java
abstract class Animal {
    private final String name;

    protected Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract String sound();
}

class Dog extends Animal {
    Dog(String name) {
        super(name);
    }

    @Override
    String sound() {
        return "Gâu";
    }
}
```

`Animal` được đánh dấu `abstract` và `Dog` là một lớp cụ thể triển khai phương thức `sound()`. Một đoạn mã đặt trong phương thức có thể viết `Animal pet = new Dog("Milu");`, nhưng **không thể** viết `new Animal("Milu")` vì `Animal` là trừu tượng.

Các nguyên tắc quan trọng:

- Lớp có phương thức instance `abstract` **phải** là abstract class (trừ những quy tắc riêng của interface).
- Abstract class **không bắt buộc** chứa abstract method. Nó vẫn có ích để ngăn tạo trực tiếp hoặc làm lớp cơ sở trong thiết kế kế thừa.
- Abstract class **có thể có constructor**, nhưng constructor đó không dùng để tạo instance `Animal` trực tiếp; constructor được gọi trong quá trình tạo một đối tượng lớp con.
- Lớp con cụ thể phải triển khai các phương thức abstract mà nó kế thừa, trừ những phương thức đã được triển khai thích hợp ở cấp trung gian; nếu chưa hoàn thiện, lớp con cũng phải khai báo `abstract`.
- Abstract class **vẫn có thể có phương thức `final`**. “Lớp abstract” và “phương thức final” không mâu thuẫn: lớp có thể được kế thừa, còn riêng phương thức final không được override.

Ví dụ sai:

```java
class Animal {
    abstract void sound();      // SAI: lớp chứa abstract method nhưng không abstract
}
```

Ví dụ hợp lệ:

```java
abstract class Animal {
    final void breathe() {
        System.out.println("Thở");
    }

    abstract void sound();
}
```

Đoạn `Animal` cuối là ví dụ khai báo độc lập minh họa, không được đặt cùng một package/tập nguồn với lớp `Animal` trước đó vì sẽ trùng tên.

## 5. `final`: cấm kế thừa lớp

Khi đặt `final` trước khai báo lớp, lớp **không thể có lớp con**:

```java
final class Token {
    private final String value;

    Token(String value) {
        this.value = value;
    }

    String value() {
        return value;
    }
}
```

`Token` có thể được tạo bằng `new Token("abc")` ở nơi có quyền gọi constructor, nhưng `class SpecialToken extends Token { }` sẽ không biên dịch. `final` **không** có nghĩa lớp không được khởi tạo; nó chỉ cấm **kế thừa lớp**.

Cần phân biệt ba cách dùng `final`:

| Vị trí | Ví dụ | Tác dụng |
| --- | --- | --- |
| Lớp | `final class Token { }` | Không thể `extends Token` |
| Phương thức | `final void log() { }` | Lớp con không được override phương thức đó |
| Biến / field | `final int id = 1;` | Biến không được gán lại sau khi đã khởi tạo đúng quy tắc |

Một `final class` **không tự động bất biến** (*immutable*). Nó vẫn có thể sở hữu field có thể thay đổi:

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int getValue() {
        return value;
    }
}
```

`Counter` không thể bị kế thừa, nhưng các thể hiện vẫn thay đổi trạng thái sau mỗi lần `increment()`. Muốn bất biến cần thiết kế các field, đối tượng liên quan và API phù hợp.

## 6. `sealed` và `non-sealed` trong Java 17: giới hạn hệ phân cấp kế thừa

Java 17 hỗ trợ **sealed classes** và **sealed interfaces**. `sealed` quy định **những kiểu nào được làm lớp con trực tiếp**; `permits` liệt kê các kiểu con được phép nếu không sử dụng cơ chế suy luận danh sách phù hợp.

Một **lớp con trực tiếp** của kiểu `sealed` phải tuyên bố một trong ba trạng thái:

- `final`: kết thúc nhánh kế thừa tại lớp đó.
- `sealed`: tiếp tục kiểm soát các lớp con trực tiếp ở tầng tiếp theo.
- `non-sealed`: mở nhánh này cho các lớp con tiếp theo theo quy tắc kế thừa thông thường.

`abstract` có thể xuất hiện cùng `sealed` hoặc `non-sealed` vì hai nhóm modifier nói về **khả năng tạo thể hiện** và **mức giới hạn kế thừa** khác nhau.

### 6.1. Ví dụ Java 17 hoàn chỉnh

Lưu toàn bộ nội dung sau vào **`ModifierDemo.java`**:

```java
public class ModifierDemo {
    public static void main(String[] args) {
        Shape a = new Square(3);
        Shape b = new Rectangle(2, 5);

        System.out.println("Square: " + a.area());
        System.out.println("Rectangle: " + b.area());
        System.out.println("Square type: " + (a instanceof Square));
        System.out.println("Rectangle type: " + (b instanceof Rectangle));
    }
}

abstract sealed class Shape permits Square, OpenShape {
    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}

abstract non-sealed class OpenShape extends Shape {
    // Nhánh này được phép có lớp con tiếp theo.
}

class Rectangle extends OpenShape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    int area() {
        return width * height;
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 ModifierDemo.java
java ModifierDemo
```

Kết quả chuẩn:

```text
Square: 9
Rectangle: 10
Square type: true
Rectangle type: true
```

Giải thích từng modifier:

- `ModifierDemo` là **top-level `public`**; tên tệp bắt buộc là `ModifierDemo.java` khi dùng `javac` theo cách thông thường.
- `Shape` là **`abstract sealed`**: không được `new Shape()` trực tiếp; chỉ **`Square` và `OpenShape`** là lớp con trực tiếp hợp lệ vì chúng xuất hiện trong `permits`.
- `Square` là **`final`**, cho nên không ai được tạo lớp con của `Square`.
- `OpenShape` là **`abstract non-sealed`**: vẫn không thể tạo thể hiện trực tiếp, nhưng cho phép các lớp con như `Rectangle` mở rộng nhánh này.
- `Rectangle` **không phải lớp con trực tiếp** của `Shape` (nó kế thừa `OpenShape`), nên không cần có trong `Shape permits ...` và không bắt buộc phải khai báo `final`, `sealed` hay `non-sealed`.
- `sealed` không tự biến lớp thành abstract. Một lớp `sealed` **không có `abstract`** vẫn có thể được khởi tạo trực tiếp nếu constructor có thể truy cập và lớp thỏa mãn các quy tắc khác.

Dùng `abstract sealed` khi muốn giữ lớp cơ sở không được tạo trực tiếp và giới hạn chính xác các loại dẫn xuất. Dùng `abstract non-sealed` khi muốn cho phép hệ phân cấp tiếp tục mở rộng thông qua một nhánh đã được cấp phép.

### 6.2. Nhánh `sealed` nhiều tầng

Đoạn sau minh họa dạng khai báo hợp lệ (không phải chương trình độc lập):

```java
sealed class Vehicle permits Car, Truck { }

final class Car extends Vehicle { }

sealed class Truck extends Vehicle permits SmallTruck { }

final class SmallTruck extends Truck { }
```

Ở đây `Vehicle` chỉ cho `Car` và `Truck` kế thừa **trực tiếp**. `Truck` vẫn là `sealed` nên phải xác định lớp con trực tiếp hợp lệ `SmallTruck`; `SmallTruck` đóng nhánh bằng `final`.

Không thể khai báo một lớp con khác trực tiếp `extends Vehicle` nếu không được cho phép trong `permits`.

### 6.3. Quy tắc nguồn và module của `sealed`

- Các kiểu được cho phép phải là **kiểu con trực tiếp** qua `extends` hoặc `implements` phù hợp; chỉ được nêu tên trong `permits` chưa đủ.
- Trong **named module**, các kiểu con trực tiếp được cho phép phải thuộc **cùng module** với kiểu `sealed`. Trong **unnamed module**, chúng phải thuộc **cùng package**.
- Nếu tất cả các lớp con trực tiếp xuất hiện trong **cùng đơn vị biên dịch**, `permits` có thể được **suy luận** theo quy tắc Java; việc ghi `permits` rõ ràng thường giúp người học và người bảo trì nhìn thấy chủ ý.
- `non-sealed` chỉ có ý nghĩa khi lớp đó **trực tiếp kế thừa hoặc triển khai ít nhất một siêu kiểu `sealed`**. Không thể dùng `non-sealed` một cách độc lập cho bất kỳ lớp thông thường nào.
- Java giới hạn **kiểu con trực tiếp** của `sealed`; từ nhánh `non-sealed`, các lớp cháu có thể kế thừa theo quy tắc thông thường.

## 7. Lớp thành viên/lồng nhau: có thêm `private`, `protected` và `static`

Với **member class** nằm bên trong một lớp khác, các access modifier và `static` có thể được sử dụng theo ngữ cảnh hợp lệ.

Lưu thành **`NestedDemo.java`**:

```java
public class NestedDemo {
    private final String owner;

    public NestedDemo(String owner) {
        this.owner = owner;
    }

    private class Label {
        String text() {
            return "Owner: " + owner;
        }
    }

    protected static class Formatter {
        static String bracket(String text) {
            return "[" + text + "]";
        }
    }

    public void show() {
        Label label = new Label();
        System.out.println(Formatter.bracket(label.text()));
    }

    public static void main(String[] args) {
        new NestedDemo("An").show();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 NestedDemo.java
java NestedDemo
```

Stdout:

```text
[Owner: An]
```

- `NestedDemo` là top-level `public`.
- `Label` là **private member inner class**; nó thuộc thân `NestedDemo` và không khai báo `static`. Thể hiện `Label` có thể truy cập `owner` thuộc thể hiện `NestedDemo` bao ngoài.
- `Formatter` là **protected static nested class**. `static` nghĩa là không đòi một thể hiện `NestedDemo` bao ngoài như lớp `Label`. `protected` là access modifier hợp lệ cho member class; quyền truy cập từ lớp khác được xác định theo các quy tắc protected của Java.
- `Formatter.bracket()` là phương thức static được gọi qua `Formatter` trong nội bộ lớp bao ngoài.
- `private` và `protected` ở đây hợp lệ **vì `Label` và `Formatter` nằm trong thân lớp `NestedDemo`**, không ở cấp tệp.

Bảng so sánh:

| Bối cảnh lớp | Access modifier có thể dùng | `static`? | Ghi chú |
| --- | --- | --- | --- |
| **Top-level class** | `public` hoặc bỏ modifier (package-private) | **Không** | Không có lớp bao ngoài |
| **Member class trong một class** | `public`, `protected`, `private` hoặc bỏ modifier | **Có** | `static class` là static nested class |
| **Local class trong phương thức/khối** | Không dùng `public`, `protected`, `private` | **Không** | Local class có quy tắc riêng; có thể `abstract` hoặc `final` |
| **Anonymous class** | Không có dòng khai báo `class Name` để đặt modifier | Không áp dụng | Tạo thể hiện và khai báo lớp vô danh trong một biểu thức |

Ví dụ **không hợp lệ** khi được đặt trực tiếp ở cấp tệp:

```java
private class FileHelper { }       // SAI: private top-level
protected class FileFormatter { }  // SAI: protected top-level
static class FileCache { }         // SAI: static top-level
```

Muốn lớp `private static`, phải đặt **bên trong** một kiểu bao ngoài:

```java
class Service {
    private static final class InternalCache {
        // Lớp lồng nhau, private, static và final: hợp lệ.
    }
}
```

Một member class không `static` được gọi là **inner class**, còn member class `static` là **static nested class**. Không nên gọi mọi lớp viết chung một tệp là nested class: chỉ có khai báo **thực sự nằm trong thân kiểu khác** mới là member/nested class.

## 8. Các tổ hợp modifier hợp lệ và không hợp lệ

### 8.1. Bảng tổ hợp thường gặp

| Khai báo / tổ hợp | Kết quả | Giải thích |
| --- | --- | --- |
| `public class A` | **Hợp lệ** | Lớp top-level truy cập công khai, khi đặt tệp `A.java` |
| `abstract class A` | **Hợp lệ** | Có thể làm lớp cơ sở, không tạo trực tiếp |
| `final class A` | **Hợp lệ** | Lớp có thể tạo đối tượng nhưng không thể được kế thừa |
| `abstract sealed class A permits B` | **Hợp lệ có điều kiện** | `B` phải là lớp con trực tiếp hợp lệ và tuyên bố `final`, `sealed` hoặc `non-sealed` |
| `abstract non-sealed class B extends A` | **Hợp lệ có điều kiện** | `A` phải là một siêu kiểu trực tiếp `sealed` phù hợp |
| `private static final class Helper` | **Hợp lệ với member class** | Lớp phải nằm trong thân một kiểu phù hợp, không thể là top-level |
| `static abstract class Nested` | **Hợp lệ với member class** | Là static nested class trừu tượng |
| `abstract final class A` | **Sai** | Vừa cần kế thừa để hoàn thiện vừa cấm kế thừa |
| `final sealed class A` | **Sai** | `final` chặn mọi lớp con, `sealed` định nghĩa các lớp con được phép |
| `sealed non-sealed class A` | **Sai** | Không thể vừa đóng và vừa mở cùng nhánh trực tiếp |
| `final non-sealed class A` | **Sai** | `final` cấm kế thừa; `non-sealed` mở kế thừa |
| `non-sealed class A`, không có siêu kiểu `sealed` trực tiếp | **Sai** | `non-sealed` không có siêu kiểu sealed để nới lỏng |
| `private class A` ở cấp tệp | **Sai** | `private` không phải top-level class modifier |
| `protected class A` ở cấp tệp | **Sai** | `protected` không phải top-level class modifier |
| `static class A` ở cấp tệp | **Sai** | Không tồn tại static top-level class |
| `public private class A` | **Sai** | Hai mức truy cập đối nghịch; ở top-level còn vi phạm quy tắc `private` |
| `public public class A` | **Sai** | Lặp modifier `public` |

Các dòng trong bảng mô tả **mẫu khai báo**, không phải những khai báo nên đặt chung trong một tệp: nhiều mẫu cùng dùng tên `A` nhằm so sánh. Khi thử từng mẫu, cần bảo đảm không trùng tên trong cùng package và tuân thủ tên tệp nếu mẫu có `public`.

### 8.2. Vì sao `abstract final` sai?

```java
abstract final class Impossible {
}
```

`abstract` nghĩa là không thể khởi tạo trực tiếp và thường hướng tới việc lớp con kế thừa/hoàn thiện. `final` cấm mọi lớp con. JLS cấm tổ hợp này **dù thân lớp không có phương thức abstract nào**.

Cách sửa tùy mục đích:

- Cần **lớp cơ sở** cho phép mở rộng, không tạo trực tiếp: dùng `abstract class Base`.
- Cần **chặn kế thừa** và vẫn cho phép khởi tạo: dùng `final class Value`.
- Cần **kiểm soát một số lớp con nhất định**: dùng `sealed class Base permits ...` và khai báo các lớp con phù hợp.

Không có thứ tự sắp xếp modifier nào khiến `abstract final` hợp lệ; đổi thành `final abstract` vẫn sai.

### 8.3. Vì sao `final sealed`, `sealed non-sealed` và `final non-sealed` sai?

```java
final sealed class FrozenHierarchy { }          // SAI
sealed non-sealed class ConflictingHierarchy { } // SAI
final non-sealed class OpenYetFinal { }          // SAI
```

Ba trạng thái `final`, `sealed`, `non-sealed` xác định **ba cách quản lý sự kế thừa tại nhánh lớp**: đóng hoàn toàn, cho phép có chọn lọc hoặc mở rộng tự do sau một sealed parent. Java không cho phép lấy hai trạng thái đó gắn đồng thời lên **một khai báo lớp**.

Riêng `abstract` có thể đi cùng `sealed` hoặc `non-sealed` vì nó nêu một trục khác: **khả năng tạo thể hiện trực tiếp**.

### 8.4. Vì sao `non-sealed` đứng riêng là sai?

```java
non-sealed class FreeClass { }  // SAI: không có sealed direct supertype
```

Từ `non-sealed` không phải cách viết thay thế cho lớp bình thường. Với lớp thông thường muốn cho phép kế thừa, **chỉ cần không khai báo `final` hoặc `sealed`**:

```java
class FreeClass { }             // HỢP LỆ
```

Chỉ khai báo `non-sealed` khi lớp là **con trực tiếp của sealed class hoặc kiểu trực tiếp triển khai sealed interface**, và cần cho phép các lớp con sâu hơn.

### 8.5. Vì sao một lớp con của `sealed` phải đánh dấu trạng thái kế thừa?

Đoạn sau **sai** dù `Leaf` đã nằm trong `permits`:

```java
sealed class Root permits Leaf { }

class Leaf extends Root { }     // SAI: thiếu final / sealed / non-sealed
```

Ví dụ sửa:

```java
sealed class Root permits Leaf { }

final class Leaf extends Root { }    // HỢP LỆ
```

Nếu muốn `Leaf` có lớp con tiếp tục theo kế thừa thông thường, dùng `non-sealed class Leaf extends Root { }`. Nếu muốn `Leaf` tự kiểm soát lớp con của nó, dùng `sealed class Leaf extends Root permits ...` và khai báo nhánh hợp lệ.

Một kiểu `sealed` **không nhất thiết phải là abstract**. Nếu `Root` không có `abstract` và constructor có thể truy cập, `new Root()` có thể hợp lệ; `sealed` chỉ hạn chế **ai được kế thừa trực tiếp**.

## 9. Các từ khóa dễ nhầm là class modifier

Không phải mọi từ khóa xuất hiện trong thân lớp đều được phép đặt trước khai báo `class`.

| Từ khóa | Thường dùng ở đâu? | Có phải modifier của top-level class thông thường? |
| --- | --- | --- |
| `static` | Field, method và member/nested class | **Không** |
| `synchronized` | Method hoặc câu lệnh `synchronized (...) { ... }` | **Không** |
| `native` | Method gắn với triển khai native | **Không** |
| `transient` | Field (liên quan serialization mặc định) | **Không** |
| `volatile` | Field để thể hiện các quy tắc hiển thị/thứ tự truy cập của Java Memory Model | **Không** |
| `default` | Method `default` của interface hoặc nhánh `default` trong `switch` | **Không** |
| `strictfp` | Class/interface/method theo cú pháp lịch sử | **Có**, nhưng dư thừa từ Java 17 |
| `extends` | Mệnh đề chỉ định superclass hoặc interface kế thừa tùy loại khai báo | **Không**, là phần khác của khai báo |
| `implements` | Mệnh đề lớp triển khai interface | **Không**, là phần khác của khai báo |
| `permits` | Mệnh đề lớp/interface sealed liệt kê các direct permitted subtypes | **Không**, là phần khác của khai báo |

Ví dụ không hợp lệ:

```java
synchronized class Task { }    // SAI: synchronized không áp dụng cho class
native class NativeTask { }    // SAI: native không áp dụng cho class
volatile class State { }       // SAI: volatile không áp dụng cho class
transient class Data { }       // SAI: transient không áp dụng cho class
```

Một field `volatile` nằm **trong** lớp có thể hoàn toàn hợp lệ, nhưng điều đó không khiến `volatile` trở thành modifier của lớp.

**Về `strictfp`:** Trước Java 17, modifier này có liên quan đến việc yêu cầu đánh giá biểu thức dấu phẩy động theo ngữ nghĩa nghiêm ngặt. Kể từ Java 17, Java sử dụng ngữ nghĩa dấu phẩy động nghiêm ngặt nhất quán, nên `strictfp` được xem là **lỗi thời về tác dụng**, dù cú pháp vẫn được chấp nhận trong các vị trí hỗ trợ và `javac` có thể cảnh báo. Mã Java 17 mới hầu như không cần khai báo `strictfp`.

**Về `@Deprecated`:** annotation được viết trước khai báo:

```java
@Deprecated
public class LegacyApi {
}
```

Đây là cú pháp hợp lệ nếu nằm trong tệp `LegacyApi.java`. Annotation bổ sung metadata; nó không thay thế `public`, `final`, `abstract` hoặc những quy tắc về kế thừa của lớp.

## 10. Kiểu khai báo khác lớp thông thường: interface, record và enum

Khi chuyển từ `class` sang `interface`, `record` hoặc `enum`, đừng áp dụng máy móc toàn bộ bộ modifier của lớp thông thường.

- **Interface:** interface về bản chất mang tính trừu tượng và không được khai báo `final`. Nó có thể là `sealed` hoặc `non-sealed` khi thỏa quy tắc; các lớp **trực tiếp implements** một sealed interface phải tuân thủ việc đánh dấu `final`, `sealed` hoặc `non-sealed` nếu là những lớp thông thường. Member types khai báo trong interface có những quy tắc modifier ngầm định, chẳng hạn member class được xem là `public static`.
- **Record:** record class có tính chất **final** theo ngôn ngữ, không được `extends` một lớp tùy ý và không được khai báo `abstract`. Mục đích chính của record là mô hình dữ liệu có cấu trúc; không dùng `sealed`/`non-sealed` cho bản thân record class để tạo nhánh kế thừa.
- **Enum:** enum có quy tắc riêng về khả năng kế thừa và các hằng enum; không thể tùy tiện `extends` enum bằng một class khác.
- **Annotation type:** `@interface` là khai báo kiểu annotation, không phải khai báo `class` thông thường; tập modifier hợp lệ cần xét theo quy tắc annotation.

Mục tiêu thực tế là luôn kiểm tra **loại khai báo** trước khi lựa chọn modifier. Phần lớn ví dụ trong bài tập trung vào **class declaration** để không nhầm các quy tắc đặc thù của từng loại kiểu.

## 11. Hướng dẫn chẩn đoán lỗi `javac`

Khi gặp lỗi liên quan class modifier:

1. **Nhìn nơi mở đầu khai báo:** `class A` đang ở cấp tệp, trong thân class/interface, hay trong phương thức?
2. **Tách nhóm modifier:** access (`public`/`private`/`protected`), khả năng tạo/kế thừa (`abstract`, `final`, `sealed`, `non-sealed`), ngữ cảnh lồng nhau (`static`).
3. **Kiểm tra xung đột:** đặc biệt `abstract final`, mọi tổ hợp từng cặp `final`/`sealed`/`non-sealed`, và access modifier trùng hoặc mâu thuẫn.
4. **Kiểm tra `extends`/`implements`:** lớp `final` có bị kế thừa không; lớp `non-sealed` có direct sealed supertype không; direct subclass của sealed type có đánh dấu đúng không và có được cho phép không?
5. **Kiểm tra tên tệp nếu `public` top-level:** `public class Report` thuộc `Report.java` theo quy tắc biên dịch thông thường.
6. **Đọc thông báo lỗi thực tế:** `javac` thường chỉ ra dòng khai báo bị lỗi. Thông điệp cụ thể phụ thuộc JDK; không cần học thuộc từng chữ của thông báo.

Ví dụ thực hành:

```java
// SAI khi khai báo top-level:
public static final class Toolbox { }
```

Đọc theo checklist: `public` hợp lệ top-level; `final` cũng hợp lệ; **`static` không hợp lệ ở top-level**. Sửa:

```java
// File: Toolbox.java
public final class Toolbox {
    private Toolbox() {
    }

    public static String hello() {
        return "Hello";
    }
}
```

`Toolbox` giờ là lớp top-level `public final` hợp lệ, có phương thức tiện ích static và constructor private để ngăn gọi constructor từ bên ngoài lớp. Mục đích tạo utility class **không đòi modifier `static` trên chính lớp**.

Nếu muốn `static class Toolbox`, khai báo nó thành **member class** bên trong lớp bao ngoài:

```java
class Container {
    static final class Toolbox {
        static String hello() {
            return "Hello";
        }
    }
}
```

Trong trường hợp này, `Toolbox` là static nested class; khác với top-level `Toolbox` về vị trí và tên kiểu.

## 12. Bài tự luyện có đáp án

**Bài 1.** Những modifier nào trong khai báo sau không hợp lệ nếu lớp nằm trực tiếp trong tệp nguồn?

```java
private static final class Cache { }
```

**Đáp án:** `private` và `static` không hợp lệ đối với **top-level class**; `final` riêng lẻ hợp lệ. Nếu chuyển `Cache` vào trong thân một class, tổ hợp `private static final` có thể hợp lệ.

**Bài 2.** Khai báo `abstract sealed class Base permits Child` có thể hợp lệ không? Lớp con `Child` có bắt buộc cũng `abstract`?

**Đáp án:** Có thể hợp lệ nếu các điều kiện `sealed` và lớp con trực tiếp được đáp ứng. `Child` **không bắt buộc abstract**; chẳng hạn `final class Child extends Base { }` hợp lệ nếu không còn phương thức abstract nào chưa triển khai.

**Bài 3.** Vì sao `non-sealed class A { }` thường bị lỗi, còn `class A { }` không bị?

**Đáp án:** `non-sealed` phải thuộc một nhánh **trực tiếp kế thừa/triển khai sealed type**, trong khi lớp thông thường cho phép kế thừa theo mặc định và không cần modifier đặc biệt đó.

**Bài 4.** Xét:

```java
sealed class A permits B { }
non-sealed class B extends A { }
class C extends B { }
```

Khai báo có hợp lệ không? **Có.** `B` là nhánh trực tiếp được phép của `A` và được đánh dấu `non-sealed`; `C` kế thừa `B` theo quy tắc thông thường. `C` không cần có trong `A permits ...`.

**Bài 5.** `final class Config` và `final String name` có cùng ý nghĩa không?

**Đáp án:** Không. Modifier `final` của lớp cấm lớp con; modifier `final` của biến cấm gán lại biến sau khi được khởi tạo đúng quy tắc. Nó không tự động làm tất cả trạng thái đối tượng bất biến.

**Bài 6.** Có thể dùng `private class Helper` và `protected static class Formatter` trong cùng một tệp Java không?

**Đáp án:** Có, **nếu các lớp đó là member classes nằm trong thân một lớp bao ngoài** và những modifier tương ứng hợp lệ. Không được dùng chúng trực tiếp ở cấp tệp.

## Tổng kết

Hãy ghi nhớ bốn quy tắc nền tảng:

- **Top-level class:** có thể `public` hoặc package-private (bỏ access modifier); **không thể `private`, `protected` hay `static`**.
- **Khả năng tạo/kế thừa:** `abstract` không cho tạo trực tiếp, `final` cấm kế thừa, `sealed` chỉ cho những lớp con trực tiếp được phép, còn `non-sealed` mở lại kế thừa từ một sealed direct supertype.
- **Tổ hợp sai:** `abstract final`; mọi cặp trong `final`, `sealed`, `non-sealed`; và modifier không phù hợp vị trí khai báo. `abstract sealed` và `abstract non-sealed` có thể hợp lệ.
- **Member class khác top-level class:** lớp thành viên có thể dùng `private`, `protected`, `static` trong các ngữ cảnh phù hợp. Mỗi khai báo còn phải tuân thủ tên tệp, quyền truy cập và hợp đồng lớp con của sealed type.
