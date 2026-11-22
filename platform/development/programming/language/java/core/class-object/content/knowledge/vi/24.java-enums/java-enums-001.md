# Enum để mô hình hóa tập thể hiện có tên hữu hạn trong Java

## 1. Mục tiêu: biểu diễn một tập lựa chọn đóng, có tên và có ý nghĩa

Một số khái niệm nghiệp vụ chỉ có **một số trạng thái hoặc giá trị được định nghĩa trước**: mức ưu tiên `LOW`, `MEDIUM`, `HIGH`; hướng `NORTH`, `EAST`, `SOUTH`, `WEST`; trạng thái đơn hàng `NEW`, `PAID`, `SHIPPED`, `CANCELLED`. Khi các lựa chọn có tên, có ý nghĩa và không phải do người dùng tự tạo thêm tùy lúc, Java cung cấp kiểu **`enum`** để mô hình hóa.

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

Đây là **một khai báo enum hợp lệ** có thể đặt ở cấp tệp hoặc dưới dạng nested type, chưa phải chương trình chạy riêng.

Với enum `Priority`:

- `LOW`, `MEDIUM`, `HIGH` là **các hằng enum có tên** và là **các đối tượng** thuộc enum type `Priority`.
- Một biến kiểu `Priority` chỉ có thể tham chiếu các constant instances của kiểu đó **hoặc `null`**, chứ không nhận mọi chuỗi/số nguyên.
- Những constant instances được xác định bởi khai báo enum, không thể tạo một constant mới bằng `new Priority()` từ client.
- Các constant được dùng qua `Priority.LOW`, `Priority.MEDIUM`, `Priority.HIGH`.
- Enum có **type riêng**, nên compiler phân biệt Priority với các enum khác, dù có cùng tên constant.
- Số lượng và tên constant **được đóng trong phiên bản khai báo enum**, không phải tập động do người dùng mở rộng ở runtime.

> **Tư tưởng:** Khi miền giá trị thực sự là một **tập hữu hạn đã biết trước, mỗi phần tử có tên rõ**, `enum` làm cấu trúc dữ liệu phản ánh đúng miền giá trị hơn dùng số “ma thuật” hoặc chuỗi nhập tùy ý.

Mục tiêu bài học là hiểu **khi nào, vì sao và như thế nào** dùng enum để mô hình hóa tập giá trị hữu hạn; nhận diện các giới hạn của nó và kiểm chứng qua ví dụ Java 17+ chạy được.

## 2. Một chương trình đầu tiên

Tạo tệp **`PriorityBasicsDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class PriorityBasicsDemo {
    public static void main(String[] args) {
        Priority current = Priority.HIGH;

        System.out.println(current);
        System.out.println(current == Priority.HIGH);
        System.out.println(current == Priority.LOW);
        System.out.println(Priority.values().length);
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac PriorityBasicsDemo.java
java PriorityBasicsDemo
```

**Standard output:**

```text
HIGH
true
false
3
```

Giải thích:

1. `Priority.HIGH` là hằng đã được định nghĩa của type Priority.
2. `current == Priority.HIGH` true vì cùng tham chiếu constant instance.
3. `current == Priority.LOW` false vì hai constants khác nhau.
4. Compiler cung cấp `values()` cho enum, trả một mảng các constants theo thứ tự khai báo, nên có 3.
5. `System.out.println(current)` dùng `toString()`; khi không override, output là tên constant `HIGH`.

**Chú ý:** `enum` không đồng nghĩa “chỉ chứa số”. Trong Java, mỗi constant là một **đối tượng** có thể có fields, methods và behavior riêng. Tuy nhiên, set constant instances vẫn do khai báo enum xác định.

## 3. So sánh với String và int: vì sao cần một kiểu riêng?

Trước enum, có thể viết:

```java
String priority = "HGIH"; // Sai chính tả nhưng vẫn là String.
int level = 17;           // Không rõ 17 có hợp lệ hay không.
```

Hai dòng là **mảnh minh họa** lỗi thiết kế:

- `String` chấp nhận mọi nội dung, bao gồm typo, chữ hoa/thường khác nhau, giá trị không hợp lệ.
- `int` chấp nhận một miền số rất lớn, trong khi nghiệp vụ có thể chỉ có ba mức.
- Code phân tán các chuỗi/hằng số gây trùng lặp, khó refactor và kiểm soát.
- Một method nhận String/primitive không tự nói rõ tập giá trị hợp lệ.

Với enum:

```java
Priority priority = Priority.HIGH;
```

Compiler kiểm kiểu. Đoạn sau không hợp lệ:

```java
// Priority wrong = "HIGH";      // String không phải Priority.
// Priority wrong = 17;          // int không phải Priority.
// Priority wrong = Priority.HGIH; // Constant không tồn tại.
```

**Lợi ích chính:** *type safety*. Người đọc API `schedule(Priority level)` biết level thuộc tập Priority đã định nghĩa. Một typo khi gọi constant thường được phát hiện lúc biên dịch thay vì tồn tại thành dữ liệu sai ở runtime.

**Giới hạn:** Compiler không tự bảo vệ trước `null`, hay đầu vào không hợp lệ đến từ JSON/HTTP/database. Việc ánh xạ dữ liệu từ bên ngoài sang enum vẫn cần validation/parse thích hợp.

## 4. Số lượng hữu hạn và tên hằng có nghĩa

Một enum tốt thường mô tả **các lựa chọn rời rạc, có tên ổn định trong domain**.

Ví dụ:

```java
enum Direction {
    NORTH, EAST, SOUTH, WEST
}

enum Light {
    RED, YELLOW, GREEN
}

enum AccessLevel {
    GUEST, MEMBER, ADMIN
}
```

Đây là **các khai báo minh họa**.

Nhìn vào type, ta xác định được những lựa chọn đã được mô hình hóa.

Nhưng các tên này chỉ là ví dụ về một **tập có giới hạn do ứng dụng quy định**. Không phải mọi hệ thống có đủ đúng ba access levels, hay đèn giao thông ở mọi quốc gia đều chỉ có ba trạng thái. Khi domain thay đổi, chính enum declaration cũng cần được cập nhật và các downstream consumers được kiểm tra.

### Khi nào không phù hợp?

Các trường hợp như username, mã sản phẩm do người dùng nhập, hàng nghìn đơn hàng khác nhau, IDs sinh liên tục, danh sách quốc gia/currency lấy từ nhà cung cấp động… thường **không nên cố đóng vào một enum của application** nếu tập giá trị có thể mở rộng không theo chu kỳ release.

Một tập “có hữu hạn giá trị tại thời điểm này” chưa đủ; điều cần thiết là tập giá trị **được biết trước và có chủ đích đóng ở cấp thiết kế**.

## 5. Tập hữu hạn có tên khác tập object tùy ý

Giả sử hệ thống có trạng thái vận chuyển:

