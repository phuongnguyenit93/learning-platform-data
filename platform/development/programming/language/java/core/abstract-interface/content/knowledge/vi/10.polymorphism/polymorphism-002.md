# Liên kết động khi gọi phương thức instance trong Java

**Liên kết động** (*dynamic binding*, hay *dynamic method dispatch*) là cơ chế Java lựa chọn phiên bản thực thi của một **phương thức instance có thể ghi đè** dựa trên **kiểu thực tế của đối tượng nhận lời gọi ở runtime**, sau khi lời gọi đã được kiểm tra hợp lệ và xác định chữ ký ở compile time. Đây là nền tảng của **đa hình runtime**: mã dùng kiểu cha hoặc interface vẫn có thể chạy hành vi khác nhau theo từng đối tượng cụ thể.

Điều cần nắm vững là Java kết hợp **hai thời điểm quyết định**:

1. **Khi biên dịch:** xác định lời gọi hợp lệ theo kiểu biểu thức, chọn chữ ký qua các quy tắc overload, kiểm tra quyền truy cập, kiểu tham số và kiểu trả về.
2. **Khi chạy:** với lời gọi instance được dispatch động, chọn implementation ghi đè phù hợp với **class thực tế** của đối tượng nhận.

Vì thế, kiểu tham chiếu quyết định **có thể gọi phương thức nào**, còn kiểu đối tượng runtime quyết định **thân của phương thức được override nào được chạy**.

## 1. Ví dụ mở đầu: một kiểu tham chiếu, nhiều hành vi

Lưu ví dụ độc lập trong file `DynamicDispatchDemo.java`:

```java
abstract class Animal {
    abstract String sound();

    String describe() {
        return "Animal says: " + sound();
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}

public class DynamicDispatchDemo {
    public static void main(String[] args) {
        Animal first = new Dog();
        Animal second = new Cat();

        System.out.println(first.sound());
        System.out.println(second.sound());
        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac DynamicDispatchDemo.java
java DynamicDispatchDemo
```

Đầu ra chính xác:

```text
woof
meow
Animal says: woof
Animal says: meow
```

**Giải thích từng bước:**

- `first` và `second` có cùng **kiểu khai báo** `Animal`; compiler thấy `Animal` có `sound()` và `describe()` nên chấp nhận lời gọi.
- `new Dog()` tạo một đối tượng có class runtime là `Dog`; `first.sound()` thực thi `Dog.sound()`.
- `new Cat()` tạo một đối tượng có class runtime là `Cat`; `second.sound()` thực thi `Cat.sound()`.
- `describe()` chỉ được định nghĩa trong `Animal`, nên cả hai lời gọi `describe()` đều dùng thân `Animal.describe()`. Tuy nhiên, khi thân này gọi `sound()` (tương đương `this.sound()`), lời gọi đó **vẫn được dispatch động**. Kết quả phụ thuộc vào đối tượng `Dog` hoặc `Cat`, ngay cả khi mã `describe()` nằm ở superclass.

Đây chính là điểm mạnh của đa hình: phương thức ở lớp cha có thể gọi một “điểm mở rộng” trong lớp con mà không phải dùng `if (object instanceof Dog)` hay `switch` theo từng loại đối tượng.

## 2. Compiler làm gì, JVM làm gì?

Xét biểu thức:

```java
Animal animal = new Dog();
String text = animal.sound();
```

Về mặt ngữ nghĩa:

| Giai đoạn | Dữ kiện được dùng | Quyết định |
| --- | --- | --- |
| **Compile time** | Kiểu biểu thức `animal` là `Animal`; phương thức có thể truy cập; kiểu và số lượng đối số | `sound()` là một lời gọi hợp lệ; kiểu kết quả là `String`. |
| **Runtime** | Giá trị thực của `animal` đang trỏ đến đối tượng `Dog` | Với lời gọi virtual, implementation được chọn là `Dog.sound()`. |

Không thể diễn giải rằng compiler luôn chốt `Animal.sound()` làm thân chạy cuối cùng: nếu như vậy Java không có đa hình ghi đè (*runtime polymorphism*).

