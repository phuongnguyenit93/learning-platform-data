# Phương thức được phép gọi theo kiểu khai báo trong Java

## 1. Quy tắc cốt lõi của đa hình

Trong Java, một biến tham chiếu luôn có **kiểu khai báo** (declared type, còn gọi là static type hoặc compile-time type), và tại thời điểm chạy biến đó có thể trỏ đến một đối tượng thuộc **kiểu thực tế** (runtime class) là một lớp con hoặc lớp triển khai tương thích.

Ví dụ:

```java
Animal animal = new Dog();
```

- `Animal` là **kiểu khai báo** của biểu thức tham chiếu `animal`.
- `Dog` là **lớp thực tế** của đối tượng được tạo bởi `new Dog()`.
- Khi viết `animal.someMethod()`, **compiler trước hết kiểm tra phương thức có thể được gọi thông qua kiểu `Animal` hay không**, bao gồm tên, danh sách tham số, phạm vi truy cập và ngữ cảnh gọi.
- Sau khi lời gọi hợp lệ, nếu đây là **instance method có thể override**, JVM sẽ chọn bản triển khai chạy theo kiểu đối tượng thực tế (`Dog`), theo quy tắc dynamic dispatch.

Vì thế cần tách hai câu hỏi:

1. **Được phép viết lời gọi nào?** Quyết định chủ yếu tại thời điểm biên dịch dựa trên **kiểu khai báo của biểu thức nhận lời gọi**.
2. **Lời gọi đó thực thi thân phương thức nào?** Với instance method được override, quyết định lúc chạy dựa trên **đối tượng thực tế**.

Một đối tượng `Dog` không mất đi các hành vi riêng chỉ vì được gán vào biến `Animal`. Tuy nhiên, compiler chỉ cho gọi các hành vi mà `Animal` công bố và có thể truy cập trong ngữ cảnh hiện tại, trừ khi dùng cơ chế thu hẹp kiểu hợp lệ.

## 2. Ví dụ hoàn chỉnh: có thể gọi gì qua biến kiểu cha?

Tạo một tệp `Main.java` sau (Java 17+):

```java
abstract class Animal {
    public void eat() {
        System.out.println("Animal eats");
    }

    public abstract void speak();

    public String description() {
        return "Animal";
    }
}

final class Dog extends Animal {
    @Override
    public void speak() {
        System.out.println("Woof");
    }

    @Override
    public String description() {
        return "Dog";
    }

    public void fetch() {
        System.out.println("Fetching");
    }
}

public class Main {
    public static void main(String[] args) {
        Animal animal = new Dog();

        animal.eat();
        animal.speak();
        System.out.println(animal.description());

        Dog dog = (Dog) animal;
        dog.fetch();
    }
}
```

Biên dịch và chạy từ thư mục chứa `Main.java`:

```bash
javac Main.java
java Main
```

Kết quả:

```text
Animal eats
Woof
Dog
Fetching
```

Phân tích từng lời gọi:

| Biểu thức | Hợp lệ khi biên dịch? | Cơ chế / kết quả |
| --- | --- | --- |
| `animal.eat()` | Có | `Animal` khai báo `eat()`; `Dog` không override nên chạy `Animal.eat()` |
| `animal.speak()` | Có | `Animal` khai báo `speak()`; JVM chạy `Dog.speak()` |
| `animal.description()` | Có | `Animal` khai báo phương thức; JVM chạy bản override `Dog.description()` |
| `animal.fetch()` | **Không** | `Animal` không khai báo/kế thừa phương thức `fetch()` |
| `((Dog) animal).fetch()` | Có | Sau phép cast hợp lệ, biểu thức có kiểu compile-time `Dog` và có thể gọi `fetch()` |

Dòng `animal.fetch()` cố ý **không xuất hiện trong chương trình chạy được**: nếu thêm dòng đó, trình biên dịch báo không tìm thấy phương thức `fetch()` trên kiểu `Animal`. Việc đối tượng thực tế là `Dog` không làm compiler bỏ qua kiểm tra kiểu khai báo.

