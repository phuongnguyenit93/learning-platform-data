# Chuỗi hàm khởi tạo và số lần chạy khối khởi tạo đối tượng trong Java

Khi tạo một đối tượng Java bằng `new`, có thể có **nhiều constructor** tham gia vào một lần tạo object: constructor lớp con gọi `super(...)`, hoặc constructor của cùng lớp gọi `this(...)`. Đồng thời, lớp có thể khai báo **instance field initializer** và **instance initialization block** — những đoạn code được thực thi trong quá trình khởi tạo từng đối tượng.

Câu hỏi quan trọng là: **Nếu ba constructor nối nhau bằng `this(...)`, khối khởi tạo đối tượng có chạy ba lần không?**

**Không.** Với một lần tạo đối tượng thành công theo lời gọi constructor thông thường:

- Mỗi lớp trên chuỗi kế thừa thực hiện **các instance field initializers và instance initialization blocks của chính lớp đó một lượt**, theo thứ tự chúng xuất hiện trong khai báo lớp.
- Các constructor nối bằng `this(...)` có thể khiến **nhiều constructor bodies** của cùng một lớp được chạy, nhưng **không** lặp lại instance initializers của lớp đó.
- Quá trình khởi tạo các lớp **cha** hoàn tất trước khi chạy instance initializers và constructor body phù hợp của **lớp con**.
- **Static initialization** là cơ chế riêng: khởi tạo lớp khi JVM yêu cầu, thường một lần cho một đối tượng `Class` trong class loader tương ứng, **không** chạy lại với mỗi `new`.

Đây là sơ đồ rút gọn:

```text
new Child(...)
    |
    v
Child constructor (có thể this(...) đến constructor Child khác)
    |
    v
Điểm cuối của chuỗi this(...) gọi super(...)
    |
    v
Superclass initialization: constructor chain của cha
    |
    v
Instance field initializers + instance blocks của Child: MỘT LƯỢT
    |
    v
Body của Child constructor đích (đã gọi super)
    |
    v
Body của những Child constructors đã this(...), theo chiều quay lui
    |
    v
Object được trả về cho caller
```

Sơ đồ này dành cho trường hợp khởi tạo bình thường của class. Bên dưới chúng ta sẽ phân tích sâu: vì sao lời gọi nối constructor không tạo thêm object, cách đếm chính xác số lần khối khởi tạo chạy, thứ tự với superclass, và các ngoại lệ do lỗi runtime.

## 1. Ba cơ chế thường dễ nhầm

### 1.1. Constructor

Constructor có tên **giống tên class**, không có return type và được gọi trong quá trình tạo instance hoặc từ constructor khác bằng `this(...)` / `super(...)`.

```java
class User {
    User() {
        System.out.println("Constructor User()");
    }

    User(String name) {
        System.out.println("Constructor User(String)");
    }
}
```

Các constructor có **thân riêng**. Nếu một constructor gọi constructor khác, nhiều thân constructor có thể được thực thi trong cùng một lần tạo object.

### 1.2. Instance field initializer

Biểu thức ở khai báo instance field:

```java
class User {
    int level = 10;
    String name = computeName();

    String computeName() {
        return "guest";
    }
}
```

Hai initializer `10` và `computeName()` là một phần của **quá trình khởi tạo instance**, không phải các lệnh chạy một lần khi nạp class.

### 1.3. Instance initialization block

Khối `{ ... }` **không có `static`** được khai báo trực tiếp trong thân class:

```java
class User {
    int level;

    {
        level = 10;
        System.out.println("Instance block");
    }
}
```

Khối này được thực thi trong quá trình khởi tạo **từng object** theo quy tắc Java. Nó không phải constructor riêng, không có tên hay danh sách tham số, và **không** gọi nó bằng `new UserBlock()` hay `this(...)`.

### 1.4. Static initialization block

Khối:

```java
static {
    System.out.println("Static block");
}
```

là **static initializer**, thuộc **quá trình khởi tạo class**, không phải instance initializer. Cần tách nó ra khi đếm số lần chạy.

| Thành phần | Liên hệ với | Khi nào chạy trong trường hợp thông thường? |
| --- | --- | --- |
| Instance field initializer | Mỗi instance | Khi khởi tạo phần instance của class đó |
| Instance block `{ ... }` | Mỗi instance | Cùng giai đoạn với instance field initializers, theo thứ tự văn bản |
| Constructor body | Constructor được gọi trong chuỗi | Khi control quay về body constructor tương ứng |
| Static field initializer | Class | Trong class initialization khi cần |
| Static block `static { ... }` | Class | Trong class initialization khi cần |

## 2. Ví dụ ngắn nhất: instance block chạy trước constructor body

Lưu thành **`BasicInitDemo.java`**:

```java
class Box {
    int number = printNumber();

    {
        System.out.println("Instance block");
    }

    Box() {
        System.out.println("Constructor body");
    }

    private int printNumber() {
        System.out.println("Field initializer");
        return 7;
    }
}

public class BasicInitDemo {
    public static void main(String[] args) {
        Box box = new Box();
        System.out.println("number = " + box.number);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 BasicInitDemo.java
java BasicInitDemo
```

**Stdout chính xác:**

```text
Field initializer
Instance block
Constructor body
number = 7
```

Trình tự:

1. JVM tạo đối tượng `Box`, thiết lập các giá trị mặc định thích hợp cho trường dữ liệu.
2. Constructor superclass (`Object` trong trường hợp này) được xử lý theo chuỗi gọi constructor.
3. Instance field initializer `number = printNumber()` chạy; method in một dòng và trả `7`.
4. Instance block kế tiếp in `Instance block`.
5. Constructor body `Box()` in `Constructor body`.
6. Caller đọc giá trị `number` là `7`.

Trong class `Box` này, **field initializer và block chạy trước body của constructor `Box()`**. Chúng **không** chạy sau khi constructor đã kết thúc.

## 3. `this(...)` là constructor chaining cùng lớp

Một constructor có thể gọi constructor khác của **cùng class** thông qua **explicit constructor invocation** `this(arguments)`:

```java
class Product {
    Product() {
        this("unknown");
        System.out.println("Product()");
    }

    Product(String name) {
        System.out.println("Product(String): " + name);
    }
}
```

Lời gọi:

```java
new Product();
```

không tạo hai objects. Constructor `Product()` ủy quyền cho `Product(String)` **để khởi tạo cùng một object**. Sau khi constructor `Product(String)` hoàn tất, control quay về `Product()` và chạy phần body nằm **sau** `this("unknown")`.

**Điểm dễ nhầm:** `this(...)` không giống `new Product(...)`:
- `this(...)` nối constructor **trên object đang được xây dựng**.
- `new Product(...)` tạo **một object mới**.
- Chỉ gọi `this(...)` không làm JVM phân bổ thêm một instance.

### Trong Java 17, `this(...)` đứng đầu constructor

```java
Product() {
    this("default");
    System.out.println("done");
}
```

Không hợp lệ trong Java 17:

```java
// Product() {
//     System.out.println("before");
//     this("default"); // SAI: explicit constructor invocation phải đầu tiên.
// }
```

Lý do phiên bản rất quan trọng: **Java 17** yêu cầu một explicit constructor invocation `this(...)` hoặc `super(...)` là câu lệnh đầu tiên của constructor body. Đừng dùng cú pháp linh hoạt của các bản Java mới hơn khi bài đang kiểm tra Java 17.

## 4. Ví dụ cốt lõi: hai constructor, instance block vẫn một lần

Lưu thành **`ThisChainDemo.java`**:

```java
class Device {
    private final String name;

    {
        System.out.println("Device instance block");
    }

    Device() {
        this("default");
        System.out.println("Device()");
    }

    Device(String name) {
        this.name = name;
        System.out.println("Device(String): " + name);
    }

    String name() {
        return name;
    }
}

public class ThisChainDemo {
    public static void main(String[] args) {
        Device device = new Device();
        System.out.println("Result: " + device.name());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ThisChainDemo.java
java ThisChainDemo
```

**Stdout:**

```text
Device instance block
Device(String): default
Device()
Result: default
```

