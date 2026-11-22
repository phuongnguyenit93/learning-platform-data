# Phân biệt thành viên lớp, hàm khởi tạo và khối khởi tạo trong Java

## 1. Ba khái niệm cùng nằm trong thân `class` nhưng có vai trò khác nhau

Khi đọc một khai báo `class` trong Java, có thể bắt gặp các field, method, lớp lồng nhau, constructor và những khối lệnh không có tên. Chúng đều được viết trong cặp dấu `{ ... }` của lớp nhưng **không cùng loại khai báo**, không có cùng cách gọi và không chạy vào cùng thời điểm.

- **Thành viên lớp (*class members*)** là các field, method và kiểu thành viên lồng nhau (member class/interface) theo ngữ nghĩa của Java. Chúng định nghĩa trạng thái, hành vi và các kiểu liên quan được gắn với lớp. Field và method có thể là **instance** hoặc **`static`**.
- **Hàm khởi tạo (*constructor*)** định nghĩa cách tạo và khởi tạo một instance khi thực hiện lời gọi tạo đối tượng thích hợp. Constructor có tên trùng tên lớp, **không có kiểu trả về** và không được gọi như method thông thường. Theo Java Language Specification (JLS), constructor **không phải member** của lớp và không được kế thừa.
- **Khối khởi tạo (*initializer block*)** là một khối lệnh không có tên hoặc chữ ký method: `static { ... }` để khởi tạo lớp, hoặc `{ ... }` để khởi tạo instance. Theo JLS, các initializer block cũng **không phải member** của lớp. Chúng được hệ thống khởi tạo thực thi tại thời điểm thích hợp; chương trình không gọi trực tiếp bằng tên.

Còn có **field initializer**, tức biểu thức ở ngay khai báo field như `int count = 1;`. Nó thực hiện công việc khởi tạo nhưng **không phải một initializer block**. Phân biệt bốn thứ này giúp bạn giải thích chính xác việc dữ liệu được cấp giá trị ở đâu, câu lệnh chạy lúc nào và phần nào được phép truy cập từ mã bên ngoài.

### Nhìn nhanh bằng một lớp mẫu

```java
class Product {
    static int nextId = 1;          // Static field + field initializer
    private final int id;           // Instance field (blank final)
    private String name = "New";    // Instance field + field initializer

    static {                         // Static initializer block
        System.out.println("Product class initialized");
    }

    {                                // Instance initializer block
        id = nextId++;
    }

    Product(String name) {           // Constructor
        this.name = name;
    }

    String getName() {               // Instance method
        return name;
    }

    static int getNextId() {         // Static method
        return nextId;
    }

    static class Label {             // Static member class (nested type)
    }
}
```

Đây là **đoạn khai báo lớp có thể biên dịch**, chưa phải chương trình độc lập để chạy vì không có `main`. `id` là field `final` được gán đúng một lần trong instance initializer. Constructor gán `name`. Lần khởi tạo lớp đầu tiên sẽ thực thi initializer tĩnh; mỗi lần tạo instance sẽ thực thi instance initializer.

## 2. Bảng so sánh cốt lõi

| Tiêu chí | Thành viên lớp | Constructor | Initializer block |
| --- | --- | --- | --- |
| Hình thức | Field, method, nested member type | `ClassName(...) { ... }` | `static { ... }` hoặc `{ ... }` |
| Là *member* theo JLS? | Có | Không | Không |
| Có tên để tham chiếu? | Có tên field/method/kiểu | Có tên trùng lớp nhưng không gọi như method | Không |
| Có tham số? | Method có thể có; field và kiểu không theo nghĩa tham số lời gọi | Có thể có | Không |
| Có kiểu trả về? | Method có, kể cả `void`; field có kiểu dữ liệu | **Không có**, kể cả `void` | Không |
| `static` hay instance? | Field/method có thể là cả hai; nested member class có thể `static` | Luôn gắn với việc dựng instance, không khai báo `static` | Hai dạng: static và instance |
| Thực thi khi nào? | Field initializer khi khởi tạo thích hợp; method khi được gọi; kiểu lồng nhau không tự chạy chỉ vì được khai báo | Khi có lời gọi tạo instance/chuỗi constructor tương ứng | Static: khi khởi tạo lớp; instance: trong quá trình tạo từng instance |
| Có thể gọi trực tiếp? | Field được đọc/ghi và method được gọi theo quyền truy cập; kiểu được dùng trong biểu thức kiểu | Thông qua `new` hoặc chuỗi `this(...)`/`super(...)` theo cú pháp | Không |
| Được kế thừa? | Một số thành viên được thừa hưởng theo quy tắc truy cập/kế thừa | Không | Không |
| Mục đích | Mô tả API, trạng thái, hành vi, tổ chức kiểu | Nhận dữ liệu đầu vào và thiết lập instance hợp lệ | Khởi tạo logic chung trước thân constructor hoặc khởi tạo trạng thái của lớp |