Ở chiều ngược lại, lời gọi `animal.speak()` vẫn hợp lệ dù `Animal.speak()` là phương thức `abstract`: compiler cần biết hợp đồng tồn tại; lớp cụ thể `Dog` cung cấp thân phương thức sẽ chạy.

## 3. Kiểu khai báo quyết định tập phương thức nhìn thấy

### 3.1. Kiểu cha chỉ bộc lộ hợp đồng của kiểu cha

Giả sử:

```java
Animal animal = new Dog();
```

Qua `animal`, mã có thể gọi những instance method hợp lệ, có thể truy cập thuộc `Animal` và các superclass của nó; nếu `Animal` triển khai interface, những phương thức phù hợp từ hợp đồng interface cũng được xét theo quy tắc ngôn ngữ. Compiler **không tự suy đoán** toàn bộ API riêng của `Dog` chỉ từ đối tượng ở vế phải.

Tương tự:

```java
Object object = new Dog();
```

Lúc này kiểu khai báo là `Object`. `object.toString()` hoặc `object.getClass()` hợp lệ vì `Object` có những phương thức đó; nhưng `object.speak()` không hợp lệ vì `Object` không khai báo `speak()`.

Đối tượng thực tế vẫn là `Dog`. Gọi phương thức `toString()` qua biến `Object` vẫn có thể chạy bản `toString()` được lớp con override, nếu lớp con có override hợp lệ.

### 3.2. Với interface, compiler nhìn hợp đồng interface

Ví dụ độc lập đặt vào `Main.java`:

```java
interface Payable {
    void pay(int amount);

    default String currency() {
        return "VND";
    }
}

final class CardPayment implements Payable {
    @Override
    public void pay(int amount) {
        System.out.println("Paid " + amount);
    }

    public void verifyCard() {
        System.out.println("Card verified");
    }
}

public class Main {
    public static void main(String[] args) {
        Payable payment = new CardPayment();
        payment.pay(120);
        System.out.println(payment.currency());

        if (payment instanceof CardPayment card) {
            card.verifyCard();
        }
    }
}
```

Lệnh `javac Main.java` và `java Main` cho kết quả:

```text
Paid 120
VND
Card verified
```

- `payment.pay(120)` hợp lệ vì `Payable` khai báo phương thức `pay(int)`. Phần thân chạy là của `CardPayment`.
- `payment.currency()` hợp lệ vì `Payable` có `default` method. Nếu lớp triển khai override hợp lệ thì JVM có thể chọn bản override.
- `payment.verifyCard()` **không hợp lệ** theo kiểu khai báo `Payable`. Muốn gọi hành vi riêng phải kiểm tra và thu hẹp kiểu sang `CardPayment` như ví dụ.

Một lớp có thể implements nhiều interface, nhưng khi biến được khai báo bằng **một** interface, compiler chỉ biết những gì có thể truy cập qua kiểu interface đó (kể cả các superinterface), cộng những phương thức của `Object` được Java cho phép gọi trong ngữ cảnh tương ứng.

### 3.3. Phạm vi truy cập vẫn áp dụng

Việc phương thức tồn tại trong lớp hoặc interface chưa đủ. Compiler còn kiểm tra `public`, `protected`, package-private, `private` và ngữ cảnh truy cập. Ví dụ mã nằm ở package khác không thể gọi một phương thức package-private chỉ vì biến có kiểu của lớp chứa phương thức.

Một biến kiểu cha không thể gọi phương thức `private` của lớp cha từ bên ngoài; subclass cũng không thể override phương thức `private` của superclass vì phương thức đó không được kế thừa theo nghĩa override.

**Quy tắc thực hành:** Hãy nhìn vào **khai báo kiểu của biểu thức phía trước dấu chấm**, API của kiểu đó và quyền truy cập hiện tại trước khi kết luận một lời gọi hợp lệ.

## 4. Overriding và dynamic dispatch: lời gọi hợp lệ chạy vào đâu?

