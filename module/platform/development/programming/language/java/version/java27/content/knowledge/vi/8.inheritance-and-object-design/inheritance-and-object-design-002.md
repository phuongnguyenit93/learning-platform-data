# Ghi đè phương thức, đa hình và dynamic dispatch

Trong Java 27, **ghi đè phương thức (method overriding)** cho phép lớp con cung cấp cách thực hiện riêng cho một phương thức instance mà nó kế thừa. **Đa hình (polymorphism)** cho phép cùng một kiểu tham chiếu, chẳng hạn lớp cha hoặc interface, đại diện cho nhiều kiểu đối tượng khác nhau. **Dynamic dispatch** là cơ chế chọn phiên bản phương thức instance phù hợp khi chương trình chạy dựa trên lớp thực tế của đối tượng nhận lời gọi.

Ba khái niệm này phối hợp để mã sử dụng một hợp đồng chung mà không phải biết từng lớp triển khai cụ thể. Chúng là nền tảng của thiết kế hướng đối tượng, nhưng cần hiểu rõ phạm vi áp dụng: Java chỉ thực hiện dynamic dispatch theo cơ chế ghi đè đối với các phương thức instance được phép ghi đè; việc chọn overload, truy cập field hoặc gọi phương thức static tuân theo quy tắc khác.

## 1. Ghi đè phương thức là gì?

Xét lớp **Animal** có phương thức **makeSound()** và hai lớp con **Dog**, **Cat**:

~~~java
class Animal {
    void makeSound() {
        System.out.println("Animal sound");
    }
}

class Dog extends Animal {
    @Override
    void makeSound() {
        System.out.println("Woof");
    }
}

class Cat extends Animal {
    @Override
    void makeSound() {
        System.out.println("Meow");
    }
}
~~~

**Dog** và **Cat** kế thừa từ **Animal** bằng từ khóa **extends**. Cả hai ghi đè **makeSound()** để cung cấp hành vi tương ứng.

~~~java
Animal first = new Dog();
Animal second = new Cat();

first.makeSound();
second.makeSound();
~~~

Kết quả:

~~~text
Woof
Meow
~~~

Dù **first** và **second** được khai báo với kiểu **Animal**, phương thức thực thi phụ thuộc vào đối tượng mà mỗi biến đang tham chiếu. Đó là hành vi đa hình thông qua ghi đè.

Lớp con cũng kế thừa các phương thức instance hợp lệ mà nó không ghi đè. Nếu lớp **Animal** có phương thức **sleep()** và **Dog** không ghi đè phương thức này, đối tượng **Dog** vẫn dùng phần triển khai được kế thừa.

## 2. Quy tắc của method overriding

Để thực sự ghi đè, phương thức của lớp con phải đáp ứng các quy tắc của Java về chữ ký phương thức, kiểu trả về, quyền truy cập và ngoại lệ.

### Chữ ký phương thức

Trong trường hợp thông thường, tên phương thức và danh sách kiểu tham số phải tương ứng với phương thức được ghi đè. Kiểu trả về không phải là một phần của chữ ký dùng để phân biệt overload.

~~~java
class Parent {
    void process(String text) {
        System.out.println("Parent: " + text);
    }
}

class Child extends Parent {
    @Override
    void process(String text) {
        System.out.println("Child: " + text);
    }
}
~~~

Đây là overriding vì **Child.process(String)** thay thế cách triển khai của **Parent.process(String)**.

Nếu lớp con thay đổi danh sách tham số, phương thức mới thường là **nạp chồng (overloading)** thay vì ghi đè:

~~~java
class Parent {
    void process(String text) {
        System.out.println(text);
    }
}

class Child extends Parent {
    void process(int number) {
        System.out.println(number);
    }
}
~~~

Trong ví dụ thứ hai, **Child** có thêm **process(int)** nhưng vẫn kế thừa **process(String)**.

Với generic và type erasure, Java còn có quy tắc *subsignature* để xác định phương thức có ghi đè hợp lệ hay không. Khi viết mã thông thường, nên giữ tên và danh sách tham số nhất quán, sử dụng **@Override** để trình biên dịch kiểm tra.

### Annotation @Override

**@Override** thể hiện rằng một khai báo phương thức có ý định ghi đè một phương thức từ lớp cha hoặc triển khai phương thức của interface.