Cần hiểu chữ **“thành viên lớp”** chính xác. Trong cách nói thông thường, một số tài liệu dùng “thành phần của lớp” theo nghĩa rất rộng, bao gồm cả constructor và initializer. Nhưng khi phân loại theo cú pháp/ngữ nghĩa Java, **member** là thuật ngữ kỹ thuật và không đồng nhất với “mọi thứ viết trong thân lớp”.

## 3. Thành viên lớp: field, method và kiểu lồng nhau

### 3.1. Field là dữ liệu thuộc instance hoặc lớp

Field là biến được khai báo trực tiếp trong thân lớp. Java chia thành:

- **Instance field**: mỗi đối tượng có trạng thái riêng. Ví dụ `private int balance;`; khi tạo hai tài khoản, mỗi tài khoản có `balance` riêng.
- **Static field**: thuộc về lớp, được chia sẻ giữa các instance. Ví dụ `private static int createdCount;`; thường truy cập theo tên lớp `Account.createdCount` nếu quyền truy cập cho phép.

```java
class Account {
    private static int nextNumber = 1;
    private final int number;
    private int balance;

    Account(int initialBalance) {
        this.number = nextNumber++;
        this.balance = initialBalance;
    }

    int getNumber() {
        return number;
    }

    int getBalance() {
        return balance;
    }
}
```

Đây là **mảnh mã lớp để minh họa**, không có `main`. `nextNumber` là static field dùng chung, `number` và `balance` là instance field. Hai instance được tạo liên tiếp nhận số hiệu khác nhau. Với hệ thống đồng thời, việc tăng một static field bằng `++` không tự bảo đảm an toàn luồng; ví dụ trên chỉ mô tả phân loại field trong một luồng.

Một field khai báo mà không gán giá trị rõ ràng sẽ nhận **giá trị mặc định** khi Java cấp phát đối tượng hoặc khởi tạo lớp: `int` là `0`, `boolean` là `false`, kiểu tham chiếu là `null`. Điều này khác với biến cục bộ trong method/constructor: biến cục bộ phải được gán trước khi đọc.

### 3.2. Method là hành vi có thể gọi bằng tên

```java
class Counter {
    private int value;

    void increment() {  // Instance method
        value++;
    }

    int getValue() {    // Instance method
        return value;
    }

    static int doubleOf(int n) {  // Static method
        return n * 2;
    }
}
```

- `counter.increment()` cần tham chiếu tới một đối tượng `Counter` hợp lệ vì thao tác trên `value` của đối tượng đó.
- `Counter.doubleOf(5)` gọi method `static`, không cần tạo instance.
- Method có kiểu trả về (ví dụ `int`, `void`), tên và danh sách tham số; có thể được **overload** bằng các danh sách tham số khác nhau.
- Static method không có `this`. Nó không thể truy cập trực tiếp instance field hoặc gọi instance method nếu không có tham chiếu tới đối tượng thích hợp.

Method thực thi **khi được gọi**, không tự chạy đơn giản vì lớp được khởi tạo hay đối tượng được tạo. Ngoại lệ liên quan đến việc method cụ thể bị gọi từ constructor/initializer theo mã của lập trình viên; bản thân việc khai báo method không khiến nó chạy.

### 3.3. Member type tổ chức các kiểu liên quan

```java
class Container {
    static class Entry {
        final String key;

        Entry(String key) {
            this.key = key;
        }
    }

    interface Validator {
        boolean isValid(String key);
    }
}
```

`Entry` là **static member class**, `Validator` là **member interface**. Chúng là các kiểu được khai báo bên trong `Container`; có thể dùng tên `Container.Entry` và `Container.Validator` từ vị trí có quyền truy cập. Việc viết khai báo kiểu lồng nhau không làm constructor của `Entry` tự chạy. `new Container.Entry("code")` mới tạo instance của `Entry`.

Một **non-static member class** (*inner class*) lại cần quan hệ với một đối tượng lớp bao ngoài, ví dụ `outer.new Inner()`. Cả hai hình thức đều là member type, nhưng quy tắc sở hữu instance khác nhau.

