# Không khởi tạo `new T()` và cách truyền `Supplier<T>` trong Java Generics

## 1. Tại sao bài toán này xuất hiện?

Bạn đang viết một class generic dùng để quản lý hoặc khởi tạo nhiều kiểu dữ liệu khác nhau:

```java
class Box<T> {
    T create() {
        // Mong muốn tạo một object mới có đúng kiểu T.
        return new T(); // Không biên dịch.
    }
}
```

Ý định có vẻ hợp lý: caller dùng `Box<Customer>` thì `create()` tạo `Customer`, còn `Box<Order>` thì tạo `Order`. Tuy nhiên Java **không cho phép `new T()`** khi `T` là type variable. Thông báo từ `javac` thường có dạng:

```text
error: unexpected type
  required: class
  found:    type parameter T
```

Ngay cả khi gắn bound cho biến kiểu, ví dụ `<T extends Number>`, trình biên dịch vẫn không thể cấp phát trực tiếp bằng `new T()`. Java không có cú pháp bound kiểu “`T` bắt buộc có public no-argument constructor” như một số ngôn ngữ khác.

Giải pháp thường gọn và dễ kiểm thử nhất là **để caller cung cấp chiến lược tạo object** thông qua `Supplier<T>`:

```java
import java.util.function.Supplier;

class Box<T> {
    private final Supplier<T> factory;

    Box(Supplier<T> factory) {
        this.factory = factory;
    }

    T create() {
        return factory.get();
    }
}
```

Caller quyết định cách tạo instance:

```java
Box<StringBuilder> box = new Box<>(StringBuilder::new);
StringBuilder builder = box.create();
```

Ở đây `StringBuilder::new` là **constructor reference**, được chuyển thành một implementation của `Supplier<StringBuilder>`. Khi `create()` gọi `factory.get()`, logic tạo object chạy ở đúng nơi đã biết class cụ thể.

Bài này giải thích nguyên nhân từ type erasure, cách dùng `Supplier<T>` và `Supplier<? extends T>`, constructor reference, lambda có tham số, thiết kế factory, kiểm soát null/freshness, checked exceptions và các lỗi thường gặp. Ví dụ chính dùng Java 17 và đã được biên dịch, chạy kiểm tra.

## 2. `T` là type variable, không phải tên một class cụ thể

Một class generic:

```java
class Repository<T> {
    T value;
}
```

định nghĩa **một type variable `T`** để compiler kiểm tra các phép gán và quan hệ kiểu tại source. Chẳng hạn:

```java
Repository<String> strings = new Repository<>();
Repository<Integer> numbers = new Repository<>();
```

`String` và `Integer` là type arguments khác nhau khi dùng `Repository<T>`. Nhưng chúng không khiến JVM tạo các bản class `Repository<String>` và `Repository<Integer>` riêng biệt theo mỗi argument.

Phần lớn thông tin type argument generic bị loại khỏi những method/field descriptors ở bytecode theo cơ chế **type erasure** (*xóa kiểu*). Với type variable không có bound tường minh, erasure thường trở thành `Object`.

Điều đó tạo ra một giới hạn: bên trong class generic, compiler không có một biểu thức `new` tự động xác định runtime class nào sẽ được tạo khi caller chọn `T`.

### 2.1. Phân biệt dùng `T` và tạo `T`

Bạn **được** viết:

```java
class Holder<T> {
    private T value;

    void put(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Bởi vì code chỉ lưu và trả lại các object đã được bên ngoài tạo, compiler kiểm tra kiểu `T` qua hợp đồng generic.

Bạn **không được** viết:

```java
class Holder<T> {
    T make() {
        return new T(); // Lỗi biên dịch.
    }
}
```

`new` cần biết kiểu class có thể khởi tạo và constructor tương ứng ở source. `T` chỉ là type variable: nó không xác định một constructor cụ thể mà method này có quyền gọi.

**Ghi nhớ:** `T` hữu ích để liên kết *kiểu của giá trị* giữa tham số, field và kết quả. Nó **không phải một “constructor động”**.

### 2.2. Bound không làm `new T()` hợp lệ

Xét:

```java
class Factory<T extends Number> {
    T make() {
        return new T(); // Vẫn sai.
    }
}
```

`T extends Number` chỉ yêu cầu type argument là `Number` hoặc một subtype thích hợp. Caller có thể chọn `Integer`, `Double`, một `Number` tự định nghĩa, v.v. Các lớp đó không có chung một constructor public không tham số.

Ngay cả khi bound là một class có constructor public không tham số:

```java
class Base {
    public Base() {
    }
}

class Generic<T extends Base> {
    // T make() { return new T(); } // Vẫn sai.
}
```

Compiler không thể suy luận rằng **mọi subtype `T`** sẽ có constructor phù hợp. Constructor không phải một member polymorphic được thừa kế như instance method; subclass có thể chỉ có các constructor nhận tham số hoặc có quyền truy cập khác.

### 2.3. Vì sao không dùng `T.class`?

```java
class Holder<T> {
    // Class<T> type() { return T.class; } // Không hợp lệ.
}
```

`T.class` không phải class literal hợp lệ vì `T` là type variable, không phải tên một class cụ thể hiện diện ở runtime. Khi thực sự cần class token, caller phải cung cấp `Class<T>` như một giá trị riêng.

```java
static <T> String className(Class<T> type) {
    return type.getName();
}