~~~java
class Vehicle {
    void start() {
        System.out.println("Starting");
    }
}

class Car extends Vehicle {
    @Override
    void start() {
        System.out.println("Car starting");
    }
}
~~~

Nếu vô tình viết **starts()** thay vì **start()**, annotation **@Override** sẽ khiến trình biên dịch báo lỗi vì không tìm thấy phương thức phù hợp để ghi đè.

~~~java
class Car extends Vehicle {
    // @Override // Nếu bỏ comment annotation, đây là lỗi biên dịch.
    void starts() {
        System.out.println("Car starting");
    }
}
~~~

Nên dùng **@Override** khi ghi đè hoặc triển khai phương thức interface; annotation giúp phát hiện lỗi sai tên và sai chữ ký ngay lúc biên dịch.

### Quyền truy cập không được thu hẹp

Phương thức ghi đè không được giảm mức truy cập so với phương thức được ghi đè.

~~~java
class Service {
    protected void execute() {
        System.out.println("Service");
    }
}

class NetworkService extends Service {
    @Override
    public void execute() {
        System.out.println("Network service");
    }
}
~~~

Đổi **protected** thành **public** là hợp lệ vì quyền truy cập được mở rộng. Ngược lại, ghi đè một phương thức **public** thành **protected** hoặc **private** sẽ gây lỗi biên dịch.

### Kiểu trả về tương thích

Phương thức ghi đè phải có kiểu trả về tương thích với phương thức gốc. Với kiểu tham chiếu, Java cho phép **covariant return type**: lớp con có thể trả về một kiểu con cụ thể hơn.

~~~java
class Document {
    Document copy() {
        return new Document();
    }
}

class PdfDocument extends Document {
    @Override
    PdfDocument copy() {
        return new PdfDocument();
    }
}
~~~

**PdfDocument.copy()** hợp lệ vì **PdfDocument** là kiểu con của **Document**. Với kiểu trả về nguyên thủy, không thể tùy ý đổi sang một kiểu nguyên thủy khác chỉ vì có thể chuyển đổi giá trị giữa chúng.

### Ngoại lệ checked không được mở rộng

Một phương thức ghi đè không được khai báo thêm hoặc mở rộng checked exception vượt ra ngoài những checked exception được phép bởi phương thức gốc.

~~~java
import java.io.IOException;

class DataSource {
    void load() throws IOException {
        System.out.println("Loading");
    }
}

class MemorySource extends DataSource {
    @Override
    void load() {
        System.out.println("Loaded from memory");
    }
}
~~~

**MemorySource.load()** hợp lệ vì phương thức ghi đè có thể không khai báo checked exception nào. Nếu khai báo **throws Exception** trong ví dụ này, chương trình sẽ không biên dịch được vì **Exception** rộng hơn **IOException**. Các unchecked exception như **RuntimeException** không chịu giới hạn này theo cùng cách.

## 3. Đa hình qua lớp cha

Đa hình cho phép viết mã dựa trên lớp cha và xử lý các đối tượng thuộc lớp con.

~~~java
class Animal {
    String move() {
        return "Moving";
    }
}

class Bird extends Animal {
    @Override
    String move() {
        return "Flying";
    }
}

class Fish extends Animal {
    @Override
    String move() {
        return "Swimming";
    }
}

class Zoo {
    static void showMovement(Animal animal) {
        System.out.println(animal.move());
    }

    public static void main(String[] args) {
        showMovement(new Bird());
        showMovement(new Fish());
    }
}
~~~

Kết quả:

~~~text
Flying
Swimming
~~~

Phương thức **showMovement(Animal)** không cần kiểm tra xem đối tượng là **Bird** hay **Fish**. Chỉ cần đối tượng có kiểu tương thích với **Animal** là có thể truyền vào phương thức.

Điểm quan trọng:

- Kiểu **Animal** ở tham số xác định tập thành viên mà mã gọi được tại thời điểm biên dịch.
- Đối tượng thật sự là **Bird** hoặc **Fish** xác định cách triển khai của **move()** được chọn khi chạy.
- Thêm một lớp con mới ghi đè **move()** thường không buộc phải sửa phương thức **showMovement()**.

Đa hình có ích khi nhiều kiểu đối tượng cần tuân theo một hợp đồng chung và cung cấp cách xử lý khác nhau.