### 3.4. “Thành viên” không đồng nghĩa với “static”

Tên gọi **thành viên lớp** không có nghĩa tất cả các thành viên đều được khai báo `static`. Trong giao tiếp kỹ thuật thường gặp hai cách nói dễ gây lẫn:

- *Member of a class*: field/method/member type được khai báo trong một lớp, có thể thuộc instance hoặc `static`.
- *Class member* theo nghĩa “thành viên tĩnh”: một số người dùng cụm này để nói `static field`/`static method`, đối lập với *instance member*.

Khi đọc tài liệu Java, hãy xem ngữ cảnh và dùng các thuật ngữ cụ thể **`static field`, `instance field`, `static method`, `instance method`** để không nhầm “nằm trong lớp” với “thuộc chung về lớp”.

## 4. Constructor: nơi thiết lập một instance

Constructor không phải method thông thường, dù có thân chứa statement.

```java
class Ticket {
    private final String code;
    private int usedCount;

    Ticket(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        this.code = code;
    }

    Ticket() {
        this("DEFAULT"); // Gọi constructor khác của cùng lớp.
    }

    void use() {
        usedCount++;
    }

    String describe() {
        return code + ":" + usedCount;
    }
}
```

Đoạn này biên dịch được như một lớp nhưng **không có điểm vào `main`**. Có hai constructor: `Ticket()` và `Ticket(String)`. `this("DEFAULT")` chuyển trách nhiệm khởi tạo sang constructor còn lại của **cùng instance**, không tạo thêm một đối tượng.

Những quy tắc thiết yếu:

1. **Tên constructor phải trùng chính xác tên lớp**, kể cả chữ hoa/chữ thường; không ghi kiểu trả về. `void Ticket()` là **method**, không phải constructor.
2. Có thể **overload constructor** theo số lượng/kiểu/thứ tự tham số. Không phân biệt các constructor chỉ bằng quyền truy cập.
3. Constructor có thể có mức truy cập `public`, `protected`, `private` hoặc package-private, nhưng không thể `static`, `final`, `abstract`.
4. Constructor **không được kế thừa**: lớp con cần khai báo constructor của mình, hoặc nhận constructor mặc định nếu đáp ứng điều kiện.
5. Nếu lớp không khai báo constructor nào, compiler bổ sung một constructor mặc định không tham số với quyền truy cập tương ứng. Ngay khi lớp tự khai báo **bất kỳ constructor nào**, compiler không tự bổ sung constructor không tham số.
6. Với **Java 17**, lời gọi `this(...)` hay `super(...)` tường minh phải là statement đầu tiên trong thân constructor; không thể dùng cả hai để gọi trực tiếp trong cùng một constructor. Nếu không viết lời gọi tường minh, trình biên dịch sẽ tự chèn lời gọi constructor cha không tham số thích hợp khi quy tắc cho phép.
7. Field instance `final` chưa được gán ngay khi khai báo (*blank final*) phải được gán trong quá trình khởi tạo sao cho mọi constructor hoàn tất bình thường đều đáp ứng **definite assignment**, và không bị gán lại trái quy tắc.

Trong ví dụ `Ticket`, `code` được gán ở constructor hai tham số; constructor không tham số gọi qua `this(...)` nên vẫn bảo đảm `code` được khởi tạo.

### Constructor khác với lời gọi method

```java
class Sample {
    Sample() {                       // Constructor
        System.out.println("construct");
    }

    void Sample() {                  // Method tên Sample
        System.out.println("method");
    }
}
```

Nếu chạy `Sample s = new Sample();` thì constructor in `construct`. Chỉ khi gọi tiếp `s.Sample();` method mới in `method`. Viết thêm `void` làm thay đổi hoàn toàn ý nghĩa khai báo. Do đó khi nhìn một thành phần giống tên lớp, hãy kiểm tra **có kiểu trả về hay không**.

### Constructor và bất biến của đối tượng

Constructor thường là điểm kiểm soát điều kiện như “giá tiền không âm”, “tên không rỗng” hoặc “cặp tọa độ hợp lệ”. Đặt những kiểm tra này vào constructor giúp ngăn tạo instance không hợp lệ. Nếu nhiều constructor cùng thiết lập bất biến, dùng constructor chaining để tránh lặp kiểm tra.

