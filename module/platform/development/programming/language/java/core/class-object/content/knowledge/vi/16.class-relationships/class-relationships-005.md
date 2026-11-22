# Ủy quyền thao tác cho đối tượng thành phần trong Java

## 1. Mục tiêu của bài học

Trong lập trình hướng đối tượng, **ủy quyền (*delegation*)** là cách một đối tượng **nhờ một đối tượng khác thực hiện một phần công việc**. Đối tượng nhận yêu cầu từ caller được gọi là đối tượng **ủy quyền/chuyển tiếp** (*delegator*); đối tượng thực hiện công việc chuyên trách thường được gọi là **đối tượng thành phần, cộng tác viên hoặc delegate** (*component/collaborator/delegate*).

Ví dụ một `Car` có `Engine`. Khi caller gọi `car.start()`, `Car` không nhất thiết tự thực hiện logic khởi động động cơ; nó có thể gọi `engine.start()`:

```java
class Car {
    private final Engine engine = new Engine();

    void start() {
        engine.start();
    }
}
```

Đoạn trên là **minh họa phần class**, giả định có class `Engine` khai báo instance method `start()`. Điểm cốt lõi không nằm ở số dòng code, mà ở **phân chia trách nhiệm**:

- `Car` quyết định **khi nào** cần khởi động.
- `Engine` sở hữu **cách khởi động động cơ**.
- Caller chỉ cần API `Car.start()`, không bắt buộc biết `Engine` được dùng ở bên trong.

Đây là một kỹ thuật quan trọng để hiện thực quan hệ **has-a/uses-a**, giảm coupling, tăng cohesion và giúp thay đổi implementation mà không phải sửa mọi caller.

Sau bài này, bạn sẽ có thể:

1. Nhận diện một lời gọi ủy quyền trong code Java.
2. Viết class có trường tham chiếu tới component và phương thức chuyển tiếp lời gọi.
3. Phân biệt delegation với inheritance, composition, aggregation và wrapper/decorator.
4. Quyết định nên chuyển tiếp toàn bộ hay chỉ một phần API của component.
5. Hiểu ownership, aliasing, dependency injection và xử lý lỗi khi component thất bại.
6. Kiểm thử delegator bằng một fake collaborator.
7. Phát hiện các lỗi thiết kế: vòng ủy quyền, lộ mutable component, truyền sai tham số, che mất exception hoặc tạo state dùng chung không mong muốn.

## 2. Ví dụ đầu tiên: `Car` giao việc cho `Engine`

Tạo tệp **`DelegationBasicsDemo.java`**:

```java
class Engine {
    private boolean running;

    void start() {
        if (!running) {
            running = true;
            System.out.println("Engine started");
        }
    }

    boolean isRunning() {
        return running;
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    void start() {
        System.out.println("Car receives start request");
        engine.start();
    }

    boolean isRunning() {
        return engine.isRunning();
    }
}

public class DelegationBasicsDemo {
    public static void main(String[] args) {
        Engine engine = new Engine();
        Car car = new Car(engine);

        car.start();
        System.out.println("running=" + car.isRunning());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac DelegationBasicsDemo.java
java DelegationBasicsDemo
```

**Standard output:**

```text
Car receives start request
Engine started
running=true
```

Hãy đọc theo luồng thực thi:

1. `new Engine()` tạo object động cơ.
2. `new Car(engine)` tạo object xe và giữ một tham chiếu `engine` trong field `private final`.
3. Caller gọi `car.start()`. Receiver của lời gọi là **Car object**.
4. `Car.start()` in thông báo rồi gọi `engine.start()`. Receiver của lời gọi bên trong là **Engine object**.
5. `Engine.start()` đổi trạng thái riêng của Engine, in `Engine started`.
6. `Car.isRunning()` lại **ủy quyền việc truy vấn trạng thái** cho `Engine.isRunning()`.

Đây không phải method invocation trên cùng một receiver. Hai objects có identities và trách nhiệm riêng:

```text
main
  |
  | car.start()
  v
Car object
  |
  | engine.start()
  v
Engine object
  |
  +-- running: false -> true
```

**Một chi tiết quan trọng:** `final Engine engine` chỉ ngăn field `engine` bị gán sang reference khác sau construction hợp lệ; nó **không làm Engine bất biến**. `engine.start()` vẫn mutate `running`.

## 3. Ủy quyền là hành vi; composition là quan hệ cấu trúc

Hai khái niệm này thường xuất hiện cùng nhau nhưng **không đồng nghĩa**.

- **Composition/has-a:** một class giữ object thành phần trong field, ví dụ `Car` có `Engine`.
- **Delegation:** một method **gọi method của object khác để thực hiện công việc**, ví dụ `Car.start()` gọi `Engine.start()`.
- **Aggregation:** một mô tả thiết kế về quan hệ giữa đối tượng toàn thể và đối tượng được tham chiếu khi vòng đời/ownership có mức độc lập cao hơn; Java không có keyword `aggregation`.
- **Dependency:** một class sử dụng dịch vụ của một type khác, có thể qua field, parameter, local variable hoặc return value.

Có thể **composition mà chưa delegation**: class giữ component để làm dữ liệu nhưng tự xử lý toàn bộ logic mà không gọi method component.

Có thể **delegation mà không sở hữu component lâu dài**: method nhận đối tượng cộng tác qua parameter rồi nhờ nó xử lý.

Ví dụ delegation qua tham số:

```java
class ReportPrinter {
    void print(String report, java.io.PrintStream destination) {
        destination.println(report);
    }
}
```

`ReportPrinter` không có field giữ `PrintStream`, nhưng method `print` vẫn **giao phần in thực tế** cho collaborator `destination`. Đoạn này là class minh họa, không có `main`.

### Khi nào gọi đó là “đối tượng thành phần”?

Trong bài này, ta tập trung vào trường hợp một class có **field tham chiếu đến object khác** và chuyển tiếp phần việc cho object ấy. Đây là hình thức phổ biến nhất của delegation trong quan hệ giữa lớp, nhưng bản chất delegation là **sự chuyển giao hành vi**, không phải chỉ việc có một field.

## 4. Lời gọi được chuyển tiếp như thế nào?

Ví dụ đơn giản:

```java
final class OrderService {
    private final PriceCalculator calculator;

    OrderService(PriceCalculator calculator) {
        this.calculator = calculator;
    }

    int total(int price, int fee) {
        return calculator.addFee(price, fee);
    }
}
```

`PriceCalculator` ở đây là type giả định có `int addFee(int,int)`; đây là **mảnh minh họa, không phải chương trình độc lập**.

Đọc dòng:

```java
return calculator.addFee(price, fee);
```

- `calculator` là **receiver reference** của lời gọi instance method.
- `addFee` được chọn theo quy tắc method resolution/dispatch.
- Các đối số `price`, `fee` được truyền theo **giá trị** của Java.
- Giá trị method trả về được `OrderService.total` chuyển tiếp cho caller.
- Nếu collaborator ném exception, exception có thể **lan truyền ra caller**, trừ khi delegator chủ động xử lý.
- Nếu collaborator có side effect, side effect có thể xảy ra **trước khi delegator hoàn tất method**.

Không có syntax đặc biệt `delegate` trong Java để compiler tự làm việc này cho class thông thường. Ta viết **forwarding method** tường minh (hoặc công cụ sinh code hỗ trợ theo quy trình riêng), rồi kiểm soát contract của method chuyển tiếp.

## 5. Một ví dụ trọn vẹn: `Order` ủy quyền tính giá

Tệp **`OrderDelegationDemo.java`**:

```java
final class PriceCalculator {
    int total(int basePrice, int shippingFee) {
        if (basePrice < 0 || shippingFee < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return Math.addExact(basePrice, shippingFee);
    }
}

final class Order {
    private final int basePrice;
    private final PriceCalculator calculator;

    Order(int basePrice, PriceCalculator calculator) {
        if (basePrice < 0) {
            throw new IllegalArgumentException("negative base price");
        }

        this.basePrice = basePrice;
        this.calculator =
                java.util.Objects.requireNonNull(calculator, "calculator");
    }

    int totalWithShipping(int shippingFee) {
        return calculator.total(basePrice, shippingFee);
    }
}

public class OrderDelegationDemo {
    public static void main(String[] args) {
        PriceCalculator calculator = new PriceCalculator();
        Order order = new Order(100, calculator);

        System.out.println(order.totalWithShipping(15));
        System.out.println(order.totalWithShipping(30));
    }
}
```

```bash
javac OrderDelegationDemo.java
java OrderDelegationDemo
```

```text
115
130
```

**Vai trò:**

- `Order` sở hữu ngữ cảnh nghiệp vụ là `basePrice` và biết cần cung cấp `totalWithShipping`.
- `PriceCalculator` thực hiện phép tính và kiểm tra overflow.
- `Order` không cần biết chi tiết phép cộng nằm ở đâu; nó **ủy quyền** cho calculator.
- Caller sử dụng `Order.totalWithShipping(...)`, không cần tự hỏi giá nằm trong field nào.
- Dependency truyền qua constructor nên không phải tạo mới `PriceCalculator` mỗi lần `totalWithShipping` được gọi.

Việc dùng `Math.addExact` khiến overflow ném `ArithmeticException` thay vì âm thầm wrap số `int`; đó là contract kỹ thuật của component. Delegator có thể để exception lan truyền khi behavior ấy phù hợp API.

## 6. Vì sao không cho caller lấy thẳng component rồi tự gọi?

So sánh hai API:

**API làm lộ component:**

```java
Engine engine() {
    return engine;
}
```

Caller viết `car.engine().start()`. Khi đó caller biết `Car` sử dụng `Engine` và phụ thuộc vào API `Engine`.

**API ủy quyền có chủ đích:**

```java
void start() {
    engine.start();
}
```

Caller viết `car.start()`, không cần biết một engine cụ thể được tổ chức ra sao.

Đây là hai lựa chọn **phụ thuộc contract**, không phải một câu trả lời đúng cho mọi hệ thống:

- Nếu khách hàng chỉ cần “khởi động xe”, `car.start()` giúp che chi tiết và giữ invariant.
- Nếu hệ thống thực sự cần expose một engine component như API công khai có vòng đời riêng, getter có thể hợp lý, nhưng phải quản lý coupling/ownership.
- Nếu `Engine` mutable, trả trực tiếp reference có thể cho code bên ngoài gọi `engine.stop()` ở thời điểm bất hợp lệ đối với `Car`.

**Không nên mở một getter cho mọi component chỉ vì field là private.** Hãy công khai **hành vi phù hợp với đối tượng bao ngoài**.

## 7. Ủy quyền giúp bảo vệ bất biến của object bao ngoài

Giả sử `BankAccount` có một thành phần `Balance` lưu tiền. Nếu caller được sửa trực tiếp Balance object, có thể phá bất biến của BankAccount. Một API phù hợp cho phép BankAccount **kiểm soát điều kiện nghiệp vụ** rồi giao thao tác lưu số dư cho component.

Tệp **`ControlledDelegationDemo.java`**:

```java
final class Balance {
    private int amount;

    Balance(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial");
        }
        amount = initial;
    }

    int amount() {
        return amount;
    }

    void credit(int value) {
        amount = Math.addExact(amount, value);
    }

    void debit(int value) {
        amount = Math.subtractExact(amount, value);
    }
}

final class BankAccount {
    private final Balance balance;

    BankAccount(int initial) {
        balance = new Balance(initial);
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        balance.credit(amount);
    }

    void withdraw(int amount) {
        if (amount <= 0 || amount > balance.amount()) {
            throw new IllegalArgumentException("invalid withdrawal");
        }
        balance.debit(amount);
    }

    int balance() {
        return balance.amount();
    }
}

public class ControlledDelegationDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);

        account.deposit(30);
        account.withdraw(50);
        System.out.println("balance=" + account.balance());

        try {
            account.withdraw(200);
        } catch (IllegalArgumentException ex) {
            System.out.println("withdrawal rejected");
        }

        System.out.println("balance=" + account.balance());
    }
}
```

```bash
javac ControlledDelegationDemo.java
java ControlledDelegationDemo
```

```text
balance=80
withdrawal rejected
balance=80
```

`BankAccount.withdraw` kiểm tra số tiền trước khi giao cho `Balance.debit`. `Balance` không public và không được trả qua getter; caller không tự gọi `credit` hoặc `debit` mà phải dùng API nghiệp vụ của BankAccount.

**Điểm cần biết:** `Balance.credit`/`debit` không tự kiểm mọi invariant nếu được gọi bằng đối số tùy ý bởi code có quyền trong cùng package. Vì vậy đây là thiết kế với assumption **chỉ BankAccount điều phối các lời gọi**. Trong thư viện phức tạp, có thể thêm validation ngay trong `Balance` để component tự bảo vệ contract và giảm phụ thuộc vào mọi caller dùng đúng.

**Không suy ra transaction/concurrency:** example chỉ xử lý các lỗi được kiểm tra trong một luồng. Nếu nhiều thread rút tiền đồng thời, cần đồng bộ check-and-update hoặc immutable/atomic design thích hợp.

## 8. Tạo component trong constructor hay nhận qua constructor?

Hai cách thường thấy:

**Class tự tạo component:**

```java
class Car {
    private final Engine engine = new Engine();
}
```

**Nhận component từ caller:**

```java
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }
}
```

Khác biệt không chỉ về cú pháp:

| Khía cạnh | Tự tạo component | Inject qua constructor |
| --- | --- | --- |
| Ai chọn implementation? | Class bao ngoài | Caller/composition root |
| Mức gắn bó với concrete type | Thường cao hơn | Có thể thấp nếu dùng interface |
| Test bằng fake component | Có thể khó hơn | Dễ hơn |
| Quản lý vòng đời | Bao ngoài thường quản lý | Phải quy định ai sở hữu/đóng component |
| Nhiều instances dùng chung component? | Không mặc định | Caller có thể chia sẻ |
| Component có cấu hình riêng | Phải tự lấy config | Có thể được cung cấp từ ngoài |

**Không phải lúc nào dependency injection cũng tốt hơn.** Với một component nhỏ, chỉ dùng nội bộ, không cần hoán đổi implementation hoặc test riêng, tự tạo là hợp lý và đơn giản. Với collaborator có I/O, nhiều chiến lược hoặc cần thay trong tests, inject qua constructor thường giúp thiết kế rõ hơn.

### Validate dependency sớm

Viết:

```java
this.engine = java.util.Objects.requireNonNull(engine, "engine");
```

giúp thất bại ngay khi tạo `Car` nếu dependency null, thay vì chỉ gặp `NullPointerException` ở một lời gọi `start` xảy ra muộn. Tuy nhiên **non-null không bảo đảm collaborator đang hoạt động đúng**, thread-safe hoặc chưa đóng; những điều ấy cần contract khác.

## 9. Ủy quyền qua interface: thay implementation mà không sửa delegator

Một bước nâng cao là delegator giữ **interface**, thay vì concrete class.

Tệp **`StrategyDelegationDemo.java`**:

```java
interface ShippingCost {
    int cost(int weight);
}

final class StandardShipping implements ShippingCost {
    @Override
    public int cost(int weight) {
        if (weight <= 0) {
            throw new IllegalArgumentException("weight must be positive");
        }
        return weight <= 5 ? 10 : 20;
    }
}

final class ExpressShipping implements ShippingCost {
    @Override
    public int cost(int weight) {
        if (weight <= 0) {
            throw new IllegalArgumentException("weight must be positive");
        }
        return weight <= 5 ? 25 : 40;
    }
}

final class Checkout {
    private final ShippingCost shippingCost;

    Checkout(ShippingCost shippingCost) {
        this.shippingCost = java.util.Objects.requireNonNull(shippingCost);
    }

    int shipping(int weight) {
        return shippingCost.cost(weight);
    }
}

public class StrategyDelegationDemo {
    public static void main(String[] args) {
        Checkout normal = new Checkout(new StandardShipping());
        Checkout express = new Checkout(new ExpressShipping());

        System.out.println("normal=" + normal.shipping(3));
        System.out.println("express=" + express.shipping(3));
    }
}
```

```bash
javac StrategyDelegationDemo.java
java StrategyDelegationDemo
```

```text
normal=10
express=25
```

`Checkout` nhận một object theo interface `ShippingCost` và ủy quyền tính phí. **Cùng một code của Checkout** có thể dùng hai concrete implementations khác nhau.

### Delegation và Strategy pattern

Ví dụ trên đồng thời thể hiện ý tưởng **Strategy**: có một họ thuật toán cho phí vận chuyển, chọn implementation qua dependency. Mẫu Strategy **thường sử dụng delegation**, nhưng delegation là một kỹ thuật rộng hơn:

- `Car` giao việc cho Engine dù chỉ có một Engine implementation.
- `Checkout` giao việc cho ShippingCost và có nhiều strategies.
- Không phải mọi lời gọi ủy quyền đều cần interface.
- Không cần tạo interface cho mỗi helper class nếu chỉ có một implementation ổn định và không có nhu cầu abstraction.

Cách chọn tốt dựa vào **điểm biến thiên thật sự** của hệ thống.

## 10. Ủy quyền không phải kế thừa

Trong kế thừa, class con diễn đạt quan hệ **is-a**, ví dụ `ElectricCar extends Car` khi phù hợp contract. Với delegation/composition, class bao ngoài có một collaborator và dùng nó: **has-a**.

| Tiêu chí | Inheritance (`extends`) | Delegation qua component |
| --- | --- | --- |
| Quan hệ chính | is-a | has-a / uses-a |
| Tái sử dụng | Thừa hưởng behavior từ superclass | Gọi method của collaborator |
| Coupling | Phụ thuộc vào contract superclass/hierarchy | Phụ thuộc vào contract component |
| Thay behavior | Override instance method | Thay object component/strategy |
| Expose methods | Inherited accessible methods thường là một phần API | Chọn forwarding methods công khai |
| Có nhiều “nguồn chức năng”? | Chỉ một direct superclass class | Có thể giữ nhiều components |
| Lifecycle | Object subclass cũng là instance của superclass | Component có identity/lifecycle riêng |
| Runtime dispatch | Override theo receiver object | Gọi component, rồi dispatch theo runtime component |

**Đừng dùng `extends Engine` chỉ vì `Car` muốn gọi `start()` của Engine.** Một chiếc xe không phải là một động cơ. Viết `Car` có `Engine` và chuyển tiếp `start` phản ánh domain đúng hơn.

### Một bẫy kế thừa để tái sử dụng

```java
// Ý tưởng sai về mô hình:
// class Car extends Engine { }
// Car không có nghĩa là một loại Engine.
```

Đây là minh họa về thiết kế không phù hợp, **không phải tuyên bố Java cấm cú pháp**. Nếu các classes thực tế cho phép kế thừa về mặt compiler, code vẫn có thể biên dịch nhưng domain model không đúng.

**Nguyên tắc thường hữu ích:** “ưu tiên composition/delegation hơn inheritance” khi muốn **tái sử dụng hành vi mà không có quan hệ is-a thực sự**. Đây là guideline thiết kế, không phải luật cấm mọi inheritance.

## 11. Thế nào là forwarding method?

**Forwarding method** là method trong delegator gọi collaborator để thực hiện chức năng tương ứng, thường với tên/đối số gần giống.

```java
class PrinterFacade {
    private final Printer printer;

    PrinterFacade(Printer printer) {
        this.printer = printer;
    }

    void print(String text) {
        printer.print(text);
    }
}
```

Giả định interface `Printer` có `void print(String)`; đây là mảnh khai báo minh họa.

Nhưng forwarding **không nhất thiết phải một-một**:

```java
String displayName(User user) {
    return formatter.format(user.firstName(), user.lastName());
}
```

Ví dụ thứ hai là mảnh method dùng các types giả định; nó chọn hai giá trị từ object User rồi giao phần định dạng cho component. Nó vẫn là delegation dù tên method delegator khác tên method delegate và arguments được chuyển đổi.

### Ba kiểu chuyển tiếp phổ biến

1. **Chuyển tiếp nguyên trạng:** `return repository.find(id);`.
2. **Bao điều kiện nghiệp vụ:** validate input, phân quyền, trạng thái, sau đó gọi `delegate.execute(...)`.
3. **Kết hợp kết quả:** gọi một hoặc nhiều collaborators rồi xây đối tượng trả về phù hợp cho caller.

Delegator có thể **điều phối và bảo vệ contract**, không chỉ là lớp “chuyển tiếp vô nghĩa”.

## 12. Đừng expose toàn bộ API của component một cách vô điều kiện

Nếu object bao ngoài chỉ hứa cho client `addProduct` và `checkout`, việc đưa ra mọi method của một mutable list hoặc repository làm API có thể khiến caller phá invariant.

Ví dụ nguy hiểm:

```java
class Cart {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    java.util.List<String> items() {
        return items;
    }
}
```

Nếu caller nhận list thật qua `cart.items()`, nó có thể `clear`/`add` trực tiếp mà Cart không validate. Dù field `items` là `private final`, object `ArrayList` vẫn mutable.

Một thiết kế có chủ đích:

```java
class Cart {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    void add(String item) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("item required");
        }
        items.add(item);
    }

    java.util.List<String> snapshot() {
        return java.util.List.copyOf(items);
    }
}
```

`Cart.add` giao việc lưu phần tử cho `List.add` sau validation. `snapshot` giao việc sao chép dữ liệu cho thư viện collection; caller không nhận mutable list nội bộ.

**Đó cũng là delegation**: `Cart` sử dụng capability của `ArrayList`, nhưng **giữ quyền quyết định API** mà bên ngoài được thấy.

## 13. Wrapper và Decorator: những trường hợp sử dụng delegation

Một **wrapper** giữ một object khác và chuyển tiếp lời gọi; nó có thể thêm validation, logging, metrics, access control hoặc thay đổi contract. **Decorator pattern** là một mẫu wrapper có ý định thêm hành vi mà vẫn cung cấp giao diện tương thích.

Tệp **`DecoratorDelegationDemo.java`**:

```java
interface Notifier {
    void send(String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("send:" + message);
    }
}

final class LoggingNotifier implements Notifier {
    private final Notifier delegate;

    LoggingNotifier(Notifier delegate) {
        this.delegate = java.util.Objects.requireNonNull(delegate);
    }

    @Override
    public void send(String message) {
        System.out.println("before-send");
        delegate.send(message);
        System.out.println("after-send");
    }
}

public class DecoratorDelegationDemo {
    public static void main(String[] args) {
        Notifier notifier =
                new LoggingNotifier(new ConsoleNotifier());

        notifier.send("hello");
    }
}
```

```bash
javac DecoratorDelegationDemo.java
java DecoratorDelegationDemo
```

```text
before-send
send:hello
after-send
```

Ở đây:

- `LoggingNotifier` **implements cùng interface** `Notifier`, nên caller có thể dùng nó thay ConsoleNotifier theo contract.
- Nó **không extends ConsoleNotifier**; nó giữ một `Notifier` trong field `delegate`.
- `send` thêm hành vi log trước và sau rồi **ủy quyền** cho collaborator.
- Caller không cần biết lớp decorator lồng bao nhiêu tầng.

**Lưu ý lỗi:** nếu `delegate.send(message)` ném exception, dòng `after-send` **không chạy** ở code hiện tại. Nếu muốn log cả thất bại, phải thiết kế `try/finally` hay bắt exception đúng contract. Không được ghi log “đã gửi thành công” khi component thực sự thất bại.

## 14. Bao và chuyển tiếp interface methods: chính sách `@Override`

Khi wrapper implements một interface, những phương thức interface cần triển khai phải có access hợp lệ, thường là `public` đối với methods của public interface.

Ví dụ:

```java
interface ClockSource {
    long millis();
}

class FixedClock implements ClockSource {
    @Override
    public long millis() {
        return 1000L;
    }
}
```

`FixedClock` có thể package-private, nhưng implementation method `millis` phải `public` do nó triển khai contract interface tương ứng.

Nếu wrapper implements `ClockSource`:

```java
class MonitoredClock implements ClockSource {
    private final ClockSource delegate;

    MonitoredClock(ClockSource delegate) {
        this.delegate = delegate;
    }

    @Override
    public long millis() {
        return delegate.millis();
    }
}
```

`@Override` giúp compiler xác nhận method đúng chữ ký; nó **không tự sinh việc chuyển tiếp**. Developer vẫn phải viết lời gọi collaborator trong thân method.

**Không suy rằng** chỉ cần ghi `implements SomeInterface` là tất cả lời gọi tự chuyển sang field `delegate`. Java không có automatic delegation for ordinary classes theo cú pháp `by` của một số ngôn ngữ khác.

## 15. Một component có thể hỗ trợ nhiều methods; delegator chỉ chọn những gì cần

Một `List` có nhiều operations như `add`, `remove`, `clear`, `set`, `get`. Một class quản lý danh sách có thể quyết định chỉ expose:

- `addValidItem(String)`: có validation.
- `count()`: truy vấn số lượng.
- `snapshot()`: bản sao không chỉnh sửa được.

Không cần viết một forwarding method cho **mọi** method của List.

Tệp **`SelectiveDelegationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class GuestList {
    private final List<String> guests = new ArrayList<>();

    void register(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("invalid guest");
        }
        if (guests.contains(name)) {
            throw new IllegalArgumentException("duplicate guest");
        }
        guests.add(name);
    }

    int size() {
        return guests.size();
    }

    List<String> snapshot() {
        return List.copyOf(guests);
    }
}

public class SelectiveDelegationDemo {
    public static void main(String[] args) {
        GuestList list = new GuestList();

        list.register("An");
        list.register("Binh");

        System.out.println("count=" + list.size());
        System.out.println(list.snapshot());
    }
}
```

```bash
javac SelectiveDelegationDemo.java
java SelectiveDelegationDemo
```

```text
count=2
[An, Binh]
```

`GuestList` **ủy quyền lưu và truy vấn** cho `ArrayList`, nhưng không cho caller tự ý `clear` hoặc thay slot. Chúng ta giữ **độ hạt API phù hợp domain**.

Nếu caller cần tính năng xóa người đã đăng ký, thêm method có tên/các điều kiện nghiệp vụ cụ thể; không cần mở hết mutable list.

## 16. Nhiều components: chia việc theo chuyên môn

Một class có thể giữ **nhiều collaborators** và điều phối chúng, mỗi collaborator phụ trách phần việc cụ thể.

Ví dụ xử lý checkout:

```text
CheckoutService
   |
   +-- PriceCalculator       -> tính tổng
   |
   +-- PaymentGateway        -> yêu cầu thanh toán
   |
   +-- ReceiptFormatter      -> định dạng biên nhận
```

Nếu viết tất cả logic vào `CheckoutService`, class có thể quá nhiều trách nhiệm. Nếu chia thành ba collaborators rồi thực hiện delegation, từng thành phần trở nên dễ kiểm tra và thay thế hơn.

### Ví dụ runnable không dùng dịch vụ ngoài

Tệp **`MultiComponentDelegationDemo.java`**:

```java
final class PriceCalculator {
    int total(int base, int shipping) {
        if (base < 0 || shipping < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return Math.addExact(base, shipping);
    }
}

final class PaymentGateway {
    boolean pay(int amount) {
        System.out.println("charged=" + amount);
        return true;
    }
}

final class ReceiptFormatter {
    String format(int amount) {
        return "receipt:" + amount;
    }
}

final class CheckoutService {
    private final PriceCalculator calculator;
    private final PaymentGateway gateway;
    private final ReceiptFormatter formatter;

    CheckoutService(PriceCalculator calculator,
                    PaymentGateway gateway,
                    ReceiptFormatter formatter) {
        this.calculator =
                java.util.Objects.requireNonNull(calculator);
        this.gateway = java.util.Objects.requireNonNull(gateway);
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    String checkout(int base, int shipping) {
        int total = calculator.total(base, shipping);
        if (!gateway.pay(total)) {
            throw new IllegalStateException("payment rejected");
        }
        return formatter.format(total);
    }
}

public class MultiComponentDelegationDemo {
    public static void main(String[] args) {
        CheckoutService service = new CheckoutService(
                new PriceCalculator(),
                new PaymentGateway(),
                new ReceiptFormatter());

        System.out.println(service.checkout(100, 15));
    }
}
```

```bash
javac MultiComponentDelegationDemo.java
java MultiComponentDelegationDemo
```

```text
charged=115
receipt:115
```

**Chú ý giới hạn của ví dụ:** `PaymentGateway` ở đây chỉ là một fake đơn giản trong RAM/in console và luôn trả true; không phải cổng thanh toán thực. Trong hệ thống thật, thanh toán, lưu database và gửi event có thể có **side effects không tự rollback** nếu formatter hoặc bước sau thất bại. Delegation **không tự cung cấp transaction** cho nhiều collaborators.

## 17. Delegator có thể biến đổi arguments hoặc kết quả

Ủy quyền không nhất thiết là gọi nguyên xi với cùng parameter list. Delegator có thể:

- Chuẩn hóa input trước khi chuyển tiếp.
- Kiểm tra quyền truy cập.
- Biến đổi đơn vị đo, DTO hoặc domain value.
- Kết hợp kết quả từ nhiều calls.
- Chuyển output về một abstraction phù hợp caller.

Tệp **`TransformingDelegationDemo.java`**:

```java
final class TemperatureConverter {
    double celsiusToFahrenheit(double celsius) {
        return celsius * 9.0 / 5.0 + 32.0;
    }
}

final class WeatherDisplay {
    private final TemperatureConverter converter =
            new TemperatureConverter();

    String displayFahrenheit(double celsius) {
        double fahrenheit = converter.celsiusToFahrenheit(celsius);
        return String.format(java.util.Locale.ROOT, "%.1f F", fahrenheit);
    }
}

public class TransformingDelegationDemo {
    public static void main(String[] args) {
        WeatherDisplay display = new WeatherDisplay();
        System.out.println(display.displayFahrenheit(0));
        System.out.println(display.displayFahrenheit(100));
    }
}
```

```bash
javac TransformingDelegationDemo.java
java TransformingDelegationDemo
```

```text
32.0 F
212.0 F
```

Ở đây `WeatherDisplay` không chỉ chuyển tiếp kết quả `double`; nó giao phép đổi nhiệt độ cho `TemperatureConverter` rồi tạo format string phục vụ nhu cầu hiển thị. Nếu interface bên ngoài nên trả một value object thay vì string, đó là một quyết định thiết kế khác.