## 4. Dynamic dispatch diễn ra thế nào?

Java tách việc kiểm tra lời gọi phương thức thành hai khía cạnh:

1. **Thời điểm biên dịch:** kiểm tra kiểu của biểu thức nhận lời gọi, xác định phương thức có thể gọi, kiểm tra tham số và quyền truy cập.
2. **Thời điểm chạy:** với lời gọi phương thức instance có ghi đè, chọn cách triển khai phù hợp theo lớp thực tế của đối tượng nhận lời gọi.

Ví dụ:

~~~java
class Message {
    void deliver() {
        System.out.println("Deliver message");
    }
}

class EmailMessage extends Message {
    @Override
    void deliver() {
        System.out.println("Send email");
    }
}

Message message = new EmailMessage();
message.deliver();
~~~

Kết quả:

~~~text
Send email
~~~

Giải thích từng bước:

1. Biến **message** có kiểu khai báo **Message**.
2. **Message** có phương thức instance **deliver()**, nên lời gọi **message.deliver()** hợp lệ khi biên dịch.
3. Giá trị đang nằm trong **message** là tham chiếu tới một đối tượng **EmailMessage**.
4. Lúc chạy, Java chọn phiên bản **deliver()** được ghi đè trong **EmailMessage**.

Nếu sau đó gán **message = new Message()** và gọi lại, cách triển khai trong **Message** được dùng. Cùng một câu lệnh gọi phương thức có thể tạo ra hành vi khác nhau theo đối tượng nhận lời gọi.

Dynamic dispatch thường được mô tả là **late binding** cho phương thức instance. Không nên hiểu rằng mọi lời gọi trong Java đều được quyết định hoàn toàn tại thời điểm chạy: quá trình biên dịch vẫn quyết định kiểu hợp lệ và lựa chọn chữ ký phương thức.

### Ghi đè nhiều tầng

Nếu hệ thống có nhiều tầng kế thừa, Java chọn cách triển khai ghi đè phù hợp nhất với kiểu thực tế của đối tượng.

~~~java
class A {
    void show() {
        System.out.println("A");
    }
}

class B extends A {
    @Override
    void show() {
        System.out.println("B");
    }
}

class C extends B {
    @Override
    void show() {
        System.out.println("C");
    }
}

A value = new C();
value.show(); // C
~~~

Kết quả là **C** vì đối tượng thật sự thuộc lớp **C** và lớp đó có phiên bản ghi đè **show()**.

## 5. Đa hình qua interface

Java không yêu cầu phải có một lớp cha cụ thể để sử dụng đa hình. **Interface** định nghĩa hợp đồng mà nhiều lớp có thể triển khai độc lập.

~~~java
interface PaymentMethod {
    void pay(long amountInCents);
}

class CardPayment implements PaymentMethod {
    @Override
    public void pay(long amountInCents) {
        System.out.println("Card payment: " + amountInCents);
    }
}

class BankTransfer implements PaymentMethod {
    @Override
    public void pay(long amountInCents) {
        System.out.println("Bank transfer: " + amountInCents);
    }
}

class Checkout {
    static void complete(PaymentMethod method, long amountInCents) {
        method.pay(amountInCents);
    }

    public static void main(String[] args) {
        complete(new CardPayment(), 50_000);
        complete(new BankTransfer(), 75_000);
    }
}
~~~

Kết quả:

~~~text
Card payment: 50000
Bank transfer: 75000
~~~

**Checkout.complete()** chỉ phụ thuộc vào interface **PaymentMethod**, vì vậy có thể làm việc với mọi lớp triển khai interface này. Java thực hiện lựa chọn cách triển khai **pay()** tương ứng với đối tượng thật.

Phương thức triển khai một phương thức **public** của interface phải được khai báo **public**. Viết **void pay(...)** với quyền truy cập package-private trong lớp triển khai sẽ không đáp ứng yêu cầu truy cập.

### Interface default method và ghi đè

Interface có thể cung cấp **default method**. Lớp triển khai có thể dùng cách thực hiện mặc định hoặc ghi đè nó.

~~~java
interface Greeter {
    default String greet() {
        return "Hello";
    }
}