Nếu kiểu khai báo `Animal` công bố `speak()`, lời gọi `animal.speak()` hợp lệ. Với `Animal animal = new Dog();`, nếu `Dog` override `speak()`, runtime chạy `Dog.speak()`. Tuy nhiên, đối tượng runtime không làm lộ API riêng của `Dog`: `animal.fetch()` vẫn lỗi biên dịch nếu `fetch()` chỉ được khai báo trong `Dog`.

Bài **Liên kết động khi gọi phương thức instance** đi sâu vào điều kiện override, lời gọi `super`, constructor dispatch và hành vi JVM.

## 5. Overloading khác overriding: compiler chọn chữ ký theo kiểu tĩnh

Overload là các phương thức cùng tên nhưng khác danh sách tham số. Compiler chọn chữ ký dựa trên kiểu tĩnh của receiver và đối số; nếu chữ ký instance đã chọn được override, runtime mới chọn phần triển khai cho chữ ký đó.

Ví dụ các khai báo và lời gọi sau là những đoạn minh họa cần đặt trong class/method phù hợp:

```java
static void describe(Animal value) { }
static void describe(Dog value) { }
```

```java
Animal animal = new Dog();
describe(animal); // Chọn describe(Animal) theo kiểu tĩnh.
```

Các trường hợp boxing/unboxing, varargs, `null` mơ hồ và generic erasure được phân tích trong bài **Chọn overload lúc biên dịch và chọn override lúc chạy**.

## 6. Ép kiểu và `instanceof`: mở rộng API nhìn thấy một cách có kiểm soát

Nếu cần hành vi chỉ có ở subtype, hãy thu hẹp kiểu sau khi kiểm tra:

```java
Animal animal = new Dog();
if (animal instanceof Dog dog) {
    dog.fetch();
}
```

`instanceof` không thay đổi kiểu khai báo của biến; pattern matching tạo biến `dog` trong phạm vi được compiler xác định. Cast sai có thể ném `ClassCastException`. Quan hệ cast, phạm vi pattern và các lỗi cast được giải thích trong các bài **Upcast và downcast giữa lớp, lớp trừu tượng và interface**, **instanceof, pattern matching và kiểm tra trước khi ép kiểu**, và **ClassCastException và giới hạn ép kiểu không hợp lệ**.

## 7. `static` method và field không hoạt động như override

| Thành viên | Quy tắc chọn |
| --- | --- |
| Instance method có thể override | Kiểu runtime của receiver chọn implementation sau khi chữ ký được xác định. |
| Field | Kiểu tĩnh của biểu thức xác định field được truy cập. |
| `static` method | Kiểu/tên lớp xác định method; không dispatch theo object. |

Field hiding và static method hiding được trình bày đầy đủ trong bài **Vì sao truy cập field và phương thức static không đa hình**.

## 8. `var`, generic và kiểu biểu thức: đừng chỉ nhìn tên biến

### 8.1. `var` vẫn có kiểu xác định tại lúc biên dịch

`var` (biến cục bộ, từ Java 10) cho compiler tự suy ra kiểu của biểu thức khởi tạo; nó **không** biến Java thành ngôn ngữ tìm phương thức hoàn toàn ở runtime.

```java
var directDog = new Dog();         // Kiểu tĩnh suy ra: Dog
Animal typedAnimal = new Dog();    // Kiểu tĩnh: Animal
var copiedAnimal = typedAnimal;    // Kiểu tĩnh suy ra: Animal

directDog.fetch();                // Hợp lệ.
// typedAnimal.fetch();            // Lỗi biên dịch.
// copiedAnimal.fetch();           // Lỗi biên dịch.
```

Đây là đoạn minh họa cần có `Animal` và `Dog` được khai báo như trong ví dụ mục 2; không phải chương trình độc lập. Đổi tên biến, dùng `var` hay gán từ một tham chiếu khác không tự làm lộ API của subtype.

### 8.2. Generic trả về kiểu mà compiler biết

Nếu có `List<Animal>` thì `animals.get(0)` có kiểu compile-time `Animal`, dù phần tử cụ thể đang là `Dog`:

```java
java.util.List<Animal> animals = java.util.List.of(new Dog());

Animal first = animals.get(0);
first.speak();
// first.fetch(); // Lỗi biên dịch.
```

