# Lựa chọn thành phần hay kế thừa cho một yêu cầu cụ thể trong Java

Khi thiết kế phần mềm hướng đối tượng, **kế thừa (inheritance)** và **kết hợp đối tượng/thành phần (object composition)** đều có thể giúp tái sử dụng code và mở rộng hành vi. Nhưng chúng **không giải quyết đúng cùng một vấn đề**. Việc chọn giữa chúng cần dựa vào **ý nghĩa quan hệ**, **hợp đồng hành vi**, **những gì dự kiến sẽ thay đổi**, **vòng đời các đối tượng**, chứ không dựa vào việc cách nào ít dòng hơn.

Hai câu hỏi khởi đầu:

- **A thật sự là một loại B?** Nếu mọi đối tượng A phải có thể được dùng hợp lệ ở nơi yêu cầu B, và hierarchy có ý nghĩa ổn định, cân nhắc **inheritance/implements**.
- **A có một B, dùng một B, hoặc ủy quyền công việc cho B?** Nếu A phối hợp với B để làm việc, cần hoán đổi chức năng hoặc kết hợp nhiều khả năng, cân nhắc **composition + delegation**, thường đi với interface.

Ví dụ:

```java
class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = formatter;
    }
}
```

`ReportService` **dùng một `Formatter`**, không phải “là một Formatter”. Vì thế một field tham chiếu và ủy quyền tới Formatter đúng ngữ nghĩa hơn `class ReportService extends Formatter`.

Ngược lại:

```java
interface Shape {
    double area();
}

final class Rectangle implements Shape {
    // Triển khai hợp đồng Shape.
}
```

`Rectangle` **là một `Shape`** theo hợp đồng abstraction, nên triển khai interface này là hợp lý. Trong Java, **`implements` interface và `extends` class là hai cơ chế khác nhau**; cả hai đều tạo quan hệ kiểu, nhưng inheritance từ class còn chia sẻ implementation và ràng buộc trạng thái superclass.

**Kết luận định hướng:** *Ưu tiên composition khi cần cộng tác/hoán đổi hành vi; dùng inheritance khi có subtype thật sự và hợp đồng kế thừa ổn định*. Đây là **heuristic**, không phải quy tắc cấm kế thừa.

Bài dùng **Java 17+**, trình bày quy trình lựa chọn từng bước, ví dụ so sánh cùng yêu cầu bằng hai thiết kế, những trường hợp nên hoặc không nên kế thừa, cùng chương trình Java có lệnh `javac`/`java` và stdout.

## 1. Định nghĩa đúng các quan hệ

### 1.1. Inheritance: quan hệ is-a

Khi viết:

```java
class Dog extends Animal {
}
```

`Dog` là subtype của `Animal` theo quan hệ kế thừa. Trong code, một biến `Animal` có thể giữ đối tượng `Dog` nếu quyền truy cập và các điều kiện kiểu phù hợp.

Khi viết:

```java
class Dog implements Pet {
}
```

`Dog` cam kết triển khai `Pet`, một abstraction hành vi; điều này cũng tạo khả năng dùng một `Dog` ở nơi nhận `Pet`.

**Nhưng hai thứ không giống hệt:**
- `extends` một class mang theo quan hệ inheritance của **implementation và state**; Java chỉ cho mỗi class có tối đa một superclass trực tiếp.
- `implements` một hoặc nhiều interfaces để thỏa contract; interface có thể chứa abstract/default/static/private methods theo quy tắc Java, nhưng không cung cấp instance fields như class.
- Interface thường là lựa chọn nhẹ hơn để thể hiện **vai trò hoặc khả năng**.

### 1.2. Composition: quan hệ has-a / works-with

Khi viết:

```java
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }
}
```

`Car` giữ một `Engine` để cộng tác; Car không trở thành subtype của Engine.

Composition theo nghĩa **kỹ thuật thiết kế** thường là kết hợp những object nhỏ thành object có hành vi lớn hơn, ủy quyền những công việc phù hợp. Theo nghĩa **UML strong composition**, từ này còn mang ý nghĩa **sở hữu whole–part và vòng đời**. Hai nghĩa **liên quan nhưng không đồng nhất**.

Ví dụ `Car` nhận một `Engine` do caller tạo: đó chắc chắn là **association**; việc Car có sở hữu Engine độc quyền hay không phụ thuộc ownership contract. Trong design patterns, ta vẫn có thể nói Car “được kết hợp từ các thành phần” theo nghĩa object composition.

### 1.3. Delegation: chuyển tiếp hành vi

```java
class ReportService {
    private final Formatter formatter;

    String render(String input) {
        return formatter.format(input);
    }
}
```

`render` **ủy quyền** việc định dạng cho object khác. Một lớp có thể vừa có association với Formatter, vừa sử dụng delegation.

### 1.4. Dependency injection không tự quyết định ownership

```java
ReportService(Formatter formatter) {
    this.formatter = formatter;
}
```

Đây là **constructor injection**. Nó làm dependency hiển thị ở chữ ký và có thể thay khi tạo ReportService. Nhưng constructor injection **không bắt buộc** ReportService sở hữu vòng đời Formatter. Formatter có thể được DI container hoặc caller quản lý.

## 2. Câu hỏi quan trọng nhất: có phải is-a thật sự?

Để đánh giá inheritance, đừng hỏi chỉ “A có đặc điểm giống B không?”. Hãy hỏi:

> Nếu một hàm yêu cầu `B`, việc truyền object `A` có luôn giữ được ý nghĩa và hợp đồng mà hàm kỳ vọng không?

Ví dụ:

```java
void feed(Animal animal) {
    animal.eat();
}
```

Nếu `Dog extends Animal` và mọi Dog đáp ứng contract `eat()` của Animal, quan hệ có lý.

Nhưng “ReportService cần ghi log” không có nghĩa ReportService **là một Logger**:

```java
// Thiết kế đáng ngờ:
// class ReportService extends Logger { ... }
```

Nếu service kế thừa Logger chỉ để gọi `log(...)`, mọi nơi mong đợi Logger có thể nhận ReportService, dù ReportService **không thuộc miền nghĩa Logger**. Điều này phơi ra các operations kế thừa không cần thiết và khiến thay implementation logger khó khăn.

Cách phù hợp hơn:

```java
class ReportService {
    private final Logger logger;

    ReportService(Logger logger) {
        this.logger = logger;
    }
}
```

Một `ReportService` **có/dùng** Logger, thay vì **là** Logger.

## 3. Liskov Substitution Principle (LSP)

**LSP** là phép thử hành vi cho subtype. Nếu `S` được dùng thay `T` ở nơi client trông đợi một `T`, những giả định và hợp đồng hợp lệ của client phải tiếp tục được bảo toàn.

Ở mức thực hành:

- Subclass không nên **tăng yêu cầu đầu vào** vô cớ so với superclass contract.
- Subclass không nên **làm yếu những bảo đảm đầu ra/hậu điều kiện**.
- Subclass cần giữ **invariants** đã hứa bởi abstraction.
- Subclass không được tạo ra các lỗi/hành vi bất ngờ trái contract mà client dựa vào.
- Chữ ký tương thích **chưa đủ**: hành vi cũng phải phù hợp.

### Phản ví dụ: Bird – Penguin

Một abstraction:

```java
class Bird {
    void fly() {
        System.out.println("Flying");
    }
}
```

Nếu `Penguin extends Bird` nhưng Penguin không thể bay và phải override `fly` để ném exception:

```java
class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException();
    }
}
```

thì client gọi `bird.fly()` theo giả định mọi Bird bay được sẽ gặp bất ngờ.

**Giải pháp không nhất thiết là composition cho mọi thứ.** Có thể sửa hệ kiểu:

```java
interface Bird {
    void eat();
}

interface Flyable {
    void fly();
}

final class Sparrow implements Bird, Flyable {
    @Override
    public void eat() { }

    @Override
    public void fly() { }
}

final class Penguin implements Bird {
    @Override
    public void eat() { }
}
```

`Sparrow` và `Penguin` đều là Bird theo contract tối thiểu; chỉ Sparrow triển khai Flyable. **Interface segregation và phân tách vai trò** giúp subtype có ý nghĩa.

**Bài học:** kế thừa nên phản ánh một contract bền vững, không chỉ nhóm các class có tên hoặc thuộc tính giống nhau.

## 4. “Dùng lại code” chưa phải lý do đủ để `extends`

Giả sử hai class cần hàm format:

```java
class StringUtilities {
    String normalize(String value) {
        return value.trim();
    }
}
```

Thiết kế:

```java
// class CustomerService extends StringUtilities { ... }
```

dùng inheritance chỉ để tránh viết `new StringUtilities()` là dấu hiệu **implementation inheritance for convenience** không có quan hệ is-a.

Những lựa chọn tốt hơn tùy bài toán:

1. **Static utility** nếu hành vi thuần, không state và thích hợp là hàm tiện ích.
2. **Composition/delegation** nếu component có state hoặc cần cấu hình/thay implementation.
3. **Interface** nếu client cần một contract trừu tượng.
4. **Superclass** nếu có quan hệ subtype thật sự và một phần implementation chung mang ý nghĩa domain.

Đừng coi số dòng ít hơn ở bản đầu là thước đo duy nhất. Inheritance tạo coupling giữa superclass và subclasses; việc sửa superclass trong tương lai có thể ảnh hưởng rất rộng.

## 5. Quy trình lựa chọn trong 7 bước

Một trình tự đủ thực tế để áp dụng cho yêu cầu mới:

1. **Viết yêu cầu bằng hành vi**: object phải làm gì, đầu vào/đầu ra/invariant là gì?
2. **Xác định roles**: đối tượng là loại của abstraction nào, hay chỉ làm việc với nó?
3. **Kiểm tra substitutability** bằng LSP: có thể dùng object con thay cha mà client vẫn đúng không?
4. **Liệt kê trục thay đổi** (*axes of variation*): thuật toán, nguồn dữ liệu, kênh gửi, quyền truy cập, cấu hình, trạng thái.
5. **Đánh giá nhu cầu thay runtime** và số cách kết hợp các trục.
6. **Xem ownership và vòng đời**: ai tạo, quản lý, đóng, chia sẻ component?
7. **Đánh giá API lâu dài**: testability, coupling, backward compatibility, độ phức tạp, performance thực tế.

Khi quan hệ is-a yếu, nhiều trục biến thể độc lập hoặc cần đổi hành vi khi chạy, composition thường thắng. Khi cần **hợp đồng subtype ổn định và extension points được bảo vệ**, inheritance có thể thắng.

## 6. Cùng một yêu cầu: thiết kế kế thừa dễ gây rối