**Phân tích từng bước:**

1. `new Device()` chọn constructor không tham số.
2. `Device()` bắt đầu bằng `this("default")` và chuyển sang `Device(String)` cho **cùng object**.
3. `Device(String)` không viết `this(...)` / `super(...)` nên Java 17 có lời gọi `super()` ngầm định, dẫn tới `Object()`.
4. Quá trình khởi tạo phần instance của `Device` chạy: block in đúng **một lần**.
5. Body `Device(String)` chạy, gán `this.name` và in dòng tương ứng.
6. Control quay về `Device()` và in `Device()`.
7. Caller nhận đối tượng đã xây dựng, `name()` trả `default`.

Nếu tưởng instance block được chạy ở đầu **mọi constructor body**, bạn sẽ dự đoán sai thành hai dòng `Device instance block`. Trên thực tế, các instance initializers **thuộc chu kỳ khởi tạo phần instance của class**, không được sao chép và chạy lại khi control quay về một constructor delegating qua `this(...)`.

## 5. Ba constructor nối bằng `this(...)`: đếm số lần

Mở rộng chuỗi:

```java
class Chain {
    Chain() {
        this(1);
        System.out.println("Chain()");
    }

    Chain(int value) {
        this(value, "X");
        System.out.println("Chain(int)");
    }

    Chain(int value, String label) {
        System.out.println("Chain(int,String)");
    }
}
```

Khi tạo `new Chain()`, chuỗi lời gọi constructor là:

```text
Chain()
  -> this(1)
     -> Chain(int)
        -> this(1, "X")
           -> Chain(int, String)
              -> super() / Object()
              -> instance initializers của Chain: MỘT LƯỢT
              -> body Chain(int, String)
        <- body Chain(int)
  <- body Chain()
```

**Số lần chạy:**
- Constructor bodies: **3** (mỗi overload trong chuỗi một lần).
- Các instance blocks của `Chain`: **mỗi block một lần**, không phải ba lần.
- Các instance field initializers của `Chain`: **mỗi initializer một lần** trong pha khởi tạo `Chain`.
- Số đối tượng `Chain` được tạo bởi **một** `new Chain()`: **1**.

### Chương trình runnable ba constructor

Lưu **`ThreeConstructorChainDemo.java`**:

```java
class Chain {
    int marker = log("Field initializer");

    {
        log("Instance block");
    }

    Chain() {
        this(1);
        log("Chain()");
    }

    Chain(int value) {
        this(value, "X");
        log("Chain(int): " + value);
    }

    Chain(int value, String label) {
        log("Chain(int,String): " + value + "," + label);
    }

    private int log(String text) {
        System.out.println(text);
        return 1;
    }
}

public class ThreeConstructorChainDemo {
    public static void main(String[] args) {
        new Chain();
    }
}
```

```bash
javac -encoding UTF-8 ThreeConstructorChainDemo.java
java ThreeConstructorChainDemo
```

**Stdout:**

```text
Field initializer
Instance block
Chain(int,String): 1,X
Chain(int): 1
Chain()
```

Field initializer gọi `log` và nhận giá trị `1` để lưu vào `marker`. Instance block cũng gọi `log` nhưng bỏ giá trị trả về. Cả hai chạy **một lượt**. Chỉ các constructor bodies xuất hiện theo thứ tự từ **constructor đích sâu nhất** quay về constructor đã ủy quyền.

## 6. `super(...)` nối constructor từ lớp con sang lớp cha

Mỗi class thông thường (trừ `Object`) có một superclass trực tiếp. Trên đường tạo object, một constructor không ủy quyền qua `this(...)` phải gọi constructor superclass hợp lệ, **tường minh hoặc ngầm định**:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    Child() {
        super();
        System.out.println("Child()");
    }
}
```

`super()` ở `Child()` gọi constructor superclass `Parent()` để khởi tạo **phần Parent của cùng object Child**, không tạo một object `Parent` độc lập.

Kết quả khi chạy `new Child()`:

```text
Parent()
Child()
```

Nếu bỏ `super();` trong ví dụ này, Java 17 chèn `super();` ngầm định. Nhưng nếu superclass **không có no-arg constructor truy cập được**, subclass phải gọi một `super(arguments)` thích hợp hoặc có constructor chaining khác dẫn tới lời gọi superclass đúng.

### `super(...)` không phải `new Parent(...)`

```java
super(5);           // Khởi tạo phần superclass của object hiện tại.
new Parent(5);      // Tạo object Parent MỚI và độc lập.
```

Hai hoạt động có ý nghĩa khác. Việc tạo object Parent mới bằng `new` có thể kích hoạt thêm các instance initializers/constructors của **object mới đó**; lời gọi `super(...)` không.

## 7. Kế thừa: superclass initializer chạy trước subclass initializer

Với hai lớp:

```java
class Parent {
    int a = initializeA();

    {
        System.out.println("Parent block");
    }

    Parent() {
        System.out.println("Parent constructor");
    }

    private int initializeA() {
        System.out.println("Parent field");
        return 1;
    }
}

class Child extends Parent {
    int b = initializeB();

    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child constructor");
    }

    private int initializeB() {
        System.out.println("Child field");
        return 2;
    }
}
```

Trong lần `new Child()`, sau khi superclass `Object` được xử lý, thứ tự mà chúng ta quan sát được là:

```text
Parent field
Parent block
Parent constructor
Child field
Child block
Child constructor
```

**Điểm then chốt:** không phải tất cả instance field initializers của mọi lớp đều chạy cùng lúc trước tất cả constructor bodies. Java khởi tạo **phần superclass trước**, bao gồm field initializers, instance blocks và constructor body của superclass; sau đó mới tới phần khởi tạo của subclass.

## 8. Ví dụ hoàn chỉnh nhiều lớp: superclass → subclass

Lưu **`InheritanceInitializationDemo.java`**:

```java
class Parent {
    private int parentNumber = initParentNumber();

    {
        System.out.println("Parent block");
    }

    Parent() {
        System.out.println("Parent constructor: " + parentNumber);
    }

    private int initParentNumber() {
        System.out.println("Parent field");
        return 10;
    }
}

class Child extends Parent {
    private int childNumber = initChildNumber();

    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child constructor: " + childNumber);
    }

    private int initChildNumber() {
        System.out.println("Child field");
        return 20;
    }
}

public class InheritanceInitializationDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 InheritanceInitializationDemo.java
java InheritanceInitializationDemo
```

**Stdout chính xác:**

```text
Parent field
Parent block
Parent constructor: 10
Child field
Child block
Child constructor: 20
```

Thứ tự không phải “đọc từ trên xuống toàn bộ hai class”. Nó phụ thuộc vào **chuỗi gọi constructor cha/con**, trong đó mỗi phần superclass hoàn tất trước khi tiếp tục instance initialization của subclass.

### Có tạo một object Parent rồi một object Child không?

**Không.** `new Child()` cấp phát một object mà cấu trúc đối tượng bao gồm trạng thái được định nghĩa bởi các lớp trong hierarchy. Constructor `Parent()` xử lý phần superclass **trong cùng object Child**.

Vì vậy khi nói “mỗi class chạy initializer một lần”, ta đang nói tới **mỗi phần khởi tạo tương ứng của một object duy nhất**, không phải số objects tách biệt.

## 9. Kết hợp `super(...)` và `this(...)` trong cùng chuỗi

Giả sử `Child()` gọi `this("A")` và `Child(String)` gọi `super(5)`. Luồng đúng là:

```text
new Child()
  Child() bắt đầu
    -> this("A")
       Child(String) bắt đầu
         -> super(5)
            Parent(int) chạy (bao gồm initializer Parent)
         <- Parent(int) kết thúc
       instance initializers của Child: một lượt
       body Child(String)
    <- Child(String) kết thúc
  body Child()
Object xây dựng xong
```

Quan trọng là **không phải hai Child constructors đều chạy các instance initializers của Child**. Chúng nối nhau trên **một lần khởi tạo Child**.

### Chương trình minh họa Java 17

Lưu **`CombinedChainDemo.java`**:

```java
class Parent {
    {
        System.out.println("P: block");
    }

