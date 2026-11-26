# Ngữ cảnh khởi tạo sớm và các giới hạn truy cập this, super cùng phương thức instance

## Trạng thái tính năng và mục tiêu

**Flexible Constructor Bodies** cho phép viết các câu lệnh trong constructor trước lời gọi constructor tường minh `super(...)` hoặc `this(...)`. Những câu lệnh này hữu ích để kiểm tra tham số, chuẩn hóa dữ liệu, tính toán đối số cho constructor kế tiếp và khởi tạo một số field của chính lớp đang được tạo.

Tính năng được giới thiệu ở Java 22 nhưng chỉ ở dạng preview. Lộ trình là:

| JDK | JEP | Trạng thái |
|---|---|---|
| 22 | [JEP 447](https://openjdk.org/jeps/447) — Statements before `super(...)` | Preview lần đầu |
| 23 | [JEP 482](https://openjdk.org/jeps/482) — Flexible Constructor Bodies | Preview lần thứ hai |
| 24 | [JEP 492](https://openjdk.org/jeps/492) — Flexible Constructor Bodies | Preview lần thứ ba |
| 25 | [JEP 513](https://openjdk.org/jeps/513) — Flexible Constructor Bodies | Final, chính thức |
| 26–27 | JEP 513 | Stable, không cần preview |

Tại ngày 25/11/2026, JDK 27 đã GA từ ngày 15/09/2026 và JDK 25 là LTS mới nhất. Vì vậy, các ví dụ trong bài dùng cú pháp final của JDK 25 trở lên; không cần bật `--enable-preview`.

## Vì sao constructor cần phần prologue?

Trước JDK 25, constructor thông thường phải bắt đầu bằng lời gọi `this(...)`, `super(...)`, hoặc lời gọi `super()` ngầm định. Điều này gây khó khăn khi lớp con cần xác thực dữ liệu trước khi gọi constructor của lớp cha.

Ví dụ, lớp `Employee` kế thừa `Person` và cần kiểm tra tuổi trước khi chuyển tuổi cho constructor của lớp cha. Trước đây, việc kiểm tra thường phải đặt sau `super(...)`, hoặc phải đưa logic kiểm tra vào một phương thức static được gọi ngay trong danh sách đối số của `super(...)`.

Từ JDK 25, có thể viết trực tiếp:

```java
class Person {
    private final int age;

    Person(int age) {
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
        this.age = age;
    }
}

class Employee extends Person {
    private final String employeeId;

    Employee(int age, String employeeId) {
        if (age < 18 || age > 67) {
            throw new IllegalArgumentException("employee age must be 18..67");
        }
        String normalizedId = java.util.Objects.requireNonNull(employeeId).trim();
        if (normalizedId.isEmpty()) {
            throw new IllegalArgumentException("employeeId must not be blank");
        }

        super(age);
        this.employeeId = normalizedId;
    }
}
```

Các câu lệnh kiểm tra và chuẩn hóa nằm trước `super(age)`. Nếu tham số không hợp lệ, constructor ném exception ngay và không cần bắt đầu khởi tạo phần lớp cha.

## Prologue, constructor invocation và epilogue

Thân constructor có thể có hai vùng:

- **Prologue:** các câu lệnh đứng trước lời gọi constructor tường minh.
- **Epilogue:** các câu lệnh đứng sau lời gọi constructor tường minh.

```java
class Child extends Parent {
    Child(Input input) {
        // Prologue: early construction context
        validate(input);
        Prepared prepared = prepare(input);

        super(prepared);

        // Epilogue: late construction context
        initializeAfterParent();
    }
}
```

Lời gọi constructor tường minh có thể là:

- `super(arguments...)`: gọi constructor của lớp cha trực tiếp.
- `this(arguments...)`: gọi một constructor khác trong cùng lớp.

Một constructor có tối đa một lời gọi constructor tường minh. Lời gọi này phải xuất hiện ở cấp cao nhất của thân constructor, không thể đặt trong `if`, `switch`, vòng lặp hoặc `try` để chọn nhiều constructor theo nhánh.

Không được dùng `return` trong prologue để bỏ qua lời gọi constructor. Có thể ném exception trong prologue để kết thúc quá trình tạo object khi tham số không hợp lệ; nếu không có exception, luồng khởi tạo phải đi tới constructor invocation.

Nếu constructor không có lời gọi tường minh, Java vẫn chèn `super()` ngầm định ở đầu theo quy tắc thông thường. Các câu lệnh trong constructor khi đó thuộc epilogue; chúng không tự trở thành prologue. Muốn chạy câu lệnh trước constructor lớp cha, hãy viết rõ `super(...)` hoặc `super()` sau phần prologue.

Ví dụ có constructor lớp cha không có constructor mặc định:

```java
class Message {
    Message(String value) { }
}

class UserMessage extends Message {
    UserMessage(String raw) {
        String value = java.util.Objects.requireNonNull(raw).strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("message is blank");
        }

        super(value);
    }
}
```

Không thể bỏ `super(value)` trong ví dụ này vì `Message` không có constructor không tham số để Java chèn `super()` ngầm định.

## Early Construction Context là gì?

**Early construction context** (ngữ cảnh khởi tạo sớm) bao gồm:

1. Các biểu thức đối số của lời gọi `super(...)` hoặc `this(...)`.
2. Các câu lệnh trong prologue, tức các câu lệnh trước lời gọi đó.

Đây là giai đoạn đối tượng đang được tạo nhưng constructor của lớp cha hoặc constructor được ủy quyền chưa hoàn tất. Vì vậy, code trong ngữ cảnh này không được sử dụng đối tượng hiện tại theo cách có thể quan sát trạng thái chưa hoàn chỉnh.

Sau khi lời gọi constructor hoàn tất, các câu lệnh còn lại nằm trong **late construction context** (ngữ cảnh khởi tạo muộn). Trong giai đoạn này, constructor có thể sử dụng `this` và các thành viên instance theo quy tắc Java thông thường.

```text
Constructor của lớp con
        |
        v
Prologue + đối số super(...) / this(...)
        |
        | Early construction context
        | - kiểm tra tham số
        | - tính toán giá trị
        | - gán một số field chưa khởi tạo của lớp hiện tại
        | - không đọc/truy cập instance tùy ý
        v
super(...) hoặc this(...)
        |
        v
Constructor được gọi hoàn tất
        |
        v
Epilogue
        |
        | Late construction context
        | - dùng this
        | - đọc field
        | - gọi instance method
        v
Constructor kết thúc
```

## Những gì bị cấm trong early construction context

### Không được tham chiếu `this` để đọc hoặc sử dụng đối tượng

Các cách sau không hợp lệ trong prologue:

```java
class Account {
    private int balance;

    Account(int initialBalance) {
        System.out.println(this); // Lỗi: tham chiếu đối tượng đang tạo
        int current = this.balance; // Lỗi: đọc field của instance hiện tại
        this.printBalance(); // Lỗi: gọi instance method
        printBalance(); // Lỗi: gọi instance method không ghi this
        super();
    }

    void printBalance() {
        System.out.println(balance);
    }
}
```

Quy tắc không chỉ cấm từ khóa `this`. Một lời gọi instance method không ghi `this` vẫn ngầm dùng đối tượng hiện tại nên cũng bị cấm. Tương tự, đọc field instance bằng tên đơn giản cũng là truy cập đối tượng hiện tại.

### Không được đọc field của lớp hiện tại hoặc lớp cha

Trong early construction context, không thể đọc field của instance đang tạo, kể cả field được khai báo trong lớp cha:

```java
class Base {
    protected int baseValue = 10;
}

class Derived extends Base {
    private int value;

    Derived(int input) {
        int a = this.value; // Lỗi: đọc field của Derived
        int b = baseValue;  // Lỗi: đọc field kế thừa từ Base
        int c = super.baseValue; // Lỗi: truy cập field qua super
        super();
    }
}
```

Ngay cả khi field có initializer hoặc đã được gán ở một nơi khác, prologue không được đọc field của đối tượng đang tạo. Hãy dùng tham số constructor hoặc biến local làm dữ liệu đầu vào cho phép tính.

### Không được truy cập thành viên qua `super`

Trong early construction context, không được dùng `super` để đọc field, gọi method hoặc tạo method reference tới thành viên của lớp cha:

```java
class Parent {
    int code;

    void refresh() { }
}

class Child extends Parent {
    Child() {
        int value = super.code; // Lỗi
        super.refresh();        // Lỗi
        Runnable task = super::refresh; // Lỗi
        super();
    }
}
```

Lời gọi constructor `super(...)` vẫn hợp lệ và là mục đích của cú pháp này. Điều bị cấm là dùng `super` để truy cập thành viên của instance trước khi constructor lớp cha chạy.

### Không được tạo inner class cần instance hiện tại làm enclosing instance

Trong prologue của lớp `Outer`, biểu thức `new Inner()` ngầm tương đương với `this.new Inner()`. Vì vậy, nó cần đối tượng `Outer` đang được tạo và không hợp lệ:

```java
class Outer {
    class Inner { }

    Outer() {
        Inner inner = new Inner(); // Lỗi: cần this của Outer
        super();
    }
}
```

## Ngoại lệ quan trọng: gán field chưa được khởi tạo của chính lớp

JEP 513 cho phép một ngoại lệ có giới hạn: trong prologue, constructor có thể gán trực tiếp field instance được khai báo trong chính lớp đó, nếu field chưa có initializer.

Ví dụ:

```java
class Base {
    Base() {
        printState();
    }

    void printState() {
        System.out.println("Base");
    }
}

class Child extends Base {
    private final String name; // Không có initializer

    Child(String name) {
        this.name = java.util.Objects.requireNonNull(name);
        super();
    }

    @Override
    void printState() {
        System.out.println(name);
    }
}

class Demo {
    public static void main(String[] args) {
        new Child("Java");
    }
}
```

Kết quả:

```text
Java
```

`Child.name` được gán trước khi `Base()` chạy. Khi constructor lớp cha gọi phương thức đã được override, phương thức `Child.printState()` nhìn thấy giá trị hợp lệ của `name`, thay vì giá trị mặc định `null`.

Đây là ngoại lệ có mục đích, không phải quyền truy cập `this` tổng quát. Cần phân biệt rõ:

| Biểu thức trong prologue | Hợp lệ? | Lý do |
|---|---|---|
| `this.name = input;` | Có, nếu `name` là field của lớp hiện tại và không có initializer | Gán trực tiếp field chưa được khởi tạo. |
| `name = input;` | Có trong cùng điều kiện | Là phép gán đơn tới field của lớp hiện tại. |
| `String old = this.name;` | Không | Đọc field của đối tượng đang tạo. |
| `this.name += suffix;` | Không | Phép gán ghép phải đọc giá trị cũ. |
| `this.name++;` | Không | Toán tử tăng vừa đọc vừa ghi field. |
| `this.parentField = input;` | Không | Field được khai báo trong lớp cha. |
| `this.name = normalize(input);` | Có trong cùng điều kiện | Vế phải dùng dữ liệu độc lập, vế trái gán field chưa khởi tạo. |

Field có initializer không được gán lại trong prologue theo ngoại lệ này:

```java
class Example extends Base {
    private String label = "default";

    Example(String label) {
        this.label = label; // Lỗi: field đã có initializer
        super();
    }
}
```

Nếu cần chuẩn hóa giá trị trước `super(...)`, hãy dùng biến local rồi gán field sau lời gọi constructor:

```java
class Example extends Base {
    private String label = "default";

    Example(String raw) {
        String normalized = java.util.Objects.requireNonNull(raw).strip();
        super();
        this.label = normalized;
    }
}
```

## Những gì được phép trong prologue

Các câu lệnh không tham chiếu tới instance đang tạo vẫn có thể chạy trước `super(...)` hoặc `this(...)`:

- Kiểm tra tham số và ném exception nếu dữ liệu không hợp lệ.
- Khai báo biến local và tính toán giá trị trung gian.
- Gọi static method, truy cập static field.
- Tạo hoặc sử dụng đối tượng độc lập được truyền qua tham số hoặc biến local.
- Chuẩn hóa, chuyển đổi hoặc phân tích dữ liệu đầu vào.
- Gán field chưa có initializer của chính lớp đang tạo theo ngoại lệ đã trình bày.

Ví dụ tính toán một giá trị dùng chung cho nhiều đối số của constructor lớp cha:

```java
class Shape {
    Shape(int width, int height, long area) { }
}

class Rectangle extends Shape {
    Rectangle(String rawWidth, String rawHeight) {
        int width = parsePositive(rawWidth);
        int height = parsePositive(rawHeight);
        long area = (long) width * height;

        if (area > 1_000_000L) {
            throw new IllegalArgumentException("rectangle is too large");
        }

        super(width, height, area);
    }

    private static int parsePositive(String raw) {
        int value = Integer.parseInt(raw);
        if (value <= 0) {
            throw new IllegalArgumentException("dimension must be positive");
        }
        return value;
    }
}
```

`parsePositive` là static method nên không cần instance `Rectangle`. Các biến `width`, `height`, `area` là local variable, có thể được dùng để chuẩn bị đối số cho `super(...)`.

## Dùng prologue trước `this(...)` để ủy quyền constructor

Flexible Constructor Bodies cũng cho phép có câu lệnh trước lời gọi constructor khác trong cùng lớp. Cách này hữu ích khi cần chuẩn hóa hoặc kiểm tra dữ liệu trước khi ủy quyền:

```java
class User {
    private final String name;
    private final String role;

    User(String rawName) {
        String normalized = java.util.Objects.requireNonNull(rawName).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name is blank");
        }

        this(normalized, "USER");
    }

    User(String name, String role) {
        this.name = name;
        this.role = role;
    }
}
```

Prologue của constructor thứ nhất chỉ sử dụng tham số và biến local. `this(normalized, "USER")` chuyển việc khởi tạo field cho constructor hai tham số. Không được tự gán field instance trước `this(...)` như một cách bỏ qua constructor được ủy quyền.

## Constructor của record và enum

Record có quy tắc constructor riêng:

- Record không cho constructor gọi `super(...)` tường minh.
- Non-canonical constructor phải gọi canonical constructor bằng `this(...)`.
- Từ JDK 25, non-canonical constructor có thể có prologue trước `this(...)` để kiểm tra hoặc chuyển đổi tham số.

Ví dụ:

```java
record Point(int x, int y) {
    Point(String text) {
        String[] parts = text.split(",");
        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected x,y");
        }

        int parsedX = Integer.parseInt(parts[0].strip());
        int parsedY = Integer.parseInt(parts[1].strip());
        this(parsedX, parsedY);
    }
}
```

Constructor canonical của record chịu trách nhiệm khởi tạo các component field. Không chuyển quy tắc gán field trước `super(...)` của class thường sang compact canonical constructor của record.

Constructor của enum cũng có thể dùng prologue trước `this(...)` để chuẩn hóa hoặc kiểm tra tham số khi ủy quyền cho constructor khác trong cùng enum. Constructor enum không gọi trực tiếp constructor của `Enum` bằng `super(...)` trong mã nguồn.

## Nested class: khi nào được dùng enclosing instance?

Một nested class có thể truy cập instance của lớp bao ngoài vì enclosing instance đã tồn tại trước khi instance của nested class được tạo. Do đó, trong early construction context của `Inner`, việc truy cập `Outer.this` có thể hợp lệ:

```java
class Outer {
    private int counter;

    void record() {
        counter++;
    }

    class Inner {
        Inner() {
            Outer.this.record();
            super();
        }
    }
}
```

`Outer.this` tham chiếu tới enclosing instance, không phải instance `Inner` đang được tạo. Tuy nhiên, trong prologue của `Outer`, `new Inner()` vẫn không hợp lệ vì nó cần chính `this` của `Outer` làm enclosing instance.

## Preview trên JDK 27 và ranh giới với tính năng khác

Flexible Constructor Bodies không còn là preview trên JDK 27. JEP 513 đã final từ JDK 25, nên các ví dụ của bài không cần bật preview.

JDK 27 có preview language feature **Primitive Types in Patterns, `instanceof`, and `switch` (JEP 532, fifth preview)**. Nếu thử tính năng đó, phải dùng đúng compiler JDK 27 và bật preview ở cả compile lẫn run:

```shell
javac --enable-preview --release 27 PreviewPatterns.java
java --enable-preview PreviewPatterns
```

JEP 532 không thay đổi quy tắc Flexible Constructor Bodies. Không bật preview chỉ để dùng prologue hoặc early construction context.

Ngoài ra, Oracle Java 27 Language Guide có ghi chú về một thay đổi preview riêng: khi bật preview trong build tương ứng, code constructor của record cũng được xem là early construction context như value class. Đây không phải quy tắc stable của JEP 513 và không được áp dụng cho ví dụ class thông thường trong bài. Nếu thử behavior preview trên build JDK 27 tương ứng, dùng `javac --enable-preview --release 27` và `java --enable-preview`; class file preview chỉ dùng với đúng release đã biên dịch.

**Value Classes and Objects (JEP 401)** thuộc hướng phát triển Valhalla. JEP này được nhắm tới JDK 28 dưới dạng preview; các build Valhalla early-access có thể dựa trên nền JDK khác với bản JDK GA. Không xem JEP 401 hoặc thay đổi record trong Valhalla là API stable của JDK 27. Nếu thử bản Valhalla preview, phải dùng đúng build được chỉ định và bật `--enable-preview` ở cả compile lẫn run.

## Lưu ý thiết kế và giới hạn

- **Không gọi instance method trước `super(...)`.** Hãy dùng static helper hoặc biến local. Điều này tránh quan sát một phần trạng thái của object.
- **Chỉ gán field đúng điều kiện.** Field phải được khai báo trong chính lớp hiện tại và không có initializer; không dùng ngoại lệ này để đọc field hoặc sửa field của lớp cha.
- **Ưu tiên fail fast.** Kiểm tra tham số trước khi gọi constructor lớp cha giúp tránh thực hiện công việc khởi tạo không cần thiết.
- **Cẩn thận với side effect.** Nếu prologue ghi file, cập nhật hệ thống bên ngoài hoặc thay đổi trạng thái dùng chung rồi `super(...)` thất bại, side effect đó vẫn đã xảy ra.
- **Không đặt lời gọi constructor trong nhánh điều kiện.** Một constructor chỉ có một constructor invocation ở vị trí được grammar cho phép.
- **Constructor lớp cha gọi method override vẫn là rủi ro thiết kế.** Gán field trước `super(...)` có thể bảo vệ những field được gán theo quy tắc, nhưng cách an toàn hơn vẫn là tránh gọi method có thể override từ constructor của lớp cha.
- **Không nhầm prologue với static method.** Prologue không phải static context thông thường; nó có các quy tắc early construction riêng, bao gồm ngoại lệ gán field hẹp.

## Tài liệu tham khảo

- [JEP 447 — Statements before `super(...)` (JDK 22 Preview)](https://openjdk.org/jeps/447)
- [JEP 482 — Flexible Constructor Bodies (JDK 23 Preview)](https://openjdk.org/jeps/482)
- [JEP 492 — Flexible Constructor Bodies (JDK 24 Preview)](https://openjdk.org/jeps/492)
- [JEP 513 — Flexible Constructor Bodies (JDK 25 Final)](https://openjdk.org/jeps/513)
- [Oracle Java SE 27 Language Guide — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html)
- [Java Language Specification, Java SE 27 — Constructor Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.8)
- [Java SE 27 Language Changes Summary](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [Java SE 27 Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [JEP 532 — Primitive Types in Patterns, `instanceof`, and `switch` (JDK 27 Fifth Preview)](https://openjdk.org/jeps/532)
- [JEP 401 — Value Classes and Objects (Valhalla Preview)](https://openjdk.org/jeps/401)
- [Inside.java — JDK 28: Value Classes (JEP 401 Preview)](https://inside.java/2026/10/27/quality-heads-up/)