Các bước trực giác để hiểu dispatch động:

```text
Biểu thức tham chiếu x.method(arguments)
                 │
                 ▼
Compiler kiểm tra kiểu, overload, quyền truy cập
                 │
                 ▼
Khi chạy: đánh giá receiver và arguments
                 │
                 ▼
Receiver là null? ── có ──► NullPointerException
                 │ không
                 ▼
Tra implementation instance phù hợp với class runtime
                 │
                 ▼
Thực thi implementation được chọn
```

Sơ đồ là mô hình **ngữ nghĩa** dành cho lập trình viên, không mô tả cứng thuật toán nội bộ của mọi JVM. JVM có thể tối ưu bằng devirtualization, inlining, caching và biên dịch JIT, nhưng hành vi quan sát được vẫn phải đúng theo ngữ nghĩa Java.

**Lưu ý về thời điểm đánh giá:** với một biểu thức gọi method, Java thực hiện các bước đánh giá receiver/đối số theo quy tắc của ngôn ngữ; ví dụ lệnh gọi qua receiver `null` vẫn có thể đánh giá biểu thức đối số trước khi ném `NullPointerException`. Sơ đồ trên chỉ tóm lược kiểm tra runtime, không thay thế đặc tả về thứ tự đánh giá.

## 3. Overriding tạo khả năng dispatch động

**Override** xảy ra khi subclass cung cấp một instance method hợp lệ thay thế instance method được kế thừa hoặc thực hiện hợp đồng của interface. Với một lời gọi virtual, runtime chọn phương thức override cuối cùng phù hợp với đối tượng.

```java
class Vehicle {
    String move() {
        return "moving";
    }
}

class Bicycle extends Vehicle {
    @Override
    String move() {
        return "pedaling";
    }
}

class ElectricBicycle extends Bicycle {
    @Override
    String move() {
        return "assisted pedaling";
    }
}
```

Với:

```java
Vehicle a = new Vehicle();
Vehicle b = new Bicycle();
Vehicle c = new ElectricBicycle();
```

Ba biểu thức `a.move()`, `b.move()`, `c.move()` lần lượt trả `"moving"`, `"pedaling"`, `"assisted pedaling"`. Các lời gọi đều hợp lệ qua `Vehicle`, nhưng implementation chạy lần lượt nằm trong `Vehicle`, `Bicycle` và `ElectricBicycle`.

Các điều kiện override cần nhớ:

- Method phải có chữ ký phù hợp; không thể “override” bằng cách đổi danh sách tham số rồi giữ tên cũ.
- Quyền truy cập của method override không được hẹp hơn method gốc. Ví dụ method gốc `public` thì bản override cũng phải `public`.
- Kiểu trả về phải phù hợp (có thể dùng **covariant return type** với các kiểu tham chiếu hợp lệ).
- Quy tắc về checked exceptions phải được tôn trọng; bản override không được mở rộng tập checked exceptions trái hợp đồng.
- Method `final` không thể bị override.
- `@Override` không tạo dispatch động, nhưng yêu cầu compiler kiểm tra đúng quan hệ override và giúp bắt lỗi đánh máy/chữ ký.

Việc subclass **không override** cũng hoàn toàn hợp lệ nếu đã có method concrete được kế thừa: JVM sẽ chọn implementation kế thừa gần nhất phù hợp.

## 4. Đa hình qua interface: gọi đúng implementation

Không cần quan hệ “lớp con của một superclass” mới có dispatch động. Đối tượng có thể implement cùng interface với nhiều class không có chung superclass cụ thể ngoài `Object`.

Tạo file `NotificationDemo.java`:

```java
interface Notifier {
    void notifyUser(String message);
}

class EmailNotifier implements Notifier {
    @Override
    public void notifyUser(String message) {
        System.out.println("EMAIL: " + message);
    }
}

class SmsNotifier implements Notifier {
    @Override
    public void notifyUser(String message) {
        System.out.println("SMS: " + message);
    }
}

class NotificationService {
    void dispatch(Notifier notifier, String message) {
        notifier.notifyUser(message);
    }
}

public class NotificationDemo {
    public static void main(String[] args) {
        NotificationService service = new NotificationService();

        service.dispatch(new EmailNotifier(), "Hello");
        service.dispatch(new SmsNotifier(), "Hello");
    }
}
```