Đây cũng là đoạn minh họa dùng lại `Animal` và `Dog` ở mục 2. Muốn gọi `fetch()` phải làm rõ subtype bằng phép kiểm tra/cast phù hợp, hoặc thiết kế lại hợp đồng khi đó là chức năng phổ quát.

`List<Dog>` không tự động là subtype của `List<Animal>`: generic Java là invariant với các tham số kiểu như vậy. Ngay cả khi dùng wildcard đọc `List<? extends Animal>`, compiler nhìn phần tử tối đa theo kiểu `Animal`, không tự dựa vào dữ liệu runtime để cho gọi `Dog.fetch()`.

### 8.3. Kiểu biểu thức, không chỉ kiểu biến, mới là chìa khóa

Xét:

```java
((Dog) animal).fetch();
```

Biến `animal` vẫn khai báo là `Animal`, nhưng biểu thức `((Dog) animal)` có kiểu compile-time `Dog`. Do đó compiler cho phép `fetch()`, sau khi cast qua được kiểm tra runtime.

Tương tự, biểu thức trả về từ phương thức có kiểu theo **kiểu trả về khai báo**, không tự theo implementation thực tế. Nếu một factory khai báo `Animal makeAnimal()` rồi trả về `new Dog()`, kết quả của `makeAnimal()` có kiểu tĩnh `Animal` khi xét lời gọi ở nơi sử dụng.

## 9. Trường hợp đặc biệt: `super`, `private` và `final`

- `super.method()` trong subclass là cú pháp gọi phần triển khai của superclass theo quy tắc ngôn ngữ, cho phép bỏ qua bản override của subclass đối với lời gọi đó. Không thể dùng `super` từ mã bên ngoài subclass.
- Phương thức `final` có thể **được gọi** qua tham chiếu kiểu cha nếu hợp lệ theo phạm vi truy cập, nhưng không được override trong subclass. Vì thế runtime không thể chọn một bản override khác của phương thức final.
- Phương thức `private` của superclass không được override bởi subclass. Một phương thức trùng tên được khai báo trong subclass (khi hợp lệ) không biến lời gọi private trong superclass thành lời gọi đa hình.
- Constructor không phải phương thức được kế thừa/override theo mô hình trên. Lệnh `new Dog()` kiểm tra constructor của `Dog`; chuỗi constructor `super(...)` được xử lý riêng.

Các quy tắc này giúp phân biệt **đa hình ở instance method** với các cơ chế tên gọi/khởi tạo khác của Java.

## 10. Những lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: method fetch()` khi gọi `animal.fetch()` | Kiểu khai báo `Animal` không có phương thức `fetch()` | Dùng hành vi thuộc hợp đồng cha, hoặc kiểm tra subtype rồi gọi `Dog.fetch()` |
| Cast `(Dog) animal` biên dịch nhưng gây `ClassCastException` | Đối tượng thực tế không phải `Dog` | Dùng `instanceof` và xử lý nhánh kiểu khác |
| Overload `describe(Animal)` chạy dù đối tượng là `Dog` | Overload chọn theo kiểu compile-time của tham số | Hiểu rõ chữ ký chọn ở compile-time; dùng override nếu cần hành vi đa hình |
| `Parent p = new Child(); p.label()` gọi static của `Parent` | Static method hiding, không dynamic dispatch | Gọi static qua tên lớp; dùng instance method nếu muốn override |
| `p.name` đọc trường superclass | Field hiding được phân giải theo kiểu tĩnh | Dùng private field và getter/instance method rõ ràng |
| `var x = typedAnimal` vẫn không gọi được `fetch()` | `var` suy ra kiểu `Animal` | Kiểm tra kiểu được suy luận hoặc thay đổi khai báo theo nhu cầu thực |
| `List<Animal>.get(0).fetch()` lỗi biên dịch | `get(0)` được khai báo trả về `Animal` | Đọc theo hợp đồng hoặc thu hẹp subtype sau khi kiểm tra |
| Gọi `private`/package-private ngoài phạm vi được phép | Java kiểm tra phạm vi truy cập ở compile-time | Công khai API phù hợp hoặc thay đổi ngữ cảnh thiết kế, không dựa vào đối tượng runtime |

