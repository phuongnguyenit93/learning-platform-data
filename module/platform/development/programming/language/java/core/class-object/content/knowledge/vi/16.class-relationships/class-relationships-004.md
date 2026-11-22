# Kết hợp đối tượng bằng composition và phân chia trách nhiệm trong Java

**Composition** (kết hợp đối tượng, thường gọi là *object composition*) là cách xây dựng hành vi của một đối tượng lớn từ các **đối tượng cộng tác nhỏ hơn**. Thay vì đặt mọi xử lý vào một class khổng lồ hoặc lạm dụng `extends`, ta giao cho mỗi object một vai trò rõ ràng rồi **phối hợp** chúng thông qua field, constructor, method và interface.

Ý tưởng ngắn gọn:

- Một `Order` **có** các `OrderLine` và yêu cầu chúng tính subtotal.
- Một `ReportService` **sử dụng** một `Formatter` để định dạng và một `Destination` để gửi kết quả.
- Một `Car` **có** động cơ; động cơ là một thành phần, **không phải** một loại xe hơi.
- Một `CheckoutService` **phụ thuộc vào** `PaymentGateway` thông qua interface, thay vì phải kế thừa một lớp cổng thanh toán để thay đổi cách xử lý.

Composition đặc biệt hữu ích khi muốn phân chia trách nhiệm theo nguyên tắc **high cohesion** (mỗi class tập trung vào nhiệm vụ gần nhau), **low coupling** (ít biết chi tiết triển khai của class khác), bảo vệ invariants và thay đổi thuật toán bằng việc **thay object cộng tác**, không cần thay cấu trúc kế thừa.

> Trong Java, **không có keyword `composition`**. Đây là một lựa chọn thiết kế và quan hệ giữa objects. Một field kiểu đối tượng là cách thể hiện phổ biến, nhưng **chỉ có field chưa đủ để chứng minh mô hình sở hữu/lifecycle theo nghĩa UML**; cần xem ai tạo, ai kiểm soát và ai được phép sử dụng object đó.

Bài Knowledge README này dành cho **Java 17+**, đi từ khái niệm, phân biệt `has-a` với `is-a`, trách nhiệm, giao tiếp giữa objects, ownership và lifecycle, defensive copy, delegation, dependency injection, interface, testability, concurrency, Java records đến các anti-pattern thường gặp. Những ví dụ có `main` đều có tệp, lệnh chạy và stdout xác định.

## 1. Composition nghĩa là gì?

Xét bài toán một dịch vụ tạo hóa đơn. Ta có ít nhất ba trách nhiệm:

1. **Biểu diễn dữ liệu hóa đơn:** số hóa đơn, các dòng sản phẩm, số lượng.
2. **Tính toán tiền:** cộng subtotal, kiểm tra overflow/giá trị hợp lệ.
3. **Xuất kết quả:** chuyển thông tin thành văn bản, ghi vào nơi lưu hoặc gửi cho người dùng.

Một class làm tất cả dễ trở thành *God Object*: vừa đọc đầu vào, lưu state, tính tiền, format và giao tiếp bên ngoài. Composition cho phép phối hợp những objects chuyên biệt hơn:

~~~text
InvoiceService
    |
    +-- has/uses --> Invoice
    |                 |
    |                 +-- contains --> InvoiceLine (nhiều)
    |
    +-- uses -------> InvoiceFormatter
    |
    +-- uses -------> InvoicePublisher
~~~

Ở đây, object ở phía trái **cộng tác** với object phía phải. Nó không nhất thiết phải **kế thừa** class phía phải.

Java có thể biểu diễn cấu trúc như sau:

~~~java
class InvoiceService {
    private final InvoiceFormatter formatter;
    private final InvoicePublisher publisher;

    InvoiceService(InvoiceFormatter formatter,
                   InvoicePublisher publisher) {
        this.formatter = formatter;
        this.publisher = publisher;
    }

    void publish(Invoice invoice) {
        String text = formatter.format(invoice);
        publisher.send(text);
    }
}
~~~

Đây là **đoạn minh họa**, giả sử có các kiểu `Invoice`, `InvoiceFormatter`, `InvoicePublisher`; chưa phải chương trình độc lập. Nó cho thấy **delegation**: `InvoiceService` điều phối, nhưng giao formatting cho `formatter` và giao việc gửi cho `publisher`. Hai dependencies có thể được cung cấp qua constructor.

### 1.1. Điểm nhấn là cộng tác, không phải “class chứa class”

Composition không bắt buộc object phải là nested class, không bắt buộc có inheritance, và không yêu cầu đặt mọi object trong cùng tệp `.java`. Các component có thể là:

- Object cụ thể lưu trực tiếp trong `private final` field.
- Object được inject theo một interface.
- Một tập hợp component chứa trong `List<Component>`.
- Immutable record hoặc value object.
- Service được lắp ghép tại **composition root**, chẳng hạn `main` hoặc cấu hình ứng dụng.

Quan trọng nhất là **ai chịu trách nhiệm về invariant nào** và **luồng gọi giữa các objects rõ ràng đến đâu**.

## 2. So sánh composition và inheritance

Hai mô hình trả lời hai câu hỏi khác nhau:

- **Inheritance:** `Child extends Parent` thể hiện quan hệ **“is-a”** khi Child thật sự là một dạng Parent theo hợp đồng và có thể thay thế Parent phù hợp.
- **Composition:** `Engine engine` trong `Car` thể hiện quan hệ **“has-a”** hoặc **“uses-a”**; Car không phải là Engine, mà Car dùng Engine để hoàn thành công việc.

Ví dụ:

~~~java
// Quan hệ is-a (khi hợp đồng đúng):
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}
~~~

~~~java
// Quan hệ has-a / cộng tác:
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void start() {
        engine.start();
    }
}

interface Engine {
    void start();
}
~~~

Hai đoạn là **mã khai báo minh họa**; những tham số/nghiệp vụ validation được rút gọn để tập trung vào quan hệ.

| Tiêu chí | Inheritance | Composition |
| --- | --- | --- |
| Cú pháp thường dùng | `extends` | Fields, constructor arguments, interface references |
| Ý nghĩa | “Là một loại của” | “Có/dùng/phối hợp với” |
| Tái sử dụng | Kế thừa hành vi/state theo luật Java | Ủy quyền hành vi cho collaborator |
| Thay hành vi | Override/hook trong subclass | Thay object collaborator hoặc strategy |
| Liên kết | Dễ phụ thuộc chi tiết superclass | Có thể phụ thuộc interface nhỏ |
| Có runtime polymorphism không? | Có qua overriding | Có khi collaborator là implementation của interface |
| Lifecycle của các object | Không tự tạo nhiều component instances | Cần thiết kế ai tạo/giữ/chia sẻ component |

**Không phải “composition luôn tốt hơn inheritance”.** Inheritance phù hợp khi có quan hệ is-a thật, contract mở rộng được thiết kế rõ và cần polymorphism của hierarchy. Composition thường linh hoạt hơn để kết hợp các **khả năng độc lập**, nhưng quá nhiều lớp ủy quyền vô nghĩa cũng khiến thiết kế cồng kềnh.

### 2.1. Tại sao `Car extends Engine` thường là sai?

Nếu viết `class Car extends Engine` chỉ để dùng `start()`, ta đã khẳng định một chiếc xe *là một động cơ*. Các public/protected API của Engine có thể trở thành một phần API của Car, trong khi nghiệp vụ muốn Car **có** một động cơ. Điều này làm quan hệ kiểu và contract khó hiểu.

Với composition:

~~~java
interface Engine {
    void start();
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    void start() {
        engine.start();
    }
}
~~~

Car kiểm soát **hành vi công bố ra ngoài**, không bắt buộc công khai mọi method của Engine. Việc thay động cơ mô phỏng bằng một implementation Engine khác có thể không ảnh hưởng API Car.

## 3. Composition, association, aggregation và dependency không hoàn toàn đồng nghĩa

Ở mức Java source, nhiều quan hệ dùng cùng một field:

~~~java
private final Customer customer;
private final List<OrderLine> lines;
private final PaymentGateway gateway;
~~~

Nhưng khi mô hình hóa, ta cần phân biệt **ý nghĩa sở hữu** chứ không chỉ cú pháp.

