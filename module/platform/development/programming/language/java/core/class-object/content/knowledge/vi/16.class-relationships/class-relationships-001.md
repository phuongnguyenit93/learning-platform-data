# Đối tượng chứa tham chiếu tới đối tượng khác trong Java

## Mục tiêu học tập

Kết thúc bài này, bạn có thể:

- Hiểu một object có thể **giữ tham chiếu đến object khác** qua instance field, từ đó biểu diễn quan hệ giữa các lớp (thường gọi là *has-a*, association).
- Phân biệt **kiểu tham chiếu**, **biến tham chiếu**, **đối tượng thật trên bộ nhớ** và **`null`**; không nhầm việc khai báo field với việc tự động tạo object.
- Tạo mô hình `Customer` chứa `Address`, `Order` chứa `OrderLine`, `Car` dùng `Engine` và gọi phương thức qua chuỗi tham chiếu.
- Nhận diện nhiều biến/fields cùng trỏ đến **một object** (*aliasing*), sự khác biệt giữa thay object được tham chiếu và thay trạng thái của object đó.
- Phân biệt *association*, *aggregation* và *composition* như các **khái niệm thiết kế/ownership**, không phải các từ khóa Java có cơ chế tự động quản lý vòng đời.
- Áp dụng constructor injection, kiểm tra non-null, đóng gói, immutable values, defensive copying và collections cho quan hệ một–một, một–nhiều.
- Giải thích ý nghĩa của `final` trên reference field, shallow copy/deep copy, sự khác nhau giữa `==` và `equals`, cách Java truyền tham số kiểu tham chiếu **theo giá trị**.
- Hiểu bidirectional references, chu kỳ tham chiếu, reachability/garbage collection, nguy cơ `NullPointerException`, recursive `toString()` và concurrency.
- Biên dịch/chạy các chương trình Java 17+ độc lập, đọc stdout chính xác và thiết kế API biểu diễn quan hệ hợp lý.

## 1. Ý tưởng cốt lõi: object có thể biết và sử dụng object khác

Một chương trình hướng đối tượng thường gồm **nhiều object cộng tác**. Ví dụ:

- Một `Customer` có một `Address`.
- Một `Order` chứa danh sách các `OrderLine`.
- Một `Library` biết những `Book` đang được quản lý.
- Một `Car` dùng `Engine` để thực hiện hành vi vận hành.
- Một `Student` tham chiếu tới `School` mà nhiều students có thể dùng chung.

Trong Java, cách biểu diễn phổ biến là khai báo **field có kiểu là một class/interface/record khác**:

~~~java
class Address {
    String city;
}

class Customer {
    Address address;
}
~~~

Hai khai báo trên chỉ mô tả **kiểu dữ liệu**. Chúng không tự tạo một `Address` mỗi khi tạo `Customer`.

Cụ thể:

~~~java
Customer customer = new Customer();
// customer.address hiện có giá trị mặc định null.
customer.address = new Address();
customer.address.city = "Ha Noi";
~~~

Đây là đoạn **minh họa** đặt trong method thích hợp, trong cùng vùng có quyền truy cập fields. `new Customer()` tạo object Customer, rồi `new Address()` tạo **một object riêng**; field `address` chỉ giữ **tham chiếu** tới object Address ấy.

Điều quan trọng: **đối tượng chứa tham chiếu không nhất thiết sở hữu độc quyền đối tượng được tham chiếu**, và việc thay reference không tự sao chép hoặc hủy object cũ.

### 1.1. Mô hình trực quan

~~~text
customer (biến tham chiếu)
   |
   v
Customer object
   address -----+
                |
                v
            Address object
              city = "Ha Noi"
~~~

Có hai objects riêng có identity riêng. `Customer.address` là một **reference field**, không phải một `Address` “nhúng nguyên object” theo cách ngôn ngữ bắt buộc.

Java che giấu chi tiết địa chỉ bộ nhớ vật lý và không cung cấp pointer arithmetic tùy ý cho Java references. Sơ đồ mũi tên giúp tư duy quan hệ, **không phải cam kết layout bộ nhớ cụ thể của JVM**.

## 2. Biến tham chiếu, object và `null`

Hãy phân biệt:

| Thực thể | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Kiểu tham chiếu** | `Address` | Tên kiểu dùng để khai báo biến và kiểm tra phép gán |
| **Biến tham chiếu local** | `Address a` | Biến có thể giữ reference hoặc `null`; local phải được definitely assigned trước khi đọc |
| **Reference field** | `private Address address;` | Thành viên của object khác, mặc định `null` nếu chưa được gán |
| **Object** | `new Address()` | Instance được tạo theo quy tắc Java |
| **Phép gán reference** | `customer.address = a;` | Sao chép **giá trị tham chiếu**, không clone Address |
| **`null`** | `address = null;` | Không tham chiếu tới object nào |
| **Method call qua reference** | `address.getCity()` | Thao tác trên object được trỏ đến, nếu reference hợp lệ |

Đoạn:

~~~java
Address first = new Address();
Address second = first;
~~~

tạo **một Address object**, nhưng hai biến `first` và `second` cùng tham chiếu object đó. Nó **không gọi constructor lần thứ hai**.

Trong khi:

~~~java
Address first = new Address();
Address second = new Address();
~~~

tạo **hai instances Address riêng biệt** ngay cả khi fields bên trong có giá trị giống nhau.

### 2.1. `new` cho object nào?

Nếu:

~~~java
class Invoice {
    Customer customer;
}
~~~

thì `new Invoice()` **không tự động** gọi `new Customer()`. Field `customer` nhận default `null` trừ khi field initializer/constructor hoặc một logic khác gán reference hợp lệ.

Muốn bắt buộc invoice có customer, nên yêu cầu tham số trong constructor và kiểm tra rõ ràng; phần sau sẽ làm.

## 3. Chương trình đầu tiên: một customer chứa address

Lưu file **`CustomerAddressDemo.java`**:

~~~java
public class CustomerAddressDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }

        void changeCity(String newCity) {
            city = newCity;
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        void print() {
            System.out.println(name + " lives in " + address.city());
        }
    }

    public static void main(String[] args) {
        Address address = new Address("Ha Noi");
        Customer customer = new Customer("Lan", address);

        customer.print();

        address.changeCity("Hue");
        customer.print();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CustomerAddressDemo.java
java CustomerAddressDemo
~~~

Stdout:

~~~text
Lan lives in Ha Noi
Lan lives in Hue
~~~

**Phân tích từng bước:**

1. `new Address("Ha Noi")` tạo Address object.
2. `new Customer("Lan", address)` tạo Customer object, rồi gán reference từ parameter `address` vào field `Customer.address`.
3. `customer.print()` đọc thông tin qua chuỗi gọi `address.city()`.
4. `address.changeCity("Hue")` sửa **cùng Address object** bên ngoài Customer.
5. Khi Customer đọc lại `address.city()`, nó thấy `Hue` do hai references trỏ cùng object.

Đây là ví dụ về **aliasing**. Modifier `final` trên field `Customer.address` **không** làm Address object bất biến; nó chỉ ngăn field reference của Customer được gán lại sau khởi tạo đúng quy tắc.

### 3.1. Constructor ở ví dụ chưa đủ validation

Ví dụ đầu chủ ý ngắn để bộc lộ reference sharing. Nếu caller viết `new Customer("Lan", null)`, constructor nhận `null`, và khi gọi `print()` sẽ có nguy cơ `NullPointerException`.

Trong ứng dụng cần invariant “mỗi Customer luôn có Address”, hãy dùng:

~~~java
Customer(String name, Address address) {
    this.name = java.util.Objects.requireNonNull(name, "name");
    this.address = java.util.Objects.requireNonNull(address, "address");
}
~~~

Ngoài ra cần kiểm tra `name.isBlank()` hoặc fields của Address theo quy tắc nghiệp vụ. Kiểm tra non-null chỉ ngăn reference rỗng, **không tự bảo đảm** object được tham chiếu có trạng thái hợp lệ hay bất biến.

## 4. “Has-a” là quan hệ, không đồng nghĩa kế thừa

So sánh hai câu:

- **Car has an Engine** → thường biểu diễn bằng field `Engine engine`.
- **ElectricCar is a Car** → có thể biểu diễn bằng `extends Car` nếu đúng quan hệ kiểu.

~~~java
class Engine {
    void start() {
        System.out.println("Engine started");
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void start() {
        engine.start();
    }
}
~~~

Đây là **khai báo minh họa** hợp lệ trong một source file/package phù hợp. `Car` không kế thừa Engine; nó **ủy quyền hành vi** tới Engine mà nó giữ reference.

Một class vừa có thể kế thừa một superclass, vừa chứa references tới objects khác. Nhưng đừng dùng `extends` chỉ vì “A dùng B”. Kế thừa mô tả quan hệ kiểu (*is-a*) và tạo điều kiện polymorphism; field reference mô tả quan hệ object (*has-a/uses-a*).

### 4.1. Chọn composition khi muốn thay thành phần

Ví dụ:

~~~java
interface Engine {
    void start();
}

class ElectricEngine implements Engine {
    public void start() {
        System.out.println("Electric engine started");
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void start() {
        engine.start();
    }
}
~~~

Đây là mô hình minh họa nhiều class, không có `main`. `Car` phụ thuộc vào **interface `Engine`**. Nó có thể dùng một implementation khác mà không cần kế thừa lớp engine cụ thể.

Bản thân `interface` không tạo object; ở runtime, field `engine` tham chiếu một object của class triển khai interface đó.

## 5. Chương trình ủy quyền qua interface reference

Lưu **`CompositionStrategyDemo.java`**:

~~~java
public class CompositionStrategyDemo {
    interface Notifier {
        void send(String message);
    }

    static final class ConsoleNotifier implements Notifier {
        public void send(String message) {
            System.out.println("console: " + message);
        }
    }

    static final class PrefixNotifier implements Notifier {
        private final String prefix;

        PrefixNotifier(String prefix) {
            this.prefix = prefix;
        }

        public void send(String message) {
            System.out.println(prefix + message);
        }
    }

    static final class OrderService {
        private final Notifier notifier;

        OrderService(Notifier notifier) {
            this.notifier = java.util.Objects.requireNonNull(
                    notifier, "notifier");
        }

        void complete(String orderId) {
            notifier.send("completed " + orderId);
        }
    }

    public static void main(String[] args) {
        OrderService first = new OrderService(
                new ConsoleNotifier());
        OrderService second = new OrderService(
                new PrefixNotifier("event: "));

        first.complete("A-1");
        second.complete("B-2");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CompositionStrategyDemo.java
java CompositionStrategyDemo
~~~

Output:

~~~text
console: completed A-1
event: completed B-2
~~~

**Vì sao ví dụ này hữu ích?**

- `OrderService` **giữ một reference kiểu interface**.
- Constructor injection đưa dependency vào từ ngoài thay vì hard-code `new ConsoleNotifier()` trong `complete`.
- Khi gọi `notifier.send(...)`, dynamic dispatch chạy implementation tương ứng với object đang được tham chiếu.
- `private final Notifier notifier` cố định reference sau constructor, nhưng implementation cụ thể có thể có state mutable riêng.
- `Objects.requireNonNull` bảo vệ invariant reference tồn tại.

Đây là **composition bằng cộng tác object**. Nó khác `extends`, đồng thời cho phép thay behavior qua dependency. Trong tests, bạn cũng có thể truyền một fake implementation để ghi nhận tin nhắn mà không gửi thông báo thực.

## 6. Association, aggregation và composition: một reference chưa quyết định quyền sở hữu

Giữ field `Department department` hay `List<OrderLine> lines` cho thấy object A **biết hoặc tham chiếu** đến object B, nhưng không đủ để kết luận **ai sở hữu** B.

| Quan hệ | Ý nghĩa cần xác minh | Hình ảnh ví dụ |
| --- | --- | --- |
| **Association** | A liên hệ, biết hoặc điều hướng đến B | Employee → Department |
| **Aggregation** | Whole nhóm những part có thể có vòng đời riêng hoặc được chia sẻ | Team ↔ Member |
| **Composition** | Whole chịu trách nhiệm chặt về part và invariant/vòng đời theo mô hình nghiệp vụ | Order → OrderLine |

Java **không có keywords** `association`, `aggregation` hay `composition`, cũng không tự gọi “delete” khi gỡ một reference. Cả ba thường dùng fields/collections tương tự nhau; **quy tắc domain và API tạo/gỡ/chia sẻ đối tượng mới quyết định ý nghĩa quan hệ**.

Ở mức bài nhập môn này, hãy xác định: “A giữ reference nào?”, “B có thể được object khác giữ không?” và “ai kiểm tra invariants khi liên kết đổi?”. Bài **Quan hệ sử dụng, liên kết và sở hữu đối tượng** triển khai đầy đủ dependency, association, aggregation, composition, UML multiplicity và ownership transfer; bài này tiếp tục tập trung vào việc tham chiếu đến **chính object** và các aliases ở Java runtime.

## 7. Aliasing: hai chỗ cùng giữ một reference

**Alias** là những biến/fields cùng tham chiếu một object.

~~~java
Address shared = new Address("Ha Noi");
Customer a = new Customer("Lan", shared);
Customer b = new Customer("Minh", shared);
~~~

Nếu cả hai Customer giữ nguyên reference, thao tác đổi `shared.city` sẽ được cả hai quan sát. Đây là **chia sẻ cùng object**, không phải hai Address objects tự động đồng bộ.

### 7.1. Chương trình quan sát việc chia sẻ

Lưu **`SharedReferenceDemo.java`**:

~~~java
public class SharedReferenceDemo {
    static final class Box {
        private int value;

        Box(int value) {
            this.value = value;
        }

        int value() {
            return value;
        }

        void setValue(int value) {
            this.value = value;
        }
    }

    static final class Holder {
        private Box box;

        Holder(Box box) {
            this.box = box;
        }

        int read() {
            return box.value();
        }

        void replace(Box replacement) {
            box = replacement;
        }
    }

    public static void main(String[] args) {
        Box shared = new Box(10);
        Holder a = new Holder(shared);
        Holder b = new Holder(shared);

        System.out.println("initial=" + a.read() + "," + b.read());

        shared.setValue(20);
        System.out.println("mutated=" + a.read() + "," + b.read());

        a.replace(new Box(99));
        System.out.println("replaced=" + a.read() + "," + b.read());

        shared.setValue(30);
        System.out.println("original=" + a.read() + "," + b.read());
    }
}
~~~

Chạy:

~~~bash
javac SharedReferenceDemo.java
java SharedReferenceDemo
~~~

Output:

~~~text
initial=10,10
mutated=20,20
replaced=99,20
original=99,30
~~~

**Đọc đúng hai thao tác khác nhau:**

- `shared.setValue(20)` **sửa state của một object**. Hai holders đang trỏ object đó nên cùng thấy 20.
- `a.replace(new Box(99))` **thay reference** nằm trong field `a.box`. Nó không sửa `b.box` và không biến `shared` thành Box(99).
- Sau khi thay reference ở `a`, `shared.setValue(30)` chỉ tác động Box cũ mà `b` còn giữ. `a` đang trỏ Box mới có value 99.

Một lỗi logic rất phổ biến là nhầm `holder.box = new Box(...)` với `holder.box.setValue(...)`: phép gán reference thay object đích; lời gọi method sửa object đang được trỏ.

### 7.2. `final` field chặn cái nào?

~~~java
class Holder {
    private final Box box;

    Holder(Box box) {
        this.box = box;
    }

    void update(int value) {
        box.setValue(value); // Có thể hợp lệ.
    }
}
~~~

Đây là lớp minh họa (giả sử `Box` có method phù hợp). `final` không cho method `update` gán lại `box = new Box(...)`, nhưng vẫn có thể gọi method **mutate Box object**. `final` là một điều kiện về **field reference assignment**, không phải **deep immutability**.

## 8. Java truyền tham số tham chiếu như thế nào?

**Java luôn truyền tham số theo giá trị.** Với parameter kiểu tham chiếu, giá trị được sao chép là **reference value**, không phải object phía sau.

Điều đó có hai hệ quả:

1. Method có thể sửa object thông qua reference được truyền nếu object có API mutable.
2. Gán parameter sang một reference khác **không làm biến caller đổi reference**.

### 8.1. Chương trình chạy được

Lưu **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Person {
        String name;

        Person(String name) {
            this.name = name;
        }
    }

    static void mutate(Person p) {
        p.name = "Changed";
    }

    static void reassign(Person p) {
        p = new Person("Replacement");
        System.out.println("inside reassign=" + p.name);
    }

    public static void main(String[] args) {
        Person person = new Person("Original");

        mutate(person);
        System.out.println("after mutate=" + person.name);

        reassign(person);
        System.out.println("after reassign=" + person.name);
    }
}
~~~

Lệnh:

~~~bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Output:

~~~text
after mutate=Changed
inside reassign=Replacement
after reassign=Changed
~~~

`mutate` dùng reference copy để sửa **cùng Person object**. `reassign` chỉ thay reference trong local parameter `p`; biến `person` của caller vẫn trỏ object cũ.

Đừng gọi Java là “pass by reference” theo nghĩa biến phía caller có thể bị gán lại thông qua parameter thông thường. Cách nói chính xác: **pass by value, và value ở đây là reference**.

### 8.2. Truyền `null`

Nếu caller truyền `null` và method gọi `p.name` hoặc `p.method()`, thường sẽ gặp `NullPointerException`. Một method nhận reference nullable nên công bố hợp đồng rõ: cho phép null không, nếu không thì reject tại ranh giới.

## 9. Constructor injection và bất biến của quan hệ bắt buộc

Nếu một `Invoice` phải luôn gắn với `Customer`, thiết kế:

~~~java
class Invoice {
    private Customer customer;

    Invoice() {
    }

    void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
~~~

tạo khoảng thời gian mà Invoice tồn tại nhưng `customer == null`. Có thể hợp lý với builder/form đang nhập dở, nhưng không phù hợp nếu Invoice nghiệp vụ **luôn** cần một Customer.

Thiết kế bắt buộc dependency ngay từ constructor:

~~~java
import java.util.Objects;

class Invoice {
    private final Customer customer;

    Invoice(Customer customer) {
        this.customer = Objects.requireNonNull(
                customer, "customer");
    }

    Customer customer() {
        return customer;
    }
}
~~~

Đoạn này cần kiểu `Customer` được khai báo trong source/project. `Objects.requireNonNull` ném `NullPointerException` ngay tại constructor với tên tham số rõ. `final` làm reference của Invoice cố định sau khi object được xây đúng.

**Không có gì bắt buộc constructor phải tự tạo `new Customer()`.** Đưa dependency từ caller vào (*constructor injection*) thường có ích khi Customer đã tồn tại hoặc được nhiều invoices chia sẻ.

### 9.1. Khi nào tự tạo part bên trong?

Nếu part là implementation detail và không cần chia sẻ:

~~~java
class Device {
    private final Controller controller = new Controller();
}
~~~

đây là thiết kế hợp lý khi Controller đúng là thành phần riêng của Device. Nhưng Controller cần phải là class có constructor phù hợp. Tự tạo part ngầm làm việc thay implementation/test khó hơn; cân nhắc factory injection nếu cần đổi behavior hoặc ownership linh hoạt.

**Nguyên tắc:** ai tạo part, ai giữ reference, ai được phép sửa part và part có thể chia sẻ không phải được quyết định theo nghiệp vụ, không chỉ theo cú pháp field.

## 10. Đóng gói reference mutable và defensive copying

Ngay cả `private final Address address` vẫn có thể bị thay đổi **gián tiếp** nếu object Address mutable được chia sẻ.

Có ba chiến lược thường gặp:

1. **Chia sẻ có chủ đích:** giữ reference tới object chung, chấp nhận updates xuất hiện ở nhiều nơi. Phải mô tả rõ ownership/concurrency contract.
2. **Immutable value object:** dùng record/final class với immutable components, không có setters, nên chia sẻ an toàn hơn về state.
3. **Defensive copy/snapshot:** sao chép input mutable khi nhận và output mutable khi trả để bảo vệ representation.

### 10.1. Record immutable cho địa chỉ đơn giản

~~~java
record Address(String city) {
    Address {
        java.util.Objects.requireNonNull(city, "city");
        if (city.isBlank()) {
            throw new IllegalArgumentException("city required");
        }
    }
}
~~~

Với chỉ `String city` (String immutable), mỗi `Address` record có trạng thái quan sát được không thay đổi qua accessor. Consumer có thể giữ/chia sẻ reference tới cùng record mà không thể đổi city bằng setter.

Nhưng Java **record không tự tạo deep immutability** nếu component là mutable array, list hoặc custom mutable class; vẫn cần sao chép/bảo vệ components khi cần.

### 10.2. Chương trình hoàn chỉnh với immutable parts

Lưu **`ImmutableRelationshipDemo.java`**:

~~~java
import java.util.Objects;

public class ImmutableRelationshipDemo {
    record Address(String city) {
        Address {
            Objects.requireNonNull(city, "city");
            if (city.isBlank()) {
                throw new IllegalArgumentException("blank city");
            }
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = Objects.requireNonNull(name, "name");
            this.address = Objects.requireNonNull(address, "address");
        }

        String describe() {
            return name + "@" + address.city();
        }

        Customer moveTo(Address destination) {
            return new Customer(name, destination);
        }
    }

    public static void main(String[] args) {
        Address hanoi = new Address("Ha Noi");
        Customer first = new Customer("Lan", hanoi);
        Customer second = new Customer("Minh", hanoi);

        System.out.println(first.describe());
        System.out.println(second.describe());

        Customer moved = first.moveTo(new Address("Hue"));

        System.out.println("old=" + first.describe());
        System.out.println("new=" + moved.describe());
        System.out.println("second=" + second.describe());
    }
}
~~~

Chạy:

~~~bash
javac ImmutableRelationshipDemo.java
java ImmutableRelationshipDemo
~~~

Stdout:

~~~text
Lan@Ha Noi
Minh@Ha Noi
old=Lan@Ha Noi
new=Lan@Hue
second=Minh@Ha Noi
~~~

Hai Customers ban đầu chia sẻ **cùng Address record**, nhưng không có method nào mutate nó. Method `moveTo` trả Customer object **mới**, giữ object cũ nguyên trạng. `second` vẫn ở Ha Noi.

Lưu ý `Customer` ở đây là một cách minh họa thiết kế immutable; không phải mọi hệ thống khách hàng đều phải immutable. Cần chọn mô hình dữ liệu theo nhu cầu nghiệp vụ.

## 11. Sao chép một đối tượng mutable cả khi nhận lẫn khi trả

Nếu `Address` cần mutable, một class sở hữu bản chụp độc lập có thể sao chép ở constructor và trả một bản sao từ getter.

Lưu **`DefensiveAddressCopyDemo.java`**:

~~~java
public class DefensiveAddressCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        Address(Address source) {
            this.city = source.city;
        }

        void setCity(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }
    }

    static final class Customer {
        private final Address address;

        Customer(Address input) {
            if (input == null) {
                throw new IllegalArgumentException("address required");
            }
            address = new Address(input); // Sao chép khi nhận.
        }

        Address address() {
            return new Address(address); // Sao chép khi trả.
        }
    }

    public static void main(String[] args) {
        Address source = new Address("Ha Noi");
        Customer customer = new Customer(source);

        source.setCity("Hue");
        System.out.println("source=" + source.city());
        System.out.println("customer=" + customer.address().city());

        Address snapshot = customer.address();
        snapshot.setCity("Da Nang");

        System.out.println("snapshot=" + snapshot.city());
        System.out.println("customer after=" + customer.address().city());
    }
}
~~~

Chạy:

~~~bash
javac DefensiveAddressCopyDemo.java
java DefensiveAddressCopyDemo
~~~

Output:

~~~text
source=Hue
customer=Ha Noi
snapshot=Da Nang
customer after=Ha Noi
~~~

**Vì sao cần hai chiều copy?**

- Constructor copy: caller sửa `source` sau đó không làm thay đổi Customer.
- Getter copy: caller sửa object `snapshot` được trả về không sửa Address được giữ bên trong Customer.

Trong ví dụ, Address chỉ chứa `String` immutable nên copy constructor đơn giản là đủ. Nếu Address có mutable subobjects như `List<String>` hoặc `int[]`, copy một reference sang object mới vẫn là **shallow copy**, có thể phải copy các subobjects ở độ sâu cần thiết.

### 11.1. Shallow copy và deep copy

| Loại copy | Làm gì? | Nguy cơ |
| --- | --- | --- |
| Shallow copy | Tạo object ngoài mới nhưng giữ references tới inner objects | Inner mutable objects vẫn chia sẻ |
| Deep copy thích hợp | Tạo independent copies của toàn bộ mutable graph cần bảo vệ | Đắt hơn, phức tạp khi graph có cycle/shared identities |
| Immutable snapshot | Dùng immutable value types + cấu trúc không sửa được | Mutable elements còn shared nếu không bảo vệ |
| Không copy | Cố ý dùng chung object | Aliasing và concurrency phải rõ |

Không có một toán tử Java duy nhất bảo đảm deep copy cho **mọi object graph**. `Object.clone()` (nếu dùng) mặc định có hành vi shallow theo hợp đồng nền tảng; còn serialization/reflection-based copy có những rủi ro và điều kiện riêng. Khi cần độc lập, hãy thiết kế copy theo **kiểu/domain cụ thể**.

## 12. Quan hệ một–nhiều: object chứa danh sách references

Không phải lúc nào object cũng tham chiếu đúng một part. Ví dụ một `Order` có nhiều dòng hàng.

~~~java
class Order {
    private final java.util.List<OrderLine> lines;
}
~~~

`List<OrderLine>` mô tả **collection chứa references tới OrderLine objects**. Java không nhân bản mỗi OrderLine chỉ vì một phần tử được thêm vào list.

Với một phần tử mutable, cả list và caller có thể giữ reference tới **cùng OrderLine object**. Với một list mutable bị lộ qua getter, caller còn có thể thêm/xóa các reference trong collection nội bộ.

### 12.1. Hợp đồng một–nhiều cần trả lời

- Danh sách có thể **rỗng** không?
- Part có được **null** không?
- Part có được chia sẻ giữa nhiều Orders không?
- Ai được **thêm/xóa/sửa** phần tử?
- Order lưu snapshot hay live view?
- Khi xóa khỏi list, có phải dữ liệu part bị xóa bền vững không?
- Mọi OrderLine có thỏa invariants (quantity dương, unit price không âm) không?

Những câu hỏi đó không tự được giải đáp bởi một khai báo `List<OrderLine>`.

## 13. Ví dụ one-to-many có kiểm soát

Lưu **`OrderLinesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderLinesDemo {
    record OrderLine(String sku, int quantity, long unitPrice) {
        OrderLine {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long amount() {
            return Math.multiplyExact((long) quantity, unitPrice);
        }
    }

    static final class Order {
        private final String id;
        private final List<OrderLine> lines;

        Order(String id, List<OrderLine> input) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            this.id = id;
            this.lines = List.copyOf(input);
        }

        List<OrderLine> lines() {
            return lines;
        }

        long total() {
            long result = 0;
            for (OrderLine line : lines) {
                result = Math.addExact(result, line.amount());
            }
            return result;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        List<OrderLine> draft = new ArrayList<>();
        draft.add(new OrderLine("PEN", 2, 10));
        draft.add(new OrderLine("BOOK", 1, 35));

        Order order = new Order("O-7", draft);
        draft.clear();

        System.out.println("draft size=" + draft.size());
        System.out.println("order size=" + order.lines().size());
        System.out.println("total=" + order.total());

        try {
            order.lines().clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("order lines are read-only");
        }

        System.out.println("total after=" + order.total());
    }
}
~~~

Chạy:

~~~bash
javac OrderLinesDemo.java
java OrderLinesDemo
~~~

Stdout:

~~~text
draft size=0
order size=2
total=55
order lines are read-only
total after=55
~~~

**Giải thích:**

1. `draft` là mutable list bên ngoài, chứa hai immutable `OrderLine` records.
2. `Order` lưu `List.copyOf(input)`: cấu trúc list của Order là unmodifiable snapshot.
3. Xóa toàn bộ `draft` sau đó không xóa các dòng đã lưu trong Order.
4. Caller không được sửa cấu trúc `order.lines()` bằng `clear()`.
5. `Math.multiplyExact` và `Math.addExact` giúp phát hiện overflow số nguyên khi tính tổng; tránh số tiền sai âm thầm.
6. Các `OrderLine` records dùng `String` + primitives, không có nested mutable components; điều này giúp việc chia sẻ elements an toàn hơn.

**Không đồng nghĩa composition tự động:** `Order` ở ví dụ không thể bị caller sửa cấu trúc thông qua API, nhưng record `OrderLine` vẫn có thể được tạo và dùng ở nơi khác. Nếu nghiệp vụ bắt buộc part thuộc duy nhất một Order, cần thiết kế identity/ownership contract bổ sung.

### 13.1. `List.copyOf` không phải deep copy

`List.copyOf` ngăn mutate cấu trúc list trả về/được lưu, và lấy snapshot về các phần tử hiện tại; nó **không** sao chép sâu mỗi element object.

Ngoài ra `List.copyOf` **không chấp nhận null elements** và có thể tái sử dụng một list đầu vào vốn đã unmodifiable phù hợp. Đừng dựa vào việc mỗi lời gọi `copyOf` tạo một object list mới theo identity; hãy dựa vào tính không sửa được/snapshot theo contract.

Nếu `OrderLine` là class mutable có `setUnitPrice(...)`, việc giữ reference chung đến elements có thể phá invariant của Order. Khi đó, ưu tiên immutable elements hoặc sao chép sâu/DTO bất biến theo nhu cầu.

## 14. Unmodifiable view, snapshot và live sharing

Có hai cách dễ nhầm:

~~~java
List<Member> view = java.util.Collections.unmodifiableList(source);
List<Member> copy = List.copyOf(source);
~~~

Giả sử `source` là mutable list:

- `view` là **read-only view** trỏ tới backing list `source`. Caller không sửa qua `view`, nhưng nếu ai đó sửa `source` thì `view` có thể phản ánh những thay đổi ấy.
- `copy` là một unmodifiable snapshot của các element references tại thời điểm gọi. Thêm/xóa phần tử trong `source` sau đó không thay đổi cấu trúc `copy`.
- **Cả hai** có thể giữ reference tới **cùng Member objects**. Nếu Member mutable, nội dung Member có thể thay đổi qua alias.
- `new ArrayList<>(source)` tạo mutable shallow copy; caller sửa cấu trúc bản copy không ảnh hưởng cấu trúc source, nhưng elements có thể vẫn shared.

### 14.1. Chương trình phân biệt view với snapshot

Lưu **`ViewVsSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot add");
        }
    }
}
~~~

