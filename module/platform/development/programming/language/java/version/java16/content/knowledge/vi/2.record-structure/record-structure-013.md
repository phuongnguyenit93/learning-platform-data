# Record lồng nhau và tính static ngầm định

## 1. Record có thể được khai báo bên trong kiểu khác

Record không nhất thiết phải là kiểu top-level. Java cho phép khai báo record bên trong class, interface hoặc một record khác. Record được khai báo như thành viên của kiểu bao ngoài được gọi là *member record*.

~~~java
class Order {
    record Item(String sku, int quantity) {}
}
~~~

Có thể dùng kiểu lồng qua tên đầy đủ:

~~~java
Order.Item item = new Order.Item("SKU-01", 2);
System.out.println(item.sku());
~~~

Điểm quan trọng là member record **ngầm định là static**. Vì vậy, `Item` không gắn với một instance cụ thể của `Order`; không cần tạo `Order` trước rồi mới tạo `Item`.

Quy tắc này là phần ổn định của Java record từ Java 16. Nó cũng áp dụng cho record được khai báo bên trong record khác và cho local record được khai báo trong một block.

Mục tiêu bài học:

- Nhận diện member record và local record.
- Hiểu ý nghĩa của tính static ngầm định.
- Tạo và tham chiếu nested record qua tên kiểu bao ngoài.
- Hiểu vì sao nested record không truy cập trực tiếp instance member của kiểu bao ngoài.
- Tổ chức generic record lồng nhau mà không phụ thuộc type parameter của outer class.
- Dùng record lồng nhau trong interface và mô hình thông điệp.
- Phân biệt nested record với component chứa một record khác.

## 2. Member record ngầm định là static

Khi khai báo record bên trong một class:

~~~java
class Customer {
    private String id;

    record Snapshot(String name) {}
}
~~~

Java hiểu `Snapshot` là một static member type. Có thể hình dung tương đương về mặt quan hệ thành viên:

~~~java
class Customer {
    private String id;

    static record Snapshot(String name) {}
}
~~~

Từ khóa `static` không cần viết trong khai báo member record vì tính chất này đã được quy định ngầm định. Điều đó có các hệ quả:

- `Snapshot` thuộc về kiểu `Customer`, không thuộc một object `Customer` cụ thể.
- Không có tham chiếu `Customer.this` tự động bên trong `Snapshot`.
- Không thể đọc trực tiếp field instance `id` của một object `Customer` bao ngoài.
- Có thể tạo `Customer.Snapshot` mà không cần tạo `Customer`.
- Nested record có thể truy cập thành viên static của kiểu bao ngoài theo quy tắc truy cập Java.

Ví dụ tạo object:

~~~java
Customer.Snapshot snapshot =
    new Customer.Snapshot("Lan");
~~~

Không dùng cú pháp tạo inner class thông thường:

~~~java
Customer customer = new Customer();

// Không hợp lệ: Snapshot là static member type,
// không phải inner class gắn với instance customer.
// Customer.Snapshot snapshot = customer.new Snapshot("Lan");
~~~

Đây là khác biệt thực tế giữa member record và một inner class không static thông thường.

## 3. Nested record không có enclosing instance

Một inner class không static thông thường có thể truy cập instance member của object bao ngoài:

~~~java
class Account {
    private final String accountId;

    Account(String accountId) {
        this.accountId = accountId;
    }

    class View {
        String accountId() {
            return Account.this.accountId;
        }
    }
}
~~~

Member record không có quan hệ enclosing instance như vậy:

~~~java
class Account {
    private final String accountId;

    Account(String accountId) {
        this.accountId = accountId;
    }

    record View(String label) {
        // Không hợp lệ: record View không có Account.this.
        // String id() {
        //     return Account.this.accountId;
        // }
    }
}
~~~

`View` chỉ biết những gì được khai báo trong component, tham số phương thức hoặc những thành viên static có thể truy cập. Đây là hệ quả của tính static ngầm định.

### Nếu cần dữ liệu của outer object, hãy truyền rõ ràng