// className(String.class) -> "java.lang.String"
```

`Class<T>` là một công cụ khác với `Supplier<T>`: class token mô tả một runtime class, còn Supplier mô tả **hành động cung cấp giá trị**. Supplier thường phù hợp hơn khi mục tiêu là tạo object, đặc biệt với constructor có tham số, dependency injection hoặc factory tùy chỉnh.

## 3. `Supplier<T>` là gì?

`java.util.function.Supplier<T>` là một functional interface tiêu chuẩn của Java:

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

Nó có một abstract method **không nhận tham số** và trả một giá trị kiểu `T`.

Có thể xem Supplier như một lời hứa:

> “Khi được gọi `get()`, tôi sẽ cung cấp một giá trị tương thích với `T`.”

Nó **không hứa**:

- Mỗi lần gọi trả một object mới.
- Kết quả luôn khác null.
- Việc tính toán luôn nhanh hoặc không có tác dụng phụ.
- Có thể gọi đồng thời an toàn trên nhiều thread.
- Phương thức `get()` không bao giờ ném unchecked exception.

Những thuộc tính đó phải được quy định thêm trong hợp đồng của ứng dụng hoặc được đảm bảo bởi implementation cụ thể.

### 3.1. Supplier khác `Consumer`, `Function` và `Callable`

| Interface | Abstract method | Trường hợp thường dùng |
| --- | --- | --- |
| `Supplier<T>` | `T get()` | Cung cấp/tạo giá trị không có input tại thời điểm gọi. |
| `Function<A,R>` | `R apply(A input)` | Tạo/chuyển đổi kết quả có một input. |
| `BiFunction<A,B,R>` | `R apply(A a, B b)` | Tạo/chuyển đổi với hai input. |
| `Consumer<T>` | `void accept(T value)` | Tiêu thụ hoặc xử lý một giá trị; không trả kết quả. |
| `Callable<T>` | `T call() throws Exception` | Tác vụ trả giá trị, có chữ ký cho checked exception. |

`Supplier<T>` phù hợp nhất khi object có thể được tạo mà **không cần đối số được truyền cho `get()`**. Điều đó không có nghĩa constructor thật phải không có tham số: lambda có thể **capture** các giá trị cấu hình được cung cấp từ trước.

## 4. Giải pháp cơ bản: truyền Supplier vào generic class

Thiết kế:

```java
import java.util.Objects;
import java.util.function.Supplier;

final class Box<T> {
    private final Supplier<? extends T> factory;

    Box(Supplier<? extends T> factory) {
        this.factory = Objects.requireNonNull(factory, "factory");
    }

    T newValue() {
        return Objects.requireNonNull(
                factory.get(), "factory returned null");
    }
}
```

Lợi ích:

1. Class `Box<T>` **không cần biết** `T` là class nào.
2. Caller cung cấp cách tạo object, có thể thay bằng constructor reference, lambda hoặc method reference.
3. `newValue()` trả về `T`, nên caller không cần cast.
4. Có thể thay Supplier bằng factory giả trong unit test.
5. Có thể kiểm tra rõ ràng việc factory được truyền vào là null và factory trả null.

Cách dùng:

```java
Box<StringBuilder> box = new Box<>(StringBuilder::new);

StringBuilder first = box.newValue();
StringBuilder second = box.newValue();

System.out.println(first != second); // true với constructor reference này
```

`StringBuilder::new` tạo builder mới mỗi lần được gọi, vì constructor không có tham số được thực thi mỗi lần Supplier chạy.

### 4.1. Vì sao dùng `Supplier<? extends T>`?

Một khai báo đơn giản:

```java
Supplier<T> factory;
```

đủ dùng cho nhiều trường hợp. Nhưng khi factory có thể trả subtype của `T`, khai báo:

```java
Supplier<? extends T> factory;
```

thường linh hoạt hơn. Ví dụ một API muốn trả kiểu tổng quát `Number`, nhưng factory thực tế tạo `Integer`:

```java
Supplier<Integer> integers = () -> Integer.valueOf(7);
Supplier<? extends Number> numbers = integers;

Number value = numbers.get();
```

`Supplier<? extends T>` phù hợp vì `Supplier` là **producer**: bạn đọc một giá trị từ factory. Đây là ứng dụng trực tiếp của quy tắc PECS (*Producer Extends, Consumer Super*).

Không nên đổi thành `Supplier<? super T>` khi mục tiêu là lấy một `T`, vì factory kiểu `Supplier<? super T>` có thể trả một supertype rộng hơn `T`, compiler không thể hứa kết quả là `T`.

### 4.2. Vì sao kiểm tra `Objects.requireNonNull`?

```java
Objects.requireNonNull(factory, "factory");
```

giúp lỗi xuất hiện tại lúc tạo `Box`, thay vì đợi đến `newValue()` rồi vô tình gọi `.get()` trên tham chiếu null.

```java
Objects.requireNonNull(factory.get(), "factory returned null");
```

thể hiện hợp đồng riêng: method `newValue()` **không chấp nhận kết quả null**. Nếu ứng dụng cho phép null như một giá trị có nghĩa, bỏ hoặc thay kiểm tra này bằng một API mô tả rõ ràng, ví dụ `Optional<T>` khi thích hợp.

Đừng thêm ràng buộc không-null mà bỏ qua contract: đôi khi Supplier được thiết kế có thể trả null để biểu thị “không có dữ liệu”.

## 5. Cung cấp Supplier bằng constructor reference

Một constructor không tham số có thể khớp `Supplier<T>`:

```java
class Customer {
    Customer() {
    }
}

