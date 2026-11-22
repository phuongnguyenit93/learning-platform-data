# Default method so với abstract class trong Java

**Interface default method** và **abstract class** đều giúp Java chia sẻ hành vi giữa nhiều kiểu đối tượng, nhưng giải quyết **hai bài toán thiết kế khác nhau**:

- **Default method trong interface** cung cấp một cách triển khai mặc định cho **một khả năng/hợp đồng** mà nhiều lớp có thể cùng thực hiện. Một lớp có thể triển khai nhiều interface, vì vậy nó có thể sử dụng nhiều nhóm hành vi mặc định.
- **Abstract class** là **lớp cơ sở** của một họ đối tượng có thể chia sẻ cả **trạng thái instance, constructor, bất biến nghiệp vụ, phương thức triển khai sẵn và những phương thức bắt buộc lớp con hoàn thiện**. Một lớp chỉ `extends` trực tiếp **một** lớp cha.

Cả hai đều hỗ trợ tính đa hình, override và tái sử dụng code. Chúng **không hoán đổi cho nhau**: thêm `default` vào interface không biến nó thành lớp có constructor và instance fields; viết abstract class không giúp Java đa kế thừa nhiều lớp.

Các cơ chế cốt lõi có từ Java 8 và **vẫn áp dụng trong Java hiện đại**. Ví dụ thực thi đầy đủ dùng JDK 17+; phần có API mới hơn Java 8 được đánh dấu phiên bản rõ ràng.

## 1. Nhận diện nhanh hai khái niệm

### Interface có default method

~~~java
interface Identified {
    String id(); // Hợp đồng trừu tượng

    default String summary() {
        return "interface:" + id();
    }
}
~~~

Đây là **khai báo kiểu**, chưa phải chương trình độc lập. `summary()` đã có implementation, gọi `id()` để lấy dữ liệu từ từng đối tượng triển khai. Lớp triển khai không nhất thiết phải override `summary()`; chỉ cần cung cấp một `id()` hợp lệ.

Từ khóa `default` trong interface nghĩa là **phương thức instance có thân được kế thừa theo quy tắc của interface**. Đây **không phải** “quyền truy cập default/package-private” của Java. Phương thức default trong interface là **public**.

### Abstract class có trạng thái và hợp đồng chưa hoàn thiện

~~~java
abstract class BaseEntity {
    private final String id;

    protected BaseEntity(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public final String id() {
        return id;
    }

    public abstract String kind();

    public String summary() {
        return kind() + ":" + id;
    }
}
~~~

Lớp cơ sở trên có:

- **Instance field** `id`, mỗi object có một giá trị riêng.
- **Constructor** khởi tạo và kiểm tra dữ liệu.
- Phương thức concrete `id()` được đánh dấu `final`: lớp con không được override.
- Phương thức trừu tượng `kind()`: lớp con concrete phải cài đặt.
- Phương thức concrete `summary()` có thể gọi abstract method để tùy biến một phần quy trình.

Không thể gọi `new BaseEntity(...)` vì lớp được khai báo `abstract`. Nhưng **constructor của `BaseEntity` vẫn chạy khi tạo lớp con**, thông qua `super(...)`.

### Bảng so sánh trọng tâm

| Tiêu chí | Interface default method | Abstract class |
| --- | --- | --- |
| Bản chất | Phương thức có thân trong một interface | Một lớp chưa cho phép khởi tạo trực tiếp |
| Ký hiệu | `default ReturnType method(...) { ... }` | `abstract class Name { ... }` |
| Hợp đồng bắt buộc | Abstract methods của interface | Abstract methods trong lớp cơ sở và inherited contracts |
| Hành vi dùng chung | Default methods | Concrete instance methods |
| Trạng thái instance do chính kiểu khai báo | **Không** có instance field trong interface | **Có** instance fields, initializers và constructors |
| Constructor để khởi tạo lớp triển khai | Không có constructor trong interface | Có constructor của abstract class |
| Kế thừa nhiều nguồn | Interface có thể `extends` nhiều interface; lớp có thể `implements` nhiều interface | Mỗi lớp chỉ `extends` một lớp cha trực tiếp |
| Modifier và khả năng truy cập method | Default method là public instance method; không `final`/`protected` | Concrete methods có thể `public`, `protected`, package-private hoặc `private` tùy ngữ cảnh; có thể `final` |
| Override | Lớp triển khai có thể override default phù hợp | Lớp con override concrete method nếu không `final` và triển khai abstract methods |
| Gọi implementation cha | `InterfaceName.super.method()` trong ngữ cảnh hợp lệ | `super.method()` từ lớp con |
| Bài toán hợp lý | Bổ sung hành vi mặc định cho **capability** rộng | Dùng chung **identity, invariant, state, lifecycle** của một họ đối tượng |
| Quan hệ với lambda | Default methods không làm tăng số SAM nếu interface là functional interface | Abstract class **không** thể làm target type của lambda |

**Đọc đúng “abstract”**: interface có các abstract methods và có thể đồng thời có default methods. Ngược lại, abstract class có thể **không khai báo abstract method nào** nhưng vẫn không thể khởi tạo trực tiếp. Hai khái niệm là hai trục khác nhau: **kiểu giao diện** đối lập **kiểu lớp**, và **có implementation** đối lập **chưa có implementation**.

## 2. Default method tồn tại để giải quyết vấn đề gì?

Trước khi có default methods, thêm một abstract method vào interface công khai có thể khiến những lớp triển khai cũ phải thêm implementation. Default method cho phép tác giả API cung cấp một cách xử lý mặc định bằng phương thức instance có thân trong interface.

Ví dụ:

~~~java
interface Printable {
    String text();