Một constructor có thể gọi instance method nhưng cần thận trọng: gọi **method có thể override** trong quá trình xây dựng đối tượng có thể dispatch xuống lớp con trước khi trạng thái lớp con khởi tạo xong. Đây là một nguồn lỗi khó quan sát; nên ưu tiên xử lý trực tiếp các field của lớp trong constructor hoặc gọi helper không thể bị override khi thích hợp.

## 5. Khối khởi tạo tĩnh: `static { ... }`

Static initializer nằm trong thân lớp và có cú pháp:

```java
class Configuration {
    private static final int PORT;

    static {
        PORT = 8080;
    }

    static int port() {
        return PORT;
    }
}
```

Đoạn này hợp lệ; `PORT` là static blank final field, được gán một lần trong khối khởi tạo tĩnh. Java thực hiện các **static field initializers** và **static initializer blocks** theo thứ tự văn bản khi **lớp được khởi tạo**.

Một lớp thường được khởi tạo trước lần *active use* đầu tiên, như tạo một instance bằng `new`, gọi một static method hoặc đọc/ghi một static field không phải trường hợp hằng biên dịch được hưởng quy tắc đặc biệt. Việc JVM đã tải (*load*) metadata của lớp **không nhất thiết** đồng nghĩa static initializer đã chạy. Biểu thức `SomeType.class` tự nó thường không kích hoạt khởi tạo lớp, và việc đọc static final primitive/String *compile-time constant* có thể được inline mà không kích hoạt lớp khai báo.

Các quy tắc quan trọng:

- Static initializer **không có tên, tham số hoặc kiểu trả về**; không gọi trực tiếp bằng cú pháp `Configuration.static()` hay `new Configuration.static()`.
- Static initializer **không có `this`** và không thể tham chiếu trực tiếp field/method instance như thể đã có một đối tượng.
- Một lớp có thể có nhiều static initializer; chúng chạy xen kẽ với static field initializer theo thứ tự khai báo.
- Trong quá trình khởi tạo, Java bảo đảm cơ chế đồng bộ hóa khởi tạo lớp; điều này **không biến mọi thao tác trên static field sau đó thành thread-safe**.
- Exception phát sinh trong static initialization có thể làm khởi tạo lớp thất bại, ảnh hưởng các lần dùng tiếp theo. Không nên chứa I/O hoặc thao tác dễ lỗi trong static initializer nếu không có lý do thiết kế rõ ràng.

### Lỗi dễ gặp với static initializer

```java
class WrongStatic {
    private int value = 7;

    static {
        // System.out.println(value);
        // Dòng trên, nếu bỏ comment, sẽ lỗi biên dịch:
        // không thể tham chiếu field instance value từ ngữ cảnh static.
    }
}
```

Đây là khai báo lớp hợp lệ **vì lệnh sai đã được comment**. Muốn đọc `value` cần một đối tượng `WrongStatic` cụ thể; ngữ cảnh `static` không tự cung cấp `this`.

## 6. Khối khởi tạo instance: `{ ... }`

Instance initializer là khối không có `static` đứng trực tiếp trong thân lớp:

```java
class Session {
    private int retries;

    {
        retries = 3;
    }

    Session() {
    }

    int retries() {
        return retries;
    }
}
```

Khối `{ retries = 3; }` chạy trong quá trình **khởi tạo mỗi instance**, trước phần thân constructor của lớp tương ứng và sau khi công việc khởi tạo lớp cha hoàn tất theo thứ tự thông thường. Nó có thể tham chiếu tới `this` và instance field theo các quy tắc truy cập/tham chiếu trước khai báo của Java.

Đặc điểm:

- Không có tên, tham số, danh sách `throws` hay kiểu trả về.
- Không gọi trực tiếp; JVM/bytecode thực thi công việc được biên dịch từ initializer trong quy trình xây dựng instance.
- Một lớp có thể có nhiều instance initializer xen kẽ **instance field initializers**; chúng chạy theo thứ tự khai báo trong nguồn.
- Nếu lớp có nhiều constructor, các initializer instance của lớp chạy trong một lần khởi tạo đối tượng tương ứng, **không chạy thêm mỗi khi constructor ủy quyền qua `this(...)`**.
- Instance initializer có thể ném ngoại lệ, khiến quá trình tạo đối tượng thất bại. Ngoại lệ checked chịu các giới hạn biên dịch chặt chẽ; với công việc có thể lỗi, constructor thường thể hiện việc xử lý/khai báo ngoại lệ rõ hơn.