**Yêu cầu:** bán hàng cần tính giảm giá khác nhau cho khách thường và khách thành viên. Mỗi hóa đơn chứa các mặt hàng, nhưng quy tắc giảm giá có thể thay theo chương trình khuyến mại.

Một phương án inheritance trực tiếp:

```java
class Checkout {
    int total(int subtotal) {
        return subtotal;
    }
}

class MemberCheckout extends Checkout {
    @Override
    int total(int subtotal) {
        return subtotal - 10;
    }
}

class HolidayCheckout extends Checkout {
    @Override
    int total(int subtotal) {
        return subtotal - 20;
    }
}
```

Phương án có thể chạy, nhưng thử đặt câu hỏi:

- Một **Checkout** có thật sự biến thành một subtype khi **chính sách giảm giá** thay đổi?
- Nếu khách thành viên cũng mua vào dịp lễ, cần `HolidayMemberCheckout`?
- Nếu mỗi checkout phải hỗ trợ nhiều chương trình giảm giá tùy hóa đơn, phải tạo object subclass mới?
- Nếu một service đã được tạo trước, làm thế nào thay chính sách giảm giá mà không thay loại object?

Nếu giảm giá là một **chiến lược độc lập**, hierarchy subclass Checkout gắn **trục “kiểu checkout”** với **trục “quy tắc giảm giá”**. Điều này làm việc bổ sung tổ hợp hành vi trở nên khó.

### Rủi ro tổ hợp subclass

Nếu có 3 mức khách hàng × 4 chiến dịch × 2 quy tắc làm tròn, thiết kế bằng subclass theo mọi tổ hợp có thể dẫn tới tới **24 tổ hợp** cần xem xét, trước khi thêm nhu cầu mới.

Không phải lúc nào cũng có đủ 24 concrete subclasses, nhưng số tổ hợp là dấu hiệu rằng **các chiều thay đổi nên được tách**.

## 7. Thiết kế composition: tách chính sách giảm giá

Định nghĩa contract:

```java
interface DiscountPolicy {
    int apply(int subtotal);
}
```

Checkout giữ chính sách:

```java
final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = policy;
    }

    int total(int subtotal) {
        return policy.apply(subtotal);
    }
}
```

Một `Checkout` **dùng** `DiscountPolicy`, không **là** `DiscountPolicy`. Đây là **Strategy pattern qua composition**.

### Chương trình Java 17 hoàn chỉnh

Lưu **`DiscountCompositionDemo.java`**:

```java
interface DiscountPolicy {
    int apply(int subtotal);
}

final class NoDiscount implements DiscountPolicy {
    @Override
    public int apply(int subtotal) {
        return subtotal;
    }
}

final class FixedDiscount implements DiscountPolicy {
    private final int amount;

    FixedDiscount(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
        }
        this.amount = amount;
    }

    @Override
    public int apply(int subtotal) {
        return Math.max(0, subtotal - amount);
    }
}

final class PercentageDiscount implements DiscountPolicy {
    private final int percent;

    PercentageDiscount(int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be 0..100");
        }
        this.percent = percent;
    }

    @Override
    public int apply(int subtotal) {
        return subtotal - (subtotal * percent / 100);
    }
}

final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }

    int total(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal < 0");
        }
        return policy.apply(subtotal);
    }
}

public class DiscountCompositionDemo {
    public static void main(String[] args) {
        Checkout regular = new Checkout(new NoDiscount());
        Checkout member = new Checkout(new FixedDiscount(20));
        Checkout holiday = new Checkout(new PercentageDiscount(10));

        System.out.println("Regular: " + regular.total(200));
        System.out.println("Member: " + member.total(200));
        System.out.println("Holiday: " + holiday.total(200));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DiscountCompositionDemo.java
java DiscountCompositionDemo
```

**Stdout chính xác:**

```text
Regular: 200
Member: 180
Holiday: 180
```

Lợi ích:
- `Checkout` chịu trách nhiệm validate subtotal và điều phối.
- Mỗi `DiscountPolicy` chịu trách nhiệm một thuật toán giảm giá.
- Thêm chính sách mới thường **không cần sửa `Checkout`**.
- Test có thể cung cấp fake policy để kiểm chứng Checkout gọi đúng.
- Chương trình có thể tạo Checkout khác với chiến lược khác ngay tại runtime.

**Giới hạn cần nêu:** phép `subtotal * percent` dùng kiểu int có thể overflow nếu subtotal quá lớn; ví dụ minh họa contract thiết kế, không phải logic tiền tệ production. Trong hệ thống bán hàng, dùng số tiền phù hợp (`long`/`BigDecimal`) cùng quy tắc làm tròn được xác định.

## 8. Composition cho phép thay chiến lược khi chạy

Trong ví dụ trước, field `policy` là `final` nên mỗi Checkout giữ cùng strategy reference. Nhưng có thể cho phép thay qua một operation có kiểm soát:

```java
final class Checkout {
    private DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        setPolicy(policy);
    }

    void setPolicy(DiscountPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }

    int total(int subtotal) {
        return policy.apply(subtotal);
    }
}
```

Nếu business requirement là **“đổi chính sách sau khi service được tạo”**, composition cung cấp cách diễn đạt trực tiếp. Với inheritance, **runtime class của một object không thể bị biến thành subclass khác** chỉ bằng setter.

Tuy nhiên thay dependency mutable ở runtime có thể mang vấn đề:
- Ai có quyền đổi chính sách?
- Có những phép tính đang chạy đồng thời không?
- Cần snapshot policy cho một transaction?
- Có cần audit/log lần chuyển policy?

**Khả năng hoán đổi** không có nghĩa nên tùy tiện mutate object trong hệ thống nhiều thread. Nếu yêu cầu không cần đổi giữa chừng, **constructor injection + final field** thường đơn giản và an toàn hơn.

## 9. “Composition over inheritance” không có nghĩa không được dùng interface

Một nhầm lẫn phổ biến: vì chọn composition nên không dùng `implements`.

Thực tế thiết kế với composition thường **dùng interface rất nhiều**:

```java
interface Serializer {
    byte[] serialize(String value);
}

final class ExportService {
    private final Serializer serializer;

    ExportService(Serializer serializer) {
        this.serializer = serializer;
    }
}
```

Ở đây:
- `JsonSerializer implements Serializer` là quan hệ **type abstraction**.
- `ExportService` giữ `Serializer` là **composition/delegation** ở mức object design.
- `ExportService` không phải subtype của Serializer.
- Một implementation khác của Serializer có thể được inject mà không đổi ExportService.

Quy tắc thiết kế thường là **program to an interface, prefer composition for reuse** — không phải “tránh mọi inheritance/interface”.

## 10. Khi nào inheritance là lựa chọn phù hợp?

Inheritance từ class có thể phù hợp nếu:

- Có một **hợp đồng base type rõ ràng và ổn định**.
- Mọi subtype hợp lệ đều có thể thay superclass theo LSP.
- Superclass định nghĩa **state/behavior chung thực sự thuộc mọi subtype**.
- Có những **extension points** được thiết kế để subclass override.
- Các subclass cần chia sẻ một quy trình chuẩn mà không được bỏ qua các bước invariant.
- Framework/domain chủ động công bố superclass như API mở rộng.

Ví dụ: một **abstract job pipeline** có một method chạy quy trình chung, còn subclass thực hiện đúng một bước đặc thù. Đây là tình huống **template method** có chủ đích.

Ngược lại, nếu subclass chỉ muốn dùng một helper method của superclass mà **không** có quan hệ is-a, inheritance kém thuyết phục.

### “Là một” theo tiếng Việt chưa đủ

Một `Square` có thể được nói là “hình chữ nhật”, nhưng **một Rectangle mutable có setter độc lập `setWidth` và `setHeight`** có thể mang contract không tương thích với Square luôn giữ width=height. Đây là ví dụ kinh điển cho thấy ontology is-a **không tự bảo đảm LSP**.

Hãy kiểm tra method-level contract chứ không chỉ tên miền.

## 11. Ví dụ inheritance hợp lý: abstract Shape

Một ứng dụng cần xử lý tất cả hình theo contract `area()`. Mỗi loại hình tự cung cấp thuật toán diện tích. Khách hàng chỉ cần nhìn qua abstraction.

Lưu **`ShapeInheritanceDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

abstract class Shape {
    abstract double area();

    final String describe() {
        return String.format(Locale.ROOT,
                "%s: %.2f",
                getClass().getSimpleName(), area());
    }
}

final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("positive dimensions");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        if (radius <= 0) {
            throw new IllegalArgumentException("positive radius");
        }
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

public class ShapeInheritanceDemo {
    public static void main(String[] args) {
        List<Shape> shapes = List.of(
                new Rectangle(3, 4),
                new Circle(2));

        for (Shape shape : shapes) {
            System.out.println(shape.describe());
        }
    }
}
```

```bash
javac -encoding UTF-8 ShapeInheritanceDemo.java
java ShapeInheritanceDemo
```

**Stdout:**

```text
Rectangle: 12.00
Circle: 12.57
```

Vì sao inheritance hợp lý trong mô hình này?
1. Cả `Rectangle` và `Circle` đáp ứng cùng contract `area()`.
2. Client có thể lưu `List<Shape>` và gọi `describe()` mà không cần phân nhánh `instanceof`.
3. `describe()` là `final` để giữ một format chung, còn `area()` là abstract extension point.
4. Mỗi subclass kiểm soát các giá trị đầu vào cần thiết cho công thức riêng.
5. Không có yêu cầu đổi một `Rectangle` thành `Circle` trong cùng object.

**Giới hạn:** ví dụ cho thấy inheritance hợp lý với một abstraction ổn định. Một `interface Shape` cũng có thể phù hợp nếu không cần shared instance implementation của abstract class. Chọn interface hay abstract class là quyết định tiếp theo, không phải bằng chứng rằng mọi “Shape” bắt buộc extends một superclass.

## 12. Abstract class, interface hay composition?

| Yêu cầu | Cân nhắc |
| --- | --- |
| Nhiều loại object cần đáp ứng cùng **khả năng** | Interface + implementations |
| Các subtype thực sự thuộc cùng **họ và chia sẻ state/algorithm** | Abstract class/superclass có chủ đích |
| Một class cần **dùng một khả năng** từ bên ngoài | Field/parameter kiểu interface, delegation |
| Hành vi cần thay tùy cấu hình hoặc runtime | Strategy/DI qua composition |
| Cần nhiều trục hành vi kết hợp độc lập | Composition nhiều strategies/components |
| Chỉ một tính năng helper được tái sử dụng | Utility/standalone component |
| Không muốn cho subclass của implementation | `final class` + interface/composition |
| Chỉ cho một tập subtype được xác định | `sealed class`/`sealed interface` trong Java 17 |

