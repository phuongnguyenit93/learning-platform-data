# Phương thức đối tượng và đối tượng nhận lời gọi trong Java

## 1. Phương thức đối tượng dùng để làm gì?

Trong Java, **phương thức đối tượng** (*instance method*) mô tả hành vi gắn với một **đối tượng cụ thể**. Ví dụ, hai tài khoản ngân hàng đều hỗ trợ hành vi `deposit` (nạp tiền), nhưng khi gọi phương thức trên tài khoản nào thì số dư của tài khoản ấy được thay đổi.

```java
Account first = new Account("Mai", 100);
Account second = new Account("Nam", 30);

first.deposit(20);  // Tác động lên first: 100 -> 120.
second.deposit(5);  // Tác động lên second: 30 -> 35.
```

Đoạn trên minh họa một lời gọi, giả sử `Account` có constructor và phương thức `deposit` tương ứng; **chưa phải chương trình độc lập**. Điểm chính không nằm ở tên method `deposit`, mà ở phần **`first` hoặc `second` đứng trước dấu chấm**. Đối tượng được chọn làm nơi tiếp nhận lời gọi này được gọi là **đối tượng nhận lời gọi** (*receiver*).

Với cú pháp `first.deposit(20)`:

- `first` là **biểu thức receiver** (*receiver expression*). Nó được đánh giá để lấy một tham chiếu.
- Đối tượng mà tham chiếu đó trỏ tới là **receiver object** của lần gọi method.
- `deposit` là **tên phương thức**.
- `20` là **đối số** được truyền cho tham số của phương thức.
- Phương thức thực thi dựa trên **trạng thái của receiver** và các đối số được truyền.

**Phân biệt quan trọng:** một **biến tham chiếu** như `first` không phải là bản thân đối tượng. Hai biến khác nhau có thể cùng tham chiếu đến một receiver object; một biến cũng có thể nhận tham chiếu mới về sau.

## 2. Cú pháp khai báo và gọi một instance method

Dạng khái quát của khai báo phương thức có thân:

```java
[modifiers] ReturnType methodName(ParameterType parameter, ...) {
    // Statements
}
```

Đây là **ký pháp mô tả cú pháp**, không được biên dịch nguyên văn với dấu ngoặc vuông và `...`.

Ví dụ thực tế:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int getValue() {
        return value;
    }
}
```

Trong lớp `Counter`:

- `value` là **instance field**, tức mỗi `Counter` có một giá trị riêng.
- `increment()` là **instance method** có kiểu trả về `void`, thay đổi `value`.
- `getValue()` là **instance method** trả về `int`, quan sát `value`.
- Hai method **không có từ khóa `static`**, nên cần ngữ cảnh của một instance khi được gọi.
- Trong thân instance method, tên `value` được hiểu là field thuộc đối tượng đang nhận lời gọi; có thể viết rõ `this.value`.

Cách gọi phổ biến:

```java
Counter counter = new Counter();
counter.increment();
int current = counter.getValue();
```

Đây là mảnh mã để đặt trong method. `counter.increment()` dùng `counter` để xác định receiver. `counter.getValue()` trả lại giá trị trên **chính receiver đó**. Nếu tạo một `Counter` thứ hai, trạng thái `value` của hai instance độc lập.

Bảng phân biệt nhanh:

| Biểu thức | Đặc điểm |
| --- | --- |
| `object.method(args)` | Lời gọi instance method qua biểu thức receiver; đối tượng thực được xác định khi chạy. |
| `this.method(args)` | Gọi method trên **instance hiện tại** ở ngữ cảnh instance phù hợp. |
| `method(args)` | Lời gọi không ghi receiver tường minh; trong một instance method có thể tương đương gọi trên `this`, tùy tên nào được phân giải. |
| `ClassName.staticMethod(args)` | Gọi **static method**, gắn với lớp, không yêu cầu receiver object. |
| `super.method(args)` | Trong lớp con, yêu cầu dùng triển khai phù hợp từ superclass theo quy tắc Java; vẫn liên quan tới đối tượng `this` đang xây dựng/thực thi. |

Không phải mọi phương thức gọi qua dấu chấm đều là instance method: Java cho phép viết một lời gọi static method thông qua một biểu thức tham chiếu, nhưng đó vẫn là **static invocation**; cách viết được khuyến nghị là `ClassName.staticMethod()` để tránh hiểu nhầm về receiver.

## 3. Ví dụ chạy hoàn chỉnh: receiver quyết định đối tượng nào được thay đổi

Tạo tệp **`ReceiverDemo.java`** với toàn bộ mã sau (Java 17+):

```java
class Account {
    private final String owner;
    private int balance;