### Field initializer và instance initializer khác nhau ở đâu?

```java
class State {
    private int first = 10; // Field initializer
    private int second;     // Chưa gán tường minh: mặc định 0

    {                        // Instance initializer block
        second = first + 5;
    }

    State() {                // Constructor body
        first++;
    }

    String report() {
        return first + "," + second;
    }
}
```

Với `new State().report()`, kết quả là `11,15`. Cụ thể:

1. Field instance ban đầu có giá trị mặc định `0`.
2. Khai báo `first = 10` gán `10`.
3. Instance initializer đọc `first` và gán `second = 15`.
4. Constructor tăng `first` thành `11`.
5. `report()` đọc trạng thái sau khi xây dựng.

**Suy ra:** cả biểu thức gán ở khai báo field và khối instance đều tham gia khởi tạo, nhưng cú pháp và khả năng diễn đạt khác nhau. Field initializer phù hợp với một giá trị/biểu thức đơn giản, instance initializer dùng cho nhóm lệnh chung, constructor phù hợp với khởi tạo theo tham số và kiểm tra bất biến.

## 7. Ví dụ chạy đầy đủ: thứ tự khởi tạo qua kế thừa và `this(...)`

Tạo tệp **`InitializationFlowDemo.java`** với mã sau (tương thích **Java 17+**):

```java
class Parent {
    static {
        System.out.println("Parent.static");
    }

    {
        System.out.println("Parent.instance");
    }

    Parent() {
        System.out.println("Parent.constructor");
    }
}

class Gadget extends Parent {
    private static int limit = initLimit();

    static {
        System.out.println("Gadget.static block");
    }

    private final String name;
    private int stock = initStock();

    {
        System.out.println("Gadget.instance block");
    }

    Gadget() {
        this("Default");
        System.out.println("Gadget.noarg body");
    }

    Gadget(String name) {
        this.name = name;
        System.out.println("Gadget.constructor " + name);
    }

    private static int initLimit() {
        System.out.println("Gadget.static field");
        return 10;
    }

    private int initStock() {
        System.out.println("Gadget.instance field");
        return 1;
    }

    String describe() {
        return name + "/" + stock + "/" + limit;
    }
}

public class InitializationFlowDemo {
    public static void main(String[] args) {
        System.out.println("Start");
        Gadget first = new Gadget("A");
        Gadget second = new Gadget();

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac InitializationFlowDemo.java
java InitializationFlowDemo
```

**Standard output theo đúng thứ tự:**

```text
Start
Parent.static
Gadget.static field
Gadget.static block
Parent.instance
Parent.constructor
Gadget.instance field
Gadget.instance block
Gadget.constructor A
Parent.instance
Parent.constructor
Gadget.instance field
Gadget.instance block
Gadget.constructor Default
Gadget.noarg body
A/1/10
Default/1/10
```

### Phân tích lần tạo đối tượng thứ nhất

Lệnh `new Gadget("A")` là lần sử dụng chủ động đầu tiên của `Gadget` trong chương trình. Vì `Gadget` kế thừa `Parent`, **lớp cha được khởi tạo trước lớp con**:

```text
Khởi tạo Parent (một lần):
    Parent.static
Khởi tạo Gadget (một lần):
    Gadget.static field  -> limit = 10
    Gadget.static block

Tạo Gadget("A"):
    Giá trị instance mặc định được thiết lập
    Khởi tạo phần Parent:
        Parent.instance
        Parent.constructor
    Khởi tạo phần Gadget:
        Gadget.instance field  -> stock = 1
        Gadget.instance block
        Gadget.constructor A  -> name = "A"
```

Trong bản demo, `initLimit()` và `initStock()` là **method** được gọi bởi **field initializer**. Dòng log “Gadget.static field” hay “Gadget.instance field” xuất hiện khi initializer gọi method, chứ không phải vì mọi field initializer luôn tự in ra chữ nào đó.

### Phân tích lần tạo đối tượng thứ hai

`new Gadget()` đi vào constructor không tham số. Dòng `this("Default")` ủy quyền sang constructor `Gadget(String)`; đường đi chỉ xây dựng **một** instance:

```text
Tạo Gadget():
    (Không lặp static initialization)
    Parent.instance
    Parent.constructor
    Gadget.instance field
    Gadget.instance block
    Gadget.constructor Default
    Gadget.noarg body
```

Sau khi `Gadget(String)` hoàn thành, chương trình mới thực hiện câu `println` còn lại trong thân `Gadget()`. Điều này chứng minh constructor chaining **không tạo đối tượng thứ hai** và cũng không chạy khối instance hai lần.