Chạy:

```bash
javac NotificationDemo.java
java NotificationDemo
```

Kết quả:

```text
EMAIL: Hello
SMS: Hello
```

`NotificationService` chỉ biết hợp đồng `Notifier`; lời gọi `notifier.notifyUser(message)` chuyển đến implementation dựa trên class runtime (`EmailNotifier` hoặc `SmsNotifier`). Đây là lý do ứng dụng có thể dùng dependency injection, test double, mock hoặc plugin mà mã sử dụng interface không phải viết lại mỗi khi có class thực thi mới.

Các phương thức `default` của interface cũng có quy tắc chọn implementation và override tương ứng. Một class có thể override method `default`; nếu class không override, method default hợp lệ được thừa hưởng sẽ chạy. Nếu có nhiều default method xung đột không giải quyết được, **compiler sẽ báo lỗi**, không để JVM chọn ngẫu nhiên lúc chạy.

## 5. Overloading là quyết định khác với dynamic dispatch

**Overloading**: các method cùng tên nhưng **khác danh sách tham số**. Compiler chọn method áp dụng phù hợp dựa trên **kiểu của biểu thức đối số ở compile time**. Sau khi chọn chữ ký, nếu implementation của chữ ký đó là virtual thì runtime mới chọn phiên bản override tương ứng.

Tạo file `OverloadVsOverrideDemo.java`:

```java
class Creature { }

class Puppy extends Creature { }

class Presenter {
    String show(Creature value) {
        return "Presenter: Creature";
    }

    String show(Puppy value) {
        return "Presenter: Puppy";
    }
}

class SpecialPresenter extends Presenter {
    @Override
    String show(Creature value) {
        return "Special: Creature";
    }

    @Override
    String show(Puppy value) {
        return "Special: Puppy";
    }
}

public class OverloadVsOverrideDemo {
    public static void main(String[] args) {
        Creature creature = new Puppy();
        Puppy puppy = new Puppy();
        Presenter presenter = new SpecialPresenter();

        System.out.println(presenter.show(creature));
        System.out.println(presenter.show(puppy));
        System.out.println(presenter.show((Creature) puppy));
    }
}
```

Chạy:

```bash
javac OverloadVsOverrideDemo.java
java OverloadVsOverrideDemo
```

Kết quả chính xác:

```text
Special: Creature
Special: Puppy
Special: Creature
```

Phân tích:

1. `creature` có kiểu **biên dịch** `Creature` dù đang trỏ đến `new Puppy()`. Compiler chọn overload `show(Creature)`; runtime chọn bản override `SpecialPresenter.show(Creature)`.
2. `puppy` có kiểu biên dịch `Puppy`. Compiler chọn overload `show(Puppy)`; runtime chọn `SpecialPresenter.show(Puppy)`.
3. Ép kiểu `(Creature) puppy` khiến compiler xét biểu thức đối số theo kiểu `Creature`, do đó chọn overload `show(Creature)`. Cast không biến đối tượng `Puppy` thành một đối tượng `Creature` mới.

**Quy tắc nhớ:** *Overload chọn chữ ký theo kiểu tại compile time; override chọn thân thực thi theo class runtime*. Java không “chọn overload lại” chỉ vì đối tượng của đối số thực tế thuộc subclass.

## 6. Các trường hợp không dispatch động theo nghĩa override thông thường

Không phải bất kỳ thứ gì gọi bằng cú pháp dấu chấm `.` đều được chọn implementation theo kiểu runtime.