class VietnameseGreeter implements Greeter {
    @Override
    public String greet() {
        return "Xin chao";
    }
}
~~~

Lời gọi **greet()** trên đối tượng **VietnameseGreeter** dùng phiên bản của lớp. Khi cần gọi rõ default method của một superinterface phù hợp, lớp có thể sử dụng cú pháp **InterfaceName.super.methodName()** trong ngữ cảnh hợp lệ.

Nếu có nhiều default method cùng chữ ký từ các interface khác nhau, lớp triển khai có thể phải giải quyết xung đột bằng cách cung cấp phương thức ghi đè tường minh.

## 6. Overriding khác overloading

Hai cơ chế thường bị nhầm lẫn:

| Tiêu chí | Overriding (ghi đè) | Overloading (nạp chồng) |
|---|---|---|
| Mục tiêu | Thay đổi cách triển khai một phương thức được kế thừa | Cung cấp nhiều phương thức cùng tên với danh sách tham số khác nhau |
| Nơi xuất hiện | Trong quan hệ kế thừa lớp hoặc triển khai interface | Trong cùng lớp hoặc giữa các lớp có quan hệ kế thừa |
| Chữ ký | Phải đáp ứng quy tắc override/subsignature | Phân biệt theo kiểu hoặc số lượng tham số |
| Lựa chọn | Cách triển khai phương thức instance phụ thuộc kiểu thực tế của receiver khi chạy | Chọn overload dựa trên kiểu tại thời điểm biên dịch |
| Annotation | Thường dùng **@Override** | Không dùng **@Override** để chỉ việc nạp chồng |

Ví dụ sự khác biệt giữa kiểu khai báo và kiểu thực tế:

~~~java
class Animal {}
class Dog extends Animal {}

class Printer {
    void print(Animal animal) {
        System.out.println("Animal overload");
    }

    void print(Dog dog) {
        System.out.println("Dog overload");
    }
}

Animal pet = new Dog();
Printer printer = new Printer();
printer.print(pet);
~~~

Kết quả:

~~~text
Animal overload
~~~

Dù đối tượng thực tế là **Dog**, trình biên dịch chọn **print(Animal)** vì biểu thức **pet** có kiểu **Animal** tại vị trí gọi. Đây là overloading.

Bây giờ ghi đè overload **print(Animal)** ở một lớp con:

~~~java
class SpecialPrinter extends Printer {
    @Override
    void print(Animal animal) {
        System.out.println("Special animal");
    }
}

Printer printer = new SpecialPrinter();
Animal pet = new Dog();
printer.print(pet);
~~~

Kết quả:

~~~text
Special animal
~~~

Trình biên dịch vẫn chọn chữ ký **print(Animal)**, còn dynamic dispatch chọn cách triển khai được ghi đè trong **SpecialPrinter** khi chạy. Hai quy tắc này có thể hoạt động trong cùng một lời gọi.

## 7. Những thành viên không được dynamic dispatch theo overriding

Không phải thành viên nào được kế thừa cũng ghi đè theo cách của instance method.

### Phương thức static: method hiding

Phương thức **static** thuộc về lớp. Nếu lớp con khai báo một static method cùng chữ ký với static method có thể được thừa kế từ lớp cha, đây là **method hiding**, không phải overriding.

~~~java
class Base {
    static String typeName() {
        return "Base";
    }
}

class Derived extends Base {
    static String typeName() {
        return "Derived";
    }
}

Base reference = new Derived();

System.out.println(Base.typeName());     // Base
System.out.println(Derived.typeName());  // Derived
~~~

Nên gọi static method thông qua tên lớp để thể hiện rõ nơi định nghĩa. Trong trường hợp gọi static method qua biến tham chiếu (dù không được khuyến khích), kiểu tại thời điểm biên dịch của biểu thức được dùng để xác định lời gọi; Java không chọn phiên bản static theo kiểu runtime như với instance method.

Không được dùng **@Override** cho một static method với ý định ghi đè static method của lớp cha.

### Field: field hiding

Field không được ghi đè theo dynamic dispatch. Nếu lớp con khai báo field cùng tên, tên field được xác định dựa trên kiểu và cách truy cập tại thời điểm biên dịch.

~~~java
class Base {
    String label = "Base field";

    String describe() {
        return "Base method";
    }
}

class Derived extends Base {
    String label = "Derived field";