Supplier<Customer> factory = Customer::new;
Customer customer = factory.get();
```

`Customer::new` không khởi tạo object ngay lúc viết biểu thức. Nó tạo một function object có hành vi gọi constructor khi `get()` được gọi.

### 5.1. Constructor phải truy cập được tại nơi viết reference

Một constructor reference như:

```java
Supplier<Customer> factory = Customer::new;
```

chỉ hợp lệ nếu compiler có thể truy cập constructor tương ứng từ vị trí expression và overload resolution chọn được constructor phù hợp với functional interface.

Một class có constructor `private` không thể được reference tùy ý từ code bên ngoài. Nhưng bạn có thể tạo Supplier **ở bên trong class** hoặc một factory method có quyền truy cập, rồi truyền nó ra ngoài mà không tiết lộ constructor.

### 5.2. Constructor không tham số có thể là implicit hoặc explicit

Ví dụ:

```java
class Empty {
}
```

Nếu không khai báo bất cứ constructor nào, compiler có thể tạo default constructor theo quy tắc của Java; `Empty::new` hợp lệ khi constructor ấy truy cập được từ nơi sử dụng.

Nếu class đã khai báo một constructor nhận tham số:

```java
class User {
    User(String name) {
    }
}
```

Java **không tự thêm** constructor không tham số. Khi đó `User::new` không thể khớp `Supplier<User>` nếu chỉ có `User(String)`; cần dùng lambda capture hoặc `Function<String,User>`.

### 5.3. `Class<T>` không phải constructor reference

Không thể viết một `T::new` tổng quát bên trong class generic:

```java
class Box<T> {
    // Supplier<T> factory = T::new; // Không hợp lệ.
}
```

`T` chưa phải một tên class có constructor xác định. Caller cần cung cấp `ActualClass::new` ở nơi biết class cụ thể.

## 6. Constructor có tham số: lambda capture

Với class:

```java
class Config {
    private final String region;

    Config(String region) {
        this.region = region;
    }

    String region() {
        return region;
    }
}
```

Không dùng được `Config::new` làm `Supplier<Config>` nếu chỉ có constructor `Config(String)`:

```java
// Không hợp lệ cho Supplier<Config>:
// Supplier<Config> factory = Config::new;
```

Nhưng có thể **capture giá trị region**:

```java
String region = "ap-southeast";

Supplier<Config> factory = () -> new Config(region);
Config first = factory.get();
```

Lambda ở đây không nhận tham số khi `.get()` được gọi; nó đã “giữ” giá trị `region` từ môi trường nơi Supplier được tạo.

Trong Java, local variable được capture phải là `final` hoặc **effectively final** — không bị gán lại sau khi được lambda capture theo quy tắc ngôn ngữ.

### 6.1. Capturing khác việc luôn tạo object ngay

```java
Config existing = new Config("ap-southeast");

Supplier<Config> reused = () -> existing;
Supplier<Config> fresh = () -> new Config("ap-southeast");
```

Hai Supplier cùng trả kiểu `Config`, nhưng có hành vi khác:

- `reused.get()` trả cùng `existing` qua mỗi lần gọi.
- `fresh.get()` thực hiện `new Config(...)` mỗi lần gọi.

Đừng suy luận từ **kiểu `Supplier<Config>`** rằng mỗi lần `.get()` chắc chắn cấp phát một object mới. Sự khác biệt phải được định nghĩa trong hợp đồng.

### 6.2. Dependency injection qua lambda

Một object có thể cần nhiều dependency:

```java
class Service {
    Service(String endpoint, int timeoutMillis) {
    }
}
```

Caller có thể cung cấp:

```java
String endpoint = "https://example.invalid";
int timeoutMillis = 1000;

Supplier<Service> serviceFactory =
        () -> new Service(endpoint, timeoutMillis);
```

Ví dụ URL là chuỗi minh họa cấu hình, không có truy cập mạng. Điều quan trọng là các dependency có sẵn tại **nơi dựng Supplier**. Class generic nhận `Supplier<Service>` không phải biết constructor đang nhận hai tham số hay cách cấu hình chúng.

Khi dependency thay đổi theo từng lời gọi, `Function`/`BiFunction` thường thích hợp hơn Supplier đã capture tham số cố định.

## 7. Khi nào dùng `Function` hoặc `BiFunction` thay Supplier?

`Supplier<T>` có method `.get()` không nhận argument. Nếu quá trình khởi tạo cần input **ở mỗi lần gọi**, bạn có thể dùng `Function<A,T>` hoặc `BiFunction<A,B,T>`.

Ví dụ `record` với hai thành phần:

```java
record Ticket(int id, String title) {
}
```

Có thể tạo một vé từ title trong một hàm:

```java
import java.util.function.Function;

Function<String, Ticket> createTicket =
        title -> new Ticket(7, title);

Ticket t = createTicket.apply("Java");
```

Nếu cả `id` và `title` là input:

```java
import java.util.function.BiFunction;

BiFunction<Integer, String, Ticket> ticketFactory =
        Ticket::new;