| Trường hợp | Có override/dispatch động như instance method thông thường? | Điểm cần nhớ |
| --- | --- | --- |
| Instance method không `static`, không `private`, có thể override | **Có**, khi có bản override thích hợp | Quyết định implementation dựa trên class runtime của receiver. |
| `static` method | **Không**; method có thể bị *hide* | Chọn theo kiểu/định danh được phân giải lúc biên dịch. |
| `private` method | **Không bị override** | Method chỉ thuộc khai báo cho phép truy cập; method trùng tên ở subclass là một method riêng. |
| `final` instance method | **Không thể override** | Không có bản override khác để runtime lựa chọn, dù cú pháp vẫn có thể là instance call. |
| `super.method()` | **Không** dispatch đến override của class hiện tại theo receiver runtime | Truy cập implementation của superclass theo quy tắc `super`. |
| Constructor (`new`, `super(...)`, `this(...)`) | **Không** được override | Constructor thiết lập đối tượng; vẫn có thể **gọi virtual method trong constructor**, xem mục 8. |
| Field có cùng tên ở superclass/subclass | **Không**; field bị *hide*, không override | Field được chọn theo kiểu biểu thức/khai báo. |
| Overloaded method khác chữ ký | Overload chọn **chữ ký tĩnh**; implementation có thể **động** | Hai quá trình diễn ra ở hai giai đoạn khác nhau. |

### 6.1. Field hiding và static hiding thuộc bài học riêng

Truy cập `ref.field` dựa vào kiểu tĩnh của biểu thức; lời gọi `ref.staticMethod()` cũng được phân giải theo kiểu/tên lớp, không theo class runtime. Hai cơ chế này là **field hiding** và **method hiding**, khác với override của instance method. Bảng trên đủ để phân biệt trong bài liên kết động; ví dụ chi tiết và các quy tắc riêng của interface nằm trong bài **Vì sao truy cập field và phương thức static không đa hình**.

### 6.2. Gọi `super` và gọi `this`

File `SuperCallDemo.java`:

```java
class Base {
    String greet() {
        return "base";
    }
}

class Extended extends Base {
    @Override
    String greet() {
        return "extended";
    }

    String compare() {
        return super.greet() + " / " + this.greet();
    }
}

public class SuperCallDemo {
    public static void main(String[] args) {
        Base x = new Extended();
        System.out.println(x.greet());
        System.out.println(((Extended) x).compare());
    }
}
```

Chạy:

```bash
javac SuperCallDemo.java
java SuperCallDemo
```

Kết quả:

```text
extended
base / extended
```

`super.greet()` được liên kết theo superclass, giúp subclass tận dụng hành vi gốc. Trong khi đó, `this.greet()` là lời gọi virtual trên đối tượng hiện tại. Nếu class con của `Extended` override `greet()` lần nữa, `this.greet()` vẫn có thể chuyển đến phiên bản mới đó.

## 7. Đổi kiểu tham chiếu không đổi class runtime của object

`Animal a = new Dog(); Animal b = (Animal) a;` tạo hai tham chiếu tới cùng đối tượng `Dog`. Cả `a.sound()` và `b.sound()` vẫn dispatch đến `Dog.sound()`. Upcast/cast chỉ đổi kiểu nhìn thấy ở compile time, không đổi class runtime; các quan hệ cast và cách kiểm tra subtype được trình bày trong bài **Upcast và downcast giữa lớp, lớp trừu tượng và interface**.

## 8. Bẫy quan trọng: gọi overridable method từ constructor

Java vẫn dùng virtual dispatch trong lúc chạy constructor. Khi constructor của superclass gọi một method có thể override, nó có thể chạy method của subclass **trước khi phần khởi tạo subclass hoàn tất**. Điều này dễ dẫn đến `null` hoặc trạng thái chưa sẵn sàng.

File `ConstructorDispatchDemo.java`:

```java
class Parent {
    Parent() {
        System.out.println("Parent sees: " + value());
    }

    String value() {
        return "parent";
    }
}

class Child extends Parent {
    private String name = "ready";

    @Override
    String value() {
        return name;
    }
}

public class ConstructorDispatchDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

Chạy:

```bash
javac ConstructorDispatchDemo.java
java ConstructorDispatchDemo
```

Kết quả:

```text
Parent sees: null
```

**Tại sao là `null`?** Đối tượng mới ngay từ đầu có class runtime là `Child`. Khi `Parent()` đang chạy, `value()` được dispatch đến `Child.value()`; tại thời điểm đó field `Child.name` mới có giá trị mặc định `null`, vì initializer `= "ready"` của subclass chưa được thực thi. Sau khi superclass hoàn tất mới đến phần khởi tạo của subclass.

**Thực hành:** tránh gọi method có thể override trong constructor, field initializer hoặc logic khởi tạo có yêu cầu trạng thái subclass đã sẵn sàng. Thay vào đó, khởi tạo bằng constructor/private/final helper phù hợp, hoặc gọi phần hành vi đa hình sau khi object được tạo hoàn chỉnh.

## 9. Dispatch động và `null`

Lời gọi instance method cần receiver khác `null`; nếu receiver là `null`, runtime ném `NullPointerException` và không chạy thân phương thức. `instanceof` với `null` trả `false`, còn phương thức `static` không cần receiver instance. Bài **Đối tượng null và lời gọi qua tham chiếu interface** giải thích hợp đồng null, default method, method reference và thứ tự đánh giá đối số.

## 10. JVM thực hiện lời gọi thế nào?

Ở mức bytecode, Java có nhiều lệnh gọi phục vụ những kiểu liên kết khác nhau:

| Lệnh bytecode | Nhóm tình huống điển hình | Quan hệ với dispatch |
| --- | --- | --- |
| `invokevirtual` | Gọi instance method trên class trong phần lớn trường hợp virtual | Chọn implementation phù hợp theo kiểu runtime, có xét các quy tắc chọn/phân giải liên quan. |
| `invokeinterface` | Gọi instance method thông qua interface | Chọn implementation của đối tượng runtime thỏa hợp đồng interface. |
| `invokespecial` | Gọi constructor, `private` method và các lời gọi `super` thích hợp | Có ngữ nghĩa đặc biệt, không dispatch virtual theo cách thông thường. |
| `invokestatic` | Gọi static method | Không có receiver instance để chọn override. |
| `invokedynamic` | Cơ chế call site có bootstrap, ví dụ trong một số triển khai lambda/string concatenation | Là một cơ chế liên kết khác; **không đồng nghĩa** với “dynamic method dispatch” của `animal.sound()`. |

Có thể tự quan sát bytecode do `javac` tạo ra. Với file `DynamicDispatchDemo.java` ở mục 1:

```bash
javac DynamicDispatchDemo.java
javap -c DynamicDispatchDemo
```

Trong output `javap`, tìm các lời gọi `Animal.sound` / `Animal.describe` và opcode tương ứng. Số thứ tự dòng bytecode, constant-pool index và chi tiết tối ưu có thể khác theo compiler/JDK, nên không gán một bản `javap` duy nhất làm output cố định. Lời gọi `notifyUser` qua biến interface trong ví dụ ở mục 4 là trường hợp tiêu biểu dùng `invokeinterface`.

Một cách hình dung phổ biến về triển khai JVM là tìm method qua bảng thông tin kiểu (vtable/itable) hoặc thông tin tương đương. **Đây là chi tiết triển khai, không phải cam kết rằng mọi JVM bắt buộc dùng cấu trúc bảng cụ thể.**

JIT có thể nhận thấy tại một call site chỉ xuất hiện một kiểu receiver rồi inline thẳng implementation đó, kèm điều kiện bảo vệ hoặc cơ chế vô hiệu hóa tối ưu khi giả định thay đổi. Điều này giúp giải thích vì sao **đa hình không đồng nghĩa mỗi lời gọi chắc chắn phải tra bảng chậm**. Nên đo hiệu năng bằng profiler/benchmark đáng tin thay vì tự tối ưu khỏi interface hoặc override khi chưa có số liệu.

## 11. Quy tắc đặc biệt và các hiểu nhầm nâng cao

### 11.1. `private` và `final` khác nhau

- Method `private` không được kế thừa để override. Method cùng tên/chữ ký trong subclass thường là một khai báo khác.
- Method `final` là method có thể có tính kế thừa bình thường nhưng **không thể bị override**, giúp bảo vệ hành vi ổn định.
- Một lời gọi instance `final` vẫn thao tác trên receiver; thiếu receiver hợp lệ vẫn có thể gây `NullPointerException`. Không đồng nhất “không override” với “static”.

### 11.2. Method của superclass gọi method override của subclass

Ví dụ `Animal.describe()` gọi `sound()` ở mục 1 chứng minh rằng **nguồn mã của method gọi đang nằm ở class nào không quyết định implementation của virtual call**. Receiver `this` vẫn là đối tượng thực tế. Nếu subclass muốn dùng logic cha, nó có thể gọi `super.sound()` khi method cha concrete và được phép truy cập.

### 11.3. Covariant return type và bridge method

Khi subclass override method với kiểu trả về tham chiếu chuyên biệt hơn (ví dụ method cha trả `Animal`, method con trả `Dog`), compiler có thể phát sinh **bridge method** để bảo toàn các quy tắc dispatch và binary compatibility trong một số tình huống, đặc biệt với generics/erasure. Bridge method là chi tiết trình biên dịch nhằm giữ ngữ nghĩa override nhất quán; bạn vẫn gọi method theo contract, không cần tự viết bridge.

### 11.4. Truy cập package-private ảnh hưởng đến override

Một method package-private ở superclass **không được kế thừa như method có thể override** bởi subclass nằm ở package khác. Method cùng tên/chữ ký trong subclass package khác không đương nhiên là override của method đó. Dùng `@Override` để compiler chỉ rõ khi quan hệ override thực sự hợp lệ.

### 11.5. `Object` và interface

Mọi class thông thường đều kế thừa từ `Object`. Những method instance có thể override như `toString()`, `equals(Object)`, `hashCode()` vẫn tuân theo dispatch động. Do đó `Object value = "hello"; System.out.println(value.toString());` sẽ chạy phiên bản thích hợp cho `String`, không nhất thiết implementation gốc của `Object`.

Một interface có thể được dùng làm kiểu tham chiếu cho class implementation. Các method `public` của `Object` cũng có vai trò trong khả năng gọi trên biểu thức kiểu interface theo quy tắc đặc tả Java; nhưng không nên coi mọi member mới của implementation đều tự có trên kiểu interface.

## 12. Thiết kế với dispatch động

Một mô hình đơn giản:

```text
                       Shape
                         │ area()
               ┌─────────┴─────────┐
               │                   │
             Circle             Rectangle
             area()               area()
               ▲                   ▲
               └──── Shape ref ────┘
                      s.area()
       Tùy object runtime, chọn override phù hợp