    Account(String owner, int openingBalance) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("Owner is required");
        }
        if (openingBalance < 0) {
            throw new IllegalArgumentException("Opening balance cannot be negative");
        }
        this.owner = owner;
        this.balance = openingBalance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        balance += amount;
    }

    boolean withdraw(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amount > balance) {
            return false;
        }
        balance -= amount;
        return true;
    }

    void transferTo(Account target, int amount) {
        if (target == null) {
            throw new IllegalArgumentException("Target is required");
        }
        if (this.withdraw(amount)) {
            target.deposit(amount);
        }
    }

    String summary() {
        return owner + ": " + balance;
    }
}

public class ReceiverDemo {
    public static void main(String[] args) {
        Account mai = new Account("Mai", 100);
        Account nam = new Account("Nam", 30);
        Account alias = mai;

        mai.deposit(20);
        alias.withdraw(15);
        mai.transferTo(nam, 25);

        System.out.println(mai.summary());
        System.out.println(nam.summary());
        System.out.println(mai == alias);
        System.out.println(mai == nam);
    }
}
```

Biên dịch và chạy ở thư mục chứa tệp:

```bash
javac ReceiverDemo.java
java ReceiverDemo
```

**Kết quả chính xác:**

```text
Mai: 80
Nam: 55
true
false
```

Giải thích theo từng lời gọi:

1. `new Account("Mai", 100)` và `new Account("Nam", 30)` tạo **hai đối tượng khác nhau**.
2. `mai.deposit(20)` đặt tài khoản “Mai” làm receiver, nên số dư của Mai thành `120`; tài khoản Nam vẫn `30`.
3. `alias = mai` chỉ **sao chép tham chiếu**. `alias.withdraw(15)` nhận **cùng đối tượng Mai** làm receiver, làm số dư Mai giảm xuống `105`. Nó không tạo tài khoản thứ ba.
4. `mai.transferTo(nam, 25)` gọi method với receiver là **Mai**. Trong method, `this.withdraw(25)` rút `25` từ Mai, còn `target.deposit(25)` nạp `25` cho Nam. Vì vậy hai số dư cuối là `80` và `55`.
5. `mai == alias` là `true` vì hai biến cùng trỏ tới một đối tượng; `mai == nam` là `false` vì chúng trỏ tới hai đối tượng khác nhau.

### Sơ đồ tham chiếu

```text
Biến mai ───────────┐
                    ├──> Account {owner="Mai", balance=80}
Biến alias ─────────┘

Biến nam ───────────────> Account {owner="Nam", balance=55}
```

Các method `deposit`, `withdraw`, `transferTo`, `summary` là cùng **các định nghĩa phương thức** trong lớp `Account`. Những lần gọi khác nhau sử dụng receiver khác nhau; Java không tạo riêng một bản sao mã method cho từng object.

Một hệ quả thiết kế quan trọng: **phương thức thay đổi trạng thái của “đối tượng đang nhận lời gọi”, không phải của “biến được dùng để gọi”**. Biến chỉ là đường dẫn tới object, nên gọi qua `alias` vẫn ảnh hưởng `mai`.

> Ví dụ nhằm giải thích receiver và trạng thái; không mô tả transaction ngân hàng thực tế. Nếu một chuyển khoản phải bảo đảm tính nguyên tử, đồng thời, bền vững và xử lý lỗi trung gian, cần thêm cơ chế riêng. Các cơ chế ấy không tự có chỉ vì logic được đặt trong instance method.

## 4. `this` là tham chiếu tới đối tượng đang nhận lời gọi

Trong **thân instance method**, từ khóa `this` biểu thị **đối tượng hiện tại** mà lời gọi đang thực thi trên đó. Cùng một đoạn thân method có thể nhận những `this` khác nhau ở các lần gọi.

```java
class Greeter {
    private final String name;

    Greeter(String name) {
        this.name = name;
    }

    String greeting() {
        return "Xin chào " + this.name;
    }

    void printGreeting() {
        System.out.println(this.greeting());
    }
}
```

Trong `greeting()`, `this.name` chính là field `name` của receiver. Trong `printGreeting()`, `this.greeting()` gọi thêm một instance method trên **cùng đối tượng**. Nếu viết `greeting()` mà không có `this.`, khi phân giải tên phù hợp, Java cũng ngầm lấy receiver hiện tại.

### Khi nào nên viết `this` tường minh?

Trường hợp dễ thấy nhất là khi tham số trùng tên field:

```java
class Book {
    private String title;