Hai đối tượng có `stock == 1` riêng; cùng tham chiếu giá trị static `limit == 10`. Do đó hai dòng cuối là `A/1/10` và `Default/1/10`.

> Trong Java 17, đặt statement trước `this(...)` hoặc `super(...)` trong constructor là lỗi biên dịch. Hãy tuân thủ quy tắc phiên bản đang học; các cập nhật ngôn ngữ về “flexible constructor bodies” ở phiên bản Java mới hơn không áp dụng khi biên dịch với `--release 17`.

## 8. Sơ đồ tổng quát của vòng đời khởi tạo

```text
Khai báo lớp được biên dịch
          |
          v
JVM nạp/liên kết lớp khi cần (chưa chắc chạy static initializer)
          |
          v
Khởi tạo lớp khi bị yêu cầu (mỗi lượt khởi tạo của Class tương ứng)
          |
          +--> Khởi tạo các superclass thích hợp trước
          |
          +--> static field initializers + static { } theo thứ tự nguồn
          |
          v
Lệnh new tạo instance
          |
          +--> Cấp phát và đặt giá trị mặc định cho instance fields
          |
          +--> Gọi constructor cha (và chuỗi constructor của cha)
          |
          +--> instance field initializers + { } của lớp hiện tại
          |    theo thứ tự nguồn
          |
          +--> Thân constructor hiện tại
          |
          v
Instance đã dựng xong, có thể gọi method
```

Sơ đồ nhằm làm rõ thứ tự thông thường, không trình bày mọi trường hợp chi tiết của bộ nạp lớp, thất bại khởi tạo, khởi tạo thông qua reflection hay constructor chaining đa tầng. Với `this(...)`, quá trình khởi tạo trong lớp được thực hiện thông qua constructor đích rồi quay lại phần thân constructor ủy quyền; các field initializer và instance initializer **không lặp**.

Một điểm dễ nhầm: **giá trị mặc định của field** được đặt trong quá trình cấp phát/khởi tạo, nhưng **initializer có biểu thức** như `int x = compute();` được thực thi theo quy tắc thứ tự đã nêu. Nếu initializer đọc một field khác ở thời điểm không hợp lệ, Java có thể cấm tham chiếu trực tiếp theo tên đơn trước khi field đó được khai báo; những cách truy cập gián tiếp còn có thể thấy giá trị mặc định. Tránh để các field initializers phụ thuộc vòng tròn vào nhau.

### Thứ tự văn bản có thể đổi kết quả

Đoạn sau là lớp có thể biên dịch:

```java
class Ordered {
    static int number = 1;

    static {
        number = number * 2;
    }

    static int snapshot = number + 5;
}
```

Khi `Ordered` được khởi tạo, `number` lần lượt là `1` rồi `2`; `snapshot` thành `7`. Nếu chuyển khai báo `snapshot` **lên trước** khối `static`, snapshot sẽ là `6` vì lúc đó `number == 1`. Kết quả phản ánh thứ tự thực thi **static field initializers và static blocks** trong cùng lớp.

Quy tắc tương tự tồn tại giữa instance field initializer và instance block. Vì sự phụ thuộc thứ tự thường khó đọc, nên ưu tiên khai báo khởi tạo đơn giản, ít side effect và constructor rõ ràng.

## 9. Nên khởi tạo dữ liệu bằng cách nào?

Không có một lựa chọn duy nhất cho mọi trường hợp. Một cách ra quyết định thực tế:

| Nhu cầu | Vị trí phù hợp | Ví dụ |
| --- | --- | --- |
| Giá trị ban đầu cố định, biểu thức đơn giản của mỗi instance | Instance field initializer | `private int retryCount = 3;` |
| Giá trị ban đầu cố định của lớp | Static field initializer | `private static final int LIMIT = 100;` |
| Một nhóm lệnh khởi tạo static dùng chung, có phụ thuộc theo thứ tự | `static { ... }` khi thật cần | Khởi tạo cấu trúc dữ liệu tĩnh bằng vài bước |
| Công việc chung bắt buộc chạy cho mỗi instance trước thân constructor | Instance initializer `{ ... }` trong trường hợp có lý do cụ thể | Một khối nhất quán giữa nhiều constructor |
| Phụ thuộc tham số tạo đối tượng, cần validate, có nhiều biến thể | Constructor | `Account(String owner, long openingBalance)` |
| Thao tác cần thực thi theo yêu cầu sau khi tạo object | Instance method | `account.deposit(amount)` |
| Chức năng không dùng instance, gọi theo lớp | Static method | `Math.max(a, b)` hoặc factory method |