Chạy:

~~~bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

Output:

~~~text
source=[A, B]
view=[A, B]
snapshot=[A]
view cannot add
~~~

Đây là sự khác biệt quan trọng trong thiết kế quan hệ một–nhiều. Trả read-only view không phải lúc nào cũng có nghĩa caller nhận dữ liệu bất biến theo thời điểm.

## 15. `null`, quan hệ tùy chọn và cách xử lý an toàn

Một field tham chiếu có thể bằng `null` nếu không được gán. Đối với quan hệ **tùy chọn**, điều này có thể là ý định hợp lệ; đối với quan hệ **bắt buộc**, nó có thể là trạng thái sai nghiệp vụ.

### 15.1. Quan hệ bắt buộc

~~~java
class Order {
    private final Customer customer;

    Order(Customer customer) {
        this.customer = java.util.Objects.requireNonNull(
                customer, "customer");
    }
}
~~~

Ở đây `customer` luôn non-null khi constructor hoàn thành bình thường. Nếu Customer object mutable, non-null **không** có nghĩa mọi state của Customer luôn hợp lệ; cần thiết kế hợp đồng của Customer nữa.

### 15.2. Quan hệ tùy chọn

Nếu Employee có thể chưa có manager, API có thể biểu diễn bằng field nullable và method trả `Optional`:

~~~java
import java.util.Optional;

class Employee {
    private Employee manager;

    Optional<Employee> manager() {
        return Optional.ofNullable(manager);
    }

    void assignManager(Employee manager) {
        this.manager = manager;
    }
}
~~~

Đây là một ví dụ **giá trị null mang ý nghĩa hợp đồng**, không phải lỗi mặc định. `Optional` thường phù hợp làm **kiểu trả về** để caller xử lý có/không. Không cần biến mọi field nullable thành `Optional<Field>` field; chọn API dựa vào domain và coding conventions.

### 15.3. Chuỗi truy cập tham chiếu có thể ném NPE

~~~java
customer.address().city()
~~~

Nếu `customer` hoặc `address()` trả null, phép truy cập tiếp theo có thể ném `NullPointerException`. Đừng nối chuỗi method calls chỉ vì dữ liệu hiện tại trong tests luôn có đủ object.

Cách tốt hơn khi quan hệ bắt buộc: validate tại constructor và không trả null. Khi tùy chọn: dùng `Optional`, nhánh kiểm tra hoặc giá trị domain rõ ràng.

## 16. Ví dụ tùy chọn manager bằng `Optional`

Lưu **`OptionalRelationshipDemo.java`**:

~~~java
import java.util.Optional;

public class OptionalRelationshipDemo {
    static final class Employee {
        private final String name;
        private Employee manager;