```java
enum DeliveryStatus {
    CREATED, PACKED, SENT, DELIVERED
}
```

`DeliveryStatus.SENT` là một constant instance. Mọi chỗ trong cùng runtime context thông thường dùng `DeliveryStatus.SENT` đều tham chiếu cùng constant object đó.

Ngược lại, nếu tự thiết kế class:

```java
final class DeliveryStatusValue {
    private final String label;

    DeliveryStatusValue(String label) {
        this.label = label;
    }
}
```

Class này **cho phép tạo nhiều instances** bằng `new DeliveryStatusValue("SENT")`. Nó không tự đảm bảo đóng tập instance ở bốn tên như enum.

**Không suy rằng enum là một class không có methods.** Enum là một cơ chế ngôn ngữ đặc biệt cho các constant objects được khai báo có tên, đồng thời có hành vi giống những objects khác ở những nơi Java cho phép.

## 6. Enum được định danh theo type: hai enum có constant cùng tên vẫn khác

Tạo **`EnumTypeSafetyDemo.java`**:

```java
enum ShippingStatus {
    NEW, DONE
}

enum PaymentStatus {
    NEW, DONE
}

public class EnumTypeSafetyDemo {
    static String summarize(ShippingStatus status) {
        return "shipping=" + status;
    }

    public static void main(String[] args) {
        ShippingStatus shipping = ShippingStatus.DONE;
        PaymentStatus payment = PaymentStatus.DONE;

        System.out.println(summarize(shipping));
        System.out.println(payment.name());

        // summarize(payment); // Lỗi compile-time:
        // PaymentStatus khác ShippingStatus.
    }
}
```

```bash
javac EnumTypeSafetyDemo.java
java EnumTypeSafetyDemo
```

```text
shipping=DONE
DONE
```

Hai enums có constant tên `DONE`, nhưng:

- `ShippingStatus.DONE` là ShippingStatus.
- `PaymentStatus.DONE` là PaymentStatus.
- Không thể truyền nhầm PaymentStatus cho method đòi ShippingStatus mà compiler âm thầm chấp nhận.

Đây là khác biệt quan trọng với cách dùng String `"DONE"`: String không mang theo khái niệm “DONE của thanh toán” và “DONE của vận chuyển” dưới dạng distinct Java types.

## 7. Enum constants là những đối tượng singleton theo mỗi constant

Với:

```java
enum Size {
    SMALL, MEDIUM, LARGE
}
```

mỗi constant `SMALL`, `MEDIUM`, `LARGE` được Java khởi tạo như một object của enum type. Trong phạm vi runtime/class loader bình thường, không có việc client gọi `new Size()` để tạo hằng Size thứ tư.

Một phép so sánh thường dùng với enum là `==` vì constants được định danh bằng identity:

```java
Size a = Size.SMALL;
Size b = Size.SMALL;
System.out.println(a == b); // true.
```

Đây là **mảnh code** trong method hợp lệ.

### So sánh `==` và `equals()`

`Enum.equals()` có semantics identity. Với non-null enum references cùng type, `a == b` và `a.equals(b)` có cùng ý nghĩa so hằng, nhưng `a.equals(b)` có thể ném `NullPointerException` nếu a null.

Do đó:

```java
if (status == DeliveryStatus.SENT) {
    // ...
}
```

là cách rõ ràng và null-safe khi status có thể null.

**Không tự khẳng định “một singleton trên toàn bộ vũ trụ JVM” mà bỏ qua class loader boundaries**. Với ứng dụng thông thường, mỗi enum constant có một identity ổn định trong context class loading của type ấy. Mục tiêu API là tập constant instances được quy định bởi enum declaration.

## 8. `values()` và `valueOf()`: quan sát tập đã định nghĩa

Java cung cấp hai methods đặc biệt trên enum types:

- `Priority.values()`: mảng chứa các constants theo thứ tự khai báo.
- `Priority.valueOf("HIGH")`: tìm constant **đúng tên khai báo** hoặc ném `IllegalArgumentException` nếu không có tên đó.

Tạo **`EnumValuesDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumValuesDemo {
    public static void main(String[] args) {
        for (Priority value : Priority.values()) {
            System.out.println(value.name());
        }

        System.out.println(
                Priority.valueOf("HIGH") == Priority.HIGH);

        try {
            Priority.valueOf("high");
        } catch (IllegalArgumentException ex) {
            System.out.println("unknown name");
        }
    }
}
```

```bash
javac EnumValuesDemo.java
java EnumValuesDemo
```

```text
LOW
MEDIUM
HIGH
true
unknown name
```

**Giới hạn quan trọng:**

- `valueOf` **case-sensitive**: `"high"` không phải `"HIGH"`.
- `valueOf(null)` ném `NullPointerException` theo API.
- `values()` trả một **mảng mới**, không phải reference trực tiếp đến mảng lưu constants nội bộ.
- Mảng có thể sửa các slots, nhưng việc đó **không tạo hoặc thay đổi tập constant được enum type khai báo**.
- Các enum constants có thể có customized `toString()`. `valueOf` tra cứu theo **`name()`**, không tra cứu bằng kết quả customized toString.

**Không dùng `values()` làm cơ chế cho phép client đăng ký constant mới.** Tập enum được đóng ở declaration.

## 9. Chứng minh `values()` trả mảng khác nhưng chứa cùng constant objects

Tạo **`EnumValuesArrayDemo.java`**:

```java
enum Status {
    OPEN, CLOSED
}

public class EnumValuesArrayDemo {
    public static void main(String[] args) {
        Status[] first = Status.values();
        Status[] second = Status.values();

        System.out.println(first == second);
        System.out.println(first[0] == second[0]);

        first[0] = Status.CLOSED;

        System.out.println(first[0]);
        System.out.println(second[0]);
        System.out.println(Status.values()[0]);
    }
}
```

```bash
javac EnumValuesArrayDemo.java
java EnumValuesArrayDemo
```

```text
false
true
CLOSED
OPEN
OPEN
```

**Phân biệt hai cấp độ:**

1. `first` và `second` là **hai array objects khác nhau**.
2. `first[0]` và `second[0]` ban đầu trỏ **cùng Status.OPEN enum constant instance**.
3. Gán `first[0] = Status.CLOSED` sửa chỉ một slot của array first.
4. Nó không xóa hay đổi tên Status.OPEN; `Status.values()[0]` vẫn trả OPEN theo declaration order.

## 10. Cách chọn tên và phạm vi enum trong thiết kế

Tên enum type nên diễn tả **miền giá trị**: `OrderStatus`, `Priority`, `Direction`, `PaymentMethod`. Constants nên diễn tả các **phần tử cụ thể**: `PAID`, `HIGH`, `NORTH`.

Convention phổ biến là:

- Type: PascalCase, chẳng hạn `OrderStatus`.
- Constants: UPPER_SNAKE_CASE, chẳng hạn `IN_PROGRESS`.
- Fields/methods: camelCase theo conventions Java thông thường.

Tên phải **không nhập nhằng**. Nếu có `Status` chung cho thanh toán, vận chuyển và tài khoản, việc dùng một enum quá rộng dễ làm lẫn semantics. Có thể dùng những enum riêng:

```java
enum AccountStatus {
    ACTIVE, SUSPENDED, CLOSED
}

enum InvoiceStatus {
    DRAFT, ISSUED, PAID
}
```

Hai types này phản ánh hai miền trạng thái khác nhau.

### Đặt ở đâu?

- Một public top-level enum có thể ở file `OrderStatus.java` theo quy tắc filename/public type.
- Nested enum trong class phù hợp khi chỉ gắn một khái niệm domain cục bộ ở class.
- `private enum` có thể là nested member type, hữu ích nếu implementation detail không nên trở thành API.
- Trong Java 17 có thể khai báo **local enum** trong block; local enum implicitly static, không capture local variables như một local inner class.
- Không mở public API của enum chỉ vì tiện gọi nếu consumers không thật sự cần tên type ấy.

## 11. Dùng enum trong signature giúp hợp đồng rõ ràng

Tạo **`PriorityApiDemo.java`**:

```java
import java.util.Objects;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class PriorityApiDemo {
    static String deliveryChannel(Priority priority) {
        Objects.requireNonNull(priority, "priority");

        return switch (priority) {
            case LOW -> "batch";
            case MEDIUM -> "normal";
            case HIGH -> "express";
        };
    }

    public static void main(String[] args) {
        System.out.println(
                deliveryChannel(Priority.HIGH));
        System.out.println(
                deliveryChannel(Priority.LOW));
    }
}
```

```bash
javac PriorityApiDemo.java
java PriorityApiDemo
```

```text
express
batch
```

Thay vì method nhận `String priority` rồi so nhiều literals, API dùng `Priority` để **giới hạn kiểu giá trị hợp lệ**. `Objects.requireNonNull` kiểm null boundary, tránh code xử lý null không chủ định.

**Lợi ích tại call site:** `deliveryChannel(Priority.HIGH)` tự mô tả hơn `deliveryChannel(3)`. Compiler phát hiện truyền nhầm một enum type khác.

### Về `switch` expression

Trong ví dụ, `switch` là **expression** Java 17 trả về String. Các cases bao phủ tất cả constants hiện tại của Priority, nên không cần `default`. Nếu thêm constant vào Priority trong cùng source/module khi rebuild, compiler có thể giúp phát hiện thiếu case và buộc bạn xét ý nghĩa mới.

**Không đánh đồng compile-time exhaustive check với cam kết input từ phiên bản dữ liệu khác luôn an toàn.** Public API/serialized values có yêu cầu compatibility riêng khi enum tiến hóa.

## 12. Enum là tập tên hữu hạn, nhưng mỗi phần tử có thể mang dữ liệu

Đôi khi tên constants chưa đủ để hiển thị hoặc tính toán. Một enum có thể lưu **metadata gắn với từng lựa chọn**, thay vì scattering `if/switch` ở nhiều chỗ.

Tạo **`PriorityWithFieldsDemo.java`**:

```java
enum Priority {
    LOW(1, "thap"),
    MEDIUM(2, "trung binh"),
    HIGH(3, "cao");

    private final int weight;
    private final String label;

    Priority(int weight, String label) {
        this.weight = weight;
        this.label = label;
    }

    int weight() {
        return weight;
    }

    String label() {
        return label;
    }
}

public class PriorityWithFieldsDemo {
    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(priority.name() + ":" +
                    priority.weight() + ":" +
                    priority.label());
        }
    }
}
```

```bash
javac PriorityWithFieldsDemo.java
java PriorityWithFieldsDemo
```

```text
LOW:1:thap
MEDIUM:2:trung binh
HIGH:3:cao
```

Điểm cần nhớ:

- Các constant declarations được đặt đầu enum body.
- Dấu `;` sau constant list cần thiết khi phía sau còn khai báo fields/methods.
- Constructor `Priority(int, String)` được runtime/compiler dùng khi khởi tạo constants; client không gọi `new Priority(...)`.
- Enum constructors không được public/protected; thường để implicit/private.
- `weight` và `label` là final fields để mỗi constant có immutable metadata trong ví dụ.
- `Priority.values()` vẫn chứa đúng ba constants LOW/MEDIUM/HIGH; thêm metadata không tạo ra constants mới.

**Mô hình tốt:** Enum là một tập lựa chọn có danh tính ổn định, còn dữ liệu đính kèm mô tả ý nghĩa từng lựa chọn.

## 13. Enum constructor không phải public factory

Cú pháp `LOW(1, "thap")` trông giống constructor call, nhưng nó là **khai báo enum constant** trong chính enum body.

Client không được:

```java
// Priority fourth = new Priority(4, "very high");
```

Ngay cả khi constructor nằm trong source, Java cấm tạo enum instances tùy ý từ client. Điều này giúp giữ **tính đóng** của tập constant instances.

**Cẩn trọng về constructor và initialization:**

- Enum constants được tạo khi enum class được khởi tạo theo quy tắc class initialization.
- Không dựa vào các side effects mơ hồ hoặc thứ tự khởi tạo giữa nhiều classes.
- Tránh thao tác mutable global state trong enum constructors.
- Enum constant fields nên được khởi tạo rõ ràng, dữ liệu immutable khi có thể.
- Java áp dụng các giới hạn đặc biệt về tham chiếu đến static fields của enum từ constructors/instance initializers để tránh truy cập trước khi class được khởi tạo hoàn chỉnh.

Một tập hữu hạn nên **ổn định và dễ suy luận**; đừng biến enum constructor thành nơi mở socket, ghi database hay đăng ký resource không có lifecycle rõ.

## 14. Mỗi constant có thể có hành vi qua methods

Dữ liệu và hành vi gắn theo domain có thể được đặt gần constants. Ví dụ quy tắc tính phí khác nhau cho ba phương thức giao hàng.

Tạo **`DeliveryMethodBehaviorDemo.java`**:

```java
enum DeliveryMethod {
    STANDARD {
        @Override
        int fee(int items) {
            return 10;
        }
    },
    EXPRESS {
        @Override
        int fee(int items) {
            return 20 + items * 2;
        }
    },
    PICKUP {
        @Override
        int fee(int items) {
            return 0;
        }
    };

    abstract int fee(int items);
}

public class DeliveryMethodBehaviorDemo {
    public static void main(String[] args) {
        for (DeliveryMethod method : DeliveryMethod.values()) {
            System.out.println(method.name() + "=" +
                    method.fee(3));
        }
    }
}
```

```bash
javac DeliveryMethodBehaviorDemo.java
java DeliveryMethodBehaviorDemo
```