**Đừng dùng subclass để mô hình hóa “tùy chọn cấu hình”.** Một sự lựa chọn như format CSV/JSON hoặc payment provider thường là strategy/collaborator; không phải một phiên bản bản thể luận khác của service.

## 13. Nhận diện các trục thay đổi độc lập

Giả sử một hệ thống gửi thông báo có hai chiều thay đổi:

- **Kênh:** email, SMS, push.
- **Định dạng nội dung:** ngắn gọn, chi tiết, HTML.

Nếu tạo subclass cho mọi tổ hợp:

```text
ShortEmailSender
DetailedEmailSender
HtmlEmailSender
ShortSmsSender
DetailedSmsSender
...
```

số subtype có nguy cơ tăng theo tích số lựa chọn của từng chiều.

Composition tách chúng:

```java
interface Channel {
    void deliver(String message);
}

interface Template {
    String render(String name);
}

final class NotificationService {
    private final Channel channel;
    private final Template template;

    NotificationService(Channel channel, Template template) {
        this.channel = channel;
        this.template = template;
    }

    void notify(String name) {
        channel.deliver(template.render(name));
    }
}
```

Thêm Channel mới không cần tạo lại mọi Template, và ngược lại. Đây là lợi ích cốt lõi khi yêu cầu có **nhiều axes of variation**.

## 14. Ví dụ Java 17: hai chiến lược độc lập

Lưu **`NotificationCompositionDemo.java`**:

```java
interface Channel {
    void deliver(String text);
}

interface Template {
    String render(String name);
}

final class ConsoleEmail implements Channel {
    @Override
    public void deliver(String text) {
        System.out.println("EMAIL: " + text);
    }
}

final class ConsoleSms implements Channel {
    @Override
    public void deliver(String text) {
        System.out.println("SMS: " + text);
    }
}

final class SimpleTemplate implements Template {
    @Override
    public String render(String name) {
        return "Hello " + name;
    }
}

final class FormalTemplate implements Template {
    @Override
    public String render(String name) {
        return "Dear " + name + ", welcome.";
    }
}

final class NotificationService {
    private final Channel channel;
    private final Template template;

    NotificationService(Channel channel, Template template) {
        this.channel = channel;
        this.template = template;
    }

    void notify(String name) {
        channel.deliver(template.render(name));
    }
}

public class NotificationCompositionDemo {
    public static void main(String[] args) {
        NotificationService email = new NotificationService(
                new ConsoleEmail(), new FormalTemplate());

        NotificationService sms = new NotificationService(
                new ConsoleSms(), new SimpleTemplate());

        email.notify("An");
        sms.notify("Bình");
    }
}
```

```bash
javac -encoding UTF-8 NotificationCompositionDemo.java
java NotificationCompositionDemo
```

**Stdout:**

```text
EMAIL: Dear An, welcome.
SMS: Hello Bình
```

Ở đây NotificationService **không được subclass** thành `EmailFormalNotificationService`. Thay vào đó nó **phối hợp** hai object đáp ứng hai interfaces độc lập.

Đây là lý do composition thường thích hợp khi hành vi là các **khả năng có thể ghép**, thay vì các “loài” cố định của đối tượng.

## 15. Kế thừa gây coupling với implementation của superclass

Subclass thường bị ràng buộc bởi:

- Chữ ký các constructors của superclass;
- Protected members/virtual methods được công bố cho subclass;
- Thứ tự superclass gọi các hook;
- Quy tắc khởi tạo superclass trước subclass;
- Những thay đổi state/invariants của superclass;
- Những method superclass có thể override;
- Tương tác giữa các overridden methods.

Ví dụ, subclass override `add` để đếm số phần tử, nhưng superclass `addAll` lại gọi `add` cho từng phần tử. Nếu subclass cũng tăng counter trong `addAll`, có thể vô tình **đếm hai lần**. Đây là một dạng vấn đề được gọi là **fragile base class** khi subclass phụ thuộc vào chi tiết internal call của superclass.

Không có nghĩa inheritance luôn sai; nó có nghĩa **superclass muốn hỗ trợ subclassing phải thiết kế và tài liệu hóa extension contract**.

### Composition làm ranh giới hẹp hơn

Một wrapper giữ interface `Collection` hay một service delegate thường chỉ phụ thuộc vào **public contract** của đối tượng cộng tác, không cần biết các method nội bộ gọi nhau như thế nào. Việc cập nhật implementation của delegate có thể ít ảnh hưởng đến wrapper hơn.

Tuy nhiên wrapper cũng phải định nghĩa những operation được phép và bảo đảm không bỏ sót những method mới của interface khi hợp đồng đòi hỏi.

## 16. Phản ví dụ thực tế: subclass `HashSet` để đếm add

Nếu mục tiêu là đếm số phần tử mới thêm vào một `Set`, việc subclass `HashSet` và override `add`/`addAll` rất dễ gây coupling với cách `HashSet`/`AbstractCollection` triển khai các thao tác.

Đoạn minh họa có vấn đề:

```java
class CountingSet<E> extends java.util.HashSet<E> {
    private int additions;

    @Override
    public boolean add(E item) {
        additions++;
        return super.add(item);
    }

    @Override
    public boolean addAll(
            java.util.Collection<? extends E> items) {
        additions += items.size();
        return super.addAll(items);
    }
}
```

Có ít nhất hai sai lệch ý nghĩa:
- `add(item)` tăng counter cả khi item đã tồn tại và `Set` không thêm gì.
- `addAll(items)` tăng thêm `items.size()` trước khi gọi logic superclass, rồi superclass có thể gọi `add` theo một đường triển khai, dẫn đến đếm trùng hoặc phụ thuộc implementation.

**Đừng xây một correctness proof dựa vào việc “superclass hiện tại gọi đúng hook theo cách mình đoán”.**

Một thiết kế composition có thể quản lý rõ hơn số lần thay đổi thành công.

## 17. Chương trình runnable: wrapper Set qua composition

Lưu **`CountingSetCompositionDemo.java`**:

```java
import java.util.Collection;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class CountingSet<E> {
    private final Set<E> elements = new HashSet<>();
    private int successfulAdds;

    boolean add(E value) {
        boolean changed = elements.add(value);
        if (changed) {
            successfulAdds++;
        }
        return changed;
    }

    int addAll(Collection<? extends E> values) {
        Objects.requireNonNull(values);

        int added = 0;
        for (E value : values) {
            if (add(value)) {
                added++;
            }
        }
        return added;
    }

    int size() {
        return elements.size();
    }

    int successfulAdds() {
        return successfulAdds;
    }
}

public class CountingSetCompositionDemo {
    public static void main(String[] args) {
        CountingSet<String> set = new CountingSet<>();

        System.out.println(set.add("A"));
        System.out.println(set.add("A"));
        System.out.println(set.addAll(
                java.util.List.of("A", "B", "C", "C")));
        System.out.println("size = " + set.size());
        System.out.println("adds = " + set.successfulAdds());
    }
}
```

```bash
javac -encoding UTF-8 CountingSetCompositionDemo.java
java CountingSetCompositionDemo
```

**Stdout:**

```text
true
false
2
size = 3
adds = 3
```

`CountingSet` sử dụng `HashSet` như **một thành phần riêng** và tự định nghĩa contract “successfulAdds là số phần tử mới thực sự được thêm qua API này”.

**Giới hạn:** wrapper demo **chưa implements `Set<E>`**; cố ý chỉ cung cấp những operation cần thiết cho use case. Nếu cần một drop-in `Set`, có thể viết một forwarding/decorator implementation đầy đủ, nhưng phải bao phủ đúng hợp đồng `Set` (iterator.remove, clear, removeAll, v.v.) và định nghĩa chính xác metric cần đếm.

Đừng gọi wrapper này là thay thế hoàn chỉnh cho mọi `Set`, bởi nó không implement `Set`.

## 18. Dùng delegation thay vì exposed inheritance API

Một lớp con có thể **thừa hưởng quá nhiều methods** không liên quan đến nghiệp vụ.

Ví dụ `class UserRepository extends ArrayList<User>`:

- Repository sẽ có `get(index)`, `subList`, `sort`, `removeIf` và các mutators theo hợp đồng của List.
- Caller có thể bỏ qua validation/invariant của repository.
- “Repository is-a List” là quan hệ rất khó bảo vệ nếu domain không thật sự cam kết List semantics.

Một cấu trúc tốt hơn:

```java
final class UserRepository {
    private final List<User> users = new ArrayList<>();

    void save(User user) {
        // Validation/uniqueness phù hợp.
        users.add(user);
    }

    List<User> findAll() {
        return List.copyOf(users);
    }
}
```

Đây là đoạn minh họa giả sử đã khai báo `User` và import `List`/`ArrayList`. Repository **có một internal list**, không tuyên bố nó **là một List**.

**Lợi ích:** API có thể chỉ công bố những behavior cần thiết, tránh bị ràng buộc bởi toàn bộ inherited API từ concrete collection.

## 19. Composition và information hiding

Kết hợp đối tượng hiệu quả khi **ẩn implementation detail**:

```java
final class Cart {
    private final List<String> skus = new ArrayList<>();

    void add(String sku) {
        skus.add(sku);
    }

    int size() {
        return skus.size();
    }
}
```

Nếu ngày mai cần thay `ArrayList` bằng `LinkedHashSet` hoặc database-backed repository, một Cart API chỉ công bố `add`/`size` có thể thay đổi internal representation dễ hơn so với `class Cart extends ArrayList`, vốn để lộ toàn bộ API và semantics của ArrayList.

**Nhưng** không phải cứ private field là bất biến:
- Field `final List` không ngăn mutate list.
- Getter trả backing list trực tiếp có thể cho caller phá invariant.
- Caller giữ mutable input alias có thể sửa state ngoài owner.

Cần kiểm soát **encapsulation và ownership**, không chỉ chọn từ khóa “composition”.

## 20. Constructor injection và testability

Composition thường giúp unit test dễ hơn vì dependency được thay bằng một **test double** implement cùng interface.

Giả sử `Checkout` phụ thuộc `DiscountPolicy`. Test không cần kế thừa `Checkout` để chặn thuật toán, mà cung cấp fake policy có kết quả dự đoán được.

Lưu **`CompositionTestDemo.java`**:

```java
interface TaxPolicy {
    int addTax(int subtotal);
}

final class Checkout {
    private final TaxPolicy policy;

    Checkout(TaxPolicy policy) {
        this.policy = policy;
    }

    int total(int subtotal) {
        return policy.addTax(subtotal);
    }
}

final class FixedTestTax implements TaxPolicy {
    private int calls;

    @Override
    public int addTax(int subtotal) {
        calls++;
        return subtotal + 7;
    }

    int calls() {
        return calls;
    }
}

public class CompositionTestDemo {
    public static void main(String[] args) {
        FixedTestTax fake = new FixedTestTax();
        Checkout checkout = new Checkout(fake);

        System.out.println(checkout.total(10));
        System.out.println("calls = " + fake.calls());
    }
}
```

```bash
javac -encoding UTF-8 CompositionTestDemo.java
java CompositionTestDemo
```

**Stdout:**

```text
17
calls = 1
```

Test double `FixedTestTax` ghi nhận số lần được gọi. Vì `Checkout` không tự tạo concrete tax calculator, test có thể kiểm tra **interaction** rõ ràng.

Tuy nhiên **DI không tự làm mọi test tốt hơn**. Nếu một class không có dependency biến đổi, dùng interface chỉ để test có thể tạo thêm abstraction không cần thiết. Hãy đánh giá nhu cầu thực.

## 21. Inheritance có thể dùng Template Method hợp lý

Có những yêu cầu cần **một pipeline bắt buộc** được mọi subtype tuân thủ, trong khi chỉ một bước được tùy biến. Đây là trường hợp inheritance có thể tốt.

Lưu **`TemplateMethodChoiceDemo.java`**:

```java
import java.util.Locale;

abstract class ImportJob {
    public final String run(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw required");
        }

        String normalized = raw.trim();
        return transform(normalized);
    }

    protected abstract String transform(String normalized);
}

final class UppercaseJob extends ImportJob {
    @Override
    protected String transform(String normalized) {
        return normalized.toUpperCase(Locale.ROOT);
    }
}

final class DashJob extends ImportJob {
    @Override
    protected String transform(String normalized) {
        return normalized.replace(" ", "-");
    }
}

public class TemplateMethodChoiceDemo {
    public static void main(String[] args) {
        ImportJob first = new UppercaseJob();
        ImportJob second = new DashJob();

        System.out.println(first.run("  hello java  "));
        System.out.println(second.run("  hello java  "));
    }
}
```

```bash
javac -encoding UTF-8 TemplateMethodChoiceDemo.java
java TemplateMethodChoiceDemo
```

**Stdout:**

```text
HELLO JAVA
hello-java
```

Trong thiết kế này:

- `ImportJob` là một **base contract thực sự** của các import jobs.
- `run` là `final` để subclass không thể override và bỏ qua normalize/null check bằng cách thay toàn bộ pipeline.
- `transform` là extension point rõ và có chữ ký ổn định.
- Concrete jobs là subtype thực hiện một bước.
- Subclass **không** có quyền viết lại lifecycle tổng thể.

**Cảnh báo:** method `transform` vẫn có thể ném exception hoặc gây side effects. Final template method không tự bảo vệ mọi invariant của chương trình nếu contract hook quá rộng.

## 22. Cùng Template Method đó có thể viết bằng composition

Nếu biến thể `transform` cần được cung cấp runtime thay vì tạo subclass `ImportJob`, ta có thể viết:

```java
interface Transformer {
    String transform(String input);
}

final class ImportService {
    private final Transformer transformer;

    ImportService(Transformer transformer) {
        this.transformer = transformer;
    }

    String run(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw required");
        }
        return transformer.transform(raw.trim());
    }
}
```

Hai hướng khác nhau:

| Khía cạnh | Inheritance template | Composition transformer |
| --- | --- | --- |
| Điểm thay đổi | Subclass override hook | Object collaborator implement interface |
| Chọn behavior | Thường lúc chọn/khởi tạo subtype | Lúc cung cấp dependency |
| Thay implementation trên cùng service object | Không thay runtime class | Có thể thiết kế thay component nếu cần |
| Coupling | Subclass ↔ superclass hooks/state | Service ↔ interface contract |
| Mở rộng nhiều trục | Khó hơn nếu gộp trong một hierarchy | Thuận lợi khi tách nhiều interfaces |
| Phù hợp | Framework chủ động tạo họ subtype | Strategy/configuration/provider |

**Không có đáp án tuyệt đối.** Nếu dự án có framework base class được tài liệu hóa và các subtype thật sự thuộc họ ImportJob, inheritance là lựa chọn hợp lý. Nếu transformer độc lập, dùng chung bởi nhiều services và thay liên tục, composition thường hợp lý hơn.

## 23. Decorator: mở rộng hành vi bằng wrapping thay vì subclass explosion

Một yêu cầu thường gặp:

> Có `Sender` gửi thông báo. Cần thêm logging, tiền tố và kiểm tra mà không sửa concrete sender. Có thể bật/tắt những behavior này theo cấu hình.

Tạo `LoggedEmailSender`, `PrefixedEmailSender`, `LoggedPrefixedEmailSender` ... dễ dẫn đến bùng nổ subclasses.

**Decorator** dùng interface chung và mỗi wrapper giữ một delegate:

```java
interface Sender {
    void send(String text);
}

final class PrefixSender implements Sender {
    private final Sender delegate;

    PrefixSender(Sender delegate) {
        this.delegate = delegate;
    }

    @Override
    public void send(String text) {
        delegate.send("[INFO] " + text);
    }
}
```

Một `PrefixSender` **implements Sender** (đáp ứng contract) và **có một Sender delegate** (composition). Đây là ví dụ cụ thể rằng polymorphism và composition không loại trừ nhau.

### Chương trình runnable Decorator

Lưu **`DecoratorChoiceDemo.java`**:

```java
interface Sender {
    void send(String text);
}

final class ConsoleSender implements Sender {
    @Override
    public void send(String text) {
        System.out.println("SEND " + text);
    }
}

final class PrefixSender implements Sender {
    private final Sender delegate;

    PrefixSender(Sender delegate) {
        this.delegate = delegate;
    }

    @Override
    public void send(String text) {
        delegate.send("[INFO] " + text);
    }
}

final class AuditSender implements Sender {
    private final Sender delegate;

    AuditSender(Sender delegate) {
        this.delegate = delegate;
    }

    @Override
    public void send(String text) {
        System.out.println("AUDIT " + text);
        delegate.send(text);
    }
}

public class DecoratorChoiceDemo {
    public static void main(String[] args) {
        Sender base = new ConsoleSender();
        Sender prefix = new PrefixSender(base);
        Sender audited = new AuditSender(prefix);

        audited.send("hello");
        base.send("plain");
    }
}
```

```bash
javac -encoding UTF-8 DecoratorChoiceDemo.java
java DecoratorChoiceDemo
```

**Stdout:**

```text
AUDIT hello
SEND [INFO] hello
SEND plain
```

Mỗi wrapper có contract `Sender` nhưng hành vi được tạo bởi **kết hợp đối tượng**. Có thể thay thứ tự wrapper hoặc bỏ wrapper theo nhu cầu mà không tạo subclass mới cho từng tổ hợp.

**Chú ý:** thứ tự decoratos có thể thay thứ tự side effects. Đây là một phần contract hệ thống và cần test, không coi mọi hoán vị đều tương đương.

## 24. Adapter: composition khi hai API không có quan hệ is-a

**Yêu cầu:** ứng dụng dùng interface `PaymentPort`, nhưng thư viện legacy chỉ có một API khác về tên và định dạng tham số.

Không nên:

```java
// class PaymentService extends LegacyGateway { ... }
```

chỉ để thừa hưởng `chargeCents`. Service không phải là gateway.

Adapter nhận gateway và chuyển lời gọi:

```java
interface PaymentPort {
    String pay(int cents);
}

class LegacyGateway {
    String chargeCents(int cents) {
        return "OK:" + cents;
    }
}

final class LegacyPaymentAdapter implements PaymentPort {
    private final LegacyGateway gateway;

    LegacyPaymentAdapter(LegacyGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public String pay(int cents) {
        return gateway.chargeCents(cents);
    }
}
```

Adapter **implements** một interface của ứng dụng và **has-a** legacy object. Đây thường là cách ít coupling hơn so với làm domain service extends external library class.

### Ví dụ Java 17 đầy đủ

Lưu **`AdapterChoiceDemo.java`**:

```java
interface PaymentPort {
    String pay(int cents);
}

final class LegacyGateway {
    String chargeCents(int cents) {
        return "OK:" + cents;
    }
}

final class LegacyPaymentAdapter implements PaymentPort {
    private final LegacyGateway gateway;

    LegacyPaymentAdapter(LegacyGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    @Override
    public String pay(int cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }
        return gateway.chargeCents(cents);
    }
}

final class BillingService {
    private final PaymentPort payments;

    BillingService(PaymentPort payments) {
        this.payments = payments;
    }

    String charge(int cents) {
        return payments.pay(cents);
    }
}

public class AdapterChoiceDemo {
    public static void main(String[] args) {
        PaymentPort adapter =
                new LegacyPaymentAdapter(new LegacyGateway());

        BillingService billing = new BillingService(adapter);

        System.out.println(billing.charge(1500));
    }
}
```

```bash
javac -encoding UTF-8 AdapterChoiceDemo.java
java AdapterChoiceDemo
```

**Stdout:**

```text
OK:1500
```

Adapter giúp cô lập API bên ngoài ở ranh giới. Nếu ngày mai thay `LegacyGateway`, domain `BillingService` vẫn phụ thuộc `PaymentPort`. Code production cần thêm transaction IDs, retries, idempotency, currency và xử lý lỗi; ví dụ ở đây chỉ minh họa chọn quan hệ.

## 25. Một class không được đa kế thừa class trong Java

Java không cho:

```java
// class FlyingCar extends Car, Airplane { }
// SAI: Java không hỗ trợ extends hai classes.
```

Nhưng Java cho một class **implements nhiều interfaces**:

```java
interface Flyable {
    void fly();
}

interface Drivable {
    void drive();
}

final class FlyingCar implements Flyable, Drivable {
    @Override
    public void fly() { }

    @Override
    public void drive() { }
}
```

Nếu hành vi bay và lái là các **component riêng, có thể thay**, composition còn phù hợp hơn:

```java
class Vehicle {
    private final FlightSystem flightSystem;
    private final DriveSystem driveSystem;
}
```

Trong ví dụ cuối, các kiểu `FlightSystem`/`DriveSystem` là giả định minh họa; phải khai báo chúng nếu muốn biên dịch đoạn độc lập.

**Cần chọn theo yêu cầu:** nếu `FlyingCar` tự thực hiện hai contract và không cần hoán đổi implementation, nhiều interfaces có thể đủ. Nếu mỗi khả năng do một hệ thống con có cấu hình và vòng đời riêng, dùng composition.