## 18. Ủy quyền không tự đồng nghĩa “method 100% thuần”

Một delegator có thể gọi collaborator gây side effect:

```java
void send(String message) {
    notifier.send(message);
}
```

Nếu `notifier` gửi email hoặc viết file, cuộc gọi có tác động ra ngoài. Dù `send` chỉ có một dòng code, class bao ngoài vẫn phải chịu trách nhiệm về **contract công khai**:

- Nếu input không hợp lệ, có nên từ chối trước khi gửi?
- Nếu collaborator trả về false, caller nhận gì?
- Nếu collaborator ném exception, có retry không?
- Sau exception, thao tác đã thành công một phần hay chưa?
- Có cần log/metrics/audit?
- Có thể gọi lại an toàn không?

**Đừng dùng một forwarding method để che giấu lỗi hệ thống mà caller cần biết.** Việc chuyển tiếp ngắn không làm cho side effect biến mất.

## 19. Xử lý exception khi delegate thất bại

Một chiến lược đơn giản: **để exception lan truyền** khi nó phù hợp với contract của delegator.

```java
int total(int price, int fee) {
    return calculator.total(price, fee);
}
```

Nếu calculator ném `IllegalArgumentException` do negative input và đó cũng là contract của `total`, delegator không cần `try/catch` vô ích.

Khi muốn cung cấp một lỗi ở cấp abstraction phù hợp:

```java
String load(String id) {
    try {
        return repository.read(id);
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("Cannot load " + id, ex);
    }
}
```

Đây là **mảnh method minh họa**, giả định `repository.read` khai báo ném `IOException`. Constructor `IllegalStateException(String, Throwable)` giữ **cause** để chẩn đoán.

**Bẫy:**

- Không viết `catch (Exception ex) { return null; }` chỉ để làm caller hết lỗi; nó có thể che dữ liệu hỏng/side effect.
- Không tự retry một method có tác động thanh toán, ghi DB hoặc gửi message nếu chưa có idempotency contract.
- Nếu delegator thực hiện mutation trước khi gọi collaborator và collaborator fail, object bao ngoài có thể ở trạng thái dở dang. Hãy cân nhắc validate/compute-before-commit, rollback hoặc transaction đúng phạm vi.
- Nếu delegate trả kết quả có thể null, delegator phải quyết định có chấp nhận null, wrap trong `Optional` hay ném lỗi — không tự suy “delegate luôn trả object”.

## 20. Một ví dụ “gọi rồi thất bại” cho thấy cần chọn thứ tự

Giả sử:

```java
void placeOrder(Order order) {
    order.markPaid();
    gateway.charge(order.total()); // Có thể lỗi.
}
```

Đây là **mảnh giả định về API**, không phải chương trình chạy độc lập. Nếu `charge` thất bại sau `markPaid`, object Order đã chuyển sang trạng thái đã thanh toán dù payment chưa thực hiện.

Có thể cải thiện bằng cách thiết kế ranh giới nghiệp vụ:

1. Validate request/order trước.
2. Xác định trạng thái nào được coi là **committed**.
3. Giao thao tác thanh toán cho gateway.
4. Cập nhật order state theo **kết quả đáng tin** của giao dịch.
5. Nếu có DB và gateway ngoài tiến trình, dùng patterns như outbox/idempotency/saga khi phù hợp.

Delegation giúp **phân tách nơi thực hiện công việc**, nhưng **không thay thế việc điều phối trạng thái nhất quán**.

## 21. Quản lý ownership và vòng đời component

Một field `private final Repository repository` không nói rõ ai **sở hữu** repository. Có ít nhất hai tình huống:

**(A) Object bao ngoài tự tạo và quản lý component:**

```java
class ReportService {
    private final Formatter formatter = new Formatter();
}
```

**(B) Object bao ngoài mượn/shared dependency từ caller:**

```java
class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = formatter;
    }
}
```

Hai đoạn là **minh họa**, giả định có `Formatter`. Cần mô tả rõ:

- Ai được phép thay đổi cấu hình component?
- Component có được share giữa nhiều delegators?
- Component có thread-safe không?
- Ai tạo/đóng resource nếu implement `AutoCloseable`?
- Nếu outer object hết vòng đời, component còn được dùng ở nơi khác không?

### Ví dụ với resource

Nếu một delegator nhận `java.io.Writer` do caller cung cấp, delegator **không nên tự ý `close()`** ở mọi method trừ khi API nói rõ delegator sở hữu Writer. Ngược lại nếu chính delegator tạo resource và hứa quản lý lifecycle, nó phải có cơ chế cleanup phù hợp.

**Không áp dụng máy móc:** “composition luôn phải close mọi component”, hoặc “dependency injection luôn không được close”. Ownership là **hợp đồng kiến trúc** cần được định nghĩa cụ thể.

## 22. Delegation và tham chiếu `final`

Một pattern thường gặp:

```java
private final PaymentGateway gateway;
```

`final` mang ý nghĩa field `gateway` không gán lại sau construction hợp lệ, giúp chắc chắn delegator tiếp tục dùng **cùng tham chiếu collaborator**.

Nhưng:

- Object gateway vẫn có thể mutable, có cache, connection pool hoặc counters.
- Nếu component có setters được gọi từ nơi khác, hành vi của delegator có thể thay đổi dù field final.
- `final` không làm method calls thread-safe.
- `final` không ngăn component bị close ở một nơi khác khi có shared ownership.
- Nếu cần thay strategy runtime, có thể dùng phương án state management riêng hoặc tạo delegator mới với dependency khác.

Trong nhiều thiết kế, **constructor injection + private final field** là một mặc định tốt khi collaborator không cần thay sau construction, nhưng đây là quyết định API, không phải yêu cầu bắt buộc của delegation.

## 23. Tránh aliasing mutable state không được kiểm soát

Tệp **`SharedComponentDemo.java`**:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int get() {
        return value;
    }
}

class Dashboard {
    private final Counter counter;

    Dashboard(Counter counter) {
        this.counter = counter;
    }

    void record() {
        counter.increment();
    }

    int total() {
        return counter.get();
    }
}

public class SharedComponentDemo {
    public static void main(String[] args) {
        Counter shared = new Counter();

        Dashboard first = new Dashboard(shared);
        Dashboard second = new Dashboard(shared);

        first.record();
        second.record();

        System.out.println(first.total());
        System.out.println(second.total());
    }
}
```

```bash
javac SharedComponentDemo.java
java SharedComponentDemo
```

```text
2
2
```

Hai Dashboard objects **chung một Counter component**, vì caller truyền cùng reference `shared` vào constructors. Do vậy cả hai cùng nhìn thấy count=2.

Nếu mục tiêu là **mỗi dashboard có bộ đếm riêng**, cần tạo riêng hai Counter objects (hoặc đặt counter trong constructor private và không chia sẻ). Nếu mục tiêu là **bộ đếm dùng chung**, hành vi là chủ đích nhưng phải tính concurrency.

**Delegation không tự quy định ownership, identity hoặc sharing.** Hãy kiểm tra nơi tạo và cách truyền component.

## 24. Kiểm thử delegation bằng fake collaborator

Một lợi ích của thiết kế có collaborator injection là ta có thể dùng fake để **xác minh delegator có gọi đúng dependency hay không** mà không cần mạng, DB hoặc framework mocking.

Tệp **`DelegationTestDemo.java`**:

```java
interface MessageSender {
    void send(String text);
}

final class FakeSender implements MessageSender {
    int calls;
    String lastMessage;

    @Override
    public void send(String text) {
        calls++;
        lastMessage = text;
    }
}

final class GreetingService {
    private final MessageSender sender;