Trong mã ứng dụng thường ngày, hãy ưu tiên **field initializer** cho mặc định đơn giản và **constructor** để kiểm tra/thống nhất bất biến. Các instance initializer block ít phổ biến hơn vì dễ bị bỏ sót khi đọc mã và thường có thể chuyển logic sang constructor/constructor delegation. Không nên dùng static initializer để chạy kết nối mạng, truy cập DB hoặc điều kiện môi trường khó kiểm soát ngay lúc khởi tạo lớp.

### Phân biệt constructor với static factory method

```java
class Money {
    private final long cents;

    private Money(long cents) {
        this.cents = cents;
    }

    static Money ofCents(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("cents must not be negative");
        }
        return new Money(cents);
    }

    long cents() {
        return cents;
    }
}
```

`Money(long cents)` là **constructor private**; `ofCents(long cents)` là **static method** trả về một đối tượng `Money`. Người dùng lớp có thể gọi `Money.ofCents(150)` (nếu quyền truy cập cho phép), nhưng không thể gọi constructor private từ bên ngoài phạm vi cho phép. Đây là một ví dụ phân biệt bằng cú pháp: method có kiểu trả về `Money`, còn constructor không có kiểu trả về.

## 10. Những lỗi thường gặp

| Nhầm lẫn | Hệ quả và cách sửa |
| --- | --- |
| “Cái gì trong thân `class` cũng là thành viên được kế thừa” | Constructor và initializer không phải member theo JLS và không được kế thừa; method/field/member type có quy tắc thừa hưởng riêng. |
| “Constructor là method có tên trùng lớp” | Constructor không có return type và không phải method; `void Foo()` là method khác. |
| “`static { ... }` chạy khi tạo từng object” | Nó gắn với **khởi tạo lớp**, thường chạy một lần cho Class được khởi tạo, không chạy cho mỗi object. |
| “`{ ... }` luôn chỉ là scope bình thường” | Khối trần đặt trực tiếp trong class body là **instance initializer**; cùng cú pháp ngoặc trong method lại là block statement. |
| “Instance initializer chạy sau constructor” | Đối với lớp hiện tại, các instance initializers được thực hiện trước thân constructor tương ứng, sau khi superclass đã được khởi tạo. |
| “`this(...)` làm chạy tất cả initializer thêm một lượt” | Constructor delegation dùng một instance; initializer không lặp lại chỉ vì một constructor gọi constructor khác. |
| “Field static có nghĩa là hằng số” | `static` chỉ nói field thuộc lớp; muốn không gán lại thường phối hợp `final`, nhưng `final` cũng không làm object tham chiếu thành immutable. |
| “Một static method truy cập được `this`” | Static context không có `this`, muốn dùng instance field cần tham chiếu cụ thể. |
| “Bỏ mọi constructor thì không tạo được object” | Nếu lớp không có constructor tự khai báo, compiler thường cung cấp constructor mặc định không tham số, phụ thuộc điều kiện lớp cha. |
| “Có constructor nhận tham số thì vẫn tự có constructor rỗng” | Khi đã tự khai báo constructor, compiler không bổ sung constructor không tham số. |
| “Đảo thứ tự initializer nào cũng vô hại” | Các static/instance initializer và field initializer cùng nhóm chạy theo thứ tự văn bản; việc đổi chỗ có thể đổi trạng thái. |
| “Constructor lớp con chạy xong rồi mới gọi cha” | Khởi tạo superclass diễn ra trước logic instance của subclass trong chuỗi constructor thông thường. |
| “Static block có thể ném lỗi mà không ảnh hưởng lần dùng sau” | Lỗi trong class initialization có thể khiến lớp không thể sử dụng bình thường nữa trong class loader tương ứng. |

Các đoạn mã bên dưới minh họa **lỗi có chủ đích, không dùng để biên dịch**:

```java
class Broken {
    int value;

    static {
        // value = 1;       // Lỗi: truy cập instance field trong static context.
        // this.value = 1;  // Lỗi: static context không có this.
    }

    // Broken(int n) {
    //     System.out.println(n);
    //     this();          // Lỗi với Java 17: this(...) phải đứng đầu constructor.
    // }

    // static Broken() { } // Lỗi: constructor không được khai báo static.
}
```