    default void print() {
        System.out.println(text());
    }
}
~~~

Lớp triển khai chỉ cung cấp `text()`. Khi gọi `print()`, default method sử dụng implementation `text()` của object đó. Đó là sự kết hợp **hợp đồng trừu tượng** với **hành vi tái sử dụng**.

Một số API Java tiêu chuẩn sử dụng default methods vẫn còn được dùng:

- `Iterable.forEach(Consumer<? super T>)`: duyệt và áp dụng hành động.
- `Collection.removeIf(Predicate<? super E>)`: mặc định có cách loại bỏ các phần tử thỏa điều kiện dựa trên iterator; implementation có thể override để tối ưu hoặc quy định hành vi.
- `List.replaceAll(UnaryOperator<E>)`: thay giá trị mỗi phần tử theo toán tử.
- `Map.getOrDefault(Object key, V defaultValue)`: trả giá trị tương ứng với key hoặc fallback theo hợp đồng của `Map`.
- `Map.forEach(BiConsumer<? super K,? super V>)`: xử lý từng cặp key/value.

Ví dụ đặt trong một phương thức:

~~~java
List<String> labels = new ArrayList<>(List.of("ok", "", "ready"));
labels.removeIf(String::isEmpty);
labels.replaceAll(String::toUpperCase);
// labels: ["OK", "READY"]
~~~

Cần import `java.util.*`. `List.of` được thêm ở Java 9, nhưng `removeIf` và `replaceAll` đã có từ Java 8. Ở đây ta tạo `ArrayList` sửa được từ danh sách nguồn, nên các thao tác cập nhật có ý nghĩa. Đừng làm `List.of(...).removeIf(...)` và mong cập nhật được: danh sách từ `List.of` là không sửa được.

### Default method không có nghĩa là API evolution luôn “không phá vỡ”

Thêm một default method thường **giảm yêu cầu** phải bổ sung method vào từng implementation, nhưng vẫn có khả năng tạo **xung đột tên/chữ ký** với những interface khác hoặc ảnh hưởng overload resolution và hành vi kế thừa trong một số hierarchy. Khi phát triển thư viện công khai, luôn kiểm thử những kiểu triển khai kết hợp nhiều interface và đánh giá tương thích nguồn, binary và behavior. Không dùng khẩu hiệu “thêm default method luôn an toàn tuyệt đối”.

## 3. Default method không có instance state riêng

Một interface có thể khai báo field, nhưng theo quy tắc Java những field ấy đều là **`public static final`**, không phải field instance gắn riêng với từng object.

~~~java
interface Thresholds {
    int LIMIT = 100; // public static final
}
~~~

`LIMIT` là hằng thuộc interface. **Không** thể viết:

~~~java
// SAI – interface không cho phép instance field:
interface Invalid {
    private int count;
}
~~~

Từ Java 9, interface có thể có **private helper methods** để tái sử dụng code giữa default/static methods, nhưng điều đó **không thêm constructor hoặc instance field**. Private interface methods cũng không được lớp triển khai kế thừa như một API callable.

Tuy nhiên, default method **có thể quan sát và thay đổi trạng thái của đối tượng triển khai** thông qua những phương thức mà interface công khai. Ví dụ:

~~~java
interface Adjustable {
    int value();
    void setValue(int value);

    default void increment() {
        setValue(value() + 1);
    }
}
~~~

`increment()` không sở hữu field `value`; nó gọi hai abstract methods để nhờ implementation lưu trạng thái. Nếu implementation dùng mutable state, hành vi vẫn có side effect. Vì vậy, “interface không có instance fields” **không đồng nghĩa** “default method luôn là pure function” hoặc “tự động thread-safe”.

Ngược lại, abstract class có thể giữ `private final String id` và buộc mọi lớp con đi qua constructor để áp dụng invariant chung. Đây là một điểm mạnh khi các lớp có chung mô hình trạng thái thực sự.

## 4. Abstract class: chia sẻ state, quy trình và bất biến

Một abstract class phù hợp khi nhiều biến thể thực sự là **cùng một họ đối tượng**, có phần dữ liệu chung và các quy tắc phải được thực thi nhất quán.

~~~java
abstract class AbstractAccount {
    private final String accountId;
    private long balance;