    Parent(int number) {
        System.out.println("P: constructor " + number);
    }
}

class Child extends Parent {
    private String name = initName();

    {
        System.out.println("C: block");
    }

    Child() {
        this("An");
        System.out.println("C: no-arg body");
    }

    Child(String name) {
        super(5);
        this.name = name;
        System.out.println("C: String body " + this.name);
    }

    private String initName() {
        System.out.println("C: field");
        return "default";
    }
}

public class CombinedChainDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 CombinedChainDemo.java
java CombinedChainDemo
```

**Stdout:**

```text
P: block
P: constructor 5
C: field
C: block
C: String body An
C: no-arg body
```

`Parent` không có zero-argument constructor; `Child(String)` gọi `super(5)` tường minh. `Child()` gọi `this("An")`, không được thêm `super()` nữa trong chính constructor `Child()`.

## 10. Mỗi lớp trong hierarchy khởi tạo phần instance của mình một lượt

Giả sử:

```text
Object
  |
  v
Grandparent
  |
  v
Parent
  |
  v
Child
```

Với một lời gọi `new Child()` và constructor chaining hợp lệ, một chuỗi hoàn tất bình thường sẽ đi qua:

1. Giai đoạn constructor của `Object`.
2. Instance field initializers/instance blocks của `Grandparent`, rồi constructor body được chọn và các constructor bodies khác trong chuỗi `this(...)` của `Grandparent`.
3. Tương tự cho `Parent`.
4. Tương tự cho `Child`.

Đếm theo class:

| Class trong chain | Lượt chạy mỗi instance initializer khi tạo một `Child` |
| --- | --- |
| `Grandparent` | 1 |
| `Parent` | 1 |
| `Child` | 1 |
| `Object` | Theo cơ chế khởi tạo superclass; `Object` không có instance blocks được người dùng viết trong ví dụ |

Nếu mỗi lớp có **hai** instance blocks, thì **mỗi block** chạy một lượt, nghĩa là hai lượt thực thi block khác nhau **trong lớp đó**, không phải “toàn bộ hai block gộp thành một dòng”. Nếu có **ba class** mỗi class một block, tổng cộng **ba block executions** cho một `new Child()`.

### Cách tính tổng quát

Đối với việc tạo thành công một object thuộc class `T` qua constructor bình thường, nếu mỗi class `K` trên tuyến superclass từ `Object` tới `T` khai báo `b(K)` instance initialization blocks, thì số lần thực thi các block tương ứng trong quá trình đó là:

\[
\sum_{K \in \mathrm{hierarchy}(T)} b(K).
\]

Đây là số **block executions** trong một lần khởi tạo hoàn tất bình thường, **không** phải số lần Java gọi constructors, và giả định các block được đi qua mà không bị exception cắt ngang.

## 11. Ví dụ ba tầng kế thừa, nhiều constructor

Lưu **`ThreeLevelsDemo.java`**:

```java
class Grandparent {
    {
        System.out.println("G: block");
    }

    Grandparent() {
        this(1);
        System.out.println("G: no-arg");
    }

    Grandparent(int number) {
        System.out.println("G: int " + number);
    }
}

class Parent extends Grandparent {
    {
        System.out.println("P: block");
    }

    Parent() {
        super();
        System.out.println("P: no-arg");
    }
}

class Child extends Parent {
    {
        System.out.println("C: block");
    }

    Child() {
        this("X");
        System.out.println("C: no-arg");
    }

    Child(String name) {
        super();
        System.out.println("C: String " + name);
    }
}

public class ThreeLevelsDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ThreeLevelsDemo.java
java ThreeLevelsDemo
```

**Stdout:**

```text
G: block
G: int 1
G: no-arg
P: block
P: no-arg
C: block
C: String X
C: no-arg
```

Phân tích định lượng:

- **Một** object `Child` được tạo.
- `Grandparent` có **hai constructor bodies** chạy vì `Grandparent()` gọi `this(1)`; block `G` chỉ in **một lần**.
- `Parent` có một constructor body và block `P` chạy một lần.
- `Child` có **hai constructor bodies** vì `Child()` gọi `this("X")`; block `C` chỉ in **một lần**.
- Tổng số dòng bắt đầu bằng `G: block`, `P: block`, `C: block` là **3**. Tổng số constructor body logs là **5**.

Ví dụ này chứng minh bằng output rằng **số constructor bodies trong chain không quyết định số lần instance blocks chạy**.

## 12. Thứ tự giữa field initializers và instance blocks của cùng lớp

Trong cùng một class, **instance field initializer** và **instance initialization block** được thực thi **theo thứ tự chúng xuất hiện trong source code**, miễn thuộc pha khởi tạo instance của class đó.

Ví dụ:

```java
class Sequence {
    private int a = print("field a", 1);

    {
        print("block 1", 0);
    }

    private int b = print("field b", 2);

    {
        print("block 2", 0);
    }

    Sequence() {
        print("constructor", 0);
    }

    private int print(String label, int result) {
        System.out.println(label);
        return result;
    }
}
```

Với `new Sequence()`:

```text
field a
block 1
field b
block 2
constructor
```

**Không có quy tắc “mọi field initializer chạy hết rồi mới mọi instance block”.** Chúng được xử lý xen kẽ theo thứ tự văn bản trong cùng class.

### Không nhầm với thứ tự trong hierarchy

Thứ tự textual được áp dụng **trong từng class**. Nếu `Parent` có instance initializer nằm cuối file `Parent.java` còn `Child` có instance initializer nằm đầu file `Child.java`, phần `Parent` vẫn được khởi tạo trước phần `Child` theo constructor chain.

## 13. Ví dụ thứ tự xen kẽ có stdout

Lưu **`InterleavedInitializersDemo.java`**:

```java
class Sequence {
    int first = trace("field first", 1);

    {
        trace("block A", 0);
    }

    int second = trace("field second", 2);

    {
        trace("block B", 0);
    }

    Sequence() {
        System.out.println("constructor: " + first + "," + second);
    }

    private int trace(String text, int result) {
        System.out.println(text);
        return result;
    }
}

public class InterleavedInitializersDemo {
    public static void main(String[] args) {
        new Sequence();
    }
}
```

```bash
javac -encoding UTF-8 InterleavedInitializersDemo.java
java InterleavedInitializersDemo
```

**Stdout:**

```text
field first
block A
field second
block B
constructor: 1,2
```

Lợi ích của cách biểu diễn này là mô tả **rõ ràng nơi khai báo những hiệu ứng khởi tạo**. Tuy nhiên, nếu initializer quá phức tạp, khó theo dõi exception hoặc phụ thuộc nhiều state, hãy cân nhắc đưa logic vào constructor hoặc helper method để dễ kiểm thử.

## 14. Giá trị mặc định của field xuất hiện trước initializer

Khi object được cấp phát, instance fields có **giá trị mặc định theo kiểu** trước khi các initializer/constructor bodies gán giá trị cụ thể:

| Loại field | Giá trị mặc định |
| --- | --- |
| `boolean` | `false` |
| `byte`, `short`, `int`, `long` | `0` tương ứng |
| `float`, `double` | `0.0` tương ứng |
| `char` | ký tự `\u0000` |
| Các kiểu tham chiếu | `null` |

Về mặt quy tắc, các field của object được đặt trạng thái mặc định **trước** giai đoạn thực thi các constructor/instance initializers.

Ví dụ:

```java
class Demo {
    int value;