    Book(String title) {
        this.title = title;
    }

    void rename(String title) {
        this.title = title;
    }

    String title() {
        return this.title;
    }
}
```

`this.title` là field của receiver, còn `title` ở vế phải trong constructor/method là tham số. Nếu viết `title = title;` ở đây, cả hai tên `title` đều trỏ tới tham số, dẫn tới không cập nhật field như mong muốn.

Sử dụng `this.` trong toàn bộ code là một lựa chọn style; điều bắt buộc là phân biệt khi tên local/tham số che khuất field.

### `this` chỉ có ở ngữ cảnh instance thích hợp

```java
class Settings {
    private int version = 1;

    int readVersion() {
        return this.version; // Hợp lệ: instance method.
    }

    static String category() {
        return "settings";   // Static method không có this.
    }

    // static int invalid() {
    //     return this.version; // LỖI biên dịch nếu bỏ comment.
    // }
}
```

Static method không được truyền receiver object và không thể dùng `this` hay truy cập trực tiếp instance field như thể đã có đối tượng. Nếu static method cần đọc dữ liệu instance, nó phải nhận hoặc tạo tham chiếu cụ thể:

```java
static int read(Settings settings) {
    return settings.readVersion();
}
```

Mảnh method này được đặt **bên trong một lớp** có thể tham chiếu `Settings`. `settings` là receiver của `readVersion()`; method `read` vẫn là static.

**Không nhầm `this.method()` với `this(...)`:** dạng `this(...)` là lời gọi constructor khác của cùng lớp trong constructor, theo quy tắc vị trí riêng; nó không phải lời gọi instance method thông thường.

## 5. Receiver có thể là biểu thức, không chỉ là tên biến

Những lời gọi sau có thể hợp lệ nếu các lớp, method và kiểu trả về tương ứng được khai báo:

```java
account.deposit(10);            // Biến tham chiếu làm receiver expression.
getAccount().deposit(10);       // Kết quả method làm receiver expression.
accounts[0].deposit(10);        // Phần tử mảng làm receiver expression.
new Account("An", 10).deposit(5); // Đối tượng vừa được tạo làm receiver.
this.account.deposit(10);       // Field của instance hiện tại làm receiver.
```

Đây là **các mảnh minh họa**, không phải chương trình chạy độc lập; chúng giả định `getAccount()` trả về `Account` và các biến liên quan tồn tại. Biểu thức receiver được **đánh giá**, lấy ra giá trị tham chiếu, rồi Java tiến hành gọi method trên đối tượng nhận được.

### Ví dụ hoàn chỉnh: gọi nối tiếp và receiver thay đổi theo biểu thức

Tạo tệp **`FluentReceiverDemo.java`**:

```java
class Lamp {
    private final String label;
    private boolean on;

    Lamp(String label) {
        this.label = label;
    }

    Lamp turnOn() {
        this.on = true;
        return this;
    }

    Lamp turnOff() {
        this.on = false;
        return this;
    }

    String status() {
        return label + ": " + (on ? "ON" : "OFF");
    }
}

public class FluentReceiverDemo {
    public static void main(String[] args) {
        Lamp desk = new Lamp("Desk");
        Lamp sameLamp = desk.turnOn().turnOff().turnOn();

        System.out.println(desk.status());
        System.out.println(sameLamp.status());
        System.out.println(desk == sameLamp);
        System.out.println(new Lamp("Hall").turnOn().status());
    }
}
```

Chạy:

```bash
javac FluentReceiverDemo.java
java FluentReceiverDemo
```

```text
Desk: ON
Desk: ON
true
Hall: ON
```

`desk.turnOn()` thay đổi trạng thái của `desk` và **trả về `this`** (cùng một đối tượng), do đó lời gọi `turnOff()` sau dấu chấm tiếp tục nhận cùng object. Method `status()` cuối chuỗi vẫn được gọi trên kết quả tham chiếu của biểu thức ngay trước nó. `sameLamp == desk` là `true` vì chuỗi lời gọi không tự tạo Lamp mới. Trong dòng cuối, `new Lamp("Hall")` thật sự tạo **một object khác** rồi gọi tiếp method trên nó.

Đây là kiểu API thường gọi là **fluent interface**; cần lưu ý rằng không phải method trả về kiểu của lớp nào cũng nhất thiết trả về `this`. Nó có thể trả về một instance mới, đối tượng con hoặc `null`. Muốn hiểu receiver của mắt xích tiếp theo, phải xem **giá trị trả về thực tế** của mắt xích trước.

## 6. Biến tham chiếu, receiver object và trạng thái

Việc gọi method không “gắn vĩnh viễn” method vào tên biến được dùng trong cú pháp.

```java
Account first = new Account("A", 10);
Account second = new Account("B", 10);