| Quan hệ ý niệm | Cách hiểu | Ví dụ | Java tự bảo đảm không? |
| --- | --- | --- | --- |
| Association | Object A có liên hệ hoặc biết B | `Order` tham chiếu `Customer` | Không có keyword riêng |
| Aggregation | A nhóm các B, B có thể tồn tại độc lập và chia sẻ | `Department` liên hệ các `Employee` | Không tự quản lý vòng đời |
| Composition theo UML (strong ownership) | Whole sở hữu parts theo mô hình; part không đồng thời thuộc nhiều whole; lifecycle gắn với whole | `Order` sở hữu các `OrderLine` | Không được tự thực thi chỉ nhờ field |
| Dependency / uses-a | A tạm sử dụng B để thực hiện thao tác | Method nhận `Formatter` parameter | Không đồng nghĩa sở hữu |
| Inheritance / is-a | Subtype của một kiểu | `Circle extends Shape` | Java có `extends`/`implements` |

**Lưu ý quan trọng:** trong tài liệu lập trình, “composition” đôi khi được dùng rộng để chỉ **ghép object bằng fields/delegation**, kể cả object được chia sẻ giữa nhiều owners. Trong UML, **composition** thường mang nghĩa **sở hữu mạnh và vòng đời gắn kết**. Nên nói rõ ý định khi thiết kế, tránh suy luận toàn bộ semantics của UML chỉ từ mã `private final Engine engine`.

### 3.1. Java không có “destructor theo composition” như một số ngôn ngữ khác

Một object Java trở nên có thể thu gom rác khi không còn reachable theo các quy tắc GC; **việc whole không còn được tham chiếu không tạo một lệnh Java tự động gọi destructor cho từng part**. Part còn được nơi khác tham chiếu vẫn có thể sống.

Nếu part nắm tài nguyên như file, socket hoặc database connection, cần chính sách **đóng tài nguyên tường minh** (`AutoCloseable`, `try-with-resources`, lifecycle manager), không dựa vào việc Java GC “hủy con khi cha chết”.

### 3.2. Sở hữu phải được bảo vệ bằng API

Nếu một `OrderLine` chỉ được phép thuộc một `Order` về mặt domain, chỉ có field `List<OrderLine> lines` không chặn caller dùng **cùng OrderLine object** trong hai orders. Có thể chọn:

- Tạo `OrderLine` bên trong `Order.addItem(...)`.
- Dùng immutable line value rồi copy khi nhận vào.
- Không expose mutable list nội bộ.
- Nếu cần transfer part giữa wholes, đưa ra API rõ và giữ invariant nhất quán.

Một reference `final` giúp không gán lại field, **không khóa ownership** của object mà field trỏ tới.

## 4. Phân chia trách nhiệm: ai nên biết và làm điều gì?

Một composition có ích khi mỗi collaborator có **lý do thay đổi tương đối rõ**. Ví dụ bán hàng:

- `Product`: SKU, tên, đơn giá của một sản phẩm hoặc một **snapshot giá tại thời điểm lựa chọn** nếu thiết kế như vậy.
- `OrderLine`: product/đơn giá được dùng và số lượng; tính thành tiền một dòng.
- `Order`: sở hữu danh sách dòng hàng, kiểm tra điều kiện thêm/xóa và tính tổng.
- `PaymentGateway`: giao tiếp hệ thống thanh toán cụ thể.
- `CheckoutService`: điều phối use case thanh toán, không trực tiếp tự cài tất cả thuật toán.
- `ReceiptFormatter`: chuyển dữ liệu đã chuẩn hóa thành biểu diễn hóa đơn.

Không phải lúc nào cũng cần **sáu class**. Nếu bài toán nhỏ, tách quá nhiều có thể tạo **indirection** không có giá trị. Cách phân chia có chất lượng là mỗi abstraction làm rõ invariant hoặc trục biến đổi thực sự.

### 4.1. “Information expert”: giao việc cho object nắm dữ liệu cần thiết

Nếu `OrderLine` nắm `unitPriceCents` và `quantity` thì chính nó có đủ dữ liệu để tính:

~~~java
long subtotalCents() {
    return Math.multiplyExact(unitPriceCents, quantity);
}
~~~

`Order` không phải lặp lại công thức nhân và truy cập một loạt fields mà nó không sở hữu. Nó chỉ cần hỏi mỗi line: `line.subtotalCents()`, sau đó cộng.

Điều này tạo **cohesion cao** và giảm việc sao chép công thức qua nhiều classes. Khi chính sách tính tiền thay đổi, ta biết responsibility đang nằm ở đâu.

### 4.2. “Creator”: ai tạo object con?

Khi `Order` là nơi kiểm soát tập lines, API:

~~~java
order.addProduct(product, quantity);
~~~

có thể **tự tạo** `new OrderLine(product, quantity)` sau validation, thay vì nhận một mutable `OrderLine` do code tùy ý bên ngoài điều khiển. Điều này hỗ trợ ownership, nhưng **không phải luật phổ quát**: với immutable value objects, nhận trực tiếp instance cũng có thể an toàn.

### 4.3. “Controller”: ai điều phối use case?

`CheckoutService` có thể gọi `order.totalCents()`, `gateway.charge(...)` và `receiptPublisher.publish(...)`, nhưng không nên sở hữu luôn thuật toán tính giá từng dòng. Điều phối và tính toán nghiệp vụ là hai trách nhiệm có thể tách.

Một controller quá lớn vẫn là God Object nếu nó biết mọi chi tiết bên trong mỗi collaborator; việc có nhiều fields không tự bảo đảm Single Responsibility Principle.

## 5. Ví dụ hoàn chỉnh: Order **kết hợp** Product và OrderLine

Ví dụ này dùng **record** của Java 17 cho dữ liệu theo giá trị và một class mutable có kiểm soát cho aggregate `Order`. Giá tiền lưu bằng **`long` đơn vị cent** để tránh lỗi cơ bản khi biểu diễn số tiền bằng `double`.