    Demo() {
        System.out.println(value); // 0 nếu chưa initializer/gán khác.
        value = 10;
    }
}
```

**Cần tránh nhầm với biến cục bộ:** local variable không được Java tự cho giá trị mặc định để đọc trước khi khởi tạo. Một local chưa definitely assigned không thể được đọc hợp lệ.

### Constructor cha có thể quan sát trạng thái mặc định của phần subclass

Điều này đặc biệt nguy hiểm khi constructor của superclass gọi một method bị subclass override; phần initializer của subclass **chưa chạy xong** tại thời điểm superclass constructor thực thi.

## 15. Bẫy phổ biến: gọi method có thể override trong constructor cha

Trong một constructor chain gồm `super(...)` và `this(...)`, có thể gặp một **virtual call** từ superclass constructor **trước** khi subclass instance fields/blocks chạy:

```java
class Parent {
    Parent() { report(); }
    void report() { }
}
class Child extends Parent {
    String message = "READY";
    @Override void report() { System.out.println(message); }
}
```

Đây là **snippet**, không phải chương trình độc lập. Khi tạo `new Child()`, `report()` trong Parent có thể in `null` do dispatch đến override của Child trong khi `message` vẫn ở default value. Điều này **không làm instance initializer của Child chạy thêm lần nào**: sau khi Parent constructor hoàn thành, initializer Child chạy **một lượt** cho object ấy, rồi mới đến các bodies constructors của Child theo chuỗi.

Vì thế khi làm bài **đếm số lượt khởi tạo**, hãy tách **số lần callback bị gọi trong constructor** khỏi **số lần field/instance block của mỗi lớp chạy**. Tránh override callbacks trong constructor; ví dụ runnable và thiết kế thay thế được phân tích chuyên sâu ở bài về gọi phương thức ghi đè trước khi object khởi tạo xong.

## 16. `this(...)` và `super(...)` không được gọi đồng thời trong một constructor Java 17

Đây là dạng **không hợp lệ**:

```java
class Base {
    Base() {
    }
}

class Derived extends Base {
    Derived() {
        // this(1);
        // super();
        // SAI nếu dùng cả hai explicit constructor invocations.
    }

    Derived(int value) {
        super();
    }
}
```

Trong Java 17, một constructor có thể có **tối đa một explicit constructor invocation ở đầu**:

- `this(arguments);`: chuyển sang constructor khác **cùng class**.
- `super(arguments);`: chuyển sang constructor superclass phù hợp.
- Hoặc không viết cái nào, compiler chèn `super();` khi cần theo quy tắc.

Nếu constructor chọn `this(...)`, constructor được ủy quyền sẽ tiếp tục chuỗi đến một constructor cùng lớp không dùng `this(...)` nữa, rồi phần superclass được khởi tạo.

### Constructor `this(...)` không tạo nhánh thứ hai để chạy initializer

Một constructor body không tự động chạy `super()` **sau khi** `this(...)` hoàn thành. Nếu vậy sẽ khởi tạo superclass hai lần, trái với mô hình đúng. Các lời gọi constructor theo chain chỉ đi qua **một tuyến** khởi tạo cho cùng object.

## 17. Chuỗi `this(...)` không thể tạo vòng lặp

Ví dụ **không hợp lệ**:

```java
class InvalidChain {
    InvalidChain() {
        this(1);
    }

    InvalidChain(int number) {
        this();
    }
}
```

Compiler phát hiện chuỗi constructor invocation đệ quy:

```text
InvalidChain() -> InvalidChain(int) -> InvalidChain() -> ...
```

Java không cho một vòng `this(...)` khiến chuỗi constructor không bao giờ đến constructor có đường gọi superclass hợp lệ.

### Cách thiết kế đúng

Cho một overload đóng vai trò nơi khởi tạo chính:

```java
class ValidChain {
    private final int number;

    ValidChain() {
        this(1);
    }

    ValidChain(int number) {
        this.number = number;
    }
}
```

Constructor `ValidChain(int)` không gọi `this(...)`; Java 17 chèn `super()` nếu superclass mặc định hợp lệ. Sau khi superclass xong, instance initializers của `ValidChain` được thực thi một lượt, rồi body `ValidChain(int)` gán field `number`.

Đây là mẫu **constructor delegation**: overload đơn giản chuyển tới constructor có đủ tham số.

## 18. Constructor overload không đồng nghĩa số lượt instance initialization

Khi một class có bốn overload:

```java
class Request {
    Request() { this("GET"); }
    Request(String method) { this(method, "/"); }
    Request(String method, String path) { this(method, path, 0); }
    Request(String method, String path, int version) { }
}
```

Nếu tất cả hợp lệ, `new Request()` làm **bốn constructor bodies** được thực thi theo chiều quay lui, nhưng các instance initializers của `Request` vẫn chỉ chạy một lượt.

Nếu gọi `new Request("POST", "/orders", 1)` trực tiếp, chỉ body của overload có ba tham số chạy, nhưng instance initializers vẫn chạy **một lượt**.

**Số constructor overload được khai báo** trong class hoàn toàn **không quyết định** số lần instance blocks chạy.

### Bảng dự đoán

| Lời gọi | Body của constructors được chạy (trong `Request`) | Lượt chạy một instance block trong `Request` |
| --- | --- | --- |
| `new Request()` | 4 | 1 |
| `new Request("GET")` | 3 | 1 |
| `new Request("GET", "/")` | 2 | 1 |
| `new Request("GET", "/", 2)` | 1 | 1 |

Bảng giả định các constructor trong đoạn mã đều hoàn tất bình thường, superclass constructor phù hợp và không có code tạo thêm `Request` objects khác trong initializer.

## 19. Chạy thử các overload và đếm chính xác

Lưu **`ConstructorCountDemo.java`**:

```java
class Request {
    static int blockExecutions;

    {
        blockExecutions++;
        System.out.println("block #" + blockExecutions);
    }

    Request() {
        this("GET");
        System.out.println("body Request()");
    }

    Request(String method) {
        this(method, "/");
        System.out.println("body Request(String)");
    }

    Request(String method, String path) {
        System.out.println("body Request(String,String)");
    }
}

public class ConstructorCountDemo {
    public static void main(String[] args) {
        new Request();
        new Request("POST", "/save");
        System.out.println("total blocks = " + Request.blockExecutions);
    }
}
```

```bash
javac -encoding UTF-8 ConstructorCountDemo.java
java ConstructorCountDemo
```

**Stdout:**

```text
block #1
body Request(String,String)
body Request(String)
body Request()
block #2
body Request(String,String)
total blocks = 2
```

Vì sao tổng là `2`?

- Lần `new Request()` có ba constructor bodies chạy, nhưng instance block chỉ chạy **một lượt**.
- Lần `new Request("POST", "/save")` có một constructor body, instance block cũng chạy **một lượt**.
- Tổng hai lần tạo instance là hai lượt chạy block. Static counter chỉ dùng để **quan sát số lượt** và không phải dữ liệu độc lập của từng Request.

**Cẩn thận khi đếm:** nếu instance block gọi `new Request(...)` lần nữa, đây là việc tạo **object khác**, do đó sẽ có thêm lượt initializer. Bảng trên không áp dụng khi code có side effect tạo thêm instances.

## 20. Static initializer khác instance initializer về số lần

Lưu **`StaticVsInstanceDemo.java`**:

```java
class Widget {
    static {
        System.out.println("static block");
    }

    {
        System.out.println("instance block");
    }

    Widget() {
        System.out.println("constructor");
    }
}

public class StaticVsInstanceDemo {
    public static void main(String[] args) {
        System.out.println("before first new");
        new Widget();

        System.out.println("before second new");
        new Widget();
    }
}
```

```bash
javac -encoding UTF-8 StaticVsInstanceDemo.java
java StaticVsInstanceDemo
```

**Stdout:**

```text
before first new
static block
instance block
constructor
before second new
instance block
constructor
```

- `Widget` được khởi tạo như một class trước lần sử dụng chủ động tạo instance đầu tiên trong ví dụ.
- Static block in **một lần** trong quá trình khởi tạo class `Widget`.
- Mỗi lần `new Widget()` tạo một object, instance block in **một lần** rồi constructor body in một lần.
- Lần `new` thứ hai không làm static block chạy lại khi vẫn dùng cùng class initialization state.

**Nói chính xác:** static initialization diễn ra theo các quy tắc khởi tạo lớp/interface của JVM, không phải “chạy lại mỗi lần gọi static method”. Các class loaders khác nhau có thể định nghĩa các runtime classes riêng; cùng tên class không nhất thiết có một global initialization duy nhất cho toàn bộ mọi class loaders.

## 21. Static initialization và instance initialization theo hierarchy

Khi lần đầu khởi tạo một subclass `Child`, JVM bảo đảm việc class initialization cần thiết của superclass xảy ra theo quy tắc trước khi subclass hoàn tất class initialization. Sau đó các lần tạo object chạy **instance initialization** theo từng object.

Ví dụ:

```java
class Parent {
    static { System.out.println("P static"); }
    { System.out.println("P instance"); }
    Parent() { System.out.println("P ctor"); }
}