Account selected = first;
selected.deposit(5);  // Receiver là object A.

selected = second;
selected.deposit(7);  // Receiver bây giờ là object B.
```

Đây là mảnh code minh họa dùng lớp `Account` ở ví dụ chính. `selected` vẫn có **kiểu tĩnh `Account`**, nhưng giá trị tham chiếu chứa trong biến đã đổi. Do đó object nhận lời gọi lần đầu khác lần sau. Sau các phép gọi, số dư A là `15` và B là `17`.

Giữa hai biến tham chiếu, phép gán không sao chép object; nó sao chép **giá trị tham chiếu**. Với các immutable object như `String`, method có thể tạo giá trị mới thay vì sửa object cũ; khác biệt này do **hành vi method và thiết kế lớp**, không phải do cách xác định receiver.

### Một instance method có thể gọi method trên object khác

Trong ví dụ `Account.transferTo`:

```java
void transferTo(Account target, int amount) {
    if (target == null) {
        throw new IllegalArgumentException("Target is required");
    }
    if (this.withdraw(amount)) {
        target.deposit(amount);
    }
}
```

Cùng một thân method chứa **hai receiver khác nhau**:

- `this.withdraw(amount)`: receiver là **tài khoản đang thực thi `transferTo`**.
- `target.deposit(amount)`: receiver là **tài khoản được tham chiếu bởi tham số `target`**.

Bởi vậy không nên nói “mọi lệnh trong một instance method đều thao tác trên `this`”. Instance method có quyền dùng `this`, nhưng cũng có thể tạo/cầm tham chiếu tới object khác và gọi method trên các object ấy.

## 7. Receiver bằng `null`: lỗi xảy ra ở thời điểm gọi instance method

Một biến có kiểu lớp hợp lệ vẫn có thể chứa giá trị `null`:

```java
Account account = null;
// account.deposit(10); // Nếu chạy: NullPointerException.
```

`null` **không trỏ tới bất kỳ đối tượng nào**. Vì thế không tồn tại receiver object để thực thi instance method `deposit`. Khi chương trình cố gọi instance method qua `null`, Java ném `NullPointerException`, trừ những hình thức đặc biệt không phải instance invocation.

### Ví dụ chạy được, chủ động bắt ngoại lệ

Tệp **`NullReceiverDemo.java`**:

```java
class Clock {
    void ring() {
        System.out.println("ring");
    }
}

public class NullReceiverDemo {
    public static void main(String[] args) {
        Clock clock = null;

        try {
            clock.ring();
        } catch (NullPointerException ex) {
            System.out.println("receiver is null");
        }

        clock = new Clock();
        clock.ring();
    }
}
```

```bash
javac NullReceiverDemo.java
java NullReceiverDemo
```

```text
receiver is null
ring
```

Compiler chấp nhận `clock.ring()` vì biến có kiểu `Clock` và lớp khai báo `ring()`, nhưng ở runtime receiver là `null` nên lỗi. Sau khi `clock` được gán tham chiếu `new Clock()`, lời gọi có object nhận hợp lệ.

Cách phòng tránh phụ thuộc hợp đồng API: từ chối `null` đầu vào bằng `Objects.requireNonNull` hoặc kiểm tra tường minh; bảo đảm field tham chiếu được khởi tạo; trả giá trị thay thế khi thích hợp; hoặc thiết kế API không để trạng thái vắng mặt xuất hiện ngoài dự kiến. Java 17 **không có toán tử truy cập null-safe `?.`** như một số ngôn ngữ khác.

### Receiver được đánh giá trước đối số, nhưng việc kiểm tra `null` cần hiểu đúng

Khi gọi `receiver.method(argumentExpression)`, Java đánh giá **biểu thức xác định receiver trước**, sau đó đánh giá các biểu thức đối số theo thứ tự từ trái sang phải, rồi thực hiện lời gọi theo quy tắc runtime. Với trường hợp lời gọi instance method trên `null`, **biểu thức đối số vẫn có thể được đánh giá trước khi `NullPointerException` được ném tại bước gọi**.

Ví dụ riêng có thể chạy để quan sát:

```java
class Printer {
    void print(int n) {
        System.out.println("number=" + n);
    }
}

public class EvaluationOrderDemo {
    static Printer findPrinter() {
        System.out.println("receiver expression");
        return null;
    }