    @Override
    String describe() {
        return "Derived method";
    }
}

Base object = new Derived();

System.out.println(object.label);
System.out.println(object.describe());
~~~

Kết quả:

~~~text
Base field
Derived method
~~~

**object.label** dùng field của **Base** do kiểu khai báo của biến **object** là **Base**. **object.describe()** dùng method được ghi đè trong **Derived** vì đối tượng thật sự là **Derived**.

Đặt field cùng tên giữa lớp cha và lớp con dễ gây nhầm lẫn; thường nên tránh field hiding trong thiết kế.

### final, private và constructor

- **final instance method:** không thể bị lớp con ghi đè.
- **private method:** không được kế thừa theo cách cho phép lớp con ghi đè; lớp con có thể khai báo phương thức cùng tên và tham số nhưng đó không phải overriding của private method.
- **Constructor:** không được kế thừa hoặc ghi đè. Lớp con khởi tạo phần lớp cha theo quy tắc gọi constructor.
- **static method:** không được ghi đè bằng instance method hoặc ngược lại.

Ví dụ:

~~~java
class Account {
    public final String id() {
        return "fixed-id";
    }

    private void audit() {
        System.out.println("Internal audit");
    }
}

class SavingsAccount extends Account {
    // public String id() { ... } // Lỗi biên dịch: id() là final.

    void audit() {
        System.out.println("Savings account audit");
    }
}
~~~

**SavingsAccount.audit()** là phương thức riêng của lớp con; nó không ghi đè **Account.audit()**.

## 8. super, this và truy cập cách triển khai ở lớp cha

Trong instance method của lớp con, **this** tham chiếu tới đối tượng hiện tại; **super** cho phép gọi phương thức hoặc truy cập thành viên kế thừa của lớp cha theo quy tắc Java.

~~~java
class Logger {
    void log(String message) {
        System.out.println("LOG: " + message);
    }
}

class TimestampLogger extends Logger {
    @Override
    void log(String message) {
        super.log("[timestamp] " + message);
    }
}
~~~

Ở đây, **super.log(...)** gọi cách triển khai của **Logger** từ method ghi đè trong **TimestampLogger**. Nó giúp mở rộng hành vi của lớp cha thay vì viết lại toàn bộ.

**super.method()** không thực hiện lựa chọn phương thức theo kiểu runtime của receiver như lời gọi instance thông thường; nó chỉ định rõ cách triển khai được kế thừa từ lớp cha theo các quy tắc của Java.

Có thể dùng **super(...)** trong constructor để gọi constructor lớp cha, nhưng đây là cơ chế khởi tạo đối tượng, không phải method overriding.

Không thể dùng **this** hoặc **super** trong static context theo cách đòi hỏi một instance đang tồn tại.

## 9. Kết hợp đa hình với interface và kiểu Java hiện đại

Đa hình không chỉ xuất hiện trong cây kế thừa lớp sâu. Java hiện đại hỗ trợ **record** và **sealed interface** để mô hình hóa một tập kiểu dữ liệu có ranh giới rõ ràng.

Ví dụ, một hệ thống có hai loại kết quả xử lý:

~~~java
sealed interface OperationResult permits Success, Failure {
    String summary();
}

record Success(String value) implements OperationResult {
    @Override
    public String summary() {
        return "Success: " + value;
    }
}

record Failure(String reason) implements OperationResult {
    @Override
    public String summary() {
        return "Failure: " + reason;
    }
}

class ResultDemo {
    static void show(OperationResult result) {
        System.out.println(result.summary());
    }

    public static void main(String[] args) {
        show(new Success("Saved"));
        show(new Failure("Invalid input"));
    }
}
~~~

Kết quả:

~~~text
Success: Saved
Failure: Invalid input
~~~

Ở đây:

- **OperationResult** là hợp đồng chung.
- **sealed** giới hạn những kiểu được phép trực tiếp triển khai interface, theo danh sách **permits**.
- **Success** và **Failure** là các record, tự có những thành viên dữ liệu cơ bản mà Java sinh từ record component.
- Hai record đều ghi đè **summary()**, nên lời gọi qua tham chiếu **OperationResult** được dispatch theo đối tượng thật.