Có thể truyền object bao ngoài thành một component:

~~~java
class Account {
    private final String accountId;

    Account(String accountId) {
        this.accountId = accountId;
    }

    record View(Account account, String label) {
        String accountId() {
            return account.accountId;
        }
    }
}
~~~

Sử dụng:

~~~java
Account account = new Account("ACC-100");
Account.View view = new Account.View(account, "Primary");

System.out.println(view.accountId()); // ACC-100
~~~

Nested record vẫn không tự giữ enclosing instance. `Account` ở đây là một component tường minh, vì vậy quan hệ tham chiếu được thể hiện trong header và có thể được kiểm soát như dữ liệu của record.

Cần cân nhắc rằng component này giữ tham chiếu đến một object `Account` có thể mutable. Nếu mục tiêu là snapshot dữ liệu, thường nên truyền các giá trị cần thiết như `accountId` thay vì giữ cả object.

## 4. Nested record có thể truy cập static member của outer type

Member record không có enclosing instance, nhưng có thể sử dụng thành viên static của kiểu bao ngoài:

~~~java
class Order {
    private static final String PREFIX = "ORD-";

    record Item(String id, int quantity) {
        String fullId() {
            return PREFIX + id;
        }
    }
}
~~~

Sử dụng:

~~~java
Order.Item item = new Order.Item("100", 3);
System.out.println(item.fullId()); // ORD-100
~~~

`PREFIX` thuộc class `Order`, nên nested record có thể truy cập mà không cần một object `Order`.

Ngược lại, field instance của outer class không thể được dùng trực tiếp. Nếu dữ liệu instance cần thiết cho `Item`, hãy truyền nó thành component hoặc tham số phương thức.

## 5. Nested record bên trong một record khác

Record cũng có thể khai báo một member record bên trong body của nó:

~~~java
record Order(String orderId, String customerId) {
    record Customer(String customerId, String name) {}

    record Line(String sku, int quantity, long unitPrice) {}
}
~~~

Các kiểu `Customer` và `Line` là member record của `Order`, đồng thời ngầm định static. Có thể dùng chúng độc lập với một instance `Order`:

~~~java
Order.Customer customer =
    new Order.Customer("C-01", "An");

Order.Line line =
    new Order.Line("SKU-01", 2, 50_000);

Order order = new Order("O-100", customer.customerId());
~~~

Việc khai báo `Order.Line` không tự thêm một component `Line` vào `Order`. Nếu muốn `Order` lưu danh sách dòng hàng, phải khai báo component rõ ràng:

~~~java
import java.util.List;

record OrderWithLines(String orderId, List<Order.Line> lines) {}
~~~

Ở đây, `lines` mới là component lưu dữ liệu; `Line` chỉ là kiểu lồng dùng để mô tả cấu trúc một dòng hàng.

### Dùng nested record để gom nhóm kiểu liên quan

Nested record hữu ích khi một kiểu dữ liệu chỉ có ý nghĩa trong phạm vi API hoặc domain type bao ngoài:

- `Order.Line` biểu diễn một dòng thuộc mô hình đơn hàng.
- `Order.Customer` biểu diễn dữ liệu khách hàng dùng trong ngữ cảnh đơn hàng.
- `HttpResponse.Header` có thể biểu diễn một header của response.
- `Parser.Token` có thể biểu diễn một token thuộc API parser.

Đặt kiểu gần nơi sử dụng giúp người đọc nhận ra mối quan hệ và tránh làm namespace package có quá nhiều kiểu top-level.

Không nên lồng record quá sâu nếu kiểu đó được dùng rộng rãi ở nhiều module. Khi một kiểu có vai trò độc lập và được tái sử dụng nhiều nơi, khai báo top-level có thể làm API dễ tìm và dễ phụ thuộc hơn.

## 6. Nested record bên trong interface

Các member type được khai báo trong interface vốn là public static. Vì record cũng là member type static, ta có thể đặt các kiểu record liên quan ngay trong interface:

~~~java
interface PaymentEvent {
    record Authorized(String paymentId, long amount) implements PaymentEvent {}
    record Rejected(String paymentId, String reason) implements PaymentEvent {}
}
~~~

Sử dụng qua tên interface:

~~~java
PaymentEvent event =
    new PaymentEvent.Authorized("PAY-100", 250_000);
~~~

`PaymentEvent.Authorized` và `PaymentEvent.Rejected` là các kiểu lồng có thể được tạo mà không cần instance bao ngoài. Mỗi record triển khai cùng hợp đồng `PaymentEvent`, nên code xử lý có thể nhận kiểu chung:

~~~java
class PaymentEventHandler {
    static void handle(PaymentEvent event) {
        System.out.println(event);
    }
}
~~~

Ví dụ này dùng interface thông thường và record, không cần sealed types hoặc switch pattern. Nó chạy theo các tính năng ổn định có từ Java 16.

## 7. Local record cũng ngầm định static

Ngoài member record, Java còn cho khai báo record cục bộ trong một block, ví dụ bên trong method:

~~~java
class CsvParser {
    void parse(String rawLine) {
        record Row(String name, int age) {}

        Row row = new Row("An", 20);
        System.out.println(row.name());
    }
}
~~~

`Row` là local record. Phạm vi tên của nó chỉ nằm trong block khai báo, nhưng nó vẫn có semantics static ngầm định: không giữ enclosing instance và không capture local variable từ method.

Ví dụ sau không hợp lệ:

~~~java
class CsvParser {
    void parse(String prefix, String rawLine) {
        // Local record không capture local variable prefix.
        // record Row(String value) {
        //     String prefixed() {
        //         return prefix + value;
        //     }
        // }
    }
}
~~~

Nếu cần dữ liệu cục bộ đó, truyền nó vào record như component hoặc truyền vào phương thức:

~~~java
class CsvParser {
    void parse(String prefix, String rawLine) {
        record Row(String prefix, String value) {
            String prefixed() {
                return prefix + value;
            }
        }

        Row row = new Row(prefix, rawLine);
        System.out.println(row.prefixed());
    }
}
~~~

Việc truyền `prefix` vào constructor làm dữ liệu cần thiết trở thành một phần rõ ràng của giá trị `Row`. Nó không còn là biến được capture ngầm từ method bên ngoài.

### Local record trong instance method cũng không có this của outer class

Dù local record được khai báo trong instance method, nó vẫn không tự có tham chiếu đến instance đang gọi method. Nếu cần một giá trị từ object hiện tại, hãy truyền giá trị đó vào constructor:

~~~java
class ReportService {
    private final String region;

    ReportService(String region) {
        this.region = region;
    }

    void createReport(String title) {
        record Report(String region, String title) {}

        Report report = new Report(region, title);
        System.out.println(report.region() + ": " + report.title());
    }
}
~~~

`region` được đọc từ `this` trong method bên ngoài rồi truyền vào `Report`. Local record chỉ lưu hai component được truyền vào.

## 8. Generic outer type và type parameter của nested record

Vì member record ngầm định static, nó không sử dụng trực tiếp type parameter của outer generic class. Type parameter của nested record phải được khai báo riêng nếu cần.

Ví dụ:

~~~java
class Container<T> {
    record Snapshot<U>(U value) {}
}
~~~

`Snapshot` không thể tham chiếu đến `T` của `Container`, vì nó không gắn với một `Container<T>` cụ thể. Nó khai báo type parameter riêng `U`.

Sử dụng:

~~~java
Container.Snapshot<String> text =
    new Container.Snapshot<>("Java");

Container.Snapshot<Integer> number =
    new Container.Snapshot<>(16);
~~~

Kiểu được viết là `Container.Snapshot<String>`, không phải `Container<String>.Snapshot<String>`, vì `Snapshot` là static member type.