```text
STANDARD=10
EXPRESS=26
PICKUP=0
```

Mỗi enum constant ở đây có class body riêng override method `fee`. Tuy nhiên **tập lựa chọn vẫn hữu hạn**: STANDARD, EXPRESS, PICKUP; chúng không phải plugin types có thể đăng ký thêm từ ngoài vào.

**Khi nào nên đặt behavior vào enum?**

- Khi logic nhỏ, gắn trực tiếp và ổn định với từng lựa chọn.
- Khi tránh các `switch` phân tán lặp lại cùng quy tắc.
- Khi interface/method có contract rõ và inputs đơn giản.

**Khi nào không?** Nếu mỗi lựa chọn cần hệ thống dependency injection, database/network access hoặc hàng trăm dòng workflow, enum có thể quá nặng. Giữ enum như **identifier của loại** và chuyển hành vi phức tạp sang strategy/services bên ngoài sẽ dễ test và quản lý dependencies hơn.

## 15. Hành vi khác nhau không làm tập enum trở thành mở rộng động

Một enum không phải cơ chế plugin registry. Dù constant có class body riêng như `EXPRESS { ... }`, ứng dụng khác **không thể khai báo thêm `DeliveryMethod.DRONE` từ class ngoài** ở runtime.

Để thêm một lựa chọn, thường phải:

1. Thay source enum declaration.
2. Rebuild/deploy phần Java liên quan.
3. Kiểm tra exhaustive switches, routing, validation, mapping từ external codes.
4. Xem lại backward/forward compatibility với persisted data và clients.

Nếu nghiệp vụ yêu cầu người dùng tự tạo loại mới trong database hoặc bên thứ ba đăng ký behavior lúc chạy, cân nhắc **interface + classes + registry**, sealed hierarchy với giới hạn thích hợp, hoặc value objects/dynamic configuration. Enum chỉ phù hợp khi tập phần tử *đóng* là một chủ đích của thiết kế.

## 16. Enum dùng trong tập `EnumSet`

Khi một object cần lưu **nhiều lựa chọn enum cùng lúc**, Java có collection `EnumSet<E>` tối ưu cho enum types.

Tạo **`EnumSetDemo.java`**:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, EXECUTE, DELETE
}

public class EnumSetDemo {
    public static void main(String[] args) {
        EnumSet<Permission> allowed =
                EnumSet.of(Permission.READ, Permission.EXECUTE);

        System.out.println(allowed);
        System.out.println(allowed.contains(Permission.READ));
        System.out.println(allowed.contains(Permission.WRITE));

        allowed.add(Permission.WRITE);
        System.out.println(allowed);
    }
}
```

```bash
javac EnumSetDemo.java
java EnumSetDemo
```

```text
[READ, EXECUTE]
true
false
[READ, WRITE, EXECUTE]
```

`EnumSet` dùng **declaration order** cho iteration/output ở ví dụ. Nó chỉ chấp nhận constants của cùng một enum type trong generic contract, nên không lẫn `Permission.READ` với một enum khác.

Một `EnumSet` thông thường là **mutable collection**. `allowed.add(...)` được phép và thay set, mặc dù từng enum constant vẫn không thể tạo thêm.

### `EnumSet.allOf`, `noneOf` và `complementOf`

```java
EnumSet<Permission> all = EnumSet.allOf(Permission.class);
EnumSet<Permission> none = EnumSet.noneOf(Permission.class);
EnumSet<Permission> others = EnumSet.complementOf(allowed);
```

Đây là **mảnh code minh họa** với Permission/allowed tồn tại. Set các values của enum không đồng nghĩa EnumSet là immutable; nó chỉ là một collection chuyên biệt cho domain hữu hạn.

## 17. Enum làm khóa của `EnumMap`

Một cấu hình theo từng lựa chọn enum có thể dùng `EnumMap`, tránh dùng String keys tùy ý.

Tạo **`EnumMapDemo.java`**:

```java
import java.util.EnumMap;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumMapDemo {
    public static void main(String[] args) {
        EnumMap<Priority, Integer> targets =
                new EnumMap<>(Priority.class);

        targets.put(Priority.HIGH, 5);
        targets.put(Priority.LOW, 1);
        targets.put(Priority.MEDIUM, 3);

        for (Priority priority : targets.keySet()) {
            System.out.println(priority + "=" +
                    targets.get(priority));
        }
    }
}
```

```bash
javac EnumMapDemo.java
java EnumMapDemo
```

```text
LOW=1
MEDIUM=3
HIGH=5
```

Dù `put` không theo thứ tự enum declaration, EnumMap có iteration order theo **natural order của keys** (declaration order của constants).

**Ranh giới:** EnumMap không tự bắt buộc phải có mapping cho **mọi** constant. Bạn vẫn cần kiểm những key thiếu. Nếu muốn ánh xạ đầy đủ, hãy thiết kế validations hoặc khởi tạo rõ từng constant.

**Điều này minh họa một lợi ích thiết kế:** miền keys được xác định bởi enum type, còn values là dữ liệu có thể thay đổi theo nghiệp vụ.

## 18. So sánh enum với nhiều booleans

Giả sử một ticket chỉ có đúng một trạng thái tại một thời điểm:

```java
boolean newTicket;
boolean assigned;
boolean closed;
```

Ba booleans tạo ra **8 combinations**, bao gồm nhiều trạng thái mâu thuẫn như cả new và closed cùng true.

Nếu domain chỉ cho phép một trong ba trạng thái, enum hợp hơn:

```java
enum TicketStatus {
    NEW, ASSIGNED, CLOSED
}
```

`TicketStatus status` mô hình **một lựa chọn duy nhất** từ tập hữu hạn. Không có cấu hình “vừa NEW vừa CLOSED” ở cùng một biến enum.

**Nhưng khi có nhiều lựa chọn đồng thời?** Nếu một account có nhiều permissions, dùng `EnumSet<Permission>` phù hợp hơn một biến Permission duy nhất.

**Không ép enum thay mọi booleans:** Nếu hai thuộc tính thật sự độc lập, ví dụ `isVerified` và `hasPremiumPlan`, giữ hai booleans có thể đúng. Chỉ dùng enum khi domain là **các trạng thái loại trừ nhau** hoặc **loại có tên hữu hạn**.

## 19. Phân biệt “trạng thái” và “sự kiện”

Một sai lầm mô hình hóa là trộn sự kiện diễn ra trong thời gian với một trạng thái kéo dài.

Ví dụ:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

enum OrderEvent {
    PAYMENT_RECEIVED, SHIPMENT_SENT, CANCELLATION_REQUESTED
}
```

`OrderStatus.PAID` mô tả state hiện tại. `OrderEvent.PAYMENT_RECEIVED` mô tả một sự kiện có thể gây chuyển trạng thái.