Record là kiểu lớp không thể được kế thừa bằng **extends**; record vẫn có thể triển khai interface. Với dữ liệu đơn giản, cách kết hợp record và interface có thể giảm mã lặp mà vẫn giữ được đa hình.

Nếu hệ thống cần xử lý riêng từng kiểu cụ thể, Java cũng hỗ trợ pattern matching như **instanceof** pattern và **switch** trên kiểu phù hợp. Tuy vậy, khi hành vi thuộc trách nhiệm của từng kiểu, gọi phương thức đa hình thường giúp giữ logic xử lý gần với dữ liệu của kiểu đó hơn.

## 10. Lời gọi trong constructor và nguy cơ dispatch quá sớm

Dynamic dispatch vẫn áp dụng khi constructor lớp cha gọi một phương thức instance có thể bị ghi đè. Điều này có thể khiến phương thức của lớp con chạy **trước khi phần khởi tạo của lớp con hoàn tất**.

~~~java
class Base {
    Base() {
        printStatus();
    }

    void printStatus() {
        System.out.println("Base");
    }
}

class Child extends Base {
    private String status = "ready";

    @Override
    void printStatus() {
        System.out.println(status);
    }
}
~~~

Khi chạy:

~~~java
new Child();
~~~

Kết quả:

~~~text
null
~~~

Giải thích: trong lúc constructor của **Base** đang thực thi, đối tượng đã có kiểu thực tế **Child**, nên lời gọi **printStatus()** được dispatch tới **Child.printStatus()**. Tuy nhiên, field **status** của phần lớp con vẫn chưa được gán giá trị khởi tạo tường minh **"ready"**; tại thời điểm đó nó còn mang giá trị mặc định **null**.

Do vậy, nên tránh gọi phương thức có thể bị ghi đè từ constructor nếu phương thức đó có thể phụ thuộc vào trạng thái lớp con. Có thể dùng phương thức **private** hoặc **final** cho logic khởi tạo nội bộ không cần đa hình, hoặc hoàn tất việc tạo đối tượng trước khi gọi các hành vi mở rộng.

## 11. Thiết kế hướng đối tượng với overriding và polymorphism

Overriding hữu ích khi lớp con thực sự là một dạng chuyên biệt của lớp cha và phải tuân theo hợp đồng chung. Một thiết kế tốt cần giữ khả năng thay thế: mã đang dùng lớp cha hoặc interface vẫn phải hoạt động đúng khi nhận instance lớp con.

Những nguyên tắc thường áp dụng:

- **Phụ thuộc vào abstraction:** viết mã nhận interface hoặc lớp trừu tượng nếu có nhiều cách triển khai hợp lệ.
- **Dùng @Override:** giúp trình biên dịch xác nhận ý định ghi đè và tránh sai chữ ký.
- **Giữ hợp đồng hành vi:** lớp con không nên làm mất các cam kết cơ bản mà người gọi kỳ vọng từ lớp cha.
- **Giữ khả năng mở rộng có chủ đích:** chỉ mở method cho overriding khi thật sự cần; dùng **final** nếu hành vi cần được cố định.
- **Không lạm dụng kế thừa:** nếu một lớp chỉ sử dụng chức năng của lớp khác, composition thường phù hợp hơn quan hệ extends.
- **Tránh kiểm tra kiểu liên tiếp:** nếu nhiều nhánh **instanceof** chỉ để gọi những hành vi khác nhau, hãy cân nhắc đưa hành vi đó vào một phương thức đa hình.
- **Giữ API rõ ràng:** công khai hợp đồng cần thiết; hạn chế phụ thuộc vào chi tiết triển khai, field hiding và static method hiding.

Ví dụ minh họa composition thay vì kế thừa không phù hợp:

~~~java
interface MessageSender {
    void send(String message);
}

class EmailSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}

class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }

    void notifyUser(String message) {
        sender.send(message);
    }
}
~~~