    protected AbstractAccount(String accountId, long openingBalance) {
        this.accountId = java.util.Objects.requireNonNull(accountId);
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balance = openingBalance;
    }

    public final String accountId() { return accountId; }

    public final long balance() { return balance; }

    protected final void add(long amount) {
        if (amount < 0) throw new IllegalArgumentException("negative amount");
        balance = Math.addExact(balance, amount);
    }

    public abstract String accountType();
}
~~~

Đây là **khai báo lớp minh họa**, không có `main`. Lưu ý `Math.addExact` kiểm tra overflow, nhưng đoạn ví dụ chưa đủ để làm hệ thống kế toán thực tế, chưa có kiểm soát đồng thời, tính nhất quán giao dịch hay truy cập dữ liệu. Mục tiêu là mô tả **khả năng giữ trạng thái và tập trung invariant**.

Abstract class có thể:
- Khởi tạo trạng thái qua constructor và kiểm tra điều kiện trước khi object dùng được.
- Giữ field `private`, cung cấp getter hoặc hành vi `protected` có kiểm soát.
- Dùng `final` cho phương thức không muốn lớp con phá invariant.
- Có nhiều concrete methods bên cạnh abstract methods.
- Có abstract methods `protected` nếu đó không phải phương thức phải thỏa hợp đồng `public` của interface.
- Triển khai một hoặc nhiều interface để tham gia các capability chung.

**Không nên chọn abstract class chỉ vì có hai dòng code giống nhau.** Nếu các kiểu không cùng vòng đời và invariant, cân nhắc utility, helper, composition hoặc default method thích hợp. Abstract class còn tạo **ràng buộc kế thừa**: một lớp đã `extends` lớp khác không thể `extends` thêm abstract base class nữa.

## 5. Kết hợp cả hai: một lớp có state và nhiều capability

Java cho phép một class **extends một abstract/concrete class** đồng thời **implements nhiều interface**:

~~~java
interface Identified {
    String id();
    default boolean hasId() { return !id().isBlank(); }
}

interface Priced {
    int amount();
    default String receipt() { return "receipt:" + amount(); }
}

abstract class BaseEntity implements Identified {
    private final String id;

    protected BaseEntity(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    @Override public final String id() { return id; }
    public abstract String kind();
}

final class Order extends BaseEntity implements Priced {
    private final int amount;

    Order(String id, int amount) {
        super(id);
        this.amount = amount;
    }