    GreetingService(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }

    void greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        sender.send("Hello " + name);
    }
}

public class DelegationTestDemo {
    public static void main(String[] args) {
        FakeSender fake = new FakeSender();
        GreetingService service = new GreetingService(fake);

        service.greet("An");

        if (fake.calls != 1 || !"Hello An".equals(fake.lastMessage)) {
            throw new AssertionError("delegation failed");
        }

        System.out.println("calls=" + fake.calls);
        System.out.println("message=" + fake.lastMessage);
    }
}
```

```bash
javac DelegationTestDemo.java
java DelegationTestDemo
```

```text
calls=1
message=Hello An
```

Test xác nhận:

1. `GreetingService.greet("An")` có gọi sender.
2. Lời gọi xảy ra **một lần**.
3. Argument được chuyển tiếp đúng.
4. Không cần tạo email client hoặc service thật.

Đây là một **fake test thủ công bằng `main`**, không phải JUnit. Trong dự án thật, có thể dùng JUnit và mocks khi có ích. Đừng chỉ test “đã gọi method” mà bỏ qua **kết quả/hợp đồng quan sát được** của nghiệp vụ.

## 25. Kiểm tra cả đường thất bại: delegate ném exception

Một fake collaborator có thể được thiết kế để ném exception, từ đó xác nhận cách delegator xử lý lỗi.

Tệp **`DelegationFailureDemo.java`**:

```java
interface Sender {
    void send(String message);
}

final class FailingSender implements Sender {
    @Override
    public void send(String message) {
        throw new IllegalStateException("network unavailable");
    }
}

final class AlertService {
    private final Sender sender;

    AlertService(Sender sender) {
        this.sender = sender;
    }

    void alert(String message) {
        sender.send("ALERT:" + message);
    }
}

public class DelegationFailureDemo {
    public static void main(String[] args) {
        AlertService service = new AlertService(new FailingSender());

        try {
            service.alert("disk full");
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getMessage());
        }
    }
}
```

```bash
javac DelegationFailureDemo.java
java DelegationFailureDemo
```

```text
failure=network unavailable
```

`AlertService.alert` không bắt exception; nó lan ra caller theo semantics Java. Đây là hành vi hợp lệ nếu contract của AlertService muốn caller biết lỗi. Với một API khác, ta có thể bọc exception vào error type riêng hoặc trả trạng thái lỗi rõ ràng; quan trọng là **không tuyên bố thông báo đã gửi khi collaborator thất bại**.

## 26. Nhiều tầng delegation và tracing lời gọi

Delegation có thể được tổ chức thành nhiều tầng:

```text
API Controller
    |
    v
OrderService
    |
    v
OrderRepository
    |
    v
Storage Client
```

Mỗi tầng có vai trò khác nhau. Đây là một cách xây **layered architecture**, nhưng không phải cứ nhiều tầng càng tốt.

Tệp **`DelegationChainDemo.java`**:

```java
class Storage {
    String load(String key) {
        System.out.println("Storage.load");
        return "value:" + key;
    }
}

class Repository {
    private final Storage storage = new Storage();

    String find(String key) {
        System.out.println("Repository.find");
        return storage.load(key);
    }
}

class Service {
    private final Repository repository = new Repository();

    String get(String key) {
        System.out.println("Service.get");
        return repository.find(key);
    }
}

public class DelegationChainDemo {
    public static void main(String[] args) {
        Service service = new Service();

        System.out.println(service.get("A"));
    }
}
```

```bash
javac DelegationChainDemo.java
java DelegationChainDemo
```

```text
Service.get
Repository.find
Storage.load
value:A
```

Chuỗi này giúp quan sát **delegator nào gọi collaborator nào**, và dữ liệu kết quả đi ngược lên như thế nào. Nếu chỉ có một hành vi đơn giản, việc tạo 3 lớp chỉ để chuyển tiếp có thể **overengineering**; chọn số tầng theo trách nhiệm thực và yêu cầu thay đổi.

### Vòng ủy quyền nguy hiểm

Nếu `A.process()` gọi `B.process()` và `B.process()` lại gọi `A.process()` mà không có điểm dừng, chương trình có thể đệ quy vô hạn và gặp `StackOverflowError`. Một vòng object references không tự là lỗi, nhưng **vòng delegation trong call flow không có điều kiện dừng** là vấn đề.

Hãy xác định **hướng phụ thuộc** và đảm bảo một method kết thúc ở component thực hiện công việc thật, không chỉ đẩy trách nhiệm vòng quanh.

## 27. Ủy quyền và đa hình động của component

Nếu field của delegator có type là interface, lời gọi `delegate.method()` có thể dispatch đến concrete implementation theo runtime object:

```java
interface Formatter {
    String format(String name);
}

class UppercaseFormatter implements Formatter {
    @Override
    public String format(String name) {
        return name.toUpperCase(java.util.Locale.ROOT);
    }
}

class FormatterService {
    private final Formatter formatter;

    FormatterService(Formatter formatter) {
        this.formatter = formatter;
    }

    String show(String name) {
        return formatter.format(name);
    }
}
```

Đây là class/interface declarations hợp lệ, chưa có `main`.

- Bản thân **delegation** là việc `FormatterService.show` gọi `formatter.format`.
- **Polymorphism** chọn concrete implementation của `format` dựa trên runtime type của object Formatter.
- **Composition** là việc giữ Formatter qua field.
- Ba yếu tố này phối hợp nhưng không đồng nghĩa.

Nếu collaborator method là **static**, nó không được runtime dispatch như instance override. Các static utility calls như `Math.max(...)` là **sử dụng static helper**, không phải hình thức “ủy quyền instance qua component” mà ta đang tập trung ở đây.

## 28. Concurrency: delegator không tự làm component thread-safe

Nếu một mutable component dùng chung giữa nhiều delegators hoặc nhiều threads, những operations cần bảo vệ không tự an toàn chỉ vì gọi qua wrapper.

Ví dụ nguy cơ:

```java
class Counter {
    private int count;

    void increase() {
        count++;
    }
}
```

Hai threads gọi `dashboard.record()` trên chung Counter có thể gây lost updates vì `count++` không phải một read-modify-write atomic operation.

Một phiên bản component dùng atomic type:

```java
class Counter {
    private final java.util.concurrent.atomic.AtomicInteger count =
            new java.util.concurrent.atomic.AtomicInteger();

    void increase() {
        count.incrementAndGet();
    }