class Child extends Parent {
    static { System.out.println("C static"); }
    { System.out.println("C instance"); }
    Child() { System.out.println("C ctor"); }
}
```

Nếu `Child` chưa từng được khởi tạo trong quá trình chạy, lần `new Child()` đầu tiên cho thứ tự:

```text
P static
C static
P instance
P ctor
C instance
C ctor
```

Lần `new Child()` tiếp theo chỉ cho các dòng instance/ctor:

```text
P instance
P ctor
C instance
C ctor
```

### Chương trình chạy được

Lưu **`HierarchyStaticInstanceDemo.java`**:

```java
class Parent {
    static {
        System.out.println("P static");
    }

    {
        System.out.println("P instance");
    }

    Parent() {
        System.out.println("P ctor");
    }
}

class Child extends Parent {
    static {
        System.out.println("C static");
    }

    {
        System.out.println("C instance");
    }

    Child() {
        System.out.println("C ctor");
    }
}

public class HierarchyStaticInstanceDemo {
    public static void main(String[] args) {
        System.out.println("first");
        new Child();

        System.out.println("second");
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 HierarchyStaticInstanceDemo.java
java HierarchyStaticInstanceDemo
```

**Stdout:**

```text
first
P static
C static
P instance
P ctor
C instance
C ctor
second
P instance
P ctor
C instance
C ctor
```

Ví dụ cố ý in tên loại initializer để người học không cộng nhầm lượt chạy static block vào số lượt instance blocks.

## 22. Một class có nhiều instance blocks: đếm theo **từng block**

Ví dụ:

```java
class MultiBlock {
    {
        System.out.println("A");
    }

    {
        System.out.println("B");
    }

    MultiBlock() {
        this(1);
        System.out.println("zero");
    }

    MultiBlock(int number) {
        System.out.println("int");
    }
}
```

Với `new MultiBlock()`:

```text
A
B
int
zero
```

Có:
- **2 lượt block executions**, vì class khai báo **2 blocks**, mỗi block chạy một lần.
- **2 constructor body executions**, vì `MultiBlock()` gọi `this(1)`.
- **1 object instance**, vì chỉ có một `new MultiBlock()`.

Nếu có `new MultiBlock()` hai lần, ta có tổng cộng **4 block executions** (A hai lần, B hai lần), nhưng không phải mỗi A/B chạy hai lần trong *một* lần tạo object.

### Công thức có điều kiện

Với class duy nhất có `b` blocks, tạo `n` instances bằng những constructor hoàn tất bình thường, và không có code phụ tạo instances khác, tổng số instance block executions của chính class ấy là:

\[
n \times b.
\]

Việc có một, hai hay nhiều constructor trong một `this(...)` chain không tạo thêm thừa số nào.

## 23. Phân biệt “mỗi object một lượt” với “chỉ một lần trong đời chương trình”

**Instance initializer** không phải singleton initializer.

```java
new Sample();
new Sample();
new Sample();
```

Nếu mỗi lời gọi tạo một `Sample` độc lập thành công, mọi instance block của `Sample` chạy **ba lượt** tổng cộng.

Nhưng:

```java
Sample sample = new Sample();
Sample alias = sample;
```

hai biến `sample` và `alias` có thể trỏ **cùng một object**. Phép gán `alias = sample` **không** tạo instance nên **không** chạy instance block thêm lần nữa.

Tương tự, truyền object làm đối số:

```java
process(sample);
```

chỉ sao chép giá trị tham chiếu, không tạo mới object để instance initializer chạy lại.

**Hãy đếm object thật sự được khởi tạo, không đếm số biến tham chiếu hay số lần truy cập object.**

## 24. `new` trong constructor/initializer có thể tạo nhiều objects

Quy tắc “một lần `new Outer()` → mỗi initializer của Outer một lượt” không đồng nghĩa **chương trình chỉ tạo một object tổng cộng**.

Ví dụ:

```java
class Engine {
    Engine() {
        System.out.println("Engine ctor");
    }
}

class Car {
    Engine engine = new Engine();

    Car() {
        System.out.println("Car ctor");
    }
}
```

`new Car()` thực hiện:
1. Tạo một `Car`.
2. Trong field initializer của `Car`, thực hiện `new Engine()`, tạo **một object Engine khác**.
3. Khởi tạo và chạy constructor của `Engine` cho object Engine.
4. Chạy constructor body của `Car`.

Output:

```text
Engine ctor
Car ctor
```

Sự xuất hiện hai constructor ở đây là do **hai object được tạo thật**, không phải `this(...)` tạo thêm object.

### Phân biệt đối tượng của superclass

`new Child()` **không** dùng `new Parent()` để tạo một object Parent thứ hai. Nó gọi constructor Parent trên **cùng Child object**. Đây là khác biệt then chốt khi thống kê allocations và lượt khởi tạo.

## 25. Initialization blocks không thay thế constructor parameters

Một instance initialization block không có danh sách tham số riêng:

```java
class Order {
    int total;

    {
        total = 0;
    }

    Order(int initial) {
        total = initial;
    }
}
```

Block có thể khởi tạo giá trị chung như `0`, nhưng thông tin `initial` là tham số constructor. Trong một instance initializer thông thường của class, bạn không thể giả định có quyền dùng một tham số chỉ khai báo bởi một constructor overload cụ thể.

Nếu mỗi overload cần một giá trị khác nhau, nên xử lý qua constructor chính và `this(...)` delegation.

### Mẫu có constructor chính

```java
class Order {
    private final String id;
    private final int total;

    {
        System.out.println("Order block");
    }

    Order() {
        this("UNKNOWN", 0);
    }

    Order(String id, int total) {
        this.id = id;
        this.total = total;
    }
}
```

Block in một lần bất kể gọi overload nào; hai final fields được khởi tạo ở constructor chính. Đây là thiết kế rõ ràng khi các overload chỉ khác **giá trị mặc định**.

**Tránh viết logic phụ thuộc tham số cụ thể vào instance block**: code ở block không được gọi như một method có parameter list.

## 26. Blank final fields trong constructor chaining

Một `final instance field` không có initializer ở khai báo (*blank final*) phải được khởi tạo theo quy tắc **definite assignment**.

Ví dụ:

```java
class Session {
    private final String id;

    Session() {
        this("default");
    }

    Session(String id) {
        this.id = id;
    }
}
```

`new Session()` gọi `Session()`, ủy quyền bằng `this("default")`. Field `id` được gán ở constructor chính **một lần** cho object đó.

Không hợp lệ:

```java
class InvalidSession {
    private final String id;

    InvalidSession() {
        this("default");
        // id = "changed"; // SAI: field đã được gán từ chain.
    }

    InvalidSession(String id) {
        this.id = id;
    }
}
```

**Ý nghĩa:** constructor delegation thường dùng để tập trung việc khởi tạo final fields tại **một constructor có đủ tham số**, giảm nguy cơ nhánh thiếu gán hoặc gán nhiều lần.

### Lưu ý instance initializer với blank final

Một blank final field cũng có thể được gán bởi instance initializer hợp lệ:

```java
class Ticket {
    private final String type;

    {
        type = "STANDARD";
    }

    Ticket() {
        // type = "OTHER"; // SAI: không được gán lần hai.
    }
}
```

Block chạy **một lần cho mỗi object** và gán `type` đúng một lần. Dù `Ticket()` gọi qua `this(...)` đến overload khác, block không phải được chạy lại để gán lần hai.

## 27. Constructor có `return;` thì initializer có chạy không?

Constructor của Java có thể dùng **`return;` không có biểu thức** để kết thúc constructor body sớm trong tình huống hợp lệ, nhưng nó **không bỏ qua** phần initialization của superclass và instance initializers vốn đã chạy **trước body**.

Ví dụ:

```java
class Example {
    {
        System.out.println("block");
    }

    Example(boolean stop) {
        if (stop) {
            return;
        }
        System.out.println("body after check");
    }
}
```

`new Example(true)` vẫn in:

```text
block
```

Constructor body kiểm tra `stop` rồi kết thúc sớm, **không** in `body after check`.

### Chương trình Java 17

Lưu **`ConstructorReturnDemo.java`**:

```java
class Example {
    {
        System.out.println("block");
    }

    Example(boolean stop) {
        if (stop) {
            return;
        }
        System.out.println("continued");
    }
}

public class ConstructorReturnDemo {
    public static void main(String[] args) {
        new Example(true);
        new Example(false);
    }
}
```

```bash
javac -encoding UTF-8 ConstructorReturnDemo.java
java ConstructorReturnDemo
```

Stdout:

```text
block
block
continued
```

**Không được** viết `return someObject;` trong constructor để “trả object khác”; constructor không có return type và không trả expression.

## 28. Exception trong initializer: không có cam kết toàn bộ chain hoàn tất

Những bảng “mỗi initializer chạy một lần” nêu trên mô tả **chuỗi khởi tạo được thực thi bình thường**. Nếu initializer hoặc constructor ném exception, phần code phía sau có thể **không được chạy**.

Ví dụ:

```java
class Fragile {
    {
        System.out.println("before error");
        if (true) {
            throw new IllegalStateException("failed");
        }
    }

    Fragile() {
        System.out.println("constructor body");
    }
}
```

Đây là đoạn minh họa chủ ý về lỗi lúc chạy. Java sẽ bắt đầu instance block, in dòng trước exception, rồi ném `IllegalStateException`; constructor body không in vì chưa được đi tới. Không có object hoàn chỉnh được trả về từ lời gọi `new Fragile()` đó.

### Ví dụ runnable và bắt lỗi

Lưu **`InitializationExceptionDemo.java`**:

```java
class Fragile {
    {
        System.out.println("block begins");
        if (System.nanoTime() >= 0) {
            throw new IllegalStateException("failed");
        }
    }

    Fragile() {
        System.out.println("constructor body");
    }
}

public class InitializationExceptionDemo {
    public static void main(String[] args) {
        try {
            new Fragile();
        } catch (IllegalStateException error) {
            System.out.println("caught: " + error.getMessage());
        }
    }
}
```

Trong ví dụ trên, điều kiện `System.nanoTime() >= 0` phụ thuộc clock monotonic tương đối của JVM và **không nên dùng để tạo lỗi chắc chắn**. Để có ví dụ chính xác, thay bằng một phương thức ném exception vô điều kiện:

```java
class Fragile {
    {
        System.out.println("block begins");
        fail();
    }

    static void fail() {
        throw new IllegalStateException("failed");
    }

    Fragile() {
        System.out.println("constructor body");
    }
}

public class InitializationExceptionDemo {
    public static void main(String[] args) {
        try {
            new Fragile();
        } catch (IllegalStateException error) {
            System.out.println("caught: " + error.getMessage());
        }
    }
}
```

Dùng **phiên bản thứ hai** khi lưu tệp `InitializationExceptionDemo.java`; hai đoạn là **các phiên bản thay thế**, không đặt đồng thời trong cùng package.

```bash
javac -encoding UTF-8 InitializationExceptionDemo.java
java InitializationExceptionDemo
```

**Stdout phiên bản thứ hai:**

```text
block begins
caught: failed
```

Điều kiện để constructor body chạy là các giai đoạn trước đó **hoàn tất bình thường**. Nếu superclass constructor ném exception, subclass initializers cũng không được thực hiện vì control chưa quay về phần khởi tạo subclass.

### Exception trong static initialization khác

Lỗi từ `static { ... }` là lỗi **khởi tạo class**, có thể được bọc hoặc biểu hiện qua các loại lỗi khởi tạo lớp như `ExceptionInInitializerError`. Không đánh đồng nó với một `IllegalStateException` ném từ instance block bình thường.

## 29. Nếu constructor cha ném lỗi thì block của lớp con có chạy không?

**Không, nếu superclass constructor không hoàn tất bình thường trước khi subclass initialization bắt đầu.**

Ví dụ:

```java
class Parent {
    Parent() {
        System.out.println("Parent ctor");
        throw new IllegalArgumentException("stop");
    }
}

class Child extends Parent {
    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child ctor");
    }
}
```

Với `new Child()`:
- `Parent ctor` được in.
- Superclass constructor ném exception.
- `Child block` **không** được in.
- `Child ctor` **không** được in.

Đây là hệ quả trực tiếp của thứ tự cha trước con.

**Không nên hiểu ngoại lệ này là block bị “bỏ qua một cách ngẫu nhiên”.** Quá trình khởi tạo chưa đến giai đoạn instance initializer của `Child`.

### Cẩn thận với side effects trước khi lỗi

Nếu superclass constructor đã đăng ký `this` vào nơi khác trước khi ném exception, một object **chưa hoàn chỉnh** có thể bị quan sát. Tránh làm lộ `this` quá sớm và tránh side effects khó hoàn tác trong constructors.

## 30. `this` escape: không để object chưa hoàn chỉnh bị sử dụng

Một constructor hoặc instance block có thể gọi:

```java
registry.add(this);
```

Nếu `this` được chuyển ra ngoài quá sớm, mã khác có thể sử dụng object khi subclass fields hoặc các initializers khác **chưa hoàn tất**.

Nguy cơ bao gồm:
- Observer/callback thấy giá trị mặc định `0`/`null` thay vì trạng thái cuối.
- Thread khác truy cập field chưa được công bố an toàn.
- Override method chạy trên subclass object trước khi subclass initializer đã chạy.
- Invariant của object chưa được thiết lập nhưng đã bị coi như hợp lệ.

**Cách giảm rủi ro:** tạo object hoàn chỉnh trước rồi đăng ký callback/khởi động thread; cân nhắc static factory hoặc builder để tách construction khỏi registration.

Không nên để instance block chứa logic “gọi ra thế giới bên ngoài” phức tạp chỉ vì muốn code chạy trước constructor body.

## 31. Constructor chaining và truy cập `this`/`super` ở Java 17

Để nắm rõ Java 17:

```java
class Base {
    Base(int id) {
    }
}

class Derived extends Base {
    Derived() {
        this(1);  // Hợp lệ: explicit invocation đầu constructor.
    }