    @Override public int amount() { return amount; }
    @Override public String kind() { return "order"; }
}
~~~

Đây là **các khai báo minh họa** (có thể đặt trong một tệp với chỉ một top-level `public` class thích hợp). Với `Order`:

- `BaseEntity` chịu trách nhiệm **ID, constructor và việc lưu identity**.
- `Identified` nêu **contract `id()`** và cung cấp default `hasId()`.
- `Priced` nêu **contract `amount()`** và cung cấp default `receipt()`.
- `Order` triển khai hành vi cụ thể `kind()` và `amount()`.

Lớp không bị buộc phải chọn “default method **hoặc** abstract class”; trong nhiều thiết kế tốt, chúng **bổ sung** cho nhau.

Mô hình hợp lý là: **interface mô tả *can do what***, abstract class mô tả *what kind of object / which shared state and invariants*. Ví dụ một số đối tượng khác nhau hoàn toàn vẫn có thể `Priced` mà không phải cùng kế thừa `BaseEntity`.

### Tại sao cần tránh abstract class quá lớn?

Nếu `BaseEntity` tích lũy mọi capability như audit, pricing, notification, serialization và validation, nhiều lớp con sẽ thừa hưởng những hành vi không cần thiết. Dùng các interface nhỏ, có tên theo khả năng và cung cấp default methods đủ hẹp thường giúp mô hình tốt hơn. Khi implementation cần tài nguyên hoặc trạng thái phức tạp, đặt logic vào **service/composition** thay vì nhồi tất cả vào default method.

## 6. Quy tắc ưu tiên: phương thức của class và interface

Đây là phần dễ nhầm nhất khi so sánh default method với abstract class.

### 6.1. Concrete instance method trong superclass được ưu tiên

~~~java
interface Greeting {
    default String greet() { return "interface"; }
}

class BaseGreeting {
    public String greet() { return "class"; }
}

class ChildGreeting extends BaseGreeting implements Greeting {
}
~~~

`new ChildGreeting().greet()` trả `"class"`. Implementation `greet()` của class được kế thừa ưu tiên hơn default method cùng chữ ký trong interface. Có thể gọi nguyên tắc dễ nhớ là **“class wins”**, nhưng cần hiểu nó nói đến **concrete class method hợp lệ** và những quy tắc kế thừa/override cụ thể, không phải mọi method có nguồn từ class đều tự động thắng mọi default.

Trong chương trình chạy hoàn chỉnh ở phần 9, điều này được chứng minh bằng `classWins=class`.

### 6.2. Abstract method của superclass không biến thành implementation mặc định

~~~java
interface AutoCheck {
    default String check() { return "default-check"; }
}

abstract class NeedsCheck {
    public abstract String check();
}

// Concrete subclass phải cung cấp implementation:
class ExplicitCheck extends NeedsCheck implements AutoCheck {
    @Override public String check() { return "explicit-check"; }
}
~~~

Một lớp concrete phải thỏa abstract method mà nó kế thừa từ class. **Không được suy luận rằng default `AutoCheck.check()` sẽ tự động lấp vào abstract `NeedsCheck.check()`.** Nếu bỏ override ở `ExplicitCheck`, compiler báo rằng lớp concrete còn abstract method chưa cài đặt. Trường hợp này cũng nằm trong demo Java 17 ở phần sau.

Đây là khác biệt thiết kế quan trọng: abstract class có thể cố ý **buộc từng nhánh lớp con đưa ra quyết định**, không chấp nhận việc một default method không liên quan tình cờ trở thành implementation.

### 6.3. Cùng một interface có default method, class override tường minh

~~~java
interface Described {
    default String description() { return "generic"; }
}

class Detailed implements Described {
    @Override
    public String description() {
        return "detailed";
    }
}
~~~

Phương thức override của class phải có visibility tương thích với hợp đồng interface **public**. Không thể cài `description()` bằng `protected` hoặc package-private để làm giảm khả năng truy cập.

Trong abstract class, concrete method cũng có thể override default interface để thống nhất hành vi cho mọi lớp con. Nếu người thiết kế đánh dấu implementation đó `final`, lớp con không được thay đổi nó; interface default method tự nó không thể được khai báo `final`.

## 7. Xung đột giữa nhiều default methods: phải giải quyết rõ ràng

Một lớp có thể implement nhiều interface. Nếu cả hai đưa ra default method **cùng chữ ký nhưng implementation khác nhau**, Java **không chọn tùy tiện** interface xuất hiện trước hay sau trong `implements`.

~~~java
interface Alpha {
    default String label() { return "A"; }
}

interface Beta {
    default String label() { return "B"; }
}

// SAI: không thể kế thừa nguyên trạng hai default cùng chữ ký.
class Ambiguous implements Alpha, Beta {
}
~~~

Đây là mã **cố ý không biên dịch**, chỉ dùng để giải thích conflict. Cách giải quyết:

~~~java
final class Resolved implements Alpha, Beta {
    @Override
    public String label() {
        return Alpha.super.label() + "+" + Beta.super.label();
    }
}
~~~

`Resolved.label()` chọn **chủ động** cách kết hợp hành vi của hai interface, trả `"A+B"`. Cú pháp `Alpha.super.label()` truy cập implementation mặc định của một **direct superinterface thích hợp** từ lớp triển khai; khác với `super.label()` dùng cho superclass.

Bạn cũng có thể override và viết implementation hoàn toàn mới nếu không muốn kết hợp. Điều quan trọng là **lập trình viên phải xác định hợp đồng nào đúng**, không phó mặc cho thứ tự liệt kê interface.

### Khi chính interface con `extends` nhiều interface

~~~java
interface Left {
    default String name() { return "L"; }
}

interface Right {
    default String name() { return "R"; }
}

// SAI: kế thừa hai default override-equivalent mà không xử lý.
interface Broken extends Left, Right {
}

// ĐÚNG:
interface Combined extends Left, Right {
    @Override
    default String name() {
        return Left.super.name() + Right.super.name();
    }
}
~~~

Một interface con cũng phải giải quyết conflict bằng override, thay vì đợi đến lúc có class triển khai.

**Một default method và một abstract method có cùng chữ ký** kế thừa từ hai interface không có quan hệ ưu tiên thích hợp cũng có thể gây compile-time conflict. Không được tự dùng “default thắng abstract”; interface con nên override tường minh để chốt cách xử lý.

### Mức độ cụ thể của interface hierarchy cũng quan trọng

Nếu một subinterface override default method của superinterface, implementation từ **subinterface cụ thể hơn** được nhìn thấy theo quy tắc kế thừa; không có “hai default độc lập” để giải quyết chỉ vì chúng xuất hiện qua hai nhánh khác nhau. Tuy nhiên, đừng giản lược toàn bộ các tình huống về khẩu quyết “interface nào gần hơn cũng thắng”: cần xem **chữ ký, quan hệ subinterface và override** theo JLS.

## 8. Thứ gì không được biến thành default method?

Một số hạn chế của default method giúp phân biệt với concrete methods của abstract class.

### 8.1. Không khai báo default cho phương thức của `Object`

~~~java
interface InvalidObjectDefault {
    // SAI: default method không được override-equivalent với
    // public non-private method của java.lang.Object.
    default String toString() { return "value"; }
}
~~~

Mã này **cố ý không biên dịch**. Java cấm interface định nghĩa default implementation tương đương với các instance methods `public` không private của `Object`, như `toString()`, `equals(Object)` và `hashCode()`. Lý do là bất kỳ class triển khai cũng đã có quan hệ kế thừa với `Object`.

Class (kể cả abstract class) hoàn toàn có thể cung cấp `public String toString()` concrete override khi phù hợp. Nếu muốn giao diện quy định cách trình bày, hãy định nghĩa một method tên riêng như `displayText()`, rồi để class quyết định có gọi nó từ `toString()` hay không.

### 8.2. Không có constructor hay instance field trong interface

Default method có code nhưng không làm interface khởi tạo được bằng `new Interface()`. Interface chỉ có thể được triển khai bởi object của class, lớp vô danh hoặc theo cơ chế tương ứng của lambda khi nó là functional interface. Object thực tế vẫn là **instance của một class**, với vòng đời và state do class nắm giữ.

### 8.3. Không dùng `final`, `protected`, `private default` theo nghĩa modifier default

Default method là **public instance method** của interface, cho phép override. Nếu chỉ cần helper không lộ ra hợp đồng, từ **Java 9** có thể dùng `private` method trong interface (không khai báo là `default`), hoặc tách helper phù hợp. Abstract class có thể dùng phương thức `private`, `protected` và `final` cho từng vai trò.

### 8.4. Default method không là “miễn phí” về side effect hoặc concurrency

Một default method có thể gọi `setValue`, duyệt collection, kích hoạt callback, ném exception hay chạy I/O. Không có đảm bảo tự động về atomicity, transaction, retry, idempotency hoặc thread safety. Những quy tắc của implementation cụ thể vẫn áp dụng.

### 8.5. Phân biệt static, private và default methods của interface

| Loại method của interface | Được tính là abstract contract? | Được kế thừa như instance method? | Tình huống |
| --- | --- | --- | --- |
| `void run();` (abstract) | Có, sau quy tắc kế thừa | Có | Lớp concrete phải triển khai |
| `default void run() { ... }` | Không | Có, trừ khi override/conflict | Hành vi instance mặc định |
| `static Helper create() { ... }` | Không | **Không** theo cách gọi instance | Gọi qua tên interface khai báo |
| `private void helper() { ... }` (Java 9+) | Không | Không | Helper dùng nội bộ interface |

Thêm default method vào **functional interface** không làm tăng số abstract methods, nên nếu interface vẫn có đúng một phương thức hàm theo JLS, lambda vẫn sử dụng được. Nhưng một **abstract class dù có đúng một abstract method** cũng **không** tự biến thành functional interface và không nhận lambda trực tiếp như một target type.

## 9. Chương trình hoàn chỉnh: kế thừa, state, conflict và ưu tiên

Ví dụ sau tự chứa, dùng **JDK 17+** và trình bày các trường hợp còn áp dụng hiện nay. Lưu mã thành **DefaultVsAbstractDemo.java**:

~~~java
import java.util.Objects;

public class DefaultVsAbstractDemo {
    interface Identified {
        String id();
        default String summary() { return "interface:" + id(); }
        default boolean hasId() { return !id().isBlank(); }
    }