Tạo tệp **`OrderCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OrderCompositionDemo {
    record Product(String sku, String name, long unitPriceCents) {
        Product {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU rỗng");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("Giá âm");
            }
        }
    }

    record OrderLine(Product product, int quantity) {
        OrderLine {
            Objects.requireNonNull(product, "product");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng sai");
            }
        }

        long subtotalCents() {
            return Math.multiplyExact(product.unitPriceCents(), quantity);
        }
    }

    static final class Order {
        private final String id;
        private final List<OrderLine> lines = new ArrayList<>();

        Order(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID rỗng");
            }
            this.id = id;
        }

        void add(Product product, int quantity) {
            // Order quyết định cách tạo phần tử của tập mình sở hữu.
            lines.add(new OrderLine(product, quantity));
        }

        List<OrderLine> lines() {
            return List.copyOf(lines);
        }

        long totalCents() {
            long total = 0;
            for (OrderLine line : lines) {
                total = Math.addExact(total, line.subtotalCents());
            }
            return total;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        Product book = new Product("B-1", "Book", 15_000);
        Product pen = new Product("P-2", "Pen", 7_000);

        Order order = new Order("ORD-7");
        order.add(book, 2);
        order.add(pen, 2);

        System.out.println("Order = " + order.id());
        System.out.println("Lines = " + order.lines().size());
        System.out.println("Book subtotal = "
                + order.lines().get(0).subtotalCents());
        System.out.println("Total = " + order.totalCents());

        List<OrderLine> snapshot = order.lines();
        try {
            snapshot.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot cannot be edited");
        }

        try {
            order.add(book, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final lines = " + order.lines().size());
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 OrderCompositionDemo.java
java OrderCompositionDemo
~~~

**Stdout chính xác:**

~~~text
Order = ORD-7
Lines = 2
Book subtotal = 30000
Total = 44000
Snapshot cannot be edited
Rejected = Số lượng sai
Final lines = 2
~~~

### 5.1. Những trách nhiệm đã được phân tách

**`Product`** chịu trách nhiệm về dữ liệu sản phẩm và validation ở mức một product value. Trong ví dụ, đơn giá là giá chụp tại lúc tạo Product; nếu ứng dụng dùng catalog thay giá liên tục, hãy phân biệt **giá catalog hiện hành** và **giá được chốt khi đặt hàng** bằng mô hình riêng.

**`OrderLine`** chịu trách nhiệm về một sản phẩm được chọn, số lượng và subtotal. Nó dùng `Math.multiplyExact` để báo lỗi khi phép nhân `long` tràn số, thay vì âm thầm tạo tổng sai.

**`Order`** chịu trách nhiệm sở hữu tập `lines`, thêm dòng sau validation của `OrderLine`, công bố snapshot read-only và tính tổng bằng cách **gọi từng component**. `Order` không cần biết các fields nội bộ của OrderLine để tự nhân giá với số lượng.

### 5.2. Vì sao đây là composition hợp lý?

- Một Order có **nhiều OrderLine**; mỗi OrderLine có vai trò thành phần của đơn hàng.
- API `order.add(...)` tạo OrderLine mới, tránh nhận một mutable line shared tùy ý.
- List nội bộ là private; không thể sửa cấu trúc qua `order.lines()`.
- Các record `Product` và `OrderLine` có component fields final; vì dữ liệu của Product gồm String/long và OrderLine trỏ đến Product value immutable, snapshot tránh nhiều rủi ro aliasing.
- Order có thể thêm lines theo rule, nhưng ID cố định (`final`).

**Không nhầm:** List.copyOf trả collection không sửa được về cấu trúc và shallow-copy các phần tử; ở đây an toàn thuận lợi **vì phần tử là các immutable records chứa immutable components**. Nếu `Product` hoặc `OrderLine` chứa mutable references, cần thêm chính sách defensive copy.

### 5.3. Giới hạn của ví dụ

Một hệ thống đặt hàng thật có thể cần discount, tax, currency, exchange rates, audit, inventory, idempotency, concurrency và persistence. Nếu có quy tắc mọi order chỉ chứa một line cho một SKU, `add(...)` cần gộp và kiểm tra số lượng; ví dụ cho phép các dòng trùng SKU. Những chi tiết ấy thuộc hợp đồng domain, không được `composition` tự giải quyết.

## 6. Delegation: phân chia hành vi bên cạnh phân chia dữ liệu

Khi kết hợp nhiều objects, component không chỉ để giữ state: object bao ngoài có thể **ủy quyền một phần công việc cho object chuyên trách**.

~~~java
interface Formatter {
    String format(String value);
}

class Printer {
    private final Formatter formatter;

    Printer(Formatter formatter) {
        this.formatter = formatter;
    }

    void print(String value) {
        System.out.println(formatter.format(value));
    }
}
~~~

Trong đoạn khai báo minh họa này, `Printer` quyết định **khi nào in**, còn `Formatter` quyết định **cách biểu diễn**. `Printer` không cần `extends Formatter`; interface field thể hiện cộng tác giữa objects. Đây là ví dụ cho việc **giữ đúng trách nhiệm ở từng class**, không phải yêu cầu tạo wrapper cho mọi method.

Không nhầm delegation với UML composition bắt buộc sở hữu vòng đời: component `Formatter` có thể do caller tạo và chia sẻ. Bài riêng **Ủy quyền thao tác cho đối tượng thành phần** đào sâu forwarding methods, biến đổi arguments/results, exception propagation, boundary invariants, testing với fake và điều phối nhiều delegates.

## 7. Dependency injection là một cách lắp ghép object

Khi một class cần collaborator, có hai cách thường gặp.

**Tạo cứng dependency bên trong:**

~~~java
class ReportService {
    private final HtmlFormatter formatter = new HtmlFormatter();
}
~~~

Nếu `ReportService` phụ thuộc cụ thể vào `HtmlFormatter`, thay thuật toán thành JSON hoặc plain text đòi chỉnh ReportService.

**Nhận dependency từ constructor:**

~~~java
class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter =
                java.util.Objects.requireNonNull(formatter);
    }
}
~~~

Nếu `Formatter` là một interface, ReportService chỉ cần biết **contract `format(...)`**, không biết implementation cụ thể.

Đây là **constructor injection** — một dạng dependency injection không cần framework. Người tạo object, ví dụ `main`, lựa chọn và kết hợp implementations phù hợp. Lợi ích:

- Rõ ràng về dependencies bắt buộc.
- Dễ thay behavior theo môi trường.
- Dễ kiểm thử với fake/stub.
- Không phải dùng static/global mutable service state.
- Field `final` giúp giữ dependency reference ổn định sau xây dựng.

**`final` không có nghĩa collaborator tự immutable hoặc thread-safe**; đó là một vấn đề khác.

### 7.1. Composition root

Ở ứng dụng nhỏ:

~~~java
Formatter formatter = new PlainTextFormatter();
Publisher publisher = new ConsolePublisher();
ReportService service = new ReportService(formatter, publisher);
~~~

Đây là đoạn minh họa với các classes tương ứng. Nơi **lắp ráp object graph** được gọi là *composition root*. Nó hiểu implementations cụ thể; các services còn lại chỉ phụ thuộc contracts cần thiết.

Một ứng dụng dùng Spring hoặc framework DI khác cũng phải giải quyết cùng trách nhiệm lắp ghép, nhưng ở mức Java Core, tự gọi constructors là đủ để học chính xác bản chất.

## 8. Interface và Strategy Pattern giúp thay đổi hành vi không cần `extends` service

Một service có thể cần các chính sách thay đổi:

- Phí vận chuyển cố định hoặc theo cân nặng.
- Định dạng hóa đơn dạng văn bản hoặc JSON.
- Chính sách giảm giá theo khách hàng hoặc chiến dịch.
- Cách lưu dữ liệu vào file, database hoặc memory.
- Cách gửi thông báo bằng email, SMS hoặc log.

Thay vì tạo subclasses `ShippingServiceFlat`, `ShippingServiceWeight` rồi override toàn bộ service logic, có thể đưa **phần thay đổi** vào interface `ShippingCost` và inject implementation qua composition.

~~~text
ShippingService
   |-- ShippingCost (interface)
   |      |-- FlatRate
   |      +-- WeightBased
   |
   +-- NoticeSink (interface)
          |-- InMemoryNotice
          +-- EmailNotice
~~~

`ShippingService` vẫn điều phối luồng tạo nhãn/thu phí, không phải xử lý mọi cách tính phí và mọi kênh thông báo.

## 9. Ví dụ hoàn chỉnh: phối hợp ShippingCost và NoticeSink

Tạo tệp **`ShippingCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ShippingCompositionDemo {
    interface ShippingCost {
        long calculateCents(int grams);
    }

    static final class FlatRate implements ShippingCost {
        @Override
        public long calculateCents(int grams) {
            if (grams <= 0) {
                throw new IllegalArgumentException("Khối lượng sai");
            }
            return 25_000;
        }
    }

    static final class WeightBased implements ShippingCost {
        @Override
        public long calculateCents(int grams) {
            if (grams <= 0) {
                throw new IllegalArgumentException("Khối lượng sai");
            }
            return Math.addExact(
                    5_000, Math.multiplyExact(15L, grams));
        }
    }

    interface NoticeSink {
        void send(String text);
    }

    static final class InMemoryNotice implements NoticeSink {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void send(String text) {
            messages.add(text);
        }

        List<String> messages() {
            return List.copyOf(messages);
        }
    }

    static final class ShippingService {
        private final ShippingCost cost;
        private final NoticeSink notice;

        ShippingService(ShippingCost cost, NoticeSink notice) {
            this.cost = Objects.requireNonNull(cost, "cost");
            this.notice = Objects.requireNonNull(notice, "notice");
        }

        String createLabel(String code, int grams) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("Mã rỗng");
            }

            long fee = cost.calculateCents(grams);
            notice.send("Created " + code);
            return code + ":" + fee;
        }
    }

    public static void main(String[] args) {
        InMemoryNotice inbox = new InMemoryNotice();

        ShippingService flat =
                new ShippingService(new FlatRate(), inbox);
        ShippingService weighted =
                new ShippingService(new WeightBased(), inbox);

        System.out.println("Flat = "
                + flat.createLabel("S-1", 800));
        System.out.println("Weight = "
                + weighted.createLabel("S-2", 800));
        System.out.println("Messages = " + inbox.messages());

        try {
            flat.createLabel("S-3", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
        System.out.println("Final messages = "
                + inbox.messages().size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ShippingCompositionDemo.java
java ShippingCompositionDemo
~~~

**Stdout chính xác:**

~~~text
Flat = S-1:25000
Weight = S-2:17000
Messages = [Created S-1, Created S-2]
Rejected = Khối lượng sai
Final messages = 2
~~~

### 9.1. Những gì ví dụ thể hiện

- `ShippingService` được **lắp từ hai collaborators**: `ShippingCost` và `NoticeSink`.
- Hai implementations `FlatRate` và `WeightBased` thay thuật toán tính phí. Với 800g, phí lần lượt 25.000 cent và `5000 + 15 * 800 = 17000` cent.
- `InMemoryNotice` là một fake đơn giản lưu thông báo vào collection. Ví dụ dùng cùng một sink cho hai services để cho thấy collaborators **có thể được chia sẻ** khi hợp đồng cho phép.
- `ShippingService` không biết sink là in-memory, email hay loại khác; nó chỉ gọi `send(...)`.
- Input khối lượng 0 bị strategy từ chối **trước khi** có thông báo, nên `Final messages = 2`.

**Lưu ý thiết kế:** đây là *object composition theo nghĩa ghép các collaborators*, nhưng việc **hai services chia sẻ cùng một NoticeSink** không phải quan hệ sở hữu độc quyền của service theo nghĩa UML composition mạnh. Khi mô hình hóa lifecycle, cần nói rõ sink thuộc ai và được quản lý ở đâu.

### 9.2. Vấn đề atomicity và tính nhất quán

`createLabel` tính tiền, gọi notice rồi trả label. Trong hệ thống thực, nếu `notice.send` ném exception hoặc đã gửi xong nhưng transaction khác thất bại, cần quyết định phải retry/rollback/outbox hay không. Composition chỉ làm **ranh giới trách nhiệm rõ hơn**, **không tự tạo transaction** giữa các objects.

Nếu nhiều thread dùng chung `InMemoryNotice`, `ArrayList` trong ví dụ **không được thiết kế thread-safe**. Có thể inject một thread-safe sink hoặc triển khai synchronization phù hợp. `final NoticeSink notice` không làm sink tự thread-safe.

## 10. Chia trách nhiệm theo “lý do thay đổi”

Một tiêu chí thực tế để tách class là mỗi class **có cùng một nhóm lý do thay đổi**.

Ví dụ:

| Thay đổi yêu cầu | Class có thể chịu trách nhiệm |
| --- | --- |
| Cách tính shipping fee | `ShippingCost` implementation |
| Gửi thông báo qua kênh khác | `NoticeSink` implementation |
| Quy tắc cho phép tạo shipping label | `ShippingService` hoặc validation policy |
| Mô hình thông tin đơn hàng | `Order`/`OrderLine` |
| Cách hiển thị order tổng kết | `OrderFormatter` |
| Cơ chế lưu order | `OrderRepository` |
| Kết nối HTTP hay command line | Controller/adapter lớp ngoài |

Bảng là **gợi ý phân chia**, không phải luật ép một thay đổi luôn chỉ chạm đúng một tệp. Có những thay đổi xuyên nhiều class hợp lý, đặc biệt khi hợp đồng nghiệp vụ thực sự đổi. Mục tiêu là **giảm lan truyền thay đổi do phụ thuộc không cần thiết**.

### 10.1. Trách nhiệm khác nhau chưa chắc nên tách bằng class ngay lập tức

Một class đơn giản có hai field và một method tính toán có thể rõ ràng hơn việc tạo ba interfaces, hai factories và một configuration layer. Cần cân bằng:

- **Cohesion:** các method/fields có thực sự cùng phục vụ một nhiệm vụ?
- **Coupling:** class có biết quá nhiều nội bộ class khác không?
- **Trục biến đổi:** những thuật toán/dependencies có thực sự thay đổi độc lập không?
- **Khả năng kiểm thử:** có thể kiểm thử đơn vị qua contracts rõ không?
- **Chi phí abstraction:** người đọc có phải đi qua quá nhiều file chỉ để hiểu một phép tính?

**Tách vì trách nhiệm, không tách vì đạt số lượng classes.**

## 11. Ownership: ai có quyền thay đổi và ai chịu trách nhiệm đóng tài nguyên?

Một object có field tham chiếu đến component **không mặc nhiên sở hữu độc quyền** nó:

~~~java
class Service {
    private final DatabaseConnection connection;

    Service(DatabaseConnection connection) {
        this.connection = connection;
    }
}
~~~

Đoạn này giả sử có kiểu `DatabaseConnection`. Connection được caller đưa vào; có thể được dùng chung ở nơi khác. Vì vậy, **đừng tự đóng connection trong Service** chỉ dựa vào việc có field `connection`. API cần xác định ownership:

- **Service owns:** Service tạo/nhận quyền sở hữu resource và có trách nhiệm close theo contract.
- **Service borrows/uses:** Service sử dụng resource do caller/application quản lý, thường không tự đóng.
- **Shared ownership:** nhiều components dùng một resource, nhưng một lifecycle manager điều phối việc close đúng lúc.

### 11.1. Resource composition và `AutoCloseable`

Ví dụ mô tả API sở hữu:

~~~java
final class FilePipeline implements AutoCloseable {
    private final java.io.BufferedWriter writer;

    FilePipeline(java.io.BufferedWriter writer) {
        this.writer =
                java.util.Objects.requireNonNull(writer);
    }

    void write(String text) throws java.io.IOException {
        writer.write(text);
    }

    @Override
    public void close() throws java.io.IOException {
        writer.close();
    }
}
~~~

Đây là khai báo; **nó ngầm chọn hợp đồng FilePipeline sở hữu writer**. Nếu caller chỉ cho mượn writer, tự đóng ở đây có thể sai. Phải tài liệu hóa lựa chọn.

~~~java
try (FilePipeline pipeline = new FilePipeline(writer)) {
    pipeline.write("Hello");
}
~~~

Đây là fragment; cần khởi tạo `writer` trước. `try-with-resources` đảm bảo `close()` được gọi theo quy tắc Java khi thoát phạm vi, kể cả exception. **Composition không khiến Java tự close tài nguyên; `AutoCloseable` và ownership contract mới quản lý chuyện đó.**

### 11.2. Khi whole mất tham chiếu, part có chắc bị GC không?

Không. Nếu một `Engine` vừa được `Car` tham chiếu vừa được một controller khác giữ, nó vẫn có thể reachable sau khi Car không còn được dùng. GC xét reachability, không dựa trực tiếp vào sơ đồ UML “hình thoi đặc”.

Nói **“Order có các OrderLine”** là quyết định domain, không phải phát biểu rằng JVM bắt buộc giải phóng bộ nhớ của lines cùng một thời điểm với Order.

## 12. Aliasing: nhiều tham chiếu tới cùng một component

Giả sử:

~~~java
final class SharedSettings {
    String mode = "safe";
}

class Worker {
    private final SharedSettings settings;

    Worker(SharedSettings settings) {
        this.settings = settings;
    }

    String currentMode() {
        return settings.mode;
    }
}
~~~

Nếu tạo:

~~~java
SharedSettings shared = new SharedSettings();
Worker first = new Worker(shared);
Worker second = new Worker(shared);
shared.mode = "fast";
~~~

Hai Worker objects có field reference riêng nhưng **cùng trỏ tới một SharedSettings object**. `first.currentMode()` và `second.currentMode()` cùng thấy mode đã đổi trong ngữ cảnh tuần tự.

Đó là **aliasing**. Nó có thể là chủ đích (shared configuration) hoặc nguy hiểm (external code sửa state nội bộ).

### 12.1. Khi cần snapshot thay vì chia sẻ

Nếu một `Request` cần cấu hình cố định từ lúc khởi tạo, thay vì giữ mutable settings reference, có thể chụp giá trị:

~~~java
final class Request {
    private final String mode;

    Request(SharedSettings settings) {
        this.mode = settings.mode;
    }

    String mode() {
        return mode;
    }
}
~~~

`Request.mode` là final String, không bị ảnh hưởng bởi thao tác gán `settings.mode = "fast"` sau đó. Đây là **chọn ownership/temporal semantics**, không phải chỉ thêm keyword final.

### 12.2. Không phải chia sẻ nào cũng sai

Một stateless formatter, immutable Clock, connection pool được quản lý đúng, hoặc cache thread-safe có thể được chia sẻ giữa nhiều services một cách hợp lý. Hỏi:

1. Object có mutable state không?
2. Ai được phép sửa?
3. Những thay đổi có nên được phản ánh ngay ở tất cả consumers không?
4. Nó có thread-safe nếu dùng đồng thời không?
5. Lifecycle ai sở hữu?

Composition hữu ích vì khiến những lựa chọn này **có thể mô tả tại ranh giới giữa objects**.

## 13. Đóng gói collection khi whole sở hữu many parts

Một whole thường chứa `List<Part>` hoặc `Map<Key, Part>`. Lỗi phổ biến:

~~~java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    public java.util.List<String> members() {
        return members; // Lộ mutable list nội bộ
    }
}
~~~

Caller có thể gọi `team.members().clear()` hoặc thêm phần tử không được validate. Dù field là `private final`, composition boundary bị phá vì object mutable đã thoát ra ngoài.

Cách tốt hơn là whole có **commands**:

~~~java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    void addMember(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên rỗng");
        }
        members.add(name.trim());
    }

    java.util.List<String> members() {
        return java.util.List.copyOf(members);
    }
}
~~~

`List.copyOf` trả collection không sửa được về cấu trúc; với String immutable, đây là một snapshot an toàn về thành viên. Nhưng nếu List chứa **mutable objects**, đó là shallow copy — caller có thể vẫn sửa state của objects trong list.

### 13.1. Constructor cũng cần bảo vệ đầu vào

~~~java
class Catalog {
    private final java.util.List<String> names;

    Catalog(java.util.List<String> source) {
        this.names = java.util.List.copyOf(source);
    }

    java.util.List<String> names() {
        return names;
    }
}
~~~

Nếu chỉ giữ `this.names = source`, caller có thể giữ biến source và gọi `source.clear()` sau khi Catalog đã tạo. Copy lúc constructor ngăn việc sửa cấu trúc qua alias source.

Cần hiểu đúng:
- `List.copyOf` từ chối phần tử null.
- Copy là shallow; không deep-copy mutable elements.
- `Collections.unmodifiableList(source)` tạo **unmodifiable view**, có thể phản ánh những thay đổi được thực hiện trên source từ alias khác.
- Snapshot thời điểm đang có concurrent writers cần một protocol đồng bộ rõ nếu phải nhất quán giữa nhiều phần tử.

## 14. Ví dụ hoàn chỉnh: ownership bằng defensive snapshot

Tạo tệp **`LibraryCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class LibraryCompositionDemo {
    record Book(String title) {
        Book {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("Tên sách rỗng");
            }
        }
    }

    static final class Shelf {
        private final String label;
        private final List<Book> books;

        Shelf(String label, List<Book> initialBooks) {
            this.label = Objects.requireNonNull(label, "label");
            this.books = List.copyOf(initialBooks);
        }

        String label() {
            return label;
        }

        List<Book> books() {
            return books;
        }

        int count() {
            return books.size();
        }
    }

    public static void main(String[] args) {
        List<Book> input = new ArrayList<>();
        input.add(new Book("Java"));
        input.add(new Book("OOP"));

        Shelf shelf = new Shelf("S-A", input);
        input.clear();
        input.add(new Book("Changed"));

        System.out.println("Shelf = " + shelf.label());
        System.out.println("Books = " + shelf.books());
        System.out.println("Count = " + shelf.count());
        System.out.println("Input count = " + input.size());

        try {
            shelf.books().add(new Book("Extra"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("Shelf list is read-only");
        }

        System.out.println("Final count = " + shelf.count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LibraryCompositionDemo.java
java LibraryCompositionDemo
~~~

**Stdout chính xác:**

~~~text
Shelf = S-A
Books = [Book[title=Java], Book[title=OOP]]
Count = 2
Input count = 1
Shelf list is read-only
Final count = 2
~~~

Ở đây `Shelf` có collection các `Book` value objects:

- Input list mutable được **copy** khi tạo Shelf. Sửa `input` về sau không đổi cấu trúc `shelf.books`.
- `books()` trả read-only list, nên caller không thể thêm/xóa trực tiếp.
- `Book` là record có một String component immutable; điều này giúp kết quả snapshot đủ an toàn cho ví dụ.
- `Shelf` không bắt buộc “sở hữu” Book theo nghĩa độc quyền: cùng một immutable Book instance có thể xuất hiện ở nhiều shelves mà không gây mutation conflict. Nếu nghiệp vụ yêu cầu mỗi quyển vật lý chỉ nằm trên một shelf, cần mô hình BookCopy/InventoryItem có identity và invariant ownership riêng.

**Một composition có thể an toàn nhờ immutable parts** mà không cần chặn mọi tham chiếu chia sẻ.

## 15. “Không hỏi nội tạng” của component: Tell, Don't Ask và Law of Demeter

Một dấu hiệu coupling cao là **train-wreck navigation**:

~~~java
order.getCustomer()
     .getAddress()
     .getCity()
     .getName();
~~~

Đây là fragment minh họa: mỗi getter có thể kéo caller phụ thuộc vào cấu trúc của nhiều objects. Nếu model thay `Address`, caller phải sửa dù nhu cầu chỉ là lấy địa danh để giao hàng.

Một alternative:

~~~java
String deliveryCity = order.deliveryCityName();
~~~

Hoặc để `DeliveryPlanner` nhận một value object được `Order` công bố theo hợp đồng rõ.

**Law of Demeter** thường được diễn giải: một object nên làm việc chủ yếu với collaborators trực tiếp, arguments và objects mình tạo, tránh đào sâu vào cấu trúc component không thuộc trách nhiệm nó. Đây là heuristic, không phải quy tắc compiler.

### 15.1. Đừng giấu hoàn toàn dữ liệu chỉ vì sợ getter

Nếu caller thực sự cần một `Address` immutable để tính tuyến vận chuyển, trả một immutable Address value object có thể là thiết kế sạch. Không bắt buộc thêm `order.deliveryCityName()`, `order.deliveryPostalCode()`, `order.deliveryCountry()` nếu API value object đã có ý nghĩa ổn định.

Mục tiêu là **giảm coupling không cần thiết**, không phải cấm mọi traversal.

## 16. Một object có thể giữ nhiều vai trò mà không thành God Object

Một `Order` có thể:

- Kiểm tra logic thêm dòng hàng.
- Tính tổng từ các OrderLines.
- Quản lý trạng thái của aggregate.
- Cung cấp snapshot cho tầng trình bày.

Đây đều có thể thuộc một **trách nhiệm hợp nhất**: duy trì invariant của Order. Single Responsibility Principle **không có nghĩa mỗi class chỉ được một method hoặc một field**.

Đồng thời, việc `Order` tự gửi email, tự SQL query, tự format HTML và tự kiểm soát transport HTTP có thể là những **lý do thay đổi độc lập** không cần nằm trong aggregate.

### 16.1. Phân tách giữa domain và infrastructure

~~~text
Order (domain)
   |
   +-- OrderLine (domain value/part)

CheckoutService (application)
   |
   +-- PaymentGateway (port/interface)
   +-- OrderRepository (port/interface)
   +-- ReceiptPublisher (port/interface)

Adapters (infrastructure)
   |
   +-- HttpPaymentGateway
   +-- SqlOrderRepository
   +-- EmailReceiptPublisher
~~~

Đây là một **cách tổ chức** gợi ý, không phải cấu trúc bắt buộc cho mọi bài tập. Application service điều phối use case, domain objects giữ business invariants, adapters phụ trách IO.

Trong ví dụ Java Core, hoàn toàn có thể dùng implementations trong memory mà không cần framework hoặc database.

## 17. Thiết kế interface vừa đủ cho collaborator

Interface có ích khi object cần phụ thuộc **hành vi** thay vì một implementation cụ thể. Nhưng tách interface cho **mọi class** dù không có use case biến đổi nào cũng có thể làm code khó đọc.

Ví dụ interface nhỏ:

~~~java
interface TaxPolicy {
    long taxFor(long subtotalCents);
}
~~~

Nó xác định đúng trách nhiệm tính tax từ subtotal. Một `CheckoutService` nhận `TaxPolicy` thay vì biết nhiều lớp thuế cụ thể.

Nếu class chỉ có một implementation ổn định, không cần mock, không có nhiều policies và không mở API, dùng concrete class cũng có thể phù hợp.

### 17.1. Interface Segregation Principle

Đừng ép một collaborator phải implement những methods không liên quan:

~~~java
interface EverythingGateway {
    void charge(long amount);
    void sendEmail(String text);
    void saveToDatabase(Object object);
}
~~~

Mỗi consumer nên chỉ phụ thuộc những capabilities nó thật sự cần, như `PaymentGateway`, `NotificationSink`, `OrderStore`. Tách interface giảm coupling giữa những thay đổi độc lập.

### 17.2. Dependency Inversion

Nếu một high-level service phụ thuộc concrete low-level adapter, mỗi lần đổi adapter có thể kéo theo sửa service. Phụ thuộc interface/port đủ nhỏ giúp định hướng phụ thuộc về **hợp đồng chức năng**.

**Không nhầm Dependency Inversion với “dùng interface cho tất cả”.** Một domain value object immutable có thể được dùng trực tiếp, không nhất thiết cần `IProduct` chỉ để trông linh hoạt.

## 18. Tính kiểm thử: object cộng tác có thể được thay bằng fake

Composition thường làm unit test dễ hơn vì có thể lắp class với test collaborators.

Ví dụ một `InvoiceService` cần `Clock` để lấy thời gian, có thể inject `Clock.fixed(...)`:

~~~java
class InvoiceService {
    private final java.time.Clock clock;

    InvoiceService(java.time.Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    java.time.Instant issueTime() {
        return clock.instant();
    }
}
~~~

Test có thể tạo:

~~~java
java.time.Clock fixed = java.time.Clock.fixed(
        java.time.Instant.parse("2026-01-01T00:00:00Z"),
        java.time.ZoneOffset.UTC);
InvoiceService service = new InvoiceService(fixed);
System.out.println(service.issueTime());
~~~

Kết quả (nếu đặt fragment trong method thích hợp):

~~~text
2026-01-01T00:00:00Z
~~~

Không cần sửa global clock hoặc override logic của InvoiceService chỉ để kiểm thử. `Clock` là collaborator qua composition; `final` field làm dependency reference ổn định.

### 18.1. Test double không cần framework mocking

Một `InMemoryNotice` trong ví dụ shipping là **fake** có thể tự viết bằng Java Core. Nó ghi lại những messages mà service gửi, giúp kiểm tra hành vi ở biên:

- Service có gọi đúng collaborator không?
- Khi validate input thất bại có tạo side effect không?
- Khi thay implementation của strategy, service có giữ contract điều phối không?

Với các kiểm thử thật, nên dùng assertion của JUnit hoặc công cụ test tương ứng thay vì chỉ in stdout; bài này dùng main để minh họa chạy độc lập.

### 18.2. Đừng thêm setter dependency chỉ để test

Nếu class có `private final PaymentGateway gateway`, đừng vội bỏ final và thêm `setGateway` chỉ để unit test thay dependency sau khi object đã tạo. Constructor injection cho phép test cung cấp fake **ngay khi tạo object**, giữ contract rõ hơn.

## 19. Composition và immutability

Composition kết hợp tốt với **immutable value objects**. Nếu các parts không thay đổi được, whole có thể chia sẻ references an toàn hơn theo những điều kiện thích hợp.

~~~java
record Address(String city, String street) {
    Address {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City rỗng");
        }
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street rỗng");
        }
    }
}

record Recipient(String name, Address address) {
    Recipient {
        java.util.Objects.requireNonNull(name);
        java.util.Objects.requireNonNull(address);
    }
}
~~~

Đây là Java 17 records. `Recipient` **có** một `Address`; hai objects hợp thành một cấu trúc dữ liệu nhưng Address value có thể được chia sẻ an toàn vì String immutable và records không có setters tự sinh.

### 19.1. Java record chỉ có shallow immutability

Nếu `record Recipient(String name, List<String> tags)` chứa List mutable, component reference final nhưng List có thể bị sửa. Dùng compact constructor tạo snapshot:

~~~java
record TaggedRecipient(String name,
                       java.util.List<String> tags) {
    TaggedRecipient {
        java.util.Objects.requireNonNull(name);
        tags = java.util.List.copyOf(tags);
    }
}
~~~

Đồng thời, nếu tags là list của mutable objects thì shallow copy không đủ để khóa trạng thái bên trong từng object. Composition không thay thế việc quyết định **defensive copying sâu tới mức nào**.

### 19.2. Mutable aggregate + immutable parts

Mô hình Order có thể mutable ở mức danh sách lines, trong khi mỗi line là immutable value. Đây thường là một kết hợp hợp lý: aggregate sở hữu thay đổi về thành phần, còn state từng line không bị sửa tùy tiện từ ngoài.

## 20. Composition và inheritance có thể cùng tồn tại

Không phải chọn **chỉ một**. Ví dụ:

~~~java
interface PaymentGateway {
    void charge(long cents);
}

abstract class RetryingGateway implements PaymentGateway {
    // Có thể giữ logic retry chung và mở hooks thích hợp.
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    void checkout(long cents) {
        gateway.charge(cents);
    }
}
~~~

`CheckoutService` dùng **composition** với PaymentGateway. Một implementation của PaymentGateway có thể dùng **inheritance** để tái sử dụng workflow nội bộ, nếu is-a/extension contract thực sự phù hợp.

**Điều nên tránh** là để CheckoutService **kế thừa PaymentGateway** chỉ để có phương thức `charge`, vì CheckoutService không phải một payment gateway.

### 20.1. Tránh “inheritance for code reuse” không đúng subtype contract

Một class có thể kế thừa toàn bộ public methods của superclass dù chỉ cần một helper. Nếu class con không bảo đảm được những kỳ vọng của superclass (preconditions, postconditions, invariants), code polymorphic sẽ dễ sai.

Composition chỉ công bố **những methods whole lựa chọn**, nên thường giúp bảo vệ contract trước thay đổi của implementation detail.

## 21. Lỗi “shared mutable state” khi ghép nhiều objects

Dù mỗi class được tách đẹp, shared mutable collaborators có thể vẫn gây data races:

~~~java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int current() {
        return value;
    }
}

class JobService {
    private final Counter counter;

    JobService(Counter counter) {
        this.counter = counter;
    }

    void execute() {
        counter.increment();
    }
}
~~~

Nếu nhiều `JobService` objects giữ **cùng Counter**, và nhiều threads gọi `execute`, `Counter.value++` không nguyên tử và có thể mất cập nhật. `private final Counter counter` chỉ ngăn gán lại tham chiếu, **không biến Counter thành thread-safe**.

Có thể chọn:

- Mỗi service một counter riêng nếu nghiệp vụ muốn state độc lập.
- `AtomicInteger` hoặc đồng bộ cho counter chung.
- Immutable value snapshot nếu không cần cập nhật shared state.
- Chỉ rõ concurrency model cho collaborator.

**Chia trách nhiệm tốt và thread safety là hai bài toán khác nhau.** Composition tạo nơi đặt chính sách đồng bộ hợp lý, nhưng không tự triển khai nó.

## 22. Quan hệ hai chiều và vòng tham chiếu

Một mô hình có cả:

~~~java
class Parent {
    private final java.util.List<Child> children =
            new java.util.ArrayList<>();
}

class Child {
    private Parent parent;
}
~~~

có quan hệ hai chiều. Điều này có thể hữu ích cho navigation, nhưng làm tăng trách nhiệm đồng bộ:

- Khi thêm Child vào Parent, ai thiết lập `child.parent`?
- Khi chuyển Child sang Parent khác, ai xóa liên hệ cũ?
- Ai được phép sửa danh sách và field parent?
- Nếu serialization/toString/equals đi vòng references, làm sao tránh lặp vô hạn?
- Có nhiều threads sửa graph cùng lúc không?

Một cách giảm rủi ro là **quy định một aggregate root kiểm soát cả hai chiều của mối quan hệ**, không cho caller tự sửa hai fields độc lập. Nhưng đôi khi chỉ cần quan hệ **một chiều**; đừng thêm back-reference khi không có use case thật.

### 22.1. Vòng tham chiếu không đồng nghĩa Java GC bất lực

Java garbage collector có thể thu gom các objects tạo thành cycle **nếu cả chu trình không còn reachable từ GC roots**. Vấn đề lớn hơn ở đây thường là **invariant, traversal và lifecycle**, chứ không phải cứ có cycle là memory leak.

Nếu static registry vẫn giữ một object trong cycle, toàn bộ object graph còn reachable theo các đường tham chiếu tương ứng; phải xem reachability thực tế.

## 23. Composition và equality/hashCode

Khi whole chứa parts, cần quyết định:

- Whole là **entity** có identity riêng (ví dụ Order ID), hay **value object** được xác định bằng các components?
- Equality có so toàn bộ parts hay chỉ identity?
- Parts có immutable không?
- Nếu đưa mutable aggregate vào `HashSet` hoặc làm key `HashMap`, thay đổi fields tham gia hashCode có làm lookup sai không?

Một immutable record như:

~~~java
record Point(int x, int y) {
}
~~~

có component-based equality theo contract record, phù hợp value semantics. Một Order entity có ID riêng không nhất thiết coi hai orders cùng danh sách items là bằng nhau.

Composition **không tự quyết định equality**. Không sinh `equals/hashCode` dựa trên mọi field một cách máy móc nếu graph có mutable fields, cycles hoặc entity identities.

## 24. Composition và hiệu năng

Ghép objects có thể tạo thêm:

- Allocations cho các component instances.
- Một số method calls qua interface/delegation.
- Indirection khi truy cập dữ liệu.
- Snapshots/defensive copies nếu muốn bảo vệ ownership.

Nhưng cũng giúp:

- Cô lập dữ liệu và logic, giảm chi phí bảo trì.
- Reuse collaborator đúng chỗ.
- Thay implementation không sửa nhiều nơi.
- Test không cần hệ thống thật.
- Đưa tối ưu chuyên biệt vào đúng component chịu trách nhiệm.

Không nên mặc định “inheritance nhanh hơn composition” hay “một class khổng lồ luôn hiệu quả hơn”. JVM/JIT có những tối ưu như inlining và escape analysis tùy ngữ cảnh. Nếu performance quan trọng, **đo đúng workload** với benchmark phù hợp, không phá mô hình trách nhiệm chỉ dựa vào phỏng đoán.

## 25. Phân biệt object graph, class diagram và runtime ownership

Một sơ đồ lớp cho thấy `Order` tham chiếu `List<OrderLine>` là **class-level relationship**. Nhưng runtime có thể là:

~~~text
Order A --> Line 1
        --> Line 2

Order B --> Line 3

ShippingService A --+
                    +--> SharedNoticeSink
ShippingService B --+
~~~

Trong graph này, mỗi Order giữ những OrderLine riêng theo API đã thiết kế. Hai ShippingService cùng tham chiếu một sink. Nếu domain muốn exclusive ownership, invariant phải được bảo vệ, không chỉ vẽ hình thoi đặc UML.

**Mô hình miền là một quyết định thiết kế; object references là cơ chế thi hành quyết định đó.**

## 26. Các anti-pattern dễ gặp

### 26.1. God Object

Một class chứa mọi field, mọi database call, mọi calculation và mọi output format. Cần tìm **ranh giới trách nhiệm** thay vì thêm nhiều private helper vào cùng class không kiểm soát.

### 26.2. Inheritance thay cho has-a

`class Invoice extends PdfWriter` để tái dùng `write` khiến Invoice trở thành một dạng PDF writer về mặt kiểu; sai quan hệ nghiệp vụ. Hãy dùng `private final PdfWriter writer` hoặc `DocumentPublisher` interface.

### 26.3. Expose mutable component trực tiếp

`getLines().clear()` cho phép caller làm hỏng invariant của Order. Cung cấp commands và immutable snapshots khi cần.

### 26.4. Object graph quá sâu

`a.getB().getC().getD().execute()` khiến caller biết nhiều implementation details. Cân nhắc delegation tại ranh giới có ý nghĩa, đừng làm wrapper cơ học ở mọi cấp.

### 26.5. Interface cho mọi lớp dù không có abstraction thật

Tạo `IOrderLine`, `IProduct`, `IOrderId` chỉ vì mỗi class “phải có interface” có thể làm code rối. Dùng interface ở chỗ có **hợp đồng hành vi/biến thể/dependency boundary** hữu ích.

### 26.6. Bảo vệ reference nhưng không bảo vệ object

`final List<Item>` không làm list hoặc Items bất biến. Cần xét aliasing, defensive copy và các methods thay đổi state.

### 26.7. Sở hữu tài nguyên không rõ

Một service nhận shared connection từ ngoài nhưng tự `close()` khi xong, làm các consumers khác hỏng. Ghi rõ ai sở hữu và khi nào close.

### 26.8. Business logic ở tầng điều phối thay vì domain object

Service truy cập price/quantity fields của từng line và tự tính subtotal ở nhiều nơi. Đặt phép tính gần dữ liệu và invariant mà nó bảo vệ.

### 26.9. Shared mutable collaborator nhưng không có concurrency protocol

Nhiều services inject cùng mutable fake/cache/counter, dữ liệu bị race. Chọn thread-safe collaborator hoặc mỗi owner một instance.

### 26.10. Circular dependency không kiểm soát

A cần B để khởi tạo, B lại cần A ngay trong constructor. Dễ khiến constructor chaining khó, dùng object chưa khởi tạo xong hoặc làm dependency injection container không giải quyết được vòng. Xem lại trách nhiệm, dùng abstraction/mediator hoặc chuyển state hợp lý.

### 26.11. Over-composition

Một nghiệp vụ nhỏ bị chia thành mười tầng wrappers chỉ chuyển tiếp một method. Đừng chạy theo số lượng class; xem lợi ích testability/coupling có thật không.

### 26.12. Dùng `static` làm dependency toàn cục

`PaymentGateway.INSTANCE` mutable global khiến service khó có cấu hình độc lập và tests dễ ảnh hưởng lẫn nhau. Constructor injection thông thường rõ hơn nếu nhiều cách triển khai.

## 27. Hướng dẫn thiết kế composition theo từng bước

**Bước 1 — Viết use case.** Ví dụ: “Tạo đơn hàng, thêm sản phẩm, tính tổng, tính phí vận chuyển và gửi thông báo”.

**Bước 2 — Liệt kê dữ liệu và invariants.** Giá không âm, số lượng dương, order ID hợp lệ, tổng không tràn, không công khai list mutable.

**Bước 3 — Xác định object biết dữ liệu nào.** OrderLine biết product/quantity và tính subtotal; Order giữ lines và tính total; shipping policy biết thuật toán phí.

**Bước 4 — Tìm trục biến đổi.** Một ứng dụng có thể thay nhiều shipping policies hoặc notification channels. Dùng interfaces cho các điểm biến đổi ấy.

**Bước 5 — Chọn ownership.** Order tạo lines hay nhận immutable lines? Sink được share hay owned? Resource nào cần close? Có cần copy input/output?

**Bước 6 — Thiết kế API hành vi.** `order.add(product, qty)`, `order.totalCents()`, `service.createLabel(...)`. Hạn chế setter/getter làm lộ nội bộ.

**Bước 7 — Lắp ghép ở ngoài.** `main` hoặc composition root tạo collaborators, inject vào services.

**Bước 8 — Kiểm thử ở ranh giới.** Kiểm tra invariants, negative inputs, exceptions, fake collaborators, aliasing và trường hợp shared state.

**Bước 9 — Rà soát coupling.** Một thay đổi formatter có buộc sửa Order không? Một thay đổi storage có buộc sửa Product không?

**Bước 10 — Chỉ mở rộng mô hình khi nhu cầu phát sinh.** Tránh tạo thêm layer/interface không dùng được chỉ để “đúng pattern”.

## 28. Bài tập tự kiểm tra có đáp án

**Câu 1.** `Car` dùng `Engine` để khởi động. Quan hệ nào tự nhiên hơn: `Car extends Engine` hay `Car` giữ một `Engine` field?

**Đáp án:** Thường là composition: Car **có/sử dụng** Engine, chứ Car không phải một Engine.

**Câu 2.** `Order` giữ `private final List<OrderLine> lines`. Chỉ riêng `final` đã bảo vệ invariant danh sách chưa?

**Đáp án:** Chưa. Final chặn gán lại field, nhưng mutable List vẫn có thể bị sửa qua methods hoặc alias. Cần API có kiểm soát và snapshot/defensive copy phù hợp.

**Câu 3.** Tại sao `OrderLine` nên tính subtotal thay vì `Order` tự đọc field giá và số lượng của từng line?

**Đáp án:** OrderLine nắm dữ liệu cần thiết, nên logic cùng trách nhiệm sẽ cohesive hơn và tránh lặp business rule trong nhiều owners.

**Câu 4.** Một service inject `NotificationSink` qua constructor. Nó có nhất thiết sở hữu và đóng sink khi kết thúc không?

**Đáp án:** Không. Field reference không tự xác lập lifecycle ownership. Cần contract rõ về owned, borrowed hoặc shared dependencies.

**Câu 5.** `List.copyOf(List<MutableItem>)` có tạo deep copy của từng MutableItem không?

**Đáp án:** Không. Nó tạo unmodifiable snapshot về cấu trúc nhưng không deep-copy mutable elements.

**Câu 6.** Hai services giữ cùng một `InMemoryNotice` instance có phải UML composition strong ownership độc quyền không?

**Đáp án:** Không theo nghĩa sở hữu độc quyền; đó là shared collaborator. Vẫn có thể gọi là object composition theo nghĩa rộng ghép dependencies.

**Câu 7.** Vì sao composition thường dễ unit test?

**Đáp án:** Vì collaborators được inject, có thể thay bằng fake/stub để kiểm tra hành vi mà không cần service ngoài thật.

**Câu 8.** Có phải mọi class domain phải có interface mới là thiết kế composition tốt?

**Đáp án:** Không. Dùng interface nơi có hợp đồng hành vi, biến thể hoặc boundary thực sự có ích. Immutable value objects cụ thể thường không cần interface.

**Câu 9.** Dùng `private final Clock clock` có thể lấy những thời điểm khác nhau không?

**Đáp án:** Có. Final giữ reference cố định, còn `clock.instant()` có thể trả các giá trị khác nhau theo thời gian.

**Câu 10.** Nếu hai Workers dùng chung một mutable Counter, `final Counter counter` làm increment thread-safe không?

**Đáp án:** Không. Shared mutable state cần thread-safe implementation hoặc synchronization thích hợp.

**Câu 11.** Quan hệ hai chiều Parent–Child có rủi ro gì?

**Đáp án:** Cần đồng bộ hai hướng khi thêm/xóa/chuyển, tránh làm lộ mutable state, cycles khi traversal/serialization và quy định owner cập nhật.

**Câu 12.** Với vòng tham chiếu A↔B, Java GC có luôn bị memory leak không?

**Đáp án:** Không. Nếu toàn bộ graph không còn reachable từ GC roots, GC có thể thu gom các objects có cycle.

**Câu 13.** Một `Order` entity có nên dùng `equals` so toàn bộ mutable `lines` không?

**Đáp án:** Không có câu trả lời mặc định. Cần quyết định identity/equality theo domain; mutable fields trong hash-based collections có thể gây lỗi lookup khi hashCode thay đổi.

**Câu 14.** Composition có làm mọi code nhanh hơn inheritance không?

**Đáp án:** Không có bảo đảm. Chọn thiết kế theo semantics/coupling và benchmark khi hiệu năng thật sự quan trọng.

**Câu 15.** Khi nào inheritance vẫn thích hợp?

**Đáp án:** Khi có quan hệ is-a hợp lệ, contract của base class cho subclassing rõ, và polymorphism qua hierarchy thật sự được yêu cầu.

**Câu 16.** API `order.getLines().get(0).getProduct().getPrice()` có vấn đề gì?

**Đáp án:** Caller phụ thuộc sâu vào cấu trúc object graph, tăng coupling. Có thể dùng `order.totalCents()` hoặc API trả immutable value thích hợp nếu caller chỉ cần tổng.

**Câu 17.** Vì sao service không nên tự format SQL/email/HTML nếu trách nhiệm chính là checkout?

**Đáp án:** Những phần ấy có lý do thay đổi khác với điều phối checkout, thường nên nằm trong collaborators/adapters phù hợp.

**Câu 18.** Nếu một part được tạo bởi whole, khi whole bị GC thì JVM có bắt buộc gọi destructor của part ngay không?

**Đáp án:** Không. Java dùng GC/reachability và quản lý resource tường minh; không có cơ chế destructor đồng bộ với UML composition.

## 29. Checklist khi review quan hệ composition

1. **Quan hệ thật là has-a/uses-a hay is-a?** Đừng dùng inheritance chỉ để tái sử dụng một method.
2. **Mỗi class có trách nhiệm rõ ràng không?** Nên biết vì sao class đó tồn tại.
3. **Whole có giao việc chuyên biệt cho parts không?** Hay nó tự thao tác fields của parts rồi lặp logic?
4. **API có che representation nội bộ không?** Tránh lộ mutable collections và object graph vô ích.
5. **Những input mutable được copy khi cần chưa?** Không giữ alias làm hỏng invariant.
6. **Getter có trả mutable parts không?** Cân nhắc snapshot, immutable value, readonly view theo contract.
7. **Part có được dùng chung không?** Nếu có, shared mutability, lifecycle và ownership đã rõ chưa?
8. **Ai tạo part và ai được chuyển part sang whole khác?** Có ràng buộc exclusivity không?
9. **Ai close resource?** Constructor injection không tự quyết định ownership.
10. **Dependencies có được inject từ bên ngoài khi hợp lý không?** Tránh hard-code mọi implementation.
11. **Có interface hợp lý cho điểm biến đổi không?** Đừng ép interface cho mọi value object.
12. **Composition root có rõ không?** Có một nơi xác định implementations và lắp ráp objects.
13. **Có tests dùng fake collaborator được không?** Những tác dụng phụ có thể được quan sát/kiểm soát không?
14. **Có vòng tham chiếu/quan hệ hai chiều không cần thiết không?** Tránh coupling và cập nhật state hai chiều khó.
15. **Có concurrency protocol cho shared mutable objects không?** Final reference không thay thế thread safety.
16. **Có lạm dụng wrapper/layer không?** Mỗi lớp trung gian cần một vai trò thực sự.
17. **Equality/identity có phản ánh domain không?** Không sinh dựa trên mọi field mutable một cách máy móc.
18. **Các method có thực thi validation/invariant đúng nơi sở hữu không?** Đừng phó mặc toàn bộ cho caller.
19. **Thiết kế có cho phép đổi một thuật toán mà không phải sửa mọi lớp khác không?** Nếu không, xem coupling.
20. **Code có còn dễ đọc với developer mới không?** Composition tốt phải làm cấu trúc và hành vi rõ hơn, không chỉ tạo thêm file.

## Kết luận

**Composition** kết hợp các object để thực hiện một mục tiêu lớn, trong đó **mỗi object chịu trách nhiệm cho một phần hành vi hoặc state rõ ràng**. Trong Java, ta thường dùng fields, constructor injection, interfaces và delegation để hiện thực điều đó. Với domain aggregate như `Order`, whole có thể quản lý các parts và bảo vệ invariants; với application service như `ShippingService`, whole điều phối các collaborators thực hiện chính sách khác nhau.

Không nhầm **object composition theo nghĩa ghép behavior** với **UML composition sở hữu mạnh**: JVM không tự áp đặt exclusivity, lifecycle hay destructor từ một field tham chiếu. Ownership, defensive copying, resource management, thread safety và mutation boundaries phải được thiết kế có chủ đích.

Dùng composition khi nó giúp **phân chia trách nhiệm, tăng cohesion, giảm coupling, dễ thay đổi hành vi và dễ kiểm thử**. Dùng inheritance khi có subtype contract thực sự. Lựa chọn tốt không phải “nhiều class nhất” mà là **những ranh giới đúng nơi dữ liệu và hành vi thuộc về**, với một API nhỏ, rõ nghĩa và bảo vệ trạng thái hợp lệ.