Cả hai đều có thể là enum, nhưng chúng là **hai miền giá trị có ý nghĩa khác nhau**. Tách type khiến method `apply(OrderEvent event)` và property `OrderStatus status` rõ ràng hơn.

**Không nên** thêm những giá trị mơ hồ như `UPDATED` hoặc `PROCESSED` vào cùng enum chỉ để gom hết từ vựng domain, nếu chúng không cùng loại khái niệm.

## 20. Một trạng thái enum không tự cấm chuyển trạng thái sai

Type `OrderStatus` giới hạn tập constants, nhưng nó **không tự bảo đảm** các chuyển trạng thái hợp lệ.

Ví dụ, ứng dụng có thể cấm:

- `NEW -> SHIPPED` nếu chưa trả tiền.
- `CANCELLED -> PAID` nếu đã đóng đơn.
- `SHIPPED -> NEW` nếu quy trình không hỗ trợ quay ngược.

Enum giúp mô hình **những trạng thái có thể biểu diễn**, còn quy tắc **transition** phải do code nghiệp vụ thực thi.

Tạo **`EnumTransitionDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

public class EnumTransitionDemo {
    static boolean canAdvance(OrderStatus from,
                              OrderStatus to) {
        if (from == null || to == null) {
            return false;
        }

        return switch (from) {
            case NEW -> to == OrderStatus.PAID
                    || to == OrderStatus.CANCELLED;
            case PAID -> to == OrderStatus.SHIPPED
                    || to == OrderStatus.CANCELLED;
            case SHIPPED, CANCELLED -> false;
        };
    }

    public static void main(String[] args) {
        System.out.println(canAdvance(
                OrderStatus.NEW, OrderStatus.PAID));
        System.out.println(canAdvance(
                OrderStatus.NEW, OrderStatus.SHIPPED));
        System.out.println(canAdvance(
                OrderStatus.CANCELLED, OrderStatus.PAID));
    }
}
```

```bash
javac EnumTransitionDemo.java
java EnumTransitionDemo
```

```text
true
false
false
```

**Phạm vi:** Đây chỉ là transition rule ví dụ, không phải một workflow engine đầy đủ. Các invariant của đơn hàng (thanh toán, kho, hoàn tiền, idempotency) cần thêm điều kiện riêng.

## 21. Parse external input: không được giả định text luôn là enum constant

Trong code Java đã biên dịch, `Priority.HIGH` là type-safe. Nhưng input từ UI, REST, CSV hoặc database thường là `String`. Phải phân biệt **Java constant name** với **external code**.

Tạo **`EnumInputParsingDemo.java`**:

```java
import java.util.Locale;
import java.util.Optional;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumInputParsingDemo {
    static Optional<Priority> parse(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        String normalized =
                raw.trim().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            return Optional.empty();
        }

        try {
            return Optional.of(Priority.valueOf(normalized));
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        System.out.println(parse(" high "));
        System.out.println(parse("urgent"));
        System.out.println(parse(null));
    }
}
```

```bash
javac EnumInputParsingDemo.java
java EnumInputParsingDemo
```

```text
Optional[HIGH]
Optional.empty
Optional.empty
```

Ở đây parser cố ý chấp nhận chữ thường/khoảng trắng biên, nhưng **không tự chấp nhận mọi giá trị**. `"urgent"` chưa có trong enum nên Optional.empty.

**Quy tắc API:** Thống nhất chính sách khi input không hợp lệ: trả Optional, result type có lỗi cụ thể, ném exception hợp nghĩa hoặc gửi HTTP 400. Không âm thầm map mọi unknown value sang một constant tùy tiện nếu làm mất thông tin nghiệp vụ.

### Chuẩn hóa chữ hoa theo locale

`toUpperCase(Locale.ROOT)` tránh phụ thuộc một số quy tắc địa phương không phù hợp khi xử lý **mã kỹ thuật**. Nhưng **không phải mọi mã bên ngoài đều nên uppercase**: nếu contract nói case-sensitive, hãy tôn trọng contract ấy.

## 22. External code ổn định khác `name()`

Dùng `name()` để lưu vào database hoặc gửi qua API là đơn giản, nhưng **đổi tên enum constant trong code** có thể phá dữ liệu cũ/client.

Một cách có kiểm soát là **khai báo mã external ổn định**:

Tạo **`EnumStableCodeDemo.java`**:

```java
import java.util.Optional;

enum PaymentState {
    WAITING("P0"),
    SETTLED("P1"),
    REJECTED("P2");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static Optional<PaymentState> fromCode(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        for (PaymentState state : values()) {
            if (state.code.equals(raw)) {
                return Optional.of(state);
            }
        }
        return Optional.empty();
    }
}

public class EnumStableCodeDemo {
    public static void main(String[] args) {
        System.out.println(PaymentState.SETTLED.code());
        System.out.println(PaymentState.fromCode("P2"));
        System.out.println(PaymentState.fromCode("P9"));
    }
}
```

```bash
javac EnumStableCodeDemo.java
java EnumStableCodeDemo
```

```text
P1
Optional[REJECTED]
Optional.empty
```

`WAITING` là Java constant name, `"P0"` là external code. Có thể đổi Java identifier khi cần refactor mà vẫn giữ external code, miễn mapping/compatibility được quản lý nhất quán.

**Không dùng `ordinal()` làm mã lưu trữ ổn định.** Chúng ta sẽ phân tích vì sao ở mục kế.

## 23. Vì sao không dùng `ordinal()` như ID nghiệp vụ?

Mỗi enum constant có `ordinal()` là vị trí khai báo bắt đầu từ 0.

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

Ở đây LOW có ordinal 0, MEDIUM 1, HIGH 2. Nếu tương lai chèn một constant ở đầu hoặc đổi thứ tự khai báo, các ordinal khác có thể đổi.

Tạo **`EnumOrdinalDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumOrdinalDemo {
    public static void main(String[] args) {
        for (Priority p : Priority.values()) {
            System.out.println(p.name() + ":" + p.ordinal());
        }
    }
}
```

```bash
javac EnumOrdinalDemo.java
java EnumOrdinalDemo
```

```text
LOW:0
MEDIUM:1
HIGH:2
```

**Bẫy:** Nếu database đã lưu 1 nghĩa là MEDIUM và sau này bạn thêm `URGENT` trước MEDIUM, 1 có thể trở thành URGENT. Ngữ nghĩa dữ liệu cũ bị đổi mà không có compiler báo.

- `ordinal()` hữu ích cho một số implementation/collection nội bộ.
- `EnumSet` và `EnumMap` xử lý hiệu quả mà client không cần lưu ordinal.
- Trong persistent/external API, chọn **mã ổn định explicit** nếu compatibility quan trọng.
- Ngay cả lưu `name()` cũng cần migration policy khi rename/remove constants.

## 24. `toString()` có thể phục vụ hiển thị, không phải contract parse mặc định