    static int calculateArgument() {
        System.out.println("argument expression");
        return 42;
    }

    public static void main(String[] args) {
        try {
            findPrinter().print(calculateArgument());
        } catch (NullPointerException ex) {
            System.out.println("call failed");
        }
    }
}
```

Lưu thành **`EvaluationOrderDemo.java`**, sau đó:

```bash
javac EvaluationOrderDemo.java
java EvaluationOrderDemo
```

```text
receiver expression
argument expression
call failed
```

Chương trình đánh giá `findPrinter()` và nhận `null`, tiếp tục đánh giá `calculateArgument()`, rồi thất bại khi thử gọi instance method. Thứ tự này quan trọng nếu biểu thức đối số có side effect. Đừng giả định chỉ vì receiver là `null` thì các đối số chắc chắn chưa được tính.

## 8. Lớp khai báo method, kiểu tham chiếu và kiểu thực tế của receiver

Với kế thừa, cần phân biệt **kiểu tĩnh của biến/biểu thức** và **lớp runtime của object**.

```java
Animal animal = new Dog();
```

Biến `animal` có kiểu tĩnh `Animal`, nhưng object được tạo thuộc lớp `Dog`. Khi gọi instance method có thể ghi đè (*overridable instance method*), Java chọn triển khai phù hợp với **lớp thực tế của receiver** qua cơ chế **dynamic dispatch**.

Tạo tệp **`DynamicReceiverDemo.java`**:

```java
class Animal {
    String speak() {
        return "some sound";
    }

    String kind() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "woof";
    }

    String fetch() {
        return "ball";
    }
}

public class DynamicReceiverDemo {
    static String describe(Animal animal) {
        return "Animal overload";
    }

    static String describe(Dog dog) {
        return "Dog overload";
    }

    public static void main(String[] args) {
        Animal general = new Dog();
        Dog specific = new Dog();

        System.out.println(general.speak());
        System.out.println(general.kind());
        System.out.println(specific.fetch());
        System.out.println(describe(general));
        System.out.println(describe(specific));
    }
}
```

Biên dịch và chạy:

```bash
javac DynamicReceiverDemo.java
java DynamicReceiverDemo
```

```text
woof
animal
ball
Animal overload
Dog overload
```

Phân tích từng dòng:

1. `general.speak()` gọi triển khai `Dog.speak()` nên trả `woof`, bởi **object thực tế là Dog** và method này đã được override.
2. `general.kind()` chạy triển khai được kế thừa từ `Animal` do `Dog` không override `kind()`; kết quả là `animal`.
3. `specific.fetch()` hợp lệ vì biến có kiểu tĩnh `Dog`, lớp này khai báo method `fetch()`.
4. `describe(general)` chọn overload nhận `Animal` tại **thời điểm biên dịch**. Dù object trỏ tới là `Dog`, overload không tự chuyển thành `describe(Dog)`.
5. `describe(specific)` chọn overload nhận `Dog` vì kiểu tĩnh đối số là `Dog`.

Nếu viết `general.fetch()` thì **không biên dịch**, vì kiểu tĩnh `Animal` không cung cấp `fetch()`, dù object runtime là `Dog`.

### Overloading và overriding không giống nhau

| Cơ chế | Dựa vào điều gì? | Hệ quả với receiver |
| --- | --- | --- |
| **Overloading** (quá tải) | Tên phương thức, các chữ ký áp dụng và **kiểu tĩnh** của biểu thức/đối số khi biên dịch | Chọn chữ ký overload thích hợp trước khi chạy. |
| **Overriding** (ghi đè) | Lớp thực tế của receiver khi gọi instance method có khả năng override | Triển khai của lớp con có thể chạy dù biến đang mang kiểu lớp cha. |
| **Static method hiding** | Quy tắc phân giải tĩnh của phương thức `static` | Không phải dynamic dispatch theo object receiver. |
| **Private method** | Không bị override theo cơ chế kế thừa bình thường | Một method cùng tên trong lớp con không override private method của lớp cha. |

Các phương thức `final` không thể bị override; static method cũng không được override theo nghĩa đa hình runtime. Do vậy câu “mọi lời gọi `object.method()` đều chọn method bằng runtime polymorphism” là quá rộng: phải xem **method nào được chọn tại compile time, có thể override hay không, và kiểu thực tế của object**.

### `super.method()` trong lớp con

Nếu cần gọi triển khai của superclass thay vì bản override hiện tại, lớp con có thể dùng `super` trong ngữ cảnh hợp lệ:

```java
class BaseMessage {
    String message() {
        return "base";
    }
}