    Derived(int id) {
        super(id); // Hợp lệ: explicit invocation đầu constructor.
    }
}
```

Nhưng:

```java
class InvalidDerived extends Base {
    InvalidDerived() {
        // super(this.hashCode()); // SAI: không được dùng
        // receiver this theo cách đó trước superclass constructor.
    }
}
```

Đây là các đoạn minh họa, và `InvalidDerived` **như viết ở trên không biên dịch** vì không gọi một constructor superclass thích hợp (class `Base` không có no-arg constructor), kể cả khi dòng có `super(...)` được comment.

Thông điệp quan trọng: **trước khi constructor chain hoàn thành superclass invocation, chưa thể tùy ý sử dụng instance state như trong một instance method thông thường**. Java 17 giới hạn việc truy cập `this`/`super` trong explicit constructor invocation; hãy giữ lời gọi chaining rõ ràng, truyền các đối số có thể đánh giá hợp lệ.

### Constructor overload và argument evaluation

`this(1 + 2)` chọn overload theo kiểu của biểu thức đối số. Các biểu thức đối số được đánh giá theo quy tắc Java khi thực hiện lời gọi tương ứng, nhưng bản thân `this(...)` **không** có nghĩa “đã có một object mới”.

Tránh đưa side effects khó dự đoán vào biểu thức đối số constructor nếu việc hiểu thứ tự khởi tạo đã phức tạp.

## 32. Bài toán đếm: hai objects, ba lớp, hai blocks mỗi lớp

Giả sử:
- `A` có một instance block.
- `B extends A` có hai instance blocks.
- `C extends B` có một instance block.
- Mỗi class có constructor chaining hợp lệ (số overload tùy ý).
- Thực hiện `new C()` **hai lần**, đều thành công.
- Không initializer nào tạo thêm `A/B/C` objects.

Mỗi `new C()` kích hoạt:
- Block của `A`: 1 lần.
- Hai blocks của `B`: tổng 2 lượt.
- Block của `C`: 1 lần.

Vậy mỗi object có **4 block executions**, tạo **2 objects** là **8 block executions**.

Nếu constructor `C()` còn gọi `this(int)` rồi `this(int,String)`, con số **8** vẫn không đổi. Constructor chaining chỉ tăng số **constructor bodies được thực thi**, không tạo thêm lượt block per class.

### Cách giải có hệ thống

1. Đếm **object creation expressions thực sự** được thực hiện và thành công.
2. Với mỗi object, vẽ superclass chain.
3. Đếm **instance blocks + instance field initializers** trong từng class; phân biệt loại nếu đề yêu cầu.
4. Đánh dấu **mỗi class một lượt khởi tạo instance** theo chuỗi.
5. Đếm riêng constructor bodies nối qua `this(...)`.
6. Đếm riêng static blocks nếu đề có class initialization.
7. Kiểm tra exception hoặc code tạo thêm object trong initializer trước khi kết luận.

## 33. Bài thực hành tổng hợp Java 17

Đây là bài trace kết hợp **static initialization, field initializers, instance blocks, constructor `this(...)`, `super(...)` và nhiều object instances**.

Lưu **`FullInitializationTraceDemo.java`**:

```java
class Base {
    static {
        System.out.println("Base.static");
    }