**NotificationService** sử dụng một **MessageSender** thông qua field thay vì kế thừa từ sender. Khi cần thay đổi kênh gửi, có thể truyền một triển khai khác mà không sửa logic của service.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Phương thức lớp con không được gọi | Khai báo sai chữ ký nên tạo overload, hoặc phương thức không thể override | Dùng **@Override** và kiểm tra kiểu tham số, tên và modifier |
| Báo lỗi khi override | Thu hẹp quyền truy cập, trả về không tương thích hoặc mở rộng checked exception | Giữ hợp đồng truy cập, kiểu trả về và ngoại lệ hợp lệ |
| Gọi static method cho kết quả lớp cha | Static method được lựa chọn theo kiểu tại thời điểm biên dịch | Gọi qua tên lớp; không kỳ vọng dynamic dispatch cho static |
| Truy cập field cho giá trị lớp cha | Field hiding không dùng dynamic dispatch | Tránh field trùng tên; dùng method truy cập nếu cần hành vi đa hình |
| **@Override** báo lỗi trên method private | Private method của lớp cha không phải mục tiêu ghi đè | Đổi thiết kế quyền truy cập nếu thực sự cần khả năng mở rộng |
| Gọi method con từ constructor cha thấy trạng thái **null** | Dispatch xảy ra trước khi field lớp con được khởi tạo tường minh | Tránh gọi method có thể override trong constructor |
| Ép kiểu lớp cha xuống lớp con gây **ClassCastException** | Đối tượng thực tế không thuộc kiểu con được ép | Không downcast khi không cần; nếu cần, kiểm tra **instanceof** |
| Method lớp con không nhận interface contract | Method triển khai không đủ **public** hoặc không khớp chữ ký | Giữ đúng chữ ký và quyền truy cập **public** |
| Nhầm overloading với overriding | Nhìn vào kiểu runtime khi dự đoán overload | Xác định overload theo kiểu compile-time, rồi xác định override theo runtime |

### Ví dụ ép kiểu an toàn

~~~java
Animal animal = new Dog();

if (animal instanceof Dog dog) {
    System.out.println("The animal is a dog");
}
~~~

**instanceof** pattern kiểm tra kiểu đối tượng tại thời điểm chạy và giới thiệu biến **dog** nếu kiểm tra thành công. Cách này tránh ép kiểu không an toàn khi cần làm việc với đặc điểm riêng của lớp con.

## 13. Ví dụ tổng hợp: tính phí giao hàng

Ví dụ sau sử dụng interface làm hợp đồng chung, các lớp triển khai ghi đè method tính phí và một lớp service chỉ làm việc với interface.

~~~java
interface ShippingPolicy {
    long calculateFee(long orderTotalInCents);
}

class StandardShipping implements ShippingPolicy {
    @Override
    public long calculateFee(long orderTotalInCents) {
        return 3_000;
    }
}

class FreeShippingOverThreshold implements ShippingPolicy {
    private final long thresholdInCents;

    FreeShippingOverThreshold(long thresholdInCents) {
        this.thresholdInCents = thresholdInCents;
    }

    @Override
    public long calculateFee(long orderTotalInCents) {
        return orderTotalInCents >= thresholdInCents ? 0 : 3_000;
    }
}

class ShippingCalculator {
    static long totalWithShipping(
            long orderTotalInCents,
            ShippingPolicy policy) {
        return orderTotalInCents + policy.calculateFee(orderTotalInCents);
    }

    public static void main(String[] args) {
        ShippingPolicy standard = new StandardShipping();
        ShippingPolicy promotion = new FreeShippingOverThreshold(50_000);

        System.out.println(totalWithShipping(60_000, standard));
        System.out.println(totalWithShipping(60_000, promotion));
        System.out.println(totalWithShipping(20_000, promotion));
    }
}
~~~

Kết quả:

~~~text
63000
60000
23000
~~~

**ShippingCalculator** được biên dịch dựa trên interface **ShippingPolicy**. Khi chạy, lời gọi **policy.calculateFee(...)** chọn cách triển khai trong **StandardShipping** hoặc **FreeShippingOverThreshold** tùy đối tượng thực tế. Đây là sự kết hợp của **method overriding**, **polymorphism** và **dynamic dispatch**.

Khi học hoặc đọc mã Java 27, hãy phân biệt ba câu hỏi: phương thức nào được phép gọi dựa trên kiểu khai báo; phiên bản instance method nào được thực thi dựa trên đối tượng thật; và lời gọi có phải overriding hay là overloading, static hiding hoặc field access. Trả lời đúng ba câu hỏi này giúp dự đoán kết quả chương trình và thiết kế các lớp có thể mở rộng, dễ kiểm thử và dễ bảo trì.