`name()` là tên constant được khai báo và không bị override. `toString()` có thể được override để trình bày thân thiện.

Tạo **`EnumDisplayDemo.java`**:

```java
enum Status {
    IN_PROGRESS("Dang xu ly"),
    COMPLETED("Hoan thanh");

    private final String display;

    Status(String display) {
        this.display = display;
    }

    @Override
    public String toString() {
        return display;
    }
}

public class EnumDisplayDemo {
    public static void main(String[] args) {
        Status status = Status.IN_PROGRESS;

        System.out.println(status.name());
        System.out.println(status.toString());
        System.out.println(Status.valueOf("IN_PROGRESS"));
    }
}
```

```bash
javac EnumDisplayDemo.java
java EnumDisplayDemo
```

```text
IN_PROGRESS
Dang xu ly
Dang xu ly
```

Dòng thứ ba trả `Status.IN_PROGRESS` từ `valueOf` rồi `println` gọi **overridden `toString()`**, nên in `Dang xu ly`, không in tên constant.

**Kết luận:** Phân biệt **identifier**, **display text**, **external serialization code**. Có thể cần ba giá trị khác nhau; không bắt `toString` phục vụ đồng thời database và UI.

Trong ứng dụng đa ngôn ngữ, nên dùng message keys/resource bundles thay vì nhúng toàn bộ bản dịch vào enum, nếu domain yêu cầu localization động.

## 25. Enum có thể implement interface, nhưng không extends class tùy ý

Enum type kế thừa `java.lang.Enum<E>` theo cơ chế ngôn ngữ; nó không được tự `extends MyBaseClass`.

Tuy nhiên, một enum **có thể implement interfaces**, giúp nhiều enum types tham gia cùng một contract.

Tạo **`EnumInterfaceDemo.java`**:

```java
interface Code {
    String code();
}

enum Severity implements Code {
    INFO("I"),
    WARNING("W"),
    ERROR("E");

    private final String value;

    Severity(String value) {
        this.value = value;
    }

    @Override
    public String code() {
        return value;
    }
}

public class EnumInterfaceDemo {
    static void printCode(Code value) {
        System.out.println(value.code());
    }

    public static void main(String[] args) {
        printCode(Severity.WARNING);
        System.out.println(Severity.ERROR instanceof Code);
    }
}
```

```bash
javac EnumInterfaceDemo.java
java EnumInterfaceDemo
```

```text
W
true
```

`Severity` có đúng ba named constants, còn `Code` là interface chung. Implementing interface **không làm enum mở rộng constant set**, chỉ cung cấp thêm hợp đồng hành vi.

**Nếu thực sự cần các implementations mới không biết trước**, interface + concrete classes/registry sẽ phù hợp hơn enum đóng.

## 26. Cẩn thận mutable fields trong enum constants

Tuy constants không thể bị client tạo thêm, **field của enum object không tự immutable**.

Đây là ví dụ **một thiết kế có chủ ý để lộ rủi ro**:

```java
enum Mode {
    STANDARD;

    private int counter;

    void increment() {
        counter++;
    }

    int counter() {
        return counter;
    }
}
```

`Mode.STANDARD` là shared enum constant object. Nếu một module gọi `increment()`, module khác có thể nhìn thấy counter thay đổi. Đó không phải state riêng theo từng user/request.

### Khuyến nghị

- Enum constants nên có **metadata immutable**, thường `private final`.
- Không đặt request-specific/user-specific counters, caches mutable khó kiểm soát vào enum.
- Nếu cần data thay đổi cho từng yêu cầu, đặt state vào **class instance riêng** hoặc một service/collection được quản lý phù hợp.
- Một mutable enum field dùng chung giữa threads đòi synchronization/atomicity; type enum không tự cung cấp thread safety cho state mutable ấy.

**Phân biệt:** Constant identity ổn định không đồng nghĩa immutable state.

## 27. `null` vẫn là giá trị tham chiếu có thể xuất hiện

Dù type là enum:

```java
Priority priority = null;
```

câu lệnh là hợp lệ về Java reference typing. Vì vậy enum **không hoàn toàn loại bỏ invalid runtime state** nếu business contract cấm null.

Khi validate boundary:

```java
Objects.requireNonNull(priority, "priority");
```

Đây là mảnh code, giả định `java.util.Objects` đã được import.

Một so sánh:

```java
if (priority == Priority.HIGH) {
    // ...
}
```

là **null-safe**, nhưng không nhất thiết thay cho validation: nếu business operation bắt buộc có priority, im lặng coi null là false có thể che bug. Hãy quyết định rõ việc null có được chấp nhận không.

Không lạm dụng constant `UNKNOWN` chỉ để khỏi xử lý null nếu `UNKNOWN` không phải domain state hợp lệ. `UNKNOWN` hợp lý khi **thực sự** là một loại giá trị được thiết kế, ví dụ trạng thái chưa xác định được phân biệt rõ với sai dữ liệu.

## 28. Enum và `switch`: thêm constant là một thay đổi domain

Enum được xem là tập đóng **trong phiên bản hiện tại**. Khi thêm constant, các phép xử lý dựa trên tập đó có thể cần cập nhật.

Ví dụ ban đầu:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

Nếu bổ sung `CRITICAL`, hãy rà:

- `switch` expressions cần xử lý CRITICAL theo nghiệp vụ.
- `EnumMap` có mapping đầy đủ không?
- `EnumSet` rules có tự bao gồm constant mới không?
- Input/output API có chấp nhận external code mới không?
- Dữ liệu đã persisted có cần migration/compatibility không?
- UI có label mới, sorting order mới, analytics grouping mới không?
- Các tests trước đây có ngầm giả định `values().length == 3` không?

**Tập đóng không có nghĩa không bao giờ thay đổi theo phiên bản phần mềm**. Nó có nghĩa việc thay đổi tập là **thay đổi code/schema có chủ đích**, khác với user tự thêm giá trị vào một table runtime.

## 29. Không dùng Enum để đại diện từng bản ghi dữ liệu

Hãy đối chiếu:

- `OrderStatus` có vài giá trị nghiệp vụ dùng chung: enum hợp.
- `Order` là một bản ghi có ID, customer, items, timestamps: cần **class/record/entity** riêng, không phải một enum constant cho mỗi order.
- `UserRole` có thể là enum nếu chính sách roles được đóng trong mã: ADMIN, USER, REVIEWER.
- Nếu roles do quản trị viên tạo động và gán permissions tùy ý: một database-backed Role entity hoặc config có thể phù hợp hơn.

**Phân biệt set-of-types với set-of-data-records:** Enum mô tả một **số lượng lựa chọn có tên**, không thay thế bảng dữ liệu hoặc collection instances có lifecycle riêng.

## 30. Bài tập mô hình hóa: chọn enum, boolean hay class?