class CustomMessage extends BaseMessage {
    @Override
    String message() {
        return "custom+" + super.message();
    }
}
```

`new CustomMessage().message()` cho kết quả chuỗi `custom+base`. `super.message()` **không tạo instance superclass mới**; nó yêu cầu lời gọi triển khai superclass trên cùng object hiện tại theo quy tắc ngôn ngữ. Đoạn mã này là khai báo lớp minh họa, muốn in cần đặt trong `main`.

## 9. Truyền đối tượng làm tham số vẫn là truyền giá trị (*pass-by-value*)

Trong Java, tất cả đối số phương thức đều được truyền bằng **giá trị**. Nếu đối số có kiểu tham chiếu, giá trị được sao chép là **tham chiếu tới object**, không phải bản sao object.

Đây là nguồn nhầm lẫn vì method có thể sửa trạng thái object mà caller đang tham chiếu, nhưng **không thể gán lại biến tham chiếu của caller** bằng cách gán lại tham số.

Tệp **`ReferenceParameterDemo.java`**:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class ReferenceParameterDemo {
    static void change(Box box) {
        box.value += 3;
        box = new Box(99);
        System.out.println("inside=" + box.value);
    }

    public static void main(String[] args) {
        Box current = new Box(2);

        change(current);

        System.out.println("outside=" + current.value);
    }
}
```

```bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
```

```text
inside=99
outside=5
```

Ở đầu `change(current)`, tham số `box` nhận một **bản sao của tham chiếu** đang có trong `current`; cả hai tham chiếu cùng trỏ `Box(2)`. `box.value += 3` sửa object chung thành `5`. Sau đó `box = new Box(99)` chỉ đổi **biến tham số `box` trong method**, không gán lại biến `current` của caller. Vì vậy sau khi thoát method, `current.value` vẫn là `5`.

Phân biệt:

- **Thay đổi nội dung object qua tham chiếu**: người giữ tham chiếu cùng object có thể quan sát.
- **Gán lại biến tham chiếu cục bộ**: không làm biến tham chiếu tại nơi gọi đổi giá trị.
- **Tạo object mới trong method**: không tự trả object đó cho caller, trừ khi method trả tham chiếu hoặc đặt nó vào một vị trí mà caller có thể truy cập.

Trong ví dụ `Account.transferTo(nam, 25)`, tham số `target` nhận bản sao tham chiếu của `nam`; gọi `target.deposit(...)` vẫn sửa cùng tài khoản Nam. Đây là cơ chế Java pass-by-value của tham chiếu, không phải ngôn ngữ pass-by-reference theo nghĩa tham số gán lại biến caller.

## 10. Lời gọi instance method và static method: đừng nhầm đối tượng nhận lời gọi

Một **static method** có thể được gọi bằng tên lớp mà không cần một instance:

```java
class Converter {
    static int toSeconds(int minutes) {
        return minutes * 60;
    }

    int triple(int number) {
        return number * 3;
    }
}
```

Cách gọi tự nhiên:

```java
int seconds = Converter.toSeconds(2); // static, trả 120.
Converter converter = new Converter();
int result = converter.triple(4);     // instance, trả 12.
```

Tuy Java chấp nhận cú pháp gọi static method thông qua biến đối tượng trong một số trường hợp (ví dụ `converter.toSeconds(2)`), method này vẫn được phân giải là static, **không có receiver object làm `this`**, và không dùng dynamic dispatch. Viết theo tên lớp `Converter.toSeconds(2)` để ý định rõ ràng.

Một chi tiết nâng cao: biến chứa `null` đôi khi vẫn có thể dùng trong cú pháp lời gọi static method được phân giải tĩnh; điều này **không** chứng minh rằng instance method gọi qua `null` là an toàn. Thực hành tốt vẫn là gọi static bằng tên lớp để tránh nhầm và tránh side effect không cần thiết khi biểu thức trước dấu chấm được đánh giá.

| Tiêu chí | Instance method | Static method |
| --- | --- | --- |
| Khai báo | Không có `static` | Có `static` |
| Lời gọi thông dụng | `object.run()` | `TypeName.run()` |
| Có receiver object/`this`? | Có receiver phù hợp khi chạy; `this` dùng trong ngữ cảnh instance | Không có `this` |
| Truy cập instance field | Trực tiếp qua `this` hoặc tên phù hợp | Phải có tham chiếu object cụ thể |
| Ghi đè/đa hình | Có thể override khi quy tắc cho phép | Không override theo dynamic dispatch; có thể hide |
| Khi nào nên dùng | Hành vi phụ thuộc trạng thái hoặc danh tính object | Hàm tiện ích, factory, chức năng chung không cần instance |