Ticket t = ticketFactory.apply(7, "Java");
```

`Ticket::new` ở đây khớp `BiFunction<Integer,String,Ticket>` vì record constructor có hai tham số `int` và `String`; compiler có thể sử dụng unboxing từ `Integer` khi cần theo quy tắc tương thích.

### 7.1. Generic factory function

```java
static <A, T> T createFrom(
        A input,
        java.util.function.Function<? super A, ? extends T> factory) {
    return java.util.Objects.requireNonNull(
            factory, "factory").apply(input);
}
```

`? super A` ở đầu vào của Function cho phép factory nhận kiểu rộng hơn `A`. `? extends T` ở đầu ra cho phép trả subtype của `T`. Đây là thiết kế linh hoạt khi factory đóng vai trò nhận input và tạo output.

Bản trên chưa kiểm tra kết quả null; nếu contract yêu cầu không-null, thêm `Objects.requireNonNull(factory.apply(input), ...)` tương tự ví dụ Box.

### 7.2. Khi constructor có checked exception

`Supplier<T>.get()` **không khai báo `throws` checked exception**. Nếu constructor bạn muốn gọi ném `IOException` hoặc checked exception khác, bạn không thể trực tiếp viết method reference/lambda ném checked exception ấy để gán cho Supplier thông thường, trừ khi xử lý exception bên trong lambda.

Ví dụ minh họa, cần import thích hợp:

```java
Supplier<String> fromFile = () -> {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of("input.txt"));
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
};
```

Đây là **đoạn minh họa**, không đọc file thực trong chương trình chạy chính. Nó wrap `IOException` thành unchecked exception; đây là lựa chọn API, không phải phương pháp luôn luôn nên dùng.

Nếu checked exception là thành phần quan trọng của hợp đồng, định nghĩa functional interface riêng có `throws`, hoặc cân nhắc `Callable<T>` (`call() throws Exception`), tùy mục tiêu. Không nên âm thầm nuốt exception trong Supplier rồi trả null nếu caller cần biết thất bại.

## 8. Ví dụ Java 17 hoàn chỉnh

Tạo file **`SupplierFactoryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class SupplierFactoryDemo {
    static final class Resource {
        private static int nextId;
        private final int id = ++nextId;

        int id() {
            return id;
        }
    }

    static final class Config {
        private final String region;

        Config(String region) {
            this.region = region;
        }

        String region() {
            return region;
        }
    }

    record Ticket(int id, String title) {}

    static final class Box<T> {
        private final Supplier<? extends T> factory;

        Box(Supplier<? extends T> factory) {
            this.factory = Objects.requireNonNull(factory, "factory");
        }

        T newValue() {
            return Objects.requireNonNull(
                    factory.get(), "factory returned null");
        }
    }

    static <T> List<T> createMany(
            int count, Supplier<? extends T> factory) {
        if (count < 0) {
            throw new IllegalArgumentException("negative count");
        }
        Objects.requireNonNull(factory, "factory");

        List<T> values = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            values.add(Objects.requireNonNull(
                    factory.get(), "factory returned null"));
        }
        return values;
    }

    static <A, T> T createFrom(
            A input, Function<? super A, ? extends T> factory) {
        return Objects.requireNonNull(factory, "factory").apply(input);
    }

    public static void main(String[] args) {
        Box<Resource> box = new Box<>(Resource::new);

        Resource a = box.newValue();
        Resource b = box.newValue();
        System.out.println("ids=" + a.id() + "," + b.id());
        System.out.println("distinct=" + (a != b));

        List<Resource> resources = createMany(2, Resource::new);
        System.out.println("batch=" + resources.size());
        System.out.println("batch-ids=" + resources.get(0).id()
                + "," + resources.get(1).id());

        Box<Config> config = new Box<>(
                () -> new Config("ap-southeast"));
        System.out.println("region=" + config.newValue().region());

        Ticket ticket = createFrom(
                "Java", title -> new Ticket(7, title));
        System.out.println("ticket=" + ticket.id()
                + ":" + ticket.title());

        Resource singleton = new Resource();
        Box<Resource> reused = new Box<>(() -> singleton);
        System.out.println("reused="
                + (reused.newValue() == reused.newValue()));

        try {
            new Box<String>(() -> null).newValue();
        } catch (NullPointerException e) {
            System.out.println("null-error=" + e.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 -Xlint:all SupplierFactoryDemo.java
java SupplierFactoryDemo
```

Ví dụ đã biên dịch thành công không có cảnh báo và cho stdout:

```text
ids=1,2
distinct=true
batch=2
batch-ids=3,4
region=ap-southeast
ticket=7:Java
reused=true
null-error=factory returned null
```

### 8.1. Diễn giải `ids=1,2` và `distinct=true`

`Resource::new` là factory gọi constructor của `Resource`. Trong chương trình chạy tuần tự này, mỗi invocation tạo một object mới và tăng `nextId`, nên có hai ID `1` và `2` và tham chiếu `a != b`.

**Không phải mọi Supplier đều bảo đảm điều này.** Bằng chứng về object mới đến từ implementation cụ thể `Resource::new`, không đến từ type `Supplier<Resource>`.

Biến đếm tĩnh `nextId` được dùng đơn giản để minh họa và **không thread-safe** nếu code được gọi đồng thời. Ứng dụng thực muốn cấp ID duy nhất trong môi trường đa luồng phải có cơ chế đồng bộ hoặc ID generator phù hợp.

### 8.2. Diễn giải `batch=2` và `batch-ids=3,4`

`createMany` gọi `factory.get()` trong một vòng lặp. Vì caller truyền `Resource::new`, hai lần gọi tiếp theo tạo resource mang ID `3` và `4`.

Đối với `count = 0`, method trả danh sách rỗng; nó vẫn kiểm tra factory khác null. Đối với `count < 0`, method ném `IllegalArgumentException`. Nếu factory ném exception ở lần thứ `k`, method không hoàn tất và exception lan ra ngoài — đoạn ví dụ này **không** tự rollback những object đã được tạo trước đó.

### 8.3. Diễn giải `region=ap-southeast`

`Config` chỉ có constructor nhận một `String`. Caller dùng:

```java
() -> new Config("ap-southeast")
```

để tạo một `Supplier<Config>` không có tham số `get()`. Factory capture cấu hình, và mỗi invocation gọi constructor `Config(String)`.

### 8.4. Diễn giải `ticket=7:Java`

`createFrom` nhận một input `String` và một `Function` dùng nó để tạo `Ticket`. Nếu `id` cũng cần được cung cấp cho mỗi lần gọi, `BiFunction<Integer,String,Ticket>` và `Ticket::new` là lựa chọn trực tiếp hơn.

### 8.5. Diễn giải `reused=true`

`new Box<>(() -> singleton)` trả **cùng object** mỗi lần gọi `.get()`. Điều này chứng minh `Supplier<T>` là interface *cung cấp giá trị*, không phải hợp đồng *luôn tạo instance mới*. Nếu tên method `newValue()` của API yêu cầu object mới, cần tài liệu hóa invariant và thiết kế factory/test bảo đảm điều đó.

### 8.6. Diễn giải `null-error=...`

Ví dụ chủ động gọi `Objects.requireNonNull(factory.get(), "factory returned null")`. Một Supplier có quyền trả null theo hợp đồng chung của `Supplier`, nhưng `Box` đã bổ sung hợp đồng **không chấp nhận null** và báo lỗi ngay tại boundary.

Nếu trường hợp “không tạo được object” là một trạng thái nghiệp vụ bình thường, cân nhắc `Supplier<Optional<T>>` hoặc một kiểu kết quả riêng, thay vì ném `NullPointerException` nếu contract không mong muốn.

## 9. Ví dụ cố tình không biên dịch: `new T()` và `T.class`

Tạo file riêng **`InvalidNewT.java`**:

```java
class InvalidNewT<T extends Number> {
    T create() {
        return new T();
    }

    Class<T> token() {
        return T.class;
    }
}
```

Biên dịch:

```bash
javac --release 17 InvalidNewT.java
```

Đây là chương trình **cố tình sai**. `javac --release 17` đã trả về hai diagnostic:

```text
error: unexpected type
  required: class
  found:    type parameter T
```

và:

```text
error: cannot select from a type variable
```

Lỗi đầu tiên đến từ `new T()`. Lỗi thứ hai đến từ `T.class`.

Sửa đúng bằng cách thay thiết kế:

```java
final class GenericCreator<T> {
    private final Supplier<? extends T> factory;

    GenericCreator(Supplier<? extends T> factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    T create() {
        return factory.get();
    }
}
```

Đây là class minh họa cần import `java.util.function.Supplier` và `java.util.Objects` nếu đặt trong file riêng. Caller phải cung cấp `SomeConcreteType::new` hoặc lambda khi tạo `GenericCreator<SomeConcreteType>`.

Đừng cố bỏ bound `<T extends Number>` để sửa lỗi `new T()`; bỏ bound không làm compiler có được constructor của `T`.

## 10. Vì sao không tự dùng Reflection để gọi constructor?

Một cách khác là nhận **class token**:

```java
static <T> T createWithNoArgs(Class<T> type)
        throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
```

Trong ví dụ này, `Class<T>` mang runtime class cụ thể, để Reflection tra cứu constructor không tham số. Nó có khác biệt lớn với Supplier:

| Tiêu chí | `Supplier<T>` | `Class<T>` + Reflection |
| --- | --- | --- |
| Ai quyết định cách tạo object? | Caller cung cấp hành vi bất kỳ | Generic code cố tìm constructor từ class token |
| Có cần constructor không tham số? | Không; lambda có thể capture đối số | Có nếu code gọi `getDeclaredConstructor()` không tham số |
| Có thể dùng static factory/singleton/pool? | Có | Không tự động, trừ khi thiết kế thêm |
| Checked exception từ reflection | Không có ở `Supplier.get()` | Có thể có `NoSuchMethodException`, `IllegalAccessException`, `InvocationTargetException`, `InstantiationException` |
| Phạm vi truy cập | Compiler kiểm tra method reference/lambda ở nơi tạo | Reflection chịu quy tắc access/module; `getDeclaredConstructor()` không có nghĩa luôn được phép invoke |
| Unit test bằng stub/fake | Dễ truyền Supplier giả | Cần class thực hoặc thiết kế thêm abstraction |
| Độ phức tạp API | Thường ít boilerplate | Cần xử lý lỗi reflection và chính sách access |

Reflection hữu ích nếu bạn đang viết container, serializer hoặc framework cần tạo class được xác định động. Nhưng đối với việc tạo `T` mà caller đã biết constructor hoặc chiến lược xây dựng, `Supplier<T>` thường đơn giản và minh bạch hơn.

### 10.1. `Class<T>` không bảo đảm constructor tồn tại

```java
Class<T> type;
```

không chứng minh có constructor public không tham số, cũng không chứng minh type là concrete class thay vì interface/abstract class. Reflection có thể thất bại do thiếu constructor, constructor không truy cập được, class abstract hoặc exception được constructor ném.

Không nên dùng `Class.newInstance()` như giải pháp mặc định: API này đã bị deprecated; thường nên dùng `getDeclaredConstructor().newInstance()` khi thực sự chọn hướng reflection.

### 10.2. Constructor parameterized khó được suy ra hoàn toàn bằng reflection

Nếu `T` chỉ có constructor nhận `String`, generic method cần biết tên, số lượng, kiểu và giá trị tham số, cùng chính sách chọn overload. Đây là lý do truyền factory/lambda thường tốt hơn:

```java
Supplier<Config> creator = () -> new Config("ap-southeast");
```

Constructor được compiler kiểm tra tại source; generic class không cần tự giải quyết reflective overload hay access.

## 11. Đưa Supplier vào generic method thay vì giữ trong class

Không phải mọi thiết kế đều cần lưu factory thành field. Bạn có thể yêu cầu factory trực tiếp khi gọi:

```java
static <T> T make(Supplier<? extends T> supplier) {
    return Objects.requireNonNull(supplier, "supplier").get();
}
```

Dùng:

```java
StringBuilder value = make(StringBuilder::new);
```

Hoặc method tạo nhiều phần tử:

```java
static <T> List<T> createMany(
        int count, Supplier<? extends T> supplier) {
    if (count < 0) {
        throw new IllegalArgumentException("negative count");
    }
    Objects.requireNonNull(supplier, "supplier");

    List<T> values = new ArrayList<>();
    for (int i = 0; i < count; i++) {
        values.add(supplier.get());
    }
    return values;
}
```

Đoạn trên là method minh họa, cần import `java.util.List`, `java.util.ArrayList`, `java.util.Objects` và `java.util.function.Supplier`. Nếu muốn cấm null, thêm kiểm tra kết quả `get()` như chương trình hoàn chỉnh.

### 11.1. Khi nào nên injection qua constructor?

Giữ `Supplier<? extends T>` trong field khi class cần tạo nhiều `T` qua nhiều method hoặc nhiều lần sử dụng. Ưu điểm là:

- Một lần thiết lập factory, nhiều lần dùng.
- Dễ thay implementation trong unit test.
- Generic class ít phụ thuộc vào class cụ thể.
- Phù hợp inversion of control hoặc dependency injection đơn giản.

Nếu factory chỉ cần đúng một lần, truyền trực tiếp vào method có thể gọn hơn.

### 11.2. Có nên lưu `Supplier<T>` tĩnh trong generic class?

Một trường `static` không thể đơn giản “mang T của instance”:

```java
class Registry<T> {
    // static Supplier<T> factory; // Không hợp lệ:
    // cannot reference non-static type variable T.
}
```

`T` thuộc về type parameter của **class instance**, không phải một tham số riêng của static field. Nên lưu factory ở **instance field**, hoặc thiết kế static generic method có type parameter riêng:

```java
static <T> T create(Supplier<T> factory) {
    return factory.get();
}
```

Điều này tránh nhầm lẫn giữa type variable ở cấp class và cấp method.

## 12. Thiết kế hợp đồng Supplier thật rõ

Khi bạn viết một API như:

```java
T create();
```

hãy làm rõ mục đích “create” bao gồm điều gì. Một Supplier chung có thể hợp lệ nhưng không thỏa mong đợi ứng dụng.

### 12.1. Có phải trả một object mới mỗi lần?

```java
Supplier<StringBuilder> fresh = StringBuilder::new;

StringBuilder shared = new StringBuilder();
Supplier<StringBuilder> cached = () -> shared;
```

`fresh.get()` tạo builder mới; `cached.get()` trả lại cùng builder. Cả hai cùng thuộc kiểu `Supplier<StringBuilder>`.

Nếu API yêu cầu *fresh instance per call*, hãy ghi cụ thể trong JavaDoc/hợp đồng và kiểm thử. Chỉ truyền một Supplier không chứng minh freshness.

### 12.2. Supplier có thể có side effect

```java
AtomicInteger sequence = new AtomicInteger();

Supplier<Integer> nextId = sequence::incrementAndGet;
```

Ví dụ này cần import `java.util.concurrent.atomic.AtomicInteger`. Mỗi lần `get()` thay đổi state bên ngoài Supplier. Kết quả phụ thuộc số lần gọi và thứ tự gọi.

Không nên tự cho rằng gọi `.get()` hai lần sẽ cho kết quả bằng nhau hoặc không thay đổi state.

### 12.3. Supplier có thể đắt hoặc thất bại

Factory có thể mở file, thiết lập socket, gọi một service, hoặc khởi tạo resource đắt. Nếu method `createMany(1000, factory)` gọi `get()` 1000 lần, đó có thể là thao tác tốn kém.

Nếu Supplier gặp exception ở lần gọi thứ năm, những object đã được tạo trong bốn lần trước có thể cần cleanup. Generic factory code không tự có transaction/rollback chỉ vì trả `List<T>`.

### 12.4. Supplier không mặc nhiên thread-safe

Một Supplier giữ mutable state không đồng bộ có thể xảy ra data race khi nhiều thread gọi `.get()` cùng lúc. Thread safety phụ thuộc implementation của factory và các object mà nó capture.

Nếu dùng nhiều thread, hãy xem:

- Các dependency được capture có mutable không?
- Counter hoặc cache có đồng bộ không?
- Có dùng singleton mutable được chia sẻ giữa nhiều caller không?
- Logic tạo object có được phép chạy đồng thời không?

Một constructor reference đơn giản không tự động bảo đảm toàn bộ quy trình tạo object an toàn trong mọi ứng dụng.

### 12.5. Nullable factory result

`Supplier<T>` được phép trả null. Nếu API cấm null, validate tại boundary:

```java
T value = Objects.requireNonNull(
        supplier.get(), "factory returned null");
```

Nếu null đại diện cho trạng thái bình thường, có thể dùng kết quả `Optional<T>` hoặc một `Result<T,Error>` do ứng dụng định nghĩa. Đừng dùng `Optional` bừa bãi cho mọi field; cần phân biệt “không có kết quả” với “factory lỗi”.

## 13. Constructor reference, lambda và method reference khác nhau thế nào?

Ba Supplier sau đều có thể cung cấp một object kiểu `T` trong những hoàn cảnh thích hợp:

```java
Supplier<StringBuilder> a = StringBuilder::new;
Supplier<StringBuilder> b = () -> new StringBuilder();
Supplier<StringBuilder> c = FactoryMethods::newBuilder;
```

Với một class hỗ trợ:

```java
class FactoryMethods {
    static StringBuilder newBuilder() {
        return new StringBuilder();
    }
}
```

- `StringBuilder::new` là **constructor reference**.
- `() -> new StringBuilder()` là **lambda** gọi constructor.
- `FactoryMethods::newBuilder` là **method reference** tới một static factory method.

Tất cả có thể khớp `Supplier<StringBuilder>` vì method đích không cần input và trả `StringBuilder`.

### 13.1. Ưu tiên cách nào?

Dùng `SomeClass::new` khi constructor có chữ ký phù hợp và không cần thêm xử lý.

Dùng lambda khi:

- Constructor cần các tham số được capture.
- Cần validate/thay đổi logic trước hoặc sau khi tạo.
- Cần chọn một trong nhiều implementation theo cấu hình.
- Cần chuyển checked exception sang hợp đồng lỗi khác một cách có chủ đích.

Dùng method reference như `Factories::create` khi đã có static factory rõ nghĩa hoặc logic tạo object phức tạp được đóng gói ở một phương thức độc lập.

### 13.2. Method reference được giải quyết tại compile time

`SomeClass::new` không tìm constructor bằng reflection lúc gọi. Compiler dùng **target type** của functional interface để xác định constructor overload thích hợp. Vì thế:

```java
Supplier<StringBuilder> supplier = StringBuilder::new;
Function<Integer, StringBuilder> sized = StringBuilder::new;
```

có thể chọn những constructor khác nhau của `StringBuilder`, lần lượt không tham số hoặc nhận capacity.

Nếu chỉ viết:

```java
// var creator = StringBuilder::new; // Không có target type phù hợp.
```

một method/constructor reference không tự có kiểu chức năng độc lập để suy ra chỉ từ `var`; nó cần một **target functional interface** phù hợp. Hãy gán cho `Supplier<StringBuilder>` hoặc truyền vào một method có tham số nhận Supplier.

## 14. Các lựa chọn thay thế trong thiết kế hướng đối tượng

### 14.1. Truyền sẵn object thay vì factory

Nếu code chỉ cần một object để lưu hoặc xử lý:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Không cần Supplier khi không có nhu cầu tạo object trong tương lai.

### 14.2. Dùng factory interface domain

Nếu logic khởi tạo có nhiều thao tác hoặc checked exception riêng:

```java
interface ConnectionFactory<T> {
    T open(String endpoint) throws Exception;
}
```

Một interface có tên domain và method nhận tham số có thể rõ nghĩa hơn `Supplier<T>`. Không nên ép mọi factory vào `Supplier<T>` khi contract thật đòi endpoint, timeout, validation, resource cleanup hoặc xử lý lỗi phức tạp.

### 14.3. Template method qua abstract class

Một class generic có thể giao quyền tạo object cho subclass:

```java
abstract class Creator<T> {
    protected abstract T create();

    T make() {
        return create();
    }
}
```

Subclass concrete biết `T`:

```java
class StringCreator extends Creator<String> {
    @Override
    protected String create() {
        return "Java";
    }
}
```

Điều này hợp lệ vì subclass triển khai việc tạo `String` cụ thể. Tuy nhiên nó yêu cầu kế thừa để thay đổi hành vi. `Supplier<T>` thường linh hoạt hơn vì dùng **composition** và lambda/constructor reference.

## 15. Sai lầm phổ biến và cách sửa

### Sai lầm 1 — “Đã có `<T>` thì dùng `new T()` được”

**Sai.** `<T>` không có nghĩa compiler biết runtime class hoặc constructor cần gọi. Truyền `Supplier<T>`/`Supplier<? extends T>` từ caller hoặc thiết kế factory khác.

### Sai lầm 2 — “`T extends SomeClass` bảo đảm mọi subtype có constructor không tham số”

**Sai.** Constructor không phải member instance được thừa kế; subclass có thể chỉ có constructor nhận tham số hoặc không thể được tạo. Bound không giải quyết bài toán này.

### Sai lầm 3 — “`Supplier<T>` luôn tạo object mới”

**Sai.** `() -> existing` trả cùng object. Nếu cần một object mới mỗi lần, document và test điều kiện đó; dùng constructor reference hoặc factory có invariant tương ứng.

### Sai lầm 4 — “Constructor reference tự động dùng được với mọi constructor”

**Sai.** `Supplier<T>` không nhận tham số. `User(String)` không khớp trực tiếp `Supplier<User>`; dùng `() -> new User("name")` hoặc `Function<String,User>`.

### Sai lầm 5 — “Lưu `Class<T>` là đủ để tạo mọi loại `T`”

**Sai.** `Class<T>` không bảo đảm class concrete, không bảo đảm constructor truy cập được hoặc không tham số, và không quyết định dependency cần inject. Reflection cần xử lý thêm lỗi và quyền truy cập.

### Sai lầm 6 — “Không thể dùng Supplier với interface hoặc abstract type”

**Sai.** Supplier có thể trả bất kỳ subtype phù hợp với `T`. Ví dụ `Supplier<? extends Animal>` có thể tạo `Dog`, dù bạn không thể `new Animal()` khi `Animal` abstract. Chính factory concrete quyết định implementation.

### Sai lầm 7 — “Chỉ cần `Supplier<T>` là không bao giờ có null”

**Sai.** Supplier có thể trả null. Cần hợp đồng và kiểm tra tại boundary nếu yêu cầu non-null.

### Sai lầm 8 — “Supplier không có tham số nên không dùng được constructor có tham số”

**Sai.** Lambda có thể capture tham số đã có tại nơi tạo Supplier:

```java
Supplier<Config> factory = () -> new Config("ap-southeast");
```

Nếu giá trị phải thay đổi mỗi lần gọi, chọn `Function` hoặc `BiFunction` phù hợp.

### Sai lầm 9 — “`Supplier.get()` có thể khai báo mọi checked exception”

**Sai.** `get()` không có checked `throws`. Một lambda gán cho Supplier phải xử lý checked exception hoặc dùng API chức năng khác có `throws`.

### Sai lầm 10 — “Factory injection tự động an toàn cho đa luồng”

**Sai.** Supplier có thể capture state mutable, giữ cache hoặc dùng bộ đếm không đồng bộ. Thread safety phải được thiết kế trong factory thực tế.

### Sai lầm 11 — “`Supplier<? super T>` vẫn trả `T`”

**Sai.** Khi producer trả supertype, compiler không thể khẳng định kết quả là `T`. Nếu chỉ **đọc giá trị T**, dùng `Supplier<? extends T>` hoặc `Supplier<T>`.

### Sai lầm 12 — “Suppress lỗi `new T()` bằng annotation”

**Không thể.** Đây là **lỗi biên dịch**, không phải unchecked warning. `@SuppressWarnings` không làm `new T()` trở nên hợp lệ. Phải đổi API để cung cấp chiến lược tạo object.

## 16. Checklist triển khai trong dự án

| Câu hỏi | Thiết kế phù hợp |
| --- | --- |
| Có thật cần tạo object bên trong generic class không? | Nếu chỉ lưu giá trị có sẵn, nhận `T` trực tiếp thay vì Supplier. |
| Caller biết class concrete và constructor không tham số không? | Truyền `Concrete::new`. |
| Constructor cần cấu hình cố định từ caller không? | Truyền `() -> new Concrete(config)`. |
| Tham số khởi tạo thay đổi theo mỗi lần gọi không? | Dùng `Function`/`BiFunction` hoặc factory domain-specific. |
| Có cần factory trả subtype của `T` không? | Cân nhắc `Supplier<? extends T>`. |
| `get()` được phép trả null không? | Viết contract rõ và validate/encode absence. |
| Phải trả object mới mỗi lần không? | Document và test freshness, đừng suy từ chữ `Supplier`. |
| Có checked exception trong logic tạo không? | Wrap có chủ đích hoặc chọn functional interface có `throws`. |
| Resource tạo ra có cần close/rollback không? | Thiết kế ownership, cleanup và xử lý partial failure. |
| Gọi factory ở nhiều thread không? | Kiểm tra state capture, singleton, synchronization và thread safety. |
| Có cần dùng Reflection thực sự không? | Chỉ khi class được chọn động và chấp nhận xử lý constructor/access/exception. |
| Unit test sẽ cung cấp object thế nào? | Truyền `() -> fake`, `FakeType::new` hoặc factory có đếm số lần gọi. |

Một quy trình sửa từ code `new T()` có thể là:

1. Xác định lý do generic code muốn tạo `T` và thời điểm tạo.
2. Xác định caller nào biết concrete type và dependencies.
3. Thiết kế constructor/method nhận `Supplier<? extends T>` hoặc factory có input tương ứng.
4. Chuyển logic `new Concrete(...)` về phía caller bằng constructor reference/lambda.
5. Định nghĩa hợp đồng null, freshness, exception, ownership và concurrency.
6. Viết test với cả factory bình thường và factory lỗi/null/reuse.
7. Biên dịch với `javac --release 17 -Xlint:all` và thử luồng runtime.
8. Đảm bảo không còn cast unchecked hoặc reflection không cần thiết chỉ để khởi tạo `T`.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao class generic sau không compile?

```java
class Maker<T> {
    T make() {
        return new T();
    }
}
```

<details>
<summary>Đáp án</summary>

`T` là type variable, không phải một concrete class có constructor xác định ở source. Java không hỗ trợ generic constructor bound yêu cầu mọi subtype có constructor không tham số. Truyền một factory như `Supplier<T>` từ caller.

</details>

**Câu 2.** Nếu caller có constructor không tham số của `Invoice`, làm sao cung cấp factory cho `Box<Invoice>`?

<details>
<summary>Đáp án</summary>

Có thể viết `new Box<>(Invoice::new)` khi constructor truy cập được và type inference/target type thích hợp. `Invoice::new` tương ứng Supplier tạo `Invoice` khi `.get()` được gọi.

</details>

**Câu 3.** Một class chỉ có constructor `User(String name)`. Cần factory như thế nào?

<details>
<summary>Đáp án</summary>

Nếu tên được cố định từ đầu, dùng `() -> new User("Lan")` làm `Supplier<User>`. Nếu tên thay đổi ở mỗi lần tạo, dùng `Function<String,User>` với `User::new` và `.apply(name)`.

</details>

**Câu 4.** `Supplier<Resource>` có bảo đảm mỗi `get()` trả object mới không?

<details>
<summary>Đáp án</summary>

Không. `Resource::new` sẽ gọi constructor mỗi lần, nhưng `() -> existingResource` có thể luôn trả cùng object. Freshness là invariant bổ sung của implementation, không nằm trong interface `Supplier`.

</details>

**Câu 5.** Vì sao có thể lưu `Supplier<? extends Number>` nhận một `Supplier<Integer>`?

<details>
<summary>Đáp án</summary>

Supplier là producer: mỗi `get()` trả `Integer` và `Integer` là subtype của `Number`, nên có thể đọc kết quả như `Number`. `? extends Number` diễn đạt sự tương thích đó mà không yêu cầu `Supplier<Integer>` là subtype của `Supplier<Number>`.

</details>

**Câu 6.** Factory trả null có bị `Supplier<T>` tự từ chối không?

<details>
<summary>Đáp án</summary>

Không. Interface không cấm null. API dùng Supplier phải tự quyết định xử lý: chấp nhận null, ném lỗi rõ ràng bằng `Objects.requireNonNull`, hoặc biểu diễn trường hợp không có giá trị bằng kiểu kết quả phù hợp.

</details>

**Câu 7.** `Class<T>` và `Supplier<T>` khác nhau ở đâu?

<details>
<summary>Đáp án</summary>

`Class<T>` đại diện một class runtime để introspection/cast và có thể dùng reflection tìm constructor; nó không tự bảo đảm constructor khả dụng. `Supplier<T>` là hành vi cung cấp giá trị, có thể gọi constructor, static factory, cache hoặc logic khác. Nếu chỉ cần tạo giá trị từ caller, Supplier thường dễ dùng và dễ test hơn.

</details>

## 18. Kết luận

**Java không hỗ trợ `new T()` vì `T` là biến kiểu, không phải một tên class có constructor xác định tại điểm biên dịch.** Type erasure giải thích vì sao một class generic không có runtime specialization riêng cho mọi type argument, còn quy tắc constructor của Java không bảo đảm rằng mọi subtype `T` đều có constructor giống nhau.

Cách thiết kế thông dụng là **đưa hành vi tạo object từ caller vào generic code bằng `Supplier<T>` hoặc `Supplier<? extends T>`**:

```java
Box<StringBuilder> box = new Box<>(StringBuilder::new);
StringBuilder item = box.newValue();
```

Với constructor cần tham số cố định, dùng lambda capture; khi tham số thay đổi mỗi lần, dùng `Function`/`BiFunction` hoặc factory domain-specific. Khi thiết kế API, đừng quên rằng `Supplier.get()` có thể trả null, trả cùng object, có side effect hoặc ném unchecked exception. Generic factory chỉ thực sự hữu ích khi hợp đồng tạo object, kiểm soát dữ liệu và vòng đời object được mô tả rõ.