| Bài toán | Mô hình có thể phù hợp | Lý do |
| --- | --- | --- |
| Tín hiệu đèn đỏ/vàng/xanh | `enum Signal` | Tập hữu hạn có tên, mỗi lần chọn một |
| Hướng bắc/đông/nam/tây | `enum Direction` | Bốn tên domain rõ |
| Đơn hàng đang ở giai đoạn nào | `enum OrderStatus` | Một state từ tập đã định |
| Các quyền đang được bật cùng lúc | `EnumSet<Permission>` | Có nhiều lựa chọn cùng lúc |
| Một số lượng 0–100 | `int` kèm validation | Không có 101 tên constant hữu ích |
| Username của người dùng | `String`/value object | Giá trị động, không đóng |
| Trạng thái có xác nhận hay không | `boolean` nếu đúng hai trường hợp | Dễ hiểu khi thật sự nhị phân |
| Ba boolean biểu diễn cùng một status loại trừ | `enum` tốt hơn | Tránh tổ hợp mâu thuẫn |
| Cấu hình plugin có thể đăng ký runtime | Interface + registry/classes | Enum đóng không mở rộng động |
| Mức cảnh báo có code và nhãn cố định | Enum có final fields | Data gắn với mỗi constant |
| Mã sản phẩm trong catalog thay đổi mỗi ngày | Entity/value type | Tập do dữ liệu quyết định |
| Các ngày trong tuần | `DayOfWeek` JDK | Đã có enum chuẩn trong `java.time` |
| Giá trị quốc gia từ dịch vụ cập nhật | Cân nhắc data-driven source | Không mặc định đóng trong Java code |

**Quy tắc tự kiểm:** “Có thể viết đầy đủ tên mọi lựa chọn ngay trong source hôm nay, và yêu cầu đổi tập chỉ diễn ra qua release có kiểm soát không?” Nếu có, enum là ứng viên mạnh.

## 31. Tự kiểm bằng assertions không phụ thuộc `-ea`

Một bộ self-test có thể xác nhận contract tập constants và mapping, không chỉ in names.

Tạo **`EnumContractSelfTest.java`**:

```java
import java.util.EnumMap;
import java.util.EnumSet;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumContractSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(Priority.values().length == 3, "count");
        check(Priority.valueOf("HIGH") == Priority.HIGH,
                "valueOf mapping");
        check(Priority.HIGH == Priority.HIGH, "identity");

        EnumSet<Priority> selected =
                EnumSet.of(Priority.LOW, Priority.HIGH);

        check(selected.contains(Priority.HIGH),
                "set membership");
        check(!selected.contains(Priority.MEDIUM),
                "set non-membership");

        EnumMap<Priority, Integer> weights =
                new EnumMap<>(Priority.class);

        weights.put(Priority.LOW, 1);
        weights.put(Priority.MEDIUM, 2);
        weights.put(Priority.HIGH, 3);

        for (Priority value : Priority.values()) {
            check(weights.containsKey(value),
                    "missing mapping for " + value);
        }

        check(weights.get(Priority.HIGH) == 3,
                "high weight");
        System.out.println("enum contract PASS");
    }
}
```

```bash
javac EnumContractSelfTest.java
java EnumContractSelfTest
```

```text
enum contract PASS
```

`check` chủ động ném `AssertionError` khi false, không yêu cầu bật JVM assertions bằng `-ea`. Self-test này chỉ bao phủ một tập Priority có ba constants; khi thêm constant, nó cố ý báo cần cập nhật test/EnumMap mapping.

**Quan trọng:** Đừng kiểm số lượng constants cứng ở mọi nơi trong production nếu tính mở rộng qua release là dự kiến. Trong self-test một domain contract cụ thể, kiểm con số có thể là chủ đích; trong application code, nên duyệt `values()` hoặc có quy tắc phù hợp.

## 32. Lỗi phổ biến và cách sửa

| Ngộ nhận | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Enum chỉ là vài chuỗi hằng” | Mất hiểu biết về type safety/object semantics | Coi enum là type có named constant instances |
| “Mọi chuỗi đều có thể gán cho enum” | Compile-time type mismatch | Parse/validate String trước |
| “`valueOf` tự không phân biệt chữ hoa” | Phân biệt chính xác name | Normalize có chủ đích hoặc dùng external-code parser |
| “`values()` cho phép sửa constant set” | Chỉ trả mảng chứa references | Không coi mảng là registry mở |
| “Enum có thể new thêm constant” | Enum constructors không công khai tạo instance | Định nghĩa constant ở declaration |
| “Enum singleton nghĩa toàn bộ state immutable” | Mutable fields trên shared constants vẫn đổi | Giữ final immutable metadata |
| “Ordinal là ID ổn định” | Thứ tự khai báo có thể đổi | External code explicit |
| “`toString()` luôn là `name()`” | Có thể override | Tách name, code, display |
| “Enum không thể null” | Enum là reference type | Validate boundary nếu không chấp nhận null |
| “Hai enums có cùng constant name thay thế nhau” | Hai Java types khác nhau | API nhận enum đúng domain |
| “Một enum status tự bảo vệ transitions” | Type chỉ giới hạn values | Thêm state machine/validation |
| “EnumMap tự có mọi constant keys” | Map có thể thiếu mapping | Kiểm đầy đủ nếu contract đòi |
| “EnumSet là immutable” | EnumSet thường mutable | Copy/wrap theo contract |
| “Một enum thay cho dữ liệu động” | Tập đóng không phù hợp catalog cập nhật runtime | Value object/DB registry |
| “Thêm constant là thay đổi nhỏ, không cần review” | Switch/mapping/API/persistence có thể bị tác động | Review exhaustive consumers và migration |
| “Một enum cho mọi trạng thái dùng chung” | Trộn domains, lose type safety | Tách enum theo ngữ nghĩa |
| “Dùng enum thay mọi boolean” | Có trường hợp nhị phân thật sự | Chọn type đơn giản đủ rõ |
| “Thêm nhiều flags qua boolean cho trạng thái loại trừ” | Cho phép trạng thái mâu thuẫn | Enum một giá trị |
| “Enum là hệ plugin mở” | Không thể tự đăng ký constants | Interface/registry khi cần extensibility |
| “Default trong switch luôn giúp tốt hơn” | Có thể che constant mới chưa được xử lý | Cân nhắc exhaustive switch expression không default |
| “Tất cả enum đều có thứ tự nghiệp vụ” | Declaration order không nhất thiết domain order | Định nghĩa explicit rank nếu cần |

## 33. Câu hỏi tự luyện

**Câu 1.** Tại sao enum phù hợp cho `Priority { LOW, MEDIUM, HIGH }`?

*Đáp án:* Đây là tập lựa chọn có tên, hữu hạn và được đóng trong source; type riêng tránh nhầm với String/int hay enum khác.

**Câu 2.** Có thể viết `new Priority()` từ code client không?