## 26. Java 17 sealed types: khi tập subtype hữu hạn và có chủ đích

Java 17 hỗ trợ **sealed classes/interfaces**, cho phép kiểm soát **direct permitted subclasses/implementations**.

Ví dụ:

```java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String message) implements Result {
}
```

Hai records là final types, đáp ứng yêu cầu phân nhánh của sealed interface.

**Khi nào sealed hierarchy phù hợp?**
- Domain có một **tập biến thể đã biết và giới hạn**.
- Mọi biến thể thật sự là subtype của một contract.
- Bạn muốn compiler giúp giới hạn implementations hợp lệ.
- API không chủ trương cho plugin bên ngoài tùy ý tạo subtype mới.

**Khi nào composition hợp lý hơn?**
- Các thành phần/strategies được bên thứ ba bổ sung liên tục.
- Nhiều trục hành vi cần kết hợp.
- Cần hoán đổi hành vi lúc chạy.
- Một đối tượng có nhiều “vai trò” hợp tác nhưng không phải một biến thể đóng của một abstract type.

Đừng chọn sealed chỉ vì nó mới. Một interface thường và composition có thể đơn giản hơn cho extensibility mở.

### Chương trình sealed runnable

Lưu **`SealedChoiceDemo.java`**:

```java
sealed interface Outcome permits Success, Failure {
    String describe();
}

record Success(String value) implements Outcome {
    @Override
    public String describe() {
        return "OK: " + value;
    }
}

record Failure(String reason) implements Outcome {
    @Override
    public String describe() {
        return "ERROR: " + reason;
    }
}

public class SealedChoiceDemo {
    public static void main(String[] args) {
        Outcome first = new Success("saved");
        Outcome second = new Failure("invalid");

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

```bash
javac -encoding UTF-8 SealedChoiceDemo.java
java SealedChoiceDemo
```

**Stdout:**

```text
OK: saved
ERROR: invalid
```

## 27. Final class và record gợi ý composition

Một `final class` không thể có subclass. Một Java record cũng **ngầm định final**.

```java
final class CustomerId {
    private final String value;

    CustomerId(String value) {
        this.value = value;
    }
}

record Money(long cents) {
}
```

Nếu yêu cầu là mở rộng behavior của service sử dụng `Money` hoặc `CustomerId`, việc thử `extends Money` sẽ thất bại. Thay vào đó thường:

- Tạo service/helper nhận value object.
- Dùng interface abstraction nếu có nhiều implementations thật sự.
- Kết hợp immutable values vào aggregates.
- Decorate behavior của service qua collaborators.

**Nhưng** final/record không tự bảo đảm deeply immutable khi field/component là mutable object; bảo vệ aliasing vẫn cần trong mô hình sở hữu.

Đừng bỏ `final` khỏi value object chỉ để dùng inheritance như cách tái sử dụng utility.

## 28. Trường hợp thay thế hành vi tùy user/tenant/runtime

Nếu một phương thức cần lựa chọn strategy theo cấu hình user/tenant:

```java
DiscountPolicy policy = policies.forCustomer(customer);
Checkout checkout = new Checkout(policy);
```

là cách diễn đạt tốt: object `Checkout` được ghép từ policy phù hợp cho yêu cầu đó.

Nếu tạo một subclass Checkout cho từng tenant:

```text
TenantACheckout
TenantBCheckout
TenantCCheckout
...
```

thì domain/service code sẽ bị ràng buộc vào tenant, khó mở rộng khi cấu hình chuyển đổi.

Tuy vậy phải làm rõ **strategy được chọn ở đâu**:
- Tại controller/service orchestration?
- Tại factory?
- Trong DI container scope?
- Per request hay singleton?

Composition chỉ giúp tách responsibilities; hệ thống vẫn cần một **composition root** hoặc factory chịu trách nhiệm lắp ráp dependencies.

## 29. Composition root: nơi lắp ráp object graph

Một anti-pattern là service tự tạo dependency:

```java
class Checkout {
    private final DiscountPolicy policy =
            new FixedDiscount(10);
}
```

Khi yêu cầu thay policy, phải sửa Checkout hoặc thêm logic điều kiện vào trong.

Có thể đưa việc chọn implementation ra **composition root**:

```java
DiscountPolicy policy = new FixedDiscount(10);
Checkout checkout = new Checkout(policy);
```

Đây thường là code ở tầng khởi động ứng dụng, controller factory hoặc DI configuration.

**Cần phân biệt:**
- **Composition**: Checkout phối hợp với Policy.
- **Dependency injection**: Policy được cấp vào Checkout.
- **Composition root**: nơi chọn/tạo/lắp ráp Policy và Checkout.

Một ứng dụng nhỏ có thể lắp thủ công bằng `new` mà không cần DI framework.

## 30. Ownership và vòng đời: không phải cứ nhận component là sở hữu

```java
class ReportService {
    private final OutputStream output;

    ReportService(OutputStream output) {
        this.output = output;
    }
}
```

Field `output` có thể thể hiện association/dependency lâu dài. Nhưng trách nhiệm `close()` **không suy ra tự động**:
- Nếu `ReportService` **mượn** output stream, caller phải đóng.
- Nếu constructor **nhận chuyển giao ownership**, service có thể chịu trách nhiệm đóng.
- Nếu stream được chia sẻ bởi nhiều services, một service tự đóng có thể làm hỏng service khác.

Một ownership contract tốt phải nói rõ:
- Ai tạo?
- Ai được sử dụng?
- Ai được thay đổi?
- Ai phải đóng?
- Khi nào việc đóng xảy ra?
- Các references khác có còn được dùng không?

Trong UML, **strong composition** gắn với vòng đời whole–part; trong Java, một field `final` hoặc một constructor parameter **không tự enforce ownership độc quyền**.

## 31. Ví dụ composition sở hữu resource

Lưu **`OwnedResourceDemo.java`**:

```java
final class Connection implements AutoCloseable {
    private boolean closed;

    void query() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        System.out.println("query");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("connection closed");
        }
    }
}

final class Session implements AutoCloseable {
    private final Connection connection = new Connection();

    void execute() {
        connection.query();
    }

    @Override
    public void close() {
        connection.close();
    }
}

public class OwnedResourceDemo {
    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.execute();
        }
        System.out.println("done");
    }
}
```

```bash
javac -encoding UTF-8 OwnedResourceDemo.java
java OwnedResourceDemo
```

**Stdout:**

```text
query
connection closed
done
```

`Session` **tự tạo Connection và chịu trách nhiệm close**: đây là ownership mạnh đối với resource.

Ngược lại, nếu Session chỉ nhận một shared Connection từ caller/DI container, API cần định nghĩa rõ việc Session có được đóng shared connection không. Không thể kết luận từ cú pháp `private final Connection connection`.

**GC không thay `close()`.** Java không bảo đảm object bị thu hồi memory ngay sau khi biến local mất tham chiếu. Với file/socket/connection thực, dùng `AutoCloseable` và try-with-resources hoặc quản lý vòng đời rõ ràng.

## 32. Phản ví dụ “mọi has-a đều là UML composition”

```java
final class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }
}
```

Nếu `Engine` do caller tạo, có thể dùng chung với một object khác hoặc chuyển owner, quan hệ code là association, **chưa thể kết luận strong UML composition**.

Nếu `Car` tạo Engine nội bộ, kiểm soát cập nhật và chịu trách nhiệm kết thúc vòng đời Engine theo contract, composition mạnh có thể phù hợp.

**Điểm cần phân biệt:**
- Trong **design-pattern vocabulary**, “composition over inheritance” thường nói về **đưa object khác vào để ủy quyền**, kể cả DI/shared dependencies.
- Trong **UML**, filled diamond **composition** có nghĩa whole–part ownership đặc biệt.
- Một thiết kế có thể tốt với **association + delegation** mà không cần gọi là UML composition.

## 33. Ranh giới đóng gói và defensive copy

Composition có thể bị phá nếu object ngoài được sửa trực tiếp:

```java
class Order {
    private final List<String> items = new ArrayList<>();

    List<String> items() {
        return items; // Lộ backing list mutable.
    }
}
```

Caller có thể `order.items().clear()`, bỏ qua API nghiệp vụ `removeItem`.

Cách an toàn hơn khi elements immutable:

```java
List<String> items() {
    return List.copyOf(items);
}
```

`List.copyOf` trả unmodifiable snapshot của cấu trúc list từ nguồn mutable thông thường; với **mutable elements**, bản sao vẫn nông và có thể chia sẻ state phần tử. Nếu giữ mutable input của caller, constructor cũng cần defensive copy ở **đầu vào**.

**Không nhầm:** `Collections.unmodifiableList(backing)` trả unmodifiable **view** có thể phản ánh cập nhật backing list; nó không tự trở thành snapshot.

Việc chọn composition đi đôi với thiết kế **ownership/mutability contract**, không phải chỉ cất object vào private field.

## 34. Kế thừa và khởi tạo object: constructor superclass chạy trước

Trong Java, khi tạo subclass instance, quá trình constructor đi qua superclass trước khi subclass hoàn tất khởi tạo fields/constructor body của mình.

Nếu constructor superclass gọi một overridable method, dynamic dispatch có thể chạy implementation subclass **trước khi fields của subclass được khởi tạo tường minh**.

Ví dụ:

```java
class Parent {
    Parent() {
        show();
    }

    void show() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String state = "READY";

    @Override
    void show() {
        System.out.println(state);
    }
}
```

`new Child()` có thể in `null` khi `Parent` constructor gọi `show()` trước khi field initializer `state = "READY"` của Child chạy.

Đây là một rủi ro **đặc thù của inheritance/lifecycle**. Với composition, constructor thường có thể nhận một component đã được khởi tạo đầy đủ; tuy nhiên cũng cần tránh truyền `this` ra ngoài quá sớm hoặc gọi callback trước khi object hoàn chỉnh.

### Chương trình kiểm chứng

Lưu **`ConstructorOverrideRiskDemo.java`**:

```java
class Parent {
    Parent() {
        show();
    }

    void show() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String state = "READY";

    @Override
    void show() {
        System.out.println("Child state: " + state);
    }
}

public class ConstructorOverrideRiskDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 ConstructorOverrideRiskDemo.java
java ConstructorOverrideRiskDemo
```

**Stdout:**

```text
Child state: null
```

Đừng coi đây là cách thiết kế nên làm. Nó minh họa vì sao subclass coupling và overridable constructor calls có rủi ro. Một base class có chủ đích cho subclass nên tránh gọi methods overridable từ constructors.

## 35. Khi nào inheritance thắng composition vì tính đơn giản?

Một hệ thống nhỏ có một **closed hierarchy** ổn định, ví dụ `Success` và `Failure` là hai trạng thái kết quả thực sự khác biệt, có thể biểu diễn bằng sealed interface + records.

Nếu cố composition mọi thứ:

```java
class Outcome {
    private final StatusKind kind;
    private final Object payload;
}
```

rồi liên tục kiểm tra `kind` và cast `payload`, thiết kế có thể kém type safety hơn so với một hierarchy rõ ràng.

Khi mỗi loại **là một biến thể hợp lệ** của một abstraction và tập biến thể được quản lý, polymorphic subtype model là cách tự nhiên.

### Các trường hợp inheritance phù hợp

- Thực thể có subtype thật sự và mọi client dùng base contract đều hợp lệ.
- Domain có họ dữ liệu đóng cần mô hình variant (sealed interface/record).
- Framework khai báo abstract base class và hợp đồng override rõ.
- Một base class chứa code/hook ổn định mà subclasses chính là những loại của base.
- Cần polymorphic API cho cùng một hành vi mà implementations thực sự thuộc một role.

**Câu quan trọng:** thiết kế tốt đôi khi dùng **inheritance cho role/interface** và **composition cho behavior/dependency** trong cùng giải pháp.

## 36. Khi nào composition thắng inheritance rõ ràng?

Dấu hiệu mạnh:

- Mối quan hệ thực tế là **uses-a/has-a**, không phải is-a.
- Muốn hoán đổi thuật toán hoặc implementation theo cấu hình/runtime.
- Nhiều biến thể có thể kết hợp độc lập.
- Class mới chỉ muốn tái sử dụng một phần helper của class khác.
- Superclass cung cấp quá nhiều public/protected API không phù hợp.
- Cần quản lý component lifecycle/ownership tách khỏi service.
- Cần test bằng fake/mock collaborator mà không làm thay state nội bộ của superclass.
- Muốn tránh phụ thuộc vào cách superclass gọi các methods nội bộ.
- Muốn adapter/decorator/strategy thay vì tăng số subclasses.
- Library third-party class có API/constructor/invariant dễ thay đổi.

Composition có chi phí riêng: thêm interfaces, forwarding boilerplate, object wiring, xử lý null/lifecycle và có thể gây quá nhiều abstraction nếu lạm dụng. Vì vậy “composition luôn thắng” cũng sai.

## 37. Bảng quyết định nhanh theo yêu cầu cụ thể

| Yêu cầu | Hướng thường phù hợp | Lý do |
| --- | --- | --- |
| Một `Dog` cần được dùng như `Animal` theo contract hợp lệ | Inheritance hoặc interface | Is-a/substitutability |
| `OrderService` cần gửi email | Composition với `MessageSender` | Uses-a; kênh gửi thay được |
| Ứng dụng có format CSV/JSON/XML | Composition Strategy | Thuật toán format là trục thay đổi |
| Cần validate rồi chạy một bước tùy biến của cùng họ Jobs | Abstract base + final template | Invariant của pipeline |
| Đối tượng có nhiều tính năng có thể bật/tắt | Composition/decorators | Tránh tổ hợp subclass |
| Một loại object có nhiều roles (Comparable, Closeable...) | Implements interfaces phù hợp | Contract khả năng, không cần superclass implementation |
| Một hierarchy có tập kết quả Success/Failure giới hạn | Sealed interface + records | Closed sum-like variants |
| Repository muốn dùng ArrayList để lưu | Composition | Repository không phải List |
| Cần thích ứng cổng thanh toán legacy | Adapter + composition | Tách external implementation |
| Một `Order` sở hữu OrderLines theo domain | Composition mạnh/aggregate | Vòng đời và invariant part |
| Nhiều services dùng chung connection pool | Association/DI; pool owner riêng | Shared dependency, không sở hữu riêng |
| Framework chỉ cho extends `AbstractController` | Inheritance khi contract được đảm bảo | Tuân thủ extension points framework |
| Muốn code gần giống superclass nhưng LSP sai | Composition/contract tách lại | Tránh subtype giả |
| Cần đổi discount policy mỗi request | Composition/factory | Strategy được lựa chọn runtime |
| Chỉ cần một hàm `Math.max` | Static utility | Không cần object relation |
| Cần thêm audit/logging mà không sửa sender | Decorator | Wrapping behavior |

Đây là gợi ý, không phải kết luận tự động. Một yêu cầu lớn có thể cần **cả hai** tại những ranh giới khác nhau.

## 38. Phương pháp “yêu cầu → quan hệ → code” từng bước

Cho một yêu cầu:

> Hệ thống xuất báo cáo. Báo cáo có title, data; user có thể chọn PDF hoặc CSV; mọi báo cáo phải được kiểm tra quyền truy cập trước khi xuất; storage provider có thể thay từ local sang cloud.

Phân tích:

**Bước 1 — Trách nhiệm:**
- `Report`: dữ liệu và invariant của báo cáo.
- `ReportExporter`: cách tạo file từ Report.
- `Storage`: cách lưu bytes/file.
- `ExportService`: kiểm tra quyền rồi điều phối export và save.

**Bước 2 — Biến thể:**
- Export format: PDF/CSV.
- Storage: local/cloud.
- Authorization: có thể tùy chính sách.

**Bước 3 — Quan hệ:**
- `Report` **không phải** Exporter hay Storage.
- `ExportService` **dùng** Exporter, Storage và Authorizer.
- `PdfExporter` và `CsvExporter` đều **implements `ReportExporter`**.
- `LocalStorage` và `CloudStorage` đều **implements `Storage`**.

**Bước 4 — Lựa chọn:**
- Dùng composition để phối hợp ba dependencies.
- Dùng interfaces để đa hình các implementations.
- Dùng một entry point có kiểm tra quyền; tránh để subclass override rồi bỏ check.
- Dùng DI/factory ở composition root để chọn component theo config.
- Nếu có resource, xác định owner/`close()` riêng.

Không nên tạo một hierarchy:

```text
PdfLocalAuthorizedExportService
PdfCloudAuthorizedExportService
CsvLocalAuthorizedExportService
CsvCloudAuthorizedExportService
...
```

vì đó là kết hợp nhiều trục thay đổi độc lập.

## 39. Chương trình Java 17 cho bài toán report

Dưới đây là phiên bản tối giản cho **export format + storage**, có một bước permission check. Nó không thực hiện PDF thật; chữ `PDF:` chỉ là ký hiệu để tập trung vào thiết kế quan hệ.

Lưu **`ReportDesignDemo.java`**:

```java
import java.util.Objects;

record Report(String title, String body) {
    Report {
        Objects.requireNonNull(title);
        Objects.requireNonNull(body);
    }
}

interface ReportExporter {
    String export(Report report);
}

final class CsvExporter implements ReportExporter {
    @Override
    public String export(Report report) {
        return "CSV:" + report.title() + "|" + report.body();
    }
}

final class PdfMarkerExporter implements ReportExporter {
    @Override
    public String export(Report report) {
        return "PDF:" + report.title() + "|" + report.body();
    }
}

interface Storage {
    void save(String content);
}

final class ConsoleStorage implements Storage {
    @Override
    public void save(String content) {
        System.out.println("SAVED " + content);
    }
}

interface Authorizer {
    boolean canExport(String user);
}

final class NamedUserAuthorizer implements Authorizer {
    @Override
    public boolean canExport(String user) {
        return "admin".equals(user);
    }
}

final class ExportService {
    private final ReportExporter exporter;
    private final Storage storage;
    private final Authorizer authorizer;

    ExportService(
            ReportExporter exporter,
            Storage storage,
            Authorizer authorizer) {
        this.exporter = Objects.requireNonNull(exporter);
        this.storage = Objects.requireNonNull(storage);
        this.authorizer = Objects.requireNonNull(authorizer);
    }

    void exportFor(String user, Report report) {
        if (!authorizer.canExport(user)) {
            System.out.println("DENIED " + user);
            return;
        }
        storage.save(exporter.export(report));
    }
}