    interface Priced {
        int amount();
        default String receipt() { return "receipt:" + amount(); }
    }

    abstract static class BaseEntity implements Identified {
        private final String id;

        protected BaseEntity(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override public final String id() { return id; }
        @Override public String summary() { return "base:" + id; }

        public abstract String kind();

        protected String detail() {
            return kind() + "#" + id.length();
        }
    }

    static final class Order extends BaseEntity implements Priced {
        private final int amount;
        Order(String id, int amount) {
            super(id);
            this.amount = amount;
        }
        @Override public String kind() { return "order"; }
        @Override public int amount() { return amount; }
    }

    interface Alpha {
        default String label() { return "A"; }
    }
    interface Beta {
        default String label() { return "B"; }
    }
    static final class Resolved implements Alpha, Beta {
        @Override public String label() {
            return Alpha.super.label() + "+" + Beta.super.label();
        }
    }

    static class BaseGreeting {
        public String greet() { return "class"; }
    }
    interface Greeting {
        default String greet() { return "interface"; }
    }
    static final class ChildGreeting extends BaseGreeting implements Greeting { }

    interface AutoCheck {
        default String check() { return "default-check"; }
    }
    abstract static class NeedsCheck {
        public abstract String check();
    }
    static final class ExplicitCheck extends NeedsCheck implements AutoCheck {
        @Override public String check() { return "explicit-check"; }
    }