*Đáp án:* Không; Java quản lý enum constants, không cho tùy ý tạo enum instances.

**Câu 3.** `Priority.HIGH == Priority.HIGH` bằng gì?

*Đáp án:* true, cùng constant instance.

**Câu 4.** `Priority.valueOf("high")` hoạt động không?

*Đáp án:* Không với tên khai báo HIGH; valueOf case-sensitive, ném IllegalArgumentException.

**Câu 5.** `Priority.values()` trả về gì?

*Đáp án:* Một array mới các constants theo declaration order.

**Câu 6.** Có thể gán `Priority p = null` không?

*Đáp án:* Có; phải validate nếu domain cấm null.

**Câu 7.** Hai enums cùng có constant `DONE` có dùng thay nhau trong method parameter không?

*Đáp án:* Không; Java phân biệt enum types.

**Câu 8.** Tại sao không nên lưu ordinal trong database?

*Đáp án:* Ordinal là vị trí khai báo, có thể thay khi chèn/đổi thứ tự constants.

**Câu 9.** `name()` và `toString()` luôn giống nhau không?

*Đáp án:* Không; enum có thể override toString, name vẫn là identifier constant.

**Câu 10.** Muốn lưu mã `"P1"` ổn định cho `PaymentState.SETTLED` thì làm sao?

*Đáp án:* Gắn final code field và method parse/fromCode theo explicit mapping.

**Câu 11.** Enum có thể có constructors và methods không?

*Đáp án:* Có, với restrictions của enum; constructors được dùng để tạo constants do declaration quy định.

**Câu 12.** Enum constant có thể có class body riêng override behavior không?

*Đáp án:* Có; đó không làm tập constants mở rộng động.

**Câu 13.** `EnumSet` hợp tình huống nào?

*Đáp án:* Lưu một tập nhiều constants cùng enum type, ví dụ các permissions đang bật.

**Câu 14.** `EnumMap` có đảm bảo mọi enum key đều có entry không?

*Đáp án:* Không; vẫn có thể thiếu, phải validate mapping theo contract.

**Câu 15.** Khi nào boolean tốt hơn enum?

*Đáp án:* Với câu hỏi thật sự chỉ có hai giá trị độc lập và tên boolean rõ nghĩa.

**Câu 16.** Có nên dùng enum cho IDs của hàng triệu đơn hàng không?

*Đáp án:* Không; đó là dữ liệu động, nên dùng value/entity type.

**Câu 17.** Enum có tự chặn `NEW -> SHIPPED` không?

*Đáp án:* Không; transitions cần business validation riêng.

**Câu 18.** Thêm một constant vào enum có thể ảnh hưởng nơi nào?

*Đáp án:* Exhaustive switches, mappings, UI, persistence, serialization, tests và các integrations.

**Câu 19.** Enum có thể implement interface không?

*Đáp án:* Có; nhưng không extends tùy ý một user-defined class vì enum kế thừa Enum theo cơ chế ngôn ngữ.

**Câu 20.** Tại sao mutable counter trong enum constant nguy hiểm?

*Đáp án:* Constant object được dùng chung; counter là shared mutable state, có thể gây aliasing/concurrency issues.

**Câu 21.** `EnumSet.allOf(Priority.class)` tạo đối tượng immutable không?

*Đáp án:* Không; nó tạo EnumSet bao gồm tất cả constants hiện tại, set thông thường vẫn mutable.

**Câu 22.** Có thể dùng enum khi người dùng được tự tạo loại mới trên website mà không deploy code không?

*Đáp án:* Thường không; cần data-driven model/registry.

**Câu 23.** Nếu có cả `OrderStatus.PAID` lẫn `PaymentStatus.PAID`, đó là một constant không?

*Đáp án:* Không, chúng là constants của hai types khác nhau.

**Câu 24.** Bản chất của “tập hữu hạn có tên” trong enum là gì?

*Đáp án:* Java type khai báo rõ toàn bộ tập constant instances có tên được hỗ trợ bởi phiên bản source đó, thay vì cho phép mọi object/string tùy ý.

## 34. Checklist thiết kế enum

- [ ] Domain có thực sự là một tập lựa chọn **rời rạc, có tên, đóng theo phiên bản code**?
- [ ] Các constant names có diễn tả đúng ngữ nghĩa domain?
- [ ] Enum type có đủ cụ thể, không gom các domains khác nhau?
- [ ] Method signatures dùng enum thay String/int khi hợp lý?
- [ ] Đã phân biệt một lựa chọn với tập nhiều lựa chọn (`EnumSet`)?
- [ ] Nếu enum là trạng thái, transition rules được kiểm riêng?
- [ ] Không dùng enum cho IDs/dữ liệu có số lượng dynamic không thể biết trước?
- [ ] Có validate `null` và unknown external inputs không?
- [ ] `valueOf` có đang được dùng đúng case-sensitive constant names?
- [ ] Nếu external contract dùng text codes, đã tách stable code khỏi `name()`?
- [ ] Không lưu `ordinal()` như business ID hoặc persisted code?
- [ ] `toString()` chỉ phục vụ display nếu đã override?
- [ ] Metadata của constants có immutable fields khi có thể?
- [ ] Không đặt per-request mutable state vào enum constant?
- [ ] Nếu behavior per constant phức tạp, đã cân nhắc strategy/service khác?
- [ ] Các `EnumMap` có mapping đầy đủ nếu yêu cầu không?
- [ ] Các `switch` expressions có phản ánh tất cả constants cần xử lý?
- [ ] Thêm/đổi tên constant có đi kèm tests, schema/API review không?
- [ ] Có dùng interface/registry khi hệ thống thực sự cần mở rộng runtime?
- [ ] Code samples có tên file/public class đúng và lệnh `javac`/`java` chạy với Java 17+?
- [ ] stdout không phụ thuộc dữ liệu không ổn định như hash codes, timing hoặc Map iteration order không xác định?

---

**Ghi nhớ cuối bài:** Trong Java, **`enum` là một kiểu mô hình hóa tập **constant instances có tên** được quy định hữu hạn trong khai báo source**. Nó phù hợp với những miền giá trị như mức ưu tiên, hướng, trạng thái, chế độ hay quyền, nơi compiler có thể phân biệt types và kiểm những lựa chọn hợp lệ. Enum không chỉ là chuỗi hay số: constants là objects, có thể gắn metadata/behavior, dùng `==`, `switch`, `EnumSet` và `EnumMap`. Nhưng tập constant đóng không làm tất cả dữ liệu immutable hoặc mọi chuyển trạng thái hợp lệ; `null`/input từ bên ngoài vẫn phải validate, và `ordinal()` không phải ID lưu trữ ổn định. **Hãy dùng enum khi danh sách lựa chọn là một quyết định thiết kế ổn định theo phiên bản; dùng data-driven models hoặc interfaces khi danh sách cần được mở rộng động.**