Nếu cần kết hợp kiểu `T` của outer class với dữ liệu nested record, hãy truyền kiểu đó thành type parameter riêng hoặc thành component. Cách đơn giản thường là dùng `Container.Snapshot<T>` từ ngữ cảnh có `T` phù hợp, hoặc truyền giá trị `T` vào constructor của một record có type parameter riêng.

## 9. Nested record bên trong inner class từ Java 16

Trước Java 16, inner class không static bị hạn chế khai báo static member, ngoại trừ một số trường hợp như constant variable. JEP 395 đã nới lỏng quy tắc này để inner class có thể khai báo các static member hợp lệ.

Điều này quan trọng với record vì member record ngầm định static. Từ Java 16, có thể khai báo record bên trong một inner class:

~~~java
class Outer {
    class Inner {
        record Snapshot(String value) {}
    }
}
~~~

`Snapshot` là static member type của `Inner`, không gắn với một object `Inner` hoặc `Outer` cụ thể. Có thể tham chiếu qua tên lồng:

~~~java
Outer.Inner.Snapshot snapshot =
    new Outer.Inner.Snapshot("captured value");
~~~

Không cần tạo `Outer` và `Inner` để tạo `Snapshot`. Đây là một thay đổi ổn định được đưa vào cùng JEP 395, giúp nested record có thể được tổ chức gần class liên quan ngay cả khi class đó là inner class.

Lưu ý: thay đổi này nói về việc khai báo static member trong inner class. Nó không làm inner class tự trở thành static và cũng không thay đổi quy tắc tạo instance của chính `Inner`.

## 10. Phân biệt nested record, local record và record component lồng nhau

Các khái niệm dưới đây liên quan nhưng có ý nghĩa khác nhau:

| Khái niệm | Vị trí khai báo | Đặc điểm |
| --- | --- | --- |
| Member nested record | Trong body của class, interface hoặc record | Là member type; ngầm định static; dùng qua tên kiểu bao ngoài. |
| Local record | Trong block, method hoặc constructor | Chỉ có scope cục bộ; ngầm định static; không capture local variable hoặc enclosing instance. |
| Record component có kiểu record khác | Trong header của record bên ngoài | Là dữ liệu instance thực sự; accessor trả về record được lưu trong component. |

Ví dụ kết hợp:

~~~java
record Address(String city, String country) {}

record Customer(String id, Address address) {
    record Contact(String email, String phone) {}
}
~~~

- `Customer.Contact` là member nested record, ngầm định static.
- `address` là component của `Customer`; mỗi instance `Customer` giữ một tham chiếu đến `Address`.
- `Address` ở đây là kiểu top-level, không phải nested type của `Customer`.

Không nhầm việc khai báo một kiểu bên trong body với việc lưu một object của kiểu đó trong trạng thái record. Chỉ component trong header mới tạo field instance.

## 11. Ví dụ hoàn chỉnh: mô hình sự kiện và kiểu kết quả lồng nhau

Ví dụ sau dùng interface chứa các record event, cùng một record kết quả lồng trong service class:

~~~java
import java.util.Objects;

interface UserEvent {
    record Registered(String userId, String email) implements UserEvent {}
    record Suspended(String userId, String reason) implements UserEvent {}
}

class UserService {
    private static final String SOURCE = "user-service";

    record Result<T>(T value, String source) {}

    Result<UserEvent> register(String userId, String email) {
        String id = Objects.requireNonNull(userId, "userId").strip();
        String address = Objects.requireNonNull(email, "email").strip();

        if (id.isEmpty() || address.isEmpty()) {
            throw new IllegalArgumentException("userId and email are required");
        }

        UserEvent event = new UserEvent.Registered(id, address);
        return new Result<>(event, SOURCE);
    }
}

public class Demo {
    public static void main(String[] args) {
        UserService service = new UserService();

        UserService.Result<UserEvent> result =
            service.register("U-100", "an@example.com");

        System.out.println(result.source());
        System.out.println(result.value());

        UserEvent suspended =
            new UserEvent.Suspended("U-101", "Policy review");

        System.out.println(suspended);
    }
}
~~~

Biên dịch và chạy trên JDK 16 trở lên:

~~~bash
javac --release 16 Demo.java
java Demo
~~~

Điểm cần quan sát:

1. `UserEvent.Registered` và `UserEvent.Suspended` là member record trong interface, được dùng mà không cần instance bao ngoài.
2. `UserService.Result<T>` là member record static ngầm định của `UserService`.
3. `Result<T>` khai báo type parameter riêng, không phụ thuộc một instance `UserService`.
4. `SOURCE` là static member của `UserService`, nên có thể được dùng trong method để tạo `Result`.
5. `Result.value` là component thực sự lưu object `UserEvent`; nested type declaration tự nó không tạo trạng thái instance.
6. Không có record nào cần giữ tham chiếu ẩn đến instance `UserService` hoặc `UserEvent`.

## 12. Lỗi thường gặp và cách khắc phục

1. **Tạo nested record qua instance outer:** member record là static ngầm định; dùng `Outer.Nested` và `new Outer.Nested(...)`.
2. **Truy cập `Outer.this` từ nested record:** record không có enclosing instance. Truyền outer object hoặc dữ liệu cần thiết thành component/tham số.
3. **Cho rằng nested record tự trở thành component của outer record:** khai báo kiểu lồng không lưu dữ liệu; phải khai báo component rõ ràng.
4. **Dùng type parameter của outer generic class:** member record là static, nên khai báo type parameter riêng cho nested record.
5. **Local record capture biến trong method:** local record ngầm định static; truyền giá trị qua constructor hoặc tham số phương thức.
6. **Nhầm record trong inner class với inner record có outer instance:** member record vẫn static ngầm định, kể cả khi được khai báo trong inner class.
7. **Lồng kiểu quá sâu:** chỉ nên nested khi phạm vi và mối quan hệ thực sự rõ; kiểu được tái sử dụng rộng rãi có thể phù hợp với khai báo top-level.
8. **Nhầm static nested type với static field:** nested record là một kiểu thành viên; nó không phải một instance hay một component của outer type.

## 13. Bài tập thực hành

1. Khai báo `class Library` có nested record `Book(String isbn, String title)`. Tạo một `Library.Book` mà không tạo object `Library`.
2. Khai báo record `Order` có nested record `Line`. Thêm component `List<Line>` vào `Order` và phân biệt kiểu lồng với dữ liệu component.
3. Khai báo interface `Notification` có hai nested record `EmailSent` và `SmsSent`, cùng triển khai `Notification`.
4. Viết local record trong method để biểu diễn một dòng CSV. Truyền các giá trị cần dùng vào constructor thay vì capture biến cục bộ.
5. Khai báo generic class `Cache<T>` có nested record `Entry<K, V>`. Giải thích vì sao `Entry` cần type parameter riêng.
6. Khai báo nested record bên trong một inner class và giải thích vì sao có thể tạo nó mà không cần instance của inner class.
7. Viết một nested record cần dùng dữ liệu instance của outer class. Truyền outer object thành component và phân tích ưu/nhược điểm so với chỉ truyền các giá trị cần thiết.

## Ghi nhớ

Member record được khai báo bên trong class, interface hoặc record ngầm định là static. Local record cũng ngầm định static. Vì vậy, nested record không giữ enclosing instance, không thể dùng `Outer.this` và không capture local variable của method. Có thể tạo member record qua tên kiểu bao ngoài như `Outer.Nested`, dùng static member của outer type và khai báo type parameter riêng cho nested record. Record lồng trong interface hữu ích để nhóm các kiểu thông điệp; local record hữu ích cho dữ liệu tạm trong một block. Từ Java 16, inner class cũng được phép khai báo static member, hỗ trợ đặt nested record bên trong inner class. Hãy phân biệt rõ khai báo một kiểu lồng với component thực sự lưu object kiểu đó trong trạng thái record. Các quy tắc này là phần ổn định của Java record và tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Nested Classes and Inner Classes, mục 8.1.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.1.3)
- [Java Language Specification – Local Classes, mục 14.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.3)