public class ReportDesignDemo {
    public static void main(String[] args) {
        Report report = new Report("Sales", "Q1");

        Authorizer auth = new NamedUserAuthorizer();
        Storage storage = new ConsoleStorage();

        ExportService csv = new ExportService(
                new CsvExporter(), storage, auth);
        ExportService pdf = new ExportService(
                new PdfMarkerExporter(), storage, auth);

        csv.exportFor("admin", report);
        pdf.exportFor("guest", report);
        pdf.exportFor("admin", report);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReportDesignDemo.java
java ReportDesignDemo
```

**Stdout:**

```text
SAVED CSV:Sales|Q1
DENIED guest
SAVED PDF:Sales|Q1
```

**Cách hiểu quan hệ:**

- `Report` là dữ liệu, không `extends ReportExporter` hay `Storage`.
- `CsvExporter`/`PdfMarkerExporter` đáp ứng **is-a ReportExporter** theo interface contract.
- `ConsoleStorage` đáp ứng **is-a Storage**.
- `ExportService` **có/dùng** ba collaborators và **ủy quyền** nhiệm vụ cho chúng.
- `ExportService.exportFor` kiểm tra quyền **trước** khi gọi exporter/storage.
- Sự kết hợp CSV/PDF với Storage/Auth độc lập; không cần subclass ExportService cho mọi tổ hợp.

**Giới hạn thực tế:** một exporter CSV thật phải escape dấu phân cách/quotes, PDF cần thư viện và đặc tả, authorization cần kiểm soát danh tính/chính sách, Storage cần xử lý lỗi/giao dịch. Ví dụ dùng marker strings và output ổn định chỉ để minh họa **quyết định kiến trúc**.

## 40. Tránh quá nhiều interface không mang giá trị

Composition có thể gây **overengineering** nếu với một đối tượng đơn giản, không có biến thể và không cần test double, người viết tạo:

```text
INameReader
NameReaderImpl
NameReaderFactory
NameReaderManager
NameReaderManagerAdapter
...
```

mà không có lý do thay implementation rõ ràng.

Một số tình huống **đừng vội trừu tượng hóa**:
- Value object nhỏ dùng `record`.
- Helper function đơn giản không state.
- Một service ổn định không có collaborator nào cần thay.
- Abstraction được tạo chỉ vì “mỗi class phải có interface” dù client không cần.

Nguyên tắc: **đặt abstraction ở chỗ có biến thể hoặc ranh giới trách nhiệm**, chứ không phải tăng số types cho đẹp sơ đồ.

**Một concrete collaborator private field vẫn là composition.** Interface có giá trị khi thật sự cần tách hợp đồng khỏi implementation.

## 41. So sánh coupling và khả năng thay đổi

| Tiêu chí | Inheritance từ class | Composition qua interface |
| --- | --- | --- |
| Mối quan hệ | Is-a/subtype + implementation sharing | Has-a/uses-a + delegation |
| Chia sẻ state của superclass | Có thể có | Không tự động; collaborator giữ state riêng |
| Coupling với superclass internals | Có thể mạnh, nhất là protected hooks | Chủ yếu qua interface contract nếu che giấu đúng |
| Thay collaborator implementation | Không đổi runtime class hiện tại | Có thể đổi bằng injection/new instance/config |
| Nhiều trục hành vi | Dễ nhiều subclasses | Ghép independent components |
| Khả năng bảo vệ quy trình | Final template method | Service kiểm soát flow và delegate các bước |
| Test isolation | Có thể cần subclass/test hooks | Fake/mock interface thuận lợi |
| API exposed | Subclass thừa hưởng các members phù hợp | Wrapper chỉ công bố API mong muốn |
| Vòng đời | Constructor chain cha–con gắn chặt | Component có ownership/lifecycle riêng |
| Chi phí code | Có thể ít wiring ban đầu | Có thể nhiều interfaces/delegation |
| Rủi ro | LSP, fragile base class, overriding lifecycle | Over-abstraction, wiring, alias/ownership |
| Dùng hợp lý nhất khi | Quan hệ subtype ổn định | Cộng tác, strategies, biến thể runtime |

**Không xem bảng là chứng minh hiệu năng.** JVM tối ưu phương thức ảo và interface calls khá mạnh; lựa chọn kiến trúc nên dựa vào semantics, maintainability và benchmarks nếu performance là ràng buộc quan trọng.

## 42. Static utility, association và inheritance: chọn đúng công cụ

Không phải mọi thao tác cần một trong hai kỹ thuật:

```java
int maximum = Math.max(10, 20);
```

Đây là lời gọi **static utility** thuần, không có object collaborator cần lưu trong field.

Nếu helper có cấu hình, caching hoặc external resource:
- Nó có thể đáng trở thành service component được inject.
- Nếu chỉ là một biểu thức thuần, static method có thể đủ.
- Không nên tạo superclass chỉ để đưa một static helper vào hierarchy.

Một tiêu chí hữu ích:

**Stateful behavior do một instance quản lý?** Cân nhắc instance collaborator/composition.

**Pure stateless calculation?** Cân nhắc static function hoặc functional interface nếu cần thay implementation.

**Behavior của chính subtype?** Cân nhắc instance polymorphism/interface/inheritance.

## 43. API compatibility: inheritance ràng buộc người dùng thư viện

Nếu library công bố:

```java
public class BaseProcessor {
    protected void step() {
    }
}
```

các clients có thể đã tạo subclasses override `step()`. Việc đổi superclass:
- Thêm/đổi method;
- Thay gọi thứ tự các hooks;
- Đổi access;
- Đánh dấu final;
- Đổi invariant trong constructor;

có thể phá source/binary compatibility hoặc behavior của clients.

Với composition qua một interface hẹp, library có thể cô lập nhiều implementation details khỏi external plugins. Tuy nhiên **thay interface contract** cũng có thể phá compatibility, nên cần versioning và test contract tương tự.

### Quy tắc thực tế

Một class chỉ nên được thiết kế “for inheritance” khi **tác giả chủ động hỗ trợ subclassing**, tài liệu hóa overridable methods và nghĩa của hooks. Nếu không, cân nhắc `final class` hoặc không công bố protected extension points, đồng thời cung cấp interfaces/composition để mở rộng.

## 44. `equals`/`hashCode` và subtype

Một base class tự định nghĩa `equals` dựa trên fields, sau đó subclass thêm fields có thể dẫn tới vấn đề **đối xứng** hoặc **bắc cầu** nếu mỗi subtype có logic so sánh khác nhau.

Ví dụ về rủi ro ý tưởng:

- Base so sánh chỉ bằng `id`.
- Subclass muốn thêm `region` vào `equals`.
- `base.equals(child)` có thể true, trong khi `child.equals(base)` false nếu viết thiếu nhất quán.

Đây là lý do **value objects** thường được thiết kế `final` hoặc dùng `record` với components bất biến phù hợp, thay vì cho phép subclass thêm state vào mô hình equality.

Nếu nghiệp vụ cần nhiều variants, có thể dùng sealed hierarchy hoặc identifier/value contract được thiết kế rõ.

**Composition giúp giảm nhu cầu subclass các kiểu giá trị**, nhưng việc giữ collaborator object cũng phải xem semantics equality có nên phụ thuộc identity hay value.

## 45. State mutation và concurrency

Composition không tự bảo đảm thread-safety; inheritance cũng vậy.

```java
final class Catalog {
    private final List<String> items =
            new ArrayList<>();
}
```

Dù Catalog final và giữ list private, list vẫn mutable. Nếu nhiều threads cập nhật, phải định nghĩa synchronization hoặc sử dụng immutable snapshots/concurrent collections phù hợp.

Tương tự, một strategy object được **chia sẻ giữa nhiều services** có thể có mutable cache/state. Constructor injection không có nghĩa strategy tự thread-safe.

Khi thiết kế:
- Đánh giá component có **stateless/immutable** không.
- Nếu mutable, ai có quyền ghi?
- Một instance được share hay mỗi request có một instance?
- Đóng resource có ảnh hưởng services khác không?
- Các operations phải atomic ở mức nào?

Đừng chọn inheritance/composition như cách chữa mọi race conditions; chúng giải quyết **cấu trúc quan hệ**, còn concurrency là một hợp đồng khác.

## 46. Dấu hiệu thiết kế nên được refactor

### Từ inheritance sang composition

Dấu hiệu:
- Nhiều subclasses khác nhau chỉ vì config.
- Override method để tắt chức năng superclass bằng exception.
- Subclass chỉ kế thừa để lấy helper method.
- Parent thay đổi khiến hàng loạt subclasses lỗi.
- Test phải subclass service chỉ để fake external dependency.
- Rất nhiều `instanceof`/cast vì hierarchy không phù hợp.
- Kế thừa từ concrete collection nhưng muốn cấm các mutators.

Một hướng refactor:
1. Xác định capability thực sự dùng từ base class.
2. Tạo interface riêng cho capability ấy.
3. Đưa implementation thành collaborator.
4. Inject collaborator vào class đang dùng.
5. Chuyển overrides thành implementations/decorators/strategies khi phù hợp.
6. Test giữ nguyên hành vi public trước khi loại extends.

### Từ composition phức tạp về hierarchy/đơn giản hóa

Dấu hiệu:
- Hàng chục wrapper classes chỉ chuyển tiếp y hệt.
- Những variants thực sự là closed alternatives nhưng dùng `Object` + if/cast.
- Hệ thống cần kiểm tra invariant chung của một họ subtype, nhưng không có abstraction ổn định.
- Các interfaces trùng nhau mà không phục vụ client thực.

Có thể hợp nhất interfaces, dùng record/sealed variants hoặc abstract class có contract rõ. **Refactor theo domain constraints**, không chạy theo khẩu hiệu.

## 47. Một bài toán cần kết hợp cả hai

Giả sử công ty có nhiều `PaymentProvider`, mỗi provider có logic riêng, nhưng một `PaymentService` cần retry và logging.

Thiết kế:
- `PaymentProvider` interface với `pay(...)`.
- `StripeProvider`, `BankProvider` implementations của interface.
- `PaymentService` giữ một provider và một retry policy: composition.
- Một `RetryingProvider` decorator implements `PaymentProvider` và giữ delegate: vừa subtype theo contract, vừa composition.
- Một kết quả thanh toán có thể là sealed `PaymentResult` variants (Success/Failure) nếu tập biến thể được thiết kế đóng.

Sơ đồ ý tưởng:

```text
PaymentService
    |
    +-- has-a --> PaymentProvider <---- implemented by Providers
    |
    +-- has-a --> RetryPolicy

RetryingProvider -- implements --> PaymentProvider
RetryingProvider -- has-a -------> PaymentProvider

PaymentResult (sealed)
    +-- Success
    +-- Failure
```

**Một hệ thống có thể dùng inheritance/interface tại những điểm có subtype thật, composition tại những điểm phối hợp.** Đó thường là phương án cân bằng nhất.

## 48. Một checklist ra quyết định cho pull request

Trước khi viết `extends B`:

1. A có thật sự **là B** theo domain không?
2. Một client nhận B có thể dùng A mà không phát sinh unsupported operation bất ngờ không?
3. Invariants, preconditions và postconditions của B vẫn đúng với A không?
4. A có cần thừa hưởng toàn bộ public/protected contract của B không?
5. Superclass có được thiết kế/tài liệu hóa để subclass override không?
6. Có đang phụ thuộc vào thứ tự gọi internal methods của superclass không?
7. Constructors/hook methods có rủi ro gọi override khi subclass state chưa khởi tạo không?
8. Việc đổi B có thể phá A ở những điểm nào?
9. Quan hệ này có phải chỉ là tái sử dụng code/thuật toán không?
10. Một interface riêng và collaborator có thể diễn đạt ý định đúng hơn không?

Trước khi viết `private final B b;`:

1. A chỉ **dùng** B hay A thực sự **sở hữu** B?
2. Ai tạo B, ai thay B, ai `close()` B nếu cần?
3. Có cần đổi implementation runtime/config không?
4. Interface B có một contract ổn định và đáng tồn tại không?
5. B có được chia sẻ bởi nhiều clients không?
6. Nếu B mutable, có alias ngoài có thể phá invariant không?
7. API có lộ mutable backing object hay collection không?
8. B có cần thread-safe không? Scope của B là singleton/request/object?
9. Có đang tạo interfaces/forwarding code không cần thiết không?
10. Có cần caller truyền B vào hay A nên tự tạo một private detail đơn giản?

Nếu chưa trả lời được những câu quan trọng nhất, nên làm rõ requirement/contract trước khi khóa kiến trúc.

## 49. Bài tập 1: Repository extends collection

**Đề:** `UserRepository` cần thêm/xóa/tìm User, nhưng không muốn caller sửa internal storage tùy ý. Có nên `extends ArrayList<User>` để lấy methods miễn phí?

**Đáp án:** Thường **không**. `ArrayList` cung cấp các mutators rộng và semantics indexed collection không nhất thiết thuộc contract Repository. Dùng **composition** với `List<User>` private, viết API `save`/`findById`/`removeById` phù hợp, bảo vệ các invariants. Dùng interface repository nếu cần nhiều backend implementations.

## 50. Bài tập 2: Hình tròn và hình chữ nhật

**Đề:** Cần duyệt danh sách các hình và tính diện tích, loại hình cố định và mọi hình đáp ứng `area()`. Nên chọn gì?

**Đáp án:** `Shape` interface hoặc abstract class với các implementations `Circle`/`Rectangle` là hợp lý. Nếu không cần shared implementation/state, **interface** thường đủ; nếu cần một template method/contract chung có state, cân nhắc abstract class. Bất kể hướng nào, subtype phải thỏa LSP.

## 51. Bài tập 3: Logging cho tất cả services

**Đề:** `OrderService`, `InvoiceService`, `UserService` đều cần ghi log. Có nên cho chúng `extends Logger`?

**Đáp án:** **Không nên** chỉ để tái sử dụng code. Các services **dùng** Logger, không phải các loại Logger. Inject Logger interface hoặc dùng logging facility hợp lý. Constructor injection có thể làm test và cấu hình dễ hơn, nhưng trách nhiệm vòng đời logger vẫn cần rõ nếu có resources.

## 52. Bài tập 4: Thay kênh thông báo khi chạy

**Đề:** User chọn Email hoặc SMS lúc bấm gửi. Cần thêm Push trong tương lai.

**Đáp án:** Dùng `MessageSender`/`Channel` interface với implementations, service **nhận collaborator theo request hoặc được factory chọn**. Đây là composition/strategy. Một hierarchy của `EmailUser`/`SmsUser` không phản ánh đúng trục thay đổi.

## 53. Bài tập 5: Fixed template algorithm

**Đề:** Mọi import phải `validate -> normalize -> persist`, chỉ khác bước parse dữ liệu, và application chủ động định nghĩa họ import jobs.

**Đáp án:** Abstract base `ImportJob` với `final execute` và abstract/protected `parse` có thể phù hợp. Nếu parse cần được hoán đổi độc lập hoặc một import service hỗ trợ nhiều parser, composition bằng `Parser` interface cũng phù hợp. Quyết định dựa vào extension contract và runtime variability.

## 54. Bài tập 6: Square – Rectangle và LSP

**Đề:** `Rectangle` có `setWidth`/`setHeight` độc lập. `Square extends Rectangle` nhưng mỗi setter buộc hai cạnh bằng nhau.

**Đáp án:** Đây là dấu hiệu **vi phạm LSP** nếu client của Rectangle dựa vào hai chiều có thể đổi độc lập. Dù “Square là hình chữ nhật” theo toán học, mutability contract của Rectangle không phù hợp. Cân nhắc immutable shapes với contract khác, interface Shape, hoặc composition của dimensions theo use case.

## 55. Bài tập 7: Kết hợp audit và compression

**Đề:** Writer cần có thể bật audit, nén dữ liệu, mã hóa, và kết hợp mọi tính năng theo thứ tự cấu hình.

**Đáp án:** Dùng **decorator chain/composition** thường tốt hơn tạo lớp con cho mọi tổ hợp. Mỗi wrapper implement interface Writer và giữ delegate Writer. Cần test thứ tự transformation và ownership của stream/resource, nhất là ai chịu trách nhiệm đóng.

## 56. Bài tập 8: API thư viện chỉ có `AbstractProvider`

**Đề:** Framework công bố abstract class với protected extension points và yêu cầu concrete providers extends nó để đăng ký.

**Đáp án:** Kế thừa là **contract framework đã chọn**, có thể dùng nếu subclass tuân thủ hook/invariant. Bọc framework trong adapter tại boundary để domain của bạn không phải extends sâu một concrete framework type nếu muốn giảm coupling.

## 57. Bài tập 9: Nhiều người dùng một connection pool

**Đề:** Nhiều services nhận cùng một `DataSource` từ DI container; service A kết thúc trước B. Service A có nên close DataSource không?

**Đáp án:** Thường **không** nếu DataSource do container/app sở hữu. Service A chỉ có association/dependency và **mượn** resource. Owner thực sự quản lý close theo application lifecycle. Có field `private final DataSource` không chứng minh ownership transfer.

## 58. Bài tập 10: Success/Failure variants

**Đề:** Một operation trả một trong hai kết quả Success/Failure; tập biến thể đóng và client xử lý theo contract.

**Đáp án:** `sealed interface Result permits Success, Failure` và records tương ứng có thể phù hợp trong Java 17. Đây là quan hệ **subtype variants** chứ không nhất thiết là strategy composition. Nếu logic xử lý kết quả phức tạp, có thể bổ sung visitor/service thay vì chèn quá nhiều switch/cast.

## 59. Bài tập 11: Dynamic payment rules

**Đề:** Payment service có ba dimensions: payment gateway, fraud checker và fee policy. Mỗi thành phần được chọn riêng.

**Đáp án:** Composition của ba interfaces `PaymentGateway`, `FraudChecker`, `FeePolicy`. Thêm một gateway không làm phải tạo mọi tổ hợp fee/fraud subclass. Dùng composition root/factory và xem transaction/ownership/concurrency.

## 60. Bài tập 12: Class dùng cùng một helper không state

**Đề:** Năm classes cần parse một chuỗi số nguyên với cùng quy tắc đơn giản, không config và không external dependencies.

**Đáp án:** Một **static utility** hay method ở đúng abstraction có thể là đủ. Không nhất thiết tạo hierarchy hoặc DI interface. Chọn giải pháp đơn giản đúng contract.

## 61. Bài tập 13: Final class và extensibility

**Đề:** Một value object dùng `final class CustomerId`. Muốn hỗ trợ nhiều cách kiểm tra định dạng ID trong từng thị trường.

**Đáp án:** Giữ `CustomerId` là value object không subclass; dùng **validator strategy** `CustomerIdValidator` hoặc factory/parse policy phù hợp. Đừng loại bỏ final rồi tạo subclasses cho mỗi thị trường nếu các biến thể thật sự là quy tắc xác thực tách biệt với identity.

## 62. Bài tập 14: Protected hooks và rủi ro constructor

**Đề:** Base class constructor gọi `initialize()`, subclass override đọc field được gán trong initializer của subclass.

**Đáp án:** Rủi ro đọc field chưa khởi tạo (có thể thấy `null`/`0`). Tránh gọi overridable methods từ constructors; đặt các bước yêu cầu subtype state vào operation sau construction hoặc dùng component được tạo đầy đủ và điều phối minh bạch.

## 63. Bài tập 15: Một class vừa implements interface vừa giữ delegate

**Đề:** `CachingRepository implements Repository` và có field `Repository delegate`. Đây là inheritance hay composition?

**Đáp án:** **Cả hai khía cạnh:** `CachingRepository` là subtype của interface `Repository` theo contract, và dùng **composition/delegation** tới repository thật. Nó là một wrapper/decorator có thể cache reads. Interface inheritance không đồng nghĩa kế thừa implementation từ concrete repository.

## 64. Sai lầm thường gặp khi lựa chọn

| Sai lầm | Tại sao gây vấn đề | Hướng sửa |
| --- | --- | --- |
| Dùng `extends` chỉ để dùng vài methods | Is-a giả, lộ inherited API, coupling mạnh | Composition/utility |
| Subclass ném `UnsupportedOperationException` cho contract cha | Vi phạm kỳ vọng subtype | Tách role interfaces/hierarchy |
| Một subclass cho từng cấu hình | Bùng nổ tổ hợp | Strategies/components |
| Lạm dụng `instanceof` rồi cast mỗi subtype | Abstraction có thể đang sai | Polymorphism hoặc tách operations phù hợp |
| Superclass constructor gọi overridable hook | Subclass state chưa init | Tránh gọi virtual methods khi construct |
| Subclass phụ thuộc call graph nội bộ của superclass | Fragile base class | Document hooks hoặc delegation |
| Repository extends `ArrayList` | Expose API không thuộc domain | Private collection + methods nghiệp vụ |
| Cho mọi class một interface | Tăng cognitive overhead không có biến thể thực | Chỉ tạo abstraction có consumer/use case |
| Gọi mọi field reference là UML composition | Ownership không tự suy ra | Nêu lifecycle contract |
| Kết luận `final` field làm object immutable | Mutable state vẫn sửa qua reference | Copy/immutable representation |
| Inject shared resource rồi tự `close` | Đóng tài nguyên người khác sở hữu | Xác định owner |
| Dùng inheritance để giải quyết test mocking | Làm méo domain design | Injection qua interface |
| Nghĩ composition không dùng inheritance/interface | Strategy implementation vẫn implements interface | Phân biệt is-a contract và has-a collaborator |
| Nghĩ inheritance luôn nhanh hơn | JVM optimize tùy workload | Benchmark khi cần |
| Dùng sealed cho extension plugin mở | Sealed giới hạn direct subtypes | Interface mở nếu cần extensibility |
| Subclass immutable value để thêm equality fields | Dễ hỏng `equals` contract | Final/record, role abstractions |
| Tạo component mutable dùng chung mà không đồng bộ | Race conditions | Thread-safety/immutability |
| Thay policy runtime không xét transaction | Kết quả thiếu nhất quán | Snapshot policy hoặc controlled lifecycle |

## 65. Kết luận: chọn bằng nghĩa quan hệ và khả năng thay đổi

Một công thức ghi nhớ đơn giản:

```text
Nếu A thật sự là B và thỏa contract B:
    -> Cân nhắc extends/implements.
       Nếu cần shared implementation/state:
           -> Cân nhắc abstract/base class.
       Nếu cần contract vai trò:
           -> Interface có thể đủ.

Nếu A cần B để hoàn thành công việc:
    -> Cân nhắc has-a/uses-a + delegation.
       Nếu B có nhiều implementations:
           -> Interface + DI/Strategy.
       Nếu cần chồng thêm tính năng:
           -> Decorator/Wrapper.
       Nếu cần kết hợp nhiều trục:
           -> Composition nhiều components.

Nếu chỉ cần một phép tính thuần:
    -> Utility/static function có thể đơn giản nhất.
```

**Ba nguyên tắc cuối cùng:**

1. **Đặt is-a đúng nơi thực sự có substitutability.** Kế thừa phải giữ hợp đồng hành vi, không chỉ chia sẻ code.
2. **Dùng composition để mô hình hóa cộng tác và thay đổi độc lập.** Các collaborator được lắp qua interfaces/constructors/factories, nhưng phải xác định ownership và lifetime.
3. **Không cực đoan hóa.** Một thiết kế tốt có thể dùng sealed hierarchy cho kết quả, interfaces cho roles, abstract base class cho framework hook và composition cho strategies trong cùng một ứng dụng.

Cách chọn đúng là cách khiến **yêu cầu cụ thể dễ diễn đạt, invariant dễ bảo vệ, API dễ kiểm thử và thay đổi trong tương lai ít gây tác động ngoài ý muốn**.