        Employee(String name) {
            this.name = name;
        }

        void setManager(Employee manager) {
            this.manager = manager;
        }

        Optional<Employee> manager() {
            return Optional.ofNullable(manager);
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Employee lan = new Employee("Lan");
        Employee minh = new Employee("Minh");

        System.out.println("Lan manager=" +
                lan.manager().map(Employee::name).orElse("none"));

        lan.setManager(minh);

        System.out.println("Lan manager=" +
                lan.manager().map(Employee::name).orElse("none"));
        System.out.println("Minh manager=" +
                minh.manager().map(Employee::name).orElse("none"));
    }
}
~~~

Chạy:

~~~bash
javac OptionalRelationshipDemo.java
java OptionalRelationshipDemo
~~~

Output:

~~~text
Lan manager=none
Lan manager=Minh
Minh manager=none
~~~

Điều này chỉ minh họa optional reference, **không** triển khai các quy tắc tổ chức thực tế như “employee không được tự quản lý chính mình” hay “không có vòng quản lý”. Những invariants ấy cần validation nếu nghiệp vụ yêu cầu.

## 17. Identity khác equality: cùng object hay cùng dữ liệu?

Một câu hỏi khác là hai references đang trỏ đến **cùng object** hay hai objects khác nhau nhưng **có cùng nội dung**.

- `a == b` với hai references: so **identity của references** (cùng object hay không), trừ trường hợp null.
- `a.equals(b)`: gọi logic equality của object theo implementation; với class không override, `Object.equals` mặc định dựa trên identity.
- Java records cung cấp `equals` theo record components với semantics phù hợp; hai record instances riêng có thể equal về value.

### 17.1. Chương trình minh họa identity/value

Lưu **`ReferenceEqualityDemo.java`**:

~~~java
public class ReferenceEqualityDemo {
    record Address(String city) {
    }