```

Một hàm nhận `Shape` không cần biết có bao nhiêu loại hình, miễn mỗi loại cung cấp `area()`. Bạn có thể bổ sung implementation mới mà không viết lại logic gọi trên `Shape`.

Các điểm hữu ích khi dùng:

1. **Thiết kế interface/abstract class quanh hành vi ổn định**, để client phụ thuộc contract thay cho class cụ thể.
2. **Giữ logic thay đổi trong implementation**; sử dụng một lời gọi virtual thay vì tập hợp `if/else` kiểm tra từng loại object khi thực sự có hành vi đa hình.
3. **Tránh gọi overridable method khi object chưa hoàn tất khởi tạo**, đặc biệt trong superclass constructor.
4. **Không lạm dụng override** để làm hành vi khó dự đoán: phương thức override phải tôn trọng các điều kiện và bất biến của contract; không bất ngờ thu hẹp hành vi được hứa.
5. **Ưu tiên đọc được và kiểm thử được**. Một interface có nhiều implementation đủ rõ ràng giúp thay thế dependency và lập unit test; bổ sung interface chỉ vì “sợ” concrete class đôi khi làm cấu trúc phức tạp hơn mà không có lợi ích.

## 13. Lỗi thường gặp và cách nhận diện

| Nhầm lẫn | Giải thích chính xác |
| --- | --- |
| “Kiểu biến là `Parent` nên luôn gọi `Parent.method()`” | Với virtual method bị override, runtime chọn implementation của đối tượng thật, ví dụ `Child.method()`. |
| “Java chọn overload theo class runtime của đối số” | Compiler chọn overload theo kiểu biểu thức/chữ ký tại compile time; rồi có thể dispatch động implementation của chữ ký đó. |
| “`static` method cũng override như instance method” | `static` method bị hide, không override; gọi bằng tên class cho rõ ràng. |
| “Field ở subclass được truy cập động qua biến superclass” | Field bị hide; truy cập field theo kiểu tham chiếu/khai báo, không theo override. |
| “`super.method()` vẫn gọi override cuối cùng ở subclass” | `super` yêu cầu lời gọi đặc biệt vào đường superclass phù hợp. |
| “Thêm `@Override` mới kích hoạt đa hình” | `@Override` là kiểm tra biên dịch, không phải công tắc runtime. |
| “Đối tượng bị đổi thành superclass khi upcast” | Upcast chỉ đổi kiểu nhìn thấy ở compile time; class runtime của object giữ nguyên. |
| “Method override không thể chạy khi superclass constructor chưa kết thúc” | Virtual call trong constructor có thể dispatch đến subclass, gây truy cập trạng thái chưa khởi tạo. |
| “Mọi instance method đều override được” | `private` và `final` có quy tắc khác; constructor và static method không override. |
| “Dispatch động luôn chậm vì phải tra bảng” | JVM có nhiều tối ưu JIT; chỉ đánh giá chi phí trên benchmark/profiler thực tế. |

## 14. Tự kiểm tra

**Câu 1.** Cho `Parent p = new Child();` và `Child` đã override `public void run()` của `Parent`. `p.run()` gọi thân nào?

**Đáp án:** `Child.run()`, vì kiểu runtime của object là `Child`; compiler chỉ cần xác minh `run()` có thể gọi qua `Parent`.

**Câu 2.** `Parent` có `static String kind()`; `Child` có static method cùng chữ ký. Với `Parent p = new Child(); p.kind()`, method của lớp nào được gọi?

**Đáp án:** `Parent.kind()`; static method không được dispatch theo object runtime. Nên viết `Parent.kind()` trực tiếp.

**Câu 3.** Có hai overload `send(Parent)`, `send(Child)`. Biến đối số khai báo `Parent x = new Child();`. Nếu gọi `send(x)`, compiler chọn chữ ký nào?

**Đáp án:** `send(Parent)` nếu không có overload khác phù hợp hơn với kiểu tĩnh `Parent`. Sau đó, nếu bản `send(Parent)` là instance method bị override trên receiver, runtime vẫn có thể chọn implementation override.

**Câu 4.** Phương thức `Parent.execute()` gọi `this.validate()`. Nếu `Child` override `validate()`, receiver thực tế là `Child`, method `validate()` nào được gọi?

**Đáp án:** Bản `Child.validate()` (nếu đó là virtual method được override hợp lệ). Vị trí mã nguồn của `execute()` ở `Parent` không khóa dispatch vào `Parent.validate()`.

**Câu 5.** Vì sao `new Child()` có thể khiến method override của `Child` chạy khi constructor `Parent()` đang thực thi?

**Đáp án:** Đối tượng được tạo có class runtime là `Child` ngay từ đầu; lời gọi instance virtual từ `Parent()` dùng class runtime để chọn override, ngay cả khi field initializer và constructor của `Child` chưa thực hiện xong.

**Kết luận kiến thức:** Liên kết động trong Java là sự lựa chọn **implementation của instance method có thể override theo receiver runtime**. Việc xác định lời gọi hợp lệ và overload diễn ra trước ở compile time. Phân biệt rõ hai bước này, đồng thời nhận biết ngoại lệ `static`, `private`, `final`, `super`, constructor và field, sẽ giúp dự đoán chính xác hành vi đa hình trong code thực tế.