    int value() {
        return count.get();
    }
}
```

Hai đoạn `Counter` là **các phương án thay thế**, không đặt đồng thời trong cùng source set.

**Không nhầm:**

- `private final Counter counter` cố định reference, không tự bảo vệ `counter.increase()`.
- `synchronized` trong một delegator không đủ nếu nơi khác gọi trực tiếp cùng component ngoài monitor ấy.
- Một operation gồm nhiều calls tới component có thể cần atomicity của **cả chuỗi nghiệp vụ**, không chỉ atomicity từng call.
- Nếu component được share, policy về concurrency cần thống nhất giữa mọi callers.

## 29. Tránh “thần đối tượng” chỉ làm việc của tất cả thành phần

Một delegator tốt chỉ điều phối những trách nhiệm phù hợp. Nhưng nếu mọi operation trong hệ thống đi qua một class `ApplicationManager` với hàng trăm forwarding methods, class có thể trở thành **god object**.

Dấu hiệu:

- Method công khai chỉ có tên chung chung như `doTask1`, `doTask2`.
- Object bao ngoài giữ quá nhiều unrelated components.
- Client chỉ cần một chức năng nhỏ vẫn phải import một manager lớn.
- Mỗi thay đổi một domain đều phải sửa manager.
- API surface của component bị sao chép nguyên xi dù không cần.

Cách cải thiện:

1. Gom components theo **ranh giới domain/use case**.
2. Delegator nên cung cấp **hành vi đúng cấp abstraction**.
3. Nếu client cần dùng trực tiếp collaborator hợp pháp, có thể inject chính collaborator/interface thay vì bắt đi qua manager.
4. Không tạo forwarding layer nếu nó không đem lại invariant, lifecycle, security boundary, orchestration hoặc API stability có giá trị.

**Delegation không phải mục tiêu tự thân.** Nó là kỹ thuật giúp đối tượng phối hợp có trách nhiệm rõ ràng.

## 30. Khi nào nên chọn delegation thay vì inheritance?

Một checklist nhanh:

- Nếu đối tượng A **không phải một loại** đối tượng B, đừng `extends B` chỉ để gọi method.
- Nếu A cần sử dụng **một phần khả năng** của B, field component + method forwarding thường phù hợp.
- Nếu cần **thay cách thực hiện** ở runtime hoặc trong tests, inject interface collaborator.
- Nếu cần **thêm behavior** trước/sau một method nhưng vẫn giữ cùng interface, wrapper/decorator có thể phù hợp.
- Nếu chỉ dùng helper stateless phổ quát như `Math.abs`, có thể gọi static method trực tiếp, không nhất thiết tạo component.
- Nếu A thực sự là subtype của B theo mọi expectation của client, inheritance/interface implementation có thể vẫn phù hợp.
- Nếu component cần lifecycle riêng, hãy quyết định ownership trước.
- Nếu API bao ngoài phải bảo vệ invariant, đừng expose mutable collaborator bừa bãi.

### Câu hỏi quan trọng

> “Client nên nói với đối tượng A: *hãy thực hiện hành vi nghiệp vụ này*, hay client cần biết B và tự điều phối mọi phương thức B?”

Nếu câu trả lời là hành vi ở cấp A, hãy cân nhắc API `A.operation()` ủy quyền cho B bên trong. Nếu client thực sự là consumer hợp lệ của B, đôi khi đưa B trực tiếp qua dependency injection sẽ đơn giản hơn.

## 31. Những lỗi thường gặp

| Sai lầm | Vì sao sai / nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Dùng `extends` chỉ để tái sử dụng utility method | Mô hình is-a không đúng | Dùng component hoặc helper thích hợp |
| Tưởng field component tự động tạo delegation | Java không tự chuyển tiếp method | Viết forwarding method tường minh |
| Trả mutable component qua getter công khai | Caller có thể bypass invariant | Expose behavior hoặc snapshot |
| Khai báo `final` field rồi tin component immutable | Final chỉ cố định reference | Thiết kế mutability/ownership riêng |
| Tạo component trong mỗi lần gọi dù có state cần giữ | State có thể mất và tốn resource | Giữ field/cấu hình lifecycle đúng |
| Tạo một static shared component cho mọi instance ngoài ý muốn | Shared mutable state khó kiểm soát | Instance dependency hoặc inject có chủ đích |
| Không kiểm null dependency ở constructor | Lỗi muộn và khó hiểu | `Objects.requireNonNull` khi phù hợp |
| Wrapper implements interface nhưng giảm method access | Interface method contract yêu cầu public | Dùng `public`/`@Override` đúng |
| Đổi chữ ký khi forward mà không nói rõ | Caller không biết behavior/validation | Thiết kế API và document rõ |
| Swallow exception từ collaborator | Che thất bại, state không rõ | Lan truyền hoặc chuyển lỗi có cause |
| Retry operation ngoài hệ thống vô điều kiện | Side effect có thể lặp | Idempotency/retry contract |
| Tạo vòng A→B→A không điểm dừng | Có thể stack overflow | Phá vòng, phân tách trách nhiệm |
| Coi wrapper thread-safe vì có field final | Mutable delegate vẫn có race | Đồng bộ/atomic theo contract |
| Quá nhiều forwarding layers vô nghĩa | Coupling và độ phức tạp tăng | Chỉ thêm layer khi có giá trị |
| Test chỉ kiểm output mà không kiểm gọi delegate ở behavior quan trọng | Dễ forward sai argument | Test behavior + fake collaborator |
| Test chỉ kiểm invocation mà không kiểm invariant | Miss lỗi domain | Test kết quả, lỗi và state |
| Một collaborator đóng resource do caller sở hữu | Phá ownership | Định nghĩa rõ ai close |
| Lạm dụng interface cho từng helper | Over-abstraction | Chỉ tạo interface khi có contract/variation thực |
| Đoán delegation luôn có transaction | Mỗi component có failure modes riêng | Orchestrate transaction/compensation |
| Nhầm delegation với aggregation | Một cái là call behavior, cái kia mô tả object relation | Phân biệt cấu trúc và hành vi |

## 32. Bài thực hành tổng hợp: ủy quyền cho đối tượng lưu trữ

Bài toán: thiết kế `Library` cho phép caller đăng ký một tựa sách và hỏi số lượng, nhưng không được trực tiếp mutate dữ liệu lưu trữ. `Library` giữ một component `BookStore` chuyên trách việc lưu.

Tệp **`LibraryDelegationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class BookStore {
    private final List<String> titles = new ArrayList<>();

    void add(String title) {
        titles.add(title);
    }

    boolean contains(String title) {
        return titles.contains(title);
    }

    int count() {
        return titles.size();
    }

    List<String> snapshot() {
        return List.copyOf(titles);
    }
}

final class Library {
    private final BookStore store;

    Library(BookStore store) {
        this.store = Objects.requireNonNull(store);
    }

    void register(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title required");
        }
        String normalized = title.trim();

        if (store.contains(normalized)) {
            throw new IllegalArgumentException("duplicate title");
        }

        store.add(normalized);
    }

    int numberOfBooks() {
        return store.count();
    }

    List<String> catalog() {
        return store.snapshot();
    }
}

public class LibraryDelegationDemo {
    public static void main(String[] args) {
        Library library = new Library(new BookStore());

        library.register(" Java Core ");
        library.register("Clean Code");

        System.out.println("count=" + library.numberOfBooks());
        System.out.println("catalog=" + library.catalog());

        try {
            library.register("Java Core");
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate rejected");
        }

        System.out.println("count=" + library.numberOfBooks());
    }
}
```

```bash
javac LibraryDelegationDemo.java
java LibraryDelegationDemo
```

```text
count=2
catalog=[Java Core, Clean Code]
duplicate rejected
count=2
```

**Phân tích trách nhiệm:**

- `BookStore` thực hiện lưu/truy vấn danh sách.
- `Library` sở hữu các quy tắc domain: title không trống, loại bỏ whitespace đầu cuối, không chấp nhận duplicate.
- `Library.register` **ủy quyền `contains` và `add`** cho store sau khi kiểm tra.
- `numberOfBooks` **ủy quyền `count`**.
- `catalog` ủy quyền tạo snapshot, không trả mutable list gốc.
- Caller chỉ thấy API Library, không cần tự gọi BookStore methods.

**Điểm mở rộng:** Nếu `BookStore` được chia sẻ cho nhiều Library objects hoặc nhiều threads, cần đồng bộ hóa thao tác `contains` + `add` để tránh race/duplicate. Ví dụ một luồng này không tự giải quyết atomicity.

## 33. Bài tập cải tiến từ ví dụ thư viện

Sau khi chạy `LibraryDelegationDemo`, hãy thử:

1. Thêm method `unregister(String)` vào `Library` với validation rõ, ủy quyền xóa cho store.
2. Đổi `BookStore` thành interface `CatalogStore` có `add`, `contains`, `count`, `snapshot`; tạo `InMemoryCatalogStore` để implement.
3. Viết `FakeCatalogStore` ghi nhận argument được truyền, test `Library.register` có trim title.
4. Thêm điều kiện tối đa ba titles; đặt validation ở API Library, kiểm tra lỗi không sửa danh sách.
5. Thử trả list mutable nội bộ qua getter, quan sát vì sao caller có thể phá invariant.
6. Nếu hai threads cùng đăng ký cùng title, thiết kế lại check-and-add thành operation atomic trong component hoặc phối hợp khóa.
7. Nếu store thực sự truy cập database, xác định hợp đồng về lỗi I/O, transaction và lifecycle.

### Gợi ý kiến trúc sau cải tiến

```text
Client
  |
  | library.register("Java")
  v