    static final class Box {
        private final int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Address a1 = new Address("Hue");
        Address a2 = new Address("Hue");
        Address alias = a1;

        System.out.println("record identity=" + (a1 == a2));
        System.out.println("record equals=" + a1.equals(a2));
        System.out.println("alias identity=" + (a1 == alias));

        Box b1 = new Box(5);
        Box b2 = new Box(5);

        System.out.println("box identity=" + (b1 == b2));
        System.out.println("box equals=" + b1.equals(b2));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ReferenceEqualityDemo.java
java ReferenceEqualityDemo
~~~

Output:

~~~text
record identity=false
record equals=true
alias identity=true
box identity=false
box equals=false
~~~

**Lưu ý thiết kế:** nên định nghĩa `equals`/`hashCode` cùng nhau nếu custom class cần equality theo giá trị và được dùng trong `HashSet`/`HashMap`. Với các entity mang identity nghiệp vụ, giá trị bằng nhau chưa chắc tương đương “cùng một entity”; cần một hợp đồng equality rõ.

### 17.2. Tránh dùng `==` để so thông tin text

Nếu `Customer` chứa `String name`, so hai tên bằng `==` là so reference identity của String objects. Nên dùng `name.equals(otherName)` nếu non-null hoặc `Objects.equals(name, otherName)` khi nullable.

## 18. Quan hệ hai chiều: hai objects giữ reference lẫn nhau

Một liên kết có thể là **một chiều**:

~~~text
Employee ----> Department
~~~

hoặc **hai chiều**:

~~~text
Employee ----> Department
          <----
~~~

Nếu `Employee` giữ `Department` và `Department` giữ danh sách `Employee`, đây là hai hướng reference **độc lập về mặt field assignment**. Java **không tự động** cập nhật cả hai hướng khi bạn thay một bên.

### 18.1. Vấn đề đồng bộ hai đầu

Nếu chỉ chạy:

~~~java
employee.department = newDepartment;
~~~

và Department cũ vẫn giữ employee trong list, object graph có thể không nhất quán. Ngoài việc đóng gói fields, cần một method quản lý quan hệ:

~~~java
void transfer(Employee employee, Department destination) {
    // Kiểm tra đầu vào/trạng thái
    // Loại employee khỏi source department
    // Thêm employee vào destination department
    // Cập nhật employee.department
}
~~~

Đây là **pseudocode thiết kế**, không phải method runnable vì chưa có đầy đủ class/API. Nó minh họa rằng quan hệ hai chiều là một **invariant nhiều objects** và phải được cập nhật có kiểm soát.

Khi có concurrency/persistence, thao tác phối hợp có thể cần locks, transaction hoặc aggregate boundary; vài assignments rời rạc không tạo atomicity.

### 18.2. Chu trình references không nhất thiết là memory leak

Giả sử A trỏ B và B trỏ A. **Garbage collector Java xét reachability từ GC roots**, không đơn thuần đếm số references. Nếu cả cặp không còn reachable từ roots, Java GC có thể thu hồi cả chu kỳ (không cam kết thời điểm). Chu kỳ tự nó **không đồng nghĩa memory leak**.

Ngược lại, nếu một static collection vẫn giữ reference tới A, thì graph A↔B có thể vẫn reachable và chiếm bộ nhớ dù nghiệp vụ đã “xong”. Đây mới là rủi ro giữ references quá lâu.

## 19. Chương trình object graph có chu kỳ

Lưu **`CyclicReferencesDemo.java`**:

~~~java
public class CyclicReferencesDemo {
    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void connect(Node next) {
            this.next = next;
        }

        String nextName() {
            return next == null ? "none" : next.name;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.connect(b);
        b.connect(a);

        System.out.println("A -> " + a.nextName());
        System.out.println("B -> " + b.nextName());
        System.out.println("same A=" + (a == b.next));
    }
}
~~~

Chạy:

~~~bash
javac CyclicReferencesDemo.java
java CyclicReferencesDemo
~~~

Output:

~~~text
A -> B
B -> A
same A=true
~~~

Hai objects tham chiếu lẫn nhau; field `next` chỉ chứa reference. Nếu implement `toString()` bằng cách in **toàn bộ next object theo đệ quy** mà không có bảo vệ visited/depth, graph dạng chu kỳ có thể gây đệ quy vô hạn/`StackOverflowError`.

**Thiết kế tốt:** in ID/tên ngắn thay vì recursively render mọi object; hoặc duyệt graph bằng tập visited khi cần.

## 20. Garbage collection, vòng đời và quan hệ sở hữu

Java có automatic garbage collection, nhưng **không có cú pháp Java field reference nào tự áp dụng delete/cascade-delete của composition UML**.

Một số tình huống:

- `customer.address = null` (nếu field mutable) chỉ bỏ **một đường tham chiếu** tới Address object; Address vẫn có thể còn reference từ biến/objects khác.
- Xóa `order.lines().remove(line)` (nếu list mutable) chỉ thay cấu trúc collection; không nhất thiết xóa line khỏi database hay thu hồi ngay object.
- Khi không còn reachable từ GC roots, object có thể **đủ điều kiện** được thu gom. JVM không hứa collector chạy đúng lúc bạn gán `null`.
- GC thu hồi **bộ nhớ quản lý**, không tự đóng file/socket/DB transaction đúng thời điểm. Tài nguyên ngoài heap nên có lifecycle explicit, thường qua `try-with-resources` và `AutoCloseable`.
- Object reference có thể được giữ từ nơi khác ngoài mô hình “owner” tưởng tượng; chỉ public/private field không tự chặn mọi alias.

**Composition mạnh về domain** cần API và ownership rules thật, không thể dựa vào giả định rằng `new Owner()` tự điều khiển bộ nhớ của toàn bộ parts.

### 20.1. `static` reference làm vòng đời khác hẳn

Một `static List<Object> cache` giữ references có thể khiến một graph objects tiếp tục reachable trong runtime. Đừng dùng mutable global static collections như “danh sách các object tồn tại” mà không có chính sách eviction hoặc lifecycle phù hợp.

## 21. `private` không luôn bảo vệ dữ liệu phía sau reference

Xem:

~~~java
class Customer {
    private final java.util.List<String> tags;

    Customer(java.util.List<String> tags) {
        this.tags = tags;
    }

    java.util.List<String> tags() {
        return tags;
    }
}
~~~

Field `tags` là `private final` nhưng:

1. Caller giữ `tags` input có thể thêm/xóa phần tử sau khi Customer được tạo.
2. Getter trả lại **cùng mutable list** cho code khác.
3. `final` ngăn gán lại `this.tags`, không ngăn mutate list.

Nếu API muốn giữ **snapshot chỉ đọc**, dùng:

~~~java
class Customer {
    private final java.util.List<String> tags;

    Customer(java.util.List<String> tags) {
        this.tags = java.util.List.copyOf(tags);
    }