## 11. Lỗi thường gặp khi xác định receiver

### Lỗi 1: nghĩ tên biến quyết định danh tính vĩnh viễn

`Account selected = mai;` rồi `selected = nam;` làm receiver đổi theo tham chiếu mà `selected` đang giữ ở từng thời điểm. Xem **giá trị tham chiếu**, không đoán từ cách đặt tên biến.

### Lỗi 2: dùng `this` trong static method

`this` không tồn tại ở static context. Static method phải nhận object qua tham số, truy cập static members hoặc tạo object thích hợp rồi dùng tham chiếu.

### Lỗi 3: đọc nhầm cú pháp `account.deposit(10)` thành “sao chép account rồi deposit”

Java không tạo bản sao object khi gọi instance method. Phép gọi chạy trên object được receiver tham chiếu. Nếu cần hành vi không sửa trạng thái, hãy thiết kế immutable object hoặc phương thức trả về object mới rõ ràng.

### Lỗi 4: gọi instance method trên `null`

`String text = null; text.length();` có thể biên dịch nhưng khi chạy ném `NullPointerException`. Kiểu tĩnh hợp lệ không bảo đảm receiver object tồn tại.

### Lỗi 5: tưởng `Base ref = new Derived()` làm mọi method của `Derived` đều gọi được

Trình biên dịch kiểm tra method có trong **kiểu tĩnh của receiver expression**. Nếu method chỉ có ở `Derived`, không thể gọi trực tiếp qua biến `Base`. Có thể dùng interface hoặc thiết kế API phù hợp; ép kiểu chỉ khi đã kiểm tra tính tương thích runtime.

### Lỗi 6: nhầm overload với override

`handle(Animal)` và `handle(Dog)` là hai overload, chọn theo phân giải ở compile time. `Dog.speak()` override `Animal.speak()` thì chọn triển khai theo receiver runtime. Hai cơ chế khác nhau dù đều thấy nhiều method cùng tên.

### Lỗi 7: nghĩ tham số là “tham chiếu truyền theo reference”

Java sao chép **giá trị tham chiếu**; method có thể sửa object chung nhưng gán lại biến tham số không đổi biến caller. Thử ví dụ `ReferenceParameterDemo` để quan sát sự khác biệt.

### Lỗi 8: không xác định receiver ở lời gọi lồng nhau

`service.getAccount().deposit(10)` có receiver của `getAccount()` là `service`, còn receiver của `deposit()` là **object mà `getAccount()` trả về**. Nếu method trả về `null`, lời gọi `deposit` sẽ thất bại. Phân tích lần lượt từng dấu chấm.

### Lỗi 9: gọi method ghi đè từ constructor khi object chưa khởi tạo xong

Nếu constructor của lớp cha gọi một **instance method có thể override**, runtime có thể dispatch tới method của lớp con trước khi các field initializer/constructor của lớp con hoàn thành. Receiver là **cùng object đang được xây dựng**, nhưng trạng thái lớp con có thể chưa sẵn sàng. Tránh gọi method có thể override từ constructor trừ khi hiểu rõ quy tắc và chấp nhận rủi ro.

### Lỗi 10: dùng `private` như thể chỉ truy cập được field của `this`

Trong cùng lớp, Java có thể cho phép một instance method truy cập private field của **một instance khác cùng lớp** qua biến tham chiếu phù hợp:

```java
class Point {
    private int x;

    Point(int x) {
        this.x = x;
    }

    int distanceFrom(Point other) {
        return Math.abs(this.x - other.x);
    }
}
```

`this.x` là field của receiver hiện tại, `other.x` là field của receiver **khác** nằm trong tham số. `private` bảo vệ thành phần theo phạm vi truy cập của lớp, không giới hạn thành viên chỉ được đọc từ object `this`. Đoạn code là khai báo lớp hợp lệ, không có `main`.

## 12. Tự kiểm tra với các tình huống cụ thể

**Câu 1.** Cho `Counter a = new Counter(); Counter b = a;`, sau đó gọi `a.increment(); b.increment();`. Có mấy đối tượng `Counter` được tạo? Giá trị `a.getValue()` là bao nhiêu?

**Đáp án:** Chỉ có **một đối tượng** vì chỉ một lần `new`. `a` và `b` là hai biến cùng tham chiếu object đó; giá trị cuối là `2`.

**Câu 2.** Trong `mai.transferTo(nam, 25)` của ví dụ đầu, receiver của `transferTo`, `this.withdraw` và `target.deposit` lần lượt là gì?