Comment trong ví dụ chỉ đánh dấu vị trí có thể gây lỗi; khối `Broken` đang hiển thị biên dịch được. Không nhầm lỗi biên dịch với lỗi runtime: truy cập field instance sai static context là lỗi được compiler bắt, còn logic khởi tạo gây exception có thể là lỗi khi chạy.

## 11. Tự kiểm tra với câu hỏi và đáp án

**Câu 1.** Phần nào trong các thành phần sau là member theo JLS: `private int total;`, `Order() { }`, `void pay() { }`, `static { ... }`, `class Details { }` lồng trong `Order`?

**Đáp án:** Field `total`, method `pay` và member class `Details` là member; constructor `Order()` và static initializer không phải member.

**Câu 2.** Nếu class có hai constructor, mỗi constructor tạo một object khác nhau bằng `new`, một instance initializer chạy tổng cộng mấy lần?

**Đáp án:** Chạy **hai lần**, mỗi object một lần. Nếu constructor thứ nhất gọi `this(...)` sang constructor thứ hai trong **cùng một lần tạo object**, initializer chỉ chạy một lần cho object đó.

**Câu 3.** Vì sao method `static` không gọi được instance method không qua đối tượng?

**Đáp án:** Static method thuộc ngữ cảnh lớp, không mang `this`. Instance method cần một instance cụ thể để xác định các instance field và hành vi.

**Câu 4.** Trong ví dụ `InitializationFlowDemo`, tại sao `Parent.static` nằm trước `Gadget.static field` và `Gadget.static block`?

**Đáp án:** Khi `Gadget` bắt đầu khởi tạo, superclass `Parent` được khởi tạo trước. Sau đó các static field initializers và static blocks của `Gadget` chạy theo thứ tự nguồn.

**Câu 5.** Tại sao ví dụ thứ hai lại in `Gadget.constructor Default` rồi mới đến `Gadget.noarg body`?

**Đáp án:** `Gadget()` gọi `this("Default")`, nên constructor `Gadget(String)` thực thi trước; chỉ khi nó trả về thì phần thân còn lại của `Gadget()` mới chạy.

**Câu 6.** Chỗ nào thích hợp để kiểm tra `openingBalance >= 0` của `Account`, nếu điều kiện phải đúng ngay khi đối tượng được tạo?

**Đáp án:** Constructor nhận tham số số dư. Nếu có nhiều constructor, có thể điều phối chúng về một constructor làm kiểm tra chung. Sau này, các instance method thay đổi số dư cũng cần duy trì điều kiện liên quan.

**Câu 7.** Đoạn nào chạy trước: `int level = 3;` hay `{ level++; }` nếu cả hai là phần khởi tạo instance trong cùng lớp và được khai báo theo thứ tự đó?

**Đáp án:** Field initializer gán `3` trước, instance initializer tăng thành `4`. Nếu constructor tiếp tục sửa `level`, trạng thái cuối phụ thuộc phần thân constructor.

## 12. Checklist khi đọc mã Java thực tế

Để tránh kết luận nhầm về trạng thái đối tượng, hãy tìm theo thứ tự sau:

1. **Phân loại khai báo:** member field/method/nested type, constructor, static initializer hay instance initializer?
2. **Xác định phạm vi:** field/method `static` hay instance, mức truy cập nào, có `final` không?
3. **Tìm đường tạo object:** constructor nào được chọn theo danh sách tham số, có `this(...)`/`super(...)`, lớp cha có constructor phù hợp không?
4. **Lập thứ tự khởi tạo:** static initializers của superclass/subclass, instance initializers superclass/subclass và thân constructor được thực thi khi nào?
5. **Kiểm tra bất biến và side effect:** constructor/initializer có thể ném ngoại lệ hoặc gọi method override hay không; nhiều object có dùng chung mutable static state hay không?
6. **Đối chiếu output:** chỉ in ra một dòng khi có statement thực sự thực thi, không suy ra output từ việc khai báo member.

**Ghi nhớ:** **Member** khai báo trạng thái, hành vi hoặc kiểu lồng nhau; **constructor** thiết lập một instance khi xây dựng object; **initializer block** là lệnh được thực thi tự động trong quy trình khởi tạo lớp hoặc instance. Nhìn đúng loại thành phần và đúng thứ tự chạy giúp giải thích cả mã đơn giản lẫn quan hệ giữa `static`, kế thừa, field initializer và constructor chaining.