    int baseValue = trace("Base.field", 1);

    {
        System.out.println("Base.block");
    }

    Base() {
        this(10);
        System.out.println("Base()");
    }

    Base(int value) {
        System.out.println("Base(int): " + value);
    }

    private int trace(String event, int result) {
        System.out.println(event);
        return result;
    }
}

class Derived extends Base {
    static {
        System.out.println("Derived.static");
    }

    int derivedValue = traceDerived("Derived.field", 2);

    {
        System.out.println("Derived.block");
    }

    Derived() {
        this("X");
        System.out.println("Derived()");
    }

    Derived(String label) {
        super();
        System.out.println("Derived(String): " + label);
    }

    private int traceDerived(String event, int result) {
        System.out.println(event);
        return result;
    }
}

public class FullInitializationTraceDemo {
    public static void main(String[] args) {
        System.out.println("START");
        new Derived();
        System.out.println("NEXT");
        new Derived("Y");
        System.out.println("END");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FullInitializationTraceDemo.java
java FullInitializationTraceDemo
```

**Stdout chính xác:**

```text
START
Base.static
Derived.static
Base.field
Base.block
Base(int): 10
Base()
Derived.field
Derived.block
Derived(String): X
Derived()
NEXT
Base.field
Base.block
Base(int): 10
Base()
Derived.field
Derived.block
Derived(String): Y
END
```

### Từng giai đoạn của object đầu tiên

1. `main` in `START`.
2. Lần đầu `new Derived()` khiến JVM khởi tạo class `Base` và `Derived` khi cần: static blocks in `Base.static`, `Derived.static`.
3. `Derived()` gọi `this("X")` → constructor `Derived(String)`.
4. `Derived(String)` gọi `super()` → `Base()`.
5. `Base()` gọi `this(10)` → `Base(int)`.
6. `Base` chạy instance field initializer và block: `Base.field`, `Base.block`.
7. Body `Base(int)` in `Base(int): 10`.
8. Control quay về body `Base()` in `Base()`.
9. `Derived` chạy field initializer và block: `Derived.field`, `Derived.block`.
10. Body `Derived(String)` in `Derived(String): X`.
11. Body `Derived()` in `Derived()`.

### Object thứ hai

Lần `new Derived("Y")`:
- Không chạy lại hai static blocks vì class initialization đã hoàn tất.
- Vẫn chạy **mỗi instance field initializer/block của Base và Derived một lượt** cho object mới.
- Không chạy body `Derived()` vì constructor được chọn trực tiếp là `Derived(String)`.
- Constructor `Base()` vẫn ủy quyền cho `Base(int)` nên cả hai bodies của `Base` được chạy.

**Bài học:** dùng log như vậy dễ nhầm nếu không vẽ constructor chaining từ constructor được chọn ở `new` xuống constructor cuối cùng gọi superclass rồi quay lui.

## 34. Các lỗi thường gặp và cách sửa

| Nhầm lẫn / lỗi | Điều thực tế xảy ra | Cách suy nghĩ đúng |
| --- | --- | --- |
| `this(...)` tạo object mới | Nó ủy quyền constructor cùng object | Phân biệt `this(...)` với `new` |
| Mỗi constructor body chạy một instance block | Initializers của class chạy một lượt trong object initialization | Đếm per class/per object, không per constructor |
| Superclass constructor chạy sau subclass block | Superclass hoàn tất trước phần instance initialization subclass | Vẽ `super(...)` chain |
| Tất cả instance fields của mọi class được gán trước mọi constructor bodies | Chỉ default values toàn object có sớm; explicit initializers chạy theo từng class | Phân biệt default initialization và explicit initializers |
| Mọi field initializer chạy trước mọi block | Trong cùng class chúng chạy theo thứ tự văn bản xen kẽ | Đọc source order |
| Static block chạy mỗi `new` | Static block thuộc class initialization | Đếm riêng static/instance |
| Hai biến trỏ cùng object làm block chạy hai lần | Gán tham chiếu không tạo object | Đếm `new` được thực thi |
| `super()` tạo object cha riêng | Khởi tạo phần superclass của cùng object | Không cộng object allocation |
| Constructor `Child()` gọi `this(...)` rồi tự thêm `super()` | Không hợp lệ trong Java 17 | Chuỗi `this(...)` chỉ có một điểm kết thúc gọi superclass |
| Dùng `this(...)` sau lệnh in | Sai cú pháp Java 17 | Đặt explicit invocation đầu tiên |
| Constructor chaining vòng tròn | Recursive constructor invocation bị từ chối | Chọn một constructor đích có `super(...)` |
| Superclass thiếu no-arg constructor | Implicit `super()` không giải quyết được | Gọi `super(arguments)` phù hợp |
| Subclass field đã init khi constructor cha gọi method override | Chưa chắc; có thể chỉ là default value | Tránh gọi overridable methods trong ctor |
| Constructor body đặt giá trị trước instance initializer của chính class | Instance initializers chạy trước body đích | Tập trung field initialization rõ ràng |
| Instance block được truyền tham số constructor | Block không có parameter list | Dùng constructor/body/helper |
| Instance block lỗi nhưng constructor body vẫn chạy | Exception cắt ngang initialization bình thường | Phân tích control flow thực tế |
| `return;` trong constructor làm block không chạy | Block đã chạy trước body | Phân biệt initializer và constructor body |
| Cứ có `final field` là phải gán trong mọi overload | Delegating ctor có thể nhận kết quả gán từ constructor đích | Kiểm tra definite assignment cả chain |
| Đếm một object với nhiều constructors thành nhiều instances | Constructor bodies ≠ object allocations | Một `new` thông thường tạo một object |
| Instance initializer “chỉ một lần cho cả chương trình” | Mỗi instance mới có lượt của riêng mình | Đừng nhầm static initializer |

## 35. Bài tập tự luyện có đáp án

### Bài 1 — Hai constructor nối qua `this(...)`

```java
class A {
    { System.out.println("block"); }

    A() {
        this(1);
        System.out.println("zero");
    }

    A(int value) {
        System.out.println("int");
    }
}
```

**Hỏi:** `new A()` in gì?

**Đáp án:**

```text
block
int
zero
```

Instance block một lần, hai constructor bodies theo chiều quay lui.

### Bài 2 — Gọi overload trực tiếp

Với class `A` của bài 1, `new A(5)` in gì?

**Đáp án:**

```text
block
int
```

Không chạy body `A()` vì lời gọi chọn `A(int)` trực tiếp.

### Bài 3 — Hai object độc lập

```java
new A();
new A(2);
```

Với class `A` của bài 1, `block` in bao nhiêu lần?

**Đáp án:** **2 lần**, vì tạo hai instances. Constructor overload/chaining không nhân số block execution cho từng instance.

### Bài 4 — Superclass và subclass

```java
class P {
    { System.out.println("P block"); }
    P() { System.out.println("P ctor"); }
}

class C extends P {
    { System.out.println("C block"); }
    C() { System.out.println("C ctor"); }
}
```

**Hỏi:** `new C()` in gì?

**Đáp án:**

```text
P block
P ctor
C block
C ctor
```

Khởi tạo phần superclass trước phần subclass.

### Bài 5 — Hai blocks ở cùng class

```java
class A {
    { System.out.println("one"); }
    { System.out.println("two"); }
    A() { this(1); }
    A(int value) { System.out.println("ctor"); }
}
```

**Đáp án:** `new A()` in:

```text
one
two
ctor
```

Mỗi block riêng chạy một lượt, dù hai constructors nằm trong chain.

### Bài 6 — Xen kẽ field và block

```java
class A {
    int x = log("field x");
    { log("block"); }
    int y = log("field y");

    int log(String text) {
        System.out.println(text);
        return 1;
    }
}
```

**Đáp án:** `new A()` với constructor mặc định hợp lệ cho thứ tự:

```text
field x
block
field y
```

Khối và initializer xen kẽ theo thứ tự source.

### Bài 7 — Static vs instance

```java
class A {
    static { System.out.println("static"); }
    { System.out.println("instance"); }
    A() { System.out.println("ctor"); }
}
```

Nếu thực hiện `new A(); new A();` trong một lần chạy, class chưa được khởi tạo trước đó, thì:

**Đáp án:**

```text
static
instance
ctor
instance
ctor
```

Static block không lặp lại vì thêm instance mới.

### Bài 8 — Class cha gọi overridable method

```java
class P {
    P() { show(); }
    void show() { System.out.println("P"); }
}

class C extends P {
    int x = 10;

    @Override
    void show() {
        System.out.println(x);
    }
}
```

**Hỏi:** `new C()` in giá trị nào?

**Đáp án:** `0`. Dynamic dispatch từ constructor `P` tới `C.show()` xảy ra trước initializer `x = 10` của subclass.

### Bài 9 — Constructor chain vòng lặp

```java
class A {
    A() { this(1); }
    A(int x) { this(); }
}
```

**Đáp án:** Không biên dịch do recursive constructor invocation. Không có điểm kết thúc để khởi tạo superclass hợp lệ.

### Bài 10 — Constructor cha không có no-arg

```java
class P {
    P(int value) { }
}

class C extends P {
    C() {
        // Cần super(1);
    }
}
```

**Đáp án:** Với dạng chưa gọi `super(1)`, compiler chèn `super()` và gặp lỗi vì `P` không có no-arg constructor. Sửa thành:

```java
class C extends P {
    C() {
        super(1);
    }
}
```

### Bài 11 — Exception trong superclass

```java
class P {
    P() { throw new IllegalStateException(); }
}

class C extends P {
    { System.out.println("C block"); }
}
```

**Đáp án:** Khi `new C()` chạy, `C block` **không in**; superclass constructor ném exception trước khi control đến phần initializer của C.

### Bài 12 — `this(...)` có thể gán field final hai lần không?

```java
class A {
    final int value;

    A() {
        this(1);
        // value = 2;
    }

    A(int v) {
        value = v;
    }
}
```

**Đáp án:** `A()` hợp lệ khi dòng `value = 2` còn comment. Nếu bỏ comment, gán lại final field không hợp lệ. `this(1)` không chạy lại instance initializers mà ủy quyền gán final field cho constructor đích.

### Bài 13 — Đếm trên ba lớp

`A` có một instance block, `B extends A` có hai blocks, `C extends B` có một block. Chạy `new C()` ba lần, không exception, không tạo thêm objects lồng nhau.

**Đáp án:** Mỗi object gây `1 + 2 + 1 = 4` block executions; ba objects gây tổng **12**. Số constructor overload không ảnh hưởng kết quả.

### Bài 14 — Tạo object khác trong initializer

```java
class Helper {
    { System.out.println("Helper block"); }
}

class Owner {
    Helper helper = new Helper();
    { System.out.println("Owner block"); }
}
```

**Đáp án:** `new Owner()` in:

```text
Helper block
Owner block
```

Hai lines này thuộc **hai objects của hai classes khác nhau**: one Helper created inside field initializer and one Owner.

## 36. Checklist khi phân tích thứ tự khởi tạo

1. **Xác định lời gọi `new` được thực thi thật.** Có bao nhiêu objects được tạo trực tiếp hoặc lồng trong initializer?
2. **Kiểm tra class initialization:** static blocks/fields đã được khởi tạo chưa? Có superclass static initializer không?
3. **Vẽ superclass chain** từ class được tạo tới `Object`.
4. **Xác định constructor overload được chọn** bởi `new ClassName(arguments)`.
5. **Theo `this(...)` chain** cho tới constructor không tiếp tục gọi `this(...)`.
6. **Theo `super(...)` chain** lên superclass, xét cả lời gọi `super()` ngầm định.
7. **Trên đường quay về**, chạy mỗi class instance field initializers/blocks **một lượt**, theo thứ tự source trong class đó, trước body constructor đích.
8. **Chạy các constructor bodies theo chiều quay lui** của `this(...)` trong từng class.
9. **Không đếm `super(...)` như một object allocation mới.**
10. **Không nhân số lần instance block** với số constructor overload/bodies.
11. **Đừng dồn tất cả initializer của subclass trước constructor cha**; superclass được khởi tạo trước.
12. **Phân biệt default field values với explicit field initializers**; constructor cha có thể thấy default của subclass.
13. **Kiểm tra method overridable được gọi trong constructor**, nhất là khi đọc field subclass.
14. **Nếu có nhiều blocks cùng class**, mỗi block chạy một lượt; đếm tổng block executions đúng.
15. **Nếu có nhiều `new` instances**, áp dụng quy tắc lặp lại cho từng object mới.
16. **Nếu có exception**, dừng trace ở điểm ném; không tự in những body/blocks chưa được thực thi.
17. **Nếu có final fields**, kiểm tra definite assignment xuyên chuỗi `this(...)`.
18. **Kiểm tra cú pháp Java 17**: explicit `this(...)`/`super(...)` phải ở đầu constructor body.
19. **Đối chiếu stdout theo từng dòng** thay vì chỉ ghi “cha trước con” một cách chung chung.
20. **Khi thiết kế thực tế**, giữ constructor/initializers dễ đọc, tránh side effects và tránh làm lộ object trước khi xây dựng xong.

## Ghi nhớ

- **`this(...)` nối constructors trong cùng class và cùng một object**, không tạo thêm object và không chạy lại instance initializers.
- **`super(...)` khởi tạo phần superclass của cùng object**, không gọi `new Superclass(...)` tạo object cha khác.
- **Instance field initializers và instance initialization blocks** của một class chạy **một lượt cho phần instance của class đó trong mỗi lần tạo object bình thường**, không chạy một lượt cho mỗi constructor body.
- **Trong cùng class**, field initializers và instance blocks chạy xen kẽ **theo thứ tự khai báo**, trước body constructor đích.
- **Giữa các class**, superclass được khởi tạo trước subclass; constructor cha hoàn tất trước phần instance initialization của con.
- **Static initialization** thuộc class, thường thực hiện một lần theo ngữ nghĩa khởi tạo class; instance initialization thực hiện lại với mỗi object mới.
- **Một chain có ba constructor bodies** vẫn có thể chỉ có **một** instance block execution cho class đó khi tạo một object.
- **Dynamic dispatch từ constructor cha** có thể gọi override của subclass trước khi các field initializers subclass chạy; đó là lý do không nên gọi overridable method từ constructor.
- **Exception có thể cắt ngang chain**: chỉ những initializer/bodies thật sự đã tới được mới chạy.
- Khi giải bài, **đếm objects, vẽ `this/super` chain, đi từ superclass xuống subclass, và tách static khỏi instance**. Cách này cho kết quả ổn định hơn việc đoán từ số constructor trong code.