**Đáp án:** `transferTo` và `this.withdraw` có receiver là tài khoản Mai; `target.deposit` có receiver là tài khoản Nam.

**Câu 3.** Cho `Animal a = new Dog();`, `a.speak()` trả gì và vì sao `a.fetch()` lỗi biên dịch?

**Đáp án:** `a.speak()` trả `woof` vì instance method đã override và runtime receiver là `Dog`. `a.fetch()` bị chặn vì kiểu tĩnh của `a` là `Animal`, trong đó không có `fetch()`.

**Câu 4.** Trong `Lamp x = new Lamp("Desk"); Lamp y = x.turnOn();`, `x == y` là `true` hay `false`?

**Đáp án:** `true` vì `turnOn()` trả về `this`. Nếu thay cách triển khai để trả về `new Lamp(...)`, kết quả có thể khác; phải đọc hợp đồng method.

**Câu 5.** Cho `Box b = new Box(2); change(b);` theo `ReferenceParameterDemo`, vì sao `b.value` là `5` thay vì `99`?

**Đáp án:** `change` sửa object đang được cả hai tham chiếu trỏ tới, rồi chỉ gán lại **tham số cục bộ** thành tham chiếu một object mới. Biến `b` phía caller vẫn trỏ object ban đầu đã được đổi từ `2` sang `5`.

**Câu 6.** Nếu `Account a = null;`, lời gọi `a.summary()` xảy ra ở giai đoạn nào?

**Đáp án:** Phương thức được trình biên dịch chấp nhận theo kiểu tĩnh, nhưng khi chạy không có receiver object để gọi nên ném `NullPointerException`.

**Câu 7.** Với `new Lamp("Hall").turnOn().status()`, có bao nhiêu receiver object?

**Đáp án:** Trong ví dụ này có **một đối tượng Lamp** được tạo. `turnOn()` nhận object đó, trả về `this`, nên `status()` tiếp tục dùng cùng object. Hai **lần gọi method** không có nghĩa hai object.

**Câu 8.** `super.method()` trong instance method của lớp con có tạo một đối tượng lớp cha riêng không?

**Đáp án:** Không. Đó là một dạng lời gọi yêu cầu triển khai phù hợp từ superclass trong ngữ cảnh **cùng object**, không phải một lệnh `new`.

## 13. Cách tự truy vết một lời gọi method

Khi gặp biểu thức `someExpression.someMethod(arguments)` trong mã thực tế, hãy lần lượt xác định:

1. **Kiểu tĩnh của biểu thức phía trái dấu chấm**: compiler cho phép truy cập những thành viên nào?
2. **Biểu thức đó trả về tham chiếu nào khi chạy**: một object cụ thể, tham chiếu khác qua alias, hay `null`?
3. **Đây là lời gọi instance hay static**: chữ ký method được phân giải là instance method hay static method?
4. **Có nhiều overload không**: phiên bản chữ ký nào được compiler lựa chọn theo quy tắc chọn method?
5. **Instance method đó có bị override không**: nếu có, lớp runtime của receiver quyết định triển khai nào chạy?
6. **Thân method tác động vào object nào**: các câu `this.field`, `other.field` và lời gọi method trên tham số có thể chỉ tới những object khác nhau?
7. **Method trả về gì**: primitive, tham chiếu tới `this`, tham chiếu khác, object mới, hay `void`? Câu trả lời xác định receiver ở mắt xích tiếp theo nếu có.
8. **Có thể phát sinh lỗi runtime không**: receiver `null`, đối số không hợp lệ, method ném exception hoặc trạng thái object chưa hợp lệ?

Thực hành từng bước trên `mai.transferTo(nam, 25)`, `desk.turnOn().turnOff()` và `general.speak()` sẽ giúp phân biệt rõ **biến tham chiếu**, **đối tượng nhận lời gọi**, **method được chọn** và **đối tượng thực sự bị thay đổi**.

---

**Ghi nhớ:** Một **instance method** là hành vi được thực thi trong ngữ cảnh một **receiver object**. Biểu thức trước dấu chấm thường cung cấp tham chiếu tới receiver; `this` là receiver hiện tại trong thân instance method. Hai biến có thể cùng trỏ một object, lời gọi có thể chuyển sang object khác qua tham số hoặc kết quả method, và Java chọn triển khai method override dựa vào lớp runtime của receiver. Nhận diện đúng **receiver, kiểu tĩnh, trạng thái và kết quả trả về** là nền tảng để đọc, thiết kế và gỡ lỗi phương thức đối tượng trong Java.