Thông báo compiler cụ thể có thể thay đổi tùy ngữ cảnh và phiên bản, nhưng bản chất vẫn là **kiểu biểu thức và quy tắc truy cập** quyết định lời gọi có hợp lệ hay không.

## 11. Quy trình tư duy khi đọc một lời gọi phương thức

Khi gặp biểu thức `receiver.method(argument)`:

1. **Xác định kiểu compile-time của `receiver`**: kiểu khai báo của biến, kiểu trả về khai báo của hàm, kiểu suy luận của `var`, hoặc kiểu của biểu thức cast.
2. **Liệt kê các phương thức có tên `method` mà compiler có thể xét** từ kiểu đó, theo kế thừa/interface, phạm vi truy cập và dạng lời gọi.
3. **Xem tham số và overload resolution** để xác định chữ ký hợp lệ, phù hợp nhất tại lúc biên dịch. Nếu không tìm thấy phương thức áp dụng được hoặc có lời gọi mơ hồ, biên dịch thất bại.
4. **Phân loại phương thức đã chọn**: nếu là instance method có thể override, JVM dispatch theo đối tượng thực tế; nếu là `static`, dùng phân giải compile-time; nếu là `private`/`final`, không có bản override hợp lệ của nó.
5. **Nếu cần phương thức riêng của subtype**, cân nhắc thiết kế lại API hoặc dùng `instanceof`/cast có kiểm tra; nhớ rằng cast không biến đổi đối tượng.

Quy trình này giúp tránh suy luận nhầm rằng chỉ cần đối tượng thực tế có phương thức là mọi biến tham chiếu đều gọi được phương thức đó.

## 12. Tự kiểm tra

**Câu 1.** Giả sử `Animal a = new Dog();`, phương thức `Dog.fetch()` không được khai báo trong `Animal`. Viết `a.fetch()` có hợp lệ không?

**Đáp án:** Không. Compiler kiểm tra trên kiểu `Animal`. Muốn dùng `fetch()` phải có biểu thức kiểu `Dog` thích hợp, ví dụ sau `instanceof`.

**Câu 2.** Với cùng khai báo, nếu `Dog` override `Animal.speak()` thì `a.speak()` chạy thân nào?

**Đáp án:** Compiler chấp nhận vì `Animal.speak()` tồn tại; runtime dispatch đến `Dog.speak()`.

**Câu 3.** Có hai overload `describe(Animal)` và `describe(Dog)`; `Animal a = new Dog(); describe(a);` chọn cái nào?

**Đáp án:** `describe(Animal)`, dựa trên kiểu tĩnh của `a`.

**Câu 4.** `Parent p = new Child();` với cả hai lớp cùng khai báo `static label()`. `p.label()` gọi bản nào?

**Đáp án:** Bản static trên `Parent`. Nên viết rõ `Parent.label()` để tránh hiểu lầm.

**Câu 5.** Dùng `var a = someAnimalReference;` có làm phương thức riêng của subtype trở nên gọi được không?

**Đáp án:** Không. `var` suy ra kiểu compile-time từ biểu thức khởi tạo. Nếu biểu thức có kiểu `Animal`, biến được suy ra cũng là `Animal`.

**Câu 6.** Vì sao `Payable payment = new CardPayment();` có thể gọi `payment.pay(100)` nhưng không gọi `payment.verifyCard()`?

**Đáp án:** `Payable` công bố `pay(int)`, không công bố `verifyCard()`. Đối tượng runtime triển khai hợp đồng, nhưng API thấy được qua biến vẫn phụ thuộc kiểu khai báo.

**Ghi nhớ:** **Kiểu khai báo/kiểu biểu thức quyết định phương thức nào được phép gọi và overload nào được chọn; kiểu đối tượng thực tế quyết định bản override nào của instance method chạy.** Hiểu hai thời điểm này giúp dùng interface, abstract class, inheritance và polymorphism chính xác mà không lạm dụng cast.