    java.util.List<String> tags() {
        return tags;
    }
}
~~~

Hai phiên bản trên là **thiết kế thay thế**, không được cùng định nghĩa một class tên Customer trong một package khi biên dịch.

Nếu phần tử list là mutable custom object, `List.copyOf` vẫn chia sẻ từng element. Chọn immutable element type hoặc defensive-copy thích hợp.

## 22. Tham chiếu qua interface và polymorphism

Một field có thể có **kiểu interface hoặc superclass**:

~~~java
private PaymentMethod paymentMethod;
~~~

Tại runtime, nó có thể trỏ tới `CardPayment`, `WalletPayment` hoặc implementation khác. Caller nhìn thấy behavior theo kiểu tĩnh `PaymentMethod`, còn method override thực thi theo runtime object.

Lợi ích:

- Object chứa field phụ thuộc **abstraction** thay vì implementation detail.
- Dễ thay object triển khai và viết unit tests.
- Tránh constructor của object ngoài phải hiểu toàn bộ nested implementation.
- Cho phép tổ chức trách nhiệm nhỏ và rõ.

Giới hạn:

- Nếu giữ reference mutable không kiểm soát, code khác có thể thay behavior/state ở runtime.
- Nếu implementation không thread-safe, việc inject nó không làm class chứa nó thread-safe.
- Interface không bảo đảm mỗi implementation thỏa contract nếu không có kiểm thử và thiết kế đúng.

**Dùng composition thay inheritance** thường có lợi khi “A dùng B để hoàn thành việc” chứ không phải “A là một loại của B”.

## 23. Concurrency: object graph chia sẻ state cũng chia sẻ rủi ro

Nếu hai objects A và B cùng giữ reference tới một mutable Counter và được dùng ở hai threads, chúng cùng truy cập **một Counter object**. `private` của reference field trong A và B không tạo hai bản sao Counter.

Ví dụ:

~~~java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
~~~

`value++` không atomic. Nếu nhiều threads dùng shared Counter, có thể mất updates hoặc gặp visibility issues theo Java Memory Model.

Giải pháp tùy trường hợp:

- Dùng immutable values và thay reference theo mô hình có kiểm soát.
- Dùng synchronization/locks nhất quán cho state mutable cần bảo vệ.
- Dùng `AtomicInteger` cho counter đơn giản, nhưng không suy ra nhiều fields tự được cập nhật atomic.
- Tránh chia sẻ state mutable khi có thể; xác định ownership rõ.
- Nếu một object trả snapshot và ngay sau đó threads khác cập nhật state, snapshot có thể là ảnh tại một thời điểm, không phải live view.

Trong Java 17, `final` field giúp không gán lại reference sau khởi tạo hợp lệ; nó **không** tự làm object được tham chiếu thread-safe.

## 24. Những lỗi thường gặp khi thiết kế quan hệ giữa lớp

| Lỗi/nhầm lẫn | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “`Address address;` tự tạo Address object.” | Field chỉ có reference, thường mặc định null | Gán reference qua constructor/initializer |
| “`new Customer()` chắc tạo Address bên trong.” | Không có cơ chế tự động như vậy | Quy định ai tạo và inject/sở hữu Address |
| “`a = b` clone object.” | Chỉ sao chép reference | Dùng copy/factory nếu cần independent state |
| “Hai references bằng nhau về fields thì chắc là cùng object.” | Identity khác value equality | Phân biệt `==` và `equals` |
| “`private final Address` khiến Address immutable.” | Final chỉ chặn gán lại field reference | Immutable Address hoặc defensive copy |
| “Getter trả list private thì không ai mutate được.” | Getter có thể lộ mutable reference | Unmodifiable snapshot/copy theo contract |
| “`Collections.unmodifiableList` là snapshot.” | Có thể là live view của backing list | `List.copyOf` nếu cần snapshot |
| “`List.copyOf` deep-copy elements.” | Elements vẫn shared | Immutable elements/deep copy |
| “Cứ có field là composition UML.” | Ownership không được chứng minh bởi cú pháp | Định nghĩa lifecycle/invariants qua API |
| “Aggregation/Composition có từ khóa Java.” | Chúng là khái niệm mô hình hóa | Diễn đạt bằng fields, constructors, factories và contracts |
| “Quan hệ hai chiều tự đồng bộ.” | Hai references/collections là fields riêng | Method quản lý cả hai phía |
| “Có chu kỳ reference thì GC không thu hồi.” | Reachability mới là yếu tố chính | Tránh giữ graph từ GC roots không cần thiết |
| “Set reference null sẽ lập tức giải phóng object.” | Có thể còn aliases; GC không tức thì | Quản lý lifecycle và resources rõ |
| “Java truyền object theo tham chiếu.” | Java pass-by-value của reference | Phân biệt mutate với reassignment |
| “`null` lúc nào cũng là lỗi.” | Nullable association có thể là domain hợp lệ | Optional/contract rõ |
| “Có `final` thì thread-safe.” | Mutable referent vẫn có races | Đồng bộ hoặc thiết kế immutable |
| “Recursive `toString` qua mọi field luôn an toàn.” | Bidirectional cycles có thể recurse vô hạn | In ID, giới hạn độ sâu, visited set |
| “Order bỏ Line khỏi list là xóa line ở DB.” | Collection update khác persistence operation | Thiết kế repository/transaction riêng |

## 25. Checklist thiết kế một reference field

Trước khi viết `private B b;` bên trong class A, hãy tự hỏi:

1. **Quan hệ nghiệp vụ là gì?** A có, biết, dùng, quản lý hay sở hữu B?
2. **Số lượng:** 1–1, 0–1, 1–n, 0–n hay n–n?
3. **Bắt buộc hay tùy chọn?** Cho phép `null`/empty không?
4. **Ai tạo B?** A tự tạo, caller inject, factory hay repository?
5. **Ai sở hữu B?** Có được nhiều As tham chiếu cùng một B không?
6. **B có mutable không?** Mutations từ A/B/third party ảnh hưởng nhau ra sao?
7. **Có cần `final` field không?** Quan hệ có cố định hay cần thay reference?
8. **Getter trả gì?** Original mutable reference, read-only view, snapshot, immutable value hay chỉ một dữ liệu tính toán?
9. **Nội dung B có cần defensive copy không?** Shallow đủ hay cần deep theo graph?
10. **Quan hệ hai chiều không?** Ai bảo đảm cả hai phía đồng bộ?
11. **Có invariant nhiều objects không?** Ví dụ line thuộc order, employee thuộc department.
12. **Có vòng references không?** Xử lý `toString`, serialization, graph traversal thế nào?
13. **Concurrency contract là gì?** Được dùng chung threads không?
14. **Resource/persistence lifecycle thuộc ai?** GC không thay transaction/close.
15. **Identity/equality định nghĩa thế nào?** Entity theo ID hay value object theo content?
16. **Tests có chứng minh behavior không?** Alias, null, replace, copy, getter mutation và cycles.

## 26. Câu hỏi ôn tập có lời giải

**Câu 1.** Viết `class Customer { Address address; }` đã tạo một Address object chưa?  
**Đáp án:** Chưa. Đó là khai báo reference field; nếu không gán, giá trị mặc định của field là null.

**Câu 2.** `Address a = new Address(); Address b = a;` tạo bao nhiêu Address object?  
**Đáp án:** Một. Hai biến chứa cùng reference value.

**Câu 3.** `Address b = new Address();` có khác `b = a` không?  
**Đáp án:** Có. `new` tạo object mới; assignment sao chép reference hiện có.

**Câu 4.** Nếu `Customer.address` giữ reference tới Address mutable do caller cung cấp, caller đổi city thì Customer thấy thay đổi không?  
**Đáp án:** Có thể có, nếu vẫn tham chiếu cùng object và không copy.

**Câu 5.** `private final Address address` có ngăn `address.setCity(...)` không?  
**Đáp án:** Không tự ngăn. Final khóa reference field, không khóa state của Address.

**Câu 6.** `customer.address = new Address(...)` (khi có quyền ghi field) làm gì?  
**Đáp án:** Thay reference của field customer.address; không tự mutate Address object cũ.

**Câu 7.** `Customer` có thể giữ field kiểu `Notifier` interface không?  
**Đáp án:** Có. Field có thể tham chiếu instance thuộc class triển khai Notifier.

**Câu 8.** `Car has Engine` khác `ElectricCar extends Car` ở đâu?  
**Đáp án:** Một cái là quan hệ object/has-a (composition/association); cái kia là quan hệ kiểu/is-a (inheritance).

**Câu 9.** Một `Team` chứa `List<Member>` có tự chứng minh composition mạnh không?  
**Đáp án:** Không. Ownership, chia sẻ và lifecycle là hợp đồng thiết kế, không do riêng cú pháp List quyết định.

**Câu 10.** Tại sao trả một mutable `ArrayList` nội bộ qua getter có thể nguy hiểm?  
**Đáp án:** Caller nhận cùng reference và có thể thêm/xóa/sửa cấu trúc list trực tiếp.

**Câu 11.** `List.copyOf` có tự deep-copy các `Member` mutable không?  
**Đáp án:** Không. Nó bảo vệ cấu trúc list snapshot, nhưng references tới Member objects có thể còn shared.

**Câu 12.** `Collections.unmodifiableList(source)` có tự giữ snapshot cũ khi `source.add(...)` không?  
**Đáp án:** Không bảo đảm snapshot; unmodifiable view có thể phản ánh thay đổi backing list.

**Câu 13.** Vì sao constructor injection giúp class có required dependency?  
**Đáp án:** Nó bắt buộc caller cung cấp dependency khi tạo và class có thể kiểm tra non-null trước khi object hoàn tất khởi tạo.

**Câu 14.** Nếu B có state mutable, cần làm gì để A giữ snapshot độc lập?  
**Đáp án:** Defensive copy input khi nhận và tránh lộ internal mutable reference khi trả, copy tới độ sâu cần thiết.

**Câu 15.** `record Address(String city)` với String component có thể được chia sẻ an toàn hơn mutable Address như thế nào?  
**Đáp án:** Record có immutable component reference và String immutable; không có setter sửa city tại chỗ.

**Câu 16.** Record chứa `int[]` có chắc deep immutable không?  
**Đáp án:** Không. Array mutable; cần copy ở constructor/accessor nếu muốn ngăn aliasing.

**Câu 17.** Java truyền parameter `Person p` theo reference hay theo value?  
**Đáp án:** Java truyền **bản sao của reference value**. Method có thể mutate object qua p, nhưng gán lại p không gán lại biến caller.

**Câu 18.** `a == b` và `a.equals(b)` với references kiểm tra gì?  
**Đáp án:** `==` so identity; `equals` theo implementation/hợp đồng equality của object.

**Câu 19.** Hai Java records Address có cùng city nhưng được `new` riêng sẽ như thế nào?  
**Đáp án:** `==` thường false vì khác instances; `equals` có thể true vì cùng components.

**Câu 20.** Vì sao một Employee và Department giữ reference hai chiều không tự đồng bộ?  
**Đáp án:** Hai sides có fields/lists riêng; Java không tự update phía kia. Cần controlled methods.

**Câu 21.** A tham chiếu B, B tham chiếu A: cả hai có chắc memory leak không?  
**Đáp án:** Không. GC xét reachability từ roots; graph không reachable có thể được thu hồi dù có cycle.

**Câu 22.** Xóa object khỏi list có tự đóng tài nguyên của nó hoặc xóa DB record không?  
**Đáp án:** Không. Đó là thay đổi collection reference, không phải lifecycle/persistence operation tự động.

**Câu 23.** Một static cache giữ reference tới object graph làm gì với vòng đời bộ nhớ?  
**Đáp án:** Có thể giữ graph reachable và chiếm bộ nhớ lâu hơn cần thiết; cần eviction/lifecycle.

**Câu 24.** Hai threads dùng chung mutable object B qua hai holders có tự thread-safe do holders giữ fields private không?  
**Đáp án:** Không. B vẫn được chia sẻ; cần thread-safe contract hoặc synchronization/immutability.

**Câu 25.** Một `Address` field nên nullable hay required?  
**Đáp án:** Phụ thuộc domain: nếu bắt buộc thì constructor validate; nếu tùy chọn thì công bố ngữ nghĩa absent rõ.

**Câu 26.** Làm sao tránh recursive `toString()` ở graph có cycles?  
**Đáp án:** In identifiers/summary fields, hạn chế độ sâu hoặc dùng visited set khi duyệt graph.

**Câu 27.** Nếu Order tạo `OrderLine` immutable và chỉ trả unmodifiable list snapshot, đã đủ đảm bảo OrderLine chỉ thuộc một Order chưa?  
**Đáp án:** Chưa. Ownership/domain identity cần contract rõ; line value object vẫn có thể được dùng ở nơi khác.

**Câu 28.** Khi nào nên dùng composition qua interface hơn kế thừa?  
**Đáp án:** Khi class cần **sử dụng/ủy quyền** behavior của một dependency có thể thay đổi implementation, thay vì có quan hệ kiểu “is-a” thật sự.

## Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference types và giá trị.
- Java Language Specification, [`4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.5): mặc định `null` cho reference fields.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object creation.
- Java Language Specification, [`15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): biểu thức `new`.
- Java Language Specification, [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): method calls và runtime dispatch.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): khai báo fields, `final`.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list snapshot.
- Java Platform API, [`Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): kiểm tra reference bắt buộc.
- Java Platform API, [`Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): biểu diễn giá trị có thể vắng mặt tại API.
- Java Platform API, [`Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): hợp đồng equality.

## Tổng kết

Một object **chứa tham chiếu tới object khác** bằng một field kiểu tham chiếu. Điều đó tạo ra quan hệ **has-a/association** và giúp các objects cộng tác; nó **không** tự tạo, sao chép, sở hữu độc quyền hay hủy object được tham chiếu. Nhiều references có thể chỉ tới cùng object (*aliasing*), nên sửa state của object chung được quan sát ở các nơi giữ reference ấy.

Hãy thiết kế quan hệ bằng những quyết định rõ ràng: **bắt buộc hay tùy chọn**, **tạo ở đâu**, **chia sẻ hay sở hữu**, **mutable hay immutable**, **getter trả original/view/snapshot**, **có cần đồng bộ hai phía**, và **thread-safety/lifecycle** ra sao. `private` và `final` bảo vệ mức field nhưng không tự làm graph bất biến. Constructor injection, immutable records, defensive copying và controlled methods là các công cụ then chốt để mô hình quan hệ giữa các lớp chính xác, dễ kiểm thử và dễ bảo trì.