Library
  |
  | catalogStore.registerIfAbsent("Java")
  v
CatalogStore interface
  |
  +-- InMemoryCatalogStore
  |
  +-- DatabaseCatalogStore
```

Thao tác `registerIfAbsent` được thiết kế như một operation đơn nhất ở component có thể giúp tránh việc delegator phải tách `contains` và `add` trong môi trường đồng thời. Khi dùng database, triển khai còn cần constraint/index/transaction phù hợp.

## 34. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** Một class A có field B nhưng chưa gọi method B bao giờ. Có chắc đã sử dụng delegation chưa?

**Đáp án:** Chưa chắc. A có **quan hệ tham chiếu/component**, nhưng delegation nói về việc A giao thực hiện behavior cho B.

**Câu 2.** `car.start()` gọi `engine.start()` bên trong. Receiver của lời gọi bên ngoài và bên trong là một object?

**Đáp án:** Không. Bên ngoài receiver là Car object; bên trong receiver là Engine object.

**Câu 3.** Delegation bắt buộc dùng interface không?

**Đáp án:** Không. Có thể ủy quyền cho concrete class; interface hữu ích khi có contract trừu tượng hoặc cần thay implementation.

**Câu 4.** Dùng `private final Engine engine` có làm Engine state immutable không?

**Đáp án:** Không. Final chỉ cố định field reference; Engine vẫn có thể mutate.

**Câu 5.** Có phải class có component nên expose getter trả thẳng component không?

**Đáp án:** Không. Cân nhắc API ở cấp domain và nguy cơ caller bypass invariant.

**Câu 6.** Tại sao `Car extends Engine` thường không phù hợp?

**Đáp án:** Car **có** engine, không phải một loại engine. Delegation biểu diễn has-a đúng hơn inheritance is-a.

**Câu 7.** Một wrapper implements interface `Notifier` và gọi `delegate.send()` có phải decorator không?

**Đáp án:** Có thể là decorator khi wrapper giữ cùng contract và thêm behavior; nếu chỉ chuyển tiếp nguyên xi, có thể chỉ là forwarding wrapper.

**Câu 8.** `@Override` trên forwarding method có tự tạo code gọi collaborator không?

**Đáp án:** Không. Developer phải viết body.

**Câu 9.** Một component bị inject qua constructor, ai phải đóng nó?

**Đáp án:** Phụ thuộc ownership contract; không thể suy chỉ từ injection. Phải quy định ai sở hữu/close và có shared consumers không.

**Câu 10.** Nếu delegate ném exception, mặc định delegator có tự rollback state không?

**Đáp án:** Không. Exception lan truyền nếu không bị bắt; rollback phải được thiết kế riêng.

**Câu 11.** Cùng một mutable Counter được inject vào hai Dashboards, count thay đổi ở một bên có thể thấy ở bên kia không?

**Đáp án:** Có. Cả hai giữ alias tới cùng Counter object.

**Câu 12.** Static utility method `Math.max` có phải delegation cho component instance không?

**Đáp án:** Không theo ngữ cảnh bài này; đó là gọi static helper không cần một đối tượng thành phần nhận lời gọi.

**Câu 13.** Một delegator có cần copy cùng mọi methods của component vào public API không?

**Đáp án:** Không. Chỉ expose hành vi cần cho client, có thể validate/transform/compose.

**Câu 14.** Nếu nhiều threads cùng thực hiện `contains` rồi `add` vào store, delegation tự bảo đảm uniqueness không?

**Đáp án:** Không. Check-then-act có race; cần atomic operation hoặc đồng bộ/transaction phù hợp.

**Câu 15.** Cách nào giúp kiểm thử delegator mà không gọi network?

**Đáp án:** Inject một fake collaborator theo cùng interface rồi kiểm input, số lượt gọi, outcome và exception behavior.

**Câu 16.** Vòng `A.go() -> B.go() -> A.go()` có thể gây điều gì?

**Đáp án:** Nếu không có điều kiện dừng, lời gọi lặp vô hạn cho đến stack overflow hoặc lỗi tương tự.

**Câu 17.** Nếu delegator chỉ forward một method, nó luôn là thiết kế tồi?

**Đáp án:** Không. Nó có thể ổn định public API, bảo vệ lifecycle, hỗ trợ test/mocking hoặc mô tả abstraction domain. Nhưng layer không đem lại giá trị nên được xem lại.

**Câu 18.** Strategy pattern có thể dùng delegation không?

**Đáp án:** Có. Context thường giữ strategy object rồi gọi method strategy; delegation rộng hơn Strategy.

## 35. Checklist code review

- [ ] Delegator và collaborator có **trách nhiệm phân biệt rõ**?
- [ ] Có quan hệ has-a/uses-a thực thay vì lạm dụng inheritance?
- [ ] Field component có scope `private` phù hợp?
- [ ] Constructor nhận/tạo collaborator theo đúng ownership/lifecycle?
- [ ] Dependency có được kiểm null/cấu hình hợp lệ sớm?
- [ ] Interface chỉ được tạo khi có abstraction/variation hoặc contract rõ?
- [ ] Phương thức công khai cung cấp **hành vi ở cấp delegator**, không lộ chi tiết vô ích?
- [ ] Có vô tình expose mutable component hoặc shared collections qua getter?
- [ ] Arguments được validate/normalize trước khi forward khi cần?
- [ ] Kết quả trả về có đúng type/contract caller mong đợi?
- [ ] Exceptions/cause/retry/idempotency được xử lý theo phạm vi trách nhiệm?
- [ ] Delegation có mutation trước lời gọi có thể fail không?
- [ ] Nếu nhiều collaborators, các bước có cần transaction/compensation?
- [ ] Component có được share giữa nhiều delegators hoặc threads?
- [ ] Mutable component có thread-safe không; nhiều thao tác có cần atomic boundary?
- [ ] Có quy định ai close resources và vào thời điểm nào?
- [ ] Có vòng delegation hoặc layering không cần thiết?
- [ ] Test có fake collaborator xác minh input, call count, kết quả và failure path?
- [ ] Có bảo vệ invariant khi component thay đổi hoặc thất bại?
- [ ] Các ví dụ Java có tên tệp trùng public class, lệnh `javac`/`java` và stdout đúng?

---

**Ghi nhớ:** **Ủy quyền thao tác cho đối tượng thành phần** là việc một object **giữ hoặc nhận một collaborator rồi gọi method của collaborator để thực hiện phần công việc thích hợp**. Composition/has-a mô tả **quan hệ cấu trúc**, còn delegation mô tả **cách hành vi được thực hiện**. Khi thiết kế tốt, delegator công khai API ở đúng cấp trách nhiệm, giữ component bên trong, validate/điều phối đúng chỗ và có thể thay implementation qua interface khi cần. Delegation không tự biến object thành immutable, không tự bảo đảm thread safety/transaction và không bắt buộc tạo wrapper cho mọi method. Hãy dùng nó để **phân chia trách nhiệm và giữ ranh giới đối tượng rõ ràng**, không chỉ để chuyển tiếp lời gọi cho đủ một tầng.