    public static void main(String[] args) {
        Identified record = new Order("O-7", 120);
        Order order = (Order) record;

        System.out.println("summary=" + record.summary());
        System.out.println("id=" + record.id() + ",valid=" + record.hasId());
        System.out.println("kind=" + order.kind() + ",detail=" + order.detail());
        System.out.println("receipt=" + order.receipt());
        System.out.println("conflict=" + new Resolved().label());
        System.out.println("classWins=" + new ChildGreeting().greet());
        System.out.println("abstractRequires=" + new ExplicitCheck().check());
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 DefaultVsAbstractDemo.java
java DefaultVsAbstractDemo
~~~

Stdout **đã kiểm chứng bằng biên dịch và thực thi**:

~~~text
summary=base:O-7
id=O-7,valid=true
kind=order,detail=order#3
receipt=receipt:120
conflict=A+B
classWins=class
abstractRequires=explicit-check
~~~

### Giải thích từng dòng

1. `Identified record = new Order(...)`: biến được khai báo dưới kiểu interface, nhưng object là `Order`, có superclass `BaseEntity`. Đây là đa hình thông thường.
2. `record.summary()` cho `base:O-7`, **không phải** `interface:O-7`, vì `BaseEntity` đã override default `Identified.summary()` bằng phương thức concrete.
3. `record.hasId()` dùng default method từ interface và gọi `id()` do `BaseEntity` cài đặt; chuỗi `"O-7"` không blank nên trả `true`. `String.isBlank` được thêm ở **Java 11**.
4. `order.kind()` do lớp concrete triển khai abstract method từ base; `detail()` là concrete method từ abstract class, gọi `kind()` đa hình rồi ghép `#` với độ dài ID bằng 3.
5. `order.receipt()` dùng default method từ interface `Priced`, trả `receipt:120`. Nhờ vậy `Order` kết hợp được state từ base và capability pricing mà không cần thừa kế thêm một superclass.
6. `Resolved.label()` giải quyết xung đột default methods bằng `Alpha.super.label()` và `Beta.super.label()`, cho `A+B`.
7. `ChildGreeting` kế thừa concrete `greet()` từ class `BaseGreeting`; method này thắng default cùng chữ ký của interface `Greeting`, nên `classWins=class`.
8. `NeedsCheck.check()` là abstract method của superclass. `AutoCheck` có default cùng chữ ký nhưng không tự cung cấp implementation cho concrete `ExplicitCheck`; lớp con override và trả `explicit-check`.

Các ví dụ cố ý sai ở phần 7–8 **không được ghép vào tệp chạy**, vì sẽ gây lỗi biên dịch theo chủ đích.

## 10. Lựa chọn thiết kế trong các tình huống thực tế

### Trường hợp A: nhiều đối tượng không cùng họ nhưng cùng một khả năng

Ví dụ hóa đơn, bản ghi tồn kho và phí dịch vụ đều có thể “có giá trị tiền” nhưng không nhất thiết chia sẻ identity hay vòng đời. Dùng interface `Priced` với `amount()` và `receipt()` có thể hợp lý hơn ép tất cả kế thừa `AbstractPricedObject`. Các lớp vẫn tự do kế thừa một class khác nếu có nhu cầu.

**Tiêu chí:** các lớp chia sẻ **hợp đồng khả năng** nhưng không chia sẻ cấu trúc state/cách khởi tạo.

### Trường hợp B: cả họ đối tượng phải có cùng state và invariant

Ví dụ nhiều loại tài khoản đều phải có account ID bất biến, số dư hợp lệ, kiểm soát cập nhật cùng quy trình khởi tạo. Abstract class có constructor và protected/final methods giúp tập trung ràng buộc hơn việc copy-paste cùng code vào từng implementation.

**Tiêu chí:** chung **identity, lifecycle, invariants và phần implementation đáng kể**.

### Trường hợp C: cần cả một base class lẫn nhiều capability

Mô hình `Order extends BaseEntity implements Priced` là lựa chọn phổ biến: base giữ dữ liệu, interface diễn đạt behavior. Nếu capability cần nhiều state hoặc dependency riêng, cân nhắc **composition**: object giữ một service thành viên và default method chỉ điều phối qua hợp đồng công khai khi thực sự cần.

### Trường hợp D: API công khai muốn bổ sung một operation

Có thể cân nhắc thêm default method với implementation hợp lý dựa trên các abstract methods hiện có:

~~~java
interface HasCode {
    String code();

    default boolean hasCode() {
        String current = code();
        return current != null && !current.isBlank();
    }
}
~~~

`hasCode()` cung cấp giá trị chung mà lớp triển khai không cần lặp lại. **Nhưng** nếu implementation default không hợp lý với mọi đối tượng, đừng thêm chỉ để tránh nâng phiên bản API; một method mới có hợp đồng rõ ràng hoặc interface mới có thể an toàn hơn.

### Trường hợp E: có logic framework theo từng giai đoạn

Nếu framework muốn giữ cấu trúc một quy trình, chỉ cho phép lớp con tùy biến một vài “hook” thì **Template Method pattern** trong abstract class thường phù hợp:

~~~java
abstract class TaskPipeline {
    public final void execute() {
        validate();
        process();
    }

    protected void validate() {
        // Có thể override nếu hợp đồng cho phép.
    }

    protected abstract void process();
}
~~~

Đây là **khai báo lớp minh họa**, không phải chương trình độc lập. `execute()` là `final` để khóa trình tự, `process()` bắt lớp con thực hiện, và `validate()` có implementation mặc định. Interface default method có thể tạo hành vi chung, nhưng không có cùng khả năng **giữ state và final instance template method** trong chính interface.

## 11. Một số quyết định API dễ gây hiểu nhầm

### Default method có làm interface “giống abstract class” không?

Chúng giống ở khả năng **có một số method được triển khai sẵn**, nhưng khác ở:
- khả năng sở hữu instance fields;
- constructor/invariants;
- số lượng superclass cho phép;
- visibility/finality của các instance methods;
- conflict/override rules.

Nên nói **“default method giúp interface cung cấp behavior”**, không nói “interface đã trở thành abstract class”.

### Có thể dùng abstract class nhưng không có abstract method không?

Có. `abstract class Holder { ... }` hợp lệ ngay cả khi mọi method đều concrete. `abstract` khi ấy ngăn tạo trực tiếp instance lớp đó. Việc có nên làm như vậy là quyết định thiết kế; thường dùng khi định nghĩa lớp cơ sở chưa hoàn chỉnh về mặt ý nghĩa dù code có implementation.

### Có thể dùng interface chỉ có default methods không?

Có. Một interface có thể có các default methods và không có abstract method riêng (ngoài những quy tắc inherited members). Nó vẫn là một interface bình thường và **không nhất thiết** là functional interface. Đừng dùng lambda để cài một interface không có hợp đồng SAM.

### Có thể dùng `InterfaceName.super.method()` từ mọi nơi không?

Không. Đây là cú pháp có **ràng buộc ngữ cảnh và quan hệ superinterface** theo JLS. Không thể coi như lời gọi static hoặc gọi từ một class không có quan hệ triển khai thích hợp. Với method của superclass, dùng `super.method()` theo quy tắc lớp. Nếu cần reuse default behavior ở nhiều hierarchy phức tạp, nên kiểm tra compiler với đúng JDK mục tiêu.

### Một class đã kế thừa implementation của Object thì interface default có thắng không?

Không thể khai báo interface default tương đương với các public non-private methods của `Object` như `toString()`. Class có thể tự override `toString()`, hoặc expose một interface method `displayText()` rồi class quyết định cách sử dụng. Không dùng interface default để thay thế hợp đồng nền tảng của Object.

### Default method có thể trả `void` và có side effect không?

Có. `Iterable.forEach` là default method sử dụng `Consumer` và không trả giá trị. Kiểu trả về `void` không nói lên an toàn hay đồng thời; side effect cần được thiết kế cụ thể.

## 12. Checklist trước khi chọn default method hay abstract class

1. **Đối tượng có chung một mô hình state/invariant không?** Nếu có, abstract class có thể là công cụ phù hợp; nếu chỉ cùng một khả năng, ưu tiên interface.
2. **Một lớp có cần kết hợp nhiều khả năng độc lập không?** Java cho phép `implements` nhiều interface nhưng chỉ một superclass.
3. **Tôi có cần constructor, field `private`, hoặc `final` method ở base không?** Chỉ abstract/concrete class đáp ứng đầy đủ nhu cầu đó.
4. **Default implementation có đúng cho mọi implementation hợp lệ không?** Nếu không, đừng tự động nhét behavior vào interface.
5. **Đã có default method cùng chữ ký ở interface khác chưa?** Kiểm tra xung đột và override.
6. **Superclass có concrete hoặc abstract method cùng chữ ký chưa?** Concrete class method được ưu tiên; abstract class method có thể buộc class concrete override.
7. **Mở rộng public API có phá source/binary/behavior compatibility không?** Kiểm thử với các implementation đa kế thừa.
8. **State và side effect có ảnh hưởng concurrency không?** Từ khóa `default` không tạo thread safety, và abstract class cũng không tự bảo đảm.
9. **Có nguy cơ ép những lớp không cùng “is-a” relationship vào chung base không?** Cân nhắc interface và composition.
10. **Có thể diễn đạt rõ hơn bằng helper/service thay vì inheritance không?** Không nên lạm dụng cả default method lẫn abstract class chỉ để tái sử dụng vài dòng.

## 13. Những lỗi phổ biến

| Hiểu nhầm / mã có vấn đề | Giải thích | Cách đúng |
| --- | --- | --- |
| “Có default method thì interface giữ instance field được” | Interface field là `public static final`, không phải field riêng từng object | Lưu state trong class hoặc component; interface gọi contract |
| “Default method được truy cập package-private” | Nhầm từ khóa `default` với *default access* | Default method trong interface là public |
| “Abstract class bắt buộc có abstract method” | Có thể abstract vì ý định không cho tạo trực tiếp | Không đồng nhất keyword với số method |
| “Có default method thì luôn không cần cài đặt bất kỳ method nào” | Interface vẫn có abstract contracts | Concrete class phải đáp ứng contract còn lại |
| “Java có đa kế thừa class vì có nhiều default methods” | Chỉ đa kế thừa hợp đồng/behavior interface, không đa kế thừa class state và constructors | `extends` một class, `implements` nhiều interfaces |
| “Hai default methods trùng chữ ký tự chọn interface đầu tiên” | Java báo conflict trong nhiều trường hợp | Override tường minh và gọi `Interface.super` nếu cần |
| “Default method luôn thắng abstract method của superclass” | Abstract method từ class có quy tắc ưu tiên khác | Concrete subclass cài đặt method |
| “Class và interface có method trùng chữ ký thì interface thắng vì mới hơn” | Concrete class implementation ưu tiên | Kiểm tra phương thức class inherited/overridden |
| “Default method có thể là `final`” | Interface default không có modifier final | Nếu cần khóa hành vi, cân nhắc final method trong class |
| “Default `toString()` trong interface hợp lệ” | JLS cấm default method tương đương public Object instance method | Dùng interface method tên riêng hoặc override trong class |
| “Tạo `new AbstractBase()` được vì class có constructor” | Abstract class không thể instantiate trực tiếp | Tạo concrete subclass, constructor base chạy qua `super` |
| “Default method luôn pure và thread-safe” | Có thể mutate state gián tiếp và gọi I/O | Thiết kế concurrency/side effect rõ ràng |
| “Thêm default vào public interface không bao giờ phá tương thích” | Có thể tạo conflict hoặc đổi nghĩa kế thừa | Kiểm thử đa interface và upgrade API |
| “Abstract class là functional interface nếu có một abstract method” | Functional interface phải là interface theo JLS | Dùng interface `@FunctionalInterface` cho lambda |
| “`List.of` có thể sửa giống `ArrayList`” | List của `List.of` không sửa được | Dùng `new ArrayList<>(List.of(...))` khi cần mutate |
| “Dùng default method để chia sẻ field `private` giữa các lớp” | Interface không sở hữu per-instance field | Dùng abstract base hoặc composition |

## 14. Bài tập tự kiểm tra

1. Phân biệt `default String name()` trong interface với `String name()` concrete trong abstract class. Chúng có cùng mức truy cập mặc định không?
2. Vì sao `interface Priced { int amount(); default String receipt() {...} }` không cần biết cách `Order` lưu `amount`?
3. Một abstract class có constructor nhận `id` và field `private final id` mang lại lợi ích gì so với interface có default `id()`?
4. Viết một class `Order extends BaseEntity implements Priced`. Xác định phương thức nào đến từ base class, interface và chính class con.
5. Nếu class extends `BaseGreeting` có concrete `greet()`, đồng thời implements interface có default `greet()`, phương thức nào chạy?
6. Nếu superclass khai báo `abstract String check()`, một interface độc lập có `default String check()`, concrete subclass có thể bỏ qua override không? Vì sao?
7. Hai interface cùng có `default String label()`; hãy giải quyết conflict bằng cách override trong class và kết hợp cả hai chuỗi.
8. Có thể viết default method `toString()` trong interface không? Nếu cần hỗ trợ format, nên dùng tên API nào?
9. Giải thích vì sao thêm `default void log()` vào interface công khai có thể gặp rủi ro dù không ép mọi implementation viết thêm method.
10. Một interface có default `increment()` gọi `setValue(value()+1)`. Nó có state riêng không, và cần chú ý điều gì nếu nhiều thread cùng gọi?
11. Đề xuất cách chia trách nhiệm giữa interface, abstract class và service cho các đối tượng cùng có phí dịch vụ nhưng khác quy trình lưu trữ.
12. Vì sao `@FunctionalInterface` có thể chứa default methods, còn abstract class với một abstract method không thể làm target type cho lambda?

## Tài liệu chuẩn còn áp dụng

- [Java Language Specification — Interfaces, `9.4 và `9.4.1](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.4)
- [Java Language Specification — Inheriting Methods with Override-Equivalent Signatures, `8.4.8.4](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.4.8.4)
- [Java Language Specification — Abstract Classes, `8.1.1.1](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.1.1.1)
- [Java SE 17 — Iterable.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html#forEach(java.util.function.Consumer))
- [Java SE 17 — Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate))
- [Java SE 17 — List.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator))
- [Java SE 17 — Map.getOrDefault](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#getOrDefault(java.lang.Object,java.lang.Object))

**Kết luận:** Chọn **interface default method** khi cần cung cấp hành vi chung cho **một hợp đồng khả năng** có thể áp dụng ở nhiều class hierarchy. Chọn **abstract class** khi nhiều lớp thực sự chia sẻ **identity, constructor, instance state, invariant và quy trình nền tảng**. Có thể kết hợp cả hai, nhưng phải hiểu quy tắc **class method ưu tiên, abstract method vẫn có thể bắt buộc override, và default conflicts cần giải quyết tường minh**. Mục đích thiết kế quan trọng hơn việc tối đa hóa tái sử dụng code bằng inheritance.
